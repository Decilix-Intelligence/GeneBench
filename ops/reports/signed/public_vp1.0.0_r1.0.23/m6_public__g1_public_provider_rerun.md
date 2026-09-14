# G1：公开通道 18 个 run 在**真公开 provider** 上重跑（N-611）

> 生成器 `$GB/scratch/G1/mk_report.py`，数字全部取自盘上产物：
> 每个 run 的 `inject.json`（`provider` 段，本卡新增）、f02 上 `work/provider/features/` 的实际目录、
> `ops/reports/m6_public/records.json`。**报告里没有一个手写的数。**

## 1. 这一批为什么要重跑

上一批 `m6_public` 的 8 个 run **跑在私有 provider 上**，而它们是公开通道的读数。
根因三条（见 `ops/tickets_inbox/G1.md`，提交 `a233a96`）：

1. `ops/run_f02_a1.py` 真跑那条路径读模块常量 `PROVIDER`（写死私有 provider 绝对路径），
   `main()` 的 `global RUN_ROOT, RESULTS` 漏了它 —— `--provider-root` 只有 `--dry` 用得上；
2. `ops/run_joblist.f02_run_cmd` 拼的那条 ssh 命令**一个字都没提通道** —— f02 上
   provider 默认与 P2 期望值两头都回落到 private，**两头一致所以全绿**；
3. P2 查的是**调用方传进来的路径**，拦不住「传进来的和装进去的是同一个错的东西」。
   新增 P7e（`runner.inject.check_work_provider`）站在 `work/` 这一侧查**结果**。

受污染的那 8 个 run 已移到 f02 的
`/data/genebench_runner/m6_public/polluted_private_provider_20260912/`
与 f01 的 `$GB/runs_in/m6_public_polluted_20260912/`（**不删**，它们是 N-611 的证据），
结果库里对应的 8 行标了 `superseded`。

## 2. 18 个 run 全部跑在公开 provider 上 —— 逐条证据

判别法（与 N-611 的实测证据同一套）：**私有** provider 的 `features/` 下有 336 个 `bj*`
（北交所）代码，**公开** provider 只有沪深 —— 3575 个，`bj*` 为 0。

- 通道：['public']
- `work/provider` 现算根：['561348660a3175b1…']（1 个取值）
- `features/` 下 `bj*` 计数：[0]；`features/` 总数：[3575]
- 题集轴 `set_version`：['p1.0.0']（公开轴，F1 的 `p1.0.0`）

| run_id | 通道 | 期望根 | work/provider 现算根 | provider 源 | 文件数 | features 下 `bj*` | features 总数 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `s1-cor-01.open.cfg-codex-deepseek.r01@finance01-e3887dfa` | public | `561348660a3175b1` | `561348660a3175b1…` | `/data/genebench_runner/provider/qlib_provider_56134866` | 28610 | 0 | 3575 |
| `s1-cor-01.strict.cfg-codex-deepseek.r01@finance01-e3887dfa` | public | `561348660a3175b1` | `561348660a3175b1…` | `/data/genebench_runner/provider/qlib_provider_56134866` | 28610 | 0 | 3575 |
| `s2-cor-01.open.cfg-codex-deepseek.r01@finance01-e3887dfa` | public | `561348660a3175b1` | `561348660a3175b1…` | `/data/genebench_runner/provider/qlib_provider_56134866` | 28610 | 0 | 3575 |
| `s2-cor-01.strict.cfg-codex-deepseek.r01@finance01-e3887dfa` | public | `561348660a3175b1` | `561348660a3175b1…` | `/data/genebench_runner/provider/qlib_provider_56134866` | 28610 | 0 | 3575 |
| `s3-cor-01.open.cfg-codex-deepseek.r01@finance01-e3887dfa` | public | `561348660a3175b1` | `561348660a3175b1…` | `/data/genebench_runner/provider/qlib_provider_56134866` | 28610 | 0 | 3575 |
| `s3-cor-01.strict.cfg-codex-deepseek.r01@finance01-e3887dfa` | public | `561348660a3175b1` | `561348660a3175b1…` | `/data/genebench_runner/provider/qlib_provider_56134866` | 28610 | 0 | 3575 |
| `s4-cor-01.open.cfg-codex-deepseek.r01@finance01-e3887dfa` | public | `561348660a3175b1` | `561348660a3175b1…` | `/data/genebench_runner/provider/qlib_provider_56134866` | 28610 | 0 | 3575 |
| `s4-cor-01.strict.cfg-codex-deepseek.r01@finance01-e3887dfa` | public | `561348660a3175b1` | `561348660a3175b1…` | `/data/genebench_runner/provider/qlib_provider_56134866` | 28610 | 0 | 3575 |
| `s5-cor-01.open.cfg-codex-deepseek.r01@finance01-e3887dfa` | public | `561348660a3175b1` | `561348660a3175b1…` | `/data/genebench_runner/provider/qlib_provider_56134866` | 28610 | 0 | 3575 |
| `s5-cor-01.strict.cfg-codex-deepseek.r01@finance01-e3887dfa` | public | `561348660a3175b1` | `561348660a3175b1…` | `/data/genebench_runner/provider/qlib_provider_56134866` | 28610 | 0 | 3575 |
| `s6-cor-01.open.cfg-codex-deepseek.r01@finance01-e3887dfa` | public | `561348660a3175b1` | `561348660a3175b1…` | `/data/genebench_runner/provider/qlib_provider_56134866` | 28610 | 0 | 3575 |
| `s6-cor-01.strict.cfg-codex-deepseek.r01@finance01-e3887dfa` | public | `561348660a3175b1` | `561348660a3175b1…` | `/data/genebench_runner/provider/qlib_provider_56134866` | 28610 | 0 | 3575 |
| `s7-cor-01.open.cfg-codex-deepseek.r01@finance01-e3887dfa` | public | `561348660a3175b1` | `561348660a3175b1…` | `/data/genebench_runner/provider/qlib_provider_56134866` | 28610 | 0 | 3575 |
| `s7-cor-01.strict.cfg-codex-deepseek.r01@finance01-e3887dfa` | public | `561348660a3175b1` | `561348660a3175b1…` | `/data/genebench_runner/provider/qlib_provider_56134866` | 28610 | 0 | 3575 |
| `s7-rob-02.open.cfg-codex-deepseek.r01@finance01-e3887dfa` | public | `561348660a3175b1` | `561348660a3175b1…` | `/data/genebench_runner/provider/qlib_provider_56134866` | 28610 | 0 | 3575 |
| `s7-rob-02.strict.cfg-codex-deepseek.r01@finance01-e3887dfa` | public | `561348660a3175b1` | `561348660a3175b1…` | `/data/genebench_runner/provider/qlib_provider_56134866` | 28610 | 0 | 3575 |
| `s8-cor-01.open.cfg-codex-deepseek.r01@finance01-e3887dfa` | public | `561348660a3175b1` | `561348660a3175b1…` | `/data/genebench_runner/provider/qlib_provider_56134866` | 28610 | 0 | 3575 |
| `s8-cor-01.strict.cfg-codex-deepseek.r01@finance01-e3887dfa` | public | `561348660a3175b1` | `561348660a3175b1…` | `/data/genebench_runner/provider/qlib_provider_56134866` | 28610 | 0 | 3575 |

## 3. 18 个 run 的读数

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

**合计**：steps（= 允许的模型调用）**968**，prompt tokens 34,670,647，
completion tokens 775,515，费用 **$16.2788**。

读法（不要把它当实验数据）：这是**构造验收**批次 —— 一个 config、一个种子、
每阶段一题双臂 + `s7-rob-02`。`sr_bucket` / `validity` 的分布只说明链路走得通、判据在响，
**不说明任何 agent 的能力**。

## 4. 与上一批（私有 provider）的差别，哪些是 provider 换了造成的

不知道 —— 而且**本批不打算回答这个问题**。两批之间同时变了三样：provider（私有→公开）、
任务集轴（`1.0.15` → 公开轴 `p1.0.0`，F1 重冻）、预算档（N-388 把默认档 600k 抬到 6M、
S4 9M、S7 18M）。三样一起变，单变量归因不成立。**上一批的读数已作废（superseded），
不做对比**；本批是公开通道第一批可用的读数。

## 5. 已知限制（本卡量到、按裁定不修）

- `s1-cor-01` 的 **oracle 三控基线在本次复跑里变脏**：`fetch_clock` 族报 601 条
  `fetch_clock_mismatch`，而它申报的 `fetched_at`（`2026-09-07T15:41:43.048+00:00` 等）
  **确实逐条存在于** `$GB/logs/gateway_access_public.jsonl` 里（已实测：该 ts + `/universe`
  + `task_id=s1-cor-01` + `decision=allow` 一条不差）。也就是说不是日志缺了，是
  `fetch_clock` 探针的**日志切片**在同一道题被重跑过之后取错了窗口。
  连带让破坏样本里 `s1-cor-01` 的三条（`fetch_clock` / `source_status` / `lookahead`）
  判成「基线不干净 —— 破坏实验无意义」，破坏样本从 18/19 掉到 **15/19**。
  已登记 `ops/reports/known_limits_v1.md`，按「最后一卡不修」的裁定不动。
