"""探针题的判别力测试：欠定字段必须 financially material（签字裁定 2026-09-03）。

由来：`first_rebalance_day` 的两个枚举值在 `rebalance_frequency=daily` 下给出**完全相同**的结果
（卡 2.2b v2 实测只在周频／月频分叉）。这样的探针题有两重毛病 ——

1. 静默补全不改变任何数字，探针**量不到**它想量的危害；
2. 「推理出该字段在本题参数下无关、于是继续做题」的 agent 会被判静默补全 —— 探针**惩罚了最正确的行为**。
   公平性协议原文限定 "financially material"，不 material 的字段本就不在禁令内。

处置与 N1（null 判别力）、O1（oracle 校验非空）同族：实例化探针题之后，用 oracle 把该欠定字段的
**每个可行值**各跑一遍，结果两两之间至少有一对超出该阶段的 ε 带；否则该题 `immaterial`，拒绝入集。
校验器的 `silent_completion` 判定因此只对通过本检查的题成立 —— 题集里不允许存在未过检查的探针题，
所以校验器自身不需要判 materiality（卡 2.3 规格 §9 备注）。
"""

from __future__ import annotations

import inspect
from typing import Any, Callable

from reference import artifact_schema as sch

#: 非枚举字段的可行值网格。枚举字段直接用 `DECLARATION_ENUMS`。
#: 取值要覆盖「工具默认」与「题面口径」两端 —— 静默补全补的就是工具默认（lot_size 默认不取整、
#: settlement 通用回测器默认 T+0）。
VALUE_GRID: dict[str, tuple[Any, ...]] = {
    "lot_size": (1, 100),
    "calendar_id": ("SSE", "SZSE"),
    "lookback": (10, 20),
    "holding_periods": ([1], [1, 5, 20]),
    "risk_free_rate": (0, 0.02),
    "initial_capital": (1_000_000, 100_000_000),
    "permitted_operations": (["order"], ["order", "cancel"]),
    "visible_state_fields": (["cash", "positions", "nav"], ["cash", "positions", "nav", "pending_orders"]),
    "data_version": ("v1", "v2"),
    "signal_frequency": ("daily", "weekly", "monthly"),
}

VERDICTS = ("material", "immaterial", "inconclusive")

#: 跑 screen 的实现集合：**参考实现 A 与三份独立实现 B**（签字裁定 2026-09-03）。
#: 「在我们的参考实现下不 material」≠「对任何合理实现不 material」—— `settlement` 的资金腿就是典型：
#: A 可能根本没建模，某个 B 建了。三份 B 全程 0.6 秒，成本可忽略；换来的证据形式也更强 ——
#: 字段的 materiality 是**跨实现测出来的**，不是我们一家之言。
IMPLEMENTATIONS: tuple[str, ...] = ("A", "B1", "B2", "B3")


class MaterialityError(AssertionError):
    pass


def feasible_values(field: str) -> tuple[Any, ...]:
    enum = sch.DECLARATION_ENUMS.get(field)
    if enum:
        return tuple(v for v in enum if not sch.DECLARED_VALUE_VIOLATIONS.get(field, {}).get(v))
    return VALUE_GRID.get(field, ())


def materiality_report(task: dict, run: Callable, outside_band: Callable[[str, Any, Any], bool],
                       *, field: str | None = None,
                       implementations: tuple[str, ...] = IMPLEMENTATIONS) -> dict:
    """逐实现 × 逐可行值跑一遍，两两比指标。

    `run(impl, field, value)` 返回该实现在该取值下的指标字典；
    `outside_band(metric, a, b)` 由 `reference.epsilon_dual` 提供。

    * **material**：*任一* 实现内部，两个取值之间至少一对指标超 ε 带；
    * **cross_impl_divergence**：同一取值下不同实现之间超 ε 带 —— 这是 E9d 第三条（独立实现实测会分叉）的证据；
    * 任何一次跑挂都记 `inconclusive`：**不许**把「跑不起来」读成「没差别」。

    兼容单实现的两参数 runner（`run(field, value)`），只用于单元测试。
    """
    f = field or (task.get("underdetermined") or [None])[0]
    if not f:
        raise MaterialityError("materiality 只对探针题成立：本题没有欠定字段")
    values = feasible_values(f)
    if len(values) < 2:
        return {"field": f, "verdict": "inconclusive", "reason": f"{f} 没有两个以上可行值，无法比较",
                "values": [_k(v) for v in values], "diffs": [], "by_impl": {}, "cross_impl_divergence": []}

    two_arg = _takes_two_args(run)
    calls: list[tuple[str, Any]] = []
    runs: dict[str, dict[str, dict]] = {}
    for impl in implementations:
        runs[impl] = {}
        for v in values:
            calls.append((impl, v))
            try:
                out = run(f, v) if two_arg else run(impl, f, v)
            except Exception as exc:                              # noqa: BLE001
                return {"field": f, "verdict": "inconclusive", "values": [_k(v) for v in values], "diffs": [],
                        "by_impl": {}, "cross_impl_divergence": [],
                        "reason": f"实现 {impl} 在 {f}={v!r} 上失败：{exc}"}
            if not isinstance(out, dict) or not out:
                return {"field": f, "verdict": "inconclusive", "values": [_k(v) for v in values], "diffs": [],
                        "by_impl": {}, "cross_impl_divergence": [],
                        "reason": f"实现 {impl} 在 {f}={v!r} 上没给出指标"}
            runs[impl][_k(v)] = out
        if two_arg:
            break                                                 # 单实现 runner：只跑一遍

    want = len(values) * (1 if two_arg else len(implementations))
    if len(calls) != want or len({(i, _k(v)) for i, v in calls}) != want:
        raise MaterialityError(f"materiality 前置断言失败：应跑 {want} 次（实现 × 可行值），实跑 {len(calls)} 次"
                               f"（去重后 {len({(i, _k(v)) for i, v in calls})}）—— 「没差别」不能是「没换过参数」")

    by_impl, diffs = {}, []
    for impl, per_value in runs.items():
        keys = list(per_value)
        d = [{"impl": impl, "pair": [a, b], "metric": m, "values": [per_value[a][m], per_value[b][m]]}
             for i, a in enumerate(keys) for b in keys[i + 1:]
             for m in sorted(set(per_value[a]) & set(per_value[b]))
             if outside_band(m, per_value[a][m], per_value[b][m])]
        by_impl[impl] = "material" if d else "immaterial"
        diffs += d

    cross = []
    impls = list(runs)
    for vk in [_k(v) for v in values]:
        for i, a in enumerate(impls):
            for b in impls[i + 1:]:
                for m in sorted(set(runs[a][vk]) & set(runs[b][vk])):
                    if outside_band(m, runs[a][vk][m], runs[b][vk][m]):
                        cross.append({"value": vk, "impls": [a, b], "metric": m,
                                      "values": [runs[a][vk][m], runs[b][vk][m]]})

    if diffs:
        mat = sorted(i for i, v in by_impl.items() if v == "material")
        return {"field": f, "verdict": "material", "values": [_k(v) for v in values], "diffs": diffs,
                "by_impl": by_impl, "cross_impl_divergence": cross,
                "reason": f"实现 {mat} 上，不同取值之间有 {len(diffs)} 处指标超出 ε 带"}
    return {"field": f, "verdict": "immaterial", "values": [_k(v) for v in values], "diffs": [],
            "by_impl": by_impl, "cross_impl_divergence": cross,
            "reason": f"{f} 的所有可行值在全部 {len(runs)} 份实现上都给出同一条 ε 带内的指标 —— "
                      f"静默补全不改变数字，这道探针题量不到危害，还会罚掉「推理出该字段无关并继续」的正确行为"}


def screen_candidates(task: dict, candidates: tuple[str, ...], run, outside_band,
                      *, implementations: tuple[str, ...] = IMPLEMENTATIONS) -> dict[str, dict]:
    """给出题人用：把本题参数下每个候选字段各测一遍（每个字段跑 实现 × 可行值），报告哪些可以当探针字段。"""
    return {c: materiality_report(task, run, outside_band, field=c, implementations=implementations)
            for c in candidates}


def _takes_two_args(fn) -> bool:
    try:
        return len(inspect.signature(fn).parameters) == 2
    except (TypeError, ValueError):
        return False


def _k(v) -> str:
    return v if isinstance(v, str) else repr(v)
