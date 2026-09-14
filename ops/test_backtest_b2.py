# -*- coding: utf-8 -*-
"""`reference/b2_engine.py` 的判据测试（裁定 N-83 的「声明→配置的映射逐字段可测」）。

分三组：

1. **两份补丁的 sha 门** —— 证明本模块用的 P-SELL 与 2026-09-03 materiality screen
   用的**逐字节相同**；
2. **`config_from_declared` 逐字段** —— 每一个声明字段各有一条：值错必红、缺失必红、
   值确实流进 B2 的常量。**不允许一条笼统的「大概能映射」盖过去**（D-27）；
3. **两处同值常量的对齐断言**（D-21）。

跑完整回测的那几条在 `ops/acceptance/s7_b2_wrapper_gate.py`（要 1818 天面板，太慢，
不进单测）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import genebench_config as cfg                                        # noqa: E402
from ops import screen_runner as sr                                   # noqa: E402
from reference import b2_engine as b2                                 # noqa: E402
from reference import backtest                                        # noqa: E402
from reference import s7_oracle_common as cor                         # noqa: E402

TASK = cfg.GENEBENCH_ROOT / "reference" / "tasks" / "v1.0-smoke" / "s7-cor-01" / "task.yaml"


@pytest.fixture(scope="module")
def declared() -> dict:
    return yaml.safe_load(TASK.read_text(encoding="utf-8"))["declared"]


# ------------------------------------------------------------------ 补丁 sha 门
def test_frozen_b2_source_sha_is_pinned():
    assert b2._sha(b2.B2_SOURCE.read_text(encoding="utf-8")) == b2.B2_SHA256


def test_p_sell_patched_sha_matches_the_materiality_screen():
    """这个值来自 `ops/reports/materiality_s7_sell_rule.json` 的 `impls.B2.patched_sha256`。
    对上了才说明「sell_rule 两读法 material」那份实测能给这份 gold 背书。"""
    assert b2._sha(b2.source(ledger=False)) == b2.P_SELL_PATCHED_SHA256


def test_p_sell_edits_match_the_screen_harness():
    """D-21：同一份补丁在两处各存一份，必须有断言把它们绑住。"""
    mine = [tuple(e) for e in b2.P_SELL_EDITS]
    theirs = [tuple(e) for e in sr.SWITCH_EDITS["P-SELL"]["B2"]]
    assert mine == theirs


def test_warmup_days_agrees_with_the_oracle_trunk():
    assert b2.WARMUP_DAYS == cor.WARMUP_DAYS


def test_ledger_patch_only_adds_lines():
    """台账补丁**只加不改**：打完之后，原文的每一行都还在。"""
    before = b2.source(ledger=False).splitlines()
    after = set(b2.source(ledger=True).splitlines())
    missing = [ln for ln in before if ln not in after]
    assert not missing, f"台账补丁删改了原文：{missing[:3]}"


def test_anchor_that_no_longer_matches_raises():
    with pytest.raises(b2.WrapperError, match="锚点"):
        b2._apply("hello", [("不存在的锚点", "x")], "测试")


def test_backtest_reexports_the_b2_symbols():
    """`s7_oracle_common.run_engine` 调的是 `reference.backtest.run` —— 断在这里。"""
    assert backtest.run is b2.run
    assert backtest.config_from_declared is b2.config_from_declared


# ------------------------------------------------------------------ 逐字段映射
def test_released_declaration_maps_cleanly(declared):
    c = b2.config_from_declared(declared)
    assert c["INIT_CASH"] == 100_000_000.0 and c["LOT"] == 100
    assert c["TOPK"] == 50 and c["NDROP"] == 5
    assert c["BUY_RATE"] == 0.0005 and c["SELL_RATE"] == 0.0015 and c["MIN_COST"] == 5.0
    assert c["sell_rule"] == "worst_n_drop" and c["rebalance_frequency"] == "daily"


@pytest.mark.parametrize("field,bad", [
    ("adjust", "none"), ("fill_price", "open"), ("settlement", "t_plus_0"),
    ("share_accounting", "raw_shares"), ("delisting_policy", "hold_forever"),
    ("tradability_policy", "force"), ("risk_free_rate", 0.02),
    ("first_rebalance_day", "first_period_end"),
])
def test_each_contract_pinned_field_goes_red_on_a_different_value(field, bad, declared):
    """B2 是照契约写死这些取值的。声明成别的还照跑 =「声明与实现不一致且无人报错」。"""
    with pytest.raises(b2.WrapperError, match=field):
        b2.config_from_declared({**declared, field: bad})


@pytest.mark.parametrize("field", [
    "adjust", "fill_price", "settlement", "share_accounting", "delisting_policy",
    "tradability_policy", "risk_free_rate", "first_rebalance_day",
    "initial_capital", "lot_size", "strategy", "cost_model",
    "rebalance_frequency", "sell_rule",
])
def test_each_required_field_goes_red_when_missing(field, declared):
    d = {k: v for k, v in declared.items() if k != field}
    with pytest.raises(b2.WrapperError):
        b2.config_from_declared(d)


@pytest.mark.parametrize("field,const,value,want", [
    ("initial_capital", "INIT_CASH", 5_000_000, 5_000_000.0),
    ("lot_size", "LOT", 200, 200),
])
def test_numeric_declarations_flow_into_the_engine_constants(field, const, value, want, declared):
    assert b2.config_from_declared({**declared, field: value})[const] == want


@pytest.mark.parametrize("key,const,value,want", [
    ("topk", "TOPK", 30, 30), ("n_drop", "NDROP", 3, 3),
])
def test_strategy_fields_flow_through(key, const, value, want, declared):
    d = {**declared, "strategy": {**declared["strategy"], key: value}}
    assert b2.config_from_declared(d)[const] == want


@pytest.mark.parametrize("key,const,value,want", [
    ("buy_bps", "BUY_RATE", 10, 0.001),
    ("sell_bps", "SELL_RATE", 20, 0.002),
    ("min_cost_cny", "MIN_COST", 8, 8.0),
])
def test_cost_model_bps_are_converted_not_copied(key, const, value, want, declared):
    """bps → 比率要除 10000。直接抄进去的话费用会差 **四个数量级**，
    而回测照样跑得完、指标照样出得来。"""
    d = {**declared, "cost_model": {**declared["cost_model"], key: value}}
    assert b2.config_from_declared(d)[const] == pytest.approx(want)


def test_nonzero_impact_cost_is_refused(declared):
    """B2 不计滑点（契约 §3）。非零值照跑就是把一条声明当空气。"""
    d = {**declared, "cost_model": {**declared["cost_model"], "impact_cost": 0.001}}
    with pytest.raises(b2.WrapperError, match="impact_cost"):
        b2.config_from_declared(d)


def test_wrong_strategy_type_is_refused(declared):
    with pytest.raises(b2.WrapperError, match="TopkDropout"):
        b2.config_from_declared({**declared, "strategy": {**declared["strategy"],
                                                          "type": "EqualWeight"}})


@pytest.mark.parametrize("freq", ["weekly", "monthly"])
def test_weekly_and_monthly_are_refused_while_their_epsilon_is_unusable(freq, declared):
    """N-85：那两档的 ε `usable=false`，gold 出得来但判不了。"""
    with pytest.raises(b2.WrapperError, match="N-85"):
        b2.config_from_declared({**declared, "rebalance_frequency": freq})


def test_unknown_rebalance_frequency_is_refused(declared):
    with pytest.raises(b2.WrapperError, match="三档"):
        b2.config_from_declared({**declared, "rebalance_frequency": "hourly"})


@pytest.mark.parametrize("rule", ["worst_n_drop", "dropped_from_target"])
def test_both_sell_rule_readings_are_accepted(rule, declared):
    """A-1 的两个读法都得接 —— 写死任何一边，四道题里就有一半的 gold 与题面对不上。"""
    assert b2.config_from_declared({**declared, "sell_rule": rule})["sell_rule"] == rule


def test_unknown_sell_rule_is_refused(declared):
    with pytest.raises(b2.WrapperError, match="sell_rule"):
        b2.config_from_declared({**declared, "sell_rule": "sell_everything"})


def test_an_unmapped_declaration_field_is_refused(declared):
    """静默忽略一个声明字段的表现是「题面声明了、gold 没照做」，两边都不报。"""
    with pytest.raises(b2.WrapperError, match="不认识的字段"):
        b2.config_from_declared({**declared, "brand_new_knob": 1})


def test_passthrough_fields_are_recorded_not_dropped(declared):
    c = b2.config_from_declared(declared)
    assert c["calendar_id"] == "SSE" and c["benchmark"] == "equal_weight_universe"


# ------------------------------------------------------------------ 面板前置条件
def test_panel_shorter_than_warmup_is_refused(declared):
    tiny = pd.DataFrame({"date": ["2026-07-01"] * 2, "code": ["SH600000", "SZ000001"],
                         "close": [1.0, 2.0], "factor": [1.0, 1.0],
                         "in_universe": [True, True], "has_price": [True, True],
                         "is_delisted": [False, False], "signal": [0.1, 0.2]})
    with pytest.raises(b2.WrapperError, match="暖机"):
        b2.run(tiny, b2.config_from_declared(declared))


def test_sell_rule_env_is_restored_after_load(monkeypatch):
    monkeypatch.setenv("GB_SELL_RULE", "sentinel")
    b2.load("worst_n_drop", ledger=False)
    import os
    assert os.environ["GB_SELL_RULE"] == "sentinel", "开关的 env 没还原，会漏给下一次运行"
