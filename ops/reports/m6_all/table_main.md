# 主表（固定十九列） — GeneBench 结果库（筛选：batch=['m6', 'm6b']；superseded=None）；构造验收 / 接入验证，**不是实验数据**

| config_id | arm | arm_kind | n_tasks | n_runs | SR | P@1 | $ | Cov | Prov | Cell% | Adj | Fid | Decl | IC-agr | Set | Sig | ρ̄ | W-agr | Cons | ε-agr | Ledger | Audit | Ovr |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cfg-codex-deepseek | open | baseline | 12 | 14 | 0.5 | 0.25 | 0.944654 | 1 | 1 | 0.998945 | 1 | — | — | — | — | unobservable | unobservable | 1 | 1 | — | — | — | 0.0547945 |
| cfg-codex-deepseek | strict | protocol | 12 | 15 | 0.541667 | 0.291667 | 0.918698 | — | — | 1 | 1 | — | — | 1 | unobservable | — | — | 1 | 1 | — | 1 | — | 0.104439 |

> **set_version 混轴**：1.0.7 | 1.0.9 —— 这一列的行不是一个可比的读数
> **reference_version 混轴**：r1.0.14 | r1.0.8 —— 这一列的行不是一个可比的读数
> protocol_version = geneprotocol_v1@7e8ad97d1f7a（裸臂在协议轴上记 `geneprotocol_v1@none` —— 它们不投放协议工件，与协议臂并排不算混轴）
> channel = private
> 记录数 29；筛选 batch=['m6', 'm6b']；superseded=None
> 本表由 `--allow-mixed-axes` 显式放行；跨版本轴的行按 `(config_id, arm)` 合并，读数不可与单版本的表并排比较。
