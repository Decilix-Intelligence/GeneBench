"""探针 1:两源产物的形态 / 重叠窗口 / 一阶差异量级。"""
from __future__ import annotations
import datetime as dt
import pandas as pd
import genebench_config as cfg
from snapshots import lake

pd.set_option("display.width", 200)

A = pd.read_parquet(cfg.UNIVERSE_DIR / "index_weight_intervals.parquet")
B = pd.read_parquet(cfg.UNIVERSE_DIR / "qlib_instruments_intervals.parquet")
print("A", A.shape, list(A.dtypes.items()))
print(A.head(3).to_string())
print("B", B.shape, list(B.dtypes.items()))
print(B.head(3).to_string())
print()
print("A universes:", A.universe.value_counts().to_dict())
print("B universes:", B.universe.value_counts().to_dict())
print("A out_date nulls:", A.out_date.isna().sum())
print("B out_date == freeze:", (B.out_date == dt.date(2026, 7, 31)).sum())
print()
for u in cfg.UNIVERSES:
    a = A[A.universe == u]
    b = B[B.universe == u]
    print(f"{u}: A in[{a.in_date.min()},{a.in_date.max()}] out[{a.out_date.min()},{a.out_date.max()}] codes={a.code.nunique()}")
    print(f"{u}: B in[{b.in_date.min()},{b.in_date.max()}] out[{b.out_date.min()},{b.out_date.max()}] codes={b.code.nunique()}")
    print(f"{u}: A距离B码集: A-only={len(set(a.code)-set(b.code))} B-only={len(set(b.code)-set(a.code))} both={len(set(a.code)&set(b.code))}")
    print(f"{u}: B distinct in_dates={b.in_date.nunique()} A distinct in_dates={a.in_date.nunique()}")
print()
cal = lake.query(
    "SELECT cal_date FROM trade_cal WHERE is_open = 1 AND cal_date <= ? ORDER BY cal_date",
    [lake.FREEZE_DATE_COMPACT],
)["cal_date"].tolist()
print("trade_cal open days <= freeze:", len(cal), cal[0], cal[-1])
