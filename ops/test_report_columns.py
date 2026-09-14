# -*- coding: utf-8 -*-
"""卡 C（2026-09-10 用户裁定 ⑩⑪⑫⑬）：主表十九列 / 取消聚合 / 空值三态 / 指标集与规格逐项相等。

这一份钉的是**报告器的口径**，不是聚合算法（那由 `ops/test_scorer_report.py` 钉）：

* ⑩ 主表**固定十九列**，列名与顺序写死 —— 列集相等 + 顺序相等，两条都断言；
* ⑪ **不出总分**；`effect` 不进发布表；「拒绝 / 诚实终止 / 未结算 / 预算截断」
  四类各造一条夹具，**CSV / Markdown / LaTeX 三种格式各断言一次**渲染成 `—`；
* ⑫ 生成器的指标集与 `ops/specs/GeneBench指标规格_v1.md` §9 登记的指标集**逐项相等**；
* ⑬ 核六列（`Prov` / `Decl` / `Set` / `W-agr` / `Ledger` / `Ovr`）算得出来，
  算不出的**标 `unobservable`**（不是 0、不是 `—` —— 三者语义不同）。
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from ops import mk_metric_tables as MM                        # noqa: E402
from ops import mk_tables as MT                               # noqa: E402
from scorer import l3 as L3                                   # noqa: E402
from scorer import report as R                                # noqa: E402

#: 十九列的**字面量**。这份列表故意与 `scorer/report.py` 重抄一遍 ——
#: 「改了实现忘了改裁定」正是这条测试要拦的，引用实现就拦不住了。
NINETEEN: tuple[str, ...] = (
    "SR", "P@1", "$",
    "Cov", "Prov",
    "Cell%", "Adj",
    "Fid", "Decl",
    "IC-agr", "Set",
    "Sig", "ρ̄",
    "W-agr", "Cons",
    "ε-agr", "Ledger",
    "Audit", "Ovr",
)

#: ⑬ 的核六列。
CORE_SIX: tuple[str, ...] = ("Prov", "Decl", "Set", "W-agr", "Ledger", "Ovr")


def _rec(task, seq, *, stage="S1", status="ok", validity="valid", l3=True,
         cfg="cfg-x", arm="strict", **kw):
    from runner.c42.failure_modes import sr_bucket
    r = {"task_id": task, "stage": stage, "config_id": cfg, "arm": arm, "seq": seq,
         "run_status": status, "sr_bucket": sr_bucket(status), "validity": validity,
         "malformed": status == "malformed", "l3_pass": l3, "steps": 5, "latency_s": 10.0,
         "tokens_prompt": 100, "tokens_completion": 20,
         "validator_rejections": None, "overreach": None, "correctness": {}}
    r.update(kw)
    return r


# ================================================================ ⑩ 固定十九列

def test_main_table_columns_are_frozen_nineteen():
    assert len(R.MAIN_TABLE_COLUMNS) == 19, "主表就是十九列（⑩）"
    assert set(R.MAIN_TABLE_COLUMNS) == set(NINETEEN), "列集相等"
    assert tuple(R.MAIN_TABLE_COLUMNS) == NINETEEN, "顺序也相等 —— 顺序变了，两次发布的表并排读不了"
    assert len(set(R.MAIN_TABLE_COLUMNS)) == 19, "列名不许重复"


def test_main_table_stage_columns_cover_eight_stages_two_each():
    """每阶段两列，八个阶段一个不缺（⑩）。"""
    from collections import Counter
    per = Counter(st for _c, st, _h, _k in R.STAGE_COLUMN_SOURCES)
    assert sorted(per) == [f"S{i}" for i in range(1, 9)]
    assert set(per.values()) == {2}, f"每阶段两列，实际 {dict(per)}"
    cols = [c for c, _st, _h, _k in R.STAGE_COLUMN_SOURCES]
    assert cols == list(NINETEEN[3:]), "十六个阶段列的顺序必须与十九列的后十六位一致"


def test_main_table_rows_have_exactly_index_plus_nineteen():
    rows = R.main_table([_rec("t1", 1)])
    assert set(rows[0]) == set(R.TABLE_A_INDEX_COLUMNS) | set(NINETEEN)


# ================================================================ ⑥-c S2 的保真列

def test_s2_fidelity_column_is_cellagree_not_align():
    """⑥-c：S2 的保真列是 `Cell%`（取 `CellAgree`），`Align` 不在主表上。

    为什么换：`Align` 量的是**申报**（字段映射对不对），`CellAgree` 量的是**内容**
    （面板逐格对不对）。真记录里两者分叉，且方向对被测方有利 —— 见 `S2_SPLIT_EVIDENCE`。
    """
    src = {c: (st, how, key) for c, st, how, key in R.STAGE_COLUMN_SOURCES}
    assert "Cell%" in R.MAIN_TABLE_COLUMNS, "S2 的保真列表头是 `Cell%`"
    assert "Align" not in R.MAIN_TABLE_COLUMNS, \
        "`Align` 只量申报，不该占主表 S2 的保真列（⑥-c）"
    assert src["Cell%"] == ("S2", "correctness", "CellAgree"), \
        f"`Cell%` 必须取 `CellAgree` 这个键，实际 {src.get('Cell%')}"
    assert src["Adj"] == ("S2", "correctness", "Adj"), "`Adj` 留作 S2 的有效性列（⑥-c）"


#: ⑥-c 的判据不是「谁听起来更对」，是**库里真有一条这样的记录**。
#: 路径写在这里，是为了让下一个想把这一列换回去的人先去看那份 json。
S2_SPLIT_EVIDENCE = (
    "ops/reports/i_rehearsal_v2/scores/s2-cor-01.strict.cfg-codex-deepseek.r02.score.json")


def test_align_and_cellagree_really_do_diverge_on_a_real_record():
    """有一条真记录 `Align = 1.0` 而 `CellAgree = 0.0` —— 换列的理由就在这一条上。

    本机没有这份记录时跳过（它是跑批产物，不是仓库的冻结件）。
    """
    import json
    p = Path(R.__file__).resolve().parents[1] / S2_SPLIT_EVIDENCE
    if not p.is_file():
        pytest.skip(f"本机没有 {S2_SPLIT_EVIDENCE}")

    def _find(o, k, acc):
        if isinstance(o, dict):
            for kk, vv in o.items():
                if kk == k:
                    acc.append(vv)
                _find(vv, k, acc)
        elif isinstance(o, list):
            for x in o:
                _find(x, k, acc)
        return acc

    d = json.loads(p.read_text(encoding="utf-8"))
    align = _find(d, "Align", [])
    cell = _find(d, "CellAgree", [])
    assert align and cell, f"{S2_SPLIT_EVIDENCE} 里没有 Align / CellAgree —— 证据没了，重找一条"
    assert float(align[0]) == 1.0 and float(cell[0]) == 0.0, (
        f"这份记录不再是「Align 满分、CellAgree 零分」那一条（Align={align[0]}、"
        f"CellAgree={cell[0]}）—— 换一条真记录来支撑 ⑥-c，别删这条测试")


def test_align_stays_in_the_stage_metric_table():
    """换列**不等于**不再算 `Align`：它照旧在全量阶段指标表的 S2 里（规格 §9.2）。"""
    assert ("S2", "Align") in MM.stage_metric_pairs()
    assert ("S2", "CellAgree") in MM.stage_metric_pairs()


# ================================================================ ⑥-b table_a 是诊断件

def test_table_a_is_never_a_release_table():
    """⑥-b：发布表只有三张（主表 + 两张全量指标表）。`table_a` / `table_b` 是诊断件。"""
    from ops import archive_signoff as AS
    from ops import mk_release_manifest as MR
    rel = set(AS.RELEASE_TABLES)
    assert rel, "发布表清单空了 —— 那不是「没有诊断件」，是签字包不再说明哪张能引用"
    for f in rel:
        assert f.rsplit("/", 1)[-1].split(".")[0] in ("table_main", "metrics_agent", "metrics_stage"), \
            f"发布表清单里出现了 {f} —— ⑥-b 只留主表与两张全量指标表"
    for f in AS.DIAGNOSTIC_TABLES:
        assert f not in rel, f"{f} 同时在发布表与诊断表两张清单里"
    #: 发布件清单（`RELEASE_ITEMS`）里一件诊断件都不许有。
    for group, items in MR.RELEASE_ITEMS.items():
        for rel_path in items:
            name = rel_path.rsplit("/", 1)[-1]
            assert name not in MR.DIAGNOSTIC_NOT_RELEASE, \
                f"发布件清单的「{group}」里出现了诊断件 {rel_path}（⑥-b）"


def test_diagnostic_note_says_it_is_not_a_release_artifact(tmp_path):
    """落盘 `table_a` 时旁边那份说明必须自称诊断件，且点名 `effect`。"""
    p = MT.write_diagnostic_note(tmp_path, "a")
    txt = p.read_text(encoding="utf-8")
    assert p.name == "table_a.NOTE.md"
    assert "诊断件" in txt and "不是发布件" in txt
    assert "effect" in txt and "table_main" in txt
    #: 幂等：写两遍内容一样（每批都会被重出的生成器重写一次）。
    assert MT.write_diagnostic_note(tmp_path, "a").read_text(encoding="utf-8") == txt


# ================================================================ ⑪ 取消聚合

def test_no_aggregate_column_anywhere_in_the_published_tables():
    """不出总分：主表与两张全量指标表里，一列都不许是「把多阶段合成一个数」的那种。"""
    published = (set(R.MAIN_TABLE_COLUMNS) | set(MM.agent_metric_names())
                 | {n for _st, n in MM.stage_metric_pairs()}
                 | {n for n, _r, _h, _k in MM.STAGE_CROSS_METRICS})
    #: 判据：列名**就是**那些名字之一，或者以 `_score` / `_total` 结尾。
    #: 不用前缀匹配 —— `effect_settled_runs` 是样本量计数，不是分数，
    #: 把它算成聚合列会让这条断言变成一个恒红的噪音门。
    for col in sorted(published):
        low = col.lower()
        assert low not in R.AGGREGATE_COLUMN_NAMES, \
            f"发布表上出现了聚合列 {col!r} —— ⑪ 明文取消聚合，不出总分"
        assert not low.endswith(("_score", "_total", "_总分")), \
            f"发布表上出现了聚合列 {col!r} —— ⑪ 明文取消聚合，不出总分"


def test_effect_stays_in_the_results_db_and_out_of_every_published_table():
    assert "effect" not in R.MAIN_TABLE_COLUMNS
    assert "effect" not in MM.agent_metric_names()
    assert "effect" not in {n for _st, n in MM.stage_metric_pairs()}
    #: 但它照旧**在行里**（结果库 / Table A 的诊断 CSV 从行里取）——
    #: 「不进发布表」不等于「不再算」。
    rows = R.table_a([_rec("t1", 1, effect=42.0)])
    assert rows[0]["effect"] == 42.0
    from ops import results_db as DB
    assert "effect" in DB.RESULT_FIELDS, "效果分必须留在结果库里（⑪）"


# ================================================================ ⑪ 四类「没有读数」× 三种格式

WITHHELD_FIXTURES: dict[str, dict] = {
    "rejected":         dict(status="violation", validity="invalid", l3=None),
    "honest_halt":      dict(status="ok", validity="valid", l3=None, correct_handling=True),
    "unsettled":        dict(status="ok", validity="valid", l3=None),
    "budget_exhausted": dict(status="budget_exhausted", validity=None, l3=None,
                             budget={"calls": 100, "max_calls": 100}),
}


@pytest.mark.parametrize("reason", sorted(WITHHELD_FIXTURES))
def test_withheld_reason_is_classified(reason):
    assert R.withheld_reason(_rec("t1", 1, **WITHHELD_FIXTURES[reason])) == reason
    assert reason in R.WITHHELD_REASONS


@pytest.mark.parametrize("reason", sorted(WITHHELD_FIXTURES))
def test_withheld_cell_renders_as_em_dash_in_csv(tmp_path, reason):
    rows = R.main_table([_rec("t1", 1, **WITHHELD_FIXTURES[reason])])
    assert rows[0]["Cov"] == R.NO_READING, f"{reason} 的格子必须是 `—`，不是 0、不是空"
    p = R.write_csv(rows, tmp_path / "main.csv", (*R.TABLE_A_INDEX_COLUMNS, *R.MAIN_TABLE_COLUMNS))
    with open(p, newline="", encoding="utf-8") as fh:
        got = list(csv.DictReader(fh))
    assert got[0]["Cov"] == "—", "CSV 里写 `—` 本身"


@pytest.mark.parametrize("reason", sorted(WITHHELD_FIXTURES))
def test_withheld_cell_renders_as_em_dash_in_markdown(reason):
    rows = R.main_table([_rec("t1", 1, **WITHHELD_FIXTURES[reason])])
    md = MT.to_markdown(rows, (*R.TABLE_A_INDEX_COLUMNS, *R.MAIN_TABLE_COLUMNS), caption="主表")
    body = md.splitlines()[-1]
    assert "—" in body, f"{reason}：Markdown 里写 `—` 本身"


@pytest.mark.parametrize("reason", sorted(WITHHELD_FIXTURES))
def test_withheld_cell_renders_as_triple_dash_in_latex(reason):
    rows = R.main_table([_rec("t1", 1, **WITHHELD_FIXTURES[reason])])
    tex = R.to_latex(rows, ("config_id", "arm", "Cov"), caption="主表", label="tab:main")
    line = [l for l in tex.splitlines() if l.startswith("cfg-x")][0]
    assert line.endswith(r"--- \\"), f"{reason}：LaTeX 里 `—` 写成 `---`，实际 {line!r}"


# ================================================================ ⑬ 三态：0 / — / unobservable / 空

def test_unobservable_is_not_zero_and_not_em_dash(tmp_path):
    """有可用的 run、但这个量测不出来 —— 必须写 `unobservable`。"""
    rows = R.main_table([_rec("t1", 1, l3=True, correctness={"CellAgree": 1.0})])
    assert rows[0]["Cov"] == R.UNOBSERVABLE
    assert rows[0]["Cov"] != 0 and rows[0]["Cov"] != R.NO_READING
    p = R.write_csv(rows, tmp_path / "m.csv", ("config_id", "Cov"))
    assert "unobservable" in p.read_text(encoding="utf-8")
    md = MT.to_markdown(rows, ("config_id", "Cov"), caption="x")
    assert "unobservable" in md.splitlines()[-1]
    tex = R.to_latex(rows, ("config_id", "Cov"), caption="x", label="t")
    assert r"\textit{unobservable}" in tex


def test_a_real_zero_stays_zero():
    rows = R.main_table([_rec("t1", 1, correctness={"Cov": 0.0})])
    assert rows[0]["Cov"] == 0.0, "「测了，是零」不许被翻成 `—` 或 unobservable"


def test_no_runs_for_a_stage_is_blank_not_a_dash(tmp_path):
    """S1 的 run 里没有 S4 的题 —— S4 那两列是**空**，不是 `—`（没有 run ≠ 没有读数）。"""
    rows = R.main_table([_rec("t1", 1, stage="S1", correctness={"Cov": 1.0})])
    assert rows[0]["IC-agr"] is None and rows[0]["Set"] is None
    p = R.write_csv(rows, tmp_path / "m.csv", ("config_id", "IC-agr"))
    with open(p, newline="", encoding="utf-8") as fh:
        assert list(csv.DictReader(fh))[0]["IC-agr"] == ""


# ================================================================ ⑬ 核六列算得出来

def test_core_six_columns_all_have_a_source():
    src = {c: (how, key) for c, _st, how, key in R.STAGE_COLUMN_SOURCES}
    for col in CORE_SIX:
        assert col in src, f"核六列的 {col} 在主表里没有取数来源（⑬ 要求补上）"


def test_ledger_comes_from_the_probe_state_three_ways():
    clean = _rec("t7", 1, stage="S7", probe_states={"ledger_conservation": "clean"})
    viol = _rec("t7", 2, stage="S7", validity="invalid", status="violation", l3=None,
                probe_states={"ledger_conservation": "violation"})
    unobs = _rec("t7", 3, stage="S7", probe_states={"ledger_conservation": "unobservable"})
    assert R.cell_from([clean], "probe", "ledger_conservation") == 1.0
    assert R.cell_from([viol], "probe", "ledger_conservation") == 0.0
    #: 探针检不了的那条：它本身不是四类原因之一 → unobservable，**不是 0**
    assert R.cell_from([unobs], "probe", "ledger_conservation") == R.UNOBSERVABLE


def test_ovr_merges_numerator_and_denominator_not_the_ratios():
    """越权率是比率：合并分子分母，**不是**对逐 run 的比率取均值。"""
    rs = [_rec("t8", 1, stage="S8", overreach={"denied": 1, "total": 100}),
          _rec("t8", 2, stage="S8", overreach={"denied": 1, "total": 2})]
    got = R.cell_from(rs, "overreach", "")
    assert got == pytest.approx(2 / 102)
    assert got != pytest.approx((0.01 + 0.5) / 2), "逐 run 求均值会被小样本的那条拉爆"
    assert R.cell_from([_rec("t8", 3, stage="S8")], "overreach", "") == R.UNOBSERVABLE


def test_correctness_cells_only_count_gate_passing_runs():
    """闸门失败时效果分不产出（不是低分）—— invalid 的 correctness 不进均值。"""
    rs = [_rec("t1", 1, correctness={"Cov": 1.0}),
          _rec("t1", 2, validity="invalid", status="violation", l3=None, correctness={"Cov": 0.0})]
    assert R.cell_from(rs, "correctness", "Cov") == 1.0


# ================================================================ ⑬ Decl / Set

def _artifact(stage: str, decl: dict) -> dict:
    return {"stage": stage, "declarations": dict(decl)}


def _legal(fields) -> dict:
    """给每个声明字段编一个**合法**取值：有限枚举的取枚举里的第一个，其余随便给个字符串。

    不能一律写 `"x"` —— 枚举外的取值按口径就是「没申明」，那样夹具本身会把 `Decl` 拉下来，
    而这条测试想量的是别的东西。
    """
    from reference import artifact_schema as ASch
    return {f: (ASch.DECLARATION_ENUMS[f][0] if f in ASch.DECLARATION_ENUMS else "x")
            for f in fields}


def test_decl_counts_an_honestly_marked_unresolved_field():
    """题面真欠定、产物如实标 unresolved —— **计入分子**。把它记 0 等于罚诚实。"""
    from reference import artifact_schema as ASch
    fields = ASch.declaration_fields("S6")
    full = _legal(fields)
    ok = L3.declaration_metrics(_artifact("S6", full), stage="S6", task={"underdetermined": []})
    assert ok["Decl"] == pytest.approx(1.0)
    marked = dict(full, **{fields[0]: ASch.UNRESOLVED})
    honest = L3.declaration_metrics(_artifact("S6", marked), stage="S6",
                                    task={"underdetermined": [fields[0]]})
    assert honest["Decl"] == pytest.approx(1.0), "如实标 unresolved 仍算如实申明"
    sloppy = L3.declaration_metrics(_artifact("S6", marked), stage="S6",
                                    task={"underdetermined": []})
    assert sloppy["Decl"] < 1.0, "题面没欠定却标 unresolved 是乱标，不计分子"


def test_decl_rejects_null_and_out_of_enum_values():
    from reference import artifact_schema as ASch
    fields = ASch.declaration_fields("S2")
    full = _legal(fields)
    full["adjust"] = "post"
    base = L3.declaration_metrics(_artifact("S2", full), stage="S2", task={"underdetermined": []})
    nulled = L3.declaration_metrics(_artifact("S2", dict(full, adjust=None)), stage="S2",
                                    task={"underdetermined": []})
    bad_enum = L3.declaration_metrics(_artifact("S2", dict(full, adjust="hfq")), stage="S2",
                                      task={"underdetermined": []})
    assert base["Decl"] > nulled["Decl"] and base["Decl"] > bad_enum["Decl"]


def test_set_is_the_payload_dependency_subset_not_the_whole_contract():
    """`Set` 与 `Decl` 不是同一个量：分母不同。"""
    from reference import artifact_schema as ASch
    dep = sorted({f for deps in ASch.PAYLOAD_DEPENDS_ON["S4"].values() for f in deps})
    required = ASch.declaration_fields("S4")
    assert set(dep) < set(required), "S4 的 payload 依赖集应当是契约必填集的真子集"
    art = _artifact("S4", _legal([f for f in required if f not in dep]))
    m = L3.declaration_metrics(art, stage="S4", task={"underdetermined": []})
    assert m["Set"] == 0.0 and m["Decl"] > 0.0


def test_declaration_metrics_returns_nothing_when_there_are_no_declarations():
    """畸形产物没有 `declarations` —— 返回空 dict（于是主表写 unobservable），**不是 0**。"""
    assert L3.declaration_metrics({"stage": "S1"}, stage="S1", task={}) == {}


# ================================================================ ⑫ 生成器 vs 规格，逐项相等

def test_generator_metric_set_equals_the_spec_registry():
    bad = MM.check_spec_matches_generator()
    assert not bad, "生成器的指标集与指标规格 §9 的登记表不一致：\n  " + "\n  ".join(bad)


def test_agent_metric_table_has_eighteen_items():
    assert len(MM.AGENT_METRICS) == 18, "⑫：全量 agent 指标表 18 项"
    assert len(MM.spec_agent_metrics()) == 18


def test_stage_metric_table_has_six_cross_stage_metrics():
    assert len(MM.STAGE_CROSS_METRICS) == 6, "⑫：六条跨阶段"
    assert len(MM.spec_stage_cross_metrics()) == 6


def test_stage_metric_table_lists_every_stage():
    pairs = MM.stage_metric_pairs()
    assert {st for st, _n in pairs} == {f"S{i}" for i in range(1, 9)}
    assert len(pairs) == len(set(pairs)), "同一阶段里指标名不许重复"
    assert len(pairs) == len(MM.spec_stage_metrics())


def test_every_role_is_one_of_four_and_effect_is_gone():
    """⑫：Role 列 `effect` → `fidelity`，规格里一处 `effect` 都不许再当 Role 用。"""
    roles = {r for _n, r in MM.spec_agent_metrics()} | {r for _s, _n, r in MM.spec_stage_metrics()} \
        | {r for _n, r in MM.spec_stage_cross_metrics()}
    assert roles <= set(MM.ROLES), f"规格里出现了未定义的 Role：{sorted(roles - set(MM.ROLES))}"
    assert "effect" not in roles
    assert "fidelity" in roles, "保真度类的指标必须真的存在 —— 否则这条改名就是空改"


def test_slip_self_consistency_is_a_gate_now():
    """④（2026-09-10 裁定）：Slip 的 role 由 `reported` 改成 `gate`。"""
    got = {(s, n): r for s, n, r in MM.spec_stage_metrics()}
    assert got[("S8", "SlipSelfConsistent")] == "gate"
    code = {(st, n): r for st in MM.STAGES for n, r, _h, _k in MM.STAGE_METRICS.get(st, ())}
    assert code[("S8", "SlipSelfConsistent")] == "gate"


# ================================================================ 生成器出得了表

def test_metric_tables_build_on_fixtures():
    recs = [_rec("t1", 1, stage="S1", correctness={"Cov": 1.0, "Decl": 1.0, "Set": 1.0}),
            _rec("t8", 1, stage="S8", correctness={"Audit": 1.0},
                 overreach={"denied": 0, "total": 10})]
    arows, acols = MM.build("agent", recs)
    assert acols == (*R.TABLE_A_INDEX_COLUMNS, *MM.agent_metric_names())
    assert len(arows) == 1
    srows, scols = MM.build("stage", recs)
    assert {r["stage"] for r in srows} == {"S1", "S8"}
    for name, _role, _how, _key in MM.STAGE_CROSS_METRICS:
        assert name in scols, f"六条跨阶段里的 {name} 没进阶段表的列"
    assert srows[1]["Ovr"] == 0.0, "一次都没越权是**真值 0**，不是空"


def test_report_spec_doc_covers_every_one_of_the_nineteen():
    doc = (_REPO / "ops" / "reports" / "report_spec_v1.md").read_text(encoding="utf-8")
    for col in NINETEEN:
        assert f"`{col}`" in doc, f"report_spec_v1.md 没写第 {NINETEEN.index(col) + 1} 列 {col}"
    for word in ("unobservable", "—", "没有读数", "取消聚合", "总分"):
        assert word in doc


# ================================================================ 真数据：核六列有数或有明确的 unobservable

def test_core_six_on_real_results_db():
    """⑬ 的收口：在**真数据**上出一遍主表，六列要么有数、要么是明确的 `unobservable` / `—`。"""
    from ops import results_db as DB
    if not DB.results_path().is_file():
        pytest.skip("本机没有结果库")
    recs = [r for r in DB.load() if DB.track_of(r) == "main"]
    if not recs:
        pytest.skip("结果库里没有主赛道记录")
    rows = R.main_table(recs)
    assert rows
    allowed = {R.NO_READING, R.UNOBSERVABLE, None}
    for row in rows:
        for col in CORE_SIX:
            v = row[col]
            assert isinstance(v, (int, float)) or v in allowed, \
                f"{row['config_id']}/{row['arm']} 的 {col} 是 {v!r} —— 只许是数、`—`、unobservable 或空"
    #: 至少有一格真的算出了数 —— 全表都是 unobservable 说明这一列根本没接上。
    for col in ("Ovr", "Ledger"):
        assert any(isinstance(r[col], (int, float)) for r in rows), \
            f"真数据上 {col} 一格数都没有 —— 那不是「不可观测」，是没接上"
