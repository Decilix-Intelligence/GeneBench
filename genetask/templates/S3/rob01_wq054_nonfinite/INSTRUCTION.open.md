<<fixed:preamble>>
请把下面这条因子按它的源方言原文实现出来，在计算窗口（见 上面给出的计算窗口）内对每个截面、每只标的算出值，并如实报告非有限值、暖机期与退化情况
产出一份 S3 artifact（payload 里要有 factor_id、payload.expression、values_ref、nonfinite、warmup、approximated_operators、degeneracy 这几个键）。
因子编号 worldquant_101.054，原文是 `((-1 * ((low - close) * (open^5))) / ((low - high) * (close^5)))`。
这道题考的是对非有限值的处理纪律：A 股一字板那种全天只有一个成交价的截面会让分母为零，这些格子算出来是什么就写什么，nonfinite 里的 inf、nan、被替换三个计数（inf_count、nan_count、replaced_count）都要能和你的值文件逐格核对
payload 里的 expression 请照抄原文
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
