<<fixed:preamble>>
这次的窗口很长（好几年），请把网关的日线整理成一张和标准面板长得一样的表。
除了做对，这道题还看你做得省不省：向网关发了多少次请求、网关一共给你返回了多少行、花了多长时间，都要尽量小。
所以向 /bars 要数据时请明确写上 fields、只要面板用得着的列
一次把整个窗口取下来，别一天一天地问
同样的请求不要发第二遍。
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
产出里请写清：源字段到目标字段的完整映射（field_map，代码和日期两列也写上）
面板行数（rows）和面板文件的 sha256（panel_ref，面板按代码、日期升序写）
网格里有多少个格子没有行情（missing_rows.count —— 就算按口径这些格子最后不留在面板里，这个数也要报出来）。
产出要包含：字段命名对齐结果、缺行处理结果、复权处理结果

<<fixed:no_default_fill>>

<<fixed:output_format>>
<<fixed:output_files>>
<<fixed:artifact_path>>
校验串：<<canary>>
