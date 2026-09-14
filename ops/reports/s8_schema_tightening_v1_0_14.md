# S8 事件 schema 收紧与滑点符号统一（v1.0.14 / r1.0.21，卡 Y1）

生成日期 2026-09-10。裁定来源：用户 2026-09-10 批 **N-383**（Slip 纳入判据、符号统一）与
**N-384**（`events.required` 收紧）。本文件是那两条裁定的**后果清单** —— 代码注释里
（`reference/artifact_schema.PAYLOAD_SHAPE["S8"]`、`ops/test_s8_event_fields.py`）指向的就是它。

## 1 两条根

| 轴 | 版本 | root |
| --- | --- | --- |
| 任务集 | v1.0.13 → **v1.0.14** | `925a1adcdf82e6a0…` → **`947bf817ae3df348e2bd6a979dfa156a5fe4186f2a9c1fa243fba540e2b8adc8`** |
| 参考 | r1.0.20 → **r1.0.21** | `8c162988c2a7b5d2…` → **`399fffde62108b522106ef10673c213e050174fe40ac60b4edd5d0e624473b8d`** |

`instances_fingerprint = 969f698618eaaaae7bb319ef31d5ade997c2ddfd649bdd3a1b18cd469c0eccba`
（**不在 `ROOT_FIELDS` 里** —— 实例表变动不作废任何 bundle 通行证）。

**已发通行证全部作废**：Y1 之后的出集必须在本次重冻之后做。

## 2 N-383：滑点的符号

### 2.1 不一致的三处

| 处 | 公式 | 翻符号？ |
| --- | --- | --- |
| `ops/specs/GeneBench指标规格_v1.md` §3 | `Slip = 量加权(成交价 − 决策时点价) bps` | 否 |
| `gateway/sim_engine.py::slippage_bps` | `qty × (成交价 − 基准) / 基准 × 1e4` | 否 |
| S8 五题两臂题面（N-127，v1.0.13 落） | 「成交价高于计价基准时取正，低于计价基准时取负」 | 否 |
| `reference/s8_oracle_common.py::fill_metrics`（**改前**） | 上式 `× sign`，`sign = +1 买 / −1 卖` | **是** |

三比一，以规格 §3 为准 → 删掉 `fill_metrics` 的 `sign`。

### 2.2 gold 重出（两条通道各一次真跑，O1 全绿）

| 题 | 模板 | 旧 Slip（带 sign） | 新 Slip | 变了？ |
| --- | --- | ---: | ---: | --- |
| `s8-cor-01` | `s8_lifecycle` | −202.514311 | **+53.483048** | **是** |
| `s8-eco-01` | `s8_min_slippage` | −160.492521 | −160.492521 | 否 |
| `s8-ops-01` | `s8_audit_overreach` | +26.587586 | +26.587586 | 否 |
| `s8-rob-01` | `s8_idempotent` | −149.031264 | −149.031264 | 否 |

**只有 `s8-cor-01` 变**，因为它是唯一一道既有买单又有卖单的题（建仓 + 清仓）；另外三道全是买单，
`sign` 恒为 +1，逐位不变。私有与公开两条通道的四个数**逐位一致**。

### 2.3 代价（不许省）

旧口径读作「**执行不利度**」：买贵与卖便宜都是不利，同号相加。
新口径读作「**相对基准的价格偏离**」：一买一卖的偏离**会互相抵消** ——
一个双边完成的建仓＋清仓可能报出接近 0 的 Slip，而两条腿各自都是不利成交。
`s8-cor-01` 从 −202.5 变成 +53.5 就是这件事的实测数字。

这是**定义**的改变，不是 bug 的修复。v1 的 Slip 是价格偏离。要量执行不利度得另立一个指标
（登记在 `ops/tickets_inbox/Y1.md`），不能靠在 oracle 里翻符号 —— 翻了它就与网关自己算的那份、
与题面告诉被测方的那条对不上，而后两者是**被测方看得见**的。

### 2.4 判据：Slip 判什么、容差怎么来

**不与 gold 比。** S8 的题面没规定下哪些单（实测三个 agent 分别产生 12 / 10 / 4 条状态迁移），
agent 与 oracle 两轮不是同一个量的两次测量 —— 拿 gold 的数当标准答案是 N-114 同族的错误。
Fill 早就因为这条只判自洽，Slip 现在同形：

> `SlipSelfConsistent` = 「自报的 `slippage_bps`」与「从 **agent 自己那条事件链** 重算的
> 量加权 Slip」之差 ≤ 一个最小价位换算成的 bps。

换算式（`scorer/l3.MIN_TICK_CNY` 与指标规格 §3 脚注两处逐字相同）：

```
tol_bps(单 i) = 0.01 元 / 该单的计价基准(元) × 10000
tol_bps       = Σ_i 成交量_i × tol_bps(单 i) / Σ_i 成交量_i
```

逐单换算而不是给一个固定 bps：0.01 元在 1720 元的标的上是 **0.058 bps**，在 3 元的标的上是
**33 bps**。给固定 bps 等于对高价标的过松、对低价标的过严。

**读不到基准价 → `unobservable`，不是 0。** 计价基准由题面声明 `slippage_reference_price` 决定；
`close` / `open` 两档的基准是**环境侧**的价，事件链里根本没有，那两档下 Slip 记跳过。
`reference_close` 档要求 order 事件带 `reference_close`（契约 §2 的委托记录里有，`/sim/log` 也发它）。
已发布四道题的声明全是 `reference_close`。

**已知边界**：`reference_close` 不在 `PAYLOAD_SHAPE["S8"].events` 的 `required` 里（题面没要求带它），
所以一个照题面做到位、但没把基准价写进 order 事件的被测方，Slip 会记 `unobservable` 而不是判 0。
这是刻意的 —— 判据要的东西题面必须说，题面没说就不判（N-114 / N-127 / N-128 同一条纪律）。

## 3 N-384：`events.required` 收紧

### 3.1 收紧成什么

题面（N-128 随 v1.0.13 落，五道题两臂各四行）逐字要求：

* order 事件必须带 `order_id`、`symbol`、`side`、`qty` 四个键
* fill 事件必须带 `order_id`、`symbol`、`side`、`qty`、`price` 五个键
* cancel 事件与 state 事件必须带 `order_id`，state 事件另带 `state` 键

扁平的 `required` 说不出「按 type 分档」，所以：

* **扁平 `required` = `["ts", "type", "order_id"]`** —— 四类的**交集**（四类都要 `order_id`）；
* **逐类的那一半走 `allOf` + `if/then`**，逐字对着上面三行取，不多不少。

把逐类必填塞进扁平 `required` 会要求 cancel 事件也带 `price` —— 那是**比题面严**。

### 3.2 三个消费者的能力不同（这件事必须写下来）

| 消费者 | 认 `allOf`/`if`？ | 于是它拦得到 |
| --- | --- | --- |
| 完整 JSON Schema 校验器（`genebench_client` 发给被测方的那份） | 是 | 全部 |
| `ops/protocol/geneprotocol_v1/validate_artifact.py::_type_ok`（**够用子集**） | **否** | 只有缺 `order_id` |
| `reference/artifact_schema._s8`（评分器 L1） | —（手写） | **刻意也只到 `order_id`** |

后两者必须收得**一样宽**：`ops/validator_parity.py` 守着两个方向 ——
「validator 报 ⟹ scorer 也必须报」与「作用域内 scorer 报 ⟹ validator 也必须报」。
任何一边多严一点，那两条里就断一条。逐类的那几个字段仍由 **L3 的 Audit** 判
（`scorer/l3.REPLAY_FIELDS`，且要求**有值**不只是键在，卡 5.1 的收紧）。

收紧后跑 `ops/validator_parity.py`：语料 124 份，**两个方向各 0 份缺口**。

### 3.3 题面为什么跟着变

`fixed:output_format` 固定槽是**机器从 schema 的 `required` 生成**的。收紧之后 S8 五道题两臂的那一句
从「events 含 ts, type」变成「**events 含 ts, type, order_id**」。

**题面正文一个字没手改** —— 变的是机器生成的那一句。但 agent 看到的东西确实不同了，所以推 v1.0.14。
这也正是收紧的正面后果：共享 schema 与题面**第一次真的等价**。

### 3.4 既有产物：不追溯

v1.0.13 及以前跑出来的 **121 份真产物**（`runs_in/{m6,m6b,a1}`）多数的 order 事件只有 `{ts, type}` ——
按新 schema 它们集体畸形。**不重判、不重算分**：题面当时没这么要求，判它们畸形是对被测方不公平
（这正是 N-128 立案的原因）。

* 旧产物按**旧 schema**判，主表上 v1.0.13 及以前的 S8 结果口径不变；
* 新旧不可比的地方有两处：S8 的 `malformed` 率（schema 收紧）与 `s8-cor-01` 的 Slip（符号统一）；
* `ops/validator_parity.py` 的语料基线因此**不做追溯修正**，它比的是「两个校验器判得一样吗」，
  而两者在收紧前后都一致（各 0 份缺口），这条判据本身跨版本成立。

跟着改的**只有样例与测试用例**（它们是「合法的最小例子」，必须随规则走）：
`reference/artifact_samples.py::s8()`、`ops/test_emit.py` 的 S8 最小样例、
红队用例 `ops/redteam_cases/c23/rt34_env2_03_S8_ts_mixed_precision_false_reject.json`
（那条用例查的是**时间戳精度**，不补 `order_id` 它会因为一个无关的原因变红，也就不再查它本来要查的东西）。

## 4 六道欠定探针题：仍然挂起

W3 逐题判过，六道在 `ops/reports/public/materiality_screen.{json,md}` 里**全部 `inconclusive`**，
而且是同一个结构性原因：筛查 harness 是三份冻结的 **S7 回测引擎**，S1–S5 / S8 的探针字段
根本没有进入它的入口。照 screen 自己的判据 ——

> 任何一题 inconclusive 都不许翻锁 —— 「跑不起来」「量不到」都不是「没差别」。

—— **一道都不放出**，`genetask/schema.py::DIVERGENCE_EVIDENCE` 一个字未加。
出集维持 **34 题 / 挂起 6 题**。逐题缺什么见 `ops/reports/instances_design.md` §9（W3 写的表）。

**本卡对那张表的一处更新**：`s8-rob-02` 那一行写着「与 N-383 的 Slip 判据是同一条线：
Slip 纳入 S8 判据之后，这道题才有量得到的可能」。Slip **今天已经纳入**了，但那道题**仍然量不到** ——
Slip 判的是「自报与自己的事件链一致」，不是「换一个 `slippage_reference_price` 会不会让结果不同」。
后者要的是**三份独立的 S8 撮合实现**并且它们各有滑点参考价这个入口，而那不存在。
把「Slip 纳入判据」读成「s8-rob-02 可以放出了」是错的。

## 5 实例层第一次进清单

130 个实例（40 基点 × 窗口/宇宙/因子池，W3 生成）写进 `ops/manifests/v1.0-smoke.json` 的
`instances` 段，逐实例记 id / 参数 / 题面指纹 / 夹具 sha。

**夹具：47 个已物化，83 个没有**（如实记 `fixtures: {}`，不假装有）：

| 阶段 | 实例数 | 夹具物化 | 说明 |
| --- | ---: | ---: | --- |
| S1 / S2 / S3 | 17 / 17 / 17 | — | 这三阶段的题不引用夹具（`inputs` 为空），无须物化 |
| S4 | 17 | 17 | 因子面板切片，3 分 46 秒，峰值 RSS 1.0 GB |
| S5 | 17 | 17 | 信号切片 |
| S7 | 15 | 15 | |
| S8 | 15 | 0 | 题不引用夹具 |
| **S6** | **15** | **0** | **做不了，见下** |

S6 卡在一个先有鸡还是先有蛋：`reference/make_fixtures.py::s6_consumer_window(set_root)` 要先在
**实例集根**里扫到「引用 `reference/signals/*` 的题」才能算出窗口并集，而那些题**正是它要出夹具的题** ——
它们要等夹具 sha 才写得进去。实测报 `FixtureError: 没有任何题引用 reference/signals/*`。
`reference/make_fixtures.py` 在参考轴冻结根里且不在本卡的路径清单内，**没有动它**；
处置写进 `ops/tickets_inbox/Y1.md`。

## 6 复现命令

```sh
GB=/data/shared/genebench; PY=$GB/env/bin/python; cd $GB/repo

# gold 重出（私有 / 公开各一次）。外层持网关锁 → 内层必须 --no-batch-lock，
# 否则同一把 fcntl.flock 在另一个进程里再拿一次会永久阻塞（实测等 120 s，holder 就是自己）。
$PY ops/gateway_lock.py --what "…" -- \
  $PY ops/run_oracles.py --tasks s8-cor-01,s8-eco-01,s8-ops-01,s8-rob-01 --no-batch-lock
ops/public_gateway.sh run -- \
  $PY ops/run_oracles.py --tasks s8-cor-01,s8-eco-01,s8-ops-01,s8-rob-01 \
      --no-batch-lock --set-name public/v1.0-smoke-public
# ↑ 落点 = <ANSWER_ROOT>/tasks/<set_name>，ANSWER_ROOT 固定是 $GB/reference（N-61 / D-28）。
#   把 --answer-root 指到 .../tasks/public 会落在 .../tasks/public/tasks/…（踩过一次）。

# schema 重生成 + 副本重灌
$PY ops/mk_artifact_schemas.py            # 八份，只有 S8.json 变

# 重冻（分两次，N-111）
flock -w 7200 $GB/locks/heavy.lock systemd-run --user --scope -q -p MemoryMax=10G \
  $PY ops/freeze_v10.py --write --with-instances
flock -w 7200 $GB/locks/heavy.lock systemd-run --user --scope -q -p MemoryMax=10G \
  $PY ops/freeze_v10.py --write-reference

# 一致性
$PY ops/validator_parity.py --out <自己的落点>   # 不要覆盖 ops/reports/ 里那份共享的
```
