<<fixed:preamble>>
把因子值原样当作信号分数（因子在 /task/inputs/ 里，以同目录的 manifest.json 为准），但要分清两种「没有值」
信号值就是当日因子值，不做变换
每个交易日因子排在当天最低一成的标的，明确标记为空仓（flat）
网关 /tradability 视图为 no_data 的格子、或者因子本身缺值的格子，留空表示没有观点
[计分禁令] 无观点的格子不得补 0
[计分禁令] 无观点的格子不得写 flat
[计分禁令] 无观点的格子不得用前值填充
还没进宇宙或已经出去的票不得凭空造格子
产出里的 payload.coverage 的三项计数必须和 signals 的内容一致
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
