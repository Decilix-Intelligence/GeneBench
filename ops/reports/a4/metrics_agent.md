# 全量 agent 指标表（18 项） — GeneBench 结果库（筛选：batch=a4；superseded=None）；口径见 ops/specs/GeneBench指标规格_v1.md §9 与 ops/reports/report_spec_v1.md

| config_id | arm | arm_kind | n_tasks | n_runs | SR | P@1 | pass^3 | ProgressRate | Steps | $ | Latency | Recov | Ovr | tokens_prompt | tokens_completion | unsettled_runs | budget_exhausted_runs | unbounded_requests | overreach_observable_runs | pass^3_tasks_with_3_runs | effect_settled_runs | unobservable_probes_mean |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cfg-codex-deepseek | doc | protocol | 1 | 2 | 0.5 | 0.5 |  | 0.5 | 30 | 0.59226 | 461.76 |  | 0.00938338 | 2449228 | 80954 | 0 | 1 | 6 | 2 | 0 | 1 | 0 |
| cfg-codex-deepseek | hint | instruction_variant | 1 | 2 | 0 | 0 |  | 0 | 45.5 | 0.813705 | 861.675 |  | 0.0278746 | 3475305 | 74452 | 0 | 1 | 8 | 2 | 0 | 0 | 0 |
| cfg-codex-deepseek | strict | protocol | 1 | 2 | 0.5 | 0 |  | 0.5 | 29.5 | 0.56339 | 379.375 |  | 0.0397727 | 2338937 | 73975 | 0 | 1 | 7 | 2 | 0 | 1 | 0 |

> set_version = 1.0.12
> reference_version = r1.0.19
> protocol_version = geneprotocol_v1@d6fbcaa08302（裸臂在协议轴上记 `geneprotocol_v1@none` —— 它们不投放协议工件，与协议臂并排不算混轴）
> channel = private
> 记录数 6；筛选 batch=a4；superseded=None
