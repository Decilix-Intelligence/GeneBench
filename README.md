# GeneBench

**GeneBench 把一次完整的量化研究流程切成八个阶段，每个阶段给被测 agent 一道有标准答案的题，
让它在一个「只能从题面读需求、只能经网关取数、除模型 API 外没有任何出口」的容器里做完，
再按逐阶段的口径给出可复现的分数。**

| 你是谁 | 从哪读起 |
| --- | --- |
| 想知道这是什么、能不能用 | **本文** |
| 要在自己的机器上把它跑起来 | [`docs/OPERATOR_MANUAL.md`](docs/OPERATOR_MANUAL.md) |
| 有一个通用 CLI agent 想接上去（P1 / P3） | [`harnesses/README.md`](harnesses/README.md) |
| 有一个专用量化系统想作为被测方（P2） | [`integrations/README.md`](integrations/README.md) + [`integrations/P2_CONTRACT.md`](integrations/P2_CONTRACT.md) |
| 要接手施工 / 想知道每条决定为什么这么定 | [`ops/HANDOFF.md`](ops/HANDOFF.md) |
| 要判断两次结果能不能放进同一张表 | [`VERSIONS.md`](VERSIONS.md) |

> **先看一眼 [§5 发布状态](#5-发布状态如实)**：今天还有几条未闭合的事挡着「打包发出去」，
> 权威条数以 `RELEASE_MANIFEST.json` 为准（§5 逐条抄了出来）。
> 它们**不挡在自己的机器上跑**，但会挡住「拿一个现成的包直接开箱」。

<!-- G2-2026-09-12 答案在包里 -->
> ## ⚠️ 先知道这一件事：**答案就在这个包里**
>
> 这个仓库**带全部答案面** —— 参考实现（`reference/`，含每道题的 `solve.py`）、评分器
> （`scorer/`）、题面模板与参数（`genetask/templates`、`genetask/params`）、ε/τ 的标定代码，
> 以及作为 Release 附件发布的 **gold 子集**。这是有意的：**不带答案面，你跑完就算不出分**，
> 这个基准对外只有一半。
>
> **代价也是真的，请照着用**：
>
> * **把这些文件喂给被测模型（或让它联网抓到本仓库）＝ 这次测量作废。**
>   评测时答案面**永不挂进 agent 容器**（红线 2 的容器边界口径，见 [§4 设计约束](#4-设计约束) ①）——
>   `runner/f02/answer_plane_guard.py --mode container` 在容器起来之前判这件事，命中即拒绝启动。
> * **跨期比较要当心。** 题面与参考解在公网上，随时间推移可能进入某些模型的训练语料。
>   同期各臂之间的比较不受影响（大家看到的东西完全相同）；
>   「今年的 80 分 vs 去年的 80 分」则**不再等价**。
>   v1.1 会用**留出集**（held-out split，不公开）来支撑跨期结论。
> * **`reference/memory_probe_answers/` 不在这个包里** —— 记忆探针的钥匙一旦公开就立刻失效。
>
> 完整的判定与理由见 [`ops/reports/known_limits_v1.md`](ops/reports/known_limits_v1.md)
> 「G2（2026-09-12）」那一条。

---

## 0. 是什么

### 0.1 测什么、不测什么

GeneBench 测的是**在受控信息条件下，把一件量化研究的事做对**的能力。
每道题都有一份由参考实现算出来的 gold 和一条 ε 容差带；判的是产物与 gold 对不对得上、
声明得诚不诚实、有没有越权取数，**不是**收益率高低。

题面之外的干预**只有两样**：题面的表达形式，以及 `/task/protocol/` 这份自检工件的有无。
同一道题的两个臂（`strict` / `open`）之间，唯一允许 sha256 不同的文件就是 `INSTRUCTION.md`，
其余文件逐字节相同、由注入器做文件集封闭核对。因为差异面被压到这么小，
两臂之间的分差才可以被归因到干预本身 —— 口径在
[`ops/specs/fairness_protocol.md`](ops/specs/fairness_protocol.md)。

**v1 明确不做的事**：

* 不测实盘收益，不排收益榜；S7 的回测指标是**判「算得对不对」**，不是「赚不赚钱」。
* 不做 best-of-N、不做提示词调优竞赛；`pass^k` 是**无偏估计**，不是「挑最好的一次」。
* 不给被测方联网：任务容器接在 `internal: true` 的网上，唯一出口是出向边车，
  边车按白名单只放行模型 API 域名，其余出站一律拒。
* 不替任何被测系统写内核适配（见 [§1 三范式](#1-三范式)）。
* 不承诺「这一版的分数与下一版可比」—— 可比性由四条版本轴显式判定，见 [§0.3](#03-两条通道与四条版本轴)。
* 今天**不判**的指标逐条点名在
  [`ops/specs/metrics_as_implemented_v1.md`](ops/specs/metrics_as_implemented_v1.md)（含「为什么不判」）。

### 0.2 八个阶段

一次研究从取数走到下单，八段各出一份结构化产物（`/task/artifact.json`，逐阶段 JSON Schema）。
v1 出集 **34 道题**（草拟 40，扣住 6 道）：

| 阶段 | 做什么 | v1 出集 |
| --- | --- | --- |
| **S1** 取数 | 按窗口取日线，如实记录每一次取数（含空结果与被拒）的时点与状态 | 4 |
| **S2** 对齐 | 整理成标准面板：字段命名对齐、复权处理、缺行照实保留 | 4 |
| **S3** 因子 | 实现题面给的因子，报告非有限值、暖机期、退化情况 | 4 |
| **S4** 评估 | 算 IC 族：均值 / 标准差 / ICIR / 覆盖率 / bootstrap 区间 | 4 |
| **S5** 信号 | 因子转交易信号；**没有观点留 `null`，明确不持有记 `flat`** | 4 |
| **S6** 组合 | 由信号与约束给目标持仓，逐票写满台账六字段 | 5 |
| **S7** 回测 | 收益 / 风险 / 换手（单双边分报）/ 成本 / 记账残差 / 归因 | 5 |
| **S8** 交易 | 模拟盘下单，逐条记事件、状态迁移与成交 | 4 |

每个阶段的题按四类变体出：`cor`（正例）、`eco`（自由度更大的经济题）、`ops`（审计/台账）、
`rob`（欠定与鲁棒）。扣住的 6 道是各阶段的 `rob-02` 探针题（`s6-rob-02` 在 5.2 重冻后进集）。
出集清单与题面指纹在 [`ops/manifests/v1.0-smoke.json`](ops/manifests/v1.0-smoke.json)。

### 0.3 两条通道与四条版本轴

**两条数据通道**并列存在，互不覆盖：

* `private` —— 内网数据湖派生的冻结快照；
* `public` —— 从 baostock 公开源从零建第二遍的快照，**任何人都能自己重建**
  （对账结论见 [`ops/reports/public/reconciliation.md`](ops/reports/public/reconciliation.md)）。

**同一道题在两条通道上不是同一道题**：覆盖面、停牌表示、复权口径、涨跌停推导都不同，
逐条见 [`ops/data_cards/README.md`](ops/data_cards/README.md)。

**一次结果只有在四条轴全部相同时才与另一次可比**：任务集 `set_version`（agent 看到的东西变了吗）、
参考面 `reference_version`（我们算 gold 的方式变了吗）、协议 `protocol_version`（这个 run 拿到的是哪一版协议工件）、
数据通道 `channel`。库在出表时按这四条判混轴，**混了默认拒绝出表**。
四条轴各自什么时候变、为什么要拆开，在 [`VERSIONS.md`](VERSIONS.md)。

当前值：任务集 **1.0.16**（公开通道那条轴是 **p1.0.0**，见 [`VERSIONS.md`](VERSIONS.md) §1.1a）/ 参考面 **r1.0.23** / 冻结线 **2026-07-31**。
现查（不要手抄）：

```sh
GB=/data/shared/genebench; PY=$GB/env/bin/python; cd $GB/repo
$PY -c "import json;m=json.load(open('ops/manifests/v1.0-smoke.json'));print(m['set_version'], m['counts'])"
$PY ops/results_db.py versions      # 库里出现过的全部轴组合（混轴在这里看得见）
```

---

## 1. 三范式

GeneBench 不假设被测方长什么样，只规定边界：**题面从哪读、数从哪取、产物写到哪**。
边界之内怎么组织，是三种形态。这条分界是纪律不是偏好 ——
**接口定义在范式层，接入责任在被测方**；替某个系统写内核适配，做出来的分数是
「我们替它改了多少」的函数，不是它本身的能力。

**P1 —— 通用 CLI harness。**
被测方是「给它一个目录和一句话，它自己写代码」的工具（Codex CLI、Claude Code、OpenHands、
gemini-cli、opencode、grok-cli……）。适配由范式层写一次，所有模型共用；
接一个新 harness = 加一个目录 `harnesses/<id>/{Dockerfile,launch.json,config.yaml,README.md}`，
两个共享文件一行都不用改。全部手册在 [`harnesses/README.md`](harnesses/README.md)。

**P2 —— 专用系统。**
被测方自带研究流程与内部数据抽象（因子挖掘框架、多智能体投研、你自己的 pipeline）。
适配责任在**被测方**：读 `/task/INSTRUCTION.md`、经 `$GENEBENCH_GATEWAY` 取数、
把产物写成 `/task/artifact.json`。规则（13 个端点、`as_of` 语义、错误码、产物 schema、
禁止事项）在 [`integrations/P2_CONTRACT.md`](integrations/P2_CONTRACT.md)，
操作步骤在 [`integrations/README.md`](integrations/README.md)，
一个 30 行、真能跑的例子在 [`integrations/example_minimal/`](integrations/example_minimal)。
已接入的系统与它们各跑到哪个阶段：[`integrations/COVERAGE.md`](integrations/COVERAGE.md)。

**P3 —— P1 加上被动存在的 `/task/protocol/`。**
同一个通用 harness，容器里多一个目录：一个离线自检器 `validate_artifact.py` 和三份规则 JSON。
**它是被动的** —— 没有任何东西要求被测方去读它、去调它；无视它照样合规，
也可以写完产物后跑一遍自检、按 findings 修回去。它只发给协议臂（`strict`），
裸臂（`open`）没有这个目录，**那是干预本身，不是遗漏**。
所以被测系统**不许读 `GENEBENCH_ARM` 去改自己的行为**（改超参、改重试、改模型都不行）。
加法与 P1 相同，只是 `launch.json` 里写 `paradigm: "P3"`。

---


<!-- Y1-2026-09-11 -->
## 1.5 最低配置与包体（开跑之前先对一眼）

| | 最低 | 备注 |
| --- | --- | --- |
| 内存 · 数据面 | **16 GB** | 网关常驻 ≈ 2.3 GB，上限 12 GiB；**要自己重建数据面则 30 GB**（gold 重算峰值 22 GiB） |
| 内存 · 执行面 | **16 GB** | 一次真跑起两个容器 |
| 内存 · 单机形态 | **30 GB** | 上面两条相加的上界 |
| 磁盘 | 只走 (a) + §2.4 最短路径 **≈ 15 GB**；想连着跑几批留 **50 GB**；自己重建数据面留 **200 GB** | 15 GB 的算式在本节末尾，逐项都是实测值 |
| docker | **≥ 24 + compose v2**，且**引擎可用内存 ≥ 16 GB** | Linux 实测 29.1.3 / 2.40.3；macOS 实测 Docker Desktop 引擎 **29.2.0 aarch64** / compose v5.0.2。**Docker Desktop 默认只给 8 GB —— 不够**：Settings → Resources → Memory limit 调到 **16 GB**，Apply & restart。**纯数据面那台不需要 docker** |
| Python | **3.12+** | macOS 自带的 `python3` 是 **3.9.6，不够**。3.12 是外部路径唯一有实测背书的版本（2026-09-11 Linux 演练、2026-09-13 macOS 外部验收都在 3.12 上）；代码本身在 3.10 上也跑 —— 发布方内部环境就是 3.10，**内部自检与内部路径继续用它**。六个包：`fastapi uvicorn pandas pyarrow duckdb pyyaml`（仓库里没有 requirements 文件，见手册 §1.2） |

**包体 1.52 GiB**（代码 4.0 MiB + 公开通道数据面 ≈ 957 MiB + gold 子集 152 MiB + 答案面 427 MiB）。
**gold 只发子集**：全量 14.90 GiB，而 40 行出集 + 130 个实例真正读到的只有 41 个因子面板
（152.0 MiB，全量的 1.00%）—— 逐件 sha256 见
[`ops/data_cards/gold_subset_v1.md`](ops/data_cards/gold_subset_v1.md)。
子集够跑题算分，**不够**重新推导 `s4_eco_pool_v1` 那 30 条的选取（那要全量 gold）。
逐部分体积：`ops/reports/i_rehearsal_v2/package_inventory.json`。

<!-- C2-2026-09-13 -->
**磁盘 ≈ 15 GB 是怎么算出来的**（逐项实测，不是估的）：

| 项 | 体积 | 量在哪 |
| --- | ---: | --- |
| clone 一棵仓库（含 `.git`） | 0.03 GB | macOS 实测 32 MB |
| 三个附件本身 | 0.91 GiB（0.98 GB） | 782,100,276 + 157,448,605 + 42,046,516 = 981,595,397 B = 936.1 MiB |
| 解开之后（三个包一起） | 1.15 GiB（1.24 GB） | macOS 实测 1.0 GB + 152 MB，第三件 84,755,038 B |
| Python 3.12 环境（六个包，带 pytest） | 0.25–0.40 GB | macOS venv 实测 249 MB；Linux `pip --target` 实测 377 MB |
| 统一基座 + 一个 harness 镜像 | ≈ 1.7 GB | 实测 `gb-base:bookworm-r1` 889 MB；`gb-cx-u:r1` 1.63 GB（含基座层，两者不重复计） |
| §2.4 那 8 个 run 的目录 | 4.8 GB | 每个 run 约 600 MB（实测 `work/` 608 MB —— 大头是逐 run 物化的 provider 树） |
| docker 自己的镜像层与构建缓存 | ≈ 2 GB | 随构建次数涨 |
| **合计** | **≈ 10.8 GB** | 留余量 → **按 15 GB 准备** |

留 **50 GB** 那一档是给「想连着跑好几批、并且把 run 目录留着当证据」的人；
**200 GB** 只有自己重建数据面（[§2.1](#21-共同前置) 的 (b)）才用得上。

**Python 3.12 怎么装、环境建在哪**（macOS；不动系统自带那个 3.9）：

```sh
GB=$HOME/genebench                                  # 本块自带定义，可以单独跑；§2.1 第一行用的是同一个值
brew install python@3.12
/opt/homebrew/bin/python3.12 -m venv $GB/env        # Intel Mac 换成 /usr/local/bin/python3.12
$GB/env/bin/python -V                               # 要看到 3.12.x
$GB/env/bin/python -m pip install fastapi uvicorn pandas pyarrow duckdb pyyaml
```

**这六个包就是全部硬要求**（`ops/selfcheck_public.py` 第 2 项逐个查）。**想跑仓库自带的测试**再装 `pytest`、`jsonschema` 与 `httpx`：
`ops/test_artifact_schema.py` / `ops/test_genetask.py` 导入前者，`ops/test_gateway.py` / `ops/test_gateway_fields.py` / `ops/test_sim_endpoints.py` 用的
`starlette.testclient` 导入后者 —— 缺这两个包时它们在 **collection 期**报错，`pytest ops/` 会整场中断而不是给你几条可读的红。
**只跑 `ops/selfcheck_public.py`、出题、跑题、出表不需要它们。**

**环境的落点不是随便挑的**：`ops/run_joblist.py` 起子进程时用的是
`genebench_config.PYTHON` = **`$GENEBENCH_ROOT/env/bin/python`**。
把 venv 建在别处，前面几步都正常，到「出表」那一步才报「找不到解释器」。
Linux 上 `python3 -m venv` 常常缺 `ensurepip`（装 `python3-venv` 要 root）——
没有 root 的做法见手册 §1.2。

<!-- C9-2026-09-14 -->
**macOS 上这五个 Linux 工具要么没有、要么不是同一个**：`sha256sum`、`ufw`、`systemctl`、`ss`、`setsid`。
后四个是**真没有**；它们出现在哪几步、Mac 上换成什么，逐条在手册 §1.3（`ufw` / `systemctl`）与 §1.5（`ss` / `setsid`）。
`ops/public_gateway.sh` 自己已经分好岔了：有 `ss` 用 `ss`，没有就用 `lsof`；
有 `setsid` 用 `setsid`，没有就用 `nohup`。**脚本在 macOS 上实跑过**（起得来、`/healthz` 200、`stop` 之后端口释放）。

**`sha256sum` 是 2026-09-14 才补进这张表的（N-839），它的说法要比其它四个小心**，
所以下面写的是**当天在一台 Mac 上逐例量出来的**，不是「众所周知 macOS 没有」：

* **它不在 `/usr/bin`，但当前 macOS 自带一个同名的。** 2026-09-14 在
  **macOS 15.7.4（Darwin 24.6.0，arm64）** 上实测：`/sbin/sha256sum` 在，
  是 **Apple 自己签的**（`codesign` 报 `com.apple.md5sum`，`--version` 报 `sha256sum (Darwin) 1.0`，
  与 `/sbin/md5sum`、`/sbin/sha512sum` 是同一个多名二进制）—— **不是** GNU coreutils。
  `/sbin` 在 macOS 的默认 `PATH` 里，所以 [§2.1a](#21a-数据面-a拿现成的冻结包) 那几条命令
  **在这台机器上原样就能跑**。
* **但别假定它一定在。** `sha256sum` 既不是 POSIX 也不是 BSD 的命令；它是哪一版 macOS 开始随系统发的、
  企业镜像里会不会被裁掉，**我们只有这一台 Mac 可以量，所以不下这个断言**。
  **一定在的是 `shasum`**（perl，`/usr/bin/shasum`，实测 6.02）。
* **两者对我们要做的事等价**（同日逐例实测，同一份 GNU 格式校验和文件）：
  匹配 → `a.txt: OK`、退 0；不匹配 → `FAILED` + `WARNING: 1 computed checksum did NOT match`、退 1；
  文件不在 → 退 1。**有一处不等价**：**校验和行本身写坏**时（例如哈希长度不对），
  **GNU 退 1，Apple 那个退 0**（只打一句 `WARNING: 1 line is improperly formatted`）。
  所以 §2.1a 那句「三行都要 OK」**要看输出**，别只看退出码。
* **§2.1a 的块已经改成两边通用的写法**（一个 `sumc()` 小函数），照抄即可。
  **也可以完全不敲它**：`ops/selfcheck_public.py` 的**第 4 项**（发布附件落位与 sha256）
  是**纯 Python** 的等价物，`sha256sum` 与 `shasum` 一个都不依赖。

**这张表现在是全的。** 2026-09-14 把 README 所有命令块里的命令逐个过了一遍
（除 `brew` / `python` / `git` / `curl` / `tar` / `cat` / `mv` / `mkdir` / `chmod` / `ulimit` / `ssh` / `sh` / `sudo`
这些两边都有的之外，只剩上面五个），**没有第六个**。

## 2. 快速开始

两种部署形态跑的是**同一套代码**，差别只在三个常量和一条防火墙规则：

| | 形态 ① 单机 | 形态 ② 双机（本项目现在的形态） |
| --- | --- | --- |
| 数据面（网关 + 快照 + 答案面） | 与执行面同机 | 独立一台 |
| 执行面（docker：任务容器 + 出向边车） | 同机 | 独立一台 |
| 容器怎么找到网关 | 走宿主 LAN 地址，**要放行宿主防火墙** | 走另一台机的 LAN 地址，不碰宿主防火墙 |
| 「答案面不上执行面」靠什么 | 目录权限 0700 + 推送守门 | 权限 + **物理分机** + 推送守门 |

下面每条命令的完整语义、坑与出处在 [`docs/OPERATOR_MANUAL.md`](docs/OPERATOR_MANUAL.md) 对应节，
本节**不重复正文**。

### 2.1 共同前置

```sh
GB=$HOME/genebench; export GENEBENCH_ROOT=$GB   # **落点自己挑**；`/data/shared/genebench` 是发布方内部的值，外部照抄多半没有写权限
PY=$GB/env/bin/python; REPO=$GB/repo             # venv **必须**建在 $GB/env —— `genebench_config.PYTHON` 写死这个位置；建它的命令就是下面第 4 行
mkdir -p $GB && chmod 700 $GB                    # $GB 及其下每一级都要 0700，否则网关拒绝启动（手册 §7.6）
/opt/homebrew/bin/python3.12 -m venv $GB/env     # 先 brew install python@3.12；Intel Mac 换 /usr/local/bin/python3.12，Linux 换 python3.12
$PY -m pip install fastapi uvicorn pandas pyarrow duckdb pyyaml   # 六个包是硬要求；想跑仓库自带的测试再加 jsonschema httpx
git clone https://github.com/Decilix-Intelligence/GeneBench.git $REPO   # 协议工件单独一棵：https://github.com/Decilix-Intelligence/GeneQuant.git
cd $REPO && ulimit -n 8192                       # 触数据的命令之前必敲，否则 gold 全表扫 Too many open files
$PY ops/guard_modes.py --harden                  # **先收紧、再自检**（顺序不能反，理由紧接在下面）；网关起不来的第一嫌疑（手册 §7.6）
$PY ops/selfcheck_public.py                      # **外部自检**：Python/六个包/docker 内存/发布附件/三条冻结根/网关起不起得来
```

<!-- Y-2026-09-13 -->
**最后两行的顺序是有理由的，别对调回去。** venv 按上面第 2 行的硬要求建在 `$GB/env`，
而第 5 行 `pip install` 装出来的 `.so` / `.py` 默认是**对组 / 其它开放**的；
`ops/guard_modes.py` 的审计走的正是 **`$GB` 全树**。所以先 `selfcheck` 的话，
它的第 6 项（网关起不起得来）**一定是红**，而且红得很唬人 ——
2026-09-13 在一台外部机器上实测：**113 条「模式放松」、网关拒绝启动、`selfcheck` 退 1**。
`--harden` 一跑就收干净（同一次实测「收紧 113 个条目」），再自检就是**绿 5 / 红 1**
（剩下那条红是那台机器真没装 docker）。**照上面的顺序跑，最后一眼就是好的。**
反过来说：你要是已经先跑了 `selfcheck` 并看到一屏红，别急着查环境 ——
先跑 `--harden`，再跑一次 `selfcheck`。

<!-- C2-2026-09-13 -->
> **`ops/test_env.py` 不是给你跑的。** 它是**发布方的内部自检** —— 断言 `/data` 落点、
> 内部数据湖（`market_lake`）、发布方那个解释器与发布方的网关地址、以及 `/data` 留 500 GiB。
> 在干净机器上它必然红一片（2026-09-13 的 macOS 外部验收实测 **10 failed / 52 passed / 2 skipped**），
> **而那些红不是缺陷**。文件保留着，它对内部仍然有用。
>
> 外部要跑的是上面那条 **`ops/selfcheck_public.py`**：只查你自己能满足的六件事
> （Python ≥ 3.12 / 六个包 / docker 在不在且内存够 / 发布附件落位与 sha256 / 三条冻结根 `--check-all` / 网关起不起得来），
> 一条都不碰 `/data`、不碰数据湖、不认发布方的解释器与地址。
> 四种状态：**绿**、**红**、**跳过**（前置还没做，例如附件还没下）、**登记在案**（已知的发布缺件，不是你机器的问题）。
> **有红条才退非零**；`--strict` 把后两种也算成不通过。`--role data` 用于「这台只当数据面」（不查 docker）。
>
> <!-- P2-2026-09-13 -->
> 同理，**`$PY ops/mk_release_manifest.py --check` 是发布方自检**，外部不必跑 ——
> 但跑了**应当退 0**。这份清单**刻意不取决于跑它的机器**
> （`clone_urls_declared` 的 docstring 就是这么写的）；曾经有两处机器依赖
> （「这台 clone 有没有 remote」「这台有没有发布方那批 `m6_public` 的 run 清单」）
> 让它在**每一个**外部 clone 上退 1，2026-09-13 已修根因（用户裁定 ②）。
> 要核发布件完不完整，看的是另外两样：`ops/freeze_v10.py --check-all` 与附件的
> `sha256sum -c`（**macOS 的 `/usr/bin` 里没有 `sha256sum`**，一定在的是 `shasum -a 256 -c`；
> 两者的逐例实测与唯一那处行为差异见 §1.5）—— 这两样 `ops/selfcheck_public.py` 都替你跑了，
> 而且它的**第 4 项是纯 Python 的等价物**，这两个命令一个都不依赖。

<!-- C2-2026-09-13 -->
**模型认证怎么配（key 要你自己准备）。** 发布件里**没有任何可用的 key**，也不该有。
落点是 `~/.config/genebench/secrets.env`，`0600`，一行一个：

```sh
mkdir -p ~/.config/genebench && chmod 700 ~/.config/genebench
: > ~/.config/genebench/secrets.env && chmod 600 ~/.config/genebench/secrets.env
# 文件内容：变量名由你要跑的那条 config.yaml 的 `api_key_env` 决定，**必须以 _API_KEY 结尾**
# DEEPSEEK_API_KEY=<你自己的 key>
```

三条要点：**①** `config.yaml` 里只写**变量名**（`api_key_env`），**永远不写值**；
**②** 容器里拿到的是**占位 key**，真 key 由出向边车注入 —— 所以 key 不进镜像、不进 bundle、不进日志；
**③** `base_url` 必须是 https，而且**要与你的 key 同源** —— 把某一家的 key 发给另一家的默认端点，
轻则 401，重则把 key 泄给了不该拿到它的人。出向白名单与 `base_url` 同源是一条测试（手册 §2.5）。
逐键说明在手册 §2.1，key 的落点与注入路径在手册 §2.4。

数据面二选一（手册 §1.4）：**(a) 拿现成的冻结包** —— 三个附件挂在 GitHub Release `v1.0.16` 上，见下面 [2.1a](#21a-数据面-a拿现成的冻结包)；
**(b) 自己从公开源建** —— 不想下 896 MiB、或者想自己走一遍数据链的话：

```sh
$PY ops/build_public_channel.py --dry-run        # 六步先看一遍，什么都不动
$PY ops/build_public_channel.py                  # fetch→tables→gate→tradability→provider→verify（可续跑）
$PY ops/run_public_chain.py --dry-run            # 重建链六步（universe→…→calibration，全链约 4 小时 15 分）
```

`--spill-root` 默认开着，**别关**：792 个面板同时压内存时常驻 22 GiB，30 GiB 的机器上被 OOM killer 收走过两次。

### 2.1a 数据面 (a)：拿现成的冻结包

三个附件挂在 GitHub Release **`v1.0.16`** 上，加起来 **936.1 MiB**，解开约 **1.15 GiB**：

| 附件 | 字节数 | sha256 |
| --- | --- | --- |
| `genebench_public_provider_v1.tar.gz` | 782,100,276（745.9 MiB） | `33083ff242c64a8f0bbbcec332ef4d3ad87daa703b78d95728ccdd1bdefc18e9` |
| `genebench_public_gold_subset_v1.tar.gz` | 157,448,605（150.2 MiB） | `edc5ea7cf70ffec3589b981cd67b2b9872527ea8001a2495bde8d6c55ec9ef06` |
| `genebench_public_runtime_v1.tar.gz` | 42,046,516（40.1 MiB） | `49e9b250d398a1ceaad22da3de6d2cc87605a5dc036113bf4b19f04e2e00963f` |

**下到哪儿**：接着上面 [§2.1](#21-共同前置) 的 `cd $REPO`，下面几条就落在**仓库根**下 ——
`ops/selfcheck_public.py` 的第 4 项会在这里找它们（也认 `./downloads/`、
`$GENEBENCH_ROOT/`、`$GENEBENCH_ROOT/downloads`，或者 `--downloads <目录>` 指过来）。

```sh
B=https://github.com/Decilix-Intelligence/GeneBench/releases/download/v1.0.16
curl -L -O $B/genebench_public_provider_v1.tar.gz
curl -L -O $B/genebench_public_gold_subset_v1.tar.gz
curl -L -O $B/genebench_public_runtime_v1.tar.gz

# ① 先校验包体本身。三行都要 OK —— 少一行就是没下全，别急着解包
cat > SHA256SUMS.release <<'SUMS'
33083ff242c64a8f0bbbcec332ef4d3ad87daa703b78d95728ccdd1bdefc18e9  genebench_public_provider_v1.tar.gz
edc5ea7cf70ffec3589b981cd67b2b9872527ea8001a2495bde8d6c55ec9ef06  genebench_public_gold_subset_v1.tar.gz
49e9b250d398a1ceaad22da3de6d2cc87605a5dc036113bf4b19f04e2e00963f  genebench_public_runtime_v1.tar.gz
SUMS
# 核包的命令两边不同名：Linux 上是 GNU 的 `sha256sum`；macOS 的 `/usr/bin` 里没有它
# （当前 macOS 在 `/sbin` 下自带一个 Apple 版的同名命令，但**别假定它一定在**），
# **一定在**的是 perl 的 `shasum`。逐例实测与两者唯一那处行为差异见 §1.5。
# 下面这个小函数两边通用。**别写成 SUMC="sha256sum -c" 再 $SUMC …** ——
# macOS 默认 shell 是 zsh，它**不对未加引号的变量做词分割**，那样写会去找一个
# 名叫「sha256sum -c」的命令（实测 `command not found`）。函数没有这个问题。
sumc() { if command -v sha256sum >/dev/null 2>&1; then sha256sum -c "$@"; else shasum -a 256 -c "$@"; fi; }

sumc SHA256SUMS.release          # 三行都要 OK —— **看输出，别只看退出码**（理由在 §1.5）

# ② 解开之后逐件校验。**三个包的校验和文件各不同名**，写混了会「找不到文件」
tar xzf genebench_public_provider_v1.tar.gz
( cd genebench_public_provider_v1 && sumc SHA256SUMS )                          # 28,658 行，约 0.8 秒
tar xzf genebench_public_gold_subset_v1.tar.gz
( cd genebench_public_gold_subset_v1 && sumc gold_subset_SHA256SUMS )           # 46 行，约 0.1 秒
tar xzf genebench_public_runtime_v1.tar.gz
( cd genebench_public_runtime_v1 && sumc runtime_SHA256SUMS )                   # 533 行，约 0.4 秒
```

<!-- P2-2026-09-13 -->
**③ 落位。解包目录与运行时布局不是一一对应的，`provider/` 还要改名**（N-771）——
此前**任何文档都没给过这一段**，2026-09-13 的 Mac 外部验收与同日的 Linux 端到端实证各撞了一次：

```sh
# 承 §2.1 的 $GB；在三个包解开之后的那个目录里跑
mkdir -p "$GB/snapshots/public_v1"

# ① provider 包：provider/ **要改名**成 qlib_provider/，另外三个同名搬
mv genebench_public_provider_v1/provider  "$GB/snapshots/public_v1/qlib_provider"
for d in tables tradability universe; do
  mv "genebench_public_provider_v1/$d" "$GB/snapshots/public_v1/$d"
done

# ② gold 子集包：一个目录，同名搬
mv genebench_public_gold_subset_v1/gold_factors "$GB/snapshots/public_v1/gold_factors"

# ③ 第三件（公开题集实例 + 标定物料）自带落位命令，包内 runtime_README.md 里那一条就是：
#    --strip-components=1 把包内顶层目录剥掉，两棵子树正好落到 reference/tasks/public/… 与 snapshots/public_v1/
tar -xzf genebench_public_runtime_v1.tar.gz --strip-components=1 -C "$GENEBENCH_ROOT"
```

解包目录里**剩下的三样不用落位**：`docs/`（许可与数据卡）、`selfbuild/`（形态 B 的脚本副本）、
`frozen/`（`factor_library/compiled/*.jsonl` 与 `reference/factorlib_pinned/*.py` 的随包副本 ——
仓库里本来就有这六件，随包这份是给你对一遍用的）。

**改名那一步漏掉的表现很不友好**：网关照样起得来、`/healthz` 照样 200（它读的是 `tables/`），
一直要到取行情才报 provider 不在。落位对不对，跑一次 `$PY ops/selfcheck_public.py` 就知道。

> **两个附件已经挂上去了**（Release [`v1.0.16`](https://github.com/Decilix-Intelligence/GeneBench/releases/tag/v1.0.16)，2026-09-13）——
> 同日下午**第三件也挂上了**，现在是**三件**；上面那三条 `curl -L -O` **匿名就能下**，不需要 token。
> 传完之后从同一条地址下回来重算过 sha256，与上表逐字相同；
> 上表、[`ops/release/attachments.json`](ops/release/attachments.json)、
> `RELEASE_MANIFEST.json` 的 `release_attachments` 三处同源。
> 上传与回核的逐步记录在 [`ops/reports/push_result.md`](ops/reports/push_result.md) §7（前两件）与 §8.5（第三件）。
> **(b) 自己从公开源建那条路同样是通的**，两条都可以。

<!-- C2-2026-09-13 -->
> **附件到底有几件，以 [`ops/release/attachments.json`](ops/release/attachments.json) 为准，不要数上面这张表。**
> 上表列的是**已经挂上去、匿名能下**的那三件。清单里还可能有**登记了但还没上传**的条目
> （那种条目的 `download_url` 是空串）—— **2026-09-13 起一条都没有了**：第三件
> `genebench_public_runtime_v1.tar.gz`（整棵公开题集树 + `calibration.json` + `epsilon/`，
> **缺了它公开冻结根核不绿、题也跑不起来**）当天下午也传了上去，三条地址都已回填。
> `ops/selfcheck_public.py` 会把这两类分开说：已挂的那几件逐件核 sha256，还没挂的只提醒一句、不判红。

包里有什么、**少了什么**：

* `provider/` —— qlib 格式的冻结行情面，28,656 件。行情来自 **baostock**
  （`adjustflag=3` 前复权 + 复权因子），冻结线 `2026-07-31`。
* `provider/instruments/` 与 `universe/universe_pit.parquet` —— 宇宙定义面，
  **由 baostock 成分接口重建**（`query_hs300_stocks` / `query_zz500_stocks`），
  不含任何第三方派生的成分行。逐行核对见
  [`ops/reports/release_scan_publish.md`](ops/reports/release_scan_publish.md) §1。
* **`csi1000` 不在包里**（baostock 没有该成分接口）——
  公开通道复现不出任何以 csi1000 为宇宙的读数。
  发布方机器上那份 `$GENEBENCH_ROOT/snapshots/public_v1/gold_factors/csi1000`（8.3 GiB / 8.9 GB，792 件）
  **保留着但不随包发** —— 它算在旧的 tushare 派生成分名单上，正是这次换面要去掉的东西。
* **gold 只发子集**：40 行出集 + 130 个实例真正读到的 41 个因子面板（152.0 MiB，全量的 1.00%）。
  够跑题、够算分，**不够**重新推导 `s4_eco_pool_v1` 那 30 条的选取 —— 那要全量 gold。
* **子集与随包的阈值不同源**：子集算在**换面之后**的 provider 上，而随包的
  `calibration.json`、ε 阈值与仓库里已发布的 18 个公开 run 算在**换面之前**那一版成分名单上。
  **说清后果**：你拿这个包算出来的分是对的、可复现的；但 `calibration.json` 里的 τ、
  ε 带与 IC 族阈值**不是在这份 gold 名单上标定的** —— 它们标定在换面之前那一版名单上。
  所以「分」可复现，「分算出来之后拿哪条线去判它过不过」这一步是**跨名单**的：
  逐格对齐我们已发布的 18 个公开读数会有差，贴着阈值的边界样本可能判反。
  **阈值与当前 gold 名单不同源，本轮不重算，重算排 v1.0.17。**
  同一件事在 [`DATA_LICENSE`](DATA_LICENSE) §6 也写了一遍；逐条量化见
  [`ops/reports/known_limits_v1.md`](ops/reports/known_limits_v1.md)。

### 2.2 形态 ② 双机

```sh
systemctl --user status genebench-gateway.service          # 私有网关（systemd 用户单元，绑 LAN 显式地址）
curl -sS --max-time 5 http://<数据面 LAN 地址>:18080/healthz  # 手册 §1.5：ok/freeze_line/channel 三样都要对
ops/public_gateway.sh start                                # 公开通道网关（脚本起停，另一个端口）
git status --porcelain                                     # 推 exec 树之前看一眼：别把别人的半成品推过去
ops/push_exec_to_f02.sh --with-launch-data                 # 同步 exec 树（不带这个开关，执行面找不到新 config_id）
ssh <执行面> 'sh exec/harnesses/build.sh <id>'              # 在执行面构建 harness 镜像，拿 digest（手册 §3）
```

**只看 `"ok":true` 不够。** `/healthz` 的 `channel` 必须是你以为的那条 ——
起了个私有实例却以为在跑公开通道，是这一步最贵的错：数字看起来全对，只是来自另一份数据。

### 2.3 形态 ① 单机

跑同一套东西，多两件事要做，**少一台机器的物理隔离**：

```sh
# ① 唯一要 root 的一条：放行「容器网段 → 宿主自身的网关端口」。手册 §1.3
#    容器发往宿主自身 IP 的包走 INPUT 链，docker 只在 FORWARD 链插规则，管不到这条。
#    **端口要跟你实际起的那个网关实例走**。两个值刻意不同（`genebench_config.py`）：
#      公开通道 GATEWAY_PUBLIC_PORT = 18081  ←—— 外部用户按 §2.4 ⓪ 走的就是这条
#      私有通道 GATEWAY_PORT        = 18080      发布方内部那条；外部手上没有它的题集
sudo ufw allow from 172.31.240.0/22 to any port 18081 proto tcp   # 公开通道（默认按这条）
# 走私有通道时把 18081 换成 18080；两条都起就放行两次。**不要**改成放行 any
# ② 更不要把网关改成监听 0.0.0.0——后者会被 assert_no_wildcard_bind() 当场抛
$PY ops/guard_modes.py --harden
curl -sS --max-time 5 http://<本机 LAN 地址>:18081/healthz   # 公开通道；私有通道是 18080
sh harnesses/build.sh <id>                                  # 执行面就是本机，直接构建
```

<!-- H10-2026-09-14 -->
**① 那条规则的端口写错了，失败形态极难认**（用户 2026-09-14 点名要写清）：
容器起得来、模型照样调得动，**只有数据网关打不通** —— run 一路空转到 1500 秒墙钟闸、
以 `124` 退出，读起来像「agent 不会做题」，比报一条错难查十倍。
两个端口的值与「为什么刻意不同」都在 [`genebench_config.py`](genebench_config.py)：
`GATEWAY_PORT = 18080`（私有通道）、`GATEWAY_PUBLIC_PORT = 18081`（公开通道）——
后者的注释原文写着，「忘了设端口」的失败形态必须是**起在 18081**，
不能是**抢私有网关的 18080**。**所以别把这条规则改回 18080 了事**，那样它就不生效了。
端口从代码现算是 `genebench_config.gateway_port(channel)`（环境变量
`GENEBENCH_GATEWAY_PORT` 赢过通道默认值）。容器网段取
[`runner/c41/runner_core.py`](runner/c41/runner_core.py) 的 `EGRESS_SUBNET`
所在的那个 /22（默认 `172.31.240.0/24` 与 `172.31.241.0/24`，真运行逐 run 分配）。

<!-- C2-2026-09-13 -->
**③ 还有三处地址常量要改成本机的**（手册 §1.3 有整张表）：`genebench_config.py::GATEWAY_HOST`、
`runner/c41/runner_core.py` 里的网关地址常量、`runner/c41/runner_core.py::LAN`。
**`GATEWAY_HOST` 没有环境变量可以覆盖**（端口有 `GENEBENCH_GATEWAY_PORT`，地址没有），
只能改常量 —— 这是外部用户第一步就会撞上的事，`ops/selfcheck_public.py` 的第 6 项会直接告诉你「这台机器绑不上它」。
只在本机自测（不起容器）就改成 `127.0.0.1`；容器要打它，就得是**本机 LAN 地址**。

<!-- Y-2026-09-13 -->
**④ 还有一处不是常量、是环境变量：执行面的 ssh 目标 `GENEBENCH_F02` —— 它只对双机形态成立。**

* **单机形态（`--topology single`）：这一整段跳过。** 这条路上**一条 `ssh` 都不发** ——
  bundle 与 exec 树在本机落位（[`runner/placement.py`](runner/placement.py)）、真跑的 inner 是本机
  `bash -c`、两件执行面前置探针也在本机跑。所以**不必**设 `GENEBENCH_F02`，
  更**不必**为它去配「免密 ssh 到本机」。旧版这里写的是
  「单机形态下 export GENEBENCH_F02=<你>@127.0.0.1（并且要能免密 ssh 到本机）」——
  那是**双机的退化写法**：它还要求本机能 ssh 自己、要求远端有 systemd timer、
  要求造得出发布方那个执行面根，三件在 macOS 上都不成立。
* **双机形态：`export GENEBENCH_F02=<你>@<执行面主机>`**，
  **五个**入口一起跟着走：`ops/push_bundle_to_f02.sh`、`ops/push_exec_to_f02.sh`、
  `ops/api_usage.py`，以及跑批与结算这两个 —— `ops/run_joblist.py::F02`、`ops/score_runs.py::F02`。
  **后两个此前是写死的**：2026-09-13 在一台外部机器上实测，设了 `GENEBENCH_F02` 之后
  §2.4 ④ 干跑里的 ssh 目标**仍然是发布方那台**，而用户只能改源码、且无处得知要改哪两行。
  现在这两处也读同一个变量；**不设它时默认值一个字没变**（发布方那台的行为不受影响）。

**macOS 上 ① 那条 `ufw` 不适用** —— Mac 没有 `ufw`，也没有 `systemctl`。
Mac 的包过滤是 `pf`，而且 Docker Desktop 的容器跑在一层 Linux 虚拟机里，
容器打宿主走的是 VM 的网，不经过宿主 INPUT 链 —— 那条规则要解决的问题在 Mac 上换了形状。
**替代的隔离判据没有变，仍然是容器边界那一条**：答案面（`reference/`、`scorer/`、`runs_in/`、
`gold/`、`memory_probe_answers/`）**永不挂进 agent 容器**，由
`runner/f02/answer_plane_guard.py --mode container` 读 compose 挂载面判定，命中就**拒绝启动**。
**别用「放行了防火墙」去替代它，也别因为 Mac 没有 ufw 就以为少了一层** —— 这两件事本来就不是同一层。
同理，推送守门要求执行面上那道 `genebench-answer-plane-scan.timer` 处于 `enabled + active`，
**这是 systemd 的东西，Mac 上没有**；Mac 上的等价做法与「没有它意味着少了什么」写在手册 §1.3。

> **拿不到 root 就直接走形态 ②。** 上面两件事都要机器主人执行，
> 而「换一个绑定地址」绕不过去 —— 容器打宿主的 LAN 地址、docker0 地址、
> 自建网自己的网关地址，三种全部超时（手册 §1.3 有三行探针结论）。

<!-- C2-2026-09-13 -->
> **状态（2026-09-13，别读成「都验过了」，也别读成「没验过」）。**
> **Linux 上这一形态已经端到端跑通**：2026-09-11 在一台机器上、只用发布包解出来的树，
> 走完了解包 → 起网关（绑本机 LAN 地址，`/healthz` 200、`channel=public`、**不是** `0.0.0.0`）→
> 建 harness 镜像 → 落 secrets → **3 题双臂真跑** → 结算 → 出表；
> 逐步证据在 [`ops/reports/rehearsal_v2.md`](ops/reports/rehearsal_v2.md)，手册 §1.1 / §1.3 记的是同一件事。
> **macOS（arm64）上还没跑通**：**下载 → 逐件核 sha256 → 解包 → 本机网关 `/healthz` 200**
> 四步是**实测通过**的（2026-09-13 的外部验收），再往后就停了。
> 读法就是这一句：**流程与网络在 Linux 上验到底了；Mac 上验到网关为止。**
>
> <!-- C9-2026-09-14 -->
> **这一句的「为什么」2026-09-14 换过一次（N-843）—— 旧版那两条成因都已经不成立了。**
> 旧版原话是：「2026-09-13 的外部验收走到「建 harness 镜像」就停了 ——
> 本机没有统一基座 `gb-base:bookworm-r1`，公开题集 S4–S7 那 18 道题的输入夹具也没有随两个附件交付。」
> **两条同一天都补上了**：基座的整套构建上下文随树发了（`build/base/`，
> 而且 `harnesses/build.sh` 发现缺基座会自己构）；S4–S7 那 18 道题在**第三件附件**带来的
> 公开题集树里，2026-09-14 的交付终核落位后逐题核过。
> **照旧版去补这两件，补完照样走不过去** —— 所以这里换成今天真正的那一条。
>
> **今天真正拦路的，是单机形态那条路上还留着的跨机步骤。** 下面 §2.4
> ③④ 两步走的是 `ops/push_exec_to_f02.sh` / `ops/push_bundle_to_f02.sh`，
> 而它们和它们背后的几个根都是按「发布方那台 Linux」写的：推送脚本的解释器与暂存目录
> 默认指着发布方的绝对路径；执行面的 run 根写死 `/data/genebench_runner`，推送脚本还把
> 「目标必须在这个根下」写成硬判据；推送前要 `ssh` 到执行面核一道 `systemd` 的 timer
> （手册 §1.3 自己写着「Mac 上这条过不去」，而脚本没有任何绕过开关）；跑批每个 job 都要拿的
> 那把网关锁，锁根也是写死的。
>
> **这四条在 Linux 上永远不显形**，原因很朴素：**Linux 上 `mkdir /data` 就把那些写死的路径
> 造出来了**（此前的端到端正是这么走过去的），于是判据看起来全对；而 **macOS 自 Catalina 起
> 根卷只读**，`sudo mkdir /data` 直接报 `Read-only file system`，同一份代码在 Mac 上就是硬停。
> 这一支的定义与前七例见 [`ops/reports/known_limits_v1.md`](ops/reports/known_limits_v1.md)
> 的 **D-06 家族第八例**。
>
> <!-- H10-2026-09-14 -->
> **这条新路已经在这棵树里了，而且实测可用 —— 不是「待建」。**
> 旧版这一段写的是
> 「已经排进施工（用户 2026-09-14 裁定 ①②）：单机形态定义为一条不含任何跨机步骤的路径 ——
> 单机没有「推」这件事，bundle 与 exec 树本来就在本机，那两步换成本地落位；
> 其余的根一律从 GENEBENCH_ROOT 现算。双机形态一个字不动。
> 这条落地之前，上面那句结论不变；落地之后这一段会跟着改」。
> 那句话的问题不是「让读者去补一件还没有的东西」，
> 是**让读者不知道自己手上已经有了**。现状（2026-09-14 落地）：
>
> * 单机形态 = **一条不含任何跨机步骤的路径**。入口是
>   [`runner/placement.py`](runner/placement.py)，跑批那一侧是 `ops/run_joblist.py --topology single`；
>   照抄命令见下面 §2.4 ③④。
> * **形态判据是显式的**：`--topology single|dual` > 环境变量 `GENEBENCH_TOPOLOGY` > 默认 `dual`；
>   两者都给且不一致**当场拒绝**。**没有** hostname / `uname` / 路径存在性嗅探
>   —— 有一条测试专门禁止它们出现在 `resolve_topology()` 里。
> * **本地落位不是「绕过守门」**：它调的是**同一批门、同一份实现、同样顺序**
>   （[`ops/push_guard.py`](ops/push_guard.py) →
>   [`runner/f02/answer_plane_guard.py`](runner/f02/answer_plane_guard.py) `--mode container` →
>   本地拷贝 → 落地之后再用树口径扫一遍）。
> * **双机形态一个字没动**：[`ops/push_bundle_to_f02.sh`](ops/push_bundle_to_f02.sh) 与
>   [`ops/push_exec_to_f02.sh`](ops/push_exec_to_f02.sh) 这一轮**一个字节都没改**，
>   也没有加任何绕过开关。
> * 门在 [`ops/test_single_machine.py`](ops/test_single_machine.py)。它此前钉着几条
>   **strict xfail**，对应这条路上四个**只在单机形态显形**的执行面缺陷；
>   **那几条 2026-09-14 已经修完，xfail 标记随之删掉**，今天这道门是绿的。
>   唯一 skip 的那条是「真跑前置没齐」——没有 docker / 没有模型 key / 网关没起 /
>   执行面上还没有 provider，它会**逐条**告诉你缺哪件，正好当自查用。
>   已知限制逐条见 [`ops/reports/known_limits_v1.md`](ops/reports/known_limits_v1.md)。
> * **单机形态少了一件，说清楚**：双机那条路还核一件事 —— 执行面上
>   `genebench-answer-plane-scan.timer` 处于 `enabled + active`（每小时的**兜底**扫描）。
>   单机用的是**落位即扫**（上面那两道门每一次落位时同步跑），**不是**每小时一次的周期复查；
>   差别就落在「**落完了、还没跑**」那段时间窗里 —— 那段时间没有第二次复查。
>   主判据（挂载面口径）**一条没松**。**这一件本轮不做，登记 v1.1**（用户 2026-09-14 裁定 ②）。
>
> **上面那句结论一个字不改，也别把它读宽**：**Linux 上验到出表；Mac 上目前仍然只验到网关。**
> 「本树里有这条路」与「这条路在 Mac 上被走过」是两件事。
>
> <!-- P2-2026-09-13 -->
> **2026-09-13 又多了一次更强的 Linux 实证。** 强在「没有任何遗留物」——
> 2026-09-11 那次跑在一台参与过开发的机器上，**看不见缺件**；这一次的树上
> 本项目**一件遗留物都没有**，只凭 `git clone` + 三个附件走完：
> 建统一基座（仓库 `build/base/`，`--no-cache` **69 秒**，`pip freeze` 与发布方那份逐行相同）→
> 建 harness 镜像 → 起网关 → 出集三个 bundle →
> **3 题双臂 6 个 run 真跑 2 小时 1 分 / 582 次真模型调用** → 结算 → 入库 →
> 出表（`--table main`，实测 **19 指标列 + 5 身份列 = CSV 24 列**）。
> **唯一的例外**是结算与入库那两步先补了两条软链 —— `ops/score_runs.py` 与
> `ops/results_db.py` 当时用的 run 根不同源（在发布方机器上它们恰好是同一个路径，
> 所以这处分叉内部永远看不见）。那个缺陷 2026-09-13 已修，显式入口是
> `ops/score_runs.py --runs-root`，同机结算还要 `--remote-host local`。
> 逐步实测在 [`ops/reports/mac_gap_closeout.md`](ops/reports/mac_gap_closeout.md) §4–§5。
> **这一句不改上面那两句的结论**：Mac 那一侧仍然只验到网关。

### 2.4 最短路径：4 道题 → 一张表

现成的验收矩阵 [`ops/joblists/v1demo.yaml`](ops/joblists/v1demo.yaml) 是
4 道题 × 双臂 × 1 配置 × 1 种子 = 8 个 run（刻意避开 S4/S7 那两个多轮阶段）：

```sh
export GENEBENCH_CHANNEL=public                                     # ⓪ **公开通道要显式开**，理由紧接在下面
$PY ops/joblist.py gen --matrix ops/joblists/v1demo.yaml            # ① 生成清单
$PY ops/run_joblist.py --jobs $GB/runs_in/v1demo/jobs.jsonl --dry --channel public   # ② 干跑：六段命令原样打出来，不动真格
```

<!-- H10-2026-09-14 -->
**③④ 两步按形态分岔 —— 先认清自己是哪一种。** 判据是**显式**的，工具不猜：
`--topology single|dual` > 环境变量 `GENEBENCH_TOPOLOGY` > **默认 `dual`**
（两者都给且不一致**当场拒绝**）。**不给就是双机** —— 单机用户忘了给，
会得到一条 `ssh` 到发布方执行面的命令，而那台机器不是你的。

**形态 ① 单机**（数据面 / 执行面 / 答案面同一台机器，整条路**一条 `ssh` 都不发**）：

```sh
export GENEBENCH_TOPOLOGY=single                                    # 也可以每条命令都带 --topology single
$PY -m runner.placement --topology single --where                   # ③⁰ 先把这套部署的几个根打出来看清楚
$PY -m runner.placement --place-exec --with-launch-data             # ③ exec 树**本地落位**（= 双机的 push_exec）
$PY ops/run_joblist.py --jobs $GB/runs_in/v1demo/jobs.jsonl --channel public --topology single --check-plane          # ③c 只探不跑
$PY ops/run_joblist.py --jobs $GB/runs_in/v1demo/jobs.jsonl --resume --tables main,a,b --channel public --topology single   # ④ 真跑（可续跑）
```

**形态 ② 双机**（本项目自己的形态，这一轮一个字没变）：

```sh
git status --porcelain                                              # 推之前看一眼：别把别人的半成品推过去
ops/push_exec_to_f02.sh --with-launch-data                          # ③ 手工推 exec 树（刻意留在流程外）
$PY ops/run_joblist.py --jobs $GB/runs_in/v1demo/jobs.jsonl --channel public --check-plane          # ③c 只探不跑
$PY ops/run_joblist.py --jobs $GB/runs_in/v1demo/jobs.jsonl --resume --tables main,a,b --channel public   # ④ 真跑（可续跑）
```

<!-- H10-2026-09-14 -->
**③b 执行面还要一份 provider —— 这一步此前两份文档里一个字都没有。**
它是「一个 job 就算有 docker、有 key 也走不到表」的**直接原因**：注入器 P2 要在
**执行面那棵树**上比一份 provider 的根 sha256，比不上就每个 run 都红，
而那条报错读起来像「注入器坏了」。**两种形态都要做这一步**，
差别只是一个在本机 `cp`、一个 `rsync` 过去。

```sh
# 目录名的约定是 qlib_provider_<公开 provider 根 sha256 前 8 位>。**那 8 位现算，别手抄**：
P8=$($PY -c "import runner.inject as I; print(I.provider_pin_expect('public')[:8])")
echo "$P8"          # 公开通道现在是 f7dda289

# <执行面根> 就是上面 ③⁰ 那条 --where 打出来的 runner_root
#（单机 = $GENEBENCH_ROOT/genebench_runner；`GENEBENCH_RUNNER_ROOT` 可覆盖）
mkdir -p "<执行面根>/provider"
cp -a "$GB/snapshots/public_v1/qlib_provider" "<执行面根>/provider/qlib_provider_$P8"   # 单机：本机 cp
# 双机：rsync -a "$GB/snapshots/public_v1/qlib_provider/" <你>@<执行面主机>:<执行面根>/provider/qlib_provider_$P8/
```

**那 8 位是哪来的**：`runner.inject.provider_pin_expect('public')` 返回的是**公开 provider
树的根 sha256** —— 定义是「该树顶层 `files.sha256` 这个文件本身的 sha256」，**现算**，
不采信树里记着的值；现在是 `f7dda2899071b07a…`，所以目录名是 `qlib_provider_f7dda289`。
**自查不必真跑一道题**：上面 ③c 那条 `--check-plane` **只探不跑** ——
它把「执行面打不打得到该通道的网关」与「执行面上有没有根 sha 对得上的 provider」
两件一起探完打一份 JSON，**退出码 0 = 两件执行面前置都齐**；缺哪件它会把补法逐条写出来。

出表两种形态相同：

```sh
$PY ops/mk_tables.py --table main --format csv --filter batch=v1demo --out ops/reports/<你的目录>
```

<!-- Y-2026-09-13 -->
**⓪ 与两个 `--channel public` 不是可有可无的。** `ops/run_joblist.py --channel` 的
**默认值是 `private`** —— 而私有题集 `$GB/reference/tasks/v1.0-smoke` 按设计**永远不随发布件交付**
（答案面不出内网）；你手上有的是第三件附件带来的 `$GB/reference/tasks/public/v1.0-smoke-public`，
`v1demo.yaml` 那四道题在公开题集里**都在**，所以差的只是这个开关。
不带它的代价是**静默**：② 干跑会照私有题集根把六段命令原样渲染出来（看起来一切正常），
要到 ④ 真跑那一步才报「找不到任务目录」。
两个只给一个时工具会当场拒绝并把正确命令打出来（`--channel` 管本进程，
`GENEBENCH_CHANNEL` 管它 import 的一切，两者必须一致）——**一个都不给才是那条静默的路。**

<!-- C2-2026-09-13 -->
**要引的那张表是 `--table main`，不是 `--table a`。**

| | `--table main` | `--table a` / `--table b` |
| --- | --- | --- |
| 是什么 | **发布表**（主表 `table_main`）——「这个系统在这套题上是什么水平」就引它 | **诊断表**，给自己看的 |
| 列 | **19 个指标列 + 5 个身份列 = CSV 24 列**，列名与顺序写死 | 全量指标，列会随诊断量增减 |
| 19 列是哪些 | `SR` `P@1` `$` 三个总览列 + 每阶段两列：`Cov`/`Prov`（S1）、`Cell%`/`Adj`（S2）、`Fid`/`Decl`（S3）、`IC-agr`/`Set`（S4）、`Sig`/`ρ̄`（S5）、`W-agr`/`Cons`（S6）、`ε-agr`/`Ledger`（S7）、`Audit`/`Ovr`（S8） | — |
| 5 个身份列 | `config_id` `arm` `arm_kind` `n_tasks` `n_runs`（**不是指标**） | 同左 |

主表**没有总分**：把多阶段合成一个数的列（`total` / `overall` / `score` / `effect` …）
被一条测试当场拦掉 —— 少了那一列不是漏了，是刻意的。
列名与顺序由 `ops/test_report_columns.py` **逐字钉住**（列集相等 + 顺序相等），
逐列的定义 / 数据源 / 闸门条件 / 不可得时显示什么在 [`ops/reports/report_spec_v1.md`](ops/reports/report_spec_v1.md)。
`--table a` 带一列 `effect`，那是诊断量；**别拿 Table A 当发布读数往外贴**。
（`ops/run_joblist.py --tables` 的帮助文本还只写着 `a,b,adaptation`，但它是原样透传给
`mk_tables.py --table` 的，`main` 一样认。）

一个 job 的六段是：出集 → 推送 bundle → 真跑 → 结算 → 入库 → 回写状态。
中断之后**原样再敲一次同一条命令**就是恢复；失败与撞预算闸都是终态，**不自动重跑**。

**照抄这份矩阵之前先读手册 §5.3。** 默认预算档的 `max_tokens` 现在是 **6,000,000**
（N-388 已裁定，2026-09-10；此前是 600,000，实测一批 8/8 撞的是 token 闸、调用数只用到
18–22 / 100 —— 那样读出来的 `SR` / `pass@1` 是**「预算够不够」而不是能力**）。
**因此真跑不必再显式给 `--max-tokens`，矩阵 yaml 里也不要再写 `max_tokens: 3000000`** ——
显式给的逐键赢过档位，写 3M 反而把默认档从 6M 压下去，S4 / S7 更是把自己的
9M / 18M 一起打回去。让档位生效就是正确做法：S4 150 次 / 9M、S7 300 次 / 18M、其余 100 次 / 6M。
上面这份 `v1demo.yaml` 里那一行已经删掉（2026-09-10 随 N-388 同步）。
既有历史读数不追溯：`ops/reports/v1demo/` 那 8 个 run 是在 600k 默认档下跑的，
它们是 N-388 的证据，不改。

<!-- S-2026-09-13 -->
**预算档到底给多少、撞了闸算什么**（用户 2026-09-13 点名要写清。数出自
[`runner/registry.py`](runner/registry.py)，别照抄转述）：

| 档 | `max_calls` | `max_tokens` | 谁吃这一档 |
| --- | ---: | ---: | --- |
| 默认 `RUN_BUDGET` | **100** | **6,000,000** | S4 / S7 之外的全部阶段 |
| `BUDGET_TIERS["S4"]` | **150** | **9,000,000** | S4 |
| `BUDGET_TIERS["S7"]` | **300** | **18,000,000** | S7 |

也就是：默认 **100 次调用 / 6,000,000 tokens**，**S4 150 次 / 9M**、**S7 300 次 / 18M**。
入口是 `runner/registry.py::budget_for(stage)`，而 `--max-calls` / `--max-tokens`
**逐键赢过档位** —— 所以两行都不写才是让档位生效（手册 §5.3）。

**撞闸记 `budget_exhausted`，那是一个收口状态，不是失败。**
它与 `ok` / `violation` / `timeout` 并列，同属 `runner/c42/failure_modes.py::RUN_STATUSES`
（那个元组的顺序即判定优先级）。跟着来的三件事：

* **主表里那一格渲染成 `—`**（`scorer/report.py::NO_READING`），而 `—` / `0` / `unobservable`
  是**三个不同的东西**：`0` 是「测了，是零」；`—` 是「这一格的 run 全落在拒绝 / 诚实终止 /
  未结算 / 预算截断四类里，**没有读数**」；`unobservable` 是「有可用的 run，但这个量在它们身上
  **根本测不了**」。混成一个，恒绿的门就看不出来了（另有第四种 `n/a` = 这个量在这一阶段不定义）。
* **撞了闸不一定就记 `budget_exhausted`**：已经把产物写下来之后才撞闸的 run，终态是 `ok`。
  要数「被预算停下的 run」看 `budget_exhausted_runs` 那一列（口径见手册 §6.5）。
* **撞闸与失败一样是终态，不自动重跑**；要重跑得显式
  `ops/run_joblist.py --retry-status budget_exhausted`。

**别把「一批 run 大半撞闸」读成自己配错了。** 2026-09-13 在一台没有本项目任何遗留物的机器上
做的端到端（3 题双臂 6 个 run，`ops/reports/d2_e2e/`）终态分布是
**3 个 `budget_exhausted` / 1 个 `timeout`（1548 s，撞 1500 秒墙钟闸）/ 1 个 `ok` / 1 个 `violation`**；
其中**四个** run 用满了 100 次调用，只是有一个已经把 artifact 写下来了、于是终态是 `ok`。
这是 **100 次闸下的真实分布**，与 M6 那一批的形状一致，**这六个 run 的分布不调档**
（用户 2026-09-13 裁定）。那张表是**构造验收，不是能力读数**。

这条流水线的四个入口是 [`ops/joblist.py`](ops/joblist.py)（矩阵 yaml → 清单，带状态机）、
[`ops/run_joblist.py`](ops/run_joblist.py)（按清单跑六段）、
[`ops/results_db.py`](ops/results_db.py)（结果库，三张表的单一来源）、
[`ops/mk_tables.py`](ops/mk_tables.py)（出表，混轴默认拒绝）。
矩阵 yaml 的逐字段说明与踩过的坑在 [`ops/HANDOFF.md`](ops/HANDOFF.md) §16。

读表：[`docs/OPERATOR_MANUAL.md`](docs/OPERATOR_MANUAL.md) §6.5–§6.7 逐列给了口径。
最要紧的一条规则是 **空 ≠ 0**：空 = 「这个量在这批 run 上没有可用样本」，
0 = 「量到了，值就是零」。

---

## 3. 仓库布局

仓库根 = `$GENEBENCH_ROOT/repo`。所有路径、端口、冻结线由**单一配置常量模块**
[`genebench_config.py`](genebench_config.py) 提供，**任何模块都不许再硬编码绝对路径** ——
换落点只改那一个文件，或用环境变量 `GENEBENCH_ROOT` 覆盖。

| 顶层 | 面 | 一句话 |
| --- | --- | --- |
| [`genebench_config.py`](genebench_config.py) | 共用 | **唯一**允许出现绝对路径字面量的地方；建目录、收权限、拒通配绑定的工具也在这里 |
| [`genetask/`](genetask) | 出题 | 八阶段模板、措辞表、参数表、双臂定义、打包器 —— **题面的冻结面** |
| [`gateway/`](gateway) | 执行面 | 执行面取数的**唯一入口**：只读 HTTP 服务，13 个端点，只绑 LAN 显式地址 |
| [`runner/`](runner) | 执行面 | 注入、起容器、跑 agent、收产物、记账、出向边车与白名单 |
| [`harnesses/`](harnesses) | 执行面 | P1 / P3 通用 CLI harness，一个目录一个 harness（数据驱动，不改共享代码） |
| [`integrations/`](integrations) | 执行面 | P2 专用系统接入：契约、取数垫片、产物助手、示例与覆盖矩阵 |
| [`snapshots/`](snapshots) | 构建面 | 从数据源建冻结快照的代码（私有派生 + 公开通道），产物落仓库之外 |
| [`reference/`](reference) | **答案面** | 参考解与 gold 的生成逻辑。**对执行面不可见** |
| [`scorer/`](scorer) | **答案面** | 拿参考面的答案给产物打分、出记录与三张表。**对执行面不可见** |
| [`ops/`](ops) | 运维 | 跑批 / 结算 / 出表 / 出集 / 推送 / 报告 / 规格 / 数据卡 / 全部测试 |
| [`docs/`](docs) | 文档 | 面向外部运行者与内部接手人的长文 |
| [`tasks/`](tasks) | — | 历史占位（只有 `.gitkeep`）。真正的题目根在仓库**之外**的答案面目录下 |

仓库**之外**的同级目录（不入 git；大产物只落这里，不落 `/home`）：
`env/`（隔离运行环境）、`snapshots/`（冻结快照）、`reference/`（答案面题根）、
`runs_in/`（跑批清单与 run 目录）、`results/`、`logs/`、`locks/`、`staging/`、`scratch/`、`release/`。
每一条都有对应的 `cfg` 常量，**一条都不许在代码里现拼**。

### 发布件

| 文件 | 是什么 |
| --- | --- |
| [`VERSIONS.md`](VERSIONS.md) | 四条版本轴、「可比」的定义、五条现查命令 |
| [`CHANGELOG.md`](CHANGELOG.md) | 任务集轴与参考轴的逐次重冻记因（**渲染**自冻结模块，勿手改） |
| [`LICENSE`](LICENSE) | 代码许可 —— **Apache-2.0**（全文在内；版权行待填），见 [§6](#6-许可与引用) |
| [`DATA_LICENSE`](DATA_LICENSE) | 数据再分发条件 —— 状态 `pending_license_text` |
| [`CITATION.cff`](CITATION.cff) | 引用信息（`license` 已填 Apache-2.0、`repository-code` 已填真地址；**作者一处待填**）|
| [`RELEASE_MANIFEST.json`](RELEASE_MANIFEST.json) | 发布件逐件 sha256 + 四轴根 + 缺件 + blocker + `releasable` |
| [`ops/data_cards/README.md`](ops/data_cards/README.md) | 八份数据卡的统一入口（每份六字段、私有/公开归属） |
| [`ops/specs/metrics_as_implemented_v1.md`](ops/specs/metrics_as_implemented_v1.md) | 逐指标「规格说什么 / 代码算什么 / 今天判不判」 |
| [`ops/reports/known_limits_v1.md`](ops/reports/known_limits_v1.md) | v1 已知限制逐条判定（已修 / 设计性限制 / v1.1） |

---

## 4. 设计约束

下面六条不是风格偏好，是这套系统**成立的前提**。外部运行者改了其中任何一条，
跑出来的数就不再是 GeneBench 的数了。

**① 答案面永不挂进 agent 容器（容器边界）。** `reference/`（含 oracle 源码）、`scorer/`、
`gold/`、calibration 是答案面；被测 agent 跑在容器里，判据是**那个容器的挂载面**：
挂进容器的宿主路径集合里不得出现答案面，本 run 的 run dir 里也不得出现。
单机形态下的等价表述是「答案面位于 `/task` 之外」。
网关不服务答案面的任何产物，也不提供能间接反推答案的接口。
<!-- H10-2026-09-14 按形态分岔 -->
把 bundle 与 exec 树送上执行面，**路只有「过守门」那一条；具体走哪个入口按形态分岔**：

* **双机形态：只有这两个脚本。** bundle 走 [`ops/push_bundle_to_f02.sh`](ops/push_bundle_to_f02.sh)（带守门），
  exec 树走 [`ops/push_exec_to_f02.sh`](ops/push_exec_to_f02.sh)。
  **这一条对双机没有任何放宽**，也没有 `--force` 之类的绕过开关。
* **单机形态：没有「推」这件事。** bundle 与 exec 树本来就在本机，入口是
  [`runner/placement.py`](runner/placement.py)（`--topology single`）。
  **它不是「绕过守门」** —— 它调的是**同一批门、同一份实现、同样的顺序**：
  [`ops/push_guard.py`](ops/push_guard.py)（形状 + 通行证逐文件核对）→
  `answer_plane_guard --mode container`（挂载面口径，主口径）→ 本地拷贝 →
  落地之后再用树口径扫一遍。少掉的只是「ssh 到对面」那一段。
* **两种形态都不许的是同一件事：手工 `cp` / `rsync` 绕过守门把东西放上执行面。**
  历史上一次手写 `rsync` 父目录就把参考解推上了执行面 —— 那才是这一条要挡的。
  **「我在单机上，所以直接 cp 就行」是错的读法。**

判据的实现是 [`runner/f02/answer_plane_guard.py`](runner/f02/answer_plane_guard.py)
`--mode container`：它读 compose 的挂载面（三种 bind 写法全看）与 run dir，
命中即**拒绝启动**——**不删任何东西**，因为命中的往往是答案面本体，删它等于把基准删了。

<!-- G2-2026-09-12 容器边界 -->
> **v1.0.16 起口径改为容器边界 —— 旧表述与为什么改。**
> v1.0.15 及以前这一条写的是「**答案面不上执行面**」：答案面不许出现在执行面那台机器上，
> 由 `answer_plane_guard --mode tree`（扫 `/data/genebench_runner` 整棵，命中即删）兑现。
> 改的理由：本仓库**公开发布时带全部答案面**（oracle 源码、gold 子集、calibration、评分器），
> 否则外部用户跑完算不出分，这个基准对外只有一半。一旦答案面可以公开，
> 「哪台机器上有它」就不再是判据 —— 公网上人人都能 clone 到它。
> **代价要说清**：题面与参考解进了公网，就有进入训练语料的风险，
> `τ`/`ε` 标定与 canary 的判别力会随时间衰减。这是**设计性限制**，
> 记在 [`ops/reports/known_limits_v1.md`](ops/reports/known_limits_v1.md)，v1.1 以**留出集**处理。
> **树口径没有退役**：它降为第二道，f02 上每小时的兜底 timer 照跑 ——
> 私有通道的 gold 全量仍然不公开，执行面上出现它仍然是事故。

**② 目录权限 0700 是这条隔离的物理保障。** `$GENEBENCH_ROOT` 及其下每一个目录都必须 0700。
很多机器的 umask 是 002，裸 `mkdir` / `os.makedirs` 会静默产出 0775；
`os.makedirs(p, mode=0o700)` 也不够（Python 3.7 起 `mode` 只作用于最后一级）。
一律用 `genebench_config.create_dir()`，每个进程入口调一次 `harden_umask()`。
`$GB` 下**一个 0644 文件就够让网关起不来**（服务的 `ExecStartPre` 就是权限守门），
所以网关起不来的第一嫌疑永远是权限。

**③ 网关不许监听 `0.0.0.0`。** 固定绑一个显式 LAN 地址。
机器若在 tailscale 之类的覆盖网上，**那种流量绕过 ufw** —— 监听 `0.0.0.0`
等于把执行面网关对整个 tailnet 敞开。代码级防线：每一处启动监听前先过
`genebench_config.assert_no_wildcard_bind()`，它对 `0.0.0.0` / `''` / `::` / `*` 直接抛。

**④ 容器只有一个出口。** 任务容器接 `internal: true` 的网，没有任何出口；
出向边车替换占位 key、记 `llm_log`、卡预算，并按白名单只放行模型 API 域名。
白名单与配置注册表**同源**（`runner/c41/egress_proxy.py` 与 `runner/registry.py`），
改一处不改另一处会得到「配置存在但连不出去」。

**⑤ 打网关的批任务必须串行。** 网关是单 worker（取证完整性要求），
所有打网关的真跑、oracle 跑批、控制实验、出集验证都要先拿网关锁
（[`ops/gateway_lock.py`](ops/gateway_lock.py)）。并发跑批 = 网关 OOM。
跑批并发数固定是 1，这不是保守 —— 这套系统里**没有 >1 的合法值**。

**⑥ 冻结线 `2026-07-31`，且题面改动必重冻结、必记因。**
v1 的一切查询、快照、任务上界都不得越过冻结线。
题面（任务集轴）与 gold 算法（参考轴）各有自己的冻结根，改动要重冻并写进
[`CHANGELOG.md`](CHANGELOG.md)；**题面指纹变了是致命项，必须人工签字。**
在途的 bundle 会因此作废 —— 通行证过期的报错与处置在手册 §7.1。

<!-- H10b-2026-09-14 用户裁定 ④ 的那条纪律 -->
> **一条贯穿上面六条的纪律：判据不能是「在现有环境上跑通」，
> 必须是「在一棵全新的树上从零走一遍」。**
> 双机形态今天能跑，靠的往往不是交付链路，而是某次手工操作留下的东西 ——
> 执行面上那份 `vendor/h11` 是一次跑容器测试时手工复制的；exec 树根的 `0700`
> 是手工 `mkdir` 出来的（`mkdir -m 700 -p` 的 `-m` 只作用在最后一段，中间那层吃 umask）；
> provider 的父目录恰好存在，使得一处写死的路径「看起来对」。
> 这三件**都没有任何一条文档化步骤会产生它们**，而只要那棵既有的树还在，
> 它们就**永远不显形** —— 门全绿，却一条都没拦住。
>
> **同一条纪律的另一面**：单机形态那道门**替双机挖出了故障**。
> 2026-09-14 在单机路径上量到四条，其中一条（守门模块级 import 一个不在同步白名单里的模块）
> 正等着在**下一次**同步 exec 树时打断**双机**生产 —— 它与「单机」本身没有关系，
> 只是单机那条路先踩到了它。
>
> 所以这两件事是同一条：**新铺一棵执行面目录跑一次冒烟**，与**跑一次单机形态的门**。
> 两件都做，而且判据都不许退回「在既有那棵树上跑通」。

---

## 5. 发布状态（如实）

**今天 `releasable = true`，未闭合的零条。** 权威状态在
[`RELEASE_MANIFEST.json`](RELEASE_MANIFEST.json)（`releasable` 字段是**推导**出来的：
任何缺件、任何未闭合的 blocker、任何一份未定的许可 → false；手改会被测试当场抓到）。
现查：

```sh
$PY ops/mk_release_manifest.py --check      # 0 一致 / 1 判据变了（停下）/ 3 生成件又跑了一次（重生成即可）
```

**清单里共五条，现在五条全闭。** 下面逐条保留，是为了让读过旧版的人看得见它们去哪了
（第 3、4 条 2026-09-10 闭合，第 2、5 条 2026-09-11，第 1 条 2026-09-11 用户裁定 ⑨）。
**`releasable=true` 不等于「外部用户能用」** —— 挡使用的事另有一份逐条判定，见本节末尾。

1. ~~**baostock 的书面再分发许可原文没有入库**（`DATA_LICENSE` 状态 `pending_license_text`，
   公开数据包只落在暂存目录、`publishable=false`）。~~
   **已闭合（2026-09-11 用户裁定 ⑨）**：再分发许可**已取得** —— 研究用途、允许再分发
   派生日线数据、署名 baostock；[`DATA_LICENSE`](DATA_LICENSE) 状态翻成 **`granted`**。
   **「授权有了」与「原文可查」是两件事**：许可方出具的书面正文**仍未到手**，
   `DATA_LICENSE` 的「## 2. 许可原文」一节是一处**显式占位**（写着「正式文本待替换」），
   由仓库所有者原样替换。别把占位读成「已经入库」。
2. ~~**这个仓库没有可 clone 的地址**（`git remote` 是空的）。~~
   **已闭合（2026-09-11 用户裁定 ㉑）**：本体 <https://github.com/Decilix-Intelligence/GeneBench.git>，协议工件单独一棵
   <https://github.com/Decilix-Intelligence/GeneQuant.git>。本文与手册里的 `git clone` 步骤已换成真地址。
   **一件要说清楚的事**：地址已定、树已备好，**推送由仓库所有者执行** ——
   所以你 clone 到的是哪一次推送的内容，以那边的 `git log` 为准；
   本仓库**没有**配置 remote（`git remote -v` 仍是空的，那是有意的：
   一棵内网工作树不该指向外网）。推送前后的核对清单在
   [`ops/reports/push_instructions.md`](ops/reports/push_instructions.md)。
3. ~~**`factor_library/compiled/{qlib_native,qlib_panel,blocked}.jsonl` 三个文件不在仓库里。**~~
   **已闭合（2026-09-10，卡 W2 提交 `8428252` 从湖里收进仓库）** —— 声明的 6 个冻结件现在
   **全部到位**（`RELEASE_MANIFEST.json` 的 `frozen_artifacts_missing`: `satisfied=true`）。
   它们是 gold 的**定义面**（「τ 标定于这一对实现」），少了就复现不出 τ。
4. ~~**代码许可未定**~~ **已闭合（2026-09-10 用户裁定，卡 B 落地）**：[`LICENSE`](LICENSE)
   已换成 **Apache-2.0** 全文，首行 `SPDX-License-Identifier: Apache-2.0`。见 [§6](#6-许可与引用)。
   **仍待填的是版权行**（Apache-2.0 附录要求的「Copyright [年] [版权人]」）——
   那不挡使用，挡的是署名完整。
5. ~~**公开通道一个 run 都没有**~~ **已闭合（2026-09-11 卡 X1 起步，2026-09-12 N-611 跑齐 18/18；`RELEASE_MANIFEST.json` 的 `public_channel_zero_runs`: `satisfied=true`）**。
   X1 那一轮的 8 个 run 跑在**私有 provider** 上（`--provider-root` 被静默忽略），已全部重跑并作废 ——
   证据保留在 [`ops/reports/m6_public/g1_public_provider_rerun.md`](ops/reports/m6_public/g1_public_provider_rerun.md)。下面这段是闭合前的原文，留着让读过旧版的人看得见它去哪了：
   （原文）公开通道一个 run 都没有（`m6_public` 的 18 行清单全是 `pending`，f02 上连
   `/data/genebench_runner/m6_public` 目录都不存在）。后果：
   [`ops/reports/m6_public/v1_0_readiness_public.md`](ops/reports/m6_public/v1_0_readiness_public.md)
   的 §4 / §4b 渲染不出逐 run 证据 ——「外部用户按手册跑得通」这一条在**公开通道**上
   只有构造层的背书，没有真跑的背书。**这一条不挡你自己跑**（跑起来就有 run 了），
   挡的是我们这边的发布验收。

五条各自的「怎样才算闭合」逐条写在 `RELEASE_MANIFEST.json` 的 `blockers` 里（那里才是权威：本节的条数与它逐条对得上是一条测试），
形态层面的分析在 [`ops/reports/public/release_forms.md`](ops/reports/public/release_forms.md)。

**这几条挡的是「发布」，不挡「使用」。** 挡使用的另有一份逐条判定：
[`ops/reports/known_limits_v1.md`](ops/reports/known_limits_v1.md) ——
每条都标着「已修 / 设计性限制 / v1.1」，并且顶部单列了三条**待裁定**
（默认预算档、适配赛道题源、S7 的回合数）。
就绪度的另一半（状态是什么，而不是拿它怎么办）在
[`ops/reports/v1_0_readiness.md`](ops/reports/v1_0_readiness.md)。

<!-- C2-2026-09-13 -->
**一件外部读者一定会撞上、但不是「发布件损坏」的事：**

1. **`ops/freeze_v10.py --check-all` 的公开任务集轴，在只落位了那两个附件的机器上核不绿。**
   现算 `c5639e55…`、清单记 `3e5ab441…`，**差异全部落在 `channel_fixtures/`**。
   私有任务集轴与参考面轴**一致**，附件的逐件 sha256 也全部通过 —— **不是下载损坏**。
   原因是公开题集树按红线 6 落在 `$GENEBENCH_ROOT` 之下、在仓库之外，而公开树是 `git archive HEAD` 打的，
   射程里根本没有它。**缺的这一堆已经补成第三个附件** `genebench_public_runtime_v1.tar.gz`
   （整棵公开题集树 + `calibration.json` + `epsilon/`），落位之后三条轴实测全绿；
   **2026-09-13 它已经传上 Release `v1.0.16`、匿名可下**（`ops/release/attachments.json` 里它的
   `download_url` 已回填，逐字地址与校验命令见 [§2.1a](#21a-数据面-a拿现成的冻结包)）。
   **三件一起落位之后这一条就核绿了**；只落位前两件时仍然核不绿 —— 那不是下载损坏，是少落位了一件。
   `ops/selfcheck_public.py` 对「登记了但还没上传」的条目报「登记在案」而不是红。
   **附件到底有几件、各自的字节数 / sha256 / 下载地址，以
   [`ops/release/attachments.json`](ops/release/attachments.json) 为准**
   —— [§2.1a](#21a-数据面-a拿现成的冻结包) 的表现在列的就是**全部三件**（三件都已挂上）。
   **不要用 `--write*` 去把它重冻绿** —— 那是把判据改成现状。

<!-- P2-2026-09-13 -->
**曾经还有一件，现在没有了**：`ops/mk_release_manifest.py --check` 在干净 clone 上退 1。
根因是清单里有两处内容取决于**跑它的机器**（「这台有没有 remote」「这台有没有发布方那批
`m6_public` 的 run 清单」），而 `blockers` 在 `FATAL_KEYS` 里 —— 于是本节上面那句
「退 1 才要停下」在每一个外部 clone 上都会被触发。2026-09-13 按用户裁定 ② 修的是**根因**，
不是写一句「忽略它」：清单现在与跑它的机器无关，判据是「同一棵树在有 / 无 remote
两种状态下生成的清单逐字节相同」。（2026-09-13 的 macOS 外部验收同一次还核过：
`RELEASE_MANIFEST.json` 声明的 **53/53** 个仓库文件 sha256 全部一致。）

**注意 `RELEASE_MANIFEST.json` 会随生成件漂移，那是正常的。**
发布件里有 9 件是由代码渲染的（三份报告 + 六份数据卡），重跑一次生成器就换 sha。
`--check` 退出 **3** 直接重新生成即可；退出 **1** 才要停下 —— 那意味着「能不能发」这个答案变了。

**另有一件 `releasable` 管不着、外部读者一定会撞上的事：Release 的附件 —— 三件都已经挂上去了。**
包打定了、六项上传前扫描全零、校验和是终值（见
[`ops/reports/release_scan_publish.md`](ops/reports/release_scan_publish.md)），
2026-09-13 传上 Release `v1.0.16` 并从下载地址取回重算 sha256 核过，两件都对得上。
它本来就**不是** `RELEASE_MANIFEST.json` 里的第六条 blocker —— 清单判的是「这份东西够不够格发」，
而这件事是「发的动作」。上传与回核逐步记在
[`ops/reports/push_result.md`](ops/reports/push_result.md) §7，
[§2.1a](#21a-数据面-a拿现成的冻结包) 的 (a) 现在走得通。

---

## 6. 许可与引用

**代码许可：[Apache-2.0](LICENSE)**（用户裁定 2026-09-10）。[`LICENSE`](LICENSE) 里是
apache.org 的**许可原文逐字未改**（首行 `SPDX-License-Identifier: Apache-2.0`），
外加一段记因：真正被权衡的只有「要不要明文专利授权」这一条，代价是与 GPL-2.0 不兼容、
改过的文件要按 §4(b) 标注。**你可以使用、复制、修改、再分发本仓库的代码**，
条件按该许可 §4（保留版权与许可声明、标注改动、`NOTICE` 若有则随附）。

**还差一个版权行。** Apache-2.0 的附录要求写明「Copyright [年] [版权人]」，
本仓库的版权人（个人还是机构）是所有者的决定，**没有代填**——
所以源文件里今天**没有**逐文件的许可头，等版权行定了一次加完（[`LICENSE`](LICENSE) §A）。
这不影响授权是否成立：`RELEASE_MANIFEST.json` 的 `code_license_undecided` 判的是首行 SPDX，
已经 `satisfied: true`。

**数据许可另算。** [`DATA_LICENSE`](DATA_LICENSE) 管的是快照与公开包能不能再分发，
与代码许可是两件事；它现在是 `pending_license_text`（见 [§5](#5-发布状态如实) 第 1 条），
其中 §2.2 列了「许可原文里必须能回答的四个问题」——
收到原文时按那四条核，缺哪条写明缺哪条，**不要按最宽的解释填空**。

**引用**：[`CITATION.cff`](CITATION.cff)。`license` 已经填成 `Apache-2.0`，
`repository-code` 已经填成 <https://github.com/Decilix-Intelligence/GeneBench.git>（裁定 ㉑）；
**作者一处仍是占位符**，**带占位符的 CITATION 不要随发布包发出去**。

协议工件（三条协议的规格/契约、validator、适配模块、投放说明）另有一棵可独立发布的树
[`genequant/`](genequant/)，仓库 <https://github.com/Decilix-Intelligence/GeneQuant.git>，同样 Apache-2.0、自带 `CITATION.cff`。
本体在 `RELEASE_MANIFEST.json` 的 `genequant` 段里**以 sha256 钉住它用的那一版协议**。

---

## 7. 内部工程说明

原 README 里面向施工方的内容（pip 镜像、落点搬迁、数据湖已知陷阱、建目录的正确姿势、
进度纪律）搬到了 [`docs/INTERNAL_NOTES.md`](docs/INTERNAL_NOTES.md)。
逐阶段「谁做了什么、为什么这么定、踩过哪些坑」在 [`ops/HANDOFF.md`](ops/HANDOFF.md)；
需要特权的待办在 [`ops/tickets.md`](ops/tickets.md)，逐卡验收记录在
[`ops/progress.md`](ops/progress.md)。

本文自己的判据是 [`ops/test_readme.py`](ops/test_readme.py)：
README 里提到的每个仓库路径真的存在、每个指向的文档真的在、
[§5](#5-发布状态如实) 说的发布状态与 `RELEASE_MANIFEST.json` 的
`releasable` / `blockers` / `missing` 逐条一致。
