# 卡 Zfin —— 交付终核（只读）

**口径**：全新空目录 `git clone --depth 1`（SSH）+ 三件附件，在**真 3.12** 上完全照 README
逐字走一遍。本卡**除本文件外一个字节都没有改仓库**、没有推树、没有碰 Release、没有写
known_limits、**一次都没连 f02**。

**环境替换（三处，如实记，判据不受影响）**
1. `GB=$HOME/genebench` → `GB=$HOME/gb_zfin/gb`。README 第 1 行原文就写「**落点自己挑**」；
   `$HOME/genebench` 是卡 Xfin / Y 的遗留物，占着就不是干净机器了。
2. `/opt/homebrew/bin/python3.12 -m venv $GB/env` → `python3.12 -m venv $GB/env`。
   README 本行行内注释即「Linux 换 `python3.12`」。f01 没有 `/opt/homebrew`。
3. README §2.1 第 5 行 `$PY -m pip install …`：f01 的 `python3.12` **无 `ensurepip`**
   （实测 `VENV_RC=1`，但 venv 的目录结构与 `pyvenv.cfg` **已经建好**），
   照 README §1.5 点名的手册 §1.2 免 root 口径，用系统 `pip3 --target` 装进
   `$GB/env/lib/python3.12/site-packages`。**Mac（brew python@3.12 自带 pip）不受这条影响。**
   §2.1a 的三条 `curl -L -O` 里两条大件换成 f01 上**同字节**本地副本（782 MB 不整件下），
   **命令形状没动**；最小那件（40 MiB）走的是**真 `curl`**，证明这条 curl 行本身通。

**证据**：`$GB/scratch/Zfin/`（`z21.log` / `z21b.log` = §2.1 逐字；`z21a.log` = §2.1a 逐字落位；
`sc2.log` = 落位后自检；`z24.log` = §2.4 ①②；`z_probe.log` / `z_p3.log` = ③④ 的断点与常量；
`z_inject.log` = 冒烟门判别力；`t17.log` = 十七个测试文件；`w_stale.txt` / `pyscan2.txt` = 两类过期口径扫描；
`mac_tools.txt` = 干净 macOS 缺的 GNU 工具；`z_bind2.log` = GATEWAY_HOST 不是本机时第一次自检长什么样；
`release_anon.txt` / `z_range.log` = 匿名回核）。

## 一、核过没问题的（**没找到问题就说没找到**）

* **两个远端**：`refs/heads/main` = `refs/tags/v1.0.16^{}` = **eb9c8508**（tag 对象 **d1169379**）；
  克隆树 `git ls-files` **2,230** 件，HEAD 与远端逐字相同。GeneQuant 仍 **6ce7664e**，本卡没碰没推。
  **匿名 https clone 也通**（f01→github 的 TLS 抖了两次，第 3 次成功，HEAD/件数与 SSH 克隆逐字相同）。
* **§2.1 逐字**：一条 `Permission denied` 都没有；唯一的 `No such file or directory` 是
  f01 链路抖动导致的那两次 https clone 失败（重试即好），不是仓库的事。
  `--harden` 收紧 113 个条目 → 自检 **绿 2 / 红 1 / 跳过 2 / 登记在案 1**，
  那条红是「这台机器真没装 docker」，**与 §2.1 新加的那段注解逐字吻合**（N-832 修得住）。
* **§2.1a 逐字**：`sha256sum -c` 三行全 OK；解包后逐件 **3 + 28,658 + 46 + 533 = 29,240 行全 OK、0 条 FAILED**；
  ③ 落位（含 `provider/` → `qlib_provider/` 改名与 `--strip-components=1`）一次过。
  落位后自检 **绿 5 / 红 1**（红仍是 docker），网关 1 秒起来、`/healthz` 200、
  `channel=public`、`freeze_line=2026-07-31`。
* **§2.4 ①**：`8 个 job → …/runs_in/v1demo/jobs.jsonl`、`pending: 8` —— **N-829 这个 block 在外部 3.12 上确实没了**。
* **§2.4 ②④**：题集根都落在 `…/reference/tasks/public/v1.0-smoke-public`（不是私有的 `v1.0-smoke`）——
  N-830 修得住。`v1demo.yaml` 那四道题（s1/s2/s3/s5-cor-01）在落位后的公开题集里**都在**；
  公开题集共 34 道 + `_ledger.jsonl`，**S4–S7 那 18 道也在**。
* **冒烟门 `ops/test_Y.py` 有判别力**（本卡自己验的）：往克隆树的 `ops/joblist.py` 注入一条重复的
  `sub.add_parser("reset")` → **3 failed**（AST 层 2 条 + 真 3.12 层 `[ops/joblist.py]` 1 条，两层都咬住了），
  `joblist.py --help` 当场抛 `argparse.ArgumentError: conflicting subparser: reset`；
  还原后 **32 passed**，`sha256sum` 与 `git diff` 双证逐字节还原。
* **`ops/mk_release_manifest.py --check`**（不带 `--write`）：**退 0**，「与落盘清单一致；releasable=True」。
* **`ops/freeze_v10.py --check-all`**（不带 `--write`）：**退 0**，三条轴全绿；
  public 根 = `3e5ab441a991c4115a6c0fb988715f583e22ee303f582f1302fd3197fb183538`，**与任务书给的值逐字相同**；
  private `d9ebd541…`、参考面 `dddabe44…`。**没有重算 τ/ε，一个值没改。**
* **`build/` 五件**在克隆树里：`build/README.md` + `build/base/{Dockerfile,README.md,requirements.txt,constraints.txt}`。
* **三件附件匿名 `Range: bytes=0-0`**：三件全 **HTTP 206**，`content-range` 总长
  **782,100,276 / 157,448,605 / 42,046,516**，与 `ops/release/attachments.json`、
  `RELEASE_MANIFEST.json::release_attachments`、README §2.1a 表**四处逐字一致**。
  GitHub 资产主机**不回 `digest` 头**（只有 Azure blob 的 `etag`），digest 落在 sha256 上核 —— 已全绿。
* **Release 匿名 GET**：HTTP 200，`id` = **387775425**，`target_commitish` 仍是**字符串 `"main"`**，
  `draft`/`prerelease` 均 False，三件 asset 全 `state=uploaded`，size 与 API 侧 `digest`（sha256）
  与上表逐字相同。**不需要 PATCH。**
* **十七个测试文件**（真 3.12、外部 clone）：`test_d` 15p/3s、`test_readme` **218p/2s**、
  `test_docs_consistency` 12p、`test_operator_manual` **193p**、`test_selfcheck_public` 20p、
  `test_release_manifest` 20p、`test_release_forms` 32p、`test_pack_release` 14p/7s、`test_e` 14p、
  `test_V2` 26p、`test_W2` 12p/6s、`test_push_guard` 25p、**`test_Y` 32p**、`test_report_columns` 45p/1s
  —— **十四个文件全绿**。剩下三个的红**全部是早已登记的**：`test_public_acceptance` 3 红 +
  `test_a_publish` 1 红（**N-835**，判据写死发布方路径，文档没叫外部用户跑）、
  `test_env` 6 failed / 57 passed / 1 skipped（README 自己写着「**不是给你跑的**」）。
  **没有一条新红。** 卡 Xfin 那轮 `test_readme` 4 红 / `test_operator_manual` 5 红（含 1 条 ValueError 崩）
  **本轮一条不剩**。
* **过期口径扫描**：`w_scan_stale.py` 在克隆树上 (a) **11** / (b) **280** / (c) **37**，
  与卡 Y 推树前那次**逐条相同**（本次原始输出是 282，多出的 2 条逐条比对确认来自**解包出来的附件内文档**
  `genebench_public_gold_subset_v1/docs/…/instruments_switch.md`，不是树里的文件）。
  另按同一口径扫**会打印给用户看的 `.py`**：38 条命中，与卡 Xfin 那次**逐条相同（diff 为空）**，
  逐条判完**真错 0 条** —— 全是门的断言常量、只在 `download_url` 为空时才走到的分支
  （三条都已回填，永远走不到），以及本卡实测为真的话（`mk_release_manifest.py:470`「匿名可下（不需要 token）」——
  匿名 206 已证）。

## 二、发现（按严重度）

| 编号 | 事项 | 状态 | 说明 |
| --- | --- | --- | --- |
| N-839 | README §2.1a 的验包块用 `sha256sum`，**干净 macOS 上没有这个命令** | **major（本卡新发现）** | README:325 / 329 / 331 / 333 四条，外加 README:269、471 与手册里 3 处。干净 macOS 只有 `shasum`（perl）与 `openssl`，**`sha256sum` 不在 `/usr/bin`**（要 `brew install coreutils`）。而 README §1.5:206 有一句**看起来穷举**的「**macOS 上没有这四个 Linux 工具**：`ufw`、`systemctl`、`ss`、`setsid`」——`sha256sum` 不在其中，于是读者有理由相信这张表是全的。**全仓库 `shasum` / `coreutils` / `gsha256sum` 出现 0 次**（README + 手册都是 0）。后果：Mac 用户下完 936 MiB 之后的**第一条验证命令**就 `command not found`，而 §2.1a 紧接着写「三行都要 OK —— 少一行就是没下全，别急着解包」。**改法**：`sha256sum -c X` → `shasum -a 256 -c X`（同一份校验和文件格式，`-c` 模式行为一致），或在 §1.5 那张「macOS 没有的工具」里补上它并给等价写法。**有出路**：README:269 自己就写着「`sha256sum -c` —— 这两样 `ops/selfcheck_public.py` 都替你跑了」（纯 Python，实测绿），所以不是死路，只是会停下来。 |
| N-840 | `ops/push_exec_to_f02.sh` / `ops/push_bundle_to_f02.sh` 的 `GENEBENCH_PY` **默认值是发布方那台的解释器**，而两处文档一次都没提过这个变量 | **block（本卡新发现）** | `ops/push_exec_to_f02.sh:29` 与 `ops/push_bundle_to_f02.sh:16` 都是 `PY="${GENEBENCH_PY:-/data/shared/genebench/env/bin/python}"`；同文件 `:32` 还有 `STAGE="${GENEBENCH_EXEC_STAGE:-/data/shared/genebench/scratch/exec_push}"`，`push_bundle_to_f02.sh:61` 还有 `GENEBENCH_APG_LOG` 默认 `/data/shared/genebench/logs/…`。**`GENEBENCH_PY` / `GENEBENCH_EXEC_STAGE` / `GENEBENCH_EXEC_DEST` 在 `README.md`、`docs/OPERATOR_MANUAL.md`、`ops/HANDOFF.md` 里 grep 命中 0 次。** 而 README §2.4 ③ 给的是**裸命令** `ops/push_exec_to_f02.sh --with-launch-data`，前面没有任何 env。**实测**（把 `GENEBENCH_PY` 指到一个不存在的解释器，等价于干净 Mac 上 `/data/shared/genebench/env/bin/python` 不存在）：走到 `== 3/6 用执行面自己那道门扫 staging` 时 `ops/push_exec_to_f02.sh: line 133: …: No such file or directory`，**rc=127**。这是**过了网关之后、干净 Mac 上的第一处硬停**。与 N-770 / N-826 / N-831 同形：**分叉在「跑它的是不是发布方那台机器」上**。**改法**：默认值改成 `cfg.PYTHON`（即 `$GENEBENCH_ROOT/env/bin/python`，两处文档已经反复写它是硬要求的落点），`STAGE` 改成 `$GENEBENCH_ROOT/scratch/exec_push`；并把这三个变量补进 README §2.3 与手册 §1.3 那张表（那张表现在只有三个地址常量 + `GENEBENCH_F02`）。 |
| N-841 | 执行面 run 根 `/data/genebench_runner` 写死、且被推送脚本**强制**，而 macOS 根卷只读、建不出 `/data` | **block（本卡新发现）** | `ops/run_joblist.py:77` `RUNNER_ROOT = "/data/genebench_runner"`（**没有 env 兜底** —— 同文件 `:76` 的 `F02` 刚在 N-831 里加了兜底，紧挨着的这一行没有）；`ops/push_bundle_to_f02.sh:69-70` 更是把它写成**硬判据**：`case "$DST" in /data/genebench_runner/*) : ;; *) echo "推送中止：目标 $DST 不在 /data/genebench_runner/ 下"; exit 1`。单机形态下「执行面」就是这台 Mac 自己，而 **macOS 自 Catalina 起根卷只读**：`sudo mkdir /data` 报 `Read-only file system`，要建得动得写 `/etc/synthetic.conf` 再**重启**。README §2.3 把单机形态要改的东西**逐条列了**（`GATEWAY_HOST`、`runner_core` 两处、`GENEBENCH_F02`），**这一条不在里面**，而那份列举读起来就是「全部」。**改法**：`RUNNER_ROOT = os.environ.get("GENEBENCH_RUNNER_ROOT", "/data/genebench_runner")`，`push_bundle_to_f02.sh` 的 ② 段按同一个变量判（**这道门不能去掉** —— 它防的是手滑推到对面别处，只是判据要跟着根走），然后进 README §2.3 与手册 §1.3 那张表。 |
| N-842 | `ops/push_bundle_to_f02.sh` 的 timer 核查在 Mac 上「**过不去**」，而**没有任何绕过开关** | **block（本卡新发现；手册已承认现象，但没给出路）** | `ops/push_bundle_to_f02.sh:36-42`：推之前 `ssh "$F02" "systemctl --user is-enabled genebench-answer-plane-scan.timer && systemctl --user is-active …"`，不过就 `exit 1`。手册 §1.3 (3) 已经如实写了「**Mac 上这条核查过不去**」，还给了 launchd 的等价做法（`~/Library/LaunchAgents/*.plist` + `StartInterval 3600`），**但脚本核的是 `systemctl`，装了 launchd 等价物这条核查照样过不去**。全脚本 grep `no-timer` / `skip` / `bypass` / `--force` **命中 0**。于是单机 Mac 用户在 README §2.4 ④ 上被一道**明知过不去、且无路可走**的门挡住，只能改源码 —— 而手册那一段的落点是「你少的是第三道兜底，前两道仍在」，**没有说「所以推送脚本你要怎么办」**。**改法二选一**：① 给一个显式的 `--no-timer-check`（打印一行「你少了第三道兜底」），② 把核查改成「有 `systemctl` 才核，没有就打印手册 §1.3 (3) 那段并放行」。**别默默放行**。 |
| N-838 更新 | `ops/gateway_lock.py:34` 的 `LOCK` 写死 `/data/shared/genebench/locks/gateway.lock`，不跟 `GENEBENCH_ROOT` | **block（卡 Y 已登记为 v11_deferred；本卡把它实测成「干净 Mac 上必停」）** | 本卡实测：`GENEBENCH_ROOT=/home/ljn/gb_zfin/gb` 时 `ops.gateway_lock.LOCK` 仍打印 `/data/shared/genebench/locks/gateway.lock`。`gateway_lock()` 第一件事就是 `LOCK.parent.mkdir(parents=True, exist_ok=True)`，而 `ops/run_joblist.py:459` 的真跑**每个 job 都进这个上下文**。干净 Mac 上 `/data` 建不动（同 N-841），于是 §2.4 ④ 的第三段必崩。卡 Y 的修法建议照旧有效，并重申它那句要紧的话：**改完必须连着核一遍所有拿这把锁的调用方** —— 红线 6 要求真跑与跑批串行，锁一换根就不再互斥。**本卡补一条**：换根之后 f01 上已有的那把锁（`/data/shared/genebench/locks/gateway.lock`）与新根下的锁**会是两把**，发布方自己的跑批要同步切过去，否则内部反而失去互斥。 |
| N-843 | README:468–471 的 macOS 状态框里，**两条成因都已经不成立了**，而现在真正拦路的四条一条没列 | **major（本卡新发现）** | 原话：「**macOS（arm64）上还没跑通**：2026-09-13 的外部验收走到「建 harness 镜像」就停了 —— 本机没有统一基座 `gb-base:bookworm-r1`，公开题集 S4–S7 那 18 道题的输入夹具也没有随两个附件交付。」**成因①已消失**：`build/base/` 同日已随树发（本卡实测克隆树里正好五件），`harnesses/build.sh` 缺基座时会自己构，`build/base/README.md` §3 给了 `docker build -t gb-base:bookworm-r1 build/base`。**成因②也已消失**：第三件附件带来的公开题集树里 **S4–S7 的 18 道题都在**（本卡落位后实测）。措辞是过去时、逐字**不算说假话**（「随**两个**附件」当时为真），但一个新读者读到的是「这两件事挡着」，照着去补完就会撞上 N-840 / N-841 / N-842 / N-838 这四条**一条都没被提到**的墙。**结论仍然成立**（Mac 侧确实只验到网关），要改的是**成因列表**。**改法**：把这两条改写成「当时的成因，两条**同日都已补上**」，并把当前真正的四条拦路写进去 —— 它们才是「Mac 上验到网关为止」这句话今天的内容。 |
| N-844 | README §2.1 的「照上面的顺序跑，**最后一眼就是好的**」，与 §2.3 ③ 自己那句「这是外部用户**第一步就会撞上**的事」互相矛盾 | **minor（本卡新发现）** | §2.1 那段注解把首跑残留的红**穷举成一条**：「再自检就是**绿 5 / 红 1**（剩下那条红是那台机器真没装 docker）」。但 `genebench_config.py:562` 是 `GATEWAY_HOST: str = "192.168.1.48"` —— **发布方 f01 的地址**，任何别的机器都绑不上。本卡实测（把它改成本机没有的地址，等价于干净 Mac）：§2.1 最后一行的自检是**绿 4 / 红 2**，第 6 项红在「`genebench_config.py::GATEWAY_HOST` 现在是 …，**这台机器绑不上它**」。**这条红本身写得非常好**（直接给了改法、指了手册 §1.3），§2.3 ③ 也明说「外部用户第一步就会撞上」—— 所以问题只在 §2.1 那句穷举。**改法**：§2.1 那段把残留的红写成两条（docker + `GATEWAY_HOST`），并就地指一句「地址那条的改法在 §2.3 ③」。 |
| N-845 | 基座构建耗时两处不同源：README:478 / 手册:158 说 **69 秒**，`build/base/README.md` §5 与 `ops/reports/base_image_portability.md` 说 **282 秒** | **minor（本卡新发现）** | 两个都是真实测量、都是 `--no-cache`、都是 2026-09-13、都是 Linux x86_64：282 秒那次在 f01（`x86_64 Ubuntu，Docker 29.1.3，12 核 30 GB`），69 秒那次在 f02 的干净 clone 上（`ops/reports/mac_gap_closeout.md:187`）。但**说 69 秒的那两处都没写是哪台机器**，而用户查「要多久」时会去看 `build/base/README.md` §5（写着 282 秒）—— 同一条命令、同一天、4 倍差，读者无从调和。`base_image_portability.md:169` 给的 arm64 估计（**4–8 分钟**）又是按 282 秒折算的。**改法**：README:478 与手册:158 那两处补一句机器（「在执行面那台上 69 秒」），或统一引 `build/base/README.md` §5 的 282 秒并说明 69 秒是另一台。 |
| N-846 | README §3「仓库布局」那张顶层表里**没有 `build/`** | **minor（本卡新发现）** | 表里列了 `genetask/` `gateway/` `runner/` `harnesses/` `integrations/` `snapshots/` `reference/` `scorer/` `ops/` `docs/` `tasks/`，**独缺 `build/`** —— 而 `build/base/` 正是「用仓库自带的 Dockerfile 构 arm64 基座」这一步唯一的落点，也是 2026-09-13 才搬进来、专门为外部用户加的那棵子树。README 全文只在 :358 与 :478 顺带提到 `build/`，都不是「它在哪」。叠加 `build/README.md` 自己记的那条：`.gitignore` 第 6 行有一条**不锚定**的 `build/`，所以在这棵子树里新建文件 `git status` 不提醒（N-752，登记未修）。**改法**：§3 那张表补一行 `build/`（一句话：统一基座 `gb-base:bookworm-r1` 的构建上下文，`harnesses/build.sh` 缺基座时来这里构）。 |
| N-847 | `GENEBENCH_ROOT` 不设时的默认值仍是发布方的 `/data/shared/genebench`，而两处文档都没说「这个 export 要一直在」 | **minor（本卡新发现，本轮最弱的一条）** | `genebench_config.py:140-141` = `os.environ.get("GENEBENCH_ROOT") or _DEFAULT_ROOT`，`_DEFAULT_ROOT` 是 `/data/shared/genebench`。README §2.1 第 1 行有 `export GENEBENCH_ROOT=$GB`，但**只在那一个 shell 里**；而整条路径要跨几个小时（下 936 MiB、构镜像、一批真跑 2 小时），换个终端窗口就没了。实测：不带这个 env 跑 `ops/run_joblist.py --help`，`--channel` 的帮助文本里渲染出来的题集根就是 **`/data/shared/genebench/reference/tasks/public/v1.0-smoke-public`** —— 发布方的路径，打印给外部用户看。**失败是响的**（那个目录在 Mac 上不存在），不是静默，所以只记 minor。**改法**：§2.1 那块末尾补一句「这两行建议写进你的 shell profile —— 后面每一步都吃这个变量」。 |

## 三、登记不修 / 复核未变

| 编号 | 事项 | 状态 |
| --- | --- | --- |
| N-835 | `ops/test_public_acceptance.py` 3 红、`ops/test_a_publish.py` 1 红，判据写死发布方路径 | 复核未变，仍登记不修：文档没有叫外部用户跑这两个 |
| N-370 | 红线 3 扫描器扫到 `$GB/scratch/Xfin/clean/` 那棵 clone 里 `ops/test_env.py` **自己的反面夹具** | 复核未变。本卡的验证树刻意放在 `$GB` 之外（`/home/ljn/gb_zfin/`），**没有给这道门再添一条 offender** |
| N-752 | `.gitignore` 第 6 行那条不锚定的 `build/` | 复核未变（N-846 里再提了一次，因为它正好落在外部用户要用的那棵子树上） |
