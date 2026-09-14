<<fixed:preamble>>
任务（S7）：按题面给出的声明对参考信号计算全程回测，并把净收益拆解归因。
归因口径：
- total = ann_return_net
- cost = ann_return_net − ann_return_gross（费用对年化收益的侵蚀）
- total_cost 本身走绝对金额通道（累计费用 ÷ 初始资金），不得对逐日费用率求和
- beta = β̂ × 基准年化收益，β̂ 为组合毛日收益对基准日收益的 OLS 斜率，基准 = 窗口内当日成分股的等权日收益（由网关数据自行构造，不另取指数行情）
- alpha = total − beta − cost。
目标：alpha + beta + cost = total（残差 ≤ 1e-6），指标按上面的声明算对，逐日记账守恒（最大绝对残差 ≤ 1e-6）。
输入：/task/signal.parquet（列 date / code / signal），即回测用的参考信号
这是唯一的信号来源
[计分禁令] 不得自造或改算信号
/task/signal.meta.json 记录该信号的上游 artifact 标识。
行情、复权因子、交易日历、指数成分与可交易性状态都经网关获取。
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
- payload.attribution：alpha、beta、cost、total（按上面的口径）。
产出要包含：换手（单边与双边分别报）、成本、记账守恒残差（数值）、收益归因。

<<fixed:no_default_fill>>

<<fixed:output_format>>
<<fixed:output_files>>
<<fixed:artifact_path>>
校验串：<<canary>>
