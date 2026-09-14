# -*- coding: utf-8 -*-
"""公开源（baostock）的**归一化读取层**（卡 1.1-a）。

上游是 N-68 那一轮拉下来的原始缓存：

* `$GB/scratch/bs_cache/<ts_code>.parquet` —— 日线，`adjustflag=3`（不复权），
  字段 `date,code,open,high,low,close,preclose,volume,amount,turn,tradestatus,isST`，
  **全列都是字符串**（baostock 的 `get_row_data()` 就是字符串）；
* `$GB/scratch/bs_adj_cache/<ts_code>.parquet` —— 复权因子事件流（`snapshots.public.fetch_adj`）；
* `$GB/scratch/bs_basic.parquet` —— `query_stock_basic` 全量（`snapshots.public.fetch_basic`）。

**本模块只做归一化，不做判定**。判定（涨跌停、可交易性）在 `limits.py` / `tables.py`。

三条口径写在这里，别的地方不要再写第二份：

1. **码的形态**：对外一律用湖的写法 `600000.SH`（不是 `sh.600000`，也不是 `SH600000`）。
   三种写法混用踩过一次（N-68 的「已缓存 0 只」）。
2. **日期形态**：一律紧凑串 `YYYYMMDD` —— 私有快照表的 `trade_date` 就是这个形状，
   两条通道的表要能逐列比对，形状必须一样。
3. **单位**：baostock 的 `amount` 已经是**元**、`volume` 是**股**（N-67 的 B2 实测：
   `low <= amount/volume <= high` 在 5,439 行上 ratio 1.000000）。**不做任何换算** ——
   这里乘一个 1000 的表现是 792 条因子里凡是用 `vwap` 的全部差 1000 倍，而 gold 照常算得出数。
"""
from __future__ import annotations

import pathlib
from typing import Iterator

import numpy as np
import pandas as pd

import genebench_config as cfg

#: 日线缓存（N-68 那一轮的产物，本卡只读不写）。
BS_CACHE: pathlib.Path = cfg.GENEBENCH_ROOT / "scratch" / "bs_cache"
#: 复权因子缓存（`snapshots.public.fetch_adj` 的产物）。
ADJ_CACHE: pathlib.Path = cfg.GENEBENCH_ROOT / "scratch" / "bs_adj_cache"
#: `query_stock_basic` 全量缓存（`snapshots.public.fetch_basic` 的产物）。
BASIC_CACHE: pathlib.Path = cfg.GENEBENCH_ROOT / "scratch" / "bs_basic.parquet"
#: v1 三宇宙并集名单（qlib 写法，3,575 只）。
UNION_FILE: pathlib.Path = cfg.GENEBENCH_ROOT / "scratch" / "v1_union.txt"

#: 公开通道的窗口。左端是缓存里最早的一天，右端是**冻结线**（红线 7）。
WINDOW_START: str = "20090105"
WINDOW_END: str = cfg.FREEZE_DATE.replace("-", "")

#: 归一化之后的行情列（`quotes` 中间产物）。
QUOTE_COLUMNS: tuple[str, ...] = (
    "ts_code", "trade_date", "open", "high", "low", "close", "pre_close",
    "volume", "amount", "turn", "trade_status", "is_st",
)

_NUMERIC = ("open", "high", "low", "close", "pre_close", "volume", "amount", "turn")


class PublicSourceError(RuntimeError):
    pass


# ------------------------------------------------------------------ 码与日期

def to_lake_code(code: str) -> str:
    """`sh.600000` / `SH600000` / `600000.SH` → `600000.SH`。"""
    c = code.strip().upper()
    if "." in c:
        a, b = c.split(".", 1)
        return f"{a}.{b}" if a[:1].isdigit() else f"{b}.{a}"
    if len(c) > 2 and c[:2] in ("SH", "SZ", "BJ"):
        return f"{c[2:]}.{c[:2]}"
    raise PublicSourceError(f"认不出的代码写法：{code!r}")


def to_bs_code(code: str) -> str:
    """`600000.SH` → `sh.600000`。"""
    lake_code = to_lake_code(code)
    num, ex = lake_code.split(".")
    return f"{ex.lower()}.{num}"


def compact(date: str) -> str:
    """`2026-07-31` / `20260731` → `20260731`。"""
    d = str(date).strip().replace("-", "")
    if len(d) != 8 or not d.isdigit():
        raise PublicSourceError(f"认不出的日期：{date!r}")
    return d


def union_codes() -> list[str]:
    """并集名单，湖写法，去重且**保持文件里的顺序**（可复现）。"""
    if not UNION_FILE.is_file():
        raise PublicSourceError(f"缺 {UNION_FILE} —— 先跑并集计算（N-68）")
    out, seen = [], set()
    for line in UNION_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        c = to_lake_code(line)
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


# ------------------------------------------------------------------ 日线

def read_quote_file(code: str) -> pd.DataFrame:
    """读一只票的日线缓存并归一化。缓存里没有 → 抛（**不静默返回空表**）。"""
    path = BS_CACHE / f"{to_lake_code(code)}.parquet"
    if not path.is_file():
        raise PublicSourceError(f"{code} 的日线缓存不在：{path}")
    raw = pd.read_parquet(path)
    out = pd.DataFrame()
    out["ts_code"] = pd.Series([to_lake_code(code)] * len(raw), dtype="string")
    out["trade_date"] = raw["date"].astype(str).str.replace("-", "", regex=False)
    for c, src in (("open", "open"), ("high", "high"), ("low", "low"),
                   ("close", "close"), ("pre_close", "preclose"),
                   ("volume", "volume"), ("amount", "amount"), ("turn", "turn")):
        out[c] = pd.to_numeric(raw[src], errors="coerce")
    # `tradestatus` 是**字符串** '1'/'0'。`astype(bool)` 会把 '0' 判成 True ——
    # 那样全市场的停牌行会被当成交易行，而 gold 照常算得出数。
    out["trade_status"] = pd.to_numeric(raw["tradestatus"], errors="coerce").fillna(-1).astype("int8")
    out["is_st"] = pd.to_numeric(raw["isST"], errors="coerce").fillna(0).astype("int8") == 1
    out = out[(out["trade_date"] >= WINDOW_START) & (out["trade_date"] <= WINDOW_END)]
    bad = out["trade_status"][~out["trade_status"].isin((0, 1))]
    if len(bad):
        raise PublicSourceError(f"{code}：tradestatus 出现 {sorted(set(bad))} —— 只认 0/1")
    return out[list(QUOTE_COLUMNS)].sort_values("trade_date").reset_index(drop=True)


def iter_quotes(codes: list[str], *, chunk: int = 400) -> Iterator[pd.DataFrame]:
    """按 `chunk` 只票一批产出归一化日线。1,100 万行不一次性握在手里。"""
    buf: list[pd.DataFrame] = []
    for i, code in enumerate(codes, 1):
        buf.append(read_quote_file(code))
        if i % chunk == 0:
            yield pd.concat(buf, ignore_index=True)
            buf = []
    if buf:
        yield pd.concat(buf, ignore_index=True)


# ------------------------------------------------------------------ 复权因子

def read_adj_events(code: str) -> pd.DataFrame:
    """一只票的复权事件流：`(trade_date, adj_factor)`，按日期升序。

    取 `backAdjustFactor`（**后复权**）—— 与私有通道 `adj_factor` 的方向一致
    （私有那列也是随时间单调累计的后复权因子）。两条通道的**绝对值不同**
    （不同源各有各的基准），但 provider 只用 `adj(t)/adj(L_c)` 这个比值，
    比值与基准无关，所以复权后的价格是可比的 —— 这一条写进数据卡。
    """
    path = ADJ_CACHE / f"{to_lake_code(code)}.parquet"
    if not path.is_file():
        raise PublicSourceError(f"{code} 的复权因子缓存不在：{path}（先跑 snapshots.public.fetch_adj）")
    raw = pd.read_parquet(path)
    if len(raw) == 0:
        return pd.DataFrame({"trade_date": pd.Series(dtype=str),
                             "adj_factor": pd.Series(dtype="float64")})
    out = pd.DataFrame({
        "trade_date": raw["dividOperateDate"].astype(str).str.replace("-", "", regex=False),
        "adj_factor": pd.to_numeric(raw["backAdjustFactor"], errors="coerce"),
    })
    out = out[np.isfinite(out["adj_factor"]) & (out["adj_factor"] > 0)]
    return out.sort_values("trade_date").drop_duplicates("trade_date", keep="last").reset_index(drop=True)


def expand_adj(events: pd.DataFrame, dates: "list[str] | np.ndarray") -> np.ndarray:
    """把事件流摊平到给定交易日上：取 `<= t` 的最后一个事件值，之前一律 **1.0**。

    「之前一律 1.0」只在事件流**含上市日那条**时成立 —— 所以 `fetch_adj` 从
    1990-01-01 拉（实测：`sz.300750` / `sh.688111` / `sz.002415` 的第一条都是
    上市日、值 1.000000）。只从 2009 拉的话，`sh.600000` 的第一条是 2.969727，
    「之前是 1.0」当场变成一个**系统性错的**假设，而价格照样算得出来。
    """
    d = np.asarray([compact(x) for x in dates], dtype=object)
    if len(events) == 0:
        return np.ones(len(d), dtype="float64")
    ev_d = events["trade_date"].to_numpy(dtype=object)
    ev_v = events["adj_factor"].to_numpy(dtype="float64")
    pos = np.searchsorted(ev_d.astype(str), d.astype(str), side="right") - 1
    out = np.where(pos >= 0, ev_v[np.clip(pos, 0, None)], 1.0)
    return out.astype("float64")


# ------------------------------------------------------------------ 基础信息

#: `query_stock_basic` 的 `type`：1=股票 2=指数 3=其它 4=可转债 5=ETF。
BS_TYPE_STOCK = "1"


def read_basic() -> pd.DataFrame:
    """`stock_basic` 归一化：`ts_code / name / list_date / delist_date / list_status`。"""
    if not BASIC_CACHE.is_file():
        raise PublicSourceError(f"缺 {BASIC_CACHE} —— 先跑 `snapshots.public.fetch_basic`")
    raw = pd.read_parquet(BASIC_CACHE)
    keep = raw[raw["type"].astype(str) == BS_TYPE_STOCK].copy()
    out = pd.DataFrame({
        "ts_code": [to_lake_code(c) for c in keep["code"]],
        "name": keep["code_name"].astype(str).values,
        "list_date": keep["ipoDate"].astype(str).str.replace("-", "", regex=False).values,
        "delist_date": keep["outDate"].astype(str).str.replace("-", "", regex=False).values,
        # baostock `status`：1=上市 0=退市。翻成湖的 `L`/`D` 两档。
        "list_status": np.where(keep["status"].astype(str).values == "1", "L", "D"),
    })
    out["delist_date"] = out["delist_date"].replace({"": None})
    return out.sort_values("ts_code").reset_index(drop=True)


def is_s_share(name: str) -> bool:
    """S 股（股权分置改革未完成）：名字以 `S` 开头且**不是** `ST` / `*ST`。

    全市场只有 `600182.SH`「S佳通」（N-67 实测）。样本只有一只 ——
    结论按「观测到的」写，不按「规则应该是」写。
    """
    n = str(name).strip().upper().replace(" ", "")
    return n.startswith("S") and not n.startswith("ST")
