"""探针 6:代码映射对的两侧区间;窗口外统计;边界日联合分布。"""
from __future__ import annotations
import bisect, collections, datetime as dt
import pandas as pd
import genebench_config as cfg
from snapshots import lake

FREEZE = dt.date.fromisoformat(cfg.FREEZE_DATE)
cal = lake.query("SELECT cal_date FROM trade_cal WHERE is_open=1 ORDER BY cal_date")["cal_date"].tolist()
print("trade_cal 全量(含未来):", len(cal), cal[0], cal[-1])
A = pd.read_parquet(cfg.UNIVERSE_DIR / "index_weight_intervals.parquet")
B = pd.read_parquet(cfg.UNIVERSE_DIR / "qlib_instruments_intervals.parquet")
for uni, pairs in [("csi500", ["000022.SZ","001872.SZ","300114.SZ","302132.SZ","601868.SH","600068.SH"]),
                   ("csi1000", ["000022.SZ","001872.SZ","000043.SZ","001914.SZ","300114.SZ","302132.SZ","601313.SH","601360.SH","600680.SH"])]:
    print(f"\n===== {uni}")
    for c in pairs:
        a = A[(A.universe==uni)&(A.code==c)]
        b = B[(B.universe==uni)&(B.code==c)]
        sa = [f"{r.in_date}..{r.out_date}" for r in a.itertuples()]
        # 合并 B 的贴片段
        bs = sorted(zip(b.in_date, b.out_date))
        mg = []
        for i,o in bs:
            if mg and (i - mg[-1][1]).days <= 1: mg[-1][1] = max(mg[-1][1], o)
            else: mg.append([i,o])
        print(f"  {c}:  A={sa}")
        print(f"          B={[f'{x[0]}..{x[1]}' for x in mg]}")
# 窗口外:B 在 2009-01-05 之前(trade_cal 起点之前)的区间
print()
for uni in cfg.UNIVERSES:
    b = B[B.universe==uni]
    cut = {"csi300": dt.date(2009,1,23), "csi500": dt.date(2009,1,23), "csi1000": dt.date(2014,10,31)}[uni]
    pre = b[b.out_date < cut]
    span = b[(b.in_date < cut) & (b.out_date >= cut)]
    print(f"{uni}: B 完全早于窗口起点的区间 {len(pre)} 条 (codes {pre.code.nunique()}), "
          f"跨窗口起点 {len(span)} 条; B 最早 in={b.in_date.min()}")
    # 窗口外自然日
    days = 0
    for i,o in zip(pre.in_date, pre.out_date): days += (o-i).days+1
    print(f"      窗口外自然日成员日 {days}")
