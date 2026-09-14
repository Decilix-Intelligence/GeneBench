# A1 / M4 收口报告（2026-09-05 夜班）

> 裁定：「A1 出结果即 M4 收口报告」。三配置（OpenHands / Codex / RD-Agent(Q)，同一 DeepSeek）各跑一道真题（s1-cor-01）、双臂各一次；
> 跑不通的记 BLOCKED 并列具体错误。本报告只报机器证据；判据设计上的疑点单列（N-114）。

## 0. 前置：统一基座跨版本核

`ops/reports/crossver_probe_a1.md`：f01 oracle 环境（py3.10 / pandas 2.2.3 / numpy 1.26.4 / pyarrow 20）与统一基座
`gb-base:bookworm-r1`（py3.12 / pandas 2.3.3 / numpy 2.5.2 / pyarrow 25.0.1）在同一份 agent 可见面板上算 18 个量，
**17/18 逐位相同**；唯一不同是 parquet 字节流 sha（pyarrow 版本编码差，值相同）。第三腿（f01 同机钉版本）因 f01 出网卡住未做（N-108），
两腿已零差，第三腿信息量为零。

三个 harness 镜像在基座上各叠一层：`gb-cx-u:r1`（codex-cli 0.153.2 / node 22.23.2）、`gb-oh-u:r1`（openhands 1.11.0）、`gb-rd-u:r1`（rdagent 0.8.0）。
N-62 的偏离从「未在统一基座」缩为「无」。

## 1. 结果（任务集 v1.0.7 / 参考面 r1.0.7 出的 bundle；结算 r1.0.8，数值不变）

数据面结算：`ops/score_runs.py --batch a1`（`ops/reports/a1/`）。网关 access_log 在 f01 本机，按 (task_id, config_id, 时间窗) 三重切片，
四个依赖日志的探针族（declared_reads / fetch_clock / lookahead / source_status）是**真判**，不是 unobservable。

| 配置 | 臂 | run | 结局 | 闸门 | 探针 16 族 | L3（exact） | 模型调用 | tokens（prompt / completion） | 耗时 |
|---|---|---|---|---|---|---|---|---|---|
| Codex CLI（`gb-cx-u:r1`） | GQ（strict） | r03 | **ok，合法产物** | valid | **全 clean** | 0（N-114） | 22 | 679 601 / 28 533 | 255 s |
| Codex CLI | 裸（open） | r03 | no_artifact（第 22 次调用撞 600k token 闸，N-115） | — | — | — | 23 | ≈ 620k / — | 245 s |
| Codex CLI | 裸（open） | r04（token 闸 3M） | **ok，合法产物** | valid | **全 clean** | 0（N-114） | 49 | 1 857 459 / 35 636 | 540 s |
| OpenHands（`gb-oh-u:r1`） | GQ | r02 | no_artifact（**agent 自己停的**，见下） | — | — | — | 37 | 1 113 224 / 33 840 | 238 s |
| OpenHands | 裸 | r02 | **malformed**：`payload.fetches[*].status` 不在 {ok, empty, denied, rate_limited}（写了别的词） | invalid | — | — | 34 | 1 027 018 / 33 793 | 252 s |
| RD-Agent(Q) | 双臂 | — | **BLOCKED**（N-105）：适配器只有无 LLM 的降级路径，没有可发真题的调用命令 | | | | 0 | | |

**判据更正后的 Table A**（`ops/reports/a1/table_a.csv`；n=1 题，pass^3 无定义）—— N-114 裁定 ① 落地，S1 的 L3 改判 Cov% / PIT% / Prov：

| 配置 / 臂 | SR | pass@1 | ProgressRate | effect | Steps | Latency | 越权率 | tokens(prompt) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Codex / GQ | 1.00 | **1.00** | 1.00 | **100** | 21 | 255 s | 0.120 | 679 601 |
| Codex / 裸 | 0.50 | **0.50** | 0.50 | **100**（r04） | 35.5 | 393 s | 0.011 | 2 454 238 |
| OpenHands / GQ | 0 | 0 | 0 | — | 37 | 238 s | 0.049 | 1 113 224 |
| OpenHands / 裸 | 0 | 0 | 0 | — | 34 | 252 s | 0.106 | 1 027 018 |

* **效果分**（裁定 2026-09-05）= `100 × (agent − null) / (oracle − null)`，夹 [0, 100]；底 = 该题 null_agent 产物的同一判据标量，
  顶 = oracle 自比。Codex 两臂的 Cov = 1.0（要求字段一个不缺）→ 100。
* **越权率**改按契约 §6 从**网关日志**结算：`403 次数 / 数据请求总数`（422 的参数错单列 `malformed_requests` ——
  「参数拼错」与「想看未来」含义相反，合成一个数会把它们混掉）。此前这一列是 `None`，因为边车的转发事件不带状态码。
* `$` 列仍空：注册表没有价目表（N-106 已裁定用本仓的最小 LaTeX 出口，价目表另说）。
* Codex GQ 臂的 PIT% = 0.685（54 条数据请求里 17 条 as-of 不合规：`asof_missing` 3 条、`open_range_would_cross_asof` 4 条…），
  裸臂 PIT% = 0.938（690 条里 43 条）。**PIT 是从日志结算的，不采信产物自报。**

真 API 用量：A1 合计 **165 次**（Codex 22+23+49，OpenHands 37+34；上限 200）。总账 3000 里余 2835 给 M6-lite。

## 2. 跑不通的都是我们的坑（已修，各真跑一次）

| 编号 | 症状 | 根因 | 修 |
|---|---|---|---|
| N-100 | 边车起不来，任务容器 `EAI_AGAIN` | 我给 `egress_proxy.py` 加的 vendor 垫片在容器路径 `/opt/egress_proxy.py` 上 `parents[2]` 越界 | 有第三层才加；SIM-N 真打抓到 |
| N-101 | Codex 两臂 3 s 退出、零调用、`mkdir: cannot create directory ''` | compose **解析期**把命令里的 `$CODEX_HOME` / `$OPENAI_BASE_URL` / `$(cat …)` 插值成空 | `$$` |
| — | OpenHands 两臂 20 s 退出、零调用、`PermissionError: /.openhands` | SDK 的 `LLMProfileStore` 要写 `~/.openhands`，容器 uid 1000 无 HOME | `HOME=/task/.oh_home` |
| — | 注入被红线 5 拦：`exec/ops/__pycache__` 0775 | f02 umask 002，宿主 python 写字节码 | `umask 022` + `PYTHONDONTWRITEBYTECODE=1` |
| — | 宿主 runner `import h11` 失败 | f02 python3 无 h11 也无 pip | exec 树随船 `vendor/h11`（P7d 那份） |

这四个 harness 故障的 run（Codex r02 ×2、OpenHands r01 ×2）已移到 `runs_in/a1_harness_faults/`，**不进表**（`unscorable_harness` 的语义，但 score_run 目前只按产物分类，
所以靠人移 —— 登记为待办：run.json 该带 harness_fault 标记）。

## 3. 观察（不是判定）

**OpenHands GQ 臂到底是谁停的**（裁定要求一句话，实测答案）：**agent 自己停的**。
SDK 正常退出（`exit_code=0`，无异常），第 37 次模型调用的回复在 **8 192 completion tokens**（DeepSeek 的单次输出上限）
处被截断，内容仍是在反复推敲题面「把**每一次**取数写成结构化记录」里的「每一次」是指一次 API 调用还是一只标的
（原文可见于 `runs_in/a1/…openhands…r02/log/llm_log.jsonl` 最后一条）—— 它**从没发出写文件的工具调用**。
不是 SDK 驱动崩了，也不是我们的 harness 掐的：预算闸设的是 50 次调用 / 3M tokens，它用了 37 次 / 1.11M。

**OpenHands 裸臂的 malformed 是我们第一个真 agent 的结构性拦截样例**：它把 `payload.fetches[*].status` 写成了
枚举外的词，`s1_status_enum` 当场拦下（「空结果 / 拒绝 / 限流必须可分辨」）。此前 `malformed` 这一桶的样例
全是**我们自己造的**（`reference/artifact_samples.ILLEGAL` 38 条手写非法样例）——
这是第一条来自真实被测系统的，收进验证验证器报告的边界说明里。


* 两个 harness 的**裸臂都能打通网关取数链**（/universe → /calendar → /bars → /adj，边车身份注入生效，16 族探针 clean）；差别在**产物纪律**：
  Codex 两臂都按 S1.json 写出合法产物；OpenHands 裸臂把 `status` 写成枚举外的词（`s1_status_enum`），GQ 臂在 37 轮里反复推敲「每一次取数」的含义没写产物。
* 裸臂比 GQ 臂吃 token（Codex 1.86M vs 0.68M prompt）—— 没有协议工件，靠自己摸。
* Codex 裸臂 r04 的 `fetches` 有 602 条（oracle 601 条：逐标的取），GQ 臂 3 条（整窗取）—— 两种都合法，`exact` 判据把它们都判 0（N-114）。

## 4. 判据上的问题（待批，不是我定）

**N-114**：S1 的 `tolerance.kind=exact` 让 L3 比取数台账逐字相等，而指标规格 §3 给 S1 的是 Cov / PIT% / Prov。
倾向：S1/S2 的 L3 按规格 §3 实现（Cov = 获取字段 ∩ 要求字段 / 要求字段），`fields_obtained` 进集合语义。在此之前 Table A 的 pass@1 对 S1 无意义。

## 5. M4 收口判定

* 路线 A 的链路（bundle 出集 → 推送守门 → 注入 → 边车（h11 解析、身份注入、模型反代、预算闸）→ 容器 → 采集 → 数据面结算）**端到端无人工干预跑通两次**（Codex 两臂）；
* OpenHands 跑通到「产物」这一步，两臂各自败在产物纪律上（可结算的结局，不是基建）；
* RD-Agent(Q) BLOCKED（N-105）；
* 结算侧：三态、L3、Table A/B 都是最小实现，`effect` 一律 null（卡 5.4 未落地）。

M4 以「链路跑通 + 三配置结局可结算或 BLOCKED 有具体错误」收口；RD-Agent 的 LLM 路径与 N-114 的判据是两条待批。
