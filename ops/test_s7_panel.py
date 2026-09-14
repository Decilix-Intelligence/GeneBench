# -*- coding: utf-8 -*-
"""`s7_oracle_common.fetch_panel` 与面板验收门的判据测试。

两部分：

1. **拼面板**：喂一个答案已知的合成网关，逐列核契约 §1 的四种形态。
2. **验收门逐段必红**（D-27 实施要求）：`s7_panel_vs_frozen.verdict()` 声称保护
   七段（行集合 / close 值 / close 空值形态 / factor 值 / factor 只在有价格处 /
   factor 空值差只落在无价格处 / 三个布尔列）。**每一段各喂一个真改动，必须翻红**——
   不允许用一条笼统的「随便改点什么它会红」盖过去。恒绿的门与恒红的一样会被绕过（F7）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reference import gateway_client as gc
from reference import s7_oracle_common as cor                              # noqa: E402
from ops.acceptance import s7_panel_vs_frozen as acc                       # noqa: E402

DAYS = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09",
        "2026-01-12", "2026-01-13", "2026-01-14", "2026-01-15", "2026-01-16"]
WINDOW = {"start": DAYS[6], "end": DAYS[-1]}          # 前面正好留 6 个暖机交易日
AS_OF = "2026-01-30"                                   # **晚于窗口末日** —— factor 的基准日
TASK = {"window": WINDOW, "as_of": AS_OF, "universe": "csi300"}

#: A 全程有价但第 5 天停牌；B 只在后半段入选；C 第 8 天起没有价（退市）。
PRICES = {
    "600000.SH": {d: 10.0 + i for i, d in enumerate(DAYS) if d != DAYS[4]},
    "000001.SZ": {d: 20.0 + i for i, d in enumerate(DAYS)},
    "600068.SH": {d: 30.0 + i for i, d in enumerate(DAYS[:8])},
}
#: adj 在第 9 天除权一次，`as_of` 当天又一次 —— 基准日取错就会露馅。
ADJ = {
    "600000.SH": {**{d: 2.0 for d in DAYS[:8]}, DAYS[8]: 2.5, DAYS[9]: 2.5, AS_OF: 4.0},
    "000001.SZ": {**{d: 1.0 for d in DAYS}, AS_OF: 1.0},
    "600068.SH": {d: 3.0 for d in DAYS[:8]},          # 退市票在 as_of 没有行
}
MEMBERS = {d: (["600000.SH", "600068.SH"] if i < 5 else ["600000.SH", "000001.SZ"])
           for i, d in enumerate(DAYS)}


class FakeGateway:
    def trading_days(self, start, end):
        return [d for d in DAYS if start <= d <= end]

    def members(self, universe, date):
        return sorted(MEMBERS[date])

    def bars(self, codes, start, end, fields):
        return pd.DataFrame([{"code": c, "date": d, "status": "trade", "close": v}
                             for c in codes for d, v in PRICES[c].items() if start <= d <= end])

    def adj(self, codes, start, end):
        return pd.DataFrame([{"code": c, "date": d, "adj_factor": v}
                             for c in codes for d, v in ADJ[c].items() if start <= d <= end])


@pytest.fixture(scope="module")
def panel() -> pd.DataFrame:
    return cor.fetch_panel(FakeGateway(), TASK)


def cell(p, code, day, col):
    s = p[(p.code == code) & (p.date == day)][col]
    return s.iloc[0] if len(s) else None


# ------------------------------------------------------------------ 形状
def test_warmup_is_six_trading_days_not_calendar_days(panel):
    assert panel.date.min() == DAYS[0] and DAYS.index(WINDOW["start"]) == cor.WARMUP_DAYS


def test_panel_is_a_full_grid_of_days_by_ever_selected_codes(panel):
    """掉出指数的行必须在（契约 §1 第二形态）—— 只留有成分的格会把它们删掉。"""
    assert len(panel) == len(DAYS) * 3
    assert set(panel.code) == {"SH600000", "SZ000001", "SH600068"}


def test_columns_are_exactly_the_contract_eight(panel):
    assert list(panel.columns) == ["date", "code", "close", "factor",
                                   "in_universe", "has_price", "is_delisted", "signal"]


def test_window_start_must_be_a_trading_day():
    with pytest.raises(ValueError, match="不是交易日"):
        cor.trading_window(FakeGateway(), {**TASK, "window": {"start": "2026-01-10", "end": DAYS[-1]}})


def test_insufficient_warmup_raises_instead_of_shrinking_silently():
    with pytest.raises(ValueError, match="暖机"):
        cor.trading_window(FakeGateway(), {**TASK, "window": {"start": DAYS[1], "end": DAYS[-1]}})


# ------------------------------------------------------------------ factor 的基准日（N-80）
def test_factor_base_is_as_of_not_window_end(panel):
    """`SH600000` 的 adj 在窗口内是 2.0/2.5，`as_of` 是 4.0 —— 基准取窗口末日会得到 0.8。"""
    assert cell(panel, "SH600000", DAYS[0], "factor") == pytest.approx(2.0 / 4.0)
    assert cell(panel, "SH600000", DAYS[9], "factor") == pytest.approx(2.5 / 4.0)


def test_delisted_code_uses_its_own_last_adj_as_base(panel):
    """退市票在 `as_of` 没有 adj 行；基准退到它自己最后一个 —— factor 恒 1。"""
    assert cell(panel, "SH600068", DAYS[0], "factor") == pytest.approx(1.0)


def test_close_is_raw_times_factor(panel):
    assert cell(panel, "SH600000", DAYS[0], "close") == pytest.approx(10.0 * 0.5)


# ------------------------------------------------------------------ 四种形态（契约 §1）
def test_normal_member_is_in_universe_and_priced(panel):
    assert bool(cell(panel, "SH600000", DAYS[6], "in_universe"))
    assert bool(cell(panel, "SH600000", DAYS[6], "has_price"))


def test_dropped_from_index_but_still_trading_keeps_its_row(panel):
    """第二形态：`in_universe=False` 且 `has_price=True`（可以卖）。"""
    assert not bool(cell(panel, "SZ000001", DAYS[0], "in_universe"))
    assert bool(cell(panel, "SZ000001", DAYS[0], "has_price"))
    assert not bool(cell(panel, "SZ000001", DAYS[0], "is_delisted"))


def test_suspended_is_unpriced_but_not_delisted(panel):
    """第三形态：停牌仍上市 —— 与真退市必须分开。"""
    assert not bool(cell(panel, "SH600000", DAYS[4], "has_price"))
    assert not bool(cell(panel, "SH600000", DAYS[4], "is_delisted"))


def test_delisted_starts_the_day_after_the_last_priced_day(panel):
    assert bool(cell(panel, "SH600068", DAYS[7], "has_price"))
    assert not bool(cell(panel, "SH600068", DAYS[7], "is_delisted"))
    assert bool(cell(panel, "SH600068", DAYS[8], "is_delisted"))


def test_a_code_priced_through_the_end_is_never_delisted(panel):
    assert not panel[(panel.code == "SH600000")].is_delisted.any()


def test_factor_is_null_exactly_where_there_is_no_price(panel):
    """契约 §1 只给了 `原始价 = close / factor` —— 无价的格上它没有定义（N-82）。"""
    assert (panel.factor.isna() == panel.close.isna()).all()


def test_in_universe_follows_the_per_day_pit_list(panel):
    for d in DAYS:
        got = set(panel[(panel.date == d) & panel.in_universe].code)
        assert got == {gc.to_panel_code(c) for c in MEMBERS[d]}


def test_missing_signal_fixture_raises_instead_of_filling_nan(tmp_path):
    """题面 `inputs` 声明了 `work/signal.parquet`；缺输入不许拿 NaN 顶上（N-84）。"""
    with pytest.raises(FileNotFoundError, match="signal.parquet"):
        cor.load_signal(tmp_path)


# ------------------------------------------------------------------ 验收门逐段必红（D-27）
def _green_report() -> dict:
    return {
        "only_new": 0, "only_ref": 0,
        "factor_only_where_priced": {"new": 0, "ref": 0},
        "factor_nan_diff_all_unpriced": True,
        "columns": {
            "close": {"nan_pattern_equal": True, "n_over_tol": 0, "bitwise_equal": True},
            "factor": {"nan_pattern_equal": False, "n_over_tol": 0, "bitwise_equal": True},
            "in_universe": {"mismatch": 0}, "has_price": {"mismatch": 0},
            "is_delisted": {"mismatch": 0},
        },
    }


def test_verdict_is_green_on_a_clean_report():
    """先证它**能**绿 —— 恒红的门和恒绿的一样没用。"""
    assert acc.verdict(_green_report()) is True


@pytest.mark.parametrize("section,mutate", [
    ("行集合：新面板多出的格", lambda r: r.update(only_new=1)),
    ("行集合：冻结面板多出的格", lambda r: r.update(only_ref=1)),
    ("close 数值超容差", lambda r: r["columns"]["close"].update(n_over_tol=1)),
    ("close 不再逐位相等", lambda r: r["columns"]["close"].update(bitwise_equal=False)),
    ("factor 不再逐位相等", lambda r: r["columns"]["factor"].update(bitwise_equal=False)),
    ("close 空值形态不同", lambda r: r["columns"]["close"].update(nan_pattern_equal=False)),
    ("factor 数值超容差", lambda r: r["columns"]["factor"].update(n_over_tol=1)),
    ("本仓侧 factor 空而 close 非空", lambda r: r["factor_only_where_priced"].update(new=1)),
    ("冻结侧 factor 空而 close 非空", lambda r: r["factor_only_where_priced"].update(ref=1)),
    ("factor 空值差落到了有价格的格上", lambda r: r.update(factor_nan_diff_all_unpriced=False)),
    ("in_universe 不一致", lambda r: r["columns"]["in_universe"].update(mismatch=1)),
    ("has_price 不一致", lambda r: r["columns"]["has_price"].update(mismatch=1)),
    ("is_delisted 不一致", lambda r: r["columns"]["is_delisted"].update(mismatch=1)),
])
def test_verdict_goes_red_for_each_section_it_claims_to_protect(section, mutate):
    r = _green_report()
    mutate(r)
    assert acc.verdict(r) is False, f"{section}：喂了真改动，门没红"
