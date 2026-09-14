# GeneBench 主表口径 v1（十九列逐列）

> **谁该读这一页**：红队（判「这张表能不能绕」）与外部读者（判「这个数说的是什么」）。
> 规格原文在 `ops/specs/GeneBench指标规格_v1.md`（§9 是登记表，§0–§8 是设计稿）；
> 实现在 `scorer/report.py`（`MAIN_TABLE_COLUMNS` / `main_table()`）与 `ops/mk_tables.py`。
> 这一页只做一件事：**把主表的十九列一列一列讲清楚**。

出表：

```
python ops/mk_tables.py --table main --format csv   --filter batch=<批次>
python ops/mk_tables.py --table main --format md    --filter set_version=1.0.14
python ops/mk_tables.py --table main --format latex --filter batch=<批次>
```

---

## 0 先看这三件事

### 0.1 主表**没有总分**（取消聚合，⑪）

v1 不出总分（2026-09-10 用户裁定 ⑪）。没有任何一列把多阶段合成一个数，
也没有任何一列是「加权平均」。**逐指标按各自的闸门条件读** —— 闸门条件写在下面每一列里。

理由不是审美：把 S1 的覆盖率和 S7 的回测复现带加权成一个数，权重就得有出处，
而我们没有那份出处。一个没有出处的权重会决定谁排第一 —— 那比不排名更糟。

效果分的归一值（`effect` = `100 × (被测 − null 底) / (oracle 顶 − null 底)`）
**照旧逐 run 落在结果库**（`ops/results_db.py`），只是不进主表与全量指标表。
想看它的人查库，不在发布表上读到一个看起来可比、实际锚点还没铺完的分数
（替换基线阶梯卡 5.4 未落地，`anchor_ladder_54 = false`）。

### 0.2 一格里可能写四种东西

| 写法 | 含义 | CSV | Markdown | LaTeX |
| --- | --- | --- | --- | --- |
| 数值 | 测到了 | `0.5` | `0.5` | `0.500` |
| `—`（U+2014） | **没有读数**：这一格的 run 全部落在「拒绝 / 诚实终止 / 未结算 / 预算截断」四类里 | `—` | `—` | `---` |
| `unobservable` | **检不了**：有可用的 run，但这个量在这些 run 上测不出来 | `unobservable` | `unobservable` | `\textit{unobservable}` |
| 空 | 这一格**一个 run 都没有**（该配置该臂在这一阶段一道题都没跑） | （空） | （空） | `---` |
| `n/a` | **不适用**：这个量在这一阶段根本不定义。**主表上不会出现**（十九列每一列都在它自己的阶段切片上取数），只出现在全量阶段宽表上 —— 见指标规格 §9.0 | `n/a` | `n/a` | `\textit{n/a}` |

**`0` 不是其中之一。** `0` 只能是「测了，是零」。这条不是讲究：把「检不了」写成 0，
一个恒绿的门与一个真的零命中在表上就长得一模一样，而恒绿的门与恒红的一样会被绕过。

**LaTeX 上 `—` 与「没有 run」都写 `---`**（booktabs 里没有第二种空格）。要分开看 CSV 或 md。
这是个已知的、故意留下的糊点，不是 bug —— 论文表上需要区分时，把那一行的样本量
（`n_runs` / `n_tasks`）一起放出来。

### 0.3 四类「没有读数」分别是什么

判定顺序即优先级（`scorer/report.py::withheld_reason`）。
**先过一道短路**：闸门 `valid` 且 `l3_pass` 有值的 run **给得出读数**，不属于这四类中的任何一类
（哪怕它路上撞过预算闸）。

1. **诚实终止** `honest_halt` —— 题面欠定某项金融要害语义，产物如实标 `unresolved` 并停下。
   **这不是失败**：协议 §3.1 要的就是这个行为，`P@1` 把它算成功。
   **判在最前**（2026-09-11，红队 V2.rt finding 1）：诚实终止的 run 往往**同时**带一条预算记录 ——
   它把预算用到闸上才如实停下。先判预算的话，全库唯一一条真诚实终止会被判成预算截断，
   于是 `honest_halt_rate` 这一列结构上恒为 0；而一个永远为 0 的列，看不出是恒绿还是真零。
2. **预算截断** `budget_exhausted` —— 边车真的发过 429（记录里的 `budget`）。
   **判在拒绝之前**：撞闸的 run 多半没交产物，不先判它就会被算成「拒绝」。
3. **拒绝** `rejected` —— 闸门判 `invalid`（探针命中或结构畸形），或压根没有可评分产物
   （交白卷 / harness 自己坏掉）。
4. **未结算** `unsettled` —— 有可评分产物、闸门也过了，但判据在 v1 没有输入
   （`l3_pass is None`）。**这说的是我们缺判据，不是被测方不行。**

---

## 1 十九列逐列

约定：**分母**一律只排除 `unscorable_harness`（`runner/c42/failure_modes.py`）——
harness 自己坏掉的 run 不进分母，否则「harness 越不稳，指标看起来越好」。
正确性量只取**闸门过了**的 run（闸门失败时效果分不产出，不是低分）；
探针态与越权率取全部 run（它们是 L1 事实，跟闸门过没过无关）。

### 1–3 全阶段三列

| # | 列 | 定义 | 数据源 | 闸门条件 | 不可得时 |
| --- | --- | --- | --- | --- | --- |
| 1 | `SR` | 存在可评分终端产物的比例；任务内对种子取均值，再对任务宏平均 | `record.sr_bucket` | 无阈值。两个臂并排读；单独一个 SR 不说明任何事 | 四类原因 → `—`；无 run → 空 |
| 2 | `P@1` | `mean_t mean_s succ`，succ = 闸门 `valid` ∧ L3 通过；诚实终止题按 `correct_handling` 记成功 | `record.validity` / `l3_pass` / `correct_handling` | 未结算的 run **既不进分子也不进分母** —— 单列在全量 agent 表的 `unsettled_runs` 里。一条都判不了的题不进均值（**不是记 0**） | 同上 |
| 3 | `$` | 每 run `cost_usd` 的均值 | `runner/pricing.yaml` × 网络侧 usage（边车 llm trace） | 不判 | 缺价或缺 usage → **空**。这一列**不套 `—`**：一次被拒的运行照样花了钱，把它的成本写成「没有读数」是错的 |

> **`$` 是成本上界，不是账单实数。** DeepSeek 分高峰 / 低谷两档而边车不记落在哪一档，
> 价目表取高峰价。要账单请查服务商侧。

### 4–5 S1（信息获取）

| # | 列 | 定义 | 数据源 | 闸门条件 | 不可得时 |
| --- | --- | --- | --- | --- | --- |
| 4 | `Cov` | 获取字段 ∩ 要求字段 / 要求字段。**要求字段取 gold 的 `fields_obtained`** —— 不取产物自报的 | `scorer/l3.py::compare_cov` | `Cov = 1` | 空 |
| 5 | `Prov` | 产物申报的每一次取数里，能在**网关日志**里找到同端点同时刻那条的占比 | 网关 access_log + 产物取数台账 | `Prov = 1`（日志可得时） | 日志不可得、或产物没有取数台账 → `unobservable` |

> `Prov` 是规格 §1「验行为不验申报」的落点之一：它比的不是「产物说它引用了什么」，
> 而是「网关那边有没有这一条」。日志不可得时它必须是 `unobservable` 而不是 1 ——
> 「我们看不见」不能读成「它是干净的」。

### 6–7 S2（数据对齐）

| # | 列 | 定义 | 数据源 | 闸门条件 | 不可得时 |
| --- | --- | --- | --- | --- | --- |
| 6 | `Align` | 映射到金标 schema 的字段正确率 | `scorer/l3.py::compare_align` | `Align = 1` | 空 |
| 7 | `Adj` | 申报的复权口径与任务声明一致（**指纹法**核验实际口径，见规格 §1） | 同上 | `Adj = 1` | 空 |

> S2 的判据不止这两列：`Cal ≥ 0.99` 与 `CellAgree ≥ 0.999` 同样进 `l3_pass`，
> 只是主表每阶段只放两列。全量阶段指标表里四列都有。

### 8–9 S3（因子实现）

| # | 列 | 定义 | 数据源 | 闸门条件 | 不可得时 |
| --- | --- | --- | --- | --- | --- |
| 8 | `Fid` | 逐日截面秩相关 `≥ τ` 的交易日占比（`fid_day_rate`）。分母取 **gold 侧可比交易日数**，不取共同天数 —— 只交一天也能拿 1.0 是旧写法的洞 | `scorer/l3.py::compare_tau` | 判据落在同一族的 `rho_p10 ≥ τ` 且 `day_coverage ≥ 1`；τ = `snapshots/v1/calibration.json` 的 `tau.value` | 空 |
| 9 | `Decl` | **契约必填声明完整率**：该阶段 `declaration_fields(stage)` 里「如实给出」的字段占比 | `scorer/l3.py::declaration_metrics` | 期望 1。`< 1` 说明有金融要害语义没申明 —— 协议总则「不得经隐式默认或推断补全」的可测形态 | 产物没有 `declarations`（畸形），或记录由早于 v1.0.14 的 scorer 结算 → `unobservable` |

> **「如实给出」的三条**（缺一不算）：① 键在 `declarations` 里且值不是 `null`；
> ② 值是 `unresolved` 时，**本题必须确实欠定该字段**（`task.underdetermined`）——
> 题面给了却标 `unresolved` 是乱标，不计分子；题面真欠定而如实标出，**计入分子**
> （把它记 0 等于罚诚实）；③ 有限枚举字段的取值必须在枚举内。
>
> `Decl` 是**跨阶段**可算的，主表按裁定 ⑩ 放在 S3 这一列；八个阶段各自的值在全量阶段指标表里。

### 10–11 S4（因子评价）

| # | 列 | 定义 | 数据源 | 闸门条件 | 不可得时 |
| --- | --- | --- | --- | --- | --- |
| 10 | `IC-agr` | IC 族指标落在 ε 带内的占比（`within_band_rate`） | `compare_epsilon` + `calibration.json` 的 `epsilon.ic_family.by_holding_period` | `= 1`，且 `max_band_ratio ≤ 1` | 没有可用 ε 档（例如 `positive_ratio` 的标定状态是 `implausible_stop_and_report`）→ `unobservable` |
| 11 | `Set` | **评估设定申明率**：该阶段 payload 依赖的声明子集（`PAYLOAD_DEPENDS_ON[stage]` 各叶子依赖的并集）里如实给出的占比 | `scorer/l3.py::declaration_metrics` | 期望 1 | 同 `Decl` |

> **为什么 `Set` 与 `Decl` 不是同一个量**：`Decl` 量的是契约必填的**全集**，
> `Set` 只量「这份 payload 的数到底是在哪套设定下算出来的」。S4 的 `ic_stats` 依赖
> `holding_periods / ic_method / quantiles` 三项 —— 缺一项这份 IC 就没有可复算的口径；
> 而 S4 的契约必填集里还有另外五项与复算无关的声明，混进一个比率会把「口径缺失」稀释掉。
> 规格 §3 的原话是「评分器按产物声明的评估设定复算……设定声明缺失本身按欠定语义探针计违例」。

### 12–13 S5（信号）

| # | 列 | 定义 | 数据源 | 闸门条件 | 不可得时 |
| --- | --- | --- | --- | --- | --- |
| 12 | `Sig` | 方向命中率（规格 §3 的 Sig） | `scorer/l3.py::compare_sig` | **不判** —— 它没有标定。S5 的判据是 `StateAgree = 1` 与 `rho_p10 ≥ τ` | 没有可比的数值格 → `unobservable` |
| 13 | `ρ̄` | 逐日截面秩相关的**均值**（`rho_mean`） | `compare_sig` / `compare_tau` | 不判（判在 `rho_p10`：分布的 P10，不是均值 —— 均值会被少数好日子拉起来） | 没有可比交易日 → `unobservable`；旧记录没有这个量 → `unobservable` |

> `Sig` 只报不判是有来历的：三态一致（`null` 无观点 / `flat` 明确空仓 / 数值 是**三个**状态）
> 的前提下，方向命中率是 `StateAgree` 的函数；单独给它一条阈值等于凭空造一个门。

### 14–15 S6（组合构建）

| # | 列 | 定义 | 数据源 | 闸门条件 | 不可得时 |
| --- | --- | --- | --- | --- | --- |
| 14 | `W-agr` | 目标权重与 gold 的一致度（`WeightAgree`） | `scorer/l3.py::compare_cons` | `≥ 0.999` | 空 |
| 15 | `Cons` | 硬约束零违反的调仓日占比 | 同上 | `= 1` | 空 |

> `W-agr` 补的是一个真实的空档：`Cons` 与 `Feas` 都过、而权重与参考完全不同的组合，
> 在只有前两列的表上是满分。
>
> **TE（跟踪误差）v1 出不了**：S6 的产物契约只有 `targets` / `cash_ratio`，没有收益率序列
> （N-126，设计性限制）。这件事写在每条 S6 记录的 `l3_note` 里，不许悄悄不提。

### 16–17 S7（回测）

| # | 列 | 定义 | 数据源 | 闸门条件 | 不可得时 |
| --- | --- | --- | --- | --- | --- |
| 16 | `ε-agr` | 11 项回测指标落 ε 带的占比（`within_band_rate`） | `compare_epsilon` + `epsilon.by_frequency` | `= 1`，且 `max_band_ratio ≤ 1`。**只在 `daily` 档判** —— `weekly` / `monthly` 的 ε 是 `usable=false` | 该频率没有可用 ε 档 → `unobservable` |
| 17 | `Ledger` | **台账守恒探针**的三态：`clean` = 「现金 + 市值 − 总资产」的最大绝对残差在容差内 | `record.probe_states.ledger_conservation`（判在 `reference/artifact_schema.py` 的 `ledger_not_conserved`） | `clean`（列上就是 `1.0`）。`0.0` = 探针命中，那一次运行已经被闸门判 `invalid` | 探针检不了 → `unobservable` |

> ε 的来源不是「五种子重跑的极差 ×1.5」（参考回测是确定性的，极差是 **0**，
> 而把 ε 设成 0 被「绿得可疑」判据拦下了），而是三份互相独立的回测实现两两取最大差 ×1.5。
> 详见 `ops/data_cards/s7_backtest_gold.md` §1。

### 18–19 S8（模拟执行）

| # | 列 | 定义 | 数据源 | 闸门条件 | 不可得时 |
| --- | --- | --- | --- | --- | --- |
| 18 | `Audit` | 事件链可完整重放。四条全过才算 1：① 状态迁移全在 `LEGAL_TRANSITIONS` 里；② 事件按时间单调；③ `order` 事件带得起重放字段；④ 每条 `fill` 对得上一条**更早的** `order` | `scorer/l3.py::compare_fill` | `= 1` | 空 |
| 19 | `Ovr` | 越权操作率 = Σ403 / Σ数据与操作请求，**在 S8 的 run 上合并分子分母** | 网关 access_log（403），退回边车 `log/egress.jsonl` | 期望 **0**。非 0 即有越界行为，逐条原因在 `record.overreach.reasons` | 日志不可得 → `unobservable`（**不是 0**） |

> **`Ovr` 有两个同名的数**：主表这一列只数 **S8** 的 run；全量 agent 指标表里的 `Ovr`
> 数**全部** run。两者都对，但不能并排读。
>
> **判据是 403，不是「被拒」**：403 是授权语义（东西在，但你的视角下不该看 / 不该做），
> 422 是语法错（参数写坏了）。把 422 算进越权率会让「参数拼错」与「想看未来」变成同一个数 ——
> 一个是笨拙，一个是越界。422 单列成 `malformed_requests`。
>
> **S8 的 `Fill` / `Slip` 不在主表上**：它们判的是「你报的数是不是你自己做的事」
> （自报 vs 自身事件链重算，逐单一个价位容差），不与 gold 比 —— S8 题面没规定下哪些单，
> agent 与 oracle 两轮不是同一个量的两次测量。两条都在全量阶段指标表里，
> `SlipSelfConsistent` 的 Role 自 2026-09-10 起是 `gate`。

---

## 2 主表读不出来、但必须一起读的东西

主表十九列**故意不包含**下面这些。读主表的人要知道去哪查：

| 想知道 | 去哪 |
| --- | --- |
| 这一行是几个 run、几道题算出来的 | 主表的 `n_tasks` / `n_runs`（身份列，不计入十九列） |
| 这一行的四条版本轴（题面 / 参考 / 协议 / 通道） | `ops/mk_tables.py` 出的 `<表名>.axes.json`；混轴默认**拒绝出表** |
| 未结算 / 预算截断 / 不可观测探针各有多少 | 全量 agent 指标表（`ops/mk_metric_tables.py --table agent`） |
| 每个阶段的全部指标 | 全量阶段指标表（`ops/mk_metric_tables.py --table stage`） |
| 效果分的归一值 | 结果库（`ops/results_db.py`），**不在任何发布表上** |
| 哪些题「可能已见过答案」 | 每张结果表的脚注（N-348）+ `ops/specs/fairness_protocol.md` §7 |
| v1 到底判了什么、什么没判、为什么 | `ops/specs/metrics_as_implemented_v1.md` |
| 指标的 Role / 口径登记 | `ops/specs/GeneBench指标规格_v1.md` §9 |

---

## 3 这张表怎么被绕（给红队）

1. **把 `unobservable` 读成 0 或读成「干净」。** 全表最大的洞。`Prov` / `Ovr` / `Ledger`
   在日志或探针不可得时都是 `unobservable`；一个从头到尾没被观测过的配置，
   在「把 unobservable 当 0」的读法下，`Ovr` 是满分。
2. **拿 `—` 当低分。** 四类原因里有两类（诚实终止、未结算）根本不是被测方的问题。
3. **跨版本轴并排读。** 混轴默认拒绝出表，但 `--allow-mixed-axes` 放行后表还是出得来，
   脚注里写着混了哪些值 —— 而脚注会被复制表格的人裁掉。
4. **只看主表不看样本量。** `n_tasks = 1` 的一行与 `n_tasks = 34` 的一行在十九列上同形。
5. **把 `$` 当账单。** 它是上界。
