# -*- coding: utf-8 -*-
"""卡 X1 的定向测试。

三条都是**会自己失效**的断言：撞车修好了、清单被人重建了、手册退回旧说法，它们就红。
不做「扫描 / lint / 纪律」类自查（契约 D）。
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
GB = pathlib.Path("/data/shared/genebench")
MANUAL = REPO / "docs" / "OPERATOR_MANUAL.md"
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _manual() -> str:
    return MANUAL.read_text(encoding="utf-8")


def test_gateway_reaching_into_reference_must_stay_documented():
    """形态① 的阻塞点：网关 import 链穿到答案面。

    只要 `gateway/` 里还有 `from reference.` 这一行，手册就必须把这件事写着 ——
    **不是把红线写松，是不许让它消失在沉默里**。
    哪天有人按报告 §4 的方向 ① 把常量搬走了，这条断言的前提不成立，测试自动放行。
    """
    hits = []
    for f in sorted((REPO / "gateway").rglob("*.py")):
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if re.match(r"\s*from reference[.\s]", line) or re.match(r"\s*import reference\b", line):
                hits.append(f"{f.relative_to(REPO)}:{n}")
    if not hits:
        return  # 搬走了：这条阻塞不存在了
    m = _manual()
    assert "reference.artifact_schema" in m, (
        f"gateway/ 仍从 reference/ import（{hits}），但手册没有记这件事 —— "
        f"形态① 的运行者会在「起网关」那一步撞上一条没人写下来的红线"
    )
    assert "两种形态跑的是同一套代码" in m and "今天**不成立**" in m, (
        "手册 §1.1 还在说两种形态是同一套代码，而 gateway/ 仍依赖 reference/"
    )


def test_manual_has_the_third_way_to_build_the_data_plane():
    """§1.4 必须有第三条路「引用一份现成快照」，而且是**验过的步骤**不是缺口段。"""
    m = _manual()
    assert "(c) 引用一份已经建好的快照" in m, "§1.4 少了第三条路"
    assert "今天本手册没有给出写法（缺口" not in m, "§1.4(c) 还停在「缺口」的写法上"
    assert "GENEBENCH_ROOT=$ROOT" in m and "snapshots/public_v1/tables" in m, \
        "§1.4(c) 没给出可照抄的落点与软链写法"
    assert "genebench_config.snapshot_tables_dir()" in m, \
        "§1.4(c) 必须写清版本目录名按通道取 —— 指错通道时数字看起来都对"


def test_manual_records_that_containers_can_now_reach_the_host_gateway():
    """§1.3 那张「三种全部超时」的表是**放行前**的结论，必须标注，别当现状引。"""
    m = _manual()
    assert "放行之后（2026-09-10" in m, "§1.3 没记放行之后的实测"
    assert "192.168.1.219:18080` = 200" in m or "192.168.1.219:18080 = 200" in m, \
        "§1.3 没写出放行之后容器打宿主 LAN 的实测码"


def test_m6_public_joblist_does_not_pin_max_tokens():
    """N-388：默认档已是 6 M，清单里再显式写 `max_tokens` 就是把预算压回去。

    清单不在 git 里（`$GB/runs_in/`），机器上没有就跳过。
    """
    jobs = GB / "runs_in" / "m6_public" / "jobs.jsonl"
    if not jobs.is_file():
        import pytest
        pytest.skip("本机没有 m6_public 清单")
    bad = []
    for line in jobs.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if "max_tokens" in (r.get("budget_override") or {}):
            bad.append(r.get("job_id"))
    assert not bad, (
        f"{len(bad)} 个 job 仍显式钉着 max_tokens（例：{bad[:3]}）—— "
        f"S4/S7 会因此拿不到 9 M / 18 M 的档位"
    )


# ---------------------------------------------------------------- 2026-09-11 续（18 个 run 那一轮）

M6P = REPO / "ops" / "reports" / "m6_public"


def test_public_fixture_identity_gate_is_the_thing_blocking_export():
    """挡住 10 个 run 的那件事必须一直有据可查，且**证据自洽**。

    会自己失效的方式有两种，都是我们想要的：
      · 有人按方向 A/B 修好了 → 公开侧开始有夹具与声明相同 → 这条断言的前提不成立，测试自动放行；
      · 有人把 `export_task` 的闸删了 → 阻塞理由不成立，那才是要红的（见下一条）。
    """
    p = M6P / "x1_fixture_identity_block.json"
    if not p.is_file():
        import pytest
        pytest.skip("本机没有 X1 的取证文件")
    d = json.loads(p.read_text(encoding="utf-8"))
    if d["n_public_matches_declared"] > 0:
        return                                  # 已经被修好了
    assert d["n_fixture_rows"] > 0, "取证文件里一件夹具都没有 —— 它不该是空的"
    assert d["n_private_matches_declared"] == d["n_fixture_rows"], (
        "私有侧本该逐件与声明相同（那正是这道闸在私有通道成立的原因）；"
        f"现在 {d['n_private_matches_declared']}/{d['n_fixture_rows']}"
    )
    assert d["runs_blocked"] == len(d["tasks_blocked"]) * 2, "被挡住的 run 数与题数对不上（双臂）"
    assert set(d["tasks_blocked"]) & set(d["tasks_exportable"]) == set(),         "同一道题不能既出得了集又出不了集"


def test_export_task_still_has_the_identity_gate():
    """上一条的另一半：阻塞理由是「`export_task` 里那道闸」，闸没了理由就不成立。

    **不许靠删闸变绿** —— 真要放行，方向 A/B 都是有版本号的改动（X1.md §1）。
    """
    src = (REPO / "genetask" / "packager.py").read_text(encoding="utf-8")
    assert "与题面声明不符" in src and "不出集" in src, (
        "genetask/packager.py::export_task 的夹具身份闸不见了 —— "
        "如果这是有意的放行，请连着 ops/reports/m6_public/x1_fixture_identity_block.json "
        "与 ops/tickets_inbox/X1.md §1 一起更新，别让阻塞理由静默失效"
    )


def test_control_oracle_window_drift_is_evidenced_not_asserted():
    """三控里 `s1-cor-01/oracle` 那一行的差异必须有**逐条命中**的取证，不能只有一句结论。

    判据：产物的 fetched_at 与某一个日志块 601/601 命中、与 `oracle_window()` 选中的块 0/601。
    哪天有人重跑了该题 oracle 把配对接回去，这个取证文件会被重出或删掉，这条跳过。
    """
    p = M6P / "x1_rerun2" / "s1_oracle_window_drift.json"
    if not p.is_file():
        import pytest
        pytest.skip("本机没有 X1 的漂移取证")
    d = json.loads(p.read_text(encoding="utf-8"))
    hits = {r["block_hour"]: r["declared_hits_in_block"] for r in d["declared_vs_block"]}
    total = d["artifact_n_fetches"]
    assert sorted(hits.values()) == [0] * (len(hits) - 1) + [total], (
        f"产物应当与**恰好一个**日志块逐条命中（{total} 条），实际 {hits} —— "
        f"不是「口径变了」那一类，就该是这个形状"
    )


def test_main_table_for_the_public_batch_has_the_nineteen_columns():
    """公开批的主表按 C 卡口径出：十九列一列不裁，且不含聚合列。"""
    p = M6P / "table_main.csv"
    if not p.is_file():
        import pytest
        pytest.skip("本机没有公开批主表")
    import csv
    with p.open(encoding="utf-8") as fh:
        cols = next(csv.reader(fh))
    from scorer.report import MAIN_TABLE_COLUMNS
    want = list(MAIN_TABLE_COLUMNS)
    assert len(want) == 19, f"MAIN_TABLE_COLUMNS 不是十九列而是 {len(want)}（⑩）"
    # 前面几列是身份列（config_id / arm / arm_kind / n_tasks / n_runs），十九列接在后面
    assert cols[-19:] == want, (
        f"主表的十九列与 scorer/report.py::MAIN_TABLE_COLUMNS 不一致：\n"
        f"  表里 {cols[-19:]}\n  常量 {want}"
    )
    assert cols[:len(cols) - 19] == ["config_id", "arm", "arm_kind", "n_tasks", "n_runs"], (
        f"主表的身份列变了：{cols[:len(cols) - 19]}"
    )
    for agg in ("total", "score", "overall", "aggregate"):
        assert agg not in [c.lower() for c in cols], f"主表出现疑似聚合列 {agg!r}（⑪ 取消聚合）"
