# 全量阶段指标表（六条跨阶段 + 逐阶段） — GeneBench 结果库（筛选：batch=a4；superseded=None）；口径见 ops/specs/GeneBench指标规格_v1.md §9 与 ops/reports/report_spec_v1.md

| config_id | arm | arm_kind | stage | n_runs | n_runs_denom | invalid_rate | honest_halt_rate | unsettled_rate | Decl | Set | Ovr | Align | Adj | Cal | CellAgree |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cfg-codex-deepseek | doc | protocol | S2 | 2 | 2 | 0 | 0 | 0 | unobservable | unobservable | 0.00938338 | 1 | 1 | 1 | 1 |
| cfg-codex-deepseek | hint | instruction_variant | S2 | 2 | 2 | 0 | 0 | 0 | — | — | 0.0278746 | — | — | — | — |
| cfg-codex-deepseek | strict | protocol | S2 | 2 | 2 | 0 | 0 | 0 | unobservable | unobservable | 0.0397727 | 1 | 1 | 1 | 0.998945 |

> set_version = 1.0.12
> reference_version = r1.0.19
> protocol_version = geneprotocol_v1@d6fbcaa08302（裸臂在协议轴上记 `geneprotocol_v1@none` —— 它们不投放协议工件，与协议臂并排不算混轴）
> channel = private
> 记录数 6；筛选 batch=a4；superseded=None
