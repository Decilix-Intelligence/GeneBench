# -*- coding: utf-8 -*-
"""卡 2.3 的验收样例：**每阶段一个合法样例与三个以上非法样例**。

非法样例的选法原则（2026-09-01 签字确认）：**按冻结项各挑一个会「静默通过」的形态**，
不是随手凑三个缺字段。每个非法样例写明期望命中的 code；标 ``exclusive`` 的还要求
**只有**那一个 code 命中 —— 否则被测的那条规则可能是空的（D-06）。

样例里的数值全是合成值。
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from reference.artifact_schema import FLAT, SCHEMA_VERSION, UNRESOLVED

TS1 = "2026-09-01T12:00:00.000+00:00"
TS2 = "2026-09-01T12:00:01.000+00:00"
TASK = "T-sample"
CFG = "cfg-sample"


@dataclass
class Sample:
    name: str
    artifact: dict
    task: dict | None = None
    log: list[dict] | None = None
    trad: dict | None = None


@dataclass
class Illegal(Sample):
    code: str = ""
    exclusive: bool = True
    severity: str = "malformed"        # 期望的严重级


def _env(stage: str, decl: dict, payload: dict, **over) -> dict:
    a = {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": f"{stage}-art-1",
        "stage": stage,
        "task_id": TASK,
        "config_id": CFG,
        "arm": "strict",
        "seed": 0,
        "as_of": "2026-07-31",
        "produced_at": TS1,
        "provenance": [],
        "declarations": decl,
        "payload": payload,
    }
    a.update(over)
    return a


def _task(stage: str, decl: dict, under: list[str] | None = None) -> dict:
    d = {k: v for k, v in decl.items() if k not in set(under or [])}
    return {"task_id": TASK, "stage": stage, "declared": d, "underdetermined": list(under or [])}


def _log(path: str, *, ts: str = TS1, decision: str = "allow", rows: int = 8,
         params: dict | None = None, reason: str | None = None) -> dict:
    return {"ts": ts, "task_id": TASK, "config_id": CFG, "method": "GET", "path": path,
            "params": params or {}, "as_of": "2026-07-31", "decision": decision,
            "reason": reason, "status": 200 if decision == "allow" else 403,
            "rows": rows if decision == "allow" else None}


# ============================================================== 各阶段合法样例

def s1() -> Sample:
    decl = {"calendar_id": "SSE", "universe": "csi300", "data_version": "v1"}
    log = [_log("/bars", params={"code": "600519.SH", "fields": "close"})]
    payload = {
        "fetches": [{"endpoint": "/bars", "params": {"code": "600519.SH", "fields": "close"},
                     "fetched_at": TS1, "status": "ok", "rows": 8}],
        "fields_obtained": ["close"],
    }
    return Sample("S1", _env("S1", decl, payload), _task("S1", decl), log)


def s2() -> Sample:
    decl = {"adjust": "post", "calendar_id": "SSE", "universe_ref": "csi300@2026-07-31",
            "missing_row_policy": "keep_missing", "alignment_target": "market_view_v1"}
    trad = {("2026-07-01", "000001.SZ"): "trade", ("2026-07-02", "000001.SZ"): "no_data",
            ("2026-07-03", "000001.SZ"): "suspend", ("2026-07-06", "000001.SZ"): "no_data"}
    payload = {
        "panel_ref": {"rows": 1200, "n_symbols": 300, "n_dates": 4, "sha256": "ab" * 32},
        "field_map": {"ts_code": "symbol", "trade_date": "date", "close": "close"},
        "missing_rows": {"count": 3, "policy_applied": "keep_missing"},
    }
    return Sample("S2", _env("S2", decl, payload), _task("S2", decl), None, trad)


def s3() -> Sample:
    decl = {"required_fields": ["close"], "lookback": 20, "eval_frequency": "daily",
            "operator_semantics": {"ts_rank": "pct_0_1"}, "param_order": ["window"],
            "nonfinite_policy": "propagate", "warmup_policy": "null_until_full"}
    log = [_log("/bars", params={"code": "600519.SH", "fields": "close"})]
    payload = {
        "factor_id": "gtja_191.001", "expression": "ts_rank(close, 20)",
        "values_ref": {"rows": 6000, "n_dates": 20, "n_symbols": 300, "coverage": 0.97, "sha256": "cd" * 32},
        "nonfinite": {"inf_count": 0, "nan_count": 12, "replaced_count": 0},
        "warmup": {"lookback": 20, "first_valid_date": "2026-01-29", "nonnull_before_warmup": 0},
        "approximated_operators": [],
        "degeneracy": {"is_constant": False, "alert": False, "coverage": 0.97},
    }
    return Sample("S3", _env("S3", decl, payload), _task("S3", decl), log)


def s4() -> Sample:
    decl = {"quantiles": 10, "tie_handling": "average", "weighting": "equal",
            "rebalance_timing": "close", "holding_periods": [1, 5, 20], "ic_method": "spearman",
            "annualization": 252, "uncertainty_method": "block_bootstrap"}
    payload = {
        "ic_stats": {"mean": 0.031, "std": 0.12, "icir": 0.258, "positive_ratio": 0.56,
                     "coverage": 0.98, "ci_low": 0.012, "ci_high": 0.05, "ci_method": "block_bootstrap"},
        "nw_t": 3.4, "half_life_days": 6.5,
    }
    return Sample("S4", _env("S4", decl, payload), _task("S4", decl))


def s5() -> Sample:
    decl = {"value_semantics": "score", "signal_frequency": "daily", "direction": "higher_is_long",
            "universe_ref": "csi300@2026-07-31", "missing_policy": "keep_null",
            "input_factors": ["gtja_191.001"]}
    trad = {("2026-07-31", "600519.SH"): "trade", ("2026-07-31", "000001.SZ"): "trade",
            ("2026-07-31", "300750.SZ"): "no_data", ("2026-07-31", "601318.SH"): "trade"}
    payload = {
        "signals": [
            {"date": "2026-07-31", "symbol": "600519.SH", "value": 0.82},
            {"date": "2026-07-31", "symbol": "000001.SZ", "value": -0.31},
            {"date": "2026-07-31", "symbol": "300750.SZ", "value": None},      # 无数据 → 无观点
            {"date": "2026-07-31", "symbol": "601318.SH", "value": FLAT},      # 有数据，主动空仓
        ],
        "coverage": {"n_valued": 2, "n_null": 1, "n_flat": 1},
    }
    return Sample("S5", _env("S5", decl, payload), _task("S5", decl), None, trad)


def _positions(delta_zero: bool = False) -> list[dict]:
    rows = [("600519.SH", 0.9, 0.05, 0.10, 1720.5), ("000001.SZ", 0.4, 0.05, 0.00, 11.2)]
    out = []
    for sym, score, prev, tgt, px in rows:
        if delta_zero:
            tgt = prev
        out.append({"symbol": sym, "score": score, "previous_weight": prev,
                    "target_weight": tgt, "delta_weight": tgt - prev, "reference_close": px})
    return out


def s6() -> Sample:
    decl = {"constraints": {"long_only": True, "max_weight": 0.1}, "objective": "max_score",
            "weighting_scheme": "equal", "rebalance_frequency": "daily"}
    payload = {
        "targets": [{"date": "2026-07-31", "solver_status": "optimal", "positions": _positions()}],
        "cash_ratio": None,                 # N-26 留位：v1 为 null，但字段必须在
    }
    return Sample("S6", _env("S6", decl, payload), _task("S6", decl))


S7_DECL = {
    "rebalance_frequency": "daily", "first_rebalance_day": "window_start", "adjust": "post",
    "calendar_id": "SSE",
    "cost_model": {"commission_bps": 3, "stamp_tax_bps": 5, "slippage_bps": 0},
    "fill_price": "close", "settlement": "t_plus_1", "share_accounting": "adjusted_shares",
    "initial_capital": 100_000_000, "lot_size": 100,
    "strategy": {"type": "TopkDropout", "topk": 50, "n_drop": 5},
    "delisting_policy": "force_liquidate_last_day", "tradability_policy": "skip_untradable",
    "benchmark": "equal_weight_universe", "risk_free_rate": 0, "sell_rule": "worst_n_drop",
}


def _s7_payload(freq: str = "daily") -> dict:
    return {
        "metrics": {"ann_return_gross": 0.184, "ann_return_net": 0.121, "ann_vol_net": 0.22,
                    "max_drawdown_net": -0.31, "sharpe_gross": 0.84, "sharpe_net": 0.55,
                    "sortino_net_mar0": 0.71, "calmar_net": 0.39, "total_cost": 0.471,
                    "turnover_one_way_mean": 0.043, "turnover_two_way_mean": 0.086},
        "n_days": 1818,
        "rebalance_frequency": freq,
        "ledger_check": {"max_abs_residual": 1e-9},
        "attribution": {"alpha": 0.06, "beta": 0.124, "cost": -0.063, "total": 0.121},
    }


def s7() -> Sample:
    return Sample("S7", _env("S7", dict(S7_DECL), _s7_payload()), _task("S7", S7_DECL))


def s7_unresolved_ok() -> Sample:
    """**欠定任务上诚实标记 unresolved + 依赖它的量不出数 —— 这是正确行为，必须通过。**

    2026-09-03 裁定（PAYLOAD_DEPENDS_ON）：`rebalance_frequency` 欠定就跑不了回测，
    metrics / attribution / ledger_check 三块因此**应当**为 null。旧版本样例把数照样填上 ——
    那不是诚实标记，是「标了 unresolved 又私下挑了一个取值」，现在由 `computed_despite_unresolved` 判。
    """
    decl = dict(S7_DECL); decl["rebalance_frequency"] = UNRESOLVED
    payload = _s7_payload(UNRESOLVED)
    for k in ("metrics", "attribution", "ledger_check"):
        payload[k] = None                      # 诚实终止：算不出就不出数（不是出 0）
    return Sample("S7-unresolved", _env("S7", decl, payload),
                  _task("S7", S7_DECL, under=["rebalance_frequency"]))


def s8() -> Sample:
    decl = {"visible_state_fields": ["cash", "positions", "nav"],
            "permitted_operations": ["order", "cancel"], "matching_frequency": "daily",
            "calendar_id": "SSE", "slippage_reference_price": "reference_close"}
    log = [_log("/bars", ts=TS1), _log("/bars", ts=TS2, decision="deny", reason="asof_violation")]
    # N-384（v1.0.14）：`PAYLOAD_SHAPE["S8"].events.items.required` 收紧到 `ts/type/order_id`，
    # 逐类的必填（order 的 symbol/side/qty、fill 的 +price、state 的 state）写在 schema 的 `allOf` 里。
    # 这个「合法样例」因此必须带齐 —— 收紧之前它只有 `symbol`/`qty`，收紧之后那份会被判畸形。
    # `reference_close` 不是必填，但样例带上：`scorer/l3.py::_slip_recompute`（N-383 的 Slip 判据）
    # 就是从 order 事件的这个键取计价基准的，样例不带就没有一份合法样例能演示 Slip 判得动。
    payload = {
        "events": [{"ts": TS1, "type": "order", "order_id": "o-1", "symbol": "600519.SH",
                    "side": "buy", "qty": 100, "reference_close": 1700.0},
                   {"ts": TS2, "type": "fill", "order_id": "o-1", "symbol": "600519.SH",
                    "side": "buy", "qty": 100, "price": 1720.5}],
        "state_transitions": [{"from": "idle", "to": "ordered", "order_id": "o-1"},
                              {"from": "ordered", "to": "filled", "order_id": "o-1"}],
        "fills": {"fill_rate": 1.0, "slippage_bps": 120.5882352941},   # (1720.5−1700)/1700×1e4，与上面的事件链自洽（N-383 的 SlipSelfConsistent）
        "overreach": {"denied_requests": 1},
    }
    return Sample("S8", _env("S8", decl, payload), _task("S8", decl), log)


LEGAL: dict[str, Sample] = {s.name: s for s in
                            (s1(), s2(), s3(), s4(), s5(), s6(), s7(), s7_unresolved_ok(), s8())}


# ============================================================== 非法样例

def _mut(sample: Sample, fn) -> Sample:
    s = deepcopy(sample)
    fn(s)
    return s


def _ill(base: Sample, name: str, code: str, fn, *, exclusive: bool = True,
         severity: str = "malformed") -> Illegal:
    m = _mut(base, fn)
    return Illegal(name, m.artifact, m.task, m.log, m.trad, code, exclusive, severity)


def _set_log_fields(s: Sample, fields: str) -> None:
    s.log[0]["params"]["fields"] = fields


ILLEGAL: list[Illegal] = [
    # ---------------- 版本分派（2.3-b）----------------
    _ill(s1(), "版本未知：0.9", "unknown_schema_version",
         lambda s: s.artifact.__setitem__("schema_version", "0.9")),
    _ill(s1(), "版本缺失", "missing_schema_version",
         lambda s: s.artifact.pop("schema_version")),

    # ---------------- S1 ----------------
    _ill(s1(), "S1 抓取时点不等于网关时钟", "fetch_clock_mismatch",
         lambda s: s.artifact["payload"]["fetches"][0].__setitem__("fetched_at", "2026-09-01T11:59:59+00:00"),
         severity="violation"),
    _ill(s1(), "S1 日志说空结果，artifact 说 ok", "source_status_mismatch",
         lambda s: s.log[0].__setitem__("rows", 0), severity="violation"),
    _ill(s1(), "S1 状态枚举外", "s1_status_enum",
         lambda s: s.artifact["payload"]["fetches"][0].__setitem__("status", "unknown"),
         exclusive=False),   # 日志核对也会响，这条只证枚举门

    # ---------------- S2 ----------------
    _ill(s2(), "S2 声明 keep_missing 却报 0 缺行（静默补行）", "missing_rows_silently_filled",
         lambda s: s.artifact["payload"]["missing_rows"].__setitem__("count", 0), severity="violation"),
    _ill(s2(), "S2 声明字段写了 null", "declaration_null",
         lambda s: s.artifact["declarations"].__setitem__("adjust", None)),
    _ill(s2(), "S2 复权口径枚举外", "declaration_enum",
         lambda s: (s.artifact["declarations"].__setitem__("adjust", "hfq"),
                    s.task["declared"].__setitem__("adjust", "hfq")),
         exclusive=True),

    # ---------------- S3 ----------------
    _ill(s3(), "S3 声明只读 close，日志显示还读了 open（.038 形态，2.3-c）", "undeclared_reads",
         lambda s: _set_log_fields(s, "open,close"), severity="violation"),
    _ill(s3(), "S3 声明只读 close，实际请求了 *（读全表也是超读）", "undeclared_reads",
         lambda s: _set_log_fields(s, "*"), severity="violation"),
    _ill(s3(), "S3 的 /bars 请求没传 fields（不传即畸形，探针不可检）", "fields_not_explicit",
         lambda s: s.log[0]["params"].pop("fields")),
    _ill(s3(), "S3 非有限值被静默替换", "nonfinite_silently_replaced",
         lambda s: s.artifact["payload"]["nonfinite"].__setitem__("replaced_count", 5), severity="violation"),
    _ill(s3(), "S3 用近似算子替代", "operator_approximated",
         lambda s: s.artifact["payload"]["approximated_operators"].append("ts_rank→rolling_rank"),
         severity="violation"),
    _ill(s3(), "S3 回看窗口未满就出值", "warmup_violation",
         lambda s: s.artifact["payload"]["warmup"].__setitem__("nonnull_before_warmup", 3), severity="violation"),
    _ill(s3(), "S3 常数输出没报警", "degeneracy_unreported",
         lambda s: s.artifact["payload"]["degeneracy"].update({"is_constant": True, "alert": False}),
         severity="violation"),

    # ---------------- S4 ----------------
    _ill(s4(), "S4 用 Newey–West 替代 block-bootstrap", "ci_method_not_block_bootstrap",
         lambda s: s.artifact["payload"]["ic_stats"].__setitem__("ci_method", "newey_west"), severity="violation"),
    _ill(s4(), "S4 声明 5 分位（与冻结标定冲突）", "calibration_conflict",
         lambda s: (s.artifact["declarations"].__setitem__("quantiles", 5),
                    s.task["declared"].__setitem__("quantiles", 5)), severity="violation"),
    _ill(s4(), "S4 IC 汇总缺 positive_ratio", "s4_ic_stats_incomplete",
         lambda s: s.artifact["payload"]["ic_stats"].pop("positive_ratio")),

    # ---------------- S5 ----------------
    _ill(s5(), "S5 fillna(0)：无数据的格子写成 flat（缺失伪装成主动空仓）", "missing_masquerading_as_signal",
         lambda s: (s.artifact["payload"]["signals"][2].__setitem__("value", FLAT),
                    s.artifact["payload"]["coverage"].update({"n_null": 0, "n_flat": 2})),
         severity="violation"),
    _ill(s5(), "S5 fillna(0)：无数据的格子写成 0.0", "missing_masquerading_as_signal",
         lambda s: (s.artifact["payload"]["signals"][2].__setitem__("value", 0.0),
                    s.artifact["payload"]["coverage"].update({"n_null": 0, "n_valued": 3})),
         severity="violation"),
    _ill(s5(), "S5 value_semantics 缺失（必填无默认）", "declaration_missing",
         lambda s: (s.artifact["declarations"].pop("value_semantics"))),
    _ill(s5(), "S5 声明 missing_policy=fill_zero", "missing_filled_as_zero",
         lambda s: (s.artifact["declarations"].__setitem__("missing_policy", "fill_zero"),
                    s.task["declared"].__setitem__("missing_policy", "fill_zero")), severity="violation"),
    _ill(s5(), "S5 rank 语义下写了 0", "zero_under_rank_semantics",
         lambda s: (s.artifact["declarations"].__setitem__("value_semantics", "rank"),
                    s.task["declared"].__setitem__("value_semantics", "rank"),
                    s.artifact["payload"]["signals"][0].__setitem__("value", 0))),
    _ill(s5(), "S5 自报 coverage 与内容不符", "s5_coverage_inconsistent",
         lambda s: s.artifact["payload"]["coverage"].__setitem__("n_null", 0)),

    # ---------------- S6 ----------------
    _ill(s6(), "S6 求解不收敛却静默沿用上期持仓", "optimizer_failure_silently_carried",
         lambda s: s.artifact["payload"]["targets"][0].update(
             {"solver_status": "not_converged", "positions": _positions(delta_zero=True)}),
         severity="violation"),
    _ill(s6(), "S6 现金占比留位字段缺失（N-26）", "s6_cash_ratio_reserved_missing",
         lambda s: s.artifact["payload"].pop("cash_ratio")),
    _ill(s6(), "S6 台账 delta 与 target−previous 不符", "s6_delta_inconsistent",
         lambda s: s.artifact["payload"]["targets"][0]["positions"][0].__setitem__("delta_weight", 0.5)),

    # ---------------- S7（2.3-a 三态在这里）----------------
    _ill(s7(), "S7 欠定任务上填了默认值 daily（静默补全，第五探针）", "silent_completion",
         lambda s: s.task["underdetermined"].append("rebalance_frequency") or
                   s.task["declared"].pop("rebalance_frequency"),
         severity="violation"),
    _ill(s7(), "S7 欠定任务上字段缺失（缺失 ≠ 标记）", "underdetermined_field_missing",
         lambda s: (s.task["underdetermined"].append("rebalance_frequency"),
                    s.task["declared"].pop("rebalance_frequency"),
                    s.artifact["declarations"].pop("rebalance_frequency"),
                    s.artifact["payload"].pop("rebalance_frequency")),
         exclusive=False),   # payload 回显也会响：声明没了，回显也对不上
    _ill(s7(), "S7 任务已声明，artifact 却标 unresolved", "declared_field_marked_unresolved",
         lambda s: (s.artifact["declarations"].__setitem__("first_rebalance_day", UNRESOLVED))),
    _ill(s7(), "S7 任务声明 daily，artifact 写 weekly（自行改口径）", "declaration_mismatch",
         lambda s: (s.artifact["declarations"].__setitem__("rebalance_frequency", "weekly"),
                    s.artifact["payload"].__setitem__("rebalance_frequency", "weekly")),
         severity="violation"),
    _ill(s7(), "S7 turnover 只记了一个", "turnover_single_recorded",
         lambda s: s.artifact["payload"]["metrics"].pop("turnover_two_way_mean")),
    _ill(s7(), "S7 复式记账不守恒", "ledger_not_conserved",
         lambda s: s.artifact["payload"]["ledger_check"].__setitem__("max_abs_residual", 0.5),
         severity="violation"),
    _ill(s7(), "S7 归因不守恒", "attribution_not_conserved",
         lambda s: s.artifact["payload"]["attribution"].__setitem__("total", 0.5), severity="violation"),
    _ill(s7(), "S7 持仓按原始股数记账（与契约 §5b 冲突）", "share_accounting_off_contract",
         lambda s: (s.artifact["declarations"].__setitem__("share_accounting", "raw_shares"),
                    s.task["declared"].__setitem__("share_accounting", "raw_shares")),
         severity="violation"),

    # ---------------- S8 ----------------
    _ill(s8(), "S8 事件链乱序（不可重放）", "s8_events_not_ordered",
         lambda s: s.artifact["payload"]["events"].reverse()),
    _ill(s8(), "S8 非法状态迁移", "s8_illegal_transition",
         lambda s: s.artifact["payload"]["state_transitions"].append({"from": "idle", "to": "filled"}),
         severity="violation"),
    _ill(s8(), "S8 自报越权 0 次，日志有 1 次", "overreach_count_mismatch",
         lambda s: s.artifact["payload"]["overreach"].__setitem__("denied_requests", 0)),
]


# ============================================================== scorer / 遥测

SCORER_VALID = {"schema_version": SCHEMA_VERSION, "task_id": TASK, "config_id": CFG, "arm": "strict",
                "seed": 0, "stage": "S7", "validity": "valid", "gate_failed": [],
                "correctness": {"exec": 1.0}, "effect": {"sharpe_net": 0.55, "in_band": 1.0}}
SCORER_INVALID = {**SCORER_VALID, "validity": "invalid", "gate_failed": ["underdetermined"],
                  "effect": None}

SCORER_VALID_ANCHOR_PENDING = {**SCORER_VALID, "effect": None, "effect_withheld_reason": "anchor_pending"}

SCORER_ILLEGAL: list[tuple[str, dict, str]] = [
    ("invalid 时效果分写了 0 而不是空", {**SCORER_INVALID, "effect": {"sharpe_net": 0.0}},
     "effect_score_on_invalid"),
    ("valid 却带 gate_failed", {**SCORER_VALID, "gate_failed": ["lookahead"]}, "valid_with_gate_failed"),
    ("invalid 却没说哪个探针失败", {**SCORER_INVALID, "gate_failed": []}, "invalid_without_gate"),
    ("gate_failed 里有未知探针", {**SCORER_INVALID, "gate_failed": ["made_up"]}, "gate_failed_malformed"),
    ("unobservable 与 gate_failed 重叠", {**SCORER_INVALID, "unobservable": ["underdetermined"]}, "unobservable_and_failed"),
    ("unobservable 含未知探针", {**SCORER_VALID, "unobservable": ["nope"]}, "unobservable_malformed"),
    ("版本未知", {**SCORER_VALID, "schema_version": "2.0"}, "unknown_schema_version"),
]

TELEMETRY_OK = {"schema_version": SCHEMA_VERSION, "run_id": "r1", "search_count": None,
                "trial_family": None, "cash_ratio_median": None, "tokens_in": 100, "tokens_out": 20}
TELEMETRY_ILLEGAL: list[tuple[str, dict, str]] = [
    ("预留字段 search_count 缺失", {k: v for k, v in TELEMETRY_OK.items() if k != "search_count"},
     "telemetry_reserved_missing"),
    ("search_count 为负", {**TELEMETRY_OK, "search_count": -1}, "search_count_type"),
    ("版本缺失", {k: v for k, v in TELEMETRY_OK.items() if k != "schema_version"}, "missing_schema_version"),
    ("版本是数字 1.0 而非字符串", {**TELEMETRY_OK, "schema_version": 1.0}, "unknown_schema_version"),
]
