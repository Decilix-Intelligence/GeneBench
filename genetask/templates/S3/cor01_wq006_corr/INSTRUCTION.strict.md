<<fixed:preamble>>
任务（S3）：按下面的源方言原文实现因子，在计算窗口（上面给出的计算窗口）内逐截面计算，产出 S3 artifact（payload 含 factor_id、expression、values_ref、nonfinite、warmup、approximated_operators、degeneracy）。
因子：worldquant_101.006
源方言原文：`(-1 * correlation(open, volume, 10))`
因子值按下列口径算：expression 照抄原文，算子不得自行替换
payload.expression 照抄原文
暖机从计算窗口首日起算，不得用窗口之前的数据把前几个截面补出来。
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
