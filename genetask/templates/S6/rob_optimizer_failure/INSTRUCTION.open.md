<<fixed:preamble>>
你手上有一份信号文件（在 /task/ 目录里）。
请按这次任务给的约束和目标，在每个调仓日算出目标持仓，写成 S6 的产出
payload.targets 按调仓日一条一条列，每条写日期（date）、求解状态（solver_status，optimal、infeasible 或 not_converged）和持仓列表（positions）
持仓列表里每只票一行、含六个台账字段——代码（symbol）、信号分数（score）、上期权重（previous_weight）、目标权重（target_weight）、权重变动（delta_weight）、当日参考收盘价（reference_close）
payload.cash_ratio 先留着写 null。
几条规则：
分数取信号文件里当天那只票的值
[计分禁令] 值为 null 或 flat 的标的不得入选
信号文件在部分日期覆盖很稀，动手之前先数一数每天有多少只票能入选
哪一天在约束下根本凑不出可行解，就把求解状态写成 infeasible、持仓列表留空
算不收敛就把求解状态写成 not_converged
[计分禁令] 求解失败不得把上期持仓抄成当日目标，也不得标 optimal
[计分禁令] 求解失败不得放宽约束凑出一个解
无解的日子不动仓位，下一个调仓日的上期权重仍然取最近一次成功求解那天的目标权重
第一个调仓日从空仓开始，上期权重全是 0
被清出去的票保留一行、目标权重写 0
参考收盘价用网关 /bars 返回的当天 close（显式写 fields）
权重变动等于目标权重减上期权重
provenance 里引用信号文件元数据中的上游 artifact_id
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
