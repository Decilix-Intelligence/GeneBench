import sys, datetime as dt
sys.path.insert(0, "/data/shared/genebench/repo")
import genebench_config as cfg
import pandas as pd, numpy as np, duckdb

con = duckdb.connect(str(cfg.CATALOG), read_only=True)
cal = con.execute("SELECT cal_date FROM trade_cal WHERE is_open=1 ORDER BY cal_date").fetchdf()
td = pd.to_datetime(cal.cal_date, format="%Y%m%d").dt.date.tolist()
con.close()
tdset = set(td)
print("trade days", len(td), td[0], td[-1])
print("2026-07-31 open?", dt.date(2026,7,31) in tdset)

A = pd.read_parquet(cfg.UNIVERSE_DIR / "index_weight_intervals.parquet")
B = pd.read_parquet(cfg.UNIVERSE_DIR / "qlib_instruments_intervals.parquet")
B = B[B.universe.isin(cfg.UNIVERSES)].copy()

def d(s): return pd.to_datetime(s, format="%Y%m%d").dt.date
A["in_d"] = d(A.in_date)
A["out_d"] = pd.to_datetime(A.out_date, format="%Y%m%d").dt.date
A.loc[A.out_date.isna(), "out_d"] = dt.date(2026,7,31)

# check A endpoints on grid
print("A in_date all trading days?", A.in_d.map(lambda x: x in tdset).all())
print("A out_date all trading days?", A.out_d.map(lambda x: x in tdset).all())
print("B in_date all trading days?", B.in_date.map(lambda x: x in tdset).all())
print("B out_date trading-day rate:", B.groupby("universe").out_date.apply(lambda s: round(s.map(lambda x: x in tdset).mean(),4)).to_dict())

# B: how many rows have in_date < 2009-01-23 (before trade_cal start 2009-01-01?)
print("B in_date < 2009-01-01 rows:", (B.in_date < dt.date(2009,1,1)).sum())
print("B min in_date per universe:", B.groupby("universe").in_date.min().to_dict())
print("B max out_date per universe:", B.groupby("universe").out_date.max().to_dict())
print("A min in per uni:", A.groupby("universe").in_d.min().to_dict())
print("A max out per uni:", A.groupby("universe").out_d.max().to_dict())

# B merging on trading-day grid
tdidx = {x:i for i,x in enumerate(td)}
def prev_td(x):
    # last trading day <= x
    import bisect
    i = bisect.bisect_right(td, x) - 1
    return td[i] if i>=0 else None
def next_td(x):
    import bisect
    i = bisect.bisect_left(td, x)
    return td[i] if i < len(td) else None

B2 = B.copy()
B2["in_g"] = B2.in_date.map(next_td)
B2["out_g"] = B2.out_date.map(prev_td)
print("B rows with in_g None:", B2.in_g.isna().sum(), "out_g None:", B2.out_g.isna().sum())
bad = B2[(B2.out_g.notna())&(B2.in_g.notna())&(B2.out_g < B2.in_g)]
print("B rows collapsing to empty on trading grid:", len(bad))
print(bad.groupby("universe").size().to_dict())
print(bad.head(10).to_string())
