# 全量 agent 指标表（18 项） — GeneBench 结果库（筛选：batch=n130；superseded=None）；口径见 ops/specs/GeneBench指标规格_v1.md §9 与 ops/reports/report_spec_v1.md

| config_id | arm | arm_kind | n_tasks | n_runs | SR | P@1 | pass^3 | ProgressRate | Steps | $ | Latency | Recov | Ovr | tokens_prompt | tokens_completion | unsettled_runs | budget_exhausted_runs | unbounded_requests | overreach_observable_runs | pass^3_tasks_with_3_runs | effect_settled_runs | unobservable_probes_mean |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cfg-codex-deepseek | open | baseline | 1 | 1 | 0 | 0 |  | 0 | 64 | 1.84395 | 1464.16 |  | 0 | 3960233 | 76853 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| cfg-codex-deepseek | strict | protocol | 1 | 1 | 1 | 0 |  | 1 | 87 | 2.56474 | 1967.35 |  | 0 | 5580144 | 82935 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |

> set_version = 1.0.13
> reference_version = r1.0.20
> protocol_version = geneprotocol_v1@d6fbcaa08302（裸臂在协议轴上记 `geneprotocol_v1@none` —— 它们不投放协议工件，与协议臂并排不算混轴）
> channel = private
> 记录数 2；筛选 batch=n130；superseded=None
