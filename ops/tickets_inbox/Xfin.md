# 卡 Xfin —— 交付前终核（只读）

**口径**：完全照 README 逐字走一台干净外部机器的路，`git clone --depth 1`（SSH）+ 三个附件。
本卡**一个字节都没有改仓库**（除本文件）、没有推树、没有碰 Release、没有写 known_limits。
**执行面（f02）一次都没连。**

**环境偏差（已如实记录，判据不受影响）**：f01 是 Ubuntu 24.04，`python3.12` 缺 `ensurepip`
（README §1.5 与手册 §1.2 都写了这件事），所以 README §2.1 第 5 行的 `$PY -m pip install` 在这台上
拿不到 pip。按手册 §1.2 的「不用 root」口径，用系统 pip `--target` 把**README 点名的六个包**
（外加 §1.5 点名的 `pytest jsonschema httpx`）装进 `$GB/env/lib/python3.12/site-packages`，
再往下走。Mac（brew python@3.12 自带 pip）不受这条影响。

证据：`$GB/scratch/Xfin/`（`paste21b.log` = §2.1 整块逐字粘贴；`a21a.log` = §2.1a 逐字落位，
29,240 行 `sha256sum -c` 全 OK、0 条 FAILED；`t14.log` = 14 个测试文件；`stale.txt` = 三类过期口径扫描）。

## 一、发现（按严重度）

| 编号 | 事项 | 状态 | 说明 |
| --- | --- | --- | --- |
| N-829 | `ops/joblist.py` 在 **Python 3.12 上每次调用都当场抛**，README §2.4「最短路径」第 ① 条命令就死 | **block（本卡新发现）** | `ops/joblist.py:389` 与 `:393` 是**逐字相同的 5 行重复块**，把子命令 `rebudget` 注册了两次。Python **3.10**（发布方内部环境）的 `argparse` 不查重，照跑，`--help` 里 `rebudget` 打印两遍而已；**3.11 起 `add_parser` 开始查重**，于是在 README §1.5 强制的 **3.12** 上抛 `argparse.ArgumentError: argument cmd: conflicting subparser: rebudget` —— `--help` / `gen` / `stat` / `list` / `reset` **全部**起不来。这就是「内部 3.10 恒绿、外部 3.12 恒红」，内部任何测试都照不到。实测：克隆树 3.12 抛，发布方 3.10 上同一份文件 rc=0。**连带**把手册 §8.6 叫用户跑的 `ops/test_operator_manual.py` 打红两条（`joblist.py-gen---matrix`、`joblist.py-reset---status`）—— 那两个 flag 源码里都**真有**，红的原因是判据 shell out 到 `--help` 而 `--help` 崩了。**改法 = 删掉 393–395 三行**，本卡已在克隆树的一份探针副本上验过：删完 `--help` 正常，README §2.4 ① 原样跑出 `8 个 job → runs_in/v1demo/jobs.jsonl`、`pending: 8`，正是 §2.4 承诺的 4 题×双臂。全树扫过一遍，**重复 `add_parser` 只此一处**；README/手册点名的其余 13 个 CLI 在 3.12 上 `--help` 全部正常。 |
| N-830 | README §2.4 的代码块**没有 `--channel public`**，外部用户会拿私有题集跑 | **major（本卡新发现）** | §2.4 的 ② 与 ④ 都是裸的 `$PY ops/run_joblist.py --jobs …`。`ops/run_joblist.py` 的 `--channel` **默认 private**，于是干跑打出来的是 `--ref-tasks $GB/reference/tasks/v1.0-smoke`、`GENEBENCH_CHANNEL=private` —— 而 `v1.0-smoke` 是**私有题集**，外部用户手上只有第三件附件带来的 `reference/tasks/public/v1.0-smoke-public`（红线 2 决定了私有题集永远不会给他）。实测：加上 `GENEBENCH_CHANNEL=public` + `--channel public` 之后题集根立刻变成正确的 `…/public/v1.0-smoke-public`，`v1demo.yaml` 那四道题（s1/s2/s3/s5-cor-01）在公开题集里**都在**，所以**只差这一个开关**。**两个开关只给一个时工具会当场拒绝并把正确命令打出来**（写得很好），但**一个都不给就是静默跑私有**，要到真跑那一步才报「找不到 v1.0-smoke/… 的任务目录」。 |
| N-831 | 单机形态下 `ops/run_joblist.py` 与 `ops/score_runs.py` 的执行面地址**写死、无法用环境变量改**，而两处文档的「要改哪些常量」表都没列它们 | **major（本卡新发现）** | `ops/run_joblist.py:70` 与 `ops/score_runs.py:49` 都是 `F02 = "ljn@192.168.1.219"`，**没有 env 兜底**（全仓库只有 `ops/api_usage.py:51` 写了 `os.environ.get("GENEBENCH_F02", …)`）。实测：`GENEBENCH_F02=me@127.0.0.1` 设了之后，§2.4 ④ 的干跑里 ssh 目标**仍然是** `ljn@192.168.1.219`。而 README §2.3 ③ 说「**还有三处**地址常量要改成本机的」并列了三条（`genebench_config.py::GATEWAY_HOST`、`runner/c41/runner_core.py` 的网关常量、`runner/c41/runner_core.py::LAN`），手册 §1.3 那张表也是同三条 —— **两处都没有这两个 `F02`**。手册 §1.3 另有一段说 `GENEBENCH_F02` 可以指目标，但那一段**明确只说 `ops/push_bundle_to_f02.sh` 与 `ops/push_exec_to_f02.sh`**，而那两个 `.sh` 确实读它（`${GENEBENCH_F02:-…}`，已核）—— 所以**手册那句话本身没说假话**，问题是「跑批入口这两处写死」既没被那张表覆盖、也没有任何别的地方提过。单机 Mac 用户只能改源码，而他不知道要改哪两行。 |
| N-832 | README §2.1 把 `selfcheck` 排在 `guard_modes --harden` **前面**，于是首跑第 6 项**必红**，而块里没说要再跑一次 | **minor（本卡新发现）** | §2.1 的顺序是：第 5 行 `pip install` → 第 8 行 `selfcheck_public.py` → 第 9 行 `guard_modes.py --harden`。venv 按 README 自己的硬要求建在 `$GB/env`，pip 装出来的 `.so`/`.py` 是对组/其它开放的，而网关的红线 5 审计走的正是 `$GB` 全树 —— 所以**第 8 行那次 selfcheck 的第 6 项一定是红**（本卡实测：113 条「模式放松」，网关拒绝启动），`selfcheck` 退 1。第 9 行 `--harden` 一跑就收干净（实测「收紧 113 个条目」），**再跑一次 selfcheck 就是绿 5 / 红 1**（剩下那条红是 f01 真没装 docker），网关 1 秒起来、`/healthz` 200、`channel=public`、`freeze_line=2026-07-31`。红条自己的「修：」提示指的就是下一行，所以**自带导航**；但块跑完最后停在一个退 1 的自检上、没人叫他复跑，容易让人以为没过。Mac 上 umask 022，命中条数只会更多。**改法**：§2.1 把第 8、9 两行对调，或在 `--harden` 之后再补一行 `$PY ops/selfcheck_public.py`。 |
| N-833 | `ops/test_readme.py` / `ops/test_operator_manual.py` 在外部 clone 上把「文档说了真话」的路径判红，而手册 §8.6 **正是叫用户跑后者** | **minor（本卡新发现）** | 两个判据把文档里出现的路径一律当**仓库相对路径**去 `exists()`，可 README 里有三类路径根本不该在仓库里：① `$GB/snapshots/public_v1`、`reference/tasks/public/…` —— README §2.1a 自己就写成 `$GB/…`，它们落在 `$GENEBENCH_ROOT` 下（本卡实测：落位后 `$GB` 下**有**、repo 下**没有**）；② `reference/memory_probe_answers/` —— README:37 原话是「**不在这个包里** —— 记忆探针的钥匙一旦公开就立刻失效」，**文档说的是真话，判据照样判红**，而它打出来的话是「README 里提到 X，但仓库里没有它。要么改 README，要么这次移动漏了一处」，会把人支去找一个不存在的遗漏。外部 clone 上 `test_readme.py` **4 红**、`test_operator_manual.py` **5 红**（其中 2 条是 N-829 的连带、1 条 `test_the_gateway_lock_path_in_the_manual_is_the_real_one` 直接 `ValueError` 崩在「发布方锁路径不在 `$HOME/genebench` 之下」）。手册 §8.6 的原话是「它查两件事……这两件事都是『**外部用户按手册能不能用**』的最低限度」，并给了命令 —— 也就是**明确请外部用户跑一个在他机器上必然 5 红的判据**。同类问题 N-828 已登记（12 个 `ops/test_*.py` 写死发布方路径），这两个是**文档主动指过去**的，所以单列。 |
| N-834 | README §2.4 与手册 §8.4 都引用 `ops/reports/d2_e2e/`，**公开树里没有这个目录** | **minor（本卡新发现）** | README:541 与 OPERATOR_MANUAL:884 是同一句话：「2026-09-13 在一台没有本项目任何遗留物的机器上做的端到端（3 题双臂 6 个 run，`ops/reports/d2_e2e/`）终态分布是……」。那段话是用来劝用户「别把一批 run 大半撞闸读成自己配错了」的，**证据目录却不在他手上**（本卡实测 `ls ops/reports/d2_e2e` = No such file or directory）。`test_readme.py` 与 `test_operator_manual.py` 各有一条红正是它。**改法二选一**：把那个目录随树发（它是构造验收产物，不是答案面），或者在两处都改成「逐步证据在发布方留存」的措辞。 |

## 二、核过没问题的（**没找到问题就说没找到**）

* **两个远端**：`refs/heads/main` = `refs/tags/v1.0.16^{}` = **bd8b158d…**（tag 对象 8fcc8246…），克隆树 `git ls-files` **2,224** 件，与上一轮终值逐字一致；GeneQuant 仍 **6ce7664e…**，本卡没碰没推。
* **三件附件**：匿名 `Range: bytes=0-0` 三件全部 **HTTP 206**，`content-range` 总长 782,100,276 / 157,448,605 / 42,046,516，与 `ops/release/attachments.json`、`RELEASE_MANIFEST.json`、README §2.1a 表**四处逐字一致**；`download_url` 三条都非空且指向 `v1.0.16`。GitHub 的资产主机**不回 `digest` 头**（只有 Azure blob 的 `etag`），所以「digest 三处比对」这一项落在 sha256 上：本卡按 §2.1a 逐字跑完 `sha256sum -c`，**29,240 行全 OK、0 条 FAILED**（3 + 28,658 + 46 + 533）。
* **Release 匿名 GET**：HTTP 200，`id` = **387775425**，`target_commitish` 仍是**字符串 `"main"`**，`draft`/`prerelease` 均 False，三件 asset 全 `state=uploaded` 且 size 与上面一致。**不需要 PATCH。**
* **`ops/test_d.py` 在克隆树里**：**15 passed / 3 skipped**，不再 collection 崩；判别力实测在 —— 改坏**克隆树自己的** README 一处 sha256 → **2 failed**，还原 → 回到 15 passed。W2 修的 N-826 站得住。
* **`ops/mk_release_manifest.py --check`**（不带 `--write`）：**退 0**，「与落盘清单一致；releasable=True」。
* **`ops/freeze_v10.py --check-all`**（不带 `--write`）：**退 0**，三条轴全绿，public 根 = `3e5ab441a991c4115a6c0fb988715f583e22ee303f582f1302fd3197fb183538`，**与任务书给的值逐字相同**；private `d9ebd541…`、参考面 `dddabe44…`。**没有重算 τ/ε，一个值没改。**
* **`build/` 五件**在克隆树里：`build/README.md` + `build/base/{Dockerfile,README.md,requirements.txt,constraints.txt}`，**正好 5 件**。
* **过期口径扫描**：`w_scan_stale.py` 在克隆树上 (a) **11** / (b) **273** / (c) **36**，与 W2 推树前那次**逐个数字相同** —— 推上去之后没有漂。另按同一口径扫了 **会打印给用户看的 `.py`**（`w_scan_stale` 只扫 `.md`）：`selfcheck_public.py` 与各 CLI 的 help/提示里共 33 处命中，**逐条判完真错 0 条** —— 全是门的断言常量（`test_d.py` 的双向门、`test_e.py` 的「附件清单为空」）、只在 `download_url` 为空时才走到的分支（三条都已回填，永远走不到）、或**本卡实测为真**的话（`mk_release_manifest.py:470`「匿名可下（不需要 token）」—— 匿名 206 已证）。
* **可执行位**：文档里**直接调用**（不带 `sh`/`bash` 前缀）的脚本 `ops/public_gateway.sh`、`ops/push_exec_to_f02.sh` 在 git 里都是 **100755**；`harnesses/build.sh` 是 100644，但文档一律写 `sh harnesses/build.sh`，**对得上**。没有「照抄一敲就 Permission denied」的地方。
* **另外 10 个交付面测试文件**在克隆树上全绿：`test_docs_consistency`(12) / `test_selfcheck_public`(20) / `test_release_manifest`(20) / `test_release_forms`(32) / `test_pack_release`(14+7s) / `test_e`(14) / `test_V2`(26) / `test_W2`(12+6s) / `test_push_guard`(25)。

## 三、登记不修（外部 clone 上判别力为零，同 N-828 一类）

| 编号 | 事项 | 状态 | 说明 |
| --- | --- | --- | --- |
| N-835 | `ops/test_public_acceptance.py` 3 红、`ops/test_a_publish.py` 1 红，都是**判据写死发布方路径** | 登记不修 | 前者两条断言 `assert '/home/ljn/ge…' == '/data/shared/…'`、一条 `FileNotFoundError` 找私有题集 `v1.0-smoke/s8-cor-01`；后者找 `$GB/snapshots/public_v1/instruments_rebuild/csi300.txt`（附件里没有这一棵）。与 N-828 同类。**文档没有叫外部用户跑这两个**，所以不像 N-833 那样单列成缺陷。 |
