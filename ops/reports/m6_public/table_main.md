# 主表（固定十九列） — GeneBench 结果库（筛选：batch=m6_public；set_version=p1.0.0；superseded=None）；构造验收 / 接入验证，**不是实验数据**

| config_id | arm | arm_kind | n_tasks | n_runs | SR | P@1 | $ | Cov | Prov | Cell% | Adj | Fid | Decl | IC-agr | Set | Sig | ρ̄ | W-agr | Cons | ε-agr | Ledger | Audit | Ovr |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cfg-codex-deepseek | open | baseline | 9 | 9 | 0.777778 | 0.333333 | 1.06538 | 1 | 1 | — | — | — | — | 0.875 | 1 | unobservable | 1 | 1 | 1 | — | 1 | — | — |
| cfg-codex-deepseek | strict | protocol | 9 | 9 | 0.555556 | 0.444444 | 0.743372 | 1 | 1 | — | — | — | — | — | — | unobservable | 1 | 1 | 1 | — | 1 | — | — |

> set_version = p1.0.0
> reference_version = r1.0.23
> protocol_version = geneprotocol_v1@d6fbcaa08302（裸臂在协议轴上记 `geneprotocol_v1@none` —— 它们不投放协议工件，与协议臂并排不算混轴）
> channel = public
> 记录数 18；筛选 batch=m6_public；set_version=p1.0.0；superseded=None
