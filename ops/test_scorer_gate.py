# -*- coding: utf-8 -*-
"""卡 5.1 闸门/三态接线的红测 + `score_run` 端到端（用真实题目录 s1-cor-01；没有就跳过）。"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from reference import artifact_samples as AS
from reference.artifact_schema import PROBE_IDS, Verdict, validate_scorer_output
from runner.c42 import visibility as VIS
from scorer import gate as G

REF_TASK = Path("/data/shared/genebench/reference/tasks/v1.0-smoke/s1-cor-01")


# ------------------------------------------------------------------ probe_states
def test_probe_states_cover_every_family_and_three_states():
    v = Verdict()
    v.add("x", "violation", "$.p", "m", probe="lookahead")
    v.mark_unobservable("pit_universe", "no view")
    st = G.probe_states(v)
    assert set(st) == set(PROBE_IDS)
    assert st["lookahead"] == "violation" and st["pit_universe"] == "unobservable"
    assert all(s in G.PROBE_STATES for s in st.values())
    assert sum(1 for s in st.values() if s == "clean") == len(PROBE_IDS) - 2


def test_probe_states_reject_overlap():
    v = Verdict()
    v.add("x", "violation", "$.p", "m", probe="lookahead")
    v.unobservable.append("lookahead")              # 绕过 mark_unobservable 的保护，模拟上游脏数据
    with pytest.raises(G.GateError):
        G.probe_states(v)


# ------------------------------------------------------------------ gate()
def test_gate_clean_sample_is_valid_with_all_clean_or_unobservable():
    s = AS.s1()
    r = G.gate(s.artifact, task=s.task, gateway_log=s.log, tradability=s.trad, config_id=AS.CFG)
    assert r.validity == "valid" and not r.malformed and r.gate_failed == []
    assert "violation" not in r.probe_states.values()


def test_gate_log_unavailable_marks_log_probes_unobservable_not_clean():
    s = AS.s1()
    marks = [(p, VIS.UNOBSERVABLE_REASON) for p in VIS.LOG_DEPENDENT_PROBES]
    r = G.gate(s.artifact, task=s.task, gateway_log=None, unobservable_marks=marks, config_id=AS.CFG)
    assert r.validity == "valid"
    for p in VIS.LOG_DEPENDENT_PROBES:
        assert r.probe_states[p] == "unobservable"
    assert set(r.unobservable) >= set(VIS.LOG_DEPENDENT_PROBES)


def test_gate_malformed_is_invalid_without_gate_failed():
    s = AS.s1()
    bad = dict(s.artifact)
    del bad["schema_version"]
    r = G.gate(bad, task=s.task, gateway_log=s.log, config_id=AS.CFG)
    assert r.validity == "invalid" and r.malformed and r.gate_failed == []


def test_gate_config_id_mismatch_is_malformed():
    s = AS.s1()
    r = G.gate(s.artifact, task=s.task, gateway_log=s.log, config_id="someone-else")
    assert r.malformed and any("config_id_mismatch" in f for f in r.findings)


# ------------------------------------------------------------------ score_run 端到端
def _mk_run(tmp_path: Path, task_dir: Path, *, config_id="cfg-t", arm="open", artifact: dict | None) -> Path:
    rd = tmp_path / "s1-cor-01.open.cfg-t.r01"
    (rd / "work").mkdir(parents=True)
    (rd / "log").mkdir()
    (rd / "run.json").write_text(json.dumps({
        "run_id": rd.name, "arm": arm, "config_id": config_id, "exit_code": 0,
        "started_at": "2026-09-05T10:00:00+00:00", "finished_at": "2026-09-05T10:05:00+00:00",
        "elapsed_s": 300.0, "new_files": {}, "unexpected": [], "stdout_tail": "", "stderr_tail": ""}))
    (rd / "inject.json").write_text(json.dumps({
        "run_id": rd.name, "task_id": "s1-cor-01", "config_id": config_id, "arm": arm, "seq": 1, "files": {}}))
    if artifact is not None:
        (rd / "work" / "artifact.json").write_text(json.dumps(artifact, ensure_ascii=False))
    return rd


@pytest.fixture
def ref_task():
    if not (REF_TASK / "solution" / "artifact.json").is_file():
        pytest.skip("本机没有 s1-cor-01 的参考题目录 / gold")
    return REF_TASK


def test_score_run_oracle_copy_is_valid_and_l3_passes(tmp_path, ref_task):
    """判据 2026-09-05 起是 `cov`（N-114）：S1 比 Cov% / PIT% / Prov，不比取数台账逐字相等。"""
    from scorer import score_run as SR
    gold = json.loads((ref_task / "solution" / "artifact.json").read_text(encoding="utf-8"))
    agent = {**gold, "config_id": "cfg-t", "arm": "open"}
    rd = _mk_run(tmp_path, ref_task, artifact=agent)
    r = SR.score_run(rd, ref_task, out_dir=tmp_path / "out", anchor_status="pending")
    rec, out = r["record"], r["scorer_output"]
    assert rec["run_status"] == "ok" and rec["sr_bucket"] == "scorable" and rec["validity"] == "valid"
    assert rec["l3_kind"] == "cov" and rec["l3_pass"] is True and rec["l3_score"] == 1.0
    assert rec["correctness"]["Cov"] == 1.0
    assert out["effect"] is None and out["effect_withheld_reason"] == "anchor_pending"
    assert validate_scorer_output(out, anchor_status="pending").ok
    assert set(rec["probe_states"]) == set(PROBE_IDS)
    # 日志不给（模拟 f02 侧不可得）→ 这四族必须是 unobservable，不是 clean
    for pr in VIS.LOG_DEPENDENT_PROBES:
        assert rec["probe_states"][pr] == "unobservable"
    assert rec["latency_s"] == 300.0 and rec["steps"] is None
    assert Path(r["path"]).is_file()


def test_effect_is_anchored_between_null_and_oracle(tmp_path, ref_task):
    """效果分 = 100 × (agent − null) / (oracle − null)，夹 [0, 100]（裁定 2026-09-05）。

    两端各测一次：oracle 副本 = 100（顶），null 产物 = 0（底）。中间值由 Cov 的定义保证单调。
    """
    from scorer import score_run as SR
    gold = json.loads((ref_task / "solution" / "artifact.json").read_text(encoding="utf-8"))
    rd = _mk_run(tmp_path, ref_task, artifact={**gold, "config_id": "cfg-t", "arm": "open"})
    r = SR.score_run(rd, ref_task, out_dir=tmp_path / "out", anchor_status="fixed")
    out = r["scorer_output"]
    assert out["effect"]["score"] == 100.0 and out.get("effect_withheld_reason") is None
    assert out["effect"]["anchor_floor"] == 0.0 and out["effect"]["anchor_ceiling"] == 1.0
    assert validate_scorer_output(out, anchor_status="fixed").ok
    # 半分：只拿到三个要求字段里的一个 → Cov=1/3 → effect≈33.3
    half = {**gold, "config_id": "cfg-t", "arm": "open"}
    half["payload"] = {**gold["payload"], "fields_obtained": [gold["payload"]["fields_obtained"][0]]}
    rd2 = _mk_run(tmp_path / "half", ref_task, artifact=half)
    r2 = SR.score_run(rd2, ref_task, out_dir=tmp_path / "out", anchor_status="fixed")
    assert r2["scorer_output"]["effect"]["score"] == pytest.approx(100 / 3, abs=0.01)


def test_effect_withheld_when_anchor_degenerate(tmp_path, ref_task, monkeypatch):
    """两端同分 → 分母为零 → effect 是 **null**（不是 0），理由 `anchor_degenerate`。"""
    from scorer import score_run as SR
    monkeypatch.setattr(SR, "anchor", lambda *a, **k: {"floor": 1.0, "ceiling": 1.0, "kind": "two_rung"})
    gold = json.loads((ref_task / "solution" / "artifact.json").read_text(encoding="utf-8"))
    rd = _mk_run(tmp_path, ref_task, artifact={**gold, "config_id": "cfg-t", "arm": "open"})
    r = SR.score_run(rd, ref_task, out_dir=tmp_path / "out", anchor_status="fixed")
    out = r["scorer_output"]
    assert out["effect"] is None and out["effect_withheld_reason"] == "anchor_degenerate"
    assert validate_scorer_output(out, anchor_status="fixed").ok


def test_score_run_deleted_artifact_is_unscorable_not_scored(tmp_path, ref_task):
    """删产物必红（D-27）：没有产物 → unscorable_agent，**没有** scorer 输出，也没有 gate_failed。"""
    from scorer import score_run as SR
    rd = _mk_run(tmp_path, ref_task, artifact=None)
    r = SR.score_run(rd, ref_task, out_dir=tmp_path / "out", anchor_status="pending")
    rec = r["record"]
    assert rec["run_status"] == "no_artifact" and rec["sr_bucket"] == "unscorable_agent"
    assert r["scorer_output"] is None and rec["gate_failed"] == [] and rec["l3_pass"] is None


def test_score_run_identity_mismatch_is_unscorable_agent(tmp_path, ref_task):
    from scorer import score_run as SR
    gold = json.loads((ref_task / "solution" / "artifact.json").read_text(encoding="utf-8"))
    rd = _mk_run(tmp_path, ref_task, artifact={**gold, "config_id": "self-reported-other"})
    r = SR.score_run(rd, ref_task, out_dir=tmp_path / "out", anchor_status="pending")
    assert r["record"]["run_status"] == "identity_mismatch" and r["scorer_output"] is None


def test_score_run_malformed_artifact_is_malformed_bucket(tmp_path, ref_task):
    from scorer import score_run as SR
    gold = json.loads((ref_task / "solution" / "artifact.json").read_text(encoding="utf-8"))
    bad = {**gold, "config_id": "cfg-t"}
    del bad["payload"]
    rd = _mk_run(tmp_path, ref_task, artifact=bad)
    r = SR.score_run(rd, ref_task, out_dir=tmp_path / "out", anchor_status="pending")
    assert r["record"]["run_status"] == "malformed" and r["record"]["sr_bucket"] == "malformed"
    assert r["scorer_output"] is None


def test_score_run_timeout_exit_code(tmp_path, ref_task):
    from scorer import score_run as SR
    rd = _mk_run(tmp_path, ref_task, artifact=None)
    j = json.loads((rd / "run.json").read_text()); j["exit_code"] = 124
    (rd / "run.json").write_text(json.dumps(j))
    r = SR.score_run(rd, ref_task, out_dir=tmp_path / "out", anchor_status="pending")
    assert r["record"]["run_status"] == "timeout"
