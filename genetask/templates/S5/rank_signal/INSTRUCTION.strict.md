<<fixed:preamble>>
任务（S5）：把输入因子面板（/task/inputs/ 下的 parquet，以同目录 manifest.json 为准）变成横截面名次信号。
规则：计算窗口内每个交易日（以网关 /calendar 为准），把当日有因子值的标的按因子值升序做百分位名次
名次取值落在 (0, 1]，最小 1/N、最大 1，其中 N 为当日参与排名的标的数
并列取平均名次
名次不得为 0
因子值为空、或网关 /tradability 视图为 no_data 的格子写 null
[计分禁令] 无观点的格子不得补 0
[计分禁令] 本题不得出现 flat
payload.coverage 的三项计数（n_valued / n_null / n_flat）必须与 signals 内容一致
<<fixed:gateway_url>>
<<fixed:endpoints>>
<<fixed:as_of>>
<<fixed:task_window>>
<<fixed:task_universe>>
<<fixed:inputs>>
本次任务的口径（逐项）：
<<say_each>>
产出要包含：无观点的格子写 null，以及覆盖统计（n_valued / n_null / n_flat 三项）

<<fixed:no_default_fill>>

<<fixed:output_format>>
<<fixed:artifact_path>>
校验串：<<canary>>
