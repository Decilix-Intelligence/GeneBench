# -*- coding: utf-8 -*-
"""接线③：把**网关**的数据落成 AlphaAgent 的 DSL 面板。

AlphaAgent 的因子求值口 `alphaagent.dsl.eval.eval_factor(expr, panel)` 认的是
**一个 DataFrame**：`MultiIndex[datetime, instrument]` + 普通列名，DSL 里用
`$列名` 引用（`alphaagent/dsl/core/parser.py::dollar_ref_to_pyname`：`$close` → `close`）。
形状实测自 `alphaagent/data/panel.py::_coerce_datetime_index`（那里断言
`panel.index.names == ["datetime", "instrument"]`）与
`alphaagent/dsl/eval.py::_dollar_columns`。

所以「把系统的数据层换成垫片」在 AlphaAgent 上的落法是**两层**：

  * **本模块**：经垫片取数、按它要的形状造面板，直接喂给 `eval_factor` ——
    替换掉的是 `alphaagent.data.panel.build_panel` / `load_panel` 这条
    「先 fetch 到 parquet 缓存、再离线 build_panel」的两段式管线。
    它一行都不用改：我们只是不走那条路，把它的产物直接递到下一站。
  * `glue/bootstrap.py`：把 `tushare` 顶替成经网关的 compat 层，让系统内部
    任何残余的取数路径也通到网关。

**为什么面板不经 compat.tushare 取**：compat 层的 `fields` 只裁剪返回值、
不改变网关上的读取集（垫片 README §4），而 S3 的「声明读取集 vs 实际读取集」
探针是从 access_log 反推的 —— 经 compat 取数就控制不了声明读取集。
所以这里用 `gb.client().bars(codes, start, end, fields=[...])` **显式传 fields**。

**退成 NoData 的数据源**：AlphaAgent 原本描述的面板有 OHLC + 复权 OHLC +
`$vwap` / `$float_cap` / `$tot_cap` / `$ret` / `$is_trade` / `$not_st` /
`$industry_sw_l1` 与一整套 `funda_*` 基本面列（见它的 mining prompt）。
本环境只发放题面点名的那几列。这里**不造**其余的列：造出来的 `$float_cap`
会让模型写出一个跑得通、值全是编的因子。缺哪些、模型看不看得见，
由 `glue/agent.py` 把**实际列集**逐字写进 system prompt。
"""
from __future__ import annotations


def build_panel(bars, fields):
    """`bars` 是垫片 `Client.bars()` 的长表（列 code / date / status / <fields>）。

    返回 AlphaAgent DSL 面板：索引 `[datetime, instrument]`，列就是 `fields`。

    **只搬运，不补值**：`status` 不是行情列，不进面板；缺的日期就是缺，
    不 reindex 出一格 NaN 来 —— 那会让「这天没数」与「这天算不出来」混成一件事。
    `instrument` 直接用网关的代码写法（`600000.SH`），与 AlphaAgent 面板里
    tushare 口径的 `ts_code` 是同一种写法，不需要来回搬运。
    """
    import pandas as pd

    if bars is None or len(bars) == 0:
        raise RuntimeError("网关返回空的 bars —— 面板落不下去。不造数据。")
    df = bars.copy()
    cols = [c for c in fields if c in df.columns]
    if not cols:
        raise RuntimeError(f"bars 里没有题面要的列 {list(fields)}；实得 {list(df.columns)}")
    df["datetime"] = pd.to_datetime(df["date"])
    df["instrument"] = df["code"].astype(str)
    out = df.set_index(["datetime", "instrument"])[cols].astype("float64")
    out = out[~out.index.duplicated(keep="first")]
    return out.sort_index()


def panel_summary(panel) -> dict:
    """给 prompt 与日志用的一份**清点**（没有一处是「应该是多少」）。"""
    dts = panel.index.get_level_values("datetime")
    return {
        "columns": [str(c) for c in panel.columns],
        "rows": int(len(panel)),
        "n_dates": int(dts.nunique()),
        "n_instruments": int(panel.index.get_level_values("instrument").nunique()),
        "date_min": str(dts.min().date()),
        "date_max": str(dts.max().date()),
    }
