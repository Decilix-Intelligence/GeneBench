"""snapshots —— 从数据湖构建冻结快照的代码。

只读连接数据湖(`duckdb.connect(..., read_only=True)`),
产物落 `cfg.SNAPSHOTS`(不落 /home,红线 6),
一切上界不得超过 `cfg.FREEZE_DATE`(红线 7)。
"""
