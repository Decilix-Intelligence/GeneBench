# -*- coding: utf-8 -*-
"""StockAgent 接入的入口。

顺序是有讲究的（每一步都踩过）：

  1. `prepare_cwd()` —— **必须在 import 上游之前**。`log/custom_logger.py` 在 import 期
     就 `FileHandler('log/test.txt')`，`record.py` 往 `res/*.xlsx` 写，两个都是相对 CWD。
     容器的 working_dir 是 `/task`（run dir 的 `work/` 本身），落进去就破 P8 文件集封闭。
  2. `install_gemini_trap()` —— `agent.py` 顶层 `import google.generativeai`，
     而那个包**故意不装**（见 glue/seams.py）。
  3. 才 import 上游。
"""
from __future__ import annotations

import json
import os
import pathlib
import random
import sys
import types
from typing import Any

_HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from glue import instruction as I          # noqa: E402
from glue import seams                     # noqa: E402
from glue.market import Factors, Market, pick_codes   # noqa: E402
from glue.signals import Recorder, to_signals         # noqa: E402

TASK = pathlib.Path(os.environ.get("GENEBENCH_TASK_DIR", "/task"))
UPSTREAM = pathlib.Path(os.environ.get("GENEBENCH_SA_UPSTREAM", str(_HERE / "upstream")))
STAGE = "S5"
#: 模拟的两只股票槽位（上游的撮合与 `secretary.check_action` 只认 A / B）。
SLOTS = ("A", "B")


def _sizes() -> tuple[int, int, int]:
    """规模闸。三个数一起决定模型调用量：agents × days × (1 贷款 + sessions 交易 + 1 预测 + 1 发帖)。
    默认 2 × 4 × (1+2+1+1) = 40 次，给格式重试留出余量（每 run 的闸是 100 次）。"""
    return (int(os.environ.get("GENEBENCH_SA_AGENTS", 2)),
            int(os.environ.get("GENEBENCH_SA_DAYS", 4)),
            int(os.environ.get("GENEBENCH_SA_SESSIONS", 2)))


def run(sidecar: Any = None) -> dict:
    scratch = seams.prepare_cwd()
    seams.install_gemini_trap()
    sys.path.insert(0, str(UPSTREAM))

    text = (TASK / "INSTRUCTION.md").read_text(encoding="utf-8")
    as_of = I.as_of(text)
    win_start, win_end = I.window(text)
    universe = I.universe(text)

    import genebench_client as gb
    from genebench_client import emit
    gb.set_as_of(as_of)
    cli = gb.client()

    fields = emit.declaration_fields(STAGE)
    declarations: dict[str, Any] = {k: "unresolved" for k in fields}
    declarations.update(I.declarations(text, fields))

    factors = Factors(TASK / "inputs")
    codes = pick_codes(cli, universe, as_of, factors, len(SLOTS))
    all_days = cli.trading_days(win_start, win_end)
    n_agents, n_days, n_sessions = _sizes()
    days = all_days[-n_days:] if all_days else []
    if not codes or not days:
        raise RuntimeError(f"取不到标的或交易日：codes={codes} days={len(all_days)}")
    slot_of_code = {c: SLOTS[i] for i, c in enumerate(codes)}
    code_of_slot = {v: k for k, v in slot_of_code.items()}

    market = Market(cli, universe=universe, as_of=as_of, start=win_start, end=win_end,
                    codes=codes, days=days)

    import util, stock as stock_mod, secretary as secretary_mod, agent as agent_mod  # noqa: E402
    import main as main_mod                                                          # noqa: E402
    from procoder.prompt import NamedBlock, NamedVariable                            # noqa: E402

    util.AGENTS_NUM, util.TOTAL_DATE, util.TOTAL_SESSION = n_agents, n_days, n_sessions
    if sidecar is None:
        sidecar = seams.Sidecar()
    seams.install_model_seam(agent_mod, secretary_mod, sidecar)
    two_stock = seams.install_two_stock_prompts(agent_mod)

    rec = Recorder()

    def _set_day(d: int) -> None:
        """换日：重建那两个 prompt 块，把当天（含）之前的价量与因子值放进去。
        **只到当天为止** —— 窗口内前视网关看不见，这条线在这里守。"""
        if rec.day == d and getattr(_set_day, "_done", None) == d:
            return
        rec.day = d
        brief = market.brief(days[d - 1], code_of_slot, factors)
        agent_mod.FIRST_DAY_FINANCIAL_REPORT = NamedVariable(
            refname="first_day_financial_prompt",
            name="Market data available to you today", content=brief)
        agent_mod.FIRST_DAY_BACKGROUND_KNOWLEDGE = NamedBlock(
            name="Background of the stocks in this market",
            content=("These are real listed A-share companies, not simulated tickers. "
                     "What you know about them is exactly what is listed in "
                     "{first_day_financial_prompt} — prices, volumes, tradability and the "
                     "research factors provided for this task. No company financial "
                     "statements, news or analyst reports exist in this environment; "
                     "do not invent any."))
        _set_day._done = d  # type: ignore[attr-defined]

    #: 参考价：内生 → 网关来的 PIT 收盘价（见 glue/seams.py 第 3 条）。
    def _get_price(self):
        code = code_of_slot.get(self.name)
        if code is None:
            return self.price
        px = market.last_close_upto(days[rec.day - 1], code)
        return self.price if px is None else float(px)

    stock_mod.Stock.get_price = _get_price

    _plan_stock, _plan_loan = agent_mod.Agent.plan_stock, agent_mod.Agent.plan_loan

    def plan_stock(self, date, time, stock_a, stock_b, a_deals, b_deals):
        _set_day(int(date))
        action = _plan_stock(self, date, time, stock_a, stock_b, a_deals, b_deals)
        rec.note(self.order, time, action if isinstance(action, dict) else {})
        return action

    def plan_loan(self, date, a_price, b_price, forum):
        _set_day(int(date))
        return _plan_loan(self, date, a_price, b_price, forum)

    agent_mod.Agent.plan_stock, agent_mod.Agent.plan_loan = plan_stock, plan_loan

    random.seed(int(os.environ.get("GENEBENCH_SEED", 0)))
    _set_day(1)
    main_mod.simulation(types.SimpleNamespace(
        model=os.environ.get("GENEBENCH_MODEL", "deepseek-chat")))

    signals = to_signals(rec, days=days, slot_of_code=slot_of_code,
                         market=market, factors=factors)
    art = emit.emit_s5(signals=signals, declarations=declarations, as_of=as_of)
    out = art.write(TASK / "artifact.json")

    summary = {"artifact": str(out), "codes": codes, "days": days,
               "cells": len(signals), "decisions": len(rec.rows),
               "llm_calls": getattr(sidecar, "calls", None),
               "llm_stopped_reason": getattr(sidecar, "stopped_reason", None),
               "fundamentals_nodata_traced": market.fundamentals_traced,
               "gateway_requests": len(getattr(cli, "ledger", []) or []),
               "coverage": art["payload"]["coverage"], "scratch": str(scratch), "two_stock_prompts": two_stock}
    (scratch / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
    return summary


def main() -> int:
    s = run()
    print(json.dumps(s, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
