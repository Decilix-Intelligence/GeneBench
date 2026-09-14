# -*- coding: utf-8 -*-
"""``tushare`` 兼容层。

用法::

    from genebench_client.compat import tushare as ts
    pro = ts.pro_api()                                  # token 收下但**不用**
    df  = pro.daily(ts_code="600000.SH", start_date="20260601", end_date="20260630")

单位：**必须换算，不能直接透传**（实证结论，不是查文档）
--------------------------------------------------------
湖里的 ``daily`` 已被 platform 流水线归一过 —— ``volume`` 是**股**、``amount`` 是**元**
（`ops/tickets.md:2457`、`ops/data_cards/qlib_provider.md`）。
2026-09-06 在生产网关上复核：``600000.SH @ 2026-07-28`` ``close=9.19``、
``volume=102,060,442``、``amount=934,214,852`` → ``amount/volume = 9.15`` ≈ 每股价格。
若 volume 真是"手"，每股价就会是 91.5 —— 差 10 倍，一眼可判。

tushare 原生是 ``vol`` **手**、``amount`` **千元**。所以这里::

    vol    = volume / 100
    amount = amount / 1000

**不换算的后果**是任何换手率/成交额口径静默差 100×/1000×，而没有任何东西会报错。

已知语义差异
------------

====================  ===================================================
接口 / 字段           说明
====================  ===================================================
``daily``             **没有** ``pre_close`` / ``change`` / ``pct_chg`` ——
                      网关不发 `pre_close`（湖里 `stk_limit.pre_close` 全 NULL），
                      拿前一日收盘去减在除权日就是错的，**不现编**。
``stk_limit``         **没有** ``pre_close``；**多一列** ``no_price_limit``：
                      为真时 `up_limit`/`down_limit` 是 null（哨兵编码，
                      本来就没有涨跌停价），**绝不要把哨兵当真实涨停价**。
``index_weight``      **没有** ``weight`` 列 —— 网关 `/universe` 只发 PIT 成分，
                      不发权重。给一列 NaN 会让 `weight.sum()` 静默变 0，
                      所以这里让它 `KeyError`：响的错，不是哑的错。
``suspend_d``         由 `/tradability`（单日）或 `/bars` 的 `status`（区间）派生。
                      ``suspend_type`` 只给 ``'S'``；**不给 ``'R'``**（复牌）——
                      五档 `status` 里没有"复牌"这一档，推出来的会是我们编的。
``trade_cal``         只有 **SSE**。深市沿用 SSE 日历是本项目的约定，不是数据事实。
其余 API              → `NoData` 并在网关 access_log 留痕。
====================  ===================================================
"""
from __future__ import annotations

import functools
from typing import Any, Iterable, Sequence

import pandas as pd

import genebench_client as _gb
from genebench_client import codes as _codes
from genebench_client import nodata as _nd
from genebench_client.errors import MalformedRequest

#: tushare `daily` 的列（本环境能给出的那一部分）。
DAILY_COLUMNS: tuple[str, ...] = ("ts_code", "trade_date", "open", "high", "low",
                                  "close", "vol", "amount")
TRADE_CAL_COLUMNS = ("exchange", "cal_date", "is_open", "pretrade_date")
ADJ_FACTOR_COLUMNS = ("ts_code", "trade_date", "adj_factor")
STK_LIMIT_COLUMNS = ("ts_code", "trade_date", "up_limit", "down_limit", "no_price_limit")
INDEX_WEIGHT_COLUMNS = ("index_code", "con_code", "trade_date")
SUSPEND_D_COLUMNS = ("ts_code", "trade_date", "suspend_timing", "suspend_type")

#: 手 / 千元的换算因子。**写成常量**，别在调用处各乘各的。
SHARES_PER_LOT: int = 100
YUAN_PER_KILOYUAN: int = 1000

#: 指数代码（tushare 写法）→ 网关宇宙名。
INDEX_TO_UNIVERSE: dict[str, str] = {
    "000300.SH": "csi300", "399300.SZ": "csi300",
    "000905.SH": "csi500", "399905.SZ": "csi500",
    "000852.SH": "csi1000", "399852.SZ": "csi1000",
}

#: 明确点名的 NO_DATA 接口（值 = 留痕粗分类）。名单之外的一律 `other`。
NO_DATA_APIS: dict[str, str] = {
    "income": "fundamentals", "balancesheet": "fundamentals",
    "cashflow": "fundamentals", "fina_indicator": "fundamentals",
    "fina_mainbz": "fundamentals", "forecast": "fundamentals",
    "express": "fundamentals", "dividend": "corporate_actions",
    "fina_audit": "fundamentals", "disclosure_date": "fundamentals",
    "moneyflow": "moneyflow", "moneyflow_hsgt": "moneyflow",
    "moneyflow_ind_dc": "moneyflow", "moneyflow_mkt_dc": "moneyflow",
    "hk_hold": "moneyflow", "margin": "moneyflow", "margin_detail": "moneyflow",
    "news": "news", "major_news": "news", "cctv_news": "news",
    "anns_d": "news", "irm_qa_sh": "news", "irm_qa_sz": "news",
    "top10_holders": "holders", "top10_floatholders": "holders",
    "stk_holdernumber": "holders", "stk_holdertrade": "insider",
    "block_trade": "other", "top_list": "other", "top_inst": "other",
    "stock_basic": "other", "namechange": "other", "hs_const": "other",
    "index_daily": "other", "index_dailybasic": "other", "daily_basic": "other",
    "stk_factor": "other", "stk_factor_pro": "other", "ggt_top10": "other",
    "cn_gdp": "macro", "cn_cpi": "macro", "cn_ppi": "macro", "shibor": "macro",
}


def set_token(token: str | None = None) -> None:
    """收下 token 但**不用** —— 本环境不与 tushare 通信。空实现，不抛。"""


def get_token() -> str:
    return ""


def pro_api(token: str | None = None, timeout: int | None = None) -> "DataApi":
    return DataApi()


def pro_bar(*a: Any, **kw: Any):
    """``ts.pro_bar`` 是复权行情的通用入口。本环境请改用 ``pro.daily`` + ``pro.adj_factor``——
    `pro_bar` 的 `adj` / `factors` / `ma` 参数会在垫片里变成一堆我们自己编的口径。"""
    _nd.raise_no_data(_gb.client(), "other", "tushare.pro_bar",
                      hint="改用 pro.daily(...) 与 pro.adj_factor(...) 自行复权")


class DataApi:
    """``ts.pro_api()`` 返回的对象。

    与真 tushare 一样靠 ``__getattr__`` 派发 —— 于是 ``pro.任何名字(...)`` 都可调，
    没实现的在**调用时**抛 `NoData` 并留痕，而不是 `AttributeError`。
    `AttributeError` 会被上游的 `hasattr` 探测吞掉，然后回落到别的数据源。
    """

    # ---------------------------------------------------------- 有数据的六个

    def daily(self, ts_code: str | Iterable[str] = "", trade_date: str = "",
              start_date: str = "", end_date: str = "", fields: str = "",
              as_of: str | None = None, **kw: Any) -> pd.DataFrame:
        cli = _gb.client()
        a = cli._as_of(as_of)
        lo, hi = _range(trade_date, start_date, end_date, a)
        codes = _need_codes(ts_code, "daily")
        bars = cli.bars(codes, lo, hi,
                        fields=["open", "high", "low", "close", "volume", "amount"],
                        as_of=a)
        if bars.empty:
            return _empty(DAILY_COLUMNS, fields)
        out = pd.DataFrame({
            "ts_code": bars["code"],
            "trade_date": bars["date"].map(_codes.compact_date),
            "open": pd.to_numeric(bars["open"], errors="coerce"),
            "high": pd.to_numeric(bars["high"], errors="coerce"),
            "low": pd.to_numeric(bars["low"], errors="coerce"),
            "close": pd.to_numeric(bars["close"], errors="coerce"),
            "vol": pd.to_numeric(bars["volume"], errors="coerce") / SHARES_PER_LOT,
            "amount": pd.to_numeric(bars["amount"], errors="coerce") / YUAN_PER_KILOYUAN,
        })
        out = out.dropna(subset=["close"])            # 停牌日 tushare 本来就没有行
        return _finish(out, DAILY_COLUMNS, fields)

    def trade_cal(self, exchange: str = "SSE", start_date: str = "", end_date: str = "",
                  is_open: str | int | None = None, fields: str = "",
                  as_of: str | None = None, **kw: Any) -> pd.DataFrame:
        cli = _gb.client()
        a = cli._as_of(as_of)
        if exchange and str(exchange).upper() not in ("SSE", ""):
            raise MalformedRequest(
                f"exchange={exchange!r}：湖内 trade_cal **只有 SSE**。"
                f"深市沿用 SSE 日历是本项目的约定，不是数据事实 —— 不冒充成 SZSE 的日历返回")
        lo = _codes.iso_date(start_date) if start_date else _codes.shift_days(a, -365)
        hi = _codes.iso_date(end_date) if end_date else a
        cal = cli.calendar(lo, hi, as_of=a)
        if cal.empty:
            return _empty(TRADE_CAL_COLUMNS, fields)
        out = pd.DataFrame({
            "exchange": cal["exchange"],
            "cal_date": cal["date"].map(_codes.compact_date),
            "is_open": pd.to_numeric(cal["is_open"], errors="coerce").astype("Int64"),
            "pretrade_date": cal["pretrade_date"].map(
                lambda x: _codes.compact_date(x) if pd.notna(x) and str(x) else None),
        })
        if is_open is not None and str(is_open) != "":
            out = out[out["is_open"] == int(is_open)]
        return _finish(out, TRADE_CAL_COLUMNS, fields, sort=["cal_date"])

    def adj_factor(self, ts_code: str | Iterable[str] = "", trade_date: str = "",
                   start_date: str = "", end_date: str = "", fields: str = "",
                   as_of: str | None = None, **kw: Any) -> pd.DataFrame:
        cli = _gb.client()
        a = cli._as_of(as_of)
        lo, hi = _range(trade_date, start_date, end_date, a)
        adj = cli.adj(_need_codes(ts_code, "adj_factor"), lo, hi, as_of=a)
        if adj.empty:
            return _empty(ADJ_FACTOR_COLUMNS, fields)
        out = pd.DataFrame({
            "ts_code": adj["code"],
            "trade_date": adj["date"].map(_codes.compact_date),
            "adj_factor": pd.to_numeric(adj["adj_factor"], errors="coerce"),
        })
        return _finish(out, ADJ_FACTOR_COLUMNS, fields)

    def stk_limit(self, ts_code: str | Iterable[str] = "", trade_date: str = "",
                  start_date: str = "", end_date: str = "", fields: str = "",
                  as_of: str | None = None, **kw: Any) -> pd.DataFrame:
        cli = _gb.client()
        a = cli._as_of(as_of)
        lo, hi = _range(trade_date, start_date, end_date, a)
        lim = cli.limits(_need_codes(ts_code, "stk_limit"), lo, hi, as_of=a)
        if lim.empty:
            return _empty(STK_LIMIT_COLUMNS, fields)
        out = pd.DataFrame({
            "ts_code": lim["code"],
            "trade_date": lim["date"].map(_codes.compact_date),
            "up_limit": pd.to_numeric(lim["up_limit"], errors="coerce"),
            "down_limit": pd.to_numeric(lim["down_limit"], errors="coerce"),
            "no_price_limit": lim["no_price_limit"].astype(bool),
        })
        return _finish(out, STK_LIMIT_COLUMNS, fields)

    def index_weight(self, index_code: str = "", trade_date: str = "",
                     start_date: str = "", end_date: str = "", fields: str = "",
                     as_of: str | None = None, **kw: Any) -> pd.DataFrame:
        """→ ``/universe``。**没有 `weight` 列**（见模块 docstring）。"""
        cli = _gb.client()
        a = cli._as_of(as_of)
        uni = INDEX_TO_UNIVERSE.get(str(index_code).strip().upper())
        if uni is None:
            raise MalformedRequest(
                f"index_code={index_code!r} 不在本环境的 PIT 宇宙里；"
                f"可选 {sorted(INDEX_TO_UNIVERSE)}（分别对应 csi300/csi500/csi1000）")
        d = _codes.iso_date(trade_date or end_date or start_date or a)
        members = cli.members(uni, d, as_of=a)
        out = pd.DataFrame({"index_code": [str(index_code).upper()] * len(members),
                            "con_code": members,
                            "trade_date": [_codes.compact_date(d)] * len(members)})
        return _finish(out, INDEX_WEIGHT_COLUMNS, fields, sort=["con_code"])

    def suspend_d(self, ts_code: str | Iterable[str] = "", trade_date: str = "",
                  start_date: str = "", end_date: str = "", suspend_type: str = "",
                  fields: str = "", as_of: str | None = None, **kw: Any) -> pd.DataFrame:
        """停牌。``suspend_type`` 只给 ``'S'``（见模块 docstring）。

        * 给了 ``ts_code``：走 ``/bars`` 的 `status`（一次请求覆盖整段区间）；
        * 只给 ``trade_date``：走 ``/universe(all)`` + ``/tradability``（**全市场，
          请求数 ≈ 成分数/300**，注意预算）。
        """
        cli = _gb.client()
        a = cli._as_of(as_of)
        if str(suspend_type).upper() == "R":
            _nd.raise_no_data(cli, "other", "tushare.suspend_d(suspend_type='R')",
                              hint="五档 status 里没有『复牌』这一档，推出来的会是我们编的")
        if ts_code:
            lo, hi = _range(trade_date, start_date, end_date, a)
            bars = cli.bars(_need_codes(ts_code, "suspend_d"), lo, hi,
                            fields=["has_daily"], as_of=a)
            hit = bars[bars["status"].astype(str) == "suspend"] if not bars.empty else bars
        else:
            if not trade_date:
                raise MalformedRequest(
                    "suspend_d 需要 ts_code 或 trade_date —— 无 code 的区间查询会是"
                    "「成分数 × 天数」次请求，这里不替调用方做那个决定")
            d = _codes.iso_date(trade_date)
            members = cli.members("all", d, as_of=a)
            trad = cli.tradability(members, d, as_of=a)
            hit = trad[trad["status"].astype(str) == "suspend"] if not trad.empty else trad
        if hit is None or hit.empty:
            return _empty(SUSPEND_D_COLUMNS, fields)
        out = pd.DataFrame({
            "ts_code": hit["code"].to_numpy(),
            "trade_date": [_codes.compact_date(x) for x in hit["date"]],
            "suspend_timing": [None] * len(hit),
            "suspend_type": ["S"] * len(hit),
        })
        return _finish(out, SUSPEND_D_COLUMNS, fields)

    # ---------------------------------------------------------- 派发

    #: 有实现的 API 名 → 方法。`query()` 与 `__getattr__` 都查它。
    @property
    def _served(self) -> dict[str, Any]:
        return {"daily": self.daily, "trade_cal": self.trade_cal,
                "adj_factor": self.adj_factor, "stk_limit": self.stk_limit,
                "index_weight": self.index_weight, "suspend_d": self.suspend_d}

    def query(self, api_name: str, fields: str = "", **kw: Any) -> pd.DataFrame:
        """``pro.query("daily", ...)`` —— tushare 的通用入口。"""
        fn = self._served.get(str(api_name))
        if fn is None:
            _nd.raise_no_data(_gb.client(),
                              NO_DATA_APIS.get(str(api_name), "other"),
                              f"tushare.pro.{api_name}",
                              **{k: v for k, v in kw.items() if isinstance(v, (str, int))})
        return fn(fields=fields, **kw)

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        return functools.partial(self.query, name)


# --------------------------------------------------------------- 内部


def _need_codes(ts_code: str | Iterable[str], api: str) -> list[str]:
    if not ts_code:
        raise MalformedRequest(
            f"{api} 必须指定 ts_code —— 网关的 `/bars` / `/adj` / `/limits` 都要求至少一个 code；"
            f"全市场取数请自己先取 `index_weight`（→ /universe）拿成分")
    if isinstance(ts_code, str):
        return [x.strip() for x in ts_code.replace(",", " ").split() if x.strip()]
    return [str(x).strip() for x in ts_code if str(x).strip()]


def _range(trade_date: str, start_date: str, end_date: str, as_of: str) -> tuple[str, str]:
    """tushare 的三种日期入参 → 网关的**闭区间**。tushare 的 end_date 是**闭**的。"""
    if trade_date:
        d = _codes.iso_date(trade_date)
        return d, d
    lo = _codes.iso_date(start_date) if start_date else _codes.shift_days(as_of, -29)
    hi = _codes.iso_date(end_date) if end_date else as_of
    return lo, hi


def _wanted(fields: str, served: Sequence[str]) -> list[str]:
    if not fields or not str(fields).strip():
        return list(served)
    want = [x.strip() for x in str(fields).split(",") if x.strip()]
    unknown = [x for x in want if x not in served]
    if unknown:
        raise MalformedRequest(
            f"fields 里有本环境不服务的列 {unknown}；服务集 {list(served)}。"
            f"**不静默丢掉** —— 悄悄跳过一个拼错的列名，调用方拿到的仍是一份"
            f"「看起来成功」的结果")
    return want


def _empty(served: Sequence[str], fields: str) -> pd.DataFrame:
    return pd.DataFrame(columns=_wanted(fields, served))


def _finish(df: pd.DataFrame, served: Sequence[str], fields: str,
            sort: Sequence[str] | None = None) -> pd.DataFrame:
    keys = list(sort) if sort else ["ts_code", "trade_date"]
    keys = [k for k in keys if k in df.columns]
    if keys:
        df = df.sort_values(keys)
    return df[_wanted(fields, served)].reset_index(drop=True)


def __getattr__(name: str):
    """模块级 fail-closed：``ts.<没实现的东西>`` 是一个抛 `NoData` 的可调用对象。"""
    if name.startswith("_"):
        raise AttributeError(name)

    def _call(*a: Any, **kw: Any):
        _nd.raise_no_data(_gb.client(), NO_DATA_APIS.get(name, "other"),
                          f"tushare.{name}")
    _call.__name__ = name
    return _call
