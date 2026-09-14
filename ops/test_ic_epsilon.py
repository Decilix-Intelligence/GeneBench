# -*- coding: utf-8 -*-
"""N-117 的红测：IC 族 ε 的双实现标定 + 合并 + scorer 侧取带。

纪律（D-27）：每条判据一正一反；**能被"什么都不做"通过的断言不算测试**。
本文件里三处"变异必红"是显式写出来的（`_mutate_*`），不是靠自觉。
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import genebench_config as cfg
from ops import ic_epsilon as ICE
from ops import merge_ic_epsilon as MRG
from scorer import l3 as L3


# ------------------------------------------------------------------ 口径一致性
def test_multiplier_and_thresholds_match_backtest_epsilon():
    """ε 的系数/地板/超阈**必须**与 2.2b 的回测 ε 同值。

    `ops.ic_epsilon` 刻意不 import `reference.epsilon_dual`（那是参考轴的冻结面，
    ops 侧引它会让"改一个 ops 文件"变成"改冻结根"），代价就是这三个数被抄了一遍 ——
    这条测试是那份抄写的唯一防线：任一处改了而另一处没改，这里红。
    """
    from reference import epsilon_dual as ed
    assert ICE.MULTIPLIER == ed.MULTIPLIER
    assert ICE.NOISE_FLOOR == ed.NOISE_FLOOR
    assert ICE.IMPLAUSIBLE_REL_DIFF == ed.IMPLAUSIBLE_REL_DIFF


def test_ic_zero_approaching_set_is_disjoint_from_backtest_one():
    """IC 族的趋零集合与回测的**不是一回事** —— 这正是不能复用 `ed.tolerance_kind` 的原因。"""
    from reference import epsilon_dual as ed
    assert ICE.ZERO_APPROACHING & ed.ZERO_APPROACHING == set()
    for m in ICE.ZERO_APPROACHING:
        assert ed.tolerance_kind(m) == "relative"          # 回测那套会把 IC 均值判成相对容差
        assert ICE.tolerance_kind(m) == "absolute"


def test_qlib_impl_a_is_the_sig_ana_record_path():
    """A 实现的出处**运行时**核，不靠注释。qlib 换版本改了路径，这里必须红。"""
    prov = ICE.qlib_impl_provenance()
    assert prov["is_sig_ana_record_path"] is True
    assert prov["entry"] == "qlib.contrib.eva.alpha.calc_ic"
    assert prov["qlib_version"]


# ------------------------------------------------------------------ 两份实现
def _fixture(days: int = 40, codes: int = 30, seed: int = 7):
    rng = np.random.default_rng(seed)
    idx = [f"2026-01-{d + 1:02d}" for d in range(days)]
    cols = [f"SZ{c:06d}" for c in range(codes)]
    f = pd.DataFrame(rng.normal(size=(days, codes)), index=idx, columns=cols)
    r = pd.DataFrame(rng.normal(size=(days, codes)) * 0.02 + 0.3 * f.to_numpy() * 0.02,
                     index=idx, columns=cols)
    valid = pd.DataFrame(True, index=idx, columns=cols)
    n_uni = pd.Series(float(codes), index=idx)
    return f, r, valid, n_uni


def test_a_and_b_agree_when_no_freedom_is_exercised():
    """厚截面、无缺失、无涨跌停 —— 两份实现**只差 float64 舍入**。

    这条是 A/B 这一对的"零点校准"：它一旦红，说明两份实现在**声明已经写死**的地方
    就分歧了，那样量出来的 ε 是 bug 不是自由度。
    """
    f, r, valid, n_uni = _fixture()
    A = ICE.impl_a_qlib(f, r, valid, n_uni)
    B = ICE.impl_b_pandas(f, r, valid, n_uni)
    for m in ICE.IC_METRICS:
        assert math.isclose(A[m], B[m], rel_tol=1e-12, abs_tol=1e-15), m


def test_b_min_cross_section_is_a_real_degree_of_freedom():
    """薄截面的日子：qlib 照算，B 按门槛丢掉 —— 这就是被量进 ε 的自由度之一。"""
    f, r, valid, n_uni = _fixture()
    thin = valid.index[0]
    valid.loc[thin, valid.columns[3:]] = False                 # 那天只剩 3 个有效格
    A = ICE.impl_a_qlib(f, r, valid, n_uni)
    B = ICE.impl_b_pandas(f, r, valid, n_uni)
    assert A["mean"] != B["mean"]
    # 反向：把门槛降到 1，两份又一致 —— 证明差异确实来自门槛，不是别处
    B1 = ICE.impl_b_pandas(f, r, valid, n_uni, min_cross_section=1)
    assert math.isclose(A["mean"], B1["mean"], rel_tol=1e-12, abs_tol=1e-15)


def test_c_differs_from_b_only_through_the_tradability_reading():
    """C 与 B 是同一份汇总代码，只有"不可交易"的读法不同 —— 掩码相同则必须完全相等。"""
    f, r, valid, n_uni = _fixture()
    same = ICE.impl_c_pandas_limits_tradable(f, r, valid, n_uni)
    base = ICE.impl_b_pandas(f, r, valid, n_uni)
    assert same == base
    relaxed = valid.copy()
    strict = valid.copy()
    strict.iloc[:, :5] = False                                  # 涨跌停格：严格读法剔除
    assert ICE.impl_b_pandas(f, r, strict, n_uni)["mean"] != \
           ICE.impl_c_pandas_limits_tradable(f, r, relaxed, n_uni)["mean"]


def test_empty_valid_gives_nan_not_zero():
    f, r, valid, n_uni = _fixture()
    valid = valid & False
    for out in (ICE.impl_a_qlib(f, r, valid, n_uni), ICE.impl_b_pandas(f, r, valid, n_uni)):
        assert all(math.isnan(out[m]) for m in ICE.IC_METRICS)


# ------------------------------------------------------------------ 带的推导
def _diffs(rel, ab):
    return [{"rel": x, "abs": y} for x, y in zip(rel, ab)]


def test_band_is_p90_times_multiplier():
    rels = [0.0001 * i for i in range(1, 101)]     # 全部在超阈线（5%）以下
    rec = ICE.band_from_diffs("std", _diffs(rels, rels))
    assert rec["status"] == "calibrated"
    assert math.isclose(rec["epsilon"], float(np.quantile(rels, ICE.BAND_QUANTILE)) * ICE.MULTIPLIER)
    assert rec["epsilon"] < rec["epsilon_if_max_rule"]          # 分位规则确实比取最大窄


def test_band_zero_spread_is_not_written_as_zero():
    """E-1：ε=0 是标定失效，不是标定成功。**不许**落成一条比特级相等的断言。"""
    rec = ICE.band_from_diffs("std", _diffs([0.0] * 50, [0.0] * 50))
    assert rec["status"] == "no_implementation_freedom" and rec["epsilon"] is None


def test_band_float_noise_is_rejected_for_absolute_metrics_too():
    """绝对容差分支上也要有噪声地板 —— 两份实现逐位相同却量出 1e-18 的 ε 是最坏的绿。"""
    rec = ICE.band_from_diffs("mean", _diffs([1e-16] * 50, [5e-18] * 50))
    assert rec["status"] == "invalid_below_noise_floor" and rec["epsilon"] is None


def test_band_implausible_gate_is_relative_only():
    """超阈闸只对相对容差开：趋零量的相对差被结构性放大，拿它判「声明没写清」会全军覆没。"""
    rel = ICE.band_from_diffs("std", _diffs([0.5] * 50, [0.5] * 50))
    assert rel["status"] == "implausible_stop_and_report" and rel["epsilon"] is None
    ab = ICE.band_from_diffs("mean", _diffs([0.5] * 50, [1e-3] * 50))
    assert ab["status"] == "calibrated" and math.isclose(ab["epsilon"], 1e-3 * ICE.MULTIPLIER)


def test_pairwise_worst_takes_the_widest_pair():
    row = {"A": {"std": 1.0}, "B": {"std": 1.02}, "C": {"std": 1.05}}
    d = ICE.pairwise_worst(row, "std")
    assert d["pair"] == "A|C" and math.isclose(d["abs"], 0.05)
    assert ICE.pairwise_worst({"A": {"std": 1.0}}, "std") is None      # 一份实现构不成对


def test_pick_factors_is_deterministic():
    """抽样必须确定性 —— 换一次种子换一批样本，带就会跟着抖，而带要进 calibration.json。"""
    d = cfg.SNAPSHOTS_V1 / "gold_factors"
    if not (d / "csi300").is_dir():
        pytest.skip("私有通道 gold 面板不在本机")
    a = ICE.pick_factors(d, "csi300", 20)
    b = ICE.pick_factors(d, "csi300", 20)
    assert a == b and len(a) == 20


# ------------------------------------------------------------------ scorer 取带
def _calib_with_ic_family(eps1: float = 1e-3, eps20: float = 1.0) -> dict:
    def band(e):
        return {"mean": {"status": "calibrated", "epsilon": e, "tolerance_kind": "absolute"},
                "std": {"status": "calibrated", "epsilon": 0.02, "tolerance_kind": "relative"},
                "icir": {"status": "calibrated", "epsilon": 0.4, "tolerance_kind": "absolute"},
                "positive_ratio": {"status": "calibrated", "epsilon": 0.06, "tolerance_kind": "relative"},
                "coverage": {"status": "calibrated", "epsilon": 0.012, "tolerance_kind": "relative"},
                "ci_low": {"status": "no_pair_in_qlib_path", "epsilon": None},
                "ci_high": {"status": "no_pair_in_qlib_path", "epsilon": None}}
    return {"tau": {"value": 0.98},
            "epsilon": {"noise_floor": 1e-13,
                        "by_frequency": {"daily": {"usable": True, "by_metric": {}}},
                        "ic_family": {"by_holding_period": {
                            "1": {"by_metric": band(eps1)},
                            "5": {"by_metric": band(0.5 * (eps1 + eps20))},
                            "20": {"by_metric": band(eps20)}}}}}


def _s4_gold():
    one = {"mean": 0.010, "std": 0.12, "icir": 1.3, "positive_ratio": 0.52,
           "coverage": 0.99, "ci_low": -0.02, "ci_high": 0.04, "ci_method": "block_bootstrap"}
    return {"ic_stats": dict(one),
            "ic_by_horizon": {"1": dict(one), "5": dict(one), "20": dict(one)}}


DECL = {"holding_periods": [1, 5, 20], "tie_handling": "average"}


def test_l3_reads_ic_family_and_settles_s4():
    """**N-117 的正判据**：从前 S4 一格都比不了（`l3_pass=None`），现在比得了。"""
    r = L3.compare_epsilon(_s4_gold(), _s4_gold(), declared=DECL, calib=_calib_with_ic_family())
    assert r.l3_pass is True and r.score == 1.0
    assert r.correctness["n_band_ic_family"] == 20      # 5 指标 ×（ic_stats + 3 个持有期）
    assert r.correctness["n_band_backtest"] == 0
    assert "ic_stats.mean" in r.compared and "ic_by_horizon.20.coverage" in r.compared


def test_l3_ci_stays_uncalibrated_and_is_skipped():
    r = L3.compare_epsilon(_s4_gold(), _s4_gold(), declared=DECL, calib=_calib_with_ic_family())
    assert "ic_stats.ci_low" in r.skipped and "ic_stats.ci_high" in r.skipped
    assert "no_pair_in_qlib_path" in r.skipped["ic_stats.ci_low"]


def test_l3_breach_of_ic_band_fails():
    a = _s4_gold()
    a["ic_stats"]["mean"] = 0.010 + 5e-3                    # 5e-3 ≫ 1e-3 的绝对带
    r = L3.compare_epsilon(a, _s4_gold(), declared=DECL, calib=_calib_with_ic_family())
    assert r.l3_pass is False and r.correctness["band:ic_stats.mean"] == 0.0
    assert 0.0 < r.score < 1.0


def test_l3_ic_stats_uses_the_shortest_declared_holding_period():
    """题面：`ic_stats` 取声明中**最短**的持有期。取错档 = 用一条宽 1000 倍的带判它。"""
    calib = _calib_with_ic_family(eps1=1e-3, eps20=1.0)
    a = _s4_gold()
    a["ic_stats"]["mean"] = 0.010 + 0.5                     # 落在 h=20 的带内、h=1 的带外
    a["ic_by_horizon"]["20"]["mean"] = 0.010 + 0.5          # 这一格按 h=20 的带算应当通过
    r = L3.compare_epsilon(a, _s4_gold(), declared=DECL, calib=calib)
    assert r.correctness["band:ic_stats.mean"] == 0.0
    assert r.correctness["band:ic_by_horizon.20.mean"] == 1.0


def test_l3_without_declared_holding_periods_does_not_guess():
    """声明里没有 holding_periods → `ic_stats` 不猜一个默认档，跳过。"""
    g = {"ic_stats": _s4_gold()["ic_stats"]}
    r = L3.compare_epsilon(g, g, declared={}, calib=_calib_with_ic_family())
    assert r.l3_pass is None and r.compared == []


def test_l3_ic_band_not_applied_outside_ic_roots():
    """`mean` / `std` 是通名 —— 别的 payload 根下的同名叶子**不许**套 IC 的带。"""
    g = {"whatever": {"mean": 0.01, "std": 0.12}}
    r = L3.compare_epsilon(g, g, declared=DECL, calib=_calib_with_ic_family())
    assert r.l3_pass is None and r.compared == []


def test_l3_ic_band_without_tolerance_kind_raises():
    calib = _calib_with_ic_family()
    calib["epsilon"]["ic_family"]["by_holding_period"]["1"]["by_metric"]["mean"].pop("tolerance_kind")
    with pytest.raises(L3.L3Error):
        L3.compare_epsilon(_s4_gold(), _s4_gold(), declared=DECL, calib=calib)


def test_l3_backtest_bands_still_win_and_still_assert_their_kind():
    """回测那条路一个字没变：既有带优先、且仍走 `epsilon_dual.assert_tolerance_kind`。"""
    calib = _calib_with_ic_family()
    calib["epsilon"]["by_frequency"]["daily"]["by_metric"] = {
        "sharpe_net": {"status": "calibrated", "epsilon": 4.39e-3, "tolerance_kind": "relative"}}
    g = {"metrics": {"sharpe_net": 1.0}}
    ok = L3.compare_epsilon({"metrics": {"sharpe_net": 1.001}}, g, declared=DECL, calib=calib)
    assert ok.l3_pass is True and ok.correctness["n_band_backtest"] == 1
    calib["epsilon"]["by_frequency"]["daily"]["by_metric"]["sharpe_net"]["tolerance_kind"] = "absolute"
    with pytest.raises(ValueError):
        L3.compare_epsilon({"metrics": {"sharpe_net": 1.001}}, g, declared=DECL, calib=calib)


# ------------------------------------------------------------------ 合并
def _fake_source() -> dict:
    band = {"tolerance_kind": "absolute", "unit": "IC 点", "status": "calibrated",
            "epsilon": 1e-3, "diff_quantiles": {"p50": 1e-4}, "diff_max": 2e-3,
            "n_samples": 100, "zero_diff_ratio": 0.0}
    blk = {"by_metric": {"mean": band}, "n_samples": 100, "calibrated": ["mean"],
           "implausible": [], "no_freedom": [], "no_pair": ["ci_low", "ci_high"], "usable": True}
    return {"card": "N-117", "method": "dual_independent_implementation_ic",
            "built_at": "2026-09-06T00:00:00+00:00", "code_head": "deadbeef",
            "multiplier": 1.5, "noise_floor": 1e-13, "implausible_threshold": 0.05,
            "band_quantile": 0.9, "band_rule": "…", "tolerance_rule": {}, "declaration": {},
            "implementation_pair": {}, "icir_annualization_ambiguity": {}, "no_ci_calibration": {},
            "inputs": {"n_samples": 100}, "by_holding_period": {"1": blk, "5": blk, "20": blk},
            "calibrated": ["mean"], "implausible": [], "no_freedom": [], "no_pair": [], "usable": True}


def _fake_calib() -> dict:
    return {"schema_version": 1, "card": "2.2",
            "tau": {"value": 0.9841234567890123},
            "epsilon": {"method": "x", "noise_floor": 1e-13,
                        "by_frequency": {"daily": {"usable": True, "by_metric": {}}}},
            "ready_for_scoring": False}


def _write_pair(tmp_path: Path):
    c = tmp_path / "calibration.json"
    s = tmp_path / "ic_epsilon_dual.json"
    c.write_text(json.dumps(_fake_calib(), ensure_ascii=False, indent=2), encoding="utf-8")
    s.write_text(json.dumps(_fake_source(), ensure_ascii=False, indent=2), encoding="utf-8")
    return c, s


def test_merge_adds_only(tmp_path):
    c, s = _write_pair(tmp_path)
    before = c.read_bytes()
    rep = MRG.merge(c, s, log=lambda *a: None)
    assert rep["lines_added"] > 0 and rep["structural_identity_ex_new_key"] is True
    after = json.loads(c.read_text(encoding="utf-8"))
    fam = after["epsilon"].pop(MRG.KEY)
    assert after == json.loads(before)                          # 既有内容逐值不变
    assert fam["by_holding_period"]["1"]["by_metric"]["mean"]["epsilon"] == 1e-3
    assert fam["read_by"] == "scorer.l3.ic_family_band()"
    assert (tmp_path / "calibration.json.pre_n117.bak").read_bytes() == before


def test_merge_check_only_does_not_write(tmp_path):
    c, s = _write_pair(tmp_path)
    before = c.read_bytes()
    MRG.merge(c, s, check_only=True, log=lambda *a: None)
    assert c.read_bytes() == before


def test_merge_refuses_when_an_existing_value_would_change(tmp_path):
    """把守门变异掉必须红 —— 否则"只多不少"就是一句没有防线的话。

    `after` 里**必须带上新键**，否则拦下它的是"新键不存在"那一支，
    量到的就不是"既有值被动过"这道闸了（第一版就是这么写错的）。
    """
    c, s = _write_pair(tmp_path)
    before = c.read_bytes()
    tampered = json.loads(before)
    tampered["epsilon"][MRG.KEY] = {"x": 1}                      # 新键照加
    tampered["tau"]["value"] = 0.99                              # 但顺手动了一个既有值
    after = json.dumps(tampered, ensure_ascii=False, indent=2).encode("utf-8")
    with pytest.raises(SystemExit):
        MRG.verify(before, after)


def test_merge_refuses_when_the_new_key_is_absent(tmp_path):
    c, s = _write_pair(tmp_path)
    before = c.read_bytes()
    with pytest.raises(SystemExit):
        MRG.verify(before, before)


def test_merge_refuses_non_canonical_original(tmp_path):
    c = tmp_path / "calibration.json"
    c.write_text(json.dumps(_fake_calib(), ensure_ascii=False, indent=4), encoding="utf-8")
    obj = json.loads(c.read_bytes())
    obj["epsilon"][MRG.KEY] = {"x": 1}
    after = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
    with pytest.raises(SystemExit):
        MRG.verify(c.read_bytes(), after)


# ------------------------------------------------- 真产物：S4 不再 unsettled
def _real_calib():
    p = cfg.SNAPSHOTS_V1 / "calibration.json"
    if not p.is_file():
        pytest.skip("私有通道 calibration.json 不在本机")
    d = json.loads(p.read_text(encoding="utf-8"))
    if not ((d.get("epsilon") or {}).get("ic_family")):
        pytest.skip("calibration.json 还没合入 ic_family（先跑 ops/merge_ic_epsilon.py）")
    return d


def test_real_s4_gold_self_comparison_is_settled():
    """真 gold 自比：顶必须是 1.0 且 `l3_pass` 不是 None —— 这就是 effect 解封的分母。"""
    calib = _real_calib()
    task = Path("/data/shared/genebench/reference/tasks/v1.0-smoke/s4-cor-01")
    if not (task / "solution" / "artifact.json").is_file():
        pytest.skip("s4-cor-01 的 gold 产物不在本机")
    gold = json.loads((task / "solution" / "artifact.json").read_text(encoding="utf-8"))
    spec = json.loads((task / "taskspec.json").read_text(encoding="utf-8"))
    r = L3.compare("epsilon", stage="S4", agent_artifact=gold, gold_artifact=gold,
                   task=spec, calib=calib)
    assert r.l3_pass is True and r.score == 1.0
    assert r.correctness["n_band_ic_family"] >= 5


def test_real_s4_null_agent_scores_zero_not_none():
    """真 null 桩：底必须算得出来（0.0），否则锚点还是退化，effect 还是扣住。"""
    calib = _real_calib()
    task = Path("/data/shared/genebench/reference/tasks/v1.0-smoke/s4-cor-01")
    if not (task / "solution" / "artifact.null.json").is_file():
        pytest.skip("s4-cor-01 的 null 产物不在本机")
    gold = json.loads((task / "solution" / "artifact.json").read_text(encoding="utf-8"))
    null = json.loads((task / "solution" / "artifact.null.json").read_text(encoding="utf-8"))
    spec = json.loads((task / "taskspec.json").read_text(encoding="utf-8"))
    r = L3.compare("epsilon", stage="S4", agent_artifact=null, gold_artifact=gold,
                   task=spec, calib=calib)
    assert r.score == 0.0 and r.l3_pass is False


def test_merge_twice_is_idempotent_and_still_only_adds(tmp_path):
    """重跑标定后再合一次 —— 基线必须取**备份**，不是"已经带着旧块的当前文件"。

    拿当前文件当基线的话，"只多不少"退化成"和上一次比只多不少"，
    而上一次若挤掉了某个既有值，这件事将永远查不出来。
    """
    c, s = _write_pair(tmp_path)
    pristine = c.read_bytes()
    MRG.merge(c, s, log=lambda *a: None)
    once = c.read_bytes()
    src = json.loads(s.read_text(encoding="utf-8"))
    src["by_holding_period"]["1"]["by_metric"]["mean"]["epsilon"] = 2e-3      # 重标了
    s.write_text(json.dumps(src, ensure_ascii=False, indent=2), encoding="utf-8")
    MRG.merge(c, s, log=lambda *a: None)
    twice = json.loads(c.read_text(encoding="utf-8"))
    assert twice["epsilon"][MRG.KEY]["by_holding_period"]["1"]["by_metric"]["mean"]["epsilon"] == 2e-3
    twice.pop("epsilon")
    base = json.loads(pristine)
    eps_new = json.loads(c.read_text(encoding="utf-8"))["epsilon"]
    eps_new.pop(MRG.KEY)
    assert eps_new == base["epsilon"]                       # ε 节的既有内容一个字没动
    assert (tmp_path / "calibration.json.pre_n117.bak").read_bytes() == pristine
    assert once != c.read_bytes()                           # 确实换成了新带（不是空转）


def test_provider_preflight_names_the_missing_piece(tmp_path):
    """缺件要报出**缺的是哪一件** —— 公开通道当前就缺 `universe/`。"""
    (tmp_path / "tables").mkdir()
    for f in ("daily.parquet", "adj_factor.parquet", "trade_cal.parquet"):
        (tmp_path / "tables" / f).write_bytes(b"")
    (tmp_path / "tradability").mkdir()
    with pytest.raises(SystemExit) as e:
        ICE.Inputs.preflight(tmp_path)
    assert "universe/universe_pit.parquet" in str(e.value)
    (tmp_path / "universe").mkdir()
    (tmp_path / "universe" / "universe_pit.parquet").write_bytes(b"")
    ICE.Inputs.preflight(tmp_path)                      # 齐了就不该抛


def test_public_channel_snapshot_has_the_universe_it_used_to_lack():
    """卡 1.2 在这里留了一条**会自己失效**的哨兵：「公开通道还缺 universe/」。

    卡 1.1-b 把它建起来了（`ops/run_public_chain.py --step universe` 从私有
    `universe_pit.parquet` 复制一份到公开快照根下 —— 宇宙轴按 N-68 沿用 v1，
    「谁在指数里」是定义不是行情），于是哨兵按设计变红。这里把它**翻成正向断言**：
    公开快照根下的 `universe_pit.parquet` 必须在，且 `Inputs.preflight` 必须过 ——
    删掉它、或者哪天公开链换了落点，这条照样会红。
    """
    pub = cfg.SNAPSHOTS / cfg.PUBLIC_VERSION
    if not pub.is_dir():
        pytest.skip("本机没有公开通道快照")
    up = pub / "universe" / "universe_pit.parquet"
    assert up.is_file(), (
        f"公开通道缺 {up} —— 先跑 ops/run_public_chain.py --step universe")
    for need in ("tables", "tradability"):
        if not (pub / need).is_dir():
            pytest.skip(f"公开通道的 {need}/ 还没建（数据面是卡 1.1-a）")
    ICE.Inputs.preflight(pub)               # 缺件会 SystemExit，这里就是要它不抛
