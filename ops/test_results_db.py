#!/usr/bin/env python3
"""卡 5.4 的测试：结果库（`ops/results_db.py`）+ 三张表的单一出口（`ops/mk_tables.py`）。

判据全部来自卡面：
1. `ingest` 幂等（同一批收两遍，第二遍一条都不加）；
2. 同一主键内容不同 → 报错**且不覆盖**；
3. 四条版本轴缺一即拒；
4. 混轴默认拒绝出表，`--allow-mixed-axes` 才放行；
5. csv / md / latex 三种格式都出得来；
6. **从库生成的 Table A / Table B 与既有 batch 目录里的 CSV 逐格相同**（用真数据）。

第 6 条是本卡最要紧的一条：它判的不是「表好不好看」，而是「结果库这条新路与旧路
算出来的是不是同一个数」。不同就说明聚合逻辑漂了 —— 那种漂移的表现是两张表都出得来。
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import genebench_config as cfg                                  # noqa: E402
from ops import mk_tables as MT                                 # noqa: E402
from ops import results_db as DB                                # noqa: E402
from scorer import report as R                                  # noqa: E402

REPORTS = _REPO / "ops" / "reports"

#: 真数据回填要用的批（`ops/reports/<b>/records.json` + `runs_in/<b>/*/inject.json` 都在才跑）。
REAL_BATCHES = ("m6", "m6b", "a4", "a1", "h_opencode", "i_tradingagents")


def _has_real(batch: str) -> bool:
    p = REPORTS / batch / "records.json"
    if not p.is_file() or not json.loads(p.read_text(encoding="utf-8")):
        return False
    return DB.protocol_version_from_runs(batch)[0] is not None


def _fake(run_id: str, *, batch: str = "t1", arm: str = "open", task_id: str = "s1-cor-01",
          **over) -> dict:
    """一条最小可入库的主赛道记录。**不是产物夹具** —— 只用来判库的行为。"""
    rec = {"task_id": task_id, "stage": "S1", "config_id": "cfg-x", "arm": arm, "seq": 1,
           "run_id": run_id, "batch": batch,
           "set_version": "1.0.12", "reference_version": "r1.0.19",
           "protocol_version": "geneprotocol_v1@aaaaaaaaaaaa", "channel": "private",
           "run_status": "ok", "sr_bucket": "scorable", "validity": "valid", "malformed": False,
           "correctness": {"Cov": 1.0}, "effect": 100.0, "l3_kind": "cov", "l3_pass": True,
           "l3_score": 1.0, "steps": 3, "tokens_prompt": 10, "tokens_completion": 2,
           "cost_usd": 0.01, "probe_states": {"calendar": "clean"},
           "overreach": {"denied": 0, "total": 4}, "unbounded_requests": 0,
           "budget_exhausted": False, "seed": 1, "track": "main"}
    rec.update(over)
    return rec


# ------------------------------------------------------------------ 1. 幂等

def test_ingest_is_idempotent(tmp_path):
    recs = [_fake("r1"), _fake("r2")]
    a = DB.ingest(copy.deepcopy(recs), root=tmp_path)
    b = DB.ingest(copy.deepcopy(recs), root=tmp_path)
    assert (a["added"], a["duplicate"]) == (2, 0)
    assert (b["added"], b["duplicate"]) == (0, 2), "同一批收两遍必须一条都不加"
    assert len(DB.load(tmp_path)) == 2
    assert DB.index_path(tmp_path).is_file()
    assert json.loads(DB.index_path(tmp_path).read_text(encoding="utf-8"))["n_records"] == 2


def test_ingest_same_call_twice_same_key(tmp_path):
    with pytest.raises(DB.ResultsDBError, match="出现了两次"):
        DB.ingest([_fake("r1"), _fake("r1")], root=tmp_path)


# ------------------------------------------------------------------ 2. 内容冲突不覆盖

def test_conflicting_content_raises_and_does_not_overwrite(tmp_path):
    DB.ingest([_fake("r1", l3_score=1.0)], root=tmp_path)
    with pytest.raises(DB.ResultsDBError, match="内容不同"):
        DB.ingest([_fake("r1", l3_score=0.5)], root=tmp_path)
    kept = DB.load(tmp_path)
    assert len(kept) == 1 and kept[0]["l3_score"] == 1.0, "冲突时库里必须还是老那条"


def test_same_run_id_in_two_batches_is_kept_and_reported(tmp_path):
    """`run_id` 不含批次，跨批必然会撞（实测 `s2-cor-01.strict.cfg-codex-deepseek.r01`
    在 a4 与 m6 里各有一条）。主键带 batch → 两条都留，重名单独报出来。"""
    DB.ingest([_fake("rx", batch="b1", l3_score=1.0)], root=tmp_path)
    DB.ingest([_fake("rx", batch="b2", l3_score=0.0)], root=tmp_path)
    rows = DB.load(tmp_path)
    assert len(rows) == 2
    assert DB.run_id_reuse(rows) == {"rx": ["b1", "b2"]}
    idx = json.loads(DB.index_path(tmp_path).read_text(encoding="utf-8"))
    assert idx["run_id_reused_across_batches"] == {"rx": ["b1", "b2"]}


# ------------------------------------------------------------------ 3. 四条版本轴缺一即拒

@pytest.mark.parametrize("axis", DB.AXES)
def test_missing_any_axis_is_rejected(tmp_path, axis):
    rec = _fake("r1")
    rec.pop(axis)
    with pytest.raises(DB.ResultsDBError, match=f"缺版本轴 {axis}"):
        DB.ingest([rec], root=tmp_path)
    assert DB.load(tmp_path) == []


def test_axes_are_the_four_from_n207():
    assert DB.AXES == ("set_version", "reference_version", "protocol_version", "channel")


def test_unknown_channel_is_rejected(tmp_path):
    with pytest.raises(DB.ResultsDBError, match="channel="):
        DB.ingest([_fake("r1", channel="staging")], root=tmp_path)


def test_missing_identity_or_result_field_is_rejected(tmp_path):
    r = _fake("r1")
    r.pop("task_id")
    with pytest.raises(DB.ResultsDBError, match="缺身份键 task_id"):
        DB.ingest([r], root=tmp_path)
    r2 = _fake("r2")
    r2.pop("validity")
    with pytest.raises(DB.ResultsDBError, match="缺结算字段 validity"):
        DB.ingest([r2], root=tmp_path)


# ------------------------------------------------------------------ 协议轴 / 通道轴

def test_protocol_digest_needs_the_whole_closed_set():
    full = {n: "0" * 64 for n in DB.PROTOCOL_STATIC}
    assert DB.protocol_digest(full).startswith("geneprotocol_v1@")
    partial = dict(full)
    partial.pop(DB.PROTOCOL_STATIC[0])
    with pytest.raises(DB.ResultsDBError, match="缺件"):
        DB.protocol_digest(partial)


def test_protocol_digest_changes_when_an_artifact_changes():
    a = {n: "0" * 64 for n in DB.PROTOCOL_STATIC}
    b = dict(a, **{DB.PROTOCOL_STATIC[0]: "1" * 64})
    assert DB.protocol_digest(a) != DB.protocol_digest(b)


def test_protocol_version_from_inject_is_none_for_bare_arm():
    assert DB.protocol_version_from_inject({"files": {"work/artifact.json": "x"}}) is None


def test_backfill_refuses_when_protocol_axis_cannot_be_derived(tmp_path):
    """反算不出协议轴 → 拒绝入库。**不拿今天仓库里的版本去追认历史批次**。"""
    reports = tmp_path / "reports" / "zz"
    reports.mkdir(parents=True)
    (reports / "records.json").write_text(json.dumps([_fake("r1", batch="zz")]), encoding="utf-8")
    with pytest.raises(DB.ResultsDBError, match="协议轴反算不出"):
        DB.backfill_batch("zz", root=tmp_path / "db", reports=tmp_path / "reports",
                          runs_in=tmp_path / "runs_in")


# ------------------------------------------------------------------ 4. 混轴

def _mixed_db(tmp_path):
    DB.ingest([_fake("r1", batch="b1"),
               _fake("r2", batch="b2", set_version="1.0.9")], root=tmp_path)
    return tmp_path


def test_mixed_axes_refused_by_default(tmp_path):
    _mixed_db(tmp_path)
    with pytest.raises(MT.MixedAxesError, match="set_version"):
        MT.select({}, root=tmp_path)


def test_mixed_axes_allowed_explicitly(tmp_path):
    _mixed_db(tmp_path)
    rows, axes = MT.select({}, root=tmp_path, allow_mixed=True)
    assert len(rows) == 2
    assert axes["mixed_axes"] == {"set_version": ["1.0.12", "1.0.9"]}
    notes = MT.axes_notes(axes)
    assert any("混轴" in n for n in notes) and any("显式放行" in n for n in notes), \
        "放行了就必须在脚注里说明，否则表上看不出这是合出来的"


def test_single_axis_selection_passes(tmp_path):
    _mixed_db(tmp_path)
    rows, axes = MT.select({"batch": "b1"}, root=tmp_path)
    assert len(rows) == 1 and axes["mixed_axes"] == {}


def test_cli_refuses_mixed_axes(tmp_path):
    _mixed_db(tmp_path)
    out = tmp_path / "out"
    rc = MT.main(["--table", "a", "--format", "csv", "--out", str(out), "--db", str(tmp_path)])
    assert rc == 3 and not (out / "table_a.csv").exists()
    rc2 = MT.main(["--table", "a", "--format", "csv", "--out", str(out), "--db", str(tmp_path),
                   "--allow-mixed-axes"])
    assert rc2 == 0 and (out / "table_a.csv").is_file()


def test_versions_lists_every_combo(tmp_path):
    _mixed_db(tmp_path)
    v = DB.versions(tmp_path)
    assert len(v) == 2
    assert {x["set_version"] for x in v} == {"1.0.12", "1.0.9"}
    assert all(set(DB.AXES) <= set(x) for x in v)


def test_query_filters(tmp_path):
    DB.ingest([_fake("r1", batch="b1", arm="open"), _fake("r2", batch="b1", arm="strict")],
              root=tmp_path)
    assert len(DB.query(tmp_path, arm="strict")) == 1
    assert len(DB.query(tmp_path, arm=["open", "strict"])) == 2
    assert DB.query(tmp_path, arm="nope") == []


# ------------------------------------------------------------------ 5. 三种格式

@pytest.mark.parametrize("fmt,ext", [("csv", "csv"), ("md", "md"), ("latex", "tex")])
def test_three_formats(tmp_path, fmt, ext):
    DB.ingest([_fake("r1"), _fake("r2", arm="strict")], root=tmp_path)
    out = tmp_path / "out"
    rc = MT.main(["--table", "a", "--format", fmt, "--out", str(out), "--db", str(tmp_path)])
    p = out / f"table_a.{ext}"
    assert rc == 0 and p.is_file() and p.stat().st_size > 0
    txt = p.read_text(encoding="utf-8")
    assert "cfg-x" in txt
    if fmt == "csv":
        assert (out / "table_a.axes.json").is_file(), "CSV 是给机器读的，版本轴落在旁边那份 JSON 里"
    else:
        assert "protocol_version" in txt and "channel" in txt, "md / latex 的脚注必须写出四条轴"


def test_adaptation_table_only_takes_adaptation_records(tmp_path):
    adapt = {"batch": "adapt", "example_id": "L1-01", "config_id": "cfg-x", "arm": "adapt",
             "run_id": "a1", "level": "L1", "outcome": "first_pass", "valid": True,
             "matched": True, "expected_outcome": "first_pass",
             "set_version": "1.0.12", "reference_version": "r1.0.19",
             "protocol_version": "geneprotocol_v1@aaaaaaaaaaaa", "channel": "private"}
    DB.ingest([_fake("r1", batch="adapt"), adapt], root=tmp_path)
    rows, _ = MT.select({}, root=tmp_path)
    ta = MT.build("adaptation", rows)[0]
    assert ta, "适配赛道表出不来行"
    assert all(r["config_id"] == "cfg-x" and r["arm"] == "adapt" for r in ta), \
        "主赛道的 run 混进了适配赛道表 —— 五结局对它们没有定义"
    assert sum(r["first_pass"] for r in ta) == 2      # level=L1 一行 + ALL 一行


# ------------------------------------------------------------------ 6. 与既有 CSV 逐格相同（真数据）

@pytest.mark.parametrize("batch", REAL_BATCHES)
def test_tables_from_db_match_existing_csv(tmp_path, batch):
    if not _has_real(batch):
        pytest.skip(f"{batch} 的 records.json 或 runs_in/{batch} 不在本机上")
    DB.backfill_batch(batch, root=tmp_path)
    v = MT.verify_batch(batch, root=tmp_path)
    for t, tv in v["tables"].items():
        assert tv["status"] == "逐格相同", \
            f"{batch} Table {t.upper()} 与既有 CSV 不同（{tv['status']}）：{tv['diffs'][:5]}"


def test_combined_m6_all_matches_existing_csv(tmp_path):
    """合表也要对得上 —— 而且它**只能**在显式放行之后才出得来。"""
    for b in ("m6", "m6b"):
        if not _has_real(b):
            pytest.skip("m6 / m6b 不在本机上")
    old = REPORTS / "m6_all" / "table_a.csv"
    if not old.is_file():
        pytest.skip("没有既有的 m6_all/table_a.csv")
    for b in ("m6", "m6b"):
        DB.backfill_batch(b, root=tmp_path)
    with pytest.raises(MT.MixedAxesError):
        MT.select({"batch": ["m6", "m6b"]}, root=tmp_path)
    rows, axes = MT.select({"batch": ["m6", "m6b"]}, root=tmp_path, allow_mixed=True)
    ta, cols = MT.build("a", rows)
    out = tmp_path / "out"
    MT.write_table("a", "csv", ta, cols, axes, out, name="m6_all")
    with open(out / "m6_all.csv", encoding="utf-8", newline="") as fh:
        new = fh.read()
    with open(old, encoding="utf-8", newline="") as fh:
        assert new == fh.read(), "从结果库出的合表与 ops/reports/m6_all/table_a.csv 不同"


def test_real_backfill_covers_every_batch_with_records():
    """回填要覆盖**所有**有 records.json 的批 —— 漏一批，结果库就不是单一来源。"""
    have = set(DB.discoverable_batches())
    assert "m6_all" not in have, "合表是别的批的副本，收它等于把同一条 run 收两遍"
    for d in sorted(p for p in REPORTS.iterdir() if p.is_dir()):
        p = d / "records.json"
        if p.is_file() and json.loads(p.read_text(encoding="utf-8")) and d.name not in DB.DERIVED_BATCHES:
            assert d.name in have, f"{d.name} 有 records.json 却不在回填清单里"


# ------------------------------------------------------------------ 红线 5：库落盘的权限

def test_db_files_are_not_group_or_world_readable(tmp_path):
    DB.ingest([_fake("r1")], root=tmp_path)
    for p in (DB.results_path(tmp_path), DB.index_path(tmp_path), DB.db_root(tmp_path)):
        assert not (p.stat().st_mode & 0o077), f"{p} 组/其它位没剥干净（红线 5）"


def test_enrich_does_not_touch_verdicts():
    src = {"task_id": "t", "config_id": "c", "arm": "open", "seq": 1, "run_id": "r",
           "set_version": "1.0.12", "reference_version": "r1.0.19",
           "l3_score": 0.5, "effect": 42.0, "validity": "valid"}
    got = DB.enrich([src], batch="b", protocol_version="geneprotocol_v1@aaaaaaaaaaaa",
                    channel="private")[0]
    for k, v in src.items():
        assert got[k] == v, f"enrich 动了判据字段 {k}"
    assert got["seed"] == 1 and got["channel"] == "private"
    assert cfg.assert_channel(got["channel"]) == "private"
