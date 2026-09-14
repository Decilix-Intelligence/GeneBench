# -*- coding: utf-8 -*-
"""S7 五道题共用的 oracle 主干（D-31 推论，2026-09-05 抽出）。

原来它住在 `genetask/templates/S7/cor_reproduce/solve.py` 里，另外四题
`from genetask.templates.S7.cor_reproduce import solve as cor` —— **模板 import 模板**。
落到任务目录的那份因此不是自足的：被 import 的 trunk 永远从**模板目录**执行，
`__file__` 指向模板，统一 I/O 契约当场判「任务规格缺失」（S7 四题实测全倒）。

**共用主干抽到 `reference/` 下，不靠 import 兄弟模板** ——
`ops/test_oracle_contract.py` 有 AST 锁盯着这条。

> **未完成**：`fetch_panel` 的面板拼装仍是 `NotImplementedError`，
> `reference/gateway_client.py` 也还没有。抽取只解决了**自足性**，
> 不代表 S7 的 oracle 能跑 —— 这一点不许被「已抽取」四个字盖过去。
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from reference import gateway_client as gwc


ANN = 252
WARMUP_DAYS = 6          # 契约 §1：面板含 6 天暖机


def load_task(task_dir: Path) -> dict:
    return yaml.safe_load((task_dir / "task.yaml").read_text(encoding="utf-8"))


def trading_window(gw, task: dict) -> list[str]:
    """窗口交易日 + 契约 §1 的 6 天暖机（**交易日**不是自然日）。"""
    w = task["window"]
    lo = (pd.Timestamp(w["start"]) - pd.Timedelta(days=60)).strftime("%Y-%m-%d")
    days = gw.trading_days(lo, w["end"])
    if w["start"] not in days:
        raise ValueError(f"窗口起点 {w['start']} 不是交易日 —— 日历与题面对不上，不许猜")
    i = days.index(w["start"])
    if i < WARMUP_DAYS:
        raise ValueError(f"{lo} 之后只有 {i} 个交易日可作暖机，契约要 {WARMUP_DAYS}")
    return days[i - WARMUP_DAYS:]


def fetch_panel(gw, task: dict, task_dir: Path | None = None) -> pd.DataFrame:
    """经网关拼契约 §1 的八列面板。`gw = reference.gateway_client.Client`。

    三条口径是**实测定的**，不是从注释推的（2026-09-05 对着冻结面板
    `snapshots/v1/epsilon/bt_input_csi300_v2.parquet` 逐格核出来）：

    ① **`factor` 的基准日是 `as_of`，不是窗口末日。**
       `factor = adj_factor(code, d) / adj_factor(code, as_of)`；已退市的票取它自己
       最后一个 `adj_factor`。实测 `SH600000`：窗口末日 adj=16.5935、`as_of` adj=17.3774，
       而面板 `factor` 末值 0.95489 = 16.5935/17.3774 —— 基准日取错，
       全表 `close` 会整体差一个**每票不同**的常数比例，而没有任何一列看得出来。
       代价是取 `/adj` 要取到 `as_of`（**晚于窗口末日**）；这是面板构造里的一处前视，
       已登记 N-80，本函数按冻结面板的既有口径复现，不擅自改。

    ② **`is_delisted` = 日期晚于该票在窗口内的最后一个有价日。** 冻结面板 540 票里
       14 票有 `is_delisted`，与「最后有价日早于面板末日」的 14 票**完全同集**，
       且起始日恰为最后有价日的次一交易日 —— 面板用的就是这条纯操作性规则。
       它把「永久停牌但仍上市」也算成退市（`SH688072` 最后有价日 2026-06-26，
       距面板末日只有 5 个交易日，很可能是停牌），已登记 N-81。

    ③ **`/bars` 与 `/adj` 的日期格式不同**（`YYYY-MM-DD` vs `YYYYMMDD`），
       客户端 `_by_code` 里已归一；这里再 merge。不归一就 merge 得到全 NaN 且不报错。

    面板是**全格**：`日 × 曾入选过的票`（冻结面板 1824 × 540 = 984,960 行整）——
    不是「只留有成分的格」。掉出指数的行必须在（契约 §1 第二形态）。
    """
    days = trading_window(gw, task)
    uni = {d: gw.members(task["universe"], d) for d in days}          # PIT，逐日
    codes = sorted({c for v in uni.values() for c in v})
    lo, hi = days[0], days[-1]

    bars = gw.bars(codes, lo, hi, ["close"])
    adjs = gw.adj(codes, lo, task["as_of"])                          # 到 as_of，见口径 ①

    grid = pd.MultiIndex.from_product(
        [days, [gwc.to_panel_code(c) for c in codes]], names=["date", "code"])
    out = pd.DataFrame(index=grid).reset_index()

    bars = bars.assign(code=bars.code.map(gwc.to_panel_code))
    adjs = adjs.assign(code=adjs.code.map(gwc.to_panel_code))
    base = adjs.sort_values("date").groupby("code").adj_factor.last()  # as_of 当日（或该票最后一个）
    adjs = adjs[adjs.date <= hi]

    out = out.merge(bars[["date", "code", "close"]].rename(columns={"close": "raw_close"}),
                    on=["date", "code"], how="left")
    out = out.merge(adjs[["date", "code", "adj_factor"]], on=["date", "code"], how="left")
    out["factor"] = out.adj_factor / out.code.map(base)
    # 停牌日没有 adj 行；复权因子在停牌期间不变 —— 按票前向填充，再回填上市前的头部。
    out = out.sort_values(["code", "date"])
    out["factor"] = out.groupby("code").factor.ffill().bfill()
    out["close"] = out.raw_close * out.factor
    # 契约 §1 只把 factor 定义成「原始价 = close / factor」—— **无价的格上它没有定义**。
    # 冻结面板在那些格上残留着 qlib 上市窗口内的因子值（46,265 格，全部 close 为空），
    # 三份实现 B 都只在 `close / factor` 里读它，读不到这些格。这里按契约置空，
    # 并由 `ops/acceptance/s7_panel_factor_immaterial.py` 用「喂真改动」证明这处差异不改任何指标。
    out.loc[out.close.isna(), "factor"] = np.nan

    out["has_price"] = out.close.notna()
    last_priced = out[out.has_price].groupby("code").date.max()
    out["is_delisted"] = out.date.gt(out.code.map(last_priced).fillna("")) & out.code.isin(
        last_priced.index[last_priced < hi])

    memb = pd.DataFrame([{"date": d, "code": gwc.to_panel_code(c), "in_universe": True}
                         for d, v in uni.items() for c in v])
    out = out.merge(memb, on=["date", "code"], how="left")
    out["in_universe"] = out.in_universe.notna()

    if declares_signal(task):
        if task_dir is None:
            raise ValueError("题面 inputs 声明了 work/signal.parquet，但没给 task_dir —— "
                             "不许在这里退化成全 NaN 的 signal 列")
        out = out.merge(load_signal(Path(task_dir)), on=["date", "code"], how="left")
    else:
        out["signal"] = np.nan
    # ④ **`close`/`factor` 落 float32** —— 这一条不是省空间，是可比性的一部分。
    #
    #    冻结的 ε 面板存的就是 float32，而 ε 是在它上面标定的。经网关拼出来的是 float64
    #    （两位小数的 close × 四位小数的 adj_factor，float64 里算完还是 float64），
    #    两者逐格只差 ~6e-08 —— 但回测里有**整手取整**这个不连续算子，
    #    它把 1e-8 的价差放大成「多买一手/少买一手」。2026-09-05 实测：
    #    光是这个 dtype 差别就吃掉 `turnover_two_way_mean` **33.8% 的 ε 预算**
    #    （`ops/reports/s7_panel_dtype_effect.json`）。
    #
    #    降到 float32 之后，与冻结面板**逐位相同**：935,979 个有价格的格，
    #    `close` 与 `factor` 的最大 ULP 差都是 **0**。于是 S7 的 gold 从
    #    「落在 ε 带内」升级成「逐位可复现」，`s7_panel_vs_frozen` 那条验收也跟着
    #    从容差比较改成**逐位相等**。
    #
    #    `signal` 保持 float64（冻结面板里它本来就是 float64）。
    out["close"] = out["close"].astype("float32")
    out["factor"] = out["factor"].astype("float32")
    cols = ["date", "code", "close", "factor", "in_universe", "has_price", "is_delisted", "signal"]
    return out[cols].sort_values(["date", "code"]).reset_index(drop=True)


def declares_signal(task: dict) -> bool:
    """题面 `inputs` 里有没有声明 `work/signal.parquet`。

    **不能靠「文件在不在」判断** —— 文件不在正是要报的那件事（N-84：
    `s7_dedicated_signal_v1` 这份夹具还没生成）。判据要落在题面上，不落在磁盘上。
    """
    return any(str(i.get("path", "")).endswith("work/signal.parquet")
               for i in (task.get("inputs") or []))


def load_signal(task_dir: Path) -> pd.DataFrame:
    """`work/signal.parquet`（题面 `inputs` 声明的专用信号 `s7_dedicated_signal_v1`）。"""
    f = task_dir / "work" / "signal.parquet"
    if not f.exists():
        raise FileNotFoundError(f"{f} 不存在 —— 题面 inputs 声明了它；缺输入不许拿 NaN 顶上")
    df = pd.read_parquet(f)
    return df[["date", "code", "signal"]].assign(date=df.date.astype(str))


def run_engine(panel: pd.DataFrame, declared: dict) -> pd.DataFrame:
    """④ 实现 B。返回逐日表，列见 `cor_reproduce/solve.py` docstring ④。

    **当前阻塞（N-83）**：`reference/backtest.py` 里只有**实现 A**（qlib `TopkDropoutStrategy`），
    `run` 与 `config_from_declared` 都不存在。契约开篇写死了「实现 B 不得阅读 qlib 的
    exchange/executor/strategy」—— 拿 A 当 gold 会让 ε 虚小（N-27 实测 A 与 B 的
    `ann_return_gross` 差 1.22pp/年）。实现 B 存在，但是三份互相独立的**脚本**
    （`snapshots/v1/epsilon/impl_v2_b{1,2,3}.py`，签名各异），选哪一份当 gold 是待裁的事。

    所以这里**明说阻塞**，不 fallback 到 A —— 悄悄换成 A 的话，S7 五道题会照常出数、
    照常通过 schema 自检，而 ε 带是错的，没有任何一处会报。
    """
    from reference import backtest                                       # 实现 B（契约先于实现落盘）
    missing = [n for n in ("run", "config_from_declared") if not hasattr(backtest, n)]
    if missing:
        raise NotImplementedError(
            f"reference/backtest.py 缺 {missing} —— S7 的 gold 引擎（实现 B）尚未指定，见 "
            "ops/tickets.md 的 N-83。**不得**改用同文件里的实现 A（qlib）顶替。")
    return backtest.run(panel, config=backtest.config_from_declared(declared))


def metrics(daily: pd.DataFrame, initial_capital: float) -> dict:
    r_g, r_n = daily.r_gross.to_numpy(), daily.r_net.to_numpy()
    n = len(r_n)
    ann_ret = lambda r: float(np.prod(1 + r) ** (ANN / n) - 1)                    # noqa: E731
    sd = lambda r: float(np.std(r, ddof=1))                                      # noqa: E731
    nav = np.cumprod(1 + r_n)
    mdd = float(np.min(nav / np.maximum.accumulate(nav) - 1))
    down = np.minimum(r_n, 0.0)
    m = {
        "ann_return_gross": ann_ret(r_g), "ann_return_net": ann_ret(r_n),
        "ann_vol_net": sd(r_n) * np.sqrt(ANN),
        "max_drawdown_net": mdd,
        "sharpe_gross": float(np.mean(r_g)) / sd(r_g) * np.sqrt(ANN),
        "sharpe_net": float(np.mean(r_n)) / sd(r_n) * np.sqrt(ANN),
        "sortino_net_mar0": float(np.mean(r_n)) / sd(down) * np.sqrt(ANN),
        "calmar_net": None,                                                       # 填在下面
        "total_cost": float(daily.cost_abs.sum()) / initial_capital,             # 绝对金额通道
        "turnover_one_way_mean": float((daily.sell_val / daily.ta_pre_trade).mean()),
        "turnover_two_way_mean": float(((daily.buy_val + daily.sell_val) / daily.ta_pre_trade).mean()),
    }
    m["calmar_net"] = m["ann_return_net"] / abs(mdd) if mdd != 0 else None
    return m


def attribution(daily: pd.DataFrame, panel: pd.DataFrame, m: dict) -> dict:
    bench = (panel[panel.in_universe & panel.has_price]
             .sort_values(["code", "date"]).groupby("code").close.pct_change()
             .groupby(panel.date).mean().reindex(daily.date).fillna(0.0).to_numpy())
    r_g = daily.r_gross.to_numpy()
    beta_hat = float(np.polyfit(bench, r_g, 1)[0])
    ann_bench = float(np.prod(1 + bench) ** (ANN / len(bench)) - 1)
    total = m["ann_return_net"]
    cost = m["ann_return_net"] - m["ann_return_gross"]
    beta = beta_hat * ann_bench
    return {"alpha": total - beta - cost, "beta": beta, "cost": cost, "total": total}


def build_artifact(task: dict, daily: pd.DataFrame, panel: pd.DataFrame, meta: dict, arm: str) -> dict:
    m = metrics(daily, task["declared"]["initial_capital"])
    return {
        "schema_version": "1.0", "artifact_id": f"{task['task_id']}-oracle-{arm}", "stage": "S7",
        "task_id": task["task_id"], "config_id": "oracle", "arm": arm, "seed": 0, "as_of": task["as_of"],
        "produced_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "provenance": [{"stage": meta["stage"], "artifact_id": meta["artifact_id"]}],
        "declarations": deepcopy(task["declared"]),
        "payload": {
            "metrics": m, "n_days": int(len(daily)),
            "rebalance_frequency": task["declared"]["rebalance_frequency"],
            "ledger_check": {"max_abs_residual": float((daily.cash + daily.mv - daily.total_assets).abs().max())},
            "attribution": attribution(daily, panel, m),
        },
    }
