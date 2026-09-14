<<fixed:preamble>>
请把下面这条因子按它的源方言原文实现出来，在计算窗口（见 上面给出的计算窗口）内对每个截面、每只标的算出值，并如实报告非有限值、暖机期与退化情况
产出一份 S3 artifact（payload 里要有 factor_id、payload.expression、values_ref、nonfinite、warmup、approximated_operators、degeneracy 这几个键）。
因子编号 worldquant_101.006，原文是 `(-1 * correlation(open, volume, 10))`。
因子值按下列口径算：payload 里的 expression 请照抄原文，算子不要自行替换
暖机从计算窗口的第一天起算，不要拿窗口之前的数据把开头几个截面补出来。
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
