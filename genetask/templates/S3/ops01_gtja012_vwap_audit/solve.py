# oracle 参考解（数据面私有；在 f01 直跑，经网关 snapshot 后端产 artifact）。gold_token: <<gold_token>>
"""s3-ops-01 · S3-OPS-01（流程与审计）· gtja_191.012
   = (RANK((OPEN - (SUM(VWAP, 10) / 10)))) * (-1 * (RANK(ABS((CLOSE - VWAP)))))

审计要点（本题的分主要在这里，不在数值）：
  1. /bars 逐次显式 fields=open,close,vwap —— **vwap 直接从网关取**（N-33 加列后 /bars 服务 vwap=amount/volume，volume=0→null）。
     自己用 amount/volume 推算 = 读了 amount、volume → declared_reads 探针报 undeclared_reads。
  2. 每次取数的 (endpoint, params) 都可在网关 access_log 里按 task_id/config_id 找到；oracle 不写 S1 式 fetches，
     但 provenance 留空列表（S3 无上游 artifact）。
  3. values_ref.sha256 = work/values.parquet 的字节摘要；文件按 (date, code) 排序、float64、列名 date/code/value。
  4. approximated_operators=[]、degeneracy 显式填写；expression 逐字照抄（含空格与括号）。
算子（operator_semantics / param_order）：
  RANK = 截面百分位秩 (0,1]：df.rank(axis=1, pct=True)；SUM(x, 10) = rolling(10, min_periods=10).sum()；ABS 逐元素。
  lookback=10 → 前 9 个交易日 NaN（null_until_full 从 window.start 起算）。
  vwap 为 null 的格（volume=0，停牌）→ SUM 窗口内含 null 则该格 NaN（propagate）。
gold：compiled 表达式经 factor_exec 的切片；scorer 按 τ 做 Spearman。
null_agent=empty。
"""
from __future__ import annotations

import pandas as pd

# 统一 I/O 契约（裁定 2026-09-05）：读标准位置的任务规格、经网关取数、写标准 artifact 路径。
# **不接受任何 stage 特定的 env/argv**。
from reference.oracle_io import context as _oracle_context
CTX = _oracle_context(__file__)

FACTOR_ID = "gtja_191.012"
EXPRESSION = "(RANK((OPEN - (SUM(VWAP, 10) / 10)))) * (-1 * (RANK(ABS((CLOSE - VWAP)))))"
LOOKBACK = 10
FIELDS = ["open", "close", "vwap"]


def compute(df: pd.DataFrame, cal: pd.DatetimeIndex) -> pd.Series:
    w = {f: df[f].unstack("code").reindex(cal).astype("float64") for f in FIELDS}
    sum_vwap = w["vwap"].rolling(LOOKBACK, min_periods=LOOKBACK).sum()
    left = (w["open"] - sum_vwap / LOOKBACK).rank(axis=1, pct=True)
    right = -1.0 * (w["close"] - w["vwap"]).abs().rank(axis=1, pct=True)
    return (left * right).stack(dropna=False).rename("value")


def main():
    from reference.s3_oracle_common import run
    run(ctx=CTX, factor_id=FACTOR_ID, expression=EXPRESSION, lookback=LOOKBACK, fields=FIELDS, compute=compute)


if __name__ == "__main__":
    main()
