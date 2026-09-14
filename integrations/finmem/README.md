# FinMem 接入（P2）

**被测方**：[pipiku915/FinMem-LLM-StockTrading](https://github.com/pipiku915/FinMem-LLM-StockTrading)
commit `be814aa4`（main HEAD，2024-08-18；仓库没有打过 tag），
论文 [arXiv:2311.13743](https://arxiv.org/abs/2311.13743)
《FinMem: A Performance-Enhanced LLM Trading Agent with Layered Memory and Character Design》，MIT。
分层记忆（短 / 中 / 长 / 反思四层 + faiss 检索 + 衰减与跳层）的**逐日单标的交易 agent**：
每个交易日读当天的价格、新闻与财报文本，检索记忆，出一条 buy / hold / sell。

**范式**：P2（专用系统，自带研究流程与内部数据抽象）。
**镜像**：`gb-finmem-u:r1`。**配置**：`cfg-finmem-deepseek`（`deepseek-chat`）。
**接的阶段**：**S5（信号）** —— 它一次产出一个标的、一个交易日的一档决策，那就是一格信号。

---

## 1. 数据层怎么接的

**FinMem 的运行期不取数。** 上游 `run.py` 只做一件事：

```python
with open(market_data_info_path, "rb") as f:
    env_data_pkl = pickle.load(f)
environment = MarketEnvironment(env_data_pkl=env_data_pkl, ...)
```

取数全部发生在**离线阶段** `data-pipeline/`（`01_Alpaca_News_API_download.py` 取新闻、
`01_SEC_API_10k10q_download.py` 取 10-K/10-Q、`04-data_pipeline.py` 用 yfinance 取价，
`03-summary.py` 用 LLM 把新闻摘要成短句）。

所以这个接入的替换缝**不在运行期的某个函数上，而在那个 pkl 上** ——
`glue/env_data.py::build()` 就站在 `data-pipeline/` 的位置。

> **这带来一条与 TradingAgents 相反的性质，值得单独记一笔。**
> TradingAgents 那一轮的结论是「整表替换 vendor 注册表是必要的但不充分」——
> 它有三条通向原生数据源的路，接入者只找到第一条，第 2、3 条是真跑 + 容器隔离
> 抓出来的。FinMem 这边**结构上没有第二条路**：`puppy/` 全树只有两处出网，
> 都是模型侧（`chat.py` 的 `httpx.post(end_point)` 与 `embedding.py` 的
> OpenAI embeddings），没有任何行情/新闻源主机名。
> `smoke_in_container.py` 的第 7 项与 `ops/test_integration_finmem.py` 各守一遍。
> **「取数是否全部经过数据面」这件事，在 FinMem 上是由它自己的架构保证的，
> 不是由我们穷举替换点保证的** —— 这是「运行期取数」与「离线数据集」两类系统
> 在可核查性上的真实差别。

### 1.1 有数的那一样：价格

走垫片的 `compat.yfinance`（FinMem 的 pipeline 原生就是 yfinance），
`auto_adjust=True`，`Close` 是复权价，基准是窗口内 as_of（含）之前最后一个
`adj_factor`。**不自己拼 URL、不自己算复权** —— 那两件事垫片已经做过一遍。
`download` 的 `end` 是右开（与 yfinance 一致），所以 `build()` 里显式 +1 天，
让闭区间的题面窗口右端真的进来。

停牌/无成交那一天**跳过，不前值填充** —— 前值填充会让「那天没交易」
在收益序列上表现为「那天收益 0」，而 FinMem 的动量与反馈都是从这条序列上算的。

### 1.2 没数的那三样：新闻、10-K、10-Q

`env_data` 的 `news` / `filing_k` / `filing_q` 三个槽**恒为空字典**。
每一类在网关 `access_log` 上留一次痕（`genebench_client.nodata.trace`，
打一个白名单之外的 `/nodata/<kind>`，网关的 HTTP 中间件对未匹配路由同样记账）。
**一类一次，不是一天一次**：FinMem 的 pipeline 是「一次把整段窗口的新闻拉下来」，
尝试的粒度就是一类一段。真跑实测三条全部 `traced: true`。

**这对 FinMem 意味着什么，就是这次接入要测的东西**：它的短期记忆层本来装的是
新闻摘要，中/长期装的是 10-Q/10-K。没有这三样，四层记忆里**只剩它自己写的反思**。
我们不为它接一条新闻源（红线 5：行情/新闻源域名一律不得入出向白名单），
也不把题面给的因子面板塞进 `news` 槽冒充新闻（见 §4.2）。

---

## 2. 配置指向 `/task`

* 题面：`/task/INSTRUCTION.md`（唯一入口）。`glue/instruction.py` 从固定槽读
  `as_of` / `window` / `universe` 与「本次任务的口径（逐项）」，**取不到就退出，不猜默认值**。
  正则写法与 `integrations/tradingagents/glue/run.py` 同源（同一批坑：两臂表达形式不同、
  `universe` 会被 `可用端点：… /universe …` 那一行带偏到 `tradability`）。
* 产物：`/task/artifact.json`，由 `genebench_client.emit.emit_s5` 写；`coverage` 由 emit 清点。
* **落盘一律在 `/tmp`，不进 `/task`**：上游三处 `logging.FileHandler` 写的是
  **相对 CWD** 的 `data/04_model_output_log/<sym>_run.log`，所以入口先
  `chdir` 到 `/tmp/finmem` 并把 `data/` 的六个子目录建好（`run.py::prepare_workdir`）。
  容器里的 `/task` 就是 run dir 的 `work/` 本身，往它下面落东西会破 P8 文件集封闭。
  真跑实测 `run.json` 的 `unexpected` 是 `[]`。
* `GENEBENCH_AS_OF` **不由 runner 注入**（compose 模板里没有这一行），
  所以入口启动时 `gb.set_as_of(as_of)` 一次，`as_of` 从题面读。

---

## 3. LLM 怎么指

上游用 `httpx` 直接打 `config["chat"]["end_point"]`。接线层把它设成
**`{OPENAI_BASE_URL}/chat/completions`**（`glue/chat_seam.py::build_chat_config`），
`glue/` 里**没有任何写死的主机名**（三个变量依次试，都没有就退出）。

唯一不兼容的一处是**读响应**：上游 `ChatOpenAICompatible.parse_response` 按模型名
前缀分三条路（`gpt` / `gemini-pro` / `tgi`），`deepseek-chat` 走到 else 分支
**当场 `NotImplementedError: Model deepseek-chat not implemented`**（自检里看着它抛，
不是相信注释）。接线层用一个**只覆盖 `parse_response` 的子类**顶替
`puppy.agent` 命名空间里的那个名字 —— 换 `puppy.chat` 对它无效，因为 `agent.py` 是
`from .chat import ChatOpenAICompatible`，它持有自己那份引用。

**不谎报模型名**：把 `model` 写成 `gpt-…` 去骗那个 `startswith` 会让 payload 里的
模型名与真正被调用的模型对不上，而边车与 `llm_log` 记的是 payload 里那个名字。

预算：每 run `--max-calls 100`。FinMem 每个交易日一次反思调用，`guardrails` 的
`num_reasks=1` 意味着最多两次。真跑实测 **strict 36 次 / open 35 次**（22 步：
12 天建记忆 + 10 天出决策）。

---

## 4. 已知限制（**这一节是本接入最重要的部分**）

### 4.1 本环境没有 embeddings 端点 —— 向量后端被换掉了

分层记忆是 FinMem 的核心，没有向量后端它一步都跑不动。上游用
`langchain_community` 的 `OpenAIEmbeddings`（`text-embedding-ada-002`）。

**这件事是实测的，不是断言的**：入口启动时真打一次
`POST {OPENAI_BASE_URL}/embeddings`，打通就用它、维度取回包里那个。
真跑的结果写在 stdout 上：

```
[glue] 向量后端探针：{"backend": "offline_hash", "dim": 1536,
  "model": "text-embedding-ada-002", "status": 404, "reason": "http_404",
  "endpoint": "http://gateway:8081/v1/embeddings", "body_head": ""}
```

**404** —— 边车把请求原样转给上游模型 API，而那一头没有这个端点。
于是退到 `glue/embedding_seam.py` 的**离线确定性向量**：哈希袋
（正则切词/CJK 单字 → `blake2b` 定址与定号 → `log(1+tf)` 累加 → L2 归一），
维度仍是 1536（这样 faiss 那一侧的配置一个字不用改）。

**它保的是「字面重合的两段文字相似」，保不了「语义相近但用词不同的两段文字相似」。**
这会降低记忆检索的质量 —— 这是一处**替换**，不是一处「本环境没有这类数据」，
所以写在这里而不是藏在注释里。想关掉探针：`GENEBENCH_FINMEM_EMB_PROBE=0`。

### 4.2 题面给的三条因子面板，FinMem 用不上

`s5-eco-01` 在 `/task/inputs/` 下发了三张因子面板（`gtja_191.001/002/003`），
声明口径里的 `input_factors` 就是这三条。**FinMem 的流水线里没有装外生因子的槽**：
它的输入形态是 `{price, news, filing_k, filing_q}` 四样，前一样是数、后三样是**文本**。

我们**没有**把因子值渲染成文字塞进 `news` 槽 —— 那是伪造新闻：
它会在 agent 的上下文里表现为「有人说了这么一句」，而事实是没有人说过。
声明照题面逐字填（题面正文写着「键名用每条给出的字段名，取值用每条给出的接口值」），
**声明与实际用到的输入之间的这处落差是接入结果，交给评分器判**，不由接入层抹平。

### 4.3 两段式：train 建记忆、test 出决策（**不是可选项**）

FinMem 的 **train 模式不产出交易决策** —— `agent.py::_construct_train_actions`
直接拿 `cur_record`（次日价 − 当日价）的符号当动作，LLM 在那一段只负责写反思；
`investment_decision` 只在 **test 模式**里产生（`__process_test_action`）。

所以「跑一遍 train 就交信号」不可能；而「整段都用 train」会把**次日收益**喂进
产出信号的那一步 —— 那是窗口内的前视。**网关看不见它**（数据全在 `as_of` 之内，
不会有一次 403），但它会让分数不是这个系统的能力。

入口因此按官方协议切两段、**首尾相接不重叠**：`train 2026-07-01..07-17`（12 天）
→ `test 2026-07-17..07-31`（10 天）。test 段的每一天只用到严格更早的日子。
官方是 `sim`（train）落 checkpoint → `sim -rm test -tap <ckpt>` 载入；
本入口不落盘、直接把同一个 agent 对象接着用，与 save→load 等价
（checkpoint 存的就是 brain + portfolio + `reflection_result_series_dict` + counter）。

### 4.4 产出粒度是一格 × 连续若干天，题面要的是一张面板

`s5-eco-01` 要的是 csi300 × 2026-01-05..07-31 的一张面板（约 4 万格），
本次交了 **10 格**（1 个标的 × 10 天）。

**我们不替它补格子。** 凑不满是**事实**，由评分器判；接入层把剩下的格子填成
0 / 前值 / 随机数，得到的分数就是「我们替它补了多少」的函数 ——
而且**没有任何信号会红，分数只是更高一点**。

**选「一个标的 × 连续若干天」而不是「若干标的 × 一天」**（TradingAgents 那一轮
选的是后者）：FinMem 的核心是分层记忆，记忆只有在同一个标的的时间序列上才积累得
起来。横着切会把它变成一个没有记忆的零样本分类器 —— 那测的不是 FinMem。
格数由 `GENEBENCH_FINMEM_TRAIN_DAYS` / `_TEST_DAYS` / `_MAX_SYMBOLS` 控制，
**改大就要同步改 `--max-calls`，两个数必须一起改**。

### 4.5 「没有新闻」在它自己的代码里的样子

`environment.py` 对「当天没有新闻」的处理是 `cur_news = {self.symbol: ''}`，
`agent.py::_handling_news` 的判据是 `if news != {}` —— 空字符串不等于空字典，
于是**每一天都会往短期记忆里塞一条空记忆**。

**这是它自己的退化路径，我们不替它改**（改了就不是 `be814aa4` 那份字节）。
记在这里是因为它会影响读日志的人：短期记忆里那一堆空条目不是接线层的 bug。

### 4.6 `hold` 是一档决策，「没跑出决策」不是

`buy +1.0 / hold 0.0 / sell -1.0`。上游在 guardrails 解析失败时**自己**兜底成
`investment_decision="hold"`（`reflection.py` 末尾），那仍然是它交出来的一档决策，
照记 0.0。只有**那一天整个 `agent.step` 抛了**（预算 429、上游 502……）才记
`None`（无观点）—— 题面写着无观点的格子不得补 0，而 `hold` 与「这一天根本没跑出
决策」含义相反。连着 3 天拿不到决策就停（`GENEBENCH_FINMEM_MAX_FAILS`）：
预算耗尽的现场表现就是「每一天都拿不到决策」，而上游把任何异常都吞成 `{}`。

### 4.7 角色设定没有照抄

上游示例配置里的 `character_string` 是一段**人工写的 TSLA 先验**
（"You are an expert of TSLA … Tesla's continued growth …"）。标的换成 A 股之后
逐字照抄等于把一段与标的无关的先验塞进检索查询
（`query_short(query_text=character_string)` 用的就是它）。
`run.py::CHARACTER` 是一段只陈述**题面与本环境事实**的中性 persona：
标的是什么、有什么数据、没有什么数据，**没有任何方向性判断**。

### 4.8 依赖与解释器的两处偏离

* **不装 `torch`**：上游冻结清单里的 `torch==2.2.0+cpu`（与它带的
  `--extra-index-url https://download.pytorch.org/whl/cpu`）没装。`torch` 只经
  `transformers` 被间接需要，而 `transformers` 在这里只用来 `AutoTokenizer`
  （`TextTruncator`），且 `TextTruncator` 只在 config 里出现 `max_token_short` 时
  才实例化 —— 本接入的 config 没有那个键，所以 `torch` 一次都不会被加载。
  实测：无 torch 时 `import puppy` 成功。镜像因此小了约 800 MB。
* **跑在 uv 装的 CPython 3.10 上**，不是基座的 3.12：上游 `pyproject.toml` 写死
  `python = ">= 3.10, < 3.11"`，冻结清单每一行都带同样的环境标记。
  **在 3.12 上 pip 会把每一行都判为不适用、一个包都不装且不报错**
  （"Successfully installed" 后面什么都没有）；就算强行去掉标记，
  `faiss-cpu==1.7.4` 与 `pydantic==2.4.2` 在 cp312 上也没有轮子。

两处都记在 `pin.json` 的 `deviations` 里。

---

## 5. 怎么复现

### 5.1 构建（在 f02；f01 没有容器运行时）

构建上下文要有三样：本目录、垫片、**源码 tarball**。
**2026-09-07 实测 `codeload.github.com` 在 f02 的构建网里可达**
（`curl -o … 200`，25.9 MB；而 2.6-tradingagents 那一轮实测是超时的 ——
所以这件事会变，不要写进 Dockerfile）。tarball 由构建者预先取好放进上下文：

```bash
# 在 f02（或本地取了两跳 scp 过去；两条路的 sha256 必须一样）
cd /data/genebench_runner/build/finmem
curl -sSL -o FinMem-LLM-StockTrading-be814aa47970de9bf2fdd6a1d5a60ae5cf361b46.tar.gz \
  https://codeload.github.com/pipiku915/FinMem-LLM-StockTrading/tar.gz/be814aa47970de9bf2fdd6a1d5a60ae5cf361b46
sha256sum FinMem-LLM-StockTrading-*.tar.gz
# → f0ee88b737b3f4523d4ff7f57d670bbe910f3980136061b44f7c8334bc2d5c36   （= pin.json）

# 在 f01：把接入目录与垫片送过去
scp -r integrations/finmem integrations/genebench_client \
       ljn@192.168.1.219:/data/genebench_runner/build/finmem/

# 在 f02
cd /data/genebench_runner/build/finmem
docker build -t gb-finmem-u:r1 -f finmem/Dockerfile .
docker inspect gb-finmem-u:r1 --format '{{.Id}}'
```

**镜像 digest（本次）**：`sha256:5c57f60660d94c535d5491b50e1940f3b40e3860084d447c4b1b11b5f41ae980`
（1.74 GB on disk / 402 MB content）。

### 5.2 无头自检（`--network none`，不打网关、不调真模型）

```bash
docker run --rm --network none --user 1000:1000 \
  gb-finmem-u:r1 /opt/finmem/venv/bin/python /opt/finmem/smoke_in_container.py   # → SMOKE-OK
```

它证明七件事：venv 是 3.10 且上游装上了；**两处接线点在替换之前各自都是红的**
（非空证明 —— 一道永远绿的门证明不了任何事）；装上之后都转绿；离线向量后端确定
且空文本不产生全零向量；**整条 FinMem 循环在零外网下跑得通**（faiss + guardrails +
train 段 + test 段，模型换成回环上的一个桩）；题面解析与 `emit` 走得通；
`puppy/` 全树没有第二条取数路径。

### 5.3 出集 → 推送 → 真跑 → 结算

```bash
PY=/data/shared/genebench/env/bin/python; cd /data/shared/genebench/repo
STG=/data/shared/genebench/staging/i_finmem_s5-eco-01
DIG=sha256:5c57f60660d94c535d5491b50e1940f3b40e3860084d447c4b1b11b5f41ae980

rm -rf "$STG"
$PY ops/export_bundle.py s5-eco-01 --staging "$STG" --digest "$DIG" \
    --image gb-finmem-u --params genetask/params/v1.0-smoke40.yaml
ops/push_bundle_to_f02.sh "$STG/tasks/s5-eco-01" \
    /data/genebench_runner/i_finmem/runner/tasks "$STG/s5-eco-01.manifest.json"
ops/push_exec_to_f02.sh --with-launch-data      # 必带，否则 f02 上 by_id 找不到 config_id

$PY ops/gateway_lock.py --what "2.6-finmem:真跑 s5-eco-01" -- \
  ssh -o ConnectTimeout=120 ljn@192.168.1.219 \
  "umask 022; export PYTHONDONTWRITEBYTECODE=1; cd /data/genebench_runner && \
   python3 exec/ops/run_f02_a1.py \
     --bundle   /data/genebench_runner/i_finmem/runner/tasks/s5-eco-01 \
     --manifest /data/genebench_runner/i_finmem/runner/tasks/s5-eco-01.manifest.json \
     --config-id cfg-finmem-deepseek --arms strict,open --seq 1 \
     --timeout 2400 --max-calls 100 --max-tokens 3000000 \
     --run-root /data/genebench_runner/i_finmem/runs \
     --results-dir /data/genebench_runner/i_finmem/results"

$PY ops/score_runs.py --batch i_finmem --remote /data/genebench_runner/i_finmem/runs/runs
```

### 5.4 本次真跑的结果（证据）

| | strict | open |
| --- | --- | --- |
| run_id | `s5-eco-01.strict.cfg-finmem-deepseek.r01` | `s5-eco-01.open.cfg-finmem-deepseek.r01` |
| 结果 | `valid`，gate `[]` | `valid`，gate `[]` |
| 越权率 | 0.0 | 0.0 |
| 模型调用 | 36 | 35 |
| 容器耗时 | 76.8 s | 69.6 s |
| 交出的格 | 10（`n_valued=10 / n_null=0 / n_flat=0`） | 10 |
| `run.json` 的 `unexpected` | `[]` | `[]` |

`SR=1.0`（跑完并交出合规产物）、**`pass@1=0.0`** —— 后者别读成「它做对了 0 分之一」：
`s5-eco-01` 是 `kind: free`、`tolerance: none` 的自由题，10 格对 4 万格的面板，
`pass@1` 在这里衡量的是整张面板的口径符合度。**这次接入证明的是链路通、产物合规、
数据面干净，不是 FinMem 的信号有多好。**

证据路径：

* `ops/reports/i_finmem/`（`summary.md` / `records.json` / `table_a.csv` / `table_b.csv` / `scores/`）
* f02：`/data/genebench_runner/i_finmem/runs/runs/s5-eco-01.{strict,open}.cfg-finmem-deepseek.r01/`
  （`work/artifact.json`、`run.json`、`log/llm_log.jsonl`、`log/egress.jsonl`）
* 网关侧：`$GENEBENCH_ROOT/logs/gateway_access.jsonl` 里本次的 `/nodata/news`、
  `/nodata/fundamentals`（各 1 条，`status: 404`）与 `/bars`、`/universe`、`/calendar`。
