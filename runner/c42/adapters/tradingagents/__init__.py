"""TradingAgents 适配层（卡 4.2 §10 / §11.2）。

**实测结论（2026-09-04，在 f02 的 `gb-probe-ta:0.7.0` 容器里跑出来的）**：

* 触网数据入口**只有三处**（AST import 扫描）：`dataflows/yfinance.py`、
  `dataflows/tickers.py`、`dataflows/news.py`（`yfinance` 三处、`feedparser` 一处）。
  没有 finnhub、没有裸 `requests` / `httpx`。替换面比预想小得多。
* **`dataflows/providers.py` 不是替换缝** —— 它只是**元数据**
  （`DataProviderAdapter` 描述 point-in-time 能力），没有任何函数注册表。
  真正的缝是 `agents/utils/tool_registry.py::get_analyst_tools(analyst_type)`：
  它返回绑给 LLM 的 LangChain 工具，工具本体是 `agents/utils/*_tools.py` 里的
  `@tool` 函数，再下钻到 `dataflows/yfinance.py`。
* `AgentState` 的键（实测 14 个，见 `PINS["tradingagents"].required_state_keys`）。
* 入口：`TradingAgentsGraph.propagate(company_name, trade_date, on_message=None,
  on_state=None) -> (AgentState, TradeRecommendation)`。
* **产物目录可配**：`TradingAgentsConfig.results_dir` 默认 `./results`（相对路径，
  §3.3 判违规），`data_cache_dir = results_dir / "data_cache"`。产物文件是
  `results_dir/<ticker>/full_states_log_<ticker>_<date>.json`。配到 `/task` 下即可。
* **口径错配（必须写进主表脚注）**：这是一个**美股、单标的、单日期**的决策框架
  （yfinance ticker + `TradeRecommendation`）。我们的数据面是 **A 股**。
  它天然落 S5（单格信号），落不了 S3（因子）与 S7（回测）。
"""
