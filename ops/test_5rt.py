#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段五红队一轮（5.rt）的回归夹具：一个 block + 三条 major。

红队这一轮**没有报出一条「表上的数算错了」** —— 三条 major 全是「表上的数说错了话」，
外加一条 block：阶段五的四个入口在任何面向用户的文档里都不存在。所以这份测试的判据
也分两种：一种钉住口径（同一批记录，改口径前后表上那一格必须变），一种是**双向判据**
（一端是代码里真实存在的入口文件，一端是文档里的措辞）。

| finding | 严重度 | 判据在这里的名字 |
|---|---|---|
| 1 文档到不了阶段五的四个入口 | block | `test_handoff_has_stage5_section` / `test_readme_points_at_the_joblist_entry` |
| 2 `budget_exhausted_runs` 漏掉「撞闸但交了卷」 | major | `test_budget_exhausted_runs_counts_the_gate_not_the_status` 等三条 |
| 3 `unbounded_requests` 的 0 伪装成「不可得」 | major | `test_unbounded_requests_zero_is_not_none` 等两条 |
| 4 协议轴把批级声明当成逐 run 事实 | major | `test_protocol_axis_is_per_run` 等五条 |
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from ops import mk_tables as MT                                  # noqa: E402
from ops import results_db as DB                                 # noqa: E402
from scorer import report as R                                   # noqa: E402

REPORTS = _REPO / "ops" / "reports"


def _rec(task, seq, status="ok", validity="valid", l3=True, arm="strict", **kw) -> dict:
    from runner.c42.failure_modes import sr_bucket
    r = {"task_id": task, "stage": "S1", "config_id": "cfg-x", "arm": arm, "seq": seq,
         "run_status": status, "sr_bucket": sr_bucket(status), "validity": validity,
         "malformed": status == "malformed", "l3_pass": l3, "steps": 5, "latency_s": 10.0,
         "tokens_prompt": 100, "tokens_completion": 20, "validator_rejections": None,
         "overreach": None}
    r.update(kw)
    return r


# ══════════════════════════════════ finding 2（major）：撞闸的判据是 429，不是 run_status

BUDGET_HIT = {"limit": "tokens", "used": 642132, "max": 600000}


def test_budget_exhausted_runs_counts_the_gate_not_the_status():
    """撞了闸**但已经把 artifact 写下来**的 run：`run_status` 是 `ok`，它同样是被预算停下的。

    v1demo 实测就是这一格失真：8 个 run 全部撞了 600k token 闸，其中两个因为已经写下
    artifact 而判 `run_status=ok`，旧口径于是两臂各写 3，真值是 4/4 —— 而漏掉的那两个
    恰是全表仅有的两个进了 pass@1 分子的 run。
    """
    recs = [_rec("t1", 1, budget=dict(BUDGET_HIT)),                       # 撞闸，交了卷
            _rec("t2", 1, status="budget_exhausted", validity=None, l3=None,
                 budget=dict(BUDGET_HIT)),                                # 撞闸，交白卷
            _rec("t3", 1)]                                                # 没撞
    row = R.table_a(recs)[0]
    assert row["budget_exhausted_runs"] == 2, "「撞闸但交了卷」的那个 run 必须也算进来"
    assert row["n_runs"] == 3


def test_budget_exhausted_runs_falls_back_to_status_for_old_records():
    """旧记录没有 `budget` 键（N-130 之前）→ 退回状态口径，**只多不少**。"""
    recs = [_rec("t1", 1, status="budget_exhausted", validity=None, l3=None)]
    assert R.table_a(recs)[0]["budget_exhausted_runs"] == 1


def test_budget_exhausted_runs_is_zero_when_nobody_hit_the_gate():
    """恒绿也要钉：没人撞闸就是 0，别把「没撞」写成「撞了」。"""
    assert R.table_a([_rec("t1", 1), _rec("t1", 2)])[0]["budget_exhausted_runs"] == 0


def test_v1demo_reports_four_of_four_budget_capped_runs():
    """真数据：v1demo 两臂各 4 个 run，**全部**撞了默认档 token 闸。"""
    p = REPORTS / "v1demo" / "records.json"
    if not p.is_file():
        pytest.skip("ops/reports/v1demo/records.json 不在本机上")
    recs = json.loads(p.read_text(encoding="utf-8"))
    rows = R.table_a(recs)
    assert rows, "v1demo 出不来行"
    for row in rows:
        assert row["budget_exhausted_runs"] == row["n_runs"] == 4, \
            f"{row['arm']} 臂：撞闸 {row['budget_exhausted_runs']} / {row['n_runs']} —— " \
            f"这一批 8/8 撞了 600k token 闸，主表上的 SR/pass@1 读的是预算不是能力"


# ══════════════════════════════════ finding 3（major）：0 与「不可得」必须分得开

def test_unbounded_requests_zero_is_not_none():
    """一次都没发过无右端取数请求（我们想看到的好结果）不能与「网关日志不可得」同形。"""
    row = R.table_a([_rec("t1", 1, unbounded_requests=0), _rec("t1", 2, unbounded_requests=0)])[0]
    assert row["unbounded_requests"] == 0
    assert row["unbounded_requests"] is not None


def test_unbounded_requests_none_when_no_sample():
    """一条可用样本都没有 → None（CSV 空串 / LaTeX `---`）。"""
    row = R.table_a([_rec("t1", 1, unbounded_requests=None)])[0]
    assert row["unbounded_requests"] is None


def test_unbounded_requests_sums_available_samples():
    recs = [_rec("t1", 1, unbounded_requests=8), _rec("t1", 2, unbounded_requests=0),
            _rec("t1", 3, unbounded_requests=None)]
    assert R.table_a(recs)[0]["unbounded_requests"] == 8


def test_unbounded_requests_zero_reaches_the_csv_as_zero(tmp_path):
    """落盘那一跳也要判：`write_csv` 把 None 写成空串，0 必须还是 `0`。"""
    rows = R.table_a([_rec("t1", 1, unbounded_requests=0)])
    p = R.write_csv(rows, tmp_path / "a.csv", R.TABLE_A_COLUMNS)
    line = p.read_text(encoding="utf-8").splitlines()
    cols = line[0].split(",")
    val = line[1].split(",")[cols.index("unbounded_requests")]
    assert val == "0", f"CSV 里写的是 {val!r} —— 空串会被读成「网关日志不可得」"


# ══════════════════════════════════ finding 4（major）：协议轴逐 run，不是批级声明

def _inject(protocol: bool) -> dict:
    files = {"work/artifact_schema.md": "a" * 64}
    if protocol:
        files.update({f"work/protocol/{n}": f"{i}" * 64 for i, n in enumerate(DB.PROTOCOL_STATIC)})
    return {"files": files}


def _fake_rec(run_id: str, *, batch: str, arm: str, **over) -> dict:
    rec = {"task_id": "s1-cor-01", "stage": "S1", "config_id": "cfg-x", "arm": arm, "seq": 1,
           "run_id": run_id, "batch": batch,
           "set_version": "1.0.13", "reference_version": "r1.0.20",
           "run_status": "ok", "sr_bucket": "scorable", "validity": "valid", "malformed": False,
           "correctness": {"Cov": 1.0}, "effect": 100.0, "l3_kind": "cov", "l3_pass": True,
           "l3_score": 1.0, "steps": 3, "tokens_prompt": 10, "tokens_completion": 2,
           "cost_usd": 0.01, "probe_states": {"calendar": "clean"},
           "overreach": {"denied": 0, "total": 4}, "unbounded_requests": 0, "budget": None}
    rec.update(over)
    return rec


def _lay_out_batch(root: Path, batch: str, runs: dict[str, bool]) -> tuple[Path, Path]:
    """`runs`: `run_id → 这次注入有没有协议工件`。返回 `(reports, runs_in)`。"""
    reports, runs_in = root / "reports", root / "runs_in"
    (reports / batch).mkdir(parents=True)
    recs = [_fake_rec(rid, batch=batch, arm=("strict" if has else "open"))
            for rid, has in runs.items()]
    (reports / batch / "records.json").write_text(json.dumps(recs), encoding="utf-8")
    for rid, has in runs.items():
        d = runs_in / batch / rid
        d.mkdir(parents=True)
        (d / "inject.json").write_text(json.dumps(_inject(has)), encoding="utf-8")
    return reports, runs_in


def test_protocol_by_run_marks_bare_arms_explicitly(tmp_path):
    """裸臂的取值是 `NO_PROTOCOL`（一个**显式的事实**），不是 None（「不知道」）。"""
    _, runs_in = _lay_out_batch(tmp_path, "b", {"r_gq": True, "r_bare": False})
    got = DB.protocol_by_run("b", runs_in)
    assert got["r_bare"] == DB.NO_PROTOCOL
    assert got["r_gq"].startswith("geneprotocol_v1@") and got["r_gq"] != DB.NO_PROTOCOL


def test_protocol_axis_is_per_run(tmp_path):
    """入库之后：协议臂带摘要、裸臂带 none —— 批级声明不再盖在裸臂上。"""
    reports, runs_in = _lay_out_batch(tmp_path, "b", {"r_gq": True, "r_bare": False})
    DB.backfill_batch("b", root=tmp_path / "db", reports=reports, runs_in=runs_in)
    rows = {r["run_id"]: r["protocol_version"] for r in DB.load(tmp_path / "db")}
    assert rows["r_bare"] == DB.NO_PROTOCOL
    assert rows["r_gq"] != DB.NO_PROTOCOL


def test_filter_by_protocol_digest_excludes_bare_arms(tmp_path):
    """立卡理由：`--filter protocol_version=<摘要>` 不该选出从来没见过该协议的 run。"""
    reports, runs_in = _lay_out_batch(tmp_path, "b", {"r_gq": True, "r_bare": False})
    DB.backfill_batch("b", root=tmp_path / "db", reports=reports, runs_in=runs_in)
    digest = DB.protocol_by_run("b", runs_in)["r_gq"]
    got = DB.query(tmp_path / "db", protocol_version=digest)
    assert [r["run_id"] for r in got] == ["r_gq"]


def test_none_beside_a_digest_is_not_mixed_axes(tmp_path):
    """同一批两个臂跑在同一次发布上 —— 那不是混轴，否则每一批都出不来表。"""
    reports, runs_in = _lay_out_batch(tmp_path, "b", {"r_gq": True, "r_bare": False})
    DB.backfill_batch("b", root=tmp_path / "db", reports=reports, runs_in=runs_in)
    rows, axes = MT.select({"batch": "b"}, root=tmp_path / "db")     # 不放行也必须出得来
    assert len(rows) == 2 and axes["mixed_axes"] == {}
    notes = MT.axes_notes(axes)
    assert any(DB.NO_PROTOCOL in n for n in notes), "脚注要说清楚裸臂那一格是什么"
    assert not any("protocol_version 混轴" in n for n in notes)


def test_two_digests_are_still_mixed_axes(tmp_path):
    """真正要拦的那一条不能被放松：协议臂之间出现两个摘要 = 混轴。"""
    db = tmp_path / "db"
    a = _fake_rec("r1", batch="b1", arm="strict", protocol_version="geneprotocol_v1@aaaaaaaaaaaa",
                  channel="private", seed=1, track="main", budget_exhausted=False)
    b = _fake_rec("r2", batch="b2", arm="strict", protocol_version="geneprotocol_v1@bbbbbbbbbbbb",
                  channel="private", seed=1, track="main", budget_exhausted=False)
    DB.ingest([a, b], root=db)
    assert "protocol_version" in DB.mixed_axes(DB.load(db))
    with pytest.raises(MT.MixedAxesError, match="protocol_version"):
        MT.select({}, root=db)


def test_pure_baseline_batch_can_enter_the_db(tmp_path):
    """纯裸臂的批（oracle / null_agent / 控制批）以前永远进不了库 —— 现在按 `none` 收。"""
    reports, runs_in = _lay_out_batch(tmp_path, "ctl", {"r1": False, "r2": False})
    r = DB.backfill_batch("ctl", root=tmp_path / "db", reports=reports, runs_in=runs_in)
    assert r["protocol_version"] == DB.NO_PROTOCOL and r["added"] == 2


def test_backfill_still_refuses_when_nothing_can_be_read(tmp_path):
    """恒红不绕过：连 `inject.json` 都读不到 = 真的不知道，仍然拒。"""
    reports = tmp_path / "reports" / "zz"
    reports.mkdir(parents=True)
    (reports / "records.json").write_text(
        json.dumps([_fake_rec("r1", batch="zz", arm="open")]), encoding="utf-8")
    with pytest.raises(DB.ResultsDBError, match="协议轴反算不出"):
        DB.backfill_batch("zz", root=tmp_path / "db", reports=tmp_path / "reports",
                          runs_in=tmp_path / "runs_in")


def test_backfill_refuses_a_batch_that_spans_two_protocol_versions(tmp_path):
    """一批里两个摘要 → 人来裁定，不选一个。"""
    reports, runs_in = _lay_out_batch(tmp_path, "b", {"r1": True})
    d = runs_in / "b" / "r2"
    d.mkdir(parents=True)
    files = {f"work/protocol/{n}": "f" * 64 for n in DB.PROTOCOL_STATIC}
    (d / "inject.json").write_text(json.dumps({"files": files}), encoding="utf-8")
    with pytest.raises(DB.ResultsDBError, match="协议摘要"):
        DB.backfill_batch("b", root=tmp_path / "db", reports=reports, runs_in=runs_in)


# ══════════════════════════════════ finding 1（block）：文档到得了这四个入口

STAGE5_ENTRIES = ("ops/joblist.py", "ops/run_joblist.py", "ops/results_db.py", "ops/mk_tables.py")


@pytest.mark.parametrize("rel", STAGE5_ENTRIES)
def test_stage5_entry_exists(rel):
    """双向判据的一端：这四个入口是真的（文档里写的不是幻觉）。"""
    assert (_REPO / rel).is_file(), f"{rel} 不在仓库里"


@pytest.mark.parametrize("rel", STAGE5_ENTRIES)
def test_handoff_has_stage5_section(rel):
    """另一端：HANDOFF 有阶段五一节，且四个入口都在里面被点过名。

    红队 5.rt finding 1（block）：在这一节之前，`grep -rln 'joblist' --include=*.md` 只命中
    代理自己的票据 —— 外部用户只凭 README + HANDOFF **走不到**这四个入口，连「有这么个
    东西」都不知道。
    """
    body = (_REPO / "ops" / "HANDOFF.md").read_text(encoding="utf-8")
    assert "## 16. 阶段五" in body, "HANDOFF 没有阶段五一节"
    assert f"`{rel}`" in body, f"HANDOFF §16 没点名 {rel}"


def test_handoff_stage5_has_a_copyable_recipe():
    """§16 要有「跑法（照抄）」，形态与 §12.5 / §14.3 一致 —— 不是一段说明文字。"""
    body = (_REPO / "ops" / "HANDOFF.md").read_text(encoding="utf-8")
    sec = body[body.index("## 16. 阶段五"):]
    assert "跑法（照抄" in sec
    for frag in ("ops/joblist.py gen --matrix", "ops/run_joblist.py --jobs", "--dry",
                 "ops/results_db.py ingest --batch", "ops/mk_tables.py --table"):
        assert frag in sec, f"§16 的跑法里没有 `{frag}`"
    assert "harnesses/" in sec and "digest" in sec, "矩阵字段表要写明 digest 从哪儿取"


def test_readme_points_at_the_joblist_entry():
    """README 一个字都没提过阶段五 —— 至少要把四个入口与 HANDOFF §16 指出来。"""
    body = (_REPO / "README.md").read_text(encoding="utf-8")
    for frag in ("ops/run_joblist.py", "ops/results_db.py", "ops/mk_tables.py", "ops/joblist.py"):
        assert frag in body, f"README 没提 {frag}"
    assert "§16" in body, "README 要指向 HANDOFF §16（照抄的命令与坑在那里）"
