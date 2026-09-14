# -*- coding: utf-8 -*-
import duckdb
c=duckdb.connect("/home/ljn/projects/data/market_lake/catalog/market.duckdb", read_only=True)
c.execute("set threads=2")
G="/home/ljn/projects/data/market_lake/gold"
def one(label, path, n=2, order=None):
    print("\n--",label)
    try:
        rs=c.execute(f"select * from read_parquet('{path}') limit {n}").fetchall()
        for r in rs[:n]: print("   ", r)
    except Exception as e: print("    ERR", str(e)[:150])
one("suspend_d 20260828", f"{G}/suspend_d/trade_date=2026-08-28/*.parquet")
one("stk_limit 20260828", f"{G}/stk_limit/trade_date=2026-08-28/*.parquet")
one("limit_list_d 20260805", f"{G}/limit_list_d/trade_date=2026-08-05/*.parquet",1)
one("adj_factor 20260828", f"{G}/adj_factor/trade_date=2026-08-28/*.parquet")
print("\n-- income 600519.SH (ann/f_ann/end):")
try:
    for r in c.execute(f"select ts_code,ann_date,f_ann_date,end_date,end_type,update_flag,total_revenue,n_income from read_parquet('{G}/income/ts_code=600519.SH/*.parquet') order by ann_date desc limit 3").fetchall(): print("   ",r)
except Exception as e: print("   ERR",str(e)[:150])
print("\n-- fina_indicator 600519.SH:")
try:
    for r in c.execute(f"select ts_code,ann_date,end_date,eps,roe,netprofit_margin from read_parquet('{G}/fina_indicator/ts_code=600519.SH/*.parquet') order by ann_date desc limit 3").fetchall(): print("   ",r)
except Exception as e: print("   ERR",str(e)[:150])
print("\n-- stock_basic partitions:")
import os
p=f"{G}/stock_basic"
print("   ", sorted(os.listdir(p))[:20])
print("\n-- index_weight distinct dates for 000300 recent:")
for r in c.execute("select distinct trade_date from index_weight where index_code='000300.SH' order by 1 desc limit 6").fetchall(): print("   ",r)
print("\n-- index_weight monthly cadence check (2026):")
for r in c.execute("select trade_date, count(*) from index_weight where index_code='000300.SH' and trade_date>='20260101' group by 1 order by 1").fetchall(): print("   ",r)
print("\n-- stock_st types:")
for r in c.execute("select type, type_name, count(*) from stock_st group by 1,2 order by 3 desc limit 8").fetchall(): print("   ",r)
print("\n-- namechange sample:")
for r in c.execute("select * from namechange order by ann_date desc limit 2").fetchall(): print("   ",r)
