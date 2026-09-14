# 外部演练 v2 —— 只凭发布包 + 手册，在一台干净机器上走完七步

**做法**：扮演一个**只拿到发布包**的外部运行者，只读
`README.md` / `docs/OPERATOR_MANUAL.md` / `harnesses/README.md` / `RELEASE_MANIFEST.json`，
**不读 `ops/HANDOFF.md`**（那是内部交接），不读任何施工代理的输出。
每一处走不通或有歧义的地方记一条 finding，**做完之后回过头修文档**（只改文档，不改判据）。

**日期**：2026-09-11。**演练目录**：执行面 `/data/genebench_runner/rehearsal_v2/`
（一个全新的目录树：自己的解释器环境、自己的 `GENEBENCH_ROOT`、自己的网关、自己的 run 根）。
**上一次**：`ops/reports/rehearsal_v1.md`（2026-09-08，五件事成了三件半，**部署那一件一步都没走成**）。

> **一句话结论**：**七步全部走通，形态 ① 第一次端到端跑成。**
> 上一次卡死的那一件（形态 ① 单机双容器）今天从解包一路走到出表 ——
> 挡路的两件都已拆掉：防火墙那条由机器主人放行了，网关对答案面的 import 由
> `genetask/s8_contract.py` 摘干净了。
> **代价是 17 条 findings**，其中 **6 条 block**：四条在「怎么把解释器环境建出来」上
> （发布包里根本没有依赖清单），一条在「本机那道答案面扫描会删掉你自己的答案面」上，
> 一条是**代码层的静默走错**（`--provider-root` 在真跑路径上被忽略，公开通道真跑喂的是私有 provider）。

---

## 0. findings 表（修前 → 修后）

严重度：**block** = 外部运行者按文档走不下去 / 会做出错的事；
**major** = 走得下去但会踩坑、或读到与事实不符的话；**minor** = 别扭，登记不修。

| # | where（文件:节） | what | 严重度 | 修后 |
| --- | --- | --- | --- | --- |
| Y-01 | 仓库根 / 手册 §1.2 | **发布包里没有依赖清单**（没有 `requirements.txt`、没有 `pyproject.toml`），手册前置表只写「Python 3.10（`$GB/env`，独立环境）」。装哪些包**一个字都没有** | **block** | 手册 §1.2 新增「『独立环境』怎么建出来」：六个包的名字逐个列出（`fastapi uvicorn pandas pyarrow duckdb pyyaml`），并注明这一行是演练里一个个试出来的 |
| Y-02 | 手册 §1.2 | 执行面那台机器上 `python3 -m venv` 与 `python3 -m pip` **两个都没有**（实测 Ubuntu 24.04 + Python 3.12：`ensurepip is not available` / `No module named pip`），而 `apt install python3.12-venv` 要 root —— 而这一节的前提正是「执行面不需要 sudo」 | **block** | §1.2 给出**不用 root** 的三条命令：`get-pip.py --target` 引导 pip → `pip install --target` 装到自己的目录 → `PYTHONPATH` 指过去 |
| Y-03 | 手册 §1.2 | 直连 `pypi.org` 在这台机器上**挂住**：40 分钟 0 字节，连接停在 `CLOSE-WAIT`（走 IPv6 到 Fastly）。换国内镜像后 **14 秒**装完。`--progress-bar off` 让它连进度条都没有 —— 现场表现是死机，不是报错 | **block** | §1.2 写明要带 `-i <镜像>`，并把「不是慢、是看起来像死机」这句话写进去 |
| Y-04 | `runner/inject.py::h11_source_dir()` ↔ 发布包 | 注入器要 `import h11`（它把 h11 复制进 run 目录给边车用），先找 exec 树的 `vendor/h11`，找不到才用运行环境里的 —— 而 **`vendor/` 不在仓库里**（`git ls-files vendor` 为空），发布包里没有它。外部运行者真跑第一条命令就 `ModuleNotFoundError: No module named 'h11'` | **block** | §1.2 写明「执行面也要这个环境」，真跑命令要带 `PYTHONPATH=<site>`（`pip install` 顺带装上了 h11）。**vendor 进不进仓库是一次裁定**，已登记 |
| Y-05 | 手册 §1.3 末尾（答案面扫描 timer） | 手册说「单机形态下这个 timer 要装在同一台机器上」，**没说 `--root` 该指到哪一层**。而 `reference` 正是它的「答案面目录名」之一、**命中即整棵删**。单机形态下答案面与执行面同机 —— 照字面做就会删掉自己的答案面 | **block** | §1.3 加告示：`--root` 只指执行面那棵（本项目是 `/data/genebench_runner`），千万别指到包含 `reference/` 的那一层 |
| Y-06 | 发布包自身 | 包里有**两份带合成 gold 串的测试文件**（`ops/test_answer_plane_guard.py`、`ops/test_inject.py`）。落在扫描根里会被当场删掉，unit 进 failed 并置闩。实测：剔除答案面之后的包 1313 个文件里**命中 2 条**，就是这两份 | **major** | §1.3 写明「把它们放在扫描根之外」。根治是把串改成运行时拼接（扫描器按设计不命中），已登记 |
| Y-07 | 手册 §1.3 的 `ufw allow` ↔ §1.4 (c) 的「端口显式错开」 | 那条放行规则**把端口写死成 18080**（`to any port 18080`），而 §1.4 (c) 又教人「端口显式错开，别和生产网关抢」。两条一起照做，容器就打不到网关 —— 而现场表现是超时，不是拒绝 | **major** | §1.3 加告示：单机形态**就绑 18080**（本机上没有别的东西占它），要错开得让机器主人按新端口再放行一条 |
| Y-08 | 手册 §1.3 的探针结论 | 「容器 → 本机宿主网关」这一行**取决于容器在哪个网段**。用 `docker run`（默认 bridge，172.17/16）探会**超时**，而那不是形态 ① 的结论 —— 默认 bridge 不在 `ufw allow from 172.31.240.0/22` 里 | **major** | §1.3 换成**三行对照**（放行网段→本机 200 / 放行网段→别的主机 200 / 默认 bridge→本机 超时），并写明第三行才是判别力所在 |
| Y-09 | `ops/run_f02_a1.py`（代码层，不是文档） | `--provider-root` **只有 `--dry` 用它**；真跑那条路径读模块常量 `PROVIDER`（写死私有 provider 的绝对路径）。`main()` 里 `global RUN_ROOT, RESULTS` 把那两个按参数改写，**唯独 provider 没有**。后果：**公开通道的真跑喂给容器的是私有 provider 树**，而 P2 照样绿（跑批不设 `GENEBENCH_CHANNEL` 时期望值也是私有的，两头一致）。证据：`m6_public` 的 run 目录里 `work/provider/features/` 下有 `bj*`（北交所）代码，公开 provider 只有沪深 | **block** | **文档修不了**，已登记（建议当挡发布）。手册 §5.6 加告示写明这件事与它的表现。本次演练**改了自己那棵树的这一行常量**，所以这 6 个 run 用的是公开 provider |
| Y-10 | 手册 §5.6 单题方式 | 那条可粘贴的命令缺三个环境变量：`GENEBENCH_CHANNEL`（少了它 P2 拿私有冻结值核公开树，当场红）、`GENEBENCH_GATEWAY_ADDR`（形态 ① 要打本机网关）、`PYTHONPATH`（Y-04） | **major** | §5.6 加三行 |
| Y-11 | 手册 §8.1「四条版本轴怎么查」 | 只给了**两条**（两条冻结轴）。协议轴在包里查不到（`ops/manifests/v1.0-smoke.json` 的 `protocol_version` 是 `null`），通道轴一个字没提 | **major** | §8.1 补：协议轴是**逐 run** 的读数（从结果库查）、通道轴是环境变量；并补上「解包之后跑一次 `mk_release_manifest.py --check`」与四个退出码的含义 |
| Y-12 | 手册 §0 / README | **没有「最低 RAM / 磁盘 / docker 版本」，也没有包体** —— 拿到包的人第一个问题就是「我这台机器够不够、要下多少」 | **block** | 新增手册 §0.0 与 README §1.5：逐行给数**并给出处**；包体逐部分列出；gold 只发子集这件事连同它的限制一起写明 |
| Y-13 | 手册 §2.4 | secrets 只说了位置与「不要 `cat` 它」。**没有格式样例**、没有权限要求的判据、没有「怎么验证容器里确实看不见」 | **major** | 新增 §2.4.1：位置/权限/格式 + 占位值样例 + 三段注入链 + 一条可粘贴的验证命令（读真跑留下的 `compose.yml`）与实测输出 |
| Y-14 | 手册 §9 ↔ §5.5（**两节自相矛盾**） | §9 给了并发档位（S7 1 / S4 ≤2 / 其余 ≤3），而 §5.5 写着「并发数固定是 1 …… 这套系统里**没有 >1 的合法值**」。本次演练按 §9 并发 2 跑了一次，**两条都炸了**：`subnets.allocate()` 的 TOCTOU 竞态（`invalid pool request: Pool overlaps`）、以及另一个失败 run 的清理把 `run_root` 拿走（`[P0] run_root 不可写`） | **major** | 见下文 §5 的实测记录。**两节的口径要统一**，落点 `docs/OPERATOR_MANUAL.md` §9 是卡 B 写的，已登记；演练本身改回串行 |
| Y-15 | `genebench_config.py::GATEWAY_HOST` / `ops/run_joblist.py::gateway_addr()` | 端口有环境变量（`GENEBENCH_GATEWAY_PORT`），**主机名没有**。而 `run_joblist` 渲染给容器的网关地址读的正是这个常量、也没有覆盖入口 —— 于是在跨机 fleet 上**没法用清单方式演练形态 ①** | **minor** | 登记不修（手册 §1.3 本来就写「改常量」）。本次演练因此走 §5.6 单题方式 |
| Y-16 | `harnesses/build.sh` | 缓存命中时它 **0.2 秒**打印「构建完成」，digest 与旧镜像逐字相同 —— 「这一步要哪些外网、离线能不能建」在有缓存的机器上**量不出来**；脚本没有 `--no-cache` 透传 | **minor** | 登记不修。本报告另跑一次 `docker build --no-cache` 把这件事量了（§4） |
| Y-17 | 演练第 ⑦ 步「导出结果」 | **走演练的那一刻**（2026-09-11 11:0x UTC）裁定 ⑮ 的 `genebench export` / `merge` 还不存在，包里只有 `ops/results_db.py query` 与 `ops/mk_tables.py` —— 导出的东西既没有机器标识、也没有四轴一致性校验 | ~~major~~ **本卡收口时已闭** | **不是本卡修的**：卡 Y2 在 09:31 UTC 落地了 `ops/genebench_cli.py`（提交 `425a3a8` 及其之前）。收口时用真家伙把第 ⑦ 步**重走了一遍**，见 §6.1。**这一行原样留着**，因为「演练当时确实没有」与「现在有了」是两件事 |

**修了 11 条**（Y-01…Y-03、Y-05…Y-08、Y-10…Y-13 里的文档部分），
**登记不修 / 交给别的卡 6 条**（Y-04 的 vendor 归属、Y-09、Y-14、Y-15、Y-16、Y-17）——
逐条在 `ops/tickets_inbox/Y1-rehearsal.md`。

---

## 1. 七步逐步

| 步 | 做了什么 | 结果 | 耗时 |
| --- | --- | --- | --- |
| ① 解包 | `git archive HEAD` → 剔除答案面 → 执行面那道门扫一遍 → 打包送到干净目录 → 解开 | 1683 → **1311 个文件**；`answer_plane_guard.scan` **0 命中**（剔除前 2 命中，见 Y-06）；tar.gz **4,155,177 字节** | 约 3 分钟 |
| ② 校验四轴 | 从**解出来的那棵树**跑（不是工作树） | 任务集 **1.0.15**（根 `622f720c…`）/ 参考面 **r1.0.22**（根 `c61b0667…`）；`mk_release_manifest.py --check` rc=**3**（只是两份手写件的 sha 漂了）；协议轴与通道轴**查不到**→ Y-11 | 约 1 分钟 |
| ③ 起网关 | **形态 ①**：网关起在执行面这台机器上，绑本机 LAN | `/healthz` **5 秒**回 200；`channel=public`、`bind=192.168.1.219:18080`、`tables_dir` 指向演练自己的树、`exposed_datasets` 五个 | 5 秒（对照：f01 的生产网关 40–70 秒，大头是 `ExecStartPre` 扫全树） |
| ④ 建 harness 镜像 | `sh harnesses/build.sh codex --dry-run` → 真建（换 tag，不碰被 `--digest` 钉住的 `gb-cx-u:r1`） | 缓存命中 **0.2 秒**、digest 与旧镜像相同（Y-16）；另跑 `--no-cache` 一次：**41.4 秒**，要 `registry.npmjs.org` | 约 1 分钟 |
| ⑤ 落本机 secrets | 按 §2.4.1 核格式/权限/注入链 | `~/.config/genebench/secrets.env` 0600；`compose.yml` 里边车是 `${GENEBENCH_MODEL_API_KEY}` **引用**、任务容器是占位串 | 秒级 |
| ⑥ 跑 3 题双臂 | `s1-cor-01` / `s2-cor-01` / `s3-cor-01`，公开通道，网关是**本机**那一个 | 见 §5 | 见 §5 |
| ⑦ 结算 + 导出 | `score_runs` → `results_db ingest` → `mk_tables` | 见 §6 | 见 §6 |

---

## 2. 所需外网（⑭ 要求逐条记录）

| 哪一步 | 域名 | 干什么 | 离线能不能做 |
| --- | --- | --- | --- |
| ② 建解释器环境 | `bootstrap.pypa.io` | 引导 pip（机器上没有 pip / venv） | **不能**，除非机器上已经有 pip，或者你有 root 能 `apt install python3-pip` |
| ② 建解释器环境 | `pypi.org` + `files.pythonhosted.org`，或镜像 `pypi.tuna.tsinghua.edu.cn` | 装六个包 | **不能**，除非预先做好 wheel 包随包分发 |
| ④ 建 harness 镜像 | `registry.npmjs.org` | `npm install -g "@openai/codex@0.153.2"` | **不能** |
| ④ 建 harness 镜像 | **`docker.io` 不需要**（在本项目的网络里也不可达） | 基座 `gb-base:bookworm-r1` **必须本机已有**，`build.sh` 在构建前显式核这一条 | 基座在本机 = 这一步离线可做 |
| ⑥ 真跑 | 出向白名单里的模型 API 域名（本次是 DeepSeek） | 模型调用 | **不能** |

顺带实测（**不在任何一步的必需路径上**，只是回答「这台机器出得了网吗」）：
`github.com` **200**。四个域名的连通性探测原样留在 `ops/reports/i_rehearsal_v2/`。

---

## 3. 形态 ①：单机双容器（⑧ 之后的收口）

**结论：通了。** 逐步证据见 §1 的 ③⑥⑦ 行与 §5。这里只记那一件「不试就不知道」的事。

**容器 → 本机宿主网关**（同一时刻、同一台机器，2026-09-11）：

```
容器（放行网段 172.31.243.0/24） → 本机宿主 192.168.1.219:18080   ✅ 200 public
容器（放行网段）                  → 别的主机  192.168.1.48:18080   ✅ 200（对照）
容器（默认 bridge 172.17/16）     → 本机宿主 192.168.1.219:18080   ❌ 超时
```

第三行是**判别力**：那条 `ufw allow from 172.31.240.0/22` 只放行注入器分配的任务网段
（`runner/c41/subnets.py::POOL = 172.31.240.0/20`），默认 bridge 不在里面。
**拿默认 bridge 的容器去探形态 ①，会得到「不通」这个错误结论**（本演练第一次就是这么探的）。

**三处常量**（手册 §1.3 那张表）实际只改了一处：`genebench_config.py::GATEWAY_HOST`。
另外两处今天有环境变量入口（`GENEBENCH_GATEWAY_ADDR`），不必改代码。
`GATEWAY_HOST` **没有**环境变量入口（Y-15）。

**网关与答案面**：本演练在执行面上起的网关**没有**带任何答案面 ——
`gateway/**` 今天一条 `import reference` 都没有（`genetask/s8_contract.py` 之后）。
这正是 ⑧ 要拆的那堵墙，拆完之后形态 ① 的「起网关」这一步才不与红线撞车。

---

## 4. 镜像构建：缓存把「所需外网」藏起来了

```
sh harnesses/build.sh codex --tag gb-cx-u:rehearsal_v2
  → Step 2/2 ... ---> Using cache        0.2 秒，digest 961e3878b28f…（与 gb-cx-u:r1 相同）

docker build --no-cache -t gb-cx-u:rh2_nocache harnesses/codex
  → 41.43 秒，digest b61ca3d09216…（与上面**不同** —— npm 装出来的东西不是逐字节可复现的）
```

两条一起读才有信息量：
**① 这一步真正要的外网只有 `registry.npmjs.org`**（`docker.io` 不需要，基座必须本机已有）；
**② 重建同一个 tag 拿不到同一个 digest** —— 所以 `build.sh` 默认拒绝重打已存在的 tag 是对的
（重打会让所有已出集 bundle 的 `--digest` 对不上，而对不上的表现可能是「核对绿而跑的是另一个镜像」）。

---

## 5. 真跑：3 题双臂（⑥）

**6 个 run 全部真跑完**（`s1-cor-01` / `s2-cor-01` / `s3-cor-01` × strict/open，公开通道，
网关是执行面**本机**那一个）。**真 API 共 500 次**（`ops/api_usage.py` 前后差 3945 → 4445）。

| run_id | 结果 | 墙钟 | 调用 | 产物 |
| --- | --- | --- | --- | --- |
| `s1-cor-01.strict.cfg-codex-deepseek.r01` | budget_exhausted（撞 100 次调用闸） | 1426.9 s | 101 | 无 |
| `s1-cor-01.open.cfg-codex-deepseek.r01` | budget_exhausted | 874.4 s | 101 | 无 |
| `s2-cor-01.strict.cfg-codex-deepseek.r02` | ok / valid / l3 `align:False` | 1272.4 s | 81 | 805 B |
| `s2-cor-01.open.cfg-codex-deepseek.r02` | ok / valid / l3 `align:False` | 1385.6 s | 64 | 798 B |
| `s3-cor-01.strict.cfg-codex-deepseek.r01` | timeout（1800 s 墙钟） | 1813.0 s | 101 | 1092 B |
| `s3-cor-01.open.cfg-codex-deepseek.r01` | violation / invalid / gate `declared_reads` | 460.2 s | 55 | 1170 B |

**这一栏不是能力读数**，是**构造验收**：它证明的是「这条链路在一台机器上能把一次真运行变成一行主表」。
（`s2` 两臂的 `--seq` 是 2 —— 见下面「并发那一次」。）

### 5.1 并发 2 那一次：两条都炸了（Y-14）

手册 §9 给的并发档位是「S4 ≤2 / 其余 ≤3」，§5.5 却写着「并发数固定是 1 …… 没有 >1 的合法值」。
按 §9 把 `s2` 与 `s3` 并发 2 跑了一次，**两条都炸**：

```
s2-cor-01.strict  ERROR  边车起不来：failed to create network …_gb_task:
                         invalid pool request: Pool overlaps with other one on this address space
s3-cor-01.strict  ERROR  [P0] run_root 不可写：…/rehearsal_v2/runs
                         （No such file or directory: …/runs/.inject_write_probe）
```

第一条是 `runner/c41/subnets.py::allocate()` 的 **TOCTOU 竞态** ——
它拿 `docker network inspect` 的实时结果判否，两个进程同时判、同时建就会撞
（它的 docstring 只说「两臂并发会抢同一个网段」，修法是动态分配；**跨进程那一层没有锁**）。
第二条更隐蔽：`s2` 那一侧失败之后的清理把 `run_root` 拿走了，`s3` 恰好在那一瞬间探写。
**两条都表现为「某一臂莫名其妙没跑」，不是一条显眼的报错。**

重跑时 `s2` 两臂的 run 目录已经建出来了，注入器拒绝覆盖（`run dir 已存在 …… 不覆盖`），
按手册 §5.6「重跑同一个目标要换 `--seq`」改成 `--seq 2` —— 这一条手册是对的，照做就过。

**结论：在 `allocate()` 拿到跨进程锁之前，§9 那张并发表不该被当成可用的档位。** 已登记。

### 5.2 顺带量到的两件

* **网关访问日志只有 3 行**（6 个 run 合计）。出向日志里能看到任务容器打 `gateway` 5 次、
  打宿主 `192.168.1.219:18080` 1 次，其余出站（`ab.chatgpt.com` / `chatgpt.com` / `api.github.com`
  —— codex 自己的遥测）被白名单挡掉。**链路是通的，agent 用得少**。
* **`s1` 两臂都撞了 100 次调用闸**（默认档 100 次 / 6M tokens）。`s1-cor-01` 在
  `m6_public`（私有 provider）上只用了 29 / 26 次 —— 同一道题、同一个模型、同一个镜像，
  换成公开 provider 之后 101 / 101。**这正是 Y-09 那条为什么要紧**：
  provider 树喂错了，表上看到的是「能力差异」。

---

## 6. 结算与导出（⑦）

```sh
# 结算（公开通道要显式给题集根与网关日志；网关日志在**执行面那台机器**上，先取回来）
scp ljn@<执行面>:/data/genebench_runner/rehearsal_v2/gbroot/logs/gateway_access_public.jsonl $GB/scratch/Y1/
GENEBENCH_CHANNEL=public $PY ops/score_runs.py --batch i_rehearsal_v2 \
    --remote /data/genebench_runner/rehearsal_v2/runs/runs \
    --ref-tasks $GB/reference/tasks/public/v1.0-smoke-public \
    --gateway-log $GB/scratch/Y1/gateway_access_public.jsonl
# 入库
$PY ops/results_db.py ingest --batch i_rehearsal_v2 --channel public
# 导出（**演练当时**只有这两条，见 Y-17；收口时用 genebench export 重走了一遍，见 §6.1）
$PY ops/results_db.py query --filter batch=i_rehearsal_v2 \
    --fields run_id,set_version,reference_version,protocol_version,channel
$PY ops/mk_tables.py --table main --format md --filter batch=i_rehearsal_v2 --out ops/reports/i_rehearsal_v2
```

结算 **6 个 run / 问题 0**；入库 `added=6 / duplicate=0 / n_total=132`，
轴是 **1.0.15 / r1.0.22 / public**。主表两行（`ops/reports/i_rehearsal_v2/table_main.md`）：

| config_id | arm | n_tasks | n_runs | SR | P@1 | $ | Align | Adj |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cfg-codex-deepseek | open | 3 | 3 | 0.666667 | 0 | 1.07355 | 0.666667 | 1 |
| cfg-codex-deepseek | strict | 3 | 3 | 0.333333 | 0 | 2.06749 | 1 | 1 |

**第 ⑦ 步当时缺的是什么**（Y-17，**收口时已闭，见 §6.1**）：走演练那一刻，裁定 ⑮ 要的 `genebench export` / `genebench merge` 还不存在。
上面那两条命令能把结果**倒出来**，但倒出来的东西
**没有机器标识**（哪台机器跑的）、**也没有「合并前先校四轴一致」这道闸**。
两台机器各跑一半再合并这件事，今天只能靠人看 `results_db versions` 的输出自己判。

**结算这一步本身没有踩到坑** —— 公开通道那两个必须显式给的参数（`--ref-tasks` / `--gateway-log`）
手册 §5.7 与 `run_joblist.score_cmd` 的 docstring 都写清了为什么（少给的后果是
「拿私有 gold 判分、在私有日志里找不到自己的请求」，而那会静默塌成 unobservable）。
唯一要补一句的是：**形态 ① 下网关日志在执行面那台机器上**，结算前要先取回来。


### 6.1 收口时用 `genebench export` 重走了一遍第 ⑦ 步

演练跑完之后（09:31 UTC，卡 Y2 提交 `425a3a8`）裁定 ⑮ ⑰ 的入口落地了。
收口时拿它把第 ⑦ 步重走一遍，Y-17 那条因此闭合：

```sh
$PY ops/genebench_cli.py axes                       # ⑰ 版本锁自检
$PY ops/genebench_cli.py export --out <落点> --filter batch=i_rehearsal_v2 --label "…"
```

* `axes`：四条轴**现值**与 `RELEASE_MANIFEST.json` 逐条对上
  （`1.0.15` / `622f720c…` / `r1.0.22` / `c61b0667…`），退 0 =「入口不会拦」。
* `export`：出 `genebench-results-finance01-e3887dfa-20260911T123652Z.tar.gz`
  （旁边一个同名 `.sha256`），**6 条记录、带机器标识 `finance01-e3887dfa`
  （指纹来源 `/etc/machine-id`）、带轴 `1.0.15 / r1.0.22`**。
  这正是 Y-17 里说「缺的那两件」——今天不缺了。

结果包落在 `$GB/scratch/Y1/resultpack/`，**没有进仓库**（它是一次演练的读数，不是发布件）。

---

## 7. 与 v1 的差别

| | v1（2026-09-08） | v2（2026-09-11） |
| --- | --- | --- |
| 形态 ① 部署 | **一步都没走成**（要 root 的两条前置） | **七步全通** |
| 起网关 | 没走到 | 5 秒，`channel=public` |
| 真跑 | 走的是形态 ② | **形态 ①：容器与网关同机** |
| findings | 20 条（修 12） | 17 条（修 11） |
| 卡住的那一件 | 防火墙 + 网关 import 答案面 | **都拆了**；今天卡的是「怎么把 python 环境建出来」 |

**v1 的 20 条里有几条今天仍然成立**（本次没有重新验证、也没有重新计数）：
`integrations/` 那几条接入侧的（F-07…F-11）、`s2-ops-01` 题面与采集侧允许集的冲突（F-17 / F-19）、
`s2-ops-01` 的 gold 面板缺件（F-20）。它们不在本次七步的路径上。
