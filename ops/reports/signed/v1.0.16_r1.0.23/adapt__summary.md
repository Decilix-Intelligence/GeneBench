# 适配赛道 v1.0-adapt 结算摘要

例：30；有 oracle：30；有真运行：30；结算到的 run：30；问题：0

> **完成定义是「30 例各有 oracle 与一次真运行」，不是「都要通过」。** 结局分布如实报。

> 脚注（N-348，2026-09-10 用户裁定）：适配赛道 v1.0-adapt 的题源是**出集规定题的 oracle 产物**（探针题不入），这些产物随适配 bundle 进入执行面。**跑过适配赛道的被测方，主赛道这些题算「可能已见过答案」**；口径与逐题清单见 ops/specs/fairness_protocol.md §7 与 ops/reports/known_limits_v1.md。

> **本版为准（X2，2026-09-11）**：v1.0.14 / r1.0.21 签字包内的这张表**整体偏低约 13 个百分点**（ALL resolved 0.6333 → 0.7667；failed 11 → 7；L1 first_pass 7 → 8、L2 7 → 9、L3 correct_flag 5 → 6）。**不是被测方表现变了，是 oracle 侧判错**：S6 参考解的 `provenance[0].artifact_id` 曾是占位串 `TODO:signal-artifact-id-missing`，被测方按协议写了合法的 `unresolved`，判据罚的是照规则做的那一方。r1.0.22 修根因后，这四例的**既有**产物与新 oracle 在 `provenance` 上逐字节相同 —— 重算，未重跑，真 API 0 次。记因见 `ops/freeze_v10.py::REFERENCE_REVISIONS` 的 r1.0.22 条；逐例见 `ops/tickets_inbox/X2.md`。

## 结局分布（如实报）

- correct_flag: 6
- failed: 7
- first_pass: 17

- cfg-codex-deepseek / adapt / L1: n=10 resolved=0.8 as_expected=0.8
- cfg-codex-deepseek / adapt / L2: n=10 resolved=0.9 as_expected=0.9
- cfg-codex-deepseek / adapt / L3: n=10 resolved=0.6 as_expected=0.6
- cfg-codex-deepseek / adapt / ALL: n=30 resolved=0.7666666666666667 as_expected=0.7666666666666667
