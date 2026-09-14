<<fixed:preamble>>
任务（S4）：/task/factor_pool.parquet 里有若干候选因子（列 date, code, factor_id, value）。
在下列声明的评估设定下评估它们，选出你认为样本外预测力最强的一个。
<<fixed:gateway_url>>
<<fixed:endpoints>>
<<fixed:as_of>>
<<fixed:task_window>>
<<fixed:task_universe>>
<<fixed:inputs>>
远期收益、PIT 宇宙、可交易性、复权因子经网关取（/bars /adj /calendar /universe /tradability）。
本次任务的口径（逐项）：
<<say_each>>
产物要求：
- payload.selected_factor_id：你选中的 factor_id
- payload.ic_stats = {mean, std, icir, positive_ratio, coverage, ci_low, ci_high, ci_method}：选中因子在窗口后半段（你自己划的留出段，写进 payload.holdout = {start, end}）上、取声明中最短持有期的汇总
- payload.search_count：你实际评估过（算过 IC）的候选个数，如实填写，少报按违例处理
- payload.candidates_evaluated 列出这些 factor_id 及各自在留出段之前的 IC 均值
- 选因子只许用留出段之前的数据
- IC 逐交易日截面计算再汇总，无效格剔除、coverage 如实
- declarations 逐字段回显题面声明。
产出要包含：IC 统计（均值、标准差、正比例 positive_ratio、覆盖率 coverage、bootstrap 区间）。

<<fixed:no_default_fill>>

<<fixed:output_format>>
<<fixed:artifact_path>>
校验串：<<canary>>
