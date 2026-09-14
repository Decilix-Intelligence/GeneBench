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
