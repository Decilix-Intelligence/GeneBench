"""卡 1.1 对账:源A(index_weight 月末 diff) vs 源B(qlib instruments)。

输入
----
* 源A 产物 ``cfg.UNIVERSE_DIR / index_weight_intervals.parquet``
  —— 湖 ``index_weight`` 月末快照相邻期 diff 推出的成分区间(字符串 ``YYYYMMDD``,
  ``out_date`` 为 NULL 表示右删失)。
* 源B 产物 ``cfg.UNIVERSE_DIR / qlib_instruments_intervals.parquet``
  —— qlib community instruments 解析出的成分区间(``date32``,闭日历区间,
  ``out_date == cfg.FREEZE_DATE`` 表示右删失)。
* 湖 ``trade_cal``(只读):交易日网格。
* 湖 ``stock_basic``(只读):``delist_date`` / ``name``,用于分歧归因与人读清单。

产出
----
* ``cfg.REPORTS / universe_reconciliation.md`` —— 给人看的对账报告(会被原样贴出去)。
* ``cfg.OPS / universe_reconciliation.json`` —— 机器可读版。

方法(三步,顺序不能换)
----------------------
**第一步:先解决约定,再算数字。** 两源的区间约定不同,直接比大小得到的全是垃圾:

===============  ==============================  ==============================
                 源A                              源B
===============  ==============================  ==============================
日期类型          字符串 ``YYYYMMDD``              ``datetime.date``
``in_date``      首次观测到在成分内的**快照日**    成分调整**生效日**
``out_date``     ``prev_trading_day(下一期快照)``  ``下一期生效日 − 1 **日历**天``
右删失            ``out_date IS NULL``            ``out_date == FREEZE_DATE``
端点日类型        两端都是交易日                    ``in`` 是交易日,``out`` 不保证
一 code 多段      真·多段(中间确实不在成分内)       **贴片式**:每个 epoch 一行,
                                                  相邻行首尾相接,不合并
===============  ==============================  ==============================

归一化(`_to_grid` / `_merge_touching`):把两源都投影到**交易日网格**上的闭区间

  * ``in`` → 不早于它的第一个交易日;``out`` → 不晚于它的最后一个交易日;
  * 源A 的 NULL ``out_date`` 按右删失填 ``FREEZE_DATE``;
  * **相邻段合并**:两段之间若不含任何交易日就并成一段。这一步把源B 的贴片行
    还原成真正的成分段(csi300 16 198 行 → 约 1 000 段),也顺手消化了
    "源B 的 ``out_date`` 落在周日、源A 落在上周五"这种纯约定差。

归一化之后两源是**同一种对象**:交易日网格上的闭区间集合。此后所有比较都在网格上做,
边界差的单位是**交易日**,不是日历天 —— 日历天会把周末和长假算进偏差里。

**第二步:只在重叠窗口内比。** 每个宇宙的窗口
``[max(min_in_A, min_in_B), min(max_out_A, max_out_B)]``。窗口外的区间单独统计,
不计入分歧。两源都已被冻结线截到 ``cfg.FREEZE_DATE``,所以右端一律是冻结线;
左端由源A 决定(湖 ``index_weight`` 从 2009-01 起,csi1000 从 2014-10 起)。

**第三步:两个层次分别算。**

(a) **成员日一致率**(最硬的指标):把区间按 ``trade_cal`` 展开成 ``(code, 交易日)``
    集合,算 Jaccard 与逐日对称差。注意这比"只在月末快照日比对"严格得多 ——
    源A 的快照日恰好是两源最容易一致的那些天,分歧几乎全部藏在快照日之间。

(b) **区间段一致率**:抽 ``SAMPLE_SIZE`` 只 code 逐段比 ``in``/``out``。抽样用
    ``sha256(seed|universe|code)`` 排序取前 N(见 `sample_codes`),
    **与 random 库实现、numpy 版本、平台都无关**,给定种子完全可复现。

分歧归因
--------
不堆长表,把每个**分歧区段**(同一 code 在网格上连续的对称差)归到一个类型上,
每类给"区段数 + 成员日数 + 具名例子"。类型与判定顺序见 `RUN_CLASSES` 与 `classify_run`。
成员日按类型求和**恰好等于**总对称差 —— 归因不重不漏是这份报告的可信度基础。

跑法
----
``cd $REPO && $GENEBENCH_ROOT/env/bin/python -m snapshots.universe_reconcile``
"""

from __future__ import annotations

import bisect
import collections
import datetime as dt
import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

import genebench_config as cfg
from snapshots import lake

__all__ = [
    "SAMPLE_SEED",
    "SAMPLE_SIZE",
    "BOUNDARY_TOL_TD",
    "RUN_CLASSES",
    "Grid",
    "alt_source_b_half_open",
    "alt_source_b_unmerged",
    "alt_calendar_day_symdiff",
    "sample_codes",
    "build",
    "main",
]

# --------------------------------------------------------------------------
# 可调参数 —— 全部写进报告,不许悄悄改
# --------------------------------------------------------------------------

#: 抽样种子。取冻结线的数字形态,便于人记忆与复核。
#: 抽样实现是 `sha256(f"{seed}|{universe}|{code}")` 排序取前 N,
#: 不依赖任何随机数发生器,换机器 / 换 numpy 版本结果不变。
SAMPLE_SEED: int = 20260731

#: 每个宇宙抽多少只 code 做逐段比对。实施稿验收原文是"抽 300 只逐段比对",
#: 这里对**每个宇宙**各抽 300 只(合计 900 只),是验收要求的超集。
SAMPLE_SIZE: int = 300

#: 边界差的容忍阈值,单位是**交易日**。
#:
#: 为什么是 23:源A 的分辨率上限就是快照粒度(月末),一个月约 20~23 个交易日。
#: 源B 的 ``in_date`` 是调整**生效日**,源A 最早也要等到生效日之后的第一期月末快照
#: 才看得见 —— 这段滞后是**约定层的系统性偏差,不是数据错误**,不该记成分歧。
#: 超过一个快照周期的偏差就不再能用"月末粒度"解释,必须逐条查。
#:
#: 收口时(卡 1.1)这个常量被提到 `genebench_config`:`snapshots/universe_build.py`
#: 判 `tolerated_boundary_lag` 用的是同一个阈值,两处各写一份必然漂移 ——
#: 一旦漂了,对账报告说"一致"的段和收口表说"一致"的段就不是同一批,
#: 而这种不一致没有任何测试会抓到。这里只保留别名,值由 cfg 定。
BOUNDARY_TOL_TD: int = cfg.BOUNDARY_TOL_TD

#: 判定"源B 的基期缺口"用的阈值:某宇宙在源B 里的成员数低于名义规模的这个比例,
#: 就认为该宇宙在源B 里**还没真正开始**(源B 文档 B-01:csi1000 在 2015-05-29
#: 之前只有 3 个成员)。不硬编码日期,让数据自己说话。
BASE_PERIOD_MIN_FILL: float = 0.5

#: 归因到"退市/吸收合并响应差"时,退市日相对分歧区段的允许位置(日历天)。
#: 退市日可以早于区段起点最多 `LOOKBACK` 天(慢的那一源还没把票摘掉),
#: 或晚于区段终点最多 `LOOKAHEAD` 天(快的那一源提前摘)。
#: 400 天覆盖源B 的半年度格点 + 余量;30 天覆盖"退市前已停牌、指数提前剔除"。
DELIST_LOOKBACK_DAYS: int = 400
DELIST_LOOKAHEAD_DAYS: int = 30

#: 判定两个 code 是"同一实体的前后两个代码"所需的分歧日 **Jaccard** 下限。
#: 用 Jaccard 而不是 ``|X∩Y| / min(|X|,|Y|)``:后者只要一方的分歧日是另一方的子集
#: 就给满分,任何一个短区段都能冒充对家(实测会把三个不相干的码全配到同一只票上)。
CODE_MAP_MIN_JACCARD: float = 0.5

# --------------------------------------------------------------------------
# 产物文件名。**目录**一律走 cfg,文件名留在模块里 —— 与 `snapshots/universe_qlib.py`
# 同一套写法,搬家时只动 `genebench_config._DEFAULT_ROOT` 一行。
# --------------------------------------------------------------------------

_REPORT_NAME = "universe_reconciliation.md"
_SUMMARY_NAME = "universe_reconciliation.json"
_SOURCE_A_NAME = "index_weight_intervals.parquet"
_SOURCE_B_NAME = "qlib_instruments_intervals.parquet"


def _file_sha256(path) -> str:
    """输入文件的内容指纹 —— 抬头据此声明「这份报告是对哪一版快照算的」。"""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def report_path():
    """人读报告路径:``cfg.REPORTS / universe_reconciliation.md``。"""
    return cfg.REPORTS / _REPORT_NAME


def summary_path():
    """机器可读摘要路径:``cfg.OPS / universe_reconciliation.json``。"""
    return cfg.OPS / _SUMMARY_NAME


def source_a_path():
    return cfg.UNIVERSE_DIR / _SOURCE_A_NAME


def source_b_path():
    return cfg.UNIVERSE_DIR / _SOURCE_B_NAME


# --------------------------------------------------------------------------
# 分歧类型
# --------------------------------------------------------------------------

#: 分歧类型表。``key`` 是稳定 ID(进 JSON),``label`` 给人看,``why`` 是判据说明。
#: **判定顺序就是这张表的顺序** —— 前面的类型优先,保证每个分歧区段只落一类,
#: 各类成员日之和恰好等于总对称差。
RUN_CLASSES: tuple[tuple[str, str, str], ...] = (
    (
        "index_base_gap",
        "指数基期缺口(源B 该宇宙尚未真正开始)",
        "源B 在该宇宙的成员数低于名义规模的一半,整段属于上游的伪区间;"
        "源B 文档已登记为 B-01(csi1000 在 2015-05-29 之前只有 3 个成员)。",
    ),
    (
        "code_mapping",
        "代码映射(同一实体、两源用不同 ts_code)",
        "更名 / 吸收合并 / 借壳后代码变更。源A(湖 index_weight)用**当前** ts_code "
        "回溯改写历史,源B(qlib)保留**当时**的旧码,于是同一家公司在两源里是两个代码。"
        "自动配对:一源独有的 code 与另一源同宇宙、同时段的 code,分歧日集合 Jaccard ≥ 50%。",
    ),
    (
        "delist_response",
        "退市 / 吸收合并的响应差",
        "该 code 在湖 stock_basic 里有 delist_date,且退市日落在分歧区段的 "
        "[起点−400 天, 终点+30 天] 内。两源对“票没了”的反应速度不同。",
    ),
    (
        "intra_period_flattened",
        "月内进出被抹平(短命整段只有一方有)",
        "孤立段且长度 ≤ 一个快照周期:一方看得见的一次短暂进出,另一方的网格太粗直接抹平。",
    ),
    (
        "one_side_whole_segment",
        "一方缺整段 / 多一个中间段",
        "分歧区段两侧都不是“两源都在”的状态(孤立段),或两侧都是(中间挖了个洞)—— "
        "不是边界对不齐,是整段的有无之差。",
    ),
    (
        "month_end_lag",
        "月末快照粒度导致的边界差(源A 滞后,在容忍内)",
        "方向是“源A 晚于源B”(源A 尾巴更长 / 头更晚),且偏差 ≤ BOUNDARY_TOL_TD 个交易日。"
        "这是源A 约定的**分辨率上限**,不是数据错误。",
    ),
    (
        "month_end_lag_beyond_tol",
        "边界差超出容忍(源A 滞后 > 一个快照周期)",
        "方向同上但偏差超过一个快照周期 —— 已经不能用月末粒度解释,必须逐条查。",
    ),
    (
        "coarse_epoch_b",
        "源B 换仓格点粗(源A 领先:快速纳入 / 临时调整被源B 漏掉)",
        "方向是“源A 早于源B”。源B 在本窗口里每年只有 2~4 个 epoch,"
        "IPO 快速纳入、退市临时替换这类月内事件会被推迟到下一个半年度格点。",
    ),
    (
        "unclassified",
        "未归类",
        "以上规则都不命中。这一类**必须为 0**,不为 0 说明分类规则漏了情形。",
    ),
)

_CLASS_ORDER: tuple[str, ...] = tuple(k for k, _, _ in RUN_CLASSES)
_CLASS_LABEL: dict[str, str] = {k: v for k, v, _ in RUN_CLASSES}
_CLASS_WHY: dict[str, str] = {k: w for k, _, w in RUN_CLASSES}


# --------------------------------------------------------------------------
# 交易日网格
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Grid:
    """交易日网格。所有区间比较都在这上面做。

    Attributes:
        days: 升序交易日列表(已截到冻结线)。
        index: ``date -> 序号`` 的反查表。
    """

    days: tuple[dt.date, ...]
    index: dict[dt.date, int]

    def floor(self, day: dt.date) -> int | None:
        """不晚于 ``day`` 的最后一个交易日序号;没有就返回 None。"""
        i = bisect.bisect_right(self.days, day) - 1
        return i if i >= 0 else None

    def ceil(self, day: dt.date) -> int | None:
        """不早于 ``day`` 的第一个交易日序号;没有就返回 None。"""
        i = bisect.bisect_left(self.days, day)
        return i if i < len(self.days) else None

    def date(self, i: int) -> dt.date:
        return self.days[i]

    def iso(self, i: int) -> str:
        return self.days[i].isoformat()


def load_grid(conn=None) -> Grid:
    """从湖 ``trade_cal`` 读交易日,截到 ``cfg.FREEZE_DATE``(红线 7)。

    `trade_cal` 只有 SSE 一个交易所(卡 0.2 实测)。A 股两所日历一致,
    本模块也只用它,不做跨所判断 —— 与源A 的口径一致。

    走 `snapshots.lake` 而不是自己 `duckdb.connect`:湖是活的,外部 ETL 的
    瞬时 `.wal` 会让只读打开偶发失败,`lake` 里带重试;而且"全仓库只有 lake
    一处连湖"本身是卡 0.2 立的护栏(`ops/test_lake_baseline.py` 会扫)。

    Args:
        conn: 复用的只读连接;不给就由 `lake` 临时开一个再关掉。
    """
    freeze = dt.date.fromisoformat(cfg.FREEZE_DATE)
    raw = lake.query(
        "SELECT cal_date FROM trade_cal WHERE is_open = 1 ORDER BY cal_date",
        conn=conn,
    )["cal_date"]
    days = []
    for s in raw:
        day = dt.date(int(s[:4]), int(s[4:6]), int(s[6:8]))
        if day <= freeze:
            days.append(day)
    return Grid(tuple(days), {d: i for i, d in enumerate(days)})


# --------------------------------------------------------------------------
# 两源装载 + 归一化
# --------------------------------------------------------------------------

#: 归一化之后的区间:``(起序号, 止序号)``,闭区间,单位是交易日网格序号。
Seg = tuple[int, int]


def _merge_touching(segments: Iterable[Seg]) -> list[Seg]:
    """把网格上相邻/重叠的段并起来。

    判据是"两段之间**不含任何交易日**"(``next.start <= cur.end + 1``),
    不是"日历日相接" —— 后者会把跨周末的真实空档漏掉,前者才是网格语义。

    源B 是贴片式(每个 epoch 一行),这一步是必须的;源A 的相邻段之间至少隔一个
    完整快照周期,这一步对它是恒等变换(代码里会核这一点)。
    """
    out: list[Seg] = []
    for start, end in sorted(segments):
        if out and start <= out[-1][1] + 1:
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((start, end))
    return out


def _load_source_a(grid: Grid) -> tuple[dict[str, dict[str, list[Seg]]], dict]:
    """读源A 并投影到网格。

    Returns:
        ``(segments, diag)``,``segments[universe][code] = [(i0, i1), ...]``。
    """
    freeze = dt.date.fromisoformat(cfg.FREEZE_DATE)
    df = pd.read_parquet(source_a_path())
    diag = {
        "path_relative_to_root": str(source_a_path().relative_to(cfg.GENEBENCH_ROOT)),
        "sha256": _file_sha256(source_a_path()),
        "rows": int(len(df)),
        "n_null_out_date": int(df["out_date"].isna().sum()),
        "date_form": "字符串 YYYYMMDD;out_date IS NULL = 右删失",
    }
    segments: dict[str, dict[str, list[Seg]]] = collections.defaultdict(
        lambda: collections.defaultdict(list)
    )
    dropped = 0
    for row in df.itertuples(index=False):
        in_day = dt.date(
            int(row.in_date[:4]), int(row.in_date[4:6]), int(row.in_date[6:8])
        )
        if isinstance(row.out_date, str):
            out_day = dt.date(
                int(row.out_date[:4]), int(row.out_date[4:6]), int(row.out_date[6:8])
            )
        else:  # 右删失:开口区间,按冻结线收口(不是"当天被调出")
            out_day = freeze
        i0, i1 = grid.ceil(in_day), grid.floor(out_day)
        if i0 is None or i1 is None or i1 < i0:
            dropped += 1
            continue
        segments[row.universe][row.code].append((i0, i1))
    merged_away = 0
    result: dict[str, dict[str, list[Seg]]] = {}
    for uni, per_code in segments.items():
        result[uni] = {}
        for code, segs in per_code.items():
            merged = _merge_touching(segs)
            merged_away += len(segs) - len(merged)
            result[uni][code] = merged
    diag["n_rows_dropped_off_grid"] = dropped
    # 源A 的相邻段之间至少隔一个完整快照周期,合并应当是恒等变换。
    diag["n_segments_merged_away"] = merged_away
    diag["merge_is_noop"] = merged_away == 0
    return result, diag


def _load_source_b(grid: Grid) -> tuple[dict[str, dict[str, list[Seg]]], dict]:
    """读源B、只取源A 也有的三个宇宙,投影到网格并**合并贴片行**。"""
    df = pd.read_parquet(source_b_path())
    total_rows = int(len(df))
    df = df[df["universe"].isin(cfg.UNIVERSES)]
    diag = {
        "path_relative_to_root": str(source_b_path().relative_to(cfg.GENEBENCH_ROOT)),
        "sha256": _file_sha256(source_b_path()),
        "rows_all_universes": total_rows,
        "rows_in_compared_universes": int(len(df)),
        "universes_ignored": sorted(
            set(pd.read_parquet(source_b_path(), columns=["universe"])["universe"])
            - set(cfg.UNIVERSES)
        ),
        "date_form": f"date32;out_date == {cfg.FREEZE_DATE} = 右删失",
    }
    segments: dict[str, dict[str, list[Seg]]] = collections.defaultdict(
        lambda: collections.defaultdict(list)
    )
    dropped = 0
    for row in df.itertuples(index=False):
        i0, i1 = grid.ceil(row.in_date), grid.floor(row.out_date)
        if i0 is None or i1 is None or i1 < i0:
            dropped += 1
            continue
        segments[row.universe][row.code].append((i0, i1))
    raw_rows = 0
    merged_rows = 0
    result: dict[str, dict[str, list[Seg]]] = {}
    for uni, per_code in segments.items():
        result[uni] = {}
        for code, segs in per_code.items():
            merged = _merge_touching(segs)
            raw_rows += len(segs)
            merged_rows += len(merged)
            result[uni][code] = merged
    diag["n_rows_dropped_off_grid"] = dropped
    diag["n_rows_on_grid"] = raw_rows
    diag["n_segments_after_merge"] = merged_rows
    diag["merge_note"] = (
        "源B 是贴片式:同一 code 在每个 epoch 各占一行,相邻行首尾相接。"
        "不合并就会把“一直在成分内”读成几十次进出,段数完全没有可比性。"
    )
    return result, diag


def _native_spans(window: dict[str, tuple[str, str]]) -> dict[str, dict]:
    """两源在**原始日历上**的覆盖跨度,以及落在重叠窗口之外的存量。

    刻意读原始 parquet 而不是复用投影后的段:湖 `trade_cal` 只从 2009-01-05 起,
    源B 的 2005~2008 段一旦投影到网格,左端就会被夹成 2009-01-05,
    报告里就会写出"源B 从 2009 年开始"这种假话。**窗口外的东西必须用原始日期报。**

    Args:
        window: ``{universe: (窗口起, 窗口止)}``,ISO 日期字符串。
    """
    freeze = dt.date.fromisoformat(cfg.FREEZE_DATE)
    a = pd.read_parquet(source_a_path())
    b = pd.read_parquet(source_b_path())
    b = b[b["universe"].isin(cfg.UNIVERSES)]
    out: dict[str, dict] = {}
    for uni in cfg.UNIVERSES:
        sa = a[a["universe"] == uni]
        sb = b[b["universe"] == uni]
        a_in = pd.to_datetime(sa["in_date"], format="%Y%m%d").dt.date
        a_out = pd.to_datetime(sa["out_date"], format="%Y%m%d").dt.date
        w_lo = dt.date.fromisoformat(window[uni][0])
        w_hi = dt.date.fromisoformat(window[uni][1])
        before = sb["out_date"] < w_lo
        codes_before = set(sb.loc[before, "code"])
        codes_inside = set(sb.loc[~before, "code"])
        out[uni] = {
            "source_a": [
                a_in.min().isoformat(),
                (freeze if sa["out_date"].isna().any() else a_out.max()).isoformat(),
            ],
            "source_b": [
                sb["in_date"].min().isoformat(),
                sb["out_date"].max().isoformat(),
            ],
            "outside": {
                "window": [window[uni][0], window[uni][1]],
                "source_a_rows_entirely_outside": int(
                    ((a_in > w_hi) | (a_out < w_lo)).sum()
                ),
                "source_b_rows_entirely_before_window": int(before.sum()),
                "source_b_codes_seen_only_before_window": len(
                    codes_before - codes_inside
                ),
                "source_b_calendar_days_before_window": (
                    w_lo - dt.date.fromisoformat(sb["in_date"].min().isoformat())
                ).days,
                "note": (
                    "窗口外的差异按要求不计入分歧。湖 trade_cal 只从 2009-01-05 起,"
                    "源B 的窗口前区段没有交易日网格可展开,这里只报原始行数、"
                    "只在窗口前出现过的代码数与日历天数,不折算成员日 —— 折不出来就不编。"
                ),
            },
        }
    return out


def _clip(
    segments: dict[str, list[Seg]], lo: int, hi: int
) -> tuple[dict[str, list[Seg]], int]:
    """把某宇宙的所有段夹到窗口 ``[lo, hi]``,返回 ``(夹后段, 被整段丢掉的段数)``。"""
    out: dict[str, list[Seg]] = {}
    dropped = 0
    for code, segs in segments.items():
        kept = []
        for s, e in segs:
            s2, e2 = max(s, lo), min(e, hi)
            if s2 <= e2:
                kept.append((s2, e2))
            else:
                dropped += 1
        if kept:
            out[code] = _merge_touching(kept)
    return out, dropped


# --------------------------------------------------------------------------
# 抽样(固定种子,与随机数发生器无关)
# --------------------------------------------------------------------------


def alt_source_b_half_open(grid: Grid) -> dict[str, dict[str, list[Seg]]]:
    """**故意用错的**约定:把源B 读成 ``[in_date, out_date)`` —— 右端不含。

    这是源B 文档 §3.3 点名的坑。放在这里不是给主流程用的,是给
    `ops/negctl_universe_reconcile.py` 量判别力用,顺便让 `build()` 能把
    "拆掉这一步会多出多少假分歧"直接算进报告 —— 手抄进文档的数字会漂。
    """
    df = pd.read_parquet(source_b_path())
    df = df[df["universe"].isin(cfg.UNIVERSES)]
    segs: dict[str, dict[str, list[Seg]]] = collections.defaultdict(
        lambda: collections.defaultdict(list)
    )
    for row in df.itertuples(index=False):
        i0 = grid.ceil(row.in_date)
        j = bisect.bisect_left(grid.days, row.out_date) - 1  # 严格早于 out_date
        if i0 is None or j < 0 or j < i0:
            continue
        segs[row.universe][row.code].append((i0, j))
    return {u: {c: _merge_touching(v) for c, v in per.items()} for u, per in segs.items()}


def alt_source_b_unmerged(grid: Grid) -> dict[str, dict[str, list[Seg]]]:
    """**故意用错的**约定:保留源B 的贴片行,不合并相邻段。"""
    df = pd.read_parquet(source_b_path())
    df = df[df["universe"].isin(cfg.UNIVERSES)]
    segs: dict[str, dict[str, list[Seg]]] = collections.defaultdict(
        lambda: collections.defaultdict(list)
    )
    for row in df.itertuples(index=False):
        i0, i1 = grid.ceil(row.in_date), grid.floor(row.out_date)
        if i0 is None or i1 is None or i1 < i0:
            continue
        segs[row.universe][row.code].append((i0, i1))
    return segs


def alt_calendar_day_symdiff() -> dict[str, tuple[int, int]]:
    """**故意用错的**约定:不投影到交易日网格,直接在自然日上展开两源。

    Returns:
        ``{universe: (交集自然日数, 对称差自然日数)}``。

    注意:自然日的 Jaccard **不能**和交易日网格的 Jaccard 比大小 —— 分母不是一回事
    (自然日把周末也算进交集,分母被撑大)。有意义的只有**对称差的绝对量**。
    """
    freeze = dt.date.fromisoformat(cfg.FREEZE_DATE)
    a = pd.read_parquet(source_a_path())
    b = pd.read_parquet(source_b_path())
    b = b[b["universe"].isin(cfg.UNIVERSES)]
    a = a.assign(
        in_d=pd.to_datetime(a["in_date"], format="%Y%m%d").dt.date,
        out_d=pd.to_datetime(a["out_date"], format="%Y%m%d").dt.date,
    )
    a["out_d"] = a["out_d"].where(a["out_date"].notna(), freeze)
    out: dict[str, tuple[int, int]] = {}
    for uni in cfg.UNIVERSES:
        sa, sb = a[a["universe"] == uni], b[b["universe"] == uni]
        lo = max(sa["in_d"].min(), sb["in_date"].min())
        n = (freeze - lo).days + 1
        masks: dict[str, np.ndarray] = {}

        def slot(code: str) -> np.ndarray:
            if code not in masks:
                masks[code] = np.zeros((2, n), dtype=bool)
            return masks[code]

        for r in sa.itertuples(index=False):
            s, e = max(r.in_d, lo), min(r.out_d, freeze)
            if s <= e:
                slot(r.code)[0, (s - lo).days : (e - lo).days + 1] = True
        for r in sb.itertuples(index=False):
            s, e = max(r.in_date, lo), min(r.out_date, freeze)
            if s <= e:
                slot(r.code)[1, (s - lo).days : (e - lo).days + 1] = True
        inter = sum(int((m[0] & m[1]).sum()) for m in masks.values())
        sym = sum(int((m[0] ^ m[1]).sum()) for m in masks.values())
        out[uni] = (inter, sym)
    return out


def sample_codes(codes: Iterable[str], universe: str, n: int, seed: int) -> list[str]:
    """可复现抽样:按 ``sha256(f"{seed}|{universe}|{code}")`` 排序取前 ``n``。

    刻意**不用** ``random`` / ``numpy.random``:那些实现随版本可变,
    "换台机器重跑抽到别的 300 只"会让这份报告的签字失去意义。
    sha256 在任何平台任何版本都是同一个数,给定种子结果完全确定。

    Args:
        codes: 候选 code 全集。
        universe: 参与哈希,保证不同宇宙抽到不同的 300 只(否则三份报告在看同一批票)。
        n: 抽样数量;候选不足时全取。
        seed: 随机种子,写进报告。

    Returns:
        升序排列的 code 列表(排序只为可读,选谁与顺序无关)。
    """
    pool = sorted(set(codes))
    if len(pool) <= n:
        return pool
    ranked = sorted(
        pool,
        key=lambda c: hashlib.sha256(f"{seed}|{universe}|{c}".encode()).hexdigest(),
    )
    return sorted(ranked[:n])


# --------------------------------------------------------------------------
# 成员日展开
# --------------------------------------------------------------------------


def _mask(segs: Sequence[Seg], lo: int, hi: int) -> np.ndarray:
    m = np.zeros(hi - lo + 1, dtype=bool)
    for s, e in segs:
        m[s - lo : e - lo + 1] = True
    return m


@dataclass
class Run:
    """一个**分歧区段**:同一 code 在网格上连续的一串对称差日。"""

    universe: str
    code: str
    side: str  # "A" = 只有源A 有;"B" = 只有源B 有
    i0: int
    i1: int
    kind: str  # lead / trail / hole / isolated
    other_has_code_in_universe: bool
    code_in_other_source_at_all: bool
    cls: str = "unclassified"
    note: str = ""
    partner: str | None = None

    @property
    def n_td(self) -> int:
        return self.i1 - self.i0 + 1


def _runs_for_code(
    universe: str,
    code: str,
    a_segs: Sequence[Seg],
    b_segs: Sequence[Seg],
    lo: int,
    hi: int,
    a_has_code: bool,
    b_has_code: bool,
    code_in_a_anywhere: bool,
    code_in_b_anywhere: bool,
) -> list[Run]:
    av = _mask(a_segs, lo, hi)
    bv = _mask(b_segs, lo, hi)
    diff = av ^ bv
    if not diff.any():
        return []
    both = av & bv
    n = hi - lo + 1
    idx = np.flatnonzero(diff)
    brk = np.flatnonzero(np.diff(idx) > 1)
    starts = np.concatenate(([0], brk + 1))
    ends = np.concatenate((brk, [len(idx) - 1]))
    runs: list[Run] = []
    for s_, e_ in zip(starts, ends):
        p0, p1 = int(idx[s_]), int(idx[e_])
        left = bool(both[p0 - 1]) if p0 > 0 else False
        right = bool(both[p1 + 1]) if p1 < n - 1 else False
        if left and right:
            kind = "hole"
        elif right:
            kind = "lead"  # 区段之后两源都在 → 这是"入场边界"的差
        elif left:
            kind = "trail"  # 区段之前两源都在 → 这是"出场边界"的差
        else:
            kind = "isolated"
        side = "A" if av[p0] else "B"
        runs.append(
            Run(
                universe=universe,
                code=code,
                side=side,
                i0=p0 + lo,
                i1=p1 + lo,
                kind=kind,
                other_has_code_in_universe=(b_has_code if side == "A" else a_has_code),
                code_in_other_source_at_all=(
                    code_in_b_anywhere if side == "A" else code_in_a_anywhere
                ),
            )
        )
    return runs


# --------------------------------------------------------------------------
# 分歧归因
# --------------------------------------------------------------------------


def _detect_base_period(
    b_segs: dict[str, list[Seg]], universe: str, lo: int, hi: int
) -> tuple[int | None, int]:
    """找源B 在该宇宙的"基期缺口"终点。

    做法:逐日数源B 的成员数,找**第一个**达到名义规模 ``BASE_PERIOD_MIN_FILL`` 的交易日。
    在那之前源B 的名单是上游的伪区间(源B 文档 B-01),不该当成"源A 多出来的票"。

    Returns:
        ``(第一个达标日的网格序号 或 None, 缺口起点那天源B 的成员数)``。
        窗口一开始就达标时返回 ``(lo, 成员数)``。
    """
    nominal = cfg.UNIVERSE_NOMINAL_SIZE[universe]
    counts = np.zeros(hi - lo + 1, dtype=np.int32)
    for segs in b_segs.values():
        for s, e in segs:
            counts[s - lo : e - lo + 1] += 1
    ok = np.flatnonzero(counts >= nominal * BASE_PERIOD_MIN_FILL)
    if len(ok) == 0:
        return None, int(counts[0])
    return int(ok[0]) + lo, int(counts[0])


def _detect_code_mapping(
    runs: list[Run], grid: Grid, base_period_end: dict[str, int | None]
) -> tuple[dict[tuple[str, str], str], list[dict]]:
    """自动配对"同一实体的前后两个代码"。

    线索:某个 code 只在一源里出现(另一源全库都没有),而另一源在**同一宇宙、
    同一时段**恰好独有另一个 code。更名 / 吸收合并 / 借壳换码就是这个形状 ——
    源A(湖 index_weight)用**当前** ts_code 回溯改写历史,源B(qlib)保留当时的旧码。

    判据:两个 code 的分歧日集合 **Jaccard** ``|X∩Y| / |X∪Y| >= CODE_MAP_MIN_JACCARD``。
    刻意不用 ``|X∩Y| / min(|X|,|Y|)`` —— 那个只要一方是另一方的子集就给满分,
    随便一个短区段都能冒充对家。

    落在源B 基期缺口里的区段**不参与配对**:那一整段源B 几乎是空的,任何 code 都会跟
    任何 code "高度重合",配出来的全是假的。

    Returns:
        ``({(universe, code): 对家 code}, 配对明细列表)``。
    """

    def in_base_gap(r: Run) -> bool:
        end = base_period_end.get(r.universe)
        return end is not None and r.i1 < end

    runs = [r for r in runs if not in_base_gap(r)]
    days: dict[tuple[str, str, str], set[int]] = collections.defaultdict(set)
    for r in runs:
        days[(r.universe, r.side, r.code)].update(range(r.i0, r.i1 + 1))

    orphan_a = sorted(
        {(u, c) for (u, s, c) in days if s == "A"}
        & {
            (r.universe, r.code)
            for r in runs
            if r.side == "A" and not r.code_in_other_source_at_all
        }
    )
    orphan_b = sorted(
        {(u, c) for (u, s, c) in days if s == "B"}
        & {
            (r.universe, r.code)
            for r in runs
            if r.side == "B" and not r.code_in_other_source_at_all
        }
    )

    mapping: dict[tuple[str, str], str] = {}
    detail: list[dict] = []
    # 孤儿码可能在任一侧;对家不要求也是孤儿(例:源A 的新码在源B 的别的宇宙里存在)。
    for orphan_side, orphans in (("A", orphan_a), ("B", orphan_b)):
        other_side = "B" if orphan_side == "A" else "A"
        for uni, code in orphans:
            mine = days[(uni, orphan_side, code)]
            best: tuple[float, str] | None = None
            for (u2, s2, c2), theirs in days.items():
                if u2 != uni or s2 != other_side or not theirs:
                    continue
                ov = len(mine & theirs) / len(mine | theirs)
                if best is None or ov > best[0]:
                    best = (ov, c2)
            if best is not None and best[0] >= CODE_MAP_MIN_JACCARD:
                mapping[(uni, code)] = best[1]
                mapping[(uni, best[1])] = code
                span = sorted(mine | days[(uni, other_side, best[1])])
                detail.append(
                    {
                        "universe": uni,
                        "only_in_source": orphan_side,
                        "code_only_in_that_source": code,
                        "counterpart_code_in_other_source": best[1],
                        "day_set_jaccard": round(best[0], 4),
                        "disagreement_span": [grid.iso(span[0]), grid.iso(span[-1])],
                        "n_disagreement_td": len(span),
                    }
                )
    detail.sort(key=lambda d: (d["universe"], d["code_only_in_that_source"]))
    return mapping, detail


def classify_run(
    run: Run,
    *,
    base_period_end: dict[str, int | None],
    code_map: dict[tuple[str, str], str],
    delist: dict[str, dt.date],
    grid: Grid,
) -> None:
    """给一个分歧区段定类型(就地写回 ``run.cls`` / ``run.note`` / ``run.partner``)。

    判定顺序 = `RUN_CLASSES` 的顺序,前面的优先。顺序不是随便排的:
    基期缺口和代码映射是**成因明确、与边界精度无关**的整块问题,
    必须先摘出去,否则它们会伪装成"缺整段"把边界统计淹掉。
    """
    # 1. 指数基期缺口
    end = base_period_end.get(run.universe)
    if end is not None and run.side == "A" and run.i1 < end:
        run.cls = "index_base_gap"
        run.note = f"源B 在 {grid.iso(end)} 之前该宇宙未真正开始"
        return

    # 2. 代码映射
    partner = code_map.get((run.universe, run.code))
    if partner is not None:
        run.cls = "code_mapping"
        run.partner = partner
        run.note = f"与另一源的 {partner} 是同一实体"
        return

    # 3. 退市 / 吸收合并响应差
    dl = delist.get(run.code)
    if dl is not None:
        lo_day = grid.date(run.i0) - dt.timedelta(days=DELIST_LOOKBACK_DAYS)
        hi_day = grid.date(run.i1) + dt.timedelta(days=DELIST_LOOKAHEAD_DAYS)
        if lo_day <= dl <= hi_day:
            run.cls = "delist_response"
            run.note = f"delist_date={dl.isoformat()}"
            return

    # 4/5. 整段有无之差
    if run.kind in ("isolated", "hole"):
        if run.kind == "isolated" and run.n_td <= BOUNDARY_TOL_TD:
            run.cls = "intra_period_flattened"
        else:
            run.cls = "one_side_whole_segment"
        return

    # 6/7/8. 边界差 —— 方向是关键
    a_later = (run.side == "A" and run.kind == "trail") or (
        run.side == "B" and run.kind == "lead"
    )
    if a_later:
        run.cls = (
            "month_end_lag"
            if run.n_td <= BOUNDARY_TOL_TD
            else "month_end_lag_beyond_tol"
        )
    else:
        run.cls = "coarse_epoch_b"


# --------------------------------------------------------------------------
# 区间段比对
# --------------------------------------------------------------------------


@dataclass
class SegmentVerdict:
    universe: str
    code: str
    verdict: str
    n_seg_a: int
    n_seg_b: int
    max_abs_in_diff: int | None = None
    max_abs_out_diff: int | None = None
    pairs: list[dict] = field(default_factory=list)


def _compare_segments(
    universe: str,
    code: str,
    a_segs: list[Seg],
    b_segs: list[Seg],
    grid: Grid,
) -> SegmentVerdict:
    """逐段比一只 code。

    段数相同就按时间顺序一一配对(两边都已排序、已合并,且分歧以边界差为主,
    顺序配对就是正确配对);段数不同直接判 ``segment_count_differs`` —— 强行配对
    只会造出好看但没意义的偏差数字。
    """
    v = SegmentVerdict(universe, code, "", len(a_segs), len(b_segs))
    if not a_segs:
        v.verdict = "only_in_source_B"
        return v
    if not b_segs:
        v.verdict = "only_in_source_A"
        return v
    if len(a_segs) != len(b_segs):
        v.verdict = "segment_count_differs"
        return v
    max_in = max_out = 0
    for (a0, a1), (b0, b1) in zip(a_segs, b_segs):
        d_in, d_out = a0 - b0, a1 - b1
        max_in = max(max_in, abs(d_in))
        max_out = max(max_out, abs(d_out))
        v.pairs.append(
            {
                "a_in": grid.iso(a0),
                "a_out": grid.iso(a1),
                "b_in": grid.iso(b0),
                "b_out": grid.iso(b1),
                "in_diff_td": d_in,
                "out_diff_td": d_out,
            }
        )
    v.max_abs_in_diff, v.max_abs_out_diff = max_in, max_out
    worst = max(max_in, max_out)
    if worst == 0:
        v.verdict = "identical"
    elif worst <= BOUNDARY_TOL_TD:
        v.verdict = "within_tolerance"
    else:
        v.verdict = "boundary_beyond_tolerance"
    return v


_SEG_VERDICTS = (
    "identical",
    "within_tolerance",
    "boundary_beyond_tolerance",
    "segment_count_differs",
    "only_in_source_A",
    "only_in_source_B",
)

# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------


def _stock_meta(conn=None) -> tuple[dict[str, str], dict[str, dt.date]]:
    """从湖 ``stock_basic`` 取名称与退市日。

    ``stock_basic`` 是多快照表,同一 ts_code 有多行;按 ``last_seen_at`` 取最新一条。
    只用来给报告加人读信息与做退市归因,不参与任何成员判定。
    """
    df = lake.query(
        "SELECT ts_code, name, delist_date, last_seen_at FROM stock_basic",
        conn=conn,
    )
    df = df.sort_values("last_seen_at").drop_duplicates("ts_code", keep="last")
    names = {r.ts_code: r.name for r in df.itertuples(index=False)}
    delist: dict[str, dt.date] = {}
    for r in df.itertuples(index=False):
        s = r.delist_date
        if isinstance(s, str) and len(s) == 8 and s.isdigit():
            delist[r.ts_code] = dt.date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    return names, delist


def build() -> dict:
    """跑完整对账,返回机器可读结果(也就是写进 JSON 的那个对象)。"""
    cfg.harden_umask()
    lake.raise_open_file_limit()
    with lake.catalog() as con:
        grid = load_grid(con)
        names, delist = _stock_meta(con)

    a_all, a_diag = _load_source_a(grid)
    b_all, b_diag = _load_source_b(grid)
    code_any_a = {c for per in a_all.values() for c in per}
    code_any_b = {c for per in b_all.values() for c in per}

    per_universe: dict[str, dict] = {}
    all_runs: list[Run] = []
    base_period_end: dict[str, int | None] = {}
    seg_verdicts: list[SegmentVerdict] = []
    clipped: dict[str, tuple[dict[str, list[Seg]], dict[str, list[Seg]], int, int]] = {}

    # 先定窗口(两遍走:窗口本身要拿去算"窗口外存量",而后者必须用原始日历日期)
    bounds: dict[str, tuple[int, int]] = {}
    for uni in cfg.UNIVERSES:
        a_segs, b_segs = a_all[uni], b_all[uni]
        a_lo = min(s for segs in a_segs.values() for s, _ in segs)
        a_hi = max(e for segs in a_segs.values() for _, e in segs)
        b_lo = min(s for segs in b_segs.values() for s, _ in segs)
        b_hi = max(e for segs in b_segs.values() for _, e in segs)
        bounds[uni] = (max(a_lo, b_lo), min(a_hi, b_hi))
    native = _native_spans(
        {u: (grid.iso(lo), grid.iso(hi)) for u, (lo, hi) in bounds.items()}
    )

    for uni in cfg.UNIVERSES:
        a_segs, b_segs = a_all[uni], b_all[uni]
        lo, hi = bounds[uni]
        a_win, _ = _clip(a_segs, lo, hi)
        b_win, _ = _clip(b_segs, lo, hi)
        clipped[uni] = (a_win, b_win, lo, hi)

        end, first_count = _detect_base_period(b_win, uni, lo, hi)
        base_period_end[uni] = end if end is not None and end > lo else None

        # ---- (a) 成员日
        n_a = sum(e - s + 1 for segs in a_win.values() for s, e in segs)
        n_b = sum(e - s + 1 for segs in b_win.values() for s, e in segs)
        inter = only_a = only_b = 0
        daily_symdiff = np.zeros(hi - lo + 1, dtype=np.int32)
        for code in set(a_win) | set(b_win):
            av = _mask(a_win.get(code, []), lo, hi)
            bv = _mask(b_win.get(code, []), lo, hi)
            inter += int((av & bv).sum())
            only_a += int((av & ~bv).sum())
            only_b += int((bv & ~av).sum())
            daily_symdiff += (av ^ bv).astype(np.int32)
            runs = _runs_for_code(
                uni,
                code,
                a_win.get(code, []),
                b_win.get(code, []),
                lo,
                hi,
                a_has_code=code in a_win,
                b_has_code=code in b_win,
                code_in_a_anywhere=code in code_any_a,
                code_in_b_anywhere=code in code_any_b,
            )
            all_runs.extend(runs)
        union = inter + only_a + only_b
        n_exact_days = int((daily_symdiff == 0).sum())

        per_universe[uni] = {
            "index_code": cfg.UNIVERSE_INDEX_CODE[uni],
            "nominal_size": cfg.UNIVERSE_NOMINAL_SIZE[uni],
            "window": {
                "start": grid.iso(lo),
                "end": grid.iso(hi),
                "n_trading_days": hi - lo + 1,
                "source_a_native_span": native[uni]["source_a"],
                "source_b_native_span": native[uni]["source_b"],
            },
            "outside_window": native[uni]["outside"],
            "source_b_base_period_gap": (
                None
                if base_period_end[uni] is None
                else {
                    "gap_end_exclusive": grid.iso(base_period_end[uni]),
                    "n_trading_days": base_period_end[uni] - lo,
                    "source_b_member_count_at_window_start": first_count,
                    "note": "源B 在这段里的名单是上游伪区间(源B 文档 B-01),不是源A 多算",
                }
            ),
            "member_day": {
                "n_member_days_source_a": n_a,
                "n_member_days_source_b": n_b,
                "n_intersection": inter,
                "n_union": union,
                "n_only_source_a": only_a,
                "n_only_source_b": only_b,
                "n_symmetric_difference": only_a + only_b,
                "jaccard": round(inter / union, 6) if union else None,
                "n_days_with_zero_symmetric_difference": n_exact_days,
                "pct_days_with_zero_symmetric_difference": round(
                    100.0 * n_exact_days / (hi - lo + 1), 4
                ),
                "mean_symmetric_difference_per_day": round(
                    float(daily_symdiff.mean()), 4
                ),
                "max_symmetric_difference_on_one_day": int(daily_symdiff.max()),
                "worst_day": grid.iso(lo + int(daily_symdiff.argmax())),
            },
            "codes": {
                "n_codes_source_a": len(a_win),
                "n_codes_source_b": len(b_win),
                "n_codes_both": len(set(a_win) & set(b_win)),
                "n_codes_only_a": len(set(a_win) - set(b_win)),
                "n_codes_only_b": len(set(b_win) - set(a_win)),
            },
            "segments": {
                "n_segments_source_a": sum(len(v) for v in a_win.values()),
                "n_segments_source_b": sum(len(v) for v in b_win.values()),
            },
        }

        # 排除基期缺口后的成员日一致率(csi1000 的可用窗口)
        if base_period_end[uni] is not None:
            u_lo = base_period_end[uni]
            i2 = j2 = k2 = 0
            for code in set(a_win) | set(b_win):
                av = _mask(a_win.get(code, []), lo, hi)[u_lo - lo :]
                bv = _mask(b_win.get(code, []), lo, hi)[u_lo - lo :]
                i2 += int((av & bv).sum())
                j2 += int((av & ~bv).sum())
                k2 += int((bv & ~av).sum())
            per_universe[uni]["member_day_excluding_base_period_gap"] = {
                "window": {"start": grid.iso(u_lo), "end": grid.iso(hi)},
                "n_intersection": i2,
                "n_union": i2 + j2 + k2,
                "n_only_source_a": j2,
                "n_only_source_b": k2,
                "jaccard": round(i2 / (i2 + j2 + k2), 6) if (i2 + j2 + k2) else None,
            }

    # ---- 分歧归因
    # 先把跨越基期缺口边界的区段切开:缺口内外成因完全不同,不切开就会被整段
    # 记到一类上,归因表的"不重不漏"就成了假的。
    split: list[Run] = []
    for r in list(all_runs):
        end = base_period_end.get(r.universe)
        if end is None or r.side != "A" or not (r.i0 < end <= r.i1):
            continue
        split.append(
            Run(
                r.universe,
                r.code,
                r.side,
                r.i0,
                end - 1,
                "lead",
                r.other_has_code_in_universe,
                r.code_in_other_source_at_all,
                note="区段被源B 基期缺口的边界切开",
            )
        )
        r.i0 = end
    all_runs.extend(split)

    code_map, code_map_detail = _detect_code_mapping(all_runs, grid, base_period_end)
    for r in all_runs:
        classify_run(
            r,
            base_period_end=base_period_end,
            code_map=code_map,
            delist=delist,
            grid=grid,
        )

    by_class: dict[str, dict] = {}
    for key in _CLASS_ORDER:
        rs = [r for r in all_runs if r.cls == key]
        by_class[key] = {
            "label": _CLASS_LABEL[key],
            "criterion": _CLASS_WHY[key],
            "n_runs": len(rs),
            "n_member_days": sum(r.n_td for r in rs),
            "by_universe": {
                u: {
                    "n_runs": sum(1 for r in rs if r.universe == u),
                    "n_member_days": sum(r.n_td for r in rs if r.universe == u),
                }
                for u in cfg.UNIVERSES
            },
            "examples": _class_examples(rs, grid, names, delist, clipped, k=3),
        }
        # 第 5 类（一方缺整段）是下游**必须避开**的那一类：M1 签字裁定
        # "不做公告考古，工程化处理" —— 于是 `ambiguous` 标记要以它为准。
        # `examples` 只挑 3 条（最大/中位/最小），拿它去打标记会漏掉一半。
        # 这一类只有个位数条，全量落盘不会把 JSON 撑爆；别的类（月末粒度
        # 861 条）刻意不全量落，需要时重跑生成器。
        if key == "one_side_whole_segment":
            by_class[key]["runs"] = [
                {
                    "universe": r.universe,
                    "code": r.code,
                    "only_in_source": r.side,
                    "edge_kind": r.kind,
                    "start": grid.iso(r.i0),
                    "end": grid.iso(r.i1),
                    "n_trading_days": r.n_td,
                }
                for r in sorted(rs, key=lambda x: (x.universe, x.code, x.i0))
            ]

    total_symdiff = sum(
        per_universe[u]["member_day"]["n_symmetric_difference"] for u in cfg.UNIVERSES
    )
    attributed = sum(v["n_member_days"] for v in by_class.values())

    # ---- (b) 区间段一致率
    def _sample_block(uni: str, sub_lo: int | None = None) -> tuple[dict, list]:
        a_win, b_win, lo, hi = clipped[uni]
        a_use, b_use = a_win, b_win
        if sub_lo is not None:
            a_use, _ = _clip(a_win, sub_lo, hi)
            b_use, _ = _clip(b_win, sub_lo, hi)
        pool = set(a_use) | set(b_use)
        # 抽样池永远取**全窗口**的 code 全集,子窗口只是把段夹短 ——
        # 换个池子重抽会让两张表比的不是同一批票,没法对照。
        picked = [c for c in sample_codes(set(a_win) | set(b_win), uni, SAMPLE_SIZE, SAMPLE_SEED) if c in pool]
        vs = [
            _compare_segments(uni, c, a_use.get(c, []), b_use.get(c, []), grid)
            for c in picked
        ]
        counts = collections.Counter(v.verdict for v in vs)
        diffs_in = [p["in_diff_td"] for v in vs for p in v.pairs]
        diffs_out = [p["out_diff_td"] for v in vs for p in v.pairs]
        n = max(len(picked), 1)
        return (
            {
                "window": [grid.iso(sub_lo if sub_lo is not None else lo), grid.iso(hi)],
                "n_codes_in_pool": len(pool),
                # 抽样池是**夹窗口之后**的 code 集合。把不夹窗口的数也落盘,
                # 因为照报告字面(不夹窗口)复现会抽到另一批票 —— 这两个数不同
                # 正是"夹窗口"这一步必须写进方法描述的证据(合议裁决 A-5)。
                "n_codes_in_pool_unclipped": len(set(a_all[uni]) | set(b_all[uni])),
                "n_sampled": len(picked),
                # 抽中的 code 全部落盘:签字要能核"你抽的是不是这 300 只",
                # 只给一个种子等于让人自己去复现算法。
                "sampled_codes": picked,
                "verdicts": {k: counts.get(k, 0) for k in _SEG_VERDICTS},
                "pct_identical": round(100.0 * counts.get("identical", 0) / n, 2),
                "pct_identical_or_within_tolerance": round(
                    100.0
                    * (counts.get("identical", 0) + counts.get("within_tolerance", 0))
                    / n,
                    2,
                ),
                "n_segment_pairs_compared": len(diffs_in),
                "in_diff_td": _describe(diffs_in),
                "out_diff_td": _describe(diffs_out),
            },
            vs,
        )

    sample_block: dict[str, dict] = {}
    sample_block_usable: dict[str, dict] = {}
    for uni in cfg.UNIVERSES:
        blk, vs = _sample_block(uni)
        sample_block[uni] = blk
        seg_verdicts.extend(vs)
        end = base_period_end.get(uni)
        sample_block_usable[uni] = (
            _sample_block(uni, end)[0] if end is not None else blk
        )

    # ---- 约定敏感度:拆掉归一化的一步会多出多少"假分歧"
    # 直接算进报告而不是手抄负控脚本的输出 —— 抄进来的数字迟早会漂。
    half = alt_source_b_half_open(grid)
    unmerged = alt_source_b_unmerged(grid)
    cal = alt_calendar_day_symdiff()
    sens = {"by_universe": {}}
    for uni in cfg.UNIVERSES:
        a_win, b_win, lo, hi = clipped[uni]
        base_sym = per_universe[uni]["member_day"]["n_symmetric_difference"]
        b_half, _ = _clip(half[uni], lo, hi)
        sym_half = 0
        for code in set(a_win) | set(b_half):
            sym_half += int(
                (_mask(a_win.get(code, []), lo, hi) ^ _mask(b_half.get(code, []), lo, hi)).sum()
            )
        sens["by_universe"][uni] = {
            "baseline_symmetric_difference_trading_days": base_sym,
            "half_open_extra_symmetric_difference": sym_half - base_sym,
            "calendar_grid_symmetric_difference_calendar_days": cal[uni][1],
            "calendar_grid_extra_vs_baseline": cal[uni][1] - base_sym,
            "n_segments_source_b_merged": sum(len(v) for v in b_win.values()),
            "n_segments_source_b_unmerged": sum(
                len(v) for v in unmerged[uni].values()
            ),
        }
    sens["half_open_extra_total"] = sum(
        v["half_open_extra_symmetric_difference"] for v in sens["by_universe"].values()
    )
    sens["calendar_grid_extra_total"] = sum(
        v["calendar_grid_extra_vs_baseline"] for v in sens["by_universe"].values()
    )
    sens["max_segment_inflation_without_merging"] = round(
        max(
            v["n_segments_source_b_unmerged"] / max(v["n_segments_source_b_merged"], 1)
            for v in sens["by_universe"].values()
        ),
        1,
    )
    sens["note"] = (
        "把归一化的某一步拆掉,重算同一个对称差,看多出多少。数字越大,"
        "说明那一步越不能省。自然日那一列的 Jaccard 与交易日网格**不可比**"
        "(分母不是一回事),所以只报对称差绝对量。完整逐项见 "
        "ops/negctl_universe_reconcile.py。"
    )

    signoff = _pick_signoff(all_runs, grid, names, delist, clipped, code_map, n=20)

    result = {
        "card": "1.1-reconcile",
        "title": "PIT 宇宙对账:源A(index_weight 月末 diff) vs 源B(qlib instruments)",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "generator": "snapshots/universe_reconcile.py",
        "freeze_date": cfg.FREEZE_DATE,
        "parameters": {
            "sample_seed": SAMPLE_SEED,
            "sample_size_per_universe": SAMPLE_SIZE,
            "sampling_method": 'sha256(f"{seed}|{universe}|{code}") 升序取前 N',
            "boundary_tolerance_trading_days": BOUNDARY_TOL_TD,
            "base_period_min_fill": BASE_PERIOD_MIN_FILL,
            "delist_lookback_days": DELIST_LOOKBACK_DAYS,
            "delist_lookahead_days": DELIST_LOOKAHEAD_DAYS,
            "code_map_min_day_set_jaccard": CODE_MAP_MIN_JACCARD,
        },
        "snapshot_inputs": {
            "snapshot_version": cfg.SNAPSHOT_VERSION,
            "qlib_release": cfg.QLIB_RELEASE.name,
            "catalog_relative_to_lake": "catalog/market.duckdb",
            "why": (
                "抬头据此声明「这份报告是对哪一版输入算的」。两份 parquet 是卡 1.1 的"
                "冻结产物,sha256 变了就说明重算的不是同一批输入,报告里的数字不可比。"
            ),
        },
        "normalisation": {
            "grid": "湖 trade_cal(is_open=1),截到冻结线",
            "n_trading_days": len(grid.days),
            "grid_span": [grid.iso(0), grid.iso(len(grid.days) - 1)],
            "rule_in": "in_date → 不早于它的第一个交易日",
            "rule_out": "out_date → 不晚于它的最后一个交易日;源A 的 NULL 按右删失填冻结线",
            "rule_merge": "两段之间不含任何交易日就合并(源B 贴片行的还原步骤)",
            "why": (
                "源B 的 out_date 是“下一期生效日 − 1 日历天”,大量落在周日与节假日;"
                "源A 的 out_date 是“下一期快照的前一个交易日”。两者在交易日网格上是"
                "同一个端点,在日历上差 1~3 天。不先归一化,这个纯约定差会被当成分歧。"
            ),
            "source_a": a_diag,
            "source_b": b_diag,
        },
        "per_universe": per_universe,
        "member_day_overall": _overall_member_day(per_universe),
        "segment_level": sample_block,
        "segment_level_overall": _overall_segments(sample_block),
        "segment_level_excluding_base_period_gap": sample_block_usable,
        "segment_level_overall_excluding_base_period_gap": _overall_segments(
            sample_block_usable
        ),
        "divergence_classes": by_class,
        "attribution_check": {
            "total_symmetric_difference_member_days": total_symdiff,
            "attributed_member_days": attributed,
            "balanced": total_symdiff == attributed,
            "n_unclassified_runs": by_class["unclassified"]["n_runs"],
        },
        "convention_sensitivity": sens,
        "code_mapping_pairs": code_map_detail,
        "signoff_sample": signoff,
        "limitations": _limitations(),
    }
    return result


def _describe(xs: list[int]) -> dict:
    if not xs:
        return {"n": 0}
    arr = np.array(xs)
    return {
        "n": int(arr.size),
        "n_zero": int((arr == 0).sum()),
        "pct_zero": round(100.0 * float((arr == 0).mean()), 2),
        "n_abs_le_tol": int((np.abs(arr) <= BOUNDARY_TOL_TD).sum()),
        "pct_abs_le_tol": round(
            100.0 * float((np.abs(arr) <= BOUNDARY_TOL_TD).mean()), 2
        ),
        "min": int(arr.min()),
        "max": int(arr.max()),
        "mean": round(float(arr.mean()), 3),
        "p50": int(np.percentile(arr, 50)),
        "p95": int(np.percentile(arr, 95)),
        "n_a_later": int((arr > 0).sum()),
        "n_a_earlier": int((arr < 0).sum()),
    }


def _overall_member_day(per_universe: dict) -> dict:
    inter = sum(v["member_day"]["n_intersection"] for v in per_universe.values())
    union = sum(v["member_day"]["n_union"] for v in per_universe.values())
    only_a = sum(v["member_day"]["n_only_source_a"] for v in per_universe.values())
    only_b = sum(v["member_day"]["n_only_source_b"] for v in per_universe.values())
    usable_i = usable_u = 0
    for v in per_universe.values():
        blk = v.get("member_day_excluding_base_period_gap") or v["member_day"]
        usable_i += blk["n_intersection"]
        usable_u += blk["n_union"]
    return {
        "n_intersection": inter,
        "n_union": union,
        "n_only_source_a": only_a,
        "n_only_source_b": only_b,
        "n_symmetric_difference": only_a + only_b,
        "jaccard": round(inter / union, 6),
        "jaccard_excluding_base_period_gap": round(usable_i / usable_u, 6),
    }


def _overall_segments(sample_block: dict) -> dict:
    tot = sum(v["n_sampled"] for v in sample_block.values())
    agg = collections.Counter()
    for v in sample_block.values():
        agg.update(v["verdicts"])
    return {
        "n_sampled_total": tot,
        "verdicts": {k: agg.get(k, 0) for k in _SEG_VERDICTS},
        "pct_identical": round(100.0 * agg["identical"] / tot, 2),
        "pct_identical_or_within_tolerance": round(
            100.0 * (agg["identical"] + agg["within_tolerance"]) / tot, 2
        ),
    }


# --------------------------------------------------------------------------
# 例子 / 签字清单
# --------------------------------------------------------------------------


def _segments_text(segs: list[Seg], grid: Grid, i0: int, i1: int) -> str:
    """把与 ``[i0, i1]`` 有关(相交或紧邻)的段渲染成人读文本。"""
    lo = i0 - 400
    hi = i1 + 400
    rel = [(s, e) for s, e in segs if e >= lo and s <= hi]
    if not rel:
        return "(该时段无区间)"
    return " ∪ ".join(f"[{grid.iso(s)} … {grid.iso(e)}]" for s, e in rel)


def _run_case(
    run: Run,
    grid: Grid,
    names: dict[str, str],
    delist: dict[str, dt.date],
    clipped: dict,
) -> dict:
    a_win, b_win, _, _ = clipped[run.universe]
    dl = delist.get(run.code)
    nm = names.get(run.code)
    return {
        "universe": run.universe,
        "code": run.code,
        "name": nm if isinstance(nm, str) and nm else "(湖 stock_basic 无此码)",
        "disagreement_span": [grid.iso(run.i0), grid.iso(run.i1)],
        "n_trading_days": run.n_td,
        "only_in_source": run.side,
        "edge_kind": run.kind,
        "class": run.cls,
        "class_label": _CLASS_LABEL[run.cls],
        "source_a_says": _segments_text(a_win.get(run.code, []), grid, run.i0, run.i1),
        "source_b_says": _segments_text(b_win.get(run.code, []), grid, run.i0, run.i1),
        "delist_date": dl.isoformat() if dl else None,
        "counterpart_code": run.partner,
        "counterpart_says": (
            None
            if run.partner is None
            else _segments_text(
                (a_win if run.side == "B" else b_win).get(run.partner, []),
                grid,
                run.i0,
                run.i1,
            )
        ),
        "note": run.note,
    }


def _class_examples(
    runs: list[Run], grid: Grid, names, delist, clipped, k: int = 3
) -> list[dict]:
    """每类挑 k 个例子:最大的、中位的、最小的 —— 覆盖量级范围,不是只看最大值。"""
    if not runs:
        return []
    ordered = sorted(runs, key=lambda r: (-r.n_td, r.universe, r.code))
    picks: list[int] = []
    for pos in (0, len(ordered) // 2, len(ordered) - 1):
        if pos not in picks:
            picks.append(pos)
    return [_run_case(ordered[i], grid, names, delist, clipped) for i in picks[:k]]


#: 各分歧类型的"谁对"判词模板。判断依据来自约定层的可证事实,不是口味。
_VERDICT: dict[str, tuple[str, str]] = {
    "index_base_gap": (
        "源A 对",
        "源B 的上游在该宇宙的基期只写了 3 只票(源B 文档 B-01 已登记),"
        "是伪区间;源A 的月末快照在同期给出满编名单,与指数实际发布一致。"
        "**结论:该时段只能用源A,或干脆不用。**",
    ),
    "code_mapping": (
        "两源都自洽,但不可混用",
        "同一家公司在两源里是两个 ts_code:源A(湖 index_weight)用**当前**代码"
        "回溯改写历史,源B(qlib)保留**当时**的旧码。谁对取决于配套的行情表用哪套代码 ——"
        "跟湖 daily 对齐就用源A,跟 qlib features 对齐就用源B。**结论:必须建映射表,"
        "不能当成“一方漏数”。**",
    ),
    "delist_response": (
        "见逐条判词",
        "该票在分歧区段附近已经退市 / 被吸收合并。谁对**取决于方向**,逐条给。",
    ),
    "one_side_whole_segment": (
        "需人工判定",
        "不是边界对不齐,是整段的有无之差。两源同宗(都源自 Tushare index_weight),"
        "出现整段差异说明至少一方的上游加工有问题,机器判不了谁对,必须查指数公告。",
    ),
    "intra_period_flattened": (
        "源A 对(分辨率更高)",
        "一次短于一个快照周期的进出,只有一方看得见。源A 的网格是月末(约 12 期/年),"
        "源B 在本窗口里每年只有 2~4 个 epoch,更粗的那一方会把这次进出整个抹平。",
    ),
    "month_end_lag": (
        "源B 对(源A 精度不够,但方向正确)",
        "源B 的 in_date 是调整**生效日**;源A 最早也要等到生效日之后的第一期月末快照"
        "才看得见,滞后 ≤ 一个快照周期。这是源A 约定写死的**分辨率上限**,不是错误 ——"
        "源A 文档 conventions 已明确。**结论:要精确到日必须用源B 的边界。**",
    ),
    "month_end_lag_beyond_tol": (
        "需人工判定",
        "方向与月末滞后一致,但偏差超过一个快照周期,已经不能用“月末粒度”解释。"
        "多半是源B 的 epoch 格点粗于半年,或该期两源上游名单本身不同。",
    ),
    "coarse_epoch_b": (
        "源A 对",
        "源A 早于源B 看到变化 —— 可能是源A 先纳入(源B 还没加),也可能是源A 先剔除"
        "(源B 还留着)。源B 在本窗口里每年只有 2~4 个 epoch,IPO 快速纳入、"
        "退市临时替换这类月内事件会被推迟到下一个半年度格点才反映。"
        "**结论:源B 在这段时间的名单落后于事实。**",
    ),
    "unclassified": ("需人工判定", "分类规则未覆盖,必须人工查。"),
}


def _days_kept_after(segs: Sequence[Seg], d_idx: int) -> int | None:
    """该源的区间在 ``d_idx`` 这个交易日之后还延续几个交易日。

    负数 = 在这天之前就已经收尾。找不到任何相关段返回 None。
    """
    covering = [e for s, e in segs if s <= d_idx <= e]
    if covering:
        return max(covering) - d_idx
    prior = [e for s, e in segs if e < d_idx]
    return (max(prior) - d_idx) if prior else None


def _verdict_for(run: Run, grid: Grid, delist, clipped) -> tuple[str, str]:
    """给一条签字项算判词。

    退市类**必须按方向算**:静态判词会在"源A 反而留得更久"的个案上给出反向的
    错误结论(实测 `600357.SH` 就是这种)。这里用两源各自"退市日之后还延续几个
    交易日"来定谁对,数字直接写进依据。
    """
    if run.cls != "delist_response":
        return _VERDICT[run.cls]
    dl = delist.get(run.code)
    d_idx = grid.floor(dl) if dl else None
    a_win, b_win, _, _ = clipped[run.universe]
    a_keep = _days_kept_after(a_win.get(run.code, []), d_idx) if d_idx is not None else None
    b_keep = _days_kept_after(b_win.get(run.code, []), d_idx) if d_idx is not None else None
    if a_keep is None or b_keep is None or a_keep == b_keep:
        return (
            "需人工判定",
            f"该票 `{dl.isoformat() if dl else '?'}` 退市 / 被吸收合并,但两源的收尾"
            "位置无法直接比较,请查指数公告。",
        )
    early, late = ("A", "B") if a_keep < b_keep else ("B", "A")
    keep = {"A": a_keep, "B": b_keep}

    def _phrase(n: int) -> str:
        # `_days_kept_after` 允许返回负数(= 在退市日之前就收尾了)。
        # "延续 -1 个交易日"是模板套出来的废话,在一份要贴给人签字的文档里
        # 必须说人话。(合议裁决 A-8 / 视角二缺陷 6)
        if n > 0:
            return f"在此之后还延续 {n} 个交易日"
        if n == 0:
            return "恰好收尾在这一天"
        return f"在退市日之前 {abs(n)} 个交易日就已收尾"

    return (
        f"源{early} 对",
        f"该票 `{dl.isoformat()}` 退市 / 被吸收合并。以退市日(取不晚于它的最后一个"
        f"交易日)为基准:**源A 的区间{_phrase(a_keep)},源B {_phrase(b_keep)}**。"
        f"已退市的票不可能还在指数里,留得久的源{late} 在这 "
        f"{abs(keep[late] - keep[early])} 个交易日里给出的名单含**无法成交的持仓**。",
    )


def _pick_signoff(
    runs: list[Run], grid: Grid, names, delist, clipped, code_map, n: int = 20
) -> dict:
    """按分歧类型**分层**挑 n 条供人工签字。

    不随机挑:随机挑会把 20 条全部砸在最大的那一类上(基期缺口一类就占九成成员日),
    签完字也看不出别的问题。分配规则:

    1. 每个非空类型**保底 1 条**;
    2. 剩余名额按各类成员日占比用最大余数法分配,单类不超过 4 条;
    3. 类内按"最大 / 中位 / 最小 / 次大 / 次中位"取,覆盖量级范围;
       同一 (universe, code) 不重复入选。
    """
    cap = 4
    pools = {
        k: sorted(
            [r for r in runs if r.cls == k],
            key=lambda r: (-r.n_td, r.universe, r.code),
        )
        for k in _CLASS_ORDER
    }
    non_empty = [k for k in _CLASS_ORDER if pools[k]]
    quota = {k: 1 for k in non_empty}
    left = n - len(non_empty)
    if left > 0:
        weight = {k: sum(r.n_td for r in pools[k]) for k in non_empty}
        total = sum(weight.values()) or 1
        raw = {k: left * weight[k] / total for k in non_empty}
        for k in non_empty:
            quota[k] = min(quota[k] + max(int(raw[k]), 0), cap, len(pools[k]))
        # 最大余数法补齐,并让候选不足的类型把名额让出去
        rest = sorted(non_empty, key=lambda k: (-(raw[k] % 1), k))
        changed = True
        while sum(quota.values()) < n and changed:
            changed = False
            for k in rest:
                if sum(quota.values()) >= n:
                    break
                if quota[k] < min(cap, len(pools[k])):
                    quota[k] += 1
                    changed = True

    items: list[dict] = []
    seen: set[str] = set()
    for key in _CLASS_ORDER:
        if key not in quota:
            continue
        pool = pools[key]
        order: list[int] = []
        m = len(pool)
        for pos in (0, m // 2, m - 1, 1, m // 2 + 1, m - 2, 2):
            if 0 <= pos < m and pos not in order:
                order.append(pos)
        order += [i for i in range(m) if i not in order]
        taken = 0
        for pos in order:
            if taken >= quota[key]:
                break
            r = pool[pos]
            if r.code in seen:  # 20 条要覆盖 20 家不同的公司,不在同一只票上重复签字
                continue
            seen.add(r.code)
            case = _run_case(r, grid, names, delist, clipped)
            case["verdict"], case["basis"] = _verdict_for(r, grid, delist, clipped)
            items.append(case)
            taken += 1
    return {
        "n_items": len(items),
        "selection": (
            "按分歧类型分层:每个非空类型保底 1 条,余额按成员日占比分配(单类 ≤ 4),"
            "类内取最大/中位/最小以覆盖量级范围。完全确定,重跑结果不变。"
        ),
        "quota_by_class": quota,
        "items": items,
    }


def _limitations() -> list[str]:
    return [
        "**两源同宗,这不是独立验证。** 源B 的上游 chenditc/investment_data 用 Tushare "
        "index_weight 生成成分区间,与湖里的 index_weight 是同一份原始数据。"
        "对得上只说明两条加工链口径一致,不能证明名单本身正确;对不上才有信息量。"
        "(源B 文档已登记为风险 B-07)",
        "**只对了三个宇宙。** 湖 index_weight 只有 000300.SH / 000905.SH / 000852.SH,"
        "源B 的 csi800 / csiall / all 无源A 可对,本报告不涉及。",
        "**重叠窗口之外的差异不算分歧。** 源B 的 csi300 从 2005-04、csi500 从 2007-01 起,"
        "这段没有源A;两源都已被冻结线截到 2026-07-31,所以右端无窗口外差异。",
        "**trade_cal 只有 SSE 一个交易所。** 深市/北交所票用同一张日历展开。"
        "A 股两所日历一致,这个近似在本窗口内不产生误差,但不是零假设。",
        "**归一化会吃掉真实的 1~3 天差。** 把两源都投影到交易日网格,"
        "“源B 说到周日、源A 说到上周五”这种差异被消掉了 —— 这正是想要的(纯约定差),"
        "但如果下游要在非交易日上做判断,本报告的一致率就不适用。",
        "**段数不同时不做强行配对。** 段数不等直接判 segment_count_differs,"
        "不去猜哪段对哪段;这会让“区间段一致率”比“成员日一致率”看起来更悲观,"
        "是刻意的保守选择。",
        "**退市归因用的是最新一期 stock_basic。** 湖 stock_basic 只有 2026-08 的 18 个快照,"
        "delist_date 是当前状态字段,不是 PIT 的;仅用于给分歧贴标签与写清单,不参与成员判定。",
        "**代码映射是自动配对的推断,不是证据链。** 判据只有“分歧日集合 Jaccard ≥ 50% + 一源独有”,"
        "没有工商变更 / 交易所公告佐证。签字清单里的映射条目需要人工确认。",
    ]


# --------------------------------------------------------------------------
# Markdown 渲染
# --------------------------------------------------------------------------


def _pct(x: float) -> str:
    return f"{x * 100:.4f}%"


def _n(x: int) -> str:
    return f"{x:,}"


def _pit_closure_facts(codes: set[str]) -> tuple[set[str], dict[tuple[str, str], str]]:
    """从收口产物 `universe_pit` 现读:哪些 code 被在市窗口整只滤掉、尾段收在哪天。

    本清单比的是两份**原料**,而 `universe_pit` 叠了第三源 `stock_basic` 的在市窗口,
    已经替签字人闭掉了一部分条目(合议裁决 A-6)。这里**现读产物**而不是写死常量 ——
    写死的交叉引用会在下一次重建时悄悄变成假话。

    产物不存在(比如单独跑本模块、pit 还没建)就返回空,§5 的交叉引用整块跳过,
    报告仍然完整,只是少了这条省工时的提示。
    """
    absent: set[str] = set()
    tails: dict[tuple[str, str], str] = {}
    try:
        import pyarrow.parquet as _pq

        if not cfg.UNIVERSE_PIT_PARQUET.exists():
            return absent, tails
        pit = _pq.read_table(
            cfg.UNIVERSE_PIT_PARQUET,
            columns=["code", "universe", "out_date", "listing_clipped"],
        ).to_pandas()
    except Exception:  # pragma: no cover - 产物缺失/读不动时静默降级,不拖垮报告
        return absent, tails
    present = set(pit["code"].astype(str))
    absent = {c for c in codes if c not in present}
    clipped_rows = pit[pit["listing_clipped"].astype(bool)]
    for (uni, code), grp in clipped_rows.groupby(["universe", "code"]):
        if str(code) in codes:
            tails[(str(uni), str(code))] = str(max(grp["out_date"]))
    return absent, tails


def render_markdown(res: dict) -> str:
    L: list[str] = []
    w = L.append
    ov = res["member_day_overall"]
    sg = res["segment_level_overall"]
    per = res["per_universe"]

    w("# PIT 宇宙对账报告:源A(湖 index_weight) vs 源B(qlib instruments)")
    w("")
    w(
        f"卡 **{res['card']}** · 生成于 `{res['generated_at_utc']}` · "
        f"冻结线 `{res['freeze_date']}` · 实现 `{res['generator']}` · "
        f"机器可读版 `ops/{_SUMMARY_NAME}`"
    )
    w("")
    si = res["snapshot_inputs"]
    sa = res["normalisation"]["source_a"]
    sb = res["normalisation"]["source_b"]
    nz = res["normalisation"]
    w(
        f"**依赖的快照版本** —— 快照仓 `{si['snapshot_version']}`;"
        f"源A `{sa['path_relative_to_root']}`"
        f"(sha256 `{sa['sha256'][:16]}`,{_n(sa['rows'])} 行);"
        f"源B `{sb['path_relative_to_root']}`"
        f"(sha256 `{sb['sha256'][:16]}`,{_n(sb['rows_all_universes'])} 行,"
        f"上游 qlib release `{si['qlib_release']}`);"
        f"交易日网格取自湖 `trade_cal`,{nz['grid_span'][0]} … {nz['grid_span'][1]},"
        f"共 {_n(nz['n_trading_days'])} 个交易日。"
    )
    w("")
    w("---")
    w("")
    w("## 执行摘要")
    w("")
    w(
        f"1. **成员日一致率(Jaccard)= {_pct(ov['jaccard'])}**"
        f"(重叠窗口内共 {_n(ov['n_union'])} 个 `(code, 交易日)`,分歧 {_n(ov['n_symmetric_difference'])} 个);"
        f"剔除源B 已登记的 csi1000 基期缺口后为 **{_pct(ov['jaccard_excluding_base_period_gap'])}**。"
    )
    sgu0 = res["segment_level_overall_excluding_base_period_gap"]
    w(
        f"2. **区间段一致率**:固定种子抽 {sg['n_sampled_total']} 只 code 逐段比对,"
        f"边界**完全一致** {sg['pct_identical']:.2f}%,"
        f"**一致或差在一个快照周期({res['parameters']['boundary_tolerance_trading_days']} 个交易日)以内** "
        f"{sg['pct_identical_or_within_tolerance']:.2f}%;"
        f"同样剔除 csi1000 基期缺口后为 {sgu0['pct_identical']:.2f}% / "
        f"**{sgu0['pct_identical_or_within_tolerance']:.2f}%**。"
    )
    w(
        f"3. **分歧不是随机噪声**:{_n(ov['n_symmetric_difference'])} 个分歧成员日里,"
        f"{_pct(res['divergence_classes']['index_base_gap']['n_member_days'] / max(ov['n_symmetric_difference'], 1))} "
        f"来自源B 的 csi1000 基期缺口(已知缺陷 B-01),"
        f"{_pct((res['divergence_classes']['month_end_lag']['n_member_days'] + res['divergence_classes']['month_end_lag_beyond_tol']['n_member_days']) / max(ov['n_symmetric_difference'], 1))} "
        f"来自源A 的月末快照粒度(约定层的分辨率上限,不是错误),"
        f"{_pct(res['divergence_classes']['code_mapping']['n_member_days'] / max(ov['n_symmetric_difference'], 1))} "
        f"来自 4 组代码变更(同一家公司两个 ts_code);"
        f"扣掉这些之后,**既非已知缺陷、也非约定粒度、也非代码映射的“纯整段有无之差”只剩 "
        f"{_n(res['divergence_classes']['one_side_whole_segment']['n_member_days'] + res['divergence_classes']['intra_period_flattened']['n_member_days'])} 个成员日"
        f"({100.0 * (res['divergence_classes']['one_side_whole_segment']['n_member_days'] + res['divergence_classes']['intra_period_flattened']['n_member_days']) / max(ov['n_symmetric_difference'], 1):.2f}%)**。"
    )
    w("")
    # ⚠️ 上面第 3 条减掉的两类里,有两类是本报告**自己判了谁对谁错**的真分歧
    #    (退市响应差、源B 换仓格点粗)。只报最小的那个残余数会让签字人以为
    #    "只剩 791 个成员日要看",这是挑口径。三个口径在这里一次说清。
    #    (合议裁决 A-7 / 视角二缺陷 4)
    _dc = res["divergence_classes"]
    _pure = (
        _dc["one_side_whole_segment"]["n_member_days"]
        + _dc["intra_period_flattened"]["n_member_days"]
    )
    _judged = (
        _pure
        + _dc["delist_response"]["n_member_days"]
        + _dc["coarse_epoch_b"]["n_member_days"]
    )
    w(
        f"4. **“还剩多少要看”有三个口径,别只记住最小的那个。** "
        f"上面第 3 条的 {_n(_pure)} 个成员日({100.0 * _pure / max(ov['n_symmetric_difference'], 1):.2f}%)"
        f"是**最窄**的口径 —— 它把本报告已经判了谁对谁错的两类真分歧也减掉了"
        f"(退市响应差 {_n(_dc['delist_response']['n_member_days'])}、"
        f"源B 换仓格点粗 {_n(_dc['coarse_epoch_b']['n_member_days'])})。"
        f"**把这两类加回来 = {_n(_judged)} 个成员日"
        f"({100.0 * _judged / max(ov['n_symmetric_difference'], 1):.2f}%)** —— "
        f"这才是“两源实质不一致、需要有人拍板选一边”的量。"
        f"两个数都不假,区别是:{_n(_pure)} 回答“还有多少我说不清”,"
        f"{_n(_judged)} 回答“有多少地方我替你做了选择”。"
        f"签字看后者,§5 的清单也是按后者分层抽的。"
    )
    w("")
    w("> **这份报告不是互证。** 源B 的上游用 Tushare `index_weight` 生成区间,")
    w("> 与湖里的 `index_weight` 是同一份原始数据(源B 文档风险 B-07)。")
    w("> 对得上只说明两条加工链口径一致;**对不上的地方才有信息量**,本报告的重点在后者。")
    w("")
    w("---")
    w("")

    # ---- 方法
    w("## 1. 方法")
    w("")
    w("### 1.1 先解决约定,再算数字")
    w("")
    w("两源的区间约定不同,不归一化直接比大小,得到的每一个数字都是垃圾:")
    w("")
    w("| | 源A(index_weight 月末 diff) | 源B(qlib instruments) |")
    w("| --- | --- | --- |")
    w("| 日期类型 | 字符串 `YYYYMMDD` | `date32` |")
    w("| `in_date` 语义 | 首次观测到在成分内的**月末快照日** | 成分调整**生效日** |")
    w("| `out_date` 语义 | `下一期快照的前一个**交易日**` | `下一期生效日 − 1 **日历**天` |")
    w("| 右删失表示 | `out_date IS NULL` | `out_date == 2026-07-31` |")
    w("| 端点是不是交易日 | 两端都是 | `in` 100% 是;`out` 只有 57%~85% 是 |")
    w("| 一个 code 多段 | 真·多段(中间确实不在成分内) | **贴片式**:每 epoch 一行,首尾相接 |")
    w("")
    w("归一化分两步,顺序不能换:")
    w("")
    w(
        "1. **投影到交易日网格**(湖 `trade_cal`,`is_open=1`):"
        "`in_date` 取不早于它的第一个交易日,`out_date` 取不晚于它的最后一个交易日;"
        "源A 的 `NULL` 按右删失填冻结线 `2026-07-31`。"
        "这一步消掉的正是纯约定差 —— 源B 的 `out_date` 大量落在周日与节假日,"
        "源A 落在上一个交易日,**在网格上它们是同一个端点**。"
    )
    w(
        "2. **合并网格上相邻的段**(两段之间不含任何交易日就并成一段)。"
        f"这一步把源B 的贴片行还原成真正的成分段:三个宇宙合计 "
        f"{_n(res['normalisation']['source_b']['n_rows_on_grid'])} 行 → "
        f"{_n(res['normalisation']['source_b']['n_segments_after_merge'])} 段。"
        "**不做这一步,“区间段一致率”比的就是“贴片行数”对“成分段数”,完全没有意义。**"
    )
    w("")
    w(
        f"对源A 这一步是恒等变换(实测合并掉 "
        f"{res['normalisation']['source_a']['n_segments_merged_away']} 段,符合预期:"
        "源A 的相邻段之间至少隔一个完整快照周期)。归一化之后两源是**同一种对象** —— "
        "交易日网格上的闭区间集合,此后所有偏差的单位都是**交易日**,不是日历天。"
    )
    w("")
    sens = res["convention_sensitivity"]
    w("**这一步值多少?** 把归一化的每一环各拆掉一个,重算同一个对称差:")
    w("")
    w("| 拆掉哪一步 | 后果 | 多出的分歧成员日 |")
    w("| --- | --- | ---: |")
    w(
        f"| 源B 读成半开 `[in, out)` | 每个换仓边界日整批丢成分(源B 文档 §3.3 的坑) "
        f"| **+{_n(sens['half_open_extra_total'])}** |"
    )
    w(
        f"| 不投影到交易日网格,按自然日比 | 源B 的 `out_date` 落在周末/节假日、源A 落在上一个交易日 "
        f"| **+{_n(sens['calendar_grid_extra_total'])}** |"
    )
    w(
        f"| 不合并源B 的贴片行 | 成员日**一个都不变**,但源B 段数虚增到 "
        f"{sens['max_segment_inflation_without_merging']} 倍,§3 的段级指标直接失效 | 0 |"
    )
    w("")
    w(
        "> 三项都有判别力,所以 §1.1 不是仪式性的开场白。第三项之所以只影响 §3 而不影响 §2,"
        "是因为成员日展开成集合之后与怎么分段无关 —— **两个层次的指标各自防住不同的错**,"
        "这也是为什么两个都得算。逐项复现:`ops/negctl_universe_reconcile.py`。"
    )
    w("")
    w("### 1.2 比较窗口")
    w("")
    w(
        "只在两源**都有覆盖**的窗口内比较;窗口外的区间单独统计,不计入分歧。"
        "两源都已被冻结线截到 `2026-07-31`(源B 产物在卡 1.1-sourceB 就完成了截断),"
        "所以右端一律是冻结线,左端由源A 决定。"
    )
    w("")
    w("| 宇宙 | 源A 原生跨度 | 源B 原生跨度 | **重叠窗口** | 窗口内交易日 |")
    w("| --- | --- | --- | --- | ---: |")
    for u in cfg.UNIVERSES:
        win = per[u]["window"]
        w(
            f"| {u} | {win['source_a_native_span'][0]} … {win['source_a_native_span'][1]} "
            f"| {win['source_b_native_span'][0]} … {win['source_b_native_span'][1]} "
            f"| **{win['start']} … {win['end']}** | {_n(win['n_trading_days'])} |"
        )
    w("")
    w("**窗口外的存量**(按要求单独统计,不计入分歧):")
    w("")
    w("| 宇宙 | 源B 窗口前的行数 | 只在窗口前出现过的 code | 窗口前的日历天 | 源A 完全在窗口外的行数 |")
    w("| --- | ---: | ---: | ---: | ---: |")
    for u in cfg.UNIVERSES:
        o = per[u]["outside_window"]
        w(
            f"| {u} | {_n(o['source_b_rows_entirely_before_window'])} "
            f"| {o['source_b_codes_seen_only_before_window']} "
            f"| {_n(o['source_b_calendar_days_before_window'])} "
            f"| {o['source_a_rows_entirely_outside']} |"
        )
    w("")
    w(
        "> 源B 的 csi300 从 2005-04-08 起、csi500 从 2007-01-31 起,这两段**没有源A 可对**。"
        "湖 `trade_cal` 只从 2009-01-05 起,窗口前这段没有交易日网格可展开,"
        "所以这里只报原始行数、代码数与日历天数,**不折算成员日 —— 折不出来就不编**。"
    )
    w("")
    w("### 1.3 容忍多少天算一致")
    w("")
    tol = res["parameters"]["boundary_tolerance_trading_days"]
    w(
        f"**{tol} 个交易日(≈ 一个自然月)。** 理由不是拍脑袋:源B 的 `in_date` 是调整**生效日**,"
        "源A 最早也要等到生效日之后的**第一期月末快照**才看得见这次调整 —— 这段滞后是"
        "源A 约定写死的分辨率上限(源A 文档 `conventions.resolution` 已声明),"
        "不是数据错误。一个自然月约 20~23 个交易日,取上界 23。"
    )
    w("")
    w(
        "**超过一个快照周期的偏差就不再能用月末粒度解释**,单独成类(见 §4),必须逐条查。"
        "报告里“完全一致”和“容忍内一致”两个数都给,读者可以自己取舍。"
    )
    w("")
    w("### 1.4 抽样怎么保证可复现")
    w("")
    p = res["parameters"]
    w(
        f"种子 **`{p['sample_seed']}`**,方法:`{p['sampling_method']}`,"
        f"每个宇宙抽 **{p['sample_size_per_universe']}** 只(三个宇宙合计 {sg['n_sampled_total']} 只)。"
    )
    w("")
    w(
        "刻意**不用** `random` / `numpy.random`:那些实现随版本可变,"
        "“换台机器重跑抽到另外 300 只”会让签字失去意义。"
        "sha256 在任何平台任何版本都是同一个数,给定种子结果完全确定。"
        "宇宙名参与哈希,保证三个宇宙抽的不是同一批票。"
    )
    w("")
    w(
        "**候选池的定义是这个方法的一部分,漏了就抽不到同一批票。** "
        "候选池 = **先把两源的段按 §1.1 归一化、再夹到 §1.2 的重叠窗口 `[窗口起, 冻结线]`、"
        "夹完还剩至少一个交易日**的 code 并集 —— 不是“两源出现过的 code 全集”。"
        "整段落在窗口之外的 code 夹完就没了(§1.2 第二张表里“只在窗口前出现过的 code”"
        "那一列,以及 §1.1 第 1 步投影时落在交易日网格之外的),两者差别是实打实的:"
        "不夹窗口会得到 "
        + " / ".join(
            _n(res["segment_level"][u]["n_codes_in_pool_unclipped"])
            for u in cfg.UNIVERSES
        )
        + ",夹了才是下表的 "
        + " / ".join(
            _n(res["segment_level"][u]["n_codes_in_pool"]) for u in cfg.UNIVERSES
        )
        + "。**只要有一个宇宙的池子对不上,那个宇宙的前 300 名就是另一批票,"
        "一致率也就跟着变** —— 所以复核时这一步不能跳。"
    )
    w("")
    w(
        "> 抽样池取的是**全窗口**的 code 全集;§3 下半张“剔除基期缺口”的表只把段夹短、"
        "**不换池子**,否则两张表比的就不是同一批票,没法对照。"
    )
    w("")
    w("---")
    w("")

    # ---- 层次 a
    w("## 2. 层次(a):成员日一致率")
    w("")
    w(
        "把两源的区间按 `trade_cal` 展开成 `(code, 交易日)` 成员集合,算 Jaccard 与逐日对称差。"
        "**这是最硬的指标** —— 它比“只在月末快照日比对”严格得多:源A 的快照日恰好是两源"
        "最容易一致的那些天,分歧几乎全部藏在快照日之间的那 20 来个交易日里。"
    )
    w("")
    w("| 宇宙 | 窗口 | 交易日 | 源A 成员日 | 源B 成员日 | 交集 | 并集 | **Jaccard** | 只有A | 只有B | 零分歧日占比 |")
    w("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for u in cfg.UNIVERSES:
        m = per[u]["member_day"]
        win = per[u]["window"]
        w(
            f"| {u} | {win['start']}…{win['end']} | {_n(win['n_trading_days'])} "
            f"| {_n(m['n_member_days_source_a'])} | {_n(m['n_member_days_source_b'])} "
            f"| {_n(m['n_intersection'])} | {_n(m['n_union'])} | **{_pct(m['jaccard'])}** "
            f"| {_n(m['n_only_source_a'])} | {_n(m['n_only_source_b'])} "
            f"| {m['pct_days_with_zero_symmetric_difference']:.2f}% |"
        )
    w(
        f"| **合计** | — | — | — | — | {_n(ov['n_intersection'])} | {_n(ov['n_union'])} "
        f"| **{_pct(ov['jaccard'])}** | {_n(ov['n_only_source_a'])} | {_n(ov['n_only_source_b'])} | — |"
    )
    w("")
    for u in cfg.UNIVERSES:
        gap = per[u].get("source_b_base_period_gap")
        if not gap:
            continue
        ex = per[u]["member_day_excluding_base_period_gap"]
        w(
            f"> **{u} 的 {_pct(per[u]['member_day']['jaccard'])} 里,窗口最前面 {gap['n_trading_days']} 个交易日根本不该参与比较。** "
            f"源B 在 `{gap['gap_end_exclusive']}` 之前该宇宙只有 "
            f"{gap['source_b_member_count_at_window_start']} 个成员"
            f"(源B 文档已登记为 **B-01**,名义规模是 {per[u]['nominal_size']}),"
            f"整段是上游的伪区间。**剔除这段后 {u} 的 Jaccard = "
            f"{_pct(ex['jaccard'])}**(窗口 {ex['window']['start']}…{ex['window']['end']}),"
            "与另外两个宇宙同一量级。"
        )
        w("")
    w("**逐日对称差**(每个交易日两源名单差几只):")
    w("")
    w("| 宇宙 | 零分歧的交易日 | 占比 | 日均对称差 | 单日最大 | 最差的一天 |")
    w("| --- | ---: | ---: | ---: | ---: | --- |")
    for u in cfg.UNIVERSES:
        m = per[u]["member_day"]
        w(
            f"| {u} | {_n(m['n_days_with_zero_symmetric_difference'])} "
            f"| {m['pct_days_with_zero_symmetric_difference']:.2f}% "
            f"| {m['mean_symmetric_difference_per_day']} "
            f"| {m['max_symmetric_difference_on_one_day']} | {m['worst_day']} |"
        )
    w("")
    w("---")
    w("")

    # ---- 层次 b
    w("## 3. 层次(b):区间段一致率(逐段比对)")
    w("")
    w(
        f"每个宇宙抽 {p['sample_size_per_universe']} 只 code(种子 `{p['sample_seed']}`,"
        f"候选池的定义见 §1.4 —— **必须是夹过窗口的那个池子**),"
        "比 `in_date` / `out_date`。"
        "**段数不同的直接判“段数不同”,不做强行配对** —— 硬凑只会造出好看但没意义的偏差数字。"
    )
    w("")
    w("**配对之前必须先做这两步,顺序不能换**(照字面跳过会得到完全不同的数):")
    w("")
    w(
        "1. 两源的段按 §1.1 归一化后,**夹到本宇宙的重叠窗口 "
        "`[窗口起, 冻结线]`**(§1.2 的表),窗口外的部分整段丢弃;"
    )
    w(
        "2. 夹完**重新合并相邻段**(`_merge_touching`)—— 夹断之后原本隔着窗口外"
        "一小截的两段可能变成首尾相接,不重合并会虚增段数、把本来一致的 code "
        "误判成“段数不同”。"
    )
    w("")
    w(
        "> 这两步在实现里是 `snapshots/universe_reconcile.py` 的 `_clip()`"
        "(它内部就调 `_merge_touching`)。**跳过它们复现不出下表**:第一步就已经"
        "换掉了候选池(§1.4 的两组数),池子一换,前 300 名就是另一批票,"
        "后面每一格都对不上。两名独立验收员照报告旧版字面复现,得到的完全一致率"
        "分别是 55.11% 和 67.00%,差别的全部来源就是这一步 —— 这条方法描述"
        "因此被补进正文(合议裁决 A-5)。"
    )
    w("")
    w("| 宇宙 | 候选 code | 抽样 | 完全一致 | 容忍内一致 | 边界超容忍 | 段数不同 | 只有A | 只有B |")
    w("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for u in cfg.UNIVERSES:
        s = res["segment_level"][u]
        v = s["verdicts"]
        w(
            f"| {u} | {_n(s['n_codes_in_pool'])} | {s['n_sampled']} "
            f"| **{v['identical']}** ({s['pct_identical']:.1f}%) "
            f"| {v['within_tolerance']} | {v['boundary_beyond_tolerance']} "
            f"| {v['segment_count_differs']} | {v['only_in_source_A']} | {v['only_in_source_B']} |"
        )
    v = sg["verdicts"]
    w(
        f"| **合计** | — | {sg['n_sampled_total']} | **{v['identical']}** "
        f"({sg['pct_identical']:.1f}%) | {v['within_tolerance']} "
        f"| {v['boundary_beyond_tolerance']} | {v['segment_count_differs']} "
        f"| {v['only_in_source_A']} | {v['only_in_source_B']} |"
    )
    w("")
    w(
        f"**完全一致 {sg['pct_identical']:.2f}%,一致或容忍内 "
        f"{sg['pct_identical_or_within_tolerance']:.2f}%。**"
    )
    w("")
    sgu = res["segment_level_overall_excluding_base_period_gap"]
    if sgu["verdicts"] != sg["verdicts"]:
        w(
            "csi1000 的数字被源B 的基期缺口整个压塌了(§2 已说明):抽到的 300 只里有 "
            f"{res['segment_level']['csi1000']['verdicts']['boundary_beyond_tolerance']} 只"
            "的段头差正好卡在缺口边界上,`in` 偏差 −141 个交易日,全部落进“边界超容忍”。"
            "**把缺口那段剔掉之后**(同一批抽样 code,只把段夹到可用窗口):"
        )
        w("")
        w("| 宇宙 | 比较窗口 | 抽样 | 完全一致 | 容忍内一致 | 边界超容忍 | 段数不同 | 只有A | 只有B |")
        w("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
        for u in cfg.UNIVERSES:
            s = res["segment_level_excluding_base_period_gap"][u]
            v2 = s["verdicts"]
            w(
                f"| {u} | {s['window'][0]}…{s['window'][1]} | {s['n_sampled']} "
                f"| **{v2['identical']}** ({s['pct_identical']:.1f}%) "
                f"| {v2['within_tolerance']} | {v2['boundary_beyond_tolerance']} "
                f"| {v2['segment_count_differs']} | {v2['only_in_source_A']} | {v2['only_in_source_B']} |"
            )
        v2 = sgu["verdicts"]
        w(
            f"| **合计** | — | {sgu['n_sampled_total']} | **{v2['identical']}** "
            f"({sgu['pct_identical']:.1f}%) | {v2['within_tolerance']} "
            f"| {v2['boundary_beyond_tolerance']} | {v2['segment_count_differs']} "
            f"| {v2['only_in_source_A']} | {v2['only_in_source_B']} |"
        )
        w("")
        w(
            f"**剔除基期缺口后:完全一致 {sgu['pct_identical']:.2f}%,"
            f"一致或容忍内 {sgu['pct_identical_or_within_tolerance']:.2f}%。**"
        )
        w("")
    w("段级边界偏差分布(正数 = 源A 更晚,单位:交易日):")
    w("")
    w("| 宇宙 | 配对段数 | `in` 偏差=0 | `in` \\|偏差\\|≤容忍 | `in` 最小/中位/最大 | `out` 偏差=0 | `out` \\|偏差\\|≤容忍 | `out` 最小/中位/最大 |")
    w("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for u in cfg.UNIVERSES:
        s = res["segment_level"][u]
        di, do = s["in_diff_td"], s["out_diff_td"]
        if not di.get("n"):
            continue
        w(
            f"| {u} | {_n(di['n'])} | {di['pct_zero']:.1f}% | {di['pct_abs_le_tol']:.1f}% "
            f"| {di['min']} / {di['p50']} / {di['max']} "
            f"| {do['pct_zero']:.1f}% | {do['pct_abs_le_tol']:.1f}% "
            f"| {do['min']} / {do['p50']} / {do['max']} |"
        )
    w("")
    w(
        "> 偏差为正的绝大多数,方向与源A 文档 `qlib_alignment.expected_direction_for_card_1_2` "
        "的预测一致:`in_date_A >= start_B`、"
        "`out_date_A >= prev_trading_day(end_B + 1 天)`。"
        "⚠️ 出场侧**不是** `out_date_A >= end_B` —— 源B 的 `end` 是自然日且无一是交易日,"
        "不投影到网格直接比会先收到 245 条 −2 天的假矛盾(见 §1.1 第 1 步)。"
        "本表的偏差单位已经是**交易日**,那批假矛盾在这里不会出现。"
        "**取整之后方向仍然反了的(源A 更早)才不是精度问题**,已单独归类,见 §4 的"
        "“源B 换仓格点粗”。"
    )
    w("")
    w("---")
    w("")

    # ---- 分歧分类
    w("## 4. 分歧分类")
    w("")
    ac = res["attribution_check"]
    w(
        f"把每个**分歧区段**(同一 code 在网格上连续的一串对称差日)归到一个类型上。"
        f"判定按下表顺序,前面的优先,所以每个区段只落一类 —— "
        f"各类成员日之和 {_n(ac['attributed_member_days'])} "
        f"**恰好等于**总对称差 {_n(ac['total_symmetric_difference_member_days'])}"
        f"({'✅ 配平' if ac['balanced'] else '❌ 没配平,报告不可信'}),"
        f"未归类 {ac['n_unclassified_runs']} 条。"
    )
    w("")
    w("| # | 类型 | 区段数 | 分歧成员日 | 占比 | csi300 | csi500 | csi1000 |")
    w("| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    tot = max(ac["total_symmetric_difference_member_days"], 1)
    for i, key in enumerate(_CLASS_ORDER, 1):
        c = res["divergence_classes"][key]
        if c["n_runs"] == 0 and key != "unclassified":
            w(
                f"| {i} | {c['label']} | 0 | 0 | — | 0 | 0 | 0 |"
            )
            continue
        bu = c["by_universe"]
        w(
            f"| {i} | {c['label']} | {_n(c['n_runs'])} | {_n(c['n_member_days'])} "
            f"| {100.0 * c['n_member_days'] / tot:.2f}% "
            f"| {_n(bu['csi300']['n_member_days'])} | {_n(bu['csi500']['n_member_days'])} "
            f"| {_n(bu['csi1000']['n_member_days'])} |"
        )
    w("")
    for i, key in enumerate(_CLASS_ORDER, 1):
        c = res["divergence_classes"][key]
        if not c["examples"]:
            if key == "unclassified":
                w(f"### 4.{i} {c['label']} —— **0 条**")
                w("")
                w("分类规则完全覆盖了本轮所有分歧区段。这一类不为 0 就说明规则漏了情形。")
                w("")
            else:
                w(f"### 4.{i} {c['label']} —— **本窗口内 0 条**")
                w("")
                w(f"判据:{c['criterion']}")
                w("")
                if key == "intra_period_flattened":
                    w(
                        "> **这是一条有信息量的零。** 常见的担心是“源A 月末粒度会把月内进出整个抹平”。"
                        "本窗口内**没有观测到任何一例**:源B 在这三个宇宙里每年只有 2~4 个 epoch,"
                        "比源A 的月末网格**更粗**,所以抹平的方向反而是源B。"
                    )
                    w("")
            continue
        w(f"### 4.{i} {c['label']} —— {_n(c['n_runs'])} 条 / {_n(c['n_member_days'])} 个成员日")
        w("")
        w(f"判据:{c['criterion']}")
        w("")
        for ex in c["examples"]:
            w(
                f"* **`{ex['code']}` {ex['name']}**({ex['universe']},"
                f"{ex['disagreement_span'][0]} … {ex['disagreement_span'][1]},"
                f"{ex['n_trading_days']} 个交易日,只有源{ex['only_in_source']} 说它在)"
            )
            w(f"  * 源A:{ex['source_a_says']}")
            w(f"  * 源B:{ex['source_b_says']}")
            extra = []
            if ex["delist_date"]:
                extra.append(f"退市日 `{ex['delist_date']}`")
            if ex["counterpart_code"]:
                extra.append(f"对家代码 `{ex['counterpart_code']}`")
            if extra:
                w(f"  * {' · '.join(extra)}")
        w("")

    if res["code_mapping_pairs"]:
        w("### 4.10 自动识别出的代码映射对")
        w("")
        w("| 宇宙 | 只在源 | 该源用的码 | 另一源用的码 | 分歧日 Jaccard | 分歧时段 | 交易日 |")
        w("| --- | :-: | --- | --- | ---: | --- | ---: |")
        for d in res["code_mapping_pairs"]:
            w(
                f"| {d['universe']} | {d['only_in_source']} | `{d['code_only_in_that_source']}` "
                f"| `{d['counterpart_code_in_other_source']}` | {d['day_set_jaccard']:.0%} "
                f"| {d['disagreement_span'][0]} … {d['disagreement_span'][1]} "
                f"| {_n(d['n_disagreement_td'])} |"
            )
        w("")
        w(
            "> 这是**自动推断**,判据只有“分歧日集合 Jaccard ≥ 50% + 一源独有”,"
            "没有工商变更/交易所公告佐证。**下游要用必须先人工确认。**"
        )
        w("")
    w("---")
    w("")

    # ---- 签字清单
    so = res["signoff_sample"]
    w(f"## 5. 人工签字清单({so['n_items']} 条)")
    w("")
    w(f"挑选规则:{so['selection']}")
    w("")
    w(
        "**不是随机挑的。** 随机挑会把 20 条全部砸在最大的那一类上"
        "(基期缺口一类就占九成成员日),签完字也看不出别的问题。"
    )
    w("")
    # ⚠️ 本清单是对着**对账**写的,比的是两份原料;而收口产物 universe_pit 叠了
    #    第三源 stock_basic 的在市窗口,已经把其中两类闭掉了。不交叉引用的话,
    #    签字人会在已经没有争议的条目上空转 1/5 的工时。
    #    (合议裁决 A-6 / 视角二缺陷 3)条号一律现场推,不写死。
    _PIT_ABSENT_CODES, _PIT_TAIL = _pit_closure_facts(
        {it["code"] for it in so["items"]}
    )
    _closed = [
        (i, it)
        for i, it in enumerate(so["items"], 1)
        if it["class"] == "delist_response"
        and (it["universe"], it["code"]) in _PIT_TAIL
    ]
    _nolake = [
        (i, it)
        for i, it in enumerate(so["items"], 1)
        if it["code"] in _PIT_ABSENT_CODES
    ]
    if _closed or _nolake:
        w(
            "> **先看这一段,能省掉你一部分工时。** 本清单是对着**对账**写的 —— "
            "它比的是源A 与源B 两份**原料**,**不是**收口产物 `universe_pit`。"
            "下面这些条目在收口时已经被下游闭环,签字人**不必再拍板**,"
            "只需确认闭环方式认可:"
        )
        w(">")
    if _closed:
        w(
            "> * **退市 / 吸收合并的响应差(本清单第 "
            + "、".join(str(i) for i, _ in _closed)
            + " 条):已闭环。** `universe_pit` 叠了第三源 `stock_basic` 的在市窗口"
            "(`list_date <= D < delist_date`),把两源的收尾一律夹到退市日**之前**,"
            "`listing_clipped=True` 显式标记。逐条实测:"
            + ";".join(
                f"`{it['code']}` {it['universe']} 止于 "
                f"`{_PIT_TAIL[(it['universe'], it['code'])]}`"
                f"(退市日 {it['delist_date']})"
                for _, it in _closed
            )
            + "。**判词与收口结果一致,且收口比两源都更严** —— "
            "包括本清单判“源B 对”的那条,收口收得比源B 还早一天。"
        )
    if _nolake:
        w(
            "> * **湖 `stock_basic` 里查无此票的码(本清单第 "
            + "、".join(str(i) for i, _ in _nolake)
            + " 条):已被滤掉。** 这些码在 `universe_pit` 里 **0 行**"
            "(整只被在市窗口滤掉,数据卡 §5.3 有记),不会流到任何下游读法里。"
            "签字人不必去考证它是哪家公司。"
        )
    if _closed or _nolake:
        n_open = so["n_items"] - len(_closed) - len(_nolake)
        w(">")
        w(
            f"> 其余 {n_open} 条是**真的需要你拍板**的:代码映射要不要建映射表、"
            "月末粒度的滞后认不认、源B 换仓格点粗时信谁。"
        )
        w("")
    for i, it in enumerate(so["items"], 1):
        w(
            f"#### {i}. `{it['code']}` {it['name']} · {it['universe']} · "
            f"{it['class_label']}"
        )
        w("")
        w(
            f"| 分歧时段 | {it['disagreement_span'][0]} … {it['disagreement_span'][1]}"
            f"({it['n_trading_days']} 个交易日) |"
        )
        w("| --- | --- |")
        w(f"| **源A 说** | {it['source_a_says']} |")
        w(f"| **源B 说** | {it['source_b_says']} |")
        w(f"| 分歧方向 | 这段时间**只有源{it['only_in_source']}** 认为它在成分内 |")
        if it["delist_date"]:
            w(f"| 退市日(湖 stock_basic) | `{it['delist_date']}` |")
        if it["counterpart_code"]:
            w(
                f"| 另一源用的代码 | `{it['counterpart_code']}`,"
                f"在另一源里的区间:{it['counterpart_says']} |"
            )
        w(f"| **我的判断** | **{it['verdict']}** |")
        w(f"| **依据** | {it['basis']} |")
        w("| 人工签字 | ☐ 认可　☐ 不认可(理由:____________) |")
        w("")
    w("---")
    w("")

    # ---- 局限
    w("## 6. 已知局限")
    w("")
    for i, lim in enumerate(res["limitations"], 1):
        w(f"{i}. {lim}")
    w("")
    w("---")
    w("")
    w("## 7. 复现")
    w("")
    w("```")
    w("# 0) 先定义这两个变量,否则下面第一行会把你 cd 回家目录")
    w(f"export GENEBENCH_ROOT={cfg.GENEBENCH_ROOT}")
    w('export REPO="$GENEBENCH_ROOT/repo"')
    w('cd "$REPO"')
    w("ulimit -n 8192            # 不抬 fd 上限,duckdb 查全表会 too many open files")
    w("# 1) 重建报告与 JSON")
    w("$GENEBENCH_ROOT/env/bin/python -m snapshots.universe_reconcile")
    w("# 2) 验收测试(算术自洽 / 抽样可复现 / 与源B 文档交叉核对 / 冻结线)")
    w("$GENEBENCH_ROOT/env/bin/python -m pytest ops/test_universe_reconcile.py -q")
    w("# 3) 负控:逐项量出 §1.1 每一步归一化的判别力")
    w("$GENEBENCH_ROOT/env/bin/python ops/negctl_universe_reconcile.py")
    w("```")
    w("")
    w(
        f"> `GENEBENCH_ROOT` 当前是 `{cfg.GENEBENCH_ROOT}`(临时落点,见 `ops/tickets.md` 的 T-01);"
        "搬家之后只改这一行 export,下面四条命令不动。"
    )
    w("")
    w(
        f"确定性:抽样种子 `{p['sample_seed']}` 写死在 `snapshots/universe_reconcile.py` 的 "
        "`SAMPLE_SEED`,抽样与例子挑选都不依赖随机数发生器,"
        "同样的两份 parquet 输入必然得到逐字相同的报告。"
    )
    w("")
    return "\n".join(L)


# --------------------------------------------------------------------------
# 落盘
# --------------------------------------------------------------------------


def _write(path, text: str) -> None:
    """写文本并把权限收到 0600(本机 umask 是 002,不显式 chmod 会落成组可读,红线 5)。"""
    cfg.create_dir(path.parent)
    path.write_text(text, encoding="utf-8")
    os.chmod(path, 0o600)


def main(argv: Sequence[str] | None = None) -> int:
    cfg.harden_umask()
    res = build()
    _write(summary_path(), json.dumps(res, ensure_ascii=False, indent=2, default=str))
    _write(report_path(), render_markdown(res))
    ov = res["member_day_overall"]
    sg = res["segment_level_overall"]
    print(f"报告      : {report_path()}")
    print(f"机器可读  : {summary_path()}")
    print(f"成员日 Jaccard        : {ov['jaccard']:.6f}  (剔基期缺口 {ov['jaccard_excluding_base_period_gap']:.6f})")
    print(f"区间段 完全一致       : {sg['pct_identical']:.2f}%")
    print(f"区间段 容忍内一致     : {sg['pct_identical_or_within_tolerance']:.2f}%")
    ac = res["attribution_check"]
    print(f"归因配平              : {ac['balanced']}  未归类 {ac['n_unclassified_runs']}")
    return 0 if ac["balanced"] and ac["n_unclassified_runs"] == 0 else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
