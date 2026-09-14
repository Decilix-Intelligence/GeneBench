# 夹具数据卡：S6 输入信号（N-99 ②③）

## `s5_gtja001_csi300_v1`（②）

= **S5 oracle（s5-cor-01）**在 gtja_191.001 × csi300 上的 gold 输出。
窗口放宽到 S6 消费方并集 `2026-05-06` … `2026-07-31`（同一份 oracle 代码，放进 scratch 任务目录跑）。
与 s5-cor-01 真 gold 在其自身窗口上的逐值核对：`{'checked': True, 'rows': 6900}`。
每个消费方按自己的 `window.start … max_date` 切片。

## `s6_sparse_coverage_csi300_v1`（③）

取 ② 的信号，窗口内**每第 7 个交易日**（从首日起，下标 0,7,14,…）把当日除**代码最小的 3 只**以外全部置 null；其余日不动。
3 < `max_weight=0.1` 下 `full_investment` 所需的 10 只 —— 那些日子构造无可行解。

### s6-cor-01

- dense_rows: `6900`

### s6-eco-01

- dense_rows: `18600`

### s6-ops-01

- dense_rows: `18600`

### s6-rob-01

- sparse_rows: `6900`
- nulled_dates: `['2026-07-01', '2026-07-10', '2026-07-21', '2026-07-30']`

### s6-rob-02

- dense_rows: `13200`

