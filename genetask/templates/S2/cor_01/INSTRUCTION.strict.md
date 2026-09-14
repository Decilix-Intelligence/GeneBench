<<fixed:preamble>>
任务（S2）：把网关返回的日线整理成与标准面板同构的日线面板 —— 字段改名到目标命名、价格统一到声明的复权口径、缺行按声明策略处置。
<<fixed:gateway_url>>
<<fixed:endpoints>>
<<fixed:as_of>>
<<fixed:task_window>>
<<fixed:task_universe>>
<<fixed:inputs>>
窗口与宇宙以 上面给出的计算窗口 / universe 为准。
交易日历只从 /calendar 取
成分只从 /universe 取（按 as_of 时点）
复权因子只从 /adj 取，不得从价格序列反推。
本次任务的口径（逐项）：
<<say_each>>
产出要求（payload）：
- field_map：源字段 → 目标字段的完整映射，键列（代码、日期）也要列入
- panel_ref：rows = 面板行数
- sha256 = 面板文件的 sha256（面板按代码、日期升序落盘）
- missing_rows：count = 「交易日 × 当日成分」网格里没有行情的格子数。
产出要包含：字段命名对齐结果、缺行处理结果、复权处理结果

<<fixed:no_default_fill>>

<<fixed:output_format>>
<<fixed:output_files>>
<<fixed:artifact_path>>
校验串：<<canary>>
