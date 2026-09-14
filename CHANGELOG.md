# CHANGELOG

> **本文件是渲染出来的，不要手改。**
> 生成器 `ops/mk_release_manifest.py --write-changelog`，
> 数据源 `ops/freeze_v10.py` 的 `REVISIONS` / `REFERENCE_REVISIONS`。
> 想改一条记录就去改那两个元组 —— 那里才是「这两次运行为什么不可比」的答案所在。

当前：任务集 **1.0.16** / 参考面 **r1.0.23**。
四条版本轴与「可比」的定义见 [`VERSIONS.md`](VERSIONS.md)。

> **一处历史遗留，照实说**：拆轴之后新增的**任务集**记录写进了
> `REFERENCE_REVISIONS` 元组里（`1.0.7` … `1.0.13`）。本文件按版本号前缀 `r` 分轴，
> 所以它们出现在「任务集轴」一节 —— 元组本身没有整理，整理它要动冻结面的代码。

---

## 任务集轴（`set_version`，17 条记录）

### `1.0.16` — 2026-09-11　（票据 N-605 / N-578 / N-573（卡 F1，用户裁定 ①③⑦））

* **为什么**：**四件事挤在同一次重冻里**，因为它们每一件都动到「根覆盖什么」，分四次推等于让同一批题面有四个版本。
① **公开通道分轴**（N-605，裁定 ① 走 B）：公开链此前**借用私有轴的号**，而它的夹具字节与私有的根本不同（实测 `s4-cor-01/work/factor_panel.parquet` 公开侧 `034c4526…` ≠ 私有侧 `c8ed955e…`）。同一个 `set_version` 指向两批不同字节的题，「这两次运行可比吗」在公开通道上**答不出来**；而且公开通道那 5 道带 `inputs` 的题（s4-cor-01 / s5-cor-01 / s6-cor-01 / s7-cor-01 / s7-rob-02）**一道都出不了集** —— `export_task` 的夹具身份闸拿私有声明去核公开字节，必然不符。
② **实例 ID 一律带参数指纹**（N-578，裁定 ③）：基点实例此前**沿用基点题的 task_id**，于是 `v1.0-instances/s8-cor-01` 与 `v1.0-smoke/s8-cor-01` 同号。`gateway/sim_factory.task_dir` 靠 glob 找题目录，同号就是歧义，它按设计**当场 RuntimeError 不猜** —— 结果是 **S8 四道题的 gold 现在一份都重算不出来**。
③ **sim 会话键带 set_id**（裁定 ③）：会话键原来是 `(run_id, task_id)`，而 `task_id` 在两个出集里可以重名。同号不同题共用一个会话，表现是「账户里有一批不属于这道题的持仓」，没有一处会报。
④ **`REVISIONS` 复活**（N-573，裁定 ⑦）：拆轴之后新增的任务集记因**全写进了 `REFERENCE_REVISIONS`**（1.0.7 … 1.0.15 共 10 条），`REVISIONS` 停在 1.0.6 变成死表，而 `build_manifest` 的 `revised_at` 取的正是它 —— 清单里那个日期从 2026-09-05 起就没动过。
* **改了什么**：① `SET_VERSION_PUBLIC` 与私有轴并列，公开清单落 `ops/manifests/v1.0-smoke-public.json`；公开根多一段 `channel_fixtures`（公开树上夹具的**真实** sha），`frozen_ref(channel=…)` / `check_manifest(..., channel=…)` 按通道取根。`genetask/packager.export_task(..., channel=…)` 按通道处理夹具身份：**私有通道逐字节不变**（仍是「声明什么就必须是什么」），公开通道把**盘上真值**写进导出的 X `task.yaml`，并保留防漏闸 —— 公开夹具的 sha **等于**私有声明值即当场红（那意味着私有数据漏进了公开树）。
② `ops/mk_instances.allocate_task_ids`：基点实例不再沿用基点题号，在变体发完号之后继续顺序发号（变体编号**一个都不动**），`row` 跟着写 `set_id=v1.0-instances` 与带指纹的 `subject_id`。
③ `gateway/sim_factory.task_dir` / `read_task_face` / `build_engine` 的 `set_id` **必填无默认**；`gateway/routers/sim.py` 的 `_SESSIONS` 键改成 `(run_id, task_id, set_id)`，工厂注册时一并登记本进程服务的 `set_id`（`GENEBENCH_SET_ID`，默认 `v1.0-smoke`）。
④ 10 条任务集记因从 `REFERENCE_REVISIONS` **搬**进 `REVISIONS`（逐字未改），两个元组一律升序（最后一条 = 当前号），`ops/manifests/v1.0-smoke.json` 的变更记录由它重出。
* **射程**：冻结根内只动了 `genetask/packager.py`（export_task 的通道分支）。实例表 `genetask/params/v1.0-instances.yaml` **字节未变** —— 它记的是 `{instance_id: 夹具 sha}`，而 `instance_id` 本来就带参数指纹；发号规则换掉的是 `task_id`，于是变的是清单里的 `instances` 段与 `instances_fingerprint`（40 个基点实例换了号，130 个变体一个都没动）。**题面一个字没动** —— 私有通道同一道题改前改后的 bundle 逐文件 sha256 相同（证据见 `ops/reports/f1_private_export_bitwise.md`）。
* **闸门 / 证据**：`ops/test_f1.py`：公开通道 5 道带 inputs 的题出得了集 / 防漏闸喂一件与私有声明相同的夹具当场红 / 私有导出逐字节不变 / 基点实例与冒烟题不再同号 / `task_dir` 对四道 S8 不再 RuntimeError / `REVISIONS[-1]['version'] == SET_VERSION`；外加 `ops/test_instances.py`、`ops/test_sim_factory.py`、`ops/test_y1.py`、`ops/test_release_manifest.py` 定向重跑。

### `1.0.15` — 2026-09-10　（票据 N-484 / N-543 / N-518（卡 A，用户裁定 ①②③⑤⑧））

* **为什么**：**一次重冻，压四件动冻结根的事** —— 分四次推版本等于让同一批题面有四个号，而其中三件题面一个字都没动。四件各自的病灶：
① **N-484**：公开 provider 的打包器在 `files.sha256` 生成之后又写了 `MANIFEST.sha256` 与 `build_info.json` 两件构建元数据，而 `genetask/pin.py::PROVIDER_META_FILES` 只豁免清单自身与 `manifest.json` —— 于是**公开通道的每一次注入**都在 P2 判红成「树里有而清单里没有」，而那棵树一个字节都没被动过。症状说 provider 被改了，病因是打包器多写了两个文件；照着报错去查 provider 的人查不到任何东西。
⑤ **实例层此前不在根内**：根只覆盖出集那 34 道题，而实例层有 130 道。换掉整张实例参数表，根 hash 一个字不变 —— 也就是说根答不出「这一次被测方拿到的是哪一批题」。
⑧ **`gateway/sim_engine.py` 有全树唯一一条「网关 import 答案面」**（`from reference.artifact_schema import LEGAL_TRANSITIONS, TRADABILITY_STATES, UNTRADABLE_STATES`）。红线 B2 不许 `reference/` 上执行面，于是单机双容器形态里网关**根本 import 不起来**，手册 §1.1「两种形态跑同一套代码」那句话不成立。
② ③ 是参考轴的事，记在 r1.0.22。
* **改了什么**：① `PROVIDER_META_FILES` 加 `MANIFEST.sha256` 与 `build_info.json`，**豁免面封闭成这四个字面名字**（写成前缀/通配会把「多出来的文件也是改动」整片关掉）。实测：公开树 2 条报错 → 0 条，私有树 0 条 → 0 条。
⑤ `instances_fingerprint` 进 `ROOT_FIELDS`；`genetask/params/v1.0-instances.yaml` 进 `CODE_FILES`。连带两处：`build_manifest()` 默认翻成 `with_instances=True`（不算就没这个字段，`manifest_root` 直接 KeyError）；`frozen_ref(verify=True)` 的现算比对**补上实例指纹**（不补的话「实例表改了没重冻」不会被任何一处发现 —— 本文件骂过三次的 F7 形态的第四次）。
⑧ 三个 S8 契约常量抽成 `genetask/s8_contract.py`（**零依赖**，不 import `reference/`）；`reference/artifact_schema.py` 与 `gateway/sim_engine.py` 双双改成引用它，**值逐字节不变**（改前改后快照 sha256 同为 `315a9ba4fa860b7c…`，见 `ops/reports/s8_contract_parity.txt`）。该文件同时进 `CODE_FILES`：它现在是 `DECLARATION_MEMBER_ENUMS` 与 `$.payload.*.state` 枚举的唯一来源，而 `artifact_schema.py` 改成 import 之后**改契约模块不会让参考轴的 sha 动一下**。
* **射程**：**题面逐字不变，出集清单不变（34 题）** —— 本次三件都不改任何 agent 读得到的正文。根 hash 变的原因是：`code` 段多了两个文件（实例参数表、S8 契约模块）、`genetask/pin.py` 的 sha 变了、且 `ROOT_FIELDS` 多了 `instances_fingerprint` 一项（**覆盖面变了也会让根变**，2026-09-05 拆轴时踩过一次，所以 `root_scope` 记着覆盖面）。
* **闸门 / 证据**：`ops/test_provider_pin_channel.py`（两条通道真注入 + 新增 ① 的八条：豁免面恰好四个名字 / 按名字不按形状 / 真缺文件仍红 / 内容不符仍红 / 非元数据的多余文件仍红 / 真树上清单覆盖除四者外全部 / 两条通道 P2 真树全绿）；`ops/test_s8_contract.py`（新，AST 判 `gateway/**` 零 `import reference` + 干净子进程真 import 引擎数 `sys.modules` 里的 `reference.*` = 0 + 三常量逐个与合并 sha 比对 + `is` 同一对象不是两份相等的 + 全树只有一处定义）；`ops/test_freeze*.py` / `ops/test_y1.py` 定向全绿。

### `1.0.14` — 2026-09-10　（票据 N-384 / N-383 / W3 实例层 / 六道欠定探针（卡 Y1））

* **为什么**：**agent 看得见的东西变了两处，都是「判据要的东西题面/schema 没说清」的收尾。**
① **N-384**：`PAYLOAD_SHAPE["S8"].events` 的 `required` 此前只有 `{ts, type}` ——而 Audit 的定义是「事件链可完整重放」，只有这两个键的链**重放不了**。卡 5.2 把字段写进了题面与 schema 的 `properties`，但**刻意没收紧 `required`**（当时的理由：会让合法样例与既有 121 份真产物集体变畸形，那是判据变更）。用户 2026-09-10 批了这次判据变更 —— 于是共享 schema 与题面**第一次真的等价**：题面说「order 事件必须带 order_id、symbol、side、qty」，schema 现在也这么要求。
② **N-383 的题面侧后果**：`fixed:output_format` 固定槽是**机器从 schema 的 `required` 生成**的，收紧之后 S8 五道题两臂的那一句从「events 含 ts, type」变成「events 含 ts, type, order_id」—— 题面确实不同了，必须推版本。（N-383 本身是参考轴的事，记在 r1.0.21。）
③ **实例层第一次进清单**（W3）：40 个基点 × 窗口/宇宙/因子池 → 130 个实例。它**不进根**（见 `root_scope` 与 `INSTANCES_NOTE`），所以不影响已发通行证；但「有哪些实例、每个实例的题面指纹与夹具 sha 是什么」从此有记录。
④ **六道欠定探针题仍然挂起**：W3 逐题判过，六道在 `materiality_screen` 里全部 `inconclusive`，而且是同一个结构性原因（筛查 harness 是三份冻结的 S7 回测引擎，S1–S5/S8 的探针字段根本没有进入它的入口）。照 screen 自己的判据「量不到不是没差别」，**一道都不放出**，`DIVERGENCE_EVIDENCE` 一个字未加。出集维持 **34 题 / 挂起 6 题**。
* **改了什么**：① `reference/artifact_schema.PAYLOAD_SHAPE["S8"].events.items`：扁平 `required` 收紧成 `[ts, type, order_id]`（四类事件的**交集** —— 题面对 order/fill/cancel/state 都写了「必须带 order_id」）；逐类的那一半走 `allOf` + `if/then`，逐字对着题面正文取：order → order_id/symbol/side/qty，fill → +price，cancel → order_id，state → order_id/state。**为什么不把逐类必填写进扁平 required**：那会要求 cancel 事件也带 price。
② `ops/specs/artifact_schema/v1.0/S*.json` 八份由 `ops/mk_artifact_schemas.py` 重生成（**只有 S8.json 变**），`genebench_client/emit_schemas.py` 的逐字副本同步重灌。
③ `reference/artifact_schema._s8` 补一条：每条事件都要有非空 `order_id`。**只收到 order_id 为止** —— 协议 validator（`ops/protocol/geneprotocol_v1`）的「够用子集」不认 `allOf`，评分器收得比它严会让 `ops/validator_parity.py` 的两个方向之一当场断。逐类字段仍由 L3 的 Audit 判（`scorer/l3.REPLAY_FIELDS`，且要求**有值**不只是键在）。
④ `reference/artifact_samples.py::s8()` 的合法样例补齐 order_id/side（并带上 `reference_close`，让 N-383 的 Slip 自洽判据在样例上演示得出来）；`ops/test_emit.py` 的 S8 最小样例、红队用例 `rt34_env2_03_S8_ts_mixed_precision_false_reject.json` 同补。
⑤ 判据锁 `ops/test_s8_event_fields.py::test_events_required_is_not_tightened_by_this_card` 换成三条新锁（扁平 required 是什么 / 逐类 required 逐字对题面 / 两者是交集关系）。
⑥ 实例层：`build_manifest(with_instances=True)` 第一次落盘，`instances` 段 130 条 + `instances_fingerprint`。130 个实例里 **47 个的夹具已物化**（S1–S5 与 S7），S6 的 15 个**没有** —— `reference/make_fixtures.s6_consumer_window` 要先在实例集根里看到引用 `reference/signals/*` 的题，而那些题正是它要出夹具的题（先有鸡还是先有蛋）。如实记 `fixtures: {}`，不假装有。
* **射程**：题面：S8 十份 `arms/INSTRUCTION.{strict,open}.md` 的 `fixed:output_format` 槽（机器生成，各 +1 个键名 `order_id`）—— **题面正文一个字没手改**。冻结根其余：`ops/specs/artifact_schema/v1.0/S8.json`。S1–S7 的题面逐字不变。出集清单不变（34 题）。清单新增 `instances` / `instances_fingerprint` 两段（**不在 `ROOT_FIELDS` 里**）。
* **闸门 / 证据**：40 题 build 全过 E1–E15/C1 零 problems；130 个实例 build 全过（`ops/mk_instances.py --build` red=0）；`ops/test_s8_event_fields.py` / `test_emit.py` / `test_artifact_schema.py` / `test_scorer_l3.py` / `test_protocol_validator.py` / `test_artifact_redteam.py` / `test_genetask.py` / `test_c42.py` / `test_instances.py` 定向全绿；S8 四题 oracle **私有 / 公开各一次真跑，4/4 零 finding**（gold 重出，见 r1.0.21）。

### `1.0.13` — 2026-09-07　（票据 N-103 / N-127 / N-128 / N-279 / N-126（卡 5.2））

* **为什么**：**出集清单实质变了**（N-103），外加两处「判据要求的东西题面没说」的补齐（N-127 / N-128）。五件事挤在同一次里，是因为它们都要重签题面，分开推等于让同一批题面有五个版本；而这是阶段五唯一一个没有在途 bundle 的窗口。
* **改了什么**：① **N-103**：`genetask/schema.py::DIVERGENCE_EVIDENCE` 加 `("rebalance_frequency", (("weighting_scheme", "equal"),))` 一条（正文由卡 1.1-c 的 `ops/reports/public/materiality_evidence.json` 原样搬来：三份冻结独立实现逐可行值各跑一遍，私有 26/26/27 共 79 处、公开 27/27/27 共 81 处指标超 daily 档 ε 带，两条通道都 material，Gate 0 双门均过、本字段不打补丁故 Gate 1 不适用）。**既有的 `sell_rule` 那条一个字没动。**证据到位 ⟹ `s6-rob-02` 从「不落盘」变成「落盘」，于是 `IN_V10` 的探针白名单从 `{s7-rob-02}` 变成 `{s7-rob-02, s6-rob-02}`，出集从 33 题变成 **34 题**；它的夹具 `work/signal_s5_gtja001_csi300_v1.parquet` 第一次物化，params 里那个全零占位 sha 换成真值；`tolerance.kind` 由 `cons` 改 `none`（与 s7-rob-02 同，N-93：诚实终止之后 gold 没有 targets 可比）。② **N-127 滑点符号约定**：S8 五道题**两臂**题面各加一行 —— `payload.fills.slippage_bps` 成交价高于计价基准时取正、低于取负，单位 bps。方向与指标规格 §3 的 `Slip = 量加权(成交价 − 决策时点价)` 同向。**判据不动**：`scorer/l3.compare_fill` 里 Fill / Slip 仍只报不判（改判据要另一轮红队）。③ **N-128 事件记录字段**：同样五道题两臂各加四行，写明 `payload.events` 的 order / fill / cancel / state 事件各必须带哪些键、`payload.state_transitions` 每条必须带 from / to / order_id；同一组字段补进 `reference/artifact_schema.PAYLOAD_SHAPE["S8"].events` 的叶子 `properties`（**只补不重写**，且**不收紧 required** —— 收紧会让既有合法样例与 121 份真产物集体变畸形，那是判据变更），八份 `ops/specs/artifact_schema/v1.0/S*.json` 由 `ops/mk_artifact_schemas.py` 重生成（只有 S8.json 变），`genebench_client/emit_schemas.py` 里那份逐字副本同步重灌。④ **N-279 s2-eco-01**：oracle 打 `/bars?universe=csi300` 不给 `code`，网关 422，两条通道同一条红 —— 「33 题零 finding」卡的就是它。取小改那条：只动参考轴的 `solve.py`，按 code 批量取并按网关 `MAX_ROWS` 反算分批（不动 `gateway/routers/market.py`，那会改 `declared_reads` 探针的分母口径且仍跨不过行数上限）。⑤ **N-126**：S6 的 TE 本来就没进 v1 判据（`scorer/l3` 出 note 说明），本次只登记，不改判据。
* **射程**：题面：S8 十份 `INSTRUCTION.{strict,open}.md`（每份 +5 行）。冻结根其余：`genetask/schema.py`（DIVERGENCE_EVIDENCE +1 条）、`genetask/params/v1.0-smoke40.yaml`（s6-rob-02 的 1 个 sha + 1 处 tolerance）、`ops/specs/artifact_schema/v1.0/S8.json`。出集清单 33 → 34 题。S1–S7 的题面逐字不变。
* **闸门 / 证据**：40 题 build 全过 E1–E15/C1 零 problems；`ops/test_s8_event_fields.py` 38 条；O1 两条通道各重跑受影响的题并合进累积记录 —— **私有 34/40、公开 34/40 零 finding**，两条通道逐题一致，not-ok 的六题就是仍无实质性证据、被 E9c 拦在落盘之前的六道欠定探针（s1/s2/s3/s4/s5/s8-rob-02）。也就是说**出集的 34 题全部零 finding**，完成定义里的「33 题」达成并多一题。

### `1.0.12` — 2026-09-07　（票据 卡 4.1（臂机制数据驱动））

* **为什么**：**题面与出集内容逐字节不变，推的是「输入变了」这条轴。**臂名此前是 `genetask/schema.py:32` 的一个元组，等价规则按「两臂成对」写死，注入器把「协议工件」与 `strict` 这个名字绑死 —— 加一个臂要改五处代码、改完还要重签题面。本次把臂集合变成数据（`genetask/arms.yaml`）之后，**决定题面的输入里多了一份文件**：它说了默认出几个臂、每个臂取哪一列措辞、变体臂追加哪一段文字。不把它收进冻结根，「把 default: false 翻成 true」这一下会静默改动每一道题的字节而版本号纹丝不动。
* **改了什么**：① `CODE_FILES` 收 `genetask/arms.yaml`，`CODE_DIRS` 收 `genetask/arms/`（变体臂的追加文本，agent 直接读到它）；② 渲染器/规则代码（render / packager / schema / bundle）本身按 N 臂泛化，它们本来就在 `CODE_FILES` 里，这次内容变了；③ 数据面文件分类（`packager.EXPORTED_FILES`，G3）改成按注册表展开题面文件名 ——原先写死 strict/open 两条，第三个臂的题面会被判「未归类」而整份题导不出去（出四臂 bundle 时实测撞到，与①②同属本卡，同一个版本号内重冻）。
* **射程**：**templates 根与 released_tasks 根一个字节没动** —— 漂移报告是「输入已变、题面未变（重冻即可）」。新登记的 `doc` / `hint` 两臂是 `default: false`，不进任何既有出集：40 题的 `task.yaml` instruction 段仍是`{strict, open}` 两条，`task_sha256` 未变。
* **闸门 / 证据**：钉住金丝雀 nonce / 时刻 / 子网分配之后，s2-cor-01 与 s7-rob-02 在改动前后的「出集全部文件 + 两臂干注入 run dir 全部文件」sha256 逐条相同（`/data/shared/genebench/scratch/4.1/{before,after}`，harness 自身的确定性另测一遍）。`ops/test_arms_registry.py` 31 条；`ops/test_inject.py` / `ops/test_genetask.py` / `ops/test_c41.py` / `ops/test_p2_contract.py` / `ops/test_budget_tiers.py` 413 条全绿。

### `1.0.11` — 2026-09-06　（票据 N-129（5.1 红队一轮首件））

* **为什么**：发给 GQ 臂的 validator 与评分器 L1 **判得不一样**：10 个带 `validator.log` 的真 run 里它报了 0 条，同批评分器判 `malformed` 的有 4 个。根因不是 validator 写坏了，是**规则数据不够细** ——`work/{stage}.json`（两臂共享）此前只到「这个键是 object、必填哪几个子键」，而真 agent 犯的错在叶子上：HTTP 200 写进 `status`、一句话写进 `alert`、紧凑串写进 `date`。
* **改了什么**：`PAYLOAD_SHAPE` 下到叶子（枚举 / bool / pattern / 上下界），八个 schema 文件随之重生成 ——**agent 拿到的规则变严变全了**，所以推任务集版本。
* **射程**：`reference/artifact_schema.PAYLOAD_SHAPE` + 8 个落盘 schema（它们在 code 段里，v1.0.10 起）。题面正文、模板、params 未动。
* **闸门 / 证据**：121 份真语料（23 份真 agent 产物 + 三控 98 份）上：validator 比 scorer 严 **0** 份、作用域内反向缺口 **0** 份、scorer 报而 validator 沉默 **0** 份（修前是 4 份）。工具 `ops/validator_parity.py`，测试 `test_parity_on_the_real_m6_corpus`。

### `1.0.10` — 2026-09-06　（票据 N-131）

* **为什么**：`ops/specs/artifact_schema/v1.0/{stage}.json` 会被逐字节复制成 bundle 里的 `work/{stage}.json`（**两臂都拿得到**），却不在冻结清单的 `code` 段里 —— 改它，agent 看到的东西就变了，而两条版本轴一动不动。2026-09-06 往里写取数约定时实测到这一点（freeze 报「与冻结清单一致」）。「任务集版本回答『agent 看到的东西变了吗』」这句话，在这条路径上本来不成立。
* **改了什么**：冻结清单的 `code` 段改为「显式清单 + `CODE_DIRS` 下的全部文件」，把 `ops/specs/artifact_schema/` 收进来。**文件内容本身这次没有再改**（取数约定是上一步 r1.0.17 写进去的）——变的是 `root_scope`：根覆盖的范围大了 8 个文件。
* **射程**：冻结脚本 1 处；清单里新增 8 个 `code` 条目。题面正文、模板、params 一个字没动。
* **闸门 / 证据**：根 hash 变（范围变了，**内容未变**，与 1.0.4 那次同形）；`instruction_fingerprint` 不变；40 题重建全 ok；两份报告的版本行改 v1.0.10 / r1.0.17。

### `1.0.9` — 2026-09-05　（票据 判据全仓改判（裁定 ②））

* **为什么**：`exact`（结构化 payload 逐键相等）**把 gold 的写法当成了标准答案**。两条实测：S1 上它让两份都合法、16 族探针全 clean 的产物判 0（N-114）；S2 上它让与 gold **逐字节相同**（同一个 sha256）的面板仍判 0.33 —— 扣的是 gold 的 dict 多带 `n_symbols` / `policy_applied` 这类描述键。判据必须是**指标规格 §3 的量**，不是写法。
* **改了什么**：params 的 `tolerance.kind`：S2 五题 → `align`（Align / Adj / Cal + 面板逐格比对）、S5 三题 → `sig`（三态一致率 + 逐日秩相关用已标定 τ）、S6 五题 → `cons`（Cons / Feas + 权重一致度）、S8 五题 → `fill`（Fill / Slip / Audit）。**全仓再无 `exact`**；`ops/test_scorer_l3.py::test_exact_only_for_file_sha_tasks` 把这条钉住。
* **射程**：params 18 行 + schema 枚举。模板与措辞表不动，题面指纹不变。
* **闸门 / 证据**：40 题重建全 ok；M6-lite 的 8 题按新判据重结算（不重跑 agent）。

### `1.0.8` — 2026-09-05　（票据 N-114 / N-104）

* **为什么**：① **N-114**：S1 的 `tolerance.kind=exact` 让 L3 比「取数台账逐字相等」，而题面**没有**规定取数粒度 ——Codex 两臂（整窗 3 条 / 逐标的 602 条）都合法、16 族探针全 clean，却双双判 0。指标规格 §3 给 S1 的是Cov% / PIT% / Prov。签字裁定改判据。② **N-104**：S8 的能力位闸（`s8_state_endpoint`）翻绿，五道 S8 题第一次真的能出集 ——此前 `freeze_v10.CAPS` 里写着 True、而运行时的 `ops/capabilities.json` 是 False，冻结清单里它们已在 `released_tasks`，生产路径上却一道都建不出来。
* **改了什么**：params：五个 S1 行 `tolerance.kind` exact → cov（新增枚举值，`genetask/schema.py::TOLERANCE_KINDS`）。S8 五题的出集不改清单（它们本来就在 `released_tasks`），改的是运行时能力位。
* **射程**：params（5 行）+ schema 枚举。模板、措辞表、夹具都不动。
* **闸门 / 证据**：40 题重建全 ok；S8 五题 oracle 真跑；A1 与 M6-lite 用新判据重结算（不重跑 agent）。

### `1.0.7` — 2026-09-05　（票据 N-99）

* **为什么**：N-99 裁定的三族夹具落地 —— agent 拿到的输入多了三份此前**没有定义**的文件（S4-ECO 的因子池、S6 的稠密/稀疏信号），`inputs[].sha256` 从 null 变成真值，题面因此重签。S4-ECO-01 与五道 S6 题此前**出不了集**（N-99），这一次是它们第一次有身份。
* **改了什么**：① `s4_eco_pool_v1`：30 因子（gtja_191 / worldquant_101 / qlib_alpha158 各 10，按 ID 排序等距抽样，剔退化与覆盖 <95%）；② `s5_gtja001_csi300_v1`：S5 oracle（s5-cor-01）gold 的信号；③ `s6_sparse_coverage`：每第 7 个交易日只留 3 个最小代码。三者 sha 写回 params；数据卡 `ops/data_cards/fixture_s4_eco_pool_v1.md`、`fixture_s6_signals.md`。
* **射程**：params（S4 pool 1 个 sha + S6 五题的信号 sha）。模板与措辞表不动。
* **闸门 / 证据**：s4-cor-01 / s4-eco-01 / s4-ops-01 / s4-rob-01 真跑零 finding；S6 真跑记在 r1.0.7。

### `1.0.6` — 2026-09-05　（票据 N-84 / N-86 / N-93 / N-98 / E15）

* **为什么**：**这一次改的是 agent 看得见的东西**，所以推任务集版本（前几次都只推参考轴）。四件事挤在同一次里，是因为它们都要重签题面，分开推等于让同一批题面有四个版本。**跳过 1.0.5**：那个号在下面已经被占用（2026-09-05 拆轴时改判为参考面变更），复用会出现两个同号条目。
* **改了什么**：① **夹具落地**（N-84）：S7 的 `s7_dedicated_signal_v1`、S4 的 `factor_panel`、S5 的 `inputs/*` 与清单，共 24 个 `inputs[].sha256` 从 null 填成真值 —— 夹具此前**没有身份**，换一份没有任何东西会报。② **N-86 改名**：`open_orders` → `pending_orders`。原名让 `s8-rob-01` 的每一次 `/sim/state` **与 `/sim/advance`** 都 422，agent 照题面做也一样，那道题谁都做不了。③ **N-93**：`s7-rob-02` 的 `oracle.expected` → `honest_halt`、`tolerance.kind` → `none`；并把 `oracle.expected` 改成由 `kind` 全映射决定（原来是二分支，探针题被静默归到 `full`，而 `full` 要求 gold 对被欠定字段择一填上 —— 那正是本题要抓的静默补全）。④ **S8 的 `as_of` 语义**（N-98）：题面只给一个平的冻结线日期，而 S8 的有效上界随模拟时钟走；`s8-ops-01` 更写着「请求 as_of 之后的数据会被拒」，照字面读是反的。补一句机器生成的注释，**两臂同给**。
* **射程**：params（24 个 sha + 1 处改名 + 1 处 tolerance）、phrasebook（改名）、packager（oracle.expected 全映射 + S8 as_of 注释）、schema（新增 lint E15）。
* **闸门 / 证据**：E15 扫全集 40 题**零命中**（首扫命中 1 题，即 N-86）；40 题 build 全 ok；`ops/test_vocabulary_e15.py` 含词汇表与引擎的对齐断言与逐类必红。**两族夹具仍无定义**（S4 的 `s4_eco_pool_v1`、S6 的两个信号），见 N-99 —— 它们的 `sha256` 还是 null，本次不假装它们有。

### `1.0.5（**已改判为参考面变更**）` — 2026-09-05　（票据 N-77）

* **为什么**：统一调用约定之后 40 题真跑，露出的**全部是端点形状的错误假设** ——每一处都只在真跑时才现形，而这些 oracle 从来没跑过：
① `pd.DataFrame(r.json()["rows"])` —— `rows` 是**行数（整数）**，数据在 `data` 里（S2/S5 共 10 个模板，那句 TODO「与响应体键名对齐」一直没做）；
② `/calendar` 的参数是 `start_date`/`end_date`，写 `start`/`end` **直接 403**；日期列是 `cal_date` 不是 `date`；
③ `/universe` 的参数是 `universe=`（`name=` **直接 422**），回包是 `{size, members}` 而不是 `data[].code`；
④ `/adj` 给 `ts_code`/`trade_date`，与 `/bars` 的 `code`/`date` 不同名；
⑤ S2 的 `get()` **一个身份头都没带** —— 网关日志按 (task_id, config_id) 切片，缺了这一半就切不出来，表现是「oracle 一次网关都没请求过」而其实请求了几百次；
⑥ S3 的日历索引没命名 → `stack()` 后 `reset_index()` 给出 `level_0` → `emit` 里 KeyError。
* **改了什么**：在**取数边界**上归一一次（列名别名表 + `/universe` 摊平 + 身份头），比在十几个调用点各改各的可靠 —— 漏一个只在真跑时才现形。S3 公共层给日历索引命名 `date`。S7 的共用主干抽到 `reference/s7_oracle_common.py`（D-31 推论：**模板不许 import 兄弟模板**，否则落到任务目录的那份不自足），并加 AST 锁 `test_a_template_never_imports_another_template`。
* **射程**：S2 五个 + S5 五个 + S3 公共层 + S7 五个模板。**题面一个字没动**，改的全是数据面私有的参考解。
* **闸门 / 证据**：契约锁 162 条全绿；`s3-cor-01` 与 `s2-cor-01` 已能跑通并产出 artifact。**S7 的 `fetch_panel` 与 S8 的取数仍是 `NotImplementedError`** ——抽取只解决了自足性，不代表能跑，这一点不许被「已抽取」四个字盖过去。

### `1.0.4` — 2026-09-05　（票据 N-75 + N-62）

* **为什么**：**两条原因，一次重冻结**（裁定 2026-09-05）。
① oracle 的调用约定有**六套**：七个阶段各写各的，光「artifact 写哪里」就有四个名字（`GENEBENCH_ORACLE_OUT` / `GENEBENCH_ARTIFACT` / `GENEBENCH_ARTIFACT_PATH` / `sys.argv[1]`），两套「任务规格从哪来」（env 里塞 JSON vs 读文件）。它们从没冲突过，因为**没有一个被执行过**。
② 三个 harness 的镜像基座互不相同（python:3.12-slim / node:22-slim / RD 自带），pandas 只有 RD 那个有且版本与题面钉的不一致 —— 而三条配置的全部意义是「同一模型、三种 harness，**固定模型效应**」。基座不同，主表上「harness 差异」这一列里就混进了运行时差异。
* **改了什么**：① 立契约：**oracle 的 I/O 契约 = agent 的 I/O 契约** —— 读标准位置的任务规格（`<task_dir>/task.yaml` + `taskspec.json`）、经网关取数、写标准 artifact 路径；唯一允许的环境变量是 `GENEBENCH_GATEWAY_URL`（**部署事实**，不是任务事实）与 `GENEBENCH_ORACLE_OUT`。实现在 `reference/oracle_io.py`，40 个 `solve.py` 的前言全部改写；S3 五题的取数/暖机/落盘抽到 `reference/s3_oracle_common.py`（那条 TODO 落地）。`ops/test_oracle_contract.py` 用 **AST** 锁死：任何 stage 特定 env 或 `sys.argv` 即红。
② 基座换成 `python:3.12-slim-bookworm` + **Node 22.23.2**（官方 tarball + 钉 sha256，不走 `curl | bash`），数值栈取三家里最高的 `pandas==2.3.3` / `pyarrow==25.0.1`。
* **射程**：① 40 题全部（改的是**数据面私有的参考解**，题面 INSTRUCTION / template.yaml / scorer.yaml 一个字没动）；② 39 个模板的 `Dockerfile`（在 `TEMPLATE_FILES` 里，进冻结面）。
* **闸门 / 证据**：契约锁 122 条全绿（含判别力：喂一个真读 stage 特定 env 的源码必须命中）；S3 端点形状按实测改正三处（`/calendar` 的 `cal_date`、`/universe` 的 `universe=` 参数、回包 `members`）。**跨版本数值核（统一基座 vs f01 qlib_env，全部指标相对差 1e-13 量级）是 A1 的前置，不阻塞本次冻结；不过则 v1.0.5。**

### `1.0.4（拆轴后 root 重算，**内容未变**）` — 2026-09-05　（票据 N-78）

* **为什么**：两条版本轴拆开（裁定 2026-09-05）：`solve.py` 是答案面，移出 `TEMPLATE_FILES`。**任务集的内容一个字没变**（题面 / schema / 镜像 / 夹具都还是 1.0.4 那份），但 root 覆盖的字段集变了，所以 root 值变了：`5a9c0616…` → `b4b058df…`。
* **改了什么**：root 的覆盖面写进清单的 `root_scope` 字段 —— 事后比两个 root 的人能看出「不一样」是因为覆盖面变了，而不是题面动了。版本号**不推**：推了会让人以为 agent 看到的东西变了。
* **射程**：只改 root 的覆盖面定义。答案面内容改在参考轴 r1.0.0。
* **闸门 / 证据**：两条轴各自的逐段红测试；`inject.json` 同时记两个版本。

### `1.0.3（**已改判为参考面变更**）` — 2026-09-05　（票据 N-72）

* **为什么**：40 题的 oracle **一次都没跑过** —— 每个 `solve.py` 末尾那句「自检：oracle 必须零 finding（O1）… assert validate(...)」是**注释着的**。真跑之后，S1 的四个参考解在三处上不成立：① `/universe` 的回包是 `{size, members}` 而解析按 `{rows, data[].code}` 写 —— 取到空列表，整道题一次 `/bars` 都没取，**却仍然产出一份看起来合法的 artifact**；② `fetched_at` 契约要求用网关回包的时间戳，而网关**不回显任何时间戳**；③ 行数字段名逐端点不同，缺省按 0 处理会把「没认出回包」判成 `empty`。
* **改了什么**：S1 四个模板的 `solve.py`：按实测形状解析 `/universe`（取 `members`，取不到成分**直接抛**而不是产出空壳）；`fetched_at` 只认新加的 `x-genebench-ts` 响应头（**不读日志自己填** —— 那会让被核值与基准同源，交叉核成恒真）；行数取 `rows`/`size`/列表长度，取不到**不默认 0**。
* **射程**：S1 的四个模板（cov_fields / lean_fetch / prov_ledger / source_status），覆盖 s1-cor-01 / s1-rob-01 / s1-eco-01 / s1-ops-01 四题。**题面（INSTRUCTION / template.yaml / scorer.yaml / Dockerfile）一个字没动** —— 改的是数据面私有的参考解。
* **闸门 / 证据**：四题真跑过 O1（零 finding），网关日志切片非空（602–2249 条）；同批修好冻结防漂本身 —— 它原来**比不到 `templates` 段**，正是这次改动没被它拦下的原因（见 N-74）。

### `1.0.2` — 2026-09-04　（票据 N-58①）

* **为什么**：「可用端点」固定槽是一个**不按 stage 区分**的字面量，于是 `/fundamentals` 写进了每一道题两臂的槽里 —— 每个 agent 都被告知可以查财报，而 v1 没有一道题需要它（40 题 gold 侧零调用，三条独立检索一致）。render 的 E8b 只管「正文端点 ⊆ 槽」，槽里多列一个不会被任何检查拦下。
* **改了什么**：端点清单改为按 stage 生成（`packager.stage_endpoints`）：v1 六个数据端点 + S8 的五个 sim 端点；`/fundamentals` 进 `V1_WITHHELD_ENDPOINTS`，出现在任何阶段即 import 期抛。同批：TradingAgents 适配器的 `get_fundamentals` 改接 `NO_SOURCE`。
* **射程**：全部 40 题的 `fixed:endpoints` 槽（S1–S7 少一个端点，S8 同）。
* **闸门 / 证据**：E1–E14 全过 40 题；`stage_endpoints` 的突变（把 /fundamentals 加回）必抛；另加一条断言：发放的端点必须都在网关 ALLOWED_ROUTES 里（发一个不存在的端点会得到 404，而 404 与越权在越权率上分不开）。

### `1.0.1` — 2026-09-04　（票据 N-44）

* **为什么**：三处产出物题面无路径与规范形（S3 values / S2 panel / S7 逐日序列），而 values_ref.sha256 是被计分的量 —— agent 不知道往哪写、写什么格式，两个同样正确的实现字节不同，跨实现比对本就不成立。
* **改了什么**：artifact_schema 加 PAYLOAD_FILES（路径/格式/列序/排序/索引），packager._output_files_phrase 机器生成，新增固定槽 fixed:output_files （两臂同给），S2/S3/S7 共 15 题（出集 13 题）的两臂模板各插一行。
* **射程**：S2/S3/S7；S1/S4/S5/S6/S8 的题面逐字不变。
* **闸门 / 证据**：E1–E14 全过 40 题；三条突变（两臂列序漂开 / 缺槽 / 路径写 work/）分别被 E3 / E1 / E8 拦下。

---

## 参考面轴（`reference_version`，24 条记录）

### `r1.0.23` — 2026-09-11　（票据 N-578（卡 F1，用户裁定 ③））

* **为什么**：**S8 四道题的 gold 此前算不出来，这一版让它重新算得出来 —— 于是「我们算 gold 的方式」变了，**必须推参考号。根因是任务集侧的同号（见 `REVISIONS` 的 1.0.16 ②）：`gateway/sim_factory.task_dir` 找到两个候选目录就 `RuntimeError` 不猜，而 S8 的 oracle 全部要经模拟盘会话才出得了产物。**不要把这条读成「gold 的数值变了」** —— 会话的构造参数（日历 / 收盘价 / 可交易性 / 声明）一个都没改，改的是「按哪个出集的 `task.yaml` 构造」这件事此前是歧义、现在是显式参数。
* **改了什么**：`build_engine(run_id, task_id, *, set_id)` 的 `set_id` 改成**必填无默认**，调用方（`gateway/routers/sim.py` 的工厂注册与两处物化路径）全部跟着传；会话键从 `(run_id, task_id)` 改成 `(run_id, task_id, set_id)`。冒烟集 S8 四题（s8-cor-01 / s8-eco-01 / s8-ops-01 / s8-rob-01）的 gold 重出。
* **射程**：**参考清单的字节没动**（40 个 `solve.py` 与 `REFERENCE_MODULE_FILES` 逐个 sha 相同）——变的是参考版本号本身，它在 `REFERENCE_ROOT_FIELDS` 里，所以参考根跟着变。**一处要照实说**：`gateway/sim_factory.py` 决定 S8 gold 的运行环境，却**不在** `REFERENCE_MODULE_FILES` 里（它住在网关侧，不在 `reference/` 下）——也就是说改它不会让参考根自己动，这一次是靠这条记因钉住的。已登记进 `ops/reports/known_limits_v1.md`。
* **闸门 / 证据**：`ops/test_f1.py::test_sim_factory_set_id_is_required` 与 `test_task_dir_no_longer_guesses_between_two_sets`；`ops/test_sim_factory.py` 全绿。

### `r1.0.22` — 2026-09-10　（票据 N-543 / N-518（卡 A，用户裁定 ②③））

* **为什么**：**两处参考解各有一个「看起来像值的非值」，而两处都没有任何东西会报错。**
② **N-543**：`genetask/templates/S6/*/solve.py` 读上游信号 parquet 的 schema metadata 取 `artifact_id`，取不到时兜底成字面串 `"TODO:signal-artifact-id-missing"`。协议只要求 `artifact_id` 是**非空串**，于是这个 TODO 一路通过校验，进了五份 S6 gold，又随 `broken.json` 进了适配赛道四例（`adapt-l1-08` / `l2-07` / `l2-08` / `l3-06`）。适配臂 INSTRUCTION 规则 1 要求「源里没有的写成显式 `unresolved`」—— 被测方照做，oracle 却要求原样抄回那个 TODO 串，`scorer/adaptation.py::match_oracle` 于是在 `provenance` 上判不一致。**被罚的正是照规则做的那一方。**
③ **N-518**：`S4/eco_free_select/solve.py` 的留出段是两个写死的日期 `2026-04-01..2026-06-30`，而窗口是实例层会换的取值。窗口一挪，这个划分就不再落在窗口里，**三种废法没有一种会报**：窗口挪到留出段之前（`s4-eco-02`/`04`）→ 留出段为空 → `ic_stats` 七个字段全 NaN，artifact 照写、照过 envelope 校验，直到结算时 7 条 `malformed:s4_ic_stat_not_number`；窗口挪到留出段之内（`s4-eco-03`）→ 训练段为空 → 所有候选 mean/std 皆 NaN → `t.abs().idxmax()` 返回 NaN → `"nan"` 被当成 factor_id 查因子池 → 崩在「池里没有 'nan' 的行」。**报错指着因子池，问题在那一行常量。**出集那 40 行每行只有一个取值，`s4-eco-01` 一直是绿的 —— 没人知道这道题的参考解不耐窗口变化。
* **改了什么**：② 五个 S6 模板的兜底值改成协议的显式欠定标记 `artifact_schema.UNRESOLVED`（= `"unresolved"`），**import 而不是重抄那个字面串**。**重出 S6 五题 gold，私有 + 公开各一次**（`s6-{cor,eco,ops,rob-01,rob-02}-01`），两条通道 5/5 零 finding，`provenance` 现为 `[{"stage": "S5", "artifact_id": "unresolved"}]`。
③ 两处修根因：
  * `reference/s4_oracle_common.py`：新增 `S4SampleTooThin`；`bh_fdr_select` **先筛掉算不出 t 的候选**（mean/std 非有限、std=0、n < `MIN_TRAIN_DAYS`）而不是原来的 `fillna(0)`——把「算不出」当成「t=0」会让它挤进 BH 的分母 m，**一个算不出来的候选因此能改变别人是否显著**；一个都不剩就抛，不返回 NaN。`summarize` 与 `ic_by_horizon` 在「一个 IC 都算不出 / 日期集为空」时抛，不交一份全 NaN 的 `ic_stats`。
  * `S4/eco_free_select/solve.py`：留出段**跟着窗口走**（`split_window`）——默认划分在窗口里切得出两段就用它（**出集那一行因此逐字节不变**），切不出来就按窗口自身的交易日位置对半分，并把 `holdout_rule=window_half` **如实写进 `payload.note`**（不许让回退的划分看起来像默认划分）；连对半分都切不出两段 10 天 → 抛 `S4SampleTooThin`，说清这道题在这个窗口取值上没有答案。`payload.holdout` 报实际用的那一段。
* **射程**：5 个 S6 `solve.py` + 1 个 S4 `solve.py` + 1 个参考模块（`reference/s4_oracle_common.py`）；S6 五题两条通道的 gold；S4-ECO 四个实例的 gold。**题面一个字没动**（那一半记在 1.0.15）。
* **闸门 / 证据**：S6 五题**私有 5/5、公开 5/5 零 finding**；S4-ECO 四实例（`s4-eco-01..04`）**4/4 零 finding** —— `s4-eco-03` 此前直接崩、`02`/`04` 各 7 条 malformed，实例矩阵由「零 finding 89/127、非零 2」变成「92/127、非零 0」。**基点 `s4-eco-01` 的 gold 在两棵树上都与 v1.0.14 逐字节相同**（`produced_at` 除外），证明 `split_window` 的默认分支没改动既有结果。

### `r1.0.21` — 2026-09-10　（票据 N-383（卡 Y1））

* **为什么**：**滑点的符号在我们自己的三份实现里不一致，而 Slip 就要被纳入判据了。**
`reference/s8_oracle_common.py::fill_metrics` 乘了一个 `sign = +1 买 / −1 卖`（docstring 写「买正卖负」），而另外两处都不翻符号：
* `ops/specs/GeneBench指标规格_v1.md` §3：`Slip = 量加权(成交价 − 决策时点价) bps`
* `gateway/sim_engine.py::slippage_bps`：`qty × (成交价 − 基准) / 基准 × 1e4`
买单两者同号、**卖单相反**。这件事此前不影响任何分数（Slip 只报不判），而 N-127 已闭（v1.0.13 把符号约定写进了 S8 五题两臂题面），用户 2026-09-10 因此批了「Slip 纳入 S8 判据」—— 纳入之前必须先对齐，**以规格 §3 为准**。
* **改了什么**：① 删掉 `fill_metrics` 里的 `sign`，docstring 改写并写明后果。
② **重出 S8 四题的 gold**：`s8-cor-01` / `s8-eco-01` / `s8-ops-01` / `s8-rob-01`，私有与公开两条通道各跑一次 oracle。**只有 `s8-cor-01` 的数变了** —— 它是唯一一道既有买单又有卖单的题（lifecycle：建仓 + 清仓），`slippage_bps` 由 **−202.514311 → +53.483048**；另外三道全是买单，逐位不变（−160.492521 / +26.587586 / −149.031264），两条通道逐位一致。
③ 判据侧（**不在本轴**，记在这里免得读的人找不到）：`scorer/l3.compare_fill` 把 Slip 从「只报不判」改成判 —— 判的是**自报与 agent 自己那条事件链的一致性**（重算 vs 自报），**不与 gold 比**（S8 题面没规定下哪些单，两轮不是同一个量的两次测量，同 N-114 的教训）。容差 = **一个最小价位**（A 股 0.01 元），逐单按该单的计价基准换成 bps 再量加权：`tol_bps(单) = 0.01 / 计价基准 × 10000`，`tol_bps = Σ 成交量 × tol_bps(单) / Σ 成交量`。换算式同时写进指标规格 §3 的脚注与 `scorer/l3.MIN_TICK_CNY` 的注释。
* **射程**：1 个参考模块（`reference/s8_oracle_common.py`）+ S8 四题两条通道的 gold。**任务集面的对应改动记在 1.0.14**（题面因 schema 收紧而重签，与本条无关）。
* **闸门 / 证据**：S8 四题私有 4/4 零 finding、公开 4/4 零 finding；`ops/test_s8_oracle_common.py` 的符号断言按新口径重写并新增一条「三处实现同号」的交叉断言（oracle 主干 / 网关引擎公式 / 评分器重算，同一笔卖单）。

### `r1.0.20` — 2026-09-07　（票据 N-279 / N-103（卡 5.2））

* **为什么**：两个 oracle 此前**跑不出干净产物**，而两者都只在真跑时才现形。
* **改了什么**：① `S2/eco_01/solve.py`：`/bars`、`/adj` 改按 code 批量取 + 按 `MAX_ROWS` 分批（网关不接受 `universe=`，且 300 只 × 约 1 840 个交易日 ≈ 55 万行 > 20 万行上限）；顺带补上与其余四道 S2 题同族的两处老问题 —— `get()` 没带身份头（网关日志切不出这一轮，表现是 `log=0`）与 payload 档位 `s2_adjust_report` 要求的 `adjust_applied` 一直没报。② `S6/rob_underdetermined/solve.py`：改成**诚实终止**。原实现出「窗口首个交易日建仓」一条，自己在 docstring 里留着 TODO 问这算不算与节奏无关；判据早就写着不算 —— `PAYLOAD_DEPENDS_ON["S6"]["targets"]` 含 `rebalance_frequency`，真跑当场判 `computed_despite_unresolved`。而 N-103 的证据正说明三种节奏不数值等价，oracle 不得替 agent 挑一个。改法与 S7 `rob_underdetermined` 同形（N-93）：`payload.targets` 出 null，落 `gold/underdetermined_note.json`，并现场自证「换成一个具体取值必被判 silent_completion」。
* **射程**：2 个 `solve.py`。**任务集面的对应改动记在 1.0.13**。
* **闸门 / 证据**：s2-eco-01 私有 / 公开各一次真跑零 finding（网关日志 8 条 = 2 + 2×3 批，与新的「理论最少请求数」逐字对上）；s6-rob-02 私有 / 公开各一次真跑零 finding。

### `r1.0.19` — 2026-09-06　（票据 卡 1.1-b / N-117 / N-68）

* **为什么**：公开通道并列：重建链路径参数化 + `calibration.json` 加 `ic_family`（N-117），**私有通道数值不变**。
① gold → 互检 → τ → ε → `calibration.json` 这条链原来把落点写死在 `snapshots/v1/` 上，公开通道要用**同一份代码**长出第二份产物 —— 复制一份「公开版链路」的表现是两条通道的口径慢慢漂开，而两边都照常算得出数。
② `ic_family` 此前是卡 1.2 用 `ops/merge_ic_epsilon.py` **事后插进**已落盘的 `calibration.json` 的，于是「再跑一次 `calibration.build()` 就把它抹掉」—— 抹掉之后 S4 回到 `l3_pass=None` / `effect=None`，**没有任何一处会报错**。公开通道从零重建这条链正好会踩上它，所以收进 `build()`。
* **改了什么**：`genebench_config` 加 `snapshot_root/gold_dir/crosscheck_dir/crosscheck_report/epsilon_dir/calibration_path/universe_dir/universe_pit_parquet` 八个通道函数（**只加不改**）；`reference/{factor_exec,calibration,epsilon,epsilon_dual,make_epsilon_panel}.py` 的落点改走这些函数，其中 `GOLD_DIR` / `OUT` / `EPS_DIR` 用 PEP 562 的模块级 `__getattr__` 按通道现算（这样 `factor_crosscheck` / `backtest` / `ic_epsilon` 这些下游一个字都不用改）；`factor_exec.init_qlib` 按通道取 provider，`_INITED` 从布尔改成**记住是哪个 provider**（只记布尔时同进程里切通道会静默沿用上一个）；`write_gold(root=)` / `calibration.build(out=)` 两个可选落点参数（不变性比对用）；`calibration._ic_family()` 用 `ops.merge_ic_epsilon.build_block`（**同一份代码**）把 `ic_epsilon_dual.json` 收进 `epsilon.ic_family`；`factor_exec` 加 `PanelStore` / `SpillPanelStore` 面板暂存面 —— `run()` 原来把 792 个面板同时压在内存里（csi1000 实测常驻约 22 GiB），2026-09-07 05:20Z 内核就是这么把公开 gold 收走的（`exit=137`，被杀前已退化到「一小时写一个 parquet」）；开了暂存之后峰值只剩几 GiB，**落盘产物逐字节不变**（暂存面只决定面板在被 `write_gold` 消费之前放在哪，用 pickle 原样进出，不做 dtype/index 转换）。
* **射程**：1 个配置模块 + 5 个参考模块（其中只有 `make_epsilon_panel.py` 在 `REFERENCE_MODULE_FILES` 里，所以参考根 hash 因它而变）。**题面正文 / 模板 / params / schema 一个字没动**，任务集版本不推。
* **闸门 / 证据**：私有 `calibration.json` 用新代码重建后**逐字节相同**（只有顶层 `built_at` 变；把它换回原值后 sha256 = `6920dd1f…` 与线上那份完全一致）；三宇宙 gold 各抽 3 个 parquet 的 sha256 不变；`ops/test_public_chain.py` 19 条，6 处变异逐条打红（含「`_INITED` 退回布尔」与「覆盖表漏一项」两处静默错误）；暂存面另加四条 —— 内存版与落盘版 `write_gold` 出来的 parquet 逐字节相同、帧的 dtype/index/NaN/inf 原样进出、`write_gold` 仍收普通 dict、`import ops.run_public_chain` 不再翻掉整个进程的通道。

### `r1.0.18` — 2026-09-06　（票据 N-129）

* **为什么**：同上：规则数据要下到叶子，源头在 `reference/artifact_schema.PAYLOAD_SHAPE`（`json_schema()` 的唯一输入）。
* **改了什么**：`PAYLOAD_SHAPE` 八个阶段补叶子级 spec。**评分器的判定逻辑一个字没改** ——这张表的唯一消费者是 `json_schema()`，也就是发出去的规则；修的是 validator 那一侧的可判性。
* **射程**：1 个参考模块 1 张表。
* **闸门 / 证据**：`test_json_schema_file_matches_generator` 八个阶段全绿；真语料一致性 0/0/0。

### `r1.0.17` — 2026-09-06　（票据 前视闸收窄 + 取数约定进两臂共享文件）

* **为什么**：裁定 2026-09-06（第 2 种读法）：**显式越界是意图，开区间是不知道 API 约定**。第一版把 `open_range_would_cross_asof` 也算进闸门，结果 20 个有产物的 run 里 19 个当场 invalid，而 125 次命中里 99 次是这一类 —— 它判的是「会不会用这个 API」，而那条 API 约定**题面没写**。「判据要求的东西，题面必须说」：约定得先给出去，越界的**意图**才配进闸门。
* **改了什么**：`LOOKAHEAD_DENY_REASONS` 收窄到六个**显式**越界 reason；新增 `UNBOUNDED_REQUEST_REASONS` 与 `count_unbounded_requests()`（遥测，进 Table A 的 `unbounded_requests` 列，不进闸门）；新增 `GATEWAY_FETCH_CONTRACT` 并由 `json_schema()` 落进 `work/{stage}.json` —— 那是 bundle 里**两臂都拿得到**的文件（`protocol/` 只给 strict 臂）。八个 schema 文件重生成。
* **射程**：校验器 3 处 + 八个落盘 schema。**任务集版本不动**（题面正文未改；实测冻结根一致）。
* **闸门 / 证据**：六个 reason 逐个必响且只响这一族；开区间不再进闸门（同一份日志上 gate 从 ['lookahead'] 变空）；两批 29 个 run 重结算后 lookahead 命中从 19 降到 6（`asof_beyond_freeze_line` 23 次 + `range_end_after_asof` 3 次），`unbounded_requests` 合计 165 次单列。

### `r1.0.16` — 2026-09-06　（票据 签字前三件之 ① / ②）

* **为什么**：① `lookahead` 族**没有发出点** —— 网关早就在按 as-of 边界拒，`reason` 也早就落进 access_log，缺的只是把它接到闸门上；在那之前它在主表上永远 clean，而 clean 的原因是**没人检**。② S2 的 gold 面板落在题目录根（裸 `open`，吃 umask），结算侧找不到 → `align` 只算 Align/Adj/Cal 三项 →三项满分 = 天花板 → **effect 100 而 l3_pass=False** 的矛盾。「判不了」必须表现成判不了。
* **改了什么**：① `artifact_schema` 加 `LOOKAHEAD_DENY_REASONS`（七个 as-of 边界 reason）与 `_lookahead`：日志切片里命中即 violation → 闸门；语法类的拒（`asof_missing` / `param_malformed`）**不算**；日志不可得时什么都不判（那是 unobservable）。② S2 的 oracle 把 `panel.csv` 落 `gold/`（走 `oracle_io.write_private`，0600；顺带让它收 bytes）；`scorer/l3.compare_align` 在 `gold/` 找面板，找不到就**整题未结算**（score=None → 效果分扣住），不拿其余三项凑分。
* **射程**：校验器 2 处 + oracle_io 1 处 + 1 个 solve.py；结算侧 `compare_align`。
* **闸门 / 证据**：七个 reason 逐个真跑必响且只响这一族；干净日志与语法类拒零误报；破坏样本从 13 族变 **14 族**；S2 四题 oracle 重跑后 `align` 的 CellAgree 算得出来。

### `r1.0.15` — 2026-09-06　（票据 r1.0.14 的回归）

* **为什么**：`Client.trading_days` 在 `frame()` 之后又按 `%Y%m%d` 解一次日期 —— 而 r1.0.14 刚把归一挪到 `frame()` 的边界上，于是它当场抛 `time data "2026-07-30" doesn't match format`。**`ops/test_gateway_client.py` 当场抓到** —— 归一挪位置这类改动，回归就藏在「谁还在自己解一遍」里。
* **改了什么**：`trading_days` 直接用归一后的 ISO（字典序即时间序），并加一条判据：混进非 ISO 就抛，不静默排错。
* **射程**：1 个参考模块 1 处。
* **闸门 / 证据**：`test_calendar_column_is_cal_date_and_is_renamed` 转绿；S4/S7/S8 三题 oracle 真跑（它们走这条路径）。

### `r1.0.14` — 2026-09-05　（票据 取数层归一收进客户端（裁定 ③））

* **为什么**：同一族 bug 今晚出现三次（S5 / S6 / S2）：网关各端点的日期与代码写法不统一，两路数据在 join 或输出上相遇 → **静默出空**。三次都是在模板里各修一份，而模板各写一份 `_COL_ALIASES` 正是它会再来第四次的原因。
* **改了什么**：`reference/gateway_client` 加 `iso_date` / `normalize_frame`（列名 + 日期值 + 代码写法）与 `assert_join_nonempty`（merge 完 `value_col` 全空即抛，并打印两侧键样例）；`Client.frame()` 走 `normalize_frame`；S2 五题的 `_normalize`、S5 四题的输出日期、S6 五题的 `trading_days` 全部改走公共层；S2 的合并加 `assert_join_nonempty`。
* **射程**：1 个参考模块 + 14 个 solve.py。
* **闸门 / 证据**：`assert_join_nonempty` 的判别力自测（紧凑 vs ISO 的 merge 当场抛）；S2 / S5 / S6 真跑零 finding。

### `r1.0.13` — 2026-09-05　（票据 冻结清单漏了 S4 公共层）

* **为什么**：`reference/s4_oracle_common.py` 是 r1.0.7 新收的公共层（S4 四题的取数 + IC 机器），却没进 `REFERENCE_FILES` —— 于是改它不会改参考根，「参考版本相同 ⇒ gold 相同」这条**不成立**。`test_reference_files_cover_the_whole_reference_plane` 抓到。
* **改了什么**：清单补该模块；根重算。
* **射程**：冻结清单 1 行（代码未变）。
* **闸门 / 证据**：该测试转绿；参考根从 951ddfe0 变为本次新值（**内容未变，只是覆盖面变了** —— 与 1.0.4 那次同形）。

### `r1.0.12` — 2026-09-05　（票据 S2 两题的 payload 档位键）

* **为什么**：`s2-ops-01` / `s2-rob-01` 的档位是 `s2_adjust_report`，它要求 `payload.adjust_applied`（申报**实际**用的复权口径，`adjust_fingerprint` 探针据此判）。两个模板都没写这一项 —— 于是它们的 oracle 产物一直被判 `payload_profile_key_missing`。此前这两条红混在跑批的一堆红里（日期 bug、网关超时）没被分开看；日期 bug 修完之后它们单独露出来了。
* **改了什么**：两个模板的 payload 补 `adjust_applied: decl["adjust"]`（cor_01 一直有）。
* **射程**：2 个 solve.py。
* **闸门 / 证据**：s2-ops-01 / s2-rob-01 真跑 2/2 零 finding；整批 O1 矩阵在 33 道出集题上 33/33 零 finding。

### `r1.0.11` — 2026-09-05　（票据 N-124 / S5 三题的 ISO）

* **为什么**：**同一族 bug 今晚第三次出现**：两路数据的日期写法不同（`/calendar` 给紧凑串 `20260105`，`/bars` 给 ISO `2026-01-05`），在 join / 输出上相遇，结果是**静默的空**或**格式非法**。① S2：`_normalize` 只归一列名不归一值 → `grid.merge(have, on=[code,date])` 一行都对不上 → gold 面板 41 700 行价格**全 NaN**，`missing_rows.count` 恰好 41 700，看着还像个正经数；**是 M6-lite 的真 agent 报 44（= 停牌格数）才把它顶出来**（N-124）。② S5 的另外三个模板（format_audit / free_signal / null_vs_flat）输出行的 `date` 是紧凑串，校验器逐行判 `s5_signal_row_malformed` —— r1.0.6 那次只修了 rank_signal 与内部键。
* **改了什么**：五个 S2 模板的 `_normalize` 补日期值归一；`cor_01` 加**生产路径判据**：面板价格全空即 SystemExit（并打印两侧 date 样例）—— 判据放生产路径不放测试（D-33）。四个 S5 模板输出行统一 ISO。
* **射程**：9 个 solve.py。任务集面不动。
* **闸门 / 证据**：s2-cor-01 的 `missing_rows.count` 从 41 700 变成停牌格数量级；S5 四题真跑零 finding。

### `r1.0.10` — 2026-09-05　（票据 S8 二次 pass 的两处根因）

* **为什么**：① **越权率两把尺**：契约 §6 写死「越权率 = **403 次数** / 请求总数，来源网关日志」，而 `_s8` 的交叉核按 `decision == "deny"` 数 —— 把 `/sim/advance` 走到窗口末的 **409 `window_exhausted`** 也算成越权。结果是**正确**的 oracle 产物（自报 0，它数的是 403）被判 `overreach_count_mismatch`：s8-cor-01 / s8-ops-01 两题。② **会话没有随运行重新开始**：`gateway_client` 的缺省 run_id 是常量 `f"{config_id}.{task_id}"`，而 S8 的模拟盘会话键是 `(run_id, task_id)`（N-88）—— 第二次跑同一道题复用了第一次的会话，`sim_date` 已在窗口末，`/sim/advance` 直接 409。真跑批里 run_id 由 runner 注入（每次不同），所以这条只咬**数据面直跑的 oracle**，而那正是 gold 的产出路径。
* **改了什么**：`artifact_schema._s8` 的越权核改数 403；`gateway_client` 的缺省 run_id 带**进程标记**（import 时算一次 —— 逐请求算会让同一进程的 `/sim/log` 与 `/sim/state` 落到两个会话上）。
* **射程**：校验器 1 处 + 网关客户端 1 处。
* **闸门 / 证据**：S8 四题 oracle 真跑 **4/4 零 finding**（此前 0/4）；`ops/test_artifact_schema.py` 等 141 条全绿。

### `r1.0.9` — 2026-09-05　（票据 N-93 落地 / 效果分锚定）

* **为什么**：① `s7-rob-02` 的 oracle 骨架断言欠定字段必须在 `ENGINE_FILL` 里，而本题实际欠定的是 `sell_rule` ——它**没有**等价取值（N-39 实测：三份 B 实现的 ann_return_gross 相对差 0.38–0.45% > ε）。于是这道题的 oracle **从来没跑出过产物**，而「没产物」在矩阵里显示成 `n/a`，与「跑出来是干净的」不是一回事。N-93 已把它的 `oracle.expected` 改成 `honest_halt`，骨架这一半没跟上。② 效果分的锚定归一（裁定 2026-09-05）落地，需要第三个**扣住理由**：两端锚点同分或某端算不出时归一化没有分母 —— 出 0 会把「无法归一」说成「零效果」。
* **改了什么**：S7/rob_underdetermined 增加诚实终止路径（依赖 `sell_rule` 的 metrics / attribution / ledger_check为 null，n_days 与 rebalance_frequency 照出；自检仍是两步：validate 零 finding + 换成具体取值必命中`silent_completion`）；`artifact_schema.EFFECT_WITHHELD_REASONS` 加 `anchor_degenerate` 并在`validate_scorer_output` 里补对应分支。
* **射程**：1 个 solve.py + 校验器的扣住理由集（冻结件，改动记在这里）。
* **闸门 / 证据**：s7-rob-02 oracle 真跑零 finding（诚实终止产物）；`ops/test_scorer_*.py` 全绿。

### `r1.0.8` — 2026-09-05　（票据 N-102）

* **为什么**：S6 五个模板的 `close_on` 逐 (标的, 日) 打网关：6 900 次 × 1.2 s ≈ 2 小时一题，40 题跑批与 M6-lite 都过不去。
* **改了什么**：`close_on` 改按标的一次拉整窗再查表（同端点、同 as_of、同字段，切片里那一天的值与单日请求相同）；旧的单日实现留作 `_close_on_single_day` 对照。**数值不变**，只少打网关。
* **射程**：5 个 S6 solve.py。任务集面不动。
* **闸门 / 证据**：S6 四题（cor/eco/ops/rob-01）真跑零 finding，targets 23/13/3/23 天；s6-cor-01 从 >2 h 降到约 1 分钟。

### `r1.0.7` — 2026-09-05　（票据 S4 公共层 / S6 日历列 / A1 前置）

* **为什么**：① S4 四个模板里三个还是桩（`ops_audit_trail` / `rob_sparse_panel` / `eco_free_select`），取数与 IC 机器只住在 cor 模板里；D-31 不许模板互相 import，所以收进参考公共层四题共用。② S6 五个模板读 `/calendar` 取 `r['date']`，网关给的是 `cal_date`（YYYYMMDD）——五题全 KeyError，S6 此前**从没真跑过**（它们一直被 N-99 挡在出集之外）。
* **改了什么**：新增 `reference/s4_oracle_common.py`（build_inputs / load_factor_panel / forward_returns / ic_series / block_bootstrap_ci / summarize / ic_by_horizon / bh_fdr_select）；S4 四题接线（eco：训练段 BH-FDR q=0.10 选因子，无幸存者时取 |t| 最大并标 `no_fdr_survivor`；ops：FETCHES = 客户端请求台账，不手写；rob：valid 过滤后再 rank）；S6 五题 `cal_date` → ISO。
* **射程**：1 个新参考模块 + 9 个 solve.py。任务集面的对应改动是 v1.0.7（夹具 sha）。
* **闸门 / 证据**：S4 四题真跑零 finding（eco 选出 gtja_191.126 / no_fdr_survivor）；s6-cor-01 真跑；跨版本核 `ops/reports/crossver_probe_a1.md`：oracle 环境 vs 统一基座 17/18 键逐位相同（唯一不同是 parquet 字节流 sha，值相同）。

### `r1.0.6` — 2026-09-05　（票据 红线 5 / S5 gold）

* **为什么**：① 24 个 S1–S6 模板的 artifact 用裸 `write_text`/`open(...,'w')` 落盘，吃 umask 落成 0664 ——网关的 ExecStartPre 守门（`ops/guard_modes.py`）在重启时当场拒起（S7/S8 那次已抓过同形态）。② S5 的 gold **6900 行全 null**：因子面板 code 是 `SH600000`，宇宙是 `600000.SH`，reindex 后全 NaN 而 rank 对 NaN 只是静默给 None；再加日历紧凑串 vs tradability ISO、rt07 要 ISO —— 三处格式各自为政。
* **改了什么**：S1–S6 全部走 `oracle_io.write`（0600）；S5 五个模板统一内部键为紧凑串、输出行 ISO、因子 code 归一到网关形态，且对「全对不上」直接 SystemExit 而不是静默出全 null。
* **射程**：24 个 solve.py。任务集面不动。
* **闸门 / 证据**：s5-cor-01 真跑零 finding（6796 有值 / 104 null）；`guard_modes.py` 绿。

### `r1.0.5` — 2026-09-05　（票据 N-84 / N-99）

* **为什么**：夹具生成器决定 agent 拿到的输入是什么，也就决定了 gold 在什么输入上算出来 —— 它必须在参考轴里，否则「参考版本相同」不再蕴含「gold 相同」。
* **改了什么**：新增 `reference/make_fixtures.py`（按题面 `inputs[].origin` 物化 S4/S5 夹具，**认不出的 origin 一律报错、不猜**）；`make_s7_signal.py` 改成把 sha 写回 **params**（题面的源头）而不是生成出来的 `task.yaml` —— 后者每次 `build_task` 都会重建，写进去下一次就没了。
* **射程**：1 个新参考模块 + `make_s7_signal`。任务集面的对应改动是 v1.0.6。
* **闸门 / 证据**：24 个 `inputs[].sha256` 落到 params；两族无定义的 origin 被点名跳过（N-99），`sha256` 保持 null —— 不假装它们有。

### `r1.0.4` — 2026-09-05　（票据 N-87 / N-96）

* **为什么**：S8 的四个 oracle **一行都跑不通**：端点路径全是占位（`/orders`、`/clock/advance`、`/state`），`reference_close` 必填没带，`client_order_id` 用 `uuid4`（gold 不可复现），而且全都拿 `task.as_of` 去请求 —— 而 S8 的 `as_of` 上界 = 当前 `sim_date`（契约 §3.1），拿冻结线那天去请求会被全面拒。
* **改了什么**：新增 `reference/s8_oracle_common.py`（`Sim` 会话：`as_of` 跟着 `sim_date` 走；事件与迁移取自 `/sim/log` 而不是各次应答 —— 契约 §4 审计日志是权威）；四个模板按实测端点重写，`client_order_id` 改成确定性；gold 侧的副产物一律走新的 `oracle_io.write_private`（红线 5：原先 `write_text` 吃 umask 落成 0664，网关的 ExecStartPre 守门在重启时当场抓到）。
* **射程**：1 个新参考模块 + 4 个 S8 `solve.py` + 5 个 S7 `solve.py`（补写标准 artifact 路径） + `oracle_io` / `files_io`。**任务集面不动。**
* **闸门 / 证据**：`ops/test_s8_oracle_common.py`(16)。真跑：s8-cor-01 / s8-eco-01 / s8-ops-01 **三题零 finding**（s8-rob-01 被 N-86 挡死，连 `/sim/advance` 都 422）。另修 `run_oracles.Result.ok` —— 它原来「没有产物」也算「零 finding」。

### `r1.0.3` — 2026-09-05　（票据 N-82）

* **为什么**：定义 S7 gold **输入**的那份代码原来住在 `scratch/` 下 —— 不在仓库、不在冻结清单、没有测试。
* **改了什么**：`scratch/export_input2.py` 收编成 `reference/make_epsilon_panel.py`，拆成「取数（qlib）」与「派生（纯函数）」两半，后者可测。
* **射程**：1 个新参考模块。**冻结面板的字节没有重建** —— 重建会引入 N-89 那类环境漂移，而且重建之后必须重标 ε。这次收编只是把记录放回受保护的地方。
* **闸门 / 证据**：`ops/test_epsilon_panel_builder.py`(15，四种形态各一条 + 多段成分区间 + 暖机)；外加已有的 `s7_panel_vs_frozen` —— 走网关的第二实现逐格对拍 984,960 格。

### `r1.0.2` — 2026-09-05　（票据 N-83 / N-84 / N-90）

* **为什么**：S7 收口：gold 引擎（裁定 N-83 = 实现 B2）与专用信号夹具（裁定 N-84）落地，外加实测出来的两处口径修正。此前 `run_engine` 调的 `backtest.run` / `config_from_declared` **两个符号都不存在**，S7 一道也跑不出产物。
* **改了什么**：新增 `reference/b2_engine.py`（加载冻结的 `impl_v2_b2.py`，两层内存补丁：P-SELL 开关 + 只记录不改算术的逐日台账；`config_from_declared` 逐字段映射、映射不上即报错）与 `reference/make_s7_signal.py`（`s7_dedicated_signal_v1` = 冻结 ε 面板的 signal 列）；`reference/backtest.py` 再导出这两个符号；`fetch_panel` 的 `close`/`factor` 落 **float32**（N-90：dtype 差别吃掉 ε 的 33.8%，降成 float32 之后与冻结面板逐位相同）；修 `ops_audit` 的 `/calendar` 调用（`Client` 没有 `.get`、参数名也不对）与 `eco_attribution` 写成单边的判别力判据。
* **射程**：2 个新参考模块 + `s7_oracle_common` + `backtest` + 2 个 S7 `solve.py`。**任务集面不动**；信号夹具落进任务目录但 `task.yaml` 的 `inputs[].sha256` 留到夹具那次一起填、一起推任务集版本。
* **闸门 / 证据**：`ops/acceptance/s7_b2_wrapper_gate.py` 四门（包装与今天的 B2 逐位相同 11/11；台账补丁逐位中性；sell_rule 开关咬得动 8 项；上层 metrics 与 B2 逐位一致）；`s7_panel_vs_frozen` 收紧成逐位相等（984,960 格，max_rel_diff 0.0）；`ops/test_backtest_b2.py`(49，逐声明字段各一条必红)。S7 五题真跑 **4/5 零 finding**（s7-rob-02 见 N-93）。

### `r1.0.1` — 2026-09-05　（票据 N-82 / N-83）

* **为什么**：S7 的 oracle 此前**不可能跑通**：`reference/gateway_client.py` 根本不存在，`fetch_panel` 是一句 `NotImplementedError`。这次把取数与拼面板做出来 —— 面板是 S7 gold 的全部输入，它错了 11 项指标会一起偏而没有一处报错。
* **改了什么**：新增 `reference/gateway_client.py`（端点形状按实测收口：`/bars` 与 `/adj` 的**日期格式不同**、`code` 是重复参数可批量、分批按网关 `MAX_ROWS` 反算）；`fetch_panel` 按契约 §1 拼八列全格面板，三条口径都是对着冻结 ε 面板实测定的（`factor` 基准日 = `as_of` 见 N-80；`is_delisted` = 最后有价日之后 见 N-81；`factor` 在无价格的格上置空 见 N-82）；`run_engine` 在实现 B 缺位时**明说阻塞**，不 fallback 到实现 A。
* **射程**：1 个新参考模块 + `s7_oracle_common` + 5 个 S7 `solve.py`。**任务集面不动**（题面/schema/镜像/夹具都没碰）。
* **闸门 / 证据**：`ops/acceptance/s7_panel_vs_frozen.py` 全表 984,960 格对冻结 ε 面板：`close` 相对差 5.95e-08、三个布尔列各 0 格不一致、行集合两侧完全相同；`ops/acceptance/s7_panel_factor_immaterial.py` 双向证 `factor` 空值差无影响；`ops/test_gateway_client.py`(21) + `ops/test_s7_panel.py`(28，含验收门 11 段逐段必红)。

### `r1.0.0` — 2026-09-05　（票据 N-78）

* **为什么**：**参考轴的起点。** 在此之前，答案面的每一次改动都被记在任务集轴上（v1.0.3 = S1 oracle 调用链修正；v1.0.4 的一半 = 统一 I/O 契约；v1.0.5 = 端点形状四层 + S7 主干抽取）—— 三次里有两次**题面一个字没动**。拆轴之后这些内容归本轴，任务集版本回到 1.0.4。
* **改了什么**：`solve.py` 从 `TEMPLATE_FILES` 移入 `REFERENCE_TEMPLATE_FILES`；新增 `REFERENCE_MODULE_FILES`（`oracle_io` + 各阶段 `*_oracle_common`）；两条轴各自 manifest、各自根 hash、各自「喂真改动必红」测试。
* **射程**：39 个模板的 `solve.py` + 3 个参考模块。**任务集面（题面/schema/镜像/夹具）不动。**
* **闸门 / 证据**：两条轴的逐段红测试；`inject.json` 同时记两个版本，可比性要求**两者都相同**。

---

## 本仓库的里程碑

版本轴记的是「题面 / gold 变没变」，里程碑记的是「这套东西长成了什么样」。
两者不同步：一个里程碑里可能一次版本都没推。

| 里程碑 | 是什么 | 一句话 |
| --- | --- | --- |
| **M0** | 环境闸门与湖基线 | 落点、权限红线、数据湖只读基线；`ops/test_env.py` 的递归权限审计从这里开始 |
| **M1** | 数据面：宇宙 / 可交易性 / as-of 网关 / 快照表 | `universe_pit`（三源合成 + 在市窗口闸门）、`tradability`（五档互斥 status）、只读 HTTP 网关（绑显式地址，不绑 0.0.0.0） |
| **M2** | 冻结 provider + gold + τ/ε 标定 + artifact schema | 自建 qlib provider（日历里**物理上没有**冻结线之后的交易日）、三宇宙 792 因子的 gold、τ = 0.984006、ε 分档（只有 daily 可用）、八阶段 artifact schema v1.0 |
| **M3** | 出题与打包：v1.0 冒烟集冻结 | 40 题起草 / 34 题出集；冻的是**输入**（模板 + 措辞表 + 参数表 + 渲染器代码），不是渲染产物 |
| **M4** | runner 隔离拓扑、出向白名单、两臂注入器 | 容器隔离、出向代理只放模型 API 域名、两臂 work/ 文件集的**等号**判据 |
| **M5** | 结算面：闸门 + L3 + 主表 | 有效性闸门语义（invalid 而非低分）、四种 L3 比法、Table A/B |
| **M6** | 跑批与结果库 | 作业清单 → 结果库（四条版本轴缺一即拒）→ 三张表（混轴默认拒绝出表） |
| **阶段一~六** | 从「跑得起来」到「可分发」 | 公开数据通道、三范式接入、通用 harness、臂机制与适配赛道、跑批与结果库、发布件 |

**「可分发」的完成定义不是「跑得通」**：它要求外部用户照手册能把这套东西用起来。
今天还差三件事，逐条在 [`RELEASE_MANIFEST.json`](RELEASE_MANIFEST.json) 的 `blockers` 里，
也逐条在 [`ops/reports/known_limits_v1.md`](ops/reports/known_limits_v1.md) 的收口核对一节里。
