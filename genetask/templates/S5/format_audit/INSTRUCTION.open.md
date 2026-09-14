<<fixed:preamble>>
本题要求信号表本身规范（信号值原样取因子值，因子在 /task/inputs/ 里，以同目录的 manifest.json 为准），下面任何一条没做到都算畸形：窗口内每个交易日（/calendar）、声明宇宙里的每只 PIT 成分股（/universe）必须恰好一行，不多不少不重复
日期（date）用 YYYY-MM-DD，代码（symbol）用大写并带交易所后缀，和网关返回的写法一致
因子缺值、或 /tradability 视图为 no_data 的格子留空（写 null）
[计分禁令] 本题不得出现 flat
provenance 必须引用你用的上游因子产物（阶段和 artifact_id 抄 manifest.json 里的）
payload.coverage 的三项计数必须和 signals 的内容一致
declarations 必须逐项照抄题面的口径，不能增减或改动。
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
