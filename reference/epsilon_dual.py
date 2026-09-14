# -*- coding: utf-8 -*-
"""卡 2.2b：ε = **两份独立实现**同一份声明的自然分歧 × 1.5。

    cd $REPO && $GENEBENCH_ROOT/env/bin/python -m reference.epsilon_dual

**为什么不是跨库版本**（上一轮实测，见 `design_notes.md` D-05 第二个实例）：
跨 4 个 numpy/pandas 组合的最大相对极差只有 **8.53e-14**，全是 float64 舍入。
把它写成 ε 等于要求**比特级相等**。

**为什么是双实现**：ε 的用途是判 agent 交付的回测结果是否落在 gold 的 ε 带内，
而 **agent 不会用我们的 qlib 代码、会自己实现撮合**。
所以 ε 必须覆盖「两份独立实现同一份声明会差多少」——**环境噪声与这件事无关**。
这也让 τ 与 ε 方法论对齐：都是两个独立实现之间的自然分歧，
一个在**因子值**上（逐日截面秩相关），一个在**回测指标**上。

**独立性是这张卡唯一真正的风险**（见 `ops/specs/backtest_contract.md`）：
实现 B 只依据声明写，不读 qlib 的 `exchange` / `executor` / `strategy` 源码，
且输入是一份**纯 parquet**（不需要 qlib），独立性因此是结构性的而不是自觉的。

三条约束，**写在代码里而不只在文档里**：

1. 某指标 A 与 B 完全相同 → 标 ``no_implementation_freedom``，
   **不得用其他指标的 ε 代填**；
2. 每个指标的 ε 必须**显著高于**浮点噪声地板（:data:`NOISE_FLOOR`），低于则标 ``invalid`` 并停下；
3. 相对差 > :data:`IMPLAUSIBLE_REL_DIFF` 的，**不写成 ε**，标 ``implausible`` 并停下 ——
   那多半是声明没写清或有一方实现错了，而一个过宽的 ε 会让 S7 失去判别力。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

import genebench_config as cfg

#: **通道相关的模块属性**（卡 1.1-b，PEP 562 ``__getattr__``）：不设
#: ``GENEBENCH_CHANNEL`` 时逐字等于既有常量，设成 ``public`` 时落到
#: ``snapshots/public_v1/epsilon/``。做成属性而不是改成函数，是为了让
#: 下游（``reference/calibration.py``、``ops/screen_band.py``、验收脚本）
#: 一个字都不用改 —— 逐个去改的话，漏掉一处的表现是「公开链读了私有 ε」。

def eps_dir(ch: "str | None" = None) -> Path:
    """该通道的 ε 目录。"""
    return cfg.epsilon_dir(ch)


def out_path(ch: "str | None" = None) -> Path:
    """该通道的 ``epsilon_dual.json`` 落点。"""
    return eps_dir(ch) / "epsilon_dual.json"


def __getattr__(name: str):
    if name == "EPS_DIR":
        return eps_dir()
    if name == "OUT":
        return out_path()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

#: ε = 相对差 × 这个系数。
MULTIPLIER: float = 1.5

#: 浮点噪声地板 —— 上一轮跨库版本实测出来的最大相对极差。
#: 低于它的"分歧"量到的是舍入，不是实现自由度。
NOISE_FLOOR: float = 1e-13

#: 高于这个相对差就不像实现自由度了。签字建议值 5%。
IMPLAUSIBLE_REL_DIFF: float = 0.05

#: 至少要覆盖这些指标（签字要求）。
REQUIRED_METRICS: tuple[str, ...] = (
    "sharpe_net", "max_drawdown_net", "ann_return_net",
    "turnover_one_way_mean", "turnover_two_way_mean", "win_rate_net",
)

# --------------------------------------------------------------- 度量类型规则
#
# **相对容差施加在「构造上可能趋零」的量上是没有意义的。**
#
# 实测把这一条逼出来了：`ann_return_net` 的相对差高达 90.85%，
# 但那不是「实现差了 90%」—— 净收益 = 毛收益(≈0.057) − 成本拖累(≈0.05)，
# 是**两个大数的小差**，相对误差被结构性放大。
# 同一批实现在 `ann_vol_net` 上只差 1.53%。
#
# 规则：
#
# * **尺度无关且不趋零** → **相对容差**（Sharpe、MDD、换手、波动、胜率、总成本…）
# * **构造上可能趋零** → **绝对容差**，ε = |A−B| 的绝对差 × 1.5，**单位是收益点**
#
#: 构造上可能趋零 —— 必须用绝对容差。
ZERO_APPROACHING: frozenset[str] = frozenset({
    "ann_return_net",     # = 毛收益 − 成本拖累，两个大数的小差
    "alpha",              # 定义上就是「超出基准的部分」，零是它的中心
    "excess_return",      # 同上
    "calmar_net",         # 分子是净收益，直接继承它的趋零性
    "sortino_net_mar0",   # 分子是均值收益，同上
})

#: 绝对容差的单位说明（进产物，供签字人读）。
ABSOLUTE_UNIT: str = "收益点（与该指标同单位的绝对差）"


def tolerance_kind(metric: str) -> str:
    """该指标该用哪种容差。**评分器必须调这个，不许自己判断。**"""
    return "absolute" if metric in ZERO_APPROACHING else "relative"


def assert_tolerance_kind(metric: str, kind: str) -> None:
    """配置校验：给趋零指标配相对容差 → **直接抛错**。

    这条不是提示而是硬拦 —— 相对容差施加在趋零量上会得到一个
    「看起来很大、其实没有意义」的数（实测 `ann_return_net` 90.85%），
    照着它定阈值会让 S7 对净收益近乎无约束。
    """
    want = tolerance_kind(metric)
    if kind != want:
        raise ValueError(
            f"{metric} 必须用 {want} 容差，配置成了 {kind}。"
            + (f"该指标构造上可能趋零（{sorted(ZERO_APPROACHING)}），"
               f"相对容差在趋零量上没有意义。" if want == "absolute" else
               "该指标尺度无关且不趋零，用绝对容差会随组合规模漂移。")
        )

__all__ = ["compare", "MULTIPLIER", "NOISE_FLOOR", "IMPLAUSIBLE_REL_DIFF", "OUT",
           "EPS_DIR", "eps_dir", "out_path"]


def _rel(a: float, b: float) -> float:
    d = abs(a - b)
    scale = max(abs(a), abs(b))
    return d / scale if scale else (0.0 if d == 0 else float("inf"))


def compare_pairwise(impls: "dict[str, Path]", *, label: str = "",
                     verbose: bool = True, out: "Path | None" = None) -> dict[str, Any]:
    """**全对**最大分歧 —— N 份独立实现两两比，取最大。

    比「A vs B」更干净：A（qlib）是一份**特定**实现，带自己的口径怪癖
    （实测 `total_cost` 与三份 B 系统性差 18%，而三份 B 互相只差 0.067%）。
    ε 要量的是「两份诚实实现的自然分歧」，用一组独立实现的**全对最大差**更贴近这个定义。
    """
    import itertools

    ms = {}
    for name, path in impls.items():
        d = json.loads(path.read_text(encoding="utf-8"))
        ms[name] = d["metrics"] if "metrics" in d else d
    names = sorted(set.intersection(*[set(v) for v in ms.values()]))
    per: dict[str, Any] = {}
    for m in names:
        vals = {n: ms[n].get(m) for n in ms}
        if not all(isinstance(v, (int, float)) for v in vals.values()):
            continue
        if m in ("n_days",):
            continue
        kind = tolerance_kind(m)
        pairs = []
        for a, b in itertools.combinations(sorted(ms), 2):
            x, y = float(vals[a]), float(vals[b])
            pairs.append({"pair": f"{a}|{b}", "rel": _rel(x, y), "abs": abs(x - y)})
        worst = max(pairs, key=lambda r: r["abs" if kind == "absolute" else "rel"])
        rel, ab = worst["rel"], worst["abs"]
        diff = ab if kind == "absolute" else rel
        rec: dict[str, Any] = {
            "values": {k: float(v) for k, v in vals.items()},
            "max_rel_diff": rel, "max_abs_diff": ab, "worst_pair": worst["pair"],
            "tolerance_kind": kind,
            "unit": ABSOLUTE_UNIT if kind == "absolute" else "相对差",
        }
        if diff == 0.0:
            rec["status"] = "no_implementation_freedom"
            rec["epsilon"] = None
            rec["note"] = ("全部实现完全相同 —— 该指标在当前声明下**没有实现自由度**。"
                           "**不得用其他指标的 ε 代填**。")
        elif kind == "relative" and rel < NOISE_FLOOR:
            rec["status"] = "invalid_below_noise_floor"
            rec["epsilon"] = None
        elif kind == "relative" and rel > IMPLAUSIBLE_REL_DIFF:
            rec["status"] = "implausible_stop_and_report"
            rec["epsilon"] = None
            rec["note"] = (f"相对差 {rel:.2%} 超过 {IMPLAUSIBLE_REL_DIFF:.0%} —— "
                           f"不像实现自由度，多半是**声明没写清**。停下汇报，不写成 ε。")
        else:
            rec["status"] = "calibrated"
            rec["epsilon"] = diff * MULTIPLIER
        per[m] = rec

    bad = [m for m, r in per.items() if r["status"] == "implausible_stop_and_report"]
    payload = {
        "card": "2.2b", "method": "pairwise_independent_implementations",
        "label": label, "n_implementations": len(ms),
        "implementations": {k: str(v) for k, v in impls.items()},
        "multiplier": MULTIPLIER, "noise_floor": NOISE_FLOOR,
        "implausible_threshold": IMPLAUSIBLE_REL_DIFF,
        "epsilon_by_metric": per,
        "calibrated": [m for m, r in per.items() if r["status"] == "calibrated"],
        "implausible": bad,
        "no_freedom": [m for m, r in per.items() if r["status"] == "no_implementation_freedom"],
        "usable": not bad,
    }
    dest = out or (eps_dir() / f"epsilon_dual_{label or 'pairwise'}.json")
    cfg.create_dir(dest.parent)
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    dest.chmod(0o600)
    if verbose:
        print(f"--- {label} （{len(ms)} 份实现全对最大差）---")
        print(f"{'指标':<24}{'相对差':>9}{'绝对差':>12}{'ε':>12} 类型  状态")
        for m in sorted(per, key=lambda x: -per[x]["max_rel_diff"]):
            r = per[m]
            e = "—" if r["epsilon"] is None else format(r["epsilon"], ".4g")
            k = "abs" if r["tolerance_kind"] == "absolute" else "rel"
            print(f"{m:<24}{r['max_rel_diff']:>9.3%}{r['max_abs_diff']:>12.4g}"
                  f"{e:>12} {k:<5} {r['status']}")
        print(f"可标定 {len(payload['calibrated'])} · 超阈 {len(bad)} · → {dest}\n")
    return payload


def compare(impl_a: Path, impls_b: "dict[str, Path]", *, verbose: bool = True) -> dict[str, Any]:
    A = json.loads(impl_a.read_text(encoding="utf-8"))
    ma = A["metrics"] if "metrics" in A else A
    bs = {name: json.loads(p.read_text(encoding="utf-8")) for name, p in impls_b.items()}
    bs = {k: (v["metrics"] if "metrics" in v else v) for k, v in bs.items()}

    names = sorted(set(ma) & set().union(*[set(v) for v in bs.values()]))
    missing = [m for m in REQUIRED_METRICS if m not in names]
    if missing:
        raise RuntimeError(f"实现 B 少了必须覆盖的指标：{missing}")

    per: dict[str, Any] = {}
    for m in names:
        if m in ("n_days",):
            continue
        a = ma.get(m)
        if not isinstance(a, (int, float)):
            continue
        rows = {}
        for name, mb in bs.items():
            b = mb.get(m)
            if not isinstance(b, (int, float)):
                continue
            rows[name] = {"a": float(a), "b": float(b), "rel": _rel(float(a), float(b))}
        if not rows:
            continue
        kind = tolerance_kind(m)
        for r in rows.values():
            r["abs"] = abs(r["a"] - r["b"])
        worst = max(rows.values(), key=lambda r: r["abs" if kind == "absolute" else "rel"])
        rel = worst["rel"]
        diff = worst["abs"] if kind == "absolute" else rel
        rec: dict[str, Any] = {
            "a": float(a), "by_impl": rows, "max_rel_diff": rel,
            "max_abs_diff": worst["abs"], "tolerance_kind": kind,
            "unit": ABSOLUTE_UNIT if kind == "absolute" else "相对差",
        }
        if kind == "absolute":
            # 趋零指标：判据走绝对差，相对差只作记录（它会被结构性放大）
            if diff == 0.0:
                rec["status"] = "no_implementation_freedom"
                rec["epsilon"] = None
                rec["note"] = ("A 与所有 B 完全相同 —— 该指标在当前声明下**没有实现自由度**。"
                               "**不得用其他指标的 ε 代填**。")
            else:
                rec["status"] = "calibrated"
                rec["epsilon"] = diff * MULTIPLIER
                rec["note"] = (f"**绝对容差**：该指标构造上可能趋零，相对差（{rel:.2%}）"
                               f"会被结构性放大，不作判据。ε 单位 = {ABSOLUTE_UNIT}。")
            per[m] = rec
            continue
        if rel == 0.0:
            rec["status"] = "no_implementation_freedom"
            rec["epsilon"] = None
            rec["note"] = ("A 与所有 B 完全相同 —— 该指标在当前声明下**没有实现自由度**。"
                           "**不得用其他指标的 ε 代填**；S7 判这一项时应当要求精确相等"
                           "（或另行声明一个理由充分的容差）。")
        elif rel < NOISE_FLOOR:
            rec["status"] = "invalid_below_noise_floor"
            rec["epsilon"] = None
            rec["note"] = (f"相对差 {rel:.3g} 低于浮点噪声地板 {NOISE_FLOOR:g} —— "
                           f"量到的是舍入不是实现自由度，**不作 ε**。")
        elif rel > IMPLAUSIBLE_REL_DIFF:
            rec["status"] = "implausible_stop_and_report"
            rec["epsilon"] = None
            rec["note"] = (f"相对差 {rel:.2%} 超过 {IMPLAUSIBLE_REL_DIFF:.0%} —— "
                           f"这不像实现自由度，多半是**声明没写清**或**有一方实现错了**。"
                           f"**停下汇报，不写成 ε**：过宽的 ε 会让 S7 失去判别力。")
        else:
            rec["status"] = "calibrated"
            rec["epsilon"] = rel * MULTIPLIER
        per[m] = rec

    bad = [m for m, r in per.items() if r["status"] == "implausible_stop_and_report"]
    floor = [m for m, r in per.items() if r["status"] == "invalid_below_noise_floor"]
    free = [m for m, r in per.items() if r["status"] == "no_implementation_freedom"]
    ok = [m for m, r in per.items() if r["status"] == "calibrated"]
    usable = (not bad) and all(m in per for m in REQUIRED_METRICS)

    payload = {
        "card": "2.2b",
        "method": "dual_independent_implementation",
        "built_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "multiplier": MULTIPLIER,
        "noise_floor": NOISE_FLOOR,
        "implausible_threshold": IMPLAUSIBLE_REL_DIFF,
        "contract": "ops/specs/backtest_contract.md",
        "implementation_a": str(impl_a),
        "implementations_b": {k: str(v) for k, v in impls_b.items()},
        "why_not_cross_version": ("跨 4 个 numpy/pandas 组合的最大相对极差 8.53e-14，全是舍入；"
                                  "ε 的用途是判 agent 的独立实现，环境噪声与之无关。"),
        "tolerance_rule": {
            "relative": "尺度无关且不趋零的指标（Sharpe / MDD / 换手 / 波动 / 胜率 / 总成本）",
            "absolute": f"构造上可能趋零的指标：{sorted(ZERO_APPROACHING)}；"
                        f"ε = |A−B| 的绝对差 × {MULTIPLIER}，单位 = {ABSOLUTE_UNIT}",
            "why": ("相对容差施加在趋零量上没有意义。实测 ann_return_net 的相对差 90.85%，"
                    "但那是毛收益(0.057) 减 成本拖累(0.05) 的小差被放大，"
                    "同一批实现在 ann_vol_net 上只差 1.53%。"),
            "enforced_by": "reference.epsilon_dual.assert_tolerance_kind()（配错直接抛错）",
        },
        "epsilon_by_metric": per,
        "calibrated": ok, "no_freedom": free,
        "below_floor": floor, "implausible": bad,
        "usable": usable,
        "outstanding": ([] if usable else
                        [f"{m}: 相对差 {per[m]['max_rel_diff']:.2%} 超阈，需先查声明或实现" for m in bad]),
    }
    dest = out_path()
    cfg.create_dir(dest.parent)
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    dest.chmod(0o600)
    if verbose:
        print(f"{'指标':<26}{'A':>13}{'相对差':>10}{'绝对差':>12}{'ε':>12} 类型  状态")
        for m in sorted(per, key=lambda x: -per[x]["max_rel_diff"]):
            r = per[m]
            e = "—" if r["epsilon"] is None else format(r["epsilon"], ".4g")
            k = "abs" if r["tolerance_kind"] == "absolute" else "rel"
            print(f"{m:<26}{r['a']:>13.5g}{r['max_rel_diff']:>10.2%}"
                  f"{r['max_abs_diff']:>12.4g}{e:>12} {k:<5} {r['status']}")
        print(f"\n可标定 {len(ok)} · 无自由度 {len(free)} · 低于地板 {len(floor)} · 超阈 {len(bad)}")
        if bad:
            print("\n⚠ 以下指标**停下汇报**，未写成 ε：")
            for m in bad:
                print(f"  {m}: 相对差 {per[m]['max_rel_diff']:.2%}")
                for n, r in per[m]["by_impl"].items():
                    print(f"      A={r['a']:.6g}  {n}={r['b']:.6g}")
        print(f"→ {dest}")
    return payload


def main(argv: "list[str] | None" = None) -> int:
    p = argparse.ArgumentParser(description="卡 2.2b 双实现 ε 标定")
    p.add_argument("--a", default=str(eps_dir() / "bt_qlib_alpha158.ROC20_baseline.json"))
    p.add_argument("--b", nargs="+", required=True, help="实现 B 的指标 JSON（可多份）")
    a = p.parse_args(argv)
    bs = {Path(x).stem: Path(x) for x in a.b}
    rep = compare(Path(a.a), bs)
    return 0 if rep["usable"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
