<<fixed:preamble>>
任务（S4）：对 /task/ 下给定的因子值面板，在下列声明的评估设定下复算 IC 族。
<<fixed:gateway_url>>
<<fixed:endpoints>>
<<fixed:as_of>>
<<fixed:task_window>>
<<fixed:task_universe>>
<<fixed:inputs>>
材料：因子面板 /task/factor_panel.parquet（列 date, code, value；已是 给定的参考面板 因子值，不要重算因子）。
远期收益、PIT 宇宙、可交易性、复权因子经网关取（/bars /adj /calendar /universe /tradability）。
本次任务的口径（逐项）：
<<say_each>>
产物要求：
- payload.ic_stats = {mean, std, icir, positive_ratio, coverage, ci_low, ci_high, ci_method}，取声明中最短的持有期
- 每个声明持有期各自的同八键汇总写 payload.ic_by_horizon[<h>]
- IC 逐交易日截面计算、再对时序汇总
- 无效格（因子非有限 / 当日不可交易 / 远期收盘缺失 / 远期日期越过 as_of）剔除，coverage 如实
- declarations 逐字段回显题面声明，不得改口径。
产出要包含：IC 统计（均值、标准差、正比例 positive_ratio、覆盖率 coverage、bootstrap 区间）。

<<fixed:no_default_fill>>

<<fixed:output_format>>
<<fixed:artifact_path>>
校验串：<<canary>>
