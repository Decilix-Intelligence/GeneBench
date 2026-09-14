# oracle 参考解（数据面私有；在 f01 直跑，经网关 snapshot 后端产 artifact）。gold_token: <<gold_token>>
"""s3-eco-01 · S3-ECO-02 · 自由发挥（kind=free，oracle.expected=validate_only，anchor pending）

本题没有 gold。oracle 的职责只是证明「在声明的预算内能产出一份零 finding 的 S3 artifact」（O1），
并给基线阶梯提供一个 hand-crafted 档位样本（对接决定 §1.2：random/placebo → hand-crafted → existing-set）。
预算 = 声明：required_fields=[close, volume]、lookback=20、operator_semantics={dialect: qlib_expression}、
        param_order=[series, window]、nonfinite=propagate、warmup=null_until_full。
oracle 采用的因子（hand-crafted 档，量价背离）：
  factor_id  = "free.oracle_pv_divergence_20"
  expression = "Corr(Rank($close), Rank($volume), 20) * -1"      ← qlib 表达式方言，窗口 20 == lookback
  实现：qlib 语义下 Rank 为**截面**百分位秩（0,1]、Corr 为滚动 Pearson；用 pandas 复刻：
        rank_c = close.rank(axis=1, pct=True); rank_v = volume.rank(axis=1, pct=True)
        val = -1 * rank_c.rolling(20, min_periods=20).corr(rank_v)
网关端点：/calendar、/universe、/bars（fields=close,volume 显式）。
产出：同 s3-cor-01 的 emit；declarations 原样回填七个字段；degeneracy 必须真算（自由题最容易交常数因子）。
效果分：禁止结算（卡 3.1 §7 第 4 条），scorer 只出 validity/gate_failed/correctness{}，effect=null 直到卡 5.4 标定锚。
null_agent=empty → payload_missing / declarations_missing（N1）。
"""
from __future__ import annotations

import pandas as pd

# 统一 I/O 契约（裁定 2026-09-05）：读标准位置的任务规格、经网关取数、写标准 artifact 路径。
# **不接受任何 stage 特定的 env/argv**。
from reference.oracle_io import context as _oracle_context
CTX = _oracle_context(__file__)

FACTOR_ID = "free.oracle_pv_divergence_20"
EXPRESSION = "Corr(Rank($close), Rank($volume), 20) * -1"
LOOKBACK = 20
FIELDS = ["close", "volume"]


def compute(df: pd.DataFrame, cal: pd.DatetimeIndex) -> pd.Series:
    close = df["close"].unstack("code").reindex(cal).astype("float64")
    vol = df["volume"].unstack("code").reindex(cal).astype("float64")
    rc = close.rank(axis=1, pct=True)          # qlib Rank：截面百分位秩
    rv = vol.rank(axis=1, pct=True)
    val = -1.0 * rc.rolling(LOOKBACK, min_periods=LOOKBACK).corr(rv)
    return val.stack(dropna=False).rename("value")


def main():
    from reference.s3_oracle_common import run
    run(ctx=CTX, factor_id=FACTOR_ID, expression=EXPRESSION, lookback=LOOKBACK, fields=FIELDS, compute=compute)


if __name__ == "__main__":
    main()
