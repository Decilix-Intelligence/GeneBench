# -*- coding: utf-8 -*-
"""`reference/s8_oracle_common.py` 的判据测试。

S8 的 oracle 与其余七个阶段不同：它与环境**有状态交互**，而网关的 `as_of` 上界
与模拟时钟耦合（契约 §3.1）。第一版四个模板全部撞在这上面 —— 用 `task.as_of`
去请求，被 `asof_beyond_freeze_line` 全面拒。这里把那条口径钉死。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reference import s8_oracle_common as s8                          # noqa: E402

TASK = {"task_id": "s8-cor-01", "as_of": "2026-07-31",
        "window": {"start": "2026-07-01", "end": "2026-07-31"},
        "universe": "csi300", "declared": {"visible_state_fields": ["cash"]}}


class FakeGW:
    """假网关。**记下每次请求时的 `as_of`** —— 那正是要测的东西。"""

    def __init__(self, sim_date="2026-07-01"):
        self.as_of = ""
        self.seen: list[tuple[str, str]] = []
        self.sim_date = sim_date
        self.log_events: list[dict] = []
        self.next_order = 0
        self.ledger: list[dict] = []

    def get_json(self, path, **params):
        self.seen.append((path, self.as_of))
        if path == "/sim/log":
            return {"events": list(self.log_events), "sim_date": self.sim_date}, "ts", 200
        if path == "/sim/state":
            return {"cash": 1.0, "positions": []}, "ts", 200
        return {}, "ts", 200

    def post_json(self, path, body):
        self.seen.append((path, self.as_of))
        if path == "/sim/order":
            self.next_order += 1
            oid = f"o{self.next_order:06d}"
            self.log_events.append({"seq": len(self.log_events) + 1, "ts": "T1",
                                    "type": "order", "payload": {"order_id": oid, **body}})
            return {"order_id": oid, "status": "accepted", "reason": None}, 200
        if path == "/sim/advance":
            assert body == {}, "advance 不接受任何 body 键"
            self.sim_date = "2026-07-02"
            return {"sim_date": self.sim_date, "fills": [], "state": {}}, 200
        return {}, 200


def test_as_of_starts_at_the_declared_window_start():
    """初值取题面的 `window.start` —— **从 task.yaml 读得出来**，不从环境拿（D-32）。
    它 ≤ 引擎的第一个交易日，所以一定不越 §3.1 的上界。"""
    gw = FakeGW()
    s8.Sim(gw, TASK)
    assert gw.seen[0] == ("/sim/log", "2026-07-01")


def test_as_of_never_uses_the_task_as_of():
    """用 `task.as_of`（冻结线那天）去请求会被全面拒 —— 第一版四个模板全撞在这上面。"""
    gw = FakeGW()
    sim = s8.Sim(gw, TASK)
    sim.state()
    assert all(a != TASK["as_of"] for _p, a in gw.seen), gw.seen


def test_as_of_moves_forward_only_after_advance():
    """§3.1：**推进之后 `as_of` 才前移**。"""
    gw = FakeGW()
    sim = s8.Sim(gw, TASK)
    assert gw.as_of == "2026-07-01"
    sim.advance()
    assert gw.as_of == "2026-07-02" and sim.sim_date == "2026-07-02"


def test_advance_sends_an_empty_body():
    """端点收到任何 body 键就 422（「收不到参数，就没有可以违反的规则」）。"""
    s8.Sim(FakeGW(), TASK).advance()                # FakeGW 里有断言


def test_denied_requests_are_counted_not_swallowed():
    gw = FakeGW()
    sim = s8.Sim(gw, TASK)
    gw.post_json = lambda path, body: ({"error": "denied"}, 403)
    sim.cancel("o000001")
    assert sim.denied == 1


# ------------------------------------------------------------------ 确定性
def test_client_order_id_is_deterministic():
    """`uuid4` 让同一道题两次 gold 的字节不同 —— 那是可比性的直接否定。"""
    a = s8.client_order_id("s8-cor-01", "600000.SH", "buy", 0)
    b = s8.client_order_id("s8-cor-01", "600000.SH", "buy", 0)
    assert a == b and "." not in a and a.startswith("s8-cor-01-")


def test_client_order_id_separates_side_and_sequence():
    ids = {s8.client_order_id("t", "600000.SH", side, i)
           for side in ("buy", "sell") for i in range(2)}
    assert len(ids) == 4


# ------------------------------------------------------------------ 日志 → 产物
LOG = [
    {"ts": "T1", "type": "order", "payload": {"order_id": "o1", "symbol": "A"}},
    {"ts": "T2", "type": "advance", "payload": {"from": "d1", "to": "d2", "n_fills": 1}},
    {"ts": "T2", "type": "fill", "payload": {"order_id": "o1", "symbol": "A",
                                             "side": "buy", "qty": 100, "price": 11.0}},
    {"ts": "T3", "type": "order", "payload": {"order_id": "o2", "symbol": "B"}},
    {"ts": "T4", "type": "reject", "payload": {"order_id": "o2", "reason": "suspend"}},
    {"ts": "T5", "type": "cancel", "payload": {"order_id": "o3"}},
]


def test_events_drop_advance_and_fold_reject_into_state():
    """`artifact_schema` 的事件枚举只有 order/fill/cancel/state。
    `advance` 不是委托生命周期事件；`reject` 折成一条 `state`（委托被打回 idle）。"""
    ev = s8.events_from_log(LOG)
    assert [e["type"] for e in ev] == ["order", "fill", "order", "state", "cancel"]
    assert all(e["type"] in s8.EVENT_TYPES for e in ev)
    assert [e for e in ev if e["type"] == "state"][0]["reason"] == "suspend"


def test_events_keep_the_server_timestamp():
    """题面写死：事件 `ts` 必须**原样**用网关响应里的服务器时间戳。"""
    assert [e["ts"] for e in s8.events_from_log(LOG)] == ["T1", "T2", "T3", "T4", "T5"]


def test_transitions_follow_the_paths_the_engine_actually_walks():
    tr = s8.transitions_from_log(LOG)
    pairs = [(t["from"], t["to"]) for t in tr]
    assert pairs == [("idle", "ordered"), ("ordered", "filled"), ("filled", "idle"),
                     ("idle", "ordered"), ("ordered", "cancelled"), ("cancelled", "idle"),
                     ("ordered", "cancelled"), ("cancelled", "idle")]


def test_a_reject_is_a_kill_path_not_a_fill_path():
    """被拒的委托走 cancelled→idle。记成 filled 的话 `fill_rate` 会虚高。"""
    tr = s8.transitions_from_log([LOG[3], LOG[4]])
    assert ("ordered", "filled") not in [(t["from"], t["to"]) for t in tr]


# ------------------------------------------------------------------ 指标
def test_fill_rate_is_filled_over_ordered():
    orders = {"o1": {"symbol": "A", "side": "buy", "qty": 100, "reference_close": 10.0,
                     "filled": 100, "notional": 1000.0},
              "o2": {"symbol": "B", "side": "buy", "qty": 100, "reference_close": 10.0,
                     "filled": 0, "notional": 0.0}}
    assert s8.fill_metrics(orders)["fill_rate"] == 0.5


def test_slippage_is_positive_when_the_fill_is_above_the_basis():
    """成交价高于计价基准 → 正。买单如此。"""
    orders = {"o1": {"symbol": "A", "side": "buy", "qty": 100, "reference_close": 10.0,
                     "filled": 100, "notional": 1010.0}}
    assert s8.fill_metrics(orders)["slippage_bps"] == pytest.approx(100.0)


def test_slippage_does_not_flip_sign_for_sells():
    """**N-383（2026-09-10 裁定，随 r1.0.21 落）：卖单不翻符号。**

    卖单成交在基准之下 → **负** 100 bps，不是正 100。此前这里断言的是「卖便宜了 = 同样不利
    = 同样为正」（`fill_metrics` 乘一个 `sign = +1 买 / −1 卖`），而规格与题面两处都写的是
    **不翻符号**：

    * `ops/specs/GeneBench指标规格_v1.md` §3：`Slip = 量加权(成交价 − 决策时点价) bps`
    * S8 五题两臂题面（N-127）：「成交价高于计价基准时取正，低于计价基准时取负」
    * `gateway/sim_engine.py::slippage_bps`：`qty × (成交价 − 基准) / 基准 × 1e4`

    以规格 §3 为准 —— 三处里只有 `fill_metrics` 一处翻了符号，改它是最小改动。

    **代价要写下来**：旧口径是「不利为正」，买卖两条腿的不利同号、相加；新口径下**一买一卖
    的滑点会互相抵消**，量加权之后一个双边完成的建仓＋清仓可能报出接近 0 的 Slip，
    而两条腿各自都是不利成交。旧断言的 docstring 说的正是这件事，它没有说错 —— 变的是
    这个量的**定义**：v1 的 Slip 是「相对基准的价格偏离」，不是「执行不利度」。要量执行不利度
    得另立一个指标（登记 N-? 在 `ops/tickets_inbox/Y1.md`），不能靠在 oracle 里偷偷翻符号，
    因为翻了之后它就与网关自己算的那份、与题面告诉被测方的那条对不上。
    """
    orders = {"o1": {"symbol": "A", "side": "sell", "qty": 100, "reference_close": 10.0,
                     "filled": 100, "notional": 990.0}}
    assert s8.fill_metrics(orders)["slippage_bps"] == pytest.approx(-100.0)


def test_the_three_implementations_agree_on_the_sign(tmp_path):
    """三处实现同向：oracle 主干 / 网关引擎 / 评分器重算，同一笔卖单同号。

    符号是**跨三个文件**的约定，任何一处单独改都会让另外两处静默地不一致 ——
    N-383 就是这么被发现的（两处不一致挂了四天，因为 Slip 当时只报不判）。
    """
    from scorer.l3 import _slip_recompute
    oracle = s8.fill_metrics({"o1": {"symbol": "A", "side": "sell", "qty": 100,
                                     "reference_close": 10.0, "filled": 100,
                                     "notional": 990.0}})["slippage_bps"]
    ev = [{"ts": "2026-07-03T15:00:00+08:00", "type": "order", "order_id": "o1",
           "symbol": "A", "side": "sell", "qty": 100, "reference_close": 10.0},
          {"ts": "2026-07-06T15:00:00+08:00", "type": "fill", "order_id": "o1",
           "symbol": "A", "side": "sell", "qty": 100, "price": 9.9}]
    scorer_side, tol, n = _slip_recompute(ev, "reference_close")
    assert n == 1
    assert scorer_side == pytest.approx(oracle)
    # 网关引擎的公式（`gateway/sim_engine.py::slippage_bps`）逐字：qty × (成交价 − 基准) / 基准 × 1e4
    engine = 100 * (9.9 - 10.0) / 10.0 * 1e4 / 100
    assert engine == pytest.approx(oracle)
    # 容差 = 一个最小价位换成 bps：0.01 / 10.0 × 1e4 = 10 bps
    assert tol == pytest.approx(10.0)


def test_slippage_is_volume_weighted():
    orders = {"o1": {"symbol": "A", "side": "buy", "qty": 100, "reference_close": 10.0,
                     "filled": 100, "notional": 1010.0},
              "o2": {"symbol": "B", "side": "buy", "qty": 300, "reference_close": 10.0,
                     "filled": 300, "notional": 3000.0}}
    assert s8.fill_metrics(orders)["slippage_bps"] == pytest.approx(25.0)


def test_no_fills_gives_zero_not_nan():
    assert s8.fill_metrics({})["slippage_bps"] == 0.0
    assert s8.fill_metrics({})["fill_rate"] == 0.0
