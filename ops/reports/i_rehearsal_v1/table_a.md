# Table A — GeneBench 结果库（筛选：batch=i_rehearsal_v1）；构造验收 / 接入验证，**不是实验数据**

| config_id | arm | arm_kind | n_tasks | n_runs | SR | pass@1 | pass^3 | ProgressRate | effect | Steps | $ | Latency | Recov | 越权率 | tokens_prompt | tokens_completion | pass^3_tasks_with_3_runs | overreach_observable_runs | unsettled_runs | unbounded_requests | budget_exhausted_runs | effect_settled_runs | set_version | reference_version | runner_version | image_digest |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cfg-quantagent-deepseek | open | baseline | 1 | 3 | 0.333333 | 0 |  | 0.333333 |  |  |  | 227.104 |  | 0 |  |  | 0 | 3 | 1 | 0 | 0 | 0 | 1.0.13 | r1.0.20 | 9089e489123a… | MIXED:gb-quantagent-u@sha256:0dd347bb34ad…\|gb-quantagent-u@sha256:22ffdf7b0ca4…\|gb-quantagent-u@sha256:cfed9e93e2ec… |
| cfg-quantagent-deepseek | strict | protocol | 1 | 3 | 0.333333 | 0 |  | 0.333333 |  |  |  | 226.742 |  | 0 |  |  | 0 | 3 | 1 | 0 | 0 | 0 | 1.0.13 | r1.0.20 | 9089e489123a… | MIXED:gb-quantagent-u@sha256:0dd347bb34ad…\|gb-quantagent-u@sha256:22ffdf7b0ca4…\|gb-quantagent-u@sha256:cfed9e93e2ec… |

> set_version = 1.0.13
> reference_version = r1.0.20
> protocol_version = geneprotocol_v1@d6fbcaa08302（裸臂在协议轴上记 `geneprotocol_v1@none` —— 它们不投放协议工件，与协议臂并排不算混轴）
> channel = private
> 记录数 6；筛选 batch=i_rehearsal_v1
