# 全量阶段指标表（六条跨阶段 + 逐阶段） — GeneBench 结果库（筛选：batch=v1demo；superseded=None）；口径见 ops/specs/GeneBench指标规格_v1.md §9 与 ops/reports/report_spec_v1.md

| config_id | arm | arm_kind | stage | n_runs | n_runs_denom | invalid_rate | honest_halt_rate | unsettled_rate | Decl | Set | Ovr | Cov | PIT | Prov | Align | Adj | Cal | CellAgree | fid_day_rate | rho_p10 | rho_median | rho_mean | day_coverage | StateAgree | Sig |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cfg-codex-deepseek | open | baseline | S1 | 1 | 1 | 0 | 0 | 0 | unobservable | unobservable | 0.0615385 | 1 | 0.430769 | 1 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| cfg-codex-deepseek | open | baseline | S2 | 1 | 1 | 0 | 0 | 0 | — | — | 0.0295567 | n/a | n/a | n/a | — | — | — | — | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| cfg-codex-deepseek | open | baseline | S3 | 1 | 1 | 0 | 0 | 0 | — | — | 0.0740741 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | — | — | — | — | — | n/a | n/a |
| cfg-codex-deepseek | open | baseline | S5 | 1 | 1 | 0 | 0 | 0 | — | — | 0 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | — | — | — | — | — | — | — |
| cfg-codex-deepseek | strict | protocol | S1 | 1 | 1 | 0 | 0 | 0 | — | — | 0.0327869 | — | — | — | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| cfg-codex-deepseek | strict | protocol | S2 | 1 | 1 | 0 | 0 | 0 | — | — | 0.0078125 | n/a | n/a | n/a | — | — | — | — | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| cfg-codex-deepseek | strict | protocol | S3 | 1 | 1 | 0 | 0 | 0 | — | — | 0.0612245 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | — | — | — | — | — | n/a | n/a |
| cfg-codex-deepseek | strict | protocol | S5 | 1 | 1 | 0 | 0 | 0 | unobservable | unobservable | 0 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 1 | 1 | 1 | unobservable | 1 | unobservable | unobservable |

> set_version = 1.0.13
> reference_version = r1.0.20
> protocol_version = geneprotocol_v1@d6fbcaa08302（裸臂在协议轴上记 `geneprotocol_v1@none` —— 它们不投放协议工件，与协议臂并排不算混轴）
> channel = private
> 记录数 8；筛选 batch=v1demo；superseded=None
