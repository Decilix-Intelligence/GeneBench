# 主表（固定十九列） — GeneBench 结果库（筛选：batch=i_rehearsal_v2；superseded=None）；构造验收 / 接入验证，**不是实验数据**

| config_id | arm | arm_kind | n_tasks | n_runs | SR | P@1 | $ | Cov | Prov | Cell% | Adj | Fid | Decl | IC-agr | Set | Sig | ρ̄ | W-agr | Cons | ε-agr | Ledger | Audit | Ovr |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cfg-codex-deepseek | open | baseline | 3 | 3 | 0.666667 | 0 | 1.07355 | — | — | 0.0344964 | 1 | — | — |  |  |  |  |  |  |  |  |  |  |
| cfg-codex-deepseek | strict | protocol | 3 | 3 | 0.333333 | 0 | 2.06749 | — | — | 0 | 1 | — | — |  |  |  |  |  |  |  |  |  |  |

> set_version = 1.0.15
> reference_version = r1.0.22
> protocol_version = geneprotocol_v1@d6fbcaa08302（裸臂在协议轴上记 `geneprotocol_v1@none` —— 它们不投放协议工件，与协议臂并排不算混轴）
> channel = public
> 记录数 6；筛选 batch=i_rehearsal_v2；superseded=None
