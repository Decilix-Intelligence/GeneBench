# 参数轮换实例：设计与判据（W3，2026-09-10）

> 代码 `ops/mk_instances.py` · 参数表 `genetask/params/v1.0-instances.yaml` ·
> 测试 `ops/test_instances.py` · 清单 `ops/freeze_v10.py::build_instances_section`
>
> **本卡不推任何版本号、不跑 oracle、不碰 f02。** 实例只到「题面可渲染、夹具可导出、
> 清单可写入」为止；真出集与推版本由 Y1 统一做。

## 0. 一句话

拿出集参数表的 **40 行**，沿 **窗口 × 宇宙 × 因子池**（按每行适用的维度）换取值，
得到 **130 个实例**（每阶段 15–17）。题面仍由 `genetask/render.py::render_arm` +
**现有** `genetask/phrasebook.yaml` 渲染，夹具仍由 `reference/make_fixtures.py::materialize`
从 gold 面板导出 —— 生成器一行渲染逻辑、一行夹具逻辑都不新写。

## 1. 口径：「40 模板」是 40 **行**，不是 40 个模板目录

报告口径写 **40 模板 / 130 实例**。这里的 40 指出集参数表 `v1.0-smoke40.yaml` 的 40 **行**；
模板**目录**只有 **39** 个 —— `S1/source_status` 被 `s1-rob-01`（规定题）与
`s1-rob-02`（探针题）两行复用。身份的单位因此是「参数表的一行」，代码里叫 **基点（base）**。

这不是学术区别：`instance_id` 里若只写 `模板 ID + 参数指纹`，这两行的**基准实例 id 逐字节相同**
（两行的窗口与宇宙恰好都一样，参数字典都是 `{}`）—— 实测撞过，见
`ops/test_instances.py::test_shared_template_dir_does_not_collide`。

## 2. 实例 ID 与指纹

```
instance_id = <stage>/<template_id>@<base_task_id>#<fingerprint>
例：S4/cor_ic_recompute@s4-cor-01#f436d8670e
```

* `stage` 不可省：`rob_underdetermined` 在 S6 与 S7 各有一份。
* `base_task_id` 不可省：见上一节。
* `fingerprint` = 规范化参数字典的 `sha256` 前 **10** 位。

**规范化四条（`mk_instances.normalize`，指纹的唯一定义）**：

1. 只收维度参数（`window` / `universe` / `factor_pool`），别的键一律报错；
2. **剔除等于基点现值的维度**（"不含默认值"）—— 基准实例的参数字典因此是 `{}`，
   指纹恒为 `44136fa355`（= `sha256(b"{}")[:10]`）；
3. 取值一律过 `genetask.render.value_key`（与 phrasebook 取键**同一个函数**，dict 走规范 JSON）；
4. `json.dumps(sort_keys=True, separators=(",",":"), ensure_ascii=False)` 后 `sha256`。

同参数必得同 ID；键序、dict 内部顺序、枚举顺序、seed 都不影响它。
`ops/test_instances.py::test_fingerprint_is_pinned_across_machines` 拿**死值**钉住三个指纹 ——
「跑两遍一样」在同一进程内必然成立，不是判据。

### `task_id` 怎么来

`genetask/schema.py` 的 `task_id` 正则是 `^s[1-8]-(cor|rob|eco|ops)-\d{2}$`，装不下指纹。所以：

* **基准实例沿用基点自己的 task_id**（`s4-cor-01` 还是 `s4-cor-01`）；
* 变体在 `(stage, family)` 内按 `(template_id, fingerprint)` 排序，
  从该组基点里最大的编号 **+1** 起顺序发号。确定性、跨机可复现，且**一律大于出集用掉的号** ——
  加实例只往后追，不会覆盖出集的题，也不会重排已有的。

## 3. 为什么「槽位机器生成、不必重签」

签字签的是**措辞**，不是取值。三条判据合起来才成立，缺一条都不成立：

1. **凡是会落进 `declared` 的取值，phrasebook 里已经有 strict/open 两列措辞。**
   没有就当场拒（`MissingPhrasing`，报出是哪个字段的哪个取值、可用的键有哪些）。
   *不许往 phrasebook 加新词*：它在冻结根 `ops/freeze_v10.py::CODE_FILES` 里，
   加一个词 40 道出集题全部重签 —— 那正是本卡要避免的事。
2. **只改取值，不改键集。** `declared` 的键集与 `underdetermined` 一字不动，于是
   `packager.build_task` 的 **T1**（模板 `slots` == 声明字段全集）与
   `render.check_arms` 的 **E1**（两臂槽位**序列**相等）自动仍成立。
3. **每个实例都过一遍 `packager.build_task`** —— E1–E15 / R1–R5 / C1 / T1 / J1 全套照查。
   **没有任何一条规则对实例开例外。** 130/130 全绿（实测 3.1 秒）。

窗口与宇宙落在**固定槽** `task_window` / `task_universe` 上，措辞由 `render.FIXED_PHRASES`
用 `{v}` 拼出来，本来就是机器生成的。

## 4. 三个维度，逐阶段适用性

| 维度 | 写到哪 | 需要 phrasebook？ | 适用阶段 |
| --- | --- | --- | --- |
| `window` | `row.window`、`inputs[].max_date` | 否（固定槽） | 全部 8 个阶段 |
| `universe` | `row.universe`、`declared.universe`（S1）/ `declared.universe_ref`（S2/S5）、`inputs[].origin` | S1/S2/S5 **是**；S3/S4 否（只是固定槽） | S1–S5 |
| `factor_pool` | `gold_args.factor_id`、`inputs[].origin` | S5 是（落 `declared.input_factors`） | **仅 S4** |

`inputs[].max_date` 一律跟到 `window.end` —— 出集 40 行现状就是这个恒等式（逐行核过），
也是 A1 两条（`max_date ≤ as_of`、`window.end ≤ as_of`）的最紧写法。

### 换因子**题面逐字不变**

`packager._inputs_phrase` **刻意不把 `origin` 写进题面**（origin 是数据面的来源说明，
可能含 gold / 信号 id 这类评分侧词汇）。S4 的输入路径又是常量 `work/factor_panel.parquet`。
所以换因子只改 `gold_args` 与夹具 origin：**题面指纹不变、夹具 sha 变**。
这不是漏洞，是这一维度的定义 —— `test_factor_axis_moves_the_fixture_not_the_text` 把它钉死。

### 轮换排布

适用维度的**笛卡尔积**，按**对角线序** `(max(下标), sum(下标), 下标元组)` 排定，
再从下标 = 「基点在本阶段内的序号」处开始取；规范化后为空（整组等于基准）与重复指纹跳过。

*为什么不是字典序*：字典序会把「第一个维度取 0 号值」的组合全排在前面，而 0 号值往往就是
基点现值、在规范化时被剔掉 —— 实测 S4 按字典序取，17 个实例里**只有 2 个换过窗口**。
对角线序让每个维度轮流先动（改后 S4：窗口 8 / 宇宙 5 / 因子 3）。

每个基点出 **3** 个实例（含基准）；适用维度 ≥ 2 的阶段，按 `base_task_id` 排序的**前 2 个**基点
各再加 1 个 → 多轴阶段 17 个、单轴阶段 15 个，合计 **130**。

## 5. 计数

| 阶段 | 实例 | 维度 |
| --- | --- | --- |
| S1 | 17 | window, universe |
| S2 | 17 | window, universe |
| S3 | 17 | window, universe |
| S4 | 17 | window, universe, factor_pool |
| S5 | 17 | window, universe |
| S6 | 15 | window |
| S7 | 15 | window |
| S8 | 15 | window |
| **合计** | **130** | 基点 40 |

## 6. 夹具：按实例从 gold 面板导出

走 `reference/make_fixtures.py::materialize(task_dir, task)` —— 它的驱动源是题面的
`inputs[].origin`，而窗口 / 宇宙 / 因子池已经写进 `task.window` / `task.universe` /
`inputs[].origin`，所以「按实例导出」不需要给它加任何新参数。

`origin` 里的宇宙与因子 token 由 `_rewrite_origin` 跟着实例改写；**认不出的形态报错，不猜**
（与 `make_fixtures` 同一条纪律）。变体的 `inputs[].sha256` 先置 `null` ——
留着基点的 sha 就是「这份夹具有身份」的假绿。

实测（`s4-cor-01` 的 4 个实例，2026-09-10）：

| 实例 | 参数 | 夹具 sha256 |
| --- | --- | --- |
| `…#44136fa355`（基准） | `{}` | `c8ed955e…` |
| `…#a10c40daae` | `factor_pool=gtja_191.017` | `b34144bb…` |
| `…#0b0d39a2c6` | `universe=csi500` | `7687dd89…` |
| `…#f436d8670e` | `window=2026-01-05…2026-03-31` | `d155747d…` |

两条交叉核对（这是「走的是同一条路径」的证据，不是断言）：
基准实例的 sha **逐字节等于**出集 `s4-cor-01` 记着的那个；
`gtja_191.017` 变体的 sha **逐字节等于**出集 `s4-rob-01` 记着的那个（同因子同窗同宇宙）。

sha 由 `--write-shas` 写回**参数表**（`v1.0-instances.yaml` 的 `fixtures:` 段），
不写生成出来的 `task.yaml` —— 与 `make_fixtures.write_params_shas` 同一条纪律：
后者每次 `build_task` 都重建，写进去下一次就没了，而「没了」的表现是 `sha256: null`。

写回**只替换 `fixtures:` 那一段的文本，不整文件重 dump**。第一版用了 `yaml.safe_dump(doc)`，
它把参数表里逐条写着「这个取值为什么可以用 / 那个为什么不许用」的注释全部抹掉
（13162 → 9395 字节，实测）—— 参数表的一多半价值就在那些注释里。
段边界取「`fixtures:` 行 + 随后所有缩进行与空行」，**顶格注释也是边界**：
用「到下一个顶格键」当边界会把紧挨在下一个键上面的说明注释一并吞掉。
配 `test_fixture_write_back_preserves_the_comments`。

## 7. 冻结清单：模板与实例**两层**

`ops/freeze_v10.py::build_instances_section()` → 清单的 `instances` 段：

```
instances.bases[<base_task_id>] = {stage, family, template_id, template_key, axes,
                                   instances: [{instance_id, task_id, fingerprint, is_base,
                                                params, window, universe,
                                                instruction_fingerprint, fixtures}]}
```

`instances_fingerprint` = 逐实例 `(instance_id, 题面指纹, 夹具 sha)` 拼起来算一次 sha256。

**它刻意不进 `ROOT_FIELDS`**：进了根，加一个实例就会让所有已发 bundle 通行证作废
（`frozen_ref` 比的是根），而实例与出集那 34 题不是一回事。同理 `build_manifest()`
**默认不算实例段** —— `frozen_ref(verify=True)` 每出一个 bundle 就调它一次，
多建 130 道题只为算一个不进根的字段，是白付的钱。
写入要显式：`python3 ops/freeze_v10.py --write --with-instances`；
只看漂移：`python3 ops/freeze_v10.py --instances-dry`（本卡跑的就是这个）。

**留给 Y1 的一个决定**：`instances_fingerprint` 要不要收进 `ROOT_FIELDS`。
收 = 实例也享受「改了就作废通行证」的保护，代价是实例表一动全部 bundle 重出；
不收 = 实例层记录在案但不受根保护。本卡按保守方向做（不动根），标 `pending_freeze_bumps`。

## 8. 想要而做不到的取值（都不许绕）

| 维度 | 取值 | 阶段 | 为什么不许 |
| --- | --- | --- | --- |
| universe | `csi1000` | S1 / S2 / S5 | phrasebook 缺 `universe[csi1000]` 与 `universe_ref[csi1000@2026-07-31]` 的两列措辞。补措辞会改冻结根，40 道出集题重签。 |
| universe | `csi1000` | S3 / S4 | 措辞上可行（只是固定槽），但两阶段的 oracle 从未在 csi1000 上跑过，截面是 csi300 的三倍多，gold 重算成本与 ε 标定都没有依据。 |
| factor_pool | `gtja_191.002` 等任何别的单因子 | S5 | S5 把因子写进 `declared.input_factors`，而 phrasebook 只有 `gtja_191.001` 与 `gtja_191.001,gtja_191.002,gtja_191.003` 两个键。 |
| factor_pool | 任何 | S3 | S3 的因子**就是模板本身**：公式写在 `INSTRUCTION.*.md` 与 `solve.py` 里。换因子 = 换模板 = 人工重写题面，正是本卡明令不许生成的那一类。 |
| universe | 任何 ≠ csi300 | S6 / S7 / S8 | S6 的输入信号（`s5_gtja001_csi300_v1` / `s6_sparse_coverage_csi300_v1`）、S7 的 ε 面板 `s7_panel_v3`、S8 的撮合面板都是 csi300 绑定的**冻结夹具**。换宇宙要重做夹具与 ε 标定，不是换一个参数。 |

## 9. 六道挂起探针题：逐题判「能不能放出」

判据是 `genetask/schema.py` 的 **E9c**（本题条件下有 screen 实测或 `FIELD_MATERIAL_WHEN` 静态规则）
与 **E9d2**（本题**条件**下有实测证据 —— 别的条件下的结论不能顶）。
证据源：`ops/reports/public/materiality_screen.{json,md}`（2026-09-07 跑的）与
`ops/reports/public/materiality_evidence.json`。

**结论：六道一道都放不出。** 六道全部 `inconclusive`，而且是**同一个结构性原因** ——
筛查 harness 是三份冻结的 **S7 回测引擎**（`snapshots/*/epsilon/impl_v2_b*.py`），
它量得到的只有回测指标；S1–S5、S8 的探针字段根本没有进入这套 harness 的入口。
`materiality_screen.md` 结尾那句是本卡照办的判据：
**「任何一题 inconclusive 都不许翻锁 —— 『跑不起来』『量不到』都不是『没差别』。」**

因此本卡**不写任何 `DIVERGENCE_EVIDENCE` 条目正文**（`genetask/schema.py` 里现有的两条
`s6-rob-02` / `s7-rob-02` 已经出集，与本卡无关）。逐题缺什么：

| 题 | 欠定字段 | 本题条件 | screen 结论 | 缺什么才放得出 |
| --- | --- | --- | --- | --- |
| `s1-rob-02` | `data_version` | （无条件） | inconclusive · 0 处分叉 | 需要一套 **S1 取数层**的独立实现比较：三份冻结实现读的是一张定死的 csi300 面板（`bt_input_csi300_v2.parquet`），**没有「数据版本」这个入口**；换版本等于换输入面板，那是另一份标定不是一个开关。要么造 v1/v2 两份真实有差异的快照并按 Cov%/PIT%/Prov 三个 S1 判据量差，要么承认这道题在 v1 量不到、永久挂起。 |
| `s2-rob-02` | `adjust` | `missing_row_policy=keep_missing` | inconclusive · 0 处分叉 | 需要 **S2 对齐层**的 harness：复权口径在面板生成时就已经定死（post），三份实现拿到的是复权后的价，**没有「换一种复权」的入口**。要量它必须在面板**生成**这一层做 post/none 两版，再按 S2 的 `align` 判据比 —— 那是一份新的 screen，不是现有 harness 加个开关。 |
| `s3-rob-02` | `eval_frequency` | `lookback=24` | inconclusive · 0 处分叉 | 需要 **S3 因子求值**的独立实现：三份实现是回测引擎，**不求值因子**，只吃现成的信号面板。要量它得有 ≥2 份独立的因子求值器（`tau` 判据），且要在 `lookback=24` 这个条件下量 —— 别的 lookback 下的结论不能顶（E9d2）。 |
| `s4-rob-02` | `holding_periods` | `ic_method=spearman` | inconclusive · 0 处分叉 | 需要 **IC 族**的独立实现：三份实现不出 IC；S4 的判据是 IC 族 ε（N-117），不是回测指标 ε。要量它得先有第二份 IC 计算实现，并在 `ic_method=spearman` 条件下逐指标比 IC 族 ε 带。 |
| `s5-rob-02` | `signal_frequency` | `value_semantics=score` | inconclusive · 0 处分叉 | 需要 **S5 信号层**的 harness：三份实现吃的是**已经算好的**信号，不重采样它。要量它得有两份独立的「按声明频率重采样因子 → 信号」的实现，按 `sig` 判据比。 |
| `s8-rob-02` | `slippage_reference_price` | `matching_frequency=daily` | inconclusive · 0 处分叉 | 需要 **S8 撮合**的入口：三份实现按 close 成交、**没有滑点参考价这个入口**；换入之后要重做一次面板与标定（题面自己就标着「等 `slippage_reference_price` 换入后一并跑」）。与 N-383 的 Slip 判据是同一条线：Slip 纳入 S8 判据之后，这道题才有量得到的可能。 |

三条共同的形态，写下来免得下一轮又走一遍：

* **「量不到」≠「没差别」**。六道的 0 处分叉全部来自 harness 结构，不来自数据。
  把它读成「这个字段无所谓」会让六道题被错误地出集，而它们的探针恰好测不到任何东西。
* **证据的键是 `(字段, 条件)` 不是字段**（`schema.EVIDENCE_CONDITION_KEYS`）。
  即使将来某个字段量到了，也只在**当时那个条件**下算数。
* **每道题要的是它那一层的 harness**，六道分属六层（取数 / 对齐 / 因子求值 / IC / 信号 / 撮合）。
  这不是一件事，是六件事 —— 别按「补一个 screen」估工。

## 10. 本卡跑过什么

* `python3 ops/mk_instances.py --list` → 130 实例 / 每阶段 15–17；
* `python3 ops/mk_instances.py --build` → **130 建、0 红**（3.1 秒）；
* `s4-cor-01` 的 4 个实例真出夹具，两条 sha 与出集逐字节对上（见 §6）；
* `python3 ops/freeze_v10.py --instances-dry` → 实例层漂移报告（不写盘、不推版本）；
* `pytest ops/test_instances.py`。
