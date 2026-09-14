# materiality screen 接线方案（可执行）

综合四份现场调查（S3+S4 / S5+S6 / S7+S8 / S1+S2）而成。目标：把 `ops/run_materiality_screen.py`
从「第一步就 `return 2`」变成「今天能跑的都跑出数、跑不了的把缺口写在报告里」，且**不伪造 runner**
（脚本 :20-22 的自我约束）、**不改 f01 上任何文件**（本文件本身只是方案）。

**行号说明**：正文行号取自四份调查的现场取证与本机 `gb2/out/` 镜像（2026-09-03）。落地前逐处
`grep -n` 对一眼再动手 —— 本方案在每处给了 grep 锚点，锚点比行号可靠。

---

## 1. 今天能跑的 / 跑不了的

### 表 A — 今天能跑出数的（4 行）

| # | 阶段·字段 | 今天能跑到哪一步 | 需要的改动 | 机时 | 结论能进 `DIVERGENCE_EVIDENCE` 吗 |
|---|---|---|---|---|---|
| A1 | **S6 · rebalance_frequency** | 三份 B 直接吃这个参数（`run(freq, …)` 的 freq 就是它），九份产物已在快照里。实测 81 个比较中 **64 处超带** → material | **零补丁**。只需脚手架 §2 的四处改动 | Gate0 4s + 跑 4s ≈ **10s** | ❌ 还不能。① A 缺席（lane 只有 B1/B2/B3）；② 产物空间错位：B 出的是 S7 回测指标，S6 要判的是 `targets`/`cash_ratio`，题面 `tolerance.kind=exact`。要记进证据表须先签字接受口径替换（§7-③） |
| A2 | **S7 · sell_rule** | 三份 B 各打 1 行补丁即可按两个取值跑。实测三份**全部 material**（b1 六项超带：`ann_return_gross` rel 0.4460% vs ε 0.2372% 等） | 补丁 **P-SELL-01/02/03**（§4.2） | Gate0 3s + Gate1 3s + 跑 **6.98s** ≈ **13s** | ⚠️ 部分。证据表里登记的 **22.69%** 是 **A↔B** 的差，不是同实现换取值的 0.28–0.45%。**两类数不得混用**（Gate 2 与 §8-③）。A 侧补齐前只能作为佐证 |
| A3 | **S7 · first_rebalance_day** | 三份 B 各打 1–2 行补丁。daily 下两取值**逐位相同**（rel 全 0）→ immaterial；weekly 下 rel 5.23–5.34% → material | 补丁 **P-FRD-01/02/03**（§4.3） | daily **7s**（+ weekly 对照组 7.7s） | ❌ 不需要进。这是**预期的 immaterial**，正好落在 `FIELD_MATERIAL_WHEN['first_rebalance_day']`（schema.py:77-79）上。它的价值是当**阴性对照**（Gate 3） |
| A4 | **S3 · eval_frequency** | A（`factor_exec`）+ B（`factor_crosscheck` 的 `PanelFormulaEvaluator`）经新适配层可出数：daily 跨实现最大相对差 5.019e-02、weekly 5.464e-02 | 新写 **`ops/screen_adapters/s3_factor.py`**（§4.5，A/B 源文件一行不改） | 单次全量 **15.5s**，两候选字段 < 20s | ❌ 不能。① B 只有 **1 份**（要 3 份）；② 判据是 **τ**（面板秩相关下限），不是逐指标带 → `Band` 抛 `BandUndecided` → 记 inconclusive |

> **重要**：A1–A4 没有一行满足签字裁定的「A + 三份 B」跑法。报告里必须显式记 `implementations`
> 与 `signoff_complete=false`（§2.5），退出码不得为 0。`probe_materiality_verified` 今天**保持 false**。

### 表 B — 今天跑不了的，按缺口分类

缺口四类：**缺实现**（没有可跑的 A/B）、**缺参数**（实现存在但读不到这个字段）、**缺 gold/数据**
（数据、快照、网关等运行前提）、**缺 ε 带**（没有可用判据）。

| # | 阶段·字段 | 缺实现 | 缺参数 | 缺 gold/数据 | 缺 ε 带 | 最小解锁路径 |
|---|---|---|---|---|---|---|
| B1 | **S1 · data_version** | ✅ A 接错阶段（`run_backtest`，实测 `TypeError: unexpected keyword 'stage'`）；真 A 是 TODO 骨架；**B 零份** | ✅ 网关全部 Query 参数无版本维度；`templates/S1/source_status/solve.py` 里该字段 `grep -c` = **0** | ✅ 只有 `v1` 快照（`SNAPSHOT_VERSION='v1'`），无 v2；网关未起（18080 无监听） | ✅ `tolerance.kind=exact`；ε 表只覆盖 9 个 S7 回测指标 | 造 v2 快照 + 给网关加版本维度 + 写三份取数实现 + 给 S1 定数值判据。**属新工程** |
| B2 | **S2 · adjust** | ✅ B 零份（三份 B 吃的 `close` 已是后复权价，复权是输入常量不是参数） | ❌ A 侧 `templates/S2/cor_01/solve.py` 已有三分支（`:45`、`:56-62`），可用 | ✅ `market_view_v1` 在 f01 侧未注册；`reference/tasks/` 不存在；网关未起 | ✅ `exact`；**且 payload 里没有一个数值量对 adjust 敏感** —— 实测三取值 `rows/n_symbols/n_dates/missing` 逐位相同（41700/300/139/44），只有 `sha256` 变，而哈希不是数 | 先给 S2 定「对复权敏感的数值判据」（否则四实现全就位也必判 immaterial），再写三份面板对齐实现 |
| B3 | **S2 · missing_row_policy** | ✅ 同上 | ⚠️ A 有三分支但 **`forward_fill` 是坏的**：`groupby("code").ffill()` 丢掉分组列 → 下一行 `KeyError: "['symbol'] not in index"`（§4.6） | ✅ 同上 | ✅ `exact`；唯一真变的数值量 `rows`（41700 vs 41656）没有标定值；`keep_missing` 与 `forward_fill` 之间连 `rows` 都不变 | 修 §4.6 两处 → 再补 B → 再定判据 |
| B4 | **S3 · lookback** | ⚠️ A 有、B 只有 1 份 | ✅ **两份实现都不读它** —— `gtja_191.046` 的窗口 `(3,6,12,24)` 写死在表达式串里，`declared.lookback=24` 只是最大值；`VALUE_GRID` 给的 (10,20) 还都比题面小 | ❌ gold 面板齐 | ✅ τ，同 A4 | **建议摘掉**（§7-⑤），或把它改接到真的被读的量（`factor_exec.WARMUP_DAYS` 或 solve.py 的暖机截断）。否则测出的分叉是我们适配层的分叉 |
| B5 | **S4 · holding_periods** | ✅ **A 与 B 全部 0 份**：五个 `templates/S4/*/solve.py` 全是 `NotImplementedError`；`scorer/__init__.py` 只有 189 字节注释；三份 B 是回测器不产 IC | ❌ 新写即天然有 | ❌ gold 面板齐（实测 1.7s 端到端跑通最小 IC） | ✅ IC 七量（mean/std/ICIR/positive_ratio/coverage/CI）在 ε 表里一个都没有；本题 `kind=none` | **先改网格再谈实现**：`VALUE_GRID` 的 `([1], [1,5,20])` 在 payload 口径 `by_h[str(min(...))]` 下 **min 都等于 1**，实测两取值逐位相同（mean=-0.005606、icir=-0.7308）→ 必判 immaterial。改成 `([1],[20])` 或改 payload 口径，二选一 |
| B6 | **S4 · ic_method** | ✅ 同上（0 份） | ❌ 新写实现里就是一个 rank 与否的分支（约 2 行） | ❌ 无 | ✅ 同上 | **建议扶正为 S4 主探针字段**：实测单实现内 pearson vs spearman 的 mean IC 差 3 倍（-0.016681 vs -0.005606）、ICIR -2.3414 vs -0.7308。比 `holding_periods` 靠谱得多 |
| B7 | **S5 · signal_frequency** | ✅ A **结构性不存在** —— 唯一的 S5 oracle 在注释里明确拒绝降采样（`freq_unstated/solve.py:99-100`）；B 零份（三份 B 的 `freq` 是 **rebalance**_frequency） | — | ✅ 网关未起；`work/inputs/` 整个目录不存在 | ✅ `exact`；`schema.py` 把 ε 限死 S7；ε 指标与 S5 payload（`signals`/`coverage`）零交集 | 新写两份以上独立 S5 信号实现 + 定 S5 可比指标 + 标 S5 的带。**属新工程** |
| B8 | **S5 · direction** | ✅ 全仓 5 处命中全是声明表/措辞表，**无一处执行路径** | — | — | ✅ 同上 | **先做 E9d 静态裁定**：题面措辞是「方向约定」（`render.py:127`），很可能属规范化默认。跑了也必然 immaterial（`materiality.py:132-135` 要求拒绝入集） |
| B9 | **S6 · weighting_scheme** | ✅ 无执行路径（权重硬编码等权：`cor_ledger/solve.py:112-116`、`impl_v2_b1.py:218-219`） | ✅ **`feasible_values("weighting_scheme")` 实测返回 `()`** —— 既不在 `DECLARATION_ENUMS` 也不在 `VALUE_GRID` → `materiality.py:77-79` 短路成 inconclusive，**一次实现都不跑**，而 `run_materiality_screen.py:134` 要求全部 material → 它现在挡着 S6 翻锁 | — | ✅ `exact` | 补一行可行值只把 inconclusive 变成 immaterial。**建议按 E9d/E9d4 摘掉**（题面写着「入选标的等权」，答案在题面里），像 S1 摘 `calendar_id`、S7 摘 `permitted_operations` 那样附理由 |
| B10 | **S7 · sell_rule 的 A 侧** | ✅ qlib `TopkDropoutStrategy` 没有 `dropped_from_target` 开关（`method_sell` 只有 `bottom`/`random`，卖出候选集写死） | — | — | ❌ daily 带 usable=true，指标名与 A 的 `metrics()` 对得上 | 新写策略子类 ~60 行 + `run_backtest` 加直通参数（§4.7），默认必须保持 `worst_n_drop` 否则 `ops/test_underdetermination_guard.py:36-60` 会红 |
| B11 | **S8 · slippage_reference_price** | ✅ **整个被测对象不存在**：网关无 `/sim/*`（只挂 market+reference 两个 router）；`s8_state_endpoint=false`；oracle 的 HTTP 客户端是 `raise NotImplementedError`；B 零份 | — | ✅ 模拟盘、审计日志、`as_of`/`sim_date` 耦合全缺 | ✅ 本题 `kind=exact`；ε 产物全是 S7 指标，`slippage_bps`/`fill_rate` 没有登记 | 按 `s8_state_contract.md:113-118` 的四条先落地，再重写 oracle（现骨架的探针字段还写着 `calendar_id`，端点还是 `/orders`，**已过期**），再写实现。**属新工程** |

---

## 2. 脚手架：`ops/run_materiality_screen.py` 与 `genetask/materiality.py` 的五处必改

四份调查一致命中同一批 bug。**五处要一起改** —— 只改一处会把「明显停下」变成「跑到一半崩」，后者更难看出问题。

### 2.1 改动一：`IMPL_CANDIDATES` → 按阶段的实现规格（B 是脚本不是库）

现状（`:41-46`）按**包名** import，九个名字实测全部 `ModuleNotFoundError`：
`reference.backtest_b{1,2,3}` / `reference.impl_b{1,2,3}` / `reference.b{1,2,3}`。
真身是 `/data/shared/genebench/snapshots/v1/epsilon/impl_v2_b{1,2,3}.py` —— **脚本**，在 `reference/` 之外、
不在 `sys.path` 上，且用模块级 `HERE = Path(__file__).resolve().parent` 定位面板。

```diff
 #: 四份实现的候选入口。A = 参考实现；B1..B3 = 卡 2.2b 的三份独立实现。
-IMPL_CANDIDATES: dict[str, tuple[str, ...]] = {
-    "A":  ("reference.backtest",),
-    "B1": ("reference.backtest_b1", "reference.impl_b1", "reference.b1"),
-    "B2": ("reference.backtest_b2", "reference.impl_b2", "reference.b2"),
-    "B3": ("reference.backtest_b3", "reference.impl_b3", "reference.b3"),
-}
-RUN_FN_CANDIDATES = ("run_backtest", "backtest", "run", "evaluate", "main")
+#: B 侧不是包名而是**脚本路径** —— 按包名 import 的九个候选实测全部 ModuleNotFoundError。
+#: 加载与调用一律走 ops/screen_runner.py 的沙箱（复制→打补丁→子进程→读 JSON），见方案 §3。
+from ops.screen_runner import SCRIPTS as B_SCRIPTS      # noqa: E402
+
+#: 每个阶段今天实际可跑的 lane。**不许**把缺席的实现悄悄省掉：lane ≠ MAT.IMPLEMENTATIONS 时
+#: 报告要标 signoff_complete=false，退出码不得为 0（见 :134 的改动）。
+LANE: dict[str, tuple[str, ...]] = {
+    "S6": ("B1", "B2", "B3"),      # A 缺席：真 A 候选 cor_ledger/solve.py 要网关 + 一份不存在的信号 parquet
+    "S7": ("B1", "B2", "B3"),      # A 缺席：qlib 没有 dropped_from_target 开关（§4.7）
+    "S3": ("A", "B1"),             # 只有一份 B（factor_crosscheck 的 PanelFormulaEvaluator）
+}
```

`_resolve()`（`:50-71`）随之只负责 A 侧，或在 lane 里没有 `"A"` 时直接跳过 —— 不要再打印
`[接线] A -> reference.backtest.run_backtest`，那是 **S7 的回测入口**，跟 S1/S2/S3 的语义不搭，
留着只会误导下一个人。

### 2.2 改动二：runner 闭包（`:110-113`）改调沙箱

现状按 `impls[impl](stage=…, declared=…, window=…, universe=…, as_of=…)` 调，而唯一接上的
`reference.backtest.run_backtest(factor_id, conf=None)` 收不到这些关键字 —— 实测
`TypeError: run_backtest() got an unexpected keyword argument 'stage'`，会被 `materiality.py:90-93`
吞成 inconclusive。

**闭包对外的三参形态必须保留**（`materiality.py:89` 按 `run(impl, field, value)` 调，
且 `_takes_two_args` 数的是参数个数，带默认值的 `_task`/`_stage` 不能删到只剩 2 个）：

```diff
-        def run(impl: str, field: str, value, _task=task, _stage=stage):
-            spec = {**_task["declared"], field: value}
-            return impls[impl](stage=_stage, declared=spec, window=_task["window"],
-                               universe=_task["universe"], as_of=_task["as_of"])
+        def run(impl: str, field: str, value, _task=task, _stage=stage):
+            # A 侧（若在 lane 里）走各自的适配器；B 侧一律走沙箱：复制→补丁→子进程→读 JSON。
+            w = WIRING[(_stage, field)]
+            if impl == "A":
+                return A_ADAPTERS[_stage](_task, field, value)
+            freq = value if w["mode"] == "freq" else _task["declared"]["rebalance_frequency"]
+            env = {} if w["mode"] == "freq" else {w["env_key"]: str(value)}
+            return SB.metrics(SB.run(impl, freq, env))
```

配套的字段接线表（放在脚本顶部或 `ops/screen_specs.py`）：

```python
#: (阶段, 字段) → 怎么把取值喂给 B 侧。mode="freq" 直接当 CLI 参数；mode="env" 经补丁开关。
WIRING = {
    ("S6", "rebalance_frequency"): {"mode": "freq", "patch": None},
    ("S7", "sell_rule"):           {"mode": "env", "env_key": "GB_SELL_RULE",           "patch": "P-SELL-01"},
    ("S7", "first_rebalance_day"): {"mode": "env", "env_key": "GB_FIRST_REBALANCE_DAY", "patch": "P-FRD-01"},
}
A_ADAPTERS = {
    "S3": lambda task, f, v: __import__("ops.screen_adapters.s3_factor", fromlist=["run_a"]).run_a(task, f, v),
}
```

### 2.3 改动三：`_band()`（`:74-84`）删掉 `compare`，按 `tolerance.kind` 分流

**这是最危险的一处。** `epsilon_dual` 里 `outside_band` / `is_outside_band` / `beyond_epsilon`
**三个都不存在**，候选表第四个 `compare` 存在 —— 于是 `_band()` 不会停下报错，而是打印
`[接线] ε 带 -> epsilon_dual.compare` 并返回一个签名是 `compare(impl_a: Path, impls_b: dict)` 的批处理入口。
实测 `compare("sharpe_net", 1.0, 2.0)` → `TypeError: compare() takes 2 positional arguments but 3 were given`，
而这个调用在 `materiality.py:113` / `:123` 是**在 try 之外**的，会直接把整轮 screen 崩掉。
脚本 `:20-22` 自己写着「不要为了让它跑通而伪造 runner」—— 把 `compare` 留在候选表里，
正是猜中了一个**名字对、类型错**的东西。

```diff
-def _band():
-    """ε 带判据。用 reference.epsilon_dual 的公开入口；找不到就报出它有什么，不要退化成常数容差。"""
-    import reference.epsilon_dual as e
-    for name in ("outside_band", "is_outside_band", "beyond_epsilon", "compare"):
+def _band(task):
+    """按题面 tolerance 取判据。**compare 已从候选表删除** —— 它收的是结果 JSON 路径
+    （compare(impl_a: Path, impls_b: dict[str, Path])），arity 与语义都不是逐指标带判据。"""
+    import reference.epsilon_dual as e
+    for name in ("outside_band", "is_outside_band", "beyond_epsilon"):
         if callable(getattr(e, name, None)):
             print(f"[接线] ε 带 -> epsilon_dual.{name}")
             return getattr(e, name)
-    pub = [n for n in dir(e) if not n.startswith("_") and callable(getattr(e, n))]
-    raise SystemExit(f"[停] epsilon_dual 没有已知的带判据入口；公开可调用：{pub}\n"
-                     f"    请把正确的入口名补进本脚本的候选表，不要用常数容差代替。")
+    from ops.screen_band import Band
+    print(f"[接线] ε 带 -> ops.screen_band.Band(kind={task['tolerance']['kind']}, "
+          f"tier={task['tolerance'].get('tier')})")
+    return Band(task["tolerance"]).outside
```

`:96` 的 `outside = _band()` 要**挪进 for 循环**（判据随题走：`s7-rob-02` 是 `epsilon/daily`，
`s8-rob-02` 是 `exact`，`s3-rob-02` 是 `tau`，`s4-rob-02` 是 `none`）。

新文件 **`ops/screen_band.py`**：

```python
"""screen 的带判据。形状 = materiality.py 要的 outside_band(metric, a, b) -> bool。

四种 tolerance.kind（schema.py 的 TOLERANCE_KINDS）各走各的：
  epsilon → 读 snapshots/v1/epsilon/epsilon_dual_<tier>.json 的 epsilon_by_metric
  exact   → a != b 即超带（S1/S2/S5/S6/S8 的探针题都是 exact）
  none    → 本题不进结算（s4-rob-02）
  tau     → 面板秩相关下限，形状不是逐指标带（s3-rob-02）
后两种抛 BandUndecided：让整题记 inconclusive 并停下汇报，**不许**退化成常数容差。
"""
from __future__ import annotations
import json
from pathlib import Path
from reference import epsilon_dual as ED

CAL = Path("/data/shared/genebench/snapshots/v1/epsilon")


class BandUndecided(RuntimeError):
    """判据未裁定。按 run_materiality_screen.py:131：「跑不起来」不是「没差别」。"""


def _rel(a: float, b: float) -> float:            # 与 epsilon_dual.py 的 _rel 同式，抄一份避免依赖私有名
    m = max(abs(a), abs(b))
    return abs(a - b) / m if m > 0 else 0.0


class Band:
    def __init__(self, tolerance: dict):
        self.kind = tolerance.get("kind")
        self.tier = tolerance.get("tier", "daily")
        self.table: dict = {}
        if self.kind == "epsilon":
            doc = json.loads((CAL / f"epsilon_dual_{self.tier}.json").read_text())
            if not doc.get("usable"):
                # weekly: ann_return_gross implausible；monthly: 另有 sharpe_net / total_cost
                raise BandUndecided(f"ε 带 {self.tier} 档 usable=false，不许用作判据")
            self.table = doc["epsilon_by_metric"]

    def outside(self, metric: str, a, b) -> bool:
        if self.kind == "exact":
            return a != b
        if self.kind != "epsilon":
            raise BandUndecided(f"tolerance.kind={self.kind!r} 没有逐指标带判据"
                                f"（τ 是面板秩相关下限，none 表示本题不进结算）")
        rec = self.table.get(metric)
        if rec is None:
            raise BandUndecided(f"指标 {metric} 不在 {self.tier} 档 ε 表里（该表只覆盖 9 个回测指标）")
        eps, status = rec.get("epsilon"), rec.get("status")
        if eps is None:
            if status == "no_implementation_freedom":
                return a != b                     # 【待签字 §7-①】按「要求精确相等」处理
            if status == "invalid_below_noise_floor":
                raise BandUndecided(f"{metric} 在噪声底以下，本指标不进比较")
            raise BandUndecided(f"{metric} 的 ε 是 {status} —— 不得用其他指标的 ε 代填，停下汇报")
        return abs(a - b) > eps if ED.tolerance_kind(metric) == "absolute" else _rel(a, b) > eps
```

`BandUndecided` 会从 `materiality.py:113`（try 之外）抛出来，所以**在 screen 的循环里接住**，
落成 inconclusive 而不是 traceback：

```diff
-        rep = MAT.materiality_report(task, run, outside)
-        screen = MAT.screen_candidates(task, S.UNDERDETERMINED_CANDIDATES[stage], run, outside)
+        lane = LANE.get(stage, MAT.IMPLEMENTATIONS)
+        try:
+            rep = MAT.materiality_report(task, run, outside, implementations=lane)
+            screen = MAT.screen_candidates(task, S.UNDERDETERMINED_CANDIDATES[stage], run, outside,
+                                           implementations=lane)
+        except BandUndecided as exc:
+            rep = {"field": (task.get("underdetermined") or [None])[0], "verdict": "inconclusive",
+                   "reason": f"判据未裁定：{exc}", "by_impl": {}, "diffs": [], "cross_impl_divergence": []}
+            screen = {}
```

### 2.4 改动四：`materiality.py:112` 加数值过滤

`for m in sorted(set(per_value[a]) & set(per_value[b]))` 没有按类型过滤，而 A 的 `metrics()`
带字符串键 `total_cost_source`，B 的 `run()` 带字符串 `rebalance_frequency` 与机械计数 `n_days`。
`epsilon_dual` 自己是过滤了的，这里没有。

```diff
-             for m in sorted(set(per_value[a]) & set(per_value[b]))
+             for m in sorted(_numeric(per_value[a]) & _numeric(per_value[b]))
```
```diff
+#: 只比数值指标。字符串键（total_cost_source / rebalance_frequency）与机械计数（n_days）不进比较；
+#: n_days 不比但要**对账**：两个取值下它必须相等，不等说明开关意外改了窗口（见方案 Gate 5）。
+_SKIP = ("n_days", "rebalance_frequency", "total_cost_source")
+
+
+def _numeric(d: dict) -> set:
+    return {k for k, v in d.items()
+            if k not in _SKIP and isinstance(v, (int, float)) and not isinstance(v, bool)}
```

`:122` 的 `cross` 循环同样要换。（若不想动 `genetask/`，退而求其次：在 §3 的
`Sandbox.metrics()` 里就把这些键滤掉 —— 但 A 侧适配器也得记得滤，两处都改不如改一处。）

### 2.5 改动五：lane 不完整时不许返回 0

```diff
-        out[task["task_id"]] = {"probe_field": rep["field"], "verdict": rep["verdict"], "reason": rep["reason"],
+        out[task["task_id"]] = {"probe_field": rep["field"], "verdict": rep["verdict"], "reason": rep["reason"],
+                                "implementations": list(lane),
+                                "signoff_complete": tuple(lane) == MAT.IMPLEMENTATIONS,
+                                "patch_id": WIRING.get((stage, rep["field"]), {}).get("patch"),
+                                "manifest": str(MANIFEST_PATH),
                                 "by_impl": rep["by_impl"], "diffs": rep["diffs"][:20],
```
```diff
-    return 0 if all(v["verdict"] == "material" for v in out.values()) else 1
+    # lane 缺 A 时即便全 material 也不算过 —— 「在我们的参考实现下不 material」≠「对任何合理实现不 material」，
+    # 反过来也一样：三份 B 全 material 不等于四实现都 material。
+    ok = all(v["verdict"] == "material" and v["signoff_complete"] for v in out.values())
+    return 0 if ok else 1
```

---

## 3. B 侧标准路径：复制 → 打补丁 → 子进程 → 读 JSON

### 3.1 为什么走 CLI，而不是 `import` 它们的 `run()`

三份 B 的 `run` 签名互不相同：
`b1 run(freq, panel)` / `b2 run(freq, dates_w, S, top, n_top)`（要先 `load_panel`→`build_window`→`build_targets`）
/ `b3 run(freq, P=None, debug=False)`（且 `main()` **不收 argv**）。
按 `run` 接线要给每份猜内部数据结构 —— 那正是「伪造 runner」的滑坡。

而三份都有一个把结果写成 `out_v2_b<i>_<freq>.json` 的 CLI `main` —— **那就是快照里九份产物的生成路径**。
走 CLI 有一个额外的、很硬的好处：跑之前可以用「未打补丁的副本 diff 快照产物」证明本 harness
没有改变任何实现的行为（**Gate 0**，实测 `/tmp` 重跑与快照 `diff` 全部 IDENTICAL）。

### 3.2 沙箱目录布局与 MANIFEST

```
/tmp/gb_screen/<run_id>/
├── gate0/            # 未打补丁的副本（复现门）
│   ├── B1/impl_v2_b1.py  bt_input_csi300_v2.parquet -> symlink  out_v2_b1_daily.json
│   ├── B2/…  B3/…
├── main/             # 打了补丁的副本（真正出数的那次）
│   ├── B1/…  B2/…  B3/…
└── MANIFEST.json     # 源 sha256 / 补丁 sha256 / 打完补丁的 sha256 / 每次跑的 env、墙钟、产物 sha256
```

`ops/screen_patches/` 里存补丁文本，**跟着仓库走**（补丁入档是 §4.1 契约的一条）。
`snapshots/` 下**一个字节都不改**；跑完 `git status --porcelain` 必须为空。

### 3.3 `ops/screen_runner.py`（新文件，可直接落地）

```python
#!/usr/bin/env python3
"""B 侧三份独立实现是**脚本**不是库：复制到沙箱、打最小补丁、子进程跑、读它自己写出的 JSON。

本模块不修改 /data/shared/genebench/snapshots 下的任何文件，也不改实现的算法 ——
补丁只加一个由环境变量驱动的开关（补丁契约见方案 §4.1）。
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

PY = "/data/shared/genebench/env/bin/python"
SNAP = Path("/data/shared/genebench/snapshots/v1/epsilon")
PANEL = SNAP / "bt_input_csi300_v2.parquet"           # 984,960 行 × 8 列，1824 日 × 540 票，6.4 MB
PATCHES = Path(__file__).resolve().parent / "screen_patches"

#: 每份 B 的调用方式。b3 的 main() 不收 argv —— 一次算三个频率，按需读其中一份产物。
SCRIPTS: dict[str, dict] = {
    "B1": {"src": SNAP / "impl_v2_b1.py", "argv": ["{freq}"], "out": "out_v2_b1_{freq}.json"},
    "B2": {"src": SNAP / "impl_v2_b2.py", "argv": ["{freq}"], "out": "out_v2_b2_{freq}.json"},
    "B3": {"src": SNAP / "impl_v2_b3.py", "argv": [],         "out": "out_v2_b3_{freq}.json"},
}
#: 不进比较的键：字符串与机械计数。n_days 不比但要对账（见 Gate 5）。
SKIP_METRICS = ("n_days", "rebalance_frequency", "total_cost_source")


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


class Sandbox:
    def __init__(self, root: Path, patch: str | None = None):
        self.root, self.patch = Path(root), patch
        self.manifest = {"harness": "ops/screen_runner.py", "patch": patch,
                         "impls": {}, "runs": [], "gates": {}}

    def prepare(self, impl: str) -> Path:
        spec = SCRIPTS[impl]
        d = self.root / impl
        d.mkdir(parents=True, exist_ok=True)
        dst = d / spec["src"].name
        shutil.copy2(spec["src"], dst)                       # 源永远只读
        link = d / PANEL.name
        if not link.exists():
            link.symlink_to(PANEL)                           # 脚本用 HERE = Path(__file__).parent 找面板
        rec = {"src": str(spec["src"]), "src_sha256": sha256(spec["src"])}
        if self.patch:
            pf = PATCHES / f"{self.patch}.{impl.lower()}.patch"
            subprocess.run(["patch", "-p0", "-i", str(pf)], cwd=d, check=True,
                           capture_output=True, text=True)
            rec |= {"patch_file": str(pf), "patch_sha256": sha256(pf),
                    "patched_sha256": sha256(dst)}
        self.manifest["impls"][impl] = rec
        return d

    def run(self, impl: str, freq: str, env: dict[str, str]) -> dict:
        spec, d = SCRIPTS[impl], self.root / impl
        out = d / spec["out"].format(freq=freq)
        out.unlink(missing_ok=True)                          # 不许读上一次的残留
        argv = [a.format(freq=freq) for a in spec["argv"]]
        t0 = time.time()
        proc = subprocess.run([PY, spec["src"].name, *argv], cwd=d, check=True,
                              env={**os.environ, **env}, capture_output=True,
                              text=True, timeout=900)
        rec = json.loads(out.read_text())
        self.manifest["runs"].append({"impl": impl, "freq": freq, "env": env,
                                      "wall_s": round(time.time() - t0, 2),
                                      "out_sha256": sha256(out),
                                      "stderr_tail": proc.stderr[-400:]})
        return rec

    @staticmethod
    def metrics(rec: dict) -> dict[str, float]:
        return {k: v for k, v in rec.items()
                if k not in SKIP_METRICS and isinstance(v, (int, float))
                and not isinstance(v, bool)}

    def dump(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.manifest, ensure_ascii=False, indent=1), encoding="utf-8")


def gate_baseline(root: Path, impls=("B1", "B2", "B3"), freqs=("daily",)) -> list[str]:
    """Gate 0：**未打补丁**的沙箱副本必须复现快照里的产物。harness 自证不改行为。"""
    sb, bad = Sandbox(root / "gate0", patch=None), []
    for impl in impls:
        sb.prepare(impl)
        for f in freqs:
            got = sb.run(impl, f, env={})
            ref = json.loads((SNAP / SCRIPTS[impl]["out"].format(freq=f)).read_text())
            if got != ref:
                bad.append(f"{impl}/{f}")
    sb.manifest["gates"]["baseline_identical"] = not bad
    sb.dump(root / "gate0" / "MANIFEST.json")
    return bad


def gate_patch_neutral(root: Path, patch: str, native_env: dict[str, dict[str, str]],
                       impls=("B1", "B2", "B3"), freqs=("daily",)) -> list[str]:
    """Gate 1：打了补丁、开关取**各自的原读法**时，结果必须与 Gate 0 逐字节相同。
    不相同 = 补丁动了算法，回滚重写（补丁契约 §4.1 第 ③ 条）。"""
    sb, bad = Sandbox(root / "neutral", patch=patch), []
    for impl in impls:
        sb.prepare(impl)
        for f in freqs:
            got = sb.run(impl, f, env=native_env[impl])
            ref = json.loads((SNAP / SCRIPTS[impl]["out"].format(freq=f)).read_text())
            if got != ref:
                bad.append(f"{impl}/{f}")
    sb.manifest["gates"]["patch_neutral"] = not bad
    sb.dump(root / "neutral" / "MANIFEST.json")
    return bad
```

> 若某份 B 的产物里含时间戳或绝对路径，逐字节相等会假红。那时把 Gate 0/1 退化成
> 「除 `generated_at` / `path` 类键外全等」，并**把这个退化写进报告**——不要默默放宽。

---

## 4. 每份实现的最小补丁

### 4.1 补丁契约（怎么改才不污染实现的独立性）

1. **只加开关，不改算法。** 允许的编辑形态只有一种：*把一个已经存在的合取项 / 赋值语句，包进一个
   由模块级常量控制的分支*。禁止改排序键、禁止改 `n_drop` 上限、禁止改可交易性过滤、禁止改预算分配、
   禁止改 rebalance 日历的其余分支。
2. **开关默认值 = 该实现打补丁前的原读法。** 三份 B 的原读法**不一定一致** ——
   `first_rebalance_day` 上 b1/b2 默认 `window_start`（`keep[0]=True` / `mask[0]=True`），
   b3 **没有首日强制**、默认就是 `first_period_end`。默认值按各自原样设，不许对齐。
3. **中性门必须过**（Gate 1）：打了补丁、开关取原读法，产物与快照逐字节相同。不同就回滚。
4. **补丁入档**：文本补丁放 `ops/screen_patches/<patch_id>.<impl>.patch`，进版本库；
   screen 报告逐题记 `patch_id`、`patch_sha256`、`src_sha256`、`patched_sha256`、`env`。
5. **三份补丁互不参考**：环境变量名是**协议**（可以一样），分支写法各按各自的数据结构写；
   不得为了让三份 B 结果一致而互相对齐代码。

### 4.2 P-SELL-01/02/03 — S7 `sell_rule`（每份 1 行，已实测跑通）

三份 B 都把 A-1 的读法写死成 `dropped_from_target`。补丁把「跌出目标组合」这一个合取项做成开关。

**`P-SELL-01.b1.patch`**（`impl_v2_b1.py`；锚点 `grep -n 'buy_day < t'`，约 `:202`）
```diff
--- impl_v2_b1.py
+++ impl_v2_b1.py
@@ 模块头，紧接 HERE / INPUT（约 :32-33）@@
 HERE = Path(__file__).resolve().parent
 INPUT = HERE / "bt_input_csi300_v2.parquet"
+# --- screen 补丁 P-SELL-01：只加开关，不改算法 ---------------------------------
+# 默认 = 打补丁前本实现的原读法。worst_n_drop 只放宽**候选池**；
+# 排序键（-rank2d，:205）、n_drop 上限、可交易性过滤一律不动。
+SELL_RULE = os.environ.get("GB_SELL_RULE", "dropped_from_target")
+# ------------------------------------------------------------------------------
@@ 卖出块（约 :202）@@
-        cand = (hold > 0) & (~is_target[t]) & sellable[t] & (buy_day < t)
+        _pool = np.ones_like(is_target[t]) if SELL_RULE == "worst_n_drop" else (~is_target[t])
+        cand = (hold > 0) & _pool & sellable[t] & (buy_day < t)
```
（若文件头没有 `import os`，补丁一并加上——这是唯一允许的额外编辑。）

**`P-SELL-01.b2.patch`**（`impl_v2_b2.py`；锚点 `grep -n 'np.isin(held'`，约 `:253`）
```diff
-        cand = held[~np.isin(held, tgt)]
+        cand = held if SELL_RULE == "worst_n_drop" else held[~np.isin(held, tgt)]
```
后续 `:254` 的可交易性过滤与 `:258` 的「按信号升序取前 NDROP」不变。

**`P-SELL-01.b3.patch`**（`impl_v2_b3.py`；锚点 `grep -n 'bought_today'`，约 `:215`）
```diff
-        cand = held & ~target_mask[t] & can_sell[t] & ~bought_today
+        _pool = np.ones_like(target_mask[t]) if SELL_RULE == "worst_n_drop" else (~target_mask[t])
+        cand = held & _pool & can_sell[t] & ~bought_today
```
`:223` 的 `lexsort` 选最差 N_DROP 只不变。

**中性门的 native_env**：`{"B1": {}, "B2": {}, "B3": {}}`（三份默认都是 `dropped_from_target`）。
**实测预期**：三份全部 material。b1 `ann_return_gross` worst=0.05559674388 / dropped=0.05534877102
（rel 0.4460% > ε 0.2372%）；b2 与 b3 数值相同（0.05564677668 / 0.0554364186）；各 6 项超带。

### 4.3 P-FRD-01/02/03 — S7 `first_rebalance_day`（1–2 行/份）

**b1**（锚点 `grep -n 'keep\[0\]'`，约 `:153`）
```diff
+FIRST_REB = os.environ.get("GB_FIRST_REBALANCE_DAY", "window_start")   # 原读法
@@
-    keep[0] = True                        # 首日建仓
+    if FIRST_REB == "window_start":
+        keep[0] = True                    # 首日建仓
```
**b2**（锚点 `grep -n 'mask\[0\]'`，约 `:147`）：同形。默认同样 `window_start`。

**b3**（锚点 `grep -n 'return {"daily"'`，约 `:147`）—— 方向**相反**：b3 原本就没有首日强制。
```diff
+FIRST_REB = os.environ.get("GB_FIRST_REBALANCE_DAY", "first_period_end")   # 原读法（与 b1/b2 不同）
@@ return 之前 @@
+    if FIRST_REB == "window_start":
+        weekly[0] = True
+        monthly[0] = True
     return {"daily": daily, "weekly": weekly, "monthly": monthly}
```

> **顺带一条值得登记的发现**：b3 与 b1/b2 在 `first_rebalance_day` 上的默认读法本来就相反 ——
> 一处现成的独立实现分歧。因为 ε 只有 daily 档 usable、而 daily 下它不显现，目前测不出来。
> 建议记进卡 2.2b 的歧义清单（不是 `DIVERGENCE_EVIDENCE`，那里只收实测超带的）。

**实测预期**：daily 下三份**逐位相同**（rel 全 0.0000%）→ 三份 immaterial（阴性对照，Gate 3）；
weekly 下 rel 5.23–5.34% → material，但 weekly 带 `usable=false`，只能当体检不能当结论。

### 4.4 S6 `rebalance_frequency` — 零补丁

`freq` 本来就是三份 B 的 CLI 参数（`run(freq, …)`，`:151` 还会对未知值 `raise ValueError`），
九份产物 `out_v2_b{1,2,3}_{daily,weekly,monthly}.json` 已在快照里。
`WIRING[("S6","rebalance_frequency")] = {"mode": "freq", "patch": None}` 即可。
仍然要跑 Gate 0（沙箱复现），别直接读快照 JSON —— 出处要能自证。

### 4.5 S3 适配层 — 新写 `ops/screen_adapters/s3_factor.py`，A/B 源文件一行不改

两份实现都没有 `eval_frequency` 旋钮（`factor_exec.py` 的 `D.features(..., freq="day")` 写死日频，
`qlib_loader._raw_panels` 也只有日频），但 `phrasebook.yaml` 把 weekly/monthly 定义成
**「只取每周/每月最后一个交易日的截面」= 对日频面板的后置抽样** —— 所以不必改 `factor_exec`
或 `factor_crosscheck`，在适配层里 resample 即可。真正缺的是 **(impl, field, value) → 数值字典**
的折算（`materiality.py:94-97` 要 dict[str, number]，而 `eval_expression` 返回 DataFrame 面板）。

```python
"""S3 的 screen 适配层：把 A/B 的因子面板折成可比的数值字典。不改 A/B 的任何一行。"""
import numpy as np

FREQ_RULE = {"weekly": "W", "monthly": "M"}          # phrasebook: 只取每周/每月最后一个交易日的截面


def resample(panel, freq):
    if freq == "daily":
        return panel
    key = panel.index.to_period(FREQ_RULE[freq])
    last = panel.groupby(key).apply(lambda g: g.index.max())
    return panel.loc[sorted(last)]


def fold(panel) -> dict[str, float]:
    v = panel.to_numpy(dtype="float64")
    fin = np.isfinite(v)
    return {"n_dates": float(panel.shape[0]), "coverage": float(fin.mean()),
            "nan_count": float((~fin).sum()),
            "mean_value": float(v[fin].mean()), "std_value": float(v[fin].std(ddof=1))}
```
A 侧 `run_a` 调 `factor_exec.eval_expression(recs, universe, start, end)`；
B 侧调 `factor_crosscheck` 里的 `PanelFormulaEvaluator`（吃**源方言原文** `r["expression"]`）。
实测：A/B 重叠格 40,845，重叠处 `max|A−B| = 5.96e-08`（两份实现本身是对齐的）。

**注意**：折出的这五个量在 ε 表里一个都没有，题面 `tolerance.kind=tau` —— `Band` 会抛
`BandUndecided`，S3 今天**能出数、不能出结论**。这是诚实的结果，不是 bug。

### 4.6 S2 A 侧的两处修复（不属于 screen，但挡在前面）

`genetask/templates/S2/cor_01/solve.py`，锚点 `grep -n 'groupby("code").ffill'`（约 `:73`）：
```diff
-    panel = panel.sort_values(["code", "date"]).groupby("code").ffill()
+    panel = panel.sort_values(["code", "date"])
+    _cols = ["close", "high", "low", "volume"]
+    panel[_cols] = panel.groupby("code")[_cols].ffill()
```
`DataFrame.groupby("code").ffill()` 会把分组列 `code` 从结果里丢掉，下一行的 rename/取列
抛 `KeyError: "['symbol'] not in index"`。40 题集里 `missing_row_policy` 只用了 `keep_missing` 与
`drop`，所以这个 bug 平时看不见，**screen 跑到第三个可行值时才炸**。

第二处（约 `:69`）：`missing = int(panel["close"].isna().sum())` 在策略分支**之前**算，
所以 `missing_rows.count` 按构造与策略无关（实测三策略恒为 44）。想让它成为判据，得挪到分支之后
或另出一个「策略生效后」的计数。

### 4.7 S7 A 侧的新实现（约 60 行，不属于最小补丁）

qlib `TopkDropoutStrategy.__init__` 的 `method_sell` 只有 `bottom`/`random`，卖出候选集写死为
`sell = last[last.isin(get_last_n(comb, n_drop))]` —— **`dropped_from_target` 在 qlib 里没有对应开关**。
要点：
* 新写子类覆盖 `generate_trade_decision`：先算当日 topk 目标组合，卖出集取
  「持仓 ∩ 非目标 ∩ 可交易」再按分数升序截 `n_drop`；买入、涨跌停、`hold_thresh`、最小成交粒度沿用父类。
* 必须与 `ops/specs/backtest_contract.md` §9 的 A-1 记录逐条对齐 —— 否则它不是「同一份声明的另一种读法」，
  而是第三种读法。
* `run_backtest` 加一个 `sell_rule` 直通参数（`CONFIG` 加键 + 策略构造处传参），
  **默认保持 `worst_n_drop`**，否则 `ops/test_underdetermination_guard.py:36-60` 的 A-1 状态锁
  （`turn_rel < 0.03` 且 `gross_rel > 0.10`）会红。

---

## 5. 跑序与耗时

签字裁定的跑序 **S3 S4 S5 S6 → S1 S2 S7 S8** 原样保留（脚本 `:89` 的 `STAGE_ORDER` 不动）。
八个阶段互不依赖，所以「先跑哪个」只影响报告的可读性，不影响结论；下表是逐阶段今天的实际行为。

### 5.1 命令序列与预期

```bash
cd /data/shared/genebench/repo
ENV=/data/shared/genebench/env/bin/python
# 0) 两道门先跑（不产结论，只证明 harness 与补丁没改行为）
$ENV -m ops.screen_runner --gate0                       # Gate 0：三份 B × daily 复现快照
$ENV -m ops.screen_runner --gate1 P-SELL-01             # Gate 1：补丁中性
$ENV -m pytest ops/test_screen_selfcheck.py -q          # Gate 2：A-1 阳性对照（§6）
# 1) 按签字裁定跑序
for st in S3 S4 S5 S6 S1 S2 S7 S8; do $ENV ops/run_materiality_screen.py $st; done
```

| 序 | 阶段 | 今天跑什么 | 机时 | 预期 verdict |
|---|---|---|---|---|
| 1 | **S3** | `eval_frequency` 经新适配层跑 A + B1（日频面板复用，3 个取值一份面板）；`lookback` 建议先摘 | **15.5–20s** | **inconclusive**（判据是 τ，无逐指标带；且只有 1 份 B）。报告里附实测数：daily 跨实现最大相对差 5.019e-02 |
| 2 | **S4** | 立刻停 | **0s** | **inconclusive**（A 与 B 全 0 份）。附静态结论：`holding_periods` 在现网格下两取值逐位相同，先改网格或改 payload 口径 |
| 3 | **S5** | 立刻停 | **0s** | **inconclusive**（无实现；`direction` 先过 E9d 静态裁定） |
| 4 | **S6** | `rebalance_frequency` 三份 B × 三取值；`weighting_scheme` 短路 | Gate0 4s + 跑 **4s** | `rebalance_frequency` → **material**（预期 64/81 超带），但 `signoff_complete=false`；`weighting_scheme` → **inconclusive**（`feasible_values` 为空） |
| 5 | **S1** | 立刻停 | **0s** | **inconclusive** |
| 6 | **S2** | 立刻停（跑之前先修 §4.6，否则第三个可行值必炸） | **0s** | **inconclusive** |
| 7 | **S7** | `sell_rule` 三份 B × 2 值；`first_rebalance_day` 三份 B × 2 值（daily） | Gate0+Gate1 6s + **6.98s** + **7s** ≈ **20s** | `sell_rule` → **material**（各 6 项超带），`signoff_complete=false`；`first_rebalance_day` → **immaterial**（阴性对照） |
| 8 | **S8** | 立刻停 | **0s** | **inconclusive** |

**今天的总机时 ≈ 55 秒**（含两道门）。**代价从来不是瓶颈**，实现的存在与否才是。

### 5.2 人工工时

| 工作 | 估时 | 产出 |
|---|---|---|
| 脚手架五处改动（§2）+ `ops/screen_band.py` + `ops/screen_runner.py` | **0.5 人日** | 脚本能跑到底、崩不了 |
| 六个 B 补丁 + 归档 + 两道门（§4.2/4.3） | **1 小时** | S6/S7 出数 |
| S3 适配层（§4.5） | **0.5 人日** | S3 出数（结论仍 inconclusive） |
| S2 A 侧两处修复（§4.6） | **15 分钟** | 第三个可行值不炸 |
| **小计：今天能跑的全部跑完并出报告** | **约 1.5 人日** | |
| S7 A 侧新实现（§4.7），含保持 guard 绿 | 约 1 人日；跑时 +65.6s/次 × 4 = **4 分 22 秒** | S7 的 lane 补齐 → `signoff_complete=true` |
| S4 四份 IC 实现 / S5 两份信号实现 / S8 整个模拟盘 | 新工程，不在本方案内 | |

---

## 6. 判别力自检：六道门（确认 screen 不是空转）

**报告出来后逐条核这六项；任一项红，整轮作废，不许翻锁。**

**Gate 0 · 复现门（harness 不改行为）**
未打补丁的沙箱副本跑出的 `out_v2_b*_{freq}.json` 必须与快照逐字节相同（已实测 IDENTICAL）。
红 = 我们的跑法本身改变了实现，后面所有数都不作数。

**Gate 1 · 中性门（补丁不改算法）**
打了补丁、开关取各自原读法，产物仍与快照逐字节相同。红 = 补丁碰了算法（§4.1 第 ①③ 条），回滚重写。

**Gate 2 · 阳性门（已知 material 必须报 material）** ← 这是「不是空转」的主证据
用仓库现存产物 `bt_A_rd1.json`（A 侧）与 `out_v2_b1_daily.json`（B 侧）直接喂**同一条**带判据：

```python
# ops/test_screen_selfcheck.py
import json, pathlib
from ops.screen_band import Band

SNAP = pathlib.Path("/data/shared/genebench/snapshots/v1/epsilon")

def test_band_reports_material_on_the_ab_residual():
    """**判据链的活性检查**（不是 A-1 的证据，N-39）：A↔B 有一个 22.69% 的**未归因残差**，
    量级足够大 —— 判据链活着就必须对它报 material；报 immaterial 或 inconclusive = 判据链坏了。
    注意这里比的是 A 与 B 两份**不同实现**；A-1 / sell_rule 的单独效应是同实现换取值的 0.38–0.45%，
    两类数不得互相替代（见本文件末尾第 3 条与 card_3.2 §3b）。"""
    band = Band({"kind": "epsilon", "tier": "daily"}).outside
    a = json.loads((SNAP.parent / "bt_A_rd1.json").read_text())      # 路径以现场为准
    b = json.loads((SNAP / "out_v2_b1_daily.json").read_text())
    shared = {k for k in set(a) & set(b)
              if isinstance(a[k], (int, float)) and not isinstance(a[k], bool)
              and k not in ("n_days", "rebalance_frequency", "total_cost_source")}
    out = [m for m in sorted(shared) if band(m, a[m], b[m])]
    assert len(out) == len(shared) == 9, f"A-1 应 9/9 超带，实得 {len(out)}/{len(shared)}：{out}"
    gross = abs(a["ann_return_gross"] - b["ann_return_gross"]) / abs(b["ann_return_gross"])
    assert 0.22 < gross < 0.24, f"A↔B 未归因残差应 ≈22.8%（卡 2.2b 记 22.69%），实得 {gross:.2%}"
```
实测复算：9/9 指标超带，毛收益差 **22.82%**、换手差 **0.51%** —— 与卡 2.2b 记的 A↔B 残差
22.69% / 0.51% 一致。**这是判据链的活性检查，不是 A-1 的证据**：`DIVERGENCE_EVIDENCE` 里
`sell_rule` 那条登记的是 screen 的**同实现**差（0.38–0.45%），两者是两个量（N-39）。

**Gate 3 · 阴性门（已知 immaterial 必须报 immaterial，且字段不是死的）**
`first_rebalance_day` 在 **daily** 下必须报 **immaterial**（三份 B 逐位相同，rel 全 0）——
这正是 `FIELD_MATERIAL_WHEN` 的由来；同一字段在 **weekly** 下必须报 **material**（rel 5.23–5.34%）,
证明它不是死的、判据也不是恒 immaterial。（weekly 带 `usable=false`，此格只做体检、不做结论。）

**Gate 4 · 开关生效门（识别空转）**
若某字段所有指标 rel 恰好 0.0000%，而它**不是** Gate 3 的那一格 —— **先怀疑开关没生效**，不要写结论：
① `MANIFEST.json` 里该次 run 的 `env` 是否带上了 `GB_SELL_RULE` / `GB_FIRST_REBALANCE_DAY`；
② 子进程是否继承了它（`subprocess.run(env=…)` 有没有被覆盖）；
③ 补丁的默认分支是不是写反了（b3 的默认与 b1/b2 相反，最容易写反的就是它）；
④ `MANIFEST.json` 里 `patched_sha256 != src_sha256`（补丁真的打上了）。

**Gate 5 · 判据污染门**
报告的 `diffs` 里**不得出现** `total_cost_source` / `rebalance_frequency` / `n_days` 作为被比指标
（出现 = §2.4 没打）。同时对账：两个取值下 `n_days` 必须相等（daily 档 = 1818），
不等说明开关意外改了窗口。

**Gate 6 · 循环论证门**
`cross_impl_divergence` 在 B 内部为空是**预期**：那条带本来就是这三份 B 两两最大差 ×1.5 标出来的
（`compare_pairwise`，`MULTIPLIER=1.5`），拿自己标的带判自己永远判不出分叉。
报告里**必须写明**「本栏在 lane=B-only 时对 B 无判别力，只有 A 接上后才有意义」。
（S6 实测：跨取值 64/81 超带，同取值跨实现 0 处 —— 正是这个现象。）

---

## 7. 落地前要签字的七条口径

1. **`epsilon=None` 的三种 status 各怎么判。** 本方案的读法：`no_implementation_freedom` → 要求精确相等；
   `invalid_below_noise_floor` → 该指标不进比较；`implausible_stop_and_report` → 整档带作废、停下汇报。
   带契约里没写清，这是我们选的口径。
2. **跨取值比较该用哪一档 ε。** ε 是**逐频率**标的（「ε 随调仓频率跨约 3 个数量级」），
   `daily|weekly` 这一对该用哪条带没有定义。S6 的实测用的是「取两端较宽的那条」。
   另：weekly / monthly 两档 `usable=false`，本方案禁止用它们作判据。
3. **S6 的产物空间替代口径。** 三份 B 产的是 S7 回测指标，S6 要判的是 `targets`/`cash_ratio`，
   题面 `tolerance.kind=exact`。那 64 条证据严格说是「`rebalance_frequency` 对**回测结果** material」。
   要写进 `DIVERGENCE_EVIDENCE` 必须签字接受口径替换，或另标 S6 自己的带。
4. **S3 的 τ 判据形状。** τ 是「两份实现的面板做秩相关 ≥ τ」，不是 `outside_band(metric, a, b)`。
   要么给 S3 写一条 τ 版通道，要么承认 S3 今天只能 inconclusive。
5. **三个候选字段的 E9d 静态裁定**（跑之前做，做完可能就不用跑了）：
   `S5/direction`（题面措辞「方向约定」）、`S6/weighting_scheme`（题面写着「入选标的等权」，
   同时触及 E9d4「可行值不得与固定槽内容重叠」）、`S3/lookback`（现有实现都不读它）。
   建议像 S1 摘 `calendar_id`、S7 摘 `permitted_operations` 那样摘掉并附一行理由。
6. **S4 的可行值网格。** `([1], [1,5,20])` 在 `ic_stats = by_h[str(min(...))]` 口径下 min 都等于 1，
   两取值逐位相同。三选一：改网格为 `([1],[20])`；改 payload 让 `ic_stats` 跨 horizon 聚合；
   或把 S4 的探针字段换成 `ic_method`（单实现内实测分叉 3 倍，是更靠谱的探针）。
7. **`probe_materiality_verified` 维持 `false`。** 今天没有任何一个阶段拿到「A + 三份 B」的完整证据；
   `run_materiality_screen.py:131`：任何一题 inconclusive 都不许翻锁 ——「跑不起来」不是「没差别」。

---

## 8. 不要做的五件事

1. **不要把 `compare` 留在 `_band()` 的候选表里。** 它名字对、类型错，会静默绑上去、在第一次比指标时
   把整轮崩掉；而这个异常在 `materiality.py:113` 是 try 之外的，连 inconclusive 都记不成。
2. **不要在 `snapshots/` 里改实现或放补丁。** 快照是冻结物。补丁入档在 `ops/screen_patches/`，
   跑在 `/tmp/gb_screen/<run_id>/`；跑完 `git status --porcelain` 必须为空。
3. **两类数必须分栏，不得互相替代（N-39 之后口径已定）**：`DIVERGENCE_EVIDENCE` 里 `sell_rule` 登记的
   是 **screen 的同实现差 0.38–0.45%**（那才是这个字段的效应量）；A↔B 的 **22.69%** 是另一个量 ——
   一个**未归因残差**，只用作判据链的活性检查。把后者写成 A-1 的证据正是被撤回的那步（附录 AA / N-39）。
4. **不要因为报告里全是 inconclusive 就去翻能力位。** 也不要为了让某题不 inconclusive 而放宽判据 ——
   `BandUndecided` 的正确归宿是 inconclusive + 停下汇报。
5. **不要给缺席的实现补一个「跑起来但什么都不做」的桩。** 如果 A 在某字段上语义里根本没有这个概念
   （如 `first_rebalance_day` 之于 `run_backtest`），正确做法是如实记「该实现无此字段」并把它与
   「跑挂」区分开（今天 `materiality.py:90-93` 把两者一律记 inconclusive，这是一个待改的真问题），
   而不是让它假装跑了两遍同样的东西。
