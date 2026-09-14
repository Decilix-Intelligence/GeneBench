# 全量 agent 指标表（18 项） — GeneBench 结果库（筛选：batch=m6；superseded=None）；口径见 ops/specs/GeneBench指标规格_v1.md §9 与 ops/reports/report_spec_v1.md

| config_id | arm | arm_kind | n_tasks | n_runs | SR | P@1 | pass^3 | ProgressRate | Steps | $ | Latency | Recov | Ovr | tokens_prompt | tokens_completion | unsettled_runs | budget_exhausted_runs | unbounded_requests | overreach_observable_runs | pass^3_tasks_with_3_runs | effect_settled_runs | unobservable_probes_mean |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cfg-codex-deepseek | open | baseline | 8 | 10 | 0.625 | 0.375 | 0 | 0.625 | 45.1 | 0.992517 | 842.91 |  | 0.0179112 | 20947583 | 536544 | 0 | 5 | 66 | 10 | 1 | 4 | 0 |
| cfg-codex-deepseek | strict | protocol | 8 | 11 | 0.4375 | 0.4375 | 0 | 0.4375 | 42.7273 | 0.952783 | 615.148 |  | 0.0333002 | 22389144 | 476814 | 0 | 5 | 65 | 10 | 1 | 3 | 0 |

> set_version = 1.0.7
> reference_version = r1.0.8
> protocol_version = geneprotocol_v1@7e8ad97d1f7a（裸臂在协议轴上记 `geneprotocol_v1@none` —— 它们不投放协议工件，与协议臂并排不算混轴）
> channel = private
> 记录数 21；筛选 batch=m6；superseded=None
