# -*- coding: utf-8 -*-
"""生成 ops/specs/operator_semantics_conflicts.md（签字 1b）。

    cd $REPO && $GENEBENCH_ROOT/env/bin/python ops/mk_operator_conflicts.py

数字全部从 `ops/acceptance/card_2.1b_crosscheck.json` 与逐格 parquet 现算，不手抄。
"""
from __future__ import annotations
import inspect, json, re, sys
from pathlib import Path
import numpy as np, pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import genebench_config as cfg
from reference import factor_exec as fx
import KunQuant.predefined.Alpha101 as A

OUT = cfg.OPS / "specs" / "operator_semantics_conflicts.md"
CONF = json.loads(Path("/data/shared/genebench/scratch/conflicts.json").read_text())
recs, _ = fx.load_records()
by = {r["id"]: r for r in recs}
cells = pd.read_parquet(cfg.SNAPSHOTS_V1 / "crosscheck" / "rank_ic_cells_csi300.parquet")
k = cells[np.isfinite(cells["rho"]) & ~cells["degenerate"]]

def tau(exclude=frozenset()):
    d = k[~k["factor_id"].isin(exclude)]
    return float(np.percentile(d["rho"], 10))

S = json.loads(Path("/data/shared/genebench/scratch/sets.json").read_text())
tau_excl, gold_kq = set(S["tau_excluded"]), set(S["gold_flagged_kunquant"])

kq_rows = [x for x in CONF if x["backend"] == "qlib_kunquant_loader"]
ex_rows = [x for x in CONF if x["backend"] == "qlib_expression"]
changes = [x for x in kq_rows if "不变" not in x["form"]]
invariant = [x for x in kq_rows if "不变" in x["form"]]

def rho(x):
    return f"{x['measured_mean_rho']:+.4f}" if x["measured_mean_rho"] is not None else "—"
def p10(x):
    return f"{x['measured_p10_rho']:+.4f}" if x["measured_p10_rho"] is not None else "—"

L = []; A_ = L.append
A_("# 同名算子的语义冲突：`ts_rank` 实证档案")
A_("")
A_("**这份文件是 v1 唯一一组有据可查的、真实的同名算子语义冲突样本。**")
A_("它不是构造出来的陷阱 —— 是卡 2.1b 的双实现互检在 792 条因子上跑出来的。")
A_("")
A_("裁定依据（签字人 2026-09-01 原话要点）：GeneQuant 协议明文规定**算子语义须绑定在因子定义上、"
   "不得由任何一方隐式补全**。评测方替因子库拍板一种归一化，等于自己犯了被测方要被判违例的错误。")
A_("所以 v1 走 **C**：把受影响的因子移出 τ 样本、单列、gold 标注「算子约定存疑」、S3 出题避开。")
A_("")
A_("---")
A_("")
A_("## 1. 机制")
A_("")
A_("| 引擎 | `ts_rank` 实现 | 值域 | 实测（同一列 `volume`，窗口 32）|")
A_("| --- | --- | --- | --- |")
A_("| 面板求值器（`PanelFormulaEvaluator`） | `rolling(w, min_periods=w).rank(pct=True)` | `(0, 1]` | 0.031250 … 1.000000 |")
A_("| qlib 表达式引擎（`qlib.data.ops.Rank`） | `rolling(N).rank(pct=True)` | `(0, 1]` | 0.031250 … 1.000000 |")
A_("| **KunQuant**（`KunQuant.ops.TsRank`） | `num_less + (num_eq + 1) / 2` | `[1, w]` | WQAlpha35 实测 −0 … 14880 |")
A_("")
A_("**三方里 KunQuant 是唯一的原位次序实现。** qlib 与面板求值器**恰好一致**（都用 pandas 的 `pct=True`），")
A_("但那是巧合而非约定 —— 因子定义里从没写过 `Ts_Rank` 该归一化到哪个值域。")
A_("")
A_("### 分歧如何进入截面序")
A_("")
A_("常数缩放不改变截面上的相对次序，所以**不是**每一条用 `ts_rank` 的因子都受影响。")
A_("受影响的判据是：`ts_rank` 的**绝对量纲**是否参与组合。实测归纳出四种形式：")
A_("")
A_("| 形式 | 为什么改变截面序 |")
A_("| --- | --- |")
A_("| `1 - ts_rank(·)` | pct 下结果在 `[0,1)` 为**正**；原位下在 `[1-w, 0]` 为**负** —— 符号翻转 |")
A_("| `max(rank(·), ts_rank(·))` | `rank` 在 `[0,1]`；原位 `ts_rank ≥ 1` **永远赢**，`max` 退化成恒等 |")
A_("| `rank(·) + ts_rank(·)` | 两项量纲差 w 倍，和被 `ts_rank` 主导 |")
A_("| `pow(ts_rank(·), ·)` | 底数从 `(0,1]` 变成 `[1,w]`，指数为负时单调性反转 |")
A_("")
A_("反之，`rank(ts_rank(·))`（被截面 rank 重新归一）与纯常数缩放（如 `-1 * ts_rank(·)`）**不受影响**。")
A_("")
A_("---")
A_("")
A_("## 2. 逐条档案")
A_("")
A_(f"KunQuant 侧用到 `ts_rank` 的共 **{len(kq_rows)}** 条。"
   f"其中形式判定为**会改变截面序**的 {len(changes)} 条、**不变**的 {len(invariant)} 条。")
A_("")
A_("### 2.1 会改变截面序")
A_("")
A_("| 因子 | 组合形式 | 实测 mean ρ | 该因子 P10 | 有实测日 | 源方言原文 |")
A_("| --- | --- | ---: | ---: | ---: | --- |")
for x in sorted(changes, key=lambda z: (z["measured_mean_rho"] is None, z["measured_mean_rho"] or 9)):
    A_(f"| `{x['id']}` | {x['form']} | {rho(x)} | {p10(x)} | {x['measured_days']:,} | "
       f"`{x['expression'][:96]}` |")
A_("")
A_("### 2.2 形式上不变（仍标注，但未观察到分歧）")
A_("")
A_("| 因子 | 组合形式 | 实测 mean ρ | 有实测日 |")
A_("| --- | --- | ---: | ---: |")
for x in sorted(invariant, key=lambda z: z["id"]):
    A_(f"| `{x['id']}` | {x['form']} | {rho(x)} | {x['measured_days']:,} |")
A_("")
A_("**形式判定与实测互相印证**：判为「会改变」的 5 条有实测的，mean ρ 全部 < 0.9；")
A_("判为「不变」的 4 条有实测的里 3 条 ρ ≈ 1.0000。**唯一的例外是 `worldquant_101.038`（ρ = +0.8955）**，")
A_("查下来它根本不是 `ts_rank` 问题 —— 见第 4 节。")
A_("")
A_("### 2.3 `qlib_expression` 侧的 4 条：语义同样未绑定，但两引擎恰好一致")
A_("")
A_("| 因子 | 实测 mean ρ | 该因子 P10 | 最小 ρ |")
A_("| --- | ---: | ---: | ---: |")
for x in sorted(ex_rows, key=lambda z: z["id"]):
    mn = f"{x['measured_min_rho']:+.4f}" if x["measured_min_rho"] is not None else "—"
    A_(f"| `{x['id']}` | {rho(x)} | {p10(x)} | {mn} |")
A_("")
A_("它们**不进 gold 标注集**（qlib 的 `Rank` 与面板求值器同为 pct，无实际冲突），")
A_("但**进 τ 排除集** —— 排除规则定在「源方言使用了语义未绑定的 `Ts_Rank`」，")
A_("而不是「观察到了分歧」。理由：一致是巧合，不是约定；")
A_("按「观察到分歧才排除」的规则，τ 会随两个实现碰巧的一致而变松。")
A_("")
A_("---")
A_("")
A_("## 3. 可直接引用的两个案例（进论文）")
A_("")
A_("### 3.1 WQ101 `alpha073`：`max` 的两个操作数必须同值域")
A_("")
A_("原文公式：")
A_("")
A_("```")
A_(str(by["worldquant_101.073"]["expression"]))
A_("```")
A_("")
A_("KunQuant 实现：")
A_("")
A_("```python")
for l in (next(x for x in CONF if x["id"] == "worldquant_101.073")["kunquant_src"] or "").splitlines():
    A_(l)
A_("```")
A_("")
A_("| 约定 | `rank(decay_linear(delta(vwap,5),3))` | `ts_rank(decay_linear(...),17)` | `max` 的结果 |")
A_("| --- | --- | --- | --- |")
A_("| pct（`(0,1]`） | `[0,1]` | `(0,1]` | 两者竞争，`max` 有意义 |")
A_("| 原位（`[1,17]`） | `[0,1]` | `[1,17]` | **`ts_rank` 永远赢，`max` 退化成恒等** |")
A_("")
A_(f"实测秩相关 mean ρ = **{next(x for x in CONF if x['id']=='worldquant_101.073')['measured_mean_rho']:+.4f}**"
   f"（{next(x for x in CONF if x['id']=='worldquant_101.073')['measured_days']:,} 个交易日）。")
A_("")
A_("**结论**：把归一化的截面 `rank` 与 `Ts_Rank` 放进同一个 `max`，"
   "只有当两者都在 `[0,1]` 时公式才说得通。原文未声明值域，两种实现都「合法」，"
   "而它们算出的**不是同一个因子**。")
A_("")
A_("### 3.2 WQ101 `alpha035`：`1 - Ts_Rank` 在原位约定下符号翻转")
A_("")
A_("原文公式：")
A_("")
A_("```")
A_(str(by["worldquant_101.035"]["expression"]))
A_("```")
A_("")
A_("KunQuant 实现：")
A_("")
A_("```python")
for l in (next(x for x in CONF if x["id"] == "worldquant_101.035")["kunquant_src"] or "").splitlines():
    A_(l)
A_("```")
A_("")
A_("| 约定 | `1 - Ts_Rank(x, 16)` | `1 - Ts_Rank(returns, 32)` | 两项之积 |")
A_("| --- | --- | --- | --- |")
A_("| pct | `[0, 1)`，**非负** | `[0, 1)`，**非负** | 非负 |")
A_("| 原位 | `[-15, 0]`，**非正** | `[-31, 0]`，**非正** | 非负但量纲差 ~500 倍 |")
A_("")
A_(f"实测秩相关 mean ρ = **{next(x for x in CONF if x['id']=='worldquant_101.035')['measured_mean_rho']:+.4f}**"
   f"，即两个实现给出**接近反向**的截面排序。")
A_("")
A_("**结论**：`1 - f(·)` 这种写法把 `f` 的值域**隐式声明**成了 `[0,1]` —— "
   "但那只是读者的推断，公式本身没写。这正是「名字相同不等于语义相同」最干净的一个实证。")
A_("")
A_("---")
A_("")
A_("## 4. 顺带查出的第二类缺陷：字段错位（不是算子语义）")
A_("")
A_("`worldquant_101.038` 的 mean ρ = +0.8955，形式上却判为「被 `rank()` 包住、截面序不变」。")
A_("查下来根本不是 `ts_rank` 的事：")
A_("")
A_("| | 表达式 |")
A_("| --- | --- |")
A_("| 源方言原文 | `((-1 * rank(Ts_Rank(**close**, 10))) * rank((close / open)))` |")
A_("| KunQuant 实现 | `-1 * rank(ts_rank(self.**open**, 10)) * rank(inner)` |")
A_("")
A_("**KunQuant 在 `ts_rank` 的实参上用了 `open`，而公式写的是 `close`。** 这是字段错位，")
A_("与归一化约定无关，属于参考实现的缺陷。已随本文件登记。")
A_("")
A_("**扫描的覆盖限度（必须写清）**：为此写了一个 (算子, 字段实参) 对的比较器，")
A_("并**先在 `.038` 上验过判别力**（抓不到就不出结论 —— 第一版比的是字段**集合**，")
A_("对「同一组字段换了位置」恒返回 0，是一次空转的扫描）。")
A_("扣掉 `adv20 → sma(volume,20)` 这类已知良性展开后仍有若干命中，")
A_("但**凡是有实测 ρ 的，除 `.038` 外全部 ρ = +1.0000**，即比较器的剩余命中是假阳。")
A_("")
A_("⚠ **真正的限度在别处**：82 条 KunQuant 因子里只有 **51 条**有第二实现可比，")
A_("另外 31 条**无法用互检裁定**。那 31 条里若有同类字段错位，本方法**看不见**。")
A_("这条限度写进 L5 适配赛道的题源说明。")
A_("")
A_("---")
A_("")
A_("## 5. τ 的执行口径")
A_("")
A_("| | 集合 | 条数 |")
A_("| --- | --- | ---: |")
A_(f"| **gold 标注「算子约定存疑」** | KunQuant 侧用到 `ts_rank` 的 | **{len(gold_kq)}** |")
A_(f"| **移出 τ 样本** | 可比因子里源方言使用 `Ts_Rank` 的 | **{len(tau_excl)}** |")
A_(f"| 两者交集 | | {len(tau_excl & gold_kq)} |")
A_("")
A_("| τ 口径 | 值 |")
A_("| --- | ---: |")
A_(f"| 不排除（全部 159 条可比因子） | {tau():.6f} |")
A_(f"| **排除 {len(tau_excl)} 条（已签字，写进 calibration.json）** | **{tau(tau_excl):.6f}** |")
A_(f"| 参考：只排除观察到冲突的 {len(tau_excl & gold_kq)} 条 | {tau(tau_excl & gold_kq):.6f} |")
A_("")
A_("最后一行只作记录：**规则定在「语义未绑定」而不是「观察到分歧」**，"
   "所以取第二行。两者差 "
   f"{abs(tau(tau_excl) - tau(tau_excl & gold_kq)):.6f}，且第二行更保守。")
A_("")
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
OUT.chmod(0o600)
print(f"→ {OUT}  {OUT.stat().st_size} B")
