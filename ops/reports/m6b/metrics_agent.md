# 全量 agent 指标表（18 项） — GeneBench 结果库（筛选：batch=m6b；superseded=None）；口径见 ops/specs/GeneBench指标规格_v1.md §9 与 ops/reports/report_spec_v1.md

| config_id | arm | arm_kind | n_tasks | n_runs | SR | P@1 | pass^3 | ProgressRate | Steps | $ | Latency | Recov | Ovr | tokens_prompt | tokens_completion | unsettled_runs | budget_exhausted_runs | unbounded_requests | overreach_observable_runs | pass^3_tasks_with_3_runs | effect_settled_runs | unobservable_probes_mean |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cfg-codex-deepseek | open | baseline | 4 | 4 | 0.25 | 0 |  | 0.25 | 36.75 | 0.824994 | 535.498 |  | 0.0547945 | 6830953 | 222997 | 0 | 0 | 16 | 4 | 0 | 0 | 0 |
| cfg-codex-deepseek | strict | protocol | 4 | 4 | 0.75 | 0 |  | 0.75 | 36.5 | 0.824962 | 493.644 |  | 0.104439 | 6861668 | 212661 | 0 | 0 | 18 | 4 | 0 | 0 | 0 |

> set_version = 1.0.9
> reference_version = r1.0.14
> protocol_version = geneprotocol_v1@7e8ad97d1f7a（裸臂在协议轴上记 `geneprotocol_v1@none` —— 它们不投放协议工件，与协议臂并排不算混轴）
> channel = private
> 记录数 8；筛选 batch=m6b；superseded=None
