# Table A — GeneBench 结果库（筛选：batch=v1demo）；构造验收 / 接入验证，**不是实验数据**

| config_id | arm | arm_kind | n_tasks | n_runs | SR | pass@1 | pass^3 | ProgressRate | effect | Steps | $ | Latency | Recov | 越权率 | tokens_prompt | tokens_completion | pass^3_tasks_with_3_runs | overreach_observable_runs | unsettled_runs | unbounded_requests | budget_exhausted_runs | effect_settled_runs | set_version | reference_version | runner_version | image_digest |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cfg-codex-deepseek | open | baseline | 4 | 4 | 0.25 | 0.25 |  | 0.25 | 100 | 20 | 0.302794 | 224.853 |  | 0.0283019 | 2439488 | 104395 | 0 | 4 | 0 | 12 | 4 | 1 | 1.0.13 | r1.0.20 | 33ab773224a4… | gb-cx-u@sha256:961e3878b28f… |
| cfg-codex-deepseek | strict | protocol | 4 | 4 | 0.25 | 0.25 |  | 0.25 | 100 | 20.75 | 0.284008 | 227.169 |  | 0.0111235 | 2346657 | 78412 | 0 | 4 | 0 | 10 | 4 | 1 | 1.0.13 | r1.0.20 | 33ab773224a4… | gb-cx-u@sha256:961e3878b28f… |

> set_version = 1.0.13
> reference_version = r1.0.20
> protocol_version = geneprotocol_v1@d6fbcaa08302（裸臂在协议轴上记 `geneprotocol_v1@none` —— 它们不投放协议工件，与协议臂并排不算混轴）
> channel = private
> 记录数 8；筛选 batch=v1demo
