# -*- coding: utf-8 -*-
"""FinRobot 的 `data_source` 层 → GeneBench 数据网关（**接线，不改内核**）。

FinRobot 原生的四个数据源 —— finnhub / yfinance / FMP / SEC（外加 reddit）——
在本环境里**全部在 `MARKET_DATA_HOSTS` 黑名单**里：容器的出向白名单只放模型 API，
它们一个都连不上。所以接线层做两件事，只做这两件：

1. **把类方法整个换掉**（`monkeypatch`，不改上游源码一个字节）：
   能对上网关端点的换成网关实现，对不上的换成 `NoData` 且**在数据面留痕**。
2. **把换好的方法喂回 FinRobot 自己的注册路径**（`agent_library.library` 里那张
   toolkit 表 → `finrobot.toolkits.register_toolkits`）。注册用的仍是它的代码。

替换点逐条在 `REPLACEMENTS` 里列着（`模块.类.方法 → 去处`），
`assert_no_native_datasource()` 在跑图之前把这张表核一遍：
**只要有一个方法还是上游原件就当场退出**，不靠"我记得我换过了"。

## 为什么 `get_stock_data` 不走 `compat.yfinance`

`genebench_client.compat.yfinance` 是给"我改不动 import"的系统用的便利层，
它按上游库的**完整列集**向网关请求 `fields`（`integrations/README.md` §3 的
「compat 层的 `fields` 只裁剪返回值，不改变网关上的读取集」）。
而 S1 题面明写 **「close 与 volume 走 /bars 并显式传 fields」** ——
声明读取集是**这道题在考的东西**，用 compat 层就控制不了。
所以这里按同一节手册给的正路直接用 `gb.client().bars(..., fields=[...])`。

`compat.install()` 仍然装（见 `run.py`）：`finrobot/functional/quantitative.py`
在**模块层** `import yfinance as yf`，不顶替就 import 不进来 ——
而顶替进去的是垫片，等于把"意外连上 Yahoo"这条路从进程里拿掉了。

## 加了三个上游没有的工具

网关有而 FinRobot 没有对应概念的三样东西：指数 PIT 成分、交易日历、复权因子。
S1 题面明写「成分不得手写，一律经 /universe 取」——
不给工具，agent 就只能手写成分（违题）或者干脆做不了。

    get_index_constituents / get_trading_calendar / get_adjustment_factors

这三个是**接线层新增的工具**，不是改内核：FinRobot 的架构本来就是
"把一组函数注册给 agent"，加一个函数走的是它自己的 `register_toolkits`。
README §4 把它们与替换点分开列，别读成"上游本来就有"。
"""
# **本模块有意不写 `from __future__ import annotations`。**
# autogen 从签名生成工具的 JSON schema，走的是 `pydantic.TypeAdapter(Annotated[...])`；
# PEP 563 把注解变成字符串之后，`Annotated[str, "……"]` 到了 pydantic 手里是一个
# 解析不了的 ForwardRef，当场 `PydanticUserError: … is not fully defined`。
# 现场表现同样是"agent 根本没起来"（本卡镜像内自检抓到的第二个，见 README §5）。
# 下面用到的 `X | None` / `list[str]` 在 3.10+ 的运行期都成立，不需要这条 future。
import functools
import re
from typing import Annotated, Any, Callable

import pandas as pd

import genebench_client as gb
from genebench_client import nodata
from genebench_client.codes import to_lake

#: 打在每个替换后的函数上的记号。`assert_no_native_datasource()` 只认这个。
MARK = "__genebench_gateway__"

#: 键列不是"字段"。`fields_obtained` 从返回列里减掉它们。
#:
#: `status` 在这一档里 —— 它是 `/bars` 每次都发的**停牌标记**，不是我们请求的字段。
#: 权威在 `reference/artifact_schema.py::BARS_KEY_COLUMNS`（`{code, date, status}`），
#: 评分侧算"声明读取集 vs 实际读取集"时正是先减掉这三个（同文件 1097 / 1243 行）。
#: 把 `status` 算进 `fields_obtained` 会让产物看起来"多读了一个字段"。
KEY_COLUMNS: frozenset[str] = frozenset(
    {"code", "date", "status", "trade_date", "ts_code", "symbol"})

#: 这一趟里网关真的还回来过哪些列。**清点，不自报** —— `run.py` 拿它填
#: `payload.fields_obtained`。
COLUMNS_SEEN: set[str] = set()

#: 一个 token 长得像 A 股代码吗（`600000` / `600000.SH` / `sh600000`）。
_TICKER = re.compile(r"^(?:[a-zA-Z]{2}\d{6}|\d{6}(?:\.[a-zA-Z]{2})?)$")

#: 返回给模型的表最多带几行原始数据。
#:
#: **这是一处已知偏离，写在 README §5**：上游 `stringify_output` 把整张
#: DataFrame `to_string()` 塞进对话，而 csi300 × 一个月 = 约 6,900 行、
#: 五十万字符 —— 一次就把上下文顶满，现场表现是"跑了一半就停"。
#: 所以这里返回**摘要 + 前几行**：行数/列名/区间/标的数都是真数，不是估。
PREVIEW_ROWS = 5


def _mark(fn: Callable) -> Callable:
    setattr(fn, MARK, True)
    return fn


def _client():
    return gb.client()


def _codes(symbols: str) -> list[str]:
    """把模型写的 `symbols` 解析成网关代码表。

    三种写法都收：单个代码、逗号分隔的代码表、**一个指数名**（`csi300` 这类）——
    指数名当场走 `/universe` 取 PIT 成分（题面：成分不得手写）。
    """
    raw = [t.strip() for t in str(symbols).replace(";", ",").split(",") if t.strip()]
    if not raw:
        raise ValueError("symbols 是空的 —— 不猜标的。")
    if len(raw) == 1 and not _TICKER.match(raw[0]):
        return _client().members(raw[0])
    return [to_lake(t) for t in raw]


def _summary(df: pd.DataFrame, head: str) -> str:
    COLUMNS_SEEN.update(str(c) for c in df.columns)
    n_sym = int(df["code"].nunique()) if "code" in df.columns else 0
    span = ""
    if "date" in df.columns and not df.empty:
        span = f" window={df['date'].min()}..{df['date'].max()}"
    body = "" if df.empty else "\n" + df.head(PREVIEW_ROWS).to_string(index=False)
    return (f"{head}\nrows={len(df)} symbols={n_sym}{span} "
            f"columns={[str(c) for c in df.columns]}"
            f"\n(only the first {PREVIEW_ROWS} rows are shown; the full frame stays on the "
            f"data plane and is counted into the run's fetch ledger){body}")


# ------------------------------------------------------------------ 网关实现

@_mark
def get_stock_data(
    symbols: Annotated[str, "One ticker (600000.SH), a comma separated list of tickers, "
                            "or an index name such as csi300 meaning that index's "
                            "point-in-time constituents."],
    start_date: Annotated[str, "start date of the window, YYYY-mm-dd, inclusive"],
    end_date: Annotated[str, "end date of the window, YYYY-mm-dd, inclusive"],
    fields: Annotated[str, "comma separated list of daily bar fields to read, "
                           "e.g. 'close,volume'. Declare exactly the fields you need: "
                           "the read set you declare here is what the data plane records."]
    = "close,volume",
) -> str:
    """Retrieve daily bars for the given symbols and window from the data gateway."""
    flds = [f.strip() for f in str(fields).replace(";", ",").split(",") if f.strip()]
    if not flds:
        raise ValueError("fields 是空的 —— /bars 必须显式传字段（题面要求）。")
    df = _client().bars(_codes(symbols), start_date, end_date, fields=flds)
    return _summary(df, f"/bars fields={flds}")


@_mark
def get_adjustment_factors(
    symbols: Annotated[str, "One ticker, a comma separated list, or an index name."],
    start_date: Annotated[str, "start date, YYYY-mm-dd, inclusive"],
    end_date: Annotated[str, "end date, YYYY-mm-dd, inclusive"],
) -> str:
    """Retrieve the adjustment factor (adj_factor) series from the data gateway."""
    df = _client().adj(_codes(symbols), start_date, end_date)
    return _summary(df, "/adj")


@_mark
def get_index_constituents(
    index_name: Annotated[str, "index name, one of csi300 / csi500 / csi1000 / all"],
    date: Annotated[str, "the trading day whose membership you want, YYYY-mm-dd"] = "",
) -> str:
    """Retrieve the point-in-time constituents of an index from the data gateway."""
    df = _client().universe(index_name, date or None)
    COLUMNS_SEEN.update(str(c) for c in df.columns)
    codes = [] if df.empty else sorted(df["code"].astype(str))
    return (f"/universe {index_name} @ {date or 'as_of'}: {len(codes)} constituents\n"
            + ",".join(codes))


@_mark
def get_trading_calendar(
    start_date: Annotated[str, "start date, YYYY-mm-dd"],
    end_date: Annotated[str, "end date, YYYY-mm-dd"],
) -> str:
    """Retrieve the trading days in a window from the data gateway."""
    days = _client().trading_days(start_date, end_date)
    return f"/calendar {start_date}..{end_date}: {len(days)} trading days\n" + ",".join(days)


# ------------------------------------------------------------------ NoData

def _no_data(name: str, kind: str, why: str, original: Callable | None = None) -> Callable:
    """造一个"可调用、抛不出去、且在数据面留痕"的替身。

    **不返回 `AttributeError`、也不静默返回 `None`**：前者会被上游的 `hasattr`
    探测吞掉、回落到原生数据源；后者让"它试过要新闻"这件事在数据面上什么都不剩，
    而"什么都没有"与"它根本没想过要新闻"不可区分（`genebench_client.nodata`）。

    留痕之后返回一句**给模型看的**说明 —— 工具抛异常会让 autogen 把整段
    traceback 塞回对话，那既没用又费 token。

    **签名照抄上游那一个**（`functools.wraps` + `__wrapped__`，`inspect.signature`
    会跟过去）。这不是洁癖：autogen 从签名生成工具的 JSON schema，
    `*args, **kwargs` 会让它当场

        TypeError: All parameters of the function '…' without default values
        must be annotated.

    而这句话出现在**组装 agent 的时候**，不是调用的时候 —— 现场表现是
    "接线看着都对，agent 根本没起来"（本卡镜像内自检抓到，见 README §5）。
    签名照抄还有一个好处：模型看到的参数与上游文档一致，
    "这个工具在本环境没数据"是**运行时**的答复，不是一个形状不同的假工具。
    """
    def _call(*args: Any, **kwargs: Any) -> str:
        try:
            nodata.trace(_client(), kind, f"finrobot.{name}", args=str(args)[:200])
        except Exception as exc:                                   # noqa: BLE001
            return f"NO_DATA: {name} —— {why}（留痕本身也失败了：{exc}）"
        return (f"NO_DATA: {name} is not available in this environment —— {why}. "
                f"Do not guess a substitute value; state it as missing if you need it.")

    if original is not None:
        _call = functools.wraps(original)(_call)
    _call.__name__ = name.split(".")[-1]
    _call.__qualname__ = name
    _call.__doc__ = f"[NO DATA in this environment] {why}"
    if not getattr(_call, "__annotations__", None):
        _call.__annotations__ = {"return": str}
    return _mark(_call)


#: 替换点全表：`模块路径.类.方法` → 去处。**README §4 与这张表同源**。
REPLACEMENTS: dict[str, str] = {}

_NO_DATA_SPEC: dict[str, list[tuple[str, str, str]]] = {
    # 类名: [(方法名, nodata 分类, 为什么没有)]
    "YFinanceUtils": [
        ("get_stock_info", "other", "网关不发标的档案（只有 PIT 成分与行情）"),
        ("get_company_info", "other", "网关不发公司档案"),
        ("get_stock_dividends", "corporate_actions",
         "网关只发合成的 adj_factor，不发分红/拆股明细 —— 用 get_adjustment_factors"),
        ("get_income_stmt", "fundamentals", "三大报表不发放给 v1 的任何一道题"),
        ("get_balance_sheet", "fundamentals", "三大报表不发放给 v1 的任何一道题"),
        ("get_cash_flow", "fundamentals", "三大报表不发放给 v1 的任何一道题"),
        ("get_analyst_recommendations", "sentiment", "本环境没有卖方评级数据源"),
    ],
    "FinnHubUtils": [
        ("get_company_profile", "other", "本环境没有 finnhub 档案数据源"),
        ("get_company_news", "news", "本环境没有新闻数据源"),
        ("get_basic_financials", "fundamentals", "三大报表不发放给 v1 的任何一道题"),
        ("get_basic_financials_history", "fundamentals", "三大报表不发放给 v1 的任何一道题"),
    ],
    "FMPUtils": [
        ("get_target_price", "sentiment", "本环境没有目标价数据源"),
        ("get_sec_report", "other", "本环境没有 SEC 数据源（A 股环境）"),
        ("get_historical_market_cap", "fundamentals", "网关不发市值序列"),
        ("get_historical_bvps", "fundamentals", "网关不发每股净资产"),
        ("get_financial_metrics", "fundamentals", "三大报表不发放给 v1 的任何一道题"),
    ],
    "SECUtils": [
        ("get_10k_metadata", "other", "A 股环境没有 10-K"),
        ("download_10k_filing", "other", "A 股环境没有 10-K"),
        ("download_10k_pdf", "other", "A 股环境没有 10-K"),
        ("get_10k_section", "other", "A 股环境没有 10-K"),
    ],
    "RedditUtils": [
        ("get_reddit_posts", "sentiment", "本环境没有社交媒体数据源"),
    ],
}

#: 换成网关实现的（上游有同名方法，行为被顶替）。
_GATEWAY_SPEC: dict[str, list[tuple[str, Callable]]] = {
    "YFinanceUtils": [("get_stock_data", get_stock_data)],
}

#: 上游没有、接线层新增的工具（README §4 单列一节）。
ADDED_TOOLS: tuple[Callable, ...] = (
    get_index_constituents, get_trading_calendar, get_adjustment_factors)


def install() -> dict[str, str]:
    """把上面两张表落到 FinRobot 的类上。**必须在 `import agent_library` 之前**跑。

    `agent_library` 在**模块层**就把 `FinnHubUtils.get_company_profile` 这些
    函数对象抓进 `library[...]["toolkits"]` 了；晚一步换，换到的是没人再看的那份。
    """
    from finrobot import data_source as DS

    REPLACEMENTS.clear()
    for cls_name, items in _GATEWAY_SPEC.items():
        cls = getattr(DS, cls_name)
        for meth, impl in items:
            if not hasattr(cls, meth):
                raise RuntimeError(
                    f"上游没有 {cls_name}.{meth} —— 版本对不上，接线不能装。"
                    f"（钉的版本见 integrations/finrobot/pin.json）")
            setattr(cls, meth, impl)
            REPLACEMENTS[f"{cls_name}.{meth}"] = f"网关 {impl.__name__}"
    for cls_name, items in _NO_DATA_SPEC.items():
        cls = getattr(DS, cls_name)
        for meth, kind, why in items:
            if not hasattr(cls, meth):
                raise RuntimeError(f"上游没有 {cls_name}.{meth} —— 版本对不上。")
            setattr(cls, meth, _no_data(f"{cls_name}.{meth}", kind, why,
                                        original=getattr(cls, meth)))
            REPLACEMENTS[f"{cls_name}.{meth}"] = f"NoData({kind})"
    return dict(REPLACEMENTS)


def patch_library(library: dict) -> list[str]:
    """把 `agent_library.library` 里那张 toolkit 表也换成换过的函数。

    **为什么需要这一步**：`agent_library` 在**模块层**就把函数对象抓进
    `library[...]["toolkits"]` 了。只要有任何一条 import 路径先碰到
    `finrobot.agents.*`（例如先 `import finrobot.agents.workflow`），
    `install()` 再换类属性也换不到那张表 —— 而现场表现是
    「接线装好了、日志也打印了替换表，agent 手里拿的却还是原生实现」，
    真跑时才会以"连不上 finnhub"的形态暴露出来（本卡的镜像内自检抓到过一次）。

    所以这里按**函数名**把表里的每一项重绑到当前的类属性上，让顺序不再是前提。
    重绑不了的（上游哪天换了函数来源）就地报错，不静默留着原件。
    """
    by_name: dict[str, Callable] = {}
    from finrobot import data_source as DS
    for cls_name in _NO_DATA_SPEC:
        cls = getattr(DS, cls_name)
        for meth in dir(cls):
            if not meth.startswith("_"):
                by_name[meth] = getattr(cls, meth)
    for cls_name in _GATEWAY_SPEC:
        cls = getattr(DS, cls_name)
        for meth, _impl in _GATEWAY_SPEC[cls_name]:
            by_name[meth] = getattr(cls, meth)

    rebound: list[str] = []
    for entry in library.values():
        tools = entry.get("toolkits")
        if not tools:
            continue
        fixed = []
        for fn in tools:
            name = getattr(fn, "__name__", None)
            if callable(fn) and not getattr(fn, MARK, False) and name in by_name:
                fixed.append(by_name[name])
                rebound.append(f"{entry.get('name')}.{name}")
            else:
                fixed.append(fn)
        entry["toolkits"] = fixed
    return rebound


def assert_no_native_datasource() -> None:
    """跑图之前核一遍：五个类的**每一个公开方法**都必须是我们换上去的。

    上游哪天多一个方法（或者我们漏换一个），这里当场退出 —— 那比"真跑到一半
    去连 finnhub、被出向代理拦掉、现场看起来像模型不会用工具"便宜得多。
    """
    from finrobot import data_source as DS

    leaked: list[str] = []
    for cls_name in ("YFinanceUtils", "FinnHubUtils", "FMPUtils", "SECUtils", "RedditUtils"):
        cls = getattr(DS, cls_name)
        for meth in dir(cls):
            if meth.startswith("_"):
                continue
            fn = getattr(cls, meth)
            if callable(fn) and not getattr(fn, MARK, False):
                leaked.append(f"{cls_name}.{meth}")
    if leaked:
        raise RuntimeError(
            "这些 data_source 方法还是上游原件（会去连黑名单里的行情源）："
            + ", ".join(sorted(leaked)))


def assert_market_data_seam_closed() -> None:
    """`import yfinance` 拿到的必须是垫片，不是真库。

    `finrobot/functional/quantitative.py` 在模块层 `import yfinance as yf` ——
    真库要是装在镜像里，这一行就是一条绕过网关的路。
    """
    import sys

    from genebench_client import compat

    mod = sys.modules.get("yfinance")
    if mod is not compat.yfinance:
        raise RuntimeError(
            f"sys.modules['yfinance'] 不是垫片而是 {mod!r} —— "
            f"compat.install() 没跑，或者真的 yfinance 被装进镜像了。")


def fields_obtained() -> list[str]:
    """这一趟真拿到的字段（**清点**：网关还回来的列，减掉键列）。"""
    return sorted(c for c in COLUMNS_SEEN if c not in KEY_COLUMNS)


def dump_table() -> str:
    return "\n".join(f"  {k} → {v}" for k, v in sorted(REPLACEMENTS.items()))
