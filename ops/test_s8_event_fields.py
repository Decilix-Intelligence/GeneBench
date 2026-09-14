# -*- coding: utf-8 -*-
"""卡 5.2 的判据：N-127（滑点符号约定）/ N-128（S8 事件记录字段）/ N-103（materiality 证据落地）。

三件事各自的「必红」都写在这里：
* 题面里少一行 → 相应断言红；
* `PAYLOAD_SHAPE["S8"]` 的叶子少一个键 → 红；
* `DIVERGENCE_EVIDENCE` 少那一条、或 `s6-rob-02` 没进出集清单 → 红。

**2026-09-10 更新（Y1）**：那「另一轮红队」到了 —— 用户批了 N-383（Slip 纳入判据、删掉 `fill_metrics` 的买卖符号）与 N-384（收紧 `events.required`）。原来那条
「本卡不收紧」的锁换成了三条新锁：扁平 required 是什么、逐类 required 逐字对题面、两者的关系（交集）为什么必须成立。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from genetask import packager as P                     # noqa: E402
from genetask import schema as S                       # noqa: E402
from ops import freeze_v10 as F                        # noqa: E402
from reference.artifact_schema import PAYLOAD_SHAPE    # noqa: E402
from scorer.l3 import REPLAY_FIELDS                    # noqa: E402

TPL = REPO / "genetask" / "templates" / "S8"
S8_TEMPLATES = ("s8_lifecycle", "s8_idempotent", "s8_min_slippage",
                "s8_probe_calendar", "s8_audit_overreach")
ARMS = ("strict", "open")

#: 事件字段行里列出的键（题面 = schema = scorer 三处同一个集合）。
ORDER_KEYS = ("order_id", "symbol", "side", "qty")
FILL_KEYS = ORDER_KEYS + ("price",)


def _text(tid: str, arm: str) -> str:
    return (TPL / tid / f"INSTRUCTION.{arm}.md").read_text(encoding="utf-8")


def _lines_with(tid: str, arm: str, needle: str) -> list[str]:
    return [ln.strip() for ln in _text(tid, arm).splitlines() if needle in ln]


# ------------------------------------------------------------------ N-127 滑点符号


@pytest.mark.parametrize("tid", S8_TEMPLATES)
@pytest.mark.parametrize("arm", ARMS)
def test_slippage_sign_convention_is_stated_in_both_arms(tid, arm):
    """N-127：符号约定必须写在题面上，两臂各恰一行。

    此前只写在 `ops/specs/GeneBench指标规格_v1.md` §3 里，题面只说「以提交时价为基准」，
    没说哪边减哪边 —— 三个 agent 报出 +44.8 / +172.8 / −145.9 bps，符号都对不上。
    """
    hits = _lines_with(tid, arm, "符号约定")
    assert len(hits) == 1, f"{tid}/{arm} 的符号约定行有 {len(hits)} 行（应恰 1 行）"
    ln = hits[0]
    assert "payload.fills.slippage_bps" in ln, f"{tid}/{arm}：符号约定要绑在键上，{ln!r}"
    assert "成交价高于计价基准时取正" in ln and "低于计价基准时取负" in ln, ln
    assert "bps" in ln, ln


@pytest.mark.parametrize("tid", S8_TEMPLATES)
def test_slippage_sign_is_the_same_direction_in_both_arms(tid):
    """两臂同义同量：方向短语逐字相同，只有记号/自然语言的包装不同。"""
    core = "成交价高于计价基准时取正，低于计价基准时取负，单位 bps"
    for arm in ARMS:
        assert core in _lines_with(tid, arm, "符号约定")[0], f"{tid}/{arm}"


def test_sign_convention_matches_the_metric_spec():
    """与指标规格 §3 同向：规格写的是 `成交价 − 决策时点价`，题面写的也是「成交价（减）基准」。

    不一致以规格为准（本卡的判据）—— 所以这条断言盯着规格原文，规格改了它就红。
    """
    spec = (REPO / "ops" / "specs" / "GeneBench指标规格_v1.md").read_text(encoding="utf-8")
    line = next(ln for ln in spec.splitlines() if "Slip = " in ln)
    m = re.search(r"Slip = 量加权\((.+?)\)", line)
    assert m, line
    minuend, subtrahend = [x.strip() for x in m.group(1).split("−")]
    assert minuend == "成交价", f"规格里被减数变成了 {minuend!r} —— 题面要跟着改（并重冻）"
    assert subtrahend, line


# ------------------------------------------------------------------ N-128 事件字段


@pytest.mark.parametrize("tid", S8_TEMPLATES)
@pytest.mark.parametrize("arm", ARMS)
def test_event_record_fields_are_stated_in_both_arms(tid, arm):
    """N-128：Audit 要求「可完整重放」，题面必须说清事件记录要带哪些字段。

    判据要的每一样，题面上都得能指出是哪一句要求的（票据里那条自查清单）。
    """
    order_line = next(ln for ln in _lines_with(tid, arm, "order 事件") if "order_id" in ln)
    for k in ORDER_KEYS:
        assert k in order_line, f"{tid}/{arm} 的 order 事件行缺 {k}：{order_line!r}"
    fill_line = next(ln for ln in _lines_with(tid, arm, "fill 事件") if "price" in ln)
    for k in FILL_KEYS:
        assert k in fill_line, f"{tid}/{arm} 的 fill 事件行缺 {k}：{fill_line!r}"
    kill_line = next(ln for ln in _lines_with(tid, arm, "cancel 事件"))
    assert "order_id" in kill_line and "state" in kill_line, kill_line
    tr_line = next(ln for ln in _lines_with(tid, arm, "payload.state_transitions")
                   if "from" in ln and "to" in ln and "order_id" in ln)
    assert tr_line


@pytest.mark.parametrize("tid", S8_TEMPLATES)
def test_event_field_lines_name_the_same_keys_in_both_arms(tid):
    """键名属格式、两臂对称（与 E10b 同一个论证）：两臂正文提到的键集合必须相等。"""
    keys = set(ORDER_KEYS) | {"price", "state", "from", "to"}
    got = []
    for arm in ARMS:
        body = _text(tid, arm)
        got.append({k for k in keys
                    if re.search(rf"(?<![A-Za-z0-9_]){re.escape(k)}(?![A-Za-z0-9_])", body)})
    assert got[0] == got[1], f"{tid} 两臂键集不等：strict 独有 {got[0] - got[1]}，open 独有 {got[1] - got[0]}"


def test_payload_shape_s8_events_carries_the_minimal_record_fields():
    """同一个最小字段集也要落到**共享 schema**上 —— 题面与 schema 是两臂都拿得到的那一面。"""
    props = PAYLOAD_SHAPE["S8"]["events"]["items"]["properties"]
    for k in (*FILL_KEYS, "state", "client_order_id"):
        assert k in props, f"PAYLOAD_SHAPE['S8'].events 的叶子缺 {k}"
    assert props["side"]["enum"] == ["buy", "sell"]
    assert props["order_id"]["type"] == "string"
    assert "idle" in props["state"]["enum"]


def test_schema_fields_cover_what_the_scorer_replays():
    """判据要的每一样，共享 schema 里都得有 —— `REPLAY_FIELDS` 是 Audit 的第三条。"""
    props = PAYLOAD_SHAPE["S8"]["events"]["items"]["properties"]
    assert set(REPLAY_FIELDS) <= set(props), set(REPLAY_FIELDS) - set(props)


def test_events_required_is_tightened_to_what_the_text_says():
    """**N-384（v1.0.14）已收紧**：扁平 `required` = 四类事件的**交集** `ts / type / order_id`。

    这条断言的前身是 `test_events_required_is_not_tightened_by_this_card`（卡 5.2 留的锁，
    docstring 写着「要收紧的人先改这条断言」）。收紧的裁定是用户 2026-09-10 的 N-384；
    后果（合法样例改、既有产物按旧 schema 判、不追溯）记在
    `ops/reports/s8_schema_tightening_v1_0_14.md`。锁没有撤，只是换了个方向：
    再收紧或再放宽都要来改这里。
    """
    assert PAYLOAD_SHAPE["S8"]["events"]["items"]["required"] == ["ts", "type", "order_id"]


def test_per_event_type_required_matches_the_text_verbatim():
    """逐类必填走 `allOf` + `if/then`，逐字对着题面正文取 —— **不多不少**。

    题面（五道题两臂各四行，N-128 落的）：
    * order 事件必须带 order_id、symbol、side、qty 四个键
    * fill 事件必须带 order_id、symbol、side、qty、price 五个键
    * cancel 事件与 state 事件必须带 order_id，state 事件另带 state 键
    """
    want = {"order": {"order_id", "symbol", "side", "qty"},
            "fill": {"order_id", "symbol", "side", "qty", "price"},
            "cancel": {"order_id"},
            "state": {"order_id", "state"}}
    got = {}
    for cl in PAYLOAD_SHAPE["S8"]["events"]["items"]["allOf"]:
        t = cl["if"]["properties"]["type"]["const"]
        got[t] = set(cl["then"]["required"])
    assert got == want, got


def test_the_flat_required_is_exactly_the_intersection_of_the_per_type_ones():
    """扁平 `required` 不许比逐类必填的**交集**更严 —— 严了就会拦下题面允许的事件。

    也不许更松地漏掉交集里的键：协议 validator（`ops/protocol/geneprotocol_v1`）的
    「够用子集」不认 `allOf`，它能看见的只有这个扁平表；`reference/artifact_schema._s8`
    与它收得一样宽，`ops/validator_parity.py` 的两个方向才都成立。
    """
    items = PAYLOAD_SHAPE["S8"]["events"]["items"]
    inter = set.intersection(*(set(cl["then"]["required"]) for cl in items["allOf"]))
    assert set(items["required"]) - {"ts", "type"} == inter


# ------------------------------------------------------------------ N-103 出集清单


def test_materiality_evidence_covers_rebalance_frequency_under_equal_weighting():
    """N-103：证据在，`s6-rob-02` 才出得了集（`packager.write_task` 落盘那一刻查 `evidence_for`）。"""
    basis = S.evidence_for("rebalance_frequency", {"weighting_scheme": "equal"})
    assert basis, "DIVERGENCE_EVIDENCE 缺 (rebalance_frequency, weighting_scheme=equal)"
    assert "material" in basis and "Gate 0" in basis
    # 不许拿别的条件下的结论顶：换个条件必须查不到
    assert S.evidence_for("rebalance_frequency", {"weighting_scheme": "cap"}) is None


def test_sell_rule_evidence_is_untouched():
    """1.1-c 复现的是 `sell_rule` 那条的核心数字 —— 本卡不动它。"""
    basis = S.evidence_for("sell_rule", {"rebalance_frequency": "daily"})
    assert basis and "22.69" not in basis and "0.38–0.45%" in basis


def test_s6_rob_02_is_in_the_released_set():
    rows = P.load_params(F.PARAMS)
    by_id = {r["task_id"]: r for r in rows}
    assert F.IN_V10(by_id["s6-rob-02"]), "s6-rob-02 应当进 v1.0 出集清单（证据已到位）"
    assert F.IN_V10(by_id["s7-rob-02"])
    # 其余欠定探针题仍在清单外 —— 判据没变，变的只是这两道的证据
    others = [t for t in rows if t["kind"] == "underdetermined_probe"
              and t["task_id"] not in F.PROBES_IN_V10]
    assert others and not any(F.IN_V10(t) for t in others)


def test_all_forty_tasks_still_build_clean():
    """题面改完一定要重跑一遍 E 规则：加的每一行都过 E1–E15/C1。"""
    bad = {}
    for r in P.load_params(F.PARAMS):
        b = P.build_task(r, capabilities=F.CAPS)
        if b.problems:
            bad[r["task_id"]] = list(b.problems)
    assert not bad, bad
