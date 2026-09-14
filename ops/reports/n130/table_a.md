# Table A — GeneBench 结果库（筛选：batch=n130）；构造验收 / 接入验证，**不是实验数据**

| config_id | arm | arm_kind | n_tasks | n_runs | SR | pass@1 | pass^3 | ProgressRate | effect | Steps | $ | Latency | Recov | 越权率 | tokens_prompt | tokens_completion | pass^3_tasks_with_3_runs | overreach_observable_runs | unsettled_runs | unbounded_requests | budget_exhausted_runs | effect_settled_runs | set_version | reference_version | runner_version | image_digest |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cfg-codex-deepseek | open | baseline | 1 | 1 | 0 | 0 |  | 0 |  | 64 | 1.84395 | 1464.16 |  | 0 | 3960233 | 76853 | 0 | 1 | 0 | 0 | 0 | 0 | 1.0.13 | r1.0.20 | 66f921b78275… | gb-cx-u@sha256:961e3878b28f… |
| cfg-codex-deepseek | strict | protocol | 1 | 1 | 1 | 0 |  | 1 |  | 87 | 2.56474 | 1967.35 |  | 0 | 5580144 | 82935 | 0 | 1 | 0 | 0 | 0 | 0 | 1.0.13 | r1.0.20 | 66f921b78275… | gb-cx-u@sha256:961e3878b28f… |

> set_version = 1.0.13
> reference_version = r1.0.20
> protocol_version = geneprotocol_v1@d6fbcaa08302（裸臂在协议轴上记 `geneprotocol_v1@none` —— 它们不投放协议工件，与协议臂并排不算混轴）
> channel = private
> 记录数 2；筛选 batch=n130
