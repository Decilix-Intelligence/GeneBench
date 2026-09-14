# Table A — GeneBench 结果库（筛选：batch=rehearsal_v1）；构造验收 / 接入验证，**不是实验数据**

| config_id | arm | arm_kind | n_tasks | n_runs | SR | pass@1 | pass^3 | ProgressRate | effect | Steps | $ | Latency | Recov | 越权率 | tokens_prompt | tokens_completion | pass^3_tasks_with_3_runs | overreach_observable_runs | unsettled_runs | unbounded_requests | budget_exhausted_runs | effect_settled_runs | set_version | reference_version | runner_version | image_digest |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cfg-codex-deepseek | open | baseline | 3 | 3 | 0.333333 | 0 |  | 0.333333 |  | 38 | 0.815173 | 608.848 |  | 0.0163043 | 5232102 | 108632 | 0 | 3 | 0 | 7 | 1 | 0 | 1.0.13 | r1.0.20 | 9089e489123a… | gb-cx-u@sha256:961e3878b28f… |
| cfg-codex-deepseek | strict | protocol | 3 | 3 | 0.666667 | 0 |  | 0.666667 | 77.4284 | 45.3333 | 1.17512 | 485.797 |  | 0.0259939 | 7530244 | 160643 | 0 | 3 | 1 | 15 | 1 | 1 | 1.0.13 | r1.0.20 | 9089e489123a… | gb-cx-u@sha256:961e3878b28f… |

> set_version = 1.0.13
> reference_version = r1.0.20
> protocol_version = geneprotocol_v1@d6fbcaa08302（裸臂在协议轴上记 `geneprotocol_v1@none` —— 它们不投放协议工件，与协议臂并排不算混轴）
> channel = private
> 记录数 6；筛选 batch=rehearsal_v1
