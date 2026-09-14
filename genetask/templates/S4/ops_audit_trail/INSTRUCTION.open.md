<<fixed:preamble>>
请评估一个已经算好的因子的预测能力，并且把整个评估过程做成能被审计、能被别人原样重跑的样子。
因子值面板在 /task/factor_panel.parquet（date、code、value 三列，就是因子值本身，不要再算）
旁边的 /task/factor_panel.meta.json 写着这份面板的 sha256 和它来自哪个 S3 artifact。
<<fixed:gateway_url>>
<<fixed:endpoints>>
远期收益、成分股名单、能不能交易、复权因子都从网关的 /bars /adj /calendar /universe /tradability 端点拿
<<fixed:as_of>>
<<fixed:task_window>>
<<fixed:task_universe>>
<<fixed:inputs>>
本次任务的口径（逐项）：
<<say_all>>
要交的东西：payload.ic_stats 八项（mean、std、icir、positive_ratio、coverage、ci_low、ci_high、ci_method），按口径里最短持有期算
每个持有期各自的八项放 payload.ic_by_horizon，键是持有期天数。
provenance 里要有一条 stage 为 S3、artifact_id 为 meta.json 里那个上游 id 的引用。
payload.audit 里写清：input_sha256（你自己算的面板文件哈希，必须和 meta.json 对得上）、fetches（你向网关发的每一次请求的 endpoint、params、rows，按先后顺序）、bootstrap 的 seed、n_resamples、block_length，以及 code_sha256（你评估脚本的哈希，脚本本身放在 /task/solve_s4.py）。
产物信封里的 seed 要和 audit.bootstrap.seed 一样
同一个脚本、同一个 seed 再跑一次，ic_stats 每一位都要相同。
产出要包含：IC 统计（均值、标准差、正比例 positive_ratio、覆盖率 coverage、bootstrap 区间）。

<<fixed:no_default_fill>>

<<fixed:output_format>>
IC 一天一个截面地算再汇总，坏格子剔掉、coverage 如实
declarations 把口径原样写回
<<fixed:artifact_path>>
校验串：<<canary>>
