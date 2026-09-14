# -*- coding: utf-8 -*-
"""``yfinance`` 兼容层。

用法::

    from genebench_client.compat import yfinance as yf
    df = yf.download(["600000.SS", "000001.SZ"], start="2026-06-01", end="2026-06-30")
    h  = yf.Ticker("600000.SS").history(start="2026-06-01", end="2026-06-30")

已知语义差异（**都是必要偏离，不是没做完**）
--------------------------------------------

============  ==========================================================
差异          为什么
============  ==========================================================
``Adj Close`` yfinance 的 Adj Close 是相对**今天**的后复权基准。as-of 世界里
              没有"今天"——把冻结线之后的因子拿来当基准就是前视。这里的基准是
              **窗口内 as_of 当日（含）之前最后一个 `adj_factor`**，逐票各算各的。
              公式写在 `_adjust_ratio` 上，别在别处再写一份。
``end`` 右开  与 yfinance 一致：``end="2026-06-30"`` **不含** 06-30。
              网关的 ``end_date`` 是**闭区间**，所以这里减一天。
              这一条最容易被漏，漏了就少/多一根 K 线，而没有任何东西会报错。
无默认 period 都不给 ``start``/``period`` 时取 ``period="1mo"``（与
              ``Ticker.history`` 的默认一致），**不是** yfinance ``download``
              事实上的 "max" —— 在 as-of 世界里 max 会拉几十年、直接撞
              网关的 200,000 行上限（422），表现成「参数写错了」。
无 Dividends  网关只发合成的 ``adj_factor``，**没有**分红/拆股明细。
无 Splits     **不编两列 0.0** —— 那等于宣称"这段时间没有分红"，是编数据。
停牌日        无行情的交易日不出现在结果里（与 yfinance 一致）。要停牌语义请用
              ``genebench_client.client().bars(..., fields=[..., "status"])``。
``.news`` 等  → `NoData`，且在网关 access_log 留痕。见 `genebench_client.nodata`。
============  ==========================================================
"""
from __future__ import annotations

from typing import Any, Iterable, Sequence

import pandas as pd

import genebench_client as _gb
from genebench_client import codes as _codes
from genebench_client import nodata as _nd
from genebench_client.errors import MalformedRequest

#: 从网关 `/bars` 取的列（**显式传** `fields`，让 S3 的读取集探针有字段粒度）。
_GATEWAY_FIELDS: tuple[str, ...] = ("open", "high", "low", "close", "volume")

#: 网关列名 → yfinance 列名。
_RENAME = {"open": "Open", "high": "High", "low": "Low", "close": "Close",
           "volume": "Volume"}
#: yfinance 的列序（`auto_adjust=False` 时 `Adj Close` 插在 Close 与 Volume 之间）。
_ORDER_RAW = ("Open", "High", "Low", "Close", "Adj Close", "Volume")
_ORDER_ADJ = ("Open", "High", "Low", "Close", "Volume")

#: ``period`` → 往前推多少自然日。``max`` 不支持（见模块 docstring）。
_PERIODS = {"1d": 1, "5d": 5, "1wk": 7, "1mo": 30, "3mo": 91, "6mo": 182,
            "1y": 365, "2y": 730, "5y": 1826, "10y": 3652}

#: 这些属性/方法一律 NO_DATA（值 = 留痕用的粗分类）。
_NO_DATA_ATTRS: dict[str, str] = {
    "news": "news", "get_news": "news",
    "info": "fundamentals", "get_info": "fundamentals",
    "fast_info": "fundamentals", "basic_info": "fundamentals",
    "financials": "fundamentals", "quarterly_financials": "fundamentals",
    "income_stmt": "fundamentals", "quarterly_income_stmt": "fundamentals",
    "balance_sheet": "fundamentals", "quarterly_balance_sheet": "fundamentals",
    "cashflow": "fundamentals", "quarterly_cashflow": "fundamentals",
    "earnings": "fundamentals", "quarterly_earnings": "fundamentals",
    "get_financials": "fundamentals", "get_balance_sheet": "fundamentals",
    "get_cashflow": "fundamentals", "get_income_stmt": "fundamentals",
    "get_earnings": "fundamentals",
    "dividends": "corporate_actions", "splits": "corporate_actions",
    "actions": "corporate_actions", "capital_gains": "corporate_actions",
    "get_actions": "corporate_actions", "get_dividends": "corporate_actions",
    "get_splits": "corporate_actions",
    "major_holders": "holders", "institutional_holders": "holders",
    "mutualfund_holders": "holders", "insider_transactions": "insider",
    "insider_purchases": "insider", "insider_roster_holders": "insider",
    "recommendations": "sentiment", "recommendations_summary": "sentiment",
    "upgrades_downgrades": "sentiment", "analyst_price_targets": "sentiment",
    "sustainability": "other", "calendar": "other", "earnings_dates": "other",
    "option_chain": "other", "options": "other", "shares_full": "other",
}


# --------------------------------------------------------------- 内部


def _tickers(t: str | Iterable[str]) -> list[str]:
    if isinstance(t, str):
        parts = [x for x in t.replace(",", " ").split() if x]
    else:
        parts = [str(x).strip() for x in t if str(x).strip()]
    if not parts:
        raise MalformedRequest("tickers 为空")
    return parts


def _window(start, end, period, as_of: str) -> tuple[str, str]:
    """→ 网关用的**闭区间** ``(start_date, end_date)``。

    ``end`` 右开（yfinance 语义）→ 网关闭区间要减一天。
    ``end`` 缺省 = as_of 当日（**含**），因为 as_of 是这个世界的"今天"。
    """
    hi = _codes.shift_days(end, -1) if end is not None else as_of
    # ⚠️ **给了 end 就原样往网关送，哪怕它越过 as_of。**
    # 第一版在这里写了 `hi = min(hi, as_of)`。那一行的后果是：一次前视尝试被垫片
    # 自己截回合法窗口，请求根本没到网关 —— access_log 里**什么都没有**，而
    # 卡 5.1 的前视结算只认 access_log、不采信自报。于是「它试图看未来」与
    # 「它没试过」不可区分，探针全绿而 as-of 强制已经形同虚设。
    # 越界必须由**网关**判、落一条 403，垫片只负责把 `LookaheadDenied` 抛给调用方。
    # 只有 end 缺省（"到今天为止"）时才用 as_of —— 那不是越界，那是"今天"的定义。
    if start is not None:
        lo = _codes.iso_date(start)
    else:
        p = str(period or "1mo").lower()
        if p not in _PERIODS:
            raise MalformedRequest(
                f"period={period!r} 不支持；可选 {sorted(_PERIODS)}。"
                f"**`max` 不支持**：as-of 世界里它会拉几十年、直接撞网关 200,000 行上限")
        lo = _codes.shift_days(hi, -_PERIODS[p] + 1)
    if lo > hi:
        raise MalformedRequest(f"start={lo} 晚于 end={hi}（end 右开，已减一天）")
    return lo, hi


def _adjust_ratio(adj: pd.DataFrame) -> pd.DataFrame:
    """逐票算复权比 ``ratio = adj_factor / adj_factor(窗口内最后一天)``。

    **基准是窗口内最后一个可见因子**，不是"最新因子" —— 后者要读 as_of 之后的数据。
    输出列：``code`` / ``date`` / ``ratio``。
    """
    if adj.empty:
        return pd.DataFrame(columns=["code", "date", "ratio"])
    a = adj.sort_values(["code", "date"]).copy()
    a["adj_factor"] = pd.to_numeric(a["adj_factor"], errors="coerce")
    base = a.groupby("code")["adj_factor"].transform("last")
    a["ratio"] = a["adj_factor"] / base.where(base > 0)
    return a[["code", "date", "ratio"]]


def _long_frame(codes: list[str], lo: str, hi: str, as_of: str | None,
                auto_adjust: bool) -> pd.DataFrame:
    """→ 长表 ``code/date/Open/High/Low/Close/[Adj Close]/Volume``。"""
    cli = _gb.client()
    a = cli._as_of(as_of)
    bars = cli.bars(codes, lo, hi, fields=list(_GATEWAY_FIELDS), as_of=a)
    if bars.empty:
        return pd.DataFrame(columns=["code", "date", *_ORDER_RAW])
    df = bars.rename(columns=_RENAME)
    for col in ("Open", "High", "Low", "Close", "Volume"):
        df[col] = pd.to_numeric(df.get(col), errors="coerce")
    df = df.dropna(subset=["Close"])                 # 停牌/无行情日：与 yfinance 一致，不出现
    ratio = _adjust_ratio(cli.adj(codes, lo, hi, as_of=a))
    df = df.merge(ratio, on=["code", "date"], how="left")
    df["ratio"] = pd.to_numeric(df["ratio"], errors="coerce").fillna(1.0)
    if auto_adjust:
        for col in ("Open", "High", "Low", "Close"):
            df[col] = df[col] * df["ratio"]
    else:
        df["Adj Close"] = df["Close"] * df["ratio"]
    keep = ["code", "date", *(_ORDER_ADJ if auto_adjust else _ORDER_RAW)]
    return df[[c for c in keep if c in df.columns]].sort_values(["code", "date"])


def _wide(long: pd.DataFrame, tickers: list[str], auto_adjust: bool,
          group_by: str) -> pd.DataFrame:
    """长表 → yfinance 的宽表。单票时列是平的；多票时列是 `MultiIndex`。"""
    order = [c for c in (_ORDER_ADJ if auto_adjust else _ORDER_RAW) if c in long.columns]
    if long.empty:
        idx = pd.DatetimeIndex([], name="Date")
        if len(tickers) == 1:
            return pd.DataFrame(index=idx, columns=list(order))
        cols = pd.MultiIndex.from_product([order, tickers], names=["Price", "Ticker"])
        return pd.DataFrame(index=idx, columns=cols)
    long = long.copy()
    long["Date"] = pd.to_datetime(long["date"])
    long["Ticker"] = long["code"].map(_codes.to_yfinance)
    if len(tickers) == 1:
        out = long.set_index("Date")[order]
        out.index.name = "Date"
        return out
    wide = long.pivot(index="Date", columns="Ticker", values=order)
    wide = wide.reindex(columns=pd.MultiIndex.from_product([order, tickers]))
    wide.columns = wide.columns.set_names(["Price", "Ticker"])
    if group_by in ("ticker", "Ticker"):
        wide = wide.swaplevel(axis=1).sort_index(axis=1, level=0)
        wide.columns = wide.columns.set_names(["Ticker", "Price"])
    wide.index.name = "Date"
    return wide


# --------------------------------------------------------------- 公开面


def download(tickers: str | Iterable[str], start=None, end=None, *,
             interval: str = "1d", period: str | None = None,
             auto_adjust: bool = True, group_by: str = "column",
             as_of: str | None = None, progress: bool = False,
             **kwargs: Any) -> pd.DataFrame:
    """``yfinance.download`` 的形状。

    支持的参数之外的一律**忽略**（与 yfinance 一样宽松），
    但 ``interval`` 必须是日线 —— 网关只有日频，接受一个被忽略的 `interval`
    等于让调用方以为分钟线生效了。
    """
    if str(interval).lower() not in ("1d", "1day", "d", "daily"):
        raise MalformedRequest(
            f"interval={interval!r}：本环境只有**日频**。不静默降级成日线——"
            f"那会让调用方以为自己拿到了分钟线")
    tks = _tickers(tickers)
    codes = [_codes.to_lake(t) for t in tks]
    a = _gb.client()._as_of(as_of)
    lo, hi = _window(start, end, period, a)
    long = _long_frame(codes, lo, hi, a, bool(auto_adjust))
    return _wide(long, tks, bool(auto_adjust), group_by)


class Ticker:
    """``yfinance.Ticker`` 的形状。**只有 `history` 有数据**，其余一律 `NoData`。"""

    def __init__(self, ticker: str, session: Any = None) -> None:
        self.ticker = str(ticker).strip()
        self._code = _codes.to_lake(self.ticker)

    def __repr__(self) -> str:                       # pragma: no cover
        return f"genebench_client.compat.yfinance.Ticker object <{self.ticker}>"

    def history(self, period: str | None = None, interval: str = "1d",
                start=None, end=None, *, auto_adjust: bool = True,
                as_of: str | None = None, **kwargs: Any) -> pd.DataFrame:
        """单票 K 线。列 ``Open High Low Close [Adj Close] Volume``，索引 ``Date``。

        **没有 `Dividends` / `Stock Splits` 两列** —— 网关只发合成因子，
        编两列 0.0 等于宣称"这段时间没有分红"。
        """
        if str(interval).lower() not in ("1d", "1day", "d", "daily"):
            raise MalformedRequest(f"interval={interval!r}：本环境只有日频")
        a = _gb.client()._as_of(as_of)
        lo, hi = _window(start, end, period, a)
        long = _long_frame([self._code], lo, hi, a, bool(auto_adjust))
        return _wide(long, [self.ticker], bool(auto_adjust), "column")

    def get_history_metadata(self, **kw) -> dict:
        return {"symbol": self.ticker, "currency": "CNY", "exchangeName": "SSE/SZSE/BSE",
                "timezone": "Asia/Shanghai", "instrumentType": "EQUITY",
                "source": "genebench-gateway"}

    def __getattr__(self, name: str):
        """`.news` / `.financials` / `.get_info()` … → `NoData` **并留痕**。

        未知属性也走这条（fail-closed）：一个我们没实现的 yfinance 接口，
        正确答案是"本环境没有这类数据"，不是 `AttributeError`。
        `AttributeError` 会被上游的 `hasattr` 静默吞掉，然后回落到**别的数据源**。
        """
        if name.startswith("__") or name.startswith("_"):
            raise AttributeError(name)
        kind = _NO_DATA_ATTRS.get(name, "other")
        api = f"yfinance.Ticker.{name}"
        if name.startswith("get_") or name in ("option_chain",):
            def _call(*a: Any, **kw: Any):
                _nd.raise_no_data(_gb.client(), kind, api, code=self._code)
            return _call
        _nd.raise_no_data(_gb.client(), kind, api, code=self._code)


class Tickers:
    """``yfinance.Tickers`` 的形状：``.tickers`` 是 `{符号: Ticker}`。"""

    def __init__(self, tickers: str | Iterable[str], session: Any = None) -> None:
        self.symbols = _tickers(tickers)
        self.tickers = {s: Ticker(s) for s in self.symbols}

    def history(self, **kw) -> pd.DataFrame:
        return download(self.symbols, **kw)


def __getattr__(name: str):
    """模块级 fail-closed：``yf.<没实现的东西>`` 返回一个抛 `NoData` 的可调用对象。

    返回可调用对象而不是当场抛，是为了让 ``hasattr(yf, "x")`` 仍然为真 ——
    上游拿 `hasattr` 做能力探测时，我们要的是"它调下去然后拿到 NO_DATA 并留痕"，
    而不是"它以为没有这个接口，于是换一条原生数据源"。
    """
    if name.startswith("_"):
        raise AttributeError(name)

    def _call(*a: Any, **kw: Any):
        _nd.raise_no_data(_gb.client(), _NO_DATA_ATTRS.get(name, "other"),
                          f"yfinance.{name}")
    _call.__name__ = name
    return _call
