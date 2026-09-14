# 结果库回填与核对（卡 5.4）

库：`/data/shared/genebench/results/v1/results.jsonl`；记录 **74** 条；版本轴组合 **14** 种。

## 怎么用

```bash
PY=/data/shared/genebench/env/bin/python; cd /data/shared/genebench/repo
# 新结算之后把这一批收进库（幂等，收两遍不会重）
$PY ops/results_db.py ingest --batch <batch>
# 库里都有哪些版本轴组合（混轴在这里看得见）
$PY ops/results_db.py versions
# 三张表，三种格式；--filter 可重复，值用逗号分隔即「或」
$PY ops/mk_tables.py --table a --format csv   --filter batch=m6            --out ops/reports/m6
$PY ops/mk_tables.py --table b --format md    --filter set_version=1.0.12  --out /tmp/x
$PY ops/mk_tables.py --table adaptation --format latex --filter batch=adapt --out /tmp/x
# 跨版本合表：默认拒绝，必须显式放行（放行后表脚注会写明混了哪些值）
$PY ops/mk_tables.py --table a --format csv --filter batch=m6,m6b --allow-mixed-axes --out /tmp/x
```

四条版本轴 = `set_version` / `reference_version` / `protocol_version` / `channel`
（票据 N-207 的「四个版本字段」）。**缺一即拒**：一条不知道自己是哪一版跑出来的记录，
进了库就再也切不开。主键是 `(batch, run_id)` 而不是裸 `run_id` —— 见下面的重名表。

## 收了哪些批

| batch | records.json | 入库 | 重复 | protocol_version | channel |
| --- | --- | --- | --- | --- | --- |
| `a1` | 5 | 0 | 5 | `geneprotocol_v1@7e8ad97d1f7a` | private |
| `a4` | 6 | 0 | 6 | `geneprotocol_v1@d6fbcaa08302` | private |
| `h_claude-code` | 2 | 0 | 2 | `geneprotocol_v1@d6fbcaa08302` | private |
| `h_gemini-cli` | 2 | 0 | 2 | `geneprotocol_v1@d6fbcaa08302` | private |
| `h_grok-cli` | 2 | 0 | 2 | `geneprotocol_v1@d6fbcaa08302` | private |
| `h_opencode` | 2 | 0 | 2 | `geneprotocol_v1@d6fbcaa08302` | private |
| `i_alphaagent` | 2 | 0 | 2 | `geneprotocol_v1@d6fbcaa08302` | private |
| `i_finmem` | 2 | 0 | 2 | `geneprotocol_v1@d6fbcaa08302` | private |
| `i_finrobot` | 2 | 0 | 2 | `geneprotocol_v1@d6fbcaa08302` | private |
| `i_rdagent_q` | 4 | 0 | 4 | `geneprotocol_v1@d6fbcaa08302` | private |
| `i_rehearsal` | 2 | 0 | 2 | `geneprotocol_v1@d6fbcaa08302` | private |
| `i_tradingagents` | 6 | 0 | 6 | `geneprotocol_v1@d6fbcaa08302` | private |
| `m6` | 21 | 0 | 21 | `geneprotocol_v1@7e8ad97d1f7a` | private |
| `m6b` | 8 | 0 | 8 | `geneprotocol_v1@7e8ad97d1f7a` | private |
| `v1demo` | 8 | 0 | 8 | `geneprotocol_v1@d6fbcaa08302` | private |

## 版本轴组合

| set_version | reference_version | protocol_version | channel | run 数 | 批 |
| --- | --- | --- | --- | --- | --- |
| 1.0.11 | r1.0.18 | `geneprotocol_v1@d6fbcaa08302` | private | 2 | h_claude-code, h_gemini-cli |
| 1.0.11 | r1.0.18 | `geneprotocol_v1@none` | private | 2 | h_claude-code, h_gemini-cli |
| 1.0.11 | r1.0.19 | `geneprotocol_v1@d6fbcaa08302` | private | 10 | h_grok-cli, h_opencode, i_alphaagent, i_finmem, i_finrobot, i_rdagent_q, i_tradingagents |
| 1.0.11 | r1.0.19 | `geneprotocol_v1@none` | private | 10 | h_grok-cli, h_opencode, i_alphaagent, i_finmem, i_finrobot, i_rdagent_q, i_tradingagents |
| 1.0.12 | r1.0.19 | `geneprotocol_v1@d6fbcaa08302` | private | 3 | a4, i_rehearsal |
| 1.0.12 | r1.0.19 | `geneprotocol_v1@none` | private | 5 | a4, i_rehearsal |
| 1.0.13 | r1.0.20 | `geneprotocol_v1@d6fbcaa08302` | private | 4 | v1demo |
| 1.0.13 | r1.0.20 | `geneprotocol_v1@none` | private | 4 | v1demo |
| 1.0.7 | r1.0.7 | `geneprotocol_v1@7e8ad97d1f7a` | private | 2 | a1 |
| 1.0.7 | r1.0.7 | `geneprotocol_v1@none` | private | 3 | a1 |
| 1.0.7 | r1.0.8 | `geneprotocol_v1@7e8ad97d1f7a` | private | 11 | m6 |
| 1.0.7 | r1.0.8 | `geneprotocol_v1@none` | private | 10 | m6 |
| 1.0.9 | r1.0.14 | `geneprotocol_v1@7e8ad97d1f7a` | private | 4 | m6b |
| 1.0.9 | r1.0.14 | `geneprotocol_v1@none` | private | 4 | m6b |

## 已知限制

- **适配赛道还没有记录**：`scorer.adaptation.AdaptationResult.as_record` 出的记录不带四条版本轴（也没有 `task_id` / `seq`），`ops/reports/adapt/records.json` 现在是空的（真跑被红线 B2 闸住）。库的适配赛道通路已经通（`--table adaptation` 出得来表，身份键走 `IDENTITY_ADAPT`），但要真收记录，得先让 `adapt_report.py` 把四条轴写进记录。
- **公开通道没有可结算的 run**：`ops/reports/public/` 里只有三控与对账，没有 `records.json`。所以库里 `channel` 现在只有 `private` 一个取值；回填时它是**声明**的（`axes_source.channel= backfill:declared`），不是从记录里读出来的 —— 记录里根本没有这一项。
- **协议轴是逐 run 反算的**（红队 5.rt finding 4 之后）：取 `runs_in/<batch>/<run_id>/inject.json` 里这次注入真的拿到的 `work/protocol/{validate_artifact.py,README.md,contract.md}` 三件的 sha。裸臂不发协议工件 → 逐 run 记 `geneprotocol_v1@none`（**显式**「这次没有协议工件」，不是「不知道」）；同一批里 `none` 与摘要并排**不算混轴**（`results_db.mixed_axes` 按 arm_kind 分组判），协议臂之间出现两个摘要才算。一批里反算出两个摘要 → 拒（人来裁定）；连 `inject.json` 都读不到 → 拒，不拿今天仓库里的版本去追认。纯裸臂的批（oracle / 控制批）现在收得进来了。

## 跨批重名的 run_id（主键必须带 batch 的理由）

- `s1-cor-01.open.cfg-codex-deepseek.r01`：m6, v1demo
- `s1-cor-01.strict.cfg-codex-deepseek.r01`：m6, v1demo
- `s2-cor-01.open.cfg-codex-deepseek.r01`：m6, v1demo
- `s2-cor-01.strict.cfg-codex-deepseek.r01`：a4, m6, v1demo
- `s3-cor-01.open.cfg-codex-deepseek.r01`：m6, v1demo
- `s3-cor-01.strict.cfg-codex-deepseek.r01`：m6, v1demo
- `s5-cor-01.open.cfg-codex-deepseek.r01`：m6, v1demo
- `s5-cor-01.strict.cfg-codex-deepseek.r01`：m6, v1demo

## 与既有 CSV 逐格核对

| batch | Table A | Table B |
| --- | --- | --- |
| `a1` | 逐格相同 | 逐格相同 |
| `a4` | 逐格相同 | 逐格相同 |
| `h_claude-code` | 逐格相同 | 逐格相同 |
| `h_gemini-cli` | 逐格相同 | 逐格相同 |
| `h_grok-cli` | 逐格相同 | 逐格相同 |
| `h_opencode` | 逐格相同 | 逐格相同 |
| `i_alphaagent` | 逐格相同 | 逐格相同 |
| `i_finmem` | 逐格相同 | 逐格相同 |
| `i_finrobot` | 逐格相同 | 逐格相同 |
| `i_rdagent_q` | 逐格相同 | 逐格相同 |
| `i_rehearsal` | 逐格相同 | 逐格相同 |
| `i_tradingagents` | 逐格相同 | 逐格相同 |
| `m6` | 逐格相同 | 逐格相同 |
| `m6b` | 逐格相同 | 逐格相同 |
| `v1demo` | 逐格相同 | 逐格相同 |
