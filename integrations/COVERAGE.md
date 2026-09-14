# 接入覆盖矩阵

**行 = 被测系统，列 = 阶段 S1..S8，格 = 实测结果。**
只写**实测过的** —— 「应该能跑」不是一个格值。一张写满推测的覆盖矩阵比空表更坏，
因为它看起来像证据。

| 格值 | 含义 |
| --- | --- |
| `passed` | 真跑过这个阶段的题，产物过了评分器 |
| `invalid` | 产物结构合规，但判定为违例（越权 / 静默补全 / 前视……） |
| `malformed` | 产物结构不合规（缺声明字段、枚举写错、类型错……） |
| `no_artifact` | 跑完了但 `/task/artifact.json` 不在位置上（含容器起来就退） |
| `—` | **没跑过** |

一个系统在同一阶段跑过多次时，写**最后一次**的结果，并在「备注」里注明前面那次是什么
（返工次数记在 [`COST.md`](COST.md)，不在这张表里重复）。

| 系统 | 范式 | S1 | S2 | S3 | S4 | S5 | S6 | S7 | S8 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `rdagent_q` | P2 | — | — | `invalid` | — | — | — | — | — | RD-Agent 0.8.0 的 FactorCoSTEER 循环（真 LLM 驱动，DeepSeek，18 次调用/臂）。S3 = `s3-cor-01`，双臂 `r02`：strict 跑出覆盖率 0.989 的值序列但被闸 `warmup_boundary`（模型自己没守暖机口径）；open 臂同一份代码没写出能跑的因子，产物如实写覆盖率 0。格值取两臂里最坏的那个。回测那一路没接（要 qlib + conda/Docker），所以 S4–S8 是 —。证据：`ops/reports/i_rdagent_q/` |
| `tradingagents` | P2 | — | — | — | — | `passed` | — | — | — | TauricResearch/TradingAgents v0.4.0（commit 2448d0a1）。S5 = `s5-eco-01`（自由发挥题），双臂 `r03` 都是 `valid`：十六个探针族全 `clean`、越权率 0（strict 0/91、open 0/88）、`unbounded_requests` 0、`/task` 下零多余文件。**但只交出 3 格**（3 个标的 × 1 个交易日；题面要的是 csi300 × 约 140 个交易日的面板）—— 它一次只对一个标的一天给一条五档评级，凑不满面板是事实，接入层不替它补格子。「合规」与「做完了」是两件事，这个 `passed` 要连着这句备注读。前两次 `r01`/`r02` 是 `no_artifact`/`malformed`，两次都是我们链路的问题（镜像里接线层 0600；open 臂题面解析），已修。证据：`ops/reports/i_tradingagents/`、`integrations/tradingagents/README.md` §6 |
| `finmem` | P2 | — | — | — | — | `passed` | — | — | — | FinMem `be814aa4`（分层记忆的逐日单标的交易 agent，真 LLM 驱动，DeepSeek）。S5 = `s5-eco-01`，双臂 `r01` 都 **valid**、gate 空、越权率 0.0（strict 36 次调用 / open 35 次）。交 10 格 = 1 个标的 × 10 个交易日（train 12 天建记忆 → test 10 天出决策；两段首尾相接不重叠，见 README §4.3），题面要的是 csi300 × 139 天的面板 —— 差额是事实，不补格子。`pass@1=0.0` 是自由题的口径符合度，别读成「信号有多好」。新闻 / 10-K / 10-Q 三类 NoData 各留痕一次；`/embeddings` 实测 **404**，向量后端退成离线哈希（README §4.1）。S1–S4 / S6–S8 没跑过。证据：`ops/reports/i_finmem/` |
| `finrobot` | P2 | `passed` | — | — | — | — | — | — | — | AI4Finance-Foundation/FinRobot 0.1.5（PyPI sdist，与 repo commit `6e91cef9` 的包目录逐字节相同）。跑的是它自带的 AutoGen 单智能体 `SingleAssistant("Market_Analyst")` —— 它的工具本来就是四个取数接口，接线层把实现整层换成经网关的，换不成的退成 NoData 并留痕。S1 = `s1-cor-01`，双臂 `r01` 都 **valid**、gate 空、越权率 0.0（strict 8 次模型调用 / open 13 次）。两臂都把整张面板取全了：`/bars`（`fields=close,volume`）6,900 行 = 300 只 × 23 个交易日、`/adj` 6,900 行，`fields_obtained=[adj_factor, close, volume]`。新闻 / 三大报表 / SEC / reddit 一律 NoData（各自留痕）。S2–S8 没跑过。证据：`ops/reports/i_finrobot/`、`integrations/finrobot/README.md` §6 |
| `alphaagent` | P2 | — | — | `invalid` | — | — | — | — | — | RndmVariableQ/AlphaAgent `b42cb397`（论文 arXiv:2502.16789 Tang et al. 2025，**但本 commit 是论文之后的重写版**，仓库 git 历史起于 2026-07 —— 见 `pin.json`）。S3 = `s3-cor-01`，双臂 `r01` 都 `invalid`，gate 都是 `warmup_boundary`；**L3 的 tau 容差两臂都过、越权率 0.0、`/task` 下零多余文件**，各 3 次模型调用。两臂独立收敛到同一条 DSL（`MULTIPLY(-1, TS_CORR($open,$volume,10))` / `-1 * TS_CORR($open,$volume,10)`），产出的 `values.parquet` **逐字节相同**。那道闸的根因不在模型也不在接线：AlphaAgent 自己的滚动内核在序列头部是扩张窗（`dsl/core/accel.py::_roll_corr_numba`：`if w > i+1: w = i+1`、有效对数 ≥2 就出值），于是 `TS_CORR(...,10)` 从第 2 个观测起就有值，与题面 `warmup_policy=null_until_full` 冲突 —— 接入层没有替它修。模型自己在推理里诊断对了这一点却没改写就交付了。挖掘那一路（FactorZoo / IC / AST 去重）**没跑过**：要前瞻 label，而本题 `required_fields=[open, volume]` 里没有 `close`。S1/S2/S4–S8 没跑过。证据：`ops/reports/i_alphaagent/`（含 `agent_trajectory.json`）、`integrations/alphaagent/README.md` §4 |
| `stockagent` | P2 | — | — | — | — | `passed` | — | — | — | MingyuJ666/Stockagent `e2a9c052`（arXiv:2407.18957，ACM TIST）——一个**原生完全不取数**的封闭模拟市场：N 个 LLM 交易员逐日逐时段报价撮合，股票是虚构的、财报写死在 prompt 里。接入把它虚构的参考价与财报换成网关来的 PIT 数据（`/bars` fields 显式给、`/tradability` 逐日、财报 `/nodata/fundamentals` 留痕），把逐日决策翻成分数信号。S5 = `s5-eco-01`（自由题），双臂 `r02` 都 **valid**、`gate=[]`、越权率 **0.0**、`unexpected=[]`（strict 43 次调用 / open 44 次）。**只交 8 格**（2 只 × 4 个交易日；上游的撮合与 `check_action` 只认 A/B 两只股票，天数由 100 次调用的闸决定），题面要的是 csi300 × 约 140 日 —— 差额是事实，不补格子。`pass@1=0.0` 是自由题的口径符合度，别读成「信号有多好」。**出向自检干净**：`egress.jsonl` 里被拒的 CONNECT 是 0 —— 它本来就不出网，这是三类被测方里「结构保证」那一类的实测样子。S1–S4 / S6–S8 没跑过。证据：`ops/reports/i_rehearsal/`、`ops/reports/integrations_rehearsal.md`（本接入是卡 2.7 内部演练的产物） |
| `quantagent` | P2 | — | `passed` | — | — | — | — | — | — | Aurora-73/QuantAgent `4027f572`（MIT，A 股研究系统：自己的数据层 + 因子/回测/组合层）。S2 = `s2-ops-01`，双臂 `r03` 都 **valid**、十六族探针全 `clean`、`gate=[]`、越权 **0 / 602** 次网关请求、`Align`·`Adj`·`Cal` **全 1.0**；面板 6,900 行 = 300 只 × 23 个交易日，两臂逐字节相同。**`l3_pass` 是 `null`，原因不在这个接入**：`l3_note` 写着「gold 面板缺件：S2 的 oracle 应把 panel.csv 写进 gold/」（票据）。**模型调用 0 次** —— 上游 ADR-001 把 LLM 移出了系统（MCP Server 形态，推理由外部编排方提供），`config.yaml` 的 `model`/`base_url`/`api_key_env` 登记而不使用；**别读成「接入失败」**。上游三条原生取数路径（baostock 首选 / pytdx 首选 / akshare 兜底）：前两条靠「镜像里不装」结构性关闭，第三条经垫片 —— 但上游调的 `ak.stock_zh_a_daily` 垫片没有，接线层补上（不补的表现是「每只取到 0 条」，不是报错）。`unexpected_files` 里有 `work/missing_rows.csv`：题面「流程要求 3」要求写它，而 `harvest.PRODUCED_BY_STAGE["S2"]` 只允许 `panel.csv`（票据）。前两次 `r01`/`r02` 是 `no_artifact`，两次都红在**范式层自己的 `emit`** 上（题面要求把键列写进 `field_map`，而 `emit._norm` 把叫 `date` 的键当日期归一；票据）。S1 / S3–S8 没跑过。证据：`ops/reports/i_rehearsal_v1/`、`integrations/quantagent/README.md` |
