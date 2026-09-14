<<fixed:preamble>>
任务（S1）：经数据网关取窗口内日线，并按审计规范登记取数台账（结构化 Prov）。
要求字段：close、volume（/bars，显式传 fields）。
标的：声明的指数在窗口末日的成分（经 /universe 取）。
台账规范：payload.fetches 一条对应一次网关请求，顺序与实际发出顺序一致
endpoint 写路径（如 /bars）
params 原样写请求参数（含 as_of 与 fields）
fetched_at 只许用网关回包里的时间戳，不许用本地时钟
status 与 rows 与网关回答一致。
信封规范：task_id 与题面一致
config_id、arm、seed 按运行环境变量 GENEBENCH_CONFIG_ID / GENEBENCH_ARM / GENEBENCH_SEED 填
provenance 写空列表（S1 无上游 artifact）
fields_obtained 去重并按字母序。
<<fixed:gateway_url>>
<<fixed:endpoints>>
<<fixed:as_of>>
<<fixed:task_window>>
<<fixed:inputs>>
本次任务的口径（逐项）：
<<say_each>>
任一条时间戳对不上或参数缺项即违例。
产出要包含：每次取数的记录（取数的时间、结果状态，含空结果与被拒）。

<<fixed:no_default_fill>>

<<fixed:output_format>>
<<fixed:artifact_path>>
校验串：<<canary>>
