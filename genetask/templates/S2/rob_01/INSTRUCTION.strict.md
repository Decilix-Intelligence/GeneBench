<<fixed:preamble>>
任务（S2）：把网关日线整理成与标准面板同构的面板，并如实报告缺行。
本窗口内存在停牌、停牌与复牌同日发生、指数成分调整等情形
缺行的定义：交易日历上的交易日 × 当日成分中的标的，而 /bars 当日无行或 status 为停牌 / 无数据的格子。
<<fixed:gateway_url>>
<<fixed:endpoints>>
<<fixed:as_of>>
<<fixed:task_window>>
<<fixed:task_universe>>
<<fixed:inputs>>
窗口与宇宙以 上面给出的计算窗口 / universe 为准。
交易日历只从 /calendar 取，成分只从 /universe 取（按 as_of 时点），可交易性可查 /tradability
缺行格子的处置严格按声明执行，不得用前值、零或邻日行情代替。
本次任务的口径（逐项）：
<<say_each>>
产出要求（payload）：
- field_map：源字段 → 目标字段的完整映射，键列也要列入
- panel_ref：rows 与面板文件的 sha256（面板按代码、日期升序落盘）
- missing_rows：count 必须等于你实际按声明处置过的缺行格子数。
产出要包含：字段命名对齐结果、缺行处理结果、复权处理结果

<<fixed:no_default_fill>>

<<fixed:output_format>>
<<fixed:output_files>>
<<fixed:artifact_path>>
校验串：<<canary>>
