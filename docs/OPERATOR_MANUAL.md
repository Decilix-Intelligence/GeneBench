# GeneBench 运行者手册

**读者**：拿到这个包、要在自己的机器上把 GeneBench 跑起来的人。
不是被测方（被测方读 `integrations/P2_CONTRACT.md`），不是接手施工的人（那读 `ops/HANDOFF.md`）。

**这份手册与 `ops/HANDOFF.md` 的关系**：HANDOFF 是**内部交接**文档 —— 它按施工阶段组织，
记的是「谁做了什么、为什么这么定、踩过哪些坑」。本手册按**运行者要做的事**组织：
部署 → 加配置 → 加被测系统 → 跑一批 → 出表 → 出错了查哪。
两者的命令有重叠，口径以本手册为准；本手册说不清的细节按节里给的出处去 HANDOFF 查。

---

## 0. 先读这一段


<!-- Y1-2026-09-11 -->
### 0.0 最低配置与包体（先看这一段，不够就别往下走）

**最低配置**（2026-09-11 实测，出处逐条给在右列）：

| | 最低 | 实测出处 |
|---|---|---|
| **内存 · 数据面**（网关那台） | **16 GB** | 网关常驻 ≈ 2.3 GB；一道 **S7** 真题把它顶过 6 GB 上限并触发 4 次 oom-kill，所以上限现在是 **12 GiB**（§9）。只跑非 S7、并发 1 的话 8 GB 也能过，但**没有实测背书** |
| **内存 · 数据面（要自己重建数据面）** | **30 GB** | `run_public_chain` 的 gold 重算：792 个面板常驻 **22 GiB**，30 GiB 的机器上被 OOM killer 收走过两次（§1.4） |
| **内存 · 执行面**（docker 那台） | **16 GB** | 一次真跑起两个容器；agent 侧峰值随 harness 变 |
| **内存 · 形态 ① 单机** | **30 GB** | 上面两条相加的上界 |
| **磁盘** | 只走 §1.4 (a) + README §2.4 最短路径 **≈ 15 GB**；想连着跑几批 **50 GB**；要自己重建数据面留 **200 GB** | 15 GB 的逐项算式在 README §1.5（clone 0.03 + 附件 0.91 + 解包 1.15 + Python 环境 0.25–0.40 + 基座与一个 harness 镜像 1.7 + 8 个 run 4.8 + docker 缓存 2 ≈ 10.8 GB，留余量取 15）。发布包解开 **1.52 GiB**（下表）；**每个 run 的目录约 600 MB**（实测 `work/` 608 MB —— 大头是逐 run 物化的 provider 树）；本项目 `$GB` 全树 99 GB |
| **docker** | **≥ 24 + compose v2**，且**引擎可用内存 ≥ 16 GB** | Linux 实测 docker **29.1.3** / compose **2.40.3**；macOS 实测 Docker Desktop 引擎 **29.2.0 aarch64** / compose **v5.0.2**。**Docker Desktop 默认只给 8 GB —— 不够**：Settings → Resources → Memory limit 调到 **16 GB**，Apply & restart（调到 16 GB 之后 `docker info` 自报的 `MemTotal` 是 16,748,077,056 B ≈ 15.6 GiB，引擎自己留了一截，这是对的）。**纯数据面那台不需要 docker**（本项目的 f01 根本没装） |
| **Python** | **3.12+** | macOS 自带的 `python3` 是 **3.9.6，不够**。3.12 是外部路径唯一有实测背书的版本（2026-09-11 Linux 演练、2026-09-13 macOS 外部验收都在 3.12 上）；代码本身在 3.10 上也跑 —— 本项目内部环境就是 3.10，**内部自检与内部路径继续用它**（§1.2） |

**包体**（`ops/reports/i_rehearsal_v2/package_inventory.json` 现算，2026-09-11）：

| 部分 | 体积 | 发不发 |
|---|---|---|
| 代码树（`git archive HEAD`） | 18.8 MiB（剔除答案面后 **gzip 4.0 MiB**） | 必发 |
| 公开通道行情表 `$GB/snapshots/public_v1/tables` | 446.3 MiB | 必发（网关只读这一棵） |
| 公开通道 `qlib_provider` | 352.0 MiB | 必发（注入器按 sha 根核） |
| 公开通道 `tradability` | 146.4 MiB | 必发 |
| 公开通道 `epsilon`（含 S7 信号源面板） | 10.7 MiB | 必发 |
| 公开通道 `universe` / `calibration.json` / `crosscheck` | 2.0 MiB | 必发 |
| **gold 因子面板** | **全量 14.90 GiB → 只发 152.0 MiB 的子集（41 件）** | 见下 |
| 答案面 `reference/`（gold 产物 + 夹具） | 427.3 MiB | 发给**运行者**，**绝不进容器** |
| harness 镜像 | — | **不发**，本机 `harnesses/build.sh` 建（§3） |
| **合计** | **1.10 GiB**（不含答案面）/ **1.52 GiB**（含） | |

**gold 只发子集**：全量是 793 因子 × 3 宇宙 × 2 通道 = **14.90 GiB**，超过 5 GB 的发布线；
而出集 40 行 + 130 个实例真正读到的只有 **41 个因子面板文件（152.0 MiB，占全量 1.00%）**。
逐件 sha256 与「子集能干什么、不能干什么」在 `ops/data_cards/gold_subset_v1.md`，
机读清单在 `ops/reports/i_rehearsal_v2/gold_subset.json`。
**一句话限制**：子集够你跑完题、算出分；**不够**你重新推导 `s4_eco_pool_v1` 那 30 条是怎么挑的
（那一步要扫全族每一条），要审选取就走 §1.4 (b) 重建一遍。

**解包之后第一件事**（三条，缺一条都会在后面变成看不懂的报错）：

```sh
$PY ops/mk_release_manifest.py --check    # 0 一致 / 3 只是内容 sha 漂了 / 1 **判据变了** / 2 还没有清单
$PY ops/freeze_v10.py --check-all         # **三条轴一起核**：私有任务集 / 公开任务集 / 参考面
$PY ops/guard_modes.py --harden           # $GB 下一个 0644 就能让网关起不来（§7.6）
```

<!-- C2-2026-09-13 -->
**外部用户把上面三条换成一条**：`$PY ops/selfcheck_public.py`。
它把这三条里外部能核的部分（冻结根 + 权限前置）连同 Python 版本、六个包、docker 内存、
发布附件的 sha256（有几件以 `ops/release/attachments.json` 为准，今天是三件）、网关起不起得来一起跑一遍，**只查外部环境能自己满足的项**。
四种状态：绿 / 红 / 跳过（前置还没做）/ 登记在案（已知发布缺件）；有红条才退非零。

**两条命令是发布方自检，外部用户不要拿它们判「发布件坏没坏」：**

* **`ops/test_env.py`** —— 断言 `/data` 落点、内部数据湖（`market_lake`）、发布方那个解释器与
  发布方的网关地址、以及 `/data` 留 500 GiB。干净机器上必然红一片
  （2026-09-13 macOS 外部验收实测 **10 failed / 52 passed / 2 skipped**），**那些红不是缺陷**。
  文件保留着，**它对内部仍然有用**；README 的外部步骤里已经不再出现它。
<!-- P2-2026-09-13 -->
* **`ops/mk_release_manifest.py --check`** —— 发布方自检，外部不必跑；**跑了应当退 0**。
  这份清单**刻意不取决于跑它的机器**（`clone_urls_declared` 的 docstring 就是这么写的）。
  曾经有两处机器依赖（「这台 clone 有没有 remote」「这台有没有发布方那批 `m6_public`
  的 run 清单」）让它在每一个外部 clone 上退 1 —— 2026-09-13 按用户裁定 ② 修了根因，
  判据是「同一棵树在有 / 无 remote 两种状态下生成的清单**逐字节相同**」。

### 0.1 五件曾经挡着「今天就能对外发布」的事（不粉饰；**五条全部已闭合**，`releasable=true`）

> **「releasable」不等于「外部用户能用」** —— 五条 blocker 是发布清单的判据，真正挡可用性的事在 `ops/reports/known_limits_v1.md`。
> 另：第 1 条闭的是**授权**，不是**原文**。下面逐条写清。

1. ~~**baostock 的书面许可原文没有入库。**~~
   **已闭合（2026-09-11 用户裁定 ⑨）**：baostock 的再分发许可**已取得** ——
   条款摘要是「研究用途、允许再分发派生日线数据、署名 baostock」，`DATA_LICENSE`
   的状态从 `pending_license_text` 翻成 **`granted`**，`RELEASE_MANIFEST.json` 的
   `data_license_text` 随之 `satisfied=true`，`releasable` 推导为 **true**。
   闭合之前它的状态是 `pending_license_text`，公开数据包只落在
   `$GB/release/_staging_unpublished/`、包里的 `publishable=false`；现在不是了。
   **但「授权有了」与「原文可查」是两件事**：许可方出具的**书面正文仍未到手**，
   `DATA_LICENSE` 的「## 2. 许可原文」一节是一处**显式占位**（写着「正式文本待替换」），
   它指定的许可正文落点**仍然是空的** —— 目录不存在就是它的真实状态，
   **不要往里放任何替身文件**。谁把占位删掉而没有同时放进正文，就是把「有人口头说过」
   写成了「有文件可查」。
2. ~~**这个仓库没有可 clone 的地址**（`git remote -v` 是空的）。~~
   **已闭合（2026-09-11 用户裁定 ㉑）**：本体 `https://github.com/Decilix-Intelligence/GeneBench.git`，
   协议工件单独一棵 `https://github.com/Decilix-Intelligence/GeneQuant.git`。`git clone …` 的步骤已换成真地址。
   **推送由仓库所有者执行**，所以「地址已定」与「那边现在有什么内容」是两件事 ——
   核对清单在 `ops/reports/push_instructions.md`。本仓库仍**没有**配置 remote，那是有意的。
3. ~~**`factor_library/compiled/{qlib_native,qlib_panel,blocked}.jsonl` 三个文件不在仓库里**~~
   **已闭合（2026-09-10，卡 W2 提交 `8428252`）**：`PUBLIC_FROZEN_ARTIFACTS` 声明的
   6 个冻结件现在**全部到位**。它们是 gold 的定义面 —— 少了就复现不出 τ。
4. ~~**代码许可未定。**~~ **已闭合（2026-09-10 用户裁定，卡 B 落地）**：`LICENSE`
   换成了 **Apache-2.0 全文**，首行是 `SPDX-License-Identifier: Apache-2.0`。
   这一条挡的从来不是「能不能跑起来」，是「跑完之后这份代码你能不能用、能不能转发」——
   现在**能**：按 Apache-2.0 §4 的条件（保留版权与许可声明、标注改动）使用 / 复制 / 修改 / 再分发。
   **仍待填的是版权行**（附录的「Copyright [年] [版权人]」）与 `CITATION.cff` 的 `authors`
   —— 那是仓库所有者的决定，没有代填；它影响署名完整，不影响授权成立。

5. ~~**公开通道一个 run 都没有。**~~ **已闭合（2026-09-11 卡 X1 起步，2026-09-12 N-611 跑齐）**：
   18 个计划 run **18/18 全部跑成**（批 `m6_public`，八道题两臂，四轴
   `p1.0.0 / r1.0.23 / geneprotocol_v1@d6fbcaa08302 / public`），
   `ops/reports/m6_public/` 下的表与就绪报告都有逐 run 证据。
   `RELEASE_MANIFEST.json` 的 `public_channel_zero_runs` 已 `satisfied=true`。
   **N-611 的教训写在这里**：X1 那一轮的 8 个 run 跑在**私有 provider** 上
   （`--provider-root` 在真跑路径上被静默忽略），已全部重跑并作废，
   证据保留在 `ops/reports/m6_public/g1_public_provider_rerun.md` 与
   `ops/reports/m6_public/scores_superseded_20260912/`。
   **这一条从来不挡你自己跑**（跑起来就有 run 了）。

这五条不是本手册能修的。**权威条数与逐条关闭条件以 `RELEASE_MANIFEST.json` 的 `blockers` 为准**
（本节只是把它摊开讲）；形态层面的分析在 `ops/reports/public/release_forms.md` §0
（那一页只讲前三条 —— 代码许可不是形态问题）；「拿它怎么办」在 `ops/reports/known_limits_v1.md`。

### 0.2 全文的四个变量

```sh
GB=/data/shared/genebench            # 数据根（$GENEBENCH_ROOT）
PY=$GB/env/bin/python                # 这套东西专用的解释器（Python 3.10）
REPO=$GB/repo                        # 仓库根
F02=ljn@192.168.1.219                # 执行面主机（形态 ② 才有；形态 ① 就是本机）
cd $REPO
ulimit -n 8192                       # 跑任何触数据的命令之前先敲；否则 gold 全表扫会 Too many open files
```

`$GB` 的落点由 `genebench_config.py` 的 `_DEFAULT_ROOT` 一行决定，也可以用环境变量
`GENEBENCH_ROOT` 覆盖。**仓库里除了这个文件，任何地方都不许出现绝对路径字面量。**

### 0.3 本手册里的命令是怎么验证的

* **不调用模型的命令：在 f01/f02 上原样跑过。** 包括出集、推送 bundle、干跑清单、
  结算入库、三种格式出表、混轴被拒、公开数据面与重建链的 `--dry-run`、网关起停与 `/healthz`。
* **会真调用模型的只有「真跑」那一步**（§5.4 ④ 与 §5.6）：验到 `--dry` 为止 ——
  注入器把 `work/` 装配完、两臂文件集比对通过、`compose.yml` 生成，**没有起容器、没有调模型**。
<!-- C2-2026-09-13 -->
* **形态 ① 的完整链路：Linux 上已经整条跑过，macOS 上还没有。**
  2026-09-11（卡 Y1）在一台 Linux 机器上走完了解包 → 起网关 → 建 harness 镜像 → 落 secrets →
  3 题双臂真跑 → 结算 → 出表，证据在 `ops/reports/rehearsal_v2.md`（§1.1 / §1.3 记的是同一件事）。
  2026-09-13 的 macOS（arm64）外部验收**没走完**：下载 → 逐件核 sha256 → 解包 → 本机网关 `/healthz` 200
  四步实测通过，再往后就停了。
  **所以这一条的准确说法是：Linux 验到底，macOS 验到网关为止。**
  <!-- C9-2026-09-14 -->
  **成因 2026-09-14 换过一次（N-843）。** 旧版写的是「卡在「建 harness 镜像」——
  本机没有统一基座 `gb-base:bookworm-r1`，公开题集 S4–S7 那 18 道题的输入夹具也没有随两个附件交付」，
  **这两条同日都已经补上**：基座的整套构建上下文随树发了（`build/base/`，`harnesses/build.sh`
  缺基座时自己构），S4–S7 那 18 道题在**第三件附件**里（交付终核落位后逐题核过）。
  **照旧版去补这两件，补完照样走不过去。** 今天真正拦路的是**单机形态那条路上还留着的跨机步骤**：
  两个 `push_*_to_f02.sh` 的解释器与暂存目录默认指着发布方的绝对路径；执行面 run 根写死
  `/data/genebench_runner`，且被推送脚本当成硬判据；推送前要 `ssh` 去核一道 `systemd` timer
  （§1.3 (3) 自己写着 Mac 上这条过不去，而脚本没有绕过开关）；跑批每个 job 要拿的网关锁锁根也写死。
  **这四条在 Linux 上永远不显形** —— Linux 上 `mkdir /data` 就把那些路径造出来了；
  **macOS 根卷只读**，`sudo mkdir /data` 直接失败。逐条与成因见
  `ops/reports/known_limits_v1.md` 的 **D-06 家族第八例**。
  <!-- H10-2026-09-14 -->
  **这条新路已经在本树里了，而且实测可用 —— 不是「待建」。** 旧版这里写的是
  「用户 2026-09-14 裁定 ①②：单机路径改成不含任何跨机步骤（那两步换成本地落位，
  其余根从 GENEBENCH_ROOT 现算），双机路径不动」，读起来像是在让你去等一件东西。
  **现状**：单机形态就是**一条不含任何跨机步骤的路径**，入口 `runner/placement.py`
  （`python -m runner.placement --topology single --place-exec --with-launch-data`），
  跑批侧 `ops/run_joblist.py --topology single`；形态判据**显式**
  （`--topology` > `GENEBENCH_TOPOLOGY` > 默认 `dual`，没有 hostname / 路径存在性嗅探）；
  本地落位调的是**同一批门、同一份实现、同样顺序**，而 `ops/push_bundle_to_f02.sh` /
  `ops/push_exec_to_f02.sh` 这一轮**一个字节没改**。门在 `ops/test_single_machine.py`
  （它此前钉着几条 strict xfail 的那四个执行面缺陷 **2026-09-14 已修完，标记随之删掉**；
  今天这道门是绿的，唯一 skip 的那条会**逐条**告诉你真跑前置缺哪件）。照抄命令见 §1.3 与 §5.4。
  **结论一个字不改：macOS 那一侧仍然只验到网关。**
  「树里有这条路」与「这条路在 Mac 上被走过」是两件事。
<!-- P2-2026-09-13 -->
* **2026-09-13 的第二次 Linux 实证比第一次强**：2026-09-11 那次跑在一台参与过开发的机器上，
  **量不出缺件**；这一次在一棵**没有本项目任何遗留物**的树上，只凭 `git clone` + 三个附件
  走完了建基座（仓库 `build/base/`，`--no-cache` 69 秒）→ 建 harness 镜像 → 起网关 →
  出集 → **3 题双臂 6 个 run 真跑 2 小时 1 分 / 582 次真模型调用** → 结算 → 入库 →
  出表（`--table main`，19 指标列 + 5 身份列 = CSV 24 列）。**唯一的例外**是结算与入库
  先补了两条软链（`ops/score_runs.py` 与 `ops/results_db.py` 的 run 根当时不同源，
  2026-09-13 已修 —— 显式入口 `--runs-root`，同机结算另加 `--remote-host local`）。
  逐步实测在 `ops/reports/mac_gap_closeout.md` §4–§5。**macOS 那一侧的结论没有变。**
* 命令后面带 **★未实跑** 的，是「跑一次要几小时」或「跑一次就造出一件不该造的东西」那几条
  （建数据面全链、重建链、打包、归档、交易时段拉数）。它们只验到 `--help` ——
  开关名与语义是真的，**但我没有替你按下去**。逐条清单见 §8.5。

---

## 1. 部署

### 1.1 两种形态

| | 形态 ① 单机 | 形态 ② 双机（本项目现在的形态） |
|---|---|---|
| 数据面（网关 + 快照 + 答案面） | 与执行面同机 | 独立一台（f01 `192.168.1.48`） |
| 执行面（docker：任务容器 + 出向边车） | 同机 | 独立一台（f02 `192.168.1.219`） |
| 容器怎么找到网关 | 走宿主的 LAN 地址 —— **需要放行宿主防火墙**，见 §1.3 | 走另一台机的 LAN 地址，跨主机流量，不碰宿主防火墙 |
| 答案面隔离靠什么 | **容器边界**（答案面在 `/task` 之外）+ 目录权限 0700 + 推送守门 | 同左 + **物理分机** |
| 适合谁 | 只有一台机器的外部运行者 | 想在容器边界之外再加一层物理保障的人 |

<!-- G2-2026-09-12 容器边界 -->
> **v1.0.16 起：隔离的判据是容器边界，不是机器边界。**
> 「答案面不上执行面」是 v1.0.15 及以前的表述 —— 它要求答案面不出现在执行面**那台机器**上。
> 本版起改为：**答案面永不挂进 agent 容器**；单机形态下答案面位于 `/task` 之外即可。
> 于是形态 ① 不再是「弱化版」：一台机器上同时放答案面与容器，隔离性与双机**相同**，
> 双机多出来的只是「万一挂载面判据被绕过」时的第二层物理保障。
> 判据的实现：`runner/f02/answer_plane_guard.py --mode container`（读 compose 挂载面 + run dir，
> 命中**拒绝启动、不删**）。理由与代价见 README §4 ①。

**两种形态跑的是同一套代码**，差别只在三个常量与一条防火墙规则。

<!-- H10-2026-09-14 -->
> **怎么告诉代码你是哪一种：显式开关，不猜。**
> `--topology single|dual` > 环境变量 `GENEBENCH_TOPOLOGY` > **默认 `dual`**；
> 两者都给且不一致**当场拒绝**（与 `--channel` / `GENEBENCH_CHANNEL` 同一套纪律）。
> **不给就是双机** —— 单机用户忘了给，会得到一条 `ssh` 到发布方执行面的命令。
> 形态影响的只有**两步**：① exec 树与 bundle 怎么上执行面（双机 `ops/push_bundle_to_f02.sh` /
> `ops/push_exec_to_f02.sh`；单机 `runner/placement.py` **本地落位**，调同一批门、
> 同一份实现、同样顺序），② 真跑的 inner 是 `ssh` 还是本机 `bash -c`。
> 其余（出集、守门、网关锁、结算、出表）两种形态**同一份实现**。
> **判据里没有** hostname / `uname` / 路径存在性嗅探 —— 那正是 2026-09-14 这一轮在修的病：
> 判据一旦依赖「这台机器像不像发布方」，它在 Linux 上就永远是绿的。

<!-- Y1-2026-09-11 -->
> **2026-09-11 恢复（卡 Y1 端到端实测）**：这句话**重新成立**。
> 2026-09-10 曾有一条更正说它不成立 —— 理由是网关的 import 链穿到了答案面
> （`gateway/sim_engine.py` → `reference.artifact_schema`），而形态① 要求网关与容器同机。
> 那条路已经拆掉：三个常量搬进**零依赖**的 `genetask/s8_contract.py`，
> 今天 `gateway/**` 里一条 `import reference` 都没有（`ops/test_s8_contract.py` 用 AST +
> 干净子进程真 import 两头钉着）。
> **形态 ① 已经在一台机器上整条跑过**：解包 → 起网关（本机 LAN 地址）→ 建 harness 镜像 →
> 落 secrets → 3 题双臂真跑 → 结算 → 出表。逐步证据在 `ops/reports/rehearsal_v2.md`。

一次真跑起两个容器（这是「双容器」的由来，两种形态都一样）：

* `task` —— 被测 agent，接 `gb_task` 网（`internal: true`，**没有任何出口**）；
* `gateway` —— 出向边车，接 `gb_task` 与 `gb_egress` 两张网，是任务容器**唯一**的出口。
  它同时干三件事：反代数据网关、反代模型 API（替换占位 key、记 `llm_log`、卡预算）、
  做 CONNECT 代理并按白名单拒绝一切其它出站。

模板在 `runner/c41/runner_core.py::COMPOSE_TMPL`，注入器 `runner/inject.py` 逐 run 渲染。

### 1.2 前置

| | 数据面 | 执行面 |
|---|---|---|
| Python | 外部 **3.12+**；本项目内部是 3.10。装在 **`$GB/env`**（独立环境；**不要装进系统 python**）—— 落点不是随便挑的，`genebench_config.PYTHON` 写死是 `$GENEBENCH_ROOT/env/bin/python`，`ops/run_joblist.py` 起子进程就用它 | 只要 python3（跑 `exec/ops/run_f02_a1.py`） |
| 容器 | 不需要（f01 上根本没装 docker） | docker ≥ 24 + compose v2（实测 docker 29.1.3 / compose 2.40.3） |
| sudo | 不需要 | 不需要（用户要在 `docker` 组里） |
| 磁盘 | 实测 `$GB` 全树 99 GB（私有快照 18 GB + 公开通道 17 GB + 出集/暂存/日志/发布包）；**留 200 GB** | 每批 run 目录几百 MB |
| 内存 | ≥ 30 GB（gold 重算峰值可到 22 GB，必须带 `--spill-root`） | ≥ 16 GB |
| 网 | 只监听 LAN 显式地址，**绝不 0.0.0.0** | 构建期要能出网（PyPI / npm）；运行期只放行模型 API 域名 |

**权限**：`$GB` 及其下每一个目录必须是 `0700`。本机 umask 常常是 002，裸 `mkdir` 会产出 0775 —— 
那会让网关**起不来**（见 §7.6）。建目录一律用 `genebench_config.create_dir()`，
每个进程入口调一次 `harden_umask()`。


<!-- Y1-2026-09-11 -->
**「独立环境」怎么建出来 —— 这一条以前只写了结果，没写做法（卡 Y1 演练的第一处卡点）。**
在一台**没有 root** 的机器上（执行面通常正是这样），`python3 -m venv` 与 `python3 -m pip`
**两个都没有**（实测 Ubuntu 24.04：`ensurepip is not available` + `No module named pip`），
而装 `python3-venv` / `python3-pip` 要 `apt` 要 root。不用 root 的办法：

```sh
curl -sSL -o get-pip.py https://bootstrap.pypa.io/get-pip.py
python3 get-pip.py --target <某处>/pipself --no-warn-script-location
PYTHONPATH=<某处>/pipself python3 -m pip install --target <某处>/site \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    fastapi uvicorn pandas pyarrow duckdb pyyaml
PYTHONPATH=<某处>/site python3 -c "import fastapi,uvicorn,pandas,pyarrow,duckdb,yaml;print('ok')"
```

三件都是踩出来的：

* **六个包就是全部**（`fastapi uvicorn pandas pyarrow duckdb pyyaml`）——
  仓库里**没有** `requirements.txt` / `pyproject.toml`，这一行是演练里一个个试出来的。
* **换国内镜像**（`-i`）。直连 `pypi.org` 在本项目的执行面上走 IPv6 到 Fastly **挂住**：
  实测 **40 分钟 0 字节**（连接停在 `CLOSE-WAIT`），换镜像后 **14 秒**装完。
  不是「慢」，是看起来像死机 —— 而 `--progress-bar off` 让它连个进度条都没有。
* **执行面也要这个环境**：注入器要 `import h11`（它把 h11 复制进 run 目录给边车用）。
  `runner/inject.py` 先找 exec 树里的 `vendor/h11`，找不到才用运行环境里的 ——
  而 **`vendor/` 不在仓库里**，发布包里没有它。上面那条 `pip install` 顺带装上了 h11
  （`uvicorn` 的依赖），所以真跑那条命令要带 `PYTHONPATH=<某处>/site`。

### 1.3 形态 ①：单机双容器

> **先判断你有没有 root。** 这一形态有两条前置**都要机器主人执行**：
> 下面那条 `ufw allow`，以及 §1.3 末尾那道答案面扫描 timer。
> 两条都拿不到就**不要在这一节耗时间** —— 回 §1.1 选形态 ②（跨主机流量不碰宿主防火墙）。
> 卡 6.4 的外部演练就是卡在这里：整条链路一步都没走成，不是因为哪条命令写错了。

**这个形态唯一「不试就不知道」的点是：任务侧容器能不能打到同一台机器上、绑在 LAN 地址的网关端口。**
在本项目的执行面上实测的结论是：

```
容器 → 别的主机的网关（192.168.1.48:18080）    ✅ 通（形态 ② 今天就跑在这条路上）
容器 → 本机自己的 LAN 地址（192.168.1.219）    ❌ 超时（默认 bridge / 自建网 / host-gateway 别名，三种都超时）
宿主 → 本机自己的 LAN 地址                     ✅ 通
```

**「换一个绑定地址」绕不过去** —— 卡 6.4 把探针从 LAN 地址扩到了另外两种
「宿主自己的显式地址」，三种全部超时（同一台执行面，同一时刻，2026-09-08）：

```
容器 → 宿主 LAN 地址        192.168.1.219:18080   ❌ 超时
容器 → docker0 网桥地址     172.17.0.1:18080      ❌ 超时
容器 → 自建网自己的网关地址  172.31.244.1:18080    ❌ 超时
容器 → 别的主机的网关       192.168.1.48:18080    ✅ 通（对照）
宿主 → 上面任意一个          ✅ 通
```

<!-- X1-2026-09-10 --> 放行之后
> **放行之后（2026-09-10，卡 X1 实测）**：用户放行 `172.31.240.0/22 → 18080` 之后，
> **容器 → 本机宿主 LAN 地址 `192.168.1.219:18080` = 200**（对照：容器 → f01 `192.168.1.48:18080` = 200）。
> 上面那张「三种全部超时」的表是**放行前**的结论，别当现状引。
> 复现脚本 `$GB/scratch/X1/x1_probe3.sh`（在执行面上 `sh` 跑）。两条判读规矩：
> ① `gb-base` 镜像里**没有 curl**，用 `python3 -m urllib` 打，否则四行全 000 而那不是网络结论；
> ② 建探针网撞 `Pool overlaps` 就换一个 `/24`（残留的 compose 网会占着 `172.31.240.0/24`），
> 并且**对照那一行不是 200 就整张表作废**。

所以这不是「绑错了地址」，是 INPUT 链把**所有**发往宿主自身的容器流量挡掉了。
复现脚本 `$GB/scratch/6.4/probe2.sh` 与 `probe3.sh`（在执行面上 `sh` 跑）。

原因是宿主防火墙：容器发往**宿主自身 IP** 的包走 INPUT 链，被默认拒收挡掉
（docker 只在 FORWARD 链插规则，管不到这一条）。所以形态 ① 的前置多一条：

```sh
# 放行「容器网段 → 宿主网关端口」。需要 root，本项目没有 sudo，因此这一条要由机器主人执行。
# **端口要跟你实际起的那个网关实例走**，两个值刻意不同（见 genebench_config.py）：
#   公开通道 GATEWAY_PUBLIC_PORT = 18081  ←—— 外部用户拿到的是公开题集，走的就是这条
#   私有通道 GATEWAY_PORT        = 18080      发布方内部那条
sudo ufw allow from 172.31.240.0/22 to any port 18081 proto tcp   # 公开通道
sudo ufw allow from 172.31.240.0/22 to any port 18080 proto tcp   # 私有通道（发布方内部）
```

`172.31.240.0/22` 覆盖注入器分配的任务网 / 出向网（默认 `172.31.240.0/24` 与 `172.31.241.0/24`，
真运行由 `runner/c41/subnets.py::allocate()` 逐 run 分配）。
**不要**改成放行 `any`，也不要把网关改成监听 `0.0.0.0` —— 后者是红线，
`genebench_config.assert_no_wildcard_bind()` 会当场抛。

<!-- H10-2026-09-14 -->
**端口放行错了的失败形态极难认**（2026-09-14 用户点名要写清）：容器起得来、
模型照样调得动，**只有数据网关打不通** —— run 一路空转到 1500 秒墙钟闸、以 `124` 退出，
读起来像「agent 不会做题」。端口从代码现算是 `genebench_config.gateway_port(channel)`
（环境变量 `GENEBENCH_GATEWAY_PORT` 赢过通道默认值）；两个默认值刻意不同的记因写在
`genebench_config.GATEWAY_PUBLIC_PORT` 的注释里：「忘了设端口」的失败形态必须是
**起在 18081**，不能是**抢私有网关的 18080**。

<!-- C2-2026-09-13 -->
> **macOS 上没有 `ufw`，也没有 `systemctl`。** 这一节有两条前置是 Linux 专有的，逐条说 Mac 上怎么办：
>
> **(1) 那条 `sudo ufw allow`：Mac 上不适用，也不需要照搬。**
> Mac 的包过滤是 `pf`（`pfctl`），而且 Docker Desktop 的容器并不直接跑在宿主内核上 ——
> 它们在一层 Linux 虚拟机里，容器打宿主走的是 VM 的网络栈，**不经过宿主的 INPUT 链**，
> 所以「INPUT 链把发往宿主自身的容器流量挡掉」这个 Linux 症状在 Mac 上换了形状。
> <!-- H10-2026-09-14 -->
> **这里以前写着一条本代码根本表达不出来的办法，现在如实改掉。**
> 旧版原话是「Mac 上容器打宿主的规范写法是 host.docker.internal（Docker Desktop 自带的别名）」——
> 在 Docker 的世界里这句话没错，**但这套代码收不下它**：容器要打的网关地址由
> `runner/c41/runner_core.py::gateway_addr()` 定，它**只认 `IPv4:端口`**
> （正则逐字：四段十进制 + 冒号 + 端口），**主机名当场抛 `ValueError`**；
> 而且 `0.0.0.0` / `127.0.0.1` / `localhost` / `::1` 在它的**拒绝名单**里
> （理由：那几个在**边车容器里**指向边车自己，不是数据面那台机器）。
> 所以 `export GENEBENCH_GATEWAY_ADDR=host.docker.internal:18081` **不是「没验过」，是当场拒绝**。
>
> **那 Mac 上到底填什么？** 代码这侧只剩一条可表达的路：填**这台 Mac 自己的 LAN IPv4**
> （`ipconfig getifaddr en0` 拿到的那个），网关也绑同一个地址。
> **这条路我们没有在 Mac 上验过** —— 它要求 Docker Desktop 那层 Linux 虚拟机里的容器
> 能把包送到宿主的 LAN 地址上，而 2026-09-13 的外部验收停在更前面（见 §0.3）。
> **所以这里不给结论，给判据**：真到那一步请自己探一次
> （`gb-base` 镜像里没有 `curl`，用 `python3 -m urllib` 打）；探不通就回形态 ②。
> **这条矛盾本身是一条已知限制**：文档曾给出一条代码无法表达的写法，
> 而代码侧**没有主机名入口** —— Mac 上目前没有任何被验证过的容器→宿主网关路径。
>
> **(2) 隔离判据不因为没有 ufw 而少一层。** 防火墙规则从来就不是隔离判据 ——
> 它解决的是「容器能不能连上网关」，不是「答案面会不会漏进容器」。
> v1.0.16 起隔离的判据是**容器边界**（见 §1.1）：答案面永不挂进 agent 容器，
> 由 `runner/f02/answer_plane_guard.py --mode container` 读 compose 挂载面 + run dir 判定，
> **命中拒绝启动、不删**。这一道在 Mac 上照跑（纯 Python，不依赖 systemd / ufw）。
>
> **(3) 那道每小时的答案面扫描 timer：Mac 上没有 systemd，这一道**确实**少了。**
> `ops/push_bundle_to_f02.sh` 推之前会核执行面上 `genebench-answer-plane-scan.timer`
> 处在 `enabled + active`，不活就拒推 —— Mac 上这条核查过不去。
> **它少了什么**：少的是「万一有人绕过推送脚本把答案面拷过去」的**兜底清扫**，
> 不是主判据（主判据是上面 (2) 的挂载面口径，推送脚本自己也跑 `--mode container` + `--mode tree` 两道）。
> Mac 上的等价做法是把同一支扫描器挂成 `launchd` 的周期任务
> （`~/Library/LaunchAgents/*.plist`，`StartInterval 3600`，调用 `runner/f02/answer_plane_guard.py --mode tree --root <执行面那棵树>`）。
> **`--root` 千万别指到包含 `reference/` 的那一层** —— 它命中即删，会把你自己的答案面整棵删掉。
> 本手册**没有替你写这份 plist，也没有在 Mac 上验过它**；在它装好之前，
> 你少的是第三道兜底，**前两道仍在**。

放行之后，还要把三个地址换成本机的。**先看一眼你的树上有没有环境变量那条路**：

```sh
$PY -c "from runner.c41 import runner_core as RC; print(hasattr(RC,'gateway_addr'))"
```

* 打印 `True` —— 网关上游地址已经是环境变量（`GENEBENCH_GATEWAY_ADDR`，形如 `IPv4:端口`）。
  **不要改常量**，起真跑之前 `export GENEBENCH_GATEWAY_ADDR=<本机 LAN>:18080` 就行；
  形状不对它会当场抛，不会静默回落到默认值。
* 打印 `False` —— 老树，只能改常量。

| 改哪儿 | 现值 | 单机形态改成 |
|---|---|---|
| `genebench_config.py::GATEWAY_HOST` | `192.168.1.48` | 本机 LAN 地址 |
| `runner/c41/runner_core.py` 里的网关地址常量（老树叫 `GATEWAY`，有 `gateway_addr()` 的树上叫 `GATEWAY_DEFAULT`） | `192.168.1.48:18080` | `<本机 LAN 地址>:18080`（或改用上面那个环境变量） |
| `runner/c41/runner_core.py::LAN` | `192.168.1.219` | 本机 LAN 地址（容器端口映射一律显式绑它） |
| <!-- Y-2026-09-13 -->`ops/run_joblist.py::F02`（跑批时 ssh 到执行面的目标） | `ljn@192.168.1.219`，**读 `GENEBENCH_F02`** | 不必改常量：`export GENEBENCH_F02=<你>@127.0.0.1` |
| `ops/score_runs.py::F02`（`--remote` 不带主机段 / `--remote-host` 的默认远端） | `ljn@192.168.1.219`，**读 `GENEBENCH_F02`** | 同上（同机结算另有 `--remote-host local`，见 §6.1） |

改常量这条路改完 `ops/test_*` 里没有任何断言会红 —— 它们比的是「代码与代码」，
不是「代码与这台机器的 IP」。

**验证改对了没有**：出集之后本地干跑一次，读生成的 `compose.yml` ——
现场唯一可信的证据是那一行 `--gateway`，不要拿常量反推。

```sh
$PY ops/run_f02_a1.py --dry --bundle <bundle> --manifest <manifest> \
    --config-id cfg-codex-deepseek --arms strict,open \
    --provider-root $GB/snapshots/v1/qlib_provider --run-root /tmp/genebench_dry
grep -n -- --gateway /tmp/genebench_dry/*/runs/*/compose.yml
```

另外两件事 —— 第一件**两种形态都要读**（上执行面走哪个入口），第二件是形态 ① 特有的（那道兜底扫描装在哪）：

* <!-- H10-2026-09-14 按形态分岔 -->**上执行面这一步：两种形态两个入口，守门是同一批。**
  * **单机形态（`--topology single`）：不走推送脚本，也不需要 `GENEBENCH_F02`。**
    入口是 `runner/placement.py`：exec 树用
    `python -m runner.placement --topology single --place-exec --with-launch-data`；
    bundle 由 `ops/run_joblist.py --topology single` 在六段里自己落位。
    **这条路一条 `ssh` 都不发**，所以**不必**配「免密 ssh 到本机」。
    旧版这里写的是「单机形态设成 GENEBENCH_F02=<你>@127.0.0.1，并且要能免密 ssh 到本机」——
    那是**双机的退化写法**（还要求远端有 systemd timer、要求造得出发布方那个执行面根，
    两件在 macOS 上都不成立），**不是**今天的单机路径。
  * **双机形态：`ops/push_bundle_to_f02.sh` 与 `ops/push_exec_to_f02.sh`，一个字没变。**
    用环境变量 `GENEBENCH_F02` 指目标（默认 `ljn@192.168.1.219`）。
    <!-- Y-2026-09-13 -->**读这个变量的一共五个**：上面两个 `.sh`、`ops/api_usage.py`，
    外加**跑批与结算**这两个 —— `ops/run_joblist.py::F02` 与 `ops/score_runs.py::F02`。
    后两个**此前是写死的**（外部机器上设了变量也不跟着走，2026-09-13 实测），现在同源；
    **不设变量时默认值逐字不变**，由 `ops/test_Y.py` 钉住。
  * **两种形态都不许的是同一件事：手工 `cp` / `rsync` 绕过守门。**
    历史上一次手写 `rsync` 父目录就把参考解推上了执行面。
    **单机的本地落位不算「绕过」** —— 它调的是同一批门、同一份实现、同样顺序。
    v1.0.16 起守门各跑**两道**：`--mode container`（挂载面口径，主口径）+
    `--mode tree`（树口径，第二道）；**两条路都是这两道**。
* **执行面那道每小时兜底扫描必须是活的**：`ops/push_bundle_to_f02.sh` 在推之前会检查
  执行面上 `genebench-answer-plane-scan.timer` 处在 `enabled + active`，不活就拒推。
  **「门有了、门后没人」比没有门更危险**，所以这条检查不许跳过，**双机形态一个字没松**。
  <!-- H10-2026-09-14 -->**单机形态下这一件如实说清**：本地落位用的是**落位即扫**
  （容器口径 + 树口径两道门在**每一次落位**时同步跑），**不是**每小时一次的周期复查。
  差别就落在「**落完了、还没跑**」那段时间窗里 —— 那段时间没有第二次复查。
  主判据（挂载面口径）**一条没松**。Linux 上想把周期复查补回来，可以自己把
  `runner/f02/answer_plane_guard.py --mode tree --root <执行面那棵树>` 挂成 systemd timer；
  macOS 上没有 systemd，等价物是 `launchd`（见上面 (3)）。
  **`--root` 千万别指到包含 `reference/` 的那一层** —— 树口径命中即删。
  **这一件本轮不做，登记 v1.1**（用户 2026-09-14 裁定 ②）。

> <!-- Y1-2026-09-11 -->
> **状态（2026-09-11，卡 Y1）：形态 ① 已端到端跑通。** 在执行面那台机器上，
> 只用发布包解出来的树：解包 → 起网关（`GATEWAY_HOST` 改成本机 LAN，`/healthz` **5 秒**回 200，
> `channel=public`、`bind=192.168.1.219:18080`、**不是** `0.0.0.0`）→ 建 harness 镜像 →
> 落 secrets → **3 题双臂真跑** → 结算 → 出表。逐步证据与 findings 在 `ops/reports/rehearsal_v2.md`。
>
> **容器 → 本机宿主网关的三行对照**（同一时刻、同一台机器，2026-09-11）：
>
> ```
> 容器（放行网段 172.31.243.0/24） → 本机宿主 192.168.1.219:18080   ✅ 200 public
> 容器（放行网段）                  → 别的主机  192.168.1.48:18080   ✅ 200（对照）
> 容器（**默认 bridge** 172.17/16） → 本机宿主 192.168.1.219:18080   ❌ 超时
> ```
>
> 第三行是判别力所在：那条 `ufw allow from 172.31.240.0/22` **只放行注入器分配的任务网段**，
> 默认 bridge 不在里面。**拿默认 bridge 探针去测形态 ① 会得到「不通」，而那是错的结论。**
>
> **还有两条要连着读**：
> <!-- H10-2026-09-14 -->
> ① **放行的端口必须与你实际起的那个网关实例一致。** 这一条以前写成
> 「那条 ufw 规则把端口写死成 18080 …… 单机形态请把网关就绑 18080」——
> 那是 2026-09-11 演练当时的做法（那次起的实例绑的就是 18080）。
> **现在的口径是跟着通道走**：公开通道默认 `GATEWAY_PUBLIC_PORT = 18081`、
> 私有通道 `GATEWAY_PORT = 18080`；上面那段 `ufw allow` 两条都给了，
> 你只需要放行**自己真起的那一条**。外部用户手上只有公开题集，走的就是 18081。
> ② 本机那道每小时的答案面扫描 timer（下面第二条）**扫的是 `--root` 指的整棵树，命中即删**。
> 单机形态下答案面与执行面在同一台机器上，**`--root` 千万别指到包含 `reference/` 的那一层**——
> `reference` 是它的「答案面目录名」之一，指错了它会把你自己的答案面整棵删掉。
> 只指执行面那棵（本项目是 `/data/genebench_runner`）。
> 另：发布包里有**两份带合成 gold 串的测试文件**（`ops/test_answer_plane_guard.py`、
> `ops/test_inject.py`），落在扫描根里会被当场删掉 —— 把它们放在扫描根之外。
>
> 以下为 2026-09-10 的原文（那时卡在「起网关」，见 §1.1 的更正）：
> **状态（2026-09-10 更新，卡 X1）：仍未端到端；卡住的那一件换了。**
> 已验：容器打得到本机宿主网关（放行之后 200）、出集与推送两步在单机落点上真跑全绿
> （含推送守门对执行面 `genebench-answer-plane-scan.timer` 的 `enabled + active` 核查 —— f02 上它是活的）。
> **现在卡在「起网关」**：`gateway/sim_engine.py` 从 `reference.artifact_schema` import 三个常量，
> 而 `reference/` 不许进执行面。这一处是**唯一**的一处（`grep -rn "from reference" gateway/ snapshots/`），
> 被引的是协议 schema 不是参考解（`answer_plane_guard` 单独扫它 0 命中），
> 但要不要因此松开那条红线**是一次裁定**，不是配置。两个方向与倾向见
> `ops/reports/public/single_node_form1.md` §4。真跑 / 结算 / 出表三步因此一步都没走。
>
> 以下为原文（放行之前的判断）：
> **状态：未端到端验证。** 上面的探针结论是实测的，三处常量改动与两条注意事项是从代码读出来的；
> 但形态 ① 的完整链路（起网关 → 出集 → 推送 → 真跑 → 结算）还没有在一台机器上整条跑过。
> 本项目的执行面没有 sudo，放行不了那条防火墙规则。

### 1.4 建数据面

两条路：拿现成的冻结包，或者自己重建。

<!-- C2-2026-09-13 -->
**(a) 拿冻结包（形态 A）** —— **这条路今天通了**（2026-09-13）。
三个附件都已经挂在 GitHub Release `v1.0.16` 上，**匿名就能下，不需要 token**；
2026-09-13 的 macOS 外部验收从其中前两条地址下回来，逐件核 sha256 **两件都对**
（命令是 `sha256sum -c`；**macOS 的 `/usr/bin` 里没有 `sha256sum`**，一定在的是 `shasum -a 256 -c`，
两者的逐例实测与唯一那处行为差异在 README §1.5），
解包后逐件校验 provider **28,658/28,658 OK**、gold 子集 **46/46 OK**。
下载地址、字节数与 sha256 的单一来源是 `ops/release/attachments.json`，
可粘贴的下载与逐件校验命令在 README §2.1a（现在是三件）。
（此前本节写着「今天走不通，见 §0.1 第 1 条」—— 那一条挡的是**许可**，2026-09-11 用户裁定 ⑨ 已闭合；
包也早就从 `_staging_unpublished/` 出来了。留这一句是给读过旧版的人看见它去哪了。）

**还有第三件附件** —— README §2.1a 的 `curl` 块里第三条就是它。
公开题集树（`reference/tasks/public/v1.0-smoke-public/`）与 `calibration.json` / `epsilon/`
按红线 6 落在 `$GENEBENCH_ROOT` 之下、在仓库之外，而公开树是 `git archive HEAD` 打的 ——
射程里没有它们。只落位那两个附件的机器上，`ops/freeze_v10.py --check-all` 的
**公开任务集轴核不绿**（差异全部落在 `channel_fixtures/`）；私有轴与参考面轴一致，
包的逐件 sha256 全过 —— **不是下载损坏**。
这一堆已经打成 `genebench_public_runtime_v1.tar.gz` 登记进
`ops/release/attachments.json`，落位之后三条轴实测全绿；
**2026-09-13 下午它也传上了同一个 Release `v1.0.16`、匿名可下**，那条记录的
`download_url` 已回填（登记表里 `download_url` 是空串的条目才是「登记了但还没上传」
—— 现在三件都不是）。逐字地址、字节数、`sha256` 与校验 / 落位命令都在 README §2.1a。
**附件有几件、各自的 sha256 与地址，以 `ops/release/attachments.json` 为准**，不要数 README 的表。

打包与逐文件比对的命令（**发布方用**）：

```sh
$PY ops/release/pack_public_provider.py                                  # 打包（★未实跑）
$PY ops/release/pack_public_provider.py --compare <某个 SHA256SUMS>      # A↔B 逐文件比对（★未实跑）
```

**(b) 自己从公开源建（形态 B）** —— 这是外部运行者今天真正能走的路。
数据源是 baostock（任何人都能自己拉），整条链在它上面从零长过第二遍，结构性结论一条没变
（对账见 `ops/reports/public/reconciliation.md`）。

```sh
$PY ops/build_public_channel.py --dry-run     # 先看要做哪六步；什么都不动
$PY ops/build_public_channel.py               # 建数据面（可续跑，已完成的步自动跳过）（★未实跑）
$PY ops/build_public_channel.py --step provider --force          # 只重跑某一步
$PY ops/build_public_channel.py --step fetch --force-trading-hours   # **明知在交易时段**仍要拉数（★未实跑）
```

六步是 `fetch → tables → gate → tradability → provider → verify`。
拉数那一步约 5.3 分钟；**交易时段不拉**（真要拉加 `--force-trading-hours`，
那意味着你拉到的是一份边界不稳的数据）。

数据面建好之后是**重建链**（universe → gold → crosscheck → epsilon → ic_epsilon → calibration，
全链约 4 小时 15 分）：

```sh
$PY ops/run_public_chain.py --dry-run                                  # 只说要做什么
$PY ops/run_public_chain.py                                            # 全链，已完成的步跳过（★未实跑）
$PY ops/run_public_chain.py --step gold --universes csi300 --force     # 重跑一个宇宙的 gold（★未实跑）
$PY ops/run_public_chain.py --step gold --spill-root $GB/scratch/mine/spill  # 换面板暂存根（★未实跑）
```

`--spill-root` 默认开着，**别关**：792 个面板同时压内存时 csi1000 常驻 22 GiB，
30 GiB 的机器上被 OOM killer 收走过两次。
`ic_epsilon` 那一步**退出码 1 是正常的**（只要还有指标超阈就返回 1），脚本按这条判读。
这条链不打网关，不需要网关锁。

产物落 `$GB/snapshots/public_v1/`，标定文件是 `$GB/snapshots/public_v1/calibration.json`。
取三个关键数用这条命令，**不要手抄**：

```sh
$PY -c "import json;d=json.load(open('$GB/snapshots/public_v1/calibration.json'));\
print('tau =',d['tau']['value']);\
print('eps =',{f:(len(v['calibrated']),v['usable']) for f,v in d['epsilon']['by_frequency'].items()});\
print('ic_family =',d['epsilon']['ic_family']['usable_metrics'])"
```

数据卡在 `ops/data_cards/public_channel.md`：每个数后面跟一条 `<!-- src: 文件:键路径=值 -->`，
逐条由测试核对 —— 引数就引那份，别自己算一遍。

**(c) 引用一份已经建好的快照（★2026-09-10 实跑验过，卡 X1）** —— 隔壁机器上已经有一份建好的
快照时走这条：**不重建、不解发布包**，省掉 (b) 那条约 4 小时 15 分的重建链。

```sh
ROOT=$GB/scratch/mine/refroot                     # 一个新的 GENEBENCH_ROOT，随便挑个位置
mkdir -p $ROOT/snapshots/public_v1 $ROOT/logs $ROOT/results && chmod -R go-rwx $ROOT
ln -s <那份现成的>/public_v1/tables $ROOT/snapshots/public_v1/tables      # ← 引用，不复制
cd $GB/repo && GENEBENCH_ROOT=$ROOT GENEBENCH_CHANNEL=public \
  GENEBENCH_GATEWAY_PORT=18082 GENEBENCH_GATEWAY_BACKEND=snapshot \
  PYTHONDONTWRITEBYTECODE=1 $PY -m gateway.run --workers 1
curl -sS http://$(hostname -I | awk '{print $1}'):18082/healthz          # 核 tables_dir 是不是那份
curl -sS "http://<本机>:18082/calendar?start_date=20260701&end_date=20260710&as_of=20260731"
```

实测（f01，2026-09-10）：**50 秒**起来，`/healthz` 200 且自报
`tables_dir=$ROOT/snapshots/public_v1/tables`、`exposed_datasets` 五个（证明它真读了那份 `manifest.json`），
`/calendar` 取回 **10 行真数据**。

四条要点（都是踩出来的，别省）：

* **目录布局必须照 `$GB` 的约定**：`<root>/snapshots/<版本>/tables`。版本目录名**按通道取**
  （`private` → `v1`，`public` → `public_v1`；`genebench_config.snapshot_tables_dir()`）。
  指错通道的表 = 「题集是公开的、读的表是私有的」，报告头会照实打印通道，而数字看起来都对。
* `tables` 那一层用**软链**就行，网关跟着走；但 `<root>` 及其下每个目录仍要 `0700`
  （否则 §7.6 那条：网关拒绝启动）。
* **端口显式错开**（`GENEBENCH_GATEWAY_PORT=18082`），别和生产网关抢 18080。
* 网关真正要读的只有 `tables_dir`，不是整棵快照树 —— 实测 `$SNAPSHOTS/v1/tables` **1.5 GB**、
  `$SNAPSHOTS/public_v1/tables` **447 MB**，而整棵 `public_v1` 是 **16 GB**。
  **注入器另外要 `qlib_provider` 树**，它按通道核 sha256 根 —— 换通道就对不上
  （证据 `ops/reports/m6_public/plane_probe.md` ②）。三个地址常量与那条 ufw 规则见 §1.3。

### 1.5 起网关，并确认它真的起来了

**生产（private）网关**是一个 systemd 用户单元 `genebench-gateway.service`，绑
`192.168.1.48:18080`。它的 `ExecStartPre` 就是权限守门（§7.6），
所以起不来的第一嫌疑永远是权限而不是网关本身。

**公开（public）网关**用脚本起停，绑 `192.168.1.48:18081`：

```sh
$PY ops/guard_modes.py --harden      # 先收紧权限，否则下一条可能被 $GB 下任何人留的 0644 挡掉
ops/public_gateway.sh start
ops/public_gateway.sh status
ops/public_gateway.sh stop
ops/public_gateway.sh run -- <你的命令>     # 拿网关锁 → 起 → 跑 → 停（跑批用这个）
```

`start` 要等到 41 秒左右才开始监听（import 链是 fastapi + pandas + pyarrow + duckdb），
脚本等 180 秒。它有三条守门，都不是注释：端口不许等于生产端口；起来之后核
`/healthz` 的 `channel` 必须是 `public`；`stop` 之后核端口真的释放了。

<!-- C2-2026-09-13 -->
**macOS 上没有 `ss`，也没有 `setsid`** —— 这两个工具原本出现在 `ops/public_gateway.sh` 的三处：
查端口占用、查监听进程的 pid、把网关脱离终端。**脚本已经自己分好岔**（2026-09-13，卡 C2）：

| 干什么 | Linux | macOS 上换成 |
|---|---|---|
| 查端口在不在监听 | `ss -ltn "sport = :PORT"` | `lsof -nP -iTCP:PORT -sTCP:LISTEN`（都没有就退回 `nc -z`） |
| 查占着端口的 pid | `ss -ltnp` | `lsof -nP -iTCP:PORT -sTCP:LISTEN -t` |
| 脱离终端起进程 | `setsid nohup …  &` | `nohup … &`（bash 的 job control 在脚本里本来就是关的，`nohup` 足够） |

选哪一支由 `command -v` 当场判，不看操作系统名 —— 装了 `ss` 的 Mac 或没装 `ss` 的精简 Linux 都对。
**2026-09-13 在 macOS 上原样跑过一遍**：`start` 起得来、`/healthz` 回 200 且 `channel=public`、
`status` 认得出监听、`stop` 之后端口确认释放。

还有一件 Mac 上绕不过去的事：`genebench_config.py::GATEWAY_HOST` 是**常量，没有环境变量可以覆盖**
（端口有 `GENEBENCH_GATEWAY_PORT`，地址没有）。本脚本的绑定地址就是从它读的，
所以 Mac 上要先把它改成本机地址（只在本机自测就 `127.0.0.1`；容器要打它就用本机 LAN 地址）。
`ops/selfcheck_public.py` 的第 6 项会直接告诉你「这台机器绑不上它」。

**怎么算「起来了」**（两种形态、两条通道都是这一条）：

```sh
curl -sS --max-time 5 http://192.168.1.48:18080/healthz     # private
curl -sS --max-time 5 http://192.168.1.48:18081/healthz     # public
```

返回里必须同时对上三样：`"ok":true`、`"freeze_line":"2026-07-31"`、`"channel"` 是你以为的那条。
**只看 `ok:true` 不够** —— 起了个私有实例却以为在跑公开通道，是这一步最贵的错：
数字看起来全对，只是来自另一份数据。

六个数据端点怎么调（八条可粘贴的 curl）在 `ops/reports/public/data_channel_notes.md` §7.1；
端点的完整契约在 `integrations/P2_CONTRACT.md` §2。

---

## 2. 加配置（新模型 / 新 `config_id`）

一条「被测配置」= 一个 `config_id`，它是主表的切片键，也是 `x-genebench-config-id` 头的值。
配置是**数据不是代码**：加一条只改一个 `config.yaml`，不动 `runner/registry.py`。

### 2.1 落点与七个键

落在被测系统自己的目录里：`harnesses/<id>/config.yaml`（通用 harness）或
`integrations/<id>/config.yaml`（专用系统）。键集是**闭集** —— 少一个或多一个都当场红：

| 键 | 说明 |
|---|---|
| `config_id` | 主表切片键。全仓唯一 |
| `harness` | 人读的 harness 名（内置三条要求互不相同） |
| `model` | 模型名 |
| `base_url` | OpenAI 兼容端点。**必须 https**；主机名由它派生，不另抄一份 |
| `api_key_env` | 装凭据的**环境变量名**，必须以 `_API_KEY` 结尾。**只有名字，没有值** |
| `note` | 一句话说明 |
| `enabled` | 布尔。`true` 合并进 `CONFIGS`，`false` 只登记进 `PENDING_CONFIGS` |

「多一个键」在这里是**静默生效**的失败形态 —— 写的人以为它生效了，其实没有；
所以键集判据是「恰好相等」，不是「包含」。

### 2.2 `enabled` 的含义

* `enabled: true` → 进 `CONFIGS`，`by_id()` 找得到，能出现在作业清单里。
* `enabled: false` → 进 `PENDING_CONFIGS`，`by_id()` 抛错并告诉你「登记了但没开」。
  **登记而不生效是一个显式状态，不是遗漏** —— 链路全通但卡在上游协议的 harness 就该是这个状态。

两种状态**都要过**「https / `_API_KEY` 结尾 / base_url 不指向行情源」这三条判据：
翻开关的那一刻没有人会重新审一遍 `base_url` 指到哪。

### 2.3 同一模型约束（`assert_registry_sane`）

`runner/registry.py` 在 import 期跑 `assert_registry_sane()`，其中一条是
**内置三条配置必须同一模型**。理由写在模块 docstring 里：v1.0 是**验收配置**不是实验设计，
固定模型效应之后，主表上暴露的才只有 harness 与协议臂的差异。
`PURPOSE` 是 `"acceptance"`，改这个字符串会被当场拒 —— 要跑配置网格是另一张表，不是改这里一行。

数据里的 `config_id` 与内置三条**重名即红**：内置的不许被数据悄悄换掉。

### 2.4 key 落在哪

**凭据不进仓库、不进日志、不进产物。** 真 key 只有一个落点：

```
执行面主机的  ~/.config/genebench/secrets.env     权限 0600
内容形如      DEEPSEEK_API_KEY=<值>
```

`ops/run_f02_a1.py` 从这里读，放进**本进程环境**，再由 compose 以 `${...}` 引用的形式
只注给**边车**服务。任务容器的 `environment` 里只有占位 key，边车转发时替换成真值。
于是被测 agent 拿不到真 key，而 usage / Steps / 预算闸全都有落点。
`compose.yml` 与 run 目录里都不会出现真值。

新模型要新的 key：在 `config.yaml` 里写 `api_key_env` 的**名字**，把值加进 `secrets.env`。
**不要 `cat` 它、不要 echo、不要复制到别处。**


<!-- Y1-2026-09-11 -->
#### 2.4.1 格式、位置、权限（⑱）

```
位置    <执行面主机>:~/.config/genebench/secrets.env
权限    0600（`ops/run_f02_a1.py::load_key` 先核权限再读；不是 0600 直接 SystemExit）
属主    跑 runner 的那个用户
格式    每行 `<环境变量名>=<值>`，`#` 开头是注释，不要加引号、不要 `export`
```

样例（**占位值，不是真 key**）：

```sh
install -d -m 700 ~/.config/genebench
cat > ~/.config/genebench/secrets.env <<'EOF'
# 一个配置一把 key。变量名 = harnesses/<id>/config.yaml 里 api_key_env 写的那个名字。
DEEPSEEK_API_KEY=<把你自己的 key 贴在这里>
EOF
chmod 600 ~/.config/genebench/secrets.env
```

**一个配置一把 key**：`config.yaml` 里写的是**变量名**（`api_key_env`），不是值；
加一个模型就在这个文件里加一行同名变量。仓库里、日志里、产物里都不许出现值本身。

**真 key 怎么进到模型调用里（三段，中间没有第四段）**：

1. `run_f02_a1.py::load_key()` 读 `secrets.env`，把值放进**本进程**的 `GENEBENCH_MODEL_API_KEY`——
   **不回显、不写盘**；
2. compose 以 `${GENEBENCH_MODEL_API_KEY}` 的形式**只**注给**出向边车**那个服务；
3. 边车转发模型请求时，把任务容器发来的**占位** key 换成真值。

**怎么验证容器里确实看不见**（一条命令，读的是真跑留下的 `compose.yml`）：

```sh
grep -n "API_KEY" <run_dir>/compose.yml
```

对的样子长这样（2026-09-11 实测，`s1-cor-01.strict.cfg-codex-deepseek.r01`）：

```
34:      GENEBENCH_MODEL_API_KEY: "${GENEBENCH_MODEL_API_KEY}"   ← 边车服务；是**引用**，不是值
71:      OPENAI_API_KEY: "sk-genebench-placeholder"               ← 任务容器：占位
72:      LLM_API_KEY: "sk-genebench-placeholder"                  ← 任务容器：占位
```

**判据是「34 行那一处是 `${...}` 而不是一串字符」**：`compose.yml` 落在 run 目录里，
真值若出现在这里就等于写进了盘、写进了备份、写进了你发给别人的 run 包。
容器跑完 `down -v`，所以容器**里面**没法事后 `docker inspect`；`compose.yml` 是留得下来的那份证据。
占位串 `sk-genebench-placeholder` 是**公开的**，它出现在任何地方都不是泄漏（`harnesses/README.md` §2.1）。

### 2.5 白名单同源

出向白名单**只放模型 API 域名**。行情 / 新闻源一律不得入表 —— 放进去等于让被测系统绕过数据面取数：
网关的 `access_log` 会干干净净，前视探针全绿，而 as-of 强制已经失效。

白名单有两份，必须同源：

* `runner/registry.py::collect_egress_hosts()` —— 从所有 `enabled: true` 的配置的 `base_url` 现算；
* `runner/c41/egress_proxy.py::MODEL_API_ALLOW` —— 边车真正执行的那份。

**键集相等**（不是包含）是一条断言。加了新模型域名而只改一处，判据当场红 —— 这是设计。
看一眼现算的那份：

```sh
$PY -c "from runner import registry as REG; print(REG.collect_egress_hosts())"
```

`runner/registry.py::MARKET_DATA_HOSTS` 是反向清单：`base_url` 落在里面直接拒绝。

---

## 3. 加一个通用 harness（P1）

**什么时候该加 harness，而不是接一个专用系统**：

* 你要接的东西是一个**通用 agent 壳**（CLI / 框架），它自己不懂量化，
  题面给什么它做什么，模型端点可以由环境变量指走 —— 加 **harness**（P1）。
* 你要接的东西是一个**专用系统**（有自己的数据层、自己的研究循环、自己的产物格式），
  需要**改它的代码**才能经网关取数、才能吐出合规产物 —— 走**接入**（P2，见 §4）。

判别只有一条：**要不要动被测系统自己的代码**。要动就是 P2。

四件文件，缺一件判据就红：

```
harnesses/<id>/
  Dockerfile      # FROM gb-base:bookworm-r1，只装 harness 本身
  launch.json     # 镜像 + 容器内命令 + 必需环境变量
  config.yaml     # §2 的七个键
  README.md       # 这个 harness 怎么把模型指到 OpenAI 兼容端点、已知限制
```

**先跑判据再往下走**：

```sh
$PY -m pytest ops/test_harness_contract.py -q -p no:cacheprovider
```

怎么写这四件、`$` 为什么一律写 `$$`、镜像怎么构建拿 digest、`llm_log` 的形状 ——
全部在 **`harnesses/README.md`**（§0 是十分钟版）。本手册不重复它，只给路口。

同步到执行面 + 构建：

```sh
ops/push_exec_to_f02.sh --dry-run --with-launch-data      # 先看清单
ops/push_exec_to_f02.sh --with-launch-data                # 真推（**必带这个开关**）
ssh $F02 "cd /data/genebench_runner/exec && sh harnesses/build.sh <id>"
```

`harnesses/build.sh` 的 tag 从 `launch.json` 的 `image` 字段取（不是拼 `gb-<id>-u:r1`）——
让构建与启动读同一个字段，「构建成功了、跑的还是旧镜像」这个坑就不存在。
构建期可以出网（PyPI / npm），但 **docker.io 是不通的**：`FROM` 只能是本机已有的统一基座。

---

## 4. 接一个专用系统（P2）

被测方自己写代码、自己调网关。三份文档，各管一段：

| 文档 | 给谁 | 管什么 |
|---|---|---|
| `integrations/P2_CONTRACT.md` | 被测系统作者 | 13 个端点逐个的参数 / 必填 / 返回形状 / 错误码、`as_of` 三层上界与六条越界 reason、`/sim/*` 会话语义、artifact 的位置与三态、四条禁止事项 |
| `integrations/README.md` | 同上 | 接入八步，每步一条可复制命令；取数垫片 `genebench_client`；常见失败清单；成本记账 |
| `integrations/example_minimal/` | 同上 | 30 行的最小可跑示例（判据核对手册里的摘录与文件逐字一致） |

运行者在这一段要知道的只有三件事：

1. **五件套**：`integrations/<id>/{Dockerfile,launch.json,config.yaml,pin.json,README.md}` + `glue/`。
   比 harness 多一个 `pin.json`（钉住上游版本），因为 P2 要声明「接的是上游的哪一版」。
2. **上游内核一个字节都不许改**。接线只能用上游自己的扩展点（注册表 / 构造形参 / 子类覆写 / monkeypatch）。
3. **判据先跑**：

```sh
$PY -m pytest ops/test_p2_contract.py -q -p no:cacheprovider
$PY -m pytest ops/test_integrations_readme.py -q -p no:cacheprovider
```

已接进来的六个系统各自有一份 `README.md` 的「复现」一节，逐字可抄；
覆盖矩阵在 `integrations/COVERAGE.md`（格值**只写实测过的**，「应该能跑」不是一个格值）。

---

## 5. 跑一批（作业清单）

一批真跑 = **一份清单 + 一个结果库**，不是一条 `for` 循环。

### 5.1 四个入口

| 入口 | 干什么 | 落点 |
|---|---|---|
| `ops/joblist.py` | 矩阵 yaml → `jobs.jsonl`：一行一个 `(task, arm, config, seed)`，带状态机 | `$GB/runs_in/<batch>/jobs.jsonl` |
| `ops/run_joblist.py` | 按清单跑六段流水线；终态跳过、可续跑 | `ops/reports/<batch>/` |
| `ops/results_db.py` | 结果库（追加式），四条版本轴缺一即拒 | `$GB/results/v1/` |
| `ops/mk_tables.py` | 从库出三张表，三种格式 | `ops/reports/<batch>/table_*.{csv,md,tex}` |

### 5.2 矩阵 yaml 的字段

> ✅ **`max_tokens` 这一行现在不要写**（2026-09-10，N-388 已裁定）。默认档已经抬到
> 100 次 / **6,000,000** tokens，`ops/joblists/v1demo.yaml` 里那一行已经删掉。
> 写 `max_tokens: 3000000` 现在是**把预算压低**：显式给的逐键赢过档位，
> 3M < 默认档 6M，S4 / S7 更是把自己的 9M / 18M 一起打回去。
> 历史读数不动：`ops/reports/v1demo/` 那 8 个 run 是在 600k 默认档下跑的，8/8 撞闸（见 §5.3）。

照抄 `ops/joblists/v1demo.yaml` 改。键集是**闭集**：少一个必填键或多一个不认识的键，`gen` 当场拒
（多出来的键静默生效是最坏的一种）。

| 字段 | 必填 | 怎么填 |
|---|---|---|
| `name` / `batch` | ✅ | 批名。`batch` 决定 `$GB/runs_in/<batch>/`、`ops/reports/<batch>/`、执行面上的 run 根 |
| `configs` | ✅ | `enabled: true` 的 `config_id`（例：`cfg-codex-deepseek`） |
| `tasks` | ✅ | 出集里的 `task_id`（例：`s1-cor-01`） |
| `arms` | ✅ | **至少两条，且第一条必须是干预臂**（`strict` / `doc` / `hint` …），参照臂 `open` 写在后面 |
| `seeds` | ✅ | 整数 ≥ 1（`run_id` 里是 `r01` 这样两位） |
| `image` | — | 镜像名**不带 tag**（例：`gb-cx-u`） |
| `digest` | — | 该镜像的 `sha256:…`。哪儿取：`harnesses/<id>/Dockerfile` 顶部的来历注释，或 f02 上 `sh harnesses/build.sh <id>` 最后打印的那一行 |
| `timeout_s` | — | 单 run 墙钟上限，默认 1500 |
| `max_calls` / `max_tokens` | — | 见下面 §5.3 —— **两个都不要写**（默认档已是 100 次 / 6M，写上只会把档位压低） |
| `note` | — | 一句话说明这一批是什么 |

**`arms` 写反了不会报错。** `arms: [open, strict]` 得到的是一张 `ok=True`、无 problems、
两侧逐字节相同的等价表 —— 因为出集把第一条当干预臂，于是等价表在拿 `open` 跟 `open` 比。
最自然的写法正是错的那个。

### 5.3 `max_tokens` 这一行：为什么现在**不要**写

默认预算档是 `max_calls=100 / max_tokens=6,000,000`（`runner/registry.py::RUN_BUDGET`），
与 `BUDGET_TIERS` 的换算规则同源：档位调用数 × 60k/次 → 100 × 60k = **6M**。

**这一段在 2026-09-10 之前是反过来写的**（默认档 600k，文档要求一律显式给 3M）。
理由是实测的：`ops/reports/v1demo/` 那 8 个 run **全部**撞了 token 闸，调用次数只用到
18–22 / 100 —— 表上的 `SR` / `pass@1` 读的是「预算够不够」，**不是能力**。撞闸的现场表现
不是一条显眼的错误，是「agent 做到一半自己放弃了」——**它长得像结论**。
**票据 N-388 已由用户裁定（2026-09-10）：默认档抬到 6M，绕法随之作废。**

所以现在的规矩只有一条：

```yaml
# 矩阵 yaml 里 max_calls / max_tokens 两行都不写 —— 让档位生效
```

```sh
# 单题命令行同理：不要再带 --max-tokens
```

**为什么写上反而更糟**：

* `--max-calls` / `--max-tokens` 是**逐键覆盖**，显式给的赢过档位。现在 3M < 默认档 6M，
  写上就是**把预算压低**；S4 / S7 更是把自己的 150/9M 与 300/18M 一起打回去。
* 现场确认这次跑的是哪一档，**唯一的证据是 run 目录里 `compose.yml` 那一行 `--max-calls`**。
  别拿 registry 的默认值反推。

<!-- S-2026-09-13 -->
**预算档到底给多少、撞了闸算什么**（用户 2026-09-13 点名要写清。数出自
`runner/registry.py`，别照抄转述）：

| 档 | `max_calls` | `max_tokens` | 谁吃这一档 |
| --- | ---: | ---: | --- |
| 默认 `RUN_BUDGET` | **100** | **6,000,000** | S4 / S7 之外的全部阶段 |
| `BUDGET_TIERS["S4"]` | **150** | **9,000,000** | S4 |
| `BUDGET_TIERS["S7"]` | **300** | **18,000,000** | S7 |

也就是：默认 **100 次调用 / 6,000,000 tokens**，**S4 150 次 / 9M**、**S7 300 次 / 18M**。
入口是 `runner/registry.py::budget_for(stage)`，而 `--max-calls` / `--max-tokens`
**逐键赢过档位** —— 所以两行都不写才是让档位生效（本节上半段）。

**撞闸记 `budget_exhausted`，那是一个收口状态，不是失败。**
它与 `ok` / `violation` / `timeout` 并列，同属 `runner/c42/failure_modes.py::RUN_STATUSES`
（那个元组的顺序即判定优先级）。跟着来的三件事：

* **主表里那一格渲染成 `—`**（`scorer/report.py::NO_READING`），而 `—` / `0` / `unobservable`
  是**三个不同的东西**：`0` 是「测了，是零」；`—` 是「这一格的 run 全落在拒绝 / 诚实终止 /
  未结算 / 预算截断四类里，**没有读数**」；`unobservable` 是「有可用的 run，但这个量在它们身上
  **根本测不了**」。混成一个，恒绿的门就看不出来了（另有第四种 `n/a` = 这个量在这一阶段不定义）。
* **撞了闸不一定就记 `budget_exhausted`**：已经把产物写下来之后才撞闸的 run，终态是 `ok`。
  要数「被预算停下的 run」看 `budget_exhausted_runs` 那一列（口径见 §6.5）。
* **撞闸与失败一样是终态，不自动重跑**；要重跑得显式
  `ops/run_joblist.py --retry-status budget_exhausted`。

**别把「一批 run 大半撞闸」读成自己配错了。** 2026-09-13 在一台没有本项目任何遗留物的机器上
做的端到端（3 题双臂 6 个 run，`ops/reports/d2_e2e/`）终态分布是
**3 个 `budget_exhausted` / 1 个 `timeout`（1548 s，撞 1500 秒墙钟闸）/ 1 个 `ok` / 1 个 `violation`**；
其中**四个** run 用满了 100 次调用，只是有一个已经把 artifact 写下来了、于是终态是 `ok`。
这是 **100 次闸下的真实分布**，与 M6 那一批的形状一致，**这六个 run 的分布不调档**
（用户 2026-09-13 裁定）。那张表是**构造验收，不是能力读数**。

### 5.4 六步一条命令

```sh
# ① 生成清单
$PY ops/joblist.py gen --matrix ops/joblists/<name>.yaml
$PY ops/joblist.py stat $GB/runs_in/<batch>/jobs.jsonl      # stat/list/reset 收**位置参数**（不接 jobs 那个开关）

# ② 先干跑：把每个 job 会执行的命令原样打出来 —— 不出集、不推、不跑、不改清单
$PY ops/run_joblist.py --jobs $GB/runs_in/<batch>/jobs.jsonl --dry

# ③ 手工把 exec 树送上执行面（**刻意留在流程外**，见下）。**按形态二选一：**
#    双机：
git status --porcelain          # 先看一眼，工作树里有别人的半成品就等一等
ops/push_exec_to_f02.sh --with-launch-data
#    单机（一条 ssh 都不发，本地落位；执行面根从 GENEBENCH_ROOT 现算）：
GENEBENCH_TOPOLOGY=single $PY -m runner.placement --place-exec --with-launch-data

# ③b 执行面还要一份 **provider**（两种形态都要；此前两份文档一个字都没有）。
#     目录名约定 qlib_provider_<公开 provider 根 sha256 前 8 位>；那 8 位**现算，别手抄**：
P8=$($PY -c "import runner.inject as I; print(I.provider_pin_expect('public')[:8])")   # 公开通道 = f7dda289
cp -a "$GB/snapshots/public_v1/qlib_provider" "<执行面根>/provider/qlib_provider_$P8"   # 单机：本机 cp
# 双机：rsync -a "$GB/snapshots/public_v1/qlib_provider/" $F02:<执行面根>/provider/qlib_provider_$P8/
# 自查（**只探不跑**，退 0 = 网关与 provider 两件执行面前置都齐）：
$PY ops/run_joblist.py --jobs $GB/runs_in/<batch>/jobs.jsonl --channel public --check-plane

# ④ 真跑（可续跑；真跑那一步每个 job 自己去拿网关锁，不必再包一层）
$PY ops/run_joblist.py --jobs $GB/runs_in/<batch>/jobs.jsonl --resume --tables a,b
#    单机形态再加 --topology single（不给就是 dual，会 ssh 到执行面主机）：
$PY ops/run_joblist.py --jobs $GB/runs_in/<batch>/jobs.jsonl --resume --tables a,b --topology single
```

<!-- Y-2026-09-13 -->
**上面四条都没写 `--channel`，那是因为它的默认值是 `private`（发布方内部那条通道）。**
跑**公开**通道的每一条 `run_joblist` 都要显式带 `--channel public`，
并且同时 `export GENEBENCH_CHANNEL=public` —— 两者不一致时它拒绝启动并把正确命令打出来，
**一个都不给则静默按私有题集跑**（私有题集不随发布件交付，外部手上只有公开那份）。
README §2.4 那份最短路径就是照公开通道写的，可以直接照抄。

一个 job 的六段是：出集 → 推送 bundle → 真跑 → 结算 → 入库 → 回写状态。
`--dry` 会把这六段的命令原样打出来（包括推送走不走守门脚本、真跑有没有包网关锁），
一眼能看出矩阵写错没有；**干跑不改清单**（`jobs.jsonl` 的 md5 前后相同）。

**第 ③ 步为什么不在流程里**：`ops/push_exec_to_f02.sh` 会把工作树里**别人未提交的改动**
一起推到执行面。这是一个需要人看一眼的动作，不是自动化的遗漏。

### 5.5 并发、续跑、中断、恢复

* **并发数固定是 1**（`runner/registry.py::RUNNER_CONCURRENCY`）。
  不是保守 —— 这套系统里**没有 >1 的合法值**：网关是单 worker（取证完整性要求），
  所有打网关的真跑都要先拿网关锁，调到 3 只会得到三个在 flock 上排队的线程，
  墙钟一秒不省而日志更难读。`--concurrency` 能覆盖它，覆盖了也只会让「出集 / 结算」并行。
* **续跑**：终态一律跳过（不加 `--resume` 也跳过；加了只是把「清单里已有终态」从提醒变成预期）。
  中断之后原样再敲一次同一条命令就是恢复。
* **失败与撞闸都是终态，不自动重跑。** 撞了 token 闸的 job 记 `budget_exhausted`，
  失败的记 `failed`。要重跑必须显式点名：

```sh
$PY ops/run_joblist.py --jobs $GB/runs_in/<batch>/jobs.jsonl --retry-failed
$PY ops/run_joblist.py --jobs $GB/runs_in/<batch>/jobs.jsonl --retry-status budget_exhausted
$PY ops/joblist.py reset --status failed $GB/runs_in/<batch>/jobs.jsonl     # 显式重置成 pending
```

* **只跑一部分 / 跳过某几段**：

```sh
# 这里都带着 --dry 写（先看命令、不动真格）；去掉 --dry 才是真跑
$PY ops/run_joblist.py --jobs $GB/runs_in/<batch>/jobs.jsonl --dry --only-task s1-cor-01 --limit 2 --concurrency 1
$PY ops/run_joblist.py --jobs $GB/runs_in/<batch>/jobs.jsonl --dry --no-export --no-score
```

`--no-export` = bundle 已经在执行面上了，别再出一次；`--no-score` = 只跑，不结算不入库不回写终态。

* **看进度**：`$PY ops/joblist.py stat <jobs.jsonl>` 出状态计数，
  `$PY ops/joblist.py list <jobs.jsonl>` 逐行列出（带档位与 `run_id`）。
### 5.6 单题方式

不用清单时的单题命令（`ops/run_f02_a1.py` 包在网关锁里，从数据面这一侧起）：

```sh
$PY ops/gateway_lock.py --what "<谁>:真跑 <task>" -- ssh -o ConnectTimeout=120 $F02 \
  "umask 022; export PYTHONDONTWRITEBYTECODE=1; cd /data/genebench_runner && \
   python3 exec/ops/run_f02_a1.py --bundle /data/genebench_runner/<batch>/runner/tasks/<task> \
     --manifest /data/genebench_runner/<batch>/runner/tasks/<task>.manifest.json \
     --config-id <config_id> --arms strict,open --seq 1 --timeout 1500 \
     --run-root /data/genebench_runner/<batch>/runs --results-dir /data/genebench_runner/<batch>/results"
```

`umask 022` 与 `PYTHONDONTWRITEBYTECODE=1` **不是可选的**：
执行面的权限守门会拦 0775 的 `__pycache__`。
重跑同一个目标要换 `--seq`，否则会被拒（同一个 `run_id` 不许覆盖）。


<!-- Y1-2026-09-11 -->
> **单题方式在形态 ① / 公开通道下要多带两个环境变量，上面那条命令里没有**（卡 Y1 演练实测）：
>
> ```
> export GENEBENCH_CHANNEL=public                     # 少了它：P2 拿**私有** provider 的冻结值去核公开树，当场红
> export GENEBENCH_GATEWAY_ADDR=<本机 LAN IPv4>:<你起的那个端口>   # 形态 ①：容器要打**本机**网关（§1.3；公开通道默认 18081、私有 18080）
> #   只收 `IPv4:端口`，**主机名当场抛 `ValueError`**（见 §1.3）；
> #   `0.0.0.0` / `127.0.0.1` / `localhost` / `::1` 在拒绝名单里（它们在边车容器里指向边车自己）。
> #   发布方那台当时用的是 `192.168.1.219:18080` —— 那是**它的** LAN 地址与私有端口，不要照抄。
> export PYTHONPATH=<你的 site 目录>                   # 注入器要 import h11（§1.2）
> ```
>
> **还有一条会静默走错的**：`ops/run_f02_a1.py` 的 `--provider-root` **只有 `--dry` 用它**；
> 真跑那条路径读的是模块常量 `PROVIDER`（写死私有 provider 的绝对路径），
> `--run-root` / `--results-dir` 都会按参数改写、**唯独它不会**。
> 后果是**公开通道的真跑喂给容器的是私有 provider 树**，而 P2 照样绿 ——
> 因为跑批不设 `GENEBENCH_CHANNEL` 时期望值也是私有的，两头一致。
> 证据：`m6_public` 的 run 目录里 `work/provider/features/` 下有 `bj*`（北交所）代码，
> 而公开 provider 只有沪深。**这不是文档能修的**，已登记（`ops/tickets.md` 的 **N-611**）；
> 在修好之前，公开通道真跑要么改自己那棵树的这行常量，要么接受这件事并在报告里写明。

出集与推送这两步的独立命令（清单方式已经替你跑了）：

```sh
STG=$GB/staging/<batch>_<task>; rm -rf "$STG"
$PY ops/export_bundle.py <task> --staging "$STG" --digest sha256:<64hex> --image <镜像名不带 tag>
ops/push_bundle_to_f02.sh "$STG/tasks/<task>" /data/genebench_runner/<batch>/runner/tasks "$STG/<task>.manifest.json"
```

出非默认臂要点名，**第一个必须是干预臂**：`--arms doc,open`。臂的定义在 `genetask/arms.yaml`，
加一个臂只改那个 yaml（不要碰任何 `.py`），怎么加见 `ops/HANDOFF.md` §15.2。

### 5.7 公开通道跑批

公开通道的批任务外面再包一层 `ops/public_gateway.sh run --`，它自带网关锁并在跑完停掉网关。
**内层因此必须加 `--no-batch-lock`** —— 同一把 `fcntl.flock` 在另一个进程里再拿一次会永久阻塞，
表现是「网关起来了、一题都没跑、也不报错」：

```sh
ops/public_gateway.sh run -- env GENEBENCH_CHANNEL=public PYTHONDONTWRITEBYTECODE=1 \
  $PY ops/run_oracles.py --tier full --agent oracle --no-batch-lock \
      --answer-root $GB/reference --set-name public/v1.0-smoke-public \
      --out ops/reports/public/probe_run_oracle.json
```

**裸跑时千万别加 `--no-batch-lock`** —— 不拿锁并发 = 网关 OOM。

三控（oracle / null / filler 三条对照）也指向公开通道，它不打网关：

```sh
GENEBENCH_CHANNEL=public $PY ops/run_controls.py \
  --answer-root $GB/reference/tasks/public/v1.0-smoke-public \
  --gateway-log $GB/logs/gateway_access_public.jsonl --out <你自己的落点>
```

少了 `GENEBENCH_CHANNEL=public` 会**拒绝启动**（只换题集不换通道 = 题集是公开的、读的表是私有的）。
`--out` 别指到 `ops/reports/public/`，那是共享目录。

---

## 6. 结算与读表

### 6.1 结算：`ops/score_runs.py`

数据面**主动去执行面拉** run 目录（执行面没有任何回连）：

```sh
$PY ops/score_runs.py --batch <batch> --remote /data/genebench_runner/<batch>/runs/runs

# 已经拉过、只想重算一遍（重算一遍看结果一不一样，是最便宜的可复现性判据）
$PY ops/score_runs.py --batch <batch> --no-pull --no-gateway-log --ref-tasks $GB/reference/tasks/v1.0-smoke
```

**`--remote` 比 `--run-root` 多一层 `runs/`。** 这是这套系统里被撞过最多次的一个坑
（三张卡各撞一次），因为**它不报错**：少写那一层会退 0 并打印「runs: 0；问题: 0」。
两层的由来是 `run_f02_a1.py --run-root <X>` 会在 `<X>/` 下再建一个 `runs/` 放各 run 目录。

<!-- Y-2026-09-13 -->
**上面第二条写的 `--ref-tasks $GB/reference/tasks/v1.0-smoke` 是私有题集根。**
公开通道要换成 `$GB/reference/tasks/public/v1.0-smoke-public`（第三件附件解开后落在那里），
同机结算还要 `--remote-host local`，run 根用 `--runs-root` 显式给。
拉取的默认远端是 `ops/score_runs.py::F02`，它**读 `GENEBENCH_F02`**（§1.3 那张表）——
不设它就会去连**发布方的执行面**，而那句 `Host key verification failed` 里看不出这一点。

其它开关：`--no-pull`（不拉，直接结算本地已有的）、`--ref-tasks`（换参考题集根）、
`--gateway-log`（喂网关 access_log —— 四个依赖日志的探针族靠它从 `unobservable` 变成真判）、
`--no-gateway-log`（显式声明日志不可得，那四族标 `unobservable`）。

**重跑一遍结算，看结果一不一样，是检验报告可复现性的最便宜判据**，每张出报告的卡都值得做一次。

### 6.2 入库：`ops/results_db.py`

结果库是三张表的**单一来源**（追加式 `results.jsonl` + `index.json`，主键 `(batch, run_id)`）。

```sh
$PY ops/results_db.py ingest --batch <batch>          # 收一个批
$PY ops/results_db.py backfill                        # 把 ops/reports/*/records.json 全收进来
$PY ops/results_db.py stat                            # 库的元信息（批 / 条数 / 版本轴组合）
$PY ops/results_db.py versions                        # 库里出现过的版本轴组合（混轴在这里看得见）
$PY ops/results_db.py query --filter batch=<batch> --fields run_id,run_status,arm
```

**四条版本轴缺一即拒入库**。它们是 `ops/results_db.py::AXES`：
`set_version` / `reference_version` / `protocol_version` / `channel`。

### 6.3 出表：`ops/mk_tables.py`

<!-- C2-2026-09-13 -->
**先分清哪张是发布表。** `--table` 有四个值，只有 `main` 是发布表：

| `--table` | 是什么 | 列 |
|---|---|---|
| `main` | **发布表**（主表 `table_main`）——「这个系统在这套题上是什么水平」引它 | **19 个指标列 + 5 个身份列 = CSV 24 列**，列名与顺序写死（`ops/test_report_columns.py` 逐字钉住）；**没有总分** |
| `a` | **诊断表**（Table A，⑥-b 裁定）—— 带 `effect` 这一列，**不是发布件** | 全量指标，随诊断量增减 |
| `b` | 诊断表（Table B） | 同上 |
| `adaptation` | 适配赛道表 | §6.7 |

19 列 = `SR` `P@1` `$` + 每阶段两列：`Cov`/`Prov`、`Cell%`/`Adj`、`Fid`/`Decl`、`IC-agr`/`Set`、
`Sig`/`ρ̄`、`W-agr`/`Cons`、`ε-agr`/`Ledger`、`Audit`/`Ovr`。
5 个身份列 = `config_id` `arm` `arm_kind` `n_tasks` `n_runs`（`scorer/report.py::TABLE_A_INDEX_COLUMNS`）。
逐列口径在 `ops/reports/report_spec_v1.md`；**别拿 Table A 当发布读数往外贴**。
`ops/run_joblist.py --tables` 的帮助文本还只写着 `a,b,adaptation`，但它是原样透传给
`mk_tables.py --table` 的，写 `main,a,b` 一样认。

```sh
$PY ops/mk_tables.py --table main --format csv --filter batch=<batch> --out ops/reports/<batch>   # 发布表
$PY ops/mk_tables.py --table a --format md    --filter batch=<batch> --out ops/reports/<batch>
$PY ops/mk_tables.py --table b --format csv   --filter batch=<batch> --out ops/reports/<batch>
$PY ops/mk_tables.py --table adaptation --format latex --filter batch=<batch> --out ops/reports/<batch>

# 混轴显式放行 + 定制表名/表头/标签 + 改 pass^k 的 k
$PY ops/mk_tables.py --table a --format latex --filter batch=<batch> --out ops/reports/<batch> \
    --allow-mixed-axes --k 3 --name table_a_mixed --caption "混轴，不可比" --label tab:a-mixed
```

`--filter` 可重复，值用逗号分隔即「或」。`--k` 改 pass^k 的 k（默认 3）。
`--name` / `--caption` / `--label` 定制输出文件名与表头。

**混轴默认拒绝出表。** 所选记录的四条版本轴不全同时，`mk_tables` 退出并列出分歧，例如：

```
拒绝出表：所选的 29 条记录跨了版本轴，默认不出表 —— 分歧：protocol_version: … ；
reference_version: r1.0.20 | r1.0.8；set_version: 1.0.13 | 1.0.7。
这不是一个可比的读数（同一行会把两个版本的 run 合成一个 pass@1）。
```

要合就显式 `--allow-mixed-axes`，md / latex 的表脚注会逐条写明混了哪些值，
CSV 旁边落一份 `<表名>.axes.json`。**放行出来的那一行不是一个可比的读数，别与单版本的表并排比。**

一个**不算混轴**的例外：协议轴上「裸臂 = `geneprotocol_v1@none` + 协议臂 = 某个摘要」是正常的，
判据按 `arm_kind` 分组，脚注会把这件事说清楚。

### 6.4 两组「四条版本轴」不是同一组

这是最容易读错的一处：

| 哪一组 | 内容 | 谁写的 / 干什么用 |
|---|---|---|
| `scorer/report.py::VERSION_AXES` | `set_version` / `reference_version` / `runner_version` / `image_digest` | **注入面**写进每条记录的，出现在表的**列**里 |
| `ops/results_db.py::AXES` | `set_version` / `reference_version` / `protocol_version` / `channel` | **库**用来判可比性的，出现在表的**脚注**里，混轴保护按它判 |

表上写不下 64 位十六进制，所以 `runner_version` 与 `image_digest` 在表里缩成前 12 位 + `…`；
**完整值留在 `records.json` 里** —— 表是给人读的，记录才是证据。

### 6.5 Table A 每一列的口径

**这一节是本手册最容易被读错的地方。最要紧的一条规则：空 ≠ 0。**
空 = 「这个量在这批 run 上没有可用样本」；0 = 「量到了，值就是零」。两者在表上必须分得开。

| 列 | 定义 | 数据源 | 不可得时 |
|---|---|---|---|
| `config_id` / `arm` | 分组键（Table A 按 `(config_id, arm)` 分组） | 记录 | — |
| `arm_kind` | `baseline` / `protocol` / `instruction_variant` | `genetask/arms.yaml` | — |
| `n_tasks` / `n_runs` | 这一格里有几道题 / 几个 run | 记录 | — |
| `SR` | 逐题「`sr_bucket == scorable` 的比例」再对题取均值 | 记录的 `run_status` / `sr_bucket` | 分母为 0 的题**整题不进任何均值**（不是记 0） |
| `pass@1` | 逐题在**判得出来**的 run 上的成功率，再对题取均值 | 记录 | 一条都判不了的题不进 `pass@1`（**不是记 0**） |
| `pass^3` | 无偏 pass^k 估计（`--k` 改 k） | 同上 | 样本不够的题不进；`pass^3_tasks_with_3_runs` 给的就是进了几道题 |
| `ProgressRate` | 结构合规率（过了结构但答案不对也算） | 记录 | 同 `SR` 的分母纪律 |
| `effect` | 逐 run 效应量的**均值** | 记录 | `None` 不进均值 —— 所以必须连着 `effect_settled_runs` 读 |
| `effect_settled_runs` | `effect` 那个均值是几个 run 上算出来的 | 记录 | 0 |
| `Steps` / `Latency` | 平均步数 / 平均墙钟秒 | run 目录 | 空 |
| `$` | 逐 run 成本（`runner/pricing.py` 算好放进记录）的均值 | `llm_log` 的 usage | **全 None 时是空，不是 0** —— 「上游 404 一个 token 都没买到」写 0 会被读成「这家几乎不花钱」，与真相正相反 |
| `Recov` | 在**收到过 validator 拒绝**的 run 里，最终 `valid` 的比例 | 记录 | 裸臂没有这条回路 → 不进分母 → 空 |
| `越权率` | 被网关拒的请求数 / 总请求数 | 网关 `access_log` | 一个可观测 run 都没有 → 空；`overreach_observable_runs` 给分母 |
| `tokens_prompt` / `tokens_completion` | **总和**（不是均值） | `llm_log` | 一条样本都没有 → 空 |
| `unbounded_requests` | 没界定右端的取数请求**总数**（行为计数，不是比率） | 网关日志 | **三态**：有样本就报总数（**0 就是 0**）；一条样本都没有才是空。空 = 日志不可得，0 = 一次都没发过 |
| `budget_exhausted_runs` | 边车**真的发过 429** 的 run 数 | 记录里的 `budget` 字段 | **不是** `run_status == "budget_exhausted"` 的数 —— 撞了闸但已经把 artifact 写下来的 run，状态是 `ok`，它同样是被预算停下的 |
| `unsettled_runs` | 判不出成功/失败的 run 数 | 记录 | 0 |
| 四条版本轴 | 见 §6.4；混了就写 `MIXED:a|b` | 记录 | 不静默合并 |

### 6.6 Table B 每一列的口径

按 `(config_id, arm, stage)` 分组，只在 **`validity == valid`** 的 run 上对各阶段
correctness 指标取均值；另报三个量：

| 列 | 定义 | 不可得时 |
|---|---|---|
| `n_runs` / `n_runs_denom` | 这一格全部 run 数 / **分母** run 数 | 分母只排除 `unscorable_harness`，**只排除它** |
| `invalid_rate` | `validity == invalid` 的比例，分母是 `n_runs_denom` | 分母为 0 → 空 |
| `honest_halts` | `correct_handling is True` 的 run 数（诚实终止） | 0 |
| `unobservable_probes_mean` | 每个 run 平均有几族探针是 `unobservable` | — |
| 各 correctness 指标 | 阶段各自的指标，逐键取均值 | 该指标一个 valid run 都没有 → 该列不出现 |

`n_runs_denom` 这一列不是冗余：拿 `n_runs` 当分母的话，harness 自己坏掉的 run
（`validity` 是 `None`）进不了分子却占着分母 —— 于是「harness 越不稳，invalid 率看起来越低」。

### 6.7 适配赛道表每一列的口径

按 `(config_id, arm, level)` 分组（`level` ∈ L1/L2/L3，另出一行 `ALL`），五类结局计数 + 比例并列
（只给比例的话，10 例里 1 例与 100 例里 10 例在表上同形）：

| 列 | 定义 |
|---|---|
| `n` | 这一格几例 |
| `first_pass` / `repaired_pass` / `correct_flag` / `blocked` / `failed` | 五类结局的**计数**（`correct_flag` 是 L3 专属） |
| `*_rate` | 上面五个各自 / `n` |
| `resolved_rate` | (首次通过 + 修复后通过 + 正确标记) / n —— 「这份上游产物最后接进来了吗」。**拦截既不算失败也不算成功**：正确地拒绝一份修不了的产物是协议要的行为，计进分子会奖励硬修 |
| `as_expected_rate` | 结局 == 该例 `expected_outcome` 的比例（L1/L2 期望首次通过，L3 期望正确标记） |
| `validator_rejections_mean` | 只在**有** validator.log 的 run 上取均值（裸臂没有这条回路 → 不进分母） |

**适配赛道今天一个真运行都没有**（`ops/reports/adapt/summary.md`：`有真运行：0`）。
表只有表头，**不要引** SR / 结局分布。挡着的是一条需要用户裁定的题源问题（票据 N-348）——
在裁定之前一个适配 bundle 都不许推到执行面。

> ⚠ **这条禁令今天只是一句话，没有任何守门在执行它。**
> 卡 6.4 的外部演练照 §5.6 的写法 `--arms adapt,open` 出集、再走 §4② 那个
> **唯一允许的推送入口** `ops/push_bundle_to_f02.sh`，**两步全绿**，
> `INSTRUCTION.adapt.md` 就落到执行面上了（当场删除，没有起过 run）。
> `push_guard` 核的是通行证与答案面，**不看臂**。
> 所以：**今天靠的是你读到了这一句**。要把它变成守门是代码层的事，已登记票据。
> 另外，「适配赛道怎么跑」在本手册与 README 里**没有步骤**，只有本节这张列口径的表 ——
> 想跑的人今天要读 `ops/specs/adaptation_track.md`（内部规格），见 §8.4。

### 6.8 归档一版

要把交签的那一版固化成只读目录：

```sh
$PY ops/archive_signoff.py --label "签字版"      # ★未实跑：归档是不可变的，不该为了验命令造一份
```

落 `ops/reports/signed/v<集版本>_r<参考版本>/` + `MANIFEST.json`。
**归档是不可变的**：目标已存在时默认拒绝，`--force` 才覆盖。现有一份 `v1.0.10_r1.0.17`。

### 6.9 把结果带走：`genebench export` / `genebench merge`（裁定 ⑮）

结果库是**一台机器一份**（`$GB/results/v1/results.jsonl`）。在自己的机器上跑完 GeneBench、
想把读数拼回来 —— 走这两条命令，**不要拷 `results.jsonl`**：两份文件行与行之间没有主键约束，
拼完之后没有人知道两边跑的是不是同一套题。

```sh
# 导出：结果库切片 + run 清单 + 四条版本轴 + 机器标识 → 一个自包含的 .tar.gz（旁边有 .sha256）
$PY ops/genebench_cli.py export --out ~/out --filter batch=m6_public --label "第一批公开通道"

# 收别人的包：**先校验四轴一致**，不一致当场拒；一致才合并进本地结果库
$PY ops/genebench_cli.py merge ~/in/genebench-results-<机器>-<时间>.tar.gz --dry   # 只校验与试算
$PY ops/genebench_cli.py merge ~/in/genebench-results-<机器>-<时间>.tar.gz

# 先自己核一遍包（`-c` 读的是相对路径，**要先 cd 到包所在目录**）
# macOS 的 /usr/bin 里没有 sha256sum，一定在的是 perl 的 shasum；这个小函数两边通用
# （别写成 SUMC="sha256sum -c" 再 $SUMC … —— zsh 不对未加引号的变量做词分割，见 README §1.5）
sumc() { if command -v sha256sum >/dev/null 2>&1; then sha256sum -c "$@"; else shasum -a 256 -c "$@"; fi; }
( cd ~/in && sumc genebench-results-<机器>-<时间>.tar.gz.sha256 )
```

`--db <库根>` / `--release-manifest <清单>` 两个开关**写在子命令前后都行**
（`merge <包> --db ~/db` 与 `--db ~/db merge <包>` 等价）。

**包里有什么**（解开就三件，MANIFEST 里逐件带 sha256）：

| 件 | 是什么 |
|---|---|
| `MANIFEST.json` | 四条轴、机器标识、逐 run 轴的取值集合、批次/赛道计数、选择条件、两件的 sha256 |
| `results.jsonl` | 结果库切片，**每条记录自带四条轴**（`set_version` / `reference_version` / `protocol_version` / `channel`） |
| `runs.json` | run 清单：一条 run 一行（机器、批、run_id、题、配置、臂、种子、状态、四条轴），给人看的索引 |

**机器标识怎么取**（`runner/inject.py::machine_fingerprint`，手册与代码同源）：

```
fingerprint = sha256(b"genebench-machine-v1\0" + 稳定源).hexdigest()[:8]
machine_id  = f"{主机名 slug（≤16 字符）}-{fingerprint}"
```

稳定源按顺序取第一个拿得到的：① 环境变量 `GENEBENCH_MACHINE_ID`（给了就**整个 machine_id
由它决定**）；② `/etc/machine-id` 或 `/var/lib/dbus/machine-id`（装机时生成，重启 / 改 IP /
换网卡都不变，**哈希之后才用**）；③ macOS 的 `IOPlatformUUID`；④ 都没有 → 退回主机名，
指纹来源如实记成 `hostname-only`（**两台同名机器会撞**，这种部署请显式设
`GENEBENCH_MACHINE_ID`）。IP、MAC、容器 id、时间一概不进算法 —— 它们会变。

**`run_id` 末尾从此带机器标识**：`<题>.<臂>.<配置>.r<NN>@<machine_id>`。清单里的 `job_id`
就是它算的（同源），跑批时 f01 会把自己的 `GENEBENCH_MACHINE_ID` export 给 f02，
所以两边仍然逐字相同。**既有 run_id 不追溯** —— 2026-09-10 之前那批记录没有机器段，
表上按「机器未知」如实写，不给它们盖今天的标识。

**merge 校验什么、退什么码**：

| 退出码 | 什么事 |
|---|---|
| 0 | 合了（幂等：同主键同内容 → 记重复，不重写） |
| 3 | **四条轴不一致** —— 一条都没写进去，逐条列出「包说什么 / 本机是什么 / 怎么办」 |
| 4 | 同主键内容不同 —— 报错不覆盖（结果库的老纪律，`ops/results_db.py`） |
| 5 | 包坏了（`.sha256` 或 MANIFEST 里的逐件 sha256 对不上、缺件、成员形状不对） |
| 2 | 用法（比如切片是空的 —— 空包多半是 `--filter` 写错了） |

主键是 `(machine_id, batch, run_id)`。两台机器按同一份清单跑同一道题，`run_id` 因为带机器段
而天然不撞 —— 这正是这条标识存在的理由。

**跨版本的读数**（比如把 1.0.7 那批老结果带到 1.0.15 的装置上）：常规包装不下，
`export` 会当场拒并让你显式 `--archive`；归档包里两个 root 写 `null`（本装置的 root 描述的
不是那些记录），**合并端也必须显式 `--archive`**。归档 ≠ 可比：出表那一步照旧按混轴拒绝（§7.11）。

> 本节命令**原样跑过**（f01，2026-09-11）：`export --archive`（m6 切片 21 条）、
> `merge --dry`（拒 / 试算两种）、`merge --archive`（幂等 0 新增）、`axes`。

### 6.10 版本锁：四条轴与 `RELEASE_MANIFEST.json` 不一致就拒绝运行（裁定 ⑰）

```sh
$PY ops/genebench_cli.py axes          # 自检：退 0 = 一致；退 3 = 不一致，逐条说清哪条对不上
```

比的是 `RELEASE_MANIFEST.json` 里声明的四个字段与**本装置现算的值**：
`set_version` / `set_root` / `reference_version` / `reference_root`
（只比版本号不够 —— 「号没动、内容动了」正是重冻要解决的那件事），
外加一条：`ops/freeze_v10.py` 的代码常量与盘上的冻结清单必须同值（改了常量没重冻 =
这个装置「现在是哪一版」没有答案）。

**这道门在入口处跑**：`ops/genebench_cli.py` 的每个子命令、`ops/run_joblist.py`（**`--dry`
也拦** —— 干跑的用处是把真跑会做的事原样打出来，而真跑会被拦下）。不一致就退 **3** 并印出
「清单说什么 / 本装置现算什么 / 为什么拦 / 怎么修」。

怎么修，两个方向，报错里都写着：

* **清单陈了**（常见：刚重过冻）→ `$PY ops/mk_release_manifest.py` 重新生成；
* **装置陈了** → 重冻两条轴（分两次，N-111）：`$PY ops/freeze_v10.py --write` 与
  `$PY ops/freeze_v10.py --write-reference`。

发布包解开之后清单不在仓库里 → 用 `GENEBENCH_RELEASE_MANIFEST=<包内的 RELEASE_MANIFEST.json>`
指过去。**那是换路径，不是开关**：指到一个不存在的文件照样拒（「没有清单」不是「那就不校验了」，
是「没有可比的一方」）。


---

## 7. 常见错误：症状 → 原因 → 看哪里

### 7.1 通行证作废：`PushBlocked: bundle 的冻结引用已过期`

**症状**：推送被拒，说「通行证 `<旧 root>` ≠ 当前 `<新 root>`」，或者「内容与通行证不符」。
**原因**：题面重冻过了。冻结根里任何一个文件变化都会让 `root` 变，
而 `root` 在通行证的 `ROOT_FIELDS` 里 —— **重冻作废所有已发通行证**。
**怎么办**：**重新出集**，不要去改通行证。

```sh
rm -rf "$STG" && $PY ops/export_bundle.py <task> --staging "$STG" --digest sha256:<64hex> --image <镜像>
```

**看哪里**：`ops/push_guard.py::check_manifest`。核当前两轴：

```sh
$PY ops/freeze_v10.py --check-all         # 三条轴一起核（旧写法 frozen_ref/reference_ref 漏了公开轴）
```

### 7.2 `budget_exhausted` / 「agent 做到一半自己放弃了」

**症状**：`run_status=budget_exhausted`；或者更坏 —— 状态是 `ok`，但 `llm_log` 尾部一片
`budget_exceeded`，分数照出。
**原因**：撞了 token 闸。**这条在 2026-09-10 之前几乎必然发生**：默认档只有 600k，
而 Codex 每次 prompt 实测 43k–68k，大约第 20 次调用就撞（`max_calls` 才用掉 18–22 / 100）。
N-388 裁定之后默认档是 6M，同样的一批不该再撞。
**怎么办**：矩阵里**什么都别写**，让档位生效（§5.3）—— 写 `max_tokens: 3000000` 现在是把 6M 压成 3M。
还撞的话看的是这一次真的要那么多 token，而不是护栏定低了。
**看哪里**：run 目录的 `compose.yml` 那一行 `--max-calls` / `--max-tokens` 是现场唯一证据；
`log/llm_log.jsonl` 里 `decision` 不是 `allow` 的那些行给的是被拒的理由。
表上读 `budget_exhausted_runs` 这一列（口径见 §6.5）。

### 7.3 `no_artifact`

**症状**：`run_status=no_artifact`，`sr_bucket=unscorable_agent`。
**原因**：`/task/artifact.json` 不在位置上 —— 被测方写到别处了、写在容器里但没落到挂载卷、
或者根本没写完。**这是「被测方自己停了」，不是 harness 坏了**（后者是 `unscorable_harness`）。
**看哪里**：`<run_dir>/run.json` 的 `stdout_tail` / `stderr_tail`（各 2000 字符）——
真跑收尾会 `down -v`，**容器日志早就没了**，`docker compose logs` 拿不到东西。
产物该放哪、三态怎么声明：`integrations/P2_CONTRACT.md` §3.1。

### 7.4 `malformed`

**症状**：`run_status=malformed`，`sr_bucket=malformed`（它自己一个桶，既不是成功也不是 agent 放弃）。
**原因**：产物在位置上但结构不合规 —— 信封 12 个必填键缺一个、三态声明写成了默认值、
或者依赖图（`payload_depends_on`）对不上。
**怎么办**：用产物助手生成，别手拼：`integrations/genebench_client/src/genebench_client/emit.py`
的 `emit_s1…emit_s8` 会替你把三态、依赖图、写法归一做对，并且是**清点而非编造**
（S5 的 coverage 按 signals 数出来，自报对不上当场炸）。
**一个不会红的坑**：题面夹具与网关**不同源**（`20260105`+`SH600000` vs `2026-01-05`+`600000.SH`），
join 得空表且不报错，产出**一张全 null 但结构合规、覆盖自洽、过 validator 的面板**。

### 7.5 `identity_mismatch`

**症状**：结算出 `SR=0.0`，而 summary 说「问题: 0」。
**原因**：产物信封里的 `(task_id, config_id, arm)` 与容器环境变量 `GENEBENCH_*` 的真值对不上。
**这不是答错**，是身份没对齐 —— 被测方把这三个值写死了，而不是从环境变量读。
**看哪里**：`<run_dir>/work/artifact.json` 的信封 vs `<run_dir>/compose.yml` 的 `environment`。

### 7.6 网关起不来（`$GB` 下一个 0644 文件就够）

**症状**：网关连不上；`systemctl --user status genebench-gateway.service` 里 restart counter 一直涨。
**原因**：`genebench-gateway.service` 的 `ExecStartPre` 就是权限守门 `ops/guard_modes.py`。
`$GB` 全树**任何人**留下的一个 0644/0664/0775 都会让它拒绝启动 ——
而那长得跟网关自身故障一模一样，**肇事者自己什么都看不到**。
实际发生过：网关停了约 35 分钟；另一次是 `.git/index` 被留成 0664。
**诊断一条命令**（它会逐条列出是哪个文件）：

```sh
$PY ops/guard_modes.py            # 只查
$PY ops/guard_modes.py --harden   # 统一收紧后再查
```

<!-- U-2026-09-13 -->
**`--harden` 修不好的有三类**（N-818）：答案面根（`reference/` `runs_in/` `gold/`）下的符号链接
（它不替人删东西）、读不到模式的**断链**、以及 access_log 的轮转配置。守门打出来的
「修：」那一行**按类别分了岔**，`--harden` 收不掉的会明说并给出真能照着做的下一步 ——
看到那句就别再反复跑 `--harden`。
**建 venv 不会再撞这道门**：`python3 -m venv $GB/env` 留下的 `bin/python` / `bin/python3` /
`bin/python3.12` 是**符号链接**，最终指向系统解释器（`0755`、root 所有）；守门不再按**目标**
的权限位判符号链接（符号链接自身的模式在 POSIX 上恒为 `lrwxrwxrwx`、没有意义）。
`$GB` 下**真实**的 `0644` 文件 / `0775` 目录判据一个字没改，照样拒绝启动、照样 `--harden` 收得掉。

**预防**：在 `$GB` 下做任何事都 `umask 077` 开头，scp 之后立刻 `chmod -R go-rwx <目录>`，
跑 git 也要带 `umask 077`。仓库整棵收紧：

```sh
$PY -c "from ops import report_io as R; R.secure_tree('/data/shared/genebench/repo')"
```

### 7.7 网关锁排队 / 拿着锁却一题都不跑

**症状 A**：命令挂在那儿，每 30 秒打印一次「在等谁」。
**是正常的** —— 网关是单 worker，跑批与真跑不许同时打它（不串行 = 网关 OOM）。
锁文件 `$GB/locks/gateway.lock` 里写着持有者（pid / 主机 / 命令 / 起始时刻）。
不想等就 `--nowait`（直接退 2）：

```sh
$PY ops/gateway_lock.py --nowait --what "看看锁空不空" -- true
```

**症状 B**：网关起来了、一题都没跑、也不报错，**永远挂着**。
**原因**：网关锁是 `fcntl.flock`，**不可重入**。`ops/public_gateway.sh run` 本身就是
`ops/gateway_lock.py` 起的，里面再拿一次同一把锁就永久阻塞。
**怎么办**：外层是 `public_gateway.sh run` 时，内层跑批一律加 `--no-batch-lock`；
**裸跑时千万别加**。

### 7.8 湖写锁

**症状**：触数据湖的测试或命令报 duckdb 锁冲突。
**原因**：**别的进程**（往往是机器主人自己的分析进程）持着湖写锁。
**怎么办**：等它退出；`ops/test_lake_baseline.py` / `ops/test_universe_pit.py` 这一族的红
多半属于这一类，**不是你的改动**。判别法：**单跑那个文件**，能绿就是外部进程。

### 7.9 exec 树没同步：`未知 config_id` / f02 上 runner 直接 import 不了

**症状 A**：执行面报「未知 `config_id`」，而数据面上 `by_id()` 找得到。
**原因**：忘了 `--with-launch-data` —— 不带这个开关，`harnesses/` 与 `integrations/`
（`launch.json` / `config.yaml` 所在）不会推过去，执行面上的注册表里没有你的配置。
**症状 B**：数据面一切正常，执行面上 `run_f02_a1.py` 一起手就炸。
**原因**：同步脚本是**显式白名单**。加了新的 **import 期**读的数据文件而没在脚本里加一行，
执行面就少那个文件。**加新的 import 期数据文件 = 在同步脚本里加一行。**
**怎么办**：

```sh
ops/push_exec_to_f02.sh --dry-run --with-launch-data     # 先看清单里有没有你的文件
ops/push_exec_to_f02.sh --with-launch-data
```

### 7.10 公开 / 私有通道搞混

**症状**：数字看起来全对，只是来自另一份数据。**这是最贵的一种错，因为它不报错。**
**三条判别 / 预防**：

1. `curl .../healthz` 的 `channel` 字段必须是你以为的那条（§1.5）。
2. 跑批要**同时**换题集和通道：`ops/run_controls.py` 少了 `GENEBENCH_CHANNEL=public` 会拒绝启动。
   两条通道的网关日志也不能混（`$GB/logs/gateway_access.jsonl` vs `gateway_access_public.jsonl`）——
   拿私有日志核公开那一跑，越权计数与读取集都会对不上。
3. **公开出集必须在多的那一层 `public/` 底下**：`$GB/reference/tasks/public/v1.0-smoke-public/`。
   照字面建成 `tasks/v1.0-smoke-public/` 会让 `gateway/sim_factory.py::task_dir` 命中两个目录，
   **私有生产网关的 S8 四题一起 500**。复核：

```sh
$PY -c "import sys;sys.path.insert(0,'.');from gateway import sim_factory as SF;print(SF.task_dir('s8-cor-01'))"
# 必须打印 .../tasks/v1.0-smoke/s8-cor-01
```

**还有一条静默的**：同一个进程里先跑私有再跑公开，`init_qlib()` 会因为已经初始化过而直接返回，
公开链**静默地**读私有 provider —— 表现只是「公开 gold 的数和私有一模一样」，没有任何报错。

### 7.11 混轴出表被拒

**症状**：`拒绝出表：所选的 N 条记录跨了版本轴`。
**原因**：筛出来的记录跨了 `set_version` / `reference_version` / `protocol_version` / `channel`。
**这是设计**：同一行会把两个题面版本的 run 合成一个 `pass@1`，而论文里那一行会被当成可比读数读。
**怎么办**：把 `--filter` 收紧到一个版本；确实要合就 `--allow-mixed-axes`，
然后**读脚注**并且不要与单版本的表并排比。先看看库里有哪些组合：

```sh
$PY ops/results_db.py versions
```

### 7.12 结算打印「runs: 0；问题: 0」

见 §6.1：`--remote` 少了一层 `runs/`。**这是不报错的错。**

### 7.13 两臂都在 3 秒内退出 / `mkdir: cannot create directory ''`

**原因**：`launch.json` 的 `command` 里写了裸 `$` —— compose 解析期就把它插值成空。
**怎么办**：`launch.json` 里一律写 `$$`。判据 `ops/test_harness_contract.py` 会拦。

### 7.14 注入期就被拦（run 目录都没建出来）

**症状**：两臂 0.1 秒退出，**没有 run 目录、没有容器日志**。
**原因**：注入器的前置检查（P0–P9）之一没过 —— 臂名拼错、bundle 形状不对、
协议模块还是 `status: draft`、run 根落在数据根之内（被 L-5a 拒）等。
**看哪里**：注入器的 stderr（`run_f02_a1.py` 自己的输出），以及 `--dry` 跑一遍本地复现。

---

## 8. 附录

### 8.1 四条版本轴怎么查

```sh
# 任务集轴 + 参考轴（几秒，只读）
$PY ops/freeze_v10.py --check-all         # **三条轴一起核**：私有任务集 / 公开任务集 / 参考面

# 库里出现过的全部组合（混轴在这里看得见）
$PY ops/results_db.py versions

# 逐 run 的 runner_version / image_digest：完整值在记录里，不在表上
$PY ops/results_db.py query --filter batch=<batch> --fields run_id,set_version,reference_version
```

**记住有两组四条轴，含义不同**（§6.4）。
<!-- Y1-2026-09-11 -->
**上面只给了两条轴。另外两条这么查**（卡 Y1 演练：一个只拿到包的人按原文查不出协议轴）：

```sh
# 协议轴：包里**没有**一个写着 protocol_version 的字段（ops/manifests/v1.0-smoke.json 里是 null）。
# 它是**逐 run** 的读数 —— 注入器把那一版协议工件的摘要写进 run 记录，结算时带进结果库。
$PY ops/results_db.py query --filter batch=<batch> --fields run_id,protocol_version

# 通道轴：进程环境变量，没设就是 private。**跑之前自己确认一次，别等报告头告诉你。**
echo "${GENEBENCH_CHANNEL:-private}"
```

**解包之后还该跑一次发布清单自校**（它比四条轴多查缺件与 blocker）：

```sh
$PY ops/mk_release_manifest.py --check
#   0 = 一致；3 = 只是某份生成件的 sha 漂了（重新生成即可）；
#   1 = **判据变了**（能不能发的答案变了）；2 = 还没有落盘的清单
```



### 8.2 锁有哪几把，各管什么

| 锁 | 谁拿 | 管什么 |
|---|---|---|
| `$GB/locks/gateway.lock` | `ops/gateway_lock.py`、`ops/public_gateway.sh run`、`ops/run_oracles.py` | **网关串行闸**：跑批与 agent 真跑不许同时打网关。唯一一把由代码强制的锁。**不可重入** |
| `$GB/locks/heavy.lock` | 施工方自己（`flock`） | 重活串行：gold 重算 / IC-ε / oracle 矩阵 / 对账全量 / 打包。全机同一时刻只跑一个 |
| `$GB/locks/pytest.lock` | 施工方自己 | 全量 pytest 串行 |
| `$GB/locks/git.lock` | 施工方自己 | git 写操作串行。**不要在它里面等别的锁** —— 会让所有人的 `git commit` 挂住 |

只有第一把是运行者必须知道的；后三把是多人同时在一棵工作树上施工时的纪律。

### 8.3 目录布局

```
$GB = /data/shared/genebench                     ← 数据面根，及其下每一级都是 0700
├── repo/                                        ← 仓库（本手册在 repo/docs/）
│   ├── genebench_config.py                      ← **唯一**允许出现绝对路径的地方
│   ├── gateway/     执行面取数的唯一入口（只读 HTTP，绑显式地址）
│   ├── snapshots/   从数据湖建冻结快照的代码
│   ├── reference/   ★答案面★ 参考解 / 标准答案       ← 不上执行面
│   ├── scorer/      ★答案面★ 打分                    ← 不上执行面
│   ├── genetask/    题面模板 / 参数 / arms.yaml（冻结根）
│   ├── runner/      执行面：注入器、注册表、边车
│   ├── harnesses/   通用 harness（P1），一个 id 一个目录
│   ├── integrations/专用系统接入（P2）+ 契约 + 取数垫片
│   ├── ops/         运维入口：出集 / 推送 / 跑批 / 结算 / 出表 / 报告 / 票据
│   └── docs/        面向运行者的手册（这一份）
├── env/             专用 Python 环境（$PY）
├── snapshots/       冻结快照：v1（私有）/ public_v1（公开）
├── reference/       ★答案面★ 出集产物 tasks/<set>/<task>/
│   └── tasks/public/v1.0-smoke-public/          ← 公开出集，多的那层 public/ 是必须的
├── staging/         出集暂存（bundle + 通行证）
├── runs_in/<batch>/jobs.jsonl                   ← 作业清单
├── results/v1/                                  ← 结果库
├── release/         发布包：public_v1/ 三个附件（_staging_unpublished/ 已按 N-714 整棵删除）
├── logs/            网关 access_log（两条通道各一份）、施工日志
├── locks/           §8.2 的四把锁
└── scratch/         临时脚本与产物

执行面（形态 ② 是另一台机；形态 ① 是同一台）
/data/genebench_runner/
├── exec/            从仓库同步过来的 genetask / ops / runner / vendor（+ harnesses、integrations）
├── <batch>/runner/tasks/<task>/                 ← 推过来的 bundle
├── <batch>/runs/runs/<run_id>/                  ← run 目录（**两层 runs**，结算 --remote 指这里）
└── <batch>/results/
~/.config/genebench/secrets.env                  ← 真 key，0600，只注给边车
```

### 8.4 还去哪儿查

| 想知道 | 看 |
|---|---|
| 网关 13 个端点的逐项契约、`as_of` 越界的六条 reason、artifact schema | `integrations/P2_CONTRACT.md` |
| 怎么把自己的系统接进来（八步） | `integrations/README.md` |
| 怎么加一个通用 harness（四件文件） | `harnesses/README.md` |
| 施工历史、每个阶段的坑与票据编号 | `ops/HANDOFF.md` |
| 已知限制以及每一条的关闭状态 | `ops/reports/known_limits_v1.md` |
| 公平性协议（臂、等价规则、主表怎么分块） | `ops/specs/fairness_protocol.md` |
| 适配赛道的现状与题源两个方向 | `ops/specs/adaptation_track.md`、`ops/reports/adapt/README.md` |
| 结果库收了哪些批、与既有 CSV 逐格核对 | `ops/reports/results_db_backfill.md` |
| 真 API 用量（机器统计，不是手抄） | `$PY ops/api_usage.py` |
| 待办与需要裁定的事项 | `ops/tickets.md` |

### 8.5 本手册每条命令验到了哪一步

| 层 | 哪些 | 验到哪 |
|---|---|---|
| **原样跑过** | 出集 `export_bundle`、推送 `push_bundle_to_f02.sh`、`push_exec_to_f02.sh --dry-run`、`joblist gen/stat/list`、`run_joblist --dry`（含 `--only-task/--limit/--concurrency/--no-export/--no-score`）、`results_db stat/versions/query`、`mk_tables` 三种格式与混轴被拒、`score_runs`（空批）、`build_public_channel --dry-run`、`run_public_chain --dry-run`、`public_gateway.sh status`、`/healthz`、两轴 verify、`gateway_lock --nowait`、`guard_modes` | rc 与输出都看过 |
| **`--dry` 验到注入完成** | `run_f02_a1.py --dry`（`work/` 装配 + 两臂文件集比对 + 生成 `compose.yml`） | 没有起容器、没有调模型 |
| **★未实跑** | `build_public_channel`（真建）、`run_public_chain`（真跑，4 小时 15 分）、`--force-trading-hours`、`--spill-root`、`pack_public_provider`、`archive_signoff` | 只验了 `--help`：开关名与语义是真的 |
| ~~**未端到端验证**~~ **已端到端**（2026-09-11，卡 Y1） | 形态 ① 的完整链路（§1.3） | 解包 → 起网关 → 建镜像 → 落 secrets → 3 题双臂真跑 → 结算 → 出表，逐步证据 `ops/reports/rehearsal_v2.md` |

### 8.6 本手册自己的判据

```sh
$PY -m pytest ops/test_operator_manual.py -q -p no:cacheprovider
```

它查两件事：手册里提到的每个仓库路径**真的存在**；手册里每条命令用到的每个 `--flag`
在对应脚本的 `--help` 里**真的有**。这两件事都是「外部用户按手册能不能用」的最低限度，
而它们不会让别的任何测试变红。
---

## 9. 排网格：一个批里能并发几个 run（⑨，2026-09-11）

**先改的那件事**：网关单元的 `MemoryMax` 从 **6 G 抬到 12 G**
（`~/.config/systemd/user/genebench-gateway.service`，`--user` 单元，不需要 sudo）。
理由是那条线**卡在了正常工作量上**而不是在挡异常：上一轮一道 **S7** 真题
（strict 臂 **5.66 M tokens / 87 次调用**）就把网关顶到 6 G 上限、触发 **4 次 oom-kill**。

```sh
systemctl --user show genebench-gateway.service -p MemoryMax -p MemoryCurrent -p NRestarts
# MemoryMax=12884901888  ← 12 GiB。不是这个数就是单元没 daemon-reload
```

改完要 `systemctl --user daemon-reload` 再起停；起一次要 **40–70 s**
（`ExecStartPre` 的权限守门扫全树，`TimeoutStartSec=600` 就是给它的）。
起完认两件事：`/healthz` 回 200，且 `bind` 仍是 `192.168.1.48:18080`（**不是** `0.0.0.0`）。

### 换算

网关是**单 worker**（取证完整性要求：`access_log` 用进程内锁，多 worker 会交错写坏行）。
一批里所有并发 run 的数据面请求压在同一个进程上，**内存相加**：

```
并发上限 ≈ floor( (MemoryMax − 常驻 2.3 G) / 单 run 峰值增量 )
```

| 阶段 | 单 run 峰值增量 | 12 G 下的并发上限 | 这个数是怎么来的 |
|---|---|---|---|
| **S7** | ≈ 3.7 G | **1（不并发）** | **实测**推算：一道题把 2.3 G 常驻推过 6 G |
| **S4** | 未实测 | **≤ 2** | **外推**（预算档 9 M tokens，介于 S7 与其余之间）|
| 其余 | 未实测 | **≤ 3** | **外推**（预算档 6 M tokens）|

> 表里只有 S7 那一行有实测背书，另外两行是**外推**。当成起点，不要当成保证 ——
> 真要排更密的网格，先量一道该阶段的真题峰值，再回来改这张表。

**起批之前**：`free -g` 的 `available` ≥ **20 G**（这台机只有 30 G，宿主上还有别人的进程）；
`MemoryCurrent` 还在常驻量级。**批与批之间**的串行由 `ops/gateway_lock.py` 保证（必须包），
本节管的是**一个批内部**的并发度 —— 两件事都要守。

**顶爆的现场表现**：网关被 cgroup 杀 → `Restart=on-failure` 拉起 → 守门 40–70 s
→ 这期间在跑的 run 数据面全部失败。看上去是「批的中段成片失败」，不是一条显眼的报错。
认 `NRestarts` 是不是往上跳（`journalctl --user -u genebench-gateway` 有 oom 记录）。
