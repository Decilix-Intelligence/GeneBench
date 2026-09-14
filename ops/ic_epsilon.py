#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""N-117：**S4 IC 族的 ε 双实现标定**（与卡 2.2b 的回测 ε 同构）。

    cd $REPO && $GENEBENCH_ROOT/env/bin/python ops/ic_epsilon.py --factors 60

**为什么要这张卡**：`snapshots/v1/calibration.json` 的 ε 只标定了**回测指标**
（sharpe_net / max_drawdown_net / …）。S4 的 `tolerance.kind` 是 `epsilon`，而它的
payload 全是 IC 族（mean / std / icir / positive_ratio / coverage / CI）——
一个带都没有 → `scorer.l3.compare_epsilon` 一格都比不了 → `l3_pass=None` →
锚点退化 → **S4 的 effect 永远扣住**（票据 N-117）。

**方法与 2.2b 同构**（`reference/epsilon_dual.py`）：ε = 两份**独立实现**同一份声明的
自然分歧 × :data:`MULTIPLIER`。区别只在实现对与样本面：

* 实现对 **A = qlib 口径**：`qlib.contrib.eva.alpha.calc_ic` ——
  它**就是** `qlib.workflow.record_temp.SigAnaRecord._generate` 的计算路径
  （该方法体内逐字调用 `calc_ic(pred.iloc[:, 0], label.iloc[:, label_col])`，
  见 :func:`qlib_impl_provenance`，运行时从源码里核一次，核不上就抛）。
* 实现对 **B = 纯 pandas 口径**：逐截面 `rank(平局平均) → Pearson`，
  再对时间序列汇总；带一条 qlib 没有的**最小截面门槛**。
* 样本面不是一次回测，而是 **N 因子 × M 宇宙 × 持有期 {1,5,20}** 的一个**分歧分布**，
  所以带取分位而不是取单点（见 :data:`BAND_QUANTILE`）。

**两条实现都吃同一份输入面**，这是刻意的：题面（`INSTRUCTION.*.md`）把无效格
逐条写死了（"因子非有限 / 当日不可交易 / 远期收盘缺失 / 远期日期越过 as_of"），
把它算成"实现自由度"等于把**已声明**的东西量进 ε 里，那样的带会宽到没有判别力。
留给自由度的是题面**没写**的那几处：

1. **最小截面门槛**：多薄的截面还算 IC？qlib 不设门槛，B 设 5（与 S4 公共层同）；
2. **NaN 日算不算分母**：`positive_ratio` / `coverage` 的分母是"窗口内全部交易日"
   还是"IC 有定义的交易日"；
3. **一格都没有的交易日**：qlib 的 `groupby` 里根本不存在这一天，B 记 coverage=0。

**ICIR 的年化不在 ε 里，它是声明歧义**：`SigAnaRecord` 的 ICIR = `ic.mean()/ic.std()`，
**不年化**；S4 题面声明 `annualization=252` 而参考实现年化（×√252）。两者差 √252 ≈ 15.9 倍，
那不是容差能盖的，是**题面没写清 ICIR 要不要年化**。按 2.2b 的纪律：
超阈的不写成 ε，停下汇报（本模块把两个数都算出来放进产物的
`icir_annualization_ambiguity`，并在 `ops/tickets_inbox/1.2.md` 记一条）。
参与标定的 `icir` **两边都年化**，量的才是实现自由度而不是单位差。

**CI 不标定**：qlib 口径里**没有** CI —— `SigAnaRecord` 不产 bootstrap 区间，
双实现对在这一项上**构不成**。硬造第二份自举实现会得到一个由 RNG 抽样决定的数，
那不是"两份诚实实现的自然分歧"。`ci_low` / `ci_high` 因此标
``no_pair_in_qlib_path``、**不出带**，L3 跳过它们（在产物里写明）。

**度量类型规则**沿用 2.2b 的形状但**另立集合**：IC 均值与 ICIR 构造上在 0 附近
（一个没有预测力的因子的 IC 均值就是 0），相对容差在它们上没有意义 → **绝对容差**。
`reference.epsilon_dual.ZERO_APPROACHING` 是**回测指标**的集合，不含 IC 族的名字，
所以这里不复用它，也**不去改它**（那是参考轴的冻结面）：见 :data:`ZERO_APPROACHING`。
"""
from __future__ import annotations

import argparse
import datetime as dt
import inspect
import json
import math
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import genebench_config as cfg                                   # noqa: E402

# --------------------------------------------------------------------- 常量

#: ε = 分歧 × 这个系数。与 `reference.epsilon_dual.MULTIPLIER` 同值，**刻意不 import**：
#: 那是参考轴的冻结面，ops 侧引它会让"改一个 ops 文件"变成"改冻结根"。值不一致会被
#: `ops/test_ic_epsilon.py::test_multiplier_matches_backtest_epsilon` 抓红。
MULTIPLIER: float = 1.5

#: 浮点噪声地板 —— 与 2.2b 同值同理由（低于它量到的是舍入，不是实现自由度）。
NOISE_FLOOR: float = 1e-13

#: 高于这个相对分歧就不像实现自由度了（2.2b 的签字建议值 5%）。
IMPLAUSIBLE_REL_DIFF: float = 0.05

#: **带取分位而不是取最大**。2.2b 的样本面是一次回测（3 份实现两两比 = 3 个数），
#: 取最大是唯一可能；这里的样本面是 N 因子 × M 宇宙的一个**分布**，最大值由单个
#: 最病态的因子决定（全窗几乎常数、截面只剩 3 只），拿它定带 = 让 ε 被离群点绑架。
#:
#: 取 **P90** 是 τ 的镜像：τ = 正确实现两两逐日 ρ 分布的 **P10**（允许最差 10% 的样本
#: 落在门外，`ops/specs/GeneBench秩相关与标定口径_v1.md` F-2）。ε 与 τ 方向相反，
#: 同样的 10% 尾巴落在**上**侧，所以是 P90。产物里同时报 P50/P95/P99/max 与
#: "若按 max 定带会是多少"，好让签字人看见这个选择的代价。
BAND_QUANTILE: float = 0.90

#: 进标定的 IC 族指标（= `calibration.json.scoring.ic_summary.report` 里能构成双实现对的那些）。
IC_METRICS: tuple[str, ...] = ("mean", "std", "icir", "positive_ratio", "coverage")

#: 构造上可能趋零 → **绝对容差**。IC 均值的零假设中心就是 0（没有预测力的因子），
#: ICIR 的分子是它，直接继承。相对容差施加在它们上会得到"看起来很大、其实没意义"的数
#: （与 2.2b 在 `ann_return_net` 上踩到的是同一个坑）。
ZERO_APPROACHING: frozenset[str] = frozenset({"mean", "icir"})

#: 有分歧但**构不成双实现对**的指标：qlib 口径里没有 bootstrap 区间。
NO_PAIR_METRICS: tuple[str, ...] = ("ci_low", "ci_high")

#: 绝对容差的单位（进产物，供签字人读）。
ABSOLUTE_UNIT: dict[str, str] = {
    "mean": "IC 点（与 IC 同单位的绝对差）",
    "icir": "ICIR 点（年化后，绝对差）",
}

#: B 实现的最小截面门槛。题面没写，**这正是自由度本身**。
MIN_CROSS_SECTION: int = 5

#: v1.0 冒烟集 S4 题的评估窗（`reference/tasks/v1.0-smoke/s4-cor-01/task.yaml`）。
#: **带必须在与判据同量级的窗上标**：窗长决定 IC 序列的样本数，而分歧里有一部分
#: 恰好来自"少数几天算不算"——在 2 700 天的全史窗上标出来的带会系统性偏窄。
DEFAULT_WINDOWS: tuple[tuple[str, str], ...] = (
    ("2026-01-05", "2026-06-30"),      # ← s4-*-01 的窗，判据实际落在这一档
    ("2025-07-01", "2025-12-31"),
    ("2025-01-02", "2025-06-30"),
)
DEFAULT_AS_OF: str = "2026-07-31"
DEFAULT_HOLDING_PERIODS: tuple[int, ...] = (1, 5, 20)
DEFAULT_ANNUALIZATION: int = 252
DEFAULT_TIE: str = "average"

OUT_DEFAULT: Path = cfg.SNAPSHOTS_V1 / "epsilon" / "ic_epsilon_dual.json"

__all__ = ["MULTIPLIER", "NOISE_FLOOR", "IMPLAUSIBLE_REL_DIFF", "BAND_QUANTILE",
           "IC_METRICS", "ZERO_APPROACHING", "NO_PAIR_METRICS", "tolerance_kind",
           "impl_a_qlib", "impl_b_pandas", "band_from_diffs", "build", "OUT_DEFAULT"]


def tolerance_kind(metric: str) -> str:
    """该 IC 指标该用哪种容差。**评分器必须读产物里的 `tolerance_kind`，不许自己判断。**"""
    return "absolute" if metric in ZERO_APPROACHING else "relative"


def _rel(a: float, b: float) -> float:
    d = abs(a - b)
    scale = max(abs(a), abs(b))
    return d / scale if scale else (0.0 if d == 0 else float("inf"))


# --------------------------------------------------------------- 实现对的出处

def qlib_impl_provenance() -> dict[str, Any]:
    """**运行时**核一次"A 就是 SigAnaRecord 的计算路径"，核不上就抛。

    不是注释里写一句"等价于"就算数：`SigAnaRecord._generate` 的源码里必须真的出现
    `calc_ic(`，且 `calc_ic` 必须与 `qlib.contrib.eva.alpha.calc_ic` 是同一个对象。
    qlib 换版本把这条路径改掉时，这里会红，而不是悄悄标定了一个别的东西。
    """
    import qlib                                                  # noqa: F401
    from qlib.contrib.eva import alpha as qeva
    from qlib.workflow.record_temp import SigAnaRecord

    src = inspect.getsource(SigAnaRecord._generate)
    if "calc_ic(" not in src:
        raise RuntimeError("SigAnaRecord._generate 里没有 calc_ic( —— qlib 的 IC 路径变了，"
                           "A 实现的出处断了，停下不标定。")
    mod = sys.modules[SigAnaRecord.__module__]
    if getattr(mod, "calc_ic", None) is not qeva.calc_ic:
        raise RuntimeError("SigAnaRecord 模块里的 calc_ic 不是 qlib.contrib.eva.alpha.calc_ic，"
                           "A 实现的出处断了，停下不标定。")
    return {
        "qlib_version": qlib.__version__,
        "entry": "qlib.contrib.eva.alpha.calc_ic",
        "is_sig_ana_record_path": True,
        "evidence": "qlib.workflow.record_temp.SigAnaRecord._generate 源码内逐字调用 calc_ic(...)；"
                    "该模块里的 calc_ic 与 qlib.contrib.eva.alpha.calc_ic 是同一对象（运行时核过）。",
        "sig_ana_record_icir": "ic.mean()/ic.std()（**不年化**）—— 见模块 docstring 的声明歧义一节。",
    }


# ------------------------------------------------------------------- 两份实现

def _stack(f: pd.DataFrame, r: pd.DataFrame, valid: pd.DataFrame) -> pd.DataFrame:
    long = pd.DataFrame({"pred": f.where(valid).stack(), "label": r.where(valid).stack()})
    long.index.names = ["datetime", "instrument"]
    return long


def impl_a_qlib(factor: pd.DataFrame, fwd: pd.DataFrame, valid: pd.DataFrame,
                n_universe: pd.Series, *, ic_method: str = "spearman",
                annualization: int = DEFAULT_ANNUALIZATION) -> dict[str, float]:
    """**A：qlib 口径**。IC 序列由 `qlib.contrib.eva.alpha.calc_ic` 出，汇总走 qlib 的写法。

    qlib 的写法有三处与 B 不同，**都是题面没写的**：
    没有最小截面门槛；`(ic > 0).mean()` 的分母是序列全长（NaN 日算进分母）；
    `groupby` 里不存在"一格都没有"的交易日（那天不进 coverage 的分子也不进分母）。
    """
    from qlib.contrib.eva.alpha import calc_ic

    long = _stack(factor, fwd, valid)
    if long.empty:
        return {m: float("nan") for m in IC_METRICS}
    ic, ric = calc_ic(long["pred"], long["label"])
    s = ric if str(ic_method).lower() == "spearman" else ic
    mean, std = float(s.mean()), float(s.std())
    n_day = long.groupby(level="datetime").size()
    cov = (n_day / n_universe.reindex(n_day.index)).mean()
    return {
        "mean": mean,
        "std": std,
        "icir": (mean / std * math.sqrt(annualization)) if std else float("nan"),
        "positive_ratio": float((s > 0).mean()),
        "coverage": float(cov),
    }


def impl_b_pandas(factor: pd.DataFrame, fwd: pd.DataFrame, valid: pd.DataFrame,
                  n_universe: pd.Series, *, tie: str = DEFAULT_TIE,
                  annualization: int = DEFAULT_ANNUALIZATION,
                  min_cross_section: int = MIN_CROSS_SECTION) -> dict[str, float]:
    """**B：纯 pandas 口径**。逐截面 `rank(平局按 tie) → Pearson`，再对时序汇总。

    只依据题面的声明写：`ic_method=spearman` 落成"秩的 Pearson"，`tie_handling=average`
    落成 `rank(method="average")`；截面薄于 `min_cross_section` 的日子**不算 IC**
    （题面没写这条门槛，这正是与 A 的自由度所在）；`positive_ratio` 的分母是
    **IC 有定义的日子**，`coverage` 的分母是窗口内**全部**交易日（没有一格的日子记 0）。
    """
    f = factor.where(valid)
    r = fwd.where(valid)
    n_valid = valid.sum(axis=1)
    rf = f.rank(axis=1, method=tie)
    rr = r.rank(axis=1, method=tie)
    # 逐行 Pearson（秩的 Pearson = Spearman，平局平均法）—— 向量化，与 factor_crosscheck 同法
    a = rf.to_numpy(dtype=float)
    b = rr.to_numpy(dtype=float)
    m = np.isfinite(a) & np.isfinite(b)
    a = np.where(m, a, np.nan)
    b = np.where(m, b, np.nan)
    n = m.sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        am = np.nanmean(a, axis=1, keepdims=True)
        bm = np.nanmean(b, axis=1, keepdims=True)
        da, db = a - am, b - bm
        num = np.nansum(da * db, axis=1)
        den = np.sqrt(np.nansum(da * da, axis=1) * np.nansum(db * db, axis=1))
        rho = np.where(den > 0, num / den, np.nan)
    rho = np.where(n >= min_cross_section, rho, np.nan)
    s = pd.Series(rho, index=factor.index, dtype=float)
    x = s.dropna()
    if x.empty:
        return {m_: float("nan") for m_ in IC_METRICS}
    mean, std = float(x.mean()), float(x.std(ddof=1))
    cov = float((n_valid / n_universe).mean())
    return {
        "mean": mean,
        "std": std,
        "icir": (mean / std * math.sqrt(annualization)) if std else float("nan"),
        "positive_ratio": float((x > 0).mean()),
        "coverage": cov,
    }


def impl_c_pandas_limits_tradable(factor: pd.DataFrame, fwd: pd.DataFrame,
                                  valid_relaxed: pd.DataFrame, n_universe: pd.Series, *,
                                  tie: str = DEFAULT_TIE,
                                  annualization: int = DEFAULT_ANNUALIZATION) -> dict[str, float]:
    """**C：另一种同样站得住的读法** —— 「当日不可交易」只算**停牌 / 无数据**，涨跌停算可交易。

    题面写的是「当日不可交易 → 剔除」，而 `/tradability` 的 status 有五档
    （`trade` / `suspend` / `limit_up` / `limit_down` / `no_data`）。参考实现把
    `status == "trade"` 之外的全算不可交易；但**涨停那天股票是成交的**，
    把它算「不可交易」是一种读法，算「可交易但买不进」是另一种 —— 题面没有裁。

    这不是"编出来的分歧"：涨跌停占全样本约 10% 的格，两种读法给出的 IC 族是两个不同的数。
    C 与 B 只差这一处（同一份 pandas 汇总代码），所以量到的就是**这一处歧义**的代价。
    """
    return impl_b_pandas(factor, fwd, valid_relaxed, n_universe, tie=tie,
                         annualization=annualization)

# ------------------------------------------------------------------ 带的推导

def band_from_diffs(metric: str, diffs: "list[dict[str, float]]") -> dict[str, Any]:
    """一个指标的一堆 (rel, abs) 分歧 → 一条带。**规则与 2.2b 同构，只把"取最大"换成"取分位"。**"""
    kind = tolerance_kind(metric)
    key = "abs" if kind == "absolute" else "rel"
    xs = np.array([d[key] for d in diffs if np.isfinite(d[key])], dtype=float)
    rels = np.array([d["rel"] for d in diffs if np.isfinite(d["rel"])], dtype=float)
    rec: dict[str, Any] = {
        "tolerance_kind": kind,
        "unit": ABSOLUTE_UNIT.get(metric, "相对差") if kind == "absolute" else "相对差",
        "n_samples": int(len(xs)),
        "n_samples_nonfinite_dropped": int(len(diffs) - len(xs)),
    }
    if len(xs) == 0:
        rec.update({"status": "no_samples", "epsilon": None,
                    "note": "一个可用样本都没有 —— 不出带。"})
        return rec
    q = {f"p{int(p * 100)}": float(np.quantile(xs, p)) for p in (0.5, 0.9, 0.95, 0.99)}
    rec["diff_quantiles"] = q
    rec["diff_max"] = float(xs.max())
    rec["max_rel_diff"] = float(rels.max()) if len(rels) else float("nan")
    rec["p90_rel_diff"] = float(np.quantile(rels, BAND_QUANTILE)) if len(rels) else float("nan")
    rec["n_zero_diff"] = int((xs == 0.0).sum())
    rec["zero_diff_ratio"] = float((xs == 0.0).mean())
    band = float(np.quantile(xs, BAND_QUANTILE))
    rel_band = float(np.quantile(rels, BAND_QUANTILE)) if len(rels) else float("nan")
    rec["diff_at_band_quantile"] = band
    rec["epsilon_if_max_rule"] = float(xs.max()) * MULTIPLIER
    if band == 0.0:
        # 分歧分布的 P90 恰为 0 = 九成样本上两份实现**逐位相同**。
        # 按 E-1：ε=0 不是标定成功而是标定失效 —— 不出带，停下汇报。
        rec.update({"status": "no_implementation_freedom", "epsilon": None,
                    "note": (f"{rec['zero_diff_ratio']:.1%} 的样本上两份实现分歧恰为 0，"
                             f"P{int(BAND_QUANTILE * 100)} 分位也是 0 —— 该指标在当前声明下"
                             f"**没有可测的实现自由度**。按 E-1，**不得把 ε 写成 0**，"
                             f"也**不得用其他指标的 ε 代填**；L3 跳过该项。")})
        return rec
    # 噪声地板一律用**相对**分歧判 —— 绝对差的量纲随指标走，1e-18 对 IC 均值是舍入、
    # 对 turnover 可能是真差。2.2b 在绝对容差分支上漏了这道闸（那里的样本没触到），
    # 这里补上：不补的话「两份实现逐位相同」会被写成一条 1e-18 的 ε，
    # 那正是 E-1 说的比特级相等断言。
    if not np.isfinite(rel_band) or rel_band < NOISE_FLOOR:
        rec.update({"status": "invalid_below_noise_floor", "epsilon": None,
                    "note": f"P{int(BAND_QUANTILE * 100)} **相对**分歧 {rel_band:.3g} 低于噪声地板 "
                            f"{NOISE_FLOOR:g} —— 量到的是 float64 舍入而不是实现自由度，"
                            f"**不作 ε**（E-1：ε=0 是标定失效，不是标定成功）。"})
        return rec
    # **超阈闸只对相对容差开**（2.2b 原样）：趋零量的相对差被结构性放大
    # （实测 IC 均值的相对分歧 >50%，而绝对分歧只有 8e-4 个 IC 点），
    # 拿它去判「不像实现自由度」会把每一个趋零指标都判成声明没写清。
    if kind == "relative" and rel_band > IMPLAUSIBLE_REL_DIFF:
        rec.update({"status": "implausible_stop_and_report", "epsilon": None,
                    "note": f"P{int(BAND_QUANTILE * 100)} 相对分歧 {rel_band:.2%} 超过 "
                            f"{IMPLAUSIBLE_REL_DIFF:.0%} —— 不像实现自由度，多半是**声明没写清**。"
                            f"停下汇报，不写成 ε。"})
        return rec
    rec.update({"status": "calibrated", "epsilon": band * MULTIPLIER})
    return rec


# ------------------------------------------------------------------ 数据装载

def _to_contract_code(s: pd.Series) -> pd.Series:
    """`000001.SZ` → `SZ000001`（契约 §1 形态，与 gold 因子面板一致）。"""
    x = s.astype(str).str.upper().str.strip()
    return x.str[-2:] + x.str[:6]


def _iso(x) -> str:
    s = str(x)[:10]
    return s if "-" in s else f"{s[:4]}-{s[4:6]}-{s[6:8]}"


#: `daily.parquet` 是 356 MB、`adj_factor.parquet` 14 MB —— 9 个 (宇宙 × 窗) 各读一遍
#: 是三分钟的纯 I/O。进程内缓存一次；键是快照根，所以私有 / 公开通道各缓存各的。
_PX_CACHE: dict[str, tuple[pd.DataFrame, pd.DataFrame]] = {}


def _prices(snap: Path, min_date: str = "1990-01-01") -> tuple[pd.DataFrame, pd.DataFrame]:
    """`min_date` 之前的行直接丢掉再缓存 —— 全史缓存实测 6.2 GB RSS，
    机器只剩 10 GB 可用，三个宇宙并行会把自己跑进 swap。"""
    k = f"{snap}|{min_date}"
    if k not in _PX_CACHE:
        px = pd.read_parquet(snap / "tables" / "daily.parquet",
                             columns=["ts_code", "trade_date", "close"])
        adj = pd.read_parquet(snap / "tables" / "adj_factor.parquet",
                              columns=["ts_code", "trade_date", "adj_factor"])
        cut = min_date.replace("-", "")
        px = px[px["trade_date"].astype(str) >= cut]
        adj = adj[adj["trade_date"].astype(str) >= cut]
        px = px.assign(code=_to_contract_code(px["ts_code"]), date=px["trade_date"].map(_iso))
        adj = adj.assign(code=_to_contract_code(adj["ts_code"]), date=adj["trade_date"].map(_iso))
        _PX_CACHE[k] = (px.reset_index(drop=True), adj.reset_index(drop=True))
    return _PX_CACHE[k]


class Inputs:
    """一个宇宙的共享输入面（两份实现吃同一份，见模块 docstring）。"""

    #: 快照根下必须有的三样东西（`--provider-dir` 指到哪都得齐）。
    REQUIRED: tuple[tuple[str, str], ...] = (
        ("tables/daily.parquet", "日线收盘"),
        ("tables/adj_factor.parquet", "复权因子"),
        ("tables/trade_cal.parquet", "交易日历"),
        ("universe/universe_pit.parquet", "PIT 宇宙成分"),
        ("tradability", "可交易性分区（year=YYYY/）"),
    )

    @classmethod
    def preflight(cls, snap: Path) -> None:
        """缺件时报出**缺的是哪一件**，而不是让 pandas 抛一个只有路径的 FileNotFoundError。

        2026-09-06 实测：公开通道快照 `snapshots/public_v1/` 有 `tables/` 与 `tradability/`
        但**没有 `universe/`** —— 拿它当 `--provider-dir` 会在第 200 行才炸。
        """
        miss = [f"{rel}（{what}）" for rel, what in cls.REQUIRED if not (snap / rel).exists()]
        if miss:
            raise SystemExit(f"快照根 {snap} 缺件，标定跑不了：\n  " + "\n  ".join(miss)
                             + "\n（公开通道当前缺 universe/ —— 见 ops/tickets_inbox/1.2.md）")

    def __init__(self, snap: Path, universe: str, start: str, end: str, as_of: str,
                 h_max: int, price_min_date: str | None = None):
        self.preflight(snap)
        cal = pd.read_parquet(snap / "tables" / "trade_cal.parquet")
        col = "cal_date" if "cal_date" in cal.columns else "trade_date"
        if "is_open" in cal.columns:
            cal = cal[cal["is_open"].astype(int) == 1]
        days = sorted({_iso(d) for d in cal[col]})
        days = [d for d in days if d <= _iso(as_of)]
        window = [d for d in days if _iso(start) <= d <= _iso(end)]
        after = [d for d in days if d > _iso(end)]
        if not window:
            raise ValueError(f"窗口 {start}..{end} 内没有交易日")
        if len(after) < h_max:
            raise ValueError(f"窗口末 {end} 之后到 as_of {as_of} 只有 {len(after)} 个交易日，"
                             f"持有期 {h_max} 的前向收益算不满 —— 不静默截断（与 S4 公共层同）")
        self.window, self.series = window, window + after[:h_max]

        pit = pd.read_parquet(snap / "universe" / "universe_pit.parquet",
                              columns=["code", "universe", "in_date_compact", "out_date_compact"])
        pit = pit[pit["universe"].astype(str) == universe]
        if pit.empty:
            raise ValueError(f"universe_pit 里没有 {universe!r}")
        pit = pit.assign(code=_to_contract_code(pit["code"]))
        self.codes = sorted(pit["code"].unique())

        inu = pd.DataFrame(False, index=self.window, columns=self.codes)
        wa = np.array(self.window)
        for c, lo, hi in zip(pit["code"], pit["in_date_compact"].astype(str),
                             pit["out_date_compact"].astype(str)):
            sel = (wa >= _iso(lo)) & (wa <= _iso(hi))
            if sel.any():
                inu.loc[wa[sel], c] = True
        self.in_universe = inu
        self.n_universe = inu.sum(axis=1).astype(float)
        if (self.n_universe <= 0).any():
            raise ValueError(f"{universe} 有交易日的 PIT 成分为空 —— 输入面不对")

        px, adj = _prices(snap, price_min_date or _iso(start))
        keep = set(self.codes)
        px = px[px["code"].isin(keep) & px["date"].isin(set(self.series))]
        adj = adj[adj["code"].isin(keep) & adj["date"].isin(set(self.series))]
        m = px.merge(adj[["code", "date", "adj_factor"]], on=["code", "date"], how="left")
        m["adj_close"] = m["close"].astype(float) * m["adj_factor"].astype(float)
        ac = m.pivot_table(index="date", columns="code", values="adj_close", aggfunc="last")
        self.adj_close = ac.reindex(index=self.series, columns=self.codes)
        if self.adj_close.notna().sum().sum() == 0:
            raise ValueError("adj_close 全空 —— daily/adj_factor 的键没对上")

        years = sorted({d[:4] for d in self.window})
        parts = []
        for y in years:
            d = snap / "tradability" / f"year={y}"
            if not d.is_dir():
                raise ValueError(f"缺可交易性分区：{d}")
            for p in sorted(d.glob("*.parquet")):
                t = pd.read_parquet(p, columns=["code", "date", "status"])
                parts.append(t)
        tr = pd.concat(parts, ignore_index=True)
        tr = tr.assign(code=_to_contract_code(tr["code"]), date=tr["date"].map(_iso))
        tr = tr[tr["code"].isin(keep) & tr["date"].isin(set(self.window))]
        if tr.empty:
            raise ValueError("可交易性一行都没有")
        st = tr["status"].astype(str)

        def _wide(flag: pd.Series) -> pd.DataFrame:
            w = (tr.assign(ok=flag.to_numpy())
                   .pivot_table(index="date", columns="code", values="ok", aggfunc="max")
                   .reindex(index=self.window, columns=self.codes))
            return w.astype(object).where(w.notna(), False).astype(bool)

        #: 参考实现的读法：`trade` 之外全不可交易。
        self.tradable = _wide(st == "trade")
        #: 另一种读法（实现 C）：只有停牌 / 无数据不可交易，涨跌停照算。
        self.tradable_relaxed = _wide(~st.isin(["suspend", "no_data"]))
        self.limit_cell_ratio = float((st.isin(["limit_up", "limit_down"])).mean())
        self.has_close = self.adj_close.loc[self.window].notna()

    def fwd(self, h: int) -> pd.DataFrame:
        f = self.adj_close.shift(-h)
        return (f / self.adj_close - 1.0).loc[self.window]

    def base_valid(self, h: int) -> pd.DataFrame:
        return self.in_universe & self.tradable & self.has_close & self.fwd(h).notna()

    def base_valid_relaxed(self, h: int) -> pd.DataFrame:
        return self.in_universe & self.tradable_relaxed & self.has_close & self.fwd(h).notna()


def load_factor(path: Path, window: list[str], codes: list[str]) -> pd.DataFrame:
    df = pd.read_parquet(path, columns=["date", "code", "value"])
    df = df.assign(date=df["date"].map(_iso), code=df["code"].astype(str).str.strip())
    df = df[df["date"].isin(set(window))]
    if df.empty:
        raise ValueError(f"{path.name} 在窗口内没有行")
    w = df.pivot_table(index="date", columns="code", values="value", aggfunc="last")
    return w.reindex(index=window, columns=codes)


# --------------------------------------------------------------------- 主流程

def _git_head(repo: Path) -> str:
    try:
        r = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=30)
        return r.stdout.strip() if r.returncode == 0 else "unknown"
    except Exception:                                             # pragma: no cover
        return "unknown"


def pick_factors(gold_dir: Path, universe: str, n: int | None) -> list[Path]:
    """等距抽样 —— **确定性**（排序后按位置取），不用 RNG：换一次种子换一批样本，
    带就会跟着抖，而带是要写进 `calibration.json` 的。"""
    all_f = sorted((gold_dir / universe).glob("*.parquet"))
    if not all_f:
        raise ValueError(f"{gold_dir / universe} 下没有因子面板")
    if n is None or n >= len(all_f):
        return all_f
    idx = np.linspace(0, len(all_f) - 1, num=n).round().astype(int)
    return [all_f[i] for i in sorted(set(idx.tolist()))]


def run_samples(gold_dir: Path, snap: Path, *, universes: Iterable[str],
                windows: Iterable[tuple[str, str]], holding_periods: Iterable[int],
                as_of: str, n_factors: int | None, state: Path | None = None,
                annualization: int = DEFAULT_ANNUALIZATION, tie: str = DEFAULT_TIE,
                ic_method: str = "spearman", log=print) -> list[dict]:
    """逐 (宇宙, 窗, 因子, 持有期) 出一条 A/B 记录。`state` 给断点续跑（jsonl，一行一条）。"""
    windows = list(windows)
    universes = list(universes)
    done: set[tuple] = set()
    rows: list[dict] = []
    if state is not None and state.is_file():
        for line in state.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            rows.append(r)
            done.add((r["universe"], r["window"], r["factor_id"], str(r["h"])))
        log(f"[resume] 已有 {len(rows)} 条")
    fh = state.open("a", encoding="utf-8") if state is not None else None
    hs = sorted(holding_periods)
    #: 价格缓存只从最早那个窗的起点算起（缓存键带它，所以各窗共用同一份）。
    price_floor = min(_iso(a) for a, _ in windows)
    try:
        for uni in universes:
            for (ws, we) in windows:
                X = Inputs(snap, uni, ws, we, as_of, max(hs), price_min_date=price_floor)
                pre = {h: X.base_valid(h) for h in hs}
                pre_rx = {h: X.base_valid_relaxed(h) for h in hs}
                fwds = {h: X.fwd(h) for h in hs}
                files = pick_factors(gold_dir, uni, n_factors)
                wlab = f"{ws}..{we}"
                log(f"[{uni} {wlab}] {len(files)} 因子 × {len(hs)} 持有期")
                for i, p in enumerate(files, 1):
                    fid = p.stem
                    if all((uni, wlab, fid, str(h)) in done for h in hs):
                        continue
                    try:
                        F = load_factor(p, X.window, X.codes)
                    except Exception as e:                        # 面板本身不可用 —— 记下来，不静默跳
                        log(f"  ! {fid}: {e}")
                        continue
                    finite = pd.DataFrame(np.isfinite(F.to_numpy(dtype=float)),
                                          index=F.index, columns=F.columns)
                    for h in hs:
                        if (uni, wlab, fid, str(h)) in done:
                            continue
                        valid = pre[h] & finite
                        valid_rx = pre_rx[h] & finite
                        A = impl_a_qlib(F, fwds[h], valid, X.n_universe,
                                        ic_method=ic_method, annualization=annualization)
                        B = impl_b_pandas(F, fwds[h], valid, X.n_universe,
                                          tie=tie, annualization=annualization)
                        C = impl_c_pandas_limits_tradable(F, fwds[h], valid_rx, X.n_universe,
                                                          tie=tie, annualization=annualization)
                        rec = {"universe": uni, "window": wlab, "factor_id": fid, "h": h,
                               "n_days": int(len(X.window)), "n_valid_cells": int(valid.to_numpy().sum()),
                               "n_valid_cells_relaxed": int(valid_rx.to_numpy().sum()),
                               "A": A, "B": B, "C": C}
                        rows.append(rec)
                        if fh is not None:
                            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    if fh is not None and i % 25 == 0:
                        fh.flush()
                        log(f"  … {i}/{len(files)}")
    finally:
        if fh is not None:
            fh.flush()
            fh.close()
    return rows


#: 参与全对比较的实现名（顺序即产物里 `worst_pair` 的写法）。
IMPLS: tuple[str, ...] = ("A", "B", "C")


def pairwise_worst(row: dict, metric: str) -> "dict[str, Any] | None":
    """一条样本上、一个指标的**全对最大分歧**（2.2b `compare_pairwise` 的同一取法）。

    比「A vs B」干净：A（qlib）是一份**特定**实现，带自己的口径怪癖；ε 要量的是
    「两份诚实实现的自然分歧」，用一组独立读法的全对最大差更贴近这个定义。
    """
    import itertools
    vals = {}
    for k in IMPLS:
        v = (row.get(k) or {}).get(metric)
        if v is None:
            continue
        v = float(v)
        if np.isfinite(v):
            vals[k] = v
    if len(vals) < 2:
        return None
    kind = tolerance_kind(metric)
    best = None
    for x, y in itertools.combinations(sorted(vals), 2):
        d = {"pair": f"{x}|{y}", "rel": _rel(vals[x], vals[y]), "abs": abs(vals[x] - vals[y])}
        if best is None or d["abs" if kind == "absolute" else "rel"] > best["abs" if kind == "absolute" else "rel"]:
            best = d
    return best


def aggregate(rows: list[dict], *, holding_periods: Iterable[int],
              sensitivity_rows: "list[dict] | None" = None) -> dict[str, Any]:
    """样本 → 逐持有期的带 + 逐宇宙的分歧分布。"""
    hs = sorted(holding_periods)
    by_h: dict[str, Any] = {}
    for h in hs:
        sub = [r for r in rows if int(r["h"]) == h]
        per: dict[str, Any] = {}
        for m in IC_METRICS:
            diffs = [d for d in (pairwise_worst(r, m) for r in sub) if d is not None]
            per[m] = band_from_diffs(m, diffs)
        for m in NO_PAIR_METRICS:
            per[m] = {"status": "no_pair_in_qlib_path", "epsilon": None,
                      "tolerance_kind": tolerance_kind(m), "unit": "—",
                      "note": ("qlib 口径（SigAnaRecord）**不产 bootstrap 区间** —— "
                               "双实现对在这一项上构不成。硬造第二份自举实现量到的是 RNG 抽样，"
                               "不是实现自由度。不出带，L3 跳过。")}
        ok = [m for m, r in per.items() if r["status"] == "calibrated"]
        bad = [m for m, r in per.items() if r["status"] == "implausible_stop_and_report"]
        free = [m for m, r in per.items() if r["status"] == "no_implementation_freedom"]
        by_h[str(h)] = {
            "by_metric": per, "calibrated": ok, "implausible": bad, "no_freedom": free,
            "no_pair": list(NO_PAIR_METRICS),
            "n_samples": len(sub),
            "usable": (not bad) and bool(ok),
        }
    by_u: dict[str, Any] = {}
    for uni in sorted({r["universe"] for r in rows}):
        sub = [r for r in rows if r["universe"] == uni]
        by_u[uni] = {"n_samples": len(sub), "by_metric": {}}
        for m in IC_METRICS:
            xs = [d["abs"] for d in (pairwise_worst(r, m) for r in sub) if d is not None]
            if not xs:
                continue
            a = np.array(xs)
            by_u[uni]["by_metric"][m] = {
                "n": int(len(a)), "abs_p50": float(np.quantile(a, 0.5)),
                "abs_p90": float(np.quantile(a, 0.9)), "abs_max": float(a.max()),
                "zero_diff_ratio": float((a == 0.0).mean()),
            }
    #: 样本面的**实际**构成 —— 长跑可能没跑满（并行三个宇宙、按时间盒收口），
    #: 不把它写出来的话，「792 因子 × 3 宇宙」就是一句没有证据的话。
    cov: dict[str, Any] = {}
    for uni in sorted({r["universe"] for r in rows}):
        for w in sorted({r["window"] for r in rows if r["universe"] == uni}):
            fs = {r["factor_id"] for r in rows if r["universe"] == uni and r["window"] == w}
            cov[f"{uni}|{w}"] = {"n_factors": len(fs),
                                 "n_rows": len([r for r in rows if r["universe"] == uni
                                                and r["window"] == w])}
    #: **换一个窗，带会不会变一个数量级？** 判据只落在 v1.0 冒烟集那一个窗上，
    #: 但带若对窗极度敏感，那说明量到的不是"实现自由度"而是"这半年的行情"。
    srows = rows if sensitivity_rows is None else sensitivity_rows
    by_w: dict[str, Any] = {}
    for w in sorted({r["window"] for r in srows}):
        sub = [r for r in srows if r["window"] == w]
        blk: dict[str, Any] = {"n_samples": len(sub),
                               "n_factors": len({r["factor_id"] for r in sub}),
                               "universes": sorted({r["universe"] for r in sub}),
                               "by_metric": {}}
        for m in IC_METRICS:
            ds = [d for d in (pairwise_worst(r, m) for r in sub) if d is not None]
            key = "abs" if tolerance_kind(m) == "absolute" else "rel"
            xs = np.array([d[key] for d in ds if np.isfinite(d[key])], dtype=float)
            if len(xs):
                blk["by_metric"][m] = {"n": int(len(xs)),
                                       "p90": float(np.quantile(xs, BAND_QUANTILE)),
                                       "epsilon_if_this_window_only":
                                           float(np.quantile(xs, BAND_QUANTILE)) * MULTIPLIER}
        by_w[w] = blk
    return {"by_holding_period": by_h, "by_universe": by_u,
            "by_window_sensitivity": by_w, "sample_coverage": cov}


def icir_ambiguity(rows: list[dict], annualization: int) -> dict[str, Any]:
    """把 ICIR 的年化歧义单列出来：**它不是容差，是题面没写清**（见模块 docstring）。"""
    return {
        "what": "SigAnaRecord 的 ICIR = ic.mean()/ic.std()，**不年化**；S4 题面声明 "
                "annualization=252 而参考实现年化（×√annualization）。",
        "ratio": math.sqrt(annualization),
        "relative_gap": abs(math.sqrt(annualization) - 1.0) / math.sqrt(annualization),
        "decision": "标定时**两边都年化** —— 量的才是实现自由度而不是单位差。"
                    "年化与否本身按 2.2b 的纪律属于「声明没写清」，登记为票据，不写成 ε。",
        "n_samples": len([r for r in rows if np.isfinite(float(r["A"].get("icir", np.nan)))]),
    }


def load_state(state: Path) -> list[dict]:
    """把断点盘读回来。`state` 是目录时读它下面全部 `*.jsonl`
    （三个宇宙并行跑各写各的盘，出带时要合起来看）。"""
    files = sorted(state.glob("*.jsonl")) if state.is_dir() else [state]
    rows = []
    for f in files:
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def build(*, gold_dir: Path, snap: Path, out: Path, universes: Iterable[str],
          windows: Iterable[tuple[str, str]], holding_periods: Iterable[int], as_of: str,
          n_factors: int | None, state: Path | None, annualization: int = DEFAULT_ANNUALIZATION,
          tie: str = DEFAULT_TIE, ic_method: str = "spearman", aggregate_only: bool = False,
          log=print) -> dict[str, Any]:
    prov = qlib_impl_provenance()
    if aggregate_only:
        if state is None or not (state.is_file() or state.is_dir()):
            raise SystemExit("--aggregate-only 需要一个存在的 --state")
        rows_all = load_state(state)
        keep = {f"{a}..{b}" for a, b in windows}
        rows = [r for r in rows_all if r["window"] in keep]
        log(f"[aggregate-only] {len(rows)} 条样本（窗过滤后：{sorted(keep)}）")
        if not rows:
            raise SystemExit(f"断点盘里没有这些窗的样本：{sorted(keep)}")
    else:
        rows_all = rows = run_samples(gold_dir, snap, universes=universes, windows=windows,
                                      holding_periods=holding_periods, as_of=as_of,
                                      n_factors=n_factors, state=state,
                                      annualization=annualization, tie=tie,
                                      ic_method=ic_method, log=log)
    # 带只用**判据窗**的样本（保持三个宇宙等量）；窗敏感性用**全部**样本，
    # 好回答「换一个窗带会不会变一个数量级」而不必重跑。
    agg = aggregate(rows, holding_periods=holding_periods, sensitivity_rows=rows_all)
    hs = sorted(holding_periods)
    all_ok = sorted({m for h in hs for m in agg["by_holding_period"][str(h)]["calibrated"]})
    all_bad = sorted({m for h in hs for m in agg["by_holding_period"][str(h)]["implausible"]})
    all_free = sorted({m for h in hs for m in agg["by_holding_period"][str(h)]["no_freedom"]})
    payload: dict[str, Any] = {
        "card": "N-117",
        "schema_version": 1,
        "method": "dual_independent_implementation_ic",
        "built_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "code_head": _git_head(_REPO),
        "channel": "private" if str(snap).startswith(str(cfg.SNAPSHOTS_V1)) else str(snap),
        "inputs": {"gold_dir": str(gold_dir), "snapshot_dir": str(snap),
                   "universes": list(universes), "windows": [f"{a}..{b}" for a, b in windows],
                   "as_of": as_of, "holding_periods": hs,
                   "n_factors_per_universe": n_factors, "n_samples": len(rows)},
        "declaration": {"ic_method": ic_method, "tie_handling": tie,
                        "annualization": annualization,
                        "valid_cell_rule": "因子非有限 / 当日不可交易 / 远期收盘缺失 / 远期日期越过 as_of → 剔除"
                                           "（题面 INSTRUCTION 逐条写死，**两份实现共用**）"},
        "implementation_pair": {
            "A": {"label": "qlib 口径（SigAnaRecord 的计算路径）", **prov},
            "B": {"label": "纯 pandas 口径", "entry": "ops.ic_epsilon.impl_b_pandas",
                  "how": "逐截面 rank(平局 average) → Pearson；最小截面门槛 "
                         f"{MIN_CROSS_SECTION}；positive_ratio 分母 = IC 有定义的日子；"
                         "coverage 分母 = 窗口内全部交易日；「不可交易」= status != trade。"},
            "C": {"label": "纯 pandas 口径 + 另一种「不可交易」读法",
                  "entry": "ops.ic_epsilon.impl_c_pandas_limits_tradable",
                  "how": "与 B 同一份汇总代码，只把「不可交易」读成 status ∈ {suspend, no_data}"
                         "（涨跌停当天股票是成交的）。"},
            "aggregation": "全对最大分歧（A|B, A|C, B|C 取最大）—— 与 2.2b 的 compare_pairwise 同法。",
            "freedom": ["「当日不可交易」指什么：`trade` 之外全算，还是只算停牌 / 无数据"
                        "（涨跌停约占 10% 的格）",
                        "最小截面门槛（题面没写）",
                        "positive_ratio / coverage 的分母算不算 NaN 日",
                        "一格都没有的交易日进不进 coverage"],
            "not_freedom": ["因子非有限 / 远期收盘缺失 / 远期日期越过 as_of（题面逐条写死，三份共用）",
                            "ICIR 年化（声明歧义，见 icir_annualization_ambiguity）"],
        },
        "multiplier": MULTIPLIER,
        "noise_floor": NOISE_FLOOR,
        "implausible_threshold": IMPLAUSIBLE_REL_DIFF,
        "band_quantile": BAND_QUANTILE,
        "band_rule": (f"ε = 分歧分布的 P{int(BAND_QUANTILE * 100)} × {MULTIPLIER}。"
                      f"2.2b 是「全对最大差 × {MULTIPLIER}」，那里样本面只有 3 个数；"
                      f"这里样本面是 N 因子 × M 宇宙的分布，取最大 = 让带被最病态的因子绑架。"
                      f"P{int(BAND_QUANTILE * 100)} 是 τ 的 P10 的镜像（同样允许 10% 的尾巴落在带外）。"
                      f"每条带同时报 P50/P95/P99/max 与 epsilon_if_max_rule。"),
        "tolerance_rule": {
            "relative": f"尺度无关且不趋零：{sorted(set(IC_METRICS) - ZERO_APPROACHING)}",
            "absolute": f"构造上可能趋零：{sorted(ZERO_APPROACHING)}；ε = |A−B| × {MULTIPLIER}",
            "why": "没有预测力的因子 IC 均值就是 0，ICIR 的分子是它 —— 相对容差在它们上没有意义。",
            "enforced_by": "产物里逐指标写 tolerance_kind；scorer 读它，不自己判断。",
        },
        "icir_annualization_ambiguity": icir_ambiguity(rows, annualization),
        "no_ci_calibration": {
            "metrics": list(NO_PAIR_METRICS),
            "why": "qlib 口径没有 bootstrap 区间，双实现对构不成 —— 不出带，L3 跳过。",
        },
        **agg,
        "calibrated": all_ok, "implausible": all_bad, "no_freedom": all_free,
        "no_pair": list(NO_PAIR_METRICS),
        #: `usable` 沿用 2.2b 的严格含义：**每一个**要标的指标都拿到了带。
        #: 有一个超阈就是 False —— 那句话说的是「这一族的标定还没收完」，
        #: **不是**「一条带都不能用」。L3 是逐指标按 `status` 取带的，
        #: 所以 `usable=False` 与「S4 能不能结算」是两件事，别把它们读成一件。
        "usable": bool(all_ok) and not all_bad,
        "usable_metrics": all_ok,
        "unusable_metrics": {"implausible": all_bad, "no_freedom": all_free,
                             "no_pair": list(NO_PAIR_METRICS)},
        "verdict": (f"{len(all_ok)}/{len(IC_METRICS)} 个 IC 指标拿到带：{all_ok}。"
                    + (f"超阈未出带：{all_bad}（按 2.2b 纪律，>{IMPLAUSIBLE_REL_DIFF:.0%} 的相对分歧"
                       f"不像实现自由度，多半是声明没写清 —— 停下汇报）。" if all_bad else "")
                    + (f"无实现自由度：{all_free}（E-1：不得把 ε 写成 0）。" if all_free else "")
                    + f"双实现对构不成：{list(NO_PAIR_METRICS)}（qlib 口径没有 bootstrap 区间）。"
                    + "L3 逐指标按 status 取带，因此 S4 的 l3_pass 仍然算得出来。"),
    }
    cfg.create_dir(out.parent)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    out.chmod(0o600)
    log(f"→ {out}")
    return payload


def _print_table(payload: dict[str, Any], log=print) -> None:
    for h, blk in payload["by_holding_period"].items():
        log(f"--- h={h}（{blk['n_samples']} 样本）---")
        log(f"{'指标':<18}{'P50':>12}{'P90':>12}{'max':>12}{'ε':>12}  类型  状态")
        for m, r in blk["by_metric"].items():
            q = r.get("diff_quantiles") or {}
            e = "—" if r.get("epsilon") is None else format(r["epsilon"], ".4g")
            f = lambda v: "—" if v is None else format(v, ".4g")            # noqa: E731
            log(f"{m:<18}{f(q.get('p50')):>12}{f(q.get('p90')):>12}"
                f"{f(r.get('diff_max')):>12}{e:>12}  "
                f"{'abs' if r.get('tolerance_kind') == 'absolute' else 'rel':<5} {r['status']}")
        log(f"可标定 {blk['calibrated']} · 超阈 {blk['implausible']} · 无自由度 {blk['no_freedom']}\n")


def main(argv: "list[str] | None" = None) -> int:
    cfg.harden_umask()
    p = argparse.ArgumentParser(description="N-117：S4 IC 族 ε 双实现标定")
    p.add_argument("--gold-dir", default=str(cfg.SNAPSHOTS_V1 / "gold_factors"))
    p.add_argument("--provider-dir", default=str(cfg.SNAPSHOTS_V1),
                   help="含 tables/ universe/ tradability/ 的快照根。公开通道传 snapshots/public_v1 —— "
                        "但它当前**没有 universe/**，会被 Inputs.preflight() 拦下并说清缺哪件")
    p.add_argument("--out", default=str(OUT_DEFAULT))
    p.add_argument("--universes", nargs="+", default=list(cfg.UNIVERSES))
    p.add_argument("--holding-periods", nargs="+", type=int, default=list(DEFAULT_HOLDING_PERIODS))
    p.add_argument("--as-of", default=DEFAULT_AS_OF)
    p.add_argument("--windows", nargs="+", default=[f"{a}..{b}" for a, b in DEFAULT_WINDOWS],
                   help="START..END，可多个")
    p.add_argument("--factors", type=int, default=None, help="每宇宙等距抽样这么多因子（默认全部）")
    p.add_argument("--state", default=None, help="断点续跑盘（jsonl）")
    p.add_argument("--aggregate-only", action="store_true",
                   help="不跑样本，只把 --state 里已有的样本聚成带（长跑与出带分开）")
    p.add_argument("--quiet", action="store_true")
    a = p.parse_args(argv)
    log = (lambda *x: None) if a.quiet else print
    wins = [tuple(w.split("..")) for w in a.windows]
    rep = build(gold_dir=Path(a.gold_dir), snap=Path(a.provider_dir), out=Path(a.out),
                universes=a.universes, windows=wins, holding_periods=a.holding_periods,
                as_of=a.as_of, n_factors=a.factors,
                state=Path(a.state) if a.state else None,
                aggregate_only=a.aggregate_only, log=log)
    _print_table(rep, log=log)
    return 0 if rep["usable"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
