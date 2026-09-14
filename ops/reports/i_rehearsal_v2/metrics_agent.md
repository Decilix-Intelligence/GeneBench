# 全量 agent 指标表（18 项） — GeneBench 结果库（筛选：batch=i_rehearsal_v2；superseded=None）；口径见 ops/specs/GeneBench指标规格_v1.md §9 与 ops/reports/report_spec_v1.md

| config_id | arm | arm_kind | n_tasks | n_runs | SR | P@1 | pass^3 | ProgressRate | Steps | $ | Latency | Recov | Ovr | tokens_prompt | tokens_completion | unsettled_runs | budget_exhausted_runs | unbounded_requests | overreach_observable_runs | pass^3_tasks_with_3_runs | effect_settled_runs | unobservable_probes_mean |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cfg-codex-deepseek | open | baseline | 3 | 3 | 0.666667 | 0 |  | 0.666667 | 73 | 1.07355 | 906.705 |  |  | 6872163 | 149171 | 0 | 1 | 0 | 0 | 0 | 1 | 0 |
| cfg-codex-deepseek | strict | protocol | 3 | 3 | 0.333333 | 0 |  | 0.333333 | 93.6667 | 2.06749 | 1504.1 |  |  | 13364514 | 244013 | 0 | 2 | 0 | 0 | 0 | 1 | 0 |

> set_version = 1.0.15
> reference_version = r1.0.22
> protocol_version = geneprotocol_v1@d6fbcaa08302（裸臂在协议轴上记 `geneprotocol_v1@none` —— 它们不投放协议工件，与协议臂并排不算混轴）
> channel = public
> 记录数 6；筛选 batch=i_rehearsal_v2；superseded=None
