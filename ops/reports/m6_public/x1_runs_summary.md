# X1：公开通道 m6_public 逐 run 实况（18 个 job，2026-09-12 重出）

> **这一份是重出的。** 旧版（2026-09-11）里的 8 行读数跑在**私有 provider** 上、
> 另外 10 行是「被夹具身份闸挡住」的占位 —— 两样都已不成立：夹具身份闸由 F1 的公开轴
> （`p1.0.0`）解掉，provider 静默串通道由 G1 的 `a233a96` 修掉。
> 逐条的 provider 身份证据见 `g1_public_provider_rerun.md` §2。

| run_id | stage | arm | run_status | validity | sr_bucket | steps | tok_prompt | tok_completion | USD | l3 | gate_failed | findings |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `s1-cor-01.open.cfg-codex-deepseek.r01@finance01-e3887dfa` | S1 | open | ok | valid | scorable | 25 | 630824 | 19450 | 0.3032 | cov:True | — | 0 |
| `s1-cor-01.strict.cfg-codex-deepseek.r01@finance01-e3887dfa` | S1 | strict | ok | valid | scorable | 27 | 968275 | 36312 | 0.4740 | cov:True | — | 0 |
| `s2-cor-01.open.cfg-codex-deepseek.r01@finance01-e3887dfa` | S2 | open | violation | invalid | scorable | 42 | 1738067 | 49351 | 0.8299 | align:False | lookahead | 1 |
| `s2-cor-01.strict.cfg-codex-deepseek.r01@finance01-e3887dfa` | S2 | strict | violation | invalid | scorable | 41 | 2220277 | 71458 | 1.0712 | align:False | lookahead | 1 |
| `s3-cor-01.open.cfg-codex-deepseek.r01@finance01-e3887dfa` | S3 | open | identity_mismatch | — | unscorable_agent | 30 | 933332 | 28517 | 0.4483 | — | — | 0 |
| `s3-cor-01.strict.cfg-codex-deepseek.r01@finance01-e3887dfa` | S3 | strict | malformed | invalid | malformed | 28 | 910970 | 23452 | 0.4318 | — | lookahead | 2 |
| `s4-cor-01.open.cfg-codex-deepseek.r01@finance01-e3887dfa` | S4 | open | ok | valid | scorable | 29 | 986096 | 32726 | 0.4771 | epsilon:False | — | 0 |
| `s4-cor-01.strict.cfg-codex-deepseek.r01@finance01-e3887dfa` | S4 | strict | identity_mismatch | — | unscorable_agent | 32 | 1279418 | 31078 | 0.6040 | — | — | 0 |
| `s5-cor-01.open.cfg-codex-deepseek.r01@finance01-e3887dfa` | S5 | open | ok | valid | scorable | 29 | 617156 | 12629 | 0.2882 | tau:True | — | 0 |
| `s5-cor-01.strict.cfg-codex-deepseek.r01@finance01-e3887dfa` | S5 | strict | ok | valid | scorable | 27 | 911583 | 22686 | 0.4310 | tau:True | — | 0 |
| `s6-cor-01.open.cfg-codex-deepseek.r01@finance01-e3887dfa` | S6 | open | ok | valid | scorable | 36 | 1554707 | 37864 | 0.7341 | cons:True | — | 0 |
| `s6-cor-01.strict.cfg-codex-deepseek.r01@finance01-e3887dfa` | S6 | strict | ok | valid | scorable | 42 | 1584772 | 30849 | 0.7380 | cons:True | — | 0 |
| `s7-cor-01.open.cfg-codex-deepseek.r01@finance01-e3887dfa` | S7 | open | violation | invalid | scorable | 165 | 6436160 | 112733 | 2.9807 | epsilon:False | attribution_conservation | 1 |
| `s7-cor-01.strict.cfg-codex-deepseek.r01@finance01-e3887dfa` | S7 | strict | timeout | — | unscorable_agent | 52 | 2903559 | 59027 | 1.3555 | — | — | 0 |
| `s7-rob-02.open.cfg-codex-deepseek.r01@finance01-e3887dfa` | S7 | open | violation | invalid | scorable | 83 | 5458596 | 101622 | 2.5359 | none:False | underdetermined, attribution_conservation | 2 |
| `s7-rob-02.strict.cfg-codex-deepseek.r01@finance01-e3887dfa` | S7 | strict | ok | valid | scorable | 80 | 2143122 | 43104 | 0.9999 | none:True | — | 0 |
| `s8-cor-01.open.cfg-codex-deepseek.r01@finance01-e3887dfa` | S8 | open | budget_exhausted | — | unscorable_agent | 100 | 2130878 | 40454 | 0.9910 | — | — | 0 |
| `s8-cor-01.strict.cfg-codex-deepseek.r01@finance01-e3887dfa` | S8 | strict | budget_exhausted | — | unscorable_agent | 100 | 1262855 | 22203 | 0.5850 | — | — | 0 |

**18 个 run 合计**：steps **968**，prompt tokens 34,670,647，
completion tokens 775,515，费用 **$16.2788**。全部跑在公开 provider
（根 `561348660a3175b1…`，`features/` 下 `bj*` 为 0）上。

读法（不要把它当实验数据）：构造验收批次，一个 config、一个种子、每阶段一题双臂 +
`s7-rob-02`。`sr_bucket` / `validity` 的分布只说明链路走得通与判据在响。
