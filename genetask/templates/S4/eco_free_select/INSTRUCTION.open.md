<<fixed:preamble>>
/task/factor_pool.parquet 里放了一批候选因子（date、code、factor_id、value 四列）
请在给定口径下评估它们，挑出你认为在没见过的数据上最有预测力的那一个
<<fixed:gateway_url>>
<<fixed:endpoints>>
<<fixed:as_of>>
<<fixed:task_window>>
<<fixed:task_universe>>
<<fixed:inputs>>
远期收益、按时点取的成分股（PIT 宇宙）、能不能交易、复权因子都从网关的 /bars /adj /calendar /universe /tradability 端点拿
本次任务的口径（逐项）：
<<say_all>>
要交的东西：payload.selected_factor_id 写你选的因子
payload.ic_stats 八项（mean、std、icir、positive_ratio、coverage、ci_low、ci_high、ci_method）是它在窗口后半段留出样本上、按口径里最短持有期算出来的结果，留出段的起止日（start、end）写进 payload.holdout。
你算过 IC 的候选一共有几个，如实写进 payload.search_count，少报按违例处理
这些候选的 factor_id 和它们在留出段之前的 IC 均值列在 payload.candidates_evaluated 里
挑因子只许拿留出段之前的数据来挑
IC 一天一个截面地算再汇总，坏格子剔掉、coverage 如实
declarations 把口径原样写回
产出要包含：IC 统计（均值、标准差、正比例 positive_ratio、覆盖率 coverage、bootstrap 区间）。

<<fixed:no_default_fill>>

<<fixed:output_format>>
<<fixed:artifact_path>>
校验串：<<canary>>
