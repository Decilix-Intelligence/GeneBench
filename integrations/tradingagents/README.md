# TradingAgents 接入（P2）

**被测方**：[TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)
v0.4.0（commit `2448d0a1`），论文 [arXiv:2412.20138](https://arxiv.org/abs/2412.20138)，
Apache-2.0。多智能体投研框架：四个分析师（行情 / 社交 / 新闻 / 基本面）出报告，
多空研究员辩论，交易员成稿，三档风控复议，最后给出**一条五档评级**。

**范式**：P2（专用系统，自带研究流程与内部数据抽象）。
**镜像**：`gb-tradingagents-u:r1`。**配置**：`cfg-tradingagents-deepseek`（`deepseek-chat`）。
**接的阶段**：**S5（信号）** —— 它一次产出一个标的、一个交易日的一条评级，那就是一格信号。

> 与 `runner/c42/adapters/tradingagents/` 的关系：那一份是同一件事的**上一代**实现
> （自己拼 URL、自己做 PIT 判断）。**v1.0 起以本目录为准**，那一份不删、只作对照。

---

## 1. 数据层怎么接的

替换缝是**上游自己的扩展点**，不是我们凿出来的：
`tradingagents/dataflows/interface.py` 里有一张 vendor 注册表 ——

```python
VENDOR_METHODS = {方法: {厂商: 实现}}      # 11 个方法 × 4 家（yfinance / alpha_vantage / fred / polymarket）
route_to_vendor(method, *args)             # 按 config["data_vendors"][category] 派发
```

`glue/gateway_vendors.py` 的 `install()` 做三件事（**不改上游源码** ——
改了 `pin.json` 的 `commit` 就不再是那份字节）：

| 换什么 | 换成什么 | 为什么在这一层 |
| --- | --- | --- |
| `interface.VENDOR_METHODS`（整张表） | 每个方法唯一可用的 vendor = `genebench_gateway` | `route_to_vendor` 派发**读的就是这张表**。上一代实现换的是 `ANALYST_TOOL_REGISTRY`，红队实测「换了注册表、图仍然执行原生工具」（N-52）—— 门装在了错的层 |
| `interface.VENDOR_LIST` | `["genebench_gateway"]` | `"default"` sentinel（没显式配时）用的是**全部可用 vendor**；不清空这张列表，配置一丢就回到 yfinance |
| `dataflows.config.set_config` 里的 `data_vendors` / `tool_vendors` | 六个 category 全指向我们、tool 级覆盖清空 | `route_to_vendor` 读的是**模块级**配置，不是调用方手里那份 dict。只改调用方那份的后果是 fail-closed（安全方向），但它仍然是「改了一份没人读的配置」 |

**为什么必须是「整表」**：留一个原生实现在表里就是一条**未声明的数据源** ——
网关 `access_log` 会干干净净、前视探针全绿，而 as-of 强制已经失效。
f02 的容器在**构建期**实测能直连 `query1.finance.yahoo.com:443`，所以这不是理论风险。
`assert_only_gateway_vendor()` 就是这条的门，它**在替换之前必须报**
（`ops/test_integration_tradingagents.py::test_the_door_is_red_before_the_replacement`），
否则它证明不了任何事。

取数本身走垫片 [`genebench_client`](../genebench_client/)，不自己拼 URL：
身份头、`as_of` 必填、错误码翻译（403 越界 / 422 畸形 / 429 预算）、
分批、access_log 留痕都由它负责。

### 1.1 哪两个方法有数

| 上游方法 | 走到哪 | 说明 |
| --- | --- | --- |
| `get_stock_data(symbol, start, end)` | `Client.bars(fields=[open,high,low,close,volume,amount])` | 闭区间、两端都给。**越界不预先拦** —— 让网关拒并计进越权率；替换层替网关拒掉，探针就看不见这次尝试 |
| `get_indicators(symbol, ind, curr_date, lookback)` | `Client.bars(...)` + `stockstats` **本地现算** | 指标是计算不是数据源。算不出来返回 `[NO_INDICATOR]` 并说明，**不回退到别的行情源** |

### 1.2 哪九个方法退成 `NO_DATA`

返回一句显式的 `[NO_DATA] 本环境不提供…`，**不是空串、不是编一段话** ——
让「这个环境没有这类数据」在 agent 的上下文里可见，也在网关日志里可见
（垫片每次打一个 `GET /nodata/<kind>`，网关的 HTTP 中间件对未匹配路由同样记账）。

| 方法 | 类别 | 为什么没有 |
| --- | --- | --- |
| `get_news` / `get_global_news` | `news` | 本基准不提供新闻源 |
| `get_insider_transactions` | `insider` | 同上 |
| `get_macro_indicators` | `macro` | 同上（上游走 FRED，需要 key，且是境外源） |
| `get_prediction_markets` | `other` | 同上（上游走 Polymarket） |
| `get_fundamentals` / `get_balance_sheet` / `get_cashflow` / `get_income_statement` | `fundamentals` | **`/fundamentals` 端点存在但 v1 的题面不发放它**（N-58①）。把它接上等于把一件「题面没告诉 agent 它有」的工具递到手里 —— 只摘题面一头会把我们自己造成的诱导记进越权率 |

`build_vendor_table()` 对**上游多出来的方法当场抛**，不静默跳过：
跳过的那一个会留着原生实现，而那正是最看不见的失效。

---

## 2. 配置指向 `/task`

* 题面：`/task/INSTRUCTION.md`（唯一入口）。`glue/run.py` 从固定槽读
  `as_of` / `window` / `universe` 与「本次任务的口径（逐项）」。
  **取不到就退出，不猜默认值** —— 猜出来的 `as_of` 会让越界变成合法请求，
  而产物上完全看不出来。
* 产物：`/task/artifact.json`，由 `genebench_client.emit.emit_s5` 写。
* **落盘一律在 `/tmp`，不进 `/task`**：`TRADINGAGENTS_RESULTS_DIR` /
  `_CACHE_DIR` / `_MEMORY_LOG_PATH` 三个环境变量在 Dockerfile 里改到 `/tmp/ta/*`，
  `HOME` / `XDG_CACHE_HOME` 到 `/tmp/h`。容器里的 `/task` 就是 run dir 的 `work/` 本身，
  往它下面落东西会破 P8 文件集封闭（上游默认落在 `~/.tradingagents/`，
  `logs/` + `cache/` + `memory/` 三处，一次运行会写出几十个文件）。
* `GENEBENCH_AS_OF` **不由 runner 注入**（compose 模板里没有这一行），
  所以入口启动时 `gb.set_as_of(as_of)` 一次，`as_of` 从题面读。

---

## 3. LLM 怎么指

上游用 `langchain-openai`，`TradingAgentsGraph` 从 `config["backend_url"]` 取 base URL。
接线层把它设成 **`OPENAI_BASE_URL`（边车的反向代理）**，`glue/run.py` 里
**没有任何写死的主机名**（`_base_url()` 依次试 `OPENAI_BASE_URL` /
`OPENAI_API_BASE` / `LLM_BASE_URL`，三个都没有就退出）。

provider 选 **`openai_compatible`**，不是 `openai`：

* `openai` 那条会走 OpenAI 的 Responses API 且对模型名做校验；
* `openai_compatible` 是上游给「任意 OpenAI 兼容端点」留的口子
  （`require_base_url=True`、模型名不校验、结构化输出不强推 `tool_choice`），
  正好是边车的形状。
* 它读的 key 变量是 `OPENAI_COMPATIBLE_API_KEY`；容器里只有占位 key，
  入口用 `os.environ.setdefault` 从 `OPENAI_API_KEY` 抄一份过去。
  **真 key 在边车里，容器拿不到也不需要。**

预算：每 run `--max-calls 100`。**一格（一个标的 × 一天）要走完四个分析师 +
多空辩论 + 风控三轮，实测每格数十次调用** —— 所以默认只跑 `GENEBENCH_TA_MAX_CELLS=3` 格。
想跑更多就得同时把 `--max-calls` 提上去，两个数必须一起改。

---

## 4. 已知限制（**这一节是本接入最重要的部分**）

### 4.0 vendor 表**不是**唯一的取数路径（三条缝，本次真跑逐条抓出来的）

这是本次接入最值得记下来的一条：**「整表替换 vendor 注册表」是必要的，但不充分。**
v0.4.0 里通向原生数据源的路一共三条，第一次真跑把后两条一次抓了出来
（三条都记在 `glue/gateway_vendors.py` 的注释里）：

| # | 路径 | 谁走它 | 现在怎么处理 |
| --- | --- | --- | --- |
| 1 | `interface.VENDOR_METHODS` → `route_to_vendor` | 十一个数据工具 | **整表替换**（`install()`）；`assert_only_gateway_vendor()` 守门 |
| 2 | `stockstats_utils.load_ohlcv` → `yf.download` | `@tool get_verified_market_snapshot`（**直接绑给行情分析师，不经 `route_to_vendor`**），经 `market_data_validator` | **换函数**（`install_market_data_seam()`）：`load_ohlcv` 换成经网关的实现，并把持有 `import yfinance as yf` 的五个模块手里的 `yf` 换成一个**任何属性访问都抛**的陷阱；`assert_market_data_seam_closed()` 守门 |
| 3 | `dataflows/stocktwits.py` / `dataflows/reddit.py` 的 `urllib.request.urlopen` | 社交/情绪分析师 | **还没换**（见下）。本次真跑里它被**容器的出向白名单**挡住：`Tunnel connection failed: 403 Forbidden`（CONNECT 允许集是空集） |

第 2 条的现场表现是「三格全挂，报 `NoMarketDataError: Yahoo Finance returned no rows`」。
**之所以是「挂」而不是「悄悄取到了美股行情」，是因为运行期断网** ——
换句话说，拦住它的是隔离，不是我们的替换。在一台能出网的机器上，
同一份代码会安静地拿到 Yahoo 的数据、网关 `access_log` 干干净净，而 as-of 强制已经失效。

第 3 条同理，而且**目前仍然如此**：`stocktwits.py` / `reddit.py` 不在
vendor 表里、也不经 `yfinance`，接线层没有覆盖它们；
本次真跑的 stderr 里能逐条看到 `StockTwits fetch failed …: 403 Forbidden`、
`Reddit RSS fetch failed for r/wallstreetbets …: 403 Forbidden`。
**是出向白名单挡的，不是我们挡的。**
修法与第 2 条同形（把那两个模块的取数函数换成 `NO_DATA`），已登记票据
（`ops/tickets_inbox/2.6-tradingagents.md`）—— **本版没有改**，
因为改了就与 `sha256:d875d084…` 那次真跑的证据对不上，
而「代码与证据对得上」比「多堵一条已经被隔离堵住的路」更重要。v1.1 修并重跑。

> 推广到范式层的一句话：**「被测系统的取数是否全部经过数据面」这件事，
> 不能靠接入者穷举替换点来保证。** 本次三条缝里，接入者自己找到的是第 1 条，
> 第 2、3 条是**真跑 + 容器隔离**告诉我们的。容器的出向白名单不是冗余，
> 它是这条性质唯一的兜底。

### 4.1 产出粒度是一格，题面要的是一张面板

TradingAgents 的产出是 `(标的, 交易日) → 五档评级` 的**一格**。
S5 题面要的是窗口内**每个交易日 × universe 全体**的一张面板
（`s5-eco-01`：csi300 × 2026-01-05..2026-07-31，约 4 万格）。

**我们不替它补格子。** 凑不满是**事实**，由评分器判；
接入层把剩下的格子填成 0 / 前值 / 随机数，得到的分数就是
「我们替它补了多少」的函数，不是它的能力 —— 而且**没有任何信号会红，分数只是更高一点**。
所以：跑得完几格就交几格，`coverage` 由 `emit` 如实清点，其余的格子根本不出现在 `signals` 里。

**这是这次接入得到的第一个真结论**，不是一个待修的 bug。

### 4.2 五档评级 → 分数

题面（S5 自由题）要 `value_semantics=score`、`direction=higher_is_long`。
五档是**有序**的，映射成有序的数是一次写法转换，不是编值：

```
Buy +1.0 / Overweight +0.5 / Hold 0.0 / Underweight -0.5 / Sell -1.0
```

`REVIEW`（上游自己说「这次的决定没有可解析的评级」）→ **`None`（无观点）**，
不是 0：题面写着「无观点的格子不得补 0」，而 `Hold` 与「没解析出来」含义相反。

### 4.3 它的四个分析师有两个拿不到数据

行情与技术指标经网关；**新闻分析师与基本面分析师**拿到的全是 `[NO_DATA]`。
框架照样会让它们出报告 —— 报告的内容就是「没有数据」。
这会影响它的表现，但那**正是被测量的东西**：一个依赖新闻的系统在没有新闻的环境里能做什么。
我们不为它接一条新闻源（红线 5：行情/新闻源域名一律不得入出向白名单）。

### 4.4 上游默认跑美股

`benchmark_map` 里有 `.SS` / `.SZ` 的映射，但整套 prompt 与 ticker 习惯是美股形态。
本接入把 A 股代码（`600000.SH`）原样传给 `propagate()`，
垫片按湖内形态处理，模型侧则是「它认不认得这个代码」的问题 —— **不替它改写代码形态**。

### 4.5 `declared_reads` 探针看不到细粒度 `fields`

`get_stock_data` 一律按六列请求 `/bars`。S3 类任务需要控制声明读取集时不能走这条路
（本接入只做 S5，不受影响）。

---

## 5. 怎么复现

### 5.1 构建（在 f02；f01 没有容器运行时）

构建上下文要有三样：本目录、垫片、**源码压缩包**。
**codeload.github.com 在 f02 的构建网里不可达**（实测 curl 超时），
所以不在 Dockerfile 里 clone/curl —— 在本地下载、经 f01 两跳 scp 过去：

```bash
# 本地（记下 commit 与 sha256，与 pin.json 逐字核对）
curl -L -o TradingAgents-2448d0a12576f9b2ddcd5980a0630833423d1e1b.tar.gz \
  https://codeload.github.com/TauricResearch/TradingAgents/tar.gz/2448d0a12576f9b2ddcd5980a0630833423d1e1b
shasum -a 256 TradingAgents-*.tar.gz
# → f4f81e7538992b094a0610d38c919cc2777344bf4ebee55d740818fc323db94d

# 在 f01
scp -r integrations/tradingagents integrations/genebench_client \
       ljn@192.168.1.219:/data/genebench_runner/build/tradingagents/
scp TradingAgents-2448d0a12576f9b2ddcd5980a0630833423d1e1b.tar.gz \
       ljn@192.168.1.219:/data/genebench_runner/build/tradingagents/

# 在 f02
cd /data/genebench_runner/build/tradingagents
docker build -t gb-tradingagents-u:r1 -f tradingagents/Dockerfile .
docker inspect gb-tradingagents-u:r1 --format '{{.Id}}'
```

**镜像 digest（本次）**：`sha256:d875d084e2cc16985721445f2e72dc355c01fa86bb67ac24a32c858efb48e2b0`

两处构建期的坑（都在 Dockerfile 里注掉了，写在这里免得再踩）：

1. 基座 `python:3.12-slim` **没有 setuptools**，而垫片的 build-backend 就是
   `setuptools.build_meta` —— 照手册那三行直接 `--no-index --no-build-isolation`
   会当场 `BackendUnavailable`。先 `pip install "setuptools>=61" wheel`（走 index），
   垫片本身仍然 `--no-index`。
2. **`COPY` 原样带上宿主的文件权限**。`$GENEBENCH_ROOT` 全树受红线 5 守门、一律 0600，
   于是接线层进了镜像也是 0600，而容器以 `user: "1000:1000"` 跑 ——
   `Permission denied`，两臂 13 秒退出、`no_artifact`。COPY 之后要
   `chmod -R a+rX`。（本接入第一次真跑就是这么挂的。）

### 5.2 无头自检（不打网关、不调模型）

```bash
# 在 f02
docker run --rm --network none --user 1000:1000 \
  -v $PWD/smoke_in_container.py:/tmp/smoke.py:ro \
  -v $PWD/INSTRUCTION.strict.md:/tmp/INSTRUCTION.md:ro \
  gb-tradingagents-u:r1 python3 /tmp/smoke.py          # → SMOKE-OK
```

它证明七件事：上游装上了且 vendor 表是 11 个方法；替换点全部在位；
**两条缝在替换之前各自都是红的**（非空证明）；整表替换 + `load_ohlcv`/`yf` 换掉之后都转绿；
`yfinance` 陷阱确实会抛；题面解析与 `emit` 走得通。

### 5.3 出集 → 推送 → 真跑 → 结算

```bash
PY=/data/shared/genebench/env/bin/python; cd /data/shared/genebench/repo
STG=/data/shared/genebench/staging/i_tradingagents_s5-eco-01
DIG=sha256:d875d084e2cc16985721445f2e72dc355c01fa86bb67ac24a32c858efb48e2b0

rm -rf "$STG"
$PY ops/export_bundle.py s5-eco-01 --staging "$STG" --digest "$DIG" --image gb-tradingagents-u
ops/push_bundle_to_f02.sh "$STG/tasks/s5-eco-01" \
    /data/genebench_runner/i_tradingagents/runner/tasks "$STG/s5-eco-01.manifest.json"
ops/push_exec_to_f02.sh --with-launch-data          # 必带，否则 f02 上 by_id 找不到 config_id

$PY ops/gateway_lock.py --what "2.6:真跑 s5-eco-01 tradingagents" -- \
  ssh -o ConnectTimeout=120 ljn@192.168.1.219 \
  "umask 022; export PYTHONDONTWRITEBYTECODE=1; cd /data/genebench_runner && \
   python3 exec/ops/run_f02_a1.py \
     --bundle   /data/genebench_runner/i_tradingagents/runner/tasks/s5-eco-01 \
     --manifest /data/genebench_runner/i_tradingagents/runner/tasks/s5-eco-01.manifest.json \
     --config-id cfg-tradingagents-deepseek --arms strict,open --seq 1 \
     --timeout 1500 --max-calls 100 --max-tokens 3000000 \
     --run-root /data/genebench_runner/i_tradingagents/runs \
     --results-dir /data/genebench_runner/i_tradingagents/results"

$PY ops/score_runs.py --batch i_tradingagents --remote /data/genebench_runner/i_tradingagents/runs/runs
$PY ops/api_usage.py                                # 模型用量（扫 llm_log 的 decision==allow）
```

### 5.4 判据

```bash
cd /data/shared/genebench/repo && ulimit -n 8192
$PY -m pytest ops/test_integration_tradingagents.py -q -p no:cacheprovider
```

---

## 6. 真跑证据

**任务**：`s5-eco-01`（S5 自由发挥题：用给定的三个因子面板构造分数信号；
`as_of=2026-07-31`，窗口 `2026-01-05..2026-07-31`，universe `csi300`）。
选它而不是 `s5-cor-01`，因为 `s5-cor-01` 要的是「把给定因子面板做横截面百分位名次」——
一次确定性变换，与 TradingAgents 在做的事（多智能体给一条评级）根本不是一回事；
`s5-eco-01` 的 `value_semantics=score` 与它的五档评级同型。

**批次**：`i_tradingagents`。**镜像**：`gb-tradingagents-u:r1`
（`sha256:d875d084e2cc16985721445f2e72dc355c01fa86bb67ac24a32c858efb48e2b0`）。

| run_id | 结果 | 模型调用 | 说明 |
| --- | --- | --- | --- |
| `s5-eco-01.{strict,open}.cfg-tradingagents-deepseek.r01` | `no_artifact` | **0** | 接线层在镜像里是 0600，容器非 root 读不到（§5.1 第 2 条坑）。**agent 一次都没起来** |
| `s5-eco-01.strict.…r02` | `malformed`（`invalid`） | 3 | 第 2 条缝：`get_verified_market_snapshot` 走 `yf.download`，三格全挂，交出 `signals: []` |
| `s5-eco-01.open.…r02` | `no_artifact` | 0 | open 臂题面写「本次任务的 as_of 是 …」，解析只认 strict 的 `key=value`，入口当场退出 |
| **`s5-eco-01.strict.…r03`** | **`ok` / `valid`** | **61** | 3 格：`Hold` / `Underweight` / `Underweight` |
| **`s5-eco-01.open.…r03`** | **`ok` / `valid`** | **58** | 3 格，同上 |

`r03` 两臂的结算（`ops/reports/i_tradingagents/`）：

* `validity = valid`、`gate_failed = []`、**十六个探针族全部 `clean`**；
* **越权率 0**（strict 0/91、open 0/88，来源是网关 `access_log` 的 403 计数，不采信自报）；
* `unbounded_requests = 0`、`unexpected_files = []`（`/task` 下没多出文件，P8 封闭）；
* `effect` 按 `anchor_pending` 扣住不发（自由发挥题，卡 5.4 之前本来就不产出效果分）；
* 一个值得注意的数：`malformed_requests` strict 60 / open 45，`reason` 全是 `unclassified`
  —— 那**不是**参数拼错，是垫片的 `NO_DATA` 留痕（`GET /nodata/<kind>` 故意打在白名单之外，
  网关中间件记 404）。已登记票据：这两件事在结算口径上现在分不开。

**证据路径**（f01）：

```
ops/reports/i_tradingagents/{summary.md,records.json,table_a.csv,table_b.csv,scores/}
/data/shared/genebench/staging/i_tradingagents_s5-eco-01/          # 出集
```

**证据路径**（f02，run dir 里有产物、容器日志、egress 与 llm 日志）：

```
/data/genebench_runner/i_tradingagents/runs/runs/s5-eco-01.{strict,open}.cfg-tradingagents-deepseek.r03/
    work/artifact.json  run.json  log/egress.jsonl  log/llm_log.jsonl
```

**产物长什么样**（`r03` open 臂，逐字）：

```json
"declarations": {"value_semantics": "score", "signal_frequency": "daily",
                 "direction": "higher_is_long", "universe_ref": "csi300@2026-07-31",
                 "missing_policy": "keep_null",
                 "input_factors": ["gtja_191.001", "gtja_191.002", "gtja_191.003"]},
"payload": {"signals": [{"date": "2026-07-31", "symbol": "000001.SZ", "value": 0.0},
                        {"date": "2026-07-31", "symbol": "000002.SZ", "value": -0.5},
                        {"date": "2026-07-31", "symbol": "000063.SZ", "value": -0.5}],
            "coverage": {"n_valued": 3, "n_null": 0, "n_flat": 0}}
```

**怎么读这三行**：产物**合规**（valid、零违例、零越权），但它只有 3 格，
而题面要的是整张面板 —— 这正是 §4.1 那条。**「合规」与「做完了」是两件事**，
覆盖矩阵里那个 `passed` 必须连着备注一起读。

接入工时与返工次数在 [`COST.md`](../COST.md)；模型用量另有机器统计（`$PY ops/api_usage.py`）。
