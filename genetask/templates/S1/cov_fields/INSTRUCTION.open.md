<<fixed:preamble>>
请通过数据网关，把指定标的在指定窗口内的日线取回来，并把每一次取数写成结构化记录。
要求字段：close、volume、adj_factor。
取法：close 与 volume 走 /bars 并显式传 fields
adj_factor 走 /adj。
窗口：上面给出的计算窗口
标的：声明的指数在窗口末日的成分，经 /universe 取
[计分禁令] 成分不得手写，一律经 /universe 取
<<fixed:gateway_url>>
<<fixed:endpoints>>
<<fixed:as_of>>
<<fixed:task_window>>
<<fixed:inputs>>
本次任务的口径（逐项）：
<<say_all>>
产出：payload.fetches 逐次列 {endpoint, params, fetched_at, status, rows}，fetched_at 取网关回包里的时间戳
payload.fields_obtained 列出实际拿到的字段名。
产出要包含：每次取数的记录（取数的时间、结果状态，含空结果与被拒）。

<<fixed:no_default_fill>>

<<fixed:output_format>>
<<fixed:artifact_path>>
校验串：<<canary>>
