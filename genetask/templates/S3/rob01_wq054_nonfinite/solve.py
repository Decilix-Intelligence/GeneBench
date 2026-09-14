# oracle 参考解（数据面私有；在 f01 直跑，经网关 snapshot 后端产 artifact）。gold_token: <<gold_token>>
"""s3-rob-01 · S3-ROB-02（非有限值安全传播）· worldquant_101.054
   = ((-1 * ((low - close) * (open^5))) / ((low - high) * (close^5)))

网关端点：同 s3-cor-01（/calendar、/universe、/bars），/bars 显式 fields=open,high,low,close。
要害：A 股一字板截面 low == high → 分母 (low-high)*close^5 == 0：
  分子非零 → ±inf；分子也为零（low==close，一字板必然）→ 0/0 = NaN。
  nonfinite_policy=propagate：不 clip、不 fillna、不 replace；replaced_count 必须为 0。
  power=elementwise_pow_no_clip：np.power 原样，float64 下 close^5 不会溢出（close < 1e4）。
  lookback=1：无跨日算子，warmup.first_valid_date = window.start，nonnull_before_warmup = 0。
产出：与 s3-cor-01 同一套 emit（values_ref/nonfinite/warmup/approximated_operators/degeneracy），
  区别只在 compute()。degeneracy.coverage 用有限值占比 —— 一字板格子是 NaN，csi300 上比例很小，不会触 alert。
gold：compiled 表达式经 factor_exec 的切片；真 inf/NaN 格保留不筛（卡 2.1b ⑧），Spearman 只在共同有限格上算。
null_agent=default_fill：把某个声明改一档 → declaration_mismatch（N1）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# 统一 I/O 契约（裁定 2026-09-05）：读标准位置的任务规格、经网关取数、写标准 artifact 路径。
# **不接受任何 stage 特定的 env/argv**。
from reference.oracle_io import context as _oracle_context
CTX = _oracle_context(__file__)

FACTOR_ID = "worldquant_101.054"
EXPRESSION = "((-1 * ((low - close) * (open^5))) / ((low - high) * (close^5)))"
LOOKBACK = 1
FIELDS = ["open", "high", "low", "close"]


def compute(df: pd.DataFrame, cal: pd.DatetimeIndex) -> pd.Series:
    w = {f: df[f].unstack("code").reindex(cal).astype("float64") for f in FIELDS}
    with np.errstate(divide="ignore", invalid="ignore"):          # 让 inf/NaN 产生而不是抛错
        num = -1.0 * ((w["low"] - w["close"]) * np.power(w["open"], 5))
        den = (w["low"] - w["high"]) * np.power(w["close"], 5)
        val = num / den                                            # 0/x → 0；x/0 → ±inf；0/0 → NaN；全部原样保留
    return val.stack(dropna=False).rename("value")


def main():
    from reference.s3_oracle_common import run
    run(ctx=CTX, factor_id=FACTOR_ID, expression=EXPRESSION, lookback=LOOKBACK, fields=FIELDS, compute=compute)


if __name__ == "__main__":
    main()
