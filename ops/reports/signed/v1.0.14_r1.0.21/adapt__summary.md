# 适配赛道 v1.0-adapt 结算摘要

例：30；有 oracle：30；有真运行：30；结算到的 run：30；问题：0

> **完成定义是「30 例各有 oracle 与一次真运行」，不是「都要通过」。** 结局分布如实报。

> 脚注（N-348，2026-09-10 用户裁定）：适配赛道 v1.0-adapt 的题源是**出集规定题的 oracle 产物**（探针题不入），这些产物随适配 bundle 进入执行面。**跑过适配赛道的被测方，主赛道这些题算「可能已见过答案」**；口径与逐题清单见 ops/specs/fairness_protocol.md §7 与 ops/reports/known_limits_v1.md。

## 结局分布（如实报）

- correct_flag: 5
- failed: 11
- first_pass: 14

- cfg-codex-deepseek / adapt / L1: n=10 resolved=0.7 as_expected=0.7
- cfg-codex-deepseek / adapt / L2: n=10 resolved=0.7 as_expected=0.7
- cfg-codex-deepseek / adapt / L3: n=10 resolved=0.5 as_expected=0.5
- cfg-codex-deepseek / adapt / ALL: n=30 resolved=0.6333333333333333 as_expected=0.6333333333333333
