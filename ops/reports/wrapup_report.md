# GeneBench 收尾报告（2026-09-10 收尾卡）

> 口径：本报告只写**今天能核到的现值**。数字与结论都给证据路径；
> 「未达成」不改写成「部分达成」，「卡在裁定」不改写成「快好了」。
>
> 三个数请照抄：**任务集 v1.0.14**（root `947bf817ae3df348…`）/ **参考轴 r1.0.21**（root `399fffde62108b52…`）；
> 出集 **34 题 / 挂起 6 题**；**40 模板（= 出集参数表的 40 行）/ 130 实例**。
> 逐条票据 `ops/tickets.md`「2026-09-10 收尾卡」一节（**N-475…N-570**，96 条）；交接 `ops/HANDOFF.md` §18 + §18.2。

---

## 〇、现值更新（2026-09-12，最终卡红队修复之后）

> **这一段是后写的，下面的正文一个字没动。** 正文是 2026-09-10 那天的判断，
> 后来有四件事把它的三个数改掉了。**要引用现值就引用这一段**；
> 正文里的「未达成（0/18）」「`releasable=false`」「v1.0.14 / r1.0.21」都是当天的值，不是现值。

| | 2026-09-10 正文写的 | 现值（2026-09-12，现算） |
|---|---|---|
| 任务集轴 | v1.0.14 / `947bf817ae3df348…` | **1.0.16** / `d9ebd5412ac4cc7e…` |
| 公开任务集轴（裁定 ①） | 那天还没有这条轴 | **p1.0.0** / `3e5ab441a991c411…` |
| 参考轴 | r1.0.21 / `399fffde62108b52…` | **r1.0.23** / `dddabe440163b36e…` |
| 6-⑤ 公开通道整批 | **未达成（0/18）** | **18/18 跑成**（N-611：18/18 在真公开 provider 上；前 8 个是受污染重跑） |
| 发布清单 | `releasable=false`，五条 blocker 里未闭合 1 条 | `releasable=true`，未闭合 **0 条** |

三件事的出处：
* **重冻两条轴** —— `ops/manifests/*.json`，逐条记因见 `CHANGELOG.md`；三条根的自检是
  `$PY ops/freeze_v10.py --check-all`（2026-09-12 新加：从前那条命令只核私有任务集轴）。
* **N-611** —— `ops/run_f02_a1.py` 的 `--provider-root` 在真跑路径上被静默忽略，
  受污染的 8 个与被夹具身份闸挡住的 10 个一起重跑，证据 `ops/reports/m6_public/g1_public_provider_rerun.md`。
* **裁定 ⑨** —— baostock 再分发许可**已取得**（研究用途、允许再分发派生日线数据、署名 baostock），
  `DATA_LICENSE` 状态 `granted`，`data_license_text` 随之闭合。
  **书面正文仍未到手**：`DATA_LICENSE §2.1` 是一处显式占位，`ops/terms/baostock/permission/` 仍然是空的。
  「授权有了」与「原文可查」是两件事，后者没有 —— 这一点不因 blocker 闭合而消失。

还有一件**不在上表里、但读这份报告的人该知道**：2026-09-12 之前，公开通道的结算
读的是**私有通道的**标定（τ/ε）、网关日志与题集根（三处默认值都写死了私有路径）。
已修；`m6_public` 重结算后主表与 Table A **逐字节相同**（判据一个都没翻），
变的是 3 条记录的 4 个诊断值（s5 两臂的 `tau`、s4/s7 的 `max_band_ratio`）。

---

## 一、状态：六阶段 + 本收尾卡；f01 全量数字；真 API 用量

### 1.1 六阶段（2026-09-08 收口时的 26 条总完成定义，按今天的现值重判）

| # | 阶段 / 完成定义 | 2026-09-08 判 | **今天判** | 变了什么 |
|---|---|---|---|---|
| 1-①…1-④ | 一：O1 矩阵 34/34、三控全绿、验证验证器五部分过、τ/ε 标定齐 | 达成 ×4 | **达成 ×4** | 不变。O1 本轮又在**实例层**跑了一遍（见 1.2 ④） |
| 2-①…2-③ | 二：三范式五件齐 / 六个开源系统各接一个 / 手册够用 | 达成 ×3 | **达成 ×3** | 不变 |
| 3-① | 三：六个 harness + 接入手册 | 达成 | **达成** | 不变 |
| 3-② | 三：五个 harness 真跑体检 | **部分（3 通 / 2 卡上游）** | **部分（不变）** | `gemini-cli` 4 条调用上游全 404、`grok-cli` 工具参数恒 `{}`，根因钉死、`enabled:false` |
| 3-③ | 三：`llm_log` usage 完整度 | 达成 | **达成** | 不变 |
| 4-①…4-③ | 四：臂机制数据驱动 / 题面逐字节不变 / `doc` 臂真跑 | 达成 ×3 | **达成 ×3** | 不变 |
| 4-④ | 四：`hint` 臂一次真运行验通 | **未达成（我们没做到）** | **未达成（不变）** | 修法已知（`--timeout` 1500 → 2400），「1 次 + 1 次重试」额度已用尽。N-330 |
| 4-⑤ | 四：`adapt` 臂一次真运行验通 | **未达成（等用户签字）** | **✅ 达成** | N-348 裁定落地，适配模块 `status` draft→released（N-535），**30 个 adapt run 真跑**、749 次真 API |
| 4-⑥ | 四：预算按阶段分档 | 达成 | **达成** | 默认档抬到 6M（N-388/N-481），档位判据不变 |
| 4-⑦ | 四：适配赛道 30 例各有 oracle | 达成 | **达成** | 题源按 N-348 **重建过一次**（出集规定题的 oracle 产物） |
| 4-⑧ | 四：适配赛道 30 例各有一次真运行 | **未达成（0/30）** | **✅ 达成（30/30）** | N-532 |
| 5-① | 五：已知限制表只剩设计性与 v1.1 项 | 达成 | **达成** | 三条「挡着但卡在用户签字」里 N-388 / N-130 本轮关掉、N-348 收口成设计性限制（N-548） |
| 5-② | 五：从清单跑 4 题双臂到出表 | 达成 | **达成** | 不变 |
| 6-① 6-② 6-⑥ | 六：README 入口 / 运行者手册 / 红队一轮 | 达成 ×3 | **达成 ×3** | 手册本轮三处更正（§1.1 / §1.3 / §1.4）；**又跑了一轮红队**（12 条，见 2.6） |
| 6-③ | 六：发布件齐 | **文件齐 / `releasable=false`（四条 blocker）** | **文件齐 / `releasable=false`（五条 blocker，一闭一新增）** | `frozen_artifacts_missing` **已闭**（N-490）；新立 `public_channel_zero_runs`（N-546）。见 1.4 |
| 6-④ | 六：外部演练五件 | **五件成三件半** | **五件成三件半（不变）** | 挡着它的两条（形态① / 适配赛道）本轮**各推进一格但都没跑成**，演练**没有重跑** |
| 6-⑤ | 六：公开通道上跑完整 M6 pass | **未达成（18 run 一个都没有）** | **未达成（0/18，不变）** | 三件前置**齐了两件**（18081 通、provider 在 f02），第三件卡在 N-484 那次裁定 |

**六阶段总计：26 条 → 达成 21 / 部分达成 3（3-② 6-③ 6-④）/ 未达成 2（4-④ 6-⑤）。**
（2026-09-08 是 19 / 3 / 4；本轮把 4-⑤ 与 4-⑧ 两条关掉。）
**未达成与部分达成的 5 条里，只有一件是「我们没做到」**：`hint` 臂那一次真运行（4-④）。其余全部卡在用户裁定或授权。

### 1.2 本收尾卡（本轮五条完成定义）

| # | 完成定义 | 判 | 证据 |
|---|---|---|---|
| ① | 公开通道 18 个 run 跑完并出表 | **未达成（0/18）** | `$GB/runs_in/m6_public/jobs.jsonl` 18 行全 `pending`；`ops/reports/m6_public/README.md` §5。卡在 **N-484**（见第三节第 1 条） |
| ② | 单机双容器形态① 端到端 | **未达成** | `ops/reports/public/single_node_form1.md`。旧墙（容器打不到宿主端口）已解（N-559，实测 200/对照 200），**新墙是 N-560**（`gateway/sim_engine.py` import 穿到答案面），按红线 B2 停手 |
| ③ | 适配赛道 30 例各有 oracle 与一次真运行 | **达成** | `ops/reports/adapt/summary.md`：「例 30 / 有 oracle 30 / **有真运行 30** / 结算到的 run 30 / 问题 0」；749 次真 API / 30 run |
| ④ | 实例扩张每阶段 15–18、总计约 130，O1 按实例出 | **达成** | 冻结清单 `instances.counts = {bases 40, instances 130, per_stage S1–S5 各 17 / S6–S8 各 15}`；O1 两条通道 `ops/reports/probe_matrix_instances.md`（私有跑 127/130）与 `ops/reports/public/probe_matrix_instances.md`（公开跑 30/130，**墙钟封顶，如实报**） |
| ⑤ | 签字包重出并附实例层 O1 与适配赛道表 | **达成** | `ops/reports/signed/v1.0.14_r1.0.21/`（33 件 + MANIFEST，逐件 sha256 全过、全部 0400、`declared_but_missing` 2 件），比上一版**新增 11 件**、一件没少 |

**本轮：达成 3 / 未达成 2。两条未达成都卡在一次裁定，没有一条是「跑了但结果不好」，也没有一条被算成达成。**

### 1.3 f01 全量数字

| 量 | 现值 | 出处 |
|---|---|---|
| 任务集 / 参考轴 | **1.0.14** `947bf817ae3df348…` / **r1.0.21** `399fffde62108b52…` | `ops/manifests/v1.0-smoke{,.reference}.json` |
| `instances_fingerprint` | `969f698618eaaaae…`（**不在 `ROOT_FIELDS`**） | 同上 `instances` 段 |
| 出集 | **34 题**（regulated 29 + free 3 + 已放出探针题 2）**/ 挂起 6 题**；草拟 40 | `counts = {drafted 40, released 34, held 6}` |
| 模板 / 实例 | **40 模板**（= 参数表 40 **行**；目录 39 个）/ **130 实例**（可建 112，18 个是挂起探针题的实例，**设计如此**） | `instances.counts` |
| 实例 O1（私有） | 跑 **127/130**；可判 91、**零 finding 89**、非零 2、没判成 36（四类分开数） | `ops/reports/probe_matrix_instances.md` |
| 实例 O1（公开） | 跑 **30/130**；可判 26、**零 finding 26**、非零 0、没判成 4 | `ops/reports/public/probe_matrix_instances.md` |
| 基准实例 vs 出集同题「结论不同」 | **0 / 31** | 同上「一致性对照」一节 |
| 适配赛道 | 30 例 / oracle 30 / 真运行 30；`first_pass 14 / correct_flag 5 / failed 11`；`resolved_rate ALL 0.633` | `ops/reports/adapt/` |
| 结果库 | **118 行**（`adapt` 30 / `m6` 21 / `m6b` 8 / `v1demo` 8 / 其余各批） | `$GB/results/v1/results.jsonl` |
| 发布件 | **47 件，缺件 0**；`releasable=false`，**五条 blocker（一闭四未闭）** | `RELEASE_MANIFEST.json` |
| 签字包 | `v1.0.14_r1.0.21`：33 件 + MANIFEST，0400，`declared_but_missing` 2 | `ops/reports/signed/` |
| 票据 | 本节新增 **96 条**（N-475…N-570），累计到 **N-570** | `ops/tickets.md` |
| 本轮提交 | **27 个**（2026-09-10 起，含本卡的第一个提交；本卡另有两个提交落在本报告之后 —— 报告与判据、签字包） | `git log --since` |
| 全量 pytest | **4,026 passed / 3 failed / 30 skipped / 1 xfailed**（919.65 s，rc=1）—— 3 条全是 `test_lake_baseline`，**非湖类失败 0 条** | `$GB/scratch/wrapup/full2.log` |

> **全量 pytest 的红逐条说清楚。** 收口这一次 **3 条**，全部是 `ops/test_lake_baseline.py`
> （`test_stalled_tables_match_live_recompute` / `test_the_measured_stalled_tables_are_still_these_eight` /
> `test_freeze_line_green_does_not_imply_alive`）—— 外部 ETL 在写湖，施工契约点名这一类可不算，
> W.rt 那次全量也是同样这 3 条。**非湖类失败 0 条。**
>
> 收口的**第一次**全量是 5 条（3 湖 + 2 条**这一步自己造成的**）：`ops/test_wrt.py` 里两条按**收件箱文件名**
> 读的断言，在收件箱并进票据、改名 `.merged` 之后当场红。**判据没有变**（那两件事今天还在不在），
> 变的只是它住哪 —— 改成「收件箱（原名或 `.merged`）**并且** `ops/tickets.md` 里都要有」，
> **比原来更严，不是放宽**，然后重跑了一次全量。两次日志都在 `$GB/scratch/wrapup/`（`full.log` / `full2.log`）。

### 1.4 真 API 用量（机器统计，**以它为准，不要手抄**）

```
$PY ops/api_usage.py   →   总计 3,568 次真调用 / 109 个 run
上一次收口（2026-09-08）          2,668 次 / 77 个 run
本轮增量                            900 次 / 32 个 run
    ├ W1  N-130 复验（S7 双臂）      151 次 / 2 个 run
    └ Y2  适配赛道 30 例             749 次 / 30 个 run
```

**公开通道那 18 个 run 仍然是零次调用**（没跑起来）；`echo-min` 与 `quantagent` 的 6 个 run 也是零次调用
（不调模型 / LLM 在系统之外，N-449）。**别把「调用数是 0」读成「接入失败」。**
本轮外推与实测的对照：Y2 先跑 3 例测得 67 次 → 外推 670 次，实测 749 次（**误差 +12%**），未触发 1500 次的报备线。

---

## 二、本轮完成项与真运行证据路径

| 卡 | 做成了什么 | 真运行 / 产物证据 |
|---|---|---|
| **W1** | 网关起动可靠性（两个根因：守门扫全树 69 s 撞 90 s 超时；`StartLimitIntervalSec/Burst` 写在 `[Service]` 被 systemd **静默丢掉**）；`guard_modes` 遍历改 `os.scandir`（95.6 s → 43.9 s，**两版逐条同结论**）；N-388 默认档抬到 6M 并同步九处文档；注入器按通道取 provider 钉子（P2 与 P7b **两个入口**）；公开 provider 铺到 f02；**N-130 可关** | 起停三次各 rc=0 / 68–70 s / NRestarts=0 `ops/reports/w1/gateway_restart3.log`；provider 推送 `ops/reports/w1/provider_push_public.log`（28,610 文件 / 369 MB / 4 s，根现算一致）；18081 探测 `ops/reports/w1/public_gateway_18081_probe.log`（**f02 → f01:18081 = 200**）；**真跑 2 个 run / 151 次调用** `ops/reports/n130/`（open 64 次 4.04 M、strict 87 次 5.66 M，`llm_log` 全 `allow`、0 次 `budget_exceeded`，strict 臂 `sr_bucket=scorable`） |
| **W2** | 三件冻结件**不是丢了是从没进过仓库** —— 从数据湖收进来，`RELEASE_MANIFEST` 缺件 **3 → 0**、blocker `frozen_artifacts_missing` satisfied；只用 baostock 重建 csi300/csi500 的 PIT 名单并与私有逐日对账 | `ops/reports/public/factor_library_recovery.md`（与 gold 三项对账**逐条复现、一处没凑**）；`ops/reports/public/instruments_rebuild.md`（**5,056 次真取数** / 4,269 个交易日 / 80 次随机回查逐字一致；csi300 **成员一只不差**）；`$GB/snapshots/public_v1/instruments_rebuild/` |
| **W3** | 40 基点 → **130 实例**（窗口 × 宇宙 × 因子池），130 过 `build_task` **0 红 / 3.1 秒**；冻结清单加 `instances` 两层段（**刻意不进根**）；六道挂起探针题逐题判过后**一道都没放出** | `genetask/params/v1.0-instances.yaml`、`ops/mk_instances.py`、`ops/test_instances.py`(27)、`ops/reports/instances_design.md`；夹具通路验证：`s4-cor-01` 四个实例的夹具 sha **与出集记的逐字节相同** |
| **X1** | 探执行面 `--check-plane` 退 0；公开通道三控与逐族破坏样本**重跑且口径没变**（`mutations.md` 与 09-08 那份**逐字节一致**）；两份公开通道报告重出；形态① 的旧墙解掉、新墙找到并写进手册；手册 §1.4 补第三条路 | `ops/reports/m6_public/x1_rerun/{controls,mutations}.{md,json}` + `.diff`；`ops/reports/public/single_node_form1.md`；`$GB/scratch/X1/x1_probe3.sh`（容器 → 宿主 = 200，**对照 200**）；§1.4(c) f01 实跑：网关 50 秒起、`/calendar` 取回 10 行 |
| **Y1** | **一次重冻 v1.0.14 / r1.0.21**：N-383 Slip 符号统一 + 纳入判据（判自洽不比 gold）、N-384 `events.required` 收紧、实例两层清单首次落盘、六道探针题仍全挂起 | S8 四题 gold **私有 + 公开各重出一次、各 4/4 零 finding**，**只有 `s8-cor-01` 的数变了**（−202.514311 → **+53.483048**，唯一一道有卖单的题）`$GB/reference/tasks/v1.0-smoke/s8-*/gold/oracle_artifact.json`；`ops/validator_parity.py` 语料 124 份、两方向各 0 缺口；出集烟测 rc=0 且 bundle 无 gold/solution |
| **Y1b** | oracle 跑批与 O1 矩阵**按实例**出；私有 127/130、公开 30/130；两条**出集那 40 行看不出来的**真发现 | `ops/reports/probe_matrix_instances.md` / `ops/reports/public/probe_matrix_instances.md` + 两份累积明细；**发现一**：S4-ECO 参考解换窗口算出 NaN（N-518，`ic_stats` 七字段全 NaN / 挑出一个叫 `'nan'` 的因子）；**发现二**：S2-ROB 13 个月窗口跑不完 600 秒（N-519）；一致性对照 **0/31 结论不同** |
| **Y2** | 适配赛道按 N-348 重建题源（出集规定题的 oracle 产物、探针题不入、按阶段分层 + 种子固定）；守门「按集拒」**定点解除并记因**、换上更窄的**落点**门；后果写进三处文档 + 两处表；**30 例真跑** | **真跑 30 run / 749 次调用**，逐 run 见 `ops/reports/adapt/records.json` 与 `oracle_matrix.{csv,md}`；表 `table.{csv,tex}`；`ops/manifests/v1.0-adapt.json::exposed_source_tasks`（19 道）；`$GB/runs_in/adapt/` |
| **W.rt** | 红队十二条：**7 条 major 全修**、1 条 block 按红线 B4 如实登记不修、4 条 minor 登记；另抓到三条**一直红的门**（N-388 后 6 个 case、W2 之后的 `test_recon_public`、红线 5 源码侧门 4 处裸 `mkdir`） | `$GB/scratch/W.rt/full2.log`（全量 4009 passed / 3 failed，**非湖类 0 条**）；`ops/test_wrt.py`(18)；两次提交 `af0babc` + `52b951c` |
| **收尾卡** | 八张卡的收件箱并进票据（**N-475…N-570**，96 条、无缺号、零撞号）；HANDOFF §18.2；签字包 `ITEMS` 扩 11 件并重出；`RELEASE_MANIFEST` 重跑；全量 pytest + `api_usage`；本报告 | `ops/tickets.md`、`ops/HANDOFF.md` §18.2、`ops/reports/signed/v1.0.14_r1.0.21/`、`RELEASE_MANIFEST.json`、`$GB/scratch/wrapup/full.log`、本文件 |

**本轮真运行合计：32 个 run / 900 次真 API 调用**（W1 2 run / 151 次，Y2 30 run / 749 次）。
其余卡（W2 / W3 / X1 / Y1 / Y1b / W.rt / 收尾卡）**真 API 调用 0 次** —— 它们跑的是 oracle（参考解 + 网关）、
取数（baostock）、或纯文档与测试，`RUN_BUDGET` 一格没动。

---

## 三、BLOCKED_AWAITING_USER（卡在什么 / 两个方向 / 倾向）

### 1. 公开 provider 的 `files.sha256` 漏了它自己的两个元数据文件（**挡着公开通道全部 18 个 run**）· N-484

**卡在什么。** `$SNAPSHOTS/public_v1/qlib_provider` 的 `files.sha256` 没有收录 `MANIFEST.sha256` 与 `build_info.json`，
而 `genetask/pin.py::PROVIDER_META_FILES` 只豁免 `files.sha256` 与 `manifest.json`。于是根 hash 过了、
`pin.verify_filelist` 报 2 条「树里有而清单里没有」→ **即使 P2 的 expect 已经按通道给对了（N-482 已做），
公开通道的每一次注入仍然在 P2 红**。f01 源树同样 2 条、私有那份 0 条 —— **不是传输问题**。
`ops/run_joblist.py --check-plane` **退 0 也帮不了忙**：它只核根 hash，红是在真跑的注入期才发生的，
18 个 run 会一起红在 P2。**执行面另外两件前置本轮都齐了**（f02 → f01:18081 = 200；公开 provider 在 f02，根现算一致）。

**方向 ①（两卡都倾向）**：`PROVIDER_META_FILES` 加这两个名字。语义本来就对 ——
`snapshots/public/tables.py::_stamp` 写这两个文件时**明确把它们自己排除在清单之外**，它们就是「清单不含自己」那一类。
代价：`genetask/pin.py` 在冻结根 `CODE_FILES` 里 → **推任务集版本（v1.0.15）**；且要先解掉用户 2026-09-10
「`genetask/pin.py` 一个字不动」那条裁定。

**方向 ②′**：把 `MANIFEST.sha256` 从 provider 树里删掉，再把 `build_info.json` 收进 `files.sha256`。
（**W1 原本列的方向 ②「两个都收进 `files.sha256`」被 X1 证伪**：`MANIFEST.sha256` 里有一行记的就是
`files.sha256` 的 sha256，两者互指，**没有不动点**。）代价：根 sha 从 `561348660a3175b1…` 变成新值 →
`ops/HANDOFF.md:557`、`ops/reports/public/release_forms.md:118`、`qlib_provider_public.md`、
**v1.0.13 签字包里两处**、`runner/inject.py::PUBLIC_PROVIDER_SHA256_ROOT` 全要改，已签字那份作废，
**并且少了一份逐文件校验表**。

**倾向 ①。** **明确没有采纳的第三条**：推的时候把这两个文件排除掉 —— 门会变绿，但**绿的原因是把证据挪走了**。

### 2. `gateway/sim_engine.py` 的 import 链穿到答案面（**挡着单机形态① 端到端**）· N-560

**卡在什么。** `gateway/app.py → routers/sim.py → sim_engine.py:20 → from reference.artifact_schema import
(LEGAL_TRANSITIONS, TRADABILITY_STATES, UNTRADABLE_STATES)`。形态① 要求网关与容器**同机**，
于是「起网关」这一步与**红线 B2（`reference/` 不进执行面）**直接撞车 → 网关起不来 → 真跑 / 结算 / 出表三步一步没走。
这是**唯一**一处（`grep -rn "from reference" gateway/ snapshots/` 只此一行），被引的是三个协议常量、不是任何题的答案，
`answer_plane_guard.scan` 单独扫它**命中 0** —— 但该模块自己的 docstring 写着「本模块是**评分侧**的（不进执行面）」，
而 B2 的措辞是整棵 `reference/`。

**方向 ①（倾向）**：把三个常量搬出 `reference/`（落到 `genetask/` 或一个新的协议侧模块）→ 推参考轴 **r1.0.22**。
语义对：它们是协议 schema 不是参考解；搬完两种形态才**真的**是同一套代码。

**方向 ②**：裁定「`reference/artifact_schema.py` 允许出现在执行面」，B2 从「看目录名就能判」变成「逐文件判」。
代价：**B2 之所以有效正是因为它不需要判断** —— 下一次谁再加一个 import，没人拦得住。

**倾向 ①。** 在裁定下来之前，形态① 对外部用户是「起不了网关」，手册已按这个事实更正，
不再宣称「只差三个常量与一条防火墙规则」。**没有采纳的做法**：只把那一个文件 scp 过去让网关起来。

### 3. S6 gold 的 `provenance[0].artifact_id` 是未填的占位串（**让适配表偏低约 13 个百分点**）· N-543

**卡在什么。** 五份 S6 参考解的 `provenance[0].artifact_id` 都是字面量 `TODO:signal-artifact-id-missing`
（来源 `genetask/templates/S6/*/solve.py:126` 的兜底值）。适配赛道 `adapt-l1-08` / `l2-07` / `l2-08` / `l3-06`
四例的 `broken.json` 也带着它；适配臂规则 1 要求「源里没有的写成显式 `unresolved`」，被测方照做、oracle 却要求原样抄回。
改正后：ALL `resolved_rate` **0.6333 → 0.7667**、failed 11 → 7。主赛道评分器**不比 `provenance`**，主表数不受影响。

**方向 ①（倾向）**：改 `solve.py` 的兜底值为协议的 `unresolved` 标记 → 参考轴 **r1.0.22** +
重出 S6 五题 gold + 重出四例 oracle + 重算适配表。**`solve.py` 在参考轴冻结根，红线 B4 禁止施工侧直接动。**
**方向 ②**：在 `scorer/adaptation.py::match_oracle` 里把 `TODO:` 前缀值与 `unresolved` 判为等价 —— **判据变更**。

**倾向 ①**（修根因；这个项目对同类问题 N-383 刚刚就是按 ① 做的）。
**注意：方向 ① 与上面第 2 条的方向 ① 都推 r1.0.22，应当并成一次。**

### 4. 要不要把 baostock 重建版换进公开包的 `instruments/{csi300,csi500}.txt` · N-494

**换**：公开包在数据许可上真正自足（不再派生自 tushare），且重建版在进出场日期上更准（私有那份把调整吸附到月末、中位晚 15 天）。
**代价**：换掉公开通道的宇宙定义 → 公开 gold 因子面板 / 双实现互检 / τ·ε 标定 / `calibration.json` 整条链要重跑重签，
**是判据变更不是数据修补**。
**不换**（W2 已按此执行）：在 `DATA_LICENSE` / 数据卡里显式写明「名单一项来自 tushare 派生，不在 baostock 许可射程内」，
当成一条已披露的许可边界。
**倾向不换** —— 收益（许可自足）可以先靠披露顶住；等用户明确要「公开包零私有依赖」时再一次性换、一次性重签。
判据输入已量清楚：csi300 **成员一只不差**、csi500 只在私有的 32 只全在首 14 天的种子段。

### 5. S4-ECO 的参考解换个窗口就算出 NaN · N-518

三个变体全废（两例 `ic_stats` 七字段全 NaN；一例崩在「`factor_pool.parquet` 里没有 `'nan'` 的行」），
夹具都在、**不是缺件**。**这正是实例层存在的全部理由的实证** —— 出集那 40 行每行只有一个取值，`s4-eco-01` 一直是绿的。
**① 修 `reference/s4_oracle_common.py` 与 S4-ECO 的 `solve.py`** → 参考轴 **r1.0.22**（**倾向**，与第 2/3 条并成一次）；
**② 认定这几个窗口取值超出设计范围、从参数表候选里去掉** —— 不推版本，但等于宣布「这道题只在一个窗口上成立」，
**等于把温度计藏起来**。

### 6. 另外四条待裁定（方向已量清楚，不展开）

| # | 事项 | ① | ② | 倾向 |
|---|---|---|---|---|
| N-519 | S2-ROB 13 个月窗口跑不完 600 秒 | 先**量**再决定放宽 `run_one` 的超时 | 把该取值从参数表候选里去掉 | **①**（没量之前删掉 = 用「看不见」替代「跑得慢」） |
| N-520 | `gateway/sim_factory.py::task_dir` 跨出集 glob，实例集一落盘就把**出集** S8 打挂 | `task_dir` 收一个显式 `set_id` | 实例集的基准实例改发新号 | **①**（② 会让「基准实例 = 出集那道题」在 id 上看不出来，且 130 个 id 全变） |
| N-503 | `instances_fingerprint` 进不进 `ROOT_FIELDS`；`v1.0-instances.yaml` 进不进 `CODE_FILES` | 进（实例层也受根保护，代价是实例表一动全部 bundle 重出） | 不进（记录在案但不受保护） | 三张卡一路**按保守方向不进**；**要做趁早**，越晚作废的通行证越多 |
| N-491 | `reference/factor_exec.FACTOR_LIB` 只认数据湖，公开包里那三份外部用户读不到 | 加「湖在用湖、不在退回仓库副本」的回退（推参考轴，**不改任何数值**） | 不加（「公开包自足」只做到「文件在」，没做到「能用」） | **①**（两处逐字节相同，有测试钉住） |

---

## 四、CONFLICT 清单（规格冲突，八条；一律按保守方向做并留了判据）

| # | 卡 | spec_a（原文） | spec_b（实况 / 另一处原文） | 怎么做的 |
|---|---|---|---|---|
| 1 | W1 | 用户裁定：「N-130：S7 用 **300 次 / 6M** 跑一道验」 | 同一轮任务书：「**走档位，不显式给**」，而 `BUDGET_TIERS["S7"]` 是 300 次 / **18M** | **按「走档位」做**。6M 会在约第 100 次调用撞 token 闸，而撞闸的现场**长得像结论**，正好会把 N-130 错误地关成「已知限制」。事后两种读法都够（strict 5.66 M，离 6M 差 5.6%）—— **下次收紧 S7 的 token 档按这个数算，别按 18M 反推** |
| 2 | W3 | 任务书：「实例 ID = `<template_id>#<param_fingerprint>`」 | `S1/source_status` 被 `s1-rob-01` 与 `s1-rob-02` **两行**复用且窗口宇宙相同 | id 加 `base_task_id`。照原样写会让两者的**基准实例 id 逐字节相同**（**实测撞了**）。**身份的单位是参数表的一行** |
| 3 | W3 | 报告口径「40 模板」 | `genetask/templates/` 下模板**目录**只有 **39** 个 | 文档里把「40 模板」显式定义成「参数表的 40 **行**」，三处各写一遍。否则 40 与 39 会同时出现在墙上 |
| 4 | X1 | 手册 §1.1：「两种形态跑的是**同一套代码**，差别只在三个常量与一条防火墙规则」 | `reference/artifact_schema.py` 的 docstring：「本模块是**评分侧**的（不进执行面）」+ 红线 B2 | **按保守方向：不推 `reference/` 的任何内容上 f02，网关没起**；手册 §1.1 加「2026-09-10 更正：这句话今天**不成立**」，留了一条**会自己失效**的测试 |
| 5 | Y1 | 用户裁定 N-383：「**Slip 纳入 S8 判据**，容差 = 一个最小价位……**逐单**按该单的计价基准算再量加权」 | 同一条裁定给 Fill 的说明：「题面没规定下哪些单，两轮不是同一个量的两次测量」 | **判成 `SlipSelfConsistent`（自报 vs 从 agent 自己的事件链重算），不与 gold 比。** 三条理由：① 那条说明对 Slip 同样成立；② 一个价位的容差在 gold-vs-agent 上会让**全员判 0**（离散度 ±170 bps vs 容差 0.058 bps）；③ 「逐单」需要一份委托清单，gold-vs-agent 比的是两个标量、**拿不出「逐单」** |
| 6 | Y1 | 用户裁定 N-384：「`events` 的 required 收紧到题面写的那几个字段，**不多不少**」 | 题面对四类事件要求**不同**，而 JSON Schema 的 `items.required` 是**扁平列表**，说不出「按 type 分档」 | 扁平 required = 四类的**交集** `[ts,type,order_id]`，逐类必填走 `allOf` + `if/then`。**没有采纳**「六个键全塞进扁平 required」——那会要求 cancel 事件也带 `price`，**比题面严** |
| 7 | Y1b | `render_matrix` 抬头：「**任一格非零即探针缺陷**」 | 同一文件模块 docstring：「`malformed` 同样算，**因为 oracle 是我们自己写的**」 | 实例层矩阵抬头改成**两类行归因相反**。按字面读法，S4-ECO 那 7 条 `malformed` 会被归成「探针缺陷」，于是正确的动作变成「去改探针别报 NaN」——**那正好把唯一一个抓到参考解缺陷的信号关掉** |
| 8 | Y2 | 用户裁定 N-348：「题源 = **33 道**出集规定题的 oracle 产物」 | 清单现值：出集 34 = 规定题 **32** + 已放出探针题 2；挂起 6 道全是探针题 | **按清单现值做 32 道**（再被 Y2 自加的 700 KB 体量帽减到 30 道候选池），差如实记在四处。**没有把清单改成 33，也没有假装 33 就是 32。** 这个差不影响任何判据 |

---

## 五、红线接触记录（B1–B7，含未违反的接触）

| 红线 | 本轮接触 | 判 |
|---|---|---|
| **B1** 无 sudo / 不改既有系统服务与定时任务 | W1 改了 `--user` 单元 `genebench-gateway.service`（用户 2026-09-04 裁定网关改动不走既有服务待批），全程无 sudo、备份 `.w1bak`；X1 **只读查**了 f02 的 `genebench-answer-plane-scan.timer` 状态（enabled+active，没装没改）；其余卡只起停我们自己的公开实例 `ops/public_gateway.sh` | **未违反** |
| **B2** 答案面不上执行面 | **本轮最主要的接触点，且是按用户裁定 N-348 主动做的**：30 个适配 bundle 的 `work/input/broken.json` **内容上就是 19 道出集规定题的答案**。守门「按集拒 `v1.0-adapt`」**显式解除并记因**，换上更窄的**落点**门（只许 `/data/genebench_runner/adapt/`，**没声明落点 = 拒**，实测三态）；`ORIGINS_NOT_PUSHABLE=('gold_derived',)` 一般规则**没放宽**，通行证如实自报。后果写进三处文档 + 每一张表的脚注 + 逐题清单。**另一处接触**：X1 发现 `gateway/sim_engine.py` 依赖 `reference.artifact_schema`，**按保守方向停手**（第三节第 2 条）。推 f02 的每一批素材推之前都过 `answer_plane_guard.scan`（公开 provider 28,610 文件 **0 命中**、代码 staging 36 文件 0 命中、快照表 23 文件 0 命中），bundle 一律走 `ops/push_bundle_to_f02.sh` | **未违反**（B2 的放宽是用户裁定的，且换上了更窄的门） |
| **B3** 凭据不进仓库 / 日志 / 对话 | 全轮没有 cat / echo / 复制过 `DEEPSEEK_API_KEY`，没读过 f02 的 `secrets.env`；测试与 scratch 里没有 key 形态字面量（`ops/test_env.py` 的红线 3 门在两次全量里都绿） | **未违反** |
| **B4** 题面改动必重冻结记因 | Y1 **主动按裁定**改了冻结根里的 `ops/specs/artifact_schema/v1.0/S8.json`（`CODE_DIRS`）与 `reference/s8_oracle_common.py`（`REFERENCE_MODULE_FILES`），两条轴各推一版、各写一条含 why/what/scope/gates/consequence 的完整记因，按 **N-111 分两次** `--write` / `--write-reference`。`genetask/templates/**` 的题面正文**一个字未手改**（指纹变是因为 `fixed:output_format` 机器从 `required` 生成）。`genetask/pin.py` **全轮一个字未动**（用户约束）—— 正因为不动，N-484 才只能记 blocked。W.rt 遇到的那条 block（S6 gold 的 TODO）**按 B4 停手不修** | **未违反** |
| **B5** 网关只绑显式地址 / 端口映射 / 网段 / 出向白名单 | 全轮没有出现过 `0.0.0.0`。私有走生产实例 `192.168.1.48:18080`，公开走 `ops/public_gateway.sh` 的 `192.168.1.48:18081`（探完即 stop、端口已释放复核过），X1 的验证实例显式错开到 18082。容器端口映射一律 `192.168.1.219:PORT`；探针容器网用 `172.31.242.0/24`（在用户放行的 `/22` 内），跑完即删；`MODEL_API_ALLOW` 未动 | **未违反** |
| **B6** 跑批与真跑必须串行 | 30 次适配真跑**每一次**都包 `ops/gateway_lock.py`；两次 N-130 真跑由 `run_joblist` 逐 run 包锁；oracle 跑批一律 `gateway_lock` + 内层 `--no-batch-lock`（**忘了它会自死锁，Y1 白等 120 秒**，N-530）。**一处对字面的偏离，照实说**：Y1b 的私有跑批换用了 `$GB/scratch/Y1b/gwlock_block.py` —— **同一个锁文件、同一套持有者 JSON、同一条互斥保证**，只把 `LOCK_NB` 轮询换成阻塞 `flock`（内核排队）。原因是轮询式对着 Y2 的背靠背生产者会**饿死**（实测连等 1711 秒零进展）。N-125 要的串行完全成立，且**比轮询版更严格**。**请编排方确认**（N-521） | **一处按等价物做了替换，已如实登记待确认** |
| **B7** f02 上跑 runner 的 `umask 022` / `PYTHONDONTWRITEBYTECODE=1` | 到 f02 的命令都带；f01 侧远端命令一律 `umask 077` 开头、scp 后 `chmod -R go-rwx`。**红线 5 踩过三次**（W1 / Y1 / X1 各一次：0644 的 scp 文件、0775 的 `__pycache__`、别人 git 操作留下的 0664 `.git/index`）—— 症状都是「网关拒绝启动」，处置口径是 `report_io.secure_tree`。W.rt 另外**修好了红线 5 的源码侧门**（`snapshots/public/` 4 处裸 `mkdir`，自 W2 起一直红，N-554）。收尾复核 `ops/guard_modes.py` 报「敏感根权限合规（2 个根）」rc=0 | **未违反** |

**收尾卡自己的接触**：只改了 `ops/tickets.md` / `ops/HANDOFF.md` / `ops/archive_signoff.py` / `ops/reports/signed/**` /
`ops/reports/wrapup_report.md` / `ops/test_wrapup.py` 与 `RELEASE_MANIFEST.json`（生成件）。
**零真 API 调用、零 f02 连接、冻结根一个文件未动**；共享文件的改动都是 `flock git.lock` 内的**幂等追加**
（幂等靠**核终态**而不是重跑补丁 —— 那正是 W.rt 踩过的坑，N-555）。

---

## 六、需要用户提供的（一处列全）

**A. 挡发布的四条**（条数以 `RELEASE_MANIFEST.json` 的 `blockers` 为准；第五条 `frozen_artifacts_missing` 本轮**已闭**）

| # | blocker | 要什么 | 闭合之后要做什么 |
|---|---|---|---|
| 1 | `data_license_text` | **baostock 书面再分发许可的原文** | 放进 `ops/terms/baostock/permission/`，把 `DATA_LICENSE` 顶部状态从 `pending_license_text` 改成 `granted`。**按 §2.2 的四个问题逐条核**，缺哪条写明缺哪条，**不要按最宽的解释填空** |
| 2 | `no_clone_url` | **一个外部用户能访问的 git 地址** | 改 README §2.1 与 §5 + 写进 `README_TEMPLATE` + **重打一次公开包**（包里那份 README 是旧文本，且 `frozen/` 只有 3 件 —— N-492） |
| 3 | `code_license_undecided` | **代码许可选哪个**（建议 Apache-2.0 或 MIT） | 换 `LICENSE` 的 SPDX 行与正文 + 重跑 `ops/mk_release_manifest.py`；**README §6 那两段要人工改一遍** |
| 4 | `public_channel_zero_runs` | **不是要东西，是要下面 B 组第 1 条那次裁定** | 跑完 18 个 run 并出表 |

**B. 挡着完成定义的裁定五条**（每条的两个方向与倾向见第三节）

| # | 票据 | 一句话 | 倾向 | 不解的后果 |
|---|---|---|---|---|
| 1 | **N-484** | 公开 provider 的 `files.sha256` 漏了自己的两个元数据文件 | **①** 改 `PROVIDER_META_FILES`（要先解掉「`pin.py` 一个字不动」并推 v1.0.15） | **公开通道 18 个 run 一个都跑不了**；`public_channel_zero_runs` 永远不闭 |
| 2 | **N-560** | `gateway/sim_engine.py` 依赖 `reference.artifact_schema` | **①** 把三个协议常量搬出 `reference/`（推 r1.0.22） | 形态① 对外部用户是「起不了网关」；**只有一台机器的外部运行者没有路** |
| 3 | **N-543** | S6 gold 的 `provenance` 是未填的占位串 | **①** 改 `solve.py` 兜底值（推 r1.0.22） | 已发表的适配表**偏低约 13 个百分点** |
| 4 | **N-518** | S4-ECO 参考解不耐窗口变化 | **①** 修参考解（推 r1.0.22） | 这道题在实例层只有 1/4 可用，而出集那一行看起来一直是绿的 |
| 5 | **N-494** | 要不要把 baostock 重建版换进公开包的 instruments | **不换**（先靠披露顶住） | 公开包的名单一项仍派生自 tushare，不在 baostock 许可射程内 |

**B 组第 2、3、4 条都推参考轴 r1.0.22 —— 请并成一次，别推三次**（每推一次都作废一批通行证）。

**C. 要编排方确认的三条**

| # | 事项 |
|---|---|
| 1 | **N-521**：Y1b 用「同一把锁、同一套持有者记录、把轮询换成内核排队」的包装绕过了 `gateway_lock` 的饿死。不接受的话请裁定替代方案 —— 直接后果是这类跑批在有背靠背生产者时**一次锁都拿不到** |
| 2 | **N-534**：Y2 自加的题源体量帽 `MAX_SOURCE_BYTES = 700 KB`（不在裁定里），排掉 `s5-eco-01`（4.0 MB）与 `s4-ops-01`（878 KB）。要保留大产物题改一行常量即可，但要一并想清楚预算 |
| 3 | **N-535**：Y2 把适配模块 `MANIFEST.json` 的 `status` 从 `draft` 改成 `released`（三件工件内容一字未改、sha 与 09-07 相同）。不改就跑不成真跑，但该文件不在 Y2 的路径清单里 |

**D. 上一轮 §17.6 里仍然立着、本轮没有变化的两条**：提交署名两条 trailer 并存请定一个；卡 6.4 对同一目标真跑 3 次的理由已逐条记在案。

---

## 七、下一步（按「解一次裁定能解开多少」排序）

1. **裁 N-484**（一行改动 + 一次推版）→ 公开通道 18 个 run 立刻可跑（约 600–1200 次真 API、3–4 小时网关独占），
   `public_channel_zero_runs` 闭合，Table A/B 第一次有公开通道的读数。**这是投入产出比最高的一条。**
2. **把 r1.0.22 那三条并成一次推版**（N-560 常量搬家 + N-543 S6 占位串 + N-518 S4-ECO 参考解），
   一次重冻同时解开：形态① 端到端、适配表偏低 13 个百分点、S4-ECO 的 3/4 实例。
   **推完必须重出两份就绪报告的 §1** —— 上一次就是没人重出才成了红队 major（N-544）。
3. **补 30 个 `open` 参照臂 run**（约 750 次真 API）→ 适配赛道从「绝对值 0.633」变成**读得出干预效应**（N-537）。
4. **实例层补跑**：私有还差 3 个（要先解 N-520）、公开还差 100 个（要先按公开通道物化 S4/S5 夹具，约 3 小时网关独占）；
   S6 那 15 个**跑一次废一次**，先解 N-510（倾向：让 `mk_instances --fixtures` 先落 `task.yaml` 再补 sha，**不动冻结根**）。
5. **四条 minor 与两条待办**：主表 CSV 的 N-348 脚注（N-558）、两份实例矩阵的口径行（N-557）、
   暴露脚注四处措辞统一成「19 道」（N-556）、`ops/mk_tables.py` 末尾那条过期的已知限制（N-541）、
   `push_bundle_to_f02.sh` 把落点传给守门（N-538，一行）、公开包重打（N-492）。**谁顺路谁做。**
6. **三条会再咬人的**：网关在 S7 负载下 OOM（N-479，**② 查 RSS 为什么涨到 6G 更像根因**）、
   `runner_core` 的 stdin 透传（N-485）、`gateway_lock` 改阻塞式（N-521）。
