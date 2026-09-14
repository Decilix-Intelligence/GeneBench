<<fixed:preamble>>
请评估一个已经算好的因子有没有预测能力。
因子值面板放在 /task/factor_panel.parquet（每行一个 date、code、value，这就是因子值本身，不用你再算因子）。
<<fixed:gateway_url>>
<<fixed:endpoints>>
远期收益、成分股名单、能不能交易、复权因子这些都从网关的 /bars /adj /calendar /universe /tradability 端点拿
<<fixed:as_of>>
<<fixed:task_window>>
<<fixed:task_universe>>
<<fixed:inputs>>
本次任务的口径（逐项）：
<<say_all>>
要交的东西：payload.ic_stats 里给出 mean、std、icir、positive_ratio、coverage、ci_low、ci_high、ci_method 八项，按口径里最短的那个持有期算
每个持有期各自的这八项放进 payload.ic_by_horizon，键是持有期天数。
IC 要一天一个截面地算、再把这条序列汇总
因子值不是有限数、当天不能交易、后面那天没有收盘价、或者后面那天已经超过 as_of 的格子都要剔掉，剔掉多少要如实体现在 coverage 里。
产出要包含：IC 统计（均值、标准差、正比例 positive_ratio、覆盖率 coverage、bootstrap 区间）。

<<fixed:no_default_fill>>

<<fixed:output_format>>
declarations 里把上面的口径原样写回去，不要改
<<fixed:artifact_path>>
校验串：<<canary>>
