# -*- coding: utf-8 -*-
"""`ops/run_oracles.py` 的判据（卡 2.6 / B8）。

重点在**报告不许说谎**：矩阵是要进 M6「验证验证器」报告的东西，
一张把「36 题崩了」画成「全部干净」的矩阵，比没有矩阵更坏。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ops.run_oracles import MALFORMED_ROW, Result, check_log_evidence, render_matrix


def _r(tid, probes=None, artifact=True, **kw):
    return Result(tid, tid[:2].upper(), "tpl", ran=True, rc=0,
                  artifact=(Path("/x/artifact.json") if artifact else None),
                  probes=probes or {}, **kw)


# ---------------------------------------------------------------- 矩阵不许把崩溃画成干净
def test_a_task_without_an_artifact_is_na_not_zero():
    """**「没跑成」与「跑了且干净」不能长得一样。**

    实测：40 题里 36 题崩在调用约定上，第一版矩阵显示**全零** ——
    看起来像「所有探针都干净」，而其实什么都没判过。
    这与 `None`/`[]` 是同一族错误：**不可得 ≠ 零**。
    """
    md = render_matrix([_r("s1-cor-01"), _r("s2-cor-01", artifact=False)], agent="oracle")
    assert "可判题目 1/2" in md
    assert "n/a" in md, "没产出 artifact 的题没有标成 n/a"
    assert "s2-cor-01" in md.split("不可判的")[1][:80]


def test_silent_families_are_counted_only_over_evaluable_tasks():
    """「全零的族」只在**可判**的题上算 —— 在崩掉的题上算全零 = 把崩溃当干净。"""
    md = render_matrix([_r("s1-cor-01", {"calendar": 2}),
                        _r("s2-cor-01", artifact=False)], agent="oracle")
    assert "在这 1 道可判题上全零的族" in md
    assert "`calendar`" not in md.split("全零的族")[1][:400], "响过的族被算进全零里了"


def test_nonzero_cells_are_marked_and_totalled():
    md = render_matrix([_r("s1-cor-01", {"calendar": 3, MALFORMED_ROW: 1})], agent="oracle")
    line = next(l for l in md.splitlines() if l.startswith("| `calendar`"))
    assert "**3**" in line and line.rstrip().endswith("| 3 |")


def test_oracle_matrix_says_zero_does_not_prove_direction():
    """在 oracle 上全零是**应该的**，不能拿来说明方向对（D-30）。

    2026-09-05 改注：方向的另一半从「f1 矩阵」改成「逐族破坏样本」（`ops/run_probe_mutations.py`）——
    f1 填充器按题面 `null_agent.behavior` 造产物，能触发的只有静默补全那一族。
    注文必须指向**真正**证方向的那份东西，否则读表的人会去看一张证不了这件事的矩阵。
    """
    md = render_matrix([_r("s1-cor-01")], agent="oracle")
    assert "不能" in md and "方向" in md
    assert "mutations.md" in md, "注文没指向逐族破坏样本"


def test_f1_matrix_states_the_opposite_criterion():
    """f1 矩阵的注文要说清**它只证一族**，并把「全零 ≠ 干净」那半留着。"""
    md = render_matrix([_r("s1-cor-01", {"underdetermined": 2})], agent="f1")
    assert "underdetermined" in md and "只针对静默补全" in md
    assert "不能" in md and "干净" in md


# ---------------------------------------------------------------- 证据源
def test_log_evidence_distinguishes_unavailable_from_empty():
    """`None`（不可得）与 `[]`（可得但零条）是两回事 —— 说法必须不同。"""
    a = check_log_evidence(None)
    b = check_log_evidence([])
    assert a and b and a != b
    assert "不可得" in a[0] and "0 条" in b[0]


def test_log_evidence_names_the_gateway_when_rows_is_missing():
    """`rows` 缺失是**网关的缺陷**，不是 artifact 的 —— 报告要指对地方。"""
    rows = [{"decision": "allow", "rows": 5}, {"decision": "allow", "rows": None}]
    out = check_log_evidence(rows)
    assert out and "1/2" in out[0] and "网关" in out[0]


def test_log_evidence_is_quiet_when_the_source_is_intact():
    """防恒红：证据源健全时不许报。"""
    assert check_log_evidence([{"decision": "allow", "rows": 5},
                               {"decision": "deny", "reason": "asof_beyond_freeze"}]) == []


def test_bool_rows_is_not_an_integer_row_count():
    """`True` 不是行数。bool 是 int 的子类 —— 这条在本仓库已经犯过三次。"""
    assert check_log_evidence([{"decision": "allow", "rows": True}])


# ===================================================== O1 判据不许恒绿（D-27，2026-09-05）
#
# `Result.ok` 原来是 `ran and rc == 0 and not findings` —— **没有产物时 `findings`
# 恰好是空的**，于是「校验器一条都没查」被记成「零 finding」。S7 五题就是这样：
# 它们把产物写到 `gold/oracle_artifact.json`，而跑批找的是 `solution/artifact.json`，
# 找不到却整列绿。恒绿的门与恒红的一样会被绕过（F7 / D-06）。

def _result(**kw):
    from ops.run_oracles import Result
    base = dict(task_id="s7-cor-01", stage="S7", template_id="cor_reproduce",
                ran=True, rc=0)
    return Result(**{**base, **kw})


def test_ok_requires_an_artifact_not_just_a_zero_exit(tmp_path):
    """**删产物必红**：同一次运行，只把 artifact 拿掉，`ok` 必须从真变假。"""
    art = tmp_path / "artifact.json"
    art.write_text("{}", encoding="utf-8")
    r = _result(artifact=art)
    assert r.ok is True
    r.artifact = None
    assert r.ok is False, "没有产物却算「零 finding」—— 校验器一条都没查"


def test_ok_is_false_when_the_process_failed_even_with_an_artifact(tmp_path):
    art = tmp_path / "artifact.json"
    art.write_text("{}", encoding="utf-8")
    assert _result(rc=1, artifact=art).ok is False


def test_ok_is_false_when_findings_exist(tmp_path):
    """反面对照：门要**能红也能绿**，否则上一条测的可能是一个恒假的属性。"""
    art = tmp_path / "artifact.json"
    art.write_text("{}", encoding="utf-8")
    assert _result(artifact=art, findings=["x"]).ok is False


def test_run_one_says_why_when_the_oracle_wrote_nowhere(tmp_path, monkeypatch):
    """rc=0 但没写标准路径 —— 要**说出原因**，不能只是不绿。

    「统一 I/O 契约要求写 `GENEBENCH_ORACLE_OUT`」这句话必须出现在 note 里，
    否则下一个人看到的是一个没有解释的空格子。
    """
    from ops import run_oracles as RO
    td = tmp_path / "s7-cor-01"
    (td / "solution").mkdir(parents=True)
    (td / "solution" / "solve.py").write_text("print('我什么都不写')\n", encoding="utf-8")
    res = RO.run_one(td, {"task_id": "s7-cor-01", "stage": "S7",
                          "template_id": "cor_reproduce"})
    assert res.ran and res.rc == 0
    assert res.artifact is None and res.ok is False
    assert "GENEBENCH_ORACLE_OUT" in res.note, res.note
