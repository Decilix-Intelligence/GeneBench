# 主表（固定十九列） — GeneBench 结果库（筛选：batch=m6；superseded=None）；构造验收 / 接入验证，**不是实验数据**

| config_id | arm | arm_kind | n_tasks | n_runs | SR | P@1 | $ | Cov | Prov | Cell% | Adj | Fid | Decl | IC-agr | Set | Sig | ρ̄ | W-agr | Cons | ε-agr | Ledger | Audit | Ovr |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cfg-codex-deepseek | open | baseline | 8 | 10 | 0.625 | 0.375 | 0.992517 | 1 | 1 | 0.998945 | 1 | — | — | — | — | unobservable | unobservable | 1 | 1 | — | — |  |  |
| cfg-codex-deepseek | strict | protocol | 8 | 11 | 0.4375 | 0.4375 | 0.952783 | — | — | 1 | 1 | — | — | 1 | unobservable | — | — | 1 | 1 | — | 1 |  |  |

> set_version = 1.0.7
> reference_version = r1.0.8
> protocol_version = geneprotocol_v1@7e8ad97d1f7a（裸臂在协议轴上记 `geneprotocol_v1@none` —— 它们不投放协议工件，与协议臂并排不算混轴）
> channel = private
> 记录数 21；筛选 batch=m6；superseded=None
