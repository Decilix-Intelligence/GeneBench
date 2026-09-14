"""卡 5.1 红队回归夹具（2026-09-07）：六视角逐条负例，**原样入库**。

每一条都对应一次实跑（跑板 `scratch/5.1/redteam_probe.py`，实际输出写进
`ops/reports/rescore_5_1.md` 的「红队发现」表）。命名规则：`test_rt51_<视角><序号>_<形态>`。

视角与协议 `ops/specs/redteam_protocol.md` §1 的六个一一对应：

* ① 边界值（空产物 / 单行 / 恰好在容差上）
* ② 三态混淆（None vs [] vs 0；缺失 vs 标记）
* ③ 自报 vs 行为（§2.1：切片键 / 基准来自被判者）
* ④ 类型与序列化（§2.2：Python 相等 ≠ JSON 相等；JSON 里没有 inf/nan）
* ⑤ 聚合口径（分子分母、锚点退化、未结算不进两侧）
* ⑥ 版本与切片（四条版本轴混进同一张表）

**突变落在门保护的对象上**（协议 §7）：每条负例改的都是「被判的那份产物 / 那批记录」，
不是判定器的参数 —— 改判据的阈值只测得到参数传递。
"""
from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from reference.artifact_schema import validate_scorer_output
from scorer import l3 as L3
from scorer import report as R
from scorer import score_run as SR

TASKS = Path("/data/shared/genebench/reference/tasks/v1.0-smoke")


# ============================================================ ① 边界值
def _panel_dirs(tmp: Path, gold_df: pd.DataFrame, agent_df: pd.DataFrame) -> tuple[Path, Path]:
    (tmp / "agent").mkdir(parents=True, exist_ok=True)
    (tmp / "task" / "gold").mkdir(parents=True, exist_ok=True)
    gold_df.to_csv(tmp / "task" / "gold" / "panel.csv", index=False)
    agent_df.to_csv(tmp / "agent" / "panel.csv", index=False)
    return tmp / "agent", tmp / "task" / "work"          # gold_dir 按生产口径传 work/


_FLAT_PAYLOAD = {"field_map": {}, "adjust_applied": "post", "missing_rows": {"count": 0}}


def test_rt51_a1_align_subset_of_rows_is_not_full_marks():
    """S2 只交 1/200 行 —— 旧口径 CellAgree=1.0 / score=1.0 / l3_pass=True（内连接当分母）。"""
    tmp = Path(tempfile.mkdtemp())
    gold = pd.DataFrame({"symbol": [f"{i:06d}.SZ" for i in range(200)],
                         "date": ["2026-07-01"] * 200, "close": [float(i) for i in range(200)]})
    adir, gdir = _panel_dirs(tmp, gold, gold.head(1))
    r = L3.compare_align(dict(_FLAT_PAYLOAD), dict(_FLAT_PAYLOAD), declared={"adjust": "post"},
                         agent_dir=adir, gold_dir=gdir)
    assert r.correctness["CellAgree"] == pytest.approx(1 / 200)
    assert r.correctness["n_gold_rows"] == 200 and r.correctness["n_rows_missing"] == 199
    assert r.l3_pass is False


def test_rt51_a1b_align_full_panel_still_full_marks():
    """判别力自检：逐格相同的面板照样 1.0 —— 修的是分母，不是把所有人一起判低。"""
    tmp = Path(tempfile.mkdtemp())
    gold = pd.DataFrame({"symbol": ["A", "B", "C"], "date": ["2026-07-01"] * 3,
                         "close": [1.0, 2.0, 3.0]})
    adir, gdir = _panel_dirs(tmp, gold, gold.copy())
    r = L3.compare_align(dict(_FLAT_PAYLOAD), dict(_FLAT_PAYLOAD), declared={"adjust": "post"},
                         agent_dir=adir, gold_dir=gdir)
    assert r.correctness["CellAgree"] == 1.0 and r.correctness["n_rows_missing"] == 0


def test_rt51_a1c_align_missing_row_not_excused_by_gold_nan():
    """gold 那格是 NaN、agent 整行没交 —— 左连接下两边都是 NaN，不许判成「对上了」。"""
    tmp = Path(tempfile.mkdtemp())
    gold = pd.DataFrame({"symbol": ["A", "B"], "date": ["2026-07-01"] * 2,
                         "close": [float("nan"), 2.0]})
    adir, gdir = _panel_dirs(tmp, gold, gold.tail(1))       # 只交 B 那一行
    r = L3.compare_align(dict(_FLAT_PAYLOAD), dict(_FLAT_PAYLOAD), declared={"adjust": "post"},
                         agent_dir=adir, gold_dir=gdir)
    assert r.correctness["CellAgree"] == pytest.approx(0.5)


def test_rt51_a2_tau_one_day_of_twenty_is_not_full_marks():
    """S3/S5 只交 1/20 天 —— 旧口径 fid_day_rate=1.0（分母是共同天数）。"""
    days = [f"2026-06-{i:02d}" for i in range(1, 21)]
    g = pd.DataFrame([{"date": d, "code": f"{i:06d}.SZ", "value": float(i)}
                      for d in days for i in range(10)])
    a = g[g["date"] == days[0]].copy()
    r = L3.compare_tau(a, g, tau=0.98)
    assert r.correctness["n_gold_days"] == 20 and r.correctness["n_days"] == 1
    assert r.correctness["fid_day_rate"] == pytest.approx(1 / 20)
    assert r.l3_pass is False


def test_rt51_a2b_tau_full_coverage_still_passes():
    """判别力自检：全交且逐日相同仍是 1.0 / True。"""
    days = [f"2026-06-{i:02d}" for i in range(1, 6)]
    g = pd.DataFrame([{"date": d, "code": f"{i:06d}.SZ", "value": float(i)}
                      for d in days for i in range(10)])
    r = L3.compare_tau(g.copy(), g, tau=0.98)
    assert r.correctness["fid_day_rate"] == 1.0 and r.l3_pass is True
    assert r.correctness["day_coverage"] == 1.0


def test_rt51_c3_align_duplicate_rows_do_not_dilute():
    """把对的行复制 20 遍稀释错行 —— 旧口径 0.952（正确口径 0.5）。重复格整格作废。"""
    tmp = Path(tempfile.mkdtemp())
    gold = pd.DataFrame({"symbol": ["A", "B"], "date": ["2026-07-01"] * 2, "close": [1.0, 2.0]})
    ag = pd.DataFrame({"symbol": ["A"] * 20 + ["B"], "date": ["2026-07-01"] * 21,
                       "close": [1.0] * 20 + [999.0]})
    adir, gdir = _panel_dirs(tmp, gold, ag)
    r = L3.compare_align(dict(_FLAT_PAYLOAD), dict(_FLAT_PAYLOAD), declared={"adjust": "post"},
                         agent_dir=adir, gold_dir=gdir)
    assert r.correctness["CellAgree"] == pytest.approx(0.0)      # A 重复作废、B 值错
    assert r.correctness["n_agent_dup_rows"] == 20


# ============================================================ ② 三态混淆
def test_rt51_b1_fill_null_replay_fields_are_not_replayable():
    """S8：四个键都写上、值全 null —— 旧口径 orders_replayable=1.0。"""
    ev = [{"ts": "2026-07-01T09:30:00Z", "type": "order", "order_id": None, "symbol": None,
           "side": None, "qty": None},
          {"ts": "2026-07-01T09:31:00Z", "type": "fill", "order_id": None}]
    r = L3.compare_fill({"events": ev, "state_transitions": [{"from": "new", "to": "filled"}],
                         "fills": {"fill_rate": 1.0}}, {})
    assert r.correctness["orders_replayable"] == 0.0
    assert r.correctness["fills_linked_to_orders"] == 0.0        # null 委托号对不上任何委托
    assert r.correctness["Audit"] == 0.0


def test_rt51_b1b_fill_real_chain_still_replayable():
    """判别力自检：字段有值的链照样 orders_replayable=1.0。"""
    ev = [{"ts": "2026-07-01T09:30:00Z", "type": "order", "order_id": "o1", "symbol": "A",
           "side": "buy", "qty": 100},
          {"ts": "2026-07-01T09:31:00Z", "type": "fill", "order_id": "o1"}]
    r = L3.compare_fill({"events": ev, "state_transitions": [], "fills": {}}, {})
    # state_transitions 为空 → 走「无从重放」那条早退；单独核 _replayable
    assert L3._replayable(ev[0]) is True
    assert L3._replayable({"order_id": "o1", "symbol": "A", "side": "buy", "qty": True}) is False


def test_rt51_b2_honest_halt_needs_the_key_present_not_absent():
    """S7 探针题：payload 整个空对象 —— 旧口径 `payload.get(f) is None` 判成「已置 null」。"""
    task = {"stage": "S7", "underdetermined": ["cost_model"]}
    absent = L3.compare_none({"declarations": {"cost_model": "unresolved"}, "payload": {}}, task)
    assert absent.correct_handling is False
    assert absent.correctness["n_dependents_missing"] == absent.correctness["n_dependents"] > 0
    # 判别力自检：把依赖字段显式写成 null 就是诚实终止
    halted = L3.honest_halt_fields("S7", {"cost_model": "unresolved"}, ["cost_model"])
    present = L3.compare_none({"declarations": {"cost_model": "unresolved"},
                               "payload": {f: None for f in halted}}, task)
    assert present.correct_handling is True


# ============================================================ ③ 自报 vs 行为
def test_rt51_c1_pit_baseline_never_falls_back_to_self_report():
    """题面没有 as_of 时 PIT 的基准曾回退到 artifact 自报的 as_of（协议 §2.1）。"""
    art = {"as_of": "2026-09-01", "payload": {"fields_obtained": ["close"], "fetches": []}}
    gold = {"payload": {"fields_obtained": ["close"]}}
    log = [{"path": "/bars", "as_of": "2026-09-01", "decision": "allow"}] * 4
    r = L3.compare("cov", stage="S1", agent_artifact=art, gold_artifact=gold, task={},
                   gateway_log=log, as_of=None)
    assert "PIT" not in r.correctness and "PIT" in r.skipped
    # 判别力自检：任务侧给了 as_of 就照常判，且判的是**任务侧**那个值
    r2 = L3.compare("cov", stage="S1", agent_artifact=art, gold_artifact=gold, task={},
                    gateway_log=log, as_of="2026-07-31")
    assert r2.correctness["PIT"] == 0.0


def test_rt51_c2_duplicate_symbol_cannot_hide_leverage():
    """S6：同一 symbol 两行各 0.9（真实敞口 1.8）—— 旧口径去重后只看到 0.9，Cons=1.0。"""
    gday = {"date": "d", "positions": [{"symbol": "A", "target_weight": 0.5},
                                       {"symbol": "B", "target_weight": 0.5}],
            "solver_status": "optimal"}
    aday = {"date": "d", "positions": [{"symbol": "A", "target_weight": 0.9},
                                       {"symbol": "A", "target_weight": 0.9}],
            "solver_status": "optimal"}
    r = L3.compare_cons({"targets": [aday]}, {"targets": [gday]},
                        declared={"constraint_set": "long_only"})
    assert r.correctness["Cons"] == 0.0
    assert r.correctness["n_dup_positions"] == 1


def test_rt51_c2b_position_weight_must_be_a_json_number():
    """`"0.9"` / `true` / 缺键都不是权重 —— 旧口径 `float(v or 0.0)` 把它们读成 0.9 / 1 / 0。"""
    w, dup, bad = L3._positions({"positions": [{"symbol": "A", "target_weight": "0.9"},
                                               {"symbol": "B", "target_weight": True},
                                               {"symbol": "C"},
                                               {"symbol": "D", "target_weight": 0.4}]})
    assert w == {"D": 0.4} and dup == 0 and bad == 3


# ============================================================ ④ 类型与序列化
def test_rt51_b3_json_true_is_not_a_signal_value():
    """S5：每一格都写 JSON `true` —— 旧口径 StateAgree=1.0、无 ρ 可算、l3_pass=True（满分）。"""
    gp = {"signals": [{"date": "2026-07-01", "symbol": f"{i:06d}.SZ", "value": float(i) - 3}
                      for i in range(6)]}
    ap = {"signals": [{"date": "2026-07-01", "symbol": f"{i:06d}.SZ", "value": True}
                      for i in range(6)]}
    r = L3.compare_sig(ap, gp, tau=0.98)
    assert r.correctness["StateAgree"] == 0.0
    assert r.l3_pass is False
    assert L3._cell_state(True) == "other" and L3._cell_state(1) == "value"
    assert L3._cell_state({"v": 1}) == "other" and L3._cell_state([1]) == "other"


def test_rt51_b3b_signal_duplicate_cell_is_voided():
    """同一 (date, symbol) 两行、一行 null 一行有值 —— 判定不许取决于读到哪一行（协议 §3）。"""
    cells, dup = L3._signal_cells([{"date": "d", "symbol": "A", "value": None},
                                   {"date": "d", "symbol": "A", "value": 1.0}])
    assert cells == {} and dup == 1


def test_rt51_a3_epsilon_never_writes_infinity_into_json():
    """缺一个带标定的指标 → `max_band_ratio` 曾是 `inf`，`json.dump` 落裸 `Infinity`（非法 JSON）。"""
    calib = {"epsilon": {"noise_floor": 0.0, "by_frequency": {"daily": {"usable": True, "by_metric": {
        "sharpe_net": {"status": "calibrated", "epsilon": 0.01, "tolerance_kind": "relative"},
        "turnover": {"status": "calibrated", "epsilon": 0.01, "tolerance_kind": "relative"}}}}}}
    r = L3.compare_epsilon({"sharpe_net": 1.0}, {"sharpe_net": 1.0, "turnover": 0.2},
                           declared={"rebalance_frequency": "daily"}, calib=calib)
    assert r.correctness["max_band_ratio"] is None          # 不可比出来的比值不写 inf
    assert r.correctness["n_metrics_missing"] == 1
    assert r.correctness["within_band_rate"] == pytest.approx(0.5)
    _assert_strict_json(r.correctness)


def _assert_strict_json(obj) -> None:
    """严格 JSON：`Infinity` / `NaN` 一出现就抛（别人的解析器就是这么读的）。"""
    def boom(c):
        raise AssertionError(f"落盘里出现了非法 JSON 常量 {c!r}")
    json.loads(json.dumps(obj), parse_constant=boom)


def test_rt51_a3b_sanitize_is_the_gate_not_the_caller():
    got, bad = L3.sanitize({"a": float("inf"), "b": float("nan"), "c": 1.0, "d": "x"})
    assert got == {"a": None, "b": None, "c": 1.0, "d": "x"} and sorted(bad) == ["a", "b"]
    _assert_strict_json(got)


# ============================================================ ⑤ 聚合口径
def test_rt51_d1_ceiling_must_be_a_real_self_comparison():
    """真题目录上的 S2 锚点顶：旧实现拿 `work/`（agent 的输入目录）当 oracle 自己的产物目录，
    题目录里根本没有 `work/` → CellAgree=0 → ceiling=0.75 → 所有 ≥0.75 的产物夹成 100。"""
    td = TASKS / "s2-cor-01"
    if not (td / "task.yaml").is_file():
        pytest.skip("题目录不在本机")
    spec = json.loads((td / "taskspec.json").read_text(encoding="utf-8"))
    SR._ANCHOR_CACHE.clear()
    anc = SR.anchor(td, kind="align", stage="S2", spec=spec, calib=None)
    assert anc["ceiling"] == pytest.approx(1.0), f"oracle 自比拿不到天花板：{anc}"
    assert Path(anc["ceiling_payload_dir"]).name == "gold"


def test_rt51_d1b_broken_ceiling_withholds_instead_of_clamping_to_100():
    """顶低于选手 = 天花板坏了，不是超常发挥。旧实现夹成 effect=100 并只留一个 `clamped: true`。"""
    anc = {"floor": 0.0, "ceiling": 0.75}
    eff, meta, why = SR.effect_of(L3.L3Result(kind="align", score=1.0), anc)
    assert eff is None and why == "anchor_degenerate" and meta["ceiling_below_agent"] is True
    # 判别力自检：顶正常时照常出数
    eff2, meta2, why2 = SR.effect_of(L3.L3Result(kind="align", score=0.5), {"floor": 0.0, "ceiling": 1.0})
    assert why2 is None and eff2["score"] == pytest.approx(50.0)


def test_rt51_d1c_nonfinite_metric_is_withheld_not_zero():
    """NaN 判据标量：`max(0.0, nan)` 返回 0.0 —— 旧实现把「算出来是 NaN」静默夹成 effect=0。"""
    eff, meta, why = SR.effect_of(L3.L3Result(kind="cov", score=float("nan")),
                                  {"floor": 0.0, "ceiling": 1.0})
    assert eff is None and why == "anchor_degenerate"


def _rec(**kw):
    base = dict(config_id="c", arm="strict", task_id="t", stage="S1", run_status="ok",
                sr_bucket="scorable", validity="valid", l3_pass=True, correctness={},
                run_id="r", effect=None)
    base.update(kw)
    return base


def test_rt51_d2_effect_column_reports_its_sample_size():
    """1/10 与 10/10 的 effect 均值都是 100 —— 表上必须能分开。"""
    a = [_rec(run_id=f"r{i}", effect=(100.0 if i == 0 else None)) for i in range(10)]
    b = [_rec(run_id=f"r{i}", effect=100.0) for i in range(10)]
    ra, rb = R.table_a(a)[0], R.table_a(b)[0]
    assert ra["effect"] == rb["effect"] == 100.0
    assert ra["effect_settled_runs"] == 1 and rb["effect_settled_runs"] == 10
    assert "effect_settled_runs" in R.TABLE_A_COLUMNS


def test_rt51_d3_invalid_rate_denominator_excludes_harness_faults():
    """harness 自己坏掉的 run `validity` 是 None：进不了分子却占着分母 → invalid 率被稀释。"""
    rs = [_rec(run_id="r1", validity="invalid"),
          _rec(run_id="r2", run_status="harness_error", sr_bucket="unscorable_harness", validity=None)]
    row = R.table_b(rs)[0]
    assert row["invalid_rate"] == 1.0 and row["n_runs"] == 2 and row["n_runs_denom"] == 1


def test_rt51_d3b_unknown_status_stays_in_denominator():
    """认不出的历史状态**留在分母**：移出去会抬高比率，方向对我们有利。"""
    rs = [_rec(run_id="r1", validity="invalid"), _rec(run_id="r2", run_status="退役了", validity="valid")]
    assert R.table_b(rs)[0]["n_runs_denom"] == 2


# ============================================================ ⑥ 版本与切片
def test_rt51_e1_mixed_versions_are_visible_on_the_table():
    """m6（1.0.7 / r1.0.8）与 m6b（1.0.9 / r1.0.14）合成了同一行 pass@1，表上却没有版本列。"""
    rs = [_rec(run_id="r1", l3_pass=True, set_version="1.0.7", reference_version="r1.0.8"),
          _rec(run_id="r2", l3_pass=False, set_version="1.0.9", reference_version="r1.0.14")]
    row = R.table_a(rs)[0]
    assert row["set_version"] == "MIXED:1.0.7|1.0.9"
    assert row["reference_version"] == "MIXED:r1.0.14|r1.0.8"
    assert all(ax in R.TABLE_A_COLUMNS for ax in R.VERSION_AXES)
    # 判别力自检：同版本时写的是那个版本本身，不是 MIXED
    same = [_rec(run_id="r1", set_version="1.0.12"), _rec(run_id="r2", set_version="1.0.12")]
    assert R.table_a(same)[0]["set_version"] == "1.0.12"


def test_rt51_e2_record_carries_all_four_version_axes():
    ax = SR.version_axes({"frozen_manifest": {"set_version": "1.0.12"},
                          "reference_manifest": {"reference_version": "r1.0.19"},
                          "runner_version": "abc", "image": "gb-cx-u@sha256:dead"})
    assert ax == {"set_version": "1.0.12", "reference_version": "r1.0.19",
                  "runner_version": "abc", "image_digest": "gb-cx-u@sha256:dead"}
    assert set(ax) == set(SR.VERSION_AXES)
    # 缺就是 None —— 不填一个默认值假装一致
    assert SR.version_axes({}) == {a: None for a in SR.VERSION_AXES}


def test_rt51_e3_version_axes_same_as_score_run():
    """报告器不 import `score_run`（依赖太重），两处名字由这条钉住。"""
    assert tuple(R.VERSION_AXES) == tuple(SR.VERSION_AXES)


# ============================================================ scorer 输出仍过自己的 schema
def test_rt51_scorer_output_still_valid_after_withholding():
    out = {"schema_version": "1.0", "validity": "valid", "gate_failed": [], "unobservable": [],
           "correctness": {"CellAgree": 1.0}, "effect": None,
           "effect_withheld_reason": "anchor_degenerate"}
    assert validate_scorer_output(out, anchor_status="fixed").ok


def test_rt51_e1b_hash_axes_are_short_on_the_table_full_in_the_record():
    """64 位十六进制在表上写不下，缩成前 12 位；**完整值留在 records.json**。"""
    long_runner = "37392fdc2392cbb9b650780e2b3bd09f7d7a9a1ed60af25a352cc69a7794785f"
    img = "gb-cx-u@sha256:961e3878b28fc13ef2600254c4c4cbaceb7c337e2944fc173eaba1335752561a"
    rs = [_rec(run_id="r1", runner_version=long_runner, image_digest=img, set_version="1.0.12")]
    row = R.table_a(rs)[0]
    assert row["runner_version"] == "37392fdc2392…"
    assert row["image_digest"] == "gb-cx-u@sha256:961e3878b28f…"
    assert row["set_version"] == "1.0.12"                 # 短版本号不动
    assert R._short_version("r1.0.19") == "r1.0.19"
