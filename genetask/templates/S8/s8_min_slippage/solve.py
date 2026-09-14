# oracle 参考解（数据面私有；在 f01 直跑，经网关 snapshot 后端产 artifact）。gold_token: <<gold_token>>
"""S8-ECO-01 最小请求数建仓 —— oracle。

ECO 家族量的是**请求经济性**，所以取数要能合并就合并：
`/bars` 的 `code` 是**重复参数、可一次多票**（实测），5 只一次拿完，不是 5 次。

请求预算（本 oracle 实际发出的）：
`/sim/log` 1（建会话并取 `sim_date`）+ `/universe` 1 + `/bars` 1 + `/sim/order` N + `/sim/advance` 1
+ `/sim/state` 1 + `/sim/log` 2（装配 events / transitions 各一次）。

**推进一次即在次日收盘全额撮合**（契约 §1 日频、全成/零成），所以不需要 deadline 循环；
真有未成交的（停牌/涨跌停被拒），`fill_rate` 会如实低于 1，那是数据事实不是缺陷。
"""
from __future__ import annotations

from pathlib import Path

from reference.oracle_io import context as _oracle_context
from reference.oracle_io import write as _oracle_write
from reference.oracle_io import write_private as _write_private

CTX = _oracle_context(__file__)

from reference import s8_oracle_common as s8            # noqa: E402
from reference.gateway_client import Client             # noqa: E402

N_SYMBOLS, LOT = 5, 100


def main(task_dir: str, arm: str = "strict") -> None:
    from reference import artifact_schema as sch
    td = Path(task_dir)
    task = s8.load_task(td)
    sim = s8.Sim(Client.for_context(CTX), task)

    picks = sim.universe(N_SYMBOLS)
    # **一次 /bars 拿全部** —— 五只各取一次是 ECO 家族要扣的那种浪费。
    df = sim.gw.frame("/bars", code=picks, start_date=sim.sim_date,
                      end_date=sim.sim_date, fields="close")
    px = {r.code: float(r.close) for r in df.itertuples()}
    missing = [s for s in picks if s not in px]
    assert not missing, f"/bars 没给出 {missing} 的 close —— 缺价不许用默认值下单"

    for i, sym in enumerate(picks):
        sim.order(symbol=sym, side="buy", qty=LOT,
                  coid=s8.client_order_id(task["task_id"], sym, "buy", i),
                  reference_close=px[sym])
    sim.advance()                                        # 次日收盘撮合

    held = {p["symbol"]: int(p["shares"]) for p in (sim.state().get("positions") or [])}

    art = s8.build_artifact(task, sim, arm=arm)
    spec = {k: task[k] for k in ("task_id", "stage", "declared", "underdetermined")}
    v = sch.validate(art, task=spec)
    assert v.ok, [str(f) for f in v.findings]                            # O1
    _oracle_write(CTX, art)
    _write_private(td / "gold" / "oracle_artifact.json", art)
    _write_private(td / "gold" / "session.json",
                   {"sim_date": sim.sim_date, "picks": picks, "held": held,
                    "gateway_requests": len(sim.gw.ledger),
                    "by_endpoint": {e: sum(1 for x in sim.gw.ledger if x["endpoint"] == e)
                                    for e in sorted({x["endpoint"] for x in sim.gw.ledger})},
                    "denied": sim.denied})


if __name__ == "__main__":
    main(str(_oracle_context(__file__).task_dir))
