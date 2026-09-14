# Table B — GeneBench 结果库（筛选：batch=i_rehearsal_v1）；构造验收 / 接入验证，**不是实验数据**

| arm | arm_kind | config_id | image_digest | n_runs | reference_version | runner_version | set_version | Adj | Align | Cal | honest_halts | invalid_rate | n_runs_denom | stage | unobservable_probes_mean |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| open | baseline | cfg-quantagent-deepseek | MIXED:gb-quantagent-u@sha256:0dd347bb34ad…\|gb-quantagent-u@sha256:22ffdf7b0ca4…\|gb-quantagent-u@sha256:cfed9e93e2ec… | 3 | r1.0.20 | 9089e489123a… | 1.0.13 | 1 | 1 | 1 | 0 | 0 | 3 | S2 | 0 |
| strict | protocol | cfg-quantagent-deepseek | MIXED:gb-quantagent-u@sha256:0dd347bb34ad…\|gb-quantagent-u@sha256:22ffdf7b0ca4…\|gb-quantagent-u@sha256:cfed9e93e2ec… | 3 | r1.0.20 | 9089e489123a… | 1.0.13 | 1 | 1 | 1 | 0 | 0 | 3 | S2 | 0 |

> set_version = 1.0.13
> reference_version = r1.0.20
> protocol_version = geneprotocol_v1@d6fbcaa08302（裸臂在协议轴上记 `geneprotocol_v1@none` —— 它们不投放协议工件，与协议臂并排不算混轴）
> channel = private
> 记录数 6；筛选 batch=i_rehearsal_v1
