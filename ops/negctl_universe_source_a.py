"""卡 1.1 源A 负控:量出验收测试对"约定选错"的**区分力**,而不是假设它有。

跑法::

    cd $REPO && $GENEBENCH_ROOT/env/bin/python ops/negctl_universe_source_a.py

为什么必须有这一步
------------------
`ops/test_universe_source_a.py` 全绿只说明"产物自洽",不说明"判据管用"。
本脚本用**两种明确错误的约定**重算一遍区间,再拿验收测试的两条主判据去量:

* 备选①:``out_date = 最后一次出现的那期 T_j``(内近似)
* 备选②:``in_date = 上一期的次日``(提前建仓)

实测结论(写进了测试的 docstring):

* **快照日判据对三种约定一视同仁,全是 0 失败** —— 它管切段与截断,
  **管不住约定**。不把这条写明白,它就是个假绿。
* **月中判据是唯一分得开的**:两种错约定都被大面积抓住。

所以"改 in/out 约定"的正确姿势是:先跑本脚本看新约定在月中判据下是什么样,
再决定改不改 —— 而不是改完看见 36 个绿点就放心。
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict
from pathlib import Path

# ⚠️ 收紧 umask 必须在**任何仓库内 import 之前** —— CPython 在 import 那一刻
# 就建 `__pycache__/`,等到函数里再调 `cfg.harden_umask()` 已经晚了,
# 目录会带着本机的 002 umask 落成 0775,踩红卡 0.1 的递归权限审计。
# 卡 0.2 的 builder 真踩过一次;这三行是它定下的写法。
_PREVIOUS_UMASK = os.umask(0o077)

# 仓库根 = 本文件的上一级(ops/ 的父目录)。相对推导,不写绝对路径字面量 ——
# 唯一配置入口是 `genebench_config`,而它本身就在仓库根上。
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import genebench_config as cfg  # noqa: E402
from snapshots import lake  # noqa: E402

assert 0o077 == cfg.REQUIRED_UMASK, (
    f"硬写的 umask 0o077 与 cfg.REQUIRED_UMASK={oct(cfg.REQUIRED_UMASK)} 漂移了"
)

lake.raise_open_file_limit()
with lake.catalog() as con:
    raw = lake.query(
        "SELECT index_code, con_code, trade_date FROM index_weight WHERE trade_date <= ?",
        [lake.FREEZE_DATE_COMPACT],
        conn=con,
    )
    cal = lake.query(
        "SELECT cal_date FROM trade_cal WHERE is_open = 1 AND cal_date <= ? ORDER BY 1",
        [lake.FREEZE_DATE_COMPACT],
        conn=con,
    )["cal_date"].tolist()

prev_td = {cur: prv for prv, cur in zip(cal, cal[1:])}
members: dict[str, dict[str, set]] = {u: defaultdict(set) for u in cfg.UNIVERSES}
for ic, code, td in zip(raw["index_code"], raw["con_code"], raw["trade_date"]):
    members[cfg.INDEX_CODE_UNIVERSE[ic]][td].add(code)
dates = {u: sorted(members[u]) for u in cfg.UNIVERSES}

OPEN = "99999999"


def build(variant: str):
    """variant: 'chosen' | 'out_is_last_seen' | 'in_is_prev_plus_one'"""
    rows = []
    for uni in cfg.UNIVERSES:
        ds = dates[uni]
        pos = {d: i for i, d in enumerate(ds)}
        seen = defaultdict(list)
        for d in ds:
            for c in members[uni][d]:
                seen[c].append(pos[d])
        for code, idxs in seen.items():
            idxs.sort()
            runs, start, prev = [], idxs[0], idxs[0]
            for i in idxs[1:]:
                if i == prev + 1:
                    prev = i
                    continue
                runs.append((start, prev))
                start = prev = i
            runs.append((start, prev))
            for i, j in runs:
                in_d = ds[i]
                out_d = None if j == len(ds) - 1 else prev_td[ds[j + 1]]
                if variant == "out_is_last_seen":
                    out_d = None if j == len(ds) - 1 else ds[j]
                if variant == "in_is_prev_plus_one" and i > 0:
                    # "上一期的次日"（下一个交易日）
                    k = cal.index(ds[i - 1])
                    in_d = cal[k + 1]
                rows.append((uni, code, in_d, out_d or OPEN))
    return rows


def midmonth_check(rows, label):
    """与 test_universe_between_snapshots_* 同一判据。"""
    by_uni = defaultdict(list)
    for uni, code, a, b in rows:
        by_uni[uni].append((code, a, b))
    next_td = {p_: c_ for p_, c_ in zip(cal, cal[1:])}
    prev_td_ = {c_: p_ for p_, c_ in zip(cal, cal[1:])}
    bad_total = 0
    for uni in cfg.UNIVERSES:
        ds = dates[uni]
        snap = set(ds)
        probe = sorted(
            {
                d
                for cur, nxt in zip(ds, ds[1:])
                for d in (next_td.get(cur), prev_td_.get(nxt))
                if d and d not in snap
            }
        )
        sample = probe
        segs = by_uni[uni]
        bad = 0
        for day in sample:
            last = max(d for d in ds if d <= day)
            got = frozenset(c for c, a, b in segs if a <= day <= b)
            if got != members[uni][last]:
                bad += 1
        bad_total += bad
        print(f"  [{label}] {uni:8s} 月中重建对不上的天数 {bad}/{len(sample)}")
    return bad_total


def snapshot_check(rows, label):
    """与 test_pit_reconstruction_* 同一判据。"""
    by_uni = defaultdict(list)
    for uni, code, a, b in rows:
        by_uni[uni].append((code, a, b))
    bad_total = 0
    for uni in cfg.UNIVERSES:
        segs = by_uni[uni]
        bad = sum(
            1
            for day in dates[uni]
            if frozenset(c for c, a, b in segs if a <= day <= b) != members[uni][day]
        )
        bad_total += bad
        print(f"  [{label}] {uni:8s} 快照期对不上的期数 {bad}/{len(dates[uni])}")
    return bad_total


print("=== 本卡所选约定（in=T_i, out=prev_trading_day(T_{j+1})）===")
chosen = build("chosen")
a1 = snapshot_check(chosen, "chosen")
a2 = midmonth_check(chosen, "chosen")

print("=== 备选①：out_date = 最后一次出现的那期 T_j ===")
alt1 = build("out_is_last_seen")
b1 = snapshot_check(alt1, "alt-out")
b2 = midmonth_check(alt1, "alt-out")

print("=== 备选②：in_date = 上一期的次日 ===")
alt2 = build("in_is_prev_plus_one")
c1 = snapshot_check(alt2, "alt-in")
c2 = midmonth_check(alt2, "alt-in")

print()
print(f"chosen  : 快照失败 {a1}  月中失败 {a2}   -> 期望 0 / 0")
print(f"alt-out : 快照失败 {b1}  月中失败 {b2}   -> 期望 0 / >0（月中宇宙缩水）")
print(f"alt-in  : 快照失败 {c1}  月中失败 {c2}   -> 期望 0 / >0（提前一个月建仓）")
print()
print("结论① 快照日判据对三种约定一视同仁（都是 0）——"
      " 它管的是切段与截断，**管不住约定**，这条必须写进测试 docstring，否则是假绿。")
print("结论② 月中判据是唯一分得开的：两种错约定都被抓住。")
ok = a1 == 0 and a2 == 0 and b1 == 0 and b2 > 0 and c1 == 0 and c2 > 0
print("负控结论:", "PASS(月中判据有区分力,快照判据的局限已如实记录)"
      if ok else "FAIL(测试抓不住错约定)")
sys.exit(0 if ok else 1)
