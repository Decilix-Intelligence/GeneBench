<<fixed:preamble>>
任务（S4）：对 /task/ 下给定的因子值面板，在下列声明的评估设定下复算 IC 族，并让整个评估可审计、可重算。
<<fixed:gateway_url>>
<<fixed:endpoints>>
<<fixed:as_of>>
<<fixed:task_window>>
<<fixed:task_universe>>
<<fixed:inputs>>
材料：因子面板 /task/factor_panel.parquet（列 date, code, value；给定的参考面板 因子值，不要重算）
/task/factor_panel.meta.json 给出该面板的 sha256 与上游 S3 artifact_id。
远期收益、PIT 宇宙、可交易性、复权因子经网关取（/bars /adj /calendar /universe /tradability）。
本次任务的口径（逐项）：
<<say_each>>
产物要求：
- payload.ic_stats = {mean, std, icir, positive_ratio, coverage, ci_low, ci_high, ci_method}，取声明中最短的持有期
- 每个持有期各自的同八键汇总写 payload.ic_by_horizon[<h>]
- provenance 含一条 {stage: "S3", artifact_id: <meta.json 里的上游 id>}
- payload.audit = {input_sha256（面板文件实测哈希，必须与 meta.json 一致）, fetches[{endpoint, params, rows}]（你发出的每一次网关请求，顺序保留）, bootstrap{seed, n_resamples, block_length}, code_sha256（你评估脚本的哈希，脚本本身留在 /task/solve_s4.py）}
- 信封 seed 等于 audit.bootstrap.seed
- 同一脚本同一 seed 重跑，ic_stats 逐位相同
- IC 逐交易日截面计算再汇总，无效格剔除、coverage 如实
- declarations 逐字段回显题面声明。
产出要包含：IC 统计（均值、标准差、正比例 positive_ratio、覆盖率 coverage、bootstrap 区间）。

<<fixed:no_default_fill>>

<<fixed:output_format>>
<<fixed:artifact_path>>
校验串：<<canary>>
