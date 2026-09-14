# -*- coding: utf-8 -*-
"""`reference/make_epsilon_panel.py` 的判据测试（N-82 收编）。

这份构建器定义 S7 gold 的**全部输入**，此前住在 `scratch/` 下、不受任何门保护。
收编之后测的是**派生那一半**（纯函数）—— 取数那一半要 qlib 环境，
它的判据是另一条：`ops/acceptance/s7_panel_vs_frozen.py` 用走网关的第二实现逐格对拍。

四种形态（契约 §1）各有一条；每条都能被喂真改动打红。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reference import make_epsilon_panel as M                         # noqa: E402

D = pd.to_datetime(["2026-07-01", "2026-07-02", "2026-07-03", "2026-07-06", "2026-07-07"])
CODES = ["SH600000", "SZ000001", "SH600068"]


def _grid(days=D, codes=CODES) -> pd.DataFrame:
    return pd.MultiIndex.from_product([days, codes],
                                      names=["date", "code"]).to_frame(index=False)


def _px(rows) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["date", "code", "close", "factor"])


#: A 全程有价；B 第 3 天停牌后复牌；C 第 3 天起再无价（退市）。
PX = _px([(D[i], "SH600000", 10.0 + i, 1.0) for i in range(5)]
         + [(D[i], "SZ000001", 20.0 + i, 1.0) for i in (0, 1, 3, 4)]
         + [(D[i], "SH600068", 30.0 + i, 1.0) for i in (0, 1)])

#: A 全程成分；B 只在后两天；C 调出又调入（**两段区间**）。
SPANS = {"SH600000": [("2026-07-01", "2026-07-07")],
         "SZ000001": [("2026-07-06", "2026-07-07")],
         "SH600068": [("2026-07-01", "2026-07-01"), ("2026-07-03", "2026-07-07")]}


@pytest.fixture(scope="module")
def flags() -> pd.DataFrame:
    return M.derive_flags(_grid(), PX, M.membership_frame(SPANS))


def cell(df, code, i, col):
    s = df[(df.code == code) & (df.date == D[i])][col]
    return s.iloc[0] if len(s) else None


def test_grid_is_complete(flags):
    """全格：无价的格必须**存在**。靠行缺失暗示「没有价」正是 v1 的根因 ——
    三份独立实现各自发明了规则，B 侧共 292 次「消失即清仓」。"""
    assert len(flags) == len(D) * len(CODES)


def test_columns_are_the_contract_shape(flags):
    assert {"date", "code", "close", "factor", "in_universe",
            "has_price", "is_delisted"} <= set(flags.columns)


# ------------------------------------------------------------------ 四种形态
def test_normal_member_is_in_universe_and_priced(flags):
    assert bool(cell(flags, "SH600000", 0, "in_universe"))
    assert bool(cell(flags, "SH600000", 0, "has_price"))
    assert not bool(cell(flags, "SH600000", 0, "is_delisted"))


def test_dropped_from_index_but_still_priced(flags):
    """第二形态：`in_universe=False` 且 `has_price=True` —— 已持有的可以卖。"""
    assert not bool(cell(flags, "SZ000001", 0, "in_universe"))
    assert bool(cell(flags, "SZ000001", 0, "has_price"))
    assert not bool(cell(flags, "SZ000001", 0, "is_delisted"))


def test_suspended_is_unpriced_but_not_delisted(flags):
    """第三形态：停牌仍上市 —— `SZ000001` 第 3 天无价、第 4 天又有。"""
    assert not bool(cell(flags, "SZ000001", 2, "has_price"))
    assert not bool(cell(flags, "SZ000001", 2, "is_delisted"))
    assert bool(cell(flags, "SZ000001", 3, "has_price"))


def test_delisted_starts_after_the_last_priced_day(flags):
    """第四形态：`SH600068` 最后有价日是第 2 天，第 3 天起 is_delisted。"""
    assert bool(cell(flags, "SH600068", 1, "has_price"))
    assert not bool(cell(flags, "SH600068", 1, "is_delisted"))
    assert bool(cell(flags, "SH600068", 2, "is_delisted"))


def test_a_code_priced_through_the_end_is_never_delisted(flags):
    assert not flags[flags.code == "SH600000"].is_delisted.any()


# ------------------------------------------------------------------ 多段成分区间
def test_two_membership_spans_are_both_honoured(flags):
    """`SH600068` 调出又调入：第 1 天在、第 2 天**不在**、第 3 天起又在。

    只取第一段的话第二段会被记成不在成分内 —— 而那正是第二形态要区分的东西。
    """
    assert bool(cell(flags, "SH600068", 0, "in_universe"))
    assert not bool(cell(flags, "SH600068", 1, "in_universe"))
    assert bool(cell(flags, "SH600068", 2, "in_universe"))


def test_membership_frame_flattens_every_span():
    m = M.membership_frame(SPANS)
    assert len(m) == 4                                   # 1 + 1 + 2
    assert set(m.code) == set(CODES)


def test_a_code_with_no_span_is_never_in_universe():
    f = M.derive_flags(_grid(), PX, M.membership_frame({"SH600000": SPANS["SH600000"]}))
    assert not f[f.code == "SZ000001"].in_universe.any()


# ------------------------------------------------------------------ 暖机
@pytest.mark.parametrize("n_window,expect_index", [(3, 1), (5, 0), (10, 0)])
def test_warmup_start_backs_up_six_trading_days(n_window, expect_index):
    full = [f"2026-06-{d:02d}" for d in range(1, 11)]
    got = M.warmup_start(full, list(range(n_window)))
    assert got == full[expect_index][:10]


def test_warmup_is_six_not_a_calendar_offset():
    """往前数的是**交易日**，不是自然日。写成 `start - 6 days` 遇周末就少数了。"""
    full = [f"2026-06-{d:02d}" for d in (1, 2, 3, 4, 5, 8, 9, 10, 11, 12)]
    assert M.warmup_start(full, list(range(4))) == "2026-06-01"
    assert M.WARMUP_DAYS == 6


# ------------------------------------------------------------------ 信号与列序
def test_attach_signal_left_joins_and_formats_the_date(flags):
    sig = pd.DataFrame({"date": [D[0]], "code": ["SH600000"], "signal": [0.5]})
    out = M.attach_signal(flags, sig)
    assert list(out.columns) == list(M.PANEL_COLUMNS)
    assert out.date.iloc[0] == "2026-07-01"
    assert float(out[(out.code == "SH600000") & (out.date == "2026-07-01")].signal.iloc[0]) == 0.5
    assert out[(out.code == "SZ000001")].signal.isna().all()      # 没信号的格留空，不填 0
