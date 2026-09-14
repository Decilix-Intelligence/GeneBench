<<fixed:preamble>>
给你几个因子（都在 /task/inputs/ 里，以同目录的 manifest.json 为准），用它们组合出一个你认为最能预测下一期涨跌的分数信号
只能用给定的因子和网关数据（/bars、/adj、/calendar、/tradability、/universe），不得使用窗口之后的信息
所有因子都缺值、或者网关 /tradability 视图为 no_data 的地方留空（写 null）
明确不想持有的地方标成空仓（flat）
[计分禁令] 主动空仓不得写 0
payload.coverage 的三项计数必须和 signals 的内容一致
<<fixed:gateway_url>>
<<fixed:endpoints>>
<<fixed:as_of>>
<<fixed:task_window>>
<<fixed:task_universe>>
<<fixed:inputs>>
本次任务的口径（逐项）：
<<say_all>>
产出要包含：无观点的格子写 null、主动空仓写 flat，以及覆盖统计。

<<fixed:no_default_fill>>

<<fixed:output_format>>
<<fixed:artifact_path>>
校验串：<<canary>>
