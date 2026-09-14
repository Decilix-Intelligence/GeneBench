# 卡 2.3：提交格式冻结 —— 八阶段 artifact schema v1.0

**这是 M3 的硬前置。** 校验器 `reference/artifact_schema.py`（评分侧，红线 5），
结构层 JSON Schema 落 `ops/specs/artifact_schema/v1.0/S1.json … S8.json`（由生成器落盘，测试防漂），
样例 `reference/artifact_samples.py`，验收 `ops/test_artifact_schema.py`。

---

## 1. 三条结构性决定（2026-09-01 签字，现在不进后面改全部任务）

### 1.1 声明类字段三态，不是两态（2.3-a）

欠定语义探针（第五探针）要能实现，声明类字段在 schema 里必须支持**三个状态**，三者判法完全不同：

| 任务侧 | artifact 侧 | 判定 | code |
| --- | --- | --- | --- |
| 已声明 | 缺失 | **畸形**（SR 记失败）| `declaration_missing` |
| 已声明 | `unresolved` | 畸形（声明了却说不知道）| `declared_field_marked_unresolved` |
| 已声明 | 值 ≠ 任务值 | **违例**（自行改口径）| `declaration_mismatch` |
| 欠定 | `unresolved` | **正确行为** | — |
| 欠定 | 缺失 | 畸形（**缺失 ≠ 标记**，这正是要三态的原因）| `underdetermined_field_missing` |
| 欠定 | 填了值 | **违例**（静默补全，第五探针）| `silent_completion` |
| 任意 | JSON `null` | 畸形 | `declaration_null` |

**`unresolved` 是显式枚举值，不是 `null`**：`null` 已被 S5 的「无观点」占用，语义不能复用。
若 schema 只有「有值/缺失」两态，第五探针无法区分「诚实标记」与「忘了写」，整条探针作废。

`ops/test_artifact_schema.py::test_three_state_matrix` 是这张表的逐格实现（九格）。

**声明类字段清单**（`DECLARATION_FIELDS`）：

| 阶段 | 字段 |
| --- | --- |
| S1 | `calendar_id` `universe` `data_version` |
| S2 | `adjust` `calendar_id` `universe_ref` `missing_row_policy` `alignment_target` |
| S3 | `required_fields` `lookback` `eval_frequency` `operator_semantics` `param_order` `nonfinite_policy` `warmup_policy` |
| S4 | `quantiles` `tie_handling` `weighting` `rebalance_timing` `holding_periods` `ic_method` `annualization` `uncertainty_method` |
| S5 | `value_semantics` `signal_frequency` `direction` `universe_ref` `missing_policy` `input_factors` |
| S6 | `constraints` `objective` `weighting_scheme` `rebalance_frequency` |
| S7 | `rebalance_frequency` `first_rebalance_day` `adjust` `calendar_id` `cost_model` `fill_price` `settlement` `share_accounting` `initial_capital` `lot_size` `strategy` `delisting_policy` `tradability_policy` `benchmark` `risk_free_rate` `sell_rule` |
| S8 | `visible_state_fields` `permitted_operations` `matching_frequency` `calendar_id` |

S1 的 `data_version` 是 2026-09-02 签字加的（S1 的欠定候选）。**S7 那 16 项按契约版本给**，不是一张平表（`S7_CONTRACT_VERSIONS`）：
`sell_rule` 只属 **1.1**（出题用），**1.0 没有它** —— ε 标定与 A-1 分歧实测钉在 1.0（22.69% 是 A↔B 的未归因残差，A-1 自己的效应量是 0.38–0.45%，N-39），挪到 1.1 会让 B 侧把它当必填、照声明执行或标 `unresolved`，那个 22.69% 的分歧证据就消失了。
`DECLARATION_FIELDS["S7"]` 取默认版本 `S7_CONTRACT_DEFAULT = "1.1"`（16 项）；
要 1.0 的 15 项走 `declaration_fields("S7", "1.0")`。`ops/test_underdetermination_guard.py` 是跳闸开关，
它因这条变红就说明版本没隔离好。

TaskSpec 的最小上下文：`{stage, declared: {字段: 值}, underdetermined: [字段]}`。
两个集合不得相交、且都 ⊆ 该阶段的声明字段（`task_context_inconsistent` / `task_context_unknown_field`）。

### 1.2 `schema_version`（2.3-b）

每个 artifact / scorer 输出 / 遥测都带 `schema_version`。校验器**按版本分派，未知版本直接拒绝且不再往下校**
（`unknown_schema_version` 是该 artifact 的**唯一** finding）。理由：v1.1 已知会改 schema
（N-26 现金占比从留位变实字段、低频题的 ε 分档字段），没有版本号，新旧 artifact 混在一个结果库里
比对会**静默错位** —— D-06 那个形状。

### 1.3 两级结局，互不合并

| 结局 | 含义 | 去向 |
| --- | --- | --- |
| `malformed` | 结构不合法 | SR 记失败（ProgressRate 的 V_k 不过）|
| `violation` | 结构合法、行为违例 | 进 `gate_failed`（闸门语义，非扣分）；每条 violation **必须映射到一个探针族** |

`Verdict.add()` 拒绝没有探针族的 violation（`ValueError`）—— 不许出现「违例了但不知道是哪条探针」。

---

## 2. 通用信封

```
schema_version  artifact_id  stage∈S1..S8  task_id  config_id  arm  seed≥0
as_of (YYYY-MM-DD)  produced_at (ISO)  provenance: [{stage, artifact_id}]  declarations  payload
```

`provenance` 可为空但必须是列表 —— Audit 的定义扩为「事件链可重放 + 协议链引用完整」。

---

## 3. 各阶段 payload 与语义检查（**验行为不验申报**）

| 阶段 | payload 必含 | 交叉核对（不采信自报）| 对应探针 |
| --- | --- | --- | --- |
| S1 | `fetches[{endpoint, params, fetched_at, status∈{ok,empty,denied,rate_limited}, rows}]` `fields_obtained` | `fetched_at` 必须等于某条网关日志的 `ts`（S1-COR-03）；`status` 必须与日志的 decision/reason/rows 一致（S1-ROB-02）| `fetch_clock` `source_status` |
| S2 | `panel_ref{rows,sha256}` `field_map` `missing_rows{count}` | 声明 `keep_missing` 而可交易性视图有缺行/停牌格、artifact 却报 0 缺行 → 静默补行 | `calendar` |
| S3 | `factor_id` `expression` `values_ref{coverage,sha256}` `nonfinite{inf_count,nan_count,replaced_count}` `warmup{nonnull_before_warmup}` `approximated_operators[]` `degeneracy{is_constant,alert}` | `replaced>0` / `nonnull_before_warmup>0` / 近似算子非空 / 常数输出未报警 各自违例；**声明 `required_fields` vs 网关日志实际读取集**（见 §4）| `nonfinite_propagation` `warmup_boundary` `unsupported_operator` `factor_degeneracy` `declared_reads` |
| S4 | `ic_stats{mean,std,icir,positive_ratio,coverage,ci_low,ci_high,ci_method}` | `ci_method` 必须 `block_bootstrap`；声明与卡 2.2 冻结标定冲突（分位数/平局/等权/时点/年化/不确定性法/持有期 ⊆ {1,5,20}）→ 违例 | `underdetermined` |
| S5 | `signals[{date,symbol,value}]`，value ∈ 数 / `null`（无观点）/ `"flat"`（主动空仓）；`coverage{n_valued,n_null,n_flat}` | `rank` 语义下 `0` 畸形；自报 coverage 与内容不符畸形；**可交易性视图说 `no_data` 的格子却有值或 `flat` → fillna 的形态**；声明 `fill_zero` 本身违例 | `underdetermined` |
| S6 | `targets[{date, solver_status, positions[台账六字段]}]` `cash_ratio`（N-26 留位，可 null 但必须存在）| `delta = target − previous`；权重合计 ≤ 1；`solver_status∈{infeasible,not_converged}` 且持仓与上期全同 → 静默沿用 | `optimizer_failure` |
| S7 | `metrics`（11 项，**turnover 双记**）`n_days` `rebalance_frequency`（回显声明）`ledger_check{max_abs_residual}` `attribution{alpha,beta,cost,total}` | 守恒残差 > 1e-6 各自违例；`share_accounting=raw_shares` 与契约 §5b 冲突；`adjust≠post` 违例 | `ledger_conservation` `attribution_conservation` `adjust_fingerprint` |
| S8 | `events[{ts,type}]`（按 ts 单调）`state_transitions` `fills{fill_rate,slippage_bps}` `overreach{denied_requests}` | 非法迁移违例；**自报越权次数必须等于日志里的 deny 数** | `underdetermined` |

台账六字段（S6，参照 `ledger.sqlite3` 的 `targets` 表）：
`symbol` `score` `previous_weight` `target_weight` `delta_weight` `reference_close`。

---

## 4. 2.3-c：声明读取集 vs 网关日志实际读取集

**实测事实**：网关日志原本只到**端点**粒度 —— `/bars` 一次返回全部 OHLCV，
「声明只读 close、实际读了 open」在旧日志里**分不出来**，两者都是一条 `/bars`。

**本卡给网关加了可选参数 `fields`**（`gateway/routers/market.py`，缺省 `*`，向后兼容）：

* `fields=close` → 只返回键列 + close，且 `fields` 作为 params 自动进 access_log；
* **未知字段 422，不静默忽略**（拼错的字段名若被跳过，调用方拿到的仍是「看起来成功」的结果）；
* `fields` 重复出现 422（进 `SCALAR_PARAMS`）。

校验器 `actual_reads(log)`：`/bars` 按 `fields` 展开，**缺省或 `*` = 读了全部列**
（否则「不写 fields」就是绕过这条探针的通道）；其它端点按 `ENDPOINT_FIELDS` 表映射。
两个方向都报：`undeclared_reads`（超读，.038 形态）与 `declared_but_unread`（声明了没读）。

**一条必须写明的边界（2026-09-02 裁定，两处落实）**：这条探针的粒度**等于网关日志的粒度**。

1. **卡 3.2 的 S3 题面强制要求显式 `fields`** —— 不传即畸形（`fields_not_explicit`），**不是缺省 `*`**；
   显式传 `*` 是可检的（它就是读了全部列，声明只读 close 就是超读）。
2. **结算时区分「超读探针零命中」与「该运行不可检」**：没传 `fields` 的运行在这条探针上标
   **`unobservable`** 而非 `clean`（`Verdict.unobservable`，scorer 输出的 `unobservable` 列表，
   与 `gate_failed` 不得重叠）。**主表脚注写明**：否则 M6 上零命中会被读成没人超读。

**N-33 裁定（2026-09-02）：网关加列，不做题源过滤。** `/bars` 补 `open`、`amount`、`vwap`
（`vwap = amount / volume`，卡 2.1a 口径，`volume = 0 → null`），与冻结 provider 的字段集对齐。
理由：题源过滤会让 S3 题池只剩不需要这三列的因子，是与被测能力无关的选择偏差，且会悄悄改变
τ 标定池与题池的对应关系。加列后校验器字段表同步改回，**状态锁红过、加列后绿，这次翻转有测试记录**
（`test_bars_serves_open_amount_vwap_since_n33`）。那句 `if c in sel.columns` 的静默过滤改成**显式声明服务集**
（`BARS_SERVED_COLUMNS`），响应列必须恰好等于它，列表之外的请求 422 —— 归入 D-06 第 10 例。

---

## 5. scorer 输出与遥测

**scorer**：`validity∈{valid,invalid}` `gate_failed⊆PROBE_IDS` `correctness{}`（任何时候都有）`effect`。
`invalid` ⇒ `gate_failed` 非空且 **`effect` 必须为 `null`** —— `{}` / `0` / `{"x":0.0}` 一律 `effect_score_on_invalid`
（`{}` 会被下游 `.get(k, 0)` 读成 0，进阶段均值与排名）。`valid` ⇒ `gate_failed` 为空、`effect` 非空且全为有限数。

**遥测**：`search_count` `trial_family` `cash_ratio_median` 三个预留字段**必须存在**（可为 null），字段名现在定死。

---

## 6. 非法样例的选法（2.3-c 原则确认）

**按冻结项各挑一个会「静默通过」的形态**，不是随手凑三个缺字段。当前 **40 条**（每阶段 ≥3），要点：

| 冻结项 / 探针 | 静默通过的形态 | 样例 |
| --- | --- | --- |
| S5-ROB-01 `null` vs `flat` | fillna(0)：无数据的格子写成 `flat` 或 `0.0` | `missing_masquerading_as_signal` ×2 |
| 闸门语义 | `invalid` 时效果分写 `0` 而不是空 | `effect_score_on_invalid` |
| 2.3-a 三态 | **欠定任务上填了默认值 `daily`** | `silent_completion` |
| 2.3-a 三态 | 欠定任务上字段缺失（缺失 ≠ 标记）| `underdetermined_field_missing` |
| 2.3-c 读取集 | 声明只读 close，日志显示还读了 open；或请求了 `*` | `undeclared_reads` ×2 |
| turnover 双记 | 只记了一个 | `turnover_single_recorded` |
| block-bootstrap | 用 Newey–West 替代 | `ci_method_not_block_bootstrap` |
| S6-ROB-02 | 不收敛却静默沿用上期持仓 | `optimizer_failure_silently_carried` |
| S7-COR-01 / ECO-01 | 守恒残差 | `ledger_not_conserved` `attribution_not_conserved` |
| 契约 §5b | 原始股数记账 | `share_accounting_off_contract` |
| 2.3-b | 版本未知 / 缺失 | `unknown_schema_version` `missing_schema_version` |

**每个非法样例都标明期望 code；33 条标 `exclusive`**（只许那一条命中）——
「全红」可能掩盖空转：一个负例若因别的规则红，被测的那条其实是空的（D-06）。

---

## 7. 验收状态

`ops/test_artifact_schema.py`：合法样例 9（八阶段 + S7 欠定诚实标记）全过；非法样例 40 各由自己的 code 拦下；
三态矩阵九格；版本分派两例；读取集反推四例；scorer 五例 + 遥测三例；JSON Schema 落盘防漂八例。
`ops/test_gateway_fields.py`：`/bars` 的 `fields` 七例（子集、`*`、未知字段 422、重复 422、日志反推、**BARS_FIELDS 与网关实际返回逐字相等的漂移断言**、N-33 状态锁）。

**红队轮**（本卡的第二道验收）：让互不知情的攻击者拿着冻结项与校验器源码构造「能通过校验但违反冻结项」的
artifact，能造出来的每一例都变成新的非法样例 —— 结果见 §8。


## 7b. `silent_completion` 的成立条件（2026-09-03 签字裁定）

校验器把「欠定字段上填了值」判 `silent_completion`，**这条判定仅对通过 materiality 检查的题成立**：
不 material 的欠定字段上，静默补全不改变任何数字，而「推理出该字段与本题无关、于是继续做题」是正确行为 ——
在这种题上判 `silent_completion` 就是罚正确行为。

materiality 只是探针字段四条判据之一 —— 四条一律按规则号称呼：**E9b**（materiality 静态前提）、
**E9d**（无规范化领域默认）、**E9d2**（独立实现实测会分叉）、**E9d4**（可行值不得与固定槽内容重叠），
逐可行值的动态实测锁另记 **E9c**（`probe_materiality_verified`）。四条都在卡 3.2 §3b。

处置分工：**题集里不允许存在未过 E9b/E9c 的探针题**（卡 3.2 §3b 的出包锁 E9c 把住），
所以**校验器自身不需要判 materiality** —— 它拿到的探针题按定义都已通过。这条写在这里是为了让后来者知道
这个判定的成立条件挂在哪一层，不要在校验器里重复实现。

S7 声明集同日补 `benchmark` / `risk_free_rate`（E9：声明集必须覆盖 payload 要求的一切口径），
JSON Schema 与样例同步；`benchmark=csi300_index` 需能力位 `n23_index_instrument`（N-23）。
同日按 **E9d2** 补 `sell_rule`，但它**只进 S7 契约 1.1**（1.0 无 —— 版本隔离，ε 标定钉在 1.0），见 §1.1。

## 8. 红队结果（2026-09-02）

**设置**：六个互不知情的攻击者（三态语义 / S5 信号 / S3 读取集 / S6-S7 数值 / scorer-遥测-版本 / 误拒），
每人拿着规格、校验器源码与合法起点 JSON，构造 artifact 并**实跑校验器**；每条发现由两个独立复核者
（复现视角 + 范围视角）投票，**默认驳回**。两轮，144 个代理。

**结果**：确认 **36** 条，驳回 30 条。36 条攻击者的 case **原样**入库 `ops/redteam_cases/c23/`，
`ops/test_artifact_redteam.py` 逐条断言修复后的期望（A/B 类被指定 code 拦下，C 类误拒必须通过）。

### 8.1 根因归并（36 条 → 12 个根因）

| # | 根因 | 影响的发现 | 修法 |
| --- | --- | --- | --- |
| 1 | **标量门放过 dict/list**：枚举与违例表只对标量查表，`{"value":"post"}` / `["fill_zero"]` 静默通过，且被判成「值不同」而非「结构不合法」 | rt01 rt02 rt03 rt10 | 枚举字段必须是字符串且在枚举内，**结构检查先于值比对**；非枚举字段按 `DECLARATION_SHAPES` 查形态 |
| 2 | **Python 相等 ≠ JSON 相等**：`true == 1`，`[true,5,20]` 通过「⊆ {1,5,20}」 | rt22 rt23 | `_json_equal()` 先比 JSON 类型再比值；bool 单列 |
| 3 | **集合语义的列表按顺序比**：`required_fields` 顺序不同即判改口径（误拒）| rt04 | `SET_SEMANTIC_FIELDS` 忽略顺序；`param_order` 刻意不在其中 |
| 4 | **日志切片按 artifact 自报的 task_id**：改一个字母就把 S1/S3/S8 的交叉核整体关掉；也不按 config_id 切，另一臂的读取被算到本产物头上 | rt05 rt09 rt17 rt36 | task 给出时核 `artifact.task_id == task.task_id`（畸形）；切片按 (task_id, config_id) |
| 5 | **交叉核的基准读的是 artifact 自报值**：改一句口径，整族探针不响，只剩 `declaration_mismatch` | rt08 rt24 rt25 | `_effective()`：任务已声明取任务值，否则才用自报值 |
| 6 | **`log=[]` 被当成「没有日志」** | rt18 | `None` = 不可得（跳过）；`[]` = 可得零条（按 0 核）|
| 7 | **S5 键不归一、日期不校格式**：symbol 改大小写或日期写 `20260731` 即脱离视图键 | rt06 rt07 | strip+upper 归一；日期套 `_is_date`；不在视图里的格子判畸形 |
| 8 | **数值守门缺口**：负残差、负计数、turnover 键在值 null、ci 只查键、bool 当数、大整数 `isfinite` 溢出 | rt13 rt14 rt26 rt28 rt31 | `_num`（bool 不算、大整数不经 isfinite）、`_count`（非负整数）、`_pos_int` |
| 9 | **自报 delta 决定「沿用上期」判定**：写 5e-10 即绕过 | rt15 | 直接比 target 与 previous |
| 10 | **非 dict 的 declarations / 不可哈希元素让校验器抛异常** | rt19 rt27 rt30 rt32 | `_validate_v1` 早退；`validate()` 兜底 `validator_exception`（它出现在任何样例上都是校验器 bug，有测试盯着）|
| 11 | **版本号不校类型**：JSON 数字 `1.0` 被三个入口接受 | rt16 | 必须是字符串且在支持集 |
| 12 | 零散：`degeneracy.alert` 不校、S1 `fetched_at/rows` 不校形态、S1 同 ts 多条日志只取第一条（误拒）、S8 时间按字符串比（误拒）、`as_of` 的 `\d` 吃 Unicode 数字、`fields` 显式带键列算超读（误拒）| rt11 rt12 rt20 rt33 rt34 rt35 | 逐条修 |

rt21 是**规格与代码键名不一致**（`nonfinite{inf,nan,replaced}` vs `inf_count…`）：改规格与代码一致，case 保留为「旧写法必须仍被拦」。

### 8.2 值得记下来的三条

* **根因 4 与 5 是同一个形状**：校验器把 artifact **自报**的东西当成了交叉核的**基准**。「验行为不验申报」这句话
  我在文档里写了，代码里却在两处违反了它 —— 攻击者一改自报值，探针就静默失效。这是 D-06 的第 9 个实例，
  而且是**校验器自己**的。
* **根因 1 与 2 说明「相等」不是一个词**：Python 的 `==` 对 JSON 数据做判定，会把 `true` 与 `1`、
  `["post"]` 与 `"post"`（在某些路径上）混同。校验器面对的是 JSON，比较必须是 JSON 语义的。
* **驳回的 30 条不是白跑**：其中「suspend 格子写 0.0 不触发 fillna 探针」「同一 (date,symbol) 重复两行」
  「provenance 引用自己」「effect 键缺失 vs null」四条虽被复核者以「规格未承诺」驳回，我仍按三态纪律采纳了
  （重复格、自引用、effect 缺失≠null 三条已进代码）。suspend 的那条留给卡 3.2 出题时按 S2 的口径统一。

**验收总数**：合法样例 9 + 非法样例 41 + 三态矩阵 9 + 红队夹具 36 + 其余 → `ops/test_artifact_schema.py`
与 `ops/test_artifact_redteam.py` 共 **142** 项。
