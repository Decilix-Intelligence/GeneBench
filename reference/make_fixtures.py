# -*- coding: utf-8 -*-
"""物化各阶段题面 `inputs` 声明的夹具（一次性、有序；裁定 2026-09-05）。

**驱动源是题面的 `inputs[].origin`**，不是一张我自己另写的表 ——
另写一张表就有了两份「哪道题要什么」，而两份会漂，漂了的表现是
「题面声明了一个文件，任务目录里没有」或者反过来（都不会有人报）。

支持的 origin 形态（**认不出的一律报错，不猜**）：

| origin | 落点 | 来源 |
| --- | --- | --- |
| `reference/gold_factors/<uni>/<factor_id>` | `work/factor_panel.parquet` | `snapshots/v1/gold_factors/<uni>/<fid>.parquet` 切窗口 |
| 同上 + `#meta` | `work/factor_panel.meta.json` | 上一条的 `{stage, artifact_id, sha256, max_date}` |
| `2.1b gold 因子面板 <fid> @<uni> 切到 window…` | `work/inputs/<fid>.parquet` | 同一份 gold 因子 |
| `f01 物化：输入因子清单…` | `work/inputs/manifest.json` | 同目录下所有输入因子的清单 |
| `signal:s7_dedicated_signal_v1` | 见 `reference/make_s7_signal.py` | 冻结 ε 面板的 signal 列 |

**两族尚未定义、本模块拒绝猜**（见 `ops/tickets.md` N-99）：
`reference/pools/s4_eco_pool_v1`（S4 的因子池：哪些因子、几只，全仓没有定义）与
`reference/signals/*`（S6 的输入信号 = S5 gold，其中 `s6_sparse_coverage_csi300_v1`
还要求"若干日只剩 < N 只非 null 标的"，稀疏到什么程度也没有定义）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import genebench_config as cfg                                        # noqa: E402

GOLD_FACTORS = cfg.SNAPSHOTS / "v1" / "gold_factors"
TASK_SET = "v1.0-smoke"
FACTOR_COLUMNS = ("date", "code", "value")

_GOLD = re.compile(r"^reference/gold_factors/(?P<uni>[^/]+)/(?P<fid>[^#]+?)(?P<meta>#meta)?$")
_S5_INPUT = re.compile(r"^2\.1b gold 因子面板 (?P<fid>\S+) @(?P<uni>\S+) 切到 window")
_S5_MANIFEST = re.compile(r"^f01 物化：输入因子清单")
_BLOCKED: tuple[str, ...] = ()          # N-99 三族都已定义（2026-09-05 裁定）
_SIGNAL_CARD: dict[str, dict] = {}


#: `s4_eco_pool_v1`（裁定 N-99 ①，2026-09-05）：从 csi300 gold_factors 取 30 条，每族 10 条，
#: **按 ID 排序等距取（不看 IC，避免泄漏）**，排除全窗 degenerate 与覆盖率 < 95% 的。
#: 选取规则与最终清单写进夹具数据卡（`ops/data_cards/fixture_s4_eco_pool_v1.md`）。
POOL_ID = "s4_eco_pool_v1"
POOL_FAMILIES: tuple[str, ...] = ("gtja_191", "worldquant_101", "qlib_alpha158")
POOL_PER_FAMILY = 10
POOL_COVERAGE_MIN = 0.95
_POOL_ORIGIN = f"reference/pools/{POOL_ID}"


def factor_stats(factor_id: str, universe: str, start: str, max_date: str) -> dict:
    """窗口内的覆盖率与是否 degenerate。**只看这一段**，不看全史。"""
    df = slice_factor(factor_id, universe, start, max_date)
    nn = df["value"].notna()
    cov = float(nn.mean()) if len(df) else 0.0
    vals = df.loc[nn, "value"]
    degenerate = (len(vals) == 0) or (vals.nunique() <= 1)
    return {"factor_id": factor_id, "rows": int(len(df)), "coverage": cov,
            "degenerate": bool(degenerate), "nunique": int(vals.nunique())}


def equidistant(items: list, k: int) -> list:
    """从已排序的 n 个里等距取 k 个：下标 round(i·(n−1)/(k−1))。**确定性、不看任何数值。**"""
    n = len(items)
    if n < k:
        raise FixtureError(f"合格因子只有 {n} 个，取不出 {k} 个")
    if k == 1:
        return [items[0]]
    idx = sorted({round(i * (n - 1) / (k - 1)) for i in range(k)})
    if len(idx) != k:                     # 只有 n 很小时才会撞，撞了就是没法等距
        raise FixtureError(f"等距下标重复：n={n}, k={k}")
    return [items[i] for i in idx]


def build_pool(universe: str, start: str, max_date: str) -> tuple[pd.DataFrame, dict]:
    """返回 `(长表 date/code/factor_id/value, 选取记录)`。"""
    card: dict = {"pool_id": POOL_ID, "universe": universe, "window": [start, max_date],
                  "rule": {"per_family": POOL_PER_FAMILY, "coverage_min": POOL_COVERAGE_MIN,
                           "order": "factor_id 字典序", "pick": "等距下标 round(i·(n−1)/(k−1))",
                           "excluded": "全窗 degenerate（非空值唯一值 ≤ 1）或覆盖率 < coverage_min"},
                  "families": {}}
    frames = []
    src_dir = GOLD_FACTORS / universe
    for fam in POOL_FAMILIES:
        ids = sorted(p.stem for p in src_dir.glob(f"{fam}.*.parquet"))
        if not ids:
            raise FixtureError(f"{src_dir} 下没有 {fam}.* 的因子")
        stats = [factor_stats(f, universe, start, max_date) for f in ids]
        eligible = [t for t in stats if not t["degenerate"] and t["coverage"] >= POOL_COVERAGE_MIN]
        chosen = equidistant([t["factor_id"] for t in eligible], POOL_PER_FAMILY)
        card["families"][fam] = {
            "candidates": len(ids), "eligible": len(eligible), "chosen": chosen,
            "excluded": [{k: t[k] for k in ("factor_id", "coverage", "degenerate")}
                         for t in stats if t not in eligible]}
        for fid in chosen:
            df = slice_factor(fid, universe, start, max_date)
            frames.append(df.assign(factor_id=fid)[["date", "code", "factor_id", "value"]])
    pool = pd.concat(frames, ignore_index=True).sort_values(["date", "code", "factor_id"])
    card["n_factors"] = int(pool["factor_id"].nunique())
    card["rows"] = int(len(pool))
    return pool.reset_index(drop=True), card


def write_pool_card(card: dict, path: Path) -> None:
    lines = [f"# 夹具数据卡：`{card['pool_id']}`", "",
             f"**宇宙** `{card['universe']}` · **窗口** `{card['window'][0]}` … `{card['window'][1]}`"
             f" · **{card['n_factors']} 条因子 / {card['rows']:,} 行**", "",
             "## 选取规则（裁定 N-99 ①，2026-09-05）", "",
             f"* 每族 **{card['rule']['per_family']}** 条，三族：{', '.join(POOL_FAMILIES)}；",
             f"* 按 {card['rule']['order']}排序，{card['rule']['pick']} —— **不看 IC**，避免选择泄漏；",
             f"* 排除：{card['rule']['excluded']}（阈值 {card['rule']['coverage_min']}）。",
             "", "## 最终清单", ""]
    for fam, info in card["families"].items():
        lines.append(f"### {fam}（候选 {info['candidates']} → 合格 {info['eligible']} → 取 {len(info['chosen'])}）")
        lines.append("")
        lines += [f"- `{f}`" for f in info["chosen"]]
        if info["excluded"]:
            lines.append("")
            lines.append(f"排除 {len(info['excluded'])} 条：" + "、".join(
                f"`{e['factor_id']}`({'degenerate' if e['degenerate'] else f'cov={e[chr(99)+chr(111)+chr(118)+chr(101)+chr(114)+chr(97)+chr(103)+chr(101)]:.3f}'})"
                for e in info["excluded"][:30]) + ("…" if len(info["excluded"]) > 30 else ""))
        lines.append("")
    cfg.create_dir(path.parent)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o600)


#: `s5_gtja001_csi300_v1`（裁定 N-99 ②）：= **S5 oracle（s5-cor-01）** 在 gtja_191.001 × csi300 上的
#: gold 输出。链：S3 gold 因子 → S5 oracle → 信号夹具。
#:
#: **窗口取 S6 消费方的并集**：s5-cor-01 自己的窗口是 07-01..07-31，而 s6-eco-01/ops-01 从 05-06、
#: s6-rob-02 从 06-01 起 —— 照 S5 自己的窗口出信号，三道 S6 题的前两个月没有信号。
#: 所以把**同一份 S5 oracle 代码**放进一个窗口放宽的 scratch 任务目录里跑（统一 I/O 契约：
#: 读标准位置的任务规格、经网关取数、写标准路径 —— 一个字节不改），再按每个消费方的窗口切片。
#: S5 的 rank 信号是**逐日横截面**的，与窗口起点无关，所以在 07-01..07-31 这段上
#: 放宽版与 s5-cor-01 的真 gold **必须逐值相同** —— `_assert_matches_s5_gold` 盯着这条。
SIGNAL_SRC_TASK = "s5-cor-01"
SIGNAL_DENSE_ID = "s5_gtja001_csi300_v1"
SIGNAL_SPARSE_ID = "s6_sparse_coverage_csi300_v1"
#: `s6_sparse_coverage_csi300_v1`（裁定 N-99 ③）：取 ② 的信号，窗口内**每第 7 个交易日**
#: （从首日起，确定性）把当日除**代码最小的 3 只**以外全部置 null；其余日不动。
#: 3 < max_weight=0.1 下 full_investment 所需的 10 只 —— 构造无可行解（陷阱日）。
SPARSE_EVERY = 7
SPARSE_KEEP = 3
SCRATCH_SIGNAL = cfg.GENEBENCH_ROOT / "scratch" / "s6_signal_gen"
_SIGNAL_ORIGIN = re.compile(r"^reference/signals/(?P<sid>[^/]+)/slice\.parquet$")
_DENSE_CACHE: dict[str, "pd.DataFrame"] = {}


def _gateway_url() -> str:
    import os
    return os.environ.get("GENEBENCH_GATEWAY_URL", "http://192.168.1.48:18080")


def s6_consumer_window(set_root: Path) -> tuple[str, str]:
    """所有引用 `reference/signals/*` 的题的窗口并集。"""
    lo, hi = None, None
    for d in sorted(set_root.iterdir()):
        f = d / "task.yaml"
        if not f.is_file():
            continue
        t = yaml.safe_load(f.read_text(encoding="utf-8"))
        if not any(str(i.get("origin", "")).startswith("reference/signals/")
                   for i in (t.get("inputs") or [])):
            continue
        w = t["window"]
        lo = w["start"] if lo is None or w["start"] < lo else lo
        hi = w["end"] if hi is None or w["end"] > hi else hi
    if lo is None:
        raise FixtureError("没有任何题引用 reference/signals/*")
    return lo, hi


def run_s5_oracle_widened(set_root: Path, start: str, end: str) -> pd.DataFrame:
    """把 s5-cor-01 的 oracle **原样**放进窗口放宽的 scratch 任务目录跑一遍，取 payload.signals。"""
    import shutil
    import subprocess
    src = set_root / SIGNAL_SRC_TASK
    if not (src / "solution" / "solve.py").is_file():
        raise FixtureError(f"{src}/solution/solve.py 不存在 —— 先出集")
    task = yaml.safe_load((src / "task.yaml").read_text(encoding="utf-8"))
    (fid,) = task["declared"]["input_factors"]
    uni = task["universe"]

    d = SCRATCH_SIGNAL / SIGNAL_SRC_TASK
    if d.exists():
        shutil.rmtree(d)
    cfg.create_dir(d / "solution")
    cfg.create_dir(d / "work" / "inputs")
    t2 = dict(task)
    t2["window"] = {"start": start, "end": end}
    (d / "task.yaml").write_text(yaml.safe_dump(t2, allow_unicode=True, sort_keys=False),
                                 encoding="utf-8")
    (d / "task.yaml").chmod(0o600)
    shutil.copyfile(src / "solution" / "solve.py", d / "solution" / "solve.py")
    (d / "solution" / "solve.py").chmod(0o600)
    # 统一 I/O 契约要求任务目录里有 `taskspec.json`（`oracle_io.context` 读它）—— 原样带上，
    # 它是 X 面（task_id/stage/declared/underdetermined），窗口放宽不改声明。
    shutil.copyfile(src / "taskspec.json", d / "taskspec.json")
    (d / "taskspec.json").chmod(0o600)
    df = slice_factor(fid, uni, start, task["as_of"])
    sha = _write_parquet(df, d / "work" / "inputs" / f"{fid}.parquet")
    _write_json([{"factor_id": fid, "path": f"work/inputs/{fid}.parquet", "stage": "S3",
                  "artifact_id": f"gold:{fid}@{uni}", "sha256": sha,
                  "max_date": task["as_of"]}], d / "work" / "inputs" / "manifest.json")

    import os
    env = dict(os.environ, GENEBENCH_GATEWAY_URL=_gateway_url(),
               GENEBENCH_ORACLE_OUT=str(d / "solution" / "artifact.json"),
               PYTHONPATH=str(Path(__file__).resolve().parents[1]))
    r = subprocess.run([sys.executable, str(d / "solution" / "solve.py")], cwd=d,
                       capture_output=True, text=True, timeout=3600, env=env)
    if r.returncode != 0:
        raise FixtureError(f"放宽窗口的 S5 oracle 失败 rc={r.returncode}：{r.stderr[-600:]}")
    art = json.loads((d / "solution" / "artifact.json").read_text(encoding="utf-8"))
    sig = pd.DataFrame(art["payload"]["signals"])
    miss = [c for c in ("date", "symbol", "value") if c not in sig.columns]
    if miss or sig.empty:
        raise FixtureError(f"放宽版 S5 信号缺列 {miss} 或为空")
    return sig.sort_values(["date", "symbol"]).reset_index(drop=True)


def _assert_matches_s5_gold(set_root: Path, wide: pd.DataFrame) -> dict:
    """放宽版在 s5-cor-01 自己的窗口上必须与 s5-cor-01 的真 gold **逐值相同**。
    rank 是逐日横截面的，与窗口起点无关；不同 = 放宽改变了算法，那份就不是 gold。"""
    art_p = set_root / SIGNAL_SRC_TASK / "solution" / "artifact.json"
    if not art_p.is_file():
        return {"checked": False, "why": f"{art_p} 还没有（先跑 s5-cor-01 的 oracle）"}
    gold = pd.DataFrame(json.loads(art_p.read_text(encoding="utf-8"))["payload"]["signals"])
    key = ["date", "symbol"]
    m = gold.merge(wide, on=key, how="left", suffixes=("_g", "_w"))
    if m["value_w"].isna().sum() != m["value_g"].isna().sum() or len(m) != len(gold):
        raise FixtureError("放宽版信号在 s5-cor-01 窗口上的行集或空值形态与真 gold 不同")
    both = m["value_g"].notna() & m["value_w"].notna()
    same = (m.loc[both, "value_g"].astype(str) == m.loc[both, "value_w"].astype(str))
    if not bool(same.all()):
        raise FixtureError(f"放宽版信号与 s5-cor-01 真 gold 有 {int((~same).sum())} 个值不同")
    return {"checked": True, "rows": int(len(gold))}


def dense_signal(set_root: Path) -> pd.DataFrame:
    if SIGNAL_DENSE_ID not in _DENSE_CACHE:
        lo, hi = s6_consumer_window(set_root)
        wide = run_s5_oracle_widened(set_root, lo, hi)
        _DENSE_CACHE[SIGNAL_DENSE_ID] = wide
        _DENSE_CACHE["_window"] = (lo, hi)
        _DENSE_CACHE["_check"] = _assert_matches_s5_gold(set_root, wide)
    return _DENSE_CACHE[SIGNAL_DENSE_ID]


def _slice_signal(sig: pd.DataFrame, start: str, max_date: str) -> pd.DataFrame:
    d = sig["date"].astype(str).str.replace("-", "", regex=False)
    out = sig[(d >= _compact(start)) & (d <= _compact(max_date))]
    if out.empty:
        raise FixtureError(f"信号在 {start}..{max_date} 为空")
    return out.reset_index(drop=True)


def sparsify(sig: pd.DataFrame, *, every: int = SPARSE_EVERY, keep: int = SPARSE_KEEP
             ) -> tuple[pd.DataFrame, list[str]]:
    """每第 `every` 个交易日（从首日起）只留代码最小的 `keep` 只，其余置 null。"""
    days = sorted(sig["date"].astype(str).unique())
    trap = days[::every]
    out = sig.copy()
    nulled: list[str] = []
    for day in trap:
        mask = out["date"].astype(str) == day
        syms = sorted(out.loc[mask, "symbol"].astype(str).unique())
        keepers = set(syms[:keep])
        kill = mask & ~out["symbol"].astype(str).isin(keepers)
        out.loc[kill, "value"] = None
        nulled.append(day)
    return out, nulled


def write_signal_card(set_root: Path, path: Path, extra: dict) -> None:
    lo, hi = _DENSE_CACHE.get("_window", ("?", "?"))
    chk = _DENSE_CACHE.get("_check", {})
    lines = ["# 夹具数据卡：S6 输入信号（N-99 ②③）", "",
             f"## `{SIGNAL_DENSE_ID}`（②）", "",
             f"= **S5 oracle（{SIGNAL_SRC_TASK}）**在 gtja_191.001 × csi300 上的 gold 输出。",
             f"窗口放宽到 S6 消费方并集 `{lo}` … `{hi}`（同一份 oracle 代码，放进 scratch 任务目录跑）。",
             f"与 {SIGNAL_SRC_TASK} 真 gold 在其自身窗口上的逐值核对：`{chk}`。",
             "每个消费方按自己的 `window.start … max_date` 切片。", "",
             f"## `{SIGNAL_SPARSE_ID}`（③）", "",
             f"取 ② 的信号，窗口内**每第 {SPARSE_EVERY} 个交易日**（从首日起，下标 0,{SPARSE_EVERY},{2*SPARSE_EVERY},…）"
             f"把当日除**代码最小的 {SPARSE_KEEP} 只**以外全部置 null；其余日不动。",
             f"{SPARSE_KEEP} < `max_weight=0.1` 下 `full_investment` 所需的 10 只 —— 那些日子构造无可行解。", ""]
    for tid, info in extra.items():
        lines.append(f"### {tid}")
        lines.append("")
        for k, v in info.items():
            lines.append(f"- {k}: `{v}`")
        lines.append("")
    cfg.create_dir(path.parent)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o600)


class FixtureError(RuntimeError):
    pass


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _compact(d: str) -> str:
    return str(d).replace("-", "")


def slice_factor(factor_id: str, universe: str, start: str, max_date: str) -> pd.DataFrame:
    """gold 因子面板切到 `[start, max_date]`。

    `max_date` 取**题面声明的那个**，不是窗口末日：它是这份输入的 PIT 上界，
    题面已经把它写给 agent 了。切过头就是给 agent 多发了它不该有的行。
    """
    src = GOLD_FACTORS / universe / f"{factor_id}.parquet"
    if not src.is_file():
        raise FixtureError(f"gold 因子不存在：{src}")
    df = pd.read_parquet(src)
    miss = [c for c in FACTOR_COLUMNS if c not in df.columns]
    if miss:
        raise FixtureError(f"{src} 缺列 {miss}（要 {FACTOR_COLUMNS}）")
    lo, hi = _compact(start), _compact(max_date)
    out = df[(df["date"].astype(str) >= lo) & (df["date"].astype(str) <= hi)]
    if out.empty:
        raise FixtureError(f"{factor_id} 在 {start}..{max_date} 一行都没有 —— 空夹具不许落盘")
    return out[list(FACTOR_COLUMNS)].sort_values(["date", "code"]).reset_index(drop=True)


def _write_parquet(df: pd.DataFrame, path: Path) -> str:
    cfg.create_dir(path.parent)
    df.to_parquet(path, index=False, compression="zstd")
    path.chmod(0o600)
    return sha256_file(path)


def _write_json(obj, path: Path) -> str:
    cfg.create_dir(path.parent)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    path.chmod(0o600)
    return sha256_file(path)


def materialize(task_dir: Path, task: dict, *,
                skip_blocked: bool = False) -> tuple[dict[str, str], list[str]]:
    """按题面 `inputs` 物化这一道题的夹具。返回 `(相对路径 → sha256, 跳过的)`。

    `skip_blocked`：把**尚无定义**的那几族点名跳过而不是整批中止 ——
    能做的做完、做不了的报出来。**默认仍是中止**：静默跳过等于"夹具生成完成了"。
    """
    uni, win = task["universe"], task["window"]
    done: dict[str, str] = {}
    skipped: list[str] = []
    pending_meta: list[dict] = []
    inputs = list(task.get("inputs") or [])

    for item in inputs:
        rel, origin = str(item["path"]), str(item.get("origin", ""))
        if origin == _POOL_ORIGIN:
            pool, card = build_pool(uni, win["start"], item["max_date"])
            done[rel] = _write_parquet(pool, task_dir / rel)
            write_pool_card(card, Path(__file__).resolve().parents[1] / "ops" / "data_cards"
                            / f"fixture_{POOL_ID}.md")
            _write_json(card, task_dir / "gold" / f"{POOL_ID}.selection.json")
            continue
        m = _SIGNAL_ORIGIN.match(origin)
        if m:
            sid = m.group("sid")
            set_root = task_dir.parent
            base = _slice_signal(dense_signal(set_root), win["start"], item["max_date"])
            if sid == SIGNAL_DENSE_ID:
                done[rel] = _write_parquet(base, task_dir / rel)
                _SIGNAL_CARD.setdefault(task["task_id"], {})["dense_rows"] = len(base)
            elif sid == SIGNAL_SPARSE_ID:
                sparse, nulled = sparsify(base)
                done[rel] = _write_parquet(sparse, task_dir / rel)
                _write_json({"signal_id": sid, "every": SPARSE_EVERY, "keep": SPARSE_KEEP,
                             "nulled_dates": nulled}, task_dir / "gold" / f"{sid}.construction.json")
                _SIGNAL_CARD.setdefault(task["task_id"], {}).update(
                    {"sparse_rows": len(sparse), "nulled_dates": nulled})
            else:
                raise FixtureError(f"{task['task_id']} 引用了没有定义的信号 {sid}")
            continue
        if origin.startswith(_BLOCKED):
            if skip_blocked:
                skipped.append(f"{task['task_id']}:{rel} ← {origin}")
                continue
            raise FixtureError(
                f"{task['task_id']} 的 {rel} 来自 {origin} —— **这一族还没有定义**"
                f"（N-99）。不猜：猜出来的夹具会变成 gold 的一部分")
        if origin.startswith("signal:"):
            continue                        # S7 的专用信号走 `make_s7_signal.py`
        m = _GOLD.match(origin)
        if m:
            if m.group("meta"):
                pending_meta.append({"rel": rel, "fid": m.group("fid")})
                continue
            df = slice_factor(m.group("fid"), m.group("uni"), win["start"], item["max_date"])
            done[rel] = _write_parquet(df, task_dir / rel)
            done.setdefault("_fid", m.group("fid"))
            continue
        m = _S5_INPUT.match(origin)
        if m:
            df = slice_factor(m.group("fid"), m.group("uni"), win["start"], item["max_date"])
            done[rel] = _write_parquet(df, task_dir / rel)
            continue
        if _S5_MANIFEST.match(origin):
            pending_meta.append({"rel": rel, "manifest": True})
            continue
        raise FixtureError(f"{task['task_id']} 的 {rel} 有不认识的 origin：{origin!r}")

    # meta / manifest 要等同批的 parquet 都落完才算得出 sha
    for pm in pending_meta:
        if pm.get("manifest"):
            entries = []
            for item in inputs:
                r = str(item["path"])
                if r.startswith("work/inputs/") and r.endswith(".parquet") and r in done:
                    entries.append({"factor_id": Path(r).stem, "path": r, "stage": "S3",
                                    "artifact_id": f"gold:{Path(r).stem}@{uni}",
                                    "sha256": done[r], "max_date": item["max_date"]})
            if not entries:
                raise FixtureError(f"{task['task_id']} 的清单一条都没有 —— 空清单不是清单")
            done[pm["rel"]] = _write_json(entries, task_dir / pm["rel"])
        else:
            src_rel = pm["rel"].replace(".meta.json", ".parquet")
            if src_rel not in done:
                raise FixtureError(f"{pm['rel']} 找不到对应的 {src_rel}")
            item = next(i for i in inputs if str(i["path"]) == src_rel)
            done[pm["rel"]] = _write_json(
                {"stage": "S3", "artifact_id": f"gold:{pm['fid']}@{uni}",
                 "sha256": done[src_rel], "max_date": item["max_date"]},
                task_dir / pm["rel"])
    done.pop("_fid", None)
    return done, skipped


PARAMS = Path(__file__).resolve().parents[1] / "genetask" / "params" / "v1.0-smoke40.yaml"


def write_params_shas(shas: dict[str, dict[str, str]], params: Path = PARAMS) -> int:
    """把 `{task_id: {rel: sha}}` 写回 **params**（题面的源头）。

    不写生成出来的 `task.yaml`：那份每次 `build_task` 都会重建，
    写进去下一次就没了 —— 而"没了"的表现是 `sha256: null`，
    也就是"这份夹具没有身份"，跟没写一样。
    """
    doc = yaml.safe_load(params.read_text(encoding="utf-8")) or {}
    n = 0
    for row in (doc.get("rows") or []):
        want = shas.get(row.get("task_id"))
        if not want:
            continue
        for item in (row.get("inputs") or []):
            sha = want.get(str(item.get("path")))
            if sha and item.get("sha256") != sha:
                item["sha256"] = sha
                n += 1
    params.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False),
                      encoding="utf-8")
    params.chmod(0o600)
    return n


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--set-id", default=TASK_SET)
    ap.add_argument("--stages", default="S4,S5,S6", help="逗号分隔")
    ap.add_argument("--skip-blocked", action="store_true",
                    help="尚无定义的夹具族点名跳过（默认中止）")
    ap.add_argument("--write-params", action="store_true",
                    help="把 sha 写回 params（题面的源头；任务集面改动，要跟着推版本）")
    a = ap.parse_args(argv)
    stages = {s.strip().upper() for s in a.stages.split(",") if s.strip()}

    root = cfg.GENEBENCH_ROOT / "reference" / "tasks" / a.set_id
    report: dict[str, dict] = {}
    all_skipped: list[str] = []
    for d in sorted(root.iterdir()):
        f = d / "task.yaml"
        if not f.is_file():
            continue
        task = yaml.safe_load(f.read_text(encoding="utf-8"))
        if task.get("stage") not in stages or not task.get("inputs"):
            continue
        placed, skipped = materialize(d, task, skip_blocked=a.skip_blocked)
        report[task["task_id"]] = placed
        all_skipped.extend(skipped)
    if _SIGNAL_CARD:
        write_signal_card(root, Path(__file__).resolve().parents[1] / "ops" / "data_cards"
                          / "fixture_s6_signals.md", _SIGNAL_CARD)
    n_sha = write_params_shas(report) if a.write_params else 0
    print(json.dumps({"tasks": len(report), "params_sha_written": n_sha,
                      "files": {k: sorted(v) for k, v in report.items()},
                      "skipped_because_undefined": sorted(all_skipped)},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
