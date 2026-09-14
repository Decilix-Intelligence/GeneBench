# GeneBench 接入指南 —— 把你的系统接成被测方

**读者**：你手上有一个已经能跑的量化研究系统（自己的 pipeline，或 RD-Agent /
TradingAgents 这类已发表系统），想让它作为**被测方**跑 GeneBench 的八个阶段。

本文是**操作手册**：从建目录到第一次真跑，每一步都给一条可以直接复制的命令。
**规则**不在这里 —— 端点参数、错误码、`as_of` 语义、产物 schema、禁止事项
全部在 [`P2_CONTRACT.md`](P2_CONTRACT.md)，那一份是从代码逐行读出来的，本文不复制一份
（复制的那份必然漂）。

| 你要找的 | 去哪 |
| --- | --- |
| 网关怎么用、产物长什么样、什么不许做 | [`P2_CONTRACT.md`](P2_CONTRACT.md) |
| 取数垫片（`yfinance` / `tushare` / `akshare` 兼容层） | [`genebench_client/README.md`](genebench_client/README.md) §1–§5 |
| 产物助手 `emit` | [`genebench_client/README.md`](genebench_client/README.md) §7 |
| 通用 CLI harness（P1/P3）怎么加 | `harnesses/README.md` |
| 一个 30 行、真能跑的 P2 系统 | [`example_minimal/`](example_minimal/) |
| 谁接了什么、跑到哪个阶段 | [`COVERAGE.md`](COVERAGE.md) |
| 接入花了多少工时 | [`COST.md`](COST.md)（生成，勿手改）、[`cost/`](cost/) |

---

## 0. 三个范式，一页说清

GeneBench 不假设被测方长什么样。它只规定**边界**：题面从哪读、数从哪取、产物写到哪。
边界之内怎么组织，是三种形态：

| 范式 | 被测方是什么 | 谁写适配 | 容器里多了什么 | 加在哪 |
| --- | --- | --- | --- | --- |
| **P1** | **通用 CLI harness**（Codex、OpenHands、Claude Code 这类"给它一个目录和一句话，它自己写代码"的工具） | 我们（范式层）写一次，所有模型共用 | 无 | `harnesses/<name>/`，见 `harnesses/README.md` |
| **P2** | **专用系统**（自带研究流程与内部数据抽象：因子挖掘框架、多智能体投研、你自己的 pipeline） | **你**（被测方） | 无 | `integrations/<id>/`，**见本文** |
| **P3** | **P1 + 协议工件**（同一个通用 harness，但 `/task/protocol/` 存在） | 与 P1 同 | `/task/protocol/` | 与 P1 同，`launch.json` 里 `paradigm: "P3"` |

**这条分界是纪律不是偏好**：接口定义在范式层，接入责任在被测方。
我们**不为任何单个系统写内核适配** —— 那样做出来的分数是"我们替它改了多少"的函数，
不是它本身的能力。已发表系统的接入作为**示例**放在 `integrations/<id>/`，
写它们的是接入者的手，不是内核。

### P3 的 `/task/protocol/` 到底是什么

它是**协议臂（strict）**多拿到的那一份东西，注入器按臂精确投放
（`runner/inject.py`；open 臂**没有**这个目录，那是干预本身，不是遗漏）。里面是：

* `validate_artifact.py` —— 离线自检器，`python3 /task/protocol/validate_artifact.py /task/artifact.json`；
* 三份数据驱动的规则 JSON（含 `artifact_schema.json`）。

**它是被动存在的**：没有任何东西要求你去读它、去调用它。
系统可以**完全无视**它照样合规；也可以在写完产物后跑一遍自检、按 findings 修回去。
两臂的差异**只能**是「题面的表达形式」与「协议工件的有无」两项 ——
所以你的系统**不许读 `GENEBENCH_ARM` 去改行为**（改超参、改重试、改模型都不行）。
读到 `arm` 只用来填产物信封里的 `arm` 字段。

> P3 与 P1 是**同一个 harness、同一个镜像、同一份配置、同一个超时**，
> 只是那道自检的门开着。差异被 `ops/specs/fairness_protocol.md` 的穷举清单守着。

---

## 1. P2 接入：八步

下面每一步都有一条可以直接复制的命令。约定：

```bash
PY=/data/shared/genebench/env/bin/python
REPO=/data/shared/genebench/repo
cd "$REPO"
```

`<id>` = 你的目录名，也是成本账本里的系统名（`integrations/<id>`）；
`<task>` = 任务 id（如 `s2-cor-01`）；`<batch>` = f02 上的 run 根（如 `m6b`）。

### ① 动手之前先起成本表

```bash
$PY -m integrations.cost begin --system <id> --who agent --note "起手"
```

**漏了这一步后面补不回来**：`begin` 记下的 HEAD 就是算 LOC 的唯一基线。
详见 [§5 接入成本怎么记](#5-接入成本怎么记)。

### ② 建目录 —— 五件套

```bash
mkdir -m 700 integrations/<id>
```

只建**你自己这一个目录**。目录里恰好这五样（外加你的系统代码或一份 pin）：

| 文件 | 干什么 | 硬约束 |
| --- | --- | --- |
| `Dockerfile` | 构建镜像 | `FROM gb-base:bookworm-r1`（统一基座）；依赖**全部在构建期装完**，运行期断网 |
| `launch.json` | 怎么在容器里把它启动起来 | 键集**恰好六个**，缺一个多一个都在 import 期 `RegistryError` |
| `config.yaml` | 被测配置（模型、base_url） | 键集**恰好七个**；先写 `enabled: false` |
| `pin.json` | 钉死你接的是哪一版（D-21） | 见下 |
| `README.md` | 这一个接入的说明 | 镜像名与 digest、已知偏离、怎么复现 |

**`Dockerfile`** —— 三行就是全部骨架，完整的一份（含构建上下文怎么摆、
`HOME` 指哪）在 [`example_minimal/Dockerfile`](example_minimal/Dockerfile)：

```dockerfile
FROM gb-base:bookworm-r1
RUN pip install --no-cache-dir "setuptools>=61" wheel      # ← 少了它下一行必炸，见下
COPY genebench_client/ /opt/genebench_client/
RUN pip install --no-cache-dir --no-index --no-build-isolation /opt/genebench_client
COPY <id>/ /opt/<id>/                # 你的系统；从 PyPI 装的话在这里 pip install
RUN chmod -R a+rX /opt/<id> /opt/genebench_client          # ← 少了它容器读不到入口，见下
```

**依赖不是「你用到的那几个」，是 `import` 闭包。** 上游的 `<pkg>/__init__.py`
多半会把整个包的模块都 import 一遍 —— 你只想用 `data.provider`，`import data.provider`
却会连带跑 `data/__init__.py` → `storage` → `configs.settings` → `yaml` / `pydantic`。
卡 6.4 的第一次构建就红在这里，而报文只说少了 `yaml`，不说是谁拉进来的。
**最便宜的判据是把 `pin.json` 的 `runnable_check` 直接写成 `Dockerfile` 的最后一行**：
它在构建期就把 import 闭包跑通一次，比真跑一遍两臂早 20 分钟发现问题。

**那两行不是洁癖，是四个接入各自撞了一次的东西**（卡 2.6 的三份票据 + 卡 2.7 的演练）：

* **少 `setuptools`**：基座是 `python:3.12-slim` 血统，**不带 `setuptools`**，
  于是下一行 `--no-build-isolation` 当场
  `pip._vendor.pyproject_hooks._impl.BackendUnavailable: Cannot import 'setuptools.build_meta'`。
  这条**只在构建期**出现，报文里一个字都不提「你少装了什么」。
* **少 `chmod -R a+rX`**：仓库文件是 `0600`（红线 5 要求 `$GENEBENCH_ROOT` 全树 `go-rwx`），
  `COPY` 保模式，而容器以**非 root** 跑 →
  `python3: can't open file '/opt/<id>/run.py': [Errno 13] Permission denied`，
  两臂十几秒退出、判 `no_artifact`。**症状与 §3.7 那四条一模一样，但都不是。**

> `example_minimal/Dockerfile` 里也没有这两行 —— 它没有被非 root 跑过（票据 N-?）。

**`launch.json`（六个键，一个不能多一个不能少）**：

```json
{
  "harness": "<你的 id>",
  "paradigm": "P2",
  "image": "gb-<你的 id>:r1",
  "command": ["sh", "-c", "cd /task && python3 /opt/<你的 id>/run.py"],
  "env_required": ["GENEBENCH_GATEWAY", "OPENAI_BASE_URL", "OPENAI_API_KEY"],
  "notes": "一句话说清这个接入是什么"
}
```

两条铁律（踩过，N-101）：

1. **命令里的 `$` 一律写 `$$`** —— 这份 JSON 会经过一层 compose 变量展开，
   写一个 `$` 的结果是变量被提前吃掉，而现场表现是"命令看起来对、跑起来是空的"。
2. **base URL 只从 `env_required` 列出的变量取，绝不写死主机名** ——
   写死就绕过了边车，那条路上没有 usage、没有预算闸、什么都看不见。

**`config.yaml`（七个键）**：

```yaml
config_id: <id>-deepseek-v3
harness: <你的 id>
model: deepseek-chat
base_url: https://api.deepseek.com/v1
api_key_env: DEEPSEEK_API_KEY
note: 一句话
enabled: false
```

`enabled: true` 才合并进 `CONFIGS`（与内置 `config_id` 重名即红）；`false` 只进
`PENDING_CONFIGS`。**无论真假**都过三条判据：`https`、变量名以 `_API_KEY` 结尾、
host 不在 `MARKET_DATA_HOSTS` 里。第三条是红线：行情/新闻源域名一律不得入表 ——
那等于让被测系统绕过数据面。

> **`config.yaml` 假设每个被测系统自己调模型 —— 有一类系统不是。**
> MCP Server 形态的系统（LLM 推理由**外部编排方**提供，系统自己只暴露工具）
> 没有 `model` / `base_url` / `api_key_env` 可填，而键集是**闭集**，不填就红。
> 今天的做法是照填并在 `note` 里写明「登记而不使用」，真跑的模型调用数是 0
> （例子：`integrations/quantagent/`，上游 ADR-001 把 LLM 移出了系统）。
> `COVERAGE.md` 的五个格值也表达不出「接进来了，但它的 LLM 在系统之外」——
> 已登记票据。**别因为调用数是 0 就以为接入失败了。**

#### 镜像名与 `config_id`：例子与实践不一致

上面两个例子里的 `gb-<你的 id>:r1` 与 `<id>-deepseek-v3`，**在这个仓库里只有
`example_minimal` 自己在用**。已落地的十一个 harness/接入用的是：

| | 例子给的 | 实际约定 | 用它的有 |
| --- | --- | --- | --- |
| 镜像 | `gb-<id>:r1` | **`gb-<id>-u:r1`**（`-u` = 统一基座） | 11 / 13 |
| `config_id` | `<id>-deepseek-v3` | **`cfg-<id>-deepseek`** | 5 / 7 个接入 |

判据不管你选哪个（三条门只看 https / `_API_KEY` 后缀 / host 不在 `MARKET_DATA_HOSTS`），
**但跟着大多数走**能让 `docker images` 与 `ops/api_usage.py` 的输出读起来是一张表。
另外：`launch.json` 的 `image` 与你 `docker build -t` 打的 tag **没有守门**，
对不上的表现是「构建成功了，跑的还是旧镜像」——不会有任何东西变红。

**`harness` 名与 `config_id` 在 `harnesses/` 与 `integrations/` 两棵树之间也不许重复。**
两处发现入口（`runner/c42/harness_commands.py` 的 `discover_launch_specs()` 与
`runner/registry.py` 的 `load_data_configs()`）一视同仁地遍历两棵树，重名当场
`RegistryError` —— 静默取其一会把「我明明加了却没生效」变成一次长调查。

**`pin.json`（D-21）** —— 钉死"你接的到底是哪一版"，否则半年后没人能复现：

```json
{
  "paper_url": "https://arxiv.org/abs/....",
  "repo_url": "https://github.com/org/project",
  "commit": "<40 位 sha>",
  "dist": "project==0.4.2",
  "dist_repo_url": "https://pypi.org/project/project/0.4.2/",
  "license": "MIT",
  "runnable_check": "python3 -c \"import project; print(project.__version__)\""
}
```

* `commit` 与 `dist` 至少要有一个；**从 PyPI 装的必须同时给 `dist` 与 `dist_repo_url`**
  （版本号不等于源码，`dist_repo_url` 是那个版本的落点）。
* `runnable_check` 是一条**在镜像里能跑**的命令，用来回答"这个镜像里到底装没装上"。
* GitHub 在构建网里**不保证可达**。不可达时的正路是：在本地下载源码 tarball
  （记下 commit sha 与 sha256）→ `scp` 到 f01 → `scp` 到 f02 → `Dockerfile` 里 `COPY` 进去。
  **不要**在 Dockerfile 里 `git clone` 一个可能连不上的地址。

### ③ 把系统的数据层换成垫片

**先认一下你的系统属于哪一类** —— 三类的工作量与「可核查性」完全不同：

| 类型 | 取数发生在哪 | 你的活 | 「取数是否全部经过数据面」靠什么保证 |
| --- | --- | --- | --- |
| **运行期取数**（多智能体投研这一类） | agent 循环里，随时 | 找出**全部**取数路径并替换 | **靠不住**：卡 2.6 有一个接入的三条原生取数路径里，接入者自己只找到第一条，第二条是真跑报错抓出来的，第三条是容器出向白名单 403 抓出来的 |
| **离线数据集**（启动时读一个 pkl） | 装数据时，一次 | 换掉那一次 | 结构保证：运行期根本不出网 |
| **无数据**（自带一个封闭模拟市场） | **不存在** | 把它虚构的那部分换成真的 | 结构保证；但反过来 —— 它对真实标的一无所知，你得把真数据**喂进它的 prompt** |

**第一类怎么把「全部」找出来**（比事后 grep 便宜，卡 6.4 照这条走的）：

```bash
# ① 上游在**哪些地方**试着 import 行情库 —— 这就是取数路径的清单
grep -rn "import \(akshare\|tushare\|yfinance\|baostock\|pytdx\|jqdatasdk\)" <上游>
# ② 它自己的开关名（多数框架写成 HAS_xxx / _HAS_xxx / try-import 兜底）
grep -rn "HAS_" <上游> | head
```

找到之后**首选「不装」而不是「替换」**：镜像里没有那个包 → 上游的 `HAS_xxx=False`
→ 那条路径**结构性**关闭，不依赖你替换得全不全。留一条给垫片顶替就够了。
卡 6.4 的 `QuantAgent` 是三条（baostock 首选 / pytdx 首选 / akshare 兜底），
逐条交代在 `integrations/quantagent/README.md`。

第一类的自检见 §3 末尾那条；后两类的工作量主要在「喂什么、喂到哪一天为止」。

这是 P2 接入的**主要工作量**，也是唯一一件"必须改被测系统代码"的事。
垫片 [`genebench_client`](genebench_client/) 让取数自动**经网关、带身份、受 `as_of` 约束、
落 access_log**，你不需要自己拼 URL、不需要自己管身份头。

**三种 compat 的替换方式**，按你的系统原来用什么选：

```python
# ── (a) 原来 import yfinance
- import yfinance as yf
+ from genebench_client.compat import yfinance as yf
# 之后 yf.download / yf.Ticker(...).history 照原样调。
# 注意三条已知偏离：end 是右开（与 yfinance 一致，垫片替你减一天）；
# Adj Close 的基准是「窗口内 as_of（含）之前最后一个 adj_factor」而不是「今天」；
# 没有 Dividends / Stock Splits 两列（网关不发明细，不编两列 0.0）。

# ── (b) 原来 import tushare
- import tushare as ts
+ from genebench_client.compat import tushare as ts
  pro = ts.pro_api()                 # set_token(...) 收下就扔，不存不记不发
# 单位按 tushare 原生口径换算好了：vol 是「手」、amount 是「千元」。
# daily 没有 pre_close / change / pct_chg（网关不发 pre_close，拿前一日收盘去减
# 在除权日就是错的）；index_weight 没有 weight 列（KeyError 是有意的：
# 给一列 NaN 会让 weight.sum() 静默变 0，那是全零权重组合）。

# ── (c) 原来 import akshare
- import akshare as ak
+ from genebench_client.compat import akshare as ak
# 成交量「手」、成交额「元」；period 只支持 daily；
# stock_zh_a_spot 的「实时」= as_of 当日，且一次约 20 次网关请求，注意预算。

# ── (d) 改不了 import 的系统（第三方库内部自己 import）
import genebench_client.compat as compat
compat.install()          # 顶替 sys.modules，之后 `import yfinance` 拿到的是垫片
```

> ⚠ **三个 compat 层实现的函数集是有限的，而「超出的部分」会静默变成空结果。**
> 垫片对没实现的名字返回一个抛 `NoData` 的可调用对象（fail-closed，为的是不让上游
> 用 `hasattr` 探测后静默换源）；但**多数上游把取数那一行包在 `except Exception:
> return pd.DataFrame()` 里** —— 于是现场表现是「这只标的取到 0 条」，不是报错。
> 卡 6.4 实测：`QuantAgent` 调的是 `ak.stock_zh_a_daily`，而垫片实现的是
> `ak.stock_zh_a_hist`，一字之差，全表为空。
> **接入前先把上游真正调用的函数名列出来，与垫片的函数表对一遍**
> （表在 [`genebench_client/README.md`](genebench_client/README.md) §4）；
> 差的那几个由**你**在接线层补上（照上游的调用形状包一层垫片已有的函数即可，
> 例子见 `integrations/quantagent/glue/gateway_akshare.py`）。

> **compat 层的 `fields` 只裁剪返回值，不改变网关上的读取集。**
> 三个 compat 层一律按上游库的**完整列集**向网关请求 `fields`：
> `pro.daily(ts_code=..., fields="ts_code,trade_date,close")` 返回 3 列，
> 但 access_log 里那条 `/bars` 的 `params.fields` 仍是
> `open,high,low,close,volume,amount`。`declared_reads` 探针只看 access_log
> （`P2_CONTRACT.md` §2.4），所以**经 compat 层取数就控制不了声明读取集** ——
> S3 类任务必须改用 `gb.client().bars(codes, start, end, fields=[...])`。
> 逐层见 [`genebench_client/README.md`](genebench_client/README.md) §4 的「compat 的 `fields`」行。

> `install()` 是**便利不是保证**：已经 `import` 过 `yfinance` 的模块持有旧对象，
> 顶替对它无效。正路仍然是改 import；`install()` 要在**任何业务模块之前**执行。

**没有对应上游库的系统**直接用网关客户端：

```python
import genebench_client as gb
gb.set_as_of(as_of)                                    # 启动时一次
cli = gb.client()
df  = cli.bars(["600000.SH"], "2026-06-01", "2026-06-30", fields=["close", "volume"])
```

`fields` **显式传**。不传等于"读了全部列" —— S3 的「声明读取集 vs 实际读取集」探针
从 access_log 反推出来的就是全表，而**S3 任务不传 `fields` 是畸形不是缺省**。

**qlib provider 树**（系统建在 qlib 上时）：

```python
import qlib
from genebench_client import qlib_provider
qlib.init(**qlib_provider.qlib_init_kwargs())          # provider_uri=/task/provider, region=cn
```

provider 是**注入期物化好的既成事实**（PA-6，物化在可信方，不在容器里），
到了容器里只需要知道它在哪。不在时抛 `ProviderMissing`，**绝不回落 qlib 社区 channel** ——
那是运行期换数据源，而且社区那份 `amount` 是千元、`volume` 是手，与本环境差 1000× / 100×。
路径覆盖用 `GENEBENCH_PROVIDER_URI`。

**替换完的自检**：全仓 grep 一遍，确认没有任何代码路径能连到行情/新闻源域名 ——
出向白名单里只有模型 API，`import` 期就会拦（`runner/c41/egress_proxy.py`），
但拦在你手上比拦在真跑时便宜。

### ④ 配置指向 `/task`

容器的 `working_dir` 是 `/task`。**题面只有一个入口**：

| 东西 | 路径 | 备注 |
| --- | --- | --- |
| 题面 | `/task/INSTRUCTION.md` | **唯一题面**；`as_of` / 窗口 / universe / 产出路径全在它的固定槽里 |
| 结构契约 | `/task/{stage}.json` | 两臂都有；**`properties.declarations.required`** 列全了要写哪些声明键（顶层**没有** `declarations` 这一键）|
| 夹具 | `/task/<文件>` | 题面 `inputs[]` 点名的才有 |
| qlib provider | `/task/provider/` | 配了 provider 的题才有 |
| 协议工件 | `/task/protocol/` | **只有 strict 臂有** |
| **你的产物** | `/task/artifact.json` | 每题都要 |
| **产出文件** | 题面固定槽「产出文件」点名的那一个 | **S2 = `/task/panel.csv`、S3 = `/task/values.parquet`、S7 = `/task/ledger.parquet`**；其余阶段没有这一项 |

声明键的读法（顶层键集是 `[$schema, $id, title, type, required, properties, x-genebench]`，
新出的 bundle 还多一个 `x-gateway-fetch-contract`；**没有** `declarations` 这一键 ——
照 `[...]["declarations"]["required"]` 写当场 `KeyError`）：

```python
json.load(open(f"/task/{stage}.json"))["properties"]["declarations"]["required"]
```

等价且更省事：`genebench_client` 的 `emit.declaration_fields("S2")`（垫片 README §7.6）。

**`task.yaml` 不在容器里。** 它在宿主的 `run_dir/bundle/` 下。凡是你在别处读到
"从 task.yaml 读 as_of"的说法，对 P2 不成立。

**`/task` 下你该新建的东西恰好是两类**：`artifact.json`，**加上**题面固定槽「产出文件」
点名的那一个（S2/S3/S7 有，其余阶段没有）。它的路径与规范序列化由题面**逐字给出** ——
写端的唯一函数体是 `genetask/file_contract.py`（`FILE_SPECS` / `write_contracted`），
采集侧的允许集是 `runner/c42/harvest.py` 的 `PRODUCED_BY_STAGE`，两边同源。
`panel_ref.sha256` / `values_ref.sha256` 就是**那个文件的字节摘要**，见垫片 README §7.3。

**除这两类以外的中间产物写容器可写层（`/tmp`），不要落进 `/task`。** run dir 有 P8 文件集封闭核对：
`work/` 里多一个不在允许集里的文件就是"来路不明"，直接红。同理，`HOME` / `<TOOL>_HOME` 不可写时
请指到 `/tmp/...`，**不要指到 `/task` 下**。

> **这一条与 `harnesses/README.md` 有出入，两处原文都摆在这里（CONFLICT，不是笔误）。**
> 那一份写的是「把 `HOME`（以及 `<TOOL>_HOME` 之类）指到 **`/task` 下的可写处**并
> `mkdir -p`」，六个 P1 harness 的 `launch.json` 也都这么写（`/task/.codex`、
> `/task/.claude_home`……）。本文对 P2 给的是 `/tmp/...`，理由是**容器里的 `/task`
> 就是 run dir 的 `work/` 本身**（`runner/c41/runner_core.py` 里那行
> `- {workdir}:/task`），落在它下面的东西会进 `run.json` 的 `unexpected` ——
> 阶段三实测过一次真跑在 `/task` 下多出 297 个 bun 转译缓存文件。P1 那边之所以
> 仍写 `/task`，是因为**第三方 CLI 的 `HOME` 我们只能从外面设**，权衡之后接受了
> 那份 `unexpected`；**P2 的代码是你自己的，没有这个约束**。两条都跑得通，
> 但别把两份手册读成一份 —— 你按本文走。

#### 题面有两种写法，你的解析器必须两种都认

两臂唯一允许不同的东西之一就是**题面的表达形式**（`genetask/render.py:59-61`）。
同一道题，同一个槽，两臂长这样：

| 槽 | strict 臂 | open 臂 |
| --- | --- | --- |
| `as_of` | `as_of=2026-07-31` | `本次任务的 as_of 是 2026-07-31` |
| 窗口 | `window=2026-01-05 到 2026-07-31` | `计算窗口（window）是 2026-01-05 到 2026-07-31` |
| universe | `universe=csi300` | `标的范围（universe）是 csi300` |
| 口径行 | `- value_semantics=score（…，接口值 score）` | `- 信号值是可比的分数，不是秩（字段 value_semantics，接口值 score）` |

**只认 `key=value` 的解析器在 open 臂上是零产物、零模型调用、当场 `SystemExit`。**
这是目前为止最贵的一条：卡 2.6 有一个接入就是这么丢掉一整个臂的，
而且它**用掉了那一次允许的重试**（失败原因在我们的链路，不在被测系统）。

两条能照抄的做法：

1. 三个槽写成「锚点词 + 至多十来个非目标字符 + 值」，不要求紧跟 `:` / `=`；
2. 口径行**统一取「接口值」后面那一段**（两臂的这一段是逐字相同的，
   `genetask/render.py:291-309`），字段名从 `- X=` 或 `（字段 X，` 两种写法里取。

**三处会把值偷走、而且产物上完全看不出来的地方**（每一处都值得配一条判据）：

* 题面里有一行 `可用端点：… /universe /tradability` —— 任何「找 `universe`
  后面那个词」的正则都会取到 `tradability`。**网关照样返回一个成分表、
  信号照样算得出来，只是标的池整个换了。**
  防法：锚点前排除 `/` 与 `_`，后面必须有一个真正的赋值记号。
* 口径行里有 `universe_ref=csi300@2026-07-31` —— 里面那个日期恰好与 `as_of` 相同，
  所以取错**不会报错也不会差**，直到某道题的两个日期不一样为止。
  防法：口径行（`- ` 开头那几行）不参与 `as_of` / `window` / `universe` 的取值。
* open 臂的口径行里散文与接口值都在（「分数，不是秩……接口值 score」），
  取散文会把 `rank` 当成答案。防法：只取「接口值」那一段。

> `§2` 那个 30 行示例的 `slot()` **只认 strict 那一种写法**
> （它只在 S1 strict 上走查过）。照着它改的时候，先把这三条补上（票据 N-?）。

产物用 `emit` 写（格式这一层它全包，业务值一个都不替你想）：

```python
from genebench_client import emit
art = emit.emit_s1(fetches=[...], fields_obtained=["close", "volume"],
                   declarations={"calendar_id": "SSE", "universe": "csi300",
                                 "data_version": "v1"},
                   as_of=as_of)
art.write("/task/artifact.json")
```

三件最容易做错的：

1. **题面没说的口径标 `"unresolved"`，不要挑一个默认值填进去。** 静默补全
   (`silent_completion`) 是被单独测量的一族行为，不是"合理的工程决定"。
   `emit` 没有"填默认值"这条路径 —— 填了一定是你自己填的。
2. **`fetched_at` 取响应头 `x-genebench-ts`，不是本地时钟。** 用系统时钟填必判
   `fetch_clock_mismatch`。垫片的 `cli.ledger` 每条都带 `ts`，直接用。
3. **信封的 `task_id` / `config_id` / `arm` 必须与环境变量逐字相等**，
   不符即 `identity_mismatch`，产物**整份不进评分**，没有人会替你改成一致。

### ⑤ LLM 经边车

容器里**只有占位 key**，真 key 由边车注入，你拿不到也不需要：

```python
import os
base_url = os.environ["OPENAI_BASE_URL"]      # 边车的反向代理
api_key  = os.environ["OPENAI_API_KEY"]       # 占位串，照传即可
```

| 变量 | 是什么 |
| --- | --- |
| `OPENAI_BASE_URL` / `OPENAI_API_BASE` / `LLM_BASE_URL` | 边车的模型反向代理 |
| `OPENAI_API_KEY` / `LLM_API_KEY` | **占位 key** |
| `HTTP_PROXY` / `HTTPS_PROXY` | 边车的 CONNECT 代理 —— **允许 CONNECT 的主机集是空集**，任何 CONNECT 一律拒并留痕 |
| `GENEBENCH_GATEWAY` | 数据网关（`NO_PROXY` 含它，走直连） |

* **自带一把 key 直连 → 403 `foreign_credential`**：那是一条未声明的资源，
  它绕开预算闸，也让 usage 归属对不上。
* **每 run 预算的默认值是 100 次调用 / 6,000,000 tokens** —— 权威在
  `runner/registry.py` 的 `RUN_BUDGET`（`max_calls: 100`、`max_tokens: 6_000_000`；
  **N-388**，2026-09-10 由 600,000 抬上来），
  注入器把它写成边车的 `--max-calls` / `--max-tokens`。超了返回 **429 `budget_exceeded`**
  （不是 402，见 [§3 常见失败](#3-常见失败的含义)）。**预算耗尽不是 harness 故障，
  是你这次运行结束了** —— 请把重试与自检的调用数算进去。
* **默认值只是默认档。** `runner/registry.py::BUDGET_TIERS` 按 bundle `task.yaml` 里的
  `stage` 分档（卡 4.3）：**S4 150 次 / 9,000,000 tokens**、**S7 300 次 / 18,000,000 tokens**，
  其余阶段就是上面那条默认的 100 次 / 6,000,000 tokens。注入器调 `registry.budget_for(stage)`
  自动取，接入方不用配。真跑命令里显式给的 `--max-calls` / `--max-tokens` **逐键覆盖档位**。
* **默认档已经按长上下文配过，真跑时什么都不用给。** 6,000,000 的来历就是
  「100 次 × 60k/次」——Codex 实测每次 prompt 43k–68k、opencode 约 30k。
  **2026-09-10 之前本手册教的「一律显式给 `--max-tokens 3000000`」已作废**：
  那是默认档只有 600,000 时文档化的绕法，今天照抄等于把预算**压低**，而且显式值
  **逐键赢过 stage 档位**，S4 的 9M 与 S7 的 18M 会一起被打回 3M。
  撞闸的现场表现不是报错，是「跑了一半就停了」（`budget_exceeded` 只落 `llm_log`）。
* 不许 best-of-N：跑 N 轮就必须交出**选轮规则**，规则只能来自 taskspec，
  选中的 `index` 进 `provenance`。理由是 best-of-N 等于给自己加了一层题目没给的搜索预算，
  **而且没有任何信号会红 —— 分数只是更高一点**。

### ⑥ 构建 → 出集 → 推送 → 真跑

**构建在 f02**（f01 没有容器运行时）。先把构建上下文送过去：

```bash
# 在 f01：把你的接入目录与垫片一起送到 f02 的构建目录
scp -r integrations/<id> integrations/genebench_client \
       ljn@192.168.1.219:/data/genebench_runner/build/<id>/
# 在 f02（只许从 f01 进）：
ssh ljn@192.168.1.219 "cd /data/genebench_runner/build/<id> && docker build -t gb-<id>:r1 -f <id>/Dockerfile ."
docker images --digests gb-<id>:r1      # 记下 digest，写进 <id>/README.md
```

**你的系统本体放构建上下文的哪里**：上面那条 `scp` **只送两样**（你的目录与垫片）——
**上游的 tarball 与它的 `SUMS` 不在里面，要再送一次**，否则下一段那个 `COPY`
当场 `file not found`（卡 6.4 照抄时就少了这两个文件）：

```bash
scp <你的 tarball> SUMS ljn@192.168.1.219:/data/genebench_runner/build/<id>/
```

你的上游源码（tarball / wheel / sdist）也必须在**同一个构建上下文**里，
否则 `COPY` 当场 `file not found`。约定是放**上下文根**，`Dockerfile` 里

```dockerfile
COPY <你的 tarball> /tmp/src/
RUN cd /tmp/src && sha256sum -c SUMS && tar xzf <你的 tarball> -C /opt/<id>/upstream --strip-components=1
```

—— 那个 `sha256sum -c` 是 `pin.json` 里那个哈希唯一起作用的地方。

**这四步不是一条直线：镜像一动就回到第一步。**

```
构建 ──(digest)──▶ 出集 ──▶ 推送 ──▶ 真跑
  ▲                                    │
  └──────── 改了接线层就得重来 ◀────────┘
```

`export_bundle.py --digest` 记的是**那一次构建**的镜像；重建之后 digest 变了，
bundle 的通行证与镜像就对不上。改完接线层直接去真跑，是白跑一次。

**出集**（在 f01；`--digest` 用上一步记下的那个）：

```bash
DIG=sha256:<你的镜像 digest>; STG=/data/shared/genebench/staging/<id>
rm -rf "$STG"
$PY ops/export_bundle.py <task> --staging "$STG" --digest "$DIG" --image gb-<id>
```

**推送 bundle**（**只走这个脚本** —— 它是答案面守门，别用 `scp` 绕过去）：

```bash
ops/push_bundle_to_f02.sh "$STG/tasks/<task>" \
    /data/genebench_runner/<batch>/runner/tasks "$STG/<task>.manifest.json"
```

**同步 exec 树**（第一次接入、或改了 `launch.json` / `config.yaml` 之后必须做，
**必须带 `--with-launch-data`**，否则 f02 上 `by_id` 找不到你新加的 `config_id`）：

```bash
ops/push_exec_to_f02.sh --dry-run              # 先看清单
ops/push_exec_to_f02.sh --with-launch-data     # 真推
```

> 它会把工作树里 `runner/` 下**别人未提交的改动**也推过去 —— 推之前
> `git status` 看一眼，有别人的半成品就等一等。

**真跑**（必须包在网关锁里；不拿锁并发 = 网关 OOM，N-125）：

```bash
$PY ops/gateway_lock.py --what "<id>:真跑 <task>" -- \
  ssh -o ConnectTimeout=120 ljn@192.168.1.219 \
  "umask 022; export PYTHONDONTWRITEBYTECODE=1; cd /data/genebench_runner && \
   python3 exec/ops/run_f02_a1.py \
     --bundle   /data/genebench_runner/<batch>/runner/tasks/<task> \
     --manifest /data/genebench_runner/<batch>/runner/tasks/<task>.manifest.json \
     --config-id <config_id> --arms strict,open --seq 1 \
     --timeout 1500 \
     --run-root /data/genebench_runner/<batch>/runs \
     --results-dir /data/genebench_runner/<batch>/results"
```

> **这条命令里一个预算参数都不给**（**N-388**，2026-09-10）。注入器按 bundle 的 `stage`
> 自动取档：默认 **100 次 / 6,000,000 tokens**、**S4 150 次 / 9M**、**S7 300 次 / 18M**
> （`runner/registry.py::BUDGET_TIERS`，见 §1⑤）。
>
> 显式给 `--max-calls` / `--max-tokens` 会**逐键压过档位** —— 写一个 `100` 会把 S4 的 150
> 与 S7 的 300 打回去，写一个 `3000000` 比默认档还低。本手册 2026-09-10 之前的版本
> 在这里写着 `--max-calls 100 --max-tokens 3000000`，**照抄那一版会把预算压低**。

> **重跑要把 `--seq` 换掉。** 上面那条命令里写死的是 `--seq 1`；
> 第一次失败之后照抄第二遍会撞 `RunError: run dir 已存在（F9）`，
> 而那不是「你哪里写错了」，只是那个 run 目录已经被上一次占了。
> `--seq` 就是这一次运行的序号，`r01` / `r02` … 也从它来。

**结算**：

```bash
$PY ops/score_runs.py --help        # 参数以 --help 为准，别照抄旧命令
```

### ⑦ 收工：成本 end + LOC

```bash
$PY -m integrations.cost loc --system <id>                       # 只看，不记事件
$PY -m integrations.cost end --system <id> --outcome passed_real_task
```

`--outcome` 三选一：`passed_real_task`（真跑过一道题并通过）/ `blocked` / `abandoned`。
`COST.md` 会在同一把锁里自动重算，**不用手动跑 `report`**。

`--outcome` 说的是**接入这件事**成没成，不是被测系统考得好不好。
「接进去了、真跑了一道题、结算判 `invalid`」仍然记 `passed_real_task` ——
**「我们接不进去」和「它接进去了但答错了」是两件事**，混成一个值就都看不见了。
「它考得怎么样」记在 `COVERAGE.md` 的格值里，两张表分开读。
（要不要给这个字段加第四个值，已登记票据。）

**真 API 用了多少不用手记**，另有一份机器统计（扫 run 目录里的 `llm_log`，
只认 `decision == "allow"` 的条数）：

```bash
$PY ops/api_usage.py
```

它把结果写到 `$GENEBENCH_ROOT/scratch/api_usage/api_usage.json` 与同名 `.md`。
成本表记的是**你的**工时，这一份记的是**模型的**用量，两件事分开记。

### ⑧ 把阶段覆盖写进 `COVERAGE.md`

```bash
$EDITOR integrations/COVERAGE.md      # 手写一行；只写实测过的
```

`COVERAGE.md` 是**共享文件**（并发施工规则 C）：读-改-提交要在同一个
`flock /data/shared/genebench/locks/git.lock` 会话里一气呵成，只追加、不重排，
补丁要幂等（应用前先看有没有人加过同一行）。
另外**阶段格必须恰好八个**（S1..S8），第 11 列才是备注 —— 少写一格
`ops/test_integrations_readme.py::test_coverage_rows_only_use_defined_values` 当场红。

矩阵的定义：**行 = 系统，列 = S1..S8，格 = 你实测得到的结果**。

| 格值 | 含义 |
| --- | --- |
| `passed` | 真跑过这个阶段的题，产物过了评分器 |
| `invalid` | 产物结构合规，但判定为违例（越权 / 静默补全 / 前视……） |
| `malformed` | 产物结构不合规（缺声明字段、枚举写错、类型错……） |
| `no_artifact` | 跑完了但 `/task/artifact.json` 不在位置上（含容器起来就退） |
| `—` | **没跑过** |

**只写实测过的。** 「应该能跑」不是一个格值 —— 一张写满推测的覆盖矩阵比空表更坏，
因为它看起来像证据。

---

## 2. 30 行最小示例

[`example_minimal/`](example_minimal/) 是一个**真能跑**的 P2 系统，主程序
[`example_minimal/run.py`](example_minimal/run.py) 的正文正好 30 行：
读题面 → 用垫片取一段 bars → `emit` 一份 S1 产物。它的作用是把上面八步
压成一份**可以照着改**的东西，而不是一段示意代码。

```python
# integrations/example_minimal/run.py —— 正文逐字（ops/test_integrations_readme.py 核对它与文件一致）
import os, pathlib, re
import genebench_client as gb
from genebench_client import emit

TASK = pathlib.Path(os.environ.get("GENEBENCH_TASK_DIR", "/task"))
FIELDS = ["close", "volume"]
# 固定槽的三种写法（`- as_of: 2026-07-31`、表格行、`` `as_of` = ... ``）都收；收不到就退出。
_SLOT = r"[`*_\s|]*{k}[`*_\s]*[:：=|]+\s*[`\"']?(?P<v>[^\s`\"'|,)]+)"

def slot(text, key):
    m = re.search(_SLOT.format(k=re.escape(key)), text, re.I)
    if not m:
        raise SystemExit(f"INSTRUCTION.md 里没有槽位 {key!r}。**不猜默认值** —— 请按题面写法改 slot()。")
    return m.group("v")

def main():
    text = (TASK / "INSTRUCTION.md").read_text(encoding="utf-8")
    as_of, universe = slot(text, "as_of"), slot(text, "universe")
    start, end = slot(text, "start_date"), slot(text, "end_date")
    gb.set_as_of(as_of)                          # 启动时一次；三处都取不到就抛，不猜
    cli = gb.client()                            # 身份头与网关地址从环境变量取
    codes = cli.members(universe, as_of)[:5]     # PIT 成分，单日
    bars = cli.bars(codes, start, end, fields=FIELDS)   # fields 显式给；闭区间
    fetches = [emit.fetch(r["path"], r["params"], fetched_at=r["ts"],   # ts 来自响应头
                          rows=r["rows"], status=r["status"]) for r in cli.ledger]
    art = emit.emit_s1(fetches=fetches, as_of=as_of,
                       fields_obtained=sorted(c for c in bars.columns if c in FIELDS),
                       declarations={"calendar_id": "SSE", "universe": universe,
                                     "data_version": "unresolved"})
    out = art.write(TASK / "artifact.json")
    print(f"wrote {out}  fetches={len(fetches)}  rows={len(bars)}")
    return 0
```

**逐行为什么**：

* `GENEBENCH_TASK_DIR` 只是为了能在 f01 上不起容器地试跑；容器里它不存在，
  默认值 `/task` 就是对的。
* `slot()` 从题面的固定槽里取值，**取不到就抛**。给 `as_of` 编一个默认值
  会让越界变成合法请求，而产物上完全看不出来。
* `cli.ledger` 里每条是 `{method, path, params, status, ts, rows}` ——
  `ts` 就是网关回显的 `x-genebench-ts`。**被拒的（403）也在 ledger 里，也要记进 `fetches`**：
  如实记录尝试过的全部操作对你有利，删掉不会让你得分（合法性判定在评分器那边，
  它读的是网关日志，不是你的产物）。
* `data_version` 写 `"unresolved"` 是因为**这道最小示例的题面没有给这个口径** ——
  这正是「诚实标记」的样子。题面给了就照填，别反过来。

**LLM 怎么接**（本例不调模型，因为 S1 是取数留痕，没有需要模型的判断）：

```python
import os
from openai import OpenAI                       # 或任何兼容 SDK
llm = OpenAI(base_url=os.environ["OPENAI_BASE_URL"],
             api_key=os.environ["OPENAI_API_KEY"])   # 占位 key，照传
rsp = llm.chat.completions.create(model=os.environ.get("GENEBENCH_MODEL", "deepseek-chat"),
                                  messages=[{"role": "user", "content": prompt}])
```

**唯一要注意的是预算**：默认 100 次调用 / 6,000,000 tokens（`runner/registry.py`
的 `RUN_BUDGET`）一到就 429，那不是故障，是这次运行结束了；**不要再显式给
`--max-tokens`**（显式值逐键压过 stage 档位），见 §1⑤ 与 §1⑥。

**在 f01 上不起容器地试跑**（打生产网关，很轻，**不需要 `gateway_lock`**；
用独立身份，不与任何真跑的切片键冲突）：

```bash
cd "$REPO"
sh integrations/example_minimal/smoke.sh          # 造一个假 /task、跑一遍、过 validator
```

它会把产物写到 `$GENEBENCH_ROOT/scratch/example_minimal/task/artifact.json`
并跑一次协议 validator。**过了 validator 不代表过了评分** ——
validator 是 scorer L1 的子集，网关日志那一族探针它看不见。

---

## 3. 常见失败的含义

每条按「**症状 → 原因 → 看哪里**」写。前四条来自网关，后六条来自跑批与守门。

### 3.1 `403 {"error":"denied","reason":"..."}` —— 越权 / 越界

* **症状**：任何数据端点返回 403，body 里 `reason` 是
  `range_end_after_asof` / `open_range_would_cross_asof` / `target_date_after_asof` /
  `asof_beyond_freeze_line` / `universe_asof_after_asof` / `fundamental_not_yet_announced`
  / `adjustment_mode_not_in_v1` / `dataset_not_exposed_in_v1` 之一。
* **原因**：**越界一律 403 不是 400** —— "你问的东西存在，但在你的 `as_of` 视角下
  不该看见"是**授权**语义。最常见的三个：`end_date > as_of`；**根本没给 `end_date`**
  （开区间被拒，不是默认到 as_of）；`as_of` 越过冻结线。
* **看哪里**：`P2_CONTRACT.md` §2.2（六条越界路径）与 §2.3（reason 全集）。
  自己这边看 `cli.ledger`；判定侧看 `$GENEBENCH_ROOT/logs/gateway_access.jsonl` 里
  `decision == "deny"` 的那些行。
* **它直接算分**：越权率 = 403 次数 / 数据与操作请求总数，**来源网关日志，不采信自报**。

### 3.2 `422 {"error":"invalid_request","reason":"param_malformed"}` —— 参数畸形

* **症状**：422，`reason` 是 `param_malformed` / `asof_missing` / `asof_malformed` /
  `unknown_universe`。
* **原因**：语法错，不是授权错。四类：**缺 `as_of`**（不是"建议带"，缺了就 422）；
  **`as_of` 写法不认**（只认 `YYYY-MM-DD` 与 `YYYYMMDD`，`2026/07/31`、带时区、
  带 `T00:00:00` 一律拒 —— 宽进严出在授权参数上是反模式）；
  **标量参数重复出现**（`as_of` / `start_date` / `end_date` / `date` / `universe` /
  `scope` / `statement` / `mode` / `fields` 每个最多一次，重复即 422，环境不替你择一）；
  **`code` 写法不对**（必须是 `600000.SH` 这种湖内形态）。
* **看哪里**：`P2_CONTRACT.md` §2.1。422 在结算里**单列 `malformed_requests`**，
  不并进越权率 —— 参数拼错与想看未来含义相反。

### 3.3 「预算」—— 是 **429 `budget_exceeded`**，不是 402

* **症状**：模型调用返回 **429**，body 里 `budget_exceeded`。
* **原因**：每 run 100 次调用 / 6,000,000 tokens 的闸在**边车**上（`--max-calls` / `--max-tokens`），
  不在数据网关上。**规划文里写 402 的地方是错的** —— 全树没有任何 HTTP 402 的落点，
  照 402 写重试分支的话，那条分支永远不触发（已登记订正票据）。
* **看哪里**：`P2_CONTRACT.md` §4.5。垫片的 `errors.BudgetExceeded` 留着 402 的映射位，
  但本项目里给出 402 的东西不存在；真正会遇到的是 `RateLimited`（429）。
* **预算耗尽不是故障，是运行结束了**。上游无响应是 502，那才是故障。
* **闸的大小按阶段取档，不是固定的。** 默认取 `runner/registry.py` 的 `RUN_BUDGET`
  （100 次 / 6,000,000 tokens），S4 / S7 另有档（150 / 9M、300 / 18M）；
  **真跑不要再显式给 `--max-tokens`**（§1⑤、§1⑥）。**所以「我算过我只用了 20 万 token」不能证明没撞闸** ——
  要看这次跑的是哪个值，以及 `llm_log` 里 `reason` 是不是 `budget_exceeded`。
* **不给参数时闸也不一定是 100。** 注入器按 bundle 的 `stage` 取档
  （`runner/registry.py::BUDGET_TIERS`：**S4 150**、**S7 300**、其余 100）。
  所以「这次的闸是多少」只有一处现场证据：run dir 的 `compose.yml` 里那行 `--max-calls`。

### 3.4 `NoData` —— 本环境不提供这类数据源

* **症状**：垫片抛 `NoData`，带 `.kind` / `.api` / `.traced`。
* **原因**：新闻 / 财务 / 资金流 / 内部人交易 / 分红拆股明细 / 股东数据 / 宏观指标
  —— 这些**这个基准就没有**。它不是"垫片没做完"，是一个事实的类型化表达。
* **看哪里**：每次 `NoData` 之前垫片会打一次 `GET /nodata/<kind>?as_of=…&api=…`，
  在 `gateway_access.jsonl` 里留一整行（`status: 404`）。
  `.traced == False` 说明网关当时连不上，降级写了容器内 `/task/log/client_nodata.jsonl`。
* **不要 fallback 到原生数据源。*** **留痕会落进 `malformed_requests`**（当前口径，知道就行，不用改你的代码）：
  留痕打的是白名单之外的路径，网关记 404 / `reason: unclassified`，
  而结算把非 403 的那些计进 `malformed_requests`。于是「参数拼错」与
  「本环境没有这类数据源」在表上分不开，**而两者含义相反** ——
  大量使用 `NoData` 的接入会显得「参数写得很烂」。
  卡 2.6 实测过一次：`malformed_requests` strict 60 / open 45，全部是留痕。
  把 `/nodata/{kind}` 做成正式端点（404 + `reason="no_such_data_source"`）的
  提议已登记票据；改了之后垫片与接入方**都不用改代码**。
 未实现的接口一律**可调用且抛 `NoData`**，
  就是为了防止上游用 `hasattr` 探测后静默回落 —— 那条路一走，access_log 干干净净
  而 as-of 强制已经失效。

### 3.5 `no_artifact` —— 产物不在位置上

* **症状**：跑完了，结算说 `no_artifact`。
* **原因**：三种。① 写到了别处（唯一合法路径是 **`/task/artifact.json`**，写死的）；
  ② 写到了 `/task` 下别的文件名，或顺手在 `/task` 里落了中间产物 —— **P8 文件集封闭**
  多一个文件就红；③ 进程压根没跑到写产物那一步（见 §3.7）。
* **看哪里**：`<run_dir>/run.json` 的 `stdout_tail` / `stderr_tail`（各 2000 字符）——
  **run dir 里没有容器日志文件**：真跑收尾会 `down -v`，`log/` 下只剩 `egress.jsonl`
  与 `llm_log.jsonl`（实测，卡 6.4）。`runner/inject.py` 的 P8 核对报文会指名道姓说多了哪个文件。

### 3.6 `malformed` —— 产物结构不合规

最高频的三类，都不会在你本地报错，只会在评分侧报：

| 症状 | 原因 | 修法 |
| --- | --- | --- |
| `declaration_missing` / `underdetermined_field_missing` | 少写了一个声明键。**缺失 ≠ 标记** | `/task/{stage}.json` 的 `properties.declarations.required` 里列全了（**含本题欠定的那个**；顶层没有 `declarations` 这一键），照着写；用 `emit` 就不会漏 |
| 枚举写错 | 值不在表里，或**被包成了对象**（`{"value": "post"}` 这种曾静默通过）。`S1.fetches[].status ∈ {ok, empty, denied, rate_limited}` —— **HTTP 码不是这个枚举** | 用 `emit.fetch()` 拼，它按 HTTP 码或异常反推档位 |
| 日期写法 / `number` 写成字符串 | `as_of` 必须 `YYYY-MM-DD`（紧凑写法只在网关参数上认）；schema 说 `number` 就不能是 `"0.031"` | `emit` 统一归一：紧凑日期→ISO、`Timestamp`→ISO、`sh600000`→`600000.SH`、`numpy` 标量→原生、`"0.031"`→`0.031` |

还有两个**判定不同但长得一样**的坑：
`"unresolved"` 是**显式字符串**不是 `null`（`null` 已被 S5 的"无观点"占用）；
声明字段标了 `unresolved` 却把依赖它的 payload 算出来了 → `computed_despite_unresolved`。

**写完自检**（strict 臂容器里）：

```bash
python3 /task/protocol/validate_artifact.py /task/artifact.json
```

### 3.7 两臂都在 3 秒内退出

* **症状**：strict 与 open 两个容器几乎同时结束，`no_artifact`，日志几乎是空的。
* **原因**：容器起来就死。按出现频率排：
  1. `launch.json` 的 `command` 里 `$` 没写成 `$$`（N-101）—— 变量被提前吃掉，
     命令看起来对、跑起来是空的；
  2. `HOME` 不可写（见 §3.9）；
  3. 入口文件在镜像里根本不在那个路径（`COPY` 的目标目录写错）；
  4. 依赖没在构建期装完 —— 运行期 `pip install` 会立刻撞断网。
* **看哪里**：`<run_dir>/run.json` 的 `stdout_tail` / `stderr_tail`（**不是**某个日志文件，
  见 §3.5）；**先在 f02 上单独 `docker run` 一次
  你的 `command`**，那比跑一遍两臂快 20 分钟。

### 3.8 `EAI_AGAIN` / DNS 解析失败

* **症状**：`EAI_AGAIN`、`Temporary failure in name resolution`、
  `getaddrinfo ENOTFOUND`。
* **原因**：**运行期是断网的**。容器能到的只有两个地方：`$GENEBENCH_GATEWAY`（数据网关）
  与 `$OPENAI_BASE_URL`（边车）。任何别的域名都解析不了。
* **看哪里**：先 grep 你的代码里写死的主机名。三种常见来源：
  系统内部残留的行情源、遥测/上报 SDK、以及**运行期 `pip install`**。
  依赖全部在构建期装完。

### 3.9 `HOME` 不可写 / `Permission denied` 写文件

* **症状**：`PermissionError: [Errno 13]` 指向 `/home/...` 或 `/.cache`，
  或工具自称"无法创建配置目录"。
* **原因**：容器以非 root 运行、`cap_drop: ALL`、`no-new-privileges`，`HOME` 不可写。
  （这条不是洁癖：root 容器往宿主 bind mount 里写过一次，harness 连删都删不掉。）
* **修法**：把 `HOME` 与 `<TOOL>_HOME` 指到**容器可写层**：

  ```json
  "command": ["sh", "-c", "export HOME=/tmp/h XDG_CACHE_HOME=/tmp/h/.cache; mkdir -p $$HOME && cd /task && python3 /opt/<id>/run.py"]
  ```

  **不要指到 `/task` 下** —— 那会往 `work/` 里多放文件，破 P8 封闭。
  注意上面那个 `$$HOME`：两个 `$`。

### 3.10 守门拦 0775 / 0644

* **症状**：`ops/test_env.py` / `ops/test_env_guard.py` 变红，报文里是**你的**目录或日志文件。
* **原因**：红线 5 要求 `$GENEBENCH_ROOT` 全树 `go-rwx`；f02 上 runner 写出来的
  `__pycache__` 默认是 0775。
* **修法**（两条，都要）：

  ```bash
  # f01：远端命令开头 umask 077；scp 之后立刻收紧
  ssh finance01-ts 'umask 077; ...'
  ssh finance01-ts 'chmod -R go-rwx /data/shared/genebench/scratch/<你的卡号>'
  # f02：跑 runner 之前
  umask 022; export PYTHONDONTWRITEBYTECODE=1
  ```

  仓库里被守门报红时的处方是一条命令：

  ```bash
  $PY -c "from ops import report_io as R; R.secure_tree('/data/shared/genebench/repo')"
  ```

* **这条会连累所有人**：留下 0644/0775 会让**每一个跑全量的代理**看到两条红。

* **它还会把生产网关整个停掉。** `genebench-gateway.service` 的 `ExecStartPre`
  跑的就是 `ops/guard_modes.py`：全树只要有一个 `0644` / `0664` / `0775`，
  预启动守门 `exit 1`，systemd 每 50 秒重试一次、一直起不来 ——
  **对别人的表现是「网关连不上」，不是「有人权限没收紧」**。
  卡 2.7 的演练撞上过一次：网关在 `restart counter is at 25` 上转了 35 分钟，
  三个肇事文件里有一个是 `ops/push_exec_to_f02.sh` 自己留下的
  `$GENEBENCH_ROOT/scratch/exec_push/ops/__init__.py`（0664），
  另外两条是并发的 git 操作把 `.git/index` 重建成了 0664。
  **诊断一条命令**（不是猜）：

  ```bash
  cd "$REPO" && $PY ops/guard_modes.py        # 它会逐条列出是哪个文件
  ```

### 3.11 注入期就被拦（run dir 都没建出来）

* **症状**：两臂各 0.1 秒 `ERROR`，`RunError: 注入失败：[P0] 注入中止（1 条）：
  P0 红线 5 目录对组/其它开放 0o775 …`；**run dir 根本没建**，没有容器日志。
* **原因**：f02 的 `exec/` 树里有 `0775` 的 `__pycache__` —— 谁在 f02 上
  没带 `PYTHONDONTWRITEBYTECODE=1` 跑过一次 `exec/` 下的 python 就会造一个。
* **它与 §3.7「两臂都在 3 秒内退出」长得像，但排查方向完全不同**：那一族要看容器日志，
  这一族根本没有容器日志可看。分辨法：run dir 在不在。
* **修法**：`ssh finance01-ts 'ssh ljn@192.168.1.219 "chmod -R go-rwx <那个目录>"'`，
  以后在 f02 上跑任何 python 都带 `umask 022; export PYTHONDONTWRITEBYTECODE=1`。

### 3.12 上游在 **import 期**按相对 CWD 写文件

* **症状**：`FileNotFoundError: [Errno 2] No such file or directory: '/task/log/test.txt'`，
  或者跑完之后 `run.json` 的 `unexpected` 里多出一堆你没打算写的东西。
* **原因**：容器的 `working_dir` 是 `/task`，而不少上游在**模块顶层**就开日志/缓存，
  路径是**相对 CWD** 的（`logging.FileHandler('log/test.txt')`、`to_excel('res/x.xlsx')`）。
  §1④ 说的「`HOME` 指到 `/tmp`」拦不住这一类 —— 它们根本不看 `HOME`。
* **修法**：在 `import` 上游**之前** `os.chdir()` 到一个 `/tmp` 下的目录，并把
  它需要的子目录先 `mkdir -p`。**顺序错了不是慢一点**：那个 `FileHandler`
  是 import 期就打开的，chdir 晚一行都来不及。
  同一条也适用于 `pin.json` 的 `runnable_check` —— 它在构建期跑，
  那时 `/task` 还不存在（卡 2.7 演练的构建第一次就是这么红的）。

### 真跑之后必须做的一件事：读一遍被挡下的出向请求

**「被测系统的取数是否全部经过数据面」不能靠你穷举替换点来保证。**
卡 2.6 有一个接入的三条原生取数路径里，接入者自己只找到第一条
（框架自己的 vendor 注册表）；第二条是**真跑报 `NoMarketDataError`** 告诉我们的，
第三条是**容器的出向白名单回 403** 告诉我们的 —— 而第三条到发稿时都还没替换掉，
真跑里挡住它的是容器，不是接入层。

所以每次真跑之后加一步（一分钟）：

```bash
# 容器 stderr 里被 CONNECT 代理拒掉的那些行（出向白名单是空集，任何 CONNECT 都拒并留痕）
grep -i "Tunnel connection failed\|403 Forbidden\|proxy" <run_dir>/log/*.jsonl <run_dir>/*.log
```

**每一条被挡下的请求，都当成一条你没替换掉的取数路径登记进 README 的「已知偏离」。**
它们在这次真跑里是无害的（被容器挡住了），但它们说明：
换一个网络配置，这个系统就会绕过数据面 —— 而那时 access_log 会干干净净。

（越权率只数网关的 403，**看不见「它试图直连第三方」这件事**；
把 CONNECT 拒绝数也进表的提议已登记票据。）

---

## 4. 取数垫片 `genebench_client/`

> 原「取数垫片」一节（卡 2.2）与「`emit`」的说明整合到这里，不留两份。
> 详细的接口表、单位换算、逐条已知偏离在
> [`genebench_client/README.md`](genebench_client/README.md)，本文不复制。

被测系统把 `import yfinance` / `import tushare` / `import akshare` 换成
`genebench_client.compat.<name>`，取数就自动**经网关、带身份、受 as_of 约束、
落 access_log**；新闻 / 财务 / 资金流一律 `NoData` **并在网关日志上留痕**。

它是**范式层给出的一件工具，不是某一个系统的适配器** —— 谁都可以装。
上半场是取数（`gateway.Client` + 三个 compat + qlib provider 定位器），
下半场是交产物（`emit`：三态声明、依赖图、写法归一，格式这一层全包，
业务值一个都不替你想）。

**它不走 exec 树**（`ops/push_exec_to_f02.sh` 同步的是 runner 的东西，不进任务容器），
只走镜像：

```dockerfile
FROM gb-base:bookworm-r1
COPY genebench_client/ /opt/genebench_client/
RUN pip install --no-cache-dir --no-index --no-build-isolation /opt/genebench_client
```

**不要 `pip install genebench-client` 去公网拿** —— 它不在任何 index 上，
而且运行期装包被禁（那会把包仓库放进出向白名单）。依赖只有 `pandas` / `numpy`，
基座里已有；HTTP 走标准库 `urllib`。

**一件必须知道的事：`GENEBENCH_AS_OF` 不由 runner 注入。** compose 模板里没有这一行
（实测）。所以容器里正常的做法是启动时 `gb.set_as_of(spec["as_of"])`，
`as_of` 从 `/task/INSTRUCTION.md` 的固定槽里读。三处都取不到时垫片抛 `AsOfRequired`，
**不猜** —— 猜出来的那个值会让越界变成合法请求，而产物上完全看不出来。

```bash
cd "$REPO" && ulimit -n 8192
$PY -m pytest ops/test_genebench_client.py ops/test_emit.py -q -p no:cacheprovider
```

---

## 5. 接入成本怎么记

**每个接入都要记。** 这不是实验记录，是 GeneBench 自带的一项遥测：范式层声称
「接口定义在范式层，接入责任在被测方」，而这句话只有在**接入成本可测**的时候
才是可证伪的。工具在 [`cost/`](cost/)，账本是 [`COST.jsonl`](COST.jsonl)（一行一个事件），
报表 [`COST.md`](COST.md) **由工具生成，不要手改**。

```bash
PY=/data/shared/genebench/env/bin/python; cd /data/shared/genebench/repo

# 动手之前先起表 —— begin 记下的 HEAD 就是后面算 LOC 的基线
$PY -m integrations.cost begin  --system <id> --who agent --note "起手"

$PY -m integrations.cost pause  --system <id> --note "等网关锁"   # 离开
$PY -m integrations.cost resume --system <id>                      # 回来
$PY -m integrations.cost rework --system <id> --why "镜像里 HOME 不可写，命令重写"
$PY -m integrations.cost loc    --system <id>                      # 只看，不记事件

$PY -m integrations.cost end    --system <id> --outcome passed_real_task
$PY -m integrations.cost report                                    # 重出 COST.md
```

`--outcome` 三选一：`passed_real_task`（真跑过一道题并通过）/ `blocked` / `abandoned`。
`--who` 二选一：`agent` / `human`。

### 5.1 量的是哪三样

| 量 | 怎么来的 | 为什么不靠回忆 |
|---|---|---|
| **净工时**（min） | `begin`..`end` **减去** `pause`..`resume` 段 | 等一个 90 分钟的 flock 不是接入成本 |
| **LOC** | `git diff --numstat <begin 时 HEAD>..HEAD -- integrations/<id>` 的增删行，外加该目录**当前**非空行数 | 「改了多少」和「最后剩下多少」是两个数；未提交的工作只在后者里看得见 |
| **返工** | `rework` 事件的条数（`end --rework` 再加一次） | 返工是事后最想不起来的一项 —— 「没花多久」通常等于「忘了那两次白干」 |

### 5.2 三个会踩的地方

1. **忘了敲 `begin`。** 用 `--at 2026-09-06T15:30:00+00:00` 按真实时刻补记
   （时刻**必须带时区**，不带的当场报错 —— 裸时刻会静默偏 8 小时，
   而偏 8 小时的工时看起来只是「那天干得久」）。基线 sha 也丢了的话，
   `loc --system <id> --base <sha>` 显式给。
2. **`COST.md` 不用手动同步。** 每次记事件都会在同一把锁里重算它；
   `report` 的日常用途是把手改过的改回去。`ops/test_integration_cost.py`
   有一条断言盯着两者是否一致 —— 红了就跑一次 `report`，那是一条命令不是一次调查。
3. **`COST.jsonl` 是共享文件**（并发施工规则 C）：只追加，追加走 `fcntl.flock`
   锁文件本身。别用编辑器改它 —— 坏一行下游每个数都偏小，而偏小和
   「这个接入很省事」在表上长得一模一样（所以读到坏行是**当场报错**，不是跳过）。

`integrations/cost/` 是工具不是接入：它没有 `launch.json` / `config.yaml`，
两处发现入口（`discover_launch_specs()` / `config_files()`）都不会把它当成被测系统。

---

## 6. `integrations/` 里都有什么

| 路径 | 是什么 | 谁维护 |
| --- | --- | --- |
| `P2_CONTRACT.md` | **规则**：网关 API、`as_of` 语义、产物 schema、禁止事项、版本轴 | 范式层 |
| `README.md`（本文） | **操作手册**：接入八步、最小示例、常见失败 | 范式层 |
| `genebench_client/` | 取数垫片 + 产物助手 `emit`（pip 可装的独立包） | 范式层 |
| `cost/` | 接入成本遥测 CLI | 范式层 |
| `COST.jsonl` / `COST.md` | 成本账本 / 生成的报表 | 工具写，勿手改 |
| `COVERAGE.md` | 谁接了什么、跑到哪个阶段（实测矩阵） | 每个接入者写自己那一行 |
| `example_minimal/` | 30 行、真能跑的 P2 示例 | 范式层 |
| `<id>/` | **一个接入 = 一个目录**，五件套见 §1② | 接入者 |

### 并发施工的两条

* **你只加自己那一个目录。** 别的路径一律不碰；需要别人改的写进票据
  `ops/tickets_inbox/<你的卡号>.md`（表格 `| 编号 | 事项 | 状态 | 说明 |`，编号先写 `N-?`），
  **不要直接改 `ops/tickets.md`**。
* **你的判据别把 `glue` 这个名字占了。** 几乎每个接入都会有一个
  `integrations/<id>/glue/` —— 于是你那份判据文件（`ops/` 下的那个）里那句
  `sys.path.insert(0, <你的目录>)` + `from glue import ...` 会把
  `sys.modules["glue"]` 占住，**别人的测试再 import 就拿到你的模块**。
  pytest 是先把所有测试文件 import 一遍再开跑的，所以**肇事者自己不会红，红的是别人**
  （卡 2.7 第一次全量就这么让 `ops/test_integration_rdagent_q.py` 挂了 8 条）。
  改法是按路径加载、挂一个带前缀的模块名：

  ```python
  spec = importlib.util.spec_from_file_location(f"_<id>_glue_{stem}", HERE / "glue" / f"{stem}.py")
  ```

* **共享文件只许追加**（`COST.jsonl` / `COVERAGE.md` / `runner/registry.py` /
  `runner/c42/harness_commands.py` / 各 README……），而且「读-改-提交」要在同一个
  `flock /data/shared/genebench/locks/git.lock` 会话里一气呵成。
  应用前先看有没有人加过同样的内容 —— 补丁要幂等。
