import sys, datetime as dt, json, collections
sys.path.insert(0,"/data/shared/genebench/repo")
import genebench_config as cfg
import pandas as pd, numpy as np
pd.set_option("display.width",260); pd.set_option("display.max_colwidth",40)
R=pd.read_parquet("/data/shared/genebench/repo/ops/recon/_runs2.parquet")
sb=pd.read_parquet("/data/shared/genebench/repo/ops/recon/_sb.parquet")
sb=sb.sort_values("last_seen_at").drop_duplicates("ts_code",keep="last")
name=dict(zip(sb.ts_code,sb.name)); dl=dict(zip(sb.ts_code,sb.delist_date)); ls=dict(zip(sb.ts_code,sb.list_status))
def kind(r):
    if r.left_both and r.right_both: return "hole"
    if r.right_both: return "lead"
    if r.left_both: return "trail"
    return "isolated"
R["kind"]=R.apply(kind,axis=1)
R["name"]=R.code.map(name); R["delist"]=R.code.map(dl); R["lstat"]=R.code.map(ls)

# --- orphan codes (present in one source only, anywhere)
orphA=sorted(set(R[(R.side=="A")&(~R.code_in_other_src_at_all)].code))
orphB=sorted(set(R[(R.side=="B")&(~R.code_in_other_src_at_all)].code))
print("orphan A-only codes:",[(c,name.get(c)) for c in orphA])
print("orphan B-only codes:",[(c,name.get(c)) for c in orphB])

# pair them by day overlap
def days(sub):
    s=set()
    for d0,d1 in zip(sub.d0,sub.d1):
        s.add((d0,d1))
    return s
def dayset(sub):
    out=set()
    for d0,d1,u in zip(sub.d0,sub.d1,sub.universe):
        out.add((u,d0,d1))
    return out
import itertools
print()
print("=== orphan pairing (overlap of disagreement day ranges, same universe) ===")
def expand(sub):
    s=set()
    for u,d0,d1 in zip(sub.universe,sub.d0,sub.d1):
        s.add((u,d0,d1))
    return s
def to_days(sub):
    s=set()
    for u,d0,d1 in zip(sub.universe,sub.d0,sub.d1):
        a=dt.date.fromisoformat(d0); b=dt.date.fromisoformat(d1)
        # coarse: month granularity
        cur=a
        while cur<=b:
            s.add((u,cur.year,cur.month)); 
            cur = (cur.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
    return s
for a in orphA:
    da=to_days(R[(R.side=="A")&(R.code==a)])
    best=[]
    for b in orphB:
        db=to_days(R[(R.side=="B")&(R.code==b)])
        if not da or not db: continue
        ov=len(da&db)/min(len(da),len(db))
        if ov>0.3: best.append((b,name.get(b),round(ov,3),len(da),len(db)))
    print(f"  A-orphan {a} ({name.get(a)}) -> {best}")

print()
print("=== delisted codes among runs ===")
d=R[R.lstat=="D"]
print("runs with delisted code:",len(d),"md",d.n_td.sum())
print(d.groupby(["universe","side","kind"]).agg(n=("n_td","size"),md=("n_td","sum")).to_string())
print(d.sort_values("n_td",ascending=False).head(15)[["universe","code","name","side","kind","d0","d1","n_td","delist"]].to_string())

print()
print("=== runs overlapping delist_date +- 200d ===")
def near(r):
    if not isinstance(r.delist,str) or len(r.delist)!=8: return False
    dd=dt.date(int(r.delist[:4]),int(r.delist[4:6]),int(r.delist[6:]))
    a=dt.date.fromisoformat(r.d0); b=dt.date.fromisoformat(r.d1)
    return a-dt.timedelta(days=200)<=dd<=b+dt.timedelta(days=200)
R["near_delist"]=R.apply(near,axis=1)
print(R.groupby(["near_delist"]).agg(n=("n_td","size"),md=("n_td","sum")).to_string())
print(R[R.near_delist].sort_values("n_td",ascending=False).head(20)[["universe","code","name","side","kind","d0","d1","n_td","delist"]].to_string())

print()
print("=== csi300 A-lead / B-trail (源A 领先) ===")
print(R[(R.universe=="csi300")&(((R.side=="A")&(R.kind=="lead"))|((R.side=="B")&(R.kind=="trail")))][["code","name","side","kind","d0","d1","n_td","delist"]].to_string())
print()
print("=== csi500 A-lead / B-trail ===")
print(R[(R.universe=="csi500")&(((R.side=="A")&(R.kind=="lead"))|((R.side=="B")&(R.kind=="trail")))][["code","name","side","kind","d0","d1","n_td","delist"]].to_string())
print()
print("=== isolated (非孤儿码) ===")
print(R[(R.kind=="isolated")&(R.code_in_other_src_at_all)].sort_values("n_td",ascending=False)[["universe","code","name","side","d0","d1","n_td","delist","lstat"]].head(30).to_string())
