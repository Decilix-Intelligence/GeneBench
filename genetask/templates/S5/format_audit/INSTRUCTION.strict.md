<<fixed:preamble>>
任务（S5）：把输入因子面板（/task/inputs/ 下的 parquet，以同目录 manifest.json 为准）变成分数信号，并按信号表规范产出
本题要求信号表与审计链本身规范，下列任一不满足即畸形。
规范：(1) signals 的格子集合必须恰好等于「window 内交易日（/calendar）× 声明宇宙的 PIT 成分（/universe）」，每个 (date, symbol) 恰好一行，不得多、不得少、不得重复
(2) date 写 YYYY-MM-DD，symbol 写大写代码加交易所后缀，与网关返回一致
(3) 信号值 = 因子值（不做变换）
因子值为空、或 /tradability 视图为 no_data 的格子写 null
[计分禁令] 本题不得出现 flat
(4) provenance 必须引用上游因子 artifact，stage 与 artifact_id 取自 manifest.json
(5) payload.coverage 的三项计数必须与 signals 内容一致
(6) declarations 必须逐项回显题面声明，不得增删改。
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
