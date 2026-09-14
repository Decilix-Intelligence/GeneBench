<<fixed:preamble>>
把网关给你的日线整理成一张和标准面板长得一样的表：字段名改成目标命名、该缺的行按声明里说的方式处理。
窗口和标的范围看题面。
交易日历只从 /calendar 取
成分只从 /universe 取（按 as_of 时点）
复权因子只从 /adj 取，不得从价格序列反推。
<<fixed:gateway_url>>
<<fixed:endpoints>>
<<fixed:as_of>>
<<fixed:task_window>>
<<fixed:task_universe>>
<<fixed:inputs>>
本次任务的口径（逐项）：
<<say_all>>
产出里请写清三件事：源字段到目标字段的完整映射（field_map，代码和日期两列也写上）
面板有多少行（rows）、面板文件的 sha256 是多少（panel_ref，面板文件请按代码、日期升序写）
「交易日 × 当天的成分」这张网格里有多少个格子没有行情（missing_rows.count）。
产出要包含：字段命名对齐结果、缺行处理结果、复权处理结果

<<fixed:no_default_fill>>

<<fixed:output_format>>
<<fixed:output_files>>
<<fixed:artifact_path>>
校验串：<<canary>>
