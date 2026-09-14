# 内部演练：只凭手册接一个没接过的系统（卡 2.7）

**问题**：`integrations/README.md` 与 `P2_CONTRACT.md` 是发给外部被测方的东西。
它们是不是真的够用？——**这件事只能用一次演练来回答，不能靠通读。**

**做法**：挑一个五个已接系统之外的开源系统，在一个干净目录里
**只看 `integrations/README.md` + `P2_CONTRACT.md` + `genebench_client/README.md`**
（不看已落地的五个接入目录 —— 那是作弊），走到「一道真题真跑 + 结算」为止。
每一处做不下去的地方记一条 finding，然后回去修手册，再按修后的手册重走受影响的步骤。

**选的系统**：[StockAgent](https://github.com/MingyuJ666/Stockagent)（arXiv:2407.18957，ACM TIST）
@ `e2a9c052`。选它的理由：可 clone、有真 LLM 循环、体量最小（9 个 .py，约 2,300 行），
而且它属于**前五个都没有的第三类被测方** —— 它原生**一次外部取数都没有**
（股票是虚构的，财报写死在 prompt 里）。候选里 FinCon 的仓库只有一个 README、没有代码，
QuantAgent 的两个候选组织下都是 404，所以实际可选的只有它。

接入目录留在 [`integrations/stockagent/`](../../integrations/stockagent/) 作为第六个示例。

---

## 1. findings 表（修前 → 修后）

「来源」列里 **2.7** = 本次演练现场撞到的；**2.6-x** = 前一轮五个接入代理各自记在
`ops/tickets_inbox/2.6-*.md` 里、本卡合并进来的。
**同一条被多个代理独立撞到，说明它不是某个人的疏忽，是手册的缺口。**

| # | 症状（照手册做会看到什么） | 手册原来哪里错 | 改成了什么 | 来源 | 现场证据 |
|---|---|---|---|---|---|
| **F-01** | 构建停在 `BackendUnavailable: Cannot import 'setuptools.build_meta'`；或镜像建成了、两臂十几秒退出、`no_artifact`，日志里 `can't open file '/opt/<id>/run.py': [Errno 13] Permission denied` | §1② 的 Dockerfile 三行骨架**少两行**：基座不带 `setuptools`；仓库文件是 0600 而容器非 root | 骨架补 `RUN pip install "setuptools>=61" wheel` 与 `RUN chmod -R a+rX`，并写明这两条的症状与「和 §3.7 长得一样但都不是」 | 2.6-tradingagents / 2.6-finrobot / 2.6-alphaagent / **2.7** | `build1.log`（f02，逐字复现） |
| **F-02** | 没有症状 —— 直到有人看 `docker images` 才发现你的镜像名和别人不是一套 | §1② 的两个例子 `gb-<id>:r1` / `<id>-deepseek-v3` 在仓库里**只有 `example_minimal` 自己在用** | 加一张对照表：镜像实际是 `gb-<id>-u:r1`（11/13），`config_id` 实际是 `cfg-<id>-deepseek`（5/7 个接入）；并写明 `launch.json` 的 `image` 与 `docker build -t` **没有守门**，对不上的表现是「构建成功了，跑的还是旧镜像」 | 2.6-alphaagent / **2.7** | `grep -h '"image"' integrations/*/launch.json harnesses/*/launch.json` |
| **F-03** | open 臂**零产物、零模型调用**、当场 `SystemExit`；strict 臂一切正常 | §1④ 把「固定槽」讲成了固定格式，读者会以为槽就是 `key=value`；§2 那个 30 行示例的 `slot()` 只认 `key=value`，而它只在 S1 strict 上走查过 | §1④ 新增「题面有两种写法，你的解析器必须两种都认」：两臂对照表 + 两条照抄做法 + **三处会把值偷走且产物上完全看不出来的地方**；`P2_CONTRACT.md` §4.6 补上渲染表的 `(文件:行)` | 2.6-rdagent_q（丢了一个臂，用掉那次重试）/ **2.7** | `genetask/render.py:59-61`；本卡 `ops/test_integration_stockagent.py` 里三条具名判据 |
| **F-04** | `COPY failed: file not found`；或者改完接线层直接去真跑，跑完发现 bundle 的通行证与镜像对不上 | §1⑥ 的 `scp` 只送两样，**没说你的上游源码放构建上下文哪里**；四步被写成一条直线，没说「镜像一动就回到第一步」 | 补「你的系统本体放构建上下文的哪里」（放上下文根 + 构建期 `sha256sum -c`），并画出那个回环 | 2.6-finmem / 2.6-finrobot / 2.6-rdagent_q / **2.7** | 本卡 `integrations/stockagent/Dockerfile` ④ |
| **F-05** | 没有症状 —— 但账本上「我们接不进去」和「它接进去了但答错了」会记成同一个值 | §1⑦ 的三个 `--outcome` 值覆盖不到「接入成功、真跑跑通、被测系统 `invalid`」 | 写明 `--outcome` 说的是**接入这件事**成没成；「它考得怎么样」在 `COVERAGE.md` 的格值里。加第四个值的提议登记票据 | 2.6-alphaagent / 2.6-rdagent_q | —（口径澄清） |
| **F-06** | `ops/test_integrations_readme.py::test_coverage_rows_only_use_defined_values` 当场红；或两个人同时改 COVERAGE 丢一行 | §1⑧ 只写 `$EDITOR`，没说它是**共享文件**、要在 flock 里读-改-提交，也没说阶段格必须恰好八个 | 补 flock 规则与「八个格 + 第 11 列是备注」 | 2.6-finrobot / 2.6-rdagent_q | — |
| **F-07** | 接入者按「找出全部取数路径并替换」去做，但对某些系统这件事**根本不适用** | §1③ 只有一种被测方模型（运行期取数） | §1③ 开头加三类分类表（运行期取数 / 离线数据集 / **无数据**），每类写明「取数是否全部经过数据面」靠什么保证 | 2.6-finmem（前两类）/ **2.7**（第三类是本次这个系统） | 本报告 §3 |
| **F-08** | **生产网关连不上**，`healthz` 无响应，`systemctl` 显示 `activating (start-pre)`、`restart counter is at 25` | §3.10 只说「留下 0644/0775 会让每一个跑全量的代理看到两条红」——**没说它会把网关整个停掉** | §3.10 补：`genebench-gateway.service` 的 `ExecStartPre` 就是 `guard_modes.py`，全树一个 0664 就让它起不来；给出一条诊断命令 | **2.7（新）** | 2026-09-07 15:12–15:31，网关停 ~35 分钟；三个肇事文件之一是 `ops/push_exec_to_f02.sh` 自己留下的 `scratch/exec_push/ops/__init__.py`（0664） |
| **F-09** | 两臂各 0.1 秒 `ERROR`，**run dir 根本没建**，没有容器日志 | §3 没有「注入期就被拦」这一条；它与 §3.7「两臂 3 秒退出」长得像但排查方向完全不同 | 新增 §3.11，写明分辨法（run dir 在不在）与一条修法命令 | 2.6-finmem | — |
| **F-10** | 构建期 `FileNotFoundError: '/task/log/test.txt'`；或跑完 `run.json` 的 `unexpected` 里多出一堆东西 | §1④ 说「`HOME` 指到 `/tmp`」，但**这一类根本不看 `HOME`** —— 它们在 import 期按相对 CWD 开文件 | 新增 §3.12：`import` 上游**之前** `chdir`；并点名 `pin.json` 的 `runnable_check` 也在构建期跑、那时 `/task` 还不存在 | 2.6-finmem / **2.7** | `build2.log`（f02） |
| **F-11** | 产物是**一张全 `null` 的面板**，结构合规、覆盖统计自洽、**一眼看不出哪里错了** | 三份手册都没说：题面 `inputs[]` 发下来的因子面板用的是 `20260105` + `SH600000`，而网关一路用 `2026-01-05` + `600000.SH`。两边 join 得到空表，**join 本身不报错** | `genebench_client/README.md` §4 新增「写法归一：题面夹具与网关**不同源**」，给出 `codes.iso_date` / `codes.to_lake` 与那句「别自己写一份」 | **2.7（新）** | `smoke4.log`（8 格全 null）→ `smoke5.log`（归一后 8 格全有值） |
| **F-12** | `RunError: run dir 已存在（F9）` | §1⑥ 的真跑命令写死 `--seq 1`，没说重跑要换 | 补一段：`--seq` 是这次运行的序号，重跑要换掉 | 2.6-tradingagents | — |
| **F-13** | 没有症状 —— 而这正是问题：系统绕过数据面的**唯一现场证据**被扔掉了 | 手册没有「真跑之后读一遍被出向白名单挡下的请求」这一步 | §3 末尾新增「真跑之后必须做的一件事」：每一条被挡下的 CONNECT 都当成一条**没替换掉的取数路径**登记进「已知偏离」 | 2.6-tradingagents（三条取数路径里两条是被真跑与白名单抓出来的） | — |
| **F-14** | 表上显示你「参数写得很烂」（`malformed_requests` 几十条） | 手册没说 `NoData` 留痕（打白名单外路径拿 404）会被结算计进 `malformed_requests` | §3.4 补一条：知道就行、不用改代码；把 `/nodata/{kind}` 做成正式端点的提议登记票据 | 2.6-tradingagents / 2.2 | 2.6 实测 strict 60 / open 45 条全是留痕 |

**没修、只登记票据的**（在 `ops/tickets_inbox/2.7.md`）：
`example_minimal/` 的 `Dockerfile` 与 `run.py::slot()`（不是本卡路径）、
`--outcome` 加第四个值、`/nodata/{kind}` 做成正式端点、
`push_exec_to_f02.sh` 收尾补一句 `chmod -R go-rwx`、
`.dockerignore` 与 `--params` 两条小澄清。

---

## 2. 手册够不够用：一句话的结论

**够用，但有一层「只有真做过才知道」的东西手册原来没写。**

把 14 条按性质分一下：

| 性质 | 条数 | 说明 |
| --- | --- | --- |
| **手册写了、但少一行**（照做会当场炸） | 4（F-01×2、F-04、F-12） | 最便宜的一类，也是被最多人独立撞到的一类 |
| **手册写了、但读者会理解反** | 2（F-03、F-05） | 最贵的一类 —— F-03 让一个接入丢掉了一整个臂**并用掉了那次重试** |
| **手册完全没写的失败模式** | 4（F-08、F-09、F-10、F-11） | 其中三条的共同点是**症状与原因隔得很远**（网关连不上 / 全 null 的产物 / 构建期报一个 `/task` 路径） |
| **纪律层面的缺口** | 4（F-06、F-07、F-13、F-14） | 不写也能跑通，但不写就会得到**看起来对的错结论** |

值得单独说的是 **F-11 与 F-08**：它们都是「没有报错」的那一类。
F-11 交出的产物结构合规、`coverage` 自洽、过 validator；
F-08 的表现是别人的网关连不上，而肇事者自己什么都看不到。
**手册最缺的不是步骤，是这一类「不会红的错」的清单。**

---

## 3. 顺带得到的一个范式层结论：第三类被测方

前五个接入分两类。这一个是第三类：

| 类型 | 例子 | 运行期取数 | 「取数是否全部经过数据面」 | 接入的主要工作量 |
| --- | --- | --- | --- | --- |
| 运行期取数 | 多智能体投研那一类 | 有，随时 | **靠不住**：三条路里接入者只找到一条 | 找全替换点（找不全） |
| 离线数据集 | 启动读一个 pkl 那一类 | 无（装数据时一次） | 结构保证 | 换掉那一次 |
| **无数据** | **StockAgent** | **不存在** | 结构保证 | **把它虚构的那部分换成真的** |

第三类的接入工作量不在「堵路」，而在「喂什么、喂到哪一天为止」——
**而「喂到哪一天为止」这条线网关是看不见的**：网关只挡 `as_of` 之后的东西，
「窗口之内、信号日之后」那一段必须由接入层自己守。
本接入把这条线写成了一个具名函数（`Market.brief` 只取 `d` 及之前），
但**没有任何判据能从外面证明接入者守了它** —— 这是范式层的一个空洞，已登记票据。

---

## 4. 演练的真跑（修完手册之后按修后的手册重走的那一遍）

顺序上，本卡是**先按原手册走到构建失败与解析踩坑，修完手册再重走受影响的步骤**
（重命名镜像与 `config_id`、重建、重出集、重推、真跑），所以下面这一次是
「按修后的手册」跑出来的。

* 题：`s5-eco-01`（S5，`kind=free`，csi300，窗口 2026-01-05..2026-07-31，`as_of=2026-07-31`）
* 配置：`cfg-stockagent-deepseek`（deepseek-chat，经边车），镜像
  `gb-stockagent-u:r1` digest `sha256:ace5eb272f299d41995db8a1795c0cdad876be55054cd81261f86b57d4560a18`
* 命令逐字在 [`integrations/stockagent/README.md`](../../integrations/stockagent/README.md) §7

| | strict | open |
| --- | --- | --- |
| `status` / `exit_code` | RAN / 0 | RAN / 0 |
| 结算 | **valid**，`gate=[]` | **valid**，`gate=[]` |
| SR / pass@1 / 越权率 | 1.0 / 0.0 / **0.0** | 1.0 / 0.0 / **0.0** |
| 模型调用（`decision==allow`） | **43** | **44** |
| 产出格子 | 8（2 只 × 4 个交易日） | 8 |
| `coverage` | `n_valued=8, n_null=0, n_flat=0` | 同 |
| `run.json` 的 `unexpected` | `[]` | `[]` |
| 用时 | 62.5 s（wall 103.1 s） | 56.9 s（wall 92.1 s） |

`pass@1=0.0` 是自由题的口径符合度，**不要读成「信号有多好」**。

**两臂的声明逐字段相同**（六个口径都从题面的「接口值」那一段取，两臂的那一段本来就一样）——
这正是 F-03 那条修法要保证的东西：两臂表达形式不同，解析结果必须相同。
两臂的信号值**不同**（同一份代码、同一个镜像、同一个种子，模型的自由发挥不同），
这是应该的。

### 4.1 F-13 那条新加的自检，在本接入上跑出来是干净的

按修后手册 §3 末尾那条，真跑之后读一遍被出向白名单挡下的请求：

```
run_dir/log/egress.jsonl  →  {'listen': 3, 'ready': 1, 'http_identity': 8}
                             被拒的 CONNECT：0
$GB/logs/gateway_access.jsonl（本次 config_id 的全部 16 条）：
  /universe 200 allow ×2   /calendar 200 allow ×2   /bars 200 allow ×2
  /tradability 200 allow ×8
  /nodata/fundamentals 404 deny ×2        ← 这两条是**我们故意打的留痕**
```

**这个系统没有试图连过任何第三方**。对比卡 2.6 那个运行期取数的接入
（它的 stderr 里逐条是 `Tunnel connection failed: 403 Forbidden`），
这就是 §3 那张三类分类表里「结构保证」那一格的实测样子 ——
不是接入者替它堵住的，是它本来就不出网。

### 4.2 一次返工与一次事故

* **返工 1 次**：从本机重推 `config.yaml` 时把 `enabled` 覆盖回了 `false`，
  真跑在 `REG.by_id` 那一步就退了（**零模型调用**，没浪费预算）。
  这是我自己的文件管理疏忽，不是手册的问题。
* **事故 1 次**：生产网关 15:12–15:31 停了约 35 分钟（见 F-08）。
  三个肇事文件里有一个是我跑 `ops/push_exec_to_f02.sh` 留下的。
  **它不是「我忘了 umask」** —— 是那个脚本自己的暂存产物；票据里建议在脚本收尾补一句。
* 另有一次**排队** 47 分钟（`gateway_lock` 排在阶段一的 `o1_inner_full --tier full` 后面），
  按手册的口径 `pause` / `resume` 剔出了净工时。

---

## 5. 接入成本

见 [`integrations/COST.md`](../../integrations/COST.md) 的 `stockagent` 一行。
**两个数要连着读**：净工时与返工次数 —— 单一分钟数会让「一次做对」和
「返工三次凑出同样分钟数」看起来一模一样。

要注意这一行**低估了**真实成本的两处：
① f02 上的镜像构建（本卡建了 6 次）发生在执行面，从 f01 侧的计时看不见（卡 2.5 已登记）；
② 本卡是「演练 + 修手册」两件事，工时里含了写 15 条 findings 与改三份文档的时间，
**不是一个纯接入的成本**。想看纯接入成本，看卡 2.6 那五行。

---

## 6. 证据

| 是什么 | 在哪 |
| --- | --- |
| 接入目录（第六个示例） | `integrations/stockagent/` |
| 判据（39 条 + 1 skip） | `ops/test_integration_stockagent.py` |
| 结算产物 | `ops/reports/i_rehearsal/`（`summary.md` / `records.json` / `table_a.csv` / `scores/`） |
| 出集 | `$GB/staging/i_rehearsal_s5-eco-01/` |
| 构建失败的两次现场 | f02 `/data/genebench_runner/build/stockagent/build1.log`（setuptools）、`build2.log`（`/task/log/test.txt`） |
| 全 null 那一版与修好那一版 | f02 同目录 `smoke4.log` → `smoke5.log` |
| 上游 HEAD 跑不起来的现场 | f02 同目录 `smoke2.log`（`KeyError: 'stock_c'`） |
| 真跑 | f02 `/data/genebench_runner/i_rehearsal/runs/runs/s5-eco-01.{strict,open}.cfg-stockagent-deepseek.r02/` |
| 演练目录与补丁脚本 | `$GB/scratch/rehearsal_2_7/`（`fix_guides_2_7{,b,c}.py`、`real2.log`、`full.log`） |
| 票据 | `ops/tickets_inbox/2.7.md` |
