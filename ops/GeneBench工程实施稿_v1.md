# GeneBench 工程实施稿 v1（发给 Claude Code 的开工文档）

依据：《设计方案 v1》《指标规格 v1》《源码学习笔记》与两轮服务器侦察（数据湖清点 + readiness 报告）。范围：v1 = 主实验一充分集（Stage 赛道 + Table A 遥测 + Table B 主指标列），Chain/Adaptation/Live 与 L2 裁判均不在本稿。执行者：Claude Code（用户 ljn，无免密 sudo）。所有大体量产物一律落 `/data`，禁落 `/home`。

---

## 0. 环境与架构定稿（由 readiness 实测导出）

**角色分工**：finance01 = 数据面（快照仓、as-of 网关、参考实现、评分器与结果库，全部在 `/data/genebench/`）；finance02 = 执行面（被测 agent 沙箱）。f01 的 k3s 污点 `dedicated=quant:NoSchedule` 顺势保留——benchmark 负载默认调不上数据面，这是我们想要的。

**隔离路线**：主路线 A——人工窗口一次性在 finance02 装 docker 并把 ljn 加入 docker 组，terminal-bench fork 按原设计跑（它依赖 docker compose）。备路线 B——若人工窗口短期不可得，用 k3s Job 包装任务容器先行（kubectl 已可用，`export KUBECONFIG=$HOME/.kube/config`），M4 的 runner 留出 Job 后端接口。路线 A 装完必须复核 flannel：从 01 的 Pod ping 02 的 Pod IP（此集群踩过 `DEFAULT_FORWARD_POLICY=DROP` 丢 VXLAN 的坑，备份在 `/etc/default/ufw.bak-quantlab`）；自定义 compose 网络避开 `10.42.0.0/16`、`10.43.0.0/16`、`10.88.0.0/16`。

**资源纪律**：两台 allocatable==capacity、无系统预留——一切容器必须显式写 CPU/内存 limits（默认 2 CPU / 4Gi / 任务，冒烟期收紧）。并发上限：执行面同时最多 4 个任务容器（12 线程留 4 给系统与 runner）。

**网络纪律**：pypi 索引页超时但 files.pythonhosted.org 快——所有 pip 安装统一 `-i https://pypi.tuna.tsinghua.edu.cn/simple`（或预置 wheels 到 `/data/genebench/wheels/`，二选一，M0 定）。api.anthropic.com 通。02→01 无 ssh 私钥，跨机文件流转一律由 01 发起。

**数据冻结线**：v1 全部任务窗口 **≤ 2026-07-31**。理由：71 个数据集冻在 2026-08-05/06（两速湖），7 月底之前所有口径齐且稳定；冻结线同时给了 v1 天然的可复现快照。W2（premium-daily 漏表）因此不阻塞 v1，推迟到 Live 赛道前处理。分钟线（NFS 桥断）v1 不需要——v1 全部日频，W1 可选。

**人工窗口清单（一次到场，约 1 小时；R1 后更新——四次 sudo 已完成其中两项）**。已完成：LXD snap 移除（W0 闭环，经 snap list 与 k3s 健康验证）、finance01 ufw 规则原文抄读。剩余五项：① finance02 装 docker + docker compose plugin，`usermod -aG docker ljn`，装后立刻做 flannel 跨节点连通复核（从 01 的 Pod ping 02 的 Pod IP；自定义 compose 网络避开 `10.42/16`、`10.43/16`、`10.88/16`）；② `apt remove lxd-installer`——snap 虽已删，但 `/usr/sbin/lxc` 触发器仍在，任何 `lxc` 子命令都会把 LXD 再装回来；③ W3：先对 `/data/market_lake_f02` 做分区级校验，再删除 finance02 系统盘上 40GB 的 `~/market_lake_f02.pre-hdd.*` 副本；④ 补读 finance02 的 ufw 规则原文（一条命令），与 finance01 的原文一并存 `/data/genebench/ops/`；⑤ 封堵网关旁路：finance01 的 `/etc/exports` 目前把整块 `/data`（含 ChinaScope）以 rw 导出给 finance02 且当前无人挂载——把这条导出移除或改 ro，杜绝执行面日后经 NFS 绕过网关直读数据。W1（NFS 挂回，R1 定论：走 LAN 地址 `192.168.1.219`、无需动任何防火墙、`ro,soft,timeo=100,retrans=3`、02 侧导出建议改回 ro，估 15–20 分钟）、W5（tailnet ACL 与 FORWARD 定向规则收紧）、W4（prismquant CrashLoop、index-minute-backfill failed）均不进本窗口，登记 `ops/tickets.md` 待排。

---

## 1. 仓库与目录

monorepo `genebench/`（源码在 f01 的 `/data/genebench/repo`，git 裸镜像同步到 f02 供沙箱构建）：

```
gateway/     as-of 数据网关（FastAPI + duckdb 只读）
snapshots/   快照仓构建脚本与版本清单（数据本体在 /data/genebench/snapshots/）
reference/   参考实现执行器与 gold 产物（对被测 agent 不可达）
tasks/       任务包（terminal-bench 骨架 + GeneQuant 字段）
runner/      terminal-bench fork + 适配器 + 遥测
scorer/      L1 探针 + L3 结算 + 报告器（目录切分仿 SWE-bench harness）
ops/         盘点、工单、环境基线记录
```

Python 环境：`/data/genebench/env`（conda，Python 3.10，克隆 qlib_env 的包清单起步；不动现有 qlib_env）。所有服务以 ljn 身份运行，无 sudo 假设。

**答案隔离红线（施工期就生效）**：`reference/` 与 `scorer/` 的产物目录只存在于 f01，执行面容器不挂载、网关不服务它们；网关只答数据、不答答案。原始 vendor 数据与 ChinaScope 任何字节不进任务容器、不进公开子集。R1 后补两条：benchmark 的一切网络服务绑定 LAN 具体地址、禁止监听 `0.0.0.0`；执行面（含任务容器）不挂载任何 NFS——数据的唯一入口是网关。 **2026-09-01 再补第三类不可泄漏物**：记忆探针（N-31）的答案集**永不进执行面、永不进任何 agent 可达路径**，与 `reference/` 的 gold 产物、`scorer/` 的评分代码同级 —— 落在 `reference/memory_probe_answers/` 以继承本红线的全套强制。单列一类的理由：前两类泄漏的后果是局部的（坏掉一道题），这一类泄漏会让**整套探针永久失效且静默失效**，之后的命中率上升会被读成「污染变严重」，实际是题目泄漏。详见 `ops/specs/card_3.2_5.1_memory_probes.md` §5.0。 **2026-09-02 再补一句（卡 3.1）**：任务包的三串金丝雀（gold / control / x）**覆盖边界是文件级** —— 转格式（CSV/JSON 重序列化）会丢 metadata，因此金丝雀命中零**不等于**无泄漏，它只证明没有原样搬运；内容级泄漏由「oracle 不进容器」与目录 0700 这两条红线守。 **2026-09-02 再补一句（卡 3.1）**：任务包的三串金丝雀（gold / control / x）**覆盖边界是文件级** —— 转格式（CSV/JSON 重序列化）会丢 metadata，因此金丝雀命中零**不等于**无泄漏，它只证明没有原样搬运；内容级泄漏由「oracle 不进容器」与目录 0700 这两条红线守。 **2026-09-02 再补一句（卡 3.1）**：任务包的三串金丝雀（gold / control / x）**覆盖边界是文件级** —— 转格式（CSV/JSON 重序列化）会丢 metadata，因此金丝雀命中零**不等于**无泄漏，它只证明没有原样搬运；内容级泄漏由「oracle 不进容器」与目录 0700 这两条红线守。 **2026-09-02 再补一句（卡 3.1）**：任务包的三串金丝雀（gold / control / x）**覆盖边界是文件级** —— 转格式（CSV/JSON 重序列化）会丢 metadata，因此金丝雀命中零**不等于**无泄漏，它只证明没有原样搬运；内容级泄漏由「oracle 不进容器」与目录 0700 这两条红线守。

---

## 2. 里程碑与任务卡

每卡格式：目标 → 要点 → 验收测试（完成定义）→ 估时 → 依赖。串行主线 M1→M2→M3→M5→M6→M7；M4 与 M2/M3 并行。
（**M6 于 2026-09-04 改定为构造验收、不出表**；**M7 实验规划**为同日新增，
网格运行在 M7 审定之后。总估随之重排，原「2.5–3.5 周」只覆盖到 M6。）

### M0 施工准备（0.5 天 + 人工窗口）

**卡 0.1 仓库与环境基线**。初始化 monorepo、CI 脚本（本地 pytest，无外网依赖）、`/data/genebench/{env,wheels,snapshots,results}` 目录树；pip 镜像写进 `pip.conf`。验收：`pytest ops/test_env.py` 全绿（断言 duckdb/pandas/pyarrow/qlib 可导入、/data 余量 >500G、网关端口空闲）。
**卡 0.2 湖只读基线**。对 `catalog/market.duckdb` 建只读连接封装，登记 v1 依赖的表清单与各表 `max(date)`，产出 `ops/lake_baseline.json`。验收：清单内全部表可查、日期上限 ≥ 2026-07-31。

### M1 数据网关 + 快照仓（2–3 天）——整个 v1 的承重墙

**卡 1.1 PIT 宇宙表构建**。输入三源：`index_weight` 相邻月末 diff 推 csi300/500/1000 成分区间；qlib community `instruments/*.txt`（PIT 起止名单）交叉对账；`stock_basic.delist_date`+`list_date`+`namechange` 兜底。产出 `universe_pit`（code, universe, in_date, out_date, source, agreement_flag）。验收：与 qlib instruments 的区间一致率报告（抽 300 只逐段比对），分歧清单人工抽查 20 条后签字；月内调整被抹平的已知局限写进数据卡。
**卡 1.2 可交易性视图**。三方 join `daily`（缺行）× `suspend_d` × `trade_cal(SSE)`，叠加 `stk_limit` 触板判定（注意 `stk_limit.pre_close` 全 NULL——触板必须 `daily.close/high/low` 对 `up_limit/down_limit` 比价）。产出 `tradability(code, date, status∈{trade,suspend,limit_up,limit_down,no_data}, …)`。验收：2026-08-28 实测样例复现（000711.SZ=suspend 且 daily 无行、600491.SH=trade）；随机 50 个 (code,date) 人工对 tushare 网页核 10 个。
**卡 1.3 as-of 网关**。FastAPI 服务（f01，**绑定 LAN 地址 `192.168.1.48`，禁止监听 `0.0.0.0`**——R1 实证 tailscale 流量经 ts-input 链绕过 ufw，凡 0.0.0.0 监听即对全 tailnet 敞开，而 tailnet 内含第三方账号的节点），端点族 `/bars /adj /calendar /universe /tradability /fundamentals /limits`；每请求强制 `as_of` 参数，任何目标日期 > as_of 一律 403 并写 `access_log`（含 config_id/task_id/请求全文）；复权统一 `adj_factor` 口径（`stk_factor_pro` 的三价口径不进 v1 数据面，避免 8 月起的双口径不同步）；`stock_basic` 类多快照表由网关封装 snapshot 语义，2026-08-05 前的状态一律走字段回溯而非快照。基本面端点只暴露三大报表（`f_ann_date`+`update_flag` 严格 PIT）；`fina_indicator` 不进 v1（缺 `f_ann_date`，降级规则留给 v1.1）。验收：探针单测套件全绿——越界请求必 403 必记录；PIT 可见性测试（600519 的 2026Q1 报表在 as_of=2026-04-24 不可见、04-25 可见）；停牌日 bars 返回带 status 而非静默空。
**卡 1.4 快照版本化**。对 v1 依赖表做一次 parquet 快照到 `/data/genebench/snapshots/v1/`（冻结线 2026-07-31），manifest 记 sha256 与行数；网关可切 `live 湖 / snapshot` 两种后端，v1 评测一律走 snapshot。验收：同一查询两后端结果一致（冻结线内）；manifest 完整。

### M2 参考实现与标定（2 天，依赖 M1）

**卡 2.1 因子参考执行器**。接入 `factor_library` 的 792 条可执行因子：oracle 执行器按 `execution_backend` 三路分发（qlib_expression / qlib_panel_loader / kunquant，KunQuant pin d4b9e61），数据经网关 snapshot 后端喂入。产出每因子的 gold 因子值面板（宇宙 × 窗口）。验收：抽 30 条跨后端可比因子做双实现互检（同因子 compiled 表达式 vs panel/kunquant 路径），秩相关分布报告落盘。
**卡 2.2 τ / ε 标定**。τ = 卡 2.1 双实现两两秩相关分布的 P10（按因子族分别报告）；ε = qlib 回测（TopkDropout，费率与可交易性过滤开启）对同一 gold 信号 5 种子重跑的指标极差 ×1.5。验收：`calibration.json` 落盘，含分布图；τ/ε 数值经你签字后写死进 scorer 配置。
**卡 2.3 提交格式冻结**。八阶段 artifact 的 JSON schema 定稿；TargetPosition 提交格式参照纸面台账 `ledger.sqlite3` 的 targets 表字段（symbol/score/previous_weight/target_weight/delta_weight/reference_close）。验收：schema 校验器 + 每阶段一个合法样例与三个非法样例的单测。

### M3 任务集（3–4 天，依赖 M1，与 M4 并行）

**卡 3.1 GeneTask 打包器**。terminal-bench 骨架（task.yaml + Dockerfile + tests/）+ GeneQuant 字段（stage、contract 引用、as_of、双臂 instruction 变体、gold 指针、探针配置、金丝雀串）。验收：打包器从模板 + 参数表批量实例化，产出物过 schema 校验。
**卡 3.2 v1.0 冒烟集（8×5=40 题）**。题源映射：S1=网关取数任务（指定字段/窗口/宇宙，Prov 用结构化引用：表名+查询参数）；S2=清洗对齐任务（复权/日历/缺行陷阱各若干，材料就是卡 1.2 发现的真实坑）；S3=因子实现（从 792 条抽，源方言原文当题面、compiled 当 gold）；S4=因子验证（声明评估设定，IC 族对 gold 复算）；S5=信号构造；S6=组合构建（约束集 + TargetPosition）；S7=回测复现（gold 信号 + 声明成本，指标落 ε 带）；S8=模拟交易速通版（网关状态接口，日频撮合）。每阶段含 1 题欠定语义探针（故意不声明复权或日历）。验收：40 题全部过打包校验；oracle_agent 跑通全部并得满分或标定分；null_agent 全部得低分。
**卡 3.3 v1.1 扩量（8×15–25）**。冒烟通过后按模板参数化扩量 + 难度门（对 2–3 个前沿配置预跑，全过/全挂题回炉）。验收：难度门报告 + 你抽 10% 复核签字。

### M4 Runner（2–3 天，依赖 M0，路线 A 依赖人工窗口）

**卡 4.1 terminal-bench fork 三改造**。任务容器加网关网络路由（只开 f01 网关端口）；parser 出口接 scorer；AgentResult 遥测（tokens/failure_mode/markers + 我们补记的 $/latency/steps）写入 results 库。若人工窗口未成行，本卡先做 k3s Job 后端（Pod 模板带 limits、toleration 不设——默认只调度 f02）。验收：hello-task 在两臂下端到端跑通，遥测入库，网关 access_log 出现该 task_id。
**卡 4.2 专用系统适配器 ×2**。TradingAgents 与 RD-Agent(Q)（后者数据走"网关 snapshot → qlib provider 适配层"，一处适配兼做其原生依赖）。验收：各自在 S3 或 S7 的一道冒烟题上产出可评分 artifact。
**卡 4.3 双臂注入器**。GQ 臂加载三协议与 validator 工件、结构化违例反馈；裸臂等价自然语言说明。验收：同题双臂 instruction диff 审查（语义等价、无信息不对称）由你抽查签字。

### M5 评分器（3 天，依赖 M2）

**卡 5.1 L1 探针族**。前视（网关日志结算）、日历、复权指纹（用湖内已知拆分事件构造指纹样本）、PIT 宇宙、欠定语义，五探针独立模块 + ARE 式注册表挂接到各阶段 artifact 字段。验收：每探针一组保真/破坏扰动单测（对 oracle 产物注入已知违例必须命中、干净产物零误报）——这就是 v1 的"验证验证器"报告初版。
**卡 5.2 L3 结算**。**IC 族 Qlib SigAnaRecord、回测 gold 契约实现 B2、qlib 对照**（改因 N-39，裁定 2026-09-05）：原文是「Qlib 薄封装（SigAnaRecord 的 IC 族、backtest 栈费后指标）」，即回测侧也拿 qlib 当 gold。N-39 实测推翻了支撑那一句的归因 —— 卡 2.2b 把 A↔B 的 22.69% 毛收益差「定位到 A-1/A-2」是**排除法**得到的，而隔离实验做出来 A-1 单独的效应量只有 0.38%–0.45%，**差约 50 倍**；也就是说 qlib 与契约实现之间有**未归因的偏离**，偏离清单至今未成。带着未归因偏离的实现不能定义 gold（gold 必须遵守书面契约）。所以：**IC 族**仍用 Qlib `SigAnaRecord`；**回测 gold** 改用契约的独立实现 **B2**（`reference/b2_engine.py`，加载冻结的 `snapshots/v1/epsilon/impl_v2_b2.py`）；**qlib 保留作对账参照**，不进 gold 链路。统一从 snapshot 后端取数；τ/ε 从 calibration.json 读。验收：对 gold 产物评分=满分带内；对已知劣化产物分数单调下降。
**卡 5.3 遥测结算与报告器**。Table A 九指标（SR/pass@1/pass^3/ProgressRate/Steps/$/Latency/Recov/越权率，pass^k 用 τ-bench 估计量）+ 主表 CSV → 现有 LaTeX 表格脚本（gen_v6 的列选择层直接吃真实数）。验收：用 mock 轨迹跑出与 gen_v6 同构的表。

### M6 **构造验收**（依赖全部）—— 范围修正 2026-09-04

> **原文（2026-08-30）已作废，留档对照**：
> 「3 配置（CC·F5、CX·5.5、RD-Agent·GPT-5.5）× 双臂 × 40 题 × 3 seed。产出：首份真实主表……
> 你审阅首表签字后 M3.3 扩量启动。」

**M6 的目的是证明 benchmark 建成，不是产出实验数据。**

| 项 | 定义 |
| --- | --- |
| 规模 | **1 个验收配置** × 双臂 × **每阶段 1–2 题**（含 `s7-rob-02`）× **1 种子** |
| 三控 | oracle / null / filler 三桩走**完整评分器**（不是只走采集器）|
| 产出 ① | **v1.0 就绪报告**：组件版本、冻结根、**全链一次无人工干预跑通**的记录 |
| 产出 ② | **验证验证器报告 v1**：探针对干净 oracle **零误报**、对注入违例**必命中**、三态判定正确 |
| 产出 ③ | 成本画像**样本**（不是预算曲线）|

**本阶段任何数字不进论文，不称主表。** 这条是范围纪律，不是措辞偏好：
一份「1 题 1 种子」的数走进论文，读者会按主表的分量读它，而它承不起那个分量。

M3.3 扩量**不再挂在 M6 之后**，改挂 **M7 的实验设计审定**（见下）。

### M7 实验规划（新增，2026-09-04）

**M6 之后、任何网格运行之前**，产出**实验设计文档**交用户审定。**审定前不启动网格。**

文档必含：

1. **E1–E5 各自的假设与所需运行** —— 一个假设配一组运行，没有假设的运行不跑；
2. **配置矩阵**，含 Claude / GPT 经**受支持地区执行节点**接入的方案（N-54；
   **不走代理绕地区限制**，那是条款问题）；
3. **种子数与预算**；
4. **预注册的 confirmatory 判据与 exploratory 边界** —— 哪些结论是事先声明要检验的、
   哪些只是探索；两者在报告里必须分开写，事后把 exploratory 的发现说成 confirmatory
   是最常见的那种自欺；
5. **基线阶梯（卡 5.4）与记忆探针（N-31）的运行安排**；
6. **难度门处置规则** —— 哪些题因为太难/太易而回炉，规则要**事先**定，
   事后按结果挑题就是选择性报告。

**卡 3.3 扩量以本文档为依据**，不再以 M6 首表为依据。

---

## 3. 决策已定（2026-08-30）

D1 = 路线 A：人工窗口在 finance02 装 docker，到场时间由你排定；窗口发生前 M0/M1/M2/M3/M5 照常推进，全稿只有卡 4.1 的 docker 路径等它（若窗口迟于 M4 启动，卡 4.1 先做 k3s Job 后端保底，窗口后切回）。D2 = LXD snap 已删除并经 R1 验证闭环（W0：snap list 干净、k3s 未受影响）；`lxd-installer` 触发器仍在，窗口里 `apt remove lxd-installer` 根除。D3 = 数据冻结线 2026-07-31 确认，v1 全日频、不含分钟线，W1/W2 缓办不阻塞。D4 = 宇宙源方案甲确认：月末快照 diff 自建为主、qlib community instruments 交叉对账，按卡 1.1 执行。

## 4. 给 Claude Code 的开工指令（复制发送）

> 按 `/data/genebench/repo` 下的《GeneBench 工程实施稿 v1》执行。从 M0 两卡与 M1 全部任务卡开始——它们不依赖 docker 与人工窗口。红线沿用侦察轮：无 sudo 假设、大文件只落 /data、reference 与 scorer 产物不对执行面暴露、不改动任何既有服务与定时任务；发现需要变更既有系统的事项一律登记 `ops/tickets.md` 待批，不执行。每完成一张任务卡，运行该卡验收测试并把结果追加到 `ops/progress.md`，验收未过不进入下一卡。M1 完成后停下来，把网关探针单测报告与 universe 对账报告贴回对话，等人工复核。
