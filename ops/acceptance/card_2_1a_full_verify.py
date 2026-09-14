# -*- coding: utf-8 -*-
"""卡 2.1a **全量**验收 + 社区 release 收益率级诊断。

    cd $REPO && ulimit -n 8192 && $GENEBENCH_ROOT/env/bin/python -m ops.acceptance.card_2_1a_full_verify

与 ``ops/test_qlib_provider.py`` 的关系：判据完全相同，那边跑抽样（进套件、秒级），
这边跑全量（一次性、分钟级），结果归档进 `ops/reports/qlib_provider_2.1a.md`。

第 ⑤ 项（与社区 release 比对）**只作诊断，不作判据** —— 两源同宗（都出自 tushare），
一致不构成互证。这条与卡 1.1 的 B-07 一致。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import genebench_config as cfg  # noqa: E402
from snapshots import qlib_provider as qp  # noqa: E402

FREEZE = cfg.FREEZE_DATE.replace("-", "")
TABLES = cfg.SNAPSHOTS_V1 / "tables"
OUT = cfg.OPS / "acceptance" / "card_2.1a_full_verify.json"
DIAG_SAMPLE = 400          # 社区比对的抽样规模（全量 5,817 只读 bin 太慢，且这条不是判据）
DIAG_SEED = 20260731


def _read_code(code: str) -> "dict[str, np.ndarray] | None":
    d = qp.FEATURES_DIR / qp.qlib_code(code).lower()
    if not d.is_dir():
        return None
    cal = qp.calendar()
    out: dict[str, np.ndarray] = {}
    start = n = None
    for f in qp.FIELDS:
        s, a = qp.read_bin(d / f"{f}.day.bin")
        if start is None:
            start, n = s, len(a)
        elif s != start or len(a) != n:
            raise AssertionError(f"{code}/{f} 窗口不一致 {s},{len(a)} vs {start},{n}")
        out[f] = a.astype("float64")
    out["date"] = np.array(cal[start:start + n], dtype=object)
    return out


def full_verify() -> dict:
    con = duckdb.connect(":memory:")
    base = {r[0]: r[1] for r in con.execute(
        f"SELECT ts_code, base_adj_factor FROM read_parquet('{qp.NORM_BASE_PARQUET}')").fetchall()}
    st = {
        "codes": 0, "factor_points": 0, "factor_max_rel": 0.0,
        "price_rows": 0, "price_max_rel": 0.0, "volume_max_rel": 0.0, "amount_max_rel": 0.0,
        "identity_rows": 0, "identity_max_rel": 0.0,
        "vwap_band_in": 0, "vwap_band_total": 0,
        "vwap_out_of_band": [], "inf_cells": 0, "missing_features": [],
        "factor_one_at_freeze": 0, "factor_one_at_own_last": 0,
    }
    for code, g in qp._groups(con):
        pf = _read_code(code)
        if pf is None:
            st["missing_features"].append(code)
            continue
        st["codes"] += 1
        idx = {d: i for i, d in enumerate(pf["date"])}
        b = base[code]
        dates = [str(d) for d in g["trade_date"]]
        for f in qp.FIELDS:
            st["inf_cells"] += int(np.isinf(pf[f]).sum())
        for k, d in enumerate(dates):
            i = idx[d]
            a = g["adj_factor"][k]
            if np.isfinite(a):
                rel = abs(pf["factor"][i] * b - a) / a
                st["factor_max_rel"] = max(st["factor_max_rel"], rel)
                st["factor_points"] += 1
            c = g["close"][k]
            if not np.isfinite(c):
                continue
            fac = pf["factor"][i]
            for name in ("open", "high", "low", "close"):
                want = g[name][k]
                rel = abs(pf[name][i] / fac - want) / max(abs(want), 1e-12)
                st["price_max_rel"] = max(st["price_max_rel"], rel)
            vol, amt = g["volume"][k], g["amount"][k]
            st["volume_max_rel"] = max(
                st["volume_max_rel"], abs(pf["volume"][i] * fac - vol) / max(abs(vol), 1e-12))
            st["amount_max_rel"] = max(
                st["amount_max_rel"], abs(pf["amount"][i] - amt) / max(abs(amt), 1e-12))
            st["price_rows"] += 1
            if np.isfinite(pf["vwap"][i]):
                lhs = pf["vwap"][i] * pf["volume"][i]
                st["identity_max_rel"] = max(
                    st["identity_max_rel"], abs(lhs - pf["amount"][i]) / max(abs(pf["amount"][i]), 1e-12))
                st["identity_rows"] += 1
                lo, hi, t = pf["low"][i], pf["high"][i], qp.VWAP_BAND_REL_TOL
                if lo * (1 - t) <= pf["vwap"][i] <= hi * (1 + t):
                    st["vwap_band_in"] += 1
                elif len(st["vwap_out_of_band"]) < 15:
                    st["vwap_out_of_band"].append(
                        {"code": code, "date": d, "vwap": float(pf["vwap"][i]),
                         "low": float(lo), "high": float(hi),
                         "amount": float(amt), "volume": float(vol)})
                st["vwap_band_total"] += 1
        fin = np.isfinite(pf["factor"])
        if FREEZE in idx and fin[idx[FREEZE]]:
            st["factor_one_at_freeze"] += int(abs(pf["factor"][idx[FREEZE]] - 1) < 1e-6)
        elif fin.any():
            st["factor_one_at_own_last"] += int(abs(pf["factor"][fin][-1] - 1) < 1e-6)
    con.close()
    st["vwap_band_rate"] = st["vwap_band_in"] / max(st["vwap_band_total"], 1)
    st["vwap_out_of_band_n"] = st["vwap_band_total"] - st["vwap_band_in"]
    return st


# --------------------------------------------------------------- ⑤ 社区诊断

def community_diag() -> dict:
    rel = cfg.QLIB_RELEASE
    cal_c = [l.strip() for l in (rel / "calendars" / "day.txt").read_text().split("\n") if l.strip()]
    cal_ours = qp.calendar()
    ours_iso = [f"{d[:4]}-{d[4:6]}-{d[6:]}" for d in cal_ours]
    rng = np.random.default_rng(DIAG_SEED)
    ours_codes = sorted(p.name for p in qp.FEATURES_DIR.iterdir() if p.is_dir())
    both = [c for c in ours_codes if (rel / "features" / c).is_dir()]
    pick = sorted(rng.choice(both, size=min(DIAG_SAMPLE, len(both)), replace=False).tolist())

    idx_c = {d: i for i, d in enumerate(cal_c)}
    idx_o = {d: i for i, d in enumerate(ours_iso)}
    per_code, all_dev = [], []
    for qcode in pick:
        try:
            so, ao = qp.read_bin(qp.FEATURES_DIR / qcode / "close.day.bin")
            sc, ac = qp.read_bin(rel / "features" / qcode / "close.day.bin")
        except Exception:
            continue
        do = {ours_iso[so + i]: v for i, v in enumerate(ao)}
        dc = {cal_c[sc + i]: v for i, v in enumerate(ac) if sc + i < len(cal_c)}
        common = sorted(set(do) & set(dc) & set(idx_o))
        if len(common) < 250:
            continue
        vo = np.array([do[d] for d in common], dtype="float64")
        vc = np.array([dc[d] for d in common], dtype="float64")
        ok = np.isfinite(vo) & np.isfinite(vc) & (vo > 0) & (vc > 0)
        if ok.sum() < 250:
            continue
        ro = np.diff(vo[ok]) / vo[ok][:-1]
        rc = np.diff(vc[ok]) / vc[ok][:-1]
        dev = np.abs(ro - rc)
        all_dev.append(dev)
        per_code.append({
            "code": qcode, "days": int(ok.sum()),
            "corr": float(np.corrcoef(ro, rc)[0, 1]) if ro.std() and rc.std() else None,
            "max_abs_dev": float(dev.max()),
            "frac_within_1e4": float((dev < 1e-4).mean()),
        })
    dev = np.concatenate(all_dev) if all_dev else np.array([0.0])
    corrs = np.array([p["corr"] for p in per_code if p["corr"] is not None])
    return {
        "sample_codes": len(per_code), "return_pairs": int(dev.size),
        "corr_min": float(corrs.min()), "corr_p01": float(np.percentile(corrs, 1)),
        "corr_median": float(np.median(corrs)), "corr_mean": float(corrs.mean()),
        "frac_return_pairs_within_1e4": float((dev < 1e-4).mean()),
        "frac_return_pairs_within_1e3": float((dev < 1e-3).mean()),
        "dev_p50": float(np.percentile(dev, 50)), "dev_p99": float(np.percentile(dev, 99)),
        "dev_max": float(dev.max()),
        "worst_codes": sorted(per_code, key=lambda p: -p["max_abs_dev"])[:8],
        "note": ("只作诊断不作判据：两源同宗（都出自 tushare），一致不构成互证；"
                 "比的是**收益率**不是价格水平 —— 归一化常数不同，水平必然差一个比例，"
                 "收益率才是归一化不变量。"),
    }


def main() -> int:
    print("[1/2] 全量验收 …")
    st = full_verify()
    print(json.dumps({k: v for k, v in st.items() if k != "vwap_out_of_band"},
                     ensure_ascii=False, indent=1))
    print(f"  vwap 越带样例（前 {len(st['vwap_out_of_band'])} 条）:")
    for r in st["vwap_out_of_band"][:8]:
        print("   ", r)
    print("[2/2] 社区 release 收益率级诊断 …")
    diag = community_diag()
    print(json.dumps({k: v for k, v in diag.items() if k != "worst_codes"},
                     ensure_ascii=False, indent=1))
    for w in diag["worst_codes"]:
        print("   ", w)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"full_verify": st, "community_diag": diag},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"→ {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
