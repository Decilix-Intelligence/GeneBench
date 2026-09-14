<<fixed:preamble>>
任务（S4）：给定的因子面板不干净——含非有限值（Inf/NaN）、空格与数量级极端的值，窗口内又有停牌与缺行。
在下列声明的评估设定下复算 IC 族
无效格只许剔除，不许修补。
<<fixed:gateway_url>>
<<fixed:endpoints>>
<<fixed:as_of>>
<<fixed:task_window>>
<<fixed:task_universe>>
<<fixed:inputs>>
材料：因子面板 /task/factor_panel.parquet（列 date, code, value；给定的参考面板 因子值，不要重算、不要裁剪、不要缩放）。
远期收益、PIT 宇宙、可交易性、复权因子经网关取（/bars /adj /calendar /universe /tradability）。
本次任务的口径（逐项）：
<<say_each>>
产物要求：
- payload.ic_stats = {mean, std, icir, positive_ratio, coverage, ci_low, ci_high, ci_method}，取声明中最短的持有期
- 每个持有期各自的同八键汇总写 payload.ic_by_horizon[<h>]
- 禁止：把非有限值或空格替换为 0 / 前值 / 截面均值
- 对因子值 winsorize、clip、标准化或转成更窄的浮点类型后再算
- 无效格按原因计数写 payload.invalid_cells = {nonfinite, missing_value, untradable, no_forward_close}，coverage 必须与之自洽
- IC 逐交易日截面计算、再对时序汇总
- declarations 逐字段回显题面声明。
产出要包含：IC 统计（均值、标准差、正比例 positive_ratio、覆盖率 coverage、bootstrap 区间）。

<<fixed:no_default_fill>>

<<fixed:output_format>>
<<fixed:artifact_path>>
校验串：<<canary>>
