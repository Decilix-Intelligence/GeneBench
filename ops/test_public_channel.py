# -*- coding: utf-8 -*-
"""卡 2.5 公开通道的 A 档验收（B0① –⑥ 的落地）。零外部依赖、纯夹具。"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from snapshots.public import gates as G          # noqa: E402
from snapshots.public import manifest as M       # noqa: E402


def _bars(scale: float = 1.0) -> pd.DataFrame:
    return pd.DataFrame({
        "low": [9.0, 10.0, 20.0], "high": [11.0, 12.0, 22.0],
        "close": [10.0, 11.0, 21.0], "volume": [100.0, 200.0, 50.0],
        "amount": [1000.0 * scale, 2200.0 * scale, 1050.0 * scale],
    })


# --------------------------------------------------------------- B0② 单位门

def test_unit_gate_passes_on_normalised_data():
    rep = G.assert_vwap_band(_bars(), source="私有湖口径")
    assert rep.ratio == 1.0 and rep.median_vwap_over_close == pytest.approx(1.0)


@pytest.mark.parametrize("scale,what", [
    (0.001, "社区 release：amount 仍是千元 —— 差 1000×"),
    (0.01, "tushare 原生 amount 千元 / vol 手混算"),
    (1000.0, "反向放大"),
])
def test_unit_gate_is_zero_percent_when_units_are_off(scale, what):
    """**差 1000 倍时这个比率是 0%** —— 这条判据比任何文档核对都硬。"""
    rep = G.vwap_band_report(_bars(scale))
    assert rep.ratio == 0.0, (what, rep)
    with pytest.raises(G.PublicChannelBlocked, match="单位没归一"):
        G.assert_vwap_band(_bars(scale), source=what)


def test_unit_gate_refuses_to_pass_on_zero_judgeable_rows():
    """零行不是「过了」—— 这是 D-06 家族最常见的形态。"""
    df = _bars()
    df["volume"] = 0.0
    with pytest.raises(G.PublicChannelBlocked, match="零行不是"):
        G.vwap_band_report(df)


def test_unit_gate_missing_column_is_not_a_pass():
    with pytest.raises(G.PublicChannelBlocked, match="缺列不是"):
        G.vwap_band_report(_bars().drop(columns=["amount"]))


def test_unit_gate_shares_the_tolerance_with_card_2_1a():
    """抄一份常量到公开通道会漂，而漂的表现是「公开过了、私有没过」，两边都不报错。"""
    from snapshots.qlib_provider import VWAP_BAND_REL_TOL
    assert G.VWAP_BAND_REL_TOL is VWAP_BAND_REL_TOL


# --------------------------------------------------------------- B0③ 前收

def test_pre_close_source_is_daily_not_stk_limit():
    """`stk_limit.pre_close` 在私有湖里**全为 NULL**（实测）——
    §3 原文写「从前收盘推」，输入假设因此改为 `daily.pre_close`。"""
    G.assert_pre_close_source(G.PRE_CLOSE_SOURCE)
    with pytest.raises(G.PublicChannelBlocked, match="全为 NULL"):
        G.assert_pre_close_source("stk_limit.pre_close")
    with pytest.raises(G.PublicChannelBlocked, match="未登记"):
        G.assert_pre_close_source("somewhere_else.pre_close")


# --------------------------------------------------------------- B0④⑤⑥ 物料

def test_public_package_carries_exactly_the_seven_items():
    """公开包的表**正好**对上范围核定的七项 —— 多一张就是多一条要交代的依赖，
    少一张就是建出来跑不通。"""
    import re
    reg = tuple(sorted(set(re.findall(
        r'dataset="([a-z_0-9]+)"',
        (_REPO / "snapshots" / "v1_tables.py").read_text(encoding="utf-8")))))
    assert len(reg) == 22, reg
    pub = M.public_tables(reg)
    assert pub == ["adj_factor", "daily", "index_weight", "stk_limit",
                   "stock_basic", "suspend_d", "trade_cal"], pub


def test_manifest_categories_are_disjoint():
    M.assert_manifest_disjoint()
    import unittest.mock as mock
    with mock.patch.object(M, "PUBLIC_EXCLUDED_TABLES",
                           M.PUBLIC_EXCLUDED_TABLES + ("income",)):
        with pytest.raises(M.ManifestError, match="同时含"):
            M.assert_manifest_disjoint()


def test_financial_tables_stay_private():
    """N-58①：`/fundamentals` 不发放给 v1 任何一道题，6 张财务快照不进公开包。
    baostock 的季频财务**无 f_ann_date**，而我们的 PIT 判据正是它 —— 补不了。"""
    for t in ("income", "balancesheet", "cashflow"):
        assert t in M.PRIVATE_ONLY_TABLES and f"{t}_vip" in M.PRIVATE_ONLY_TABLES


def test_gold_definition_surface_is_in_the_public_package():
    """N-58⑥：少了它们，拿到包的人复现不了 —— τ 恰恰标定在「两个实现有多一致」上。"""
    assert any("compiled" in x for x in M.PUBLIC_FROZEN_ARTIFACTS)
    assert any("factorlib_pinned" in x for x in M.PUBLIC_FROZEN_ARTIFACTS)
    assert len(M.PUBLIC_FROZEN_ARTIFACTS) == 6


def test_memory_probe_keys_never_get_snapshotted():
    """冻进快照就等于把答案放进了交付物 —— 而探针问的正是
    「模型记没记住冻结线之后的事」。"""
    assert set(M.NEVER_SNAPSHOT) == {"cn_cpi", "repurchase", "block_trade"}
    reg_txt = (_REPO / "snapshots" / "v1_tables.py").read_text(encoding="utf-8")
    for t in M.NEVER_SNAPSHOT:
        assert f'dataset="{t}"' not in reg_txt, f"{t} 被登记进 v1 快照了"
