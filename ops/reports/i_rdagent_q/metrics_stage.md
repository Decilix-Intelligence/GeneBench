# 全量阶段指标表（六条跨阶段 + 逐阶段） — GeneBench 结果库（筛选：batch=i_rdagent_q；superseded=None）；口径见 ops/specs/GeneBench指标规格_v1.md §9 与 ops/reports/report_spec_v1.md

| config_id | arm | arm_kind | stage | n_runs | n_runs_denom | invalid_rate | honest_halt_rate | unsettled_rate | Decl | Set | Ovr | fid_day_rate | rho_p10 | rho_median | rho_mean | day_coverage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cfg-rdagent_q-deepseek | open | baseline | S3 | 2 | 2 | 0 | 0 | 0 | unobservable | unobservable | 0 | 0 | unobservable | unobservable | unobservable | unobservable |
| cfg-rdagent_q-deepseek | strict | protocol | S3 | 2 | 2 | 0.5 | 0 | 0 | unobservable | unobservable | 0 | 0 | unobservable | unobservable | unobservable | unobservable |

> set_version = 1.0.11
> reference_version = r1.0.19
> protocol_version = geneprotocol_v1@d6fbcaa08302（裸臂在协议轴上记 `geneprotocol_v1@none` —— 它们不投放协议工件，与协议臂并排不算混轴）
> channel = private
> 记录数 4；筛选 batch=i_rdagent_q；superseded=None
