<<fixed:preamble>>
把网关给的日线整理成一张和标准面板长得一样的表，并且把缺了的行如实报出来。
这段窗口里有停牌的票、有同一天先停又复的票、也有指数调进调出的票。
所谓缺行，是指：某个交易日、某只当天在成分里的票，网关 /bars 那天没给行，或者给的 status 是停牌、无数据。
窗口和标的范围看题面。
交易日历只从 /calendar 取，成分只从 /universe 取（按 as_of 时点），可交易性可查 /tradability
缺行格子的处置严格按声明执行，不得用前值、零或邻日行情代替。
<<fixed:gateway_url>>
<<fixed:endpoints>>
<<fixed:as_of>>
<<fixed:task_window>>
<<fixed:task_universe>>
<<fixed:inputs>>
本次任务的口径（逐项）：
<<say_all>>
产出里请写清：源字段到目标字段的完整映射（field_map，代码和日期两列也写上）
面板行数（rows）和面板文件的 sha256（panel_ref，面板按代码、日期升序写）
缺行格子的数量（missing_rows.count），这个数必须和你实际按声明处置过的缺行格子数一致
产出要包含：字段命名对齐结果、缺行处理结果、复权处理结果

<<fixed:no_default_fill>>

<<fixed:output_format>>
<<fixed:output_files>>
<<fixed:artifact_path>>
校验串：<<canary>>
