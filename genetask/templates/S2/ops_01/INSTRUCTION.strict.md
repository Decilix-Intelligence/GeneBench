<<fixed:preamble>>
任务（S2）：把网关日线整理成与标准面板同构的面板，重点要求流程与审计留痕：产物格式、面板落盘规范、映射完整性、缺行清单可复核。
<<fixed:gateway_url>>
<<fixed:endpoints>>
<<fixed:as_of>>
<<fixed:task_window>>
<<fixed:task_universe>>
<<fixed:inputs>>
窗口与宇宙以 上面给出的计算窗口 / universe 为准。
交易日历只从 /calendar 取，成分只从 /universe 取（按 as_of 时点），复权因子只从 /adj 取。
本次任务的口径（逐项）：
<<say_each>>
流程要求（逐条满足）：
1. 面板落盘为 /task/panel.csv：UTF-8、无索引列、列序 = 目标命名顺序、行序按代码升序再日期升序、浮点统一 6 位小数
panel_ref.sha256 = 该文件字节的 sha256，panel_ref.rows = 该文件数据行数。
2. field_map 要覆盖目标命名的每一列且每列恰被映射一次
键列（代码、日期）也要列入
不得出现目标里没有的列。
3. 缺行清单落盘为 /task/missing_rows.csv（两列：代码、日期，排序同上）
missing_rows.count 等于该文件的行数。
4. artifact 的 declarations 逐字段回显题面声明，不得增删改
produced_at 用 ISO-8601 带时区。
产出要包含：字段命名对齐结果、缺行处理结果、复权处理结果

<<fixed:no_default_fill>>

<<fixed:output_format>>
<<fixed:output_files>>
<<fixed:artifact_path>>
校验串：<<canary>>
