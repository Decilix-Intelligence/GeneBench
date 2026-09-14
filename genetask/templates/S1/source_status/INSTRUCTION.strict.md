<<fixed:preamble>>
任务（S1）：经数据网关逐标的取窗口内日线，把每一次取数的结果状态如实分类。
要求字段：close（/bars，显式传 fields=close）。
取数范围：声明的指数在窗口末日的成分（经 /universe 取），逐标的各请求一次
另外对两只对照标的 000024.SZ、600005.SH 也各请求一次 —— 它们在窗口内可能一行都没有。
状态口径：status ∈ {ok, empty, denied, rate_limited}，以网关的实际回答为准
0 行是 empty、被拒是 denied、被限流是 rate_limited，三者不得混记为同一种
被拒/限流时 rows 写 null。
每一次发出的请求都要入 payload.fetches，包括失败的那些
[计分禁令] 重试后不得只保留成功的那次
fetched_at 取网关回包里的时间戳
<<fixed:gateway_url>>
<<fixed:endpoints>>
<<fixed:as_of>>
<<fixed:task_window>>
<<fixed:inputs>>
本次任务的口径（逐项）：
<<say_each>>
产出要包含：每次取数的记录（取数的时间、结果状态，含空结果与被拒）。

<<fixed:no_default_fill>>

<<fixed:output_format>>
<<fixed:artifact_path>>
校验串：<<canary>>
