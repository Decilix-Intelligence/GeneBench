# 全量阶段指标表（六条跨阶段 + 逐阶段） — GeneBench 结果库（筛选：batch=m6b；superseded=None）；口径见 ops/specs/GeneBench指标规格_v1.md §9 与 ops/reports/report_spec_v1.md

| config_id | arm | arm_kind | stage | n_runs | n_runs_denom | invalid_rate | honest_halt_rate | unsettled_rate | Decl | Set | Ovr | Audit | FillSelfConsistent | SlipSelfConsistent | legal_transitions | events_monotone | orders_replayable | fills_linked_to_orders |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cfg-codex-deepseek | open | baseline | S8 | 4 | 4 | 1 | 0 | 0 | — | — | 0.0547945 | — | — | — | — | — | — | — |
| cfg-codex-deepseek | strict | protocol | S8 | 4 | 4 | 1 | 0 | 0 | — | — | 0.104439 | — | — | — | — | — | — | — |

> set_version = 1.0.9
> reference_version = r1.0.14
> protocol_version = geneprotocol_v1@7e8ad97d1f7a（裸臂在协议轴上记 `geneprotocol_v1@none` —— 它们不投放协议工件，与协议臂并排不算混轴）
> channel = private
> 记录数 8；筛选 batch=m6b；superseded=None
