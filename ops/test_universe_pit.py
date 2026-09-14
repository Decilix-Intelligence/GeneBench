"""卡 1.1 收口验收:`universe_pit` 的产物自洽 + 与三源的可还原性。

跑法::

    cd $REPO && $GENEBENCH_ROOT/env/bin/python -m pytest ops/test_universe_pit.py -q

**这套测试的立场是证伪,不是背书。** 每条断言都对着一个"这样写就会静默出错"的
具体写法。凡是"重跑一遍摘要里的数字再和摘要比"的自证式断言一律不写 ——
那种测试只能证明代码没变,证明不了产物是对的。

分四层:

1. **磁盘产物的结构自洽**:区间不重叠、in <= out、冻结线、枚举值、id 唯一、
   两种日期形态一致。这一层完全不碰湖,读 parquet 就能跑。
2. **与三源的可还原性**:从源A / 源B / stock_basic 现场重算,断言合成规则
   ``(A ∪ B) ∩ 在市窗口`` **逐日**成立 —— 这是对抗审查项 1 要求的"无损还原"。
3. **读取入口的行为**:`universe_at()` 必须对越界日期抛错(不是返回空集/满额)。
4. **负控**:故意破坏产物,断言测试真的会红。测试自己也要被测。
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

import numpy as np
import pandas as pd
import pytest

import genebench_config as cfg
from snapshots import lake
from snapshots import universe_build as ub
from snapshots import universe_qlib as source_b
from snapshots import universe_reconcile as recon


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pit() -> tuple[pd.DataFrame, dict[str, str]]:
    """磁盘上的产物 + 它的 schema metadata。"""
    if not cfg.UNIVERSE_PIT_PARQUET.exists():
        pytest.fail(
            f"产物不存在:{cfg.UNIVERSE_PIT_PARQUET}。"
            f" 先跑 `python -m snapshots.universe_build`。"
        )
    return ub.read_pit()


@pytest.fixture(scope="module")
def frame(pit) -> pd.DataFrame:
    return pit[0]


@pytest.fixture(scope="module")
def meta(pit) -> dict[str, str]:
    return pit[1]


@pytest.fixture(scope="module")
def summary() -> dict[str, Any]:
    if not cfg.UNIVERSE_PIT_JSON.exists():
        pytest.fail(f"摘要不存在:{cfg.UNIVERSE_PIT_JSON}")
    return json.loads(cfg.UNIVERSE_PIT_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def grid() -> ub.Grid:
    lake.raise_open_file_limit()
    with lake.catalog() as con:
        return ub.load_grid(conn=con)


@pytest.fixture(scope="module")
def live_sources(grid) -> dict[str, Any]:
    """**现场**从三个源重建的网格段 —— 用来独立重算合成规则。

    刻意不复用 `ub.build()` 的中间结果:那样只能验证"函数是幂等的",
    验证不了"磁盘上那份产物是按规则合成的"。
    """
    lake.raise_open_file_limit()
    with lake.catalog() as con:
        windows, _ = ub.load_listing_windows(grid, conn=con)
    a_segs, a_diag = ub.load_source_a(grid)
    b_segs, _ = ub.load_source_b(grid)
    return {"a": a_segs, "b": b_segs, "windows": windows, "a_diag": a_diag}


def _mask_from_frame(
    frame: pd.DataFrame, grid: ub.Grid, universe: str, code: str, *, canonical=None
) -> np.ndarray:
    idx = {d: i for i, d in enumerate(grid.days)}
    sel = frame[(frame["universe"] == universe) & (frame["code"] == code)]
    if canonical is not None:
        sel = sel[sel["canonical"] == canonical]
    m = np.zeros(len(grid), dtype=bool)
    for r in sel.itertuples(index=False):
        m[idx[r.in_date] : idx[r.out_date] + 1] = True
    return m


# ---------------------------------------------------------------------------
# 一、结构自洽(不碰湖)
# ---------------------------------------------------------------------------


def test_required_columns_present(frame: pd.DataFrame) -> None:
    """实施稿点名的六个字段必须在,且列顺序就是声明的那个。"""
    required = ("code", "universe", "in_date", "out_date", "source", "agreement_flag")
    missing = [c for c in required if c not in frame.columns]
    assert not missing, f"实施稿要求的字段缺了:{missing}"
    assert list(frame.columns) == list(ub.PIT_COLUMNS), (
        f"列顺序漂了:{list(frame.columns)} != {list(ub.PIT_COLUMNS)}"
    )


def test_in_date_le_out_date(frame: pd.DataFrame) -> None:
    bad = frame[frame["in_date"] > frame["out_date"]]
    assert bad.empty, f"{len(bad)} 行 in_date > out_date,例如\n{bad.head()}"


def test_out_date_never_null(frame: pd.DataFrame) -> None:
    """`out_date` 为空是源A 的约定,收口表刻意不用 —— 用它 + right_censored 表达开口。"""
    assert frame["in_date"].notna().all()
    assert frame["out_date"].notna().all(), (
        "收口表的 out_date 不许为空:右截断用 out_date=冻结线 + right_censored=True 表达"
    )


def test_freeze_line_is_a_hard_bound(frame: pd.DataFrame, meta: dict[str, str]) -> None:
    """红线 7:产物里不许出现任何晚于冻结线的日期。"""
    freeze = dt.date.fromisoformat(cfg.FREEZE_DATE)
    assert meta["freeze_line"] == cfg.FREEZE_DATE
    assert meta["valid_to"] == freeze.isoformat()
    assert (frame["out_date"] <= freeze).all(), "有 out_date 越过冻结线"
    assert (frame["in_date"] <= freeze).all(), "有 in_date 越过冻结线"


def test_right_censored_iff_out_date_is_freeze(frame: pd.DataFrame) -> None:
    """`right_censored` 与 `out_date == 冻结线` 必须**等价**。

    不等价的话,下游只能靠猜 —— 而两种猜法都会错:把 out_date==冻结线 一律读成
    "当天被调出"会凭空造一次调仓,一律读成"还在"会把真的在冻结线当天被调出的
    段读成永远在。
    """
    freeze = dt.date.fromisoformat(cfg.FREEZE_DATE)
    at_freeze = frame["out_date"] == freeze
    assert (frame["right_censored"] == at_freeze).all(), (
        "right_censored 与 out_date==冻结线 不等价:"
        f"{int((frame['right_censored'] != at_freeze).sum())} 行对不上"
    )


def test_left_censored_iff_in_date_is_the_observability_floor(
    frame: pd.DataFrame, summary: dict[str, Any]
) -> None:
    """`left_censored` 与 `in_date == 该宇宙的可观测下界` 必须**等价**。

    和 `right_censored` 一样,截断标记是**行级**谓词。做成段级(整段的 part 都
    继承段头的标记)会让标记与日期脱钩,下游只能靠猜。
    """
    floors = summary["sources"]["pit"]["window_start_date"]
    for uni in cfg.UNIVERSES_PIT:
        sel = frame[frame["universe"] == uni]
        at_floor = sel["in_date_compact"] == floors[uni]
        assert (sel["left_censored"] == at_floor).all(), (
            f"{uni} 的 left_censored 与 in_date=={floors[uni]} 不等价:"
            f"{int((sel['left_censored'] != at_floor).sum())} 行对不上"
        )


def test_endpoints_are_trading_days(frame: pd.DataFrame, grid: ub.Grid) -> None:
    """两端都必须落在交易日网格上 —— 源B 的自然日端点大量落在周末,没投影就会漏。"""
    days = set(grid.days)
    bad_in = frame[~frame["in_date"].isin(days)]
    bad_out = frame[~frame["out_date"].isin(days)]
    assert bad_in.empty, f"{len(bad_in)} 行 in_date 不是交易日"
    assert bad_out.empty, f"{len(bad_out)} 行 out_date 不是交易日"


def test_code_format_is_uniform(frame: pd.DataFrame) -> None:
    """`code` 一律湖内形态 `600000.SH`,不许混进 qlib 的 `SH600000`。"""
    bad = frame[~frame["code"].str.match(r"^\d{6}\.(SH|SZ|BJ)$")]
    assert bad.empty, f"code 格式不统一:{sorted(set(bad['code']))[:10]}"
    assert not frame["code"].str.startswith(("SH", "SZ", "BJ")).any(), (
        "混进了 qlib 前缀式代码"
    )


def test_enum_columns_are_closed(frame: pd.DataFrame) -> None:
    """`source` / `universe` / `agreement_basis` 都是**封闭**枚举,不许出现表外的值。"""
    assert set(frame["universe"]) <= set(cfg.UNIVERSES_PIT)
    assert set(frame["source"]) <= set(cfg.UNIVERSE_SOURCES), (
        f"source 出现表外取值:{set(frame['source']) - set(cfg.UNIVERSE_SOURCES)}"
    )
    assert set(frame["agreement_basis"]) <= set(ub.AGREEMENT_BASIS), (
        f"agreement_basis 出现表外取值:"
        f"{set(frame['agreement_basis']) - set(ub.AGREEMENT_BASIS)}"
    )


def test_agreement_flag_matches_its_basis(frame: pd.DataFrame) -> None:
    """`agreement_flag` 必须由 `agreement_basis` 唯一决定,不能各说各话。"""
    for basis, (expected, _why) in ub.AGREEMENT_BASIS.items():
        sel = frame[frame["agreement_basis"] == basis]
        if sel.empty:
            continue
        if expected is None:
            assert sel["agreement_flag"].isna().all(), (
                f"{basis} 应当是 NULL,却有非空值"
            )
        else:
            assert (sel["agreement_flag"] == expected).all(), (
                f"{basis} 应当是 {expected},却有别的值"
            )


def test_source_and_basis_are_consistent(frame: pd.DataFrame) -> None:
    """`source == 'both'` 只能配 `both_sources_agree`;单源不许自称两源一致。"""
    both = frame[frame["source"] == "both"]
    assert (both["agreement_basis"] == "both_sources_agree").all()
    agreed = frame[frame["agreement_basis"] == "both_sources_agree"]
    assert (agreed["source"] == "both").all()
    fallback = frame[frame["source"] == "basic_fallback"]
    assert (fallback["universe"] == cfg.MARKET_UNIVERSE).all(), (
        "basic_fallback 只该出现在市场全集宇宙"
    )
    assert fallback["agreement_flag"].isna().all(), (
        "单源宇宙的 agreement_flag 必须是 NULL —— 写 False 会被读成'两源打架'"
    )


def test_canonical_definition_holds(frame: pd.DataFrame) -> None:
    """`canonical` 必须与 `is_canonical()` 逐行一致(不许手工打标)。"""
    expected = [
        ub.is_canonical(r.universe, r.source, r.agreement_basis)
        for r in frame.itertuples(index=False)
    ]
    assert (frame["canonical"] == pd.Series(expected, index=frame.index)).all()


def test_segment_id_is_unique_and_derived(frame: pd.DataFrame) -> None:
    assert frame["segment_id"].is_unique, "segment_id 不唯一,不能当行键"
    rebuilt = (
        frame["universe"].astype(str)
        + "|"
        + frame["code"].astype(str)
        + "|"
        + frame["segment_idx"].astype(str)
        + "|"
        + frame["part_idx"].astype(str)
    )
    assert (frame["segment_id"] == rebuilt).all()


def test_compact_dates_match_date32(frame: pd.DataFrame) -> None:
    """两种日期形态必须是同一件事 —— 漂移了下游 join 湖就会静默少数据。"""
    assert (
        frame["in_date_compact"]
        == frame["in_date"].map(lambda d: d.strftime("%Y%m%d"))
    ).all()
    assert (
        frame["out_date_compact"]
        == frame["out_date"].map(lambda d: d.strftime("%Y%m%d"))
    ).all()


def test_n_trading_days_matches_grid(frame: pd.DataFrame, grid: ub.Grid) -> None:
    idx = {d: i for i, d in enumerate(grid.days)}
    calc = frame.apply(
        lambda r: idx[r["out_date"]] - idx[r["in_date"]] + 1, axis=1
    )
    assert (frame["n_trading_days"] == calc).all()


@pytest.mark.parametrize("universe", cfg.UNIVERSES_PIT)
def test_intervals_do_not_overlap_or_contradict(
    universe: str, frame: pd.DataFrame, grid: ub.Grid
) -> None:
    """同一 (universe, code) 内:不重叠 + 同一次进出的 part 首尾相接 +
    不同次进出之间有真缺口 + segment_idx / part_idx 编号连续。

    这四条合起来才叫"不自相矛盾"。只查重叠会漏掉"两次进出之间其实没有缺口"
    (那是一次进出被误拆成两次)和"同一次进出的 part 之间有洞"(那是漏了一段)。
    """
    idx = {d: i for i, d in enumerate(grid.days)}
    sel = frame[frame["universe"] == universe]
    problems: list[str] = []
    for code, g in sel.groupby("code", sort=False):
        g = g.sort_values(["in_date", "out_date"], kind="mergesort")
        prev_end = prev_seg = prev_part = None
        for r in g.itertuples(index=False):
            i0, i1 = idx[r.in_date], idx[r.out_date]
            if prev_end is None:
                if r.segment_idx != 0 or r.part_idx != 0:
                    problems.append(f"{code} 首行编号不是 (0,0)")
            else:
                if i0 <= prev_end:
                    problems.append(f"{code} 区间重叠 @{r.in_date_compact}")
                elif r.segment_idx == prev_seg:
                    if i0 != prev_end + 1:
                        problems.append(
                            f"{code} 同一次进出的 part 之间有洞 @{r.in_date_compact}"
                        )
                    if r.part_idx != prev_part + 1:
                        problems.append(f"{code} part_idx 不连续 @{r.in_date_compact}")
                else:
                    if i0 == prev_end + 1:
                        problems.append(
                            f"{code} 两次进出之间没有真缺口(应当合成一次)"
                            f" @{r.in_date_compact}"
                        )
                    if r.segment_idx != prev_seg + 1:
                        problems.append(
                            f"{code} segment_idx 不连续 @{r.in_date_compact}"
                        )
                    if r.part_idx != 0:
                        problems.append(
                            f"{code} 新一次进出的 part_idx 不是 0 @{r.in_date_compact}"
                        )
            prev_end, prev_seg, prev_part = i1, r.segment_idx, r.part_idx
    assert not problems, f"{universe} 区间自相矛盾({len(problems)} 处):{problems[:10]}"


# ---------------------------------------------------------------------------
# 二、与三源的可还原性(对抗审查项 1:成员集合可无损还原)
# ---------------------------------------------------------------------------


def test_grid_matches_reconcile_grid(grid: ub.Grid) -> None:
    """本模块自建的网格必须与卡 1.1-reconcile 的逐日相同 —— 两处各建一份必然漂移。"""
    lake.raise_open_file_limit()
    with lake.catalog() as con:
        other = recon.load_grid(conn=con)
    assert tuple(grid.days) == tuple(other.days), "两处网格漂移了"
    assert grid.days[-1] == dt.date.fromisoformat(cfg.FREEZE_DATE)


@pytest.mark.parametrize("universe", cfg.UNIVERSES)
def test_membership_equals_union_intersect_listing(
    universe: str, frame: pd.DataFrame, grid: ub.Grid, live_sources: dict[str, Any]
) -> None:
    """**逐 code 逐日**重算 ``(A ∪ B) ∩ 在市窗口``,与产物比对。

    这是本卡最硬的一条:它不看摘要、不看中间变量,直接从三个源的磁盘产物
    重建成员布尔序列,再把产物展开成同样的序列逐位比。对不上就是合成规则被改了
    (或者被静默丢了段)。
    """
    a_segs = live_sources["a"].get(universe, {})
    b_segs = live_sources["b"].get(universe, {})
    windows = live_sources["windows"]
    n = len(grid)
    codes = sorted(set(a_segs) | set(b_segs))
    mismatched: list[str] = []
    for code in codes:
        want = np.zeros(n, dtype=bool)
        for i0, i1 in a_segs.get(code, []):
            want[i0 : i1 + 1] = True
        for i0, i1 in b_segs.get(code, []):
            want[i0 : i1 + 1] = True
        win = windows.get(code)
        alive = np.zeros(n, dtype=bool)
        if win is not None:
            alive[win[0] : win[1] + 1] = True
        want &= alive
        got = _mask_from_frame(frame, grid, universe, code)
        if not np.array_equal(want, got):
            mismatched.append(code)
    assert not mismatched, (
        f"{universe} 有 {len(mismatched)} 只票的成员日与 (A∪B)∩在市窗口 对不上:"
        f"{mismatched[:10]}"
    )


@pytest.mark.parametrize("universe", cfg.UNIVERSES)
def test_source_label_matches_which_source_says_so(
    universe: str, frame: pd.DataFrame, grid: ub.Grid, live_sources: dict[str, Any]
) -> None:
    """`source` 这一列必须**如实**反映哪一源说了话,抽 60 只逐日核。

    抽样是确定性的(按 code 字典序等距取),换机器重跑抽到同一批。
    """
    a_segs = live_sources["a"].get(universe, {})
    b_segs = live_sources["b"].get(universe, {})
    n = len(grid)
    idx = {d: i for i, d in enumerate(grid.days)}
    codes = sorted(set(a_segs) | set(b_segs))
    picked = codes[:: max(1, len(codes) // 60)][:60]
    for code in picked:
        a = np.zeros(n, dtype=bool)
        for i0, i1 in a_segs.get(code, []):
            a[i0 : i1 + 1] = True
        b = np.zeros(n, dtype=bool)
        for i0, i1 in b_segs.get(code, []):
            b[i0 : i1 + 1] = True
        sel = frame[(frame["universe"] == universe) & (frame["code"] == code)]
        for r in sel.itertuples(index=False):
            lo, hi = idx[r.in_date], idx[r.out_date] + 1
            in_a, in_b = a[lo:hi], b[lo:hi]
            assert in_a.all() or (~in_a).all(), f"{code} 段内源A 的说法不恒定"
            assert in_b.all() or (~in_b).all(), f"{code} 段内源B 的说法不恒定"
            want = {
                (True, True): "both",
                (True, False): "index_weight",
                (False, True): "qlib_instruments",
            }[(bool(in_a.all()), bool(in_b.all()))]
            assert r.source == want, (
                f"{universe}/{code} {r.in_date_compact}~{r.out_date_compact} "
                f"标了 {r.source},实际是 {want}"
            )


def test_all_universe_equals_listing_windows(
    frame: pd.DataFrame, grid: ub.Grid, live_sources: dict[str, Any]
) -> None:
    """`all` 宇宙必须**恰好**是第三源的在市窗口 —— 一只不多、一只不少。"""
    windows = live_sources["windows"]
    sel = frame[frame["universe"] == cfg.MARKET_UNIVERSE]
    assert set(sel["code"]) == set(windows), (
        f"all 宇宙的 code 集合与在市窗口对不上:"
        f"多 {sorted(set(sel['code']) - set(windows))[:5]},"
        f"少 {sorted(set(windows) - set(sel['code']))[:5]}"
    )
    idx = {d: i for i, d in enumerate(grid.days)}
    bad = [
        r.code
        for r in sel.itertuples(index=False)
        if (idx[r.in_date], idx[r.out_date]) != windows[r.code]
    ]
    assert not bad, f"{len(bad)} 只票的 all 区间与在市窗口不等:{bad[:10]}"
    assert (sel["segment_idx"] == 0).all(), "在市窗口是一段,不该有第二次'进出'"


def test_listing_filter_actually_removed_something(summary: dict[str, Any]) -> None:
    """第三源这道闸门必须**真的在起作用**,否则它就是个摆设。

    这条是防"闸门被改成恒真"的负控:实测源B 有 20+ 只已退市的票还留在成分名单里,
    过滤掉的成员日必须 > 0。
    """
    clip = summary["sources"]["pit"]["member_days_removed_by_listing_filter"]
    total = sum(v for k, v in clip.items() if "::" not in k)
    assert total > 0, (
        "在市窗口没有裁掉任何成员日 —— 闸门失效了。"
        "实测源B 会把已退市的票留在成分名单里(如 600270.SH 退市于 2018-12-28、"
        "源B 留到 2019-06-27),过滤应当有非零效果。"
    )
    assert sum(clip.get(f"{u}::b_only", 0) for u in cfg.UNIVERSES) > 0, (
        "裁掉的成员日里没有一个来自源B —— 与实测不符"
    )


@pytest.mark.parametrize("universe", cfg.UNIVERSES)
def test_listing_clipped_marks_the_row_whose_endpoint_was_cut(
    universe: str, frame: pd.DataFrame, grid: ub.Grid, live_sources: dict[str, Any]
) -> None:
    """`listing_clipped` 必须是**行级**谓词,现场重算逐行核。

    段级会把一次进出的所有 part 都染上(实测:600270.SH 的两行都会亮),
    读者根本无法定位到底是哪一端被裁的 —— 而"哪一端"正是这列存在的意义。
    """
    a_segs = live_sources["a"].get(universe, {})
    b_segs = live_sources["b"].get(universe, {})
    windows = live_sources["windows"]
    n = len(grid)
    idx = {d: i for i, d in enumerate(grid.days)}
    sel = frame[frame["universe"] == universe]
    wrong: list[str] = []
    for code, g in sel.groupby("code", sort=False):
        raw = np.zeros(n, dtype=bool)
        for segs in (a_segs.get(code, []), b_segs.get(code, [])):
            for i0, i1 in segs:
                raw[i0 : i1 + 1] = True
        alive = np.zeros(n, dtype=bool)
        win = windows.get(code)
        if win is not None:
            alive[win[0] : win[1] + 1] = True
        cut = raw & ~alive
        for r in g.itertuples(index=False):
            p0, p1 = idx[r.in_date], idx[r.out_date]
            want = (p0 > 0 and bool(cut[p0 - 1])) or (p1 < n - 1 and bool(cut[p1 + 1]))
            if bool(r.listing_clipped) != want:
                wrong.append(f"{r.segment_id}(标 {r.listing_clipped},实际 {want})")
    assert not wrong, f"{universe} listing_clipped 标错 {len(wrong)} 行:{wrong[:8]}"


def test_no_member_day_outside_listing_window(
    frame: pd.DataFrame, grid: ub.Grid, live_sources: dict[str, Any]
) -> None:
    """反过来查:产物里不许有任何一天落在该票的在市窗口之外。"""
    windows = live_sources["windows"]
    idx = {d: i for i, d in enumerate(grid.days)}
    bad: list[str] = []
    for r in frame.itertuples(index=False):
        win = windows.get(r.code)
        if win is None:
            bad.append(f"{r.segment_id}(该 code 没有在市窗口)")
            continue
        if idx[r.in_date] < win[0] or idx[r.out_date] > win[1]:
            bad.append(r.segment_id)
    assert not bad, f"{len(bad)} 行越出在市窗口:{bad[:10]}"


# ---------------------------------------------------------------------------
# 三、成员数落在合理范围
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("universe", cfg.UNIVERSES)
def test_canonical_size_on_every_trading_day(
    universe: str, frame: pd.DataFrame, grid: ub.Grid
) -> None:
    """主力读法下的宇宙规模,在**每一个**交易日上都要落在 ``[名义值-2, 名义值]``。

    上界是硬的(``== 名义值``):超出名义值说明并集漏进了 canonical。
    下界允许少 2 只,成因有二、都不是 bug:
    (a) 指数真空缺(csi300 在 2009-12-31~2010-01-28 少 2 席,合并退市);
    (b) 成分股月中退市、源A 的 LOCF 把它持有到下一期月末,而第三源在
        `delist_date` 当天切掉 —— 那几天"名义 300 只"里确实有 1~2 只不可交易。

    **不写 `== 名义值`**:那条断言在真实数据上是假的(实测 csi300 有 92 个交易日
    不等于 300),写了只会逼下一个人把它注释掉。
    """
    nominal = cfg.UNIVERSE_NOMINAL_SIZE[universe]
    stats = ub.daily_size_stats(frame, grid, scope="canonical")[universe]
    assert stats["max"] == nominal, (
        f"{universe} 的 canonical 规模最大 {stats['max']} > 名义值 {nominal} —— "
        f"并集漏进主力读法了。规模分布 {stats['size_histogram']}"
    )
    assert stats["min"] >= nominal - 2, (
        f"{universe} 的 canonical 规模最小 {stats['min']},比名义值少了 "
        f"{nominal - stats['min']} 只,超出已知成因能解释的 2 只。"
        f" 规模分布 {stats['size_histogram']}"
    )


@pytest.mark.parametrize("universe", cfg.UNIVERSES)
def test_union_size_is_a_superset_and_bounded(
    universe: str, frame: pd.DataFrame, grid: ub.Grid
) -> None:
    """并集读法**允许**超过名义值(这正是要有 canonical 的原因),但不能离谱。

    上界 1.25 倍不是拍脑袋:两源在同一次调仓上最多各持一份名单,
    偏差量级由调仓上限(csi300 10%/次)决定。超过它说明合并出了别的问题。
    """
    nominal = cfg.UNIVERSE_NOMINAL_SIZE[universe]
    stats = ub.daily_size_stats(frame, grid, scope="union")[universe]
    assert stats["max"] <= nominal * 1.25, (
        f"{universe} 的 union 规模最大 {stats['max']},超过名义值 {nominal} 的 1.25 倍"
    )
    assert stats["max"] >= stats["min"]


def test_market_universe_grows_monotonically_in_the_large(
    frame: pd.DataFrame, grid: ub.Grid
) -> None:
    """市场全集的规模量级必须站得住:首日 ~1600、冻结线 ~5500,且是净增长。

    这条防的是"在市窗口口径写反"(左闭右开写成左开右闭之类)——
    那种错误不会让任何结构断言变红,只会让规模整体偏移。
    """
    stats = ub.daily_size_stats(frame, grid, scope="canonical")[cfg.MARKET_UNIVERSE]
    by_year = stats["size_by_year_first_trading_day"]
    assert 1400 <= stats["min"] <= 1800, f"首日市场规模 {stats['min']} 不合理"
    assert 5000 <= stats["max"] <= 6000, f"冻结线市场规模 {stats['max']} 不合理"
    years = sorted(by_year)
    assert by_year[years[0]] < by_year[years[-1]], "市场规模没有净增长,口径可疑"


# ---------------------------------------------------------------------------
# 四、读取入口的行为(对抗审查 D3)
# ---------------------------------------------------------------------------


def test_universe_at_rejects_dates_beyond_the_freeze_line(frame, meta) -> None:
    """越界查询必须**抛错**,不能静默返回冻结线那天的名单。

    这正是源A 产物被撞出来的缺陷:``in_date <= D <= out_date`` 在 D=2027-01-01、
    甚至 D=2999-12-31 时都安静地给你 300 只。
    """
    for bad in ("20260801", "20270101", "29991231"):
        with pytest.raises(ValueError, match="有效区间"):
            ub.universe_at("csi300", bad, frame=frame, meta=meta)


def test_universe_at_rejects_dates_before_the_grid(frame, meta) -> None:
    """另一个方向同样要抛错 —— 静默空集比报错危险得多。"""
    for bad in ("20081231", "19900101"):
        with pytest.raises(ValueError, match="有效区间"):
            ub.universe_at("csi300", bad, frame=frame, meta=meta)


def test_universe_at_rejects_unknown_universe_and_scope(frame, meta) -> None:
    with pytest.raises(ValueError, match="不认识的宇宙"):
        ub.universe_at("csi800", "20260731", frame=frame, meta=meta)
    with pytest.raises(ValueError, match="不认识的 scope"):
        ub.universe_at("csi300", "20260731", frame=frame, meta=meta, scope="所有")


@pytest.mark.parametrize("universe", cfg.UNIVERSES)
def test_universe_at_default_scope_is_canonical(universe, frame, meta) -> None:
    """默认 scope 必须是 canonical:默认值错了,所有不传参的调用方都会拿到并集。"""
    d = cfg.FREEZE_DATE.replace("-", "")
    default = ub.universe_at(universe, d, frame=frame, meta=meta)
    canon = ub.universe_at(universe, d, frame=frame, meta=meta, scope="canonical")
    union = ub.universe_at(universe, d, frame=frame, meta=meta, scope="union")
    assert default == canon
    assert set(canon) <= set(union), "canonical 必须是 union 的子集"
    assert len(canon) == cfg.UNIVERSE_NOMINAL_SIZE[universe]


def test_parquet_metadata_carries_the_contract(meta: dict[str, str]) -> None:
    """parquet 单独流转时必须自带口径 —— 摘要 JSON 与数据卡都在 repo 里,带不走。"""
    for key in (
        "valid_from",
        "valid_to",
        "freeze_line",
        "safe_reader",
        "interval_closure",
        "universes",
        "data_card",
    ):
        assert key in meta and meta[key], f"parquet metadata 少了 {key}"
    assert meta["safe_reader"].startswith("snapshots.universe_build.universe_at")
    assert set(meta["universes"].split(",")) == set(cfg.UNIVERSES_PIT)


# ---------------------------------------------------------------------------
# 五、摘要 / 数据卡与产物一致
# ---------------------------------------------------------------------------


def test_summary_counts_match_the_parquet(
    frame: pd.DataFrame, summary: dict[str, Any]
) -> None:
    """摘要里的每个计数都要和 parquet 现场数出来的对上。"""
    assert summary["card"] == "1.1"
    assert summary["freeze_line"] == cfg.FREEZE_DATE
    assert summary["totals"]["n_rows"] == len(frame)
    assert summary["totals"]["n_canonical_rows"] == int(frame["canonical"].sum())
    for uni in cfg.UNIVERSES_PIT:
        sel = frame[frame["universe"] == uni]
        u = summary["universes"][uni]
        assert u["n_rows"] == len(sel)
        assert u["n_distinct_codes"] == sel["code"].nunique()
        assert u["n_left_censored"] == int(sel["left_censored"].sum())
        assert u["n_right_censored"] == int(sel["right_censored"].sum())
        assert u["n_canonical_rows"] == int(sel["canonical"].sum())
        assert u["agreement_counts"]["null"] == int(sel["agreement_flag"].isna().sum())


def test_artifact_fingerprint_points_at_the_file_on_disk(
    summary: dict[str, Any],
) -> None:
    """摘要里记的 sha256 / 字节数必须指向磁盘上那一份 parquet。"""
    import hashlib

    art = summary["artifact"]
    data = cfg.UNIVERSE_PIT_PARQUET.read_bytes()
    assert art["bytes"] == len(data)
    assert art["sha256"] == hashlib.sha256(data).hexdigest()
    assert art["mode"] == "0o600", f"产物权限 {art['mode']} 击穿红线 5"


def test_integrity_block_is_all_zero(summary: dict[str, Any]) -> None:
    """摘要的完整性自查块必须全零 —— 它和上面的断言是两条独立的路,都得绿。"""
    nonzero = {
        k: v for k, v in summary["integrity"].items() if isinstance(v, int) and v
    }
    assert not nonzero, f"完整性自查有非零项:{nonzero}"


def test_data_card_exists_and_covers_the_required_topics() -> None:
    """数据卡必须**逐条**覆盖实施稿点名的话题,不是有个文件就算数。"""
    assert cfg.UNIVERSE_PIT_CARD.exists(), f"数据卡不存在:{cfg.UNIVERSE_PIT_CARD}"
    text = cfg.UNIVERSE_PIT_CARD.read_text(encoding="utf-8")
    required = {
        "来源与构建方法": "来源与构建方法",
        "区间约定的精确定义": "区间约定的精确定义",
        "月内调整被抹平": "月内调整被抹平",
        "左右截断": "左截断",
        "右截断": "右截断",
        "两源分歧的处理策略": "两源分歧的处理策略",
        "覆盖范围与冻结线": "覆盖范围与冻结线",
        "不该拿它做什么": "不该拿它做什么",
    }
    missing = [name for name, needle in required.items() if needle not in text]
    assert not missing, f"数据卡少了这些必写话题:{missing}"
    # 数据卡里的关键数字必须是现算的,不是抄的
    assert cfg.FREEZE_DATE in text
    assert "canonical" in text


def test_data_card_is_regenerated_not_handwritten(summary: dict[str, Any]) -> None:
    """数据卡必须能由摘要**逐字重放** —— 手改过就会红。

    手写的数据卡会在下一次重建后静默过期,而数据卡恰恰是别人唯一会读的东西。
    """
    rendered = ub.render_data_card(summary)
    on_disk = cfg.UNIVERSE_PIT_CARD.read_text(encoding="utf-8")
    assert rendered == on_disk, (
        "磁盘上的数据卡与由摘要渲染出来的不一致 —— 要么被手改了,"
        "要么产物比数据卡新。重跑 `python -m snapshots.universe_build`。"
    )


def test_needs_manual_review_is_listed_not_summarized(
    frame: pd.DataFrame, summary: dict[str, Any]
) -> None:
    """残余的"必须逐条查"必须被**整个列出来**,只给个计数等于掩盖。"""
    rev = summary["needs_manual_review"]
    sel = frame[frame["agreement_basis"].isin(rev["bases"])]
    assert rev["n_rows"] == len(sel)
    assert len(rev["rows"]) == len(sel), "残余分歧被截断了,必须整个列出来"
    assert rev["n_member_days"] == int(sel["n_trading_days"].sum())


# ---------------------------------------------------------------------------
# 六、负控:把产物弄坏,断言测试真的会红
# ---------------------------------------------------------------------------


def _expect_failure(fn, *args) -> None:
    with pytest.raises(AssertionError):
        fn(*args)


def test_negative_control_overlap_is_caught(frame: pd.DataFrame, grid: ub.Grid) -> None:
    """人为造一次区间重叠,断言 `test_intervals_do_not_overlap_or_contradict` 会红。"""
    broken = frame.copy()
    i = broken.index[broken["universe"] == "csi300"][0]
    broken.loc[i, "out_date"] = grid.days[-1]
    broken.loc[i, "out_date_compact"] = grid.compact[-1]
    _expect_failure(
        test_intervals_do_not_overlap_or_contradict, "csi300", broken, grid
    )


def test_negative_control_beyond_freeze_is_caught(
    frame: pd.DataFrame, meta: dict[str, str]
) -> None:
    """把一行推过冻结线,断言冻结线断言会红(红线 7 的负控)。"""
    broken = frame.copy()
    broken.loc[broken.index[0], "out_date"] = dt.date(2026, 8, 1)
    _expect_failure(test_freeze_line_is_a_hard_bound, broken, meta)


def test_negative_control_qlib_code_form_is_caught(frame: pd.DataFrame) -> None:
    """混进一个 qlib 前缀式代码,断言格式断言会红。"""
    broken = frame.copy()
    broken.loc[broken.index[0], "code"] = "SH600000"
    _expect_failure(test_code_format_is_uniform, broken)


def test_negative_control_flag_basis_mismatch_is_caught(frame: pd.DataFrame) -> None:
    """把一行的 agreement_flag 翻过来,断言 flag/basis 一致性会红。"""
    broken = frame.copy()
    i = broken.index[broken["agreement_basis"] == "both_sources_agree"][0]
    broken.loc[i, "agreement_flag"] = False
    _expect_failure(test_agreement_flag_matches_its_basis, broken)


def test_negative_control_canonical_mislabel_is_caught(frame: pd.DataFrame) -> None:
    """把一行的 canonical 翻过来,断言 canonical 定义会红。"""
    broken = frame.copy()
    i = broken.index[broken["canonical"]][0]
    broken.loc[i, "canonical"] = False
    _expect_failure(test_canonical_definition_holds, broken)


def test_negative_control_size_check_catches_an_inflated_universe(
    frame: pd.DataFrame, grid: ub.Grid
) -> None:
    """把一批 union 行冒充成 canonical,断言规模上界会红。

    这条是整套测试里最要紧的负控:`canonical` 这一列的**全部价值**就是把宇宙
    规模压回名义值,如果规模断言抓不住"多塞了成员",这列就是装饰。
    """
    broken = frame.copy()
    mask = (broken["universe"] == "csi300") & (~broken["canonical"])
    assert mask.any(), "csi300 没有非 canonical 行,这条负控失去意义"
    broken.loc[mask, "canonical"] = True
    _expect_failure(test_canonical_size_on_every_trading_day, "csi300", broken, grid)
