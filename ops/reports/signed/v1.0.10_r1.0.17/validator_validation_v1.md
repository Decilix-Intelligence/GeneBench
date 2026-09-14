# 验证验证器报告 v1（2026-09-05）

> 卡 5.1 验收原文：每探针一组保真/破坏扰动单测 —— 对 oracle 产物注入已知违例必须命中、干净产物零误报。
> 本报告给三件事的机器证据；「方向未证实」的族（f1 矩阵全零，N-110）**不因本报告转绿**。

## ① 干净产物零误报（O1 矩阵）
- 数据源：`probe_run_oracle.cumulative.json`（2 次跑批的累积：2026-09-06T05:35, 2026-09-06T07:23）
- 题数：40；有产物且零 finding：32；有 finding：0；没跑 / 没产物（不算零误报）：8
- 零 finding 的题：s1-cor-01, s1-eco-01, s1-ops-01, s1-rob-01, s2-cor-01, s2-ops-01, s2-rob-01, s3-cor-01, s3-eco-01, s3-ops-01, s3-rob-01, s4-cor-01, s4-eco-01, s4-ops-01, s4-rob-01, s5-cor-01, s5-eco-01, s5-ops-01, s5-rob-01, s6-cor-01, s6-eco-01, s6-ops-01, s6-rob-01, s7-cor-01, s7-eco-01, s7-ops-01, s7-rob-01, s7-rob-02, s8-cor-01, s8-eco-01, s8-ops-01, s8-rob-01
- 没跑 / 没产物：s1-rob-02（落盘被拦：PackError: E9c/E9d2 探针题 s1-rob-02 不）, s2-eco-01, s2-rob-02（落盘被拦：PackError: E9c/E9d2 探针题 s2-rob-02 不）, s3-rob-02（落盘被拦：PackError: E9c/E9d2 探针题 s3-rob-02 不）, s4-rob-02（落盘被拦：PackError: E9c/E9d2 探针题 s4-rob-02 不）, s5-rob-02（落盘被拦：PackError: E9c/E9d2 探针题 s5-rob-02 不）, s6-rob-02（落盘被拦：PackError: E9c/E9d2 探针题 s6-rob-02 不）, s8-rob-02（落盘被拦：PackError: E9c/E9d2 探针题 s8-rob-02 不）

## ② 注入违例必命中（红队样例）
- 红队样例：38 条；命中期望 code+严重级：38；未命中：0
- 被样例命中过的探针族：12/16 —— attribution_conservation, calendar, declared_reads, factor_degeneracy, fetch_clock, ledger_conservation, nonfinite_propagation, optimizer_failure, source_status, underdetermined, unsupported_operator, warmup_boundary
- 样例里**没有**任何 violation 命中的族：adjust_fingerprint, input_ablation, lookahead, pit_universe

## ③ 三态判定
- 评分器三态 / L3 / 报告器红测：`65 passed in 0.92s`（rc=0）

## ④ 逐族破坏样本（取该题自己的 oracle 产物，只破坏一处）
- 破坏样本 19 条：**该族响、其余不响** 18 条；造不出 1 条；失败 0 条
- 被破坏样本证过方向的族（14）：adjust_fingerprint, attribution_conservation, calendar, declared_reads, factor_degeneracy, fetch_clock, ledger_conservation, lookahead, nonfinite_propagation, optimizer_failure, source_status, underdetermined, unsupported_operator, warmup_boundary
- 没有发出点、因而造不出样本的族：input_ablation, pit_universe（在 `ops/test_probe_coverage.py::NO_EMITTER_YET` 具名登记）
  - **s5-cor-01 / underdetermined**：造不出这个破坏（前提不满足）

> 明细：`ops/reports/m6/mutations.md`。

## ⑤ 三控走完整评分器
- oracle 桩 9 题：每族零 finding ✅（效果分：7 题 = 100，2 题扣住 —— 扣住理由见 controls.md）
- null 桩 9 题：SR 记 0 ✅
- filler 桩 on s7-rob-02：silent_completion 命中且 effect 为 null ✅

> 明细：`ops/reports/m6/controls.md`。

## 判定：通过
- 零误报：是（有产物且零 finding 32，有 finding 0，没跑/没产物 8；零 finding 的题数为 0 时不成立）
- 必命中：是（38/38）
- 三态：是
- 逐族破坏样本：是（18/19，覆盖 14 族）
- 三控：是

边界（不是脚注装饰，是可证伪的限制）：
- ②的样例覆盖的族只有上面列出的那些；没被任何样例命中的族，其「必命中」**没有证据**。
- 依赖网关日志的四族（declared_reads / fetch_clock / lookahead / source_status）在数据面结算时读 f01 的 access_log 三重切片；在 f02 侧不可得 → unobservable（不是 clean）。
- ①里「没产物」的题不算零误报（校验器一条都没查）。
