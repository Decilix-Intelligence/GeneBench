# -*- coding: utf-8 -*-
import duckdb, json, sys
DB="/home/ljn/projects/data/market_lake/catalog/market.duckdb"
c=duckdb.connect(DB, read_only=True)
def hdr(t): print("\n"+"="*8+" "+t)
def cols(v):
    try: return [r[0] for r in c.execute(f'describe select * from "{v}" limit 0').fetchall()]
    except Exception as e: return ["<ERR "+str(e)[:70]+">"]
def q(sql, n=3):
    try:
        rs=c.execute(sql).fetchall()
        for r in rs[:n]: print("   ", r)
        if not rs: print("    <empty>")
    except Exception as e: print("    ERR", str(e)[:160])

hdr("B1a index_weight / index_member_all / dc_index_member / ths_index_member")
for v in ["index_weight","index_member_all","index_classify","dc_index_member","ths_index_basic"]:
    print(f" -- {v}: {cols(v)}")
q("select index_code, count(*) n, min(trade_date), max(trade_date), count(distinct trade_date) d from index_weight where index_code in ('000300.SH','000905.SH','000852.SH','000016.SH','399006.SZ') group by 1 order by 1", 8)
print("  index_weight all indices covered:")
q("select count(distinct index_code) from index_weight")
print("  sample index_weight rows:")
q("select * from index_weight where index_code='000300.SH' order by trade_date desc limit 3")
print("  index_member_all sample (in/out dates?):")
q("select * from index_member_all limit 2", 2)

hdr("B1b delist / list_date  (stock_basic)")
print(" -- stock_basic:", cols("stock_basic"))
q("select list_status, count(*) , count(distinct ts_code) from stock_basic group by 1")
q("select count(distinct ts_code) from stock_basic where delist_date is not null and delist_date<>''")
q("select ts_code,name,list_date,delist_date,list_status,first_seen_at from stock_basic where delist_date is not null and delist_date<>'' order by delist_date desc limit 3")
q("select min(list_date), max(list_date) from stock_basic where list_date is not null and list_date<>''")

hdr("B1c ST marks + history")
for v in ["stock_st","st_history","namechange","stk_alert"]:
    print(f" -- {v}: {cols(v)}")
q("select * from stock_st order by trade_date desc limit 3")
q("select * from st_history limit 2",2)

hdr("B1d suspension")
print(" -- suspend_d:", cols("suspend_d"))
q("select * from suspend_d order by trade_date desc limit 3")
q("select suspend_type, count(*) from suspend_d group by 1 order by 2 desc",6)

hdr("B2 limit price / tradability")
print(" -- stk_limit:", cols("stk_limit"))
q("select * from stk_limit order by trade_date desc limit 2",2)
print(" -- daily cols:", cols("daily"))
print(" -- limit_list_d:", cols("limit_list_d"))
q("select * from limit_list_d order by trade_date desc limit 2",2)
print("  suspended-day presence in daily (20260828):")
q("select (select count(*) from suspend_d where trade_date='20260828' and suspend_type='S') as susp_S, (select count(*) from daily where trade_date='20260828') as daily_rows, (select count(*) from stk_limit where trade_date='20260828') as limit_rows")
q("""select s.ts_code, s.suspend_type, (select count(*) from daily d where d.ts_code=s.ts_code and d.trade_date=s.trade_date) as in_daily
     from suspend_d s where s.trade_date='20260828' limit 3""")

hdr("B3 adjustment chain")
print(" -- adj_factor:", cols("adj_factor"))
q("select min(trade_date),max(trade_date),count(*),count(distinct ts_code) from adj_factor")
q("select * from adj_factor order by trade_date desc limit 2",2)
print(" -- stk_factor_pro price cols:", [x for x in cols("stk_factor_pro") if x.split('_')[0] in ('open','high','low','close','pre','adj')][:20])
print(" -- fund_adj:", cols("fund_adj"))
q("select min(trade_date),max(trade_date) from fund_adj")

hdr("B4 trade calendars")
for v in ["trade_cal","hk_trade_calendar","fut_trade_calendar"]:
    print(f" -- {v}: {cols(v)}")
    q(f"select exchange, count(*) n, min(cal_date), max(cal_date) from {v} group by 1 order by 1", 12)
q("select * from trade_cal order by cal_date desc limit 2",2)

hdr("B5 financial dual timestamps")
for v in ["income","income_vip","balancesheet","balancesheet_vip","cashflow","cashflow_vip","fina_indicator","fina_indicator_vip","forecast","express","fina_mainbz_vip","disclosure_date"]:
    cs=cols(v)
    date_like=[x for x in cs if any(k in x for k in ("date","period","end","ann"))]
    print(f" -- {v}: {date_like}")
q("select ts_code,ann_date,f_ann_date,end_date,report_type,update_flag from income order by ann_date desc limit 3")
q("select ts_code,ann_date,end_date from fina_indicator order by ann_date desc limit 2",2)
q("select * from disclosure_date order by ann_date desc limit 2",2)
