# -*- coding: utf-8 -*-
"""卡 F1：公开轴分离（①/N-605）、实例 ID 与 sim 会话键（③/N-578）、
适配切片回库（⑤/N-645）、`REVISIONS` 复活（⑦/N-573）。

每一条都盯着**这次改动之前会红**的那件事，不是盯着「代码还在」。
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import genebench_config as cfg                    # noqa: E402
from genetask import packager as P                # noqa: E402
from ops import freeze_v10 as F                   # noqa: E402
from ops import mk_instances as MI                # noqa: E402

GB = cfg.GENEBENCH_ROOT
PRIV = GB / "reference" / "tasks" / "v1.0-smoke"
PUB = GB / "reference" / "tasks" / "public" / "v1.0-smoke-public"
WITH_INPUTS = ("s4-cor-01", "s5-cor-01", "s6-cor-01", "s7-cor-01", "s7-rob-02")
S8_SMOKE = ("s8-cor-01", "s8-eco-01", "s8-ops-01", "s8-rob-01")


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ---------------------------------------------------------------- ⑦ REVISIONS 复活

def test_revisions_last_entry_is_the_current_set_version():
    """本卡的验收条：`REVISIONS` 的最后一条就是当前号。

    改动之前这条**必红**：`REVISIONS` 停在 1.0.6（拆轴之后的任务集记因全写进了
    `REFERENCE_REVISIONS`），而 `SET_VERSION` 已经是 1.0.15。
    """
    assert F.REVISIONS[-1]["version"] == F.SET_VERSION
    assert F.REFERENCE_REVISIONS[-1]["version"] == F.REFERENCE_VERSION


def test_both_revision_tables_are_ascending_and_single_axis():
    """升序 + 分轴干净：参考表里不许再有任务集的号（那正是 N-573 的病灶）。"""
    def key(v: str) -> tuple:
        import re
        n = [int(x) for x in re.findall(r"\d+", v)[:3]]
        return tuple(n + [0] * (3 - len(n)))
    for tbl in (F.REVISIONS, F.REFERENCE_REVISIONS):
        ks = [key(r["version"]) for r in tbl]
        assert ks == sorted(ks), f"记因表不是升序：{[r['version'] for r in tbl]}"
    assert not [r for r in F.REFERENCE_REVISIONS if not r["version"].startswith("r")], \
        "REFERENCE_REVISIONS 里还有任务集轴的条目 —— 那是 N-573 的病灶"
    assert not [r for r in F.REVISIONS if r["version"].startswith("r")]


def test_every_revision_has_all_five_segments():
    for r in list(F.REVISIONS) + list(F.REFERENCE_REVISIONS):
        for k in ("version", "at", "ticket", "why", "what", "scope", "gates"):
            assert r.get(k), f"{r.get('version')} 的记因缺 {k}"


def test_revised_at_now_points_at_the_newest_entry():
    """`build_manifest` 的 `revised_at` 取 `REVISIONS[-1]["at"]` —— 表倒序时它指向**最旧**那条。"""
    m = json.loads((REPO / "ops" / "manifests" / "v1.0-smoke.json").read_text(encoding="utf-8"))
    assert m["revised_at"] == F.REVISIONS[-1]["at"]
    assert m["revised_at"] == max(r["at"] for r in F.REVISIONS)


# ---------------------------------------------------------------- ① 公开轴

def test_public_axis_has_its_own_version_and_root():
    assert F.SET_VERSION_PUBLIC != F.SET_VERSION
    pm = json.loads(F.OUT_PUBLIC.read_text(encoding="utf-8"))
    m = json.loads(F.OUT.read_text(encoding="utf-8"))
    assert pm["set_version"] == F.SET_VERSION_PUBLIC
    assert pm["set_id"] == F.PUBLIC_SET_ID
    assert F.manifest_root(pm) != F.manifest_root(m), "两条通道的根一样 —— 那就等于没分轴"
    assert "channel_fixtures" in F.PUBLIC_ROOT_FIELDS and "channel_fixtures" not in F.ROOT_FIELDS


def test_public_root_covers_the_real_fixture_bytes():
    """公开根盖得住公开夹具：改一个字节，现算根就变。"""
    pm = json.loads(F.OUT_PUBLIC.read_text(encoding="utf-8"))
    fx = pm["channel_fixtures"]
    assert fx, "公开清单里一件夹具都没有"
    tampered = json.loads(json.dumps(pm))
    tid = sorted(fx)[0]
    rel = sorted(fx[tid])[0]
    tampered["channel_fixtures"][tid][rel] = "0" * 64
    assert F.manifest_root(tampered) != F.manifest_root(pm)


def test_frozen_ref_picks_the_manifest_by_channel():
    assert F.manifest_path_for("public") == F.OUT_PUBLIC
    assert F.manifest_path_for("private") == F.OUT


@pytest.mark.parametrize("task_id", WITH_INPUTS)
def test_public_tasks_with_inputs_can_be_exported(task_id, tmp_path):
    """公开通道那 5 道带 inputs 的题出得了集，且 X task.yaml 写的是**盘上真值**。

    改动之前这条必红：`export_task` 拿私有声明去核公开字节，`PackError` 当场抛。
    """
    if not (PUB / task_id / "task.yaml").is_file():
        pytest.skip(f"公开树上没有 {task_id}")
    bundle = P.export_task(PUB / task_id, tmp_path / "out", channel="public")
    x = yaml.safe_load((Path(bundle) / "task.yaml").read_text(encoding="utf-8"))
    declared = {i["path"]: i["sha256"] for i in (x.get("inputs") or [])}
    assert declared, f"{task_id} 的 X task.yaml 里没有 inputs"
    for rel, got in declared.items():
        assert got == _sha(PUB / task_id / rel), f"{task_id}/{rel} 写的不是盘上真值"
        assert (Path(bundle) / rel).is_file()


def test_public_leak_gate_still_has_teeth(tmp_path):
    """公开夹具的字节**等于私有声明值** = 私有那份漏进了公开树 —— 必须当场红。"""
    lab = tmp_path / "s4-cor-01"
    shutil.copytree(PUB / "s4-cor-01", lab)
    shutil.copy(PRIV / "s4-cor-01" / "work" / "factor_panel.parquet",
                lab / "work" / "factor_panel.parquet")
    with pytest.raises(P.PackError, match="私有"):
        P.export_task(lab, tmp_path / "out", channel="public")


def test_private_export_is_byte_identical_to_before(tmp_path):
    """私有通道**逐字节不变**：同一道题导两次（默认通道 / 显式 private）逐文件 sha256 相同。

    「改前改后」的那一半在 `ops/reports/f1_private_export_bitwise.md`（新旧 packager 各导一次）。
    """
    for tid in ("s4-cor-01", "s1-cor-01"):
        a = P.export_task(PRIV / tid, tmp_path / f"a-{tid}")
        b = P.export_task(PRIV / tid, tmp_path / f"b-{tid}", channel="private")
        ta = {str(p.relative_to(a)): _sha(p) for p in sorted(Path(a).rglob("*")) if p.is_file()}
        tb = {str(p.relative_to(b)): _sha(p) for p in sorted(Path(b).rglob("*")) if p.is_file()}
        assert ta == tb and ta


# ---------------------------------------------------------------- ③ 实例 ID 与 sim 会话

def test_base_instances_no_longer_share_numbers_with_the_smoke_set():
    spec = MI.load_spec()
    ins = MI.enumerate_instances(spec)
    clash = sorted({i.task_id for i in ins} & set(spec["bases"]))
    assert not clash, f"实例与基点题同号：{clash} —— sim_factory 会因此无法定位题目录"
    assert all("#" in i.instance_id for i in ins), "实例 id 没带参数指纹"
    assert len({i.task_id for i in ins}) == len(ins), "实例之间自己撞号了"


def test_variant_numbering_did_not_shift():
    """基点后置发号，**变体的号一个都不动** —— 重排比同号更坏。"""
    ins = MI.enumerate_instances(MI.load_spec())
    var = sorted((i for i in ins if not i.is_base),
                 key=lambda x: (x.stage, x.family, x.template_id, x.fingerprint))
    s1 = [i.task_id for i in var if i.stage == "S1" and i.family.lower() == "cor"]
    assert s1 == sorted(s1), "变体发号不再是顺序的"
    assert s1 and s1[0] == "s1-cor-02", f"S1/cor 的第一个变体号变了：{s1[:3]}"


@pytest.mark.parametrize("task_id", S8_SMOKE)
def test_task_dir_no_longer_guesses_between_two_sets(task_id):
    """改动之前：`v1.0-smoke` 与 `v1.0-instances` 各有一份同号的题，`task_dir` 当场 RuntimeError。"""
    from gateway import sim_factory as SF
    d = SF.task_dir(task_id, "v1.0-smoke")
    assert d == GB / "reference" / "tasks" / "v1.0-smoke" / task_id
    assert (d / "task.yaml").is_file()


def test_sim_factory_set_id_is_required():
    from gateway import sim_factory as SF
    import inspect
    sig = inspect.signature(SF.build_engine)
    assert sig.parameters["set_id"].default is inspect.Parameter.empty, \
        "build_engine 的 set_id 还有默认值 —— 默认值就是「同号就挑一个」"
    with pytest.raises(ValueError, match="必填"):
        SF.task_dir("s8-cor-01", "")


def test_session_key_carries_the_set_id():
    from gateway.routers import sim as SR
    from gateway.sim_engine import SimEngine
    SR.reset_sessions()
    eng = SimEngine(calendar=["2026-07-01"], window_end="2026-07-01", closes={}, opens={},
                    tradable={}, limit_up=set(), limit_down=set(),
                    slippage_reference_price=None, permitted_operations=("buy",))
    SR.register_session("run-x", "s8-cor-01", eng, set_id="v1.0-smoke")
    SR.register_session("run-x", "s8-cor-01", eng, set_id="v1.0-instances")
    keys = [k for k in SR._SESSIONS if k[0] == "run-x"]
    assert len(keys) == 2 and all(len(k) == 3 for k in keys), \
        f"同号不同集共用了一个会话：{keys}"
    SR.reset_sessions()


# ---------------------------------------------------------------- ⑤ 适配切片回库

def test_adaptation_slice_in_db_matches_the_report():
    from ops import results_db as DB
    rows = [r for r in DB.load(None) if r.get("track") == "adaptation"]
    cur = [r for r in rows if not r.get(DB.SUPERSEDED_FIELD)]
    old = [r for r in rows if r.get(DB.SUPERSEDED_FIELD)]
    from collections import Counter
    assert Counter(r["outcome"] for r in cur) == \
        Counter({"first_pass": 17, "correct_flag": 6, "failed": 7}), \
        "库里的适配结局与报告对不上（报告 17/6/7）"
    assert len(old) == 30, "查不到被取代的那 30 行 —— 删行等于把已发表那版变成无出处"
    assert all(r.get(DB.SUPERSEDED_BY) and r.get(DB.SUPERSEDED_NOTE) for r in old)
    assert {(r["set_version"], r["reference_version"]) for r in cur} == {("1.0.15", "r1.0.22")}


def test_superseded_rows_yield_the_primary_key():
    """旧行让出主键，新行才收得进来 —— 不然同 `(batch, run_id)` 只能覆盖或报错。"""
    from ops import results_db as DB
    base = {"batch": "adapt", "run_id": "x.y.z"}
    k1 = DB.key_of(base)
    k2 = DB.key_of({**base, DB.SUPERSEDED_FIELD: True, DB.SUPERSEDED_AT: "20260911T000000Z"})
    assert k1 != k2 and k1 in k2
