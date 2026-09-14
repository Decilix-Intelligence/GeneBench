# -*- coding: utf-8 -*-
"""卡 4.2-a 的测试：生成器 / oracle / 结局分类 / 适配赛道表 / bundle 出集。

判据全部来自本卡规格 `ops/specs/adaptation_track.md`：
30 例、三级各 10、每例只破一处、oracle 过协议校验器、L3 的 oracle 在缺口上标 `unresolved`、
五类结局各有一个夹具、表能出。
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

import genebench_config as cfg
from ops import adaptation_track as AT
from ops import pack_adaptation as PK
from reference import artifact_schema as sch
from scorer import adaptation as AD
from scorer import report as RP

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


@pytest.fixture(scope="module")
def built() -> dict:
    """30 例只建一次 —— 每个测试各建一遍会把 S5 那道 65 万字节的题读 10 次。"""
    return {e.example_id: AT.build(e) for e in AT.EXAMPLES}


# ------------------------------------------------------------------ 生成器


def test_thirty_examples_ten_per_level():
    assert len(AT.EXAMPLES) == 30
    for lv in AT.LEVELS:
        assert sum(1 for e in AT.EXAMPLES if e.level == lv) == AT.PER_LEVEL, lv
    assert len({e.example_id for e in AT.EXAMPLES}) == 30, "example_id 必须互异"


def test_each_break_is_exactly_one_site(built):
    for ex in AT.EXAMPLES:
        b = built[ex.example_id]
        sites = AT.diff_sites(b["original"], b["broken"])
        assert len(sites) == 1, f"{ex.example_id} 破了 {len(sites)} 处：{sites[:3]}"
        assert sites[0]["path"].startswith(("declarations", "payload", "provenance")), sites[0]


def test_diff_sites_treats_rename_and_list_drop_as_one_site():
    """改名（一删一增）与整条被删各算一处 —— 否则「每例只破一处」这条永远不可能满足。"""
    assert len(AT.diff_sites({"a": {"volume": 1}}, {"a": {"vol": 1}})) == 1
    assert len(AT.diff_sites({"p": [{"x": 1}]}, {"p": []})) == 1
    assert len(AT.diff_sites({"a": 1, "b": 2}, {"a": 9, "b": 8})) == 2
    assert AT.diff_sites({"a": 1}, {"a": 1}) == []
    #: bool 与 int 不是同一个值（1 == True 在 Python 里成立）
    assert len(AT.diff_sites({"a": 1}, {"a": True})) == 1


def test_oracle_passes_protocol_validator(built):
    for ex in AT.EXAMPLES:
        b = built[ex.example_id]
        v = sch.validate(b["oracle"], task=b["taskspec"], gateway_log=None, tradability=None)
        assert v.ok, f"{ex.example_id} 的 oracle 不过校验器：{[str(f) for f in v.findings][:3]}"


def test_l3_oracle_marks_the_gap_unresolved(built):
    for ex in (e for e in AT.EXAMPLES if e.level == "L3"):
        o = built[ex.example_id]["oracle"]
        if ex.gap == "declaration":
            assert o["declarations"][ex.gap_field] == sch.UNRESOLVED, ex.example_id
            halt = sch.honest_halt_fields(o["stage"], o["declarations"],
                                          built[ex.example_id]["taskspec"]["underdetermined"])
            for f in halt:
                cur = o["payload"]
                for k in f.split("."):
                    cur = cur[k]
                assert cur is None, f"{ex.example_id} 的 {f} 依赖被标 unresolved 的口径，却不是 null"
            assert o.get("halted_fields") == sorted(halt)
        else:
            assert o["provenance"][ex.prov_index]["artifact_id"] == sch.UNRESOLVED, ex.example_id


def test_l1_l2_oracle_is_the_source_artifact(built):
    """L1/L2 的 oracle **就是**原件（只换信封）—— 判据不能悄悄变成「差不多」。"""
    for ex in (e for e in AT.EXAMPLES if e.level != "L3"):
        b = built[ex.example_id]
        assert b["oracle"]["payload"] == b["original"]["payload"], ex.example_id
        assert b["oracle"]["declarations"] == b["original"]["declarations"], ex.example_id
        assert b["oracle"]["provenance"] == b["original"]["provenance"], ex.example_id


def test_stage_coverage(built):
    """每级至少 5 个阶段；整条赛道覆盖八个阶段。"""
    all_stages: set[str] = set()
    for lv in AT.LEVELS:
        stages = {built[e.example_id]["original"]["stage"] for e in AT.EXAMPLES if e.level == lv}
        assert len(stages) >= 5, f"{lv} 只覆盖 {sorted(stages)}"
        all_stages |= stages
    assert all_stages == set(sch.STAGES), f"整条赛道少了 {sorted(set(sch.STAGES) - all_stages)}"


def test_l1_units_are_in_the_unit_table():
    table = AT.load_module("unit_table.json")["units"]
    for ex in (e for e in AT.EXAMPLES if e.level == "L1"):
        assert ex.unit in table, f"{ex.example_id} 用了表里没有的单位 {ex.unit!r}"


def test_l2_aliases_are_resolvable_by_field_map():
    """L2 的每个别名都要能在 field_map 里查到 —— 查不到就是「不可接纳」，那不该出成 L2 题。"""
    fm = AT.load_module("field_map.json")
    blob = json.dumps(fm, ensure_ascii=False)
    for ex in (e for e in AT.EXAMPLES if e.level == "L2"):
        assert ex.alias is not None, ex.example_id
        schema_side, source_side = ex.alias
        if ex.family == "lexicon_enum" and ":" in schema_side:
            field, value = schema_side.split(":", 1)
            assert source_side in fm["enum_values"][field][value], ex.example_id
        elif ex.family == "lexicon_field":
            assert source_side in fm["field_names"][schema_side].values(), ex.example_id
        else:                                        # lexicon_code
            assert source_side.lower()[:2] in ("sz", "sh"), ex.example_id
            assert source_side.lower()[2:] == schema_side.split(".")[0], ex.example_id
            assert "code_notation" in blob


def test_l1_recovery_route_is_declared_and_checked():
    routes = {"sibling_identity", "schema_format", "source_unit_declaration"}
    for ex in (e for e in AT.EXAMPLES if e.level == "L1"):
        assert ex.recovery["route"] in routes, ex.example_id
        if ex.recovery["route"] in ("sibling_identity", "source_unit_declaration"):
            assert ex.check is not None, f"{ex.example_id} 的可纠正性没有生成期实测"


def test_module_manifest_matches_files():
    m = json.loads((AT.MODULE_DIR / "MANIFEST.json").read_text(encoding="utf-8"))
    assert m["artifacts"] == AT.module_manifest()["artifacts"], \
        "适配模块清单与实物不符 —— 跑 ops/adaptation_track.py --write-protocol-manifest"
    assert set(m["artifacts"]) == set(AT.MODULE_STATIC)


# ------------------------------------------------------------------ 结局分类


def _log(*n_violations: int) -> list[dict]:
    return [{"n_violations": n} for n in n_violations]


def test_outcome_first_pass(built):
    b = built["adapt-l1-01"]
    r = AD.classify(mutation=b["mutation"], oracle=b["oracle"],
                    agent_artifact=b["oracle"], validator_log=_log(0))
    assert r.outcome == "first_pass" and r.matched and r.valid
    assert r.outcome == r.expected_outcome


def test_outcome_repaired_pass(built):
    b = built["adapt-l2-01"]
    r = AD.classify(mutation=b["mutation"], oracle=b["oracle"],
                    agent_artifact=b["oracle"], validator_log=_log(3, 1, 0))
    assert r.outcome == "repaired_pass" and r.validator_rejections == 2


def test_outcome_correct_flag(built):
    b = built["adapt-l3-02"]
    r = AD.classify(mutation=b["mutation"], oracle=b["oracle"],
                    agent_artifact=b["oracle"], validator_log=_log(0))
    assert r.outcome == "correct_flag" and r.marked_unresolved is True
    assert r.outcome == r.expected_outcome


def test_outcome_blocked(built):
    """校验器拒了、agent 停下：交上来的还是上游那份（缺声明字段 → malformed）。"""
    b = built["adapt-l3-01"]
    r = AD.classify(mutation=b["mutation"], oracle=b["oracle"],
                    agent_artifact=b["broken"], validator_log=_log(1, 1))
    assert r.outcome == "blocked" and r.valid is False


def test_outcome_failed_when_valid_but_wrong(built):
    """结构上完全合法、只是单位/词汇没换 —— 这一类只有比对 oracle 才判得出来。

    夹具**按性质挑**，不写死 example_id（卡 Y2）：题源与选题按 N-348 换过之后，
    `adapt-l1-01` 不再是「结构合法」的那一类了。写死 id 的夹具会在换题源时假红。
    """
    legal = [e.example_id for e in AT.EXAMPLES
             if built[e.example_id]["mutation"]["broken_validator"]["ok"]]
    assert legal, "一例结构合法的破坏都没有了 —— §5 那段话就没有依据了"
    b = built[legal[0]]
    v = sch.validate(b["broken"], task=b["taskspec"], gateway_log=None, tradability=None)
    assert v.ok, "这一例的破坏本来就该是结构合法的，否则夹具立不住"
    r = AD.classify(mutation=b["mutation"], oracle=b["oracle"],
                    agent_artifact=b["broken"], validator_log=None)
    assert r.outcome == "failed" and r.matched is False
    site = b["mutation"]["site"]
    assert any(site.split(".")[1] in m for m in r.mismatched), (site, r.mismatched)


def test_outcome_blocked_when_no_artifact(built):
    b = built["adapt-l1-01"]
    r = AD.classify(mutation=b["mutation"], oracle=b["oracle"],
                    agent_artifact=None, validator_log=_log(2))
    assert r.outcome == "blocked"
    r2 = AD.classify(mutation=b["mutation"], oracle=b["oracle"],
                     agent_artifact=None, validator_log=None)
    assert r2.outcome == "failed", "没有产物也没有回路记录 = 失败，不是拦截"


def test_validator_log_absent_is_none_not_zero():
    assert AD.rejections(None) is None
    assert AD.rejections([]) == 0


# ------------------------------------------------------------------ 表


def _rec(level, outcome, **kw):
    base = {"config_id": "c1", "arm": "adapt", "level": level, "outcome": outcome,
            "expected_outcome": "correct_flag" if level == "L3" else "first_pass",
            "validator_rejections": kw.get("rej")}
    return base


def test_table_adaptation_counts_and_rates():
    recs = [_rec("L1", "first_pass", rej=0), _rec("L1", "failed", rej=1),
            _rec("L2", "repaired_pass", rej=2), _rec("L2", "blocked", rej=1),
            _rec("L3", "correct_flag", rej=0), _rec("L3", "correct_flag", rej=0)]
    rows = RP.table_adaptation(recs)
    by = {(r["level"]): r for r in rows}
    assert by["L1"]["n"] == 2 and by["L1"]["first_pass"] == 1 and by["L1"]["failed"] == 1
    assert by["L1"]["first_pass_rate"] == 0.5
    assert by["L3"]["correct_flag"] == 2 and by["L3"]["as_expected_rate"] == 1.0
    assert by["L2"]["resolved_rate"] == 0.5, "拦截不进分子"
    assert by["ALL"]["n"] == 6
    assert by["ALL"]["validator_rejections_mean"] == pytest.approx(4 / 6)


def test_table_adaptation_writes_csv_and_latex(tmp_path):
    recs = [_rec("L1", "first_pass", rej=0), _rec("L3", "correct_flag", rej=0)]
    rows = RP.table_adaptation(recs)
    p = RP.write_csv(rows, tmp_path / "adaptation.csv", RP.TABLE_ADAPTATION_COLUMNS)
    head = p.read_text(encoding="utf-8").splitlines()[0]
    assert head.split(",")[:4] == ["config_id", "arm", "level", "n"]
    tex = RP.to_latex(rows, RP.TABLE_ADAPTATION_COLUMNS, caption="适配赛道", label="tab:adapt")
    assert r"\begin{tabular}" in tex and "---" not in tex.split(r"\midrule")[0]


def test_table_adaptation_empty_records_is_empty_not_zero():
    assert RP.table_adaptation([]) == []


# ------------------------------------------------------------------ 落盘产物 / 出集


def test_products_on_disk_match_the_generator():
    """答案面上的 30 例与现在的生成器一致 —— 生成器改了而没重跑，这条会红。"""
    idx_p = AT.OUT_ROOT / "_index.json"
    if not idx_p.is_file():
        pytest.skip(f"还没生成：{idx_p}（跑 ops/adaptation_track.py --write）")
    idx = json.loads(idx_p.read_text(encoding="utf-8"))
    assert idx["n"] == 30
    for row in idx["examples"]:
        d = AT.OUT_ROOT / row["example_id"]
        for name, want in row["files"].items():
            got = AT._sha_text((d / name).read_text(encoding="utf-8"))
            assert got == want, f"{row['example_id']}/{name} 与清单不符"


def test_set_manifest_root_is_reproducible():
    if not (AT.OUT_ROOT / "_index.json").is_file():
        pytest.skip("还没生成")
    p = PK.SET_MANIFEST
    if not p.is_file():
        pytest.skip(f"还没写集清单：{p}")
    on_disk = json.loads(p.read_text(encoding="utf-8"))
    assert on_disk["root"] == PK.set_manifest()["root"], \
        "集清单的 sha256 根与产物不符 —— 跑 ops/pack_adaptation.py --write-set-manifest"
    assert on_disk["levels"] == {"L1": 10, "L2": 10, "L3": 10}


def test_bundle_passes_push_guard():
    """出集：bundle 树 + 通行证两道都过 `ops/push_guard`。**不放宽 guard**。"""
    if not (AT.OUT_ROOT / "adapt-l1-01" / "broken.json").is_file():
        pytest.skip("还没生成")
    root = cfg.GENEBENCH_ROOT / "staging" / "adapt_bundles_pytest"
    try:
        r = PK.pack_one("adapt-l1-01", root)
        assert Path(r["bundle"], "task.yaml").is_file()
        assert Path(r["bundle"], "work", "input", "broken.json").is_file()
        m = json.loads(Path(r["manifest"]).read_text(encoding="utf-8"))
        assert m["set_id"] == "v1.0-adapt" and m["check_export"] == []
        stage = json.loads((AT.OUT_ROOT / "adapt-l1-01" / "mutation.json")
                           .read_text(encoding="utf-8"))["stage"]
        assert set(m["files"]) == {
            "task.yaml", *(f"arms/INSTRUCTION.{a}.md" for a in PK.DEFAULT_ARMS),
            "image/Dockerfile", "image/tests/test_outputs.py",
            f"work/{stage}.json", "work/input/broken.json", "work/input/source_meta.json"}
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_bundle_refuses_to_land_outside_the_answer_plane(tmp_path):
    """落点闸：适配 bundle 携带 gold 只破一处的内容，不许被打到答案面之外。"""
    with pytest.raises(PK.PackBlocked):
        PK.pack_one("adapt-l1-01", tmp_path / "somewhere")


def test_structurally_legal_breaks_are_recorded(built):
    """**9 例**的破坏结构上完全合法 —— 这是「结局必须比对 oracle、不能只看校验器」
    那句话的依据（`ops/specs/adaptation_track.md` §5）。数变了就要改文档，不许悄悄漂。

    （2026-09-10 卡 Y2：题源按 N-348 换成规定题的 oracle 产物、选题改成种子固定的分层抽样之后，
    这个数从 13 变成 9。它是**实测**，不是设计目标 —— 变了就照实改这里与 §5。）"""
    legal = [e.example_id for e in AT.EXAMPLES
             if built[e.example_id]["mutation"]["broken_validator"]["ok"]]
    assert len(legal) == 9, legal
