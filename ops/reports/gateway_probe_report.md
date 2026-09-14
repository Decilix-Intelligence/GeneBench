# 网关探针单测报告（卡 1.3 / 1.4）

生成于 `2026-08-31T19:45Z` · 数据冻结线 `2026-07-31` · 仓库 HEAD `f3ad9d1` ·
依赖快照版本：`$SNAPSHOTS/v1/tables/` manifest（22 张表 / 63,158,095 行 / 1.46 GiB）、
qlib release `2026-08-26`、湖 catalog `market.duckdb`（150 个只读 view，湖是活的，每天在长）。

> **本报告替换 2026-08-31T18:20Z 的同名版本。** 那一版写于网关尚未开工时，
> 开篇即声明"不含任何一条网关探针跑绿了的结论"。现在网关已交付，这份是它的兑现。

---

## 执行摘要（三行）

1. **卡 1.3 与卡 1.4 已交付并验收通过。** 探针套件 `ops/test_gateway.py` **70 项全绿**，
   快照套件 `ops/test_snapshot.py` **47 项全绿**，全量 `pytest ops/` = **622 passed / 0 failed**。
   前一版报告表 A 里那 12 条 ❌ 未实现·未测，现已逐条兑现（G-11/G-12 由卡 1.4 套件承接）。
2. **红线 4 由活服务实证，不是靠断言自证**：`ss -lntp` 实测 `LISTEN 192.168.1.48:18080`；
   从 tailscale 地址 `100.79.40.76:18080` **被拒**，连 `127.0.0.1:18080` 也**被拒**（只绑了 LAN 地址）；
   收尾后 18080 无监听、无残留进程。
3. **探针跑出两个真问题，都不是"测试没写好"，是产品缺陷**：
   ① 重复 `as_of` 参数时 FastAPI 取**最后一个**（宽的那个）并放行 —— 一次**可否认的越权**，已改为 422 拒绝；
   ② 快照按 `cal_date` 截 `trade_cal`，把 153 行**预写的未来日历**砍掉了，T+N 对齐会断，已改为 capture_time 表不截。

> **这份可以作为卡 1.3 / 1.4 的放行依据。** 需要一并复核的另一份是卡 1.1 的
> `ops/reports/universe_reconciliation.md`（宇宙对账，42 KB）。

---

## 1. 交付状态取证

| 检查 | 命令 | 实测 |
| --- | --- | --- |
| 网关实现 | `find repo/gateway -type f -name '*.py'` | 8 个模块：`app / asof / access_log / backends / errors / run / routers.market / routers.reference` |
| 路由 | `registered_paths(app)` | 8 条，与 `ALLOWED_ROUTES` **逐条相等** |
| 探针套件 | `pytest ops/test_gateway.py -q` | **70 passed in 13.88s** |
| 快照 manifest | `$SNAPSHOTS/v1/tables/manifest.json` | 22 张表 / 63,158,095 行 / 1.46 GiB / 每张带 sha256 |
| 快照套件 | `pytest ops/test_snapshot.py -q` | **47 passed in 20.21s** |
| 全量 | `pytest ops/ -q` | **622 passed in 170.88s**（exit=0） |
| 残留进程 | `ss -lntp \| grep 18080`、`pgrep -f gateway.run` | 均为空 |

---

## 2. 探针清单（70 项，按前一版报告表 A 的编号对齐）

| # | 探针 | 守的契约 | 断言方式 | 结果 |
| --- | --- | --- | --- | --- |
| **G-01** | `as_of` 必填 | 每请求强制 `as_of` | 7 个端点族各发一次不带 `as_of` 的请求 → 422 且 `reason=asof_missing`；另有 9 种畸形 `as_of`（`2026/07/31`、`2026-2-30`、带时区、空串…）逐一必拒 | ✅ 17 项绿 |
| **G-02** | 越界必 403 | 任何目标日期 > `as_of` 一律 403，响应体不得夹带数据 | 8 条路径参数化（显式 `end_date`、区间右端、开区间、未来日历、宇宙右端、可交易性日期…）+ 大小写变体 + 重复参数 + 响应体无 `data`/`members` | ✅ 16 项绿 |
| **G-03** | 越界必记录 | 403 必写 `access_log`（`config_id`/`task_id`/请求全文/`reason` 码） | 打越界请求 → 断言日志新增一行、七个字段齐全、`params` 可回放；allow 也要记；日志落点在 repo 之外 | ✅ 3 项绿 |
| **G-04** | PIT 可见性翻转 | 三大报表按 `f_ann_date` + `update_flag` 严格 PIT | 边界日**从湖里现查**（不写死）：`as_of=` 边界前一日 → 0 行，边界日 → ≥1 行；另有 N-15 的 NULL 判别力测试与"必须用 f_ann_date 不是 ann_date"的源码断言 | ✅ 3 项绿 |
| **G-05** | 停牌日 bars | 停牌日返回带 `status` 而非静默空 | 样例**从 `suspend_d` 现挖**且在冻结线内 → 断言有行、`status` 非空且属五档枚举 | ✅ 1 项绿 |
| **G-06** | 复权口径唯一 | 统一 `adj_factor`，三价口径不进 v1 | 5 种 `mode`（含大小写）必拒 + 响应列名不得以 `_hfq/_qfq/_bfq` 结尾 | ✅ 6 项绿 |
| **G-08** | `fina_indicator` 不可达 | 缺 `f_ann_date`，无法严格 PIT | 3 个被排除数据集逐一 403 + 白名单是**白名单**（未登记的表必拒） | ✅ 4 项绿 |
| **G-09** | 绑定地址 | 必须绑 `192.168.1.48`，禁 `0.0.0.0` | 守门函数 8 种通配写法必抛；`run.py` **必须经守门函数**取 host；AST 扫全包**代码里**无 `0.0.0.0` 字面量；端口可绑即释放 | ✅ 4 项绿 + 活服务实证（见 §4） |
| **G-10** | 答案隔离 | 不服务 `reference/` 与 `scorer/` | 9 条路径（含 `../`、URL 编码穿越、猜测端点名）必拒；路由白名单**逐条相等**且非空跑；路由名不含禁用字样 | ✅ 11 项绿 |
| **G-11** | 两后端一致（卡 1.4） | 冻结线内同查询同结果 | 10 组查询 + 1 组跨表 join，`assert_frame_equal` **不放水** | ✅ 见 `ops/test_snapshot.py` |
| **G-12** | manifest 完整（卡 1.4） | sha256 与行数逐表校验 | 22 张逐表核 sha256/字节数/行数；篡改一个字节必红 | ✅ 见 `ops/test_snapshot.py` |
| — | `/limits` 不泄露哨兵价 | 卡 1.2 D1 的下游版本 | 哨兵样例**从湖里现挖** → `no_price_limit=true` 且 `up/down_limit` 为 `null`；`pre_close` 不透出 | ✅ 2 项绿 |
| — | 后端开关是配置驱动 | 不是改代码 | 环境变量三态（snapshot/live/非法值必抛） | ✅ 1 项绿 |

**G-07（多快照表语义）** 现状：`stock_basic` 类的快照语义已在数据层封装（卡 1.1 的
`universe_build.load_listing_windows()` 走 `list_date`/`delist_date` 字段回溯而非快照分区），
但网关**没有单独暴露 `/stock_basic` 端点**，所以没有独立探针 —— 它经 `/universe` 间接生效。
这是覆盖缺口，登记见 §6。

---

## 3. 越界拦截：每条路径与取证

`as_of=2026-06-30` 统一视角，逐条打。全部返回 **403**，响应体经断言**不含** `data`/`members`。

| 路径 | 请求 | `reason` 码 | 谁在守 |
| --- | --- | --- | --- |
| ① 显式 `end_date` 越界 | `/adj?as_of=20260630&end_date=2026-07-31` | `range_end_after_asof` | `asof.guard_range()` |
| ② 区间右端跨过 as_of | `/bars`、`/limits` 同构 | `range_end_after_asof` | 同上 |
| ③ **开区间** | `/adj?as_of=…&start_date=…`（不给 end） | `open_range_would_cross_asof` | 同上，**默认拒绝**而不是静默夹紧 |
| ④ 未来交易日历 | `/calendar?end_date=2026-12-31` | `range_end_after_asof` → `calendar_date_after_asof` | `guard_range` + `/calendar` 再显式点名一次，便于按路径聚合 |
| ⑤ 宇宙区间右端 | `/universe?date=2026-07-31&as_of=20260630` | `universe_asof_after_asof` | `asof.guard_target()` |
| ⑥ 可交易性日期 | `/tradability?date=…` | `target_date_after_asof` | 同上 |
| ⑦ **as_of 自身越冻结线** | `as_of=2026-09-01` | `asof_beyond_freeze_line` | `asof.parse_asof()`，红线 7 |
| ⑧ 产物层兜底 | `universe_at()` / `tradability_at()` 越界抛 `ValueError` | 被翻成 403 `beyond_freeze_line` | 卡 1.1/1.2 的产物本身 |

**设计上的两条不变量**（写在 `gateway/asof.py` 模块 docstring 里）：

1. **`as_of` 自身也夹到冻结线** —— `as_of=2026-09-01` 不是"看见未来"，是"越过 v1 的数据边界"，同样 403。
2. **判定必须先于取数** —— 403 要在碰湖之前发生。否则"查完再判"会在日志里留下一次实际读取，
   卡 5.1 结算前视时分不清"读了但没给"和"根本没读"。

### 3.1 🔴 探针抓到的真漏洞：重复 `as_of` 时取宽的那个

```
GET /calendar?as_of=2026-06-30&as_of=2026-07-31&start_date=2026-07-01&end_date=2026-07-20
修复前 → 200，返回了 2026-06-30 之后的日历行
```

FastAPI 对标量 `Query` 参数取**最后一个**值。于是调用方可以同时递交一窄一宽两个 `as_of`，
拿到宽的那份数据，而在任何按第一个值记账的地方声称自己守规矩 —— 一次**可否认的越权**。

修法不是"取窄的那个"，而是**在路由之前直接 422 拒绝**：授权参数出现歧义，
必须由调用方消除，网关不替它择一。覆盖 `as_of / start_date / end_date / date /
universe / scope / statement / mode`（`code` 例外，它本来就是多值参数）。

---

## 4. 红线 4：绑定地址的活服务实证

TestClient 测不到"进程实际监听在哪个地址"。真起了一次服务：

```
$ ss -lntp | grep 18080
LISTEN 0 2048  192.168.1.48:18080  0.0.0.0:*  users:(("python",pid=256629,fd=6))

$ curl http://192.168.1.48:18080/healthz        → 200
$ bash -c 'echo > /dev/tcp/100.79.40.76/18080'  → 拒绝 ✅   （tailscale 地址）
$ bash -c 'echo > /dev/tcp/127.0.0.1/18080'     → 拒绝 ✅   （连回环都没绑上）

收尾后 18080 上还剩: (空)
```

**为什么这条值得单独做实验**：tailscale 把自己的 ACCEPT 规则插在 ufw 之前，
`0.0.0.0` 就等于对**整个 tailnet** 敞开，而这个 tailnet 里有第三方账号（`wx200.xyz@`）的节点。
第二轮侦察已用一对受控实验证过这一点（同端口同客户端，只改绑定地址，tailnet 可达性 3/3 拒 ↔ 3/3 通）。

防线做成三层，且**让"绕过"比"遵守"更费事**：

- `cfg.assert_no_wildcard_bind()` 拦 8 种通配写法，`run.py` 里内联调用（不经它拿不到 host）；
- AST 扫描：`gateway/` 包的**代码**里不许出现 `0.0.0.0` 字面量（docstring 里讨论它是应该的）；
- 活服务 `ss` 实证。

同一次活服务里也验了越界与日志的端到端：

```
$ curl -H 'x-genebench-config-id: live-check' -H 'x-genebench-task-id: t-live' \
    'http://192.168.1.48:18080/adj?as_of=2026-06-30&code=600519.SH&start_date=2026-07-01&end_date=2026-07-31'
HTTP 403
{"error":"denied","reason":"range_end_after_asof","detail":"end_date=20260731 晚于 as_of=20260630", ...}

$ tail -1 $GENEBENCH_ROOT/logs/gateway_access.jsonl
{"ts":"2026-08-31T19:04:33.591+00:00","config_id":"live-check","task_id":"t-live",
 "method":"GET","path":"/adj","params":{"as_of":"2026-06-30","code":"600519.SH",
 "start_date":"2026-07-01","end_date":"2026-07-31"},"as_of":"2026-06-30",
 "decision":"deny","reason":"range_end_after_asof","status":403,"backend":"live",
 "freeze_line":"2026-07-31","pid":256629,
 "extra":{"field":"end_date","value":"20260731","as_of":"20260630"}}
```

字段够卡 5.1 的前视探针独立结算：`config_id` + `task_id` 定位是谁、`params` 可回放、
`reason` 可按路径聚合、`decision` 直接给越权率的分子。

---

## 5. PIT 正确性与 N-15

### 5.1 可见性翻转（边界日从湖里现查，不写死）

探针不接受任何人给的日期常量 —— 先 `SELECT f_ann_date FROM income WHERE ts_code=? AND end_date=?`
现查出边界，再对边界前一日与边界日各请求一次，断言 `rows` 从 0 翻到 ≥1。

这样写的理由是卡 0.2 D1 与卡 1.2 D3 的教训：**把实现里的常量抄一遍再和实现比，是恒真式**。

### 5.2 N-15：`f_ann_date` 的 NULL 是一个全市场级前视泄漏的岔路口

`income_vip` 全表 **5,708 行** `f_ann_date` 为 NULL（2026Q1 占 5,686 行 / 5,678 只票 = 该季 27.7%），
成因是分区间 schema 漂移 + 视图 `union_by_name=true`（部分分区根本没这一列）。

过滤条件怎么写，差一个全市场级泄漏：

| 写法 | NULL 的归属 | 判定 |
| --- | --- | --- |
| `f_ann_date <= as_of` | SQL 三值逻辑判 UNKNOWN → 丢弃 | ✅ 对，但意图不写在脸上 |
| `NOT (f_ann_date > as_of)` | 同样 UNKNOWN → 丢弃 | ✅ 对，但更容易被误读成"保留" |
| `coalesce(f_ann_date, ann_date)` | 用 `ann_date` 兜底 | 🔴 **全市场级前视泄漏** |

网关显式写 **`f_ann_date IS NOT NULL AND f_ann_date <= as_of`** —— 不依赖三值逻辑的直觉。
配套两条测试：一条从**湖侧现算** NULL 行数（若哪天 NULL 没了，说明 N-15 前提变了，会提醒回来改结论），
一条源码级断言禁止 `coalesce` 兜底。

**缓解事实**（第二轮侦察已实测）：那 5,678 只票**每一只都同时**有非 NULL 行，
"只有 NULL 行"的票 = 0，所以严格丢弃不会丢掉任何公司。

### 5.3 `update_flag` 取版规则

同一 `(ts_code, end_date)` 在 `as_of` 时点可能已有多版。网关取**当时能看见的最新那一版**：
按 `f_ann_date` 降序、同日再按 `update_flag` 降序取第一条。

**不是取最终版**——"2026-04-25 那天看到的是哪一版"和"这一期最后定稿是哪一版"是两个问题，
benchmark 要的是前者。

---

## 6. 卡 1.4：快照与双后端

**22 张表 / 63,158,095 行 / 1.46 GiB**（`/data` 余 2.5 T）。manifest 逐表记
sha256 / 字节数 / 行数 / 源行数 / 源 max_date / 截断后 max/min / 分区语义 / **停更状态** / 用它的卡号。

### 6.1 🔴 capture_time 表不能按日期列截

首版按 `cal_date <= 冻结线` 截了 `trade_cal`，双后端一致性当场炸出 **6574 vs 6421**。
那 **153 行**是 `2026-08-01…2026-12-31` 的**预写未来日历** —— 冻结时点本就合法存在，
砍掉它 T+N 对齐就断。

根因与卡 0.2 补救 D3 同源：**capture_time 表的时间语义不在它的日期列上**，
而在 `snapshot_date`（我们哪天抄的表）。现由正反两条测试看住：
`test_capture_time_tables_are_not_truncated`（不许截）与
`test_trade_cal_keeps_the_future_calendar`（未来日历必须还在）。

### 6.2 三大报表的截断口径

网关按 `f_ann_date` 判可见性，快照按 `ann_date` 截 —— **两列不保证同序**，
只按 `ann_date` 截理论上会丢掉 `ann_date > 冻结线` 而 `f_ann_date <= 冻结线` 的行，
那正是"本该可见却被静默丢掉"。

改成 `ann_date <= L OR f_ann_date <= L` 超集口径，真正的 PIT 由网关判。
并把风险**实测**进 manifest 而不是假设它是 0：

```json
"statement_bound_risk": {
  "measured": {"balancesheet":0,"balancesheet_vip":0,"cashflow":0,
               "cashflow_vip":0,"income":0,"income_vip":0}
}
```

六张表**全为 0** —— 当前无实际损失，但这是量出来的。若哪天不为 0，超集口径就从"保险"变成"必需"。

### 6.3 双后端一致性是**真的两条路径**

`live` 走 catalog 视图，`snapshot` 走 parquet 文件；`assert_frame_equal` **不传**
`check_dtype=False` / `check_like=True`（那会把比对削成"形状差不多就行"）。
只归一化行序与索引 —— 行序不是语义。

10 组查询 + 1 组跨表 join（`daily ⋈ adj_factor`）。负控：改一个字节，sha256 与一致性**都必须炸**。

### 6.4 又一条我自己写的恒真测试

`stalled_from_baseline()` 把基线里的 `stalled_tables`（一串带 `lag_days` /
`why_it_looks_green` 的 dict）`str()` 成了字面量，于是 `source_stalled` 恒为 False，
而配套那条测试因为**两边都空**恒真通过。

现在明细原样保留、名字单独抽一份，测试钉死"必须真的标出 8 张，空集直接失败"。
8 张停更表：`balancesheet` `cashflow` `dividend` `income` `index_basic`
`limit_list_d` `namechange` `trade_cal`。

---

## 7. 没测到什么（覆盖缺口，诚实列出）

1. **G-07 多快照表语义没有独立探针。** `stock_basic` 类的字段回溯逻辑在卡 1.1 的数据层，
   网关没单独暴露端点，只经 `/universe` 间接生效。要补得先决定要不要开 `/instruments` 端点。
2. **并发与压力一条没测。** `access_log` 用进程内锁，单进程 uvicorn 够用；
   **上多 worker 必须先换方案**（每 worker 一个文件或走 syslog），已写在模块 docstring 里。
   当前没有任何测试会在有人加 `--workers 4` 时报红。
3. **没有跨机测试。** 执行面（finance02）到网关的实际连通性没验 —— 那要等 T-02（装 docker）之后，
   而且届时要一并确认容器网络能路由到 `192.168.1.48:18080`。
4. **`/bars` 的大窗口性能没量。** 目前靠 `MAX_ROWS=200_000` 硬拦，
   但"多大窗口会慢到不可接受"没有基线数字。
5. **快照没有做跨版本比对。** manifest 有 sha256，但没有"上一版 vs 这一版差了什么"的工具 ——
   v1 只有一版，等 v1.1 再说。
6. **`update_flag` 多版本的测试只覆盖了单一公司。** 全市场有多少 `(ts_code,end_date)`
   真的存在多版、多版之间间隔多久，没有统计。
7. **`/fundamentals` 没有做 `end_type` 维度的正确性验证**（年报/中报/季报的口径差异）。

---

## 8. 与前一版报告的差异

前一版（`2026-08-31T18:20Z`）写于网关尚未开工时，它的价值在于**在无实现的前提下把地基查清楚了**，
并挖出 N-15 这颗地雷。本版保留它的三项实证结论（红线 4 的受控实验、PIT 翻转的湖侧复现、
答案面无暴露路径），把表 A 的 12 条 ❌ 换成实测结果。

前一版明确写着"不是放行凭据"。**本版是。**
