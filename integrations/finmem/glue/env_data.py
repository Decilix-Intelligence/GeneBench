# -*- coding: utf-8 -*-
"""数据这一头：把 FinMem 的 `env_data.pkl` 就地造出来。

## 替换的是上游的哪个东西

**FinMem 的运行期不取数。** `run.py` 只做一件事：

    with open(market_data_info_path, "rb") as f:
        env_data_pkl = pickle.load(f)
    environment = MarketEnvironment(env_data_pkl=env_data_pkl, ...)

取数全部发生在**离线阶段** `data-pipeline/`（`01_Alpaca_News_API_download.py`、
`01_SEC_API_10k10q_download.py`、`04-data_pipeline.py` 用 yfinance 取价）。
所以这个接入的替换缝**不在运行期的某个函数上，而在那个 pkl 上** ——
`build()` 就是 `data-pipeline/` 的位置。

这带来一个与 TradingAgents 相反的性质：**FinMem 的容器里没有第二条取数路径可走**
（`puppy/` 全树只有两处出网：`chat.py` 的 `httpx.post(end_point)` 与
`embedding.py` 的 OpenAI embeddings，两处都指向边车）。
`ops/test_integration_finmem.py::test_puppy_has_no_market_data_egress` 守这一条。

## pkl 的形状（`environment.py::OneDateRecord` 逐字）

    {date(…): {"price": {sym: float}, "filing_k": {sym: str},
               "filing_q": {sym: str}, "news": {sym: [str, …]}}}

本环境里 `filing_k` / `filing_q` / `news` **恒为空字典** —— 不是"我们没接完"，
是这个基准不提供新闻与 PIT 财报文本。每一类在网关 access_log 上留一次痕
（`genebench_client.nodata.trace`，打一个白名单之外的 `/nodata/<kind>`，
HTTP 中间件照记），**这样「它尝试过要新闻」在数据面上看得见**。

价格走垫片的 `compat.yfinance`（FinMem 的 pipeline 原生就是 yfinance）：
`auto_adjust=True`，`Close` 是复权价，基准是窗口内 as_of（含）之前最后一个
`adj_factor`。**不自己拼 URL、不自己算复权** —— 那两件事垫片已经做过一遍。
"""
from __future__ import annotations

import datetime as _dt
from typing import Any

#: 三类在本环境里没有的数据源 → (nodata 的 kind, 上游的哪个 pipeline 步骤)
MISSING_SOURCES: tuple[tuple[str, str, str], ...] = (
    ("news", "finmem.data_pipeline.01_Alpaca_News_API_download", "news"),
    ("fundamentals", "finmem.data_pipeline.01_SEC_API_10k10q_download.10k", "filing_k"),
    ("fundamentals", "finmem.data_pipeline.01_SEC_API_10k10q_download.10q", "filing_q"),
)


def note_missing_sources(cli, symbol: str, start: str, end: str) -> list[dict[str, Any]]:
    """把三类 NO_DATA 各留一次痕。**永不抛** —— 留痕失败不改变被观测的行为。

    一类一次（不是一天一次）：FinMem 的 pipeline 是「一次把整段窗口的新闻拉下来」，
    尝试的粒度就是一类一段，不是一天一条。
    """
    from genebench_client import nodata

    out: list[dict[str, Any]] = []
    for kind, api, slot in MISSING_SOURCES:
        traced = nodata.trace(cli, kind, api, symbol=symbol, start=start, end=end)
        out.append({"kind": kind, "api": api, "env_slot": slot, "traced": bool(traced)})
    return out


def build(symbol: str, start: str, end: str) -> dict[_dt.date, dict[str, Any]]:
    """造 `env_data_pkl`。只有价格有数；三个文本槽恒空。

    `start` / `end` 都是闭区间的日期字符串，两端都必须给 ——
    开区间会被网关拒（`open_range_would_cross_asof`）。
    """
    from genebench_client.compat import yfinance as yf

    # `download` 的 `end` 是**右开**（与 yfinance 一致，垫片替我们减一天），
    # 所以要拿到 end 当天必须多给一天。多给的那一天仍然 <= as_of 由调用方保证。
    end_exclusive = (_dt.date.fromisoformat(end) + _dt.timedelta(days=1)).isoformat()
    frame = yf.download(symbol, start=start, end=end_exclusive)
    if frame is None or len(frame) == 0:
        raise SystemExit(f"网关在 {start}..{end} 没有 {symbol} 的行情 —— **不编价格**。")

    out: dict[_dt.date, dict[str, Any]] = {}
    for idx, row in frame.iterrows():
        day = idx.date() if hasattr(idx, "date") else _dt.date.fromisoformat(str(idx)[:10])
        price = row.get("Close")
        if price is None or float(price) != float(price) or float(price) <= 0:
            # 停牌 / 无成交的那一天没有可用价格。**跳过，不前值填充** ——
            # 前值填充会让「那天没交易」在收益序列上表现为「那天收益 0」。
            continue
        out[day] = {
            "price": {symbol: float(price)},
            "filing_k": {},          # 本环境没有 PIT 财报文本（见 MISSING_SOURCES）
            "filing_q": {},
            "news": {},              # 本环境没有新闻源
        }
    return dict(sorted(out.items()))
