# -*- coding: utf-8 -*-
"""代码写法与日期写法的互转。

**归一在取数边界做一次**，不在每个兼容层里各写一份 —— 各写一份必然漂，
而漂的表现是「merge 出一张全 NaN 的表，且 merge 本身不报错」。

四种写法，本包内部一律用**湖写法**：

| 写法 | 样子 | 谁用 |
| --- | --- | --- |
| 湖 / tushare | ``600000.SH`` ``000001.SZ`` ``430047.BJ`` | 网关、`compat.tushare` |
| yfinance | ``600000.SS`` ``000001.SZ`` ``430047.BJ`` | `compat.yfinance`（**沪市后缀是 `.SS` 不是 `.SH`**）|
| akshare | ``600000`` | `compat.akshare`（**裸六位，没有后缀**）|
| qlib / 面板 | ``SH600000`` | 少数面板产物 |

裸六位反推交易所的规则（**先判 `920` 再判首位 `9`**：北交所 920xxx 与
沪市 B 股 900xxx 都以 9 开头，判反了就把北交所的票发去了上交所）：

* ``6`` / ``9``（非 920）→ ``SH``（含 688 科创、900 B 股）
* ``0`` / ``2`` / ``3`` → ``SZ``（含 200 B 股、300 创业板）
* ``4`` / ``8`` / ``920`` → ``BJ``
"""
from __future__ import annotations

import datetime as _dt
import re

#: 湖写法允许的三个交易所后缀。
MARKETS: tuple[str, ...] = ("SH", "SZ", "BJ")

#: 湖后缀 → yfinance 后缀。**只有沪市不同**。
_LAKE_TO_YF = {"SH": "SS", "SZ": "SZ", "BJ": "BJ"}
#: yfinance 后缀 → 湖后缀。`SH` 也收（有人就是这么写的），但**输出**永远是 `SS`。
_YF_TO_LAKE = {"SS": "SH", "SH": "SH", "SZ": "SZ", "BJ": "BJ"}

_DIGITS6 = re.compile(r"^\d{6}$")
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_COMPACT = re.compile(r"^\d{8}$")


class CodeError(ValueError):
    """代码写法不认识。**抛，不猜** —— 猜错一个市场就是取了另一只票的行情。"""


def infer_market(digits: str) -> str:
    """裸六位 → 交易所后缀。"""
    if not _DIGITS6.fullmatch(digits):
        raise CodeError(f"{digits!r} 不是六位数字代码")
    if digits.startswith("920"):
        return "BJ"                    # 北交所新号段；必须排在首位 `9` 之前
    head = digits[0]
    if head in "69":
        return "SH"
    if head in "023":
        return "SZ"
    if head in "48":
        return "BJ"
    raise CodeError(
        f"{digits!r} 的首位 {head!r} 不在已知 A 股号段（6/9→SH，0/2/3→SZ，4/8/920→BJ）——"
        f"**不猜一个默认市场**：猜错就是取了另一只票的行情")


def to_lake(code: str) -> str:
    """任意写法 → 湖写法 ``600000.SH``。"""
    c = str(code).strip().upper()
    if not c:
        raise CodeError("空代码")
    if "." in c:
        num, _, mkt = c.partition(".")
        if not _DIGITS6.fullmatch(num):
            raise CodeError(f"{code!r}：`.` 左边不是六位数字")
        mkt = _YF_TO_LAKE.get(mkt)
        if mkt is None:
            raise CodeError(f"{code!r}：不认识的交易所后缀（可选 SH/SS/SZ/BJ）")
        return f"{num}.{mkt}"
    if c[:2] in MARKETS and _DIGITS6.fullmatch(c[2:]):
        return f"{c[2:]}.{c[:2]}"                   # SH600000
    if _DIGITS6.fullmatch(c):
        return f"{c}.{infer_market(c)}"
    raise CodeError(
        f"{code!r} 不是已知写法（600000.SH / 600000.SS / SH600000 / 600000）")


def to_yfinance(code: str) -> str:
    """湖写法 → yfinance 写法。**沪市 `.SH` → `.SS`。**"""
    num, _, mkt = to_lake(code).partition(".")
    return f"{num}.{_LAKE_TO_YF[mkt]}"


def to_akshare(code: str) -> str:
    """湖写法 → akshare 的裸六位。"""
    return to_lake(code).partition(".")[0]


def to_panel(code: str) -> str:
    """湖写法 → qlib / 面板写法 ``SH600000``。"""
    num, _, mkt = to_lake(code).partition(".")
    return f"{mkt}{num}"


def iso_date(d) -> str:
    """``20260105`` / ``date`` / ``Timestamp`` → ``2026-01-05``；已是 ISO 的原样返回。

    网关两个端点的日期写法**不同**（`/calendar` 与 `/adj` 给紧凑串，`/bars` 给 ISO）。
    不归一就 merge 得到的是一张全 NaN 的表，而 merge 本身不报错。
    """
    if isinstance(d, (_dt.date, _dt.datetime)):
        return d.strftime("%Y-%m-%d")
    x = str(d).strip()
    if _COMPACT.fullmatch(x):
        return f"{x[:4]}-{x[4:6]}-{x[6:]}"
    if _ISO.fullmatch(x):
        return x
    if len(x) >= 10 and _ISO.fullmatch(x[:10]):
        return x[:10]                                 # 带时分秒的 ISO
    raise CodeError(f"{d!r} 不是可识别的日期（YYYYMMDD 或 YYYY-MM-DD）")


def compact_date(d) -> str:
    """任意写法 → ``20260105``（tushare / akshare 的入参与出参写法）。"""
    return iso_date(d).replace("-", "")


def shift_days(d, days: int) -> str:
    """ISO 日期加减自然日。用于 yfinance 的 **end 右开**换算与 period 换算。"""
    base = _dt.date.fromisoformat(iso_date(d))
    return (base + _dt.timedelta(days=days)).isoformat()
