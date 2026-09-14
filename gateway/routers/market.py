# -*- coding: utf-8 -*-
"""行情侧端点：``/bars`` ``/adj`` ``/calendar`` ``/limits``。"""
from __future__ import annotations

from typing import Any

import pandas as pd
from fastapi import APIRouter, Query

import genebench_config as cfg
from snapshots import tradability as tr

from .. import backends
from ..asof import guard_codes, guard_range, guard_target, parse_asof
from ..errors import GatewayDenied, Reason

router = APIRouter()

#: `/adj` 只答这一种口径。三价口径（bfq/hfq/qfq）不进 v1 数据面 ——
#: `stk_factor_pro` 冻结在 20260731 而 `adj_factor` 还在往前走，
#: 两个口径在 2026-08 之后不同步，同时暴露等于给下游埋一个静默错配。
ADJ_MODE: str = "adj_factor"
BLOCKED_ADJ_MODES: tuple[str, ...] = ("bfq", "hfq", "qfq", "qfq_close", "hfq_close")

#: 湖里只有 SSE 一个交易所。深市用 SSE 日历是**约定不是数据事实**，
#: 响应里必须把这句话带出去，否则下游会把它当成"深交所日历也核过了"。
CALENDAR_EXCHANGE: str = "SSE"
CALENDAR_CAVEAT: str = (
    "湖内 trade_cal 只有 SSE。深市沿用 SSE 日历是本项目的约定，不是数据事实。"
)

MAX_ROWS: int = 200_000


def _too_many(n: int, what: str) -> None:
    if n > MAX_ROWS:
        raise GatewayDenied(
            Reason.PARAM_MALFORMED,
            f"{what} 会返回约 {n} 行，超过单次上限 {MAX_ROWS}；请缩小窗口或指定 code",
            status=422,
        )


#: `/bars` 永远返回的键列 —— 没有它们，只取 `close` 的行无法定位。
KEY_COLUMNS: tuple[str, ...] = ("code", "date", "status")

#: `/bars` **显式声明**的服务集（N-33，2026-09-02 裁定）。响应列必须**恰好**等于 KEY_COLUMNS ∪ 这个集合，
#: 缺一列就是 bug 而不是「这一行恰好没有」—— 此前候选列表里写着 open/pre_close/amount，
#: 一句 `if c in sel.columns` 把不存在的列静默过滤掉了（D-06 第 10 例）。
#: 与冻结 provider 的字段集对齐：open/high/low/close/volume/amount/vwap（factor 由 /adj 服务）。
BARS_SERVED_COLUMNS: tuple[str, ...] = (
    "suspend_basis", "has_daily",
    "open", "high", "low", "close", "volume", "amount", "vwap",
    "limit_up_close", "limit_down_close", "limit_touched_up", "limit_touched_down",
    "no_price_limit", "in_listing_window",
)

#: 来自 `daily` 而不在 tradability 视图里的列。
_DAILY_EXTRA: tuple[str, ...] = ("open", "amount")


def _attach_daily_extras(sel: pd.DataFrame, codes: list[str], lo: str, hi: str) -> pd.DataFrame:
    """把 `daily` 的 open / amount 贴到 tradability 行域上，并现算 vwap。  [N33-v4]

    * 行域仍是 tradability（停牌日有行、status 显式）；`daily` 缺行的格子 open/amount/vwap 为 null；
    * `vwap = amount / volume`（卡 2.1a 实证口径），`volume = 0` 或缺失 → null，**永不 inf/0**；
    * **日期过滤格式无关**：v1 按紧凑串比 `trade_date`，快照里它不是紧凑串，比较恒假、贴列为空、
      open/amount 静默全 null（2026-09-02 实测，D-06）。现在 SQL 只按年过滤
      （`substr(CAST(trade_date AS VARCHAR), 1, 4)` 对 VARCHAR/DATE/紧凑串都成立），
      日期在 pandas 里归一成 ISO 后精确切；
    * **贴列为空而行域有交易日 → 抛**，不再静默 null。
    """
    # SQL 里**只按 ts_code 过滤**，不放任何函数/CAST —— read_table 的 where 片段有白名单校验，
    # `IN (?)` 已实证可过；日期的类型归一与范围切片全部在 pandas 里做（v3）。
    code_ph = ", ".join("?" * len(codes))
    extra = backends.read_table(
        "daily",
        where=f"ts_code IN ({code_ph})",
        params=[*codes],
        columns="ts_code, trade_date, open, amount",
    )
    iso_lo = f"{lo[:4]}-{lo[4:6]}-{lo[6:]}"
    iso_hi = f"{hi[:4]}-{hi[4:6]}-{hi[6:]}"
    if extra is None or len(extra) == 0:
        extra = pd.DataFrame(columns=["code", "date", "open", "amount"])
    else:
        extra = extra.rename(columns={"ts_code": "code"})
        norm = extra["trade_date"].astype(str).str.slice(0, 10).str.replace("-", "", regex=False)
        extra["date"] = norm.str[:4] + "-" + norm.str[4:6] + "-" + norm.str[6:8]
        extra = extra[(extra["date"] >= iso_lo) & (extra["date"] <= iso_hi)]
        extra = extra[["code", "date", "open", "amount"]].drop_duplicates(["code", "date"])
    trade_days = int((sel["status"] == "trade").sum()) if "status" in sel.columns else 0
    if trade_days > 0 and len(extra) == 0:
        raise RuntimeError(
            f"/bars 贴列为空：行域里有 {trade_days} 个交易日，daily 却匹配到 0 行 —— "
            f"日期/代码格式对不上（N-33/D-06 第 10 例的形态），不静默返回 null")
    # merge 键两边都归一成 ISO **字符串**：tradability 的 `date` 是 date 对象（JSON 里才是串），
    # 拿 ISO 串去 merge 会一行都对不上、静默全 NaN（2026-09-02 第二次实测）。
    sel = sel.copy()
    sel["_k"] = sel["date"].astype(str).str.slice(0, 10)
    sel["_c"] = sel["code"].astype(str).str.strip().str.upper()
    extra = extra.assign(_k=extra["date"].astype(str).str.slice(0, 10),
                         _c=extra["code"].astype(str).str.strip().str.upper())[["_c", "_k", "open", "amount"]]
    sel = sel.merge(extra, on=["_c", "_k"], how="left").drop(columns=["_k", "_c"])
    if trade_days > 0 and int(pd.to_numeric(sel["open"], errors="coerce").notna().sum()) == 0:
        raise RuntimeError(
            f"/bars 贴列后 open 整列为空但行域有 {trade_days} 个交易日 —— merge 键没对上（键类型/格式），"
            f"不静默返回 null（N-33/D-06）")
    vol = pd.to_numeric(sel["volume"], errors="coerce") if "volume" in sel.columns else pd.Series(index=sel.index, dtype=float)
    amt = pd.to_numeric(sel["amount"], errors="coerce")
    vwap = amt / vol.where(vol > 0)
    # float 列上 where(..., None) 会被 pandas 变回 NaN（JSON 里是非法的 NaN）；先转 object 再替换
    sel["vwap"] = vwap.astype(object).where(vwap.notna(), None)
    for c in ("open", "amount"):
        col = pd.to_numeric(sel[c], errors="coerce")
        sel[c] = col.astype(object).where(col.notna(), None)
    return sel


def _select_fields(available: list[str] | None, fields: str | None) -> list[str]:
    """`fields` 缺省或 `*` = 全部列；给了就只返回请求的列（外加键列）。

    **未知列名 422，而不是静默忽略**：一个拼错的字段名若被悄悄跳过，
    调用方拿到的仍是一份「看起来成功」的结果（D-06）。

    为什么要这个参数（卡 2.3-c）：网关日志原本只到**端点**粒度，S3 的
    「声明读取集 vs 实际读取集」探针在 `/bars` 内部分不出读了 open 还是 close。
    `fields` 落进 `params` 就自动进了 access_log，探针从此有字段粒度；
    不写 `fields`（= 读全表）在探针眼里**同样是读了全部列**。
    """
    served = list(KEY_COLUMNS) + list(BARS_SERVED_COLUMNS)
    if fields is None or fields.strip() in ("", "*"):
        return served
    want = [x.strip() for x in fields.split(",") if x.strip()]
    unknown = sorted(set(want) - set(served))
    if unknown:
        raise GatewayDenied(
            Reason.PARAM_MALFORMED,
            f"/bars 不认识字段 {unknown}；服务集：{list(BARS_SERVED_COLUMNS)}",
            status=422, context={"unknown_fields": unknown},
        )
    return [c for c in served if c in KEY_COLUMNS or c in want]


@router.get("/bars")
def bars(
    as_of: str | None = Query(None),
    code: list[str] | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    fields: str | None = Query(None),
    ctx: dict[str, Any] = None,  # noqa: ARG001  由中间件注入
) -> dict[str, Any]:
    """日线。**停牌日返回带 status 的记录，不是静默空**。

    `daily` 里停牌票是**缺行**，缺行同时意味着"停牌"和"数据缺失"——
    二者靠 daily 本身分不开。所以本端点以卡 1.2 的 `tradability` 为行域基准
    （它已经三方 join 过 daily × suspend_d × trade_cal），再把 OHLCV 贴上去。
    """
    a = parse_asof(as_of)
    lo, hi = guard_range(start_date, end_date, a)
    codes = guard_codes(code)
    if not codes:
        raise GatewayDenied(
            Reason.PARAM_MALFORMED, "/bars 必须指定至少一个 code", status=422
        )
    years = sorted({int(lo[:4]), int(hi[:4])})
    years = list(range(years[0], years[-1] + 1))
    # 行域按**当前通道**取（卡 1.1-a）：private 时 `cfg.tradability_dir()`
    # 返回的就是 `cfg.TRADABILITY_DIR`，与既有逐字节同一条路径。
    frame = tr.read_tradability(years=years, root=cfg.tradability_dir())
    iso_lo, iso_hi = f"{lo[:4]}-{lo[4:6]}-{lo[6:]}", f"{hi[:4]}-{hi[4:6]}-{hi[6:]}"
    date_col = frame["date"].astype(str)
    sel = frame[
        frame["code"].isin(codes) & (date_col >= iso_lo) & (date_col <= iso_hi)
    ].copy()
    _too_many(len(sel), "/bars")
    sel = _attach_daily_extras(sel, codes, lo, hi)
    missing = [c for c in (*KEY_COLUMNS, *BARS_SERVED_COLUMNS) if c not in sel.columns]
    if missing:
        # 显式声明了就必须服务；缺列是我们的 bug，响（500），不哑
        raise RuntimeError(f"/bars 声明服务 {missing} 但行域里没有这些列 —— 服务集与实现漂了（N-33/D-06）")
    keep = _select_fields(None, fields)
    sel = sel[keep].sort_values(["code", "date"])
    return {
        "as_of": a,
        "rows": len(sel),
        "fields": [c for c in keep if c not in KEY_COLUMNS],
        "note": "行域来自 tradability：停牌日有行且 status 显式说明，不是静默空",
        "data": sel.to_dict(orient="records"),
    }


@router.get("/adj")
def adj(
    as_of: str | None = Query(None),
    code: list[str] | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    mode: str = Query(ADJ_MODE),
    ctx: dict[str, Any] = None,  # noqa: ARG001
) -> dict[str, Any]:
    """复权因子。**只答 adj_factor 口径。**"""
    a = parse_asof(as_of)
    m = str(mode).strip().lower()
    if m != ADJ_MODE:
        raise GatewayDenied(
            Reason.ADJ_MODE_UNSUPPORTED,
            f"mode={mode!r} 不在 v1 数据面。v1 统一 adj_factor 口径；"
            f"stk_factor_pro 的 {BLOCKED_ADJ_MODES} 三价口径与 adj_factor 不同步，不暴露。",
            context={"mode": m, "supported": [ADJ_MODE]},
        )
    lo, hi = guard_range(start_date, end_date, a)
    codes = guard_codes(code)
    where = "trade_date >= ? AND trade_date <= ?"
    params: list[Any] = [lo, hi]
    if codes:
        where += " AND ts_code IN (" + ",".join(["?"] * len(codes)) + ")"
        params += codes
    out = backends.read_table(
        "adj_factor", where=where, params=params,
        columns="ts_code, trade_date, adj_factor",
    )
    _too_many(len(out), "/adj")
    return {"as_of": a, "mode": ADJ_MODE, "rows": len(out),
            "data": out.sort_values(["ts_code", "trade_date"]).to_dict(orient="records")}


@router.get("/calendar")
def calendar(
    as_of: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    ctx: dict[str, Any] = None,  # noqa: ARG001
) -> dict[str, Any]:
    """交易日历。

    ⚠️ `trade_cal` 在湖里**排到 20261231**（预写的未来日历）。
    请求未来交易日是最容易被忽略的一条越界路径 —— 它不像行情那样
    "本来就没数据"，它**真的查得到**。所以这里判得和别处一样严。
    """
    a = parse_asof(as_of)
    lo, hi = guard_range(start_date, end_date, a)
    # end 已由 guard_range 判过；这里再显式点名 CALENDAR_FUTURE，
    # 让日志里这条路径可以单独聚合（卡 5.1 要按路径统计越权率）。
    guard_target(hi, a, field="end_date", reason=Reason.CALENDAR_FUTURE)
    out = backends.read_table(
        "trade_cal",
        where="exchange = ? AND cal_date >= ? AND cal_date <= ?",
        params=[CALENDAR_EXCHANGE, lo, hi],
        columns="exchange, cal_date, is_open, pretrade_date",
    )
    return {
        "as_of": a,
        "exchange": CALENDAR_EXCHANGE,
        "caveat": CALENDAR_CAVEAT,
        "rows": len(out),
        "data": out.sort_values("cal_date").to_dict(orient="records"),
    }


@router.get("/limits")
def limits(
    as_of: str | None = Query(None),
    code: list[str] | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    ctx: dict[str, Any] = None,  # noqa: ARG001
) -> dict[str, Any]:
    """涨跌停价。

    两条硬约束：

    1. **`stk_limit.pre_close` 全为 NULL**，不透出（透出去下游会拿它算涨跌幅）。
    2. **绝不把"无涨跌幅限制"的哨兵值当真实涨停价发出去**。湖里这类行的
       `up_limit` 有六种编码（100000.0 / 1000000.0 / 999999.999 / 99999.999 /
       99999.99 / 0.0），共 7,107 行。命中哨兵时 `up_limit`/`down_limit`
       置 None 并把 `no_price_limit=true` 摆在明面上 —— 卡 1.2 的 D1 就是
       因为漏掉三种编码，让 `688425.SH @ 2021-06-22` 的涨停价发成了 99999.999。
    """
    a = parse_asof(as_of)
    lo, hi = guard_range(start_date, end_date, a)
    codes = guard_codes(code)
    where = "trade_date >= ? AND trade_date <= ?"
    params: list[Any] = [lo, hi]
    if codes:
        where += " AND ts_code IN (" + ",".join(["?"] * len(codes)) + ")"
        params += codes
    out = backends.read_table(
        "stk_limit", where=where, params=params,
        columns="ts_code, trade_date, up_limit, down_limit",
    )
    _too_many(len(out), "/limits")
    if len(out):
        mask = tr.no_price_limit_mask(
            out["up_limit"].to_numpy(dtype="float64"),
            out["down_limit"].to_numpy(dtype="float64"),
        )
        out = out.assign(no_price_limit=mask)
        out.loc[mask, ["up_limit", "down_limit"]] = None
    else:
        out = out.assign(no_price_limit=pd.Series(dtype=bool))
    return {
        "as_of": a,
        "rows": len(out),
        "note": (
            "no_price_limit=true 表示该行在湖里是哨兵编码（无涨跌幅限制），"
            "此时 up_limit/down_limit 为 null —— 不是缺数，是本来就没有涨跌停价。"
            "pre_close 不透出：湖里该列全为 NULL。"
        ),
        "sentinel_rows": int(out["no_price_limit"].sum()) if len(out) else 0,
        "data": out.sort_values(["ts_code", "trade_date"]).to_dict(orient="records"),
    }
