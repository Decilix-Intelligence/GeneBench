<<fixed:preamble>>
任务（S7）：按题面给出的声明对参考信号计算全程回测
本题除指标要算对之外，额外按审计口径判，以下任一不满足即畸形：
- provenance 含且只含一条对信号上游 artifact 的引用，形如 {stage, artifact_id}，两个值取自 /task/signal.meta.json
- [计分禁令] provenance 的两个值不得手写
- declarations 逐项回显题面声明，键名与取值一字不改，不多不少，不得用 null 或别的记号代替任何一项
- payload.n_days 等于窗口内交易日历的开市日数（以网关 /calendar 为准），并等于收益率序列的长度
- payload.rebalance_frequency 回显声明值
- 信封：版本字段为字符串、stage 与 task_id 与任务一致、as_of 与任务一致、produced_at 为带时区的 ISO 时间、artifact_id 非空且在本次运行内唯一
- 逐日记账守恒（最大绝对残差 ≤ 1e-6）
输入：/task/signal.parquet（列 date / code / signal），即回测用的参考信号
这是唯一的信号来源
[计分禁令] 不得自造或改算信号
/task/signal.meta.json 记录该信号的上游 artifact 标识
行情、复权因子、交易日历、指数成分与可交易性状态都经网关获取
<<fixed:gateway_url>>
<<fixed:endpoints>>
<<fixed:as_of>>
<<fixed:task_window>>
<<fixed:task_universe>>
<<fixed:inputs>>
本次任务的口径（逐项）：
<<say_each>>
产出：
- declarations：逐项回显以上声明
- payload.metrics：ann_return_gross（毛年化收益）、ann_return_net（净年化收益）、ann_vol_net（净年化波动）、max_drawdown_net（净最大回撤）、sharpe_gross（毛夏普）、sharpe_net（净夏普）、sortino_net_mar0（净 Sortino，MAR 取 0）、calmar_net（净 Calmar）、total_cost（总成本）、turnover_one_way_mean（单边换手）、turnover_two_way_mean（双边换手）（两个数都要写，缺一即畸形）
- payload.n_days（回测覆盖的交易日数）、payload.rebalance_frequency（回显声明值）
- payload.ledger_check.max_abs_residual：逐日 |现金 + 持仓市值 − 总资产| 的最大值
- payload.attribution：alpha、beta、cost、total 四个数。
产出要包含：换手（单边与双边分别报）、成本、记账守恒残差（数值）、收益归因。

<<fixed:no_default_fill>>

<<fixed:output_format>>
<<fixed:output_files>>
<<fixed:artifact_path>>
校验串：<<canary>>
