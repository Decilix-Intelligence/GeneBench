# 实例层 O1 矩阵（私有通道，agent = `oracle`）

> **口径：40 模板 / 130 实例。** 「模板」= 出集参数表的 40 行（模板**目录**只有 39 个 —— `S1/source_status` 被 `s1-rob-01` 与 `s1-rob-02` 两行复用）；「实例」= 同一行参数沿 window / universe / factor_pool 换取值得到的变体，**不是新题**。身份的单位是参数表的一行，见 `ops/mk_instances.py`。

> 答案面落点：`$GB/reference/tasks/v1.0-instances/`。

> **判据（O1）：全零。** 但**两类行的归因是相反的**，别混着读 ——

> * **探针族**那些行非零 = **探针缺陷**：诚实的参考解在自己的题上不该触发任何一族。
> * **`(malformed)`** 那一行非零 = **oracle 自己的产物格式不对**。产物是我们写的，它连格式都对不上，用它当 gold 只会把错误传下去（`run_oracles` 模块 docstring）。

> 实例只换取值不换题型，所以两条对实例都逐字成立 —— 而**换了取值才现形**的问题，正是这一页存在的理由。

**零 finding 的实例 108/130**；**非零的 0**；**没产出 artifact、因而什么都没判的 22**。（可判 108/130）

> `·` = 判过且零；`n/a` = 该基点**一个实例都没产出 artifact**；数字 = 该基点所有实例的 finding 合计。**不可得与零不能长得一样。**

## 表一 探针族 × 基点（实例聚合）

| 探针族 | s1-cor-01 | s1-eco-01 | s1-ops-01 | s1-rob-01 | s1-rob-02 | s2-cor-01 | s2-eco-01 | s2-ops-01 | s2-rob-01 | s2-rob-02 | s3-cor-01 | s3-eco-01 | s3-ops-01 | s3-rob-01 | s3-rob-02 | s4-cor-01 | s4-eco-01 | s4-ops-01 | s4-rob-01 | s4-rob-02 | s5-cor-01 | s5-eco-01 | s5-ops-01 | s5-rob-01 | s5-rob-02 | s6-cor-01 | s6-eco-01 | s6-ops-01 | s6-rob-01 | s6-rob-02 | s7-cor-01 | s7-eco-01 | s7-ops-01 | s7-rob-01 | s7-rob-02 | s8-cor-01 | s8-eco-01 | s8-ops-01 | s8-rob-01 | s8-rob-02 | 行合计 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `adjust_fingerprint` | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | · | · | · | · | · | · | · | · | · | · | n/a | 0 |
| `attribution_conservation` | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | · | · | · | · | · | · | · | · | · | · | n/a | 0 |
| `calendar` | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | · | · | · | · | · | · | · | · | · | · | n/a | 0 |
| `declared_reads` | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | · | · | · | · | · | · | · | · | · | · | n/a | 0 |
| `factor_degeneracy` | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | · | · | · | · | · | · | · | · | · | · | n/a | 0 |
| `fetch_clock` | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | · | · | · | · | · | · | · | · | · | · | n/a | 0 |
| `input_ablation` | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | · | · | · | · | · | · | · | · | · | · | n/a | 0 |
| `ledger_conservation` | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | · | · | · | · | · | · | · | · | · | · | n/a | 0 |
| `lookahead` | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | · | · | · | · | · | · | · | · | · | · | n/a | 0 |
| `nonfinite_propagation` | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | · | · | · | · | · | · | · | · | · | · | n/a | 0 |
| `optimizer_failure` | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | · | · | · | · | · | · | · | · | · | · | n/a | 0 |
| `pit_universe` | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | · | · | · | · | · | · | · | · | · | · | n/a | 0 |
| `source_status` | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | · | · | · | · | · | · | · | · | · | · | n/a | 0 |
| `underdetermined` | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | · | · | · | · | · | · | · | · | · | · | n/a | 0 |
| `unsupported_operator` | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | · | · | · | · | · | · | · | · | · | · | n/a | 0 |
| `warmup_boundary` | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | · | · | · | · | · | · | · | · | · | · | n/a | 0 |
| `(malformed)` | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | n/a | · | · | · | · | · | · | · | · | · | · | · | · | · | · | n/a | 0 |
| **列合计** | 0 | 0 | 0 | 0 | n/a | 0 | 0 | 0 | 0 | n/a | 0 | 0 | 0 | 0 | n/a | 0 | 0 | 0 | 0 | n/a | 0 | 0 | 0 | 0 | n/a | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | n/a | 0 |

| 基点 | 实例数 | 可判 | 零 finding | 非零 |
| --- | --- | --- | --- | --- |
| `s1-cor-01` | 4 | 4 | 4 | 0 |
| `s1-eco-01` | 4 | 4 | 4 | 0 |
| `s1-ops-01` | 3 | 3 | 3 | 0 |
| `s1-rob-01` | 3 | 3 | 3 | 0 |
| `s1-rob-02` | 3 | 0 | 0 | 0 |
| `s2-cor-01` | 4 | 4 | 4 | 0 |
| `s2-eco-01` | 4 | 4 | 4 | 0 |
| `s2-ops-01` | 3 | 3 | 3 | 0 |
| `s2-rob-01` | 3 | 3 | 3 | 0 |
| `s2-rob-02` | 3 | 0 | 0 | 0 |
| `s3-cor-01` | 4 | 4 | 4 | 0 |
| `s3-eco-01` | 4 | 4 | 4 | 0 |
| `s3-ops-01` | 3 | 3 | 3 | 0 |
| `s3-rob-01` | 3 | 3 | 3 | 0 |
| `s3-rob-02` | 3 | 0 | 0 | 0 |
| `s4-cor-01` | 4 | 4 | 4 | 0 |
| `s4-eco-01` | 4 | 4 | 4 | 0 |
| `s4-ops-01` | 3 | 3 | 3 | 0 |
| `s4-rob-01` | 3 | 3 | 3 | 0 |
| `s4-rob-02` | 3 | 0 | 0 | 0 |
| `s5-cor-01` | 4 | 4 | 4 | 0 |
| `s5-eco-01` | 4 | 4 | 4 | 0 |
| `s5-ops-01` | 3 | 3 | 3 | 0 |
| `s5-rob-01` | 3 | 3 | 3 | 0 |
| `s5-rob-02` | 3 | 0 | 0 | 0 |
| `s6-cor-01` | 3 | 3 | 3 | 0 |
| `s6-eco-01` | 3 | 3 | 3 | 0 |
| `s6-ops-01` | 3 | 3 | 3 | 0 |
| `s6-rob-01` | 3 | 3 | 3 | 0 |
| `s6-rob-02` | 3 | 3 | 3 | 0 |
| `s7-cor-01` | 3 | 3 | 3 | 0 |
| `s7-eco-01` | 3 | 3 | 3 | 0 |
| `s7-ops-01` | 3 | 3 | 3 | 0 |
| `s7-rob-01` | 3 | 3 | 3 | 0 |
| `s7-rob-02` | 3 | 3 | 3 | 0 |
| `s8-cor-01` | 3 | 2 | 2 | 0 |
| `s8-eco-01` | 3 | 2 | 2 | 0 |
| `s8-ops-01` | 3 | 2 | 2 | 0 |
| `s8-rob-01` | 3 | 2 | 2 | 0 |
| `s8-rob-02` | 3 | 0 | 0 | 0 |

## 表二 逐实例明细

| 实例 id | task_id | 基点 | 参数 | 可判 | finding | 视图行 | 日志行 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `S1/cov_fields@s1-cor-01#44136fa355` | `s1-cor-01` | `s1-cor-01` | （基准） | 是 | · | 6900 | 601 |
| `S1/cov_fields@s1-cor-01#0b0d39a2c6` | `s1-cor-02` | `s1-cor-01` | universe=csi500 | 是 | · | 11500 | 1001 |
| `S1/cov_fields@s1-cor-01#9a9d633fc3` | `s1-cor-03` | `s1-cor-01` | window={"end":"2026-07-31","start":"2026-07-20"} | 是 | · | 3000 | 601 |
| `S1/cov_fields@s1-cor-01#cf724e2f35` | `s1-cor-04` | `s1-cor-01` | universe=csi500；window={"end":"2026-07-31","start":"2026-07-20"} | 是 | · | 5000 | 1001 |
| `S1/lean_fetch@s1-eco-01#44136fa355` | `s1-eco-01` | `s1-eco-01` | （基准） | 是 | · | 11500 | 501 |
| `S1/lean_fetch@s1-eco-01#1a7afd3c8d` | `s1-eco-02` | `s1-eco-01` | universe=csi300；window={"end":"2026-07-17","start":"2026-07-06"} | 是 | · | 3000 | 301 |
| `S1/lean_fetch@s1-eco-01#522bb9f4fc` | `s1-eco-03` | `s1-eco-01` | universe=csi300；window={"end":"2026-07-31","start":"2026-07-20"} | 是 | · | 3000 | 301 |
| `S1/lean_fetch@s1-eco-01#9a9d633fc3` | `s1-eco-04` | `s1-eco-01` | window={"end":"2026-07-31","start":"2026-07-20"} | 是 | · | 5000 | 501 |
| `S1/prov_ledger@s1-ops-01#44136fa355` | `s1-ops-01` | `s1-ops-01` | （基准） | 是 | · | 1500 | 301 |
| `S1/prov_ledger@s1-ops-01#5dc3931adf` | `s1-ops-02` | `s1-ops-01` | window={"end":"2026-07-17","start":"2026-07-06"} | 是 | · | 3000 | 301 |
| `S1/prov_ledger@s1-ops-01#cf724e2f35` | `s1-ops-03` | `s1-ops-01` | universe=csi500；window={"end":"2026-07-31","start":"2026-07-20"} | 是 | · | 5000 | 501 |
| `S1/source_status@s1-rob-01#44136fa355` | `s1-rob-01` | `s1-rob-01` | （基准） | 是 | · | 3000 | 303 |
| `S1/source_status@s1-rob-02#44136fa355` | `s1-rob-02` | `s1-rob-02` | （基准） | 否 | n/a | — | — |
| `S1/source_status@s1-rob-01#5dc3931adf` | `s1-rob-03` | `s1-rob-01` | window={"end":"2026-07-17","start":"2026-07-06"} | 是 | · | 3000 | 303 |
| `S1/source_status@s1-rob-02#8651587ec8` | `s1-rob-04` | `s1-rob-02` | window={"end":"2026-06-30","start":"2026-06-01"} | 否 | n/a | — | — |
| `S1/source_status@s1-rob-01#e606de531e` | `s1-rob-05` | `s1-rob-01` | universe=csi500；window={"end":"2026-07-17","start":"2026-07-06"} | 是 | · | 5000 | 503 |
| `S1/source_status@s1-rob-02#e606de531e` | `s1-rob-06` | `s1-rob-02` | universe=csi500；window={"end":"2026-07-17","start":"2026-07-06"} | 否 | n/a | — | — |
| `S2/cor_01@s2-cor-01#44136fa355` | `s2-cor-01` | `s2-cor-01` | （基准） | 是 | · | 41700 | 602 |
| `S2/cor_01@s2-cor-01#0b0d39a2c6` | `s2-cor-02` | `s2-cor-01` | universe=csi500 | 是 | · | 69500 | 1002 |
| `S2/cor_01@s2-cor-01#2c12388ef5` | `s2-cor-03` | `s2-cor-01` | universe=csi500；window={"end":"2026-06-30","start":"2026-04-01"} | 是 | · | 30000 | 1002 |
| `S2/cor_01@s2-cor-01#d8f9b9b820` | `s2-cor-04` | `s2-cor-01` | window={"end":"2026-06-30","start":"2026-04-01"} | 是 | · | 18000 | 602 |
| `S2/eco_01@s2-eco-01#44136fa355` | `s2-eco-01` | `s2-eco-01` | （基准） | 是 | · | 551400 | 8 |
| `S2/eco_01@s2-eco-01#2c12388ef5` | `s2-eco-02` | `s2-eco-01` | universe=csi500；window={"end":"2026-06-30","start":"2026-04-01"} | 是 | · | 30000 | 4 |
| `S2/eco_01@s2-eco-01#b5537c3109` | `s2-eco-03` | `s2-eco-01` | window={"end":"2026-07-31","start":"2025-07-01"} | 是 | · | 79500 | 4 |
| `S2/eco_01@s2-eco-01#d8f9b9b820` | `s2-eco-04` | `s2-eco-01` | window={"end":"2026-06-30","start":"2026-04-01"} | 是 | · | 18000 | 4 |
| `S2/ops_01@s2-ops-01#44136fa355` | `s2-ops-01` | `s2-ops-01` | （基准） | 是 | · | 6900 | 602 |
| `S2/ops_01@s2-ops-01#2c12388ef5` | `s2-ops-02` | `s2-ops-01` | universe=csi500；window={"end":"2026-06-30","start":"2026-04-01"} | 是 | · | 30000 | 1002 |
| `S2/ops_01@s2-ops-01#b5537c3109` | `s2-ops-03` | `s2-ops-01` | window={"end":"2026-07-31","start":"2025-07-01"} | 是 | · | 79500 | 602 |
| `S2/rob_01@s2-rob-01#44136fa355` | `s2-rob-01` | `s2-rob-01` | （基准） | 是 | · | 69500 | 502 |
| `S2/rob_02_probe@s2-rob-02#44136fa355` | `s2-rob-02` | `s2-rob-02` | （基准） | 否 | n/a | — | — |
| `S2/rob_01@s2-rob-01#959192a52b` | `s2-rob-03` | `s2-rob-01` | universe=csi300；window={"end":"2026-07-31","start":"2025-07-01"} | 是 | · | 79500 | 302 |
| `S2/rob_01@s2-rob-01#b5537c3109` | `s2-rob-04` | `s2-rob-01` | window={"end":"2026-07-31","start":"2025-07-01"} | 是 | · | 132500 | 502 |
| `S2/rob_02_probe@s2-rob-02#53d394212c` | `s2-rob-05` | `s2-rob-02` | window={"end":"2026-07-31","start":"2026-07-01"} | 否 | n/a | — | — |
| `S2/rob_02_probe@s2-rob-02#b1cfba288c` | `s2-rob-06` | `s2-rob-02` | universe=csi500；window={"end":"2026-07-31","start":"2025-07-01"} | 否 | n/a | — | — |
| `S3/cor01_wq006_corr@s3-cor-01#44136fa355` | `s3-cor-01` | `s3-cor-01` | （基准） | 是 | · | 41700 | 302 |
| `S3/cor01_wq006_corr@s3-cor-01#0b0d39a2c6` | `s3-cor-02` | `s3-cor-01` | universe=csi500 | 是 | · | 69500 | 502 |
| `S3/cor01_wq006_corr@s3-cor-01#764bd5aea8` | `s3-cor-03` | `s3-cor-01` | universe=csi500；window={"end":"2026-03-31","start":"2026-01-05"} | 是 | · | 28000 | 502 |
| `S3/cor01_wq006_corr@s3-cor-01#f436d8670e` | `s3-cor-04` | `s3-cor-01` | window={"end":"2026-03-31","start":"2026-01-05"} | 是 | · | 16800 | 302 |
| `S3/eco01_free_pv@s3-eco-01#44136fa355` | `s3-eco-01` | `s3-eco-01` | （基准） | 是 | · | 41700 | 302 |
| `S3/eco01_free_pv@s3-eco-01#49625d8724` | `s3-eco-02` | `s3-eco-01` | window={"end":"2026-07-31","start":"2026-04-01"} | 是 | · | 24900 | 302 |
| `S3/eco01_free_pv@s3-eco-01#764bd5aea8` | `s3-eco-03` | `s3-eco-01` | universe=csi500；window={"end":"2026-03-31","start":"2026-01-05"} | 是 | · | 28000 | 502 |
| `S3/eco01_free_pv@s3-eco-01#f436d8670e` | `s3-eco-04` | `s3-eco-01` | window={"end":"2026-03-31","start":"2026-01-05"} | 是 | · | 16800 | 302 |
| `S3/ops01_gtja012_vwap_audit@s3-ops-01#44136fa355` | `s3-ops-01` | `s3-ops-01` | （基准） | 是 | · | 41700 | 302 |
| `S3/ops01_gtja012_vwap_audit@s3-ops-01#49625d8724` | `s3-ops-02` | `s3-ops-01` | window={"end":"2026-07-31","start":"2026-04-01"} | 是 | · | 24900 | 302 |
| `S3/ops01_gtja012_vwap_audit@s3-ops-01#764bd5aea8` | `s3-ops-03` | `s3-ops-01` | universe=csi500；window={"end":"2026-03-31","start":"2026-01-05"} | 是 | · | 28000 | 502 |
| `S3/rob01_wq054_nonfinite@s3-rob-01#44136fa355` | `s3-rob-01` | `s3-rob-01` | （基准） | 是 | · | 41700 | 302 |
| `S3/rob02_gtja046_probe@s3-rob-02#44136fa355` | `s3-rob-02` | `s3-rob-02` | （基准） | 否 | n/a | — | — |
| `S3/rob01_wq054_nonfinite@s3-rob-01#49625d8724` | `s3-rob-03` | `s3-rob-01` | window={"end":"2026-07-31","start":"2026-04-01"} | 是 | · | 24900 | 302 |
| `S3/rob01_wq054_nonfinite@s3-rob-01#fcb48409e9` | `s3-rob-04` | `s3-rob-01` | universe=csi500；window={"end":"2026-07-31","start":"2026-04-01"} | 是 | · | 41500 | 502 |
| `S3/rob02_gtja046_probe@s3-rob-02#bc9824ce3e` | `s3-rob-05` | `s3-rob-02` | window={"end":"2026-06-30","start":"2025-07-01"} | 否 | n/a | — | — |
| `S3/rob02_gtja046_probe@s3-rob-02#fcb48409e9` | `s3-rob-06` | `s3-rob-02` | universe=csi500；window={"end":"2026-07-31","start":"2026-04-01"} | 否 | n/a | — | — |
| `S4/cor_ic_recompute@s4-cor-01#44136fa355` | `s4-cor-01` | `s4-cor-01` | （基准） | 是 | · | 34800 | 583 |
| `S4/cor_ic_recompute@s4-cor-01#0b0d39a2c6` | `s4-cor-02` | `s4-cor-01` | universe=csi500 | 是 | · | 58000 | 815 |
| `S4/cor_ic_recompute@s4-cor-01#a10c40daae` | `s4-cor-03` | `s4-cor-01` | factor_pool=gtja_191.017 | 是 | · | 34800 | 583 |
| `S4/cor_ic_recompute@s4-cor-01#f436d8670e` | `s4-cor-04` | `s4-cor-01` | window={"end":"2026-03-31","start":"2026-01-05"} | 是 | · | 16800 | 227 |
| `S4/eco_free_select@s4-eco-01#44136fa355` | `s4-eco-01` | `s4-eco-01` | （基准） | 是 | · | 34800 | 583 |
| `S4/eco_free_select@s4-eco-01#764bd5aea8` | `s4-eco-02` | `s4-eco-01` | universe=csi500；window={"end":"2026-03-31","start":"2026-01-05"} | 是 | · | 28000 | 395 |
| `S4/eco_free_select@s4-eco-01#d8f9b9b820` | `s4-eco-03` | `s4-eco-01` | window={"end":"2026-06-30","start":"2026-04-01"} | 是 | · | 18000 | 303 |
| `S4/eco_free_select@s4-eco-01#f436d8670e` | `s4-eco-04` | `s4-eco-01` | window={"end":"2026-03-31","start":"2026-01-05"} | 是 | · | 16800 | 227 |
| `S4/ops_audit_trail@s4-ops-01#44136fa355` | `s4-ops-01` | `s4-ops-01` | （基准） | 是 | · | 34800 | 583 |
| `S4/ops_audit_trail@s4-ops-01#1084b1fe5c` | `s4-ops-02` | `s4-ops-01` | factor_pool=gtja_191.017；universe=csi500 | 是 | · | 58000 | 815 |
| `S4/ops_audit_trail@s4-ops-01#f436d8670e` | `s4-ops-03` | `s4-ops-01` | window={"end":"2026-03-31","start":"2026-01-05"} | 是 | · | 16800 | 227 |
| `S4/rob_sparse_panel@s4-rob-01#44136fa355` | `s4-rob-01` | `s4-rob-01` | （基准） | 是 | · | 34800 | 583 |
| `S4/rob_probe_setting@s4-rob-02#44136fa355` | `s4-rob-02` | `s4-rob-02` | （基准） | 否 | n/a | — | — |
| `S4/rob_probe_setting@s4-rob-02#764bd5aea8` | `s4-rob-03` | `s4-rob-02` | universe=csi500；window={"end":"2026-03-31","start":"2026-01-05"} | 否 | n/a | — | — |
| `S4/rob_probe_setting@s4-rob-02#8aabd7c9df` | `s4-rob-04` | `s4-rob-02` | factor_pool=gtja_191.017；window={"end":"2026-03-31","start":"2026-01-05"} | 否 | n/a | — | — |
| `S4/rob_sparse_panel@s4-rob-01#0b0d39a2c6` | `s4-rob-05` | `s4-rob-01` | universe=csi500 | 是 | · | 58000 | 815 |
| `S4/rob_sparse_panel@s4-rob-01#f436d8670e` | `s4-rob-06` | `s4-rob-01` | window={"end":"2026-03-31","start":"2026-01-05"} | 是 | · | 16800 | 227 |
| `S5/rank_signal@s5-cor-01#44136fa355` | `s5-cor-01` | `s5-cor-01` | （基准） | 是 | · | 6900 | 72 |
| `S5/rank_signal@s5-cor-01#0b0d39a2c6` | `s5-cor-02` | `s5-cor-01` | universe=csi500 | 是 | · | 11500 | 118 |
| `S5/rank_signal@s5-cor-01#7212df62b9` | `s5-cor-03` | `s5-cor-01` | universe=csi500；window={"end":"2026-06-30","start":"2026-06-01"} | 是 | · | 10500 | 108 |
| `S5/rank_signal@s5-cor-01#8651587ec8` | `s5-cor-04` | `s5-cor-01` | window={"end":"2026-06-30","start":"2026-06-01"} | 是 | · | 6300 | 66 |
| `S5/free_signal@s5-eco-01#44136fa355` | `s5-eco-01` | `s5-eco-01` | （基准） | 是 | · | 41700 | 420 |
| `S5/free_signal@s5-eco-01#19f220c346` | `s5-eco-02` | `s5-eco-01` | window={"end":"2026-07-31","start":"2026-05-06"} | 是 | · | 18600 | 189 |
| `S5/free_signal@s5-eco-01#7212df62b9` | `s5-eco-03` | `s5-eco-01` | universe=csi500；window={"end":"2026-06-30","start":"2026-06-01"} | 是 | · | 10500 | 108 |
| `S5/free_signal@s5-eco-01#8651587ec8` | `s5-eco-04` | `s5-eco-01` | window={"end":"2026-06-30","start":"2026-06-01"} | 是 | · | 6300 | 66 |
| `S5/format_audit@s5-ops-01#44136fa355` | `s5-ops-01` | `s5-ops-01` | （基准） | 是 | · | 6900 | 72 |
| `S5/format_audit@s5-ops-01#19f220c346` | `s5-ops-02` | `s5-ops-01` | window={"end":"2026-07-31","start":"2026-05-06"} | 是 | · | 18600 | 189 |
| `S5/format_audit@s5-ops-01#7212df62b9` | `s5-ops-03` | `s5-ops-01` | universe=csi500；window={"end":"2026-06-30","start":"2026-06-01"} | 是 | · | 10500 | 108 |
| `S5/null_vs_flat@s5-rob-01#44136fa355` | `s5-rob-01` | `s5-rob-01` | （基准） | 是 | · | 6900 | 72 |
| `S5/freq_unstated@s5-rob-02#44136fa355` | `s5-rob-02` | `s5-rob-02` | （基准） | 否 | n/a | — | — |
| `S5/freq_unstated@s5-rob-02#b196347a80` | `s5-rob-03` | `s5-rob-02` | universe=csi500；window={"end":"2026-07-31","start":"2026-05-06"} | 否 | n/a | — | — |
| `S5/freq_unstated@s5-rob-02#c22c297f5c` | `s5-rob-04` | `s5-rob-02` | window={"end":"2026-07-31","start":"2026-01-05"} | 否 | n/a | — | — |
| `S5/null_vs_flat@s5-rob-01#19f220c346` | `s5-rob-05` | `s5-rob-01` | window={"end":"2026-07-31","start":"2026-05-06"} | 是 | · | 18600 | 189 |
| `S5/null_vs_flat@s5-rob-01#b196347a80` | `s5-rob-06` | `s5-rob-01` | universe=csi500；window={"end":"2026-07-31","start":"2026-05-06"} | 是 | · | 31000 | 313 |
| `S6/cor_ledger@s6-cor-01#44136fa355` | `s6-cor-01` | `s6-cor-01` | （基准） | 是 | · | 6900 | 100 |
| `S6/cor_ledger@s6-cor-01#19f220c346` | `s6-cor-02` | `s6-cor-01` | window={"end":"2026-07-31","start":"2026-05-06"} | 是 | · | 18600 | 202 |
| `S6/cor_ledger@s6-cor-01#287a399f81` | `s6-cor-03` | `s6-cor-01` | window={"end":"2026-07-31","start":"2026-06-01"} | 是 | · | 13200 | 157 |
| `S6/eco_swap_cap@s6-eco-01#44136fa355` | `s6-eco-01` | `s6-eco-01` | （基准） | 是 | · | 18600 | 35 |
| `S6/eco_swap_cap@s6-eco-01#287a399f81` | `s6-eco-02` | `s6-eco-01` | window={"end":"2026-07-31","start":"2026-06-01"} | 是 | · | 13200 | 27 |
| `S6/eco_swap_cap@s6-eco-01#d8f9b9b820` | `s6-eco-03` | `s6-eco-01` | window={"end":"2026-06-30","start":"2026-04-01"} | 是 | · | 18000 | 37 |
| `S6/ops_ledger_audit@s6-ops-01#44136fa355` | `s6-ops-01` | `s6-ops-01` | （基准） | 是 | · | 18600 | 57 |
| `S6/ops_ledger_audit@s6-ops-01#287a399f81` | `s6-ops-02` | `s6-ops-01` | window={"end":"2026-07-31","start":"2026-06-01"} | 是 | · | 13200 | 40 |
| `S6/ops_ledger_audit@s6-ops-01#d8f9b9b820` | `s6-ops-03` | `s6-ops-01` | window={"end":"2026-06-30","start":"2026-04-01"} | 是 | · | 18000 | 57 |
| `S6/rob_optimizer_failure@s6-rob-01#44136fa355` | `s6-rob-01` | `s6-rob-01` | （基准） | 是 | · | 6900 | 91 |
| `S6/rob_underdetermined@s6-rob-02#44136fa355` | `s6-rob-02` | `s6-rob-02` | （基准） | 是 | · | 13200 | 1 |
| `S6/rob_optimizer_failure@s6-rob-01#19f220c346` | `s6-rob-03` | `s6-rob-01` | window={"end":"2026-07-31","start":"2026-05-06"} | 是 | · | 18600 | 192 |
| `S6/rob_optimizer_failure@s6-rob-01#287a399f81` | `s6-rob-04` | `s6-rob-01` | window={"end":"2026-07-31","start":"2026-06-01"} | 是 | · | 13200 | 143 |
| `S6/rob_underdetermined@s6-rob-02#19f220c346` | `s6-rob-05` | `s6-rob-02` | window={"end":"2026-07-31","start":"2026-05-06"} | 是 | · | 18600 | 1 |
| `S6/rob_underdetermined@s6-rob-02#d8f9b9b820` | `s6-rob-06` | `s6-rob-02` | window={"end":"2026-06-30","start":"2026-04-01"} | 是 | · | 18000 | 1 |
| `S7/cor_reproduce@s7-cor-01#44136fa355` | `s7-cor-01` | `s7-cor-01` | （基准） | 是 | · | 545400 | 1837 |
| `S7/cor_reproduce@s7-cor-01#64150974fc` | `s7-cor-02` | `s7-cor-01` | window={"end":"2026-07-03","start":"2024-01-02"} | 是 | · | 181200 | 615 |
| `S7/cor_reproduce@s7-cor-01#9010b12bf6` | `s7-cor-03` | `s7-cor-01` | window={"end":"2026-07-03","start":"2022-01-04"} | 是 | · | 326400 | 1101 |
| `S7/eco_attribution@s7-eco-01#44136fa355` | `s7-eco-01` | `s7-eco-01` | （基准） | 是 | · | 545400 | 1837 |
| `S7/eco_attribution@s7-eco-01#64150974fc` | `s7-eco-02` | `s7-eco-01` | window={"end":"2026-07-03","start":"2024-01-02"} | 是 | · | 181200 | 615 |
| `S7/eco_attribution@s7-eco-01#7aa54c75eb` | `s7-eco-03` | `s7-eco-01` | window={"end":"2023-12-29","start":"2019-01-02"} | 是 | · | 364200 | 1230 |
| `S7/ops_audit@s7-ops-01#44136fa355` | `s7-ops-01` | `s7-ops-01` | （基准） | 是 | · | 545400 | 1838 |
| `S7/ops_audit@s7-ops-01#7aa54c75eb` | `s7-ops-02` | `s7-ops-01` | window={"end":"2023-12-29","start":"2019-01-02"} | 是 | · | 364200 | 1231 |
| `S7/ops_audit@s7-ops-01#9010b12bf6` | `s7-ops-03` | `s7-ops-01` | window={"end":"2026-07-03","start":"2022-01-04"} | 是 | · | 326400 | 1102 |
| `S7/rob_tradability@s7-rob-01#44136fa355` | `s7-rob-01` | `s7-rob-01` | （基准） | 是 | · | 545400 | 1837 |
| `S7/rob_underdetermined@s7-rob-02#44136fa355` | `s7-rob-02` | `s7-rob-02` | （基准） | 是 | · | 545400 | 1 |
| `S7/rob_tradability@s7-rob-01#64150974fc` | `s7-rob-03` | `s7-rob-01` | window={"end":"2026-07-03","start":"2024-01-02"} | 是 | · | 181200 | 615 |
| `S7/rob_tradability@s7-rob-01#9010b12bf6` | `s7-rob-04` | `s7-rob-01` | window={"end":"2026-07-03","start":"2022-01-04"} | 是 | · | 326400 | 1101 |
| `S7/rob_underdetermined@s7-rob-02#64150974fc` | `s7-rob-05` | `s7-rob-02` | window={"end":"2026-07-03","start":"2024-01-02"} | 是 | · | 181200 | 1 |
| `S7/rob_underdetermined@s7-rob-02#7aa54c75eb` | `s7-rob-06` | `s7-rob-02` | window={"end":"2023-12-29","start":"2019-01-02"} | 是 | · | 364200 | 1 |
| `S8/s8_lifecycle@s8-cor-01#44136fa355` | `s8-cor-01` | `s8-cor-01` | （基准） | 否 | n/a | — | — |
| `S8/s8_lifecycle@s8-cor-01#c4d54059aa` | `s8-cor-02` | `s8-cor-01` | window={"end":"2026-07-15","start":"2026-06-15"} | 是 | · | — | 39 |
| `S8/s8_lifecycle@s8-cor-01#f882f75187` | `s8-cor-03` | `s8-cor-01` | window={"end":"2026-07-15","start":"2026-07-01"} | 是 | · | — | 28 |
| `S8/s8_min_slippage@s8-eco-01#44136fa355` | `s8-eco-01` | `s8-eco-01` | （基准） | 否 | n/a | — | — |
| `S8/s8_min_slippage@s8-eco-01#8651587ec8` | `s8-eco-02` | `s8-eco-01` | window={"end":"2026-06-30","start":"2026-06-01"} | 是 | · | — | 12 |
| `S8/s8_min_slippage@s8-eco-01#c4d54059aa` | `s8-eco-03` | `s8-eco-01` | window={"end":"2026-07-15","start":"2026-06-15"} | 是 | · | — | 12 |
| `S8/s8_audit_overreach@s8-ops-01#44136fa355` | `s8-ops-01` | `s8-ops-01` | （基准） | 否 | n/a | — | — |
| `S8/s8_audit_overreach@s8-ops-01#8651587ec8` | `s8-ops-02` | `s8-ops-01` | window={"end":"2026-06-30","start":"2026-06-01"} | 是 | · | — | 29 |
| `S8/s8_audit_overreach@s8-ops-01#c4d54059aa` | `s8-ops-03` | `s8-ops-01` | window={"end":"2026-07-15","start":"2026-06-15"} | 是 | · | — | 30 |
| `S8/s8_idempotent@s8-rob-01#44136fa355` | `s8-rob-01` | `s8-rob-01` | （基准） | 否 | n/a | — | — |
| `S8/s8_probe_calendar@s8-rob-02#44136fa355` | `s8-rob-02` | `s8-rob-02` | （基准） | 否 | n/a | — | — |
| `S8/s8_idempotent@s8-rob-01#8651587ec8` | `s8-rob-03` | `s8-rob-01` | window={"end":"2026-06-30","start":"2026-06-01"} | 是 | · | — | 19 |
| `S8/s8_idempotent@s8-rob-01#c4d54059aa` | `s8-rob-04` | `s8-rob-01` | window={"end":"2026-07-15","start":"2026-06-15"} | 是 | · | — | 19 |
| `S8/s8_probe_calendar@s8-rob-02#8651587ec8` | `s8-rob-05` | `s8-rob-02` | window={"end":"2026-06-30","start":"2026-06-01"} | 否 | n/a | — | — |
| `S8/s8_probe_calendar@s8-rob-02#f882f75187` | `s8-rob-06` | `s8-rob-02` | window={"end":"2026-07-15","start":"2026-07-01"} | 否 | n/a | — | — |

## 非零的实例（逐条原因）

（无）—— 在这批可判的实例上 O1 全绿。

## 没产出 artifact 的实例（什么都没判）

| 归类 | 个数 |
| --- | --- |
| 挂起的探针题实例（设计如此） | 18 |
| 与出集撞号（sim 会话工厂） | 4 |

**挂起的探针题实例（设计如此）**

* `S1/source_status@s1-rob-02#44136fa355`（task_id `s1-rob-02`，基点 `s1-rob-02`，rc=None）：落盘被拦：PackError: E9c/E9d2 探针题 s1-rob-02 不落盘：字段 data_version 在条件 （无条件） 下既无 screen 实测记录、也无 FIELD_MATERIAL_WHEN 静态规则 —— 先跑 ops/run_materiality_screen.py 或补静态前提
* `S1/source_status@s1-rob-02#8651587ec8`（task_id `s1-rob-04`，基点 `s1-rob-02`，rc=None）：落盘被拦：PackError: E9c/E9d2 探针题 s1-rob-04 不落盘：字段 data_version 在条件 （无条件） 下既无 screen 实测记录、也无 FIELD_MATERIAL_WHEN 静态规则 —— 先跑 ops/run_materiality_screen.py 或补静态前提
* `S1/source_status@s1-rob-02#e606de531e`（task_id `s1-rob-06`，基点 `s1-rob-02`，rc=None）：落盘被拦：PackError: E9c/E9d2 探针题 s1-rob-06 不落盘：字段 data_version 在条件 （无条件） 下既无 screen 实测记录、也无 FIELD_MATERIAL_WHEN 静态规则 —— 先跑 ops/run_materiality_screen.py 或补静态前提
* `S2/rob_02_probe@s2-rob-02#44136fa355`（task_id `s2-rob-02`，基点 `s2-rob-02`，rc=None）：落盘被拦：PackError: E9c/E9d2 探针题 s2-rob-02 不落盘：字段 adjust 在条件 (('missing_row_policy', 'keep_missing'),) 下既无 screen 实测记录、也无 FIELD_MATERIAL_WHEN 静态规则 —— 先跑 ops/run_materiality_screen.py 或补静态前提
* `S2/rob_02_probe@s2-rob-02#53d394212c`（task_id `s2-rob-05`，基点 `s2-rob-02`，rc=None）：落盘被拦：PackError: E9c/E9d2 探针题 s2-rob-05 不落盘：字段 adjust 在条件 (('missing_row_policy', 'keep_missing'),) 下既无 screen 实测记录、也无 FIELD_MATERIAL_WHEN 静态规则 —— 先跑 ops/run_materiality_screen.py 或补静态前提
* `S2/rob_02_probe@s2-rob-02#b1cfba288c`（task_id `s2-rob-06`，基点 `s2-rob-02`，rc=None）：落盘被拦：PackError: E9c/E9d2 探针题 s2-rob-06 不落盘：字段 adjust 在条件 (('missing_row_policy', 'keep_missing'),) 下既无 screen 实测记录、也无 FIELD_MATERIAL_WHEN 静态规则 —— 先跑 ops/run_materiality_screen.py 或补静态前提
* `S3/rob02_gtja046_probe@s3-rob-02#44136fa355`（task_id `s3-rob-02`，基点 `s3-rob-02`，rc=None）：落盘被拦：PackError: E9c/E9d2 探针题 s3-rob-02 不落盘：字段 eval_frequency 在条件 (('lookback', '24'),) 下既无 screen 实测记录、也无 FIELD_MATERIAL_WHEN 静态规则 —— 先跑 ops/run_materiality_screen.py 或补静态前提
* `S3/rob02_gtja046_probe@s3-rob-02#bc9824ce3e`（task_id `s3-rob-05`，基点 `s3-rob-02`，rc=None）：落盘被拦：PackError: E9c/E9d2 探针题 s3-rob-05 不落盘：字段 eval_frequency 在条件 (('lookback', '24'),) 下既无 screen 实测记录、也无 FIELD_MATERIAL_WHEN 静态规则 —— 先跑 ops/run_materiality_screen.py 或补静态前提
* `S3/rob02_gtja046_probe@s3-rob-02#fcb48409e9`（task_id `s3-rob-06`，基点 `s3-rob-02`，rc=None）：落盘被拦：PackError: E9c/E9d2 探针题 s3-rob-06 不落盘：字段 eval_frequency 在条件 (('lookback', '24'),) 下既无 screen 实测记录、也无 FIELD_MATERIAL_WHEN 静态规则 —— 先跑 ops/run_materiality_screen.py 或补静态前提
* `S4/rob_probe_setting@s4-rob-02#44136fa355`（task_id `s4-rob-02`，基点 `s4-rob-02`，rc=None）：落盘被拦：PackError: E9c/E9d2 探针题 s4-rob-02 不落盘：字段 holding_periods 在条件 (('ic_method', 'spearman'),) 下既无 screen 实测记录、也无 FIELD_MATERIAL_WHEN 静态规则 —— 先跑 ops/run_materiality_screen.py 或补静态前提
* `S4/rob_probe_setting@s4-rob-02#764bd5aea8`（task_id `s4-rob-03`，基点 `s4-rob-02`，rc=None）：落盘被拦：PackError: E9c/E9d2 探针题 s4-rob-03 不落盘：字段 holding_periods 在条件 (('ic_method', 'spearman'),) 下既无 screen 实测记录、也无 FIELD_MATERIAL_WHEN 静态规则 —— 先跑 ops/run_materiality_screen.py 或补静态前提
* `S4/rob_probe_setting@s4-rob-02#8aabd7c9df`（task_id `s4-rob-04`，基点 `s4-rob-02`，rc=None）：落盘被拦：PackError: E9c/E9d2 探针题 s4-rob-04 不落盘：字段 holding_periods 在条件 (('ic_method', 'spearman'),) 下既无 screen 实测记录、也无 FIELD_MATERIAL_WHEN 静态规则 —— 先跑 ops/run_materiality_screen.py 或补静态前提
* `S5/freq_unstated@s5-rob-02#44136fa355`（task_id `s5-rob-02`，基点 `s5-rob-02`，rc=None）：落盘被拦：PackError: E9c/E9d2 探针题 s5-rob-02 不落盘：字段 signal_frequency 在条件 (('value_semantics', 'score'),) 下既无 screen 实测记录、也无 FIELD_MATERIAL_WHEN 静态规则 —— 先跑 ops/run_materiality_screen.py 或补静态前提
* `S5/freq_unstated@s5-rob-02#b196347a80`（task_id `s5-rob-03`，基点 `s5-rob-02`，rc=None）：落盘被拦：PackError: E9c/E9d2 探针题 s5-rob-03 不落盘：字段 signal_frequency 在条件 (('value_semantics', 'score'),) 下既无 screen 实测记录、也无 FIELD_MATERIAL_WHEN 静态规则 —— 先跑 ops/run_materiality_screen.py 或补静态前提
* `S5/freq_unstated@s5-rob-02#c22c297f5c`（task_id `s5-rob-04`，基点 `s5-rob-02`，rc=None）：落盘被拦：PackError: E9c/E9d2 探针题 s5-rob-04 不落盘：字段 signal_frequency 在条件 (('value_semantics', 'score'),) 下既无 screen 实测记录、也无 FIELD_MATERIAL_WHEN 静态规则 —— 先跑 ops/run_materiality_screen.py 或补静态前提
* `S8/s8_probe_calendar@s8-rob-02#44136fa355`（task_id `s8-rob-02`，基点 `s8-rob-02`，rc=None）：落盘被拦：PackError: E9c/E9d2 探针题 s8-rob-02 不落盘：字段 slippage_reference_price 在条件 (('matching_frequency', 'daily'),) 下既无 screen 实测记录、也无 FIELD_MATERIAL_WHEN 静态规则 —— 先跑 ops/run_materiality_screen.py 或补静态前提
* `S8/s8_probe_calendar@s8-rob-02#8651587ec8`（task_id `s8-rob-05`，基点 `s8-rob-02`，rc=None）：落盘被拦：PackError: E9c/E9d2 探针题 s8-rob-05 不落盘：字段 slippage_reference_price 在条件 (('matching_frequency', 'daily'),) 下既无 screen 实测记录、也无 FIELD_MATERIAL_WHEN 静态规则 —— 先跑 ops/run_materiality_screen.py 或补静态前提
* `S8/s8_probe_calendar@s8-rob-02#f882f75187`（task_id `s8-rob-06`，基点 `s8-rob-02`，rc=None）：落盘被拦：PackError: E9c/E9d2 探针题 s8-rob-06 不落盘：字段 slippage_reference_price 在条件 (('matching_frequency', 'daily'),) 下既无 screen 实测记录、也无 FIELD_MATERIAL_WHEN 静态规则 —— 先跑 ops/run_materiality_screen.py 或补静态前提

**与出集撞号（sim 会话工厂）**

* `S8/s8_lifecycle@s8-cor-01#44136fa355`（task_id `s8-cor-01`，基点 `s8-cor-01`，rc=1）：RuntimeError: /sim/log 返回 500：{}
* `S8/s8_min_slippage@s8-eco-01#44136fa355`（task_id `s8-eco-01`，基点 `s8-eco-01`，rc=1）：RuntimeError: /sim/log 返回 500：{}
* `S8/s8_audit_overreach@s8-ops-01#44136fa355`（task_id `s8-ops-01`，基点 `s8-ops-01`，rc=1）：RuntimeError: /sim/log 返回 500：{}
* `S8/s8_idempotent@s8-rob-01#44136fa355`（task_id `s8-rob-01`，基点 `s8-rob-01`，rc=1）：RuntimeError: /sim/log 返回 500：{}

## 覆盖率（对着全名册，不对着本批）

**跑过的 130/130 个实例**；**本轮一次都没跑的 0 个**。

---

> **三控与破坏样本不按实例重跑**（Y1b 裁定）：`ops/run_controls.py` 与 `ops/run_probe_mutations.py` 验的是**判据面** —— 「探针会不会误伤诚实产物」与「破坏一处该族会不会响」。那两件事的被测对象是**校验器**，不是题面；换窗口 / 换宇宙 / 换因子池不会换掉校验器的任何一条分支。实例层要证的是「同一道题换了取值，参考解仍然零 finding」——这正是本页的表一与表二。重跑三控只会得到逐字相同的结论，代价是 130 × 三控的网关时间。

## 基准实例 vs 出集同题（一致性对照）

> 基准实例 = 参数一个都没换的那个实例，与出集的同号题**是同一道题**（同一行参数、同一份题面），只是在实例集里**另跑了一遍**。两边结论必须一致；**两边都判过、结论却不同**只有两种可能 —— 要么题面其实不同（实例生成器漂了），要么 O1 本身不稳定。**两种都得知道。**

**一致 36**；**两边都判过但结论不同 0（这一栏非零就是告警）**；**实例层没判成、对不上的 4（基础设施，原因见上一节）**；**出集那边没有记录、对不了的 0**。

* 没判成 `s8-cor-01`：与出集撞号（sim 会话工厂）（出集那边是绿的）
* 没判成 `s8-eco-01`：与出集撞号（sim 会话工厂）（出集那边是绿的）
* 没判成 `s8-ops-01`：与出集撞号（sim 会话工厂）（出集那边是绿的）
* 没判成 `s8-rob-01`：与出集撞号（sim 会话工厂）（出集那边是绿的）

> **本矩阵渲自累积文件**：130 行、22 次跑批（2026-09-10T16:25, 2026-09-10T16:36, 2026-09-10T16:43, 2026-09-10T16:45, 2026-09-10T17:11, 2026-09-10T18:31, 2026-09-10T18:47, 2026-09-10T19:11, 2026-09-10T19:19, 2026-09-10T19:37, 2026-09-10T19:58, 2026-09-10T20:17, 2026-09-10T20:33, 2026-09-10T20:49, 2026-09-10T21:06, 2026-09-10T21:28, 2026-09-10T21:54, 2026-09-10T22:15, 2026-09-10T22:35, 2026-09-10T22:45, 2026-09-11T05:20, 2026-09-11T06:38）。逐行 `at` 标着这一行是哪一次跑出来的，**只有更新的行会覆盖更旧的**。
