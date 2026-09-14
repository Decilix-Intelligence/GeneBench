<<fixed:preamble>>
任务（S5）：把输入因子面板（/task/inputs/ 下的 parquet，以同目录 manifest.json 为准）变成分数信号。
规则：信号值 = 因子值（不做变换）
因子值为空、或网关 /tradability 视图为 no_data 的格子写 null
[计分禁令] 本题不得出现 flat
payload.coverage 的三项计数必须与 signals 内容一致。
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
