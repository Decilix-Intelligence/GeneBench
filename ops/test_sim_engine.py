"""卡 4.4 第一轮：契约的**可测部分** —— 状态机迁移表 + 每条迁移一正一反 + 撮合/幂等/Slip。

端点（`/sim/*` 五条）本身的验收在 `ops/test_sim_endpoints.py`（2026-09-04 落地）。
本文件把语义压在**纯引擎**上 —— 这样契约的对错不必等端点上线才验，
端点上线后这批测试也不需要起服务就能跑。
仍挂起的只剩 SIM-N（要在 f02 从任务容器真打一次），在 `PENDING_ENDPOINT_ITEMS` 里显式列着。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from gateway.sim_engine import (CONTRACT_DEFAULT_SLIPPAGE_BASE, LEGAL_TRANSITIONS,  # noqa: E402
                                GATED_OPERATIONS, SLIPPAGE_BASES, SimEngine, SimError,
                                TRADABILITY_STATES, UNTRADABLE_STATES, V1_UNREACHABLE)
from reference import artifact_schema as sch                                        # noqa: E402

#: 需要端点/网关起停的验收条目 —— 这一轮不做，**显式挂着**
#: 仍然挂起的端点侧验收。**A/B/E/H 已于 2026-09-04 落地**
#: （`ops/test_sim_endpoints.py`，19 条），只剩 N —— 它要在 f02 上起服务、
#: 从任务容器真打一次，A 档跑不了。
PENDING_ENDPOINT_ITEMS = {
    "SIM-N": "从 f02 任务容器经既有白名单能打到 /sim/state",
}

CAL = ["2026-07-01", "2026-07-02", "2026-07-03", "2026-07-06"]
SYM = "600000.SH"


def eng(**kw) -> SimEngine:
    closes = {(d, SYM): 10.0 + i for i, d in enumerate(CAL)}
    opens = {(d, SYM): 9.5 + i for i, d in enumerate(CAL)}
    kw.setdefault("closes", closes)
    kw.setdefault("opens", opens)
    return SimEngine(calendar=list(CAL), window_end=CAL[-1], **kw)


# --------------------------------------------------------------- 迁移表：不重抄

def test_transition_table_is_the_shared_constant_not_a_copy():
    """实现里的迁移表必须**引用** reference 的常量。抄第二份，两份会漂，
    而漂的表现是「校验器说合法、环境说非法」或者反过来 —— 两边都不报错。"""
    from gateway import sim_engine
    assert sim_engine.LEGAL_TRANSITIONS is sch.LEGAL_TRANSITIONS, \
        "不是同一个对象 —— 说明抄了一份"


def test_v1_never_produces_partial():
    assert V1_UNREACHABLE == {"partial"}
    assert ("ordered", "partial") in LEGAL_TRANSITIONS, "表里有，v1 不走 —— 两件事"


# --------------------------------------------------------------- 每条合法迁移：一正一反

def _drive(kind: str) -> SimEngine:
    """把引擎开到会产生指定迁移的位置。"""
    e = eng()
    if kind == "idle->ordered":
        e.submit(symbol=SYM, side="buy", qty=100, client_order_id="c1", reference_close=10.0)
    elif kind == "ordered->filled":
        e.submit(symbol=SYM, side="buy", qty=100, client_order_id="c1", reference_close=10.0)
        e.advance()
    elif kind == "ordered->cancelled":
        e.submit(symbol=SYM, side="buy", qty=100, client_order_id="c1", reference_close=10.0)
        e.cancel("o000001")
    elif kind == "filled->idle":
        e.submit(symbol=SYM, side="buy", qty=100, client_order_id="c1", reference_close=10.0)
        e.advance()
    elif kind == "cancelled->idle":
        e.submit(symbol=SYM, side="buy", qty=100, client_order_id="c1", reference_close=10.0)
        e.cancel("o000001")
    return e


@pytest.mark.parametrize("pair", sorted(LEGAL_TRANSITIONS - {("ordered", "partial"),
                                                             ("partial", "filled"),
                                                             ("partial", "cancelled")}))
def test_each_legal_transition_has_a_positive_case(pair):
    """**正例**：v1 会走到的每条迁移都要真的发生过一次。"""
    kind = f"{pair[0]}->{pair[1]}"
    e = _drive(kind)
    assert pair in e.transitions_seen(), f"{kind} 从没发生过 —— 这条迁移是死的"


@pytest.mark.parametrize("pair", sorted(
    {(a, b) for a in ("idle", "ordered", "filled", "cancelled")
     for b in ("idle", "ordered", "filled", "cancelled")} - set(LEGAL_TRANSITIONS)))
def test_each_illegal_transition_is_refused(pair):
    """**反例**：不在表里的迁移必须被 `_transition` 顶回去，且是 409 而不是静默。"""
    e = eng()
    e.submit(symbol=SYM, side="buy", qty=100, client_order_id="c1", reference_close=10.0)
    o = e.orders["o000001"]
    o.state = pair[0]
    with pytest.raises(SimError) as ei:
        e._transition(o, pair[1])
    assert ei.value.code in ("illegal_transition", "v1_unreachable_state")
    assert o.state == pair[0], "被拒的迁移不得留下副作用"


def test_run_transitions_are_subset_of_legal():
    e = eng()
    e.submit(symbol=SYM, side="buy", qty=100, client_order_id="c1", reference_close=10.0)
    e.submit(symbol=SYM, side="buy", qty=200, client_order_id="c2", reference_close=10.0)
    e.cancel("o000002")
    e.advance()
    assert e.transitions_seen() <= set(LEGAL_TRANSITIONS)
    assert "partial" not in {s for pair in e.transitions_seen() for s in pair}


# --------------------------------------------------------------- SIM-C/D：单调单步 + 审计

def test_sim_c_advance_is_single_step_and_takes_no_date():
    e = eng()
    d0 = e.sim_date
    e.advance()
    assert e.sim_date == CAL[1], "一次推进恰好一个交易日"
    assert e.sim_date > d0
    import inspect
    sig = inspect.signature(SimEngine.advance)
    # 判据是「不接受**目标日期/步数**」，不是「不接受任何参数」——
    # 写成后者的话，加一个可见性投影参数就会误伤（2026-09-04 实际发生了）。
    forbidden = ("date", "to", "target", "until", "days", "steps")
    got = [x for x in sig.parameters if x != "self"]
    assert not [x for x in got if any(f in x.lower() for f in forbidden)], \
        f"advance 不得接受目标日期/步数参数，实际 {got}"


def test_sim_d_advance_emits_one_event_with_both_dates():
    e = eng()
    before = len(e.log)
    e.advance()
    adv = [x for x in e.log[before:] if x["type"] == "advance"]
    assert len(adv) == 1
    assert adv[0]["payload"]["from"] == CAL[0] and adv[0]["payload"]["to"] == CAL[1]


def test_sim_l_window_exhausted_is_409():
    e = eng()
    for _ in range(len(CAL) - 1):
        e.advance()
    with pytest.raises(SimError) as ei:
        e.advance()
    assert ei.value.status == 409 and ei.value.code == "window_exhausted"


# --------------------------------------------------------------- SIM-J：幂等

def test_sim_j_order_is_idempotent_by_client_order_id():
    e = eng()
    a = e.submit(symbol=SYM, side="buy", qty=100, client_order_id="c1", reference_close=10.0)
    n_order_events = sum(1 for x in e.log if x["type"] == "order")
    b = e.submit(symbol=SYM, side="buy", qty=100, client_order_id="c1", reference_close=10.0)
    assert a["order_id"] == b["order_id"]
    assert sum(1 for x in e.log if x["type"] == "order") == n_order_events, \
        "重复提交不得产生第二条 order 事件（s8-rob-01 测的就是这条）"


def test_sim_j_advance_is_deliberately_not_idempotent():
    e = eng()
    e.advance(); e.advance()
    assert e.sim_date == CAL[2], "推进两次前进两天 —— **不幂等**是它的正确行为"


def test_cancel_is_idempotent():
    e = eng()
    e.submit(symbol=SYM, side="buy", qty=100, client_order_id="c1", reference_close=10.0)
    assert e.cancel("o000001")["status"] == "cancelled"
    assert e.cancel("o000001")["status"] == "cancelled"
    assert e.cancel("nope")["status"] == "not_found"


# --------------------------------------------------------------- SIM-F：Slip 随声明改变

def test_sim_f_slippage_basis_changes_the_number():
    got = {}
    for base in SLIPPAGE_BASES:
        e = eng(slippage_reference_price=base)
        e.submit(symbol=SYM, side="buy", qty=100, client_order_id="c1", reference_close=10.0)
        e.advance()
        got[base] = round(e.slippage_bps()["slippage_bps"], 6)
    assert got["close"] == 0.0, \
        ("close 档 Slip **结构性为零** —— v1 成交就是下一交易日收盘，成交价 ≡ 基准价。"
         "这不是 bug，是该取值的真实后果，实现不许为了让指标好看改成别的价")
    assert len(set(got.values())) == 3, f"三档必须互不相同，实际 {got}"


def test_slippage_default_is_recorded_as_default():
    """题面没声明时按契约默认跑，但产物要**如实记下用的是默认** ——
    不许让「默认」看起来像「agent 选的」。"""
    e = eng()
    assert e.slippage_reference_price is None
    s = e.slippage_bps()
    assert s["basis"] == CONTRACT_DEFAULT_SLIPPAGE_BASE
    assert s["used_contract_default"] is True
    e2 = eng(slippage_reference_price=CONTRACT_DEFAULT_SLIPPAGE_BASE)
    assert e2.slippage_bps()["used_contract_default"] is False, \
        "显式声明成默认值 ≠ 用了默认 —— 两件事，产物里要分得开"


def test_slippage_enum_matches_schema():
    assert set(SLIPPAGE_BASES) == set(sch.DECLARATION_ENUMS["slippage_reference_price"]), \
        "枚举与 schema 漂了"


# --------------------------------------------------------------- SIM-G：pending 只读

def test_sim_g_pending_orders_is_read_only_projection():
    e = eng()
    e.submit(symbol=SYM, side="buy", qty=100, client_order_id="c1", reference_close=10.0)
    st = e.state()
    assert [o["order_id"] for o in st["pending_orders"]] == ["o000001"]
    st["pending_orders"].clear()                       # 改投影
    assert len(e.state()["pending_orders"]) == 1, "投影是拷贝，改它不得影响引擎"
    e.cancel("o000001")
    assert e.state()["pending_orders"] == [], "撤单只经 /sim/cancel 生效"


def test_visible_state_fields_are_omitted_not_nulled():
    e = eng()
    st = e.state(visible=("sim_date", "cash"))
    assert set(st) == {"sim_date", "cash"}, "未声明的字段**不返回**，不是返回 null（契约 §2）"


# --------------------------------------------------------------- 越权

@pytest.mark.parametrize("op", sorted(GATED_OPERATIONS))
def test_gated_operations_go_through_the_permission_gate(op):
    perms = tuple(x for x in sorted(GATED_OPERATIONS) if x != op)
    e = eng(permitted_operations=perms)
    if op != "order":
        e.submit(symbol=SYM, side="buy", qty=100, client_order_id="c1", reference_close=10.0)
    call = {"order": lambda: e.submit(symbol=SYM, side="buy", qty=100,
                                      client_order_id="c9", reference_close=10.0),
            "cancel": lambda: e.cancel("o000001")}[op]
    with pytest.raises(SimError) as ei:
        call()
    assert ei.value.status == 403 and ei.value.code == "operation_not_permitted"


@pytest.mark.parametrize("op", ["advance", "state", "log"])
def test_environment_operations_are_not_gated(op):
    """环境操作不受 permitted_operations 管 —— 全部 5 道 S8 题都没声明它们，
    闸住 = 上线即整阶段 403。契约冲突记在 GATED_OPERATIONS 处，待裁定。"""
    e = eng(permitted_operations=("order",))
    {"advance": e.advance, "state": e.state, "log": e.audit_log}[op]()


# --------------------------------------------------------------- 撮合与拒绝

def test_fill_happens_on_next_trading_day_close():
    e = eng()
    e.submit(symbol=SYM, side="buy", qty=100, client_order_id="c1", reference_close=10.0)
    assert e.orders["o000001"].filled_price is None, "提交当日不成交"
    r = e.advance()
    assert r["fills"][0]["price"] == 11.0 and r["fills"][0]["date"] == CAL[1]


@pytest.mark.parametrize("st", sorted(UNTRADABLE_STATES))
def test_untradable_status_becomes_zero_fill_with_reject_event(st):
    e = eng(tradable={(CAL[1], SYM): st})
    e.submit(symbol=SYM, side="buy", qty=100, client_order_id="c1", reference_close=10.0)
    r = e.advance()
    assert r["fills"] == []
    assert [x["payload"]["reason"] for x in e.log if x["type"] == "reject"] == [st]


@pytest.mark.parametrize("bad", ["ok", "limit_up", "delisted", "", "TRADE", None])
def test_unknown_tradability_status_fails_closed(bad):
    """**不认识的状态必须拒单**。原先写成「在我列的黑名单里才拒」，而那张黑名单里
    有四个取值根本不存在（ok/limit_up/limit_down/delisted）—— 整条拦截从没生效过。"""
    e = eng(tradable={(CAL[1], SYM): bad})
    e.submit(symbol=SYM, side="buy", qty=100, client_order_id="c1", reference_close=10.0)
    assert e.advance()["fills"] == [], f"未知状态 {bad!r} 必须 fail-closed"
    assert any(str(x["payload"]["reason"]).startswith("unknown_tradability")
               for x in e.log if x["type"] == "reject")


def test_tradability_vocabulary_is_the_shared_constant():
    from gateway import sim_engine
    assert sim_engine.TRADABILITY_STATES is sch.TRADABILITY_STATES, "抄了一份就会漂"
    assert "trade" in sch.TRADABILITY_STATES and "ok" not in sch.TRADABILITY_STATES


def test_limit_up_blocks_buy_but_not_sell():
    """涨跌停是**独立字段**，不是 status 的取值；方向必须参与判断。"""
    e = eng(limit_up={(CAL[1], SYM)})
    e.positions[SYM] = {"shares": 100, "avg_cost": 10.0}
    e.submit(symbol=SYM, side="sell", qty=100, client_order_id="c1", reference_close=10.0)
    assert len(e.advance()["fills"]) == 1, "涨停不该拦卖单"
    e2 = eng(limit_up={(CAL[1], SYM)})
    e2.submit(symbol=SYM, side="buy", qty=100, client_order_id="c1", reference_close=10.0)
    assert e2.advance()["fills"] == [], "涨停必须拦买单"
    assert [x["payload"]["reason"] for x in e2.log if x["type"] == "reject"] == ["limit_up"]


def test_limit_down_blocks_sell_but_not_buy():
    e = eng(limit_down={(CAL[1], SYM)})
    e.positions[SYM] = {"shares": 100, "avg_cost": 10.0}
    e.submit(symbol=SYM, side="sell", qty=100, client_order_id="c1", reference_close=10.0)
    assert e.advance()["fills"] == [], "跌停必须拦卖单"
    e2 = eng(limit_down={(CAL[1], SYM)})
    e2.submit(symbol=SYM, side="buy", qty=100, client_order_id="c1", reference_close=10.0)
    assert len(e2.advance()["fills"]) == 1, "跌停不该拦买单"


# --------------------------------------------------------------- SIM-K：审计可重放

def test_sim_k_log_replay_reaches_the_same_terminal_state():
    e = eng()
    e.submit(symbol=SYM, side="buy", qty=200, client_order_id="c1", reference_close=10.0)
    e.submit(symbol=SYM, side="buy", qty=100, client_order_id="c2", reference_close=10.0)
    e.cancel("o000002")
    e.advance()
    e.advance()
    seqs = [x["seq"] for x in e.log]
    assert seqs == sorted(seqs) == list(range(1, len(seqs) + 1)), "seq 必须从 1 严格单调"
    replay = eng()
    for ev in e.log:
        p = ev["payload"]
        if ev["type"] == "order":
            replay.submit(symbol=p["symbol"], side=p["side"], qty=p["qty"],
                          client_order_id=p["client_order_id"],
                          reference_close=p["reference_close"])
        elif ev["type"] == "cancel":
            replay.cancel(p["order_id"])
        elif ev["type"] == "advance":
            replay.advance()
    assert replay.state() == e.state(), "按 seq 重放 order/cancel/advance 必须到同一终态"


def test_fill_rate_counts_submitted_not_events():
    e = eng()
    e.submit(symbol=SYM, side="buy", qty=100, client_order_id="c1", reference_close=10.0)
    e.submit(symbol=SYM, side="buy", qty=100, client_order_id="c1", reference_close=10.0)  # 幂等重放
    e.advance()
    assert e.fill_rate() == 1.0, "幂等重放不得把分母撑大"


# --------------------------------------------------------------- 输入校验

@pytest.mark.parametrize("qty", [0, -100, 150, 100.0, True])
def test_bad_qty_is_422(qty):
    e = eng()
    with pytest.raises(SimError) as ei:
        e.submit(symbol=SYM, side="buy", qty=qty, client_order_id="c1", reference_close=10.0)
    assert ei.value.status == 422


@pytest.mark.parametrize("cid", ["", "a" * 65, "bad id", "x\ny"])
def test_bad_client_order_id_is_422(cid):
    e = eng()
    with pytest.raises(SimError) as ei:
        e.submit(symbol=SYM, side="buy", qty=100, client_order_id=cid, reference_close=10.0)
    assert ei.value.status == 422


# --------------------------------------------------------------- 挂起项的可见性

def test_pending_endpoint_items_are_declared():
    """**这条测试在 2026-09-04 按设计翻转过一次，留记录**（同 N-33 做法）。

    翻转前：`PENDING_ENDPOINT_ITEMS` 含 SIM-A/B/E/H/N，且断言
    `'"/sim/' not in app.py` —— 端点没上线时它盯着「别悄悄以为上线了」。
    翻转后：端点已登记（`ops/test_sim_endpoints.py` 里 19 条验收），
    名单只剩 **SIM-N**（要从 f02 的任务容器真打一次，起不了服务就测不了）。

    读**文本**而不 import gateway.app：后者会拉 backends → snapshots（数据面模块），
    在执行面与开发机上都不存在。判据一样准，且两地都能跑。
    """
    assert set(PENDING_ENDPOINT_ITEMS) == {"SIM-N"}
    src = (_REPO / "gateway" / "app.py").read_text(encoding="utf-8")
    assert '"/sim/state"' in src, \
        "端点从 ALLOWED_ROUTES 里消失了 —— 白名单是逐条登记的，少一条就是 404"
    for item in ("/sim/order", "/sim/cancel", "/sim/advance", "/sim/log"):
        assert f'"{item}"' in src, item


# ===================================================== 红队 2026-09-04 补的断言

def test_transitions_are_recorded_by_the_engine_not_inferred_from_log():
    """迁移集必须来自 `_transition` 的真实记录。事后从日志猜的版本漏掉
    filled→idle / cancelled→idle（日志里没有对应事件），而「补上去」就等于自证。"""
    e = eng()
    e.submit(symbol=SYM, side="buy", qty=100, client_order_id="c1", reference_close=10.0)
    assert e.transitions == [("idle", "ordered")], "提交必须真的走一条 idle→ordered"
    e.advance()
    assert ("ordered", "filled") in e.transitions and ("filled", "idle") in e.transitions
    e.log.clear()                       # 判据不是从 log 推的
    assert ("filled", "idle") in e.transitions_seen()


def test_cash_accounting_is_asserted_not_just_exercised():
    """现金/持仓的记账原先零断言 —— 突变全部存活。这里把每一步的数钉死。"""
    e = eng(initial_cash=100_000.0, fee_rate=0.001)
    e.submit(symbol=SYM, side="buy", qty=100, client_order_id="c1", reference_close=10.0)
    assert e.cash == pytest.approx(100_000.0 - 100 * 10.0 * 1.001), "买单提交冻结 qty×参考价×(1+费率)"
    e.advance()                                   # 次日收盘 11.0 成交
    paid = 100 * 11.0 * 1.001
    assert e.cash == pytest.approx(100_000.0 - paid), "成交按实际价多退少补"
    assert e.positions[SYM]["shares"] == 100
    assert e.positions[SYM]["avg_cost"] == pytest.approx(11.0)
    e.advance()                                   # T+1：成交当日不可卖，先推进一天
    e.submit(symbol=SYM, side="sell", qty=100, client_order_id="c2", reference_close=12.0)
    assert e.cash == pytest.approx(100_000.0 - paid), "卖单提交不冻结现金"
    e.advance()                                   # 次日收盘 13.0 成交
    assert e.cash == pytest.approx(100_000.0 - paid + 100 * 13.0 * 0.999), "卖出到账扣费"
    assert e.positions[SYM]["shares"] == 0


def test_avg_cost_is_share_weighted_across_two_fills():
    """单次买入时「加权均价」与「直接取成交价」同值 —— 突变会存活。
    必须**分两批不同价**建仓，加权才成为可被证伪的判据。"""
    e = eng(initial_cash=1_000_000.0)
    e.submit(symbol=SYM, side="buy", qty=100, client_order_id="c1", reference_close=10.0)
    e.advance()                                   # 100 股 @ 11.0
    e.submit(symbol=SYM, side="buy", qty=300, client_order_id="c2", reference_close=11.0)
    e.advance()                                   # 300 股 @ 12.0
    assert e.positions[SYM]["shares"] == 400
    assert e.positions[SYM]["avg_cost"] == pytest.approx((11.0 * 100 + 12.0 * 300) / 400)
    assert e.positions[SYM]["avg_cost"] != pytest.approx(12.0), "取最后成交价会得 12.0"


def test_cancel_and_reject_refund_the_frozen_cash_exactly():
    e = eng(initial_cash=50_000.0, fee_rate=0.002)
    e.submit(symbol=SYM, side="buy", qty=300, client_order_id="c1", reference_close=10.0)
    assert e.cash != pytest.approx(50_000.0)
    e.cancel("o000001")
    assert e.cash == pytest.approx(50_000.0), "撤单必须**精确**解冻"
    e2 = eng(initial_cash=50_000.0, fee_rate=0.002, tradable={(CAL[1], SYM): "suspend"})
    e2.submit(symbol=SYM, side="buy", qty=100, client_order_id="c1", reference_close=10.0)
    e2.advance()
    assert e2.cash == pytest.approx(50_000.0), "零成交拒绝也要解冻"


def test_cancel_after_fill_returns_already_filled_not_409():
    """契约 §2：对已成交单返回 `already_filled`。判据看**成交事实**不是当前 state ——
    成交后状态已推回 idle，看 state 的分支永不可达。"""
    e = eng()
    e.submit(symbol=SYM, side="buy", qty=100, client_order_id="c1", reference_close=10.0)
    e.advance()
    assert e.orders["o000001"].filled_price is not None
    assert e.cancel("o000001") == {"status": "already_filled"}


def test_sim_l_window_end_binds_before_calendar_runs_out():
    """SIM-L 原来测的其实是「日历用尽」—— eng() 把 window_end 钉成日历最后一天。"""
    e = SimEngine(calendar=list(CAL), window_end=CAL[1],
                  closes={(d, SYM): 10.0 for d in CAL})
    e.advance()
    with pytest.raises(SimError) as ei:
        e.advance()
    assert ei.value.code == "window_exhausted"
    assert len(CAL) > 2, "日历还有剩 —— 拦下它的必须是 window_end"


def test_slip_basis_uses_env_price_not_the_self_reported_one():
    """`reference_close` 是**被测方自报**的数字。拿它当 Slip 基准 = 让 agent
    自己定自己的滑点指标。基准必须取环境侧记录的提交时可见价。"""
    honest = eng(slippage_reference_price="reference_close")
    honest.submit(symbol=SYM, side="buy", qty=100, client_order_id="c1", reference_close=10.0)
    honest.advance()
    liar = eng(slippage_reference_price="reference_close")
    liar.submit(symbol=SYM, side="buy", qty=100, client_order_id="c1", reference_close=11.0)
    liar.advance()
    assert honest.slippage_bps()["slippage_bps"] == pytest.approx(
        liar.slippage_bps()["slippage_bps"]), "自报值不得改变 Slip"
    assert liar.orders["o000001"].reference_close == 11.0, "自报值仍如实记录"
    assert liar.orders["o000001"].env_reference_close == 10.0, "结算用环境侧的价"


def test_slip_fails_closed_when_basis_price_missing():
    """取不到基准价要报错，不是静默退回成交价 —— 后者把 Slip 抹成 0 并让三档坍缩，
    而 SIM-F「三档互不相同」只是因为 fixture 一直喂着 opens。"""
    e = SimEngine(calendar=list(CAL), window_end=CAL[-1],
                  closes={(d, SYM): 10.0 + i for i, d in enumerate(CAL)},
                  opens={}, slippage_reference_price="open")
    e.submit(symbol=SYM, side="buy", qty=100, client_order_id="c1", reference_close=10.0)
    e.advance()
    with pytest.raises(SimError) as ei:
        e.slippage_bps()
    assert ei.value.code == "slippage_base_unavailable"


def test_client_order_id_reuse_with_different_body_is_refused():
    """过度幂等可被利用：同一 client_order_id 换一张单子静默回 accepted，
    委托凭空消失，而 Fill = 成交数/提交数 被拉高。"""
    e = eng()
    e.submit(symbol=SYM, side="buy", qty=100, client_order_id="c1", reference_close=10.0)
    e.submit(symbol=SYM, side="buy", qty=100, client_order_id="c1", reference_close=10.0)
    with pytest.raises(SimError) as ei:
        e.submit(symbol=SYM, side="sell", qty=200, client_order_id="c1", reference_close=10.0)
    assert ei.value.code == "client_order_id_reused"


def test_advance_state_goes_through_the_visibility_projection():
    """advance 返回的 state 原先直接 self.state()，把未声明字段全量吐给 agent。"""
    assert set(eng().advance(visible=("sim_date", "cash"))["state"]) == {"sim_date", "cash"}


def test_unknown_visible_state_field_is_refused_not_silently_dropped():
    with pytest.raises(SimError) as ei:
        eng().state(visible=("sim_date", "nav_typo"))
    assert ei.value.code == "unknown_visible_state_field"


def test_naked_short_and_over_leverage_are_refused():
    """撮合期原先零风控：无持仓可裸卖空、无买力可无限加杠杆。"""
    e = eng(initial_cash=1_000.0)
    with pytest.raises(SimError) as ei:
        e.submit(symbol=SYM, side="sell", qty=100, client_order_id="c1", reference_close=10.0)
    assert ei.value.code == "insufficient_position"
    with pytest.raises(SimError) as ei:
        e.submit(symbol=SYM, side="buy", qty=100_000, client_order_id="c2", reference_close=10.0)
    assert ei.value.code == "insufficient_cash"


def test_t_plus_1_settlement_blocks_same_day_sell():
    """契约 §4：成交日买入的**次日**才可卖。"""
    e = eng(initial_cash=1_000_000.0)
    e.submit(symbol=SYM, side="buy", qty=100, client_order_id="c1", reference_close=10.0)
    e.advance()                                   # 成交日
    assert e.positions[SYM]["shares"] == 100
    assert e.sellable(SYM) == 0, "成交当日不可卖（T+1）"
    with pytest.raises(SimError) as ei:
        e.submit(symbol=SYM, side="sell", qty=100, client_order_id="c2", reference_close=11.0)
    assert ei.value.code == "insufficient_position"
    e.advance()                                   # 次日
    assert e.sellable(SYM) == 100, "次日可卖"
    e.submit(symbol=SYM, side="sell", qty=100, client_order_id="c3", reference_close=12.0)


def test_permission_scope_matches_the_task_declarations():
    """**契约与题目声明冲突的锁**（红队 2026-09-04）。

    两条判据，方向相反，缺一不可：
    ① 各题声明的操作**并集 ⊆ GATED_OPERATIONS** —— 引擎必须闸得住所有被声明的操作，
       否则某题授权了 X 而引擎根本不管 X，越权率永远是 0。
    ② `advance` / `state` / `log` **不出现在任何一道题的声明里** —— 这是「它们是环境操作、
       不受 permitted_operations 管」这个判断的**证据**。哪天有题声明了它们，
       说明契约按字面收紧了，这条会红，逼人重新对齐。

    注意 `s8-ops-01` 只声明 `["order"]` 是**故意的**：那道题测的就是越权
    （agent 去 cancel → 403 并计入越权率）。所以判据不能写成「⊆ 各题交集」——
    我第一版就是这么写的，它把一道题的设计当成了缺陷。
    """
    from genetask import packager as _P
    rows = _P.load_params(_REPO / "genetask" / "params" / "v1.0-smoke40.yaml")
    s8 = [r for r in rows if r["stage"] == "S8"]
    assert s8
    declared = [set(r["declared"].get("permitted_operations") or []) for r in s8]
    union = set().union(*declared)
    assert union <= GATED_OPERATIONS, (
        f"有题声明了引擎不闸的操作 {sorted(union - GATED_OPERATIONS)} —— "
        f"授权了却不管，越权率恒为 0")
    env_ops = {"advance", "state", "log"}
    leaked = [r["task_id"] for r, d in zip(s8, declared) if d & env_ops]
    assert not leaked, (
        f"{leaked} 声明了环境操作 —— 契约按字面收紧了，"
        f"GATED_OPERATIONS 与 _require 要跟着改")
    # 至少有一道题**故意少授权**，否则越权率这个指标没有落点
    assert any(d != GATED_OPERATIONS for d in declared), \
        "没有任何一道题授权集小于全集 —— 越权率测不出东西"
