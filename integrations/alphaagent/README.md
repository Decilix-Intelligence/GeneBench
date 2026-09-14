# AlphaAgent 接入（P2）

**被测系统**：[RndmVariableQ/AlphaAgent](https://github.com/RndmVariableQ/AlphaAgent)
@ `b42cb397` —— 一个面向 A 股的因子研究框架：从数据源建日频 panel、用自带 DSL
表达因子、在 FactorZoo 里评估，并可由 LLM agent 迭代挖掘。
**论文**：[arXiv:2502.16789](https://arxiv.org/abs/2502.16789)（Tang et al., 2025）。

> **先读这一句再读别的**：本接入钉的 commit **不是论文那一版代码**。这个仓库的整个
> git 历史只有 8 个提交、最早一个是 2026-07-01 的「初始化项目：初始提交」，而论文是
> 2025-02 —— 历史被重置过，当前 HEAD 是一次重写（提交信息 "Release new AlphaAgent
> factor research framework"），README 里也不再提论文。论文里的数字**不能**拿来解释
> 本接入的结果。钉的依据逐条在 [`pin.json`](pin.json) 的 `note` 里。

| | |
| --- | --- |
| 范式 | P2（专用系统自带研究流程） |
| 镜像 | `gb-alphaagent-u:r1`，digest `sha256:43b8607b5f69a94a14b9a0e2bee2c3e1332562b470d90cc520a64bffd47dbbee` |
| 配置 | `cfg-alphaagent-deepseek`（deepseek-chat，经边车） |
| 实测阶段 | S3（`s3-cor-01`），双臂 `r01`，两臂都 **`invalid` / gate `warmup_boundary`** |
| 证据 | [`ops/reports/i_alphaagent/`](../../ops/reports/i_alphaagent/)（含 `agent_trajectory.json`） |

---

## 1. 这个接入是什么形状的

AlphaAgent 的因子那一路有三段：**数据**（建 panel）→ **DSL**（表达 + 求值）→
**挖掘**（LLM agent 迭代）。本接入把三段分别接住：

| 系统的这一段 | 接入怎么做 | 接线文件 |
| --- | --- | --- |
| 数据：`alphaagent.data.*` 的「从数据源拉缓存 → 离线 build_panel」两段式管线 | 经垫片从网关取数，直接造出下游要的那个 DataFrame；另把 `tushare` 顶替成经网关的 compat 层 | [`glue/panel.py`](glue/panel.py)、[`glue/bootstrap.py`](glue/bootstrap.py) |
| DSL：`alphaagent.dsl.*` 的解析器、算子库、求值口 | **原样用**，一行没改 —— 因子值就是它算出来的 | — |
| 挖掘：`alphaagent.factor.mining.loop.run_trajectory` | **原样用**它的多轮工具调用循环；工具与 system prompt 做**同形替换**（下面 §3 说清为什么必须换） | [`glue/agent.py`](glue/agent.py) |

**系统内核一行没改。** 三处接线点各自写在模块 docstring 里：

1. `glue/bootstrap.py`：`sys.modules["tushare"] ← genebench_client.compat.tushare`。
2. `glue/agent.py`：`alphaagent.factor.mining.tools.FactorEvalTools` →
   `ImplementTools`（同形：`schemas` / `dispatch` / `result_to_content` 三个方法）。
3. `glue/agent.py`：`alphaagent.factor.mining.prompts.build_system_prompt` →
   `build_prompt`（保留它现算的算子清单，换掉建立在 label 之上的那半）。

---

## 2. 怎么接的数据层

### 2.1 面板

`alphaagent.dsl.eval.eval_factor(expr, panel)` 认的是一个
`MultiIndex[datetime, instrument]` 的 DataFrame，列是普通列名，DSL 里写 `$列名`。
`glue/panel.py` 就造这个：

```python
codes = cli.members(spec.universe, spec.as_of)                  # PIT 成分，单日
bars  = cli.bars(codes, spec.window_start, spec.window_end, fields=fields)
panel = build_panel(bars, fields)        # → MultiIndex[datetime, instrument]，列 = fields
```

`instrument` 直接用网关的代码写法（`600000.SH`），与系统里 tushare 口径的 `ts_code`
是同一种写法，**不需要来回搬运**。

**`fields` 显式传，不经 compat 取面板。** compat 层的 `fields` 只裁剪返回值、
不改变网关上的读取集（垫片 README §4），而 S3 的「声明读取集 vs 实际读取集」探针
是从 access_log 反推的 —— 经 compat 层取数就控制不了声明读取集。

### 2.2 `tushare` 为什么必须顶替（而不是装上）

镜像里**没装** tushare：它是行情源客户端，装了就等于给被测系统留了一条绕过数据面的路
（红线 5）。但上游 `alphaagent/data/__init__.py` 顶层就
`from alphaagent.data.tushare_client import get_pro`，而那个模块顶层 `import tushare as ts`；
`alphaagent/factor/mining/session.py` 又 `from alphaagent.data.panel import load_panel` ——
于是**只要 import 到 agent 循环，就一定会 import 到 tushare**。

所以 `glue/bootstrap.py` 在任何 `import alphaagent` 之前跑
`genebench_client.compat.install("tushare")`。效果是：系统照样 `import tushare as ts`，
拿到的是经网关的兼容层。这也是 `pin.json` 的 `runnable_check` 开头要带一句
`compat.install('tushare')` 的原因 —— 不带它，镜像里 `import alphaagent.data` 就
`ModuleNotFoundError`（实测过一次）。

### 2.3 哪些数据源退成 NoData

AlphaAgent 的挖掘 prompt 原本描述的面板远比本环境发的宽：复权 OHLC
（`$adj_open` … `$adj_close`）、`$vwap` / `$adj_vwap`、`$float_cap` / `$tot_cap`、
`$ret`、`$is_trade` / `$not_st`、申万一级行业码 `$industry_sw_l1`，以及一整套
`funda_*` 基本面列（`scripts/fetch_fundamentals.py` 那条 PIT 财务管线）。

**这些列本接入一列都不造。** 造出来的 `$float_cap` 会让模型写出一个跑得通、
值全是编的因子。做法是：面板里**只有题面 `required_fields` 点名的那几列**，并且
`glue/agent.py` 把**实际列集**逐字写进 system prompt（「没有列出来的列就是没有」）。
两臂的实测里模型都没去碰不存在的列。

同理，系统的这几条路本接入**没有走**，因为它们要么要 label、要么要持久因子库：

* FactorZoo 入库与 AST 相似度去重（`alphaagent/factor/zoo/similarity.py`）；
* IC / ICIR / MLS-FMB 评估（`alphaagent/factor/metrics.py`）；
* `submit_factor` 的查重与增量 memmap 因子库；
* `scripts/factor_mining_agentscope.py` 那条 AgentScope 路（本接入走原生 OpenAI 工具调用路）。

---

## 3. LLM 怎么指，以及为什么换掉了它自带的两件

模型经**边车**：`glue/agent.py` 只从 `OPENAI_BASE_URL` / `OPENAI_API_KEY` 取
（`run.py::_llm_client`），**绝不写死主机名** —— 写死就绕过了边车，那条路上没有
usage、没有预算闸。容器里只有占位 key，真 key 由边车注入。

换掉的两件，各自的理由：

**① 工具：`FactorEvalTools` → `ImplementTools`。**
`FactorEvalTools` 的两个工具（`eval_on_train_set` / `eval_on_val_set`）要一个
**前瞻 label 列**才能算 IC，而 label 由未来的收盘价造。本题的
`required_fields=[open, volume]`，为了造 label 去多取一列 `close` 就是**越权读取**
（S3 的声明读取集探针从 access_log 反推）。所以工具换成
「在题面窗口的面板上求这一个因子并如实清点」，返回覆盖率、Inf/NaN 计数、
暖机期内的非空个数、是否常数、前几行样例；失败时把系统自己的结构化报错
（`MultiLineFactorEvalError` 的阶段 / 生成码行号 / 你写的哪一行）**原样**回给模型 ——
那正是它自己迭代的方式。

**② system prompt：`build_system_prompt` → `build_prompt`。**
那份 prompt 的正文是挖掘目标（`abs(ic) ≥ 0.005`、`icir`、`monthly_corr_robustness`、
入库判据……），**全部建立在有 label 的前提上**；照搬会让模型去追一组这道题里根本
不存在的指标，白烧调用预算。`build_prompt` 保留它**真正能用的那一半** ——
`alphaagent.dsl.catalog.operator_catalog_markdown()` 现算的算子清单（不是抄一份表，
抄的那份必然漂）——另一半换成**题面自己的原文**（`spec.raw` 逐字贴入，不转述：
转述一次就多一个我们编的口径）。

**选取规则事先声明，不是事后挑。** system prompt 里写明：交付方式是
`submit_expression`；若一直不交，按「**最后一次**成功求值的表达式」取。
「最后一次」是确定性的先后顺序，不是按好坏排名 —— best-of-N 是被禁的。
两臂实测都走的是 `submit_expression`，没有用到这条兜底。

---

## 4. 真跑结果（`s3-cor-01`，双臂 `r01`）

题面：实现 `(-1 * correlation(open, volume, 10))`，csi300，窗口
2026-01-05 ~ 2026-07-31，`as_of=2026-07-31`，`lookback=10`，
`warmup_policy=null_until_full`，`nonfinite_policy=propagate`。

| | strict | open |
| --- | --- | --- |
| 结果 | `invalid`，gate `warmup_boundary` | `invalid`，gate `warmup_boundary` |
| L3 容差（tau） | **通过** | **通过** |
| 越权率 | 0.0 | 0.0 |
| 模型调用（`decision==allow`） | 3 | 3 |
| Steps | 3 | 3 |
| 容器耗时 | 43.5 s | 24.4 s |
| agent 写的 DSL | `MULTIPLY(-1, TS_CORR($open, $volume, 10))` | `-1 * TS_CORR($open, $volume, 10)` |
| `values.parquet` sha256 | `0c89db85…` | `0c89db85…`（**与 strict 逐字节相同**） |
| coverage | 0.99233 | 0.99233 |
| `nonnull_before_warmup` | 2389 | 2389 |
| `/task` 下多余文件 | 无 | 无 |

两臂**独立**收敛到同一个因子、产出**逐字节相同**的 `values.parquet` ——
这是一条关于「两臂差异只在题面表达形式」的正面证据，不是我们对齐出来的。

### 4.1 唯一那道闸：`warmup_boundary` 的根因不在模型，在算子库

题面要求 `warmup_policy=null_until_full`：回看窗口未满的日期输出空值。
`nonnull_before_warmup=2389` 不是 0，所以判违例。

**根因是 AlphaAgent 的滚动内核在序列头部是「扩张窗」而不是「定长窗」。**
`alphaagent/dsl/core/accel.py::_roll_corr_numba` 里：

```python
w = window
if w > i + 1:          # ← 窗口比已有数据长时，缩到已有长度
    w = i + 1
...
if c < 2:              # ← 有效对数 ≥ 2 就出值
    out[i] = np.nan
```

于是 `TS_CORR(..., 10)` 从**第 2 个观测**起就有值，而不是第 10 个。
这不是模型写错了表达式 —— `TS_CORR($open, $volume, 10)` 与题面
`correlation(open, volume, 10)` 是逐算子对应的（参数顺序
`(df1, df2, window)` 与题面 `param_order=[series_a, series_b, window]` 一致，
docstring 自称滚动 Pearson，与 `operator_semantics={correlation: pearson_rolling_window}`
一致）。**接入层没有替它修**：那会变成「我们替它改了多少」的分数，而不是它本身的能力。

**模型自己看见了这件事。** strict 臂的推理里逐字写着
「TS_CORR 用了更小的 min_periods」「rolling(10) 默认 min_periods=window 即 10，
那么前 9 个交易日应为 NaN，nonnull_before_warmup 应该就是 0」——
它诊断对了根因，但在这一轮里没有改写成绕开的写法就交付了。
全文在 `ops/reports/i_alphaagent/agent_trajectory.json`。

**没有重试。** 施工纪律：只有失败原因是我们的链路而不是 agent 自身时才重试。
这一次链路是通的（面板取全、DSL 编译通过、产物合规、越权率 0、L3 容差过），
失败在系统与模型这一侧 —— 重跑一次只是买一个更好看的格子。

---

## 5. 怎么复现

### 5.1 取上游源码（本地有出网的机器上做一次）

```bash
curl -sSL -o alphaagent-b42cb397.tar.gz \
  "https://codeload.github.com/RndmVariableQ/AlphaAgent/tar.gz/b42cb397025510da44355db9dcf278304321f589"
shasum -a 256 alphaagent-b42cb397.tar.gz
# → cddabb7ea2c3df31bf3cfb5f8c8be95427f2913b80965b3d180164a14e274581
```

**tarball 不进仓库**（400 KB 的二进制），它只出现在 f02 的构建上下文里。
摘要在 `pin.json` 与 `Dockerfile` 两处，构建期 `sha256sum -c -` 真核 ——
两处漂了就等于没钉，而漂的那一天构建照样成功，所以有一条测试盯着它们相同。

### 5.2 构建（在 f02；f01 没有容器运行时）

```bash
# 在 f01：把接入目录与垫片送到构建目录，再把 tarball 送过去
scp -r integrations/alphaagent integrations/genebench_client \
       ljn@192.168.1.219:/data/genebench_runner/build/alphaagent/
scp <上面下好的>/alphaagent-b42cb397.tar.gz \
       ljn@192.168.1.219:/data/genebench_runner/build/alphaagent/
# 在 f02：
cd /data/genebench_runner/build/alphaagent
chmod -R a+rX .          # ← $GENEBENCH_ROOT 全树 0600，不放开构建出来的镜像里也是 0600
docker build -t gb-alphaagent-u:r1 -f alphaagent/Dockerfile .
docker images --digests gb-alphaagent-u:r1
```

### 5.3 无 LLM 的通路自检（很轻，几十次 GET，**不需要 `gateway_lock`**）

```bash
docker run --rm -e GENEBENCH_GATEWAY=http://192.168.1.48:18080 \
    gb-alphaagent-u:r1 python3 /opt/gb_alphaagent/smoke.py
# 期望最后一行 SMOKE-OK
```

它用一条**手写死**的 DSL 把 LLM 之外的每一环点亮一次（网关 → 面板 → 系统的 DSL
求值 → values.parquet → `emit` → artifact），出了事能立刻分清是「链路坏了」还是
「模型没写对」。它**不**证明模型那一段。

### 5.4 出集 → 推送 → 真跑 → 结算

```bash
PY=/data/shared/genebench/env/bin/python; cd /data/shared/genebench/repo
STG=/data/shared/genebench/staging/i_alphaagent_s3-cor-01; rm -rf "$STG"
$PY ops/export_bundle.py s3-cor-01 --staging "$STG" \
    --digest sha256:43b8607b5f69a94a14b9a0e2bee2c3e1332562b470d90cc520a64bffd47dbbee \
    --image gb-alphaagent-u
ops/push_bundle_to_f02.sh "$STG/tasks/s3-cor-01" \
    /data/genebench_runner/i_alphaagent/runner/tasks "$STG/s3-cor-01.manifest.json"
ops/push_exec_to_f02.sh --with-launch-data          # 第一次接入必带

B=/data/genebench_runner/i_alphaagent/runner/tasks
$PY ops/gateway_lock.py --what "2.6-alphaagent:真跑 s3-cor-01" -- \
  ssh -o ConnectTimeout=120 ljn@192.168.1.219 \
  "umask 022; export PYTHONDONTWRITEBYTECODE=1; cd /data/genebench_runner && \
   python3 exec/ops/run_f02_a1.py --bundle $B/s3-cor-01 --manifest $B/s3-cor-01.manifest.json \
     --config-id cfg-alphaagent-deepseek --arms strict,open --seq 1 --timeout 1500 \
     --max-calls 100 --max-tokens 3000000 \
     --run-root /data/genebench_runner/i_alphaagent/runs \
     --results-dir /data/genebench_runner/i_alphaagent/results"

$PY ops/score_runs.py --batch i_alphaagent --remote /data/genebench_runner/i_alphaagent/runs/runs
```

### 5.5 判据

```bash
cd /data/shared/genebench/repo && ulimit -n 8192
$PY -m pytest ops/test_integration_alphaagent.py -q -p no:cacheprovider
```

f01 上是 `16 passed, 4 skipped`。那 4 条 skip 是「替换点在被替换模块里确实存在」
那一族 —— 它们要 import 上游 `alphaagent`，而 f01 的解释器上没有它（只装在接入镜像里）。
**要真跑那一族就得进容器**，而容器只在 f02、仓库只在 f01，所以要先把这两条路径送过去
（**只送这两条**：其余的仓库内容没有必要、也不该出现在执行面）：

```bash
# 在 f01：
R=/data/genebench_runner/build/alphaagent/repo_ro
ssh ljn@192.168.1.219 "rm -rf $R; mkdir -p $R/ops $R/integrations"
cd /data/shared/genebench/repo
scp -q ops/test_integration_alphaagent.py ljn@192.168.1.219:$R/ops/
scp -q -r integrations/alphaagent          ljn@192.168.1.219:$R/integrations/
# 在 f02（chmod 是必须的：$GENEBENCH_ROOT 全树 0600，容器非 root 读不到）：
ssh ljn@192.168.1.219 "chmod -R a+rX $R; docker run --rm -v $R:/repo:ro -w /repo \
  gb-alphaagent-u:r1 sh -c 'pip install -q pytest pyyaml 2>&1 | tail -1; \
    python3 -m pytest ops/test_integration_alphaagent.py -q -p no:cacheprovider'"
# 期望 20 passed
```

> 那一族在容器里也得先 `compat.install("tushare")` 才 import 得动上游
> （测试里的 `_upstream()` 就是这么做的）—— 与真跑走**同一条** import 路径，
> 否则测的就不是真跑那条路。

---

## 6. 已知限制（读结果时必须连着读的几条）

1. **HEAD 不是论文那一版。** 见开头那段与 `pin.json`。论文的三个机制（AST 相似度
   原创性约束、假设-因子语义一致性、AST 复杂度控制）在本 commit 里能找到落点，
   但**本次真跑一条都没有走到** —— S3-cor 是实现题，不是挖掘题。
2. **只跑了 S3 的一道实现题，挖掘那一路没跑过。** 系统真正的主张是「自主挖掘
   抗衰减因子」，那需要 label（前瞻收益），而本题的 `required_fields` 里没有
   `close`。`s3-eco-01`（自由发挥、`required_fields=[close, volume]`）能造 label，
   是最自然的下一步 —— 但它的 `operator_semantics` 声明的方言是 `qlib_expression`，
   与 AlphaAgent 自己的 DSL 不是一种写法，这个冲突要先裁定。已登记 v11。
3. **因子值在系统内部是 float32。** AlphaAgent 的加速内核统一输出 `np.float32`
   （`dsl/core/accel.py` 里 `np.full(..., dtype=np.float32)`）。产出文件契约要求
   `value` 是 float64，接线层**只做类型转换、不做任何数值修改**。本次 L3 的 tau
   容差过了（秩相关对 float32 舍入不敏感），但若将来有按绝对值比对的判据，
   这一条会是差异的来源。
4. **暖机口径与题面不合**（§4.1），根因在算子库的扩张窗，接入层没有替它修。
5. **`approximated_operators` 写的是 `[]`，含义是「我们这一层没有替换任何算子」。**
   模型选的 DSL 算子与原文算子是否逐一对应，接入层**无从核验** —— 本次两臂的写法
   人工看是对应的（`TS_CORR` ↔ `correlation`），但这不是机器判据。
6. **`payload.expression` 放的是题面原文，不是系统执行的 DSL。** 题面明令
   「expression 照抄原文，算子不得自行替换」。系统实际执行的那条 DSL 在
   `ops/reports/i_alphaagent/agent_trajectory.json` 与容器 stdout 里可查。
7. **agent 的轨迹 JSONL 落在容器的 `/tmp`，随容器一起消失。** 它不能落 `/task`
   （那是 run dir 的 `work/`，多一个文件就是 P8 文件集封闭核对里的 `unexpected`）。
   本次的证据是从 run 目录的 `log/llm_log.jsonl` 反向摘出来的，够用；
   要更细的轨迹得让 runner 支持一个「系统自留日志」的采集位，已登记 v11。
8. **numba / C++ 加速后端都没装**，算子走纯 Python 循环。数值结果不变
   （`njit` 退化成恒等装饰器），只是慢。装 numba 要把基座的 numpy 2.5.2 降到 `<2`，
   那是动统一基座的数值栈，而 S3 的产出正是 parquet 数值。

---

## 7. 许可证：`none_declared`

`pin.json` 的 `license` 写的是 **`none_declared`**，不是某个具体许可证。依据：

* 仓库里**没有 LICENSE 文件**（`b42cb397` 的文件树里查过，141 个文件里没有）；
* GitHub API 的 `license` 字段是 `null`；
* 上游 README 末尾只有一句 "Code in this repository is open source … Research use only"，
  行情与基本面数据部分另外要求遵守其数据源的条款。

一句「open source」不是一份许可证 —— 它没有说明允许的行为。**所以这里不猜一个
MIT**：猜出来的许可证比空着更坏，它会让下游以为已经核过了。本接入的用法是
在内网做研究性评测，镜像 `gb-alphaagent-u:r1` **不对外分发**。
若将来要把这个镜像或其中的上游代码发出去，**必须先向作者确认授权** ——
这一条不在本卡的处置范围内，已在 `ops/tickets_inbox/2.6-alphaagent.md` 之外
单独提请注意。
