"""卡 5.1（线 C / C1，2026-09-05）：闸门 + 三态接线。

把已有的零件接成数据面上**一条**结算路径，不新造判据：

* 校验器 `reference.artifact_schema.validate`（冻结件，卡 0）出 findings：
  `malformed`（结构不合法）/ `violation[probe]`（合法但违例，映射到探针族）；
* 可见性 `runner.c42.visibility.visibility` 出网关日志三态（`None` 不可得 / `[]` 可得零条 / 切片）
  与本次运行**检不了**的探针族；
* 出口纪律 `runner.c42.scorer_io` 的桶规则决定哪些 run 根本没有 verdict（校验器没跑过）。

三态是**逐探针族**的：

| 态 | 含义 | 来源 |
| --- | --- | --- |
| `violation` | 检过、命中 | `Verdict.gate_failed` |
| `unobservable` | 本次运行检不了（日志不可得、粒度不够…） | `Verdict.unobservable` |
| `clean` | **检过且零命中** | 其余 |

`clean` 的定义是「检过且零命中」，不是「零命中」—— 恒绿的门与恒红的一样会被绕过（F7 / D-06），
所以 unobservable 必须单列，且 `unobservable ∩ gate_failed = ∅`（卡 2.3 已保证，这里再断言一次）。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from reference.artifact_schema import PROBE_IDS, Verdict, validate

PROBE_STATES: tuple[str, ...] = ("violation", "unobservable", "clean")


class GateError(RuntimeError):
    pass


@dataclass
class GateResult:
    validity: str                                   # "valid" | "invalid"
    malformed: bool
    gate_failed: list[str]
    unobservable: list[str]
    probe_states: dict[str, str]                    # 每个探针族 → 三态之一，**全族都在**
    findings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"validity": self.validity, "malformed": self.malformed,
                "gate_failed": list(self.gate_failed), "unobservable": list(self.unobservable),
                "probe_states": dict(self.probe_states), "findings": list(self.findings),
                "notes": list(self.notes)}


def probe_states(v: Verdict) -> dict[str, str]:
    """逐探针族三态。**每个族都出现**——少一个族就等于那族「没检」被记成了「没事」。"""
    failed, unobs = set(v.gate_failed), set(v.unobservable)
    both = failed & unobs
    if both:
        raise GateError(f"{sorted(both)} 同时 violation 与 unobservable —— 不可检的探针不可能失败")
    out: dict[str, str] = {}
    for p in sorted(PROBE_IDS):
        out[p] = "violation" if p in failed else ("unobservable" if p in unobs else "clean")
    return out


def gate(artifact: dict, *, task: dict | None, gateway_log: list[dict] | None,
         unobservable_marks: list[tuple[str, str]] = (), tradability: dict | None = None,
         config_id: str | None = None, payload_profile: str | None = None) -> GateResult:
    """跑校验器 + 贴可见性标注，出三态。

    `gateway_log`：**原样**传给校验器（`None` ≠ `[]`，红队 rt18）；
    `unobservable_marks`：`visibility()` 给的 `(probe, why)` 列表，逐条 `mark_unobservable`。
    """
    v = validate(artifact, task=task, gateway_log=gateway_log, tradability=tradability,
                 config_id=config_id, payload_profile=payload_profile)
    for probe, why in unobservable_marks:
        if probe in set(v.gate_failed):
            # 校验器在没有日志的情况下仍判出了这族的 violation（例如产物自报与声明矛盾）——
            # 那是真的违例，不因为日志不可得而撤销；只是不再额外标 unobservable。
            v.notes.append(f"{probe}: 校验器已判 violation，日志不可得不影响该判定（{why}）")
            continue
        v.mark_unobservable(probe, why)
    states = probe_states(v)
    validity = "invalid" if (v.malformed or v.gate_failed) else "valid"
    return GateResult(validity=validity, malformed=v.malformed, gate_failed=list(v.gate_failed),
                      unobservable=list(v.unobservable), probe_states=states,
                      findings=[str(f) for f in v.findings], notes=list(v.notes))
