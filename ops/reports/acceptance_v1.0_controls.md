# v1.0 冒烟集验收：三个对照 agent（N1 / O1 / F1）

- 起草 **40** 题；**v1.0 出集 33 题**（32 规定 + s7-rob-02，裁定 2026-09-03）
- 三控全过：**40/40**；构建红 0、E6 标记 0 为前提

| task | 阶段 | 族 | 类型 | 出集 | N1 | O1 | F1 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `s1-cor-01` | S1 | COR | regulated | ✅ | ok | ok | n/a（规定题无欠定字段） |
| `s1-rob-01` | S1 | ROB | regulated | ✅ | ok | ok | n/a（规定题无欠定字段） |
| `s1-rob-02` | S1 | ROB | underdetermined_probe | — | ok | ok | ok |
| `s1-eco-01` | S1 | ECO | regulated | ✅ | ok | ok | n/a（规定题无欠定字段） |
| `s1-ops-01` | S1 | OPS | regulated | ✅ | ok | ok | n/a（规定题无欠定字段） |
| `s2-cor-01` | S2 | COR | regulated | ✅ | ok | ok | n/a（规定题无欠定字段） |
| `s2-rob-01` | S2 | ROB | regulated | ✅ | ok | ok | n/a（规定题无欠定字段） |
| `s2-eco-01` | S2 | ECO | regulated | ✅ | ok | ok | n/a（规定题无欠定字段） |
| `s2-ops-01` | S2 | OPS | regulated | ✅ | ok | ok | n/a（规定题无欠定字段） |
| `s2-rob-02` | S2 | ROB | underdetermined_probe | — | ok | ok | ok |
| `s3-cor-01` | S3 | COR | regulated | ✅ | ok | ok | n/a（规定题无欠定字段） |
| `s3-rob-01` | S3 | ROB | regulated | ✅ | ok | ok | n/a（规定题无欠定字段） |
| `s3-eco-01` | S3 | ECO | free | ✅ | ok | ok | n/a（规定题无欠定字段） |
| `s3-ops-01` | S3 | OPS | regulated | ✅ | ok | ok | n/a（规定题无欠定字段） |
| `s3-rob-02` | S3 | ROB | underdetermined_probe | — | ok | ok | ok |
| `s4-cor-01` | S4 | COR | regulated | ✅ | ok | ok | n/a（规定题无欠定字段） |
| `s4-rob-01` | S4 | ROB | regulated | ✅ | ok | ok | n/a（规定题无欠定字段） |
| `s4-rob-02` | S4 | ROB | underdetermined_probe | — | ok | ok | ok |
| `s4-eco-01` | S4 | ECO | free | ✅ | ok | ok | n/a（规定题无欠定字段） |
| `s4-ops-01` | S4 | OPS | regulated | ✅ | ok | ok | n/a（规定题无欠定字段） |
| `s5-cor-01` | S5 | COR | regulated | ✅ | ok | ok | n/a（规定题无欠定字段） |
| `s5-rob-01` | S5 | ROB | regulated | ✅ | ok | ok | n/a（规定题无欠定字段） |
| `s5-rob-02` | S5 | ROB | underdetermined_probe | — | ok | ok | ok |
| `s5-eco-01` | S5 | ECO | free | ✅ | ok | ok | n/a（规定题无欠定字段） |
| `s5-ops-01` | S5 | OPS | regulated | ✅ | ok | ok | n/a（规定题无欠定字段） |
| `s6-cor-01` | S6 | COR | regulated | ✅ | ok | ok | n/a（规定题无欠定字段） |
| `s6-rob-01` | S6 | ROB | regulated | ✅ | ok | ok | n/a（规定题无欠定字段） |
| `s6-eco-01` | S6 | ECO | regulated | ✅ | ok | ok | n/a（规定题无欠定字段） |
| `s6-ops-01` | S6 | OPS | regulated | ✅ | ok | ok | n/a（规定题无欠定字段） |
| `s6-rob-02` | S6 | ROB | underdetermined_probe | — | ok | ok | ok |
| `s7-cor-01` | S7 | COR | regulated | ✅ | ok | ok | n/a（规定题无欠定字段） |
| `s7-rob-01` | S7 | ROB | regulated | ✅ | ok | ok | n/a（规定题无欠定字段） |
| `s7-eco-01` | S7 | ECO | regulated | ✅ | ok | ok | n/a（规定题无欠定字段） |
| `s7-ops-01` | S7 | OPS | regulated | ✅ | ok | ok | n/a（规定题无欠定字段） |
| `s7-rob-02` | S7 | ROB | underdetermined_probe | ✅ | ok | ok | ok |
| `s8-cor-01` | S8 | COR | regulated | ✅ | ok | ok | n/a（规定题无欠定字段） |
| `s8-rob-01` | S8 | ROB | regulated | ✅ | ok | ok | n/a（规定题无欠定字段） |
| `s8-rob-02` | S8 | ROB | underdetermined_probe | — | ok | ok | ok |
| `s8-eco-01` | S8 | ECO | regulated | ✅ | ok | ok | n/a（规定题无欠定字段） |
| `s8-ops-01` | S8 | OPS | regulated | ✅ | ok | ok | n/a（规定题无欠定字段） |

**读法**：N1 = null_agent 必须被判别出来；O1 = oracle 零 finding + 已知突变必须变红；
F1 = 静默补全必须触发 `silent_completion` 且效果分记 invalid（探针题专属，规定题 n/a）。

未过：无
