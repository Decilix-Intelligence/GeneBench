"""卡 4.2 §16：出口纪律。

`to_scorer_input()` **非 `None` 当且仅当 `run_status == "ok"` 且非 malformed**，
**且任何地方不得出现非空 `gate_failed`**。

禁止为结构性失败伪造闸门。伪造的后果：「**没交产物**」与「**有前视违例**」
在主表上变成同一个数，而这两件事的含义相反 —— 一个是能力不足，一个是行为违规。

`gate_only()` 产出的 `gate.json` **必须通不过** `validate_scorer_output()`
（codes 含 `correctness_missing`）。这是刻意的：`gate.json` 是**半成品**，
它进不了主表这件事要由**校验器**说，不由约定说。
"""
from __future__ import annotations

from runner.c42 import failure_modes as FM

SCHEMA_VERSION = "1.0"

#: `anchor_status == "pending"` 时的扣住理由。镜像自
#: `reference.artifact_schema.EFFECT_WITHHELD_REASONS`（同源断言在 ops/test_c42.py）。
ANCHOR_PENDING = "anchor_pending"


#: 这些桶里的运行**没有可读产物**，校验器根本没跑 —— 任何 `gate_failed` 都是伪造的。
#: 从 `RUN_STATUS_TO_SR` 推，不手抄一份状态名：手抄的那份会在加状态时漏掉新的。
NO_VERDICT_BUCKETS: frozenset[str] = frozenset(
    {"unscorable_agent", "unscorable_harness", "leaked"})


class ExitDisciplineError(RuntimeError):
    pass


def _assert_buckets_known() -> None:
    unknown = NO_VERDICT_BUCKETS - set(FM.SR_BUCKETS)
    if unknown:
        raise ExitDisciplineError(f"NO_VERDICT_BUCKETS 里有未知桶 {sorted(unknown)}")
    # 剩下的两个桶（scorable / malformed）是校验器跑过的 —— 少一个就说明分类表变了
    rest = set(FM.SR_BUCKETS) - NO_VERDICT_BUCKETS
    if rest != {"scorable", "malformed"}:
        raise ExitDisciplineError(
            f"分类表变了：校验器跑过的桶现在是 {sorted(rest)} —— 出口纪律的判据要跟着改")


_assert_buckets_known()


def to_scorer_input(*, run_status: str, artifact: dict | None, gate_failed=None,
                    harness_checks: dict | None = None, telemetry: dict | None = None,
                    **extra) -> dict | None:
    """结算入口。**其余一切结局返回 `None`。**"""
    bucket = FM.sr_bucket(run_status)          # 未知 run_status 在这里就抛
    gate_failed = list(gate_failed or [])
    if run_status != "ok":
        # 判据不是「非 ok 就不许有闸门」—— `malformed` 的运行**校验器跑过**，
        # 它给出的 `gate_failed`（例如 default_fill 桩的 `underdetermined`）是真的。
        # 伪造只可能发生在**校验器根本没跑**的那些结局上：没有可读产物，
        # 任何闸门都无从产生。这个集合从分类表推，不手抄。
        if gate_failed and bucket in NO_VERDICT_BUCKETS:
            raise ExitDisciplineError(
                f"run_status={run_status}（{bucket} 桶，校验器没跑过）却带着 "
                f"gate_failed={gate_failed} —— 为结构性失败伪造闸门，会让"
                f"「没交产物」与「有前视违例」在主表上变成同一个数，而这两件事含义相反")
        return None
    if bucket != "scorable":
        raise ExitDisciplineError(f"run_status=ok 却落在 {bucket} 桶 —— 分类表自相矛盾")
    if artifact is None:
        raise ExitDisciplineError("run_status=ok 却没有 artifact")
    return {"schema_version": SCHEMA_VERSION, "artifact": artifact,
            "gate_failed": gate_failed,
            "harness_checks": harness_checks or {},
            "telemetry": telemetry or {}, **extra}


def gate_only(*, gate_failed, unobservable=None, anchor_status: str = "pending") -> dict:
    """闸门半成品。**故意缺 correctness** —— 由校验器判它进不了主表。

    卡 5.4 落地补齐 correctness 之后，`anchor_status` 的两条分支：
    `pending` 须 `effect=None` + `effect_withheld_reason="anchor_pending"`；
    `fixed` 须报 `effect_missing_on_valid`。
    **那条测试届时要翻转，翻转必须留记录**（同 N-33 / `anchor_ladder_54` 做法）。
    """
    out = {"schema_version": SCHEMA_VERSION,
           "validity": "invalid" if gate_failed else "valid",
           "gate_failed": sorted(set(gate_failed or [])),
           "unobservable": sorted(set(unobservable or []))}
    if anchor_status == "pending":
        out["effect"] = None
        out["effect_withheld_reason"] = ANCHOR_PENDING
    return out
