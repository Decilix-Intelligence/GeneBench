# -*- coding: utf-8 -*-
"""ε 的度量类型规则：相对容差 vs 绝对容差。

**为什么要有这条规则**：相对容差施加在「构造上可能趋零」的量上没有意义。
实测 `ann_return_net` 的相对差 90.85% —— 但那是
毛收益(≈0.057) 减 成本拖累(≈0.05) 的**小差被结构性放大**，
同一批实现在 `ann_vol_net` 上只差 1.53%。
照 90.85% 定阈值会让 S7 对净收益近乎无约束。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reference import epsilon_dual as ed  # noqa: E402


def test_zero_approaching_metrics_get_absolute_tolerance():
    for m in ed.ZERO_APPROACHING:
        assert ed.tolerance_kind(m) == "absolute", m
    assert "ann_return_net" in ed.ZERO_APPROACHING
    assert "alpha" in ed.ZERO_APPROACHING
    assert "excess_return" in ed.ZERO_APPROACHING


def test_scale_free_metrics_get_relative_tolerance():
    for m in ("sharpe_net", "max_drawdown_net", "turnover_one_way_mean",
              "turnover_two_way_mean", "ann_vol_net", "win_rate_net", "total_cost"):
        assert ed.tolerance_kind(m) == "relative", m


def test_misconfiguring_a_zero_approaching_metric_raises():
    """**这条是硬拦，不是提示。** 给趋零指标配相对容差必须直接抛。"""
    with pytest.raises(ValueError, match="必须用 absolute"):
        ed.assert_tolerance_kind("ann_return_net", "relative")
    with pytest.raises(ValueError, match="必须用 relative"):
        ed.assert_tolerance_kind("sharpe_net", "absolute")
    # 正确配置不抛
    ed.assert_tolerance_kind("ann_return_net", "absolute")
    ed.assert_tolerance_kind("sharpe_net", "relative")


def test_the_rule_actually_changes_a_verdict():
    """判别力：这条规则必须真的改变过某个指标的结论，否则它是装饰。

    实测 `ann_return_net`：相对差 90.85%（会被判 implausible、不写成 ε），
    绝对差 0.01254（→ ε = 0.01881 收益点，可标定）。
    """
    import json
    if not ed.OUT.exists():
        pytest.skip("ε 产物尚未生成")
    r = json.loads(ed.OUT.read_text(encoding="utf-8"))
    rec = r["epsilon_by_metric"].get("ann_return_net")
    if rec is None:
        pytest.skip("产物里没有 ann_return_net")
    assert rec["tolerance_kind"] == "absolute"
    assert rec["max_rel_diff"] > ed.IMPLAUSIBLE_REL_DIFF, (
        "相对差没有超过阈值 —— 那这条规则当前改变不了任何结论，是装饰")
    assert rec["status"] == "calibrated" and rec["epsilon"] is not None
    assert "收益点" in rec["unit"]


def test_tolerance_rule_is_recorded_in_the_artifact():
    import json
    if not ed.OUT.exists():
        pytest.skip("ε 产物尚未生成")
    r = json.loads(ed.OUT.read_text(encoding="utf-8"))
    t = r["tolerance_rule"]
    assert "assert_tolerance_kind" in t["enforced_by"]
    assert "没有意义" in t["why"]
