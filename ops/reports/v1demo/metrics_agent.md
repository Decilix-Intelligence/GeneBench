# 全量 agent 指标表（18 项） — GeneBench 结果库（筛选：batch=v1demo；superseded=None）；口径见 ops/specs/GeneBench指标规格_v1.md §9 与 ops/reports/report_spec_v1.md

| config_id | arm | arm_kind | n_tasks | n_runs | SR | P@1 | pass^3 | ProgressRate | Steps | $ | Latency | Recov | Ovr | tokens_prompt | tokens_completion | unsettled_runs | budget_exhausted_runs | unbounded_requests | overreach_observable_runs | pass^3_tasks_with_3_runs | effect_settled_runs | unobservable_probes_mean |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cfg-codex-deepseek | open | baseline | 4 | 4 | 0.25 | 0.25 |  | 0.25 | 20 | 0.302794 | 224.853 |  | 0.0283019 | 2439488 | 104395 | 0 | 4 | 12 | 4 | 0 | 1 | 0 |
| cfg-codex-deepseek | strict | protocol | 4 | 4 | 0.25 | 0.25 |  | 0.25 | 20.75 | 0.284008 | 227.169 |  | 0.0111235 | 2346657 | 78412 | 0 | 4 | 10 | 4 | 0 | 1 | 0 |

> set_version = 1.0.13
> reference_version = r1.0.20
> protocol_version = geneprotocol_v1@d6fbcaa08302（裸臂在协议轴上记 `geneprotocol_v1@none` —— 它们不投放协议工件，与协议臂并排不算混轴）
> channel = private
> 记录数 8；筛选 batch=v1demo；superseded=None
