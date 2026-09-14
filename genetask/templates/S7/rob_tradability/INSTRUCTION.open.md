<<fixed:preamble>>
用题面给定的规则把这个参考信号的回测完整跑一遍。
要注意：窗口里的股票并不都是「正常可交易」的 —— 有的已经掉出指数但还在交易，有的停牌但仍在上市，有的已经真正退市，还有些日子触及了涨跌停
这几种情况能不能买、能不能卖、怎么估值、怎么出清，按题面给出的声明第 1 节和第 4 节各有规定，把它们混成一种处理，指标就会算错，或者某一天的账就平不了。
要求同前：指标按上面的声明算对，每日账目（现金加持仓市值对总资产）最大绝对残差不超过 1e-6。
输入：/task/signal.parquet（列 date / code / signal），即回测用的参考信号
这是唯一的信号来源
[计分禁令] 不得自造或改算信号
/task/signal.meta.json 记录该信号的上游 artifact 标识。
行情、复权因子、交易日历、指数成分与可交易性状态经网关端点 /bars /adj /calendar /universe /tradability 获取
停牌和退市要分开辨认，涨跌停要按题面给出的声明的判定式自己算，别只看某一个状态标签
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
另附 payload.n_days（回测覆盖的交易日数）、调仓频率的回显（payload.rebalance_frequency，声明值）、逐日「现金＋持仓市值－总资产」的最大绝对残差（payload.ledger_check.max_abs_residual）（ledger_check 的 max_abs_residual；停牌估值日和退市出清日也要算进去），和 alpha／beta／cost／total 四个数的归因（payload.attribution）。
产出要包含：换手（单边与双边分别报）、成本、记账守恒残差（数值）、收益归因。

<<fixed:no_default_fill>>

<<fixed:output_format>>
<<fixed:output_files>>
<<fixed:artifact_path>>
校验串：<<canary>>
