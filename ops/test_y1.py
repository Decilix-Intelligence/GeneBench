# -*- coding: utf-8 -*-
"""卡 Y1 的判据：N-383（Slip 符号统一 + 纳入判据）/ N-384（S8 events.required 收紧）/
两条根推到 v1.0.14 与 r1.0.21 / 实例两层清单落盘 / 六道欠定探针题仍然挂起。

每一条都写成「改回去就红」的形态 —— 断言不是装饰，是把裁定钉在盘上。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from ops import freeze_v10 as F                        # noqa: E402
from reference import artifact_samples as SAMP         # noqa: E402
from reference import artifact_schema as SCH           # noqa: E402
from reference import s8_oracle_common as S8OC         # noqa: E402
from scorer import l3                                  # noqa: E402

GB = Path("/data/shared/genebench")
GOLD_PRIVATE = GB / "reference" / "tasks" / "v1.0-smoke"
GOLD_PUBLIC = GB / "reference" / "tasks" / "public" / "v1.0-smoke-public"
S8_RELEASED = ("s8-cor-01", "s8-eco-01", "s8-ops-01", "s8-rob-01")

#: 两条通道重出的 gold（Y1 实跑，2026-09-10）。**逐位**记下来 ——
#: 「重出过了」这句话不带数字就无法被证伪。
GOLD_SLIP = {"s8-cor-01": 53.483047952181465,
             "s8-eco-01": -160.49252094287195,
             "s8-ops-01": 26.587585642703342,
             "s8-rob-01": -149.03126350733882}


# ------------------------------------------------------------------ N-383 符号

def test_fill_metrics_does_not_flip_sign_for_sells():
    """卖单不翻符号（以指标规格 §3 为准）。改回 `× sign` 这条就红。"""
    sell = {"o": {"symbol": "A", "side": "sell", "qty": 100, "reference_close": 10.0,
                  "filled": 100, "notional": 990.0}}
    buy = {"o": {"symbol": "A", "side": "buy", "qty": 100, "reference_close": 10.0,
                 "filled": 100, "notional": 990.0}}
    assert S8OC.fill_metrics(sell)["slippage_bps"] == pytest.approx(-100.0)
    # 同样的价、同样的基准 ⇒ 同样的数。买卖唯一的差别应当是**没有差别**。
    assert S8OC.fill_metrics(sell)["slippage_bps"] == \
        pytest.approx(S8OC.fill_metrics(buy)["slippage_bps"])


def test_the_word_sign_is_gone_from_fill_metrics():
    """源码级：`fill_metrics` 里不许再出现按 side 取的符号。

    数值断言挡不住「又乘回去但同时改了别处」的写法，所以再钉一次源码。
    """
    src = (REPO / "reference" / "s8_oracle_common.py").read_text(encoding="utf-8")
    body = src.split("def fill_metrics(")[1].split("\ndef ")[0]
    assert 'if o["side"] == "buy"' not in body, "fill_metrics 又按买卖翻符号了（N-383）"


def test_metric_spec_states_the_tolerance_conversion():
    """换算式必须写在**规格**里，不能只活在代码注释里（题面/规格是共享的那一面）。"""
    spec = (REPO / "ops" / "specs" / "GeneBench指标规格_v1.md").read_text(encoding="utf-8")
    assert "N-383" in spec
    assert "tol_bps(单 i) = 0.01 元 / 该单的计价基准(元) × 10000" in spec
    assert "不按方向翻符号" in spec


# ------------------------------------------------------------------ N-383 判据

def test_slip_is_judged_and_the_tolerance_is_one_tick():
    """一个最小价位之内算过，之外算不过。容差按**该单的计价基准**逐单换算。"""
    assert l3.MIN_TICK_CNY == 0.01
    ev = [{"ts": "t1", "type": "order", "order_id": "o1", "symbol": "A",
           "side": "buy", "qty": 100, "reference_close": 10.0},
          {"ts": "t2", "type": "fill", "order_id": "o1", "symbol": "A",
           "side": "buy", "qty": 100, "price": 10.1}]
    slip, tol, n = l3._slip_recompute(ev, "reference_close")
    assert n == 1
    assert slip == pytest.approx(100.0)
    assert tol == pytest.approx(10.0)          # 0.01 / 10.0 × 1e4

    def _judge(reported):
        p = {"events": ev,
             "state_transitions": [{"from": "idle", "to": "ordered", "order_id": "o1"},
                                   {"from": "ordered", "to": "filled", "order_id": "o1"}],
             "fills": {"fill_rate": 1.0, "slippage_bps": reported},
             "overreach": {"denied_requests": 0}}
        return l3.compare_fill(p, {}, declared={"slippage_reference_price": "reference_close"})

    assert _judge(100.0 + 9.9).correctness["SlipSelfConsistent"] == 1.0       # 容差内
    assert _judge(100.0 + 10.1).correctness["SlipSelfConsistent"] == 0.0      # 容差外
    # 高价标的的容差要小得多 —— 固定 bps 会对它过松
    ev2 = [dict(ev[0], reference_close=1720.0), dict(ev[1], price=1720.0)]
    _, tol2, _ = l3._slip_recompute(ev2, "reference_close")
    assert tol2 < 0.06 and tol2 == pytest.approx(0.01 / 1720.0 * 1e4)


def test_slip_is_not_compared_against_gold():
    """gold 的 Slip 只报出来供对照，**不进判据** —— 两轮不是同一个量的两次测量（N-114 同族）。"""
    ev = [{"ts": "t1", "type": "order", "order_id": "o1", "symbol": "A",
           "side": "buy", "qty": 100, "reference_close": 10.0},
          {"ts": "t2", "type": "fill", "order_id": "o1", "symbol": "A",
           "side": "buy", "qty": 100, "price": 10.1}]
    p = {"events": ev,
         "state_transitions": [{"from": "idle", "to": "ordered", "order_id": "o1"},
                               {"from": "ordered", "to": "filled", "order_id": "o1"}],
         "fills": {"fill_rate": 1.0, "slippage_bps": 100.0},
         "overreach": {"denied_requests": 0}}
    r = l3.compare_fill(p, {"fills": {"fill_rate": 0.1, "slippage_bps": -999.0}},
                        declared={"slippage_reference_price": "reference_close"})
    assert r.correctness["gold_slippage_bps"] == -999.0     # 报了
    assert r.score == 1.0 and r.l3_pass                     # 但没进判据


@pytest.mark.parametrize("base", ("close", "open", "unresolved", None))
def test_slip_is_unobservable_not_zero_when_the_basis_is_not_in_the_chain(base):
    """`close` / `open` 的基准是环境侧的价，事件链里没有 —— 记不可检，**不是判 0**。"""
    ev = [{"ts": "t1", "type": "order", "order_id": "o1", "symbol": "A",
           "side": "buy", "qty": 100, "reference_close": 10.0},
          {"ts": "t2", "type": "fill", "order_id": "o1", "symbol": "A",
           "side": "buy", "qty": 100, "price": 10.1}]
    p = {"events": ev,
         "state_transitions": [{"from": "idle", "to": "ordered", "order_id": "o1"},
                               {"from": "ordered", "to": "filled", "order_id": "o1"}],
         "fills": {"fill_rate": 1.0, "slippage_bps": 100.0},
         "overreach": {"denied_requests": 0}}
    r = l3.compare_fill(p, {}, declared={"slippage_reference_price": base} if base else {})
    assert "SlipSelfConsistent" not in r.correctness
    assert "SlipSelfConsistent" in r.skipped


# ------------------------------------------------------------------ N-383 gold

@pytest.mark.parametrize("tid", S8_RELEASED)
@pytest.mark.parametrize("root", (GOLD_PRIVATE, GOLD_PUBLIC), ids=("private", "public"))
def test_regenerated_gold_matches_the_new_sign_convention(tid, root):
    """两条通道的 gold 都按新口径重出过，且**逐位相同**。

    gold 落在数据面（`$GB/reference/`），不在仓库里 —— 没有它就跳过，
    但**有它就必须对得上**：这条不许因为「机器上没有」而变成永远不跑。
    """
    f = root / tid / "gold" / "oracle_artifact.json"
    if not f.is_file():
        pytest.skip(f"gold 不在这台机上：{f}")
    got = json.loads(f.read_text(encoding="utf-8"))["payload"]["fills"]["slippage_bps"]
    assert got == pytest.approx(GOLD_SLIP[tid], rel=1e-12)


@pytest.mark.parametrize("tid", S8_RELEASED)
def test_gold_is_self_consistent_under_the_new_slip_criterion(tid):
    """gold 自己要过新判据 —— oracle 过不了自己的判据的话，判据就是错的。"""
    f = GOLD_PRIVATE / tid / "gold" / "oracle_artifact.json"
    if not f.is_file():
        pytest.skip(f"gold 不在这台机上：{f}")
    art = json.loads(f.read_text(encoding="utf-8"))
    r = l3.compare_fill(art["payload"], art["payload"],
                        declared=art["declarations"])
    assert r.correctness.get("SlipSelfConsistent") == 1.0, r.correctness
    assert r.correctness.get("Audit") == 1.0, r.correctness


# ------------------------------------------------------------------ N-384

def test_events_required_is_the_intersection_of_the_per_type_requirements():
    items = SCH.PAYLOAD_SHAPE["S8"]["events"]["items"]
    assert items["required"] == ["ts", "type", "order_id"]
    per = {c["if"]["properties"]["type"]["const"]: set(c["then"]["required"])
           for c in items["allOf"]}
    assert per == {"order": {"order_id", "symbol", "side", "qty"},
                   "fill": {"order_id", "symbol", "side", "qty", "price"},
                   "cancel": {"order_id"},
                   "state": {"order_id", "state"}}
    assert set(items["required"]) - {"ts", "type"} == set.intersection(*per.values())


def test_the_scorer_is_exactly_as_strict_as_the_protocol_validator_can_be():
    """`_s8` 只收到 `order_id`。

    协议 validator 的「够用子集」不认 `allOf`，所以它只拦得到扁平 `required`。
    评分器比它严 ⟹ `ops/validator_parity.py` 的「作用域内 scorer 报 ⟹ validator 也必须报」断；
    评分器比它松 ⟹ 另一个方向断。两边必须一样宽。
    """
    import copy

    def _codes(ev):
        smp = SAMP.s8()
        art = copy.deepcopy(smp.artifact)
        art["payload"]["events"] = ev
        return SCH.validate(art, task=smp.task).codes

    ok = [{"ts": "2026-09-01T12:00:00Z", "type": "order", "order_id": "o1"}]
    assert "s8_event_malformed" not in _codes(ok), \
        "order 事件缺 symbol/side/qty **不该**在 L1 判 —— 那一层归 L3 的 Audit"
    for bad in ({"ts": "2026-09-01T12:00:00Z", "type": "order"},
                {"ts": "2026-09-01T12:00:00Z", "type": "order", "order_id": ""},
                {"ts": "2026-09-01T12:00:00Z", "type": "order", "order_id": 7}):
        assert "s8_event_malformed" in _codes([bad]), bad


def test_the_legal_sample_carries_the_tightened_fields():
    ev = SAMP.s8().artifact["payload"]["events"]
    assert all(e.get("order_id") for e in ev)
    order = next(e for e in ev if e["type"] == "order")
    assert {"symbol", "side", "qty"} <= set(order)
    assert "reference_close" in order, "样例要带基准价，否则没有一份合法样例能演示 Slip 判得动"
    fill = next(e for e in ev if e["type"] == "fill")
    assert {"symbol", "side", "qty", "price"} <= set(fill)


def test_the_emitted_schema_and_the_client_copy_agree():
    spec = json.loads((REPO / "ops" / "specs" / "artifact_schema" / "v1.0" / "S8.json")
                      .read_text(encoding="utf-8"))
    assert spec == SCH.json_schema("S8")
    sys.path.insert(0, str(REPO / "integrations" / "genebench_client" / "src"))
    from genebench_client.emit_schemas import SCHEMAS   # noqa: PLC0415
    assert SCHEMAS["S8"] == spec


def test_the_output_format_slot_now_names_order_id():
    """题面为什么跟着变：`fixed:output_format` 是**机器从 required 生成**的。

    这条同时说明「题面正文一个字没手改」也可以让题面指纹变 —— 收紧 schema 就够了。
    """
    from genetask import packager as P                  # noqa: PLC0415
    rows = {r["task_id"]: r for r in P.load_params(F.PARAMS)}
    b = P.build_task(rows["s8-cor-01"], capabilities=F.CAPS)
    for arm in (b.strict, b.open):
        slot = arm.phrases["fixed:output_format"]
        assert "events 含 ts, type, order_id" in slot, slot


# ------------------------------------------------------------------ 两条根

def test_both_axes_were_bumped_and_recorded():
    """**改写于 2026-09-10（卡 A）**：原来把两个版本号写死成 `1.0.14` / `r1.0.21`，
    于是每重冻一次就得回来改一次 —— 而「改一个常量让测试变绿」是这条断言最不该教人做的事。

    换成两条不写死号的不变量：① 代码里的版本常量与**盘上清单**一致
    （抓「推了号没重冻」与「重冻了没推号」）；② 记因表的最后两条**就是**当前这两个号
    （抓「重冻了没记因」）。历史条目的逐字检查照旧保留 —— 它抓的是另一件事：
    有人重排或删掉旧记因。
    """
    m = json.loads((REPO / "ops" / "manifests" / "v1.0-smoke.json").read_text(encoding="utf-8"))
    r = json.loads((REPO / "ops" / "manifests" / "v1.0-smoke.reference.json")
                   .read_text(encoding="utf-8"))
    assert F.SET_VERSION == m["set_version"], "代码里的任务集版本与盘上清单不一致 —— 推了号没重冻？"
    assert F.REFERENCE_VERSION == r["reference_version"], "参考版本与盘上清单不一致"
    # **两条轴各看各的表**（N-573 收口后，2026-09-11）：任务集记因回到 `REVISIONS`，
    # `REFERENCE_REVISIONS` 只剩带 `r` 前缀的。原来那条在一张表里取最后两条 ——
    # 它成立的前提正是「任务集记因写错了地方」这件事本身。
    assert F.REVISIONS[-1]["version"] == F.SET_VERSION, \
        f"REVISIONS 最后一条 {F.REVISIONS[-1]['version']} 不是当前任务集号 —— 重冻了没记因？"
    assert F.REFERENCE_REVISIONS[-1]["version"] == F.REFERENCE_VERSION, \
        f"REFERENCE_REVISIONS 最后一条 {F.REFERENCE_REVISIONS[-1]['version']} 不是当前参考号"
    for v, needles in (("1.0.14", ("N-384", "N-383", "order_id", "不追溯")),
                       ("r1.0.21", ("N-383", "s8-cor-01", "53.483048", "−202.514311")),
                       # 卡 A 的两条：各自钉住**这次为什么不可比**里最关键的那个事实
                       ("1.0.15", ("N-484", "MANIFEST.sha256", "instances_fingerprint",
                                   "s8_contract", "题面逐字不变")),
                       ("r1.0.22", ("N-543", "N-518", "unresolved", "13 个百分点",
                                    "holdout_rule", "逐字节相同"))):
        e = next(r for r in list(F.REVISIONS) + list(F.REFERENCE_REVISIONS)
                 if r["version"] == v)
        for k in ("why", "what", "scope", "gates"):
            assert e.get(k), f"{v} 的记因缺 {k}"
        blob = json.dumps(e, ensure_ascii=False)
        for n in needles:
            assert n in blob, f"{v} 的记因里没写 {n}"


def test_the_frozen_manifest_is_on_disk_and_consistent():
    m = json.loads((REPO / "ops" / "manifests" / "v1.0-smoke.json").read_text(encoding="utf-8"))
    assert m["set_version"] == F.SET_VERSION      # 写死号的那一版每重冻一次就得改一次（卡 A）
    assert m["root"] == F.manifest_root(m), "清单自记的根与现算的不一致"
    r = json.loads((REPO / "ops" / "manifests" / "v1.0-smoke.reference.json")
                   .read_text(encoding="utf-8"))
    assert r["reference_version"] == F.REFERENCE_VERSION
    # 参考清单**不自记根**（`reference_root()` 现算），两条轴的根必须是两个不同的数
    assert m["root"] != F.reference_root(r)


# ------------------------------------------------------------------ 实例两层清单

def test_the_instances_section_is_in_the_manifest_and_its_fingerprint_is_in_the_root():
    """**2026-09-10 翻转**（用户裁定 ⑤，卡 A）：原注写「不进根：加一个实例不许作废任何已发通行证」。
    现在反过来 —— **实例表一动就作废所有已发通行证**，这是自愿付的价，
    换根重新答得出「这一次被测方拿到的是哪一批题」。整段 `instances` 仍不进根（进的是指纹）。"""
    m = json.loads((REPO / "ops" / "manifests" / "v1.0-smoke.json").read_text(encoding="utf-8"))
    assert m["instances"]["counts"]["instances"] == 130
    assert m["instances"]["counts"]["bases"] == 40
    assert len(m["instances_fingerprint"]) == 64
    assert "instances_fingerprint" in F.ROOT_FIELDS and "instances" not in F.ROOT_FIELDS
    assert m["root_scope"]["root_fields"] == list(F.ROOT_FIELDS), \
        "清单里记的覆盖面与代码不一致 —— 事后比两个 root 的人会以为是题面变了"


def test_the_instance_fixtures_are_recorded_honestly():
    """夹具物化了多少就记多少 —— S6 的 15 个出不来（见 ops/tickets_inbox/Y1.md），记空字典。"""
    m = json.loads((REPO / "ops" / "manifests" / "v1.0-smoke.json").read_text(encoding="utf-8"))
    bases = m["instances"]["bases"]
    assert len(bases) == 40
    by_stage: dict[str, list] = {}
    for b in bases.values():
        for it in b["instances"]:
            by_stage.setdefault(b["stage"], []).append(it)
    assert sum(len(v) for v in by_stage.values()) == 130
    assert all(not it.get("fixtures") for it in by_stage["S6"]), \
        "S6 的实例夹具其实出不来（s6_consumer_window 先有鸡还是先有蛋）—— 不许记成有"
    # 反面：物化过的那几个阶段必须**真的**记着 sha，否则这条断言就退化成「全都记空」也能过
    assert any(it.get("fixtures") for it in by_stage["S4"]), "S4 的实例夹具应当已物化并记了 sha"


# ------------------------------------------------------------------ 六道欠定探针题

def test_no_probe_was_released_by_this_card():
    """出集维持 34 题 / 挂起 6 题；`DIVERGENCE_EVIDENCE` 一个字未加。"""
    from genetask import packager as P                  # noqa: PLC0415
    rows = P.load_params(F.PARAMS)
    assert F.PROBES_IN_V10 == frozenset({"s7-rob-02", "s6-rob-02"})
    assert sum(1 for t in rows if F.IN_V10(t)) == 34
    others = [t for t in rows if t["kind"] == "underdetermined_probe"
              and t["task_id"] not in F.PROBES_IN_V10]
    assert len(others) == 6 and not any(F.IN_V10(t) for t in others)


def test_the_report_says_slip_being_judged_does_not_unlock_s8_rob_02():
    """W3 §9 写着「Slip 纳入判据之后 s8-rob-02 才有量得到的可能」—— 纳入了，仍然量不到。

    这条断言存在的理由：下一个读到那句话的人很容易把它读成「现在可以放出了」。
    """
    doc = (REPO / "ops" / "reports" / "s8_schema_tightening_v1_0_14.md").read_text(encoding="utf-8")
    assert "s8-rob-02" in doc
    assert "仍然量不到" in doc
