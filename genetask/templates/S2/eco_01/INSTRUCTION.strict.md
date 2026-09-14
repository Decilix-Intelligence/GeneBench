<<fixed:preamble>>
任务（S2）：在一段多年的长窗口上把网关日线整理成与标准面板同构的面板。
本题在做对的前提下还要省：网关请求次数、网关返回的总行数、墙钟时间都要尽量小。
<<fixed:gateway_url>>
<<fixed:endpoints>>
<<fixed:as_of>>
<<fixed:task_window>>
<<fixed:task_universe>>
<<fixed:inputs>>
窗口与宇宙以 上面给出的计算窗口 / universe 为准。
取数纪律：/bars 显式传 fields 只取面板需要的列
窗口一次取全，不要按日轮询
同一端点同一参数不要重复请求。
交易日历只从 /calendar 取，成分只从 /universe 取（按 as_of 时点），复权因子只从 /adj 取。
本次任务的口径（逐项）：
<<say_each>>
产出要求（payload）：
- field_map：源字段 → 目标字段的完整映射，键列也要列入
- panel_ref：rows 与面板文件的 sha256（面板按代码、日期升序落盘）
- missing_rows：count = 网格里没有行情的格子数（即便按声明这些格子最终不在面板里，数也要报）。
产出要包含：字段命名对齐结果、缺行处理结果、复权处理结果

<<fixed:no_default_fill>>

<<fixed:output_format>>
<<fixed:output_files>>
<<fixed:artifact_path>>
校验串：<<canary>>
