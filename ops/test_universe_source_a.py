"""卡 1.1 源A 验收:index_weight 月末快照 diff → 成分区间。

跑法::

    cd $REPO && $GENEBENCH_ROOT/env/bin/python -m pytest ops/test_universe_source_a.py -v

判据从哪儿取数(沿用卡 0.2 补救定下的规矩:**产物不许自证**)
--------------------------------------------------------------
所有判据都**现场从只读 catalog 重算**,一个数都不从
`ops/universe_source_A.json` 里读。摘要 JSON 在这里是**被对账的一方**,
不是判据来源;`snapshots/universe_index_weight.py` 里的
`build_intervals()` 也**不被调用** —— 本文件自己用集合运算重写了一遍
"某天该有谁",拿它去卡 parquet。两份实现互为独立见证。

两条主判据,以及它们各自**管得住什么、管不住什么**(负控实测,不是推测)
----------------------------------------------------------------------
`test_pit_reconstruction_*`:对每个宇宙、每一期快照 T,"区间覆盖 T 的
code 集合"必须**逐字等于**湖里那期的名单。它钉死的是**多段切分**与
**左右截断** —— 少切一段、把缺口合并掉、截断标错,它立刻红。

但它**管不住 in_date / out_date 的约定选择**。这一点必须写明白,
否则就是又一个"假绿":三种候选约定在**快照日当天完全一致**
(``out=T_j`` 仍覆盖 T_j,``in=T_{i-1}+1`` 仍覆盖 T_i),
负控实测三者都是 **0/564 期失败**,一模一样地绿。

真正守约定的是 `test_universe_between_snapshots_*`:
它专挑**两期快照之间**的交易日(每个间隔取"T_k 的次交易日"和
"T_{k+1} 的前交易日"两端,确定性枚举、不抽样),断言宇宙 =
"不晚于该日的最后一期快照"。负控实测:
把 out_date 换成"最后一次出现的那期"→ 月中大面积对不上(宇宙缩水);
把 in_date 换成"上一期的次日"→ 同样对不上(提前一个月建仓)。
**改约定必须先让这条红,再谈改不改。**

注意:本测试**要连真实数据湖**(只读)。`lake.open_catalog()` 自带 5 次重试,
偶发一次失败重跑即可,连续失败才是故障。
"""

from __future__ import annotations

import ast
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

import genebench_config as cfg
from snapshots import lake
from snapshots import universe_index_weight as src_a

#: 会咬人的绝对路径前缀。模块里**一个都不许有** —— 唯一配置入口是 cfg。
_ABS_PATH_RE = re.compile(r"^/(data|home|tmp|usr|etc|var|opt|mnt|srv|root)(/|$)")


# ---------------------------------------------------------------------------
# fixtures:一次性把"现场真相"和"产物"都取出来
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def live() -> dict[str, Any]:
    """现场从只读 catalog 重算的真相,**不经过被测模块的任何计算函数**。

    Returns:
        ``members``   {universe: {trade_date: frozenset(code)}}
        ``dates``     {universe: [snapshot dates, 升序]}
        ``cal``       冻结线以内的交易日升序列表
        ``prev_td``   {trade_date: 前一个交易日}
    """
    lake.raise_open_file_limit()
    with lake.catalog() as con:
        raw = lake.query(
            "SELECT index_code, con_code, trade_date FROM index_weight "
            "WHERE trade_date <= ?",
            [lake.FREEZE_DATE_COMPACT],
            conn=con,
        )
        cal = lake.query(
            "SELECT cal_date FROM trade_cal WHERE is_open = 1 AND cal_date <= ? "
            "ORDER BY cal_date",
            [lake.FREEZE_DATE_COMPACT],
            conn=con,
        )["cal_date"].tolist()

    members: dict[str, dict[str, set[str]]] = {
        uni: defaultdict(set) for uni in cfg.UNIVERSES
    }
    for index_code, code, td in zip(
        raw["index_code"], raw["con_code"], raw["trade_date"]
    ):
        members[cfg.INDEX_CODE_UNIVERSE[index_code]][td].add(code)

    return {
        "raw": raw,
        "members": {
            uni: {d: frozenset(s) for d, s in by_date.items()}
            for uni, by_date in members.items()
        },
        "dates": {uni: sorted(members[uni]) for uni in cfg.UNIVERSES},
        "cal": cal,
        "prev_td": {cur: prv for prv, cur in zip(cal, cal[1:])},
    }


@pytest.fixture(scope="module")
def intervals() -> pd.DataFrame:
    """磁盘上的产物 parquet。产物不存在就是硬失败 —— 先跑 builder。"""
    path = cfg.UNIVERSE_INTERVALS_PARQUET
    if not path.is_file():
        pytest.fail(
            f"产物不存在:{path}\n"
            f"先跑:cd $REPO && {cfg.PYTHON} -m snapshots.universe_index_weight"
        )
    return pd.read_parquet(path)


@pytest.fixture(scope="module")
def summary() -> dict[str, Any]:
    """摘要 JSON。**只作为被对账的一方**,不当判据来源。"""
    path = cfg.UNIVERSE_SOURCE_A_JSON
    if not path.is_file():
        pytest.fail(f"摘要不存在:{path};先跑 builder。")
    return json.loads(path.read_text(encoding="utf-8"))


#: 右截断行 `out_date=NULL` 的哨兵值 —— 语义是"区间开口,上界 = +∞"。
#: 冻结线是 20260731,任何真实日期都 < 这个值。
_OPEN_END = "99999999"


def _arrays(frame: pd.DataFrame, universe: str) -> tuple[Any, Any, Any]:
    """取某宇宙的 (in_date, out_date_填哨兵, code) numpy 定长字符串数组。

    刻意 `astype(str)` 成 numpy unicode 数组再比:pandas 的可空 string dtype
    与 `pd.NA` 混进来会让 ``&`` 产出带 NA 的 object 数组,拿去做布尔索引直接炸,
    而且炸法很隐晦。哨兵 + 定长字符串是这里唯一不会给人惊喜的写法。
    """
    sel = frame[frame["universe"] == universe]
    return (
        sel["in_date"].astype(str).to_numpy(),
        sel["out_date"].fillna(_OPEN_END).astype(str).to_numpy(),
        sel["code"].astype(str).to_numpy(),
    )


# ---------------------------------------------------------------------------
# 源码级:唯一配置入口
# ---------------------------------------------------------------------------


def test_builder_has_no_absolute_path_literal() -> None:
    """`universe_index_weight.py` 里不许出现任何绝对路径字面量(含文档字符串)。"""
    tree = ast.parse(Path(src_a.__file__).read_text(encoding="utf-8"))
    offenders = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and _ABS_PATH_RE.match(node.value.strip())
    ]
    assert offenders == [], (
        f"模块里出现了绝对路径字面量:{offenders};"
        f" 唯一配置入口是 `import genebench_config as cfg`。"
    )


def test_builder_only_writes_to_config_derived_paths() -> None:
    """落盘只能走 `cfg.*` 派生的路径 —— 源码级确认没有第二条写路。"""
    text = Path(src_a.__file__).read_text(encoding="utf-8")
    tree = ast.parse(text)
    writes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"to_parquet", "write_text", "write_bytes", "replace"}
    ]
    assert writes, "一处落盘调用都没找到,测试自己失效了"
    # 唯一被 `_write_private` 之外的地方直接给出的目标只能是 cfg 常量
    assert "cfg.UNIVERSE_INTERVALS_PARQUET" in text
    assert "cfg.UNIVERSE_SOURCE_A_JSON" in text
    assert "cfg.create_dir(" in text, "建目录必须走 cfg.create_dir(红线 5)"


def test_builder_hardens_umask_before_any_repo_import() -> None:
    """`os.umask(0o077)` 必须**排在所有仓库内 import 之前**(红线 5)。

    本机 umask 是 002,CPython 在编译一个模块的那一刻就写 `__pycache__/`。
    把收紧动作放进 `main()` 或任何函数里都太晚 —— 卡 0.2 的 builder 已经
    真的因此造出过 0775 的 `snapshots/__pycache__`,踩红卡 0.1 的递归审计。
    这条是那个坑的源码级回归闸。
    """
    tree = ast.parse(Path(src_a.__file__).read_text(encoding="utf-8"))
    umask_line = next(
        (
            node.lineno
            for node in tree.body
            if isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == "umask"
        ),
        None,
    )
    assert umask_line is not None, "模块级找不到 os.umask(...) —— 收紧动作在函数里就太晚了"

    repo_import_lines = [
        node.lineno
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Try))
        and (
            "genebench_config" in ast.dump(node) or "snapshots" in ast.dump(node)
        )
    ]
    assert repo_import_lines, "测试自己失效了:没找到任何仓库内 import"
    assert umask_line < min(repo_import_lines), (
        f"os.umask 在第 {umask_line} 行,但仓库内 import 从第 {min(repo_import_lines)} 行就开始了 —— "
        f"`__pycache__` 会带着 002 落成 0775。"
    )


def test_builder_converges_existing_pycache_dirs() -> None:
    """`-m` 跑法下 `snapshots/__pycache__` 比第一行代码还早建 —— 必须事后收敛。

    上一条测试挡不住这个:umask 排第一行也没用,包的字节码缓存是 runpy 在
    import 包的时候写的。实测冷启动跑一次 `-m snapshots.universe_index_weight`
    就能造出 0o775 的 `snapshots/__pycache__`。所以模块必须像 `conftest.py`
    那样做一次幂等 chmod 收敛,并把收敛结果留痕。
    """
    assert hasattr(src_a, "CONVERGED_CACHE_DIRS"), (
        "模块没有做 __pycache__ 幂等收敛 —— `-m` 冷启动会留下 0775 的包缓存目录"
    )
    repo_root = Path(src_a.__file__).resolve().parents[1]
    offenders = [
        f"{oct(p.stat().st_mode & 0o777)} {p}"
        for p in repo_root.rglob("__pycache__")
        if p.is_dir() and p.stat().st_mode & cfg.FORBIDDEN_MODE_BITS
    ]
    assert offenders == [], f"仓库里还有对组/其它开放的字节码缓存目录:{offenders}"


# ---------------------------------------------------------------------------
# 产物形态与权限
# ---------------------------------------------------------------------------


def test_artifacts_are_private() -> None:
    """产物文件 0600、所在目录不对组/其它开放(红线 5;本机 umask 是 002)。"""
    for path in (cfg.UNIVERSE_INTERVALS_PARQUET, cfg.UNIVERSE_SOURCE_A_JSON):
        assert path.is_file(), f"{path} 不存在"
        mode = path.stat().st_mode & 0o777
        assert mode & cfg.FORBIDDEN_MODE_BITS == 0, f"{path} 权限 {oct(mode)} 对外开放"
    probe = cfg.UNIVERSE_DIR
    while probe != cfg.GENEBENCH_ROOT and probe != probe.parent:
        assert probe.is_dir(), f"{probe} 不是目录"
        mode = probe.stat().st_mode & 0o777
        assert mode & cfg.FORBIDDEN_MODE_BITS == 0, f"{probe} 权限 {oct(mode)} 对外开放"
        probe = probe.parent


def test_parquet_is_not_inside_repo() -> None:
    """大体量产物只落 `$GENEBENCH_ROOT`,repo 只放代码(红线 6)。"""
    assert cfg.REPO not in cfg.UNIVERSE_INTERVALS_PARQUET.parents


def test_schema_and_dtypes(intervals: pd.DataFrame) -> None:
    assert list(intervals.columns) == list(src_a.INTERVAL_COLUMNS)
    assert set(intervals["universe"]) == set(cfg.UNIVERSES)
    for col in ("code", "universe", "index_code", "in_date", "last_seen_snapshot"):
        assert intervals[col].notna().all(), f"{col} 不该有空值"
    for col in (
        "left_censored",
        "right_censored",
        "entry_gap_suspect",
        "exit_gap_suspect",
    ):
        assert intervals[col].dtype == bool


def test_universe_index_code_mapping(intervals: pd.DataFrame) -> None:
    got = dict(
        intervals[["universe", "index_code"]].drop_duplicates().itertuples(index=False)
    )
    assert got == cfg.UNIVERSE_INDEX_CODE


def test_no_date_exceeds_freeze_line(intervals: pd.DataFrame) -> None:
    """红线 7:一切日期不得越过 20260731。"""
    for col in ("in_date", "out_date", "last_seen_snapshot", "prev_snapshot", "next_snapshot"):
        bad = intervals.loc[intervals[col].notna() & (intervals[col] > lake.FREEZE_DATE_COMPACT), col]
        assert bad.empty, f"{col} 有 {len(bad)} 行越过冻结线,例:{bad.head().tolist()}"


# ---------------------------------------------------------------------------
# 主判据:PIT 重建
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("universe", cfg.UNIVERSES)
def test_pit_reconstruction_matches_live_snapshots(
    universe: str, intervals: pd.DataFrame, live: dict[str, Any]
) -> None:
    """每一期快照 T:区间覆盖 T 的集合 == 湖里那期的名单,**逐字相等**。

    这一条同时钉死约定、多段切分、左右截断。历史是不动的,所以用 ``==``,
    不给"方向 + 预算"的松紧带。
    """
    in_d, out_d, codes = _arrays(intervals, universe)
    mismatches: list[str] = []
    for day in live["dates"][universe]:
        hit = (in_d <= day) & (out_d >= day)
        got = frozenset(codes[hit])
        want = live["members"][universe][day]
        if got != want:
            mismatches.append(
                f"{day}: 多出 {sorted(got - want)[:5]} 缺失 {sorted(want - got)[:5]}"
            )
    assert mismatches == [], (
        f"{universe} 有 {len(mismatches)}/{len(live['dates'][universe])} 期对不上:"
        f"{mismatches[:3]}"
    )


@pytest.mark.parametrize("universe", cfg.UNIVERSES)
def test_universe_between_snapshots_is_last_observation_carried_forward(
    universe: str, intervals: pd.DataFrame, live: dict[str, Any]
) -> None:
    """非快照交易日:宇宙 == 不晚于该日的最后一期快照的名单。

    **这是三个候选约定唯一分得开的地方**,也是本卡这套 in/out 约定的全部意义
    (见模块 docstring 的负控数据)。若把 out_date 改回"最后一次出现的那期",
    月中宇宙会少掉当期被调出的那几只;若把 in_date 提前到"上一期的次日",
    月中宇宙会多出还没进来的那几只 —— 两种错法这条都红。

    取日方式是**确定性枚举**每个快照间隔的两端,不抽样。
    """
    dates = live["dates"][universe]
    next_td = {prv: cur for prv, cur in zip(live["cal"], live["cal"][1:])}
    snap_set = set(dates)
    probe_days: list[str] = []
    for cur, nxt in zip(dates, dates[1:]):
        for cand in (next_td.get(cur), live["prev_td"].get(nxt)):
            if cand and cand not in snap_set:
                probe_days.append(cand)
    probe_days = sorted(set(probe_days))
    assert len(probe_days) >= len(dates), "探测日太少,这条判据的区分力没建立起来"

    in_d, out_d, codes = _arrays(intervals, universe)

    bad: list[str] = []
    for day in probe_days:
        last_snap = max(d for d in dates if d <= day)
        hit = (in_d <= day) & (out_d >= day)
        got = frozenset(codes[hit])
        want = live["members"][universe][last_snap]
        if got != want:
            bad.append(f"{day}(上一期 {last_snap}): |got|={len(got)} |want|={len(want)}")
    assert bad == [], (
        f"{universe} 月中重建对不上 {len(bad)}/{len(probe_days)} 天:{bad[:5]}"
    )


# ---------------------------------------------------------------------------
# 区间自身的结构不变量
# ---------------------------------------------------------------------------


def test_segments_are_ordered_and_disjoint(intervals: pd.DataFrame) -> None:
    """同一 (code, universe) 的多段:segment_idx 从 0 连续、时间不重叠且严格递增。"""
    problems: list[str] = []
    for (uni, code), grp in intervals.groupby(["universe", "code"], sort=False):
        g = grp.sort_values("segment_idx")
        if list(g["segment_idx"]) != list(range(len(g))):
            problems.append(f"{uni}/{code} segment_idx 不连续:{list(g['segment_idx'])}")
            continue
        prev_out = None
        for row in g.itertuples(index=False):
            if prev_out is not None and row.in_date <= prev_out:
                problems.append(f"{uni}/{code} 段重叠:{prev_out} -> {row.in_date}")
            if row.out_date is not None and not pd.isna(row.out_date):
                if row.out_date < row.in_date:
                    problems.append(f"{uni}/{code} out<in:{row.in_date}>{row.out_date}")
                prev_out = row.out_date
            else:
                prev_out = None
    assert problems == [], problems[:10]


def test_out_date_is_previous_trading_day_of_next_snapshot(
    intervals: pd.DataFrame, live: dict[str, Any]
) -> None:
    """约定的逐行复算:``out_date == prev_trading_day(next_snapshot)``。"""
    closed = intervals[intervals["next_snapshot"].notna()]
    want = closed["next_snapshot"].astype(str).map(live["prev_td"])
    bad = closed[closed["out_date"].astype(str).to_numpy() != want.to_numpy()]
    assert bad.empty, f"{len(bad)} 行 out_date 不等于下一期的前一交易日:{bad.head(3).to_dict('records')}"
    assert (
        intervals.loc[intervals["next_snapshot"].isna(), "out_date"].isna().all()
    ), "右截断行的 out_date 必须是 NULL,不是冻结线日期"


def test_out_date_is_a_trading_day(intervals: pd.DataFrame, live: dict[str, Any]) -> None:
    """产物里每个日期都必须是真交易日 —— 下游直接 join daily 不用再取整。"""
    cal = set(live["cal"])
    for col in ("in_date", "out_date", "last_seen_snapshot", "prev_snapshot", "next_snapshot"):
        vals = set(intervals.loc[intervals[col].notna(), col])
        assert vals <= cal, f"{col} 里有非交易日:{sorted(vals - cal)[:5]}"


@pytest.mark.parametrize("universe", cfg.UNIVERSES)
def test_censoring_flags_match_live_first_and_last_period(
    universe: str, intervals: pd.DataFrame, live: dict[str, Any]
) -> None:
    """左/右截断的行数与成员集合,必须等于首期/末期的现场名单。"""
    dates = live["dates"][universe]
    first, last = dates[0], dates[-1]
    sel = intervals[intervals["universe"] == universe]

    left = sel[sel["left_censored"]]
    assert set(left["code"]) == live["members"][universe][first]
    assert (left["in_date"] == first).all(), "左截断段的 in_date 必须是首期"
    assert left["prev_snapshot"].isna().all(), "左截断段不该有 prev_snapshot"

    right = sel[sel["right_censored"]]
    assert set(right["code"]) == live["members"][universe][last]
    assert right["out_date"].isna().all(), "右截断段 out_date 必须为 NULL"
    assert (right["last_seen_snapshot"] == last).all()
    assert right["next_snapshot"].isna().all()
    # 末期恰好是名义规模(缺额期另有专门的测试点名)
    assert len(right) == len(live["members"][universe][last])


@pytest.mark.parametrize("universe", cfg.UNIVERSES)
def test_uncertainty_windows_are_consistent(
    universe: str, intervals: pd.DataFrame, live: dict[str, Any]
) -> None:
    """`prev_snapshot`/`next_snapshot` 必须是快照序列里 in/last_seen 的紧邻一期。"""
    dates = live["dates"][universe]
    pos = {d: i for i, d in enumerate(dates)}
    sel = intervals[intervals["universe"] == universe]
    for row in sel.itertuples(index=False):
        i, j = pos[row.in_date], pos[row.last_seen_snapshot]
        assert j >= i
        assert row.n_snapshots == j - i + 1
        if pd.isna(row.prev_snapshot):
            assert i == 0
        else:
            assert pos[row.prev_snapshot] == i - 1
        if pd.isna(row.next_snapshot):
            assert j == len(dates) - 1
        else:
            assert pos[row.next_snapshot] == j + 1


# ---------------------------------------------------------------------------
# 数据质量自查:每期成分数
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("universe", cfg.UNIVERSES)
def test_nominal_size_deviations_are_reported_not_hidden(
    universe: str, live: dict[str, Any], summary: dict[str, Any]
) -> None:
    """现场算出"哪几期不足额、差多少",摘要 JSON 必须一字不差地记着。

    注意判据方向:**不是**断言"每期都恒等于名义值"(实测就不是),
    而是断言"偏差被如实点名"。悄悄补齐比偏差本身危险得多。
    """
    nominal = cfg.UNIVERSE_NOMINAL_SIZE[universe]
    live_bad = {
        d: len(codes) - nominal
        for d, codes in sorted(live["members"][universe].items())
        if len(codes) != nominal
    }
    reported = {
        r["trade_date"]: r["delta"]
        for r in summary["universes"][universe]["off_size_periods"]
    }
    assert reported == live_bad, (
        f"{universe} 缺额期记录对不上:现场 {live_bad} vs 摘要 {reported}"
    )
    assert summary["universes"][universe]["size_is_constant"] == (not live_bad)

    # verdict 是**三态**(对抗审查 D2)。旧实现只要有一期不满额就报 FAIL,
    # 于是把"两只票同日吸收合并退市、指数短暂空 2 席"这件正常事判成整份摘要里
    # 唯一的 FAIL,任何自动门禁都会被它绊住。三态的判据在这里被独立复算:
    # 现场从湖里查缺席票的 delist_date,不读摘要里的 diagnosis。
    block = summary["integrity"]["nominal_size_check"][universe]
    if not live_bad:
        assert block["verdict"] == "PASS"
        assert block["off_size_diagnosis"] == []
        return

    with lake.catalog() as con:
        delist_of = {
            r.ts_code: r.delist_date
            for r in lake.query(
                "SELECT DISTINCT ts_code, delist_date FROM stock_basic "
                "WHERE delist_date IS NOT NULL",
                conn=con,
            ).itertuples(index=False)
        }
        weight_sum = {
            r.trade_date: float(r.sw)
            for r in lake.query(
                "SELECT trade_date, sum(weight) AS sw FROM index_weight "
                "WHERE index_code = ? AND trade_date <= ? GROUP BY 1",
                [cfg.UNIVERSE_INDEX_CODE[universe], lake.FREEZE_DATE_COMPACT],
                conn=con,
            ).itertuples(index=False)
        }
    dates = live["dates"][universe]
    pos = {d: i for i, d in enumerate(dates)}
    all_explained = True
    for d, delta in live_bad.items():
        prev = dates[pos[d] - 1] if pos[d] else None
        dropped = live["members"][universe][prev] - live["members"][universe][d] if prev else set()
        explained = [
            c for c in dropped if c in delist_of and prev < delist_of[c] <= d
        ]
        weight_ok = abs(weight_sum[d] - 100.0) <= src_a.WEIGHT_SUM_TOL
        if not (weight_ok and delta < 0 and len(explained) >= -delta):
            all_explained = False
    assert block["verdict"] == ("VACANCY_EXPLAINED" if all_explained else "FAIL"), (
        f"{universe} 的 verdict 判错了:现场重算 all_explained={all_explained}"
    )
    assert len(block["off_size_diagnosis"]) == len(live_bad)


@pytest.mark.parametrize("universe", cfg.UNIVERSES)
def test_gap_suspect_flags_require_the_in_missing_in_shape(
    universe: str, intervals: pd.DataFrame, live: dict[str, Any]
) -> None:
    """`entry/exit_gap_suspect` 的**精度**判据(对抗审查 D1 收窄后)。

    旧判据只要求"prev_snapshot 是个缺额期",于是把缺额期之后**整份调入名单**
    无差别染红:实测 20 行 True 里 **0 行**站得住 —— 18 个 entry 标记全部挂在
    20100129 那次正常调入上,其中两只(中国建筑 / 中国中冶)是 2009 年才上市的新股。

    收窄后的判据在这里被**逐行现场复核**:每一个亮着的标记,都必须
    (a) 紧邻一个缺额期,**且** (b) 该 code 在缺额期的另一侧也在成分内
    ——真正的"在–缺–在"形状。这个判据可以为空(本数据就是),
    但空必须是**判据判出来的空**,不是判据失效。
    """
    nominal = cfg.UNIVERSE_NOMINAL_SIZE[universe]
    members = live["members"][universe]
    dates = live["dates"][universe]
    pos = {d: i for i, d in enumerate(dates)}
    bad_dates = {d for d, codes in members.items() if len(codes) != nominal}
    sel = intervals[intervals["universe"] == universe]

    for r in sel.itertuples(index=False):
        if r.entry_gap_suspect:
            prev = r.prev_snapshot
            assert prev in bad_dates, f"{r.code} entry 标记亮在正常期 {prev}"
            i = pos[prev]
            assert i >= 1 and r.code in members[dates[i - 1]], (
                f"{r.code} 的 entry 标记不满足'在–缺–在':它在缺额期 {prev} "
                f"的上一期 {dates[i - 1]} 并不在成分内"
            )
        if r.exit_gap_suspect:
            nxt = r.next_snapshot
            assert nxt in bad_dates, f"{r.code} exit 标记亮在正常期 {nxt}"
            i = pos[nxt]
            assert i + 1 < len(dates) and r.code in members[dates[i + 1]], (
                f"{r.code} 的 exit 标记不满足'在–缺–在'"
            )
    if not bad_dates:
        assert not sel["entry_gap_suspect"].any()
        assert not sel["exit_gap_suspect"].any()


def test_gap_suspect_fires_on_a_synthetic_hole(live: dict[str, Any]) -> None:
    """**负控**:造一个人工的"在–缺–在"洞,标记必须亮。

    本数据上两列全 False。全 False 有两种可能:判据是对的(唯一的缺额期已被
    退市取证解释),或者判据失效了(永远不亮)。这条测试把两者分开 ——
    构造一份合成快照序列,在中间一期抠掉一只票,断言 `build_intervals()`
    真的会点名它。**没有这条,那两列就是装饰。**
    """
    uni = cfg.UNIVERSES[0]
    index_code = cfg.UNIVERSE_INDEX_CODE[uni]
    dates = ["20200102", "20200203", "20200302", "20200401"]
    codes = ["600000.SH", "600001.SH", "600002.SH"]
    rows = []
    for d in dates:
        for c in codes:
            if d == "20200302" and c == "600001.SH":
                continue  # ← 人工的洞:在–缺–在
            rows.append({"index_code": index_code, "con_code": c, "trade_date": d})
    df = pd.DataFrame(rows)
    dbu = {u: (dates if u == uni else []) for u in cfg.UNIVERSES}
    off = src_a.off_size_periods(df)
    # 三只票的"名义值"当然不是 300,所以自己造一份缺额期声明,
    # 并显式判成 unexplained(没有退市取证)。
    off = {u: [] for u in cfg.UNIVERSES}
    off[uni] = [
        {"trade_date": "20200302", "n_rows": 2, "n_distinct_codes": 2,
         "nominal": 3, "delta": -1}
    ]
    diag = {uni: [{"trade_date": "20200302", "classification": "unexplained"}]}
    prev_td = {d: dates[i - 1] for i, d in enumerate(dates) if i}
    out = src_a.build_intervals(df, dbu, prev_td, off, diag)
    hit = out[out["code"] == "600001.SH"]
    assert len(hit) == 2, f"人工的洞没有把区间切成两段:\n{hit}"
    assert bool(hit.iloc[1]["entry_gap_suspect"]), "'在–缺–在'的入场侧标记没亮"
    assert bool(hit.iloc[0]["exit_gap_suspect"]), "'在–缺–在'的出场侧标记没亮"
    # 同一批数据里没有洞的票,一个标记都不许亮。
    clean = out[out["code"] != "600001.SH"]
    assert not clean["entry_gap_suspect"].any(), "标记溅到了无关的票上"
    assert not clean["exit_gap_suspect"].any()


def test_gap_suspect_stays_dark_when_the_vacancy_is_explained() -> None:
    """**负控的另一半**:同一个洞,若缺额期被判成 `index_vacancy`,标记必须**不亮**。

    这条钉住 D1 修法的第一条(已被退市解释的缺额期不该触发 suspect)。
    """
    uni = cfg.UNIVERSES[0]
    index_code = cfg.UNIVERSE_INDEX_CODE[uni]
    dates = ["20200102", "20200203", "20200302", "20200401"]
    codes = ["600000.SH", "600001.SH", "600002.SH"]
    rows = [
        {"index_code": index_code, "con_code": c, "trade_date": d}
        for d in dates
        for c in codes
        if not (d == "20200302" and c == "600001.SH")
    ]
    df = pd.DataFrame(rows)
    dbu = {u: (dates if u == uni else []) for u in cfg.UNIVERSES}
    off = {u: [] for u in cfg.UNIVERSES}
    off[uni] = [
        {"trade_date": "20200302", "n_rows": 2, "n_distinct_codes": 2,
         "nominal": 3, "delta": -1}
    ]
    diag = {uni: [{"trade_date": "20200302", "classification": "index_vacancy"}]}
    prev_td = {d: dates[i - 1] for i, d in enumerate(dates) if i}
    out = src_a.build_intervals(df, dbu, prev_td, off, diag)
    assert not out["entry_gap_suspect"].any(), "已被退市解释的缺额期不该触发 suspect"
    assert not out["exit_gap_suspect"].any()


@pytest.mark.parametrize("universe", cfg.UNIVERSES)
def test_universe_size_is_not_constant_and_the_exception_is_pinned(
    universe: str, live: dict[str, Any], summary: dict[str, Any]
) -> None:
    """**规模不是不变量**(对抗审查 D4),而例外必须被钉成白名单。

    docstring 曾写"每个交易日的宇宙规模恒等于名义值 300/500/1000",被自家数据
    证伪(csi300 有 20 个交易日是 298)。绝对句式会被下游当不变量依赖
    (`assert len(univ) == 300`)。这里现场数一遍每期规模,与摘要里的直方图对账,
    并断言**唯一允许的例外**是 csi300 的 20091231 那一期(298)。
    """
    nominal = cfg.UNIVERSE_NOMINAL_SIZE[universe]
    live_hist: dict[int, int] = defaultdict(int)
    for codes in live["members"][universe].values():
        live_hist[len(codes)] += 1
    reported = {
        int(k): v
        for k, v in summary["integrity"]["size_histogram_by_period"][universe].items()
    }
    assert reported == dict(live_hist), (
        f"{universe} 的规模直方图对不上:现场 {dict(live_hist)} vs 摘要 {reported}"
    )
    allowed = {nominal: len(live["dates"][universe])}
    if universe == "csi300":
        allowed = {298: 1, 300: len(live["dates"][universe]) - 1}
    assert dict(live_hist) == allowed, (
        f"{universe} 出现了白名单之外的规模:{dict(live_hist)};"
        f" 白名单是 {allowed}。新的例外必须先被解释再进白名单,不许直接放宽。"
    )


def test_freeze_line_filter_is_falsifiable(live: dict[str, Any]) -> None:
    """**负控**:红线 7 的冻结线过滤必须真的在起作用。

    湖里的 `index_weight` 本身已经冻在 20260731,所以真实冻结线下
    `WHERE trade_date <= ?` 是个恒真条件 —— 那行被误删也不会有任何测试变红。
    这里传一个更早的界进去,断言产物真的被截短了。
    """
    earlier = "20200630"
    with lake.catalog() as con:
        df = src_a.load_snapshots(conn=con, freeze=earlier)
    assert len(df) > 0
    assert df["trade_date"].max() <= earlier, (
        f"传了 freeze={earlier},却拿到 max(trade_date)={df['trade_date'].max()} —— "
        f"冻结线过滤没有生效(红线 7 的防线是假的)"
    )
    full = len(live["raw"])
    assert len(df) < full, f"截到 {earlier} 之后行数没变({len(df)} vs {full})"


def test_source_view_date_convention_is_asserted(summary: dict[str, Any]) -> None:
    """本模块把 `trade_date` 当 8 位字符串用,这个前提必须有断言守着(D7)。

    同一份 gold 有两条访问路径两种类型(catalog view = VARCHAR、裸 parquet = DATE),
    而 `AGENT_CONTEXT` 恰恰把裸 `read_parquet` 推荐为绕 "Too many open files" 的办法。
    """
    with lake.catalog() as con:
        observed = src_a.assert_compact_date_convention(conn=con)
    assert observed["trade_date_typeof"] == "VARCHAR"
    assert len(observed["min_trade_date"]) == 8
    assert summary["integrity"]["source_view_date_types"] == observed


# ---------------------------------------------------------------------------
# 摘要 JSON:被对账的一方
# ---------------------------------------------------------------------------


def test_summary_counts_match_parquet(
    intervals: pd.DataFrame, summary: dict[str, Any]
) -> None:
    """摘要里的每个计数都要和 parquet 现场数出来的对上。"""
    assert summary["card"] == "1.1-sourceA"
    assert summary["freeze_line"] == lake.FREEZE_DATE_COMPACT
    assert summary["totals"]["n_intervals"] == len(intervals)
    for uni in cfg.UNIVERSES:
        sel = intervals[intervals["universe"] == uni]
        u = summary["universes"][uni]
        assert u["n_intervals"] == len(sel)
        assert u["n_distinct_codes"] == sel["code"].nunique()
        assert u["n_left_censored"] == int(sel["left_censored"].sum())
        assert u["n_right_censored"] == int(sel["right_censored"].sum())
        assert u["n_entry_gap_suspect"] == int(sel["entry_gap_suspect"].sum())
        assert u["n_exit_gap_suspect"] == int(sel["exit_gap_suspect"].sum())


def test_summary_date_coverage_matches_live(
    live: dict[str, Any], summary: dict[str, Any]
) -> None:
    for uni in cfg.UNIVERSES:
        cov = summary["universes"][uni]["date_coverage"]
        assert cov["snapshots"] == live["dates"][uni]
        assert cov["first_snapshot"] == live["dates"][uni][0]
        assert cov["last_snapshot"] == live["dates"][uni][-1]
        assert cov["n_snapshots"] == len(live["dates"][uni])


@pytest.mark.parametrize("universe", cfg.UNIVERSES)
def test_summary_turnover_matches_live(
    universe: str, live: dict[str, Any], summary: dict[str, Any]
) -> None:
    """换手分布现场重算一遍,摘要必须对上 min/median/max。"""
    dates = live["dates"][universe]
    adds, drops = [], []
    for prv, cur in zip(dates, dates[1:]):
        a = live["members"][universe][cur] - live["members"][universe][prv]
        d = live["members"][universe][prv] - live["members"][universe][cur]
        adds.append(len(a))
        drops.append(len(d))
    t = summary["turnover"][universe]
    assert t["n_transitions"] == len(adds)
    assert t["adds"]["min"] == min(adds)
    assert t["adds"]["max"] == max(adds)
    assert t["drops"]["min"] == min(drops)
    assert t["drops"]["max"] == max(drops)
    assert t["adds"]["median"] == statistics.median(adds)
    assert t["drops"]["median"] == statistics.median(drops)


def test_summary_artifact_fingerprint_matches_file(summary: dict[str, Any]) -> None:
    """摘要里记的 sha256/字节数,必须指向磁盘上那一份 parquet。"""
    import hashlib

    art = summary["artifact"]
    data = cfg.UNIVERSE_INTERVALS_PARQUET.read_bytes()
    assert art["bytes"] == len(data)
    assert art["sha256"] == hashlib.sha256(data).hexdigest()
    assert art["columns"] == list(src_a.INTERVAL_COLUMNS)


def test_summary_documents_conventions_and_limits(summary: dict[str, Any]) -> None:
    """数据卡不许是空壳:约定、局限、qlib 对齐三块都得在。"""
    assert set(summary["conventions"]) >= {
        "in_date",
        "out_date",
        "why",
        "resolution",
        "left_censored",
        "right_censored",
        "multi_segment",
    }
    assert len(summary["limitations"]) >= 5
    assert any("月内" in x for x in summary["limitations"]), "月内调整被抹平必须写进数据卡"
    assert set(summary["columns"]) == set(src_a.INTERVAL_COLUMNS)
    align = summary["qlib_alignment"]
    assert align["expected_direction_for_card_1_2"]
    assert align["measured"]["status"] in {"ok", "unavailable"}

    # D6:"左截断靠源B 回溯"这句对 csi1000 不成立,conventions 块必须写明例外。
    assert "csi1000" in summary["conventions"]["left_censored"], (
        "conventions.left_censored 没写 csi1000 的例外 —— "
        "源B 首日与源A 首期同一天,一只都补不了,那句承诺对它是空头支票"
    )
    # D5:给卡 1.2 的预判必须先说"投影到交易日网格",否则会产生 245 条假警报。
    joined = " ".join(align["expected_direction_for_card_1_2"])
    assert "交易日网格" in joined, (
        "预判里没写'先投影到交易日网格' —— qlib 用自然日,直接比会先收到一批 −2 天的假警报"
    )
    assert "measured_out_date_lag_natural_days" in align


def test_parquet_carries_its_validity_window() -> None:
    """产物**自带**有效区间(对抗审查 D3)。

    摘要 JSON 里的 date_coverage 只在 JSON 里,parquet 单独流转时带不走;
    于是拿到 parquet 的人按 `in_date <= D <= out_date` 查 2027 年会安静地
    拿到 2026-07-31 那份名单。
    """
    frame, meta = src_a.read_intervals()
    for key in ("valid_from", "valid_to", "freeze_line", "safe_reader",
                "valid_from_by_universe", "warning"):
        assert key in meta and meta[key], f"parquet metadata 少了 {key}"
    assert meta["valid_to"] == lake.FREEZE_DATE_COMPACT
    per_uni = json.loads(meta["valid_from_by_universe"])
    assert set(per_uni) == set(cfg.UNIVERSES)


@pytest.mark.parametrize("universe", cfg.UNIVERSES)
def test_universe_at_raises_instead_of_answering_out_of_range(universe: str) -> None:
    """越界查询必须**抛错**,不是静默返回空集或末期名单(D3)。

    裸过滤的实测行为:20090105 → 0 只、20270101 → 300 只、29991231 → 300 只,
    全程不报错。这条断言把那三种静默都堵上。
    """
    frame, meta = src_a.read_intervals()
    per_uni = json.loads(meta["valid_from_by_universe"])
    ok = src_a.universe_at(universe, per_uni[universe], frame=frame, meta=meta)
    assert len(ok) == cfg.UNIVERSE_NOMINAL_SIZE[universe]
    for bad in ("20270101", "29991231", "20081231"):
        with pytest.raises(ValueError, match="有效区间"):
            src_a.universe_at(universe, bad, frame=frame, meta=meta)


def test_multi_segment_codes_exist(intervals: pd.DataFrame) -> None:
    """"一只票可能多次进出"必须真的产出多段,而不是被压成一段。"""
    counts = intervals.groupby(["universe", "code"]).size()
    assert (counts > 1).any(), "一段多进出的票都没有,切段逻辑八成塌了"
    assert counts.max() >= 3
