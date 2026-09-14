"""对抗审查 源A 探针 6：出场侧负滞后的成因（周末伪影 vs 真矛盾）。"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from collections import Counter, defaultdict

os.umask(0o077)
sys.path.insert(0, "/data/shared/genebench/repo")
import genebench_config as cfg  # noqa: E402
from snapshots import lake  # noqa: E402

lake.raise_open_file_limit()
with lake.catalog() as con:
    cal = [
        str(x)
        for x in lake.query(
            "SELECT cal_date FROM trade_cal WHERE is_open = 1 AND cal_date <= ? "
            "ORDER BY cal_date",
            [lake.FREEZE_DATE_COMPACT],
            conn=con,
        )["cal_date"].tolist()
    ]
    rawall = lake.query(
        "SELECT index_code, trade_date FROM index_weight WHERE trade_date <= ?",
        [lake.FREEZE_DATE_COMPACT],
        conn=con,
    )
snaps_by_uni = {
    u: sorted(set(rawall.loc[rawall["index_code"] == cfg.UNIVERSE_INDEX_CODE[u], "trade_date"].astype(str)))
    for u in cfg.UNIVERSES
}
calset = set(cal)
root = cfg.QLIB_RELEASE / "instruments"
OUT = {}
for uni in cfg.UNIVERSES:
    per = defaultdict(list)
    for ln in (root / f"{uni}.txt").read_text().splitlines():
        if not ln.strip():
            continue
        cd, s, e = ln.split("\t")[:3]
        per[f"{cd[2:]}.{cd[:2]}"].append((s, e))
    merged = defaultdict(list)
    for cd, segs in per.items():
        segs.sort()
        cs, ce = segs[0]
        for s, e in segs[1:]:
            if dt.date.fromisoformat(s) == dt.date.fromisoformat(ce) + dt.timedelta(days=1):
                ce = max(ce, e)
            else:
                merged[cd].append((cs, ce))
                cs, ce = s, e
        merged[cd].append((cs, ce))
    snaps = snaps_by_uni[uni]
    first, last = snaps[0], snaps[-1]
    mx = max(e for segs in per.values() for _, e in segs)
    hist = Counter()
    neg_end_is_trading_day = 0
    neg_examples = []
    for cd, segs in merged.items():
        for s, e in segs:
            ce = e.replace("-", "")
            if e == mx or not (first <= ce <= last):
                continue
            nxt = [d for d in snaps if d > ce]
            if not nxt:
                continue
            a_out = cal[cal.index(nxt[0]) - 1]
            lag = (dt.date.fromisoformat(f"{a_out[:4]}-{a_out[4:6]}-{a_out[6:]}")
                   - dt.date.fromisoformat(e)).days
            hist[lag] += 1
            if lag < 0:
                if ce in calset:
                    neg_end_is_trading_day += 1
                    if len(neg_examples) < 8:
                        neg_examples.append(
                            {"code": cd, "qlib_end": e, "A_out_date": a_out, "lag": lag}
                        )
    OUT[uni] = {
        "lag_histogram_head": dict(sorted(hist.items())[:8]),
        "n_negative": sum(v for k, v in hist.items() if k < 0),
        "n_negative_where_qlib_end_is_a_trading_day": neg_end_is_trading_day,
        "negative_examples_trading_day": neg_examples,
        "n_zero": hist.get(0, 0),
        "n_positive": sum(v for k, v in hist.items() if k > 0),
    }
print(json.dumps(OUT, ensure_ascii=False, indent=1, default=str))
