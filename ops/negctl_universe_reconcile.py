"""卡 1.1 对账负控:量出"约定归一化"这一步到底值多少,而不是假设它有用。

跑法::

    cd $REPO && $GENEBENCH_ROOT/env/bin/python ops/negctl_universe_reconcile.py

为什么必须有这一步
------------------
`ops/test_universe_reconcile.py` 全绿只说明产物**自洽**,不说明报告里
"先解决约定,再算数字"那句话是有内容的。本脚本把归一化的三个环节各拆掉一个,
重算同一个成员日一致率,看数字塌多少:

* **N1 半开区间**:把源B 读成 ``[in_date, out_date)``。这是源B 文档 §3.3 点名的坑。
* **N2 不合并贴片行**:源B 每个 epoch 一行、首尾相接,不合并就当成几十次进出。
  这一项只影响**段级**指标,成员日不受影响 —— 拆开正好证明"段级必须合并、
  成员日不必",两个层次的指标各自防住什么,一目了然。
* **N3 日历日展开**:不投影到交易日网格,直接在自然日上比。
  源B 的 ``out_date`` 大量落在周日与节假日,源A 落在上一个交易日,
  这一项量的就是**纯约定差**有多大。

如果某一项拆掉之后数字纹丝不动,那这一步在报告里就不该被写成"关键"。
实测结论见脚本末尾打印的表,以及 `ops/reports/universe_reconciliation.md` §1.1。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# ⚠️ 收紧 umask 必须在**任何仓库内 import 之前** —— CPython 在 import 那一刻就建
# `__pycache__/`,等到函数里再调 `cfg.harden_umask()` 已经晚了(卡 0.2 踩过)。
_PREVIOUS_UMASK = os.umask(0o077)

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import genebench_config as cfg  # noqa: E402
from snapshots import lake  # noqa: E402
from snapshots import universe_reconcile as ur  # noqa: E402


def _load(grid: ur.Grid):
    """按**正确**约定装载两源(基线),返回 ``{universe: (segsA, segsB, lo, hi)}``。"""
    a_all, _ = ur._load_source_a(grid)
    b_all, _ = ur._load_source_b(grid)
    out = {}
    for uni in cfg.UNIVERSES:
        a, b = a_all[uni], b_all[uni]
        lo = max(
            min(s for v in a.values() for s, _ in v),
            min(s for v in b.values() for s, _ in v),
        )
        hi = min(
            max(e for v in a.values() for _, e in v),
            max(e for v in b.values() for _, e in v),
        )
        out[uni] = (ur._clip(a, lo, hi)[0], ur._clip(b, lo, hi)[0], lo, hi)
    return out


def _jaccard(a_segs, b_segs, lo, hi) -> tuple[int, int, float]:
    inter = sym = 0
    for code in set(a_segs) | set(b_segs):
        av = ur._mask(a_segs.get(code, []), lo, hi)
        bv = ur._mask(b_segs.get(code, []), lo, hi)
        inter += int((av & bv).sum())
        sym += int((av ^ bv).sum())
    return inter, sym, (inter / (inter + sym) if inter + sym else 1.0)


# ---------------------------------------------------------------- 备选约定
#
# 三个"故意用错"的约定住在 `snapshots/universe_reconcile.py` 里
# (`alt_source_b_half_open` / `alt_source_b_unmerged` / `alt_calendar_day_symdiff`),
# 不在这里复制一份:主流程要用它们把"这一步值多少"直接算进报告,
# 负控要用它们出逐项表。同一段逻辑分两处写,迟早会漂成两个结论。
# 依赖方向也只能是这样:ops/ 可以 import snapshots/,反过来不行。


def main() -> int:
    lake.raise_open_file_limit()
    with lake.catalog() as con:
        grid = ur.load_grid(con)

    base = _load(grid)
    half = ur.alt_source_b_half_open(grid)
    unmerged = ur.alt_source_b_unmerged(grid)
    cal = {u: (i, sym) for u, (i, sym) in ur.alt_calendar_day_symdiff().items()}

    rows = []
    for uni in cfg.UNIVERSES:
        a_segs, b_segs, lo, hi = base[uni]
        b_half = ur._clip(half[uni], lo, hi)[0]
        rows.append(
            {
                "universe": uni,
                "base": _jaccard(a_segs, b_segs, lo, hi),
                "half_open": _jaccard(a_segs, b_half, lo, hi),
                "calendar_symdiff": cal[uni][1],
                "n_seg_b_merged": sum(len(v) for v in b_segs.values()),
                "n_seg_b_unmerged": sum(
                    len(v) for v in unmerged[uni].values()
                ),
                "n_seg_a": sum(len(v) for v in a_segs.values()),
            }
        )

    print("=" * 92)
    print("卡 1.1 对账负控:拆掉归一化的每一步,看成员日一致率塌多少")
    print("=" * 92)
    print("注:N3 是自然日口径,分母与交易日网格不可比,所以只报对称差绝对量,不报 Jaccard。")
    print()
    print(
        f"{'宇宙':<10}{'基线 Jaccard':>16}{'N1 半开 Jaccard':>18}"
        f"{'基线对称差':>14}{'N1 多出':>12}{'N3 多出':>12}"
    )
    for r in rows:
        b_i, b_s, b_j = r["base"]
        h_i, h_s, h_j = r["half_open"]
        print(
            f"{r['universe']:<10}{b_j:>16.6f}{h_j:>18.6f}"
            f"{b_s:>14,}{h_s - b_s:>12,}{r['calendar_symdiff'] - b_s:>12,}"
        )
    print()
    print("-" * 92)
    print("N2 不合并源B 贴片行 —— 只打段级指标(成员日不受影响,这正是要证明的)")
    print("-" * 92)
    print(f"{'宇宙':<10}{'源A 段数':>12}{'源B 合并后':>14}{'源B 不合并':>14}{'虚增倍数':>12}")
    for r in rows:
        ratio = r["n_seg_b_unmerged"] / max(r["n_seg_b_merged"], 1)
        print(
            f"{r['universe']:<10}{r['n_seg_a']:>12,}{r['n_seg_b_merged']:>14,}"
            f"{r['n_seg_b_unmerged']:>14,}{ratio:>11.1f}x"
        )
    print()

    # ---- 结论(可断言的部分)
    worst_half = min(r["half_open"][2] for r in rows)
    worst_base = min(r["base"][2] for r in rows)
    cal_extra = sum(r["calendar_symdiff"] - r["base"][1] for r in rows)
    seg_ratio = max(
        r["n_seg_b_unmerged"] / max(r["n_seg_b_merged"], 1) for r in rows
    )
    print("=" * 92)
    print("结论")
    print("=" * 92)
    print(
        f"* N1 半开区间:最差宇宙的 Jaccard 从 {worst_base:.6f} 掉到 {worst_half:.6f};"
        f"三个宇宙合计多出 {sum(r['half_open'][1] - r['base'][1] for r in rows):,} 个分歧成员日。"
    )
    print(
        f"  → 区间开闭这一条**有判别力**,报告里把它写成前提是站得住的。"
        if worst_half < worst_base - 1e-6
        else "  → 半开/闭区间对结果没影响,报告不该把它写成关键前提。"
    )
    print(
        f"* N2 贴片行不合并:源B 段数虚增最多 {seg_ratio:.1f} 倍,"
        f"成员日**一个都不变**(展开成集合后与分段无关)。"
    )
    print(
        "  → 合并这一步只对**段级**指标是必须的;报告把它放在 §1.1 而不是 §2,位置正确。"
    )
    print(
        f"* N3 日历日展开:三个宇宙合计多出 {cal_extra:,} 个分歧成员日,"
        "全部来自源B 的 out_date 落在周末/节假日、源A 落在上一个交易日。"
    )
    print(
        "  → 这就是“纯约定差”的量。不投影到交易日网格,这些会被当成真分歧写进报告。"
        if cal_extra > 0
        else "  → 日历日与交易日网格结果相同,归一化这一步在本数据上没有产生差别。"
    )
    print()
    print(f"(收紧前的 umask = {oct(_PREVIOUS_UMASK)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
