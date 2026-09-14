"""探针 3:边界日结构 —— 两源的换仓日是不是同一批日子?"""
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

for uni in cfg.UNIVERSES:
    a, b = A[A.universe == uni], B[B.universe == uni]
    W0 = max(min(lo_idx(d8(x)) for x in a.in_date), min(lo_idx(x) for x in b.in_date))
    print(f"\n##### {uni}  窗口起 {CAL[W0]}")
    ain = sorted({d8(x) for x in a.in_date if lo_idx(d8(x)) > W0})
    bin_ = sorted({x for x in b.in_date if lo_idx(x) > W0})
    print(f"A 换仓生效日 {len(ain)} 个, B {len(bin_)} 个")
    sa, sb = set(ain), set(bin_)
    print(f"两边同日: {len(sa & sb)}   只A有: {len(sa - sb)}   只B有: {len(sb - sa)}")
    # 逐个配对:B 的每个日子,找最近的 A 日子
    rows = []
    for d in bin_:
        near = min(ain, key=lambda x: abs((x - d).days)) if ain else None
        rows.append((str(d), str(near), (near - d).days if near else None))
    print("B日 -> 最近A日 (差=A-B 天):")
    for r in rows:
        print(f"   {r[0]}  ->  {r[1]}   {r[2]:+d}")
    onlyA = sorted(sa - sb)
    print(f"只A有的换仓日({len(onlyA)}): {[str(x) for x in onlyA]}")
