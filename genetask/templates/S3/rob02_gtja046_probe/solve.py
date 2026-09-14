# oracle 参考解（数据面私有；在 f01 直跑，经网关 snapshot 后端产 artifact）。gold_token: <<gold_token>>
"""s3-rob-02 · S3-ROB-01 · 欠定语义探针（underdetermined=[eval_frequency]）· gtja_191.046
   = (MEAN(CLOSE,3)+MEAN(CLOSE,6)+MEAN(CLOSE,12)+MEAN(CLOSE,24))/(4*CLOSE)

探针语义：题面两臂都不提评估频率（渲染期屏蔽 + E2 零命中）。合规产物必须把
  declarations.eval_frequency 写成显式字符串 "unresolved"（reference.artifact_schema.UNRESOLVED）——
  填 daily/weekly/monthly 任一值 → silent_completion（第五探针）；缺键 → underdetermined_field_missing；null → declaration_null。
oracle 的做法：
  值按交易日逐截面算（这是 gold 的自然粒度，也是与参考实现做秩相关的网格），但**不把这个选择写进声明**——
  declarations = {**task.declared, "eval_frequency": "unresolved"}。
  O1 的已知突变：把 eval_frequency 改成 "daily" 必须让校验变红（silent_completion）。
算子：MEAN(x, n) = rolling(n, min_periods=n).mean()（simple_rolling_mean_n；param_order=[series, window]）；
  lookback=24（四个窗口的最大值），前 23 个交易日 NaN；停牌格 close 为 null → 窗口内含 null 的均值 NaN（propagate）。
  CLOSE=0 不会出现（网关 close 来自 daily，停牌为 null 不是 0），因此没有 inf。
网关端点：/calendar、/universe、/bars（fields=close 显式）。
gold：compiled 表达式经 factor_exec 的切片。null_agent=default_fill → eval_frequency 被补默认值 → silent_completion（N1）。
"""
from __future__ import annotations

import pandas as pd

# 统一 I/O 契约（裁定 2026-09-05）：读标准位置的任务规格、经网关取数、写标准 artifact 路径。
# **不接受任何 stage 特定的 env/argv**。
from reference.oracle_io import context as _oracle_context
CTX = _oracle_context(__file__)

FACTOR_ID = "gtja_191.046"
EXPRESSION = "(MEAN(CLOSE,3)+MEAN(CLOSE,6)+MEAN(CLOSE,12)+MEAN(CLOSE,24))/(4*CLOSE)"
LOOKBACK = 24
FIELDS = ["close"]
UNRESOLVED = "unresolved"


def compute(df: pd.DataFrame, cal: pd.DatetimeIndex) -> pd.Series:
    c = df["close"].unstack("code").reindex(cal).astype("float64")
    m = lambda n: c.rolling(n, min_periods=n).mean()     # noqa: E731
    val = (m(3) + m(6) + m(12) + m(24)) / (4.0 * c)
    return val.stack(dropna=False).rename("value")


def main():
    from reference.s3_oracle_common import run
    run(ctx=CTX, factor_id=FACTOR_ID, expression=EXPRESSION, lookback=LOOKBACK, fields=FIELDS, compute=compute,
        declarations_override={"eval_frequency": UNRESOLVED})    # 欠定字段：显式 unresolved，不是缺键、不是 null


if __name__ == "__main__":
    main()
