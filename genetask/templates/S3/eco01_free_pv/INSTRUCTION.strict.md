<<fixed:preamble>>
任务（S3，自由发挥）：自行设计并实现一个量价因子，在计算窗口（上面给出的计算窗口）内逐截面计算，产出 S3 artifact（payload 含 factor_id、expression、values_ref、nonfinite、warmup、approximated_operators、degeneracy）。
规则：payload.factor_id 自取，以 `free.` 开头
payload.expression 写出最终采用的完整表达式
下面的口径即可用的取数与算子预算，超出即违例
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
