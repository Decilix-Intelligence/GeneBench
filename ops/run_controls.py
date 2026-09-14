#!/usr/bin/env python3
"""三控走**完整评分器**（M6 产出 ②，裁定 2026-09-05）。

三桩产物 —— `oracle`（参考解）/ `null`（空产物）/ `filler`（静默补全）—— 各造一个**最小 run 目录**，
走的是生产入口 `scorer.score_run.score_run`（采集 → 分类 → 闸门三态 → L3 → 过 `validate_scorer_output` → 效果分），
**不是**旁路直接调校验器。旁路能过而生产路径过不了，是本轮已经出现过四次的形态。

三条判据（裁定原文）：

1. **oracle 产物每族零 finding** —— 16 族没有一个 `violation`，`validity=valid`，效果分 = 100（自比即天花板）；
2. **null 产物 SR=0** —— 空产物落在 `unscorable_agent` / `malformed` 桶，`sr_bucket != "scorable"`，无 scorer 输出；
3. **filler 在 `s7-rob-02` 上触发 `silent_completion` 且 effect invalid** —— 欠定字段被填上，
   `underdetermined` 族命中、`validity=invalid`、effect 为 **null**（不是 0）。

日志侧：oracle 那一桩用它**真实的** access_log 切片（config_id=`oracle`）；null / filler 从没请求过网关，
切片因此是 `[]`（**可得且零条**，不是 `None`）—— 两者在校验器里语义不同（红队 rt18）。

用法：python ops/run_controls.py [--tasks s1-cor-01,...] [--out ops/reports/m6]

公开通道要三样（缺一样就是混通道跑批，见 `assert_channel_matches`）::

    GENEBENCH_CHANNEL=public python ops/run_controls.py \\
        --answer-root /data/shared/genebench/reference/tasks/public/v1.0-smoke-public \\
        --gateway-log /data/shared/genebench/logs/gateway_access_public.jsonl --out <落点>
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

import yaml

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from ops import report_io as _RIO   # noqa: E402

import genebench_config as _cfg                       # noqa: E402
from genetask import packager as P                    # noqa: E402
from scorer import score_run as SR                    # noqa: E402

#: 私有通道的默认落点。两个都能用 CLI 换（`--answer-root` / `--gateway-log`），
#: 默认值一个字节没动 —— 公开通道与私有**并列不覆盖**（卡 1.1-c）。
#: **从 `cfg` 现算**（2026-09-13 卡 P1，N-770 同族）：写死发布方绝对路径时，
#: `$GENEBENCH_ROOT` 在别处的机器上，这两个默认值指的是它没有的一台机器。
#: 发布方那台上 `cfg.GENEBENCH_ROOT == /data/shared/genebench`，所以值一字未动。
ANSWER_ROOT = _cfg.GENEBENCH_ROOT / "reference" / "tasks" / "v1.0-smoke"
GATEWAY_LOG = _cfg.GENEBENCH_ROOT / "logs" / "gateway_access.jsonl"
#: 公开通道那一套的落点。**一处定义，`--help` 从常量渲染** ——
#: 第二次分叉的代价红队 2026-09-07 实测过：help 里手写的题集根少了一层 `public/`，
#: 那个路径根本不存在，照着 `--help` 抄命令直接失败，而报告头里写的是对的。
PUBLIC_ANSWER_ROOT = _cfg.GENEBENCH_ROOT / "reference" / "tasks" / "public" / "v1.0-smoke-public"
PUBLIC_GATEWAY_LOG = _cfg.GENEBENCH_ROOT / "logs" / "gateway_access_public.jsonl"
#: M6-lite 的题（各阶段 cor-01 + 探针题）。S8 随 v1.0.8 进第二次 pass —— 它的三控在这里照跑。
M6_TASKS = ("s1-cor-01", "s2-cor-01", "s3-cor-01", "s4-cor-01", "s5-cor-01",
            "s6-cor-01", "s7-cor-01", "s7-rob-02", "s8-cor-01")
#: null / filler 两桩从没请求过网关，任何窗口切出来都是 `[]`（可得且零条）—— 用宽窗即可。
WIDE = ("2020-01-01T00:00:00+00:00", "2030-01-01T00:00:00+00:00")


def oracle_window(task_id: str) -> tuple[str, str]:
    """oracle 桩的时间窗 = 它**最近一次**真跑的那一段（`run_probe_mutations.log_block` 同一套）。

    宽窗会把当天更早几次 oracle 跑的条目一起算进来 —— S8 的越权核当场判 `overreach_count_mismatch`
    （自报 0 次 403，而累计切片里有好几次）。这正是卡 4.2 §7.2 说的第三维。
    """
    from ops.run_probe_mutations import log_block
    blk = log_block(task_id) or []
    if not blk:
        return WIDE
    return str(blk[0]["ts"]), str(blk[-1]["ts"])


def looks_public(answer_root: Path) -> bool:
    """这个题集根是不是公开通道那一套。

    判据取**路径本身**（`.../reference/tasks/public/…` 或名字以 `-public` 结尾），
    不 resolve 到磁盘 —— 路径不存在时也要判得出来（那正是最该拦的一次）。
    """
    p = Path(answer_root)
    return "public" in p.parts or p.name.endswith("-public")


def assert_channel_matches(answer_root: Path) -> None:
    """公开题集 + 非公开通道 = **混通道跑批**，拒绝启动。

    把三控指向公开通道要三样东西：`--answer-root`、`--gateway-log`、
    以及环境变量 `GENEBENCH_CHANNEL=public`。前两样是 CLI 参数，第三样不是 ——
    而 `cfg.channel()` 默认 `private`，于是 `cfg.snapshot_tables_dir()` 会返回**私有**表目录。
    只传前两样跑出来的是「题集与网关日志是公开的、底下读的表是私有的」：
    报告头照实打印 `通道：private`，三条判据照样全过，**数字看起来都对，只是来自另一份数据**
    （红队 2026-09-07；`ops/public_gateway.sh` 注释里说的同一类错，搬到了跑批侧）。
    在这之前没有任何一条判据会拦它，所以拦在这里。
    """
    ch = _cfg.channel()
    if looks_public(answer_root) and ch != "public":
        raise SystemExit(
            f"[红] 题集根 {answer_root} 是公开通道那一套，而当前通道是 {ch!r} —— 拒绝启动。\n"
            f"    混通道跑批的表现是「题集与网关日志是公开的、读的表是私有的」，"
            f"数字看起来都对，只是来自另一份数据。\n"
            f"    带上通道重跑：GENEBENCH_CHANNEL=public $PY ops/run_controls.py "
            f"--answer-root {answer_root} --gateway-log {PUBLIC_GATEWAY_LOG} --out <落点>")
    if ch == "public" and not looks_public(answer_root):
        print(f"[黄] GENEBENCH_CHANNEL=public，而题集根 {answer_root} 看着是私有那一套 —— "
              f"确认这是你要的（公开题集在 {PUBLIC_ANSWER_ROOT}）")


def reproduce_command(answer_root: Path, gateway_log: Path, out: Path) -> str:
    """报告顶部那条**可照抄**的完整命令 —— 由本次真实参数渲染，不是手写第二份。

    含两样 `--help` 之外的东西：`GENEBENCH_CHANNEL`（见 `assert_channel_matches`）
    与网关锁的包裹（红线 6：跑批与真跑串行）。
    """
    ch = _cfg.channel()
    wrap = ("ops/public_gateway.sh run -- " if ch == "public"
            else '$PY ops/gateway_lock.py --what "三控（私有通道）" -- ')
    return (f"cd $GB/repo && ulimit -n 8192 && {wrap}env GENEBENCH_CHANNEL={ch} "
            f"PYTHONDONTWRITEBYTECODE=1 $PY ops/run_controls.py "
            f"--answer-root {answer_root} --gateway-log {gateway_log} --out {out}")


def control_artifact(task_dir: Path, which: str) -> dict | None:
    task = yaml.safe_load((task_dir / "task.yaml").read_text(encoding="utf-8"))
    if which == "oracle":
        return SR.gold_artifact(task_dir)
    if which == "null":
        return SR.null_artifact(task_dir) or P.null_artifact(task, "empty")
    if which == "filler":
        return P.null_artifact(task, "default_fill")
    raise SystemExit(f"未知控制桩 {which}")


def score_control(task_dir: Path, which: str, scratch: Path, out_dir: Path,
                  *, gateway_log: "Path | None" = None) -> dict | None:
    art = control_artifact(task_dir, which)
    if art is None:
        return None
    task_id = task_dir.name
    cfg_id = str(art.get("config_id") or which)
    rd = scratch / f"{task_id}.{which}"
    (rd / "work").mkdir(parents=True, exist_ok=True)
    (rd / "log").mkdir(exist_ok=True)
    (rd / "work" / "artifact.json").write_text(json.dumps(art, ensure_ascii=False), encoding="utf-8")
    # payload 契约里的文件（values.parquet / panel.csv / ledger.parquet…）：oracle 桩把题目录 work/ 下的
    # 那一份拷进来 —— 它就是 oracle 的产出（tau/epsilon 判据要读）。null / filler 没有，那也是事实。
    if which == "oracle":
        for f in (task_dir / "work").glob("*"):
            if f.is_file():
                shutil.copy2(f, rd / "work" / f.name)
    lo, hi = oracle_window(task_id) if which == "oracle" else WIDE
    (rd / "run.json").write_text(json.dumps({
        "run_id": rd.name, "arm": "strict", "config_id": cfg_id, "exit_code": 0,
        "started_at": lo, "finished_at": hi, "elapsed_s": 0.0,
        "new_files": {}, "unexpected": [], "stdout_tail": "", "stderr_tail": ""}), encoding="utf-8")
    (rd / "inject.json").write_text(json.dumps({
        "run_id": rd.name, "task_id": task_id, "config_id": cfg_id, "arm": "strict",
        "seq": 1, "files": {}}), encoding="utf-8")
    r = SR.score_run(rd, task_dir, out_dir=out_dir,
                     gateway_log_path=Path(gateway_log or GATEWAY_LOG))
    rec = r["record"]
    rec["control"] = which
    return rec


def judge(rows: list[dict]) -> tuple[list[str], bool]:
    lines, ok = [], True
    for r in rows:
        c, t = r["control"], r["task_id"]
        if c == "oracle":
            bad = [k for k, v in (r["probe_states"] or {}).items() if v == "violation"]
            good = (r["validity"] == "valid" and not bad and not r["findings"])
            ok &= good
            lines.append(f"| {t} | oracle | {'✅' if good else '❌'} | validity={r['validity']}；"
                         f"violation 族 {bad or '无'}；finding {len(r['findings'])} 条 | "
                         f"effect={r['effect']}（{r['effect_withheld_reason'] or '出数'}） |")
        elif c == "null":
            good = r["sr_bucket"] != "scorable"
            ok &= good
            lines.append(f"| {t} | null | {'✅' if good else '❌'} | run_status={r['run_status']}，"
                         f"桶={r['sr_bucket']} → SR 记 0 | effect={r['effect']} |")
        else:
            hit = any("silent_completion" in f for f in r["findings"])
            fam = "underdetermined" in (r["gate_failed"] or [])
            if t == "s7-rob-02":
                good = hit and fam and r["validity"] == "invalid" and r["effect"] is None
                ok &= good
                mark = "✅" if good else "❌"
            else:
                mark = "·"          # 其余题的 filler 只作参考：它们的欠定集为空，静默补全无从谈起
            lines.append(f"| {t} | filler | {mark} | silent_completion={'命中' if hit else '未命中'}；"
                         f"gate_failed={r['gate_failed']}；validity={r['validity']} | effect={r['effect']} |")
    return lines, ok


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default=",".join(M6_TASKS))
    ap.add_argument("--out", default=str(_REPO / "ops" / "reports" / "m6"))
    ap.add_argument("--answer-root", default=str(ANSWER_ROOT),
                    help=f"题集目录（默认私有 {ANSWER_ROOT}）。公开通道传 {PUBLIC_ANSWER_ROOT}"
                         f" —— 并且**必须同时**设 GENEBENCH_CHANNEL=public，否则拒绝启动"
                         f"（只换题集不换通道 = 题集是公开的、读的表是私有的）")
    ap.add_argument("--gateway-log", default=str(GATEWAY_LOG),
                    help=f"网关 access_log（默认私有那份）。公开通道传 {PUBLIC_GATEWAY_LOG} —— "
                         "**两条通道的账本不能混**：拿私有日志去核公开那一跑，越权计数与读取集都会对不上")
    a = ap.parse_args(argv)
    out = Path(a.out)
    answer_root = Path(a.answer_root)
    gateway_log = Path(a.gateway_log)
    assert_channel_matches(answer_root)
    if not answer_root.is_dir():
        raise SystemExit(f"题集目录不存在：{answer_root} —— 先跑 ops/run_oracles.py 出 oracle 产物")
    (out / "controls").mkdir(parents=True, exist_ok=True)
    rows, missing = [], []
    with tempfile.TemporaryDirectory(prefix="gb-controls-") as tmp:
        for tid in [t.strip() for t in a.tasks.split(",") if t.strip()]:
            td = answer_root / tid
            if not (td / "task.yaml").is_file():
                missing.append(f"{tid}: 没有题目录")
                continue
            for which in ("oracle", "null", "filler"):
                try:
                    rec = score_control(td, which, Path(tmp), out / "controls",
                                        gateway_log=gateway_log)
                except Exception as e:                       # noqa: BLE001
                    missing.append(f"{tid}/{which}: {type(e).__name__}: {e}")
                    continue
                if rec is None:
                    missing.append(f"{tid}/{which}: 没有这一桩的产物（oracle 未跑？）")
                    continue
                rows.append(rec)
    lines, ok = judge(rows)
    body = ["# 三控走完整评分器（M6 产出 ②）", "",
            "> 入口是 `scorer.score_run.score_run` —— 与真 run 同一条路径（采集 → 分类 → 闸门三态 → L3 → "
            "scorer 输出 schema → 效果分）。旁路直接调校验器**不算**走完整评分器。", "",
            f"> 题集根：`{answer_root}`；网关日志：`{gateway_log}`；通道：`{_cfg.channel()}`。", "",
            "复现这一跑（**照抄整条**；`GB=/data/shared/genebench`、`PY=$GB/env/bin/python`）：", "",
            "```bash", reproduce_command(answer_root, gateway_log, out), "```", "",
            "> 三样缺一不可：`--answer-root`、`--gateway-log`、**`GENEBENCH_CHANNEL`**。"
            "只换前两样而不换通道，跑出来的是「题集与日志是公开的、读的表是私有的」——"
            "报告头会照实打印通道，但数字看起来都对。本脚本对这一种组合**拒绝启动**。", "",
            "| 题 | 桩 | 判定 | 依据 | 效果分 |", "| --- | --- | --- | --- | --- |", *lines, "",
            f"**三条判据{'全过' if ok else '**未全过**'}**："
            "① oracle 每族零 finding；② null 产物 SR 记 0；③ filler 在 s7-rob-02 上命中 silent_completion 且 effect 为 null。"]
    if missing:
        body += ["", "## 没跑成的桩", ""] + [f"- {m}" for m in missing]
    (out / "controls.md").write_text("\n".join(body) + "\n", encoding="utf-8")
    (out / "controls.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    _RIO.secure_tree(out)
    print("\n".join(body))
    return 0 if (ok and not missing) else 1


if __name__ == "__main__":
    raise SystemExit(main())
