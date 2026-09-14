# 主表（固定十九列） — GeneBench 结果库（筛选：batch=a4；superseded=None）；构造验收 / 接入验证，**不是实验数据**

| config_id | arm | arm_kind | n_tasks | n_runs | SR | P@1 | $ | Cov | Prov | Cell% | Adj | Fid | Decl | IC-agr | Set | Sig | ρ̄ | W-agr | Cons | ε-agr | Ledger | Audit | Ovr |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cfg-codex-deepseek | doc | protocol | 1 | 2 | 0.5 | 0.5 | 0.59226 |  |  | 1 | 1 |  |  |  |  |  |  |  |  |  |  |  |  |
| cfg-codex-deepseek | hint | instruction_variant | 1 | 2 | 0 | 0 | 0.813705 |  |  | — | — |  |  |  |  |  |  |  |  |  |  |  |  |
| cfg-codex-deepseek | strict | protocol | 1 | 2 | 0.5 | 0 | 0.56339 |  |  | 0.998945 | 1 |  |  |  |  |  |  |  |  |  |  |  |  |

> set_version = 1.0.12
> reference_version = r1.0.19
> protocol_version = geneprotocol_v1@d6fbcaa08302（裸臂在协议轴上记 `geneprotocol_v1@none` —— 它们不投放协议工件，与协议臂并排不算混轴）
> channel = private
> 记录数 6；筛选 batch=a4；superseded=None
