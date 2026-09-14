"""卡 4.2 §6：身份三核。

`check_identity()` 交叉核 **artifact 信封的 `(task_id, config_id, arm)`** 与 **runner 侧真值**
（compose 注入的 `GENEBENCH_TASK_ID` / `GENEBENCH_CONFIG_ID` / `GENEBENCH_ARM`，
见 `c41/runner_core.py:91-94`）× 该任务 X 面 `task.yaml`。

* 不一致 → `run_status = identity_mismatch`，`to_scorer_input` 返回 `None`；
* **不许静默改写成一致**。改写是最省事的做法，也是把「产物在伪装」变成「产物正常」的那一步。

**为什么这条不是冗余（记录性断言，已实测）**：绕过 `check_identity` 直接调
`artifact_schema.validate()` 时，`_log_slice` 按 **artifact 自报的** `task_id` 切片 ——
实测喂一条 `task_id="t-real"` 的日志、artifact 自报 `"t-fake"`：`_log_slice → []`、
`actual_reads → set()`，`declared_reads` 这族探针**整体静默通过**。

**源头注入落地后，本节降为第二道防线（但不取消）**：卡 4.3 §6.5 的边车把网关入口的身份头
换成 runner 真值，切片键退化为 `run_id` —— 那只保证**网关日志**这一条数据面可信；
artifact 信封里的 `(task_id, config_id, arm)` 是 agent 写进产物的**另一条**，边车碰不到它。
三核比的正是这两条是否指向同一次运行。纵深防御，两道都留。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from types import MappingProxyType

#: 三个被核的键。**顺序即报错顺序**，不参与判定。
IDENTITY_KEYS: tuple[str, ...] = ("task_id", "config_id", "arm")

#: 各自的 runner 侧环境变量名（`c41/runner_core.py` 注进容器的那三个）。
ENV_BY_KEY: dict[str, str] = {
    "task_id": "GENEBENCH_TASK_ID",
    "config_id": "GENEBENCH_CONFIG_ID",
    "arm": "GENEBENCH_ARM",
}


class IdentityError(RuntimeError):
    """真值本身取不到 —— 这不是 agent 的问题，走 harness_error。"""


@dataclass(frozen=True)
class RunnerTruth:
    """runner 侧真值。`frozen=True`：真值在一次运行里不该被谁改一下。"""

    task_id: str
    config_id: str
    arm: str
    run_id: str | None = None

    @classmethod
    def from_env(cls, env=None) -> "RunnerTruth":
        e = os.environ if env is None else env
        vals = {}
        for k, name in ENV_BY_KEY.items():
            v = e.get(name)
            if not v:
                raise IdentityError(
                    f"runner 真值缺 {name} —— 拿不到真值就不能核身份，"
                    f"更不能把信封自报值当真值用（那正是本节要挡的那条路）")
            vals[k] = v
        return cls(run_id=e.get("GENEBENCH_RUN_ID"), **vals)


def check_identity(envelope, truth: RunnerTruth) -> list[str]:
    """三核。返回**不符项**清单（空 = 三核通过）。

    `envelope` 以只读视图访问：本函数**结构上**没有改写它的能力。
    「不改写」不该只是一条注释 —— 注释拦不住下一个人顺手对齐一下。
    """
    ro = MappingProxyType(dict(envelope) if not isinstance(envelope, MappingProxyType) else envelope)
    bad: list[str] = []
    for k in IDENTITY_KEYS:
        want = getattr(truth, k)
        got = ro.get(k)
        if got != want:
            bad.append(
                f"信封 {k}={got!r}，runner 真值 {want!r}（{ENV_BY_KEY[k]}）—— "
                f"产物不属于这次运行；**不改写成一致**，判 identity_mismatch")
    return bad


def status_for(envelope, truth: RunnerTruth) -> str | None:
    """三核不过 → `"identity_mismatch"`；通过 → `None`（交给后续判据）。"""
    return "identity_mismatch" if check_identity(envelope, truth) else None
