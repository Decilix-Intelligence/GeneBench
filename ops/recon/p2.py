"""探针 2:归一化到交易日网格后,成员日一致率与分歧的一阶结构。"""
from __future__ import annotations
import bisect, collections, datetime as dt
import pandas as pd
import genebench_config as cfg
from snapshots import lake

FREEZE = dt.date.fromisoformat(cfg.FREEZE_DATE)
cal = lake.query(
    "SELECT cal_date FROM trade_cal WHERE is_open = 1 AND cal_date <= ? ORDER BY cal_date",
    [lake.FREEZE_DATE_COMPACT],
)["cal_date"].tolist()
CAL = [dt.date(int(d[:4]), int(d[4:6]), int(d[6:])) for d in cal]
IDX = {d: i for i, d in enumerate(CAL)}

A = pd.read_parquet(cfg.UNIVERSE_DIR / "index_weight_intervals.parquet")
B = pd.read_parquet(cfg.UNIVERSE_DIR / "qlib_instruments_intervals.parquet")

def d8(s):
    return dt.date(int(s[:4]), int(s[4:6]), int(s[6:]))

def lo_idx(d):  # 第一个 >= d 的交易日下标
    return bisect.bisect_left(CAL, d)

def hi_idx(d):  # 最后一个 <= d 的交易日下标
    return bisect.bisect_right(CAL, d) - 1

def runs(sorted_idx):
    out = []
    for i in sorted_idx:
        if out and i == out[-1][1] + 1:
            out[-1][1] = i
        else:
            out.append([i, i])
    return [tuple(r) for r in out]

for uni in cfg.UNIVERSES:
    a = A[A.universe == uni]
    b = B[B.universe == uni]
    # 窗口 = 两源交易日覆盖的交集
    a_lo = min(lo_idx(d8(x)) for x in a.in_date)
    a_hi = max(hi_idx(FREEZE if pd.isna(x) else d8(x)) for x in a.out_date)
    b_lo = min(lo_idx(x) for x in b.in_date)
    b_hi = max(hi_idx(x) for x in b.out_date)
    W = (max(a_lo, b_lo), min(a_hi, b_hi))
    print(f"\n===== {uni}  窗口 {CAL[W[0]]} .. {CAL[W[1]]}  ({W[1]-W[0]+1} 交易日)"
          f"  A覆盖[{CAL[a_lo]},{CAL[a_hi]}] B覆盖[{CAL[b_lo]},{CAL[b_hi]}]")
    setA, setB = collections.defaultdict(set), collections.defaultdict(set)
    outA, outB = collections.Counter(), collections.Counter()
    for c, i, o in zip(a.code, a.in_date, a.out_date):
        lo, hi = lo_idx(d8(i)), hi_idx(FREEZE if pd.isna(o) else d8(o))
        for k in range(max(lo, W[0]), min(hi, W[1]) + 1):
            setA[c].add(k)
        for k in range(lo, min(hi, W[0] - 1) + 1):
            outA[c] += 1
        for k in range(max(lo, W[1] + 1), hi + 1):
            outA[c] += 1
    for c, i, o in zip(b.code, b.in_date, b.out_date):
        lo, hi = lo_idx(i), hi_idx(o)
        for k in range(max(lo, W[0]), min(hi, W[1]) + 1):
            setB[c].add(k)
        for k in range(lo, min(hi, W[0] - 1) + 1):
            outB[c] += 1
        for k in range(max(lo, W[1] + 1), hi + 1):
            outB[c] += 1
    inter = union = na = nb = 0
    for c in set(setA) | set(setB):
        sa, sb = setA.get(c, set()), setB.get(c, set())
        inter += len(sa & sb); union += len(sa | sb); na += len(sa); nb += len(sb)
    print(f"成员日: A={na} B={nb} 交={inter} 并={union} Jaccard={inter/union:.6f} 对称差={union-inter}")
    print(f"窗口外成员日: A={sum(outA.values())} B={sum(outB.values())}")
    # 逐日对称差
    perday = collections.Counter()
    dayA, dayB = collections.defaultdict(set), collections.defaultdict(set)
    for c, s in setA.items():
        for k in s: dayA[k].add(c)
    for c, s in setB.items():
        for k in s: dayB[k].add(c)
    exact = 0
    worst = []
    for k in range(W[0], W[1] + 1):
        sd = len(dayA[k] ^ dayB[k])
        perday[sd] += 1
        if sd == 0: exact += 1
        worst.append((sd, CAL[k], len(dayA[k]), len(dayB[k])))
    worst.sort(reverse=True)
    print(f"逐日完全一致的交易日: {exact}/{W[1]-W[0]+1} = {exact/(W[1]-W[0]+1):.4f}")
    print(f"逐日对称差分布(前12): {sorted(perday.items())[:12]}")
    print(f"最差 8 天: {worst[:8]}")
    # 段级(归一化后)
    segA = {c: runs(sorted(s)) for c, s in setA.items() if s}
    segB = {c: runs(sorted(s)) for c, s in setB.items() if s}
    print(f"归一化段数: A={sum(len(v) for v in segA.values())} ({len(segA)} codes)"
          f"  B={sum(len(v) for v in segB.values())} ({len(segB)} codes)")
    print(f"码集: A-only={len(set(segA)-set(segB))} B-only={len(set(segB)-set(segA))} 共有={len(set(segA)&set(segB))}")
