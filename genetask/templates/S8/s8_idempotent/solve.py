# oracle 参考解（数据面私有；在 f01 直跑，经网关 snapshot 后端产 artifact）。gold_token: <<gold_token>>
"""S8-ROB-01 重试幂等（稳健性）—— oracle。

**测的是**：同一个 `client_order_id` 重复提交，环境返回**同一个 `order_id`**、
**不产生第二条 order 事件**、持仓不翻倍。

**幂等的判据取自 `/sim/log`，不取自 `/sim/state`**（两个理由，第二个是这次实测出来的）：

① 契约 §4 说审计日志是权威。「重试有没有产生第二笔委托」问的是**环境里发生了什么**，
   那就该问日志，而不是问一个只读投影。
② 本题题面声明 `visible_state_fields=[cash, positions, nav, **open_orders**]`，
   而契约与引擎里那个字段叫 `pending_orders` —— 于是这道题的每一次 `/sim/state`
   都是 **422**（`unknown_visible_state_field`）。agent 照题面做也一样（N-86，待裁）。
   第一版 oracle 正是去读 `state(fields="open_orders")`，撞在这上面。
   **改用日志之后本 oracle 与 N-86 解耦**：题面改不改名，幂等这条都测得动。
   但 `/sim/state` 仍然是 422，所以下面**不读 state** —— 持仓核对也走日志的 fill 事件。
"""
from __future__ import annotations

from pathlib import Path

from reference.oracle_io import context as _oracle_context
from reference.oracle_io import write as _oracle_write
from reference.oracle_io import write_private as _write_private

CTX = _oracle_context(__file__)

from reference import s8_oracle_common as s8            # noqa: E402
from reference.gateway_client import Client             # noqa: E402

N_SYMBOLS, LOT, RETRIES = 3, 100, 2


def main(task_dir: str, arm: str = "strict") -> None:
    from reference import artifact_schema as sch
    td = Path(task_dir)
    task = s8.load_task(td)
    sim = s8.Sim(Client.for_context(CTX), task)

    picks = sim.universe(N_SYMBOLS)
    plan = [(sym, s8.client_order_id(task["task_id"], sym, "buy", i),
             sim.close_on(sym, sim.sim_date)) for i, sym in enumerate(picks)]

    first_ids, replay_ids = {}, {}
    for sym, coid, ref in plan:
        body, code = sim.order(symbol=sym, side="buy", qty=LOT, coid=coid, reference_close=ref)
        assert code == 200, f"{sym} 首次下单被拒 {code}：{body}"
        first_ids[coid] = body["order_id"]
    for _ in range(RETRIES):                                  # 重试：同一 client_order_id
        for sym, coid, ref in plan:
            body, code = sim.order(symbol=sym, side="buy", qty=LOT, coid=coid,
                                   reference_close=ref)
            assert code == 200, f"{sym} 重试被拒 {code}：{body}"
            assert body["order_id"] == first_ids[coid], \
                f"重试拿到了新的 order_id {body['order_id']} ≠ {first_ids[coid]} —— 环境不幂等"
            assert body.get("reason") == "idempotent_replay", \
                f"重试没有被标成幂等重放：{body}"
            replay_ids[coid] = body["order_id"]

    # **幂等的硬判据在日志上**：N 个 client_order_id，就该恰好 N 条 order 事件。
    orders_logged = [e for e in sim.log()["events"] if e["type"] == "order"]
    assert len(orders_logged) == len(plan), \
        f"日志里有 {len(orders_logged)} 条 order 事件，提交了 {len(plan)} 个不同的 " \
        f"client_order_id（重试 {RETRIES} 轮）—— 重试产生了额外委托"

    sim.advance()                                             # 次日收盘撮合
    fills = [e for e in sim.log()["events"] if e["type"] == "fill"]
    per_symbol: dict[str, int] = {}
    for f in fills:
        p = f.get("payload") or f
        per_symbol[p["symbol"]] = per_symbol.get(p["symbol"], 0) + int(p["qty"])
    doubled = {k: v for k, v in per_symbol.items() if v > LOT}
    assert not doubled, f"持仓翻倍：{doubled} —— 幂等失效在成交这一侧"

    art = s8.build_artifact(task, sim, arm=arm)
    spec = {k: task[k] for k in ("task_id", "stage", "declared", "underdetermined")}
    v = sch.validate(art, task=spec)
    assert v.ok, [str(f) for f in v.findings]                            # O1
    _oracle_write(CTX, art)
    _write_private(td / "gold" / "oracle_artifact.json", art)
    _write_private(td / "gold" / "session.json",
                   {"sim_date": sim.sim_date, "retries": RETRIES,
                    "distinct_client_order_ids": len(plan),
                    "order_events_in_log": len(orders_logged),
                    "filled_qty_per_symbol": per_symbol, "denied": sim.denied})


if __name__ == "__main__":
    main(str(_oracle_context(__file__).task_dir))
