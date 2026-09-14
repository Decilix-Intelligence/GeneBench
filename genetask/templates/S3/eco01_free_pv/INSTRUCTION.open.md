<<fixed:preamble>>
这是一道自由发挥题：请自己设计一个量价因子并实现出来，在计算窗口（见 上面给出的计算窗口）内对每个截面、每只标的算出值，并如实报告非有限值、暖机期与退化情况
产出一份 S3 artifact（payload 里要有 payload.factor_id、payload.expression、values_ref、nonfinite、warmup、approximated_operators、degeneracy 这几个键）。
这道题自行设计因子
本题只看 artifact 的结构与声明是否合规。
factor_id 自己取名（以 `free.` 开头），expression 写出你最终采用的完整表达式
下面的口径就是你能用的取数与算子预算，超出了就算违例
暖机从计算窗口的第一天起算。
<<fixed:gateway_url>>
<<fixed:endpoints>>
<<fixed:as_of>>
<<fixed:task_window>>
<<fixed:task_universe>>
<<fixed:inputs>>
<<fixed:fields_required>>
本次任务的口径（逐项）：
<<say_all>>
产出要包含：非有限值（Inf/NaN）计数、暖机期处理、退化（常数输出）报警。

<<fixed:no_default_fill>>

<<fixed:output_format>>
<<fixed:output_files>>
<<fixed:artifact_path>>
校验串：<<canary>>
