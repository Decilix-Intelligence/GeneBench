<<fixed:preamble>>
请把下面这条因子按它的源方言原文实现出来，在计算窗口（见 上面给出的计算窗口）内对每个截面、每只标的算出值，并如实报告非有限值、暖机期与退化情况
产出一份 S3 artifact（payload 里要有 factor_id、payload.expression、values_ref、nonfinite、warmup、approximated_operators、degeneracy 这几个键）。
因子编号 gtja_191.012，原文是 `(RANK((OPEN - (SUM(VWAP, 10) / 10)))) * (-1 * (RANK(ABS((CLOSE - VWAP)))))`。
这道题的重点在流程能不能被审计：每次 /bars 请求只带本题声明的字段且逐次显式
表达式里出现的每个价量字段都按名字从网关取，不要用别的列自己推算出来
values_ref 的 sha256 要是值文件（按 date、code 排序、float64）的字节摘要
expression 照抄原文
approximated_operators 和 degeneracy 要明确写出来，没有近似就写空列表
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
