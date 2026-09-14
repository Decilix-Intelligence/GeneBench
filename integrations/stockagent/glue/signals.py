# -*- coding: utf-8 -*-
"""把 StockAgent 的**决策**翻成 S5 的一格信号。

翻译规则（README §4.2 逐条对应；这是接入层的选择，不是上游的产出格式）：

    对每个 (模拟日 d, 标的 c)：
      n_total = 当天记录到的全部决策条数（交易员 × 交易时段）
      n_buy   = 其中 action_type=="buy"  且指向 c 的条数
      n_sell  = 其中 action_type=="sell" 且指向 c 的条数
      score   = (n_buy - n_sell) / n_total          ∈ [-1, 1]，越大越看多

    写 null（无观点）：这天这只票 `/tradability` 不可交易或 `no_data`；
                       或题面给的三条因子在这个格子上全空；
                       或当天一条决策都没记录到（系统没给出任何看法）。
    写 flat（主动空仓）：当天有决策，但**每一条都是 `no`** —— 交易员看过之后
                       明确不持有。这是「主动空仓」，不是「无观点」。
    其余写数。

两件刻意没做的事：

1. **score 恰好等于 0 时不改写成 `flat`。** 0 是买卖抵消算出来的一个分数，
   而 `flat` 是「明确不想持有」；题面写着「主动空仓不得写 0」，
   反过来把一个真实的 0 分改写成 flat 同样是在编语义。
2. **凑不满面板不补格子。** 预算只够跑几天几只，那就交几格；
   题面要的是 csi300 × 半年，差额是事实，接入层不替它填。
"""
from __future__ import annotations

from typing import Any


class Recorder:
    """挂在 `Agent.plan_stock` 外面，只记录，不改返回值。"""

    def __init__(self) -> None:
        self.day: int = 1
        self.rows: list[dict[str, Any]] = []

    def note(self, agent_order: int, session: Any, action: dict) -> None:
        self.rows.append({"day": int(self.day), "agent": int(agent_order),
                          "session": session,
                          "action_type": str(action.get("action_type", "no")).lower(),
                          "stock": action.get("stock"),
                          "amount": action.get("amount"),
                          "price": action.get("price")})

    def by_day(self, day: int) -> list[dict[str, Any]]:
        return [r for r in self.rows if r["day"] == day]


def to_signals(rec: Recorder, *, days: list[str], slot_of_code: dict[str, str],
               market, factors) -> list[dict[str, Any]]:
    """`days` 是模拟第 1..N 天对应的**真实交易日**（升序）。"""
    out: list[dict[str, Any]] = []
    for i, date in enumerate(days, start=1):
        decisions = rec.by_day(i)
        n_total = len(decisions)
        for code, slot in sorted(slot_of_code.items()):
            if not market.tradable(date, code) or factors.all_missing(date, code) or n_total == 0:
                out.append({"date": date, "symbol": code, "value": None})
                continue
            if all(d["action_type"] == "no" for d in decisions):
                out.append({"date": date, "symbol": code, "value": "flat"})
                continue
            n_buy = sum(1 for d in decisions
                        if d["action_type"] == "buy" and d["stock"] == slot)
            n_sell = sum(1 for d in decisions
                         if d["action_type"] == "sell" and d["stock"] == slot)
            out.append({"date": date, "symbol": code,
                        "value": round((n_buy - n_sell) / n_total, 6)})
    return out
