#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""参数轮换实例生成器（W3，2026-09-10）。

**一句话**：拿出集参数表的 40 行，沿「窗口 × 宇宙 × 因子池」换取值，得到约 130 个实例；
题面与夹具**都走既有路径**产出 —— 渲染走 `genetask.render.render_arm` + 现有 phrasebook，
夹具走 `reference.make_fixtures.materialize`。本模块**一行渲染逻辑都不新写**。

为什么这是「槽位机器生成、不必重签」
------------------------------------
签字签的是**措辞**，不是取值。三条判据合起来才成立，缺一条都不成立：

1. 每个会落进 ``declared`` 的取值，phrasebook 里**已经**有 strict/open 两列措辞
   （:func:`check_phrasing`；缺就当场拒，报出是哪个字段的哪个取值）。
   往 phrasebook 加新词会改 ``genetask/phrasebook.yaml`` —— 它在冻结根
   ``ops/freeze_v10.py::CODE_FILES`` 里，加一个词 40 道出集题全部重签。
2. 只改**取值**，不改**键集**：``declared`` 的键集与 ``underdetermined`` 一字不动，
   于是 ``packager.build_task`` 的 T1（模板 slots == 声明字段全集）与
   ``render.check_arms`` 的 E1（两臂槽位**序列**相等）自动仍成立。
3. 每个实例都跑一遍 :func:`build`（= ``packager.build_task``），E1–E15 / R1–R5 / C1
   全套照查，红了就不生成。**没有任何一条规则对实例开例外。**

窗口与宇宙落在**固定槽**（``task_window`` / ``task_universe``）上，措辞由
``render.FIXED_PHRASES`` 用 ``{v}`` 拼出来，本来就是机器生成的；
S4 的因子只走 ``gold_args`` 与夹具 ``origin``，而 ``packager._inputs_phrase``
**刻意不把 origin 写进题面** —— 所以换因子**题面逐字不变、夹具变**。

指纹的规范化规则（写死，配测试）
--------------------------------
``instance_id = <stage>/<template_id>@<base_task_id>#<fingerprint>``

* ``stage`` 必须在里面：``rob_underdetermined`` 这个 template_id 在 S6 与 S7 各有一份。
* ``base_task_id`` 也必须在里面：``S1/source_status`` 被 ``s1-rob-01``（规定题）与
  ``s1-rob-02``（探针题）**两行**复用，两行的窗口与宇宙又恰好相同 —— 光靠
  ``模板 ID + 参数指纹`` 这两道基准实例的 id 逐字节相同（实测撞了，见
  ``ops/test_instances.py::test_shared_template_dir_does_not_collide``）。
  身份的单位是**参数表的一行**，不是模板目录。
* 指纹 = 规范化参数字典的 sha256 前 10 位。规范化四条（:func:`normalize`）：

  1. **只收维度参数**（window / universe / factor_pool），别的一律不进；
  2. **剔除等于基准的维度**（"不含默认值"）—— 基准实例的参数字典因此是 ``{}``；
  3. 取值一律过 ``render.value_key``（与 phrasebook 取键同一个函数，dict 走规范 JSON）；
  4. ``json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)`` 再 sha256。

同参数必得同 ID，与机器、与枚举顺序、与 seed 都无关。

``task_id`` 怎么来
------------------
``instance_id`` 是实例的**身份**，但 ``genetask/schema.py`` 的 ``task_id`` 正则是
``^s[1-8]-(cor|rob|eco|ops)-\\d{2}$`` —— 装不下指纹。所以：

* 变体实例在 ``(stage, family)`` 内按 ``(template_id, fingerprint)`` 排序，
  从该组基点里最大的编号 +1 开始顺序发号。**确定性、跨机可复现**；
  加一个实例只会往后追号，不会重排已有的（:func:`allocate_task_ids` 配测试）。
* 基准实例**也发新号**，排在变体之后（N-578，用户裁定 ③，2026-09-11）。
  原来它沿用基点自己的 ``task_id``，于是 ``v1.0-instances/s8-cor-01`` 与
  ``v1.0-smoke/s8-cor-01`` 同号 —— ``gateway/sim_factory.task_dir`` 靠 glob 找题目录，
  同号就是歧义，它当场 ``RuntimeError`` 不猜，**S8 四道题的 gold 因此一份都算不出来**。
  发号顺序刻意是「变体先、基点后」：变体的编号一个都不动。

用法
----
    python3 ops/mk_instances.py --list                 # 逐实例一行（id / task_id / 参数）
    python3 ops/mk_instances.py --build                # 全部过 build_task，红了非零退出
    python3 ops/mk_instances.py --manifest             # 打印冻结清单的 instances 段
    python3 ops/mk_instances.py --fixtures --stages S4 # 按实例从 gold 面板导出夹具
    python3 ops/mk_instances.py --fixtures --stages S4 --write-shas   # 再把 sha 写回参数表

**本模块不推任何版本号**，也不动出集的 40 行参数。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from genetask import packager as P                      # noqa: E402
from genetask import render as R                        # noqa: E402
from genetask import schema as S                        # noqa: E402

SPEC = _REPO / "genetask" / "params" / "v1.0-instances.yaml"

#: 与 `ops/freeze_v10.py::CAPS` 同值。**不 import 它** —— freeze 要 import 本模块，
#: 反向 import 会成环。两处不一致会让「实例能建、出集不能建」这种鬼事发生，
#: 所以 `ops/test_instances.py::test_caps_match_freeze` 盯着这一条。
CAPS = {"n33_bars_open_amount_vwap": True, "s8_state_endpoint": True, "anchor_ladder_54": False}

#: 维度名。顺序即笛卡尔积的维度顺序（决定组合的字典序），**不许重排**。
AXES: tuple[str, ...] = ("window", "universe", "factor_pool")

FINGERPRINT_LEN = 10
_NONCE_RE = re.compile(r"GBC-[A-Z]-[0-9a-f]{16}")
_TASK_ID_RE = re.compile(r"^s([1-8])-(cor|rob|eco|ops)-(\d{2})$")

#: 夹具 origin 里带宇宙的两种写法（`reference/make_fixtures.py` 的 `_GOLD` / `_S5_INPUT` 同源）。
_ORIGIN_GOLD = re.compile(r"^reference/gold_factors/(?P<uni>[^/]+)/(?P<fid>[^#]+?)(?P<meta>#meta)?$")
_ORIGIN_S5 = re.compile(r"^(?P<head>2\.1b gold 因子面板 )(?P<fid>\S+)(?P<at>\s@)(?P<uni>\S+)(?P<tail>.*)$")
#: 明确「不带宇宙、不用改」的 origin —— 认不出的一律报错，不猜（与 make_fixtures 同一条纪律）。
_ORIGIN_NO_UNIVERSE = ("reference/pools/", "f01 物化：", "signal:", "reference/signals/")


class InstanceError(RuntimeError):
    pass


class MissingPhrasing(InstanceError):
    """某个取值在 phrasebook 里没有措辞 —— 用它就得人工写措辞，那就不是「不重签」了。"""

    def __init__(self, field_: str, value, value_key: str, axis: str, where: str):
        self.field, self.value, self.value_key, self.axis, self.where = field_, value, value_key, axis, where
        super().__init__(
            f"{where}：维度 {axis} 的取值 {value!r} 要落进 declared.{field_}，"
            f"而 phrasebook[{field_}] 里没有键 {value_key!r} —— "
            f"用它必须先人工写 strict/open 两列措辞，那就是重签。"
            f"可用的键：{sorted(_phrasebook().get(field_, {}))}")


# ============================================================== 输入

_PB_CACHE: dict = {}


def _phrasebook() -> dict:
    if not _PB_CACHE:
        _PB_CACHE.update(R.load_phrasebook(P.PHRASEBOOK))
    return _PB_CACHE


def load_spec(path: Path = SPEC) -> dict:
    doc = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    for k in ("set_id", "base_params", "axes", "values", "rotation", "bases"):
        if k not in doc:
            raise InstanceError(f"实例参数表缺 {k!r} 段：{path}")
    bad = [a for a in doc["axes"] if a not in AXES]
    if bad:
        raise InstanceError(f"参数表里有未知维度 {bad}（本模块只认 {list(AXES)}）")
    return doc


def base_rows(spec: dict) -> dict[str, dict]:
    """出集参数表的 40 行，按 task_id 索引。**只读**，不改。"""
    rows = P.load_params(_REPO / spec["base_params"])
    by_id = {r["task_id"]: r for r in rows}
    missing = [t for t in spec["bases"] if t not in by_id]
    if missing:
        raise InstanceError(f"参数表列的基点在出集里不存在：{missing}")
    extra = [t for t in by_id if t not in spec["bases"]]
    if extra:
        raise InstanceError(f"出集有 {len(extra)} 行没在实例表里登记基点：{extra} —— "
                            f"漏登记的表现是「那道题一个实例都没有」，没有一处会报")
    return by_id


# ============================================================== 指纹

def base_value(axis: str, row: dict):
    """基点在这个维度上的现值 —— 指纹里「默认值」的定义就是它。"""
    if axis == "window":
        return {"start": row["window"]["start"], "end": row["window"]["end"]}
    if axis == "universe":
        return row["universe"]
    if axis == "factor_pool":
        return ((row.get("gold_args") or {}).get("factor_id"))
    raise InstanceError(f"未知维度 {axis!r}")


def normalize(params: dict, row: dict) -> dict:
    """规范化参数字典。四条规则见模块文档；**这个函数是指纹的唯一定义**。"""
    out: dict[str, str] = {}
    for axis in sorted(params):                     # ① 只收维度参数
        if axis not in AXES:
            raise InstanceError(f"参数字典里有未知维度 {axis!r}")
        v = params[axis]
        if v is None:
            continue
        if R.value_key(v) == R.value_key(base_value(axis, row)):
            continue                                # ② 等于基准 = 默认值，不进指纹
        out[axis] = R.value_key(v)                  # ③ 取值过 value_key
    return out


def fingerprint(params: dict, row: dict) -> str:
    blob = json.dumps(normalize(params, row), ensure_ascii=False,
                      sort_keys=True, separators=(",", ":"))    # ④
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:FINGERPRINT_LEN]


def make_instance_id(stage: str, template_id: str, base_task_id: str, fp: str) -> str:
    return f"{stage}/{template_id}@{base_task_id}#{fp}"


# ============================================================== 参数落到参数行

def check_phrasing(spec: dict, axis: str, stage: str, value, *, where: str) -> None:
    """这个取值会不会落进 declared？落进去就必须已有措辞。"""
    fld = (spec["axes"].get(axis, {}).get("declared_field") or {}).get(stage)
    if not fld:
        return                                   # 只改任务级字段（固定槽），措辞机器生成
    declared_value = _declared_value(axis, stage, value, spec)
    vk = R.value_key(declared_value)
    table = _phrasebook().get(fld) or {}
    if vk not in table:
        raise MissingPhrasing(fld, declared_value, vk, axis, where)
    arms = table[vk]
    missing = [c for c in R.PHRASEBOOK_COLUMNS if c not in arms]
    if missing:
        raise MissingPhrasing(fld, declared_value, vk, axis, f"{where}（缺列 {missing}）")


def _declared_value(axis: str, stage: str, value, spec: dict):
    """维度取值 → 它在 declared 里的形态。"""
    fld = (spec["axes"].get(axis, {}).get("declared_field") or {}).get(stage)
    if axis == "universe":
        if fld == "universe_ref":
            return f"{value}@{spec['as_of']}"
        return value
    if axis == "factor_pool":
        return [value] if fld == "input_factors" else value
    return value


def _rewrite_origin(origin: str, *, universe: str | None, factor: str | None) -> str:
    """夹具 origin 里的宇宙 / 因子 token 跟着实例走。认不出的形态**报错，不猜**。"""
    m = _ORIGIN_GOLD.match(origin)
    if m:
        uni = universe or m.group("uni")
        fid = factor or m.group("fid")
        return f"reference/gold_factors/{uni}/{fid}{m.group('meta') or ''}"
    m = _ORIGIN_S5.match(origin)
    if m:
        uni = universe or m.group("uni")
        fid = factor or m.group("fid")
        return f"{m.group('head')}{fid}{m.group('at')}{uni}{m.group('tail')}"
    if origin.startswith(_ORIGIN_NO_UNIVERSE):
        return origin
    raise InstanceError(f"不认识的 origin，不敢改写：{origin!r}")


def apply_params(row: dict, params: dict, spec: dict) -> dict:
    """把维度取值写进一份**新的**参数行（基点那份一个字节不动）。"""
    r = deepcopy(row)
    stage = r["stage"]
    win = params.get("window")
    uni = params.get("universe")
    fid = params.get("factor_pool")

    if win:
        r["window"] = {"start": win["start"], "end": win["end"]}
        # `inputs[].max_date` 跟到 window.end —— 出集 40 行现状就是这个恒等式（逐行核过），
        # 而它同时是 A1 要的两条（max_date ≤ as_of、end ≤ as_of）的最紧写法。
        for it in (r.get("inputs") or []):
            it["max_date"] = win["end"]
    if uni:
        r["universe"] = uni
        fld = (spec["axes"]["universe"].get("declared_field") or {}).get(stage)
        if fld:
            r["declared"] = dict(r["declared"])
            r["declared"][fld] = _declared_value("universe", stage, uni, spec)
    if fid:
        fld = (spec["axes"]["factor_pool"].get("declared_field") or {}).get(stage)
        if fld:
            r["declared"] = dict(r["declared"])
            r["declared"][fld] = _declared_value("factor_pool", stage, fid, spec)
        if r.get("gold_args") and "factor_id" in r["gold_args"]:
            r["gold_args"] = dict(r["gold_args"])
            r["gold_args"]["factor_id"] = fid
    if uni or fid:
        for it in (r.get("inputs") or []):
            it["origin"] = _rewrite_origin(str(it["origin"]), universe=uni, factor=fid)
    if params:
        # 夹具还没物化 —— sha 必须清空。留着基点的 sha 就是「这份夹具有身份」的假绿。
        for it in (r.get("inputs") or []):
            it["sha256"] = None
    return r


# ============================================================== 枚举

@dataclass
class Instance:
    base_task_id: str
    stage: str
    family: str
    template_id: str
    params: dict                       # 原始取值（未 value_key 化）
    norm: dict                         # 规范化后的（指纹的原料）
    fingerprint: str
    instance_id: str
    row: dict                          # 可直接喂 packager.build_task 的参数行
    task_id: str = ""
    is_base: bool = False
    fixtures: dict = field(default_factory=dict)     # 相对路径 → sha256


def _combos(spec: dict, stage: str, axes: list[str]) -> list[dict]:
    """适用维度的笛卡尔积，按**对角线序**排定。

    对角线序 = ``(max(下标), sum(下标), 下标元组)``，不是字典序。
    字典序会把「第一个维度取 0 号值」的组合全排在前面 —— 而 0 号值往往就是基点的现值，
    于是它在规范化时被剔掉，前若干个组合**全都不含第一个维度**。
    实测：S4 三个维度按字典序取前 3 个，17 个实例里只有 2 个换过窗口
    （窗口是第一个维度，它的 0 号值恰是基点窗口）。对角线序让每个维度轮流先动。
    """
    lists = []
    for a in axes:
        vals = (spec["values"].get(a) or {}).get(stage)
        if not vals:
            continue
        lists.append((a, list(vals)))
    out: list[tuple[tuple[int, ...], dict]] = [((), {})]
    for a, vals in lists:
        out = [((*idx, k), {**c, a: v}) for idx, c in out for k, v in enumerate(vals)]
    out.sort(key=lambda x: (max(x[0]) if x[0] else 0, sum(x[0]), x[0]))
    return [c for idx, c in out if any(idx)]


def enumerate_instances(spec: dict, rows: dict[str, dict] | None = None) -> list[Instance]:
    rows = rows if rows is not None else base_rows(spec)
    rot = spec["rotation"]
    k = int(rot["instances_per_base"])
    ex = rot.get("extra") or {}
    by_stage: dict[str, list[str]] = {}
    for tid in sorted(spec["bases"]):
        by_stage.setdefault(spec["bases"][tid]["stage"], []).append(tid)

    out: list[Instance] = []
    for stage in sorted(by_stage):
        bases = by_stage[stage]
        multi = [t for t in bases if len(spec["bases"][t]["axes"]) >= int(ex.get("when_axes_at_least", 99))]
        bonus = set(multi[:int(ex.get("n_bases", 0))])
        for ti, base_tid in enumerate(bases):
            b = spec["bases"][base_tid]
            row = rows[base_tid]
            want = k + (int(ex.get("n_extra_each", 0)) if base_tid in bonus else 0)
            combos = _combos(spec, stage, list(b["axes"]))
            picked: list[dict] = []
            seen: set[str] = set()
            n = len(combos)
            if n == 0:
                raise InstanceError(f"{base_tid} 一个可用组合都没有 —— 参数表给它列了维度却没有取值")
            j = 0
            # 从下标 ti 处开始取（轮换偏移 = 基点在本阶段内的序号；组合按对角线序排），
            # 跳过「规范化后为空」（整组等于基准）与已出现过的指纹。
            while len(picked) < want - 1 and j < n:
                c = combos[(ti + j) % n]
                j += 1
                nz = normalize(c, row)
                if not nz:
                    continue
                key = json.dumps(nz, sort_keys=True)
                if key in seen:
                    continue
                seen.add(key)
                picked.append(c)
            if len(picked) < want - 1:
                raise InstanceError(
                    f"{base_tid} 只凑得出 {len(picked)} 个与基准不同的组合，要 {want - 1} 个 —— "
                    f"给它的维度取值太少")
            for params in [{}] + picked:
                nz = normalize(params, row)
                fp = fingerprint(params, row)
                out.append(Instance(
                    base_task_id=base_tid, stage=stage, family=row["family"],
                    template_id=b["template_id"], params=params, norm=nz, fingerprint=fp,
                    instance_id=make_instance_id(stage, b["template_id"], base_tid, fp),
                    row=apply_params(row, params, spec), is_base=not params))
    allocate_task_ids(out, rows)
    dup = {i.instance_id for i in out if [x.instance_id for x in out].count(i.instance_id) > 1}
    if dup:
        raise InstanceError(f"实例 id 撞了：{sorted(dup)} —— 同 id 不同参数是最坏的一种漂")
    return out


def allocate_task_ids(instances: list[Instance], rows: dict[str, dict]) -> None:
    """**基点实例也发新号**（N-578，用户裁定 ③，2026-09-11），变体照旧。

    原来基准实例沿用基点自己的 `task_id`（`s8-cor-01` 还是 `s8-cor-01`）。代价在别处现形：
    `$GB/reference/tasks/` 下同时有 `v1.0-smoke/s8-cor-01` 与 `v1.0-instances/s8-cor-01`，
    而 `gateway/sim_factory.task_dir` 靠 glob 找题目录 —— 同号就是歧义，
    它按设计**当场 RuntimeError 不猜**，于是 **S8 四道题的 gold 一份都重算不出来**。
    「沿用基点号」省下的那点可读性，换掉的是一整个阶段的可复现性。

    **发号顺序刻意是「变体先、基点后」**：变体的编号因此**一个都不动**
    （`used` 仍由参数表里的基点号播种），只有 40 个基点实例拿到新号。
    重排会让已经发表过的实例 id 指向别的题，那比同号更坏。
    """
    used: dict[tuple[str, str], int] = {}
    for tid in rows:
        m = _TASK_ID_RE.match(tid)
        if m:
            key = (f"S{m.group(1)}", m.group(2))
            used[key] = max(used.get(key, 0), int(m.group(3)))

    def _issue(i: Instance) -> None:
        key = (i.stage, i.family.lower())
        used[key] = used.get(key, 0) + 1
        if used[key] > 99:
            raise InstanceError(f"{key} 的两位编号用光了（>99）")
        i.task_id = f"{i.stage.lower()}-{i.family.lower()}-{used[key]:02d}"
        i.row = {**i.row, "task_id": i.task_id, "set_id": "v1.0-instances",
                 "subject_id": f"{i.row['subject_id']}#{i.fingerprint}"}

    for i in sorted((x for x in instances if not x.is_base),
                    key=lambda x: (x.stage, x.family, x.template_id, x.fingerprint)):
        _issue(i)
    for i in sorted((x for x in instances if x.is_base),
                    key=lambda x: (x.stage, x.family, x.template_id, x.base_task_id)):
        _issue(i)


# ============================================================== 构建 / 校验

def build(inst: Instance, *, capabilities: dict | None = None):
    """过一遍 `packager.build_task`：E1–E15 / R1–R5 / C1 全套照查，**没有例外**。"""
    return P.build_task(inst.row, capabilities=capabilities or CAPS)


def validate_all(spec: dict, instances: list[Instance]) -> dict[str, list[str]]:
    """先查措辞，再逐实例 build。返回 `{instance_id: 问题列表}`（空 = 全绿）。"""
    red: dict[str, list[str]] = {}
    for i in instances:
        try:
            for axis, v in i.params.items():
                check_phrasing(spec, axis, i.stage, v, where=i.instance_id)
        except MissingPhrasing as e:
            red[i.instance_id] = [f"PHRASING {e}"]
            continue
        b = build(i)
        if not b.ok:
            red[i.instance_id] = list(b.problems)
    return red


def instruction_fingerprint(built) -> str:
    """单个实例的题面指纹：两臂文本抹掉 nonce 后各算 sha，再拼起来算一次。
    与 `ops/freeze_v10.py::instruction_fingerprint` 同一算法（那边是全集一次算完）。"""
    parts = []
    for arm in ("strict", "open"):
        txt = _NONCE_RE.sub("<NONCE>", getattr(built, arm).text)
        parts.append(f"{arm}\0{hashlib.sha256(txt.encode()).hexdigest()}\n")
    return hashlib.sha256("".join(parts).encode()).hexdigest()


# ============================================================== 夹具

def materialize(inst: Instance, built, *, set_root: Path | None = None) -> dict[str, str]:
    """按实例从 gold 面板导出夹具 —— **走 `reference/make_fixtures.py` 的入口**，不另写一份。

    窗口 / 宇宙 / 因子池已经写进 `task["window"] / task["universe"] / inputs[].origin`，
    `materialize()` 就是照着这三样切的，所以「按实例导出」不需要新参数。
    """
    from reference import make_fixtures as MF
    import genebench_config as cfg
    root = set_root or (cfg.GENEBENCH_ROOT / "reference" / "tasks" / "v1.0-instances")
    d = root / inst.task_id
    cfg.create_dir(d)
    placed, skipped = MF.materialize(d, built.task)
    if skipped:
        raise InstanceError(f"{inst.instance_id} 有跳过的夹具：{skipped}")
    inst.fixtures = dict(placed)
    return placed


#: `fixtures:` 段在参数表里的边界：`fixtures:` 那一行 + 随后所有**缩进行与空行**，
#: 到第一个顶格非空白字符为止。**顶格注释也是边界** —— 用「到下一个顶格键」当边界
#: 会把紧挨在下一个键上面的那几行说明注释一并吞掉。
_FIXTURES_HEAD = re.compile(r"^fixtures:[^\n]*\n(?:[ \t][^\n]*\n|[ \t]*\n)*", re.M)


def write_fixture_shas(instances: list[Instance], path: Path = SPEC) -> int:
    """把 `{instance_id: {rel: sha}}` 写回**参数表**（与 make_fixtures.write_params_shas 同纪律）。

    **只替换 `fixtures:` 那一段的文本，不整文件重 dump。**
    第一版用了 `yaml.safe_dump(doc)` —— 它把参数表里逐条写着「这个取值为什么可以用 /
    那个为什么不许用」的注释**全部抹掉**（13162 → 9395 字节，实测）。
    参数表的一多半价值就在那些注释里：没有它们，下一个人只看得到一堆日期和宇宙名，
    看不到「csi1000 为什么不在表里」。写回一个 sha 不该有这种代价。
    """
    doc = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    fx = dict(doc.get("fixtures") or {})
    n = 0
    for i in instances:
        if not i.fixtures:
            continue
        if fx.get(i.instance_id) != i.fixtures:
            fx[i.instance_id] = dict(sorted(i.fixtures.items()))
            n += 1
    if not n:
        return 0
    body = yaml.safe_dump({"fixtures": dict(sorted(fx.items()))},
                          allow_unicode=True, sort_keys=False, default_flow_style=False)
    text = Path(path).read_text(encoding="utf-8")
    if not _FIXTURES_HEAD.search(text):
        raise InstanceError(f"{path} 里找不到 `fixtures:` 段 —— "
                            f"不敢整文件重写：那会抹掉参数表的注释")
    text = _FIXTURES_HEAD.sub(lambda _m: body + "\n", text, count=1)
    Path(path).write_text(text, encoding="utf-8")
    Path(path).chmod(0o600)
    return n


def recorded_fixtures(spec: dict, inst: Instance) -> dict:
    return dict((spec.get("fixtures") or {}).get(inst.instance_id) or {})


# ============================================================== 冻结清单的 instances 段

NORMALIZATION_RULES: tuple[str, ...] = (
    "只收维度参数（window / universe / factor_pool）",
    "剔除等于基点现值的维度（不含默认值）—— 基准实例的参数字典是 {}",
    "取值过 genetask.render.value_key（与 phrasebook 取键同一个函数）",
    f"json.dumps(sort_keys=True, separators=(',',':'), ensure_ascii=False) 后 sha256，取前 {FINGERPRINT_LEN} 位",
)


def manifest_section(spec: dict | None = None, *, with_instruction_fingerprint: bool = True) -> dict:
    """冻结清单的 **instances** 段：模板（基点）与实例**两层**。

    每个实例记 ``id / 参数 / 题面指纹 / 夹具 sha``（卡 W3 第 5 条）。
    题面指纹是**渲染结果**的指纹（抹掉 nonce），夹具 sha 取参数表里记着的那份 ——
    夹具没物化过就是空 dict，而空 dict 与「记了一个假 sha」的区别正是这里要保住的。
    """
    spec = spec or load_spec()
    rows = base_rows(spec)
    insts = enumerate_instances(spec, rows)
    bases: dict[str, dict] = {}
    for i in insts:
        b = bases.setdefault(i.base_task_id, {
            "stage": i.stage, "family": i.family, "template_id": i.template_id,
            "template_key": f"{i.stage}/{i.template_id}",
            "axes": list(spec["bases"][i.base_task_id]["axes"]),
            "instances": []})
        entry = {"instance_id": i.instance_id, "task_id": i.task_id,
                 "fingerprint": i.fingerprint, "is_base": i.is_base,
                 "params": i.norm,
                 "window": i.row["window"], "universe": i.row["universe"],
                 "fixtures": recorded_fixtures(spec, i)}
        if with_instruction_fingerprint:
            entry["instruction_fingerprint"] = instruction_fingerprint(build(i))
        b["instances"].append(entry)
    for b in bases.values():
        b["instances"].sort(key=lambda x: (not x["is_base"], x["task_id"]))
    per_stage: dict[str, int] = {}
    for i in insts:
        per_stage[i.stage] = per_stage.get(i.stage, 0) + 1
    return {
        "set_id": spec["set_id"],
        "base_set_id": spec["base_set_id"],
        "spec_file": "genetask/params/v1.0-instances.yaml",
        "note": ("**两层**：基点（= 出集参数表的 40 行）→ 实例。"
                 "报告口径「40 模板 / N 实例」的 40 指的是参数表的 40 **行**；"
                 "模板目录只有 39 个，S1/source_status 被两行复用。"
                 "实例题面由 render_arm + 现有 phrasebook 生成，E1–E15 全过，**不重签**。"),
        "instance_id_rule": ("<stage>/<template_id>@<base_task_id>#<sha256(规范化参数)[:10]>"
                             " —— base_task_id 不可省：S1/source_status 被两行复用"),
        "normalization": list(NORMALIZATION_RULES),
        "task_id_rule": ("基准实例沿用基点 task_id；变体在 (stage, family) 内按 "
                         "(template_id, fingerprint) 排序，从该组最大编号 +1 顺序发号"),
        "counts": {"bases": len(bases), "instances": len(insts), "per_stage": dict(sorted(per_stage.items()))},
        "bases": dict(sorted(bases.items())),
    }


def instances_fingerprint(section: dict) -> str:
    """instances 段的指纹：逐实例 (instance_id, 题面指纹, 夹具 sha) 拼起来算一次。

    **它不进 `ROOT_FIELDS`**（本卡刻意不动根）：进了根，加一个实例就会让所有已发
    bundle 通行证作废，而实例与出集的 34 题不是一回事。要不要收进根由 Y1 定。
    """
    parts = []
    for tid, b in sorted(section["bases"].items()):
        for e in b["instances"]:
            fx = json.dumps(e.get("fixtures") or {}, sort_keys=True, separators=(",", ":"))
            parts.append(f"{tid}\0{e['instance_id']}\0{e.get('instruction_fingerprint','')}\0{fx}\n")
    return hashlib.sha256("".join(parts).encode()).hexdigest()


# ============================================================== CLI

def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description="参数轮换实例生成器（W3）")
    ap.add_argument("--list", action="store_true", help="逐实例一行")
    ap.add_argument("--build", action="store_true", help="全部过 build_task，红了非零退出")
    ap.add_argument("--manifest", action="store_true", help="打印冻结清单的 instances 段")
    ap.add_argument("--fixtures", action="store_true", help="按实例导出夹具（走 make_fixtures）")
    ap.add_argument("--stages", default="", help="只处理这些阶段（逗号分隔）")
    ap.add_argument("--write-shas", action="store_true", help="把夹具 sha 写回参数表")
    ap.add_argument("--no-fp", action="store_true", help="--manifest 时不算题面指纹（快）")
    a = ap.parse_args(argv)

    spec = load_spec()
    rows = base_rows(spec)
    insts = enumerate_instances(spec, rows)
    if a.stages:
        keep = {s.strip().upper() for s in a.stages.split(",") if s.strip()}
        insts = [i for i in insts if i.stage in keep]

    if a.list:
        for i in insts:
            print(f"{i.instance_id}  task_id={i.task_id}  base={i.base_task_id}  "
                  f"{'BASE' if i.is_base else '    '}  {json.dumps(i.norm, ensure_ascii=False)}")
        per: dict[str, int] = {}
        for i in insts:
            per[i.stage] = per.get(i.stage, 0) + 1
        print(json.dumps({"instances": len(insts), "per_stage": dict(sorted(per.items()))},
                         ensure_ascii=False))
        return 0
    if a.build:
        red = validate_all(spec, insts)
        print(json.dumps({"instances": len(insts), "red": len(red),
                          "detail": {k: v[:6] for k, v in list(red.items())[:20]}},
                         ensure_ascii=False, indent=1))
        return 1 if red else 0
    if a.fixtures:
        done = 0
        for i in insts:
            b = build(i)
            if not b.ok:
                raise InstanceError(f"{i.instance_id} build 红了，不出夹具：{b.problems[:4]}")
            if not (i.row.get("inputs") or []):
                continue
            materialize(i, b)
            done += 1
        n = write_fixture_shas(insts) if a.write_shas else 0
        print(json.dumps({"materialized": done, "shas_written": n}, ensure_ascii=False))
        return 0
    if a.manifest:
        sec = manifest_section(spec, with_instruction_fingerprint=not a.no_fp)
        sec["instances_fingerprint"] = instances_fingerprint(sec)
        print(json.dumps(sec, ensure_ascii=False, indent=1))
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
