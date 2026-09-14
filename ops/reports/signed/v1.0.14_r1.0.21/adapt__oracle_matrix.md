# 适配赛道 v1.0-adapt：oracle × 真跑 逐例对照（30 例）

oracle：30 / 30；真运行：30 / 30。

| # | level | 题（源） | 破坏 | 期望结局 | 实际结局 | calls |
| --- | --- | --- | --- | --- | --- | --- |
| adapt-l1-01 | L1 | S1 / s1-cor-01 | 计数以百计（rows：300 → 3） | first_pass | first_pass | 18 |
| adapt-l1-02 | L1 | S1 / s1-ops-01 | 日期写成紧凑串（as_of：2026-07-31 → 20260731） | first_pass | first_pass | 18 |
| adapt-l1-03 | L1 | S2 / s2-rob-01 | 计数以百计（rows） | first_pass | failed | 31 |
| adapt-l1-04 | L1 | S3 / s3-cor-01 | 比例写成百分数（coverage：0.933333 → 93.3333） | first_pass | failed | 17 |
| adapt-l1-05 | L1 | S4 / s4-cor-01 | 比例写成百分数（positive_ratio：0.474138 → 47.4138） | first_pass | first_pass | 18 |
| adapt-l1-06 | L1 | S5 / s5-rob-01 | 计数以百计（n_valued） | first_pass | first_pass | 21 |
| adapt-l1-07 | L1 | S5 / s5-cor-01 | 日期写成紧凑串（date：2026-07-01 → 20260701） | first_pass | first_pass | 25 |
| adapt-l1-08 | L1 | S6 / s6-cor-01 | 日期写成紧凑串（date：2026-07-01 → 20260701） | first_pass | failed | 25 |
| adapt-l1-09 | L1 | S7 / s7-ops-01 | 比例写成百分数（ann_return_gross：0.0556468 → 5.56468） | first_pass | first_pass | 23 |
| adapt-l1-10 | L1 | S8 / s8-cor-01 | 价格以分计（reference_close：10.16 元 → 1016.0 分） | first_pass | first_pass | 16 |
| adapt-l2-01 | L2 | S1 / s1-ops-01 | 字段名 close 写成 Close（yfinance 的叫法） | first_pass | first_pass | 35 |
| adapt-l2-02 | L2 | S2 / s2-cor-01 | adjust 写成 hfq（源侧同义词，schema 侧是 post） | first_pass | first_pass | 34 |
| adapt-l2-03 | L2 | S2 / s2-eco-01 | 字段名 symbol 写成 ts_code（tushare 的叫法） | first_pass | failed | 24 |
| adapt-l2-04 | L2 | S3 / s3-eco-01 | eval_frequency 写成 1d（源侧同义词，schema 侧是 daily） | first_pass | first_pass | 59 |
| adapt-l2-05 | L2 | S4 / s4-cor-01 | tie_handling 写成 avg（源侧同义词，schema 侧是 average） | first_pass | first_pass | 19 |
| adapt-l2-06 | L2 | S5 / s5-rob-01 | value_semantics 写成 raw（源侧同义词，schema 侧是 score） | first_pass | first_pass | 20 |
| adapt-l2-07 | L2 | S6 / s6-eco-01 | 标的代码写成 sz002142（akshare 记法） | first_pass | failed | 35 |
| adapt-l2-08 | L2 | S6 / s6-rob-01 | rebalance_frequency 写成 1d（源侧同义词，schema 侧是 daily） | first_pass | failed | 47 |
| adapt-l2-09 | L2 | S7 / s7-ops-01 | adjust 写成 hfq（源侧同义词，schema 侧是 post） | first_pass | first_pass | 18 |
| adapt-l2-10 | L2 | S8 / s8-ops-01 | slippage_reference_price 写成 ref_close（源侧同义词，schema 侧是 reference_close） | first_pass | first_pass | 25 |
| adapt-l3-01 | L3 | S1 / s1-rob-01 | 上游不带 calendar_id 声明 | correct_flag | correct_flag | 23 |
| adapt-l3-02 | L3 | S2 / s2-eco-01 | 上游不带 calendar_id 声明 | correct_flag | correct_flag | 18 |
| adapt-l3-03 | L3 | S3 / s3-ops-01 | 上游不带 lookback 声明 | correct_flag | correct_flag | 16 |
| adapt-l3-04 | L3 | S4 / s4-cor-01 | 上游不带 quantiles 声明 | correct_flag | failed | 18 |
| adapt-l3-05 | L3 | S5 / s5-rob-01 | 上游不带 signal_frequency 声明 | correct_flag | correct_flag | 20 |
| adapt-l3-06 | L3 | S6 / s6-rob-01 | 上游不带 objective 声明 | correct_flag | failed | 24 |
| adapt-l3-07 | L3 | S6 / s6-rob-01 | 整条上游引用（依赖图的一条边）被删 | correct_flag | failed | 39 |
| adapt-l3-08 | L3 | S7 / s7-cor-01 | 上游不带 first_rebalance_day 声明 | correct_flag | correct_flag | 17 |
| adapt-l3-09 | L3 | S7 / s7-ops-01 | 整条上游引用（依赖图的一条边）被删 | correct_flag | failed | 27 |
| adapt-l3-10 | L3 | S8 / s8-cor-01 | 上游不带 visible_state_fields 声明 | correct_flag | failed | 19 |
