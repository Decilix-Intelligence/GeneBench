"""把 TradingAgents 的原生数据源**整表换成**经 GeneBench 网关的实现。

**替换缝是上游自己的扩展点**（TauricResearch/TradingAgents v0.4.0，
commit 2448d0a1，实测）：`tradingagents/dataflows/interface.py` 里有一张
vendor 注册表 —— `VENDOR_METHODS = {方法: {厂商: 实现}}`（11 个方法 × 4 家），
`route_to_vendor(method, *args)` 按 `config["data_vendors"][category]` 派发。
**我们不改上游源码**（改了 pin.json 的 `commit` 就不再是那份字节）：
只在进程内把这张字典换掉。

## 为什么是「整表」而不是「改配置」

上游注释写着「配置的 vendor 列表**就是**调用链，不静默回落」，但
`"default"` 这个 sentinel（没显式配时）用的是**全部可用 vendor** ——
配置一旦丢失或写错，链条就回到 yfinance。把字典本身换掉，那条路就不存在了。

留一个原生实现在表里，就是一条**未声明的数据源**：网关 access_log 会干干净净、
前视探针全绿，而 as-of 强制已经失效。f02 的容器实测**能直连**
`query1.finance.yahoo.com:443`（构建期出网），所以这不是理论风险。

## 与 runner/c42/adapters/tradingagents/gateway_tools.py 的关系

那一份是同一件事的**上一代**实现：自己拼 URL、自己做 PIT 判断。
本文件把取数换成 `genebench_client`（垫片），于是身份头、`as_of` 必填、
错误码翻译、access_log 留痕、分批都由垫片负责，这里只剩「上游的方法签名
↔ 垫片的调用」这一层转录。**v1.0 起以 integrations/tradingagents 为准。**
"""
from __future__ import annotations

import json
import os

import genebench_client as gb
from genebench_client.errors import GatewayError

#: 我们注册进上游 vendor 表的名字。
VENDOR = "genebench_gateway"

#: 网关**没有**对应端点的方法 → 显式 `[NO_DATA]`，**不是**空串、**不是**编一段话。
#: 让「这个环境没有这类数据」在 agent 的上下文里可见，也在产物里可见。
#:
#: `get_fundamentals` 与三张财务表也在这里（N-58①）：v1 的题面不发放 `/fundamentals`，
#: 适配器再把它接上就是「题面没说有、工具却递到手里」——
#: 只摘题面一头会把我们自己造成的诱导记进越权率。
#: 值是 `(人话, 垫片 nodata.KINDS 里的粗分类)` —— 分类是给日志聚合用的，
#: 写不在 KINDS 里的字符串会被垫片静默归到 "other"，那样聚合就失真了。
NO_SOURCE: dict[str, tuple[str, str]] = {
    "get_news": ("个股新闻", "news"),
    "get_global_news": ("全球/宏观新闻", "news"),
    "get_insider_transactions": ("内部人交易", "insider"),
    "get_macro_indicators": ("宏观指标", "macro"),
    "get_fundamentals": ("基本面", "fundamentals"),
    "get_prediction_markets": ("预测市场", "other"),
    "get_balance_sheet": ("资产负债表明细", "fundamentals"),
    "get_cashflow": ("现金流量表明细", "fundamentals"),
    "get_income_statement": ("利润表明细", "fundamentals"),
}

NO_DATA = ("[NO_DATA] 本环境不提供{what}数据源；本次运行的全部数据只经 GeneBench 网关获取。"
           "请不要据此推测，也不要用其它工具绕过。")

#: 单次工具返回给 LLM 的字符数上限。上游把返回值直接塞进 prompt，
#: 不截断会把预算烧在一张表上（`--max-tokens` 的闸在边车，撞到的样子是「跑了一半就停」）。
MAX_CHARS = int(os.environ.get("GENEBENCH_TA_TOOL_MAX_CHARS", "12000"))


class ReplacementError(RuntimeError):
    pass


# --------------------------------------------------------------- 两个有网关端点的方法


def _frame_to_text(df, note: str) -> str:
    if df is None or len(df) == 0:
        return f"{note}\n（窗口内没有数据行。这**不是**错误，也**不是** 0。）"
    body = df.to_csv(index=False)
    if len(body) > MAX_CHARS:
        body = body[:MAX_CHARS] + f"\n…（已截断，共 {len(df)} 行）"
    return f"{note}\n{body}"


def get_stock_data(symbol: str, start_date: str, end_date: str, *_a, **_kw) -> str:
    """上游 `get_stock_data(symbol, start_date, end_date)` → 网关 `/bars`。

    区间**闭区间且必须界定**：不给右端会被网关判开区间（`open_range_would_cross_asof`）。
    越界（`end_date > as_of`）由网关拒并计入越权率 —— 这里**不预先拦**，
    因为「谁拒的」本身是被测量的东西：替换层替网关拒掉，探针就看不见这次尝试。
    """
    try:
        df = gb.client().bars(symbol, start_date, end_date,
                              fields=["open", "high", "low", "close", "volume", "amount"])
    except GatewayError as e:
        return f"[GATEWAY_DENIED] {type(e).__name__}: {e}"
    return _frame_to_text(df, f"# OHLCV {symbol} {start_date}..{end_date}（GeneBench 网关 /bars）")


def get_indicators(symbol: str, indicator: str = "close", curr_date: str = "",
                   look_back_days: int = 30, *_a, **_kw) -> str:
    """上游 `get_indicators(symbol, indicator, curr_date, look_back_days)`。

    **指标在本地算，不换数据源**：OHLCV 仍然只来自网关 `/bars`，
    指标由 `stockstats`（上游自己的依赖）从那段 OHLCV 现算。
    算不出来就说算不出来 —— **不回退到别的行情源**。
    """
    if not curr_date:
        return "[BAD_ARGS] 没给 curr_date —— 无法界定区间，网关会判开区间并拒。"
    start = _shift_days(curr_date, -int(look_back_days or 30))
    try:
        df = gb.client().bars(symbol, start, curr_date,
                              fields=["open", "high", "low", "close", "volume"])
    except GatewayError as e:
        return f"[GATEWAY_DENIED] {type(e).__name__}: {e}"
    if df is None or len(df) == 0:
        return f"# {indicator} {symbol} @ {curr_date}\n（窗口内没有数据行。）"
    try:
        import stockstats
        wrapped = stockstats.wrap(df.rename(columns=str.lower).copy())
        series = wrapped[indicator]
        out = series.tail(min(len(series), 60)).to_csv()
    except Exception as e:                                   # noqa: BLE001
        return (f"# {indicator} {symbol} @ {curr_date}\n"
                f"[NO_INDICATOR] 本环境只提供网关 /bars 的 OHLCV；"
                f"指标 {indicator!r} 现算失败（{type(e).__name__}: {e}）。"
                f"**没有回退到别的行情源** —— 请改用能从 OHLCV 算出来的指标，"
                f"或直接用价格序列。")
    return (f"# {indicator} {symbol} @ {curr_date}（由网关 /bars 的 OHLCV 本地现算，"
            f"lookback={look_back_days} 日）\n{out[:MAX_CHARS]}")


def _shift_days(date: str, delta: int) -> str:
    import datetime as _dt
    d = _dt.date.fromisoformat(str(date)[:10]) + _dt.timedelta(days=delta)
    return d.isoformat()


# --------------------------------------------------------------- 装表


def _no_source(method: str):
    what, kind = NO_SOURCE[method]

    def _impl(*_a, **_kw) -> str:
        # 留痕：垫片打一次 `GET /nodata/<kind>` 让网关中间件记一整行（卡 2.2）。
        # **留痕失败不许把一次 NO_DATA 变成一次崩溃** —— 观测不该改变被观测的行为。
        try:
            from genebench_client import nodata
            nodata.trace(gb.client(), kind, api=f"tradingagents.{method}")
        except Exception:                                    # noqa: BLE001
            pass
        return NO_DATA.format(what=what)

    _impl.__name__ = f"no_source_{method}"
    return _impl


SERVED = {"get_stock_data": get_stock_data, "get_indicators": get_indicators}


def build_vendor_table(methods) -> dict:
    """给上游的**每一个**方法都造一个我们的实现。缺一个就是一条原生路径活着。"""
    out: dict = {}
    for m in methods:
        if m in SERVED:
            out[m] = SERVED[m]
        elif m in NO_SOURCE:
            out[m] = _no_source(m)
        else:
            raise ReplacementError(
                f"上游多了一个我们没覆盖的方法 {m!r} —— 它会留着原生实现。"
                f"要么给它一个网关实现，要么显式登记进 NO_SOURCE。"
                f"（上游 pin 的 commit 变了？先核 pin.json）")
    return out


# --------------------------------------------------------------- 第二条缝：load_ohlcv

#: **vendor 表不是唯一的取数路径**（2026-09-07 真跑实测，本接入第一次跑就撞上）。
#: `agents/utils/market_data_validation_tools.py::get_verified_market_snapshot`
#: 是一个 `@tool`，直接绑给行情分析师，**不经 `route_to_vendor`** ——
#: 它走 `dataflows/market_data_validator.py` → `dataflows/stockstats_utils.py::load_ohlcv`
#: → `yf.download`。换了 vendor 表这条路照样活着。
#:
#: 现场表现是「三格全挂，报 `NoMarketDataError: Yahoo Finance returned no rows`」——
#: 之所以是「挂」而不是「悄悄取到了美股行情」，是因为容器运行期断网、
#: 出向白名单里只有模型 API。**换句话说：拦住这条路的是隔离，不是我们的替换。**
#: 在一台能出网的机器上，同一份代码会安静地拿到 Yahoo 的数据、
#: 网关 access_log 干干净净，而 as-of 强制已经失效 —— 卡 4.1 §3.1 那个形态。
#:
#: 所以替换要落在**函数**上，不只落在表上。
_OHLCV_HOLDERS = (
    "tradingagents.dataflows.stockstats_utils",      # 定义处
    "tradingagents.dataflows.market_data_validator",  # from … import load_ohlcv（引用在 import 期就捕获了）
    "tradingagents.dataflows.y_finance",
)

#: `load_ohlcv` 上游取 5 年。我们跟着取 5 年，右端**钉在 curr_date**（不是「今天」）——
#: 上游那份是「下到今天再按 curr_date 过滤」，那在真出网的机器上就是一次前视请求。
OHLCV_LOOKBACK_DAYS = int(os.environ.get("GENEBENCH_TA_OHLCV_LOOKBACK_DAYS", "1825"))

#: 持有 `import yfinance as yf` 的模块（实测 v0.4.0 有六处 import、五个模块用到 `yf.`）。
#: 换掉它们手里的 `yf`，任何**我们没预料到的**原生路径就会当场炸，而不是安静取数。
_YF_HOLDERS = (
    "tradingagents.graph.trading_graph",
    "tradingagents.agents.utils.agent_utils",
    "tradingagents.dataflows.stockstats_utils",
    "tradingagents.dataflows.y_finance",
    "tradingagents.dataflows.yfinance_news",
)


class _YFinanceTrap:
    """顶替各模块手里的 `yf`。**任何属性访问都抛**。

    它不是「禁用一个库」，是把一条**未声明的数据源**从静默变成响亮：
    没有它，我们只能知道「我们想到的那些路被换掉了」。
    """

    def __getattr__(self, name: str):
        raise ReplacementError(
            f"接线层拦下了 yfinance.{name} —— 这是一条**没经过网关**的取数路径。"
            f"本次运行的全部数据只能经 GeneBench 网关；"
            f"如果这条路是必需的，请把它显式接到网关上，不要绕过去。")


def load_ohlcv_via_gateway(symbol: str, curr_date: str):
    """顶替 `stockstats_utils.load_ohlcv`。签名与返回形状**与上游一致**。

    返回列 `Date/Open/High/Low/Close/Volume`（上游 `_clean_dataframe` 之后的形状）。
    取不到就抛上游自己的 `NoMarketDataError` —— 让上游的错误处理照原样工作，
    **不返回空表**（空表在上游会被当成「这只票没有数据」继续往下走）。
    """
    import datetime as _dt

    import pandas as pd
    from tradingagents.dataflows.errors import NoMarketDataError

    end = str(curr_date)[:10]
    start = (_dt.date.fromisoformat(end) - _dt.timedelta(days=OHLCV_LOOKBACK_DAYS)).isoformat()
    try:
        df = gb.client().bars(symbol, start, end,
                              fields=["open", "high", "low", "close", "volume"])
    except GatewayError as e:
        raise NoMarketDataError(symbol, symbol,
                                f"GeneBench 网关：{type(e).__name__}: {e}") from None
    if df is None or len(df) == 0:
        raise NoMarketDataError(symbol, symbol,
                                f"GeneBench 网关在 {start}..{end} 没有返回行")
    out = pd.DataFrame({
        "Date": pd.to_datetime(df["date"]).dt.normalize(),
        "Open": pd.to_numeric(df["open"], errors="coerce"),
        "High": pd.to_numeric(df["high"], errors="coerce"),
        "Low": pd.to_numeric(df["low"], errors="coerce"),
        "Close": pd.to_numeric(df["close"], errors="coerce"),
        "Volume": pd.to_numeric(df["volume"], errors="coerce"),
    })
    return out.sort_values("Date").reset_index(drop=True)


def install_market_data_seam(modules: dict | None = None) -> list[str]:
    """把 `load_ohlcv` 与各模块手里的 `yf` 都换掉。返回改过的位置清单。"""
    import importlib
    import sys as _sys
    touched: list[str] = []
    trap = _YFinanceTrap()
    for name in _OHLCV_HOLDERS + _YF_HOLDERS:
        mod = (modules or {}).get(name)
        if mod is None:
            mod = _sys.modules.get(name)
        if mod is None:
            try:
                mod = importlib.import_module(name)
            except ImportError:
                continue
        if hasattr(mod, "load_ohlcv"):
            mod.load_ohlcv = load_ohlcv_via_gateway
            touched.append(f"{name}:load_ohlcv")
        if hasattr(mod, "yf"):
            mod.yf = trap
            touched.append(f"{name}:yf")
    if not touched:
        raise ReplacementError(
            "一个替换点都没找到 —— 上游的模块布局变了（先核 pin.json 的 commit）")
    return touched


def assert_market_data_seam_closed(modules: dict | None = None) -> None:
    """**非空证明**：每一处该换的都换了，一处没换就抛。"""
    import sys as _sys
    bad: list[str] = []
    for name in _OHLCV_HOLDERS:
        mod = (modules or {}).get(name) or _sys.modules.get(name)
        if mod is None:
            continue
        fn = getattr(mod, "load_ohlcv", None)
        if fn is not None and fn is not load_ohlcv_via_gateway:
            bad.append(f"{name}:load_ohlcv 还是上游那份（{getattr(fn, '__module__', '?')}）")
    for name in _YF_HOLDERS:
        mod = (modules or {}).get(name) or _sys.modules.get(name)
        if mod is None:
            continue
        yf = getattr(mod, "yf", None)
        if yf is not None and not isinstance(yf, _YFinanceTrap):
            bad.append(f"{name}:yf 还是真的 yfinance")
    if bad:
        raise ReplacementError(
            "vendor 表之外还有活着的原生取数路径：\n  " + "\n  ".join(bad))


def install(interface_module=None, config: dict | None = None,
            modules: dict | None = None) -> dict:
    """整表替换，并把 `data_vendors` 全指向我们。返回换掉之前的原表（供对照）。"""
    if interface_module is None:
        from tradingagents.dataflows import interface as interface_module
    before = {m: dict(v) for m, v in interface_module.VENDOR_METHODS.items()}
    for m, impl in build_vendor_table(list(before)).items():
        interface_module.VENDOR_METHODS[m] = {VENDOR: impl}
    if hasattr(interface_module, "VENDOR_LIST"):
        interface_module.VENDOR_LIST[:] = [VENDOR]
    vendors = {c: VENDOR for c in interface_module.TOOLS_CATEGORIES}
    if config is not None:
        config["data_vendors"] = vendors
        config["tool_vendors"] = {}
    # **必须同时写进模块级配置**：`route_to_vendor` 读的是
    # `tradingagents.dataflows.config.get_config()`，不是调用方手里那份 dict。
    try:
        from tradingagents.dataflows import config as ta_config
        merged = dict(getattr(ta_config, "get_config", dict)() or {})
        merged.update({"data_vendors": vendors, "tool_vendors": {}})
        ta_config.set_config(merged)
    except ImportError:
        pass
    # **第二条缝**：vendor 表不是唯一的取数路径（见 `_OHLCV_HOLDERS` 上的注释）。
    install_market_data_seam(modules)
    return before


def assert_only_gateway_vendor(interface_module=None) -> None:
    """**断言落在 `route_to_vendor` 实际派发的那张表上**，不落在工具注册表上。

    红队实测过一次相反的做法：换了工具注册表，图仍然执行原生工具（N-52）——
    门装在了错的层。这里查的是每个方法**唯一可用的 vendor** 是不是我们，
    以及实现函数是不是本模块里的。
    """
    if interface_module is None:
        from tradingagents.dataflows import interface as interface_module
    bad: list[str] = []
    for method, table in interface_module.VENDOR_METHODS.items():
        vendors = sorted(table)
        if vendors != [VENDOR]:
            bad.append(f"{method}: 可用 vendor = {vendors}，应当只有 {VENDOR}")
            continue
        impl = table[VENDOR]
        impl = impl[0] if isinstance(impl, list) else impl
        mod = getattr(impl, "__module__", "?")
        if mod != __name__:
            bad.append(f"{method}: 实现来自 {mod}，不是替换层")
    if bad:
        raise ReplacementError(
            "vendor 表里还有原生实现（整体替换的判据）：\n  " + "\n  ".join(bad))


def dump_table(interface_module=None) -> str:
    if interface_module is None:
        from tradingagents.dataflows import interface as interface_module
    return json.dumps(
        {m: {v: getattr(f, "__module__", "?") + ":" + getattr(f, "__name__", "?")
             for v, f in t.items()}
         for m, t in interface_module.VENDOR_METHODS.items()},
        ensure_ascii=False, indent=2)
