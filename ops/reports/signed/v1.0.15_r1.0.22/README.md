# 签字包 v1.0.15_r1.0.22（v1.0 收尾卡 v2（到可分发））

* 任务集 `1.0.15`（根 `622f720c95cf2249…`）
* 参考面 `r1.0.22`（根 `c61b066734e3192f…`）
* git HEAD `536c496cc6bb`

## 哪张表能引用

| 文件 | 是什么 |
| --- | --- |
| `m6_all__table_main.csv` / `.tex` | **发布表**：⑩ 的固定十九列（`SR / P@1 / $` + 每阶段两列） |
| `m6_public__table_main.csv` / `.tex` | 同上，公开通道那一批 |
| `m6_all__metrics_agent.csv` / `.md` | **发布表**：⑫ 的全量 agent 指标表（18 项） |
| `m6_all__metrics_stage.csv` / `.md` | **发布表**：⑫ 的全量阶段指标表（六条跨阶段 + 39 条逐阶段） |
| `m6_public__metrics_agent.csv`、`m6_public__metrics_stage.csv` | 同上，公开通道那一批 |
| `m6_all__table_a.csv` / `.tex`、`table_b.csv` | **内部诊断表**：带 `effect` 等归一列。⑪ 裁定 effect **不进任何发布表** —— 归档它是留证据，不是给人引用 |

## 口径与证据

| 文件 | 是什么 |
| --- | --- |
| `report_spec_v1.md` | 十九列逐列的定义 / 数据源 / 闸门条件 / 不可得时显示什么 |
| `rehearsal_v2.md` | ⑭ 从零演练：只凭发布包 + 手册在一台干净机器上走通七步的逐步记录 |
| `push_instructions.md` | ㉑ 的投放说明：推之前确认什么、推完做什么、四条不要做 |
| `genequant__MANIFEST.json` | ㉑ 协议子树的封闭清单（逐件 sha256）；`RELEASE_MANIFEST.json` 的 `genequant.manifest_sha256` 指的就是它 |

文件全部 0400；逐文件 sha256 与两条版本轴在 `MANIFEST.json` 里。改过即对不上。
