# -*- coding: utf-8 -*-
"""S8 四道题共用的 oracle 主干（D-31：模板不许 import 兄弟模板）。

**S8 与其余七个阶段的结构差别**：它是唯一一个 agent 与环境**有状态交互**的阶段，
而且网关的 `as_of` 上界与模拟时钟耦合 —— 契约 §3.1：

> 本次运行内网关的 `as_of` 上界 = 当前 `sim_date`；**推进之后 `as_of` 才前移**。

所以 S8 的取数**不能用 `task.as_of`**（那是冻结线那天）。拿它去请求会被
`asof_beyond_freeze_line` 全面拒掉 —— 2026-09-05 实测，第一版四个模板全部撞在这上面。
本主干让 `as_of` 跟着 `sim_date` 走：初值取题面的 `window.start`（**从 task.yaml 读得出来**，
不从环境拿，D-32），之后每次 `/sim/advance` 的回包里带新的 `sim_date`，就地更新。

**第一版四个模板的端点全是错的**（都是真跑才现形）：

| 模板写的 | 实际 | 说明 |
| --- | --- | --- |
| `POST /orders` | `POST /sim/order` | 且 **`reference_close` 是必填**，四个模板一个都没带 |
| `POST /clock/advance` | `POST /sim/advance` | **不接受任何 body 键**，带了就 422 |
| `GET /state?fields=…` | `GET /sim/state` | **没有 `fields` 参数**：可见字段由题面 `visible_state_fields` 决定 |
| `r["ts"]` / `r["date"]` | 都不存在 | `/sim/order` 只回 `{order_id,status,reason}`；`/sim/advance` 回 `{sim_date,fills,state}` |
| `uuid.uuid4()` 当 `client_order_id` | 必须**确定性** | 随机 id ⇒ 同一道题两次 gold 的字节不同，可比性直接没了 |

**事件与迁移取自 `/sim/log`，不取自各次应答**（契约 §4：审计日志是权威）。
从应答拼时间轴，等于让被测方的输入决定"环境发生了什么"。
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

from reference.gateway_client import Client

#: `artifact_schema.PAYLOAD_SHAPE["S8"]` 允许的事件类型。引擎还会发 `advance` 与 `reject`，
#: 它们不在这个枚举里 —— `reject` 折成一条 `state`（该委托被打回 idle），
#: `advance` 不进 events（时间轴由 `sim_date` 承载，且它不是委托生命周期事件）。
EVENT_TYPES = ("order", "fill", "cancel", "state")

#: 引擎 `_transition()` 实际走的迁移（`reference.artifact_schema.LEGAL_TRANSITIONS` 的子集）。
FILL_PATH = (("ordered", "filled"), ("filled", "idle"))
KILL_PATH = (("ordered", "cancelled"), ("cancelled", "idle"))


def load_task(task_dir: Path) -> dict:
    return yaml.safe_load((task_dir / "task.yaml").read_text(encoding="utf-8"))


def client_order_id(task_id: str, symbol: str, side: str, seq: int) -> str:
    """**确定性**的 `client_order_id`。

    第一版用 `uuid.uuid4()` —— 同一道题跑两次，gold 的字节就不同，
    而"两次 gold 的 sha 不同"是可比性的直接否定（N-44 记过同形态）。
    幂等也靠它：`/sim/order` 按 `client_order_id` 幂等，随机 id 等于每次都是新委托。
    """
    return f"{task_id}-{symbol.replace('.', '')}-{side}-{seq:03d}"


@dataclass
class Sim:
    """一次 S8 会话。**`as_of` 跟着 `sim_date` 走**（契约 §3.1）。"""

    gw: Client
    task: dict
    denied: int = 0
    sim_date: str = ""
    #: 本地委托台账：`order_id → {symbol, side, qty, reference_close, filled, notional}`
    orders: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        # 初值取题面的窗口起点：它 ≤ 引擎的第一个交易日，所以一定不越上界；
        # 真正的 `sim_date` 由第一次 `/sim/log` 给出（`log` 不受 permitted_operations 管）。
        self.gw.as_of = str(self.task["window"]["start"])
        self.sim_date = self.log()["sim_date"]
        self.gw.as_of = self.sim_date

    # ------------------------------------------------------------ 端点
    def _count(self, code: int) -> None:
        if code == 403:
            self.denied += 1

    def log(self) -> dict:
        body, _ts, code = self.gw.get_json("/sim/log")
        self._count(code)
        if code != 200:
            raise RuntimeError(f"/sim/log 返回 {code}：{str(body)[:200]}")
        return body

    def state(self) -> dict:
        body, _ts, code = self.gw.get_json("/sim/state")
        self._count(code)
        if code != 200:
            raise RuntimeError(f"/sim/state 返回 {code}：{str(body)[:200]}")
        return body

    def order(self, *, symbol: str, side: str, qty: int, coid: str,
              reference_close: float) -> tuple[dict, int]:
        """`reference_close` **必填**（契约 §2）：它是**提交时价的记录**，
        与 Slip 基准取哪一个是两回事。环境另存自己那份 `env_reference_close`，
        Slip 用环境那份 —— 自报的数被测方完全可控。"""
        body, code = self.gw.post_json("/sim/order", {
            "symbol": symbol, "side": side, "qty": int(qty),
            "client_order_id": coid, "reference_close": float(reference_close)})
        self._count(code)
        if code == 200 and body.get("reason") != "idempotent_replay":
            self.orders[body["order_id"]] = {
                "symbol": symbol, "side": side, "qty": int(qty),
                "reference_close": float(reference_close), "filled": 0, "notional": 0.0}
        return body, code

    def cancel(self, order_id: str) -> tuple[dict, int]:
        body, code = self.gw.post_json("/sim/cancel", {"order_id": order_id})
        self._count(code)
        return body, code

    def advance(self) -> dict:
        """**不带任何 body 键** —— 端点收到就 422（「收不到参数，就没有可以违反的规则」）。"""
        body, code = self.gw.post_json("/sim/advance", {})
        self._count(code)
        if code != 200:
            raise RuntimeError(f"/sim/advance 返回 {code}：{str(body)[:200]}")
        self.sim_date = body["sim_date"]
        self.gw.as_of = self.sim_date               # §3.1：推进之后上界才前移
        for f in body.get("fills") or []:
            o = self.orders.get(f["order_id"])
            if o is not None:
                o["filled"] += int(f["qty"])
                o["notional"] += float(f["qty"]) * float(f["price"])
        return body

    def advance_to_end(self, *, max_steps: int = 400) -> int:
        """推到窗口末。**窗口耗尽时引擎抛 409**，那是正常终止不是错误。"""
        n = 0
        while n < max_steps:
            body, code = self.gw.post_json("/sim/advance", {})
            self._count(code)
            if code == 409:
                return n
            if code != 200:
                raise RuntimeError(f"/sim/advance 返回 {code}：{str(body)[:200]}")
            self.sim_date = body["sim_date"]
            self.gw.as_of = self.sim_date
            for f in body.get("fills") or []:
                o = self.orders.get(f["order_id"])
                if o is not None:
                    o["filled"] += int(f["qty"])
                    o["notional"] += float(f["qty"]) * float(f["price"])
            n += 1
        raise RuntimeError(f"推进了 {max_steps} 次还没到窗口末 —— 窗口不该这么长")

    # ------------------------------------------------------------ 取数
    def close_on(self, symbol: str, date: str) -> float:
        """决策时点价 = 当日收盘（`fields` 显式传，缺省会被反推成读全表）。"""
        df = self.gw.frame("/bars", code=[symbol], start_date=date, end_date=date,
                           fields="close")
        if df.empty or "close" not in df.columns:
            raise RuntimeError(f"/bars 在 {date} 没给出 {symbol} 的 close")
        return float(df["close"].iloc[-1])

    def universe(self, n: int) -> list[str]:
        return self.gw.members(self.task["universe"], self.sim_date)[:n]


# ---------------------------------------------------------------- 产物装配
def events_from_log(log_events: list[dict]) -> list[dict]:
    """审计日志 → artifact 的 `events`（契约 §4：**日志是权威**）。

    `reject` 折成一条 `state`（委托被打回 idle）；`advance` 不进 ——
    它不是委托生命周期事件，时间轴由 `sim_date` 承载。
    """
    out: list[dict] = []
    for e in log_events:
        t, p = e["type"], dict(e.get("payload") or {})
        if t in ("order", "fill", "cancel"):
            out.append({"ts": e["ts"], "type": t, **p})
        elif t == "reject":
            out.append({"ts": e["ts"], "type": "state", "state": "idle", **p})
    return out


def transitions_from_log(log_events: list[dict]) -> list[dict]:
    """审计日志 → `state_transitions`。与引擎 `_transition()` 实际走的路径一致。"""
    out: list[dict] = []
    for e in log_events:
        t, p = e["type"], dict(e.get("payload") or {})
        oid = p.get("order_id")
        if t == "order":
            out.append({"from": "idle", "to": "ordered", "order_id": oid})
        elif t == "fill":
            out += [{"from": a, "to": b, "order_id": oid} for a, b in FILL_PATH]
        elif t in ("cancel", "reject"):
            out += [{"from": a, "to": b, "order_id": oid} for a, b in KILL_PATH]
    return out


def fill_metrics(orders: dict) -> dict:
    """`fill_rate` 与 `slippage_bps`（量加权，**不按买卖翻符号**）。

    符号约定（N-383，2026-09-10 裁定）：`Slip = 量加权(成交价 − 计价基准) bps`，
    成交价高于基准取正、低于取负，**买卖同向**。此前这里乘了一个
    `sign = +1 买 / −1 卖`，于是卖单的滑点与题面写的方向相反 ——
    三处规格与实现里只有这一处翻了符号：

    * `ops/specs/GeneBench指标规格_v1.md` §3：`Slip = 量加权(成交价 − 决策时点价) bps`（不翻）
    * `gateway/sim_engine.py::slippage_bps`：`qty × (成交价 − 基准) / 基准 × 1e4`（不翻）
    * S8 五道题两臂题面（N-127 落的那一行）：
      「成交价高于计价基准时取正，低于计价基准时取负」（不翻）

    以规格 §3 为准把 sign 删掉。**后果**：卖单参与的那几题 gold 的 `slippage_bps`
    要重出（r1.0.21 随之推版），本次改动之前的 S8 产物按旧口径算的数与新 gold 不可比。

    基准取**提交时报给环境的 `reference_close`** —— 已发布四道题
    `slippage_reference_price` 全部声明 `reference_close`。
    换成 `close`/`open` 要改这里，而 `config` 里那个声明就是开关。
    """
    ordered = sum(o["qty"] for o in orders.values())
    filled = sum(o["filled"] for o in orders.values())
    num = 0.0
    for o in orders.values():
        if not o["filled"]:
            continue
        avg = o["notional"] / o["filled"]
        # **不乘 side 符号**（N-383）：方向由「成交价 − 基准」自己决定，与买卖无关。
        num += (avg - o["reference_close"]) / o["reference_close"] * 1e4 * o["filled"]
    return {"fill_rate": (filled / ordered) if ordered else 0.0,
            "slippage_bps": (num / filled) if filled else 0.0}


def build_artifact(task: dict, sim: Sim, *, arm: str = "strict",
                   extra_events: list[dict] | None = None) -> dict:
    """信封 + payload。**声明段一字不改地抄题面**（D-32：题面读得出来的不从别处拿）。"""
    events = events_from_log(sim.log()["events"]) + list(extra_events or [])
    return {
        "schema_version": "1.0", "artifact_id": f"{task['task_id']}-oracle-{arm}",
        "stage": "S8", "task_id": task["task_id"], "config_id": "oracle", "arm": arm,
        "seed": 0, "as_of": task["as_of"],
        "produced_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "provenance": [], "declarations": deepcopy(task["declared"]),
        "payload": {
            "events": sorted(events, key=lambda e: (e["ts"], e["type"])),
            "state_transitions": transitions_from_log(sim.log()["events"]),
            "fills": fill_metrics(sim.orders),
            # **自报值**。契约 §6 说越权率由**网关日志**结算，不采信这一栏；
            # 它进 payload 是为了让"自报与实测不一致"本身成为可观测的（三核的一角）。
            "overreach": {"denied_requests": sim.denied},
        },
    }
