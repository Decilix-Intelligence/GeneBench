# -*- coding: utf-8 -*-
"""卡 5.3 报告器的红测：估计量、分母纪律、空值纪律、CSV/LaTeX 形状。"""
from __future__ import annotations

import csv

import pytest

from scorer import report as R


def test_pass_hat_k_estimator():
    assert R.pass_hat_k(3, 3, 3) == 1.0
    assert R.pass_hat_k(2, 3, 3) == 0.0
    assert R.pass_hat_k(3, 4, 3) == pytest.approx(0.25)
    assert R.pass_hat_k(1, 2, 3) is None            # n < k：无定义，不是 0


def _rec(task, seq, status="ok", validity="valid", l3=True, cfg="cfg-x", arm="strict", **kw):
    # 桶从分类表取，不在测试里手抄一份 —— 手抄的那份会在加状态时漏掉新的（budget_exhausted 就是这么漏的）
    from runner.c42.failure_modes import sr_bucket
    bucket = sr_bucket(status)
    r = {"task_id": task, "stage": "S1", "config_id": cfg, "arm": arm, "seq": seq,
         "run_status": status, "sr_bucket": bucket, "validity": validity,
         "malformed": status == "malformed", "l3_pass": l3, "steps": 5, "latency_s": 10.0,
         "tokens_prompt": 100, "tokens_completion": 20, "validator_rejections": None, "overreach": None}
    r.update(kw)
    return r


def test_table_a_basic_and_denominator():
    recs = [_rec("t1", 1), _rec("t1", 2), _rec("t1", 3, status="violation", validity="invalid", l3=None),
            _rec("t2", 1), _rec("t2", 2, status="no_artifact", validity=None, l3=None),
            _rec("t2", 3, status="harness_error", validity=None, l3=None)]
    row = R.table_a(recs)[0]
    assert row["n_tasks"] == 2 and row["n_runs"] == 6
    # t1: 3/3 可评分；t2: harness 不进分母 → 1/2
    assert row["SR"] == pytest.approx((1.0 + 0.5) / 2)
    # pass@1：t1 2/3，t2 1/2
    assert row["pass@1"] == pytest.approx((2 / 3 + 1 / 2) / 2)
    # pass^3：t1 有 3 次（c=2 → 0），t2 只有 2 次（不进均值）
    assert row["pass^3"] == 0.0 and row["pass^3_tasks_with_3_runs"] == 1
    assert row["ProgressRate"] == pytest.approx((1.0 + 0.5) / 2)
    assert row["Latency"] == 10.0 and row["Steps"] == 5
    assert row["$"] is None and row["Recov"] is None and row["越权率"] is None


def test_table_a_recov_and_overreach():
    recs = [_rec("t1", 1, validator_rejections=2, overreach={"denied": 1, "total": 4}),
            _rec("t1", 2, validator_rejections=1, validity="invalid", status="violation", l3=None,
                 overreach={"denied": 0, "total": 6}),
            _rec("t1", 3, validator_rejections=0)]
    row = R.table_a(recs)[0]
    assert row["Recov"] == pytest.approx(0.5)
    assert row["越权率"] == pytest.approx(1 / 10) and row["overreach_observable_runs"] == 2


def test_table_a_honest_halt_counts_as_success():
    recs = [_rec("t1", 1, l3=None, correct_handling=True)]
    assert R.table_a(recs)[0]["pass@1"] == 1.0


def test_table_a_all_harness_task_is_dropped_not_zeroed():
    recs = [_rec("t1", 1), _rec("t2", 1, status="harness_error", validity=None, l3=None)]
    row = R.table_a(recs)[0]
    assert row["SR"] == 1.0 and row["n_tasks"] == 2


def test_table_b_means_only_valid_runs():
    recs = [_rec("t1", 1, correctness={"exact_match_rate": 1.0}),
            _rec("t1", 2, status="violation", validity="invalid", l3=None, correctness={"exact_match_rate": 0.0}),
            _rec("t1", 3, correctness={"exact_match_rate": 0.5})]
    row = R.table_b(recs)[0]
    assert row["exact_match_rate"] == pytest.approx(0.75) and row["invalid_rate"] == pytest.approx(1 / 3)


def test_csv_none_is_empty_and_latex_none_is_dash(tmp_path):
    rows = R.table_a([_rec("t1", 1)])
    p = R.write_csv(rows, tmp_path / "a.csv", R.TABLE_A_COLUMNS)
    with open(p, newline="", encoding="utf-8") as fh:
        got = list(csv.DictReader(fh))
    assert got[0]["$"] == "" and got[0]["SR"] == "1.0"
    tex = R.to_latex(rows, ("config_id", "arm", "SR", "$", "pass^3"), caption="Table A", label="tab:a")
    assert r"\toprule" in tex and "---" in tex and r"cfg-x" in tex
    assert r"pass\^{}3" in tex and r"\$" in tex               # 列名转义


# ------------------------------------------------------------------ 报告不许悄悄退化成局部（裁定 2026-09-06）
def test_reports_cover_at_least_the_released_task_set():
    """**报告里的题数不得少于出集题数。**

    2026-09-06 踩过：`run_oracles --tasks a,b` 会**整份覆盖** `probe_run_oracle.json`，
    而两份报告都从它读数 —— 于是修完两道题重跑一次，验证验证器报告 ① 就从 40 题变成 4 题、
    「零误报」的证据从 32 条变成 0 条。报告没有报错，它只是**悄悄变小了**。
    修法是累积文件（每行带 `at`，按 task_id 取最新）；这条测试是那把锁。
    """
    import json
    import sys
    from pathlib import Path
    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo))
    from genetask import packager as P
    from ops.freeze_v10 import IN_V10

    rows = P.load_params(repo / "genetask" / "params" / "v1.0-smoke40.yaml")
    released = {r["task_id"] for r in rows if IN_V10({**r, "kind": r["kind"]})}
    cum = repo / "ops" / "reports" / "probe_run_oracle.cumulative.json"
    if not cum.is_file():
        import pytest
        pytest.skip("还没跑过 oracle 跑批（累积文件不存在）")
    got = {r["task_id"] for r in json.loads(cum.read_text(encoding="utf-8"))}
    missing = sorted(released - got)
    assert not missing, (f"O1 累积矩阵缺 {len(missing)} 道**出集题**：{missing[:8]} —— "
                         f"报告会因此少报证据。跑一次 `ops/run_oracles.py --tier full` 或把那几题补上")


def test_table_a_reports_budget_exhausted_separately_from_no_artifact():
    """预算耗尽与交白卷在主表上必须分得开（N-130）。"""
    recs = [_rec("t1", 1, status="budget_exhausted", validity=None, l3=None),
            _rec("t2", 1, status="no_artifact", validity=None, l3=None)]
    row = R.table_a(recs)[0]
    assert row["budget_exhausted_runs"] == 1 and row["n_runs"] == 2
    assert row["SR"] == 0.0, "两者都不算可评分产物 —— 桶没变，只是状态分开了"


def test_table_a_sums_unbounded_requests():
    """`unbounded_requests` 是**行为计数**，按总数报；日志不可得的 run 不该把它变成 0。"""
    recs = [_rec("t1", 1, unbounded_requests=8), _rec("t1", 2, unbounded_requests=3),
            _rec("t1", 3, unbounded_requests=None)]
    assert R.table_a(recs)[0]["unbounded_requests"] == 11
    assert R.table_a([_rec("t1", 1, unbounded_requests=None)])[0]["unbounded_requests"] is None
