<<fixed:preamble>>
用题面给定的规则把这个参考信号的回测完整跑一遍，然后把净收益拆成三块说清楚钱是从哪来、到哪去的：total 就是净年化收益
cost 是净年化收益减去毛年化收益（也就是费用吃掉了多少）
beta 是组合毛日收益对基准日收益做一元回归得到的斜率，再乘以基准的年化收益，基准用窗口内每天成分股的等权收益（自己用网关数据算，不要另外去取指数行情）
剩下的就是 alpha（total 减 beta 减 cost）。
总成本（total_cost）这一项要按累计费用金额除以初始资金来算，不要把每天的费用率加起来。
目标：三块加起来等于 total（误差不超过 1e-6），指标按上面的声明算对，每日账目（现金加持仓市值对总资产）最大绝对残差不超过 1e-6。
输入：/task/signal.parquet（列 date / code / signal），即回测用的参考信号
这是唯一的信号来源
[计分禁令] 不得自造或改算信号
/task/signal.meta.json 记录该信号的上游 artifact 标识。
行情、复权因子、交易日历、指数成分与可交易性状态都经网关获取
<<fixed:gateway_url>>
<<fixed:endpoints>>
<<fixed:as_of>>
<<fixed:task_window>>
<<fixed:task_universe>>
<<fixed:inputs>>
本次任务的口径（逐项）：
<<say_all>>
产出时把上面每一条口径原样写进 declarations
指标（payload.metrics）要填齐毛年化收益（ann_return_gross）／净年化收益（ann_return_net）、净年化波动（ann_vol_net）、净最大回撤（max_drawdown_net）、毛夏普（sharpe_gross）／净夏普（sharpe_net）、净 Sortino（sortino_net_mar0，MAR 取 0）、净 Calmar（calmar_net）、总成本（total_cost），以及单边（turnover_one_way_mean）和双边（turnover_two_way_mean）换手（两个数都要写，缺一即畸形）
另附 payload.n_days（回测覆盖的交易日数）、调仓频率的回显（payload.rebalance_frequency，声明值）、逐日「现金＋持仓市值－总资产」的最大绝对残差（payload.ledger_check.max_abs_residual），和按上面口径算的 alpha／beta／cost／total 归因（payload.attribution）。
产出要包含：换手（单边与双边分别报）、成本、记账守恒残差（数值）、收益归因。

<<fixed:no_default_fill>>

<<fixed:output_format>>
<<fixed:output_files>>
<<fixed:artifact_path>>
校验串：<<canary>>
