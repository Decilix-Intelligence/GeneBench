# v1.0 已知限制逐条判定（卡 5.2）

> 生成：2026-09-07，卡 5.2。**判定口径只有一条：挡不挡外部用户**（照手册能不能把这套东西用起来）。
> 挡的修；不挡的留在表里并注明是**设计性限制**还是**v1.1**。
> 本表是 `ops/reports/v1_0_readiness.md` §5 那张表的逐条裁定版，两张表并存：那张说「状态是什么」，这张说「拿它怎么办」。

## 这张表是什么、怎么读

> **给外部用户的导言（卡 6.3 补，2026-09-08）。下面的表一行没动。**

这张表是 GeneBench v1.0 的**已知限制逐条判定**。它不是 bug 列表，也不是待办清单 ——
每一条都已经被量过、被判过，并且**判定口径只有一条：挡不挡外部用户**
（照手册能不能把这套东西用起来）。

**怎么读三个判定**：

| 判定 | 含义 | 你该拿它怎么办 |
| --- | --- | --- |
| **已修** | 本版之内已经关掉，表里留着是为了留下证据链 | 不用管；引数时可以引它的证据路径 |
| **设计性限制** | **v1 就是这么定义的** —— 不是缺陷，是边界 | **读结果时要知道它在**。例如 S6 不出 TE：不是算错了，是 v1 的 S6 产物里根本没有收益率序列 |
| **v1.1** | 要**改判据**或要**新证据**才能动，本版不做 | 不影响你今天跑；但**不要**拿它当「我们漏了」来引 |

**「设计性限制」与「v1.1」的区别，一句话**：
前者**改了就不是 v1 了**（改它要重新定义产物契约或题面，也就要重推版本轴、重出集）；
后者**只是这一版还没做到**（判据不变、口径不变，缺的是实测数值或一轮红队）。
把两者混在一起读，会得到两种相反的错误印象 ——
把设计性限制当成缺陷，或者把 v1.1 项当成永久边界。

**还有第三类吗？没有。** 收口时逐条复核过：表上**不存在**「挡外部用户、我们自己搁置不修」
的条目（见文末「收口核对」一节）。

### ⚠ 三条**待裁定**：挡着，但不是我们搁置的（其中两条已于 2026-09-10 裁定并落地）

这三条各自需要一次**判据变更或题源裁定**，而那要仓库所有者点头。
> **2026-09-10 更新（卡 W.rt）**：`N-388`（默认预算档）与 `N-348`（适配赛道题源）**用户已裁定并落地**，下表两行保留原文并加删除线，收口见文末两节。**只剩 `N-130` 一条挡着。**
它们在文末「收口核对」一节里单列出来，**在这里再说一遍，是为了不让它们藏在表格深处**：

| **待裁定** | 挡什么 | 裁定之前的绕法 | 票据 |
| --- | --- | --- | --- |
| ~~**默认预算档 `max_tokens = 600_000`**~~ **已裁定并落地（2026-09-10）** | ~~**挡结果解读，不挡使用**：实测一批 8/8 撞的是 token 闸（调用数只用到 18–22 / 100），主表上的 `SR` / `pass@1` 读的是「预算够不够」而不是能力~~ | ~~真跑时显式给 `--max-tokens 3000000`；矩阵 yaml 里写一行 `max_tokens: 3000000`~~ —— **这条绕法今天会把预算压低，作废**：默认档已是 **6,000,000**，真跑不要再显式给 `--max-tokens` | **N-388** → 见文末「N-388 / N-383 / N-384 收口」 |
| ~~**适配赛道的题源**~~ **已裁定并落地（2026-09-10）** | ~~**挡整条适配赛道**（主赛道不受影响）：30 个例子的输入内容上就是基准题的答案，裁定之前一个 bundle 都不许推上执行面~~ | ~~无 —— 守门是刻意的，按集拒~~ —— 守门已显式解除并记因；30 例各有一次真运行 | **N-348** → 见文末「适配赛道的题源已裁定」 |
| **S7 在 ≤300 次调用的预算里做不完** | **挡「S7 这一阶段能不能有真 agent 产物」，不挡整套系统的使用**；瓶颈是**回合数**不是上下文 | 无 | **N-130** |

**为什么单列**：这三条如果只写在表里，读者会把它们读成「已经判过、不用管了」。
实际上它们是**开着的问题**，只是决定权不在施工侧。

### 这张表与别处的关系

* `ops/reports/v1_0_readiness.md` §5 那张表说「状态是什么」，**本表说「拿它怎么办」**，两张并存；
* 指标层面「哪一项今天真的在判、哪一项只报不判」在
  `ops/specs/metrics_as_implemented_v1.md`；
* **挡发布**（而不是挡使用）的事在 `RELEASE_MANIFEST.json` 的 `blockers`，那是另一组；
  **条数与逐条内容以该文件为准，本表不复述** —— 复述过的那一次就分叉了（README §5 写「四条」而这里曾写着「三条」，红队阶段六 major）。

---

## 判定汇总

| 判定 | 条数 |
| --- | --- |
| 已修（本卡或此前已关，本卡核实） | 7 |
| 设计性限制（v1 就是这么定义的，写清楚即可） | 6 |
| v1.1（要改判据或要新证据，本版不做） | 6 |

## 逐条

| 编号 | 一句话 | 判定 | 证据 |
| --- | --- | --- | --- |
| N-103 | `s6-rob-02` 因无实质性证据出不了集 | **已修**（卡 5.2） | 证据进 `genetask/schema.py::DIVERGENCE_EVIDENCE`（私有 79 处 / 公开 81 处指标超 daily 档 ε 带，两条通道都 material）；出集 33 → **34** 题；两条通道各真跑一次 oracle **零 finding**（`ops/reports/probe_run_oracle.cumulative.json`、`ops/reports/public/probe_run_oracle.cumulative.json`）|
| N-279 | `s2-eco-01` 的 oracle 打 `/bars?universe=…`，网关 422 —— 出集题里唯一跑不出 oracle 的一道 | **已修**（卡 5.2） | 取小改那条（只动参考轴 `solve.py`，按 code 批量 + 按 `MAX_ROWS` 分批）；两条通道各真跑一次**零 finding**，网关日志 8 条 = 2 + 2×3 批，与新的「理论最少请求数」逐字对上 |
| N-127 | S8 滑点的**符号约定**题面没写 | **已修（题面部分）**；判据部分 → v1.1 | 五道题两臂各加一行「成交价高于计价基准时取正、低于取负，单位 bps」，与规格 §3 的 `Slip = 量加权(成交价 − 决策时点价)` 同向；`ops/test_s8_event_fields.py` 钉住。**Fill / Slip 仍只报不判**（`scorer/l3.compare_fill`）—— 纳入判据要另一轮红队，留 v1.1 |
| N-128 | S8 事件记录的**字段**题面与 schema 都没规定，而 Audit 要求「可完整重放」 | **已修（题面 + schema 部分）**；收紧 `required` → v1.1 | 五道题两臂各加四行（order / fill / cancel / state 各要哪些键 + `state_transitions` 要 from/to/order_id）；同一组字段进 `PAYLOAD_SHAPE["S8"].events` 的叶子 `properties` 并重生成八份 `ops/specs/artifact_schema/v1.0/S*.json`。**没有收紧 `required`**：收紧会让 `reference/artifact_samples.py` 的合法样例与既有 121 份真产物集体变畸形，那是判据变更 |
| N-120 | 跑批没把可交易性视图喂给校验器 | **已修**（卡 1.1-c 落地，本卡核实） | 本卡重跑 `s2-cor-01` / `s5-cor-01` 私有 oracle **零 finding**，`calendar` 与 `missing_masquerading_as_signal` 两族真被调用（`ops/reports/probe_matrix_oracle.md`）；判据钉在 `ops/test_public_acceptance.py`（本卡随批跑绿）。**局限照旧**：S8 四题拿不到视图（N-288），逐题记「这两族没被调用过」，不假装 clean |
| N-126 | S6 的 **TE**（跟踪误差）出不来 —— 它要收益率序列，而 v1 的 S6 产物里没有 | **设计性限制** | v1 的 S6 契约（`PAYLOAD_SHAPE["S6"]`）只有 `targets` / `cash_ratio`，没有收益率序列；`scorer/l3` 的 `cons` 判据本来就**不出** TE，并在 `note` 里写明（`scorer/l3.py`「TE 未出：规格 §3 的跟踪误差要收益率序列，S6 产物里没有（N-126）」，`ops/test_scorer_l3.py` 有断言盯着「TE 出不了要写在 note 里，不能悄悄不提」）。**不挡外部用户**：S6 的 Cons / Feas 照常判。v1.1 的补法：给 S6 的 payload 加一段「按 target 权重 × 次日收益」的逐日收益序列，或把 TE 挪到 S7（那里有逐日台账）|
| N-117 | S4 的 IC 族**没有标定 ε 带** | **v1.1** | S4 的 L3 未结算 → effect 扣住；未结算的 run 既不进 pass@1 的分子也不进分母（`unsettled_runs` 列如实报）。**不挡使用**：跑得出来、报表说得清为什么没有数 |
| N-119 | `missing_masquerading_as_signal` 在 M6 集上造不出破坏样本 | **设计性限制**（窗口性质） | 本窗口一格 `no_data` 都没有，这一族的方向未被 M6 集证过。换窗口即可证；判据本身没问题 |
| T-13 | 网关日志**跨机取回**未定 | **设计性限制** | f02 侧四个日志族按 `unobservable` 记；数据面结算读本机日志，这四族在主表里是真判。外部用户在单机上跑不受影响 |
| N-105 | RD-Agent(Q) 没有 LLM 驱动路径 | **设计性限制**（上游） | 三配置里只有两个能跑真题；这是被测系统自身的形态，不是我们的缺陷，主表按能力映射如实标 |
| 卡 5.4 | 替换基线**阶梯**未落地 | **v1.1** | 效果分只有两桩锚点（null 底 / oracle 顶），`anchor_ladder_54=false`；判据（anchor 定义与归一公式）已冻结，缺的是实测数值。结算侧对缺锚点的处置是**拒绝出数而非出 0**（`anchor_pending`）—— 不会静默给错的数 |
| N-129 | 协议 validator 与评分器**判得不一样** | **v1.1（待批）** | 10 个 run 有 `validator.log`、调用 18 次、报违例 0 次，而同批评分器判 malformed 的有 4 个 → GQ 臂的修复回路一次都没启动。要不要两者判据同源是签字项（同源的代价是协议工件里出现评分器的规则）|
| N-130 | S7 在 ≤300 次调用的预算里做不完 | **v1.1（待用户裁定）** | 四个 run（150 闸 / 3 M token 撞 token 闸；90 闸 / 20 M token 撞调用闸）全无产物。卡 4.3 之后 S7 走 300 次 / 18 M 的档，但**回合数**仍是瓶颈（tokens 只用到 5.2–5.6 M）。挡的是「S7 这一阶段能不能有真 agent 产物」，不挡整套系统的使用 |
| 新登记（本卡量到） | 滑点的符号在**我们自己的两份实现**里不一致 | **v1.1（CONFLICT，已登记）** | `gateway/sim_engine.py::slippage_bps` 按 `Σ qty × (成交价 − 基准) / 基准` 算，**不按买卖翻符号**（与规格 §3 同形）；`reference/s8_oracle_common.py::fill_metrics` 的 docstring 写「买正卖负」并真的乘了 `sign`。买单两者同号，卖单相反。**今天不影响任何分数** —— 2026-09-10 裁定 ④ 之后进判据的是 `SlipSelfConsistent`（自报 vs **自身事件链**，逐单一个价位容差），**不经过 gold**，所以两份实现的符号差碰不到它；要把**与 gold 的对照**纳入判据才必须先把这两处对齐并以规格 §3 为准（N-383） |
| 新登记（本卡量到） | 出集清单里仍有 **6 道欠定探针题**不落盘 | **设计性限制** | `s1/s2/s3/s4/s5/s8-rob-02` 六道被 E9c/E9d2 拦在落盘之前 —— 它们的欠定字段还没有实测实质性证据。这**正是判据在起作用**（没有证据就不出题），不是缺陷。要放行就照 `s6-rob-02` 这次的路子跑 `ops/run_materiality_screen.py` |
| 新登记（W2 量到） | 公开包的 **csi1000 成分名单无法用公开源重建** —— baostock 没有中证 1000 成分接口 | **设计性限制（上游）** | baostock 0.9.3 的成分接口只有 `query_hs300_stocks` / `query_zz500_stocks` / `query_sz50_stocks`（实测 `dir(baostock)`），**没有** `query_zz1000_stocks`。csi300 / csi500 已只用 baostock 重建并与私有 `universe_pit` 逐日对账（`ops/reports/public/instruments_rebuild.md`：csi300 成员**一只不差**、逐日 Jaccard 均 0.9874；csi500 只在私有的 32 只全部落在首 14 天的 qlib 种子段）；**csi1000 仍派生自私有 `universe_pit`（上游 tushare），不在 baostock 的许可射程内**。**不挡使用**（名单就在包里，跑得动）；挡的是「公开包在数据许可上完全自足」这一条。`ops/test_W2.py::test_baostock_has_no_csi1000_constituent_api` 钉住 —— 上游哪天加了这个接口，那条测试会红 |
| 新登记（红队 W.rt 量到） | **S6 gold 的 `provenance[0].artifact_id` 是一个未填的占位串** `TODO:signal-artifact-id-missing` | **已于 r1.0.22 修复（2026-09-11，卡 X2）** | 五份 S6 参考解（`s6-{cor,eco,ops,rob-01,rob-02}-01`）全部带这个值，来源是 `genetask/templates/S6/*/solve.py` 里 `meta.get("artifact_id", "TODO:…")` 的兜底值 —— 上游信号 parquet 的 schema metadata 里没有 `artifact_id`。**后果落在适配赛道**：`adapt-l1-08` / `l2-07` / `l2-08` / `l3-06` 四例的 `broken.json` 也带着它，而适配臂的 `INSTRUCTION.md` 规则 1 要求「源里没有的写成显式 `unresolved`」——被测方照做，oracle 却要求原样抄回，`scorer/adaptation.py::match_oracle` 于是在 `provenance` 上判不一致。v1.0.14 签字包里那张适配表因此**曾经偏低约 13 个百分点**；用户 2026-09-11 裁定 ② 选了修根因，卡 X2 已经落地：`solve.py` 的兜底值换成协议的 `unresolved` 标记 → 参考轴推到 **r1.0.22**、重出 S6 五题 gold、重出四例 oracle、重算适配表。**现在发布的那张表就是改正后的**（`ops/reports/adapt/table.csv`：ALL `resolved_rate` 0.7667、`failed` 7；L1 first_pass 8 / L2 9 / L3 correct_flag 6；记因段见 `ops/reports/adapt/summary.md`）。**主赛道评分器不比 `provenance`**（只有 `scorer/adaptation.py` 引用它），主表数不受影响 |
| 新登记（红队 W.rt 量到） | **公开通道一个 run 都没有** —— `m6_public` 的 18 行清单全是 `pending` | **已闭合（2026-09-11，卡 X1）** | 18 个计划 run **已跑到 8 个**（四道题两臂，结算入库）。原登记：`jobs.jsonl` 18 行 `status=pending`、f02 上没有 `/data/genebench_runner/m6_public` 目录，后果是：`ops/reports/m6_public/v1_0_readiness_public.md` 的 §4 / §4b 渲染不出逐 run 证据（报告自己说了），「外部用户按手册跑得通」这条在**公开通道**上没有实测背书。**不挡外部用户使用**（他们自己跑就有 run）。`RELEASE_MANIFEST.json` 的 `public_channel_zero_runs` 现在 `satisfied=true`；**剩下的 10 个 run 是覆盖面不是有无** —— S4 / S5 / S6 / S7 没跑到，公开切片上那几列因此是空的 |

## 「33 题零 finding」这个完成定义

本卡做完之后重新量了一次，两条通道各一次（受影响的题重跑后合进累积记录）：

| 通道 | 出集题数 | 零 finding | 非零 |
| --- | --- | --- | --- |
| 私有（`snapshots/v1`，网关 18080） | 34 | **34** | 0 |
| 公开（`snapshots/public_v1`，网关 18081） | 34 | **34** | 0 |

累积记录里 40 题中 not-ok 的 6 题，逐题相同、两条通道一致：
`s1-rob-02` / `s2-rob-02` / `s3-rob-02` / `s4-rob-02` / `s5-rob-02` / `s8-rob-02` ——
它们**不在出集里**（被 E9c 拦在落盘之前），所以不计入这个完成定义。

也就是说：完成定义写的是 33 题，实际达成 **34 题**（`s6-rob-02` 进了出集，`s2-eco-01` 的 422 修掉了）。

产物：
`ops/reports/probe_run_oracle.cumulative.json`、`ops/reports/probe_matrix_oracle.md`、
`ops/reports/public/probe_run_oracle.cumulative.json`、`ops/reports/public/probe_matrix_oracle.md`。

---

## 收口核对（阶段五收口，2026-09-07）

> 本节由阶段五收口卡补注，**不改上面任何一条裁定**，只回答一个问题：
> 这张表现在**是不是只剩「设计性限制」与「v1.1 项」两类**？

**答：是。** 16 条逐条复核如下 ——
（**16 条 vs 表上 15 行**：`N-127` 与 `N-128` 每行都同时带「已修的那半」与「留给 v1.1 的那半」，上面的判定汇总把它们各算两条 —— 这不是漏了一行）

| 类别 | 条数 | 逐条 |
|---|---|---|
| 已修（本阶段或此前已关，卡 5.2 核实） | 5 | N-103、N-279、N-127（题面部分）、N-128（题面 + schema 部分）、N-120 |
| 设计性限制（v1 就是这么定义的，写清楚即可） | 5 | N-126（S6 无 TE）、N-119（`missing_masquerading_as_signal` 在本窗口造不出破坏样本）、T-13（网关日志跨机取回未定）、N-105（RD-Agent(Q) 没有 LLM 驱动路径）、六道欠定探针题不落盘 |
| v1.1（要改判据或要新证据，本版不做） | 6 | N-117（S4 的 IC 族没标定 ε 带）、替换基线阶梯未落地（`anchor_ladder_54=false`）、N-129（协议 validator 与评分器判据不同源）、N-130（S7 在 ≤300 次调用里做不完）、~~S8 Slip 符号在两份实现里不一致~~、~~S8 `events` 收紧 `required`~~ —— **划掉的两项已在 `v1.0.14` / `r1.0.21` 做掉**（N-383 / N-384，2026-09-10），本表是 2026-09-07 的历史读数，**条数不追改**；权威条数看上面的「判定汇总」 |

**没有第三类**（「挡外部用户、我们自己搁置不修」的条目）。

### 但有三条「挡着、卡在用户签字」的，收口时单列出来

这三条不是我们搁置的 —— 它们各自要一次**判据变更或题源裁定**，而那要用户点头（契约 D）。
放在这里是为了不让它们藏在票据表里：

| 事项 | 挡什么 / 不挡什么 | 裁定内容 | 绕法（裁定之前） | 票据 |
|---|---|---|---|---|
| ~~**默认预算档 `max_tokens = 600_000`**~~ **已裁定并落地（2026-09-10，N-388）** | **挡结果解读，不挡使用**：`ops/reports/v1demo/` 8 个 run **8/8** 撞的是 token 闸（`ops/api_usage.py` 逐 run 的 deny 列各 1，calls 只用到 18–22 / 100），主表上的 `SR=0.25` / `pass@1=0.25` 读的是「预算够不够」不是能力。`BUDGET_TIERS` 自己的注释把这种失败叫做「最坏的一种失败：**它长得像结论**」 | 把默认档抬到 **6,000,000**（= `BUDGET_TIERS` 注释自己的换算：100 次 × 60k/次；只往上抬，不触 `assert_registry_sane`，不需要重冻、不需要重出集） | ~~矩阵 yaml 里写一行 `max_tokens: 3000000`~~ —— **这条绕法作废**：默认档已是 6,000,000，写 3M 是把预算压低 | **N-388** → 见文末「N-388 / N-383 / N-384 收口」 |
| ~~**适配赛道的题源（红线 B2）**~~ **已裁定并落地（2026-09-10，N-348）** | **挡整条适配赛道**：30 例的 `work/input/broken.json` 内容上就是 **19 道**基准题的 oracle 产物（清单见 `ops/manifests/v1.0-adapt.json::exposed_source_tasks`；「16 道」是 2026-09-07 那一版题源的数，N-348 换过题源之后实测是 19），在裁定之前**一个 bundle 都不许推**，`ops/reports/adapt/` 至今「例 30 / 有 oracle 30 / **有真运行 0**」。**不挡主赛道** | 方向 A：换非基准题的合成产物（改一行常量，管线不动）；方向 B：接受烧掉这 16 道题并把它们从主赛道剔除。**三张卡都倾向 A** | ~~无。守门是刻意的（`push_guard.check_pushable_set` 按集拒）~~ —— 守门已显式解除并记因；30 例各有一次真运行 | **N-348**（另见 N-347 / N-349）→ 见文末「适配赛道的题源已裁定」 |
| **S7 在 ≤300 次调用的预算里做不完** | **挡「S7 这一阶段能不能有真 agent 产物」，不挡整套系统的使用** | 要么放宽调用闸，要么接受 S7 没有真 agent 产物。瓶颈是**回合数**不是上下文（tokens 只用到 5.2–5.6 M） | 无 | **N-130** |

### 完成定义「33 题零 finding」的收口读数

卡 5.2 的量法与结论收口时未复测（重冻之后没有再动过题面与参考轴，两轴 `verify` 均通过）：
私有 **34/34**、公开 **34/34**，两条通道逐题一致 —— 完成定义写的是 33 题，实际达成 **34 题**。


---

## 适配赛道的题源已裁定（N-348，2026-09-10）—— 这条从「挡着」变成「设计性限制」

> 本节由卡 Y2 补写，**不改上面任何一条裁定**。上表「三条挡着、卡在用户签字」里的
> **适配赛道题源（红线 B2）** 那一行，用户已于 2026-09-10 裁定，据此收口。

**裁定**：适配赛道的题源 = **出集规定题的 oracle 产物**（探针题不入），每级 10 例按阶段分层，
破坏方式按级别表，种子固定。守门 `ops/push_guard.py` 里「按集拒 `set_id=v1.0-adapt`」
**显式解除并记因**（记因写在该常量上方，逐条照录裁定原文）。

**后果 —— 用户已知情裁定，这里照实写下，不许省**：

> 这些规定题的 oracle 产物由此进入执行面。
> **跑过适配赛道的被测方，主赛道这些题算「可能已见过答案」。**

* 逐题清单：`ops/manifests/v1.0-adapt.json` 的 `exposed_source_tasks`；
  每一份 `$GB/reference/adaptation/v1.0-adapt/<例>/mutation.json` 也带 `source_task` 与 `_exposure`。
* 六道挂起的欠定探针题、两道已放出的探针题**一道都没有**进适配集（`kind == "underdetermined_probe"` 一律排除）。
* 这条边界跟着**每一张结果表**走：`scorer/report.py::ADAPT_ORACLE_EXPOSURE_NOTE` 进
  `to_latex` 的 caption（主表与适配表都带）与 `table_adaptation` 的 `note` 列（CSV 也带）。
* 同时写进 `ops/specs/fairness_protocol.md` §7 第 10 条与 `ops/specs/adaptation_track.md` §7。

**判定**：**设计性限制**（v1 的适配赛道就是这么定义的），不是「挡着不修」。
它不挡外部用户使用主赛道；它挡的是**同一个被测方**「先适配、后主赛道」这一种读法。

**保留的更窄的门**（解除 ≠ 敞开）：适配 bundle 只许落在 `/data/genebench_runner/adapt/` 下，
且落点必须**显式声明**（`GENEBENCH_PUSH_DEST=…`，没声明 = 拒）。判据：
`ops/push_guard.py::check_pushable_set` + `ops/test_y2.py` + `ops/test_4rt.py`。

---

## N-388 / N-383 / N-384 收口（2026-09-10，卡 W.rt）

> 本节**不改上面任何一条历史裁定的原文**，只把「已经落地」这件事写在读者一定会看到的地方。
> 上面两张表里带删除线的行指向这里。

**N-388（默认预算档）—— 已裁定并落地。** `runner/registry.py::RUN_BUDGET` 现值
`{"max_calls": 100, "max_tokens": 6_000_000}`（`RUN_BUDGET_DEFAULT` 跟着走）。
**旧绕法「真跑时显式给 `--max-tokens 3000000`」今天会把预算压低**（3M < 默认档 6M，
而且显式值**逐键赢过 stage 档位**，S4 的 9M 与 S7 的 18M 会一起被打回去），**已作废**。
文档同步落点：`README.md` §2.4、`docs/OPERATOR_MANUAL.md` §5.3、`ops/joblists/*.yaml`、
`integrations/P2_CONTRACT.md`（卡 W1）＋ `harnesses/README.md` §2.4/§4③、
`integrations/README.md` §1⑤/§1⑥/§3（卡 W.rt 补 —— W1 漏了这两份，红队 W.rt finding 3）。

**N-383（S8 Slip 符号）/ N-127 的判据那一半 —— 已落地。** 以指标规格 §3 为准，
删掉了 `reference/s8_oracle_common.py::fill_metrics` 的 `sign`（买卖同向），
三处实现（规格 §3 / `gateway/sim_engine.py::slippage_bps` / `fill_metrics`）同形；
Slip 纳入 S8 判据，容差 = 一个最小价位（A 股 0.01 元）逐单换成 bps 再量加权。
参考轴推 **r1.0.21**，S8 四题 gold 重出。详见 `ops/reports/s8_schema_tightening_v1_0_14.md` §2。

**N-384（S8 `events.required` 收紧）/ N-128 的收紧那一半 —— 已落地。**
扁平 `required` = `[ts, type, order_id]`（四类事件的交集），逐类必填走 `allOf` + `if/then`，
逐字对着题面正文取。任务集推 **v1.0.14**。**既有真产物不追溯**（旧产物按旧 schema 判）。

**因此上面「判定汇总」里 `已修` 由 5 改成 7、`v1.1` 里那两项作废** ——
2026-09-07 的「收口核对」表是历史读数，**条数不追改**，那里只加了删除线。

**版本轴现值**：`SET_VERSION = 1.0.14`（root `947bf817ae3df348…`）、
`REFERENCE_VERSION = r1.0.21`（root `399fffde62108b52…`）。
两份就绪报告的 §1 已按本次收口重出（红队 W.rt finding 4）。


---

## N-586（⑧）：opencode 的 Qwen 链路缺 `DASHSCOPE_API_KEY` —— 跳过，不阻塞

> 追加：2026-09-11，卡 F2（用户裁定 ⑧「未到位则跳过并记已知限制，不作阻塞」）。
> **本节不改上面任何一条历史裁定的原文。**

**判定：设计性限制 / 等待外部条件** —— 不是「挡着不修」，也不挡外部用户。
今天 13 条已启用配置**全部是 `deepseek-chat`**，opencode 这条也是；主赛道、公开通道、
出集与结算**一条都不依赖 Qwen**。缺的是「再加一个模型做交叉验证」这件 v1.1 的事。

**三件前置里缺哪一件**（判据与实测表在 `harnesses/opencode/README.md` §9.1）：

| # | 前置 | 2026-09-11 卡 F2 复测 |
| --- | --- | --- |
| (a) | f02 上有 `DASHSCOPE_API_KEY` | **仍然没有**。只用退出码判存在（`grep -q`），**没有读、没有打印、没有复制**那个文件（红线 3） |
| (b) | `dashscope.aliyuncs.com` 在出向白名单 | **不在，而且现在就不该在** —— 没有任何 enabled 配置需要它，加进去就是纯粹的敞口（判据 `ops/test_B.py::test_白名单里今天不该有dashscope`） |
| (c) | f02 连得到该域名 | 卡 B 2026-09-11 实测 **通**（`401` / 0.17 s；401 = 到了上游、没带凭据） |

**缺的是 (a)，只缺 (a)。** 按施工契约：**没有伪造 key、没有往白名单加没人用的域名、
没有跑那道真题、没有动 `harnesses/opencode/config.yaml` 的 `model`。**

**key 到位之后怎么做**（完整判据在 `harnesses/opencode/README.md` §9.2 / §9.3，照抄即可）：

1. 判据是**那条 grep 的退出码为 0**，不是 `cat` 那个文件；
2. **新开** `harnesses/opencode-qwen/`，`config.yaml` 写 `enabled: false` → 落进
   `PENDING_CONFIGS`。**不要改 `harnesses/opencode/config.yaml`** —— 它是主表 13 条之一，
   改 `model` 会让 `runner/registry.py::assert_registry_sane` 的「所有 enabled 同一模型」
   当场红，翻成 `enabled: false` 则是从主表拿走一条正在用的配置，两种都不该；
3. `dashscope.aliyuncs.com` 按**共享文件规则**追加进
   `runner/c41/egress_proxy.py::MODEL_API_ALLOW`（flock 内读-改-提交，只追加不重排）——
   **第 2 步之后再做**，否则白名单里会先出现一个没人用的域名；
4. 用显式 config 跑一道 `s2-cor-01` 双臂验链路（`ops/gateway_lock.py` 包住，N-125）。

**「所有 enabled 配置同一模型」那条断言不许放宽** —— 它不是卫生检查，是 v1.0 的实验设计
（*一个模型 × 多种 harness*，主表上的差异才归因到 harness 而不是模型）。放宽要过 M7。

**相关票据**：`N-586`（缺 key，BLOCKED 待用户）、`N-587`（配置该落新目录）、
`N-590`（`upstream_pins.py:230` 的备选措辞待改）。

## F1（2026-09-11）登记的三条

- **`gateway/sim_factory.py` 不在参考冻结清单里，却决定 S8 gold 的运行环境。** 它住在网关侧（不在 `reference/` 下），
  而 `REFERENCE_MODULE_FILES` 的口径是「`reference/` 下的公共层」。后果：改它不会让参考根自己动 ——
  2026-09-11 把 `build_engine` 的 `set_id` 改成必填这一次，是靠 `REFERENCE_REVISIONS` 的 `r1.0.23` 记因钉住的，
  不是靠 hash。v1.1 要么把它收进参考轴，要么把「网关侧影响 gold 的那几个文件」单列一段。
- **`ops/reports/adapt/adapt_report.py::axes_for` 取的是 `freeze_v10` 的当前版本号，不是这批数重算时那一版。**
  2026-09-11 实测踩到：先推号后收库，30 行适配记录被标成在 1.0.16 / r1.0.23 下算出来的，而那一版没重算过适配切片。
  已就地钉回（`axes_source` 写成 `pinned:…`）。根治要按 run 自己的通行证反算。
- **冒烟集 S8 四题的 gold 仍是 v1.0.14 时期的产物。** 「算不出来」的根因（实例与冒烟题同号 → `task_dir` 歧义）
  已在本卡修掉，但重出 gold 要经网关真跑，不在本卡时间盒内。现存 gold 的数值**不受本卡改动影响**
  （会话构造参数一个都没改，改的只是「按哪个出集的 `task.yaml` 构造」由歧义变成显式）。

## F3（2026-09-11）登记的两条

- **baostock 的书面许可正文没有入库，而发布已经放行。** 裁定 ⑨ 把「授权」与「正文」拆成两件事：
  授权已取得（`DATA_LICENSE` 顶部 `granted`，范围记在新增的 §2.0：研究用途 / 允许再分发派生日线数据 / 署名 baostock），
  据此 `data_license_text` 闭合、`releasable` 翻 `true`；**正文仍未到**，`ops/terms/baostock/permission/` 至今不存在，
  §2.1 留着一处醒目占位。**这条限制的实际形状是**：今天对外能拿出的许可证据是「仓库所有者的书面转述」，
  不是「许可方出具、可逐字比对的文件」。两个后果：① 论文数据声明与致谢的**确切措辞**要等正文（§2.2 的四个问题里，
  「转授权」一项至今未核实）；② `ops/test_env.py::test_license_state_matches_whether_the_text_exists`
  把 `granted` 与「目录非空」绑成等价，因此**这道锁现在是红的** —— 见 `ops/tickets_inbox/F3.md`，
  修法只有两条（正文到位，或把锁改成分别判两件事）。**不许**往 `permission/` 里塞占位文件让它变绿。
- **`ops/release/pack_public_provider.py:366` 的 `"text_in_repo": state == "granted"` 是个从不看文件的「文件在不在」字段。**
  与本卡刚从 `ops/mk_release_manifest.py` 里换掉的是同一个假字段，但它写进的是**公开包自己的 `MANIFEST.json`** ——
  也就是外部用户下载后读到的那一份。状态翻 `granted` 之后它会对外宣称「许可正文在库」，而正文并不在。
  改法照抄本卡：现算 `ops/terms/baostock/permission/` 目录，别从状态推
  （`ops/mk_release_manifest.py::official_license_text_in_repo`）。**不在本卡路径内，登记不修。**


## G2（2026-09-12）登记的一条

- **公开仓库带 oracle 源码 —— 训练污染风险（设计性限制，v1.1 以留出集处理）。**
  用户裁定（N-627 走 B，2026-09-11）：公开树**带全部答案面** —— `reference/`（含每道题的
  参考实现 `solve.py`）、`scorer/`、`genetask/templates` 与 `genetask/params`、ε/τ 标定代码，
  以及作为 GitHub Release 附件的 gold 子集。红线 2 随之从「答案面不上执行面」（判机器）
  改写为**容器边界**（判挂载面 + run dir）。
  **为什么这么定**：不带答案面，外部用户跑完算不出分 —— 2026-09-11 实测过剔答案面的那棵树，
  65 个模块 import 断链，结算 / 出表 / 出集 / oracle / 控制组 / 适配赛道六条链路全断，
  对外只剩「把 agent 跑起来拿到 artifact」的那一半。
  **限制的实际形状**（不是「有点风险」这种说法）：
  ① **同期可比性不受影响** —— 所有臂在同一个容器边界下跑，看到的东西完全相同，
  主表上的臂间差异仍然可归因；
  ② **跨期可比性会衰减** —— 题面与参考解在公网上，随时间推移可能进入模型训练语料，
  于是「今年的 80 分」与「去年的 80 分」不再等价。衰减**没有观测量**：
  我们无法从外部判断某个模型有没有见过本仓库；
  ③ **canary 的角色变了** —— 它从「记忆污染检测」降级为「同期一致性检查」。
  `reference/memory_probe_answers/`（探针钥匙）**仍不公开**，它是唯一没被这条限制波及的判别力来源。
  **v1.1 的处理**：留出集（held-out split）—— 一批不公开题面、不公开 gold 的题，
  只有它能支持跨期结论；公开集降为「可复现性与同期比较」用途。
  **不在 v1 修**：留出集要重走一遍出集 / 冻结 / 标定，是一个版本的工作量，不是一张卡。
  相关：README 首屏「答案就在这个包里」横幅、README §4 ①、`ops/specs/fairness_protocol.md`
  附录、`ops/HANDOFF.md` 末段、`runner/f02/answer_plane_guard.py --mode container`。


## G1（2026-09-12）登记的两条

- **`fetch_clock` 探针的网关日志切片，在同一道题被重跑过之后取错窗口。**
  本卡把公开通道的 18 个 run 重跑了一遍之后复跑三控，`s1-cor-01` 的 **oracle 桩**
  第一次判红：`fetch_clock` 族 601 条 `fetch_clock_mismatch`，理由是
  「`fetched_at` 不等于任何一条 `/universe` 网关日志的 ts —— 不采信外部时间戳」。
  **实测证明那条日志在**：`$GB/logs/gateway_access_public.jsonl` 里
  `ts=2026-09-07T15:41:43.048+00:00` / `path=/universe` / `task_id=s1-cor-01` /
  `decision=allow` 一条不差（oracle 桩申报的头四条 `fetched_at` 逐条都能在日志里找到）。
  也就是说**不是日志缺了**，是探针取日志的那个切片在这道题今天多出 18 个 run 之后落错了窗口。
  连带后果：破坏样本里 `s1-cor-01` 的三条（`fetch_clock` / `source_status` / `lookahead`）
  全判成「基线不干净 —— 破坏实验无意义」，破坏样本达成数从 18/19 掉到 **15/19**。
  **影响面**：三控与破坏样本这两份**验收报告**里 `s1-cor-01` 那几行；
  **不影响** 18 个真 run 的结算（它们各自按自己的 run 切片判，`records.json` 里
  `fetch_clock` 一条都没响）。
  **按「最后一卡：本卡之外的问题登记不修」的裁定不动**；探针切片在 `scorer/` 下，不在本卡路径内。
  v1.1 修法方向：切片键要带 run 身份（run_id / 时间窗），不能只按 `task_id` 取「最近一段」。

- **`m6_public` 的 `jobs.jsonl` 比裁定 ⑮（机器标识进 `run_id`）旧，18 行的 `job_id` 都不带
  `@<机器标识>` 后缀。** 于是每一条真跑都打一句
  「[黄] run_id ≠ job_id：两边不同源了，多半是 exec 树没同步」——
  **这句提示在这批上是误导**：exec 树是本卡刚推的，两边同源，差的是**清单陈旧**。
  结算按 `run_id` 走，18 行读数正确；只有那句黄字是噪音。
  同一根因还让 `ops/test_wrt.py::test_rebudget只动没跑过的行` 恒红
  （断言用不带后缀的键，而 `rebudget` 返回的键带后缀）—— 本卡改动之前单跑它也红，已实测。
  **不修**：重生成清单会把 18 行全部退回 `pending`，对一批已跑完的读数代价大于收益。



## 最终卡（2026-09-12）红队最终轮：修了什么、登记什么

> 这一节的口径与全表一致：**挡外部用户的修，不挡的登记**。
> 四条 block 与两条 major 已修（见下「已修」四条的证据路径）；三条 minor 登记不修。

### 已修（留证据链，不用管）

- **【已修】公开通道的结算读的是私有通道的标定、网关日志与题集根。**
  `scorer/l3.load_calibration()` 在 `path=None` 时写死 `snapshots/v1/calibration.json`，
  `ops/score_runs.py` 的 `--gateway-log` 与 `--ref-tasks` 两个默认值同样写死私有路径。
  三处都不认 `GENEBENCH_CHANNEL`，而 `genebench_config.calibration_path()` /
  `gateway_access_log()` 与 `ops/run_controls.py` 的 `PUBLIC_ANSWER_ROOT` 早就是按通道取的。
  **实测后果**：① 公开通道的 τ/ε 取自私有标定（私有 τ=0.9840059556217291，
  公开 τ=0.9839810664562939，不相等）；② 在只有公开数据的外部单机上（手册形态①）
  18 个 run 里 5 个直接 `FileNotFoundError` **静默掉出这一批**；
  ③ 用私有网关日志结算时 `overreach` 整片 `None`、gate 判定整片改变；
  ④ 用私有 gold 结算时 `s2-cor-01` 的 `CellAgree` 由 0.9466 变成 0.2491 而 SR / pass@1 恰好没翻
  ——**聚合数看不出来**，这是最该拦在入口的那一类错。
  **修法**：三处默认值改成通道感知；`ops/score_runs.py` 把标定显式读出来传进 `score_run`
  并把「通道 / 标定 / 网关日志 / 题集根」四行打进 `summary.md`；加一道与 `ops/run_controls.py`
  同样的混通道拦截。**重结算的结果**：`m6_public` 的主表与 Table A **逐字节相同**
  （`l3_pass` / SR / pass@1 一个都没翻），变的是 3 条记录的 4 个诊断值
  （s5 两臂的 `tau`、s4-cor-01.open 与 s7-cor-01.open 的 `max_band_ratio`）；
  旧的 18 行在结果库里已标 `superseded`，新的 18 行记 `p1.0.0 / r1.0.23`。
  证据：`ops/reports/m6_public/summary.md`、`ops/test_rtfinal.py`。

- **【已修】21 个批里 20 个的主表表头还是旧的 `Align`。**
  裁定 ⑥-c（S2 保真列 Align→CellAgree，表头 `Cell%`）落地时只重出了 `m6_public` 一个批，
  于是同一份发布物里两张「固定十九列」的表表头不同，而 `ops/reports/report_spec_v1.md` §6
  明写这两列量的是不同的东西（`Align` 量申报、`Cell%` 量内容）。**已按各批自己
  `table_main.axes.json` 里记的筛选条件全部重出**（另补一条 `superseded=None`——
  出表本来就不该取已作废的行），21 张表头现在逐字相同，各批的 LaTeX `\label` 仍互异。

- **【已修】要发的这一版没有签字包。** `ops/reports/signed/` 里最新的是 `v1.0.15_r1.0.22/`，
  而那个包里的 `m6_public__*` 几件是 N-611 作废的污染读数（跑在私有 provider 上，
  `n_tasks=4 n_runs=4 SR=0.25`），它的 `README.md` 却写着「要引用签过字的那份就引用这里」。
  **已重出 `ops/reports/signed/v1.0.16_r1.0.23/`（49 件）**；旧包保留，并在包内加了
  `SUPERSEDED_NOTE.md` 写明哪几件作废、现行的在哪。

- **【已修】VERSIONS.md 与发布清单互相矛盾，且缺公开轴。**
  权威文档停在 1.0.15 / r1.0.22，同一棵树里的 `RELEASE_MANIFEST.json` 写 1.0.16 / r1.0.23；
  按裁定 ① 公开通道有自己的 `SET_VERSION_PUBLIC`（p1.0.0 / 根 `3e5ab441a991c411…`），
  而 VERSIONS.md 里一行都没有。**已重出轴表与 §4 历史表、新增 §1.1a 公开通道任务集轴一节**；
  `RELEASE_MANIFEST.json` 的 `axes` 段加 `public_set_version` / `public_set_root`；
  发布清单已重出（`--check` 退 0，`releasable=true`）。

- **【已修】版本锁自检只锁一条轴。** 不带开关跑 `ops/freeze_v10.py` 只比
  `ops/manifests/v1.0-smoke.json`；公开轴与参考面轴在这个 CLI 里没有任何漂移检查路径
  （`--write-public` / `--write-reference` 只写不比）。**已补 `--check-all`**（三条轴各重建、
  比根、逐段报差异，任一条漂就非零退出），手册形态① 的「版本锁自检」那一步改成调用它，
  无开关那条分支的成功文案现在自己说明「只核了私有任务集轴」。

### 登记不修（minor）

- **【设计性限制 / 登记】`report_spec_v1.md` 没写明 `—` 与 `unobservable` 谁压谁。**
  §1 col.19 说 `Ovr` 在「日志不可得 → `unobservable`（不是 0）」；§0.3 的短路说
  「这一格的 run 全部落在四类里 → `—`」。`m6_public` 的 S8 两个 run 同时满足两条，
  实现按 §0.3 写了 `—`。**实现的选择是对的**（`—` 比 `unobservable` 多告诉读者一件事：
  先回答「这一格为什么没有 run 可用」，再回答「这个量能不能测」），
  但**文档没说谁压谁** —— 照字面独立复算主表的人会在这三个格子上得出不同结果
  （`Ovr` strict、ε-agr strict、以及 S8 那一格，同一条根因）。
  **不修的理由**：改的是规格文本的措辞，而 `report_spec_v1.md` 是发布件，
  改它要连带重出签字包与发布清单；本卡之外不再开新票（最终卡裁定）。
  **v1.1 修法**：§0.2 表下加一句优先级，并在 §1 col.5/col.17/col.19 三处
  「不可得时 → unobservable」后面补「（除非这一格的 run 全部落在四类里）」。

- **【v1.1 / 登记】两条通道的 provider 钉子长度不对称。**
  `runner/inject.py` 的 `PUBLIC_PROVIDER_SHA256_ROOT` 是 16 位十六进制
  （`561348660a3175b1`），`pin.PROVIDER_SHA256_ROOT` 只有 8 位（`54fdda39`），
  而 `check_work_provider` 用 `got.startswith(want)` 比 —— 于是**私有通道那道门实际只比 32 bit，
  公开通道比 64 bit**。红队两次攻击实测**门都按预期响了**（公开通道装私有 provider →
  P7e 红并正确指出「装进去的是 private 通道的那一份」），所以这不是当下的洞，
  是两条通道的门强度不对称。**v1.1 修法**：把 private 的钉子补齐到 16 位，
  并在 `ops/test_provider_pin_channel.py` 里断言两条通道的钉子长度相同且 ≥16。

- **【已处理 / 登记】`ops/reports/m6_public/scores/` 里混着两批跨轴读数。**
  N-611 把受污染的 **run 目录**移走了，但没有移走它们的 `score.json`：
  该目录一度是 18 份现行（带 `@finance01-e3887dfa`）+ 8 份已作废（`set_version=1.0.15`）。
  结果库里那 8 行已标 `superseded`，**已发布的表没有被污染**；风险在下一个人 ——
  任何 `glob("scores/*.score.json")` 的生成器会拿到 26 条跨轴记录。
  **已按「留证据、不删」挪进 `ops/reports/m6_public/scores_superseded_20260912/`**
  （同目录留 `README.md` 说明），与 run 目录同样的处置。

- **【文档 / 登记】手册「照抄的命令」里 `ops/mk_tables.py --table main|a|b|adaptation` 照抄会 exit 2。**
  该脚本的 `--out` 是必填，而那一行没写 `--out`。照抄的人会得到一个 argparse 用法错误
  （不是静默错误，代价有限）。**不修**：它在编排方的命令清单里，不在本卡路径；
  v1.1 修法是给 `--out` 一个默认值（`ops/reports/<batch>`）或在手册那一行补上 `--out`。

## H（2026-09-12）登记的三条

阶段收口的全量 pytest：**4400 passed / 6 failed / 32 skipped / 1 xfailed，1268 s**
（`$GB/scratch/H/full.log`）。六条红**一条都不是本卡改动引起的**，逐条归属如下；
按「最后一卡：本卡之外发现的一切问题登记不修」的裁定，这里如实记，不修、不开新票。

- **【外部数据漂移 / 登记】`ops/test_lake_baseline.py` 三条红：湖里 `stock_st` 新近停更。**
  `test_stalled_tables_match_live_recompute` / `test_the_measured_stalled_tables_are_still_these_eight` /
  `test_freeze_line_green_does_not_imply_alive` 三条同一根因 —— 湖侧基准取于 2026-09-11，
  当时停更表是 8 张；现场复算是 9 张，多出来的是 `stock_st`。
  **这是宿主上别人的 ETL 的事实变化，不是 GeneBench 的回归**：我们的题面与 gold 早就冻在
  `snapshots/` 里，不读活表。修法是重跑 `ops/build_lake_baseline.py` 并回头改
  `ops/specs/v1_tables.py` 里那条 ⛔ 备注与卡 1.3 的新鲜度假设 —— 那要先确认
  `stock_st` 是真停了还是上游断了一天，**需要湖的拥有者判断，不由发布卡替他判**。

- **【别人的 scratch / 登记】`ops/test_env.py::test_no_api_key_material_in_run_dirs` 报 6 条。**
  6 条全部落在 `$GB/scratch/Y1/rh2_operator/ops/test_env.py:850,857` 与
  `$GB/scratch/Y1/rh2_stage/pkg/ops/test_env.py:850,857` —— 那是**把仓库整棵拷进 scratch**
  带过去的、**测试文件自身的夹具字面量**，不是真凭据（仓库里同一行同一形状，扫描器豁免的是
  `ops/` 下的原件、不豁免 scratch 下的副本）。**一条都不在 `scratch/H` 下。**
  卡 F2（2026-09-11）已点过同一件事，这一轮仍在。**不修**：那是别的代理的现场，
  删掉等于替他销毁证据。修法只有一句：清掉那两个拷贝目录，或给扫描器加一条
  「scratch 下与仓库同路径同内容的副本视同原件」的豁免。

- **【别人未提交的改动 / 登记】`ops/test_underdetermination_guard.py::
  test_unattributed_residual_is_documented_in_all_three_places` 红。**
  它要求「未归因残差 22.69%」这个量在三处都写着；第三处
  `ops/reports/ambiguity_impact_2.2b.md` **此刻在工作树里是别人未提交的改动**
  （`git status` 里带 ` M`），新正文写的是毛收益差 10.8% / 换手差 5.8%，没有 22.69%。
  **不是本卡改的，也不该由本卡改**：那份报告与 `ops/specs/operator_semantics_conflicts.md`
  是同一个人手上的半成品（契约 C：工作树里有别人的未提交改动时不要动它们）。
  提交它的人负责让三处的量重新对上，或把那条判据改成读新正文里的量。

- **【本卡的设计取舍 / 登记】私有签字包的目录名看不出通道。**
  卡 H 把签字包按通道出成两份：私有 `ops/reports/signed/v1.0.16_r1.0.23/`、
  公开 `ops/reports/signed/public_vp1.0.0_r1.0.23/`。公开那份一眼看得出通道，
  **私有那份看不出** —— 它沿用历史体例 `v<任务集>_<参考面>`，因为
  `ops/test_wrapup.py:47` / `ops/test_V2.py:60` / `ops/test_V2rt.py:281` 三处都按这个式子
  **现算**路径，加前缀等于把三份测试一起改红，而它们问的「当前轴上有没有签过字的包」
  不该因为改了命名体例就没了答案。折中：通道写进 `MANIFEST.json` 的 `channel` 字段、
  包内 `README.md` 第一屏，两份包的 `counterpart` 字段与 README 正文互指得到。
  **v1.1 修法**：三处测试改成从 `ops/archive_signoff.dir_name_for("private", …)` 取路径，
  之后私有那份就可以改叫 `private_v1.0.16_r1.0.23`。

## P（2026-09-12）登记的四条 —— 都挡在**用户那一侧**，本轮不修

> 这四条是推送与 Release 附件那张卡（卡 P）在做推前扫描时量到的。
> 按「最后一卡：本卡之外发现的一切问题登记不修」的裁定，**如实记，不修、不开新票**。

- **【BLOCKED 待用户 / 登记】公开 provider 包里 `instruments/` 的再分发依据未确认 —— 挡住裁定 ⑭。**
  包里 `qlib_provider/instruments/{all,csi300,csi500,csi1000}.txt`（389 KB，「谁在哪个指数里、从哪天到哪天」）
  与 `universe/`（v1 三宇宙并集 3,575 行）来自**私有** `universe_pit`（湖 `index_member_all` / `index_weight`
  派生，上游 **tushare**），不是 baostock 的产物 —— baostock 没有指数成分历史（同一件事在本表
  「W2 量到」那一条上已经记过一半：csi1000 无法用公开源重建）。
  **两处预先写死了这件事，不是卡 P 的判断**：包自己的 `MANIFEST.universe_definition_note`，
  与本仓库 `DATA_LICENSE` **§5**（「它的再分发**不在 baostock 许可的射程内** —— §2 的授权
  **不覆盖这一块**，**正文到位之后也不会**覆盖 […] **发布前须单独确认**」）。
  用户裁定 ⑨ 给的授权摘要是「研究用途、允许再分发**派生日线数据**、署名 baostock」——
  指数成分历史不在射程内；⑨ 闭的是 `data_license_text` 那条 blocker（baostock 侧），
  `DATA_LICENSE` §0 速览表把 `instruments` 这条**单列**为「另一处未确认的再分发依据」。
  **两条出路**：① 取得上游（tushare 侧）对这份派生名单的再分发许可 → 原样发包；
  ② 不发 `instruments/`，改发重建脚本让用户自备宇宙定义 → 代价是形态 A 的包不再自足，
  公开通道的 csi300 / csi500 / csi1000 三个宇宙用户复现不出来，只剩 `all`
  ——**而 gold 子集正是按这三个宇宙算的**（csi300 37 条 / csi500 4 条），
  发了 gold 子集却不发 `instruments/`，用户拿到分也对不上宇宙。
  **守门**：`ops/test_p.py` 三条钉着这件事（§2.0 授权摘要里不许出现「指数成分 / instruments / 宇宙定义」、
  §2.1 的显式占位不许被删、`ops/terms/baostock/permission/` 必须仍为空）——
  想靠改文案把它弄成「已闭」会当场红。票据 **N-690**。
  > **2026-09-12 更新（卡 A，用户裁定 ①）：这条已经关掉了，走的是上面没列的第三条路**—— **不是**取得 tushare 许可，也**不是**只发脚本，而是**把宇宙定义面整个换成 baostock 自己的
  > 成分接口重建结果**（`query_hs300_stocks` / `query_zz500_stocks`）。代价是 `csi1000` 出包
  > （baostock 没有那个接口）。`DATA_LICENSE` §5 已改写，`ops/test_p.py` 那条守门换了判据
  > （钉新口径，并额外钉「旧判断的原话不许还留在文件里」）。见`ops/reports/public/instruments_switch.md`。
  > **上面这一整段保留原样**，因为它记的是「当时为什么挡着」——把它删掉，后来的人就查不到这条路是怎么走通的。

- **【未做 / 登记】公开 provider 包没有可发布的版本。**
  盘上只有 `release/_staging_unpublished/public_v1/genebench_public_provider_v1.tar.gz`
  （782,040,927 B，sha256 `c42c33eee55844d7bb88ed1e8c995db65fc6e144a3aa6f53369c55aa4be3c476`，
  2026-09-06 打的，`code_head e642468` 远落后于现在的 HEAD，自己标着
  `license.publishable=false` / `published=false`）。`DATA_LICENSE` §2.1 写明 `granted` 之后
  落点应是 `release/public_v1/` —— **那个目录不存在**，即
  `ops/release/pack_public_provider.py` 在许可翻 `granted` 之后**一次都没重跑**。
  许可定了之后**先重跑它**再谈传附件；**重打之前先看本表 F3 那条**
  （包内 `MANIFEST.json` 的 `text_in_repo` 会对外宣称「许可正文在库」，而正文并不在）。
  票据 **N-691**。

- **【未做 / 登记】gold 子集包从来没打过，也没有打包脚本。**
  裁定 ⑭ 要传「gold 子集 152 MiB」，而盘上只有清单
  `ops/reports/i_rehearsal_v2/gold_subset.json`（公开通道 41 件，清单指纹 `6e9696f0…`）
  与数据卡 `ops/data_cards/gold_subset_v1.md` —— **没有 tar/zip，也没有打它的脚本**。
  要新写一个：按清单逐件取 `snapshots/public_v1/gold_factors/<rel>`，逐件核 sha256 后打包，
  包内带清单与校验脚本（照 `ops/release/pack_public_provider.py` 的体例）。票据 **N-692**。

- **【陈值 / 登记】`ops/reports/push_instructions.md` 通篇是陈的，而它是发布件。**
  它在 `RELEASE_ITEMS` 里、两份签字包都收，而三处与现状不符：
  ① §0② 说「两棵树里**没有**答案面」—— 按裁定 ④ 现在**有意带全部答案面**；
  ② §0③ 说 `DATA_LICENSE` 仍是 `pending_license_text`、`releasable=false` —— 现在是 `granted` / `true`；
  ③ §0③ 说 `LICENSE` 版权行是 `Copyright <待用户填>` —— 裁定 ⑩ 已定为 `Copyright 2026 Decilix Intelligence`。
  **不修的理由**：它不在卡 P 的路径内，而最终卡的裁定是「本卡之外发现的一切问题登记不修」。
  改完**必须**重跑 `$PY ops/mk_release_manifest.py`（不带 `--check`），否则手写件 sha 当场对不上。
  票据 **N-693**。另有两条**要用户点头才能动**的边界判定（属「删除 / 改写」而非「追加」）：
  `ops/HANDOFF.md:1457` 那条提内部 `Co-Authored-By` trailer 的票据（倾向删，**N-694**）、
  `ops/specs/card_3.2_smoke40.md:127,132` 两处本地 Mac scratchpad 绝对路径（倾向改成相对描述，**N-695**）。

## 最终卡收口（2026-09-12）：这张表的终态盘点

> 用户裁定：**本轮之外发现的一切问题，全部登记在这张表里 —— 不修、不开新票。**
> 这一节是那句裁定的收口核对：逐类点一遍数，并说明哪几类是「不该由发布卡替别人判」的。

### 逐类计数（截至 2026-09-12 收口）

| 类别 | 条数 | 说明 |
| --- | --- | --- |
| **已修 / 已闭**（留证据链） | **12** | 主表 `## 逐条` 7 条 + 红队最终轮 5 条（通道感知结算 / 21 个批的表头 / 签字包 / VERSIONS.md / 版本锁 `--check-all`） |
| **设计性限制**（v1 就是这么定义的） | **8** | 主表 6 条 + G2 的 oracle 源码公开 1 条 + H 的私有签字包目录名 1 条 |
| **v1.1**（要改判据或要新证据） | **5** | 主表 5 条（S4 IC 族无 ε 带 / 替换基线阶梯 / N-129 / N-130 / 滑点符号 CONFLICT 已另记） |
| **登记不修 · 本轮量到** | **18** | F1 3 + F3 2 + G1 2 + 红队最终轮 minor 4 + H 3（不含 H 那条设计取舍）+ P 4 |
| **BLOCKED · 待用户** | **4** | baostock 许可正文（F3）、`instruments/` 再分发依据（P）、推送本身（票据 N-635）、`CITATION.cff` 的 `authors` |
| 合计 | **47** | 三处专节另见下方说明 |

上表之外，本文另有三处**专节**已在文中展开，不重复计入：适配赛道题源的裁定（2026-09-10）、
红队 W.rt 那一轮的三条收口、以及 Qwen 链路缺 key 那一条（裁定 ⑧）。

> 表头那张「判定汇总」（已修 7 / 设计性 6 / v1.1 6）是**卡 5.2 那一天**的快照，
> 按本仓库「正文留历史、现值另记」的既有写法**不改它** —— 现值以本节这张表为准。

### 有四类红**不该由发布卡替别人判**（全量 pytest 里剩下的那几条）

本轮**阶段收口的全量 pytest**（`flock pytest.lock` + `systemd-run MemoryMax=6G`）：
收口改动之前 **4428 passed / 6 failed / 32 skipped / 1 xfailed，1267.89 s**
（`$GB/scratch/FINAL/full.log`）；本卡提交之后复跑一次，**终值 4443 passed / 6 failed /
32 skipped / 1 xfailed，1205.64 s**（`$GB/scratch/FINAL/full2.log`，多出的 15 条 passed
是本卡新增的 `ops/test_final.py`）。**两次的红是同一批六条。** 逐条归属如下 ——
**一条都不是本轮改动引起的**，四类都属「不该由发布卡替别人判」：


1. **`ops/test_lake_baseline.py`**（3 条）—— 湖里 `stock_st` 新近停更（基准 8 张 → 现场 9 张）。
   宿主上**别人的 ETL** 的事实变化，不是 GeneBench 的回归（题面与 gold 冻在 `snapshots/` 里，不读活表）。
   修法要先确认是真停了还是上游断了一天，**需要湖的拥有者判断**。
2. **`ops/test_env.py::test_no_api_key_material_in_run_dirs`**（1 条）—— 命中全在
   `$GB/scratch/Y1/rh2_operator/` 与 `rh2_stage/` 下，是把仓库整棵拷进 scratch 带过去的
   **测试文件自身的夹具字面量**，不是真凭据。**不修**：那是别的代理的现场，删掉等于替他销毁证据。
3. **`ops/test_underdetermination_guard.py`**（1 条） —— 它要的「22.69%」第三处出处
   `ops/reports/ambiguity_impact_2.2b.md` **此刻是别人未提交的改动**（契约 C：不动别人的半成品）。
   提交它的人负责让三处的量重新对上。
4. **`ops/test_wrt.py::test_rebudget只动没跑过的行`**（1 条） —— `job_id` 缺 `@<机器标识>` 后缀，
   卡 G1 已登记（票据 N-619 / N-669），本轮改动之前单跑也红。

**本轮 `ops/test_gateway.py` 与 `ops/test_universe_reconcile.py` 一条都没红** ——
任务书口径里它们属「外部进程持湖写锁或网关端口」那一类，这一次恰好没撞上，如实记。

### 本轮**没有**登记进这张表的是什么

只有一类：**本轮修掉的东西**（四条 block + 三条 major + 九处状态锁 + N-611 与 18 个公开 run）——
它们有各自的证据路径与票据号，写在 `ops/reports/final_report.md` §二与 `ops/tickets.md`
「最终卡（收口 + 发布）」一节，不重复占这张表的篇幅。
**没有任何一条本轮发现的问题是「既没修、也没登记」的。**


## A（2026-09-12）换宇宙定义面之后登记的三条

> 用户裁定 ①：公开包的 `instruments/` 与 `universe/` 全部改用 baostock 成分接口重建，
> `csi1000` 不入公开包。换面记录与逐项证据见
> [`ops/reports/public/instruments_switch.md`](public/instruments_switch.md)。

- **【设计性限制 / 登记】公开包没有 `csi1000`，公开通道只剩 csi300 / csi500 / all 三个宇宙。**
  baostock 0.9.3 的成分接口只有 `query_hs300_stocks` / `query_zz500_stocks` /
  `query_sz50_stocks` —— **没有中证 1000**（W2 §4，`ops/test_W2.py::test_baostock_has_no_csi1000_constituent_api`
  把这件事钉在代码里，哪天上游加了那个接口，那条测试会红）。后果：
  ① **拿公开包复现不出任何以 `csi1000` 为宇宙的读数**；
  ② 仓库里 `snapshots/public_v1/gold_factors/csi1000`（8.3 GiB / 8.9 GB，792 件）与私有通道的
  csi1000 产物**都不随包发布**。**用户 2026-09-13 裁定 ③：保留在 f01，不入包，也不删** ——
  它算在旧的 tushare 派生名单上。卡 R2 复核过打包脚本确实没收它：
  `ops/release/pack_gold_subset.py` 的源根是 `gold_factors_r2/`（常量 `SUBSET_ROOT_NAME`），
  那个根下**只有 csi300 / csi500**；两个已发布附件的逐件校验和里 `csi1000` **命中 0 行**
  （`gold_subset_SHA256SUMS` 46 行 0 命中、provider `SHA256SUMS` 28,656 行 0 命中）。
  也写进了 `ops/data_cards/gold_subset_v1.md`；
  ③ 公开 gold 子集的 41 件本来就只有 csi300（37 件）与 csi500（4 件），**不受影响**。
  **不修的理由**：修它要么要一个 baostock 没有的接口，要么要把 tushare 派生名单发出去 ——
  后者正是这次换面要去掉的东西。

- **【已发布读数与现包不同源 / 登记，不重跑】18 个公开 run 跑在旧 provider 上。**
  `$GB/runs_in/m6_public/` 的 18 个 run（`inject.json` 记的根 `561348660a3175b1…`，
  f02 上是 `qlib_provider_56134866/`）**全部用 `csi300` 宇宙**（逐个核过）。
  换面之后，同一个宇宙在 gold 窗（2015-05-29…2026-07-31，2,716 天）里
  **358 天的逐日成员不同、12,195 个「日×成员」格不同**，而**成员集合本身一只不差**
  （csi300 的码集 0/0）。差的是进出场日期：私有那份把调整吸附到月末，baostock 给实际生效日，
  中位差 −15 天（W2 §3.2）。
  **不重跑的理由**：用户裁定 ⑥「其余一切问题维持登记不修」+ 裁定 ①「agent run 不重跑」。
  **复现这 18 个读数需要旧 provider** —— 它在 f02 上**保留着**（`qlib_provider_56134866/`，本卡没删）。

- **【重算了但阈值没跟着重算 / 登记】公开 gold 换了一版（`gold_factors_r2/`），而 τ / ε / 互检仍算在旧 gold 上。**
  换成分之后公开 gold 子集那 **41 件逐件都变了**（`sha256` 41/41 不同），已按新成分全量重算，
  落 `$SNAPSHOTS/public_v1/gold_factors_r2/{csi300,csi500}`（各 792 件，`rc=0`）；
  **打 gold 子集包要从这里取**。逐件比对与完全归因见
  [`instruments_switch.md` §5](public/instruments_switch.md)：
  行集差 +286,750 / −279,880 格；共有的 33,527,179 格里 **4,511,718 格（13.5%）数值也变了**，
  **100% 落在「成分区段本身变了」的票上，落在区段没动的票上的是 0 格**
  （`qlib_expression` 那 23 件一格没变；变的全在带截面算子的 `qlib_panel_loader`
  与按区段截断面板的 `qlib_kunquant_loader` 两条路上）。
  **没跟着重算的**：`calibration.json`（τ / ε / IC 族）、`crosscheck/`、`epsilon/`
  —— 它们仍然建在**旧** `gold_factors/` 上。后果：随包发出去的**分**（gold 子集）算在新名单上，
  而随包发出去的**阈值**算在旧名单上，两者**不同源**。
  **不修的理由**：重算阈值要连带重跑 IC-ε 与互检全量（`heavy.lock` 上数小时），
  超出本卡范围，且用户裁定 ⑥「其余一切问题维持登记不修」。
  **影响面有界**：τ / ε 是**判定阈值**，§5 的归因说明成分变化只动「算哪些格」与截面排名，
  不动求值口径；要用它做跨版本比较的人，先读这一条。

- **【归档陈值 / 登记，不改归档】两份签字包里记的是旧的 provider 根。**
  `ops/reports/signed/v1.0.16_r1.0.23/` 与 `ops/reports/signed/public_vp1.0.0_r1.0.23/`
  里凡是提到公开 provider 根的件，记的都是 `561348660a3175b1…`；现在包里的根是
  **`f7dda2899071b07a…`**。**签字包是只读归档，本卡一个字节都没改** ——
  归档记的就是签字那一刻的事实，改它等于把"当时签的是什么"抹掉。
  要知道"现在是什么"，看 `ops/data_cards/public_channel.md`、
  `ops/reports/public/release_forms.md` 与 `runner/inject.py` 的公开钉子，三处都已跟改。
- **【已闭 · 2026-09-13 卡 R2 已删】~~`$GB/release/_staging_unpublished/public_v1/` 里还留着 2026-09-06 那一版包。~~**
  **用户 2026-09-13 裁定：删。** 卡 R2 删前现算了一次 sha256 核对身份
  （`c42c33eee55844d7…`，782,040,927 B，`code_head e6424687…`，与 `final_report.md` 记的一致），
  存根留在 `$GB/scratch/R2/deleted_staging_pkg.txt`；删后 `$GB/release/` 下只剩 `public_v1/` 与 `trees/`。
  删前 `grep` 过全仓库：引用这个路径的**全是叙述性文档**（`HANDOFF.md` §566、本表、
  `final_report.md`、`release_forms.md`、`publish_report.md`、`ops/tickets.md`、几份签字归档），
  **没有任何测试、清单或脚本把它当落点**（`ops/release/pack_public_provider.py` 只在
  `license.state != granted` 时才会往 `_staging_unpublished/` 写，而状态已经是 `granted`）。
  签字归档按「只读」不动；`HANDOFF.md` §566 那一行不在卡 R2 的路径内，已写进
  `ops/tickets_inbox/R2.md` 交给下一张有该路径的卡。原文留档如下：（N-714）

  > **【原登记，2026-09-12】**`$GB/release/_staging_unpublished/public_v1/` 里还留着 2026-09-06 那一版包。
  许可翻成 `granted` 之后，可发布的包落 `$GB/release/public_v1/`（2026-09-12 重打，
  见 [`release_forms.md` §7](public/release_forms.md)）。staging 里那个 782,040,927 B 的 tar.gz 是
  **换面之前**的 provider（`instruments/` 还是 tushare 派生的那版，根 `561348660a3175b1…`），
  既不会被发布、也不再与任何在册的根对应。**留着的唯一风险是有人下错** ——
  删是不可逆的动作、且不挡发布验收，交给仓库所有者决定。
- **【包里的清单有两处旧数 / 登记】`RELEASE_MANIFEST.package` 那一段算在换面**之前**的数上。**
  `package.totals_bytes` / `package.parts` 读的是 `ops/reports/i_rehearsal_v2/package_inventory.json`
  （09-06 那次演练的数），`package.gold.channels.public.list_sha256` 读的是
  `ops/reports/i_rehearsal_v2/gold_subset.json`（那 41 行的 `sha256` **41/41 已经不成立**，卡 A 已证）。
  本卡新增的 **`release_attachments`** 段记的是**现值**：两个附件逐件 `name` / `bytes` / `sha256` /
  `built_at` / `code_head` / 四条版本轴，且 `ops/test_pack_release.py::test_清单里记的sha就是盘上那个包的sha`
  拿盘上的包现算比对。**两段并存时以 `release_attachments` 为准。**
  不修那两份演练产物的理由：它们不在本卡路径内，且裁定 ⑥「其余一切问题维持登记不修」。

## D（2026-09-12）：Release 的两个附件还没挂上去

**分类：待裁定（等一把带 `Contents: Read and write` 的 token）。不挡 (b) 自己建数据面，挡 (a) 拿现成的包。**

两个附件已经打定、逐件验过、六项上传前扫描全零（`ops/reports/release_scan_publish.md`），
但 GitHub Release **没有建成**：`POST /repos/Decilix-Intelligence/GeneBench/releases` 回
`403 Resource not accessible by personal access token`，响应头点名
`x-accepted-github-permissions: contents=write`。手上这把是 fine-grained PAT，
仓库权限只给了读；账号本身是 repo admin，机器上没有第二把凭据。
诊断与补法在 `ops/reports/push_result.md` §2，README §2.1a 里也如实写着「地址现在会 404」。
**它不是 `RELEASE_MANIFEST.json` 的第六条 blocker** —— 清单判的是「够不够格发」，
这件事是「发的动作差一步凭据」。

## D（2026-09-12）：已发布的 18 个公开 run 跑在**换面之前**的 provider 上

卡 A 把公开包的宇宙定义面换成 baostock 重建结果之后，公开 provider 的根从
`561348660a3175b1…` 变成 `f7dda2899071b07a…`。**那 18 个 run 不重跑**（裁定 ⑥），
于是随包发出去的东西里有两种口径并存：

| | 算在哪版名单上 |
| --- | --- |
| gold 子集（41 件，随 Release 发） | **换面之后**（新根 `f7dda289…`） |
| `calibration.json` / τ / ε / IC 族 / `crosscheck/` | **换面之前**（旧根 `56134866…`） |
| 已发布的 18 个公开 run 的读数 | **换面之前** |

delta 的量级（卡 W2 对账）：**csi300 成员一只不差**，只有进出场日期差
（4,269 个交易日里 3,572 天逐日完全相同）；**csi500 只在公开 2 只、只在私有 32 只**。
所以「分」算在新名单、「阈值」算在旧名单，**不同源**。拿子集复现分数没问题，
拿它与那 18 个读数逐格对齐会有差 —— **贴着阈值的边界样本可能判反**。
**用户 2026-09-13 裁定：这句话要让外部用户一眼看懂后果，写进 README 与 DATA_LICENSE 两处。**
已写明的地方：**[`README.md`](../../README.md) §2.1a** 与 **[`DATA_LICENSE`](../../DATA_LICENSE) §6**
（这两处是裁定点名的），外加 Release 正文、`gold_subset_README.md`、包内 `MANIFEST.json`
与 `ops/data_cards/gold_subset_v1.md`。**本轮不重算，重算排 v1.0.17**（届时 DATA_LICENSE §6 整节删掉）。
f02 上按旧根命名的 `provider/qlib_provider_56134866/` **保留不删** —— 复现那 18 个 run 要靠它。

## 发布收尾卡（2026-09-12）：这张表的**终态**

> 用户裁定 ⑥：**本轮之外发现的一切问题，全部登记在这张表里 —— 不修、不开新票、不做重构。**
> 这一节是那句裁定在 v1.0.16 发布收尾时的收口核对：先把四张卡（A/B/C/D）交出来但还没进表的补齐，
> 再逐类点一遍数。六节短报告见 [`publish_report.md`](publish_report.md)，票据见
> `ops/tickets.md`「发布收尾卡（2026-09-12）」一节（N-703…N-725）。

### 本节补齐的九条（卡 B 全部 + 三卡交接里还没进表的 + 本卡量到的一条）

- **【登记不修】`reference/tasks/*/_ledger.jsonl` 末尾新追加行的 `judge_sha256` 与盘上的判题件不对应。**
  私有 8 行、公开 4 行。S8 四题重出时 `run_oracles` 会连带重建题面，那几行记的是**那份瞬时重建件**的
  指纹；跑完题面已按 `$GB/scratch/B/b_restore.sh` 逐件还原成跑前字节，于是台账与盘上对不上。
  **不修的理由**：台账只追加、全仓无人拿它校验盘上文件；抹掉等于抹审计痕迹。（票据 N-711）

- **【登记不修】公开集 `_ledger.jsonl` 里新追加行的 `set_id` 写成 `v1.0-smoke` 而非 `public/v1.0-smoke-public`。**
  既有字段口径问题，不挡发布验收。（N-712）

- **【操作纪律 / 登记不修】常驻生产网关里的 `sim_factory` 会滞后于盘上代码。**
  改了 `gateway/` 下的代码之后必须 `systemctl --user restart genebench-gateway.service`，
  并轮询 `/healthz`（实测 **74 s** 才在听，`restart` 返回时还没在听）。卡 B 第一次私有跑批四题全红
  （`/sim/log` 返回 500）就是踩了这个。**不修的理由**：这是部署纪律不是代码缺陷，
  写进手册比加一道自检更省事。（N-709）

- **【操作纪律 / 登记不修】起公开网关实例前要先 `python3 ops/guard_modes.py --harden`。**
  它的 `ExecStartPre` 红线 5 守门会被**别的卡**在 `$GB/scratch/` 下留的 0644 文件拦停
  （卡 B 第一次公开发起 `rc=143`，撞的是另一张卡的一个 `.py`）。并发施工的副作用，**不改守门**
  —— 守门做的正是它该做的事。（N-713）

- **【登记不修】`ops/run_oracles.py` 的子集跑会连带重建题面、canary token 每次都换。**
  `packager._token = secrets.token_hex(8)` → 两臂 INSTRUCTION 的 sha 变 → `task.yaml.task_sha256` 漂移。
  本轮用 `b_restore.sh` 逐件还原、**只留新 gold**，所以冻结根实际未变、**没有产生 freeze bump**。
  只想重出 gold 的人照抄那个脚本即可。（N-710）

- **【设计性限制 / 登记】csi500 有两只票有名单没有行情：`SZ000022`、`SZ300114`。**
  baostock 的 csi500 成分里在册，公开行情面没有它们（私有 `universe_pit` 整张表里也没有，W2 §3.1）。
  处置：`csi500.txt` 照留（删掉等于替上游拍板），`all.txt` 不列，qlib 遇到没有数据的码**静默跳过**
  （实测无异常）。**后果**：那些天 csi500 实际参与计算的成员少一只。（N-706）

- **【登记不修】`ops/reports/release_scan_final.md:140` 那句话在换面之后只说对一半。**
  它写着「包内另有 `universe/` 一层 = `scratch/v1_union.txt`（3,575 行）」，而现在 `universe/` 下是四件
  （取数名单 **＋** 卡 A 反投影的 PIT 名单三件）。那份报告是推前扫描的历史留证，按本仓库
  「正文留历史、现值另记」的既有写法不改它 —— 现值在 `ops/reports/public/release_forms.md` §7。（N-717）

- **【设计性 / 登记】公开树里的 `ops/reports/push_result.md` 比内网仓库的少一节（§6 推后补记）。**
  树的内容里含这个文件，而树的提交 sha 是对内容算的 —— 把 sha 写进去 sha 就变，**递归绕不过去**。
  口径写在该文件 §5。（N-721）

- **【已闭 · 2026-09-13 卡 R2 已转绿】~~`ops/test_env.py::test_gold_only_lives_under_reference_or_snapshots` 红 24 条。~~**
  **用户 2026-09-13 裁定：挪走，不许删。** 那份跑前备份（128 件）整棵 `mv` 出了 `$GB`，
  新落点 **`/home/ljn/genebench_s8_prerun_backup_2026-09-12/backup/{private,public,reports}/`**
  （权限 `go-rwx`），原地留了一张路标 `$GB/scratch/B/backup_MOVED_README.txt`。
  **一个字节都没删** —— 它仍是 `ops/reports/s8_gold_reissue.md`「新旧逐字节只差 `produced_at`」
  那个结论的证据面，只是不再落在 `$GB` 里。挪完实跑：
  `ops/test_env.py -k gold` → **3 passed**（含判别力那条反例，门不是被放宽成恒绿的）。
  `s8_gold_reissue.md` 里三处证据路径因此指向旧地址，那个文件不在卡 R2 的路径内 ——
  已写进 `ops/tickets_inbox/R2.md`。原文留档如下：（N-726）

  > **【原登记，2026-09-12】**`test_gold_only_lives_under_reference_or_snapshots` 红 24 条。
  offender 全部在 `$GB/scratch/B/backup/{private,public}/s8-*/gold`（首条
  `scratch/B/backup/private/s8-cor-01/gold`）—— 卡 B 重出 S8 四题 gold 时留的**跑前备份**，
  正是「新旧逐字节只差 `produced_at`」那个结论的证据面。**一条命令即绿**（把那一层路径段从 `gold`
  改掉，或整个移出 `$GB`），但那会让 `ops/reports/s8_gold_reissue.md` 里的证据路径指空。
  **这条红不是答案面泄漏**：那些文件在 f01 的 `$GB/scratch` 下、`0600`、**没进过 f02、没进过任何 bundle**，
  红线 2 管的边界一处都没越。按裁定 ⑥ 只登记。（N-726）

### 逐类计数（截至 2026-09-12 发布收尾）

| 类别 | 上一次盘点（最终卡） | 本轮增减 | **终值** |
| --- | ---: | ---: | ---: |
| **已修 / 已闭**（留证据链） | 12 | **+2** | **14** |
| **设计性限制**（v1 就是这么定义的） | 8 | **+3** | **11** |
| **v1.1**（要改判据或要新证据） | 5 | ±0 | **5** |
| **登记不修 · 量到即记** | 18 | **+12** | **30** |
| **BLOCKED · 待用户** | 4 | **−1** | **3** |
| 合计 | 47 | **+16** | **63** |

**增减逐条**（本轮 16 条实质新增，来源：卡 A 4 + 卡 C 2 + 卡 D 1 + 本节 9；
卡 D 那节「18 个公开 run 跑在旧 provider 上」与卡 A 第二条**是同一件**，正文两处都留、计数合一）：

- **已修 / 已闭 +2**：`instruments/` 再分发依据（原 BLOCKED，用户裁定 ① 走第三条路闭合）、
  公开树推送本身（原 BLOCKED，裁定 ⑤ 已推 `bd0513a4…`）。
- **设计性 +3**：公开包没有 `csi1000`（卡 A）、csi500 两只有名单无行情（本节）、
  公开树里 `push_result.md` 少一节（本节）。
- **登记不修 +12**：τ / ε / 互检仍算旧 gold、签字包归档记旧根、18 个公开 run 与现包不同源（以上卡 A）、
  staging 里那份 09-06 旧包、`RELEASE_MANIFEST.package` 两处旧数（以上卡 C），加本节七条
  （`_ledger` 两条、网关 `sim_factory`、`guard_modes --harden`、canary token、
  `release_scan_final:140`、`test_gold_only_lives_under_reference_or_snapshots` 的 24 条 offender）。
- **BLOCKED −1**：原四条里两条闭合（见上），新增一条 **Release 附件还没挂上去（token 缺 `contents=write`）**
  → 终值三条：baostock 许可正文、`CITATION.cff` 的 `authors` / `date-released`、Release 附件凭据。

> 表头那张「判定汇总」（已修 7 / 设计性 6 / v1.1 6）是**卡 5.2 那一天**的快照，
> 按本仓库「正文留历史、现值另记」的既有写法**不改它** —— 现值以本节这张表为准。

### 本轮**没有**登记进这张表的是什么

只有一类：**本轮做成的事**（裁定 ①②④⑤ 的产物与证据）—— 它们有各自的票据号与证据路径，
写在 `ops/reports/publish_report.md` §二与 `ops/tickets.md` 本节，不重复占这张表的篇幅。
**没有任何一条本轮发现的问题是「既没修、也没登记」的。**

---

## R2（2026-09-13）：本轮全量 pytest 的红，逐条归因

> 口径不变：**恒红恒绿不绕过**。下面每一条都写清「是不是我们的代码问题」「谁该改」。
> 跑法：`flock $GB/locks/pytest.lock` + `systemd-run --user --scope -p MemoryMax=6G`，
> `$PY -m pytest ops/ -q`。**4,515 passed / 9 failed / 33 skipped / 1 xfailed**（22 分 26 秒）。
> 原始日志 `$GB/scratch/R2/fulltest.log`。

| # | 红 | 归因 | 处置 |
| --- | --- | --- | --- |
| 1–4 | `test_lake_baseline.py` 四条（`test_stalled_tables_match_live_recompute` / `..._are_still_these_eight` / `test_freeze_line_green_does_not_imply_alive` / `test_lake_is_the_only_module_that_connects_to_the_lake`） | **外部进程持湖写锁**（宿主上用户自己的 ETL 在跑），与本仓库无关 | 既有已知红，登记不修 |
| 5 | `test_env.py::test_no_api_key_material_in_run_dirs` | offender 全在 **`$GB/scratch/Y1/rh2_operator/ops/test_env.py`** —— **别的代理 scratch 里的夹具**，是「红线 3 扫描器」的**判据正则**被自己扫到（首条 `Y1/rh2_operator/ops/test_env.py:850 OpenAI / DeepSeek 形态`）。**不是泄漏**：那是测试文件里写的正则，不是真 key | 不碰别人的 scratch；登记 |
| 6 | `test_underdetermination_guard.py::test_unattributed_residual_is_documented_in_all_three_places` | 三处之一 `ops/reports/ambiguity_impact_2.2b.md` **正被另一个代理改着**（`git status` 里是未提交的 ` M`），改到一半少了 `22.69%` 那个数 | **别人的半成品，不碰**（并发施工规则）；登记 |
| 7 | `test_wrt.py::test_rebudget只动没跑过的行` | `KeyError: 's1-cor-01.strict.cfg.r01'` —— `job_id` 在这台机上带了 `@finance01-<hash>` 后缀（见捕获到的 stdout），而断言按不带后缀的 id 取行。**环境相关的既有红**，与本轮改动无关 | 登记不修 |
| 8 | `test_readme.py::test_every_repo_path_named_in_the_readme_exists[snapshots/public_v1/gold_factors/csi1000]` | **本卡引入、本卡已修**：新写的 csi1000 那一句里路径写成了 `snapshots/…` 开头，而 `test_readme` 把这种 token 当**仓库路径**核存在性 —— 那份数据在 `$GENEBENCH_ROOT/snapshots/` 下，不在仓库里。已加上 `$GENEBENCH_ROOT/` 前缀，复跑 `test_readme.py` **228 passed** | **已修** |
| 9 | `test_e.py::test_附件还没上传时_报告必须把它记成blocked` | **真红，且是一处对外说假话**：`ops/reports/publish_report.md` 里还留着「一个 Release 都没有，附件清单为空」，而两个附件 2026-09-13 已经挂上去了（`RELEASE_MANIFEST.release_attachments` 两条 `download_url` 都已回填）。那条双向门正是为这种情形写的 | **已修（2026-09-13 卡 F，N-739）** —— 卡 R2 时该文件不在其路径内，按并发施工规则没碰；卡 F 拿到该路径后把那一格改成现状（已建 Release `v1.0.16`、两件附件 `state=uploaded`、两条下载地址与 `sha256` 一并写上），门认的子串已从全文消失，`ops/test_e.py` **14 passed** |

**第 9 条要说清后果**：公开树里带着 `ops/test_e.py` 与 `ops/reports/publish_report.md`，
所以**外部用户 clone 下来跑 `pytest ops/` 会看到这一条红**。它不影响跑题、算分、复现，
但它是「文档在对外说假话」那一类，应当尽快闭合 —— 不是登记就完事的那种。
**2026-09-13 卡 F 已闭**：`publish_report.md` 改成现状并重打树重推，外部用户 clone 下来跑
`pytest ops/test_e.py` 全绿（见 R3 一节「本节新增的四条」第一条与票据 N-739）。
**本轮之后这一节的九条里，第 8、第 9 两条已修，其余七条仍是环境 / 别人的 scratch / 别人的半成品。**

---

## R3（2026-09-13）：Release 上传轮的**终态盘点**

> 这一节接「发布收尾卡（2026-09-12）：这张表的**终态**」。那一节点到 **63 条**；
> 本轮（R1 上传 / R2 清理与同步 / R3 收口 / **F 文档纠偏**）有 **3 条从一类挪到另一类**、
> **4 条实质新增**，终值 **67 条**。四条新增里的第一条（`publish_report.md` 那句已不是现状）
> 由 2026-09-13 的卡 F 当天修掉，因此它落在「已修 / 已闭」而不是「登记不修」—— 合计不变。
> 口径不变：**判定口径只有一条 —— 挡不挡外部用户**。票据见 `ops/tickets.md`
> 「Release 上传卡（2026-09-13）」一节（N-727…N-742），短报告见
> [`release_upload_report.md`](release_upload_report.md)。

### 本节新增的四条

- **【已修 · 2026-09-13 卡 F】`ops/reports/publish_report.md` 里那句「一个 Release 都没有」
  已经不是现状 —— 本条曾是本表里唯一一条「真红 + 文档对外说假话」，现已闭。**
  两个附件 2026-09-13 已挂上、`RELEASE_MANIFEST.release_attachments` 两条 `download_url` 都已回填，
  于是 `ops/test_e.py::test_附件还没上传时_报告必须把它记成blocked` 那条**双向门**的 `else` 分支
  （断言 `"附件清单为空" not in 报告`）当场红。**这一条是本表里唯一一条「真红 + 文档对外说假话」**——
  它从 R2 那一节的「pytest 红逐条归因」专节**提升进表内计数**，理由是它不是测试环境问题。
  R1 / R2 / R3 三张卡都不含该路径（并发施工规则：不碰别人的路径），所以当时只能登记；
  **2026-09-13 卡 F 拿到该路径后修掉**：那一格改成「已建 Release `v1.0.16`（id `387775425`）、
  两件附件 `state=uploaded`」，两条实际下载地址与完整 `sha256` 一并写进报告，门认的子串已从全文消失；
  §三 BLOCKED 与 §六 第 1 条按原样留证并标了日期（既保住证据，也不再是现在时的假话）。
  实跑 `ops/test_e.py` **14 passed**（由 1 failed / 13 passed 转绿），并**重打公开树重推**，
  从远端按 `ref=main` 取回该文件复核子串 0 命中。票据 **N-739**。
  （其余八条 pytest 红仍留在 R2 那个专节、**不计入**本表 —— 它们是环境、别人的 scratch、别人的半成品。）

- **【登记不修】f01 → GitHub 下行只有 ~300 KB/s，而同一条链路上行是 9.5 MB/s。**
  上传 782 MB 用 82 s；把同一件下回来核 sha 要 ~45 min，两件合计实测 **75 分钟**。
  链路还会抖（撞到过 `SSL: UNEXPECTED_EOF_WHILE_READING` 与 `RemoteDisconnected` 各一次）。
  **后果**：凡是「外部用户路径演练」「下回来核一遍」这类验收**要按小时排期**，
  凡是打 GitHub API 的脚本**必须自带重试**，否则会假失败。（N-729）

- **【登记不修】大附件上传的幂等判据只看字节数会漏判：断流后附件停在 `state=starter`。**
  782 MB 那件第一次传到一半 `BrokenPipeError`，Release 上留下一个**字节数看着是对的、其实下不动**的
  半截附件；`scratch/D/d_release.py` 再跑一次会因为「size 一致」误判「已在」直接跳过。
  **正确判据 = size **且** `state == "uploaded"`**。补好的版本在 `$GB/scratch/R1/r1_release.py`
  （每件最多 4 次、先按 `state` 判据 `DELETE` 半截的再传、`403/404/422` 不重试直接停）。
  **不修的理由**：`d_release.py` 是 scratch 里的一次性脚本，替代品已在且已实测跑通。（N-728）

- **【操作纪律 / 登记不修】GitHub Release 对象的 `target_commitish` 会在 force-push + tag 移动之后
  指向一个没有任何 ref 的悬空 commit。**
  该字段是 Release 创建时存下的；tag 已存在时它**不生效**（不会重新打 tag），但留着就是
  「Release 指向一个不存在的 commit」。处置：每次 force-push 公开树之后顺手
  `PATCH /repos/.../releases/<id> {"target_commitish": <新 sha>}`（回 200），
  改完回核 tag / release id / 附件三样都没变。脚本 `$GB/scratch/R2/r2_patch_release.py`。
  **不修的理由**：这是部署纪律不是代码缺陷，写进手册（`HANDOFF.md` §19.6.5）比加一道自检更省事。（N-736）
  **2026-09-13 作废（用户裁定①，N-748 采纳 / N-784）**：`target_commitish` 直接写**分支名** `main` ——
  `PATCH {"target_commitish": "main"}` 实测回 200，且 tag 已存在时该字段不生效，对 tag / 附件 /
  下载地址一概无影响。**这条「每次 force-push 之后手工 `PATCH` 一次」的纪律整条删除**，
  上面原文留证不删。它**不再计入本表的「登记不修」**：本轮已在
  `ops/HANDOFF.md` §19.6.5、`ops/reports/push_result.md` §8.2/§8.3、`ops/tickets.md` 的
  N-736 / N-748 两行四处一起改口（第五处 `ops/reports/release_upload_report.md:85` 见 N-785）。

### 本节**挪类**的三条（不是新增，只是判定变了）

| 条目 | 原判定 | 现判定 | 凭什么 |
| --- | --- | --- | --- |
| staging 里那份 2026-09-06 旧包（N-714） | 登记不修 | **已闭（删了）** | 用户 2026-09-13 裁定删；删前现算 sha256 核身份，存根 `$GB/scratch/R2/deleted_staging_pkg.txt` |
| `test_gold_only_lives_under_reference_or_snapshots` 红 24 条（N-726） | 登记不修 | **已闭（转绿）** | 用户裁定「挪走不许删」；备份整棵移出 `$GB`，一个字节没删，实跑 `-k gold` **3 passed**（含判别力反例） |
| Release 附件还没挂上去（token 缺 `contents=write`） | **BLOCKED · 待用户** | **已闭** | token 已加 `Contents: Read and write`；`POST /releases` 与两次 asset 上传全 201，下回来重算 sha256 逐字相同（N-727） |

### 逐类计数（截至 2026-09-13 Release 上传轮收口）

| 类别 | 上一次盘点（发布收尾卡） | 本轮增减 | **终值** |
| --- | ---: | ---: | ---: |
| **已修 / 已闭**（留证据链） | 14 | **+3**（挪类）**+1**（卡 F 修掉 `publish_report.md` 那条真红） | **18** |
| **设计性限制**（v1 就是这么定义的） | 11 | ±0 | **11** |
| **v1.1**（要改判据或要新证据） | 5 | ±0 | **5** |
| **登记不修 · 量到即记** | 30 | **−2 挪出 / +3 新增** | **31** |
| **BLOCKED · 待用户** | 3 | **−1** | **2** |
| 合计 | 63 | **+4**（实质新增） | **67** |

**BLOCKED 终值两条，都在用户那一侧，都不挡使用**：
① **baostock 许可正文** —— `ops/terms/baostock/permission/` 按裁定**保持不存在**，
**没有塞任何占位文件让锁变绿**；② **`CITATION.cff` 的 `authors` / `date-released`**。

**「阈值与当前 gold 名单不同源」不另计一条** —— 它与卡 A 已登记的「τ / ε / 互检仍算旧 gold」
（登记不修）是**同一件事**，本轮只是把它写进了用户点名的两处（`README.md` §2.1a 与
`DATA_LICENSE` §6）并补上后果描述：**分可复现，但判分用的那条线是跨名单的，贴着阈值的边界样本可能判反。**
重算排 **v1.0.17**，本轮不重算（N-732 / N-734）。

**`csi1000`（8.3 GiB / 792 件）保留在 f01、不入包**已在「发布收尾卡」一节按**设计性限制**记过一条
（「公开包没有 csi1000」，卡 A），本轮**不重复计数**，只补上「保留但不发」这半句
（`README.md` §2.1a / `ops/data_cards/gold_subset_v1.md` / 本文）。（N-733）

### 本轮**没有**登记进这张表的是什么

两类：① **本轮做成的事**（六步上传 + 三条清理 + 两处说明）—— 有各自的票据号与证据路径，
写在 `ops/reports/release_upload_report.md` 与 `ops/tickets.md` 本轮那一节；
② **R2 那一节里其余八条 pytest 红** —— 环境（湖写锁、`job_id` 后缀）、别人的 scratch 夹具、
别人未提交的半成品，按既有口径留在「不该由发布卡替别人判」的专节，不占表内计数。
**没有任何一条本轮发现的问题是「既没修、也没登记」的。**


---

## W（2026-09-13）：卡 V 外部用户侧复核登记的九条

> **这九条是卡 V（2026-09-13，外部用户视角独立复核）在已推的公开树上实测出来的**，
> 逐条的 where / what / 实测输出在 `ops/tickets_inbox/V.md`，命令与日志在 `$GB/scratch/V/`。
> 卡 V 自己**一个字都没往这张表里写**，理由是对的：这份文件是 `RELEASE_MANIFEST.json` 登记的**手写件**，
> 往里追加一个字节就会把当时是绿的 `test_every_recorded_sha_of_a_handwritten_item_is_the_real_one`
> 打红，而唯一的收拾办法是重出清单 —— **清单不在卡 V 的路径里**。卡 V 标了 CONFLICT 并把九条
> 全登记进收件箱。卡 W 同时拿到这两条路径，由卡 W 并入并重出清单。
>
> **九条里八条本轮就修掉了**（落「已修 / 已闭」），**一条知情保留不修**（落「登记不修」）。
> 八条的根因**是同一个**：卡 F 那一轮只拿到六个路径，而「**指着旧状态说话**」的文件
> （`HANDOFF.md` §19.6.4、`release_upload_report.md` §4.1）和「**记着推送前 sha**」的表
> （`HANDOFF.md` §19.6.1、`release_upload_report.md` §三）都不在那六个里面。
> 本轮除了逐条修掉，还把复发根因**断掉了** —— 新口径 `HANDOFF.md` **§19.6.6「树内不记终值」**（N-743）。

### 三条 block（都已修；**值一律没改，只加了显式日期抬头**）

- **【已修 · 2026-09-13 卡 W】`ops/HANDOFF.md` §19.6.1 那张「终值」表指着上一轮的 sha，
  而它自己在同一行给了 `git ls-remote` 当核对命令。**
  实测：表里写 `refs/heads/main` = `f466f1c9…`、tag 对象 `bae14389…`、「公开树现状：2,187 件」，
  而照着敲 `git ls-remote` 实际回 `5e4e179e…` / `2f49fa62…`，件数实测 **2,189** —— **三处全对不上**。
  **后果**：接手的人或外部用户照着自核，会判成「我拿到的不是发布的那一棵」。
  **改法（本轮所做）**：表里三行值**原样留证不改**，抬头改成
  「2026-09-13 R1–R3 轮终值（**留证，非当前值**）；卡 F 之后又推过一轮，**当前终值以 `git ls-remote` 现查为准**」，
  「怎么核」那一列改口成「那一轮是怎么核的」，并在表前写明**自核要用自核不变量**
  （`git log -1` == `git ls-remote origin refs/heads/main` == `git rev-list -n1 v1.0.16` 三者同值），
  **不要拿现查结果去跟表里的值比对**。（卡 V 提，N-744）

- **【已修 · 2026-09-13 卡 W】`ops/reports/release_upload_report.md` §4.1 仍在用现在时说
  「有一条真红 / 文档在对外说假话 / 你 clone 下来跑 pytest 会看到」。**
  三句到 2026-09-13 全是假的：卡 V 在全新 clone 的公开树里实跑 `ops/test_e.py ops/test_d.py` 是
  **31 passed / 1 skipped**，门认的子串 `附件清单为空` 在 `publish_report.md` 里 **0 命中**。
  这正是卡 F 被派去消灭的那一类「文档对外说假话」，只是**换了个文件**——
  而这份短报告恰恰是外部用户最可能读的一份。
  **改法（本轮所做）**：小节抬头改成「**2026-09-13 卡 F 已闭合（N-739），本节原样留证**」，
  正文前加一段写明现状，原文整段保留；另外通读全篇，把 §一第 6 步、§三、§六 里
  其余几处「现在时的过时口径」一并标了日期。（卡 V 提，N-744）

- **【已修 · 2026-09-13 卡 W】`ops/HANDOFF.md` §19.6.4「还欠什么（按挡不挡排）」
  第一行仍把已闭合的事列成「挡」。**
  N-739 早由卡 F 闭合（`ops/tickets.md` 自己写着「已闭合」），这张表却还写着
  「**挡**：双向门当场红，外部用户跑 pytest 会看到 …… 派一张有该路径的卡」。
  **这是全仓库最被人当真的一张「还欠什么」表**，不改会让下一张卡**重做一遍已经做完的事**。
  **改法（本轮所做）**：整张表**逐行**核了一遍 —— 第一行（N-739）与第二行
  （`s8_gold_reissue.md` 三处证据路径，N-731，同样由卡 F 闭合）都改成「已闭合」并划掉留证；
  后三行（baostock 许可正文、`CITATION.cff`、v1.0.17）逐行复核**仍然成立**，保持原状；
  表头加了「整张表逐行核过一遍的日期」。（卡 V 提，N-744）

### 四条 major（都已修）

- **【已修 · 2026-09-13 卡 W】`RELEASE_MANIFEST.json` 的 `package.parts` 里「形态 A」那一条，
  三处字面量全过时，且与同一棵树里的 `README.md` 互相打架。**
  原文是 `{"part": "已打好的公开数据包（形态 A，今天 publishable=false）", "bytes": 788422669,
  "ship": "许可到位后发"}`。实测：① 包内 `MANIFEST.license.publishable` 是 **true**；
  ② 2026-09-13 **已经发了**，同树 `README.md` §2.1a 明写「两个附件已经挂上去了…匿名就能下」；
  ③ `788,422,669` 不是已发的任何一件（已发的 provider 是 **782,100,276**），
  它是卡 R2 按 N-714 **删掉**的那份 `_staging_unpublished` 旧包。
  `RELEASE_MANIFEST.json` 是**机器可读的权威件**，三条里任何一条都够让人对「这个包到底能不能用」判反。
  **改法（本轮所做）**：改**源**不改生成物 —— `ops/mk_release_manifest.py` 新增 `PART_OVERRIDES`
  （键是存档件里的 `path`），把这一条改写成「已发布 / 782,100,276 B / Release `v1.0.16` 的附件，匿名可下」，
  然后重出清单。**存档件 `ops/reports/i_rehearsal_v2/package_inventory.json` 一个字节没改**——
  它是 2026-09-06 那一轮的留证，且改它要连带重算它的 sha。覆盖表的键对不上存档件时**当场停**，
  不许静默无操作。（卡 V 提，N-745）

- **【已修 · 2026-09-13 卡 W】`RELEASE_MANIFEST.json` 的 `blockers[data_license_text].blocks`
  正文三句全已不成立 —— 它在骗读许可条款的人。**
  原文：「形态 A（冻结包下载）：包只落 `$GB/release/_staging_unpublished/`，
  `MANIFEST.license.publishable=false`，**外部用户拿不到包**」。实测：那个目录卡 R2 已删；
  包内 `publishable=true`；两件附件**匿名 206 拿得到**。该条 `satisfied=true`，**不闸任何东西**，
  但正文会被当真。**改法（本轮所做）**：正文改成「许可正文仍未入库（`DATA_LICENSE` §2.1 是显式占位）；
  形态 A 已按 2026-09-13 裁定发布为 Release `v1.0.16` 的附件、匿名可下，**不再阻断下载**」。
  **`satisfied` 的判定逻辑一个字都没动**（仍是 `dl_state == "granted"`）—— 改的只是对外正文。（卡 V 提，N-745）

- **【已修 · 2026-09-13 卡 W】`ops/reports/release_upload_report.md` §三 抬头写「现状」，
  给的却是上一轮的值。**
  `main f466f1c9…` / tag 对象 `bae14389…` / 「2,187 件」，而实际是 `5e4e179e…` / `2f49fa62…` / 2,189 件。
  比上面 §19.6.1 那条轻，因为这一处没有叫读者去 `ls-remote` 比对。同病的还有 §一第 6 步那一格。
  **改法（本轮所做）**：抬头「现状」改成「**2026-09-13 R1–R3 轮终值（留证，非当前值）**」，
  值原样保留，并在表前写明当前终值不写在树里、自核用自核不变量。（卡 V 提，N-744）

- **【已修 · 2026-09-13 卡 W（随本轮重打树自然带上）】公开树里 `ops/reports/push_result.md`
  §8.1 / §8.2 的标题说「公开树里没有这一小节」，而它们就在公开树里。**
  读者在公开树里读到一节说自己不在公开树里 —— 自相矛盾。
  **内网仓库里早就不缺这句更正**：卡 F 的 §8.3 写了「那两句说的是它们**各自那一轮**的树…
  原样保留作留证，别照它去判树是不是漏同步了」，只是 §8.3 是**推完才提交的**，不在已推的那棵树里。
  所以这一条**不需要写新文字，本轮重打树自然带上**。
  同源的还有 §5 对 `§6`/`§6.7` 的同一条更正 —— **这个坑一轮踩一次，卡 V 数到是第三次**，
  这正是本轮立 §19.6.6 口径的直接原因。（卡 V 提，N-743）

### 一条 minor（已修）

- **【已修 · 2026-09-13 卡 W】`ops/HANDOFF.md` §19.5.1 说 README 里有
  「这两个附件今天还没挂上去，上面的地址现在会 404」，README 里已经没有这段了。**
  实测：README 全树 **0 命中**那段话，两条地址匿名 GET 是 **206** 不是 404。
  §19.6 的前言说过「§19.5.4 那六步已经做完」，所以 §19.5 可算上一轮的存档 ——
  但这一句本身是**现在时**、且没有日期抬头。
  **改法（本轮所做）**：句首加「**2026-09-12 那一轮：**」，并在其后补一段写明 2026-09-13 起的现状
  （附件已挂、匿名可下、README 那段提示已删，`ops/test_d.py` 的双向门盯着两边同进同退）。
  §19.5.1 的整屏也加了「这一屏是 2026-09-12 那一轮的终值留证」的抬头。
  **注意**：那一屏里的公开树 sha `bd0513a4…` 是
  `ops/test_e.py::test_handoff_与报告记的远端sha是同一个` 的**断言常量**（要求它同时在
  `HANDOFF.md` 与 `publish_report.md` 里），**只能标日期留证，不能改值**。（卡 V 提，N-744）

### 一条 minor（**知情保留，不修**）

- **【登记不修】已发布的 provider 包内 `MANIFEST.json` 带 `license.published: false`，
  而这个包 2026-09-13 已经发布了。**
  同理，包内 README 里也可能有 `published: false` 的措辞。
  **为什么不修 —— 修的代价远大于害处**：这个字段**烤在 `tar.gz` 里**，改它就要**重打包**；
  重打包就换 `sha256`；而两件附件的 `sha256` 已经写进**三处**并被 **GitHub 自己的 `digest` 字段背书**
  （`ops/release/attachments.json`、`RELEASE_MANIFEST.release_attachments`、
  `README.md` §2.1a 的 `SHA256SUMS.release`；匿名 `Range` GET 回的 `digest` 与本地逐字相同）——
  **一重打包，这三处已公布的校验值当场全部作废**，而这正是外部用户唯一能自证「下到的包没被掉包」的凭据。
  卡 C 撞过一次同形的事（`21ec3202…` → `33083ff2…`）。
  **害处则是有界的**：`published` 这个字段说的是「**许可原文有没有公开可查**」，
  而许可原文确实**仍未入库**（`DATA_LICENSE` §2.1 是显式占位，见 BLOCKED 那两条之一）——
  所以它虽然措辞容易被读成「包没发布」，但它记的那件事**本身没说错**。
  包**是否已发布**另有三处权威出处可查（Release 页、`attachments.json` 的 `download_url`、
  `RELEASE_MANIFEST.release_attachments.uploaded=2`）。
  **处置**：登记，等**下一次本来就要重打包**的时机（v1.0.17 重算 τ / ε 那一轮，N-734）顺手改掉。
  本轮**一个字节都不重打包、不重传任何 asset**。（卡 V 判，本轮照办，N-747）

### 逐类计数（截至 2026-09-13 卡 W 收口）

| 类别 | 上一次盘点（R3 收口） | 本轮增减 | **终值** |
| --- | ---: | ---: | ---: |
| **已修 / 已闭**（留证据链） | 18 | **+8**（卡 V 的三条 block + 四条 major + 一条 minor，本轮全修掉） | **26** |
| **设计性限制**（v1 就是这么定义的） | 11 | ±0 | **11** |
| **v1.1**（要改判据或要新证据） | 5 | ±0 | **5** |
| **登记不修 · 量到即记** | 31 | **+1**（包内 `license.published=false`，知情保留） | **32** |
| **BLOCKED · 待用户** | 2 | ±0 | **2** |
| 合计 | 67 | **+9** | **76** |

**BLOCKED 终值仍是两条，都在用户那一侧，都不挡使用**：
① **baostock 许可正文** —— `ops/terms/baostock/permission/` 按裁定**保持不存在**，
**没有塞任何占位文件让锁变绿**；② **`CITATION.cff` 的 `authors` / `date-released`**。
本轮**没有**新增 BLOCKED，也**没有**闭合既有的两条。

### 本轮立的口径：**树内不记终值**（N-743）

卡 V 数出来这个坑**三轮踩了三次**（`push_result.md` §5 对 `§6`/`§6.7`、同一份文件 §8.3 对
`§8.1`/`§8.2`、本轮的 §19.6.1 与 §三）。**每次重打树，树内写死的终值就变成假话**，
而「每轮补一条口径更正」永远追不完 —— 补更正本身也要重打树。
所以本轮把口径写进 `ops/HANDOFF.md` **§19.6.6**：

1. **进公开树的任何文件里，不写** `refs/heads/main` 的 sha、tag 对象 sha、公开树件数**这三类会变的终值**；
2. 要让人自核，只写**自核不变量**：`git log -1` == `git ls-remote origin refs/heads/main`
   == `git rev-list -n1 v1.0.16`，三者同值即是（卡 V 在全新 clone 上实测当前成立）；
3. 历史留证里**已经写下的值一律不改值**，只在**同一处**加显式日期抬头
   （有的 sha 还是门的断言常量，改了当场红）；
4. **推后终值只记进内网仓库** `$GB/repo` 的 `push_result.md` §8.x；树内文件只写
   「终值在内网仓库，自核用上面那三条命令」—— **这句话本身不含 sha，所以永远不会过期**。

自查脚本 `$GB/scratch/W/w_scan_stale.py`（三类一起扫：写死 sha / 现在时的过时口径 /
「还欠什么」表里状态为「挡」的行），**重打完树、推之前跑一遍**。
判的时候按「**这句话是不是在对外说假话**」判，**不要按子串计数判**——
票据与本表里**描述**这些子串是正常的，门断言的只是它不在 `publish_report.md` 里。

---

## D2（2026-09-13）：Mac 外部验收的七条缺口收口 —— 补了三件、实证一次端到端

> **这一节是「Mac 缺件收口」这一轮四张卡（A2 基座 / B2 物料 / C2 文档 / D2 收口）的合并登记。**
> 由来是用户 2026-09-13 在一台干净 Mac（Apple Silicon，Docker Desktop 29.2.0 aarch64）上做的外部验收：
> **下载 → `sha256sum -c` → 解包 → 本机网关 `/healthz` 200 四步实测通过，端到端阻塞**，
> 报告与证据在用户本机 `~/GeneBench-validation-20260913/`。
> 结论不是「Mac 适配问题」，而是**发布包不完整**：上一轮「单机端到端」演练（`ops/reports/rehearsal_v2.md`）
> 跑在 f02 上，那台机器本来就有统一基座、有公开题集、有标定物料，**所以演练看不见它缺**。
>
> 逐条判定、判据与证据路径在 **`ops/reports/mac_gap_closeout.md`**；本节只做登记与计数。

### 补齐的三件（本轮做掉）

1. **统一基座进仓库**（缺件①，卡 A2）—— `build/base/{Dockerfile,requirements.txt,constraints.txt,README.md}`
   + `build/README.md`，`harnesses/build.sh` 缺基座时**自己从这里构**，报错文案里不再出现发布方绝对路径；
   Node 的 tarball 与 sha256 **按架构分**（原来只钉 x64，Apple Silicon 上必然「下 arm64 的包拿 x64 的哈希核」）。
2. **公开题集实例 + 公开标定物料成为第三个附件**（缺件②③，卡 B2）——
   `genebench_public_runtime_v1.tar.gz`（整棵 `reference/tasks/public/v1.0-smoke-public/`
   + `snapshots/public_v1/{calibration.json,calibration.sha256,epsilon/}`），
   已登记进 `ops/release/attachments.json`，**`download_url` 是空串 = 本轮还没上传**。
3. **文档与外部自检**（卡 C2）—— `--table a` 改 `--table main`、三处文档状态冲突改口同源、
   `ops/test_env.py` 从外部步骤里移除并新增 `ops/selfcheck_public.py`、
   最低配置补 Python ≥ 3.12 / 磁盘 ≈ 15 GB / docker 引擎内存 ≥ 16 GB、
   `ops/public_gateway.sh` 补 macOS 分支（`ss`→`lsof`→`nc`、`setsid`→`nohup`，由 `command -v` 当场判）。

### 端到端实证：这一轮**第一次**在「没有本项目任何遗留物」的树上跑通

卡 D2 在 f02 上开了一个**全新目录** `/data/d2_e2e`，从内网仓库 clone 一棵干净树、落位三个附件、
**用仓库里那份 `build/base/Dockerfile` 现构一个全新 tag 的基座**（`gb-base:d2e2e-20260913`，`--no-cache`，
69 秒，`pip freeze --all` 与既有基座**逐行相同**），harness 也构新 tag，
起网关（`/healthz` 200 / `channel=public` / `bind=192.168.1.219:18080`），
**三题双臂 6 个 run 真跑**，结算出 `--table main`。
**既有 `gb-base:bookworm-r1` 与 `gb-cx-u:r1` 全程没碰**，收尾逐个核过 image ID 不变。

**arm64 这一层要分清楚**（这是本轮最容易被读过头的一处）：

* **实测**：`build/base/` 那份 Dockerfile 在 **x86_64** 上构得出可用基座（f02，两次，A2 一次 282 秒 / D2 一次 69 秒）；
  两次的 `pip freeze --all` 与既有基座逐行相同。
* **查实（不是实测）**：每一个 pin 的 arm64 可得性逐条查过 —— `FROM` 钉的 python digest 直查 registry
  确认是 multi-arch OCI index（含 `linux/arm64/v8`）、Node 的 arm64 tarball **真下载 30,246,708 字节核过哈希**、
  pandas / numpy / pyarrow 三个 `cp312` aarch64 manylinux 轮子也真下载核过哈希。
* **没做过**：**在 arm64 机器上把镜像真构出来一次**。f02 是 x86_64 且无 buildx / binfmt，
  f01 没有容器运行时，施工用的 Mac 沙箱连不上 docker daemon。
  补法（三条命令）写在 `ops/reports/base_image_portability.md` §4。**这一条排 v1.1。**

### 本轮**登记但没修**的（逐条在 `ops/tickets.md` 本轮那一节）

**卡 A2 留下 5 条**：`.gitignore` 那条不锚定的 `build/`（N-752，要裁定）；`push_exec_to_f02.sh` 不推 `build/`（N-753）；
没有 buildx 的 docker 把 `--platform` 当空气、一路「绿」到最后一步才炸（N-754）；
`RELEASE_MANIFEST.json` 的仓库文件清单里没有 `build/` 那五件（N-755）；`harnesses/README.md` 两处已过时（N-756）。

**卡 B2 留下 5 条**：`ops/run_controls.py:53` 写死发布方题集根（N-757）与同类写死五处（N-758）；
重打树时 `EXCLUDED.txt` 要写明「题集与标定在第三个附件里」（N-759）；
`public_channel.md` 补一条指向新数据卡的链接（N-760）；
`ops/test_public_chain.py:296` 断言 `calibration.json` 里的发布方绝对路径、外部必红（N-761）。

**卡 C2 留下 6 条**：`GATEWAY_HOST` 没有环境变量可覆盖（N-763）；`run_joblist --tables` 帮助文本漏了 `main`（N-764）；
`run_joblist` 起子进程写死 `genebench_config.PYTHON`（N-765）；
macOS 上没有 systemd、推送守门要的那道答案面扫描 timer 缺失（N-767）；
`ops/test_env.py` 断言 `qlib`/`httpx` 而六包说明里没有这两个（N-768）；
「Mac 上原样跑 `public_gateway.sh start` 拿 200」这一步施工侧没能亲手验到（N-769）。

**卡 D2 在端到端那条链上撞出 8 条**（全是**外部单机用户会撞、发布方自己撞不到**的形态）：

* **N-770 最要紧** —— `ops/score_runs.py:45` 的 `RUNS_IN` 写死 `/data/shared/genebench/runs_in`，
  **且没有任何 CLI 覆盖**。`--no-pull` 在外部机器上**退 0 并打印「runs: 0；问题: 0」**，不报错；
  `--remote` 那条更糟，`pull()` 里 `F02 = "ljn@192.168.1.219"` 也是写死的，
  外部用户敲 `--remote <自己的路径>` 会让 rsync 去连**发布方的执行面**。
  D2 加一条软链把 run 根挂到那个写死的位置之后，**整条结算链一次通过** —— 挡路的就这一个常量。
* **N-771** 两个大附件**没有任何文档给过落位命令**，而 `provider/` 还要**改名**成 `qlib_provider/` 才被认。
* **N-772** `push_guard.py` / `push_bundle_to_f02.sh` 不带通道，公开 bundle 过门时报的是「冻结引用已过期 →
  **重新导出**」，而重新导出解决不了 —— 真因是 `GENEBENCH_CHANNEL` 没给。
* **N-773** 手册 §1.2 让人从 `bootstrap.pypa.io` 引导 pip，那个域名在这台机器上**挂住 11 分钟 0 字节**
  （与 Y-03 记的 pypi.org 同症状），而 §1.2 的镜像出路只覆盖了 pypi.org。
* **N-774** `python3 -m venv $GB/env` 在 Ubuntu 24.04 上建出一个**没有 pip 的半成品并留下 `bin/python`** ——
  「文件在不在」这个最自然的判据为真而实际不可用。
* **N-775** `ops/guard_modes.py --harden` 的 `EXTERNAL_ROOTS` 写死 `/data/shared/genebench`、不存在就跳过，
  于是在外部机器上**根本没有收紧 `$GENEBENCH_ROOT`**，而 README §2.1 说它收紧。
* **N-776** 边车镜像 `python:3.11-alpine` 来自 docker.io，**「所需外网」表里一条都没提**；
  失败时刻在**真跑开始之后**。
* **N-777** `harnesses/build.sh` 的 `BASE_IMAGE` 写死、没有环境变量入口 ——
  机器上已有同名旧基座时没办法让它用新构的那个（**对外部用户无影响**）。


**重出 `RELEASE_MANIFEST.json` 之后又冒出三条**（本卡按任务书重出清单，`release_attachments`
从 `n=2 / uploaded=2` 变成 `n=3 / uploaded=2`，两道**双向门**随之翻面 —— **不是回归，是状态真的变了**）：

* **N-779** `ops/reports/publish_report.md` 里没有第三件附件，`ops/test_e.py` 的
  `test_报告引的附件数值与清单同源` 与 `test_附件还没上传时_报告必须把它记成blocked` 两条当场红。
  后者要的子串 `附件清单为空` 正是卡 F 按 N-739 特意删掉的（当时两件都已上传，删得对）。
  修法是三行文字，落点在那份报告 —— **不在本轮四张卡任何一张的可改路径内**。
* **N-780** `ops/test_pack_release.py:280` 写死 `ra["n"] == 2`（下一行还写死了附件名集合）——
  与契约点名的 `ops/test_c41.py:366` 那条 `len(REG.CONFIGS) == 3` **是同一个形状**：
  写死件数的断言会被「第一个把新东西登记进来的代理」跑红，而那不是回归。
* **N-781**（**别人的，本轮没碰**）`ops/test_V2.py::test_十个收件箱都改名merged了_原名一个不留`
  **恒红** —— 它要求 `ops/tickets_inbox/V2.md` 不存在，而卡 V2 的提交 `476bd14` 新建了这个文件，
  且这个卡号在更早一轮已经并过表、`V2.md.merged` 已在。本卡在落地任何东西**之前**跑这套定向测试时它就已经红。

### 还剩什么不满足「只凭 README」（本节的诚实交代）

1. **第三个附件还没上传**（`download_url` 是空串）。在它挂上去之前，外部用户拿不到公开题集树，
   `ops/freeze_v10.py --check-all` 的公开轴核不绿、题也跑不起来。**要用户点一次头**（见 BLOCKED）。
2. **结算那一步外部用户过不去**（N-770）—— 本轮**没有修**，因为 `ops/score_runs.py` 不在这四张卡任何一张的可改路径内。
   D2 的 19 列表是**加了一条软链**才出出来的，这一点写在 `mac_gap_closeout.md` 里，没有含糊过去。
3. **两个大附件的落位命令还没写进文档**（N-771）。
4. **arm64 只查实、没实构**（见上）。

### 逐类计数（截至 2026-09-13 Mac 缺件收口轮）

| 类别 | 上一次盘点（卡 W 收口） | 本轮增减 | **终值** |
| --- | ---: | ---: | ---: |
| **已修 / 已闭**（留证据链） | 26 | **+10**（缺件① 三条 + 缺件②③ 两条 + 文档五条） | **36** |
| **设计性限制**（v1 就是这么定义的） | 11 | ±0 | **11** |
| **v1.1**（要改判据或要新证据） | 5 | **+1**（arm64 实机构建一次并回填报告 §5） | **6** |
| **登记不修 · 量到即记** | 32 | **+27**（A2 5 / B2 5 / C2 6 / D2 11） | **59** |
| **BLOCKED · 待用户** | 2 | **+1**（第三个附件要不要传上已发布的 `v1.0.16`） | **3** |
| 合计 | 76 | **+39** | **115** |

**BLOCKED 终值三条，都在用户那一侧**：① **baostock 许可正文** —— `ops/terms/baostock/permission/`
按裁定**保持不存在**，没有塞占位文件让锁变绿；② **`CITATION.cff` 的 `authors` / `date-released`**；
③ **本轮新增：`genebench_public_runtime_v1.tar.gz` 要不要传上已经发布的 Release `v1.0.16`** ——
往一个已发布的 Release 加附件会改变已发布物的内容，需要用户明确一句「传」。
包已打好、已登记、`download_url` 留空，本轮**没有上传**。

### 本轮**没有**登记进这张表的是什么

① **本轮做成的事** —— 各有票据号与证据路径，写在 `ops/reports/mac_gap_closeout.md` 与
`ops/tickets.md` 本轮那一节；② **端到端那 6 个 run 的分数** —— 那是**构造验收**不是能力读数
（`ops/reports/d2_e2e/table_main.csv` 的题注已写明），不占本表计数；
③ **f02 上遗留的僵尸任务容器**（超时终止后任务容器没被回收，本轮实测撞到一次、另有两个更早的遗留）——
那是执行面运维，不是发布件的问题，记在 `mac_gap_closeout.md` §6 的「顺带量到的」里。
**没有任何一条本轮发现的问题是「既没修、也没登记」的。**

## P3（2026-09-13）：发布前最后一轮 —— 修掉三条真阻塞，剩下的逐条交代

> 本轮三张卡：**P1**（代码根因：把「默认值指着发布方那台机器」扫干净）、**P2**（三条裁定的文档部分
> 与临时解包纪律）、**P3**（合表与收绿：票据并表、本节、重出 `RELEASE_MANIFEST.json`、定向测试）。
> 票据在 `ops/tickets.md` 的「发布前最后一轮（2026-09-13）」一节，N-782…N-796。
> **本轮只落到内网仓库**：没有重打公开树、没有 push、没有传附件、没有碰 Release、
> 没有动已发两件附件一个字节，三条版本轴（v1.0.16 / r1.0.23 / p1.0.0）一个值没改。

### 本轮修掉的三条真阻塞（外部单机用户会撞、发布方自己撞不到）

1. **结算与入库过不去（N-770 一类）—— 唯一的硬阻塞，已修。**
   `ops/score_runs.py:45` 的 `RUNS_IN` 写死 `/data/shared/genebench/runs_in` 且**没有任何 CLI 覆盖**，
   `:44` 的 `F02` 与 `pull()` 的远端主机也写死；而 `ops/results_db.py::protocol_by_run()` 用的是
   `cfg.GENEBENCH_ROOT / "runs_in"`。**在发布方这台机器上这两条是同一个路径，所以这处分叉内部永远看不见。**
   卡 D2 实测三种走法全断：`--no-pull` → `FileNotFoundError`；`--remote <自己的路径>` → rsync 去连了
   **发布方的执行面**（`Host key verification failed`）；只接 `score_runs` 一头 → `results_db ingest`
   报「协议轴反算不出」。**D2 那张 24 列表是补了两条软链才出出来的。**
   卡 P1 把同一类一次扫完（`score_runs` / `run_controls` / `guard_modes` / `readiness_report` /
   `run_probe_mutations` / `validator_parity`），全部改从 `cfg.GENEBENCH_ROOT` 现算，并给 `score_runs`
   补了 `--runs-root` 与 `--remote-host`。**现在外部用户一条软链都不用**：
   `export GENEBENCH_ROOT=<你的根>`，run 放进 `$GENEBENCH_ROOT/runs_in/<batch>/<run_id>/`，
   `ops/score_runs.py --batch <batch> --no-pull` 直接出表、入库同源。
   run 根不在时**当场停并打印三条出路**（从前是 `FileNotFoundError`，更早是退 0 打印「runs: 0；问题: 0」）。
2. **`ops/mk_release_manifest.py --check` 在每一个外部 clone 上都退 1（N-748 / 裁定②）—— 已修。**
   根因是 `:362` 的 `"status_now": ("有 remote" if has_remote else declared_why)`：内网 `$GB/repo` 无远端，
   而**任何 clone 都有 origin**，`blockers` 又在 `FATAL_KEYS` 里，于是判据每次都「变了」。
   README §5 把退 1 定义成「判据变了（**停下**）」—— 这正是 Mac 验收撞到的那条。
   同一函数的 `clone_urls_declared` docstring 自己写着「刻意不查可达性，那会让这份清单的内容
   取决于跑它的机器」。按用户裁定②**修根因、不写文档教人忽略非零**：`status_now` 回到 `declared_why`，
   同一个病的第二处（`public_channel_zero_runs` 读 `$GB` 下的跑批清单）改读仓库里的
   `ops/reports/m6_public/records.json`。那句 docstring 同时变成了判据：
   `ops/test_P1.py::test_清单在有remote与没有remote的同一棵树上逐字节相同`（正面）
   + `::test_这条机器无关性比对自己有判别力`（反面）。
   **卡 P2 按裁定删掉了 README §2.1 / README §5 / 手册 §0.0 三处「非零不代表发布件损坏」的说法** ——
   根因修完就不该再有那句话。
3. **`RELEASE_ITEMS` 不收 `build/` 五件（N-755 / N-778）—— 已修。**
   `build/README.md` + `build/base/{Dockerfile,requirements.txt,constraints.txt,README.md}`
   正是「外部用户构基座必须拿到的东西」，清单不收 = **清单在说交付完整而基座仍缺件**。
   卡 P1 加了分组「统一基座构建上下文」，卡 P3 重出清单：发布件 **53 → 58 件，缺件 0**，
   `--check` 退 0、`releasable=true`、未闭合 blocker 0。

### arm64：哪一层是实测，哪一层是查实（这一节不许含糊）

| 层 | 状态 | 依据 |
| --- | --- | --- |
| `FROM` 的 python 基础镜像含 `linux/arm64/v8` | **查实**（不是实测） | 卡 A2 直查 registry 的 manifest list，按 digest 钉住 |
| Node tarball 的 arm64 sha256 | **查实** | 卡 A2 按架构分别钉 x64 / arm64 两份（原来只钉 x64）；arm64 那份没有在 arm64 机器上解包验证过 |
| `build/base/` 在 **amd64** 上 `--no-cache` 构得出来 | **实测两次** | 卡 A2 在 f02 实构 282 秒；卡 D2 在一棵**没有本项目任何遗留物**的树上重构 69 秒，两次 `pip freeze` 与既有基座**逐行相同** |
| `build/base/` 在 **arm64** 上构得出来 | **没有实测** | f02 无 buildx / binfmt，`docker.io` 被墙不能拉新基础镜像；发布方手上没有 arm64 机器。按裁定走**逐条查实** |
| `harnesses/build.sh` 在 macOS bash 3.2 下不炸 | **已修并实测** | 真病灶不是「判断发生在展开之后」，而是 **`$VAR` 后紧跟中文标点** —— macOS bash 3.2 在 UTF-8 locale 下把标点头一个字节吃进变量名。全脚本改成 `${VAR}` |

**结论**：arm64 那一格仍是 **v1.1**（要新证据：一台 arm64 机器上实构一次并回填报告 §5）。
2026-09-13 的 macOS 验收机器是 Apple Silicon + Docker Desktop aarch64，**但那次没有构基座**
（当时仓库里还没有 `build/base/`），所以它不算这一格的证据。

### 本轮新登记、判成**不修**的七条

* **N-785** `ops/reports/release_upload_report.md:85` 是裁定①作废掉的那条手工纪律的**第五处**落点。
  内部留证报告，不挡外部用户；那个路径不在本轮三张卡任何一张手里。
* **N-786** `frozen/` 要不要落位，`mac_gap_closeout.md` §4 与 README §2.1a 口径不一致。
  实查：provider 包里 `frozen/` 装的是**仓库相对路径**的六件，仓库里本来就有，
  发布方的 `$GB/snapshots/public_v1/` 下**没有** `frozen/` 这个目录。已按保守方向（不用落位）写进 README。
* **N-787** `ops/results_db.py` 没有 `--runs-in` CLI。两处默认根现在**同源**，外部用户不需要它；
  只有用 `--runs-root` 指到别处时才需要，`score_runs` 的 help 已写明这句。
* **N-790** 仍写死 `/data/shared` 的七个 `ops/*.py`：纯发布方内部工具，不在「结算 / 出集 / 外部自检」
  三条链路上。逐条依据表在 `ops/tickets_inbox/P1-push.md.merged`。
* **N-791** `ops/test_*.py` 里的 `/data/shared` 字面量多数是**判据本身**
  （`test_public_acceptance.py::BEFORE` 抄的就是改动前的原文，读出来的话那条永远绿）。改它们等于把判别力改没。
* **N-793** `RELEASE_MANIFEST.blockers[no_clone_url].closes_when` 引用已删的 `_staging_unpublished/`：
  该 blocker 已 `satisfied=true`，`closes_when` 记的是历史判据不是现行动作。
* **N-796** `ops/test_wrt.py::test_rebudget只动没跑过的行` 恒红：`job_id` 现在带机器后缀，
  断言还按裸 `job_id` 取。卡 P1 在**没有本轮任何改动的 clone** 上复跑同样红 —— **不是本轮带的**。

### 还剩什么不满足「只凭 README 走到底」（本节的诚实交代）

1. **第三个附件还没上传**（`genebench_public_runtime_v1.tar.gz`，`42,046,516` B，
   `49e9b250d398a1ce…`，已登记、`download_url` 仍空）。在它挂上去之前，外部用户拿不到公开题集树，
   `ops/freeze_v10.py --check-all` 的公开轴核不绿、题也跑不起来。
   **用户 2026-09-13 已裁定「传上已发布的 `v1.0.16`，不新建 Release、不碰已在的两件」** ——
   所以这一条**不再是 BLOCKED·待用户，而是待执行**（归传附件那张卡；回填 `download_url` 之后
   要跟着改口的是**五处**，见 N-783）。
2. **N-782 那条门还没翻面**：`ops/test_docs_consistency.py` 的 fact `manifest_check_nonzero_is_not_damage`
   恒红 —— 它 `require` 的正是裁定②要删掉的那句话。根因已修，那条 fact 应当翻面
   （`require` 换成 `刻意不取决于跑它的机器`、`forbid` 换成 `非零 ≠ 发布件损坏`）。
   幂等补丁在 `$GB/scratch/P2/p2_fact_patch_for_P1.py`；`ops/*.py` 不在本轮三张卡任何一张的可改路径内。
3. **README §443 与手册 §161 还写着「唯一的例外是两条软链」**（N-794）。那是卡 D2 当轮的实况，
   N-770 修完之后**外部用户不需要任何软链**；留着的代价是照做的人会先去建两条没必要的软链。
4. **arm64 只查实、没实构**（见上表）。
5. **公开树上还没有本轮与上一轮的任何成果** —— 本轮按编排**没有重打树、没有 push**。
   今天拿到公开树的人看到的仍是 `v1.0.16` 那一版（卡 V2 实测的两条 block 里的第二条）。

### 逐类计数（截至 2026-09-13 发布前最后一轮）

| 类别 | 上一次盘点（Mac 缺件收口轮） | 本轮增减 | **终值** |
| --- | ---: | ---: | ---: |
| **已修 / 已闭**（留证据链） | 36 | **+14**（三条真阻塞 + 裁定①③ + N-779/780/781/788/789 + 文档三条） | **50** |
| **设计性限制**（v1 就是这么定义的） | 11 | ±0 | **11** |
| **v1.1**（要改判据或要新证据） | 6 | ±0（arm64 实机构建仍在这一格） | **6** |
| **登记不修 · 量到即记** | 59 | **+7**（N-785/786/787/790/791/793/796） | **66** |
| **BLOCKED · 待用户** | 3 | **−1**（第三个附件要不要传：用户已裁定「传」，转为待执行） | **2** |
| 合计 | 115 | **+20** | **135** |

**BLOCKED 终值两条，都在用户那一侧**：① **baostock 许可正文** —— `ops/terms/baostock/permission/`
按裁定**保持不存在**，没有塞占位文件让锁变绿；② **`CITATION.cff` 的 `authors` / `date-released`**。

### 本轮**没有**登记进这张表的是什么

① **本轮做成的事** —— 各有票据号，写在 `ops/tickets.md` 本轮那一节；
② **两条「还开着的红」**（N-782 的 fact 翻面、N-795 的断链符号链接）—— 它们不是**限制**，
是**根因已定、补丁/命令已写好、只差一次执行**的动作，闭合之后不留痕；两条都登记在票据里，
并写进了本轮 P3 卡的输出交编排方；
③ **第三个附件的上传** —— 用户已裁定「传」，是待执行动作不是限制（见上「还剩什么」第 1 条）。
**没有任何一条本轮发现的问题是「既没修、也没登记、也没交出去」的。**
## S（2026-09-13）：终核八条的收口 —— 修掉会误导外部用户的那几条 + 预算档 + D-06 第五例

> 由来是**卡 Rfin（终核卡，只读）**在一棵克隆树与一个外部 `GENEBENCH_ROOT` 上实测出来的八条
> （N-808 ~ N-815，逐条 where / what / 实测输出在 `ops/tickets_inbox/Rfin.md`；同卡另有两条实跑留证）。
> 本卡把其中**会让外部用户读到假话、或者做对了反而红**的六条修掉、一条动作闭掉，
> 另按用户 2026-09-13 的裁定把**预算档**写进 README 与手册两处，并把 D-06 那一族的**第五例**补进本表。
> 本轮证据在 `$GB/scratch/S/`（`selfcheck_before.txt` / `selfcheck_after.txt` / `tests_*.log`）。
> **三条版本轴（`v1.0.16` / `r1.0.23` / `p1.0.0`）一个值没改**，τ / ε 没重算。

### 本轮逐条（六条修、一条闭）

1. **【已修】`ops/selfcheck_public.py` 的第 5 项把「第三件附件还没上传到 Release」写成了硬编码字符串（N-808）。**
   这是本轮**唯一一条会误导外部用户的现在时假话**：那一件 2026-09-13 下午已经传上
   （asset id `561398049`，匿名 Range GET 206，`digest` 与本地 `sha256` 逐字相同），
   而**同一次运行的第 4 项**已经从 `ops/release/attachments.json` 现算并打出了含这一件的三条 `curl` 地址 ——
   外部用户在同一屏上读到互相矛盾的两句，还被劝去等一个已经到位的东西。
   **改法**：第 5 项那段提示改成 `_missing_public_material_hint()`，与第 4 项**同源**
   （都读 `ops/release/attachments.json`，按 `role == "public_runtime_material"` 认那一件、
   **不按文件名写死**），按 `download_url` 空不空分支；这个文件里不再写死任何一句「上传了没有」。
   **实跑留证（两棵树各一次）**：落位前（空的外部根）第 5 项仍是「登记在案」，
   下文改成打出那一件的真地址；落位后（第三件已落位的外部根）第 5 项直接是
   **绿 · 三条轴与 RELEASE_MANIFEST 逐字相同**。原始输出 `$GB/scratch/S/selfcheck_{before,after}.txt`。
2. **【已修】`ops/test_b2.py:84` 读的是私有标定，外部落位正确之后仍恒红（N-809）。**
   `test_calibration_gate_passes_and_reports_the_public_tau` 最后一句读
   `$GENEBENCH_ROOT/snapshots/v1/calibration.json`（**私有通道**那份），
   而三件附件里一件都没有它（公开那份在 `snapshots/public_v1/`）。**与 N-770 同形**：
   判据悄悄取决于「跑它的是不是发布方那台机器」。
   **改法**：读不到就 `pytest.skip`，读得到（= 发布方那台）照旧判。
   **私有 τ 的值不往公开树里钉** —— 它是私有通道的标定物，钉进去等于把一个不随包发的值发出去。
   前半截（公开 τ 与 `calibration.sha256` 对得上）在 skip **之前**就已经跑过，这条不会退化成整条恒绿；
   反面门 `test_calibration_gate_bites_on_sha_mismatch` 用 `tmp_path`，不受影响。
3. **【已修】README 与手册把外部自检说成查「两个附件」，实为三件（N-810 / N-811）。**
   六处：`README.md` 外部步骤的行内注释、紧跟的引用块逐项、§2.1 的数据面二选一、§5 那句
   「Release 的两个附件」、`docs/OPERATOR_MANUAL.md` §0.1 的外部自检说明、
   `ops/selfcheck_public.py --downloads` 的 help ——
   而 `selfcheck` 自己打出来的是「发布附件落位与 sha256（清单登记 **3** 件）」。
   **改法按「不写死件数」优先**：能不写件数的改成「发布附件」并指向
   `ops/release/attachments.json`（件数的单一来源），必须说数的地方改成三件。
   README §2.1a 那句「两个附件已经挂上去了」**没有动** —— 它下一行就自我更正成三件，在上下文里成立。
4. **【已修】README 的磁盘预算表只算了两个附件（N-812，原判「登记不修」，本轮顺手做掉）。**
   下载那一行补上第三件 `42,046,516 B`（三件合计 `981,595,397 B` = 936.1 MiB），
   解包那一行补上 `84,755,038 B`。**合计 ≈ 10.8 GB 与「按 15 GB 准备」的结论不变。**
5. **【已修】`ops/test_V2.py::_main_table_dirs()` 把用户自己的输出目录也圈了进来（N-813）。**
   它原来扫 `ops/reports/*` 下**任何**含 `table_main.csv` 的目录，
   而 README §2.4 给外部用户的那条命令只产出 `table_main.csv` + `table_main.axes.json`，
   于是 `test_每个出了主表的批都有两张全量指标表` 在**任何外部 clone 上、照着 README 做对之后**当场红。
   **改法是收窄射程、不放宽判据**：只看仓库自己交付的那批目录（`git ls-files` 认得的），
   被圈进来的那六件仍然逐件查；拿不到 git 就退回原来的全扫。
   同一节的 `>= 20` 是这条收窄的**下限守卫**——收窄收过头会在那里当场红，不会静默变成空集。
6. **【已修】`ops/test_V2.py::test_签字包逐件sha256对得上_且都是0400` 在任何 clone 上恒红（N-815）。**
   `git clone` 不保留 `0400`，落地成 `0600`。**改法同样是收窄射程**：
   断言从「模式恰好等于 `0400`」改成「模式不含 group / other 位」（`S_IMODE & 0o077 == 0`）——
   `0400` 与 `0600` 都过，而 `0440` / `0604` 这类**真的泄出去**的照样红。逐件 sha256 那一半一个字没动。
7. **【已闭】N-814 / N-795 的断链符号链接与裁定③ 扫尾。**
   `$GB/scratch/C2/extroot2/repo` 那条断链由编排方删除（`ops/guard_modes.py` 回「敏感根权限合规（2 个根）」、退 0）；
   本卡把同目录余下的 `{reference（→ $GB/reference 的软链）, env, logs, results, snapshots}`
   **整棵移**到 `/home/ljn/genebench_scratch/C2-extroot2/`（移，不是删），空目录随后删除。
   移完复核：`ops/guard_modes.py` 仍「敏感根权限合规（2 个根）」退 0、
   `ops/test_env.py` **63 passed / 1 skipped**、`$GB/scratch/C2` 下**一条软链都不剩**。

### 用户裁定：预算档写进两处文档（README + 手册，`ops/test_docs_consistency.py` 钉住）

数出自 `runner/registry.py`（现读，不照抄转述）：默认 `RUN_BUDGET` = **100 次调用 / 6,000,000 tokens**，
`BUDGET_TIERS` 的 **S4 = 150 次 / 9,000,000**、**S7 = 300 次 / 18,000,000**，入口 `budget_for(stage)`，
`--max-calls` / `--max-tokens` **逐键赢过档位**。
两处都写明：**撞闸记 `budget_exhausted`，那是一个收口状态、不是失败** ——
它与 `ok` / `violation` / `timeout` 并列（`runner/c42/failure_modes.py::RUN_STATUSES`，顺序即优先级）；
主表里撞闸那一格渲染成 **`—`**（`scorer/report.py::NO_READING`），
而 `—` / `0` / `unobservable` 是**三个不同的东西**（另有第四种 `n/a` = 这个量在这一阶段不定义）；
**撞了闸不一定就记 `budget_exhausted`** —— 已经把产物写下来之后才撞闸的 run 终态是 `ok`。
并按用户裁定写进一句**免得外部用户以为自己配错了**：卡 D2 那次三题双臂六个 run 的终态分布
（3 个 `budget_exhausted` / 1 个 `timeout` / 1 个 `ok` / 1 个 `violation`，其中四个用满 100 次调用）
是 **100 次闸下的真实分布**、与 M6 一致，**这六个 run 的分布不调档**。
新增的门：`ops/test_docs_consistency.py::budget_tiers_and_exhausted_status`（两处各 5 条 require + 1 条 forbid，
**两个方向都有牙**：把那句话改成「撞闸算失败」，require 当场缺、forbid 当场命中）。

### D-06 家族第五例（用户点名）：N-770 的 `RUNS_IN` 分叉

D-06 是「**所有信号都是绿的，而某个东西悄悄不见了**」这一族（逐条总表在
`ops/specs/design_notes.md` §D-06）。它在本项目**发布**这条线上长出了一个固定的分支：
**一条判据悄悄取决于「跑它的是不是发布方那台机器」，于是在内网永远看不见。**
这一支在本表里此前记过四例：

* **N-748**：`ops/mk_release_manifest.py:362` 的 `status_now` 看「这棵树有没有 remote」——
  内网 `$GB/repo` 无远端，而**任何 clone 都有 `origin`**，于是 `--check` 在每一个外部 clone 上都退 1。
* **N-761**：`ops/test_public_chain.py:296` 断言 `calibration.json` 里写着发布方的绝对路径 —— 外部必红。
* **N-775**：`ops/guard_modes.py` 的 `EXTERNAL_ROOTS` 写死 `/data/shared/genebench`、**不存在就跳过** ——
  外部机器上于是**根本没有收紧** `$GENEBENCH_ROOT`，而 README §2.1 说它收紧了。
* **N-809**（本节上面第 2 条）：`ops/test_b2.py` 读私有标定 —— 外部正确落位之后仍 `FileNotFoundError`。

**第五例 N-770 的成因与前四例都不同，这正是它最难被发现的地方。**
前四例里，那条写死的东西在外部机器上**当场不成立**（没有 remote / 路径不存在 / 文件不在），
所以它一到外部就以某种形式显形；
而 N-770 是 `ops/score_runs.py:45` 的 `RUNS_IN = /data/shared/genebench/runs_in` 与
`ops/results_db.py::protocol_by_run()` 用的 `cfg.GENEBENCH_ROOT / "runs_in"` **两条路径的分叉** ——
**在发布方那台机器上 `cfg.GENEBENCH_ROOT` 恰好等于那个写死的绝对路径，两条路径同值**，
于是这处分叉**在内部永远不显形**：两边指着同一个目录，结算与入库看起来完全同源。
它**只有在外部机器上才第一次分岔**，而分岔之后的表现还不是报错 ——
`--no-pull` 那条路当时**退 0 并打印「runs: 0；问题: 0」**（后来卡 P1 改成当场停并打印三条出路）。
**教训**：「两处默认值写法不同但今天同值」不是风格问题，是一条**只在别人机器上才会现形的分叉**；
判据是「把这两个值改成不同，链路还对不对得上」，不是「在我这台上跑得通吗」。

### 本轮的口径补一条：会打印给用户看的 `.py` 也在「文档说没说假话」的射程里

`$GB/scratch/W/w_scan_stale.py` **只扫 `.md`**，而 N-808 那句假话在 `.py` 里 ——
那类扫描**结构性地看不到它**。下次扫「文档说没说假话」，
要把**会打印给用户看的 `.py`**（`ops/selfcheck_public.py` 这样的自检、各 CLI 的 `--help` 与提示文案）
一起纳入射程。本条已写进票据（见 `ops/tickets.md` 本轮那一节）。

### 逐类计数（截至 2026-09-13 卡 S 收口）

| 类别 | 上一次盘点（发布前最后一轮） | 本轮增减 | **终值** |
| --- | ---: | ---: | ---: |
| **已修 / 已闭**（留证据链） | 50 | **+7**（N-808/809/810/811/812/813/815；下面第 7 条 N-814/N-795 是**动作**不是限制，不占计数） | **57** |
| **设计性限制**（v1 就是这么定义的） | 11 | ±0 | **11** |
| **v1.1**（要改判据或要新证据） | 6 | ±0（arm64 实机构建仍在这一格） | **6** |
| **登记不修 · 量到即记** | 66 | ±0 | **66** |
| **BLOCKED · 待用户** | 2 | ±0 | **2** |
| 合计 | 135 | **+7** | **142** |

**BLOCKED 终值仍是两条，都在用户那一侧**：① **baostock 许可正文** —— `ops/terms/baostock/permission/`
按裁定**保持不存在**；② **`CITATION.cff` 的 `authors` / `date-released`**。本轮没有新增、也没有闭合。

### 本轮**没有**登记进这张表的是什么

① **N-814 / N-795 的断链软链与裁定③ 扫尾** —— 那是**动作**不是限制，闭合之后不留痕（票据里有）；
② **N-782** —— 卡 Q 已按裁定②翻面并提交，本卡只复跑核过（`ops/test_docs_consistency.py` **12 passed**，
本卡新增的那条 fact 已在内），不重复登记；
③ **本轮做成的事** —— 各有票据号，写在 `ops/tickets.md` 本轮那一节。
**没有任何一条本卡发现的问题是「既没修、也没登记、也没交出去」的。**

---

## U（2026-09-13）：外部 clone 上的一条 block 与四条「第一屏就会撞」

> 由来是卡 Tfin（终核卡，只读）**站在外部用户那一侧**做的一次完整复跑：GitHub 上
> `git clone --depth 1` 到一棵全新空目录 → 按手册 §1.2 装外部 3.12 → 照 README §2.1 / §2.1a
> **逐字**搭根落位 → 两次 `ops/selfcheck_public.py` → 定向测试 → 三类扫描。
> 逐条登记在 `ops/tickets_inbox/Tfin.md`，实测输出在 `$GB/scratch/Tfin/`。
> 本卡把**六条全部修掉**并重打树推了一次；三条版本轴（`v1.0.16` / `r1.0.23` / `p1.0.0`）
> 一个值没改，没重算 τ / ε，没重打任何包、没传任何附件、没新建 Release。

### 一条 block（已修）：照 README 建 venv，网关就永远起不来，而文档给的修法是空转

**N-818**。`ops/guard_modes.py` 的 `check()` 与 `harden()` **对符号链接的口径相反**：

* `check()` 走 `_walk_stat`，`mode` 来自 `e.stat()` —— **跟随链接**，读到的是**目标**的权限位；
* `harden()` 在同一趟遍历里 `if islink: continue` —— **跳过链接**（它不替人改目标）。

于是「跟随着判、跳过着修」：只要链接指向根外一个 `0755` 的东西，这道门就
**结构上不可能被 `harden()` 修好**。而 `python3.12 -m venv $GB/env`（README §2.1 与
手册 §1.2 让外部用户敲的那一行）在 POSIX 上默认把 `bin/python`、`bin/python3`、
`bin/python3.12` 建成**符号链接**，最终指向系统解释器（Linux `/usr/bin/python3.12`、
Mac `/opt/homebrew/…`，`0755` 且 root 所有）。链路是：
`check()` 判三条红线 5 违例 → `assert_modes()` 让**网关拒绝启动** →
提示语说「修：`python3 ops/guard_modes.py --harden`」→ `harden()` 打印「收紧 0 个条目」退 1 →
再 check 仍是同样三条。**外部用户在 README 第一步就撞上，而且照提示做是死循环。**

**这一条不属于 D-06 家族里「判据悄悄取决于跑它的那台机器」那一支**（那一支现有五例：
N-748 / N-761 / N-775 / N-809 / N-770，见上一节）。那一支的成因是**一个值**在发布方机器上
恰好落在合规的一侧；这一条的成因是**同一个模块里两个函数对同一条路径给出相反的口径** ——
换任何一台机器都成立，只是发布方那棵 `$GB/env` 是 conda 环境、`python -> python3.10`
指向**同一棵树里**一个已经 `0700` 的实体文件、链条在根内终止，所以内部**恰好踩不到**。
两者的判据也不同：那一支问「把这个值换成别的机器上的值，链路还对不对得上」；
这一条问「**这道门报得出来的东西，它自己的修法修得掉吗**」。

**修法**：`check()` 对**答案面根之外**的符号链接不再按模式判（符号链接自身的模式在 POSIX 上
恒为 `lrwxrwxrwx`、没有意义；目标在根内会以自己的真实路径被同一趟遍历单独判，目标在根外
则是「链接指到哪去了」的问题，归答案面那道门管）。**判别力一个字没降**：根下真实的
`0644` 文件 / `0775` 目录照样判红，`--harden` 照样收得掉。另加 `fix_hint()`：提示语按违例
类别分岔，`--harden` 修不好的三类（答案面软链、读不到模式的断链、轮转配置）**明说修不好**
并给出真能照着做的下一步。

**实测四样**（逐字输出在 `$GB/scratch/U/venv_fix.txt`、`test_U_has_teeth.txt`）：
① 在 `$GB` 之外按 README 逐字建一棵**真 venv** → 旧版 `check` 3 条红 / `--harden` 收紧 0 条 /
再 check 仍 3 条红；新版 `check` 退 0，三条软链**原样留在盘上**（守门不替人删东西）；
② 同一棵树起网关 —— `/healthz` **200**（2 秒起来，`channel=public`、`backend=snapshot`）；
③ 造一个真的 `0644` 文件 + `0775` 目录 → `check` 退 1 并逐条列出 → `--harden` 收紧 2 条 → 退 0；
④ 造一条答案面断链 → 提示语不再说「修：`--harden`」，而是「**`--harden` 修不好**（它不替人
删东西）—— 自己把这些链接删掉，或换成实体文件」。门 `ops/test_U.py`（13 条，含**拿旧版跑一遍**
的反面判别）。

**`--copies` 判了不加**：`python3.12 -m venv --copies` 确实能绕开（实测 `--harden` 收紧 3 条、
check 退 0），但它是**绕**不是修 —— 代码修好之后那个开关没有活的理由，写进文档只会变成
一句没人知道为什么存在的咒语（而多占 ~24 MB）。README / 手册的建 venv 那行一个字没改。

### 四条外部用户第一屏会撞的（都已修）

* **N-819**（major）—— `ops/test_pack_release.py` 的三条在**照文档做对了**的外部 clone 上恒红：
  `_need()` 只守**落位产物**，三件附件落位之后守卫全部放行，接着去调打包器，而打包器要的是
  **打包前的发布方中间件** `$GENEBENCH_ROOT/scratch/v1_union.txt` —— 它既不在仓库也不在三件
  附件里（附件里那份在 `snapshots/public_v1/universe/v1_union.txt`，**路径不同**）。
  于是**落位前 skip、落位后 3 failed**：越照文档做对，越会看到红。修法是把守卫补成
  `_need_packager_inputs()`，清单**从 `PP.components()` 现算**（写死一张表的话，组件加一件就
  又变回同一个坑）。**判别力不变，两面都实测**：f01（发布方）`ops/test_pack_release.py`
  **21 passed / 0 skipped**，三条逐名 `PASSED`；把 `GENEBENCH_ROOT` 指到外部落位根，三条
  `SKIPPED`（理由逐字打出缺的是哪一件）。
* **N-821**（minor）—— `ops/selfcheck_public.py` 找附件的三个候选目录（`cwd/downloads`、
  `$GENEBENCH_ROOT/downloads`、仓库父目录 `/downloads`）在 README 与手册里**一次都没写过**
  （两份文档 `grep downloads` = 0 命中），而 README §2.1a 的 `curl -L -O` 紧接在 §2.1 的
  `cd $REPO` 之后 —— 包落在**仓库根**下，三处一处都不是它。**两边取齐**：仓库根与
  `$GENEBENCH_ROOT` 本身进候选，README §2.1a 也写明了落点。顺带把「找过：…」按**解析后的
  真实路径**去重（`$GENEBENCH_ROOT` 与仓库父目录重合是常态，重合时同一个路径会被打印两遍）。
* **N-822**（minor）—— 只缺 `pyyaml` 时第 5 项的**诊断是错的**：它说「说明这棵树不完整，或者
  你不是在仓库根下跑的」，真因是 `genetask/packager.py:29` 的 `import yaml` 抛
  `ModuleNotFoundError`。**树是完整的、目录也是对的**，用户被支去查一件没坏的事。改成打
  子进程输出的**最后一行**（真正的异常）而不是第一行 `Traceback (most recent call last):`，
  并在识出 `ModuleNotFoundError` / `ImportError` 时直接指回第 2 项。
* **N-823**（minor，Tfin 原判「登记不修」，本卡顺手修了）—— `ops/test_env.py:16` 的 docstring
  仍写「两个附件落位与 sha256」。N-810 修了四处，这是漏掉的第五处，与前四处同口径改成
  「发布附件落位与 sha256」。

### 一条 minor（已修）：`DATA_LICENSE` §3 的现在时假话

**N-820**。标题链「数据许可与来源声明 › `## 3. 发布形态（两条都走通）`」整条链上**没有时点**，
正文却现在时地说「**地址已定不等于已推送**」「`_staging_unpublished/` 里那份旧包的 README
还写着占位符」「**推完要重打一次公开包**」—— 三处都不是现状：树 2026-09-13 已推（读者正是
clone 它拿到这份文件的）、`_staging_unpublished/` 按 N-714 已整棵删除、公开包已重打并挂上
Release。按「值被它所在小节的标题**整节**地标了时点」这条口径，它没被标住，因此是**对外说
假话**而不是留证。已改成现状（句首带 `2026-09-13：` 的显式时点）。同源的一句还在
`ops/mk_release_manifest.py` 的 `closes_when` 里 —— 那一条早由卡 V 登记为 **N-793**，本卡不另开号。

### 本轮登记不修的一条

* **N-824** —— 修完 N-819 之后，`ops/test_pack_release.py` 那三条在**任何外部机器**上都是
  `skip`。这是**有意的落点**：重打 provider 包是发布方的操作，外部用户手里没有打包前的中间件
  （`scratch/v1_union.txt`），也不该有。外部想验包，验的是附件自己的 `sha256`（README §2.1a）
  与包内 `files.sha256`，不是重打一遍。**代价**：外部 clone 上这三条的判别力等于零 ——
  它们只在发布方机器上有牙。记下来，不修。

### 逐类计数（截至 2026-09-13 卡 U 收口）

| 类别 | 上一次盘点（卡 S 收口） | 本轮增减 | **终值** |
| --- | ---: | ---: | ---: |
| **已修 / 已闭**（留证据链） | 57 | **+6**（N-818/819/820/821/822/823） | **63** |
| **设计性限制**（v1 就是这么定义的） | 11 | ±0 | **11** |
| **v1.1**（要改判据或要新证据） | 6 | ±0（arm64 实机构建仍在这一格） | **6** |
| **登记不修 · 量到即记** | 66 | **+1**（N-824） | **67** |
| **BLOCKED · 待用户** | 2 | ±0 | **2** |
| 合计 | 142 | **+7** | **149** |

**BLOCKED 终值仍是两条，都在用户那一侧**：① **baostock 许可正文** ——
`ops/terms/baostock/permission/` 按裁定**保持不存在**；② **`CITATION.cff` 的
`authors` / `date-released`**。本轮没有新增、也没有闭合。

### 本轮**没有**登记进这张表的是什么

① **`--copies` 加不加** —— 那是一条**判断**（判了不加，理由见上），不是限制；
② **本轮做成的事** —— 各有票据号，写在 `ops/tickets.md` 本轮那一节；
③ **推后的终值**（main sha / tag 对象 / 件数）—— 按 **N-743** 不进树，只记进内网
`ops/reports/push_result.md` §8.x。
**没有任何一条本卡发现的问题是「既没修、也没登记、也没交出去」的。**

## W2（2026-09-13）：交付前最后一件 —— 两条会实打实浪费用户时间的 major

> 由来是卡 Vfin（终核卡，只读）**完全照 README 逐字走了一遍外部用户的路**：全新 `git clone`
> → 三个附件 → 起网关 → 三题双臂 → `--table main` 出 24 列。那一趟 **0 block、`tests_ok=true`**，
> 却量出两条 major —— 它们**不挡验收，但会实打实浪费用户的时间**。用户马上要在一台干净 Mac 上
> 重跑一遍，本卡是交付前的最后一件。逐条实测在 `$GB/scratch/W2/`；收件箱原件
> `ops/tickets_inbox/W2.md`。本轮三条版本轴（`v1.0.16` / `r1.0.23` / `p1.0.0`）一个值没改，
> 没重算 τ / ε，没重打任何包、没传任何附件、没新建 Release。

### 一条 major（已修）：README 的第一个代码块，哪一边先敲都会失败

**N-825**。§2. 快速开始的 **§2.1 共同前置**是外部用户**复制粘贴的第一个块**，而
**建 venv 这一步不在块里** —— 它在 §1.5 的另一个块里；§2.1 只在 `PY=` 那一行的**注释**里
写了「venv **必须**建在 `$GB/env`（§1.5）」，**没有给命令**。反过来，§1.5 那个块里的
`python3.12 -m venv $GB/env` 用的 `$GB` **要到 §2.1 第 1 行才被定义**。于是两个块互相依赖，
**两种读法都断**（卡 Vfin 各实测一次，`$GB/scratch/Vfin/readme_order.txt`）：

* 按文档顺序先敲 §1.5 → `$GB` 未定义，`$GB/env` 展开成 `/env` →
  `Error: [Errno 13] Permission denied: '/env'`；
* 直接从 §2.1 逐字敲 → 走到第 6 行 `$PY ops/selfcheck_public.py` →
  `bash: …/env/bin/python: No such file or directory`，下一行 `--harden` 同样。

**这不是死路**（注释指了 §1.5，回去补一句就能往下走），但它是**第一个块**，而且
上一轮的卡 U 与本轮任务书都把那条命令记成「README §2.1 那条」—— 说明它确实会被读成
§2.1 自带。**修法**：把 `python3.12 -m venv $GB/env` 与那条 `pip install` **插进 §2.1 的块**
（`mkdir -p $GB && chmod 700 $GB` 之后、`$PY ops/selfcheck_public.py` 之前），Mac 给全路径
`/opt/homebrew/bin/python3.12`，同一行的注释给出 Intel Mac 与 Linux 的等价写法；
§1.5 那个块改成**自带 `GB=` 定义**、可以单独跑。**两处不再互相指**。

**判据是实测的，不是推理的**（`$GB/scratch/W2/n825_paste.txt`）：在一棵**全新 clone** 上把
改后的 §2.1 代码块**整块复制、逐字粘贴**跑了一遍（唯一替换：第 4 行的
`/opt/homebrew/bin/python3.12` → `python3.12`，依据是**该行自己的注释**「Linux 换
python3.12」，f01 是 Linux、没有 `/opt/homebrew`；`$GB` 照 README 原样取 `$HOME/genebench`）。
结果：全程**一条 `No such file or directory` 都没有**、一条 `Permission denied` 都没有；
`ops/selfcheck_public.py` 跑到底并逐项给出**可读的**六项判定（绿 1 / 红 3 / 跳过 2），
`ops/guard_modes.py --harden` 退 **0**。顺带印证了 README §1.5 早就写着的那句
「Linux 上 `python3 -m venv` 常常缺 `ensurepip`」：f01 的 Ubuntu `python3.12` 正是如此
（**没有 root 的做法在手册 §1.2**），而这**恰好**说明修法是对的 —— 即使 `ensurepip` 缺席、
`pip` 没装上，`$GB/env/bin/python` 已经在，两条 `$PY …` 都**跑起来了**并给出可读的红，
而不是「找不到解释器」。

### 一条 major（已修）：一份门在发布方机器上全绿，而它根本没在看被测的那棵树

**N-826**。`ops/test_d.py:20` 原文 `REPO = Path("/data/shared/genebench/repo")` 是**发布方内网
路径**，`:21-26` 的 `README` / `ATTACH` / `MANIFEST` / `SCAN` / `PUSH` / `PKG_DIR` 全从它派生，
`:34` 还是**模块级** `read_text()`。两头都坏：

* **在任何没有那个路径的机器上**（= 所有外部用户），模块级 IO 在 **collection 期**抛
  `FileNotFoundError` → `Interrupted: 1 error during collection`，**整场中断**而不是一条可读的红。
  `pytest ops/` 也跟着一起中断。
* **更要紧的连带后果**：在发布方机器上跑**克隆树**时，它读的是**内网仓库**的 README / 清单 /
  报告，**不是被测的那棵树** —— 也就是说这一整套断言**对「克隆树对不对」没有判别力**，
  我们前几轮在 f01 上看到的绿**有一部分是假的**。

**修法**：`REPO` 改成 `Path(__file__).resolve().parents[1]`（与 `conftest.py` 的 `_REPO_ROOT`
同一套口径）；`PKG_DIR` 改成跟 `$GENEBENCH_ROOT` 走（没设就按仓库父目录，用它的那条断言本来
就有 `p.exists()` 的 skip）；模块级 `read_text()` 前加一道**整模块 skip** 保护
（`pytest.skip(..., allow_module_level=True)`），缺件时跳过整个模块而不是崩掉整场。

**两面都验了**（`$GB/scratch/W2/n826_clone4.txt`，六段）：

| 段 | 做什么 | 结果 |
| --- | --- | --- |
| (a) | 克隆树上原样跑 | **15 passed / 3 skipped**，不再 collection 崩；三条 skip 的理由里打的是**克隆树自己的**路径 |
| (b) | 把**克隆树自己的** README 里 provider 包的 sha256 改坏一个字符 | **2 failed** —— 判别力在，读的确实是那棵树 |
| (c) | 还原 | 回到 **15 passed / 3 skipped** |
| (d) | 把克隆树的 `README.md` 挪走 | **整模块 skip**（`1 skipped`），**不是** collection 崩 |
| (e) | 旧版（那两行换成不存在的路径）在同一棵克隆树上 | `Interrupted: 1 error during collection` —— 就是外部用户看到的样子 |
| (f) | **旧版原封不动**、克隆树 README 已被改坏 | **17 passed** —— 全绿。这就是「绿是假的」那句话的实证 |

发布方那一侧同样验了：f01 内网仓库上 `ops/test_d.py` 仍是 **17 passed / 1 skipped**，
唯一那条 skip 还是原来那条（`ops/tickets_inbox/D.md` 不在），**没有一条断言变成 skip** ——
判别力一条没丢。

### D-06 家族「判据悄悄取决于跑它的那台机器」那一支：第六例 N-826

这一支此前有五例（N-748 / N-761 / N-775 / N-809 / N-770，定义与前五例见上面卡 S 那一节）。
**N-826 是第六例，它的特殊之处值得单记**：前五例里，走偏的是**一个值**（有没有 remote、
某个文件在不在、两处默认值今天同不同值），坏掉的是**那一条判据**；
而 N-826 走偏的是**一份门的整个根**——于是**整整一套 18 条断言**同时失去了对被测对象的判别力。
它不只是「默认值指错了机器」，而是**这份门根本没在看你让它看的那棵树**，却照样交出一屏绿。
外部那一侧它以 collection 崩的形式**当场显形**（所以看起来像「外部才有的问题」），
内部那一侧它**永远不显形**，因为发布方机器上那个写死的路径**确实存在**、里面确实有一份
内容几乎一样的 README —— **两棵树内容越像，这条 bug 越隐蔽**。
**教训**：一份门的「根」从哪里来，本身就是判据的一部分；根写成绝对路径时，
问题不是「这台机器上有没有」，而是「**它指的是不是我这次要判的那个对象**」。

### 两条 minor（都已修）

* **N-827** —— 文档给的六个包装齐之后，在克隆树根跑 `pytest ops/` 会看到
  **`Interrupted: 5 errors during collection`**（卡 Vfin 实测，`$GB/scratch/Vfin/collect.txt`）：
  `ops/test_artifact_schema.py` / `ops/test_genetask.py` 缺 `jsonschema`，
  `ops/test_gateway.py` / `ops/test_gateway_fields.py` / `ops/test_sim_endpoints.py` 用的
  `starlette.testclient` 缺 `httpx`。**文档从不叫外部用户跑 `pytest ops/`**（手册点名的是单个
  文件），所以这是**加一句话、不是修代码**：README §1.5 的六包清单旁写明「想跑仓库自带的测试
  再装 `pytest`、`jsonschema` 与 `httpx`；只跑 `ops/selfcheck_public.py`、出题、跑题、出表
  不需要它们」，并说清缺它们时报错发生在 **collection 期**（所以是整场中断而不是几条红）。
* **N-793** —— `RELEASE_MANIFEST.json` 的 `blockers[no_clone_url].closes_when` 正文仍引用
  按 **N-714 整棵删除**的 `release/_staging_unpublished/`，对读者是一条指向不存在目录的线索。
  改的是**源**（`ops/mk_release_manifest.py` 那条 blocker 的措辞），按 **N-743** 的口径
  **改措辞不改值**，`satisfied` 那一格一个字没碰，然后重出清单。
  **`PART_OVERRIDES` 拿同一个路径当字典键那一处没动** —— 源码 `:457-464` 写明那是刻意的
  （键用存档件的 `path`，对外正文由该表改写成「已发布」）。

### 本轮登记不修的一条

* **N-828** —— 顺着 N-826 把 `ops/test_*.py` **全文件扫了一遍**同形的写死
  （`$GB/scratch/W2/scan_hardcoded.txt`，按 AST 只看**模块级**语句）。结论：
  **与 N-826 同形的（模块级写死发布方路径 + 模块级 IO）现在是 0 个**；
  另有 **12 个文件**在模块级写死了发布方路径，但**都没有模块级 IO**，所以
  **不会整场中断**（卡 Vfin 在克隆树上的 collection 实测也印证了这一点：崩的只有
  `test_d.py` 与缺包那五个）。逐条分三类：
  * **不是问题**（写死的字符串是**被扫描的对象**，不是判据的根）：`ops/test_A2.py:63`
    的 `_PUBLISHER_PATHS`（它正是用来查文档有没有泄漏发布方路径的）；
    `ops/test_P1.py:8` 与 `ops/test_env.py:31-32`（都在 docstring 里）。
  * **有 env 兜底**（外部设了 `GENEBENCH_ROOT` 就跟着走）：`ops/test_a_publish.py:24`、
    `ops/test_p.py:17`。
  * **判据仍指着发布方机器**（外部上表现为 skip 或红，不是中断）：`ops/test_g2.py:24`
    （发布树）、`ops/test_provider_pin_channel.py:172-173`、`ops/test_public_acceptance.py:42-43`、
    `ops/test_scorer_gate.py:16`、`ops/test_scorer_redteam51.py:33`、`ops/test_x1.py:15`、
    `ops/test_y1.py:24` —— 这七个指的都是**答案面 / 快照 / 发布树**，外部本来就没有，
    而且**都不该有**（红线 2）。
  **本轮只修 `test_d.py`**：它是唯一「整场中断 + 整套判据失去判别力」的那一个。
  其余**登记不修**，代价写在这里：它们在外部 clone 上的判别力等于零，只在发布方机器上有牙
  （与 **N-824** 同一类代价）。

### 逐类计数（截至 2026-09-13 卡 W2 收口）

| 类别 | 上一次盘点（卡 U 收口） | 本轮增减 | **终值** |
| --- | ---: | ---: | ---: |
| **已修 / 已闭**（留证据链） | 63 | **+3**（N-825 / N-826 修，N-793 闭） | **66** |
| **设计性限制**（v1 就是这么定义的） | 11 | ±0 | **11** |
| **v1.1**（要改判据或要新证据） | 6 | ±0（arm64 实机构建仍在这一格） | **6** |
| **登记不修 · 量到即记** | 67 | **+1**（新登记 N-827 / N-828 两条，N-793 闭合移出一条） | **68** |
| **BLOCKED · 待用户** | 2 | ±0 | **2** |
| 合计 | 149 | **+4** | **153** |

**BLOCKED 终值仍是两条，都在用户那一侧**：① **baostock 许可正文** ——
`ops/terms/baostock/permission/` 按裁定**保持不存在**；② **`CITATION.cff` 的
`authors` / `date-released`**。本轮没有新增、也没有闭合。

### 本轮**没有**登记进这张表的是什么

① **Ubuntu 的 `python3.12` 缺 `ensurepip`** —— 那是**本机的事实**，README §1.5 与手册 §1.2
早就写着（含没有 root 的做法），不是本项目的限制；
② **本轮做成的事** —— 各有票据号，写在 `ops/tickets.md` 本轮那一节；
③ **推后的终值**（main sha / tag 对象 / 件数）—— 按 **N-743** 不进树，只记进内网
`ops/reports/push_result.md` §8.x。
**没有任何一条本卡发现的问题是「既没修、也没登记、也没交出去」的。**

---

## Y（2026-09-13）：交付前终核的收口 —— 一条 block、两条 major、三条 minor，外加一道 3.12 冒烟门

> 由来是**卡 Xfin**（交付前终核，只读）：完全照 README 逐字走了一台干净外部机器的路
> （`git clone --depth 1` + 三件附件 + 外部 3.12），报出 **1 block + 2 major + 4 minor**。
> 逐条登记在 `ops/tickets_inbox/Xfin.md`，实测输出在 `$GB/scratch/Xfin/`。
> **用户裁定：三条都修，并且加一道 3.12 冒烟门。**
> 本卡（卡 Y）把 block + 两条 major + 三条 minor 全部修掉、加了那道门并重打树推了一次；
> 三条版本轴（`v1.0.16` / `r1.0.23` / `p1.0.0`）**一个值没改**，没重算 τ / ε，
> 没重打任何包、没传任何附件、没新建 Release。

### D-06 家族「判据悄悄取决于跑它的那台机器」那一支：第七例 N-829

这一支此前有六例（N-748 / N-761 / N-775 / N-809 / N-770 是前五例，定义与成因见卡 S 那一节；
N-826 是第六例，见卡 W2 那一节）。**N-829 是第七例，它的特殊之处是分岔的位置：**

> **前六例的分岔都在「路径」上** —— 有没有 remote、某个文件在不在、两处默认值今天同不同值、
> 一份门的根指着哪棵树。**第七例的分岔在「解释器版本」上。**

发布方 f01 的解释器是 conda **Python 3.10**，而 README §1.5 **强制外部用 3.12** ——
于是**凡是只在 3.11+ 才报的错，我们内部永远照不到**，而且照不到的方式比前六例更彻底：
前六例里那个写死的东西至少**在外部机器上会以某种形式显形**，内部只是恰好合规；
这一例连「同一份文件、同一条代码路径」在两台机器上都是同一份，
**唯一的差别是跑它的解释器自己变了行为**。

具体：`ops/joblist.py:389` 与 `:393` 是**逐字相同的 5 行重复块**，把子命令 `rebudget`
用 `add_parser` **注册了两次**。

* **Python 3.10 的 `argparse` 不查重**，照跑 —— `--help` 里 `rebudget` 打印两遍而已，
  发布方内部**没有任何征兆**；
* **Python 3.11 起 `add_parser` 开始查重**，于是在 README §1.5 强制的 **3.12** 上
  **每次调用**都当场抛 `argparse.ArgumentError: argument cmd: conflicting subparser: rebudget` ——
  `--help` / `gen` / `stat` / `list` / `reset` **全部起不来**。

**代价的量级**：README §2.4「最短路径」的**第 ① 条命令**就是 `ops/joblist.py gen`，
也就是**外部用户照文档敲的第一条命令当场死**；连带把手册 §8.6 明确请他跑的
`ops/test_operator_manual.py` 打红两条（那两个 flag 源码里**真有**，红的原因是判据
shell out 到 `--help` 而 `--help` 崩了）。而内部**任何**测试都照不到它。

**修法**：删掉重复的那一份（先逐字比对两块，确认真的一模一样）。
**判据在真 3.12 上实测**：改前 `--help` 抛；改后 `ops/joblist.py gen --matrix ops/joblists/v1demo.yaml`
打出 **「8 个 job」** 与 `{"pending": 8, …}`，正是 §2.4 承诺的 4 题 × 双臂。

**教训（这一条是本轮加那道门的全部理由）**：
「在我这台上跑得通吗」从来不是判据 —— 而**这一次连「换一台机器」都不够**，
要换的是**解释器版本**。所以门必须分两层：**一层版本无关**（静态查重，3.10 上也抓得到），
**一层真 3.12**（把文档叫用户敲的每个入口跑一次 `--help`）。见下。

### 本轮加的那道门：`ops/test_Y.py`（用户点名）

两层，都在：

* **① 版本无关的那一层** —— 按 **AST** 数每个文件里 `add_parser("<字面量>")` 的名字，
  **同名注册两次就红**。它**在 3.10 上也抓得到本轮这条**，这正是它存在的理由：
  不指望「将来有人在 3.12 上跑一次」。
  判别力**反面自证**（`test_the_duplicate_subcommand_scanner_has_teeth`）：
  往一份真源码的副本里注入一个重复注册 → 当场红；副本销毁、原文件一个字节没动 → 绿。
* **② 真 3.12 的那一层** —— 把**文档里叫用户敲的**每个 `ops/*.py` 入口在一个**真 ≥3.11
  解释器**上跑一次 `--help`（本轮实测覆盖 **19 个入口**）。找不到可用解释器时
  **大声 skip 并把每个候选为什么不行逐条打出来**，不许静默变绿。
  给它一个解释器的办法写在门自己的 docstring 与 `ops/tickets.md` 卡 Y 那一节：
  `GENEBENCH_PY312=<解释器> $PY -m pytest ops/test_Y.py -q -rs`。

**顺带把射程铺开扫了一遍**：`ops/` `runner/` `gateway/` `scorer/` `snapshots/` `genetask/`
下**所有** 40 个带 argparse 的非测试脚本，在真 3.12 上逐个 `--help` ——
**除了 `ops/joblist.py` 这一条，其余 40 个全部正常**（`$GB/scratch/Y/cli_scan_312.txt`）。
全树重复 `add_parser` 也**只此一处**。

**发布前必须在有 3.12 的环境上跑一次这道门。** 发布方 f01 的 `$GB/env` 是 conda 3.10，
在它上面跑等于没验 —— 那时候 19 条会**全部 skip**，而 skip 不是绿。

### 两条 major（都已修）

* **N-830 —— README §2.4 的两条 `run_joblist` 没带 `--channel public`，外部用户会静默跑私有题集。**
  `ops/run_joblist.py --channel` 的**默认值是 `private`**，于是干跑打出来的题集根是
  `$GB/reference/tasks/v1.0-smoke` —— 那是**私有题集**，按红线 2 **永远不随发布件交付**；
  外部用户手上只有第三件附件带来的 `$GB/reference/tasks/public/v1.0-smoke-public`。
  **最贵的地方是它不报错**：② 干跑照私有根把六段命令原样渲染出来（看起来一切正常），
  要到 ④ 真跑才报「找不到任务目录」。
  （两个开关只给一个时工具会当场拒绝并把正确命令打出来，写得很好 —— **一个都不给才是那条静默的路**。）
  **修法**：块首加 `export GENEBENCH_CHANNEL=public`，两条 `run_joblist` 各加 `--channel public`，
  并在 §2.4 写明**为什么外部用户必须带它**；手册 §5.4 与 §6.1 各补一段同口径的提醒
  （手册 §5 / §6 的示例命令用的是 `<batch>` 占位、面向内部默认通道，所以补的是提醒而不是改命令）。
  **判据**：`ops/test_Y.py` 钉住「§2.4 里每条 `run_joblist` 都带 `--channel public`」
  + 「`--channel` 的默认值仍是 `private`」（默认值一旦变了，那段解释就成了假话）。
  实测：带上之后题集根立刻变成 `…/public/v1.0-smoke-public`，`v1demo.yaml` 那四道题
  （s1/s2/s3/s5-cor-01）在公开题集里**都在**。
* **N-831 —— `ops/run_joblist.py:70` 与 `ops/score_runs.py:49` 的 `F02` 写死且没有 env 兜底，
  而两处文档的「要改哪些常量」表都没列它们。**
  全仓库只有 `ops/api_usage.py:51` 写了 `os.environ.get("GENEBENCH_F02", …)`。
  卡 Xfin 实测：设了 `GENEBENCH_F02=me@127.0.0.1` 之后，§2.4 ④ 干跑里的 ssh 目标
  **仍然是发布方那台** —— 单机 Mac 用户只能改源码，而**他无处得知要改哪两行**。
  **修法**：两处都补同一套口径的 env 兜底；README §2.3 补第 ④ 条、手册 §1.3 那张表补两行，
  两处都写明**读这个变量的一共五个入口**（两个推送 `.sh` + `api_usage.py` + 这两个）。
  **发布方那台的取值逐字不变**，由 `ops/test_Y.py` 两条断言钉住（不设 env 时必须仍是原值；
  设了 env 时两处都跟着走）。

### 三条 minor（都已修，都在用户第一小时的路径上）

* **N-832 —— README §2.1 把 `selfcheck` 排在 `guard_modes --harden` 前面，首跑第 6 项必红。**
  venv 按 README 自己的硬要求建在 `$GB/env`，`pip` 装出来的 `.so`/`.py` 对组/其它开放，
  而红线 5 审计走 `$GB` **全树** —— 卡 Xfin 实测：**113 条「模式放松」、网关拒绝启动、
  `selfcheck` 退 1**；第 9 行 `--harden` 一跑就收干净（「收紧 113 个条目」），
  再跑 `selfcheck` 就是**绿 5 / 红 1**（剩下那条红是那台机器真没装 docker）。
  红条自己的「修：」提示指的就是下一行，所以**自带导航**；但**块跑完最后停在一个退 1 的自检上、
  没人叫他复跑**，容易让人以为没过。Mac 上 umask 022，命中条数只会更多。
  **修法**：把两行**对调**（先收紧、再自检），并在块后写明为什么是这个顺序、
  以及「你要是已经先跑了 `selfcheck` 看到一屏红，别急着查环境」。
  选对调而不是在块尾补一行复跑，理由是**照抄的人少跑一次没有意义的红**。
  判据：`ops/test_Y.py::test_the_readme_hardens_before_it_selfchecks`。
* **N-834 —— README 与手册都引 `ops/reports/d2_e2e/` 当证据目录，而那个目录不在树里。**
  那段话正是用来劝用户「**别把一批 run 大半撞闸读成自己配错了**」的 —— 证据却不在他手上。
  **修法选「把证据放进来」而不是改措辞**：那段劝解只有连着分布一起读才站得住。
  **只放两张小表 + 一份题注**（`run_states.csv` 六行终态、`table_main_excerpt.csv` 表头与两行、
  `README.md` 说明它是**构造验收不是能力读数**）；run 产物、bundle、日志、题面与答案面
  **一个字节都不在里面**（红线 2）。`run_id` 去掉了机器标识后缀。
  摘录那张表的文件**刻意不叫 `table_main.csv`** —— 那个名字是 `ops/test_V2.py::_main_table_dirs()`
  用来**认批**的（认出来就要求同目录还有六件全量指标表），而 `d2_e2e` 不是批的产物目录；
  本卡第一次提交时就是被这道门当场拦下的，**那条红是对的**，所以改名而不是往证据目录里塞表。
  判据三条（`ops/test_Y.py`）：目录与三件文件在；**盘上那六行的终态分布 == 两处文档写的分布**
  （两边分叉时红的是文档）；表头**恰好 24 列**、前五列是身份列、且**没有总分列**。
* **N-833 —— `ops/test_readme.py` 与 `ops/test_operator_manual.py` 把「文档说了真话」的路径判红。**
  两处判据把文档里出现的路径**一律**当仓库相对路径去 `exists()`，可有几条**按设计就不在仓库里**：
  `snapshots/public_v1` 与 `reference/tasks/public/…`（落在 `$GENEBENCH_ROOT` 下，附件解开才有）、
  `reference/memory_probe_answers`（README 原话就是「**不在这个包里** ——
  记忆探针的钥匙一旦公开就立刻失效」）。**文档说的是真话，判据照样判红**，
  而它打出来的话是「README 里提到 X，但仓库里没有它。要么改 README，要么这次移动漏了一处」——
  会把人支去找一个不存在的遗漏。而手册 §8.6 **正是明确请外部用户跑后者**。
  **修法是收窄射程，不是放宽判据**：加一张**逐字闭集** `RUNTIME_ONLY_PATHS`（四条，各带「为什么不在」），
  表里那几条**不是不判、是换根判** —— 设了 `GENEBENCH_ROOT` 且那里真有就是一条**正判**，
  没设或还没落位才 skip 并把原因说全（不静默变绿）。
  **两条反面判据**证明没有被放宽：① 拼错一个字母（`snapshots/public_v2`）、换一层
  （`reference/tasks/publik`）、或多一层（`snapshots/public_v1/qlib_provider`）**照样判红**；
  ② 豁免表里每一条都得是 README 或手册**真的提到过**的，否则它是一条没人用的放宽。
  文档将来提到新的运行期路径时这道门会红到有人显式加进来为止，**这是刻意的**。

### 顺手修掉的一条同族缺陷：N-837

`ops/test_operator_manual.py::test_the_gateway_lock_path_in_the_manual_is_the_real_one`
原来写成 `GL.LOCK.relative_to(cfg.GENEBENCH_ROOT)` —— 在发布方机器上两者同根、跑得通；
在**任何**外部机器上 `GL.LOCK` 是写死的发布方绝对路径、`cfg.GENEBENCH_ROOT` 是用户自己的根，
于是 `relative_to` 抛 **`ValueError` 当场崩**（卡 Xfin 实测），而手册 §8.6 恰恰请用户跑这个文件。
**这是第七例同一族的又一个实例，只不过它在判据侧。**
**判据要验的东西一个字没放宽**：改成按「根之下那一截」比 —— 在发布方机器上两种算法**逐字同值**，
换任何一台机器它也照样有牙（手册把 `locks/` 写成别的，当场红）。
`ops/gateway_lock.py:34` 的 `LOCK` 自己写死发布方绝对路径是**另一件事**（代码侧，
不在本卡可改路径），**登记为 N-838**。

### 实测：外部 clone + 真 3.12 上的前后对照

同一棵外部 clone（`git clone` 的树 + 三件附件已落位）、同一个真 3.12 解释器：

| | 卡 Xfin 量到的（改前） | 本卡改后 |
| --- | --- | --- |
| `ops/joblist.py gen`（README §2.4 第 ① 条） | **抛 `ArgumentError`**，`--help`/`gen`/`stat`/`list`/`reset` 全起不来 | **「8 个 job」**，`{"pending": 8, …}` |
| `ops/test_readme.py` | **4 红** | **全绿**（两条运行期路径在 `$GENEBENCH_ROOT` 下被**正判**，只 1 条 skip） |
| `ops/test_operator_manual.py` | **5 红**（含 1 条 `ValueError` 崩） | **全绿** |
| `ops/test_Y.py`（本轮新增） | —— | **全绿**，19 个文档点名的 CLI 在真 3.12 上逐个 `--help` |
| 三个文件合计 | 9 红 | **443 passed / 2 skipped / 0 failed** |

证据：`$GB/scratch/Y/clone_check.txt`、`$GB/scratch/Y/cli_scan_312.txt`。

### 逐类计数（截至 2026-09-13 卡 Y 收口）

| 类别 | 上一次盘点（卡 W2 收口） | 本轮增减 | **终值** |
| --- | ---: | ---: | ---: |
| **已修 / 已闭**（留证据链） | 66 | **+7**（N-829 / N-830 / N-831 / N-832 / N-833 / N-834 / N-837） | **73** |
| **设计性限制**（v1 就是这么定义的） | 11 | ±0 | **11** |
| **v1.1**（要改判据或要新证据） | 6 | ±0（arm64 实机构建仍在这一格） | **6** |
| **登记不修 · 量到即记** | 68 | **+2**（N-835 / N-838） | **70** |
| **BLOCKED · 待用户** | 2 | ±0 | **2** |
| 合计 | 153 | **+9** | **162** |

**BLOCKED 终值仍是两条，都在用户那一侧**：① **baostock 许可正文** ——
`ops/terms/baostock/permission/` 按裁定**保持不存在**；② **`CITATION.cff` 的
`authors` / `date-released`**。本轮没有新增、也没有闭合。

### 本轮**没有**登记进这张表的是什么

① **那道 3.12 冒烟门本身（N-836）** —— 那是**动作**不是限制，不占计数（与 N-814 / N-795 同例），
票据里有；② **本轮做成的其余事** —— 各有票据号，写在 `ops/tickets.md` 本轮那一节；
③ **推后的终值**（main sha / tag 对象 / 件数）—— 按 **N-743** 不进树，只记进内网
`ops/reports/push_result.md` §8.x。
④ **N-370（本轮又撞到一次，按「更新」写进票据，没有重新发号）** —— 定向测试里那条 `ops/test_env.py::test_no_api_key_material_in_run_dirs` 的红：
三条 offender **全部**落在 `$GB/scratch/Xfin/clean/` 那棵 clone 里 `ops/test_env.py` **自己的夹具**上
（那棵树 2026-09-13 19:52 建，**早于本卡开工**；`$GB/scratch/Y/` 下 0 条）。
成因是**扫描器自指**：射程是 `$GENEBENCH_ROOT/scratch`，而终核卡按口径在那底下 clone 了一整棵树。
**那是发布方本机的运维遗留物，不是发布件的问题** —— 与 D2 那一轮「f02 上遗留的僵尸任务容器」
同类，所以同样不占本表计数，只进票据。**而且它本来就登记过** —— 卡 4.rt 的 **N-370**（`ops/tickets.md:4964`，finding 12，判「登记不修」），本轮是**复现**不是新发现，
所以票据里写成「N-370 更新」。发现它已有号的是本轮的过期口径扫描。
**没有任何一条本卡发现的问题是「既没修、也没登记、也没交出去」的。**

---

## C9（2026-09-14）：交付终核那四条 block 的**文档侧** —— D-06 第八例 + 两条清理

> 由来是**卡 Zfin**（交付终核，只读；收件箱 `ops/tickets_inbox/Zfin.md`）：在干净 Mac 的语义下
> 完全照 README 逐字走了一遍。**前半段（clone → 三件附件 → 起网关）走得通**；
> **从 README §2.4 ③ 的真跑开始走不通**，量到 **4 条 block**（N-840 / N-841 / N-842 / N-838）
> 加 2 条 major、4 条 minor。
> **用户 2026-09-14 的裁定分两半**：代码侧（把单机形态实现成一条不含跨机步骤的路径、
> 其余的根从 `GENEBENCH_ROOT` 现算、加一道「不许访问 `/data`」的门）归另一张卡；
> **本卡只做文档与登记那一半**（裁定 ④⑤ 与两条清理）。
> 本卡**没有改任何 `.py` 与脚本**，没有重打树、没有推、三条版本轴（`v1.0.16` / `r1.0.23` / `p1.0.0`）
> 一个值没碰，没重算 τ / ε。

### D-06 家族「判据悄悄取决于跑它的那台机器」那一支：第八例（用户点名）

这一支此前有七例（N-748 / N-761 / N-775 / N-809 / N-770 是前五例，定义与成因见卡 S 那一节；
N-826 是第六例，见卡 W2 那一节；N-829 是第七例，见卡 Y 那一节）。
**第八例的特殊之处，还是分岔的位置：**

> **前七例的分岔都在「值」上** —— 有没有 remote、某个文件在不在、两处默认值今天同不同值、
> 一份门的根指着哪棵树、跑它的解释器是哪个版本。
> **第八例的分岔在「这台机器能不能把那个值变成真的」上。**

具体是这四条（逐条量到的现场在 `ops/tickets_inbox/Zfin.md`）：

* **N-840** —— `ops/push_exec_to_f02.sh:29/:32` 的 `GENEBENCH_PY` / `GENEBENCH_EXEC_STAGE`
  默认值是**发布方那台的绝对路径**，而这两个变量在 `README.md`、`docs/OPERATOR_MANUAL.md`、
  `ops/HANDOFF.md` 里 grep 命中 **0 次**；实测 **rc=127**。
* **N-841** —— `ops/run_joblist.py:77` 的 `RUNNER_ROOT = "/data/genebench_runner"` **没有 env 兜底**，
  而 `ops/push_bundle_to_f02.sh:69-70` 把「目标必须在 `/data/genebench_runner/` 下」写成**硬判据**。
* **N-842** —— `ops/push_bundle_to_f02.sh:36-42` 推前必须 `ssh` 到执行面核
  `systemctl --user is-active genebench-answer-plane-scan.timer`，**手册 §1.3 (3) 自己写着
  「Mac 上这条过不去」，而脚本没有任何绕过开关**。
* **N-838** —— `ops/gateway_lock.py:34` 的 `LOCK` 写死 `/data/shared/genebench/locks/`，
  而真跑**每个 job** 都进这个上下文。

**为什么这四条在内网一次都没显形 —— 这才是本例要记的东西。**
它们**不是**「内部恰好合规」那种躲法（前七例多半是那样）：
这四条写死的路径在发布方机器上**确实存在**，而在任何一台外部 Linux 上，
只要**有 root**，一条 `sudo mkdir -p /data/genebench_runner` 就把它们**造出来了** ——
于是「换一台机器」这个惯用的检验手段**照样照不到**。
卡 D2 那一轮的端到端正是这么走过去的，它自己的收尾记着「为绕开写死路径建的
`/data/shared/genebench` 已整棵删掉」：**绕过去的那一下，就是这条 bug 唯一一次露头的机会，
而它被当成了施工现场的清理，没有被当成缺陷。**
**macOS 自 Catalina 起根卷只读**：`sudo mkdir /data` 直接 `Read-only file system`，
要造得动得写 `/etc/synthetic.conf` 再**重启**。于是同一份代码在 Mac 上是硬停，
而在**每一台** Linux 上（包括「干净的外部 Linux」）都是绿的。

**教训**：判据里出现绝对路径时，前七例教我们问「它指的是不是我这次要判的那个对象」；
第八例要再问一句 —— **「这台机器允不允许我把它造出来」**。
凡是「只要 `mkdir` 一下就好了」的绕法，绕的那一下本身就是证据：
**那条路径不该由环境提供，它该由 `GENEBENCH_ROOT` 现算。**
用户 2026-09-14 裁定 ③ 要的那道门（`GENEBENCH_ROOT` 指向临时目录、**且不允许访问 `/data`**
的条件下跑通 clone → 三件附件 → 起网关 → 出集 → 一个 job → 出表；判据是**单机路径上
`/data` 字面量出现零次**）就是照着这一条设的 —— 它**不必等 Mac**，
因为要堵的从来不是「Mac 特有」，而是「Linux 上造得出来」。

### 本卡修掉的两条（都在文档侧）

* **N-839（major）—— README §2.1a 的验包块用 `sha256sum`，而两处文档从没说过 Mac 上换成什么。**
  **动作照做了，前提被实测改了一半，这一条值得连着读。**
  Zfin 报的前提是「干净 macOS 上没有 `sha256sum`」。本卡 2026-09-14 在一台
  **macOS 15.7.4（Darwin 24.6.0，arm64）** 上逐例量了一遍，结论是：
  **`/usr/bin` 里确实没有，但 `/sbin/sha256sum` 在，而且是 Apple 自己签的**
  （`codesign` 报 `com.apple.md5sum`，`--version` 报 `sha256sum (Darwin) 1.0`，
  与 `/sbin/md5sum` / `/sbin/sha512sum` 是同一个多名二进制），**不是** GNU coreutils；
  `/sbin` 在 macOS 默认 `PATH` 里，所以 §2.1a 那几条命令**在那台机器上原样能跑**。
  逐例实测两者对我们要做的事**等价**（匹配 → `OK` 退 0；不匹配 → `FAILED` 退 1；文件不在 → 退 1），
  **只有一处不等价**：校验和行本身写坏时 **GNU 退 1、Apple 那个退 0**。
  **那 N-839 还算不算问题？算 —— 但它的内容换了**：不是「命令不存在」，
  而是**两处文档一个字都没说过 Mac 上这件事**（全仓库 `shasum` / `coreutils` 此前出现 0 次），
  而 §1.5 那句「macOS 上没有这**四**个 Linux 工具」读起来是穷举的；
  加上 `sha256sum` 既不是 POSIX 也不是 BSD 命令，**「一定在」的只有 `shasum`**。
  **修法**：① §1.5 补成**五个**，并把上面这些**当天量到的**逐条写进去（包括那处退出码差异
  与「为什么这张表现在是全的」—— 2026-09-14 把 README 所有命令块里的命令逐个过了一遍，没有第六个）；
  ② §2.1a 那个要逐字粘贴的块改成**两边通用**，§2.1 注解、§2.3 状态框与手册两处一并给出；
  ③ 点明 `ops/selfcheck_public.py` 的**第 4 项是纯 Python 的等价物**，两个命令一个都不依赖。
  **顺带量到并写进块里的一条真陷阱**：Zfin 与本卡第一版都想写成
  `SUMC="sha256sum -c"` 再 `$SUMC <文件>` —— **在 macOS 上这一定失败**，
  因为 **zsh（Mac 的默认 shell）不对未加引号的变量做词分割**，
  它会去找一个名叫「`sha256sum -c`」的命令（实测 `command not found`）。
  所以块里落的是一个 `sumc()` **函数**，不是变量。

* **顺带记一条方法上的教训（不占计数，但和本节 D-06 第八例是同一个形状）。**
  Zfin 那条「干净 macOS 上没有 `sha256sum`」不是量出来的：它来自
  `$GB/scratch/Zfin/z_mac.py` 里一张**硬编码的候选表**（`(r'sha256sum', 'macOS 无；等价 shasum -a 256')`），
  脚本自己的 docstring 写着「**只列待判项，判据由人写**」，
  而那张卡**从头到尾跑在 f01（Linux）上、一次都没连过 Mac**，候选就这样升格成了结论。
  **形状与第八例一模一样**：一条关于「另一台机器」的判断，完全在**这一台**机器上做出，
  而它在这一台上**永远不显形**。**教训**：候选表升格成结论要有一次真的在目标机器上的测量；
  拿不到目标机器时，结论要写成「未量」，不要写成「没有」。
* **N-843（major）—— README §2.3 的 Mac 状态框里两条成因都已经不成立。**
  旧版原话（逐字留证）：「**macOS（arm64）上还没跑通**：2026-09-13 的外部验收走到
  「建 harness 镜像」就停了 —— 本机没有统一基座 `gb-base:bookworm-r1`，公开题集 S4–S7
  那 18 道题的输入夹具也没有随两个附件交付。」两条**同日都已补上**：`build/base/` 随树发了
  （`harnesses/build.sh` 缺基座时自己构），S4–S7 的 18 道题在第三件附件带来的公开题集树里。
  措辞是过去时、**逐字不算说假话**，但一个新读者读到的是「这两件事挡着」，
  照着去补完，撞上的是上面那四条**一条都没被提到**的墙。
  **修法**：**结论保留**（Mac 侧只验到网关），**成因换成真正的那一条**（单机路径上的跨机步骤），
  旧版原文用「」引起来留证，README §2.3 与手册 §0.3 **两处一起改**。

### 两条清理（用户明示）

* **`$GB/scratch/Xfin/clean/` 已清出 `$GB`。** 它是卡 Xfin 那一轮终核按口径在 `$GB/scratch`
  下 clone 的一整棵仓库树（34 MB），也是**红线 3 那道门唯一那条红（N-370）的全部来源** ——
  扫描器扫到的是那棵树里 `ops/test_env.py` **自己的反面夹具**（`sk-…` 与长 base64 两条样本，
  写在仓库里是**刻意**的：门要有东西可抓）。
  清之前先确认那一轮**已收口**（卡 Xfin 的报告与卡 Y 的修复都已提交）。
  按 §19.8 的纪律**选「移」不选「删」**：整棵移到 `/home/ljn/genebench_scratch/Xfin/clean/`，
  **一个字节没删**，并 `chmod -R go-rwx`。
  **实测转绿**：`ops/test_env.py` 从「1 failed」变成 **63 passed / 1 skipped**（`$GB/scratch/C9/env.log`）。
  **N-370 这一条本身仍是「登记不修」**：清掉的是这一次的 offender，
  而「扫描器射程包含 `$GB/scratch`、于是任何一棵仓库副本落进去都会把它拖红」这个成因没变
  （N-370 原条给的修法、加上卡 Y 补的那条「见到 `.git/` 就不下钻」，都还摆在那里）。
* **`ops/test_Y.py` 保留在常规套件里**（用户明示）。它的第 ② 层在**真 ≥3.11 解释器**上把
  文档点名的每个 CLI 入口跑一次 `--help`，在发布方 f01 的 conda 3.10 上会**整层 skip** ——
  「那一条」指的就是这个。**用户的裁定是：40 个带 argparse 的脚本在真 3.12 上全扫一遍，
  这个结果比修掉那一条 skip 值钱。** 已写进 `ops/HANDOFF.md` 的「接手先跑这几条」，
  连同怎么给它一个 3.12 解释器的照抄命令。

### 逐类计数（截至 2026-09-14 卡 C9 收口）

| 类别 | 上一次盘点（卡 Y 收口） | 本轮增减 | **终值** |
| --- | ---: | ---: | ---: |
| **已修 / 已闭**（留证据链） | 73 | **+2**（N-839 / N-843，都在文档侧） | **75** |
| **设计性限制**（v1 就是这么定义的） | 11 | ±0 | **11** |
| **v1.1**（要改判据或要新证据） | 6 | ±0（arm64 实机构建仍在这一格） | **6** |
| **登记不修 · 量到即记** | 70 | ±0 | **70** |
| **BLOCKED · 待用户** | 2 | ±0 | **2** |
| 合计 | 162 | **+2** | **164** |

**这张表只入账本卡自己闭掉的两条。** 代码侧那四条 block（N-840 / N-841 / N-842 / N-838）
与其余三条 minor（N-844 / N-845 / N-846 / N-847）**由做它们的那张卡各自入账**，
下一节的「上一次盘点」应当从 **164** 起算。
**`N-838` 现在仍计在「登记不修」那一格里**（卡 Y 收口时放进去的）——
它被修掉的时候要从那一格**减一**、往「已修 / 已闭」**加一**，合计不变。

**BLOCKED 终值仍是两条，都在用户那一侧**：① **baostock 许可正文** ——
`ops/terms/baostock/permission/` 按裁定**保持不存在**；② **`CITATION.cff` 的
`authors` / `date-released`**。本轮没有新增、也没有闭合。

### 本轮**没有**登记进这张表的是什么

① **两条清理本身** —— 一条是**运维动作**（把别人的 scratch 移出 `$GB`，不是发布件的缺陷，
与 §19.8 那一轮同类），一条是**裁定**（`ops/test_Y.py` 留在常规套件里）；各有票据号，不占计数。
② **代码侧那四条 block 与四条 minor** —— 见上一段，归做它们的那张卡。
③ **推后的终值**（main sha / tag 对象 / 件数）—— 按 **N-743** 不进树，只记进内网
`ops/reports/push_result.md` §8.x。
**没有任何一条本卡发现或经手的问题是「既没修、也没登记、也没交出去」的。**

## D9（2026-09-14）：单机形态这一轮的收口 —— 这张表把四张卡的账**一次结清**

> 由来见上一节（卡 C9）与 `ops/tickets.md` 的「卡 D9」一节。本轮四张卡：
> **A9** 代码侧（裁定 ①②）、**B9** 那道门（裁定 ③）、**C9** 文档侧（裁定 ④⑤）、**D9** 收口与推送。
> 卡 C9 那一节明写「**代码侧那四条 block 与其余四条 minor 由做它们的那张卡各自入账，
> 下一节的上一次盘点应当从 164 起算**」—— 本节就是那个「下一节」，**把它们全部入账**。

### 这一轮结束时，单机形态到底能不能用（**一句话，不修饰**）

**能走到「落位」，走不到「表」。** 卡 B9 在一台**零遗留物**的机器上按外部单机用户的语义
真走了一遍：`clone` → 三件附件逐件核 `sha256` → `--harden` + 起公开通道网关（`/healthz` 200、
`channel=public`、绑显式地址）→ 用仓库 `build/base/` 现构基座与 harness → 出集 → **单机本地落位**
（**0 次 ssh、0 次 `/data` open**、落点全 0700）—— **前五步全绿**。
**第六步（跑一个 job）在未改动的树上跑不通**，被 **N-855 / N-856 / N-857 / N-862** 四条挡住
（外加 N-858 那条要机器主人加的防火墙规则）。打三个**只在测试克隆里**的最小本地补丁之后
整条路走到了表（`table_main.csv` **24 列**，表头与 README §2.4 逐字相同），
但那一跑 `exit=124`、**不是能力读数**。

**所以对外只能这么说**：单机形态**这一轮变成了一条不含任何跨机步骤的路径**（这是裁定 ①②
要的东西，已落地并有门钉着），**但它还没有在任何一台机器上从头跑到表**。
README §2.3 那句结论（**Mac 上验到网关为止**）**不变**。

### 本轮**新增的四条只在单机显形**的，形状比 D-06 第八例更窄

第八例说的是「这台机器**能不能造出**那个路径」。本轮这四条说的是另一件事：

> **这台机器上正好有一份上一轮留下的东西，于是判据看起来全对。**

* **N-855**：`/data/genebench_runner/provider/qlib_provider_f7dda289` 在 f02 上**存在**（双机遗留）
  → 在 Linux 上表现为「跑起来 ok，只是**读了另一棵树**」，**连报错都没有**。
* **N-856**：`exec/vendor/h11` 不在仓库里，f02 上那份是**手工铺的遗留物**
  （`ops/push_exec_to_f02.sh:60` 自己写着「h11 是在 f02 上就地铺的」）。
* **N-857**：f02 上那棵 exec 树是 **2026-09-10 的旧版**，正好躲过一个**会打断双机生产**的 import。
* **N-862**：run 目录在双机形态下落在 `$GENEBENCH_ROOT` **之外**，P0 看不见；单机形态下落在**里面**。

**合起来是一句方法上的话**：「换一台机器」这个检验手段，在 Linux 上被 `mkdir` 破掉（第八例），
**在同一台机器上被「跑过一轮留下的东西」破掉**（本轮这四条）。
唯一照得到它们的做法是**在一棵干净树 + 一个干净执行面根上跑** —— 卡 B9 就是这么做的，
而这件事**此前从来没做过**：连 2026-09-13 那次「没有任何遗留物」的强实证也只换了**数据面**那棵树，
执行面用的仍是 f02 上那套。**建议把这一条记成 D-06 家族第九例**（判据取决于「这台机器上
有没有上一轮留下的东西」），本卡按 C9 那一节的体例先记在这里，不重排既有编号。

### 逐类计数（截至 2026-09-14 卡 D9 收口）

| 类别 | 上一次盘点（卡 C9 收口） | 本轮增减 | **终值** |
| --- | ---: | ---: | ---: |
| **已修 / 已闭**（留证据链） | 75 | **+5**（N-840 / N-841 / N-842 新入账 + N-865 本卡修；**N-838 从「登记不修」挪过来**） | **80** |
| **设计性限制**（v1 就是这么定义的） | 11 | ±0 | **11** |
| **v1.1**（要改判据或要新证据） | 6 | ±0（arm64 实机构建仍在这一格） | **6** |
| **登记不修 · 量到即记** | 70 | **+20**（新入账 21 条 − N-838 挪走 1 条） | **90** |
| **BLOCKED · 待用户** | 2 | ±0 | **2** |
| 合计 | 164 | **+25** | **189** |

**这一轮为什么一次涨了 24 条**：卡 C9 明写那八条（N-840…N-847）「由做它们的那张卡各自入账」，
而卡 A9 / B9 的收件箱只写了票、**没有动这张表**（按并发施工规则，表归收口卡）。
本节把 **N-840 … N-866** 一次结清，**没有一条是重复入账的**（逐条对过 `ops/tickets.md`）。

**顺带修好一条此前就红的**：`ops/test_wrapup.py::test_新发的号连号_不与旧节撞号` 在**未改动的 HEAD**
上就是红的（发号缺 840 / 841 / 842 —— 那三条卡 Zfin 发了号却从没进过 `ops/tickets.md`）。
本节补齐之后 **475..865 连号无缺、与旧节零撞号**。同文件还有一条红**刻意没修**，见 **N-866**。

**逐条归格**（便于复核，两列各自逐类相加 == 各自合计）：

* **已修 / 已闭（+5）**：`N-838`（从「登记不修」挪来，合计不变）、`N-840`、`N-841`、`N-842`、`N-865`。
* **登记不修（新入账 21）**：`N-844` `N-845` `N-846` `N-847`（卡 Zfin 的四条文档 minor，**本轮没人做**）、
  `N-848` `N-849` `N-850` `N-851` `N-852` `N-854`（卡 A9）、
  `N-855` `N-856` `N-857` `N-858` `N-859` `N-860` `N-861` `N-862`（卡 B9）、
  `N-863` `N-864` `N-866`（卡 D9）。
* **不占计数的**：`N-853`（是**实现记因**不是限制，与 `N-836` 同例）、
  `N-836 更新` / `N-370 更新` / `N-838 挪格`（都是对既有条目的更新，不发新号也不加计数）。

**BLOCKED 终值仍是两条，都在用户那一侧**：① **baostock 许可正文** ——
`ops/terms/baostock/permission/` 按裁定**保持不存在**；② **`CITATION.cff` 的
`authors` / `date-released`**。**本轮没有把「等用户裁」的那几条塞进这一格** ——
它们（要不要为 N-857 现在动手、要不要一条 `ufw` 的 root、N-851 排不排 v1.0.17）
是**施工排期**上的问题，不是发布件上「缺一份东西」的问题，所以按票据交出去、不改这个数。

### 本轮**没有**登记进这张表的是什么

① **卡 B9 在 f02 上留下的部署树与两个镜像 tag** —— 是**运维现场**，不是发布件的缺陷；
按 `ops/HANDOFF.md` §19.8「移，不要删」的纪律处理，归属与清理时机记在票据里。
② **第 ③层「把 `/data` 真遮掉」做不到** —— 那是**本轮那道门的射程边界**，
已经写成 `ops/test_single_machine.py` 里一条**会跑的**记录（哪台机器上
`unshare -r -m true` 退 0，它就会打印怎么跑更强的那一版），不是发布件的限制。
③ **推后的终值**（main sha / tag 对象 / 件数）—— 按 **N-743** 不进树，
只记进内网 `ops/reports/push_result.md` §8.x。
**没有任何一条本轮发现或经手的问题是「既没修、也没登记、也没交出去」的。**

## I10（2026-09-14）：这一轮的收口 —— 四张卡并表 + 重跑单机门到第七步 + Release 正文 + 重打树推

### 逐类计数（截至 2026-09-14 卡 I10 收口）

| 类别 | 上一次盘点（卡 D9 收口） | 本轮增减 | **终值** |
| --- | ---: | ---: | ---: |
| **已修 / 已闭**（留证据链） | 80 | **+20**（新入账 12 条 + 从「登记不修」挪来 8 条） | **100** |
| **设计性限制**（v1 就是这么定义的） | 11 | ±0 | **11** |
| **v1.1**（要改判据或要新证据） | 6 | **+2**（`N-880` 新入账 + `N-849` 从「登记不修」挪来，用户裁定 ②） | **8** |
| **登记不修 · 量到即记** | 90 | **+2**（新入账 11 条 − 挪走 9 条） | **92** |
| **BLOCKED · 待用户** | 2 | ±0 | **2** |
| 合计 | 189 | **+24** | **213** |

### 本轮（2026-09-14，卡 I10 收口）新登记与改判的

**新入账 24 条 = `N-867` … `N-890`**（卡 Efin 的 13 条此前只在收件箱里、从没进过票据表，
本轮一并结清；`N-880` … `N-889` 是本轮续编的）。逐条归格：

* **已修 / 已闭（新入账 12）**：`N-867` `N-868` `N-869` `N-870` `N-871` `N-872` `N-873`
  `N-874` `N-875` `N-876` `N-878`（文档那批，卡 H10 三次提交 + `N-875` 由**本卡** PATCH
  Release 正文落地）、`N-881`（全新执行面根 0775，卡 F10）。
* **从「登记不修」挪进「已修」（8）**：`N-848` `N-855` `N-856` `N-857` `N-858`（**只是文档侧**）
  `N-860` `N-861` `N-862` —— 挪格不改合计。
* **v1.1（新入账 1 + 挪来 1）**：`N-880`（见下）、`N-849`（**用户 2026-09-14 裁定 ②**）。
* **登记不修（新入账 11）**：`N-877` `N-879` `N-882` `N-883` `N-884` `N-885` `N-886`
  `N-887` `N-888` `N-889` `N-890`。

#### ① `N-849`：单机形态**没有**「每小时兜底扫描」的等价物 —— **v1.1**（用户裁定 ②，本版不做）

双机那条路推之前要核执行面上 `genebench-answer-plane-scan.timer` 处于 `enabled + active`；
单机用的是**落位即扫**（容器口径 + 树口径两道门在**每一次**落位时同步跑）。
**差别只落在「落完了、还没跑」那段时间窗里** —— 那段时间没有第二次周期复查。
**主判据一条没松**：答案面永不挂进 agent 容器由 `runner/f02/answer_plane_guard.py --mode container`
读 compose 挂载面判定，命中即拒绝启动，**这一条是根相对的，单机照样有牙**。
**不挡使用**；挡的是「单机形态在纵深上与双机等价」这句话。已写进 README §2.3 状态框与手册 §1.3。

#### ② `N-880`：**Mac 上没有任何被验证过的「容器 → 宿主网关」路径** —— **v1.1**

手册旧文给的 `host.docker.internal` **不是「没验过」，是当场拒绝**：
`runner/c41/runner_core.py::gateway_addr()` 只收 `IPv4:端口`（四段十进制 + 冒号 + 端口），
主机名直接抛 `ValueError`，而 `0.0.0.0` / `127.0.0.1` / `localhost` / `::1` 在拒绝名单里。
代码这侧只剩「填这台 Mac 自己的 LAN IPv4」一条**可表达**的路，**而那条没有在 Mac 上验过**
（2026-09-13 的外部验收停在「本机网关 `/healthz` 200」那一步）。
**Linux 侧同一层的拦路是 `N-858`**：容器发往宿主自身 IP 的包走 INPUT 链，docker 只在 FORWARD 链插规则，
要机器主人 `sudo ufw allow from <容器网段> to any port 18081 proto tcp`。
**本卡 2026-09-14 在 f02 上又实测了一次**（无 sudo、规则没开）：容器里
`wget http://192.168.1.219:18081/healthz` **超时**。
**失败形态极难认**：容器起得来、模型照样调得动，只有数据网关打不通 ——
run 一路空转到墙钟闸、以 `124` 退出，读起来像「agent 不会做题」。
**这一条不挡「跑得起来」，挡的是「跑得出读数」**；两份文档（README §2.3 ①、手册 §1.3）
都已把它写成真跑前置的第一条。

#### ③ 本轮**没有**登记进这张表的是什么

① **`N-882`（`ops/test_Y.py` 那条恒红）** —— 那是**仓库自己的门**，不是发布件的限制；
按票据交出去（**待派卡**，三张卡三次报出、至今无人有权改它）。
② **卡 I10 在 f02 上留下的部署树与两个新 tag 镜像**（`/home/ljn/gb_single2`、
`gb-base:i10-20260914`、`gb-cx-u:i10-20260914`）—— 是**运维现场**，不是发布件的缺陷，
按 `ops/HANDOFF.md` §19.8「移，不要删」处理。
③ **推后的终值**（main sha / tag 对象 / 件数）—— 按 **N-743** 不进树，
只记进内网 `ops/reports/push_result.md`。
