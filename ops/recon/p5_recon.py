import sys, datetime as dt, json, collections
sys.path.insert(0,"/data/shared/genebench/repo")
import genebench_config as cfg
import pandas as pd, numpy as np, duckdb
pd.set_option("display.width",250)
R=pd.read_parquet("/data/shared/genebench/repo/ops/recon/_runs.parquet")
B=pd.read_parquet(cfg.UNIVERSE_DIR/"qlib_instruments_intervals.parquet")
B=B[B.universe.isin(cfg.UNIVERSES)]
A=pd.read_parquet(cfg.UNIVERSE_DIR/"index_weight_intervals.parquet")

print("=== csi1000 only_A md before 2015-05-29 ===")
c1=R[(R.universe=="csi1000")]
pre=c1[c1.d1<"2015-05-29"]
strad=c1[(c1.d0<"2015-05-29")&(c1.d1>="2015-05-29")]
print("runs fully pre:",len(pre),"md",pre.n_td.sum())
print("runs straddling:",len(strad),"md",strad.n_td.sum())
print(strad.head(12).to_string())

print()
print("=== B distinct epoch in_dates per universe per year (within window) ===")
for u in cfg.UNIVERSES:
    s=B[(B.universe==u)]
    ep=sorted(set(s.in_date))
    ep=[e for e in ep if e>=dt.date(2009,1,23)]
    yr=collections.Counter(e.year for e in ep)
    print(u,"n_epochs_in_window",len(ep))
    print("  ",dict(sorted(yr.items())))
    print("   first 12:",[str(x) for x in ep[:12]])
    print("   last 12:",[str(x) for x in ep[-12:]])

print()
print("=== 302132.SZ / 601360.SH raw rows ===")
for c in ["302132.SZ","601360.SH","300114.SZ","000022.SZ","001872.SZ","000043.SZ","001914.SZ","601313.SH"]:
    a=A[(A.code==c)]; b=B[(B.code==c)]
    print("---",c,"A rows",len(a),"B rows",len(b))
    if len(a): print(a[["universe","segment_idx","in_date","out_date","left_censored","right_censored"]].to_string())
    if len(b): print("  B universes:",b.groupby("universe").agg(n=("in_date","size"),mn=("in_date","min"),mx=("out_date","max")).to_dict("index"))
