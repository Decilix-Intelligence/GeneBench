<<fixed:preamble>>
任务（S3）：按下面的源方言原文实现因子，在计算窗口（上面给出的计算窗口）内逐截面计算，产出 S3 artifact（payload 含 factor_id、expression、values_ref、nonfinite、warmup、approximated_operators、degeneracy）。
因子：gtja_191.012
源方言原文：`(RANK((OPEN - (SUM(VWAP, 10) / 10)))) * (-1 * (RANK(ABS((CLOSE - VWAP)))))`
本题的重点是取数流程与可审计性：每次 /bars 请求只带本题声明的字段且逐次显式
表达式里的每个价量字段都按名从网关取，不得用其它列自行推算
values_ref.sha256 为值文件（按 date、code 排序、float64）的字节摘要
payload.expression 照抄原文
approximated_operators 与 degeneracy 要显式填写（没有近似就写空列表）
暖机从计算窗口首日起算。
<<fixed:gateway_url>>
<<fixed:endpoints>>
<<fixed:as_of>>
<<fixed:task_window>>
<<fixed:task_universe>>
<<fixed:inputs>>
<<fixed:fields_required>>
本次任务的口径（逐项）：
<<say_each>>
产出要包含：非有限值（Inf/NaN）计数、暖机期处理、退化（常数输出）报警。

<<fixed:no_default_fill>>

<<fixed:output_format>>
<<fixed:output_files>>
<<fixed:artifact_path>>
校验串：<<canary>>
