"""对抗审查 源A 探针 2：多段/截断/字段自洽 + 停牌退市 + 第三方源 dc_index_member。"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

os.umask(0o077)
sys.path.insert(0, "/data/shared/genebench/repo")
import pandas as pd  # noqa: E402
import genebench_config as cfg  # noqa: E402
from snapshots import lake  # noqa: E402

OUT = {}
lake.raise_open_file_limit()

with lake.catalog() as con:
    raw = lake.query(
        "SELECT index_code, con_code, trade_date FROM index_weight "
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

    # dc_index_member: 第三方成分区间源（若存在）
    try:
        cols = lake.query("SELECT * FROM dc_index_member LIMIT 3", conn=con)
        OUT["dc_index_member_cols"] = list(cols.columns)
        OUT["dc_index_member_sample"] = cols.astype(str).to_dict("records")
        OUT["dc_index_member_count"] = int(
            lake.query("SELECT count(*) n FROM dc_index_member", conn=con)["n"].iloc[0]
        )
    except Exception as e:  # noqa: BLE001
        OUT["dc_index_member_cols"] = f"ERROR: {e}"

    # 600001 / 600357 的下市证据
    try:
        sb = lake.query(
            "SELECT ts_code, name, list_status, list_date, delist_date, snapshot_date "
            "FROM stock_basic WHERE ts_code IN ('600001.SH','600357.SH') "
            "ORDER BY ts_code, snapshot_date",
            conn=con,
        )
        OUT["stock_basic_600001_600357"] = sb.astype(str).drop_duplicates(
            ["ts_code", "list_status", "delist_date"]
        ).to_dict("records")
    except Exception as e:  # noqa: BLE001
        OUT["stock_basic_600001_600357"] = f"ERROR: {e}"

    for c in ("600001.SH", "600357.SH"):
        try:
            d = lake.query(
                "SELECT min(trade_date) mn, max(trade_date) mx, count(*) n "
                "FROM daily WHERE ts_code = ?",
                [c],
                conn=con,
            )
            OUT.setdefault("daily_span", {})[c] = d.astype(str).to_dict("records")
        except Exception as e:  # noqa: BLE001
            OUT.setdefault("daily_span", {})[c] = f"ERROR: {e}"

    # ---------- 停牌 / 无行情：成分股在快照日是否有 daily 行 ----------
    # 只查 csi300 的全部快照日（211 天），逐日 join 太重，改成一次性拉这些日的 daily ts_code
    snap_dates = sorted(
        set(raw.loc[raw["index_code"] == "000300.SH", "trade_date"].astype(str))
    )
    ph = ",".join("?" * len(snap_dates))
    dl = lake.query(
        f"SELECT trade_date, ts_code FROM daily WHERE trade_date IN ({ph})",  # noqa: S608
        snap_dates,
        conn=con,
    )
    traded = defaultdict(set)
    for td, ts in zip(dl["trade_date"], dl["ts_code"]):
        traded[str(td)].add(str(ts))

    # suspend_d 在这些快照日的记录
    sd = lake.query(
        f"SELECT trade_date, ts_code, suspend_type FROM suspend_d "  # noqa: S608
        f"WHERE trade_date IN ({ph})",
        snap_dates,
        conn=con,
    )
    susp = defaultdict(dict)
    for td, ts, st in zip(sd["trade_date"], sd["ts_code"], sd["suspend_type"]):
        susp[str(td)][str(ts)] = str(st)

members = defaultdict(lambda: defaultdict(set))
for idx, code, td in zip(raw["index_code"], raw["con_code"], raw["trade_date"]):
    uni = cfg.INDEX_CODE_UNIVERSE.get(str(idx))
    if uni:
        members[uni][str(td)].add(str(code))
dates_by_uni = {u: sorted(members[u]) for u in cfg.UNIVERSES}

# ---------- 停牌票是否被误判为退出 ----------
no_quote_total = 0
no_quote_and_dropped = []
no_quote_and_stayed = 0
examples = []
d300 = dates_by_uni["csi300"]
for k, d in enumerate(d300):
    mem = members["csi300"][d]
    nq = sorted(mem - traded.get(d, set()))
    no_quote_total += len(nq)
    if k + 1 < len(d300):
        nxt = members["csi300"][d300[k + 1]]
        for c in nq:
            if c not in nxt:
                no_quote_and_dropped.append(
                    {"date": d, "code": c, "suspend_type": susp.get(d, {}).get(c)}
                )
            else:
                no_quote_and_stayed += 1
    if nq and len(examples) < 12:
        examples.append(
            {
                "date": d,
                "n_no_quote": len(nq),
                "codes": nq[:6],
                "suspend_flags": {c: susp.get(d, {}).get(c) for c in nq[:6]},
            }
        )
OUT["suspended_members_csi300"] = {
    "n_member_days_without_daily_row": no_quote_total,
    "n_stayed_next_period": no_quote_and_stayed,
    "n_dropped_next_period": len(no_quote_and_dropped),
    "dropped_detail": no_quote_and_dropped[:20],
    "examples": examples,
}

# ---------- 独立重建段结构，与 parquet 逐行比对 ----------
prev_of = {cur: prv for prv, cur in zip(cal, cal[1:])}
ref_rows = []
for uni in cfg.UNIVERSES:
    dts = dates_by_uni[uni]
    pos = {d: i for i, d in enumerate(dts)}
    last = len(dts) - 1
    bycode = defaultdict(list)
    for d in dts:
        for c in members[uni][d]:
            bycode[c].append(pos[d])
    for c in sorted(bycode):
        idxs = sorted(bycode[c])
        runs = []
        s = p = idxs[0]
        for i in idxs[1:]:
            if i == p + 1:
                p = i
            else:
                runs.append((s, p))
                s = p = i
        runs.append((s, p))
        for si, (i, j) in enumerate(runs):
            ref_rows.append(
                {
                    "code": c,
                    "universe": uni,
                    "segment_idx": si,
                    "in_date": dts[i],
                    "out_date": None if j == last else prev_of[dts[j + 1]],
                    "last_seen_snapshot": dts[j],
                    "prev_snapshot": None if i == 0 else dts[i - 1],
                    "next_snapshot": None if j == last else dts[j + 1],
                    "n_snapshots": j - i + 1,
                    "left_censored": i == 0,
                    "right_censored": j == last,
                }
            )
ref = pd.DataFrame(ref_rows)

pq = pd.read_parquet(cfg.UNIVERSE_INTERVALS_PARQUET)
cols = [
    "code",
    "universe",
    "segment_idx",
    "in_date",
    "out_date",
    "last_seen_snapshot",
    "prev_snapshot",
    "next_snapshot",
    "n_snapshots",
    "left_censored",
    "right_censored",
]
a = pq[cols].copy()
for cc in ("in_date", "out_date", "last_seen_snapshot", "prev_snapshot", "next_snapshot"):
    a[cc] = a[cc].astype(object).where(a[cc].notna(), None)
    ref[cc] = ref[cc].astype(object)
a["n_snapshots"] = a["n_snapshots"].astype(int)
a["segment_idx"] = a["segment_idx"].astype(int)
a = a.sort_values(["universe", "code", "segment_idx"]).reset_index(drop=True)
r = ref[cols].sort_values(["universe", "code", "segment_idx"]).reset_index(drop=True)
OUT["independent_rebuild"] = {
    "n_rows_parquet": int(len(a)),
    "n_rows_ref": int(len(r)),
    "identical": bool(a.equals(r)),
}
if not a.equals(r) and len(a) == len(r):
    diff = {}
    for cc in cols:
        m = a[cc].astype(str) != r[cc].astype(str)
        if m.any():
            diff[cc] = {
                "n_diff": int(m.sum()),
                "sample": pd.concat(
                    [a.loc[m, ["universe", "code", "segment_idx", cc]].head(5),
                     r.loc[m, [cc]].head(5).rename(columns={cc: cc + "_ref"})],
                    axis=1,
                ).astype(str).to_dict("records"),
            }
    OUT["independent_rebuild"]["column_diffs"] = diff

# ---------- 段的单调性 / 不重叠 / 缺口真实性 ----------
viol = {"overlap": [], "non_monotonic": [], "adjacent_no_real_gap": [], "outdate_le_indate": []}
for (uni, code), g in pq.groupby(["universe", "code"]):
    g = g.sort_values("segment_idx")
    prev_out = None
    prev_next = None
    for _, rw in g.iterrows():
        ind, outd = rw["in_date"], rw["out_date"]
        if pd.notna(outd) and outd < ind:
            viol["outdate_le_indate"].append({"u": uni, "c": code, "in": ind, "out": outd})
        if prev_out is not None:
            if pd.isna(prev_out) or prev_out >= ind:
                viol["overlap"].append(
                    {"u": uni, "c": code, "prev_out": str(prev_out), "in": ind}
                )
            # 相邻两段之间必须真的隔了至少一期（prev_next < in_date）
            if prev_next is not None and not (prev_next < ind):
                viol["adjacent_no_real_gap"].append(
                    {"u": uni, "c": code, "prev_next": str(prev_next), "in": ind}
                )
        prev_out = outd
        prev_next = rw["next_snapshot"]
OUT["segment_violations"] = {k: {"n": len(v), "sample": v[:5]} for k, v in viol.items()}

# ---------- 截断标记自洽 ----------
firsts = {u: dates_by_uni[u][0] for u in cfg.UNIVERSES}
lasts = {u: dates_by_uni[u][-1] for u in cfg.UNIVERSES}
cen = {}
for uni in cfg.UNIVERSES:
    s = pq[pq["universe"] == uni]
    cen[uni] = {
        "n_left_censored": int(s["left_censored"].sum()),
        "left_flag_iff_in_is_first": int(
            (s["left_censored"] != (s["in_date"] == firsts[uni])).sum()
        ),
        "left_censored_but_segidx_ne_0": int(
            (s["left_censored"] & (s["segment_idx"] != 0)).sum()
        ),
        "n_right_censored": int(s["right_censored"].sum()),
        "right_flag_iff_outdate_null": int(
            (s["right_censored"] != s["out_date"].isna()).sum()
        ),
        "right_flag_iff_lastseen_is_last": int(
            (s["right_censored"] != (s["last_seen_snapshot"] == lasts[uni])).sum()
        ),
        "n_members_at_first_snapshot": len(members[uni][firsts[uni]]),
        "n_members_at_last_snapshot": len(members[uni][lasts[uni]]),
    }
OUT["censoring"] = cen

# ---------- 真实多次进出的票（从原始数据挖）----------
multi = {}
for uni in cfg.UNIVERSES:
    dts = dates_by_uni[uni]
    pos = {d: i for i, d in enumerate(dts)}
    bycode = defaultdict(list)
    for d in dts:
        for c in members[uni][d]:
            bycode[c].append(pos[d])
    cnt = {}
    for c, idxs in bycode.items():
        idxs = sorted(idxs)
        runs = 1
        for x, y in zip(idxs, idxs[1:]):
            if y != x + 1:
                runs += 1
        cnt[c] = runs
    top = sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))[:6]
    detail = []
    for c, n in top:
        s = pq[(pq["universe"] == uni) & (pq["code"] == c)].sort_values("segment_idx")
        detail.append(
            {
                "code": c,
                "raw_n_runs": n,
                "parquet_n_segments": int(len(s)),
                "raw_periods": [dts[i] for i in sorted(bycode[c])][:40],
                "parquet_segments": s[
                    ["segment_idx", "in_date", "out_date", "last_seen_snapshot", "n_snapshots"]
                ].astype(str).to_dict("records"),
            }
        )
    # 段数分布 raw vs parquet 全量比对
    pqcnt = pq[pq["universe"] == uni].groupby("code").size().to_dict()
    mismatch = {c: (cnt[c], pqcnt.get(c)) for c in cnt if pqcnt.get(c) != cnt[c]}
    multi[uni] = {
        "n_codes": len(cnt),
        "n_codes_multi": sum(1 for v in cnt.values() if v > 1),
        "max_runs": max(cnt.values()),
        "segment_count_mismatches": len(mismatch),
        "mismatch_sample": dict(list(mismatch.items())[:5]),
        "top_examples": detail,
    }
OUT["multi_segment"] = multi

print(json.dumps(OUT, ensure_ascii=False, indent=1, default=str))
