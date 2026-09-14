"""探针 4:分歧事件(极大单边成员日连续段)的结构。"""
from __future__ import annotations
import bisect, collections, datetime as dt
import pandas as pd
import genebench_config as cfg
from snapshots import lake

FREEZE = dt.date.fromisoformat(cfg.FREEZE_DATE)
cal = lake.query("SELECT cal_date FROM trade_cal WHERE is_open=1 AND cal_date<=? ORDER BY cal_date",
                 [lake.FREEZE_DATE_COMPACT])["cal_date"].tolist()
CAL = [dt.date(int(d[:4]), int(d[4:6]), int(d[6:])) for d in cal]
A = pd.read_parquet(cfg.UNIVERSE_DIR / "index_weight_intervals.parquet")
B = pd.read_parquet(cfg.UNIVERSE_DIR / "qlib_instruments_intervals.parquet")
d8 = lambda s: dt.date(int(s[:4]), int(s[4:6]), int(s[6:]))
lo_idx = lambda d: bisect.bisect_left(CAL, d)
hi_idx = lambda d: bisect.bisect_right(CAL, d) - 1

def runs(idx):
    out = []
    for i in sorted(idx):
        if out and i == out[-1][1] + 1: out[-1][1] = i
        else: out.append([i, i])
    return [tuple(r) for r in out]

for uni in cfg.UNIVERSES:
    a, b = A[A.universe == uni], B[B.universe == uni]
    W0 = max(min(lo_idx(d8(x)) for x in a.in_date), min(lo_idx(x) for x in b.in_date))
    W1 = min(max(hi_idx(FREEZE if pd.isna(x) else d8(x)) for x in a.out_date),
             max(hi_idx(x) for x in b.out_date))
    SA, SB = collections.defaultdict(set), collections.defaultdict(set)
    for c, i, o in zip(a.code, a.in_date, a.out_date):
        for k in range(max(lo_idx(d8(i)), W0), min(hi_idx(FREEZE if pd.isna(o) else d8(o)), W1) + 1): SA[c].add(k)
    for c, i, o in zip(b.code, b.in_date, b.out_date):
        for k in range(max(lo_idx(i), W0), min(hi_idx(o), W1) + 1): SB[c].add(k)
    events = []
    for c in set(SA) | set(SB):
        sa, sb = SA.get(c, set()), SB.get(c, set())
        for lo, hi in runs(sa - sb): events.append(("A", c, lo, hi, hi - lo + 1))
        for lo, hi in runs(sb - sa): events.append(("B", c, lo, hi, hi - lo + 1))
    tot = sum(e[4] for e in events)
    print(f"\n##### {uni} 窗口 {CAL[W0]}..{CAL[W1]}  分歧事件 {len(events)} 个,覆盖成员日 {tot}")
    bylen = collections.Counter(e[4] for e in events)
    print("  事件长度分布(top15):", sorted(bylen.items())[:15])
    print("  A单边事件:", sum(1 for e in events if e[0]=="A"), " B单边:", sum(1 for e in events if e[0]=="B"))
    # 边界日直方图
    st = collections.Counter((e[0], CAL[e[2]]) for e in events)
    en = collections.Counter((e[0], CAL[e[3]]) for e in events)
    print("  事件起始日 top12:", st.most_common(12))
    print("  事件结束日 top12:", en.most_common(12))
    # 整段缺失(code 只在一方)
    onlyA = sorted(set(SA) - set(SB)); onlyB = sorted(set(SB) - set(SA))
    print(f"  只A有的 code({len(onlyA)}): {onlyA[:25]}")
    print(f"  只B有的 code({len(onlyB)}): {onlyB[:25]}")
