# `d2_e2e` —— 一次端到端的**构造验收**留下的两张小表

<!-- Y-2026-09-13 -->

**这不是能力读数。** 这里的六个 run 与那两行主表，证明的是**这条链路在一台没有本项目
任何遗留物的机器上能把一次真运行变成一行主表**；它们**不是**「这套系统在这套题上是什么水平」。
拿这两行去比较模型、去引用，都是误读。

**为什么它在树里。** [`README.md`](../../../README.md) §2.4 与
[`docs/OPERATOR_MANUAL.md`](../../../docs/OPERATOR_MANUAL.md) §5.3 都用这次的终态分布劝你一件事：
**别把「一批 run 大半撞闸」读成自己配错了**。那句话要成立，你手上得有那份分布 ——
所以它随树发。**只放分布与表头这两张小表**：run 产物、bundle、日志、题面与答案面
一个字节都不在这里（红线 2）。

## 这次跑的是什么

| | |
| --- | --- |
| 时间 | 2026-09-13 |
| 树 | 一棵全新 clone + 三件附件，**本项目的遗留物一件都没有** |
| 通道 | `public`（公开题集实例 `v1.0-smoke-public`、公开 provider 快照） |
| 矩阵 | **3 题 × 双臂 = 6 个 run**，串行，默认预算档 `--max-calls 100` |
| 墙钟 | 合计 **2 小时 1 分** |
| 真模型调用 | 合计 **582 次**（`llm_log` 里 `decision == allow` 的条数） |
| 逐步实测 | [`ops/reports/mac_gap_closeout.md`](../mac_gap_closeout.md) §3–§5 |

## `run_states.csv` —— 六个 run 的终态

**终态分布：3 个 `budget_exhausted` / 1 个 `timeout` / 1 个 `ok` / 1 个 `violation`。**

读它的三条：

* **`budget_exhausted` 是收口状态，不是失败。** 它与 `ok` / `violation` / `timeout` 并列
  （`runner/c42/failure_modes.py::RUN_STATUSES`，那个元组的顺序即判定优先级）。
* **撞了闸不一定就记 `budget_exhausted`。** 这六个里**四个**用满了 100 次调用，
  其中一个（`s2-cor-01.open`）已经把 artifact 写下来了，于是终态是 `ok` ——
  所以「用满 100 次」是 4 条，「终态 `budget_exhausted`」是 3 条，两个数本来就不相等。
* 那个 `timeout` 撞的是 **1500 秒墙钟闸**（实测 1548.1 s），不是预算闸。

`run_id` 一栏**去掉了机器标识后缀**（原样是 `<task>.<arm>.<config_id>.<seq>@<machine_id>`）——
它标的是发布方那台执行面，对读这份证据的人没有意义。

## `table_main_excerpt.csv` —— 主表长什么样

**19 个指标列 + 5 个身份列 = CSV 24 列**，列名与顺序由 `ops/test_report_columns.py` 逐字钉住。
**文件名里的 `excerpt` 是认真的**：这里只有那张表的表头与两行，**不是一个批的产物目录**（真的批目录还带六件全量指标表，`ops/test_V2.py` 按 `table_main.csv` 这个名字认批，所以这份摘录不能叫那个名字）。
这份文件的价值是**表头**：照 README §2.4 走完一遍，你出的那张表的第一行应当与它逐字相同。

四条版本轴（当时的 `table_main.axes.json`）：`set_version = p1.0.0` /
`reference_version = r1.0.23` / `protocol_version = geneprotocol_v1@d6fbcaa08302`
（裸臂记 `geneprotocol_v1@none`）/ `channel = public`；`mixed_axes = {}`。

**空 ≠ 0 ≠ `—`。** `0` 是「测了，是零」；`—` 是「这一格的 run 全落在拒绝 / 诚实终止 /
未结算 / 预算截断四类里，**没有读数**」；**空白**是「这批 run 里没有这个阶段的样本」——
本批只有 S1–S3，所以 S4–S8 那十列是空的。逐列口径在
[`ops/reports/report_spec_v1.md`](../report_spec_v1.md) 与手册 §6.5–§6.7。
