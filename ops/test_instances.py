# -*- coding: utf-8 -*-
"""W3：参数轮换实例的测试。

判据分六组，对应任务书第 2/4/5/7 条：
指纹稳定性 · 同参数同 ID · 缺措辞当场拒 · 实例题面过 check_arms · 夹具 sha 与实例绑定 · 清单两层结构。

**恒绿检查**：每一条「应该拒」的断言都配了一条**负例**（换成合法取值必须通过），
否则「拒了」可能只是因为函数整个跑不起来。
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from genetask import render as R                        # noqa: E402
from ops import mk_instances as MI                      # noqa: E402


@pytest.fixture(scope="module")
def spec():
    return MI.load_spec()


@pytest.fixture(scope="module")
def rows(spec):
    return MI.base_rows(spec)


@pytest.fixture(scope="module")
def instances(spec, rows):
    return MI.enumerate_instances(spec, rows)


# ============================================================== ① 指纹稳定性

def test_fingerprint_is_key_order_and_dict_order_independent(rows):
    r = rows["s4-cor-01"]
    a = {"window": {"end": "2026-03-31", "start": "2026-01-05"}}
    b = {"window": {"start": "2026-01-05", "end": "2026-03-31"}}
    assert MI.fingerprint(a, r) == MI.fingerprint(b, r)


def test_fingerprint_is_pinned_across_machines(rows):
    """跨机可复现：拿死值钉住，不是「跑两遍一样」（那条同一进程内必然成立）。"""
    r = rows["s4-cor-01"]
    empty = hashlib.sha256(b"{}").hexdigest()[:MI.FINGERPRINT_LEN]
    assert MI.fingerprint({}, r) == empty == "44136fa355"
    assert MI.fingerprint({"window": {"start": "2026-01-05", "end": "2026-03-31"}}, r) == "f436d8670e"
    assert MI.fingerprint({"universe": "csi500"}, r) == "0b0d39a2c6"


def test_normalize_drops_values_equal_to_the_base(rows):
    """规范化第二条：等于基点现值的维度不进指纹（"不含默认值"）。"""
    r = rows["s4-cor-01"]
    same_window = {"start": r["window"]["start"], "end": r["window"]["end"]}
    assert MI.normalize({"window": same_window, "universe": r["universe"]}, r) == {}
    assert MI.fingerprint({"window": same_window}, r) == MI.fingerprint({}, r)
    # 负例：换一个不同的窗口必须进指纹，否则上一条只是「normalize 恒返回空」
    assert MI.normalize({"window": {"start": "2026-04-01", "end": "2026-06-30"}}, r) != {}


def test_normalize_uses_value_key(rows):
    r = rows["s4-cor-01"]
    n = MI.normalize({"window": {"start": "2026-04-01", "end": "2026-06-30"}}, r)
    assert n["window"] == R.value_key({"start": "2026-04-01", "end": "2026-06-30"})
    assert list(n) == sorted(n)                       # 键排序


def test_normalize_rejects_unknown_axis(rows):
    with pytest.raises(MI.InstanceError):
        MI.normalize({"lookback": 20}, rows["s4-cor-01"])
    MI.normalize({"universe": "csi500"}, rows["s4-cor-01"])          # 负例


# ============================================================== ② 同参数同 ID

def test_same_params_same_id(spec, rows):
    r = rows["s3-cor-01"]
    p1 = {"universe": "csi500", "window": {"start": "2026-01-05", "end": "2026-03-31"}}
    p2 = {"window": {"end": "2026-03-31", "start": "2026-01-05"}, "universe": "csi500"}
    id1 = MI.make_instance_id("S3", "cor01_wq006_corr", "s3-cor-01", MI.fingerprint(p1, r))
    id2 = MI.make_instance_id("S3", "cor01_wq006_corr", "s3-cor-01", MI.fingerprint(p2, r))
    assert id1 == id2


def test_instance_ids_are_unique(instances):
    ids = [i.instance_id for i in instances]
    assert len(set(ids)) == len(ids)
    assert len({i.task_id for i in instances}) == len(ids)


def test_shared_template_dir_does_not_collide(instances):
    """`S1/source_status` 被 s1-rob-01（规定题）与 s1-rob-02（探针题）两行复用，
    两行的窗口与宇宙又恰好相同 —— instance_id 里不带 base_task_id 就会撞（实测撞过）。"""
    a = [i for i in instances if i.base_task_id == "s1-rob-01" and i.is_base][0]
    b = [i for i in instances if i.base_task_id == "s1-rob-02" and i.is_base][0]
    assert a.template_id == b.template_id
    assert a.fingerprint == b.fingerprint            # 参数字典都是 {}
    assert a.instance_id != b.instance_id            # 但 id 必须不同


def test_task_id_allocation_is_deterministic_and_appends(spec, rows):
    a = {i.instance_id: i.task_id for i in MI.enumerate_instances(spec, rows)}
    b = {i.instance_id: i.task_id for i in MI.enumerate_instances(spec, rows)}
    assert a == b
    # **基点实例也发新号**（N-578，用户裁定 ③，2026-09-11）：沿用基点号会让
    # `v1.0-instances/s8-cor-01` 与 `v1.0-smoke/s8-cor-01` 同号，
    # `gateway/sim_factory.task_dir` 因此定位不到题目录，S8 的 gold 一份都算不出来。
    for i in MI.enumerate_instances(spec, rows):
        if i.is_base:
            assert i.task_id != i.base_task_id, "基点实例又与基点题同号了"
    ids = [i.task_id for i in MI.enumerate_instances(spec, rows)]
    assert len(set(ids)) == len(ids), "实例之间撞号"
    assert not (set(ids) & set(rows)), "实例与出集的题同号" 
    # 变体号一律 > 出集里该 (stage, family) 的最大号 —— 不会覆盖出集的题
    used = {}
    for tid in rows:
        m = MI._TASK_ID_RE.match(tid)
        used.setdefault((f"S{m.group(1)}", m.group(2)), 0)
        used[(f"S{m.group(1)}", m.group(2))] = max(used[(f"S{m.group(1)}", m.group(2))], int(m.group(3)))
    for i in MI.enumerate_instances(spec, rows):
        m = MI._TASK_ID_RE.match(i.task_id)
        assert int(m.group(3)) > used[(i.stage, i.family.lower())], \
            f"{i.instance_id} 的号 {i.task_id} 没有超过出集里该组的最大号 —— 会覆盖出集的题" 


# ============================================================== ③ 缺措辞当场拒

def test_missing_phrasing_is_rejected_on_the_spot(spec):
    """凡是 phrasebook 里没有措辞的取值，生成器必须当场拒并**报出是哪个取值**。"""
    with pytest.raises(MI.MissingPhrasing) as e:
        MI.check_phrasing(spec, "universe", "S1", "csi1000", where="T")
    assert e.value.field == "universe" and e.value.value_key == "csi1000"
    with pytest.raises(MI.MissingPhrasing) as e:
        MI.check_phrasing(spec, "factor_pool", "S5", "gtja_191.002", where="T")
    assert e.value.field == "input_factors"
    # 负例：有措辞的取值必须放行（否则上面两条只证明这个函数恒抛）
    MI.check_phrasing(spec, "universe", "S1", "csi500", where="T")
    MI.check_phrasing(spec, "universe", "S2", "csi500", where="T")


def test_axes_that_do_not_reach_declared_need_no_phrasing(spec):
    """S3/S4 的 universe 只落固定槽 task_universe，措辞由 FIXED_PHRASES 机器生成 ——
    不查 phrasebook。但**它也不许悄悄放行会落 declared 的那些**（上一条守着）。"""
    MI.check_phrasing(spec, "universe", "S4", "csi500", where="T")
    MI.check_phrasing(spec, "window", "S4", {"start": "2026-01-05", "end": "2026-03-31"}, where="T")


def test_every_generated_value_has_phrasing(spec, instances):
    """参数表里列的每个取值都过一遍措辞闸 —— 表里写了没措辞的取值要在这里红。"""
    for i in instances:
        for axis, v in i.params.items():
            MI.check_phrasing(spec, axis, i.stage, v, where=i.instance_id)


# ============================================================== ④ 实例题面过 check_arms

def test_all_instances_build_green(spec, instances):
    """E1–E15 / R1–R5 / C1 全套照查（`packager.build_task` 内部就在跑 `render.check_arms`）。
    **没有任何一条规则对实例开例外。**"""
    red = MI.validate_all(spec, instances)
    assert red == {}, json.dumps({k: v[:4] for k, v in list(red.items())[:5]}, ensure_ascii=False)


def test_one_param_change_moves_the_text_but_not_the_slots(instances):
    """任务书第 4 条的判据原话：改一个参数 → 题面变、槽位集不变、等价表仍 ok。"""
    base = [i for i in instances if i.base_task_id == "s4-cor-01" and i.is_base][0]
    bb = MI.build(base)
    bfp = MI.instruction_fingerprint(bb)
    moved = 0
    for i in instances:
        if i.base_task_id != "s4-cor-01" or i.is_base:
            continue
        b = MI.build(i)
        assert b.ok, b.problems
        assert b.strict.slots == bb.strict.slots      # 槽位**序列**不变（E1 比的就是序列）
        assert b.open.slots == bb.open.slots
        assert set(b.task["declared"]) == set(bb.task["declared"])
        if set(i.norm) & {"window", "universe"}:
            assert MI.instruction_fingerprint(b) != bfp    # 题面确实变了
            moved += 1
    assert moved >= 1


def test_factor_axis_moves_the_fixture_not_the_text(instances):
    """S4 的因子只走 gold_args 与夹具 origin —— `packager._inputs_phrase` 刻意不把 origin
    写进题面，所以换因子**题面逐字不变、夹具变**。这不是漏洞，是这一维度的定义。"""
    base = [i for i in instances if i.base_task_id == "s4-cor-01" and i.is_base][0]
    bfp = MI.instruction_fingerprint(MI.build(base))
    fonly = [i for i in instances if list(i.norm) == ["factor_pool"]]
    assert fonly, "因子轴一个纯变体都没有 —— 轮换排布把它挤掉了"
    for i in fonly:
        assert MI.instruction_fingerprint(MI.build(i)) == bfp
        assert [x["origin"] for x in i.row["inputs"]] != \
               [x["origin"] for x in base.row["inputs"]]
        assert i.row["gold_args"]["factor_id"] != base.row["gold_args"]["factor_id"]


def test_probe_instances_keep_their_underdetermined_field(instances):
    """探针实例的欠定字段一个字不动 —— 换窗口不该把探针题变成规定题。"""
    for i in instances:
        base_under = i.row["underdetermined"]
        if i.base_task_id.endswith("-rob-02") and i.stage in ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"):
            assert i.row["kind"] in ("underdetermined_probe", "regulated")
        if i.row["kind"] == "underdetermined_probe":
            assert len(base_under) == 1
            b = MI.build(i)
            assert b.task["probes"]["target_field"] == base_under[0]


# ============================================================== ⑤ 夹具 sha 与实例绑定

def test_variant_inputs_have_no_inherited_sha(instances):
    """变体的夹具还没物化 —— 留着基点的 sha 就是「这份夹具有身份」的假绿。"""
    for i in instances:
        if i.is_base or not i.row.get("inputs"):
            continue
        assert all(x["sha256"] is None for x in i.row["inputs"]), i.instance_id


def test_variant_origin_follows_the_instance(instances):
    """夹具 origin 里的宇宙 / 因子 token 必须跟着实例走，否则夹具会从基点的面板切。"""
    for i in instances:
        if not i.row.get("inputs"):
            continue
        u = i.row["universe"]
        for it in i.row["inputs"]:
            o = str(it["origin"])
            if o.startswith("reference/gold_factors/"):
                assert o.split("/")[2] == u, (i.instance_id, o)
            if o.startswith("2.1b gold 因子面板"):
                assert f"@{u} " in o or o.endswith(f"@{u}"), (i.instance_id, o)
            assert it["max_date"] == i.row["window"]["end"], (i.instance_id, it)


def test_unknown_origin_is_refused_not_guessed():
    with pytest.raises(MI.InstanceError):
        MI._rewrite_origin("某个没见过的来源", universe="csi500", factor=None)
    assert MI._rewrite_origin("reference/gold_factors/csi300/gtja_191.001",
                              universe="csi500", factor=None) == \
        "reference/gold_factors/csi500/gtja_191.001"          # 负例


def test_fixture_shas_round_trip_and_bind_to_instance_id(tmp_path, spec, instances):
    src = _REPO / "genetask" / "params" / "v1.0-instances.yaml"
    dst = tmp_path / "spec.yaml"
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    i = [x for x in instances if x.row.get("inputs") and not x.is_base][0]
    i.fixtures = {"work/factor_panel.parquet": "a" * 64}
    assert MI.write_fixture_shas([i], dst) == 1
    doc = yaml.safe_load(dst.read_text(encoding="utf-8"))
    assert doc["fixtures"][i.instance_id] == {"work/factor_panel.parquet": "a" * 64}
    # 绑定在 instance_id 上：别的实例读不到它
    other = [x for x in instances if x.instance_id != i.instance_id][0]
    assert MI.recorded_fixtures(doc, other) == {}
    assert MI.recorded_fixtures(doc, i) == {"work/factor_panel.parquet": "a" * 64}
    assert MI.write_fixture_shas([i], dst) == 0                 # 幂等


def test_fixture_write_back_preserves_the_comments(tmp_path, spec, rows):
    """写回一个 sha 不许抹掉参数表的注释。

    第一版 `write_fixture_shas` 用 `yaml.safe_dump(doc)` 整文件重写 —— 参数表里逐条写着
    「这个取值为什么可以用 / 那个为什么不许用」的注释**全部没了**（13162 → 9395 字节，实测）。
    参数表的一多半价值就在那些注释里。
    """
    src = _REPO / "genetask" / "params" / "v1.0-instances.yaml"
    dst = tmp_path / "spec.yaml"
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    before = [ln for ln in dst.read_text(encoding="utf-8").splitlines() if ln.startswith("#")]
    assert len(before) > 20, "参数表本来就没几行注释，这条测试证明不了什么"

    fresh = MI.enumerate_instances(spec, rows)
    i = [x for x in fresh if x.row.get("inputs") and not x.is_base][0]
    i.fixtures = {"work/factor_panel.parquet": "c" * 64}
    assert MI.write_fixture_shas([i], dst) == 1

    after_text = dst.read_text(encoding="utf-8")
    assert [ln for ln in after_text.splitlines() if ln.startswith("#")] == before
    doc = yaml.safe_load(after_text)
    assert doc["fixtures"][i.instance_id] == {"work/factor_panel.parquet": "c" * 64}
    assert doc["deferred"] and doc["bases"] and doc["values"]      # 别的段一个没少


# ============================================================== ⑥ 清单两层结构

@pytest.fixture(scope="module")
def section(spec):
    return MI.manifest_section(spec, with_instruction_fingerprint=True)


def test_manifest_has_two_layers(section, instances):
    assert set(section["bases"]) == {i.base_task_id for i in instances}
    assert section["counts"]["bases"] == 40
    assert section["counts"]["instances"] == len(instances)
    for tid, b in section["bases"].items():
        assert b["instances"], tid
        assert sum(1 for e in b["instances"] if e["is_base"]) == 1
        for e in b["instances"]:
            for k in ("instance_id", "task_id", "fingerprint", "params",
                      "instruction_fingerprint", "fixtures"):
                assert k in e, (tid, k)


def test_manifest_counts_match_the_target(spec, section):
    lo, hi = spec["target"]["per_stage_min"], spec["target"]["per_stage_max"]
    per = section["counts"]["per_stage"]
    assert len(per) == 8
    for s, n in per.items():
        assert lo <= n <= hi, (s, n)
    assert 120 <= section["counts"]["instances"] <= 140


def test_instances_fingerprint_moves_with_a_fixture_sha(section):
    a = MI.instances_fingerprint(section)
    import copy
    s2 = copy.deepcopy(section)
    first = sorted(s2["bases"])[0]
    s2["bases"][first]["instances"][0]["fixtures"] = {"work/x.parquet": "b" * 64}
    assert MI.instances_fingerprint(s2) != a


def test_instances_fingerprint_is_in_the_frozen_root():
    """**2026-09-10 翻转**（用户裁定 ⑤，卡 A）。原断言是「不进根」，理由是
    「进了根，加一个实例就会让所有已发通行证作废」，并写着「收不收进根由 Y1 定」——
    现在定了：收。**那个代价是自愿付的**，换来的是根重新回答得了
    「被测方这一次拿到的是哪一批题」：实例层有 130 道，根只覆盖出集 34 道时，
    换掉整张实例参数表，根 hash 一个字不变。

    `instances` 整段**仍然不进根**：进去的是指纹。段里有 `fixtures` 这类会随物化进度变的
    元数据，把它整段收进根等于「物化一个夹具就作废所有通行证」—— 那才是没必要的代价。
    """
    from ops import freeze_v10 as F
    assert "instances_fingerprint" in F.ROOT_FIELDS
    assert "instances" not in F.ROOT_FIELDS, "进根的是指纹，不是整段"


def test_the_manifest_cannot_be_rooted_without_the_instances_section():
    """指纹进根之后，**不带实例段就必须算不出根** —— 且报错要说得出为什么。
    这条是上一条的判别力：只断言「在 ROOT_FIELDS 里」的话，
    哪天有人给 `manifest_root` 加个 `.get(k)` 兜底，上一条照绿，而根会静默少一个字段。"""
    from ops import freeze_v10 as F
    import pytest as _pt
    thin = F.build_manifest(with_instances=False)
    assert "instances_fingerprint" not in thin
    with _pt.raises(SystemExit, match="instances_fingerprint"):
        F.manifest_root(thin)


def test_caps_match_freeze():
    from ops import freeze_v10 as F
    assert MI.CAPS == F.CAPS, "两处能力位不一致会让「实例能建、出集不能建」这种鬼事发生"


def test_freeze_manifest_carries_instances_when_asked():
    from ops import freeze_v10 as F
    sec = F.build_instances_section()
    assert sec["counts"]["bases"] == 40
    assert sec["set_id"] == "v1.0-instances"
