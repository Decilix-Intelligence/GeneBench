# 探针字段判别力筛查（通道 `public`）

> 冻结实现与 ε 带取自 `/data/shared/genebench/snapshots/public_v1/epsilon`；沙箱 `/data/shared/genebench/scratch/1.1c/screen/public`。
> 闸门：{'baseline_reproduces': True, 'baseline_detail': [], 'patch_neutral:P-SELL': True, 'patch_neutral_detail:P-SELL': []}

| 题 | 阶段 | 探针字段 | 条件 | 结论 | 逐实现 | 组内分叉 | 跨实现分叉 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| s3-rob-02 | S3 | `eval_frequency` | `lookback=24` | **inconclusive** | — | 0 处 | 0 处 |
| s4-rob-02 | S4 | `holding_periods` | `ic_method=spearman` | **inconclusive** | — | 0 处 | 0 处 |
| s5-rob-02 | S5 | `signal_frequency` | `value_semantics=score` | **inconclusive** | — | 0 处 | 0 处 |
| s6-rob-02 | S6 | `rebalance_frequency` | `weighting_scheme=equal` | **material** | {'B1': 'material', 'B2': 'material', 'B3': 'material'} | 81 处 | 48 处 |
| s1-rob-02 | S1 | `data_version` | （无条件） | **inconclusive** | — | 0 处 | 0 处 |
| s2-rob-02 | S2 | `adjust` | `missing_row_policy=keep_missing` | **inconclusive** | — | 0 处 | 0 处 |
| s7-rob-02 | S7 | `sell_rule` | `rebalance_frequency=daily` | **material** | {'B1': 'material', 'B2': 'material', 'B3': 'material'} | 15 处 | 4 处 |
| s8-rob-02 | S8 | `slippage_reference_price` | `matching_frequency=daily` | **inconclusive** | — | 0 处 | 0 处 |

## 逐题理由

- **s3-rob-02** / `eval_frequency`：这套 harness 结构上量不到这个字段：S3 是因子求值，三份实现是 S7 的回测引擎 —— 它们不求值因子，只吃现成的信号面板。
- **s4-rob-02** / `holding_periods`：这套 harness 结构上量不到这个字段：S4 是 IC 分布，三份实现不出 IC；S4 的判据是 IC 族 ε（N-117），不是回测指标 ε。
- **s5-rob-02** / `signal_frequency`：这套 harness 结构上量不到这个字段：S5 是信号面，三份实现吃的是已经算好的信号，不重采样它。
- **s6-rob-02** / `rebalance_frequency`：实现 ['B1', 'B2', 'B3'] 上，不同取值之间有 81 处指标超出 ε 带
  - 逐实现超带条数：{'B1': 27, 'B2': 27, 'B3': 27}（共 81 处；跨实现分叉 48 处）
  - 逐指标（实测差 / ε）：`ann_return_gross` 0.01269–0.471 vs ε=0.005125（rel，9 处）；`ann_return_net` 0.02427–0.07677 vs ε=0.0002757（abs，9 处）；`ann_vol_net` 0.0003969–0.04085 vs ε=9.667e-05（rel，9 处）；`max_drawdown_net` 0.1236–0.3402 vs ε=3.746e-05（rel，9 处）；`sharpe_net` 0.2138–0.7091 vs ε=0.009341（rel，9 处）；`total_cost` 0.7171–0.9385 vs ε=2.851e-06（rel，9 处）；`turnover_one_way_mean` 0.7453–0.9442 vs ε=1.65e-05（rel，9 处）；`turnover_two_way_mean` 0.7364–0.9417 vs ε=1.665e-05（rel，9 处）；`win_rate_net` 0.001699–0.01101 vs ε=0.001652（rel，9 处）
  - harness：频率就是三份实现的 argv —— **不打任何补丁**，因此没有「补丁改了算法」这种可能，Gate 1（补丁中性）在这个字段上不适用，只跑 Gate 0（沙箱副本复现快照产物）。
- **s1-rob-02** / `data_version`：这套 harness 结构上量不到这个字段：三份冻结实现读的是一张定死的 csi300 面板（bt_input_csi300_v2.parquet），没有「数据版本」这个入口；换版本等于换输入面板，那是另一份标定不是一个开关。
- **s2-rob-02** / `adjust`：这套 harness 结构上量不到这个字段：复权口径在面板生成时就已经定死（post），三份实现拿到的是复权后的价；它们没有「换一种复权」的入口。
- **s7-rob-02** / `sell_rule`：实现 ['B1', 'B2', 'B3'] 上，不同取值之间有 15 处指标超出 ε 带
  - 逐实现超带条数：{'B1': 5, 'B2': 5, 'B3': 5}（共 15 处；跨实现分叉 4 处）
  - 逐指标（实测差 / ε）：`ann_vol_net` 0.0001188–0.0001464 vs ε=9.667e-05（rel，3 处）；`max_drawdown_net` 4.52e-05–0.0001553 vs ε=3.746e-05（rel，3 处）；`total_cost` 0.002678–0.002845 vs ε=2.851e-06（rel，3 处）；`turnover_one_way_mean` 0.003475–0.003485 vs ε=1.65e-05（rel，3 处）；`turnover_two_way_mean` 0.003466–0.003476 vs ε=1.665e-05（rel，3 处）
  - harness：两种读法由 P-SELL 开关切换（只加开关不改算法，Gate 1 逐指标验中性）；频率取本题声明的 rebalance_frequency。
- **s8-rob-02** / `slippage_reference_price`：这套 harness 结构上量不到这个字段：S8 是撮合模拟，三份实现按 close 成交、没有滑点参考价这个入口；它换入之后要重做一次面板与标定（题面自己也标着「等 slippage_reference_price 换入后一并跑」）。

verdict 为 material 的题，把证据条目写进 `genetask/schema.py::DIVERGENCE_EVIDENCE`
（本卡不改冻结根，条目原样落在 `ops/reports/public/materiality_evidence.json`）。
**任何一题 inconclusive 都不许翻锁 —— 「跑不起来」「量不到」都不是「没差别」。**
