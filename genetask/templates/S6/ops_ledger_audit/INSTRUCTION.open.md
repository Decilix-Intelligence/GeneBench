<<fixed:preamble>>
你手上有一份信号文件（在 /task/ 目录里）。
请按这次任务给的约束和目标，在每个调仓日算出目标持仓，写成 S6 的产出。
本题要求台账的形式与可审计性逐条满足，下面任何一条没做到都算畸形：
payload.targets 按日期（date）从早到晚排，日期写成 YYYY-MM-DD，每条带求解状态（solver_status，optimal、infeasible 或 not_converged）和持仓列表（positions）
持仓列表按代码升序排，代码照信号文件里的写法原样抄（不得改大小写、不得增删后缀）
同一天同一只票只能出现一次
每一行恰好六个台账字段——代码（symbol）、信号分数（score）、上期权重（previous_weight）、目标权重（target_weight）、权重变动（delta_weight）、当日参考收盘价（reference_close）——数值都得是有限数
上一期权重不为零的票这一期必须出现，哪怕是目标权重为 0 的清仓行也不得省略
第一个调仓日的上期权重全是 0
参考收盘价必须等于网关 /bars 在那个调仓日返回的 close（显式写 fields=close），不得用别的来源或别的日期
权重变动等于目标权重减上期权重、要精确相等
同一天目标权重加起来不得超过 1
分数取信号文件里那个调仓日的值
[计分禁令] 值为 null 或 flat 的标的不得入选
payload.cash_ratio 这个字段必须在、写 null
provenance 里恰好引用一条，就是信号文件元数据中的上游 artifact_id（S5 阶段）
<<fixed:gateway_url>>
<<fixed:endpoints>>
<<fixed:as_of>>
<<fixed:task_window>>
<<fixed:task_universe>>
<<fixed:inputs>>
本次任务的口径（逐项）：
<<say_all>>
产出要包含：每个调仓日的台账（上期权重、目标权重、变动）与求解状态，遵守约束。

<<fixed:no_default_fill>>

<<fixed:output_format>>
<<fixed:artifact_path>>
校验串：<<canary>>
