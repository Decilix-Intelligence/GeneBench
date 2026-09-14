# -*- coding: utf-8 -*-
"""``akshare`` 兼容层（常用子集）。

用法::

    from genebench_client.compat import akshare as ak
    df  = ak.stock_zh_a_hist("600000", start_date="20260601", end_date="20260630", adjust="qfq")
    cal = ak.tool_trade_date_hist_sina()
    spot = ak.stock_zh_a_spot()          # as_of 当日的"实时"快照

单位（与 akshare 文档口径一致）
------------------------------
``成交量`` **手**（网关给的是股，这里 /100）、``成交额`` **元**（网关本来就是元，原样）。
湖里 ``volume`` 是股、``amount`` 是元的实证依据见 `compat.tushare` 的模块 docstring。

已知语义差异
------------

==========================  =============================================
接口 / 字段                 说明
==========================  =============================================
``stock_zh_a_hist``         **没有** ``振幅`` / ``涨跌幅`` / ``涨跌额`` / ``换手率`` ——
                            它们要 ``pre_close`` 与流通股本，网关都不发。
                            **不现编**：拿前一日收盘去减，在除权日就是错的。
``period``                  只支持 ``daily``。``weekly`` / ``monthly`` 直接拒 ——
                            重采样出来的口径是我们编的，不是数据。
``start_date`` 下限         早于 ``1990-12-19``（湖起点）的部分被截断。
``end_date``                **显式给的不截回 as_of** —— 越界要由网关判成 403 并落日志，
                            垫片自己截会让那次前视尝试在 access_log 上消失。
                            只有签名里的哨兵默认值 ``20500101`` 当作"没给"。
``stock_zh_a_spot``         "实时" = **as_of 当日**。列只有网关能给的那几个
                            （没有 ``名称`` / ``涨跌幅`` / ``市盈率``）。
                            ⚠️ 它要先取 ``/universe(all)``（约 5,500 只）再分批取
                            ``/bars``，**约 20 次网关请求**，注意预算。
``stock_news_em`` 等        → `NoData` 并在网关 access_log 留痕。
==========================  =============================================
"""
from __future__ import annotations

import datetime as _dt
from typing import Any

import pandas as pd

import genebench_client as _gb
from genebench_client import codes as _codes
from genebench_client import nodata as _nd
from genebench_client.errors import MalformedRequest

#: 湖里日线的起点。早于它的请求会去要根本不存在的年分区。
LAKE_START: str = "1990-12-19"

#: ``stock_zh_a_hist`` 能给出的列（**顺序照 akshare**）。
HIST_COLUMNS: tuple[str, ...] = ("日期", "股票代码", "开盘", "收盘", "最高", "最低",
                                 "成交量", "成交额")
#: akshare 有、本环境给不出的列（在 README 与 docstring 里点名，不静默省略）。
HIST_MISSING: tuple[str, ...] = ("振幅", "涨跌幅", "涨跌额", "换手率")

SPOT_COLUMNS: tuple[str, ...] = ("代码", "今开", "最高", "最低", "最新价",
                                 "成交量", "成交额")

SHARES_PER_LOT: int = 100

#: 明确点名的 NO_DATA 接口（值 = 留痕粗分类）。
NO_DATA_APIS: dict[str, str] = {
    "stock_news_em": "news", "stock_news_main_cx": "news",
    "news_cctv": "news", "news_economic_baidu": "news", "stock_zh_a_alerts_cls": "news",
    "stock_financial_abstract": "fundamentals",
    "stock_financial_report_sina": "fundamentals",
    "stock_financial_analysis_indicator": "fundamentals",
    "stock_financial_abstract_ths": "fundamentals",
    "stock_profit_sheet_by_report_em": "fundamentals",
    "stock_balance_sheet_by_report_em": "fundamentals",
    "stock_cash_flow_sheet_by_report_em": "fundamentals",
    "stock_yjbb_em": "fundamentals", "stock_a_indicator_lg": "fundamentals",
    "stock_individual_fund_flow": "moneyflow",
    "stock_individual_fund_flow_rank": "moneyflow",
    "stock_market_fund_flow": "moneyflow", "stock_sector_fund_flow_rank": "moneyflow",
    "stock_hsgt_hold_stock_em": "moneyflow", "stock_margin_sse": "moneyflow",
    "stock_hold_num_cninfo": "holders", "stock_gdfx_top_10_em": "holders",
    "stock_share_hold_change_sse": "insider",
    "stock_index_pe_lg": "macro", "macro_china_gdp": "macro", "macro_china_cpi": "macro",
    "stock_individual_info_em": "other", "stock_info_a_code_name": "other",
    "stock_zh_index_daily": "other", "stock_board_industry_name_em": "other",
}


def _period_ok(period: str) -> None:
    if str(period).lower() not in ("daily", "1d", "d", ""):
        raise MalformedRequest(
            f"period={period!r}：本环境只服务 **daily**。周/月线要靠重采样，"
            f"而重采样的口径（用哪天的开盘、跨停牌怎么算）是我们编的，不是数据")


#: akshare 函数签名里写死的两个哨兵默认值。**只有它们**被当作"没给日期"。
SENTINEL_START: str = "19700101"
SENTINEL_END: str = "20500101"


def _clamp(start_date: str, end_date: str, as_of: str) -> tuple[str, str]:
    """akshare 的日期入参 → 网关的闭区间。

    ⚠️ **显式给的 end_date 不截回 as_of。** 第一版写了 `hi = min(hi, as_of)`，
    后果是一次前视尝试被垫片自己截成合法请求、根本没到网关 —— access_log 里
    什么都没有，而卡 5.1 的前视结算只认 access_log。越界必须由**网关**判、
    落一条 403，垫片只负责把 `LookaheadDenied` 抛给调用方。

    只有 akshare 签名里那两个**哨兵默认值**（`19700101` / `20500101`）被当作
    "调用方没给日期"：那不是越界意图，那是库的默认参数。
    """
    lo_raw = str(start_date or "").strip()
    hi_raw = str(end_date or "").strip()
    lo = LAKE_START if (not lo_raw or lo_raw == SENTINEL_START) else _codes.iso_date(lo_raw)
    hi = as_of if (not hi_raw or hi_raw == SENTINEL_END) else _codes.iso_date(hi_raw)
    lo = max(lo, LAKE_START)          # 早于湖起点的部分不存在，不是越界，可以截
    if lo > hi:
        raise MalformedRequest(
            f"start_date={lo} 晚于 end_date={hi} —— 空区间不是零行，是写反了")
    return lo, hi


def stock_zh_a_hist(symbol: str = "000001", period: str = "daily",
                    start_date: str = "", end_date: str = "", adjust: str = "",
                    timeout: float | None = None, as_of: str | None = None,
                    **kw: Any) -> pd.DataFrame:
    """A 股日线。``adjust``：``""`` 不复权 / ``"qfq"`` 前复权 / ``"hfq"`` 后复权。

    复权口径::

        hfq = price * adj_factor
        qfq = price * adj_factor / adj_factor(窗口内 as_of 之前最后一天)

    **前复权基准是窗口内最后一个可见因子**，不是"最新因子"—— 后者要读 as_of 之后的数据。
    """
    _period_ok(period)
    adj_mode = str(adjust or "").lower()
    if adj_mode not in ("", "qfq", "hfq"):
        raise MalformedRequest(f"adjust={adjust!r}；可选 ''、'qfq'、'hfq'")
    cli = _gb.client()
    a = cli._as_of(as_of)
    lo, hi = _clamp(start_date, end_date, a)
    code = _codes.to_lake(symbol)
    bars = cli.bars([code], lo, hi,
                    fields=["open", "high", "low", "close", "volume", "amount"], as_of=a)
    if bars.empty:
        return pd.DataFrame(columns=list(HIST_COLUMNS))
    px = bars.dropna(subset=["close"]).copy()
    for col in ("open", "high", "low", "close", "volume", "amount"):
        px[col] = pd.to_numeric(px[col], errors="coerce")
    if adj_mode:
        adj = cli.adj([code], lo, hi, as_of=a)
        if adj.empty:
            raise MalformedRequest(
                f"adjust={adj_mode!r} 但 /adj 在 {lo}..{hi} 没有 {code} 的因子 —— "
                f"**不退回不复权**：那会静默返回一份口径不同的价格")
        adj = adj.copy()
        adj["adj_factor"] = pd.to_numeric(adj["adj_factor"], errors="coerce")
        px = px.merge(adj[["code", "date", "adj_factor"]], on=["code", "date"], how="left")
        px["adj_factor"] = px["adj_factor"].ffill().bfill()
        base = 1.0 if adj_mode == "hfq" else float(px["adj_factor"].iloc[-1])
        if not base or base != base:
            raise MalformedRequest(f"复权基准取不到（{code} {lo}..{hi}）")
        ratio = px["adj_factor"] / base
        for col in ("open", "high", "low", "close"):
            px[col] = px[col] * ratio
    out = pd.DataFrame({
        "日期": px["date"].astype(str),
        "股票代码": px["code"].map(_codes.to_akshare),
        "开盘": px["open"].round(4),
        "收盘": px["close"].round(4),
        "最高": px["high"].round(4),
        "最低": px["low"].round(4),
        "成交量": (px["volume"] / SHARES_PER_LOT).round(0),
        "成交额": px["amount"].round(2),
    })
    return out.reset_index(drop=True)


def tool_trade_date_hist_sina(as_of: str | None = None, **kw: Any) -> pd.DataFrame:
    """交易日历。列 ``trade_date``（``datetime.date``），**只到 as_of 当日**。

    ⚠️ 只有 **SSE** 日历（湖内没有第二个交易所）。
    """
    cli = _gb.client()
    a = cli._as_of(as_of)
    days = cli.trading_days(LAKE_START, a, as_of=a)
    return pd.DataFrame({"trade_date": [_dt.date.fromisoformat(d) for d in days]})


def stock_zh_a_spot(as_of: str | None = None, universe: str = "all",
                    **kw: Any) -> pd.DataFrame:
    """"实时" 行情 = **as_of 当日**的全市场快照。

    ⚠️ 约 20 次网关请求（先 ``/universe(all)`` 再分批 ``/bars``）。
    列只有网关能给的那几个 —— 没有 ``名称`` / ``涨跌幅`` / ``市盈率``（见模块 docstring）。
    """
    cli = _gb.client()
    a = cli._as_of(as_of)
    members = cli.members(universe, a, as_of=a)
    if not members:
        return pd.DataFrame(columns=list(SPOT_COLUMNS))
    bars = cli.bars(members, a, a,
                    fields=["open", "high", "low", "close", "volume", "amount"], as_of=a)
    if bars.empty:
        return pd.DataFrame(columns=list(SPOT_COLUMNS))
    px = bars.dropna(subset=["close"]).copy()
    for col in ("open", "high", "low", "close", "volume", "amount"):
        px[col] = pd.to_numeric(px[col], errors="coerce")
    out = pd.DataFrame({
        "代码": px["code"].map(_codes.to_akshare),
        "今开": px["open"], "最高": px["high"], "最低": px["low"],
        "最新价": px["close"],
        "成交量": px["volume"] / SHARES_PER_LOT,
        "成交额": px["amount"],
    })
    return out.sort_values("代码").reset_index(drop=True)


def stock_zh_a_spot_em(**kw: Any) -> pd.DataFrame:
    """东财版的同一件事。"""
    return stock_zh_a_spot(**kw)


def __getattr__(name: str):
    """模块级 fail-closed：``ak.<没实现的东西>`` 是一个抛 `NoData` 的可调用对象。

    返回可调用对象而不是当场抛，是为了让 ``hasattr(ak, "x")`` 仍然为真 ——
    上游拿它做能力探测时，我们要的是"调下去拿到 NO_DATA 并留痕"，
    而不是"以为没有这个接口，于是换一条原生数据源"。
    """
    if name.startswith("_"):
        raise AttributeError(name)

    def _call(*a: Any, **kw: Any):
        _nd.raise_no_data(_gb.client(), NO_DATA_APIS.get(name, "other"),
                          f"akshare.{name}")
    _call.__name__ = name
    return _call
