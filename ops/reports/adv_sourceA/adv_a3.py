"""对抗审查 源A 探针 3：停牌缺口 / 退市 / dc_index_member / qlib 月内调整量级。"""
from __future__ import annotations

import datetime as dt
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

    # dc_index_member 全貌
    dc = lake.query("SELECT * FROM dc_index_member", conn=con)
    OUT["dc_index_member"] = {
        "n_rows": int(len(dc)),
        "by_ts_code": dc.groupby("ts_code").size().to_dict(),
        "trade_dates": sorted(set(dc["trade_date"].astype(str)))[:10],
        "n_trade_dates": int(dc["trade_date"].nunique()),
        "sources": sorted(set(dc["source"].astype(str))),
    }

    sb = lake.query(
        "SELECT ts_code, name, list_status, list_date, delist_date FROM stock_basic "
        "WHERE ts_code IN ('600001.SH','600357.SH')",
        conn=con,
    )
    OUT["stock_basic_two"] = sb.astype(str).drop_duplicates().to_dict("records")

    # 每只票的行情起止（用于判断"缺口=停牌"还是"缺口=退市"）
    span = lake.query(
        "SELECT ts_code, min(trade_date) mn, max(trade_date) mx, count(*) n "
        "FROM daily WHERE trade_date <= ? GROUP BY ts_code",
        [lake.FREEZE_DATE_COMPACT],
        conn=con,
    )
    span_map = {
        str(t): (str(a), str(b), int(c))
        for t, a, b, c in zip(span["ts_code"], span["mn"], span["mx"], span["n"])
    }

    # 全量 daily 的 (ts_code, trade_date) 太大；改成按需查缺口内是否有成交
    # 先建区间，再对每个缺口发一条 count 查询（缺口数量有限）
    members = defaultdict(lambda: defaultdict(set))
    for idx, code, td in zip(raw["index_code"], raw["con_code"], raw["trade_date"]):
        uni = cfg.INDEX_CODE_UNIVERSE.get(str(idx))
        if uni:
            members[uni][str(td)].add(str(code))
    dates_by_uni = {u: sorted(members[u]) for u in cfg.UNIVERSES}

    gaps = []  # (uni, code, gap_start_snapshot, gap_end_snapshot)
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
                    gaps.append((uni, c, dts[x], dts[y]))
    OUT["n_gaps_total"] = len(gaps)

    # 对每个缺口：缺口期间（(gap_start, gap_end) 开区间的交易日）有没有行情
    # 一次查一票的全部缺口成本太高，改成一次查所有涉及票在最大跨度内的日数
    gap_codes = sorted({g[1] for g in gaps})
    ph = ",".join("?" * len(gap_codes))
    OUT["n_gap_codes"] = len(gap_codes)

    # 用一条聚合查询拿到每票每个自然月的成交天数，再据此判断缺口是否"整段无行情"
    mon = lake.query(
        f"SELECT ts_code, substr(trade_date,1,6) ym, count(*) n FROM daily "  # noqa: S608
        f"WHERE ts_code IN ({ph}) AND trade_date <= ? GROUP BY 1,2",
        gap_codes + [lake.FREEZE_DATE_COMPACT],
        conn=con,
    )
    mcount = defaultdict(dict)
    for t, y, n in zip(mon["ts_code"], mon["ym"], mon["n"]):
        mcount[str(t)][str(y)] = int(n)

def months_between(a: str, b: str) -> list[str]:
    """(a, b) 开区间之间的自然月 YYYYMM 列表（不含 a 月与 b 月）。"""
    ya, ma = int(a[:4]), int(a[4:6])
    yb, mb = int(b[:4]), int(b[4:6])
    out = []
    y, m = ya, ma
    while True:
        m += 1
        if m == 13:
            m, y = 1, y + 1
        if (y, m) >= (yb, mb):
            break
        out.append(f"{y:04d}{m:02d}")
    return out


gap_kinds = {"delisted_forever": 0, "no_trade_whole_gap": 0, "traded_in_gap": 0,
             "adjacent_month_gap": 0}
gap_examples = defaultdict(list)
for uni, c, gs, ge in gaps:
    ms = months_between(gs, ge)
    if not ms:
        gap_kinds["adjacent_month_gap"] += 1
        continue
    tot = sum(mcount.get(c, {}).get(m, 0) for m in ms)
    if tot == 0:
        mx = span_map.get(c, ("", "", 0))[1]
        if mx and mx < gs:
            gap_kinds["delisted_forever"] += 1
        else:
            gap_kinds["no_trade_whole_gap"] += 1
            if len(gap_examples["no_trade_whole_gap"]) < 15:
                gap_examples["no_trade_whole_gap"].append(
                    {"universe": uni, "code": c, "gap_from": gs, "gap_to": ge,
                     "n_months": len(ms), "daily_span": span_map.get(c)}
                )
    else:
        gap_kinds["traded_in_gap"] += 1
OUT["membership_gaps"] = {
    "n_gaps": len(gaps),
    "kinds": gap_kinds,
    "note": ("no_trade_whole_gap = 缺口期间该票一天都没成交（长停牌）→ 源A 把它"
             "报成'退出再进入'；traded_in_gap = 缺口期间正常成交 → 真调出再调入"),
    "examples_no_trade_whole_gap": gap_examples["no_trade_whole_gap"],
}

# ---------- qlib instruments：月内调整量级 ----------
root = cfg.QLIB_RELEASE / "instruments"


def to_lake(code: str) -> str:
    return f"{code[2:]}.{code[:2]}"


def compact(iso: str) -> str:
    return iso.replace("-", "")


qa = {}
for uni in cfg.UNIVERSES:
    p = root / f"{uni}.txt"
    if not p.is_file():
        qa[uni] = {"status": "missing"}
        continue
    per = defaultdict(list)
    for ln in p.read_text().splitlines():
        if not ln.strip():
            continue
        c, s, e = ln.split("\t")[:3]
        per[to_lake(c)].append((s, e))
    merged = defaultdict(list)
    for c, segs in per.items():
        segs.sort()
        cur_s, cur_e = segs[0]
        for s, e in segs[1:]:
            if dt.date.fromisoformat(s) == dt.date.fromisoformat(cur_e) + dt.timedelta(days=1):
                cur_e = max(cur_e, e)
            else:
                merged[c].append((cur_s, cur_e))
                cur_s, cur_e = s, e
        merged[c].append((cur_s, cur_e))

    snaps = dates_by_uni[uni]
    snapset = set(snaps)
    first, last = snaps[0], snaps[-1]
    n_merged = sum(len(v) for v in merged.values())
    invisible = []          # 整段落在两期快照之间 → 源A 完全看不到
    start_off_snap = 0      # 起点不是快照日（月内调入）
    end_off_snap = 0
    in_window = 0
    lags = []
    for c, segs in merged.items():
        for s, e in segs:
            cs, ce = compact(s), min(compact(e), lake.FREEZE_DATE_COMPACT)
            if ce < first or cs > last:
                continue
            in_window += 1
            covered = [d for d in snaps if cs <= d <= ce]
            if not covered:
                invisible.append({"code": c, "start": cs, "end": ce})
                continue
            if cs not in snapset:
                start_off_snap += 1
                lags.append(
                    (dt.date.fromisoformat(covered[0][:4] + "-" + covered[0][4:6] + "-" + covered[0][6:])
                     - dt.date.fromisoformat(s)).days
                )
            if ce not in snapset:
                end_off_snap += 1
    lags_sorted = sorted(lags)
    qa[uni] = {
        "n_lines": sum(len(v) for v in per.values()),
        "n_codes": len(per),
        "n_merged_segments": n_merged,
        "n_segments_overlapping_A_window": in_window,
        "n_segments_invisible_to_A": len(invisible),
        "pct_invisible": round(100.0 * len(invisible) / max(in_window, 1), 2),
        "n_starts_not_on_snapshot_date": start_off_snap,
        "n_ends_not_on_snapshot_date": end_off_snap,
        "entry_lag_days": {
            "n": len(lags_sorted),
            "min": lags_sorted[0] if lags_sorted else None,
            "p50": lags_sorted[len(lags_sorted) // 2] if lags_sorted else None,
            "p90": lags_sorted[int(len(lags_sorted) * 0.9)] if lags_sorted else None,
            "max": lags_sorted[-1] if lags_sorted else None,
            "mean": round(sum(lags_sorted) / len(lags_sorted), 2) if lags_sorted else None,
        },
        "invisible_examples": invisible[:12],
        "A_n_segments": int(
            pd.read_parquet(cfg.UNIVERSE_INTERVALS_PARQUET)
            .query("universe == @uni")
            .shape[0]
        ),
    }
    # 左截断量级：源A 首期成员里，qlib 说它更早就进来了的有多少
    firstmem = members[uni][first]
    earlier = 0
    earliest_gap_days = []
    for c in firstmem:
        segs = merged.get(c)
        if not segs:
            continue
        s0 = min(s for s, _ in segs)
        if compact(s0) < first:
            earlier += 1
            earliest_gap_days.append(
                (dt.date.fromisoformat(first[:4] + "-" + first[4:6] + "-" + first[6:])
                 - dt.date.fromisoformat(s0)).days
            )
    eg = sorted(earliest_gap_days)
    qa[uni]["left_censor_magnitude"] = {
        "n_first_period_members": len(firstmem),
        "n_with_qlib_start_before_A_first": earlier,
        "backdate_days_p50": eg[len(eg) // 2] if eg else None,
        "backdate_days_max": eg[-1] if eg else None,
    }
OUT["qlib_month_internal"] = qa

print(json.dumps(OUT, ensure_ascii=False, indent=1, default=str))
