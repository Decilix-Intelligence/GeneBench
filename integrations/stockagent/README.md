# StockAgent 接入（P2）

**上游**：[MingyuJ666/Stockagent](https://github.com/MingyuJ666/Stockagent) @ `e2a9c052`，
论文 [arXiv:2407.18957](https://arxiv.org/abs/2407.18957)（*When AI Meets Finance (StockAgent)*，ACM TIST）。
版本与哈希在 [`pin.json`](pin.json)（含**逐文件 sha256**）。

**镜像**：`gb-stockagent-u:r1`，digest `sha256:fea1e2b0aa9cdb648ceffe1b258f93d66a9d1d1e5418552ed780248d8e6226fd`（966 MB）。

**配置**：`cfg-stockagent-deepseek`（`config.yaml`），模型 `deepseek-chat`，经边车。

> 这个接入是**卡 2.7 内部演练**的产物：只凭 `integrations/README.md` + `P2_CONTRACT.md`
> 走一遍，把指南失败的地方记下来再回去修指南。全过程与 findings 表在
> [`ops/reports/integrations_rehearsal.md`](../../ops/reports/integrations_rehearsal.md)。

---

## 1. 它是什么，为什么它值得接

StockAgent 是**一个封闭的模拟市场**：N 个 LLM 交易员，每天分若干交易时段
报价撮合，另有贷款、破产、论坛发帖、次日预期几条支线。它与前面几个接入的
根本差别是 **它原生不取数** —— 股票 A/B/C/D 是虚构的，初始价、三年财报、
季报文本**全部写死在 `util.py` 与 `prompt/agent_prompt.py` 里**，
整个运行期一次外部请求都没有（模型调用除外）。

于是它给出了第三类被测方：

| 类型 | 取数发生在哪 | 「取数是否全部经过数据面」怎么保证 |
| --- | --- | --- |
| 运行期取数（多智能体投研这一类） | agent 循环里 | 靠接入者穷举替换点 —— **不可靠**，得靠真跑与出向白名单抓漏 |
| 离线数据集（读一个 pkl 那一类） | 装数据时 | 结构保证：运行期根本不出网 |
| **无数据（本接入）** | **不存在** | 结构保证；但反过来，**它对真实标的一无所知** |

第三类的接入工作量不在「堵路」，而在**把它虚构的那部分换成真的**。

## 2. 接成了什么

* 范式 **P2**，目标阶段 **S5**（分数信号），真跑的题是 `s5-eco-01`（`kind=free`）。
  选自由题不是图省事：`s5-cor-01` / `s5-ops-01` / `s5-rob-01` 都是 `regulated`，
  要把给定因子面板按规定口径变换成信号并与 gold 比 —— 那是一道确定性变换题，
  和「一群交易员看着行情决定买还是卖」不是同一件事。**声明能做而做不了，
  会把「框架做不了这个阶段」变成「它做了但做错了」，那是两个结论。**
* 上游的两只可交易股票槽 `A` / `B`（`main.handle_action` 与
  `secretary.check_action` 都只认这两个）映射到题面 universe 的 PIT 成分里
  **按代码排序的前两只**（确定性，不随机 —— 随机会让两臂与两次运行都没法比）。
* 模拟第 1..N 天映射到窗口内**最后 N 个交易日**。

## 3. 替换点（逐条；上游一个字节没改）

全部登记在 [`glue/seams.py`](glue/seams.py) 的 `REPLACEMENTS` 里，
每条都有一条判据盯着「上游那个名字还在不在」。

### 3.1 模型分派 —— 不换就**静默不动**

上游 `Agent.run_api` 按模型名分派：`'gpt' in model` 走 openai、`'gemini' in model`
走 google。`deepseek-chat` **两条都不匹配**，函数隐式返回 `None`。
而上游对失败的约定是 `resp == ""` —— `None != ""`，于是 `None` 一路走进
`secretary.check_loan` 的 `isinstance(resp, str)`，判「格式错」、重试三次、
最后按「今天不交易」收场。**症状是「跑完了、一次交易都没有、也没有任何报错」。**

替换后走边车（`OPENAI_BASE_URL` / `OPENAI_API_KEY`，占位 key 照传），
并**保留上游自己的对话历史语义**（它是把整段 `chat_history` 一起送出去的，
那是它的设计，不是缺陷）。

### 3.2 `google.generativeai` —— 顶替成陷阱，不装

`agent.py` 顶层 `import google.generativeai as genai`，而上游
`requirements.txt` 里**没有这个包**（上游自己的缺口）。我们**不装它**：
它是另一家模型 API 的客户端，装进来等于在镜像里留一条通向边车之外的路。
顶替成「任何属性访问都抛」的模块 —— import 得过，真去用当场炸。
（顶替成「什么都返回 None」的假货是错的：那样走到那条路时是静默的错。）

### 3.3 参考价：内生 → 网关来的 PIT 收盘价

上游的价格是内生的，由 agent 自己的撮合推动，起点是 `util.py` 里写死的初值。
替换后 `Stock.get_price()` 返回**映射标的在当天（含）之前最后一个收盘价**
（`/bars`，`fields=["close","volume"]` 显式给）。撮合本身没动 ——
`main.handle_action` 用的是 agent 自己报的 `action["price"]`。

> **这是一处替换，不是一处修复。** 代价：上游的隔夜价格发现被拿掉了。
> 不换的话 agent 面对的是一只与真实标的同名、价格却完全虚构的股票 ——
> 那样得到的决策与这道题无关。两条路都有代价，选了这一条并写在这里。

### 3.4 写死的财报 → 真实标的 + `[NO_DATA]`（**并且真的留痕**）

`FIRST_DAY_FINANCIAL_REPORT` / `FIRST_DAY_BACKGROUND_KNOWLEDGE` 是两段写死的
虚构公司三年财报与背景。对真实标的，那段文字是**假信息**。替换成：
真实代码、当天（含）之前 5 个交易日的收盘/成交量/可交易性、题面给的三条因子在
当天的值，外加一句「本环境没有财报数据源，不要编造数字」——
并在启动时真的打一次 `GET /nodata/fundamentals`，让「它想要财报」
在 `gateway_access.jsonl` 上留一行。

**窗口内前视的防线在这里**：网关只挡 `as_of` 之后的东西，
「窗口之内、信号日之后」那一段它看不见 —— 所以第 d 天的简报只到第 d 天为止，
这条线由接入层自己守（`glue/market.py::Market.brief`，有判据）。

### 3.5 落盘位置：先 `chdir`，再 import

`log/custom_logger.py` 在 **import 期**就 `logging.FileHandler('log/test.txt')`，
`record.py` 往 `res/*.xlsx` 写 —— 两个都是**相对 CWD**。容器的 working_dir 是
`/task`（run dir 的 `work/` 本身），落进去就破 P8 文件集封闭。
所以 `run.py` 的第一件事是 `seams.prepare_cwd()`：建 `/tmp/gb_stockagent/{log,res}` 并 `chdir`，
**在 `import` 上游之前**。顺序错了不是慢一点，是构建期就 `FileNotFoundError`（实测）。

### 3.6 规模闸

`util.AGENTS_NUM` / `TOTAL_DATE` / `TOTAL_SESSION` 三个数一起决定模型调用量：

    calls ≈ agents × days × (1 贷款 + sessions 交易 + 1 次日预期 + 1 发帖)

默认 `2 × 4 × (1+2+1+1) = 40` 次（环境变量 `GENEBENCH_SA_AGENTS` /
`_DAYS` / `_SESSIONS`），给格式重试留余量 —— 每 run 的闸是 100 次。
上游默认是 `50 × 10 × 3`，那是**三千次**量级。

## 4. 决策怎么变成一格信号

规则逐条在 [`glue/signals.py`](glue/signals.py) 的 docstring 里，摘要：

    score = (当天买这只的条数 − 卖这只的条数) / 当天全部决策条数     ∈ [-1, 1]
    null  ：这天这只 /tradability 不可交易或 no_data；或题面三条因子在这格全空；
            或当天一条决策都没有（系统没给出看法）
    flat  ：当天有决策，但**每一条都是 no** —— 交易员看过之后明确不持有

两件刻意没做的事：

1. **score 恰好为 0 时不改写成 `flat`。** 0 是买卖抵消算出来的分数；
   题面写着「主动空仓不得写 0」，反过来把真实的 0 分改写成 flat 同样是编语义。
2. **凑不满面板不补格子。** 预算只够几天两只，就交几格。题面要的是
   csi300 × 约 140 日，差额是事实，接入层不替它填。

## 5. 已知偏离

| # | 偏离 | 为什么 |
| --- | --- | --- |
| 1 | 只跑 2 只 × 4 天 = 8 格 | 每 run 100 次调用的闸。要跑满面板得同时抬 `--max-calls` 与三个规模变量，那是预算裁定不是代码问题 |
| 2 | 隔夜价格发现被参考价替换掉了 | §3.3 |
| 3 | 上游 `prompt/agent_prompt.py` 已改成四只股票（A/B/C/D），`agent.py` / `main.py` 仍只喂两只 | 上游 HEAD 自身不一致。`SEASONAL_FINANCIAL_REPORT` 要 `stock_c_report`/`stock_d_report` 而 `plan_stock` 不给 —— 只有在 `util.SEASON_REPORT_DAYS`（`[12, 78, 144, 210]`）那几天才走得到，本接入 `TOTAL_DATE ≤ 11`，**没碰到**。若要跑更长的窗口，这里会炸 |
| 4 | 上游 `requirements.txt` 没有逐字照抄 | `pandas==1.3.5` / `protobuf==3.20.3` 是 Python 3.9 时代的轮子，统一基座是 3.12。实装清单在 `requirements.gb.txt`，解析结果在镜像里的 `/opt/stockagent/resolved_deps.txt` |
| 5 | `procoder` 用 `--no-deps` 装 | 它声明 `black` / `python-dotenv` / `roman` 三个依赖，而代码里只 import 了 `roman`（AST 核过）。少装一个 `black` 也少一条镜像里的路 |
| 6 | 贷款 / 破产 / 论坛这几条支线跑了但不进产物 | S5 只要信号。它们仍然消耗调用、仍然影响 agent 的持仓与心态 —— 那是这个系统的一部分，不是可以关掉的开关 |
| 7 | 上游 `record.py` 的 `AgentRecordDaily(date, agent.order, loan)` 与它自己的 `__init__(self, agent, date, loan_json)` 形参顺序对不上 | 上游的 bug，只影响它自己写的 xlsx 列，不影响信号。**没有替它改** |

## 6. 许可证

**`none_declared`。** 上游仓库里没有 `LICENSE` 文件，GitHub API 的 `license`
字段是 `null`，README 里也没有许可证声明。所以 `pin.json` 写的是
`none_declared` 而不是猜一个 MIT。

本接入的用法是在内网做研究性评测、镜像不对外分发，按这个用法没有问题。
**如果发布材料要附带这个镜像、或把上游代码随论文发出去，需要先向作者确认授权。**

`procoder`（`dhh1995/PromptCoder` @ `87155427`）带 `LICENSE` 文件是 **Apache-2.0**，
而它 `setup.py` 的 classifier 写的是 MIT —— 上游两处自相矛盾，以 LICENSE 文件为准。

## 7. 复现

```bash
PY=/data/shared/genebench/env/bin/python; REPO=/data/shared/genebench/repo; cd "$REPO"
CTX=/data/genebench_runner/build/stockagent          # f02 上的构建上下文

# ① 构建上下文（在 f01；两个 tarball 与垫片都要在里面）
ssh ljn@192.168.1.219 "mkdir -p $CTX"
scp -r integrations/stockagent integrations/genebench_client \
       /data/shared/genebench/scratch/rehearsal_2_7/ctx/stockagent-src-e2a9c05.tar.gz \
       /data/shared/genebench/scratch/rehearsal_2_7/ctx/promptcoder-8715542.tar.gz \
       ljn@192.168.1.219:$CTX/

# ② 构建（在 f02；f01 没有容器运行时）
ssh ljn@192.168.1.219 "cd $CTX && umask 022 && docker build -t gb-stockagent-u:r1 -f stockagent/Dockerfile ."
ssh ljn@192.168.1.219 "docker images --digests gb-stockagent-u:r1"     # digest 变了要回到 ③

# ③ 无头自检（在 f02；**不调模型**，只打生产网关几十次 GET，不需要 gateway_lock）
ssh ljn@192.168.1.219 "cd $CTX && sh smoke_f02.sh"                   # 期望最后一行 RESULT SMOKE-OK

# ④ 出集（--digest 用 ② 记下的那个）
DIG=sha256:fea1e2b0aa9cdb648ceffe1b258f93d66a9d1d1e5418552ed780248d8e6226fd
STG=/data/shared/genebench/staging/i_rehearsal_s5-eco-01; rm -rf "$STG"
$PY ops/export_bundle.py s5-eco-01 --staging "$STG" --digest "$DIG" --image gb-stockagent

# ⑤ 推送（bundle 只走守门脚本；exec 树必带 --with-launch-data）
ops/push_bundle_to_f02.sh "$STG/tasks/s5-eco-01" \
    /data/genebench_runner/i_rehearsal/runner/tasks "$STG/s5-eco-01.manifest.json"
ops/push_exec_to_f02.sh --with-launch-data

# ⑥ 真跑（必须包在网关锁里；**--seq 要比已用过的大**）
$PY ops/gateway_lock.py --what "2.7:真跑 s5-eco-01 stockagent" -- \
  ssh -o ConnectTimeout=120 ljn@192.168.1.219 \
  "umask 022; export PYTHONDONTWRITEBYTECODE=1; cd /data/genebench_runner && \
   python3 exec/ops/run_f02_a1.py \
     --bundle   /data/genebench_runner/i_rehearsal/runner/tasks/s5-eco-01 \
     --manifest /data/genebench_runner/i_rehearsal/runner/tasks/s5-eco-01.manifest.json \
     --config-id cfg-stockagent-deepseek --arms strict,open --seq 1 \
     --timeout 1500 --max-calls 100 --max-tokens 3000000 \
     --run-root /data/genebench_runner/i_rehearsal/runs \
     --results-dir /data/genebench_runner/i_rehearsal/results"

# ⑦ 结算（--remote 要多一层 runs/）
$PY ops/score_runs.py --batch i_rehearsal --remote /data/genebench_runner/i_rehearsal/runs/runs
```

## 8. 判据

```bash
ssh finance01-ts 'cd /data/shared/genebench/repo && ulimit -n 8192 && \
  /data/shared/genebench/env/bin/python -m pytest ops/test_integration_stockagent.py -q -p no:cacheprovider'
```

要 import 上游包的那一族在 f01 上 **skip**（上游只装在镜像里），
真门是 `smoke.py` 的 `upstream.replacement_points` 与 `gemini.trap` 两项 ——
它们在 ③ 里跑，而且是**在真镜像里**跑。

---

## 9. 命名

镜像 `gb-stockagent-u:r1`、配置 `cfg-stockagent-deepseek` —— 跟的是仓库里
已落地的十一个 harness/接入的约定（`-u` = 统一基座；`cfg-` 前缀）。
**指南 §1② 的两个例子给的是 `gb-<id>:r1` 与 `<id>-deepseek-v3`**，
那两个写法在仓库里只有 `example_minimal` 自己在用。演练第一版照指南写，
收口时改成了大多数的写法，并把这条差异写进了指南（见
[`ops/reports/integrations_rehearsal.md`](../../ops/reports/integrations_rehearsal.md) findings F-02）。
