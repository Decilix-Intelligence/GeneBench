<<fixed:preamble>>
把给你的因子（在 /task/inputs/ 里，以同目录的 manifest.json 为准）变成一个只看名次的信号
计算窗口内每个交易日（以网关 /calendar 为准），把当天有因子值的标的按因子值从小到大排名次
名次换算成百分位，取值落在 (0, 1]，最小的那只是 1/N、最大的是 1，其中 N 是当天参与排名的标的数
并列的取平均名次
名次不得为 0
因子缺值、或者网关 /tradability 视图为 no_data 的格子留空（写 null）
[计分禁令] 无观点的格子不得补 0
[计分禁令] 本题不得出现 flat
产出里报的 payload.coverage 三项计数（n_valued / n_null / n_flat）必须和 signals 的内容对得上
<<fixed:gateway_url>>
<<fixed:endpoints>>
<<fixed:as_of>>
<<fixed:task_window>>
<<fixed:task_universe>>
<<fixed:inputs>>
本次任务的口径（逐项）：
<<say_all>>
产出要包含：无观点的格子写 null，以及覆盖统计（n_valued / n_null / n_flat 三项）

<<fixed:no_default_fill>>

<<fixed:output_format>>
<<fixed:artifact_path>>
校验串：<<canary>>
