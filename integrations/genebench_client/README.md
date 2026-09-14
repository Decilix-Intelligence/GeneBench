# `genebench-client` —— 被测系统的取数垫片

> 把 `import yfinance` / `import tushare` / `import akshare` 换成本包的兼容层，
> 取数就自动**经网关、带身份、受 as_of 约束、落 access_log**；
> 新闻 / 财务 / 资金流一律 `NoData`，**并且在网关日志上留痕**。

**接口定义在范式层，接入责任在被测方。** 本包是范式层给出的一件工具，不是
为哪一个系统写的适配器 —— 谁都可以装、装了就满足取数纪律。

---

## 1. 三分钟上手

```python
import genebench_client as gb
from genebench_client.compat import yfinance as yf
from genebench_client.compat import tushare as ts
from genebench_client.compat import akshare as ak

gb.set_as_of("2026-06-30")          # ← 从 /task/INSTRUCTION.md 的固定槽读来（task.yaml 不在容器里），**启动时做一次**

px  = yf.download(["600000.SS", "000001.SZ"], start="2026-06-01", end="2026-06-30")
bar = ts.pro_api().daily(ts_code="600000.SH", start_date="20260601", end_date="20260630")
his = ak.stock_zh_a_hist("600000", start_date="20260601", end_date="20260630", adjust="qfq")
```

改不了 import 的系统可以顶替 `sys.modules`：

```python
import genebench_client.compat as compat
compat.install()                    # 之后 `import yfinance` 拿到的就是垫片
```

> `install()` 是**便利不是保证**：已经 import 过 `yfinance` 的模块持有旧对象，
> 顶替对它无效。正路仍然是改 import。

### `as_of` 从哪来

优先级：**调用时显式传** > `gb.set_as_of()` > 环境变量 `GENEBENCH_AS_OF`。
三个都没有 → 抛 `AsOfRequired`，**不猜**。猜出来的值会让越界变成合法请求，
而产物上完全看不出来。

⚠️ **runner 目前不注入 `GENEBENCH_AS_OF`**（compose 模板里没有这一行，实测）。
所以容器里正常的做法是启动时**从题面固定槽读出来**再 `gb.set_as_of(...)` ——
`/task/INSTRUCTION.md` 的 `as_of:` 槽（`task.yaml` 不在容器里，`integrations/README.md` §1④）。
可抄的读法见 `integrations/example_minimal/run.py` 里的 `slot(text, "as_of")`。
（已登记 `ops/tickets_inbox/2.2.md` 的 N-?，由编排方决定要不要让 runner 注入。）

### 网关地址与身份

都从环境变量取，**容器里由 compose 注入，不用管**：

| 变量 | 用途 |
| --- | --- |
| `GENEBENCH_GATEWAY`（或 `GENEBENCH_GATEWAY_URL`） | 网关 base URL |
| `GENEBENCH_TASK_ID` / `GENEBENCH_CONFIG_ID` / `GENEBENCH_RUN_ID` / `GENEBENCH_ARM` | 身份头 |

身份头由**边车**在网关入口剥掉重注（卡 4.3 §6.5），所以垫片填什么都改不了日志里的
切片键；填它是为了在没有边车的场合（f01 直跑、单元测试）日志照样能切片。
**切片键是 `run_id`。**

---

## 2. 装进接入镜像

统一基座是 `gb-base:bookworm-r1`。**本包不走 exec 树**（exec 树是 runner 的，
不进任务容器），只走镜像。两种写法，选一种：

```dockerfile
# ── ① COPY + pip install（推荐：镜像自包含，运行期不需要出网）
FROM gb-base:bookworm-r1
COPY genebench_client/ /opt/genebench_client/
RUN pip install --no-cache-dir --no-index --no-build-isolation /opt/genebench_client
```

```dockerfile
# ── ② 可编辑安装（改垫片不用重建镜像；只在调试时用）
FROM gb-base:bookworm-r1
COPY genebench_client/ /opt/genebench_client/
RUN pip install --no-cache-dir -e /opt/genebench_client
```

构建在 **f02**（f01 没有容器运行时）。构建上下文里要有本目录：

```bash
# 在 f01
scp -r /data/shared/genebench/repo/integrations/genebench_client \
       ljn@192.168.1.219:/data/genebench_runner/build/<你的接入>/genebench_client
# 在 f02（经 f01）
cd /data/genebench_runner/build/<你的接入> && docker build -t <你的镜像>:r1 .
```

**不要 `pip install genebench-client` 去公网拿** —— 它不在任何 index 上，
而且运行期装包被卡 4.1 §3.4 明令禁止（那会把包仓库放进出向白名单）。

依赖只有 `pandas` / `numpy`（基座里已有）。HTTP 走标准库 `urllib` ——
少一个依赖就少一次「运行期 pip install」的理由。

容器里 `HTTP_PROXY` / `HTTPS_PROXY` 指向边车，`NO_PROXY` 含 `gateway`，
所以对网关的请求**不走代理**，`urllib` 的默认行为已经是对的，不用配。

---

## 3. 有什么 / 没有什么

### 网关直连（`genebench_client.gateway.Client`）

六个数据端点 `bars` / `adj` / `calendar` / `limits` / `universe` / `tradability`，
五个模拟盘端点 `sim_state` / `sim_order` / `sim_cancel` / `sim_advance` / `sim_log`。
全部返回 `DataFrame`（ISO 日期、湖写法代码 `600000.SH`）或 `dict`。

```python
cli = gb.client()
df  = cli.bars(["600000.SH"], "2026-06-01", "2026-06-10", fields=["close", "volume"])
```

> `fields` **显式传**。不传等于「读了全部列」—— S3 的「声明读取集 vs 实际读取集」
> 探针从 access_log 里反推出来的就是全表。

> **产出文件不经垫片。** S2/S3/S7 的题面会点名一个产出文件
> （`/task/panel.csv` / `/task/values.parquet` / `/task/ledger.parquet`），
> `emit` 只写 `artifact.json`，那个文件要你自己按题面的规范序列化落盘 —— 见 §7.3。

**`/fundamentals` 不在客户端里。** 它在网关白名单里真实存在，但 v1 的题面
不发放它（N-58① 裁定）；垫片把它接上就是「题面没说有、工具却递到手里」。
`ts.income(...)` 一类走 `NoData`，且**不会**去打 `/fundamentals`。

### 异常

| HTTP | 异常 | 什么时候 |
| --- | --- | --- |
| 403 | `LookaheadDenied`（带 `.reason` / `.context`） | 越过 as_of / 冻结线 / 越权 |
| 422 | `MalformedRequest` | 参数写错（也包括垫片自己判出来的，如 `interval="1m"`）|
| 402 | `BudgetExceeded` | **本项目里没有东西返回 402** —— 预算闸实际是 429 `RateLimited`（`budget_exceeded`，`P2_CONTRACT.md` §4.5）。这一档只是留着的映射位，别照它写 `except BudgetExceeded` 分支 |
| 429 | `RateLimited` | 限流 |
| — | `AsOfRequired` | 没有 as_of |
| — | `NoData`（带 `.kind` / `.api` / `.traced`）| 本环境没有这类数据源 |
| — | `GatewayUnreachable` | 连不上（**与"被拒绝"严格分开**）|

### `NoData` 与留痕

`NoData` 不是"出错了"，是**一个事实的类型化表达**：本环境不提供新闻 / 财务 /
资金流 / 内部人交易 / 分红拆股明细 / 股东数据 / 宏观指标。

每一次 `NoData` **之前**，垫片会打一次
`GET /nodata/<kind>?as_of=…&api=…&kind=…`。那是网关白名单之外的路径，
所以是 404 —— 而 `gateway/app.py` 的日志中间件**对未匹配路由同样记账**
（2026-09-06 在生产网关上实测）。于是 `$GB/logs/gateway_access.jsonl` 里得到：

```json
{"path": "/nodata/news", "params": {"kind": "news", "api": "yfinance.Ticker.news",
 "as_of": "2026-06-30"}, "decision": "deny", "reason": "unclassified", "status": 404}
```

**为什么非留不可**：只抛不留痕的话，「被测系统尝试去拿新闻」这件事在数据面上
什么都没有 —— 与「它根本没想过要新闻」不可区分。卡 5.1 的结算只认 access_log。

网关连不上时降级写容器内 `/task/log/client_nodata.jsonl`
（或 `GENEBENCH_CLIENT_NODATA_LOG` 指定的路径），`NoData.traced` 会是 `False`。
**网关记得下时不写第二份** —— 两份记录必然漂，而漂的表现是「两边对不上，且都自称权威」。

### 未实现的接口一律 fail-closed

`yf.<任何名字>` / `ts.<任何名字>` / `pro.<任何名字>` / `ak.<任何名字>`
都是**可调用的**，调下去抛 `NoData` 并留痕，**不是 `AttributeError`**。
`AttributeError` 会被上游的 `hasattr` 能力探测静默吞掉，然后回落到**原生数据源** ——
那条路一走，access_log 干干净净而 as-of 强制已经失效。

---

## 4. 已知语义差异（**都是必要偏离，不是没做完**）

### 单位：湖是 **股 / 元**，tushare 原生是 **手 / 千元**

实证结论，不是查文档。2026-09-06 在生产网关上复核 `600000.SH @ 2026-07-28`：
`close=9.19`、`volume=102,060,442`、`amount=934,214,852` →
`amount/volume = 9.15` ≈ 每股价格。若 `volume` 真是"手"，每股价就会是 91.5 ——
差 10 倍，一眼可判。（同一结论另见 `ops/tickets.md:2457`、
`ops/data_cards/qlib_provider.md`。）

| 兼容层 | 成交量 | 成交额 |
| --- | --- | --- |
| `compat.yfinance` `Volume` | **股**（原样） | — |
| `compat.tushare` `vol` / `amount` | **手** = `volume/100` | **千元** = `amount/1000` |
| `compat.akshare` `成交量` / `成交额` | **手** = `volume/100` | **元**（原样） |

不换算的后果是任何换手率 / 成交额口径静默差 100×/1000×，而没有任何东西会报错。

### 逐层

| 兼容层 / 字段 | 差异与原因 |
| --- | --- |
| `yf` `Adj Close` | yfinance 的基准是相对**今天**的。as-of 世界里没有"今天" —— 拿冻结线之后的因子当基准就是前视。这里的基准是**窗口内 as_of（含）之前最后一个 `adj_factor`**，逐票各算各的。|
| `yf` `end` | **右开**（与 yfinance 一致）。网关的 `end_date` 是闭的，所以垫片减一天。漏了这条会多/少一根 K 线，而没有任何东西会报错。|
| `yf` 默认窗口 | `start` 与 `period` 都不给时取 `period="1mo"`，**不是** yfinance `download` 事实上的 `"max"` —— as-of 世界里 max 会拉几十年、直接撞网关 200,000 行上限（422），表现成「参数写错了」。|
| `yf` 无 `Dividends` / `Stock Splits` | 网关只发合成的 `adj_factor`，没有分红/拆股明细。**不编两列 0.0** —— 那等于宣称"这段时间没有分红"。|
| `yf` 停牌日 | 无行情的交易日不出现在结果里（与 yfinance 一致）。要停牌语义请用 `gb.client().bars(...)`，那里 `status` 五档显式。|
| `ts` `daily` | **没有** `pre_close` / `change` / `pct_chg` —— 网关不发 `pre_close`（湖里 `stk_limit.pre_close` 全 NULL）。拿前一日收盘去减，在除权日就是错的，**不现编**。|
| `ts` `stk_limit` | 没有 `pre_close`；**多一列** `no_price_limit`。为真时 `up_limit`/`down_limit` 是 `null`（哨兵编码，本来就没有涨跌停价）—— **绝不要把哨兵当真实涨停价**。|
| `ts` `index_weight` | **没有 `weight` 列**。`/universe` 只发 PIT 成分，不发权重。给一列 NaN 会让 `weight.sum()` 静默变 0，所以这里让它 `KeyError`：响的错，不是哑的错。|
| `ts` `suspend_d` | 由 `/tradability`（单日）或 `/bars` 的 `status`（区间）派生。`suspend_type` 只给 `'S'`；**不给 `'R'`**（复牌）—— 五档 `status` 里没有"复牌"这一档，推出来的会是我们编的。|
| `ts` / `ak` 日历 | 只有 **SSE**。深市沿用 SSE 日历是本项目的约定，**不是数据事实**。|
| `ak` `stock_zh_a_hist` | 没有 `振幅` / `涨跌幅` / `涨跌额` / `换手率` —— 要 `pre_close` 与流通股本，网关都不发。`period` 只支持 `daily`（周/月线要重采样，口径是我们编的）。|
| `ak` `stock_zh_a_spot` | "实时" = **as_of 当日**。列只有网关能给的那几个（没有 `名称` / `涨跌幅` / `市盈率`）。⚠️ 要先取 `/universe(all)`（约 5,500 只）再分批取 `/bars`，**约 20 次网关请求**，注意预算。|
| compat 的 `fields` | **只裁剪返回值，不改变网关上的读取集。** 三层一律按上游库的完整列集向网关请求 `fields`：`pro.daily(fields="ts_code,trade_date,close")` 返回 3 列，access_log 里那条 `/bars` 的 `params.fields` 仍是 `open,high,low,close,volume,amount`；akshare 同理。`declared_reads` 探针只看 access_log，所以 **S3 类任务经 compat 层取数就控制不了声明读取集**，必须改用 `gb.client().bars(codes, start, end, fields=[...])`（`P2_CONTRACT.md` §2.4）。|
| 复权口径 | `ts.daily` 的 `close` 与 `ak(adjust="")` = **不复权**（`declarations.adjust` 写 `none`）；`ak(adjust="qfq")` / `ak(adjust="hfq")` = 垫片**在本地按 `/adj` 的 `adj_factor` 自己算**（写 `pre` / `post`）。网关**不发**这两个口径（`qfq`/`hfq` 一律 403 `adjustment_mode_not_in_v1`）—— 禁的是向网关要另一个口径，本地自己算是允许的。`yf` 的 `Adj Close` 基准见本表第一行。**声明与实际口径不符是 `declaration_mismatch` 违例，不是畸形。**|
| 全部 | **越界窗口不由垫片截回。** 显式给的 `end` 越过 as_of 时原样送到网关，由网关判 403 —— 垫片自己截会让那次前视尝试在 access_log 上消失，而卡 5.1 的结算只认 access_log。|

---

### 写法归一：题面夹具与网关**不同源**

网关一路用的是**湖写法**：日期 `2026-01-05`、代码 `600000.SH`。
但题面 `inputs[]` 发下来的**因子面板**（S3/S5 的 `gtja_191.*.parquet`）用的是
**紧凑日期 + qlib/面板写法**：`20260105`、`SH600000`。

```python
>>> pd.read_parquet("/task/inputs/gtja_191.001.parquet").head(1).to_dict("records")
[{'date': '20260105', 'code': 'SH600000', 'value': -0.6397...}]
```

**把两边直接 join 会得到一张空表，而且 join 本身不报错。**
下游的表现取决于你怎么写：卡 2.7 的演练里，它表现为「产物是一张全 `null` 的面板」——
因为每个格子都查不到因子值，于是每个格子都判「输入因子全空 → 写 `null`」，
**产物合规、覆盖统计自洽、一眼看不出哪里错了**。

归一函数就在本包里，**在取数边界做一次**：

```python
from genebench_client.codes import iso_date, to_lake
key = (iso_date(row["date"]), to_lake(row["code"]))     # ('2026-01-05', '600000.SH')
```

`to_lake` 认全部四种写法（湖 / yfinance `.SS` / akshare 裸六位 / qlib `SH600000`），
`iso_date` 认紧凑与 ISO 两种。**别自己写一份** —— 各写一份必然漂。

## 5. qlib provider 树

**不重写，也不从网关现造。** 现成的适配层是：

* 规格 `ops/specs/card_4.3_two_arm_injector.md` §7（PA-1..PA-6）；
* 物化与核根 `runner/provider_adapter.py::materialize()` / `place_for_arm()`；
* 用法示例 `runner/c42/adapters/rdagent_q/adapter.py`（`PROVIDER = "/task/provider"`）。

**PA-6：provider 物化在注入期（f02 runner 侧，可信方），不在容器里** ——
容器里跑物化 = 让不可信方决定自己拿到什么数据。到了容器里它已经是一份
**核过根的既成事实**，被测系统只需要知道它在哪：

```python
import qlib
from genebench_client import qlib_provider
qlib.init(**qlib_provider.qlib_init_kwargs())     # provider_uri=/task/provider, region=cn
```

路径覆盖用 `GENEBENCH_PROVIDER_URI`（TK-4 备用路径也走它）。
provider 不在时抛 `ProviderMissing`，**不回落到 qlib 社区 channel** ——
那是运行期换数据源（PA-5），而且社区那份 `amount` 是千元、`volume` 是手，
与本环境差 1000× / 100×。

`ensure(dest)` 默认**原地返回不复制**（PA-3：两臂不共享 provider，
复制一份到别处只是多一个可写入口）；给了 `dest` 才复制，复制后核文件数与
总字节数 —— 盘满时 `copytree` 可能只写了一半而返回成功，那是一个**不会抛异常**的错误。
（根的权威校验在 `runner/provider_adapter.py`，容器里不构成第二个权威。）

---

## 6. 测试

```bash
cd /data/shared/genebench/repo && ulimit -n 8192
/data/shared/genebench/env/bin/python -m pytest ops/test_genebench_client.py -q -p no:cacheprovider
```

核心三条判据**真打生产网关**（每条用自己的 `run_id`，很轻，**不需要 `gateway_lock`**）：

1. 经垫片取数后，`access_log` 里本 run 的切片**条数 == 请求次数**且路径逐条对上；
2. 越界 → 网关 403 → `LookaheadDenied`，且 403 落进日志；
3. `NoData` 路径在日志里有 `/nodata/<kind>` 那一行，`params.api` 指出是哪个接口。

另有两条结构判据（不打网络）：垫片**零 `reference/` 依赖**（AST 查 import）、
三方依赖只有 `pandas` / `numpy`。

---

## 7. `emit`：从 DataFrame / dict 构造 `artifact.json`

取数是垫片的上半场，**交产物**是下半场。`genebench_client.emit` 负责把「你算出来的东西」
写成合规的 `artifact.json` —— 格式这一层它全包，业务值一个都不替你想。

```python
from genebench_client import emit

art = emit.emit_s5(
    signals=df,                                    # 列 date / symbol / value（也收 list[dict]）
    declarations={"value_semantics": "rank", "signal_frequency": "daily",
                  "direction": "higher_is_long", "universe_ref": "csi300",
                  "missing_policy": "keep_null", "input_factors": ["gtja_191.001"]},
    as_of="2026-07-31",                            # 或启动时 gb.set_as_of(...)
)
art.write("/task/artifact.json")
```

### 7.1 它保证什么

| 保证 | 说明 |
| --- | --- |
| **三态齐全** | 该阶段契约要求的每个声明字段都在。你没给的、给了 `None` 的，一律写显式 `"unresolved"` —— **不填默认值**。缺失 ≠ 标记；`"unresolved"` ≠ `null`（`null` 是 S5 的「无观点」）。 |
| **依赖图（诚实终止）** | 某个口径被标 `unresolved` 时，依赖它的 payload 字段应当是 `null`。你没给 → 助手写 `null`；你给了完整的值 → 抛 `HonestHaltConflict`（口径不知道还能出数，评分侧是 `computed_despite_unresolved`）。S8 的 `fills.slippage_bps` 是**叶子级**终止，`fill_rate` 不受牵连。 |
| **信封与版本** | `schema_version` 定死 v1.0；`task_id` / `config_id` / `arm` / `artifact_id` 从参数或 compose 注入的环境变量取；`provenance` 一定是列表，自引用当场报错。 |
| **写法归一** | 紧凑日期 `20260731` → `2026-07-31`；`datetime` / `pandas.Timestamp` → ISO；代码 `sh600000` → `600000.SH`；`numpy.int64/float64` → 原生 int/float；`"0.031"` → `0.031`（schema 说 `number` 就不能是字符串）。 |
| **枚举** | 取值不在表里当场报错，且**必须是字符串** —— `{"value": "post"}` 这种包装在评分侧曾静默通过（红队 rt01/rt10）。`S1.fetches[].status ∈ {ok, empty, denied, rate_limited}`，**HTTP 码不是这个枚举**。 |
| **清点** | S5 的 `coverage` 不给就按 `signals` 数出来；给了就核，对不上当场报错（自报统计与内容不符在评分侧是畸形）。S6 的 `delta_weight` 按定义式 `target − previous` 补。 |

### 7.2 它**不**做什么（做了就是替你答题）

* **不猜业务值**：欠定的口径不填默认；S7 少一个指标就报错，**不补 0**
  （`{}` 与 `0` 会被下游 `.get(k, 0)` 读成真 0，直接进阶段均值与排名）。
* **不把 NaN 变成 0 / null / `"flat"`**：碰到 NaN 当场报错。这三件事在 S5 上判法完全不同
  （`0` 是一个数、`null` 是无观点、`"flat"` 是主动空仓），选哪一个只有你知道。
  > **pandas 的坑**：`DataFrame` 的**浮点列**会把你写的 `None` 存成 `NaN` —— 到了 `emit`
  > 这里「我没观点」和「算出来是 NaN」已经分不开，所以它照样报错。要表达无观点，
  > 把那一列转成 object：
  > `df["value"] = df["value"].astype(object).where(df["value"].notna(), None)`，
  > 或者干脆传 `list[dict]`（`emit_s5` 两种都收）。
* **不静默重排**：S8 事件时间倒序 → 报错，不替你排。
* **不改 `params`**：`S1.fetches[].params` 是你真发出去的那次请求，一个字符都不动；
  `fetched_at` 是字符串时原样保留（它要逐字等于某条网关日志的 `ts`）。

### 7.3 八阶段最小示例

```python
from genebench_client import emit
D = dict(as_of="2026-07-31")          # task_id / config_id / arm 由 compose 注入

# S1 取数留痕（status 是四值枚举，emit.fetch 帮你从 HTTP 码或异常推）
emit.emit_s1(fetches=[emit.fetch("/universe", {"universe": "csi300", "as_of": "2026-07-31"},
                                 fetched_at="2026-09-06T01:00:00+00:00", rows=300)],
             fields_obtained=["close", "volume"],
             declarations={"calendar_id": "SSE", "universe": "csi300", "data_version": "v1"}, **D)

# S2 对齐面板（missing_rows 收 {"count": n}，也收一个整数）
emit.emit_s2(panel_ref={"rows": 6300, "sha256": sha}, field_map={"close": "close"},
             missing_rows=12,
             declarations={"adjust": "post", "calendar_id": "SSE", "universe_ref": "csi300",
                           "missing_row_policy": "keep_missing", "alignment_target": "gold_panel_v1"}, **D)

# S3 因子（approximated_operators 必须显式给，通常是 []）
emit.emit_s3(factor_id="gtja_191.001", expression="-1 * ts_rank(close, 20)",
             values_ref={"coverage": 0.98, "sha256": sha},
             nonfinite={"inf_count": 0, "nan_count": 3, "replaced_count": 0},
             warmup=0, approximated_operators=[],
             degeneracy={"is_constant": False, "alert": False},
             declarations={"required_fields": ["close"], "lookback": 20, "eval_frequency": "daily",
                           "operator_semantics": {"ts_rank": "trailing, right-closed"},
                           "param_order": ["window"], "nonfinite_policy": "propagate",
                           "warmup_policy": "null_until_full"}, **D)

# S4 IC（八个键；除 ci_method 外都是数）
emit.emit_s4(ic_stats={"mean": 0.031, "std": 0.12, "icir": 0.26, "positive_ratio": 0.55,
                       "coverage": 0.97, "ci_low": -0.01, "ci_high": 0.07,
                       "ci_method": "block_bootstrap"},
             declarations={"quantiles": 10, "tie_handling": "average", "weighting": "equal",
                           "rebalance_timing": "close", "holding_periods": [1, 5, 20],
                           "ic_method": "spearman", "annualization": 252,
                           "uncertainty_method": "block_bootstrap"}, **D)

# S5 信号（value: 数 / None 无观点 / "flat" 主动空仓；coverage 自动数）
emit.emit_s5(signals=df, declarations={...}, **D)

# S6 目标组合（positions 台账六字段；delta_weight 可省）
emit.emit_s6(targets=[{"date": "2026-07-31", "solver_status": "optimal",
                       "positions": [{"symbol": "600000.SH", "score": 1.0, "previous_weight": 0.0,
                                      "target_weight": 0.5, "reference_close": 9.19}]}],
             cash_ratio=None,                       # N-26 留位：可为 null，但必须存在
             declarations={"constraints": {"long_only": True}, "objective": "max_expected_ic",
                           "weighting_scheme": "equal", "rebalance_frequency": "monthly"}, **D)

# S7 回测（metrics 十一项，turnover 双记；payload.rebalance_frequency 自动回显声明）
emit.emit_s7(metrics=m11, n_days=21, ledger_check=1e-9,
             attribution={"alpha": 0.01, "beta": 0.02, "cost": -0.003, "total": 0.027},
             declarations=s7_decl, **D)

# S8 模拟盘（events 按 ts 单调；overreach 收整数）
emit.emit_s8(events=[{"seq": 1, "ts": "2026-07-03T15:00:00+08:00", "type": "order"}],
             state_transitions=[{"from": "idle", "to": "ordered"}],
             fills={"fill_rate": 0.5, "slippage_bps": 12.5}, overreach=0,
             declarations=s8_decl, **D)
```

**S2 的 `panel_ref` / `field_map` 三句**（`emit` 只管产物那一层，不替你落盘、不替你算摘要）：

* **`panel_ref.sha256` 是「你交出去的那个文件」的字节摘要**：
  `hashlib.sha256(Path(p).read_bytes()).hexdigest()`。**不是**把 DataFrame 重新序列化一遍再算
  —— 重算会引入 pandas / pyarrow 版本差异。口径与写端同源：`genetask/file_contract.py::sha256_of`。
* **面板文件写在题面固定槽「产出文件」点名的路径上**，S2 是 **`/task/panel.csv`**
  （不是 `/tmp`：它是产出物，采集侧的允许集里有它；见 `integrations/README.md` §1④）。
  规范序列化由题面逐字给出，本环境 S2 的契约是：列序 `symbol, date, close, high, low, volume`、
  按 `symbol, date` 升序、首行列名、**不写行索引**、浮点 `%.6f`、UTF-8
  （`genetask/file_contract.py::FILE_SPECS`）。**不要自己定一种** ——
  两个同样正确的实现字节不同时这个摘要就不可比，而它是被比对的量。
* **`field_map` 的方向是「源字段 → 目标字段」**：键是你从网关拿到的列名，
  值是 `alignment_target` 那一套命名；**键列（代码、日期）也要列进去**。
  例：`{"close": "close", "code": "symbol", "trade_date": "date"}`。

### 7.4 欠定的题怎么写

**什么都不做**就是对的：你不给的声明字段，助手写 `"unresolved"`；依赖它的 payload 字段
自动为 `null`。这正是「诚实标记」在协议里的表示。

```python
decl = {...}                                        # 独独不写 sell_rule（题面没给这个口径）
art = emit.emit_s7(n_days=21, declarations=decl, **D)
art["declarations"]["sell_rule"]   # -> "unresolved"
art["payload"]["metrics"]          # -> None（回测跑不完，诚实终止）
```

替它填一个「常见默认值」会被判 `silent_completion`（第五探针）—— 助手没有那条路径，
所以填了一定是你自己填的。

### 7.5 写完自检

协议臂的容器里有 validator，写完跑一遍：

```bash
python3 /task/protocol/validate_artifact.py /task/artifact.json
```

它是评分的**子集**（不含前视/越权这类需要网关日志的探针，也不比数）。
`emit` 保证的正是它管的那一层：`ops/test_emit.py` 里八阶段的最小样例，
**协议 validator 与评分侧 `reference.artifact_schema.validate` 两把尺都是零告警**。

### 7.6 规则从哪来

只有 `genebench_client.emit_schemas.SCHEMAS` —— 它是
`ops/specs/artifact_schema/v1.0/S*.json` 的逐字副本，也就是发给两臂的 `/task/S{k}.json`
与协议臂 `/task/protocol/artifact_schema.json`。**公开规则，不是评分侧知识**；
副本漂移由 `ops/test_emit.py::test_schemas_do_not_drift_from_ops_specs` 盯着。
依赖图直接从 schema 的 `x-nullable-when` 反推，不另抄一张表。

要自己查规则：

```python
emit.declaration_fields("S7")   # 该阶段契约要求的声明字段（键集必须精确等于它）
emit.payload_keys("S5")         # payload 必填键
emit.depends_on("S7")           # {payload 键: 它依赖的声明字段}
```
