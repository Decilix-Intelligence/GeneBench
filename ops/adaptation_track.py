#!/usr/bin/env python3
"""适配赛道 v1.0-adapt —— 逐级破坏样本生成器（L1 单位 / L2 词汇 / L3 缺协议字段）。

**题源（2026-09-10 用户裁定 N-348 改写）**：**出集规定题的 oracle 产物**。
「规定题」= 出集清单 `ops/manifests/v1.0-smoke.json::released_tasks` 里
`kind != "underdetermined_probe"` 的那些题（`regulated` + `free`）——**探针题不入**。
oracle 产物按 `ORACLE_RELPATHS` 取：S7/S8 的参考解写 `gold/oracle_artifact.json`，
其余阶段写 `solution/artifact.json`（`ops/run_oracles.py:311` 与 `:134` 两处落点）。

**清单现值与裁定原文的差**（如实记，不改判据）：裁定写的是「33 道出集规定题」，
而 2026-09-10 的清单现值是**出集 34 题 = 32 道规定题（regulated 29 + free 3）+ 2 道已放出的
欠定探针题**，另有 6 道探针题挂起。八个阶段各 4 道规定题，一道不多一道不少。
本模块按**清单现值的 32 道**取题源，并在 `_index.json` 里记下这个差。

**后果（用户已知情裁定，不许省 —— 见 `ops/specs/fairness_protocol.md` §7、
`ops/reports/known_limits_v1.md`、`ops/specs/adaptation_track.md` §7）**：
这 32 道题的 oracle 产物由此进入执行面。**跑过适配赛道的被测方，主赛道这 32 题算
「可能已见过答案」。**

**每级 10 例，按阶段分层**：八个阶段各至少 1 例，余下 2 例按固定种子在候选里挑
（优先补上没出现过的 (阶段, 破坏族) 组合）。**种子固定** `SEED`，写进每一份
`mutation.json` 与 `_index.json` —— 同一份题源上重跑，选出来的 30 例逐字相同。

破坏方式**按级别表**（§3 的三张表，代码里是 `_L1_RULES` / `_L2_RULES` / `_L3_RULES`）：

| 级 | 破坏 | oracle | 期望结局 |
| --- | --- | --- | --- |
| L1 | 单位错配（比例写成百分数 / 价格以分计 / 量以手计 / 计数以百计 / 日期紧凑串）| 原件 | 首次通过 |
| L2 | 词汇翻译（字段名、枚举同义词、代码写法换成 tushare / yfinance / akshare 的叫法）| 原件 | 首次通过 |
| L3 | 缺协议字段（三态声明字段 / provenance 项 / 依赖图边）| 原件的 `unresolved` 合法形式 | 正确标记 |

**「源里带的信息足以纠正」是实测的，不是断言**：每例带一条 `recovery.route` 与一个
生成期跑的 `check`：

* `sibling_identity` —— 同一份产物里另有字段与被破坏的字段有恒等式（同名同值的兄弟字段，
  或 `_IDENTITIES` 里登记的显式恒等式）。生成期**实测**它在原件上成立；
* `schema_format` —— 目标 schema 只接受一种写法且映射唯一（ISO 日期 ↔ 紧凑串）；
* `source_unit_declaration` —— 上游交付说明声明了该路径的单位，换算规则在
  `/task/adaptation/unit_table.json` 里。**check = 按表里的换算式回算，逐位还原原值**
  （不是「相信表写对了」）；
* `vendor_alias`（L2）—— 别名在 `/task/adaptation/field_map.json` 里，且**反查唯一**。

破坏函数复用 `ops.run_probe_mutations._m`（import，不改它）。

用法：
    python ops/adaptation_track.py --write                 # 生成到默认答案面根
    python ops/adaptation_track.py --check                 # 只在内存里建 + 自检，不落盘
    python ops/adaptation_track.py --plan                  # 只打印选出来的 30 例（不建）
    python ops/adaptation_track.py --write-protocol-manifest   # 重算适配模块的封闭清单
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import functools
import random
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import genebench_config as cfg                                       # noqa: E402
from reference import artifact_schema as sch                         # noqa: E402
from ops.run_probe_mutations import _m                               # noqa: E402  破坏工具，复用不改

SET_ID = "v1.0-adapt"
SOURCE_SET = "v1.0-smoke"
LEVELS: tuple[str, ...] = ("L1", "L2", "L3")
PER_LEVEL = 10
STAGES: tuple[str, ...] = tuple(sch.STAGES)

#: **选题种子**（N-348：「种子固定」）。改它 = 换一批题 = 换一批 bundle，不要顺手改。
SEED = 20260910

#: 题源（答案面）与产物根（答案面）。**两者都不进 f02**；bundle 里只有 broken/source_meta。
SOURCE_ROOT: Path = cfg.GENEBENCH_ROOT / "reference" / "tasks" / SOURCE_SET
OUT_ROOT: Path = cfg.GENEBENCH_ROOT / "reference" / "adaptation" / SET_ID
#: 出集清单：规定题的**唯一**出处。不在这里第二次列题号。
SET_MANIFEST: Path = _REPO / "ops" / "manifests" / f"{SOURCE_SET}.json"
#: oracle 产物的落点，**按 `ops/run_oracles.py` 的两处实际落点排序**。
ORACLE_RELPATHS: tuple[str, ...] = ("gold/oracle_artifact.json", "solution/artifact.json")

#: 干预工件「适配模块」。挂进容器是 `/task/adaptation/`（由臂机制注入，不进 bundle）。
MODULE_DIR: Path = _REPO / "ops" / "protocol" / "geneprotocol_v1_adapt"
MODULE_STATIC: tuple[str, ...] = ("adaptation.md", "field_map.json", "unit_table.json")
#: 适配模块的发布状态。`draft` 时 `runner/inject.py` 的 P7 门拒绝投放 —— adapt 臂就成了裸臂。
MODULE_STATUS = "released"

UNRESOLVED = sch.UNRESOLVED
PRODUCTS: tuple[str, ...] = ("original.json", "broken.json", "mutation.json", "oracle.json")

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CODE_RE = re.compile(r"^(\d{6})\.(SH|SZ)$")
#: 每条规则在同一道题上最多出多少个候选位点 —— S1 有 1802 个日期叶子，不设帽会把枚举撑爆。
MAX_SITES_PER_RULE = 2
#: 题源产物的**体量帽**。超过它的题不进候选：`s5-eco-01` 的 oracle 产物有 **4.0 MB**
#: （41,700 条 signals），`s4-ops-01` 有 878 KB —— 把它们做成适配题，量到的是「agent 会不会
#: 用脚本改文件而不是把文件读进上下文」，不是适配能力，而且 bundle 也会跟着胖 4 MB。
#: 帽下每个阶段都还剩至少 3 道题（S5 剩 cor/ops/rob，S4 剩 cor/eco/rob），分层不受影响。
MAX_SOURCE_BYTES = 700_000
#: 每道题最多扫多少个叶子找候选。**叶子顺序固定**，所以这个帽不破坏可复现性；
#: 它挡的是 S5-ECO 那种 12.5 万叶子的题（候选在前几百个叶子里就够了）。
MAX_LEAVES_SCANNED = 4000


class AdaptError(RuntimeError):
    pass


# ============================================================== 路径工具


def _at(obj: Any, dotted: str) -> Any:
    """按 `a.b.0.c` 取值。任一层不存在就抛 —— 静默返回 None 会让「路径写错」变成「值就是 None」。"""
    cur = obj
    for k in dotted.split("."):
        if isinstance(cur, list):
            cur = cur[int(k)]
        elif isinstance(cur, dict):
            if k not in cur:
                raise AdaptError(f"路径 {dotted!r} 在 {k!r} 这一层不存在")
            cur = cur[k]
        else:
            raise AdaptError(f"路径 {dotted!r} 在 {k!r} 之前就走到了标量")
    return cur


def _has(obj: Any, dotted: str) -> bool:
    try:
        _at(obj, dotted)
    except (AdaptError, IndexError, KeyError, ValueError):
        return False
    return True


def _parent(obj: Any, dotted: str):
    keys = dotted.split(".")
    cur = obj
    for k in keys[:-1]:
        cur = cur[int(k)] if isinstance(cur, list) else cur[k]
    return cur, keys[-1]


def _drop(art: dict, dotted: str) -> dict:
    """删掉一个键（dict）或一个元素（list），返回改后的深拷贝。"""
    out = copy.deepcopy(art)
    cur, last = _parent(out, dotted)
    if isinstance(cur, list):
        del cur[int(last)]
    else:
        if last not in cur:
            raise AdaptError(f"要删的键不在：{dotted}")
        del cur[last]
    return out


def _leaves(obj: Any, prefix: str = ""):
    """逐叶子 `(dotted_path, value)`。**顺序固定**（dict 按插入序、list 按下标）—— 候选枚举靠它可复现。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _leaves(v, f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _leaves(v, f"{prefix}.{i}" if prefix else str(i))
    else:
        yield prefix, obj


# ============================================================== 差异：一处 = 一个 site


def _same_scalar(a: Any, b: Any) -> bool:
    return type(a) is type(b) and a == b


def _join(prefix: str, key: Any) -> str:
    return f"{prefix}.{key}" if prefix else str(key)


def diff_sites(a: Any, b: Any, prefix: str = "") -> list[dict]:
    """`a` → `b` 的**破坏点**列表。一次改名（同一个父对象上恰好一删一增）算**一处**，
    一次列表长度变化算**一处**（整条被删/被加），其余按叶子逐个算。

    判据存在的理由：L2 的「字段名换成 tushare 的叫法」在 JSON 上是「删一个键 + 加一个键」，
    按叶子数会变成两处，于是「每例只破一处」这条永远不可能满足 —— 那不是破坏样本的问题，
    是差异口径的问题。
    """
    sites: list[dict] = []
    if isinstance(a, dict) and isinstance(b, dict):
        removed = [k for k in a if k not in b]
        added = [k for k in b if k not in a]
        if len(removed) == 1 and len(added) == 1:
            sites.append({"op": "rename", "path": _join(prefix, removed[0]),
                          "to": _join(prefix, added[0])})
        else:
            sites += [{"op": "remove", "path": _join(prefix, k)} for k in removed]
            sites += [{"op": "add", "path": _join(prefix, k)} for k in added]
        for k in a:
            if k in b:
                sites += diff_sites(a[k], b[k], _join(prefix, k))
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            sites.append({"op": "list_length", "path": prefix or "$",
                          "from": len(a), "to": len(b)})
        for i in range(min(len(a), len(b))):
            sites += diff_sites(a[i], b[i], _join(prefix, i))
    elif not _same_scalar(a, b):
        sites.append({"op": "replace", "path": prefix or "$", "from": a, "to": b})
    return sites


# ============================================================== 题源


def regulated_tasks() -> list[dict]:
    """出集**规定题**（探针题不入）。唯一出处是出集清单，不在代码里第二次列题号。"""
    man = json.loads(SET_MANIFEST.read_text(encoding="utf-8"))
    out = []
    for t in man["released_tasks"]:
        if t.get("kind") == "underdetermined_probe":
            continue
        if oracle_path(t["task_id"]).stat().st_size > MAX_SOURCE_BYTES:
            continue                                  # 见 MAX_SOURCE_BYTES
        out.append(t)
    return out


def source_counts() -> dict:
    """题源口径的**现值**，进 `_index.json`。裁定原文写 33，清单现值是 32 —— 差在这里记着。"""
    man = json.loads(SET_MANIFEST.read_text(encoding="utf-8"))
    rel = man["released_tasks"]
    kinds: dict[str, int] = {}
    for t in rel:
        kinds[t["kind"]] = kinds.get(t["kind"], 0) + 1
    return {"released": len(rel), "held": len(man.get("held_tasks") or []),
            "released_by_kind": kinds, "regulated_used": len(regulated_tasks()),
            "ruling_said": 33,
            "_note": "N-348 原文写「33 道出集规定题」；2026-09-10 清单现值是 32 道"
                     "（released 34 = regulated 29 + free 3 + underdetermined_probe 2，"
                     "探针题不入）。以清单现值为准，差如实记。"}


def oracle_path(task_id: str) -> Path:
    for rel in ORACLE_RELPATHS:
        p = SOURCE_ROOT / task_id / rel
        if p.is_file():
            return p
    raise AdaptError(f"{task_id} 没有 oracle 产物（找过 {ORACLE_RELPATHS}）—— "
                     f"先跑 ops/run_oracles.py")


@functools.lru_cache(maxsize=64)
def _load_source(task_id: str) -> tuple[dict, dict, str]:
    """**带缓存**：S5 的题源单份 636 KB，选题期要读它十几次。
    调用方一律 deepcopy 之后再改（`_envelope` / `_m` / `_drop` 都是），所以共享同一份是安全的。"""
    p = oracle_path(task_id)
    art = json.loads(p.read_text(encoding="utf-8"))
    spec = json.loads((SOURCE_ROOT / task_id / "taskspec.json").read_text(encoding="utf-8"))
    return art, spec, str(p.relative_to(SOURCE_ROOT / task_id))


# ============================================================== 恒等式（可纠正性的实测）

#: 显式登记的**跨字段恒等式**：`stage -> [(输出路径, 说明, 检查函数)]`。
#: 同名兄弟（`ic_stats.coverage` ↔ `ic_by_horizon.1.coverage`）由 `_same_key_sibling` 自动发现，
#: 不用登记；这里放的是「算出来才相等」的那几条。
def _identity_rows_times_dims(art: dict) -> bool:
    pr = art["payload"]["panel_ref"]
    return pr["rows"] == pr["n_symbols"] * pr["n_dates"]


def _identity_coverage_sums_to_signals(art: dict) -> bool:
    c, s = art["payload"]["coverage"], art["payload"]["signals"]
    return c["n_valued"] + c["n_null"] + c["n_flat"] == len(s)


def _identity_attribution_total(art: dict) -> bool:
    return art["payload"]["metrics"]["ann_return_net"] == art["payload"]["attribution"]["total"]


_IDENTITIES: dict[str, tuple[tuple[str, str, Callable[[dict], bool]], ...]] = {
    "S2": (("payload.panel_ref.rows", "rows == n_symbols × n_dates", _identity_rows_times_dims),),
    "S5": (("payload.coverage.n_valued", "n_valued + n_null + n_flat == len(signals)",
            _identity_coverage_sums_to_signals),),
    "S7": (("payload.metrics.ann_return_net", "attribution.total == metrics.ann_return_net",
            _identity_attribution_total),),
}


def _norm_path(path: str) -> str:
    """把列表下标抹成 `#`。`payload.signals.0.value` 与 `payload.signals.523.value` 归一后相同 ——
    它们是**同一个重复结构里的两条记录**，值恰好相等是巧合，不是恒等式。"""
    return ".".join("#" if seg.isdigit() else seg for seg in path.split("."))


def _sibling_index(payload: Any) -> dict:
    """`(叶子键, 归一路径, 值) -> [路径]`，一趟建好。逐个候选去全表扫是 O(n²)，
    S5-ECO 有 12.5 万个叶子 —— 那条路跑不出来（实测：十分钟没出第一级）。"""
    idx: dict[tuple, list[str]] = {}
    for path, v in _leaves(payload, "payload"):
        if isinstance(v, bool) or not isinstance(v, (int, float, str)):
            continue
        idx.setdefault((path.split(".")[-1], type(v).__name__, v), []).append(path)
    return idx


def _same_key_sibling(art: dict, site: str, idx: dict | None = None) -> str | None:
    """同名同值的兄弟字段（**不同的重复结构**）。`ic_stats.coverage` ↔ `ic_by_horizon.1.coverage`
    就是它。**只认同名**：值恰好相等的两个不同量（S6 的 `target_weight` 与 `delta_weight`）不是恒等式；
    **且不认同构**：同一个 list 里的两条记录（S5 的两个 `signals.#.value`）也不是。"""
    want = _at(art, site)
    if isinstance(want, bool) or not isinstance(want, (int, float, str)):
        return None
    if idx is None:
        idx = _sibling_index(art.get("payload") or {})
    mine = _norm_path(site)
    for path in idx.get((site.split(".")[-1], type(want).__name__, want), ()):
        if path != site and _norm_path(path) != mine:
            return path
    return None


def _sib(path_a: str, path_b: str) -> Callable[[dict], bool]:
    return lambda art: _has(art, path_a) and _has(art, path_b) and _at(art, path_a) == _at(art, path_b)


# ============================================================== 单位换算（与 unit_table 同源）

#: `unit -> (破坏方向, 还原方向)`。**还原方向就是 `unit_table.json` 里那条换算式**；
#: `source_unit_declaration` 路线的 check 用它把 broken 逐位还原成 original ——
#: 「表写对了」这件事是跑出来的，不是相信出来的。
_UNIT_OPS: dict[str, tuple[Callable[[Any], Any], Callable[[Any], Any]]] = {
    "percent": (lambda v: v * 100.0, lambda v: v / 100.0),
    "cents": (lambda v: v * 100.0, lambda v: v / 100.0),
    "lots": (lambda v: v / 100.0, lambda v: v * 100.0),
    "hundreds": (lambda v: v / 100.0, lambda v: v * 100.0),
    "date_compact": (lambda s: s.replace("-", ""),
                     lambda s: f"{s[0:4]}-{s[4:6]}-{s[6:8]}"),
}


def _restores(site: str, unit: str) -> Callable[[dict], bool]:
    """按 unit_table 的换算式把破坏值还原，**逐位**对回原值（int 也要还原成 int）。"""
    fwd, back = _UNIT_OPS[unit]

    def _f(art: dict) -> bool:
        want = _at(art, site)
        got = back(fwd(want))
        if isinstance(want, int) and not isinstance(want, bool) and isinstance(got, float):
            got = int(round(got))
        return type(got) is type(want) and got == want
    return _f


# ============================================================== 级别表（破坏方式）

PRICE_KEYS = frozenset({"price", "reference_close", "close", "open", "vwap", "avg_price"})
QTY_KEYS = frozenset({"qty", "volume", "vol", "shares", "quantity"})
COUNT_KEYS = frozenset({"rows", "n_rows", "n_symbols", "n_dates", "n_days", "count",
                        "n_valued", "n_obs", "n_trades", "search_count"})
DATE_KEYS = frozenset({"date", "first_valid_date", "start", "end", "trade_date", "as_of"})


@dataclass(frozen=True)
class Cand:
    """一个**候选位点**：(题, 破坏族, 路径) 三元组 + 建例要用的参数。选题只在候选里挑。"""
    level: str
    stage: str
    source_task: str
    family: str
    site: str
    unit: str | None = None
    vendor: str | None = None
    alias: tuple[str, str] | None = None
    gap: str | None = None
    gap_field: str | None = None
    prov_index: int = 0
    route: str = ""
    evidence: str = ""
    sibling: str | None = None
    identity: str | None = None
    new_value: Any = None
    what: str = ""
    why: str = ""

    @property
    def key(self) -> str:
        return f"{self.stage}|{self.source_task}|{self.family}|{self.site}"


def _in_scored_payload(stage: str, site: str) -> bool:
    """位点必须落在**评分器真的比对的那部分**：`PAYLOAD_REQUIRED[stage]` 的某一棵子树，
    或 declarations / provenance。落在别处 = 破坏了但结算看不见，那种题量的是运气。"""
    parts = site.split(".")
    if parts[0] == "payload":
        return len(parts) > 1 and parts[1] in sch.PAYLOAD_REQUIRED[stage]
    return parts[0] in ("declarations", "provenance")


# -------------------------------------------------------------- L1：单位错配


def _l1_candidates(stage: str, task_id: str, art: dict) -> list[Cand]:
    out: list[Cand] = []
    seen: dict[tuple, int] = {}
    idx = _sibling_index(art.get("payload") or {})

    def _add(c: Cand) -> None:
        k = (c.family, c.route)                      # 帽按 (族, 恢复路线) 算：同一族的两条路线
        n = seen.get(k, 0)                           # 是两种题，其中一条不可行时另一条要顶上
        if n >= MAX_SITES_PER_RULE:
            return
        seen[k] = n + 1
        out.append(c)

    # 规则 ①：显式恒等式登记过的位点 —— 最强的可纠正性证据，优先。
    for site, why, check in _IDENTITIES.get(stage, ()):
        if not _has(art, site) or not _in_scored_payload(stage, site):
            continue
        v = _at(art, site)
        unit = "percent" if isinstance(v, float) and 0.0 < v < 1.0 else "hundreds"
        if unit == "hundreds" and not (isinstance(v, int) and not isinstance(v, bool)):
            continue
        _add(Cand("L1", stage, task_id,
                  "unit_ratio_as_percent" if unit == "percent" else "unit_count_as_hundreds",
                  site, unit=unit, route="sibling_identity", identity=why,
                  evidence=f"原件上实测成立：{why}",
                  what=("比例写成百分数" if unit == "percent" else "计数以百计") + f"（{site.split('.')[-1]}）",
                  why="上游按自己的量纲交付；本协议的口径由 unit_table 定死，"
                      "而这一处的可纠正性有产物内部的恒等式兜底"))

    # 规则 ②–⑥：按叶子的**形状**发现位点。
    for n_seen, (path, v) in enumerate(_leaves(art.get("payload") or {}, "payload")):
        if n_seen >= MAX_LEAVES_SCANNED:
            break
        if not _in_scored_payload(stage, path):
            continue
        key = path.split(".")[-1]
        if isinstance(v, bool):
            continue
        if isinstance(v, float) and 0.0 < v < 1.0:
            sib = _same_key_sibling(art, path, idx)
            if sib:
                _add(Cand("L1", stage, task_id, "unit_ratio_as_percent", path, unit="percent",
                          route="sibling_identity", sibling=sib,
                          evidence=f"同名兄弟字段 {sib} 与它在原件上逐位相等",
                          what=f"比例写成百分数（{key}：{v:.6g} → {v * 100:.6g}）",
                          why="比例类字段在很多上游按百分数交付；schema 要求 [0,1] 的比例"))
            else:
                _add(Cand("L1", stage, task_id, "unit_ratio_as_percent", path, unit="percent",
                          route="source_unit_declaration",
                          evidence="source_meta 声明该路径的源侧单位是 percent；"
                                   "unit_table 给 percent→ratio 的 ÷100（生成期实测可逐位还原）",
                          what=f"比例写成百分数（{key}：{v:.6g} → {v * 100:.6g}）",
                          why="比例类字段在很多上游按百分数交付；schema 要求 [0,1] 的比例"))
        elif isinstance(v, (int, float)) and key in PRICE_KEYS and v > 0:
            _add(Cand("L1", stage, task_id, "unit_price_as_cents", path, unit="cents",
                      vendor="tushare", route="source_unit_declaration",
                      evidence="source_meta 声明该路径的源侧单位是 cents；"
                               "unit_table 给 cents→yuan 的 ÷100（生成期实测可逐位还原）",
                      what=f"价格以分计（{key}：{v} 元 → {v * 100} 分）",
                      why="分/厘计价是券商回报与部分行情源的常见口径"))
        elif isinstance(v, int) and key in QTY_KEYS and v > 0 and v % 100 == 0:
            _add(Cand("L1", stage, task_id, "unit_qty_as_lots", path, unit="lots",
                      vendor="tushare", route="source_unit_declaration",
                      evidence="source_meta 声明该路径的源侧单位是 lots；"
                               "unit_table 给 lots→shares 的 ×100（生成期实测可逐位还原）",
                      what=f"下单量以手计（{key}：{v} 股 → {v // 100} 手）",
                      why="A 股一手 = 100 股；tushare 的 vol 就是手，撮合与台账要股"))
        elif isinstance(v, int) and key in COUNT_KEYS and v >= 100:
            _add(Cand("L1", stage, task_id, "unit_count_as_hundreds", path, unit="hundreds",
                      route="source_unit_declaration",
                      evidence="source_meta 声明该路径的源侧单位是 hundreds；"
                               "unit_table 给 hundreds→count 的 ×100（生成期实测可逐位还原）",
                      what=f"计数以百计（{key}：{v} → {v / 100:g}）",
                      why="「以百计」的计数口径在数据交付单里很常见；它不是比例也不是价格，单列一族"))
        elif isinstance(v, str) and key in DATE_KEYS and _DATE_RE.match(v):
            # **两条路线各出一个候选**：`schema_format` 只有在「破坏之后校验器真的会拒」时才成立
            # （`build()` 会实测这一条，不成立就不出这一例）；schema 管不到的位置退到
            # `source_unit_declaration` —— 交付说明写明该路径是紧凑串，换算表给回 ISO。
            for route, ev in (
                ("schema_format",
                 "artifact_schema 只接受 YYYY-MM-DD（生成期实测：紧凑串会被校验器拒）；"
                 "紧凑串到 ISO 的映射唯一"),
                ("source_unit_declaration",
                 "source_meta 声明该路径的源侧单位是 date_compact；unit_table 给 "
                 "YYYYMMDD→YYYY-MM-DD 的重排（生成期实测可逐位还原）")):
                _add(Cand("L1", stage, task_id, "unit_date_compact", path, unit="date_compact",
                          vendor="tushare", route=route, evidence=ev,
                          what=f"日期写成紧凑串（{key}：{v} → {v.replace('-', '')}）",
                          why="tushare 的 trade_date 就是 YYYYMMDD；本协议只收 ISO"))
    return out


# -------------------------------------------------------------- L2：词汇翻译


def _fm() -> dict:
    return load_module("field_map.json")


def _alias_is_unique(fm: dict, kind: str, field_name: str, alias: str) -> bool:
    """反查唯一：这个别名在同一张表里只指向一个 schema 侧取值。查到两个 = 不可接纳，不出成 L2 题。"""
    if kind == "enum":
        hits = [v for v, al in fm["enum_values"][field_name].items() if alias in al]
    else:
        hits = [v for v, al in fm["field_names"].items() if alias in al.values()]
    return len(hits) == 1


def _l2_candidates(stage: str, task_id: str, art: dict) -> list[Cand]:
    fm = _fm()
    out: list[Cand] = []
    seen: dict[tuple, int] = {}

    def _add(c: Cand) -> None:
        k = (c.family, c.route)
        n = seen.get(k, 0)
        if n >= MAX_SITES_PER_RULE:
            return
        seen[k] = n + 1
        out.append(c)

    # ① 枚举同义词（声明层）。
    for f, v in (art.get("declarations") or {}).items():
        if not isinstance(v, str) or f not in fm["enum_values"] or v not in fm["enum_values"][f]:
            continue
        for alias in fm["enum_values"][f][v]:
            if not alias.isascii():                       # 中文别名留给 v1.1，题面里没有中文枚举
                continue
            if not _alias_is_unique(fm, "enum", f, alias):
                continue
            _add(Cand("L2", stage, task_id, "lexicon_enum", f"declarations.{f}",
                      vendor="vendor_alias", alias=(f"{f}:{v}", alias), new_value=alias,
                      route="vendor_alias",
                      evidence=f"field_map.enum_values.{f}.{v} 含 {alias}，且反查唯一",
                      what=f"{f} 写成 {alias}（源侧同义词，schema 侧是 {v}）",
                      why="枚举同义词：翻译方向由协议裁决，不由 agent 自己说了算"))
            break

    # ② 字段名翻译（payload 里出现的 schema 侧字段名）。
    for n_seen, (path, v) in enumerate(_leaves(art.get("payload") or {}, "payload")):
        if n_seen >= MAX_LEAVES_SCANNED:
            break
        if not isinstance(v, str) or not _in_scored_payload(stage, path):
            continue
        if v in fm["field_names"]:
            for vendor, alias in fm["field_names"][v].items():
                if alias == v or not alias.isascii() or not _alias_is_unique(fm, "field", v, alias):
                    continue
                _add(Cand("L2", stage, task_id, "lexicon_field", path, vendor=vendor,
                          alias=(v, alias), new_value=alias, route="vendor_alias",
                          evidence=f"field_map.field_names.{v}.{vendor} == {alias}，且反查唯一",
                          what=f"字段名 {v} 写成 {alias}（{vendor} 的叫法）",
                          why="字段名翻译：别名查得到且唯一，因此可接纳"))
                break
        m = _CODE_RE.match(v)
        if m:
            digits, mkt = m.group(1), m.group(2)
            _add(Cand("L2", stage, task_id, "lexicon_code", path, vendor="akshare",
                      alias=(v, f"{mkt.lower()}{digits}"), new_value=f"{mkt.lower()}{digits}",
                      route="vendor_alias",
                      evidence="field_map.code_notation.patterns.akshare（小写前缀在前、无点号）；"
                               "rules 第 1 条给出唯一还原",
                      what=f"标的代码写成 {mkt.lower()}{digits}（akshare 记法）",
                      why="代码写法：前缀式与点号式一一对应，映射唯一"))
    return out


# -------------------------------------------------------------- L3：缺协议字段


def _l3_candidates(stage: str, task_id: str, art: dict, spec: dict) -> list[Cand]:
    out: list[Cand] = []
    under = set(spec.get("underdetermined") or [])
    n = 0
    for f in (art.get("declarations") or {}):
        if f in under or n >= MAX_SITES_PER_RULE:
            continue
        n += 1
        out.append(Cand("L3", stage, task_id, "gap_declaration", f"declarations.{f}",
                        gap="declaration", gap_field=f, route="not_recoverable",
                        evidence=f"源里没有任何字段能定出 {f} —— 挑一个取值就是静默补全",
                        what=f"上游不带 {f} 声明",
                        why="源中缺失的信息保持缺失、不得由 agent 补全（GeneQuant §3.3）"))
    prov = art.get("provenance") or []
    if prov and isinstance(prov[0], dict) and prov[0].get("artifact_id"):
        out.append(Cand("L3", stage, task_id, "gap_provenance_id", "provenance.0.artifact_id",
                        gap="provenance_id", prov_index=0, route="not_recoverable",
                        evidence="artifact_id 是上游产物的身份，编一个就是伪造引用",
                        what="上游引用只剩阶段、没有 artifact_id",
                        why="引用链断了一环：知道有上游，不知道是哪一份"))
        out.append(Cand("L3", stage, task_id, "gap_provenance_edge", "provenance.0",
                        gap="provenance_edge", prov_index=0, route="not_recoverable",
                        evidence="边的**存在**由 declarations 里的上游声明证明；边的**身份**不可推",
                        what="整条上游引用（依赖图的一条边）被删",
                        why="删掉的是依赖图的一条边，不是一个标量"))
    return out


# ============================================================== 例子


@dataclass(frozen=True)
class Example:
    example_id: str
    level: str
    family: str
    source_task: str
    site: str
    what: str
    why: str
    mutate: Callable[[dict], dict]
    recovery: dict
    check: Callable[[dict], bool] | None = None
    vendor: str | None = None
    unit: str | None = None
    alias: tuple[str, str] | None = None     # (schema 侧名字, 源侧别名)
    gap: str | None = None                   # L3：declaration / provenance_id / provenance_edge
    gap_field: str | None = None             # L3-declaration：哪个声明字段
    prov_index: int = 0                      # L3-provenance*：第几条引用
    stage: str = ""
    seed: int = SEED
    selection: dict = field(default_factory=dict)

    @property
    def expected_outcome(self) -> str:
        return "correct_flag" if self.level == "L3" else "first_pass"


def _mutator(c: Cand) -> Callable[[dict], dict]:
    if c.family.startswith("unit_"):
        fwd, _ = _UNIT_OPS[c.unit or ""]

        def _mu(art: dict) -> dict:
            v = _at(art, c.site)
            nv = fwd(v)
            if c.unit in ("lots",) and float(nv).is_integer():
                nv = int(nv)
            return _m(art, c.site, nv)
        return _mu
    if c.family.startswith("lexicon_"):
        return lambda art: _m(art, c.site, c.new_value)
    if c.gap in ("declaration", "provenance_id", "provenance_edge"):
        return lambda art: _drop(art, c.site)
    raise AdaptError(f"不认识的破坏族 {c.family!r}")


def _checker(c: Cand) -> Callable[[dict], bool] | None:
    if c.route == "sibling_identity":
        if c.sibling:
            return _sib(c.site, c.sibling)
        for site, _why, fn in _IDENTITIES.get(c.stage, ()):
            if site == c.site:
                return fn
        raise AdaptError(f"{c.key}：route=sibling_identity 但既无同名兄弟也无登记的恒等式")
    if c.route == "source_unit_declaration":
        return _restores(c.site, c.unit or "")
    if c.route == "vendor_alias":
        fm = _fm()
        schema_side, source_side = c.alias or ("", "")
        if c.family == "lexicon_enum":
            f, v = schema_side.split(":", 1)
            return lambda art: _alias_is_unique(fm, "enum", f, source_side) \
                and source_side in fm["enum_values"][f][v]
        if c.family == "lexicon_field":
            return lambda art: _alias_is_unique(fm, "field", schema_side, source_side)
        return lambda art: bool(_CODE_RE.match(schema_side)) and \
            source_side.lower() == f"{schema_side[-2:].lower()}{schema_side[:6]}"
    return None                                    # schema_format / not_recoverable：无需实测


def _to_example(c: Cand, example_id: str, rank: int) -> Example:
    return Example(example_id=example_id, level=c.level, family=c.family,
                   source_task=c.source_task, site=c.site, what=c.what, why=c.why,
                   mutate=_mutator(c), recovery={"route": c.route, "evidence": c.evidence,
                                                 "sibling": c.sibling, "identity": c.identity},
                   check=_checker(c), vendor=c.vendor, unit=c.unit, alias=c.alias,
                   gap=c.gap, gap_field=c.gap_field, prov_index=c.prov_index, stage=c.stage,
                   seed=SEED, selection={"seed": SEED, "rank": rank, "candidate_key": c.key})


# ============================================================== 选题（按阶段分层 · 种子固定）


def candidates(level: str) -> list[Cand]:
    """该级在**全部规定题**上的候选位点。顺序只取决于清单顺序与叶子顺序 —— 可复现。"""
    out: list[Cand] = []
    for t in regulated_tasks():
        tid, stage = t["task_id"], t["stage"]
        art, spec, _rel = _load_source(tid)
        if level == "L1":
            out += _l1_candidates(stage, tid, art)
        elif level == "L2":
            out += _l2_candidates(stage, tid, art)
        else:
            out += _l3_candidates(stage, tid, art, spec)
    return out


def _feasible(c: Cand) -> bool:
    """候选能不能真的出成一例：破坏恰好一处 + 可纠正性实测通过 + oracle 过协议校验器。"""
    try:
        build(_to_example(c, "adapt-probe", -1))
    except (AdaptError, KeyError, IndexError, TypeError, ValueError, ZeroDivisionError):
        return False
    return True


def select(level: str) -> list[Example]:
    """每级 10 例：**八个阶段各 1 例**（分层），余下 2 例按固定种子补上没出现过的 (阶段, 族)。"""
    cands = candidates(level)
    picked: list[Cand] = []
    for stage in STAGES:
        pool = sorted([c for c in cands if c.stage == stage], key=lambda c: c.key)
        rng = random.Random(f"{SEED}|{level}|{stage}")
        rng.shuffle(pool)
        chosen = next((c for c in pool if _feasible(c)), None)
        if chosen is None:
            raise AdaptError(f"{level} 在 {stage} 上一个可行候选都没有（候选 {len(pool)} 个）—— "
                             f"分层覆盖不到八个阶段，不出这一级")
        picked.append(chosen)
    used_site = {c.key for c in picked}
    used_pair = {(c.stage, c.family) for c in picked}
    rest = sorted([c for c in cands if c.key not in used_site], key=lambda c: c.key)
    random.Random(f"{SEED}|{level}|extra").shuffle(rest)
    extra: list[Cand] = []
    for want_new_pair in (True, False):              # 先补新组合，补不满再放宽
        for c in rest:
            if len(extra) >= PER_LEVEL - len(STAGES):
                break
            if c.key in used_site:
                continue
            if want_new_pair and (c.stage, c.family) in used_pair:
                continue
            if not _feasible(c):
                continue
            used_site.add(c.key)
            used_pair.add((c.stage, c.family))
            extra.append(c)
    if len(picked) + len(extra) != PER_LEVEL:
        raise AdaptError(f"{level} 只凑出 {len(picked) + len(extra)} 例（要 {PER_LEVEL}）")
    final = sorted(picked + extra, key=lambda c: (STAGES.index(c.stage), c.family, c.source_task, c.site))
    n = level[-1]
    return [_to_example(c, f"adapt-l{n}-{i + 1:02d}", i + 1) for i, c in enumerate(final)]


def _build_examples() -> tuple[Example, ...]:
    out: list[Example] = []
    for lv in LEVELS:
        out += select(lv)
    return tuple(out)


_EXAMPLES_CACHE: tuple[Example, ...] | None = None


def examples() -> tuple[Example, ...]:
    global _EXAMPLES_CACHE
    if _EXAMPLES_CACHE is None:
        _EXAMPLES_CACHE = _build_examples()
    return _EXAMPLES_CACHE


class _LazyExamples(tuple):
    """`AT.EXAMPLES` 保持元组形态（既有调用方与测试都这么用），但**第一次触碰**才去读 30 份题源。
    import 期就扫全集会让任何 `import ops.adaptation_track` 都吃掉几秒钟与几百 MB。"""

    def __new__(cls):
        return super().__new__(cls)

    def _real(self) -> tuple[Example, ...]:
        return examples()

    def __iter__(self):
        return iter(self._real())

    def __len__(self):
        return len(self._real())

    def __getitem__(self, i):
        return self._real()[i]

    def __repr__(self):
        return repr(self._real())

    def __eq__(self, other):
        return self._real() == other

    def __hash__(self):
        return hash(self._real())


EXAMPLES = _LazyExamples()


def by_id() -> dict[str, Example]:
    return {e.example_id: e for e in examples()}


class _LazyById(dict):
    def _real(self):
        return by_id()

    def __getitem__(self, k):
        return self._real()[k]

    def __iter__(self):
        return iter(self._real())

    def __len__(self):
        return len(self._real())

    def get(self, k, default=None):
        return self._real().get(k, default)

    def items(self):
        return self._real().items()

    def keys(self):
        return self._real().keys()

    def values(self):
        return self._real().values()


BY_ID = _LazyById()


# ============================================================== 建例


def _envelope(art: dict, ex: Example, role: str) -> dict:
    """把题源产物的信封改写成**这道适配题**的身份。

    不改写的话，`_task_context_sane` 会用 artifact.task_id 去比 TaskSpec.task_id 而判 malformed；
    更要紧的是：一份写着 `s3-cor-01` 的产物出现在适配题里，读者会以为它就是那道题的答案。
    """
    out = copy.deepcopy(art)
    out["task_id"] = ex.example_id
    out["artifact_id"] = f"{ex.example_id}-{role}"
    out["config_id"] = "oracle" if role == "oracle" else "upstream"
    out["arm"] = "strict" if role == "oracle" else "source"
    return out


def _spec_for(ex: Example, spec: dict) -> dict:
    """这道适配题的 TaskSpec 四键。L3-declaration 把被删的字段从 declared 挪到 underdetermined ——
    源里没有这一项，题面就不该声明它；否则 oracle 标 unresolved 会被判 `declared_field_marked_unresolved`。"""
    out = {"task_id": ex.example_id, "stage": spec["stage"],
           "declared": dict(spec.get("declared") or {}),
           "underdetermined": list(spec.get("underdetermined") or [])}
    if ex.gap == "declaration":
        out["declared"].pop(ex.gap_field, None)
        if ex.gap_field not in out["underdetermined"]:
            out["underdetermined"].append(ex.gap_field)
    return out


def _payload_set(payload: dict, dotted: str, value) -> None:
    cur = payload
    parts = dotted.split(".")
    for k in parts[:-1]:
        cur = cur[k]
    cur[parts[-1]] = value


def build_oracle(ex: Example, original: dict, spec_adapt: dict) -> dict:
    """L1/L2：原件（信封换成 oracle）。L3：原件在缺口上标 `unresolved` 的**合法形式**。"""
    o = _envelope(original, ex, "oracle")
    if ex.level != "L3":
        return o
    if ex.gap == "declaration":
        o["declarations"][ex.gap_field] = UNRESOLVED
        halt = sch.honest_halt_fields(o["stage"], o["declarations"], spec_adapt["underdetermined"])
        for f in sorted(halt):
            _payload_set(o["payload"], f, None)
        o["halted_fields"] = sorted(halt)
    elif ex.gap == "provenance_id":
        o["provenance"][ex.prov_index]["artifact_id"] = UNRESOLVED
    elif ex.gap == "provenance_edge":
        stage_of_edge = original["provenance"][ex.prov_index]["stage"]
        o["provenance"] = copy.deepcopy(original["provenance"])
        o["provenance"][ex.prov_index] = {"stage": stage_of_edge, "artifact_id": UNRESOLVED}
    else:
        raise AdaptError(f"未知 gap 类型 {ex.gap!r}")
    return o


def source_meta(ex: Example, stage: str) -> dict:
    """上游交付说明 —— 随 bundle 进 `/task/input/source_meta.json`。**它不含答案**：
    只说这份产物来自谁、哪些路径用的是源侧单位、哪一项上游根本不带。"""
    m: dict[str, Any] = {
        "schema_version": "1.0",
        "example_id": ex.example_id,
        "vendor": ex.vendor or "upstream_internal",
        "delivered": "/task/input/broken.json",
        "target_schema": f"/task/{stage}.json",
        "notes": "上游按自己的口径交付；目标 schema 与本阶段契约以 /task/ 下的 schema 为准。",
    }
    if ex.recovery.get("route") == "source_unit_declaration" and ex.unit:
        m["units"] = {ex.site: ex.unit}
        m["units_reference"] = "/task/adaptation/unit_table.json"
    if ex.level == "L3":
        m["not_carried"] = [ex.site]
        m["not_carried_note"] = ("上游没有这一项。源中缺失的信息保持缺失 —— "
                                 "不要替它挑一个取值（GeneQuant §3.3）。")
    return m


def build(ex: Example) -> dict:
    """建一例：original / broken / oracle / mutation（内存，不落盘）。任一自检不过即抛。"""
    src_art, src_spec, src_rel = _load_source(ex.source_task)
    original = _envelope(src_art, ex, "source")
    if ex.check is not None and not ex.check(original):
        raise AdaptError(f"{ex.example_id}：`源里带的信息足以纠正` 这条在原件上**实测不成立** "
                         f"（{ex.recovery.get('evidence')}）—— 不出这一例")
    broken = ex.mutate(original)
    sites = diff_sites(original, broken)
    if len(sites) != 1:
        raise AdaptError(f"{ex.example_id}：破坏了 {len(sites)} 处（要恰好 1 处）：{sites[:4]}")
    spec_adapt = _spec_for(ex, src_spec)
    oracle = build_oracle(ex, original, spec_adapt)
    vo = sch.validate(oracle, task=spec_adapt, gateway_log=None, tradability=None)
    if not vo.ok:
        raise AdaptError(f"{ex.example_id}：oracle 过不了协议校验器 —— "
                         + "；".join(str(f) for f in vo.findings[:4]))
    vb = sch.validate(broken, task=spec_adapt, gateway_log=None, tradability=None)
    if ex.recovery.get("route") == "schema_format" and vb.ok:
        raise AdaptError(
            f"{ex.example_id}：route=schema_format 说的是「目标 schema 只收一种写法」，"
            f"而破坏之后的产物**照样过校验器** —— 这一处 schema 管不到，那句话在这里不成立。"
            f"不出这一例（同位点还有一条 source_unit_declaration 的候选会顶上）")
    mutation = {
        "schema_version": "1.0",
        "set_id": SET_ID,
        "example_id": ex.example_id,
        "level": ex.level,
        "family": ex.family,
        "stage": original["stage"],
        "source_set": SOURCE_SET,
        "source_task": ex.source_task,
        "source_kind": "regulated_released",
        "source_artifact": src_rel,
        "seed": ex.seed,
        "selection": dict(ex.selection),
        "site": ex.site,
        "what": ex.what,
        "why": ex.why,
        "unit": ex.unit,
        "vendor": ex.vendor,
        "alias": list(ex.alias) if ex.alias else None,
        "gap": ex.gap,
        "gap_field": ex.gap_field,
        "recovery": dict(ex.recovery),
        "expected_outcome": ex.expected_outcome,
        "diff": sites,
        "taskspec": spec_adapt,
        "source_meta": source_meta(ex, original["stage"]),
        "oracle_validator": {"ok": vo.ok, "findings": [str(f) for f in vo.findings]},
        "broken_validator": {"ok": vb.ok, "findings": [str(f) for f in vb.findings][:8]},
        "_exposure": "本例的题源是出集规定题 " + ex.source_task + " 的 oracle 产物"
                     "（2026-09-10 用户裁定 N-348）。跑过本赛道的被测方，主赛道这道题"
                     "算「可能已见过答案」。",
    }
    return {"example": ex, "original": original, "broken": broken,
            "oracle": oracle, "mutation": mutation, "taskspec": spec_adapt}


# ============================================================== 落盘


def _dump(obj: dict) -> str:
    """**确定性**序列化：不带时间戳、键序固定 —— 清单里的 sha256 才有意义（重跑要能对上）。"""
    return json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=False) + "\n"


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_example(built: dict, out_root: Path = OUT_ROOT) -> dict:
    ex: Example = built["example"]
    d = cfg.create_dir(Path(out_root) / ex.example_id)
    files: dict[str, str] = {}
    for name, obj in (("original.json", built["original"]), ("broken.json", built["broken"]),
                      ("mutation.json", built["mutation"]), ("oracle.json", built["oracle"])):
        text = _dump(obj)
        p = d / name
        p.write_text(text, encoding="utf-8")
        p.chmod(0o600)
        files[name] = _sha_text(text)
    return {"example_id": ex.example_id, "level": ex.level, "family": ex.family,
            "stage": built["original"]["stage"], "source_task": ex.source_task,
            "source_artifact": built["mutation"]["source_artifact"],
            "site": ex.site, "expected_outcome": ex.expected_outcome, "files": files,
            "example_sha256": _sha_text(json.dumps(files, sort_keys=True))}


def read_example(example_id: str, root: Path = OUT_ROOT) -> dict:
    d = Path(root) / example_id
    out = {}
    for name in PRODUCTS:
        out[name.removesuffix(".json")] = json.loads((d / name).read_text(encoding="utf-8"))
    return out


def generate(out_root: Path = OUT_ROOT, only: tuple[str, ...] = ()) -> list[dict]:
    cfg.create_dir(Path(out_root))
    rows = []
    for ex in examples():
        if only and ex.example_id not in only:
            continue
        rows.append(write_example(build(ex), out_root))
    idx = Path(out_root) / "_index.json"
    idx.write_text(_dump({
        "set_id": SET_ID, "n": len(rows), "seed": SEED,
        "source": {"set": SOURCE_SET, "kind": "regulated_released_oracle_artifacts",
                   "relpaths": list(ORACLE_RELPATHS), "counts": source_counts(),
                   "ruling": "N-348（2026-09-10 用户裁定）：题源 = 出集规定题的 oracle 产物，"
                             "探针题不入；每级 10 例按阶段分层；破坏方式按级别表；种子固定。"},
        "exposure": "本集把上述规定题的 oracle 产物送上执行面。跑过本赛道的被测方，"
                    "主赛道这些题算「可能已见过答案」——见 ops/specs/fairness_protocol.md §7。",
        "examples": rows}), encoding="utf-8")
    idx.chmod(0o600)
    return rows


# ============================================================== 适配模块的封闭清单


def module_manifest() -> dict:
    return {
        "protocol_id": "geneprotocol_v1_adapt",
        "status": MODULE_STATUS,
        "_what_this_is": "适配赛道的**干预工件**：挂在 /task/adaptation/，只发给 adapt 臂。"
                         "内容是规则（缺失保持缺失、翻译要声明、可接纳性由协议裁决）+ 两张表，"
                         "**不含任何一道题的答案**。",
        "_closed_set": "artifacts 是封闭集合，每条带 sha256 —— 与 geneprotocol_v1 同一条判据："
                       "「协议工件 = 某个目录里当时有的东西」不可接受。",
        "_placement": "被动存在于 /task/adaptation/；题面只说「若存在」，不说里面有什么。",
        "_released": "2026-09-10（卡 Y2）：内容自 2026-09-07 一字未改，三条 sha 与当时相同；"
                     "改的只有 status —— 用户裁定 N-348 放行本赛道真跑，而 draft 状态下"
                     "注入器 P7 会拒绝投放，adapt 臂就成了裸臂（实测：22.7 s 中止、零次模型调用）。",
        "artifacts": {n: hashlib.sha256((MODULE_DIR / n).read_bytes()).hexdigest()
                      for n in MODULE_STATIC},
    }


def write_module_manifest() -> Path:
    p = MODULE_DIR / "MANIFEST.json"
    p.write_text(json.dumps(module_manifest(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    p.chmod(0o600)
    return p


def load_module(name: str) -> dict:
    return json.loads((MODULE_DIR / name).read_text(encoding="utf-8"))


# ============================================================== CLI


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT_ROOT))
    ap.add_argument("--only", default="")
    ap.add_argument("--check", action="store_true", help="只在内存里建 + 自检，不落盘")
    ap.add_argument("--plan", action="store_true", help="只打印选出来的 30 例（不建例）")
    ap.add_argument("--write", action="store_true", help="落盘到 --out")
    ap.add_argument("--write-protocol-manifest", action="store_true")
    a = ap.parse_args(argv)
    only = tuple(x.strip() for x in a.only.split(",") if x.strip())
    if a.write_protocol_manifest:
        print("适配模块清单已重算：", write_module_manifest())
        return 0
    if a.plan:
        print(f"seed={SEED}  题源={source_counts()}")
        for ex in examples():
            print(f"  {ex.example_id:<14} {ex.level} {ex.stage} {ex.family:<26} "
                  f"← {ex.source_task:<12} {ex.site}")
        return 0
    if a.write:
        rows = generate(Path(a.out), only)
        print(f"生成 {len(rows)} 例 → {a.out}（seed={SEED}）")
        for r in rows:
            print(f"  {r['example_id']:<14} {r['level']} {r['stage']} {r['family']:<26} "
                  f"← {r['source_task']}  期望结局={r['expected_outcome']}")
        return 0
    # 默认 = --check
    n = 0
    for ex in examples():
        if only and ex.example_id not in only:
            continue
        b = build(ex)
        n += 1
        print(f"[ok] {ex.example_id:<14} {ex.level} {b['original']['stage']} "
              f"破坏 1 处 · oracle 过校验器 · broken 校验 ok={b['mutation']['broken_validator']['ok']}")
    print(f"{n} 例自检通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
