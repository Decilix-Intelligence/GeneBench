# -*- coding: utf-8 -*-
"""三个取数库的兼容层。

    from genebench_client.compat import yfinance as yf
    from genebench_client.compat import tushare as ts
    from genebench_client.compat import akshare as ak

改不了源码的系统可以用 `install()` 把它们**顶替**进 `sys.modules`::

    import genebench_client.compat as compat
    compat.install()                      # 之后 `import yfinance` 拿到的就是垫片
    compat.install("tushare")             # 只顶替一个

`install()` 是**便利**不是保证：已经 `import yfinance` 过的模块持有的是旧对象，
顶替对它无效。所以正路仍然是改 import；顶替只用于"这一层代码我碰不到"的场合。
"""
from __future__ import annotations

import sys

from . import akshare, tushare, yfinance

#: 顶替名 → 垫片模块。
MODULES = {"yfinance": yfinance, "tushare": tushare, "akshare": akshare}

__all__ = ["yfinance", "tushare", "akshare", "MODULES", "install", "uninstall"]


def install(*names: str) -> list[str]:
    """把垫片注册进 `sys.modules`。不给名字 = 三个都顶替。返回实际顶替了哪些。"""
    targets = list(names) or list(MODULES)
    done: list[str] = []
    for n in targets:
        mod = MODULES.get(n)
        if mod is None:
            raise KeyError(f"没有 {n!r} 的兼容层；可选 {sorted(MODULES)}")
        sys.modules[n] = mod
        done.append(n)
    return done


def uninstall(*names: str) -> list[str]:
    """撤销 `install()`（测试用）。"""
    targets = list(names) or list(MODULES)
    done: list[str] = []
    for n in targets:
        if sys.modules.get(n) is MODULES.get(n):
            del sys.modules[n]
            done.append(n)
    return done
