"""对抗审查 源A 探针 4：边界外行为 / 视图 vs 裸 gold / 复现性 / 缺口停牌率 / qlib 月内滞后（修正版）。"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import sys
from collections import defaultdict

os.umask(0o077)
sys.path.insert(0, "/data/shared/genebench/repo")
import duckdb  # noqa: E402
import pandas as pd  # noqa: E402
import pyarrow.parquet as pqmod  # noqa: E402
import genebench_config as cfg  # noqa: E402
from snapshots import lake  # noqa: E402

OUT = {}
lake.raise_open_file_limit()

# ---------- 0. parquet 元数据 / 边界外行为 ----------
pf = pqmod.ParquetFile(cfg.UNIVERSE_INTERVALS_PARQUET)
md = pf.schema_arrow.metadata or {}
OUT["parquet_kv_metadata"] = {
    k.decode(): (v.decode()[:200] if len(v) < 5000 else "<big>") for k, v in md.items()
}
pq = pd.read_parquet(cfg.UNIVERSE_INTERVALS_PARQUET)

def active(uni: str, d: str) -> int:
    s = pq[(pq["universe"] == uni)]
    return int(
        (
            (s["in_date"] <= d) & (s["out_date"].isna() | (s["out_date"] >= d))
        ).sum()
    )

OUT["out_of_range_query"] = {
    "csi300_20090105_before_first_snapshot": active("csi300", "20090105"),
    "csi300_20090122_before_first_snapshot": active("csi300", "20090122"),
    "csi300_20260731_freeze": active("csi300", "20260731"),
    "csi300_20270101_after_freeze": active("csi300", "20270101"),
    "csi300_29991231_far_future": active("csi300", "29991231"),
    "csi1000_20140101_before_first": active("csi1000", "20140101"),
    "note": "冻结线之后仍返回满额宇宙 → 下游忘记裁剪不会报错，只会静默拿到 20260731 的名单",
}

with lake.catalog() as con:
    raw = lake.query(
        "SELECT index_code, con_code, trade_date, weight FROM index_weight "
        "WHERE trade_date <= ? ORDER BY index_code, trade_date, con_code",
        [lake.FREEZE_DATE_COMPACT],
        conn=con,
    )
    cal = [
        str(x)
        for x in lake.query(
            "SELECT cal_date FROM trade_cal WHERE is_open = 1 AND cal_date <= ? "
            "ORDER BY cal_date",
            [lake.FREEZE_DATE_COMPACT],
            conn=con,
        )["cal_date"].tolist()
    ]

# ---------- 1. 视图 vs 裸 gold parquet 对账（绕开 catalog）----------
gold = str(cfg.GOLD / "index_weight")
c2 = duckdb.connect(":memory:")
c2.execute("SET threads=4")
g = c2.execute(
    f"SELECT count(*) n, count(DISTINCT trade_date) nd, "  # noqa: S608
    f"count(DISTINCT index_code) ni, min(trade_date) mn, max(trade_date) mx, "
    f"typeof(any_value(trade_date)) t "
    f"FROM read_parquet('{gold}/*/*.parquet')"
).df()
OUT["gold_raw_vs_view"] = {
    "gold": g.astype(str).to_dict("records"),
    "view_rows": int(len(raw)),
    "match": int(g["n"].iloc[0]) == int(len(raw)),
}
gcnt = c2.execute(
    f"SELECT index_code, trade_date, count(*) n, count(DISTINCT con_code) nd "  # noqa: S608
    f"FROM read_parquet('{gold}/*/*.parquet') GROUP BY 1,2"
).df()
OUT["gold_dupes"] = int((gcnt["n"] != gcnt["nd"]).sum())
c2.close()

# ---------- 2. weight 的反事实：若误用阈值会怎样 ----------
w = raw["weight"]
OUT["weight_counterfactual"] = {
    "min": float(w.min()),
    "n_rows_lt_0.01": int((w < 0.01).sum()),
    "n_rows_lt_0.02": int((w < 0.02).sum()),
    "n_rows_lt_0.05": int((w < 0.05).sum()),
    "pct_lt_0.05": round(100.0 * float((w < 0.05).sum()) / len(w), 4),
    "note": "源A 的 SQL 只 SELECT index_code/con_code/trade_date，weight 从未进入判定；"
            "此处只量化'如果误加阈值'的破坏面",
}

# ---------- 3. 成员缺口的停牌覆盖率（精确到交易日）----------
members = defaultdict(lambda: defaultdict(set))
for idx, code, td in zip(raw["index_code"], raw["con_code"], raw["trade_date"]):
    uni = cfg.INDEX_CODE_UNIVERSE.get(str(idx))
    if uni:
        members[uni][str(td)].add(str(code))
dates_by_uni = {u: sorted(members[u]) for u in cfg.UNIVERSES}

gaps = []
for uni in cfg.UNIVERSES:
    dts = dates_by_uni[uni]
    pos = {d: i for i, d in enumerate(dts)}
    bycode = defaultdict(list)
    for d in dts:
        for c in members[uni][d]:
            bycode[c].append(pos[d])
    for c, idxs in bycode.items():
        idxs = sorted(idxs)
        for x, y in zip(idxs, idxs[1:]):
            if y != x + 1:
                gaps.append((uni, c, dts[x], dts[y], y - x - 1))

gap_codes = sorted({g[1] for g in gaps})
with lake.catalog() as con:
    ph = ",".join("?" * len(gap_codes))
    dd = lake.query(
        f"SELECT ts_code, trade_date FROM daily "  # noqa: S608
        f"WHERE ts_code IN ({ph}) AND trade_date <= ?",
        gap_codes + [lake.FREEZE_DATE_COMPACT],
        conn=con,
    )
traded = defaultdict(set)
for t, d in zip(dd["ts_code"], dd["trade_date"]):
    traded[str(t)].add(str(d))

cal_sorted = cal
import bisect  # noqa: E402

ratios = []
worst = []
for uni, c, gs, ge, nmiss in gaps:
    i = bisect.bisect_right(cal_sorted, gs)
    j = bisect.bisect_left(cal_sorted, ge)
    days = cal_sorted[i:j]  # (gs, ge) 开区间内的交易日
    if not days:
        continue
    have = len(traded.get(c, set()) & set(days))
    r = have / len(days)
    ratios.append(r)
    if r < 0.5:
        worst.append(
            {"universe": uni, "code": c, "gap_from": gs, "gap_to": ge,
             "missing_periods": nmiss, "trading_days_in_gap": len(days),
             "days_with_quote": have, "ratio": round(r, 3)}
        )
ratios.sort()
OUT["gap_trading_coverage"] = {
    "n_gaps": len(ratios),
    "min_ratio": round(ratios[0], 3) if ratios else None,
    "p05": round(ratios[max(0, int(len(ratios) * 0.05))], 3) if ratios else None,
    "p50": round(ratios[len(ratios) // 2], 3) if ratios else None,
    "n_gaps_ratio_below_0.5": len(worst),
    "n_gaps_ratio_zero": sum(1 for r in ratios if r == 0.0),
    "worst": sorted(worst, key=lambda r: r["ratio"])[:15],
    "note": "ratio = 缺口内该票有行情的交易日占比；接近 0 说明'退出'其实是长停牌",
}

# ---------- 4. entry/exit_gap_suspect 的精度 ----------
sus = pq[(pq["entry_gap_suspect"]) | (pq["exit_gap_suspect"])]
OUT["gap_suspect_flags"] = {
    "n_entry": int(pq["entry_gap_suspect"].sum()),
    "n_exit": int(pq["exit_gap_suspect"].sum()),
    "rows": sus[["universe", "code", "segment_idx", "in_date", "out_date",
                 "prev_snapshot", "next_snapshot", "entry_gap_suspect",
                 "exit_gap_suspect"]].astype(str).to_dict("records"),
}

# ---------- 5. qlib 月内调整滞后（只看落在 A 窗口内的起点）----------
root = cfg.QLIB_RELEASE / "instruments"
qa = {}
for uni in cfg.UNIVERSES:
    p = root / f"{uni}.txt"
    if not p.is_file():
        continue
    per = defaultdict(list)
    for ln in p.read_text().splitlines():
        if not ln.strip():
            continue
        c, s, e = ln.split("\t")[:3]
        per[f"{c[2:]}.{c[:2]}"].append((s, e))
    merged = defaultdict(list)
    for c, segs in per.items():
        segs.sort()
        cs, ce = segs[0]
        for s, e in segs[1:]:
            if dt.date.fromisoformat(s) == dt.date.fromisoformat(ce) + dt.timedelta(days=1):
                ce = max(ce, e)
            else:
                merged[c].append((cs, ce))
                cs, ce = s, e
        merged[c].append((cs, ce))

    snaps = dates_by_uni[uni]
    snapset = set(snaps)
    first = snaps[0]
    n_start_in_window = 0
    n_start_off_snap = 0
    lags = []
    n_end_in_window = 0
    n_end_off_snap = 0
    for c, segs in merged.items():
        for s, e in segs:
            cs = s.replace("-", "")
            ce = e.replace("-", "")
            if cs > first and cs <= lake.FREEZE_DATE_COMPACT:
                n_start_in_window += 1
                if cs not in snapset:
                    n_start_off_snap += 1
                    nxt = [d for d in snaps if d >= cs]
                    if nxt:
                        lags.append(
                            (dt.date.fromisoformat(f"{nxt[0][:4]}-{nxt[0][4:6]}-{nxt[0][6:]}")
                             - dt.date.fromisoformat(s)).days
                        )
            if first <= ce <= lake.FREEZE_DATE_COMPACT:
                n_end_in_window += 1
                if ce not in snapset:
                    n_end_off_snap += 1
    lags.sort()
    qa[uni] = {
        "n_qlib_starts_inside_A_window": n_start_in_window,
        "n_starts_not_on_month_end_snapshot": n_start_off_snap,
        "pct_starts_off_snapshot": round(100.0 * n_start_off_snap / max(n_start_in_window, 1), 1),
        "n_qlib_ends_inside_A_window": n_end_in_window,
        "n_ends_not_on_month_end_snapshot": n_end_off_snap,
        "pct_ends_off_snapshot": round(100.0 * n_end_off_snap / max(n_end_in_window, 1), 1),
        "entry_lag_days_to_next_snapshot": {
            "n": len(lags),
            "min": lags[0] if lags else None,
            "p50": lags[len(lags) // 2] if lags else None,
            "p90": lags[int(len(lags) * 0.9)] if lags else None,
            "max": lags[-1] if lags else None,
            "mean": round(sum(lags) / len(lags), 1) if lags else None,
        },
    }
OUT["qlib_intra_month_lag"] = qa

# ---------- 6. 复现性：重跑 build() 与磁盘产物比对 ----------
from snapshots import universe_index_weight as uiw  # noqa: E402

iv, summ = uiw.build()
disk = pd.read_parquet(cfg.UNIVERSE_INTERVALS_PARQUET)
same = iv.reset_index(drop=True).astype(str).equals(disk.reset_index(drop=True).astype(str))
OUT["reproducibility"] = {
    "rebuild_rows": int(len(iv)),
    "disk_rows": int(len(disk)),
    "values_identical": bool(same),
    "disk_sha256": hashlib.sha256(
        open(cfg.UNIVERSE_INTERVALS_PARQUET, "rb").read()
    ).hexdigest(),
    "summary_json_totals": summ["totals"],
}

print(json.dumps(OUT, ensure_ascii=False, indent=1, default=str))
