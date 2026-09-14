# 适配赛道（v1.0-adapt）—— 最小版规格 · 卡 4.2-a

**代码**：`ops/adaptation_track.py`（生成器）、`ops/pack_adaptation.py`（出集）、
`scorer/adaptation.py`（结局分类）、`scorer/report.py::table_adaptation`（表）、
`ops/protocol/geneprotocol_v1_adapt/`（干预工件「适配模块」）、
`ops/manifests/v1.0-adapt.json`（集清单）、`ops/test_adaptation_track.py`（测试）。

**产物**：`$GENEBENCH_ROOT/reference/adaptation/v1.0-adapt/<example>/{original,broken,mutation,oracle}.json`
（答案面），bundle 暂存在 `$GENEBENCH_ROOT/staging/adapt_bundles/`。

---

## 0. 现状（2026-09-10，卡 Y2）：**本赛道已经真跑过一遍**

2026-09-07 写在这里的三件缺的东西，今天全部解开 ——

| # | 当时缺什么 | 现在 |
| --- | --- | --- |
| ① | **题源裁定**（红线 B2） | **已裁**（用户 2026-09-10，**N-348**）：题源 = **出集规定题的 oracle 产物**（探针题不入）。`ops/push_guard.SET_IDS_NOT_PUSHABLE` 里那条按集拒**显式解除并记因**；换上一道更窄的门（落点，见 §7）。**后果照实写在 §7，不许省。** |
| ② | `INSTRUCTION.<arm>.md` | 已补（2026-09-07）：`--arms` 点名的臂各写一份题面；漏写的臂由 P6b 拒。默认臂集合现在是 `adapt,open,strict`（**第一个是干预臂**，N-364）。 |
| ③ | 适配模块 `status: draft` | **已改 `released`**（卡 Y2）。三件工件的内容自 2026-09-07 **一字未改**（sha 相同），改的只有 status —— draft 下 P7 拒绝投放，adapt 臂就是个裸臂（实测：22.7 s 中止、零次模型调用）。 |

出集与钉 digest 这一段一直是通的：`ops/pack_adaptation.py --pack --digest sha256:… --arms …`
在**出通行证之前**钉 digest（此前是事后钉，通行证与树必然对不上，两条路都过不了守门）。

---

## 1. 它对接的是哪一条

《GeneBench 指标对接决定 v1》§0 第 9 行：「B2 接入与语义保持 ≈ **适配赛道（v2）**」。
《GeneBench 指标规格 v1》第 17 行把 GeneQuant §3.3 的原文逐句接到了署名口径上：

> 「源中缺失的信息保持缺失、不得由 agent 补全」是**静默脑补率**的定义原文；
> 「有效 artifact 进入其语义完整所支持的最早协议阶段 —— 完整定义可进上游研究阶段、
> 信号可进组合构建、TargetPosition 可进回测或模拟交易」是**入口路由正确率**的判定规则原文；
> unsupported / unresolved 标记对应结局类「**缺口正确标记**」；
> 「agent 提出翻译、协议裁决可接纳性」与评分器独立原则并行不悖。

再加《指标规格 v1》第 15 行（能力协议 ❺）：

> 协议明文「可恢复违例进入修复回路、金融要害语义未解决则拒绝」正是**适配五结局**中
> 「修复后接入」与「正确拒绝」两类的来源。

**CONFLICT（登记，未解决）**：仓库里**没有**一份独立的「§3.3 适配模块」文档。
`grep -rn '3.3\|适配' ops/specs ops/protocol` 只命中上面这两处引用与若干无关的小节号
（`card_4.2_parser_scorer_adapters.md §3.3` 讲的是 harvest，`s8_state_contract.md §3.3`
讲 `pending_orders`，都不是适配条文）。`ops/protocol/geneprotocol_v1/` 的三件工件
（`README.md` / `contract.md` / `validate_artifact.py`）里也没有适配条文。
所以本卡的适配模块是**按上面两处原文定义的最小版**，不是照抄一份既有文档；
原文一旦补齐，`ops/protocol/geneprotocol_v1_adapt/adaptation.md` 要按原文重对一遍。

## 2. 题源（2026-09-10 按 **N-348** 重定）

**出集规定题的 oracle 产物。** 「规定题」= `ops/manifests/v1.0-smoke.json::released_tasks` 里
`kind != "underdetermined_probe"` 的题（`regulated` + `free`）—— **探针题不入**。
oracle 产物按落点取：S7/S8 是 `gold/oracle_artifact.json`，其余阶段是
`solution/artifact.json`（`ops/run_oracles.py` 的两处实际落点）。

**清单现值与裁定原文的差，如实记**：裁定写「33 道出集规定题」，而 2026-09-10 的清单现值是

```
出集 34 题 = 规定题 32（regulated 29 + free 3）+ 已放出的欠定探针题 2
挂起 6 题（全是欠定探针题）
八个阶段各 4 道规定题，一道不多一道不少
```

所以实际用的是 **32 道**，不是 33。差在这里记着，判据以清单为准
（`ops/adaptation_track.py::source_counts()` 把这个差写进 `_index.json`）。

**再减两道 —— 体量帽**（`MAX_SOURCE_BYTES = 700 KB`）：`s5-eco-01` 的 oracle 产物有 **4.0 MB**
（41,700 条 signals），`s4-ops-01` 有 878 KB。把它们做成适配题，量到的是「agent 会不会用脚本
改文件而不是把整个文件读进上下文」，不是适配能力，而且 bundle 也跟着胖 4 MB。
帽下每个阶段仍剩至少 3 道题，分层不受影响。

用 oracle 产物而不是手写样例，理由与 `ops/run_probe_mutations.py` 那一条相同：手写样例只证明
「在样例上会响」，不证明「在我们真的会拿去评分的那些产物上会响」。适配赛道更强一层 ——
它要求 broken 与 oracle 之间**只差一处**，手写样例做不到这一点而不引入第二处差异。

信封（`task_id` / `artifact_id` / `config_id` / `arm`）改写成这道适配题自己的身份；
`declarations` / `payload` / `provenance` 原样。**这带来一个红线后果，见 §7。**

### 2.1 选题：按阶段分层 + 种子固定

每级 10 例：**八个阶段各 1 例**（分层），余下 2 例按固定种子在候选里补上**没出现过的
(阶段, 破坏族) 组合**。种子 `SEED = 20260910` 写进每一份 `mutation.json` 的 `seed` /
`selection` 与 `_index.json` —— 同一份题源上重跑，选出来的 30 例逐字相同。

候选枚举也是可复现的：题按清单顺序、位点按叶子顺序（dict 插入序 / list 下标），
每条规则在同一道题上最多出 `MAX_SITES_PER_RULE = 2` 个位点，每道题最多扫
`MAX_LEAVES_SCANNED = 4000` 个叶子。**位点必须落在评分器真的比对的那部分**
（`PAYLOAD_REQUIRED[stage]` 的某一棵子树，或 declarations / provenance）——
落在别处的破坏结算看不见，那种题量的是运气。

一个候选要能被选中，先得**建得出来**：破坏恰好一处、可纠正性的 `check` 在原件上实测通过、
oracle 过协议校验器。建不出来就换同一阶段的下一个候选（顺序由种子定死）。

## 3. 三级定义

每例**只破一处**：`ops/adaptation_track.py::diff_sites(original, broken)` 恰好返回一条。
一次改名（同一个父对象上恰好一删一增）与一次整条被删各算**一处** —— 否则
「字段名换成 tushare 的叫法」在 JSON 上永远是两处，那不是破坏样本的问题，是差异口径的问题。

### L1 单位错配（10 例，**覆盖八个阶段**）

值的量纲被换成源侧口径：比例写成百分数、价格以分计、量以手计、计数以百计、日期写成紧凑串。
**判据：源里带的信息足以纠正**，而且这句话是**实测**的，不是断言 —— 每例带一条
`recovery.route`，生成期跑一个 `check`：

| route | 含义 | 例 |
| --- | --- | --- |
| `sibling_identity` | 同一份产物里另有字段与它有恒等式 | ① **同名同值的兄弟字段**（自动发现）：S4 `ic_stats.coverage` ↔ `ic_by_horizon["1"].coverage`、S3 `values_ref.coverage` ↔ `degeneracy.coverage`。**只认同名**（值恰好相等的两个不同量不是恒等式），**且不认同构**（同一个 list 里的两条记录 —— S5 的两个 `signals[i].value` —— 也不是）。② `_IDENTITIES` 里登记的算式：S2 `rows == n_symbols × n_dates`、S5 `n_valued + n_null + n_flat == len(signals)`、S7 `attribution.total == metrics.ann_return_net` |
| `schema_format` | 目标 schema 只收一种写法且映射唯一 | ISO 日期 ↔ 紧凑串。**这句话是实测的**：破坏之后校验器必须真的拒；schema 管不到的位置（例如 `fetches[].params` 里的日期）这条不成立，同位点退到 `source_unit_declaration` |
| `source_unit_declaration` | 交付说明声明了该路径的单位，换算规则在 `unit_table.json` | `lots` / `cents` / `percent` / `hundreds` / `date_compact`。**check = 按表里那条换算式回算、逐位还原原值**（int 也要还原成 int）—— 「表写对了」是跑出来的，不是相信出来的 |

恒等式在原件上不成立时**这一例不出**（`AdaptError`）—— 「可纠正」这句话没有靠人记住。

### L2 词汇翻译（10 例，**覆盖八个阶段**）

字段名 / 枚举值 / 代码写法换成 tushare、yfinance、akshare（或旧的前缀式）叫法。
**判据：别名在 `field_map.json` 里查得到且唯一**；查不到 = 不可接纳（按 L3 的方式标记），
那种情况不出成 L2 题。`ops/test_adaptation_track.py::test_l2_aliases_are_resolvable_by_field_map`
把这条钉住。

### L3 缺协议字段（10 例，**覆盖八个阶段**）

三个子族，各删一处：

| 子族 | 删什么 | oracle |
| --- | --- | --- |
| `gap_declaration`（7 例）| 一个三态声明字段 | 该字段标 `unresolved`，并把 `PAYLOAD_DEPENDS_ON` 里依赖它的 payload 字段置 `null`（`halted_fields` 列出）|
| `gap_provenance_id`（2 例）| 一条上游引用的 `artifact_id` | 该引用的 `artifact_id` 标 `unresolved`（阶段还在，身份不知道）|
| `gap_provenance_edge`（1 例）| 整条上游引用 | 补回 `{stage, artifact_id: "unresolved"}` —— 边的**存在**由 `declarations.input_factors` 证明，边的**身份**不可推 |

L3 的 TaskSpec 把被删的声明字段从 `declared` 挪到 `underdetermined`：源里没有这一项，
题面就不该声明它，否则 oracle 标 `unresolved` 会被判 `declared_field_marked_unresolved`。

## 4. oracle

* L1 / L2：**就是原件**（只换信封）。
* L3：原件在缺口上标 `unresolved` 的**合法形式**。

三十份 oracle 全部过协议校验器 `reference.artifact_schema.validate`
（`test_oracle_passes_protocol_validator`）。生成器在建例时就跑这条，过不了不出这一例。

## 5. 结局定义（`scorer/adaptation.py`）

| 结局 | 判据 |
| --- | --- |
| `first_pass` 首次通过 | 终稿过校验器、与 oracle 字段级一致，`validator.log` **零次**拒绝 |
| `repaired_pass` 修复后通过 | 同上，但有过至少一次拒绝 |
| `correct_flag` 正确标记 | **L3 专属**：缺口标了 `unresolved`，其余与 oracle 一致 |
| `blocked` 拦截 | 校验器拒绝（或没有终端产物），且最后一条 validator 记录仍是拒绝（agent 停下）|
| `failed` 失败 | 其余，含**过了校验器但与 oracle 不一致** |

**与 oracle 的比对不新造判据**：payload 走 `scorer.l3.compare_exact`
（`PAYLOAD_REQUIRED[stage]` 逐键、集合语义字段按集合比），declarations 与 provenance 走
同一对原语（`artifact_schema._json_equal` / `_set_equal`）。

**precedence**：L3 上「正确标记」压过「修了几轮」—— §3.3 把 unsupported / unresolved 标记
单列为一类结局，它问的是内容（有没有替源补值），不是过程；修复轮数另有
`validator_rejections` 一列，没有被藏起来。

**为什么结局不能只看校验器**：30 例里有 **9 例**的破坏**结构上完全合法**
（把 0.93 写成 93.3 不违反任何结构规则，删掉一条 provenance 也不违反）。只看
`validate_artifact.py` 的退出码，这 9 例会全判成通过。每例的 `mutation.json` 里
`broken_validator.ok` 如实记着这一点。（2026-09-07 那一版这个数是 13；题源与选题按 N-348
换过之后实测是 9。**它是实测不是设计目标**，判据 `ops/test_adaptation_track.py::
test_structurally_legal_breaks_are_recorded` 会在它漂的时候变红。）

### 表

`scorer/report.py::table_adaptation(records)`：按 (config, arm, level) 数五类结局 + 比例，
每个 (config, arm) 另出一行 `level="ALL"`；`write_csv` / `to_latex` 沿用现有出口。
`resolved_rate = (首次通过 + 修复后通过 + 正确标记) / n` —— **拦截不进分子**：
正确地拒绝一份修不了的产物是协议要的行为，把它计进成功会奖励硬修。

## 6. 题面与打包

适配集**不进 v1.0-smoke 冻结集**：题面另立、判据另立、`SET_VERSION` 不因它变动。

打包不走 `genetask/packager` 的现有入口：`build_task` 从 `genetask/params/v1.0-smoke40.yaml`
建题、题面由八套阶段模板渲染、`task_id` 被 `genetask/schema.py::_TASK_ID`
（`^s[1-8]-(cor|rob|eco|ops)-\d{2}$`）钉死 —— `adapt-l1-01` 三条都不合。硬塞要改冻结根。
所以 `ops/pack_adaptation.py` 用最小方式生成 bundle，**判据仍然是别人的**：
允许集与通行证结构取 `genetask.bundle`，Dockerfile 过 `lint_dockerfile`，
出集前过 `ops/push_guard.assert_pushable`（树 + 通行证两道）。30 个 bundle 全绿。

bundle 长这样（默认臂集合 `adapt,open,strict` 下是九个文件）：

```
task.yaml                        X 键集形状；packed_at 刻意留 null（写时间戳会让同一份内容每次出不同 sha）
arms/INSTRUCTION.adapt.md        通用适配题面，各臂同一份（适配模块不由题面提及）
arms/INSTRUCTION.open.md         **第一个臂必须是干预臂**（N-364）：这里是 adapt
arms/INSTRUCTION.strict.md
image/Dockerfile                 FROM gb-cx-u:r1@<占位 digest>，推送前由 pin_image_digest 钉真值
image/tests/test_outputs.py      容器内自检：产出在不在、信封齐不齐（不判对错）
work/S{k}.json                   目标 schema（`artifact_schema.json_schema(stage, profile)`）
work/input/broken.json           上游交来的产物 → 容器里 /task/input/broken.json
work/input/source_meta.json      交付说明：来自谁、哪些路径用源侧单位、哪一项上游不带
```

**已知缺口**：适配集没有金丝雀三串（gold_token / x_token / control_token），
因此 `check_export` 的 C1（每臂控制串恰一次）/ G2 / G3 三条判据在这个集上不适用。
正式出集前要么接 packager 的金丝雀机制，要么给适配集定义等价判据（见票据）。

## 7. 红线 B2：这份 bundle 现在**可以**推 f02 —— 代价写在这里

**裁定（用户 2026-09-10，N-348）**：题源 = 出集规定题的 oracle 产物；
`ops/push_guard.py` 里「按集拒 `set_id=v1.0-adapt`」**显式解除并记因**
（记因逐条写在 `SET_IDS_NOT_PUSHABLE` 常量上方）。

### 7.1 后果（用户已知情裁定，**不许省**）

`work/input/broken.json` 是某一道**规定题的 oracle 产物只破一处**的结果 ——
内容上它就是那道题的答案。它随 bundle 进入执行面。因此：

> **跑过适配赛道的被测方，主赛道被引用的那些题算「可能已见过答案」。**

* **逐题清单**：`ops/manifests/v1.0-adapt.json` 的 `exposed_source_tasks`；每一份
  `mutation.json` 也各带 `source_task` 与 `_exposure`。
* **不涉及探针题**：`kind == "underdetermined_probe"` 的题一律排除 —— 六道挂起的与两道已放出的
  欠定探针题，一道都没有进适配集。
* **它挡什么**：不挡主赛道本身 —— 一个从没跑过适配赛道的被测方不受影响。挡的是**同一个
  被测方**「先适配、后主赛道」这一种读法。
* **同一句话还写在**：`ops/specs/fairness_protocol.md` §7 第 10 条、
  `ops/reports/known_limits_v1.md` 末节，以及**适配表与主表的脚注**
  （`scorer/report.py::ADAPT_ORACLE_EXPOSURE_NOTE` → `to_latex` 的 caption 与
  `table_adaptation` 的 `note` 列）。

### 7.2 解除之后保留的那道更窄的门

解除的是「整集不许推」，**不是「随便往哪儿推」**：

| 门 | 在哪儿 | 判什么 |
| --- | --- | --- |
| 落点白名单 | `push_guard.ADAPT_DEST_PREFIX` | 适配 bundle 只许落在 `/data/genebench_runner/adapt/` 下。推进主赛道的 batch 目录（`m6/` `v1demo/` `a1/` …）= 拒 |
| 落点必须**显式声明** | `push_guard.DEST_ENV` / `assert_pushable(..., dest=)` / CLI 第三参 | **没声明 = 拒**，不是放行。`GENEBENCH_PUSH_DEST=<目标目录> ops/push_bundle_to_f02.sh …` |
| 打包落点闸 | `pack_adaptation.pack_one` | 暂存根必须在 `$GENEBENCH_ROOT/staging/` 下 —— 生在受审计的地方，红线 5 守门与答案面扫描才看得见它 |
| 通行证如实自报 | `pack_adaptation`：`origin: gold_derived` / `track: adaptation` | 瞒着不写才是问题；`ORIGINS_NOT_PUSHABLE` 对非适配集照旧生效 |

判据：`ops/test_y2.py`、`ops/test_4rt.py::test_push_guard_gates_the_adaptation_set_by_destination`。

## 8. 臂

适配模块 `ops/protocol/geneprotocol_v1_adapt/` 是**干预工件**，挂在 `/task/adaptation/`，
由 4.1 的臂机制投放（`genetask/arms.yaml` 加一条 `adapt` 臂，`kind=protocol`，
`mount=adaptation`，`per_task_rules=false`）。题面只说「若存在」，不说里面有什么 ——
与 `geneprotocol_v1` 的摆放规则一致。臂定义写在 `ops/tickets_inbox/4.2.md`：
本卡收口时 `genetask/arms.yaml` 还是别人工作树里的未提交文件，按并发规则不动它。

## 9. L4 / L5（记 v1.1）

* **L4 跨协议版本迁移**：源产物是 `schema_version` 更老的一版，要迁到当前版。
  v1 只有一个 schema 版本（`_VALIDATORS` 只有 `"1.0"`），造不出真的迁移题。
* **L5 算子语义分叉的适配**：`ops/specs/operator_semantics_conflicts.md:173` 已经写着
  「这条限度写进 L5 适配赛道的题源说明」—— 它要的是**同一个算子在两份实现下给不同的数**，
  判据是 τ 带而不是逐字段等价，与本卡的五结局不是同一套结算。
