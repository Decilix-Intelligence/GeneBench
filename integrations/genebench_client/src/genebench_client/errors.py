# -*- coding: utf-8 -*-
"""垫片的异常族。

**为什么单独一个模块**：被测系统接住的是这些类型，不是 HTTP 码。把「403 是什么意思」
写在异常名上（`LookaheadDenied` 而不是 `HTTPError(403)`），是让「我越界了」这件事
在被测方的代码里**看得见**——它可以据此改自己的取数窗口，而不是把 403 当成
「网关坏了」去重试。

映射表（网关侧的定义见 `gateway/errors.py`，本表是**独立实现**、不 import 它）：

| HTTP | 异常 | 语义 |
| --- | --- | --- |
| 403 | `LookaheadDenied` | 你问的东西存在，但在你的 as_of 视角下不该看见（授权语义）|
| 422 | `MalformedRequest` | 参数写错了（语法）|
| 402 | `BudgetExceeded` | 预算闸（本项目里由边车而非网关给出，留位以免调用方自己猜）|
| 429 | `RateLimited` | 限流 |
| 其它 4xx/5xx | `GatewayError` | 未分类 |

`NoData` 不是 HTTP 错误：它是**本环境不提供这类数据源**这一事实的类型化表达。
新闻 / 财务 / 资金流一律走它，且**每一次都在网关 access_log 上留痕**（见 `nodata.py`）。
"""
from __future__ import annotations

from typing import Any


class GenebenchClientError(RuntimeError):
    """本包抛出的一切错误的根。"""


class AsOfRequired(GenebenchClientError):
    """没有 as_of 就不许取数。

    **fail-closed**：缺 as_of 时不去猜一个（比如"今天"或冻结线）——
    猜出来的那个值会让越界变成合法请求，而产物上完全看不出来。
    """


class GatewayUnreachable(GenebenchClientError):
    """连不上网关。与「网关拒绝了你」严格分开：前者是部署问题，后者是判据。"""


class GatewayError(GenebenchClientError):
    """网关返回了一个我们没有分类的非 2xx。"""

    def __init__(self, message: str, *, status: int = 0, path: str = "",
                 body: Any = None) -> None:
        super().__init__(message)
        self.status = status
        self.path = path
        self.body = body


class LookaheadDenied(GatewayError):
    """403：越过 as_of / 冻结线 / 未授权的操作。

    `reason` 是网关的机器可读拒绝码（如 ``range_end_after_asof``），
    `detail` 是人话，`context` 是网关给出的字段级说明。
    """

    def __init__(self, message: str, *, reason: str = "", detail: str = "",
                 context: dict | None = None, **kw) -> None:
        super().__init__(message, **kw)
        self.reason = reason
        self.detail = detail
        self.context = context or {}


class MalformedRequest(GatewayError):
    """422：参数语法错误。**包括垫片自己判出来的**（比如 interval 不是日线）。"""


class BudgetExceeded(GatewayError):
    """402：预算闸。"""


class RateLimited(GatewayError):
    """429：限流。"""


class NoData(GenebenchClientError):
    """本环境不提供这类数据源。

    `kind` 是留痕用的粗分类（``news`` / ``fundamentals`` / ``moneyflow`` …），
    `api` 是被调用的那个兼容接口的全名（``yfinance.Ticker.news``），
    `traced` 说明这次 NO_DATA **有没有**在网关 access_log 上留下痕迹。

    ``traced=False`` 时不要当成"没发生"——它只是说明留痕那一步也失败了
    （网关不可达），事件本身照样发生了，本地兜底日志里有。
    """

    def __init__(self, kind: str, api: str, *, message: str = "",
                 traced: bool = False, detail: dict | None = None) -> None:
        super().__init__(message or (
            f"[NO_DATA] 本环境不提供{kind}数据源（{api}）；"
            f"本次运行的全部数据只经网关获取。"))
        self.kind = kind
        self.api = api
        self.traced = traced
        self.detail = detail or {}
