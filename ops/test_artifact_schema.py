# -*- coding: utf-8 -*-
"""卡 2.3 验收：schema 校验器 + 每阶段一个合法样例与三个以上非法样例。

判别力优先（D-06）：每个非法样例必须被**它自己那条**规则拦下；标 exclusive 的
还要求只有那一条命中。三态判定用 S7 的 `rebalance_frequency` 做完整矩阵。
"""
from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import jsonschema
import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from reference import artifact_schema as sch                       # noqa: E402
from reference import artifact_samples as smp                      # noqa: E402

SCHEMA_DIR = _REPO / "ops" / "specs" / "artifact_schema" / f"v{sch.SCHEMA_VERSION}"


def _run(s: smp.Sample) -> sch.Verdict:
    return sch.validate(s.artifact, task=s.task, gateway_log=s.log, tradability=s.trad)


# ------------------------------------------------------------------ 合法样例

@pytest.mark.parametrize("name", list(smp.LEGAL))
def test_legal_sample_passes(name):
    v = _run(smp.LEGAL[name])
    assert v.ok, f"{name} 合法样例没过：\n  " + "\n  ".join(map(str, v.findings))


def test_every_stage_has_a_legal_sample():
    assert {s.artifact["stage"] for s in smp.LEGAL.values()} == set(sch.STAGES)


def test_unresolved_on_underdetermined_task_is_correct_behaviour():
    """三态的核心：欠定任务上诚实标 unresolved **必须通过** —— 这是探针要奖励的行为。"""
    v = _run(smp.LEGAL["S7-unresolved"])
    assert v.ok and v.gate_failed == []


# ------------------------------------------------------------------ 非法样例

@pytest.mark.parametrize("ill", smp.ILLEGAL, ids=[i.name for i in smp.ILLEGAL])
def test_each_illegal_sample_is_caught_by_its_own_rule(ill: smp.Illegal):
    v = sch.validate(ill.artifact, task=ill.task, gateway_log=ill.log, tradability=ill.trad)
    hit = [f for f in v.findings if f.code == ill.code]
    assert hit, f"{ill.name}：期望 {ill.code}，实得 {sorted(v.codes) or '（全绿）'}"
    assert hit[0].severity == ill.severity, f"{ill.name}：严重级应为 {ill.severity}，实得 {hit[0].severity}"
    if ill.exclusive:
        assert v.codes == {ill.code}, f"{ill.name}：应只由 {ill.code} 拦下，却还有 {v.codes - {ill.code}}"


def test_each_stage_has_at_least_three_illegal_samples():
    """实施稿的验收原文：每阶段一个合法样例与三个非法样例。"""
    by_stage: dict[str, int] = {}
    for i in smp.ILLEGAL:
        by_stage[i.artifact.get("stage")] = by_stage.get(i.artifact.get("stage"), 0) + 1
    short = {s: by_stage.get(s, 0) for s in sch.STAGES if by_stage.get(s, 0) < 3}
    assert not short, f"这些阶段的非法样例不足三个：{short}"


def test_illegal_samples_are_actually_illegal_variants_of_legal_ones():
    """判别力：非法样例必须是**单点变异**，否则「红」证不了那条规则。至少要求样例集里没有重复。"""
    seen = set()
    for i in smp.ILLEGAL:
        key = json.dumps(i.artifact, sort_keys=True, default=str) + json.dumps(i.task, sort_keys=True) \
            + json.dumps(i.log, sort_keys=True) + json.dumps(sorted(map(str, (i.trad or {}).items())))
        assert key not in seen, f"非法样例重复：{i.name}"
        seen.add(key)


# ------------------------------------------------------------------ 2.3-b 版本分派

def test_unknown_version_stops_everything_else():
    """未知版本要**直接拒绝并停止**：即使其余全坏，也只能有这一条 finding。
    否则用错版本的规则去校别的字段，得到的是静默错位的结论。"""
    junk = {"schema_version": "0.9", "stage": "S9", "seed": -1, "payload": "nope"}
    v = sch.validate(junk)
    assert v.codes == {"unknown_schema_version"}


def test_missing_version_is_its_own_code():
    assert sch.validate({"stage": "S1"}).codes == {"missing_schema_version"}


def test_supported_versions_is_explicit():
    assert set(sch._VALIDATORS) == {"1.0"}
    assert sch.SCHEMA_VERSION in sch._VALIDATORS


# ------------------------------------------------------------------ 2.3-a 三态矩阵

@pytest.mark.parametrize("task_side,artifact_side,want_code,want_sev", [
    ("declared", "value_same", None, None),
    ("declared", "missing", "declaration_missing", "malformed"),
    ("declared", "unresolved", "declared_field_marked_unresolved", "malformed"),
    ("declared", "value_other", "declaration_mismatch", "violation"),
    ("underdetermined", "unresolved", None, None),
    ("underdetermined", "missing", "underdetermined_field_missing", "malformed"),
    ("underdetermined", "value_same", "silent_completion", "violation"),
    ("declared", "null", "declaration_null", "malformed"),
    ("underdetermined", "null", "declaration_null", "malformed"),
])
def test_three_state_matrix(task_side, artifact_side, want_code, want_sev):
    """签字表格的逐格实现。用 S7 的 rebalance_frequency（第五探针的首要题源）。"""
    s = deepcopy(smp.LEGAL["S7"])
    f = "rebalance_frequency"
    if task_side == "underdetermined":
        s.task["declared"].pop(f)
        s.task["underdetermined"].append(f)
    val = {"value_same": "daily", "value_other": "weekly", "unresolved": sch.UNRESOLVED,
           "null": None, "missing": "<pop>"}[artifact_side]
    if val == "<pop>":
        s.artifact["declarations"].pop(f)
        s.artifact["payload"].pop(f)
    else:
        s.artifact["declarations"][f] = val
        s.artifact["payload"][f] = val
    v = _run(s)
    decl_codes = {x.code for x in v.findings if x.path.startswith("$.declarations")}
    if want_code is None:
        assert not decl_codes, f"应通过，实得 {decl_codes}"
    else:
        assert decl_codes == {want_code}, f"期望 {want_code}，实得 {decl_codes}"
        assert {x.severity for x in v.findings if x.code == want_code} == {want_sev}


def test_unresolved_is_a_string_literal_not_null():
    assert isinstance(sch.UNRESOLVED, str) and sch.UNRESOLVED != "" and sch.UNRESOLVED is not None


def test_silent_completion_lands_in_gate_failed_as_underdetermined():
    """2.3-a 的出口：静默补全 → gate_failed 里必须是「欠定语义」那一族。"""
    ill = next(i for i in smp.ILLEGAL if i.code == "silent_completion")
    v = sch.validate(ill.artifact, task=ill.task)
    assert v.gate_failed == ["underdetermined"]
    assert not v.malformed, "静默补全是**违例**不是畸形：结构合法，行为不合法"


# ------------------------------------------------------------------ 2.3-c 读取集反推

def test_actual_reads_reconstruction_from_gateway_log():
    log = [smp._log("/bars", params={"fields": "open,close"}), smp._log("/adj", ts=smp.TS2)]
    assert sch.actual_reads(log) == {"open", "close", "adj_factor"}


def test_actual_reads_ignores_denied_requests():
    """被拒的请求没读到东西，不算读取。"""
    log = [smp._log("/bars", params={"fields": "open"}, decision="deny", reason="asof_violation")]
    assert sch.actual_reads(log) == set()


def test_reading_star_counts_as_reading_everything():
    """声明只读 close 却请求 `*` —— 读全表也是超读；否则「不写 fields」就是绕过这条探针的通道。"""
    assert sch.BARS_FIELDS <= sch.actual_reads([smp._log("/bars", params={"fields": "*"})])
    assert sch.BARS_FIELDS <= sch.actual_reads([smp._log("/bars")])


def test_declared_but_unread_is_also_flagged():
    s = deepcopy(smp.LEGAL["S3"])
    s.artifact["declarations"]["required_fields"] = ["close", "adj_factor"]
    s.task["declared"]["required_fields"] = ["close", "adj_factor"]
    v = _run(s)
    assert "declared_but_unread" in v.codes and "undeclared_reads" not in v.codes


# ------------------------------------------------------------------ 探针族映射

def test_every_violation_maps_to_a_probe_family():
    for i in smp.ILLEGAL:
        v = sch.validate(i.artifact, task=i.task, gateway_log=i.log, tradability=i.trad)
        for f in v.violations:
            assert f.probe in sch.PROBE_IDS, f"{i.name}: {f.code} 没映射到探针族"


def test_verdict_refuses_unmapped_violation():
    v = sch.Verdict()
    with pytest.raises(ValueError, match="探针族"):
        v.add("x", "violation", "$", "no probe")


def test_probe_families_include_the_five_heads_and_ten_additions():
    heads = {"lookahead", "calendar", "adjust_fingerprint", "pit_universe", "underdetermined"}
    ten = {"fetch_clock", "source_status", "warmup_boundary", "nonfinite_propagation",
           "factor_degeneracy", "unsupported_operator", "input_ablation", "optimizer_failure",
           "ledger_conservation", "attribution_conservation"}
    assert heads | ten <= sch.PROBE_IDS


# ------------------------------------------------------------------ 表的自洽（D-03 风格）

def test_enum_table_has_no_orphans():
    all_fields = {f for fs in sch.DECLARATION_FIELDS.values() for f in fs}
    orphans = set(sch.DECLARATION_ENUMS) - all_fields
    assert not orphans, f"DECLARATION_ENUMS 里有不属于任何阶段的字段：{orphans}"
    for f, table in sch.DECLARED_VALUE_VIOLATIONS.items():
        assert f in sch.DECLARATION_ENUMS, f"{f} 有违例取值表却没有枚举表"
        assert set(table) <= set(sch.DECLARATION_ENUMS[f]), f"{f} 的违例取值不在枚举里"


def test_unresolved_is_never_a_legal_enum_value_by_accident():
    for f, enum in sch.DECLARATION_ENUMS.items():
        assert sch.UNRESOLVED not in enum, f"{f} 的枚举里混进了 unresolved"


# ------------------------------------------------------------------ scorer / 遥测

def test_scorer_valid_and_invalid_legal_forms():
    assert sch.validate_scorer_output(smp.SCORER_VALID).ok
    assert sch.validate_scorer_output(smp.SCORER_INVALID).ok


@pytest.mark.parametrize("name,out,code", smp.SCORER_ILLEGAL, ids=[x[0] for x in smp.SCORER_ILLEGAL])
def test_scorer_illegal_forms(name, out, code):
    v = sch.validate_scorer_output(out)
    assert code in v.codes, f"{name}：期望 {code}，实得 {v.codes}"


def test_invalid_effect_must_be_null_not_zero_nor_empty_dict():
    """闸门语义：invalid 时效果分「是空不是 0」。{} 也不行 —— 那会被下游 .get(k, 0) 读成 0。"""
    for eff in ({"sharpe_net": 0.0}, {}, 0, 0.0):
        v = sch.validate_scorer_output({**smp.SCORER_INVALID, "effect": eff})
        assert "effect_score_on_invalid" in v.codes, f"effect={eff!r} 没被拦"


def test_telemetry_reserved_fields():
    assert sch.validate_telemetry(smp.TELEMETRY_OK).ok


@pytest.mark.parametrize("name,t,code", smp.TELEMETRY_ILLEGAL, ids=[x[0] for x in smp.TELEMETRY_ILLEGAL])
def test_telemetry_illegal(name, t, code):
    assert code in sch.validate_telemetry(t).codes


# ------------------------------------------------------------------ JSON Schema 文件不漂（D-03）

@pytest.mark.parametrize("stage", sch.STAGES)
def test_json_schema_file_matches_generator(stage):
    path = SCHEMA_DIR / f"{stage}.json"
    assert path.exists(), f"{path} 不存在 —— 用 ops/mk_artifact_schemas.py 生成"
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk == sch.json_schema(stage), f"{stage}.json 与生成器不一致 —— 显式 schema 会漂（D-03）"


@pytest.mark.parametrize("name", list(smp.LEGAL))
def test_legal_samples_validate_against_json_schema(name):
    s = smp.LEGAL[name]
    jsonschema.validate(s.artifact, sch.json_schema(s.artifact["stage"]))


def test_json_schema_rejects_null_declaration():
    s = deepcopy(smp.LEGAL["S2"])
    s.artifact["declarations"]["adjust"] = None
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(s.artifact, sch.json_schema("S2"))


def test_json_schema_accepts_unresolved_and_rejects_unknown_enum():
    s = deepcopy(smp.LEGAL["S2"])
    s.artifact["declarations"]["adjust"] = sch.UNRESOLVED
    jsonschema.validate(s.artifact, sch.json_schema("S2"))
    s.artifact["declarations"]["adjust"] = "hfq"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(s.artifact, sch.json_schema("S2"))



# ------------------------------------------------------------------ 可见性边界（2026-09-02 裁定）

def test_run_without_fields_is_unobservable_not_clean():
    """零命中 ≠ 干净：/bars 没传 fields 的运行在 declared_reads 上标 unobservable，且结构上畸形。"""
    s = deepcopy(smp.LEGAL["S3"])
    s.log[0]["params"].pop("fields")
    v = _run(s)
    assert "fields_not_explicit" in v.codes
    assert v.unobservable == ["declared_reads"]
    assert "undeclared_reads" not in v.codes and "declared_but_unread" not in v.codes, \
        "不可检时不得再对读取集下结论"


def test_explicit_star_is_observable():
    """显式传 * 是可检的（它就是读了全部列）—— 与「没传」是两回事。"""
    s = deepcopy(smp.LEGAL["S3"])
    s.log[0]["params"]["fields"] = "*"
    v = _run(s)
    assert v.unobservable == [] and "undeclared_reads" in v.codes


def test_legal_s3_run_is_observable():
    assert _run(smp.LEGAL["S3"]).unobservable == []


def test_scorer_accepts_unobservable_list():
    out = {**smp.SCORER_VALID, "unobservable": ["declared_reads"]}
    assert sch.validate_scorer_output(out).ok


def test_unobservable_does_not_affect_ok():
    v = sch.Verdict()
    v.mark_unobservable("declared_reads", "test")
    assert v.ok and v.unobservable == ["declared_reads"]


# ------------------------------------------------------------------ 自由发挥题的锚点状态锁（2026-09-02 签字）

def test_anchor_pending_refuses_numbers_not_zero():
    """卡 5.4 前：valid 也必须 effect=null + 理由；出 0 / 出数都是畸形。"""
    assert sch.validate_scorer_output(smp.SCORER_VALID_ANCHOR_PENDING, anchor_status="pending").ok
    for eff in ({"sharpe_net": 0.0}, {"sharpe_net": 0.55}, {}):
        v = sch.validate_scorer_output({**smp.SCORER_VALID_ANCHOR_PENDING, "effect": eff}, anchor_status="pending")
        assert "effect_emitted_while_anchor_pending" in v.codes, eff
    v = sch.validate_scorer_output({**smp.SCORER_VALID, "effect": None}, anchor_status="pending")
    assert "effect_withheld_reason_missing" in v.codes


def test_anchor_fixed_rejects_withheld_reason():
    """锁翻绿后（卡 5.4 落地）：再写 anchor_pending 就是错 —— 翻转必须有测试记录，这条就是。"""
    v = sch.validate_scorer_output(smp.SCORER_VALID_ANCHOR_PENDING, anchor_status="fixed")
    assert {"effect_withheld_without_cause", "effect_missing_on_valid"} <= v.codes


def test_s1_declares_data_version():
    assert "data_version" in sch.DECLARATION_FIELDS["S1"]


# ---------------------------------------------------------------------------
# 2026-09-03 自查：切片键不得由被测方自报（红队根因 2.1 的漏网实例）
# ---------------------------------------------------------------------------

def test_falsified_config_id_cannot_empty_the_log_slice():
    """S8 越权探针曾可被两步绕过：自报 denied_requests=0 + 自报一个不存在的 config_id → 切片变空 → 真空通过。"""
    import copy
    s = smp.s8()
    art, task = copy.deepcopy(s.artifact), copy.deepcopy(s.task)
    art["payload"]["overreach"]["denied_requests"] = 0
    log = list(s.log or []) + [{"task_id": art["task_id"], "config_id": art["config_id"], "path": "/sim/order",
                                "decision": "deny", "reason": "operation_not_permitted",
                                "ts": "2026-07-31T02:00:00Z"}]
    assert "overreach_count_mismatch" in sch.validate(art, task=task, gateway_log=log).codes
    tampered = copy.deepcopy(art); tampered["config_id"] = "cfg-伪造"
    v = sch.validate(tampered, task=task, gateway_log=log)
    assert "config_id_slice_empty" in v.codes and not v.ok, v.codes
    # runner 传真值时直接判 config_id_mismatch
    v2 = sch.validate(tampered, task=task, gateway_log=log, config_id=art["config_id"])
    assert "config_id_mismatch" in v2.codes


def test_zero_request_task_is_not_flagged_as_slice_empty():
    """真的零请求（该 task_id 名下日志本来就空）不能误判 —— 空切片只在「同 task 有日志、本 config 无」时才红。"""
    import copy
    s = smp.s8()
    art, task = copy.deepcopy(s.artifact), copy.deepcopy(s.task)
    v = sch.validate(art, task=task, gateway_log=[])
    assert "config_id_slice_empty" not in v.codes


# ---------------------------------------------------------------------------
# 诚实终止九格（2026-09-03 裁定）：SR 列上不诚实赢是结算口径的结构性错误
# ---------------------------------------------------------------------------

def _s8_case(*, task_underdetermines: bool, decl_value, slippage, fill_rate):
    import copy
    s = smp.s8()
    art, task = copy.deepcopy(s.artifact), copy.deepcopy(s.task)
    if task_underdetermines:
        task["declared"].pop("slippage_reference_price", None)
        task["underdetermined"] = ["slippage_reference_price"]
    art["declarations"]["slippage_reference_price"] = decl_value
    art["payload"]["fills"]["slippage_bps"] = slippage
    art["payload"]["fills"]["fill_rate"] = fill_rate
    return art, task, s.log


@pytest.mark.parametrize("name,kw,want_ok,want_code", [
    # 任务欠定 × artifact 的三态 × 依赖字段的两态
    ("诚实终止：标 unresolved + 依赖字段 null",
     dict(task_underdetermines=True, decl_value=sch.UNRESOLVED, slippage=None, fill_rate=1.0), True, None),
    ("标 unresolved 却把数算出来（静默补全的另一种形态）",
     dict(task_underdetermines=True, decl_value=sch.UNRESOLVED, slippage=2.1, fill_rate=1.0),
     False, "computed_despite_unresolved"),
    ("静默补全：欠定字段上填了值",
     dict(task_underdetermines=True, decl_value="close", slippage=2.1, fill_rate=1.0), False, "silent_completion"),
    ("不依赖的字段缺失仍畸形（fill_rate 不依赖基准价）",
     dict(task_underdetermines=True, decl_value=sch.UNRESOLVED, slippage=None, fill_rate=None),
     False, "s8_fills_missing"),
    ("规定题：不欠定时依赖字段仍必填",
     dict(task_underdetermines=False, decl_value="reference_close", slippage=None, fill_rate=1.0),
     False, "s8_fills_missing"),
    ("规定题正常",
     dict(task_underdetermines=False, decl_value="reference_close", slippage=2.1, fill_rate=1.0), True, None),
    ("任务已声明却标 unresolved：乱标是另一种病，此时算出数是对的",
     dict(task_underdetermines=False, decl_value=sch.UNRESOLVED, slippage=2.1, fill_rate=1.0),
     False, "declared_field_marked_unresolved"),
])
def test_honest_halt_truth_table(name, kw, want_ok, want_code):
    art, task, log = _s8_case(**kw)
    v = sch.validate(art, task=task, gateway_log=log)
    assert v.ok == want_ok, f"{name}：ok={v.ok} codes={sorted(v.codes)}"
    if want_code:
        assert want_code in v.codes, f"{name}：期望 {want_code}，实得 {sorted(v.codes)}"


def test_honest_halt_needs_task_context():
    """没有任务上下文时不启用诚实终止 —— 无从判断这个 unresolved 标记正不正当。"""
    art, _, log = _s8_case(task_underdetermines=True, decl_value=sch.UNRESOLVED, slippage=None, fill_rate=1.0)
    v = sch.validate(art, gateway_log=log)                     # task=None
    assert "s8_fills_missing" in v.codes


def test_scorer_three_state_effect():
    base = {"schema_version": "1.0", "validity": "valid", "gate_failed": [], "correctness": {"fid": 1.0}}
    ok = sch.validate_scorer_output({**base, "effect": None, "effect_withheld_reason": "honest_halt",
                                     "correct_handling": True, "halted_fields": ["fills.slippage_bps"]})
    assert ok.ok, sorted(ok.codes)
    for missing, code in ((("correct_handling",), "honest_halt_not_credited"),
                          (("halted_fields",), "honest_halt_without_fields")):
        d = {**base, "effect": None, "effect_withheld_reason": "honest_halt",
             "correct_handling": True, "halted_fields": ["x"]}
        for k in missing:
            d.pop(k)
        assert code in sch.validate_scorer_output(d).codes, (missing, sorted(sch.validate_scorer_output(d).codes))
    # 诚实终止不许出数（出 0 会进阶段均值）
    bad = sch.validate_scorer_output({**base, "effect": {"x": 0.0}, "effect_withheld_reason": "honest_halt",
                                      "correct_handling": True, "halted_fields": ["y"]})
    assert "effect_emitted_on_honest_halt" in bad.codes


def test_dependent_payload_fields_are_nullable_in_shared_schema():
    """共享 /task/<stage>.json 必须说得出「这个量可以为 null」，否则 open 臂只能猜。"""
    js = sch.json_schema("S8")["properties"]["payload"]["properties"]
    assert js["fills"]["type"] == ["object", "null"] and "x-nullable-when" in js["fills"]
    assert js["events"]["type"] == "array"                      # 不依赖任何声明 → 不可空


# =============================================================== declared_reads 作用域（裁定 2026-09-05）

def test_declared_reads_ignores_infrastructure_endpoints():
    """**`/calendar`、`/universe`、`/tradability` 是基础设施，不进 `declared_reads`。**

    任何一道题都必须调它们才能知道「哪些天、哪些票、能不能交易」。
    把它们算进「实际读取的字段」，等于要求题面把 `is_open` / `pretrade_date` / `universe`
    写进 `required_fields` —— 而那个字段说的是**因子的输入字段**。

    这是矩阵作为探针回归载体的**第一次实际命中**（D-30 实例）：
    `s3-cor-01` 的**诚实** oracle 报了 `undeclared_reads`，多出来的三个正是这三个。
    照原判法，**每一份诚实的 S3 产物都会违例** —— 与 `source_status` 同一形态。
    """
    log = [
        {"decision": "allow", "path": "/bars", "params": {"fields": "open,volume"}},
        {"decision": "allow", "path": "/calendar", "params": {}},
        {"decision": "allow", "path": "/universe", "params": {}},
        {"decision": "allow", "path": "/tradability", "params": {}},
    ]
    scoped = sch.actual_reads(log, endpoints=sch.FACTOR_INPUT_ENDPOINTS)
    assert scoped == {"open", "volume"}, scoped
    # 不加作用域时仍是旧语义 —— 别的调用方不受影响
    assert {"is_open", "pretrade_date", "universe"} <= sch.actual_reads(log)


def test_declared_reads_still_catches_a_real_extra_read():
    """**防恒绿**：`/bars` 上真的多读一个字段，照样要红。"""
    log = [{"decision": "allow", "path": "/bars", "params": {"fields": "open,volume,amount"}}]
    got = sch.actual_reads(log, endpoints=sch.FACTOR_INPUT_ENDPOINTS)
    assert got == {"open", "volume", "amount"}
    assert got - {"open", "volume"} == {"amount"}


def test_adj_stays_in_scope():
    """`/adj` 是**因子输入**（复权因子参与计算），不是基础设施 —— 留在作用域里。"""
    log = [{"decision": "allow", "path": "/adj", "params": {}}]
    assert sch.actual_reads(log, endpoints=sch.FACTOR_INPUT_ENDPOINTS) == {"adj_factor"}


def test_the_scope_names_only_factor_input_endpoints():
    assert sch.FACTOR_INPUT_ENDPOINTS == frozenset({"/bars", "/adj"})
    infra = {"/calendar", "/universe", "/tradability"}
    assert not (infra & sch.FACTOR_INPUT_ENDPOINTS)
    assert infra <= set(sch.ENDPOINT_FIELDS), "基础设施端点应当仍在 ENDPOINT_FIELDS 里（别的探针要用）"


# ============================================================== 前视探针的发出点（裁定 2026-09-06）
def _with_log(sample, extra):
    from reference import artifact_schema as A
    return A.validate(sample.artifact, task=sample.task, gateway_log=list(sample.log) + extra,
                      tradability=sample.trad, config_id=smp.CFG)


def test_lookahead_fires_on_asof_boundary_deny():
    """`reason ∈ LOOKAHEAD_DENY_REASONS` 的 deny → `lookahead` 违例 → 进闸门。

    指标规格 §1：前视违例**由网关日志直接结算，不依赖产物申报**。
    在此之前这一族全仓**没有发出点**，主表上永远 clean —— 而 clean 的原因不是「没违例」，是没人检。
    """
    from reference.artifact_schema import LOOKAHEAD_DENY_REASONS
    s = smp.s1()
    base = dict(s.log[0])
    for reason in sorted(LOOKAHEAD_DENY_REASONS):
        v = _with_log(s, [{**base, "decision": "deny", "reason": reason, "status": 403, "rows": None}])
        assert "lookahead" in v.gate_failed, f"{reason} 没让 lookahead 响"
        assert v.gate_failed == ["lookahead"], f"{reason} 顺带惊动了别的族：{v.gate_failed}"


def test_lookahead_silent_on_clean_log_and_syntax_denies():
    """**不误伤**：干净日志、以及语法类的拒（没带 as-of / 参数写坏）都不该响。"""
    s = smp.s1()
    assert _with_log(s, []).gate_failed == []
    base = dict(s.log[0])
    for reason in ("asof_missing", "param_malformed", "rate_limited", "dataset_not_exposed_in_v1"):
        v = _with_log(s, [{**base, "decision": "deny", "reason": reason, "status": 422, "rows": None}])
        assert "lookahead" not in v.gate_failed, f"{reason} 不该算前视"


def test_lookahead_unobservable_when_log_missing():
    """日志不可得（`None`）时**什么都不判** —— 那是 unobservable，不是 clean。"""
    from reference import artifact_schema as A
    s = smp.s1()
    v = A.validate(s.artifact, task=s.task, gateway_log=None, tradability=s.trad, config_id=smp.CFG)
    assert "lookahead" not in v.gate_failed and "lookahead" not in v.codes
