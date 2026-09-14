# 外部演练 v1 —— 只凭仓库文档做五件事

**做法**：扮演一个**只拿到这个仓库**的外部运行者，只读
`README.md` / `docs/OPERATOR_MANUAL.md` / `harnesses/README.md` / `integrations/README.md` /
`integrations/P2_CONTRACT.md` / `VERSIONS.md` / `ops/reports/known_limits_v1.md` /
`RELEASE_MANIFEST.json`，**不读 `ops/HANDOFF.md`**（那是内部交接），不读任何施工代理的输出。
每一处走不通或有歧义的地方记一条 finding，做完之后**回过头修文档**。

**日期**：2026-09-08。**演练目录**：f02 `/data/genebench_runner/rehearsal_v1/`。
**用时**：约 4 小时（逐段见 §7）。

> **一句话结论**：五件事**成了三件半**。
> 加 harness（§3）与跑批出表（§4）从文档走到底，一步没卡；
> 接一个新系统（§2）走通了，但路上撞了四处只有真做才会发现的文档缺口；
> 单机部署（§1）**在文档之外的一条硬前置上停住**（要 root），一步都没走成；
> 适配赛道（§5）**没有可读的入口**，而且发现那条「不许推执行面」的禁令**没有守门**。

---

## 0. findings 表（修前 → 修后）

严重度：**block** = 外部运行者按文档走不下去 / 会做出错的事；
**major** = 走得下去但会踩坑、或读到与事实不符的话；**minor** = 别扭，登记不修。

| # | where（文件:节） | what | 严重度 | 修后 |
| --- | --- | --- | --- | --- |
| F-01 | `docs/OPERATOR_MANUAL.md` §1.4 | 建数据面只有两条路：拿冻结包（今天走不通）与从零重建（约 4 小时 15 分）。**没有「引用一份已经建好的快照」这一条** —— 而形态 ② 转形态 ①、或同组织第二台机器的运行者要的正是这一条 | **block** | §1.4 末尾加了 (c) 一节：把量到的事实写清（网关读的是 `tables_dir`，`v1/tables` 1.5 GB、`public_v1/tables` 447 MB，整棵 `public_v1` 16 GB；provider 树按 `PROVIDER_SHA256_ROOT` 核根，换通道对不上），**并明说这条路没人端到端走过、不写成步骤**。票据记「缺的是一次实跑，不是一段文字」 |
| F-02 | `docs/OPERATOR_MANUAL.md` §1.3 / `README.md` §2.3 | 形态 ① 的两条前置（`ufw allow`、答案面扫描 timer）**都要机器主人执行**，但两处都只把这件事写在正文中段，读者往往读到一半才发现自己根本走不下去 | **block** | §1.3 开头加告示框「**先判断你有没有 root**，两条都拿不到就回 §1.1 选形态 ②，不要在这一节耗时间」；README §2.3 同步加一句 |
| F-03 | `docs/OPERATOR_MANUAL.md` §1.3 | 探针结论只有「容器 → 宿主 **LAN 地址**」一行，读者很容易以为「换个绑定地址就绕过去了」 | **major** | 本卡把探针扩到三种「宿主自己的显式地址」，**全部超时**，结论写进 §1.3：LAN `192.168.1.219`、docker0 `172.17.0.1`、自建网自己的网关 `172.31.244.1` 三种都不通，同一容器同一时刻打 f01 的 `192.168.1.48:18080` 是通的。**换绑定地址绕不过去** |
| F-04 | `harnesses/README.md` §1.1 / §3.2 | **从没说 `docker build` 的上下文是哪个目录。** 于是「能不能往 `harnesses/<id>/` 里放自己的驱动脚本并 `COPY` 进镜像」这个问题，只能去读 `build.sh` 源码才知道 | **major** | §1.1 加一段：构建上下文就是 `harnesses/<id>/` 本身（`build.sh` 跑的是 `docker build -t <tag> harnesses/<id>`），**四件文件是必需不是全部**，多放的文件不会红 |
| F-05 | `harnesses/README.md` §2.1 | 产物 schema 顶层 `required` 里有 **`seed`**，而 §2.1 那张「容器里能看见什么」的表里**没有 `GENEBENCH_SEED`** —— agent 没有任何有据可依的办法知道 seed | **major** | 实测确认容器里确实没有这个变量（`echo-min` 把每个变量有没有逐个打印出来）。§2.1 加告示框：今天唯一的来源是 `GENEBENCH_RUN_ID` 尾巴的 `r01`；**别猜 0**，写错的 seed 不会让任何东西变红。要不要注入 `GENEBENCH_SEED` 已登记票据 |
| F-06 | `integrations/README.md` §3.5 / §3.7 | 三处排查条目写「**看 run dir 下的容器日志 / stdout/stderr**」，而那个文件**不存在**：真跑收尾 `down -v`，`log/` 下只剩 `egress.jsonl` 与 `llm_log.jsonl` | **major** | 两处就地订正为「`<run_dir>/run.json` 的 `stdout_tail` / `stderr_tail`（各 2000 字符）」。（同一件事 `docs/OPERATOR_MANUAL.md` §7.3 与 `harnesses/README.md` §4 本来就写对了 —— 三份文档里只有 `integrations/` 那份是错的） |
| F-07 | `integrations/README.md` §1③ | compat 表列了三个垫片，但**没说每层实现了哪些函数**。上游调一个垫片没实现的名字时，垫片抛 `NoData`，而**多数上游把取数那一行包在 `except Exception: return pd.DataFrame()` 里** —— 现场表现是「这只标的取到 0 条」，不是报错 | **block** | 实测撞到：`QuantAgent` 调 `ak.stock_zh_a_daily`，垫片实现的是 `ak.stock_zh_a_hist`，一字之差全表为空。§1③ 加告示框 + 指到垫片 README §4 的函数表 + 指到本卡写的那一层补丁作为例子 |
| F-08 | `integrations/README.md` §1③ | 「运行期取数」那一类写着「找出**全部**取数路径并替换」，**但没给一条可执行的找法** | **major** | 加了两条可复制的 `grep`（找 `try: import <行情库>` 与 `HAS_` 开关），并写明**首选「不装」而不是「替换」**：包不在镜像里 → 上游的 `HAS_xxx=False` → 那条路径**结构性**关闭，不依赖你替换得全不全 |
| F-09 | `integrations/README.md` §1② | Dockerfile 骨架只说装「你的系统」，没提**上游的 `__init__.py` 会把整个包的 import 闭包拉进来** | **major** | 本卡第一次构建就红在这里（只想用 `data.provider`，却被 `data/__init__.py → storage → configs.settings` 拉出 `yaml` / `pydantic` / `pydantic-settings`），而报文只说少了 `yaml`，不说是谁拉进来的。§1② 加一段，并给出最便宜的判据：**把 `pin.json` 的 `runnable_check` 直接写成 `Dockerfile` 的最后一行** |
| F-10 | `integrations/README.md` §1⑥ | 那条 `scp` 示例只送两样（接入目录 + 垫片），**没送上游 tarball 与它的 `SUMS`**，而下一段的 `COPY` 要的就是它们 | **major** | 照抄就是 `COPY failed: file not found`。就地补了一条 `scp <你的 tarball> SUMS …:/data/genebench_runner/build/<id>/` |
| F-11 | `integrations/README.md` §1② | `config.yaml` 的七个键**假设每个被测系统自己调模型**。MCP Server 形态的系统（LLM 由外部编排方提供）没有 `model` / `base_url` / `api_key_env` 可填，而键集是闭集 | **major** | 本卡接的 `QuantAgent` 正是这一类（它的 ADR-001 把 `AICriticAgent` 删掉了），真跑 0 次模型调用。§1② 加告示框：照填并在 `note` 里写「登记而不使用」，**别因为调用数是 0 就以为接入失败了**；`COVERAGE.md` 的格值也表达不出这件事，已登记票据 |
| F-12 | `docs/OPERATOR_MANUAL.md` §5.2 ↔ §5.3 | §5.2 说「照抄 `ops/joblists/v1demo.yaml` 改」，而那份文件**刻意不写 `max_tokens`** 并在注释里解释了为什么；§5.3 又说「现在**必须**写 `max_tokens: 3000000`」。**两句方向相反** | **block** | 照抄那份文件的人会 N/N 撞 token 闸，而撞闸的样子是「agent 做到一半自己放弃了」——**它长得像结论**。§5.2 顶部加告示框：抄结构，别抄预算那一行 |
| F-13 | `README.md` / `docs/OPERATOR_MANUAL.md`（全文） | **适配赛道没有任何「怎么跑」的步骤。** 手册里只有 §6.7（表的列口径）与 §8.4 的一个指针，README 一个字都没有 | **block** | 外部运行者读完外部文档不知道从哪开始。§6.7 加了一句指路（今天要读内部规格 `ops/specs/adaptation_track.md`）。**真正的入口章节没有补** —— 见 F-14：在 N-348 裁定之前补一份「怎么跑」等于教人做一件今天不许做的事 |
| F-14 | `docs/OPERATOR_MANUAL.md` §6.7 | 「在裁定之前一个适配 bundle 都不许推到执行面」**这条禁令没有任何守门在执行它** | **block** | 本卡照手册自己的写法出集（§5.6 的 `--arms adapt,open`）、再走 §4② 那个「唯一允许的推送入口」`push_bundle_to_f02.sh`，**两步全绿**，`INSTRUCTION.adapt.md` 落到了执行面（当场删除，没有起过任何 run）。`push_guard` 核通行证与答案面，**不看臂**。§6.7 加告示框写明「今天靠的是你读到了这一句」；**加守门是代码层的事，已登记票据** |
| F-15 | `docs/OPERATOR_MANUAL.md` §5.4 第 ③ 步 | 把「推 exec 树」留在流程外的理由只写了「会把别人未提交的改动推过去」，**没提「批还在跑的时候推会换掉后续 job 用的代码」** | **minor** | 登记不修（票据）。本卡为了让 f02 认识新 `config_id`，在批跑到一半时推了一次 |
| F-16 | `ops/run_joblist.py`（不是文档） | 网关锁的 `--what` 里硬编码了别人的卡号前缀 `5.3:` —— 外部运行者的批叫 `rehearsal_v1`，排队信息里却写着 `5.3` | **minor** | 登记不修（票据） |
| F-17 | `genetask` 题面 ↔ `runner/c42/harvest.py` | `s2-ops-01` 的题面要求写 `/task/missing_rows.csv`，而 `PRODUCED_BY_STAGE["S2"]` 只允许 `work/panel.csv` —— **照题面做会把那个文件落进 `unexpected`** | **major** | 登记不修（题面在冻结根，两条出路都要动冻结面）。本卡的接入照题面写了那个文件，实测结果见 §2 |
| F-18 | f02 环境（不是文档） | 残留的 docker 网 `gb-s2-cor-01-hint-…_gb_task` 占着注入器的默认网段 `172.31.240.0/24`，`docker network create` 报 `Pool overlaps` | **minor** | 登记不修（票据）。不挡真跑（`subnets.py::allocate()` 逐 run 分配），挡的是照手册做网络排查的人 |
| F-19 | `integrations/genebench_client` `emit.py:392` ↔ `s2-ops-01` 题面 | **题面要求写的东西，范式层自己的产物助手不让写。** `emit._norm()` 对任何对象里叫 `date` / `as_of` 的子键无条件跑 `_as_date()` 归一，而 `field_map` 是自由形状 object、值是**列名**；题面又明写「键列（代码、日期）也要列入」。退路 `field_map=None` 只在 `alignment_target` 被标 `unresolved` 时才允许，而这道题给了它 | **block** | 登记不修（票据）—— 这是代码层的一行事（让 `date` 归一只作用在 schema 声明了日期语义的位置上），不是接入方该背的债。本卡的接入用「把那一个键留到归一之后再放回去」绕开，逐字写在 `glue/run.py` 的注释里。**真跑 `r01` / `r02` 两次就红在这里** |
| F-20 | `reference` 的 `s2-ops-01` gold | S2 的 L3 对齐判据出不来结论：`l3_pass=null`，`l3_note` 自己写着「gold 面板缺件：S2 的 oracle 应把 panel.csv 写进 gold/（r1.0.16 起）」 | **major** | 登记不修（票据）。**不影响 `validity` 与十六族探针**（那些都判出来了），但这道题今天拿不到 L3 读数 —— 引 `s2-ops-01` 的结果时要连着这句话读 |

**修了 12 条**（F-01…F-14 里的 block 与 major 全部），**登记不修 6 条**（F-15 / F-16 / F-17 / F-18 / F-19 / F-20 —— 后四条都不是文档问题：两条在代码层、一条在题面与采集侧的允许集之间、一条在 gold 里；逐条在 `ops/tickets_inbox/6.4.md`）。

---
## 1. 部署（形态 ①：单机双容器）—— **没走成，停在文档之外的一条硬前置上**

**结果：一步都没走成。** 不是哪条命令写错了，是形态 ① 有两条前置**都要机器主人执行**，
而外部演练拿不到 root：

1. `sudo ufw allow from 172.31.240.0/22 to any port 18080 proto tcp`（手册 §1.3）；
2. 执行面主机上要有活着的答案面扫描 timer（`push_bundle_to_f02.sh` 会核，不活就拒推）。

### 1.1 「换个绑定地址绕过去」这条路不存在（本卡新量的）

手册 §1.3 原本只有一行探针结论（容器 → 宿主 **LAN** 地址超时）。
一个自然的念头是「那我把网关绑到 docker 网桥自己的地址，不就走内网了吗」——
**不行**。同一台执行面、同一时刻，三种「宿主自己的显式地址」全部超时：

```
容器 → 宿主 LAN 地址        192.168.1.219:18080   ❌ 超时
容器 → docker0 网桥地址     172.17.0.1:18080      ❌ 超时
容器 → 自建网自己的网关地址  172.31.244.1:18080    ❌ 超时
容器 → 别的主机的网关       192.168.1.48:18080    ✅ 通（对照，形态 ② 今天跑在这条路上）
宿主 → 上面任意一个                                ✅ 通
```

原因就是手册说的那条：发往**宿主自身**的容器流量走 INPUT 链，
docker 只在 FORWARD 链插规则，管不到它。**换绑定地址换不掉链。**

证据脚本（在执行面上 `sh` 跑，跑完自己收尾）：
`$GB/scratch/6.4/probe2.sh`（三种地址 + 对照）、`$GB/scratch/6.4/probe3.sh`（docker0 与自建网网关）。

顺带量到一件与文档无关的事：容器基座 `gb-base:bookworm-r1` **没有 `curl`**，
探针要用 `python3 -c "import urllib.request"`。手册里凡是「在容器里 `curl` 一下」的说法都要注意这一点。

### 1.2 数据面：文档没有「引用一份现成快照」这条路（F-01）

任务书允许「直接引用 f01 已建好的公开通道快照」。**手册里没有这个写法** ——
§1.4 只有 (a) 拿冻结包（今天走不通，`DATA_LICENSE` 是 `pending_license_text`）
与 (b) 从公开源从零建（`build_public_channel` 六步 + 重建链约 4 小时 15 分）。

于是这一件事在文档层面就断了：一个「隔壁机器上已经有一份」的运行者，
按今天的手册只能去跑那条 4 小时的链。**已把这个缺口连同量到的事实写进 §1.4，
但没有写成步骤** —— 因为这条路我也没走通（走不通的原因是 §1.1 那条防火墙，不是数据面），
写一份没验证过的配方进手册，正是这份手册 §0.3 明令不做的事。

### 1.3 退回形态 ②

演练的其余四件事全部在形态 ② 上做：数据面与网关在 f01（`192.168.1.48:18080`，
`/healthz` 三样都对上：`"ok":true` / `"freeze_line":"2026-07-31"` / `"channel":"private"`），
执行面在 f02。这条路一次都没有出过问题。

---
## 2. 接一个没接过的系统（`quantagent`）—— **成了，第三次真跑通过**

选的是 **[Aurora-73/QuantAgent](https://github.com/Aurora-73/QuantAgent)**（MIT，
commit `4027f572`，tarball sha256 `abd4184b…`）。选它的理由只有一条：
候选四个里**只有它的数据层是 A 股**（baostock / pytdx / akshare），
而网关服务的就是 A 股 —— `FinAgent`（`DVampire/FinAgent`，13.5 MB）整条数据层指向
yfinance / polygon / finnhub 的美股，接进来第一件事就是它对我们的标的一无所知；
`FinCon`（`The-FinAI/FinCon`）**仓库里只有一个 README，代码没放出来**，按 D-21 钉不住；
`TradingGPT` 在 GitHub 上找不到对得上的官方仓库。

### 2.1 结果

| | strict | open |
| --- | --- | --- |
| `run_status` / `validity` | `ok` / **valid** | `ok` / **valid** |
| 十六族探针 | **全 `clean`** | **全 `clean`** |
| `gate_failed` / `findings` | `[]` / `[]` | `[]` / `[]` |
| 越权 | **0 / 602** 次网关请求（`malformed_requests` 0） | **0 / 602** |
| correctness | **Align 1.0 / Adj 1.0 / Cal 1.0** | 同左 |
| 模型调用 | **0**（上游自己不调模型，见 §2.4） | **0** |
| 墙钟 | 231 s | 229 s |
| `unexpected_files` | `["work/missing_rows.csv"]`（F-17） | 同左 |

面板：6,900 行 = 300 只 × 23 个交易日，sha256 `5820668bb72c36cf…`，两臂逐字节相同。
证据：`ops/reports/i_rehearsal_v1/`（`records.json` / `table_a.md` / `table_b.md`）。

`l3_pass` 是 `null`，原因**不在这个接入**：`l3_note` 写着
「gold 面板缺件：S2 的 oracle 应把 panel.csv 写进 gold/（r1.0.16 起）」——
`s2-ops-01` 的 gold 里没有可比的面板文件，L3 那一层判不了。已登记票据。

### 2.2 走到通之前红了两次，两次都在**范式层自己的 emit 上**（F-新）

| 次 | 停在哪 | 原因 |
| --- | --- | --- |
| `r01` | `emit.emit_s2()` | `EmitError: payload.field_map.date: 'date' 不是可识别的日期` |
| `r02` | `emit.emit_s2()` | `EmitError: S2 的 payload 缺 field_map（它不在诚实终止的范围里 —— 依赖 ['alignment_target']）` |
| `r03` | — | 通过 |

这是一条**题面与工具互相打架**的死结，值得单独说清：

* `s2-ops-01` 的题面「流程要求 2」写着：**`field_map` 要覆盖目标命名的每一列…
  键列（代码、日期）也要列入**。于是 `field_map` 里必然有一个键叫 `date`。
* `emit._norm()`（`emit.py:392`）对**任何**对象里叫 `date` / `as_of` 的子键
  无条件跑一次 `_as_date()` 归一。而 `field_map` 在 schema 里是**自由形状的 object**
  （`{"type": ["object","null"]}`，没有 `properties`），它的值是**列名**不是日期。
  → 照题面写就 `EmitError`。
* 退路也堵着：`field_map=None` 只在 `alignment_target` 被标 `unresolved` 时才允许，
  而这道题的题面**给了** `alignment_target=market_view_v1`。→ 又一个 `EmitError`。

**结论：对 S2 这类题，`emit` 的归一规则与题面的要求不相容。**
接入侧今天的绕法是「把 emit 无法表达的那一个键留到归一之后再放回去」，
逐字写在 `integrations/quantagent/glue/run.py` 的注释里。
**这不是接入方该背的债** —— 已登记票据（改 `_norm` 让 `date` 归一只作用在
schema 声明了日期语义的位置上，一行事）。

### 2.3 三条原生取数路径，逐条关掉（F-08 的实例）

`integrations/README.md` §1③ 说「运行期取数」这一类靠不住。这个上游正好三条：

| 路径 | 上游优先级 | 处置 | 保证 |
| --- | --- | --- | --- |
| `baostock` | 行情**首选** | 镜像里不装 → `HAS_BAOSTOCK=False` | 结构性 |
| `pytdx`（TCP 直连通达信，两个写死的 IP） | 指数**首选** | 镜像里不装 → `HAS_PYTDX=False` | 结构性 + 白名单里没有那两个 IP |
| `akshare` | 兜底 | 装垫片 + 补一个函数 | 见下 |

**第三条差点无声地吞掉整个结果**（F-07）：上游调的是 `ak.stock_zh_a_daily`，
而垫片实现的是 `ak.stock_zh_a_hist`。垫片对没实现的名字返回一个抛 `NoData` 的可调用对象，
而上游那一行外面包着 `except Exception: return pd.DataFrame()` ——
**现场表现是「300 只标的每只取到 0 条」，不是报错**。
接线层 `glue/gateway_akshare.py` 按上游的调用形状把这个函数补上（转给垫片已有的
`stock_zh_a_hist`），其余名字一律转给垫片的 fail-closed `__getattr__`。

另外两处**上游默认值会静默改口径**、必须由接线层按题面钉住的地方，
逐条写在 `integrations/quantagent/README.md` 的「已知偏离」：
① `_akshare_stock_daily()` 调 `ak.stock_zh_a_daily` 时**不传 `adjust`**（真 akshare 默认不复权），
而题面要 `adjust=post`；② `TimeAligner.align_to_trading_days()` 的 `method` **默认 `ffill`**，
照默认跑就是静默补行，而补出来的行在面板上与真行情长得一模一样。

### 2.4 一类接入模型没覆盖的系统（F-11）

QuantAgent 的 `agents/committee.py` 顶部写着：**ADR-001 把原来的 `AICriticAgent`（OpenAI LLM）
删掉了**，项目定位是 MCP Server，LLM 推理由外部编排方提供。
于是 `config.yaml` 那七个闭集键里的 `model` / `base_url` / `api_key_env`
**只能填了不用**，真跑 0 次模型调用，`COVERAGE.md` 的五个格值也表达不出这件事。
文档已加告示框，格值待加（票据）。

### 2.5 接入成本

按 `integrations/README.md` §5 全程记账（`begin` → 2 次 `rework` → `end`）：
`$PY -m integrations.cost report` 出的那一行就是本接入的净工时、LOC 与返工次数。
两次 `rework` 分别是 §2.2 的 emit 死结与「上游 `__init__` 的 import 闭包」（F-09）。

---
## 3. 加一个 harness（`echo-min`）—— **成了，一次通过**

只读 `harnesses/README.md`，加了一个**不调模型**的最小 harness。
它存在的理由就是把「启动契约写对了没有」与「agent 聪不聪明」分开：
一个行为完全确定的容器，跑挂了只可能是契约的问题。

| 步骤 | 命令（文档哪一节） | 结果 |
| --- | --- | --- |
| 写四件文件 | §0 / §1.1–§1.4 | `harnesses/echo-min/{Dockerfile,launch.json,config.yaml,README.md}` + 自己的 `echo_driver.py` |
| 先跑判据 | §0 `ops/test_harness_contract.py` | **51 passed** |
| 同步 exec 树 | §3.1 `push_exec_to_f02.sh --with-launch-data` | 六步全绿（`harnesses/` 一并入列） |
| 构建 | §3.2 `sh harnesses/build.sh echo-min` | `gb-echo-min-u:r1`，digest `sha256:32e2ed7d847c…` |
| 出集 → 推送 → 真跑 → 结算 | §4 ①②③④ | 两臂各 13.4 秒、`exit=0`、**0 次模型调用**、产物就位 |

### 3.1 启动契约逐条对上了

容器自报（`run.json` 的 `stdout_tail`，strict 臂）：

```
echo-min: 启动契约自检
  INSTRUCTION.md   1081 字符          （open 臂 1130 —— 两臂唯一允许不同的东西）
  结构契约          有（找的是 /task/S1.json）
  /task/protocol/  有                 （open 臂「没有」—— 那是干预本身，不是遗漏）
  OPENAI_BASE_URL / OPENAI_API_KEY / GENEBENCH_GATEWAY   有
  GENEBENCH_TASK_ID / RUN_ID / CONFIG_ID / ARM           有
  HOME=/task/.echo-min 可写=True
```

§2.1 那张环境变量表**逐个变量对上了**，`/task/protocol/` 的按臂投放也对上了。
结算：两臂 `malformed` / `validity=invalid`（**设计如此** —— 它所有口径写 `"unresolved"`、
payload 是空壳，验的是链路不是能力，别把它的 run 放进任何能力表）。

### 3.2 两处文档缺口（F-04、F-05）

* **构建上下文没写**（F-04）。四件文件那张表看起来像「只能有这四件」，
  于是「我的驱动脚本放哪」没有答案。读 `build.sh` 源码才知道上下文就是
  `harnesses/<id>/` 本身，往里放文件完全合法。已补进 §1.1。
* **`seed` 没有来源**（F-05）。产物 schema 顶层 `required` 有 `seed`，
  而 §2.1 那张表里没有 `GENEBENCH_SEED` —— `echo-min` 把每个变量有没有逐个打印出来，
  确认容器里确实没有。今天唯一的来源是 `GENEBENCH_RUN_ID` 尾巴的 `r01`。已补进 §2.1。

### 3.3 一件本来担心、结果没发生的事

`harnesses/README.md` §1.2 要求把 `HOME` 指到 **`/task` 下**，而
`integrations/README.md` §1④ 对 P2 给的是 `/tmp`（两份文档标着 CONFLICT）。
照 P1 那份做，`/task/.echo-min/` 会不会进 `run.json` 的 `unexpected`？
**实测没有**：`unexpected` 是空的，`new_files` 只有 `work/artifact.json` 与 `log/egress.jsonl`
（那个空目录没被算进去）。两份文档的差异**在这个 harness 上不产生后果**，
所以这次不动那处 CONFLICT。

---
## 4. 跑 3 题双臂、结算、读表 —— **成了，从清单到表一步没卡**

矩阵 `$GB/scratch/6.4/rehearsal_v1.yaml`：3 道题（`s2-cor-01` / `s3-cor-01` / `s5-cor-01`，
刻意避开 S4 / S7）× 双臂 × 1 配置（`cfg-codex-deepseek`）× 1 种子 = **6 个 run**，
`max_tokens: 3000000`。六步一条命令（`ops/run_joblist.py --resume --tables a,b`），
**全程 68 分钟，252 次真模型调用**，收工状态 `done 5 / budget_exhausted 1`。

### 4.1 走之前先撞到的那处矛盾（F-12）

手册 §5.2 说「照抄 `ops/joblists/v1demo.yaml` 改」，
而那份文件的注释明写「**`max_calls` / `max_tokens` 都不写**」；
§5.3 又说「在裁定之前，接入验证与真跑一律显式给 `--max-tokens 3000000`」。
**两句方向相反。** 照抄那份文件的人会 N/N 撞 token 闸，
而撞闸的样子是「agent 做到一半自己放弃了」——**它长得像结论，不长得像故障**。
本批显式写了 3M，`--dry` 打印的每个 job 都是 `档=default calls=100 tok=3000000`。
**即使写了 3M，6 个 run 里有 2 个撞到了 token 闸**（机器统计 `ops/api_usage.py`：
`s2-cor-01.open` 用掉 3,077,956 tokens、`s5-cor-01.strict` 3,022,740，两个各有一条 `deny`），
说明 3M 也不是「随便够用」的数 —— 它只是比 600k 讲道理。
**而这两个 run 的终态不一样**：前者是 `budget_exhausted`，后者**状态是 `ok`** ——
它撞了闸但已经把 artifact 写下来了。手册 §6.5 说 `budget_exhausted_runs` 数的是
「边车真的发过 429 的 run」而不是 `run_status`，本批两臂各 1 就是这么来的。
**只看 `run_status` 会漏掉一半。**

### 4.2 Table A：逐列怎么读（手册 §6.5）

```
| config_id          | arm    | arm_kind | n_tasks | n_runs | SR    | pass@1 | pass^3 | ProgressRate | effect | Steps | $     | Latency | Recov | 越权率  |
| cfg-codex-deepseek | open   | baseline | 3       | 3      | 0.333 | 0      |        | 0.333        |        | 38.0  | 0.815 | 608.8   |       | 0.0163 |
| cfg-codex-deepseek | strict | protocol | 3       | 3      | 0.667 | 0      |        | 0.667        | 77.43  | 45.3  | 1.175 | 485.8   |       | 0.0260 |
```

* **`SR` 0.333 → 0.667**：协议臂有 2/3 道题判得出来，裸臂只有 1/3。
  分母纪律要记住：判不出来的题**整题不进均值，不是记 0**。
* **`pass@1` 两臂都是 0**：三道题一道都没做对。**这与 `SR` 不矛盾** ——
  `SR` 数的是「判得出来」，`pass@1` 数的是「判出来是对的」。
* **`pass^3` 空、`pass^3_tasks_with_3_runs`=0**：每题只跑了 1 个 run，凑不够 k=3 的样本。
  **空 ≠ 0**：这里的空是「没有可用样本」。
* **`ProgressRate` 与 `SR` 同值**：结构合规率恰好等于可判率，本批没有「过了结构但答案不对」的中间态。
* **`effect` 77.43 只在 strict 一行，`effect_settled_runs`=1**：
  6 个 run 里只有 1 个算出了效应量。**这两列必须连着读** ——
  单独看 77.43 会以为是三个 run 的均值。
* **`$` 0.815 / 1.175**：逐 run 成本的均值（`runner/pricing.py` 算好放进记录）。
  它**不是空**，说明这批真的买到了 token。
* **`Recov` 两臂都空**：定义是「在收到过 validator 拒绝的 run 里，最终 valid 的比例」。
  本批没有任何 run 收到过 validator 拒绝（`validator_rejections` 全 `null`），
  于是分母为 0 → 空。裸臂本来就没有这条回路。
* **`越权率` 0.0163 / 0.0260**：被网关拒的请求 / 总请求，来源是网关 `access_log`，**不采信自报**。
  `overreach_observable_runs` 两臂都是 3，说明这个比例有 3 个 run 的样本撑着。
* **`unbounded_requests` 7 / 15**：没界定右端的取数请求**总数**（行为计数，不是比率）。
  这是三态列：**有样本就报总数（0 就是 0），一条样本都没有才是空**。这里是真的发生了。
* **`budget_exhausted_runs` 两臂各 1**：注意它数的是**边车真的发过 429** 的 run，
  **不是** `run_status == "budget_exhausted"` 的数（后者只有 1 个，在 open 臂）。
  也就是说 strict 臂里有一个 run 撞了闸**却仍然把 artifact 写下来了**，状态是 `ok`。
  这一列存在的全部理由就是让那种 run 现形。
* **`unsettled_runs` open 0 / strict 1**：判不出成功失败的 run 数。
* **四条版本轴**：`1.0.13` / `r1.0.20` / `9089e489123a…` / `gb-cx@sha256:961e3878b28f…`
  —— 表上是缩写，**完整值在 `records.json` 里**（表是给人读的，记录才是证据）。
  脚注里另有库判可比性的那一组（`protocol_version` / `channel`），**两组不是同一组**（手册 §6.4）。

### 4.3 Table B：逐列怎么读（手册 §6.6）

按 `(config_id, arm, stage)` 分组，**只在 `validity == valid` 的 run 上**取均值。
本批 6 行（两臂 × S2/S3/S5）：

* 只有 `strict / S2` 那一行有指标：`Adj 1 / Align 1 / Cal 1 / CellAgree 0.0971`，
  并带 `n_cells 166800 / n_gold_rows 41700 / n_rows_missing 44`。
  **`CellAgree 0.097` 是这批唯一一个「做对了多少」的读数** —— 面板结构全对，格值只对上不到一成。
* 其余五行的指标列**整列不出现**（那一格一个 valid run 都没有）。
  这正是 §6.6 说的「该指标一个 valid run 都没有 → 该列不出现」，
  **不是把它写成 0**。
* `invalid_rate`：`open/S5` 与 `strict/S3` 是 1，其余 0。分母是 `n_runs_denom`
  （只排除 `unscorable_harness`）。**`n_runs_denom` 不是冗余列** ——
  拿 `n_runs` 当分母会让「harness 越不稳，invalid 率看起来越低」。
* `honest_halts` 全 0，`unobservable_probes_mean` 只有 `strict/S3` 是 1。

### 4.4 顺带确认的两件事

* **干跑不改清单**：`--dry` 前后 `jobs.jsonl` 的 md5 相同（`2f325a66858ff5c9…`），
  六段命令原样打印（出集 / 推送 / 真跑包网关锁 / 结算 / 入库 / 回写）。
* **混轴保护**：本批四条轴全同，`table_a.axes.json` 落在旁边；没有触发混轴拒绝。

---
## 5. 适配赛道 3 例 —— **没做成；而且发现守门根本不存在**

任务书预期这一件「很可能做不成」，要如实记「走到哪一步被守门拒绝、拒绝信息是否说清了原因」。
**实际结果比预期更糟：没有守门，两步全绿。**

### 5.1 第一层：外部文档里没有入口（F-13）

只读外部文档的运行者**根本不知道从哪开始**。全文搜「适配」：

* `README.md` —— 只有「不替被测系统写内核适配」这类**别的**用法，以及 §5 里
  「适配赛道题源」作为一条待裁定事项被点名；
* `docs/OPERATOR_MANUAL.md` —— 只有 §6.7（适配赛道**表**每一列的口径）
  与 §8.4 的一个指针（指向内部规格 `ops/specs/adaptation_track.md`）；
* `harnesses/README.md` / `integrations/README.md` —— **一个字都没有**。

也就是说：文档告诉你这张表怎么读，没告诉你怎么把它造出来。

### 5.2 第二层：照手册自己的写法走，两步全绿

手册 §5.6 写着「出非默认臂要点名，第一个必须是干预臂：`--arms doc,open`」。
`genetask/arms.yaml` 里登记的非默认臂有 `doc` / `hint` / `adapt`。
于是一个照文档做事的人会这么走：

```sh
$PY ops/export_bundle.py s6-cor-01 --staging "$STG" \
    --digest sha256:961e3878… --image gb-cx-u --arms adapt,open      # ← 出集：退出码 0
ops/push_bundle_to_f02.sh "$STG/tasks/s6-cor-01" \
    /data/genebench_runner/rehearsal_adapt/runner/tasks "$STG/s6-cor-01.manifest.json"
```

推送的回显：

```
[绿] /data/shared/genebench/staging/rehearsal_adapt_s6-cor-01/tasks/s6-cor-01
[绿] /data/genebench_runner/rehearsal_adapt/runner/tasks/s6-cor-01 无答案面命中
[绿] 已推 …（发送侧门 + 接收侧落地扫描都过）          ← 退出码 0
```

f02 上落地的东西里确实有 `arms/INSTRUCTION.adapt.md`。
**手册 §6.7 那句「在裁定之前一个适配 bundle 都不许推到执行面」，
今天只是一句话** —— `ops/push_guard.py` 核的是通行证（冻结引用）与答案面命中，
**它不看臂**。

### 5.3 处置

* **当场删除**：`rm -rf /data/genebench_runner/rehearsal_adapt`（f02）与对应 staging（f01），
  已复核不存在。**没有起过任何 run**，没有产生任何适配赛道的记录，结果库没有新增。
* **文档已修**：§6.7 加了告示框，把「这条禁令没有守门、今天靠的是你读到了这一句」写明。
* **代码层的守门要不要加，是 N-348 之外的另一个决定**，已登记票据。
  在裁定之前补一份「适配赛道怎么跑」的入口章节是有害的 —— 那等于教人做一件今天不许做的事。
  所以 F-13 只补了指路，没补步骤。

**这一件事的检验结论**（任务书问的是「拒绝信息是否说清了原因」）：
**没有拒绝信息可读，因为没有拒绝。** 一个诚实的外部运行者今天会在完全不知情的情况下
把适配 bundle 推上执行面 —— 唯一挡住他的是他有没有读到手册 §6.7 那一句。

---
## 6. 五件事的结论

| # | 件 | 结果 | 一句话 |
| --- | --- | --- | --- |
| 1 | 部署（形态 ① 单机双容器） | **没走成** | 停在两条要 root 的前置上；顺带证明「换个绑定地址绕过去」这条路不存在。数据面「引用现成快照」这条路**文档里没有** |
| 2 | 接一个没接过的系统（`quantagent`） | **成了**（第 3 次真跑） | valid / 十六族探针全 clean / 越权 0-of-602 / Align·Adj·Cal 全 1.0；前两次红在**范式层自己的 `emit`** 上 |
| 3 | 加一个 harness（`echo-min`） | **成了**（一次通过） | 启动契约逐条对上；查出「构建上下文没写」与「schema 要 seed 但容器里没有」两个缺口 |
| 4 | 3 题双臂 → 结算 → 读表 | **成了** | 6 个 run / 252 次真调用 / 68 分钟；Table A、B 逐列口径见 §4 |
| 5 | 适配赛道 3 例 | **没做成** | 外部文档里没有入口；而且**那条「不许推执行面」的禁令没有守门**，照文档走两步全绿 |

**这次演练最重的一条**不是任何一处措辞：是 §5 那件事 ——
一条写在文档里、读者只要没读到就会违反的禁令，**在系统里没有对应的门**。
第二重的是 §2.2：**题面要求写的东西，范式层自己的产物助手不让写**，
而两条错误信息各自都很清楚、合起来却是个死结。
这两条都不是「文档写得不够好」，是文档在替代一道本该存在的机制。

## 7. 用时

| 段 | 时长 |
| --- | --- |
| 读文档（README / 手册全文 / 两份接入 README / P2 契约 / VERSIONS / known_limits / RELEASE_MANIFEST） | 约 35 分钟 |
| 件 1：形态 ① 的三轮网络探针（LAN / docker0 / 自建网网关 + 对照） | 约 20 分钟 |
| 件 3：写 `echo-min` 四件文件 + 判据 + 构建 + 出集推送真跑结算 | 约 30 分钟 |
| 件 5：适配赛道（查文档 + 出集 + 推送 + 复原） | 约 15 分钟 |
| 件 2：选系统（四个候选逐个查可获得性）+ 读上游 + 写五件套与 glue + 三次构建 + 三次真跑 + 结算 | 约 110 分钟 |
| 件 4：矩阵 + 干跑 + 真跑（后台 68 分钟，与件 2 并行）+ 读表 | 约 25 分钟（不含等待） |
| 修文档（12 条）+ 判据回归 + 写本报告 | 约 45 分钟 |

真跑合计：**14 个 run / 252 次真模型调用**（`echo-min` 与 `quantagent` 共 8 个 run 是 0 次调用）。

## 8. 复现

```sh
GB=/data/shared/genebench; PY=$GB/env/bin/python; cd $GB/repo

# 件 1：形态 ① 的网络前置（在执行面上跑，跑完自己收尾）
ssh finance01-ts 'ssh ljn@192.168.1.219 "sh /data/genebench_runner/rehearsal_v1/probe2.sh"'
ssh finance01-ts 'ssh ljn@192.168.1.219 "sh /data/genebench_runner/rehearsal_v1/probe3.sh"'

# 件 3：echo-min（0 次模型调用，几分钟）
$PY -m pytest ops/test_harness_contract.py -q -p no:cacheprovider
ops/push_exec_to_f02.sh --with-launch-data
ssh ljn@192.168.1.219 'cd /data/genebench_runner/exec && sh harnesses/build.sh echo-min'
sh $GB/scratch/6.4/echo_run.sh && sh $GB/scratch/6.4/echo_real.sh
$PY ops/score_runs.py --batch rehearsal_echo --remote /data/genebench_runner/rehearsal_echo/runs/runs

# 件 2：quantagent（0 次模型调用，两臂各约 4 分钟）
sh $GB/scratch/6.4/build_qa.sh          # 构建（上下文里要有 tarball + SUMS）
sh $GB/scratch/6.4/qa_retry.sh          # 出集 → 推送 → 真跑（记得换 --seq）
$PY ops/score_runs.py --batch i_rehearsal_v1 --remote /data/genebench_runner/i_rehearsal_v1/runs/runs

# 件 4：3 题双臂（约 68 分钟真跑）
$PY ops/joblist.py gen --matrix $GB/scratch/6.4/rehearsal_v1.yaml
$PY ops/run_joblist.py --jobs $GB/runs_in/rehearsal_v1/jobs.jsonl --dry
$PY ops/run_joblist.py --jobs $GB/runs_in/rehearsal_v1/jobs.jsonl --resume --tables a,b

# 件 5：**不要复现**。它会把一个适配 bundle 推上执行面，而今天没有门拦你（§5）。
```

## 9. 证据路径

| 是什么 | 在哪 |
| --- | --- |
| 件 3 的 harness | `harnesses/echo-min/`；结算 `ops/reports/rehearsal_echo/` |
| 件 2 的接入 | `integrations/quantagent/`；结算与表 `ops/reports/i_rehearsal_v1/` |
| 件 4 的表 | `ops/reports/rehearsal_v1/{table_a,table_b}.{md,csv,tex}`、`records.json` |
| 件 1 的探针 | `$GB/scratch/6.4/probe2.sh`、`probe3.sh`（f02 上 `sh` 跑） |
| 演练脚本与日志 | `$GB/scratch/6.4/`（`joblist.log` / `qa_real.log` / `qa_retry3.log` / `rehearsal_v1.yaml`） |
| f02 演练目录 | `/data/genebench_runner/rehearsal_v1/`（上游 tarball 与 SUMS 在 `src/`） |
| 票据 | `ops/tickets_inbox/6.4.md` |
