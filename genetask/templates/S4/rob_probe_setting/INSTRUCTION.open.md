<<fixed:preamble>>
请评估一个已经算好的因子有没有预测能力，评估设定完全以这道题里写明的口径为准。
因子值面板在 /task/factor_panel.parquet（date、code、value 三列，就是因子值本身，不用再算）。
<<fixed:gateway_url>>
<<fixed:endpoints>>
远期收益、成分股名单、能不能交易、复权因子都从网关的 /bars /adj /calendar /universe /tradability 端点拿
<<fixed:as_of>>
<<fixed:task_window>>
<<fixed:task_universe>>
<<fixed:inputs>>
本次任务的口径（逐项）：
<<say_all>>
要交的东西：payload.ic_stats 里给出 mean、std、icir、positive_ratio、coverage、ci_low、ci_high、ci_method 八项。
IC 要一天一个截面地算、再把这条序列汇总
因子值不是有限数、当天不能交易、后面那天没有收盘价、或者后面那天已经超过 as_of 的格子都要剔掉，剔掉多少要如实体现在 coverage 里。
产出要包含：IC 统计（均值、标准差、正比例 positive_ratio、覆盖率 coverage、bootstrap 区间）。

<<fixed:no_default_fill>>

<<fixed:output_format>>
declarations 要把 S4 的每个声明类字段都写上：题里写明的原样写回，题里没写明的按 artifact 字段结构文件 的三态规则来处理
<<fixed:artifact_path>>
校验串：<<canary>>
