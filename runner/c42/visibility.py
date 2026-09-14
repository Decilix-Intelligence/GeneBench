"""卡 4.2 §7：可见性三态与日志切片契约。

**三态**：

* 文件不存在 → **返回 `None`**，**绝不返回 `[]`**；
* 文件存在且零条 → `[]`。

`None` = 不可得（跳过交叉核并标 unobservable），`[]` = 可得但零请求（按 0 条核）。
传 `[]` 会让 `declared_reads` / `fetch_clock` 这些交叉核**真空通过** ——
「什么都没有」与「这次没取数」在数值上不可区分（红队 rt18/rt36）。

**第三维：时间窗（§7.2，两稿都缺）。** 校验器的 `_log_slice` 只按 `(task_id, config_id)`
两维切；同一个 task **重跑**、或日志**跨运行追加**，上一次 run 的条目会被算进这一次 ——
`actual_reads` 凭空变大、`fetch_clock` 凭空对上。这与卡 4.1 的
「`starts != 1` 说明日志跨运行了」是同一个形状，只是那边发生在出向日志。
所以切片在**交给校验器之前**就按 `(task_id, config_id, [started_at, finished_at])` 三重做完
—— 校验器是冻结件（卡 0），三维不能改到它里面去。

时间窗取 **runner 侧真值**（`started_at` / `finished_at`），**不取 artifact 自报的 `produced_at`**
—— 自报值可被改。
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

#: 结算依赖网关日志的探针族。**镜像自 `reference.artifact_schema.PROBE_IDS`**
#: （`ops/test_c42.py` 有同源断言：不在 PROBE_IDS 里的名字会让 `mark_unobservable` 抛）。
LOG_DEPENDENT_PROBES: tuple[str, ...] = (
    "declared_reads", "fetch_clock", "source_status", "lookahead",
)

#: 跨机取回（网关 `access_log` 在 f01，执行面在 f02）方案未定 —— 工单 **T-13**。
#: 在它落地之前：**一律传 `None`**，并在主表脚注写明这四族在 v1 不可检。
#: 写 `[]` 省事、并且会让主表更好看 —— 这正是不能写 `[]` 的原因。
CROSS_HOST_RETRIEVAL_PENDING: bool = True
UNOBSERVABLE_REASON = ("网关 access_log 在 f01、执行面在 f02，跨机取回未定（T-13）；"
                       "日志不可得按 None 处理，不按零条")


class VisibilityError(RuntimeError):
    pass


def load_gateway_log(path) -> list[dict] | None:
    """三态的**唯一**入口。不存在 → `None`；存在 → list（可能是 `[]`）。"""
    p = Path(path)
    if not p.exists():
        return None                       # ← 绝不 `[]`
    out: list[dict] = []
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError as ex:
            raise VisibilityError(f"{p}:{i} 不是 JSON：{ex}") from None
        if not isinstance(e, dict):
            raise VisibilityError(f"{p}:{i} 不是 JSON 对象")
        out.append(e)
    return out


def _ts(v) -> dt.datetime | None:
    if not isinstance(v, str) or not v:
        return None
    try:
        d = dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def slice_for_run(log: list[dict] | None, *, task_id: str, config_id: str,
                  started_at: str, finished_at: str) -> list[dict] | None:
    """三重切片。`None` 进 `None` 出 —— 不可得不会因为切了一刀就变成可得。

    时间窗**闭区间**：网关的 `ts` 与 runner 的 `started_at` 精度不同（毫秒 vs 秒），
    开区间会把恰好落在边界那一毫秒的请求丢掉，表现为 `actual_reads` 少一条。
    """
    if log is None:
        return None
    lo, hi = _ts(started_at), _ts(finished_at)
    if lo is None or hi is None:
        raise VisibilityError(
            f"时间窗取不到 runner 真值（started_at={started_at!r}, finished_at={finished_at!r}）"
            f" —— 拿不到窗就不能切；退回两维切片会把上一次 run 的条目算进这一次（§7.2）")
    if hi < lo:
        raise VisibilityError(f"时间窗反了：{started_at} → {finished_at}")
    out = []
    for e in log:
        if e.get("task_id") != task_id:
            continue
        if e.get("config_id") not in (None, config_id):
            continue
        t = _ts(e.get("ts"))
        if t is None or not (lo <= t <= hi):
            continue
        out.append(e)
    return out


def visibility(log_path, *, task_id: str, config_id: str,
               started_at: str, finished_at: str,
               cross_host_pending: bool | None = None
               ) -> tuple[list[dict] | None, list[tuple[str, str]]]:
    """返回 `(gateway_log, unobservable_probes)`。

    后者进 `Verdict.mark_unobservable(probe, reason)`（卡 2.3 已保证
    `unobservable ∩ gate_failed == ∅`）。标注在**数据面**做 —— 本模块不 import reference。
    """
    pending = CROSS_HOST_RETRIEVAL_PENDING if cross_host_pending is None else cross_host_pending
    if pending:
        return None, [(p, UNOBSERVABLE_REASON) for p in LOG_DEPENDENT_PROBES]
    log = load_gateway_log(log_path)
    if log is None:
        return None, [(p, f"网关日志不存在：{log_path}") for p in LOG_DEPENDENT_PROBES]
    return slice_for_run(log, task_id=task_id, config_id=config_id,
                         started_at=started_at, finished_at=finished_at), []
