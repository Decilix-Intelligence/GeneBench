# -*- coding: utf-8 -*-
"""`calibration.json` 的口径清单验收：五项冻结项 + F-1…F-5 + E-1 是否都落位。

**这份测试是给签字人用的**：它把「口径清单」从一份要人肉核对的 JSON
变成一组会红的断言。逐条对应签字原话，改任何一条口径都会红。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import genebench_config as cfg  # noqa: E402
from reference import calibration as cal  # noqa: E402
from reference import factor_crosscheck as fc  # noqa: E402
from snapshots import qlib_provider as qp  # noqa: E402

pytestmark = pytest.mark.skipif(not cal.OUT.exists(), reason="calibration.json 尚未生成")


@pytest.fixture(scope="module")
def C() -> dict:
    return json.loads(cal.OUT.read_text(encoding="utf-8"))


# ---------------------------------------------------- 第一批冻结（README 第 4 条）

def test_freeze1_quantiles_ties_weighting_rebalance(C):
    s = C["scoring"]
    assert s["quantiles"] == 10
    assert s["tie_handling"] == "average"
    assert s["weighting"] == "equal"
    assert s["rebalance_timing"] == "after_close"


def test_freeze1_holding_periods(C):
    assert C["scoring"]["holding_periods"] == [1, 5, 20]
    assert list(qp.HOLDING_PERIODS) == [1, 5, 20], "两处持有期不一致"


def test_freeze1_sharpe_annualized_and_gross_net_separated(C):
    sh = C["scoring"]["sharpe"]
    assert sh["annualized"] is True and sh["sqrt_factor"] == 252
    assert sh["gross_and_net_reported_separately"] is True
    assert C["scoring"]["sortino"]["MAR"] == 0.0


def test_freeze1_turnover_is_double_recorded(C):
    """**最容易漏的一处**：turnover 双记是两个数，只记一个下游算成本差一倍。"""
    t = C["scoring"]["turnover"]
    assert t["one_way"] is True and t["two_way"] is True and t["both_required"] is True
    # 判别力：ε 的指标表里必须**同时**有 one-way 与 two-way 两项实测值，不是一项换算出来的
    freqs = C["epsilon"]["by_frequency"]
    assert freqs, "ε 没有任何一档"
    for f, v in freqs.items():
        m = v["by_metric"]
        assert "turnover_one_way_mean" in m and "turnover_two_way_mean" in m, (f, sorted(m))
        one, two = m["turnover_one_way_mean"], m["turnover_two_way_mean"]
        # 两项的分歧不完全相等 → 它们是各自实测的，不是一项 ÷2 得来的
        assert one["max_abs_diff"] != two["max_abs_diff"], (
            f"{f}: one-way 与 two-way 的分歧完全相同，像是一项换算出来的")


def test_freeze1_ic_summary_has_positive_ratio_and_coverage(C):
    ic = C["scoring"]["ic_summary"]
    assert ic["positive_ratio_required"] and ic["coverage_required"]
    for k in ("mean", "std", "ICIR", "positive_ratio", "coverage", "CI"):
        assert k in ic["report"], k


def test_freeze1_uncertainty_is_block_bootstrap_not_only_newey_west(C):
    """**第二处最容易漏的**：block-bootstrap 不能用 Newey–West 替代。"""
    u = C["scoring"]["uncertainty"]
    bb = u["block_bootstrap"]
    assert bb["method"] == "moving_block_bootstrap"
    assert bb["n_resamples"] >= 1000 and 0 < bb["ci_level"] < 1
    assert "seed" in bb and "block_length_rule" in bb
    for k in ("IC", "RankIC", "quantile_spread", "alpha", "sharpe"):
        assert k in bb["applies_to"], k
    nw = u["newey_west"]
    assert nw["enabled"] is True
    assert "不得替代" in nw["role"], nw["role"]


def test_freeze1_gate_semantics_not_deduction(C):
    g = C["scoring"]["gate_semantics"]
    assert "invalid" in g and "不是扣分" in g


# ---------------------------------------------------- 第二批冻结（F-1…F-5）

def test_freeze2_rank_correlation_definitions(C):
    r = C["rank_correlation"]
    assert r["F-2_tau_quantile"] == fc.TAU_QUANTILE == 10.0
    assert r["F-2_pooled_not_time_averaged"] is True
    assert r["F-4_degenerate_threshold"] == fc.DEGENERATE_UNIQUE_RATIO == 0.05
    assert r["F-4_min_cross_section"] == fc.MIN_CROSS_SECTION


def test_tau_is_pooled_and_excludes_operator_conflicts(C):
    t = C["tau"]
    assert 0.9 < t["value"] < 1.0
    assert t["excluded_operator_conflict"], "算子冲突排除集是空的"
    assert t["factors_used"] + len(t["excluded_operator_conflict"]) <= t["comparable_factors"]
    assert t["degenerate_rule"]["removal_raises_tau"] is True
    assert "不是" in t["degenerate_rule"]["note"], "剔除方向的说明丢了"


def test_evaluation_right_edge_is_hard_blocked(C):
    e = C["evaluation_right_edge"]
    assert e["must_hard_block"] is True
    got = {int(k): v for k, v in e["by_holding_period"].items()}
    assert got == qp.evaluation_right_edges(), (got, qp.evaluation_right_edges())
    assert got[1] > got[5] > got[20]


def test_operator_conflict_set_is_exposed_to_task_generation(C):
    from reference.operator_flags import tasks_should_avoid
    o = C["operator_conflicts"]
    assert o["s3_must_avoid"] is True
    assert set(o["gold_suspect"]) == set(tasks_should_avoid())
    assert len(o["gold_suspect"]) >= 20


# ---------------------------------------------------- E-1

def test_epsilon_refuses_an_ineffective_source(C):
    """E-1 / D-05：失效的标定源必须**留在案上作反面记录**，而不是被悄悄替换掉。

    判别力两半：(a) 那条作废记录里的极差**确实**低到不可用（否则这条断言是空的）；
    (b) 现行 ε 换了方法，且方法名里不再是跨库版本。
    """
    sup = C["epsilon"]["superseded_cross_version"]
    assert sup["max_relative_spread"] is not None
    assert sup["max_relative_spread"] < 1e-10, (
        "作废的那个标定源现在有效了 —— 这条断言当前是空的，去核实")
    assert "舍入" in sup["verdict"] and "反面记录" in sup["verdict"]
    assert C["epsilon"]["method"] == "dual_independent_implementation_pairwise"
    # 分档的 usable 必须诚实：有超阈项就不能标可用
    for f, v in C["epsilon"]["by_frequency"].items():
        assert v["usable"] == (len(v["implausible"]) == 0), f


def test_epsilon_is_stratified_by_rebalance_frequency(C):
    """ε 必须**分档**给 —— 实测跨调仓频率相差约 3 个数量级。"""
    e = C["epsilon"]
    assert e["rebalance_frequency_is_required"] is True
    freqs = e["by_frequency"]
    assert set(freqs) >= {"daily", "weekly", "monthly"}, sorted(freqs)
    # 判别力：三档的 ε 必须**真的不同**，否则「分档」这件事没有意义
    def eps(f, m):
        return freqs[f]["by_metric"].get(m, {}).get("epsilon")
    d, w, mo = (eps(x, "turnover_two_way_mean") for x in ("daily", "weekly", "monthly"))
    assert None not in (d, w, mo)
    assert mo > w > d, (d, w, mo)
    assert mo / d > 100, f"三档 ε 只差 {mo / d:.1f} 倍，分档的必要性存疑"
    assert "低频题需要更宽的容差" in e["no_global_epsilon"]


def test_epsilon_is_per_metric_never_global(C):
    """签字要求 ①：逐指标分别给，不给全局单值。"""
    e = C["epsilon"]
    for f, v in e["by_frequency"].items():
        assert len(v["by_metric"]) >= 8, (f, len(v["by_metric"]))
    # 不许出现一个"全局 ε"字段
    assert not any(k in e for k in ("global_epsilon", "epsilon_value", "value"))
    assert "逐指标" in e["no_global_epsilon"]
    # 容差类型规则必须在案，且由代码强制
    t = e["tolerance_rule"]
    assert "assert_tolerance_kind" in t["enforced_by"]
    assert "ann_return_net" in t["absolute"]


def test_epsilon_records_full_package_manifest(C):
    """签字要求 ②：每个版本组合的完整包清单进 manifest。"""
    from reference import epsilon as ep
    raw = json.loads(ep.OUT.read_text(encoding="utf-8"))
    assert len(raw["environments"]) >= 3
    for name, v in raw["environments"].items():
        assert len(v["packages"]) > 100, f"{name} 的包清单只有 {len(v['packages'])} 项"
    assert len({tuple(sorted(v["key_versions"].items()))
                for v in raw["environments"].values()}) == len(raw["environments"]), \
        "有两个环境的关键版本组合相同"
    assert len({v["key_versions"]["pyqlib"] for v in raw["environments"].values()}) == 1, \
        "pyqlib 没有保持不变，变量没隔离干净"


def test_epsilon_zero_spread_metrics_are_flagged_not_backfilled(C):
    """差为 0 的指标单独标注，不许用别的指标代填。"""
    freqs = C["epsilon"]["by_frequency"]
    flagged = [(f, m) for f, v in freqs.items() for m in v["no_freedom"]]
    assert flagged, "没有任何一档出现零分歧指标 —— 这条断言当前是空的"
    for f, m in flagged:
        rec = freqs[f]["by_metric"][m]
        assert rec["status"] == "no_implementation_freedom"
        assert rec["epsilon"] is None, "零分歧指标不该有 ε 值"
        assert "不得用其他指标的 ε 代填" in rec["note"]


def test_provider_digest_is_pinned(C):
    """配置必须钉住它是在哪份 provider 上标的。"""
    got = json.loads(qp.MANIFEST.read_text())["digest"]["files_sha256_digest"]
    assert C["provider"]["digest"] == got
