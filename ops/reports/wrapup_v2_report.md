# 收尾卡 v2 报告（到可分发）—— 2026-09-11

> 七节格式（一…七），外加**第八节：21 条裁定逐条判**。
> 所有数字都从源头现算：版本轴取 `ops/manifests/*.json`，blocker 取 `RELEASE_MANIFEST.json`，
> 用量取 `ops/api_usage.py` 的机器统计，表取结果库。
> **凡是没做到的，本报告写「未达成」并说清为什么，不写成「部分达成」。**

---

## 一、状态表 + f01 全量数字 + 真 API 用量

### 1.0 现值更新（2026-09-12，最终卡红队修复之后）

> **这一段是后写的**。下面的 §1.1 / §1.2 是收尾卡 v2 当天（2026-09-11）的记录，**原文保留**；
> 但它们之后又被四张卡改动过（重冻两条轴、N-611 公开通道重跑、裁定 ⑨ 的数据许可、
> 红队最终轮的四条 block）。**要引用现值就引用这一段**，§1.1 / §1.2 只用来读当天的判断。
> 这里每一个数都从源头现算：轴取 `ops/manifests/*.json`，blocker 取 `RELEASE_MANIFEST.json`。

| | 现值（2026-09-12） | §1.1 当天写的 |
|---|---|---|
| 任务集（私有） | **1.0.16**，根 `d9ebd5412ac4cc7e4569ae41887bff5fd0a40ec59e78baad34ccf5086550fc63` | 1.0.15 / `622f720c…` |
| 任务集（**公开**，裁定 ①） | **p1.0.0**，根 `3e5ab441a991c4115a6c0fb988715f583e22ee303f582f1302fd3197fb183538` | §1.1 里没有这一行 |
| 参考面 | **r1.0.23**，根 `dddabe440163b36ef678dee314b29604de3292470dd88fc07aa5162dc9d7cfb2` | r1.0.22 / `c61b0667…` |
| 签字包 | `ops/reports/signed/v1.0.16_r1.0.23/` | `ops/reports/signed/v1.0.15_r1.0.22/` |
| 发布清单 | **53 件**，缺件 **0**，`releasable=true`，未闭合 blocker **0 条** | 53 件 / `releasable=false` / 未闭合 1 条 |

**blocker 五条的现状**（条数以 `RELEASE_MANIFEST.json` 的 `blockers` 为准）：

| blocker | 现状 | status_now（现算） |
|---|---|---|
| `data_license_text` | **已闭** | DATA_LICENSE = `granted`；许可方出具的正文**仍未入库**，DATA_LICENSE §2.1 是一处显式占位 |
| `no_clone_url` | **已闭** | 两个地址已定，README 与 CITATION.cff 两处一致 |
| `frozen_artifacts_missing` | **已闭** | 全部到位 |
| `public_channel_zero_runs` | **已闭** | m6_public：18 个有 run 的行 / 共 18 行 |
| `code_license_undecided` | **已闭** | SPDX-License-Identifier: Apache-2.0 |

`data_license_text` 在 2026-09-11 之后由用户裁定 ⑨ 闭合：**授权已取得**（研究用途、允许
再分发派生日线数据、署名 baostock），`DATA_LICENSE` 状态翻成 `granted`；**许可方出具的
书面正文仍未到手**，`DATA_LICENSE §2.1` 是一处显式占位，`ops/terms/baostock/permission/`
仍然是空的。**「授权有了」与「原文可查」是两件事** —— 后者没有，这一点不因 blocker 闭合而消失。

`public_channel_zero_runs` 的 `status_now` 也变了：§1.2 当天写的是「18 行里 8 行有 run」，
N-611 之后是 **18/18**，且 18 个 run 全部跑在**真公开 provider** 上（前 8 个是受污染重跑，
证据在 `ops/reports/m6_public/g1_public_provider_rerun.md`）。

---

### 1.1 这一版是什么

| | |
|---|---|
| 任务集 | **1.0.15**，根 `622f720c95cf2249e5a8c5479b2a9d5d620f4b30e420f2e5dfe9d698f6766d61` |
| 参考面 | **r1.0.22**，根 `c61b066734e3192f67c04ede148da46f9bc16f8b51e9440403ceceb523604bf0` |
| 题面指纹 | `9a011b7d8bb6d81e…` —— **与 v1.0.14 相同**，题面逐字未变 |
| 出集 | **34 题 / 挂起 6 题**；**40 模板 / 130 实例** |
| 协议轴 | `geneprotocol_v1@d6fbcaa08302`（仓库里现算；逐 run 反算见 `VERSIONS.md §1.3`） |
| 通道 | `private` / `public` |
| 票据 | 到 **N-652**（本轮并入 85 行，其中 3 行是既有票据的状态更新） |
| 签字包 | `ops/reports/signed/v1.0.15_r1.0.22/` —— **49 件**，缺件 **0**，逐件 0400 |
| 发布清单 | **53 件**，缺件 **0**，`releasable=false`，未闭合 blocker **1 条** |
| 版本锁 | `ops/genebench_cli.py axes` **退 0**：四条轴与清单、与 `freeze_v10` 代码常量一致 |

### 1.2 blocker 逐条现状（**权威条数以 `RELEASE_MANIFEST.json` 的 `blockers` 为准：五条**）

| blocker | 现状 | 说明 |
|---|---|---|
| `frozen_artifacts_missing` | **已闭** | 上一轮 W2 补齐，`missing` 空 |
| `public_channel_zero_runs` | **本轮闭合** | `m6_public` 18 行里 **8 行有 run** 并已结算入库（卡 X1）。**别把它读成「公开通道验完了」** —— 另 10 行出不了集，见第三节 |
| `code_license_undecided` | **本轮闭合** | `LICENSE` 首行 `SPDX-License-Identifier: Apache-2.0`，`CITATION.cff` 的 `license` 同（卡 B，用户裁定 ⑳） |
| `no_clone_url` | **本轮闭合** | 两个真地址落进四处并同源（卡 Z，裁定 ㉑）。判据由「本地 `.git/config` 有没有 remote」换成「地址是真地址 + README 与 CITATION 两处一致」——**刻意不查可达性**，否则清单内容会取决于跑它的机器有没有外网 |
| `data_license_text` | **未闭合（在用户手里）** | `DATA_LICENSE = pending_license_text`；baostock 的书面再分发许可原文未入库 |

`releasable=false` 只差这一条。**但「releasable」不等于「外部用户能用」** —— 三件真正挡着可用性的事
没有进 blocker 列表，全在第三节。

### 1.3 f01 全量数字

| | |
|---|---|
| 结果库 | **132 条记录**（主赛道 102 / 适配赛道 30），**19 个 batch** + 派生的 `m6_all` |
| 记录的版本轴分布 | `1.0.7/r1.0.7` 5、`1.0.7/r1.0.8` 21、`1.0.9/r1.0.14` 8、`1.0.11/r1.0.18` 4、`1.0.11/r1.0.19` 20、`1.0.12/r1.0.19` 8、`1.0.13/r1.0.20` 22、`1.0.14/r1.0.21` 30、**`1.0.15/r1.0.22` 14** |
| 实例层 O1（私有） | **零 finding 108/130**、非零 **0**、没产出 **22** |
| 适配赛道 | L1 `first_pass` **8**、L2 **9**、L3 `correct_flag` **6**；ALL `resolved_rate` **0.7667**、`failed` **7** |
| 全量 pytest | ****30 failed / 4244 passed / 30 skipped / 1 xfailed**（17 分 44 秒；`flock pytest.lock` 内、`systemd-run --user --scope -p MemoryMax=6G`、`ulimit -n 8192`）。**30 条红全部是进场时就红的**，逐条归因见 1.4** |

**实例的 130 不是「108 差 22」那么读的。** 130 = 34 道出集模板的 **112** 个实例
+ **6 道挂起探针模板**的 18 个。那 18 个被 E9c/E9d2 拦在落盘这一步，
按裁定 ⑦「无零 finding 的实例不进出集」**本来就不该进**；剩下 4 个卡在 N-578
（S8 四道题的 `task_id` 在两个集根里都有，sim 会话工厂撞号即拒）。
所以真实的分子分母是 **108/112**，矩阵页已把两类分开列、归因相反（卡 X2）。

### 1.4 那 30 条红逐条归因（**本卡一条都没造成**）

本卡跑了两轮全量。**第一轮 32 failed，其中 2 条是本卡引起的**，当场修掉之后第二轮 **30 failed**：

* `ops/test_operator_manual.py::…[ops/tickets_inbox/Y1-rehearsal.md]` —— 本卡把收件箱改名 `.merged`，
  而手册第 815 行引着那个路径。改成指票号（`ops/tickets.md` 的 **N-611**）——
  收件箱是临时落点，票据表才是长期那一份。
* `ops/test_release_manifest.py::test_every_recorded_sha_of_a_handwritten_item_is_the_real_one`
  —— 本卡改了 `ops/HANDOFF.md`（手写件）之后没有重跑清单。重跑即绿。
  **这条值得记住**：改完发布件**最后**跑一次 `mk_release_manifest.py`，顺序反了就红。

剩下 30 条：

| 条数 | 是什么 | 归因 |
|---|---|---|
| **23** | `ops/test_sim_factory.py`（22 条）+ `ops/test_public_acceptance.py::test_set_name_may_carry_one_directory_level`（1 条） | **全部指向 N-578** —— S8 四道出集题的 `task_id` 在 `v1.0-instances/` 与 `v1.0-smoke/` 两个集根里都有，`gateway/sim_factory.py::task_dir` 撞号即拒。**这是今天最大的一摊红，而且它同时挡着 S8 的 gold 重出与公开通道的 S8 真跑**（发布验收绕不开 S8）。止血一行、正解要动 `gateway/` 与 `reference/`，见第七节第 3 步 |
| **3** | `ops/test_lake_baseline.py` | 外部 ETL 持湖写锁那一类 —— 按施工契约的口径不算本轮的 |
| **1** | `ops/test_env.py::test_no_api_key_material_in_run_dirs` | 命中的是 **`$GB/scratch/Y1/rh2_oper…`** —— 卡 Y1 把整棵仓库拷进了 scratch，而 `ops/test_env.py` 自己就带着 key 形态的检测样式，于是那份副本被自己的检测器抓了。**本卡名下 0 条**（现查过）。清掉那几个 scratch 目录即绿 |
| **1** | `ops/test_wrapup.py::test_两条未达成没有被写成达成` | 收尾卡 **v1** 的报告还写着公开通道「未达成（0/18）」，而 `m6_public` 现在有 8 个已结算的 run。**方向是低报不是粉饰**，但一份签过字的报告说着一件已经不成立的事。v1 的报告不在本卡路径，已登记 N-651 |
| **1** | `ops/test_wrt.py::test_rebudget只动没跑过的行` | `KeyError: 's1-cor-01.strict.cfg.r01'` —— 裁定 ⑮ 给 `job_id` 加机器标识的确定性下游（与 N-623 同族）。改法是按 `make_job` 现算的 `job_id` 取 |

**这一遍全量跑完之后，仓库里只再动过两处**：本节这段文字（`wrapup_v2_report.md` 不是发布清单里的件）
与重跑一次 `mk_release_manifest.py`。受影响的三个测试文件
（`test_V2` / `test_release_manifest` / `test_operator_manual`）事后**定向复跑过，全绿**。

### 1.5 真 API 用量

`$PY ops/api_usage.py`（机器统计，从 f02 的 `llm_log` 现读 `decision==allow` 的条数）：

* **累计 4,445 次 / 123 个 run**。
* **本轮新增 877 次 / 14 个 run**：
  * 卡 X1 公开通道构造验收 **377 次 / 8 个 run**（$8.20）—— `ops/reports/m6_public/x1_runs_summary.md`；
  * 卡 Y1 从零演练（⑭，形态 ①）**500 次 / 6 个 run**（$3.14）—— `ops/reports/rehearsal_v2.md`。
* 本轮另外七张卡（A / B / C / X2 / Y2 / Z / V2.rt）与本卡**真 API 各 0 次**。
* 落盘：`/data/shared/genebench/scratch/api_usage/api_usage.{json,md}`。

---

## 二、本轮完成项与真运行证据路径

### 2.1 一次重冻压了四件动冻结根的事（卡 A，提交 `49748ac`）

| 做了什么 | 证据 |
|---|---|
| ① `pin.PROVIDER_META_FILES` 收进 `MANIFEST.sha256` / `build_info.json`，豁免面封闭成**四个字面名字** | `ops/manifests/v1.0-smoke.json`、`ops/test_provider_pin_channel.py`；两条通道 P2 在**真树**上现算全绿，反向门验过（塞一个清单外文件当场红） |
| ② S6 兜底值 `TODO:signal-artifact-id-missing` → 协议的 `UNRESOLVED` | 五份 `genetask/templates/S6/*/solve.py` 现在 `from reference.artifact_schema import UNRESOLVED`；旧串**只剩在注释里说明当初错在哪**。gold 现为 `[{"stage":"S5","artifact_id":"unresolved"}]` |
| ③ S4-ECO 留出段跟着窗口走（`split_window`）+ `bh_fdr_select` 先筛掉算不出 t 的候选 | `genetask/templates/S4/eco_free_select/solve.py`、`reference/s4_oracle_common.py`；四实例 4/4 零 finding |
| ⑤ `instances_fingerprint` 进 `ROOT_FIELDS`、`v1.0-instances.yaml` 进 `CODE_FILES` | `ops/freeze_v10.py` 现算两项均为真 |
| ⑧ 三个 S8 常量抽成 `genetask/s8_contract.py` | `grep -rn "from reference" gateway/` → **0 处**；`ops/reports/s8_contract_parity.txt` 两侧快照 sha256 同为 `315a9ba4fa860b7c…` |

### 2.2 真跑（本轮唯二两处消耗真 API）

* **公开通道 8 个 run**（卡 X1）：`ops/reports/m6_public/x1_runs_summary.md`、
  `ops/reports/m6_public/{table_main.csv,table_a.csv,table_b.csv,records.json,scores/}`、
  `ops/reports/m6_public/v1_0_readiness_public.md`。
  同批还复跑了三控与破坏样本：`ops/reports/m6_public/x1_rerun2/`（含
  `s1_oracle_window_drift.json` —— 601/601 对上旧日志块、0/601 对上新块，
  **口径没变、是产物与窗的配对漂了**，别把重跑出来的 15/19 当新结论）。
* **从零演练 6 个 run**（卡 Y1，⑭）：`ops/reports/rehearsal_v2.md`、
  `ops/reports/i_rehearsal_v2/`（`records.json` / `summary.md` / `table_main.md` / `scores/`）、
  执行面落点 `/data/genebench_runner/rehearsal_v2/`（`setup.log` / `gw.log` / `healthz.json` / `runs/`）。
  **形态 ①（单机双容器）第一次端到端跑通** —— 网关在执行面本机 5 秒回 200，
  `channel=public`、`bind=192.168.1.219:18080`（不是 0.0.0.0）。

### 2.3 报告器口径（卡 C + 红队修复卡 V2.rt）

* 主表**固定十九列**：`scorer/report.py::MAIN_TABLE_COLUMNS` 现算 19 项，
  与裁定 ⑩ 逐字逐序相同。
* **取消聚合**：`AGGREGATE_COLUMN_NAMES` = `{aggregate, composite, effect, overall, score, total, 总分}`，
  主表里一个都没有；`effect` 不在主表列里（仍逐 run 留在结果库）。
* 空值词汇**五态**：数值 / `—` / `unobservable` / 空 / **`n/a`（不适用，V2.rt 新加）**。
* `ops/mk_metric_tables.py --check` **退 0「指标集逐项相等」**：agent **18**、跨阶段 **6**、逐阶段 **39**。

### 2.4 本卡自己做的（收尾卡 v2）

| 做了什么 | 证据 |
|---|---|
| **票据合并**：十个收件箱 → `ops/tickets.md` 新一节「2026-09-1x 收尾卡 v2（到可分发）」，**85 行**，编号 **N-571…N-652** 连号，另 3 行是既有票据（N-484 / N-518 / N-543）按既有体例写成「**N-xxx 更新**」；**合并掉 9 条重复**；出处列在说明末尾；十个 inbox 全部改名 `.merged` | `ops/tickets.md`、`ops/tickets_inbox/*.md.merged` |
| **HANDOFF §19.2**（§19 是卡 B 的，只追加、没动它一个字） | `ops/HANDOFF.md:1680` |
| **21 个批的表统一重出**（⑩ 的十九列口径）：每批 `table_main.{csv,md,tex}` + `metrics_agent.{csv,md}` + `metrics_stage.{csv,md}` | `ops/reports/<批>/`；驱动与逐批报告 `$GB/scratch/V2/{emit_tables.py,emit2.py,emit_tables_report.json,emit2_report.json}` |
| **逐批核过列集与顺序**：21 份 `table_main.csv` 的表头 `sort -u` **只有一行**，且与 `TABLE_A_INDEX_COLUMNS + MAIN_TABLE_COLUMNS` 逐字相等 | 同上 |
| **「结果库不动数据」的证据**：`table_a.csv` / `table_b.csv` **21 批逐字节不变** | `emit_tables_report.json` 的 `table_a_changed` / `table_b_changed` 全 `false` |
| **签字包重出**：`ITEMS` 扩 10 件（两张全量指标表 ×2 通道、`report_spec_v1.md`、`rehearsal_v2.md`、`push_instructions.md`）、`ROOT_ITEMS` 加 `genequant/MANIFEST.json`；**49 件、缺件 0、逐件 sha256 复核 0 条不符、全部 0400、`MANIFEST.json` 与 `README.md` 也是 0400、包里没有清单没记的文件、同名冲突断言仍在** | `ops/reports/signed/v1.0.15_r1.0.22/`、复核脚本 `$GB/scratch/V2/verify_signed.py` |
| **签字包新增 `axis_mentions`**：逐件登记「这份文件正文里提到了哪些版本轴」。**是如实登记不是门**（`VERSIONS.md` 本来就该列历次版本）。这一版 16 个件进 `mentions_other_axes`，逐条看下来**都有正当理由，没有一件是陈值** | `ops/reports/signed/v1.0.15_r1.0.22/MANIFEST.json` |
| **`RELEASE_MANIFEST` 重跑**：53 件、缺件 0、`--check` 退 0 | `RELEASE_MANIFEST.json` |
| **全量 pytest + `api_usage`** | `$GB/scratch/V2/full.log`、`$GB/scratch/api_usage/api_usage.md` |

**本卡新量到的五件**（票据 N-645…N-648 与 N-652，详见第三节与 `ops/tickets.md`）：
结果库的适配切片是陈的、七处 LaTeX `\label` 撞号（`table_a.tex` 四个批 + `table_b.tex` 三个批，已修）、
`--caption` 双重转义（登记）、`rehearsal_echo` 按批名出表会得到空表且不报错（已加守门）、
**卡号复用时 `mv <卡>.md <卡>.md.merged` 会静默盖掉上一轮那份**（N-652）。

最后一条是本卡**自己踩的**，值得写清楚：本轮的 `X1` 与 `Y2` 两个卡号更早一轮用过，
改名收尾时直接 `mv`，把上一轮那两份（6158 B / 7968 B）整个覆盖了 —— 文件还在、名字没变、
`git status` 里只显示一个 `M`，不看 diff 发现不了。**在提交之前**用 `git show HEAD:<path> >` 原样还原
（没用 `git checkout --`，那是禁令），本轮那两份改名 `X1-public.md.merged` / `Y2-export.md.merged`。
卡 Y1 当时就是为了躲同一件事才把收件箱叫 `Y1-rehearsal.md`，但那条经验没有被写下来 ——
现在有守门了（`ops/test_V2.py::test_改名没有盖掉更早一轮的merged`，判「HEAD 里已有的每个
`*.md.merged` 内容必须与 HEAD 逐字节相同」）。

---

## 三、BLOCKED_AWAITING_USER

> 下面五件，**每一件都只差一次裁定**，施工侧不能替签字人决定。
> 前三件挡着「外部用户能用」，后两件挡着「发布」。

### 3.1 公开通道带夹具的题一件都出不了集（N-605，卡 X1）—— 挡着 18 个 run 里的 10 个

两条判据在公开通道**同时成立且互为反面**：`genetask/packager.py::export_task`
要求夹具 sha **等于**题面 `inputs[].sha256`（N-84：题面就是夹具的身份）；
公开链防漏闸要求**任何一件都不等于**（相同 = 私有源漏进来了）。
公开夹具从公开 gold 切、题面 sha 是私有行情下标定的 —— **没有第三种状态**。

实测取证 `ops/reports/m6_public/x1_fixture_identity_block.json`：8 件夹具 / 5 道题，
公开侧 **0/8** 与声明相同、私有侧 **8/8** 相同（所以私有通道照常，这不是回归）。

* **A**：改公开题目录的 `task.yaml` 的 `inputs[].sha256`。不动冻结根，但两条通道的题面
  从此多一个字段不同**而没有任何版本号说得出这件事**。
* **B**：`export_task` 按通道走 + 给公开通道一个 `SET_VERSION_PUBLIC`。要动冻结根 →
  推任务集版本 → **再作废一次所有已发通行证**。
* **卡 X1 与本卡都倾向 B**，并建议那次重冻与别的待推项合并成一次 —— 1.0.15 的通行证刚发，
  重发代价最小的窗口正是现在。裁定 ⑭（只凭发布包 + 手册走通）与 ⑰（轴不一致则拒绝运行）
  都要求包内自洽，A 做不到。

### 3.2 剔答案面之后的公开树跑不了结算与出集（N-627，卡 Z）

`runner/f02/answer_plane_guard` 的 `ANSWER_PLANE_DIRS = ("reference","solution")` 是**命中即整棵删**，
`ANSWER_PLANE_NAMES` 含 `solve.py` / `scorer.yaml`。所以「零命中」与「树里有参考解」**互斥**。
剔完现查：树里还有 **65 个模块** import `reference/` 或 `scorer/`，断链的是结算
（`ops/score_runs.py`）、出表（`ops/mk_tables.py`）、出集与建题（`genetask/packager.py`）、
oracle / 控制组 / 适配赛道。跑得了的是网关、注入器与两臂运行器、13 条 harness、`genequant/`、全部文档。

三条路写在 `ops/reports/push_instructions.md §0④`：A 保持现状 + README 首页写明
「跑完自己算不出分」／ B 公开仓库也带答案面（红线 2 口径由用户改写）／
C 拆 `GeneBench` 与 `GeneBench-private` 两个仓库。**在裁之前推 A 是安全的**（推出去的东西不会变多）。

### 3.3 `ops/run_f02_a1.py` 的 `--provider-root` 在真跑路径上被静默忽略（N-611，卡 Y1）

模块常量 `PROVIDER` 写死私有 provider 的绝对路径；`main()` 里 `global RUN_ROOT, RESULTS`
把那两个按参数改写，**唯独 provider 没有**（`--dry` 走另一条路、**用**了参数）。
后果：**公开通道的真跑喂给容器的是私有 provider 树，而 P2 照样绿**
（跑批不设 `GENEBENCH_CHANNEL` 时期望值也是私有的，**两头一致地错**）。
证据是决定性的：`/data/genebench_runner/m6_public/runs/runs/s1-cor-01.strict.…/work/provider/features/`
下有 `bj*`（北交所）代码，而公开 provider 只有沪深。

**这影响卡 X1 那 8 个公开 run 的读数归属。** 修法一行，但修完要重跑 —— 那是预算与排期的决定。
同一道 `s1-cor-01` 的对照很直白：私有 provider **29 / 26 次调用**，公开 provider **101 / 101 次、两臂都撞闸**。

### 3.4 结果库里的适配赛道切片是陈的（N-645，**本卡新量到**）

卡 X2 按裁定 ② 重算了适配表，但**没有 `--ingest` 回结果库**。实测：

| | 结果库 | `ops/reports/adapt/records.json` |
|---|---|---|
| 轴 | `1.0.14 / r1.0.21` | `1.0.15 / r1.0.22` |
| `first_pass` | 14 | **17** |
| `correct_flag` | 5 | **6** |
| `failed` | **11** | **7** |

逐例差 **4 条**：`adapt-l1-08` / `adapt-l2-07` / `adapt-l2-08`（failed→first_pass）、
`adapt-l3-06`（failed→correct_flag）—— 正是裁定 ② 点名的那四例。
**后果**：裁定 ⑮ 的 `genebench export` 导出的是**结果库切片**，
外部用户拿到的适配读数因此是改正**前**的那一版（就是那个「偏低约 13 个百分点」的版本）。

本卡按任务书「结果库不动数据、只重出表」**没有改库**，并因此**没有**把
`mk_tables --table adaptation` 出的那张（从库来的、陈的）表落进 `ops/reports/adapt/` ——
那会在同一个目录里放两张数不一样的表。修法零真 API：
`$PY ops/reports/adapt/adapt_report.py score --no-pull --ingest`；
**注意 `DB.ingest` 对同主键内容不同是报错不覆盖**，所以要先决定是覆盖那 30 条还是换 batch 名。

### 3.5 Qwen 链路缺 key（N-586，卡 B）

f02 的 `~/.config/genebench/secrets.env` 里**只有 `DEEPSEEK_API_KEY`**（只判存在，没有读它）。
另两件前置齐：f02 到 `dashscope.aliyuncs.com` 通（401 / 0.17 s）、域名不在白名单（**现在就不该在**）。
缺一件即 BLOCKED：**没有伪造 key、没有往白名单加没人用的域名、没有跑那道真题**。

---

## 四、CONFLICT

| # | 两处原文 | 本轮怎么做的 |
|---|---|---|
| 1 | **裁定 ⑫**「逐阶段 **37** 条」 ↔ 卡 C 按入表规则在 `scorer/l3.py` 的实际产出上数出来是 **39** 条 | 按保守方向取 **39，不删**。多的两条是 S8 的 `orders_replayable` 与 `fills_linked_to_orders` —— `Audit` 四条子判据里的两条，v1 真的出数且进判据；删了等于让 Audit 的四条里有两条在表上没有落点。生成器与规格 §9 **逐项相等**（`--check` 退 0），agent 18 与跨阶段 6 与裁定逐字相符。**要压回 37 需要用户指定删哪两条。** |
| 2 | 任务书「改 `TABLE_A_COLUMNS`」 ↔ 契约「恒红恒绿不绕过」+「不重出各 batch 的表」 | 卡 C 把主表做成**另一张表**（`MAIN_TABLE_COLUMNS` + `main_table()`），`TABLE_A_COLUMNS` 一字未动，`ops/test_results_db.py` 的七条逐格 parity 全绿。**本卡重出 21 批之后这一条仍然成立**：`table_a.csv` / `table_b.csv` **逐字节不变**。副作用：`effect` 仍在 Table A 的**诊断** CSV 里（⑪ 说的是「不进发布表」）。签字包的 `README.md` 里写明了哪张是发布表、哪张是诊断表。 |
| 3 | 红队 finding 1 的两条要求自相矛盾（「有读数就短路返回 `None`」 ↔ 「那条 `valid + l3_pass=True` 的真记录必须判 `honest_halt`」） | V2.rt 按保守方向把顺序改成 ①`correct_handling` → ②短路 → ③`budget` → ④`rejected` → ⑤`unsettled`，两条要求同时成立。规格 §9.3 写的数据源就是 `record.correct_handling`，这个顺序与规格同源。 |
| 4 | 手册 **§9** 的并发档位（S7 1 / S4 ≤2 / 其余 ≤3） ↔ 手册 **§5.5**「并发数固定是 1，没有 >1 的合法值」 | 卡 Y1 **给了实测**：并发 2 撞了 `runner/c41/subnets.py::allocate()` 的跨进程竞态（`Pool overlaps`），且失败那一侧的清理把另一个 run 的 `run_root` 拿走。此后一律串行。**结论：在 `allocate()` 拿到跨进程锁之前，§9 那张并发表不该被当成可用的档位。** 两节口径要统一，**未做**（§9 是卡 B 的路径）。 |
| 5 | 任务书「答案面剔除后 `answer_plane_guard` **零命中**」 ↔ 手册描述的外部主流程**包含结算与出表** | 见 3.2。按零命中判据剔除，**没有**擅自把答案面放回去；把后果量化后摆在推送之前。 |

**三条用户已认可、不再提的**（N-130 档位用 18M 而非 6M；适配赛道题源现值 32 道而非 33 道；体量帽 700KB）
本轮没有新的分歧。

---

## 五、红线接触（B1–B7）

| 红线 | 本卡 | 本轮其它卡（汇总） |
|---|---|---|
| **B1** 无 sudo / 不改既有系统服务与定时任务 | **未触及**：没有 sudo、没有起停任何服务、没有改任何单元文件、没有碰定时任务 | 卡 B **改了** `~/.config/systemd/user/genebench-gateway.service` 的 `MemoryMax`（6G→12G，裁定 ⑨ 明令）——`--user` 单元、无 sudo、只改这一行、改前备份 `.bak.<UTC>`；卡 A **重起过**生产网关（按 HANDOFF §18.1 的方式，单元文件 md5 前后相同 `b079629f17578be2…`）。两处都已登记 |
| **B2** 答案面不上执行面 | **未触及**：本卡**没有向 f02 发过一条命令**，没有出集、没有 bundle、没有推 exec 树。签字包与各批的表里**没有** `reference/` `scorer/` `runs_in/` `gold/` `memory_probe_answers/` 的任何内容 | 卡 X1 走守门入口推了 exec 树与 4 个 bundle（落地扫描 0 命中）；卡 Y1 的发布包剔答案面后扫描 0 命中 / 1311 文件；卡 Z 两棵树各扫两遍（含 `.git`）**四遍全 0 命中** |
| **B3** 凭据不进仓库 / 日志 / 对话 | **未触及**：全程没有读、写、复制、打印任何 key；f02 的 `secrets.env` 一次都没碰。本卡新建的脚本、票据、报告里**没有 key 形态字面量** | 卡 B 查 `DASHSCOPE_API_KEY` 只用退出码与 `cut -d= -f1`（只打印变量名） |
| **B4** 题面改动必重冻记因 | **未触及**：逐条核过 `freeze_v10` 的 `CODE_FILES` / `CODE_DIRS` 与参考轴 —— 本卡改的 `ops/tickets.md` / `ops/HANDOFF.md` / `ops/archive_signoff.py` / `ops/reports/**` **一个都不在冻结根内**。两条轴的号与根**未变**（1.0.15 / r1.0.22，`--check` 退 0）。`pending_freeze_bumps` 为空 | 卡 A 的一次重冻是**本轮唯一**一次动冻结根，两条记因（why/what/scope/gates/consequence 五段齐）写进 `REFERENCE_REVISIONS`；r1.0.22 的 consequence 里按裁定单列「v1.0.14 签字包内的适配表偏低约 13pp」 |
| **B5** 网关只绑显式地址 / 端口 / 网段 / 出向白名单 | **未触及**：没改任何绑定、端口映射、compose 网段或 `MODEL_API_ALLOW`；本卡不起网关 | 卡 B 抬内存后两次重启确认 bind 仍 `192.168.1.48:18080`；卡 Y1 的演练网关绑 `192.168.1.219:18080`（显式 IPv4）；**本轮没有任何卡往白名单加过域名** |
| **B6** 跑批与真跑必须串行 | **未触及**：本卡没有任何打网关的批任务，未取 `gateway_lock` 也不需要 | 卡 X1 的 8 个真跑、卡 Y1 的 6 个真跑、卡 A 与 X2 的三次 oracle 跑批**全部在锁下**；卡 A 踩过一次「给 `run_oracles` 外套 `gateway_lock` = 同一把 flock 拿两次 = 永久阻塞」并纠正，已写进 HANDOFF |
| **B7** f02 上跑 runner 的 `umask 022` / `PYTHONDONTWRITEBYTECODE=1` | **未触及**：本卡没在 f02 跑任何东西。f01 侧所有远端命令 `umask 077` 开头、所有 python 调用带 `PYTHONDONTWRITEBYTECODE=1`、pytest 前 `ulimit -n 8192` | 打到 f02 的每条命令都以 `umask 022; export PYTHONDONTWRITEBYTECODE=1` 开头 |

**红线 5（`$GB` 全树 go-rwx）**：本卡在 `$GB` 下新建的只有 `scratch/V2/`，
现查 `find -perm /g+rwx -o -perm /o+rwx` 为空；签字包由 `report_io.secure_dir` + 0400 落盘；
`ops/tickets.md` / `ops/HANDOFF.md` / 各批的表写完显式 `chmod 600`（生成器自己也这么做）。

**内存纪律**：本卡没有名单内的重活（无 gold 重算 / IC-ε / oracle 矩阵 / materiality / 对账全量 / 打包），
**未取 `heavy.lock`**；出表与重打签字包都是秒级、峰值几十 MB。
全量 pytest 在 `flock pytest.lock` 内、`systemd-run --user --scope -p MemoryMax=6G` 封顶、
起之前 `free -g` 看 `available`（实测 28 G）。**没有在 f01 留常驻轮询循环** ——
轮询一律是远端 `for i in $(seq 1 50); do test -f X.done && break; sleep 10; done` 这种 ≤9 分钟即退出的短命令。

**git**：所有写操作在 `flock /data/shared/genebench/locks/git.lock` 内；只 `git add` 显式路径；
没有 `-A`/`-u`、没有 stash/reset/`checkout --`/rebase/amend/force。
共享文件 `ops/tickets.md` / `ops/HANDOFF.md` 的改动**只是追加**（新一节 / §19.2），
没有重排、没有整文件重写、没动别人那一段一个字。
工作树里别人的未提交件（`ops/reports/validator_parity.{json,md}`、未跟踪的 `paper/`）**一个没动、没提交**。

---

## 六、需要用户提供的（**一处列全**）

| # | 要什么 | 挡着什么 | 到位的判据 |
|---|---|---|---|
| 1 | **裁 3.1**：公开通道夹具身份闸走 A 还是 B | 10 个公开 run + 「公开包能不能自洽」（⑭ / ⑯ / ⑰） | 明确选一条；选 B 要接受再作废一次通行证 |
| 2 | **裁 3.2**：公开树跑不了结算怎么办（A 保持现状 / B 带答案面 / C 拆两个仓库） | 「外部用户能用」 | 明确选一条 |
| 3 | **裁 3.3**：`--provider-root` 那件是不是当挡发布的事修，修完要不要重跑 X1 那 8 个 run | 公开通道读数的归属 | 明确「修 + 重跑」还是「修 + 如实登记旧读数不可用」 |
| 4 | **裁 3.4**：适配赛道要不要回灌结果库（覆盖那 30 条，还是换 batch 名） | `genebench export` 导出的适配读数 | 明确选一条；零真 API |
| 5 | **`DASHSCOPE_API_KEY`** | 裁定 ⑲ 的那道真题 | `ssh finance01-ts 'ssh ljn@192.168.1.219 "grep -qE ^DASHSCOPE_API_KEY= ~/.config/genebench/secrets.env; echo $?"'` 回 **0**。**key 到位之前不要有任何代理去动 opencode 配置或往白名单加域名** |
| 6 | **`LICENSE` 的版权行** `Copyright [yyyy] [name of copyright owner]` | 不挡使用（`code_license_undecided` 判的是首行 SPDX，已闭）；挡「发出去的包不带占位符」 | `LICENSE` 附录里不再有 `<待用户填>` |
| 7 | **两份 `CITATION.cff` 的 `authors`**（本体一份、`genequant/` 一份）：family-names / given-names / affiliation（机构作者用 `name:`） | **带占位符的 CITATION 不要随发布包发出去** | 两份都不再有 `<待用户填>` |
| 8 | **`DATA_LICENSE` 的书面许可原文**（baostock 再分发） | **唯一未闭合的 blocker**，`releasable` 因它仍是 false | 原文放进 `ops/terms/baostock/permission/`，`DATA_LICENSE` 顶部状态改 `granted` |
| 9 | **推送本身**（`git push` 要 GitHub personal access token，作用域 `repo`） | ㉑ 的最后一步 | 两个远端**已经各有一次提交**（`GeneBench` `55ead485…`、`GeneQuant` `6eadb004…`），与本地两棵新 `git init` 的树**没有共同祖先**，普通 push 会被拒 —— 三条路写在 `ops/reports/push_instructions.md §0①`，**先看一眼那次提交里有什么再决定 force** |
| 10 | **裁「逐阶段 37 还是 39」**（第四节 #1） | 不挡发布 | 取 39（现状）或指定删哪两条 |
| 11 | **裁 `table_a.csv` 算不算发布件**（算的话从 `TABLE_A_COLUMNS` 删 `effect` 并逐批重出） | 不挡发布 | 明确一条 |
| 12 | **裁主表 S2 那一对列**（`Align`/`Adj` vs `CellAgree`，第七节） | 不挡发布；但有一条真记录 `CellAgree=0` 却在主表 S2 上显示 1/1 | 不动列（加脚注）或换列（改裁定 ⑩） |

**施工方没有、也不该有的**：GitHub token、`DASHSCOPE_API_KEY`、任何模型 key。
`push_instructions.md §1` 里写明了「不要把它写进这棵树里的任何文件」。

---

## 七、下一步（按顺序）

1. **用户裁第六节的 1–4 条**（四件都只差一次裁定，全部不需要新的真 API 预算，
   只有第 3 条的「重跑」需要）。
2. **`ops/push_exec_to_f02.sh --with-launch-data`** —— 下一个要在 f02 真跑的卡**必须先推**：
   f02 的 `exec/` 还没拿到卡 Y2 的机器标识（`runner/inject.py`），
   而 `genetask/s8_contract.py` **不在**该脚本的 `GENETASK_FILES` 白名单里 ——
   哪天要在 f02 起网关（形态 ①），得先往白名单加一行。
3. **落 N-578 的止血**：`rm -rf $GB/reference/tasks/v1.0-instances/s8-{cor,eco,ops,rob}-01`。
   S8 四道出集题的 gold 重出与公开通道的 S8 真跑现在都被它挡着，
   而发布验收绕不开 S8。正解（`sim.py` 把 `set_id` 传给 `build_engine`）派给能动 `gateway/` 的卡。
4. **公开通道实例 oracle 补齐**（N-582，26/112）——脚本已备好，**做之前先落第 3 步**。
5. **裁定 ⑲**：key 到位后建 `harnesses/opencode-qwen/`（`enabled: false` → `PENDING_CONFIGS`），
   flock 内把 `dashscope.aliyuncs.com` 追加进 `MODEL_API_ALLOW`，跑一道真题。
   **不许放宽 `assert_registry_sane` 的「所有 enabled 同一模型」**（那是 M7 的事）。
6. **把还红的那一摊派给对应的卡**（第一节 1.4 逐条列了），
   最大的一摊是 `ops/test_sim_factory.py` 那 23 条 + `test_public_acceptance` 1 条 —— 都指向 N-578。
7. **推送**（用户执行），推完重打一次公开包（`_staging_unpublished/` 里那份 README 是旧文本）。

---

## 八、21 条裁定逐条判

> 判据：**达成** = 这一条要求的事**全部**落地并有现算/真跑证据；
> **未达成** = 有一半没做到，哪怕另一半做得很好。**没有「部分达成」这一档。**

| # | 裁定 | 判 | 为什么 / 证据路径 |
|---|---|---|---|
| ① | `pin.PROVIDER_META_FILES` 加 `MANIFEST.sha256` 与 `build_info.json`；测试覆盖除这四个名字外的全部文件 | **达成** | 现算 `PROVIDER_META_FILES` = `{MANIFEST.sha256, build_info.json, files.sha256, manifest.json}` 四个字面名字。两条通道 P2 在**真树**上现算全绿（公开 2→0、私有 0→0），反向门验过。`genetask/pin.py`、`ops/test_provider_pin_channel.py`（新增八条）、`ops/reports/m6_public/`（f02 侧现算 `p2_green=true`） |
| ② | S6 占位串改成协议的 unresolved → 重出 S6 五题 gold → 重出四例 adapt oracle → 重算适配表；REVISIONS 记「偏低约 13pp」 | **达成** | 五份 `S6/*/solve.py` 现在 `from reference.artifact_schema import UNRESOLVED`（旧串只剩在注释里说明当初错在哪）；gold 现为 `[{"stage":"S5","artifact_id":"unresolved"}]`，两条通道各重出一次、5/5 零 finding；卡 X2 零真 API 重算，`ops/reports/adapt/table.csv` 现为 L1 8 / L2 9 / L3 6、ALL `resolved_rate` 0.7667、`failed` 7；记因在 `REFERENCE_REVISIONS` 的 r1.0.22 consequence 里单列。**⚠ 但结果库没回灌 —— 见第 3.4 节 / N-645，那是「导出」的问题不是「重算」的问题** |
| ③ | 修 `reference/s4_oracle_common.py` 与 S4-ECO 的 `solve.py`（候选全 NaN / 样本不足要有明确行为） | **达成** | `split_window()`（默认划分切得出两段就用它，切不出来按窗口交易日对半分并把 `holdout_rule=window_half` 写进 `payload.note`，连对半分都切不出 → 抛 `S4SampleTooThin`）；`bh_fdr_select` **先筛掉算不出 t 的候选**（原实现 `fillna(0)` 把「算不出」当「t=0」，它会挤进 BH 的分母）。四实例 4/4 零 finding，**基点 `s4-eco-01` 的 gold 两棵树上都与 v1.0.14 逐字节相同** |
| ④ | Slip 判据不改；指标规格里该项 role 由 `reported` 改成 `gate` | **达成** | 规格 §9.2 的 `S8 / SlipSelfConsistent` 一行 Role 写 `gate` 并注明「由 `reported` 改为 `gate`（④）」；`ops/mk_metric_tables.py` 与它一致（`--check` 逐项相等）；判据实现本来就在 `scorer/l3.py::compare_fill` 并进 `l3_pass`。**判据一个字没改**。`ops/specs/metrics_as_implemented_v1.md` 的「只报不判」措辞也已由 V2.rt 改口 |
| ⑤ | `instances_fingerprint` 进 `ROOT_FIELDS`；`v1.0-instances.yaml` 进 `freeze_v10.CODE_FILES` | **达成** | 现算两项均为真。连带三处也补了：`build_manifest` 默认算实例段、`manifest_root` 缺字段给明确报错、`frozen_ref` 现算比对补上实例指纹。**长期后果**（实例表改一行就作废所有已发通行证）已写进 HANDOFF |
| ⑥ | 先量 `s2-rob-04` 的 oracle 耗时；超了就给**该实例单独的**超时；不去掉窗口 | **达成** | `/usr/bin/time -v` 实测**墙钟 834 秒 / 峰值 RSS 220 MB / rc=0**，唯一的问题就是全局 600 秒、**不是** agent 墙钟。`ops/run_oracles.py` 加「题行 > 覆盖表 > 全局」三级 `oracle_timeout()`，**全局仍是 600（不放宽）**，只给 `s2-rob-04` 一条 1800。**窗口一动没动**。顺带修了失败分类器把秒数钉死成 `超时 600s` 的真 bug |
| ⑦ | 公开实例 O1 补到 **130/130**；无零 finding 的实例不进出集 | **未达成** | 私有 **108/130**、公开侧 oracle 补齐只到 **26/112**（卡 X2 三轮共等网关锁约 27 分钟没等到）。**口径要说清**：130 = 34 道出集模板的 112 个实例 + **6 道挂起探针模板的 18 个**，那 18 个按裁定 ⑦ 本来就不该进出集（E9c/E9d2 拦在落盘这一步，且跑 materiality screen 也解决不了 —— 那套 harness 结构上量不到那 6 个探针字段）。真实分子分母 **108/112**，差的 4 个全卡在 N-578。`ops/reports/probe_matrix_instances.md` 已把两类分开列、归因相反 |
| ⑧ | 三个 S8 常量抽成零 reference 依赖的契约模块；单机双容器形态端到端跑通；手册 §1.1 恢复 | **达成** | `genetask/s8_contract.py`（零依赖），值逐字节不变（快照 sha256 两侧同为 `315a9ba4fa860b7c…`）；`grep -rn "from reference" gateway/` → **0 处**，另有 AST 测试 + 干净子进程真 import 数 `sys.modules` 里 `reference.*` = 0。**形态 ① 第一次端到端跑通**（卡 Y1，网关在执行面本机 5 秒回 200，3 题双臂 6 个 run 全部真跑完并结算入库）。`ops/reports/rehearsal_v2.md` |
| ⑨ | 网关 `MemoryMax` 6G → 12G；S7 峰值内存进「排网格参考」 | **达成** | 单元文件现为 `MemoryMax=12G`（`--user` 单元、无 sudo、只改这一行、改前备份）；起停两次 `rc=0` / `NRestarts=0` / `MemoryMax(effective)=12884901888` / bind 仍 `192.168.1.48:18080`。换算式与档位进 `ops/HANDOFF.md §19` 与 `docs/OPERATOR_MANUAL.md §9`，**只有 S7 那一行有实测背书**（≈3.7 G 增量 → 并发 1），S4 ≤2 / 其余 ≤3 明确标「外推」。**但 §9 与 §5.5 的口径冲突未收**（第四节 #4） |
| ⑩ | 主表固定十九列 | **达成** | `scorer/report.py::MAIN_TABLE_COLUMNS` 现算 19 项，与裁定逐字逐序相同：`SR / P@1 / $` + `Cov,Prov｜Align,Adj｜Fid,Decl｜IC-agr,Set｜Sig,ρ̄｜W-agr,Cons｜ε-agr,Ledger｜Audit,Ovr`。**本卡把 21 个批的表统一重出并逐批核过**：21 份 `table_main.csv` 的表头 `sort -u` 只有一行 |
| ⑪ | 取消聚合；effect 留结果库不进发布表；逐指标闸门条件；四类显示 `—` | **达成** | 不出总分（`AGGREGATE_COLUMN_NAMES` 七个名字，主表里一个都没有）；`effect` 不在主表与两张全量指标表里、仍逐 run 在结果库；闸门条件逐指标写在规格 §9 与 `ops/reports/report_spec_v1.md`；四类（拒绝 / 诚实终止 / 未结算 / 预算截断）各造一条夹具、三种格式各断言一次。**红队抓到 `honest_halt_rate` 结构性恒 0 并由 V2.rt 修好**（顺序改成诚实终止判在最前 + 有读数就短路），全库计数由 `honest_halt 0` 变成 `honest_halt 1 / budget 26` |
| ⑫ | Role `effect`→`fidelity`；agent 18 项与阶段（六条跨阶段 + 37 条）由生成器从结果库出；指标集与规格逐项相等 + 测试 | **达成（逐阶段取 39，CONFLICT 已标）** | `ops/mk_metric_tables.py --check` **退 0「指标集逐项相等」**，agent **18**、跨阶段 **6**、逐阶段 **39**。`effect` 作为 Role 一处不留。**39 vs 37 见第四节 #1** —— 按保守方向不删，等用户裁 |
| ⑬ | 核六列可算（Prov / Decl / Set / W-agr / Ledger / Ovr），不可观测标 `unobservable` | **达成** | 六列全在主表；`Decl`（契约必填声明完整率）与 `Set`（payload 依赖设定申明率）新补在 `scorer/l3.py::declaration_metrics`、由 `score_run` 贴进 `correctness`（**只报不判**，不动 `l3.score` 与 `l3_pass`）；`Ledger` 从 `probe_states` 三态读；另补 `ρ̄`。`m6_all` 上六列的取值里数值 / `—` / `unobservable` 三种都出现过，**没有一格靠 0 糊过去**。**覆盖偏薄**：当前发布轴的公开切片上只有 `Prov` 与 `Ovr` 有数（那几个阶段公开通道一道题都没跑），已登记 |
| ⑭ | 从零演练：干净机器只凭发布包 + 手册走通七步；每处手册失败修手册 | **达成** | `/data/genebench_runner/rehearsal_v2/`（自己的解释器环境 / GENEBENCH_ROOT / 网关 / run 根）走完七步，3 题双臂 **6 个 run 全部真跑完**、结算 6/6、入库 6 条、出十九列主表。**findings 17 条（6 条 block），当场修了 11 条文档**。`ops/reports/rehearsal_v2.md`、`ops/reports/i_rehearsal_v2/`。建镜像所需外网已记录（`docker build --no-cache` 41.4 秒，只要 `registry.npmjs.org`） |
| ⑮ | `genebench export` / `merge`（四轴一致才合、轴不一致即拒）；run_id 加机器标识；两台机器导出合并无冲突的测试 | **未达成** | 代码全在并有 22 条测试（`ops/genebench_cli.py`、`ops/test_export_merge.py`；`merge` 轴不一致退 3、篡改退 5、同主键冲突退 4，逐条实跑过）。**但机器标识没有被任何真记录验到**：`runner/inject.py` 现在一定拼 `@<machine_id>`，而 2026-09-11 落地的 `i_rehearsal_v2` 6 条 run 的 `run_id` 仍是无 `@` 段的旧形态、`inject.json` 里也没有 `machine_id`，**全库 `machine_of()` 返回 `None` 的是 132/132**。export 时机器标识是**现场算的**，不是从记录来的 —— 「两台机器天然不撞」在今天的数据上**没有被验证过**。要查演练走的是不是发布包里旧版的 `inject.py`（N-641） |
| ⑯ | 盘点发布包体积；gold 超 5GB 则只发子集并记 sha；最低 RAM / 磁盘 / docker 版本写手册首页 | **达成** | 手册 §0.0 + README §1.5 逐行给数**并给出处**；gold 全量 **14.90 GiB** 超线 → 只发 **41 件 / 152.0 MiB** 的子集（全量的 1.00%），逐件 sha256 + 清单指纹在 `ops/data_cards/gold_subset_v1.md`，机读清单 `ops/reports/i_rehearsal_v2/gold_subset.json`；`RELEASE_MANIFEST.json` 新增 `package` 段（`parts` / `totals_bytes` / `gold` / `gold_subset_source` / `min_spec` / `inventory_source`）。必发合计 **1.10 GiB**、加答案面 **1.52 GiB** |
| ⑰ | 任一轴与 RELEASE_MANIFEST 不一致则包拒绝运行；导出的每条结果带四轴 | **达成** | `ops/genebench_cli.py axes` **退 0**（一致）；入口自检覆盖 `genebench` 每个子命令与 `ops/run_joblist.py`（含 `--dry`），不一致退 3 并说清怎么修；`GENEBENCH_RELEASE_MANIFEST` 只换路径不是开关。导出**前**逐条核实每条记录带齐四轴，缺一就不导。**红队另抓到 `VERSIONS.md` 正文漏推**（清单/常量/表脚注/README/CHANGELOG 全跟了，唯独这份「四条轴的权威文档」停在上一版），V2.rt 补了 `--check` 先比正文 |
| ⑱ | secrets 格式与位置写进手册（每配置一把 key、边车注入、容器不可见） | **达成** | 手册 **§2.4.1**：位置 / 0600 / 每配置一把 key（`api_key_env` 写的是**变量名**）/ 三段注入链 / 一条可粘贴的验证命令**与实测输出**（边车是 `${GENEBENCH_MODEL_API_KEY}` **引用**、任务容器是占位串） |
| ⑲ | opencode 启动脚本改用 Qwen 验链路一道真题；Qwen Code 不做；手册与 `harnesses/README` 相应改 | **未达成（BLOCKED）** | f02 上**没有 `DASHSCOPE_API_KEY`**（只判存在，没有读它）。**没有伪造 key、没有往白名单加没人用的域名、没有跑那道真题**，`harnesses/opencode-qwen/` 不存在、`harnesses/opencode/config.yaml` 的 `model` 仍是 `deepseek-chat`（改它会让 `assert_registry_sane` 的「所有 enabled 同一模型」当场红，而**那条断言不许放宽**）。**文档侧已做完**：切换的完整判据在 `harnesses/opencode/README.md §9`、`harnesses/README.md §7` 写明「为什么只有一个模型」+ Qwen Code 不做。见第 3.5 节 |
| ⑳ | 代码许可 Apache-2.0 填进 LICENSE 与 CITATION.cff；作者 / 单位 / 地址维持待填 | **达成** | `LICENSE` 首行 `SPDX-License-Identifier: Apache-2.0` + 全文（取自本机 `/usr/share/common-licenses/Apache-2.0`，sha256 `cfc7749b…3d30`，**逐字未改** —— 改过的 Apache-2.0 不再是 Apache-2.0，而合规工具按 SPDX 认它、不逐字比对）；`CITATION.cff` 的 `license: Apache-2.0`；`RELEASE_MANIFEST.license.code = {spdx: Apache-2.0, decided: true}`。**作者 / 单位 / 版权行维持 `<待用户填>`，一个字没编** |
| ㉑ | 协议工件整理成 `genequant/` 子树；两个 URL 填进 RELEASE_MANIFEST 与 CITATION.cff；README clone 改真地址；`no_clone_url` 闭合；准备好可推的树（答案面剔除后再核零命中）；**推送由用户执行** | **达成** | `genequant/` **25 件**（其中 **22 件是原件的逐字节副本**，协议内容一个字节没改），来源逐件记在 `genequant/MANIFEST.json`；本体以 sha 钉住（`RELEASE_MANIFEST.genequant.manifest_sha256 = c145af300c4c3c2e…`，三棵树上现算逐字相同），**测试两个方向都查**（副本 == 原件 == 清单记的 sha）；两个地址落进四处、唯一定义处 `mk_release_manifest.REPOSITORIES`，一处分叉就红；`no_clone_url` **已闭**；两棵可推的树在 `$GB/release/trees/{genebench,genequant}/`，**答案面剔除后各扫一遍、`git init` 之后含 `.git` 整棵再各扫一遍，四遍全 0 命中**；`ops/reports/push_instructions.md` 给了两条 remote add + push、推之前四件确认、推完三件事、四条「不要做」。**未推送、未 `git remote add`**（`$GB/repo` 的 `git remote -v` 现在仍是空的）。**⚠ 这棵树跑不了结算 —— 见第 3.2 节** |

### 小结

**达成 18 条**：① ② ③ ④ ⑤ ⑥ ⑧ ⑨ ⑩ ⑪ ⑫ ⑬ ⑭ ⑯ ⑰ ⑱ ⑳ ㉑。
**未达成 3 条**：**⑦**（实例补到 130/130 —— 实为 108/112，差的 4 个卡在 N-578，公开侧只到 26/112）、
**⑮**（机器标识没有被任何真记录验到，全库 132/132 为 `None`）、
**⑲**（缺 key，真题没跑）。

**一条要单独说**：② 判「达成」是因为裁定原文那四件（改根因 / 重出 gold / 重出 oracle / 重算适配表）
全部做完了；但**重算的结果没有回灌结果库**，而 ⑮ 的导出走的是结果库 ——
这件事本身不在 ② 的字面里，所以没算 ② 未达成，而是单独立在第 3.4 节与 N-645。
**不要因为 ② 是绿的就以为导出的适配数是对的。**
