# oracle 参考解（数据面私有；在 f01 直跑，经网关 snapshot 后端产 artifact）。gold_token: <<gold_token>>
"""s3-cor-01 · S3-COR-01 · worldquant_101.006 = (-1 * correlation(open, volume, 10))

网关端点（全部带 as_of，请求头 x-genebench-task-id / x-genebench-config-id）：
  GET /calendar   ?as_of&start_date&end_date                 → 窗口内交易日（is_open=1）
  GET /universe   ?as_of&name=csi300&date=<window.end>       → 成分列表（冒烟版按 window.end 取一次 PIT 快照）
  GET /bars       ?as_of&code&start_date&end_date&fields=open,volume
                                                             → 逐票日线；fields 必须显式且 == declared.required_fields
产出（reference/artifact_schema S3 payload）：
  declarations           = task.declared 原样回填（本题零欠定）
  payload.factor_id      = gold_args.factor_id；payload.expression = 源方言原文（逐字）
  values                 = 面板 (date×code) 上 rolling(10, min_periods=10) 的 open-volume Pearson 相关 × (-1)
                           暖机：窗口前 lookback-1 个交易日强制 NaN（null_until_full 从 window.start 起算，不取窗口前数据）
  values_ref             = 写 work/values.parquet（列 date, code, value；按 (date, code) 排序；float64）
                           rows / n_dates / n_symbols / coverage=非空格÷(n_dates×n_symbols) / sha256=文件字节
  nonfinite              = inf_count=isinf 计数；nan_count=暖机期之后的 NaN 计数（成交量恒定的窗口相关系数为 NaN）；replaced_count=0
  warmup                 = {lookback, first_valid_date=窗口第 lookback 个交易日, nonnull_before_warmup=0}
  approximated_operators = []（correlation 用 pandas rolling corr 精确实现，没有近似）
  degeneracy             = is_constant=全窗非空值 nunique<=1；alert = is_constant or coverage < COVERAGE_FLOOR
gold：compiled 表达式经 reference/factor_exec 三路后端算出的切片 reference/tasks/<set>/s3-cor-01/gold/slice.parquet；
      scorer 按 τ（卡 2.2）对共同覆盖网格做 Spearman。
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import numpy as np
import pandas as pd

# 统一 I/O 契约（裁定 2026-09-05）：读标准位置的任务规格、经网关取数、写标准 artifact 路径。
# **不接受任何 stage 特定的 env/argv** —— 从任务目录读得出来的东西，一律不从环境拿。
from reference.oracle_io import context as _oracle_context
CTX = _oracle_context(__file__)
GATEWAY, TASK, WINDOW, AS_OF = CTX.gateway, CTX.spec, CTX.window, CTX.as_of
FACTOR_ID = "worldquant_101.006"
EXPRESSION = "(-1 * correlation(open, volume, 10))"
LOOKBACK = 10
FIELDS = ["open", "volume"]                 # == declared.required_fields，逐次显式传给 /bars
COVERAGE_FLOOR = 0.0574                     # N-17：792 条实测覆盖率分布 P5（待签字，签后从 calibration.json 读）
HDR = {"x-genebench-task-id": TASK["task_id"], "x-genebench-config-id": "oracle"}


def compute(df: pd.DataFrame, cal: pd.DatetimeIndex) -> pd.Series:
    open_ = df["open"].unstack("code").reindex(cal).astype("float64")
    vol = df["volume"].unstack("code").reindex(cal).astype("float64")
    # param_order=[series_a, series_b, window]；correlation=pearson_rolling_window；min_periods=window 即 null_until_full
    corr = open_.rolling(LOOKBACK, min_periods=LOOKBACK).corr(vol)
    val = -1.0 * corr
    val.iloc[: LOOKBACK - 1] = np.nan             # 暖机从 window.start 起算
    return val.stack(dropna=False).rename("value")


def main():
    # 取数 / 暖机 / 非有限值统计 / 落盘全部在公共层 —— **一处实现，五处共用**。
    from reference.s3_oracle_common import run
    run(ctx=CTX, factor_id=FACTOR_ID, expression=EXPRESSION, lookback=LOOKBACK,
        fields=FIELDS, compute=compute, coverage_floor=COVERAGE_FLOOR)


if __name__ == "__main__":
    main()
