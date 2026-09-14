"""卡 4.4：模拟盘的**引擎**（状态机 + 撮合 + 审计日志）。

与 router 分开的理由：引擎是纯逻辑，**可以脱离 FastAPI 与网关起停单测** ——
契约的可测部分（状态机迁移表、幂等、单调推进、Slip 三个基准）不该等到端点上线才验。
router（`gateway/routers/sim.py`）只做 HTTP 与头校验，把语义全交给这里。

三条硬约束，每条对应一个失败模式：
* **迁移表引用 `reference.artifact_schema.LEGAL_TRANSITIONS`，不重抄**（卡 4.4 §3）：
  抄第二份，两份就会漂 —— 而漂的表现是「校验器说合法、环境说非法」或者反过来，两边都不报错。
* **`advance` 单调、单步、不接受目标日期**：杜绝跳日与回看。每次落一条 `advance` 事件。
* **Slip 基准价由声明决定，实现不给默认**：题面没声明时按契约默认（`reference_close`）跑，
  但产物里要**如实记下用的是默认** —— 不许让「默认」看起来像「agent 选的」。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# **契约常量从 `genetask/s8_contract.py` 取，不从 `reference/`**（用户裁定 ⑧，2026-09-10）。
# 上面第 8 条硬约束说的「引用不重抄」一个字不改 —— 变的是被引用的那一端搬出了答案面：
# 原先这一行是全树唯一一条「网关 import reference」，红线 B2 不许答案面上执行面，
# 于是单机双容器形态里这个网关 import 不起来。`ops/test_s8_contract.py` 用 AST 钉住
# `gateway/**` 一条 `import reference` 都不许再有。
from genetask.s8_contract import (LEGAL_TRANSITIONS, TRADABILITY_STATES,
                                  UNTRADABLE_STATES)

#: 委托状态。与 `LEGAL_TRANSITIONS` 的节点集一致（下面有断言）。
ORDER_STATES: frozenset[str] = frozenset({s for pair in LEGAL_TRANSITIONS for s in pair})

#: v1 不产生 `partial` —— 保留给 v2（契约 §5）。这是**实现的自我约束**，有测试盯着。
V1_UNREACHABLE: frozenset[str] = frozenset({"partial"})

#: Slip 基准价的三个取值（`reference/artifact_schema.py::DECLARATION_ENUMS["slippage_reference_price"]`）
SLIPPAGE_BASES: tuple[str, ...] = ("close", "open", "reference_close")
#: 契约 §3.2 的 v1 默认。**实现不给默认**：这是契约的默认，用了要如实记。
CONTRACT_DEFAULT_SLIPPAGE_BASE = "reference_close"

#: **受 `permitted_operations` 管的操作**。
#:
#: ⚠️ **契约与题目声明在这里冲突，待裁定**（红队 2026-09-04）：契约 §2 字面说
#: 「允许的操作由 permitted_operations 决定」，读起来包括全部五个端点；而 v1.0 冒烟集里
#: **5 道 S8 题全部只声明 ["order","cancel"]**（s8-ops-01 更只有 ["order"]），
#: 没有一道声明 advance/state/log。把五个都闸住 = **上线即整阶段 403**，题根本没法做。
#: 现按题目声明取交集：只闸交易类操作。裁定方向二选一 —— ① 契约收窄为「交易类操作」；
#: ② 题目声明补上三项。`test_permission_scope_matches_the_task_declarations` 钉着一致性。
GATED_OPERATIONS: frozenset[str] = frozenset({"order", "cancel"})

_CLIENT_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")


class SimError(Exception):
    """带 HTTP 状态码的领域错误。router 直接翻成响应。"""

    def __init__(self, status: int, code: str, msg: str):
        super().__init__(msg)
        self.status, self.code, self.msg = status, code, msg


@dataclass
class Order:
    order_id: str
    client_order_id: str
    symbol: str
    side: str                       # buy | sell
    qty: int
    reference_close: float
    submitted_on: str               # 提交日（sim_date）
    state: str = "ordered"
    #: 环境侧记录的**提交时可见价** = 提交日的 close。Slip 的 `reference_close` 档取它，
    #: **不取 agent 自报的那个数** —— 自报的数被测方完全可控，拿它当基准等于让 agent
    #: 自己定自己的滑点指标（红队 2026-09-04，high）。自报值只作记录与冻结额估算。
    env_reference_close: float | None = None
    filled_price: float | None = None
    filled_on: str | None = None
    #: 终结事实。**不看当前 state**：成交/撤单之后状态都会推回 idle，
    #: 看 state 的判据会永不可达（红队 2026-09-04 抓到 already_filled 分支就是死的）。
    cancelled_on: str | None = None


@dataclass
class SimEngine:
    """一次运行的模拟盘。**不含 HTTP**、不读环境变量、不落文件 —— 全部经参数注入。"""

    calendar: list[str]                       # 交易日，升序
    window_end: str
    closes: dict[tuple[str, str], float]      # (date, symbol) → close
    opens: dict[tuple[str, str], float] = field(default_factory=dict)
    #: (date, symbol) → `/tradability` 的 status，取值只能是 `TRADABILITY_STATES`。
    #: 缺省视为 `trade`；**不认识的取值一律拒单**（fail-closed）。
    tradable: dict[tuple[str, str], str] = field(default_factory=dict)
    #: (date, symbol) → 涨停/跌停标志。涨跌停**不是** status 的取值，是独立字段。
    limit_up: set[tuple[str, str]] = field(default_factory=set)
    limit_down: set[tuple[str, str]] = field(default_factory=set)
    slippage_reference_price: str | None = None      # None = 题面没声明 → 用契约默认
    permitted_operations: tuple[str, ...] = ("order", "cancel", "advance", "state", "log")
    initial_cash: float = 1_000_000.0
    fee_rate: float = 0.0

    def __post_init__(self) -> None:
        if not self.calendar:
            raise ValueError("日历为空 —— 模拟盘没有可推进的日子")
        if self.slippage_reference_price is not None and \
                self.slippage_reference_price not in SLIPPAGE_BASES:
            raise ValueError(f"slippage_reference_price={self.slippage_reference_price!r} "
                             f"不在 {SLIPPAGE_BASES}")
        self._i = 0                                     # 当前日在 calendar 里的下标
        self.cash = float(self.initial_cash)
        self.positions: dict[str, dict[str, float]] = {}
        self.orders: dict[str, Order] = {}
        self._by_client: dict[str, str] = {}
        self.log: list[dict[str, Any]] = []
        #: 引擎**实际走过**的迁移。由 `_transition()` 记录，不是事后从日志猜 ——
        #: 猜的版本会漏掉日志里没有事件的迁移（filled→idle / cancelled→idle），
        #: 而"补上去"就等于自证：不管引擎有没有真走，判据都说走过了（红队 2026-09-04）。
        self.transitions: list[tuple[str, str]] = []
        self._seq = 0
        self._n_order_id = 0
        #: T+1：symbol → {成交日: 当日买入股数}。成交日买入的**次日**才可卖（契约 §4）。
        self._locked: dict[str, dict[str, int]] = {}

    # ---------------------------------------------------------- 基础

    @property
    def sim_date(self) -> str:
        return self.calendar[self._i]

    @property
    def slippage_base(self) -> str:
        """实际用的基准价。**没声明时用契约默认，但 used_default 会如实说**。"""
        return self.slippage_reference_price or CONTRACT_DEFAULT_SLIPPAGE_BASE

    @property
    def slippage_base_is_default(self) -> bool:
        return self.slippage_reference_price is None

    def _emit(self, type_: str, payload: dict) -> dict:
        self._seq += 1
        ev = {"seq": self._seq, "ts": f"{self.sim_date}T15:00:00+08:00",
              "type": type_, "payload": payload}
        self.log.append(ev)
        return ev

    def _require(self, op: str) -> None:
        if op not in GATED_OPERATIONS:
            return          # 环境操作，不受 permitted_operations 管（见 GATED_OPERATIONS 处的说明）
        if op not in self.permitted_operations:
            # 403 + 越权。**计入网关日志的 deny**，不采信 artifact 自报（契约 §6）
            raise SimError(403, "operation_not_permitted",
                           f"本题的 permitted_operations 不含 {op!r}")

    def _transition(self, o: Order, to: str) -> None:
        """所有状态变更**只走这里** —— 迁移合法性在一个地方判，不散落在各处。"""
        if (o.state, to) not in LEGAL_TRANSITIONS:
            raise SimError(409, "illegal_transition",
                           f"{o.order_id}: {o.state} → {to} 不在 LEGAL_TRANSITIONS")
        if to in V1_UNREACHABLE:
            raise SimError(500, "v1_unreachable_state",
                           f"v1 不产生 {to!r} —— 出现它说明实现跑偏了（契约 §5）")
        self.transitions.append((o.state, to))
        o.state = to

    # ---------------------------------------------------------- 端点语义

    def state(self, visible: tuple[str, ...] | None = None, *, _skip_gate: bool = False) -> dict:
        """只读投影。**未声明的字段不返回**（不是返回 null）—— 契约 §2。

        `visible` 里出现表外的字段名 → 报错而不是静默丢弃：题面声明了一个环境不认识的
        字段名，说明声明与实现对不上，静默丢会让这件事永远发现不了。
        """
        if not _skip_gate:
            self._require("state")
        full = {
            "sim_date": self.sim_date,
            "cash": round(self.cash, 6),
            "positions": [{"symbol": s, "shares": v["shares"], "avg_cost": round(v["avg_cost"], 6)}
                          for s, v in sorted(self.positions.items()) if v["shares"]],
            "nav": round(self._nav(), 6),
            "pending_orders": [{"order_id": o.order_id, "client_order_id": o.client_order_id,
                                "symbol": o.symbol, "side": o.side, "qty": o.qty}
                               for o in self.orders.values() if o.state == "ordered"],
        }
        if visible is None:
            return full
        unknown = [k for k in visible if k not in full]
        if unknown:
            raise SimError(422, "unknown_visible_state_field",
                           f"visible_state_fields 里有环境不认识的字段：{unknown}；"
                           f"可选 {sorted(full)}")
        return {k: v for k, v in full.items() if k in visible}

    def audit_log(self) -> list[dict]:
        """`/sim/log` 的语义。**也过越权闸** —— permitted_operations 管的是全部五个操作，
        原先只挂在 order/cancel/advance 上，state 与 log 是敞开的。"""
        self._require("log")
        return list(self.log)

    def _nav(self) -> float:
        mv = 0.0
        for s, v in self.positions.items():
            px = self.closes.get((self.sim_date, s))
            mv += (px if px is not None else v["avg_cost"]) * v["shares"]
        return self.cash + mv

    def sellable(self, symbol: str) -> int:
        """可卖股数 = 持仓 − 今日买入（T+1）− 已挂卖单。契约 §4 的「成交日买入的次日才可卖」。"""
        held = self.positions.get(symbol, {}).get("shares", 0)
        locked = self._locked.get(symbol, {}).get(self.sim_date, 0)
        pending = sum(o.qty for o in self.orders.values()
                      if o.state == "ordered" and o.side == "sell" and o.symbol == symbol)
        return max(0, held - locked - pending)

    def submit(self, *, symbol: str, side: str, qty: int, client_order_id: str,
               reference_close: float) -> dict:
        self._require("order")
        if side not in ("buy", "sell"):
            raise SimError(422, "bad_side", f"side={side!r}")
        if not isinstance(qty, int) or isinstance(qty, bool) or qty <= 0 or qty % 100:
            raise SimError(422, "bad_qty", f"qty 必须是 100 的正整数倍，收到 {qty!r}")
        if not _CLIENT_ID_RE.match(str(client_order_id or "")):
            raise SimError(422, "bad_client_order_id", f"client_order_id={client_order_id!r}")
        # 幂等：同一个 client_order_id 返回**同一个** order_id，且**不产生第二条 order 事件**
        if client_order_id in self._by_client:
            oid = self._by_client[client_order_id]
            prev = self.orders[oid]
            same = (prev.symbol == symbol and prev.side == side and prev.qty == int(qty))
            if not same:
                # **过度幂等**是可被利用的：同一 client_order_id 下换一张单子静默回 accepted，
                # 委托就凭空消失了，而 Fill = 成交数/提交数 会被拉高（红队 2026-09-04，high）。
                raise SimError(409, "client_order_id_reused",
                               f"{client_order_id!r} 已用于 {prev.symbol}/{prev.side}/{prev.qty}，"
                               f"不得复用于 {symbol}/{side}/{qty}")
            return {"order_id": oid, "status": "accepted", "reason": "idempotent_replay"}
        self._n_order_id += 1
        oid = f"o{self._n_order_id:06d}"
        env_ref = self.closes.get((self.sim_date, symbol))
        o = Order(order_id=oid, client_order_id=client_order_id, symbol=symbol, side=side,
                  qty=int(qty), reference_close=float(reference_close),
                  env_reference_close=(float(env_ref) if env_ref is not None else None),
                  submitted_on=self.sim_date)
        # **撮合期风控**：原先零校验 —— 无持仓可裸卖空、无买力可无限加杠杆（红队 2026-09-04）。
        if side == "sell":
            avail = self.sellable(symbol)
            if o.qty > avail:
                raise SimError(409, "insufficient_position",
                               f"{symbol} 可卖 {avail} 股（持仓减今日买入与已挂卖单，T+1），"
                               f"请求卖 {o.qty}")
        else:
            need = o.qty * o.reference_close * (1 + self.fee_rate)
            if need > self.cash:
                raise SimError(409, "insufficient_cash",
                               f"冻结需要 {need:.2f}，可用现金 {self.cash:.2f}")
        self.orders[oid] = o
        self._by_client[client_order_id] = oid
        o.state = "idle"                      # 先落在起点，再经 _transition 记一条 idle→ordered
        self._transition(o, "ordered")
        if side == "buy":
            self.cash -= o.qty * o.reference_close * (1 + self.fee_rate)   # 冻结
        self._emit("order", {"order_id": oid, "client_order_id": client_order_id,
                             "symbol": symbol, "side": side, "qty": o.qty,
                             "reference_close": o.reference_close})
        return {"order_id": oid, "status": "accepted", "reason": None}

    def cancel(self, order_id: str) -> dict:
        self._require("cancel")
        o = self.orders.get(order_id)
        if o is None:
            return {"status": "not_found"}
        if o.filled_price is not None:
            # 判据看**成交事实**而不是当前 state：成交后 _match 立刻把状态推到 idle，
            # 看 state == "filled" 的话这个分支永不可达，实际行为会变成抛 409（违契约 §2）。
            return {"status": "already_filled"}
        if o.cancelled_on is not None:
            return {"status": "cancelled"}          # 幂等（已撤过）
        self._transition(o, "cancelled")
        o.cancelled_on = self.sim_date
        if o.side == "buy":
            self.cash += o.qty * o.reference_close * (1 + self.fee_rate)   # 解冻
        self._emit("cancel", {"order_id": order_id})
        self._transition(o, "idle")            # cancelled → idle：这一单结束
        return {"status": "cancelled"}

    def advance(self, visible: tuple[str, ...] | None = None) -> dict:
        """**单调单步**：恰好前进一个交易日，不接受目标日期，不可回退。"""
        self._require("advance")
        if self._i + 1 >= len(self.calendar) or self.calendar[self._i + 1] > self.window_end:
            raise SimError(409, "window_exhausted",
                           f"sim_date={self.sim_date} 已到窗口末 {self.window_end}")
        prev = self.sim_date
        self._i += 1
        fills = self._match(prev)
        self._emit("advance", {"from": prev, "to": self.sim_date, "n_fills": len(fills)})
        # 走同一个投影 —— 原先直接 self.state()，把未声明的字段全量吐给 agent
        return {"sim_date": self.sim_date, "fills": fills,
                "state": self.state(visible, _skip_gate=True)}

    def _match(self, submitted_before: str) -> list[dict]:
        """撮合：提交日的**下一交易日**收盘。全成 / 因可交易性零成并记 reject。"""
        fills = []
        for o in list(self.orders.values()):
            if o.state != "ordered" or o.submitted_on > submitted_before:
                continue
            st = self.tradable.get((self.sim_date, o.symbol), "trade")
            key = (self.sim_date, o.symbol)
            if st not in TRADABILITY_STATES:
                # **fail-closed**：不认识的状态拒单，不是放行。
                # 原先写成 `st in (一串我自己造的名字)`，不在表里就放行 —— 而表里
                # 有四个取值根本不存在，等于整条可交易性拦截从来没生效过。
                reason = f"unknown_tradability:{st}"
            elif st in UNTRADABLE_STATES:
                reason = st
            elif key in self.limit_up and o.side == "buy":
                reason = "limit_up"
            elif key in self.limit_down and o.side == "sell":
                reason = "limit_down"
            else:
                reason = None
            if reason is not None:
                self._emit("reject", {"order_id": o.order_id, "reason": reason})
                self._transition(o, "cancelled")
                o.cancelled_on = self.sim_date
                self._transition(o, "idle")
                if o.side == "buy":
                    self.cash += o.qty * o.reference_close * (1 + self.fee_rate)
                continue
            px = self.closes.get((self.sim_date, o.symbol))
            if px is None:
                self._emit("reject", {"order_id": o.order_id, "reason": "no_close"})
                self._transition(o, "cancelled")
                o.cancelled_on = self.sim_date
                self._transition(o, "idle")
                if o.side == "buy":
                    self.cash += o.qty * o.reference_close * (1 + self.fee_rate)
                continue
            o.filled_price, o.filled_on = float(px), self.sim_date
            self._transition(o, "filled")
            pos = self.positions.setdefault(o.symbol, {"shares": 0, "avg_cost": 0.0})
            if o.side == "buy":
                self.cash += o.qty * o.reference_close * (1 + self.fee_rate)      # 解冻
                self.cash -= o.qty * px * (1 + self.fee_rate)                     # 实付
                tot = pos["shares"] + o.qty
                pos["avg_cost"] = (pos["avg_cost"] * pos["shares"] + px * o.qty) / tot if tot else 0.0
                pos["shares"] = tot
                self._locked.setdefault(o.symbol, {})            # T+1：当日买入不可卖
                self._locked[o.symbol][self.sim_date] = \
                    self._locked[o.symbol].get(self.sim_date, 0) + o.qty
            else:
                pos["shares"] -= o.qty
                self.cash += o.qty * px * (1 - self.fee_rate)
            fills.append({"order_id": o.order_id, "symbol": o.symbol, "side": o.side,
                          "qty": o.qty, "price": float(px), "date": self.sim_date})
            self._emit("fill", {"order_id": o.order_id, "symbol": o.symbol, "side": o.side,
                                "qty": o.qty, "price": float(px)})
            self._transition(o, "idle")
        return fills

    # ---------------------------------------------------------- 结算口径

    def slippage_bps(self) -> dict:
        """`Slip = Σ qty × (成交价 − 基准价) / Σ qty`（bps），基准按声明取。

        `slippage_reference_price=close` 时结构性为零（v1 成交就是下一交易日收盘）——
        **这不是 bug，是该取值的真实后果**，实现不许为了让指标好看去改成别的价。
        """
        base_name = self.slippage_base
        num = den = 0.0
        for o in self.orders.values():
            if o.state != "idle" or o.filled_price is None:
                continue
            if base_name == "reference_close":
                base = o.env_reference_close          # **环境侧的价**，不是自报的
            elif base_name == "close":
                base = self.closes.get((o.filled_on, o.symbol))
            else:
                base = self.opens.get((o.filled_on, o.symbol))
            if base is None or base == 0:
                # **fail-closed**：取不到基准价就说不出这个数。
                # 原先静默退回成交价 —— 那会让 open/close 两档坍缩成 0，
                # 而 SIM-F「三档互不相同」只是因为 fixture 一直喂着 opens（红队 2026-09-04）。
                raise SimError(409, "slippage_base_unavailable",
                               f"{o.order_id}: 基准 {base_name} 在 ({o.filled_on}, {o.symbol}) 取不到 —— "
                               f"不静默退回成交价，那会把 Slip 抹成 0 并让三档坍缩")
            num += o.qty * (o.filled_price - base) / base * 10_000
            den += o.qty
        return {"slippage_bps": (num / den) if den else 0.0,
                "basis": base_name, "used_contract_default": self.slippage_base_is_default}

    def fill_rate(self) -> float:
        submitted = len(self.orders)
        filled = sum(1 for o in self.orders.values() if o.filled_price is not None)
        return (filled / submitted) if submitted else 0.0

    def transitions_seen(self) -> set[tuple[str, str]]:
        """本次运行**实际走过**的迁移集（`_transition` 逐条记的）。"""
        return set(self.transitions)


# import 期自检：节点集必须与迁移表一致 —— 抄漏一个状态会在这里当场红
assert ORDER_STATES == {"idle", "ordered", "filled", "cancelled", "partial"}, ORDER_STATES
