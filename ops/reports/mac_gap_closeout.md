# Mac 外部验收七条缺口的收口（2026-09-13，卡 D2）

**这份文件回答一个问题：用户 2026-09-13 在一台干净 Mac 上报出来的七条，今天各自做到没有。**
每条给四样：**判定 / 做了什么 / 判据是什么 / 证据在哪**。
第 §5 节是本轮的核心 —— **一次真的端到端**：一台没有本项目任何遗留物的树，
从 clone 走到「三题双臂出十九列表」，以及它在哪一步**没走通**。

> **来源**：用户的验收报告在他本机 `~/GeneBench-validation-20260913/VALIDATION_REPORT.md`，
> 证据在同目录 `evidence/`。结论是「**下载 / sha256 / 解包 / 本机网关四项通过，端到端阻塞**」。
> **本轮四张卡**：A2（基座）/ B2（物料）/ C2（文档）/ D2（收口 + 端到端实证）。
> **本轮只落到内网仓库**：没有重打公开树、没有 push、没有碰 Release、没有动附件、三条版本轴一个值没改。

---

## 0. 最要紧的一句话

上一轮的「单机端到端」演练（`ops/reports/rehearsal_v2.md`，2026-09-11）跑在 **f02** 上，
而那台机器**本来就有**统一基座镜像、公开题集实例、公开标定物料 —— **所以演练看不见它缺**。
用户那台干净 Mac 是第一次把「这三样根本没发出去」这件事照出来。

**教训写在明处**：在一台参与过开发的机器上做「外部用户」演练，量不出缺件。
判据必须是「**这台机器上没有本项目的任何遗留物**」，而不是「我新建了一个目录」。
本卡的端到端因此刻意**不复用 f02 上任何既有物**：新目录、干净 clone、**新 tag 的基座与 harness**
（`--no-cache` 现构），既有 `gb-base:bookworm-r1` 与 `gb-cx-u:r1` 全程没碰、收尾逐个核过 image ID 不变。

---

## 1. 用户那七条，逐条判

### ① 统一基座没有交付

**判定：已做到。**（卡 A2，提交 `b9cac71`）

* **做了什么**：整套基座构建上下文进仓库 —— `build/base/{Dockerfile,requirements.txt,constraints.txt,README.md}`
  与 `build/README.md`；`harnesses/build.sh` 缺基座时**自己从 `build/base/` 构**，
  报错文案里不再出现 `/data/genebench_runner/build/base/Dockerfile` 这种外部没有的绝对路径；
  Node 的 tarball 与 sha256 **按架构分**（原来只钉 x64 —— 在 Apple Silicon 上必然「下 arm64 的包、拿 x64 的哈希核」，
  表现像下载损坏）。
* **判据**：**D2 独立复现** —— 在 f02 的干净 clone 上 `docker build --no-cache -t gb-base:d2e2e-20260913 build/base`，
  **69 秒**构成，`docker run … python3 -m pip freeze --all` 与既有 `gb-base:bookworm-r1` **逐行相同**（各 8 行），
  `node --version` = `v22.23.2`、`python3 -V` = `Python 3.12.14`、`uname -m` = `x86_64`。
  harness 叠上去 **40 秒**构成，`codex --version` = `codex-cli 0.153.2`。
* **证据**：`$GB/scratch/D2/evidence/build.log`；`pipfreeze_new.txt` / `pipfreeze_old.txt`（diff 为空）；
  卡 A2 的 `ops/reports/base_image_portability.md`。

### ② macOS 的 shell 在缺基座分支报 `BASE_IMAGE…: unbound variable`

**判定：已做到。**（卡 A2）

* **做了什么**：病灶不是「判断发生在展开之后」，而是 `"$BASE_IMAGE。"` 这种
  **变量名后紧跟中文标点**的写法 —— macOS 的 bash 3.2 在 UTF-8 locale 下把标点的头一个字节吃进变量名，
  `set -u` 当场炸。全脚本改成 `${VAR}`。
* **判据**：卡 A2 在 Mac 本机做过六组合复现（`/bin/sh` 与 `/bin/bash` 在 `LC_ALL=en_US.UTF-8` 下必炸、
  `LC_ALL=C` 下正常、zsh 两种都正常），并留了回归锁
  `ops/test_A2.py::test_build_sh_has_no_bare_var_before_nonascii`（**做过必红演示**：注入病灶当场红，
  而 `sh -n` 在病灶版上照样通过 —— 静态语法检查抓不到它）。
  **D2 复核**：`ops/test_A2.py` 等四个文件 **72 passed / 1 skipped**。
* **证据**：`$GB/scratch/A2/evidence/mac-unbound-variable-repro.txt`；`ops/test_A2.py`。

### ③ 运行物料不全（公开题集夹具、`calibration.json`、`epsilon/`、`tables/manifest.json`）

**判定：前三样已做到（**打成第三个附件，但本轮还没上传**）；`tables/manifest.json` 查清**不该发**。**（卡 B2）

* **做了什么**：`genebench_public_runtime_v1.tar.gz` —— 整棵公开题集树（506 件）
  + `snapshots/public_v1/{calibration.json,calibration.sha256,epsilon/}`，
  登记进 `ops/release/attachments.json`，**`download_url` 是空串 = 还没上传**。
  根因查清了：公开树是 `git archive HEAD` 打的，而公开题集与标定物料按红线 6 落在
  `$GENEBENCH_ROOT` 之下、**在仓库之外** —— `git archive` 的射程里根本没有它们。
* **判据（D2 自己重跑了一遍，不采信转述）**：f02 上全新目录 + 干净 clone（`git clone -b main`，2,209 件，
  `reference/tasks/public` **不在**）→ 落位三个附件 → `ops/freeze_v10.py --check-all`
  **退出码 0，三条根全部与冻结清单一致**，公开根现算
  `3e5ab441a991c4115a6c0fb988715f583e22ee303f582f1302fd3197fb183538`（**与清单逐字相同**，
  也就是用户报告里那条 `c5639e55…` 的差异被补齐了）。
  **全程一次 `--write*` 都没跑过。** 三个包的逐件校验：provider **28,658/28,658 OK**、
  gold **46/46 OK**、runtime **533/533 OK**。
* `tables/manifest.json`：`gateway/backends.py:115` 只在**私有**分支看它，公开通道上一行就无条件
  `return "snapshot"` —— 显式 public/snapshot 下不需要它。用户报告里「不存在但日历读取仍成功」的观察是对的。
* **证据**：`$GB/scratch/D2/evidence/setup.log`（包体与逐件校验）、`setup4.log`（`--check-all` 退 0 与三条根）；
  卡 B2 的 `ops/reports/public_runtime_material.md`、`ops/data_cards/public_runtime_v1.md` §4。

### ④ Mac 上没有 `ufw` / `systemctl` / `ss` / `setsid`

**判定：已做到（文档与脚本两侧都改了）；其中一件**在 Mac 上仍是缺口**，已写明。**（卡 C2）

* **做了什么**：`ops/public_gateway.sh` 三处分岔，**由 `command -v` 当场判、不看操作系统名**
  （查端口 `ss` → `lsof` → `nc`；查 pid `ss -ltnp` → `lsof -t`；脱离终端 `setsid nohup` → `nohup`）。
  README §2.3 与手册 §1.3 写清：Mac 没有 `ufw`，它的包过滤是 `pf`，而 Docker Desktop 的容器跑在一层 Linux
  虚拟机里、打宿主不经过宿主 INPUT 链 —— **那条 `ufw` 规则要解决的问题在 Mac 上换了形状**；
  **替代的隔离判据没变，仍然是容器边界那一条**（`answer_plane_guard.py --mode container` 读 compose 挂载面）。
* **仍是缺口**：推送守门要求执行面上 `genebench-answer-plane-scan.timer` 处于 `enabled + active`，
  **这是 systemd 的东西，Mac 上没有**。手册 §1.3 写了「少的是什么」与 launchd 的等价形状，
  但**那份 plist 没写、也没在 Mac 上验过**（卡 C2 自己标明）。少的是**第三道兜底清扫**，不是主判据。
* **判据**：C2 在 f01 上把 `ss` 与 `setsid` 从 PATH 里遮掉、逐条走同一支代码补验了「真起来 + 200 + stop 端口释放」；
  Mac 本机验到的是分支选择与判定（`have ss`=no / `have setsid`=no / `have lsof`=yes）。
  **「在 Mac 上原样跑 `public_gateway.sh start` 拿 200」这一步施工侧没能亲手验到**
  —— 施工用的 Mac 沙箱不许 bind 任何监听口。已登记（N-769）。
* **证据**：`ops/public_gateway.sh`；`$GB/scratch/C2/{both.log,macbranch.log,macbranch2.log}`；
  用户自己那次无沙箱的 `evidence/healthz.json`。

### ⑤ 路径与自检仍绑定发布方环境（`ops/test_env.py` 10 failed）

**判定：已做到（换了自检入口）；但**代码里写死发布方路径这件事本身没有修完**，D2 又量出三处新的。**（卡 C2 + D2）

* **做了什么**：`ops/test_env.py` 从 README 的外部步骤里**移除**，文件头写明「内部自检，外部用户不要跑这个」
  并把「外部实测 10 failed / 52 passed / 2 skipped、**那些红不是缺陷**」写进去；
  新增 `ops/selfcheck_public.py` 作为外部自检（六项：Python ≥ 3.12 / 六个包 / docker 在不在且内存够 /
  附件落位与 sha256 / 三条冻结根 `--check-all` / 网关起不起得来），四种状态**绿 · 红 · 跳过 · 登记在案**，
  **只有红条才退非零**。
* **没修完的**（D2 在端到端那条链上实测撞到）：`ops/score_runs.py:45` 的 `RUNS_IN`、
  `ops/score_runs.py:44` 的 `F02`、`ops/guard_modes.py` 的 `EXTERNAL_ROOTS`，以及卡 B2 早就指出的
  `ops/run_controls.py:48/49/53/54`。**逐条在 §5.3。**
* **判据**：`ops/test_selfcheck_public.py` 20 条 + `ops/test_docs_consistency.py` 8 条事实（**双向验过判别力**：
  对改前文档 10 红 / 对改后 10 绿）。D2 复跑 **72 passed / 1 skipped**。
* **证据**：`ops/selfcheck_public.py`；`$GB/scratch/C2/{selfcheck_clean.json,selfcheck_full.json}`。

### ⑥ 文档状态冲突（README §2.3 vs 手册 §1.1/§1.3 vs §1.4(a)）

**判定：已做到。**（卡 C2）

* **做了什么**：三处改成**同一句** —— 形态 ① 单机「Linux 上 2026-09-11 已端到端跑通 /
  macOS arm64 上 2026-09-13 卡在建 harness 镜像，同一次验收里下载 → sha256 → 解包 → 本机网关 200 四步实测通过」；
  手册 §1.4(a) 的「今天走不通」→「今天通了」（旧话用「」引着留下）。
* **判据**：新增 `ops/test_docs_consistency.py` —— 一张手写的「事实 →（文件, 判据）」表，
  **每条要求两处都把现状说出来、都不许留相反说法**；匹配前去掉「」里的旧版原文并压平空白。
  **本卡这一轮的实测让 §2.3 那一句需要再改一次口**（见 §7）。
* **证据**：`ops/test_docs_consistency.py`；README §2.3、手册 §0.3 / §1.1 / §1.3 / §1.4(a)。

### ⑦ 十九列表入口不匹配（README §2.4 写 `--table a`）

**判定：已做到，且**这一轮真的出了一张 24 列的表**。**（卡 C2 + D2）

* **做了什么**：README §2.4 改成 `--table main`，并补一张对照表写明
  「**19 个指标列 + 5 个身份列 = CSV 24 列**，列名与顺序写死；`table_a` 是**诊断件**，别当发布读数往外贴」；
  `run_joblist --tables` 也改成 `main,a,b`。
* **判据（D2 实证）**：见 §5.4 —— 真跑出来的 `table_main.csv` 表头**逐字** 24 列，
  与 `ops/test_report_columns.py` 钉的十九列 + 五个身份列逐字相同。
* **证据**：`$GB/scratch/D2/evidence/{table_main.csv,table_main.md,table_main.axes.json}`。

---

## 2. 一句话汇总

| # | 用户报的 | 判定 |
| --- | --- | ---: |
| ① | 统一基座没交付 | **已做到**（并由 D2 在干净 clone 上独立构了一次） |
| ② | Mac shell 的 `unbound variable` | **已做到**（带回归锁，做过必红演示） |
| ③ | 运行物料不全 | **已做到**，但**第三个附件还没上传**（要用户点一次头） |
| ④ | Mac 没有 ufw/systemctl/ss/setsid | **已做到**；其中「答案面扫描 timer 的 Mac 等价」仍是缺口，已写明 |
| ⑤ | 路径与自检绑死发布方环境 | **自检入口已换**；**写死路径没修完**，D2 又量出三处（§5.3） |
| ⑥ | 文档状态冲突 | **已做到**（并加了一道「两处不得互相打架」的门） |
| ⑦ | 十九列表入口 | **已做到**，且本轮真的出了一张 24 列的表 |

---

## 3. 端到端实证：环境与「不许复用」是怎么保证的

| | |
| --- | --- |
| 机器 | f02（`finance02`，x86_64，Docker 29.1.3，12 核 / 30 GB） |
| 落点 | `/data/d2_e2e`（**全新目录**），`GENEBENCH_ROOT=/data/d2_e2e/gb`，0700 |
| 仓库 | 从内网仓库打 `git bundle` 送过去、`git clone -b main` 出来。HEAD `b9cac71`，工作树 **0 条改动**，**2,209 件**。`reference/tasks/public` **不在 clone 里**（这正是缺件② 的形状） |
| 附件 | 三件，逐件核过：包体 sha256 与 `ops/release/attachments.json` 逐字相同；包内逐件 **28,658 / 46 / 533 全 OK** |
| 基座 | **新 tag** `gb-base:d2e2e-20260913`，`docker build --no-cache`，**只用仓库里的 `build/base/`** |
| harness | **新 tag** `gb-cx-u:d2e2e-20260913`，`--no-cache`，叠在**新基座**上 |
| 不许复用的核对 | 开工前记下 `gb-base:bookworm-r1` = `fd1e2fd0c7ae…`、`gb-cx-u:r1` = `961e3878b28f…`；**收尾逐个核，两个 ID 一字未变** |
| 任务容器真的跑的是哪个镜像 | bundle 的 `image/Dockerfile` 是 `FROM gb-cx-u@sha256:01f2a0852ed4…`，`docker ps` 里任务容器的镜像列就是 `01f2a0852ed4` |
| provider 真的喂的是哪棵树 | run.json 的 `provider.sha256_root` = `f7dda2899071b07a…`（28,609 件），源 `/data/d2_e2e/gb/snapshots/public_v1/qlib_provider` —— **公开那棵，不是发布方的私有树** |

**一处与「纯外部用户」的偏差，写在明处**：`harnesses/build.sh` 的 `BASE_IMAGE` 写死
`gb-base:bookworm-r1` 且**没有环境变量入口**，而这台机器上那个 tag 被既有镜像占着 ——
照它走就等于复用遗留物。所以 harness 那一步没走 `build.sh` 的构建支路，改成把 `harnesses/codex/`
的构建上下文原样复制到 scratch、**只改 `FROM` 一行**（diff 就一行，留在 `build.log` 里）。
`build.sh` 的**前置核查支路**（`--dry-run`）照样走了一遍并全绿。
**外部用户没有这个冲突**（他们机器上没有同名镜像），照 README 敲 `sh harnesses/build.sh codex` 就对。已登记 N-777。

---

## 4. 走到哪一步、每一步的实测

| 步 | 做了什么 | 结果 | 耗时 |
| --- | --- | --- | ---: |
| ① clone | `git clone -b main <bundle>` | 2,209 件，工作树干净 | 秒级 |
| ② 三个附件 | 包体 sha256 + 包内逐件 | 3/3 OK；28,658 + 46 + 533 全 OK | 约 1 分钟 |
| ③ 落位 | runtime 那件有现成命令；**两个大件没有任何文档给过落位命令**，D2 现场自己映射 | `snapshots/public_v1/` 下 9 项就位，题集 34 个目录 | 秒级 |
| ④ 解释器 | `python3 -m venv` 建出一个**没有 pip 的半成品**；改走手册 §1.2 的免 root 路线，但 `bootstrap.pypa.io` **挂住 11 分钟 0 字节**；最后从国内镜像直取 pip 的 wheel | 六个包 + h11 就位 | 80 秒（前两次失败另计 ~15 分钟） |
| ⑤ 冻结根 | `ops/freeze_v10.py --check-all`（**没跑过任何 `--write`**） | **退 0**，三条根全部与清单一致，公开根 `3e5ab441…` | 秒级 |
| ⑥ 基座 | `docker build --no-cache -t gb-base:d2e2e-20260913 build/base` | 成功；`pip freeze --all` 与既有基座**逐行相同** | **69 秒** |
| ⑦ harness | `docker build --no-cache`（FROM 指向新基座） | 成功，`codex-cli 0.153.2` | **40 秒** |
| ⑧ 起网关 | 改 `GATEWAY_HOST` → 本机 LAN；`$PY -m gateway.run --workers 1` | `/healthz` 200：`channel=public`、`bind=192.168.1.219:18080`、`tables_dir` 指向本卡自己的树；`/calendar` 10 行真数据 | **约 3 秒** |
| ⑨ 容器打网关 | 建 `172.31.243.0/24` 的网跑 alpine | 放行网段 → 本机宿主 **200**；**默认 bridge → 超时**（判别力那一行，与演练 §3 一致） | 秒级 |
| ⑩ 出集 | `ops/export_bundle.py` × 3，`--digest` 钉新镜像 | 三个 bundle 全绿；容器边界门 3/3 绿；`push_guard` 加 `GENEBENCH_CHANNEL=public` 后 3/3 绿 | 约 30 秒 |
| ⑪ `--dry` 自查 | 不起容器、不调模型、不读凭据 | **绿**：两臂 `work/` 的独有集与同名 sha 差异逐条对上 | 秒级 |
| ⑫ 真跑 | 3 题 × 双臂 = **6 个 run**，串行，`--max-calls 100` | 全部跑完，见 §5.1 | **2 小时 1 分** |
| ⑬ 结算 | `ops/score_runs.py`（公开通道显式给 `--ref-tasks` / `--gateway-log`） | **runs: 6；问题: 0**；重跑一遍结果相同 | 秒级 |
| ⑭ 入库 | `ops/results_db.py ingest --channel public` | `added=6 / duplicate=0`；四条轴齐 | 秒级 |
| ⑮ 出表 | `ops/mk_tables.py --table main --format csv` | **2 行 ← 6 条记录，24 列** | 秒级 |

**落位那一步的映射（文档里今天还没有，N-771）**：
`genebench_public_provider_v1/provider/` → `$GB/snapshots/public_v1/`**`qlib_provider`**`/`（**要改名**，
`genebench_config.PUBLIC_PROVIDER_DIR`）；`tables/` `tradability/` `universe/` `frozen/` → 同名落
`$GB/snapshots/public_v1/`；`genebench_public_gold_subset_v1/gold_factors/` → `$GB/snapshots/public_v1/gold_factors/`；
`genebench_public_runtime_v1.tar.gz` 有现成命令（`--strip-components=1 -C "$GENEBENCH_ROOT"`）。

---

## 5. 真跑与十九列表

### 5.1 六个 run（**构造验收，不是能力读数**）

真 API 全部走 f02 的 DeepSeek key（`~/.config/genebench/secrets.env`，0600，**本卡没有 cat / echo / 复制过它**）。
整段包在 `$PY ops/gateway_lock.py --what "D2:mac缺件收口端到端真跑（3 题双臂，f02 单机）" -- ssh …` 里，从 f01 侧起。

| run_id | 结算 `run_status` | 墙钟 | `llm_log` 里 `decision==allow` | artifact |
| --- | --- | ---: | ---: | ---: |
| `s1-cor-01.strict.cfg-codex-deepseek.r01@finance02-9a64489e` | `timeout` | 1548.1 s | **89** | 1,733 B |
| `s1-cor-01.open.cfg-codex-deepseek.r01@finance02-9a64489e` | `budget_exhausted` | 921.0 s | **100** | 0 |
| `s2-cor-01.strict.cfg-codex-deepseek.r01@finance02-9a64489e` | `budget_exhausted` | 1439.4 s | **100** | 0 |
| `s2-cor-01.open.cfg-codex-deepseek.r01@finance02-9a64489e` | `ok` / `valid` / l3 `align:False` | 1212.0 s | **100** | 1,469 B |
| `s3-cor-01.strict.cfg-codex-deepseek.r01@finance02-9a64489e` | `violation` / `invalid` / gate `declared_reads` | 1292.0 s | **93** | 1,105 B |
| `s3-cor-01.open.cfg-codex-deepseek.r01@finance02-9a64489e` | `budget_exhausted` | 874.4 s | **100** | 0 |
| **合计** | | **2 小时 1 分** | **582 次** | |

**这一栏不是能力读数**，是**构造验收**：它证明的是「这条链路在一台干净机器上能把一次真运行变成一行主表」。
四个撞到 100 次调用闸、一个撞 1500 秒墙钟闸 —— 与 2026-09-11 演练的形状一致（那一次也是 s1 两臂全撞闸）。

### 5.2 主表：19 指标列 + 5 身份列 = CSV 24 列

表头逐字（`ops/reports/d2_e2e/table_main.csv` 第一行）：

```
config_id,arm,arm_kind,n_tasks,n_runs,SR,P@1,$,Cov,Prov,Cell%,Adj,Fid,Decl,IC-agr,Set,Sig,ρ̄,W-agr,Cons,ε-agr,Ledger,Audit,Ovr
```

全表（两行）：

```
cfg-codex-deepseek,open,baseline,3,3,0.3333333333333333,0.0,1.3943554533333333,—,—,0.0,1.0,—,—,,,,,,,,,,
cfg-codex-deepseek,strict,protocol,3,3,0.3333333333333333,0.0,1.42652136,—,—,—,—,—,—,,,,,,,,,,
```

四条轴（`table_main.axes.json`）：`set_version = p1.0.0` / `reference_version = r1.0.23` /
`protocol_version = geneprotocol_v1@d6fbcaa08302`（裸臂记 `geneprotocol_v1@none`）/ `channel = public`；
`mixed_axes = {}`。**空 ≠ 0**：`—` = 这一格量到了但不适用/不可得，空白 = 这批 run 里没有该阶段的样本
（本批只有 S1–S3，S4–S8 那十列因此是空的）。

### 5.3 **走不通的那一步（本轮要找的东西）**

**结算与入库这两步，外部单机用户今天过不去。** 挡路的是**两个互相不一致的写死路径**：

```
ops/score_runs.py:45      RUNS_IN = Path("/data/shared/genebench/runs_in")     ← 写死，没有 CLI 覆盖
ops/results_db.py         protocol_by_run(): base = cfg.GENEBENCH_ROOT / "runs_in"  ← 跟 GENEBENCH_ROOT
```

**在发布方机器上这两条是同一个路径，所以这处分叉内部永远看不见。** 实测三条路径全部走不通：

* `score_runs.py --no-pull` → `FileNotFoundError: /data/shared/genebench/runs_in/d2_e2e`；
* `score_runs.py --remote /data/d2_e2e/runs/runs` → `拉取失败：Host key verification failed`
  —— 因为 `pull()` 里 `F02 = "ljn@192.168.1.219"` 也是写死的，**外部用户敲 `--remote` 会让 rsync 去连发布方的执行面**；
* 只把 `score_runs` 那一头接上（软链到 `/data/shared/genebench/runs_in/d2_e2e`）→ 结算通了，
  但 `results_db ingest` 报 `协议轴反算不出（runs_in/d2_e2e 里 GQ 臂的注入摘要 = 无）`
  —— 它看的是**另一个根**。

**所以 §5.2 那张表是加了两条软链才出出来的**：

```sh
ln -sfn <你的 run 根> /data/shared/genebench/runs_in/<batch>     # 给 score_runs
ln -sfn <你的 run 根> "$GENEBENCH_ROOT"/runs_in/<batch>          # 给 results_db
```

**这一点不含糊**：链路本身是通的、判据是真的，但**「只凭 README」今天到这一步会停住**。
修法与 `ops/run_joblist.py:79` 同源（`cfg.GENEBENCH_ROOT / …`），并给 `--runs-root` 一个显式入口。
本轮**没有修** —— `ops/score_runs.py` 不在本轮四张卡任何一张的可改路径内。已登记 **N-770**。
同一类的还有卡 B2 早就指出的 `ops/run_controls.py:48/49/53/54`（N-757 / N-758）——
本卡是靠显式给 `--ref-tasks` / `--gateway-log` 绕过去的，那两个参数**公开通道本来就必须显式给**（手册 §5.7）。

### 5.4 还有五处「只有外部用户会撞」的

* **N-771** 两个大附件**没有落位命令**，而 `provider/` 还要改名成 `qlib_provider/`（映射见 §4 末尾）。
* **N-772** `push_guard.py` / `push_bundle_to_f02.sh` 不带通道：公开 bundle 过门时报
  「冻结引用已过期 → **重新导出，不要改通行证**」，**而重新导出解决不了** —— 真因是 `GENEBENCH_CHANNEL` 没给。
  实测：加上之后同样三个 bundle 三条全绿。
* **N-773** 手册 §1.2 让人从 `bootstrap.pypa.io` 引导 pip，那个域名在这台机器上**挂住 11 分钟 0 字节**
  （与 Y-03 记的 pypi.org 同症状），而 §1.2 的镜像出路只覆盖了 pypi.org。
* **N-774** `python3 -m venv $GB/env` 建出一个**没有 pip 的半成品并留下 `bin/python`** ——
  「文件在不在」这个最自然的判据为真而实际不可用。判 venv 可用要用 `import fastapi`。
* **N-775** `ops/guard_modes.py --harden` 的 `EXTERNAL_ROOTS` 写死 `/data/shared/genebench`、不存在就跳过，
  于是在外部机器上**根本没收紧 `$GENEBENCH_ROOT`**（实测输出「收紧 0 个条目 / 敏感根权限合规（**1 个根**）」，
  那 1 个根是仓库），而 README §2.1 说它收紧 `$GB`。本卡是手工 `chmod -R go-rwx "$GB"` 补上的。
* **N-776** 边车镜像 `python:3.11-alpine` 来自 docker.io（写死在 `runner/c41/runner_core.py:163`），
  **「所需外网」表里一条都没提**；f02 上碰巧有，外部用户第一次真跑之前要 `docker pull`，
  而失败时刻在**真跑开始之后** —— 最贵的位置。

---

## 6. 顺带量到的（不进已知限制表的计数，但值得知道）

* **超时终止后任务容器不被回收**：`s1-cor-01.strict` 撞 1500 秒墙钟闸之后，边车被拆掉了，
  **任务容器还 `Up` 着**（本卡收尾时它已经 `Up 2 小时`，已由本卡删掉）。
  f02 上另有两个更早的同形遗留（`Up 31 小时` / `Up 2 天`），**不是本卡的，没动**。
* **`git bundle` 默认不带 HEAD**：`git bundle create <f> main` 出来的包，`git clone <f>` 会报
  「remote HEAD refers to nonexistent ref」并**建出一个空仓库**（`master` 分支、无提交）——
  要 `git clone -b main <f>`。本卡第一遍就掉进去了；这只影响内部把树搬来搬去，外部用户走的是 `git clone <URL>`。
* **重出发布清单之后有三条真红**（N-779 / N-780 / N-781），逐条与修法写在
  `ops/tickets.md` 本轮那一节。前两条是本卡按任务书重出 `RELEASE_MANIFEST.json` 的**直接后果**
  （`release_attachments` 从 `n=2 / uploaded=2` 变成 `n=3 / uploaded=2`，两道双向门翻面）——
  **不是回归，是状态真的变了**，落点分别是 `ops/reports/publish_report.md` 与 `ops/test_pack_release.py`，
  **两个都不在本轮四张卡任何一张的可改路径内**。第三条是卡 V2 留下的，**本卡落地任何东西之前就已经红**。
* **`ops/mk_release_manifest.py --check` 在本轮开始时是红的**（`release_attachments` 判据变了）——
  那是卡 B2 登记第三个附件之后、清单还没重出的正常状态，本卡重出后退 0。

---

## 7. 一条要跟着改的口径（留给下一张文档卡）

README §2.3 与手册 §1.1 / §1.3 现在同源写着「**Linux 上 2026-09-11 已端到端跑通 /
macOS arm64 上 2026-09-13 卡在建 harness 镜像**」。**这句话今天仍然成立**（两处说的都是那两次实测），
但本轮多了一次更强的实证：**2026-09-13，在一台没有本项目任何遗留物的 Linux 树上，
只凭仓库 + 三个附件，从 clone 走到十九列表**（唯一的例外是 §5.3 那两条软链）。
要不要把这一句加进去、怎么措辞，归文档卡；`ops/test_docs_consistency.py` 的规矩是
**两处一起改**、旧版原文用「」引起来。本卡**没有改 README 与手册**（不在可改路径内）。

---

## 8. 证据路径

| 是什么 | 在哪 |
| --- | --- |
| 端到端全套日志（setup / build / gw / export / run / score×3 / wrap） | `$GB/scratch/D2/evidence/*.log` |
| `/healthz` 原文 | `$GB/scratch/D2/evidence/healthz.json` |
| 六个 run 的 `run.json` / `inject.json` / `compose.yml` / `llm_log.jsonl` | `$GB/scratch/D2/evidence/llm_log/<run_id>/` |
| 结算记录与主表（CSV / MD / axes） | `$GB/scratch/D2/evidence/{records.json,table_main.csv,table_main.md,table_main.axes.json}` |
| 新旧基座的 `pip freeze --all` | `$GB/scratch/D2/evidence/pipfreeze_{new,old}.txt` |
| 复现脚本（七支，可整段照抄） | `$GB/scratch/D2/f02_{setup,setup2,setup3,setup4,build,gw,export,run,score,score2,score3,wrap}.sh` |
| f02 上留下的树（实测 5.8 GB —— 三个附件的解包件与 run 目录占大头，随时可 `rm -rf`） | `f02:/data/d2_e2e`（网关已停、`/data/shared/genebench` 那条绕法已清掉） |
| 本卡新建的两个镜像 tag（留作证据） | `gb-base:d2e2e-20260913` / `gb-cx-u:d2e2e-20260913` |
| 用户的验收报告 | 用户本机 `~/GeneBench-validation-20260913/VALIDATION_REPORT.md` |
