# -*- coding: utf-8 -*-
"""收尾卡 v2 红队修复（V2.rt）：七条 block / major 的定向回归。

每一条测试对着一条 finding，写清「它当初错在哪」——
红队抓到的都是**恒绿**或**发布件与实现说得不一样**这两类，
它们的共同点是：不写测试的话，下一次改动照样不会报错。
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from ops import mk_metric_tables as MM                      # noqa: E402
from ops import mk_release_manifest as MRM                  # noqa: E402
from ops import mk_tables as MT                             # noqa: E402
from ops import results_db as DB                            # noqa: E402
from scorer import report as R                              # noqa: E402

REPORTS = REPO / "ops" / "reports"

#: 全库唯一一条**真诚实终止**：`correct_handling=True`、闸门 valid、`l3_pass=True`，
#: 而且**同时带一条预算记录**（它把预算用到闸上才如实停下）。finding 1 就卡在这里。
HONEST_HALT_RUN = "s7-rob-02.strict.cfg-codex-deepseek.r01"


def _db_records() -> list[dict]:
    try:
        # **不取已作废的行**：出表口（`ops/mk_tables.py` / `ops/mk_metric_tables.py`）
        # 今天都按 `superseded=None` 取，这里取全库的话，作废的读数会和现行的
        # 被算进同一个比率（2026-09-12 实测：S7 那一格由 1/5 变成 3/9）。
        rows = DB.query(None, superseded=None)
    except Exception as e:                                   # noqa: BLE001
        pytest.skip(f"结果库读不到：{e}")
    if not rows:
        pytest.skip("结果库是空的")
    return rows


# ================================================================ finding 1：honest_halt_rate 恒 0

def _rec(**kw):
    base = {"task_id": "t1", "stage": "S1", "config_id": "cfg-x", "arm": "open",
            "run_status": "ok", "validity": "valid", "l3_pass": True, "correctness": {}}
    base.update(kw)
    return base


def test_honest_halt_wins_over_a_budget_record():
    """诚实终止的 run 常常**同时**带预算记录 —— 先判 budget 就再也判不出 honest_halt。

    这正是 finding 1 的第一半：全库唯一一条真诚实终止被判成 `budget_exhausted`，
    于是 `honest_halt_rate` 这一列在 42 行里全是 0.0。
    """
    r = _rec(correct_handling=True, budget={"calls": 50, "max_calls": 50})
    assert R.withheld_reason(r) == "honest_halt"
    assert R.WITHHELD_REASONS[0] == "honest_halt", "顺序即优先级 —— 诚实终止判在最前"


def test_a_run_with_a_reading_is_not_withheld_at_all():
    """finding 1 的第二半：**给得出读数就是 None**（本函数 docstring 的原义）。

    闸门 valid + `l3_pass` 有值 = 有读数，哪怕它路上撞过预算闸。
    之前这种 run 被算进「没有读数」，会把本该是 `unobservable` 的格子写成 `—`。
    """
    assert R.withheld_reason(_rec(budget={"calls": 50})) is None
    assert R.withheld_reason(_rec(validity="valid", l3_pass=False)) is None
    #: 但「没有 l3_pass」仍然是未结算，「闸门没过」仍然是拒绝 —— 短路不许吃掉这两类。
    assert R.withheld_reason(_rec(l3_pass=None)) == "unsettled"
    assert R.withheld_reason(_rec(validity="invalid", l3_pass=None)) == "rejected"


def test_the_real_honest_halt_record_is_classified_as_such():
    recs = _db_records()
    hit = [r for r in recs if r.get("run_id") == HONEST_HALT_RUN]
    if not hit:
        pytest.skip(f"结果库里没有 {HONEST_HALT_RUN}")
    r = hit[0]
    assert r.get("correct_handling") is True and r.get("validity") == "valid"
    assert r.get("budget"), "这条记录本来就带预算记录 —— 没有它这条测试就失去判别力"
    assert R.withheld_reason(r) == "honest_halt"


def test_honest_halt_rate_is_not_structurally_zero():
    """一个**结构上永远为 0** 的列，与一个真的零命中在表上长得一模一样。

    规格 §9.3 对这一列的注是「它高不是坏事，那是协议要的行为」——
    恒 0 正好把那句话变成看不出来的假话。
    """
    recs = _db_records()
    rows = MM.stage_table(recs)
    cell = [x for x in rows
            if (x["config_id"], x["arm"], x["stage"]) == ("cfg-codex-deepseek", "strict", "S7")]
    if not cell:
        pytest.skip("库里没有 (cfg-codex-deepseek, strict, S7) 这一格")
    #: **从同一批记录独立算一遍**，不钉死某一天的库快照：钉死的话，
    #: 库里多收一批 run 就会把这条测试跑红，而它要拦的是「这一列结构上恒 0」。
    mine = [r for r in recs
            if (r.get("config_id"), r.get("arm"), r.get("stage")) ==
            ("cfg-codex-deepseek", "strict", "S7")]
    want = sum(1 for r in mine if r.get("correct_handling") is True) / len(mine)
    assert want > 0, "这一格现在一条诚实终止都没有了 —— 判别力的前提没了，换一格再钉"
    assert cell[0]["honest_halt_rate"] == pytest.approx(want), \
        (f"{sum(1 for r in mine if r.get('correct_handling') is True)} 条诚实终止 / "
         f"{len(mine)} 条 run = {want}；写成 0.0 就是 finding 1 的原样")
    assert any((x.get("honest_halt_rate") or 0) > 0 for x in rows), "全表恒 0 = 恒绿"


# ================================================================ finding 7：宽表的第五态

def test_not_applicable_is_a_fifth_state_distinct_from_empty():
    """「这个量在 S3 上不适用」与「S3 一道题都没跑」不许同形。"""
    recs = [_rec(stage="S1", correctness={"Cov": 1.0}), _rec(stage="S8", correctness={"Audit": 1.0})]
    rows = MM.stage_table(recs)
    by = {r["stage"]: r for r in rows}
    assert by["S1"]["Audit"] == R.NOT_APPLICABLE, "S8 的 Audit 在 S1 行上是**不适用**"
    assert by["S8"]["Cov"] == R.NOT_APPLICABLE
    assert by["S1"]["Cov"] == 1.0, "本阶段定义的量照旧出数"
    assert R.NOT_APPLICABLE not in (None, "", R.NO_READING, R.UNOBSERVABLE)


def test_not_applicable_renders_differently_in_three_formats(tmp_path):
    recs = [_rec(stage="S1", correctness={"Cov": 1.0}), _rec(stage="S8", correctness={"Audit": 1.0})]
    rows = MM.stage_table(recs)
    cols = MM.stage_columns(rows)
    p = R.write_csv(rows, tmp_path / "stage.csv", cols)
    got = list(csv.DictReader(open(p, newline="", encoding="utf-8")))
    assert got[0]["Audit"] == "n/a", "CSV 里写 `n/a` 本身，不是空"
    md = MT.to_markdown(rows, cols, caption="阶段表")
    assert "n/a" in md
    tex = R.to_latex(rows, ("stage", "Audit"), caption="阶段表", label="tab:s")
    assert r"\textit{n/a}" in tex, "LaTeX 上它不许写成 `---`（那是「没有 run」）"


def test_the_published_stage_table_has_no_unfilled_gap_on_defined_metrics():
    """落盘的那张宽表：不适用的格必须是 `n/a`，空只留给「一个 run 都没有」。"""
    f = REPORTS / "m6_public" / "metrics_stage.csv"
    if not f.is_file():
        pytest.skip("没有落盘的 metrics_stage.csv")
    rows = list(csv.DictReader(open(f, newline="", encoding="utf-8")))
    every = {n for st in MM.STAGES for n, _r, _h, _k in MM.STAGE_METRICS.get(st, ())}
    for row in rows:
        mine = {n for n, _r, _h, _k in MM.STAGE_METRICS.get(row["stage"], ())}
        for col in (every & set(row)) - mine:
            assert row[col] == "n/a", f"{row['stage']} 行的 {col} 不适用，却写成 {row[col]!r}"


# ================================================================ finding 2：VERSIONS.md 的正文

def test_versions_doc_matches_the_axes():
    axes = MRM.build()["axes"]
    bad = MRM.versions_doc_drift(axes)
    assert not bad, "VERSIONS.md 是四条轴的权威文档，它的正文写错了：\n  " + "\n  ".join(bad)


def test_the_versions_drift_check_would_catch_a_stale_doc(tmp_path):
    """判别力：把正文改回旧版本号，这道门必须红。

    finding 2 的根因就是**没有任何一道门读这份文件的正文** ——
    `axes` 段对、sha 也对（清单是在文件之后生成的），漂移于是静默通过。
    """
    fake = tmp_path / "VERSIONS.md"
    body = (REPO / "VERSIONS.md").read_text(encoding="utf-8")
    axes = MRM.build()["axes"]
    fake.write_text(body.replace(f"**{axes['set_version']}**", "**1.0.14**"), encoding="utf-8")
    bad = MRM.versions_doc_drift(axes, repo=tmp_path)
    assert bad and any("1.0.14" in b for b in bad), f"篡改没被抓到：{bad}"


def test_release_manifest_check_is_wired_to_that():
    src = (REPO / "ops" / "mk_release_manifest.py").read_text(encoding="utf-8")
    assert "versions_doc_drift(cur[\"axes\"])" in src, "--check 必须先查 VERSIONS.md 正文"


# ================================================================ finding 3：metrics_as_implemented 的 Role

#: Role → 这份「描述实现」的文档里必须出现的措辞。
_ROLE_WORD = {"gate": "**判**", "reported": "**只报不判**"}


@pytest.mark.parametrize("metric", ["FillSelfConsistent", "SlipSelfConsistent"])
def test_self_consistency_metrics_are_documented_as_gates(metric):
    """发布文档上这两条的 Role 必须与生成器一致。

    它们**都进 `l3_pass`**（`scorer/l3.py:758` 与 `Audit` 三取均值后要求 == 1.0），
    而文档曾经写着「只报不判」、并且挂着一句「待用户签字」——
    读者按那一版会以为 Fill / Slip 不影响判据。
    （这条测试放在这里而不是 `ops/test_metrics_as_implemented.py`：那份文件自己声明
    **不 import `scorer/`**，而这条判据要拿生成器里的 Role 当真相。）
    """
    role = {n: r for n, r, _h, _k in MM.STAGE_METRICS["S8"]}[metric]
    doc = (REPO / "ops" / "specs" / "metrics_as_implemented_v1.md").read_text(encoding="utf-8")
    row = [l for l in doc.splitlines() if l.startswith("|") and metric in l]
    assert row, f"文档里没有 {metric} 这一行"
    want = _ROLE_WORD[role]
    for line in row:
        assert want in line, f"{metric} 的 Role 是 {role}，文档那一行却没写 {want}：{line[:80]}"
    assert "待用户签字" not in doc, "N-383 的「待用户签字」是 Slip 与 gold 对照那件事，不是这条判据"


def test_the_one_pager_lists_slip_self_consistency_as_judged():
    doc = (REPO / "ops" / "specs" / "metrics_as_implemented_v1.md").read_text(encoding="utf-8")
    head = doc.split("**真的进判据的**")[1].split("**出数但不判**")[0]
    assert "SlipSelfConsistent" in head


# ================================================================ finding 4：手册首页 vs 清单

def _manual_section_0_1() -> str:
    t = (REPO / "docs" / "OPERATOR_MANUAL.md").read_text(encoding="utf-8")
    body = t.split("### 0.1 ")[1]
    return body.split("### 0.2")[0]


def test_manual_front_page_does_not_contradict_the_blockers():
    """首页那一节自己写着「权威条数以 RELEASE_MANIFEST.json 的 blockers 为准」。

    那就别让它与清单打架：清单里 satisfied 的条数 == 首页标成「已闭合」的条数。
    finding 4 的原样是「公开通道一个 run 都没有」，而清单里那条已经 satisfied。
    """
    sec = _manual_section_0_1()
    manifest = json.loads((REPO / "RELEASE_MANIFEST.json").read_text(encoding="utf-8"))
    satisfied = [b for b in manifest["blockers"] if b.get("satisfied")]
    items = re.split(r"(?m)^\d+\. ", sec)[1:]
    assert len(items) == len(manifest["blockers"]), \
        f"首页 {len(items)} 条、清单 {len(manifest['blockers'])} 条 —— 两份对不上就别维护第二份"
    closed = [it for it in items if "已闭合" in it]
    assert len(closed) == len(satisfied), (
        f"清单里 {len(satisfied)} 条已满足，首页只标了 {len(closed)} 条已闭合")
    #: 那句话可以留着（划掉的原文是有用的历史），但不许**还立着**。
    live = [it for it in items if "公开通道一个 run 都没有" in it and "已闭合" not in it]
    assert not live, "「公开通道一个 run 都没有」还立在首页上，而批 m6_public 有 8 个真 run"


def test_public_channel_really_has_settled_runs():
    """把手册那一句话钉在数据上，而不是钉在另一份文档上。"""
    recs = [r for r in _db_records() if r.get("batch") == "m6_public"]
    assert len(recs) >= 8, f"m6_public 只有 {len(recs)} 条结算记录"


# ================================================================ finding 5：两份报告里的 S6 占位串登记

@pytest.mark.parametrize("rel", ["ops/reports/known_limits_v1.md", "ops/reports/v1_0_readiness.md"])
def test_s6_placeholder_is_registered_as_fixed(rel):
    t = (REPO / rel).read_text(encoding="utf-8")
    assert "已于 r1.0.22 修复" in t, "裁定 ② 的走法 ① 已经落地，状态列不能还写「v1.1 待批 / 本版不修」"
    assert "v1.1（要改冻结根，已进 pending_freeze_bumps）" not in t
    assert "已发表的适配表因此**偏低约 13 个百分点**" not in t, "这件事要写成过去式"
    assert "0.7667" in t, "现在发布的那张表是改正后的，把数写出来"


def test_the_published_adapt_table_is_the_corrected_one():
    f = REPORTS / "adapt" / "table.csv"
    if not f.is_file():
        pytest.skip("没有适配表")
    rows = {r["level"]: r for r in csv.DictReader(open(f, newline="", encoding="utf-8"))
            if "level" in r}
    if "ALL" not in rows:
        pytest.skip(f"适配表的列不是预期的形状：{list(rows)[:3]}")
    assert float(rows["ALL"]["resolved_rate"]) == pytest.approx(0.7667, abs=1e-3)


# ================================================================ finding 6：签字包

def test_archive_declares_the_main_table():
    from ops import archive_signoff as AS
    for item in ("m6_all/table_main.csv", "m6_all/table_main.tex"):
        assert item in AS.ITEMS, f"签字包件清单里必须有主表：缺 {item}"


def _latest_signed() -> Path | None:
    axes = json.loads((REPO / "RELEASE_MANIFEST.json").read_text(encoding="utf-8"))["axes"]
    p = REPO / "ops" / "reports" / "signed" / f"v{axes['set_version']}_{axes['reference_version']}"
    return p if p.is_dir() else None


def test_the_current_axes_have_a_signed_package():
    """四轴要在**三处**一致：表脚注 / RELEASE_MANIFEST / 签字包。第三处不能缺。"""
    p = _latest_signed()
    assert p is not None, "当前轴上没有签字包 —— 跑 `$PY ops/archive_signoff.py --label …`"
    m = json.loads((p / "MANIFEST.json").read_text(encoding="utf-8"))
    axes = json.loads((REPO / "RELEASE_MANIFEST.json").read_text(encoding="utf-8"))["axes"]
    assert (m["set_version"], m["reference_version"]) == (axes["set_version"], axes["reference_version"])
    assert m["set_root"] == axes["set_root"] and m["reference_root"] == axes["reference_root"]
    assert "m6_all/table_main.csv" in m["files"], "包里必须真的有主表，不是只在清单里声明"
    assert (p / "README.md").is_file(), "包内要有一页说清哪张表是发布表"


def test_no_release_table_in_the_package_carries_an_aggregate_column():
    """⑪：effect 与一切总分列**不进发布表**。诊断表照旧归档，但要在 README 里标出来。"""
    p = _latest_signed()
    if p is None:
        pytest.skip("当前轴上没有签字包")
    m = json.loads((p / "MANIFEST.json").read_text(encoding="utf-8"))
    for rel in m["tables"]["release"]:
        f = p / rel.replace("/", "__")
        if not f.is_file() or not f.name.endswith(".csv"):
            continue
        head = next(csv.reader(open(f, newline="", encoding="utf-8")))
        bad = [c for c in head if c.strip().lower() in R.AGGREGATE_COLUMN_NAMES]
        assert not bad, f"{rel} 是发布表，表头里却有聚合列 {bad}"
    readme = (p / "README.md").read_text(encoding="utf-8")
    for rel in m["tables"]["internal_diagnostic"]:
        assert rel.replace("/", "__").split(".")[0] in readme or "诊断表" in readme
