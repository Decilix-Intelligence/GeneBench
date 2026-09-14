# GeneBench v1.0.16 最终卡报告（2026-09-12 收口）

> 这是 v1.0.16 这一轮的**最后一份报告**。用户裁定：**本轮之外发现的一切问题，
> 一律登记进 `ops/reports/known_limits_v1.md`，不修、不开新票。**
> 票据合并在 `ops/tickets.md`「最终卡（收口 + 发布）」一节（N-653 … N-702），
> 交接在 `ops/HANDOFF.md` §19.3。
>
> **一句话结论**：`releasable=true`、两份签字包都在、公开通道 18 个 run 全部跑在真公开
> provider 上、公开树带答案面且能跑结算 —— **代码与文档这一侧已经可以发**；
> 卡在用户那一侧的是两件：**推送本身要用户本人点头**，**Release 附件的再分发依据要用户定**。
> 两个公开远端在收口时**仍是 GitHub 自动生成的初始提交**，即本轮没有人推过。

---

## 一、状态表 + f01 全量数字 + 真 API 用量

### 1.1 这一版是什么（收口时现查，不是抄的）

| | |
|---|---|
| 任务集（私有） | **1.0.16**，根 `d9ebd5412ac4cc7e4569ae41887bff5fd0a40ec59e78baad34ccf5086550fc63` |
| 任务集（**公开**，裁定 ①） | **p1.0.0**，根 `3e5ab441a991c4115a6c0fb988715f583e22ee303f582f1302fd3197fb183538` |
| 参考面 | **r1.0.23**，根 `dddabe440163b36ef678dee314b29604de3292470dd88fc07aa5162dc9d7cfb2` |
| 协议轴 | `geneprotocol_v1@<逐 run 反算，见 VERSIONS.md §1.3>` |
| 出集 | 34 题 / 挂起 6 题；**40 模板 / 130 实例** |
| 签字包（私有） | `ops/reports/signed/v1.0.16_r1.0.23/` —— **33 件**，逐件 0400，缺件 0 |
| 签字包（**公开**） | `ops/reports/signed/public_vp1.0.0_r1.0.23/` —— **27 件**，共有 8 件与私有那份逐字节相同 |
| 发布清单 | `RELEASE_MANIFEST.json`：`releasable=**true**`、`missing=[]`、五条 blocker **全 `satisfied`**、`--check` **退 0** |
| 票据 | 到 **N-702** |
| HEAD（本报告提交之前） | `cd711c6` |
| 两个公开远端 | GeneBench `55ead48588dd1ddfff7d62e9ce6bf94401424124` / GeneQuant `6eadb004104aa4564e60db70dff40445c836b817` —— **均为初始提交，本轮未推** |

五条 blocker 的现状（`RELEASE_MANIFEST.blockers`，`ops/test_h.py` 逐条核过证据路径**真的在盘上**）：

| blocker | satisfied | 现状 |
|---|---|---|
| `data_license_text` | **true** | `DATA_LICENSE = granted`；**许可方出具的正文仍未入库**，§2.1 是一处显式占位 |
| `no_clone_url` | **true** | 两个地址已定，README 与 `CITATION.cff` 两处一致 |
| `frozen_artifacts_missing` | **true** | 全部到位 |
| `public_channel_zero_runs` | **true** | `m6_public`：**18 个有 run 的行 / 共 18 行** |
| `code_license_undecided` | **true** | `SPDX-License-Identifier: Apache-2.0`，版权行 `Copyright 2026 Decilix Intelligence` |

### 1.2 f01 全量 pytest（阶段收口，本卡跑）

    flock /data/shared/genebench/locks/pytest.lock \
      systemd-run --user --scope -p MemoryHigh=5G -p MemoryMax=6G \
      $PY -m pytest ops/ -q

跑了**两次**：收口改动**之前**一次、本卡提交**之后**复跑一次 —— 两次的红**是同一批六条**。

| | passed | failed | skipped | xfailed | 耗时 | 日志 |
|---|---|---|---|---|---|---|
| 收口前（12:05Z） | 4428 | 6 | 32 | 1 | 1267.89 s | `$GB/scratch/FINAL/full.log` |
| **终值**：本卡提交后（12:42Z） | **4443** | **6** | 32 | 1 | 1205.64 s | `$GB/scratch/FINAL/full2.log` |

两次相差的 15 条 passed 就是本卡新增的 `ops/test_final.py`。
**六条红一条都不是本轮改动引起的**：

| 测试 | 条数 | 归属 |
|---|---|---|
| `ops/test_lake_baseline.py`（三条） | 3 | **外部数据漂移** —— 湖里 `stock_st` 新近停更（基准 8 张 → 现场 9 张）。宿主上别人的 ETL 的事实变化，我们的题面与 gold 冻在 `snapshots/` 里，不读活表 |
| `ops/test_env.py::test_no_api_key_material_in_run_dirs` | 1 | **别人的 scratch** —— 命中全在 `$GB/scratch/Y1/rh2_operator/` 与 `rh2_stage/`，是把仓库整棵拷进 scratch 带过去的**测试文件自身的夹具字面量**，不是真凭据 |
| `ops/test_underdetermination_guard.py::test_unattributed_residual_is_documented_in_all_three_places` | 1 | **别人未提交的改动** —— 第三处出处 `ops/reports/ambiguity_impact_2.2b.md` 此刻在工作树里带 ` M`（契约 C：不动别人的半成品） |
| `ops/test_wrt.py::test_rebudget只动没跑过的行` | 1 | **清单比裁定 ⑮ 旧** —— `job_id` 缺 `@<机器标识>` 后缀，卡 G1 已登记（N-619 / N-669），本轮改动之前单跑也红 |

对照：卡 H 在本轮中段跑的那次是 **4400 passed / 6 failed**（同样六条）；
4400 → 4428 的 28 条来自卡 P 的 `ops/test_p.py`，4428 → 4443 的 15 条来自本卡的 `ops/test_final.py`。
**本轮 `ops/test_gateway.py` 与 `ops/test_universe_reconcile.py` 一条都没红** ——
任务书口径里它们属「外部进程持湖写锁 / 网关端口」那一类，这次恰好没撞上，如实记。

### 1.3 真 API 用量

`$PY ops/api_usage.py`（机器统计，来源 `ljn@192.168.1.219:/data/genebench_runner`）：

**5,036 次真调用 / 133 个 run**，落盘 `$GB/scratch/api_usage/api_usage.{json,md}`。

* 本轮新增 **968 次 / 18 run / $16.2788**，**全部**在卡 G1 的公开通道重跑上（裁定 ②）。
* 差值说明：上一轮记的是 4,445 次 / 123 run；`5036 − 4445 = 591 = 新增 968 − 移出统计的
  8 个受污染 run 的 377`（那 8 个 run 目录已挪进 `polluted_private_provider_20260912/`）。
* 卡 G1 的预算纪律：先跑 1 题双臂（`s1-cor-01`，52 次 / 约 11 分钟）外推整卡 **~1390 次**
  （< 1500 阈值，未触发停下报编排方），实际 **968 次**，低于外推。
* **其余七张卡真 API 调用合计 0 次**（F1 / F2 / F3 / G2 / H / P / 红队最终轮都没打网关）。

---

## 二、本轮完成项与真运行证据路径

按裁定编号分组；每条给「做了什么 → 证据在哪」。

### 2.1 分轴与冻结（①③⑤⑦，卡 F1，提交 `c563152`）

* 公开通道有了**自己的** `SET_VERSION_PUBLIC`（`p1.0.0`）与自己的清单；公开根在私有
  `ROOT_FIELDS` 之上多一段 `channel_fixtures`；`export_task` **按通道**处理夹具身份 ——
  私有**逐字节不变**（新旧 packager 各导一次、逐文件 sha256 相同），公开把盘上真值写进
  X 面 `task.yaml`，5 道带 `inputs` 的题第一次出得了集。防漏闸**反过来用**（公开夹具字节
  == 私有声明值即当场红，实测红）。
  → `ops/reports/f1_private_export_bitwise.md`、`ops/manifests/v1.0-smoke-public.json`
* 实例 ID 一律带参数指纹后缀（基点亦然）；`sim_factory.task_dir` 与**会话键**加 `set_id`；
  `build_engine` 的 `set_id` 必填无默认。变体 130 个号一个没动，只有 40 个基点后置发新号。
* 适配切片 `--ingest` 回库：旧 30 行标 `superseded`（**不删行**），新 30 行记 1.0.15 / r1.0.22，
  库里 17 `first_pass` / 6 `correct_flag` / 7 `failed` 与报告逐个对上。
  → `ops/reports/adapt/records.json`、`/data/shared/genebench/results/v1/results.jsonl`
* `freeze_v10.REVISIONS` 从死表复活，v1.0.6 至今逐条补录 10 条，两表升序、末条 == 当前号；
  `CHANGELOG.md` 由它重出（现为「任务集 1.0.16 / 参考面 r1.0.23」）。
* 测试 `ops/test_f1.py`（18 条），连带跟改五个测试文件，151 passed。

### 2.2 报告器三处 + Qwen（⑥⑧，卡 F2，提交 `a7f45c4`）

* 主表 S2 的保真列 `Align` → `CellAgree`（表头 `Cell%`），`Adj` 留作有效性列；
  换列理由由**一条真记录**钉住（`Align=1.0` 而 `CellAgree=0.0`，字段全映对了一个格都没对上）。
  → `ops/reports/i_rehearsal_v2/scores/s2-cor-01.strict.cfg-codex-deepseek.r02.score.json`
* `table_a` / `table_b` 标诊断件：44 份 `*.NOTE.md` 已回填；`RELEASE_TABLES`（10 件）/
  `DIAGNOSTIC_TABLES` 两个常量 + `DIAGNOSTIC_NOT_RELEASE` 一道门。**`effect` 列保留**。
* 阶段指标：生成器与规格**本来就都是 39 条**且 `--check` 逐项相等，只补题注，**一行没增删**。
* Qwen 按裁定 ⑧ 跳过并记已知限制（**没有**往 `MODEL_API_ALLOW` 加 `dashscope.aliyuncs.com`）。

### 2.3 许可与版权（⑨⑩，卡 F3，提交 `bfeaffe` + `6581fb6`）

* `DATA_LICENSE` 顶部 `pending_license_text` → **`granted`**，新增 §2.0 授权摘要；
  §2.1 留一处醒目占位「⚠ 正式文本待替换」；`ops/terms/baostock/permission/`
  **刻意保持不存在**（目录非空的唯一含义是「正文到了」）。
* 发布清单的许可段把**授权**与**正文**拆成两个字段（`official_text_in_repo` 现算目录，今天 `false`）。
* `LICENSE` 版权行 → `Copyright 2026 Decilix Intelligence`（Apache-2.0 正文与附录模板行逐字未动）；
  `CITATION.cff` 新增 `repository`（GeneQuant），`authors` **维持 `<待用户填>`**。
* 五条 blocker 全闭，`releasable` 翻 **true**。

### 2.4 N-611 与公开通道 18 个真 run（②，卡 G1，提交 `a233a96` / `c9d7cd4` / `c356494`）

* 三处一起修：`ops/run_f02_a1.py` 的 `--provider-root` 真跑路径生效（`provider_default(channel)`
  现算）；**`ops/run_joblist.f02_run_cmd` 那条 ssh 命令此前一个字都没提通道**（这才是它能
  「静默」的真正原因 —— f02 上 provider 默认与 P2 期望值**两头一起回落到 private**，两头一致所以全绿）；
  注入器新增 **P7e**（站在 `work/` 这一侧查**结果**，不是查调用方传进来的路径）。
* **18/18 跑在真公开 provider 上**：`work/provider` 现算根 `561348660a3175b1…`，
  `features` 下 `bj*` **0 个** / 总数 3575（私有那份是 336 / 3911）。
  → `ops/reports/m6_public/g1_public_provider_rerun.md`、`ops/reports/m6_public/x1_runs_summary.md`
  → run 目录：`$GB/runs_in/m6_public`（现行）、`$GB/runs_in/m6_public_polluted_20260912`（证据，**不删**）
* 重出主表 / Table A / B / 两张全量指标表 / 三控 / 破坏样本 / 验证验证器 / 就绪报告 / X1 逐 run 实况。
* 真 API **968 次**，逐 run 明细见本报告 §一 1.3 与卡 G1 的输出。

### 2.5 红线 2 改口径 + 公开树（④，卡 G2，提交 `3ed93f6` / `b547983` / `781e394`）

* `answer_plane_guard --mode container`：读 compose 的**三种** bind 写法 + run dir，
  判据与树模式**同源**，**命中即拒绝启动、一个字节不删**，reason 码与树模式分开。
* 公开树重打：2,171 件 / 27 M，**带**全部答案面，**只剔四类**；`EXCLUDED.txt` 逐条写明。
* 验收「公开树能跑结算」：树内 `sys.path` 只指树，141 个 import `scorer`/`reference` 的模块
  **断链 0**，树内 320 passed。→ `ops/reports/g2_public_tree_scoring.md`
* 证据：`$GB/release/trees/scan_genebench_container.txt`（正例绿 + 两个反例红 —— **门有牙**）、
  `scan_genebench_tree.txt`（树口径 95 条命中，**预期内，不是红**）。

### 2.6 签字包两份 + 发布清单终核（卡 H，提交 `dcc881a` / `ed29e02`）

* `ops/archive_signoff.py --channel private|public|both`（默认 both = **各出一份，不是一份混的**）；
  归档清单劈成 `SHARED_ITEMS` + `PRIVATE_ITEMS` + `PUBLIC_ITEMS`，**`ITEMS` 并集不变**。
* 复核 `$PY $GB/scratch/H/verify_signed.py`（逐件 sha256 / 0400 / 缺件 / **通道纯度** /
  共有件逐字节 / 互指）：**红 0 条**。
* 发布清单终核：五条 blocker 全 `satisfied`、`missing=[]`、`--check` 退 0。

### 2.7 红队最终轮四条 block + 三条 major（提交 `73bf156`，264 文件）

| | 做了什么 | 证据 |
|---|---|---|
| block 1 | 公开通道结算的**三处**默认值改成通道感知（标定 / 网关日志 / 题集根）+ 混通道拦截 | `ops/reports/m6_public/summary.md`（顶部四行通道口径）、`ops/test_rtfinal.py` |
| block 2 | `VERSIONS.md` 重出轴表与 §4 历史表、新增 §1.1a 公开轴一节 | `VERSIONS.md` |
| block 3 | 21 个批的主表 × 3 格式 + 84 件指标表重出（表头全部 `Cell%`） | `ops/reports/*/table_main.{csv,md,tex}` |
| block 4 | 重出签字包 `v1.0.16_r1.0.23/`（**当时 49 件** —— 卡 H 随后按通道拆成私有 33 + 公开 27，见 §2.6）；旧包保留并加 `SUPERSEDED_NOTE.md` | `ops/reports/signed/` |
| major 5 | 发布清单重出（`status_now` 8/18 → **18/18**；5 个手写件 sha 重新对上） | `RELEASE_MANIFEST.json` |
| major 6 | `axes` 加 `public_set_version` / `public_set_root` | 同上 |
| major 7 | `ops/freeze_v10.py --check-all`（三条轴一起核） | `ops/freeze_v10.py` |

**block 1 的重结算结论值得单独说**：`m6_public` 的**主表与 Table A 逐字节相同**
（`l3_pass` / SR / pass@1 一个都没翻）—— **已发布的公开读数不必撤回**；
变的是 3 条记录的 4 个诊断值（s5 两臂的 `tau`、s4-cor-01.open 与 s7-cor-01.open 的 `max_band_ratio`）。
旧 18 行标 `superseded`，新 18 行入库。

### 2.8 推前扫描与两棵树（⑫⑬，卡 P，提交 `edb97db` / `78be588` / `cd711c6`）

* ⑬ 四项：凭据文件名 **0**、记忆探针目录 **0**、scratch 与 run 目录 **0**；
  凭据内容 3 条逐条核实**全不是凭据**。→ `ops/reports/release_scan_final.md`
* ⑫ 字样扫描：两棵树 2,194 个文件逐行扫过，**文件内容里署名形态 0 条**；
  技术事实 430 条按五类保留并逐条写明「删了会变成什么假话」。
  **`.git` 元数据里抓到并删掉 1 条真署名**（GeneQuant 旧提交的作者是 anthropic 域占位邮箱 ——
  文件内容扫描看不见它，单独核提交元数据才抓到；该旧提交**从未推送**，无对外痕迹）。
  → `ops/reports/release_scan_claude_mentions.md`
* 两棵树：`$GB/release/trees/{genebench,genequant}/`，各**单次提交、新历史、无 remote**，
  作者与提交者均为 `深情代码大师 <2994718175@qq.com>`，message 恰为
  `GeneBench v1.0.16 release` / `GeneQuant v1.0 release`。
  → `ops/reports/push_result.md`

### 2.9 本卡（收口）

* 八个收件箱（F1 / F2 / F3 / G1 / G2 / H / P / RT-final）并入 `ops/tickets.md`
  「最终卡（收口 + 发布）」一节，编号 **N-653 … N-702** 连号，既有票据十条写成「N-xxx 更新」，
  重复条目三处合并；八个收件箱改名 `.merged`。
* `ops/HANDOFF.md` 追加 **§19.3**（15 条裁定速判表 + 红线 2 口径改写 + 还挡着什么 + 接手先跑的三条）。
* 本报告 + `ops/reports/known_limits_v1.md` 终态盘点 + `ops/test_final.py`。

---

## 三、BLOCKED_AWAITING_USER

> 两条，**都不是技术不通，是「不该由代理替用户按下去」的那一类**。

### 3.1 推送两棵树到公开 GitHub（裁定 ⑪ / 票据 N-635）

* **技术前置全部验过**：`ssh -T git@github.com` 实测回 `Hi JensenLuan!`；两个远端可达且
  各只有一次 GitHub 自动生成的初始提交；两棵树的身份 / message / 单次历史 / 扫描证据全部就位。
* **卡在哪**：`git push --force` 到公开 GitHub 是**对外可见且不可撤**的发布
  （force 掉的 commit 在 GitHub 上仍会留存一段时间，推上去的答案面收不回来），
  而收到的「可以推、允许 --force」是**经编排方转述**的用户裁定 —— 发布公开内容需要**用户本人**确认。
* 两棵树**故意没加 remote**：加了就等于把不可撤的动作留成一次手滑的距离。
* **照抄即可的四条命令**在 `ops/reports/push_result.md` §3（加 remote → peek 远端初始提交 →
  `push --force` → `ls-remote` 核对）。
* **两个方向**：① 用户本人确认后立刻推；② **先不推**，等 3.2 的许可定了、附件真发得出去、
  README 与 RELEASE_MANIFEST 跟着改完、两棵树重打之后一次推干净。
  **倾向 ②** —— 现在推的话，README §1.5 与快速开始会把读者指向一个发不出去的 Release 附件，
  中间这段时间文档在对外说一件做不到的事。

### 3.2 公开 provider 包里 `instruments/` 的再分发依据（裁定 ⑭ / 票据 N-690）

* 包里 `qlib_provider/instruments/{all,csi300,csi500,csi1000}.txt` 与 `universe/` 来自**私有**
  `universe_pit`（湖 `index_member_all` 派生，上游 **tushare**），不是 baostock 的产物
  —— baostock 没有指数成分历史。
* **仓库自己预先写死了这件事**：`DATA_LICENSE` **§5**「它的再分发**不在 baostock 许可的射程内**
  —— §2 的授权**不覆盖这一块**，**正文到位之后也不会**覆盖 […] **发布前须单独确认**」；
  同一句话也在包自己的 `MANIFEST.universe_definition_note` 里。
* 裁定 ⑨ 给的授权范围是「再分发**派生日线数据**」，指数成分历史不在射程内。
* **两个方向**：① 取得上游（tushare 侧）许可 → 原样发包；
  ② 不发 `instruments/`，改发重建脚本 → 公开通道的 csi300 / csi500 / csi1000 三个宇宙用户复现不出来，
  只剩 `all`，**而 gold 子集正是按这三个宇宙算的**。
  **倾向 ①**，但**必须由用户定**。
* **另有第二个独立障碍**（与许可无关）：两个附件本身**都还不存在可发布的版本** ——
  公开 provider 包只有 2026-09-06 那个 `_staging_unpublished` 的旧包（自己标着 `publishable:false`），
  `release/public_v1/` 不存在；**gold 子集包从来没打过，也没有打包脚本**（N-691 / N-692）。

---

## 四、CONFLICT

本轮各卡按「两处原文引用、按保守方向做、标 CONFLICT」处理的规格冲突，逐条汇总：

| # | 冲突 | 处置 |
|---|---|---|
| 1 | 任务书 ⑤「新行记 r1.0.22」 vs `adapt_report.axes_for` 的实现「取 freeze 当前值」（推号后是 r1.0.23） | 按裁定钉成 **1.0.15 / r1.0.22**（那才是这批数**重算时**的版本），`axes_source` 写成 `pinned:…`**不假装是读出来的**；根治登记为 N-654 |
| 2 | 任务书 F2-2「把 `table_a.csv` 从发布件清单里拿掉」 vs 既有注释「两者都归档，包内 README 说清哪张是哪张」 | 核过之后**发布件清单里本来就一件结果表都没有** —— 做的是把裁定变成**可执行的门**（`DIAGNOSTIC_NOT_RELEASE`），而不是把证据删掉；归档照旧收，包内逐件标明 |
| 3 | `ops/test_env.py::test_license_state_matches_whether_the_text_exists`「granted ⇒ `permission/` 非空」 vs 裁定 ⑨「正文留显式占位，不许伪装成已入库」 | **翻 granted，但不制造任何文件**去让那道锁变绿。代价是那一条红着，收益是仓库里没有一处在暗示「正文已入库」。分叉逐字写进 `DATA_LICENSE` §2.3 |
| 4 | 任务书 G2「两个推送脚本的树扫描要么改成扫挂载面、要么保留为第二道 —— 你定」 vs 红线 B2 原文 | **两道都保留**，容器口径为主、树口径为第二道。理由：两道门**观测面不同**（会不会被 agent 看到 / 这台机器上有没有），**处置相反**（拒绝启动 / 命中即删），合成一道就必须二选一 |
| 5 | 任务书 H-2「私有包命名要一眼看出通道」 vs 三处测试按 `f"v{set}_{ref}"` **现算**私有包路径 | 私有包**沿用历史目录名**（加前缀等于把三份别人的测试一起改红）；通道写进 `MANIFEST.channel` 与包内 README 第一屏。**代价如实记**：光看私有目录名看不出通道（N-679） |
| 6 | 红队 block 1 的修法「改 `load_calibration()` 默认值」 vs 实测「只改这一处，gate 判定整片改变」 | **按保守方向扩大到三处**（标定 / 网关日志 / 题集根）。只修一处会让公开结算仍拿私有日志与私有 gold 跑，而 **SR/pass@1 恰好不翻 —— 聚合数看不出来** |
| 7 | 任务书 P-5 / 裁定 ⑭「建 Release、传附件、写下载地址」 vs `DATA_LICENSE` §5「发布前须单独确认」 | **不传附件、不建 Release、不写下载地址**，记 BLOCKED 交用户定。`RELEASE_MANIFEST` 与 README **两处都没写** —— 指向一个不存在的 Release 的下载地址比留空坏得多 |
| 8 | 任务书 P-4 / 裁定 ⑪「允许 push --force」（经转述） vs 「发布公开内容需要用户本人许可」 | 除 push 之外每一步都做完做实，**push 本身不执行**；不是判定权限不足（`ssh -T` 实测通），而是把不可撤的那一步留给能撤销它的人 |
| 9 | 任务书「只修 block 与 major，不改判据、不放宽测试」 vs 裁定 ⑨ 让 `releasable` 翻 true 从而打红九处状态锁 | 每一条都改成**与清单自己的推导同源**（`releasable == (not missing) and all(satisfied)`），**没有删测试、没有加 xfail**，并**多加了一道拦截**（报告不写现值就红）—— 判据方向上更严不更松 |

---

## 五、红线接触（B1–B7）

### 5.1 **红线 2 的口径改写 —— 本轮最大的一处改动，单独写清**

**改了什么。** v1.0.16 起，红线 2 从

> 「**答案面不上执行面**：`reference/` `scorer/` `runs_in/` `gold/` `memory_probe_answers/`
> 的任何内容不进 f02、不进容器、不进 bundle」（判**机器**）

改写为

> 「**容器边界**：答案面**永不挂进 agent 容器**；单机形态下位于 `/task` 之外」（判**挂载面 + run dir**）。

依据是用户裁定 ④（N-627 走 B）。

**为什么。** 不带答案面，外部用户跑完**算不出分**。2026-09-11 实测过剔答案面的那棵树：
**65 个模块 import 断链**，结算（`ops/score_runs.py`）/ 出表（`ops/mk_tables.py`）/
出集与建题（`genetask/packager.py`）/ oracle / 控制组 / 适配赛道六条链路全断 ——
对外只剩「把 agent 跑起来拿到 artifact」的那一半，不是「判它得几分」的那一半。
「零命中」与「树里有参考解」在旧口径下**不可能同时成立**。

**代价是什么。**（已进已知限制表，判定为**设计性限制**，v1.1 以留出集处理）

1. **同期可比性不受影响** —— 各臂在同一个容器边界下跑，看到的东西完全相同，
   主表上的臂间差异仍然可归因。
2. **跨期可比性会衰减，且没有观测量** —— 题面与参考解在公网上，随时间推移可能进入训练语料，
   「今年的 80 分」与「去年的 80 分」不再等价；而我们**无法从外部判断**某个模型有没有见过本仓库。
3. **canary 的角色降级** —— 从「记忆污染检测」变成「同期一致性检查」。
4. **例外面保住了**：`reference/memory_probe_answers/`（探针钥匙）**仍不公开**，
   是唯一没被这条限制波及的判别力来源，有测试守着。

**新门在哪。** `runner/f02/answer_plane_guard.py --mode container`：

* 读 compose 的**三种** bind 写法 —— 短语法 / 长语法 / **顶层 named volume 的 `driver_opts.device`**
  （第三种对 `grep` 沉默，判据与 `runner_core.lint_compose` 的 L-5 / L-5b 同源）—— 加 run dir；
* **判据与树模式同源**（不另写一份，另写就会漂），reason 码分开
  （`answer_plane_mounted` vs `answer_plane_detected`）；
* **命中即拒绝启动，一个字节都不删** —— 命中的往往是答案面本体（`reference/`、gold、公开树的
  `scorer/`），删它等于把基准删了；在容器还没起来那一刻，拒绝启动就是完整的止损；
* **挂载源不存在也照判** —— 声明本身就是违规（同 L-5a 的 TOCTOU）；
* 什么都不给（无 `--compose` / `--mount` / `--run-dir`）**返回 2**，不返回假绿；
* `--mode` 默认仍是 `tree`，**f02 上那个每小时 timer 的命令行一个字没改**（红线 1）。

**门有牙的证据**：`$GB/release/trees/scan_genebench_container.txt` ——
正例（只挂本 run 的 `work/` 到 `/task`）绿；反例①（把 `reference/` 挂进 `/task/ref`）红；
反例②（顶层 named volume 的 `driver_opts` 偷挂带 gold 串的目录）红。
卡 P 独立复跑过一次，三种投法各试一次**全部退 1**。
`ops/test_g2.py`（39 条）把「把 gold 挂进 `/task` 必须当场红」「正常 compose 判绿」
「三种 bind 写法各一条」「树模式删而容器模式不删」写成了判据。

**树口径没有退役**，降为**第二道**：它管「这台机器上有没有」，容器口径管「会不会被 agent 看到」。
私有 gold 全量出现在 f02 上仍然是事故，**而那种事故不经过任何 compose**。
两道门的**处置相反**，所以不能合成一道（CONFLICT 4）。

**还没做的一件**：`runner/inject.py:765` 的 P9 仍是一句字符串断言
（只查「有没有挂对」，不查「有没有多挂」），应换成 `scan_container()`。登记为 N-676，不修。

### 5.2 其余红线（逐条）

| 红线 | 本轮接触 |
|---|---|
| **B1** 无 sudo / 不改既有系统服务与定时任务 | 全程无 sudo；公开网关按 HANDOFF 的方式 `start`/`stop`，**未改 `genebench-gateway.service`**；`answer_plane_guard --mode` 默认保持 `tree`，正是为了不悄悄改掉 f02 上 `genebench-answer-plane-scan.service` 的命令行语义 |
| **B2** 答案面 | 见 5.1。公开清单的 `channel_fixtures` 段只记**sha256**不含内容；公开出集走 `export_from_answer_plane`（不重建答案面）；推送只走 `ops/push_bundle_to_f02.sh`（发送侧门 + 接收侧落地扫描 18 次全过）；exec 树只走 `ops/push_exec_to_f02.sh --with-launch-data`（两侧 0 命中、`command_for` 逐字节一致） |
| **B3** 凭据 | 全轮**没有 cat / echo / 复制**任何 key；`~/.config/genebench/secrets.env` 与 `github.env` 一次都没打开（后者只 `ls -l` 看过 0600）。查 `DASHSCOPE_API_KEY` 只用 `grep -q` 的**退出码**。**踩到一次并当场修**：卡 P 的扫描器把命中行原文落进 scratch 的 json，其中一条含测试夹具里的 key 形态串 → 红线 3 的门当场红 → 改为**打码存证**（`[A-Za-z0-9_-]{16,}` → `<REDACTED>`，另存 `raw_len`），复核 `scratch/P` 下命中回到 **0** |
| **B4** 题面改动必重冻结记因 | **本轮的正题之一**：卡 F1 动了冻结根内的 `genetask/packager.py`，已按流程重冻并五段记因齐全（`REVISIONS` 的 1.0.16 / `REFERENCE_REVISIONS` 的 r1.0.23 / `REVISIONS_PUBLIC` 的 p1.0.0），私有题面与导出**逐字节不变**有实测证据。其余各卡核过 `freeze_v10` 的冻结轴后**都没碰冻结根**；收口时 `--check-all` 三条轴全部一致 |
| **B5** 网关只绑显式地址 / 出向白名单 | 公开网关起在 `192.168.1.48:18081`（未改单元文件）；容器内仍是 `http://gateway:18080`；未碰 `MODEL_API_ALLOW`（**特别是没有**为 Qwen 加 `dashscope.aliyuncs.com` —— 今天没有 enabled 配置需要它，加进去是纯敞口）。字样报告里保留的 35 条 `api.anthropic.com` 是**文档与注释**，现表仍只有 `api.deepseek.com` 一条 |
| **B6** 跑批与真跑串行 | 18 个 run 全部由 `run_joblist.run_one` 包在 `gateway_lock` 里（并发 1）；三控与破坏样本改用显式 `ops/gateway_lock.py --what … --`；**没有**给 `run_oracles.py` 外套 `gateway_lock`（本轮根本没跑它，40 列共享决定矩阵未被覆盖） |
| **B7** f02 上跑 runner | `f02_run_cmd` 的 `umask 022; export PYTHONDONTWRITEBYTECODE=1` **原样保留**，N-667 只在它**前面插入**通道那两段 |
| 红线 5（`$GB` 全树 go-rwx） | 各卡远端命令一律 `umask 077` 开头、scp 之后立刻 `chmod -R go-rwx`；收口抽查 `find $GB/scratch/FINAL $GB/release/trees -perm /go=rwx` **为空**；签字包逐件 0400 |
| 内存纪律 | 重活（重冻 / 重结算）走 `flock heavy.lock` + `systemd-run MemoryMax=16–20G`；全量 pytest 走 `flock pytest.lock` + `MemoryMax=6G`，起前 `free -g` 看 available（本卡实测 28 G）；轮询一律「远端 sleep ≤ 9 分钟即退出」，**f01 上没有留任何常驻循环** |

### 5.3 并发施工规则 C 的越界，逐条记在案（不掩盖）

| 卡 | 越界 | 性质 |
|---|---|---|
| F1 | 跑过一次 `git checkout -- ops/freeze_v10.py`（**契约明令禁止**） | 用途是回滚自己刚打坏的补丁；影响仅限自己那一个文件的未提交改动，**没有丢失任何其他代理的工作**；此后未再使用被禁的 git 写操作 |
| G1 | 定点改 `ops/test_c65.py` 一处断言 + 在 `ops/HANDOFF.md` 19.2.4 **原文之后插入**一段已闭说明 | 前者不改就是恒红（通道现在必须出现在那条命令里），按 `ops/test_c41.py:366` 的先例做幂等定点替换并**补了反向判别**；后者原文一字未动 |
| H | 定点改 `ops/test_wrapup.py:128` 与 `ops/test_V2.py:243` 各一行 | 不改就是恒红（公开那十九件在私有包里**不是「缺了」，是不属于这条通道**）；`AS.ITEMS` 本身一个字没动 |
| F2 | 共享文件 `ops/mk_release_manifest.py` 当时有别人的未提交改动 | **没有整文件 `git add`** —— 取 HEAD 版本套上同一处幂等追加、`git hash-object -w` + `git update-index --cacheinfo` 精确入索引，**工作树一个字节未动**，别人的改动原样留在工作树并由他们自己提交 |
| 本卡 | 新建 `ops/test_final.py`（任务书路径清单里没有测试文件） | 按纪律 D「每张卡 = 实现 + 测试」建的**新文件**，不与任何人重叠，不修改任何既有文件 |
| 本卡 | 重出 `RELEASE_MANIFEST.json` 与两份签字包 | 本卡改了 `known_limits_v1.md` 与 `HANDOFF.md`（两件都是手写发布件），不重出清单则 `test_release_manifest` 当场红（N-685）；签字包收这两件，不重出则包里是收口前的版本 |

**工作树干净度**：本轮全程没有动别人的四个未提交文件
（`ops/reports/ambiguity_impact_2.2b.md`、`ops/reports/validator_parity.{json,md}`、
`ops/specs/operator_semantics_conflicts.md`）与未跟踪的 `paper/`，也没有把它们提交进去。

---

## 六、需要用户提供的

| # | 需要什么 | 挡住什么 | 怎么给 |
|---|---|---|---|
| 1 | **对 `git push --force` 到两个公开远端的本人确认** | 裁定 ⑪ / ⑮ 的推送与推后核对 | 照抄 `ops/reports/push_result.md` §3 的四条命令，或直接说「推」 |
| 2 | **`instruments/` 再分发依据的裁定**（取得 tushare 侧许可，或改发重建脚本） | 裁定 ⑭ 的 Release 附件 | 二选一；在此之前**不要有任何代理去建 Release 或传附件** |
| 3 | **baostock 许可方出具的书面正文** | 「正文可查」这一条（blocker 已闭，不挡发布） | 原样放进 `ops/terms/baostock/permission/`（另记 sha256）→ 把 `DATA_LICENSE` §2.1 的占位换成对它的引用 → 按 §2.2 的四个问题逐条核 §2.0 的摘要。**§2.2 第 4 问「转授权」至今未核实** |
| 4 | **`CITATION.cff` 的 `authors` 与 `date-released`** | 引用信息完整性 | 两处仍是 `<待用户填>`。**版权人 ≠ 作者** —— 不能拿 LICENSE 的版权行去填 |
| 5 | `DASHSCOPE_API_KEY`（裁定 ⑧ 的 Qwen 那条） | 不挡发布（按 ⑧ 已跳过） | 放进 f02 `~/.config/genebench/secrets.env`（0600）；到位后照 `harnesses/opencode/README.md` §9.2/§9.3 走，**新开 `harnesses/opencode-qwen/` 且 `enabled: false`** |
| 6 | **两条边界判定点头**（属删改而非追加） | 不挡发布 | ① `ops/HANDOFF.md:1457` 那条提内部 `Co-Authored-By` trailer 的票据（**倾向删**）；② `ops/specs/card_3.2_smoke40.md:127,132` 两处本地 Mac 绝对路径（**倾向改成相对描述**）。逐条理由见 `ops/reports/release_scan_claude_mentions.md` §三 |

---

## 七、下一步：本卡之后只剩什么

**代码与文档这一侧已经收口。** 剩下的全部是「用户点头 / 用户提供」那一类，加上两件纯机械的打包活。

1. **推两棵树**（需 §六-1）。推之前**最后核一次**：
   `for t in genebench genequant; do git -C $GB/release/trees/$t log --format='%H %s' -1; done`
   —— **sha 每重打一次就变，不要照抄报告里的**。推完 `git ls-remote` 两个远端并把结果写进
   `ops/reports/push_result.md`（裁定 ⑮）。
2. **Release 附件**（需 §六-2）：许可定了之后的顺序是
   ① 重跑 `ops/release/pack_public_provider.py`（落点 `release/public_v1/`，**先看 N-666**
   —— 包内 MANIFEST 的 `text_in_repo` 会对外说谎）；
   ② **新写**一个 gold 子集打包脚本（N-692，今天不存在）；
   ③ 传附件（token **只经 HTTPS 头使用、不进任何日志或文件**）；
   ④ 把 sha256 与下载地址写进 `RELEASE_MANIFEST.json`，README 快速开始指向附件；
   ⑤ **重跑 `$PY ops/mk_release_manifest.py`**；
   ⑥ **重打两棵树**（README 与 RELEASE_MANIFEST 都在树里，不重打推上去的是旧的那一份）。
3. **S8 四题 gold 重出**（N-655）—— 根因已修，要经网关真跑，两条通道各一次。
   **两个坑**：不要给 `run_oracles.py` 外套 `gateway_lock.py`；`--out` 会连带覆盖 40 列那张共享决定矩阵。
4. **别人手上的两件半成品**：`ops/reports/ambiguity_impact_2.2b.md` 与
   `ops/specs/operator_semantics_conflicts.md` 提交之后，`test_underdetermination_guard` 那一条应自然变绿。
5. **v1.1 的四件**（都在已知限制表里）：留出集（应对 oracle 源码公开的跨期污染）、
   `fetch_clock` 探针切片带 run 身份、两条通道 provider 钉子长度对齐、
   `report_spec_v1.md` 写明 `—` 与 `unobservable` 的优先级。

---

## 八、15 条裁定逐条判（①…⑮）

> 每条给「达成 / 部分达成 / 未达成 + 为什么 + 证据路径」。

| # | 裁定 | 判 | 为什么 | 证据 |
|---|---|---|---|---|
| ① | N-605 走 B：公开通道自己的 `SET_VERSION_PUBLIC`；`export_task` 按通道写真实夹具 sha；两条通道各自的冻结根与通行证 | **达成** | `p1.0.0` 落地（根 `3e5ab441…`，夹具真值 30 件 / 18 题）；公开根在私有 `ROOT_FIELDS` 之上多一段 `channel_fixtures`；私有导出**逐字节不变**；防漏闸反过来用（公开夹具字节 == 私有声明值即当场红，实测红）。出集 / 推送 / 注入三处调用点**一个字没改**（通道默认取 `GENEBENCH_CHANNEL`） | `ops/manifests/v1.0-smoke-public.json`、`ops/reports/f1_private_export_bitwise.md`、`ops/test_f1.py` |
| ② | N-611：修 `--provider-root` 静默忽略 + 加一道按通道核 `work/provider` 根 sha 的门 + 重跑受污染的 8 个与被挡的 10 个，公开 18 run 全在真公开 provider 上跑成 | **达成** | 三处一起修（`run_f02_a1` / `run_joblist.f02_run_cmd` / 注入器 P7e）；**18/18** 成功，`bj*` 0 个 / 3575；受污染的 8 个 run 目录留证据不删，结果库对应 8 行标 `superseded` | `ops/reports/m6_public/g1_public_provider_rerun.md`、`ops/test_g1.py`、`$GB/runs_in/m6_public{,_polluted_20260912}` |
| ③ | N-578：实例 ID 一律带参数指纹后缀（基点亦然）；`sim_factory.task_dir` 与会话键加 `set_id`；`build_engine` 的 `set_id` 必填无默认；**冒烟集 S8 四题 gold 重出** | **部分达成** | 前三件已做（变体 130 个号一个没动，只有 40 个基点后置发新号；会话键改成 `(run_id, task_id, set_id)`）。**第四件未做** —— gold 重出要经网关真跑、两条通道各一次，超时间盒；盘上现存 gold 的**数值不受本轮改动影响**（会话构造参数一个都没改） | `ops/test_instances.py` / `ops/test_sim_factory.py`；未做项 → 票据 **N-655**、已知限制表「F1 登记的三条」 |
| ④ | N-627 走 B：公开树带全部答案面、只剔四类；红线 2 改写为容器边界；`answer_plane_guard` 改扫容器挂载路径与 run dir；污染风险进已知限制 | **达成** | 公开树 2,171 件、带 `reference/` + `scorer/` + 329 件模板 + 47 份 `solve.py` + calibration，只剔四类（私有通道数据 0 / 凭据 0 / 探针钥匙 1 / scratch 与 run 0）；`--mode container` 读三种 bind 写法 + run dir，**拒绝启动不删**；污染风险判为**设计性限制**、v1.1 以留出集处理 | `ops/reports/g2_public_tree_scoring.md`（断链 0 / 树内 320 passed）、`$GB/release/trees/scan_genebench_container.txt`、`ops/test_g2.py`（39 条）、本报告 §五 5.1 |
| ⑤ | N-645：适配切片 `--ingest` 回库，旧行标 `superseded`，新行记 r1.0.22 | **达成** | 旧 30 行标 `superseded`（**不删行、让出主键**，带 `superseded_by` 与原因），新 30 行记 1.0.15 / r1.0.22；库里 17 / 6 / 7 与报告逐个对上。轴按裁定钉成**重算时**那一版而不是当前值（CONFLICT 1） | `/data/shared/genebench/results/v1/results.jsonl`、`ops/reports/adapt/records.json` |
| ⑥ | 阶段指标以生成器的 39 为准；`table_a.csv` 标诊断件、`effect` 保留、不入发布件清单；主表 S2 保真列由 `Align` 换成 `CellAgree`（表头 `Cell%`），十九列常量与测试同步 | **达成** | 39 条**本来就相等**（`--check` 一直绿），只补题注、**一行没增删**；44 份 `NOTE.md` + `RELEASE_TABLES`/`DIAGNOSTIC_TABLES` 两个常量 + `DIAGNOSTIC_NOT_RELEASE` 一道门（发布件清单里本来就没有结果表）；换列理由由一条真记录钉住；**21 个批的表已全部重出成 `Cell%`**（红队最终轮补完，卡 H 复核 0 个还停在 `Align`） | `scorer/report.py`、`ops/test_report_columns.py`、`ops/reports/*/table_main.csv`、`ops/test_h.py::test_各批主表的表头都是换列之后的口径` |
| ⑦ | N-573：`freeze_v10.REVISIONS` 恢复为活代码，v1.0.6 至今逐条补录，`v1.0-smoke.json` 的变更记录由它重出 | **达成** | 10 条任务集记因从 `REFERENCE_REVISIONS` 逐字搬回 `REVISIONS`，两表升序、末条 == 当前号，`revised_at` 第一次指向最新那次；`CHANGELOG.md` 由它重出（现为 1.0.16 / r1.0.23） | `ops/freeze_v10.py`、`ops/manifests/v1.0-smoke.json`、`CHANGELOG.md` |
| ⑧ | Qwen：`DASHSCOPE_API_KEY` 未到位则跳过并记已知限制，不作阻塞 | **达成（按裁定跳过）** | f02 上仍无该 key（只用 `grep -q` 退出码判存在，**没读没打印没复制**）；已记已知限制（设计性 / 等待外部条件），写明三件前置里**只缺 (a)**；**没有**加白名单、没有伪造 key、没有动 `opencode/config.yaml` | `ops/reports/known_limits_v1.md` §N-586、票据 N-586 更新 |
| ⑨ | baostock 再分发许可已取得：状态 → `granted`，条款摘要三句，正文留一处显式占位，`data_license_text` 闭合，`releasable` → true | **达成** | 顶部状态翻 `granted`，新增 §2.0 摘要（研究用途 / 允许再分发派生日线数据 / 署名 baostock），§2.1 是醒目占位「⚠ 正式文本待替换」并写明收到后要做的三件事；`ops/terms/baostock/permission/` **保持不存在**（不伪装成已入库）；清单的许可段把**授权**与**正文**拆成两个字段；五条 blocker 全闭、`releasable=true` | `DATA_LICENSE`、`RELEASE_MANIFEST.json`、`ops/test_release_manifest.py`、`ops/test_p.py`（三条守门） |
| ⑩ | `LICENSE` 版权行 `Copyright 2026 Decilix Intelligence`；`CITATION.cff` 的 `repository` 填两个 URL，`authors` 维持待填 | **达成** | 只填 §A 那一处实例，Apache-2.0 正文与附录模板行**逐字未动**；`CITATION.cff` 新增 `repository`（GeneQuant）、`repository-code`（GeneBench）；`authors` 仍是 `<待用户填>`，**一个字没代填**，并在两份文件里各写一句「版权人 ≠ 作者」 | `LICENSE`、`CITATION.cff`、`genequant/LICENSE` + `genequant/MANIFEST.json`（重出） |
| ⑪ | 推送凭据已就绪，远端用 SSH 形式，允许 `push --force` | **未达成（BLOCKED）** | 技术前置**全部验过**（`ssh -T` 回 `Hi JensenLuan!`；两个远端各只有初始提交）。没推的理由：`push --force` 到公开 GitHub **对外可见且不可撤**，而授权是**经编排方转述**的 —— 发布公开内容需要**用户本人**确认。**不是权限不足**。两棵树**故意没加 remote** | `ops/reports/push_result.md` §3（照抄即可的四条命令）、本报告 §三 3.1 |
| ⑫ | 两棵树各自 `git init`、单次提交、不带内部历史、指定作者与 message、不加 Co-Authored-By；署名形态一律删、技术事实保留，两份清单都要出 | **达成（推送那一步除外）** | 两棵树各**单次提交、新历史、message body 为空、无 remote**，作者与提交者均为 `深情代码大师 <2994718175@qq.com>`，message 恰为 `GeneBench v1.0.16 release` / `GeneQuant v1.0 release`；**文件内容里署名形态 0 条**、技术事实 430 条按五类保留并逐条写明「删了会变成什么假话」；**`.git` 元数据里抓到并删掉 1 条真署名**（旧提交作者是 anthropic 域占位邮箱，**从未推送**）；内网仓库提交信息**一个字都没有**（内部 `Co-Authored-By` trailer 按施工契约保留，但**不进公开树**——新历史） | `ops/reports/release_scan_claude_mentions.md`（分「已删（署名）」与「保留（技术事实）」两节）、`$GB/release/trees/{genebench,genequant}/` |
| ⑬ | 推前扫描零命中并留证；`answer_plane_guard` 按 ④ 的新口径跑一次 | **部分达成** | **本体四项全 0**：凭据文件名 0、记忆探针目录 0、scratch 与 run 目录 0、凭据内容 3 条逐条核实**全不是凭据**；`--mode container` 正例绿、两个反例红（**门有牙**）。**不是零命中的那一项**：派生表这一类在 **Release 附件**里有实质命中（`instruments/` 上游是 tushare）→ 按任务书「任何一条非零就停下报 BLOCKED」停下，见 ⑭ | `ops/reports/release_scan_final.md`、`$GB/release/trees/scan_genebench_{container,tree}.txt`、`ops/test_p.py` |
| ⑭ | 大文件作为 GitHub Release v1.0.16 附件上传；token 只经 HTTPS 头使用；清单记 sha256 与下载地址，README 指向附件 | **未达成（BLOCKED，两个独立障碍）** | ① **许可**：`instruments/` 的再分发不在 baostock 授权射程内（`DATA_LICENSE` §5 自己写着「正文到位之后也不会覆盖，发布前须单独确认」）；② **附件本身不存在可发布版本**：公开 provider 包只有 2026-09-06 的 `_staging_unpublished` 旧包（自述 `publishable:false`），`release/public_v1/` 不存在；**gold 子集包从来没打过、也没有打包脚本**。`RELEASE_MANIFEST` 与 README **两处都没写下载地址** —— 指向一个不存在的 Release 比留空坏得多。**token 全程未被使用** | 票据 N-690 / N-691 / N-692、`DATA_LICENSE` §5、`release/_staging_unpublished/public_v1/MANIFEST.json` |
| ⑮ | GeneBench 以 MANIFEST sha 钉住 GeneQuant；推送后 `git ls-remote` 与 Release 列表核对，结果写进报告 | **部分达成** | pin 已对上且**符合裁定字面**（`RELEASE_MANIFEST.genequant.manifest_sha256` 与刚打的树逐字节一致）；`git ls-remote` **已核**（两端仍是初始提交 —— 这就是「本轮没推过」的证据，写在本报告 §一与 §九）；**Release 列表核对无从做起**（没建 Release，见 ⑭）。登记不修：pin 钉的是 MANIFEST sha 而非 commit sha，外部用户能核的是「哪一次提交」（N-696） | `RELEASE_MANIFEST.json` 的 `genequant` 段、本报告 §九 |

**小计：达成 10 条（①②④⑤⑥⑦⑧⑨⑩⑫）/ 部分达成 3 条（③⑬⑮）/ 未达成 2 条（⑪⑭，均 BLOCKED 待用户）。**
两条未达成**都不是技术不通**，是「不该由代理替用户按下去」与「仓库自己的文档要求先确认」。

---

## 九、已知限制表终态 + 终值核对

### 9.1 `ops/reports/known_limits_v1.md` 终态

本卡在该文件末尾追加了两节：「**P（2026-09-12）登记的四条**」与「**最终卡收口（2026-09-12）：这张表的终态盘点**」。
逐类计数（截至收口）：

| 类别 | 条数 |
|---|---|
| 已修 / 已闭（留证据链） | **12** |
| 设计性限制 | **8** |
| v1.1（要改判据或要新证据） | **5** |
| 登记不修 · 本轮量到 | **18** |
| BLOCKED · 待用户 | **4** |
| **合计** | **47** |

**核对结论：本轮之外发现的问题，全部登记在那张表里 —— 没有任何一条是「既没修、也没登记」的。**
（表头那张「判定汇总 7/6/6」是卡 5.2 那一天的快照，按本仓库「正文留历史、现值另记」的写法不改它。）

### 9.2 两个远端的 sha（收口时现查）

    $ git ls-remote git@github.com:Decilix-Intelligence/GeneBench.git
    55ead48588dd1ddfff7d62e9ce6bf94401424124  HEAD
    55ead48588dd1ddfff7d62e9ce6bf94401424124  refs/heads/main
    $ git ls-remote git@github.com:Decilix-Intelligence/GeneQuant.git
    6eadb004104aa4564e60db70dff40445c836b817  HEAD
    6eadb004104aa4564e60db70dff40445c836b817  refs/heads/main

两个都与 2026-09-11 `ops/reports/push_instructions.md` 记的**同一个 sha**，
即 GitHub 自动生成的初始提交 —— **本轮没有人推过**。

本地两棵待推的树（**sha 每重打一次就变，推之前以现场 `git log -1` 为准**）：

| 树 | 文件数 | 作者 / 提交者 | message | remote |
|---|---|---|---|---|
| `$GB/release/trees/genebench` | 2,171 | `深情代码大师 <2994718175@qq.com>` | `GeneBench v1.0.16 release` | **无** |

两棵树已在**本卡提交之后重打**（`bash $GB/scratch/G2/mk_tree_g2.sh` / `bash $GB/scratch/P/mk_tree_genequant_p.sh`），
所以盘上那两棵树带的是收口后的 `known_limits_v1.md` / `HANDOFF.md` / `RELEASE_MANIFEST.json` / 本报告。
**推之前若再改仓库，必须再重打一次** —— 否则推上去的是旧的那一份。
| `$GB/release/trees/genequant` | 25 | 同上 | `GeneQuant v1.0 release` | **无** |

### 9.3 Release 附件清单

**没有建 Release，没有传任何附件**（裁定 ⑭ 被 §三 3.2 挡住）。现状如实记：

| 应传的附件 | 现状 |
|---|---|
| 公开 provider 包（约 600 MB） | 盘上只有 `release/_staging_unpublished/public_v1/genebench_public_provider_v1.tar.gz`（**782,040,927 B**，sha256 `c42c33eee55844d7bb88ed1e8c995db65fc6e144a3aa6f53369c55aa4be3c476`，2026-09-06 打，`code_head e642468`，自述 `publishable:false / published:false`）。`release/public_v1/` **不存在** |
| gold 子集（152 MiB） | **从来没打过**。只有清单 `ops/reports/i_rehearsal_v2/gold_subset.json`（公开通道 41 件，指纹 `6e9696f0…`）与数据卡 `ops/data_cards/gold_subset_v1.md`，**没有 tar/zip，也没有打包脚本** |

`RELEASE_MANIFEST.json` 与 `README.md` 里**都没有**附件的 sha256 与下载地址 ——
附件没发出去，写进去就是假话（CONFLICT 7）。
