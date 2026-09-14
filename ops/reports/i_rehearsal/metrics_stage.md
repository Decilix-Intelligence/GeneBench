# 全量阶段指标表（六条跨阶段 + 逐阶段） — GeneBench 结果库（筛选：batch=i_rehearsal；superseded=None）；口径见 ops/specs/GeneBench指标规格_v1.md §9 与 ops/reports/report_spec_v1.md

| config_id | arm | arm_kind | stage | n_runs | n_runs_denom | invalid_rate | honest_halt_rate | unsettled_rate | Decl | Set | Ovr | StateAgree | Sig | fid_day_rate | rho_p10 | rho_median | rho_mean | day_coverage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cfg-stockagent-deepseek | open | baseline | S5 | 1 | 1 | 0 | 0 | 0 | unobservable | unobservable | 0 | unobservable | unobservable | unobservable | unobservable | unobservable | unobservable | unobservable |
| cfg-stockagent-deepseek | strict | protocol | S5 | 1 | 1 | 0 | 0 | 0 | unobservable | unobservable | 0 | unobservable | unobservable | unobservable | unobservable | unobservable | unobservable | unobservable |

> set_version = 1.0.12
> reference_version = r1.0.19
> protocol_version = geneprotocol_v1@d6fbcaa08302（裸臂在协议轴上记 `geneprotocol_v1@none` —— 它们不投放协议工件，与协议臂并排不算混轴）
> channel = private
> 记录数 2；筛选 batch=i_rehearsal；superseded=None
