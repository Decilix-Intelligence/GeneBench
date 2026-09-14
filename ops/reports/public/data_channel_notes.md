# 公开通道数据面：陷阱清单与对账（卡 1.1-a / 卡 2.5）

> **这份是给卡 1.3 写数据卡用的原料。**里面每一个数字都是**公开通道自己**跑出来的，
> **没有一个是从私有通道的数据卡抄来的** —— 抄来的数字描述的是另一份数据，
> 而读者会以为它描述的是手上这份（卡 2.5 §8）。
> 引用私有通道的地方只有一类：**拿它当验证器**时的对账结果，那种地方都明写「对账」。

建于 `2026-09-06`（北京时间当晚，非交易时段）。产物路径与命令见 §7。

---

## 1. 这条通道是什么

| | 公开通道 | 私有通道（对照） |
| --- | --- | --- |
| 源 | **baostock**（免费、可再分发性见 §2） | 审计湖（tushare）+ ChinaScope |
| 落点 | `$SNAPSHOTS/public_v1/` | `$SNAPSHOTS/v1/` |
| 覆盖 | v1 三宇宙**并集 3,575 只**，2009-01-05 .. 2026-07-31 | 全市场 5,817 只，同窗口 |
| 网关 | `GENEBENCH_CHANNEL=public`，端口 **18081** | 生产网关，端口 18080 |
| 财务 | **不服务**（§5.9） | `/fundamentals` 服务 |

**两条通道并列、不覆盖**：本通道的构建过程一个字节都没写进 `snapshots/v1/`
（`ops/build_public_channel.py --step verify` 每次都核一遍私有 manifest 的 mtime）。

## 2. 源与条款

条款核实与原文存档见 `ops/terms/baostock/`（五份，含抓取时间与响应 sha256）与
`ops/tickets.md` 的 N-66。**结论**：五份条款全部治理「交易技术商城」这个知识付费平台，
**没有一条**讲通过行情 API 取得的数据能不能再分发；离得最近的一句是免责声明第 5 条，
措辞是**默认禁止**。PyPI 上 `baostock` 标的 BSD 是**客户端库**的许可，不是数据的条款。
所以默认发布形态是**构建脚本 + 校验和，用户自建**（卡 2.5 §9 的第二种）。

**拉数纪律**（三次拉取都遵守，判据写在代码里不是写在注释里）：
北京时间工作日 09:00–15:30 **拒绝启动**；每请求留 0.3 秒间隔；一只票一个 parquet，可续跑。

## 3. 覆盖面：三处「公开通道的 all 不等于私有通道的 all」

1. **只建 v1 并集 3,575 只**，不是全市场 5,817 只（N-68 裁定：全市场留 v1.1）。
   于是公开 provider 的 `instruments/all.txt` 是 **3,575 行**，私有是 **5,813 行**，
   丢掉的 2,238 个码逐一记在 `qlib_provider/manifest.json` 的 `instruments.dropped_codes`
   里 —— **不静默丢**：静默丢的表现是「两条通道的 all 宇宙不一样，而没人知道」。
2. **三个基准宇宙（csi300/csi500/csi1000）的 instruments 与私有通道逐行相同**
   （1,507 / 3,025 / 4,455 行，`diff` 无输出）。成分 PIT 取的是同一份 `universe_pit`
   —— 那是**定义面**，不是行情数据（卡 2.5 §1 第 4 项的裁定）。
3. **baostock 不服务北交所**（N-70）。三个宇宙里本来就没有北交所，所以 v1 不受影响；
   但「公开通道能建全市场」这句话是**假的**，v1.1 要正面处理。

## 4. 七项依赖各自落在哪

| # | 依赖 | 公开通道的来源 | 落点 |
| --- | --- | --- | --- |
| 1 | 日线 OHLCV / amount | `query_history_k_data_plus(adjustflag=3)` | `tables/daily.parquet`（10,948,502 行）|
| 2 | 复权因子 | `query_adjust_factor`（**事件流**，见 §5.3） | `tables/adj_factor.parquet`（11,327,557 行）|
| 3 | 交易日历 | 3,575 只票日线日期的**并集** | `tables/trade_cal.parquet`（6,417 自然日 / **4,269 个交易日**）|
| 4 | 指数成分 PIT | 私有 `universe_pit`（定义面） | `qlib_provider/instruments/*.txt` |
| 5 | 上市 / 退市 | `query_stock_basic`（一次请求 8,940 行，筛 `type=1` 得 5,552 只） | `tables/stock_basic.parquet` |
| 6 | 停牌 | 日线行的 `tradestatus=0`（**有行**，见 §5.1） | `tables/suspend_d.parquet`（379,055 行）|
| 7 | 涨跌停价 | **本通道推导**（`snapshots/public/limits.py`） | `tables/stk_limit.parquet`（11,327,557 行）|

**4,269 个交易日**与私有 provider 日历**逐日相同**，因此三个求值右端也相同：
`h=1 → 2026-07-30`、`h=5 → 2026-07-24`、`h=20 → 2026-07-03`。

## 5. 陷阱清单（**公开通道自己的**）

### 5.1 停牌是「有行」不是「缺行」——差异被吸收在一处

baostock 在停牌日**照样给一行**：`tradestatus=0`，`volume`/`amount` 为 0，
OHLC 是 `preclose` 的复读。私有湖在那一天是**缺行**。

本通道的处置：`tradestatus=0` 的行**从 `daily` 里拿掉、写进 `suspend_d`（`suspend_type='S'`）**，
`tradability` 因此得到与私有通道同构的三态。代价是 `suspend_basis='suspend_d_S'`
在公开通道的含义是「当天 baostock 说 `tradestatus=0`」，**不是**私有 `suspend_d` 的 S 行 ——
这句话写在 parquet 的 schema metadata 里，跟着文件走。

**不这么做会怎样**：把那 379,055 行当行情搬进来，`classify` 会判成 `trade`
（有行、没封板），而私有通道那天是 `suspend`。数照样算得出来。
`ops/test_public_build.py::test_keeping_the_halt_row_prices_would_have_said_trade`
就是把这个反面钉住的。

**对账**（全量、并集码、全窗口，`ops/reports/public/channel_reconcile.json`）：

| | 行数 |
| --- | --- |
| 公开 `daily` | 10,948,502 |
| 私有 `daily`（并集码、截到冻结线） | 10,948,507 |
| 两边都有 | **10,948,502** |
| **只在公开** | **0** |
| 只在私有 | **5** |

也就是说：**吸收之后，行集合的差异从 N-70 抽样里那种量级掉到了 5 行**。
（N-70 在 200 只抽样上看到 17,770 行「只在公开」，全部是 `tradestatus=0` 的行 ——
那正是这里被路由进 `suspend_d` 的那一族。）

公开 `suspend_d` 379,055 行 vs 私有 `suspend_d` 在并集码上的 `S` 行 347,873 行：
**两个数不该相等**，因为定义不同（一个是「这天没交易」，一个是「发过停牌公告」）。
拿它们对不上当 bug 会走错方向。

### 5.2 `amount` 的亚元取整，以及一处**公开源自己的错**

价格逐值对账（全量 10,948,502 行，判据「到分」/ 相对 1e-6）：

| 字段 | 一致率 | 最大相对差 | 99.9 分位相对差 |
| --- | --- | --- | --- |
| `open` | 0.99999982 | 3.3e-2 | 0 |
| `high` | 0.99999982 | 4.3e-2 | 0 |
| `low` | 0.99999991 | 1.2e-2 | 0 |
| `close` | 0.99999909 | 1.1e-2 | 0 |
| `volume` | 0.99999708 | 2.7e-2 | 9.2e-9 |
| `amount` | **0.99995817** | **4.7e-1** | 1.5e-7 |

`amount` 那 458 行分歧里，绝大多数是**亚元取整**（湖把金额取整到元，公开源保留两位，
方向不固定）；量级上的极端值是 N-70 已经归因过的那一类**公开源单点错误**
（`301279.SZ @ 2022-07-20`：两边 `volume` 完全相同，`amount` 却差 41%，
用 `close × volume` 仲裁 → **私有值自洽、公开值不自洽**）。

**为什么这条要写进数据卡**：`vwap = amount / volume` 是 792 条因子的 7 个消费字段之一。
公开通道**不静默修补**这类行 —— 网关只发 `amount`/`volume`，agent 自己算也会得到同一个数；
在 gold 里修就等于标定口径与评测口径分叉（同 N-20 的处置）。

### 5.3 复权因子：**绝对值不可跨通道比，只有比值有意义**

baostock 的 `query_adjust_factor` 给的是**事件流**（`dividOperateDate` + `backAdjustFactor`），
本通道摊平成逐日值：取 `<= t` 的最后一个事件，之前一律 1.0。

**「之前一律 1.0」只在事件流含上市日那条时成立** —— 所以拉取窗口是 **1990-01-01 起**，
不是 2009-01-05。只从 2009 拉的话 `sh.600000` 的第一条是 `2.969727`
（1999 上市，之前的除权被起始日截掉），「之前是 1.0」当场变成一个系统性错的假设，
而价格照样算得出来。`test_truncated_event_stream_would_silently_shift_everything` 钉住这条。

两条通道的 `adj_factor` **绝对值不同**（不同源各有各的基准）。实测 5 只样本票在
2026-07 的比值：`000001.SZ` 0.89859（1 个取值）、`002415.SZ` 0.99999（1 个）、
`300750.SZ` 1.00011（1 个）、`600000.SH` 0.769216~0.769218（2 个，跨度 2.5e-6）、
`688111.SH` 0.999738~0.999748（2 个，跨度 9.3e-6）。

**结论**：`/adj` 的数值**不能跨通道直接比**；能比的是 `adj(t)/adj(t₀)`，
而 provider 用的正是这个比值（`factor = adj(t)/adj(L_c)`），所以复权后的价格可比。

### 5.4 涨跌停：推导是对的，但有**一条规则推不出来**

`snapshots/public/limits.py` 的八条规则在私有 `stk_limit` 上核过（N-67：763,301 行零分歧）。
这次核的是**整条流水线**（缓存 → 归一化 → `days_listed` → 哨兵编码 → 落盘），
窗口 2026-01-01..07-31、并集码：

* 可比行 **466,773**；
* 两边都有价的行 **466,756**，**逐分相等 466,756，一致率 1.00000000**；
* 「无涨跌幅限制」判定分歧 **4 行**（8.6e-6）。

那 4 行全部是**退市整理期首日**（`600193.SH`/`600608.SH` @20260608、
`600636.SH`/`600696.SH` @20260601，与私有 `namechange.change_reason='退市整理期'`
的 `start_date` 逐条对上）。判据 `namechange` 是**私有表**，公开通道没有 ——
**这条规则在公开通道上推不出来**。不用名字近似：命名规则两个交易所相反
（深/北后缀「退」、沪前缀「退市」），按名字判会整个漏掉沪市（N-67 踩过）。

**「无限制」的编码**：公开 `stk_limit` **照抄私有那套哨兵**
（沪 `99999.999/0.01`、深 `999999.999/0.01`、北 `99999.99/0.0`）。
写 `null` 的话，网关既有的哨兵识别会给出 `no_price_limit=false` 且 `up_limit=null`，
语义直接矛盾（「有限制但不知道多少」）。

其余两条容易漏的规则（都已实现）：**ST 的 5% 带 2026-07-06 起取消**；
**新股无限制窗口沪深 5 天、北交所 1 天**（本通道无北交所）。

### 5.5 `tradability` 与私有通道**逐行相同**（2026 年）

| | 值 |
| --- | --- |
| 行数（公开 / 私有，并集码、截冻结线） | 466,773 / 466,773 |
| 只在一边的行 | **0 / 0** |
| `status` 一致 | **466,773（1.000000）** |
| 其中 `suspend` | 853 |
| 其中 `limit_up` / `limit_down` | 8,374 / 3,118 |

`limit_up` / `limit_down` 的判定要用到**推导出来的涨跌停价**，所以这张表同时也是
§5.4 的端到端验收。明细见 `ops/reports/public/tradability_reconcile_2026.json`。

### 5.6 交易日历只到冻结线，而且只有一种口径

* 公开 `trade_cal` 覆盖 2009-01-05..2026-07-31 的**每一个自然日**（6,417 行），
  `is_open` 说明开不开市，其中 **4,269 天开市**；
* 私有 `trade_cal` 里有 **153 行未来日历**（到 2026-12-31），公开通道**没有** ——
  公开源的日历是从行情反推的，冻结线之后没有行情，也就没有日历。
  凡是要「知道 8 月 3 日是不是交易日」的逻辑（T+N 对齐），在公开通道上取不到答案。
* `exchange` 一律写 `SSE`：**深市沿用沪市日历是本项目的约定，不是数据事实**
  （与私有通道同一条约定，网关的 `caveat` 原样透出）。

### 5.7 单位：**不需要归一**，但这条必须每次都验

baostock 的 `amount` 已经是**元**、`volume` 是**股**。判据不是查文档，是那条硬判据
`low <= amount/volume <= high` 的行占比：**公开 daily 全表 10,948,502 行，ratio 0.9999370**
（中位 `vwap/close` 0.99992）。差 1000 倍时这个比率是 **0%**。
这道门每次建表后自动跑（`--step gate`），不过就停。

### 5.8 `stock_basic` 是**当前快照**，不是 PIT

`query_stock_basic` 给的是「现在」的上市状态与名称。上市日（`ipoDate`）是历史事实、
可以放心用；**名称与退市状态不是** —— 本通道只用它取 `list_date`（新股窗口）与
在市区间（`tradability` 的行域），**没有**用名字判 ST（ST 用日线里的 `isST` 列，那一列是逐日的）。

### 5.9 `/fundamentals` 在公开通道**拒绝**

理由不是「暂时没建」：baostock 的季频财务**无 `f_ann_date`**，而 v1 的 PIT 判据是
`f_ann_date IS NOT NULL AND <= as_of` 且**明令禁止** `coalesce(f_ann_date, ann_date)`
（那是全市场级前视泄漏）。所以「用公开源补一份财务表」这条路**不成立**（N-58①）。
公开网关对 `/fundamentals` 返回 **403** 并把这条理由写进 `access_log`（`decision=deny`，
`reason=dataset_not_exposed_in_v1`，`extra.channel=public`）—— 只拒不记的话，
卡 5.1 的越权率会漏掉这一整族。

### 5.10 拉数时会话会掉，而症状看起来像数据问题

实测：连拉 2,012 只之后，接下来**每一只**都失败。不是那些票有问题，是 baostock 的会话掉了。
第一版把它们一条条记进失败清单、还继续跑完剩下的 1,500 只 ——
**失败清单读起来像数据问题，其实是连接问题**。现在连续失败 5 次即重登，重登后仍失败才算真失败
（`snapshots/public/fetch_adj.py::RELOGIN_AFTER`）。

## 6. 端点级对账（5 只样本票，2026-07-01..07-31）

公开网关 18081 vs 私有网关 18080，同样的参数：

| 端点 | 结果 |
| --- | --- |
| `/calendar` | `data` **逐字节相同**（31 行）|
| `/universe` | 成员**逐个相同**（csi300，300 只）|
| `/bars` | 115 行、键与列完全相同；`status`/`suspend_basis`/`has_daily`/四个 `limit_*`/`no_price_limit`/`in_listing_window` **115/115 相同**；`open/high/low/close` **逐值相等**；`volume` 最大相对差 1.4e-16；`amount`/`vwap` 最大相对差 **1.0e-9**（中位 1.3e-12）|
| `/limits` | 115 行，`up_limit`/`down_limit` **115/115 逐分相等**，`no_price_limit` 全同 |
| `/tradability` | 5 只票 `status` 全同 |
| `/adj` | 115 行；**绝对值不同**（见 §5.3），比值逐票近似常数 |
| `/fundamentals` | **403**（私有通道 200）|

## 7. 复现

```bash
export GENEBENCH_ROOT=/data/shared/genebench
cd $GENEBENCH_ROOT/repo && ulimit -n 8192

# ① 建（可续跑；每步落 state/<step>.done）
$GENEBENCH_ROOT/env/bin/python ops/build_public_channel.py            # 全部
$GENEBENCH_ROOT/env/bin/python ops/build_public_channel.py --dry-run  # 只看要做什么

# ② 起公开网关（18081），跑完自己停；拿网关锁
ops/public_gateway.sh run -- <你的批处理命令>
ops/public_gateway.sh start | status | stop

# ③ 测试
$GENEBENCH_ROOT/env/bin/python -m pytest ops/test_public_build.py ops/test_public_limits.py -q
```

### 7.1 六个端点各一条 curl（**这份手写清单就是 schema**）

网关**刻意**关掉了 `/docs` / `/redoc` / `/openapi.json`（`gateway/app.py` 里三个都是
`None`：少一个可探测面）。所以在线问不到 schema —— 这一节就是那份 schema，
改端点必须同时改这里。红队 2026-09-07 的原话：源码拼参数拼得出来，但
「没有任何一处文档写出六个端点怎么调」。

base URL 从起停脚本那一行取（`channel=public host=… port=…`），或者直接问配置：

```bash
GB=/data/shared/genebench; PY=$GB/env/bin/python; cd $GB/repo
ops/public_gateway.sh status          # 打印 channel/host/port，起着的话还打 /healthz
H=$($PY -c 'import genebench_config as c; print(c.GATEWAY_HOST)')
P=$($PY -c 'import genebench_config as c; print(c.GATEWAY_PUBLIC_PORT)')
BASE="http://$H:$P"
```

六个数据端点各一条，外加 `/healthz` 与一条**必 403** 的反例（全部实测，见本节末）：

```bash
curl -sS "$BASE/healthz"
curl -sS "$BASE/bars?as_of=2026-07-31&code=600000.SH&start_date=2026-07-01&end_date=2026-07-31"
curl -sS "$BASE/calendar?as_of=2026-07-31&start_date=2026-07-01&end_date=2026-07-31"
curl -sS "$BASE/adj?as_of=2026-07-31&code=600000.SH&start_date=2026-07-01&end_date=2026-07-31"
curl -sS "$BASE/tradability?as_of=2026-07-31&code=600000.SH&date=2026-07-31"
curl -sS "$BASE/limits?as_of=2026-07-31&code=600000.SH&start_date=2026-07-01&end_date=2026-07-31"
curl -sS "$BASE/universe?as_of=2026-07-31&universe=csi300&date=2026-07-31"
curl -sS "$BASE/fundamentals?as_of=2026-07-31&code=600000.SH"   # 公开通道必 403，见 §5.9
```

参数语义与必填性（判定只有一份实现：`gateway/asof.py`，各端点不自己写）：

| 参数 | 语义 | 必填 | 不给 / 给错会怎样 |
| --- | --- | --- | --- |
| `as_of` | 视角日期，**只认** `YYYY-MM-DD` 或 `YYYYMMDD` | **每个端点都必填** | 缺 → 422 `asof_missing`；形态不对 → 422 `asof_malformed`；晚于冻结线 `2026-07-31` → 403 `asof_beyond_freeze_line` |
| `code` | 湖内形态 `600000.SH`（六位 + `.SH`/`.SZ`，会 upper 与去重排序）；**可重复**（`&code=000001.SZ&…`） | `/bars` `/adj` `/limits` `/tradability` **至少一个** | 缺 → 422 `param_malformed`；形态不对 → 422 `param_malformed` |
| `start_date` | 区间起 | 否 | 不给按 `19900101` |
| `end_date` | 区间止，**必须 ≤ as_of** | `/bars` `/adj` `/calendar` `/limits` **必填** | 不给 → 403 `open_range_would_cross_asof`（**不接受开区间**：「到最新为止」在 as_of 视角下未定义，静默夹紧等于替调用方做了个它没声明的决定）；晚于 as_of → 403 `range_end_after_asof` |
| `date` | 单日（`/tradability` `/universe`） | 否 | 不给取 as_of；晚于 as_of → 403（`target_date_after_asof` / `universe_asof_after_asof`） |
| `universe` | `/universe` 专用：`csi300` / `csi500` / `csi1000` / `all` | **必填**（`Query(...)`） | 缺 → **422** `{"type":"missing","loc":["query","universe"]}`（FastAPI 自己报的，没有 reason 码）。猜不出来就是这个 |
| `scope` | `/universe` 的口径，默认 `canonical` | 否 | 默认 `canonical` |
| `fields` | `/bars` 的列裁剪，逗号分隔 | 否 | 不给给全列；键列 `code/date/status` 永远在 |
| `mode` | `/adj` 的口径，**只答** `adj_factor` | 否 | `bfq`/`hfq`/`qfq` 一律拒：`adjustment_mode_not_in_v1`（§5.3） |

单次上限 **200,000 行**（超了 422：缩窗口或指定 `code`）。

**实测（2026-09-07，公开实例 18081，`ops/public_gateway.sh run --` 里逐条照抄上面那八行）**：

| 端点 | HTTP | 回了什么 |
| --- | --- | --- |
| `/healthz` | 200 | `channel=public`，`tables_dir=snapshots/public_v1/tables` |
| `/bars` | 200 | 23 行 |
| `/calendar` | 200 | 31 行（带 SSE 日历的 caveat，见 §5.6） |
| `/adj` | 200 | 23 行，`mode=adj_factor`，`adj_factor=12.763991` |
| `/tradability` | 200 | 1 行（`code`/`date`/`status` 等一行全字段） |
| `/limits` | 200 | 23 行，`sentinel_rows=0`（无哨兵行） |
| `/universe` | 200 | `csi300`，`size=300` |
| `/fundamentals` | **403** | `dataset_not_exposed_in_v1`（§5.9：不是「暂时没建」） |

三条**失败**语义也各验了一次（写清单不验反面，等于没写）：

| 少给什么 | 实测 |
| --- | --- |
| `/universe` 不给 `universe` | **422** `{"type":"missing","loc":["query","universe"]}` |
| `/bars` 不给 `end_date` | **403** `open_range_would_cross_asof` |
| `/bars` 不给 `as_of` | **422** `asof_missing` |

探测脚本（自带网关锁，跑完自动停网关）：`ops/public_gateway.sh run -- <脚本>`；
本次那一份留在 `$GB/scratch/1.rt/probe_doc.sh`，输出在 `$GB/scratch/1.rt/probe.log`。

**用时**（f01，2026-09-06 实测）：

| 步 | 用时 |
| --- | --- |
| 拉复权因子（3,575 只，含一次掉线重来） | **26.5 分钟**（15.1 + 11.4） |
| 拉 `stock_basic`（1 次请求） | 37 秒 |
| 建六张表（含涨跌停逐行推导 1,132 万行） | **3.4 分钟** |
| 单位门（全表） | 0.8 秒 |
| `tradability` 18 个年分区 | 31 秒 |
| qlib provider（3,575 × 8 = 28,600 个 bin） | **60 秒** |
| 出集自检 | 20 秒 |
| **合计（不含拉数）** | **约 5.3 分钟** |

（日线那一轮不在这里：3,575 只 × 全窗口是 N-68 做的，约 7 小时。）

**产物**（都不进 git，每个目录带 `MANIFEST.sha256` + `build_info.json`）：

```
$SNAPSHOTS/public_v1/tables/         6 张表
$SNAPSHOTS/public_v1/tradability/    year=2009..2026，11,327,560 行
$SNAPSHOTS/public_v1/qlib_provider/  28,606 文件 / 346 MB / files.sha256 根 561348660a3175b1…
$SNAPSHOTS/public_v1/build/          quotes.parquet（中间产物，不是交付面）
$SNAPSHOTS/public_v1/state/          断点标记
```

## 8. 还没做的（登记，不是遗忘）

| # | 事项 | 影响 |
| --- | --- | --- |
| 1 | 全市场（5,817 只）没建 | 公开通道的 `all` 宇宙 ≠ 私有的 `all`；v1.1 |
| 2 | 退市整理期首日无限制推不出来 | 半年 4 行（并集码内），`limit_*` 判定偏严 |
| 3 | gold / τ / ε 没在公开通道上重算 | 卡 2.5 §5 的重建链，本卡只到数据面 |
| 4 | 发布包（冻结包 / 构建脚本两种形态）没打 | 卡 2.5 §9 |
