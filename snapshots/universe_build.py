"""卡 1.1 **收口**:三源合并 → 最终 PIT 宇宙表 `universe_pit`。

跑法::

    cd $REPO && $GENEBENCH_ROOT/env/bin/python -m snapshots.universe_build

产物三件(路径全部来自 `genebench_config`,本文件**不含任何绝对路径字面量**):

* `cfg.UNIVERSE_PIT_PARQUET` —— 最终区间表(落 `$GENEBENCH_ROOT`,**不进 repo**)
* `cfg.UNIVERSE_PIT_JSON`    —— 机器可读摘要 + 完整性自查(进 git)
* `cfg.UNIVERSE_PIT_CARD`    —— **数据卡**,人读(进 git;由本模块生成,不手写)

**下游只该读 `universe_pit`。** 源A(`index_weight_intervals.parquet`)与
源B(`qlib_instruments_intervals.parquet`)是对账中间产物,不是回测输入。


================================================================
一、三个源分别负责什么
================================================================

============= ============================================ ==========================
源            数据                                          在本表里的角色
============= ============================================ ==========================
A ``index_weight``  湖 `index_weight` 月末快照相邻期 diff   成分**存在性**(主力)
B ``qlib``          qlib community instruments 区间文件      成分**边界精度** + 左端回溯
C ``stock_basic``   `list_date` / `delist_date` + `namechange` **在不在市**(兜底与闸门)
============= ============================================ ==========================

合成规则一句话:**成员 = (A ∪ B) ∩ 在市窗口**,再按"哪些源这么说"切片。

*为什么是并集不是交集。* 交集会删掉两块真东西:
(1) csi1000 在 2015-05-28 之前源B 只有 3 个成员(源B 已登记缺陷 B-01),
交集会把 140,577 个成员日整片抹掉;(2) csi300/csi500 在 2009-01-05~2009-01-22
只有源B 有(源A 首期是 2009-01-23),交集会把源A 的左截断永久固化。
并集把两源的**覆盖**加起来,再用第三源当闸门,是唯一不丢真数据的做法。

*为什么必须有第三源这道闸门。* 并集会带进源B 的一类系统性错误:
**已退市的票还留在成分名单里**(实测 27 行、20+ 只,如 600270.SH 外运发展
退市于 2018-12-28 而源B 留到 2019-06-27)。这些日子的"成分股"没有行情、
不可能成交,拿去回测就是凭空的持仓。湖 `daily` 在 `delist_date` 当天及之后
**零行**(实测:277 只有行情的退市票,没有一只的最后一根 K 线 >= delist_date),
所以在市窗口取 ``list_date <= D < delist_date``,与行情表的可得性完全一致。


================================================================
二、区间约定(精确定义,下游按这个写过滤)
================================================================

* **闭区间 ``[in_date, out_date]``,两端都含。** 过滤写
  ``in_date <= D and D <= out_date``。
* **时间轴是交易日网格**(湖 `trade_cal`,``is_open = 1``,截到冻结线)。
  端点**一定**是交易日:源B 的自然日端点(落在周末/节假日)先投影 ——
  ``in`` 取不早于它的第一个交易日,``out`` 取不晚于它的最后一个交易日。
  不做这一步,同一件事在两源里会长成不同的日期,对账数字全是垃圾。
* **``out_date`` 永不为 NULL。** 冻结线之后一律截断:仍在成分内的段
  ``out_date = 2026-07-31`` **且** ``right_censored = True``。
  这两件事必须一起读 —— 单看 ``out_date == 2026-07-31`` 不代表"当天被调出"。
  (源A 用 NULL 表示开口;那个约定在源A 内部是对的,但它让
  ``in_date <= D <= out_date`` 这种过滤在冻结线**之外**静默返回满额宇宙。
  收口表把上界写进数据里,越界读法见 `universe_at()`。)
* **日期两种形态,同一件事。** ``in_date`` / ``out_date`` 是 ``date32``(权威口径);
  ``in_date_compact`` / ``out_date_compact`` 是 8 位 ``YYYYMMDD`` 字符串,
  专供直接和湖里的 ``trade_date``(VARCHAR)join。**不要**自己转换 ——
  湖的 gold parquet 里 `trade_date` 是 DATE、catalog view 里是 VARCHAR,
  自己转必踩其中一个。
* **``code`` 一律湖内形态 ``600000.SH``**,不是 qlib 的 ``SH600000``。


================================================================
三、一次"进出"会被切成多行 —— segment_idx 与 part_idx
================================================================

一只票在同一宇宙里可以多次进出,每次进出是一个 **membership run**,
``segment_idx`` 从 0 起数。**同一次进出内部**,如果两源的说法在中途变了
(比如源B 说 6 月 30 日就进来了、源A 要等到 7 月 31 日才看见),
这一次进出会再被切成若干 **part**,``part_idx`` 从 0 起数,
每个 part 的 ``source`` / ``agreement_flag`` 是常数。

所以:

* **数"这只票进出过几次" → 数 distinct ``segment_idx``,不要数行数。**
  数行数会把一次进出的两端滞后读成三次进出 —— 这是本表最容易踩的坑。
* **判"某天在不在" → 直接过滤,不用管分片。** 同一次进出的各 part 在网格上
  首尾相接(相邻 part 之间不含任何交易日),并起来就是完整区间。
* ``segment_id = "{universe}|{code}|{segment_idx}|{part_idx}"`` 是全表唯一行键。


================================================================
四、``source`` 与 ``agreement_flag``
================================================================

``source`` 取值(``cfg.UNIVERSE_SOURCES``):

* ``both``             两源都说这段在成分内
* ``index_weight``     只有源A 这么说
* ``qlib_instruments`` 只有源B 这么说
* ``basic_fallback``   第三源兜底(``all`` 市场全集宇宙专用)

``agreement_flag`` 是**可空**布尔,回答"两源在这一段上一致吗":

* ``True``  —— 一致。两种情形:两源都说在(``both_sources_agree``);
  或只有一源说在、但差异是**纯约定差**(``tolerated_boundary_lag``,见下)。
* ``False`` —— 不一致,且不能用约定差解释。``agreement_basis`` 说明是哪一类。
* ``NULL``  —— **不适用**。``all`` 宇宙只有第三源一个来源,没有第二源可对;
  写 ``False`` 会被读成"两源打架",写 ``True`` 是无中生有。

**容忍口径(这是本表最需要写清楚的一条)。**
源B 的 ``in_date`` 是成分调整的**生效日**(落在月中);源A 最早也要等到生效日
之后的第一期**月末快照**才看得见这次调整。这段滞后是源A 约定写死的
**分辨率上限**,不是数据错误。一个自然月约 20~23 个交易日,取上界
``cfg.BOUNDARY_TOL_TD = 23`` 个**交易日**。判据是三条**同时**成立:

1. 这个 part 是单源的(``source != 'both'``);
2. 它紧贴着同一次进出里的一个 ``both`` part(即它是这次进出的**头或尾**,
   中间挖洞的不算);
3. 它的长度 ``n_trading_days <= 23``。

三条都成立 → ``agreement_flag = True`` / ``tolerated_boundary_lag``。
差异**超过**一个快照周期就不再能用月末粒度解释,归
``boundary_lag_beyond_tolerance`` 并判 ``False``。

``agreement_basis`` 的全部取值见 `AGREEMENT_BASIS`。


================================================================
五、冻结线(红线 7)
================================================================

交易日网格、三个源的区间、``all`` 宇宙的在市窗口,**全部**截到
``cfg.FREEZE_DATE = 2026-07-31``。产物里不存在任何 ``> 2026-07-31`` 的日期,
parquet 的 schema metadata 里写了 ``valid_from`` / ``valid_to``,
`universe_at()` 对越界的查询日**抛错**而不是静默返回空集或末期名单。
"""

from __future__ import annotations

import argparse
import bisect
import collections
import datetime as dt
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence

# ---------------------------------------------------------------------------
# ⚠️ 收紧 umask 必须发生在**任何仓库内 import 之前**(卡 0.2 / 卡 1.1 源A 定下的三行)。
# 本机默认 umask 是 002:CPython 在 import 模块时就现建 `__pycache__/` 写字节码,
# 那一刻 `cfg.harden_umask()` 还没被调到,目录会落成 0775,踩红线 5 的递归审计。
# 字面量 0o077 刻意重复 `cfg.REQUIRED_UMASK` —— 它必须早于 import cfg 生效;
# 下面紧跟一条断言防漂移。
# ---------------------------------------------------------------------------
_PREVIOUS_UMASK = os.umask(0o077)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

try:  # 允许 `python snapshots/universe_build.py` 这种不带包上下文的跑法
    import genebench_config as cfg  # noqa: E402
except ModuleNotFoundError:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import genebench_config as cfg  # noqa: E402

from snapshots import lake  # noqa: E402
from snapshots import universe_index_weight as source_a  # noqa: E402
from snapshots import universe_qlib as source_b  # noqa: E402

assert 0o077 == cfg.REQUIRED_UMASK, (
    f"上面硬写的 umask 0o077 与 cfg.REQUIRED_UMASK={oct(cfg.REQUIRED_UMASK)} 漂移了"
)

# `-m snapshots.universe_build` 会先 import 包 `snapshots`,包的 `__pycache__`
# 比本文件第一行还早落地,只能事后幂等收敛(与源A / conftest 同一套办法)。
CONVERGED_CACHE_DIRS: list[str] = []
for _cache in Path(__file__).resolve().parents[1].rglob("__pycache__"):
    if not _cache.is_dir():
        continue
    if _cache.stat().st_mode & cfg.FORBIDDEN_MODE_BITS:
        CONVERGED_CACHE_DIRS.append(str(_cache))
    cfg.create_dir(_cache)

__all__ = [
    "PIT_COLUMNS",
    "SCOPES",
    "COLUMN_DOC",
    "AGREEMENT_BASIS",
    "PARQUET_SCHEMA",
    "Grid",
    "load_grid",
    "merge_touching",
    "load_listing_windows",
    "load_source_a",
    "load_source_b",
    "is_canonical",
    "build_pit",
    "daily_size_stats",
    "summarize",
    "render_data_card",
    "read_pit",
    "universe_at",
    "write_outputs",
    "build",
    "main",
]

#: 湖里的第三源:上市/退市窗口。多快照表,必须 DISTINCT(见 `load_listing_windows`)。
BASIC_VIEW: str = "stock_basic"

#: 湖里的更名历史(第三源的佐证面)。派生视图 `stock_name_pit` 把它整理成 PIT 区间。
NAMECHANGE_VIEW: str = "namechange"
NAME_PIT_VIEW: str = "stock_name_pit"

#: 交易日历。湖里只有 SSE 一个交易所 —— A 股两所日历一致,与源A / 对账口径相同。
CALENDAR_VIEW: str = "trade_cal"

#: 判"源B 在该宇宙还没真正开始"的阈值:成员数低于名义规模的这个比例。
#: 不硬编码日期,让数据自己说话(与卡 1.1-reconcile 的 `BASE_PERIOD_MIN_FILL` 同源)。
BASE_PERIOD_MIN_FILL: float = 0.5

#: 产物列顺序。**动这个顺序等于改产物 schema**,下游要跟着改。
PIT_COLUMNS: tuple[str, ...] = (
    "code",
    "universe",
    "in_date",
    "out_date",
    "source",
    "agreement_flag",
    "agreement_basis",
    "segment_id",
    "segment_idx",
    "part_idx",
    "canonical",
    "left_censored",
    "right_censored",
    "listing_clipped",
    "n_trading_days",
    "in_date_compact",
    "out_date_compact",
    "ambiguous",
)

#: `scope` 的取值:``canonical`` = 方案甲的主力读法(源A 为主),``union`` = 全部来源。
SCOPES: tuple[str, ...] = ("canonical", "union")

#: 每列一句话,直接写进摘要 JSON 与数据卡,免得下游回来读源码。
COLUMN_DOC: dict[str, str] = {
    "ambiguous": (
        "该段与**对账第 5 类（一方缺整段 / 多一个中间段）**有交集。"
        "两源对这段成员身份实质不一致，且本项目**不做公告考古**（M1 签字裁定）——"
        "所以任务与窗口生成器一律避开命中该标记的 `(code, 时段)`。"
        "⚠️ 行级标记是**保守**的（整行命中即为 True，可能宽于真实分歧跨度）；"
        "精确到日的排除请用 `ambiguous_spans()` / `is_ambiguous()`，"
        "它是权威来源 —— 有的分歧段在 canonical 口径下**根本没有对应行**"
        "（例：`300114.SZ` 只有源B 说它在），只看本列会漏掉。"
    ),
    "code": "成分股代码,**湖内形态** `600000.SH`(不是 qlib 的 `SH600000`)。",
    "universe": "csi300 / csi500 / csi1000 / all(市场全集)。",
    "in_date": "区间起(**含**),`date32`。一定是交易日。",
    "out_date": (
        "区间止(**含**),`date32`。一定是交易日,**永不为空**。"
        "等于冻结线且 `right_censored=True` 时表示'截至冻结线仍在',"
        "**不是**'当天被调出'。"
    ),
    "source": (
        "这一段是哪些源说的:`both` / `index_weight` / `qlib_instruments` / "
        "`basic_fallback`(见 `cfg.UNIVERSE_SOURCES`)。"
    ),
    "agreement_flag": (
        "两源在这一段上是否一致(**可空**)。True = 两源都说在,或差异在容忍口径内;"
        "False = 不一致且不能用约定差解释;NULL = 不适用(`all` 宇宙只有一个源)。"
        "为什么是这个值看 `agreement_basis`。"
    ),
    "agreement_basis": "`agreement_flag` 的判据,取值见 `AGREEMENT_BASIS`。",
    "canonical": (
        "**这一行属不属于主力读法**(实施稿方案甲:月末快照 diff 自建为主、"
        "qlib instruments 交叉对账)。True 的三种情形:`all` 宇宙全部;"
        "源A 说在(`both` / `index_weight`);源A 在该宇宙**首期之前**、"
        "只有源B 有数据的那段。**只取 canonical 行,宇宙规模就回到名义值;"
        "取全表(union)会在两源边界不齐的日子上把宇宙撑大到名义值以上。**"
    ),
    "segment_id": "`{universe}|{code}|{segment_idx}|{part_idx}`,全表唯一行键。",
    "segment_idx": (
        "这只票在这个宇宙里的**第几次进出**(0 起)。"
        "**数进出次数用 distinct segment_idx,不要数行数。**"
    ),
    "part_idx": (
        "同一次进出内部,按'哪些源这么说'切出来的第几个片段(0 起)。"
        "同一 segment_idx 下各 part 在交易日网格上首尾相接,并起来是完整区间。"
    ),
    "left_censored": (
        "**行级**谓词:`in_date` 就是该宇宙**可观测下界**那一天,真实入场日更早或不可知。"
        "指数宇宙的下界 = 两源覆盖的第一个交易日;`all` 宇宙 = 交易日历起点。"
        "等价写法 `in_date == valid_from_of(universe)`。"
        "注意 `part_idx > 0` 的行的 `in_date` 也不是真实入场日 —— 那是**来源切换**的边界,"
        "不是截断,看 `part_idx` 就能分辨。"
    ),
    "right_censored": (
        "**行级**谓词,与 `out_date == 冻结线` **等价**:未观测到出场。"
        "**不是**'当天被调出'。"
    ),
    "listing_clipped": (
        "**行级**谓词:紧挨着**这一行**端点外侧的那个交易日,有源说它还在成分里、"
        "但第三源说它那天不在市(已退市 / 尚未上市)—— 这一端是被**在市窗口**裁掉的,"
        "不是指数调仓。"
    ),
    "n_trading_days": "本段覆盖的交易日数(闭区间,两端都算)。",
    "in_date_compact": "`in_date` 的 8 位 `YYYYMMDD` 字符串形态,供直接 join 湖。",
    "out_date_compact": "`out_date` 的 8 位 `YYYYMMDD` 字符串形态,供直接 join 湖。",
}

#: `agreement_basis` 的全部取值:``key -> (agreement_flag, 判据说明)``。
#: **产物里不许出现这张表之外的值**;`ops/test_universe_pit.py` 会核。
AGREEMENT_BASIS: dict[str, tuple[bool | None, str]] = {
    "both_sources_agree": (
        True,
        "两源都说这段在成分内。最强的一档。",
    ),
    "tolerated_boundary_lag": (
        True,
        "单源段,但它紧贴同一次进出里的 `both` 段(是这次进出的头或尾),"
        f"且长度 <= cfg.BOUNDARY_TOL_TD={cfg.BOUNDARY_TOL_TD} 个交易日 —— "
        "这正是源A 月末快照粒度相对源B 生效日的系统性滞后,是**约定差,不是数据错误**。",
    ),
    "source_b_base_period_gap": (
        False,
        "只有源A 说在,且整段落在源B 的**基期缺口**内(源B 在该宇宙的成员数"
        f"低于名义规模的 {BASE_PERIOD_MIN_FILL:.0%})。源B 已登记为缺陷 B-01"
        "(csi1000 在 2015-05-29 之前只有 3 个成员)。**这段该信源A。**",
    ),
    "source_a_before_first_snapshot": (
        False,
        "只有源B 说在,且整段早于源A 在该宇宙的**首期快照**——源A 那时还没有数据,"
        "不是它说'不在'。**这段该信源B。**",
    ),
    "boundary_lag_beyond_tolerance": (
        False,
        "单源段且贴着 `both` 段,但长度超过一个快照周期 —— "
        "已经不能用月末粒度解释,**必须逐条查**。",
    ),
    "interior_single_source_hole": (
        False,
        "单源段夹在同一次进出的两个 `both` 段**中间**:一源在中途挖了个洞。"
        "不是边界对不齐,是整段的有无之差。",
    ),
    "whole_run_single_source": (
        False,
        "整整一次进出**只有一个源**说它发生过,另一源全程说不在。"
        "常见成因:代码映射(同一实体两源用不同 ts_code)、"
        "源B 换仓格点粗漏掉的临时调整。",
    ),
    "single_source_universe": (
        None,
        "这个宇宙只有一个来源(`all` = 第三源 stock_basic 的在市窗口),"
        "**没有第二源可对**,一致性不适用。",
    ),
}


# ==========================================================================
# 交易日网格
# ==========================================================================


class Grid:
    """交易日网格。**一切区间比较都在这上面做**,单位是"第几个交易日"。

    刻意在本模块自己建一份(而不是 import 卡 1.1-reconcile 的),
    是为了让依赖方向保持"报告依赖产物,产物不依赖报告";
    `ops/test_universe_pit.py::test_grid_matches_reconcile_grid`
    断言两份逐日相同,防漂移。
    """

    __slots__ = ("days", "compact", "_index")

    def __init__(self, days: Sequence[dt.date]) -> None:
        self.days: tuple[dt.date, ...] = tuple(days)
        self.compact: tuple[str, ...] = tuple(d.strftime("%Y%m%d") for d in self.days)
        self._index: dict[dt.date, int] = {d: i for i, d in enumerate(self.days)}

    def __len__(self) -> int:
        return len(self.days)

    def floor(self, day: dt.date) -> int | None:
        """不晚于 `day` 的最后一个交易日序号;没有就 None。"""
        i = bisect.bisect_right(self.days, day) - 1
        return i if i >= 0 else None

    def ceil(self, day: dt.date) -> int | None:
        """不早于 `day` 的第一个交易日序号;没有就 None。"""
        i = bisect.bisect_left(self.days, day)
        return i if i < len(self.days) else None

    def index_of(self, day: dt.date) -> int | None:
        return self._index.get(day)


def load_grid(conn: Any | None = None) -> Grid:
    """从湖 `trade_cal` 读交易日,截到 `cfg.FREEZE_DATE`(红线 7)。

    走 `snapshots.lake` 而不是自己 `duckdb.connect`:湖是活的,外部 ETL 的瞬时
    `.wal` 会让只读打开偶发失败,`lake` 里带重试;而且"全仓库只有 lake 一处连湖"
    本身是卡 0.2 立的护栏(`ops/test_lake_baseline.py` 会扫)。
    """
    raw = lake.query(
        f"SELECT cal_date FROM {CALENDAR_VIEW} "  # noqa: S608
        "WHERE is_open = 1 AND cal_date <= ? ORDER BY cal_date",
        [lake.FREEZE_DATE_COMPACT],
        conn=conn,
    )["cal_date"].tolist()
    days = [dt.date(int(s[:4]), int(s[4:6]), int(s[6:8])) for s in raw]
    if not days:
        raise lake.LakeError(f"{CALENDAR_VIEW} 里没有截到冻结线的交易日,数据出事了。")
    return Grid(days)


def merge_touching(segments: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    """把网格上相邻/重叠的段并起来。

    判据是"两段之间**不含任何交易日**"(``next.start <= cur.end + 1``),
    不是"日历日相接" —— 后者会把跨周末的真实空档漏掉,前者才是网格语义。
    源B 是贴片式(每个 epoch 一行),不合并就会把"一直在成分内"读成几十次进出。
    """
    out: list[tuple[int, int]] = []
    for start, end in sorted(segments):
        if out and start <= out[-1][1] + 1:
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((start, end))
    return out


# ==========================================================================
# 三个源的装载
# ==========================================================================


def load_listing_windows(
    grid: Grid, conn: Any | None = None
) -> tuple[dict[str, tuple[int, int]], dict[str, Any]]:
    """第三源:每只票的**在市窗口**,投影到交易日网格。

    口径 ``list_date <= D < delist_date``(左闭右开)。为什么右端开:
    湖 `daily` 在 `delist_date` **当天及之后零行**(实测 277 只有行情的退市票,
    没有一只的最后一根 K 线 >= delist_date),所以退市日当天已经不可交易,
    把它算进"在市"会造出一个**没有行情的持仓日**。

    ⚠️ `stock_basic` 是**多快照**表:catalog view 把 19 个 `snapshot_date`
    分区**全部 union** 上来(实测 111,799 行 / 5,890 个 code ≈ 19 行/码)。
    直接 join 会把行数乘 19。实测 `list_date` / `delist_date` / `list_status`
    在 19 个快照之间**零漂移**,所以 ``SELECT DISTINCT`` 之后恰好一码一行
    (5,890 / 5,890)—— 这个恒等式在下面被断言,漂移了就报错,不静默。

    Returns:
        ``({code: (i0, i1)}, diag)``。窗口完全落在网格之外的票不出现在字典里。
    """
    df = lake.query(
        f"SELECT DISTINCT ts_code, list_status, list_date, delist_date "  # noqa: S608
        f"FROM {BASIC_VIEW}",
        conn=conn,
    )
    n_codes = int(df["ts_code"].nunique())
    if len(df) != n_codes:
        dupes = sorted(df.loc[df["ts_code"].duplicated(), "ts_code"].unique())[:10]
        raise lake.LakeError(
            f"{BASIC_VIEW} DISTINCT 之后仍然一码多行({len(df)} 行 / {n_codes} 码);"
            f" 说明 list_date/delist_date/list_status 在多快照之间**漂移了**,"
            f" 例如 {dupes}。'字段回溯'这条路的前提没了,先查湖再跑。"
        )
    bad = df[
        df["delist_date"].notna() & (df["delist_date"] <= df["list_date"])
    ]
    if len(bad):
        raise lake.LakeError(
            f"{BASIC_VIEW} 里有 {len(bad)} 只票 delist_date <= list_date,"
            f" 例如 {sorted(bad['ts_code'])[:5]} —— 在市窗口是空的,数据出事了。"
        )

    first, last = grid.days[0], grid.days[-1]
    windows: dict[str, tuple[int, int]] = {}
    n_all_before = n_not_yet = 0
    for row in df.itertuples(index=False):
        ld = _parse_compact(row.list_date)
        dd = _parse_compact(row.delist_date) if row.delist_date else None
        if dd is not None and dd <= first:
            n_all_before += 1  # 网格开始之前就退了,整只票在窗口外
            continue
        if ld > last:
            n_not_yet += 1  # 冻结线之后才上市
            continue
        i0 = grid.ceil(ld)
        # 右端开区间:最后一个在市交易日 = 不晚于 (delist_date - 1 天) 的那个
        i1 = len(grid) - 1 if dd is None else grid.floor(dd - dt.timedelta(days=1))
        if i0 is None or i1 is None or i1 < i0:
            n_not_yet += 1
            continue
        windows[row.ts_code] = (i0, i1)
    diag = {
        "view": BASIC_VIEW,
        "convention": "list_date <= D < delist_date(左闭右开);证据见 docstring",
        "n_codes_in_view": n_codes,
        "n_codes_with_window_in_grid": len(windows),
        "n_codes_delisted_before_grid": n_all_before,
        "n_codes_outside_grid_other": n_not_yet,
        "n_still_listed_at_freeze": sum(
            1 for i0, i1 in windows.values() if i1 == len(grid) - 1
        ),
        # 只数**真的进了 `all` 宇宙**的票:整只票在网格之前就退市的不算,
        # 否则这个数(1662)会和产物里的 left_censored 计数(1602)对不上,
        # 而数据卡把两者放在同一节里,读者一定会去对。
        "n_listed_before_grid_start": sum(
            1
            for r in df.itertuples(index=False)
            if r.ts_code in windows and r.list_date < grid.compact[0]
        ),
        "multi_snapshot_note": (
            f"{BASIC_VIEW} 是多快照表(19 个 snapshot_date 分区被 view 全部 union),"
            "直接 join 会把行数乘 19;DISTINCT 之后一码一行这件事在代码里被断言。"
        ),
    }
    return windows, diag


def _parse_compact(s: str) -> dt.date:
    return dt.date(int(s[:4]), int(s[4:6]), int(s[6:8]))


def load_source_a(
    grid: Grid,
) -> tuple[dict[str, dict[str, list[tuple[int, int]]]], dict[str, Any]]:
    """源A 产物 → 网格段。``out_date IS NULL``(右截断)按冻结线收口。"""
    df = pd.read_parquet(cfg.UNIVERSE_INTERVALS_PARQUET)
    last = len(grid) - 1
    segs: dict[str, dict[str, list[tuple[int, int]]]] = collections.defaultdict(
        lambda: collections.defaultdict(list)
    )
    dropped = 0
    first_snapshot: dict[str, str] = {}
    for row in df.itertuples(index=False):
        i0 = grid.ceil(_parse_compact(row.in_date))
        i1 = last if not isinstance(row.out_date, str) else grid.floor(
            _parse_compact(row.out_date)
        )
        if i0 is None or i1 is None or i1 < i0:
            dropped += 1
            continue
        segs[row.universe][row.code].append((i0, i1))
        cur = first_snapshot.get(row.universe)
        if cur is None or row.in_date < cur:
            first_snapshot[row.universe] = row.in_date
    merged_away = 0
    out: dict[str, dict[str, list[tuple[int, int]]]] = {}
    for uni, per_code in segs.items():
        out[uni] = {}
        for code, s in per_code.items():
            m = merge_touching(s)
            merged_away += len(s) - len(m)
            out[uni][code] = m
    diag = {
        "path_relative_to_root": str(
            cfg.UNIVERSE_INTERVALS_PARQUET.relative_to(cfg.GENEBENCH_ROOT)
        ),
        "rows": int(len(df)),
        "n_null_out_date_right_censored": int(df["out_date"].isna().sum()),
        "n_rows_dropped_off_grid": dropped,
        "n_segments_merged_away": merged_away,
        "merge_is_noop": merged_away == 0,
        "first_snapshot_by_universe": first_snapshot,
        "date_form_in_source": "字符串 YYYYMMDD;out_date IS NULL = 右截断",
    }
    return out, diag


def load_source_b(
    grid: Grid,
) -> tuple[dict[str, dict[str, list[tuple[int, int]]]], dict[str, Any]]:
    """源B 产物 → 网格段,**只取三个基准宇宙**,并合并贴片行。"""
    df = pd.read_parquet(source_b.parquet_path())
    total = int(len(df))
    ignored = sorted(set(df["universe"]) - set(cfg.UNIVERSES))
    df = df[df["universe"].isin(cfg.UNIVERSES)]
    segs: dict[str, dict[str, list[tuple[int, int]]]] = collections.defaultdict(
        lambda: collections.defaultdict(list)
    )
    dropped = 0
    for row in df.itertuples(index=False):
        i0, i1 = grid.ceil(row.in_date), grid.floor(row.out_date)
        if i0 is None or i1 is None or i1 < i0:
            dropped += 1
            continue
        segs[row.universe][row.code].append((i0, i1))
    raw = merged = 0
    out: dict[str, dict[str, list[tuple[int, int]]]] = {}
    for uni, per_code in segs.items():
        out[uni] = {}
        for code, s in per_code.items():
            m = merge_touching(s)
            raw += len(s)
            merged += len(m)
            out[uni][code] = m
    diag = {
        "path_relative_to_root": str(
            source_b.parquet_path().relative_to(cfg.GENEBENCH_ROOT)
        ),
        "rows_all_universes": total,
        "rows_in_compared_universes": int(len(df)),
        "universes_ignored": ignored,
        "n_rows_dropped_off_grid": dropped,
        "n_rows_on_grid": raw,
        "n_segments_after_merge": merged,
        "date_form_in_source": f"date32;out_date == {cfg.FREEZE_DATE} = 右删失",
        "merge_note": (
            "源B 是贴片式:同一 code 在每个 epoch 各占一行,相邻行首尾相接。"
            "不合并就会把'一直在成分内'读成几十次进出。"
        ),
        "off_grid_note": (
            "掉出网格的行绝大多数是**源B 早于交易日历起点 2009-01-05 的历史**"
            "(csi300 回溯到 2005-04-08、csi500 到 2007-01-31)。湖 trade_cal 只从 "
            "2009-01-05 起,那段没有网格可展开 —— 不是丢数,是**表达不了**,"
            "对应的段在产物里表现为 left_censored。"
        ),
    }
    return out, diag


# ==========================================================================
# 合成
# ==========================================================================


def _b_member_counts(
    grid: Grid, b_segs: dict[str, dict[str, list[tuple[int, int]]]]
) -> dict[str, np.ndarray]:
    """源B 在每个宇宙、每个交易日上的成员数 —— 用来识别**基期缺口**。"""
    out: dict[str, np.ndarray] = {}
    for uni in cfg.UNIVERSES:
        cnt = np.zeros(len(grid), dtype=np.int32)
        for segs in b_segs.get(uni, {}).values():
            for i0, i1 in segs:
                cnt[i0 : i1 + 1] += 1
        out[uni] = cnt
    return out


def _runs_of_true(mask: np.ndarray) -> list[tuple[int, int]]:
    """布尔数组里连续 True 的极大区段 ``[(i0, i1), ...]``(闭区间)。"""
    if not mask.any():
        return []
    padded = np.concatenate(([False], mask, [False]))
    diff = np.diff(padded.astype(np.int8))
    starts = np.flatnonzero(diff == 1)
    ends = np.flatnonzero(diff == -1) - 1
    return list(zip(starts.tolist(), ends.tolist()))


def _constant_runs(labels: np.ndarray, i0: int, i1: int) -> list[tuple[int, int, int]]:
    """``labels[i0..i1]`` 里取值恒定的极大子段 ``[(start, end, label), ...]``。"""
    out: list[tuple[int, int, int]] = []
    start = i0
    cur = int(labels[i0])
    for k in range(i0 + 1, i1 + 1):
        v = int(labels[k])
        if v != cur:
            out.append((start, k - 1, cur))
            start, cur = k, v
    out.append((start, i1, cur))
    return out


#: 标签编码:1 = 只有源A,2 = 只有源B,3 = 两源都有,4 = 第三源兜底。
_LABEL_SOURCE: dict[int, str] = {
    1: "index_weight",
    2: "qlib_instruments",
    3: "both",
    4: "basic_fallback",
}


def build_pit(
    grid: Grid,
    a_segs: dict[str, dict[str, list[tuple[int, int]]]],
    b_segs: dict[str, dict[str, list[tuple[int, int]]]],
    windows: dict[str, tuple[int, int]],
    a_first_idx: dict[str, int],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """合成最终区间表。**成员 = (A ∪ B) ∩ 在市窗口**,再按来源切片。

    Args:
        grid: 交易日网格。
        a_segs / b_segs: 两源的网格段。
        windows: 第三源的在市窗口 ``{code: (i0, i1)}``。
        a_first_idx: 每宇宙源A 首期快照在网格上的序号 —— 早于它的单源B 段
            归 ``source_a_before_first_snapshot``(源A 那时没数据,不是它说"不在")。

    Returns:
        ``(frame, diag)``。`frame` 列见 `PIT_COLUMNS`。
    """
    n = len(grid)
    b_counts = _b_member_counts(grid, b_segs)
    base_gap: dict[str, np.ndarray] = {
        uni: b_counts[uni] < cfg.UNIVERSE_NOMINAL_SIZE[uni] * BASE_PERIOD_MIN_FILL
        for uni in cfg.UNIVERSES
    }

    # 每个宇宙"两源覆盖的第一个交易日" —— 左截断的判据。
    window_start: dict[str, int] = {}
    for uni in cfg.UNIVERSES:
        b_min = min(
            (i0 for segs in b_segs.get(uni, {}).values() for i0, _ in segs),
            default=None,
        )
        cands = [c for c in (a_first_idx.get(uni), b_min) if c is not None]
        window_start[uni] = min(cands) if cands else 0
    window_start[cfg.MARKET_UNIVERSE] = 0

    rows: list[dict[str, Any]] = []
    counters = collections.Counter()
    clipped_days = collections.Counter()
    dropped_codes: dict[str, list[str]] = collections.defaultdict(list)

    for uni in cfg.UNIVERSES:
        codes = sorted(set(a_segs.get(uni, {})) | set(b_segs.get(uni, {})))
        for code in codes:
            a_mask = np.zeros(n, dtype=bool)
            for i0, i1 in a_segs.get(uni, {}).get(code, []):
                a_mask[i0 : i1 + 1] = True
            b_mask = np.zeros(n, dtype=bool)
            for i0, i1 in b_segs.get(uni, {}).get(code, []):
                b_mask[i0 : i1 + 1] = True
            raw = a_mask | b_mask

            alive = np.zeros(n, dtype=bool)
            win = windows.get(code)
            if win is not None:
                alive[win[0] : win[1] + 1] = True
            member = raw & alive

            removed = int((raw & ~alive).sum())
            if removed:
                clipped_days[uni] += removed
                clipped_days[f"{uni}::a_only"] += int(
                    (raw & ~alive & a_mask & ~b_mask).sum()
                )
                clipped_days[f"{uni}::b_only"] += int(
                    (raw & ~alive & b_mask & ~a_mask).sum()
                )
            if win is None:
                dropped_codes[uni].append(code)
            if not member.any():
                continue

            labels = np.where(member, a_mask.astype(np.int8) + 2 * b_mask, 0)
            for seg_idx, (r0, r1) in enumerate(_runs_of_true(member)):
                parts = _constant_runs(labels, r0, r1)
                has_both = any(lab == 3 for _, _, lab in parts)
                for part_idx, (p0, p1, lab) in enumerate(parts):
                    flag, basis = _classify_part(
                        lab=lab,
                        p0=p0,
                        p1=p1,
                        part_idx=part_idx,
                        n_parts=len(parts),
                        has_both=has_both,
                        base_gap=base_gap[uni],
                        a_first=a_first_idx.get(uni, 0),
                    )
                    counters[basis] += 1
                    rows.append(
                        _row(
                            grid=grid,
                            code=code,
                            universe=uni,
                            i0=p0,
                            i1=p1,
                            source=_LABEL_SOURCE[lab],
                            flag=flag,
                            basis=basis,
                            segment_idx=seg_idx,
                            part_idx=part_idx,
                            # 截断标记是**行级**谓词,不是段级:说的是"**这一行的**
                            # 端点撞到了可观测边界",不是"这一行所属的那次进出撞到了"。
                            # 段级会让一次进出的头部 part 也带上 right_censored,
                            # 于是 `right_censored` 与 `out_date == 冻结线` 不再等价,
                            # 下游只能靠猜(实测差 179 行)。
                            left_censored=p0 == window_start[uni],
                            right_censored=p1 == n - 1,
                            # 同样是**行级**谓词:紧挨着**这一行**端点外侧的那个交易日,
                            # 是不是"有源说它在成分里、但它那天不在市"。段级会把一次
                            # 进出里所有 part 都染上,读者无法定位到底是哪一端被裁的。
                            listing_clipped=(
                                (p0 > 0 and bool(raw[p0 - 1]) and not bool(alive[p0 - 1]))
                                or (
                                    p1 < n - 1
                                    and bool(raw[p1 + 1])
                                    and not bool(alive[p1 + 1])
                                )
                            ),
                        )
                    )

    # ---- 市场全集宇宙:第三源单干 ----
    for code in sorted(windows):
        i0, i1 = windows[code]
        counters["single_source_universe"] += 1
        rows.append(
            _row(
                grid=grid,
                code=code,
                universe=cfg.MARKET_UNIVERSE,
                i0=i0,
                i1=i1,
                source="basic_fallback",
                flag=None,
                basis="single_source_universe",
                segment_idx=0,
                part_idx=0,
                left_censored=i0 == 0,
                right_censored=i1 == n - 1,
                listing_clipped=False,
            )
        )

    frame = _finalize(rows)
    diag = {
        "membership_rule": "(源A ∪ 源B) ∩ 第三源在市窗口",
        "n_rows": int(len(frame)),
        "agreement_basis_counts": dict(sorted(counters.items())),
        "member_days_removed_by_listing_filter": {
            k: int(v) for k, v in sorted(clipped_days.items())
        },
        "codes_with_no_listing_window": {
            uni: sorted(v) for uni, v in dropped_codes.items() if v
        },
        "window_start_grid_index": window_start,
        "window_start_date": {
            u: grid.compact[i] for u, i in window_start.items()
        },
        # 只数**该宇宙窗口之内**的基期缺口日:窗口之前源B 当然是 0 个成员,
        # 把那些天也算进"缺口"会得到一个虚高、无法解释的数字。
        "source_b_base_gap_trading_days": {
            uni: int(base_gap[uni][window_start[uni] :].sum())
            for uni in cfg.UNIVERSES
        },
        "source_b_base_gap_last_day": {
            uni: (
                grid.compact[
                    int(np.flatnonzero(base_gap[uni][window_start[uni] :])[-1])
                    + window_start[uni]
                ]
                if base_gap[uni][window_start[uni] :].any()
                else None
            )
            for uni in cfg.UNIVERSES
        },
        "base_period_min_fill": BASE_PERIOD_MIN_FILL,
    }
    return frame, diag


def _classify_part(
    *,
    lab: int,
    p0: int,
    p1: int,
    part_idx: int,
    n_parts: int,
    has_both: bool,
    base_gap: np.ndarray,
    a_first: int,
) -> tuple[bool | None, str]:
    """一个 part 的 ``(agreement_flag, agreement_basis)``。判定顺序即优先级。"""
    if lab == 3:
        return True, "both_sources_agree"
    if lab == 4:  # pragma: no cover - `all` 宇宙走的是另一条路
        return None, "single_source_universe"

    # 结构性覆盖缺口优先于"边界滞后" —— 它们不是精度问题,是某一源那时没数据。
    if lab == 1 and bool(base_gap[p0 : p1 + 1].all()):
        return False, "source_b_base_period_gap"
    if lab == 2 and p1 < a_first:
        return False, "source_a_before_first_snapshot"

    if not has_both:
        return False, "whole_run_single_source"
    if part_idx not in (0, n_parts - 1):
        return False, "interior_single_source_hole"
    if (p1 - p0 + 1) <= cfg.BOUNDARY_TOL_TD:
        return True, "tolerated_boundary_lag"
    return False, "boundary_lag_beyond_tolerance"


def is_canonical(universe: str, source: str, basis: str) -> bool:
    """这一行属不属于**主力读法**(实施稿方案甲)。

    实施稿 D4 定的是「宇宙源方案甲:**月末快照 diff 自建为主**、
    qlib community instruments **交叉对账**」—— 源A 是主力,源B 是对账方,
    不是并列的第二个成员来源。

    如果直接把并集当成宇宙,会在两源边界不齐的日子上**把宇宙撑大到名义值以上**
    (实测 csi300 在 2011-01-04 有 326 只、csi500 在 2010-01-04 有 550 只)。
    那不是"更全",那是"两个互相矛盾的答案都算数"。

    所以并集照样入表(信息不丢、来源可查),但另开一列说明"主力读法要不要它":

    * ``all`` 宇宙:只有一个源,全部是 canonical。
    * ``both`` / ``index_weight``:源A 说在 → canonical。
    * ``qlib_instruments``:**只有**在源A 该宇宙**首期之前**才 canonical
      (那段源A 根本没有数据,不是它说"不在")。其余 qlib-only 段是
      源B 相对源A 的**领先/滞后**,属对账信息,不进主力读法。
    """
    if universe == cfg.MARKET_UNIVERSE:
        return True
    if source in ("both", "index_weight"):
        return True
    return basis == "source_a_before_first_snapshot"


def _row(
    *,
    grid: Grid,
    code: str,
    universe: str,
    i0: int,
    i1: int,
    source: str,
    flag: bool | None,
    basis: str,
    segment_idx: int,
    part_idx: int,
    left_censored: bool,
    right_censored: bool,
    listing_clipped: bool,
) -> dict[str, Any]:
    return {
        "code": code,
        "universe": universe,
        "in_date": grid.days[i0],
        "out_date": grid.days[i1],
        "source": source,
        "agreement_flag": flag,
        "agreement_basis": basis,
        "canonical": is_canonical(universe, source, basis),
        "segment_id": f"{universe}|{code}|{segment_idx}|{part_idx}",
        "segment_idx": segment_idx,
        "part_idx": part_idx,
        "left_censored": left_censored,
        "right_censored": right_censored,
        "listing_clipped": listing_clipped,
        "n_trading_days": i1 - i0 + 1,
        "in_date_compact": grid.compact[i0],
        "out_date_compact": grid.compact[i1],
    }


def _finalize(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """定型:列顺序、dtype、排序。确定性可复现(不依赖字典序以外的任何东西)。"""
    frame = pd.DataFrame(rows, columns=list(PIT_COLUMNS))
    frame["ambiguous"] = _mark_ambiguous(frame)
    if frame.empty:  # pragma: no cover
        return frame
    order = {u: i for i, u in enumerate(cfg.UNIVERSES_PIT)}
    frame = (
        frame.assign(_u=frame["universe"].map(order))
        .sort_values(["_u", "code", "segment_idx", "part_idx"], kind="mergesort")
        .drop(columns="_u")
        .reset_index(drop=True)
    )
    for col in ("code", "universe", "source", "agreement_basis", "segment_id",
                "in_date_compact", "out_date_compact"):
        frame[col] = frame[col].astype("string")
    for col in ("segment_idx", "part_idx", "n_trading_days"):
        frame[col] = frame[col].astype("int32")
    for col in ("canonical", "left_censored", "right_censored", "listing_clipped"):
        frame[col] = frame[col].astype("bool")
    # 可空布尔:`all` 宇宙的 agreement_flag 是 NULL(不适用),不是 False。
    frame["agreement_flag"] = frame["agreement_flag"].astype("boolean")
    return frame


#: 产物 schema。日期用 date32(权威口径),另带一份 YYYYMMDD 字符串供 join 湖。
PARQUET_SCHEMA = pa.schema(
    [
        pa.field("code", pa.string(), nullable=False),
        pa.field("universe", pa.string(), nullable=False),
        pa.field("in_date", pa.date32(), nullable=False),
        pa.field("out_date", pa.date32(), nullable=False),
        pa.field("source", pa.string(), nullable=False),
        pa.field("agreement_flag", pa.bool_(), nullable=True),
        pa.field("agreement_basis", pa.string(), nullable=False),
        pa.field("segment_id", pa.string(), nullable=False),
        pa.field("segment_idx", pa.int32(), nullable=False),
        pa.field("part_idx", pa.int32(), nullable=False),
        pa.field("canonical", pa.bool_(), nullable=False),
        pa.field("left_censored", pa.bool_(), nullable=False),
        pa.field("right_censored", pa.bool_(), nullable=False),
        pa.field("listing_clipped", pa.bool_(), nullable=False),
        pa.field("n_trading_days", pa.int32(), nullable=False),
        pa.field("in_date_compact", pa.string(), nullable=False),
        pa.field("out_date_compact", pa.string(), nullable=False),
        pa.field("ambiguous", pa.bool_(), nullable=False),
    ]
)

#: 护栏：`pa.Table.from_pandas(frame, schema=PARQUET_SCHEMA)` 会把**不在 schema 里的
#: 列静默丢掉** —— 不报错、文件大小都不变。踩过一次（加 `ambiguous` 列时列没进产物、
#: 只有下游 KeyError 才暴露）。所以这里钉死两者等价，漏一个立刻在 import 期就炸。
_SCHEMA_NAMES = tuple(f.name for f in PARQUET_SCHEMA)
if set(_SCHEMA_NAMES) != set(PIT_COLUMNS):
    raise RuntimeError(
        f"PARQUET_SCHEMA 与 PIT_COLUMNS 对不上："
        f"只在 schema {sorted(set(_SCHEMA_NAMES) - set(PIT_COLUMNS))}，"
        f"只在 PIT_COLUMNS {sorted(set(PIT_COLUMNS) - set(_SCHEMA_NAMES))}。"
        f"加列时两处都要改，否则新列会被 from_pandas 静默丢掉。"
    )


# ==========================================================================
# 第三源的佐证面:namechange
# ==========================================================================


def namechange_evidence(
    codes: Iterable[str], conn: Any | None = None
) -> dict[str, Any]:
    """`namechange` 对第三源的佐证与**证伪**。

    两件事:

    1. **佐证退市口径。** ``change_reason = '退市整理期'`` 的那些区间应当落在
       `delist_date` **之前**。落在之后就说明我们的裁剪点错了。
    2. **证伪 stock_basic 的历史完整性(这条更重要)。** 湖里的 `stock_basic`
       用**当前** ts_code 回溯改写历史:公司改了代码,旧码就**整条消失**。
       实测源B 里有 5 个 code(`000022.SZ` `000043.SZ` `300114.SZ` `601313.SH`
       `T00018.SH`)在 `stock_basic` 里**根本不存在**,在 `namechange` 里也查不到 ——
       它们当年确实在市、确实是成分股。这意味着 `all` 宇宙(以及任何按 `list_date`
       回溯出来的历史)会**系统性低估**早期的市场规模,漏掉的正是那些后来改过码的实体。
    """
    nc = lake.query(
        f"SELECT ts_code, name, start_date, end_date, change_reason "  # noqa: S608
        f"FROM {NAMECHANGE_VIEW}",
        conn=conn,
    )
    basic = lake.query(
        f"SELECT DISTINCT ts_code, list_date, delist_date FROM {BASIC_VIEW}",  # noqa: S608
        conn=conn,
    )
    delist_of = {
        r.ts_code: r.delist_date
        for r in basic.itertuples(index=False)
        if r.delist_date
    }
    list_of = {r.ts_code: r.list_date for r in basic.itertuples(index=False)}

    phase = nc[nc["change_reason"] == "退市整理期"]
    late = [
        {"code": r.ts_code, "phase_start": r.start_date, "delist_date": delist_of[r.ts_code]}
        for r in phase.itertuples(index=False)
        if r.ts_code in delist_of and r.start_date > delist_of[r.ts_code]
    ]
    earliest = nc.groupby("ts_code")["start_date"].min().to_dict()
    before_list = [
        {"code": c, "earliest_namechange": s, "list_date": list_of[c]}
        for c, s in earliest.items()
        if c in list_of and s < list_of[c]
    ]
    wanted = sorted(set(codes))
    known = set(list_of)
    missing = [c for c in wanted if c not in known]
    return {
        "view": NAMECHANGE_VIEW,
        "n_rows": int(len(nc)),
        "n_codes": int(nc["ts_code"].nunique()),
        "delist_phase_rows": int(len(phase)),
        "delist_phase_after_delist_date": late,
        "delist_phase_check": (
            "PASS —— 退市整理期全部落在 delist_date 之前,在市窗口的右端裁剪点站得住。"
            if not late
            else "FAIL —— 有退市整理期落在 delist_date 之后,裁剪点要重查。"
        ),
        "n_codes_with_namechange_before_list_date": len(before_list),
        "namechange_before_list_date_examples": before_list[:10],
        "codes_absent_from_stock_basic": missing,
        "codes_absent_from_stock_basic_note": (
            "这些 code 在源A/源B 里出现过,但湖 stock_basic 里**没有** —— "
            "`stock_basic` 用当前 ts_code 回溯改写历史,改过码的公司只留新码、"
            "旧码整条消失(namechange 里同样查不到)。所以第三源不是历史注册表,"
            "它兜不住'当年用旧码在市'的实体;这些 code 在本表里被在市窗口过滤掉了。"
        ),
    }


# ==========================================================================
# 读取入口(唯一安全的读法)
# ==========================================================================


def parquet_metadata(grid: Grid) -> dict[bytes, bytes]:
    """写进 parquet **schema metadata** 的口径指纹。

    摘要 JSON 与数据卡都在 repo 里,parquet 单独流转时**带不走**。
    拿到 parquet 的人必须能只从文件本身知道它的有效区间与安全读法。
    """
    meta = {
        "genebench_card": "1.1",
        "table": "universe_pit",
        "generator": "snapshots/universe_build.py",
        "freeze_line": cfg.FREEZE_DATE,
        "valid_from": grid.days[0].isoformat(),
        "valid_to": grid.days[-1].isoformat(),
        "calendar": f"{CALENDAR_VIEW}(is_open=1,SSE),截到冻结线",
        "n_trading_days": str(len(grid)),
        "universes": ",".join(cfg.UNIVERSES_PIT),
        "interval_closure": "闭区间 [in_date, out_date],两端都含;out_date 永不为空",
        "right_censored_note": (
            "out_date == valid_to 且 right_censored=True 表示'截至冻结线仍在',"
            "不是'当天被调出'"
        ),
        "safe_reader": "snapshots.universe_build.universe_at(universe, date)",
        "data_card": str(cfg.UNIVERSE_PIT_CARD.relative_to(cfg.REPO)),
        "warning": (
            "数进出次数用 distinct segment_idx,不要数行数 —— "
            "一次进出会被来源切成多个 part。"
        ),
    }
    return {k.encode(): str(v).encode() for k, v in meta.items()}


#: 对账产物里第 5 类的键名。改这里之前先看 `universe_reconcile.RUN_CLASSES`。
AMBIGUOUS_CLASS: str = "one_side_whole_segment"


def ambiguous_spans(path: Path | None = None) -> list[dict[str, Any]]:
    """**权威**的模糊区段清单：对账第 5 类的全量区段。

    为什么不用 `universe_pit` 的 `ambiguous` 列当权威：canonical 口径下
    有的分歧段**根本没有对应行**（例：`300114.SZ` 只有源B 说它在市，
    源A 没有这段，于是 universe_pit 里查无此段）。生成器如果只看列，
    就会以为这个 `(code, 时段)` 干净可用 —— 而它恰恰是两源打架的地方。

    Returns:
        每条 ``{universe, code, only_in_source, edge_kind, start, end, n_trading_days}``，
        `start`/`end` 是 ISO 日期，闭区间。
    """
    target = path or (cfg.OPS / "universe_reconciliation.json")
    if not target.exists():
        raise FileNotFoundError(
            f"没有对账产物 {target}；先跑 `python -m snapshots.universe_reconcile`"
        )
    data = json.loads(target.read_text(encoding="utf-8"))
    cls = data.get("divergence_classes", {}).get(AMBIGUOUS_CLASS, {})
    runs = cls.get("runs")
    if runs is None:
        raise KeyError(
            f"对账产物里 {AMBIGUOUS_CLASS} 没有 `runs` 字段（只有 examples）。"
            f"重跑对账生成器 —— 拿 examples 打标记会漏掉一半区段。"
        )
    if len(runs) != cls.get("n_runs"):
        raise ValueError(
            f"runs 有 {len(runs)} 条但 n_runs={cls.get('n_runs')}，对不上"
        )
    return runs


def ambiguous_member_days(path: Path | None = None) -> int:
    """模糊区段一共覆盖多少个成员日。用来对账（M1 签字口径是 791）。"""
    return sum(int(r["n_trading_days"]) for r in ambiguous_spans(path))


def is_ambiguous(universe: str, code: str, day: "str | dt.date") -> bool:
    """这个 ``(universe, code, 交易日)`` 是否落在模糊区段里。"""
    d = _parse_compact(day) if isinstance(day, str) and len(day) == 8 else day
    if isinstance(d, str):
        d = dt.date.fromisoformat(d)
    for r in ambiguous_spans():
        if r["universe"] == universe and r["code"] == code:
            if dt.date.fromisoformat(r["start"]) <= d <= dt.date.fromisoformat(r["end"]):
                return True
    return False


def _mark_ambiguous(frame: pd.DataFrame) -> pd.Series:
    """行级保守标记：本段与任一模糊区段有交集即 True。"""
    flag = pd.Series(False, index=frame.index)
    try:
        runs = ambiguous_spans()
    except (FileNotFoundError, KeyError, ValueError):
        # 对账产物还没生成时不阻断建表 —— 但摘要里会记 ambiguous_source 为 None，
        # 验收测试会因此报红，不会静默放过。
        return flag
    for r in runs:
        lo = dt.date.fromisoformat(r["start"])
        hi = dt.date.fromisoformat(r["end"])
        hit = (
            (frame["universe"] == r["universe"])
            & (frame["code"] == r["code"])
            & (frame["in_date"] <= hi)
            & (frame["out_date"] >= lo)
        )
        flag |= hit
    return flag


def read_pit(
    path: Path | None = None,
) -> tuple[pd.DataFrame, dict[str, str]]:
    """读回产物 + 它的 schema metadata。``(frame, meta)``。"""
    target = path or cfg.UNIVERSE_PIT_PARQUET
    raw = pq.ParquetFile(target).schema_arrow.metadata or {}
    meta = {k.decode(): v.decode() for k, v in raw.items() if k != b"pandas"}
    return pd.read_parquet(target), meta


def universe_at(
    universe: str,
    date: str | dt.date,
    *,
    frame: pd.DataFrame | None = None,
    meta: dict[str, str] | None = None,
    scope: str = "canonical",
    exclude_ambiguous: bool = False,
) -> list[str]:
    """**唯一安全的读法**:取 `universe` 在交易日 `date` 的成员。

    裸写 ``in_date <= D <= out_date`` 在两个方向上都**静默**:``D`` 超过冻结线
    会安静地给你冻结线那天的名单,``D`` 早于数据起点会安静地给你空集。
    本函数对越界的 `date` **抛错**。

    Args:
        universe: `cfg.UNIVERSES_PIT` 之一。
        date: ``YYYYMMDD`` 字符串或 `datetime.date`。
        frame / meta: 已读好的产物;不给就现读。
        scope: ``canonical``(默认,实施稿方案甲的主力读法:源A 为主,
            宇宙规模回到名义值)或 ``union``(全部来源的并集,**会超过名义值**)。

    Returns:
        升序去重的成员代码列表。

    Raises:
        ValueError: `universe` / `scope` 不认识,或 `date` 落在
            ``[valid_from, valid_to]`` 之外。
    """
    if universe not in cfg.UNIVERSES_PIT:
        raise ValueError(
            f"不认识的宇宙 {universe!r};有的是 {list(cfg.UNIVERSES_PIT)}"
        )
    if scope not in SCOPES:
        raise ValueError(f"不认识的 scope {scope!r};有的是 {list(SCOPES)}")
    if isinstance(date, dt.date):
        day = date
    elif isinstance(date, str) and len(date) == 8 and date.isdigit():
        day = _parse_compact(date)
    else:
        raise ValueError(f"date 必须是 8 位 YYYYMMDD 字符串或 date,拿到 {date!r}")
    if frame is None or meta is None:
        frame, meta = read_pit()
    lo = dt.date.fromisoformat(meta["valid_from"])
    hi = dt.date.fromisoformat(meta["valid_to"])
    if not (lo <= day <= hi):
        raise ValueError(
            f"universe_pit 的有效区间是 [{lo}, {hi}],查询日 {day} 在区间外。"
            f" 越界查询在本表上**不会**自然报错(晚于上界返回冻结线那天的名单、"
            f" 早于下界返回空集),所以这里显式拦下。冻结线是红线 7。"
        )
    sel = frame[frame["universe"] == universe]
    if scope == "canonical":
        sel = sel[sel["canonical"]]
    hit = sel[(sel["in_date"] <= day) & (sel["out_date"] >= day)]
    codes = sorted(set(hit["code"].tolist()))
    if exclude_ambiguous:
        # 用**跨度表**而不是行级列：canonical 口径下有的分歧段没有对应行，
        # 只看列会漏掉（见 `ambiguous_spans` 的 docstring）。
        blocked = {
            r["code"]
            for r in ambiguous_spans()
            if r["universe"] == universe
            and dt.date.fromisoformat(r["start"]) <= day
            <= dt.date.fromisoformat(r["end"])
        }
        codes = [c for c in codes if c not in blocked]
    return codes


def universe_size_on(
    frame: pd.DataFrame, universe: str, day: dt.date, *, scope: str = "canonical"
) -> int:
    """某宇宙在某天的成员数(去重 code)。抽查用。"""
    sel = frame[frame["universe"] == universe]
    if scope == "canonical":
        sel = sel[sel["canonical"]]
    sel = sel[(sel["in_date"] <= day) & (sel["out_date"] >= day)]
    return int(sel["code"].nunique())


def daily_size_stats(
    frame: pd.DataFrame, grid: Grid, *, scope: str = "canonical"
) -> dict[str, Any]:
    """**每一个交易日**上的宇宙规模统计 —— 不是只在抽查日看。

    抽查日很容易全部落在"两源恰好一致"的日子上;分歧几乎全部藏在快照日之间。
    这里用扫描线在整条网格上展开,给 min / max / 直方图 / 偏离名义值的日期清单。
    """
    n = len(grid)
    out: dict[str, Any] = {}
    idx = {d: i for i, d in enumerate(grid.days)}
    for uni in cfg.UNIVERSES_PIT:
        sel = frame[frame["universe"] == uni]
        if scope == "canonical":
            sel = sel[sel["canonical"]]
        # 同一 code 的多个 part 会在同一天重复计数 —— 先按 code 去重再展开。
        delta = np.zeros(n + 1, dtype=np.int32)
        for code, g in sel.groupby("code", sort=False):
            spans = merge_touching(
                [(idx[r.in_date], idx[r.out_date]) for r in g.itertuples(index=False)]
            )
            for i0, i1 in spans:
                delta[i0] += 1
                delta[i1 + 1] -= 1
        size = np.cumsum(delta[:n])
        nominal = cfg.UNIVERSE_NOMINAL_SIZE.get(uni)
        active = size > 0
        off = []
        hist: dict[str, int] | None = None
        if nominal is not None:
            # key 用**字符串**:JSON 往返会把 int key 变成 str,
            # 数据卡是从摘要渲染的,int key 会让"重放必须逐字相同"这条断言假红。
            hist = {
                str(int(k)): int(v)
                for k, v in zip(*np.unique(size[active], return_counts=True))
            }
            bad_idx = np.flatnonzero(active & (size != nominal))
            for i in bad_idx[:50]:
                off.append({"date": grid.compact[int(i)], "size": int(size[int(i)])})
        block: dict[str, Any] = {
            "scope": scope,
            "nominal": nominal,
            "n_days_with_members": int(active.sum()),
            "min": int(size[active].min()) if active.any() else 0,
            "max": int(size[active].max()) if active.any() else 0,
            "n_days_off_nominal": (
                int((active & (size != nominal)).sum()) if nominal else None
            ),
            "days_off_nominal_first50": off,
        }
        if hist is not None:
            block["size_histogram"] = {
                k: hist[k] for k in sorted(hist, key=int)
            }
        else:
            # `all` 宇宙没有名义值,规模逐日单调爬升 —— 全直方图有近千个桶,
            # 塞进 JSON 只会把它撑成噪声。给每年首个交易日的规模就够了。
            year_first: dict[str, int] = {}
            for i, d in enumerate(grid.days):
                year_first.setdefault(str(d.year), int(size[i]))
            block["size_by_year_first_trading_day"] = year_first
        out[uni] = block
    return out


# ==========================================================================
# 摘要
# ==========================================================================


def summarize(
    frame: pd.DataFrame,
    grid: Grid,
    diags: dict[str, Any],
) -> dict[str, Any]:
    """摘要 JSON:口径 + 逐宇宙统计 + 抽查成员数 + 完整性自查。"""
    probe_days = _probe_days(grid)
    per_universe: dict[str, Any] = {}
    for uni in cfg.UNIVERSES_PIT:
        sel = frame[frame["universe"] == uni]
        runs = sel.groupby(["code", "segment_idx"]).ngroups
        per_universe[uni] = {
            "n_rows": int(len(sel)),
            "n_membership_runs": int(runs),
            "n_distinct_codes": int(sel["code"].nunique()),
            "nominal_size": cfg.UNIVERSE_NOMINAL_SIZE.get(uni),
            "first_in_date": str(sel["in_date"].min()) if len(sel) else None,
            "last_out_date": str(sel["out_date"].max()) if len(sel) else None,
            "n_left_censored": int(sel["left_censored"].sum()),
            "n_right_censored": int(sel["right_censored"].sum()),
            "n_listing_clipped": int(sel["listing_clipped"].sum()),
            "source_counts": {
                k: int(v) for k, v in sel["source"].value_counts().sort_index().items()
            },
            "agreement_counts": {
                "true": int((sel["agreement_flag"] == True).sum()),  # noqa: E712
                "false": int((sel["agreement_flag"] == False).sum()),  # noqa: E712
                "null": int(sel["agreement_flag"].isna().sum()),
            },
            "agreement_basis_counts": {
                k: int(v)
                for k, v in sel["agreement_basis"]
                .value_counts()
                .sort_index()
                .items()
            },
            "n_canonical_rows": int(sel["canonical"].sum()),
            "member_days": int(sel["n_trading_days"].sum()),
            "size_on_probe_days": {
                d.isoformat(): universe_size_on(frame, uni, d, scope="canonical")
                for d in probe_days
            },
            "size_on_probe_days_union": {
                d.isoformat(): universe_size_on(frame, uni, d, scope="union")
                for d in probe_days
            },
            "n_codes_with_multiple_runs": int(
                (sel.groupby("code")["segment_idx"].nunique() > 1).sum()
            ),
            "max_runs_per_code": int(
                sel.groupby("code")["segment_idx"].nunique().max()
            )
            if len(sel)
            else 0,
        }

    return {
        "card": "1.1",
        "title": "PIT 宇宙收口表 universe_pit:三源合并",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(
            timespec="seconds"
        ),
        "generator": "snapshots/universe_build.py",
        "freeze_line": cfg.FREEZE_DATE,
        "calendar": {
            "view": CALENDAR_VIEW,
            "n_trading_days": len(grid),
            "first": grid.days[0].isoformat(),
            "last": grid.days[-1].isoformat(),
            "note": "湖 trade_cal 只有 SSE 一个交易所;A 股两所日历一致。",
        },
        "membership_rule": "(源A ∪ 源B) ∩ 第三源在市窗口",
        "boundary_tolerance_trading_days": cfg.BOUNDARY_TOL_TD,
        "base_period_min_fill": BASE_PERIOD_MIN_FILL,
        "columns": COLUMN_DOC,
        "agreement_basis_legend": {
            k: {"agreement_flag": v[0], "why": v[1]}
            for k, v in AGREEMENT_BASIS.items()
        },
        "sources": diags,
        "universes": per_universe,
        "daily_size": {
            "canonical": daily_size_stats(frame, grid, scope="canonical"),
            "union": daily_size_stats(frame, grid, scope="union"),
            "note": (
                "在**每一个**交易日上展开后数的,不是只在抽查日看。"
                "canonical(方案甲主力读法)回到名义值;union 会在两源边界不齐的"
                "日子上撑大到名义值以上 —— 这正是为什么要有 `canonical` 这一列。"
            ),
        },
        "needs_manual_review": _needs_review(frame),
        "totals": {
            "n_rows": int(len(frame)),
            "n_canonical_rows": int(frame["canonical"].sum()),
            "n_membership_runs": int(frame.groupby(
                ["universe", "code", "segment_idx"]
            ).ngroups),
            "n_distinct_codes": int(frame["code"].nunique()),
            "member_days": int(frame["n_trading_days"].sum()),
        },
        "integrity": _integrity(frame, grid),
    }


#: 这几类分歧**不能**用约定差解释,是残余的"必须逐条查"集合。
_REVIEW_BASES: tuple[str, ...] = (
    "boundary_lag_beyond_tolerance",
    "interior_single_source_hole",
    "whole_run_single_source",
)


def _needs_review(frame: pd.DataFrame) -> dict[str, Any]:
    """把残余的"必须逐条查"行整个列出来 —— 不做汇总就掩盖,列出来才有人去查。"""
    sel = frame[frame["agreement_basis"].isin(_REVIEW_BASES)]
    items = [
        {
            "universe": r.universe,
            "code": r.code,
            "in_date": r.in_date_compact,
            "out_date": r.out_date_compact,
            "n_trading_days": int(r.n_trading_days),
            "source": r.source,
            "agreement_basis": r.agreement_basis,
            "canonical": bool(r.canonical),
        }
        for r in sel.sort_values(
            ["n_trading_days", "universe", "code"], ascending=[False, True, True]
        ).itertuples(index=False)
    ]
    return {
        "note": (
            "这三类是**不能**用两源约定差解释的残余分歧,应当逐条人工核。"
            "它们不是'脏数据'的同义词 —— 多数是代码映射(同一实体两源用不同 ts_code)"
            "或源B 换仓格点粗漏掉的临时调整,逐条判断见 "
            "ops/reports/universe_reconciliation.md 的人工签字清单。"
        ),
        "bases": list(_REVIEW_BASES),
        "n_rows": int(len(sel)),
        "n_member_days": int(sel["n_trading_days"].sum()),
        "by_basis": {
            k: int(v) for k, v in sel["agreement_basis"].value_counts().items()
        },
        "rows": items,
    }


def _probe_days(grid: Grid) -> list[dt.date]:
    """抽查日:确定性挑选,不用随机数 —— 换机器重跑必须是同一批。

    取每个自然年的**第一个交易日**,再加上网格首日与末日(冻结线)。
    """
    seen: dict[int, dt.date] = {}
    for d in grid.days:
        seen.setdefault(d.year, d)
    days = sorted({grid.days[0], grid.days[-1], *seen.values()})
    return days


def _integrity(frame: pd.DataFrame, grid: Grid) -> dict[str, Any]:
    """完整性自查:算术自洽的那些事,摘要里直接给数,不让人自己去数。"""
    idx = {d: i for i, d in enumerate(grid.days)}
    overlaps = 0
    bad_order = 0
    run_gap_missing = 0
    part_not_contiguous = 0
    for (_uni, _code), g in frame.groupby(["universe", "code"], sort=False):
        g = g.sort_values(["in_date", "out_date"], kind="mergesort")
        prev_end = None
        prev_seg = None
        for row in g.itertuples(index=False):
            i0, i1 = idx[row.in_date], idx[row.out_date]
            if i1 < i0:
                bad_order += 1
            if prev_end is not None:
                if i0 <= prev_end:
                    overlaps += 1
                elif row.segment_idx == prev_seg and i0 != prev_end + 1:
                    part_not_contiguous += 1
                elif row.segment_idx != prev_seg and i0 == prev_end + 1:
                    run_gap_missing += 1
            prev_end, prev_seg = i1, row.segment_idx
    return {
        "n_overlapping_rows": overlaps,
        "n_out_before_in": bad_order,
        "n_parts_not_contiguous_within_run": part_not_contiguous,
        "n_adjacent_runs_without_real_gap": run_gap_missing,
        "n_rows_beyond_freeze": int((frame["out_date"] > grid.days[-1]).sum()),
        "n_rows_before_grid": int((frame["in_date"] < grid.days[0]).sum()),
        "n_duplicate_segment_ids": int(len(frame) - frame["segment_id"].nunique()),
        "n_unknown_source_values": int(
            (~frame["source"].isin(cfg.UNIVERSE_SOURCES)).sum()
        ),
        "n_unknown_agreement_basis": int(
            (~frame["agreement_basis"].isin(AGREEMENT_BASIS)).sum()
        ),
        "n_code_format_violations": int(
            (~frame["code"].str.match(r"^\d{6}\.(SH|SZ|BJ)$")).sum()
        ),
        "n_compact_mismatch": int(
            (
                frame["in_date_compact"]
                != frame["in_date"].map(lambda d: d.strftime("%Y%m%d"))
            ).sum()
            + (
                frame["out_date_compact"]
                != frame["out_date"].map(lambda d: d.strftime("%Y%m%d"))
            ).sum()
        ),
    }


# ==========================================================================
# 数据卡(生成,不手写)
# ==========================================================================


def render_data_card(summary: dict[str, Any]) -> str:
    """把摘要渲染成人读数据卡。

    **刻意生成而不是手写**:数据卡里的每个数字都必须是这次产出现算的,
    手写的数字会在下一次重建时静默过期,而数据卡恰恰是别人唯一会读的东西。
    """
    s = summary
    uni = s["universes"]
    src = s["sources"]
    cal = s["calendar"]
    L: list[str] = []
    add = L.append

    add("# 数据卡:`universe_pit` —— PIT 宇宙收口表")
    add("")
    add(
        f"卡 **1.1** · 生成于 `{s['generated_at_utc']}` · 冻结线 `{s['freeze_line']}` · "
        f"实现 `{s['generator']}` · 机器可读版 `ops/universe_pit.json`"
    )
    add("")
    add(
        "> **下游只该读这一张表。** `index_weight_intervals.parquet`(源A)与 "
        "`qlib_instruments_intervals.parquet`(源B)是对账中间产物,不是回测输入。"
    )
    add("")
    add("---")
    add("")

    # ---- 1 来源与构建方法 ----
    add("## 1. 来源与构建方法")
    add("")
    add("| 源 | 数据 | 在本表里的角色 | 产物 |")
    add("| --- | --- | --- | --- |")
    add(
        f"| A | 湖 `index_weight` 月末快照相邻期 diff | 成分**存在性**(主力) | "
        f"`{src['source_a']['path_relative_to_root']}`,{src['source_a']['rows']:,} 行 |"
    )
    add(
        f"| B | qlib community `instruments` | 成分**边界精度** + 左端回溯 | "
        f"`{src['source_b']['path_relative_to_root']}`,"
        f"{src['source_b']['rows_in_compared_universes']:,} 行(三宇宙) |"
    )
    add(
        f"| C | 湖 `stock_basic` 的 `list_date`/`delist_date` + `namechange` | "
        f"**在不在市**(兜底与闸门) | catalog view,"
        f"{src['listing']['n_codes_in_view']:,} 只票 |"
    )
    add("")
    add(f"**合成规则:`{s['membership_rule']}`**,再按\"哪些源这么说\"把每次进出切成片段。")
    add("")
    add("*为什么是并集不是交集。* 交集会删掉两块真东西:")
    add("")
    add(
        f"1. csi1000 在源B 的**基期缺口**里(该宇宙成员数低于名义规模的 "
        f"{s['base_period_min_fill']:.0%},共 "
        f"{src['pit']['source_b_base_gap_trading_days']['csi1000']:,} 个交易日)"
        f"只有 3 个成员,是上游的伪区间;交集会把这一整段抹掉。"
    )
    add(
        f"2. csi300 / csi500 在 `{cal['first']}`~源A 首期之间只有源B 有数据"
        f"(源A 首期 = `{src['source_a']['first_snapshot_by_universe'].get('csi300')}`);"
        f"交集会把源A 的左截断永久固化。"
    )
    add("")
    add(
        "*为什么必须有第三源这道闸门。* 并集会带进源B 的一类系统性错误:"
        "**已退市的票还留在成分名单里**。第三源按 `list_date <= D < delist_date` "
        "把这些日子裁掉 —— 右端取开区间是因为湖 `daily` 在 `delist_date` "
        "当天及之后**零行**,退市日当天已不可交易,算进\"在市\"就会造出没有行情的持仓日。"
    )
    add("")
    add("本次裁掉的成员日:")
    add("")
    add("| 宇宙 | 被在市窗口裁掉的成员日 | 其中只有源A 说在 | 其中只有源B 说在 |")
    add("| --- | ---: | ---: | ---: |")
    clip = src["pit"]["member_days_removed_by_listing_filter"]
    for u in cfg.UNIVERSES:
        add(
            f"| {u} | {clip.get(u, 0):,} | {clip.get(f'{u}::a_only', 0):,} | "
            f"{clip.get(f'{u}::b_only', 0):,} |"
        )
    add("")
    nc = src["namechange"]
    add(
        f"第三源的佐证:`namechange` 里 {nc['delist_phase_rows']:,} 条\"退市整理期\","
        f"落在 `delist_date` **之后**的有 {len(nc['delist_phase_after_delist_date'])} 条 —— "
        f"{nc['delist_phase_check']}"
    )
    add("")

    # ---- 2 区间约定 ----
    add("## 2. 区间约定的精确定义")
    add("")
    add(
        f"* **闭区间 `[in_date, out_date]`,两端都含。** 过滤写 "
        f"`in_date <= D and D <= out_date`。"
    )
    add(
        f"* **时间轴是交易日网格**(湖 `{cal['view']}`,`is_open=1`,截到冻结线):"
        f"`{cal['first']}` … `{cal['last']}`,共 **{cal['n_trading_days']:,}** 个交易日。"
        f"端点一定是交易日 —— 源B 的自然日端点(大量落在周末/节假日)先投影:"
        f"`in` 取不早于它的第一个交易日,`out` 取不晚于它的最后一个交易日。"
    )
    add(
        f"* **`out_date` 永不为空。** 仍在成分内的段 `out_date = {cal['last']}` "
        f"**且** `right_censored = True`,两件事必须一起读。"
    )
    add(
        "* **日期两种形态,同一件事。** `in_date`/`out_date` 是 `date32`(权威口径);"
        "`in_date_compact`/`out_date_compact` 是 8 位 `YYYYMMDD` 字符串,"
        "专供直接和湖里的 `trade_date`(VARCHAR)join。**不要自己转** —— "
        "湖的 gold parquet 里 `trade_date` 是 DATE、catalog view 里是 VARCHAR,"
        "自己转必踩其中一个。"
    )
    add("* **`code` 一律湖内形态 `600000.SH`**,不是 qlib 的 `SH600000`。")
    add("")
    add("### 2.1 一次进出会被切成多行")
    add("")
    add(
        "一只票在同一宇宙里可以多次进出,每次进出是一个 **membership run**,"
        "`segment_idx` 从 0 起。**同一次进出内部**,如果两源的说法在中途变了"
        "(源B 说 6 月 30 日就进来了、源A 要等到 7 月 31 日才看见),"
        "这次进出会再被切成若干 **part**,`part_idx` 从 0 起,"
        "每个 part 的 `source` / `agreement_flag` 是常数。"
    )
    add("")
    add(
        f"> ⚠️ **数\"这只票进出过几次\"要数 distinct `segment_idx`,不要数行数。** "
        f"全表 {s['totals']['n_rows']:,} 行 = {s['totals']['n_membership_runs']:,} 次进出"
        f"被来源切片后的结果。数行数会把一次进出的两端滞后读成三次进出。"
    )
    add("")
    add("判\"某天在不在\"则不用管分片:同一次进出的各 part 在网格上首尾相接。")
    add("")
    add("### 2.2 列")
    add("")
    add("| 列 | 含义 |")
    add("| --- | --- |")
    for col in PIT_COLUMNS:
        add(f"| `{col}` | {COLUMN_DOC[col]} |")
    add("")

    # ---- 3 两源分歧 ----
    add("## 3. 两源分歧的处理策略与容忍口径")
    add("")
    add(
        "**分歧不投票、不取平均、不悄悄挑一个。** 两源都保留在并集里,"
        "分歧被显式记在 `source` / `agreement_flag` / `agreement_basis` 三列上,"
        "由下游按自己的风险偏好选择。"
    )
    add("")
    add("**容忍口径(本表最需要写清楚的一条)。**")
    add("")
    add(
        f"源B 的 `in_date` 是成分调整的**生效日**(落在月中);源A 最早也要等到生效日"
        f"之后的第一期**月末快照**才看得见。这段滞后是源A 约定写死的**分辨率上限**,"
        f"不是数据错误。一个自然月约 20~23 个交易日,取上界 "
        f"**{s['boundary_tolerance_trading_days']} 个交易日**"
        f"(`cfg.BOUNDARY_TOL_TD`)。判据是三条**同时**成立:"
    )
    add("")
    add("1. 这个 part 是单源的(`source != 'both'`);")
    add("2. 它紧贴着同一次进出里的一个 `both` part(是这次进出的**头或尾**,中间挖洞的不算);")
    add(f"3. 它的长度 `n_trading_days <= {s['boundary_tolerance_trading_days']}`。")
    add("")
    add("三条都成立 → `agreement_flag = True` / `tolerated_boundary_lag`。")
    add("超过一个快照周期就不再能用月末粒度解释,归 `boundary_lag_beyond_tolerance` 判 `False`。")
    add("")
    add("`agreement_basis` 的全部取值与它对应的 `agreement_flag`:")
    add("")
    add("| `agreement_basis` | `agreement_flag` | 行数 | 判据 |")
    add("| --- | :-: | ---: | --- |")
    total_basis: dict[str, int] = collections.Counter()
    for u in cfg.UNIVERSES_PIT:
        for k, v in uni[u]["agreement_basis_counts"].items():
            total_basis[k] += v
    for key, (flag, why) in AGREEMENT_BASIS.items():
        shown = {True: "`True`", False: "`False`", None: "`NULL`"}[flag]
        add(f"| `{key}` | {shown} | {total_basis.get(key, 0):,} | {why} |")
    add("")

    # ---- 3.1 canonical ----
    add("### 3.1 `canonical`:并集入表,但主力读法只认源A")
    add("")
    add(
        "实施稿 D4 定的是「宇宙源**方案甲**:月末快照 diff **自建为主**、"
        "qlib community instruments **交叉对账**」—— 源A 是主力,源B 是对账方,"
        "不是并列的第二个成员来源。"
    )
    add("")
    add(
        "**直接把并集当宇宙会出事:**两源边界不齐的日子上,宇宙会被撑大到名义值以上。"
        "这不是\"更全\",是\"两个互相矛盾的答案都算数\"。实测(在**每一个**交易日上展开):"
    )
    add("")
    add("| 宇宙 | 名义值 | union 规模 min/max | union 偏离名义值的交易日 | canonical 规模 min/max | canonical 偏离名义值的交易日 |")
    add("| --- | ---: | --- | ---: | --- | ---: |")
    ds = s["daily_size"]
    for u in cfg.UNIVERSES:
        cu, un = ds["canonical"][u], ds["union"][u]
        add(
            f"| {u} | {cu['nominal']:,} | {un['min']:,} / **{un['max']:,}** | "
            f"**{un['n_days_off_nominal']:,}** | {cu['min']:,} / {cu['max']:,} | "
            f"{cu['n_days_off_nominal']:,} |"
        )
    add("")
    add(
        "所以并集照样入表(信息不丢、来源可查),但另开一列 `canonical` 说明"
        "\"主力读法要不要它\"。True 的三种情形:"
    )
    add("")
    add("1. `all` 宇宙(只有一个源);")
    add("2. 源A 说在(`source` 是 `both` 或 `index_weight`);")
    add(
        "3. `source == 'qlib_instruments'` **且** "
        "`agreement_basis == 'source_a_before_first_snapshot'` —— "
        "那段源A 根本没有数据,不是它说\"不在\"。"
    )
    add("")
    add(
        f"全表 {s['totals']['n_rows']:,} 行里 **{s['totals']['n_canonical_rows']:,} 行**是 canonical。"
        f"`universe_at()` **默认 `scope='canonical'`**;要并集显式传 `scope='union'`。"
    )
    add("")
    cs = ds["canonical"]
    if any(cs[u]["n_days_off_nominal"] for u in cfg.UNIVERSES):
        add("**canonical 也不是恒等于名义值**,而且这个缺口是**对的**:")
        add("")
        add("| 宇宙 | 偏离名义值的交易日 | 规模分布 | 缺口从哪来 |")
        add("| --- | ---: | --- | --- |")
        for u in cfg.UNIVERSES:
            add(
                f"| {u} | {cs[u]['n_days_off_nominal']:,} | "
                f"`{cs[u]['size_histogram']}` | 见下 |"
            )
        add("")
        add(
            "两个成因,都不是 bug:"
            "(a)**指数真空缺** —— csi300 在 2009-12-31~2010-01-28 的 20 个交易日只有 298,"
            "是 2009-12-29 两只票同日吸收合并退市留下的 2 席空缺(权重和仍是 99.993);"
            "(b)**退市与调仓之间的空窗** —— 成分股在月中退市,源A 的 LOCF 约定会把它"
            "持有到下一期月末快照,而第三源在 `delist_date` 当天就把它切掉。"
            "这段日子里\"名义 300 只\"里有 1~2 只**已经不可交易**,"
            "本表如实给出可交易的那些。"
        )
        add("")
        add(
            "> 所以 **`assert len(universe) == nominal` 在任何 scope 下都是错的**。"
            "允许的范围是 `[nominal - 2, nominal]`(实测),"
            "`ops/test_universe_pit.py` 把它钉成断言。"
        )
    else:  # pragma: no cover
        add("> canonical 在每一个交易日上都恰好等于名义值。")
    add("")

    # ---- 3.2 残余 ----
    rev = s["needs_manual_review"]
    add("### 3.2 残余的\"必须逐条查\"")
    add("")
    add(
        f"扣掉两源约定差(`tolerated_boundary_lag`)、源B 基期缺口"
        f"(`source_b_base_period_gap`)、源A 首期之前(`source_a_before_first_snapshot`)"
        f"这三类**已经解释清楚**的分歧之后,残余 **{rev['n_rows']} 行 / "
        f"{rev['n_member_days']:,} 个成员日**:"
    )
    add("")
    add("| `agreement_basis` | 行数 |")
    add("| --- | ---: |")
    for k, v in sorted(rev["by_basis"].items()):
        add(f"| `{k}` | {v:,} |")
    add("")
    add("最长的 10 条(逐条判断见 `ops/reports/universe_reconciliation.md` 的人工签字清单):")
    add("")
    add("| 宇宙 | code | 起 | 止 | 交易日 | 来源 | 类型 | canonical |")
    add("| --- | --- | --- | --- | ---: | --- | --- | :-: |")
    for r in rev["rows"][:10]:
        add(
            f"| {r['universe']} | `{r['code']}` | {r['in_date']} | {r['out_date']} | "
            f"{r['n_trading_days']:,} | `{r['source']}` | `{r['agreement_basis']}` | "
            f"{'是' if r['canonical'] else '否'} |"
        )
    add("")

    # ---- 4 覆盖范围 ----
    add("## 4. 覆盖范围与冻结线")
    add("")
    add("| 宇宙 | 行数 | 其中 canonical | 进出次数 | 去重 code | 起 | 止 | 左截断 | 右截断 | 在市窗口裁过 |")
    add("| --- | ---: | ---: | ---: | ---: | --- | --- | ---: | ---: | ---: |")
    for u in cfg.UNIVERSES_PIT:
        b = uni[u]
        add(
            f"| {u} | {b['n_rows']:,} | {b['n_canonical_rows']:,} | "
            f"{b['n_membership_runs']:,} | "
            f"{b['n_distinct_codes']:,} | {b['first_in_date']} | {b['last_out_date']} | "
            f"{b['n_left_censored']:,} | {b['n_right_censored']:,} | "
            f"{b['n_listing_clipped']:,} |"
        )
    add("")
    add("**逐宇宙的来源构成**(行数):")
    add("")
    add("| 宇宙 | `both` | `index_weight` | `qlib_instruments` | `basic_fallback` |")
    add("| --- | ---: | ---: | ---: | ---: |")
    for u in cfg.UNIVERSES_PIT:
        c = uni[u]["source_counts"]
        add(
            f"| {u} | {c.get('both', 0):,} | {c.get('index_weight', 0):,} | "
            f"{c.get('qlib_instruments', 0):,} | {c.get('basic_fallback', 0):,} |"
        )
    add("")
    add(
        "**抽查日的成员数**(每个自然年的第一个交易日 + 网格首末日;"
        "`canonical` 读法,括号里是 `union`):"
    )
    add("")
    probe = sorted(uni[cfg.UNIVERSES_PIT[0]]["size_on_probe_days"])
    add("| 日期 | " + " | ".join(cfg.UNIVERSES_PIT) + " |")
    add("| --- | " + " | ".join("---:" for _ in cfg.UNIVERSES_PIT) + " |")
    for d in probe:
        cells = []
        for u in cfg.UNIVERSES_PIT:
            c = uni[u]["size_on_probe_days"][d]
            n = uni[u]["size_on_probe_days_union"][d]
            cells.append(f"{c:,}" if c == n else f"{c:,} ({n:,})")
        add(f"| {d} | " + " | ".join(cells) + " |")
    add("")
    add(
        f"**冻结线 `{s['freeze_line']}`(红线 7)。** 交易日网格、三个源的区间、"
        f"`all` 宇宙的在市窗口,全部截到它。产物里不存在任何晚于它的日期。"
        f"parquet 的 schema metadata 里写了 `valid_from` / `valid_to`;"
        f"`universe_at()` 对越界的查询日**抛错**,而不是静默返回空集或末期名单。"
    )
    add("")

    # ---- 5 已知局限 ----
    add("## 5. 已知局限")
    # M1 签字裁定（ops/signoffs/M1.md）落在数据卡里的两条硬约束。
    # 放在本节最前面，因为它们是**用之前必须知道**的，不是补充说明。
    add(
        "### 5.0 M1 签字裁定的两条硬约束\n\n"
        "**① csi1000 的市场窗口起点不得早于 `2015-05-29`。**\n"
        "源B（qlib instruments）在该日之前对 csi1000 只有 3 个成员"
        "（名义规模 1000），整段是上游的伪区间（源B 文档 B-01）。"
        "本表的 csi1000 区间本身是源A 主导、从 `2014-10-31` 起就有，"
        "**但只要 v1 的任务或窗口用到 csi1000，起点一律取 `2015-05-29` 或更晚** "
        "—— 否则对账口径与建表口径会在同一批实验里打架。\n\n"
        "**② 月末快照粒度是已声明局限，v1 不混入源B 的日级边界。**\n"
        "源A 的 `in_date`/`out_date` 只能取到**月末快照**粒度：一次成分调整"
        "最晚要等到生效日之后的第一期月末快照才看得见，实测滞后在 23 个交易日以内。"
        "签字人认可这是约定的分辨率上限、不是数据错误，并裁定 **v1 边界策略维持源A**"
        "—— **不**把源B 的日级边界混进来。理由是口径一致性优先于分辨率："
        "混用会让『这只票哪天进的成分』在同一张表里出现两种精度。"
        "源B 日级边界**留作 v1.1 选项**，届时应作为独立口径并行提供，而不是就地替换。\n"
    )
    add("")
    add("### 5.1 月内调整被抹平(源A 的分辨率上限)")
    add("")
    add(
        "源A 的原始事实只有一种形状:\"某月末最后一个交易日,这只票在成分里\"。"
        "相邻两期 diff 得到的是\"在这两期之间的**某个时点**发生了变动\",**不是精确生效日**。"
        "中证的调仓生效日是 6 月/12 月第二个星期五的下一交易日(还有临时调整),落在月中;"
        "月末快照只能告诉你\"到月末为止,这只票在/不在\"。"
    )
    add("")
    add("**量级(卡 1.1 对抗审查实测,单位:段):**")
    add("")
    add("| 宇宙 | 窗内 qlib 起点数 | 入场日被推迟的 | 占比 | 推迟天数 min/p50/max |")
    add("| --- | ---: | ---: | ---: | --- |")
    add("| csi300 | 723 | **183** | 25.3% | 25 / 28 / 30 |")
    add("| csi500 | 1,766 | **254** | 14.4% | 21 / 28 / 30 |")
    add("| csi1000 | 3,346 | **0** | 0.0% | — |")
    add("")
    add(
        "换算成事件频率:csi300 约 **10.5 次/年**、csi500 约 **14.5 次/年**的调仓事件"
        "被推迟到下一个月末;**csi1000 的月末快照粒度几乎零成本**"
        "(中证 1000 的调仓切点本来就落在月末最后一个交易日)。"
    )
    add("")
    add(
        "**\"月中进、同月又出\"这种完全被抹平的成员:实测 0 段。** "
        "落在源A 时间窗内的 qlib 极大段,没有一段是整段夹在两期快照之间的。"
        "也就是说源A 抹掉的不是成员的**存在性**,而是成员的**日期** —— "
        "这把一条\"未知大小的坑\"降级成了\"已量化为零的坑\"。"
        "**但这条结论只对本数据成立**,换源必须重测。"
    )
    add("")
    add(
        "本表用并集把源B 的精确边界补了回来:被推迟的那些日子在表里表现为 "
        "`source = qlib_instruments` + `agreement_basis = tolerated_boundary_lag` 的 part。"
        "**要精确到日的下游应当用整个区间(含容忍段),而不是只用 `both`。**"
    )
    add("")
    add("### 5.2 左右截断的语义")
    add("")
    add(
        f"**左截断(`left_censored = True`)** = **这一行的** `in_date` 就是该宇宙的"
        f"**可观测下界**那一天,真实入场日更早或不可知。两个截断标记都是**行级**谓词,"
        f"不是段级 —— `right_censored` 与 `out_date == 冻结线` **严格等价**,"
        f"下游不用猜。(注意 `part_idx > 0` 的行的 `in_date` 也不是真实入场日,"
        f"但那是**来源切换**的边界而不是截断,看 `part_idx` 就能分辨。)"
    )
    add("")
    add("| 宇宙 | 可观测下界 | 为什么是它 |")
    add("| --- | --- | --- |")
    for u in cfg.UNIVERSES:
        add(
            f"| {u} | `{src['pit']['window_start_date'][u]}` | "
            f"源A 首期 `{src['source_a']['first_snapshot_by_universe'].get(u)}` 与"
            f"源B 在网格上的首日,取更早的那个 |"
        )
    add(
        f"| all | `{src['pit']['window_start_date'][cfg.MARKET_UNIVERSE]}` | "
        f"交易日历起点;`list_date` 早于它的票被网格裁掉左端"
        f"({src['listing']['n_listed_before_grid_start']:,} 只) |"
    )
    add("")
    add(
        "**左截断是比月内滞后大两个数量级的误差源。** 源B 能把 csi300 回溯到 "
        "2005-04-08、csi500 到 2007-01-31,但**湖 `trade_cal` 只从 2009-01-05 起**,"
        "那段没有交易日网格可展开 —— 不是丢数,是**表达不了**。实测:csi300 首期 300 只"
        "全部被低估了 **≥1,386 天**(≥3.8 年,且这是撞到 qlib 自己左边界后的**下界**,"
        "真实更长);csi500 466/500 被低估 ≤723 天;**csi1000 0/1000**"
        "(源B 首日与源A 首期同一天,一只都补不了)。"
        "**任何跨 2009 年初的回测,左截断的影响远大于月内抹平。**"
    )
    add("")
    add(
        f"**右截断(`right_censored = True`)** = 本段延续到冻结线 `{cal['last']}`,"
        f"**未观测到出场**。`out_date` 写的是冻结线本身而不是 NULL —— "
        f"这是刻意的:源A 用 NULL 表示\"区间开口\",那个约定在源A 内部是对的,"
        f"但它让 `in_date <= D <= out_date` 这种过滤在冻结线**之外**静默返回满额宇宙"
        f"(实测:查 2027 年、查公元 2999 年都安静地给你 300 只)。"
        f"收口表把上界写进数据里,再由 `universe_at()` 拦截越界查询。"
        f"**代价是 `out_date == {cal['last']}` 单独看会被误读成\"当天被调出\" —— "
        f"必须与 `right_censored` 一起读。**"
    )
    add("")
    add("### 5.3 第三源不是历史注册表")
    add("")
    add(
        "湖 `stock_basic` 用**当前** ts_code 回溯改写历史:公司改了代码,"
        "旧码就**整条消失**。实测源A/源B 里出现过、但 `stock_basic` 里查不到的 code:"
    )
    add("")
    if nc["codes_absent_from_stock_basic"]:
        add("```")
        add(", ".join(nc["codes_absent_from_stock_basic"]))
        add("```")
        add("")
    add(
        "它们当年确实在市、确实是成分股(卡 1.1 对账报告已把这 4 只**全部**配对到新码:"
        "`000022.SZ`→`001872.SZ` 招商港口、`000043.SZ`→`001914.SZ`、"
        "`300114.SZ`→`302132.SZ`、`601313.SH`→`601360.SH` 三六零),"
        "但在 `namechange` 里同样查不到。后果有两条,都要写明:"
    )
    add("")
    add(
        f"1. **这些 code 在本表里被在市窗口过滤掉了。** 它们没有 `list_date`,"
        f"在市窗口是空的,`(A ∪ B) ∩ 在市窗口` 的结果是空集。"
        f"影响面:**{len(set().union(*src['pit']['codes_with_no_listing_window'].values()) if src['pit']['codes_with_no_listing_window'] else set())} 个去重 code**,"
        f"逐宇宙 "
        + "、".join(
            f"{u} {len(v)} 个"
            for u, v in sorted(src["pit"]["codes_with_no_listing_window"].items())
        )
        + "。"
    )
    add(
        "2. **`all` 宇宙会系统性低估早期的市场规模**,漏掉的正是那些后来改过码的实体。"
        "所以 `all` 的成员数是\"当前注册表回溯出来的在市数\",不是\"当年真实的在市数\"。"
    )
    add("")
    add(
        f"另一层:`stock_basic` 是**多快照**表,只有 2026-08-05 起的 19 个快照,"
        f"**2026-08-05 之前的状态只能靠 `list_date`/`delist_date` 字段回溯**,"
        f"不能靠快照。实测这三个字段在 19 个快照之间**零漂移**"
        f"(代码里对此有断言,漂移了会报错而不是静默),所以字段回溯这条路目前是通的 ——"
        f"**但它回溯的是\"事实\",不是\"当时的认知\"**:2015 年的人不知道某只票会在 2020 年退市。"
        f"本表只用它判\"那天在不在市\"(这件事在那天本身就是可知的),"
        f"**不**用它做任何需要\"当时认知\"的判断。"
    )
    add("")
    add("### 5.4 其它")
    add("")
    add(
        "1. **两源同宗,这不是独立验证。** 源B 的上游 chenditc/investment_data 用 "
        "Tushare `index_weight` 生成成分区间,与湖里的 `index_weight` 是同一份原始数据。"
        "两源一致只说明两条加工链口径一致,**不能证明名单本身正确**;"
        "`agreement_flag = True` 的含义是\"两条加工链没打架\",不是\"这份名单是对的\"。"
    )
    add(
        "2. **`trade_cal` 只有 SSE 一个交易所。** 深市/北交所票用同一张日历展开。"
        "A 股两所日历一致,这个近似在本窗口内不产生误差,但不是零假设。"
    )
    add(
        "3. **归一化会吃掉真实的 1~3 天差。** 两源都投影到交易日网格,"
        "\"源B 说到周日、源A 说到上周五\"这种差异被消掉了 —— 这正是想要的(纯约定差),"
        "但如果下游要在非交易日上做判断,本表的一致率就不适用。"
    )
    add(
        f"4. **`all` 宇宙是\"上市状态\"口径,不是\"可交易\"口径。** 它包含北交所"
        f"(`stock_basic` 里 344 只)与停牌日。停牌在湖 `daily` 里是**缺行**不是显式标记,"
        f"本表**不**处理停牌 —— 要\"当天真的能成交\"必须自己 join `suspend_d` + `daily`。"
    )
    add(
        "5. **`agreement_basis` 的分类是结构性的,不是归因。** 它只回答\"这段在结构上"
        "属于哪一类分歧\",不回答\"谁对\"。逐条的对错判断在 "
        "`ops/reports/universe_reconciliation.md` 的人工签字清单里,那份需要人签字。"
    )
    add("")

    # ---- 6 不该拿它做什么 ----
    add("## 6. 不该拿它做什么")
    add("")
    add(
        "1. **不能做日内 / 月内成分变动研究。** 主力源的分辨率上限是月末快照粒度;"
        "源B 补回来的边界精度也只到\"生效日\"这一天,再细就没有了。"
        "任何需要\"某只票在某天盘中被调入\"的研究,本表给不出答案,"
        "而且会给出一个**看起来像答案的错答案**(端点会被对齐到月末或生效日)。"
    )
    add(
        "2. **不能当\"指数成分\"的权威。** 它是两条加工链的并集,不是中证指数公司的公告。"
        "两源同宗(见 §5.4.1),一致不等于正确。要权威口径必须去接指数公司的调整公告。"
    )
    add(
        "3. **不能用来算指数收益 / 做指数复制。** 本表**不含权重**"
        "(源A 的 `weight` 字段被刻意排除在产物之外:成分表只回答\"在不在\","
        "不回答\"占多少\")。等权重近似会和真实指数差得离谱。"
    )
    add(
        f"4. **不能跨冻结线用。** 有效区间是 `[{cal['first']}, {cal['last']}]`。"
        f"`universe_at()` 会拦;绕过它裸写过滤则不会报错 —— 那是静默的错误答案。"
    )
    add(
        "5. **不能拿 `all` 当\"当年的市场全集\"。** 见 §5.3:改过码的实体整条消失,"
        "早期规模被系统性低估。做横截面研究(市值分位、行业中性化)时,"
        "这个偏差会直接进到分位点里。"
    )
    add(
        "6. **不能把行数当进出次数。** 见 §2.1。这是本表最容易踩的坑,"
        "而且踩了之后结果看起来完全正常。"
    )
    add(
        f"7. **不能假设宇宙规模恒等于名义值。** 见 §3.1:canonical 读法下 csi300 有 "
        f"{cs['csi300']['n_days_off_nominal']} 个交易日、csi500 有 "
        f"{cs['csi500']['n_days_off_nominal']} 个、csi1000 有 "
        f"{cs['csi1000']['n_days_off_nominal']} 个不等于名义值(最多少 2 只)。"
        f"写 `assert len(univ) == 300` 会炸。"
    )
    add(
        "8. **不能用 `agreement_flag = False` 当\"脏数据\"的过滤条件。** 它的多数成员是"
        "**已经解释清楚**的结构性差异(源B 基期缺口、源A 首期之前),"
        "把它们当脏数据剔掉会丢掉真实成员。要挑\"两源都确认\"的子集,"
        "用 `source == 'both'`;要\"主力读法\",用 `canonical`;"
        "要\"可疑\",看 `agreement_basis` 是不是 §3.2 那三类。"
    )
    add(
        "9. **不能不看 `canonical` 就整表当宇宙用。** 见 §3.1:整表是并集,"
        "在两源边界不齐的日子上会把 csi300 撑到 "
        f"{ds['union']['csi300']['max']} 只、csi500 撑到 "
        f"{ds['union']['csi500']['max']} 只。"
    )
    add("")

    # ---- 7 复现 ----
    add("## 7. 复现")
    add("")
    add("```")
    add("cd $REPO")
    add("# 1) 重建产物 + 摘要 + 本数据卡")
    add("$GENEBENCH_ROOT/env/bin/python -m snapshots.universe_build")
    add("# 2) 验收测试")
    add("$GENEBENCH_ROOT/env/bin/python -m pytest ops/test_universe_pit.py -q")
    add("```")
    add("")
    add(
        "确定性:抽查日是\"每个自然年的第一个交易日 + 网格首末日\",不依赖随机数发生器;"
        "同样的三份输入必然得到逐字相同的产物与数据卡"
        "(除 `generated_at_utc` 一行)。"
    )
    add("")
    return "\n".join(L) + "\n"


# ==========================================================================
# 落盘
# ==========================================================================


def _write_private(path: Path, write: Any) -> dict[str, Any]:
    """原子 + 0600 写文件:先写同目录临时文件、chmod、再 `os.replace`。

    umask 是 002,裸写会落成组可读 —— 答案隔离靠的就是权限位(红线 5),
    所以每个产物文件都必须显式 chmod 600,不能指望 umask。
    """
    cfg.create_dir(path.parent)
    tmp = path.with_name(path.name + ".tmp")
    try:
        write(tmp)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        if tmp.exists():  # pragma: no cover
            tmp.unlink()
    data = path.read_bytes()
    return {
        "path": str(path),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "mode": oct(path.stat().st_mode & 0o777),
    }


def write_outputs(
    frame: pd.DataFrame, summary: dict[str, Any], grid: Grid
) -> dict[str, dict[str, Any]]:
    """写 parquet + 摘要 JSON + 数据卡。

    parquet 先写、把指纹塞回 summary,再写 JSON 与数据卡 ——
    这样 JSON / 数据卡里记的指纹永远指向同一次产出。
    """
    kv = parquet_metadata(grid)

    def _write_parquet(p: Path) -> None:
        table = pa.Table.from_pandas(
            frame, schema=PARQUET_SCHEMA, preserve_index=False
        )
        merged = dict(table.schema.metadata or {})
        merged.update(kv)
        pq.write_table(table.replace_schema_metadata(merged), p)

    art = _write_private(cfg.UNIVERSE_PIT_PARQUET, _write_parquet)
    art["rows"] = int(len(frame))
    art["columns"] = list(PIT_COLUMNS)
    art["schema_metadata"] = {k.decode(): v.decode() for k, v in kv.items()}
    summary["artifact"] = art

    card_text = render_data_card(summary)
    card = _write_private(
        cfg.UNIVERSE_PIT_CARD, lambda p: p.write_text(card_text, encoding="utf-8")
    )
    summary["data_card"] = card
    js = _write_private(
        cfg.UNIVERSE_PIT_JSON,
        lambda p: p.write_text(
            json.dumps(summary, ensure_ascii=False, indent=1, default=str) + "\n",
            encoding="utf-8",
        ),
    )
    return {"parquet": art, "data_card": card, "summary_json": js}


def build() -> tuple[pd.DataFrame, dict[str, Any], Grid]:
    """跑完整条链路:读三源 → 合成 → 出摘要。**不落盘**,便于测试直接调。"""
    lake.raise_open_file_limit()
    with lake.catalog() as con:
        grid = load_grid(conn=con)
        windows, listing_diag = load_listing_windows(grid, conn=con)
        a_segs, a_diag = load_source_a(grid)
        b_segs, b_diag = load_source_b(grid)
        a_first_idx = {
            uni: (grid.ceil(_parse_compact(d)) or 0)
            for uni, d in a_diag["first_snapshot_by_universe"].items()
        }
        frame, pit_diag = build_pit(grid, a_segs, b_segs, windows, a_first_idx)
        seen_codes = set(frame["code"]) | {
            c for per in (a_segs, b_segs) for u in per.values() for c in u
        }
        nc_diag = namechange_evidence(seen_codes, conn=con)
    summary = summarize(
        frame,
        grid,
        {
            "source_a": a_diag,
            "source_b": b_diag,
            "listing": listing_diag,
            "namechange": nc_diag,
            "pit": pit_diag,
        },
    )
    return frame, summary, grid


def main(argv: list[str] | None = None) -> int:
    """CLI 入口。``--dry-run`` 只算不写。"""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dry-run", action="store_true", help="只计算并打印摘要,不写任何文件"
    )
    args = parser.parse_args(argv)

    frame, summary, grid = build()
    for uni in cfg.UNIVERSES_PIT:
        u = summary["universes"][uni]
        print(
            f"{uni:8s} 行 {u['n_rows']:6d} | 进出 {u['n_membership_runs']:6d} "
            f"| 去重 code {u['n_distinct_codes']:5d} "
            f"| both {u['source_counts'].get('both', 0):6d} "
            f"| 一致 {u['agreement_counts']['true']:6d} "
            f"不一致 {u['agreement_counts']['false']:5d} "
            f"不适用 {u['agreement_counts']['null']:5d}"
        )
    bad = {k: v for k, v in summary["integrity"].items() if isinstance(v, int) and v}
    print(f"完整性自查非零项:{bad or '无(全部为 0)'}")

    if args.dry_run:
        print("--dry-run:未写任何文件")
        return 0

    written = write_outputs(frame, summary, grid)
    for kind, info in written.items():
        print(f"{kind:12s} -> {info['path']} ({info['bytes']} B, mode {info['mode']})")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
