# 全量 agent 指标表（18 项） — GeneBench 结果库（筛选：batch=['m6', 'm6b']）；口径见 ops/specs/GeneBench指标规格_v1.md §9 与 ops/reports/report_spec_v1.md

| config_id | arm | arm_kind | n_tasks | n_runs | SR | P@1 | pass^3 | ProgressRate | Steps | $ | Latency | Recov | Ovr | tokens_prompt | tokens_completion | unsettled_runs | budget_exhausted_runs | unbounded_requests | overreach_observable_runs | pass^3_tasks_with_3_runs | effect_settled_runs | unobservable_probes_mean |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cfg-codex-deepseek | open | baseline | 12 | 14 | 0.5 | 0.25 | 0 | 0.5 | 42.7143 | 0.944654 | 755.078 |  | 0.021021 | 27778536 | 759541 | 0 | 5 | 82 | 14 | 1 | 4 | 0 |
| cfg-codex-deepseek | strict | protocol | 12 | 15 | 0.541667 | 0.291667 | 0 | 0.541667 | 41.0667 | 0.918698 | 582.746 |  | 0.0446764 | 29250812 | 689475 | 0 | 5 | 83 | 14 | 1 | 3 | 0 |

> **set_version 混轴**：1.0.7 | 1.0.9 —— 这一列的行不是一个可比的读数
> **reference_version 混轴**：r1.0.14 | r1.0.8 —— 这一列的行不是一个可比的读数
> protocol_version = geneprotocol_v1@7e8ad97d1f7a（裸臂在协议轴上记 `geneprotocol_v1@none` —— 它们不投放协议工件，与协议臂并排不算混轴）
> channel = private
> 记录数 29；筛选 batch=['m6', 'm6b']
> 本表由 `--allow-mixed-axes` 显式放行；跨版本轴的行按 `(config_id, arm)` 合并，读数不可与单版本的表并排比较。
