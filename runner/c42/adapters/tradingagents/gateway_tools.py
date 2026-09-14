"""§11.2：把 TradingAgents 的原生数据源**整体替换**为经网关的实现。

**替换缝是上游自己的扩展点**（TauricResearch v0.4.0 实测）：
`tradingagents/dataflows/interface.py` 有一张真正的 vendor 注册表 ——
`VENDOR_METHODS = {方法: {厂商: 实现}}`（11 个方法 × 4 家），
`route_to_vendor(method, ...)` 按 `config["data_vendors"][category]` 派发。

**为什么必须替换 `VENDOR_METHODS` 本身，而不只是改配置**：
上游注释写着「配置的 vendor 列表**就是**调用链，不静默回落」，但
`"default"` 这个 sentinel（没显式配时）用的是**全部可用 vendor** ——
配置一旦丢失或写错，链条就回到 yfinance。把字典本身换掉，那条路就不存在了。

**为什么必须是「整体」**：留一个原生实现在表里，就是一条**未声明的数据源** ——
网关 `access_log` 会干干净净，卡 5.1 的前视探针全绿，而 as-of 强制已经失效
（卡 4.1 §3.1 的形态）。f02 容器实测**能直连** `query1.finance.yahoo.com:443`，
所以这不是理论风险。

**先前的实现（换 `ANALYST_TOOL_REGISTRY`）是错的层**：那是 Mai0313 那个同名包的结构
（见 N-51），而且红队实测「换了注册表，图仍然执行原生工具」——
图在构造时就把工具捕获走了，按工具名分发（N-52）。
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

#: 我们注册进上游 vendor 表的名字。
VENDOR = "genebench_gateway"

GATEWAY_ENV = "GENEBENCH_GATEWAY"

#: 网关的查询参数名是 `start_date` / `end_date`（**不是** `start` / `end`）——
#: 写错名字时网关不报「未知参数」，而是判**开区间**
#: （`open_range_would_cross_asof`）。症状看起来像语义错误，
#: 排查的人会去查 as_of 而不是查拼写（N-50）。
#: **`/fundamentals` 不在这里**（N-58①）：v1 的题面不发放它，
#: 适配器再把它接上就是「题面没说有、工具却递到手里」——
#: 只摘题面一头会把我们自己造成的诱导记进越权率。
SERVED = {"bars": "/bars", "adj": "/adj", "calendar": "/calendar",
          "limits": "/limits", "universe": "/universe",
          "tradability": "/tradability"}

#: 网关**没有**对应端点的方法。返回显式 `[NO_DATA]`，
#: **不是**空串、**不是**编一段话 —— 让「这个环境没有这类数据」在产物里可见。
NO_SOURCE = {
    "get_news": "个股新闻", "get_global_news": "全球/宏观新闻",
    "get_insider_transactions": "内部人交易", "get_macro_indicators": "宏观指标",
    # N-58① 裁定：`/fundamentals` 不发放给 v1 的任何一道题 —— 把它接到网关
    # 等于把一件**题面没告诉 agent 它有**的工具递到它手里。
    # 6 张财务快照留私有通道，不进公开包。
    "get_fundamentals": "基本面",
    "get_prediction_markets": "预测市场", "get_balance_sheet": "资产负债表明细",
    "get_cashflow": "现金流量表明细", "get_income_statement": "利润表明细",
}

NO_DATA = "[NO_DATA] 本环境不提供{what}数据源；本次运行的全部数据只经网关获取。"


class ReplacementError(RuntimeError):
    pass


def _get(path: str, **params) -> dict:
    base = os.environ.get(GATEWAY_ENV)
    if not base:
        raise ReplacementError(
            f"{GATEWAY_ENV} 没设 —— 取数只能经网关，没有网关就不该有第二条路")
    url = f"{base.rstrip('/')}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={
        # 身份头由边车在网关入口**剥掉重注**（卡 4.3 §6.5 ID-1..ID-5）。
        "x-genebench-task-id": os.environ.get("GENEBENCH_TASK_ID", ""),
        "x-genebench-config-id": os.environ.get("GENEBENCH_CONFIG_ID", ""),
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _as_of() -> str:
    v = os.environ.get("GENEBENCH_AS_OF")
    if not v:
        raise ReplacementError(
            "GENEBENCH_AS_OF 没设 —— as-of 是这个基准的地基，"
            "缺了它取数会取到冻结线之后（前视），而产物上看不出来")
    return v


def _pit(date: str | None) -> str:
    """**PIT 校验**：不许索取 `as_of` 之后的数据。

    上游 v0.4.0 在自己的工具层有一层日期防护；我们把实现整体换掉之后，
    **那一层就没了**（N-52）。所以替换层必须逐个重实现 —— 而且要
    **fail-closed**：拿不到日期就拒，不放行。
    """
    a = _as_of()
    if not date:
        raise ReplacementError(f"没给日期 —— 无法判断是否越过 as_of={a}（fail-closed）")
    d = str(date).replace("-", "")[:8]
    if d > a.replace("-", "")[:8]:
        _PIT_HITS.append((date, a))
        raise ReplacementError(f"[PIT] 请求日期 {date} 晚于 as_of={a} —— 前视，拒绝")
    _PIT_HITS.append((date, a))
    return date


#: 每次 PIT 校验都记一笔。**正例断言**：一次 run 内至少命中一次，
#: 否则说明守卫根本没被调用过（红队复核：ContextVar 版的守卫在线程池里静默失效）。
_PIT_HITS: list[tuple] = []


def pit_hits() -> list[tuple]:
    return list(_PIT_HITS)


def reset_pit_hits() -> None:
    _PIT_HITS.clear()


# --------------------------------------------------------------- 实现


def get_stock_data(symbol: str, start_date: str, end_date: str, **kw) -> str:
    _pit(end_date)
    d = _get(SERVED["bars"], code=symbol, start_date=start_date,
             end_date=end_date, as_of=_as_of())
    return json.dumps(d, ensure_ascii=False)[:20000]


def get_indicators(symbol: str, indicator: str = "close", curr_date: str = "",
                   look_back_days: int = 30, **kw) -> str:
    _pit(curr_date)
    d = _get(SERVED["bars"], code=symbol, start_date=curr_date, end_date=curr_date,
             as_of=_as_of())
    return json.dumps({"indicator": indicator, "source": "gateway:/bars",
                       "rows": d.get("rows"), "data": d.get("data", [])[:200]},
                      ensure_ascii=False)[:20000]


def _no_source(method: str):
    what = NO_SOURCE[method]

    def _impl(*args, **kwargs) -> str:
        return NO_DATA.format(what=what)

    _impl.__name__ = f"no_source_{method}"
    return _impl


def build_vendor_table(methods) -> dict:
    """给上游的**每一个**方法都造一个我们的实现。缺一个就是一条原生路径活着。"""
    served = {"get_stock_data": get_stock_data, "get_indicators": get_indicators}
    out = {}
    for m in methods:
        out[m] = served.get(m) or _no_source(m) if m in served or m in NO_SOURCE else None
        if out[m] is None:
            raise ReplacementError(
                f"上游多了一个我们没覆盖的方法 {m!r} —— 它会留着原生实现。"
                f"要么给它一个网关实现，要么显式登记进 NO_SOURCE")
    return out


def install(interface_module=None, config: dict | None = None) -> dict:
    """把 `VENDOR_METHODS` 整表换成我们的，并把 `data_vendors` 全指向我们。

    返回换掉之前的原表（供还原与对照）。**不改上游源码** —— 改源码会让 `commit` 那把钉子失效。
    """
    if interface_module is None:
        from tradingagents.dataflows import interface as interface_module
    before = {m: dict(v) for m, v in interface_module.VENDOR_METHODS.items()}
    mine = build_vendor_table(list(before))
    for m, impl in mine.items():
        interface_module.VENDOR_METHODS[m] = {VENDOR: impl}
    if hasattr(interface_module, "VENDOR_LIST"):
        interface_module.VENDOR_LIST[:] = [VENDOR]
    vendors = {c: VENDOR for c in interface_module.TOOLS_CATEGORIES}
    if config is not None:
        config["data_vendors"] = vendors
        config.pop("tool_vendors", None)
    # **必须同时写进模块级配置**：`route_to_vendor` 读的是
    # `tradingagents.dataflows.config.get_config()`，不是调用方手里那份 dict。
    # 只改调用方那份的后果是 fail-closed 的（「配置的 vendor 不可用」直接抛）——
    # 这次是安全的方向，但它仍然是「改了一份没人读的配置」。
    try:
        from tradingagents.dataflows import config as ta_config
        ta_config.set_config({"data_vendors": vendors, "tool_vendors": {}})
    except ImportError:
        pass
    return before


def assert_only_gateway_vendor(interface_module=None) -> None:
    """**断言落在 `route_to_vendor` 实际派发的那张表上**，不落在工具注册表上。

    红队实测：换了工具注册表，图仍然执行原生工具（N-52）—— 门装在了错的层。
    这里查的是每个方法**唯一可用的 vendor** 是不是我们，以及实现函数是不是我们模块里的。
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
            "vendor 表里还有原生实现（§11.2 要求整体替换）：\n  " + "\n  ".join(bad))
