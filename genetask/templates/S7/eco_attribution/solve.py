# oracle 参考解（数据面私有；在 f01 直跑，经网关 snapshot 后端产 artifact）。gold_token: <<gold_token>>
"""S7-ECO-01 回测复现（经济性：归因守恒 + 成本量纲）—— oracle 骨架。

主干复用 cor_reproduce/solve.py（取数 ②、引擎 ④、指标 ⑤、守恒 ⑥、信封 ⑧）。本题 oracle 把归因 ⑦
按题面口径**显式**算并留证：

  ⑦ 归因（题面口径，与 cor 的 attribution() 同式，这里多导出中间量）：
       total      = ann_return_net
       cost       = ann_return_net − ann_return_gross
       bench_d    = 当日 in_universe & has_price 成分股 post_close 的等权日收益（由 /bars + /adj + /universe 构造）
       beta_hat   = OLS 斜率 r_gross ~ bench（np.polyfit 一次项）
       beta       = beta_hat × ann(bench)
       alpha      = total − beta − cost           ← 守恒由构造保证；残差只来自浮点，必 ≤ 1e-6
     gold/attribution_detail.json 记 {beta_hat, ann_bench, r2, n}。
  ⑤' 成本量纲双算留证（契约 §8 ① / D-06 实例 6）：
       total_cost_abs  = Σ cost_abs / initial_capital          ← artifact 用这个
       total_cost_rate = Σ (cost_abs_d / TA_{d−1})              ← **错误通道**，只写进 gold/cost_channels.json
     两者之比 ≈ 成本加权的 TA_{t−1}/TA_0 调和均值；比值偏离 1 越远，本题对「求和逐日费用率」的判别力越强。
     判据取 **|比值 − 1| ≥ 0.02**（两侧都算）：总资产在窗口内涨，比值就落在 1 以下；
     写成单边 `≥ 1.02` 会把判别力充足的题判成不足（2026-09-05 实测 0.8286）。
     偏离不足则本题 ECO 判别力不足，登记回炉（不是放宽 ε）。
  ⑤'' 盈亏平衡换手（对接决定 §2「cost break-even」，扩展列，不进 artifact）：
       be_turnover = ann_return_gross / (ann_cost_per_unit_turnover)，写 gold/breakeven.json 备用。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# 共用主干在 reference/ 下 —— **不 import 兄弟模板**（D-31 推论）
from reference import s7_oracle_common as cor

# 统一 I/O 契约（裁定 2026-09-05）：读标准位置的任务规格、经网关取数、写标准 artifact 路径。
# **不接受任何 stage 特定的 env/argv** —— 从任务目录读得出来的东西，一律不从环境拿。
from reference.oracle_io import context as _oracle_context
from reference.oracle_io import write as _oracle_write
from reference.oracle_io import write_private as _write_private
CTX = _oracle_context(__file__)


#: 双通道比值偏离 1 至少这么多，本题才对「把逐日费用率求和」这种错法有判别力。
ECO_MIN_DEVIATION = 0.02


def cost_channels(daily: pd.DataFrame, initial_capital: float) -> dict:
    ta_prev = daily.total_assets.shift(1).fillna(initial_capital)
    abs_channel = float(daily.cost_abs.sum()) / initial_capital
    rate_channel = float((daily.cost_abs / ta_prev).sum())
    return {"total_cost_abs": abs_channel, "total_cost_rate_sum": rate_channel,
            "ratio": rate_channel / abs_channel if abs_channel else None}


def attribution_detail(daily: pd.DataFrame, panel: pd.DataFrame, m: dict) -> dict:
    bench = (panel[panel.in_universe & panel.has_price]
             .sort_values(["code", "date"]).groupby("code").close.pct_change()
             .groupby(panel.date).mean().reindex(daily.date).fillna(0.0).to_numpy())
    r_g = daily.r_gross.to_numpy()
    slope, intercept = np.polyfit(bench, r_g, 1)
    resid = r_g - (slope * bench + intercept)
    r2 = 1 - resid.var() / r_g.var()
    ann_bench = float(np.prod(1 + bench) ** (cor.ANN / len(bench)) - 1)
    return {"beta_hat": float(slope), "ann_bench": ann_bench, "r2": float(r2), "n": int(len(bench))}


def main(task_dir: str, arm: str = "strict") -> None:
    from reference import artifact_schema as sch
    from reference.gateway_client import Client
    td = Path(task_dir)
    task = cor.load_task(td)
    gw = Client.for_context(CTX)
    panel = cor.fetch_panel(gw, task, CTX.task_dir)
    daily = cor.run_engine(panel, task["declared"])
    meta = json.loads((td / "work" / "signal.meta.json").read_text(encoding="utf-8"))
    art = cor.build_artifact(task, daily, panel, meta, arm)
    ch = cost_channels(daily, task["declared"]["initial_capital"])
    # 判别力看的是**偏离 1 的幅度**（docstring ⑤' 的原话：「比值偏离 1 越远……判别力越强」），
    # 而原来写的是 `ratio >= 1.02` —— **单边**。实测 ratio = 0.8286：
    # 组合总资产在窗口内是涨的，所以逐日费用率之和**小于**绝对额通道，比值落在 1 以下。
    # 偏离 0.1714 是阈值的 8.6 倍，判别力绰绰有余，却被单边判据判成「不足」。
    # 判据要按它自己写的那句话来（D-28：判据得落在它保护的那一侧）。
    dev = None if ch["ratio"] is None else abs(ch["ratio"] - 1.0)
    ch["deviation_from_one"] = dev
    assert dev is None or dev >= ECO_MIN_DEVIATION, (
        f"成本双通道比值 {ch['ratio']:.4f} 偏离 1 仅 {dev:.4f} < {ECO_MIN_DEVIATION}，"
        f"本题 ECO 判别力不足 —— 登记回炉，不是放宽 ε")
    _write_private(td / "gold" / "cost_channels.json", ch)
    _write_private(td / "gold" / "attribution_detail.json", attribution_detail(daily, panel, art["payload"]["metrics"]))
    v = sch.validate(art, task={k: task[k] for k in ("task_id", "stage", "declared", "underdetermined")})
    assert v.ok, [str(f) for f in v.findings]
    # N-44：逐日台账按契约落盘（`/task/ledger.parquet` 的 gold 侧对应物）。
    # 走 `files_io.write_contracted` 而不是各写一遍 to_parquet ——
    # 五个模板各抄一遍的下场是它们慢慢漂开，而漂开表现为
    # 「同一道题两次 gold 的 sha 不同」，没有任何东西报错。
    from reference.files_io import write_contracted
    write_contracted(daily, "S7", Path(task_dir) / "gold")
    # **标准 artifact 路径**（统一 I/O 契约 D-31）—— 跑批的校验器只看这一处。
    # 只写 gold/ 的话，`run_oracles` 找不到产物，而「找不到」曾被记成「零 finding」。
    _oracle_write(CTX, art)
    _write_private(td / "gold" / "oracle_artifact.json", art)


if __name__ == "__main__":
    main(str(_oracle_context(__file__).task_dir))
