# 全量 agent 指标表（18 项） — GeneBench 结果库（筛选：batch=i_finrobot；superseded=None）；口径见 ops/specs/GeneBench指标规格_v1.md §9 与 ops/reports/report_spec_v1.md

| config_id | arm | arm_kind | n_tasks | n_runs | SR | P@1 | pass^3 | ProgressRate | Steps | $ | Latency | Recov | Ovr | tokens_prompt | tokens_completion | unsettled_runs | budget_exhausted_runs | unbounded_requests | overreach_observable_runs | pass^3_tasks_with_3_runs | effect_settled_runs | unobservable_probes_mean |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cfg-finrobot-deepseek | open | baseline | 1 | 1 | 1 | 1 |  | 1 | 13 | 0.367074 | 420.641 |  | 0 | 553630 | 93543 | 0 | 0 | 0 | 1 | 0 | 1 | 0 |
| cfg-finrobot-deepseek | strict | protocol | 1 | 1 | 1 | 1 |  | 1 | 8 | 0.104422 | 187.399 |  | 0 | 131141 | 35394 | 0 | 0 | 0 | 1 | 0 | 1 | 0 |

> set_version = 1.0.11
> reference_version = r1.0.19
> protocol_version = geneprotocol_v1@d6fbcaa08302（裸臂在协议轴上记 `geneprotocol_v1@none` —— 它们不投放协议工件，与协议臂并排不算混轴）
> channel = private
> 记录数 2；筛选 batch=i_finrobot；superseded=None
