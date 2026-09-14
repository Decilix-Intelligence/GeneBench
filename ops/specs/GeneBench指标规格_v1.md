# GeneBench 指标与评分器规格 v1

承接《GeneBench 设计方案 v1》§3，把主指标从口径落到定义式。每条给：定义、判定层（L1 硬校验 / L2 白名单软校验 / L3 性能结算）、结算数据源、出处。协议依据：用户提供的 GeneQuant §3 全文（截图版，与论文稿一致），核对结果见 §0.5。

## 0 记号与总设定

任务 t∈T，配置 c，臂 a∈{裸, GQ, 文档}，种子 s=1..S（S=3），重试预算 K=3（占位）。阶段 k=1..8，被测产物 A_{t,k}，参考实现产物 R_{t,k}，参考市场视图 V（PIT 快照仓的 as-of 查询结果）。所有比率类指标先在任务内对种子取均值，再对任务宏平均。成功判定 succ(t,c,a,s) ∈ {0,1} 由该任务所属阶段的语义判定给出。

## 0.5 协议对齐表（v1 新增：规格与协议条文的逐项挂钩）

Contract 六元组 → 指标层。⟨I_k,O_k⟩ 的 artifact schema 由 V_k 结构检查覆盖，落在 ProgressRate 与 SR；M_k（须保全的金融语义）对应语义层指标（Fid、Align/Adj/Cal、信号语义、复现容差带）；R_k（执行约束与域不变量）对应越权操作率、Cons% 与无违例率；V_k（验证规则）由 benchmark 评分器独立重实现，即 validator 不计分原则的条文落点；P_k（来源与执行证据）对应 Prov% 与 Audit%。协议规定假设登记、版本与监控沿阶段链维护而非独立线性步骤，据此 Audit 的定义扩为"事件链可重放 + 协议链引用完整（产物对上游 artifact 的 provenance 引用可解析）"。协议总则"金融要害语义不得经隐式默认或推断补全"是整个语义层与静默脑补率共同的条文总纲。

阶段边界 → 探针。Table 2 第三列的 protocol-fixed 边界与 §1/§3 探针一一对应：S2 的时间对齐/复权约定/交易日历/PIT 宇宙即 Align/Adj/Cal/PIT 四探针；S3 的算子语义/参数序/lookback/评估频率即 Fid 比对的四个维度；S5 的信号语义/资产宇宙/频率/方向即 SignalArtifact 合法性检查项；S6 的仓位规则/组合约束/优化目标/TargetPosition 即 Cons/Feas/TE 与 schema 检查；S7 的成本/撮合/交易限制申明即回测协议字段；S8 的可见状态/操作权限/合法状态迁移/执行证据即 Fill/Slip/Audit 与越权率的结算面。

能力协议 → Table A 与敲除。❶信息访问 ↔ PIT%、Prov 与 S1 全组；❷数据分析 ↔ S2 全组；❸程序执行与工具 ↔ Exec、Steps、工具调用合法率；❹研究规划 ↔ Chain 赛道与研究计划软校验字段；❺验证诊断修复 ↔ Recov 与修复轮数——协议明文"可恢复违例进入修复回路、金融要害语义未解决则拒绝"正是适配五结局中"修复后接入"与"正确拒绝"两类的来源；❻状态执行与审计 ↔ 越权操作率、状态一致性、Audit。E0 敲除实验的行定义 = 逐一收回六项能力的 TaskSpec 授权；已验证敲除热力图使用的阶段—能力预测框线与 Table 2 完全一致（S1:❶❸；S2/S4/S6/S7:❷❸❺；S3:❷❸❹❺；S5:❷❸❹；S8:❸❺❻），mock 图无需返工。

适配条文 → 署名口径。§3.3 "源中缺失的信息保持缺失、不得由 agent 补全"是静默脑补率的定义原文；"有效 artifact 进入其语义完整所支持的最早协议阶段——完整定义可进上游研究阶段、信号可进组合构建、TargetPosition 可进回测或模拟交易"是入口路由正确率的判定规则原文；unsupported / unresolved 标记对应结局类"缺口正确标记"；"agent 提出翻译、协议裁决可接纳性"与评分器独立原则并行不悖——可接纳性裁决属被测系统侧行为，计分裁决属 benchmark 侧。TargetPosition 作为执行边界的脚注（保全意图组合、不依赖成交实现）确认 Live Track 以 TargetPosition 序列为结算对象的选择。

> **增补指引（2026-09-01）**：本规格的 §1 探针族、§3 指标口径、§5 标定参数已由
> 《GeneBench 指标对接决定 v1》增补与修订（有效性闸门语义、替换基线阶梯锚定归一、
> 搜索次数感知紧缩、十条新探针、口径冻结表）。两文冲突处以对接决定为准。

## 1 违例探针规格（审计脚本，全部 L1）

前视违例：数据网关强制 as-of 参数，违例 = ∃ 数据请求的目标日期 > 任务 as-of；由网关日志直接结算，不依赖产物申报。日历违例：产物申报的 calendar_id 与参考视图比对，另抽样 20 个交易日做实际对齐核验（申报可造假，行为不能）。复权违例：申报 adjust∈{none,pre,post} 之外，用"指纹法"核验——取窗口内一只已知拆分事件的样本，比对产物引用价格与三种复权口径的数值指纹，判别实际口径与申报是否一致。PIT 违例：产物引用的样本集合与 as-of 宇宙快照（含上市/退市/停牌状态）取差集，非空即污染。欠定语义探针（第五探针）：一部分 Stage/Chain 任务的 TaskSpec 故意欠定某项 materially 必需字段（如不声明复权口径或交易日历），正确行为是把该字段标记 unresolved 或请求澄清，违例 = 产物以隐式默认补全并继续——协议 §3.1 总则的操作化，使静默脑补率从适配赛道推广为全赛道可测。设计原则一句话：验行为不验申报。工程先例：TraderBench 在数据服务层做 temporal locking 与 lookahead detection，同一思想。

## 2 Table A 十项定义式

SR = |{t: 存在可评分终端产物}| / |T|，L1。pass@1 = mean_t mean_s succ，L1/L3，3 种子口径同 Gaia2。pass^k：任务级用无偏估计 C(c,k)/C(n,k)（n 次试验 c 次成功；n=k=3 时退化为三种子全成指示），宏平均；出处 τ-bench。ProgressRate = mean_t (1/8)Σ_k 1[A_{t,k} 通过 V_k 结构检查]，AgentBoard progress rate 的八阶段化，L1。Checkpoint 分（仅 Chain）= Σ_i w_i·1[里程碑 i 达成]/Σ_i w_i，里程碑 = 八个 V_k 通过事件 + 每阶段一个关键语义断言（共 16 个，权重占位 1:1），出处 TheAgentCompany。Steps = 工具调用与提交动作总数，越低越好。$/task 与 Latency：token 计价 + 墙钟；随附预算条件化曲线 P(b) = mean 1[succ ∧ cost≤b]（对数预算网格），报告曲线与 AUC，出处 Gaia2 预算曲线 / RE-Bench。Recov = 恢复成功的失败事件数 / 失败事件总数，失败事件 = 执行报错或校验拒绝，恢复 = 同任务后续尝试通过。越权操作率 = 网关拒绝或越界访问次数 / 数据访问总次数，GeneBench 特有，网关日志结算。附录扩展：校准误差（HLE 口径）、注入攻击成功率（AgentDojo）、无关工具调用识别（BFCL）、裁判 κ。

## 3 Table B 各阶段定义式（主表 30 列的正式口径）

S1 Cov = |获取字段 ∩ 要求字段| / |要求字段|（L1）；PIT% = as-of 正确的取数请求占比（网关，L1）；Prov = 关键数值中带可解析来源引用且核查通过的占比（结构化引用走 L1，自由文本引用进 L2 白名单；思想出处 DeepResearch Bench 的引用核查）。S1 任务按 FinSearchComp 三分法分层：T1 实时/最新值取数、T2 单点历史取数（财政日历、币种、重述口径入判定）、T3 多跳跨期溯源（拆分复权换算、极值聚合、实体消歧）；该文实测难度单调递增且 T3 卡在结构化检索，正好是我们数据网关要供给的能力。

S2 Align = 映射到金标 schema 的字段正确率；Adj、Cal 按 §1 探针 + 与参考视图逐格比对；补充 EX（处理管线执行正确率）与 VES 式效率参考（BIRD）。全 L1。

S3 Fid = 1[ρ_Spearman(f_A, f_R) ≥ τ]（网格：共同覆盖的日期×标的）；Exec = 无错执行率；Repro = 同代码同环境重执行 ρ ≥ 0.999 的占比（CORE-Bench 复现范式）。全 L1。

S4 IC = mean_d corr(f_d, r_{d+1})，RankIC 用 Spearman，ICIR = mean/std（Qlib 口径，FinTSB ranking 维同款）；显著性报 Newey–West t 并按多重检验校正线 t>3（Harvey–Liu）；另报 IC 半衰期（滞后衰减拟合）。误差维（MSE/MAE）与概率维（CRPS）进扩展列。评分器按产物声明的评估设定复算——协议把因子定义与经验效度定为分立对象、验证在声明的期窗/指标/阈值设定下进行（Table 2 的 S4 边界），故 S4 判定读取产物 P 字段中的设定声明，在该设定下重算并与参考比对，不以全局默认覆盖；设定声明缺失本身按欠定语义探针计违例。L3。

S5 Sig = 方向命中率；Dir = 预测–实现方向一致率；Decay = 信号自相关半衰期；全部按 FinTSB 四类运动模式分层报告。L3。

S6 Cons = 硬约束零违反组合占比；Feas = 可行解率；TE = std(w'r − b'r) 年化。L1/L3。CLQT 与 PortBench（2026 新出，见调研库增补）读后可能补充成本感知与相关性感知口径。

S7 Sharpe = √252·mean(r_p)/std(r_p)（费后、含可交易性过滤）；Calmar = 年化收益/MDD；MDD。复现容差带：|m_A − m_R| ≤ ε_m 对每个关键回测指标 m。L3。

S8 Fill = 成交率；Slip = 量加权(成交价 − 决策时点价) bps；Audit = 事件链可完整重放的任务占比。加测对抗差 Δ_adv = score_clean − score_adv，扰动沿 TraderBench 四级（干净→噪声→元级→对抗信号注入），并沿用其教训在报告中区分"靠不动获得的假稳健"（各级分数平坦且交易量趋零）与真适应。Live 长程指标见 §7。L3。

> **S8 Slip 的符号与容差（N-383，2026-09-10 裁定）**
>
> *符号*：`Slip = 量加权(成交价 − 计价基准) / 计价基准 × 10000` bps，成交价高于基准取正、
> 低于取负，**买卖同向、不按方向翻符号**。这一条同时是 S8 五道题两臂题面上那一行的原文
> （N-127，随 v1.0.13 落）。三处实现按本条对齐：`gateway/sim_engine.py::slippage_bps`、
> `reference/s8_oracle_common.py::fill_metrics`（r1.0.21 删掉了它多乘的买卖符号）、
> `scorer/l3.py::_slip_recompute`。
>
> *判据*：Slip 从「只报不判」改为**判**，判的是**自报与 agent 自己那条事件链的一致性**
> （重算 vs 自报），**不与 gold 比** —— S8 的题面没规定下哪些单，agent 与 oracle 两轮
> 不是同一个量的两次测量（同 N-114 的教训）。Fill 同理，维持自洽判。
>
> *容差 = 一个最小价位*（A 股 0.01 元）。逐单换算再按同一套成交量权重加权：
>
> ```
> tol_bps(单 i) = 0.01 元 / 该单的计价基准(元) × 10000
> tol_bps       = Σ_i 成交量_i × tol_bps(单 i) / Σ_i 成交量_i
> ```
>
> 逐单换算而非给一个固定 bps：0.01 元在 1720 元的标的上是 0.058 bps，在 3 元的标的上是
> 33 bps —— 固定 bps 对高价标的过松、对低价标的过严。计价基准取哪一档由题面声明
> `slippage_reference_price` 决定；`close` / `open` 两档的基准是环境侧的价、事件链里没有，
> 那两档下 Slip 记 `unobservable`（**不可检，不是 0**）。


## 4 一致性署名层

CBC（Cross-Backend Consistency）= mean_{任务} mean_{配置对(i,j)} 1[ρ(A_i, A_j) ≥ τ]，同任务跨后端。ZCSR = 零改动换臂成功数 / 尝试数。Reproduction@ε = 协议 artifact 交由异厂配置复现后，全部关键指标落 ε 带的占比。三者均 L1/L3 结算，零裁判方差，是署名指标。

## 5 阈值与容差标定协议

τ（因子秩相关门）：对每个任务用两套独立参考实现，τ = 全任务两两 ρ 分布的 P10（即"独立正确实现之间的自然离散度"决定容差，不拍脑袋）。ε_m（回测复现带）：参考实现在 5 个种子/环境重跑下各指标的极差 ×1.5。κ 发布线：软校验双裁判 Cohen's κ ≥ 0.85 方可采用该字段的 judge 结果（BigFinanceBench 实测 0.95–0.97 作为强参考）；未达线的字段回退为硬判定子集或从计分中移除。

## 6 软校验白名单与"验证验证器"发布件

白名单仅三处：研究计划文本质量、适配映射的语义等价申辩、报告叙述完整性；其余一律 L1/L3。每个 judge 字段配 tool-specific guideline（Gaia2 软检做法）。每版 benchmark 发布附验证器审计报告：对 oracle 产物施加已知保真/破坏两类扰动的单元测试通过率 + 人工标注轨迹抽样（v1 目标 200 条）与自动判定的 agreement / precision / recall；Gaia2 的结构化验证器 0.98 一致率对上下文裁判 0.72 是我们坚持结构化的引用证据。

## 7 Live Track 结算协议（对齐 StockBench 系）

窗口：季度滚入训练截止期之后的真实行情段（免污染的机制性来源）；输入：日频价格、基本面、新闻（同 StockBench 的信号面）；决策空间：GeneBench 里不是裸买卖持，而是协议化的 TargetPosition 序列（这是与 StockBench 系的关键差异——我们测的是研究链产物落到执行，不只是决策 API）；结算指标：累计收益、MDD、Sortino（StockBench 三件套）+ 相对 buy-and-hold 与等权基线的超额、IR；报告 pass^k 的跨窗口版（同配置跨季度窗口的稳定性）。StockBench 的实证教训（多数模型跑不赢 buy-and-hold、静态问答强≠交易强）写进动机段作为"为什么要全流程评测"的证据。

## 7.5 专用系统基线复现口径（首例：RD-Agent(Q)）

框架事实（读后确认，NeurIPS 2025）：RD-Agent(Q) 把量化流程拆成 Research 阶段（目标对齐提示、基于领域先验的假设生成与任务映射）与 Development 阶段（代码生成 agent Co-STEER 实现因子与模型代码），经反馈环评估回测结果后迭代；工作流分为规格、综合、实现、验证、分析五个单元；在 CSI300 上以 Qlib 回测评估，报告 IC/ICIR、ARR、IR、MDD，宣称以少 70% 的因子拿到最高两倍年化。复现口径五条：仓库版本钉死（microsoft/rd-agent，记录 commit）；底层模型经其 LLM 配置替换，构成主表的 harness×model 行；数据经"我们的 PIT 快照仓 → Qlib provider 适配层"喂入，保证与其余系统同源同窗；其原生指标一律不采信，全部产物送 GeneBench 统一评分器重算（公平性协议）；阶段映射备案——其原生管线覆盖 S3（因子研发）、S4（因子剪枝与模型验证）与 S7（Qlib 回测），S1 由 Qlib 现成数据替代、S6 走默认 TopK、S8 缺席，阶段隔离计分下的预期 profile 恰是主表所画的"S3/S4 尖峰"，这一映射写进论文附录的基线说明。同款五条口径适用于 TradingAgents 等其余专用基线，各自补阶段映射即可。

## 8 v1 定稿说明

协议核对完成（§0.5），四项待固化按以下口径收口。pass^k：任务级无偏估计 C(c,k)/C(n,k)（τ-bench 口径，n=k=3 时退化为三种子全成指示）。ProgressRate：采用八阶段结构版而非 AgentBoard 的子目标加权版——子目标标注成本高且与 V_k 结构检查重复，取舍理由入论文附录。Checkpoint：采用"里程碑积分 + 全链达成加成"机制（TheAgentCompany），两部分权重占位 1:1，其原文合成公式在工程期对开源实现核对后钉死（本规格唯一标注待验证项）。Chain 赛道研究计划字段：采用目标—证据两层轻量 rubric，不引入 PaperBench 全树——全树标注成本与我们任务量不成比例，PaperBench 作引用出处而非实现模板。本规格即 v1，下一步产出工程实施稿。


---

## 9 指标登记表（v1 发布口径，2026-09-10 用户裁定 ⑩⑪⑫⑬）

> **这一节是登记，不是设计**。§0–§8 是设计稿（增补与修订见《GeneBench 指标对接决定 v1》，
> 冲突处以对接决定为准）；这一节回答的是另一个问题：**v1 的发布表上到底有哪些列，
> 每一列的 Role 是什么，算不出来的时候写什么**。
>
> 出表的代码是 `ops/mk_metric_tables.py`，它自己带一份同样的登记；
> `ops/test_report_columns.py` **逐项**比对两份 —— 多一个少一个都红。
> 两份都写不是冗余：规格给人读，代码出数，只有互相钉住，「规格里写了代码没出」
> 与「代码出了规格没写」才会在提交时被抓住，而不是等到有人照规格去读一张没有那一列的表。

### 9.0 Role 与空值词汇

**Role**（四取一）：

| Role | 含义 |
| --- | --- |
| `gate` | 进判据（`l3_pass` / `validity` / 闸门），算错了会改结论 |
| `fidelity` | 保真度读数：与参考实现的一致程度。**v1.0.14 起取代原来的 `effect`**（⑫）—— 旧名字暗示「效果分」，而这些量量的是「像不像」，不是「好不好」 |
| `reported` | 出数进报表、**不进**判据 |
| `telemetry` | 遥测与样本量（步数、token、墙钟、分母计数） |

**空值词汇**（⑪⑬，三者语义互不相同，报告里不许混）：

| 写法 | 含义 | CSV | Markdown | LaTeX |
| --- | --- | --- | --- | --- |
| 数值 | 测到了 | `0.5` | `0.5` | `0.500` |
| `—` | **没有读数**：这一格的 run 全部落在「拒绝 / 诚实终止 / 未结算 / 预算截断」四类里 | `—` | `—` | `---` |
| `unobservable` | **检不了**：有可用的 run，但这个量在这些 run 上测不出来（网关日志不可得、基准价不在事件链里、旧版 scorer 没产出这个量……） | `unobservable` | `unobservable` | `\textit{unobservable}` |
| 空 | 这一格**一个 run 都没有**（该配置该臂在这一阶段一道题都没跑） | （空） | （空） | `---` |
| `n/a` | **不适用**：这个量在这一阶段根本不定义。只出现在 §9.2 那张**宽表**上（它是「阶段 × 全部逐阶段指标」的叉乘，S3 那一行自然有一堆 S1 / S8 才有的列） | `n/a` | `n/a` | `\textit{n/a}` |

**`0` 不在这张表里** —— `0` 是「测了，是零」。把「检不了」记成 0 会让恒绿的门与真的零命中同形，
这正是 §1「验行为不验申报」要防的那件事。

**`n/a` 与「空」为什么必须分开**（2026-09-11 红队 V2.rt finding 7）：宽表上不填的话，「S3 没有 `Prov` 这个量」与「S3 一道题都没跑」在表上长得一模一样 —— 前者是设计，后者是缺口。实现在 `ops/mk_metric_tables.py::_mark_not_applicable`，字面量在 `scorer/report.py::NOT_APPLICABLE`。LaTeX 上「没有读数」与「没有 run」都写 `---`
（booktabs 里没有第二种空格），要分开看 CSV。

**取消聚合**（⑪）：v1 **不出总分**。没有任何一列把多阶段合成一个数；
效果分的归一值（`effect`）照旧逐 run 落在结果库，**不进任何发布表**。
逐指标按各自的闸门条件报告 —— 「这一列过没过」的判据写在下面每一行里。

### 9.1 全量 agent 指标表（18 项）

按 `(config_id, arm)` 出。主表的 `SR` / `P@1` / `$` 三列取自这里。

| 指标 | Role | 口径 | 数据源 | 闸门条件 | 不可得时 |
| --- | --- | --- | --- | --- | --- |
| `SR` | gate | 存在可评分终端产物的比例；任务内取均值再宏平均 | `record.sr_bucket`，分母 `runner/c42/failure_modes.py::sr_denominator`（**只排除** `unscorable_harness`） | 无阈值，越高越好；与别的臂并排读 | 四类原因 → `—` |
| `P@1` | gate | `mean_t mean_s succ`；succ = 闸门 valid ∧ L3 通过（诚实终止题按 `correct_handling`） | `record.validity` / `l3_pass` / `correct_handling` | 未结算的 run **既不进分子也不进分母**，单列 `unsettled_runs` | 四类原因 → `—` |
| `pass^3` | gate | τ-bench 无偏估计 `C(c,k)/C(n,k)`，宏平均 | 同 `P@1` | `n<k` 的任务不进均值，计数报在 `pass^3_tasks_with_3_runs` | 空 |
| `ProgressRate` | gate | `1[产物过 V_k 结构检查]` 的均值（结构版，非子目标加权版） | `record.sr_bucket` / `malformed` | 无阈值 | 空 |
| `Steps` | telemetry | 每次运行经边车的模型调用次数（**网络侧计数**，不采信自报） | `runner/c42/llm_trace.py` | 不判 | 空 |
| `$` | telemetry | 每 run `cost_usd` 均值。**这是成本上界不是账单实数**（DeepSeek 分高峰/低谷两档而边车不记档位，取高峰价） | `runner/pricing.yaml` × 网络侧 usage | 不判 | 缺价或缺 usage → 空（**不是 0**，也不套 `—`：被拒的运行照样花了钱） |
| `Latency` | telemetry | `run.json.elapsed_s` 均值（runner 侧真值） | `run.json` | 不判 | 空 |
| `Recov` | gate | 在至少被 validator 拒过一次的运行里，最终 valid 的比例 | `work/protocol/validator.log` | 无阈值 | 裸臂没有这条回路 → 空 |
| `Ovr` | gate | 越权操作率 = Σ403 / Σ数据与操作请求，**合并分子分母**（不是对逐 run 的比率取均值）。**这一列数全部 run**；主表 S8 那一列同名但只数 S8 的 run | 网关 access_log（403），退回边车 `log/egress.jsonl` | 期望 0；非 0 即有越界行为，逐条原因在 `overreach.reasons` | 日志不可得 → `unobservable` |
| `tokens_prompt` | telemetry | 网络侧 usage 求和 | 边车 llm trace | 不判 | 空 |
| `tokens_completion` | telemetry | 同上 | 边车 llm trace | 不判 | 空 |
| `unsettled_runs` | telemetry | 有可评分产物、闸门也过了，但判据在 v1 没有输入的 run 数 | `record.l3_pass is None` | 不判 —— 它是读 `P@1` 的前提 | 0 是真值 |
| `budget_exhausted_runs` | telemetry | 撞了预算闸的 run 数。判据是**边车真的发过 429**（`record.budget`），不是 `run_status` | `log/llm_log.jsonl` | 不判 | 0 是真值 |
| `unbounded_requests` | reported | 没界定右端的取数请求**总数**（行为计数，不是比率） | 网关日志 | 期望 0 | 一条可用样本都没有 → 空；**真值 0 写 0** |
| `overreach_observable_runs` | telemetry | `Ovr` 的样本量：有网关日志的 run 数 | 同 `Ovr` | 不判 | 0 是真值 |
| `pass^3_tasks_with_3_runs` | telemetry | `pass^3` 的样本量：有 k 次运行的任务数 | 同 `pass^3` | 不判 | 0 是真值 |
| `effect_settled_runs` | telemetry | 效果分在几个 run 上结算得了。**效果分本身不出表**（⑪），这一列留着是为了让读结果库的人判断那一列可不可信 | `record.effect is not None` | 不判 | 0 是真值 |
| `unobservable_probes_mean` | telemetry | 每 run 平均有几族探针**检不了** | `record.unobservable` | 不判 —— 但它大于 0 就说明那一批的闸门有洞 | 0 是真值 |

### 9.2 全量阶段指标表 —— 逐阶段（39 条）

> **⑥-a（2026-09-11 用户裁定）：条数以生成器为准。** 生成器
> `ops/mk_metric_tables.py::STAGE_METRICS` 现算 **39** 条（S1 3 / S2 4 / S3 5 / S4 6 /
> S5 7 / S6 3 / S7 4 / S8 7），下表逐条登记同样的 39 条，每条写明它是什么（口径）、
> 数据源、Role、闸门条件与不可得时显示什么。两边**逐项相等**由
> `ops/mk_metric_tables.py --check` 与 `ops/test_report_columns.py` 钉住：多一条少一条都红。
> 规格是给人读的、代码是出数的 —— 只有互相钉住，「规格写了代码没出」与
> 「代码出了规格没写」才会在提交时就被抓住。

按 `(config_id, arm, stage)` 出。正确性量取**闸门过了的 run** 上的均值（与 Table B 同口径：
闸门失败时效果分不产出，不是低分）；探针态与越权率取全部 run（它们是 L1 事实）。

| 阶段 | 指标 | Role | 口径 | 数据源 | 闸门条件 | 不可得时 |
| --- | --- | --- | --- | --- | --- | --- |
| S1 | `Cov` | gate | 获取字段 ∩ 要求字段 / 要求字段；要求字段取 **gold 的** `fields_obtained` | `scorer/l3.py::compare_cov` | `Cov = 1` | 空 |
| S1 | `PIT` | gate | as-of 正确的取数请求占比；基准 as-of **只取任务侧**，不回退到产物自报 | 网关日志 | `PIT = 1` | 日志不可得或零取数 → `unobservable` |
| S1 | `Prov` | gate | 产物申报的每一次取数里，能在日志里找到同端点同时刻那条的占比 | 网关日志 + 产物取数台账 | `Prov = 1`（日志可得时） | 日志不可得或没有台账 → `unobservable` |
| S2 | `Align` | gate | 映射到金标 schema 的字段正确率 | `scorer/l3.py::compare_align` | `Align = 1` | 空 |
| S2 | `Adj` | gate | 申报的复权口径与任务声明一致（指纹法核验，见 §1） | 同上 | `Adj = 1` | 空 |
| S2 | `Cal` | gate | 交易日历一致（申报 + 抽样实际对齐核验） | 同上 | `Cal ≥ 0.99` | 空 |
| S2 | `CellAgree` | fidelity | 面板**逐格**比对的一致率 | 同上 | `CellAgree ≥ 0.999` | gold 面板不在 / 没有共同数值列 → `unobservable` |
| S3 | `fid_day_rate` | fidelity | 逐日截面秩相关 `≥ τ` 的交易日占比；分母取 **gold 侧可比交易日数** | `scorer/l3.py::compare_tau` | 与 `rho_p10` 一起判，见下 | 空 |
| S3 | `rho_p10` | gate | 逐日秩相关分布的 **P10**（不是先对时间平均再取分位） | 同上 | `rho_p10 ≥ τ`（τ = `calibration.json` 的 `tau.value`） | 没有可比交易日 → `unobservable` |
| S3 | `rho_median` | reported | 逐日秩相关中位数 | 同上 | 不判 | 空 |
| S3 | `rho_mean` | fidelity | 逐日秩相关**均值**（主表 S5 列 `ρ̄` 的同一个量） | 同上 | 不判 | 空 |
| S3 | `day_coverage` | gate | 实际比过的交易日 / gold 可比交易日 | 同上 | `≥ 1`（少交的交易日不是「没被判」，是「没交」） | 空 |
| S4 | `within_band_rate` | fidelity | 落在 ε 带内的指标占比（主表 `IC-agr`） | `scorer/l3.py::compare_epsilon` + `calibration.json` 的 `epsilon.ic_family` | `= 1` | 没有可用 ε 档 → `unobservable` |
| S4 | `max_band_ratio` | gate | 最差的那一项 `abs(差) / ε` | 同上 | `≤ 1` | 同上 |
| S4 | `band:ic_stats.mean` | gate | IC 均值是否落带（`absolute`） | 同上 | `= 1` | 无带 → `unobservable` |
| S4 | `band:ic_stats.std` | gate | IC 标准差是否落带（`relative`） | 同上 | `= 1` | 同上 |
| S4 | `band:ic_stats.icir` | gate | ICIR 是否落带（`absolute`，年化因子 252 冻结） | 同上 | `= 1` | 同上 |
| S4 | `band:ic_stats.coverage` | gate | 覆盖率是否落带（`relative`） | 同上 | `= 1` | 同上 |
| S5 | `StateAgree` | gate | 三态一致率（`null` 无观点 / `flat` 主动空仓 / 数值 是**三个**状态，`fillna(0)` 判违例）；分母取 gold 的格数 —— 少交也是不一致 | `scorer/l3.py::compare_sig` | `= 1` | 空 |
| S5 | `Sig` | reported | 方向命中率（规格 §3 的 Sig）。**只报不判** —— 它没有标定 | 同上 | 不判 | 没有可比数值格 → `unobservable` |
| S5 | `fid_day_rate` | fidelity | 同 S3 | 同上 | 与 `rho_p10` 一起判 | 空 |
| S5 | `rho_p10` | gate | 同 S3，用同一把 τ | 同上 | `rho_p10 ≥ τ` | 空 |
| S5 | `rho_median` | reported | 同 S3 | `compare_tau` 路的 S5 题 | 不判 | 走 `sig` 路的题不出 → `unobservable` |
| S5 | `rho_mean` | fidelity | 同 S3，**主表 S5 第二列 `ρ̄`** | 同上 | 不判 | 空 |
| S5 | `day_coverage` | gate | 同 S3 | `compare_tau` 路的 S5 题 | `≥ 1` | 走 `sig` 路的题不出 → `unobservable` |
| S6 | `Cons` | gate | 硬约束零违反的调仓日占比 | `scorer/l3.py::compare_cons` | `= 1` | 空 |
| S6 | `Feas` | gate | 有可行解的调仓日占比 | 同上 | `= 1` | 空 |
| S6 | `WeightAgree` | gate | 目标权重与 gold 的一致度（主表 `W-agr`）—— 补上「Cons/Feas 都过但权重完全不同」的空档 | 同上 | `≥ 0.999` | 空 |
| S7 | `within_band_rate` | fidelity | 11 项回测指标落 ε 带的占比（主表 `ε-agr`）。**只在 `daily` 档判**（`weekly` / `monthly` 的 ε `usable=false`） | `compare_epsilon` + `epsilon.by_frequency` | `= 1` | 频率没有可用 ε 档 → `unobservable` |
| S7 | `max_band_ratio` | gate | 最差的那一项 `abs(差) / ε` | 同上 | `≤ 1` | 同上 |
| S7 | `ledger_conservation` | gate | 台账守恒探针的三态（主表 `Ledger`）：`clean` = 现金 + 市值 − 总资产 的最大绝对残差在容差内 | `record.probe_states`，判在 `reference/artifact_schema.py` 的 `ledger_not_conserved` | `clean`（列上就是 1.0） | 探针检不了 → `unobservable` |
| S7 | `attribution_conservation` | gate | 归因守恒探针的三态：alpha + beta + cost − total 的残差在容差内 | 同上 | `clean` | 同上 |
| S8 | `Audit` | gate | 事件链可完整重放（四条全过才算 1：状态迁移合法 / 事件时间单调 / `order` 带得起重放字段 / 每条 `fill` 对得上更早的 `order`） | `scorer/l3.py::compare_fill` | `= 1` | 空 |
| S8 | `FillSelfConsistent` | gate | 自报 `fill_rate` 与**自己那条事件链**重算值一致。**不与 gold 比** —— S8 题面没规定下哪些单，两轮不是同一个量的两次测量 | 同上 | `= 1` | 事件链缺重放字段 → `unobservable` |
| S8 | `SlipSelfConsistent` | gate | 自报 `slippage_bps` 与自身事件链重算值一致，容差 = **一个最小价位**逐单换算再按成交量加权（N-383）。**Role 由 `reported` 改为 `gate`（④ 2026-09-10 裁定）** | 同上 | `= 1` | `slippage_reference_price` 取 `close` / `open` 两档时基准价不在事件链里 → `unobservable` |
| S8 | `legal_transitions` | reported | Audit 第 ① 条：状态迁移全在 `LEGAL_TRANSITIONS` 里 | 同上 | 不单判（并入 `Audit`） | 空 |
| S8 | `events_monotone` | reported | Audit 第 ② 条：事件按时间单调 | 同上 | 同上 | 空 |
| S8 | `orders_replayable` | reported | Audit 第 ③ 条：`order` 事件带得起重放字段 | 同上 | 同上 | 空 |
| S8 | `fills_linked_to_orders` | reported | Audit 第 ④ 条：每条 `fill` 对得上一条更早的 `order` | 同上 | 同上 | 空 |

### 9.3 全量阶段指标表 —— 六条跨阶段

八个阶段的每一行都有这六列。

| 指标 | Role | 口径 | 数据源 | 闸门条件 | 不可得时 |
| --- | --- | --- | --- | --- | --- |
| `invalid_rate` | gate | 闸门判 invalid 的 run 占比。分母与 SR 同口径（**只排除** `unscorable_harness`）—— 拿 `len(rs)` 当分母会让「harness 越不稳，invalid 率看起来越低」 | `record.validity` | 期望 0 | 分母为 0 → 空 |
| `honest_halt_rate` | reported | 诚实终止的 run 占比：题面欠定、产物如实标 `unresolved` 并停下 | `record.correct_handling` | 不判 —— **它高不是坏事**，那是协议要的行为 | 空 |
| `unsettled_rate` | reported | 未结算的 run 占比：有可评分产物、闸门也过了，但判据在 v1 没有输入 | `record.l3_pass is None` | 不判 —— 它高说明**我们**缺判据，不是被测方不行 | 空 |
| `Decl` | fidelity | **契约必填声明完整率**：该阶段 `declaration_fields(stage)` 里「如实给出」的字段占比。如实 = 键在、值非 null、枚举字段取值合法；标 `unresolved` 时**本题确实欠定该字段**才算如实（乱标不算，如实标 **计入分子** —— 把它记 0 等于罚诚实） | `scorer/l3.py::declaration_metrics` | 期望 1；`< 1` 说明有金融要害语义没申明 | 产物没有 `declarations`（畸形）→ `unobservable`；旧版 scorer 结算的记录同 |
| `Set` | fidelity | **评估设定申明率**：该阶段 **payload 依赖的**声明子集（`PAYLOAD_DEPENDS_ON[stage]` 各叶子依赖的并集）里如实给出的占比 —— 即「这份 payload 的数到底是在哪套设定下算出来的」。主表放在 **S4** 列：`ic_stats` 依赖 `holding_periods / ic_method / quantiles`，缺一项这份 IC 就没有可复算的口径 | 同上 | 期望 1 | 同上 |
| `Ovr` | gate | 该阶段的越权操作率 = Σ403 / Σ请求 | 网关 access_log | 期望 0 | 日志不可得 → `unobservable` |

### 9.4 主表（固定十九列）

`SR / P@1 / $` + 每阶段两列，**列名与顺序写死**（⑩），实现见 `scorer/report.py::MAIN_TABLE_COLUMNS`：

| # | 列 | 来自 | # | 列 | 来自 |
| --- | --- | --- | --- | --- | --- |
| 1 | `SR` | §9.1 | 11 | `Set` | §9.3（S4 切片） |
| 2 | `P@1` | §9.1 | 12 | `Sig` | §9.2 S5 |
| 3 | `$` | §9.1 | 13 | `ρ̄` | §9.2 S5 `rho_mean` |
| 4 | `Cov` | §9.2 S1 | 14 | `W-agr` | §9.2 S6 `WeightAgree` |
| 5 | `Prov` | §9.2 S1 | 15 | `Cons` | §9.2 S6 |
| 6 | `Cell%` | §9.2 S2 `CellAgree` | 16 | `ε-agr` | §9.2 S7 `within_band_rate` |
| 7 | `Adj` | §9.2 S2 | 17 | `Ledger` | §9.2 S7 `ledger_conservation` |
| 8 | `Fid` | §9.2 S3 `fid_day_rate` | 18 | `Audit` | §9.2 S8 |
| 9 | `Decl` | §9.3（S3 切片） | 19 | `Ovr` | §9.3（S8 切片） |
| 10 | `IC-agr` | §9.2 S4 `within_band_rate` | | | |

**第 6 列换过一次（⑥-c，2026-09-11 用户裁定）**：原来是 `Align`，现在是 `Cell%`（取 `CellAgree`）。
`Align` 量的是**申报** —— 字段有没有映射到金标 schema；`CellAgree` 量的是**内容** ——
面板逐格对不对。两者会分叉，而分叉的方向对被测方有利：
`ops/reports/i_rehearsal_v2/scores/s2-cor-01.strict.cfg-codex-deepseek.r02.score.json`
这条真记录里 `Align = 1.0` 而 `CellAgree = 0.0`（字段全映对了，一个格都没对上）。
`Align` 没有被删 —— 它照旧进 `l3_pass` 判据、照旧在 §9.2 的 S2 四条里；
`Adj` 留在主表第 7 列作**有效性列**（复权口径与任务声明一致）。

逐列的定义 / 数据源 / 闸门条件 / 不可得时显示什么，另有一份给红队与外部读者的
`ops/reports/report_spec_v1.md`。
