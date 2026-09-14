<<fixed:preamble>>
任务（S3）：按下面的源方言原文实现因子，在计算窗口（上面给出的计算窗口）内逐截面计算，产出 S3 artifact（payload 含 factor_id、expression、values_ref、nonfinite、warmup、approximated_operators、degeneracy）。
因子：worldquant_101.054
源方言原文：`((-1 * ((low - close) * (open^5))) / ((low - high) * (close^5)))`
本题的重点是非有限值的安全传播：A 股一字板（全天只有一个成交价）的截面会让分母为零
这些格子产出什么、被计成什么，要与你写出的值文件逐格对得上：nonfinite.inf_count / nan_count 按值文件实数，replaced_count 如实填写
payload.expression 照抄原文
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
