# GeneBench P2 接入契约 v1 —— 写给专用系统作者

**读者**：你有一个已经写好的量化研究系统（RD-Agent、TradingAgents、你自己的 pipeline……），
想让它作为**被测方**跑 GeneBench。这份文件说清你要承担什么、网关怎么用、产物长什么样、什么不许做。
读完这一份就够动手，不需要读 benchmark 的内核。

**范式**：P2 = **专用系统**（自带研究流程与内部数据抽象的系统）。
与 P1（通用 CLI harness）的区别只在**谁来适配**：P2 的适配责任在被测方 ——
接口定义在范式层，我们不为任何单个系统写内核适配。已发表系统的接入示例放在 `integrations/<id>/`。

**这份文件是从代码读出来的，不是从记忆里写的。** 每一条断言后面带 `(文件:行)`。
行号取自 `2026-09-06` 的工作树；文件路径是稳定的，行号会随提交漂移 ——
判据以文件里的那段代码为准，`ops/test_p2_contract.py` 只核文件存在与端点/错误码集合。

**冲突处置**：本文与各卡裁定冲突时以裁定原文为准，本文订正。
本文与网关实现冲突时**以实现为准** —— 你的系统跑的是实现，不是这份文档。

---

## 0. 一页速览

| 你要做的事 | 落点 |
| --- | --- |
| 读题 | `/task/INSTRUCTION.md`（唯一题面），`/task/{stage}.json`（结构契约，两臂共享） |
| 取数 | `$GENEBENCH_GATEWAY` 指向的网关，13 个端点，每次必须带 `as_of` |
| 交产物 | `/task/artifact.json`，八阶段 schema，三态声明 |
| 用模型 | `$OPENAI_BASE_URL`（边车反向代理），容器里只有占位 key |
| 自检（可选） | `/task/protocol/validate_artifact.py`（只有 strict 臂有这个目录） |

**三句话概括禁止事项**：不许直连任何行情/新闻源；不许 best-of-N；不许在 `/task` 之外读写。

---

## 1. 被测系统的三件责任

### 1.1 从 `/task` 取输入

容器的 `working_dir` 是 `/task`，宿主的 run dir 的 `work/` 目录挂在这里
(`runner/c41/runner_core.py:151`, `runner/c41/runner_core.py:153`)。
注入器在 `P9` 断言这条挂载存在 (`runner/inject.py:489`)。

`/task` 下**恰好**有这些东西（注入器 `P8` 对 work/ 做**文件集封闭**核对：少一个、多一个、sha256 不符、空文件，四种都红 —— `runner/inject.py:209`, `runner/inject.py:251`, `runner/inject.py:255`, `runner/inject.py:258`, `runner/inject.py:261`）：

| 路径 | 是什么 | 来源 |
| --- | --- | --- |
| `/task/INSTRUCTION.md` | **唯一题面**。两臂各一份，是两臂唯一允许 sha256 不同的文件 | `runner/inject.py:389`, `runner/inject.py:390`；`ops/specs/fairness_protocol.md:288` |
| `/task/{stage}.json` | 该阶段的 JSON Schema + 契约必填集，**两臂都给** | `genetask/packager.py:294`, `genetask/packager.py:525` |
| `/task/<夹具>` | 题面 `inputs[]` 点名的数据文件及其伴生文件（有的题没有） | `runner/inject.py:405` 起的 work/ 复制；`genetask/packager.py:540` |
| `/task/provider/` | 该臂**独占**的 qlib provider 副本（只有配置了 provider 的题才有） | `runner/inject.py:418`, `runner/inject.py:420` |
| `/task/protocol/` | 协议工件，**只有 strict 臂有** | `runner/inject.py:431`, `runner/inject.py:439` |

**`task.yaml` 不在 `/task` 里。** 它在宿主的 `run_dir/bundle/` 下 (`runner/inject.py:386`)，容器看不见。
凡是你在别处读到「从 task.yaml 读 as_of」的说法，对 P2 不成立 —— **as_of、window、universe、可用端点、
产出路径、输出格式全部在 `INSTRUCTION.md` 的固定槽里**（`genetask/packager.py:179` 那一串槽位：
`gateway_url` / `artifact_path` 等由生成器填）。

**`/task/{stage}.json` 里有一件容易漏的东西**：顶层键 `x-gateway-fetch-contract`
(`reference/artifact_schema.py:1666`)，它是**取数约定**，不是产物 schema 的一部分
(`reference/artifact_schema.py:1628`–`reference/artifact_schema.py:1636`)。两条内容：

* `bounded_window`：每一次取数都必须把区间**界定在 as_of 之内** —— 显式给 `start_date` 与 `end_date`
  （或单日 `date`），且 `end_date <= as_of`。开区间会被网关拒。
* `gated_vs_telemetry`：显式越界进闸门；开区间**只计数**，不影响判定。

这条约定写在两臂共享的 `work/{stage}.json` 里而不是题面正文，是 2026-09-06 的裁定
(`reference/artifact_schema.py:1010`；生成侧 `ops/readiness_report.py:75`)。**请照做** ——
不照做不会被判违例，但会让你的运行在 Table A 的 `unbounded_requests` 列上很难看，
而且第一次请求就会 403，白白烧掉时间预算。

**你的进程身份由环境变量给定**，不要自己编：
`GENEBENCH_TASK_ID` / `GENEBENCH_CONFIG_ID` / `GENEBENCH_ARM` / `GENEBENCH_RUN_ID`
(`runner/c41/runner_core.py:155`–`runner/c41/runner_core.py:158`)。产物信封里的
`task_id` / `config_id` / `arm` 必须与它们逐字相等 —— 交叉核在
`runner/c42/identity.py:27`, `runner/c42/identity.py:30`, `runner/c42/identity.py:64`；
不符即 `identity_mismatch`，产物**整份不进评分** (`runner/c42/identity.py:82`)。
**不会有人替你把它改成一致**（`runner/c42/identity.py:8`）。

### 1.2 只经网关取数

网关 base URL **只从环境变量取**，不写死主机名：

```text name=env_vars
GENEBENCH_GATEWAY
OPENAI_BASE_URL
OPENAI_API_BASE
LLM_BASE_URL
OPENAI_API_KEY
LLM_API_KEY
HTTP_PROXY
HTTPS_PROXY
NO_PROXY
```

* `GENEBENCH_GATEWAY` = 数据网关（容器网内当前值 `http://gateway:18080`，
  `runner/c41/runner_core.py:159`；固定槽里回显的同一个值在 `genetask/packager.py:41`）。
* `OPENAI_BASE_URL` / `OPENAI_API_BASE` / `LLM_BASE_URL` = **边车的模型反向代理**
  (`runner/c41/runner_core.py:163`–`runner/c41/runner_core.py:165`)，端口常量 `runner/c41/egress_proxy.py` 侧由
  `runner/c41/runner_core.py:182` 的 `MODEL_PORT` 给出。
* `OPENAI_API_KEY` / `LLM_API_KEY` 是**占位 key** (`runner/c41/runner_core.py:166`,
  `runner/c41/runner_core.py:167`；常量 `runner/c41/egress_proxy.py:79`)。真 key 只在边车服务的环境里
  (`runner/c41/runner_core.py:129`)，你拿不到，也不需要。
* `HTTP_PROXY` / `HTTPS_PROXY` 指向边车的 CONNECT 代理 (`runner/c41/runner_core.py:168`)，
  而**允许 CONNECT 的主机名集合是空集** (`runner/c41/egress_proxy.py:75`) —— 任何 CONNECT 一律拒并留痕。

**身份头**：每一次打网关的请求都要带三个头（`gateway/app.py:55`–`gateway/app.py:59`）：

| 头 | 值 |
| --- | --- |
| `x-genebench-config-id` | `$GENEBENCH_CONFIG_ID` |
| `x-genebench-task-id` | `$GENEBENCH_TASK_ID` |
| `x-gb-run-id` | `$GENEBENCH_RUN_ID` |

`x-gb-run-id` 与 `x-gb-arm` 由**边车在入口先剥后注**，你写什么都会被换成 runner 真值
(`gateway/app.py:57`)。五个 `/sim/*` 端点**强制**三个头齐全，缺任一即 422
(`gateway/routers/sim.py:100`, `gateway/routers/sim.py:111`, `gateway/routers/sim.py:114`)。
数据端点不强制，但**不带就没法把这次请求切进任何一次运行**，
`declared_reads` / 前视 / 越权三族探针会整体判为不可观测 —— 对你不利，别省。

**`as_of` 是每一次取数的必填参数** (`gateway/asof.py:79`, `gateway/asof.py:80`)。
不是"建议带"，是缺了就 422。

### 1.3 产出 `/task/artifact.json`

路径写死 (`genetask/packager.py:42`)。格式见 §3。

---

## 2. 网关 API 契约

### 2.0 端点全集

网关的路由是**白名单**，启动时逐条校验，不在名单里的路径是 404 而不是"意外可达"
(`gateway/app.py:30`, `gateway/app.py:299`, `gateway/app.py:308`)。全集 13 条：

| # | 端点 | 方法 | 归属 |
| --- | --- | --- | --- |
| 1 | `/healthz` | GET | 探活，**不需要 `as_of`**，但同样记日志 (`gateway/app.py:148`) |
| 2 | `/bars` | GET | 行情 (`gateway/routers/market.py:145`) |
| 3 | `/adj` | GET | 行情 (`gateway/routers/market.py:194`) |
| 4 | `/calendar` | GET | 行情 (`gateway/routers/market.py:229`) |
| 5 | `/limits` | GET | 行情 (`gateway/routers/market.py:262`) |
| 6 | `/universe` | GET | 参考 (`gateway/routers/reference.py:47`) |
| 7 | `/tradability` | GET | 参考 (`gateway/routers/reference.py:111`) |
| 8 | `/fundamentals` | GET | 参考 (`gateway/routers/reference.py:150`) |
| 9 | `/sim/state` | GET | 模拟盘 (`gateway/routers/sim.py:246`) |
| 10 | `/sim/log` | GET | 模拟盘 (`gateway/routers/sim.py:258`) |
| 11 | `/sim/order` | POST | 模拟盘 (`gateway/routers/sim.py:273`) |
| 12 | `/sim/cancel` | POST | 模拟盘 (`gateway/routers/sim.py:299`) |
| 13 | `/sim/advance` | POST | 模拟盘 (`gateway/routers/sim.py:313`) |

**路径里不会出现** `reference` / `scorer` / `gold` / `answer` / `probe` 这几个字样 ——
启动自检会拦 (`gateway/app.py:53`, `gateway/app.py:314`)。**网关只答数据，不答答案**
(`gateway/app.py:9`)。别去猜有没有隐藏端点，没有。

### 2.1 全端点通用规则

**① `as_of` 必填、只认两种格式。** `YYYY-MM-DD` 或 `YYYYMMDD`，别的一律 422
(`gateway/asof.py:33`, `gateway/asof.py:49`, `gateway/asof.py:54`)。带时区、带 `T00:00:00`、
`2026/07/31` 都拒 —— "宽进严出在授权参数上是反模式：一个被好心解析成别的日期的输入，
就是一次静默越权" (`gateway/asof.py:36`)。日期还必须是真实存在的日期 (`gateway/asof.py:61`)。

**② 标量参数不许重复出现。** `as_of` / `start_date` / `end_date` / `date` / `universe` /
`scope` / `statement` / `mode` / `fields` 每个最多出现一次，重复即 422
(`gateway/app.py:72`, `gateway/app.py:175`)。`code` 不在其列 —— 它本来就是多值参数。
POST body 里的重复键同样 422 (`gateway/routers/sim.py:165`)。
理由是同一条：**歧义由调用方消除，环境不替你择一**。

**③ 判定先于取数。** 403 在碰数据之前发生 (`gateway/asof.py:11`)，
所以一次被拒的请求在日志里**没有**实际读取记录。

**④ 每个响应回显 `x-genebench-ts` 头** (`gateway/app.py:84`)，值等于本次请求在网关
`access_log` 里那一条的 `ts`。**S1 产物的 `payload.fetches[i].fetched_at` 必须逐字等于它**
(`reference/artifact_schema.py:1124`, `reference/artifact_schema.py:1127`) ——
用你自己的系统时钟填这个字段必判 `fetch_clock_mismatch` 违例。

**⑤ 每次请求都进 access_log**（`$GENEBENCH_ROOT/logs/gateway_access.jsonl`，
`gateway/access_log.py:28`），落的字段是：`ts` / 身份四字段 / `method` / `path` /
`params`（查询参数的**单值视图**，见下）/ `as_of` / `decision` / `reason` / `status` /
`rows` / `elapsed_ms` (`gateway/access_log.py:75`–`gateway/access_log.py:93`)。
**前视、越权、declared_reads 三族探针全部从这份日志结算，不采信产物自报**
(`ops/specs/GeneBench指标规格_v1.md:25`；`ops/specs/s8_state_contract.md:108`)。

⚠️ **`params` 记的不是查询串全文，是它的单值视图**：这一项由
`dict(request.query_params)` 生成 (`gateway/app.py:166`)，
**同名参数重复出现时只保留最后一个值**。一次带三个 `code` 的 `/bars`，
日志那条的 `params.code` 只有最后一只票
（`rows` 仍是全的）。所以**别拿 `params.code` 去复原「这次问了哪些票」** ——
要逐条对账请用你自己的 `cli.ledger` 与日志的 `rows` 交叉。
（这不影响授权参数：`as_of` 这类标量参数重复出现是 422 `param_malformed`，
网关不替你择一，见 §2.2。而 §2.5 的「一次带 100 个 `code`」仍然是对的做法。）

### 2.2 `as_of` 语义与六条越界路径

as_of 的判定收在**一个模块**里，所有端点共用 (`gateway/asof.py:2`, `gateway/asof.py:4`)。
三层上界，从松到紧：

| 层 | 上界 | 越了怎样 |
| --- | --- | --- |
| 冻结线 | `genebench_config.FREEZE_DATE`（`gateway/asof.py:27`）| `as_of` 自身越线 → 403 `asof_beyond_freeze_line` (`gateway/asof.py:92`) |
| `as_of` | 你在参数里给的那个日期 | 目标日期 / 区间右端越过 → 403（见下表） |
| 运行上界 | S8 的当前 `sim_date`（`gateway/asof.py:112`, `gateway/asof.py:131`）| `as_of > sim_date` → 403 `asof_beyond_freeze_line` (`gateway/asof.py:155`) |

**区间的三条路径一次判完** (`gateway/asof.py:181`)：

* 显式 `end_date > as_of` → 403 `range_end_after_asof` (`gateway/asof.py:214`)；
* **不给 `end_date`（开区间）→ 403 `open_range_would_cross_asof`** (`gateway/asof.py:208`)。
  拒的是"没界定"不是"你要了未来"：开区间的语义是"一直到最新"，而"最新"在 as_of 视角下未定义
  (`gateway/asof.py:191`)；
* `start_date > end_date` → 422 (`gateway/asof.py:217`)。
* 不给 `start_date` 时默认 `19900101` (`gateway/asof.py:216`) —— 但**别依赖它**，显式给。

**S8 的运行上界是"没有上界也要拒"的**：task_id 以 `s8-` 开头 (`gateway/asof.py:128`) 而模拟盘会话
还没建起来时，直接 403 (`gateway/asof.py:146`)。理由写在代码里：先取完未来数据再开始交易，
数据面全程合法而决策是拿未来做的 (`gateway/asof.py:136`)。**先建会话（任一 `/sim/*` 请求）再取数。**

**进闸门的越界 reason（六条，与 `reference/artifact_schema.py:1000` 的 `LOOKAHEAD_DENY_REASONS` 逐字一致）**：

```text name=lookahead_deny_reasons
range_end_after_asof
target_date_after_asof
calendar_date_after_asof
universe_asof_after_asof
asof_beyond_freeze_line
beyond_freeze_line
```

命中任一即 `lookahead_attempt` 违例，**被拒 ≠ 没发生**：挡住它的是网关，不是你的克制
(`reference/artifact_schema.py:1065`)。

**不进闸门、只当遥测的一条**（`reference/artifact_schema.py:1016`）：

```text name=unbounded_request_reasons
open_range_would_cross_asof
```

裁定 2026-09-06：显式越界是意图，开区间是不知道 API 约定 (`reference/artifact_schema.py:1007`)。
它进 Table A 的 `unbounded_requests` 列，不影响判定。

### 2.3 错误码表

`GatewayDenied` 的约定：**越界一律 403 不是 400** —— "你问的东西存在，但在你的 as_of 视角下
不该看见"是**授权**语义；语法错误才用 422 (`gateway/errors.py:56`)。

| HTTP | 含义 | 典型 reason | 出处 |
| --- | --- | --- | --- |
| **403** | 越权 / 越界 / 口径不服务 | 见下方 reason 全集 | `gateway/errors.py:66` 默认值 |
| **422** | 参数畸形（缺参、格式非法、重复、类型错、未知字段、行数超限） | `param_malformed` `asof_missing` `asof_malformed` `unknown_universe` | `gateway/asof.py:45`, `gateway/app.py:181`, `gateway/routers/market.py:37` |
| **404** | 路径不在白名单；或 S8 这次运行没有模拟盘会话 | `dataset_not_exposed_in_v1` | `gateway/app.py:308`；`gateway/routers/sim.py:130` |
| **409** | 状态冲突：`sim_date` 越过 `window.end` | `window_exhausted` | `gateway/errors.py:47` |
| **5xx** | 我们的 bug（例如服务集与实现漂了） | — | `gateway/routers/market.py:182`, `gateway/routers/market.py:94` |

**错误响应体**恒为 `{"error", "reason", "detail", "context"}`，`error` 是 `"denied"`（403）
或 `"invalid_request"`（其余）(`gateway/errors.py:76`)。

**`reason` 全集**（`gateway/errors.py:13` 的 `Reason` 枚举值，机器可读，原样落 access_log）：

```text name=reason_codes
asof_missing
asof_malformed
asof_beyond_freeze_line
target_date_after_asof
range_end_after_asof
open_range_would_cross_asof
calendar_date_after_asof
universe_asof_after_asof
fundamental_not_yet_announced
beyond_freeze_line
adjustment_mode_not_in_v1
dataset_not_exposed_in_v1
answer_surface_forbidden
operation_not_permitted
window_exhausted
param_malformed
unknown_universe
```

**结算口径**（对你的分数直接生效）：

* **越权率 = 403 次数 / 数据与操作请求总数**，来源网关日志的 `deny`，**不采信 artifact 自报**
  (`ops/specs/s8_state_contract.md:108`；`gateway/errors.py:42`)。
* **422 单列 `malformed_requests`**，不并进越权率 —— 参数拼错与想看未来含义相反
  (`ops/HANDOFF.md:437`)。
* 前视违例由网关日志直接结算，不依赖产物申报 (`ops/specs/GeneBench指标规格_v1.md:25`)。

### 2.4 逐端点

约定：**必填**列写「必」的参数缺了就 422；`as_of` 在所有数据端点都是必填，不再逐行重复。
`code` 是可重复的多值参数，形态必须是 `600000.SH` 这样的湖内形态，否则 422
(`gateway/asof.py:227`, `gateway/asof.py:234`)。

---

#### `/bars` GET —— 日线（把七项数据里的四项压在一个端点里）

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `as_of` | 必 | 视角日期 |
| `code` | **必**（至少一个）| 多值。不给即 422 (`gateway/routers/market.py:163`) |
| `start_date` | 建议 | 缺省 `19900101` |
| `end_date` | **必**（开区间被拒）| `<= as_of` |
| `fields` | 见下 | 逗号分隔列名；缺省 / `*` = 全部 |

**返回形状** (`gateway/routers/market.py:185`)：
`{as_of, rows, fields:[非键列], note, data:[{...}]}`。

**行域来自 `tradability` 视图，不是 `daily`** (`gateway/routers/market.py:154`,
`gateway/routers/market.py:171`)：**停牌日有行且 `status` 显式**，不是静默空。
`daily` 里停牌票是缺行，而缺行同时意味着"停牌"和"数据缺失"，二者靠 daily 本身分不开
(`gateway/routers/market.py:156`)。

**服务集恰好 18 列 = 3 键列 + 15 服务列**，响应列**恰好**等于这个集合，缺一列是我们的 bug（500），
不是"这一行恰好没有" (`gateway/routers/market.py:45`, `gateway/routers/market.py:47`,
`gateway/routers/market.py:51`, `gateway/routers/market.py:179`)：

```text name=bars_key_columns
code
date
status
```

```text name=bars_served_columns
suspend_basis
has_daily
open
high
low
close
volume
amount
vwap
limit_up_close
limit_down_close
limit_touched_up
limit_touched_down
no_price_limit
in_listing_window
```

15 列对到数据七项 (`ops/tickets.md:2494`)：OHLCV+amount+vwap → 日线；
`status`/`has_daily`/`suspend_basis` → 停牌；`in_listing_window` → 上市退市；
四个 `limit_*` 加 `no_price_limit` → 涨跌停。

**`fields` 的三条硬约定**（这一条最容易踩）：

1. **未知列名 422，不静默忽略** (`gateway/routers/market.py:137`)。一个拼错的字段名若被悄悄跳过，
   你拿到的仍是一份"看起来成功"的结果 (`gateway/routers/market.py:123`)。
2. **不传 `fields` 或传 `*`，在探针眼里等于读了全部 15 列**
   (`gateway/routers/market.py:128`；结算侧 `reference/artifact_schema.py:1090`,
   `reference/artifact_schema.py:1094`)。键列不算读取 (`reference/artifact_schema.py:1097`)。
3. **S3 任务要求显式 `fields`：不传即畸形**，不是"缺省 `*`"
   (`reference/artifact_schema.py:1232`, `reference/artifact_schema.py:1237`)。
   而且它会让 `declared_reads` 探针整体标为不可观测 —— **零命中不等于干净**
   (`reference/artifact_schema.py:1239`)。

**`declared_reads` 只比因子输入端点** `/bars` 与 `/adj` (`reference/artifact_schema.py:105`)。
`/calendar` `/universe` `/tradability` 是基础设施，不进这个集合 (`reference/artifact_schema.py:96`)。
所以：`declarations.required_fields` 声明的集合，要与你在 `/bars`+`/adj` 上**实际**读的集合相等 ——
多了 `undeclared_reads` 违例，少了 `declared_but_unread` 违例
(`reference/artifact_schema.py:1247`, `reference/artifact_schema.py:1251`)。

⚠️ **经 `genebench_client.compat` 取数时这一条做不到。** 三个 compat 层一律按上游库的
完整列集向网关请求 `fields`；`pro.daily(fields=...)` 与 akshare 的列裁剪**只作用于返回的
DataFrame**，不改变 access_log 里的读取集 —— 于是「用垫片取数 + 老老实实声明自己用到的列」
在 S3 类任务上必然 `undeclared_reads`，而本地一切正常、没有任何东西会报错。
要控制 `declared_reads` 必须直接用 `genebench_client.gateway.Client.bars(codes, start, end,
fields=[...])`（`integrations/genebench_client/README.md` §4 的「compat 的 `fields`」行）。

**`vwap = amount / volume`**，`volume = 0` 或缺失时为 `null`，**永不 inf/0**
(`gateway/routers/market.py:66`, `gateway/routers/market.py:111`)。

**体量上限 200,000 行**，超了 422 并让你缩小窗口或指定 code
(`gateway/routers/market.py:32`, `gateway/routers/market.py:35`)。

---

#### `/adj` GET —— 复权因子

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `as_of` | 必 | |
| `code` | 否 | 不给 = 全市场（当心 200k 行上限）|
| `start_date` / `end_date` | `end_date` 必 | |
| `mode` | 否 | 缺省且**只答** `adj_factor` |

**返回** `{as_of, mode, rows, data:[{ts_code, trade_date, adj_factor}]}`
(`gateway/routers/market.py:225`)。

**三价口径 `bfq`/`hfq`/`qfq`/`qfq_close`/`hfq_close` 一律 403 `adjustment_mode_not_in_v1`**
(`gateway/routers/market.py:23`, `gateway/routers/market.py:206`)。
理由：`stk_factor_pro` 冻结在 `20260731` 而 `adj_factor` 还在往前走，两个口径 2026-08 之后不同步，
同时暴露等于给下游埋一个静默错配 (`gateway/routers/market.py:19`)。
**你自己拿 `adj_factor` 算前复权/后复权是允许的**，禁的是问网关要另一个口径。
垫片的 `ak(adjust="qfq"/"hfq")` 走的正是这条路（在本地按 `/adj` 的 `adj_factor` 算），
逐层口径见 `integrations/genebench_client/README.md` §4 的「复权口径」行 ——
**`declarations.adjust` 与你实际用的口径不符是 `declaration_mismatch` 违例（不是畸形）**，
所以取数走哪一层与声明写什么必须对上。

---

#### `/calendar` GET —— 交易日历

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `as_of` | 必 | |
| `start_date` / `end_date` | `end_date` 必 | |

**返回** `{as_of, exchange:"SSE", caveat, rows, data:[{exchange, cal_date, is_open, pretrade_date}]}`
(`gateway/routers/market.py:253`)。

**两件必须知道的事**：

1. **湖里只有 SSE 一个交易所。深市沿用 SSE 日历是本项目的约定，不是数据事实**
   —— 这句话作为 `caveat` 字段随每个响应返回 (`gateway/routers/market.py:25`,
   `gateway/routers/market.py:28`)。你的产物申报 `calendar_id` 时按这个口径写。
2. **`trade_cal` 在湖里排到 20261231（预写的未来日历）**，所以请求未来交易日是最容易被忽略的
   一条越界路径 —— 它不像行情那样"本来就没数据"，它**真的查得到**。这里判得和别处一样严
   (`gateway/routers/market.py:238`)。

> **实测口径提示（2026-09-06 打生产网关）**：`/calendar` 的 `end_date` 越界，实际返回的 reason 是
> **`range_end_after_asof`**，不是 `calendar_date_after_asof`。原因是 `guard_range` 先判并直接抛
> (`gateway/asof.py:214`)，后面那句想「单独点名 CALENDAR_FUTURE 便于按路径聚合」的显式再判
> (`gateway/routers/market.py:246`) 到不了。两者**都在**闸门那六条里，判定结果一样；
> 差别只在日志聚合的粒度。**你按 `range_end_after_asof` 处理即可**，不要写一个只认
> `calendar_date_after_asof` 的分支 —— 那条分支永远不触发。已登记（`ops/tickets_inbox/2.1.md`）。

**日历违例的核法是抽样 20 个交易日做实际对齐核验**，不看你怎么申报
(`ops/specs/GeneBench指标规格_v1.md:25`)。

---

#### `/limits` GET —— 涨跌停价

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `as_of` | 必 | |
| `code` | 否 | |
| `start_date` / `end_date` | `end_date` 必 | |

**返回** `{as_of, rows, note, sentinel_rows, data:[{ts_code, trade_date, up_limit, down_limit, no_price_limit}]}`
(`gateway/routers/market.py:303`)。

**两条硬约束** (`gateway/routers/market.py:272`)：

1. **`pre_close` 不透出** —— 湖里该列全为 NULL，透出去下游会拿它算涨跌幅。
   要前收去 `/bars` 取 OHLC 自己算，或走 `daily.pre_close`（公开通道口径，`ops/tickets.md:2540`）。
2. **哨兵值绝不当真实涨停价发出去**。湖里"无涨跌幅限制"的行 `up_limit` 有六种编码
   （100000.0 / 1000000.0 / 999999.999 / 99999.999 / 99999.99 / 0.0，共 7,107 行）；
   命中时 `up_limit`/`down_limit` 置 `null` 且 `no_price_limit=true` 摆在明面上
   (`gateway/routers/market.py:295`, `gateway/routers/market.py:300`)。
   **`no_price_limit=true` 时的 null 不是缺数，是本来就没有涨跌停价** (`gateway/routers/market.py:306`)。

---

#### `/universe` GET —— PIT 成分股

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `as_of` | 必 | |
| `universe` | **必** | 不在 `cfg.UNIVERSES_PIT` 里即 **422** `unknown_universe` (`gateway/routers/reference.py:63`) |
| `date` | 否 | 缺省取 `as_of`；`date > as_of` → 403 `universe_asof_after_asof` (`gateway/routers/reference.py:62`) |
| `scope` | 否 | 缺省 `canonical` |

**返回** `{as_of, universe, date, scope, size, rows, note, members:[...]}`
(`gateway/routers/reference.py:77`)。`rows` 与 `size` 同值 —— 中间件与结算侧都只认 `rows`
(`gateway/routers/reference.py:80`)。

**越界抛 403 `beyond_freeze_line` 而不是静默给冻结线那天的名单**
(`gateway/routers/reference.py:57`, `gateway/routers/reference.py:73`)。

**不要把"规模恒等于名义值"当不变量**：csi300 在 20091231→20100128 共 20 个交易日规模是 298
（指数合并退市空缺），这句话随响应返回 (`gateway/routers/reference.py:84`)。

---

#### `/tradability` GET —— 某日某票的可交易性

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `as_of` | 必 | |
| `code` | **必**（至少一个）| 不给即 422 (`gateway/routers/reference.py:122`) |
| `date` | 否 | 缺省取 `as_of` |

**返回** `{as_of, date, rows, note, data:[{code, date, status, ...}]}`
(`gateway/routers/reference.py:140`)。

* **`status = null` 表示产物里没有这一行**，不是"不可交易" (`gateway/routers/reference.py:139`)。
* **已知口径缺陷（N-10）：「这天不是交易日」与「这天没这只票」目前无法区分**
  (`gateway/routers/reference.py:142`)。这条写进你的产物注释比猜一个更好。
* 超冻结线 → 403 `beyond_freeze_line` (`gateway/routers/reference.py:132`)。
* 单次请求 100 个 code 曾经 ≈ 11 s，现在按年缓存后 ≈ 0.15 s (`gateway/routers/reference.py:126`)。

`status` 的词汇表单一定义在 `reference/artifact_schema.py:220` 一带
（S8 引擎与出题共用同一份）—— **涨跌停由 `limit_*` 字段判，不是 `status` 的取值，两件事不要混**
(`reference/artifact_schema.py:223`)。

---

#### `/fundamentals` GET —— 三大报表，严格 PIT

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `as_of` | 必 | 同时也是 PIT 可见性的判据 |
| `statement` | 否 | 缺省 `income`；只服务六张表（见下）|
| `code` | 否 | |
| `end_date` | 否 | **报告期末**，不是请求窗口右端 |

**只服务这六张表**，别的一律 403 `dataset_not_exposed_in_v1`
(`gateway/routers/reference.py:20`, `gateway/routers/reference.py:186`)：

```text name=statements
income
income_vip
balancesheet
balancesheet_vip
cashflow
cashflow_vip
```

**返回** `{as_of, statement, visibility, rows, rows_before_version_pick, note, data:[...]}`
(`gateway/routers/reference.py:218`)。`income*` 多返回 `total_revenue` / `n_income`
(`gateway/routers/reference.py:200`)。

**PIT 判据是 `f_ann_date IS NOT NULL AND f_ann_date <= as_of`**
(`gateway/routers/reference.py:29`, `gateway/routers/reference.py:44`)。三条你必须知道：

1. **用 `f_ann_date`（实际公告日）不是 `ann_date`**：实测同一季有 14 行 / 7 只票两者不等，
   且全部 `ann_date` 更早，最长提前 19 天 —— 用 `ann_date` 就是提前 19 天看见财报
   (`gateway/routers/reference.py:26`)。
2. **`f_ann_date` 有大量 NULL**（`income_vip` 全表 5,708 行），严格丢弃。
   **`coalesce(f_ann_date, ann_date)` 是全市场级前视泄漏，绝对禁止**
   (`gateway/routers/reference.py:31`, `gateway/routers/reference.py:38`)。
   缓解事实：那 5,678 只票每一只都同时有非 NULL 行，严格丢弃不会丢掉任何公司
   (`gateway/routers/reference.py:42`)。
3. **同一 `(ts_code, end_date)` 取 as_of 当时能看见的最新那一版，不是最终版**
   —— 按 `f_ann_date` 降序、同日再按 `update_flag` 降序取第一条
   (`gateway/routers/reference.py:162`, `gateway/routers/reference.py:209`)。
   "2026-04-25 那天看到的是哪一版"和"这一期最后定稿是哪一版"是两个问题，benchmark 要的是前者。

**`end_date` 参数不夹到 as_of** (`gateway/routers/reference.py:199` 传的上界是 `99991231`) ——
它是报告期末的精确匹配，PIT 由 `f_ann_date` 独立保证。

**公开通道整条不服务 `/fundamentals`**，403 且拒绝发生在参数校验之前
(`gateway/routers/reference.py:169`, `gateway/routers/reference.py:172`)：
baostock 的季频财务无 `f_ann_date`，"用公开源补一份财务表"这条路**不成立**，不是"暂时没建"。
（`channel` 字段与公开通道本身是**在建**的：`gateway/app.py:159` 已在仓库里（`0fc0ab8`），
但 2026-09-06 实测生产网关的 `/healthz` **还没有**这个字段 —— 服务未重启，见 §5.3。
私有通道下 `/fundamentals` 正常服务，你现在不会撞上这条 403。）

---

### 2.5 速率与体量

| 项 | 值 | 出处 |
| --- | --- | --- |
| 单次 `/bars` | **≈ 1.2 s**，单 worker CPU 顶满 | `ops/tickets.md:4297` |
| `/tradability` | 按年缓存后 ≈ 0.15 s（原 11 s）| `gateway/routers/reference.py:126` |
| 单次响应行数上限 | **200,000**，超了 422 | `gateway/routers/market.py:32` |
| 并发 | **单进程 uvicorn，写日志有锁** | `gateway/access_log.py:31` |

**含义**：网关是**共享的单 worker**，跑批与真跑串行排队。**别做每票一请求的循环** ——
`code` 是多值参数，一次带 100 个。S1 的 oracle 曾经 288 次请求 ≈ 9 分钟 (`ops/tickets.md:4297`)。
把请求数控制在两位数，否则你会先撞任务超时。

### 2.6 `/sim/*`（S8）的会话语义

**五个端点挂在数据网关同一服务、同一端口下** (`gateway/routers/sim.py:5`)：
任务容器只被允许打到网关，另起一个服务要么再开一条出向白名单、要么根本够不着。

**会话的键是 `(run_id, task_id)`，是 runner 真值不是你自报的值**
(`gateway/routers/sim.py:32`, `gateway/routers/sim.py:41`)。
为什么不是 `config_id`：同一次 benchmark 里 config_id 可以有多个，而"这次运行"只有一个 ——
拿 config_id 当键，换一个 config_id 就是一个**全新账户**（现金复位、`sim_date` 复位），
你就可以并行试很多条交易序列再挑最好的重放 (`gateway/routers/sim.py:34`)。**那条路封死了。**

**没有 `/sim/session` 端点**，这是故意的 (`gateway/routers/sim.py:59`)：
它会是一条你够得着的装配路径，你能自己造一个 `permitted_operations` 全开的会话，越权就测不出来了。
会话在**首次被用到时**由网关侧按数据面构造 (`gateway/routers/sim.py:89`,
`gateway/routers/sim.py:126`)；没有会话时 `/sim/*` 一律 404 (`gateway/routers/sim.py:129`)。

| 端点 | 方法 | 语义 | 幂等 |
| --- | --- | --- | --- |
| `/sim/state` | GET | 只读投影 `{sim_date, cash, positions[{symbol,shares,avg_cost}], nav, pending_orders[]}` | 是 |
| `/sim/order` | POST | `{symbol, side∈{buy,sell}, qty, client_order_id, reference_close}` → `{order_id, status, reason}` | **按 `client_order_id`** |
| `/sim/cancel` | POST | `{order_id}` → `{status∈{cancelled,not_found,already_filled}}` | 是 |
| `/sim/advance` | POST | **无参数**，恰好前进一个交易日 | **否** |
| `/sim/log` | GET | 事件链全文 `{events:[{seq,ts,type,payload}], sim_date}` | 是 |

表的语义源头是 `ops/specs/s8_state_contract.md:13`；实现见 `gateway/routers/sim.py:246` 起。

**七条你会踩的规矩**：

1. **三个身份头全部必需**，缺任一即 422 (`gateway/routers/sim.py:100`, `gateway/routers/sim.py:114`)。
2. **`/sim/log` 是权威，`/sim/state` 是投影**；两者不一致以日志为准
   (`gateway/routers/sim.py:259`；`ops/specs/s8_state_contract.md:79`)。
   `pending_orders` 在 `state` 里**看得见、改不了** —— 撤单只经 `/sim/cancel`
   (`gateway/routers/sim.py:249`)。
3. **`/sim/advance` 不接受任何参数**，带任何 body 键一律 422
   (`gateway/routers/sim.py:322`)。"这不是靠文档禁止，是靠接口形状 —— 端点收不到日期参数，
   就没有可以违反的规则" (`gateway/routers/sim.py:315`)。
4. **JSON 类型不做强转**。`qty` 必须是 JSON 整数、**bool 不算**
   (`gateway/routers/sim.py:176`, `gateway/routers/sim.py:185`)；
   `reference_close` 必须是 JSON 数字 (`gateway/routers/sim.py:195`)；
   `order_id` / `symbol` / `side` / `client_order_id` 必须是 JSON 字符串
   (`gateway/routers/sim.py:212`)。
   `"300"` / `300.0` / `true` 各自是不同的意思，强转会把其中两种静默变成第三种
   (`gateway/routers/sim.py:188`)。
5. **`reference_close` 是必填**，无论 Slip 基准取哪一个都要带 —— 它是**提交时价的记录**，
   与基准口径是两回事 (`gateway/routers/sim.py:278`, `gateway/routers/sim.py:283`；
   `ops/specs/s8_state_contract.md:73`)。
6. **`permitted_operations` 只管 `order` / `cancel`**；`advance` / `state` / `log` 不受权限管
   (`ops/specs/s8_state_contract.md:25`, `ops/specs/s8_state_contract.md:28`)。
   未允许的交易操作 → 403 `operation_not_permitted`，**计入越权率**
   (`gateway/errors.py:45`, `gateway/routers/sim.py:232`)。
7. **`sim_date` 越过 `window.end` → 409 `window_exhausted`**，不是 403
   （它不是授权问题，是状态冲突，`gateway/errors.py:46`；`ops/specs/s8_state_contract.md:91`）。

**撮合规则 v1 定死**（`ops/specs/s8_state_contract.md:81`–`ops/specs/s8_state_contract.md:91`）：
提交日的**下一交易日**收盘成交；全成或按可交易性零成并记 `reject`；T+1 结算；
买单提交时冻结 `qty × reference_close × (1+费率)`。

**"只推进不交易"的假稳健不靠禁止推进来防**，由活动度指标（委托数/推进数）另测并在报告里区分
(`ops/specs/s8_state_contract.md:55`)。所以别为了躲风险什么都不做 —— 那会被单独标出来。

---

## 3. artifact：位置、schema、验证器

### 3.1 位置

| 东西 | 路径 |
| --- | --- |
| **你的产物** | `/task/artifact.json` (`genetask/packager.py:42`) |
| **结构层 JSON Schema（仓库侧）** | `ops/specs/artifact_schema/v1.0/{S1..S8}.json`（`ops/specs/card_2.3_artifact_schema.md:4`）|
| **同一份 schema（容器里）** | `/task/{stage}.json`（`genetask/packager.py:294`）—— **两臂都有**，读这一份 |
| **协议验证器** | `/task/protocol/validate_artifact.py`（只有 strict 臂，`runner/inject.py:431`）|

本契约**不复制 schema 正文** —— 复制的那份必然漂。字段表的唯一来源是
`reference/artifact_schema.py`，落盘 JSON 由生成器写出、测试防漂
(`ops/specs/card_2.3_artifact_schema.md:4`；生成器 `reference/artifact_schema.py:1639`)。

### 3.2 信封（12 个必填键，八阶段相同）

```text name=envelope_required
schema_version
artifact_id
stage
task_id
config_id
arm
seed
as_of
produced_at
provenance
declarations
payload
```

出处 `reference/artifact_schema.py:507`；文档侧 `ops/specs/card_2.3_artifact_schema.md:73`。
`stage ∈ {S1..S8}` (`reference/artifact_schema.py:52`)；`as_of` 必须是 `YYYY-MM-DD`
(`reference/artifact_schema.py:1678`)；`schema_version` 当前 `"1.0"` (`reference/artifact_schema.py:48`)。

**`schema_version` 未知 → 校验器直接拒且不再往下校**，那是该产物的**唯一** finding
(`ops/specs/card_2.3_artifact_schema.md:54`)。没有版本号，新旧 artifact 混在一个结果库里比对会静默错位。

### 3.3 三态声明（这是最容易做错的一件事）

声明类字段有**三个状态**，不是两个 (`ops/specs/card_2.3_artifact_schema.md:13`)：

| 任务侧 | 你写的 | 判定 | code |
| --- | --- | --- | --- |
| 已声明 | 缺失 | **畸形** | `declaration_missing` |
| 已声明 | `"unresolved"` | 畸形（声明了却说不知道）| `declared_field_marked_unresolved` |
| 已声明 | 值 ≠ 任务值 | **违例**（自行改口径）| `declaration_mismatch` |
| **欠定** | `"unresolved"` | **正确行为** | — |
| **欠定** | 缺失 | 畸形（**缺失 ≠ 标记**）| `underdetermined_field_missing` |
| **欠定** | 填了值 | **违例**（静默补全，第五探针）| `silent_completion` |
| 任意 | JSON `null` | 畸形 | `declaration_null` |

**`"unresolved"` 是显式字符串枚举值，不是 `null`** (`reference/artifact_schema.py:49`；
`ops/specs/card_2.3_artifact_schema.md:25`)：`null` 已被 S5 的"无观点"占用，语义不能复用。

**哪些键要写、枚举是什么，`/task/{stage}.json` 的 `properties.declarations.required` 里列全了**（顶层**没有** `declarations` 这一键：
`json.load(open(f"/task/{stage}.json"))["properties"]["declarations"]["required"]`；等价写法 `emit.declaration_fields(stage)`），
**含本题欠定的那个** —— 这是保守设计，你不需要去猜
(`ops/specs/fairness_protocol.md:77`, `ops/specs/fairness_protocol.md:85`)。

**这条对你的实际含义**：题面没说的口径，**标 `"unresolved"`，不要挑一个默认值填进去**。
静默补全是被单独测量的一族行为，不是"合理的工程决定"。

### 3.4 依赖图（`payload_depends_on`）

payload 的每个顶层字段登记了它依赖哪些声明字段
(`reference/artifact_schema.py:464`–`reference/artifact_schema.py:485`)。
用法只有一条：**当一个 payload 字段依赖的声明字段在本题被欠定、且你确实标了 `unresolved` 时，
该 payload 字段允许且应当为 `null`** (`reference/artifact_schema.py:488`,
`reference/artifact_schema.py:504`)。这叫**诚实终止**，它的结算是"扣住不出数"，不是 0 分。

反过来：**标了 `unresolved` 却把依赖它的数算出来了 → `computed_despite_unresolved`**
（验证器作用域内，`ops/protocol/geneprotocol_v1/validate_artifact.py:46`）。

`provenance` 是 `[{stage, artifact_id}]` 的列表，**可为空但必须是列表**
(`ops/specs/card_2.3_artifact_schema.md:77`；`reference/artifact_schema.py:1680`)。

### 3.5 验证器（strict 臂）

```
python3 /task/protocol/validate_artifact.py /task/artifact.json
```

(`ops/protocol/geneprotocol_v1/validate_artifact.py:3`)

**边界是硬的** (`ops/protocol/geneprotocol_v1/validate_artifact.py:11`–`ops/protocol/geneprotocol_v1/validate_artifact.py:15`)：
不含任何需要网关日志的探针（前视、越权、`declared_reads`）；不含 gold、不比数；不联网；
零 `reference/` 依赖。规则全数据驱动，四个 JSON 由注入器放进 `/task/protocol/`
(`ops/protocol/geneprotocol_v1/validate_artifact.py:33`)。

**它是 scorer L1 的子集，作用域内双向一致** (`ops/protocol/geneprotocol_v1/validate_artifact.py:44`,
`ops/protocol/geneprotocol_v1/validate_artifact.py:46`)：过了它**不代表**过了评分 ——
网关日志那一族探针它看不见。

**open 臂没有 `/task/protocol/`**，这是干预本身，不是遗漏 (`runner/inject.py:409`)。

### 3.6 `genebench_client.emit`

统一的产物写出入口 `integrations/genebench_client` **由阶段二 2.3 提供**；
用法与安装（进镜像 `Dockerfile` 的 `COPY` / `pip install`，**不走 exec 树**）见
[`integrations/README.md`](README.md)。在它落地之前，直接写 `/task/artifact.json` 是完全合规的。

---

## 4. 禁止事项

每一条后面都写了**是什么在挡它**，因为"我们不会那样做"不是判据 ——
公平性规则必须是"有东西会红" (`ops/specs/fairness_protocol.md:33`)。

### 4.1 不许直连任何行情 / 新闻源

出向白名单**只有模型 API** (`runner/c41/egress_proxy.py:60`)。行情/新闻源域名**一律不得入表**，
import 期守门会抛 (`runner/c41/egress_proxy.py:114`, `runner/c41/egress_proxy.py:148`)，
被测配置的 `base_url` 指向它们也会在注册期红 (`runner/registry.py:145`)。当前拒绝表：

```text name=market_data_deny
query1.finance.yahoo.com
query2.finance.yahoo.com
fc.yahoo.com
finnhub.io
www.alphavantage.co
api.polygon.io
news.google.com
api.tiingo.com
api.twelvedata.com
www.reddit.com
api.stocktwits.com
api.polymarket.com
api.stlouisfed.org
```

**这张表是绊线，不是完备防线** (`runner/c41/egress_proxy.py:117`)。真正的判据是那条评审规则：
白名单每个条目必须指名一个需要它的被测配置 (`runner/c41/egress_proxy.py:138`)。

**后果写在代码注释里**：绕过数据面取数 = 网关 `access_log` 干干净净、前视探针全绿，
**而 as-of 强制已经失效** (`runner/c41/egress_proxy.py:115`, `runner/c41/egress_proxy.py:151`)。

**行为侧还有一道**：把网关设为不可达，若你的系统**仍能产出完整 artifact**，即判
「存在未声明的数据源」，这次运行的 as-of 强制**当场作废**
(`ops/specs/card_4.2_parser_scorer_adapters.md:496`)。源码扫描查"配置对不对"，
黑掉网关查"行为对不对"，两者都有 (`ops/specs/card_4.2_parser_scorer_adapters.md:499`)。

**TradingAgents 这类自带数据源的系统**：`yfinance` / `finnhub` / 新闻源要**整体替换**为经网关的实现
(`ops/specs/card_4.2_parser_scorer_adapters.md:493`)。
**RD-Agent(Q) 这类要 provider 树的系统**：把网关 snapshot 落成 qlib provider 树
（`calendars/` `instruments/` `features/`），**全部落在 `/task` 下，无宿主 bind-mount、无 NFS**
(`ops/specs/card_4.2_parser_scorer_adapters.md:463`, `ops/specs/card_4.2_parser_scorer_adapters.md:465`)。

**依赖装在镜像构建期，不进运行期白名单** —— 构建时联网、运行时断网
(`runner/c41/egress_proxy.py:85`)。包/镜像仓库出现在运行期白名单里会当场抛
(`runner/c41/egress_proxy.py:91`, `runner/c41/egress_proxy.py:143`)。

### 4.2 不许 best-of-N

跑 N 轮的系统必须把**选轮规则**交出来，规则只能来自 taskspec，非法即 `raise`，
选中的 `index` 进 `provenance` (`ops/specs/card_4.2_parser_scorer_adapters.md:509`,
`ops/specs/card_4.2_parser_scorer_adapters.md:512`)。

**为什么**：适配层"取最好那轮"等于给你加了一层**题目没给的搜索预算**，
harness × model 的可比性当场作废，**而且没有任何信号会红 —— 分数只是更高一点**
(`ops/specs/card_4.2_parser_scorer_adapters.md:515`)。

### 4.3 不许读写 `/task` 之外，也不许往 `work/` 里多放文件

run dir 有 **P8 文件集封闭**：顶层项封闭、`work/` 文件集封闭、协议工件按臂精确、无空文件
(`runner/inject.py:212`)。**多出一个文件就是"来路不明"**，直接红
(`runner/inject.py:255`)；sha256 对不上也红 (`runner/inject.py:258`)。
注入之后、起容器之前还有一道 `verify_run_dir_unchanged` (`runner/inject.py:295`) ——
实测就是探针脚本从这个窗口塞进 `work/probe.py` 才加的 (`runner/inject.py:299`)。

**`/task` 下你该新建的东西恰好是两类**：`artifact.json`，**加上**题面固定槽
「产出文件」点名的那一个 —— **S2 = `/task/panel.csv`、S3 = `/task/values.parquet`、
S7 = `/task/ledger.parquet`**，其余阶段没有这一项。契约（路径、列序、排序、索引、
浮点格式、编码）在 `genetask/file_contract.py:19` 的 `FILE_SPECS`，镜像自
`reference/artifact_schema.py:271` 的 `PAYLOAD_FILES`；容器退出后那次 P8 复核的允许集
是 `runner/c42/harvest.py:65` 的 `PRODUCED_BY_STAGE`，两边同源。
`panel_ref.sha256` / `values_ref.sha256` / `ledger_ref.sha256` 是**那个文件的字节摘要**
(`genetask/file_contract.py:80`)，不是重新序列化后的摘要。

**除这两类以外的中间产物写在容器的可写层里（`/tmp` 等），不要落进 `/task`。**
容器 `HOME` 不可写 —— 把 `HOME` / `<TOOL>_HOME` 指到 `/task` 下的
临时子目录会破 P8，请改指容器可写层。

容器以非 root 运行、`cap_drop: ALL`、`no-new-privileges`
(`runner/c41/runner_core.py:146`–`runner/c41/runner_core.py:148`)。
原因实测过：root 容器往宿主 bind mount 里写，harness 连删都删不掉
(`runner/c41/runner_core.py:140`)。

### 4.4 不许在 artifact 里自报越权率 / PIT / 前视 —— 自报不采信

**越权率来源网关日志的 `deny`，不采信 artifact 自报** (`ops/specs/s8_state_contract.md:108`)。
**前视违例由网关日志直接结算，不依赖产物申报**；
**日历违例抽样 20 个交易日做实际对齐核验**；
**复权违例用指纹法核验实际口径与申报是否一致** —— 设计原则一句话：
**验行为不验申报** (`ops/specs/GeneBench指标规格_v1.md:25`；`ops/specs/fairness_protocol.md:243`)。

**推论对你有利，别搞反**：**如实记录你尝试过的全部操作，包括失败的和被拒的**。
一个尝试了非法操作并如实记录的 agent，正是我们要与"根本没尝试"区分开的那类
(`ops/specs/fairness_protocol.md:251`)。**删掉不会让你得分**，因为合法性判定在评分器那边，
它读的是网关日志。

S8 另有一条：artifact 的 `events` 必须是 `/sim/log` 的**子集且顺序一致**
(`ops/specs/s8_state_contract.md:111`)。

### 4.5 不许把 key 写进产物或日志，不许绕过边车

容器里只有占位 key (`runner/c41/egress_proxy.py:79`)。
**自带一把 key 直连 → 403 `foreign_credential`**：那是一条未声明的资源，
它绕开预算闸，也让 usage 归属对不上 (`runner/c41/egress_proxy.py:880`,
`runner/c41/egress_proxy.py:883`)。

**CONNECT 允许集是空集**，任何 CONNECT 一律拒并留痕；空集不是"暂时没有条目"，是判据
(`runner/c41/egress_proxy.py:68`, `runner/c41/egress_proxy.py:75`)。
留一条 CONNECT 的路，等于给"agent 自带 key 直连"留门，而那条路上边车看不见任何东西：
没有 usage、没有 Steps、预算闸也管不着 (`runner/c41/egress_proxy.py:70`)。

**调用预算**：每 run 100 次调用 / 6,000,000 tokens (`runner/registry.py::RUN_BUDGET`)。
S4 与 S7 是多轮研究循环，各有更高的档（150 次 / 9,000,000 与 300 次 / 18,000,000，见 `runner/registry.py::BUDGET_TIERS`）。
2026-09-10 之前 token 上限是 600,000（票据 N-388 已裁定抬高）——**在那之前跑出来的 run 按旧预算解读**。
**超了返回 429 `budget_exceeded`** (`runner/c41/egress_proxy.py:887`,
`runner/c41/egress_proxy.py:889`)。上游无响应 → 502 (`runner/c41/egress_proxy.py:901`)。
**预算耗尽不是 harness 故障，是你的运行结束了** —— 请把重试与自检的调用数算进去。

**网关只绑显式 LAN 地址，不监听 `0.0.0.0`**；`/docs`、`/redoc`、`/openapi.json` 全关
(`gateway/app.py:4`, `gateway/app.py:136`)。别去探测，没有。

### 4.6 两臂的差异只能是协议工件

`strict` 与 `open` 的差异**穷举只有两项**：题面的表达形式、协议工件的有无
(`ops/specs/fairness_protocol.md:47`)。**超时与镜像不属于；环境变量除 `GENEBENCH_ARM` 外不属于**
(`ops/specs/fairness_protocol.md:52`)。

**对你的含义**：你的系统**不许读 `GENEBENCH_ARM` 去改行为**（改超参、改重试次数、改模型）。
读到 `arm` 只用于填信封的 `arm` 字段。两臂跑同一个镜像、同一份配置、同一个超时。

**「题面的表达形式」具体长什么样**（渲染表在 `genetask/render.py:59`, `genetask/render.py:60`,
`genetask/render.py:61`；口径行在 `genetask/render.py:291`, `genetask/render.py:309`）：

| 槽 | strict | open |
| --- | --- | --- |
| `as_of` | `as_of={v}` | `本次任务的 as_of 是 {v}` |
| 窗口 | `window={v}` | `计算窗口（window）是 {v}` |
| universe | `universe={v}` | `标的范围（universe）是 {v}` |
| 口径行 | `- {field}={v}（…，接口值 {v}）` | `- {散文}（字段 {field}，接口值 {v}）` |

**两臂逐字相同的那一段是「接口值 X」**（`genetask/render.py:305`, `genetask/render.py:309`）——
声明值就从那一段取。**只认 `key=value` 的解析器在 open 臂上取不到任何一个槽**，
而它的表现是零产物、零模型调用，不是一条报错。

---

## 5. 版本与冻结

### 5.1 四条版本轴

| 轴 | 回答什么问题 | 在哪看 | 当前值 |
| --- | --- | --- | --- |
| **任务集** | agent 看到的东西变了吗 | `ops/freeze_v10.py:378` | `1.0.11` |
| **参考面** | 我们算 gold 的方式变了吗 | `ops/freeze_v10.py:391` | `r1.0.18` |
| **协议** | 协议臂多拿到的那套东西变了吗 | `ops/protocol/geneprotocol_v1/MANIFEST.json` | `geneprotocol_v1`, `status: released` |
| **数据通道** | 数是从哪条通道来的 | `genebench_config.py:183`；`/healthz` 的 `channel` (`gateway/app.py:159`) | `v1`（private）/ `public_v1` (`genebench_config.py:620`) |

**可比性要求任务集与参考面两者都相同** (`ops/freeze_v10.py:726`)。
两条轴是 2026-09-05 拆开的：`solve.py` 是答案面走参考轴，题面与渲染器走任务集轴
(`ops/freeze_v10.py:382`, `ops/freeze_v10.py:57`, `ops/freeze_v10.py:62`)。

**`ops/specs/artifact_schema/` 在任务集冻结根里** (`ops/freeze_v10.py:43`)：
它会被逐字节复制成 bundle 的 `work/{stage}.json`，**两臂都拿得到**，
所以改它要推任务集版本 (`ops/freeze_v10.py:38`)。

### 5.2 你的产物要带哪几个版本字段

| 字段 | 位置 | 说明 |
| --- | --- | --- |
| `schema_version` | 信封必填 | 当前 `"1.0"` (`reference/artifact_schema.py:48`)；未知版本直接拒 |
| `as_of` | 信封必填 | `YYYY-MM-DD` (`reference/artifact_schema.py:1678`) |
| `declarations.data_version` | **S1 的声明字段** | `ops/specs/card_2.3_artifact_schema.md:34`；欠定时标 `"unresolved"` |
| `provenance[].artifact_id` | 信封必填（可空列表）| 上游阶段产物的引用，Audit 判据的一半 |

**其余三条轴不写进 artifact** —— 它们由 benchmark 侧从 `inject.json` 与冻结清单记录
(`ops/freeze_v10.py:121`)。你**不需要**、也**不应该**去自报任务集版本或参考版本。

### 5.3 数据冻结线

`as_of` 的绝对上界是 `genebench_config.FREEZE_DATE` (`gateway/asof.py:27`)。
越线不是"看见未来"，是"越过 v1 的数据边界"，同样 403 (`gateway/asof.py:10`)。
用 `/healthz` 读当前值。**2026-09-06 打生产网关实测**，它返回五个字段：

```json
{"ok": true, "freeze_line": "2026-07-31", "backend": "snapshot",
 "bind": "192.168.1.48:18080", "exposed_datasets": ["adj_factor", "..."]}
```

仓库里的 `gateway/app.py:159` 与 `gateway/app.py:160` 另加了 `channel` 与 `tables_dir`
（公开通道，卡 1.1-a，提交 `0fc0ab8`；**服务尚未重启**，所以线上还看不到）—— **别在这两个字段上写硬依赖**，
用 `.get()` 取并对缺失留一条路。`freeze_line` / `backend` / `exposed_datasets` 三个是稳定的。

**探活也是一次访问，同样记日志** (`gateway/app.py:150`)。

---

## 6. 接进来的最短路径

1. 读 `integrations/README.md` 的目录约定与 `harnesses/README.md` 的 schema
   （`launch.json` 六个键、`config.yaml` 七个键、`$` 要写 `$$`、base URL 只从 `env_required` 取）。
2. `mkdir -m 700 integrations/<你的 id>`，只建自己这一个目录。
3. 写 `Dockerfile`：把你的系统与 `integrations/genebench_client` 装进镜像。
   **依赖全部在构建期装完**（`runner/c41/egress_proxy.py:85`），运行期断网。
4. 写 `launch.json`（`paradigm: "P2"`）与 `config.yaml`（**先 `enabled: false`**）。
5. 在 f02 构建镜像，Dockerfile 抄回本目录并注明镜像名与 digest。
6. 出集 → 推送 → 真跑，三条命令在 `harnesses/README.md`。

**自检清单**（跑第一次真跑之前逐条过）：

- [ ] 所有取数都带 `as_of`，且 `end_date <= as_of` 显式给出（没有开区间）
- [ ] 三个身份头从环境变量取，不是硬编码
- [ ] 网关 URL 从 `$GENEBENCH_GATEWAY` 取，不是硬编码 `http://gateway:18080`
- [ ] S3 任务显式传 `fields`，且与 `declarations.required_fields` 一致
      —— **经 compat 层取数这一条做不到**（compat 一律按完整列集请求），改用 `gb.client().bars(..., fields=[...])`
- [ ] `fetched_at` 取自响应头 `x-genebench-ts`，不是本地时钟
- [ ] 题面没说的口径标 `"unresolved"`，不填默认值
- [ ] 只写 `/task/artifact.json` **加题面「产出文件」槽点名的那一个**（S2/S3/S7 有），其余中间产物不落 `/task`
- [ ] 不读 `GENEBENCH_ARM` 去改行为
- [ ] 一次 run 的模型调用 ≤ 100 次
- [ ] 没有任何代码路径能连到 §4.1 那张表里的域名

---

---

## 7. 本文自身的核对记录

**这份契约不是"照着代码复述"就算完** —— 复述得对不对，要打一次真网关。
2026-09-06 对生产网关（`192.168.1.48:18080`）逐条核过下面 17 项，脚本与输出留在
`$GENEBENCH_ROOT/scratch/c21/probe.sh` 与 `$GENEBENCH_ROOT/scratch/c21/probe_out.txt`：

| 契约说 | 实测 |
| --- | --- |
| `/bars` 不传 `fields` 返回 3 键 + 15 服务列 | ✅ 18 列，`fields` 回显 15 |
| 响应带 `x-genebench-ts` | ✅ |
| 开区间 → 403 `open_range_would_cross_asof` | ✅ |
| `end_date > as_of` → 403 `range_end_after_asof` | ✅ |
| 未知 `fields` → 422 `param_malformed` | ✅（报文直接列出服务集）|
| 缺 `as_of` → 422 `asof_missing` | ✅ |
| `as_of` 越冻结线 → 403 `asof_beyond_freeze_line` | ✅ |
| `as_of` 重复 → 422，不择一 | ✅ |
| `/adj mode=qfq` → 403 `adjustment_mode_not_in_v1` | ✅ |
| `/universe` 未知 → 422 `unknown_universe`（可选 `csi300/csi500/csi1000/all`）| ✅ |
| `/tradability` 不给 `code` → 422 | ✅ |
| `/limits` 带 `no_price_limit` 与 `sentinel_rows` | ✅ |
| `/fundamentals` 回显 `visibility` 且取当时可见的最新版 | ✅ 74 行 / 取版前 88 行 |
| `/fundamentals statement=fina_indicator` → 403 | ✅（报文写明缺 `f_ann_date`）|
| `/sim/*` 缺身份头 → 422 且列出缺哪三个 | ✅ |
| `/docs` 不存在 | ✅ 404 |
| **`/calendar` 越界报 `calendar_date_after_asof`** | ❌ **实报 `range_end_after_asof`**，见 §2.4 的提示框，已订正 |
| **`/healthz` 带 `channel` / `tables_dir`** | ❌ 生产网关**还没有**，见 §5.3，已订正 |

两处订正都是**契约照着工作树代码写、而生产服务跑的是另一版**造成的。
这正是这一节存在的理由：`ops/test_p2_contract.py` 能守住"契约与代码同源"，
守不住"代码与在跑的服务同源"。**改完网关请重跑一次 `probe.sh`。**

---

## 附：本文引用的一级来源

| 主题 | 文件 |
| --- | --- |
| 端点实现 | `gateway/routers/market.py` `gateway/routers/reference.py` `gateway/routers/sim.py` |
| as_of 与错误码 | `gateway/asof.py` `gateway/errors.py` |
| 日志与装配 | `gateway/access_log.py` `gateway/app.py` |
| 容器与出向 | `runner/c41/runner_core.py` `runner/c41/egress_proxy.py` `runner/registry.py` |
| `/task` 布局 | `runner/inject.py` `genetask/packager.py` |
| 身份三核 | `runner/c42/identity.py` |
| 产物 schema | `reference/artifact_schema.py` `ops/specs/card_2.3_artifact_schema.md` `ops/specs/artifact_schema/v1.0/` |
| 协议验证器 | `ops/protocol/geneprotocol_v1/validate_artifact.py` `ops/protocol/geneprotocol_v1/MANIFEST.json` |
| 判据与公平性 | `ops/specs/GeneBench指标规格_v1.md` `ops/specs/fairness_protocol.md` `ops/specs/s8_state_contract.md` `ops/specs/card_4.2_parser_scorer_adapters.md` |
| 版本与冻结 | `ops/freeze_v10.py` `genebench_config.py` |
| 实测记录 | `ops/tickets.md` `ops/HANDOFF.md` |
