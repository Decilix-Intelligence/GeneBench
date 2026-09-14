#!/usr/bin/env python3
"""在 f01 上跑探针字段的判别力筛查（四实现 × 逐可行值），出证据表。

**这是出题的唯一阻塞**（签字裁定 2026-09-03）：七个阶段的探针字段还没有 E9d2 要的实测证据，
`probe_materiality_verified` 因此为 false，八道探针题只许 draft。

判据四条（`genetask/materiality.py` 与 `genetask/schema.py`）：
  E9b  materiality 静态前提（FIELD_MATERIAL_WHEN）
  E9d  无规范化领域默认（CANONICAL_DEFAULT_FIELDS）
  E9d2 独立实现实测会分叉（本脚本产出的就是这条的证据）
  E9d4 可行值不得与固定槽内容重叠

跑法：
    PY=/data/shared/genebench/env/bin/python
    $PY ops/run_materiality_screen.py                                  # 全部八道探针题（私有通道）
    $PY ops/run_materiality_screen.py s6-rob-02                        # 单题
    $PY ops/run_materiality_screen.py S6                               # 单阶段（跑序：S3 S4 S5 S6 先）
    $PY ops/run_materiality_screen.py --channel public \
        --out ops/reports/public/materiality_screen                    # 公开通道（卡 1.1-c）
产出：`<--out>.json`（机器读）+ 同名 `.md`（人读），默认 `ops/reports/materiality_screen`。
锁的翻绿条件：每道探针题的 verdict == material，且证据写进 `genetask/schema.py::DIVERGENCE_EVIDENCE`。

**实现从哪来（2026-09-07 修）**：B 侧三份独立实现是**脚本不是库** ——
`snapshots/<通道>/epsilon/impl_v2_b{1,2,3}.py`，由 `ops/screen_runner.py` 复制到沙箱、
子进程跑、读它自己写的 JSON。2026-09-03 真跑出 S7 证据的那次走的就是这条路
（`ops/reports/materiality_s7_sell_rule.json` 的 `harness` 字段）。
下面的 `IMPL_CANDIDATES` / `_resolve()` 找的是**模块**入口，它一次也没找到过 B1..B3；
保留它是当取证用：把**实际可见的候选**记进报告的 `entrypoint_forensics`，
而不是让「跑不起来」成为一句没有下文的话。**不要为了让它跑通而伪造 runner。**

**能screen 的字段只有两个**（`FROZEN_SCREENS`）：`rebalance_frequency`（三份实现的 argv，
不打任何补丁）与 `sell_rule`（P-SELL 开关，Gate 1 验中性）。其余六个探针字段这套
harness **结构上量不到**（理由逐条写在 `OUT_OF_REACH`），一律记 `inconclusive` ——
「量不到」不是「没差别」。
"""
from __future__ import annotations

import argparse
import contextlib
import importlib
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from genetask import materiality as MAT          # noqa: E402
from genetask import packager as P               # noqa: E402
from genetask import schema as S                 # noqa: E402

PARAMS = REPO / "genetask" / "params" / "v1.0-smoke40.yaml"
REPORT = REPO / "ops" / "reports" / "materiality_screen"

#: 四份实现的候选入口。A = 参考实现；B1..B3 = 卡 2.2b 的三份独立实现。
IMPL_CANDIDATES: dict[str, tuple[str, ...]] = {
    "A":  ("reference.backtest",),
    "B1": ("reference.backtest_b1", "reference.impl_b1", "reference.b1"),
    "B2": ("reference.backtest_b2", "reference.impl_b2", "reference.b2"),
    "B3": ("reference.backtest_b3", "reference.impl_b3", "reference.b3"),
}
RUN_FN_CANDIDATES = ("run_backtest", "backtest", "run", "evaluate", "main")


def _resolve() -> tuple[dict[str, object], list[str]]:
    """找到四份实现的可调用入口；找不到的记进 missing，并把该模块的公开函数打印出来备查。"""
    got, missing = {}, []
    for impl, mods in IMPL_CANDIDATES.items():
        fn = None
        for m in mods:
            try:
                mod = importlib.import_module(m)
            except Exception:                                   # noqa: BLE001
                continue
            for name in RUN_FN_CANDIDATES:
                if callable(getattr(mod, name, None)):
                    fn = getattr(mod, name)
                    print(f"[接线] {impl} -> {m}.{name}")
                    break
            if fn is None:
                pub = [n for n in dir(mod) if not n.startswith("_") and callable(getattr(mod, n))]
                print(f"[接线] {impl} 找到模块 {m}，但没有已知入口名；公开可调用：{pub[:20]}")
            if fn:
                break
        (got.__setitem__(impl, fn) if fn else missing.append(impl))
    return got, missing


def _band():
    """ε 带判据。用 reference.epsilon_dual 的公开入口；找不到就报出它有什么，不要退化成常数容差。"""
    import reference.epsilon_dual as e
    for name in ("outside_band", "is_outside_band", "beyond_epsilon", "compare"):
        if callable(getattr(e, name, None)):
            print(f"[接线] ε 带 -> epsilon_dual.{name}")
            return getattr(e, name)
    pub = [n for n in dir(e) if not n.startswith("_") and callable(getattr(e, n))]
    raise SystemExit(f"[停] epsilon_dual 没有已知的带判据入口；公开可调用：{pub}\n"
                     f"    请把正确的入口名补进本脚本的候选表，不要用常数容差代替。")


# ================================================================== 冻结实现路线
#
# **B 侧三份独立实现是脚本不是库。** 它们的接口是「argv 给频率 + 环境变量给开关 +
# 自己写一个 out_v2_b*_<freq>.json」，由 `ops/screen_runner.py` 的 `Sandbox` 驱动。
# 2026-09-03 的 S7 screen 就是这么跑的，本卡把 S6 也接上去。
#
# **能screen 的字段 = 三份实现真的会因它改变行为的字段。** 只有两个：
#
# * `rebalance_frequency` —— **不需要任何补丁**：它就是三份实现的 argv（daily/weekly/monthly），
#   快照里 `out_v2_b*_{daily,weekly,monthly}.json` 九份产物就是它的三个取值；
# * `sell_rule` —— 需要 `P-SELL` 那个**只加开关不改算法**的补丁（Gate 1 逐指标验中性）。
#
# 其余六个探针字段（`data_version` / `adjust` / `eval_frequency` / `holding_periods` /
# `signal_frequency` / `slippage_reference_price`）**量不到**：这三份实现是 S7 的回测引擎，
# 它们的输入是一张定死的 csi300 面板，里头根本没有「数据版本」「求值频率」这些概念。
# 这不是「没差别」，是**这套 harness 测不了** —— 逐条记 `inconclusive` 并写明理由，
# 不许把「测不了」读成「不 material」（本脚本模块说明第 131 行的原话）。

#: 字段 → 怎么让三份冻结实现在这个字段上分叉。
#: `dispatch(value, declared) -> (freq, env)`：freq 进 argv，env 进子进程环境。
FROZEN_SCREENS: dict[str, dict] = {
    "rebalance_frequency": {
        "patch": None,
        "band_tier": "daily",
        "dispatch": lambda v, d: (str(v), {}),
        "note": "频率就是三份实现的 argv —— **不打任何补丁**，因此没有「补丁改了算法」这种可能，"
                "Gate 1（补丁中性）在这个字段上不适用，只跑 Gate 0（沙箱副本复现快照产物）。",
    },
    "sell_rule": {
        "patch": "P-SELL",
        "band_tier": "daily",
        "dispatch": lambda v, d: (str(d.get("rebalance_frequency") or "daily"),
                                  {"GB_SELL_RULE": str(v)}),
        "note": "两种读法由 P-SELL 开关切换（只加开关不改算法，Gate 1 逐指标验中性）；"
                "频率取本题声明的 rebalance_frequency。",
    },
}

#: 这套 harness 结构上量不到的字段，逐条写明**为什么**（不是「跑不起来」）。
OUT_OF_REACH: dict[str, str] = {
    "data_version": "三份冻结实现读的是一张定死的 csi300 面板（bt_input_csi300_v2.parquet），"
                    "没有「数据版本」这个入口；换版本等于换输入面板，那是另一份标定不是一个开关。",
    "adjust": "复权口径在面板生成时就已经定死（post），三份实现拿到的是复权后的价；"
              "它们没有「换一种复权」的入口。",
    "eval_frequency": "S3 是因子求值，三份实现是 S7 的回测引擎 —— 它们不求值因子，只吃现成的信号面板。",
    "holding_periods": "S4 是 IC 分布，三份实现不出 IC；S4 的判据是 IC 族 ε（N-117），不是回测指标 ε。",
    "signal_frequency": "S5 是信号面，三份实现吃的是已经算好的信号，不重采样它。",
    "slippage_reference_price": "S8 是撮合模拟，三份实现按 close 成交、没有滑点参考价这个入口；"
                                "它换入之后要重做一次面板与标定（题面自己也标着「等 slippage_reference_price 换入后一并跑」）。",
}


def _channel_eps_dir(channel: str | None) -> Path:
    import genebench_config as _cfg
    return _cfg.epsilon_dir(channel)


@contextlib.contextmanager
def frozen_impl_paths(eps_dir: Path):
    """把 `ops/screen_runner` 与 `ops/screen_band` 的落点临时指到本通道的 ε 目录。

    **为什么是覆盖而不是参数化**：那两个文件不在本卡授权的路径清单里（并发施工规则 C）。
    覆盖表的形态与卡 1.1-b 的 `ops/run_public_chain.channel_overrides()` 相同，
    局限也相同：它兜得住「覆盖表漏项」，兜不住「有人绕过覆盖表直接 import screen_runner」。
    v1.1 把两个模块参数化之后删掉这里（已登记）。

    还原是硬要求：留一个指向公开根的模块常量下去，表现是「公开 screen 读了私有快照」——
    数字照出，两边都不报错。
    """
    from ops import screen_band as sb
    from ops import screen_runner as sr

    saved = [(sr, "SNAP", sr.SNAP), (sr, "PANEL", sr.PANEL), (sb, "CAL", sb.CAL)]
    saved += [(sr.SCRIPTS[k], "src", sr.SCRIPTS[k]["src"]) for k in sr.SCRIPTS]
    try:
        sr.SNAP = Path(eps_dir)
        sr.PANEL = Path(eps_dir) / "bt_input_csi300_v2.parquet"
        for k, spec in sr.SCRIPTS.items():
            spec["src"] = Path(eps_dir) / Path(spec["src"]).name
        sb.CAL = Path(eps_dir)
        missing = [str(s["src"]) for s in sr.SCRIPTS.values() if not Path(s["src"]).is_file()]
        if not sr.PANEL.is_file():
            missing.append(str(sr.PANEL))
        if missing:
            raise SystemExit("[停] 这条通道的 ε 目录里缺件，screen 跑不了：\n  " + "\n  ".join(missing))
        yield sr, sb
    finally:
        for obj, attr, old in reversed(saved):
            if isinstance(obj, dict):
                obj[attr] = old
            else:
                setattr(obj, attr, old)


def _band_for(tier: str, sb) -> tuple:
    """ε 带判据 + 一个「被跳过的指标」清单。

    `screen_band.Band` 在指标不在带表里、或带是 `no_implementation_freedom` 之外的
    非数值状态时抛 `BandUndecided`。**抛出来不能当成「没超带」悄悄咽掉**，
    也不能让整题炸 —— 这里接住、记名字、按「没超带」处理（**保守方向**：
    少数一条超带只会让结论更难判成 material，不会凭空造出 material）。
    """
    band = sb.Band({"kind": "epsilon", "tier": tier})
    skipped: dict[str, str] = {}

    def outside(metric, a, b) -> bool:
        try:
            return bool(band.outside(metric, a, b))
        except sb.BandUndecided as e:
            skipped.setdefault(metric, str(e))
            return False

    return outside, skipped, band


def screen_field_frozen(task: dict, field: str, root: Path, sr, sb) -> dict:
    """在三份冻结实现上 screen 一个字段。返回 `materiality_report` 的产物 + harness 记账。"""
    spec = FROZEN_SCREENS[field]
    values = MAT.feasible_values(field)
    impls = ("B1", "B2", "B3")
    box = sr.Sandbox(root, patch=spec["patch"])
    for impl in impls:
        box.prepare(impl)
    outside, skipped, band = _band_for(spec["band_tier"], sb)
    cache: dict[tuple, dict] = {}

    def run(impl: str, f: str, value):
        key = (impl, MAT._k(value))
        if key not in cache:
            freq, env = spec["dispatch"](value, task["declared"])
            cache[key] = sr.Sandbox.metrics(box.run(impl, freq, env))
        return cache[key]

    rep = MAT.materiality_report(task, run, outside, field=field, implementations=impls)
    rep["diff_summary"] = diff_summary(rep, band)
    rep["metrics_by_value"] = {f"{impl}|{vk}": m for (impl, vk), m in cache.items()}
    box.dump(root / "MANIFEST.json")
    rep["harness"] = {"module": "ops/screen_runner.py", "patch": spec["patch"],
                      "implementations": list(impls), "band_tier": spec["band_tier"],
                      "note": spec["note"], "sandbox": str(root),
                      "impls": box.manifest["impls"], "n_runs": len(box.manifest["runs"]),
                      "skipped_metrics": skipped}
    return rep


def diff_summary(rep: dict, band) -> dict:
    """逐实现 / 逐指标把**全部**超带条目数出来，并记下实测差与 ε 本身。

    落盘的 `diffs` 是截断过的（前 40 条）；证据条目要写的数必须从**没截断**的那份数出来。
    每一项同时记 `epsilon` 与 `kind`（绝对/相对）—— 只写「超带」而不写「带是多少」，
    读的人无从判断这是「差了一个数量级」还是「刚压线」。
    """
    from reference import epsilon_dual as ED

    by_impl: dict[str, int] = {}
    by_metric: dict[str, dict] = {}
    for d in rep.get("diffs", ()):
        by_impl[d["impl"]] = by_impl.get(d["impl"], 0) + 1
        a, b = d["values"]
        kind = ED.tolerance_kind(d["metric"])
        obs = abs(a - b) if kind == "absolute" else (
            abs(a - b) / max(abs(a), abs(b)) if max(abs(a), abs(b)) > 0 else 0.0)
        rec = by_metric.setdefault(d["metric"], {
            "n": 0, "kind": kind,
            "epsilon": (band.table.get(d["metric"]) or {}).get("epsilon"),
            "observed_max": 0.0, "observed_min": None, "impls": []})
        rec["n"] += 1
        rec["observed_max"] = max(rec["observed_max"], obs)
        rec["observed_min"] = obs if rec["observed_min"] is None else min(rec["observed_min"], obs)
        if d["impl"] not in rec["impls"]:
            rec["impls"].append(d["impl"])
    cross: dict[str, int] = {}
    for c in rep.get("cross_impl_divergence", ()):
        cross[c["metric"]] = cross.get(c["metric"], 0) + 1
    return {"n_diffs_total": len(rep.get("diffs", ())), "by_impl": by_impl,
            "by_metric": by_metric, "cross_by_metric": cross,
            "n_cross_total": len(rep.get("cross_impl_divergence", ()))}


def _entrypoint_forensics() -> dict:
    """「模块入口」那条路线的取证：把实际可见的候选记下来，而不是一句「跑不起来」。"""
    got, missing = _resolve()
    return {"resolved": sorted(got), "missing": missing,
            "note": "IMPL_CANDIDATES 找的是 reference.backtest_b* 这样的**模块**；"
                    "B 侧三份独立实现是**脚本**（snapshots/<通道>/epsilon/impl_v2_b*.py），"
                    "由 ops/screen_runner.py 驱动。本轮走的是后者。"}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="探针字段判别力筛查（冻结实现 × 逐可行值）")
    ap.add_argument("only", nargs="?", default="",
                    help="题号（s6-rob-02）或阶段（S6）；不给就跑全部八道探针题")
    ap.add_argument("--channel", default="",
                    help="private / public。**只在 main 里设进环境**（import 期设会把任何 "
                         "import 本模块的进程整个翻到另一条通道，卡 1.1-b 踩过）")
    ap.add_argument("--epsilon-dir", default="",
                    help="冻结实现与 ε 带的目录；默认按通道取 cfg.epsilon_dir()")
    ap.add_argument("--out", default=str(REPORT), help="报告落点（不带后缀，出 .json 与 .md）")
    ap.add_argument("--sandbox", default="",
                    help="沙箱根；默认 $GB/scratch/1.1c/screen/<通道>")
    ap.add_argument("--skip-gate0", action="store_true",
                    help="跳过 Gate 0（沙箱副本复现快照产物）。**只在调试时用** —— "
                         "不跑 Gate 0 就没有「harness 没改行为」这条证据")
    a = ap.parse_args(argv[1:])
    if a.channel:
        os.environ["GENEBENCH_CHANNEL"] = a.channel
    import genebench_config as _cfg
    channel = _cfg.channel()
    eps_dir = Path(a.epsilon_dir) if a.epsilon_dir else _channel_eps_dir(channel)
    root = Path(a.sandbox) if a.sandbox else \
        Path("/data/shared/genebench/scratch/1.1c/screen") / channel
    os.umask(0o077)
    root.mkdir(parents=True, exist_ok=True)
    report = Path(a.out)

    # 跑序（签字裁定 2026-09-03）：先跑 S3/S4/S5/S6 —— 这四个阶段有基线阶梯，ε 带可用；
    # S7 的 sell_rule 已有实测证据（2026-09-03 screen）；S8 等 slippage_reference_price 换入后一并跑。
    STAGE_ORDER = ("S3", "S4", "S5", "S6", "S1", "S2", "S7", "S8")
    only = a.only
    rows = [r for r in P.load_params(PARAMS) if r.get("underdetermined")]
    if only in STAGE_ORDER:
        rows = [r for r in rows if r["stage"] == only]
    elif only:
        rows = [r for r in rows if r["task_id"] == only]
    if not rows:
        raise SystemExit(f"没有匹配 {only!r} 的探针题")
    rows.sort(key=lambda r: STAGE_ORDER.index(r["stage"]))
    caps = json.loads((REPO / S.CAPABILITIES_FILE).read_text())
    caps = {k: v for k, v in caps.items() if isinstance(v, bool)}

    out: dict[str, dict] = {}
    gates: dict[str, object] = {}
    with frozen_impl_paths(eps_dir) as (sr, sb):
        need_frozen = any((r["underdetermined"] or [None])[0] in FROZEN_SCREENS for r in rows)
        if need_frozen and not a.skip_gate0:
            # Gate 0：**未打补丁**的沙箱副本必须复现这条通道快照里的产物 —— harness 自证不改行为。
            bad = sr.gate_baseline(root)
            gates["baseline_reproduces"] = not bad
            gates["baseline_detail"] = bad
            if bad:
                print("[停] Gate 0 未过：沙箱副本没能复现快照产物 —— "
                      "在这之前跑出来的任何分叉都可能是 harness 的，不是实现的。\n  "
                      + "\n  ".join(bad))
                return 2
            print("[Gate 0] 沙箱副本逐指标复现快照产物 ✅")
        need_patch = sorted({FROZEN_SCREENS[(r["underdetermined"] or [None])[0]]["patch"]
                             for r in rows
                             if (r["underdetermined"] or [None])[0] in FROZEN_SCREENS
                             and FROZEN_SCREENS[(r["underdetermined"] or [None])[0]]["patch"]})
        for patch in need_patch:
            bad = sr.gate_patch_neutral(root, patch)
            gates[f"patch_neutral:{patch}"] = not bad
            gates[f"patch_neutral_detail:{patch}"] = bad
            if bad:
                print(f"[停] Gate 1（{patch}）未过：开关取原读法时结果与快照不同 —— 补丁动了算法。\n  "
                      + "\n  ".join(bad))
                return 2
            print(f"[Gate 1] {patch} 补丁中性 ✅")

        for r in rows:
            task = P.build_task(r, capabilities=caps).task
            tid, field = task["task_id"], (task["underdetermined"] or [None])[0]
            cond = S.evidence_condition(field, task["declared"])
            if field in FROZEN_SCREENS:
                rep = screen_field_frozen(task, field, root / tid, sr, sb)
            else:
                rep = {"field": field, "verdict": "inconclusive", "values": [],
                       "diffs": [], "by_impl": {}, "cross_impl_divergence": [],
                       "reason": "这套 harness 结构上量不到这个字段：" + OUT_OF_REACH.get(field, "（未登记理由）"),
                       "harness": {"module": None, "out_of_reach": True}}
            out[tid] = {"stage": task["stage"], "probe_field": field,
                        "evidence_condition": [list(kv) for kv in (cond or ())],
                        "verdict": rep["verdict"], "reason": rep["reason"],
                        "by_impl": rep["by_impl"], "diffs": rep["diffs"][:40],
                        "cross_impl_divergence": rep["cross_impl_divergence"][:40],
                        "n_diffs": len(rep["diffs"]), "n_cross": len(rep["cross_impl_divergence"]),
                        "diff_summary": rep.get("diff_summary"),
                        "metrics_by_value": rep.get("metrics_by_value"),
                        "values": rep.get("values", []), "harness": rep.get("harness")}
            print(f"{tid:12} {field:26} {rep['verdict']:12} {rep['reason'][:100]}")

    doc = {"channel": channel, "epsilon_dir": str(eps_dir), "sandbox": str(root),
           "gates": gates, "entrypoint_forensics": _entrypoint_forensics(), "tasks": out}
    report.parent.mkdir(parents=True, exist_ok=True)
    report.with_suffix(".json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    md = [f"# 探针字段判别力筛查（通道 `{channel}`）", "",
          f"> 冻结实现与 ε 带取自 `{eps_dir}`；沙箱 `{root}`。",
          f"> 闸门：{gates or '（未跑）'}", "",
          "| 题 | 阶段 | 探针字段 | 条件 | 结论 | 逐实现 | 组内分叉 | 跨实现分叉 |",
          "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for tid, v in out.items():
        cond = "、".join(f"`{k}={x}`" for k, x in v["evidence_condition"]) or "（无条件）"
        md.append(f"| {tid} | {v['stage']} | `{v['probe_field']}` | {cond} | **{v['verdict']}** | "
                  f"{v['by_impl'] or '—'} | {v['n_diffs']} 处 | {v['n_cross']} 处 |")
    md += ["", "## 逐题理由", ""]
    for tid, v in out.items():
        md.append(f"- **{tid}** / `{v['probe_field']}`：{v['reason']}")
        s = v.get("diff_summary") or {}
        if s.get("by_metric"):
            md.append(f"  - 逐实现超带条数：{s['by_impl']}（共 {s['n_diffs_total']} 处；"
                      f"跨实现分叉 {s['n_cross_total']} 处）")
            def _eps(r) -> str:
                # ε 为 None = 该指标在这条通道上标了 `no_implementation_freedom`
                # （三份实现完全同值）。`screen_band.Band` 对这一档的读法是**要求精确相等**
                # （那一行标着【待签字 §7-①】）—— 报告里必须把这句话写出来，
                # 否则读的人会以为它和别的指标一样是「超出某条带」。
                return ("要求精确相等（ε 未标定：no_implementation_freedom）"
                        if r["epsilon"] is None else f"ε={r['epsilon']:.4g}")

            md.append("  - 逐指标（实测差 / ε）：" + "；".join(
                f"`{m}` {r['observed_min']:.4g}–{r['observed_max']:.4g} vs "
                f"{_eps(r)}（{r['kind'][:3]}，{r['n']} 处）"
                for m, r in sorted(s["by_metric"].items())))
        h = v.get("harness") or {}
        if h.get("skipped_metrics"):
            md.append(f"  - 没有带、因而未参与比较的指标：{sorted(h['skipped_metrics'])}")
        if h.get("note"):
            md.append(f"  - harness：{h['note']}")
    md += ["", "verdict 为 material 的题，把证据条目写进 `genetask/schema.py::DIVERGENCE_EVIDENCE`",
           "（本卡不改冻结根，条目原样落在 `ops/reports/public/materiality_evidence.json`）。",
           "**任何一题 inconclusive 都不许翻锁 —— 「跑不起来」「量不到」都不是「没差别」。**"]
    report.with_suffix(".md").write_text("\n".join(md) + "\n", encoding="utf-8")
    for p in (report.with_suffix(".json"), report.with_suffix(".md")):
        p.chmod(0o600)
    print(f"\n写出 {report.with_suffix('.json')} 与 {report.with_suffix('.md')}")
    mat = [t for t, v in out.items() if v["verdict"] == "material"]
    print(f"material {len(mat)}/{len(out)}：{mat}")
    return 0 if all(v["verdict"] == "material" for v in out.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
