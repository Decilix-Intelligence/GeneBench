import sys, datetime as dt, bisect, json, collections
sys.path.insert(0, "/data/shared/genebench/repo")
import genebench_config as cfg
import pandas as pd, numpy as np, duckdb

con = duckdb.connect(str(cfg.CATALOG), read_only=True)
td = [dt.date(int(x[:4]),int(x[4:6]),int(x[6:])) for x in
      con.execute("SELECT cal_date FROM trade_cal WHERE is_open=1 ORDER BY cal_date").fetchdf().cal_date]
con.close()
FR = dt.date(2026,7,31); td=[x for x in td if x<=FR]; tdi={x:i for i,x in enumerate(td)}
def prev_td(x):
    i=bisect.bisect_right(td,x)-1; return td[i] if i>=0 else None
def next_td(x):
    i=bisect.bisect_left(td,x); return td[i] if i<len(td) else None

A = pd.read_parquet(cfg.UNIVERSE_DIR/"index_weight_intervals.parquet")
B = pd.read_parquet(cfg.UNIVERSE_DIR/"qlib_instruments_intervals.parquet")
B = B[B.universe.isin(cfg.UNIVERSES)].copy()
A["in_d"]=pd.to_datetime(A.in_date,format="%Y%m%d").dt.date
A["out_d"]=pd.to_datetime(A.out_date,format="%Y%m%d").dt.date
A.loc[A.out_date.isna(),"out_d"]=FR
A["i0"]=A.in_d.map(lambda x: tdi[next_td(x)]); A["i1"]=A.out_d.map(lambda x: tdi[prev_td(x)])
B["in_g"]=B.in_date.map(next_td); B["out_g"]=B.out_date.map(prev_td)
B=B[B.in_g.notna()&B.out_g.notna()].copy()
B["i0"]=B.in_g.map(tdi); B["i1"]=B.out_g.map(tdi); B=B[B.i1>=B.i0]

def merge(rows):
    out=[]
    for s,e in sorted(rows):
        if out and s<=out[-1][1]+1: out[-1]=(out[-1][0],max(out[-1][1],e))
        else: out.append((s,e))
    return out

summary={}
runs_all=[]
for u in cfg.UNIVERSES:
    a=A[A.universe==u]; b=B[B.universe==u]
    lo=max(a.i0.min(), b.i0.min()); hi=min(a.i1.max(), b.i1.max())
    segA=collections.defaultdict(list); segB=collections.defaultdict(list)
    for c,s,e in zip(a.code,a.i0,a.i1):
        s2,e2=max(s,lo),min(e,hi)
        if s2<=e2: segA[c].append((s2,e2))
    for c,s,e in zip(b.code,b.i0,b.i1):
        s2,e2=max(s,lo),min(e,hi)
        if s2<=e2: segB[c].append((s2,e2))
    segA={c:merge(v) for c,v in segA.items()}
    segB={c:merge(v) for c,v in segB.items()}
    # member-day
    def expand(seg):
        s=set()
        for c,vs in seg.items():
            for a0,a1 in vs: s.update((c,i) for i in range(a0,a1+1))
        return s
    SA=expand(segA); SB=expand(segB)
    inter=len(SA&SB); union=len(SA|SB)
    summary[u]=dict(window=[str(td[lo]),str(td[hi])], n_td=hi-lo+1,
        A_md=len(SA), B_md=len(SB), inter=inter, union=union,
        jaccard=round(inter/union,6), only_A=len(SA-SB), only_B=len(SB-SA),
        n_codes_A=len(segA), n_codes_B=len(segB),
        n_seg_A=sum(len(v) for v in segA.values()), n_seg_B=sum(len(v) for v in segB.values()))
    # disagreement runs per code
    codes=set(segA)|set(segB)
    for c in codes:
        av=np.zeros(hi-lo+1,bool); bv=np.zeros(hi-lo+1,bool)
        for s,e in segA.get(c,[]): av[s-lo:e-lo+1]=True
        for s,e in segB.get(c,[]): bv[s-lo:e-lo+1]=True
        diff=av^bv
        if not diff.any(): continue
        idx=np.flatnonzero(diff); brk=np.flatnonzero(np.diff(idx)>1)
        starts=np.concatenate(([0],brk+1)); ends=np.concatenate((brk,[len(idx)-1]))
        for s_,e_ in zip(starts,ends):
            i0=idx[s_]+lo; i1=idx[e_]+lo
            runs_all.append(dict(universe=u,code=c,side="A" if av[idx[s_]] else "B",
                d0=str(td[i0]),d1=str(td[i1]),n_td=i1-i0+1,i0=int(i0),i1=int(i1)))
print(json.dumps(summary,ensure_ascii=False,indent=1,default=int))
R=pd.DataFrame(runs_all)
R.to_parquet("/data/shared/genebench/repo/ops/recon/_runs.parquet")
print("total runs",len(R))
print(R.groupby(["universe","side"]).agg(n=("n_td","size"),md=("n_td","sum")).to_string())
print("=== run length hist ===")
print(pd.cut(R.n_td,[0,1,2,5,21,63,10**6]).value_counts().sort_index().to_string())
print("=== top csi1000 early runs ===")
print(R[(R.universe=="csi1000")].sort_values("n_td",ascending=False).head(8).to_string())
print("=== csi300 runs ===")
print(R[R.universe=="csi300"].sort_values("n_td",ascending=False).head(25).to_string())
