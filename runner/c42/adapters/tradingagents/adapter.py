"""TradingAgents 适配器本体。**只做转录与切片。**"""
from __future__ import annotations

import json
from pathlib import Path

import ast
import inspect
import sys
from functools import lru_cache

from runner.c42 import origin as OR
from runner.c42 import upstream_pins as UP
from runner.c42.adapters import base as AB
from runner.c42.adapters.tradingagents import gateway_tools as GT

RESULTS_DIR = "/task/out/tradingagents"

#: **原生数据路径**（实测的模块名，不是猜的）。§11.2 要求整体替换为经网关的实现。
NATIVE_DATA_MODULES: dict[str, str] = {
    "yfinance": "美股行情/基本面/新闻 —— 绕过数据面取数，as-of 强制当场失效",
    "requests": "alpha_vantage / fred / polymarket / reddit / stocktwits 都走它",
    "praw": "Reddit",
}

#: 工具注册表的缝（实测）。替换在这里做，不在 `dataflows/providers.py`（那只是元数据）。
#: **替换缝**（实测）：上游自己的 vendor 注册表，`route_to_vendor` 按它派发。\nTOOL_SEAM = "tradingagents.dataflows.interface:VENDOR_METHODS"


class TradingAgentsAdapter(AB.Adapter):
    key = "tradingagents"
    #: **只有 S5**。它一次只对一个标的、一个日期给一条建议 —— 那是一格信号。
    #: 声明能做 S3/S7 会让「框架做不了这个阶段」变成「它做了但做错了」。
    stages = frozenset({"S5"})

    def declared_outputs(self) -> tuple[str, ...]:
        return (RESULTS_DIR,)

    def config(self, *, llm_provider: str, quick: str, deep: str,
               base_url: str | None = None) -> dict:
        """上游 `DEFAULT_CONFIG` 的键（实测）。三个落盘路径默认在 `/tmp/.tradingagents/`
        下 —— **不在 `/task` 里**，`down -v` 之后就没了（§3.3）。必须全改。

        三个都可由环境变量覆盖：`TRADINGAGENTS_RESULTS_DIR` / `_CACHE_DIR` /
        `_MEMORY_LOG_PATH`（实测 `default_config.py:74-76`）。
        """
        from tradingagents.default_config import DEFAULT_CONFIG
        cfg = dict(DEFAULT_CONFIG)
        cfg.update({
            "results_dir": f"{RESULTS_DIR}/logs",
            "data_cache_dir": f"{RESULTS_DIR}/cache",
            "memory_log_path": f"{RESULTS_DIR}/memory/trading_memory.md",
            "llm_provider": llm_provider, "quick_think_llm": quick,
            "deep_think_llm": deep,
            "max_debate_rounds": 1, "max_risk_discuss_rounds": 1,
        })
        if base_url:
            cfg["backend_url"] = base_url
        return cfg

    @staticmethod
    def env_overrides() -> dict[str, str]:
        """三个落盘路径的环境变量形态 —— 进 compose 的 `environment:`。"""
        return {"TRADINGAGENTS_RESULTS_DIR": f"{RESULTS_DIR}/logs",
                "TRADINGAGENTS_CACHE_DIR": f"{RESULTS_DIR}/cache",
                "TRADINGAGENTS_MEMORY_LOG_PATH":
                    f"{RESULTS_DIR}/memory/trading_memory.md"}

    # ---- §11.2 原生数据源整体替换 ----

    @staticmethod
    def assert_native_paths_replaced(bound_tools) -> None:
        """按**实际绑给 LLM 的工具**扫，不按整个包扫。

        整个包里 `dataflows/yfinance.py` 永远在，扫它必然命中 —— 那种「命中」
        证明不了工具还在用它。判据是：**这次运行绑上去的工具**能不能走到原生数据模块。

        **必须走 import 闭包，不能只看工具模块自己的 import**（2026-09-04 实测教训）：
        上游的工具模块写的是 `from tradingagents.dataflows.yfinance import ...` ——
        顶层模块是 `tradingagents` 不是 `yfinance`。只看直接 import 的第一版扫描器
        对**完全未替换**的十五个原生工具判了「干净」—— 一道恒绿的门，
        而它本来要证明的正是「替换成功了」。非空证明（§14.3 同一条纪律）当场抓到。
        """
        bad: list[str] = []
        for t in bound_tools:
            fn = getattr(t, "func", None) or getattr(t, "coroutine", None) or t
            mod = inspect.getmodule(fn)
            name = getattr(t, "name", None) or getattr(fn, "__name__", str(t))
            if mod is None:
                bad.append(f"{name}: 取不到模块 —— 取不到就不能判它干净")
                continue
            reach = _reachable_modules(mod)
            hit = sorted(reach & set(NATIVE_DATA_MODULES))
            if hit:
                bad.append(f"{name}（{mod.__name__}）→ "
                           + "；".join(f"{h}：{NATIVE_DATA_MODULES[h]}" for h in hit))
        if bad:
            raise AB.AdapterError(
                "绑上去的工具还能走原生数据路径（§11.2）：\n  " + "\n  ".join(bad))

    # ---- 运行 ----

    def run(self, ctx: dict) -> AB.FrameworkRun:
        """跑图。**没有 LLM 凭据时跑不动** —— 那不是可以绕过去的一步。"""
        import tradingagents  # noqa: F401
        UP.assert_upstream_shape(tradingagents, self.key)
        from tradingagents.dataflows import interface as IF
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        cfg = self.config(**ctx["llm"])
        GT.install(IF, cfg)                      # §11.2 整表替换
        GT.assert_only_gateway_vendor(IF)        # 断言落在 route_to_vendor 派发的表上
        GT.reset_pit_hits()
        graph = TradingAgentsGraph(config=cfg)
        state, decision = graph.propagate(ctx["symbol"], ctx["trade_date"],
                                          asset_type=ctx.get("asset_type", "stock"))
        UP.assert_state_keys(state, self.key)
        if not GT.pit_hits():
            raise AB.AdapterError(
                "一次 run 里 PIT 校验一次都没命中 —— 守卫不在线。"
                "整体替换把上游自己那层日期防护一并删掉了，"
                "替换层的那层若也没被调用，前视就无人拦（N-52）")
        return AB.FrameworkRun(
            work_dir=Path(ctx["work_dir"]), stage="S5", task_id=ctx["task_id"],
            config_id=ctx["config_id"], arm=ctx["arm"],
            final_state=dict(state), stdout=str(decision)[:4000])

    # ---- 转录 ----

    def declarations(self, run: AB.FrameworkRun) -> AB.Transcribed:
        """原生产物里**没有 `declarations`**（§18.1）—— 返回空，不编。

        `TradeRecommendation` 里的 `confidence` / `time_horizon_days` 这些**不是**声明：
        它们是框架自己的字段，填进 declarations 就是 harness 代 agent 声明（§4.3 同理）。
        """
        return AB.Transcribed({}, {})

    def payload(self, run: AB.FrameworkRun) -> AB.Transcribed:
        """S5 的 `signals` 只能来自框架**自己写下的**建议。

        它一次只给一个标的一天 —— 一格。凑不满题面要求的面板是**事实**，
        由校验器判 malformed；harness 不替它补格子。
        """
        decision = run.final_state.get("final_trade_decision")
        if not decision:
            return AB.Transcribed({}, {})
        row = {"date": run.final_state.get("trade_date"),
               "symbol": run.final_state.get("company_of_interest"),
               "value": decision}
        return AB.Transcribed({"signals": [row]},
                              {"$.payload.signals": OR.Source.framework_output})


@lru_cache(maxsize=None)
def _reachable_modules(mod) -> frozenset:
    """从一个模块出发，沿**包内** import 边走到底，返回闭包里出现过的顶层模块名。

    只展开与起点同一个顶级包的模块（`tradingagents.*`），外部包只记名字不再下钻 ——
    再下钻会把 pandas 的依赖也拖进来，噪声压过信号。
    """
    root = mod.__name__.split(".")[0]
    seen: set[str] = set()
    tops: set[str] = set()
    stack = [mod.__name__]
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        m = sys.modules.get(name)
        if m is None:
            try:
                import importlib
                m = importlib.import_module(name)
            except Exception:
                continue
        try:
            src = inspect.getsource(m)
            tree = ast.parse(src)
        except (OSError, TypeError, SyntaxError):
            continue
        for node in ast.walk(tree):
            mods = ([a.name for a in node.names] if isinstance(node, ast.Import)
                    else [node.module] if isinstance(node, ast.ImportFrom) and node.module
                    else [])
            for target in mods:
                top = target.split(".")[0]
                tops.add(top)
                if top == root:
                    stack.append(target)
    return frozenset(tops)
