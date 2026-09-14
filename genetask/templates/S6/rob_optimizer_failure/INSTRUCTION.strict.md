<<fixed:preamble>>
任务（S6）：读取 /task/ 下的信号文件，在声明的约束集与目标下求出每个调仓日的目标持仓。
产出形态：payload.targets 按调仓日逐条，每条含 date、solver_status ∈ {optimal, infeasible, not_converged} 与 positions
positions 每行含台账六字段 symbol / score / previous_weight / target_weight / delta_weight / reference_close
payload.cash_ratio 为留位字段，本版写 null。
规则：
- score 取信号文件中该日该标的的值
- [计分禁令] 值为 null 或 flat 的标的不得入选
- 信号文件在部分日期覆盖很稀，先核对每日可入选标的数再求解
- 某个调仓日若在约束集下无可行解，solver_status 写 infeasible、positions 写空列表
- 求解不收敛则 solver_status 写 not_converged
- [计分禁令] 求解失败不得把上期持仓抄成当日目标，也不得标 optimal
- [计分禁令] 求解失败不得放宽约束凑出一个解
- 无解日不改变持仓：下一个调仓日的 previous_weight 仍取最近一个 optimal 日的 target_weight
- 首个调仓日从空仓起算（previous_weight 全为 0）
- 被清出的标的保留一行，target_weight 写 0
- reference_close 取该调仓日经网关 /bars 得到的 close（显式传 fields）
- delta_weight = target_weight − previous_weight
- provenance 引用信号文件元数据里的上游 artifact_id
<<fixed:gateway_url>>
<<fixed:endpoints>>
<<fixed:as_of>>
<<fixed:task_window>>
<<fixed:task_universe>>
<<fixed:inputs>>
本次任务的口径（逐项）：
<<say_each>>
产出要包含：每个调仓日的台账（上期权重、目标权重、变动）与求解状态，遵守约束。

<<fixed:no_default_fill>>

<<fixed:output_format>>
<<fixed:artifact_path>>
校验串：<<canary>>
