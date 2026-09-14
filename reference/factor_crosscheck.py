# -*- coding: utf-8 -*-
"""卡 2.1b 验收：双实现互检 + 秩相关分布（= 卡 2.2 的 τ 原料）。

    cd $REPO && ulimit -n 8192 && $GENEBENCH_ROOT/env/bin/python -m reference.factor_crosscheck

--------------------------------------------------------------------------
"第二个实现"从哪来
--------------------------------------------------------------------------

每条因子记录同时带 ``expression``（源方言原文）与 ``compiled_expression``（编译后）。
gold 走 ``compiled_expression`` + 它自己的引擎；互检把**源方言原文**喂给**另一个引擎**：

===================== ============================== ==============================
后端                  实现 A（= gold）                实现 B（互检）
===================== ============================== ==============================
qlib_expression       qlib 表达式引擎（逐票）        pandas 面板求值器（GTJA 方言）
qlib_kunquant_loader  KunQuant JIT 编译的 C++         pandas 面板求值器（WQ 方言）
qlib_panel_loader     pandas 面板求值器               —— **同一个引擎**，排除
===================== ============================== ==============================

``qlib_panel_loader`` 那 66 条**排除**，理由是判别力不是省事：A/B 会落在同一个引擎上，
若 ``expression`` 与 ``compiled_expression`` 还是同一个字符串，"互检"恒等于 1.0，
是自证式比较，混进 τ 的样本会把 τ 往上拉。本模块**当场检查**这一点（``identical_strings``）。

--------------------------------------------------------------------------
秩相关口径（2026-09-01 签字冻结，改任何一条都要重标 τ）
--------------------------------------------------------------------------

**F-1 算法** —— 逐交易日在**截面**上算 Spearman，再对时间序列取分布。
与 IC 的算法同构，也与 Table B 的 S4 口径一致。
tie 用**平均法**（与对接决定 §"分位/Spread"里冻结的平局处理一致）。

**F-2 τ 的取法** —— τ = **"全因子 × 全交易日"这个二维分布的 P10**。
**不是**先对时间平均再取分位 —— 那会把"某些日子完全失配"的因子藏在均值里，
而 S3 的 Fid% 判的是"这一天这个因子算对没有"，判定粒度就是 (因子, 日)。

**F-3 三个数一起报** —— ① 逐日分布 P10（= τ）；② 按因子聚合（对时间取均值）后的
因子级 P10；③ 两者的差。差很大说明失配**集中在少数日子**而不是均匀分布，
那是另一个故事，要写进标定报告。

**F-4 degenerate 必须先剔** —— Spearman 对结（tie）敏感：一个几乎处处常数的因子，
两个实现都输出常数时秩相关是 NaN 或接近 1，**两种情况都会毒化 τ 的分布尾部**。
判据：某 (因子, 日) 的截面上，任一侧的**唯一值数** < ``DEGENERATE_UNIQUE_RATIO``
× 该截面的有效标的数 → 标 ``degenerate``，**排除出 τ 样本**，不参与分位数。

**F-5 剔除率要按两个维度报** —— 按因子、按日各报一次。
若某后端的 degenerate 率显著更高，**那是后端语义差异的信号，属于要记录的事实**，
不是可以抹平的噪声。全窗 degenerate 的因子**单独列名**，进 N-17 的首批测试样本。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import genebench_config as cfg
from reference import factor_exec as fx

REPORT_JSON: Path = cfg.OPS / "acceptance" / "card_2.1b_crosscheck.json"
CELLS_DIR: Path = cfg.SNAPSHOTS_V1 / "crosscheck"

#: 实施稿要求"抽 30 条跨后端可比因子"。这是**下界**，不是抽样目标：能比的全比。
MIN_COMPARABLE: int = 30

#: degenerate 判据：唯一值数 / 截面有效标的数 的下限。
#:
#: **阈值来源**（要求"阈值来源一并记录"）：签字人 2026-09-01 指定 5%，
#: 与 N-17「因子退化检测」同源 —— 那条也是拿"因子在截面上还剩多少分辨力"当判据。
#: 这个数**不许拍**的部分是 N-17 的上线阈值（D-04 规定它要用 792 条的实测 P5）；
#: 这里是标定期的**样本清洗**阈值，用签字指定值，同时把实测的
#: 唯一值比例分布一并报出，好让签字人看见 5% 落在分布的什么位置。
DEGENERATE_UNIQUE_RATIO: float = 0.05
DEGENERATE_THRESHOLD_SOURCE: str = (
    "签字人 2026-09-01 指定：唯一值数 < 截面标的数 × 5%；与 N-17 因子退化检测同源。"
    "N-17 自己的上线阈值受 D-04 约束（须用 792 条实测覆盖率分布的 P5），与本阈值不是同一个数。"
)

#: 截面小于这个数就不算一个有效截面（成分不足，秩相关没有意义）。
MIN_CROSS_SECTION: int = 20

#: τ 取的分位。
TAU_QUANTILE: float = 10.0

__all__ = ["crosscheck", "MIN_COMPARABLE", "DEGENERATE_UNIQUE_RATIO", "TAU_QUANTILE"]


# ---------------------------------------------------------------- 向量化工具

def _row_nunique(m: np.ndarray) -> np.ndarray:
    """每行的**唯一有限值**个数。NaN/inf 不计。

    逐行 ``set()`` 在 159×2,716 上要跑几分钟；排序后数相邻不等的位置是 O(n log n) 且全向量化。
    """
    finite = np.isfinite(m)
    s = np.sort(np.where(finite, m, np.inf), axis=1)
    nv = finite.sum(axis=1)
    neq = s[:, 1:] != s[:, :-1]
    idx = np.arange(s.shape[1] - 1)[None, :]
    within = idx < (nv[:, None] - 1)
    return np.where(nv > 0, 1 + (neq & within).sum(axis=1), 0)


def _row_spearman(a: pd.DataFrame, b: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """逐行（= 逐交易日）截面 Spearman，tie 用平均法。返回 (rho, n_valid)。

    实现方式：先对每行取秩（``DataFrame.rank(axis=1)`` 的平局处理就是平均法），
    再对秩做逐行 Pearson —— 这与 ``scipy.stats.spearmanr`` 的定义等价，
    但避免 43 万次 Python 级调用。
    """
    mask = np.isfinite(a.to_numpy()) & np.isfinite(b.to_numpy())
    am = a.where(mask)
    bm = b.where(mask)
    ra = am.rank(axis=1).to_numpy()
    rb = bm.rank(axis=1).to_numpy()
    n = mask.sum(axis=1)
    ma = np.nanmean(np.where(mask, ra, np.nan), axis=1)
    mb = np.nanmean(np.where(mask, rb, np.nan), axis=1)
    da = np.where(mask, ra - ma[:, None], 0.0)
    db = np.where(mask, rb - mb[:, None], 0.0)
    num = (da * db).sum(axis=1)
    den = np.sqrt((da ** 2).sum(axis=1) * (db ** 2).sum(axis=1))
    with np.errstate(invalid="ignore", divide="ignore"):
        rho = np.where(den > 0, num / den, np.nan)
    rho = np.where(n >= MIN_CROSS_SECTION, rho, np.nan)
    return rho, n


def _q(x: np.ndarray, ps: "tuple[float, ...]" = (1, 5, 10, 25, 50, 75, 90, 99)) -> dict[str, float]:
    if x.size == 0:
        return {}
    out = {f"p{int(p):02d}": float(np.percentile(x, p)) for p in ps}
    out.update(n=int(x.size), mean=float(x.mean()), min=float(x.min()), max=float(x.max()))
    return out


def _hist(x: np.ndarray, edges: "tuple[float, ...]") -> list[dict[str, Any]]:
    """给报告用的直方图（分布图的数据形式，落盘后由报告渲染）。"""
    if x.size == 0:
        return []
    cnt, _ = np.histogram(x, bins=list(edges))
    return [{"lo": float(edges[i]), "hi": float(edges[i + 1]),
             "n": int(cnt[i]), "frac": float(cnt[i] / x.size)} for i in range(len(cnt))]


HIST_EDGES: tuple[float, ...] = (-1.0, -0.5, 0.0, 0.5, 0.8, 0.9, 0.95, 0.99, 0.999, 1.0001)


# ---------------------------------------------------------------- 主流程

def _load_gold(universe: str, fid: str) -> "pd.DataFrame | None":
    p = fx.GOLD_DIR / universe / f"{fid}.parquet"
    if not p.exists():
        return None
    t = pd.read_parquet(p)
    if t.empty:
        return None
    t["date"] = pd.to_datetime(t["date"], format="%Y%m%d")
    return t.pivot(index="date", columns="code", values="value")


def crosscheck(universe: str = "csi300", start: str = "2015-05-29",
               end: "str | None" = None, *, verbose: bool = True) -> dict[str, Any]:
    end = end or cfg.FREEZE_DATE
    t0 = time.time()
    recs, prov = fx.load_records()
    ex = [r for r in recs if r.get("executable")]
    fx.init_qlib()
    from qlib.data import D

    from reference.factorlib_pinned import qlib_loader
    from reference.factorlib_pinned.formula import parse_formula

    panels = qlib_loader._raw_panels(D.instruments(universe), start, end, fx.WARMUP_DAYS)
    ev = qlib_loader.PanelFormulaEvaluator(panels)
    if verbose:
        print(f"原始面板 {panels['CLOSE'].shape}；候选 {len(ex)} 条", flush=True)

    cells: list[pd.DataFrame] = []
    rows: list[dict[str, Any]] = []
    skipped: dict[str, list[Any]] = {"same_engine": [], "parse_fail": [],
                                     "eval_fail": [], "no_gold": [], "no_overlap": []}
    uratio_samples: list[np.ndarray] = []

    for n, r in enumerate(ex, 1):
        fid, backend = r["id"], r["execution_backend"]
        taut = str(r["expression"]).strip() == str(r["compiled_expression"]).strip()
        if backend == "qlib_panel_loader":
            skipped["same_engine"].append({"id": fid, "identical_strings": taut})
            continue
        try:
            node = parse_formula(r["expression"])
        except Exception as exc:
            skipped["parse_fail"].append([fid, f"{type(exc).__name__}: {str(exc)[:90]}"])
            continue
        try:
            b = ev.evaluate(node)
            if not isinstance(b, pd.DataFrame):
                raise TypeError(f"第二实现返回 {type(b).__name__}，不是面板")
        except Exception as exc:
            skipped["eval_fail"].append([fid, f"{type(exc).__name__}: {str(exc)[:90]}"])
            continue
        a = _load_gold(universe, fid)
        if a is None:
            skipped["no_gold"].append(fid)
            continue
        b = b.reindex(index=a.index, columns=a.columns)

        rho, nval = _row_spearman(a, b)
        av, bv = a.to_numpy(), b.to_numpy()
        both = np.isfinite(av) & np.isfinite(bv)
        ua = _row_nunique(np.where(both, av, np.nan))
        ub = _row_nunique(np.where(both, bv, np.nan))
        thr = np.maximum(1, np.floor(DEGENERATE_UNIQUE_RATIO * nval))
        degen = (nval < MIN_CROSS_SECTION) | (ua < thr) | (ub < thr)
        with np.errstate(invalid="ignore", divide="ignore"):
            uratio = np.where(nval > 0, np.minimum(ua, ub) / nval, np.nan)
        uratio_samples.append(uratio[np.isfinite(uratio)])

        cells.append(pd.DataFrame({
            "factor_id": fid, "backend": backend, "family": r["family"],
            "date": a.index.strftime("%Y%m%d"),
            "rho": rho, "n_valid": nval.astype("int32"),
            "n_unique_a": ua.astype("int32"), "n_unique_b": ub.astype("int32"),
            "degenerate": degen,
        }))

        keep = np.isfinite(rho) & ~degen
        raw_keep = np.isfinite(rho)
        rows.append({
            "id": fid, "family": r["family"], "backend": backend,
            "identical_strings": taut,
            "days": int(len(rho)),
            "days_with_rho": int(raw_keep.sum()),
            "days_kept": int(keep.sum()),
            "days_degenerate": int(degen.sum()),
            "degenerate_rate": float(degen.mean()),
            "median_cross_section": int(np.median(nval)) if nval.size else 0,
            "mean_rho_kept": float(rho[keep].mean()) if keep.any() else float("nan"),
            "median_rho_kept": float(np.median(rho[keep])) if keep.any() else float("nan"),
            "p10_rho_kept": float(np.percentile(rho[keep], 10)) if keep.any() else float("nan"),
            "min_rho_kept": float(rho[keep].min()) if keep.any() else float("nan"),
            "mean_rho_raw": float(rho[raw_keep].mean()) if raw_keep.any() else float("nan"),
        })
        if verbose and n % 100 == 0:
            print(f"  {n}/{len(ex)}；已比 {len(rows)} 条", flush=True)

    if not rows:
        raise RuntimeError("一条都没比上 —— 去查 gold 是否已生成")

    cell = pd.concat(cells, ignore_index=True)
    cfg.create_dir(CELLS_DIR)
    cp = CELLS_DIR / f"rank_ic_cells_{universe}.parquet"
    cell.to_parquet(cp, index=False, compression="zstd")
    cp.chmod(0o600)

    fin = cell["rho"].to_numpy()
    kept = cell.loc[np.isfinite(fin) & ~cell["degenerate"], "rho"].to_numpy()
    raw = cell.loc[np.isfinite(fin), "rho"].to_numpy()

    # ---- F-3 三种取法 --------------------------------------------------
    per_factor_mean = np.array([x["mean_rho_kept"] for x in rows], dtype="float64")
    per_factor_mean = per_factor_mean[np.isfinite(per_factor_mean)]
    per_factor_median = np.array([x["median_rho_kept"] for x in rows], dtype="float64")
    per_factor_median = per_factor_median[np.isfinite(per_factor_median)]

    tau_pooled = float(np.percentile(kept, TAU_QUANTILE)) if kept.size else float("nan")
    tau_factor_mean = (float(np.percentile(per_factor_mean, TAU_QUANTILE))
                       if per_factor_mean.size else float("nan"))
    tau_factor_median = (float(np.percentile(per_factor_median, TAU_QUANTILE))
                         if per_factor_median.size else float("nan"))
    tau_pooled_raw = float(np.percentile(raw, TAU_QUANTILE)) if raw.size else float("nan")

    # ---- F-5 剔除率：按因子 / 按日 --------------------------------------
    by_day = cell.groupby("date").agg(
        cells=("degenerate", "size"), degen=("degenerate", "sum")).reset_index()
    by_day["rate"] = by_day["degen"] / by_day["cells"]
    all_window_degenerate = [x["id"] for x in rows if x["days_kept"] == 0]
    high_degen_factors = sorted(
        ({"id": x["id"], "backend": x["backend"], "rate": x["degenerate_rate"]}
         for x in rows if x["degenerate_rate"] > 0.5),
        key=lambda z: -z["rate"])

    per_backend: dict[str, Any] = {}
    for bkd in sorted({x["backend"] for x in rows}):
        sub = cell[cell["backend"] == bkd]
        k = sub.loc[np.isfinite(sub["rho"]) & ~sub["degenerate"], "rho"].to_numpy()
        fm = np.array([x["mean_rho_kept"] for x in rows if x["backend"] == bkd])
        fm = fm[np.isfinite(fm)]
        per_backend[bkd] = {
            "factors": sum(1 for x in rows if x["backend"] == bkd),
            "cells": int(len(sub)),
            "degenerate_rate": float(sub["degenerate"].mean()),
            "pooled": _q(k), "pooled_hist": _hist(k, HIST_EDGES),
            "factor_level_mean": _q(fm),
            "tau_pooled_p10": float(np.percentile(k, TAU_QUANTILE)) if k.size else float("nan"),
        }

    ur = np.concatenate(uratio_samples) if uratio_samples else np.array([])
    report = {
        "card": "2.1b",
        "built_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "universe": universe, "start": start, "end": end,
        "methodology": {
            "F-1": "逐交易日截面 Spearman（tie 平均法），再对时间序列取分布",
            "F-2": f"τ = 全因子 × 全交易日 二维分布的 P{int(TAU_QUANTILE)}（不是先对时间平均再取分位）",
            "F-4_degenerate": (f"任一侧唯一值数 < {DEGENERATE_UNIQUE_RATIO:.0%} × 截面有效标的数 "
                               f"→ 剔出 τ 样本"),
            "degenerate_threshold_source": DEGENERATE_THRESHOLD_SOURCE,
            "min_cross_section": MIN_CROSS_SECTION,
        },
        "comparable_factors": len(rows),
        "min_required": MIN_COMPARABLE,
        "meets_requirement": len(rows) >= MIN_COMPARABLE,
        "cells_total": int(len(cell)),
        "cells_with_rho": int(np.isfinite(fin).sum()),
        "cells_degenerate": int(cell["degenerate"].sum()),
        "cells_kept": int(kept.size),

        # ---- 三种取法（F-3） ----
        "tau_candidates": {
            "pooled_factor_x_day_p10": tau_pooled,          # ← 这是 τ
            "factor_level_mean_p10": tau_factor_mean,
            "factor_level_median_p10": tau_factor_median,
            "delta_pooled_minus_factor_mean": tau_pooled - tau_factor_mean,
            "delta_pooled_minus_factor_median": tau_pooled - tau_factor_median,
        },
        "distributions": {
            "pooled_kept": _q(kept), "pooled_kept_hist": _hist(kept, HIST_EDGES),
            "pooled_raw_before_degenerate_removal": _q(raw),
            "pooled_raw_hist": _hist(raw, HIST_EDGES),
            "factor_level_mean": _q(per_factor_mean),
            "factor_level_mean_hist": _hist(per_factor_mean, HIST_EDGES),
            "factor_level_median": _q(per_factor_median),
        },
        "contamination": {
            "tau_before_degenerate_removal": tau_pooled_raw,
            "tau_after_degenerate_removal": tau_pooled,
            "shift": tau_pooled - tau_pooled_raw,
            "cells_removed": int(cell["degenerate"].sum()),
            "cells_removed_frac": float(cell["degenerate"].mean()),
        },
        "degenerate_by_backend": {b: per_backend[b]["degenerate_rate"] for b in per_backend},
        "degenerate_by_day": {
            "days": int(len(by_day)),
            "rate_quantiles": _q(by_day["rate"].to_numpy(), (1, 10, 50, 90, 99)),
            "worst_10_days": by_day.nlargest(10, "rate")[["date", "rate", "degen", "cells"]]
                                   .to_dict("records"),
        },
        "degenerate_by_factor": {
            "all_window_degenerate": all_window_degenerate,
            "rate_above_50pct": high_degen_factors,
            "rate_quantiles": _q(np.array([x["degenerate_rate"] for x in rows]),
                                 (1, 10, 50, 90, 99)),
        },
        "unique_value_ratio_observed": {
            "note": ("实测的 min(唯一值数A, 唯一值数B) / 截面有效标的数 分布，"
                     f"用来看签字指定的 {DEGENERATE_UNIQUE_RATIO:.0%} 落在分布的什么位置"),
            **_q(ur, (0.1, 1, 5, 10, 25, 50)),
            "frac_below_threshold": float((ur < DEGENERATE_UNIQUE_RATIO).mean()) if ur.size else 0.0,
        },
        "per_backend": per_backend,
        "worst_20_factors": sorted(rows, key=lambda x: (x["mean_rho_kept"]
                                                        if np.isfinite(x["mean_rho_kept"]) else -9))[:20],
        "skipped": skipped,
        "skipped_counts": {k: len(v) for k, v in skipped.items()},
        "cells_parquet": str(cp),
        "factor_library": prov,
        "elapsed_s": round(time.time() - t0, 1),
        "rows": rows,
    }
    cfg.create_dir(REPORT_JSON.parent)
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str),
                           encoding="utf-8")
    REPORT_JSON.chmod(0o600)
    if verbose:
        print(f"可比 {len(rows)} 条；格 {len(cell):,}；剔除 {report['cells_degenerate']:,} "
              f"（{report['contamination']['cells_removed_frac']:.2%}）")
        print(f"τ(pooled P10) = {tau_pooled:.6f}   因子级均值 P10 = {tau_factor_mean:.6f}   "
              f"差 = {tau_pooled - tau_factor_mean:+.6f}")
        print(f"→ {REPORT_JSON}")
    return report


def main(argv: "list[str] | None" = None) -> int:
    p = argparse.ArgumentParser(description="卡 2.1b 双实现互检")
    p.add_argument("--universe", default="csi300", choices=list(cfg.UNIVERSES_PIT))
    p.add_argument("--start", default="2015-05-29")
    p.add_argument("--end", default=cfg.FREEZE_DATE)
    a = p.parse_args(argv)
    rep = crosscheck(a.universe, a.start, a.end)
    return 0 if rep["meets_requirement"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
