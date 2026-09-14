"""对抗审查 源A 探针 1：类型 / 无损还原 / 截断 / 多段 / 每期成分数。

只读。不写任何产物（除了 stdout 的 JSON）。
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

os.umask(0o077)

sys.path.insert(0, "/data/shared/genebench/repo")
import pandas as pd  # noqa: E402
import genebench_config as cfg  # noqa: E402
from snapshots import lake  # noqa: E402

OUT = {}

lake.raise_open_file_limit()

with lake.catalog() as con:
    # ---------- 1. 类型探测 ----------
    types = {}
    for view, cols in [
        ("index_weight", None),
        ("trade_cal", None),
        ("daily", None),
        ("suspend_d", None),
    ]:
        try:
            d = lake.describe_view(view, conn=con)
            types[view] = {r["column_name"]: r["column_type"] for _, r in d.iterrows()}
        except Exception as e:  # noqa: BLE001
            types[view] = {"ERROR": str(e)}
    OUT["view_types"] = types

    tf = lake.query(
        "SELECT typeof(index_code) t_index, typeof(con_code) t_con, "
        "typeof(trade_date) t_td, typeof(weight) t_w FROM index_weight LIMIT 1",
        conn=con,
    )
    OUT["typeof_index_weight"] = tf.to_dict("records")
    tc = lake.query(
        "SELECT typeof(cal_date) t_cal, typeof(is_open) t_open FROM trade_cal LIMIT 1",
        conn=con,
    )
    OUT["typeof_trade_cal"] = tc.to_dict("records")

    # ---------- 2. 原始快照（含 weight）----------
    raw = lake.query(
        "SELECT index_code, con_code, trade_date, weight FROM index_weight "
        "WHERE trade_date <= ? ORDER BY index_code, trade_date, con_code",
        [lake.FREEZE_DATE_COMPACT],
        conn=con,
    )
    raw_all = lake.query(
        "SELECT count(*) n, min(trade_date) mn, max(trade_date) mx, "
        "count(DISTINCT index_code) nidx FROM index_weight",
        conn=con,
    )
    OUT["raw_no_freeze_filter"] = raw_all.to_dict("records")

    # 冻结线过滤是否真的生效（字符串比较 vs 日期比较）
    OUT["raw_rows_after_freeze"] = int(
        lake.query(
            "SELECT count(*) n FROM index_weight WHERE trade_date > ?",
            [lake.FREEZE_DATE_COMPACT],
            conn=con,
        )["n"].iloc[0]
    )

    # weight 字段体检
    w = raw["weight"]
    OUT["weight_stats"] = {
        "n_null": int(w.isna().sum()),
        "n_zero": int((w == 0).sum()),
        "n_negative": int((w < 0).sum()),
        "min": float(w.min()),
        "max": float(w.max()),
    }

    # ---------- 3. 交易日历 ----------
    cal = lake.query(
        "SELECT cal_date FROM trade_cal WHERE is_open = 1 AND cal_date <= ? "
        "ORDER BY cal_date",
        [lake.FREEZE_DATE_COMPACT],
        conn=con,
    )["cal_date"].tolist()
    cal = [str(x) for x in cal]

OUT["cal_head_tail"] = {"n": len(cal), "first": cal[0], "last": cal[-1]}

prev_of = {cur: prv for prv, cur in zip(cal, cal[1:])}
cal_set = set(cal)

# ---------- 4. 独立重建成员集合 ----------
members = defaultdict(lambda: defaultdict(set))  # uni -> date -> set(code)
weights = defaultdict(lambda: defaultdict(dict))
for idx, code, td, wt in zip(
    raw["index_code"], raw["con_code"], raw["trade_date"], raw["weight"]
):
    uni = cfg.INDEX_CODE_UNIVERSE.get(str(idx))
    if uni is None:
        continue
    members[uni][str(td)].add(str(code))
    weights[uni][str(td)][str(code)] = wt

dates_by_uni = {u: sorted(members[u]) for u in cfg.UNIVERSES}

# ---------- 5. 每期成分数（含 weight 求和）----------
per_period = {}
for uni in cfg.UNIVERSES:
    nom = cfg.UNIVERSE_NOMINAL_SIZE[uni]
    bad = []
    for d in dates_by_uni[uni]:
        n = len(members[uni][d])
        if n != nom:
            bad.append(
                {
                    "date": d,
                    "n": n,
                    "nominal": nom,
                    "sum_weight": round(float(sum(weights[uni][d].values())), 4),
                }
            )
    # 全期 weight 和的分布，用来判断"缺行"还是"数据本来就这样"
    sums = {d: float(sum(weights[uni][d].values())) for d in dates_by_uni[uni]}
    srt = sorted(sums.items(), key=lambda kv: kv[1])
    per_period[uni] = {
        "n_periods": len(dates_by_uni[uni]),
        "off_size": bad,
        "weight_sum_min5": [{"date": k, "sum": round(v, 4)} for k, v in srt[:5]],
        "weight_sum_max5": [{"date": k, "sum": round(v, 4)} for k, v in srt[-5:]],
        "first": dates_by_uni[uni][0],
        "last": dates_by_uni[uni][-1],
        # 快照日是否都是月末最后一个交易日
        "snapshot_not_trading_day": [d for d in dates_by_uni[uni] if d not in cal_set],
    }
    # 月序列是否连续（有没有整月缺失）
    ym = [d[:6] for d in dates_by_uni[uni]]
    OUT.setdefault("month_seq", {})[uni] = {
        "n_distinct_months": len(set(ym)),
        "n_periods": len(ym),
        "gaps": [],
    }
    # 检查月末最后交易日：该快照日是否 == 该月最后一个交易日
    lastcal_of_month = {}
    for c in cal:
        lastcal_of_month[c[:6]] = c
    notlast = [
        {"snapshot": d, "month_last_trading_day": lastcal_of_month.get(d[:6])}
        for d in dates_by_uni[uni]
        if lastcal_of_month.get(d[:6]) != d
    ]
    per_period[uni]["snapshot_not_month_last_trading_day"] = notlast
OUT["per_period"] = per_period

# ---------- 6. 读产物 parquet ----------
pq = pd.read_parquet(cfg.UNIVERSE_INTERVALS_PARQUET)
OUT["parquet"] = {
    "path": str(cfg.UNIVERSE_INTERVALS_PARQUET),
    "rows": int(len(pq)),
    "dtypes": {c: str(t) for c, t in pq.dtypes.items()},
    "n_out_date_null": int(pq["out_date"].isna().sum()),
    "n_prev_null": int(pq["prev_snapshot"].isna().sum()),
    "n_next_null": int(pq["next_snapshot"].isna().sum()),
}

# ---------- 7. 无损还原：区间 → 逐期成员集合 ----------
roundtrip = {}
for uni in cfg.UNIVERSES:
    sel = pq[pq["universe"] == uni]
    segs = list(
        zip(sel["code"], sel["in_date"], sel["out_date"])
    )
    per_date_bad = []
    tot_missing = tot_extra = 0
    for d in dates_by_uni[uni]:
        rec = {
            c
            for c, i, o in segs
            if i <= d and (o is None or (isinstance(o, float)) or pd.isna(o) or d <= o)
        }
        truth = members[uni][d]
        miss = truth - rec
        extra = rec - truth
        if miss or extra:
            tot_missing += len(miss)
            tot_extra += len(extra)
            per_date_bad.append(
                {
                    "date": d,
                    "n_missing": len(miss),
                    "n_extra": len(extra),
                    "missing_sample": sorted(miss)[:5],
                    "extra_sample": sorted(extra)[:5],
                }
            )
    roundtrip[uni] = {
        "n_periods": len(dates_by_uni[uni]),
        "n_periods_mismatch": len(per_date_bad),
        "total_missing": tot_missing,
        "total_extra": tot_extra,
        "detail": per_date_bad[:20],
    }
OUT["roundtrip_snapshot_dates"] = roundtrip

# ---------- 8. LOCF 等价性 + 每交易日宇宙规模 ----------
locf = {}
for uni in cfg.UNIVERSES:
    sel = pq[pq["universe"] == uni]
    segs = [
        (c, i, (None if pd.isna(o) else o))
        for c, i, o in zip(sel["code"], sel["in_date"], sel["out_date"])
    ]
    dts = dates_by_uni[uni]
    nom = cfg.UNIVERSE_NOMINAL_SIZE[uni]
    days = [d for d in cal if d >= dts[0]]
    # LOCF 参照
    import bisect

    size_hist = defaultdict(int)
    diff_days = []
    off_size_days = 0
    off_size_runs = []
    for d in days:
        k = bisect.bisect_right(dts, d) - 1
        ref = members[uni][dts[k]]
        rec = {c for c, i, o in segs if i <= d and (o is None or d <= o)}
        if rec != ref:
            diff_days.append(
                {
                    "day": d,
                    "n_missing": len(ref - rec),
                    "n_extra": len(rec - ref),
                }
            )
        size_hist[len(rec)] += 1
        if len(rec) != nom:
            off_size_days += 1
            off_size_runs.append(d)
    locf[uni] = {
        "n_trading_days_checked": len(days),
        "n_days_differ_from_locf": len(diff_days),
        "diff_sample": diff_days[:10],
        "size_histogram": dict(sorted(size_hist.items())),
        "n_days_off_nominal": off_size_days,
        "off_nominal_first": off_size_runs[0] if off_size_runs else None,
        "off_nominal_last": off_size_runs[-1] if off_size_runs else None,
    }
OUT["locf_equivalence"] = locf

print(json.dumps(OUT, ensure_ascii=False, indent=1, default=str))
