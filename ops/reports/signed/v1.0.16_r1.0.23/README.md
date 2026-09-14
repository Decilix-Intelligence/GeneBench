# 签字包 v1.0.16_r1.0.23（v1.0.16 / p1.0.0 / r1.0.23 最终卡收口）—— 私有通道

* 通道 `private`
* 任务集 `1.0.16`（根 `d9ebd5412ac4cc7e…`）
* 参考面 `r1.0.23`（根 `dddabe440163b36e…`）
* git HEAD `9c32a8339dde`

**私有通道**（任务集轴 `1.0.x`）。主表（`m6_all`）= Codex 统一基座 · M6-lite 两次 pass（**混轴**，见 `v1_0_readiness.md` §4）；另含 `m6` 的三控与破坏样本、oracle 与实例层 O1 矩阵、跨版本探针、适配赛道那一套。私有通道的夹具与标定**不公开**，这份包是内部签字用的完整记录。

> **这份包只装本通道的件。**公开通道那一份在 `ops/reports/signed/public_vp1.0.0_r1.0.23/`。
> 两条通道的题面逐字相同、**夹具字节不同**，因此任务集轴不同、数不可直接合并 ——
> 「可比」的判据是四条轴全部相同（见 `RELEASE_MANIFEST.json` 的 `axes.comparable_iff`）。
> 跨通道通用的口径件（已知限制 / 报告规格 / 演练 / 投放说明 / 发布清单 / 版本轴 /
> 协议子树清单）两份包里都有，且逐字节相同。

## 哪张表能引用

| 文件 | 是什么 |
| --- | --- |
| `m6_all__table_main.csv` | **发布表**：⑩ 的固定十九列（`SR / P@1 / $` + 每阶段两列） |
| `m6_all__table_main.tex` | 同上，LaTeX 形态 |
| `m6_all__metrics_agent.csv` | **发布表**：⑫ 的全量 agent 指标表（18 项） |
| `m6_all__metrics_agent.md` | 同上，Markdown 形态 |
| `m6_all__metrics_stage.csv` | **发布表**：⑫ 的全量阶段指标表（六条跨阶段 + 39 条逐阶段） |
| `m6_all__metrics_stage.md` | 同上，Markdown 形态 |
| `m6_all__table_a.csv` | **内部诊断表，不是发布件**（⑥-b）：带 `effect` 等归一列。⑪ 裁定 effect **不进任何发布表** —— 归档它是留证据，不是给人引用。仓库里每份 `table_a.csv` 旁边有一份 `table_a.NOTE.md` 写着同一句话 |
| `m6_all__table_a.tex` | **内部诊断表，不是发布件**（⑥-b）：带 `effect` 等归一列。⑪ 裁定 effect **不进任何发布表** —— 归档它是留证据，不是给人引用。仓库里每份 `table_a.csv` 旁边有一份 `table_a.NOTE.md` 写着同一句话 |
| `m6_all__table_b.csv` | **内部诊断表，不是发布件**（⑥-b）：带 `effect` 等归一列。⑪ 裁定 effect **不进任何发布表** —— 归档它是留证据，不是给人引用。仓库里每份 `table_b.csv` 旁边有一份 `table_b.NOTE.md` 写着同一句话 |

## 口径与证据

| 文件 | 是什么 |
| --- | --- |
| `report_spec_v1.md` | 十九列逐列的定义 / 数据源 / 闸门条件 / 不可得时显示什么 |
| `known_limits_v1.md` | 已知限制表（两条通道的都在里面） |
| `rehearsal_v2.md` | ⑭ 从零演练：只凭发布包 + 手册在一台干净机器上走通七步的逐步记录 |
| `push_instructions.md` | ㉑ 的投放说明：推之前确认什么、推完做什么、四条不要做 |
| `genequant__MANIFEST.json` | ㉑ 协议子树的封闭清单（逐件 sha256）；`RELEASE_MANIFEST.json` 的 `genequant.manifest_sha256` 指的就是它 |
| `VERSIONS.md` | 四条版本轴的正文（含公开通道那一行）与历次变更 |

文件全部 0400；逐文件 sha256 与两条版本轴在 `MANIFEST.json` 里。改过即对不上。
