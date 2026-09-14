# 卡 4.4：S8 模拟盘（`/sim/*` 五端点、日频撮合、审计日志）

**实现 `ops/specs/s8_state_contract.md` v1，一字不改地实现，不在本卡重新裁定契约。**
S8 是全基准**唯一**一个 agent 与环境**有状态交互**的阶段；今天这个环境**不存在** ——
网关只挂了 `market` 与 `reference` 两个 router，`ops/capabilities.json` 的 `s8_state_endpoint` 是 `false`，
S8 oracle 的 HTTP 客户端是 `raise NotImplementedError`。

**S8 的五道冒烟题全部等这张卡**（不只是探针题 `s8-rob-02`）：
`s8-cor-01` 的生命周期、`s8-rob-01` 的幂等、`s8-eco-01` 的最小滑点、`s8-ops-01` 的越权率、
`s8-rob-02` 的 `slippage_reference_price` —— 五道题的**被测对象是同一个东西**，就是本卡要造的模拟盘。
卡 3.2 §0 把 S8 五行整体记在这张卡名下。

---

## 0. 本卡不做什么

写在最前面，因为这张卡最容易被写成「顺手做成一个真回测器」。

| 不做 | 为什么 |
| --- | --- |
| **不做盘中撮合、不做部分成交的价格阶梯** | 契约 §1 定死：v1 只有全成 / 零成 / 按可交易性拒绝。`partial` 这个状态在 `LEGAL_TRANSITIONS` 里保留给 v2，**v1 不产生** —— 造得出 `partial` 就是实现跑偏了 |
| **不做撮合规则的任何再裁定** | 成交时点、成交价、结算、现金冻结、日历、越界全在契约 §4，**本卡只实现**。发现契约有洞 → 改契约并升版本，不在实现里悄悄补 |
| **不做 `as_of` 的第二份判定** | `gateway/asof.py` 是「全网关唯一的一份实现」，`/sim/*` 必须过同一份。见 §2.2 |
| **不做新的日志体系** | 越权率的权威是**网关 `access_log`**（契约 §6），不是模拟盘自己的日志，更不是 artifact 自报。见 §2.5 |
| **不做独立进程 / 独立端口** | 必须挂在数据网关同一服务、同一端口下。见 §1.1 —— 这是卡 4.1 的硬约束，不是部署偏好 |
| **不改 S7 契约** | S7 是**回放**（信号日收盘成交），S8 是**有状态执行**（委托次日成交）。两者的 `fill_price` 语义不同**不是冲突**，各自契约写明即可（契约 §3.2 末条） |
| **不给 agent 任何「答案面」** | `FORBIDDEN_PATH_TOKENS = ("reference", "scorer", "gold", "answer", "probe")`（`gateway/app.py`）。`/sim/*` 不含这些字样，但**新增子路径时要重新过这条**——比如不许出现 `/sim/answer` 之类 |

---

## 1. 挂在哪：网关同一服务，路由白名单显式登记

### 1.1 决定：`/sim/*` 是数据网关的第三个 router，不是一个新服务

**为什么 —— 这条由卡 4.1 决定，不是由方便决定。** 卡 4.1 §3.2 的隔离靠**拓扑**而不是防火墙规则：
任务容器接 `gb_task`（`internal: true`），**根本没有默认路由**，出向白名单只有两个目标 ——
网关 `192.168.1.48:18080` 与出向代理。

> 结论：**模拟盘若起成第二个服务/第二个端口，被测 agent 从任务容器里够不到它**，
> 而且失败形态是「连不上」而不是「被拒绝」——一个新的 D-06 面：题跑不了，日志里什么都没有。
> 要够到它就得放宽卡 4.1 的白名单，等于**为了做 S8 去拆隔离**。

`/sim/*` 因此挂 `gateway/app.py` 的 `create_app()`，与 `market`、`reference` 并列：

```python
app.include_router(market.router)
app.include_router(reference.router)
app.include_router(sim.router)          # 卡 4.4
```

### 1.2 五个端点必须逐条登记进 `ALLOWED_ROUTES`

`gateway/app.py` 的 `ALLOWED_ROUTES` 是**白名单**，注释写得很清楚：
「新增端点必须显式登记，漏登记的失败形态是 404（响的）而不是意外可达（哑的）」。

```python
ALLOWED_ROUTES = frozenset({
    "/healthz", "/bars", "/adj", "/calendar", "/limits",
    "/universe", "/tradability", "/fundamentals",
    "/sim/state", "/sim/order", "/sim/cancel", "/sim/advance", "/sim/log",   # 卡 4.4
})
```

**为什么逐条列而不是 `/sim/{op}` 一条**：一条通配会让「实现里多写了一个没在契约里的操作」变成**静默可达**。
逐条列时，多出来的那个操作在启动自检 `assert_route_whitelist()` 上当场红。

### 1.3 头与参数纪律沿用网关既有的

* 五个端点**全部要求** `x-genebench-config-id` 与 `x-genebench-task-id`（契约 §2），
  两个头都进 `access_log` 的 `config_id` / `task_id` 字段；
* **GET 的标量参数重复即 422**（`SCALAR_PARAMS` 中间件）—— `/sim/state`、`/sim/log` 沿用；
* **⚠ 已知洞（§7-1）**：`SCALAR_PARAMS` 只查 query string，**管不到 POST 的 JSON body**。
  `/sim/order`、`/sim/cancel`、`/sim/advance` 是 POST，body 里的重复键要**自己**顶回去，
  语义与中间件一致：**歧义由调用方消除，环境不替它择一**。

---

## 2. 五条决定（每条写为什么）

### 2.1 `advance` 单调、单步，且每次落一条审计事件

**做法**：`POST /sim/advance` 恰好前进**一个交易日**，**不接受目标日期参数**，不可回退；
每次推进写一条 `type="advance"` 的审计事件，payload 含**推进前与推进后的 `sim_date`**。

**为什么单调单步**（契约 §3.1）：接受目标日期就等于把「跳日」和「回看」交给被测方去自律。
跳日会让 T+1 结算与冻结现金整段被绕过；回退会让同一天被撮合两次，`Fill` 的分母失去意义。
**这不是靠文档禁止，是靠接口形状** —— 端点收不到日期参数，就没有可以违反的规则。

**为什么每次必须落事件**：`Audit` 的定义是「按 `seq` 重放 order/cancel/advance 得到同一终态」（契约 §6）。
**`advance` 不落事件，重放就少了时间轴** —— 同一串 order/cancel 在不同的推进次数下终态不同，
而重放器会算出「一致」，因为它根本不知道中间推进过。这是 D-06 的形态：判据看起来绿，实际上空。

**活动度另测**：契约 §3.1 末条 —— 「只推进不交易」的假稳健（TraderBench 教训）**不靠禁止推进来防**，
由活动度指标（委托数 / 推进数）在报告里单列。本卡**不加任何最小交易量的限制**。

### 2.2 `as_of` 与 `sim_date` 耦合：本次运行的 `as_of` 上界 = 当前 `sim_date`，推进后才前移

**做法**：`gateway/asof.py` 加一层「运行内上界」——同一 `(config_id, task_id)` 下，
`as_of` 的允许上界取 `min(冻结线 FREEZE_DATE, 当前 sim_date)`；`/sim/advance` 成功后该上界才前移。
判定仍然**只在 `asof.py` 里做一次**（该模块的模块注释：「所有端点都必须过这里，不许各写各的」）。

**为什么耦合**：没有它，S8 的前视是**免费**的 —— agent 在 `sim_date = 2026-03-02` 时
直接向 `/bars` 请求 `as_of=2026-07-31`，拿到未来三个月的价格再决定今天下什么单。
数据面全程合法（没越冻结线），网关日志全绿，而这次运行的交易决策是拿未来做出来的。

**为什么是「推进后才前移」而不是「推进时一起判」**：判定必须**先于取数**（`asof.py` 不变量 2）。
先取后判会在日志里留下一次实际读取，卡 5.1 结算前视时分不清「读了但没给」与「根本没读」。

**失败形态与落点**：推进前请求 `sim_date` 之后的数据 → **403**，`reason` 落 `access_log`。
沿用既有 `Reason` 里的越界值（`TARGET_AFTER_ASOF` / `RANGE_END_AFTER_ASOF` / `ASOF_BEYOND_FREEZE`），
**不新造一个 sim 专用的越界原因** —— 前视就是前视，卡 5.1 的探针按同一批 reason 结算。

### 2.3 Slip 的基准价由 `slippage_reference_price` **声明**决定，契约只给默认值

**做法**：环境按本题 `declared.slippage_reference_price` 取基准价，三选一：
`reference_close`（**v1 默认**，agent 提交时看到的价，委托体必须带）/ `close`（成交当日收盘）/ `open`（成交当日开盘）。
口径 `Slip = Σ qty × (成交价 − 基准价) / Σ qty`（bps）。

**为什么不写死在实现里**（契约 §3.2，2026-09-03 改写）：`slippage_bps` 是 S8 三个报告指标之一，
基准价**直接改这个数**；三种取法都合理、**没有规范化默认**（我们自己也是上周才裁定用 `reference_close`）。
写死等于**把一个可测的欠定语义变成不可测的** —— 而这正是 `s8-rob-02` 要测的东西。

**两个必须实现对的细节**：

1. **`slippage_reference_price=close` 时 Slip 结构性为零**。因为 v1 的成交就是「下一交易日收盘价」（§3），
   成交价 ≡ 基准价。**这不是 bug，是该取值的真实后果**，实现**不许**为了「让指标好看」去改成别的价。
   它恰恰是三个取值分叉足够大的原因。
2. **委托体的 `reference_close` 字段不动**（契约 §2 `/sim/order`）。它是**提交时价的记录**，
   无论基准取哪一个都要带。基准是「拿哪个价当零点」的口径选择，两回事 —— 不要把这两个名字相近的东西合并。

**默认值的位置**：契约给默认（`reference_close`），**实现不给默认**。题面没声明这个字段时（探针题就是这种），
环境按契约默认跑，但**产物里要如实记下用的是默认** —— 不许让「默认」看起来像「agent 选的」。

### 2.4 `pending_orders` 只读投影，撤单只经 `/sim/cancel`

**做法**：`/sim/state` 返回 `pending_orders[]`；它是**投影**，改不了。要撤单只有 `/sim/cancel` 一条路。
`/sim/state` 与 `/sim/log` 不一致时，**以日志为准**（契约 §3.3）。

**为什么暴露**：agent 管不了自己看不见的未成交委托。藏起来会让**状态管理能力不可测** ——
而状态管理正是 S8 相对于 S7 多出来的那件事，藏掉它这个阶段就白设了。

**为什么只读**：可写的投影会产生**两条修改路径**（改投影 / 调 `/sim/cancel`），
两条路径的审计事件不可能一直对齐，`Audit` 重放就会出现「日志重放的终态 ≠ 端点报的终态」，
而两边都自称权威。**一份权威（日志）+ 一份投影**是唯一不会漂的形状。

### 2.5 越权 403 计入**网关日志**的 `deny`，不采信 artifact 自报

**做法**：`permitted_operations` 未允许的操作 → **403**，`reason = "operation_not_permitted"`，
经 `access_log.record(decision="deny", reason=..., config_id=..., task_id=...)` 落盘。
需要在 `gateway/errors.py` 的 `Reason` 里**新增一个成员**（现有的都是 as_of / 白名单 / 参数三类，没有操作权限这一类）：

```python
    # --- 操作权限（卡 4.4 / S8）---
    OPERATION_NOT_PERMITTED = "operation_not_permitted"
```

**为什么是 403 而不是 400**：`GatewayDenied` 的既有约定 ——「你问的东西存在，但在你的视角下不该看见」
是**授权语义**，一律 403；语法错误才用 422。越权是授权语义。

**为什么权威是网关日志**：契约 §6 写死「越权率 = 403 次数 / 数据与操作请求总数，来源网关日志，**不采信 artifact 自报**」。
这条与红队协议 §2.1 是同一条规则的两个实例：**被判者自报的东西只能是被核的对象，不能是核的依据**。
S8 artifact 里的 `overreach.denied_requests` 是**被核对象**；分母分子都从 `access_log` 按
**任务侧**的 `task_id` 切片取（不是 artifact 自报的 `task_id` —— 那是红队打出来的 36 个洞之一）。

**⚠ 别把 N-36 再造一遍**：那条洞（`_log_slice` 以信封**自报**的 `config_id` 为切片键且无人核对 ——
自报一个不存在的 `config_id` 就让切片变空、空切片被读成「零请求」，S8 越权探针两步被绕过）**已在校验器侧修掉**。
本卡的义务是**不在环境侧把它还原**：`/sim/*` 写进 `access_log` 的 `config_id` / `task_id` 必须是 **runner 真值**，
不是从请求头里照抄一份就算数 —— 头是被测方给的。拿不到真值时按既有处置「空切片 + 同 task 有日志」判 `malformed`，**不判通过**。

---

## 3. 撮合与状态机（照契约实现，无裁定）

| 项 | 规则（契约 §4） |
| --- | --- |
| 成交时点 | 提交日的**下一交易日**收盘 |
| 成交价 | 该日 `close`（对 agent 暴露原始价；份额记账在环境内部按后复权，与 S7 契约 §5b 一致）|
| 成交量 | 全成，或因可交易性拒绝（停牌 / 涨停买 / 跌停卖 / 退市）零成并记 `reject` 事件 |
| 结算 | T+1：成交日买入的次日才可卖 |
| 现金 | 提交买单冻结 `qty × reference_close × (1 + 费率)`，成交按实际价多退少补；卖出成交到账扣费；费率沿用 S7 契约 `cost_model` |
| 日历 | `calendar_id` 声明的交易日历；`/sim/advance` 跳到下一交易日 |
| 越界 | `sim_date` 不得越过 task `window.end`；越过后 `/sim/advance` 返回 **409** `window_exhausted` |

**合法迁移**：直接引用 `reference/artifact_schema.py::LEGAL_TRANSITIONS`（**不重抄一份**）：

```
idle → ordered → filled → idle
              ↘ cancelled → idle
              ↘ partial → filled | cancelled       # v1 不产生 partial，保留给 v2
```

**为什么引用而不是重抄**：卡 2.3 的校验器用这个常量判 S8 artifact 的 `state_transitions`。
抄第二份，两份就会漂 —— 而漂的表现是「校验器说合法、环境说非法」或者反过来，两边都不报错。
**实现里的迁移表必须 `from reference.artifact_schema import LEGAL_TRANSITIONS`，
并有一条测试断言环境实际产生过的迁移集 ⊆ 该常量。**

**幂等**：`/sim/order` 按 `client_order_id` 幂等（重复提交返回同一个 `order_id`，**不产生第二条 order 事件**）；
`/sim/cancel` 幂等；`/sim/state`、`/sim/log` 幂等；**`/sim/advance` 不是** —— 每调一次前进一天。
`s8-rob-01` 测的就是这条。

---

## 4. 审计日志（`/sim/log`）

**形状**：每条 `{seq, ts, type ∈ {order, fill, cancel, reject, advance, state}, payload}`，`seq` 从 1 严格单调递增。

**三条硬要求**：

1. **`/sim/log` 是权威**，`/sim/state` 是投影（§2.4）。
2. **落盘位置与 `access_log` 分开**：`access_log` 记「谁在什么 as_of 下请求了什么」（前视与越权的结算源），
   sim 审计日志记「模拟盘内部发生了什么」（Fill / Slip / Audit 的结算源）。**两份日志不合并** ——
   合并会让「网络侧证据」与「环境内部叙述」混成一份，而后者部分来自被测方的输入。
3. **S8 artifact 的 `events` 必须是 `/sim/log` 的子集且顺序一致**（契约 §6 末句）。
   卡 5.1 在卡 2.3 `_s8` 的单调性检查之上加「与日志逐条对齐」。

---

## 5. 验收条件（可测，缺一不过）

**每条都要有一个能跑的断言**，不是「人工看一眼」。落 `ops/test_sim_engine.py`；
涉及网关起停的落 `verify_c44.sh`（形状照 `verify_c41_item6.sh`）。

| # | 条件 | 判据 |
| --- | --- | --- |
| SIM-A | 五个端点全部登记进 `ALLOWED_ROUTES` | 启动自检 `assert_route_whitelist()` 过；且实际路由集 **== 白名单**（多一条也红）|
| SIM-B | 五个端点缺任一必需头 → 拒绝，且落 `access_log` | 缺 `x-genebench-task-id` 时状态码非 2xx，日志里有对应 `deny` 行 |
| SIM-C | `/sim/advance` 单步 | 调 1 次 `sim_date` 前进恰 1 个交易日；带任何日期参数调用 → 拒绝（参数不被接受）|
| SIM-D | `advance` 落审计事件 | 每次推进后 `/sim/log` 恰多 1 条 `type="advance"`，payload 含推进前后 `sim_date` |
| SIM-E | `as_of` 耦合 | `sim_date = D` 时请求 `as_of > D` 的数据 → **403**，`access_log` 的 `reason` ∈ 越界族；`advance` 后同一请求 → 200 |
| SIM-F | Slip 基准价随声明改变 | 同一串委托，`slippage_reference_price` 取三个值跑三遍：`close` 一档 `slippage_bps == 0`（结构性），三档**互不相同** |
| SIM-G | `pending_orders` 只读 | 任何试图经 `/sim/state` 改动 pending 的请求都不存在可用形状（端点只有 GET）；撤单只经 `/sim/cancel` 生效 |
| SIM-H | 越权 403 计入网关日志 | `permitted_operations` 不含 `cancel` 时调 `/sim/cancel` → 403 且 `access_log` 有一行 `decision="deny"`, `reason="operation_not_permitted"`；**该行的 `task_id` 取自 runner 真值**（自报一个不存在的 `config_id` 不能让切片变空 —— N-36）|
| SIM-I | 迁移合法 | 一次完整运行产生的迁移集 ⊆ `LEGAL_TRANSITIONS`；**且 v1 不出现 `partial`** |
| SIM-J | 幂等 | 同 `client_order_id` 提交两次 → 同一 `order_id`，`/sim/log` 只多 1 条 order 事件；`/sim/advance` 两次 → `sim_date` 前进 2 天（**不幂等**是它的正确行为）|
| SIM-K | 审计可重放 | 按 `seq` 重放 order/cancel/advance → 终态与 `/sim/state` 一致（Audit 判据）|
| SIM-L | 越界 | `sim_date` 到 `window.end` 后再 `advance` → **409** `window_exhausted` |
| SIM-M | 答案面 | `/sim/*` 的任何路径都不含 `FORBIDDEN_PATH_TOKENS` 的字样；`reference/`、`scorer/` 不在任何 sim 路由里 |
| SIM-N | 卡 4.1 可达性 | 从 f02 任务容器（`internal: true`）经既有白名单能打到 `/sim/state`；打不到即说明它没挂在网关同端口下 |

**负例的独立判别力**（照卡 4.1 §5 的做法）：每条负例**必须被它自己那条判据拦下**。
只要求「全红」是不够的 —— 一个负例若因别的判据红，被测的那条其实是空的。

---

## 6. 能力位 `s8_state_endpoint` 的翻绿条件

`ops/capabilities.json` 里它现在是 `false`，`ops/test_gateway_fields.py:138` 有一条**反向断言**：

```python
assert caps["s8_state_endpoint"] is False, "S8 状态端点还没做；做了要先改这条测试"
```

**翻绿的顺序不能反**（契约 §8 + 本卡）：

1. **五端点实现并登记**（§1）、`as_of` 与 `sim_date` 耦合进 `asof.py`（§2.2）、
   `Reason.OPERATION_NOT_PERMITTED` 落地（§2.5）；
2. **§5 的 SIM-A…SIM-N 全绿**，负例逐条有独立判别力；
3. **卡 1.3 探针套件补 S8 端点的越界 / 越权用例**（契约 §8-2）；
4. 先改 `ops/test_gateway_fields.py::test_capabilities_file_matches_gateway` 的那条断言，
   **再**把 `ops/capabilities.json` 的 `s8_state_endpoint` 翻 `true` ——
   「改任一位必须先让对应测试翻转」是该文件 `_note` 写死的纪律；
5. 之后 S8 五行才可从 `draft` 变 `packed`（卡 3.2 §0）。

**翻绿≠探针题可出集**。`s8-rob-02` 还要过 `probe_materiality_verified`（**E9c**）：
本卡落地后才谈得上跑 `slippage_reference_price` 的 materiality screen，
而那把锁今天是**全局一个 bool**，按卡 3.2 §0 的待批项要先改成逐字段。
**两把锁是串的，不要合并成一把。**

---

## 7. 已知边界

1. **POST body 的重复键没有中间件兜底**：`SCALAR_PARAMS` 的去歧义只作用于 query string（`gateway/app.py`），
   `/sim/order`、`/sim/cancel`、`/sim/advance` 的 JSON body 要在 router 里自己顶回去。
   **漏了的失败形态是静默择一** —— 与那个已经修过的 `as_of` 重复参数漏洞同形。
2. **`partial` 是死状态**：`LEGAL_TRANSITIONS` 里有它、v1 不产生它。
   因此**卡 2.3 里与 `partial` 相关的迁移分支在 v1 没有任何正样例覆盖**，
   它的正确性要等 v2；在此之前不许有人把它当「已验证」。
3. **单进程假设**：`access_log` 的写锁是 `threading.Lock()`，注释写明「单进程 uvicorn 够用；
   将来上多 worker 要换」。模拟盘的状态同样是进程内的 —— **上多 worker 之前，`/sim/*` 必须单进程**，
   否则同一个 task 的状态会分裂到两个 worker，而两边都自洽。
4. **ε 带没有 S8 的指标**：`slippage_bps` / `fill_rate` 不在 `epsilon_dual_*.json` 的 9 个回测指标里，
   S8 探针题现在是 `tolerance.kind=exact`。screen 能不能用 `exact` 判 S8，见 §8-3。
5. **本卡不解决 gold**：S8 没有 gold 产物，O1 的「与 gold 比对落 τ/ε 带」在 S8 上目前是 `validate_only`。

---

## 8. 待批事项

| # | 事项 | 为什么要签字 |
| --- | --- | --- |
| 1 | `Reason` 新增 `OPERATION_NOT_PERMITTED` | 该枚举的值会**原样落进 `access_log` 的 `reason`**，卡 5.1 的探针按 reason 结算 —— 加一个值等于改结算口径的输入空间 |
| 2 | `asof.py` 的「运行内上界」改动 | 它是**全网关唯一的一份 as_of 判定**，改它会同时影响 S1–S7 的所有取数。要么加参数只对带 sim 上下文的运行生效，要么全局加一层 —— **二选一要签字**，不许实现者自己挑 |
| 3 | S8 用 `exact` 当 materiality 判据是否成立 | 三个基准价取值给出的 `slippage_bps` 必然不逐位相同，`exact` 下**必判 material** —— 那这条 screen 就是走过场。要么给 S8 标一条带，要么明确接受「S8 的 material 判据是 exact」并写清它证明了什么 |
| 4 | 单进程约束要不要写进 compose lint | §7-3。卡 4.1 §5 已有九条 lint；多 worker 是**部署期**才会踩的坑，写进 lint 才拦得住 |
