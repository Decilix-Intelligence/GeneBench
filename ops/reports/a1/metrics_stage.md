# 全量阶段指标表（六条跨阶段 + 逐阶段） — GeneBench 结果库（筛选：batch=a1；superseded=None）；口径见 ops/specs/GeneBench指标规格_v1.md §9 与 ops/reports/report_spec_v1.md

| config_id | arm | arm_kind | stage | n_runs | n_runs_denom | invalid_rate | honest_halt_rate | unsettled_rate | Decl | Set | Ovr | Cov | PIT | Prov |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cfg-codex-deepseek | open | baseline | S1 | 2 | 2 | 0 | 0 | 0 | unobservable | unobservable | 0.011236 | 1 | 0.94868 | 1 |
| cfg-codex-deepseek | strict | protocol | S1 | 1 | 1 | 0 | 0 | 0 | unobservable | unobservable | 0.12 | 1 | 0.74 | 1 |
| cfg-openhands-deepseek | open | baseline | S1 | 1 | 1 | 1 | 0 | 0 | — | — | 0.106383 | — | — | — |
| cfg-openhands-deepseek | strict | protocol | S1 | 1 | 1 | 0 | 0 | 0 | — | — | 0.0487805 | — | — | — |

> set_version = 1.0.7
> reference_version = r1.0.7
> protocol_version = geneprotocol_v1@7e8ad97d1f7a（裸臂在协议轴上记 `geneprotocol_v1@none` —— 它们不投放协议工件，与协议臂并排不算混轴）
> channel = private
> 记录数 5；筛选 batch=a1；superseded=None
