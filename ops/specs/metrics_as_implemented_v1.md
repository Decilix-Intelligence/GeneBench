# 指标：规格 vs 实现（v1 逐项对齐）

> **这份文件回答一个问题**：《GeneBench 指标规格 v1》里写的每一个指标，
> 今天在代码里**到底判不判**、判在哪一层、算在哪个文件的哪个函数。
>
> `ops/specs/GeneBench指标规格_v1.md` 是**设计稿**，`ops/specs/GeneBench指标对接决定_v1.md`
> 是它的增补与修订（两文冲突处**以对接决定为准**，规格 v1 第 19–21 行自己这么写的）。
> 两份都不描述实现。这份描述实现。
>
> **判定层**：`L1` 硬校验（结构 / 探针，零裁判方差）· `L2` 白名单软校验（v1 **一处都没启用**）·
> `L3` 性能结算（与 gold 比，带容差）。
>
> **「在判吗」三态**：
> **判** = 出数且进判据；
> **只报** = 出数进报表、**不进** `l3_pass` / `validity`；
> **不出** = v1 根本不产出这一列，理由逐条写在最后一列（不写「未实现」了事）。
>
> 每行的实现出处写成 `文件:行`。**行号会随提交漂**——
> `ops/test_metrics_as_implemented.py` 只钉住「文件存在」与「行号不越界」，
> 不钉内容（照 `ops/test_p2_contract.py:164` 与 `ops/test_p2_contract.py:173` 的写法）。

版本轴：任务集 `1.0.13` / 参考面 `r1.0.20`（现值查法见 `VERSIONS.md`）。
本文件描述的是 `scorer/` 这一侧，它**不在**任何一条冻结根内 —— 改它不推版本。

---

## 0. 先看这一张：v1 的判据其实只有三层入口

| 入口 | 做什么 | 落点 |
| --- | --- | --- |
| **闸门**（有效性闸门语义，对接决定 §1.1） | 探针失败 ⇒ 该次运行 `validity=invalid`，效果分**不产出数值**（不是低分） | `scorer/gate.py:64` |
| **L3 比对** | 按题面 `tolerance.kind` 选一条比法，与 gold 比 | `scorer/l3.py:831`（分派）|
| **聚合出表** | 按 `(config_id, arm)` / `(config_id, arm, stage)` 求均值 | `scorer/report.py:159`（Table A）、`scorer/report.py:235`（Table B）|

**闸门是 v1 与「扣分制」最大的差别**：带前视的因子 IC 会显著更高，扣掉几分之后
总分仍可能高于诚实实现 —— 那等于奖励作弊（对接决定 §1.1 原话）。所以探针失败不是扣分，
是把这次运行的效果分**取消**。逐探针族的三态（`violation` / `unobservable` / `clean`）
在 `scorer/gate.py:52`，其中 **`clean` 的定义是「检过且零命中」，不是「零命中」**——
恒绿的门与恒红的一样会被绕过。

---

## 1. Table A 十项（规格 §2）

| 指标 | 规格怎么说 | 实现在哪 | 层 | 在判吗 / 说明 |
| --- | --- | --- | --- | --- |
| **SR** | 存在可评分终端产物的任务占比 | `scorer/report.py:176`；分母口径 `runner/c42/failure_modes.py:101`，**只排除** `unscorable_harness`（`runner/c42/failure_modes.py:59`） | L1 | **判**。harness 自己坏掉的 run 不进分母 —— 否则 harness 越不稳，指标看起来越好 |
| **pass@1** | 三种子口径，任务内取均值再宏平均 | `scorer/report.py:181` | L1/L3 | **判**。**未结算的 run 既不进分子也不进分母**，单列 `unsettled_runs`（`scorer/report.py:210`）—— 「算不出」不是 0 |
| **pass^k** | 任务级无偏估计 `C(c,k)/C(n,k)`（τ-bench 口径） | `scorer/report.py:95`，聚合在 `scorer/report.py:184` | L1/L3 | **判**。同时报「有 k 次运行的任务数」`pass^3_tasks_with_3_runs` |
| **ProgressRate** | 八阶段 `1[A_k 过 V_k 结构检查]` 的均值 | `scorer/report.py:128` → `scorer/report.py:185` | L1 | **判**（结构版，非 AgentBoard 子目标加权版；取舍理由见规格 §8） |
| **Steps** | 工具调用与提交动作总数，越低越好 | `scorer/report.py:186` | 遥测 | **只报**。它不是判据，是画预算曲线的输入 |
| **$ / task** | token 计价 + 墙钟；随附预算条件化曲线 `P(b)` | `scorer/report.py:206`（逐 run 的 `cost_usd` 由 `runner/pricing.yaml` 算好后放进记录） | 遥测 | **只报，且是成本上界**：DeepSeek 分高峰 / 低谷两档而边车不记档位，表里取高峰价。**`P(b)` 预算条件化曲线 v1 不出**——它要同一配置在多档预算下各跑一遍，v1 的真跑预算不够（N-402 / N-388） |
| **Latency** | 墙钟 | `scorer/report.py:187` | 遥测 | **只报** |
| **Recov** | 恢复成功的失败事件数 / 失败事件总数 | `scorer/report.py:189`；失败事件来自 `scorer/score_run.py:217`（validator 拒绝次数） | L1 | **判，但样本可能为空**：分母是「validator 真的拒过」的 run。N-129 实测 10 个 run 调用 validator 18 次、报违例 **0** 次 → GQ 臂的修复回路一次都没启动过，这一列常常是 `None` |
| **越权操作率** | 网关拒绝或越界访问次数 / 数据访问总次数 | `scorer/report.py:192`；逐 run 来源 `scorer/score_run.py:233`（网关日志）与 `scorer/score_run.py:264`（出向代理） | L1 | **判**。网关日志不可得时是 `None` 而不是 0（`overreach_observable_runs` 单列可观测的 run 数） |
| **Checkpoint 分**（仅 Chain 赛道） | 16 个里程碑加权 | — | — | **不出**：v1 **没有 Chain 赛道**（对接决定 §5 把 B3-X 跨阶段科目整体归 Chain，推迟 v2）。没有赛道就没有里程碑，不是没实现 |
| **附录扩展**（校准误差 / 注入攻击成功率 / 无关工具调用识别 / 裁判 κ） | 规格 §2 末句 | — | — | **不出**：前三项各要一套独立的题面与攻击面；**κ 不出的理由不同** —— κ 是「软校验双裁判一致率」的发布线，而 v1 **一处软校验都没启用**（见 §4），没有 judge 字段就没有 κ 可算 |

**Table A 上另外三列不在规格里，是工程列**，但读表必须知道：

| 列 | 实现 | 为什么必须有 |
| --- | --- | --- |
| `unsettled_runs` | `scorer/report.py:210` | 「一条都判不了的题」不进 pass@1，得有地方说它去哪了 |
| `budget_exhausted_runs` | `scorer/report.py:226` | 判据是**边车真的发过 429**，不是 `run_status` —— 撞了闸但已经把 artifact 写下来的 run，`run_status` 是 `ok` 而它同样是被预算停下的（N-399） |
| `unbounded_requests` | `scorer/report.py:220` | 三态按有没有可用样本判：**真值 0**（一次都没发过无右端取数请求，正是我们想看到的）与「网关日志不可得」不能同形（N-400） |

---

## 2. Table B 各阶段（规格 §3）

每一行的入口都是 `scorer/l3.py:831` 的分派：题面 `tolerance.kind` 决定走哪条比法。
**`kind == "exact"` 只留给「产物就是一个文件的 sha256」那种题**（`scorer/l3.py:106`）——
结构化 payload 逐键相等不是判据，那是把 gold 的写法当成标准答案（N-114）。

### S1（`kind=cov`，`scorer/l3.py:135`）

| 指标 | 规格怎么说 | 实现 | 层 | 在判吗 |
| --- | --- | --- | --- | --- |
| **Cov** | 获取字段 ∩ 要求字段 / 要求字段 | `scorer/l3.py:157` | L1 | **判** |
| **PIT%** | as-of 正确的取数请求占比（网关结算） | `scorer/l3.py:177` | L1 | **判**。基准 as-of **只取任务侧**，不回退到产物自报（协议 §2.1；红队 5.1 finding C1） |
| **Prov** | 关键数值中带可解析来源引用且核查通过的占比 | `scorer/l3.py:195` | L1 | **判**（只判结构化引用；自由文本引用本应进 L2 白名单，而 L2 未启用 —— 见 §4） |

### S2（`kind=align`，`scorer/l3.py:242`）

| 指标 | 规格怎么说 | 实现 | 层 | 在判吗 |
| --- | --- | --- | --- | --- |
| **Align** | 映射到金标 schema 的字段正确率 | `scorer/l3.py:321`（三项与 `CellAgree` 同一循环写入，汇总在 `scorer/l3.py:323`） | L1 | **判** |
| **Adj** | 复权口径（申报 + 指纹法核验） | 同上 | L1 | **判** |
| **Cal** | 交易日历（申报 + 抽样实际对齐核验） | 同上 | L1 | **判** |
| **EX / VES 式效率参考** | 规格 §3 补充项（BIRD） | — | — | **不出**：v1 的 S2 产物是面板 + 字段映射，没有「处理管线」这个可执行对象，EX 无处可测 |

### S3（`kind=tau`，`scorer/l3.py:772`）

| 指标 | 规格怎么说 | 实现 | 层 | 在判吗 |
| --- | --- | --- | --- | --- |
| **Fid** | `1[ρ_Spearman(f_A, f_R) ≥ τ]`，网格 = 共同覆盖的日期 × 标的 | 逐日截面 ρ：`scorer/l3.py:744`；判据 `scorer/l3.py:800`（**逐日 P10 ≥ τ**，且可比日数不少于 gold 侧） | L3 | **判**。τ 取自标定产物 `snapshots/v1/calibration.json` 的 `tau.value` = **0.9840059556217291**；定义与取法冻结在 `ops/specs/GeneBench秩相关与标定口径_v1.md:22`（F-2：**逐日分布的 P10，不是先对时间平均再取分位**） |
| 逐日通过率 `fid_day_rate` | 规格没有这一列 | `scorer/l3.py:793` | L3 | **只报**。它是 Fid 的分解，同时是 effect 的 `raw_metric`（标签问题见 N-405） |
| **Exec** | 无错执行率 | — | — | **不出**：v1 的 S3 题不要求交付可执行代码，交付的是因子面板；「无错执行」在 harness 层表现为 `run_status`，已由 SR 覆盖，另立一列会重复计数 |
| **Repro** | 同代码同环境重执行 ρ ≥ 0.999 | — | — | **不出**：需要同一 run 重跑两次。v1 的真跑预算（100 次调用 / run）不允许每题翻倍；且**产物本来就不是逐字节可复现的**（公平性协议 §7 第 7 条：Gate 0 实测最大相对差 1.5e-14） |

### S4（`kind=epsilon`，IC 族走 `scorer/l3.py:633`）

| 指标 | 规格怎么说 | 实现 | 层 | 在判吗 |
| --- | --- | --- | --- | --- |
| **IC / RankIC** `mean` | 逐截面算再对时序汇总 | 带取自 `calibration.json` 的 `epsilon.ic_family.by_holding_period[h].by_metric`；比对在 `scorer/l3.py:714` | L3 | **判**。h=1/5/20 的 ε 分别是 **0.012837 / 0.002938 / 0.006742**，`tolerance_kind=absolute`（构造上可能趋零，`ops/ic_epsilon.py:137`） |
| `std` | 同上 | 同上 | L3 | **判**（`relative`，h=1/5/20 = 0.025591 / 0.036124 / 0.038243） |
| **ICIR** | `mean/std`，年化因子与频率冻结（√252 日频） | 同上 | L3 | **判**（`absolute`，h=1/5/20 = 1.226371 / 0.330437 / 0.572950）。年化口径冻结在 `calibration.json` 的 `scoring.annualization_factor = 252` |
| `coverage` | 对接决定 §2 采纳的新报项 | 同上 | L3 | **判**（`relative` ≈ 0.0254） |
| **`positive_ratio`** | 对接决定 §2 采纳，`positive_ratio_required: true` | 双实现差已量到，但**没出带** | L3 | **不判 —— 出数、不进比对**。标定状态是 `implausible_stop_and_report`：两份诚实实现的相对差**超过了 5% 的可信阈**，按 E-1 的纪律「停下汇报，不写成 ε」（`ops/specs/GeneBench秩相关与标定口径_v1.md:76`）。**把它标成 ε 才是错的** —— 那等于把一处没查清的口径分歧封装成容差。`compare_epsilon` 对没有带的指标记 `skipped`（`scorer/l3.py:690` 一带的 `r.skipped[path]`），不记 0 |
| **`ci_low` / `ci_high`** | 对接决定 §2：IC 一律报 block-bootstrap CI | 无带 | L3 | **不判**。标定状态 `no_pair_in_qlib_path`：qlib 口径根本不产 bootstrap 区间，**双实现对构不成**，没有「两份诚实实现的自然分歧」可量。CI 仍然出数进报表，只是不进容差比对 |
| **Newey–West t / FDR 校正** | 规格 §3 + 对接决定 §1.3（`IC_deflated`） | — | — | **不出**：`search_count` / `trial_family` 两个字段已在 artifact schema 里预留（`reference/artifact_schema.py:1610`），**但 `scorer/` 一处都没读**。没有实测的搜索次数就没有可信的紧缩分数 —— 用一个假的试验数去 deflate 比不 deflate 更糟 |

> **S4 的读法**：N-117 之前 S4 的 L3 **一格都比不了**（ε 只标定了回测指标）→ `l3_pass=None`
> → 锚点退化 → effect 永远扣住。现在五个指标里 **四个有带**、两个明确没带。
> 「未结算」与「判不过」在主表上是两件事，别读混。

### S5（`kind=sig`，`scorer/l3.py:372`）

| 指标 | 规格怎么说 | 实现 | 层 | 在判吗 |
| --- | --- | --- | --- | --- |
| **Sig** | 方向命中率 | `scorer/l3.py:402` | L3 | **只报**。判据取的是 `StateAgree`（三态一致率）与 `fid_day_rate`（`scorer/l3.py:420`）—— 方向命中率在三态一致的前提下是它的函数 |
| 三态一致率 `StateAgree` | 对接决定 §2 的 schema 级冻结：`NaN`（无观点）与 `0`（明确空仓）是**两个状态**，`fillna(0)` 判违例 | `scorer/l3.py:392` | L3 | **判**，且要求 `>= 1.0`。分母取 gold 的格数 —— **少交也是不一致** |
| 逐日秩相关 | 用已标定的 τ | `scorer/l3.py:414` | L3 | **判** |
| **Dir**（预测–实现方向一致率） | 规格 §3 | — | — | **不出**：要「实现方向」= 次日真实收益，那是 S7 结算面的数据；S5 的产物契约里没有收益序列（与 S6 的 TE 同一个成因） |
| **Decay**（信号自相关半衰期） | 规格 §3 | — | — | **不出**：v1 的 S5 题窗口最短的只有 30 余个交易日，半衰期拟合在这个长度上没有统计意义 |
| **FinTSB 四类运动模式分层** | 规格 §3 要求分层报告 | — | — | **不出**：分层要给每格标运动模式，v1 没有这份标注（对接决定 §2 「分层报告」一行已写明 v1 只做部分采纳） |

### S6（`kind=cons`，`scorer/l3.py:454`）

| 指标 | 规格怎么说 | 实现 | 层 | 在判吗 |
| --- | --- | --- | --- | --- |
| **Cons** | 硬约束零违反组合占比 | `scorer/l3.py:494` | L1/L3 | **判**（要求 `>= 1.0`） |
| **Feas** | 可行解率 | `scorer/l3.py:495` | L3 | **判**（要求 `>= 1.0`） |
| `WeightAgree` | 规格没有这一列 | `scorer/l3.py:496` | L3 | **判**（要求 `>= 0.999`）。它是「目标权重与 gold 的一致度」，补上 Cons/Feas 都过但权重完全不同的空档 |
| **TE**（跟踪误差） | `std(w'r − b'r)` 年化 | — | — | **不出，且必须写在 `note` 里**（`scorer/l3.py:504`）：v1 的 S6 产物契约只有 `targets` / `cash_ratio`，**没有收益率序列**，TE 算不出来（N-126，设计性限制）。`ops/test_scorer_l3.py` 有断言盯着「TE 出不了要写进 note，不能悄悄不提」。v1.1 的补法二选一：给 S6 payload 加逐日收益序列，或把 TE 挪到 S7（那里有逐日台账） |

### S7（`kind=epsilon`，回测带走 `by_frequency`，`scorer/l3.py:664`）

| 指标 | 规格怎么说 | 实现 | 层 | 在判吗 |
| --- | --- | --- | --- | --- |
| **Sharpe / Calmar / MDD** 等 11 项回测指标 | 复现容差带 `|m_A − m_R| ≤ ε_m` | `scorer/l3.py:714`；带取自 `calibration.json` 的 `epsilon.by_frequency[频率].by_metric` | L3 | **判，但只在 `daily` 档**。`by_frequency.daily.usable = true`；**`weekly` / `monthly` 是 `usable=false`**，`compare_epsilon` 对不可用档直接返回「没有可用的 ε 档」（`scorer/l3.py:670`）。已发布的五道 S7 题**全部声明 `daily`**，所以这不挡 v1；但换频率的题在 v1 判不了 |
| ε 的来源 | 参考实现五种子重跑极差 ×1.5 | 三份**互相独立**的回测实现 B1/B2/B3 两两取最大差 ×1.5，`ops/data_cards/s7_backtest_gold.md` §1 | — | 五种子重跑的极差是 **0**（参考回测是确定性的）—— 按 `ops/specs/GeneBench秩相关与标定口径_v1.md:76` 的 E-1，**极差为 0 要停下汇报、不许把 ε 设成 0**，所以标定源换成了跨实现差。这是「绿得可疑」判据真的起过一次作用的地方 |
| **Δ_adv**（对抗差） | 规格 §3：扰动沿 TraderBench 四级 | — | — | **不出**：要一套对抗题面（噪声 / 元级 / 对抗信号注入各一版），v1 的 34 题里没有 |
| **尾部风险 VaR/CVaR、回撤久期、cost break-even、资金梯度** | 对接决定 §2 采纳进扩展列 | — | — | **不出**：这些是 gold 侧算得出、但**没有对应题面要求 agent 交付**的量。没有 agent 侧的数就没有可比对的对象 |

### S8（`kind=fill`，`scorer/l3.py:535`）

| 指标 | 规格怎么说 | 实现 | 层 | 在判吗 |
| --- | --- | --- | --- | --- |
| **Audit** | 事件链可完整重放的任务占比 | `scorer/l3.py:580`，四条全过才算 1：① 状态迁移全在 `LEGAL_TRANSITIONS` 里；② 事件按时间单调；③ `order` 事件带得起重放字段；④ 每条 `fill` 对得上一条**更早的** `order` | L1/L3 | **判** |
| `FillSelfConsistent` | 规格没有这一列 | `scorer/l3.py:592` | L3 | **判** —— 与 `Audit` / `SlipSelfConsistent` 三取均值后要求 `== 1.0` 才 `l3_pass`（`scorer/l3.py:758`）。判的是「自报的 `fill_rate` 与**它自己的事件链**重算值一致」，**不与 gold 比**。事件链缺重放字段时记 `skipped` —— **不可检，不是 0** |
| `SlipSelfConsistent` | 规格 §9.2 记 Role = `gate`（2026-09-10 用户裁定 ④） | `scorer/l3.py:746`，容差 `scorer/l3.py::_slip_recompute` | L3 | **判**，与上一行同一个均值（`scorer/l3.py:758`）。判据 = 自报 `slippage_bps` vs **自身事件链**逐单重算值，容差 = **一个最小价位**（`MIN_TICK_CNY = 0.01`）逐单换成 bps 后按成交量加权。**不与 gold 比** —— 与 Fill 同一条理由。实测（`runs_in/m6b/s8-rob-01.strict…`）：重算 53.8834 bps、容差 21.2037 bps、自报 53.8834，判 1.0 |
| **Fill**（成交率） | 规格 §3 | `scorer/l3.py:601` 出 `reported_fill_rate`，`scorer/l3.py:605` 出 `gold_fill_rate` 供对照 | L3 | **与 gold 的对照只报不判**（自报值的**自洽性**由上一组的 `FillSelfConsistent` **判**，见上）。理由（2026-09-06 改判）：S8 题面**没有规定下哪些单**，实测三个 agent 分别产生 12 / 10 / 4 条状态迁移、交易日也各挑各的 —— 成交率是**它自己那一轮的属性**，不是同一个量的两次测量。拿 gold 的数去比等于把「gold 那一轮下了哪些单」当标准答案（与 N-114 同形） |
| **Slip**（滑点 bps） | `量加权(成交价 − 决策时点价)` | 同上 | L3 | **与 gold 的对照只报不判**，理由同上；自报值的**自洽性**由 `SlipSelfConsistent` **判**（2026-09-10 裁定 ④ 把它的 Role 记成 `gate`）。**外加一条仍然成立的登记**：滑点的**符号约定**在 v1.0.13 才写进题面（N-127），而我们自己的两份实现在卖单上符号相反 —— `gateway/sim_engine.py` 的 `slippage_bps` 不按买卖翻符号（与规格 §3 同形），`reference/s8_oracle_common.py` 的 `fill_metrics` 乘了 `sign`。**这不影响现在这条判据**：`SlipSelfConsistent` 比的是「自报 vs 自身事件链」，两边同出一个实现，不经过 gold；要把**与 gold 的对照**纳入判据才必须先对齐两处并以规格 §3 为准（**N-383，仍未裁定**） |
| **状态一致性 / 越权操作率**（S8 面） | 规格 §0.5 | 越权走 Table A 那一列；状态迁移合法性并入 Audit 的第 ① 条 | L1 | **判** |

---

## 3. 一致性署名层（规格 §4）与效果分锚定（对接决定 §1.2）

| 项 | 规格怎么说 | 实现 | 在判吗 |
| --- | --- | --- | --- |
| **效果分 `effect`** | `stage_score = 100 × (被测 − 地板) / (上沿 − 地板)`，夹到 [0,100] | 锚点 `scorer/score_run.py:108`，归一 `scorer/score_run.py:138` | **判，但只有两桩锚点**：null 底 与 oracle 顶。中间锚与上沿锚（卡 5.4 的替换基线阶梯）**未落地** —— `ops/freeze_v10.py:99` 的 `CAPS` 里 `anchor_ladder_54` 是 `False`。**缺锚点时拒绝出数而不是出 0**（`anchor_pending`，`scorer/score_run.py:72`），不会静默给错的数 |
| **CBC**（跨后端一致性） | 同任务跨后端 `1[ρ ≥ τ]` 的均值 | — | **不出**：要同一道题在两个后端上各有一份产物。v1 的真跑矩阵还没铺到「同题跨配置成对」这一步（真 API 累计 2418 次 / 71 run，全部用在接入验证与发布验收上） |
| **ZCSR**（零改动换臂成功率） | 零改动换臂成功数 / 尝试数 | — | **不出**：同上，且它要求同一份 artifact 在另一个臂的环境里原样重跑 |
| **Reproduction@ε** | 协议 artifact 交由异厂配置复现，关键指标落 ε 带的占比 | ε 带本身已有（见 S7 行），缺的是「异厂复现」这一批 run | **不出** |
| **`SearchCount` / `DSR@search` / `IC_deflated`** | 对接决定 §1.3 的署名指标 | 字段预留 `reference/artifact_schema.py:1610`；**`scorer/` 未读** | **不出**（理由见 §2 的 S4 末行） |

---

## 4. 软校验（L2）：v1 **一处都没启用**

规格 §6 把软校验白名单限死在三处：研究计划文本质量、适配映射的语义等价申辩、报告叙述完整性。
**这三处在 v1 一处都没有启用**，因此：

* Table A / Table B 上**没有任何一格来自 LLM 裁判**；
* κ 发布线（双裁判 Cohen's κ ≥ 0.85）**无从谈起** —— 没有 judge 字段就没有 κ；
* 规格 §3 里「自由文本引用进 L2 白名单」那半句在 v1 落空：`Prov` 只判结构化引用。

**这不是省略，是 v1 的设计选择**：署名指标要求零裁判方差（规格 §4），
而 v1 的完成定义是「外部用户能把这套东西跑起来并读懂表」。引入裁判会同时引入
「裁判本身要不要标定」这条链，那条链的第一步（200 条人工标注轨迹，规格 §6）v1 没有做。

**适配赛道**（`scorer/adaptation.py:154` 的五结局分类）是纯规则判定，
不经裁判 —— 它落在 L1，不在 L2。但它今天**一个真跑都没有**：题源裁定卡在用户签字
（N-348，红线 B2），`ops/reports/adapt/` 至今「例 30 / 有 oracle 30 / **有真运行 0**」。

---

## 5. 一页版：v1 到底判了什么

**真的进判据的**：
SR · pass@1 · pass^3 · ProgressRate · Recov · 越权操作率（Table A）；
Cov · PIT · Prov（S1）；Align · Adj · Cal（S2）；Fid（S3）；
IC 的 `mean`/`std`/`icir`/`coverage`（S4）；三态一致率 + 逐日秩相关（S5）；
Cons · Feas · WeightAgree（S6）；11 项回测指标的 `daily` 档 ε 带（S7）；
Audit · FillSelfConsistent · SlipSelfConsistent（S8）；以及**贯穿全部的五族探针闸门**。

**出数但不判**：Steps · $ · Latency · Sig · **Fill / Slip 与 gold 的对照值**（它们的**自洽性**在判，见 §2 的 S8 两行）· IC 的 `positive_ratio` / `ci_low` / `ci_high` · gold 侧对照值。

**v1 不出**：Checkpoint · P(b) 预算曲线 · EX/VES · Exec · Repro · Dir · Decay · TE ·
Δ_adv 与 S7 扩展列 · CBC / ZCSR / Reproduction@ε · 搜索感知紧缩三项 · 全部 L2 软校验与 κ。

**每一条「不出」在上面都有理由**，且理由分三种，读表时要分开：

1. **产物契约里没有这个量**（TE、Dir、Repro 的一半）—— 要改 schema 与题面，是判据变更；
2. **赛道或题面在 v1 不存在**（Checkpoint、Δ_adv、EX）—— 要新出题；
3. **数据算得出但没有对手方**（CBC、ZCSR、S7 扩展列）—— 要更多真跑预算。

第 1 类要重冻结记因（`ops/freeze_v10.py` 的冻结根），第 2、3 类不用。

---

## 6. 与其它发布件的关系

| 想知道 | 去哪 |
| --- | --- |
| 这些数不可比是因为什么变了 | `VERSIONS.md`（四条版本轴）· `CHANGELOG.md`（逐次 bump 的 why/what） |
| 哪些限制是设计性的、哪些留给 v1.1 | `ops/reports/known_limits_v1.md` |
| 两臂之间凭什么可比 | `ops/specs/fairness_protocol.md` |
| τ / ε 是怎么标出来的 | `ops/specs/GeneBench秩相关与标定口径_v1.md` · `ops/reports/calibration_spec_v1.md` |
| 规格原文 | `ops/specs/GeneBench指标规格_v1.md`（设计稿）· `ops/specs/GeneBench指标对接决定_v1.md`（增补，冲突处以它为准） |
