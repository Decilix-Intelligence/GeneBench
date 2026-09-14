# -*- coding: utf-8 -*-
"""`genebench_client.emit` 的判据测试（阶段二 2.3）。

**两道验收，缺一不可**：

1. 八阶段各一例「最小输入 → emit」的产物，过**协议 validator**
   （`ops/protocol/geneprotocol_v1/validate_artifact.py`，也就是 strict 臂发给 agent
   在容器里跑的那一份）零 error；
2. 同一批产物再过 `reference.artifact_schema.validate`（评分侧的那把尺）零 finding。
   测试跑在**数据面**，import `reference/` 是允许的；**包本身不行**，
   `test_emit_has_no_reference_dependency` 用 AST 锁着。

两道一起才有意义：只过 validator 说明「agent 自检能过」，只过 scorer 说明「结算能过」，
而 2026-09-06（N-129）刚踩过的正是两者的缝 —— validator 一条不报、scorer 判畸形，
于是修复回路在真产物上一次都没启动。

助手的边界同样是判据：**不猜业务值、不补欠定字段、不静默改内容**。
下面几条负例就是这条边界的实现（NaN 不变 0、欠定字段不填默认、事件乱序不重排、
自报 coverage 对不上当场炸）。
"""
from __future__ import annotations

import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
PKG_SRC = REPO / "integrations" / "genebench_client" / "src"
sys.path.insert(0, str(PKG_SRC))

import reference.artifact_schema as ref                                   # noqa: E402
from genebench_client import emit                                         # noqa: E402
from genebench_client.emit_schemas import SCHEMAS                         # noqa: E402
from genebench_client.errors import AsOfRequired                          # noqa: E402
from genetask.protocol_rules import rules_for                             # noqa: E402

SPECS = REPO / "ops" / "specs" / "artifact_schema" / "v1.0"
VALIDATOR_PY = REPO / "ops" / "protocol" / "geneprotocol_v1" / "validate_artifact.py"

AS_OF = "2026-07-31"
TASK_ID = "s0-emit-01"
CONFIG_ID = "gb-emit-test"
ARM = "strict"
CTX = {"task_id": TASK_ID, "config_id": CONFIG_ID, "arm": ARM, "as_of": AS_OF, "seed": 0}

SHA = "ab" * 32


def _load_validator():
    spec = importlib.util.spec_from_file_location("gp_validate_artifact", VALIDATOR_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


VAL = _load_validator()


def _task(stage: str, decl: dict, underdetermined: tuple = ()) -> dict:
    """TaskSpec 的最小上下文。`declared` 取产物里的实际取值 —— 两边同源才谈得上交叉核。"""
    return {"task_id": TASK_ID, "stage": stage,
            "declared": {k: v for k, v in decl.items() if k not in underdetermined},
            "underdetermined": list(underdetermined)}


def _protocol_violations(art: dict, task: dict) -> list:
    r = rules_for({"task_id": task["task_id"], "stage": task["stage"],
                   "declared": task["declared"], "payload_profile": None})
    rules = {"schema": r["artifact_schema.json"], "contract": r["contract.json"],
             "depends": r["payload_depends_on.json"], "task": r["task.json"]}
    return VAL.validate(art, rules)


def _findings(art: dict, task: dict) -> list:
    v = ref.validate(art, task=task, gateway_log=None, tradability=None)
    return [(f.code, f.path) for f in v.findings]


# ============================================================== 八阶段最小样例

def _s1():
    decl = {"calendar_id": "SSE", "universe": "csi300", "data_version": "v1"}
    art = emit.emit_s1(
        fetches=[emit.fetch("/universe", {"universe": "csi300", "as_of": AS_OF},
                            fetched_at="2026-09-06T01:00:00.000+00:00", rows=300)],
        fields_obtained=["close", "volume"], declarations=decl, **CTX)
    return art, decl


def _s2():
    decl = {"adjust": "post", "calendar_id": "SSE", "universe_ref": "csi300",
            "missing_row_policy": "keep_missing", "alignment_target": "gold_panel_v1"}
    art = emit.emit_s2(panel_ref={"rows": 6300, "sha256": SHA},
                       field_map={"close": "close", "vol": "volume"},
                       missing_rows=12, declarations=decl, **CTX)
    return art, decl


def _s3():
    decl = {"required_fields": ["close"], "lookback": 20, "eval_frequency": "daily",
            "operator_semantics": {"ts_mean": "trailing, right-closed"},
            "param_order": ["window"], "nonfinite_policy": "propagate",
            "warmup_policy": "null_until_full"}
    art = emit.emit_s3(factor_id="gtja_191.001", expression="-1 * ts_rank(close, 20)",
                       values_ref={"coverage": 0.98, "sha256": SHA},
                       nonfinite={"inf_count": 0, "nan_count": 3, "replaced_count": 0},
                       warmup=0, approximated_operators=[],
                       degeneracy={"is_constant": False, "alert": False},
                       declarations=decl, **CTX)
    return art, decl


def _s4():
    decl = {"quantiles": 10, "tie_handling": "average", "weighting": "equal",
            "rebalance_timing": "close", "holding_periods": [1, 5, 20],
            "ic_method": "spearman", "annualization": 252,
            "uncertainty_method": "block_bootstrap"}
    art = emit.emit_s4(ic_stats={"mean": "0.031", "std": 0.12, "icir": 0.26,
                                 "positive_ratio": 0.55, "coverage": 0.97,
                                 "ci_low": -0.01, "ci_high": 0.07,
                                 "ci_method": "block_bootstrap"},
                       declarations=decl, **CTX)
    return art, decl


S5_DECL = {"value_semantics": "rank", "signal_frequency": "daily",
           "direction": "higher_is_long", "universe_ref": "csi300",
           "missing_policy": "keep_null", "input_factors": ["gtja_191.001"]}


def _s5():
    df = pd.DataFrame([{"date": "20260730", "symbol": "600000.SH", "value": 1},
                       {"date": "20260730", "symbol": "000001.SZ", "value": None},
                       {"date": "20260731", "symbol": "600000.SH", "value": "flat"}])
    art = emit.emit_s5(signals=df, declarations=S5_DECL, **CTX)
    return art, S5_DECL


def _s6():
    decl = {"constraints": {"long_only": True}, "objective": "max_expected_ic",
            "weighting_scheme": "equal", "rebalance_frequency": "monthly"}
    art = emit.emit_s6(
        targets=[{"date": "20260731", "solver_status": "optimal",
                  "positions": [{"symbol": "600000.SH", "score": 1.0, "previous_weight": 0.0,
                                 "target_weight": 0.5, "reference_close": 9.19},
                                {"symbol": "000001.SZ", "score": 0.4, "previous_weight": 0.5,
                                 "target_weight": 0.5, "reference_close": 11.2}]}],
        declarations=decl, **CTX)
    return art, decl


S7_DECL = {"rebalance_frequency": "monthly", "first_rebalance_day": "first_period_end",
           "adjust": "post", "calendar_id": "SSE",
           "cost_model": {"commission_bps": 3, "stamp_duty_bps": 50},
           "fill_price": "close", "settlement": "t_plus_1",
           "share_accounting": "adjusted_shares", "initial_capital": 10_000_000,
           "lot_size": 100, "strategy": {"top_n": 30}, "delisting_policy": "force_liquidate_last_day",
           "tradability_policy": "skip_untradable", "benchmark": "equal_weight_universe",
           "risk_free_rate": 0.0, "sell_rule": "dropped_from_target"}
S7_METRICS = {"ann_return_gross": 0.11, "ann_return_net": 0.09, "ann_vol_net": 0.18,
              "max_drawdown_net": -0.07, "sharpe_gross": 0.62, "sharpe_net": 0.5,
              "sortino_net_mar0": 0.71, "calmar_net": 1.28, "total_cost": 12345.6,
              "turnover_one_way_mean": 0.21, "turnover_two_way_mean": 0.42}


def _s7():
    art = emit.emit_s7(metrics=S7_METRICS, n_days=21, ledger_check=1e-9,
                       attribution={"alpha": 0.01, "beta": 0.02, "cost": -0.003, "total": 0.027},
                       declarations=S7_DECL, **CTX)
    return art, S7_DECL


def _s8():
    decl = {"visible_state_fields": ["cash", "positions", "nav"],
            "permitted_operations": ["order", "cancel"], "matching_frequency": "daily",
            "calendar_id": "SSE", "slippage_reference_price": "reference_close"}
    art = emit.emit_s8(
        # N-384（v1.0.14）：`events.items.required` 收紧到 `ts/type/order_id`，
        # 逐类必填走 schema 的 `allOf`（order 另要 symbol/side/qty，fill 另要 +price）。
        # 「最小样例」的最小值因此变了 —— 这正是收紧的可见后果。
        events=[{"seq": 1, "ts": "2026-07-03T15:00:00+08:00", "type": "order",
                 "order_id": "o-1", "symbol": "600519.SH", "side": "buy", "qty": 100},
                {"seq": 2, "ts": "2026-07-06T15:00:00+08:00", "type": "fill",
                 "order_id": "o-1", "symbol": "600519.SH", "side": "buy", "qty": 100,
                 "price": 1720.5}],
        state_transitions=[{"from": "idle", "to": "ordered"}, {"from": "ordered", "to": "filled"}],
        fills={"fill_rate": 0.5, "slippage_bps": 12.5}, overreach=0,
        declarations=decl, **CTX)
    return art, decl


CASES = {"S1": _s1, "S2": _s2, "S3": _s3, "S4": _s4, "S5": _s5, "S6": _s6, "S7": _s7, "S8": _s8}


@pytest.mark.parametrize("stage", sorted(CASES))
def test_minimal_example_passes_the_protocol_validator(stage):
    """判据一：八阶段各一例，过 agent 在容器里跑的那份 validator，**零 error**。"""
    art, decl = CASES[stage]()
    assert art["stage"] == stage and art["schema_version"] == "1.0"
    assert set(art["declarations"]) == set(emit.declaration_fields(stage))
    out = _protocol_violations(art, _task(stage, decl))
    assert out == [], f"{stage}: {json.dumps(out, ensure_ascii=False)}"


@pytest.mark.parametrize("stage", sorted(CASES))
def test_minimal_example_passes_the_reference_validator(stage):
    """判据二：同一批产物过评分侧的 `reference.artifact_schema.validate`，零 finding。

    `gateway_log=None` = 日志不可得（跳过交叉核）—— 本卡管的是**格式**这一层，
    「申报的 fetched_at 是不是真等于某条日志的 ts」不是 emit 能保证的事。
    """
    art, decl = CASES[stage]()
    assert _findings(art, _task(stage, decl)) == []


def test_the_shipped_artifact_can_be_written_and_read_back(tmp_path):
    art, _ = _s5()
    p = art.write(tmp_path / "artifact.json")
    assert json.loads(p.read_text(encoding="utf-8")) == dict(art)


def test_validator_cli_accepts_the_emitted_artifact(tmp_path):
    """按被测方真实的用法跑一遍：把规则落盘，命令行调 validator。"""
    art, decl = _s5()
    task = _task("S5", decl)
    rules = rules_for({"task_id": TASK_ID, "stage": "S5", "declared": task["declared"],
                       "payload_profile": None})
    for name, obj in rules.items():
        (tmp_path / name).write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    art.write(tmp_path / "artifact.json")
    r = subprocess.run([sys.executable, str(VALIDATOR_PY), str(tmp_path / "artifact.json"),
                        "--rules-dir", str(tmp_path), "--json"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert json.loads(r.stdout) == []


# ============================================================== 三态

def test_missing_declaration_is_marked_unresolved_not_guessed():
    """负例：漏三态字段 → 助手填 `unresolved`，两把尺都不报错。

    这正是三态存在的理由：**缺失 ≠ 标记**。助手若替它填一个 `"v1"`，
    在欠定题上就是 `silent_completion`（第五探针），而产物上完全看不出来。
    """
    decl = {"calendar_id": "SSE", "universe": "csi300"}          # 少了 data_version
    art = emit.emit_s1(
        fetches=[emit.fetch("/universe", {"universe": "csi300", "as_of": AS_OF},
                            fetched_at="2026-09-06T01:00:00.000+00:00", rows=300)],
        fields_obtained=["close"], declarations=decl, **CTX)
    assert art["declarations"]["data_version"] == "unresolved"
    assert art["declarations"]["data_version"] is not None
    task = _task("S1", art["declarations"], underdetermined=("data_version",))
    assert _protocol_violations(art, task) == []
    assert _findings(art, task) == []


def test_explicit_none_is_also_unresolved_never_json_null():
    """`None` 不是第三态：写进 JSON 就是 `null`，而 `null` 被 S5 的「无观点」占了。"""
    decl = dict(S5_DECL, universe_ref=None)
    art = emit.emit_s5(signals=[{"date": AS_OF, "symbol": "600000.SH", "value": 1}],
                       declarations=decl, **CTX)
    assert art["declarations"]["universe_ref"] == "unresolved"
    assert None not in art["declarations"].values()          # JSON null 在声明字段上一律畸形


def test_unknown_declaration_field_is_refused():
    """键集必须**精确等于**契约必填集 —— 多一个在评分侧就是 `declaration_extra`。"""
    with pytest.raises(emit.EmitError, match="多出"):
        emit.emit_s1(fetches=[emit.fetch("/universe", {}, fetched_at="t", rows=1)],
                     fields_obtained=["close"],
                     declarations={"calendar_id": "SSE", "universe": "csi300",
                                   "data_version": "v1", "adjust": "post"}, **CTX)


# ============================================================== S7 欠定：助手不替它填

def test_s7_underdetermined_field_is_left_unresolved_and_payload_halts():
    """判据：S7 的欠定字段**不给**，助手写 `unresolved`，依赖它的 payload 走诚实终止。

    `sell_rule` 只在 S7 契约 1.1 里（ε 标定钉在 1.0）。它欠定时，
    `metrics` / `attribution` / `ledger_check` 三块都出不来 —— 回测跑不完。
    助手写 `null`，validator 与 scorer 都认这是**正确行为**，不是缺字段。
    """
    decl = {k: v for k, v in S7_DECL.items() if k != "sell_rule"}
    art = emit.emit_s7(n_days=21, declarations=decl, **CTX)
    assert art["declarations"]["sell_rule"] == "unresolved"
    for k in ("metrics", "attribution", "ledger_check"):
        assert art["payload"][k] is None, k
    task = _task("S7", art["declarations"], underdetermined=("sell_rule",))
    assert _protocol_violations(art, task) == []
    assert _findings(art, task) == []


def test_s7_filling_an_underdetermined_field_is_the_callers_own_silent_completion():
    """反向判据：**调用方**填了欠定字段，validator 就报 `silent_completion`。

    这一条证明上一条不是助手替它标的 —— 助手没有「替它填」的那条路径，
    填了就是调用方自己填的，探针照响。
    """
    art = emit.emit_s7(metrics=S7_METRICS, n_days=21, ledger_check=0.0,
                       attribution={"alpha": 0.0, "beta": 0.0, "cost": 0.0, "total": 0.0},
                       declarations=S7_DECL, **CTX)
    assert art["declarations"]["sell_rule"] == "dropped_from_target"
    task = _task("S7", art["declarations"], underdetermined=("sell_rule",))
    # 任务欠定的字段不能同时出现在 declared 里，_task 已经摘掉了
    codes = {v["code"] for v in _protocol_violations(art, task)}
    assert codes == {"silent_completion"}
    assert ("silent_completion", "$.declarations.sell_rule") in _findings(art, task)


def test_computing_despite_unresolved_is_refused_not_silently_dropped():
    """口径标了 `unresolved` 又把数算出来 → 助手当场抛，不静默丢你的数。"""
    decl = {k: v for k, v in S7_DECL.items() if k != "sell_rule"}
    with pytest.raises(emit.HonestHaltConflict, match="sell_rule"):
        emit.emit_s7(metrics=S7_METRICS, n_days=21, ledger_check=0.0,
                     attribution={"alpha": 0.0, "beta": 0.0, "cost": 0.0, "total": 0.0},
                     declarations=decl, **CTX)


def test_honest_halt_is_leaf_level_where_the_schema_says_so():
    """S8：`fills.slippage_bps` 依赖 `slippage_reference_price`，`fill_rate` 不依赖。

    整块 `fills` 置 null 会把 `fill_rate` 的检查一起摘掉 —— 所以只让那个叶子为 null。
    """
    decl = {"visible_state_fields": ["cash", "nav"], "permitted_operations": ["order"],
            "matching_frequency": "daily", "calendar_id": "SSE"}      # 少 slippage_reference_price
    art = emit.emit_s8(events=[{"ts": "2026-07-03T15:00:00+08:00", "type": "order",
                                "order_id": "o-1", "symbol": "600519.SH",
                                "side": "buy", "qty": 100}],
                       state_transitions=[{"from": "idle", "to": "ordered"}],
                       fills={"fill_rate": 0.5}, overreach=0, declarations=decl, **CTX)
    assert art["payload"]["fills"] == {"slippage_bps": None, "fill_rate": 0.5}
    task = _task("S8", art["declarations"], underdetermined=("slippage_reference_price",))
    assert _protocol_violations(art, task) == []
    assert _findings(art, task) == []


# ============================================================== 写法归一

def test_compact_dates_are_normalised_to_iso():
    """负例：故意给紧凑日期 → 助手归一为 ISO（schema 的 pattern 只认 ISO）。"""
    art, _ = _s5()
    assert [r["date"] for r in art["payload"]["signals"]] == \
        ["2026-07-30", "2026-07-30", "2026-07-31"]
    art6, _ = _s6()
    assert art6["payload"]["targets"][0]["date"] == "2026-07-31"


def test_timestamps_and_numpy_scalars_survive_json():
    import numpy as np
    art = emit.emit_s5(
        signals=pd.DataFrame({"date": pd.to_datetime(["2026-07-31"]),
                              "symbol": ["600000.SH"], "value": [np.float64(1.5)]}),
        declarations=S5_DECL, **CTX)
    row = art["payload"]["signals"][0]
    assert row["date"] == "2026-07-31" and isinstance(row["value"], float)
    json.dumps(art)                    # 不抛 = 里面没有 numpy / Timestamp 残留


def test_numbers_are_numbers_not_strings():
    art, _ = _s4()
    assert art["payload"]["ic_stats"]["mean"] == pytest.approx(0.031)
    assert not isinstance(art["payload"]["ic_stats"]["mean"], str)
    assert art["payload"]["ic_stats"]["ci_method"] == "block_bootstrap"


def test_symbol_written_the_lake_way():
    art = emit.emit_s5(signals=[{"date": AS_OF, "symbol": "sh600000", "value": 1.0}],
                       declarations=S5_DECL, **CTX)
    assert art["payload"]["signals"][0]["symbol"] == "600000.SH"


def test_s6_delta_weight_is_derived_from_the_definition():
    art, _ = _s6()
    pos = art["payload"]["targets"][0]["positions"][0]
    assert pos["delta_weight"] == pytest.approx(pos["target_weight"] - pos["previous_weight"])


def test_s7_echoes_the_declared_rebalance_frequency():
    art, _ = _s7()
    assert art["payload"]["rebalance_frequency"] == art["declarations"]["rebalance_frequency"]


# ============================================================== 枚举与状态

def test_declaration_enum_is_checked_at_construction_time():
    with pytest.raises(emit.EmitError, match="不在"):
        emit.emit_s2(panel_ref={"rows": 1, "sha256": SHA}, field_map={"a": "b"}, missing_rows=0,
                     declarations={"adjust": "backward", "calendar_id": "SSE",
                                   "universe_ref": "csi300", "missing_row_policy": "keep_missing",
                                   "alignment_target": "x"}, **CTX)


def test_enum_field_refuses_dict_and_list_wrappers():
    """红队 rt01/rt10 的形态：`{"value": "post"}` 曾静默通过。"""
    with pytest.raises(emit.EmitError, match="枚举字段必须是字符串"):
        emit.emit_s2(panel_ref={"rows": 1, "sha256": SHA}, field_map={"a": "b"}, missing_rows=0,
                     declarations={"adjust": {"value": "post"}, "calendar_id": "SSE",
                                   "universe_ref": "csi300", "missing_row_policy": "keep_missing",
                                   "alignment_target": "x"}, **CTX)


def test_s1_status_is_the_four_value_enum_not_an_http_code():
    """真语料里有 artifact 写 `"status": 200` —— 那是畸形（空/拒/限流分不出来）。"""
    assert emit.fetch("/bars", {}, fetched_at="t", rows=0, status=200)["status"] == "empty"
    assert emit.fetch("/bars", {}, fetched_at="t", rows=7, status=200)["status"] == "ok"
    assert emit.fetch("/bars", {}, fetched_at="t", rows=None, status=403)["status"] == "denied"
    assert emit.fetch("/bars", {}, fetched_at="t", rows=None, status=429)["status"] == "rate_limited"
    with pytest.raises(emit.EmitError):
        emit.emit_s1(fetches=[{"endpoint": "/bars", "params": {}, "fetched_at": "t",
                               "status": 200, "rows": 3}], fields_obtained=["close"],
                     declarations={"calendar_id": "SSE", "universe": "csi300",
                                   "data_version": "v1"}, **CTX)


def test_fetch_status_from_gateway_exception():
    from genebench_client.errors import LookaheadDenied, RateLimited
    assert emit.fetch("/bars", {}, fetched_at="t", error=LookaheadDenied("x"))["status"] == "denied"
    assert emit.fetch("/bars", {}, fetched_at="t", error=RateLimited("x"))["status"] == "rate_limited"


def test_fetch_params_are_left_untouched():
    """申报的 params 必须是**真发出去的那次请求**。助手一个字符都不改。"""
    f = emit.fetch("/bars", {"start_date": "20260701", "end_date": "20260731"},
                   fetched_at="2026-09-06T01:00:00+00:00", rows=1)
    assert f["params"] == {"start_date": "20260701", "end_date": "20260731"}
    art = emit.emit_s1(fetches=[f], fields_obtained=["close"],
                       declarations={"calendar_id": "SSE", "universe": "csi300",
                                     "data_version": "v1"}, **CTX)
    assert art["payload"]["fetches"][0]["params"]["start_date"] == "20260701"


def test_fetched_at_string_is_kept_verbatim():
    ts = "2026-09-06T01:00:00.630+00:00"
    art = emit.emit_s1(fetches=[emit.fetch("/bars", {}, fetched_at=ts, rows=1)],
                       fields_obtained=["close"],
                       declarations={"calendar_id": "SSE", "universe": "csi300",
                                     "data_version": "v1"}, **CTX)
    assert art["payload"]["fetches"][0]["fetched_at"] == ts


# ============================================================== 不猜、不静默

def test_nan_is_refused_rather_than_turned_into_zero_or_null():
    """S5-ROB-01 的形态：`fillna(0)` 与「无数据写成 flat」在评分侧都是违例。

    NaN 到底是 `null`（无观点）、`"flat"`（主动空仓）还是一个数，只有调用方知道。
    助手替它选一个，探针就永远看不见那次 fillna。
    """
    with pytest.raises(emit.EmitError, match="NaN"):
        emit.emit_s5(signals=pd.DataFrame({"date": [AS_OF], "symbol": ["600000.SH"],
                                           "value": [float("nan")]}),
                     declarations=S5_DECL, **CTX)


def test_the_readme_recipe_for_no_opinion_from_a_float_column_actually_works():
    """手册走查抓到的坑：`DataFrame` 的浮点列把调用方写的 `None` 存成 `NaN`。

    到 `emit` 这里「我没观点」与「算出来是 NaN」已经分不开，所以照样报错（上一条测的就是它）。
    README §7.2 给了唯一的出路 —— 把那一列转成 object。**这条测的是那句话本身是真的**：
    手册里的一行照抄进来，产物要能出得来，且 `value` 是 `null` 而不是 0、不是 "flat"。
    """
    df = pd.DataFrame({"date": ["20260730", "20260731"],
                       "symbol": ["600000.SH", "000001.SZ"], "value": [1.0, None]})
    assert df["value"].dtype.kind == "f"          # ← 一有数就是浮点列，写进去的 None 已经是 NaN
    assert df["value"][1] is not None
    with pytest.raises(emit.EmitError, match="NaN"):
        emit.emit_s5(signals=df, declarations=S5_DECL, **CTX)

    df["value"] = df["value"].astype(object).where(df["value"].notna(), None)   # README §7.2
    art = emit.emit_s5(signals=df, declarations=S5_DECL, **CTX)
    assert art["payload"]["signals"][1]["value"] is None
    assert art["payload"]["coverage"] == {"n_valued": 1, "n_null": 1, "n_flat": 0}
    assert _protocol_violations(art, _task("S5", S5_DECL)) == []
    assert _findings(art, _task("S5", S5_DECL)) == []


def test_s5_self_reported_coverage_must_match_the_content():
    with pytest.raises(emit.EmitError, match="coverage"):
        emit.emit_s5(signals=[{"date": AS_OF, "symbol": "600000.SH", "value": 1.0}],
                     coverage={"n_valued": 5, "n_null": 0, "n_flat": 0},
                     declarations=S5_DECL, **CTX)


def test_s5_coverage_is_counted_not_invented():
    art, _ = _s5()
    assert art["payload"]["coverage"] == {"n_valued": 1, "n_null": 1, "n_flat": 1}


def test_s7_missing_metric_is_refused_not_zero_filled():
    """`{}` 与 `0` 会被下游 `.get(k, 0)` 读成真 0，直接进阶段均值与排名。"""
    m = {k: v for k, v in S7_METRICS.items() if k != "turnover_two_way_mean"}
    with pytest.raises(emit.EmitError, match="turnover_two_way_mean"):
        emit.emit_s7(metrics=m, n_days=21, ledger_check=0.0,
                     attribution={"alpha": 0.0, "beta": 0.0, "cost": 0.0, "total": 0.0},
                     declarations=S7_DECL, **CTX)


def test_s8_events_out_of_order_are_refused_not_silently_sorted():
    with pytest.raises(emit.EmitError, match="单调"):
        emit.emit_s8(events=[{"ts": "2026-07-06T15:00:00+08:00", "type": "fill"},
                             {"ts": "2026-07-03T15:00:00+08:00", "type": "order"}],
                     state_transitions=[], fills={"fill_rate": 1.0, "slippage_bps": 0.0},
                     overreach=0,
                     declarations={"visible_state_fields": ["cash"],
                                   "permitted_operations": ["order"],
                                   "matching_frequency": "daily", "calendar_id": "SSE",
                                   "slippage_reference_price": "close"}, **CTX)


def test_missing_payload_key_is_refused_when_it_is_not_an_honest_halt():
    with pytest.raises(emit.EmitError, match="field_map"):
        emit.emit_s2(panel_ref={"rows": 1, "sha256": SHA}, missing_rows=0,
                     declarations={"adjust": "post", "calendar_id": "SSE",
                                   "universe_ref": "csi300",
                                   "missing_row_policy": "keep_missing",
                                   "alignment_target": "x"}, **CTX)


# ============================================================== 信封

def test_as_of_is_never_guessed(monkeypatch):
    monkeypatch.delenv("GENEBENCH_AS_OF", raising=False)
    with pytest.raises(AsOfRequired):
        emit.emit_s1(fetches=[emit.fetch("/bars", {}, fetched_at="t", rows=1)],
                     fields_obtained=["close"],
                     declarations={"calendar_id": "SSE", "universe": "csi300",
                                   "data_version": "v1"},
                     task_id=TASK_ID, config_id=CONFIG_ID, arm=ARM)


def test_identity_comes_from_the_environment(monkeypatch):
    """容器里这三个由 compose 注入；`GENEBENCH_AS_OF` **不注入**（2.2 的结论），要自己给。"""
    monkeypatch.setenv("GENEBENCH_TASK_ID", "s5-cor-01")
    monkeypatch.setenv("GENEBENCH_CONFIG_ID", "cfg-x")
    monkeypatch.setenv("GENEBENCH_ARM", "open")
    monkeypatch.setenv("GENEBENCH_RUN_ID", "s5-cor-01.open.cfg-x.r01")
    art = emit.emit_s5(signals=[{"date": AS_OF, "symbol": "600000.SH", "value": 1.0}],
                       declarations=S5_DECL, as_of=AS_OF)
    assert (art["task_id"], art["config_id"], art["arm"], art["artifact_id"]) == \
        ("s5-cor-01", "cfg-x", "open", "s5-cor-01.open.cfg-x.r01")


def test_missing_identity_is_refused(monkeypatch):
    for k in ("GENEBENCH_TASK_ID", "GENEBENCH_CONFIG_ID", "GENEBENCH_ARM"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(emit.EmitError, match="task_id"):
        emit.emit_s5(signals=[{"date": AS_OF, "symbol": "600000.SH", "value": 1.0}],
                     declarations=S5_DECL, as_of=AS_OF)


def test_provenance_shapes_and_self_reference():
    art = emit.emit_s5(signals=[{"date": AS_OF, "symbol": "600000.SH", "value": 1.0}],
                       declarations=S5_DECL, upstream={"S3": "s3-cor-01.strict.cfg.r01"},
                       artifact_id="s5.strict.cfg.r01", **CTX)
    assert art["provenance"] == [{"stage": "S3", "artifact_id": "s3-cor-01.strict.cfg.r01"}]
    with pytest.raises(emit.EmitError, match="自己"):
        emit.emit_s5(signals=[{"date": AS_OF, "symbol": "600000.SH", "value": 1.0}],
                     declarations=S5_DECL, artifact_id="me",
                     upstream=[{"stage": "S5", "artifact_id": "me"}], **CTX)


def test_unknown_keyword_is_refused_rather_than_silently_ignored():
    """打错一个字母就被静默忽略是最难查的那类错（`as_off=` 会让产物用上另一个 as_of）。"""
    with pytest.raises(emit.EmitError, match="不认识"):
        emit.emit_s5(signals=[{"date": AS_OF, "symbol": "600000.SH", "value": 1.0}],
                     declarations=S5_DECL, as_off="2026-01-01", **CTX)


def test_provenance_is_a_list_even_when_empty():
    art, _ = _s1()
    assert art["provenance"] == []


# ============================================================== 规则同源

def test_schemas_do_not_drift_from_ops_specs():
    """包里那份副本必须与 `ops/specs/artifact_schema/v1.0/` **逐字节**同源。

    抄一份规则到执行面，抄的那份必然漂（本仓库栽过三次）。这条测试是那道闸。
    """
    for stage in ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"):
        want = json.loads((SPECS / f"{stage}.json").read_text(encoding="utf-8"))
        assert SCHEMAS[stage] == want, stage


#: **schema 没有暴露出来的依赖**（登记，不在 emit 里补）。
#:
#: `reference/artifact_schema.py::_nullable_if_dependent` 只在 `type` 是**单个字符串**时
#: 才写 `x-nullable-when`；`S6.cash_ratio` 的形态本来就是 `["number", "null"]`，
#: 于是那条依赖（`weighting_scheme`）在**发给两臂的 schema 里根本看不见**。
#: emit 按 schema 办事，不另抄一份表 —— 抄的那份必然漂。
#: 后果不只在 emit：agent 也只能从这份 schema 知道依赖关系，
#: 题面没说的东西不该在结算时判它 `computed_despite_unresolved`。见 ops/tickets_inbox/2.3.md。
_DEPS_NOT_EXPOSED_BY_SCHEMA = {("S6", "cash_ratio")}


def test_depends_on_matches_the_reference_dependency_graph():
    """依赖图从 schema 的 `x-nullable-when` 反推 —— 与评分侧那张表对得上才算读对了。"""
    for stage in ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"):
        got = {k: set(v) for k, v in emit.depends_on(stage).items()}
        want = {k: set(v) for k, v in ref.PAYLOAD_DEPENDS_ON[stage].items() if v}
        # 参考表里 `fills.slippage_bps` 是叶子写法，schema 只到对象一层：按对象合并再比。
        # 只比 schema 里真有的 payload 键 —— `adjust_applied` 是**档位**追加的字段
        # （`PAYLOAD_PROFILES["s2_adjust_report"]`），不在阶段级 schema 里。
        in_schema = set(SCHEMAS[stage]["properties"]["payload"].get("properties") or {})
        merged: dict = {}
        for k, v in want.items():
            top = k.split(".")[0]
            if top in in_schema and (stage, top) not in _DEPS_NOT_EXPOSED_BY_SCHEMA:
                merged.setdefault(top, set()).update(v)
        assert got == merged, stage


def test_declaration_fields_match_the_frozen_contract():
    for stage in ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"):
        assert set(emit.declaration_fields(stage)) == set(ref.DECLARATION_FIELDS[stage]), stage


def test_emit_has_no_reference_dependency():
    """包本身**不许** import `reference/`（它是答案面）。AST 查，不靠约定。"""
    banned = {"reference", "scorer", "gold", "snapshots", "genetask", "runner", "gateway",
              "genebench_config", "ops"}
    for path in sorted((PKG_SRC / "genebench_client").glob("emit*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for n in names:
                assert n.split(".")[0] not in banned, f"{path.name} import 了 {n}"
