# 全量 agent 指标表（18 项） — GeneBench 结果库（筛选：batch=m6_public；set_version=p1.0.0；superseded=None）；口径见 ops/specs/GeneBench指标规格_v1.md §9 与 ops/reports/report_spec_v1.md

| config_id | arm | arm_kind | n_tasks | n_runs | SR | P@1 | pass^3 | ProgressRate | Steps | $ | Latency | Recov | Ovr | tokens_prompt | tokens_completion | unsettled_runs | budget_exhausted_runs | unbounded_requests | overreach_observable_runs | pass^3_tasks_with_3_runs | effect_settled_runs | unobservable_probes_mean |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cfg-codex-deepseek | open | baseline | 9 | 9 | 0.777778 | 0.333333 |  | 0.777778 | 59.8889 | 1.06538 | 406.849 |  | 0.00626204 | 20485816 | 435346 | 0 | 1 | 8 | 6 | 0 | 4 | 0 |
| cfg-codex-deepseek | strict | protocol | 9 | 9 | 0.555556 | 0.444444 |  | 0.555556 | 47.6667 | 0.743372 | 462.846 |  | 0.00379687 | 14184831 | 340169 | 0 | 1 | 11 | 7 | 0 | 3 | 0.111111 |

> set_version = p1.0.0
> reference_version = r1.0.23
> protocol_version = geneprotocol_v1@d6fbcaa08302（裸臂在协议轴上记 `geneprotocol_v1@none` —— 它们不投放协议工件，与协议臂并排不算混轴）
> channel = public
> 记录数 18；筛选 batch=m6_public；set_version=p1.0.0；superseded=None
