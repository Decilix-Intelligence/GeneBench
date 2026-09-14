<<fixed:preamble>>
任务（S5）：把输入因子面板（/task/inputs/ 下的 parquet，以同目录 manifest.json 为准）直接作为分数信号，并区分「无观点」与「主动空仓」。
规则：信号值 = 当日因子值（不做变换）
每个交易日因子值处于当日横截面最低 10% 的标的写 flat（主动空仓）
网关 /tradability 视图为 no_data 的格子、以及因子值为空的格子写 null（无观点）
[计分禁令] 无观点的格子不得补 0
[计分禁令] 无观点的格子不得写 flat
[计分禁令] 无观点的格子不得用前值填充
窗口内尚未纳入或已退出宇宙的格子不得凭空生成
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
