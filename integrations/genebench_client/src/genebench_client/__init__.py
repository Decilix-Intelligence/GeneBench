# -*- coding: utf-8 -*-
"""`genebench-client` —— 被测系统的取数垫片。

一句话：把 ``import yfinance`` / ``import tushare`` / ``import akshare``
换成 ``from genebench_client.compat import yfinance as yf``（其余同理），
取数就自动**经网关、带身份、受 as_of 约束、落 access_log**；
新闻 / 财务 / 资金流一律 `NoData` 并在网关日志上留痕。

最短用法::

    import genebench_client as gb
    from genebench_client.compat import yfinance as yf

    gb.set_as_of("2026-06-30")            # 从 task.yaml 的 as_of 读来
    px = yf.download(["600000.SS", "000001.SZ"], start="2026-06-01", end="2026-06-30")

不设 as_of 就抛 `AsOfRequired` —— **不猜**。猜出来的那个值会让越界变成合法请求，
而产物上完全看不出来。

⚠️ `GENEBENCH_AS_OF` 目前**不由 runner 注入**（compose 模板里没有这一行），
所以容器里正常的做法是启动时 `gb.set_as_of(spec["as_of"])`。
"""
from __future__ import annotations

import os
import threading

from .codes import (CodeError, compact_date, infer_market, iso_date, to_akshare,
                    to_lake, to_panel, to_yfinance)
from .errors import (AsOfRequired, BudgetExceeded, GatewayError,
                     GatewayUnreachable, GenebenchClientError, LookaheadDenied,
                     MalformedRequest, NoData, RateLimited)
from .gateway import (AS_OF_ENV, DATA_ENDPOINTS, GATEWAY_ENVS, SIM_ENDPOINTS,
                      Client, normalize_frame)

__version__ = "1.0.0"

__all__ = [
    "Client", "client", "set_as_of", "get_as_of", "configure", "reset",
    "normalize_frame", "compat", "qlib_provider",
    "AsOfRequired", "BudgetExceeded", "GatewayError", "GatewayUnreachable",
    "GenebenchClientError", "LookaheadDenied", "MalformedRequest", "NoData",
    "RateLimited", "CodeError",
    "to_lake", "to_yfinance", "to_akshare", "to_panel", "infer_market",
    "iso_date", "compact_date",
    "AS_OF_ENV", "GATEWAY_ENVS", "DATA_ENDPOINTS", "SIM_ENDPOINTS",
]

_LOCK = threading.Lock()
_CLIENT: Client | None = None
_AS_OF: str = ""


def set_as_of(as_of: str) -> str:
    """设定本进程的 as_of。**兼容层没有 as_of 参数可传**（`yf.download` 的签名里没有它），
    所以这是被测系统唯一该在启动时做的一件事。

    改 as_of 会**重建客户端**：一个客户端 = 一次运行的一个 as_of 视角，
    半路换 as_of 却复用同一个对象，日志里两段请求就混在一起了。
    """
    global _AS_OF
    with _LOCK:
        _AS_OF = iso_date(as_of)
        _rebuild_locked()
    return _AS_OF


def get_as_of() -> str:
    return _AS_OF or (os.environ.get(AS_OF_ENV) or "").strip()


def configure(**kw) -> Client:
    """显式装配共享客户端（`base_url` / `task_id` / `config_id` / `run_id` / `arm` / `timeout`）。

    正常路径**不需要调它** —— 这些值容器里都由 compose 注入。
    单元测试与 f01 上直跑时才用。
    """
    global _CLIENT
    with _LOCK:
        if _AS_OF and "as_of" not in kw:
            kw["as_of"] = _AS_OF
        _CLIENT = Client(**kw)
        return _CLIENT


def _rebuild_locked() -> None:
    global _CLIENT
    if _CLIENT is None:
        return
    _CLIENT = Client(base_url=_CLIENT.base_url, as_of=_AS_OF, task_id=_CLIENT.task_id,
                     config_id=_CLIENT.config_id, run_id=_CLIENT.run_id,
                     arm=_CLIENT.arm, timeout=_CLIENT.timeout)


def client() -> Client:
    """本进程共享的客户端。兼容层全部走它 —— 于是 `ledger` 是**一次运行的全部请求**。"""
    global _CLIENT
    with _LOCK:
        if _CLIENT is None:
            _CLIENT = Client(as_of=_AS_OF)
        return _CLIENT


def reset() -> None:
    """丢掉共享客户端与 as_of（测试用）。"""
    global _CLIENT, _AS_OF
    with _LOCK:
        _CLIENT = None
        _AS_OF = ""


from . import compat, qlib_provider                                   # noqa: E402,F401
