# GeneBench v1.0 就绪报告（M6 构造验收 · 产出 ①）

> 通道 `public`；批 `m6_public`；④⑤ 明细 `ops/reports/public`；O1 矩阵 `ops/reports/public`。

> ⚠ **这一批的真跑没有发生**（`records.json` 里 0 个 run）。§1 / §3 / §5 不依赖 run，是真的；
> §2 的 0 与 §4 的「不适用」也是真的。**§4 / §4b 的逐 run 叙述本节不渲染** ——
> 把有 run 那一批的叙述套在 0 run 上，得到的每一句都不成立。

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

> **`provider_sha256_pinned=False` 的原因**：注入器现在只核 provider 的**根指纹**（`pin.check_provider_pin` 比对 `files.sha256` 这个文件的 sha256 = `54fdda39…`，P2 门），**没有**逐文件重算那棵树 —— 也就是说「provider 换了一个文件」这件事目前查得出的前提是它自带的 `files.sha256` 也跟着变。卡 4.2 的适配层要做的逐文件核对还没落地，所以这把锁维持 false。

### 执行面（f02）

```
（没有执行面环境快照）
```

- **执行面的四个钉子：（未采集）** —— runner_version / h11 清单 sha / 边车 sha / 任务镜像都取自真 run 的 `inject.json`，而本批 **0 个 run**。这里不写 0、也不写空指纹。

### 数据面（f01）

- 网关：user systemd `genebench-gateway.service`（常驻、单 worker、绑 LAN、snapshot 后端）
- oracle 环境：python 3.10.20 / pandas 2.2.3 / numpy 1.26.4 / pyarrow 20.0.0
- 跨版本核：`ops/reports/crossver_probe_a1.md` —— 与统一基座 **17/18 键逐位相同**（唯一不同是 parquet 字节流 sha，读回的值相同）

## 2. 全链一次无人工干预跑通

链路：`build_task → write_task → export_bundle（钉 digest + 出通行证）→ push_bundle_to_f02（发送侧门 + 接收侧扫描）→ inject（P0–P9 + 边车 + h11 + 模型反代 + 预算闸）→ docker compose up → 容器跑 agent → harvest（down -v 之前）→ 拉回数据面 → gate（校验器 + 三态）→ L3 → validate_scorer_output → Table A/B`。

本批（m6_public）**0 个 run**，其中 `run_status=ok` **0** 个。逐 run 证据：

| run | 注入 | 边车 | 容器 | 采集 | 闸门 | L3 | 效果分 |
| --- | --- | --- | --- | --- | --- | --- | --- |

> 「无人工干预」的判据是：从 `ops/run_f02_a1.py` 起到 `.score.json` 落地，中间没有人改过任何文件。
> run 目录在 `up` 前后各复核一次（`verify_unchanged`），改过就当场红。

## 3. 三控与验证验证器

- 三控（oracle / null / filler）走**完整评分器**：27 条记录（9 题 × 3 桩），三条判据**全过** —— `ops/reports/public/controls.md`
- 逐族破坏样本：19 条，其中**该族响、其余不响** 18 条，覆盖 14 族 —— `ops/reports/public/mutations.md`
- O1 矩阵（oracle 零 finding）：**40 题**中，零 finding **34**、有 finding **0**、**没产物 6**（s1-rob-02, s2-rob-02, s3-rob-02, s4-rob-02, s5-rob-02, s8-rob-02 —— 被 E9c 拦在落盘之前，校验器一条都没查，**不计入零误报、也不计入完成定义**） —— 数据源 `ops/reports/public/probe_run_oracle.cumulative.json`（**累积**文件，定点重跑不会把它打回局部），矩阵 `ops/reports/public/probe_matrix_oracle.md`（同样从累积文件渲染；`n/a` 与 `·` 在矩阵里分得开）
- 验证验证器报告 v1：`ops/reports/public/validator_validation_v1_public.md`

## 4. 主表（构造验收口径，**不是**实验数据）

> **本批 0 个 run —— 主表与逐 run 叙述都不适用，本节不渲染。**
> 没有 run 就没有 Table A / B（**不是出表坏了**）；Recov / `$` / `unbounded_requests` 这些列的口径要在有 run 的批上才谈得上，前视闸的实测数字同理。
> 这一批为什么没跑、卡在哪两件执行面前置：`ops/reports/m6_public/README.md` §2。
> 有 run 的那一批（私有通道 `m6` + `m6b`）的主表与逐 run 叙述在 `ops/reports/v1_0_readiness.md`。

- Table A：**未生成（本批 0 个 run）**
- Table B：**未生成（本批 0 个 run）**

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
