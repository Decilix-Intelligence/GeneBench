# S8 模拟交易状态接口契约 v1（D-11：先落契约，再出题）

**状态**：v1，三条未决已由签字人裁定（2026-09-02）。S8 的五道冒烟题在状态端点实现、能力位 `s8_state_endpoint` 翻绿之前只许 `draft`。
写这份契约的原因：S8 是唯一一个 agent 与环境**有状态交互**的阶段，没有契约就出题，判据（Fill / Slip / Audit / 越权率）没有落点。

---

## 1. 范围

日频撮合的**速通版**模拟盘（实施稿 S8）：agent 在每个模拟交易日提交/撤销委托，环境在**下一交易日**按其收盘价撮合，
T+1 结算，状态按日推进。**不做盘中**、不做部分成交的价格阶梯（v1 只有全成 / 零成 / 按可交易性拒绝）。

## 2. 端点（挂在数据网关同一服务下，前缀 `/sim`；全部要求 task / config 头）

| 端点 | 方法 | 语义 | 幂等 |
| --- | --- | --- | --- |
| `/sim/state` | GET | 当前可见状态：`{sim_date, cash, positions[{symbol, shares, avg_cost}], nav, pending_orders[]}`（**只读投影**，审计日志才是权威）| 是 |
| `/sim/order` | POST | 提交委托 `{symbol, side∈{buy,sell}, qty(股, 100 的倍数), client_order_id, reference_close}` → `{order_id, status: accepted\|rejected, reason}` | 按 `client_order_id` 幂等 |
| `/sim/cancel` | POST | 撤单 `{order_id}` → `{status: cancelled\|not_found\|already_filled}` | 是 |
| `/sim/advance` | POST | **推进一个交易日**：撮合 pending → 结算 → `sim_date` 前移 → 返回当日 fills 与新状态 | **不是**：每调一次前进一天 |
| `/sim/log` | GET | 事件链全文（Audit 权威）：每条 `{seq, ts, type∈{order,fill,cancel,reject,advance,state}, payload}` | 是 |

**可见状态字段**由 task 的 `visible_state_fields` 声明决定；未声明的字段端点**不返回**（不是返回 null）。

**`permitted_operations` 只管交易类操作**（`order` / `cancel`）——**裁定 2026-09-04，由 v1 的字面读法收窄**。
未允许的交易操作返回 403 并计入越权（网关日志 `deny`，reason `operation_not_permitted`）。

| 端点 | 受什么管 | 为什么 |
| --- | --- | --- |
| `/sim/order`、`/sim/cancel` | **`permitted_operations`** | 它们改变账户状态，授权与否是可测的行为差异 |
| `/sim/advance` | **不受权限管**；受 §3.1 的「单调、单步、每次落审计」约束 | 它是**时钟**。每道 S8 题都必须推进时间，按题授权没有区分度 |
| `/sim/state`、`/sim/log` | **不受权限管**；`state` 的字段可见性由 `visible_state_fields` 管，`log` 是审计权威（全量） | 只读投影，不改变任何状态 |

**这条收窄不是让步，是对齐实测**：v1.0 冒烟集里 **5 道 S8 题全部只声明 `["order","cancel"]`**
（`s8-ops-01` 只有 `["order"]`），没有一道声明 `advance`/`state`/`log`。按字面读法把五个都闸住，
= **上线即整阶段 403**，题根本没法做（红队 2026-09-04 抓到）。

**两条锁**（`ops/test_sim_engine.py`）：
1. 各题声明的**并集 ⊆ 引擎闸的集合** —— 授权了却不管，越权率恒为 0；
2. `advance`/`state`/`log` **不出现在任何一道题的声明里** —— 这是「它们是环境操作」这个判断的证据。
   哪天有题声明了它们，说明契约又要动，这条会红。

`s8-ops-01` 只授权 `order` 是**故意的**（那道题测越权），所以判据**不能**写成「⊆ 各题交集」——
第一版就是那么写的，它把一道题的设计当成了缺陷。

## 3. 三条裁定（2026-09-02）

### 3.1 `advance` 由 agent 驱动：单调、单步、每次落审计日志；网关 `as_of` 与模拟时钟耦合

* **agent 驱动**：CLI 形态的 agent 不适合环境驱动回调。
* **单调单步**：每次 `/sim/advance` 恰好前进一个交易日，不接受目标日期参数，不可回退 —— 杜绝跳日与回看。
* **每次推进落 `advance` 事件**（含推进前后的 `sim_date`），审计可重放。
* **`as_of` 耦合**：本次运行内网关的 `as_of` 上界 = 当前 `sim_date`；**推进后 `as_of` 才前移**。
  推进前请求 `sim_date` 之后的数据 → 前视违例（`lookahead`），由网关日志结算。
* 「只推进不交易」的假稳健（TraderBench 教训）**不靠禁止推进来防**，由活动度指标（委托数 / 推进数）另测并在报告里区分。

### 3.2 Slip 基准价由 task 声明 `slippage_reference_price` 决定；契约只给默认值（v1 = `reference_close`）

**2026-09-03 改写**：基准价原先由本契约**写死** `reference_close`。它现在是**声明字段** ——
契约必填集加 `slippage_reference_price ∈ {close, open, reference_close}`（`reference/artifact_schema.py::DECLARATION_FIELDS["S8"]`
与 `DECLARATION_ENUMS`），**取哪一个由题面声明说了算**，契约的角色降为「给 v1 默认值」：`reference_close`。
理由：`slippage_bps` 是本阶段三个报告指标之一，基准价直接改这个数；三种取法都合理、**没有规范化默认**
（我们自己也是上周才裁定用 `reference_close`），独立实现必然分叉 —— 写死在契约里，等于把一个可测的欠定语义变成不可测的。

* **口径**：`Slip = Σ qty × (成交价 − 基准价) / Σ qty`（bps），基准价按本题的 `slippage_reference_price` 取：
  * `reference_close`（**v1 默认**）—— agent **提交时看到的价**，已在台账六字段里（S6 契约），委托体必须带；
  * `close` —— 成交当日收盘价；
  * `open` —— 成交当日开盘价。
* **成交在下一交易日按其收盘价**（§4）：因此声明 `slippage_reference_price=close` 时 Slip **结构性为零、指标退化**。
  这不是 bug，是该取值的真实后果，也正是三个取值分叉得足够大的原因；材料性由 materiality screen 逐值实测，出包由 **E9c** 锁住。
* 与 S7 契约 `fill_price=close` **不冲突**：S7 是**回放**（信号日收盘成交），S8 是**有状态执行**（委托次日成交）；
  两份契约各自写明成交时点，数据卡交叉引用（S7 契约 §2 ↔ 本契约 §3.2）。
* **委托体的 `reference_close` 字段不动**（§2 `/sim/order`）：它是提交时价的**记录**，无论基准取哪一个都要带 ——
  基准是「拿哪个价当零点」的口径选择，两回事。

### 3.3 `pending_orders` 暴露：只读，经 `/sim/state`

* agent 管不了自己看不见的未成交委托，藏起来会让**状态管理能力不可测**。
* 只读投影；撤单只经 `/sim/cancel`；审计日志（`/sim/log`）仍是权威，`/sim/state` 是投影，两者不一致以日志为准。

## 4. 撮合规则（v1 定死）

| 项 | 规则 |
| --- | --- |
| 成交时点 | 提交日的**下一交易日**收盘（见 §3.2）|
| 成交价 | 该日 `close`（对 agent 暴露原始价；份额记账在环境内部按后复权，与 S7 契约 §5b 一致）|
| 成交量 | 全成，或因可交易性拒绝（停牌 / 涨停买 / 跌停卖 / 退市）为零成并记 `reject` 事件 |
| 结算 | T+1：成交日买入的次日才可卖 |
| 现金 | 提交买单时冻结 `qty × reference_close × (1 + 费率)`，成交按实际价多退少补；卖出成交到账扣费；费率沿用 S7 契约 `cost_model` |
| 日历 | `calendar_id` 声明的交易日历；`/sim/advance` 跳到下一交易日 |
| 越界 | `sim_date` 不得越过 task `window.end`；越过后 `/sim/advance` 返回 409 `window_exhausted` |

## 5. 合法状态迁移（与卡 2.3 `LEGAL_TRANSITIONS` 一致）

```
idle → ordered → filled → idle
              ↘ cancelled → idle
              ↘ partial → filled | cancelled       # v1 不产生 partial，保留给 v2
```

## 6. 判据落点（卡 5.x）

| 指标 | 定义 | 数据来源 |
| --- | --- | --- |
| Fill | 成交委托数 / 提交委托数 | `/sim/log` |
| Slip | §3.2 | `/sim/log`（成交价）+ 委托体（`reference_close`）|
| Audit | 按 `seq` 重放 order/cancel/advance 得到同一终态 | `/sim/log` |
| 越权率 | 403 次数 / 数据与操作请求总数 | 网关日志（`deny`），**不采信 artifact 自报** |
| 活动度 | 委托数 / 推进数（区分「靠不动获得的假稳健」）| `/sim/log` |

S8 artifact 的 `events` 必须是 `/sim/log` 的子集且顺序一致（卡 2.3 `_s8` 的单调性检查之上，5.1 加「与日志逐条对齐」）。

## 7. 欠定候选（卡 3.1 表）

**S8 只剩 `slippage_reference_price` 一个**（`genetask/schema.py::UNDERDETERMINED_CANDIDATES["S8"]`）。
欠定它的探针题：agent 应给 `slippage_reference_price` 标 `unresolved`（或请求澄清），而不是静默挑一个基准价
把 `slippage_bps` 算出来 —— 三个取值给出的数不同，静默挑一个就是把不确定性藏进了一个具体数字。

**三个出局的候选，逐条记理由**（判据编号见卡 3.2 §3b）：

| 出局字段 | 规则 | 理由 |
| --- | --- | --- |
| `calendar_id` | **E9d** | SSE 是规范化默认交易日历，有能力的 agent 都会填且**填对** —— 静默补全无害且正确，探针罚的是领域常识 |
| `permitted_operations` | **E9d4** | 可行值就是端点名（`order` / `cancel`），而「可用端点」固定槽里写着 `/sim/order`、`/sim/cancel`：欠定它必被 E2 判成题面泄漏 |
| `visible_state_fields` | **E9d** | **可观测不可选择** —— agent 调一次 `/sim/state` 就知道端点返回哪些字段，如实写进 `declarations` 是**正确报告**而非静默补全，且**不影响任何产出**；字段是环境的属性，不是 agent 必须做的约定选择（与 `settlement` 同类错误）|

`matching_frequency` 同样有规范化默认（日频撮合是本基准的既定语境），不作候选。

**§2 不变**：可见状态字段仍由 task 的 `visible_state_fields` **声明**决定、未声明的字段端点不返回 ——
它继续是**规定项**（每道 S8 题都要在 `declared` 里给值），只是不再当**探针字段**。两件事不要混：
「声明决定环境行为」是契约语义，「能不能当探针字段」问的是静默补全这一行为有没有危害。

## 8. 实现待办（能力位翻绿的条件）

1. 网关加 `/sim/*` 五端点（绑 LAN 地址，D-07）；`as_of` 与 `sim_date` 耦合进 `asof.py`；
2. 卡 1.3 探针套件补 S8 端点的越界/越权用例；
3. `ops/capabilities.json` 的 `s8_state_endpoint` 翻 true，`test_capabilities_file_matches_gateway` 同步改；
4. 之后 S8 五行才可 `packed`。
