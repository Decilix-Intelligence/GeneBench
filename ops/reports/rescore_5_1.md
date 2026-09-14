# 卡 5.1 红队（评分器三卡：闸门 / L3 / 报告器）—— 发现、修复与既有 artifact 事后重算

> 范围严格限定在「**分数算得对不对**」：`scorer/{gate,l3,score_run,report,adaptation}.py`。
> 不审文档、不审接入、不改判据的严格程度 —— 本轮所有修复的方向都是**收紧**或**从「出数」改成「不出数」**，
> 没有一条放宽。协议：`ops/specs/redteam_protocol.md`（六视角 / §2 两个根因 / §3b 未判 / §7 突变落在门保护的对象上）。
>
> 跑板：`/data/shared/genebench/scratch/5.1/redteam_probe.py`（每条负例实跑当时的判定器，输出原样抄在下表）
> 回归夹具：`ops/test_scorer_redteam51.py`（26 条，修前 25 红 / 修后 26 绿）
> 隔离基线：`/data/shared/genebench/scratch/5.1/{oldcode,newcode}`（同一批输入分别用 HEAD 的 scorer 与打过补丁的 scorer 各重结算一次），
> 逐文件 diff：`/data/shared/genebench/scratch/5.1/isodiff.txt`

---

## 0. 一句话结论

十二条确认缺陷、七个根因；**其中三条改了已发布的数**：

| 改了什么数 | 幅度 |
| --- | --- |
| 所有 S2（`align`）题的效果分分母 | 天花板 `0.75` → `1.0`；`h_claude-code` strict 由 **100.0 → 81.49**、open 由 75.33 → 56.49；`h_opencode` strict 100.0 → 81.59、open 69.91 → 52.43 |
| 所有 S2 题的 `CellAgree` 分母 | `166624`（交集格数）→ `166800`（gold 格数）；`m6` / `a4` 的 `s2-cor-01` 由 `align:True` 变 `align:False`（少交 44 行），`a4` strict 的 pass@1 由 0.5 → 0.0，`m6` open 的 pass@1 由 0.5 → 0.375 |
| `m6b` 的两条 S8 记录 | `fills_linked_to_orders` 由 **1.0 → 0.0** —— 那批产物的委托号与成交号**全是 `null`**，旧代码把 `null` 收进「已见委托」集合，于是每条成交都「对上了一条更早的委托」 |

**一条必须由别人修的**：`ops/run_controls.py` 只从 `task_dir/work/` 拷 oracle 的产物文件，而 S2 的 gold 面板在 `gold/` ——
于是 oracle 桩自己没有面板，S2 的 oracle 控制效果分是 **75.0 而不是 100.0**。
这条以前被**同一个根因的另一半**（坏掉的天花板 0.75）抵消成 100.0，两个错刚好互相取消。见 §4 与 `ops/tickets_inbox/5.1.md`。

---

## 1. 六视角的十二条发现（全部实跑，输出原样）

`bug_class` 按协议 §1：**A** 静默通过（该扣的没扣）/ **B** 判错级别 / **C** 误拒。

| # | 视角 | 形态 | 跑板实际输出（修前） | class | 处置 |
| --- | --- | --- | --- | --- | --- |
| **A1** | ① 边界值 | S2 面板只交 1/200 行 | `{'CellAgree': 1.0, 'n_cells': 1, 'score': 1.0, 'l3_pass': True}` | A | 修 |
| **A2** | ① 边界值 | S3/S5 因子面板只交 1/20 天 | `{'fid_day_rate': 1.0, 'n_days': 1, 'score': 1.0, 'l3_pass': True}` | A | 修 |
| **C3** | ① 边界值 | S2 面板把对的行复制 20 遍稀释错行 | `{'CellAgree': 0.952…, 'n_cells': 21}`（正确口径 0.5） | A | 修 |
| **B1** | ② 三态混淆 | S8 事件链四个键都写上、值全 `null` | `orders_replayable=1.0`、`fills_linked_to_orders=1.0` | A | 修 |
| **B2** | ② 三态混淆 | S7 探针题 `payload` 整个空对象 | `{'correct_handling': True, 'n_dependents_nulled': 1, 'halted_fields': ['metrics']}` | A | 修 |
| **B3** | ④ 类型与序列化 | S5 每一格都写 JSON `true` | `{'StateAgree': 1.0, 'score': 1.0, 'l3_pass': True}` —— **满分** | A | 修 |
| **C2b** | ④ 类型与序列化 | S6 权重写 `"0.9"` / `true` / 缺键 | 旧 `float(v or 0.0)` 分别读成 0.9 / 1.0 / 0.0 | A | 修 |
| **A3** | ④ 类型与序列化 | ε 缺件 → `max_band_ratio = inf` 落盘 | `json.dumps` 产出裸 `Infinity`，严格 JSON 解析器直接抛 | B | 修 |
| **C1** | ③ 自报 vs 行为 | 题面没有 `as_of` 时 PIT 的基准回退到 artifact **自报**的 `as_of` | `{'PIT': 1.0, 'n_requests': 4}` | A | 修 |
| **C2** | ③ 自报 vs 行为 | S6 同一 symbol 写两行各 0.9（真实敞口 1.8） | `{'Cons': 1.0, 'Feas': 1.0, 'WeightAgree': 0.55}` | A | 修 |
| **D1** | ⑤ 聚合口径 | S2 的锚点顶不是真的 oracle 自比 | `{'floor': 0.0, 'ceiling': 0.75, 'effect': {'score': 100.0, …}, 'clamped': True}` | A | 修 |
| **D2** | ⑤ 聚合口径 | Table A 的 `effect` 均值没有样本量 | `{'1/10 有效': 100.0, '10/10 有效': 100.0, '列里有无 effect_settled_runs': False}` | B | 修 |
| **D3** | ⑤ 聚合口径 | Table B 的 `invalid_rate` 分母含 harness 坏掉的 run | `{'invalid_rate': 0.5, 'n_runs': 2}`（真实 1.0） | B | 修 |
| **E1/E2** | ⑥ 版本与切片 | 记录里一条版本轴都没有；`m6_all` 把两个题面版本合成同一行 | `{'pass@1': 0.5, '表里的版本列': []}`；`m6_all` 实测 = m6(`1.0.7`/`r1.0.8`) + m6b(`1.0.9`/`r1.0.14`) | A | 修 |

### 归并成七个根因

| 根因 | 覆盖 | 一句话 |
| --- | --- | --- |
| **R1 分母取交集而不取 gold** | A1 · A2 · C3 | 逐格 / 逐日比对用内连接的行数当分母 —— **少交的格子根本不出现在分母里**。规格 §3 的原话是「与**参考视图**逐格比对」「≥90% 的**交易日**过 Fid 门」，两个分母都在参考侧 |
| **R2 键在 ≠ 值在** | B1 · B2 | `k in o` / `payload.get(f) is None` 都对「键缺失」成立。与协议 §3 捞回的第 1 条（`effect` 键缺失 ≠ 标 null）同形 |
| **R3 比较前不判 JSON 类型** | B3 · C2b | 「不是 None、不是 str 就是数值」把 `true` 判成数值态；`float(v or 0.0)` 把字符串与缺键读成数。协议 §2.2 |
| **R4 基准来自被判者** | C1 | PIT 的 as-of 基准回退到产物自报。协议 §2.1 |
| **R5 容器语义：重复键静默取一行** | C2 · C3 · B3b | dict 推导 / 内连接让「同一格出现两次」变成「读到哪一行算哪一行」。协议 §3 捞回的第 2 条 |
| **R6 锚点顶不是真的自比** | D1 | 自比的「agent 侧」写死成 `task_dir/work/`（agent 的**输入**目录），S2 根本没有这个目录 |
| **R7 空值与口径在表上不可分** | D2 · D3 · E1 · E2 · A3 | 均值没有样本量、分母与 SR 不同口径、版本轴根本不在记录里、非法 JSON 常量落盘 |

---

## 2. 修了什么（逐条对应到代码）

| 根因 | 文件 | 改动 |
| --- | --- | --- |
| R1 | `scorer/l3.py::compare_align` | 逐格比对改成 **gold 左连接**：`n_gold_rows` / `n_rows_missing` 单列；`_present` 标记不可省 —— agent 整行没交时左连接也给 NaN，gold 那格若正好也是 NaN，`both_nan` 会把「没交」判成「对上了」 |
| R1 | `scorer/l3.py::compare_tau` / `_comparable_days` | `fid_day_rate` 分母改成 **gold 侧算得了 ρ 的交易日数**；新增 `n_gold_days` / `day_coverage`；`l3_pass` = τ 门 **且** 覆盖门 |
| R1 | `scorer/l3.py::compare_sig` | 同上（S5 内联信号那条路） |
| R2 | `scorer/l3.py::_replayable` | `REPLAY_FIELDS` 每一项都要有值；`qty` 必须是有限的 JSON 数；`null` 委托号不进 `seen`，没有委托号的成交直接判不 linked |
| R2 | `scorer/l3.py::compare_none` | `nulls` 要求 `f in payload and payload[f] is None`；新增 `n_dependents_missing` |
| R3 | `scorer/l3.py::_cell_state` | 先判 JSON 类型：`bool` → `other`，dict/list → `other`，只有真数值才是 `value` |
| R3 | `scorer/l3.py::_positions` | 权重必须是有限的 JSON 数（`bool` / 字符串 / 缺键都不是）；非数的行计数，那一天 `Cons` 不算过 |
| R4 | `scorer/l3.py::compare` / `compare_cov` | 删掉 `as_of or agent_artifact.get("as_of")`；题面没有 `as_of` → PIT **不可结算**（进 `skipped`），不记 0 也不记 1 |
| R5 | `scorer/l3.py::_signal_cells` / `compare_align` / `_positions` | 重复格**整格作废**并计数（信号、面板）；重复 symbol **按和计**（权重）—— 三处的共同判断：不许静默取一行 |
| R6 | `scorer/score_run.py::gold_payload_dir` / `anchor` | 按 `PAYLOAD_FILES[stage]` 的文件名探 `gold/` → `work/` → 题目录根，自比拿 oracle 自己那一份；`anchor` 元数据记 `ceiling_payload_dir`；缓存键补上 `stage` |
| R6 | `scorer/score_run.py::effect_of` | 判据标量高过天花板（`raw > 1+1e-9`）→ **锚点退化，扣住不出数**（旧行为：夹成 100，只留一个 `clamped: true`）；非有限的标量 / 锚点同样扣住（`max(0.0, nan)` 在 Python 里返回 0.0，会把 NaN 静默夹成 effect=0） |
| R7 | `scorer/l3.py::sanitize` + `score_run` | `correctness` 里的 `inf` / `nan` 一律换成 `None` 并记 `correctness_nonfinite_keys`；`l3_score` 同理 |
| R7 | `scorer/score_run.py::VERSION_AXES` / `version_axes` | 四条版本轴（`set_version` / `reference_version` / `runner_version` / `image_digest`）+ `scorer_schema_version` 逐条落进记录，**全部取自 `inject.json`**（runner 投放时盖的章，不是产物自报） |
| R7 | `scorer/report.py::version_cell` | Table A / Table B 各加四列；混了就写 `MIXED:a\|b` |
| R7 | `scorer/report.py::table_a` | 加 `effect_settled_runs` |
| R7 | `scorer/report.py::table_b` / `_in_denominator` | `invalid_rate` 分母与 SR 同口径（只排除 `unscorable_harness`）；加 `n_runs_denom`；认不出的历史状态**留在分母** |

**判别力自检（协议 §7：突变落在门保护的对象上）**：每条修复都配了一条「正例仍然满分」的测试 ——
`test_rt51_a1b`（逐格相同的面板照样 1.0）、`test_rt51_a2b`（全覆盖照样 True）、`test_rt51_b1b`（有值的链照样可重放）、
`test_rt51_d1b` 后半（顶正常时照常出 50.0）、`test_rt51_e1` 后半（同版本写版本号而不是 MIXED）、
`test_rt51_d3b`（认不出的状态留在分母）。修的是分母与判型，不是把所有人一起判低。

**表上的版本列写短形**：`runner_version` 与 `image_digest` 是 64 位十六进制，整串塞进 booktabs 表里没法读 —— 表上缩成前 12 位 + `…`（全仓一贯写法），**完整值留在 `records.json`**。表是给人读的，记录才是证据（`report._short_version`，`test_rt51_e1b`）。

---

## 3. 事后重算：逐 batch、逐文件

**方法**（为了把「我改的」与「输入自己变了」分开）：同一批 run 目录 **跑两遍** ——
一遍用 `git show HEAD:scorer/*.py` 的旧 scorer，一遍用打过补丁的，两次的产物逐文件比。
直接拿仓库里已提交的报告比是**不成立的**：那些报告是几天前生成的，其间 gold 面板落进了 `gold/`、
`calibration.json` 补了 N-117 的 IC 族带、网关 access_log 又长了一截、成本与预算字段换过实现 ——
那些差异与本卡无关，混在一起就说不清是谁改的了。

重结算**不打网关**（`--no-pull`），只读本机 `gateway_access.jsonl` / `gateway_access_public.jsonl`。

### 3.1 汇总

| | 文件数 |
| --- | --- |
| 逐字节相同 | 26 |
| **只多了新列 / 新字段**（一个既有的数都没动） | 117 |
| 有实质数字变化 | 73（其中 `scores/` 与 `controls/` 下的逐 run 文件占大头，都是同两条归因） |

### 3.2 逐 batch

| batch | 文件 | 变了没 | 归因 |
| --- | --- | --- | --- |
| `a1` | `records.json` | 变（只多字段） | 四条版本轴 + `scorer_schema_version`；**数字未动** |
| `a1` | `table_a.csv` / `table_b.csv` / `table_b.tex` | 变（只多列） | `effect_settled_runs`、四条版本列、`n_runs_denom` |
| `a1` | `summary.md` / `table_a.tex` | 同 | — |
| `a4` | `records.json` | **变（数字）** | R1：`s2-cor-01.strict.r02` 的 `CellAgree` 1.0 → 0.998945（`n_cells` 166624 → 166800，少交 44 行），`l3_pass` True → **False**（0.999 门），`l3_score` 1.0 → 0.999736，`effect` 100.0 → 99.9736；R6：`anchor.ceiling` 0.75 → 1.0、`clamped` true → false（`doc` 与 `strict` 两条） |
| `a4` | `summary.md` / `table_a.csv` / `table_a.tex` | **变（数字）** | 上一行传导：`strict` 的 `pass@1` 0.5 → **0.0** |
| `a4` | `table_b.csv` / `table_b.tex` | **变（数字）** | `CellAgree` 均值 1.0 → 0.998945；另加 `n_gold_rows` / `n_rows_missing` / `n_runs_denom` / 版本列 |
| `adapt` | 全部 | 同 | 适配赛道记录为空（`records.json` 是 `[]`），本轮改动不触及 `table_adaptation` |
| `h_claude-code` | `records.json` / `table_a.csv` / `table_b.*` | **变（数字）** | R6 是主因：`ceiling` 0.75 → 1.0 →`effect` strict **100.0 → 81.4934**、open **75.3337 → 56.4934**；R1 让 `CellAgree` 0.260011 → 0.259736。`pass@1` 本来就是 0，不受影响 |
| `h_opencode` | 同上 | **变（数字）** | 同因：`effect` strict **100.0 → 81.5946**、open **69.9079 → 52.4284** |
| `h_gemini-cli` / `h_grok-cli` | `records.json` / 两张表 | 变（只多字段/列） | 这两个 harness 的 run 没产出可评分产物（`no_artifact` / `budget_exhausted`），没有 L3 也没有 effect |
| `i_alphaagent` / `i_finmem` / `i_finrobot` / `i_rdagent_q` / `i_rehearsal` / `i_tradingagents` | 全部 | 变（只多字段/列） | 同上：接入验证批次的 run 都没走到 L3（或走的是不受影响的 kind），**一个既有的数都没动** |
| `m6` | `records.json` | **变（数字）** | R1 + R6，`s2-cor-01` 两条：`CellAgree` 1.0 → 0.998945、`l3_pass` True → **False**、`effect` 100.0 → 99.9736、`ceiling` 0.75 → 1.0 |
| `m6` | `summary.md` / `table_a.*` | **变（数字）** | `open` 臂 `pass@1` 0.5 → **0.375**（8 题里 s2 那题由过变不过） |
| `m6` | `controls.json` / `controls.md` / `controls/s2-cor-01.oracle.score.json` | **变（数字）** | R6 拆开了原先互相抵消的两个错：`ceiling` 0.75 → 1.0 之后，oracle 桩自己的 effect **100.0 → 75.0** —— 因为 `ops/run_controls.py` 只从 `task_dir/work/` 拷 oracle 产物文件，而 S2 的 gold 面板在 `gold/`。**这是真的**：那个 oracle 桩确实没有面板。见 §4 |
| `m6b` | `records.json` / `table_b.*` | **变（数字）** | R2：`s8-eco-01` 两个臂的 `fills_linked_to_orders` **1.0 → 0.0**。`Audit` 本来就是 0（`orders_replayable=0`），所以 SR / pass@1 / effect **都没变**；变的是 Table B 上那一格子信号 |
| `m6_all` | `records.json` / `summary.md` / `table_*` | **变（数字）** | m6 与 m6b 的合并传导：`open` 臂 `pass@1` 0.3333 → **0.25**、`effect` 100.0 → 99.9934；另加版本列，这张表现在会显式写出 `MIXED:1.0.7\|1.0.9` |
| `public` | `controls.json` / `controls.md` / `controls/s2-cor-01.oracle.score.json` | **变（数字）** | 与 `m6/controls` 同因同幅：oracle effect **100.0 → 75.0** |
| `public` | 其余 26 个文件（O1 矩阵、materiality、mutations、reconciliation…） | 同 | **O1 不经 scorer**：它是校验器（`reference/artifact_schema.validate`）的 finding 矩阵，本轮一行都没改 `reference/`。三控里 null / filler 两桩也逐字节相同 |

### 3.3 没变的要说明为什么没变

* **`adapt`**：适配赛道的结局判定在 `scorer/adaptation.py`，本轮**一个字节都没改**它 —— 五结局的判据不属于「分数算得对不对」里被攻击的那几类（它不做分母、不做归一、不读产物自报的数）。
* **`public/` 的 O1 与 materiality / mutations / reconciliation**：全部由校验器与独立实现产出，不经 `scorer/`。
* **null / filler 两桩控制**：它们的 `sr_bucket` 不是 `scorable`（`malformed`），根本走不到 L3 与 effect，所以七个根因一条也碰不到它们 —— 这也是三控判据 ② ③ 仍然全过的原因。
* **`i_*` 与 `h_gemini-cli` / `h_grok-cli`**：run 没有可评分产物，L3 从未被调用。
* **`a1`**：S1 走 `cov`，本轮对 `cov` 的唯一改动是「题面没有 `as_of` 时不回退到自报」——`s1-cor-01` 的 `task.yaml` 有 `as_of: '2026-07-31'`，所以那条回退路径在真数据上**从未被走过**（它是一条待触发的洞，不是一个已经算错的数）。PIT 全部原值。

---

## 4. 本卡修不了、必须由别人修的一条

**`ops/run_controls.py::score_control` 只从 `task_dir/"work"` 拷 oracle 的产物文件**（`shutil.copy2` 那一段）。
S2 的 gold 面板落在 `gold/panel.csv`（r1.0.16 起），题目录**根本没有 `work/`** ——
于是 oracle 控制桩交上去的是「有 artifact.json、没有面板」的产物，`CellAgree` 判 0，`l3_score = 0.75`。

以前看不出来，是因为**锚点的天花板也是 0.75**（同一个根因的另一半）：`0.75 / 0.75 = 1.0` → effect 100.0。
两个错互相抵消，控制判据 ①「oracle 效果分 = 100」看起来是过的。**这正是 D-06 那个形态**：
所有可见信号都绿，而门后面是空的。

`scorer/score_run.py` 现在导出了现成的 `gold_payload_dir(task_dir, stage)`，补丁是一行：

```python
    if which == "oracle":
        src = SR.gold_payload_dir(task_dir, task["stage"]) or (task_dir / "work")
        for f in src.glob("*"):
            if f.is_file() and f.name != "oracle_artifact.json":
                shutil.copy2(f, rd / "work" / f.name)
```

另外 `run_controls.judge()` **不检查 effect 是否等于 100**，只检查「出数了没有」——
所以这条判据在 `controls.md` 里写着「三条判据全过」的同时，S2 那一格是 75.0。
判据 ① 的原文是「效果分 = 100（自比即天花板）」，`judge()` 应当照原文判。两条都记在 `ops/tickets_inbox/5.1.md`。

**在这条修好之前**：`ops/reports/{m6,public}/controls.md` 里 `s2-cor-01 | oracle | effect=75.0` 是**如实记录**，
不是回归 —— 它记的是「oracle 桩没有面板」这个事实。

---

## 5. 登记不修 / 交给别人

* `ops/reports/v1_0_readiness.md` 第 47–48 行的 `align:True` / `100.0` 现在是陈旧的（应为 `align:False` / `99.9736`）。
  该文件不在本卡的路径边界内，重跑命令：`$PY ops/readiness_report.py --batch m6,m6b`。
* `m6_all` 这张表本身是**跨题面版本的合表**（`1.0.7` + `1.0.9`）。本轮让它在表上写出 `MIXED:` 了，
  但「要不要继续出这张合表」是编排方的裁定，不是报告器的。
* `compare_fill` 的 `events_monotone` 用字符串排序判时间单调。实测的 ts 都是同一种 ISO 写法所以判得对，
  但混写（带 / 不带时区、`Z` vs `+08:00`）会判错。登记不修 —— 校验器侧已有 `_parse_ts`，
  统一到那一条线属于 v11。
