# Table A — GeneBench 结果库（筛选：batch=m6_public；set_version=p1.0.0；superseded=None）；构造验收 / 接入验证，**不是实验数据**

| config_id | arm | arm_kind | n_tasks | n_runs | SR | pass@1 | pass^3 | ProgressRate | effect | Steps | $ | Latency | Recov | 越权率 | tokens_prompt | tokens_completion | pass^3_tasks_with_3_runs | overreach_observable_runs | unsettled_runs | unbounded_requests | budget_exhausted_runs | effect_settled_runs | set_version | reference_version | runner_version | image_digest |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cfg-codex-deepseek | open | baseline | 9 | 9 | 0.777778 | 0.333333 |  | 0.777778 | 96.875 | 59.8889 | 1.06538 | 406.849 |  | 0.00626204 | 20485816 | 435346 | 0 | 6 | 0 | 8 | 1 | 4 | p1.0.0 | r1.0.23 | a22b0bf33fa6… | gb-cx-u@sha256:961e3878b28f… |
| cfg-codex-deepseek | strict | protocol | 9 | 9 | 0.555556 | 0.444444 |  | 0.555556 | 100 | 47.6667 | 0.743372 | 462.846 |  | 0.00379687 | 14184831 | 340169 | 0 | 7 | 0 | 11 | 1 | 3 | p1.0.0 | r1.0.23 | a22b0bf33fa6… | gb-cx-u@sha256:961e3878b28f… |

> set_version = p1.0.0
> reference_version = r1.0.23
> protocol_version = geneprotocol_v1@d6fbcaa08302（裸臂在协议轴上记 `geneprotocol_v1@none` —— 它们不投放协议工件，与协议臂并排不算混轴）
> channel = public
> 记录数 18；筛选 batch=m6_public；set_version=p1.0.0；superseded=None
