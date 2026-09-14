import sys
sys.path.insert(0, "/data/shared/genebench/repo")
import genebench_config as cfg
import pandas as pd, duckdb

A = pd.read_parquet(cfg.UNIVERSE_DIR / "index_weight_intervals.parquet")
B = pd.read_parquet(cfg.UNIVERSE_DIR / "qlib_instruments_intervals.parquet")
print("=== A schema ==="); print(A.dtypes); print(A.head(4).to_string()); print("A rows", len(A))
print("=== B schema ==="); print(B.dtypes); print(B.head(4).to_string()); print("B rows", len(B))
print("=== A universes ==="); print(A.groupby("universe").size())
print("=== B universes ==="); print(B.groupby("universe").size())
print("=== A null out_date ==="); print(A["out_date"].isna().sum())
print("=== B out_date == freeze ==="); print((B["out_date"].astype(str)==cfg.FREEZE_DATE).sum())
print("=== A in_date sample types ==="); print(repr(A["in_date"].iloc[0]), repr(A["out_date"].iloc[0]))
print("=== B in_date sample types ==="); print(repr(B["in_date"].iloc[0]), repr(B["out_date"].iloc[0]))
con = duckdb.connect(str(cfg.CATALOG), read_only=True)
cal = con.execute("SELECT cal_date, is_open FROM trade_cal ORDER BY cal_date").fetchdf()
print("=== trade_cal ==="); print(cal.dtypes); print(cal.head(3).to_string()); print("rows", len(cal), "open", int(cal.is_open.astype(int).sum()))
con.close()
