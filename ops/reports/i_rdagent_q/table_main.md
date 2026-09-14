# 主表（固定十九列） — GeneBench 结果库（筛选：batch=i_rdagent_q；superseded=None）；构造验收 / 接入验证，**不是实验数据**

| config_id | arm | arm_kind | n_tasks | n_runs | SR | P@1 | $ | Cov | Prov | Cell% | Adj | Fid | Decl | IC-agr | Set | Sig | ρ̄ | W-agr | Cons | ε-agr | Ledger | Audit | Ovr |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cfg-rdagent_q-deepseek | open | baseline | 1 | 2 | 0.5 | 0 | 0.023309 |  |  |  |  | 0 | unobservable |  |  |  |  |  |  |  |  |  |  |
| cfg-rdagent_q-deepseek | strict | protocol | 1 | 2 | 1 | 0 | 0.0147495 |  |  |  |  | 0 | unobservable |  |  |  |  |  |  |  |  |  |  |

> set_version = 1.0.11
> reference_version = r1.0.19
> protocol_version = geneprotocol_v1@d6fbcaa08302（裸臂在协议轴上记 `geneprotocol_v1@none` —— 它们不投放协议工件，与协议臂并排不算混轴）
> channel = private
> 记录数 4；筛选 batch=i_rdagent_q；superseded=None
