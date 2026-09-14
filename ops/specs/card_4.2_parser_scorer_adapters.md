# 卡 4.2：产物采集器 / 评分接口 / 两个框架适配层

**代码**：`runner/c42/`（现网即 finance02 的 `/data/genebench_runner/c42/`；卡 4.1 的代码在 `c41/`）。
模块：`failure_modes.py`（分类表与恒等式）、`harvest.py`（采集顺序）、`origin.py`（Source × FieldOrigin）、
`identity.py`、`visibility.py`、`emission.py`（shim 协议 + parser）、`values_io.py`（值序列规范形）、
`upstream_pins.py`、`select_loop.py`、`telemetry.py`（`record_strict` + 迁移）、`canary_scan.py`、
`scorer_io.py`（`to_scorer_input` / `gate_only`）、`adapters/rdagent_q/`、`adapters/tradingagents/`。
本卡**复用**卡 4.1 的 `c41/runner_core.py::lint_compose/render_compose` 与 `c41/egress_proxy.py`，**不改它们**。

**验收**：`ops/test_c42.py`（A 档，零外部依赖）、`ops/negctl_parser.py`（≥18 负例 + ≥2 反向）、
`ops/test_c42_e2e.py`（B 档，需容器与镜像构建面）。

**设计来源**：两稿综合。骨架取稿乙（失败模式优先）。
§3 顺序断言、§4 Source 枚举与 `assert_no_inference`、§8 调用点 shim、§10 上游钉死、§12 禁 best-of-N、
§15 白名单同源、§13 遥测交叉核嫁接自稿甲；
§5 payload 逐字段归属表、§7 三重切片、§17 双臂差异断言、§18 排期约束**两稿都没有**，为综合新增。

---

## 0. 本卡不做什么

1. **不改卡 2.3 的校验器。** `artifact_schema.py` 是冻结件。本卡发现的缺口（`config_id`/`arm` 未交叉核）
   登记工单 **N-36**，由卡 2.3 下沉，不在本卡擅改。
2. **不改卡 4.1 的隔离面。** compose 渲染、lint 九条、代理白名单机制都归 4.1；本卡只**调用**它们，
   并在 §15 把白名单的**来源**从手抄改成注册表生成（这是同源化，不是放宽）。
3. **不注入题面。** 两臂 instruction 与协议工件进容器归**卡 4.3**；本卡只在 §17 给出「两臂确实不同」的**断言**，
   不产生题面、不改题面（卡 3.1 的 E1–E13 已保证等价性，4.3 不得在注入期改写）。
4. **不算分。** 效果分、ε 带、anchor 阶梯归卡 5.4；本卡只产出 `scorer_input`，且只在 §16 的出口纪律下产出。
5. **不做真实框架的 S3 冒烟绿灯。** 见 §18：这条验收在 4.3 之前**不可能达成**，本卡只打通链路。
6. **不动既有服务。** 网关加路由、跨机取日志、f02 容器运行时确认，全部登记 §21 待批，不执行。
7. **不写湖、不挂 NFS、不 bind-mount 宿主机路径。** 数据面走网关 snapshot（§11），无例外。

---

## 1. 一条总纪律（写在首页，两稿一致）

> **适配层永不代 agent 做决定。**
> `declarations` 的每一个值只能来自 **agent 自己写的字节**；
> harness 只做四件事：**转录、切片、重算、标注不可检**。

违反它的后果不是 bug，是**「探针量的是我们自己」** —— 主表全绿，而中心结论落空。

这条纪律是本卡全部规则的根：§4 的 `Source` 枚举是它的类型化，§5 的归属表是它在 payload 侧的延长，
§8 的 shim 是它在「事后不可观测量」上的唯一合法实现方式，§12 的禁 best-of-N 是它在**搜索预算**维度的形态。

**四个动作的边界（逐字定义，写进 `origin.py` 的模块 docstring）**：

| 动作 | 允许 | 禁止 |
| --- | --- | --- |
| 转录 | 把 agent 写下的字节原样搬进 artifact | 补默认值、归一化大小写、把 `null` 改成 `unresolved` |
| 切片 | 按 (task_id, config_id, 时间窗) 从日志中选行 | 事后合成日志条目（§11 负例） |
| 重算 | 从 agent 产出的**文件**推导客观量（行数、覆盖率、字节摘要）| 重算 agent 的**判断**（`degeneracy.alert`、`declarations.*`）|
| 标注不可检 | `mark_unobservable(probe, reason)` | 用 `[]` / `0` / `{0,0,0}` 冒充「测过且干净」|

---

## 2. 失败模式分类表（`failure_modes.py`）

### 2.1 为什么必须先有这张表

**实测理由**：现行 `c41/runner_core.py` 的 `failure_mode` 只有 `None | "nonzero_exit"`（:373），
而 **compose lint 未过（:329）与 `starts != 1`（:365）是 `raise`** —— 那几题**连一行都不写进库**。
那不是「失败」，是「**不存在**」：分母悄悄变小、SR 悄悄变高，没有任何东西报错。
这与 D-06 家族同形，而且方向是**对我们有利**的方向 —— 最难自查的那种。

### 2.2 三个枚举

```python
RUN_STATUSES = (                       # 顺序即优先级，前者压后者
    "leaked", "harness_error", "timeout",
    "no_artifact", "artifact_empty", "artifact_truncated",
    "artifact_oversize", "artifact_not_utf8", "artifact_not_json",
    "identity_mismatch", "malformed", "violation", "ok",
)
HARNESS_FAULTS = ("lint", "bundle", "provider_pin", "egress_starts",
                  "docker_up", "runtime_dependency", "stale_state")
SR_BUCKETS = ("scorable", "malformed", "unscorable_agent",
              "unscorable_harness", "leaked")
```

**优先级的理由逐条**：

* `leaked` 压一切 —— 泄漏发生后，这次运行的**任何**读数都不再代表被测系统；先分类成别的状态再补标泄漏，
  等于让一次污染运行的分数先进主表。
* `harness_error` 压 `timeout` —— 我们自己坏了导致的超时不能记在 agent 头上。
* `timeout` 压产物类 —— 超时的产物必然不完整，按 `artifact_truncated` 归类会把「预算耗尽」误读成「写坏了」。
* 产物类压 `identity_mismatch` —— 没有可读产物时谈身份不符没有意义。
* `identity_mismatch` 压 `malformed` —— 产物不属于这个任务时，schema 结论无效。
* `malformed` 压 `violation` —— 结构不成立时行为判定不成立（与卡 2.3 的 `malformed` / `violation` 语义一致）。

### 2.3 全映射与恒等式

`RUN_STATUS_TO_SR` **必须是 `RUN_STATUSES` 上的全映射**：

| run_status | SR 桶 | 理由 |
| --- | --- | --- |
| `leaked` | `leaked` | 单列、不算分、**留在分母**（见下） |
| `harness_error` | `unscorable_harness` | **唯一**被 `sr_denominator()` 排除的桶 |
| `timeout` | `unscorable_agent` | 预算耗尽是被测系统的属性 |
| `no_artifact` / `artifact_empty` / `artifact_truncated` / `artifact_oversize` / `artifact_not_utf8` / `artifact_not_json` | `unscorable_agent` | 「没交出可读产物」是失败，不是不存在 |
| `identity_mismatch` | `unscorable_agent` | 见下 |
| `malformed` | `malformed` | 与卡 2.3 同名同义 |
| `violation` | `scorable` | 结构合法，违例走 `gate_failed` |
| `ok` | `scorable` | |

**`identity_mismatch` 归 agent 而不是 harness**：它也可能是我们注错了环境变量，但那种情况 B 档的注入断言会**先**红。
把它记 harness 等于给「产物在伪装」开了一条**不进分母**的通道 —— 红队 rt05/rt09/rt17 正是这一族。

**`leaked` 留在分母是刻意的**：把它移出分母，等于让一次泄漏事故顺带抬高 SR。
若事后判定泄漏源是打包器，处置是**该批次整体作废重跑**，不是靠调整分母修数。

**`assert_taxonomy_total()`（import 期跑，D-03 恒等式做法）** 四条：

1. `set(RUN_STATUS_TO_SR) == set(RUN_STATUSES)`（无多、无缺）；
2. 值域 ⊆ `SR_BUCKETS`，且**每个桶至少有一个 run_status 落进来**（空桶是死桶，删或补）；
3. `RUN_STATUSES` 无重复，`rank()` 在其上是双射；
4. 每个 `HARNESS_FAULTS` 成员都能映到 `harness_error`，且**只**映到它。

`sr_denominator()` 排除 `unscorable_harness`，**只排除它**；实现里写死这一条并配负例（多排除一个桶必须红）。

---

## 3. 采集顺序（`harvest.py`）

### 3.1 硬顺序

```
load_bundle → check_bundle → render → lint → preflight(provider) → up → run
  → harvest → down -v → canary.scan → parse → classify → record_strict
  → to_scorer_input   (仅 run_status=="ok" 且非 malformed)
```

**每一处顺序都有一个会静默的失败在等着**：

| 相邻对 | 反了会怎样 |
| --- | --- |
| `lint` 在 `up` 之前 | 否则一个违规 compose 已经把端口发布到 LAN 了才被拦（卡 4.1 L-6） |
| `preflight(provider)` 在 `up` 之前 | 否则用错 provider 跑完一整轮，产物看起来完全正常（§11 P1） |
| **`harvest` 在 `down -v` 之前** | `down -v` 删卷；产物随卷一起消失，表现为 `no_artifact` —— **与 agent 真没写产物不可分** |
| `canary.scan` 在 `parse` 之前 | 泄漏必须压过一切分类结论（§2.2） |
| `classify` 在 `record_strict` 之前 | 落库要写 `run_status`，没有分类就只能写 `None`（现行 4.1 的形态） |
| `to_scorer_input` 最后且**有条件** | §16 |

### 3.2 顺序是被断言的，不是被约定的

`test_harvest_order` 用 monkeypatch 把每一步换成记录器，跑一次，断言调用序列**逐项相等**。
理由与卡 4.1 的 lint 同：拓扑保证只在代码长成那个样子时成立，「长成那个样子」必须可测。

### 3.3 harvest 的两条硬规则

* **产物落在 `/task` 挂载之外即 `raise framework_output_outside_task_mount`**（嫁接稿甲）。
  RD-Agent 与 TradingAgents 都默认往 `~/.rdagent`、`./results`、`/tmp` 写；那些路径**不在**我们挂的
  `tasks/<id>` 里，`down -v` 之后就没了。让它静默返回空 harvest 等于把 harness 的配置错误
  记成 agent 的 `no_artifact`。
* **不许返回空 harvest 而不报错。** 空 harvest 只有两种合法来源：agent 真的没写（→ `no_artifact`），
  或框架写到了别处（→ 上一条 raise）。二者必须可分。

### 3.4 超时路径

`run` 必须包在 `try/finally` 里，`finally` 保证 `down -v` 执行；随后断言
`docker compose ls` 里**没有** `gb-<task_id>` 残留（稿乙 T-TO-02）。
理由：超时是最常走的异常路径，也是最容易漏掉清理的那条；残留容器会占住网络与卷名，
下一次 `up` 复用它 —— 那次运行的隔离面就是上一次的（`stale_state`，`HARNESS_FAULTS` 里专门有这一项）。

---

## 4. origin 与「不推断」（`origin.py`）

### 4.1 类型

```python
class Source(str, Enum):
    agent_artifact    = "agent_artifact"      # agent 自己写的字节
    shim_emission     = "shim_emission"       # 发生时由 shim 记下（§8）
    framework_output  = "framework_output"    # 框架自己的产物文件
    framework_config  = "framework_config"    # conf.yaml 等
    absent            = "absent"              # 这次运行里没有这个值
    harness_inferred  = "harness_inferred"    # **永远非法**，只为让它可被断言
FieldOrigin = dict[JSONPath, Source]          # 随 artifact 一并落 provenance
```

### 4.2 四条规则（每条配反向用例）

* **(a)** `$.declarations.*` 的 `Source` **只允许** `agent_artifact`。任何其它值即 `raise`。
  —— 这是 §1 总纪律的类型化形态。
* **(b)** `Source.absent` 的字段**一个键都不写**。
  **理由（已核对 `artifact_schema.py:647`）**：任务欠定而 artifact **缺键**，卡 2.3 报
  `underdetermined_field_missing`（malformed）；写了别的值则报 `silent_completion`（violation，第五探针）。
  这两个结论**必须由校验器给出**，harness 写一个键进去就把它们都毁了。
* **(c)** 见到 `harness_inferred` 即 `raise`。它在枚举里存在的唯一目的，是让「我们没有推断」这件事
  **可被一条断言证明**，而不是靠代码里找不到反例。
* **(d)** **绝不代写 `UNRESOLVED`。** `artifact_schema.py:49` 写得很清楚：
  `UNRESOLVED` 是 agent「我注意到这里欠定了」的**声明**，不是 null。
  harness 代写它 = 把第五探针的正确答案直接送给被测系统。

**反向用例照 `c41/egress_proxy.py::assert_allowlist_sane` 的做法做**：守门写成函数而不是模块级裸语句，
用坏输入喂它、断言它真的抛。裸语句只能证明好输入不红，证不了坏输入会红。

### 4.3 `framework_config` 的准入之争：按**不准入**落

稿甲主张 `conf.yaml` 里的读数（如 RD-Agent 的 `lookback`）可以进 `declarations`。**否决**。
理由：conf.yaml 是**我们**写的，把它的值填进 declarations 就是 harness 代 agent 声明 ——
形式上有来源，实质上是 §1 禁的那件事。落法：`framework_config` 的读数**只进 provenance**，
供人事后追溯「这次跑用的是哪份配置」，**不进 declarations**。

---

## 5. payload 逐字段 origin 归属表（`PAYLOAD_ORIGIN`）—— 必修项 2

### 5.1 为什么必须单列一节

两稿都只禁了「适配层代填 declarations」，对 **payload 谁写**没有裁定 —— 而那是量纲更大的一半：

* 稿乙写「RD-Agent 原生指标一律不采信，全部产物送统一评分器重算」；
* 稿甲写「只取值序列与逐日台账重算」。

**一旦 harness 重算 metrics/attribution，S7 的这几族探针量的就是我们自己的回测器**，不是被测系统。
稿乙在它自己的 Q6 里承认了这一点（TradingAgents 落 S7 时 metrics 全是我们算的）**却没给规则**。
没有这张表，「重算」与「代填」的边界会随实现漂移，而且漂移不会报错。

### 5.2 三种归属

| 归属 | 含义 | 主表脚注里「评的是谁」 |
| --- | --- | --- |
| `verbatim_from_agent` | 原样转录 agent 写的字节 | 被测系统 |
| `recomputed_by_harness` | 从 agent 产出的**文件**重算的客观量 | 被测系统的**产出**，用我们的尺子量 |
| `shim_emitted` | 由 §8 的 shim 在**发生时**记下 | 被测系统的**行为** |

**规则**：`envelope` 由 harness 写（合法）；`declarations` 必须 agent（§4）；
**payload 的每一个叶子**在 `PAYLOAD_ORIGIN[stage]` 里必须有归属，**缺一个即 import 期 raise**
（与 `assert_taxonomy_total()` 同做法）。归属随 artifact 落 provenance。

### 5.3 S3 的归属表（示范；其余阶段同法逐叶子填）

| payload 叶子 | 归属 | 为什么不是别的 |
| --- | --- | --- |
| `factor_id` / `expression` | `verbatim_from_agent` | 是 agent 的表述，重算即改写 |
| `values_ref.{rows,n_dates,n_symbols,coverage}` | `recomputed_by_harness` | 从 `work/values.parquet` 可确定；让 agent 自报等于让它自己给自己打覆盖率 |
| `values_ref.sha256` | `recomputed_by_harness` | §9；与 gold 同一函数体 |
| `nonfinite.{inf_count,nan_count}` | `recomputed_by_harness` | 值序列里数得出来 |
| **`nonfinite.replaced_count`** | **`shim_emitted`** | **事后不可观测**（§8）：替换发生过的序列里恰好没有 NaN |
| `warmup.{first_valid_date,nonnull_before_warmup}` | `recomputed_by_harness` | 从值序列与日历可定 |
| `warmup.lookback` | `verbatim_from_agent` | 是 agent 的**参数选择**，不是观测量 |
| **`approximated_operators`** | **`shim_emitted`** | 只在**生成代码那一刻**可见；事后扫描永远得 `[]` |
| `degeneracy.is_constant` | `recomputed_by_harness` | 值序列上算得出 |
| **`degeneracy.alert`** | **`verbatim_from_agent`** | 这是 agent 的**报警行为**；代填它，`degeneracy_unreported` 探针量的就是我们自己 |

同一个 `nonfinite` 对象里三个键归属不同 —— 归属表的粒度必须是**叶子**，不是对象。

### 5.4 S7 / S8 的裁定

* S7 的 `metrics` / `attribution` / `ledger_check` → **`recomputed_by_harness`**，
  主表脚注写明：**S7 的这几族评的是被测系统的值序列与逐日台账，不是它的回测器**。
  这是一个必须公开写出来的口径限制，不是可以在实现里默默做掉的事。
* S7 的 `ledger_day` 逐日台账、S8 的 `events` / `fills` / `denied_requests` / `state_transitions`
  → **`shim_emitted`**。理由与 §8 同：**行为记录必须在发生时记**，事后重建就是伪造
  （卡 3.1 E13 已把「题面不得要求 agent 筛选自己的记录」定成规则，harness 侧的对应物就是这一条）。
* `provenance` 是**血缘声明**，归 `verbatim_from_agent` + harness 追加的 `FieldOrigin`，两段可分。

---

## 6. 身份三核（`identity.py`）

`check_identity()` 交叉核 **artifact 信封的 `(task_id, config_id, arm)`** 与 **runner 侧真值**：
compose 注入的 `GENEBENCH_TASK_ID` / `GENEBENCH_CONFIG_ID` / `GENEBENCH_ARM`（`c41/runner_core.py:100-102`）
× 该任务 X 面 `task.yaml`。

* 不一致 → `run_status = identity_mismatch`，`to_scorer_input` 返回 `None`；
* **不许静默改写成一致**。改写是最省事的做法，也是把「产物在伪装」变成「产物正常」的那一步。

**为什么这条不是冗余（记录性断言，已实测）**：绕过 `check_identity` 直接调
`artifact_schema.validate()` 时，`_log_slice` 按 **artifact 自报的** `task_id` 切片 ——
实测喂一条 `task_id="t-real"` 的日志、artifact 自报 `"t-fake"`：

```
_log_slice → []          actual_reads → set()
```

也就是说 `declared_reads` 这族探针**整体静默通过**。校验器侧已有
`envelope_task_id_mismatch`（`artifact_schema.py:580`）挡 `task_id`，但 **`config_id` 与 `arm` 没有对应检查** ——
这正是本卡要在 runner 侧补上的那一层。把 `config_id`/`arm` 的交叉核**下沉进卡 2.3** 的事
登记工单 **N-36**，本卡**不擅改冻结校验器**。

**源头注入落地后，本节降为第二道防线（但不取消）**：N-36 修的是**校验层**，
切片键的**源头**仍是 agent 自报的请求头（`gateway/app.py:82-83` 直接取
`x-genebench-task-id` / `x-genebench-config-id`，而这两个头由容器自己填，
`runner/c41/runner_core.py:317-319`）。卡 4.3 §6.5 把身份改由**代理边车**在网关入口注入 ——
剥掉客户端 `X-GB-*` 全类头、写入 runner 真值 `run_id`/`task_id`/`config_id`/`arm`，
切片键退化为 `run_id`。那条落地之后，**本节的三核从「唯一防线」降为「第二道防线」，
但不取消**：源头注入只保证**网关日志**这一条数据面可信，而 artifact 信封里的
`(task_id, config_id, arm)` 是 agent 写进产物的**另一条**，边车碰不到它；
三核比的正是这两条是否指向同一次运行。纵深防御，两道都留。

---

## 7. 可见性三态与日志切片契约（`visibility.py`）—— 必修项 3

### 7.1 三态

`load_gateway_log()`：

* 文件不存在 → **返回 `None`**，**绝不返回 `[]`**；
* 文件存在且零条 → `[]`。

**两稿在这一点上都对**（红队 rt18/rt36）：`None` = 不可得（跳过交叉核并标 unobservable），
`[]` = 可得但零请求（按 0 条核）。传 `[]` 会让 `declared_reads` / `fetch_clock` 这些交叉核**真空通过** ——
「什么都没有」与「这次没取数」在数值上不可区分。

`visibility()` 返回 `(gateway_log, unobservable_probes)`；后者进
`Verdict.mark_unobservable(probe, reason)`，卡 2.3 已保证 `unobservable ∩ gate_failed == ∅`
（`artifact_schema.py:1135`）。

### 7.2 补两稿都缺的第三维：**时间窗**

两稿的全部争论都停在 `None` vs `[]`，**都没有写时间窗**。而 `_log_slice`
（`artifact_schema.py:703`）只按 `(task_id, config_id)` 两维切：

```python
return [e for e in log if isinstance(e, dict) and e.get("task_id") == tid
        and (e.get("config_id") in (None, cid))]
```

同一个 task **重跑**、或日志**跨运行追加**，上一次 run 的条目会被算进这一次：
`actual_reads` 凭空变大、`fetch_clock` 凭空对上。这与稿乙自己发现的
「`starts != 1` 说明日志跨运行了」（`c41/runner_core.py:365`）**是同一个形状**，
只是那边发生在出向日志、这边发生在网关日志。

**切片契约必须是三重**：

```
(task_id, config_id, [run.started_at, run.finished_at])
```

时间窗取 runner 侧真值（`started_at` / `finished_at` 已在 `agent_result` 表里），不取 artifact 自报的
`produced_at` —— 自报值可被改。

**负例（`negctl_parser.py` NP-11）**：同一 task 两次 run 的日志拼在一起，
断言第二次 run 的 `actual_reads` **不含**第一次的条目。

### 7.3 跨机取回未定之前的处置

网关 `access_log` 在 f01，执行面在 f02，取回方案未定（工单 **T-13**）。
在它落地之前：**一律传 `None`**，并在主表脚注写明**哪几族在 v1 不可检**
（`declared_reads`、`fetch_clock`、`source_status`、`lookahead` 的日志侧结算）。
写 `[]` 省事、并且会让主表更好看 —— 这正是不能写 `[]` 的原因。

---

## 8. 调用点 shim（`emission.py`）—— 嫁接自稿甲，稿乙完全没有

### 8.1 协议

每个适配器配一个**进容器的发射 shim**，写 `out/emission.jsonl`，一行一 JSON：

```
kind ∈ {declaration, factor_values, signal_row, metric, ledger_day,
        fetch, nonfinite_replace, llm_call, loop_boundary, framework_error}
```

**parser 只读 `emission.jsonl`**，因而**框架无关**、可用夹具测试（这是 A 档能占 2/3 的前提）。

### 8.2 判别力：为什么没有 shim 就是假绿

两个具体的量：

* **`nonfinite.replaced_count` 事后不可观测。** 一个把 NaN 替换成 0 的实现，交出来的序列里
  恰好**没有 NaN** —— 事后扫描得到的永远是 `0`，而 `0` 与「真的没替换」**逐字节相同**。
  卡 2.3 的 `nonfinite_silently_replaced`（`artifact_schema.py:820`，probe=`nonfinite_propagation`）
  因此**永远不会响**。
* **`approximated_operators` 只在生成代码那一刻可见。** 事后扫描得到 `[]`，
  `operator_approximated` 探针同样永绿。

这两族探针在稿乙的方案下**存在但保护为零** —— 机制在，保护不在。

### 8.3 验收（A 档，夹具即可）

* **没有 `nonfinite_replace` 发射的 harvest，产出的 S3 payload 里 `nonfinite` 键必须不存在**
  → 卡 2.3 报 `s3_nonfinite_missing`（`artifact_schema.py:817`）；
  **不是**写 `{"inf_count":0,"nan_count":0,"replaced_count":0}`。
  写 `{0,0,0}` 是本卡最容易犯、也最难发现的错误：它让一次**没测到**看起来像一次**测过且干净**。
* shim 钩到 3 次替换 → `replaced_count == 3` 且 `gate_failed == ["nonfinite_propagation"]`。

---

## 9. 值序列的规范形（`adapters/values_io.py`）—— 必修项 5，两稿都错

### 9.1 gold 侧的口径（已核对 `genetask/templates/S3/*/solve.py`）

```python
out = values.reset_index().sort_values(["date", "code"])
out.to_parquet("work/values.parquet", index=False)
... "sha256": hashlib.sha256(open("work/values.parquet", "rb").read()).hexdigest()
```

即 **`values_ref.sha256` = `work/values.parquet` 的文件字节摘要**；
列 `date/code/value`，按 `(date, code)` 排序，`value` 为 float64，pandas 默认 `to_parquet`，`index=False`。
（`cor01_wq006_corr/solve.py:77-94`；`ops01_gtja012_vwap_audit/solve.py:10` 写着同一句口径。）

**两稿都错**：稿甲自造了一套**文本 canon**（按 `(date, symbol)` 排序、17 位有效数字、null 字面量、
`\n` 连接后 utf-8 sha256）—— 与 gold **必然失配**，而卡 2.3 只校验 64 位 hex
（`_sha()`，`artifact_schema.py:804`），**抓不到**；稿甲自己承认「gold 侧怎么算的我没找到」，
实际就写在模板里。稿乙则完全没有规范序列化这一节，两个适配器各自哈希会得到**两个根**。

**落法**：`adapters/values_io.py` **一处实现**「写 `values.parquet` + 取字节摘要」，
与 gold **同一函数体**（gold 侧改为 import 它，或本卡 import gold 侧的同名函数 —— 两处代码不得并存）。

### 9.2 补 gold 侧没解决的隐患：字节摘要不跨版本可复现

**已实测**：parquet 文件字节里嵌着 writer 版本串。本机（pandas 3.0.5 / pyarrow 25.0.1）
写一份两行的 `values.parquet`，字节里含：

```
"creator": {"library": "pyarrow", "version": "25.0.1"}, "pandas_version": "3.0.5"
parquet-cpp-arrow version 25.0.1
```

也就是说**换一个镜像、同一份值会得到两个哈希**，而卡 2.3 只查它是不是 64 位 hex —— 抓不到。
症状是 `values_ref.sha256` 与 gold 不等，**看起来像 agent 算错了值**。

**落法（四条，缺一不可）**：

1. **钉死 `pyarrow` 与 `pandas` 版本**（两个都嵌进字节，只钉 pyarrow 不够），写进两个适配器镜像的
   构建期依赖，并进 `upstream_pins.py`（§10）；
2. **钉死写参数**：`compression` / `version` / `write_statistics` 显式给值，不吃默认；
3. **import 期已知向量 roundtrip 断言**：一份写死的两行 DataFrame → 期望 sha256 常量，不等即 `raise`；
4. gold 侧同样跑这条断言（同一函数体，自动成立）。

第 3 条是这一节的真正保险：它把「跨版本不可复现」从一个**跑通了才发现**的问题，
变成一个 **import 就炸**的问题。

---

## 10. 上游钉死（`upstream_pins.py`）—— 嫁接自稿甲

```python
@dataclass(frozen=True)
class Pin:
    repo: str
    commit: str                 # 40 位 hex，**不得留空**
    required_attrs: tuple[str, ...]
    required_files: tuple[str, ...]
    required_state_keys: tuple[str, ...]

PINS: dict[str, Pin] = {...}    # "rdagent_q" / "tradingagents"
```

`assert_upstream_shape()` 由**两个 adapter 模块在模块级**调用。

**目的**：上游改一个字段名，我们要炸在 **import**，不要炸在
「**这个 harness×model 做不了 S3**」这条**会被写进论文**的结论里。
后者是最贵的失败：它不报错、有数字、方向一致，而且看起来像一个发现。

**落地第一步（B 档前置）**：在 f02 跑 `probe_shapes()`，把 TradingAgents 的 `final_state` 键、
RD-Agent 的产物文件名与 conf 键**实测打印**出来再填。**不许凭记忆填**，
不许留空 commit —— 空 commit 让整条断言退化成「有这个仓库就行」。

---

## 11. 数据面

### 11.1 RD-Agent(Q)：网关 snapshot → qlib provider 适配层

按签字人已定的路：`materialize(work, gw)` 把网关 snapshot 落成 qlib provider 树
（`calendars/` `instruments/` `features/`），**全部落在 `tasks/<id>/work` 下**。
**明确否决稿甲的宿主挂载方案**：无宿主 bind-mount、无 NFS（卡 4.1 FS-1/FS-2 与本卡硬约束）。

**钉法用稿乙的 P1/P2 两分 —— 合成一条就退化成空检查：**

| | 做什么 | 抓什么 |
| --- | --- | --- |
| **P1** | `read_baked_pin()` 读镜像构建期烘进去的 provider manifest sha256 根，过 `genetask/schema.py::check_provider_pin`（冻结值 `54fdda39…`）| 「这个镜像是**对着哪份 provider** 构建的」 |
| **P2** | `spotcheck()` 拿**构建期导出的 n 行**与**运行期经网关取到的**逐字段对 | 「运行期拿到的数**真的是**那份 provider 的数」 |

把 P1/P2 合成一条，就变成「冻结值与冻结值比」—— 一个恒真的空检查。

* **P1 三支齐了才允许把 `ops/capabilities.json` 的 `provider_sha256_pinned` 翻绿**：
  正确值通过 / **改一个字符必须红** / **缺失必须红**。`check_provider_pin` 的三个分支
  （空、前缀不符、通过）正好一一对应，测试逐支覆盖。
  现值 `provider_sha256_pinned: false`，翻绿要有测试记录（同 N-33 做法）。
* **P2 的报错里直接给比值**：量纲错的典型表现是 **≈1000×** 或 **≈100×**
  （社区口径 `amount` = 千元、`volume` = 手）。只报「不相等」等于让人自己去猜是精度还是量纲。

**读取钩子（嫁接稿甲）**：`materialize` 与 provider 读取入口装 `install_read_hook()`，
在**读发生时**写 `provider_reads.jsonl`，翻成 `access_log` 形状（**必须带 `backend` 字段标注来源**）
供 `declared_reads` 交叉核使用。

> **parser 禁止事后合成任何一条日志。**
> 负例 NP-23：喂一条源 journal 里不存在的条目，必须 `raise`。
> 这条与 §1 的「切片 ≠ 合成」是同一条纪律；缺了它，`declared_reads` 探针可以被 harness 自己喂饱。

### 11.2 TradingAgents：原生数据源整体替换

原生 `yfinance` / `finnhub` / 新闻源**整体替换**为经网关的实现。

* `assert_no_native_data_path()` 做**源码级扫描**（模块级调用，随适配器 import 跑）；
* 保留稿乙的**黑掉网关对照**：把网关设为不可达，**若仍能产出完整 artifact**，即判
  **「存在未声明的数据源」** —— 这次运行的 as-of 强制**当场作废**。

后者比源码扫描强：源码扫描只能查我们**想到要查**的模块名，黑掉网关查的是**结果**。
两者都要有，理由与 P1/P2 同 —— 一个查「配置对不对」，一个查「行为对不对」。

---

## 12. 禁 best-of-N（`select_loop.py`）—— 嫁接自稿甲，稿乙完全没有

RD-Agent 天生跑 N 轮。

```python
select_loop(h, rule)   # rule ∈ {"first_completed", "last_completed", "index:<k>"}
```

* **`rule` 只能来自 taskspec**，非法即 `raise`；
* 选中的 `index` 进 `provenance`。

**缺了这条会怎样**：适配层「取最好那轮」等于给被测系统加了一层**题目没给的搜索预算**，
harness×model 的可比性**当场作废**，而且**没有任何信号会红** —— 分数只是更高一点。
这与卡 4.1 §4 的知识截止日期同类：**与被测变量同向的系统性偏差**，它不把结果打散，它把结果排好序。

**验收（A 档，夹具）**：同一份 3 轮夹具上，`first_completed` 与 `last_completed` 选出的 `index`
**必须不同** —— 证明规则真在起作用，而不是两条路都返回同一轮（那样测试恒绿）。
这是 `packager.assert_mutated()` 同一条教训的第二次应用：**不是产物静默错，是测试静默空**。

---

## 13. 遥测与落库（`telemetry.py`）

### 13.1 `record_strict()`

**实测**：现行 `c41/runner_core.py:278` 的 `record()` 是

```python
row = {k: v for k, v in kw.items() if k in cols}
```

—— **未知键静默丢**。拼错一个列名，那个数就永远是 NULL，没有任何东西报错。

`record_strict()`：**任一未知键即 `raise`**，报文里指名是哪个键。

### 13.2 `assert_columns_cover()`

保证 `RUN_STATUSES` / `HARNESS_FAULTS` / `SR_BUCKETS` 的**每一个名字都有列可落**；
删任一列必须 `raise` 并**指名是哪个状态没了落点**（不是笼统的「列不全」）。

### 13.3 `MIGRATION_C42` 补列

* 分类三列：`run_status` / `harness_fault` / `sr_bucket`；
* 泄漏单列：`leaked`（bool）+ `leak_hits`（脱敏后的 `token_sha256_8`+`offset` 列表，见 §14）；
* 可见性：`gateway_log_state` ∈ {`unavailable`, `empty`, `sliced`}；
* 选轮：`loop_rule` / `loop_index`；
* 上游：`upstream_pin_id`；
* **接上 4.1 建了没填的四列**：`tokens_in` / `tokens_out` / `cost_usd` / `steps`
  （DDL 里已有，`run_task` 从没写过值）。

### 13.4 自报用量必须有网络侧佐证（嫁接稿甲）

`tokens_in + tokens_out > 0` 时，出向日志里 `event == "connect"` 的条数**必须 > 0**，
否则 `raise telemetry_unbacked`。

**只能做非零一致性核，不能做数值核**：代理看不到 TLS 里面，条数与 token 数之间没有可核的换算。
这条抓的是「框架自报了用量，而这次运行根本没连过模型 API」——
那意味着用的是缓存、是 mock，或者根本没跑，三种都不该进主表。

### 13.5 三个冻结字段的 null 语义

`search_count` / `trial_family` / `cash_ratio_median` 给不出时写 `null`，
**同时落一列 `telemetry_source`** ∈ {`framework`, `shim`, `unavailable`}。

理由：只写 `null`，「有搜索但我们没记」与「确实没有搜索」**不可分** ——
和 §7 的 `None` vs `[]` 是同一个洞，只是落在遥测列上。

---

## 14. 金丝雀（`canary_scan.py`）

### 14.1 扫描面（取稿乙的分面清单）

按格式正则扫 **agent 可写的全部字节面**：

```
artifact.json、work/**、stdout **全文**、stderr、log/egress.jsonl、
out/emission.jsonl、框架自己的转写与 reports/**
```

**stdout 必须是全文，不是 `markers` 的 300 字符尾**（`c41/runner_core.py:376` 现在只留
`r.stdout[-300:]`）—— 泄漏串出现在第 12 行的运行，尾巴里什么都没有。

### 14.2 处置

命中 `gold_token` / `x_token` → **run 级 `leaked`**，**单列、不算分、不进 `gate_failed`**
（卡 3.1 §5 已定；`gate_failed` 是探针族语义，泄漏不是探针）。

### 14.3 非空证明（接力不断链）

同一次扫描里 **`control_token` 必须恰好命中 1 次** —— 与
`genetask/packager.py::check_export` 的 **C1** 同判据（那里核的是两臂题面各恰 1 次）。
扫不到即 `raise`「**扫描器在扫空**」，那次扫描的「零命中」不作数。

这是把 3.1 的非空证明**接力**到 runner 侧：C1 证明串进了题面，本条证明串到了容器里、且我们扫得到它。
中间任何一环断了，`leaked=0` 就不再是证据。

### 14.4 脱敏

只落 `token_sha256_8` 与 `offset`。**验收**：`results.sqlite3` 与宿主日志**全文搜原文须零命中** ——
否则金丝雀本身变成了泄漏面。

---

## 15. 出向白名单同源（`registry.py` × `c41/egress_proxy.py`）

`MODEL_API_ALLOW` 由 `registry.collect_egress_hosts()` **生成**，而不是手抄。

`test_allowlist_matches_registry()` 三条断言：

1. 键集**相等**（不是包含）；
2. 每条的**引用者非空**；
3. **无一条落在 `BUILD_TIME_ONLY`**。

后两条 `c41/egress_proxy.py::assert_allowlist_sane` 已经在 import 期跑；本卡加的是**第一条**——
「白名单与被测配置注册表同源」。

**现表两条**（`api.anthropic.com` / `api.openai.com`）引用者都写着「待 M6 复核」（N-32），
本卡按注册表补齐为真实配置 id。

> **行情 / 新闻源一律不得入表。** 放进去等于让被测系统**绕过数据面取数** ——
> 网关 `access_log` 会干干净净，卡 5.1 的前视探针全绿，而 as-of 强制已经失效（卡 4.1 §3.1 的形态）。
> 这条写进 `assert_allowlist_sane` 的第三类绊线，与 `BUILD_TIME_ONLY` 并列。

---

## 16. 出口纪律（`scorer_io.py`）

### 16.1 `to_scorer_input()`

**非 `None` 当且仅当 `run_status == "ok"` 且非 malformed。** 其余一切结局返回 `None`。

**且任何地方不得出现非空 `gate_failed`。**
—— 禁止为结构性失败伪造闸门。伪造的后果：「**没交产物**」与「**有前视违例**」
在主表上变成同一个数，而这两件事的含义相反（一个是能力不足，一个是行为违规）。

### 16.2 `gate_only()`

产出 `gate.json`，它**必须通不过** `validate_scorer_output()` —— codes 含
`correctness_missing`（`artifact_schema.py:1141`）。这是刻意的：`gate.json` 是**半成品**，
它进不了主表这件事要由校验器说，不由约定说。

补齐 correctness 之后：

* `anchor_status == "pending"` 时须 `effect = None` + `effect_withheld_reason = "anchor_pending"`
  （`artifact_schema.py:1153-1160`）；
* `anchor_status == "fixed"` 时须报 `effect_missing_on_valid`（:1166）。

**卡 5.4 落地时这条测试要翻转，翻转必须留记录**（同 N-33 / `anchor_ladder_54` 做法）。

---

## 17. 双臂差异断言 —— 必修项 4，两稿都没有

### 17.1 问题

两稿都只把 `arm` 当成一个**透传字段**和一致性核对项。但第三方框架自带**大量 system prompt**
（TradingAgents 是多智能体辩论，题面只进其中一个槽），两臂之间框架自身的提示**完全相同** ——
strict 臂的协议要求可能被**稀释到无差别**。

稿甲的 A16 只验了「题面逐字送达、`control_token` 恰 1 次」，**没验两臂之间确实不同**。

缺了它，**「协议臂没效果」这条结论会被写进论文**，而真实原因是**协议根本没进到模型眼前**。
这是本卡里失败代价最高的一条：它不会让任何测试变红，它会让整篇论文的中心结论变成一个 artifact。

### 17.2 断言

同一 task 两臂各跑一次，采集**外发 prompt 全集**（经 §8 的 `llm_call` 发射记录），做 diff：

```
diff(prompts_strict, prompts_open) == INSTRUCTION 差异 ∪ 协议工件
```

* 差异集合 **= 且仅 =** 两臂 INSTRUCTION 的差异（加上协议工件）；
* **两臂外发 prompt 逐字节相同 → 直接判失败**（这是「稀释到无差别」的观测形态）。

### 17.3 边界

本卡**不改题面**（卡 3.1 E1–E13 保证等价，4.3 不得在注入期改写）。
本条只**观测**，观测结果若为「无差别」，处置是**回退给卡 4.3 改注入位置**，
不是在 4.2 里给 strict 臂加东西。

---

## 18. 排期约束与降级验收 —— 必修项 6

### 18.1 依赖

本卡的核心规则「适配层永不代写 declarations」（§1，这条对且必须坚持）有一个**直接后果**：

> 两个框架的**原生产物里根本没有 `declarations`** → artifact 必然 malformed → SR 失败。

于是「产出可评分 artifact」这条验收，在**卡 4.3 把 artifact 契约注进 agent 之前不可能达成**。
稿甲把它挂在 open question 里、稿乙干脆没提，**两稿却都在验收里写了 S3 冒烟绿灯**。

### 18.2 降级验收（本卡实际要做的）

4.2 先用 `genetask/packager.py::null_artifact()` 的**桩 agent** 打通
「采集 → 分类 → 落库 → 出口」全链路，并验判别力。**已实测**的两个行为与它们的 codes：

| 桩行为 | 卡 2.3 findings（实测） | 本卡断言 |
| --- | --- | --- |
| `empty` | `declarations_missing` | `run_status == "malformed"`，`sr_bucket == "malformed"`，`to_scorer_input() is None` |
| `default_fill` | `silent_completion` + 一串 `s3_*_missing` | `silent_completion` 必须在 findings 里；`gate_failed == ["underdetermined"]` |

> **口径修正**：综合稿写的是「`empty` 必须报 `underdetermined_field_missing`」。
> 实跑不是 —— `empty` 连 `declarations` 键都没有，校验器在更外层就停在 `declarations_missing`。
> `underdetermined_field_missing`（`artifact_schema.py:647`）要在「有 declarations、但欠定字段缺键」时才出。
> 本卡按**实测 codes** 写验收，并另加一个第三桩 `default_fill_minus_probe`（declarations 齐、
> 只把欠定字段的键删掉）专门覆盖 `underdetermined_field_missing`，让 §4 规则 (b) 有对应的正例。

### 18.3 验收文本的措辞要求

真实框架的 S3 冒烟绿灯**延后到 4.3 之后**，且验收文本里必须写明：
**这次绿灯证明的是链路，不是模型。**
不写这句，半年后没人分得清那条绿灯当时证明了什么。

---

## 19. 验收（分档，两稿都没分档）

### 19.1 A 档：零外部依赖、纯夹具，**必须先全绿**

夹具用**录制的真实产物片段**，不用手写理想夹具 —— 手写夹具会把 parser 测成永绿
（它只会遇到我们想象得到的形状）。

| # | 条件 | 出处 |
| --- | --- | --- |
| A-01 | `assert_taxonomy_total()` 四条恒等式；`RUN_STATUS_TO_SR` 全映射 | §2 |
| A-02 | 优先级 `rank()` 在 `RUN_STATUSES` 上双射；`leaked` 压一切 | §2 |
| A-03 | `sr_denominator()` 只排除 `unscorable_harness`（多排一个桶必须红）| §2 |
| A-04 | `test_harvest_order` monkeypatch 序列逐项相等；`harvest` 早于 `down -v` | §3 |
| A-05 | 产物落在 `/task` 之外 → `framework_output_outside_task_mount` | §3.3 |
| A-06 | `$.declarations.*` 非 `agent_artifact` 即 raise（反向用例喂坏输入）| §4 |
| A-07 | `Source.absent` 一个键都不写；`harness_inferred` 即 raise；不代写 `UNRESOLVED` | §4 |
| A-08 | `framework_config` 读数只进 provenance，不进 declarations | §4.3 |
| A-09 | `PAYLOAD_ORIGIN[stage]` 覆盖每个叶子，缺一即 import 期 raise | §5 |
| A-10 | `degeneracy.alert` 归 `verbatim_from_agent`（代填即 raise）| §5.3 |
| A-11 | `check_identity()` 三核；不一致 → `identity_mismatch` + `to_scorer_input() is None`；**不改写** | §6 |
| A-12 | 记录性断言：绕过身份核时 `_log_slice → []`、`actual_reads → ∅` | §6 |
| A-13 | 日志文件不存在 → `None`（返回 `[]` 即红）；`[]` 与 `None` 走不同分支 | §7.1 |
| A-14 | 三重切片：两次 run 的日志拼接，第二次 `actual_reads` 不含第一次条目 | §7.2 |
| A-15 | 无 `nonfinite_replace` 发射 → payload **无** `nonfinite` 键 → `s3_nonfinite_missing` | §8.3 |
| A-16 | shim 钩 3 次 → `replaced_count == 3` 且 `gate_failed == ["nonfinite_propagation"]` | §8.3 |
| A-17 | `values_io` 与 gold 同一函数体；import 期已知向量 roundtrip 常量断言 | §9 |
| A-18 | `select_loop` 非法 rule 即 raise；3 轮夹具上 first ≠ last | §12 |
| A-19 | `record_strict` 未知键即 raise；`assert_columns_cover` 删列必须指名 | §13 |
| A-20 | `tokens>0` 而 `connect==0` → `telemetry_unbacked` | §13.4 |
| A-21 | 扫描器 `control_token` 恰 1 次，否则 raise「扫描器在扫空」；脱敏后全文搜原文零命中 | §14 |
| A-22 | 出口纪律：非 ok 一律 `None` 且 `gate_failed` 为空；`gate.json` 必须报 `correctness_missing` | §16 |
| A-23 | 三桩 agent（`empty` / `default_fill` / `default_fill_minus_probe`）的 codes 与 §18.2 表逐条相符 | §18 |

**共 23 条。A 档不过，B 档不开工。**

### 19.2 B 档：需容器与镜像构建面

**B 档开工前必须先过 §21 的 T-16 那道门**（f02 到底有没有容器运行时与构建面）。

| # | 条件 |
| --- | --- |
| B-01 | `bundle → compose` 全流程，lint 九条全过 |
| B-02 | 超时路径走 `try/finally`，`docker compose ls` 无 `gb-<task_id>` 残留 |
| B-03 | 越权分类：`lint` / `bundle` / `provider_pin` / `egress_starts` / `docker_up` / `runtime_dependency` / `stale_state` 七种 harness fault 各造一次，都落 `harness_error` 且 `harness_fault` 列取值正确 |
| B-04 | 黑掉网关对照：TradingAgents 在网关不可达时**不得**产出完整 artifact |
| B-05 | provider **P1**：正确 / 改一字符 / 缺失三支齐 → 才允许翻绿 `provider_sha256_pinned` |
| B-06 | provider **P2**：`spotcheck()` 逐字段对，报错含比值 |
| B-07 | 两个适配器的 S3 冒烟（**延后到 4.3 之后**，见 §18.3） |
| B-08 | 双臂 prompt diff 断言（§17），两臂逐字节相同即失败 |

### 19.3 负例对照 `ops/negctl_parser.py`

**判据**：**每个负例必须被它自己那条判据拦下** —— 沿用 `c41/negctl_lint.py` 的做法
（`hit = [v for v in found if v.startswith(want)]`，串号即失败），**不是** `bool(found)`。
只要求「全红」是不够的：一个负例若因**别的**判据红，被测的那条其实是空的。

| # | 负例 | 期望判据 |
| --- | --- | --- |
| NP-01 | `declarations` 里有一个 harness 写的键 | origin(a) |
| NP-02 | `FieldOrigin` 出现 `harness_inferred` | origin(c) |
| NP-03 | harness 代写 `UNRESOLVED` | origin(d) |
| NP-04 | `Source.absent` 却写了键（值 `null`） | origin(b) |
| NP-05 | `conf.yaml` 读数进了 `declarations` | §4.3 |
| NP-06 | `harvest` 排在 `down -v` 之后 | 顺序断言 |
| NP-07 | 产物落在 `/task` 挂载之外 | `framework_output_outside_task_mount` |
| NP-08 | 超时路径跳过 `down -v` | 残留断言 |
| NP-09 | 信封 `config_id` 与注入值不符 | `identity_mismatch` |
| NP-10 | 日志文件不存在却返回 `[]` | 三态断言 |
| NP-11 | 两次 run 日志拼接 | 三重切片 |
| NP-12 | 无发射却写 `nonfinite = {0,0,0}` | `PAYLOAD_ORIGIN` |
| NP-13 | 值序列用文本 canon 算 sha | `values_io` 同源断言 |
| NP-14 | pyarrow / pandas 版本漂移 | roundtrip 已知向量 |
| NP-15 | 上游 commit 留空 / `final_state` 键改名 | `assert_upstream_shape` |
| NP-16 | `select_loop(rule="best")` | rule 来源断言 |
| NP-17 | `record_strict` 传未知键 | `record_strict` |
| NP-18 | 删掉 `sr_bucket` 列 | `assert_columns_cover`（须指名） |
| NP-19 | `control_token` 零命中 | 扫描器非空证明 |
| NP-20 | `tokens>0` 而 `connect==0` | `telemetry_unbacked` |
| NP-21 | 为 `no_artifact` 伪造 `gate_failed` | 出口纪律 |
| NP-22 | provider sha 改一字符 | `check_provider_pin` |
| NP-23 | parser 事后合成一条 `provider_reads` 条目 | 禁合成 |
| NP-24 | `MODEL_API_ALLOW` 手抄多一条 | 注册表相等 |
| NP-25 | 网关黑掉仍产出完整 artifact | 未声明数据源 |

**共 25 例（要求 ≥18）。REVERSE ≥2**：R-1 只改注释、R-2 加一个无关文件 —— **必须仍 ok**。

---

## 20. 已知边界

1. **网关日志跨机不可得（v1）。** T-13 落地前，`declared_reads` / `fetch_clock` / `source_status` 与
   `lookahead` 的**日志侧**结算一律 `unobservable`，主表脚注列名。**不得**用 `[]` 冒充。
2. **金丝雀只抓文件级搬运。** 转格式（parquet → CSV / JSON 重序列化）会丢 metadata，
   `leaked == 0` **≠ 无泄漏**（卡 3.1 §5 已定，本卡继承）。内容级泄漏靠 oracle 不进容器 + 0700 守。
3. **`telemetry_unbacked` 只能做非零一致性核。** 代理看不到 TLS 内部，token 数与连接数之间没有可核换算。
4. **S7 的 metrics 族评的是被测系统的值序列与台账，不是它的回测器**（§5.4）。这是口径限制，写进主表脚注。
5. **`provider_reads.jsonl` 不是网关 `access_log`。** 它是 provider 侧的读，`backend` 字段标注来源；
   两者合起来才覆盖完整（与卡 4.1 §3.5 的「数据面 + 网络侧」同结构，本卡是第三个面）。
6. **双臂 prompt diff 依赖 `llm_call` 发射。** 框架若在 shim 之外发起调用（如自带的重试路径），
   这条断言看不到那次调用 —— 边界写进 §17，B-08 的绿灯是 `partially_verified`。
7. **模型知识截止日期这条前视通道本卡管不到**（卡 4.1 §4 / N-31），归卡 3.2 与 5.1 的记忆探针。
8. **`values_ref.sha256` 只在两个适配器与 gold 用同一份 `values_io` 时可比。**
   任何第三方直接调 `to_parquet` 的路径都会破坏它 —— 因此 §9 要求两处代码**不得并存**。

---

## 21. 待批事项（**登记，不执行**）

按硬约束：凡要改既有系统的事项，写进 `ops/tickets.md` 待批，本卡不动手。

| # | 事项 | 为什么它阻塞了什么 | 建议动作 |
| --- | --- | --- | --- |
| **T-13** | **网关 `access_log` 跨机取回** | 日志在 f01、执行面在 f02。取不回来 → §7.3 一律传 `None` → 四族探针在 v1 不可检，主表要写脚注 | 只调研落点与取回方式（拉 / 推 / 只读挂载），**不改网关** |
| **T-14** | **给网关加 provider digest 只读路由** | §11 的 P1 现在只能读镜像里烘的 pin，没有运行期第二源。`ALLOWED_ROUTES` 是**启动即断言的闭集**，加一条属**改既有系统** | 写清路由形状与返回体，等批 |
| **T-15** | **把 `config_id` / `arm` 交叉核下沉进卡 2.3**（**N-36**） | 校验器现在只核 `task_id`（`artifact_schema.py:580`），`config_id`/`arm` 不符时 `_log_slice` 仍按自报值切 —— 本卡在 runner 侧补了，但校验器侧的洞还在 | 登记为卡 2.3 的 malformed code，**不擅改冻结校验器** |
| **T-16** | **f02 容器运行时与镜像构建面确认**（**B 档前置门**） | 见下 | 先实测，再排期 |

### T-16 展开：这是本卡最大的一处未验证前提

两稿都把「`docker compose` 可用、镜像可构建」**当既定事实**往下写了十几个模块。
而两台内网机的既有记录是：**没有容器运行时权限，docker 根本没装，f02 敲 `lxc` 会触发 snap 安装**。

同时硬约束又要求**依赖必须在构建期装**（运行期装是 lint 红，卡 4.1 L-8），
而两个适配器镜像要装 **qlib** 与 **LangGraph 全家桶** —— 构建期需要联网、需要构建机权限。
稿甲把它列为 open question 但**没给「拿不到怎么办」**，稿乙**连提都没提**。

**处置（已写进本卡结构）**：

1. **开工单实测**：容器运行时是否可得？`docker.io` 可达性（既有记录是被墙且没有镜像构建器）？
   构建面在哪台？—— 三个问题各要一段实跑取证，不接受推断。
2. **验收拆档**：A 档（§19.1，23 条，零外部依赖）**先落地**，占全部验收的约 2/3；
   B 档（§19.2）等这道门。

**不这么做的后果**：会做出一整套**无法验收**的代码 —— 写完了、看起来对、没有任何东西能证明它对。
