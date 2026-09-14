# `quantagent` —— QuantAgent 接入 GeneBench（P2）

| | |
| --- | --- |
| 上游 | [Aurora-73/QuantAgent](https://github.com/Aurora-73/QuantAgent)（MIT） |
| 钉住 | commit `4027f572f348ed7794c32e7401048ee259f2fcc5`（2026-07-08），tarball sha256 `abd4184b…`（`pin.json`） |
| 镜像 | `gb-quantagent-u:r1`，digest 见 `Dockerfile` 顶部 |
| 配置 | `cfg-quantagent-deepseek` |
| 跑到哪个阶段 | S2（见 `../COVERAGE.md`） |
| 模型调用 | **0 次**（见下「上游自己不调模型」） |

上游是一个 A 股量化研究系统：自己的数据层（`data/provider.py`）、
自己的因子/回测/组合层（`research/`、`strategies/`），
数据源是 baostock / pytdx / akshare 三条。接它的主要工作量就是**换掉那三条**。

## 上游内核一个字节没改

只用了上游自己的扩展点：

| 用到的上游件 | 扩展点 | 我们做了什么 |
| --- | --- | --- |
| `data/provider.py::DataProvider.get_stock_daily` | `import akshare as ak` | `glue/gateway_akshare.py` 把网关门面挂到 `sys.modules["akshare"]`（README §1③ 的 (d)），在 `import` 上游**之前**执行 |
| `data/aligner.py::TimeAligner.align_to_trading_days` | `method` 形参 | 题面 `missing_row_policy=keep_missing` 时传 `method=None`（reindex 不填充） |

## 三条原生取数路径，逐条交代

`integrations/README.md` §1③ 说「运行期取数」这一类**靠不住**，得把全部路径找出来。
这个上游正好是三条：

| 路径 | 上游的优先级 | 我们怎么关的 | 靠什么保证 |
| --- | --- | --- | --- |
| `baostock` | 行情**首选** | 镜像里不装 → `HAS_BAOSTOCK=False` | 结构性：包不在镜像里 |
| `pytdx`（TCP 直连通达信服务器） | 指数**首选** | 镜像里不装 → `HAS_PYTDX=False` | 结构性 + 出向白名单里没有那两个 IP |
| `akshare` | 兜底 | 装垫片，并补上垫片没有的 `stock_zh_a_daily` | 门面的 `__getattr__` 转给垫片的 fail-closed 实现 |

**第三条上有一个会静默吃掉结果的坑**：上游调的是 `ak.stock_zh_a_daily`，
而垫片实现的是 `ak.stock_zh_a_hist`。垫片对没实现的名字返回一个抛 `NoData` 的可调用对象，
而上游那一行外面包着 `except Exception: return pd.DataFrame()` ——
于是**表现是「这只股票取到 0 条」，不是报错**。`glue/gateway_akshare.py` 就是补这一条的。

## 已知偏离（每一条都影响读数，别当作实现细节）

1. **复权口径由接线层钉，不由上游**。上游 `_akshare_stock_daily()` 调
   `ak.stock_zh_a_daily` 时**不传 `adjust`**（它的 `adjust` 形参只在 baostock 分支上用），
   真 akshare 的默认是不复权。题面声明 `adjust=post` 时照上游原样跑会静默产出一份
   口径不同的价格。所以 `glue/gateway_akshare.set_adjust()` 从题面取口径显式钉住，
   认不出来的值**当场抛，不回落不复权**。
2. **对齐方式的默认值是 `ffill`**。`TimeAligner.align_to_trading_days` 的
   `method` 默认 `"ffill"` —— 照默认跑就是**静默补行**，而补出来的行在面板上
   与真行情长得一模一样。接线按题面的 `missing_row_policy` 显式传。
3. **逐只标的取数**。上游的数据层是 per-ticker 的（`get_stock_daily(ticker, …)`），
   所以一个 csi300 的面板 = 300 次 `/bars`（要复权再加 300 次 `/adj`），
   而不是一次多代码请求。**S2 的 `eco` 变体明确要求「网关请求次数尽量小」——
   这个接入在那道题上会因为上游的数据层形状而吃亏。** 这是被测系统的性质，不是缺陷，
   不要为了好看去绕过它的数据层。
4. **成交量单位**：垫片按 akshare 原生口径把 `volume` 换算成「手」（÷100），
   上游只做透传。面板里的 `volume` 因此是「手」，不是「股」。
5. **上游的 `data/__init__.py` 会 import `storage`（duckdb）**，所以镜像里装了 `duckdb`
   —— 它在本接入的路径上一行都没跑到，装它只是为了 `import data.provider` 能过。

## 上游自己不调模型

上游 `agents/committee.py` 顶部写着：ADR-001 把原来的 `AICriticAgent`（OpenAI LLM）**删掉了**，
项目定位是 MCP Server，LLM 推理由外部编排方提供。
所以这个接入的真跑 **0 次模型调用**，`config.yaml` 的 `model` / `base_url` / `api_key_env`
三个键**登记而不使用**（键集是闭集，不填就红）。

> 这是接入模型的一个盲区：`config.yaml` 假设每个被测系统都自己调模型。
> 「接进来了，但它的 LLM 在系统之外」在今天的配置模型与 `COVERAGE.md` 格值里都表达不出来。
> 已登记票据（`ops/tickets_inbox/6.4.md`）。

## 复现

```sh
GB=/data/shared/genebench; PY=$GB/env/bin/python; cd $GB/repo

# ① 构建上下文送到 f02（三样：接入目录、垫片、上游 tarball + SUMS）
scp -r integrations/quantagent integrations/genebench_client \
       ljn@192.168.1.219:/data/genebench_runner/build/quantagent/
# 上游 tarball 与 SUMS 放**上下文根**（Dockerfile 里 COPY 的就是根上那两个文件）

# ② 构建（在 f02，从 f01 发起）
ssh ljn@192.168.1.219 "cd /data/genebench_runner/build/quantagent && \
    docker build -t gb-quantagent-u:r1 -f quantagent/Dockerfile ."
ssh ljn@192.168.1.219 "docker image inspect --format '{{.Id}}' gb-quantagent-u:r1"

# ③ 出集 → 推送
DIG=sha256:<上一步那一串>; STG=$GB/staging/i_rehearsal_v1_s2-ops-01; rm -rf "$STG"
$PY ops/export_bundle.py s2-ops-01 --staging "$STG" --digest "$DIG" --image gb-quantagent-u
ops/push_bundle_to_f02.sh "$STG/tasks/s2-ops-01" \
    /data/genebench_runner/i_rehearsal_v1/runner/tasks "$STG/s2-ops-01.manifest.json"

# ④ 同步 exec 树（第一次接入必须带这个开关，否则 f02 上 by_id 找不到 config_id）
ops/push_exec_to_f02.sh --with-launch-data

# ⑤ 真跑（必须包在网关锁里）
$PY ops/gateway_lock.py --what "quantagent:真跑 s2-ops-01" -- \
  ssh -o ConnectTimeout=120 ljn@192.168.1.219 \
  "umask 022; export PYTHONDONTWRITEBYTECODE=1; cd /data/genebench_runner && \
   python3 exec/ops/run_f02_a1.py \
     --bundle   /data/genebench_runner/i_rehearsal_v1/runner/tasks/s2-ops-01 \
     --manifest /data/genebench_runner/i_rehearsal_v1/runner/tasks/s2-ops-01.manifest.json \
     --config-id cfg-quantagent-deepseek --arms strict,open --seq 1 \
     --timeout 1500 --max-calls 100 --max-tokens 3000000 \
     --run-root /data/genebench_runner/i_rehearsal_v1/runs \
     --results-dir /data/genebench_runner/i_rehearsal_v1/results"

# ⑥ 结算（--remote 比 --run-root **多一层 runs/**，少写那层会静默退 0）
$PY ops/score_runs.py --batch i_rehearsal_v1 --remote /data/genebench_runner/i_rehearsal_v1/runs/runs
```
