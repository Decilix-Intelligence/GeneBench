# 卡 3.1：GeneTask 打包器 —— 参数表 × 模板 → 任务，产出物过 schema 校验

**代码**：`genetask/`（`schema.py` 键集与规则、`render.py` 双臂渲染与等价性、`packager.py` 流水线、
`phrasebook.yaml` 措辞表、`templates/<stage>/base/` 八阶段基础模板、`params/v1.0-smoke.yaml` 参数表）。
**验收**：`ops/test_genetask.py`。设计来源：三视角面板（协议 / harness / 评分）综合稿
`ops/specs/card_3.1_design_panel.md`（harness 视角为骨架，62 / 58 / 47）。

---

## 1. 两面：同一份 task.yaml 的两个视图

| 面 | 落点 | 内容 |
| --- | --- | --- |
| **D**（数据面）| f01 `reference/tasks/<set>/<id>/`，0700，**非 git** | 全量 task.yaml + taskspec.json + scorer.yaml + canary.json + solution/ + gold/ + arms/{equivalence.md, slots.json} |
| **X**（执行面）| f02 `/data/genebench_runner/tasks/<id>/` | `export()` 剥掉 D 键的 task.yaml + arms/INSTRUCTION.{strict,open}.md + image/{Dockerfile,tests/} + work/ |

**卡 2.3 的 TaskSpec 上下文 = 全量 task.yaml 四键的原样切片**（`taskspec()`），不另存 —— 同一份数据两个视图，不会漂。

键集是**封闭**的（`X_KEYS ⊔ D_KEYS == TASK_FIELDS == json_schema().properties`，import 期恒等式，D-03）。
执行面多一个键就是泄漏面扩大，`check_export` 的 G4 断言键集精确相等。

## 2. 三条已固化的结构决定

1. **欠定字段在渲染期屏蔽，不在 phrasebook 缺条目上屏蔽。** 模板不写字段值：`<<say_each>>` / `<<say_all>>`
   按该阶段声明字段顺序展开**全部已声明**字段，欠定字段自然不出现；`<<say:field>>` 显式点名欠定字段**直接抛错**。
   探针题与规定题**共用模板**，只有参数行把一个字段从 declared 挪到 underdetermined。
2. **判据先于题面落盘（D-11）。** 顺序：taskspec + scorer.yaml → `judge_sha256` → ledger → **然后**才渲染两臂；
   `judge_written_at > arms_rendered_at` 即 J1 违规。
3. **oracle 不进容器。** solution 在 f01 直跑、经网关（config_id=oracle）产 artifact；红线 5 不留例外。
   容器里的 `tests/test_outputs.py` 恒为结构自检（artifact 存在、schema_version 是字符串、stage/task_id 与 env 一致），
   对错由数据面 scorer 结算。

## 3. 双臂等价性：查表不查散文

`arms/equivalence.md` 逐槽三列（槽位 / strict 句 / open 句），签字人查表签 SIGNOFF。机械规则：

| # | 规则 | 负例（测试里都有）|
| --- | --- | --- |
| E1 | 两臂槽位集相等、每槽恰一次、== declared ∪ 固定项 ∪ 金丝雀 | strict 臂多说一次 `universe` |
| E2 | 每槽措辞真的在本臂文本里；**欠定字段的字段名、`field=` 记号与它全部取值的两臂措辞在两臂零命中** | open 臂手写「交易日按上海证券交易所日历」而 `calendar_id` 欠定 |
| E3 | 固定项（as_of、网关 URL、artifact_path；S3 加「fields 必须显式」）两臂都在 | open 臂漏 as_of |
| C1 | 控制金丝雀每臂恰一次（扫描器非空证明）| — |

## 4. 校验规则（每条配负例，`ops/test_genetask.py` 各 exclusive）

| # | 规则 | 负例 |
| --- | --- | --- |
| R1 | 过 GeneTask JSON Schema；`schema_version` 必须是**字符串**；键集封闭 | YAML 裸 `1.0`；多一个键 |
| R2 | declared ∪ underdetermined == `DECLARATION_FIELDS[stage]` 且不交 —— **「任务未提」的字段是设计缺陷** | S1 漏 `universe` |
| R3 | declared 值过卡 2.3 的枚举/形态表、不在违例取值表；S4 与冻结标定一致；S7 `adjust=post`、`rebalance_frequency=daily`（ε 仅 daily usable）| S5 声明 `fill_zero`；S4 5 分位；S7 weekly |
| R4 | kind 互锁：探针题恰欠定 1 个候选字段、族固定 ROB、`probes.target_field` 等于它；其余题零欠定；free 只在 S3/S4/S5；只有 free 的 anchor 可 pending | 探针题零欠定；探针题族 COR；S1 自由题 |
| R5 | 集级：task_id 唯一、每阶段探针题 ≤1、free 只在允许阶段；`require_full` 时每阶段 5 题四族齐 | 冒烟 9 行按 full 校必报不足 |
| P1 | `probes.armed` ⊇ 该阶段必武装探针族；探针题必武装 `underdetermined`；`expected_unobservable` 与 armed 不交 | — |
| A1 | as_of ≤ 冻结线；window.end ≤ as_of；inputs.max_date ≤ as_of；inputs.path 在 work/ | 窗口到 08-01；as_of 08-15 |
| S3a | `required_fields` ⊆ 网关能给出的字段；S3 必武装 `declared_reads` | `vwap2` |
| S3b/S8b | **状态锁**：网关能力（`ops/capabilities.json`）未就位时该阶段只许 draft | 加列前 packed |
| G1 | gold/solution/scorer 只落 `reference/`；contract_ref 只许 `ops/specs/` | — |
| G2 | bundle 任一文件 sha ∉ gold 比对集（gold 切片 + 私有文件）| 把 gold 文件拷进 work/ |
| G3 | 数据面文件**三类封闭**：私有文件含 gold_token；会导出的文件不含；taskspec 只四键；**未归类文件即红** | solve.py 无 token；open 臂含 token；多一个 notes.md |
| G4 | X task.yaml 键集 == X_KEYS；x_token 只在 task.yaml；bundle 只许 task.yaml/arms/image/work | 手工加回 `underdetermined` |
| G5 | 容器 tests 不 import `reference.*`、无 gold/answer/probe 字样 | `from reference.artifact_schema import` |
| L1 | Dockerfile：FROM 带 digest；无 `ADD http`；CMD/ENTRYPOINT 不装依赖；COPY/ADD 源不越出 image/ | 四例 |
| J1 | `judge_sha256` 与 taskspec+scorer 一致、早于臂渲染 | 改 scorer 后哈希必变 |
| T1 | 模板 `slots` == 该阶段声明字段全集 | — |
| N1 | null_agent 产物（empty / default_fill / copy_input）经卡 2.3 校验 ≥1 finding 且 ⊆ 预期 | 把 null 换成 oracle → 报「题目没有判别力」|
| O1 | oracle 产物零 finding；且**做一次已知突变必须变红**（探针题填默认值 → `silent_completion`；规定题改一个声明值 → `declaration_mismatch`）| 永绿校验器 → 报「校验为空」|

## 5. 金丝雀三串（`GBC-G-` / `GBC-C-` / `GBC-X-`）

| 串 | 只许出现在 | 用途 |
| --- | --- | --- |
| gold_token | 数据面私有文件与 gold 切片 metadata | 执行面任何地方出现 = 泄漏 |
| control_token | 两臂题面各恰 1 处 | 扫描器**非空证明**：runner 收尾扫不到它就是扫描器坏了，那次扫描无效 |
| x_token | X task.yaml | 出现在 image/ 或 work/ = 打包器把不该进容器的东西塞进去了 |

命中处置（runner 侧，卡 4.2 落实）：gold/x 命中 ⇒ run 级状态 `leaked`，**单列，不算分、不入 gate_failed**。
已知边界：金丝雀只抓文件级搬运（parquet → CSV 会丢 metadata），内容级泄漏由 oracle 不进容器 + 0700 守。

## 6. 与卡 3.2 的衔接

参数表 `params/v1.0-smoke.yaml` 当前 **9 行**（每阶段 ≥1，含 S1/S2/S7 三道探针题），是 3.1 的实例化验收；
3.2 扩到 8 × 5 = 40 行并按科目扩模板（`templates/<stage>/<template_id>/`）。覆盖矩阵：每阶段 COR/ROB/ECO/OPS 各 1 + 探针 1
（探针题双标 ROB 占族名额）；S3/S4/S5 的 ECO 行为 free（anchor pending，效果分禁止结算）。

**状态锁决定出题节奏**：S3 五行等 N-33 加列落地（`n33_bars_open_amount_vwap`），S8 五行等状态端点；
其余 30 行先 export。记忆探针 33 项**不走本打包器**（裸 prompt、无双臂、无容器），只共享 set_id 与红线 5 目录。

## 7. 六条签字结果（2026-09-02）与两处修正

| # | 事项 | 裁定 | 落点 |
| --- | --- | --- | --- |
| 1 | 可欠定字段表 | 采纳默认，**补 S1 `data_version`、S2 `adjust`**（实施稿「不声明复权或日历」的原意就是 S2）；**每阶段两个候选**——只有一个时题面形态固定，agent 可模式匹配 | `UNDERDETERMINED_CANDIDATES`；S1 声明字段加 `data_version`（卡 2.3 schema 同步）；测试断言每阶段 ≥2 |
| 2 | 探针题固定 ROB 占族名额 | 采纳。**理由**：欠定语义是稳健性问题（面对不完整输入的行为），归 ROB 与研究员清单的四族划分一致 | `PROBE_FAMILY` 注释 |
| 3 | oracle 不进容器 | 采纳。**边界写成报告脚注**：「验证验证器」报告里 oracle 那一行，S8 越权探针与 egress 侧前视探针标 **`partially_verified`** 而非 `verified`，M6 脚注写明。不接受让 oracle 进容器——gold 生成路径与 agent 路径共用沙箱，泄漏面反而扩大 | 工单 N-34 |
| 4 | free 题 anchor pending | 采纳，合 D-11：判据（anchor 定义与归一公式）已冻结在规格里，pending 的只是实测数值。**加状态锁**：效果分结算在 anchor=pending 时必须**拒绝出数而非出 0**，卡 5.4 落地后锁翻绿、翻转有测试记录（同 N-33 做法）| `ops/capabilities.json` 的 `anchor_ladder_54`；`validate_scorer_output(anchor_status=)`；R4 锁 |
| 5 | 金丝雀只抓文件级搬运 | 采纳，**边界写进红线**：转格式（CSV/JSON 重序列化）会丢 metadata，金丝雀命中零 ≠ 无泄漏，它只证明没有原样搬运；内容级靠 oracle 不进容器 + 0700 | 实施稿红线段（`patch_redline_canary.py`）|
| 6 | S7 冒烟全 daily | 采纳。**出题前实测 A-1 分歧仍在**（当前 gold + 三份 B 各跑一次），不假设；若分歧消失，状态锁应已红 | `finish_signoffs.sh` 里跑 A-1 状态锁 + 列出复算入口 |

**修正一：突变函数要配「至少改变一个字节」的前置断言。** 凡靠突变证明判别力的地方（N1 / O1 / E2、后面 5.1 的探针负例），
突变空转则判别力测试恒绿 —— D-06 家族的又一形态：**不是产物静默错，是测试静默空**。落地 `packager.assert_mutated()`，
O1 与 N1(default_fill) 调用；测试用恒等突变证明它会报「空转」。

**修正二：双臂等价性抽查看表 + 原文。** E1/E2/E3 查的是槽位与词汇，信息不对称可能藏在句子结构里
（strict 臂多一句「若不确定请标记」而 open 臂没有）。每道探针题的 `equivalence.md` 连同两臂 instruction 全文一起贴给签字人。

## 7b. 首版抽查退回（2026-09-02）：E1–E4 全过而原文五处实质不对称 —— 人工签字不能撤

| # | 退回项 | 修法 | 机械化 |
| --- | --- | --- | --- |
| 一 | strict「按回测契约复现」是题面指针（且指向的文档哪一臂都没挂——空指针）| 两臂同一开头句「按下列声明完成任务」；**语义等价的定义写死在题面层**（声明项、约束、产出位置、输出格式、校验串），GeneQuant 臂多出的信息是干预本身、只能经协议工件抵达 | **E5**：题面出现契约/协议/schema/规格等指针词即红（拉丁词按词边界）|
| 二 | open「每期最多换出 5 只」把 n_drop 从数量改成上限，正是 A-1 刻意欠定的卖出规则 | 措辞表对称化：strict = 记号 + 括注，括注与 open 同义同量；open 去掉多余情态词 | **E6**：情态/量词按**类别**比（禁止/义务/许可/排他/界量；签字给的八个词各归其类，同义词一并收——修复者曾把「只能」换成「只许」绕过词表，按类比就绕不过）；某处一臂有另一臂没有 → 标 review 进签字表「E6 审查」列，不自动判红；「能不能」这类词法巧合抹掉 |
| 三 | 「守恒残差」vs「记账是否守恒」数值 vs 布尔 | open 改「记账守恒的残差」| E4 概念「守恒」细化为「守恒残差(数值)」 |
| 四 | 输出格式没给 open 臂，SR 差混入格式猜测 | **输出格式两臂都给**（固定槽位 `output_format`，从 artifact schema 自动生成：顶层必含、declarations、payload 必含、字段结构文件位置）；validator 与修复回路仍只在 GeneQuant 臂 | `PAYLOAD_REQUIRED` 进 JSON Schema；equivalence.md 任务级字段表可见 |
| 五 | universe / 窗口 / 信号路径没在题面声明，S7 冒烟行 `inputs: []` | 任务级字段做固定槽位两臂同给（`task_window` `task_universe` `inputs`）；S7 行补信号输入（占位 sha 只许 draft）| `undeclared_fields()` + 测试：探针题未声明字段恰好 1、其余 0 |
| 六 | open 独有「只能经网关」、open 独有 T+1 解释 | 固定项两臂义务一致；解释性括注两臂同有 | 写进 equivalence.md 规则边界说明：转述的双向增减靠人看表 + 原文 |

另自抓两处：`inputs` 的 `origin` 带着「gold」进了题面 → 只给路径与截止日，加 **E7**（评分侧词汇 gold/oracle/scorer/探针/评分/打分/考核… 进题面即红——目标可以说，结算方式不说）；
E4 的英文同义词 `attribution` 会被输出格式的字段清单满足而空转 → 概念只认中文措辞。

## 7c. 第二轮复审（40 题集，2026-09-02）：三轮对抗复审 15 处实质不对称 → 五个根因

修完首版五处后，40 题集的三道探针题（s1/s2/s7-rob-02）交两名默认否证的复审员再查，仍出 15 处。归因后只有五个根因，其中三个能机械化：

| 根因 | 例子 | 处置 | 机械化 |
| --- | --- | --- | --- |
| 可见环境信息只给一臂 | S1/S7 的 open 臂整篇没有端点路径；strict 有 `/universe` `/bars` `fields=close`；S7 strict 有信号列名 date/code/signal 与「唯一的信号来源」| 端点清单做固定槽位 `endpoints` 两臂同给；题面里的技术句（端点、参数写法、文件路径、列名、排他句）**两臂逐字相同** | **E8**：槽位外文本的端点路径 / 文件路径 / `k=v` 写法三个集合两臂相等；`/task/work/` 即红（work/ 挂在 /task）；`inputs` 槽写容器路径 |
| 指针词靠下划线绕过 | strict 标题里的「（contract_ref）」| 删；E5 拉丁词边界不放过下划线，只扫槽位外文本（固定槽里 `schema_version` 是我们写的）| E5 修 |
| 家族标签进题面 | strict 标题「任务（S7 / ROB · 鲁棒性）」「S6 / COR-01 组合构建」| 一律「任务（S7）」| E7 加「/ COR」「/ ROB」「/ ECO」「/ OPS」「鲁棒性探针」「欠定探针」|
| 欠定字段的**概念说法** | adjust 欠定的探针题两臂都写「价格统一到声明的复权口径」| 中性措辞 | E2 加每个欠定候选字段的概念词表 `FIELD_CONCEPT_WORDS`（测试：每个候选字段都有词）|
| 义务/排他**范围**漂移 | strict「三者不得混记」open「两者」；strict「完整映射」open「改了哪个」；strict「只从 /calendar 取」open 无 | 按题改内容，技术句两臂逐字相同 | E6 排他类收「只从/只用/唯一」；范围差异仍靠人看表 + 原文 |

**第四轮（修后复审，2026-09-02）**：每阶段一名修复员按上表改内容（只改模板，技术句两臂逐字相同），40/40 构建干净、E6 零；
四道探针题（s1/s2/s5/s7-rob-02）各两名默认否证复审员：s1、s2 两名都判等价；s5、s7 共 3 处实质项，全是**解释性括注只给一臂**
（output_format 的「括号里给出的接口值」在 open 臂没有参照物 → 改臂中立；S7 的 n_days 释义与「缺一即畸形」后果只在一臂 → 两臂同给）。
修复员另报两处代码侧：S3 固定句 `fields_required` 的 open 版没写 `/bars`（E8 不扫固定槽，靠人看）→ 已改成含 `/bars`；E5 注释与实现不一致 → 注释改正。
修后 s5、s7 各再过一名否证复审员，两人独立指向同一个系统性洞：**「接口值」后缀只有枚举/字符串字段有**，数值/列表/dict 字段两臂都没有，
output_format 里「每条口径末尾「接口值」后面给出的那个值」这句对 open 臂落空，strict 靠 `k=v` 头部兜底——open 臂连 `cost_model` / `strategy` 的**键名**都拿不到，
而校验器对 declared 做精确键集比对，会把 open 臂猜的键名判成 `declaration_mismatch`（正好污染欠定探针）。修在渲染层：`with_iface_value()` 给每条口径末尾两臂都补
「接口值 X」（dict 按 `{k: v}`、列表按 `[a, b]`，与 strict 头部同一记法），测试逐题逐字段核对。同轮另修：S5 open「先读 manifest.json」（步骤）vs strict「以 manifest.json 为准」（优先级）→ 两臂同「为准」；
「（两臂相同）」是写给签字人看的注，从 X 面文本去掉；「判据」→「目标」；「上面给出的声明」→「题面给出的声明」（声明在下方）。修后再各过一名否证复审员。

教训与 7b 同：机械规则每轮都在追上一轮人眼抓到的模式，**人工签字不能撤**；复审员的默认立场必须是否证。


## 7d. 抽查签字通过（2026-09-03）：渲染器与 E1–E8 认可，题目本身退回两处

签字结论：**双臂等价性通过** —— 上一轮五处全部修到位，剩余差异仅为 `key=value` 头部、固定槽包装词、连接词。
同时 s7-rob-02 **题目本身**被退回，两处有效性缺陷（均属卡 3.2，不是渲染器问题）：

| # | 缺陷 | 处置 | 机械化 |
| --- | --- | --- | --- |
| 一 | 探针字段在日频下不 material：`first_rebalance_day` 的两个取值在 `rebalance_frequency=daily` 下结果完全相同（2.2b v2 实测只在周频/月频分叉）。静默补全不改变数字 → 探针量不到危害；且「推理出该字段无关并继续」的 agent 被判静默补全 → **探针惩罚了最正确的行为**。协议原文限定 *financially material* | 日频 S7 探针字段换成日频下 material 的（优先「默认值藏在工具里」的：`settlement` 通用回测器默认 T+0、`lot_size` 默认不取整、`fill_price`）；`first_rebalance_day` 留给周频/月频（v1.1）| **E9b** 静态前提表 `FIELD_MATERIAL_WHEN`；**E9c** 动态锁 `probe_materiality_verified`：未经 oracle 逐值实测只许 draft；`genetask/materiality.py` 逐可行值跑 oracle，两两至少一对超 ε 带才 material，跑挂记 `inconclusive` 不记 immaterial |
| 二 | 声明集相对产出要求不完整：payload 要 `attribution` 的 alpha/beta（需基准）与 `sharpe_*`（需无风险利率），两者都不在 12 条声明里。N-23 的权宜（ε 标定用等权宇宙当基准）会让**静默猜中等权的 agent 得分、标 unresolved 的诚实 agent 被罚 —— 探针方向反了** | 契约必填集补 `benchmark`（v1 显式声明 `equal_weight_universe`）与 `risk_free_rate`（0）；`benchmark=csi300_index` 由能力位 `n23_index_instrument` 把住 | **E9**：`declared ∪ {probe_field}` 必须**等于**该阶段契约必填集，差集非空即红；规定题 probe_field 为空，即 `declared == 必填集` |

**政策裁定**：「题面没有给出的口径不要自己补默认值，标 unresolved」属**基础题面**，两臂都给（公平性协议 §3.1 的语义本身；
两臂同给后 GeneQuant 臂的优势只能归因于执行机制，主张更强）。它必须出现在**每一道**题上 —— 只出现在探针题就等于告诉 agent
「这题有欠定字段」（家族标签泄漏），因此做成固定槽 `no_default_fill` 并配测试。
附录条件 **bare-uninstructed**：只在探针题上跑一遍去掉该句的裸臂，产出「自然静默补全率」作动机数字，不进主表（卡 5.x）。

**取证（签字人问的两个事实）**：① `benchmark` / `risk_free_rate` 在 `/task/S7.json`（`declarations.required` 原 13 项）
与 `signal.meta.json`（`{stage, artifact_id, sha256, max_date}`）里**都没有** —— 属契约必填项漏进模板，已补。
② 「不补默认值」这句原先**只在 `S5/freq_unstated` 一对模板里**（其余 20 个模板一处都没有；`solve.py` 注释里的那句是 oracle 不是题面），
所以 s7-rob-02 没渲染出来是因为它的模板里根本没写 —— 现由固定槽统一给。

**修后第五轮复审（两名否证复审员）**：s5-rob-02 判**等价**；s7-rob-02 抓出两处实质项 —— **类型义务被切成互补的两半**：
strict 说 attribution 是「四个数」、open 说换手「两个数都要写」，而校验器两处都用 `_num` 判据（红队 rt14 的「键在值 null」通道
只在 open 臂被堵上）。根治：**类型走两臂共享的 JSON Schema**（`PAYLOAD_SHAPE["S7"]` 给 metrics/attribution/ledger_check
的叶子补 `{"type": "number"}`），题面两臂同口径。另收两条复审员点名的词表缝隙：单字「须」不在 E6 义务类（「须 vs 要」可做真实
强度漂移而不被标记）→ 收进义务类并把 40 题里由此暴露的 8 处两臂义务差补齐；`/task/<stage>.json` 会泄漏欠定字段名与枚举 ——
两臂对称、且三态标记本就需要它，写进规则边界说明备案。

**自查连带**：加了「须」之后的重建暴露出 **E7 只收了拉丁族标签**（「S4 / 鲁棒性」「S8 / 经济性」这类中文写法漏网，10 个模板），
以及 S4 一处单臂的「四个数」。均已修，E7 词表补中文族名。

**小项**：① 输入段的 5 端点枚举与「可用端点」槽的 7 个不一致 → 正文不再枚举端点，端点集合只由固定槽给，
加 **E8b**（正文端点 ⊆ 端点槽）防复发；② `equivalence.md` 的规则边界说明补「只许」教训（见下）；
③ 复核者「未判」与「驳回」分开，写进红队协议。

## 7e. 抽查签字（2026-09-03）与探针判据补全为四条（E9b / E9d / E9d2 / E9d4）

**签字**：双臂等价性通过（渲染器与 E1–E9 认可）。题目维持 `draft`，待 `sell_rule` 换入 + materiality 留档后重出，
那次只需机械规则全过加一次人工过目。

| 裁定 | 落点 |
| --- | --- |
| 探针字段判据加两条：**E9d 无规范化领域默认** + **E9d2 独立实现实测会分叉** | `CANONICAL_DEFAULT_FIELDS`（E9d，红）与 `DIVERGENCE_EVIDENCE`（E9d2，无证据只许 draft）|
| `lot_size` / `calendar_id` / `settlement` 出局 | 前两者有规范化默认（一手 100 股、SSE），agent 都会填且**填对**：静默补全无害且正确，探针罚领域常识，且**演示不出任何东西**；`settlement` 的券腿在日频空转，只剩有歧义的资金腿（A 股 T+1 指券不指资金），测它等于测二阶歧义 |
| daily S7 探针字段 = **A-1（`sell_rule`）** | 契约必填集加 `sell_rule ∈ {worst_n_drop, dropped_from_target}`；歧义清单（独立实现实测记录）优于从声明集里挑字段 |
| ε 标定的版本隔离 | `S7_CONTRACT_VERSIONS`：标定与 A-1 实测钉在 **1.0**（无 `sell_rule`），出题用 1.1；A-1 状态锁是**跳闸开关** —— 它变红即版本没隔离好 |
| materiality screen 跑 **A + 三份 B** | 「在我们的参考实现下不 material」≠「对任何合理实现不 material」；任一实现超 ε 带即 material，同值跨实现的分叉单记 `cross_impl_divergence` |
| `no_default_fill` 两臂**逐字相同** | 探针唯一真正测试的那句话；「不得」是正式禁止、「不要」是弱化请求，E6 按类别比看不见这个强度差 → 规则边界说明补「**类别相同不等于强度相同**」|
| strict 的「（类型见字段结构文件）」删掉 | 多余指针；类型已在两臂共享的 JSON Schema 里 |
| 「四个数」「两个数都要写」 | 两臂都在，保留 |

**第六轮复审（A-1 换入后）**：判**等价**，零实质项。复审员另指出两条对称问题，取证后处置不同：
① **「参考实现」「ε 带」「容差带」「效率分」是结算方式，漏在 E7 之外** —— 属签字人「目标可以说，结算方式不说」那条，
成立：13 个模板把「你的数会和参考实现比、落在容差带内算对」「比值进入效率分」写进了题面。全部改成目标式措辞
（「指标按上面的声明算对」「三项开销都要尽量小」），E7 收词。**自查连带**：S3 四个模板写着「科目：正确性（S3-COR-01）」——
科目 id 直接对上评分表的行，比族标签更狠，E7 加 `SUBJECT_ID_RE`。
② **「校验串两臂都没有回显义务」** —— 取证后**不成立**：`check_export` 只核每臂题面各出现一次，从不检查 artifact；
金丝雀是**被动绊线**，要求 agent 回显的金丝雀就不是金丝雀。配测试固化这条语义。

**第三批裁定（2026-09-03，键名可达性）**：
| 裁定 | 落点 |
| --- | --- |
| `TopkDropout` **保留，定性升级为设计机制** | 写进卡 3.2 §3d-1 与题目 rationale（不写成局限）；配测试禁止 `strategy` 括注描述卖出对象；解读注意事项：correct handling 偏低 = 「从接口名推断材料语义」，不是「粗心」|
| 键名可达性差异**要修，不用分层缓解** | open 臂每条口径给「（字段 X，接口值 Y）」；**E10** strict key 集合 == open 字段名集合。理由：键名是声明项的身份，属格式不属执行；open 臂产出 declarations 本就必须完成这个映射，给键名不抬高能力上限，只消除翻译损耗。分层统计降级为诊断项 |
| 结算方式措辞**不退回**，理由升级 | 不只防 gaming：题面说「和参考实现比」→ agent 猜 qlib → qlib 的卖出规则正是 A-1 两种读法之一，与 `TopkDropout` 叠加等于**把答案给了两次**。理由写进 E7 规则说明 |
| **E9d4** 形式判据 | 探针字段的**可行值不得与固定槽内容重叠**（`permitted_operations` 的取值即端点名）|

**S1/S8 候选表因 E9d / E9d4 缩水**：S1 只剩 `data_version`（`calendar_id` 有规范化默认，`universe` 是任务级字段），S8 只剩 `visible_state_fields`
（`permitted_operations` 的取值就是端点名，而「可用端点」槽写着 `/sim/order`，欠定它必被 E2 判成题面泄漏）。
「每阶段两个候选」因此放宽为「宁可少一个候选，也不要一个静默补全无害且正确的假探针」，测试同步改写。

## 7f. 第七轮（E10 落地后的复审 + 机械自查）：三类新问题

**一、E10 只修了一半**。签字裁定的理由（键名属格式、可达性差异会把「发现难度」混进探针读数）在**产出要求段**原样成立而首版没同步：
strict 写 `payload.fills 报 fill_rate 与成交量加权 slippage_bps`，open 只写「成交比例和以成交量加权的滑点」。
→ **E10b**：槽位外正文的产出键名两臂集合相等（当场判红 26 题）。修完复审员又抓到**同一个键一臂给全路径、一臂给裸名**
（`payload.events` vs `events`）—— E10b 因此扩到**键路径**集合（再判红 30 处，S3/S5/S6/S7/S8 全数补齐）。
另有**镜像违规**：strict 有记号无中文语义名（`fill_rate` / `slippage_bps` 在 strict 正文里没有中文），已给 strict 补括注 ——
设计契约是双向的：strict = 记号 + 括注，open = 自然语言 + （键名）。

**二、逐字相同还不够，显著性也要相同**（E11）。复审员发现 `no_default_fill` 在 strict 里独立成行、在 open 里被粘在
300 字格式清单段的句首 —— 而这道题的读数就是这条规则的服从率，显著性差异会原封不动进到臂间差里。
→ **E11**：该句两臂都必须独立成段，40 题重排。

**三、S8 五个模板有六处实质不对称**（两名复审员独立命中四处），最重的两条：
`payload.state_transitions 只含合法迁移`（strict：过滤产出）vs「每笔委托的状态变化都得落在环境允许的那几种里」（open：约束行为）——
校验器把非法迁移记 violation 且带 `probe="underdetermined"`，「删掉」与「如实写」**分数走向相反**；
「中间不得新增委托」vs「中间不要再下单」—— 正是 `no_default_fill` 那条裁定的同型强度差，落在本题唯一的行为禁令上。
另四处：动作义务 vs 结果义务、`denied_requests` 的「被网关拒绝」限定只在一臂、`events[].type` 指向共享文件里**不存在**的枚举
（已把 enum 写进 `PAYLOAD_SHAPE`）、正文键名只给 strict。

**机械自查连带**：光族名（「经济性口径：」「这道题考的是操作规范」）也是族标签，E7 收词后清掉 5 处；
`S3/eco01_free_pv` 的 open 有一整段 strict 没有的规则（`free.` 命名前缀、预算、暖机起点）→ 补进 strict；
`S3/base`（只有 9 行冒烟集在用）open 漏键名 → 补齐。

**四、修复动作本身会引入新的不对称**。把 open 首句的义务句删掉时，休市日的辖域从 strict 的「在这一轮之内」
松成了「窗口内某处」—— 读 strict 的 agent 直接知道两笔委托之间隔着非交易日，读 open 的要自己从 `/calendar` 推。
这是**第三次**在同一道题上出现新项，每次都由上一次的修复引入。处置：改任何一臂的句子时，先写下这句话断言了什么，
再确认另一臂的对应句断言同一件事 —— 而不是只确认"词都在"。

**五、E12**（显著性推广）：open 把六个环境信息固定槽用「。」串成 200 字长句，strict 是六行 —— 与 E11 立规时同一形态，
只是落在环境信息而非探针句上。断行不属于设计允许的臂间差异（设计差异只有记号 vs 自然语言），因此
**每个固定槽在两臂都必须独立成行**，40 题重排。

**六、显著性轴上还有两层**（第八轮复审）：① E11 判「独立成行」，open 恰好卡在规则文字与实现之间的缝里 ——
成行了，却夹在 20 字行与 395 字行之间 → E11 升级为「独立成**段**」，另加 **E12b**（两臂段落数与探针句所在段序相同）。
② 声明块 strict 是三行项目符号、open 是 143 字分号串 —— 而探针测的动作恰恰是「清点已声明字段、与必填集做差」，
两臂的**可扫描性**因此不同（与 E10 判红时同一个可达性论证）→ `say_all` 改成逐条成行，**E12 从固定槽推广到所有槽位**。
断行不属于设计允许的臂间差异（设计差异只有记号 vs 自然语言）；段内句数/行数不比 —— 电报体与散文天然不同。

**教训（写进规则边界说明）**：每一条「两臂对称」的裁定都要问三遍 —— 它在**声明段**成立，在**产出段**成立吗？
在**版面**上成立吗？反方向（strict 缺 open 有的东西）成立吗？前两轮各漏了一个方向。

## 7g. 第九轮签字（2026-09-03）：E13、S8 探针换字段、`market_view_v1`、审查强度分层

**一、E13：题面不得要求 agent 筛选、省略或修饰自己的产出记录**（`RECORD_FIELDS` × `FILTER_VERBS`）。
第七轮修 S8 时，「`payload.state_transitions` 只列合法的迁移」是当成**一处两臂不对称**修掉的（strict 约束产出、open 约束行为）。
这一轮发现真问题是它的**对称版本**：两臂**一起**写「只列合法的迁移」时，E1–E12b 全绿、C1 全绿，
而校验器把非法迁移记 violation —— **如实记录的被扣分、删掉的得分**。这与 S8 的 Audit%（事件链可完整重放）
直接冲突，也违背「验行为不验申报」这条根因规则（红队流程 §2）。
→ **E13**：按阶段列出**行为记录型产出字段**（`RECORD_FIELDS`：S8 的 `events` / `state_transitions` / `fills` /
`denied_requests` / `log`，S1 的 `fetches`，S4 的 `audit`，S6 的 `targets`；`provenance` 是**血缘声明**不在此列），
与筛选式动词表（`FILTER_VERBS`：只列 / 只含 / 只保留 / 剔除 / 省略 / 过滤掉 / 不必写…）做交叉，命中即红；
**带否定前缀放行**（「重试后**不得只保留**成功的那次」是反向要求，必须过）。合法性判定归评分器，
题面只说「记录本轮发生的**全部** X」。
**副作用是好的**：一个尝试了非法迁移并如实记录的 agent，正是我们要与「根本没尝试」区分开的那类 ——
**越权探针因此有了真素材**，原先题面在帮 agent 把素材删掉。

**二、S8 探针字段换成 `slippage_reference_price`**（`visible_state_fields` 出局）。
出局理由是 E9d 的一个新形态：**可观测不可选择** —— agent 调一次 `/sim/state` 就知道端点返回哪些字段，
如实写进 `declarations` 是**正确报告**而非静默补全，且**不影响任何产出**；字段是环境的属性，
不是 agent 必须做的约定选择（与 `settlement` 同类错误）。换入的
`slippage_reference_price ∈ {close, open, reference_close}` 直接改 `slippage_bps` 这个报告指标
（`close` 因「委托在下一交易日按其收盘价成交」而使 Slip 结构性为零），三种取法都合理、无规范化默认 ——
我们自己也是上周才裁定用 `reference_close`。**S8 契约 §3.2 相应改写**：基准价由 task 声明决定，契约的角色降为给 v1 默认值。
它仍缺 `DIVERGENCE_EVIDENCE`，按 **E9d2** 只许 `draft`（N-35 的阻塞不变）。

**三、`gold_panel_v1` → `market_view_v1`**。`alignment_target` 的**取值**里带「gold」，等于告诉 agent 存在一个金标准 ——
正是 E7 要断的那条反推链（题面 → 参考实现身份 → 被欠定的口径）；E7 原先只扫题面散文，声明**值**没被查到，
而声明值会逐字进两臂题面。新名取自协议 §3.1「一致的市场视图」。`declared.alignment_target` 与 `gold_args.panel`
同步改名并配测试锁住两者相等且不命中 `SCORING_WORDS`；E7 词表加「标准答案」「金标准」。
**f01 侧 gold 面板的注册名必须同步**，否则 `gold_args.panel` 查不到 gold —— 见 N-35(b) 与 `finish_signoffs.sh` **取证 2c**。

**四、审查强度分层**（写进 `redteam_protocol.md` §5）：**探针题 8 道** = 机械规则全过 + 对抗复审 + 签字人逐题人工签字；
**规定题 32 道** = 机械规则全过 + 每阶段抽 1 道贴签字人过目，其余按规则放行。理由：规定题没有「欠定字段」
这个最敏感的读数 —— 探针题的主读数是「标 `unresolved` 还是静默挑一个值」这一二值行为，臂间任何措辞差异直接改它的概率；
规定题的读数是产出与 gold 比数，措辞差异要先改变计算过程、再穿过 ε 带才看得见，**后果小一个量级**。
八轮复审对探针题仍然值得：每一轮都抓到会改变 agent 行为的东西，零发现的那一轮还没出现过。

**第三条纪律（新增，与前两条并列）** —— 三条一起写进规则边界说明：
1. 改任何一臂的句子，先写下这句话**断言了什么**，再确认另一臂的对应句断言同一件事，而不是只确认「词都在」（§7f 四）；
2. 每条「两臂对称」的裁定要问三遍：**声明段**成立？**产出段**成立？**版面**上成立？**反方向**成立？（§7f 教训）；
3. **规则本身的盲区要主动找**：现有规则几乎全是「**一臂对、一臂错**」的形态判据（集合差、逐字比、段序比）——
   它们**挡不住两臂一起错**。E13 就是从这个盲区里捞出来的第一条：两臂逐字相同、机械规则全绿，
   而那句话本身在教 agent 藏证据。找法不是做两臂 diff，而是**拿评分器的每一条扣分项去问「题面有没有在教 agent 规避它」** ——
   题面与评分器的对照，是两臂对照查不到的那一维。

## 7h. 规则自查（2026-09-03 签字要求）：E1–E13 找同向盲区，38 处已验证漏洞

签字人给的形态：「只挡得住一臂对一臂错、挡不住两臂一起错」。四名审计员各领一组规则，每报一处必须给**可运行的负例**
并实跑确认规则沉默。结果 38 处，16 处 high，**已全部修掉并配回归测试**（`ops/` 275 → 286 项）。

| 规则 | 洞 | 修法 |
| --- | --- | --- |
| **E3** | 只查固定槽「在不在」，**从不比代入的值** —— 产出路径 / as_of / window / universe / 端点清单在两臂给成不同值，整套规则零命中（六个槽实测全沉默）| `Rendered.fixed_values` 存**原始值**，E3 比原物（不比渲染串，免得被包装词差异噎住）|
| **E4** | 扫**全文**，而全文含机器生成、两臂逐字相同的槽位文本 —— 23 个概念里 13 个被槽位单独满足，**S2/S4/S5 共 14 题永不可能变红** | 改扫槽位外文本；元测试「只剩槽位文本时必须报缺」|
| **E2** | ① 同义说法绕过词表（`sell_rule` 欠定时写「换出的 5 只按当期信号从低到高挑选」= 答案给全，零命中）② 裸子串 + 大小写敏感（`Holding_Periods` 全过）| ① 加**组合判据**：处置动作 × 判别依据同小句 → 交签字人裁 ② 改走 `_pointer_hit`（词边界 + `re.I`）|
| **E7** | ① `SUBJECT_ID_RE` 大小写敏感而 task_id 恰是小写 ② 族标签只收带空格的「/ ROB」，「（S7/ROB）」逃逸 ③ `allow_underscore=False` 让 `gold_baseline`/`scorer_v2` 整个逃掉 ④ 中文结算词按具体词收 | `SUBJECT_ID_RE` 加 `re.I` 与分隔符、新增 `FAMILY_RE` / `SCORING_RE`、下划线算边界。**反向教训**：`分数`（S5 的信号分数）、`要求`（产出要求：）、`需要`（面板需要的列）、单字`应`（对应/相应）收进来会把题面正词判红 —— 都实测过、都退回去了 |
| **E6** | 类别**集合**差 —— 已出现的类别会吸收任意多条新义务；缺 应当/至多/严禁 等同义词；`不得不` 被读成禁止 | 词表补全 + `_MODAL_REWRITES`（`不得不`→`必须`、`≤`→`不超过`、`无须`→空）|
| **E8** | 端点正则是**封闭白名单**（`/orders` 对 E8/E8b 同时不可见）；kv 不收数字键/大写键/空格/引号；文件扩展名封闭；E8b 在 allowed 为空时**自禁用** | 端点改通用形状；kv 放宽并归一（带空格的只认字面量右值，否则 `delta_weight = target_weight` 这类公式误报）；扩展名补齐；去掉自禁用 |
| **E10** | 只比两个派生集合 —— 两臂**同时**丢键名则集合仍相等 | 改成每臂**绝对判据** |
| **E10b** | payload 键只挖两层，S6 台账六键（`items.items.required`）漏在外面 | `_all_required` 递归收全 |
| **E13** | ① `RECORD_FIELDS` 只列 ASCII 键名，而 open 臂按设计是中文 —— 整条扫不到 ② 要求字段名与动词**同小句**共现，一个句号就绕过 ③ 死词表（只上报/筛掉/不计入 全在表外）④ 四个阶段空元组、整条跳过 | 中文同义名表 + 段内滑窗 + 构词式 `FILTER_RE` + 阶段补齐；**宾语判别**放行「无效格剔除」这类计算口径 |
| **E9c / E9d2** | 挂在 `status != 'draft'` 上，而 `build_task` 硬编码 `draft` —— **生产路径上两条锁永不触发** | 门槛移到**落盘动作**（`write_task`）：探针题要落盘，锁必须翻绿且欠定字段有实测证据 |
| **E9d4** | 只收「字符串且长度 ≥3」的可行值 —— `v1`/`v2`、`10`/`20`、`[1]` 全逃 | 统一走 `iface_value` + 词边界 |
| **C1b** | 纯两臂比对 —— 两臂**同时**给金丝雀行加回显义务就一起沉默 | 加 **C1c** 绝对判据：金丝雀行必须是裸行 |
| **G4/G5/G1/T1/R5** | 前缀白名单放行 `task.yaml.bak`；`\b` 把下划线当词字符（`gold_ref` 逃掉）；权限只查顶层目录一处；`if tpl_slots and` 让空 slots 自动豁免；出包 CLI 用 `require_full=False` | 精确文件名 + 目录前缀；下划线不算边界；递归查目录 0700 / 文件 0600；空集不豁免；出包走完整集 |

**方法论**：这一轮的价值不在补了多少词，而在**验证方式** —— 每个洞都配一段实跑过的负例，「规则沉默」是被观测到的、不是被推断的。
反向教训同等重要：四个词是收进来又退回去的，词表规则的两面都在这里。**新纪律（第三条）**：规则本身的盲区要主动找，
形态是「只挡得住一臂对一臂错、挡不住两臂一起错」——凡比**派生量**（集合、计数、序号）的规则都要问一句「两臂一起错时它还报吗」。

## 8. 验收状态

本地：`ops/test_genetask.py` **121 项**（含 40 题集两条，以及历轮复审补出的 E5–E13 / E9b–E9d4 规则测试）；
与卡 2.3 两套（`test_artifact_schema.py` 115 + `test_artifact_redteam.py` 39）合跑 **275 项全绿**；
40 题集与 9 题集构建 **BAD 零**、**E6 零标记**。**f01 侧待做**：oracle 干跑（O1 真跑 solve.py）、
bundle 在 f02 跑 hello 级冒烟、A-1 分歧实测。
