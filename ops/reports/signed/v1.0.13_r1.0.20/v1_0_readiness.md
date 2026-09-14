# GeneBench v1.0 就绪报告（M6 构造验收 · 产出 ①）

> 通道 `private`；批 `m6, m6b`；④⑤ 明细 `/data/shared/genebench/repo/ops/reports/m6`；O1 矩阵 `/data/shared/genebench/repo/ops/reports`。

生成时间：见 git 提交；仓库 HEAD `38fb938`（fix(6.4): 演练报告 §4.1 少数了一个撞闸的 run —— 只看 run_status 会漏掉一半）。

> **M6 的目的是证明 benchmark 建成，不是产出实验数据**（范围修正 2026-09-04）。
> 下面每一行都指向机器可查的产物；数字从文件读，不手抄。

## 1. 组件版本与冻结根

| 项 | 值 |
| --- | --- |
| 任务集版本（agent 看得见的） | **1.0.13**，根 `925a1adcdf82e6a0…` |
| 参考版本（我们算 gold 的方式） | **r1.0.20**，根 `8c162988c2a7b5d2…`（39 个 solve.py + 10 个参考模块）|
| 出集 / 挂起 | 34 题出集，6 题挂起（探针题的 E9c 未过）|
| 冻结线 | 2026-07-31 |
| 能力位 | `n33_bars_open_amount_vwap`=True；`s8_state_endpoint`=True；`anchor_ladder_54`=False；`n23_index_instrument`=False；`provider_sha256_pinned`=False |

> ⚠ **§4 的主表与本节不是同一组轴**：那张表自报 `MIXED:`（几批不同版本的 run 合出来的），本节声明的是发布版的两条轴 —— 两者不能并排读，详见 §4 的告示。

> **`provider_sha256_pinned=False` 的原因**：注入器现在只核 provider 的**根指纹**（`pin.check_provider_pin` 比对 `files.sha256` 这个文件的 sha256 = `54fdda39…`，P2 门），**没有**逐文件重算那棵树 —— 也就是说「provider 换了一个文件」这件事目前查得出的前提是它自带的 `files.sha256` 也跟着变。卡 4.2 的适配层要做的逐文件核对还没落地，所以这把锁维持 false。

### 执行面（f02）

```
（没有执行面环境快照）
```

- **runner_version**（注入器自己的指纹）：`df2067cc41d87b0783da1b7a…`（取自 `s1-cor-01.open.cfg-codex-deepseek.r01` 的 `inject.json`）
- **随树船运的 h11**：12 个文件，逐文件 sha 的清单 sha256 `2c06c353afcbe5f8e4e5f03a…`（边车与网关**同一份字节**，P7d 挂进容器）
- **边车** `egress_proxy.py`：`f5e845f55ede33d7e780e23f…`
- 任务镜像：`gb-cx-u@sha256:961e3878b28fc13ef2600254c4c4cbaceb7c337e2944fc173…`

### 数据面（f01）

- 网关：user systemd `genebench-gateway.service`（常驻、单 worker、绑 LAN、snapshot 后端）
- oracle 环境：python 3.10.20 / pandas 2.2.3 / numpy 1.26.4 / pyarrow 20.0.0
- 跨版本核：`ops/reports/crossver_probe_a1.md` —— 与统一基座 **17/18 键逐位相同**（唯一不同是 parquet 字节流 sha，读回的值相同）

## 2. 全链一次无人工干预跑通

链路：`build_task → write_task → export_bundle（钉 digest + 出通行证）→ push_bundle_to_f02（发送侧门 + 接收侧扫描）→ inject（P0–P9 + 边车 + h11 + 模型反代 + 预算闸）→ docker compose up → 容器跑 agent → harvest（down -v 之前）→ 拉回数据面 → gate（校验器 + 三态）→ L3 → validate_scorer_output → Table A/B`。

本批（m6 + m6b）**29 个 run**，其中 `run_status=ok` **8** 个。逐 run 证据：

| run | 注入 | 边车 | 容器 | 采集 | 闸门 | L3 | 效果分 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `s1-cor-01.open.cfg-codex-deepseek.r01` | 46570 文件 | 74 条 | 21 次模型调用 | 产物有 | valid | cov:True | 100.0 |
| `s1-cor-01.strict.cfg-codex-deepseek.r01` | 46577 文件 | 52 条 | 22 次模型调用 | 产物有 | invalid | —:None | None |
| `s2-cor-01.open.cfg-codex-deepseek.r01` | 46570 文件 | 107 条 | 29 次模型调用 | 产物有 | valid | align:False | 99.9736 |
| `s2-cor-01.strict.cfg-codex-deepseek.r01` | 46577 文件 | 89 条 | 28 次模型调用 | 产物有 | valid | align:True | 100.0 |
| `s3-cor-01.open.cfg-codex-deepseek.r01` | 46570 文件 | 77 条 | 35 次模型调用 | 产物有 | invalid | tau:True | None |
| `s3-cor-01.strict.cfg-codex-deepseek.r01` | 46577 文件 | 385 条 | 32 次模型调用 | 产物有 | invalid | —:None | None |
| `s4-cor-01.open.cfg-codex-deepseek.r01` | 46572 文件 | 1046 条 | 51 次模型调用 | 产物有 | — | —:None | None |
| `s4-cor-01.strict.cfg-codex-deepseek.r01` | 46579 文件 | 364 条 | 51 次模型调用 | 产物有 | — | —:None | None |
| `s4-cor-01.strict.cfg-codex-deepseek.r02` | 46579 文件 | 318 条 | 40 次模型调用 | 产物有 | valid | epsilon:True | 100.0 |
| `s5-cor-01.open.cfg-codex-deepseek.r01` | 46574 文件 | 131 条 | 32 次模型调用 | 产物有 | valid | tau:True | 100.0 |
| `s5-cor-01.strict.cfg-codex-deepseek.r01` | 46581 文件 | 117 条 | 32 次模型调用 | 产物有 | invalid | —:None | None |
| `s6-cor-01.open.cfg-codex-deepseek.r01` | 46572 文件 | 362 条 | 33 次模型调用 | 产物有 | valid | cons:True | 100.0 |
| `s6-cor-01.strict.cfg-codex-deepseek.r01` | 46579 文件 | 78 条 | 33 次模型调用 | 产物有 | valid | cons:True | 100.0 |
| `s7-cor-01.open.cfg-codex-deepseek.r01` | 46574 文件 | 1218 条 | 45 次模型调用 | 产物有 | — | —:None | None |
| `s7-cor-01.open.cfg-codex-deepseek.r02` | 46574 文件 | 168 条 | 68 次模型调用 | 产物有 | — | —:None | None |
| `s7-cor-01.open.cfg-codex-deepseek.r03` | 46574 文件 | 2260 条 | 91 次模型调用 | 产物有 | — | —:None | None |
| `s7-cor-01.strict.cfg-codex-deepseek.r01` | 46581 文件 | 111 条 | 51 次模型调用 | 产物有 | — | —:None | None |
| `s7-cor-01.strict.cfg-codex-deepseek.r02` | 46581 文件 | 838 条 | 44 次模型调用 | 产物有 | — | —:None | None |
| `s7-cor-01.strict.cfg-codex-deepseek.r03` | 46581 文件 | 3087 条 | 91 次模型调用 | 产物有 | — | —:None | None |
| `s7-rob-02.open.cfg-codex-deepseek.r01` | 46574 文件 | 116 条 | 51 次模型调用 | 产物有 | — | —:None | None |
| `s7-rob-02.strict.cfg-codex-deepseek.r01` | 46581 文件 | 85 条 | 51 次模型调用 | 产物有 | valid | none:True | None |
| `s8-cor-01.open.cfg-codex-deepseek.r01` | 46570 文件 | 152 条 | 38 次模型调用 | 产物有 | invalid | —:None | None |
| `s8-cor-01.strict.cfg-codex-deepseek.r01` | 46577 文件 | 191 条 | 50 次模型调用 | 产物有 | invalid | fill:False | None |
| `s8-eco-01.open.cfg-codex-deepseek.r01` | 46570 文件 | 101 条 | 35 次模型调用 | 产物有 | invalid | fill:False | None |
| `s8-eco-01.strict.cfg-codex-deepseek.r01` | 46577 文件 | 123 条 | 29 次模型调用 | 产物有 | invalid | fill:False | None |
| `s8-ops-01.open.cfg-codex-deepseek.r01` | 46570 文件 | 90 条 | 35 次模型调用 | 产物有 | invalid | —:None | None |
| `s8-ops-01.strict.cfg-codex-deepseek.r01` | 46577 文件 | 87 条 | 40 次模型调用 | 产物有 | invalid | —:None | None |
| `s8-rob-01.open.cfg-codex-deepseek.r01` | 46570 文件 | 113 条 | 39 次模型调用 | 产物有 | invalid | —:None | None |
| `s8-rob-01.strict.cfg-codex-deepseek.r01` | 46577 文件 | 83 条 | 27 次模型调用 | 产物有 | invalid | fill:True | None |

> 「无人工干预」的判据是：从 `ops/run_f02_a1.py` 起到 `.score.json` 落地，中间没有人改过任何文件。
> run 目录在 `up` 前后各复核一次（`verify_unchanged`），改过就当场红。

## 3. 三控与验证验证器

- 三控（oracle / null / filler）走**完整评分器**：27 条记录（9 题 × 3 桩），三条判据**全过** —— `/data/shared/genebench/repo/ops/reports/m6/controls.md`
- 逐族破坏样本：19 条，其中**该族响、其余不响** 18 条，覆盖 14 族 —— `/data/shared/genebench/repo/ops/reports/m6/mutations.md`
- O1 矩阵（oracle 零 finding）：**40 题**中，零 finding **34**、有 finding **0**、**没产物 6**（s1-rob-02, s2-rob-02, s3-rob-02, s4-rob-02, s5-rob-02, s8-rob-02 —— 被 E9c 拦在落盘之前，校验器一条都没查，**不计入零误报、也不计入完成定义**） —— 数据源 `ops/reports/probe_run_oracle.cumulative.json`（**累积**文件，定点重跑不会把它打回局部），矩阵 `ops/reports/probe_matrix_oracle.md`（同样从累积文件渲染；`n/a` 与 `·` 在矩阵里分得开）
- 验证验证器报告 v1：`ops/reports/validator_validation_v1.md`

## 4. 主表（构造验收口径，**不是**实验数据）

- Table A：`ops/reports/m6_all/table_a.csv`
- Table B：`ops/reports/m6_all/table_b.csv`
- LaTeX：同目录 `table_a.tex` / `table_b.tex`（`scorer/report.py::to_latex`，空值写 `---` 不写 0）

> ⚠ **这张表是混轴表，不能与 §1 的版本并排读。** 表内自报：`reference_version` = MIXED:r1.0.14|r1.0.8；`set_version` = MIXED:1.0.7|1.0.9；而 §1 声明的是任务集 **1.0.13** / 参考 **r1.0.20**。
> 它是几批**不同题面版本**的 run 合出来的同一行 `pass@1`（合并的理由与逐批版本见该目录 `summary.md` 的脚注；`VERSIONS.md` §2 把它记作「一次真事故」）：
> **它证明的是链路能把一次真运行变成一行主表，不是发布版上的构造验收结果** ——
> 不要与任何单轴表的数并排，也不要当成 §1 那两条轴上的读数。要一张单轴的表，
> 按 §2 的清单自己跑一批（例：`ops/reports/v1demo/`）。

**Recov 列为什么是空的**：**零修复，不是未接线**：10/29 个 run 带 `work/protocol/validator.log`（GQ 臂全都有），validator 被调用 18 次、报出违例 **0** 次 —— 分母是空的，所以 Recov 按「算不出就是 None」留空。**但这个零本身是条发现**：同一批里评分器判 `malformed` 的有 4 个，协议 validator 在它们上一条都没报（N-129）。

**`$` 列为什么是空的**：注册表里没有价目表（DeepSeek 的计价没进 `runner/registry.py`）——tokens 两列是实数，折算成钱要先把价目钉进注册表并留出处。

> 规模就是 M6 的定义：**1 个验收配置 × 双臂 × 每阶段 1–2 题 × 1 种子**。
> 它证明的是「这条链路能把一次真运行变成一行主表」，不是任何模型的能力。

## 4b. 这一批里值得单独说的四件事

1. **agent 顶出了一个 gold 缺陷**（N-124）。`s2-cor-01` 的 gold 面板 41 700 行价格**全是 NaN**，
   `missing_rows.count` 恰好等于总行数 41 700 —— 行数对、sha 有值、校验器只判「非负整数」，**没有任何东西报错**。
   Codex 两臂都报 44（= 该窗口的停牌格数），逼我去看谁对：**agent 对**。修完之后 gold 的 `panel.csv`
   与 agent 那份**逐字节相同**（同一个 sha256）。根因是 `/calendar` 的紧凑日期与 `/bars` 的 ISO 日期在 join 上相遇。
2. **闸门语义在真运行上跑通了一次**。`s3-cor-01` 裸臂的因子**完全正确**（逐日 Spearman 中位数 1.0、130 天全过 τ 门），
   但它读了声明之外的字段（`adj_factor`）→ `declared_reads` 命中 → `validity=invalid` → **效果分不出数**。
   「算得对」与「按规矩算」是两件事，主表上必须分得开 —— 这一行就是证据。
3. **诚实终止被正确记分**。`s7-rob-02`（欠定探针题）的 GQ 臂把 `sell_rule` 标了 `unresolved`、
   依赖它的三块交了 null —— `correct_handling=true`、SR 记 1、效果分**扣住**（`honest_halt`）。
   这正是这道题要测的东西：不知道就说不知道，比编一个数值得分。
5. **判据要求的东西，题面必须说** —— 今晚同一族问题出现三次：S1 的取数台账（N-114）、
   S2 的描述键（N-124）、S8 的事件字段与滑点符号（N-127 / N-128）。三次都是**判据在要题面没写的东西**。
   前两次已按裁定改判；S8 这次判定成立（规格 §3 的正确性项就是「可完整重放」）但对被测方不公平，
   处置写在下面的限制表里。判据设计的自查该加一条：**写完判据回去读题面，判据要的每一样，
   题面上都得能指出是哪一句要求的**。
4. **停下 5 个 run 的是我们设的预算闸，不是 harness**。S4 / S7 两个阶段在 50 次模型调用内做不完
   （`llm_calls=50/51`，产物没写出来）。把 `s4-cor-01` 的闸放到 150 重跑一次（r02），它 **40 次**就交了合法产物。
   → 排 M7 网格时，S4/S7 的调用预算不能按 S1/S2 的量级给。

### 前视（lookahead）：闸门只收**显式越界**，开区间单列遥测

裁定 2026-09-06（第 2 种读法）：**显式越界是意图，开区间是不知道 API 约定**，而「请求须以 `end_date` 界定在 as_of 内」这条约定题面没写 —— 判据要求的东西题面必须说。

- 有产物的 run **20** 个，`lookahead` 命中 **6** 个 → invalid → 效果分扣住。
- 命中的 26 次拒按 reason：`asof_beyond_freeze_line` 23 次；`range_end_after_asof` 3 次
- 摘出闸门的那一类（**遥测**，Table A 的 `unbounded_requests`）：合计 **165** 次未界定右端的请求。
- **oracle 侧零误报**：九道题的 oracle 桩全绿（它们的取数一律显式带 `start_date`/`end_date`）。

约定已写进**两臂共享**的 `work/{stage}.json`（`x-gateway-fetch-contract`，即 `ops/specs/artifact_schema/v1.0/*.json`，由 `reference.artifact_schema.json_schema()` 生成）——**题面正文一个字没动**。
写的时候发现这条路径**在冻结根之外**（改它 agent 就看见了，而两条版本轴一动不动，N-131）——已把 `ops/specs/artifact_schema/` 收进任务集清单的 `code` 段，因此推 **v1.0.10**：**内容未变、`root_scope` 变**（与 1.0.4 那次同形）。

## 5. 已知限制（写在这里，不藏在脚注）

> **本节从 `ops/reports/known_limits_v1.md` 现读**（表上 15 行 / 判定 16 条：已修 5、设计性限制 5、v1.1 6；N-127 与 N-128 各带两半（题面部分已修、判据部分留 v1.1），所以判定条数比表行数多 —— 见该文件的「收口核对」一节）—— 那份是逐条裁定版，这里不留第二份手抄的副本。
> 判定口径只有一条：**挡不挡外部用户**。还挡着、但卡在用户签字的三条（N-388 默认预算档 / N-348 适配赛道题源 / N-130 S7 回合数）单列在该文件的「收口核对」一节。

| 编号 | 限制 | 判定 | 证据 / 影响 |
| --- | --- | --- | --- |
| N-103 | `s6-rob-02` 因无实质性证据出不了集 | **已修**（卡 5.2） | 证据进 `genetask/schema.py::DIVERGENCE_EVIDENCE`（私有 79 处 / 公开 81 处指标超 daily 档 ε 带，两条通道都 material）；出集 33 → **34** 题；两条通道各真跑一次 oracle **零 finding**（`ops/reports/probe_run_oracle.cumulative.json`、`ops/reports/public/probe_run_oracle.cumulative.json`） |
| N-279 | `s2-eco-01` 的 oracle 打 `/bars?universe=…`，网关 422 —— 出集题里唯一跑不出 oracle 的一道 | **已修**（卡 5.2） | 取小改那条（只动参考轴 `solve.py`，按 code 批量 + 按 `MAX_ROWS` 分批）；两条通道各真跑一次**零 finding**，网关日志 8 条 = 2 + 2×3 批，与新的「理论最少请求数」逐字对上 |
| N-127 | S8 滑点的**符号约定**题面没写 | **已修（题面部分）**；判据部分 → v1.1 | 五道题两臂各加一行「成交价高于计价基准时取正、低于取负，单位 bps」，与规格 §3 的 `Slip = 量加权(成交价 − 决策时点价)` 同向；`ops/test_s8_event_fields.py` 钉住。**Fill / Slip 仍只报不判**（`scorer/l3.compare_fill`）—— 纳入判据要另一轮红队，留 v1.1 |
| N-128 | S8 事件记录的**字段**题面与 schema 都没规定，而 Audit 要求「可完整重放」 | **已修（题面 + schema 部分）**；收紧 `required` → v1.1 | 五道题两臂各加四行（order / fill / cancel / state 各要哪些键 + `state_transitions` 要 from/to/order_id）；同一组字段进 `PAYLOAD_SHAPE["S8"].events` 的叶子 `properties` 并重生成八份 `ops/specs/artifact_schema/v1.0/S*.json`。**没有收紧 `required`**：收紧会让 `reference/artifact_samples.py` 的合法样例与既有 121 份真产物集体变畸形，那是判据变更 |
| N-120 | 跑批没把可交易性视图喂给校验器 | **已修**（卡 1.1-c 落地，本卡核实） | 本卡重跑 `s2-cor-01` / `s5-cor-01` 私有 oracle **零 finding**，`calendar` 与 `missing_masquerading_as_signal` 两族真被调用（`ops/reports/probe_matrix_oracle.md`）；判据钉在 `ops/test_public_acceptance.py`（本卡随批跑绿）。**局限照旧**：S8 四题拿不到视图（N-288），逐题记「这两族没被调用过」，不假装 clean |
| N-126 | S6 的 **TE**（跟踪误差）出不来 —— 它要收益率序列，而 v1 的 S6 产物里没有 | **设计性限制** | v1 的 S6 契约（`PAYLOAD_SHAPE["S6"]`）只有 `targets` / `cash_ratio`，没有收益率序列；`scorer/l3` 的 `cons` 判据本来就**不出** TE，并在 `note` 里写明（`scorer/l3.py`「TE 未出：规格 §3 的跟踪误差要收益率序列，S6 产物里没有（N-126）」，`ops/test_scorer_l3.py` 有断言盯着「TE 出不了要写在 note 里，不能悄悄不提」）。**不挡外部用户**：S6 的 Cons / Feas 照常判。v1.1 的补法：给 S6 的 payload 加一段「按 target 权重 × 次日收益」的逐日收益序列，或把 TE 挪到 S7（那里有逐日台账） |
| N-117 | S4 的 IC 族**没有标定 ε 带** | **v1.1** | S4 的 L3 未结算 → effect 扣住；未结算的 run 既不进 pass@1 的分子也不进分母（`unsettled_runs` 列如实报）。**不挡使用**：跑得出来、报表说得清为什么没有数 |
| N-119 | `missing_masquerading_as_signal` 在 M6 集上造不出破坏样本 | **设计性限制**（窗口性质） | 本窗口一格 `no_data` 都没有，这一族的方向未被 M6 集证过。换窗口即可证；判据本身没问题 |
| T-13 | 网关日志**跨机取回**未定 | **设计性限制** | f02 侧四个日志族按 `unobservable` 记；数据面结算读本机日志，这四族在主表里是真判。外部用户在单机上跑不受影响 |
| N-105 | RD-Agent(Q) 没有 LLM 驱动路径 | **设计性限制**（上游） | 三配置里只有两个能跑真题；这是被测系统自身的形态，不是我们的缺陷，主表按能力映射如实标 |
| 卡 5.4 | 替换基线**阶梯**未落地 | **v1.1** | 效果分只有两桩锚点（null 底 / oracle 顶），`anchor_ladder_54=false`；判据（anchor 定义与归一公式）已冻结，缺的是实测数值。结算侧对缺锚点的处置是**拒绝出数而非出 0**（`anchor_pending`）—— 不会静默给错的数 |
| N-129 | 协议 validator 与评分器**判得不一样** | **v1.1（待批）** | 10 个 run 有 `validator.log`、调用 18 次、报违例 0 次，而同批评分器判 malformed 的有 4 个 → GQ 臂的修复回路一次都没启动。要不要两者判据同源是签字项（同源的代价是协议工件里出现评分器的规则） |
| N-130 | S7 在 ≤300 次调用的预算里做不完 | **v1.1（待用户裁定）** | 四个 run（150 闸 / 3 M token 撞 token 闸；90 闸 / 20 M token 撞调用闸）全无产物。卡 4.3 之后 S7 走 300 次 / 18 M 的档，但**回合数**仍是瓶颈（tokens 只用到 5.2–5.6 M）。挡的是「S7 这一阶段能不能有真 agent 产物」，不挡整套系统的使用 |
| 新登记（本卡量到） | 滑点的符号在**我们自己的两份实现**里不一致 | **v1.1（CONFLICT，已登记）** | `gateway/sim_engine.py::slippage_bps` 按 `Σ qty × (成交价 − 基准) / 基准` 算，**不按买卖翻符号**（与规格 §3 同形）；`reference/s8_oracle_common.py::fill_metrics` 的 docstring 写「买正卖负」并真的乘了 `sign`。买单两者同号，卖单相反。**今天不影响任何分数**（Slip 只报不判），但 v1.1 把 Slip 纳入判之前必须先把这两处对齐，并以规格 §3 为准 |
| 新登记（本卡量到） | 出集清单里仍有 **6 道欠定探针题**不落盘 | **设计性限制** | `s1/s2/s3/s4/s5/s8-rob-02` 六道被 E9c/E9d2 拦在落盘之前 —— 它们的欠定字段还没有实测实质性证据。这**正是判据在起作用**（没有证据就不出题），不是缺陷。要放行就照 `s6-rob-02` 这次的路子跑 `ops/run_materiality_screen.py` |

## 6. 就绪判定

**v1.0 的构造验收成立**当且仅当上面每一节都有产物、且验证验证器报告判定通过。
本报告只陈述状态，不代替签字。
