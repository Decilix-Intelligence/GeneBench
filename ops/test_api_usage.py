# -*- coding: utf-8 -*-
"""`ops/api_usage.py` 的夹具测试（W-0）。

夹具照着**真机形状**搭：``<batch>/runs/runs/<task>.<arm>.<config>.rNN/log/llm_log.jsonl``
（`--run-root .../m6/runs` 传下去，runner 又建了一层 `runs/` —— 多出来的那一层
是真的，不是笔误）。测试不打 ssh、不碰 f02。
"""
from __future__ import annotations

import json

import pytest

from ops import api_usage as AU


def _log(*recs) -> str:
    return "\n".join(json.dumps(r, ensure_ascii=False) for r in recs) + "\n"


def _allow(ts, tokens):
    return {"ts": ts, "decision": "allow", "status": 200,
            "usage": {"total_tokens": tokens}}


def _deny(ts, reason="budget_exceeded"):
    return {"ts": ts, "decision": "deny", "status": 402, "reason": reason}


@pytest.fixture()
def run_root(tmp_path):
    """两个 batch、四个 run、外加两个**不该被计入**的东西。"""
    def put(rel, text):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    put("m6/runs/runs/s2-cor-01.strict.cfg-codex-deepseek.r01/log/llm_log.jsonl",
        _log(_allow("2026-09-05T10:00:00Z", 100),
             _allow("2026-09-05T10:00:01Z", 200),
             _deny("2026-09-05T10:00:02Z")))
    put("m6/runs/runs/s2-cor-01.open.cfg-codex-deepseek.r01/log/llm_log.jsonl",
        _log(_allow("2026-09-05T11:00:00Z", 50)))
    put("m6/runs/runs/s2-cor-01.strict.cfg-openhands-deepseek.r01/log/llm_log.jsonl",
        _log(_allow("2026-09-05T12:00:00Z", 7)) + "{ 这行坏了\n")
    put("a1/runs/runs/s1-cor-01.open.cfg-codex-deepseek.r03/log/llm_log.jsonl",
        _log(_allow("2026-09-04T09:00:00Z", 1000)))
    # ↓ 两个**不是 run** 的：一次性探针（没有 <batch>/runs 这一层）与非日志文件
    put("fwprobe/cred/log/llm_log.jsonl", _log(_allow("2026-09-03T00:00:00Z", 9999)))
    put("m6/runs/runs/s2-cor-01.strict.cfg-codex-deepseek.r01/log/access_log.jsonl",
        _log(_allow("2026-09-05T10:00:00Z", 12345)))
    return tmp_path


def test_only_batch_runs_are_counted(run_root):
    found = AU.find_run_logs(run_root)
    assert [(r["batch"], r["run_id"]) for r in found] == [
        ("a1", "s1-cor-01.open.cfg-codex-deepseek.r03"),
        ("m6", "s2-cor-01.open.cfg-codex-deepseek.r01"),
        ("m6", "s2-cor-01.strict.cfg-codex-deepseek.r01"),
        ("m6", "s2-cor-01.strict.cfg-openhands-deepseek.r01"),
    ]
    # fwprobe/ 没有 <batch>/runs 那一层 —— 它不是 run，不进「每 run 预算」的表
    assert all(r["batch"] != "fwprobe" for r in found)


def test_batch_filter(run_root):
    assert {r["batch"] for r in AU.find_run_logs(run_root, ["m6"])} == {"m6"}
    assert AU.find_run_logs(run_root, ["nope"]) == []


def test_summarize_counts_allow_only_and_keeps_bad_lines_visible():
    s = AU.summarize_lines([
        json.dumps(_allow("2026-09-05T10:00:00Z", 10)),
        json.dumps(_deny("2026-09-05T10:00:01Z")),
        "",
        "{ 坏行",
        json.dumps([1, 2, 3]),
        json.dumps({"ts": "2026-09-05T10:00:03Z"}),          # 没有 decision
    ])
    assert s["allow"] == 1
    assert s["other"] == 2                                   # deny + 没有 decision 的
    assert s["malformed"] == 2                               # 坏行 + 不是对象的
    assert s["by_decision"] == {"allow": 1, "deny": 1, "<missing>": 1}
    assert s["total_tokens"] == 10
    assert s["first_ts"] == "2026-09-05T10:00:00Z"
    assert s["last_ts"] == "2026-09-05T10:00:03Z"


@pytest.mark.parametrize("run_id, want", [
    ("s2-cor-01.strict.cfg-codex-deepseek.r01",
     {"task_id": "s2-cor-01", "arm": "strict",
      "config_id": "cfg-codex-deepseek", "rep": "r01"}),
    ("乱七八糟", {"task_id": None, "arm": None, "config_id": None, "rep": None}),
    ("a.b.c.d", {"task_id": None, "arm": None, "config_id": None, "rep": None}),
])
def test_parse_run_id(run_id, want):
    assert AU.parse_run_id(run_id) == want


def test_aggregate_totals_and_grouping(run_root):
    agg = AU.aggregate(AU.collect_local(run_root))
    assert agg["total"] == {"runs": 4, "allow": 5, "other": 1, "malformed": 1,
                            "total_tokens": 1357}
    assert agg["by_batch"]["m6"]["allow"] == 4
    assert agg["by_batch"]["a1"]["allow"] == 1
    assert agg["by_config_id"]["cfg-codex-deepseek"]["allow"] == 4
    assert agg["by_config_id"]["cfg-openhands-deepseek"]["allow"] == 1
    assert agg["by_arm"]["strict"]["allow"] == 3
    assert agg["by_arm"]["open"]["allow"] == 2


def test_unparsable_run_name_lands_in_its_own_bucket_not_a_plausible_one(tmp_path):
    p = tmp_path / "x/runs/runs/这不是一个-run-名/log/llm_log.jsonl"
    p.parent.mkdir(parents=True)
    p.write_text(_log(_allow("2026-09-05T10:00:00Z", 1)), encoding="utf-8")
    agg = AU.aggregate(AU.collect_local(tmp_path))
    assert agg["by_config_id"] == {"<未知>": {"runs": 1, "allow": 1, "other": 0,
                                              "malformed": 0, "total_tokens": 1}}


def test_markdown_always_carries_the_history_line_and_the_total(run_root):
    md = AU.render_markdown(AU.aggregate(AU.collect_local(run_root)))
    assert AU.HISTORY_LINE in md
    assert "1 700" in md
    assert "**总计：5 次真调用**" in md
    for h in ("### 按 batch", "### 按 config_id", "### 按 arm", "### 逐 run"):
        assert h in md


def test_empty_root_is_empty_not_an_exception(tmp_path):
    agg = AU.aggregate(AU.collect_local(tmp_path))
    assert agg["total"]["runs"] == 0 and agg["total"]["allow"] == 0
    assert AU.HISTORY_LINE in AU.render_markdown(agg)


def test_main_writes_both_files(run_root, tmp_path):
    out = tmp_path / "out"
    rc = AU.main(["--local-root", str(run_root), "--out-dir", str(out)])
    assert rc == 0
    got = json.loads((out / "api_usage.json").read_text(encoding="utf-8"))
    assert got["total"]["allow"] == 5
    assert got["history_note"] == AU.HISTORY_LINE
    assert (out / "api_usage.md").read_text(encoding="utf-8").startswith("# 真 API 用量")
