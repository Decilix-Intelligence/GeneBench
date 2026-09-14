# 全量 agent 指标表（18 项） — GeneBench 结果库（筛选：batch=a1；superseded=None）；口径见 ops/specs/GeneBench指标规格_v1.md §9 与 ops/reports/report_spec_v1.md

| config_id | arm | arm_kind | n_tasks | n_runs | SR | P@1 | pass^3 | ProgressRate | Steps | $ | Latency | Recov | Ovr | tokens_prompt | tokens_completion | unsettled_runs | budget_exhausted_runs | unbounded_requests | overreach_observable_runs | pass^3_tasks_with_3_runs | effect_settled_runs | unobservable_probes_mean |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cfg-codex-deepseek | open | baseline | 1 | 2 | 0.5 | 0.5 |  | 0.5 | 35.5 | 0.579832 | 392.555 |  | 0.011236 | 2454238 | 60454 | 0 | 1 | 8 | 2 | 0 | 1 | 0 |
| cfg-codex-deepseek | strict | protocol | 1 | 1 | 1 | 1 |  | 1 | 21 | 0.336688 | 255.111 |  | 0.12 | 679601 | 28533 | 0 | 1 | 6 | 1 | 0 | 1 | 0 |
| cfg-openhands-deepseek | open | baseline | 1 | 1 | 0 | 0 |  | 0 | 34 | 0.496495 | 252.371 |  | 0.106383 | 1027018 | 33793 | 0 | 0 | 5 | 1 | 0 | 0 | 0 |
| cfg-openhands-deepseek | strict | protocol | 1 | 1 | 0 | 0 |  | 0 | 37 | 0.534487 | 238.314 |  | 0.0487805 | 1113224 | 33840 | 0 | 0 | 2 | 1 | 0 | 0 | 0 |

> set_version = 1.0.7
> reference_version = r1.0.7
> protocol_version = geneprotocol_v1@7e8ad97d1f7a（裸臂在协议轴上记 `geneprotocol_v1@none` —— 它们不投放协议工件，与协议臂并排不算混轴）
> channel = private
> 记录数 5；筛选 batch=a1；superseded=None
