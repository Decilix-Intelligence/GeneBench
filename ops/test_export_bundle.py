# -*- coding: utf-8 -*-
"""`ops/export_bundle.py` 的判别力测试 —— 盯的是 N-61 那次泄漏的**结构**。

那次事故里 bundle 自己是干净的：脏的是它**旁边**的 `reference/`，
而当时没有任何判据看「旁边」这一层。这里的核心两条就是这件事。
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from genetask import packager as P
from ops import export_bundle as E
from ops.push_guard import check_bundle_tree, check_manifest

FAKE_DIGEST = "sha256:" + "a" * 64
TASK = "s1-cor-01"


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """把答案面根挪到 tmp —— **只有测试能挪**，见下面的签名封闭测试。"""
    monkeypatch.setattr(E, "ANSWER_ROOT", tmp_path / "reference")
    return tmp_path


# ---------------------------------------------------------------- 结构判据（事故形状）
def test_answer_plane_beside_the_bundle_is_caught(tmp_path):
    """**当晚那棵树**：bundle 干净，同级多一个 `reference/`。"""
    staging = tmp_path / "a1"
    (staging / "runner" / "tasks" / "t1" / "work").mkdir(parents=True)
    (staging / "runner" / "tasks" / "t1" / "task.yaml").write_text("id: t1\n", encoding="utf-8")
    assert check_bundle_tree(staging / "runner" / "tasks" / "t1") == [], \
        "前提搭错：bundle 自己必须是干净的，否则这条测不到「旁边」那一层"
    ref = staging / "reference" / "tasks" / "v1.0-smoke" / TASK
    ref.mkdir(parents=True)
    (ref / "canary.json").write_text('{"gold_token": "GBC-G-' + "0" * 16 + '"}', encoding="utf-8")
    with pytest.raises(E.ExportBlocked) as e:
        E.assert_staging_has_no_answer_plane(staging)
    assert "reference" in str(e.value)


def test_clean_staging_passes(tmp_path):
    """防恒红：只有 bundle 的暂存根必须放行。"""
    staging = tmp_path / "a1"
    (staging / "t1" / "work").mkdir(parents=True)
    (staging / "t1" / "task.yaml").write_text("# x_token: GBC-X-" + "0" * 16 + "\n", encoding="utf-8")
    E.assert_staging_has_no_answer_plane(staging)      # 不抛即通过


@pytest.mark.parametrize("shape", ["gold", "solution", "scorer"])
def test_other_answer_plane_shapes_beside_bundle(tmp_path, shape):
    staging = tmp_path / "a1"
    (staging / shape).mkdir(parents=True)
    (staging / shape / "x.txt").write_text("x", encoding="utf-8")
    with pytest.raises(E.ExportBlocked):
        E.assert_staging_has_no_answer_plane(staging)


# ---------------------------------------------------------------- 端到端
def test_export_one_produces_a_pushable_bundle(isolated):
    """导出的东西必须被**推送侧**的两道门接受 —— 两个工具独立给出同一结论。"""
    staging = isolated / "stage"
    r = E.export_one(TASK, staging, FAKE_DIGEST)
    bundle, manifest = Path(r["bundle"]), Path(r["manifest"])
    assert check_bundle_tree(bundle) == []
    assert check_manifest(bundle, manifest) == []
    df = (bundle / "image" / "Dockerfile").read_text(encoding="utf-8")
    assert FAKE_DIGEST in df and "@sha256:" + "0" * 64 not in df, "digest 没钉上"


def test_answer_plane_never_lands_in_the_staging_root(isolated):
    """导出之后，暂存根里**一件**答案面都不许有。"""
    staging = isolated / "stage"
    E.export_one(TASK, staging, FAKE_DIGEST)
    E.assert_staging_has_no_answer_plane(staging)
    assert (isolated / "reference" / "tasks").is_dir(), "答案面得真的写出去了（否则这条恒绿）"
    assert not list(staging.rglob("canary.json"))


def test_dataplane_selfcheck_runs(isolated):
    """`check_private_files` 真的跑过了 —— 落盘的任务目录必须自检干净。"""
    staging = isolated / "stage"
    r = E.export_one(TASK, staging, FAKE_DIGEST)
    assert P.check_private_files(Path(r["task_dir"])) == []


def test_bad_digest_is_refused(isolated):
    with pytest.raises(E.ExportBlocked) as e:
        E.export_one(TASK, isolated / "stage", "sha256:not-a-digest")
    assert "digest" in str(e.value)


def test_unknown_task_is_refused(isolated):
    with pytest.raises(E.ExportBlocked):
        E.export_one("s9-nope-99", isolated / "stage", FAKE_DIGEST)


# ---------------------------------------------------------------- 判据是封闭的
def test_caller_cannot_choose_where_the_answer_plane_goes():
    """答案面落点**不是参数**。做成参数，下一个调用方就会把它指回 scratch。"""
    sig = inspect.signature(E.export_one)
    for name in sig.parameters:
        assert "answer" not in name and "reference" not in name and "ref_root" not in name, \
            f"export_one 暴露了答案面落点参数 {name!r} —— 那正是 N-61 的成因"
    assert E.ANSWER_ROOT.name == "reference"


def test_answer_root_is_an_allowed_gold_root():
    """落点必须落在 `test_env.GOLD_ALLOWED_ROOTS` 认的第一段里，否则那条 lint 会红。

    两份常量**在两个文件里各写一次**，所以这里显式对齐（D-21）。
    """
    from ops.test_env import GOLD_ALLOWED_ROOTS
    import genebench_config as cfg
    rel = Path(E.ANSWER_ROOT).relative_to(cfg.GENEBENCH_ROOT)
    assert rel.parts[0] in GOLD_ALLOWED_ROOTS


def test_manifest_carries_the_current_frozen_root(isolated):
    from ops.freeze_v10 import frozen_ref
    r = E.export_one(TASK, isolated / "stage", FAKE_DIGEST)
    m = json.loads(Path(r["manifest"]).read_text(encoding="utf-8"))
    assert m["frozen_manifest"] == frozen_ref()
    assert m["check_export"] == []


# ---------------------------------------------------------------- 门后必须有人（D-20）
def test_export_one_itself_refuses_a_dirty_staging_root(isolated):
    """**行为判据**：把答案面预埋进暂存根，`export_one` 自己必须拒绝。

    不是「旁边放着一个判据」—— 上面那些测试是直接调判据函数的，
    判据没接进 `export_one` 时它们照样绿（D-20 已经犯过五次）。
    """
    staging = isolated / "stage"
    (staging / "reference" / "tasks").mkdir(parents=True)
    (staging / "reference" / "tasks" / "canary.json").write_text("{}", encoding="utf-8")
    with pytest.raises(E.ExportBlocked):
        E.export_one(TASK, staging, FAKE_DIGEST)


def test_export_one_runs_the_bundle_tree_gate(isolated, monkeypatch):
    """接线判据：`check_bundle_tree` 的结论必须真的被 `export_one` 消费。"""
    from ops import push_guard
    monkeypatch.setattr(E, "check_bundle_tree", lambda d: ["假发现（接线测试）"])
    with pytest.raises(push_guard.PushBlocked):
        E.export_one(TASK, isolated / "stage", FAKE_DIGEST)


def test_export_one_consumes_the_dataplane_selfcheck(isolated, monkeypatch):
    """接线判据：`check_private_files` 报红时必须停，而不是继续出通行证。"""
    monkeypatch.setattr(P, "check_private_files", lambda d: ["G1 假违规（接线测试）"])
    with pytest.raises(E.ExportBlocked) as e:
        E.export_one(TASK, isolated / "stage", FAKE_DIGEST)
    assert "数据面自检" in str(e.value)


def test_gold_token_beside_the_bundle_with_an_innocent_name(tmp_path):
    """**只有内容判据能抓的形状**：暂存根里一个名字无辜、路径无辜的文件带 gold 串。

    X3 突变（拆掉串扫描）就活在这里 —— 事故里的 `canary.json` 同时踩了文件名判据，
    掩盖了内容这一层是不是真的在工作。
    """
    from ops.push_guard import GOLD_TOKEN_RE
    staging = tmp_path / "a1"
    (staging / "t1").mkdir(parents=True)
    leak = staging / "handoff_notes.md"
    leak.write_text("交接：核对串 GBC-G-" + "1" * 16 + "\n", encoding="utf-8")
    rel_parts = set(leak.relative_to(staging).parts)
    assert not (rel_parts & set(E.ANSWER_PLANE_SEGMENTS)) and leak.name not in E.ANSWER_PLANE_NAMES, \
        "前提搭错：这条要求文件名与路径都躲过前两层判据"
    assert GOLD_TOKEN_RE.search(leak.read_text(encoding="utf-8"))
    with pytest.raises(E.ExportBlocked) as e:
        E.assert_staging_has_no_answer_plane(staging)
    assert "gold" in str(e.value)
