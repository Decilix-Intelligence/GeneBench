<<fixed:preamble>>
任务（S6）：读取 /task/ 下的信号文件，在声明的约束集与目标下求出每个调仓日的目标持仓。
本题要求台账的形式与可审计性逐条满足，下列任一不满足即畸形。
产出形态与审计要求：
- payload.targets 按 date 升序，日期写作 YYYY-MM-DD
- 每条含 solver_status ∈ {optimal, infeasible, not_converged} 与 positions。
- positions 按 symbol 升序
- symbol 沿用信号文件里的写法（不得改大小写、不得增删后缀）
- 同一调仓日同一 symbol 只能出现一次
- 每行必须且只能含台账六字段 symbol / score / previous_weight / target_weight / delta_weight / reference_close，数值字段均为有限数
- 上期权重非零的标的本期必须出现（哪怕 target_weight 为 0 的清仓行也不得省略）
- 首个调仓日 previous_weight 全为 0
- reference_close 必须等于该调仓日经网关 /bars（显式 fields=close）返回的 close，不得用其它来源或其它日期
- delta_weight = target_weight − previous_weight，精确到浮点相等
- target_weight 合计不得超过 1
- score 取信号文件中该调仓日该标的的值
- [计分禁令] 值为 null 或 flat 的标的不得入选
- payload.cash_ratio 必须存在，本版写 null
- provenance 必须恰好引用一条：信号文件元数据里的上游 artifact_id（stage S5）
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
