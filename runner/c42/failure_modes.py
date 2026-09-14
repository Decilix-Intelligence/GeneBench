"""卡 4.2 §2：失败模式分类表。**这张表必须先有**，别的都往它上面接。

**实测理由**：现行 `c41/runner_core.py` 的 `failure_mode` 只有 `None | "nonzero_exit"`，
而 compose lint 未过与 `starts != 1` 是 `raise` —— 那几题**连一行都不写进库**。
那不是「失败」，是「**不存在**」：分母悄悄变小、SR 悄悄变高，没有任何东西报错，
而且方向对我们有利 —— 最难自查的那种（D-06 家族）。
"""
from __future__ import annotations

#: **顺序即优先级**，前者压后者。改这个元组就是改结算口径，不是改常量。
RUN_STATUSES: tuple[str, ...] = (
    "leaked", "harness_error", "timeout",
    "budget_exhausted",
    "no_artifact", "artifact_empty", "artifact_truncated",
    "artifact_oversize", "artifact_not_utf8", "artifact_not_json",
    "identity_mismatch", "malformed", "violation", "ok",
)

#: harness 自己坏掉的七种形态。B-03 要求每种各造一次。
HARNESS_FAULTS: tuple[str, ...] = (
    "lint", "bundle", "provider_pin", "egress_starts",
    "docker_up", "runtime_dependency", "stale_state",
)

SR_BUCKETS: tuple[str, ...] = (
    "scorable", "malformed", "unscorable_agent", "unscorable_harness", "leaked",
)

#: 全映射：`RUN_STATUSES` 上无多、无缺（`assert_taxonomy_total` 第 1 条）。
RUN_STATUS_TO_SR: dict[str, str] = {
    # 泄漏单列、**不算分**、**留在分母**：把它移出分母等于让一次泄漏事故顺带抬高 SR。
    # 若事后判定泄漏源是打包器，处置是该批次整体作废重跑，不是靠调整分母修数。
    "leaked": "leaked",
    # **唯一**被 `sr_denominator()` 排除的桶。
    "harness_error": "unscorable_harness",
    # 预算耗尽是被测系统的属性，不是我们的。
    "timeout": "unscorable_agent",
    #: **预算耗尽与交白卷不是一回事**（裁定 2026-09-06，N-130）：前者是我们把闸拧到那儿，
    #: 后者是被测方自己停了。桶还是 `unscorable_agent`（都进 SR 分母、都不算成功），
    #: 但**状态要分得开** —— 主表上「S7 四个 run 全是 no_artifact」会被读成模型不行，
    #: 而实测是两次都撞闸（150 次/3M token 撞 token；90 次/20M token 撞调用）。
    "budget_exhausted": "unscorable_agent",
    "no_artifact": "unscorable_agent",
    "artifact_empty": "unscorable_agent",
    "artifact_truncated": "unscorable_agent",
    "artifact_oversize": "unscorable_agent",
    "artifact_not_utf8": "unscorable_agent",
    "artifact_not_json": "unscorable_agent",
    # 归 agent 而不是 harness：它也可能是我们注错了环境变量，但那种情况 B 档的注入断言
    # 会**先**红。记 harness 等于给「产物在伪装」开一条**不进分母**的通道（红队 rt05/rt09/rt17）。
    "identity_mismatch": "unscorable_agent",
    "malformed": "malformed",           # 与卡 2.3 同名同义
    "violation": "scorable",            # 结构合法，违例走 gate_failed
    "ok": "scorable",
}

#: **只排除它**。写死在这里，`sr_denominator()` 不接受参数化 ——
#: 参数化的排除集等于把结算口径交给调用方。
EXCLUDED_FROM_DENOMINATOR: tuple[str, ...] = ("unscorable_harness",)

_RANK: dict[str, int] = {s: i for i, s in enumerate(RUN_STATUSES)}


class TaxonomyError(RuntimeError):
    """分类表自身不自洽。import 期抛 —— 不能等到结算时才发现。"""


def rank(status: str) -> int:
    """优先级序号，越小越压。未知状态即抛：静默给一个大数会让它排到最后，
    而「未知」应当中止，不是排队。"""
    try:
        return _RANK[status]
    except KeyError:
        raise TaxonomyError(f"未知 run_status {status!r}；合法值 {list(RUN_STATUSES)}") from None


def worst(*statuses: str) -> str:
    """一次运行可能同时命中多条判据，取优先级最高的那个。

    `leaked` 压一切 —— 泄漏发生后，这次运行的**任何**读数都不再代表被测系统；
    先分类成别的状态再补标泄漏，等于让一次污染运行的分数先进主表。
    """
    if not statuses:
        raise TaxonomyError("worst() 至少要一个状态 —— 空调用多半是上游忘了传")
    return min(statuses, key=rank)


def sr_bucket(status: str) -> str:
    if status not in RUN_STATUS_TO_SR:
        raise TaxonomyError(f"未知 run_status {status!r}")
    return RUN_STATUS_TO_SR[status]


def status_for_fault(fault: str) -> str:
    """harness 故障 → `harness_error`。未知故障名即抛（恒等式第 4 条的运行时面）。"""
    if fault not in HARNESS_FAULTS:
        raise TaxonomyError(f"未知 harness_fault {fault!r}；合法值 {list(HARNESS_FAULTS)}")
    return "harness_error"


def sr_denominator(statuses) -> int:
    """SR 的分母：排除 `unscorable_harness`，**只排除它**。

    `leaked` 留在分母是刻意的（见 `RUN_STATUS_TO_SR` 注释）。
    """
    return sum(1 for s in statuses if sr_bucket(s) not in EXCLUDED_FROM_DENOMINATOR)


def assert_taxonomy_total() -> None:
    """import 期跑（D-03 恒等式做法）。四条。"""
    # 1. 全映射：无多、无缺。
    if set(RUN_STATUS_TO_SR) != set(RUN_STATUSES):
        miss = set(RUN_STATUSES) - set(RUN_STATUS_TO_SR)
        extra = set(RUN_STATUS_TO_SR) - set(RUN_STATUSES)
        raise TaxonomyError(f"RUN_STATUS_TO_SR 不是全映射：缺 {sorted(miss)}、多 {sorted(extra)}")
    # 2. 值域 ⊆ SR_BUCKETS，且每个桶至少有一个 run_status 落进来（空桶是死桶，删或补）。
    vals = set(RUN_STATUS_TO_SR.values())
    if not vals <= set(SR_BUCKETS):
        raise TaxonomyError(f"SR 桶越界：{sorted(vals - set(SR_BUCKETS))}")
    if vals != set(SR_BUCKETS):
        raise TaxonomyError(f"空桶：{sorted(set(SR_BUCKETS) - vals)} —— 没有任何 run_status 落进来，删或补")
    # 3. RUN_STATUSES 无重复，rank() 在其上是双射。
    if len(set(RUN_STATUSES)) != len(RUN_STATUSES):
        raise TaxonomyError("RUN_STATUSES 有重复 —— 优先级就不是全序了")
    if sorted(_RANK.values()) != list(range(len(RUN_STATUSES))):
        raise TaxonomyError("rank() 不是双射")
    # 4. 每个 HARNESS_FAULTS 成员都能映到 harness_error，且**只**映到它。
    got = {status_for_fault(f) for f in HARNESS_FAULTS}
    if got != {"harness_error"}:
        raise TaxonomyError(f"harness_fault 映到了 {sorted(got)}，应当只有 harness_error")
    if not HARNESS_FAULTS:
        raise TaxonomyError("HARNESS_FAULTS 为空 —— 第 4 条恒等式会真空通过")


assert_taxonomy_total()
