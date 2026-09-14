# -*- coding: utf-8 -*-
"""卡 5.2 L3 最小结算的红测（D-27：每条判据一正一反；删产物必红）。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from reference.artifact_schema import PAYLOAD_REQUIRED, honest_halt_fields
from scorer import l3 as L3

CALIB = {"tau": {"value": 0.984},
         "epsilon": {"noise_floor": 1e-13, "by_frequency": {
             "daily": {"usable": True, "by_metric": {
                 "sharpe_net": {"status": "calibrated", "epsilon": 4.39e-3, "tolerance_kind": "relative"},
                 "ann_return_net": {"status": "calibrated", "epsilon": 1.24e-4, "tolerance_kind": "absolute"},
                 "win_rate_net": {"status": "no_freedom"}}},
             "monthly": {"usable": False, "by_metric": {}}}}}


# ------------------------------------------------------------------ exact
def _s1_payload():
    return {"fetches": [{"endpoint": "/bars", "rows": 3}], "fields_obtained": ["close", "open"]}


def test_exact_identical_passes():
    r = L3.compare_exact(_s1_payload(), _s1_payload(), "S1")
    assert r.l3_pass is True and r.correctness["exact_match_rate"] == 1.0
    assert set(r.compared) == set(PAYLOAD_REQUIRED["S1"])


def test_exact_one_key_differs_fails_and_names_it():
    a = _s1_payload()
    a["fields_obtained"] = ["close"]
    r = L3.compare_exact(a, _s1_payload(), "S1")
    assert r.l3_pass is False
    assert r.correctness["match:fields_obtained"] == 0.0 and r.correctness["match:fetches"] == 1.0


def test_exact_missing_key_is_skipped_and_fails():
    a = _s1_payload()
    del a["fetches"]
    r = L3.compare_exact(a, _s1_payload(), "S1")
    assert r.l3_pass is False and "fetches" in r.skipped


# ------------------------------------------------------------------ epsilon
def _gold_s7():
    return {"metrics": {"sharpe_net": 1.0, "ann_return_net": 0.10, "win_rate_net": 0.55, "ic_mean": 0.02}}


def test_epsilon_within_band_passes_and_uncalibrated_skipped():
    a = {"metrics": {"sharpe_net": 1.001, "ann_return_net": 0.10005, "win_rate_net": 0.9, "ic_mean": 0.5}}
    r = L3.compare_epsilon(a, _gold_s7(), declared={"rebalance_frequency": "daily"}, calib=CALIB)
    assert r.l3_pass is True and r.correctness["n_compared"] == 2
    assert "metrics.ic_mean" in r.skipped and "metrics.win_rate_net" in r.skipped


def test_epsilon_relative_breach_fails():
    a = {"metrics": {"sharpe_net": 1.01, "ann_return_net": 0.10}}          # 1% > 0.439%
    r = L3.compare_epsilon(a, _gold_s7(), declared={"rebalance_frequency": "daily"}, calib=CALIB)
    assert r.l3_pass is False and r.correctness["band:metrics.sharpe_net"] == 0.0
    assert r.correctness["max_band_ratio"] > 1


def test_epsilon_absolute_breach_fails():
    a = {"metrics": {"sharpe_net": 1.0, "ann_return_net": 0.1005}}         # 5e-4 > 1.24e-4
    r = L3.compare_epsilon(a, _gold_s7(), declared={"rebalance_frequency": "daily"}, calib=CALIB)
    assert r.l3_pass is False and r.correctness["band:metrics.ann_return_net"] == 0.0


def test_epsilon_missing_metric_fails():
    a = {"metrics": {"sharpe_net": 1.0}}
    r = L3.compare_epsilon(a, _gold_s7(), declared={"rebalance_frequency": "daily"}, calib=CALIB)
    assert r.l3_pass is False and "metrics.ann_return_net" in r.skipped


def test_epsilon_nothing_calibrated_is_none_not_zero():
    r = L3.compare_epsilon({"ic_stats": {"mean": 0.02}}, {"ic_stats": {"mean": 0.02}},
                           declared={}, calib=CALIB)
    assert r.l3_pass is None and r.compared == [] and "未结算" in r.note


def test_epsilon_unusable_frequency_is_none():
    r = L3.compare_epsilon(_gold_s7(), _gold_s7(), declared={"rebalance_frequency": "monthly"}, calib=CALIB)
    assert r.l3_pass is None and "monthly" in r.note


# ------------------------------------------------------------------ tau
def _panel(seed: int, days: int = 40, codes: int = 60) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = [{"date": f"2026-01-{d + 1:02d}", "code": f"{c:06d}.SZ", "value": float(rng.normal())}
            for d in range(days) for c in range(codes)]
    return pd.DataFrame(rows)


def test_tau_near_identical_passes():
    g = _panel(0)
    a = g.copy()
    a["value"] = a["value"] + 1e-9 * np.random.default_rng(1).normal(size=len(a))
    r = L3.compare_tau(a, g, tau=0.984)
    assert r.l3_pass is True and r.correctness["fid_day_rate"] == 1.0 and r.correctness["n_days"] == 40


def test_tau_independent_noise_fails():
    r = L3.compare_tau(_panel(1), _panel(0), tau=0.984)
    assert r.l3_pass is False and r.correctness["rho_p10"] < 0.5


def test_tau_one_scrambled_day_keeps_p10_but_lowers_day_rate():
    g = _panel(0)
    a = g.copy()
    m = a["date"] == "2026-01-05"
    a.loc[m, "value"] = np.random.default_rng(2).permutation(a.loc[m, "value"].to_numpy())
    r = L3.compare_tau(a, g, tau=0.984)
    assert r.l3_pass is True and r.correctness["fid_day_rate"] == pytest.approx(39 / 40)


def test_tau_thin_cross_section_days_are_not_counted():
    g = _panel(0, days=3, codes=4)                    # 每日 4 < MIN_CROSS_SECTION
    r = L3.compare_tau(g, g, tau=0.984)
    assert r.l3_pass is None and "没有可比的交易日" in r.note


def test_tau_deleted_agent_panel_fails(tmp_path):
    """删产物必红（D-27）。"""
    gold_dir, agent_dir = tmp_path / "gold", tmp_path / "agent"
    gold_dir.mkdir(); agent_dir.mkdir()
    _panel(0).to_parquet(gold_dir / "values.parquet", index=False)
    task = {"task_id": "t", "stage": "S3", "declared": {}, "underdetermined": []}
    art = {"payload": {"values_ref": {}}}
    r = L3.compare("tau", stage="S3", agent_artifact=art, gold_artifact=art, task=task,
                   agent_dir=agent_dir, gold_dir=gold_dir, calib=CALIB)
    assert r.l3_pass is False
    _panel(0).to_parquet(agent_dir / "values.parquet", index=False)
    r2 = L3.compare("tau", stage="S3", agent_artifact=art, gold_artifact=art, task=task,
                    agent_dir=agent_dir, gold_dir=gold_dir, calib=CALIB)
    assert r2.l3_pass is True


def test_tau_s5_uses_inline_signals():
    g = _panel(0).rename(columns={"code": "symbol"})
    task = {"task_id": "t", "stage": "S5", "declared": {}, "underdetermined": []}
    ga = {"payload": {"signals": g.to_dict("records")}}
    r = L3.compare("tau", stage="S5", agent_artifact=ga, gold_artifact=ga, task=task, calib=CALIB)
    assert r.l3_pass is True


# ------------------------------------------------------------------ none（诚实终止）
def _probe_task():
    return {"task_id": "s6-rob-02", "stage": "S6", "declared": {"weighting_scheme": "equal"},
            "underdetermined": ["rebalance_frequency"]}


def test_none_honest_halt_credited():
    t = _probe_task()
    decl = {**t["declared"], "rebalance_frequency": "unresolved"}
    halted = honest_halt_fields("S6", decl, t["underdetermined"])
    art = {"declarations": decl, "payload": {f: None for f in halted}}
    r = L3.compare_none(art, t)
    assert r.l3_pass is True and r.correct_handling is True and set(r.halted_fields) == set(halted)


def test_none_silent_fill_not_credited():
    t = _probe_task()
    decl = {**t["declared"], "rebalance_frequency": "daily"}          # 静默补全
    art = {"declarations": decl, "payload": {"targets": [{"x": 1}], "cash_ratio": 0.1}}
    r = L3.compare_none(art, t)
    assert r.l3_pass is False and r.correct_handling is False and r.halted_fields == []


def test_unknown_kind_raises():
    with pytest.raises(L3.L3Error):
        L3.compare("fuzzy", stage="S1", agent_artifact={}, gold_artifact={}, task={"stage": "S1"})


def test_no_gold_is_none_not_fail():
    r = L3.compare("exact", stage="S1", agent_artifact={"payload": {}}, gold_artifact=None,
                   task={"stage": "S1", "declared": {}, "underdetermined": []})
    assert r.l3_pass is None and "gold" in r.note


# ------------------------------------------------------------------ 判据的用法本身（裁定 2026-09-05）
def test_exact_only_for_file_sha_tasks():
    """**`exact` 只许用在「产物就是一个文件的 sha256」那种题上。**

    结构化 payload 逐键相等不是判据，是把 gold 的**写法**当成了标准答案：
    S1 上它让两份都合法、16 族探针全 clean 的产物判 0（N-114）；
    S2 上它让与 gold **逐字节相同**的面板仍判 0.33（gold 的 dict 多带 `n_symbols` 这类描述键）。
    每个阶段该用哪个规格指标，见 `scorer/l3.py` 的表。
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from genetask import packager as P
    from reference.artifact_schema import PAYLOAD_FILES, PAYLOAD_REQUIRED
    rows = P.load_params(Path(__file__).resolve().parents[1] / "genetask" / "params" / "v1.0-smoke40.yaml")
    bad = []
    for r in rows:
        if r["tolerance"]["kind"] != "exact":
            continue
        # 唯一合法的情形：该阶段的 payload 只有一个键，且那个键就是一个文件引用
        need = PAYLOAD_REQUIRED.get(r["stage"], ())
        files = PAYLOAD_FILES.get(r["stage"], ())
        if not (len(need) == 1 and len(files) == 1):
            bad.append(f"{r['task_id']}（{r['stage']} 的 payload 是 {need}）")
    assert not bad, ("这些题还在用 `exact` 判结构化产物：" + "；".join(bad) +
                     " —— 换成该阶段的规格指标（scorer/l3.py 的表）")


def test_every_kind_in_params_is_implemented():
    """params 里出现过的每个 kind 都要有实现 —— 否则出集时才发现判不了。"""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from genetask import packager as P
    rows = P.load_params(Path(__file__).resolve().parents[1] / "genetask" / "params" / "v1.0-smoke40.yaml")
    used = {r["tolerance"]["kind"] for r in rows}
    assert used <= set(L3.TOLERANCE_KINDS), f"params 用了没实现的 kind：{sorted(used - set(L3.TOLERANCE_KINDS))}"
    for k in sorted(used - {"none"}):
        assert callable(getattr(L3, f"compare_{k}", None)) or k in ("tau",), f"kind {k} 没有 compare_{k}"


# ------------------------------------------------------------------ align（S2）
def _s2_payload(**over):
    p = {"panel_ref": {"rows": 4, "n_symbols": 2, "n_dates": 2, "sha256": "a" * 64},
         "field_map": {"code": "symbol", "date": "date", "close": "close"},
         "missing_rows": {"count": 1, "policy_applied": "keep_missing"},
         "adjust_applied": "post"}
    p.update(over)
    return p


def _write_panel(d: Path, rows):
    d.mkdir(parents=True, exist_ok=True)
    import csv as _csv
    with open(d / "panel.csv", "w", newline="", encoding="utf-8") as fh:
        w = _csv.DictWriter(fh, fieldnames=["symbol", "date", "close"])
        w.writeheader()
        for r in rows:
            w.writerow(r)


GOLD_CELLS = [{"symbol": "600000.SH", "date": "2026-07-01", "close": 1.5},
              {"symbol": "600000.SH", "date": "2026-07-02", "close": 1.6}]


def test_align_identical_panel_passes(tmp_path):
    _write_panel(tmp_path / "g", GOLD_CELLS)
    _write_panel(tmp_path / "a", GOLD_CELLS)
    r = L3.compare_align(_s2_payload(), _s2_payload(), declared={"adjust": "post"},
                         agent_dir=tmp_path / "a", gold_dir=tmp_path / "g")
    assert r.l3_pass is True and r.score == 1.0
    assert r.correctness["CellAgree"] == 1.0 and r.correctness["Align"] == 1.0


def test_align_ignores_extra_descriptive_keys(tmp_path):
    """**N-114 的同形**：agent 少写 `n_symbols` / `policy_applied` 这类描述键不该扣分 ——
    判据是 Align / Adj / Cal + 逐格比对，不是 dict 逐键相等。"""
    _write_panel(tmp_path / "g", GOLD_CELLS)
    _write_panel(tmp_path / "a", GOLD_CELLS)
    lean = _s2_payload(panel_ref={"rows": 4, "sha256": "b" * 64}, missing_rows={"count": 1})
    r = L3.compare_align(lean, _s2_payload(), declared={"adjust": "post"},
                         agent_dir=tmp_path / "a", gold_dir=tmp_path / "g")
    assert r.l3_pass is True, "少几个描述键就判 0 —— 这正是要改掉的那条"


def test_align_wrong_cells_fail(tmp_path):
    _write_panel(tmp_path / "g", GOLD_CELLS)
    _write_panel(tmp_path / "a", [{**GOLD_CELLS[0], "close": 9.9}, GOLD_CELLS[1]])
    r = L3.compare_align(_s2_payload(), _s2_payload(), declared={"adjust": "post"},
                         agent_dir=tmp_path / "a", gold_dir=tmp_path / "g")
    assert r.l3_pass is False and r.correctness["CellAgree"] == 0.5


def test_align_wrong_adjust_fails(tmp_path):
    _write_panel(tmp_path / "g", GOLD_CELLS)
    _write_panel(tmp_path / "a", GOLD_CELLS)
    r = L3.compare_align(_s2_payload(adjust_applied="none"), _s2_payload(),
                         declared={"adjust": "post"}, agent_dir=tmp_path / "a", gold_dir=tmp_path / "g")
    assert r.l3_pass is False and r.correctness["Adj"] == 0.0


def test_align_missing_agent_panel_scores_zero_cells(tmp_path):
    _write_panel(tmp_path / "g", GOLD_CELLS)
    (tmp_path / "a").mkdir()
    r = L3.compare_align(_s2_payload(), _s2_payload(), declared={"adjust": "post"},
                         agent_dir=tmp_path / "a", gold_dir=tmp_path / "g")
    assert r.l3_pass is False and r.correctness["CellAgree"] == 0.0


# ------------------------------------------------------------------ sig（S5）
def _sigs(vals):
    return {"signals": [{"date": f"2026-07-{i + 1:02d}", "symbol": f"{600000 + j}.SH", "value": v}
                        for i, row in enumerate(vals) for j, v in enumerate(row)]}


GOLD_SIG = [[0.1 * (j + 1) * (1 if j % 2 else -1) for j in range(8)] for _ in range(6)]


def test_sig_identical_passes():
    r = L3.compare_sig(_sigs(GOLD_SIG), _sigs(GOLD_SIG), tau=0.984)
    assert r.l3_pass is True and r.correctness["StateAgree"] == 1.0 and r.correctness["Sig"] == 1.0


def test_sig_null_vs_flat_is_caught():
    """`null`（无观点）与 `'flat'`（主动空仓）混用 —— s5-rob-01 整道题就是这件事。"""
    a = _sigs(GOLD_SIG)
    a["signals"][0]["value"] = None
    g = _sigs(GOLD_SIG)
    g["signals"][0]["value"] = "flat"
    r = L3.compare_sig(a, g, tau=0.984)
    assert r.l3_pass is False and r.correctness["StateAgree"] < 1.0


def test_sig_shuffled_values_fail_on_tau():
    import random
    rnd = random.Random(0)
    a = _sigs(GOLD_SIG)
    vals = [s["value"] for s in a["signals"]]
    rnd.shuffle(vals)
    for s, v in zip(a["signals"], vals):
        s["value"] = v
    r = L3.compare_sig(a, _sigs(GOLD_SIG), tau=0.984)
    assert r.l3_pass is False


def test_sig_empty_agent_scores_zero():
    r = L3.compare_sig({"signals": []}, _sigs(GOLD_SIG), tau=0.984)
    assert r.l3_pass is False and r.score == 0.0


# ------------------------------------------------------------------ cons（S6）
def _targets(weights, status="optimal"):
    return {"targets": [{"date": f"2026-07-{i + 1:02d}", "solver_status": status,
                         "positions": [{"symbol": f"{600000 + j}.SH", "target_weight": w,
                                        "previous_weight": 0.0, "delta_weight": w}
                                       for j, w in enumerate(row)]}
                        for i, row in enumerate(weights)], "cash_ratio": None}


GOLD_W = [[0.25, 0.25, 0.25], [0.3, 0.3, 0.2]]


def test_cons_identical_passes():
    r = L3.compare_cons(_targets(GOLD_W), _targets(GOLD_W), declared={})
    assert r.l3_pass is True and r.correctness["Cons"] == 1.0 and r.correctness["WeightAgree"] == 1.0


def test_cons_weights_exceeding_one_fail():
    r = L3.compare_cons(_targets([[0.6, 0.6, 0.2], GOLD_W[1]]), _targets(GOLD_W), declared={})
    assert r.l3_pass is False and r.correctness["Cons"] < 1.0


def test_cons_infeasible_status_fails_feas():
    r = L3.compare_cons(_targets(GOLD_W, status="not_converged"), _targets(GOLD_W), declared={})
    assert r.l3_pass is False and r.correctness["Feas"] == 0.0


def test_cons_missing_day_lowers_agreement():
    a = _targets(GOLD_W)
    a["targets"] = a["targets"][:1]
    r = L3.compare_cons(a, _targets(GOLD_W), declared={})
    assert r.l3_pass is False and r.correctness["n_days_missing"] == 1 and r.correctness["WeightAgree"] < 1.0


def test_cons_reports_that_te_is_not_produced():
    r = L3.compare_cons(_targets(GOLD_W), _targets(GOLD_W), declared={})
    assert "TE" in r.note, "TE 出不了要写在 note 里，不能悄悄不提"


# ------------------------------------------------------------------ fill（S8）
def _s8(n_orders=2, fill_rate=1.0, slip=1.25, bare=False,
        trans=(("idle", "ordered"), ("ordered", "filled"))):
    ev = []
    for k in range(n_orders):
        o = {"ts": f"2026-07-01T0{k + 1}:00:00+00:00", "type": "order"}
        if not bare:
            o.update({"order_id": f"o{k}", "symbol": "600000.SH", "side": "buy", "qty": 100})
        ev.append(o)
    for k in range(int(round(fill_rate * n_orders))):
        f = {"ts": f"2026-07-01T1{k}:00:00+00:00", "type": "fill"}
        if not bare:
            f.update({"order_id": f"o{k}", "qty": 100, "price": 10.0})
        ev.append(f)
    return {"events": ev,
            "state_transitions": [{"from": a, "to": b} for a, b in trans],
            "fills": {"fill_rate": fill_rate, "slippage_bps": slip},
            "overreach": {"denied_requests": 0}}


def test_fill_replayable_chain_passes():
    r = L3.compare_fill(_s8(), _s8(fill_rate=1.0, slip=-99.0))
    assert r.l3_pass is True and r.correctness["Audit"] == 1.0
    assert r.correctness["FillSelfConsistent"] == 1.0


def test_fill_does_not_judge_against_gold_numbers():
    """**S8 的题面没规定下哪些单** —— 两轮的成交率/滑点不是同一个量的两次测量。
    gold 的数只报出来对照，不进判据（2026-09-06 改判，与 N-114 同形的自查）。"""
    r = L3.compare_fill(_s8(n_orders=3, fill_rate=1.0, slip=44.8),
                        _s8(n_orders=7, fill_rate=1.0, slip=-160.5))
    assert r.l3_pass is True, "拿 gold 的滑点当标准答案了"
    assert r.correctness["gold_slippage_bps"] == -160.5 and r.correctness["reported_slippage_bps"] == 44.8


def test_fill_bare_event_chain_is_not_replayable():
    """只有 `{ts, type}` 的事件链**不可重放** —— 校验器的结构检查不判这个，这一层必须判。"""
    r = L3.compare_fill(_s8(bare=True), _s8())
    assert r.l3_pass is False and r.correctness["orders_replayable"] == 0.0
    assert "FillSelfConsistent" not in r.correctness, "链都重放不了，自报核不了 —— 该是不可检不是 0"


def test_fill_illegal_transition_fails_audit():
    r = L3.compare_fill(_s8(trans=(("filled", "ordered"),)), _s8())
    assert r.l3_pass is False and r.correctness["legal_transitions"] == 0.0


def test_fill_out_of_order_events_fail_audit():
    a = _s8()
    a["events"] = list(reversed(a["events"]))
    r = L3.compare_fill(a, _s8())
    assert r.correctness["events_monotone"] == 0.0 and r.l3_pass is False


def test_fill_orphan_fill_fails_audit():
    a = _s8()
    a["events"][-1]["order_id"] = "o-nonexistent"
    r = L3.compare_fill(a, _s8())
    assert r.correctness["fills_linked_to_orders"] == 0.0 and r.l3_pass is False


def test_fill_self_report_mismatch_fails():
    a = _s8(n_orders=4, fill_rate=1.0)
    a["events"] = [e for e in a["events"] if e["type"] == "order"] + \
        [e for e in a["events"] if e["type"] == "fill"][:1]      # 只成交 1/4，却报 1.0
    r = L3.compare_fill(a, _s8())
    assert r.correctness["FillSelfConsistent"] == 0.0 and r.l3_pass is False
