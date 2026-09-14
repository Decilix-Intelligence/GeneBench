# oracle 参考解（数据面私有；在 f01 直跑，经网关 snapshot 后端产 artifact）。gold_token: <<gold_token>>
"""S8-COR-01 委托生命周期（正确性）—— oracle。

**流程**：首个交易日按 `LOT` 买入 N 只 → 推进到窗口末（中间不交易）→
按**可见持仓**清仓 → 再推进一次让卖单成交。

**四条第一版踩过的坑**（都只在真跑时现形，见 `reference/s8_oracle_common` 的表）：
① 端点是 `/sim/*` 不是 `/orders`、`/clock/advance`、`/state`；
② `/sim/order` 的 `reference_close` **必填**；
③ `as_of` 上界 = 当前 `sim_date`，拿 `task.as_of` 去请求会被全面拒（契约 §3.1）；
④ `client_order_id` 必须**确定性** —— `uuid4` 让同一道题两次 gold 的字节不同。

**事件与迁移取自 `/sim/log`**（契约 §4：审计日志是权威），不从各次应答拼。
"""
from __future__ import annotations

import json
from pathlib import Path

# 统一 I/O 契约（D-31）：读标准位置的任务规格、经网关取数、写标准 artifact 路径。
from reference.oracle_io import context as _oracle_context
from reference.oracle_io import write as _oracle_write
from reference.oracle_io import write_private as _write_private

CTX = _oracle_context(__file__)

# 共用主干在 reference/ 下 —— **不 import 兄弟模板**（D-31 推论）
from reference import s8_oracle_common as s8            # noqa: E402
from reference.gateway_client import Client             # noqa: E402

N_SYMBOLS, LOT = 3, 100
#: 持有期（交易日）。取固定值而不是「推到窗口末」—— 见 main() 里的说明。
HOLD_DAYS = 4


def main(task_dir: str, arm: str = "strict") -> None:
    from reference import artifact_schema as sch
    td = Path(task_dir)
    task = s8.load_task(td)
    sim = s8.Sim(Client.for_context(CTX), task)

    picks = sim.universe(N_SYMBOLS)
    for i, sym in enumerate(picks):
        sim.order(symbol=sym, side="buy", qty=LOT,
                  coid=s8.client_order_id(task["task_id"], sym, "buy", i),
                  reference_close=sim.close_on(sym, sim.sim_date))
    sim.advance()                                   # 次日收盘撮合买单（契约 §1）

    for _ in range(HOLD_DAYS):                      # 持有期：只推进，不交易
        sim.advance()

    # 清仓按**可见持仓**做 —— `visible_state_fields` 没声明的字段端点根本不返回。
    #
    # **为什么不是"推到窗口末再卖"**：撮合在**下一交易日**，所以窗口最后一天提交的卖单
    # 永远不可能成交 —— 第一版就是那么写的，`fill_rate` 出来是 0.5，而那个 0.5 是
    # 「策略设计错了」不是「环境撮合率低」。而 oracle 又**不能**先查日历确定哪天是倒数第二天：
    # `/calendar` 的 `end_date` 不得越过 `as_of`，而 `as_of` 上界就是当前 `sim_date`（§3.1）。
    # 拿窗口末日反推 = 用未来信息安排今天的交易，正是 lookahead 探针要抓的。
    # 所以持有期取**固定交易日数**：不需要任何未来信息，且确定性。
    for i, p in enumerate(sim.state().get("positions") or []):
        sym = p["symbol"]
        sim.order(symbol=sym, side="sell", qty=int(p["shares"]),
                  coid=s8.client_order_id(task["task_id"], sym, "sell", i),
                  reference_close=sim.close_on(sym, sim.sim_date))
    sim.advance()                                   # 次日收盘撮合卖单
    n_mid = sim.advance_to_end()                    # 走完窗口

    art = s8.build_artifact(task, sim, arm=arm)
    spec = {k: task[k] for k in ("task_id", "stage", "declared", "underdetermined")}
    v = sch.validate(art, task=spec)
    assert v.ok, [str(f) for f in v.findings]                            # O1
    _oracle_write(CTX, art)
    _write_private(td / "gold" / "oracle_artifact.json", art)
    _write_private(td / "gold" / "session.json", {"sim_date_end": sim.sim_date, "advances_after_first": n_mid,
         "orders": len(sim.orders), "denied": sim.denied})


if __name__ == "__main__":
    main(str(_oracle_context(__file__).task_dir))
