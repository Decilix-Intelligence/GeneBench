# -*- coding: utf-8 -*-
"""卡 Y2 的测试：适配赛道按 **N-348** 重建题源 + 守门定点解除 + 后果落到三处文档与两处表。

判据全部来自 2026-09-10 的用户裁定原文：

> 适配赛道题源 = 出集规定题的 oracle 产物（探针题不入），每级 10 例**按阶段分层**，
> 破坏方式按级别表，**种子固定**。守门 `ops/push_guard.py` 里「按集拒 v1.0-adapt」要显式解除
> 并**记因**。**后果必须写下来不许省**：这些题的 oracle 产物由此进入执行面 → 跑过适配赛道的
> 被测方，主赛道这些题算「可能已见过答案」。

**这一条不在裁定里，是本卡的实测**：裁定写「33 道」，清单现值是 **32 道**（出集 34 =
规定题 32 + 已放出探针题 2）。`test_the_ruling_says_33_the_manifest_says_32` 把这个差钉住 ——
数对不上要如实报，不许把清单改成 33，也不许假装 33 就是 32。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import genebench_config as cfg
from ops import adaptation_track as AT
from ops import pack_adaptation as PK
from ops import push_guard as PG
from reference import artifact_schema as sch
from scorer import report as RP

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

_REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def exs():
    return AT.examples()


@pytest.fixture(scope="module")
def muts() -> dict:
    root = AT.OUT_ROOT
    if not (root / "_index.json").is_file():
        pytest.skip(f"还没生成：{root}（跑 ops/adaptation_track.py --write）")
    out = {}
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        p = d / "mutation.json"
        if p.is_file():
            out[d.name] = json.loads(p.read_text(encoding="utf-8"))
    return out


# ============================================================ 一、题源


def test_every_source_task_is_a_released_regulated_task(exs):
    """题源只许是**出集规定题**。探针题一道都不许进 —— 那是欠定读数最敏感的地方。"""
    man = json.loads((_REPO / "ops" / "manifests" / "v1.0-smoke.json").read_text(encoding="utf-8"))
    regulated = {t["task_id"] for t in man["released_tasks"]
                 if t["kind"] != "underdetermined_probe"}
    probes = {t["task_id"] for t in man["released_tasks"] + man["held_tasks"]
              if t["kind"] == "underdetermined_probe"}
    used = {e.source_task for e in exs}
    assert used <= regulated, f"题源里混进了非规定题：{sorted(used - regulated)}"
    assert not (used & probes), f"探针题不入，但用到了 {sorted(used & probes)}"


def test_the_source_file_is_the_oracle_artifact_not_something_else(exs):
    """题源文件必须是 **oracle 产物**：S7/S8 在 `gold/oracle_artifact.json`，其余在
    `solution/artifact.json`。这两处是 `ops/run_oracles.py` 真正的落点。"""
    for e in exs:
        p = AT.oracle_path(e.source_task)
        rel = p.relative_to(AT.SOURCE_ROOT / e.source_task).as_posix()
        assert rel in AT.ORACLE_RELPATHS, f"{e.source_task} 取的是 {rel}"
        if (AT.SOURCE_ROOT / e.source_task / "gold" / "oracle_artifact.json").is_file():
            assert rel == "gold/oracle_artifact.json", \
                f"{e.source_task} 有 gold/oracle_artifact.json 却取了 {rel} —— 那是过期的那一份"


def test_the_ruling_says_33_the_manifest_says_32():
    """裁定原文写「33 道」，清单现值是 32 道。**如实报**，两边都不改。"""
    c = AT.source_counts()
    assert c["ruling_said"] == 33
    assert c["released"] == 34 and c["held"] == 6
    assert c["released_by_kind"]["underdetermined_probe"] == 2
    n_reg = c["released"] - c["released_by_kind"]["underdetermined_probe"]
    assert n_reg == 32, f"规定题现值 {n_reg}"
    assert c["regulated_used"] <= n_reg, "体量帽只会减，不会增"


def test_the_two_oversized_sources_are_excluded(exs):
    """`s5-eco-01`（4.0 MB）与 `s4-ops-01`（878 KB）不进题源：它们量的是上下文管理不是适配。"""
    for tid in ("s5-eco-01", "s4-ops-01"):
        assert AT.oracle_path(tid).stat().st_size > AT.MAX_SOURCE_BYTES, \
            f"{tid} 现在小于体量帽了 —— 这条测试的前提没了，重新想一遍帽该设多少"
    used = {e.source_task for e in exs}
    assert not (used & {"s5-eco-01", "s4-ops-01"})
    for e in exs:
        assert AT.oracle_path(e.source_task).stat().st_size <= AT.MAX_SOURCE_BYTES, e.source_task


# ============================================================ 二、选题：分层 + 种子


def test_ten_per_level_and_every_level_covers_all_eight_stages(exs):
    assert len(exs) == 30
    for lv in AT.LEVELS:
        sub = [e for e in exs if e.level == lv]
        assert len(sub) == AT.PER_LEVEL, lv
        assert {e.stage for e in sub} == set(sch.STAGES), \
            f"{lv} 按阶段分层没覆盖八个阶段：{sorted({e.stage for e in sub})}"
    assert len({e.example_id for e in exs}) == 30


def test_selection_is_reproducible_from_the_seed(exs):
    """**种子固定**：同一份题源上再选一次，逐例相同（题、位点、破坏族、恢复路线）。"""
    again = AT.select("L2")
    got = [(e.example_id, e.source_task, e.site, e.family, e.recovery["route"]) for e in again]
    want = [(e.example_id, e.source_task, e.site, e.family, e.recovery["route"])
            for e in exs if e.level == "L2"]
    assert got == want
    assert AT.SEED == 20260910


def test_the_seed_is_written_into_every_product(muts):
    """种子与选中它的那一步要**写进产物**，否则「可复现」只是一句话。"""
    for eid, m in muts.items():
        assert m["seed"] == AT.SEED, eid
        assert m["selection"]["seed"] == AT.SEED and m["selection"]["rank"] >= 1, eid
        assert m["selection"]["candidate_key"], eid
        assert m["source_kind"] == "regulated_released", eid
        assert m["source_artifact"] in AT.ORACLE_RELPATHS, eid


def test_every_break_site_is_something_the_scorer_actually_compares(exs):
    """位点必须落在评分器真的比对的那部分 —— 落在别处的破坏，结局量的是运气。"""
    for e in exs:
        head = e.site.split(".")[0]
        assert head in ("payload", "declarations", "provenance"), e.example_id
        if head == "payload":
            assert e.site.split(".")[1] in sch.PAYLOAD_REQUIRED[e.stage], \
                f"{e.example_id} 破在 {e.site}，不在 PAYLOAD_REQUIRED[{e.stage}] 里"


def test_schema_format_route_means_the_validator_really_rejects(muts):
    """`schema_format` 那条路线声称「目标 schema 只收一种写法」——**实测**：破坏之后必须真被拒。
    schema 管不到的位置（`fetches[].params` 里的日期）由生成器退到 `source_unit_declaration`。"""
    n = 0
    for eid, m in muts.items():
        if (m.get("recovery") or {}).get("route") != "schema_format":
            continue
        n += 1
        assert m["broken_validator"]["ok"] is False, \
            f"{eid} 走 schema_format，但破坏后照样过校验器 —— 那句话在这一处不成立"
    assert n >= 1, "一条 schema_format 的例子都没有了 —— 这条测试就空转了"


# ============================================================ 三、守门：解除 + 更窄的门


def test_the_by_set_refusal_is_lifted_with_the_reason_recorded():
    """按集拒**显式解除**，且**记因**留在代码里（裁定编号 + 后果 + 保留的门，一个都不能少）。"""
    assert "v1.0-adapt" not in PG.SET_IDS_NOT_PUSHABLE
    src = (_REPO / "ops" / "push_guard.py").read_text(encoding="utf-8")
    head = src.split("SET_IDS_NOT_PUSHABLE")[0]
    for token in ("N-348", "2026-09-10", "可能已见过答案", "fairness_protocol.md"):
        assert token in head, f"记因里缺 {token!r}"


def test_the_narrower_gate_is_the_destination(tmp_path, monkeypatch):
    """解除 ≠ 敞开：落点必须显式声明，且只许在适配根下。**没声明 = 拒**。"""
    b = tmp_path / "tasks" / "adapt-x"
    b.mkdir(parents=True)
    (b / "task.yaml").write_text("set_id: v1.0-adapt\n", encoding="utf-8")
    monkeypatch.delenv(PG.DEST_ENV, raising=False)
    assert PG.check_pushable_set(b), "没声明落点必须拒"
    assert PG.check_pushable_set(b, None, "/data/genebench_runner/m6/tasks/x"), "主赛道目录必须拒"
    assert PG.check_pushable_set(b, None, "/data/genebench_runner/adapt/tasks/adapt-x") == []
    monkeypatch.setenv(PG.DEST_ENV, "/data/genebench_runner/adapt/tasks/adapt-x")
    assert PG.check_pushable_set(b) == []


def test_gold_derived_origin_is_still_refused_outside_the_adaptation_track(tmp_path):
    """`origin: gold_derived` 的一般规则没被放宽 —— 适配集是它唯一的例外。"""
    b = tmp_path / "tasks" / "x-01"
    b.mkdir(parents=True)
    (b / "task.yaml").write_text("set_id: v1.0-other\n", encoding="utf-8")
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps({"set_id": "v1.0-other", "origin": "gold_derived"}), encoding="utf-8")
    bad = PG.check_pushable_set(b, mp)
    assert bad and "gold_derived" in bad[0]


def test_the_passport_says_out_loud_where_the_content_came_from():
    """通行证如实自报 `origin` / `track` —— 瞒着不写才是问题。"""
    if not (AT.OUT_ROOT / "adapt-l1-01" / "broken.json").is_file():
        pytest.skip("还没生成")
    import shutil
    root = cfg.GENEBENCH_ROOT / "staging" / "y2_pytest"
    try:
        r = PK.pack_one("adapt-l1-01", root)
        m = json.loads(Path(r["manifest"]).read_text(encoding="utf-8"))
        assert m["origin"] == "gold_derived" and m["track"] == "adaptation"
        assert "set_id: v1.0-adapt" in (Path(r["bundle"]) / "task.yaml").read_text(encoding="utf-8")
        assert m["source_note"].startswith("work/input/broken.json")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_the_first_arm_is_the_intervention_arm():
    """N-364：出集把 `arm_ids[0]` 当干预臂。适配赛道的干预臂是 `adapt`，不是 `strict`。"""
    assert PK.DEFAULT_ARMS[0] == "adapt"
    assert "open" in PK.DEFAULT_ARMS, "参照臂要在，否则 §6.2 的等号没有可比的一侧"


# ============================================================ 四、后果落到三处文档与两处表


def test_the_consequence_is_written_in_all_three_documents():
    """**不许省**：三份文档各自写着同一句后果，且都点了 N-348。"""
    for rel in ("ops/specs/fairness_protocol.md",
                "ops/reports/known_limits_v1.md",
                "ops/specs/adaptation_track.md"):
        s = (_REPO / rel).read_text(encoding="utf-8")
        assert "N-348" in s, rel
        assert "可能已见过答案" in s, f"{rel} 里没有那句后果"


def test_the_footnote_rides_on_both_tables():
    """适配表与**主表**都带这条脚注：`to_latex` 的 caption 一律带；适配表的 CSV 每行也带。"""
    note = RP.ADAPT_ORACLE_EXPOSURE_NOTE
    assert "可能已见过答案" in note and "N-348" in note
    rows = RP.table_adaptation([{"config_id": "c", "arm": "adapt", "level": "L1",
                                 "outcome": "first_pass", "expected_outcome": "first_pass",
                                 "validator_rejections": 0}])
    assert rows and all(r["note"] == note for r in rows)
    assert "note" in RP.TABLE_ADAPTATION_COLUMNS
    tex_adapt = RP.to_latex(rows, ("config_id", "arm", "level", "n"),
                            caption="Table Adaptation", label="tab:adapt")
    assert "可能已见过答案" in tex_adapt
    main = RP.table_a([{"config_id": "c", "arm": "strict", "task_id": "s1-cor-01", "stage": "S1",
                        "run_status": "ok", "sr_bucket": "scorable", "validity": "valid",
                        "l3_pass": True, "malformed": False, "correctness": {"f1": 1.0}}])
    tex_main = RP.to_latex(main, ("config_id", "arm", "SR"), caption="Table A", label="tab:a")
    assert "可能已见过答案" in tex_main, "主表也要带 —— 读主表的人才是最需要知道这件事的人"
    assert "可能已见过答案" not in RP.to_latex(
        main, ("config_id", "arm", "SR"), caption="Table A", label="tab:a", footnote=None)


def test_the_exposed_task_list_is_in_the_set_manifest(exs):
    """逐题清单要能被人查到，而不是散在 30 份 mutation.json 里。"""
    p = PK.SET_MANIFEST
    if not p.is_file():
        pytest.skip("还没写集清单")
    m = json.loads(p.read_text(encoding="utf-8"))
    assert set(m["exposed_source_tasks"]) == {e.source_task for e in exs}
    assert "可能已见过答案" in m["pushable"]


def test_every_product_carries_its_own_exposure_note(muts):
    for eid, m in muts.items():
        assert "可能已见过答案" in m["_exposure"], eid
        assert m["source_task"] in m["_exposure"], eid


# ============================================================ 五、适配模块


def test_the_adaptation_module_is_released_and_its_shas_match_the_files():
    """P7 只投放 `released` 的清单。**内容一字未改**（sha 与 2026-09-07 相同），改的只有 status。"""
    m = json.loads((AT.MODULE_DIR / "MANIFEST.json").read_text(encoding="utf-8"))
    assert m["status"] == "released", "draft 状态下 adapt 臂就是个裸臂（P7 会拒）"
    assert m["artifacts"] == AT.module_manifest()["artifacts"]
    assert set(m["artifacts"]) == set(AT.MODULE_STATIC)
    for name, sha in m["artifacts"].items():
        import hashlib
        assert hashlib.sha256((AT.MODULE_DIR / name).read_bytes()).hexdigest() == sha, name
