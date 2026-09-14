# `rdagent_q` —— RD-Agent(Q) 作为被测方（P2）

**被测系统**：[RD-Agent](https://github.com/microsoft/RD-Agent) 0.8.0 的**因子实现循环**
（`FactorCoSTEER`）。论文是 [R&D-Agent-Quant（arXiv:2505.15155，NeurIPS 2025）](https://arxiv.org/abs/2505.15155)。
钉在 [`pin.json`](pin.json)。

接的是 **S3（因子实现）**：题面给一条源方言的因子表达式，RD-Agent 自己驱动
「模型写 `factor.py` → 本地子进程执行 → 评审 → 再写」的多轮循环，产出值序列。
**回测那一路没接**（要 qlib + conda/Docker），所以 S4–S8 一律 `—`：
声明能做而做不了，会把「框架做不了这个阶段」变成「它做了但做错了」，那是两个结论。

**内核一行没改。** `glue/` 里全部是子类、上游自己的构造参数、环境变量与数据落盘，
逐条列在下面第 3 节，`ops/test_integration_rdagent_q.py` 拿 `glue.bootstrap.REPLACEMENTS`
去 import 上游做属性存在性检查 —— 上游改名会炸在测试里，不是炸在真跑里。
仓库里既有的 `runner/c42/adapters/rdagent_q/` **没有被碰过**（只读参考）。

---

## 1. 数据层怎么接的

RD-Agent 的因子路径不认「数据源」，它认**一个目录里的 HDF5 面板**：
`FACTOR_COSTEER_SETTINGS.data_folder_debug` 下的 `daily_pv.h5`，索引是
`MultiIndex[datetime, instrument]`，列名是 qlib 风格的 `$open` / `$volume`。

所以接法是「**我们经垫片取数、按它要的形状落一份面板**」，而不是改它读文件的代码：

```
/task/INSTRUCTION.md  ──parse──▶  spec(as_of, window, universe, factor, 七项口径)
        │
        ├─ gb.set_as_of(as_of); cli.members(universe, as_of)      → PIT 成分
        ├─ cli.bars(codes, start, end, fields=required_fields)    → 长表（闭区间、显式 fields）
        └─ glue/panel.py                                          → /tmp/rdagent_q/source_data/daily_pv.h5
                                                                     （$open / $volume，qlib 代码写法）
```

* `fields` **显式传题面的 `required_fields`**，不传就是畸形（S3 的 declared_reads 探针
  从 access_log 反推实际读取集）。
* 代码写法在两边之间搬运：网关是 `600000.SH`，qlib 是 `SH600000`，
  产出文件再搬回题面那一种（`glue/panel.py::to_qlib_code` / `to_gateway_code`）。
* **不经 compat 层**（`compat.yfinance` 之类）：compat 层一律按上游库的完整列集向网关
  请求 `fields`，那会让声明读取集失控 —— 而 S3 正是要看这个。

### 哪些数据源退成 NoData

RD-Agent 的 qlib 场景原本描述的是一份 pv + 财务的全量 provider。本环境只发放行情面：

| 上游会想要的 | 本环境 | 我们做了什么 |
| --- | --- | --- |
| `$open/$high/$low/$close/$volume/$amount` | **有**（`/bars`） | 按题面的 `required_fields` 取，落进面板 |
| `$factor`（复权因子） | 有（`/adj`） | **本题没要，就没取** —— 面板里没有的列，模型也不会看见 |
| 财务 / 新闻 / 资金流 / 内部人交易 / 分红拆股明细 / 宏观 | **没有** | 面板里不造这些列。垫片对这类 API 一律 `NoData` 并留痕（`/nodata/<kind>`）。**不造 `$roe`**：造出来的结果是一个跑得通、值全是编的因子 |

模型看到的数据说明由上游自己的 `get_data_folder_intro()` 从**我们落的那份面板**生成，
所以「模型以为有什么」与「网关真给了什么」是同一件事，不需要额外对账。

## 2. LLM 怎么指

容器里只有占位 key，真 key 由边车注入。RD-Agent 0.8.0 的后端是
`rdagent.oai.backend.LiteLLMAPIBackend`，`completion()` 不显式传 `api_base` ——
它读环境变量。于是：

| 设的 | 值 | 为什么 |
| --- | --- | --- |
| `BACKEND` | `rdagent.oai.backend.LiteLLMAPIBackend` | 显式钉住，不靠默认值 |
| `CHAT_MODEL` | `openai/deepseek-chat` | `openai/` 前缀让 litellm 走 **OpenAI 兼容路由**，从而认 `OPENAI_API_BASE` |
| `OPENAI_API_BASE` | = `OPENAI_BASE_URL`（边车） | **只做名字之间的搬运**，一个主机名都不写死 |
| `CHAT_STREAM` | `False` | usage 直接在响应体里，边车记账少一层归一 |
| `MAX_RETRY` | `2` | 上游默认 10，一次抖动能吃掉十分之一的调用预算 |
| `LITELLM_LOCAL_MODEL_COST_MAP` | `True` | litellm 一 import 就去 `raw.githubusercontent.com` 拉价目表；不关掉那次 CONNECT 会被边车拒并留痕，而那条记录是我们不需要的 |

`enable_response_schema` 关掉；`openai/deepseek-chat` 不在 litellm 的价目表里，
它会打一句 `Cost calculation failed … Skip cost statistics` 的 WARNING —— **无害**，
用量以边车的 `llm_log` 为准，不以框架自报为准。

## 3. 接线点（每一处顶替的是上游的什么）

清单是**数据不是注释**：`glue/bootstrap.py::REPLACEMENTS`，测试逐条 import 上游核对。

| 顶替的 | 用什么 | 为什么 |
| --- | --- | --- |
| `RD_AGENT_SETTINGS.workspace_path` / `.pickle_cache_folder_path_str` | env `WORKSPACE_PATH` / `PICKLE_CACHE_FOLDER_PATH_STR` | 默认落在 CWD（容器里就是 `/task`）下的 `git_ignore_folder/`，会破 P8 文件集封闭 |
| `FACTOR_COSTEER_SETTINGS.data_folder(_debug)` | env `FACTOR_CoSTEER_data_folder(_debug)` | 面板落这里；`execute(data_type="Debug")` 与场景描述都读它 |
| `FACTOR_COSTEER_SETTINGS.max_loop` | env `FACTOR_CoSTEER_max_loop`（默认 **5**） | 上游默认 10 轮；实测每轮 3 次调用，5 轮 ≈ 15 次，离 `RUN_BUDGET` 的 100 次闸还远 |
| `FACTOR_COSTEER_SETTINGS.python_bin` | `python3` | 因子代码经 `subprocess` 跑 `{python_bin} factor.py` |
| `FACTOR_COSTEER_SETTINGS.file_based_execution_timeout` | `300` | 上游默认 3600，比整题的 `--timeout` 还长 |
| `LLM_SETTINGS.*`（见 §2） | env | 模型只经边车 |
| `CONDA_DEFAULT_ENV` | `"none"` | `CondaConf.conda_env_name` 是 `str` 不是 `str \| None`；取不到当场 pydantic `ValidationError`，**场景根本建不起来**。给个字符串即可 —— `conda run` 在本镜像里必然失败，上游失败时把 `bin_path` 置空并继续（实测） |
| `QlibFactorScenario.get_runtime_environment()` | **子类覆写**（`glue/scenario.py`） | 上游那一份起 `LocalEnv` 跑 `python runtime_info.py` 采运行环境；本镜像里 `PATH` 被上游置空后连 `python` 都找不到，采回来的是一句 `timeout: failed to run command 'python'`，而那句**会原样进 prompt** 当作「你的运行环境」。替上去的是同一件事实的、能核对的写法 |
| `FactorCoSTEER(scen, knowledge_self_gen=False)` | **上游自己的构造形参** | 它跑完一轮会调 `rag.generate_knowledge()` → `create_embedding()` → 打 **embedding 端点**。本环境只发一个 chat 模型，边车后面没有 embedding —— 实测：实现与评估都成功了，却在收尾建知识图谱时炸掉，整个 `develop()` 抛 `RuntimeError`，前面的成果全丢。**`with_knowledge` 保持 True**：关掉它 `implement_one_task` 会拿 `None` 去取 `queried_knowledge.task_to_former_failed_traces[...]`（上游那一行没有 `None` 分支） |

### 一处「打捞」

`develop()` 抛出时，模型已经写好的 `factor.py` 会随异常一起没了。
`glue/develop.py::_salvage_code()` 从工作区目录把它捡回来再跑一遍取值 ——
**代码仍然是模型写的**，我们只是没让它丢掉。规则是写死的一条：**取最近写入的那一份**，
不做任何挑选（挑「跑得通的那一份」等于给自己加了一层题目没给的搜索预算）。
捡不到就把**原来那个异常**抛出去，不是抛一句「打捞失败」。

## 4. 题面怎么读

两臂的题面是同一件事的两种说法（`ops/specs/fairness_protocol.md` 允许的差异恰好是
「题面的表达形式」与「协议工件的有无」）：

```
strict:  as_of=2026-07-31                   open:  本次任务的 as_of 是 2026-07-31
strict:  - lookback=10（…，接口值 10）        open:  - 回看窗口 10 个交易日（字段 lookback，接口值 10）
```

`glue/instruction.py` 把每一条写成「锚点词 + 中间随便什么 + 值」，**同一份代码认两种写法，
没有按臂分支**（读 `GENEBENCH_ARM` 去改行为是明令禁止的；测试走 AST 盯着这一条）。
槽位取不到就抛 `InstructionError`，**不猜默认值**。

> 踩过的坑，写在这里免得下一个接入的人再踩：题面里有一行
> `可用端点：/bars /adj /calendar /limits /universe /tradability`。
> 锚点没防住路径时，`universe` 会命中那里、被解析成 **`tradability`** ——
> 这种错**没有任何症状**：网关照样返回一个成分表，因子照样算得出来，只是标的池整个换了。

## 5. 镜像

```
gb-rdagent_q-u:r1   digest sha256:d2a2cd7848debb0e585f417656c878852dbc013db4022a3c053627c6387d42e4
```

构建（在 **f02**，f01 没有容器运行时）：

```bash
# 在 f01：把接入目录与垫片一起送过去
scp -r integrations/rdagent_q integrations/genebench_client \
       ljn@192.168.1.219:/data/genebench_runner/build/rdagent_q_ctx/
# 在 f02（只许从 f01 进）：
cd /data/genebench_runner/build/rdagent_q_ctx
docker build -t gb-rdagent_q-u:r1 -f rdagent_q/Dockerfile .
docker images --digests gb-rdagent_q-u:r1
```

`Dockerfile` 里装 `rdagent==0.8.0` 那一行是**逐字照抄** f02 上 `build/rd/Dockerfile` 的，
为的是命中同一层构建缓存（装出来的字节是同一份，构建从二十分钟变成几秒）。
改那一行会重新解析依赖、装出一份与既有探针镜像不同的树。

`pin.json` 的 `runnable_check` 在这个镜像里实跑的输出是 `0.8.0 FactorCoSTEER FactorFBWorkspace`。

## 6. 怎么复现

**走查**（不花模型调用，验的是链路：题面→网关→面板→执行→值→产物→协议 validator）：

```bash
cd /data/shared/genebench/repo && sh integrations/rdagent_q/smoke.sh
```

它在 f02 的**真镜像**里跑，把「模型写 `factor.py`」那一步换成给定代码
（`smoke_factor.py`，走查专用的假因子，**故意不是任何一道被计分的真题**）。

**真跑**（双臂，网关锁内）：

```bash
sh /data/shared/genebench/scratch/2.6/realrun.sh     # 完整命令见其中
/data/shared/genebench/env/bin/python ops/score_runs.py \
    --batch i_rdagent_q --remote /data/genebench_runner/i_rdagent_q/runs/runs
```

## 7. 证据

| 什么 | 在哪 |
| --- | --- |
| 结算报表 | `ops/reports/i_rdagent_q/` |
| 真跑 run 目录（f02） | `/data/genebench_runner/i_rdagent_q/runs/runs/s3-cor-01.{strict,open}.cfg-rdagent_q-deepseek.r02` |
| 走查日志与产物 | `/data/shared/genebench/scratch/2.6/smoke/`（`run.log`、`artifact.json`、`values.parquet`） |
| 上游探针输出（API 形状实测） | `/data/shared/genebench/scratch/2.6/probe*.py` |
| 镜像里跑的那三条判据 | `/data/shared/genebench/scratch/2.6/inimage_check.py`（f01 的 venv 没有 rdagent，全量里那三条是 skip） |

**2026-09-07 的真跑结果**（`--max-calls 100`，两臂各 18 次调用）：

| 臂 | 结果 | 说明 |
| --- | --- | --- |
| strict `r02` | **violation**，闸 `warmup_boundary` | 循环跑通了：模型写的代码算出了覆盖率 0.989 的值序列。判违例的是**模型自己**没守暖机口径（`nonnull_before_warmup=2611`，题面要求回看窗口未满输出空值） |
| open `r02` | valid，但 `coverage=0.0` | 同一份代码、同一个模型，这一臂的循环没写出能跑的因子；产物如实写覆盖率 0，**不编数** |
| strict `r01` / open `r01` | 见「已知限制」 | 第一次真跑：open 臂零产物，肇因是解析器只认 strict 的键值写法（**我们的链路**，已修，见 §4） |

> **N-105 可以关了。** 那条记的是「真 LLM 驱动循环未实现，只有降级路径」。
> `strict r02` 是一次**模型驱动**的完整循环：DeepSeek 写 `factor.py`、上游的
> `FactorFBWorkspace` 执行、上游的评审器给 critic、产出真值序列。降级路径现在只用于走查。

## 8. 已知限制

1. **`approximated_operators` 恒为 `[]`。** 那是「我这一层没做算子近似」的如实陈述 ——
   **模型写的代码里有没有近似，我们无从核验**。真判在评分侧（R 侧重算与 gold 比）。
2. **回测路径没接**，所以只有 S3。S4–S8 在 `COVERAGE.md` 里是 `—`。
3. **知识库 / RAG 关着**（§3）：上游那条路要 embedding 模型，本环境不发。
   于是 RD-Agent 的「跨任务经验累积」这一层能力在这里**没有被测到** ——
   这是环境的边界，不是它做不到。
4. **`nonfinite.replaced_count` 只反映我们这一层**（恒 0，因为我们不替换）。
   模型的代码若自己 `fillna` 了，这个数看不出来 —— 同 1，真判在评分侧。
5. **每轮 3 次模型调用是实测值，不是承诺。** 上游的重试与评审轮数会变；
   `--max-calls 100` 才是护栏。
