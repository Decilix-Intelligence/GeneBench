import sys, datetime as dt, bisect, json, collections
sys.path.insert(0,"/data/shared/genebench/repo")
import genebench_config as cfg
import pandas as pd, numpy as np, duckdb
pd.set_option("display.width",250)
con=duckdb.connect(str(cfg.CATALOG),read_only=True)
td=[dt.date(int(x[:4]),int(x[4:6]),int(x[6:])) for x in con.execute("SELECT cal_date FROM trade_cal WHERE is_open=1 ORDER BY cal_date").fetchdf().cal_date]
sb=con.execute("SELECT ts_code,name,list_status,list_date,delist_date,last_seen_at FROM stock_basic").fetchdf()
con.close()
FR=dt.date(2026,7,31); td=[x for x in td if x<=FR]; tdi={x:i for i,x in enumerate(td)}
print("stock_basic rows",len(sb), "delisted", (sb.list_status=='D').sum())
sb.to_parquet("/data/shared/genebench/repo/ops/recon/_sb.parquet")

def prev_td(x):
    i=bisect.bisect_right(td,x)-1; return td[i] if i>=0 else None
def next_td(x):
    i=bisect.bisect_left(td,x); return td[i] if i<len(td) else None
A=pd.read_parquet(cfg.UNIVERSE_DIR/"index_weight_intervals.parquet")
B=pd.read_parquet(cfg.UNIVERSE_DIR/"qlib_instruments_intervals.parquet")
B=B[B.universe.isin(cfg.UNIVERSES)].copy()
A["in_d"]=pd.to_datetime(A.in_date,format="%Y%m%d").dt.date
A["out_d"]=pd.to_datetime(A.out_date,format="%Y%m%d").dt.date
A.loc[A.out_date.isna(),"out_d"]=FR
A["i0"]=A.in_d.map(lambda x:tdi[next_td(x)]); A["i1"]=A.out_d.map(lambda x:tdi[prev_td(x)])
B["in_g"]=B.in_date.map(next_td); B["out_g"]=B.out_date.map(prev_td)
B=B[B.in_g.notna()&B.out_g.notna()].copy()
B["i0"]=B.in_g.map(tdi); B["i1"]=B.out_g.map(tdi); B=B[B.i1>=B.i0]
def merge(rows):
    out=[]
    for s,e in sorted(rows):
        if out and s<=out[-1][1]+1: out[-1]=(out[-1][0],max(out[-1][1],e))
        else: out.append((s,e))
    return out
rows=[]
codes_any_A=set(A.code); codes_any_B=set(B.code)
for u in cfg.UNIVERSES:
    a=A[A.universe==u]; b=B[B.universe==u]
    lo=max(a.i0.min(),b.i0.min()); hi=min(a.i1.max(),b.i1.max())
    sA=collections.defaultdict(list); sB=collections.defaultdict(list)
    for c,s,e in zip(a.code,a.i0,a.i1):
        s2,e2=max(s,lo),min(e,hi)
        if s2<=e2: sA[c].append((s2,e2))
    for c,s,e in zip(b.code,b.i0,b.i1):
        s2,e2=max(s,lo),min(e,hi)
        if s2<=e2: sB[c].append((s2,e2))
    sA={c:merge(v) for c,v in sA.items()}; sB={c:merge(v) for c,v in sB.items()}
    for c in set(sA)|set(sB):
        n=hi-lo+1
        av=np.zeros(n,bool); bv=np.zeros(n,bool)
        for s,e in sA.get(c,[]): av[s-lo:e-lo+1]=True
        for s,e in sB.get(c,[]): bv[s-lo:e-lo+1]=True
        diff=av^bv
        if not diff.any(): continue
        both=av&bv
        idx=np.flatnonzero(diff); brk=np.flatnonzero(np.diff(idx)>1)
        st=np.concatenate(([0],brk+1)); en=np.concatenate((brk,[len(idx)-1]))
        for s_,e_ in zip(st,en):
            p0=idx[s_]; p1=idx[e_]
            left_both = bool(both[p0-1]) if p0>0 else None
            right_both= bool(both[p1+1]) if p1<n-1 else None
            rows.append(dict(universe=u,code=c,side="A" if av[p0] else "B",
                d0=str(td[p0+lo]),d1=str(td[p1+lo]),n_td=int(p1-p0+1),
                touch_lo=bool(p0==0),touch_hi=bool(p1==n-1),
                left_both=left_both,right_both=right_both,
                other_has_code_in_uni = bool((c in sB) if av[p0] else (c in sA)),
                code_in_other_src_at_all = bool((c in codes_any_B) if av[p0] else (c in codes_any_A)),
                n_both=int(both.sum())))
R=pd.DataFrame(rows)
R.to_parquet("/data/shared/genebench/repo/ops/recon/_runs2.parquet")
def kind(r):
    if r.left_both and r.right_both: return "hole"
    if r.right_both: return "lead"
    if r.left_both: return "trail"
    return "isolated"
R["kind"]=R.apply(kind,axis=1)
print(R.groupby(["universe","side","kind"]).agg(n=("n_td","size"),md=("n_td","sum")).to_string())
print()
print("=== isolated runs, by universe/side ===")
iso=R[R.kind=="isolated"]
print(iso.groupby(["universe","side","code_in_other_src_at_all"]).agg(n=("n_td","size"),md=("n_td","sum")).to_string())
print()
print("=== lead/trail run length distribution ===")
lt=R[R.kind.isin(["lead","trail"])]
print(lt.n_td.describe().to_string())
print(pd.cut(lt.n_td,[0,5,23,46,130,10**6]).value_counts().sort_index().to_string())
print()
print("=== hole runs sample ===")
print(R[R.kind=="hole"].sort_values("n_td",ascending=False).head(20).to_string())
