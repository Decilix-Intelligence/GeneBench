import sys, datetime as dt, bisect
sys.path.insert(0, "/data/shared/genebench/repo")
import genebench_config as cfg
import pandas as pd, numpy as np, duckdb

con = duckdb.connect(str(cfg.CATALOG), read_only=True)
td = [dt.date(int(x[:4]),int(x[4:6]),int(x[6:])) for x in
      con.execute("SELECT cal_date FROM trade_cal WHERE is_open=1 ORDER BY cal_date").fetchdf().cal_date]
con.close()
FR = dt.date(2026,7,31)
td = [x for x in td if x <= FR]
tdi = {x:i for i,x in enumerate(td)}
def prev_td(x):
    i = bisect.bisect_right(td, x) - 1
    return td[i] if i>=0 else None
def next_td(x):
    i = bisect.bisect_left(td, x)
    return td[i] if i < len(td) else None

A = pd.read_parquet(cfg.UNIVERSE_DIR / "index_weight_intervals.parquet")
B = pd.read_parquet(cfg.UNIVERSE_DIR / "qlib_instruments_intervals.parquet")
B = B[B.universe.isin(cfg.UNIVERSES)].copy()
A["in_d"] = pd.to_datetime(A.in_date, format="%Y%m%d").dt.date
A["out_d"] = pd.to_datetime(A.out_date, format="%Y%m%d").dt.date
A.loc[A.out_date.isna(), "out_d"] = FR

# check B in_date is trading day within window
for u in cfg.UNIVERSES:
    lo = max(A[A.universe==u].in_d.min(), B[B.universe==u].in_date.min())
    sub = B[(B.universe==u)&(B.in_date>=lo)]
    ok = sub.in_date.map(lambda x: x in tdi).mean()
    print(f"{u}: window_lo={lo}  B in_date trading-day rate in window = {ok:.6f}  n={len(sub)}")

# merge B on trading grid
def merge_segments(rows):
    # rows: list of (in_g_idx, out_g_idx) sorted
    out=[]
    for s,e in rows:
        if out and s <= out[-1][1]+1:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s,e))
    return out

B["in_g"] = B.in_date.map(next_td); B["out_g"] = B.out_date.map(prev_td)
B = B[B.in_g.notna() & B.out_g.notna()].copy()
B["i0"] = B.in_g.map(tdi); B["i1"] = B.out_g.map(tdi)
B = B[B.i1>=B.i0]
res={}
for u in cfg.UNIVERSES:
    sub = B[B.universe==u]
    n_raw = len(sub); n_merged=0
    for c,g in sub.groupby("code"):
        n_merged += len(merge_segments(sorted(zip(g.i0,g.i1))))
    print(f"{u}: B raw rows={n_raw} -> merged segments={n_merged}; A segments={ (A.universe==u).sum() }")
