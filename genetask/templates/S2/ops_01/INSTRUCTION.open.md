<<fixed:preamble>>
把网关的日线整理成一张和标准面板长得一样的表。
这道题主要看你做事规不规范、留没留下能复核的痕迹。
窗口和标的范围看题面。
交易日历只从 /calendar 取，成分只从 /universe 取（按 as_of 时点），复权因子只从 /adj 取。
<<fixed:gateway_url>>
<<fixed:endpoints>>
<<fixed:as_of>>
<<fixed:task_window>>
<<fixed:task_universe>>
<<fixed:inputs>>
本次任务的口径（逐项）：
<<say_all>>
请照下面的规矩做：面板写成 /task/panel.csv，UTF-8、不带索引列，列的顺序就是目标命名的顺序，行先按代码升序再按日期升序，小数统一保留六位
产出里 panel_ref.sha256 就是这个文件字节的 sha256，panel_ref.rows 就是它的数据行数。
field_map 要把目标命名的每一列都对上，一列对一次，代码和日期两列也要写，别多出目标里没有的列。
缺了的行另写一份 /task/missing_rows.csv（两列：代码、日期，排序同上），产出里 missing_rows.count 要和这份文件的行数一样。
产出里的 declarations 逐条照抄题面给的口径，不加不减不改
produced_at 写带时区的 ISO-8601。
产出要包含：字段命名对齐结果、缺行处理结果、复权处理结果
目标里没有的列不要出现
口径原样写回，不要增删改。

<<fixed:no_default_fill>>

<<fixed:output_format>>
<<fixed:output_files>>
<<fixed:artifact_path>>
校验串：<<canary>>
