<<fixed:preamble>>
请评估一个因子的预测能力，但这次给你的因子面板是脏的：里面有 Inf 和 NaN、有空着的格子、有些值大得离谱，窗口里还有股票停牌和缺行。
你的工作是在给定口径下把 IC 算对，把坏格子剔掉而不是修补它们。
面板在 /task/factor_panel.parquet（date、code、value 三列，就是因子值本身；不要重算，也不要裁剪或缩放）。
无效格只能剔除，不能修补。
<<fixed:gateway_url>>
<<fixed:endpoints>>
远期收益、成分股名单、能不能交易、复权因子都从网关的 /bars /adj /calendar /universe /tradability 端点拿
<<fixed:as_of>>
<<fixed:task_window>>
<<fixed:task_universe>>
<<fixed:inputs>>
本次任务的口径（逐项）：
<<say_all>>
要交的东西：payload.ic_stats 八项（mean、std、icir、positive_ratio、coverage、ci_low、ci_high、ci_method），按口径里最短的持有期算
每个持有期各自的八项放 payload.ic_by_horizon，键是持有期天数。
不允许的做法：把 Inf、NaN 或空格填成 0、前一天的值或截面均值
对因子值做 winsorize、clip、标准化，或者转成更窄的浮点类型之后再算。
剔掉的格子要按原因数清楚，写进 payload.invalid_cells 的 nonfinite、missing_value、untradable、no_forward_close 四项，coverage 必须与之自洽。
产出要包含：IC 统计（均值、标准差、正比例 positive_ratio、覆盖率 coverage、bootstrap 区间）。

<<fixed:no_default_fill>>

<<fixed:output_format>>
IC 一天一个截面地算再汇总
declarations 把口径原样写回
<<fixed:artifact_path>>
校验串：<<canary>>
