# 卡 3.1 设计面板产出（2026-09-02，harness 视角为骨架）

评分：{"protocol": 47, "harness": 62, "scoring": 58}

# 卡 3.1 GeneTask 打包器 —— 最终实施设计

## 0. 结构与三条裁定

**一行参数 → 数据面全量 `task.yaml`（f01 `$GENEBENCH_ROOT/reference/tasks/v1.0/<id>/`，非 git、0700）→ `export()` 剥 D 键落执行面 bundle（f02 `/data/genebench_runner/tasks/<id>/`）**。卡 2.3 的 TaskSpec 是全量 task.yaml 四键的原样切片 `taskspec()`，不另存。对评委三项特别检查的裁定：

1. **oracle 不进容器**。`solution/solve.py` 在 f01 直跑，经网关 snapshot 后端（请求头 task_id / config_id=`oracle`）产 artifact，S1/S3 交叉核用真实网关日志。红线 5 不留例外。
2. **私有物只落 `reference/`**。`tasks/_private` 否决：`tasks/` 随裸镜像同步、L-5 按 `/tasks/` 放行。import 期断言 `git ls-files` 与 f02 同步清单均无 `reference/tasks/`（查配置态，D-06 第 7 例）。
3. **X 面最小化 + 构建上下文隔离**。执行面 task.yaml 只留 runner 消费的键（kind/family/probes 全归 D）；Dockerfile 在 `image/` 子目录，构建上下文就是它，`COPY .` 够不到 task.yaml。

## (a) task.yaml 字段表

面：**D** 仅数据面 · **X** 执行面 task.yaml（runner 读）· **C** 进容器 `/task`。

| 字段 | 类型 / 约束 | 消费者 | 面 |
|---|---|---|---|
| `schema_version` | 必须是 **字符串** `"1.0"`（YAML `1.0` 浮点即拒） | 全部 | X |
| `task_id` | `^s[1-8]-(cor\|rob\|eco\|ops)-\d{2}$`，集内唯一；探针题同族编号顺延 | runner env、日志切片、scorer | X,C(env) |
| `set_id` / `task_sha256` | `v1.0-smoke`；bundle 内容哈希 | 报告器按集/版本切片 | X |
| `stage` | ∈ `STAGES` | TaskSpec | X |
| `as_of` / `window{start,end}` / `universe` | as_of ≤ 2026-07-31；end ≤ as_of；universe ∈ universe_pit 四宇宙 | 题面、scorer PIT 探针 | X（as_of 只经题面进 C，不加环境变量）|
| `instruction{strict,open}` | `{path,sha256}` 指向 `arms/INSTRUCTION.*.md`，runner 按 `GENEBENCH_ARM` 复制为 `work/INSTRUCTION.md`（沿 4.1 现有路径） | runner | X；选中臂进 C |
| `image{base,digest}` / `timeouts{agent,test}` | 基础镜像按 digest 钉死；test ≤ 120s | runner compose | X |
| `inputs[]` | `{path,sha256,origin,max_date}`；path ⊆ `work/`；max_date ≤ as_of；sha ∉ **全集** gold sha 集 | runner 复制、scorer | X,C |
| `artifact_path` | 固定 `/task/artifact.json` | tests、parser、scorer | X,C |
| `contract_ref[]` / `artifact_schema_ref` | 只允许 `ops/specs/**` 结构文件，禁 `reference/**` | strict 臂、Audit | X；schema JSON 进 C |
| `status` / `packed_at` / `packager_version` | draft→packed→exported→signed | 全部 | X |
| `declared` | 键 ⊆ `DECLARATION_FIELDS[stage]`；值过 ENUMS/SHAPES；∉ VIOLATIONS；S4 冻结项 == FROZEN_CALIBRATION 且 holding_periods ⊆ {1,5,20}；S7 `adjust=post`、`rebalance_frequency=daily`（ε 仅 daily usable） | TaskSpec；臂槽位值源 | D（值只经题面进 C）|
| `underdetermined` | 与 declared 不交、并集 == 该阶段全部声明字段；probe 题恰 1 个 ∈ `UNDERDETERMINED_CANDIDATES[stage]`，否则 `[]` | TaskSpec | **D** |
| `kind` / `family` / `subject_id` | kind ∈ {regulated, underdetermined_probe, free}；probe 题 family 固定 **ROB**、subject 取该阶段 ROB 科目（可执行规则，报告器不再因人而异） | 覆盖校验、报告器 | D |
| `probes{armed, expected_unobservable, target_field}` | ⊆ PROBE_IDS；S3 ⊇ declared_reads、S7 ⊇ ledger/attribution；target == underdetermined[0] | scorer | D |
| `gold_ref` | `{path,manifest_sha256}`，前缀 `reference/`；S3/S4/S5 为**按题切片**的 parquet（单因子×窗口，MB 级），metadata 带 gold_token | scorer | D |
| `solution_ref` / `oracle{expected}` | `solution/solve.py`；expected ∈ {full, calibrated, validate_only(free 题)} | 3.2 oracle 验收 | D |
| `null_agent{behavior, expected_findings[]}` | behavior ∈ {empty, default_fill, copy_input}；findings 须不依赖网关日志即可命中 | 3.2 判别力验收 | D |
| `scorer_ref` / `tolerance{kind,tier}` / `anchor{floor,ceiling,status}` | scorer.yaml；S3 τ、S7 ε 且 tier usable；free 题 anchor 可 `pending`（出包允许、效果**禁止结算**） | 5.1/5.2/5.4 | D |
| `judge_sha256` / `judge_written_at` | == sha(taskspec.json + scorer.yaml)；时间早于 `arms_rendered_at`；同时追加进 `_ledger.jsonl` | D-11 审计 | D |
| `canary{gold_token, control_token, x_token}` | 各 `GBC-<id>-<16hex>`；gold_token 只在数据面私有文件与 gold 切片 metadata；control_token 只在两臂题面各恰 1 处；x_token 只在 X task.yaml | 扫描器非空证明 | D |

## (b) 参数表与实例化

`params/v1.0-smoke.yaml`（YAML，非 CSV——S7 的 cost_model/strategy 是 dict），一行一题，列 = 模板推不出的量：`task_id stage family subject_id kind template_id as_of window universe declared underdetermined inputs_args gold_args null_behavior tolerance_tier timeouts`。模板 `templates/<stage>/<template_id>/`：`INSTRUCTION.{strict,open}.md.j2`、`solve.py.j2`、`scorer.yaml.j2`、`inputs.py`（从 snapshot 物化材料并断言 max_date ≤ as_of）。列集与模板 `slots:` 必须相等（少报错、多报错）。

实例化顺序（D-11 固化）：① 行 → `taskspec.json` + `scorer.yaml` 落盘、写 ledger ② 物化 inputs、切 gold ③ 渲染两臂 ④ 全量 task.yaml ⑤ 校验 (c) ⑥ oracle/null 干跑 ⑦ `export()`。探针题与规定题**共用模板**，只有参数行把一个字段从 declared 挪到 underdetermined。

**双臂生成**：模板不写字段值，一律 `say(field)`；`phrasebook.yaml` 对每个 (field, value) 给 strict/open 两种措辞。屏蔽在**渲染期**：`say()` 对 `f ∈ task.underdetermined` 抛错（不是「phrasebook 没条目」——同一模板既出规定题又出探针题，条目必然存在）。渲染时记录槽位集，产 `arms/slots.json`（槽位→两臂原句）与 `arms/equivalence.md`（逐槽三列：id / strict 句 / open 句 + 固定项核对表）；签字人**查表不查散文**，落 `SIGNOFF`。

## (c) 校验规则（每条配负例，负例集 `ops/negctl_genetask/`，每例 `exclusive`）

| # | 规则 | 负例 |
|---|---|---|
| R1 | 过 GeneTask JSON Schema；schema_version 为字符串 | YAML 数字 `1.0` |
| R2 | declared ∪ underdetermined == DECLARATION_FIELDS[stage] 且不交 | S2 漏 `alignment_target` |
| R3 | declared 值合法、不在违例表、S4 冻结、S7 adjust=post & daily | S7 `adjust: pre`；S7 weekly 题 |
| R4 | kind 互锁：probe ⇒ 恰 1 个 ∈ 候选表；否则 `[]`；probe 题 family==ROB | regulated 题欠定 adjust |
| R5 | 集覆盖：每阶段 5 题、四族齐、probe 恰 1、free 仅 S3/4/5 各 1 | 删 S6-OPS 行 |
| E1 | 两臂**槽位集相等**且 == declared 键 ∪ FIXED_SLOTS，每槽恰 1 次（替换原 jinja2.meta 比法） | strict 多说一次 `universe` |
| E2 | 每槽 strict 措辞在 strict 臂、open 措辞在 open 臂；欠定字段名与其**全部**取值的 phrasebook 措辞（含 strict 记号如 `adjust=`、open 词如「后复权」）在两臂零命中，按词边界+lexicon 扫描而非裸词 | open 臂写「后复权」而 adjust 欠定 |
| E3 | as_of、网关 URL、artifact_path、S3「fields 必须显式」在两臂都出现 | open 臂漏 as_of |
| S3a | S3 `required_fields` 非空 ⊆ BARS_FIELDS ∪ 其它端点字段 | `vwap2` |
| S3b/S8b | 状态锁：S3 需 `ops/gateway_capabilities.json` n33=true（由 `test_bars_serves_open_amount_vwap_since_n33` 翻转）；S8 需状态端点存在；锁未开只许 `draft`，禁 export | 加列前 export S3 |
| A1 | as_of ≤ 冻结线；window.end ≤ as_of；inputs.max_date ≤ as_of | 材料含 08-01 |
| G1 | gold/solution/scorer/canary 前缀 `reference/`，目录 0700，不在 git 与同步清单 | gold_ref 指 `tasks/` |
| G2 | bundle 任一文件 sha ∉ 全集 gold sha 集；gold_token 0 命中 | gold metrics.json 拷进 work/ |
| G3 | 数据面每个私有文本文件与 gold 切片 metadata 含 gold_token（taskspec.json 除外——它只许四键） | solve.py 无 token |
| G4 | `export()` 后 X task.yaml 键集 == X_KEYS（`assert_export_is_key_free` 同款）；x_token 在 image/ 与 work/ 中 0 命中 | 手工加回 `underdetermined` |
| G5 | `tests/` 不 import `reference.*`、无 gold/answer/probe 字样 | `from reference.artifact_schema import` |
| L1 | Dockerfile：FROM 带 digest、无 `ADD http`、无运行期 pip；**COPY/ADD 源只能解析到 `image/` 内**；两臂 compose 各过 `lint_compose` | `COPY ../task.yaml` |
| C1 | control_token 在每臂题面恰 1 命中（扫描器非空）；runner 收尾扫 work/、容器层、轨迹、代理日志：control_token ≥1 否则该次扫描无效，gold_token/x_token 命中 ⇒ run 级状态 `leaked`（单列，不算分、不入 gate_failed） | 改坏扫描正则 |
| O1 | oracle 产物 `validate(art, task=taskspec()).ok` 且零 finding；再做一次已知突变（probe 填默认值 / 其余改一个声明值）必须变红 | 突变仍绿 ⇒ 校验为空 |
| N1 | null 产物按 behavior 生成后 ≥1 finding 且 ⊆ expected_findings（default_fill ⇒ silent_completion；empty ⇒ malformed） | oracle/null 都过的题 |
| J1 | judge_sha256 与实际一致、ledger 有记录、时间早于臂渲染 | 打包后改 scorer.yaml |
| D3 | import 期恒等式：TASK_FIELDS == schema.properties；X_KEYS ⊔ D_KEYS == TASK_FIELDS；declared 允许键从 artifact_schema 生成 | 加键不入任一集合 |

## (d) 目录布局与红线 5 落点

```
f01  $GENEBENCH_ROOT/reference/tasks/v1.0/<id>/        0700，非 git
       task.yaml  taskspec.json  scorer.yaml  canary.json  SIGNOFF
       solution/solve.py   gold/<slice>.parquet+manifest.json   arms/{slots.json,equivalence.md}
     $GENEBENCH_ROOT/reference/tasks/v1.0/_ledger.jsonl        判据先落盘的追加账
f02  /data/genebench_runner/tasks/<id>/                  export 产物
       task.yaml(X 键)  arms/INSTRUCTION.{strict,open}.md
       image/{Dockerfile, run-tests.sh, tests/test_outputs.py}   ← 唯一构建上下文
       work/{inputs…, S{k}.json 结构 schema}               ← 挂为 /task
```
`tests/test_outputs.py` 只查 artifact 存在、schema_version 为字符串、stage/task_id 与 env 一致；容器 tests 恒为结构自检，runner parser 以 f01 scorer 结局为准。oracle 与记忆探针答案（`reference/memory_probe_answers/`）同受 0700、网关路径禁词、`runner/` 源码禁 import 三道门。S7 材料是**专用信号**（不复用任何 S5 题的 gold），故 G2 可按全集 sha 拦。共享面板 gold_factors 不按题植 token，只靠 0700 + 按题切片；金丝雀只抓文件级搬运，内容级（转 CSV）由 oracle 不进容器 + 目录权限守——已知边界，写进验证验证器报告。

**接口**：卡 2.3——`_task_context_sane` 不单独调用，经 O1 的 `validate(oracle, task=taskspec())` 顺带覆盖；探针题 artifact 的欠定字段须显式 `"unresolved"`。卡 4.1——沿用 `work/` 与 `work/INSTRUCTION.md`、`GENEBENCH_ARM`，不新增 `GENEBENCH_AS_OF`（D-10）；`parser_name=genebench`，容器 tests 恒为结构自检；打包器把 `task_sha256/set_id` 先写进 `result_json`，DDL 加列后迁移。卡 4.3——validator 工件只许 `ops/specs` 结构 schema 且两臂同给，`work/` 与臂无关（W1）。金丝雀三串带前缀 `GBC-G-/GBC-C-/GBC-X-`，扫描器按前缀归因。

## (e) 与卡 3.2 的覆盖矩阵

每阶段 5 行 = COR/ROB/ECO/OPS 各 1 + probe 1（双标 ROB，占族名额）。

| 阶段 | 欠定字段（probe 行） | ECO 行 kind | 状态 |
|---|---|---|---|
| S1 | calendar_id | regulated | active |
| S2 | adjust | regulated | active |
| S3 | eval_frequency | **free**（anchor pending） | draft，等 S3b |
| S4 | holding_periods | **free** | active |
| S5 | signal_frequency | **free** | active |
| S6 | rebalance_frequency | regulated | active |
| S7 | first_rebalance_day（adjust 被契约钉死，不可欠定） | regulated | active |
| S8 | calendar_id | regulated | draft，等 S8b |

真实可 export：**30 题**；N-33 补丁推送后 35；S8 状态端点落地后 40。记忆探针 33 项不走本打包器（裸 prompt、无双臂、无容器），只共享 set_id 与红线 5 目录。3.2 验收 = 40 行过 R5 + 每题 O1/N1 干跑 + 签字人抽 `equivalence.md`。

## (f) 未决问题

见结构化清单；标 **[签字]** 者须签字人裁定。


## 未决问题（面板合并）

- [签字] UNDERDETERMINED_CANDIDATES 每阶段取哪个字段——本稿定 S1 calendar_id、S2 adjust、S3 eval_frequency、S4 holding_periods、S5 signal_frequency、S6 rebalance_frequency、S7 first_rebalance_day（adjust 被 backtest_adjust_off_contract 钉死 post，欠定它探针语义不成立）、S8 calendar_id；S3–S6 无法逐字执行实施稿「不声明复权或日历」，需签字替代字段。
- [签字] 探针题 family 固定记 ROB、subject 取该阶段 ROB 科目并占族名额（每阶段 5 题够用）；三份设计一致采用，本稿写成决定，请确认或改为「取最自然一族」并给可执行规则。
- [签字] oracle 不进容器：solution 在 f01 直跑、经网关（config_id=oracle）产 artifact。代价：oracle 不走容器隔离拓扑与代理，S8 越权探针、egress 侧前视探针对 oracle 的零误报只能在数据面验；换取红线 5 无例外。
- [签字] free 题（S3/S4/S5 ECO 行）anchor 在卡 5.4 之前为 pending：允许出包与 oracle validate_only 验收，效果分禁止结算（effect=null, reason=anchor_pending）。是否符合 D-11「判据先于被判之物」的口径，还是要求 5.4 阶梯先于这三题落盘。
- [签字] S3/S4/S5 gold 按题切片（单因子×窗口×宇宙，MB 级）并写 parquet metadata gold_token，共享面板 gold_factors 本体不动、只靠 0700。金丝雀因此只抓文件级搬运（parquet→CSV 会丢 metadata），内容级泄漏由 oracle 不进容器与目录权限守——请确认接受这条边界并写进验证验证器报告。
- [签字] S7 冒烟题全部 rebalance_frequency=daily（ε 仅 daily usable，R3 在打包期拦 weekly/monthly）；这意味着 v1.0 不出周/月频回测题，与 HANDOFF「不为 usable 放宽阈值」一致，但 S7 的题源需确认是 daily 可复现的（A-1 的效应量按 2026-09-03 的 screen 实测是 0.38–0.45%；22.69% 是 A↔B 的未归因残差，不是 A-1 的量 —— N-39）。
- 卡 4.1：agent_result 加 task_sha256 / set_id 两列（DDL 在 4.1 手里，过渡期写进 result_json）；parser 接受「容器 tests 恒为结构自检、以 scorer 结局为准」；不新增 GENEBENCH_AS_OF 环境变量。
- 卡 4.3：validator 工件只许 ops/specs 的结构 JSON Schema 且两臂同给，work/ 与臂无关（W1）。若 4.3 坚持臂间文件不同，E1–E3 需扩到文件级。
- S8 状态端点：当前网关 8 端点无状态类，S8 五行只能 draft。由谁、何时加端点；S8 无契约文件，建议先落 ops/specs 契约再出题（否则违 D-11）。S6 是否也引用 backtest_contract v3 的 TargetPosition 六字段。
- S3 free 题在 fields 强制要求下 required_fields 如何声明（一次声明全集 vs 每因子分别）——影响 declared_reads 探针对 free 题的可检性；S3 draft 期间可缓。
- N-33 补丁 patch_gateway_n33.py 待推送；S3b 状态锁以 test_bars_serves_open_amount_vwap_since_n33 为准，推送前 S3 五行只能 draft，30 题先 export。

## 评委批评

### 评委 1

## 三项特别检查

**1. gold / 答案 / 探针答案会不会经 task 目录进容器**

- protocol：结构上干净。E 面只有公共投影 + 两臂 + Dockerfile + tests + 空 work/，gold 只有 D 面指针，R8 比 sha、R15 投影不含 D 字段、R16 拦 tests/Dockerfile import。唯一缝隙：R8 只拦**逐字节相同**的拷贝，gold 转成 CSV 就绕过，而它的金丝雀（见下）拦不住这种形态。
- harness：有两处真实缝隙。(i) 「`gq.kind` … X」「`gq.probes{armed, expected_unobservable}` … X」——这些字段落在 f02 的 tb 骨架 task.yaml 里，与 Dockerfile 同目录；L1 只查「基础镜像带 digest、无 `ADD http`」，不拦 `COPY .`，一行 COPY 就把 `kind=underdetermined_probe` 送进 /task。G4 只断言 D 键被剥掉，对 X→C 这一跳没有任何守门。(ii) 「oracle 运行由专用适配器把 `solution/` 只读挂进容器」——答案本体进了执行面容器，靠 `arm=oracle` 单列和 canary_leak 事后兜底；作者自己列为未决，但按红线 5 原文「永不进任何 agent 可达路径」这是违反，不是待裁。
- scoring：容器包本身最干净（R10 白名单投影 + gold_token 0 命中），但**数据面落点选错了树**：「`tasks/_private/<task_id>/task.yaml  arms/equivalence.md   # 仅 f01`」——实施稿 §1「源码在 f01 的 /data/genebench/repo，git 裸镜像同步到 f02」，tasks/ 正是被同步的目录；runner_core L-5 的判据是 `"/tasks/" not in src` 才报错，`tasks/_private/` 恰好含 `/tasks/`，bind-mount 也放行。「仅 f01」没有机制支撑。全量 task.yaml 里有 gold 落点、scoring 段、oracle solution_ref、null_agent.expected_findings、canary.gold_token——泄漏的是判据与落点而非答案本体，但 D-06 第 7 例的教训正是「查配置态不查运行态」，这个目录选择在配置态上就是错的。

**2. 金丝雀能否真的测到泄漏**

- protocol：**近乎空转**。「明文只在 D」「canary.txt」——gold parquet、taskspec、solution 都不带串，R9「执行面目录命中 =0」只能证明 canary.txt 没被拷走；真正要防的 gold 文件泄漏，金丝雀根本不在上面。「扫描器非空证明」是在 reference/ 里扫到 ≥1，证明的是正则能跑，不是扫描面上有东西可抓。而且只有打包期静态扫描，没有对 work/、容器层、轨迹的收尾扫描——运行期泄漏一条也测不到。作者在未决里问「要不要同时写进 gold parquet 元数据」，这不是可选项，是这条机制成立的前提。
- harness：中等。「数据面每个文本文件都含 canary」（G3）+「非 oracle 轨迹中出现 canary 一律 canary_leak」有运行期扫描；但「共享 gold 面板（gold_factors 37 亿行）无法按题植入 canary，只靠目录 0700 守」——S3 的 gold 恰是最大的一块，金丝雀覆盖不到。另注意 `canary_leak` 若走 `Verdict.add` 作 violation 必须映射到 PROBE_IDS 里的探针族，当前 16 个里没有它，得作 run 级状态而非 finding。
- scoring：最好。双 token 设计里 control_token「只植入 INSTRUCTION」且 R11 要求「在容器包内恰 1 命中」——这是唯一在**执行面自身**上证明扫描器非空的方案（D-06 表里「缺陷扫描器：先在已知缺陷上跑」的直接实现）；runner 收尾「对 work/、容器层、轨迹、代理日志扫 gold_token」覆盖运行期。缺口：gold_token 写进 parquet metadata 要改卡 2.1b 产物，共享面板按题分 token 做不到（与 harness 同一个洞，只是没明说）；metadata 在 parquet→CSV 转换时会丢，所以它和 protocol 的 sha 一样只抓文件级搬运。

**3. 双臂等价性能否机械抽查**

- protocol：可以。core 单一来源 + strict 机械序列化 + open 经 lexicon，R5–R7 是可执行的集合比较，equivalence_report.md 有事实核对表。但「请裁定端点名是否算语义事实（影响 R5/R7 的判法）」——这条未决直接决定 R5/R7 的定义，等于两条核心规则还没写完。
- harness：最机械。「两臂模板不直接写字段值，一律经 `say(field)`」+ E1 用 `jinja2.meta` 比未声明变量集 + slots.json 逐槽并排。但「欠定字段在 phrasebook 里没有条目，say() 对它抛错——模板作者想提它都提不了」在逻辑上不成立：同一 S2 模板既出规定题（adjust 已声明，phrasebook 必须有 adjust 条目）又出探针题（adjust 欠定），条目不可能「没有」，屏蔽只能在渲染期按 `task.underdetermined` 做。E2 扫「欠定字段的任何枚举值」时 `none`/`post`/`close`/`open` 都是常见词，不加词边界与 lexicon 会误拒。
- scoring：可以。facts 表 `{id,value,strict,open}` + 两臂 fact_ids 相等 + equivalence.md「查表不查散文」是好的抽查形式。但 R7「每个 declared 值字面出现在两臂」与 facts 表设计冲突——open 臂写「后复权」时字面 `post` 不会出现；应改为「该 fact 的 open 措辞出现在 open 臂」。

## 逐份其他批评

**protocol**
- 「校验器 `_declarations()` 对「任务未提」的字段有第三分支——打包器把它变成不可达」：与源码一致（第三分支只查存在性），是对 2.3 最准确的一句对接。
- 没有 D-11。(d) 里 `scoring.json` 只是文件名，没有任何「判据先落盘 / 哈希 / 时间早于题面」的规则；实施稿把卡 3.2 的判据（卡 5.x）明列为 D-11 复发位置。
- R17「validate(oracle_sample, task=…) 无 task_context_*/envelope_task_id_mismatch」只验上下文自洽，不验 oracle 零 finding，更没有 null 低分或突变必红。3.2 验收原文「oracle_agent … 满分或标定分；null_agent 全部得低分」在这份设计里无落点。
- `gateway_capability.n33` 锁在哪、`lexicon.yaml` 谁维护、`reference://` 怎么解析、参数表的 `symbols`/`difficulty` 列谁消费，都没写。参数表用 CSV 承载 S7 十三个声明字段（其中 cost_model/strategy/constraints 是 dict）——JSON 塞 CSV 单元格，可做但脆。
- `genetask_version`/`artifact.schema_version` 只写 `=="1.0"`，没说必须是字符串——2.3-b 的教训是 YAML 里 `1.0` 会被读成浮点。

**harness**
- 「`gq.underdetermined` … 进执行面即探针作废」「D」：分面正确。「`taskspec()` 纯函数 … 不另存一份——两处不可能漂」是三份里最干净的 2.3 对接。
- 「①行→taskspec.json + scorer.yaml 落盘、记哈希与时间 ②物化 inputs ③渲染两臂 …」：D-11 被写进实例化顺序并用 J1 断言，这是唯一把 D-11 做成机制的方案。
- O1「打包器对其做一次已知突变（probe 题填默认值 / 其余改一个声明值）必须变红」：唯一的「校验非空」证明，直接对应 D-06 表里「先在已知缺陷上跑」。
- 缺 null_agent 路径（3.2 验收的另一半）；`UNDERDETERMINED_CANDIDATES[stage]` 在 artifact_schema.py 里不存在，是新常量且候选字段待签字（三份共同的未决）。
- as_of 经 `GENEBENCH_AS_OF` 注入容器——runner_core 的 COMPOSE_TMPL 目前没有这个变量，需要改 4.1 模板；作者已注意 D-10 副作用。

**scoring**
- R13「S7 tolerance.tier == 声明频率且 calibration usable」——HANDOFF §4 明写 weekly/monthly 不 usable「不要为了让它们 usable 去放宽阈值」，只有这份设计会在打包期把 weekly 题拦下；另两份会出一道结算不了的题。
- R15「null 产物按 null_behavior 生成后 ≥1 个 finding 且 ∈ expected_findings」+ (e)「default_fill 在欠定字段填默认 ⇒ silent_completion ⇒ invalid；empty ⇒ malformed」：oracle/null 分离在打包期就被证明，是对 3.2 验收最完整的实现。
- 「打包器在出包时先对它自身跑一遍 `_task_context_sane`」：注意该函数签名是 `(task, a, stage, v)`，需要一个 artifact 桩；小事但要写明。
- 「`runtime.image` 来自 `genebench/task-base:v1`」没有 digest pin，弱于 harness 的「基础镜像按 digest 钉死」。
- 未决第 1 条「探针题是否允许双标占族名额」其实已由 (e)「探针题双标」采用，且三份设计一致；第 3/9 条同样是对本稿决定的再确认——这些应写成决定而非问题。

## 结论

harness 以 30 分居首：冻结项覆盖最全（A1/J1/O1/S3b/R3 含 S7 adjust=post），D-11 与「校验非空」两条纪律都做成了机制，实例化顺序与 export() 可以直接写代码。它的两处缝隙（X 面字段与 Dockerfile `COPY .`；oracle 挂 solution 进容器）都能用一条 lint 与一个「oracle 在数据面直出 artifact」的裁定堵上。建议采纳 harness 骨架，并合并 scoring 的两件东西：双 token 金丝雀（control_token 在执行面恰 1 命中）与 R13/R15（ε 档位可用性、null_agent 判别力干跑）。protocol 的金丝雀与 D-11 缺失使其不能直接施工。

### 评委 2

## 共同核对结论

**DECLARATION_FIELDS 逐阶段对上了吗**：三份都要求 `declared ∪ underdetermined == DECLARATION_FIELDS[stage]` 全划分（protocol R1、harness R2、scoring R3），把校验器 `_declarations()` 的第三分支（任务未提）变成不可达——比校验器严，方向正确，且三份都注意到了。但实施稿「故意不声明复权或日历」在 S3/S4/S5/S6 无法逐字执行（这四阶段的 DECLARATION_FIELDS 里没有 adjust/calendar_id），三份处理方式差别很大：harness 给出逐阶段候选并说明理由（S7 取 first_rebalance_day 而非 adjust，因为校验器 `backtest_adjust_off_contract` 把 adjust 钉在 post，且 HANDOFF 记的 A↔B 22.69% 毛收益差（**未归因残差**，N-39）曾被当作 S7 首要题源的依据；A-1 现在的依据是它自己的隔离实验（0.38–0.45%，material））；protocol 建议 S7 欠定 adjust——契约钉死 post 的字段拿来做探针，agent 按契约填 post 反被判 silent_completion，探针语义不成立；scoring 干脆在 (b) 写「仅参数表把 `adjust` 或 `calendar_id` 从 declared 挪到 underdetermined」，对 S3–S6 结构上无法产出探针行。

**参数表能否覆盖 8×4+探针+自由**：三份都是每阶段 5 行 = 四族各 1 + 探针 1（双标一族），S3/S4/S5 的 ECO 行为 free。数字上能凑齐 40 行。但三份都把 S3 标 N-33 阻塞后声称「先出 35 题」（protocol、harness 原文），只有 scoring 注意到 S8「依赖网关状态接口，当前 8 个端点无状态类」——按 HANDOFF 网关只有 /bars /adj /calendar /universe /tradability /fundamentals /limits + healthz，S8 五题与 S3 同样出不了，真实可出为 ≤30 题。

**与卡 2.3 校验器的接口**：三份的 TaskSpec 形状都与 `validate(task=...)` 的 `{task_id, stage, declared, underdetermined}` 一致。protocol `to_task_context(task)` 纯投影 + R17 回路；harness `taskspec()` 原样切片「两处不可能漂」；scoring 把 `taskspec` 作为嵌套对象「原样喂」，并称「打包器在出包时先对它自身跑一遍 `_task_context_sane`」——但 `_task_context_sane(task, a, stage, v)` 是需要 artifact 参数的私有函数，单独调用要造 dummy artifact，是个小的实现摩擦。

**与卡 4.1 runner 的接口**：runner 当前是自研 compose 编排（`run_task` 把 `HELLO_TASK["arms"][arm]` 写成 `work/INSTRUCTION.md`，挂 `tasks/<id>/work` 为 `/task`，env 里有 `GENEBENCH_ARM`），并无 terminal-bench loader。protocol 的 `instruction.strict/.open` + `work/`「替换 HELLO_TASK.arms」贴合最紧；scoring 的 `arms/strict.md` 按 `GENEBENCH_ARM` 复制也直接可用；harness 的 `instruction: @arms/INSTRUCTION.{arm}.md` 引入了 tb 单字段间接引用（自陈「需要 fork 的 loader 改一行」），目录名用 `workspace/` 而 runner 用 `work/`，并要求新增 `GENEBENCH_AS_OF` 环境变量——都可做但要改 4.1。遥测 DDL 三个预留字段（search_count/trial_family/cash_ratio_median）已在 runner 里，protocol 让每题 `telemetry.expect ⊇` 它们属多余；harness 提出加 task_sha256/set_id 列是合理诉求。

## protocol

- **没有 oracle/null**。字段表里没有 solution/oracle/null 任何字段，只在 R17 出现「`validate(oracle_sample, task=…)`」和未决问题「free 题的 oracle 分是取上沿锚还是不设」。实施稿 3.2 验收是「oracle_agent 跑通全部并得满分或标定分；null_agent 全部得低分」，这份设计给不出 oracle 从哪来、怎么跑。
- **没有材料输入**。(d) 写 `work/ # 空`，字段表无 inputs。S7 是「回测复现（gold 信号 + 声明成本）」、S6 需要信号、S4 需要因子值——上游 gold 产物必须进容器，而 R8 又规定「执行面目录任何文件的 sha ≠ gold 文件 sha」，若照字面把 S5 gold 信号送进 S7 容器会被 R8 拦下。harness 明确区分「S7 的 gold **信号**是输入不是答案」，protocol 缺这一层。
- **R11 `gateway_capability.n33=true`** 从哪读没说；**「程序提示白名单」** 边界自己列为未决，而 R5/R7 的判法依赖它；`lexicon.yaml` 的内容与 `equivalence_report.md` 的核对表怎么生成没有落到机制。
- D-06 方面做得好的：R18 负例 exclusive、R14 import 期恒等式、R9「明文在 reference/ 植入文件命中 ≥1（扫描器非空证明）」。缺的是「每题校验非空」的证明——R17 只证 oracle 绿，不证坏产物会红。
- 未察觉 S8 阻塞、ε 分档 usable、记忆探针题面（实施稿 3.2 现在要出 33 项）、对接决定 §4 的科目 ID（报告器要按科目回溯，只有 family 不够）。

## harness

- **O1 是三份里唯一的「每题校验非空」断言**：「打包器对其做一次已知突变（probe 题填默认值 / 其余改一个声明值）必须变红；突变后仍绿 ⇒ 该题校验为空（D-06）」。J1 把 D-11 做成可核对的哈希与时间序。A1 `inputs.max_date ≤ as_of` 把「网关是唯一入口」延伸到打包期物化的材料上。实例化顺序「① taskspec.json + scorer.yaml 落盘、记哈希与时间 ② 物化 inputs ③ 渲染两臂 …」固化在代码里。phrasebook 让「欠定字段在 phrasebook 里没有条目，`say()` 对它抛错——模板作者想提它都提不了」——这是三份中唯一把等价性从「事后检查」变成「构造上不可能」的。
- **缺口一：free 题没有锚点字段**。(e) 说 S3/S4/S5 的 ECO 行「kind=free（效果指标唯一来源，配基线阶梯）」，但字段表里没有 anchor/effect_metrics 任何位置，scorer.yaml 只写「ε/τ 引用、探针参数」。5.4 之前可 pending，但 schema 里得有坑。
- **缺口二：E1 近乎空转**。「两臂模板的未声明变量集相等（`jinja2.meta`）」——两臂模板都只调 `say(field)` 时，`find_undeclared_variables` 对两臂都返回 `{say}`，E1 恒真。负例「strict 多用 `{{ fields_hint }}`」能造，但主路径上它什么都测不到，正是 D-06 要防的形状。
- **缺口三**：「S3 五行先写、status=draft…先出 35 题」——S8 同样出不了。
- 自己指出但未裁的张力：oracle 由「专用适配器把 `solution/` 只读挂进容器」，容器内短暂出现答案；共享 gold 面板「无法按题植入 canary，只靠目录 0700 守」。G3「数据面每个文本文件都含 canary」若字面执行会把 canary 塞进 taskspec.json（校验器不拒多余键，但这份 JSON 应当只有四个键）。`gq.declared` 约束「S4 = FROZEN_CALIBRATION」不精确：ic_method 不在冻结表里，holding_periods 是子集关系。
- 探针题 family「取该阶段最自然的一族」需要一条可执行的规则，否则报告器四族统计因人而异。

## scoring

- **覆盖最广**：R13「S7 tolerance.tier == 声明频率且 calibration usable，负例 weekly 题」是唯一把 HANDOFF「weekly/monthly 不 usable」变成打包期硬锁的设计；`null_agent {behavior, expected_findings[]}` 让 3.2 的判别力验收在打包期就跑（R15）；R11「control_token 在容器包内恰 1 命中」是扫描器非空证明的干净做法；`snapshot_manifest_sha` 给了复现锚；点出 S8 阻塞。
- **但 (b) 的探针实例化规则不可执行**：「欠定探针题模板与规定题同一模板，仅参数表把 `adjust` 或 `calendar_id` 从 declared 挪到 underdetermined」——S3–S6 没有这两个字段，按此规则 40 行填不出 20 行探针里的 4 行。未决问题里承认了，却没有像 harness 那样给候选。
- **内部矛盾**：`gold`「非 memory_probe 必填」而 free_form 题「无 gold 只有阶梯」；(c) R10「容器包白名单：只含 PUBLIC_KEYS 投影 + arms + Dockerfile + tests/」漏了 (d) 的 `inputs/`，照 R10 执行 S7 的 gold 信号进不了容器；`task_id` 同时在顶层与 `taskspec` 内，「原样喂」的前提是两处不漂，却没有恒等式。
- **成本未计**：`gold.ref_path` 以 `reference/gold/<task_id>/` 开头且带 `rows/sha256`，意味着从 37.2 亿行 / 15 GB 的共享面板按题切片；gold_token「植入 gold parquet metadata」要改卡 2.1b 产物——harness 明说了这笔账，scoring 只列为未决。
- **R15 对 S1/S3 需要网关日志切片**：「用合成日志还是让 oracle 真跑一次网关」列为未决——合成日志与「验行为不验申报」相悖，真跑则打包期依赖执行面，这是本卡该拍板的。
- 10 条未决里「双标是否占族名额」「是否由同一打包器出记忆探针」「public.yaml 是否剥 gold 路径」都是设计者应当决定的，留给实现者会导致同一份参数表在不同实现下形状不同。

## 结论

harness 最可直接开工：与校验器/runner 的接口都对得上，D-11 与 D-06 落成断言而非原则，材料输入与答案分账，欠定候选带理由。开工前需补三处：free 题的锚点字段（可 pending 但必须占位）、把 S8 与 S3 同列 blocked、把 E1 改成对 phrasebook 槽位集的相等断言。scoring 的 R13/R11/null_agent 三条值得原样并入 harness；protocol 的 R18 exclusive 与 R9 扫描器非空证明 harness 已有等价物。