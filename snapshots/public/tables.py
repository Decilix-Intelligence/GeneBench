# -*- coding: utf-8 -*-
"""公开通道的**快照表与可交易性视图**（卡 1.1-a / 卡 2.5 §2 §3 §4）。

落点 `$SNAPSHOTS/public_v1/`，布局与私有的 `snapshots/v1/` **同名同形**：

    public_v1/tables/{daily,adj_factor,trade_cal,stk_limit,suspend_d,stock_basic}.parquet
    public_v1/tradability/year=YYYY/part-0.parquet
    public_v1/build/quotes.parquet        # 中间产物，不是交付面

**两条通道并列、不覆盖** —— 本模块一个字节都不往 `snapshots/v1/` 写。

三处「公开源与私有湖不一样」的落点（数字与逐条对照见
`ops/reports/public/data_channel_notes.md`）：

* **停牌**（卡 2.5 §4）：baostock **有行**且 `tradestatus=0`，我们的湖**缺行**。
  这里把 `tradestatus=0` 的行**从 `daily` 里拿掉、写进 `suspend_d`**，
  于是 `tradability` 的三态（trade / suspend / no_data）与私有通道同构，
  差异被吸收在**这一处**，而不是散进 792 条 gold 里。
* **涨跌停**：公开源没有 `stk_limit`，按 `snapshots/public/limits.py` 从前收推
  （那套规则是拿私有 `stk_limit` 逐行核出来的，763,301 行零分歧，N-67）。
  「无涨跌幅限制」在私有湖里是**哨兵编码**，这里**照抄同一套哨兵**
  （`limits.ORACLE_NO_LIMIT_SENTINEL`），好让网关那段既有的哨兵识别代码
  在两条通道上走同一条分支 —— 不然公开通道会发出 `up_limit=null` 且
  `no_price_limit=false` 的行，语义直接矛盾。
* **退市整理期首日无限制**：判据是私有 `namechange.change_reason`，
  公开通道**没有**这张表，所以这条规则**推不出来**（半年 15 行的量级，N-67）。
  不猜、不用名字近似 —— 名字判据实测会整个漏掉沪市。登记在数据卡里。
"""
from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

import genebench_config as cfg
from snapshots import tradability as tr
from snapshots.public import limits as LM
from snapshots.public import source as S

# ---------------------------------------------------------------- 落点

TABLES_DIR: Path = cfg.PUBLIC_TABLES_DIR
TRADABILITY_DIR: Path = cfg.PUBLIC_TRADABILITY_DIR
BUILD_DIR: Path = cfg.PUBLIC_BUILD_DIR
QUOTES_PARQUET: Path = BUILD_DIR / "quotes.parquet"

#: 公开包实际要带的表。**正好是卡 2.5 §1 七项依赖里公开源给得出的那些** ——
#: 第 4 项（指数成分 PIT）走 `universe_pit`（定义面，不是行情），
#: 第 7 项（涨跌停）是本模块推的。
PUBLIC_TABLE_NAMES: tuple[str, ...] = (
    "daily", "adj_factor", "trade_cal", "stk_limit", "suspend_d", "stock_basic",
)

CALENDAR_EXCHANGE = "SSE"

# ---------------------------------------------------------------- schema

_S = pa.string()
_D = pa.float64()

SCHEMAS: dict[str, pa.Schema] = {
    "daily": pa.schema([("ts_code", _S), ("trade_date", _S), ("open", _D), ("high", _D),
                        ("low", _D), ("close", _D), ("pre_close", _D), ("amount", _D),
                        ("volume", _D)]),
    "adj_factor": pa.schema([("ts_code", _S), ("trade_date", _S), ("adj_factor", _D)]),
    "stk_limit": pa.schema([("ts_code", _S), ("trade_date", _S), ("up_limit", _D),
                            ("down_limit", _D), ("limit_pct", _D), ("limit_basis", _S)]),
    "suspend_d": pa.schema([("ts_code", _S), ("trade_date", _S), ("suspend_type", _S),
                            ("suspend_timing", _S)]),
    "trade_cal": pa.schema([("exchange", _S), ("cal_date", _S), ("is_open", pa.int32()),
                            ("pretrade_date", _S)]),
    "stock_basic": pa.schema([("ts_code", _S), ("symbol", _S), ("name", _S),
                              ("exchange", _S), ("list_status", _S), ("list_date", _S),
                              ("delist_date", _S)]),
    "quotes": pa.schema([("ts_code", _S), ("trade_date", _S), ("open", _D), ("high", _D),
                         ("low", _D), ("close", _D), ("pre_close", _D), ("volume", _D),
                         ("amount", _D), ("turn", _D), ("trade_status", pa.int8()),
                         ("is_st", pa.bool_())]),
}


class PublicBuildError(RuntimeError):
    pass


def _writer(name: str, path: Path) -> pq.ParquetWriter:
    cfg.create_dir(path.parent)
    return pq.ParquetWriter(path, SCHEMAS[name], compression="zstd")


def _harden(path: Path) -> None:
    """红线 5：umask 002 下 pyarrow 落 0664。"""
    try:
        path.chmod(0o600)
    except OSError:                                        # pragma: no cover
        pass


# ================================================================ 主构建

def build_tables(codes: "list[str] | None" = None, *, verbose: bool = True) -> dict[str, Any]:
    """一趟扫过公开源，同时长出 `quotes` + 四张表（`trade_cal`/`stock_basic` 末尾单独写）。

    **一趟**是刻意的：分几趟各读一遍 `bs_cache` 会让几张表有机会来自
    「同一份缓存的不同时刻」，而缓存是可续跑的（随时可能被补上几只票）。
    一趟出全部，表与表天然同源。
    """
    t0 = time.time()
    codes = codes or S.union_codes()
    basic = S.read_basic().set_index("ts_code")
    cfg.create_dir(TABLES_DIR)
    cfg.create_dir(BUILD_DIR)

    stats: dict[str, Any] = {
        "codes": 0, "codes_missing_basic": [], "quote_rows": 0, "daily_rows": 0,
        "suspend_rows": 0, "limit_rows": 0, "limit_no_limit_rows": 0,
        "limit_skipped_no_preclose": 0, "adj_rows": 0, "adj_codes_without_events": 0,
        "trade_status_0": 0, "trade_status_1": 0,
        "st_rows": 0, "s_share_codes": [],
    }
    trading_days: set[str] = set()

    writers = {n: _writer(n, TABLES_DIR / f"{n}.parquet")
               for n in ("daily", "adj_factor", "stk_limit", "suspend_d")}
    writers["quotes"] = _writer("quotes", QUOTES_PARQUET)
    try:
        for i, code in enumerate(codes, 1):
            q = S.read_quote_file(code)
            if len(q) == 0:
                raise PublicBuildError(f"{code}：缓存里 0 行 —— 零行不是「拉过了」")
            stats["codes"] += 1
            stats["quote_rows"] += len(q)
            n0 = int((q["trade_status"] == 0).sum())
            stats["trade_status_0"] += n0
            stats["trade_status_1"] += len(q) - n0
            stats["st_rows"] += int(q["is_st"].sum())
            trading_days.update(q["trade_date"].tolist())

            writers["quotes"].write_table(pa.Table.from_pandas(
                q, schema=SCHEMAS["quotes"], preserve_index=False))

            # -- daily：**只有真的交易了的行**（停牌行进 suspend_d）
            traded = q[q["trade_status"] == 1]
            d = traded[["ts_code", "trade_date", "open", "high", "low", "close",
                        "pre_close", "amount", "volume"]].copy()
            d["volume"] = d["volume"].astype("float64")
            stats["daily_rows"] += len(d)
            writers["daily"].write_table(pa.Table.from_pandas(
                d, schema=SCHEMAS["daily"], preserve_index=False))

            # -- suspend_d：tradestatus=0 → 一条 'S'（卡 2.5 §4 的差异落点）
            halted = q[q["trade_status"] == 0]
            if len(halted):
                s = pd.DataFrame({
                    "ts_code": halted["ts_code"].astype(str).values,
                    "trade_date": halted["trade_date"].values,
                    "suspend_type": "S",
                    "suspend_timing": pd.Series([None] * len(halted), dtype=object),
                })
                stats["suspend_rows"] += len(s)
                writers["suspend_d"].write_table(pa.Table.from_pandas(
                    s, schema=SCHEMAS["suspend_d"], preserve_index=False))

            # -- stk_limit：推导（§3）
            meta = basic.loc[code] if code in basic.index else None
            if meta is None:
                stats["codes_missing_basic"].append(code)
            name = str(meta["name"]) if meta is not None else ""
            s_share = S.is_s_share(name)
            if s_share:
                stats["s_share_codes"].append(code)
            lim = _derive_limits(q, code=code,
                                 list_date=(str(meta["list_date"]) if meta is not None else None),
                                 is_s_share=s_share)
            stats["limit_rows"] += len(lim)
            if len(lim):
                stats["limit_no_limit_rows"] += int(
                    (lim["up_limit"] >= cfg.NO_PRICE_LIMIT_UP_MIN).sum())
                writers["stk_limit"].write_table(pa.Table.from_pandas(
                    lim, schema=SCHEMAS["stk_limit"], preserve_index=False))
            stats["limit_skipped_no_preclose"] += len(q) - len(lim)

            # -- adj_factor：事件流摊平到这只票的每个有行日
            events = S.read_adj_events(code)
            if len(events) == 0:
                stats["adj_codes_without_events"] += 1
            adj = pd.DataFrame({
                "ts_code": q["ts_code"].astype(str).values,
                "trade_date": q["trade_date"].values,
                "adj_factor": S.expand_adj(events, q["trade_date"].tolist()),
            })
            stats["adj_rows"] += len(adj)
            writers["adj_factor"].write_table(pa.Table.from_pandas(
                adj, schema=SCHEMAS["adj_factor"], preserve_index=False))

            if verbose and i % 500 == 0:
                el = time.time() - t0
                print(f"  {i}/{len(codes)} 只，{el/60:.1f} 分钟，"
                      f"预计还要 {(len(codes)-i)*el/i/60:.0f} 分钟", flush=True)
    finally:
        for w in writers.values():
            w.close()
    for n in ("daily", "adj_factor", "stk_limit", "suspend_d"):
        _harden(TABLES_DIR / f"{n}.parquet")
    _harden(QUOTES_PARQUET)

    stats.update(build_trade_cal(sorted(trading_days)))
    stats.update(build_stock_basic())
    stats["seconds"] = round(time.time() - t0, 1)
    if verbose:
        print(f"表全部落好，{stats['seconds']/60:.1f} 分钟", flush=True)
    return stats


# ---------------------------------------------------------------- 涨跌停

def _derive_limits(q: pd.DataFrame, *, code: str, list_date: "str | None",
                   is_s_share: bool) -> pd.DataFrame:
    """按 `snapshots/public/limits.py` 逐行推这只票的涨跌停价。

    **`days_listed` 的口径**：含当日在内、上市以来的交易日序号。缓存窗口从
    2009-01-05 起，比它更早上市的票在窗口里拿不到真正的序号 —— 那种情况直接
    加一个大偏移（一定不是新股），**不是**传 `None`：传 `None` 会被 `derive()`
    读成「上市日未知」，reason 里多一句免责声明，而结果其实是确定的。

    **前收缺失的行不产出** —— `up_limit=None` 在这里只允许有一个含义
    （「无涨跌幅限制」），两种含义共用一个空值，下游就分不开了。
    """
    dates = q["trade_date"].tolist()
    pre = q["pre_close"].to_numpy(dtype="float64")
    st = q["is_st"].to_numpy(dtype=bool)
    rank = np.arange(1, len(dates) + 1, dtype=np.int64)
    listed_before_window = bool(list_date) and str(list_date) < S.WINDOW_START
    if listed_before_window:
        rank = rank + 10_000          # 一定不是新股
    ex = code.split(".")[-1].upper()
    sent_up, sent_dn = LM.ORACLE_NO_LIMIT_SENTINEL.get(ex, (99999.999, 0.01))

    up_out: list[float] = []
    dn_out: list[float] = []
    pct_out: list[float] = []
    why_out: list[str] = []
    keep: list[int] = []
    for k, day in enumerate(dates):
        p = pre[k]
        if not np.isfinite(p) or p <= 0:
            continue                   # 前收缺失 —— 不产出这一行
        lim = LM.derive(code, day, float(p), is_st=bool(st[k]),
                        days_listed=int(rank[k]) if list_date else None,
                        is_s_share=is_s_share, delisting_first_day=False)
        keep.append(k)
        if lim.up is None:
            up_out.append(sent_up)
            dn_out.append(sent_dn)
        else:
            up_out.append(lim.up)
            dn_out.append(lim.down)
        pct_out.append(np.nan if lim.pct is None else lim.pct)
        why_out.append(lim.reason)
    if not keep:
        return pd.DataFrame({f.name: pd.Series(dtype="object") for f in SCHEMAS["stk_limit"]})
    idx = np.asarray(keep, dtype=np.int64)
    return pd.DataFrame({
        "ts_code": q["ts_code"].astype(str).to_numpy()[idx],
        "trade_date": np.asarray(dates, dtype=object)[idx],
        "up_limit": np.asarray(up_out, dtype="float64"),
        "down_limit": np.asarray(dn_out, dtype="float64"),
        "limit_pct": np.asarray(pct_out, dtype="float64"),
        "limit_basis": np.asarray(why_out, dtype=object),
    })


# ---------------------------------------------------------------- 日历 / 基础信息

def build_trade_cal(trading_days: list[str]) -> dict[str, Any]:
    """交易日历。

    **自然日全覆盖**：窗口内每一天都有一行，`is_open` 说明它开不开市 ——
    只写交易日的话，「2026-07-04 是不是交易日」这个问题在公开通道上
    只能靠「查不到」来回答，而「查不到」与「不是交易日」是两件事。

    `pretrade_date` = **严格早于**本行的最后一个交易日；第一天没有前一天，落空。
    """
    if not trading_days:
        raise PublicBuildError("交易日集合为空 —— 零天不是「建好了」")
    open_set = set(trading_days)
    lo = dt.date.fromisoformat(f"{S.WINDOW_START[:4]}-{S.WINDOW_START[4:6]}-{S.WINDOW_START[6:]}")
    hi = dt.date.fromisoformat(f"{S.WINDOW_END[:4]}-{S.WINDOW_END[4:6]}-{S.WINDOW_END[6:]}")
    rows_date: list[str] = []
    rows_open: list[int] = []
    rows_pre: list[Any] = []
    prev: Any = None
    day = lo
    while day <= hi:
        c = day.strftime("%Y%m%d")
        is_open = 1 if c in open_set else 0
        rows_date.append(c)
        rows_open.append(is_open)
        rows_pre.append(prev)
        if is_open:
            prev = c
        day += dt.timedelta(days=1)
    frame = pd.DataFrame({
        "exchange": CALENDAR_EXCHANGE, "cal_date": rows_date,
        "is_open": np.asarray(rows_open, dtype="int32"),
        "pretrade_date": pd.Series(rows_pre, dtype=object),
    })
    path = TABLES_DIR / "trade_cal.parquet"
    pq.write_table(pa.Table.from_pandas(frame, schema=SCHEMAS["trade_cal"],
                                        preserve_index=False), path, compression="zstd")
    _harden(path)
    return {"calendar_days": len(frame), "calendar_open_days": int(sum(rows_open)),
            "calendar_start": rows_date[0], "calendar_end": rows_date[-1]}


def build_stock_basic() -> dict[str, Any]:
    b = S.read_basic()
    frame = pd.DataFrame({
        "ts_code": b["ts_code"].values,
        "symbol": [c.split(".")[0] for c in b["ts_code"]],
        "name": b["name"].values,
        "exchange": ["SSE" if c.endswith(".SH") else ("SZSE" if c.endswith(".SZ") else "BSE")
                     for c in b["ts_code"]],
        "list_status": b["list_status"].values,
        "list_date": b["list_date"].values,
        "delist_date": b["delist_date"].values,
    })
    path = TABLES_DIR / "stock_basic.parquet"
    pq.write_table(pa.Table.from_pandas(frame, schema=SCHEMAS["stock_basic"],
                                        preserve_index=False), path, compression="zstd")
    _harden(path)
    return {"stock_basic_rows": len(frame)}


# ================================================================ tradability

def _tradability_metadata(valid_from: str, valid_to: str, days: int) -> dict[bytes, bytes]:
    """公开通道 `tradability` 的 parquet metadata。

    **不复用私有那份**：那份写着「row_domain = listing_window ∪ daily ∪ stk_limit
    ∪ suspend_d」且源是湖；公开通道的行域与停牌证据来自另一个源，抄过去就是撒谎。
    """
    meta = {
        "genebench_card": "1.1-a（公开通道；判定逻辑复用卡 1.2 的 classify）",
        "table": "tradability",
        "channel": "public",
        "generator": "snapshots/public/tables.py",
        "source": "baostock query_history_k_data_plus(adjustflag=3) + query_stock_basic",
        "freeze_line": cfg.FREEZE_DATE,
        "beyond_freeze_line": "false",
        "valid_from": valid_from,
        "valid_to": valid_to,
        "n_trading_days_in_grid": str(days),
        "calendar": "公开源日线里出现过的交易日（3,575 只票的并集），只有沪深",
        "statuses": ",".join(cfg.TRADABILITY_STATUSES),
        "suspend_evidence": (
            "公开源**有行**且 tradestatus=0 即停牌（私有湖是**缺行**）；"
            "这些行写进公开 suspend_d 表并按 suspend_type='S' 参与判定，"
            "所以 suspend_basis='suspend_d_S' 在公开通道的含义是"
            "「当天 baostock 说 tradestatus=0」——**不是**私有 suspend_d 的 S 行。"
        ),
        "limits": ("涨跌停价由 snapshots/public/limits.py 从 preclose 推导（卡 2.5 §3）；"
                   "「无限制」照抄私有哨兵编码；退市整理期首日那条规则**推不出来**"
                   "（判据 namechange 是私有表）"),
        "row_domain": "listing_window ∪ 公开源行（含 tradestatus=0 的行）",
        "warning": "has_limit=False 时四个触板列全 False —— 那是**没法判**不是**没触板**。",
    }
    return {k.encode(): str(v).encode() for k, v in meta.items()}


def _load_for_tradability() -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """读回公开表，供逐年建视图。"""
    q = pq.read_table(QUOTES_PARQUET, columns=["ts_code", "trade_date", "close", "high",
                                               "low", "volume", "trade_status"]).to_pandas()
    lim = pq.read_table(TABLES_DIR / "stk_limit.parquet",
                        columns=["ts_code", "trade_date", "up_limit", "down_limit"]).to_pandas()
    cal = pq.read_table(TABLES_DIR / "trade_cal.parquet").to_pandas()
    days = cal.loc[cal["is_open"] == 1, "cal_date"].astype(str).tolist()
    return q, lim, days


def build_tradability(*, verbose: bool = True) -> dict[str, Any]:
    """逐年建公开通道的 `tradability`，判定逻辑**复用卡 1.2 的 `tr.classify`**。

    复用而不是另写一份：「三态怎么判」是**口径**。两条通道各写一份判定的话，
    差异就会长在判定里，而卡 2.5 §4 要的恰恰是「差异只在源，不在判定」。
    """
    t0 = time.time()
    quotes, lim, days = _load_for_tradability()
    idx_of = {d: i for i, d in enumerate(days)}
    basic = S.read_basic().set_index("ts_code")

    quotes["date_idx"] = quotes["trade_date"].map(idx_of)
    off_grid = int(quotes["date_idx"].isna().sum())
    if off_grid:
        raise PublicBuildError(f"{off_grid} 行行情落在日历之外 —— 日历不是从这份行情来的？")
    quotes["date_idx"] = quotes["date_idx"].astype("int64")
    lim["date_idx"] = lim["trade_date"].map(idx_of).astype("int64")

    years = sorted({int(d[:4]) for d in days})
    day_arr = np.asarray(days)
    carry: dict[str, bool] = {}
    out: dict[str, Any] = {"years": {}, "rows": 0, "status_counts": {}}
    for year in years:
        positions = [i for i, d in enumerate(days) if d[:4] == str(year)]
        i0, i1 = positions[0], positions[-1]
        frame = _span(quotes, lim, basic, days, day_arr, i0, i1, carry_in=carry)
        carry = tr._carry_out(frame, i1)
        path = tr.year_partition_path(year, TRADABILITY_DIR)
        art = tr._write_parquet(frame, path, _tradability_metadata(
            days[i0], days[i1], len(positions)))
        out["years"][str(year)] = {"rows": art["rows"], "sha256": art["sha256"][:16]}
        out["rows"] += art["rows"]
        for s, n in frame["status"].value_counts().items():
            out["status_counts"][s] = out["status_counts"].get(s, 0) + int(n)
        if verbose:
            print(f"  {year}: {art['rows']:,} 行", flush=True)
    out["seconds"] = round(time.time() - t0, 1)
    return out


def _span(quotes: pd.DataFrame, lim: pd.DataFrame, basic: pd.DataFrame,
          days: list[str], day_arr: np.ndarray, i0: int, i1: int,
          carry_in: "dict[str, bool] | None") -> pd.DataFrame:
    """一年的宽表。行域 = 在市窗口 ∪ 公开源行（**与私有通道同构**）。"""
    lo_day, hi_day = days[i0], days[i1]
    windows: dict[str, tuple[int, int]] = {}
    for code, row in basic.iterrows():
        ld = str(row["list_date"] or "")
        if not ld:
            continue
        dd = str(row["delist_date"] or "")
        a = int(np.searchsorted(day_arr, max(ld, lo_day), side="left"))
        # 退市日**当天不在市**（与私有 `list_date <= D < delist_date` 同）
        if dd and dd <= hi_day:
            b = int(np.searchsorted(day_arr, dd, side="left")) - 1
        else:
            b = i1
        a, b = max(a, i0), min(b, i1)
        if a <= b:
            windows[code] = (a, b)
    w_code, w_idx = tr._domain_from_windows(windows, i0, i1)

    q = quotes[(quotes["date_idx"] >= i0) & (quotes["date_idx"] <= i1)]
    universe = set(q["ts_code"].unique())
    dom = pd.DataFrame({
        "code": np.concatenate([w_code, q["ts_code"].to_numpy(dtype=object)]),
        "date_idx": np.concatenate([w_idx, q["date_idx"].to_numpy(dtype=np.int64)]),
    })
    # 只保留公开通道建了的票（`basic` 是全市场，行域不该长出没有数据的票）
    dom = dom[dom["code"].isin(universe)].drop_duplicates(["code", "date_idx"])

    qq = q.rename(columns={"ts_code": "code"})[
        ["code", "date_idx", "close", "high", "low", "volume", "trade_status"]]
    frame = dom.merge(qq, on=["code", "date_idx"], how="left")
    ll = lim[(lim["date_idx"] >= i0) & (lim["date_idx"] <= i1)].rename(
        columns={"ts_code": "code"})[["code", "date_idx", "up_limit", "down_limit"]]
    frame = frame.merge(ll, on=["code", "date_idx"], how="left")

    frame["has_daily"] = (frame["trade_status"] == 1).to_numpy()
    frame["has_limit"] = frame["up_limit"].notna().to_numpy()
    # `tradestatus=0` = 当天有直接停牌证据（公开 suspend_d 里那条 'S'）。
    frame["suspend_flag"] = np.where(frame["trade_status"] == 0, "S", None)
    frame["suspend_timing"] = pd.Series([None] * len(frame), dtype=object)
    # 停牌行的 OHLC 在公开源里是 preclose 的复读、成交量 0 —— **不是行情**。
    # 原样搬进来的话 status 会判成 `trade`（有行、没封板），而私有通道那天是
    # `suspend`：卡 2.5 §4 说的那条差异就漏进 gold 了。
    for c in ("close", "high", "low", "volume"):
        frame[c] = np.where(frame["has_daily"], frame[c], np.nan)

    if windows:
        bounds = pd.DataFrame([(c, a, b) for c, (a, b) in windows.items()],
                              columns=["code", "_wlo", "_whi"])
        frame = frame.merge(bounds, on="code", how="left")
        in_win = ((frame["date_idx"] >= frame["_wlo"]) &
                  (frame["date_idx"] <= frame["_whi"])).fillna(False)
        frame = frame.drop(columns=["_wlo", "_whi"])
    else:
        in_win = pd.Series(False, index=frame.index)
    frame["in_listing_window"] = in_win.to_numpy(dtype=bool)

    frame["date_compact"] = [days[i] for i in frame["date_idx"].to_numpy()]
    frame = frame.sort_values(["code", "date_idx"]).reset_index(drop=True)
    frame = tr.classify(frame, carry_in=carry_in)
    frame["date"] = pd.to_datetime(frame["date_compact"], format="%Y%m%d").dt.date
    return frame


# ================================================================ 清单

def _sha256(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_head() -> str:
    import subprocess
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(cfg.REPO),
                              capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):           # pragma: no cover
        return "unknown"


def write_manifest(root: Path, *, kind: str, extra: "dict[str, Any] | None" = None) -> dict:
    """给一个产物目录写 `MANIFEST.sha256`（逐文件）与 `build_info.json`。

    大产物不进 git —— 那么「这份东西是什么、从哪来、什么时候建的」就只能
    跟着产物走。两个文件都落在产物目录里，随 rsync / 打包一起走。
    """
    entries: list[str] = []
    total = 0
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.name in ("MANIFEST.sha256", "build_info.json"):
            continue
        size = p.stat().st_size
        total += size
        entries.append(f"{_sha256(p)}  {size}  {p.relative_to(root)}")
    man = root / "MANIFEST.sha256"
    man.write_text("\n".join(entries) + "\n", encoding="utf-8")
    _harden(man)
    info: dict[str, Any] = {
        "kind": kind,
        "channel": "public",
        "card": "1.1-a",
        "source": ("baostock：query_history_k_data_plus(adjustflag=3) / "
                   "query_adjust_factor / query_stock_basic"),
        "window": {"start": S.WINDOW_START, "end": S.WINDOW_END},
        "freeze_line": cfg.FREEZE_DATE,
        "built_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "code_head": _git_head(),
        "files": len(entries),
        "bytes": total,
        "manifest_sha256": _sha256(man),
    }
    if extra:
        info.update(extra)
    path = root / "build_info.json"
    path.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    _harden(path)
    return info
