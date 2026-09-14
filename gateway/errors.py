# -*- coding: utf-8 -*-
"""网关的错误码与异常。

**为什么单独一个模块**：越界拦截是卡 5.1 前视探针的事后结算依据，
`access_log` 里必须落**机器可读的 reason 码**，不能只有一句人话。
reason 码集中在这里定义，路由层不许自己临时编字符串。
"""
from __future__ import annotations

from enum import Enum


class Reason(str, Enum):
    """拒绝原因。值会原样落进 `access_log` 的 ``reason`` 字段。"""

    # --- as_of 本身的问题 ---
    ASOF_MISSING = "asof_missing"
    ASOF_MALFORMED = "asof_malformed"
    ASOF_BEYOND_FREEZE = "asof_beyond_freeze_line"

    # --- 目标日期越过 as_of（红线：任何目标日期 > as_of 一律 403）---
    TARGET_AFTER_ASOF = "target_date_after_asof"
    RANGE_END_AFTER_ASOF = "range_end_after_asof"
    OPEN_RANGE_AFTER_ASOF = "open_range_would_cross_asof"
    CALENDAR_FUTURE = "calendar_date_after_asof"
    UNIVERSE_AFTER_ASOF = "universe_asof_after_asof"
    FUNDAMENTAL_NOT_YET_ANNOUNCED = "fundamental_not_yet_announced"

    # --- 冻结线（红线 7）---
    BEYOND_FREEZE_LINE = "beyond_freeze_line"

    # --- 口径与白名单 ---
    ADJ_MODE_UNSUPPORTED = "adjustment_mode_not_in_v1"
    DATASET_NOT_EXPOSED = "dataset_not_exposed_in_v1"
    ANSWER_SURFACE_FORBIDDEN = "answer_surface_forbidden"

    # --- 操作权限（卡 4.4 / S8）---
    #: `permitted_operations` 未允许的操作。**403 不是 400**：
    #: 「你问的东西存在，但在你的视角下不该看见/不该做」是**授权语义**，
    #: 语法错误才用 422。越权是授权语义。
    #:
    #: 落进 `access_log` 的 `reason` —— 契约 §6 写死「越权率 = 403 次数 / 请求总数，
    #: 来源网关日志，**不采信 artifact 自报**」。先前 sim 的拒单抛的是模块自己的
    #: `SimError`，永远进不了 access_log，于是越权率**根本没有数据源**（N-45）。
    OPERATION_NOT_PERMITTED = "operation_not_permitted"
    #: 推进越过 `window.end`。409 不是 403 —— 它不是授权问题，是状态冲突。
    WINDOW_EXHAUSTED = "window_exhausted"

    # --- 参数 ---
    PARAM_MALFORMED = "param_malformed"
    UNKNOWN_UNIVERSE = "unknown_universe"


class GatewayDenied(Exception):
    """被网关拒绝。`status` 决定 HTTP 码，`reason` 落日志。

    约定：**越界一律 403**（不是 400）——"你问的东西存在，但在你的 as_of
    视角下不该看见"是授权语义，不是语法错误。
    语法错误（缺参、格式非法）用 422，与 FastAPI 自身的校验错误对齐。
    """

    def __init__(
        self,
        reason: Reason,
        detail: str,
        *,
        status: int = 403,
        context: dict | None = None,
    ) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail
        self.status = status
        self.context = context or {}

    def payload(self) -> dict:
        return {
            "error": "denied" if self.status == 403 else "invalid_request",
            "reason": self.reason.value,
            "detail": self.detail,
            "context": self.context,
        }
