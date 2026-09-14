# 全量阶段指标表（六条跨阶段 + 逐阶段） — GeneBench 结果库（筛选：batch=i_rehearsal_v2；superseded=None）；口径见 ops/specs/GeneBench指标规格_v1.md §9 与 ops/reports/report_spec_v1.md

| config_id | arm | arm_kind | stage | n_runs | n_runs_denom | invalid_rate | honest_halt_rate | unsettled_rate | Decl | Set | Ovr | Cov | PIT | Prov | Align | Adj | Cal | CellAgree | fid_day_rate | rho_p10 | rho_median | rho_mean | day_coverage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cfg-codex-deepseek | open | baseline | S1 | 1 | 1 | 0 | 0 | 0 | — | — | — | — | — | — | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| cfg-codex-deepseek | open | baseline | S2 | 1 | 1 | 0 | 0 | 0 | 1 | 1 | unobservable | n/a | n/a | n/a | 0.666667 | 1 | 0.977273 | 0.0344964 | n/a | n/a | n/a | n/a | n/a |
| cfg-codex-deepseek | open | baseline | S3 | 1 | 1 | 1 | 0 | 0 | — | — | — | n/a | n/a | n/a | n/a | n/a | n/a | n/a | — | — | — | — | — |
| cfg-codex-deepseek | strict | protocol | S1 | 1 | 1 | 0 | 0 | 0 | — | — | — | — | — | — | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| cfg-codex-deepseek | strict | protocol | S2 | 1 | 1 | 0 | 0 | 0 | 1 | 1 | unobservable | n/a | n/a | n/a | 1 | 1 | 1 | 0 | n/a | n/a | n/a | n/a | n/a |
| cfg-codex-deepseek | strict | protocol | S3 | 1 | 1 | 0 | 0 | 0 | — | — | — | n/a | n/a | n/a | n/a | n/a | n/a | n/a | — | — | — | — | — |

> set_version = 1.0.15
> reference_version = r1.0.22
> protocol_version = geneprotocol_v1@d6fbcaa08302（裸臂在协议轴上记 `geneprotocol_v1@none` —— 它们不投放协议工件，与协议臂并排不算混轴）
> channel = public
> 记录数 6；筛选 batch=i_rehearsal_v2；superseded=None
