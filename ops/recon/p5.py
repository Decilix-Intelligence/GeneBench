"""探针 5:具名个案 —— 单边码、非半年度分歧、退市票。"""
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
        if out and i == out[-1][1]+1: out[-1][1] = i
        else: out.append([i,i])
    return [tuple(r) for r in out]

sb = lake.query("SELECT ts_code, name, list_date, delist_date, list_status FROM stock_basic")
NAME = dict(zip(sb.ts_code, sb.name))
DELIST = dict(zip(sb.ts_code, sb.delist_date))
LIST = dict(zip(sb.ts_code, sb.list_date))
STATUS = dict(zip(sb.ts_code, sb.list_status))
print("stock_basic rows:", len(sb))

WIN = {}
EV = {}
for uni in cfg.UNIVERSES:
    a, b = A[A.universe==uni], B[B.universe==uni]
    W0 = max(min(lo_idx(d8(x)) for x in a.in_date), min(lo_idx(x) for x in b.in_date))
    W1 = min(max(hi_idx(FREEZE if pd.isna(x) else d8(x)) for x in a.out_date),
             max(hi_idx(x) for x in b.out_date))
    WIN[uni] = (W0, W1)
    SA, SB = collections.defaultdict(set), collections.defaultdict(set)
    for c,i,o in zip(a.code,a.in_date,a.out_date):
        for k in range(max(lo_idx(d8(i)),W0), min(hi_idx(FREEZE if pd.isna(o) else d8(o)),W1)+1): SA[c].add(k)
    for c,i,o in zip(b.code,b.in_date,b.out_date):
        for k in range(max(lo_idx(i),W0), min(hi_idx(o),W1)+1): SB[c].add(k)
    ev = []
    for c in set(SA)|set(SB):
        sa,sbb = SA.get(c,set()), SB.get(c,set())
        for lo,hi in runs(sa-sbb): ev.append(("A",c,lo,hi))
        for lo,hi in runs(sbb-sa): ev.append(("B",c,lo,hi))
    EV[uni] = (ev, SA, SB)

ERA1 = {dt.date(2009,7,1),dt.date(2009,12,29),dt.date(2010,1,4),dt.date(2010,7,1),
        dt.date(2011,1,4),dt.date(2011,7,1),dt.date(2012,1,4),dt.date(2012,7,2),
        dt.date(2013,1,4),dt.date(2013,7,1),dt.date(2009,5,6)}

for uni in cfg.UNIVERSES:
    ev, SA, SB = EV[uni]
    W0, W1 = WIN[uni]
    print(f"\n########## {uni}")
    # 非 era1 的长事件
    longs = [e for e in ev if (e[3]-e[2]+1) > 25 and CAL[e[2]] not in ERA1]
    print(f"长(>25交易日)且非 era1 起点的事件: {len(longs)}")
    for side,c,lo,hi in sorted(longs, key=lambda e:-(e[3]-e[2]))[:30]:
        print(f"  [{side}只有] {c} {NAME.get(c,'?')!s:<10} {CAL[lo]}..{CAL[hi]} ({hi-lo+1}交易日) "
              f"list={LIST.get(c)} delist={DELIST.get(c)} st={STATUS.get(c)}")
    # 单边码
    onlyA = sorted(set(SA)-set(SB)); onlyB = sorted(set(SB)-set(SA))
    print(f"  只A有 code {len(onlyA)}; 只B有 code {len(onlyB)}: {onlyB}")
    for c in onlyB:
        b2 = B[(B.universe==uni)&(B.code==c)]
        print(f"    B-only {c} {NAME.get(c,'不在stock_basic')} 段数={len(b2)} "
              f"{b2.in_date.min()}..{b2.out_date.max()}")
    if len(onlyA) <= 45:
        for c in onlyA:
            a2 = A[(A.universe==uni)&(A.code==c)]
            segs = [f"{r.in_date}..{r.out_date}" for r in a2.itertuples()]
            print(f"    A-only {c} {NAME.get(c,'?')!s:<10} delist={DELIST.get(c)} st={STATUS.get(c)} {segs}")
