"""QuantAgent 的数据层替换（`integrations/README.md` §1③ 的主要工作量）。

**为什么不是一句 `compat.install()` 就完了** —— 这个上游有**三条**原生取数路径，
而垫片的 akshare 层只覆盖其中一条的一部分：

| 上游路径 | 触发条件 | 我们怎么处理 |
| --- | --- | --- |
| `baostock`（行情首选） | `HAS_BAOSTOCK` | 镜像里**不装** baostock → `HAS_BAOSTOCK=False`，结构性关闭 |
| `pytdx`（指数首选） | `HAS_PYTDX` | 镜像里**不装** pytdx → `HAS_PYTDX=False`，结构性关闭 |
| `akshare`（兜底） | `HAS_AKSHARE` | 装**垫片**，并在这里补上垫片没有的那两个函数 |

第三条还有一个坑：上游调的是 `ak.stock_zh_a_daily`，而垫片实现的是
`ak.stock_zh_a_hist`。垫片的模块级 `__getattr__` 对没实现的名字返回一个抛 `NoData`
的可调用对象（fail-closed，为的是不让上游用 `hasattr` 探测后静默换源），
而上游那一行外面包着 `except Exception: return pd.DataFrame()` ——
于是**表现是「取到 0 条」，不是报错**。这正是 §3.4 说的那种无声失效。

**上游内核一个字节没改**：本模块把自己挂到 `sys.modules["akshare"]`，
上游 `import akshare as ak` 拿到的就是它（README §1③ 的 (d) 路子，monkeypatch）。
"""
import sys
import types

import pandas as pd

import genebench_client as gb
from genebench_client.compat import akshare as _shim

#: 复权口径由**题面**决定，glue 启动时设。
#: 上游 `_akshare_stock_daily()` 调 `ak.stock_zh_a_daily` 时**不传 adjust**
#: （它的 `adjust` 形参只在 baostock 分支上用），真 akshare 的默认是"不复权"。
#: 题面声明 `adjust=post` 时照上游原样跑会静默产出一份口径不同的价格 ——
#: 所以口径在这一层显式钉住，并写进 README 的「已知偏离」。
ADJUST = ""

_ADJUST_TO_AK = {"post": "hfq", "pre": "qfq", "none": "", "": ""}


def set_adjust(declared: str) -> None:
    """题面的 `adjust` 接口值 → akshare 的 adjust 记法。认不出来就抛，不回落。"""
    global ADJUST
    if declared not in _ADJUST_TO_AK:
        raise SystemExit(f"题面声明 adjust={declared!r}，本接入只认 {sorted(_ADJUST_TO_AK)}；**不回落不复权**")
    ADJUST = _ADJUST_TO_AK[declared]


def stock_zh_a_daily(symbol: str = "", start_date: str = "", end_date: str = "",
                     adjust: str = None, **kw) -> pd.DataFrame:
    """垫片没有的那个函数，按上游的调用形状补上。

    上游传的 `symbol` 是 `sh600519` / `sz000001`；日期是紧凑写法 `YYYYMMDD`。
    返回的列名照 akshare 的 `stock_zh_a_daily`（英文列），因为上游按
    `{"date","open","high","low","close","volume"}` 这个集合核列。
    """
    out = _shim.stock_zh_a_hist(
        symbol=symbol, period="daily", start_date=start_date, end_date=end_date,
        adjust=ADJUST if adjust is None else adjust, **kw)
    if out.empty:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "amount"])
    return pd.DataFrame({
        "date": out["日期"],
        "open": out["开盘"], "high": out["最高"], "low": out["最低"], "close": out["收盘"],
        # 垫片按 akshare 原生口径把成交量换算成「手」；上游只做透传，不再换算。
        "volume": out["成交量"], "amount": out["成交额"],
    })


def install() -> types.ModuleType:
    """把这个门面挂成 `akshare`，返回挂上去的模块。"""
    mod = types.ModuleType("akshare")
    mod.stock_zh_a_daily = stock_zh_a_daily
    # 其余名字一律转给垫片 —— 包括它的 fail-closed `__getattr__`，
    # 这样上游走到任何**我们没想到**的接口时，拿到的是一条留痕的 NoData，
    # 而不是「这个接口不存在，换一条原生数据源」。
    mod.__getattr__ = lambda name: getattr(_shim, name)
    sys.modules["akshare"] = mod
    return mod


def gateway_client():
    return gb.client()
