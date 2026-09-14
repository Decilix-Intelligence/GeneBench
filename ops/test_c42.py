# -*- coding: utf-8 -*-
"""卡 4.2 A 档验收：采集器五件（`failure_modes` / `harvest` / `origin` / `identity` /
`visibility` / `emission`）。零外部依赖、纯夹具。**A 档不过，B 档不开工。**

夹具尽量取 `reference/artifact_samples.py` 里**录制的真实产物**，不手写理想夹具 ——
手写夹具会把 parser 测成永绿（它只会遇到我们想象得到的形状）。
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

from runner.c42 import emission as EM
from runner.c42 import failure_modes as FM
from runner.c42 import harvest as HV
from runner.c42 import identity as ID
from runner.c42 import origin as OR
from runner.c42 import scorer_io as SI
from runner.c42 import upstream_pins as UP
from runner.c42 import visibility as VIS

# 本文件跑在 f01（数据面），因此**可以** import reference —— 同源断言要它。
# 被测的 c42 模块本身不许 import 它，那条由 test_inject.py 的 T11 盯。
_REPO_C42 = Path(__file__).resolve().parents[1] / "runner" / "c42"

from reference import artifact_samples as SAMP
from reference import artifact_schema as SCH


# =============================================================== A-01 / A-02 / A-03

def test_a01_taxonomy_total_four_identities():
    FM.assert_taxonomy_total()
    assert set(FM.RUN_STATUS_TO_SR) == set(FM.RUN_STATUSES)
    assert set(FM.RUN_STATUS_TO_SR.values()) == set(FM.SR_BUCKETS), "空桶是死桶"


@pytest.mark.parametrize("mutate,want", [
    (lambda: FM.RUN_STATUS_TO_SR.pop("ok"), "不是全映射"),
    (lambda: FM.RUN_STATUS_TO_SR.update({"ok": "made_up"}), "越界"),
    (lambda: FM.RUN_STATUS_TO_SR.update({"leaked": "scorable"}), "空桶"),
])
def test_a01_identities_are_discriminating(monkeypatch, mutate, want):
    """突变必须落在**门保护的对象**上（本轮纪律：不能落在门的参数上）。
    这里改的是表本身，不是 `assert_taxonomy_total` 的入参 —— 它没有入参。"""
    monkeypatch.setattr(FM, "RUN_STATUS_TO_SR", dict(FM.RUN_STATUS_TO_SR))
    mutate()
    with pytest.raises(FM.TaxonomyError, match=want):
        FM.assert_taxonomy_total()


def test_a02_rank_is_a_bijection_and_leaked_dominates():
    ranks = [FM.rank(s) for s in FM.RUN_STATUSES]
    assert sorted(ranks) == list(range(len(FM.RUN_STATUSES)))
    assert FM.worst(*FM.RUN_STATUSES) == "leaked", "泄漏必须压一切"
    assert FM.worst("ok", "leaked") == "leaked"
    assert FM.worst("timeout", "harness_error") == "harness_error", \
        "我们自己坏了导致的超时不能记在 agent 头上"
    assert FM.worst("malformed", "violation") == "malformed", "结构不成立则行为判定不成立"
    with pytest.raises(FM.TaxonomyError):
        FM.rank("made_up")


def test_a03_sr_denominator_excludes_only_harness():
    every = list(FM.RUN_STATUSES)
    assert FM.sr_denominator(every) == len(every) - 1, "只有 harness_error 出分母"
    assert FM.sr_denominator(["leaked"]) == 1, \
        "把 leaked 移出分母等于让一次泄漏事故顺带抬高 SR"
    assert FM.sr_denominator(["harness_error"]) == 0
    assert FM.EXCLUDED_FROM_DENOMINATOR == ("unscorable_harness",)


def test_a03_negative_one_more_excluded_bucket_must_go_red(monkeypatch):
    monkeypatch.setattr(FM, "EXCLUDED_FROM_DENOMINATOR", ("unscorable_harness", "leaked"))
    assert FM.sr_denominator(list(FM.RUN_STATUSES)) != len(FM.RUN_STATUSES) - 1, \
        "多排除一个桶而分母不变 —— 这条断言本身在空转"


def test_a03_every_harness_fault_maps_only_to_harness_error():
    assert {FM.status_for_fault(f) for f in FM.HARNESS_FAULTS} == {"harness_error"}
    with pytest.raises(FM.TaxonomyError):
        FM.status_for_fault("made_up")


# =============================================================== A-04 顺序

def _recorder_steps(calls, *, classify="ok", boom=None):
    def mk(name):
        def step(ctx):
            calls.append(name)
            if boom == name:
                raise RuntimeError(f"{name} 炸了")
            return classify if name == "classify" else name
        return step
    return HV.Steps(**{n: mk(n) for n in HV.HARVEST_ORDER})


def test_a04_harvest_order_is_asserted_not_agreed():
    """期望序列是**本文件里的字面量** —— 从 harvest.py import 就成了同义反复。"""
    calls: list[str] = []
    ctx = HV.run_pipeline(_recorder_steps(calls), {})
    assert calls == [
        "load_bundle", "check_bundle", "render", "lint", "preflight", "up", "run",
        "harvest", "down", "canary_scan", "parse", "classify", "record_strict",
        "to_scorer_input",
    ]
    assert calls.index("harvest") < calls.index("down"), \
        "down -v 删卷；产物随卷消失后与 agent 真没写产物不可分"
    assert calls.index("lint") < calls.index("up")
    assert calls.index("preflight") < calls.index("up")
    assert calls.index("canary_scan") < calls.index("parse")
    assert calls.index("classify") < calls.index("record_strict")
    assert ctx["scorer_input"] == "to_scorer_input"


def test_a04_to_scorer_input_is_conditional():
    for status in ("malformed", "no_artifact", "timeout", "leaked", "violation"):
        calls: list[str] = []
        ctx = HV.run_pipeline(_recorder_steps(calls, classify=status), {})
        assert ctx["scorer_input"] is None, f"{status} 仍然产出了 scorer_input"
        assert "to_scorer_input" not in calls


def test_a04_down_runs_even_when_a_step_after_up_blows_up():
    """超时路径（NP-08）：`run` 炸了，`down` 仍须执行。"""
    calls: list[str] = []
    with pytest.raises(RuntimeError, match="run 炸了"):
        HV.run_pipeline(_recorder_steps(calls, boom="run"), {})
    assert "down" in calls, "down 没跑 —— 下一个 run 会撞上残留容器"


def test_a04_preflight_fault_still_reaches_record_strict():
    """§2.1 的病灶：前置步骤 raise 出去 = 那题**连一行都不写进库**，分母悄悄变小。"""
    calls: list[str] = []
    ctx = HV.run_pipeline(_recorder_steps(calls, boom="preflight"), {})
    assert ctx["run_status"] == "harness_error"
    assert ctx["harness_fault"] == "provider_pin"
    assert "record_strict" in calls, "harness 故障也必须落库，否则那题变成「不存在」"
    assert "up" not in calls and "run" not in calls
    assert ctx["scorer_input"] is None


def test_a04_classify_cannot_overwrite_a_harness_error():
    calls: list[str] = []
    ctx = HV.run_pipeline(_recorder_steps(calls, boom="up", classify="timeout"), {})
    assert ctx["run_status"] == "harness_error", \
        "我们自己没起来导致的超时被记成了 agent 的 timeout"


def test_a04_order_constant_matches_the_dataclass():
    assert HV.HARVEST_ORDER == tuple(HV.Steps.__dataclass_fields__), \
        "顺序表与 Steps 的字段漂了 —— 会有一步永远不被调用而没人报错"


# =============================================================== A-05 挂载外产物

def test_a05_framework_output_outside_task_mount_raises():
    HV.assert_outputs_under_mount(["/task/out", "/task/artifact.json"])
    for bad in (["/root/.rdagent"], ["/tmp/results"], ["./results"], ["/taskfoo/x"]):
        with pytest.raises(HV.FrameworkOutputOutsideTaskMount):
            HV.assert_outputs_under_mount(bad)


def test_a05_collect_refuses_to_return_empty_harvest_silently(tmp_path):
    rd = tmp_path / "run"
    (rd / "work").mkdir(parents=True)
    (rd / "log").mkdir()
    h = HV.collect(rd, stage="S3", arm="open")
    assert h.status_hint == "no_artifact" and h.empty, \
        "空 harvest 必须有名字：no_artifact 或挂载外 raise，二者可分"
    with pytest.raises(HV.FrameworkOutputOutsideTaskMount):
        HV.collect(rd, stage="S3", arm="open", declared_outputs=["/root/.rdagent"])


@pytest.mark.parametrize("blob,want", [
    (b"", "artifact_empty"),
    (b"   \n", "artifact_empty"),
    (b'{"a": 1', "artifact_truncated"),
    (b"not json at all", "artifact_not_json"),
    (b'\xff\xfe{"a":1}', "artifact_not_utf8"),
    (b"[1,2,3]", "artifact_not_json"),
])
def test_a05_artifact_shape_hints(tmp_path, blob, want):
    rd = tmp_path / "run"
    (rd / "work").mkdir(parents=True)
    (rd / "work" / "artifact.json").write_bytes(blob)
    assert HV.collect(rd, stage="S1", arm="open").status_hint == want


def test_visibility_is_wired_into_the_harvester(tmp_path):
    """`visibility()` 此前全仓库只有测试在调 —— 门有了、门后没人。"""
    rd = tmp_path / "run"
    (rd / "work").mkdir(parents=True)
    (rd / "log").mkdir()
    h = HV.collect(rd, stage="S1", arm="open", task_id="t", config_id="c",
                   started_at="2026-09-04T00:00:00+00:00",
                   finished_at="2026-09-04T00:01:00+00:00")
    assert h.gateway_log is None, "日志不可得必须是 None，写 [] 会让交叉核真空通过"
    assert [p for p, _ in h.unobservable] == list(VIS.LOG_DEPENDENT_PROBES)
    bare = HV.collect(rd, stage="S1", arm="open")
    assert [p for p, _ in bare.unobservable] == list(VIS.LOG_DEPENDENT_PROBES), \
        "连身份与时间窗都没传时也必须标不可检，不能默默当成「核过了」"
    src = (_REPO_C42 / "harvest.py").read_text(encoding="utf-8")
    assert "VIS.visibility(" in src


def test_a05_produced_allowlist_is_what_run_loop_gets(tmp_path):
    """卡 4.3 退出后那次复核的允许集来自这里（裁定：定义产出物的人定义允许集）。"""
    rd = tmp_path / "run"
    (rd / "work" / "out").mkdir(parents=True)
    (rd / "log").mkdir()
    (rd / "work" / "artifact.json").write_text('{"x":1}', encoding="utf-8")
    (rd / "work" / "out" / "emission.jsonl").write_text("", encoding="utf-8")
    (rd / "log" / "egress.jsonl").write_text('{"event":"ready"}\n', encoding="utf-8")
    (rd / "work" / "sneaky.py").write_text("print(1)", encoding="utf-8")
    h = HV.collect(rd, stage="S3", arm="open")
    assert h.unexpected == ["work/sneaky.py"], h.unexpected
    assert h.egress_starts == 1
    assert h.emissions_path is not None


def test_a05_allowlist_prefix_has_a_boundary():
    assert HV._rel_allowed("work/out/emission.jsonl", ("work/out/",))
    assert not HV._rel_allowed("work/out_evil/x", ("work/out/",)), \
        "前缀判据缺 / 会把 work/out_evil/ 一并放行"


# =============================================================== A-06..A-08 origin

def test_a06_declarations_only_accept_agent_bytes():
    OR.check_declaration_origins({"$.declarations.adjust": OR.Source.agent_artifact})
    for bad in (OR.Source.framework_config, OR.Source.framework_output,
                OR.Source.shim_emission, OR.Source.harness_inferred):
        with pytest.raises(OR.OriginError):
            OR.check_declaration_origins({"$.declarations.adjust": bad})


def test_a07_absent_writes_no_key():
    vals = {"adjust": "post", "calendar_id": "SSE"}
    org = {"$.declarations.adjust": OR.Source.agent_artifact,
           "$.declarations.calendar_id": OR.Source.absent}
    out = OR.transcribe_declarations(vals, org)
    assert out == {"adjust": "post"}
    assert "calendar_id" not in out, (
        "写一个键进去就同时毁掉 underdetermined_field_missing 与 silent_completion "
        "两个结论 —— 那两个必须由校验器给出")


def test_a07_harness_inferred_always_raises():
    with pytest.raises(OR.OriginError, match="harness_inferred"):
        OR.assert_no_inference({"$.payload.x": OR.Source.harness_inferred})
    OR.assert_no_inference({"$.payload.x": OR.Source.agent_artifact})


def test_a07_harness_never_authors_unresolved():
    agent = {"sell_rule": OR.UNRESOLVED}
    OR.assert_not_authored_unresolved(
        agent, {"$.declarations.sell_rule": OR.Source.agent_artifact})
    with pytest.raises(OR.OriginError, match="unresolved"):
        OR.assert_not_authored_unresolved(
            agent, {"$.declarations.sell_rule": OR.Source.framework_config})
    with pytest.raises(OR.OriginError):
        OR.assert_not_authored_unresolved(agent, {})       # 没登记来源 = harness_inferred


def test_a08_framework_config_only_reaches_provenance():
    prov = OR.config_provenance({"lookback": 20}, config_path="rdagent/conf.yaml")
    assert list(prov) == ["$.provenance.framework_config.rdagent/conf.yaml.lookback"]
    assert all(not p.startswith("$.declarations.") for p in prov)
    with pytest.raises(OR.OriginError):
        OR.transcribe_declarations(
            {"lookback": 20}, {"$.declarations.lookback": OR.Source.framework_config})


# =============================================================== A-09 / A-10 交叉核表

def _required_leaves(shape: dict) -> set[str]:
    want = set()
    for top, spec in shape.items():
        subs = [k for k in (spec.get("required") or []) if spec.get("type") == "object"]
        want |= {f"{top}.{k}" for k in subs} if subs else {top}
    return want


def test_a09_check_table_covers_every_required_leaf():
    """同源断言：镜像表与冻结校验器的必填叶子对齐（缺一即红）。"""
    for stage, shape in SCH.PAYLOAD_SHAPE.items():
        have = set(OR.PAYLOAD_CHECK[stage])
        want = _required_leaves(shape)
        assert want <= have, f"PAYLOAD_CHECK[{stage}] 缺 {sorted(want - have)}"


def test_a09_profile_leaves_covered():
    for prof, spec in SCH.PAYLOAD_PROFILES.items():
        have = set(OR.PAYLOAD_CHECK_PROFILE[prof])
        want = _required_leaves(spec)
        assert want <= have, f"档位 {prof} 缺 {sorted(want - have)}"


def test_a09_missing_leaf_raises():
    with pytest.raises(OR.OriginError, match="不在 PAYLOAD_CHECK"):
        OR.check_of("S3", "brand_new_leaf")


# ---- 新语义的四把锁 ----

@pytest.mark.parametrize("stage,leaf", [
    ("S3", "nonfinite.replaced_count"),      # S 叶子
    ("S3", "values_ref.rows"),               # R 叶子
    ("S3", "degeneracy.alert"),              # none 叶子
    ("S8", "state_transitions"),
])
def test_lock1_payload_values_only_come_from_the_agent(stage, leaf):
    """**第一把锁**：payload 的值只能是 agent 写的字节 —— 对**每一个**叶子都一样，
    包括有 shim 证据的那些。shim 的读数是证据，不是字段的值。"""
    for good in (OR.Source.agent_artifact, OR.Source.framework_output):
        OR.check_payload_source(stage, leaf, good)
    for bad in (OR.Source.shim_emission, OR.Source.framework_config,
                OR.Source.harness_inferred, OR.Source.absent):
        with pytest.raises(OR.OriginError):
            OR.check_payload_source(stage, leaf, bad)


def test_lock1_transcribe_payload_refuses_harness_authored_values():
    ok = OR.transcribe_payload({"nonfinite.replaced_count": 3},
                               {"$.payload.nonfinite.replaced_count": OR.Source.agent_artifact},
                               stage="S3")
    assert ok == {"nonfinite": {"replaced_count": 3}}
    with pytest.raises(OR.OriginError, match="payload 的值只能是 agent 写的字节"):
        OR.transcribe_payload({"nonfinite.replaced_count": 3},
                              {"$.payload.nonfinite.replaced_count": OR.Source.shim_emission},
                              stage="S3")


def test_lock2_cross_check_never_touches_payload():
    """**第二把锁**：payload 以只读视图进，旁路记录是**另一个**字典。"""
    payload = {"nonfinite": {"replaced_count": 0, "inf_count": 0, "nan_count": 0}}
    snapshot = json.dumps(payload, sort_keys=True)
    out = OR.cross_check_all("S3", payload, {"nonfinite.replaced_count": 3})
    assert json.dumps(payload, sort_keys=True) == snapshot, "cross_check 改写了 payload"
    blk = OR.harness_checks_block(out)
    assert blk["nonfinite.replaced_count"]["payload"] == 0
    assert blk["nonfinite.replaced_count"]["harness"] == 3
    assert blk is not payload


_PROBE_VALUES = {"exact": (1, 2), "abs": (1.0, 2.0), "rel": (1.0, 2.0),
                 "set": (["a"], ["b"])}


def _probe_pair(chk):
    if chk.tol.kind != "proj":
        return _PROBE_VALUES[chk.tol.kind]
    a = [{f: "x" for f in chk.tol.fields}]
    b = [{f: "y" for f in chk.tol.fields}]
    return a, b


def _leaves_with_evidence():
    """(stage, profile, leaf, check)。档位表的 stage 走 PROFILE_STAGE，不靠名字推。"""
    out = []
    for key, tbl in OR._all_tables():
        stage, profile = ((key, None) if key in OR.PAYLOAD_CHECK
                          else (OR.PROFILE_STAGE[key], key))
        for leaf, c in tbl.items():
            if c.source is not OR.CrossCheck.none:
                out.append((stage, profile, leaf, c))
    return out


@pytest.mark.parametrize("stage,profile,leaf,chk", _leaves_with_evidence(),
                         ids=[f"{p or s}.{l}" for s, p, l, _ in _leaves_with_evidence()])
def test_lock3_cross_check_can_actually_disagree(stage, profile, leaf, chk):
    """**第三把锁 —— 用户点名的那条突变**：把重算值写进 payload 之后，
    两侧永远相等，本条测试当场变红。

    判据落在**门保护的对象**（两个不同的值）上，不落在门的参数上。
    """
    a, b = _probe_pair(chk)
    same = OR.cross_check(stage, leaf, a, a, profile=profile)
    diff = OR.cross_check(stage, leaf, a, b, profile=profile)
    assert same.status == "agree", f"{stage}.{leaf} 相同值判成了 {same.status}"
    assert diff.status == "mismatch", (
        f"{stage}.{leaf} 不同值没判 mismatch —— 若实现把 harness 值写回 payload，"
        f"这一条就是它的落点")
    assert diff.is_finding and OR.findings({leaf: diff})


def test_lock4_evidence_enum_has_no_harness_member():
    """**第四把锁**：交叉核的另一侧永远不是我们写的值。"""
    assert not any(e.value.startswith(("harness", "computed", "recomputed"))
                   for e in OR.Evidence)
    OR.assert_check_targets_are_not_ours()


def test_lock4_gate_is_discriminating(monkeypatch):
    """R 配 gateway_log（不是从 agent 的文件重算）必须被拦下。"""
    tbl = {k: dict(v) for k, v in OR.PAYLOAD_CHECK.items()}
    tbl["S3"]["values_ref.rows"] = OR.Check(OR.CrossCheck.recompute,
                                            OR.Evidence.gateway_log, "随便写点什么")
    monkeypatch.setattr(OR, "PAYLOAD_CHECK", tbl)
    with pytest.raises(OR.OriginError, match="只允许"):
        OR.assert_check_targets_are_not_ours()


def test_lock4_evidence_source_without_basis_is_rejected(monkeypatch):
    tbl = {k: dict(v) for k, v in OR.PAYLOAD_CHECK.items()}
    tbl["S3"]["values_ref.rows"] = OR.Check(OR.CrossCheck.recompute, OR.Evidence.agent_file, "")
    monkeypatch.setattr(OR, "PAYLOAD_CHECK", tbl)
    with pytest.raises(OR.OriginError, match="没写 basis"):
        OR.assert_check_targets_are_not_ours()


# ---- 「证据不可得」不得冒充「一致」（F7 的形态） ----

def test_unverified_is_not_agree():
    o = OR.cross_check("S3", "nonfinite.replaced_count", 0, None)
    assert o.status == "unverified" and not o.is_finding
    assert "不可得" in o.detail, "拿不到证据却说一致，是 F7 那条的另一种写法"


def test_absent_leaf_is_left_to_the_validator():
    o = OR.cross_check("S3", "nonfinite.replaced_count", OR._MISSING, 3)
    assert o.status == "absent" and "harness 不补" in o.detail


def test_cross_check_all_rejects_out_of_table_evidence():
    with pytest.raises(OR.OriginError, match="表外叶子"):
        OR.cross_check_all("S3", {}, {"made_up.leaf": 1})


# ---- 未验证自报清单：主表脚注的来源 ----

def test_a10_unverified_self_reports_are_enumerated():
    """N-44 之前：S7 的 12 个叶子全在「未验证自报」里（题面写着 n_days 等于收益率
    序列长度，却从没要求交出那个序列）。N-44 之后序列进了题面，它们全部转 R。"""
    s7 = OR.unverified_self_reports("S7")
    assert s7 == [], f"S7 现在应当没有无人核的叶子，实为 {s7}"
    for leaf in ("metrics.sharpe_net", "n_days", "ledger_check.max_abs_residual"):
        assert OR.check_of("S7", leaf).source is OR.CrossCheck.recompute, leaf
    # 判别力：把序列从契约里拿掉，这些量必须**退回**无人核 —— 否则这条测试
    # 证明的只是「表里现在写着 R」，而不是「R 有据可依」。
    s3 = OR.unverified_self_reports("S3")
    assert "factor_id" in s3 and "warmup.lookback" in s3, (
        "agent 的表述与参数选择本来就无人核 —— 清单不该是空的，"
        "空清单说明这条统计本身失效了")
    assert OR.check_of("S3", "degeneracy.alert").source is OR.CrossCheck.none
    assert OR.check_of("S3", "degeneracy.alert").checked_by, \
        "agent 的报警行为由校验器的 factor_degeneracy 探针核"


def test_a10_none_source_must_declare_who_checks_it_or_be_listed():
    for key, tbl in OR._all_tables():
        stage, profile = ((key, None) if key in OR.PAYLOAD_CHECK
                          else (OR.PROFILE_STAGE[key], key))
        listed = set(OR.unverified_self_reports(stage, profile))
        for leaf, c in tbl.items():
            if c.source is OR.CrossCheck.none and not c.checked_by:
                assert leaf in listed, f"{key}.{leaf} 没人核却没进未验证清单"


def test_checked_by_names_a_check_that_actually_exists():
    """`checked_by` 里写一个**不存在**的检查，等于把一个无人核的量从
    「未验证自报」清单里抹掉 —— F7 那条的又一种写法。

    红队复核实测抓到过一次：`S3.warmup.lookback` 曾写着 `validator:回显声明`，
    而校验器里没有这条检查。
    """
    src = (Path(SCH.__file__)).read_text(encoding="utf-8")
    codes = set(re.findall(r"""v\.add\(\s*[fr]?["']([a-z0-9_]+)""", src))
    assert len(codes) > 100, "没抓到 code —— 正则漂了，这条测试会真空通过"
    known = codes | set(SCH.PROBE_IDS)
    for key, tbl in OR._all_tables():
        for leaf, c in tbl.items():
            for token in filter(None, c.checked_by.split(",")):
                who, _, name = token.partition(":")
                assert who in ("validator", "scorer"), f"{key}.{leaf} 的 {token!r} 没写清是谁核"
                if who == "validator":
                    assert name in known, (
                        f"{key}.{leaf} 说由 validator:{name} 核，"
                        f"而冻结校验器里没有这个 code / probe")


def test_proj_beats_set_on_dict_lists():
    """dict 的列表用 SET 比会抛 —— 先前的实现把它静默判成 mismatch，
    于是每次运行都多一条假 finding。"""
    with pytest.raises(OR.OriginError, match="不可集合化"):
        OR._agree([{"a": 1}], [{"a": 1}], OR.SET)
    ok, _ = OR._agree([{"a": 1, "b": 9}], [{"a": 1, "b": 8}], OR.PROJ("a"))
    assert ok, "投影之外的字段不该参与比对"
    with pytest.raises(OR.OriginError, match="PROJ 比法要 dict"):
        OR._agree(["x"], ["x"], OR.PROJ("a"))


def test_produced_files_mirror_the_schema_contract():
    """N-44 同源断言：采集器的允许集必须与题面的产出文件契约一致。

    先前这里写死 `work/panel.parquet` / `work/values.parquet` 并**是错的** ——
    那两个路径只在 gold 的 solve.py 里，题面从没说过。现在它由 schema 定义，
    这条测试盯着两份别漂。
    """
    for stage, specs in SCH.PAYLOAD_FILES.items():
        want = tuple(f["path"].replace("/task/", "work/") for f in specs)
        assert HV.PRODUCED_BY_STAGE.get(stage) == want, \
            f"{stage}: 采集器 {HV.PRODUCED_BY_STAGE.get(stage)} vs 契约 {want}"
    assert set(HV.PRODUCED_BY_STAGE) == set(SCH.PAYLOAD_FILES), \
        "采集器多认或少认了阶段"
    for stage in SCH.PAYLOAD_FILES:
        assert stage not in HV.PRODUCED_DATA_GLOBS, \
            f"{stage} 的路径题面已固定，还留着 glob 就是白白放宽封闭判据"


def test_payload_files_paths_are_container_paths():
    """题面里一律 `/task/…`。写 `work/` 会被 render 的 E8 当场判红
    （容器里 work/ 就挂在 /task）—— schema 在 import 期先拦一道。"""
    for stage, specs in SCH.PAYLOAD_FILES.items():
        for f in specs:
            assert f["path"].startswith("/task/") and "/task/work/" not in f["path"], \
                f"{stage}: {f['path']}"
            assert set(f["sort"]) <= set(f["columns"]), f"{stage}: 排序列不在列清单里"


def test_output_files_phrase_is_machine_generated_and_two_arm_identical():
    """两臂同给 —— 值机器生成，只差引导语。手写的那份必然会漂。"""
    from genetask import packager as PKG
    from genetask import render as R
    for stage in ("S2", "S3", "S7"):
        v = PKG._output_files_phrase(stage)
        assert v and "/task/" in v and "work/" not in v, stage
        assert "output_files" in R.FIXED_SLOTS[stage], stage
    for stage in ("S1", "S4", "S5", "S6", "S8"):
        assert PKG._output_files_phrase(stage) == "", f"{stage} 没有产出文件契约"
        assert "output_files" not in R.FIXED_SLOTS[stage], \
            f"{stage} 加了这个槽会得到一个空的固定槽 —— 比没有更坏"


def test_gold_writes_the_contracted_file_through_one_function_body():
    """§9 的「一处实现」：五个 S7 gold 都走 `files_io.write_contracted`，
    不许各写一遍 `to_parquet` —— 各抄一遍的下场是它们慢慢漂开，
    而漂开表现为「同一道题两次 gold 的 sha 不同」，没有任何东西报错。"""
    import pathlib
    root = pathlib.Path(SCH.__file__).resolve().parents[1] / "genetask" / "templates" / "S7"
    tpls = [d for d in sorted(root.iterdir()) if d.is_dir() and d.name != "base"]
    assert len(tpls) == 5, [d.name for d in tpls]
    for d in tpls:
        src = (d / "solve.py").read_text(encoding="utf-8")
        assert "write_contracted(daily" in src, d.name
        assert "daily.to_parquet" not in src, f"{d.name} 自己写了一遍 to_parquet"


def test_contracted_writer_and_harness_recompute_agree(tmp_path):
    """写端与读端必须对得上：gold 按契约写、harness 按同一契约重算，
    两边的 sha 与统计量必须一致。对不上就说明规范形只在一侧生效。"""
    import pandas as pd
    from reference import files_io as FIO
    from runner.c42.adapters.rdagent_q import adapter as RD
    df = pd.DataFrame({"code": ["b", "a", "a"],
                       "date": ["2026-01-02", "2026-01-02", "2026-01-01"],
                       "value": [1.0, 2.0, 3.0]})
    p = FIO.write_contracted(df, "S3", tmp_path)
    assert p.name == "values.parquet"
    back = pd.read_parquet(p)
    assert list(back.columns) == ["date", "code", "value"], "列序没按契约"
    assert back["date"].tolist() == sorted(back["date"].tolist()), "没按契约排序"
    assert FIO.sha256_of(p) == RD.values_evidence(p)["values_ref.sha256"], \
        "写端与读端的字节摘要口径不同 —— 那 values_ref.sha256 就没有可比性"


def test_file_contract_mirror_matches_the_frozen_schema():
    """执行面的镜像与冻结件必须逐字段相等 —— 抄一份而没人盯着，本仓已栽过三次。"""
    from genetask import file_contract as FC
    assert set(FC.FILE_SPECS) == set(SCH.PAYLOAD_FILES)
    for stage, specs in SCH.PAYLOAD_FILES.items():
        assert FC.FILE_SPECS[stage] == specs, stage


def test_only_one_writer_body_and_it_is_reference_free():
    """写端有两个（gold 在 f01、适配器在 f02），函数体只能有一份 ——
    而它必须零 reference 依赖，否则执行面只能自己再抄一遍。"""
    import ast
    import pathlib
    src = pathlib.Path(SCH.__file__).resolve().parents[1] / "genetask" / "file_contract.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        mods = ([a.name for a in node.names] if isinstance(node, ast.Import)
                else [node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
        for m in mods:
            assert m.split(".")[0] != "reference", f"写入函数体 import 了 {m}"
    ref_io = pathlib.Path(SCH.__file__).parent / "files_io.py"
    body = ref_io.read_text(encoding="utf-8")
    assert "to_parquet" not in body and "to_csv" not in body, \
        "数据面的封装自己又写了一遍落盘 —— 那就是第二份函数体"


def test_writer_refuses_a_stage_without_a_file_contract():
    from reference import files_io as FIO
    with pytest.raises(FIO.FileContractError, match="没有产出文件契约"):
        FIO.spec_for("S1")


def test_tolerance_mirrors_match_reference():
    assert OR.LEDGER_TOL == SCH.LEDGER_TOL
    assert OR.W_TOL == SCH.W_TOL


# =============================================================== A-11 / A-12 身份

def _truth() -> ID.RunnerTruth:
    return ID.RunnerTruth(task_id="t-real", config_id="cfg-a", arm="open", run_id="r1")


def test_a11_three_way_identity_check():
    ok = {"task_id": "t-real", "config_id": "cfg-a", "arm": "open"}
    assert ID.check_identity(ok, _truth()) == []
    assert ID.status_for(ok, _truth()) is None
    for k, v in (("task_id", "t-fake"), ("config_id", "cfg-b"), ("arm", "strict")):
        bad = {**ok, k: v}
        assert ID.status_for(bad, _truth()) == "identity_mismatch", k
        assert FM.sr_bucket("identity_mismatch") == "unscorable_agent", \
            "记 harness 等于给「产物在伪装」开一条不进分母的通道"


def test_a11_identity_check_cannot_rewrite_the_envelope():
    env = {"task_id": "t-fake", "config_id": "cfg-a", "arm": "open"}
    before = json.dumps(env, sort_keys=True)
    ID.check_identity(env, _truth())
    assert json.dumps(env, sort_keys=True) == before, \
        "改写是最省事的做法，也是把「产物在伪装」变成「产物正常」的那一步"


def test_a11_runner_truth_refuses_to_fall_back_to_self_report():
    with pytest.raises(ID.IdentityError, match="GENEBENCH_CONFIG_ID"):
        ID.RunnerTruth.from_env({"GENEBENCH_TASK_ID": "t", "GENEBENCH_ARM": "open"})
    t = ID.RunnerTruth.from_env({"GENEBENCH_TASK_ID": "t", "GENEBENCH_ARM": "open",
                                 "GENEBENCH_CONFIG_ID": "c", "GENEBENCH_RUN_ID": "r"})
    assert (t.task_id, t.config_id, t.arm, t.run_id) == ("t", "c", "open", "r")


def test_a12_recorded_assertion_bypassing_identity_makes_probes_vacuum():
    """记录性断言：绕过三核直接 validate 时，切片按**自报值**走，
    `declared_reads` 这族**整体静默通过**。这条不是在测我们的代码，是在钉住那个事实。"""
    log = [{"task_id": "t-real", "config_id": "cfg-a", "path": "/bars",
            "params": {"fields": "close"}, "decision": "allow", "rows": 8,
            "ts": "2026-07-31T02:00:00.000+00:00"}]
    fake = {"task_id": "t-fake", "config_id": "cfg-a"}
    assert SCH._log_slice(log, fake) == []
    assert SCH.actual_reads(SCH._log_slice(log, fake)) == set()
    real = {"task_id": "t-real", "config_id": "cfg-a"}
    assert SCH.actual_reads(SCH._log_slice(log, real)) != set(), \
        "对照支为空 —— 上面那条断言就不是「被伪装骗过」，而是夹具本身没数据"


# =============================================================== A-13 / A-14 可见性

def _entry(tid, cid, ts, path="/bars"):
    return {"task_id": tid, "config_id": cid, "ts": ts, "path": path,
            "params": {"fields": "close"}, "decision": "allow", "rows": 3}


def test_a13_three_states_none_is_not_empty_list(tmp_path):
    missing = tmp_path / "nope.jsonl"
    assert VIS.load_gateway_log(missing) is None, \
        "返回 [] 会让 declared_reads / fetch_clock 这些交叉核真空通过"
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    assert VIS.load_gateway_log(empty) == [], "可得但零请求 ≠ 不可得"


def test_a13_none_and_empty_take_different_branches(tmp_path):
    assert VIS.slice_for_run(None, task_id="t", config_id="c",
                             started_at="2026-07-31T00:00:00+00:00",
                             finished_at="2026-07-31T01:00:00+00:00") is None
    assert VIS.slice_for_run([], task_id="t", config_id="c",
                             started_at="2026-07-31T00:00:00+00:00",
                             finished_at="2026-07-31T01:00:00+00:00") == []


def test_a13_cross_host_pending_marks_probes_unobservable(tmp_path):
    log, un = VIS.visibility(tmp_path / "x.jsonl", task_id="t", config_id="c",
                             started_at="2026-07-31T00:00:00+00:00",
                             finished_at="2026-07-31T01:00:00+00:00")
    assert log is None and [p for p, _ in un] == list(VIS.LOG_DEPENDENT_PROBES)
    v = SCH.Verdict()
    for probe, why in un:
        v.mark_unobservable(probe, why)        # 探针名必须是 PROBE_IDS 里的真名
    assert sorted(v.unobservable) == sorted(VIS.LOG_DEPENDENT_PROBES)


def test_a14_three_way_slice_excludes_the_previous_run():
    """NP-11：同一 task 两次 run 的日志拼在一起，第二次不得含第一次的条目。"""
    log = [_entry("t1", "cfg-a", "2026-07-31T01:00:00.000+00:00"),      # run 1
           _entry("t1", "cfg-a", "2026-07-31T03:00:00.000+00:00")]      # run 2
    two = VIS.slice_for_run(log, task_id="t1", config_id="cfg-a",
                            started_at="2026-07-31T02:30:00+00:00",
                            finished_at="2026-07-31T03:30:00+00:00")
    assert [e["ts"] for e in two] == ["2026-07-31T03:00:00.000+00:00"]
    assert SCH._log_slice(log, {"task_id": "t1", "config_id": "cfg-a"}) == log, \
        "对照：冻结校验器的两维切片会把上一次 run 的条目一并算进来 —— 这正是补第三维的理由"


def test_a14_window_is_closed_and_required():
    log = [_entry("t1", "cfg-a", "2026-07-31T02:30:00.000+00:00")]
    assert len(VIS.slice_for_run(log, task_id="t1", config_id="cfg-a",
                                 started_at="2026-07-31T02:30:00+00:00",
                                 finished_at="2026-07-31T02:30:00+00:00")) == 1, \
        "开区间会丢掉恰好落在边界那一毫秒的请求"
    with pytest.raises(VIS.VisibilityError, match="时间窗"):
        VIS.slice_for_run(log, task_id="t1", config_id="cfg-a",
                          started_at="", finished_at="2026-07-31T03:00:00+00:00")


def test_a13_log_dependent_probes_are_real_probe_ids():
    assert set(VIS.LOG_DEPENDENT_PROBES) <= SCH.PROBE_IDS, "镜像表漂了"


# =============================================================== A-15 / A-16 发射（证据侧）

def _s3_with(nonfinite):
    s = SAMP.s3()
    a = copy.deepcopy(s.artifact)
    if nonfinite is None:
        a["payload"].pop("nonfinite")
    else:
        a["payload"]["nonfinite"] = nonfinite
    return a, s


def test_a15_no_shim_means_unverified_not_zero():
    """没装 shim ≠ 「测过且干净」。旧实现在这里拼一个 {0,0,0} 进 payload —— 那是替代。"""
    assert EM.nonfinite_replaced_count(None) is None
    assert EM.harness_values(None, stage="S3")["nonfinite.replaced_count"] is None
    assert not hasattr(EM, "nonfinite_payload"), \
        "拼 payload 的函数还在 —— 它是「重算即替代」在本仓的唯一实例"
    o = OR.cross_check("S3", "nonfinite.replaced_count", 0, None)
    assert o.status == "unverified"


def test_a15_missing_key_is_the_validator_s_call():
    """agent 没写 nonfinite 键 → 卡 2.3 报 s3_nonfinite_missing。harness 一个键都不补。"""
    a, s = _s3_with(None)
    codes = [f.code for f in SCH.validate(a, task=s.task, gateway_log=s.log).findings]
    assert codes == ["s3_nonfinite_missing"], codes


def test_a16_three_hooks_cross_check_the_agent_s_own_report(tmp_path):
    path = tmp_path / "out" / "emission.jsonl"
    with EM.Shim(path) as shim:
        for _ in range(3):
            shim.emit("nonfinite_replace", column="close", count=1)
    hv = EM.harness_values(EM.parse_emissions(path), stage="S3")
    assert hv["nonfinite.replaced_count"] == 3

    # (a) agent 如实自报 3 → 旁路一致，且校验器对**它自己报的** 3 亮闸门
    honest, s = _s3_with({"inf_count": 0, "nan_count": 12, "replaced_count": 3})
    assert OR.cross_check("S3", "nonfinite.replaced_count", 3,
                          hv["nonfinite.replaced_count"]).status == "agree"
    v = SCH.validate(honest, task=s.task, gateway_log=s.log)
    assert v.gate_failed == ["nonfinite_propagation"] and not v.malformed

    # (b) agent 报 0 而 shim 记了 3 → **隐瞒**，旁路 mismatch；
    #     而校验器看不出来（它只有 agent 自报的那一份）——这正是旁路存在的理由
    liar, s2 = _s3_with({"inf_count": 0, "nan_count": 12, "replaced_count": 0})
    assert OR.cross_check("S3", "nonfinite.replaced_count", 0,
                          hv["nonfinite.replaced_count"]).status == "mismatch"
    v2 = SCH.validate(liar, task=s2.task, gateway_log=s2.log)
    assert v2.ok and not v2.gate_failed, "校验器对隐瞒无感 —— 所以必须有 shim 旁路"


def test_a16_emission_three_states(tmp_path):
    assert EM.parse_emissions(tmp_path / "nope.jsonl") is None, "没装 shim"
    p = tmp_path / "e.jsonl"
    p.write_text("", encoding="utf-8")
    assert EM.parse_emissions(p) == [], "装了但没触发 —— 与没装是相反的结论"
    assert EM.approximated_operators(None) is None
    assert EM.approximated_operators([]) == []
    assert EM.nonfinite_replaced_count([]) == 0, "装了且零次替换是有意义的零"


def test_a16_unknown_emission_kind_raises(tmp_path):
    p = tmp_path / "e.jsonl"
    p.write_text(json.dumps({"kind": "made_up"}) + "\n", encoding="utf-8")
    with pytest.raises(EM.EmissionError, match="未知发射类型"):
        EM.parse_emissions(p)
    with pytest.raises(EM.EmissionError):
        EM.Shim(tmp_path / "x.jsonl").emit("made_up")


# =============================================================== A-22 / A-23 出口纪律与三桩

_STUB_TASK = {
    "task_id": "s3-cor-01", "stage": "S3", "as_of": "2026-07-31",
    "declared": {"required_fields": ["close"], "lookback": 20, "eval_frequency": "daily",
                 "operator_semantics": {"ts_rank": "pct_0_1"}, "param_order": ["window"],
                 "nonfinite_policy": "propagate", "warmup_policy": "null_until_full"},
    "underdetermined": ["nonfinite_policy"],
}


def _stub_verdict(behavior):
    from genetask import packager as PKG
    a = PKG.null_artifact(_STUB_TASK, behavior)
    tk = {"task_id": _STUB_TASK["task_id"], "stage": "S3",
          "declared": {k: v for k, v in _STUB_TASK["declared"].items()
                       if k not in _STUB_TASK["underdetermined"]},
          "underdetermined": list(_STUB_TASK["underdetermined"])}
    return a, SCH.validate(a, task=tk)


def test_a23_empty_stub():
    """§18.2 口径修正：`empty` 连 declarations 键都没有，校验器停在更外层。
    综合稿写的「必须报 underdetermined_field_missing」是错的 —— 按**实测 codes** 写验收。"""
    _, v = _stub_verdict("empty")
    assert sorted({f.code for f in v.findings}) == ["declarations_missing"]
    assert v.malformed and not v.gate_failed
    assert FM.sr_bucket("malformed") == "malformed"
    assert SI.to_scorer_input(run_status="malformed", artifact={}, gate_failed=[]) is None


def test_a23_default_fill_stub_trips_the_fifth_probe():
    _, v = _stub_verdict("default_fill")
    codes = {f.code for f in v.findings}
    assert "silent_completion" in codes, "静默补全没被抓到 —— 第五探针的正例"
    assert v.gate_failed == ["underdetermined"]


def test_a23_third_stub_covers_underdetermined_field_missing():
    """第三桩存在的唯一理由：`empty` 覆盖不到这个 code，§4 规则 (b) 因此没有正例。"""
    _, v = _stub_verdict("default_fill_minus_probe")
    codes = {f.code for f in v.findings}
    assert "underdetermined_field_missing" in codes
    assert "silent_completion" not in codes, "键删掉了就不是静默补全 —— 两个 code 必须可分"
    assert not v.gate_failed


def test_a22_exit_discipline_non_ok_returns_none():
    for st in FM.RUN_STATUSES:
        if st == "ok":
            continue
        assert SI.to_scorer_input(run_status=st, artifact={}, gate_failed=[]) is None, st
    got = SI.to_scorer_input(run_status="ok", artifact={"stage": "S3"}, gate_failed=[])
    assert got is not None and got["gate_failed"] == []


def test_a22_fabricated_gate_for_a_structural_failure_raises():
    """NP-21。判据从分类表推：没有可读产物的桶里，校验器根本没跑过。"""
    for st in ("no_artifact", "timeout", "leaked", "harness_error", "identity_mismatch"):
        with pytest.raises(SI.ExitDisciplineError, match="伪造闸门"):
            SI.to_scorer_input(run_status=st, artifact=None, gate_failed=["lookahead"])
    # 对照：malformed 的运行校验器**跑过**，它的闸门是真的 —— 不许连这个一起拦
    assert SI.to_scorer_input(run_status="malformed", artifact={},
                              gate_failed=["underdetermined"]) is None


def test_a22_no_verdict_buckets_track_the_taxonomy(monkeypatch):
    monkeypatch.setattr(FM, "SR_BUCKETS", FM.SR_BUCKETS + ("brand_new",))
    with pytest.raises(SI.ExitDisciplineError, match="分类表变了"):
        SI._assert_buckets_known()


def test_a22_gate_json_must_fail_the_scorer_schema():
    """`gate.json` 是**半成品**，它进不了主表这件事要由校验器说，不由约定说。"""
    g = SI.gate_only(gate_failed=["underdetermined"])
    v = SCH.validate_scorer_output(g, anchor_status="pending")
    assert "correctness_missing" in {f.code for f in v.findings}, \
        [f.code for f in v.findings]


def test_a22_anchor_pending_state_lock():
    """卡 5.4 落地时这条要**翻转**，翻转必须留记录（同 N-33 做法）。"""
    g = SI.gate_only(gate_failed=[], anchor_status="pending")
    assert g["effect"] is None and g["effect_withheld_reason"] == SI.ANCHOR_PENDING
    fixed = {**g}
    fixed.pop("effect_withheld_reason")
    fixed.pop("effect")
    fixed["correctness"] = {"score": 1.0}
    v = SCH.validate_scorer_output(fixed, anchor_status="fixed")
    assert "effect_missing_on_valid" in {f.code for f in v.findings}, \
        [f.code for f in v.findings]


def test_a22_anchor_reason_mirror_matches_reference():
    assert SI.ANCHOR_PENDING in SCH.EFFECT_WITHHELD_REASONS


# =============================================================== §10 上游钉死

def test_pins_are_bytes_not_names():
    """**钉的是字节，不是名字。** 三种合法的钉法各有其真实性：
    git commit（内容寻址）、PyPI 的 sha256、npm 的 integrity
    （`sha512-<base64>` —— **那才是 npm 装包时真正校验的东西**，硬转成 hex 反而离真相远）。"""
    UP.assert_pins_wellformed()
    for key, pin in UP.PINS.items():
        pinned = (bool(re.fullmatch(r"[0-9a-f]{40}", pin.commit))
                  or bool(re.fullmatch(r"[0-9a-f]{64}", pin.dist_sha256))
                  or pin.dist_integrity.startswith(("sha512-", "sha256-")))
        assert pinned, f"{key} 什么都没钉住"
        assert pin.commit or pin.commit_absent_reason, \
            f"{key} 空 commit 且没写理由 —— 整条断言退化成「有这个仓库就行」"


def test_pin_shape_fields_are_measured_not_empty():
    """§10：「不许凭记忆填」。三项已在 f02 的真容器里实测填好
    （`ops/run_f02_adapter_smoke.sh` 每次跑都重核一遍）。
    **也不许填空元组充数** —— `all(x in got for x in ())` 恒真，那是空检查。"""
    for key, pin in UP.PINS.items():
        if pin.kind == "harness":
            # 通用 harness **不做 §10 适配层**（裁定 2026-09-04）：镜像 + 调用命令。
            # 它没有我们 import 的符号，硬填 required_attrs 只会编出一份 ——
            # 那比没有更坏（空检查恒真）。核的是版本命令。
            assert pin.version_cmd, key
            assert pin.required_attrs is None, \
                f"{key} 是 harness 却填了 required_attrs —— 那是编出来的"
            with pytest.raises(UP.PinError, match="harness 不是 adapter"):
                UP.assert_upstream_shape(object(), key)
            continue
        for f in ("required_attrs", "required_files", "required_state_keys"):
            got = getattr(pin, f)
            assert got, f"{key}.{f} 是 None 或空元组 —— 未实测或空检查"
        for spec in pin.required_attrs:
            assert ":" in spec, f"{key}: {spec!r} 要写成 `模块:属性`"


def test_pin_refuses_unmeasured_shape():
    """判别力：把形状抹掉，`assert_upstream_shape` 必须拒。"""
    import dataclasses
    blank = dataclasses.replace(UP.PINS["rdagent_q"], required_attrs=None)
    with pytest.raises(UP.PinError, match="实测"):
        UP.assert_upstream_shape(object(), "rdagent_q", pin=blank)


def test_adapters_write_only_under_the_task_mount():
    """§3.3：产物落在 `/task` 之外，`down -v` 之后就没了 —— 表现为 no_artifact，
    与 agent 真没写产物**不可分**。两个框架的默认路径全在外面（实测），必须全改。"""
    from runner.c42 import harvest as HV
    from runner.c42.adapters.rdagent_q import adapter as RD
    from runner.c42.adapters.tradingagents import adapter as TA
    for ad in (RD.RDAgentQAdapter(), TA.TradingAgentsAdapter()):
        HV.assert_outputs_under_mount(ad.declared_outputs())
    # 上游默认值（实测）必须被这道门拦下
    for bad in ("/git_ignore_folder/RD-Agent_workspace", "/pickle_cache",
                "git_ignore_folder/factor_implementation_source_data", "./results"):
        with pytest.raises(HV.FrameworkOutputOutsideTaskMount):
            HV.assert_outputs_under_mount([bad])


def test_native_scan_follows_the_import_closure(tmp_path, monkeypatch):
    """**实测教训（2026-09-04）**：第一版扫描器只看工具模块自己的 import，
    而上游工具写的是 `from tradingagents.dataflows.yfinance import ...` ——
    顶层是 `tradingagents` 不是 `yfinance`。于是它对**完全未替换**的十五个原生工具
    判了「干净」：一道恒绿的门，而它本来要证明的正是「替换成功了」。"""
    import sys as _sys
    import types
    pkg = types.ModuleType("fakefw")
    pkg.__path__ = [str(tmp_path)]
    inner = types.ModuleType("fakefw.data")
    tool_mod = types.ModuleType("fakefw.tools")
    (tmp_path / "data.py").write_text("import yfinance\n", encoding="utf-8")
    (tmp_path / "tools.py").write_text("from fakefw.data import x\n", encoding="utf-8")
    inner.__file__ = str(tmp_path / "data.py")
    tool_mod.__file__ = str(tmp_path / "tools.py")
    monkeypatch.setitem(_sys.modules, "fakefw", pkg)
    monkeypatch.setitem(_sys.modules, "fakefw.data", inner)
    monkeypatch.setitem(_sys.modules, "fakefw.tools", tool_mod)
    from runner.c42.adapters.tradingagents import adapter as TA
    TA._reachable_modules.cache_clear()
    reach = TA._reachable_modules(tool_mod)
    assert "yfinance" in reach, \
        "闭包没走到隔一跳的原生模块 —— 这正是那道恒绿的门的形态"


class _FakeInterface:
    """上游 `dataflows/interface.py` 的最小替身：一张 vendor 表 + 类目表。"""

    def __init__(self):
        self.TOOLS_CATEGORIES = {"core_stock_apis": {"tools": ["get_stock_data"]},
                                 "news_data": {"tools": ["get_news"]}}
        self.VENDOR_METHODS = {"get_stock_data": {"yfinance": lambda *a, **k: "native"},
                               "get_news": {"yfinance": lambda *a, **k: "native"}}
        self.VENDOR_LIST = ["yfinance"]


def test_vendor_table_replaced_wholesale_not_configured():
    """§11.2：**整表**换掉，不是改配置。

    上游注释写着「配置的 vendor 列表就是调用链」，但 `"default"` sentinel
    用的是**全部可用 vendor** —— 配置一丢就回落到 yfinance。
    """
    from runner.c42.adapters.tradingagents import gateway_tools as GT
    fake = _FakeInterface()
    with pytest.raises(GT.ReplacementError, match="还有原生实现"):
        GT.assert_only_gateway_vendor(fake)          # 非空证明
    cfg = {}
    GT.install(fake, cfg)
    GT.assert_only_gateway_vendor(fake)
    assert set(cfg["data_vendors"].values()) == {GT.VENDOR}
    assert fake.VENDOR_LIST == [GT.VENDOR], "原生 vendor 还留在 VENDOR_LIST 里"
    fake.VENDOR_METHODS["get_news"]["yfinance"] = lambda *a, **k: "native"
    with pytest.raises(GT.ReplacementError, match="可用 vendor"):
        GT.assert_only_gateway_vendor(fake)


def test_uncovered_upstream_method_is_refused():
    """上游多一个方法而我们没覆盖 —— 那个方法会留着原生实现，必须抛。"""
    from runner.c42.adapters.tradingagents import gateway_tools as GT
    with pytest.raises(GT.ReplacementError, match="没覆盖的方法"):
        GT.build_vendor_table(["get_stock_data", "get_brand_new_thing"])


def test_pit_guard_fails_closed_and_records_hits(monkeypatch):
    """整体替换把上游自己那层日期防护删掉了（N-52）——
    替换层必须自己有一层，而且 **fail-closed**：拿不到日期就拒。"""
    from runner.c42.adapters.tradingagents import gateway_tools as GT
    monkeypatch.setenv("GENEBENCH_AS_OF", "2026-07-31")
    GT.reset_pit_hits()
    assert GT._pit("2026-07-30") == "2026-07-30"
    assert len(GT.pit_hits()) == 1, "守卫要留痕 —— 否则「一次都没调用」看不出来"
    with pytest.raises(GT.ReplacementError, match=r"\[PIT\]"):
        GT._pit("2026-08-01")
    with pytest.raises(GT.ReplacementError, match="fail-closed"):
        GT._pit(None)
    monkeypatch.delenv("GENEBENCH_AS_OF")
    with pytest.raises(GT.ReplacementError, match="GENEBENCH_AS_OF"):
        GT._pit("2026-07-30")


def test_no_source_methods_say_so_explicitly():
    """网关答不出的那些**不留空、不编** —— `[NO_DATA]` 让「这个环境没有这类数据」
    在产物里可见。返回空串会让它看起来像「查了、没有」。"""
    from runner.c42.adapters.tradingagents import gateway_tools as GT
    assert GT.NO_DATA.startswith("[NO_DATA]")
    assert len(GT.NO_SOURCE) == 9
    impl = GT.build_vendor_table(["get_news"])["get_news"]
    assert impl().startswith("[NO_DATA]")
    # N-58①：`/fundamentals` 不发放给 v1 的任何一道题 —— 适配器也不许接它。
    # 只摘题面一头会把我们自己造成的诱导记进越权率。
    assert "fundamentals" not in GT.SERVED, "适配器把 v1 不发放的端点接回来了"
    assert "get_fundamentals" in GT.NO_SOURCE
    assert GT.build_vendor_table(["get_fundamentals"])["get_fundamentals"]() \
        .startswith("[NO_DATA]")


def test_v1_endpoint_slot_is_generated_per_stage_and_withholds_fundamentals():
    """判据是「agent **看不到**即不存在越权」，不是「调了返 403」——
    后者会把一次我们自己造成的诱导记成被测方的越权率。"""
    from genetask import packager as PKG
    for stage in ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"):
        eps = PKG.stage_endpoints(stage)
        assert "/fundamentals" not in eps, stage
        assert set(PKG.V1_DATA_ENDPOINTS) <= set(eps)
        assert (set(PKG.SIM_ENDPOINTS) <= set(eps)) == (stage == "S8"), stage
    import unittest.mock as M
    with M.patch.object(PKG, "V1_DATA_ENDPOINTS",
                        PKG.V1_DATA_ENDPOINTS + ("/fundamentals",)):
        with pytest.raises(ValueError, match="不发放"):
            PKG.stage_endpoints("S1")


def test_endpoint_slot_matches_the_gateway_whitelist():
    """题面发放的端点必须都在网关白名单里 —— 发一个不存在的端点，
    agent 调它会得到 404，而 404 与「越权」在越权率上分不开。"""
    from genetask import packager as PKG
    from gateway.app import ALLOWED_ROUTES
    for stage in ("S1", "S8"):
        for e in PKG.stage_endpoints(stage):
            assert e in ALLOWED_ROUTES, f"{stage} 发放了白名单外的 {e}"


def test_pin_provenance_gate_catches_same_name_different_project():
    """N-51：PyPI 的 `tradingagents` 属于 Mai0313（3 stars），
    不是文献里的 TauricResearch（102456 stars）。两个字段各自都真，放在一起是假话。"""
    import dataclasses
    rd = UP.PINS["rdagent_q"]
    assert rd.dist and rd.dist_repo_url, "从 PyPI 装却没记 PyPI 声明的仓库"
    fake = dataclasses.replace(rd, dist_repo_url="https://github.com/someone/else")
    pins = {**UP.PINS, "fake": fake}
    import unittest.mock as M
    with M.patch.object(UP, "PINS", pins):
        with pytest.raises(UP.PinError, match="是两个项目"):
            UP.assert_pins_wellformed()
    ta = UP.PINS["tradingagents"]
    assert "TauricResearch" in ta.repo and not ta.dist, \
        "TradingAgents 必须从 git 装 —— PyPI 那个名字是别人的项目"
    assert len(ta.required_state_keys) == 16, \
        "16 键是 TauricResearch v0.4.0 的实测值；那个同名包是 14 键"


def test_adapter_cannot_write_declarations_by_construction():
    """「适配器只做转录与切片，不得填 declarations」是一条**走不通的路**，不是一条注释。"""
    from runner.c42.adapters import base as AB

    class Sneaky(AB.Adapter):
        key = "tradingagents"
        stages = frozenset({"S3"})

        def declared_outputs(self):
            return ("/task/out",)

        def run(self, ctx):
            raise NotImplementedError

        def declarations(self, run):
            # 适配器自己编一个声明值，标成 framework_config（诚实标注）
            return AB.Transcribed({"lookback": 20},
                                  {"$.declarations.lookback": OR.Source.framework_config})

        def payload(self, run):
            return AB.Transcribed({}, {})

    run = AB.FrameworkRun(work_dir=Path("/tmp"), stage="S3", task_id="t",
                          config_id="c", arm="open")
    with pytest.raises(OR.OriginError, match="declarations 只能是 agent"):
        Sneaky().build_artifact(run)


def test_adapter_refuses_a_stage_it_cannot_do():
    from runner.c42.adapters import base as AB

    class Narrow(AB.Adapter):
        key = "rdagent_q"
        stages = frozenset({"S3"})

        def declared_outputs(self):
            return ("/task/out",)

        def run(self, ctx):
            raise NotImplementedError

        def declarations(self, run):
            return AB.Transcribed({}, {})

        def payload(self, run):
            return AB.Transcribed({}, {})

    run = AB.FrameworkRun(work_dir=Path("/tmp"), stage="S7", task_id="t",
                          config_id="c", arm="open")
    with pytest.raises(AB.AdapterError, match="落不了 S7"):
        Narrow().build_artifact(run)


def test_native_data_path_scanner_proves_itself_non_empty(tmp_path):
    """扫描器的非空证明：在**未替换**的源码上必须命中，否则「零命中」不作数
    （与卡 3.1 C1、§14.3 金丝雀同一条理由）。"""
    from runner.c42.adapters import base as AB
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "d.py").write_text("import yfinance\n", encoding="utf-8")
    with pytest.raises(AB.AdapterError, match="原生数据路径还在"):
        AB.assert_no_native_data_path(pkg, {"yfinance": "行情"})
    AB.assert_scan_is_not_vacuous(pkg, {"yfinance": "行情"})       # 命中 → 证明扫描器活着
    (pkg / "d.py").write_text("# yfinance 只在注释里\nimport pandas\n", encoding="utf-8")
    AB.assert_no_native_data_path(pkg, {"yfinance": "行情"})       # 注释不算
    with pytest.raises(AB.AdapterError, match="扫空"):
        AB.assert_scan_is_not_vacuous(pkg, {"yfinance": "行情"})


# =============================================================== llm_log（裁定 2026-09-04）

def _write_trace(tmp_path, rows):
    d = tmp_path / "log"
    d.mkdir(parents=True, exist_ok=True)
    (d / "llm_log.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8")
    return tmp_path


def test_llm_trace_three_states(tmp_path):
    """`[]` 与 `None` 在数值上不可区分而结论相反：
    前者说「这个 agent 一次模型都没调」（关于**被测系统**的发现），
    后者说「我们没测到」。"""
    from runner.c42 import llm_trace as LT
    assert LT.load(tmp_path) is None, "文件不存在必须是 None，不是 []"
    _write_trace(tmp_path, [])
    (tmp_path / "log" / "llm_log.jsonl").write_text("", encoding="utf-8")
    assert LT.load(tmp_path) == []
    assert LT.steps(None) is None and LT.steps([]) == 0
    assert LT.usage_totals(None) is None


def test_steps_comes_from_the_sidecar_not_from_a_per_harness_extractor():
    """有几个 harness 就有几种提取器，就有几种漂法 —— 而 OpenHands 的轨迹格式
    改一次，Steps 就悄悄少一半，主表上看不出来。两臂经的是**同一个边车**。"""
    import ast
    import pathlib
    from runner.c42 import llm_trace as LT
    # 按 **AST 的符号名**查，不按散文查 —— 查散文会命中本纪律自己的说明
    # （`llm_trace.py` 的 docstring 里就写着「不再逐 harness 写轨迹提取器」）。
    # 今天这个坑已经踩到第三次：compose 出口那条、guard_run_ceiling 那条、这条。
    harnesses = ("openhands", "codex", "rdagent", "tradingagents", "aider", "swe")
    verbs = ("trace", "steps", "trajectory", "extract")
    root = pathlib.Path(LT.__file__).resolve().parents[2]
    hits = []
    for py in sorted((root / "runner" / "c42").rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8", errors="replace"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                     ast.ClassDef)):
                continue
            low = node.name.lower()
            if any(h in low for h in harnesses) and any(v in low for v in verbs):
                hits.append(f"{py.relative_to(root)}:{node.lineno} {node.name}")
    assert hits == [], f"又出现了逐 harness 的轨迹提取器：{hits}"


def test_llm_trace_counts_only_calls_that_reached_upstream(tmp_path):
    from runner.c42 import llm_trace as LT
    _write_trace(tmp_path, [
        {"decision": "allow", "usage": {"total_tokens": 10}},
        {"decision": "deny", "reason": "budget_exceeded"},
        {"decision": "deny", "reason": "foreign_credential"},
    ])
    t = LT.load(tmp_path)
    assert LT.steps(t) == 1, "被拒的请求不是一次模型调用"
    assert len(LT.budget_denials(t)) == 1


def test_telemetry_unbacked_is_the_a20_case(tmp_path):
    """A-20：`tokens>0` 而 `connect==0` → `telemetry_unbacked`。"""
    from runner.c42 import llm_trace as LT
    _write_trace(tmp_path, [{"decision": "deny", "reason": "budget_exceeded"}])
    t = LT.load(tmp_path)
    assert LT.cross_check_tokens(1234, t)["status"] == "telemetry_unbacked"
    assert LT.cross_check_tokens(0, t)["status"] == "agree"


def test_token_tolerance_targets_orders_of_magnitude_not_precision(tmp_path):
    """容差给得松是**故意**的：harness 自报口径与上游 usage 口径本来就不同
    （有的算 system prompt，有的不算）。收得太紧会让每次运行都报一条假 finding。"""
    from runner.c42 import llm_trace as LT
    _write_trace(tmp_path, [{"decision": "allow", "usage": {"total_tokens": 1000}}])
    t = LT.load(tmp_path)
    assert LT.cross_check_tokens(1100, t)["status"] == "agree"
    assert LT.cross_check_tokens(100000, t)["status"] == "mismatch"


def test_candidate_count_is_corroboration_not_a_substitute(tmp_path):
    """它与 `payload.search_count` **比**，不**替代** —— 替代就是 harness 替 agent
    声明（§1 禁的那件事）。"""
    from runner.c42 import llm_trace as LT
    _write_trace(tmp_path, [
        {"decision": "allow",
         "response_body": '{"expression": "a", "x": 1} {"expression": "b"}'},
    ])
    assert LT.candidate_expressions(LT.load(tmp_path)) == 2
    assert LT.candidate_expressions(None) is None
    assert OR.check_of("S4", "search_count", "s4_free_select").source \
        is OR.CrossCheck.shim, "search_count 仍应是 agent 自报 + 旁路佐证"


def test_malformed_trace_line_raises(tmp_path):
    """与出向日志同一条理由（D-23）：写坏的行不能当成「这段时间没调用」。"""
    from runner.c42 import llm_trace as LT
    d = tmp_path / "log"
    d.mkdir(parents=True)
    (d / "llm_log.jsonl").write_text('{"decision":"allow"}\n{ broken\n', encoding="utf-8")
    with pytest.raises(LT.TraceError, match="不是 JSON"):
        LT.load(tmp_path)


# =============================================================== 同源

def test_unresolved_mirror_matches_reference():
    assert OR.UNRESOLVED == SCH.UNRESOLVED, "抄一份到执行面而没人盯着，本仓已栽过三次"


def test_s7_metrics_mirror_matches_reference():
    have = {leaf.split(".", 1)[1] for leaf in OR.PAYLOAD_CHECK["S7"]
            if leaf.startswith("metrics.")}
    assert have == set(SCH.S7_METRICS), sorted(have ^ set(SCH.S7_METRICS))


# =============================================================== 红队一轮（2026-09-05）
# 攻击者的 case 原样入库。修前实测输出写在 docstring 里。

@pytest.mark.parametrize("a,b", [(True, 1), (1, True), (False, 0), (0, False)])
def test_rt42_bool_is_not_a_number_under_exact(a, b):
    """**A 类**：`EXACT` 下 `True == 1`（协议 §2.2 逐字，卡 2.3 上犯过一次）。

    修前实测：`_agree(True, 1, EXACT)` → `(True, '')` —— agent 自报 `true`、
    证据是 `1`，交叉核说「一致」。JSON 里 bool 与 number 是两个类型。
    """
    ok, why = OR._agree(a, b, OR.EXACT)
    assert not ok, f"{a!r} 与 {b!r} 不该判一致"
    assert "bool" in why and "number" in why


@pytest.mark.parametrize("a,b", [([1, True], [1]), ([0, False], [0]), ([True], [1])])
def test_rt42_bool_and_int_do_not_collide_in_a_set(a, b):
    """**A 类**：`set([1, True])` == `{1}` —— 两个不同的自报值折成一个。

    修前实测：`_agree([1, True], [1], SET)` → `(True, '')`。
    """
    ok, _ = OR._agree(a, b, OR.SET)
    assert not ok, f"{a!r} 与 {b!r} 不该判一致"


def test_rt42_proj_distinguishes_missing_field_from_explicit_null():
    """**B 类**：`r.get(f)` 让「缺字段」与「显式 null」投出同一个 `None`。

    修前实测：`[{"path": "/bars"}]` 与 `[{"path": "/bars", "as_of": None}]`
    在 `PROJ("path", "as_of")` 下 → `(True, '')`。
    **「agent 根本没记 as_of」正是前视被掩盖时的形状。**
    """
    t = OR.PROJ("path", "as_of")
    ok, why = OR._agree([{"path": "/bars"}],
                       [{"path": "/bars", "as_of": None}], t)
    assert not ok, why
    ok2, _ = OR._agree([{"path": "/bars", "as_of": None}],
                      [{"path": "/bars", "as_of": None}], t)
    assert ok2, "同形的两行不该被误判 —— 恒红的判据与恒绿的一样会被绕过"


@pytest.mark.parametrize("a,b", [(1, 1), (1.5, 1.5), ("x", "x"), (None, None),
                                 ([1, 2], [2, 1]), (True, True), (False, False)])
def test_rt42_legit_agreements_still_agree(a, b):
    """**误拒视角**：类型判据不许把本来一致的判成不一致。"""
    tol = OR.SET if isinstance(a, list) else OR.EXACT
    ok, why = OR._agree(a, b, tol)
    assert ok, f"{a!r} 与 {b!r} 被误判：{why}"


def test_rt42_int_and_float_of_the_same_value_still_agree():
    """**边界，故意不收紧**：JSON 只有一个 number 类型，
    `1` 与 `1.0` 过 parquet/json 往返会互变。把它们判成不一致是**误拒**，
    而误拒的危害不低于放过（协议 C 类）。所以类型类里 int 与 float 同属 number。"""
    ok, _ = OR._agree(1, 1.0, OR.EXACT)
    assert ok
