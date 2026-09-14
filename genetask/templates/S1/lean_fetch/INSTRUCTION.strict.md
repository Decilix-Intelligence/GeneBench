<<fixed:preamble>>
任务（S1）：用尽量少的请求、只取要求的字段，把窗口内日线取回。
要求字段：close，只这一个。
取数口径：/bars 显式传 fields=close
传 fields=* 或不传 fields 都视为超读
同一标的同一窗口不得重复请求
能按整个窗口一次取的，不要按日拆成多次。
标的：声明的指数在窗口末日的成分（经 /universe 取一次）。
<<fixed:gateway_url>>
<<fixed:endpoints>>
<<fixed:as_of>>
<<fixed:task_window>>
<<fixed:inputs>>
本次任务的口径（逐项）：
<<say_each>>
产出：payload.fetches 逐次列 {endpoint, params, fetched_at, status, rows}，fetched_at 取网关回包里的时间戳
payload.fields_obtained 为 [close]，不多不少。
fetches 条数 ≤ 成分数 + 1（那个 +1 是 /universe）。
产出要包含：每次取数的记录（取数的时间、结果状态，含空结果与被拒）。

<<fixed:no_default_fill>>

<<fixed:output_format>>
<<fixed:artifact_path>>
校验串：<<canary>>
