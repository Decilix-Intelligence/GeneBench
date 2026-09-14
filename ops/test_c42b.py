"""卡 4.2-b：适配臂（`genetask/arms.yaml` 的 `adapt`）+ 适配赛道结算出表（`ops/reports/adapt/`）。

这张卡的验收面有三块，测试逐块钉：

1. **臂**：adapt 臂登记了、形状对、`default: false` 因而不进任何既有出集，
   而且**建得出来** —— 后者是本卡改掉的那个真 bug（卡 4.2-a 的交接把它定成
   `phrasebook_column: open`，而 E10 对位置 A 的臂硬要求 `f=` 头部，open 列永远没有）。
2. **适配模块**：`ops/protocol/geneprotocol_v1_adapt/` 是封闭集合、sha 对得上；
   注入器对 `status != released` 的清单**必须拒绝**（本卡的真跑正是被这道门拦下的）。
3. **结算与出表**：30 行 oracle 矩阵在没有任何真跑时也出得来，且如实写「未运行」；
   有 run 时五结局分类走 `scorer/adaptation.py`（不新造判据）。
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from genetask import packager as P            # noqa: E402
from genetask import render as R              # noqa: E402
from genetask import schema as S              # noqa: E402
from genetask.bundle import load_arms         # noqa: E402
from ops import adaptation_track as AT        # noqa: E402


def _load_report_module():
    """按路径加载 `ops/reports/adapt/adapt_report.py`（`ops/` 不是包，与 test_genetask 加载
    freeze_v10 同一个理由）。"""
    p = _REPO / "ops" / "reports" / "adapt" / "adapt_report.py"
    spec = importlib.util.spec_from_file_location("_adapt_report", p)
    m = importlib.util.module_from_spec(spec)
    sys.modules["_adapt_report"] = m
    spec.loader.exec_module(m)
    return m


AR = _load_report_module()
ADAPT_MANIFEST = "ops/protocol/geneprotocol_v1_adapt/MANIFEST.json"


# ============================================================== 1. 臂


def _adapt():
    got = [a for a in load_arms() if a.id == "adapt"]
    assert len(got) == 1, "arms.yaml 里应当恰好一条 adapt 臂"
    return got[0]


def test_adapt_arm_is_registered_with_the_adaptation_module():
    a = _adapt()
    assert a.kind == "protocol"
    assert [(x.manifest, x.mount, x.per_task_rules) for x in a.artifacts] == \
        [(ADAPT_MANIFEST, "adaptation", False)], \
        "适配模块挂 /task/adaptation/，且**不叠**逐题规则（那是 strict 臂的东西）"
    assert (_REPO / ADAPT_MANIFEST).is_file()


def test_adapt_arm_does_not_touch_any_existing_set():
    """`default: false` —— 加这个臂不该改动任何一道已发布题的字节。"""
    a = _adapt()
    assert a.default is False
    assert S.ARMS == ("strict", "open"), \
        f"默认臂集合必须还是内置两臂，现在是 {S.ARMS} —— 翻 default 就是改题面，要推任务集版本"


def test_adapt_arm_uses_the_strict_phrasebook_column():
    """**本卡改掉的那个 bug 的回归判据**：protocol 臂只能用 strict 列。

    理由是 E10 的形状而不是口味：`packager.build_task` 把每个非参照臂放在
    `check_arms` 的**位置 A**，而 E10 对位置 A 的绝对判据是「声明项 f 的措辞以 `f=` 开头」
    （`genetask/render.py`，2026-09-03 签字裁定）。open 列是自然语言括注，永远不满足。
    """
    a = _adapt()
    assert a.phrasebook_column == "strict"
    assert a.fallback_column is None, "protocol 臂不许有 fallback_column（arms.yaml 头注）"
    assert a.equivalence == "e_rules", "protocol 臂 E1–E14 全查，不开例外"


def test_open_column_in_position_a_is_exactly_what_e10_rejects():
    """把 open 列的渲染放进位置 A，E10 必须报「没有 `f=` 头部」——
    这条把「为什么 adapt 臂不能用 open 列」钉成可执行判据，而不是一句注释。"""
    pb = R.load_phrasebook(P.PHRASEBOOK)
    b = P.build_task(_row("s2-cor-01"), capabilities=_caps(), phrasebook=pb, arms=("strict", "open"))
    assert b.ok, b.problems
    open_r = b.arms["open"]                 # 假想中「adapt 臂用 open 列」渲染出来的东西
    bad = R.check_arms(b.task, open_r, b.arms["open"], pb, b.task["canary"]["control_token"],
                       names=("adapt", "open"))
    assert any(x.startswith("E10 adapt 臂的声明项") for x in bad), bad
    # 反面：strict 列放进位置 A 就一条 E10 都不报（说明这不是「规则太严」而是列不对）
    ok = R.check_arms(b.task, b.arms["strict"], b.arms["open"], pb,
                      b.task["canary"]["control_token"], names=("adapt", "open"))
    assert not [x for x in ok if x.startswith("E10")], ok


def _caps():
    return json.loads((_REPO / "ops" / "capabilities.json").read_text(encoding="utf-8"))


def _row(task_id: str):
    rows = [r for r in P.load_params(_REPO / "genetask" / "params" / "v1.0-smoke40.yaml")
            if r["task_id"] == task_id]
    assert len(rows) == 1
    return rows[0]


def test_adapt_arm_builds_on_a_real_task():
    """加臂只加配置这句话的验收：adapt 臂在一道真题上**建得出来**且过 E1–E14。"""
    b = P.build_task(_row("s2-cor-01"), capabilities=_caps(), arms=("adapt", "open"))
    assert b.ok, "adapt 臂建题不过：\n  " + "\n  ".join(b.problems)
    assert list(b.task["instruction"]) == ["adapt", "open"]
    assert b.task["instruction"]["adapt"]["path"] == "arms/INSTRUCTION.adapt.md"


# ============================================================== 2. 适配模块


def test_adaptation_module_is_a_closed_set_whose_shas_match():
    import hashlib
    man = json.loads((_REPO / ADAPT_MANIFEST).read_text(encoding="utf-8"))
    assert set(man["artifacts"]) == set(AT.MODULE_STATIC), \
        "封闭集合：清单里的条目必须恰好是模块的静态件"
    for name, sha in man["artifacts"].items():
        got = hashlib.sha256((AT.MODULE_DIR / name).read_bytes()).hexdigest()
        assert got == sha, f"{name} 的 sha 与清单不符 —— 跑 adaptation_track.py --write-protocol-manifest"


def test_the_p7_gate_reads_status_and_files_out_of_the_manifest(tmp_path, monkeypatch):
    """P7 的判据是 `status == "released" and files`（`runner/inject.py`）——
    这里钉住它读的那两样东西是从清单里来的，而不是从目录里数出来的（封闭集合，§6.2）。"""
    from runner import inject as INJ
    monkeypatch.setattr(INJ, "_REPO_ROOT", tmp_path)
    d = tmp_path / "m"
    d.mkdir()
    (d / "MANIFEST.json").write_text(json.dumps(
        {"protocol_id": "x", "status": "draft", "artifacts": {"a.md": "0" * 64}}), encoding="utf-8")
    (d / "b.md").write_text("这个文件在目录里但不在清单里", encoding="utf-8")
    assert INJ.manifest_status("m/MANIFEST.json") == "draft"
    assert INJ.manifest_files("m/MANIFEST.json") == {"a.md": "0" * 64}, \
        "封闭集合：目录里多出来的 b.md 不许进投放集"


def test_adapt_module_status_is_a_fact_this_card_recorded_not_a_guess():
    """**本卡的真跑就是被这里拦下的**：适配模块的清单 status='draft'，
    P7 于是判「adapt 臂就是个裸臂」并中止注入（零次模型调用）。

    这条不断言它必须是 draft（有人签字放行的那一刻就该变绿），只断言
    **status 是个明确的取值**、且一旦 released 内容就必须齐 —— 半发布是最坏的一种。
    """
    from runner import inject as INJ
    st = INJ.manifest_status(ADAPT_MANIFEST)
    assert st in ("draft", "released"), f"清单 status={st!r} —— 既不是草稿也不是发布，那是什么？"
    if st == "released":
        files = INJ.manifest_files(ADAPT_MANIFEST)
        assert files, "released 却是空清单 —— 那正是 P7 要拦的「裸臂」"
        base = (_REPO / ADAPT_MANIFEST).parent
        assert all((base / k).is_file() for k in files)


# ============================================================== 3. 结算与出表


def test_matrix_has_thirty_rows_each_with_an_oracle():
    rows = AR.matrix_rows([])
    assert len(rows) == 30, f"适配赛道是 30 例，现在 {len(rows)}"
    assert all(r["expected_outcome"] for r in rows), "每例都要有 oracle 侧的期望结局"
    by_level = {}
    for r in rows:
        by_level.setdefault(r["level"], []).append(r)
    assert {k: len(v) for k, v in sorted(by_level.items())} == {"L1": 10, "L2": 10, "L3": 10}
    assert {r["expected_outcome"] for r in by_level["L1"]} == {"first_pass"}
    assert {r["expected_outcome"] for r in by_level["L2"]} == {"first_pass"}
    assert {r["expected_outcome"] for r in by_level["L3"]} == {"correct_flag"}


def test_missing_runs_are_reported_as_not_run_not_as_failures():
    """没跑 ≠ 跑挂了。缺哪一半必须一眼看得出是哪一半 —— 否则空表会被读成「全失败」。"""
    rows = AR.matrix_rows([])
    assert all(r["actual_outcome"] == AR.NOT_RUN for r in rows)
    assert all(r["calls"] is None and r["as_expected"] is None for r in rows)
    assert AR.NOT_RUN not in set(__import__("scorer.adaptation", fromlist=["OUTCOMES"]).OUTCOMES), \
        "「未运行」不能是五结局之一，否则会被 table_adaptation 数进去"


def _fake_run(tmp_path: Path, example_id: str, *, artifact: dict | None,
              calls: int = 0, arm: str = "adapt") -> Path:
    rd = tmp_path / f"{example_id}.{arm}.cfg-x.r01"
    (rd / "log").mkdir(parents=True)
    (rd / "inject.json").write_text(json.dumps(
        {"run_id": rd.name, "task_id": example_id, "arm": arm, "config_id": "cfg-x"}), encoding="utf-8")
    (rd / "run.json").write_text(json.dumps({"exit_code": 0}), encoding="utf-8")
    if artifact is not None:
        (rd / "artifact.json").write_text(json.dumps(artifact, ensure_ascii=False), encoding="utf-8")
    (rd / "log" / "llm_log.jsonl").write_text(
        "".join(json.dumps({"decision": "allow"}) + "\n" for _ in range(calls))
        + json.dumps({"decision": "deny"}) + "\n", encoding="utf-8")
    return rd


def _oracle(example_id: str) -> dict:
    return json.loads((AR.EXAMPLES_ROOT / example_id / "oracle.json").read_text(encoding="utf-8"))


def test_a_run_that_lands_the_oracle_is_first_pass(tmp_path, monkeypatch):
    """L1：终稿 == oracle 且 validator 零拒 → 首次通过。判据全部来自 scorer/adaptation.py。"""
    _fake_run(tmp_path, "adapt-l1-01", artifact=_oracle("adapt-l1-01"), calls=7)
    recs, problems = AR.score_all(tmp_path)
    assert problems == []
    assert len(recs) == 1
    assert recs[0]["outcome"] == "first_pass", recs[0]
    assert recs[0]["calls"] == 7, "calls 数的是 llm_log 里 decision==allow 的条数（deny 不算）"


def test_an_l3_run_that_marks_the_gap_is_correct_flag(tmp_path):
    """L3：把缺口标成 unresolved（而不是替源补一个值）→ 正确标记。"""
    _fake_run(tmp_path, "adapt-l3-01", artifact=_oracle("adapt-l3-01"), calls=3)
    recs, _ = AR.score_all(tmp_path)
    assert recs[0]["outcome"] == "correct_flag", recs[0]


def test_a_run_with_no_artifact_is_not_silently_dropped(tmp_path):
    """没有终端产物的 run 必须进表（blocked / failed），不能因为「没产物」就被跳过 ——
    那会让分母悄悄变小。"""
    _fake_run(tmp_path, "adapt-l1-02", artifact=None, calls=2)
    recs, _ = AR.score_all(tmp_path)
    assert len(recs) == 1 and recs[0]["outcome"] in ("blocked", "failed")


def test_calls_is_none_when_there_is_no_llm_log(tmp_path):
    """0 次调用与「不知道」不是一回事。"""
    rd = tmp_path / "x"
    (rd / "log").mkdir(parents=True)
    assert AR.allowed_calls(rd) is None
    (rd / "log" / "llm_log.jsonl").write_text("", encoding="utf-8")
    assert AR.allowed_calls(rd) == 0


def test_write_all_emits_the_five_products(tmp_path, monkeypatch):
    monkeypatch.setattr(AR, "OUT", tmp_path / "out")
    rd_root = tmp_path / "runs"
    rd_root.mkdir()
    _fake_run(rd_root, "adapt-l1-01", artifact=_oracle("adapt-l1-01"), calls=5)
    recs, problems = AR.score_all(rd_root)
    out = AR.write_all(recs, problems)
    for name in ("oracle_matrix.csv", "oracle_matrix.md", "table.csv", "table.tex",
                 "records.json", "summary.md"):
        assert (out / name).is_file(), name
    table = json.loads((out / "records.json").read_text(encoding="utf-8"))
    assert table and table[0]["outcome"] == "first_pass"
    md = (out / "oracle_matrix.md").read_text(encoding="utf-8")
    assert "真运行：1 / 30" in md, "矩阵头必须如实写有几例真跑过"
    assert "**不是主赛道实验数据**" in (out / "table.tex").read_text(encoding="utf-8"), \
        "表头必须写清这批数是什么（与 ops/score_runs.py::caption_for 同一条纪律）"


def test_reports_are_written_go_rwx(tmp_path, monkeypatch):
    """红线 5：$GB 全树与报告都是 0600/0700。"""
    monkeypatch.setattr(AR, "OUT", tmp_path / "out")
    out = AR.write_all([], [])
    bad = [str(p) for p in out.rglob("*") if p.stat().st_mode & 0o077]
    assert bad == [], f"这些文件 group/other 可读：{bad}"
