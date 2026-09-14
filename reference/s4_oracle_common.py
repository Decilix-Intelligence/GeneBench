# -*- coding: utf-8 -*-
"""S4 五道题共用的 oracle 主干（D-31：模板不许 import 兄弟模板）。

第一版五个 S4 模板的取数段是一行 `adj_close = in_universe = tradable = has_close = None`
（TODO 桩），`gw()` 直接 `raise NotImplementedError` —— 一道也没跑过。这里按 S7 拼面板的
同一套实测端点形状把四张矩阵拼出来。

**四张矩阵，索引一律 ISO 日期 × 网关形态代码（`600000.SH`）**：

| 矩阵 | 行域 | 含义 |
| --- | --- | --- |
| `adj_close` | **窗口 + 之后 h_max 个交易日**（前向收益要用） | 原始 close × adj_factor（后复权）|
| `in_universe` | 窗口 | `/universe` **逐日 PIT** 名单 |
| `tradable` | 窗口 | `/tradability` 的 `status == "trade"` |
| `has_close` | 窗口 | `adj_close` 非空 |

**前向天数不够就报错，不静默截断**：h=20 的前向收益要窗口末之后 20 个交易日，
而那些日子必须 ≤ `as_of`；不够的话最后几天的 IC 会静默变成 NaN，`positive_ratio` 之类
照样算得出来，没有一处会报。

**因子面板**（`work/factor_panel.parquet` / `factor_pool.parquet`）的 date 是紧凑串、code 是
契约 §1 的 `SH600000` —— `load_factor_panel` 在边界上归一一次，与 S5 那次 6900 行全 null 的教训同源。
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from reference import gateway_client as gwc


def _iso(d) -> str:
    s = str(d)[:10]
    return s if "-" in s else f"{s[:4]}-{s[4:6]}-{s[6:8]}"


def load_factor_panel(path: str | Path, factor_id: str | None = None) -> pd.DataFrame:
    """长表 `(date, code, value[, factor_id])` → 宽表 index=ISO 日期, columns=网关形态代码。"""
    df = pd.read_parquet(path)
    if factor_id is not None:
        df = df[df["factor_id"] == factor_id]
    if df.empty:
        raise ValueError(f"{path} 里没有 {factor_id!r} 的行")
    df = df.assign(date=df["date"].map(_iso),
                   code=df["code"].astype(str).str.strip().map(gwc.to_gateway_code))
    return df.pivot(index="date", columns="code", values="value").sort_index()


def build_inputs(gw: gwc.Client, task: dict, h_max: int) -> dict:
    """返回 `{"window", "series", "codes", "adj_close", "in_universe", "tradable", "has_close"}`。"""
    start, end, as_of = task["window"]["start"], task["window"]["end"], task["as_of"]
    days_all = gw.trading_days(start, as_of)
    window = [d for d in days_all if start <= d <= end]
    after = [d for d in days_all if d > end]
    if not window:
        raise ValueError(f"窗口 {start}..{end} 内没有交易日")
    if len(after) < h_max:
        raise ValueError(f"窗口末 {end} 之后到 as_of {as_of} 只有 {len(after)} 个交易日，"
                         f"持有期 {h_max} 的前向收益算不满 —— 不静默截断")
    series = window + after[:h_max]

    members = {d: gw.members(task["universe"], d) for d in window}        # PIT 逐日
    codes = sorted(set().union(*members.values()))

    bars = gw.bars(codes, series[0], series[-1], ["close"])
    adj = gw.adj(codes, series[0], series[-1])
    px = bars[["code", "date", "close"]].merge(adj[["code", "date", "adj_factor"]],
                                              on=["code", "date"], how="left")
    px["adj_close"] = px["close"].astype(float) * px["adj_factor"].astype(float)
    adj_close = (px.pivot(index="date", columns="code", values="adj_close")
                   .reindex(index=series, columns=codes))
    if adj_close.notna().sum().sum() == 0:
        raise ValueError("adj_close 全空 —— /bars 与 /adj 的键没对上（日期格式？）")

    in_universe = pd.DataFrame(False, index=window, columns=codes)
    for d, ms in members.items():
        in_universe.loc[d, [c for c in ms if c in in_universe.columns]] = True

    trad = gw.tradability(codes, window)
    if trad.empty:
        raise ValueError("/tradability 一行都没有")
    trad = trad.assign(date=trad["date"].map(_iso))
    tradable = (trad.assign(ok=trad["status"].astype(str) == "trade")
                    .pivot(index="date", columns="code", values="ok")
                    .reindex(index=window, columns=codes).fillna(False).astype(bool))
    has_close = adj_close.loc[window].notna()
    return {"window": window, "series": series, "codes": codes, "adj_close": adj_close,
            "in_universe": in_universe, "tradable": tradable, "has_close": has_close}


# ---------------------------------------------------------------- IC 计算（从 cor 模板原样搬来）
import numpy as np


def forward_returns(dates, adj_close: pd.DataFrame, h: int) -> pd.DataFrame:
    """`r[d] = adj_close[D[i+h]] / adj_close[d] − 1`，按交易日**位置**错位，不按自然日；越界 → NaN。"""
    fwd = adj_close.shift(-h)
    return (fwd / adj_close - 1.0).loc[dates]


def ic_series(factor: pd.DataFrame, fwd: pd.DataFrame, valid: pd.DataFrame, tie: str,
              min_n: int = 5) -> tuple[pd.Series, pd.Series]:
    """逐日截面 Spearman（rank 平局按 `tie`），只用 valid 格；同时返回每日有效格数。"""
    ics, ns = {}, {}
    for d in factor.index:
        m = valid.loc[d]
        f, r = factor.loc[d][m], fwd.loc[d][m]
        ns[d] = int(m.sum())
        if ns[d] < min_n:                       # 截面太薄不算 IC
            ics[d] = np.nan
            continue
        ics[d] = f.rank(method=tie).corr(r.rank(method=tie))      # spearman = pearson of ranks
    return pd.Series(ics), pd.Series(ns)


def block_bootstrap_ci(ic: pd.Series, seed: int, *, n_boot: int = 1000,
                       block_len: int = 20) -> tuple[float, float]:
    """对 IC 序列做移动块自举，统计量 = 均值，取 2.5% / 97.5% 分位。"""
    rng = np.random.default_rng(seed)
    x = ic.dropna().to_numpy()
    n = len(x)
    if n == 0:
        return float("nan"), float("nan")
    bl = min(block_len, n)
    n_blocks = int(np.ceil(n / bl))
    means = np.empty(n_boot)
    for b in range(n_boot):
        starts = rng.integers(0, n - bl + 1, size=n_blocks)
        sample = np.concatenate([x[s:s + bl] for s in starts])[:n]
        means[b] = sample.mean()
    return float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def summarize(ic: pd.Series, n_valid: pd.Series, n_universe: pd.Series, seed: int,
              declared: dict, *, n_boot: int = 1000, block_len: int = 20,
              where: str = "") -> dict:
    """`ic_stats` 八键（契约 §S4）。ICIR 年化 √annualization（scorer 同口径）。

    **一段里一个 IC 都算不出来时抛 `S4SampleTooThin`，不交一份全 NaN 的 ic_stats**（③）。
    `where` 只进报错信息，不进返回值 —— 它回答「是哪一段不够」，而那正是
    「七个字段都是 NaN」这条报错答不上来的问题。
    """
    x = ic.dropna()
    if len(x) < MIN_IC_DAYS:
        raise S4SampleTooThin(
            f"{where or '这一段'}里 {len(ic)} 个交易日没有一个算得出截面 IC —— "
            f"`ic_stats` 的 mean/std/icir/positive_ratio/coverage/ci_low/ci_high 会全是 NaN。"
            f"常见原因：这一段是空的（窗口与留出段不相交），或每天的有效格数都 < ic_series 的 min_n。"
            f"不交 NaN：NaN 通得过 envelope 校验，要到结算时才变成 7 条 s4_ic_stat_not_number")
    mean, std = float(x.mean()), float(x.std(ddof=1))
    lo, hi = block_bootstrap_ci(ic, seed, n_boot=n_boot, block_len=block_len)
    return {
        "mean": mean, "std": std,
        "icir": mean / std * float(np.sqrt(declared["annualization"])) if std else float("nan"),
        "positive_ratio": float((x > 0).mean()),
        "coverage": float((n_valid / n_universe).mean()),
        "ci_low": lo, "ci_high": hi, "ci_method": declared["uncertainty_method"],
    }


def valid_mask(factor: pd.DataFrame, X: dict, fwd: pd.DataFrame) -> pd.DataFrame:
    """cor 模板的 valid：有限值 ∧ PIT 成分 ∧ 可交易 ∧ 有价 ∧ 有前向收益。"""
    return (np.isfinite(factor.astype(float)) & X["in_universe"] & X["tradable"]
            & X["has_close"] & fwd.notna())


def ic_by_horizon(factor: pd.DataFrame, X: dict, declared: dict, seed: int,
                  *, dates=None) -> dict[str, dict]:
    """每个持有期一份 `summarize`。`dates` 限定用哪些交易日（默认整个窗口）。"""
    idx = list(dates) if dates is not None else X["window"]
    if len(idx) < MIN_IC_DAYS:
        # **空的日期集不是「零个 IC」，是「没算」**（③）。原先这里一路往下走，
        # 每个 horizon 都交一份全 NaN 的 ic_stats（s4-eco-02/04 的 7 条 malformed 就是这么来的）。
        raise S4SampleTooThin(
            f"要算 IC 的交易日集是空的（dates={'自定' if dates is not None else '整个窗口'}）—— "
            f"窗口 {X['window'][0] if X['window'] else '?'}..{X['window'][-1] if X['window'] else '?'} "
            f"与这一段不相交。不静默出 NaN")
    f = factor.reindex(index=idx, columns=X["codes"])
    n_universe = X["in_universe"].loc[idx].sum(axis=1)
    out = {}
    for h in sorted(declared["holding_periods"]):
        fwd = forward_returns(f.index, X["adj_close"], h)
        valid = valid_mask(f, {k: (v.loc[idx] if isinstance(v, pd.DataFrame) else v)
                               for k, v in X.items()}, fwd)
        ic, n_valid = ic_series(f, fwd, valid, declared["tie_handling"])
        out[str(h)] = summarize(ic, n_valid, n_universe, seed, declared,
                                where=f"h={h} 的 {idx[0]}..{idx[-1]}（{len(idx)} 个交易日）")
    return out


#: 一个候选要进 t 检验，训练段上至少要有这么多个**算得出 IC 的交易日**。
#: `std(ddof=1)` 在 n<2 时是 NaN，n=0 时 `mean` 也是 NaN —— 两者都会让 t 变 NaN。
MIN_TRAIN_DAYS = 2

#: 一段（训练段或留出段）要算得出 `ic_stats`，至少要有这么多个算得出 IC 的交易日。
#: 低于它，`summarize` 的八个字段里有七个是 NaN —— 那不是「不准的数」，是**没有数**。
MIN_IC_DAYS = 1


class S4SampleTooThin(ValueError):
    """**这一步的样本不够，算不出数** —— 显式抛，不产 NaN（用户裁定 ③，2026-09-10）。

    为什么要有这个类型（N-518 的实测形态）：出集那一行 `s4-eco-01` 一直是绿的，
    换三个窗口取值就全废，而**三种废法各不相同、没有一种会报错**：

    * `s4-eco-02` / `s4-eco-04`（窗口挪到留出段之前）：留出段里一个交易日都没有，
      `ic_stats` 八个字段里七个是 NaN，`positive_ratio`、`coverage` 照样「算」得出来，
      artifact 照样写盘、照样通过 envelope 校验 —— 直到 7 条 `malformed:s4_ic_stat_not_number`。
    * `s4-eco-03`（窗口挪到留出段之内）：训练段空 → 每个候选的 mean/std 都是 NaN →
      `t.abs().idxmax()` 返回 NaN → `str(NaN)` = `"nan"` → **NaN 被当成 factor_id 去查表**，
      崩在 `load_factor_panel` 的 `没有 'nan' 的行`。报错说的是「因子池里少了一个因子」，
      而真正发生的事是「挑因子那一步根本没能挑」。

    三种废法的共同点是**把 NaN 往下游传**：传进 ic_stats 是第一种，传进 factor_id 查表是第二种。
    所以这里立的规矩不是「NaN 时选个别的」，是**NaN 时当场停，并说清是哪一段不够**。
    """


def bh_fdr_select(train: pd.DataFrame, q: float = 0.10) -> tuple[str, list[str], str]:
    """S4-ECO 的 oracle 选法：t = mean/std·√n，BH-FDR（q）；通过者里取 |t| 最大；
    没有通过者就取 |t| 最大者并标 `no_fdr_survivor`。`train` 列：mean, std, n。

    **先筛掉算不出 t 的候选**（③）：mean / std 非有限、std=0、或训练段样本 < `MIN_TRAIN_DAYS`。
    这三种都不是「t 很小」，是**没有 t**；留着它们的后果是 `t.abs().idxmax()` 可能返回 NaN。

    筛掉而不是 `fillna(0)`（原实现在算 p 值时就是 fillna(0)）：把「算不出」当成「t=0」，
    等于给它一个 p=1 的名次，**它会挤进 BH 的分母 m**，把别的候选的阈值 `q·i/m` 压低 ——
    一个算不出来的候选因此能改变别人是否显著。筛掉之后 m 只数真候选。

    一个都筛不剩 → 抛 `S4SampleTooThin`，**不返回 NaN**。
    """
    from math import erf, sqrt
    mean = pd.to_numeric(train["mean"], errors="coerce")
    std = pd.to_numeric(train["std"], errors="coerce")
    n = pd.to_numeric(train["n"], errors="coerce")
    usable = np.isfinite(mean) & np.isfinite(std) & (std > 0) & (n >= MIN_TRAIN_DAYS)
    dropped = [str(k) for k in train.index[~usable]]
    if not usable.any():
        raise S4SampleTooThin(
            f"{len(train)} 个候选因子里没有一个算得出 t 统计量（mean/std 非有限、"
            f"std=0、或训练段有效交易日 < {MIN_TRAIN_DAYS}）—— 挑因子这一步**没有结果**。"
            f"最常见的原因是训练段里一个交易日都没有（窗口整个落在留出段里）。"
            f"不返回 NaN：NaN 会被当成 factor_id 拿去查因子池，报错会说成「池里少了一个因子」")
    t = (mean / std * np.sqrt(n))[usable]
    p = 2 * (1 - pd.Series([0.5 * (1 + erf(abs(v) / sqrt(2))) for v in t], index=t.index))
    order = p.sort_values()
    m = len(order)
    surv = [k for i, (k, pv) in enumerate(order.items(), start=1) if pv <= q * i / m]
    if surv:
        chosen = t.loc[surv].abs().idxmax()
        return str(chosen), [str(x) for x in surv], "fdr"
    note = "no_fdr_survivor" if not dropped else f"no_fdr_survivor;dropped={len(dropped)}"
    return str(t.abs().idxmax()), [], note
