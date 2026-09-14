# `table_b.csv` 是**诊断件，不是发布件**

> ⑥-b（2026-09-11 用户裁定）。这一页与表同目录，改表的生成器会把它重写一遍。

| | |
| --- | --- |
| 这是什么 | Table B：按 `(config_id, arm, stage)` 的阶段级诊断表（逐阶段的正确性量原值） |
| 能不能引用 | **不能**。它带 `effect` 这一类归一/聚合列，而裁定 ⑪ 明写 effect 不进发布表 |
| 那该引用哪张 | 同目录的 `table_main.csv`（⑩ 的固定十九列）与 `metrics_agent.*` / `metrics_stage.*`（⑫ 的两张全量指标表） |
| 为什么还留着 | 留证据。逐格核对「结果库出的表 == 既有的表」靠的就是它（`ops/mk_tables.py::verify_batch`），删了就核不了 |
| 逐列口径 | 主表在 `ops/reports/report_spec_v1.md`；全部指标在 `ops/specs/GeneBench指标规格_v1.md` §9 |

诊断件不进发布件清单：判据在 `ops/mk_release_manifest.py::DIAGNOSTIC_NOT_RELEASE`
与 `ops/archive_signoff.py::RELEASE_TABLES`，测试在 `ops/test_report_columns.py`。
