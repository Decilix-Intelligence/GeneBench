# FinRobot × GeneBench（P2 接入）

**接的是**：[AI4Finance-Foundation/FinRobot](https://github.com/AI4Finance-Foundation/FinRobot)
`0.1.5`（PyPI sdist，sha256 `62ac363e…`，与 repo commit `6e91cef9` 的包目录逐字节相同），
论文 [arXiv:2405.14767](https://arxiv.org/abs/2405.14767)，MIT。钉在 [`pin.json`](pin.json)。

**跑的是**：`Market_Analyst` —— FinRobot 自带的 AutoGen 单智能体 + 工具集
（`SingleAssistant("Market_Analyst")`），它的工具本来就是四个取数接口。
我们把这四个接口的**实现**换成经数据网关的（换不成的退成 `NoData` 并在数据面留痕），
其余一概不动。

**跑到的阶段**：**S1（取数留痕）**，一道真题双臂都 `valid`（见 §6）。

| | |
| --- | --- |
| 镜像 | `gb-finrobot-u:r1`，image id `sha256:c6f6b3e833fbae0fd0954a8f036885323a1921cd4f3aadd78ad0622a3bbf11a2` |
| 配置 | `cfg-finrobot-deepseek`（`deepseek-chat`，经边车） |
| 接线层 | [`glue/gateway_sources.py`](glue/gateway_sources.py)（替换表）、[`glue/run.py`](glue/run.py)（入口） |
| 判据 | `ops/test_integration_finrobot.py`（41 条）、[`smoke_in_container.py`](smoke_in_container.py)（镜像内 11 项） |
| 证据 | `ops/reports/i_finrobot/`、f02 `/data/genebench_runner/i_finrobot/runs/runs/` |

---

## 1. 为什么是 S1

FinRobot 的 `Market_Analyst` 是**带取数工具的分析 agent**：库里给它的四件套
（`get_company_profile` / `get_company_news` / `get_basic_financials` / `get_stock_data`）
全部是数据获取。S1 的题面正是「经数据网关取指定字段与窗口的日线，
把每一次取数写成结构化记录」—— 这是它能力的正面照。

S3/S4/S6/S7 要的是因子表达式、IC、组合权重、成交账本，FinRobot 没有对应部件；
S5 要一张信号面板，它的 `Market_Analyst` 能出的是一段文字判断而不是逐格信号
（那条路 `tradingagents` 与 `finmem` 已经各走过一遍）。
**没跑过的阶段在 `COVERAGE.md` 里一律是 `—`。**

## 2. 怎么装的（复现步骤，逐条可抄）

上游从 **PyPI sdist** 装，`--no-deps`（依赖按本环境的口径另装，见 §3）+
`--ignore-requires-python`（上游写 `<3.12`，基座是 3.12，见 §5）。
**Dockerfile 里不 `curl`、不 `git clone`** —— 钉靠字节摘要，不靠 URL 当天通不通。

```bash
# ① 拿上游 sdist（哪台机器能出网就在哪台拿；本卡是在 f02 的构建目录里拿的）
curl -sL -o finrobot-0.1.5.tar.gz \
     https://pypi.org/packages/source/f/finrobot/finrobot-0.1.5.tar.gz
sha256sum finrobot-0.1.5.tar.gz     # 必须是 62ac363ed5e2…8291，对不上就停下

# ② 构建上下文（在 f01）
cd /data/shared/genebench/repo
scp -r integrations/finrobot integrations/genebench_client \
       ljn@192.168.1.219:/data/genebench_runner/build/finrobot/
#    再把 ① 的 tar.gz 放到 /data/genebench_runner/build/finrobot/ 顶层

# ③ 构建（在 f02；f01 没有容器运行时）
ssh ljn@192.168.1.219 "cd /data/genebench_runner/build/finrobot && \
    docker build -t gb-finrobot-u:r1 -f finrobot/Dockerfile ."

# ④ 镜像内自检（**不打模型**，只打网关几次；真跑前先过这一关）
ssh ljn@192.168.1.219 "docker run --rm \
  -e GENEBENCH_GATEWAY=http://192.168.1.48:18080 \
  -e GENEBENCH_TASK_ID=smoke-finrobot -e GENEBENCH_CONFIG_ID=cfg-finrobot-deepseek \
  -e GENEBENCH_ARM=smoke -e GENEBENCH_RUN_ID=smoke-finrobot \
  -v /data/genebench_runner/build/finrobot/finrobot/smoke_in_container.py:/tmp/smoke.py:ro \
  gb-finrobot-u:r1 python3 /tmp/smoke.py"      # 期望最后一行 RESULT SMOKE-OK
```

出集 / 推送 / 真跑 / 结算的四条命令在 §6。

## 3. 数据层怎么接的

**一句话**：`finrobot.data_source` 的**每一个公开方法**都被换掉了 ——
能对上网关端点的换成网关实现，对不上的换成 `NoData`。
替换表在 `glue/gateway_sources.py` 的 `_GATEWAY_SPEC` / `_NO_DATA_SPEC`，
`assert_no_native_datasource()` 在每次真跑开跑前把 22 个方法核一遍，
**漏一个就当场退出**（漏掉的那个会是一条网关日志上完全看不见的原生数据源）。

### 3.1 换成网关的

| 上游 | 换成 | 说明 |
| --- | --- | --- |
| `YFinanceUtils.get_stock_data` | `/bars` | **加了一个 `fields` 参数**：S1 题面要求「显式传 fields」，读取集是这道题在考的东西 |

### 3.2 接线层新增的三个工具（上游没有）

网关有、而 FinRobot 没有对应概念的三样：指数 PIT 成分、交易日历、复权因子。
题面明写「成分不得手写，一律经 `/universe` 取」，不给工具就只剩违题或做不了。

| 新增 | 端点 | 为什么不是"改内核" |
| --- | --- | --- |
| `get_index_constituents` | `/universe` | FinRobot 的架构就是"把一组函数注册给 agent"，加一个函数走的是它自己的 `register_toolkits` |
| `get_trading_calendar` | `/calendar` | 同上 |
| `get_adjustment_factors` | `/adj` | 同上。**没有**把它伪装成 `get_stock_dividends` —— `/adj` 发的是合成复权因子，不是分红明细，两者不是一件事 |

### 3.3 退成 `NoData` 的（本环境没有这个数据源）

| 上游 | 分类 | 为什么没有 |
| --- | --- | --- |
| `FinnHubUtils.get_company_news` | `news` | 本环境没有新闻数据源 |
| `FinnHubUtils.get_basic_financials` / `…_history` | `fundamentals` | 三大报表不发放给 v1 的任何一道题（N-58①） |
| `FinnHubUtils.get_company_profile` | `other` | 没有档案数据源 |
| `YFinanceUtils.get_stock_info` / `get_company_info` | `other` | 网关只发 PIT 成分与行情 |
| `YFinanceUtils.get_stock_dividends` | `corporate_actions` | 网关只发合成 `adj_factor`，不发分红/拆股明细 |
| `YFinanceUtils.get_income_stmt` / `get_balance_sheet` / `get_cash_flow` | `fundamentals` | 同上 |
| `YFinanceUtils.get_analyst_recommendations` | `sentiment` | 没有卖方评级数据源 |
| `FMPUtils.*`（5 个） | `sentiment` / `fundamentals` / `other` | 没有 FMP 数据源；A 股环境没有 SEC 报告 |
| `SECUtils.*`（4 个） | `other` | A 股环境没有 10-K |
| `RedditUtils.get_reddit_posts` | `sentiment` | 没有社交媒体数据源 |

`NoData` 的替身**不抛异常、也不返回 `None`**：它先打一次 `/nodata/<kind>` 让网关
中间件留一行 access_log（"它试过要新闻"与"它根本没想过"必须可区分），
再返回一句给模型看的说明。**签名照抄上游那一个**（见 §5 的第二个坑）。

### 3.4 `compat.yfinance` 用在哪、不用在哪

* **用**：`run.py` 开头 `compat.install()` 把垫片顶进 `sys.modules["yfinance"]`。
  `finrobot/functional/quantitative.py` 在**模块层** `import yfinance as yf`，
  不顶替就 import 不进来。顶替之后，"意外连上 Yahoo"这条路在进程里就不存在了 ——
  镜像里**根本没装** `yfinance` / `tushare` / `pandas_datareader`（见 `requirements.gb.txt`）。
* **不用**：取数不走 `compat.yfinance`。手册（`integrations/README.md` §3）自己说得很清楚——
  compat 层的 `fields` 只裁剪返回值、不改变网关上的读取集，而 S1 要的正是显式读取集。
  所以 `get_stock_data` 直接用 `gb.client().bars(..., fields=[...])`。

### 3.5 出向那一侧

FinRobot 原生四个数据源里，**Yahoo / finnhub / reddit 在 `MARKET_DATA_DENY` 表里**
（`runner/c41/egress_proxy.py`）；`financialmodelingprep.com` 与 `sec-api.io` 不在那张表上，
但出向白名单**只有模型 API**，所以它们同样连不出去。
两道门是不同的门：黑名单是"点名不许"，白名单是"没点名就不许"。

## 4. LLM 怎么指的

AutoGen 的 `llm_config.config_list` 只有一条，`base_url` 取自 `OPENAI_BASE_URL`
（边车的反向代理），`api_key` 取自 `OPENAI_API_KEY`（容器里是**占位串**，真 key 由边车注入）。
接线层里**没有任何写死的主机名** —— 写死就绕开了预算闸与 usage 归属。
`cache_seed=None`：关掉 AutoGen 的磁盘缓存，否则它往 cwd 写 `.cache/`。

对话轮数 `max_consecutive_auto_reply=12`（`GENEBENCH_FR_MAX_TURNS` 可调）。
实测一次运行 8–13 次模型调用，闸是 100 次（`--max-calls 100`）。

## 5. 已知限制与偏离

1. **`--ignore-requires-python`**：上游 `setup.py` 写 `>=3.10, <3.12`，统一基座是 3.12。
   不是"忽略警告"，是有实测的：`import finrobot.agents.workflow` 通过、
   `SingleAssistant` 组得起来、一道真题双臂跑完（§6）。0.1.5 的代码里没有 3.12 移除的用法。
   代价是**上游没在 3.12 上测过**，将来若有为 3.12 单独出的版本，应该换过去。
2. **依赖不是上游的 `requirements.txt`**：`yfinance` / `tushare` / `pandas_datareader`
   有意不装（垫片顶替）；`pyautogen[retrievechat]` 那一档只装 import 期真要的四个
   （`chromadb` / `markdownify` / `pypdf` / `beautifulsoup4`），
   不装 `sentence_transformers`（→ torch，2GB+），因为 RAG 这条路一次都没调。
   `finrobot/functional/rag.py` 在**模块层** import `RetrieveUserProxyAgent`，
   所以这几个是"进不进得了 import"的问题，不是"用不用得上"的问题。
   镜像里实际装了什么逐字记在 [`resolved_deps.txt`](resolved_deps.txt)。
3. **工具返回值做了摘要**。上游 `toolkits.stringify_output` 把整张 DataFrame
   `to_string()` 塞进对话；csi300 × 一个月是 6,900 行、几十万字符，一次就把上下文顶满
   （现场表现是"跑了一半就停"）。接线层返回 **行数 / 标的数 / 区间 / 列名 + 前 5 行**，
   都是真数不是估。**代价**：模型看不到全表，只能靠这些计数做判断 ——
   对 S1（记录取数）够用，对"读着行情做判断"的题不够。
4. **产物是接线层写的**。FinRobot 没有"产物"这个概念，`emit` 由 `run.py` 调用。
   但 `payload.fetches` 的每一行都来自**网关 ledger 的逐条清点**，
   `fields_obtained` 是真回来的列减掉键列（`code`/`date`/`status`，与
   `reference/artifact_schema.py::BARS_KEY_COLUMNS` 同源）。
   agent 没取的东西产物里不会有，多取的也赖不掉。
5. **`declarations` 照题面逐字填**，题面没给的标 `"unresolved"`。这一步是接线层做的
   （解析器在 `run.py`），不是模型做的 —— 模型做的是"取哪些数"。
6. **两个真踩到的坑**（都在镜像内自检里立了判据，因为两者的现场表现都是
   "接线看着全对、agent 根本没起来"）：
   * `agent_library` 在**模块层**就把工具函数对象抓进 `library[...]["toolkits"]`。
     只要有任何一条 import 路径先碰到 `finrobot.agents.*`，`install()` 换的就是没人再看的那份。
     补救是 `patch_library()`：按函数名把表里的项重绑到当前类属性，让顺序不再是前提。
   * autogen 从**签名**生成工具 JSON schema。`NoData` 替身若写成 `*args, **kwargs`
     会 `TypeError: All parameters … must be annotated`；而
     `from __future__ import annotations` 会让 `Annotated[str, "…"]` 到 pydantic 手里变成
     解析不了的 ForwardRef（`PydanticUserError`）。
     所以替身用 `functools.wraps(上游函数)` 照抄签名，接线模块**不写**那条 future import。
7. **没跑过多智能体那一路**（`SingleAssistantShadow` / group chat / `Expert_Investor` 的年报流水线）：
   后者要 SEC 与 PDF 那一串，本环境没有数据源。

## 6. 真跑证据

```bash
PY=/data/shared/genebench/env/bin/python; cd /data/shared/genebench/repo
STG=/data/shared/genebench/staging/i_finrobot_s1-cor-01; rm -rf "$STG"
$PY ops/export_bundle.py s1-cor-01 --staging "$STG" \
    --digest sha256:c6f6b3e833fbae0fd0954a8f036885323a1921cd4f3aadd78ad0622a3bbf11a2 \
    --image gb-finrobot-u
ops/push_bundle_to_f02.sh "$STG/tasks/s1-cor-01" \
    /data/genebench_runner/i_finrobot/runner/tasks "$STG/s1-cor-01.manifest.json"
ops/push_exec_to_f02.sh --with-launch-data
$PY ops/gateway_lock.py --what "2.6-finrobot:真跑 s1-cor-01" -- \
  ssh -o ConnectTimeout=120 ljn@192.168.1.219 \
  "umask 022; export PYTHONDONTWRITEBYTECODE=1; cd /data/genebench_runner && \
   python3 exec/ops/run_f02_a1.py \
     --bundle   /data/genebench_runner/i_finrobot/runner/tasks/s1-cor-01 \
     --manifest /data/genebench_runner/i_finrobot/runner/tasks/s1-cor-01.manifest.json \
     --config-id cfg-finrobot-deepseek --arms strict,open --seq 1 \
     --timeout 1500 --max-calls 100 --max-tokens 3000000 \
     --run-root /data/genebench_runner/i_finrobot/runs \
     --results-dir /data/genebench_runner/i_finrobot/results"
$PY ops/score_runs.py --batch i_finrobot --remote /data/genebench_runner/i_finrobot/runs/runs
```

**结果（`r01`，2026-09-07）**：

| 臂 | validity | gate | SR | pass@1 | 越权率 | 模型调用 | 用时 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| strict | `valid` | `[]` | 1.0 | 1.0 | 0.0 | 8 | 187.4 s |
| open | `valid` | `[]` | 1.0 | 1.0 | 0.0 | 13 | 420.6 s |

两臂都把**整张面板**取全了：`/bars`（`fields=close,volume`）6,900 行
= 300 只 × 23 个交易日，`/adj` 6,900 行，`/universe` 300 只，
`fields_obtained = [adj_factor, close, volume]`，
`declarations = {calendar_id: SSE, universe: csi300, data_version: v1}`。

两臂的 `fetches` 条数不同（strict 7、open 4）**不是漂**：那是两臂各自真实的取数次数 ——
strict 臂的模型多解析了两次 `/universe`（用索引名调工具时工具自己去取成分）
并重复问了一次 `/calendar`。ledger 逐条记，接线层不去重、不合并。

`run.json` 的 `new_files` 只有三样（`log/egress.jsonl`、`log/llm_log.jsonl`、
`work/artifact.json`），`/task` 下**零多余文件** —— autogen 的 `coding/` 与缓存
都落在 `/tmp/fr`（P8 文件集封闭）。

产物与日志（f02）：
`/data/genebench_runner/i_finrobot/runs/runs/s1-cor-01.{strict,open}.cfg-finrobot-deepseek.r01/`
结算（f01）：`ops/reports/i_finrobot/`（`summary.md` / `records.json` / `table_a.csv` / `scores/`）。

## 7. 判据怎么跑

```bash
cd /data/shared/genebench/repo && ulimit -n 8192
/data/shared/genebench/env/bin/python -m pytest ops/test_integration_finrobot.py -q -p no:cacheprovider
# → 41 passed（不打网关、不需要 gateway_lock）
```

f01 上装不起 FinRobot（autogen/chromadb 那一串不在这台机器上），所以本地那 41 条
对着 [`upstream_api.json`](upstream_api.json) 这份**与 `pin.json` 绑同一个 sha256** 的
上游 API 快照核替换点，并用一份形状相同的替身模块跑守门的正反两例。
**活体那一遍在镜像里**（`smoke_in_container.py` 的 11 项，每次真跑前 `run.py` 也自查一次）。
