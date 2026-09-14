<<fixed:preamble>>
任务（S5）：（自由发挥）用 /task/inputs/ 下的多个输入因子面板（以同目录 manifest.json 为准）构造你认为预测力最强的分数信号。
只许使用给定的输入因子与网关数据（/bars、/adj、/calendar、/tradability、/universe），不得使用窗口之后的信息
输入因子全部为空、或网关 /tradability 视图为 no_data 的格子写 null
主动空仓写 flat
[计分禁令] 主动空仓不得写 0
payload.coverage 的三项计数必须与 signals 内容一致
<<fixed:gateway_url>>
<<fixed:endpoints>>
<<fixed:as_of>>
<<fixed:task_window>>
<<fixed:task_universe>>
<<fixed:inputs>>
本次任务的口径（逐项）：
<<say_each>>
产出要包含：无观点的格子写 null、主动空仓写 flat，以及覆盖统计。

<<fixed:no_default_fill>>

<<fixed:output_format>>
<<fixed:artifact_path>>
校验串：<<canary>>
