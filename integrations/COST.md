# 接入成本（机器统计）

> 本文由 `python -m integrations.cost report` 从 `COST.jsonl` **生成**，
> 不要手改 —— 手改的表会和账本漂开，而漂开的表现是「表看起来是对的」。

**合计：7 个接入 / 573.6 净工时分钟 / 返工 6 次 / 目录现存 6791 非空行。**

口径：净工时 = `begin`..`end` 去掉 `pause`..`resume` 段；增删行 = `git diff --numstat <begin 时 HEAD>..HEAD -- integrations/<id>`；现存行 = 该目录当前非空行数（未提交的工作只在这一列里看得见）。

| 接入 | 谁 | 净工时(min) | 增行 | 删行 | 现存非空行 | 返工 | 结局 |
|---|---|---:|---:|---:|---:|---:|---|
| `tradingagents` | agent | 90.2 | 0 | 0 | 871 | 2 | passed_real_task |
| `rdagent_q` | agent | 105.7 | 1126 | 0 | 938 | 1 | passed_real_task |
| `finmem` | agent | 65.4 | 1549 | 0 | 1294 | 0 | passed_real_task |
| `finrobot` | agent | 44.2 | 0 | 0 | 1125 | 0 | passed_real_task |
| `alphaagent` | agent | 82.4 | 1387 | 0 | 1151 | 0 | passed_real_task |
| `stockagent` | agent | 72.2 | 0 | 0 | 1032 | 1 | passed_real_task |
| `quantagent` | agent | 113.7 | 447 | 0 | 380 | 2 | passed_real_task |
