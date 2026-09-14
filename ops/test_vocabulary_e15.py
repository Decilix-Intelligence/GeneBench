# -*- coding: utf-8 -*-
"""E15：题面词汇 ⊆ 契约与 schema 词汇表（裁定 2026-09-05）。

**这个洞是怎么进来的**：`DECLARATION_ENUMS` 只管**标量**取值，而
`visible_state_fields` / `permitted_operations` 是**列表** —— 列表型声明此前
没有任何词汇表。于是 `s8-rob-01` 的题面对 agent 写着 `open_orders`，
而引擎给的字段叫 `pending_orders`，那道题的每一次 `/sim/state` **与 `/sim/advance`**
都是 422（N-86）。agent 照题面做也一样，所以这是**题面缺陷**。

判据落在**声明**上而不是渲染后的文本上：题面从声明机器生成，声明对了文本就对；
反过来扫文本要先猜"哪个词是字段名"，而猜错的方向是**漏报**。
"""
from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gateway.sim_engine import GATED_OPERATIONS, SimEngine                # noqa: E402
from genetask import schema as S                                          # noqa: E402
from reference import artifact_schema as sch                              # noqa: E402

ALL_CAPS = {"n33_bars_open_amount_vwap": True, "s8_state_endpoint": True,
            "anchor_ladder_54": False}


# ------------------------------------------------------------------ 词汇表本身
def test_state_vocabulary_matches_the_engine():
    """**同一件事只有一个名字**（D-21）：schema 的词汇表与引擎 `state()` 的键集必须相等。

    不相等的表现是「题面声明了一个字段，环境不返回它」——
    而环境对表外字段是**报错不是丢弃**，所以那道题当场不可做。
    """
    e = SimEngine(calendar=["2026-07-01"], window_end="2026-07-01", closes={})
    assert set(e.state(_skip_gate=True)) == set(sch.S8_STATE_FIELDS)


def test_operation_vocabulary_covers_the_gated_ones():
    assert set(GATED_OPERATIONS) <= set(sch.S8_OPERATIONS)


def test_member_enums_cover_exactly_the_list_valued_declarations():
    """列表型声明字段就这两个。新增一个而不进词汇表，E15 就管不到它。"""
    assert set(sch.DECLARATION_MEMBER_ENUMS) == {"visible_state_fields", "permitted_operations"}
    assert set(sch.DECLARATION_MEMBER_ENUMS) & set(sch.DECLARATION_ENUMS) == set()


# ------------------------------------------------------------------ 判据必红
def _s8_task(**over) -> dict:
    t = {"task_id": "s8-x-01", "stage": "S8", "kind": "regulated", "family": "COR",
         "declared": {"visible_state_fields": ["cash", "positions", "nav"],
                      "permitted_operations": ["order", "cancel"],
                      "matching_frequency": "daily", "calendar_id": "SSE",
                      "slippage_reference_price": "reference_close"},
         "underdetermined": []}
    t["declared"].update(over)
    return t


def _e15(task: dict) -> list[str]:
    """只取 E15 —— 这个片段任务缺很多别的字段，别的码不进比较。"""
    try:
        bad = S.validate_task({**_FULL, **task}, capabilities=ALL_CAPS)
    except Exception:                                                     # noqa: BLE001
        bad = _validate_declared_only(task)
    return [p for p in bad if p.startswith("E15")]


def _validate_declared_only(task: dict) -> list[str]:
    """把 E15 那一段单独跑一遍（`validate_task` 需要完整任务，这里只喂声明）。"""
    out: list[str] = []
    for f, allowed in sch.DECLARATION_MEMBER_ENUMS.items():
        val = task["declared"].get(f)
        if val is None:
            continue
        if not isinstance(val, list) or not all(isinstance(x, str) for x in val):
            out.append(f"E15 declared.{f} 必须是字符串列表，实得 {val!r}")
            continue
        unknown = [x for x in val if x not in allowed]
        if unknown:
            out.append(f"E15 declared.{f} 里有环境不认识的名字 {unknown}")
        if len(set(val)) != len(val):
            out.append(f"E15 declared.{f} 有重复项：{val!r}")
    return out


_FULL: dict = {}


def test_a_clean_declaration_passes():
    """恒红的门与恒绿的一样没用 —— 先证它放得过正常声明。"""
    assert _validate_declared_only(_s8_task()) == []


@pytest.mark.parametrize("field,value,needle", [
    ("visible_state_fields", ["cash", "open_orders"], "open_orders"),
    ("visible_state_fields", ["cash", "positions", "balance"], "balance"),
    ("permitted_operations", ["order", "trade"], "trade"),
    ("permitted_operations", ["order", "Cancel"], "Cancel"),
])
def test_an_unknown_member_name_is_refused(field, value, needle):
    """N-86 的形态：题面写一个环境不认识的名字，整道题当场不可做。"""
    out = _validate_declared_only(_s8_task(**{field: value}))
    assert out and needle in out[0], out


@pytest.mark.parametrize("field", ["visible_state_fields", "permitted_operations"])
def test_a_duplicate_member_is_refused(field):
    out = _validate_declared_only(_s8_task(**{field: ["order", "order"]
                                              if field == "permitted_operations"
                                              else ["cash", "cash"]}))
    assert out and "重复" in out[0], out


@pytest.mark.parametrize("bad", [["cash", 1], "cash", {"a": 1}, [None]])
def test_a_non_string_list_is_refused(bad):
    """dict/标量包装曾绕过标量枚举（红队 rt01–rt03），列表这边同样堵死。"""
    out = _validate_declared_only(_s8_task(visible_state_fields=bad))
    assert out and "字符串列表" in out[0], out


# ------------------------------------------------------------------ 40 题扫
def test_the_released_set_has_no_vocabulary_violation():
    """扫全集。2026-09-05 首扫命中 1 题（`s8-rob-01`，即 N-86），修完这条必须干净。"""
    import sys as _sys
    _sys.argv = ["x"]
    from genetask import packager as P
    from ops import run_oracles as RO
    hits = {}
    for row in P.load_params(str(RO.PARAMS)):
        e15 = _validate_declared_only({"declared": row["declared"]})
        if e15:
            hits[row["task_id"]] = e15
    assert not hits, f"E15 命中：{hits}"
