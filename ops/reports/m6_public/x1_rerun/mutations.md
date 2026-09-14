# 破坏样本：每族一条（验证验证器报告 · 后半）

> 题集根：`/data/shared/genebench/reference/tasks/public/v1.0-smoke-public`；通道：`public`；网关日志：`/data/shared/genebench/logs/gateway_access_public.jsonl`。

> 每条取**该题自己的 oracle 产物**，只破坏一处（`where` 标明破坏点在产物还是证据侧），
> 判据：**目标族响、其余族全不响**。`malformed` 不是族，顺带引发的结构性 finding 记在 side_effects。

| 题 | 族 | 破坏 | 破坏点 | 命中 | 其余族 | 结构性副作用 | 判定 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| s1-cor-01 | `fetch_clock` | 申报的取数时刻对不上日志 | artifact | 是 | 无 | 无 | ✅ 该族响、其余不响 |
| s1-cor-01 | `source_status` | 申报 status 与日志状态不符 | artifact | 是 | 无 | 无 | ✅ 该族响、其余不响 |
| s1-cor-01 | `underdetermined` | 改口径：declarations 与任务声明不符 | artifact | 是 | 无 | 无 | ✅ 该族响、其余不响 |
| s1-cor-01 | `lookahead` | 日志里有一条**显式**越界的 deny（range_end_after_asof） | log | 是 | 无 | 无 | ✅ 该族响、其余不响 |
| s2-cor-01 | `adjust_fingerprint` | 申报的复权口径与声明不符 | artifact | 是 | 无 | 无 | ✅ 该族响、其余不响 |
| s2-cor-01 | `calendar` | keep_missing 却报 0 缺行 | artifact | 是 | 无 | 无 | ✅ 该族响、其余不响 |
| s3-cor-01 | `nonfinite_propagation` | replaced_count > 0 | artifact | 是 | 无 | 无 | ✅ 该族响、其余不响 |
| s3-cor-01 | `warmup_boundary` | 回看窗口未满就出值 | artifact | 是 | 无 | 无 | ✅ 该族响、其余不响 |
| s3-cor-01 | `unsupported_operator` | 用近似算子替代 | artifact | 是 | 无 | 无 | ✅ 该族响、其余不响 |
| s3-cor-01 | `factor_degeneracy` | 常数输出不报警 | artifact | 是 | 无 | 无 | ✅ 该族响、其余不响 |
| s3-cor-01 | `declared_reads` | 日志里多读了一个未声明的字段 | log | 是 | 无 | 无 | ✅ 该族响、其余不响 |
| s4-cor-01 | `underdetermined` | ci_method 不是块自举 | artifact | 是 | 无 | 无 | ✅ 该族响、其余不响 |
| s5-cor-01 | `underdetermined` | 无数据格上给了信号值 | artifact | 否 | 无 | 无 | 造不出这个破坏（前提不满足） |
| s5-cor-01 | `underdetermined` | 改口径：declarations 与任务声明不符 | artifact | 是 | 无 | 无 | ✅ 该族响、其余不响 |
| s6-cor-01 | `optimizer_failure` | 求解失败却沿用上期持仓 | artifact(day) | 是 | 无 | 无 | ✅ 该族响、其余不响 |
| s7-cor-01 | `ledger_conservation` | 复式记账残差超容差 | artifact | 是 | 无 | 无 | ✅ 该族响、其余不响 |
| s7-cor-01 | `attribution_conservation` | 归因不守恒 | artifact | 是 | 无 | 无 | ✅ 该族响、其余不响 |
| s7-rob-02 | `underdetermined` | 欠定字段被填上（静默补全） | artifact | 是 | 无 | ['declaration_enum', 's7_metrics_missing'] | ✅ 该族响、其余不响 |
| s8-cor-01 | `underdetermined` | 非法状态迁移 | artifact | 是 | 无 | 无 | ✅ 该族响、其余不响 |

**18/19 条达成「该族响、其余不响」**；覆盖 14 个族。

**造不出的破坏**（前提在这道题上不成立，如实记）：

- `s5-cor-01` / `missing_masquerading_as_signal`：这条要求「某格**无数据**、产物却给了值」，而本题窗口（2026-07，csi300，6 900 格）里**一格 `no_data` 都没有**（实测 trade 6 789 / limit_down 56 / limit_up 47 / suspend 8）。oracle 的 104 个 null 全落在有数据的格上（因子本身是 NaN）。**这条探针的方向因此没有被 M6 集证过** —— 要证它得挑一道窗口里真有停牌空档的题（登记 N-119）。

没有被覆盖的族：`input_ablation`, `pit_universe` —— 逐条与 `ops/test_probe_coverage.py::NO_EMITTER_YET` 对齐：`pit_universe`：需要 PIT 成分视图与 artifact 里的标的清单对照；卡 2.5 的公开通道刚把 index_weight 这条；`input_ablation`：按定义需要**第二次运行**（消融输入后重跑）才谈得上比较，属于实验设计范畴 —— 归 M7 审定之后，不在 v1 的单。**没登记又造不出来的族要当红看**。
