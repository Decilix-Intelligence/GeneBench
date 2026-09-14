# -*- coding: utf-8 -*-
"""生成 ops/specs/backtest_declaration_underdetermination.md（可引用成稿）。

    cd $REPO && $GENEBENCH_ROOT/env/bin/python ops/mk_declaration_stanza.py

与 `operator_semantics_conflicts.md` **并列** —— 两份是同一论点的两端，都会进论文。
"""
from __future__ import annotations
import glob, itertools, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import genebench_config as cfg

OUT = cfg.OPS / "specs" / "backtest_declaration_underdetermination.md"
E = cfg.SNAPSHOTS_V1 / "epsilon"

A = json.loads((E / "bt_qlib_alpha158.ROC20_baseline.json").read_text())["metrics"]
# 优先用 v2 的产物；没有就用第一轮的
v2 = sorted(glob.glob(str(E / "out_v2_b*_daily.json")))
if len(v2) >= 3:
    BS = {i + 1: json.loads(Path(p).read_text()) for i, p in enumerate(v2)}
    ROUND, FREQ = "v2（声明修订后）", "daily"
else:
    BS = {n: json.loads((E / f"out_b{n}.json").read_text()) for n in (1, 2, 3)}
    ROUND, FREQ = "v1（首轮）", "（声明未写调仓频率，三份都取了 daily）"

def rel(x, y):
    s = max(abs(x), abs(y))
    return abs(x - y) / s if s else 0.0

KEYS = ["ann_return_gross", "sharpe_net", "total_cost", "ann_vol_net",
        "max_drawdown_net", "turnover_two_way_mean", "win_rate_net"]

L = []; P = L.append
P("# 回测声明的欠定性：三份独立实现的实证")
P("")
P("> 与 `operator_semantics_conflicts.md` **并列**。两份是同一论点的两端：")
P("> **因子名不足以确定计算，回测声明不足以确定结果。**")
P("> 两端的分歧在产物层面都表现为「跑通了、有数、看着正常」。")
P("")
P(f"本文数据来自 **{ROUND}**，调仓频率 {FREQ}。")
P("")
P("## 方法")
P("")
P("**独立性由结构保证，不是由承诺保证** —— 这是本实验唯一真正的风险，处理方式有三层：")
P("")
P("1. **声明先落盘，再开始实现。** 顺序是硬要求。"
  "声明（`ops/specs/backtest_contract.md`）写完并归档之后，实现者才拿到它。")
P("2. **实现者拿不到参考实现。** 输入是一份**纯 parquet**（日期/代码/后复权价/复权因子/"
  "成分标志/有价标志/退市标志/信号），**不需要也接触不到 qlib**。"
  "「不看 qlib 源码」因此不是一条自觉遵守的规则，而是**做不到**。")
P("3. **三份实现互不知情。** 它们并行产生，彼此看不到对方的代码与结果。")
P("")
P("凡是声明没写死的点，实现者**自行决定并记录选择与理由**，"
  "**不去查别人怎么做的**。计算结构要求向量化，与参考实现的逐日循环结构不同 —— "
  "**不同的计算结构才能暴露实现自由度**。")
P("")
P("## 结果")
P("")
P("同一份声明、同一份信号、同一段窗口（csi300，2019-01-02 … 2026-07-03，1,818 个交易日）：")
P("")
P("| 指标 | B1 | B2 | B3 | **三份 B 互相最大差** |")
P("| --- | ---: | ---: | ---: | ---: |")
for k in KEYS:
    if k not in BS[1]:
        continue
    bb = max(rel(BS[i][k], BS[j][k]) for i, j in itertools.combinations((1, 2, 3), 2))
    P(f"| `{k}` | {BS[1][k]:.5g} | {BS[2][k]:.5g} | {BS[3][k]:.5g} | **{bb:.2%}** |")
P("")
gross = max(rel(BS[i]["ann_return_gross"], BS[j]["ann_return_gross"])
            for i, j in itertools.combinations((1, 2, 3), 2))
turn = max(rel(BS[i]["turnover_two_way_mean"], BS[j]["turnover_two_way_mean"])
           for i, j in itertools.combinations((1, 2, 3), 2))
P(f"**三份互不知情的实现，在毛收益上互相差 {gross:.2%}，在双边换手上互相差 {turn:.2%}。**")
P("三份都能跑通、都产出完整指标、数值分布都正常，**没有任何一份会自己报错**。")
P("")
P("分歧的来源是声明里**没写死**的点：资金如何分配到买入标的、"
  "可交易性在选股层还是执行层生效、换手的分母取哪一个总资产、"
  "以及（首轮最致命的一条）**调仓频率根本没写**。")
P("")
P("## 结论")
P("")
P("**一份回测声明，即便写明了策略类型、持仓数、换手上限、费率、涨跌停阈值、"
  "结算规则、初始资金与全部指标公式，仍不足以确定回测结果。**")
P("")
P("这与因子层的发现是同一件事的两端：")
P("")
P("| | 因子层 | 回测层 |")
P("| --- | --- | --- |")
P("| 不足以确定计算的东西 | 因子**名**与**表达式** | 回测**声明** |")
P("| 分歧的来源 | 算子语义未绑定值域；实现读错输入字段 | 声明未覆盖的执行细节 |")
P("| 产物层面的表现 | 能算出数、跑得通、数值正常 | 同左 |")
P("| 照出来的唯一手段 | 拿另一个独立实现去对 | 同左 |")
P("")
P("**方法论后果**：可复现的量化研究协议必须把「实现自由度」当成**一等公民**来度量，"
  "而不是假定它可以忽略。具体到评测：判「被测系统的回测是否复现了参考结果」时，"
  "容差不能来自浮点噪声（那会要求比特级相等），"
  "而必须来自**两份独立实现同一份声明的自然分歧** —— "
  "因为被测系统正是这样的第二份实现。")
P("")
P("**一个反面教训值得单独记**：我们最初打算用「同一份代码在不同库版本下重跑的极差」标定容差。"
  "实测跨 4 个 numpy/pandas 组合（含 pandas 1.5.3 → 2.2.3 的大版本跨度）"
  "最大相对极差只有 **8.53e-14**，即纯 float64 舍入。"
  "照它定容差等于要求被测系统与参考实现**比特级相等** —— "
  "而它在数值上看起来「已经标定过了」。")
P("")
cfg.create_dir(OUT.parent)
OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
OUT.chmod(0o600)
print(f"→ {OUT}  {OUT.stat().st_size} B（数据来自 {ROUND}）")
