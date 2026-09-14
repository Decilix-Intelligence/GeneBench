# -*- coding: utf-8 -*-
"""接线③：把**网关**的数据落成 RD-Agent 因子路径认得的 qlib 面板。

RD-Agent 的因子路径不认「数据源」，它认**一个目录里的 HDF5 面板**：
`FactorCoSTEERSettings.data_folder(_debug)` 下的 `daily_pv.h5`，
索引是 `MultiIndex[datetime, instrument]`，列名是 qlib 风格的 `$open` / `$volume`…
（形状实测自 `rdagent.scenarios.qlib.experiment.utils.get_data_folder_intro` 的输出）。

所以「把系统的数据层换成垫片」在 RD-Agent 上的落法是：
**我们经垫片取数、按它要的形状落一份面板**，而不是去改它读文件的代码。
它一行都不用改 —— 这正是 `integrations/README.md` §0 那条纪律（接口在范式层，
不为单个系统写内核适配）在这个系统上的具体形态。

**退成 NoData 的数据源**：RD-Agent 的 qlib 场景原本描述的是一份 pv + 财务的
全量 provider。本环境只发放行情面（`/bars` 的列集），财务 / 新闻 / 资金流
一律没有 —— 见 `integrations/rdagent_q/README.md` 的「哪些数据源退成 NoData」。
这里**不造**那些列：造出来的 `$roe` 会让模型写出一个跑得通、值全是编的因子。
"""
from __future__ import annotations

import re

#: 网关的代码写法（`600000.SH`）与 qlib 的写法（`SH600000`）之间只差一次搬运。
#: 两边都要有，因为**面板给模型看的是 qlib 写法，产出文件要回到题面的写法**。
_CODE = re.compile(r"^(\d+)\.([A-Za-z]{2})$")
_QCODE = re.compile(r"^([A-Za-z]{2})(\d+)$")


def to_qlib_code(code: str) -> str:
    m = _CODE.match(str(code))
    return f"{m.group(2).upper()}{m.group(1)}" if m else str(code)


def to_gateway_code(qcode: str) -> str:
    m = _QCODE.match(str(qcode))
    return f"{m.group(2)}.{m.group(1).upper()}" if m else str(qcode)


def build_panel(bars, fields):
    """`bars` 是垫片 `Client.bars()` 的长表（列 code / date / status / <fields>）。

    返回 qlib 面板：索引 `[datetime, instrument]`，列 `$<field>`。
    **只搬运，不补值**：`status` 不是行情列，不进面板；缺的日期就是缺，
    不 reindex 出一格 NaN 来（那会让「这天没数」与「这天算不出来」混成一件事）。
    """
    import pandas as pd

    if bars is None or len(bars) == 0:
        raise RuntimeError("网关返回空的 bars —— 面板落不下去。不造数据。")
    df = bars.copy()
    df["datetime"] = pd.to_datetime(df["date"])
    df["instrument"] = df["code"].map(to_qlib_code)
    cols = [c for c in fields if c in df.columns]
    if not cols:
        raise RuntimeError(f"bars 里没有题面要的列 {list(fields)}；实得 {list(df.columns)}")
    out = df.set_index(["datetime", "instrument"])[cols].astype("float64")
    out.columns = [f"${c}" for c in cols]
    return out.sort_index()


def write_panel(panel, data_folder, names=("daily_pv.h5",)):
    """落盘。RD-Agent 用 `pd.read_hdf(..., key='data')` 读，`mode='w'` 覆盖。

    只写 `daily_pv.h5` 一个文件：`get_data_folder_intro()` 会把目录里**每一个**文件
    都描述给模型，多写一份同内容的 `daily_pv_all.h5` 只会让 prompt 里出现两份
    一模一样的表，白烧 token。
    """
    import hashlib
    import pathlib

    out = {}
    for name in names:
        p = pathlib.Path(data_folder) / name
        p.parent.mkdir(parents=True, exist_ok=True)
        panel.to_hdf(p, key="data", mode="w")
        out[name] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out
