# -*- coding: utf-8 -*-
"""卡 2.1a：从 v1 快照自建**冻结的** qlib bin provider（方案 C）。

    cd $REPO && ulimit -n 8192 && $GENEBENCH_ROOT/env/bin/python -m snapshots.qlib_provider

为什么不用现成的两份 provider（这是签字人裁定的，原话摘要）：

1. **S3 主指标 Fid% 是被测因子值对 gold 的秩相关。** gold 若算自社区 bin、
   而 agent 拿到的是网关快照，任何不一致都**无法归因**是 agent 错还是数据本来就不同 ——
   主指标不可解释，并会污染"跨后端一致性"这个署名指标。
2. τ 是要签字的数字，标定口径必须与评测口径是**同一份数据**。
3. 本方案下 provider 日历里**物理上没有**冻结线之后的交易日 ——
   红线 7 从"每次调用的自觉"变成**结构保证**。

"先 A 后 C"的折中**不采纳**：两版 τ 只有一版能用，且日后容易被误引。

--------------------------------------------------------------------------
口径（全部写进数据卡，改动任何一条都要重标 τ）
--------------------------------------------------------------------------

**单位（实证得出，不是按文档假设）** —— 湖 `daily` 的 `amount` 单位是**元**、
`volume` 单位是**股**，换算系数 **1**。判据是签字人给的那条硬判据：
``low <= amount/volume <= high`` 在 **99.9843%** 的行上成立（相对容差 1e-6，
全表 14,581,977 行）。逐年都在 99.6% 以上，中位 ``vwap/close ≈ 1.0``，
说明单位没有中途变过。

> 这条判据比任何文档核对都硬：tushare 原生是 `amount` 千元 / `vol` 手，
> 直接相除会得到 10 倍的数；我们的湖在 platform 流水线里已经归一过。
> **社区 release 的 `amount` 恰好还是千元**（实测 `amount_社区/amount_湖 = 0.001`，
> 4,221 天里只有 1 个取值），跨源比对时会踩这个 1000 倍 —— 已记在数据卡。

**vwap** = ``amount / volume``（原始值），再随价格一起复权。
``volume`` 为 0 或 NULL 时 vwap 记 **NULL**，不记 inf/0 ——
这正是我们要测 agent 的 S3-ROB-02（非有限值安全传播），自己的 gold 里先别犯。
（实测本表 volume 为 0/NULL 的行 **0 条**，所以这条守门当前是**空转**的；
按 D-01 的判别力纪律，此处**明说没有实例**，不假装它被测过。）

**复权** —— 存**后复权价 + `factor` 列**，遵循 qlib 惯例
（Alpha158/360 的表达式假定 ``$close`` 是复权价；存原始价会改变全部因子语义）。
归一化基准**定死为冻结线**：

    L_c     = max{ t <= 2026-07-31 : adj_factor(c, t) 存在 }
    factor  = adj_factor(c, t) / adj_factor(c, L_c)
    价格类   = 原始价 × factor          (open/high/low/close/vwap)
    volume  = 原始股数 / factor
    amount  = 原始金额，**不复权**（钱就是钱，拆股不改变成交额）

于是 qlib 的不变式 ``$close / $factor == 原始收盘价`` 按构造成立，
并且额外白得一条**与复权无关**的恒等式：``vwap × volume == amount``（逐行精确）。
它是免费的内部一致性检查，已写成验收测试。

**冻结线当天在市的 5,548 只票 `factor(2026-07-31) = 1`，存储价 == 原始价。**
另有 **269 只**在冻结线前就已退市/停更，它们的基准是**自身最后一个有
adj_factor 的交易日**（该日 factor=1）—— 这是必要偏离，写在数据卡里，
因为"冻结线当天"对它们根本不存在。

**instruments** 取自卡 1.1 的 ``universe_pit`` **canonical** 口径（四个宇宙），
不用社区名单 —— 卡 1.1 的产出由此正式成为卡 2.1 的输入，数据面闭环。
``ambiguous`` 区段**照常保留**：provider 是数据层，不做筛选；
排除动作留在任务生成层。provider 静默丢弃它们的话，我们就有了两个不同的宇宙，
且日后无法测"在模糊区段上会发生什么"。

**calendar** 取自 ``trade_cal(SSE, is_open=1)`` 且截到 ``<= 2026-07-31``，共 4,269 天。
**这与卡 1.4 的规则不冲突**，两处规则不同、各自的理由是：

* 快照表 ``tables/trade_cal.parquet`` **保留** 153 行未来日历（capture_time 语义，
  T+N 对齐需要知道 8 月 3 日是不是交易日）；
* provider 的 ``calendars/day.txt`` 决定**因子表达式能在哪些日子求值**，
  必须停在冻结线 —— 冻结线之后本来就没有 bar 可算。

同理**不出 ``day_future.txt``**：它在 qlib 里就是"允许求值到未来"的开关。

**求值右端（会静默污染结果的那条约束）** —— 持有期 {1,5,20} 日下，
最后 h 个交易日的前向收益在冻结线内**不完整**。可用右端：

    h=1  -> 2026-07-30      h=5  -> 2026-07-24      h=20 -> 2026-07-03

三个数由 ``trade_cal`` 现数（``evaluation_right_edge()``），不写死。
它们必须进 ``calibration.json`` 并在评分器里**硬拦** ——
否则 20 日 IC 会在末段用截断/缺失的前向收益计算，被静默偏置，
**而且从指标数值上看不出来**。
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterator

import contextlib

import duckdb
import numpy as np

import genebench_config as cfg
from snapshots import lake

# ---------------------------------------------------------------- 落点

PROVIDER_DIR: Path = cfg.SNAPSHOTS_V1 / "qlib_provider"
CALENDAR_DIR: Path = PROVIDER_DIR / "calendars"
CALENDAR_FILE: Path = CALENDAR_DIR / "day.txt"
INSTRUMENTS_DIR: Path = PROVIDER_DIR / "instruments"
FEATURES_DIR: Path = PROVIDER_DIR / "features"
NORM_BASE_PARQUET: Path = PROVIDER_DIR / "norm_base.parquet"
MANIFEST: Path = PROVIDER_DIR / "manifest.json"
FILES_DIGEST: Path = PROVIDER_DIR / "files.sha256"

TABLES_DIR: Path = cfg.SNAPSHOTS_V1 / "tables"
FREEZE: str = lake.FREEZE_DATE_COMPACT

# ---------------------------------------------------------------- 通道（卡 1.1-a）
#
# 公开通道要**同一套构建逻辑**长出第二份 provider。做法是把「输入源与落点」
# 抽成一个上下文对象，**不复制一份新 builder** —— 复制的表现是两条通道的
# 复权/归一化口径慢慢漂开，而两边都照常算得出数（这正是卡 2.5 §3 那类错误的形态）。
#
# 默认上下文就是私有通道，取值与本节引入之前**逐字**相同：
# `paths().provider_dir is PROVIDER_DIR`、`paths().tables_dir is TABLES_DIR`。


class ProviderPaths:
    """一条通道的输入源与落点。

    **刻意不用 `@dataclass`**：`ops/test_qlib_provider.py` 会把本模块源码
    `exec()` 进一个不在 `sys.modules` 里的假模块来验护栏，而 dataclass 的
    `_is_type()` 要 `sys.modules[cls.__module__].__dict__` —— 那条测试会在
    护栏跑到之前就炸。朴素类零魔法，在哪儿 exec 都成立。
    """

    __slots__ = ("channel", "provider_dir", "tables_dir", "universe_pit", "data_card")

    def __init__(self, channel: str, provider_dir: Path, tables_dir: Path,
                 universe_pit: Path, data_card: Path) -> None:
        self.channel = channel
        self.provider_dir = provider_dir
        self.tables_dir = tables_dir
        self.universe_pit = universe_pit
        self.data_card = data_card

    def __repr__(self) -> str:
        return (f"ProviderPaths(channel={self.channel!r}, "
                f"provider_dir={self.provider_dir!s}, tables_dir={self.tables_dir!s})")

    @property
    def calendars(self) -> Path:
        return self.provider_dir / "calendars"

    @property
    def calendar_file(self) -> Path:
        return self.calendars / "day.txt"

    @property
    def instruments(self) -> Path:
        return self.provider_dir / "instruments"

    @property
    def features(self) -> Path:
        return self.provider_dir / "features"

    @property
    def norm_base(self) -> Path:
        return self.provider_dir / "norm_base.parquet"

    @property
    def manifest(self) -> Path:
        return self.provider_dir / "manifest.json"

    @property
    def files_digest(self) -> Path:
        return self.provider_dir / "files.sha256"


#: 私有通道（默认）。**这几个值必须与上面那组模块常量逐字相同** ——
#: 不同就意味着「默认行为变了」，而卡 1.1-a 的硬判据正是它没变。
PRIVATE_PATHS = ProviderPaths(
    channel="private",
    provider_dir=PROVIDER_DIR,
    tables_dir=TABLES_DIR,
    universe_pit=cfg.UNIVERSE_PIT_PARQUET,
    data_card=cfg.DATA_CARDS / "qlib_provider.md",
)

#: 公开通道（卡 1.1-a）。宇宙定义面**仍取私有 `universe_pit`** ——
#: 那是「谁在指数里」的定义，不是行情数据（卡 2.5 §1 第 4 项的裁定）。
PUBLIC_PATHS = ProviderPaths(
    channel="public",
    provider_dir=cfg.PUBLIC_PROVIDER_DIR,
    tables_dir=cfg.PUBLIC_TABLES_DIR,
    universe_pit=cfg.UNIVERSE_PIT_PARQUET,
    data_card=cfg.REPORTS / "public" / "qlib_provider_public.md",
)

PATHS_BY_CHANNEL: dict[str, ProviderPaths] = {
    "private": PRIVATE_PATHS, "public": PUBLIC_PATHS,
}

_CURRENT_PATHS: ProviderPaths = PRIVATE_PATHS


def paths() -> ProviderPaths:
    """当前上下文。默认私有通道。"""
    return _CURRENT_PATHS


@contextlib.contextmanager
def using(target: "ProviderPaths | str"):
    """在 `with` 块里把构建上下文切到另一条通道。

    日历缓存跟着一起换 —— 忘了换的表现是「公开 provider 用了私有日历」，
    而那种错**不会报错**：两条日历长得一模一样，只是内容来自另一份表。
    """
    global _CURRENT_PATHS, _CAL_CACHE
    tgt = PATHS_BY_CHANNEL[target] if isinstance(target, str) else target
    old, old_cal = _CURRENT_PATHS, _CAL_CACHE
    _CURRENT_PATHS, _CAL_CACHE = tgt, None
    try:
        yield tgt
    finally:
        _CURRENT_PATHS, _CAL_CACHE = old, old_cal

# ---------------------------------------------------------------- 口径常量

#: bin 字段。**只出 792 条因子真正要的 7 个 + qlib 惯例的 `factor`**。
#: 社区那份还有 `adjclose` 与 `change`：前者在"以冻结线重定基"下与 `close` 逐值相同，
#: 后者可由 `close` 求出 —— 都不出，少一个字段就少一处会漂的口径。
FIELDS: tuple[str, ...] = (
    "open", "high", "low", "close", "volume", "amount", "vwap", "factor",
)
#: 乘 factor。
PRICE_FIELDS: frozenset[str] = frozenset({"open", "high", "low", "close", "vwap"})
#: 除 factor（拆股会让股数跳变，除掉才连续）。
INVERSE_FIELDS: frozenset[str] = frozenset({"volume"})
#: 原样。`amount` 是钱；`factor` 自己就是因子。
AS_IS_FIELDS: frozenset[str] = frozenset({"amount", "factor"})

# D-03：显式字段清单必然会与分派表漂移，import 期钉死三分法是全覆盖且互斥的。
_PARTITION = (PRICE_FIELDS, INVERSE_FIELDS, AS_IS_FIELDS)
if set().union(*_PARTITION) != set(FIELDS):
    raise RuntimeError(
        f"复权分派表与 FIELDS 不等：分派 {sorted(set().union(*_PARTITION))} "
        f"vs FIELDS {sorted(FIELDS)}。加字段忘了归类 = 该字段会被静默按 as-is 写盘。"
    )
if sum(len(s) for s in _PARTITION) != len(FIELDS):
    raise RuntimeError("复权分派表有字段被归了两类。")

#: 持有期。与 `ops/specs/README.md` 第 4 条冻结项一致，不在这里另定。
HOLDING_PERIODS: tuple[int, ...] = (1, 5, 20)

#: vwap 单位判据的相对容差与通过线（签字人给的判据）。
VWAP_BAND_REL_TOL: float = 1e-6
VWAP_BAND_MIN_RATE: float = 0.99

#: 交易所后缀 → qlib 前缀。**不做猜测**：出现未知后缀直接抛。
_SUFFIX_TO_PREFIX: dict[str, str] = {"SH": "SH", "SZ": "SZ", "BJ": "BJ"}

__all__ = [
    "PROVIDER_DIR", "FIELDS", "HOLDING_PERIODS",
    "qlib_code", "ts_code", "calendar", "evaluation_right_edge",
    "read_bin", "build",
]


# ---------------------------------------------------------------- 码与日历

def qlib_code(code: str) -> str:
    """``600000.SH`` → ``SH600000``（instruments 文件里的写法，目录名取小写）。"""
    body, _, suffix = code.partition(".")
    prefix = _SUFFIX_TO_PREFIX.get(suffix.upper())
    if prefix is None or not body:
        raise ValueError(f"无法映射的 ts_code {code!r}；已知后缀 {sorted(_SUFFIX_TO_PREFIX)}")
    return f"{prefix}{body}"


def ts_code(qcode: str) -> str:
    """``SH600000`` → ``600000.SH``。"""
    q = qcode.strip().upper()
    prefix, body = q[:2], q[2:]
    if prefix not in _SUFFIX_TO_PREFIX or not body:
        raise ValueError(f"无法反解的 qlib code {qcode!r}")
    return f"{body}.{prefix}"


def _iso(compact: str) -> str:
    return f"{compact[:4]}-{compact[4:6]}-{compact[6:8]}"


def _compact(iso: str) -> str:
    return iso.replace("-", "")


_CAL_CACHE: list[str] | None = None


def calendar(refresh: bool = False) -> list[str]:
    """provider 日历：SSE 开市日、``<= 冻结线``，紧凑格式 ``YYYYMMDD``。

    直接读快照表，不读湖 —— provider 必须能在湖不可达时重建。
    """
    global _CAL_CACHE
    if _CAL_CACHE is not None and not refresh:
        return _CAL_CACHE
    con = duckdb.connect(":memory:")
    rows = con.execute(
        f"SELECT cal_date FROM read_parquet('{paths().tables_dir / 'trade_cal.parquet'}') "
        f"WHERE exchange='SSE' AND is_open=1 AND cal_date <= ? ORDER BY cal_date",
        [FREEZE],
    ).fetchall()
    con.close()
    _CAL_CACHE = [r[0] for r in rows]
    if not _CAL_CACHE:
        raise RuntimeError("provider 日历为空 —— 快照表 trade_cal 缺失或被截坏了。")
    if _CAL_CACHE[-1] > FREEZE:
        raise RuntimeError(f"日历越过冻结线：{_CAL_CACHE[-1]} > {FREEZE}")
    return _CAL_CACHE


def evaluation_right_edge(holding: int, cal: "list[str] | None" = None) -> str:
    """持有期 ``holding`` 日下，因子仍可求值的**最后一个交易日**（紧凑格式）。

    在 t 日收盘求值、收盘后调仓、持有 h 日 → 需要 ``t+h`` 日的收盘价。
    最后一个有价的日子是日历末端，所以 ``t <= cal[-(h+1)]``。

    **这个右端必须硬拦在评分器里。** 不拦的话，末段 h 天的前向收益是
    截断/缺失的，IC 会被静默偏置 —— 而指标数值上看不出来。
    """
    if holding < 1:
        raise ValueError(f"持有期必须 >= 1，收到 {holding}")
    days = calendar() if cal is None else cal
    if holding >= len(days):
        raise ValueError(f"持有期 {holding} >= 日历长度 {len(days)}")
    return days[-(holding + 1)]


def evaluation_right_edges(cal: "list[str] | None" = None) -> dict[int, str]:
    days = calendar() if cal is None else cal
    return {h: evaluation_right_edge(h, days) for h in HOLDING_PERIODS}


# ---------------------------------------------------------------- bin 读写

def _bin_path(code: str, field: str) -> Path:
    return paths().features / qlib_code(code).lower() / f"{field}.day.bin"


def read_bin(path: Path) -> tuple[int, np.ndarray]:
    """读 qlib ``.day.bin``：首个 float32 是**日历下标**，其后是 float32 数据。

    格式不是猜的：`qlib.data.storage.file_storage.FileFeatureStorage.__getitem__`
    里 ``fp.seek(4 * (i - storage_start_index) + 4)``，且已用社区 release 的
    ``sh600000`` 逐值复现过（``close/factor`` 反算出的原始价与湖一致）。
    """
    arr = np.fromfile(path, dtype="<f4")
    if arr.size < 1:
        raise ValueError(f"{path} 为空")
    return int(arr[0]), arr[1:]


def write_bin(path: Path, start_index: int, values: np.ndarray) -> None:
    if start_index < 0:
        raise ValueError(f"start_index 不能为负：{start_index}")
    if start_index > 2 ** 24:
        # float32 只能精确表示到 2^24 的整数；日历长度远小于此，越界说明算错了。
        raise ValueError(f"start_index {start_index} 超出 float32 可精确表示的整数范围")
    head = np.array([start_index], dtype="<f4")
    np.concatenate([head, values.astype("<f4", copy=False)]).tofile(path)


# ---------------------------------------------------------------- 构建

_JOIN_SQL = """
SELECT ts_code, trade_date,
       d.open, d.high, d.low, d.close, d.amount, d.volume,
       a.adj_factor
FROM read_parquet('{daily}') d
FULL OUTER JOIN read_parquet('{adj}') a USING (ts_code, trade_date)
WHERE trade_date <= '{freeze}'
ORDER BY ts_code, trade_date
"""

_BASE_SQL = """
WITH last_day AS (
  SELECT ts_code, max(trade_date) AS base_date
  FROM read_parquet('{adj}') WHERE trade_date <= '{freeze}' GROUP BY 1
)
SELECT a.ts_code, a.trade_date AS base_date, a.adj_factor AS base_adj_factor
FROM read_parquet('{adj}') a
JOIN last_day l ON a.ts_code = l.ts_code AND a.trade_date = l.base_date
ORDER BY 1
"""


def _norm_base(con: duckdb.DuckDBPyConnection) -> dict[str, tuple[str, float]]:
    """每只票的归一化基准 ``(L_c, adj_factor(c, L_c))``。"""
    sql = _BASE_SQL.format(adj=paths().tables_dir / "adj_factor.parquet", freeze=FREEZE)
    rows = con.execute(sql).fetchall()
    out: dict[str, tuple[str, float]] = {}
    for code, base_date, base_adj in rows:
        if code in out:
            raise RuntimeError(f"{code} 在 {base_date} 有重复 adj_factor 行 —— 归一化基准不唯一")
        if not base_adj or base_adj <= 0 or not np.isfinite(base_adj):
            raise RuntimeError(f"{code} 的归一化基准 adj_factor={base_adj!r} 不可用")
        out[code] = (base_date, float(base_adj))
    return out


def _groups(con: duckdb.DuckDBPyConnection) -> Iterator[tuple[str, dict[str, np.ndarray]]]:
    """按 ts_code 流式分组。内存只驻留一只票（<= 4,269 行）。"""
    sql = _JOIN_SQL.format(
        daily=paths().tables_dir / "daily.parquet",
        adj=paths().tables_dir / "adj_factor.parquet",
        freeze=FREEZE,
    )
    reader = con.execute(sql).fetch_record_batch(1 << 19)
    cols = ("trade_date", "open", "high", "low", "close", "amount", "volume", "adj_factor")
    cur: str | None = None
    buf: dict[str, list] = {c: [] for c in cols}

    def flush():
        return cur, {c: np.asarray(buf[c], dtype=object if c == "trade_date" else "float64")
                     for c in cols}

    for batch in reader:
        d = batch.to_pydict()
        codes = d["ts_code"]
        for i, code in enumerate(codes):
            if code != cur:
                if cur is not None:
                    yield flush()
                cur = code
                buf = {c: [] for c in cols}
            for c in cols:
                buf[c].append(d[c][i])
    if cur is not None:
        yield flush()


def _adjust(raw: dict[str, np.ndarray], factor: np.ndarray) -> dict[str, np.ndarray]:
    """按三分法把原始列折成 provider 列。见模块 docstring「复权」。"""
    with np.errstate(divide="ignore", invalid="ignore"):
        vol = raw["volume"]
        amt = raw["amount"]
        # volume<=0 或缺失 → vwap 记 NaN，绝不 inf/0。
        safe = np.where((vol > 0) & np.isfinite(vol) & np.isfinite(amt), vol, np.nan)
        raw_vwap = amt / safe
        out: dict[str, np.ndarray] = {}
        for f in FIELDS:
            if f == "factor":
                out[f] = factor
            elif f == "vwap":
                out[f] = raw_vwap * factor
            elif f in PRICE_FIELDS:
                out[f] = raw[f] * factor
            elif f in INVERSE_FIELDS:
                out[f] = raw[f] / factor
            else:
                out[f] = raw[f]
    return out


def build_features(*, verbose: bool = True) -> dict[str, Any]:
    """写 ``features/<code>/<field>.day.bin``。返回统计。"""
    cal = calendar()
    idx_of = {d: i for i, d in enumerate(cal)}
    con = duckdb.connect(":memory:")
    base = _norm_base(con)

    P = paths()
    cfg.create_dir(P.features)
    stats: dict[str, Any] = {
        "codes": 0, "files": 0, "rows_written": 0,
        "rows_off_calendar": 0, "codes_off_calendar": [],
        "codes_without_base": [], "codes_price_without_factor": {},
        "vwap_null_rows": 0, "volume_nonpositive_rows": 0,
        "base_date_is_freeze": 0, "base_date_earlier": 0,
    }
    base_rows: list[tuple[str, str, float]] = []

    for code, g in _groups(con):
        if code not in base:
            stats["codes_without_base"].append(code)
            continue
        base_date, base_adj = base[code]
        dates = [str(d) for d in g["trade_date"]]
        keep = np.array([d in idx_of for d in dates])
        if not keep.all():
            stats["rows_off_calendar"] += int((~keep).sum())
            stats["codes_off_calendar"].append(code)
        if not keep.any():
            continue
        idxs = np.array([idx_of[d] for d, k in zip(dates, keep) if k], dtype=np.int64)
        raw = {c: g[c][keep] for c in ("open", "high", "low", "close", "amount", "volume")}
        adjf = g["adj_factor"][keep]

        start, end = int(idxs[0]), int(idxs[-1])
        n = end - start + 1
        pos = idxs - start
        dense_raw = {c: np.full(n, np.nan) for c in raw}
        for c, v in raw.items():
            dense_raw[c][pos] = v
        dense_adj = np.full(n, np.nan)
        dense_adj[pos] = adjf
        factor = dense_adj / base_adj

        # 有价无因子 = 复权口径缺失，必须显式记账，不能靠 NaN 悄悄传播。
        bad = np.isfinite(dense_raw["close"]) & ~np.isfinite(factor)
        if bad.any():
            stats["codes_price_without_factor"][code] = int(bad.sum())

        out = _adjust(dense_raw, factor)
        stats["volume_nonpositive_rows"] += int(
            np.sum(np.isfinite(dense_raw["volume"]) & (dense_raw["volume"] <= 0))
        )
        stats["vwap_null_rows"] += int(
            np.sum(np.isfinite(dense_raw["close"]) & ~np.isfinite(out["vwap"]))
        )

        d = P.features / qlib_code(code).lower()
        cfg.create_dir(d)
        for f in FIELDS:
            write_bin(d / f"{f}.day.bin", start, out[f])
        stats["codes"] += 1
        stats["files"] += len(FIELDS)
        stats["rows_written"] += n
        base_rows.append((code, base_date, base_adj))
        if base_date == FREEZE:
            stats["base_date_is_freeze"] += 1
        else:
            stats["base_date_earlier"] += 1
        if verbose and stats["codes"] % 1000 == 0:
            print(f"  ... {stats['codes']} 只票")

    import pandas as pd
    pd.DataFrame(base_rows, columns=["ts_code", "base_date", "base_adj_factor"]).to_parquet(
        P.norm_base, index=False
    )
    try:
        P.norm_base.chmod(0o600)      # 红线 5：umask 002 下 to_parquet 会落 0664
    except OSError:
        pass
    con.close()
    return stats


def build_calendar() -> dict[str, Any]:
    P = paths()
    cal = calendar(refresh=True)
    cfg.create_dir(P.calendars)
    P.calendar_file.write_text("\n".join(_iso(d) for d in cal) + "\n", encoding="utf-8")
    fut = P.calendars / "day_future.txt"
    if fut.exists():
        # 未来日历 = "允许求值到冻结线之后"的开关。它不该存在。
        raise RuntimeError(f"{fut} 不该存在 —— 见模块 docstring「calendar」。")
    return {"days": len(cal), "start": _iso(cal[0]), "end": _iso(cal[-1]),
            "right_edges": {str(h): _iso(v) for h, v in evaluation_right_edges(cal).items()}}


def build_instruments(restrict: "set[str] | None" = None) -> dict[str, Any]:
    """从 ``universe_pit`` canonical 写 instruments。**不做任何筛选。**

    `restrict`（卡 1.1-a，公开通道用）：只保留这些码的区段。**不是筛选口径**，
    是「这条通道有没有这只票的数据」这个事实 —— 公开源不服务北交所（N-70），
    而 `all` 宇宙里有北交所。丢掉的码逐一记进返回值的 ``dropped_codes``，
    **不静默** ：静默丢的表现是「两条通道的 all 宇宙不一样，而没人知道」。
    private 通道不传这个参数，行为与既有一字不差。
    """
    P = paths()
    con = duckdb.connect(":memory:")
    out: dict[str, Any] = {"files": {}, "ambiguous_rows_kept": 0,
                           "restricted": restrict is not None, "dropped_codes": {}}
    cfg.create_dir(P.instruments)
    for uni in cfg.UNIVERSES_PIT:
        rows = con.execute(
            f"SELECT code, in_date_compact, out_date_compact, ambiguous "
            f"FROM read_parquet('{P.universe_pit}') "
            f"WHERE universe = ? AND canonical ORDER BY code, in_date_compact",
            [uni],
        ).fetchall()
        if not rows:
            raise RuntimeError(f"universe_pit 里 {uni} 的 canonical 行为空")
        dropped: set[str] = set()
        if restrict is not None:
            kept = [r for r in rows if r[0] in restrict]
            dropped = {r[0] for r in rows} - {r[0] for r in kept}
            rows = kept
            if not rows:
                raise RuntimeError(
                    f"{uni}：restrict 之后一个区段都不剩 —— 这不是「筛干净了」，"
                    f"是码的写法对不上（湖形态 vs qlib 形态）")
        lines = []
        amb = 0
        for code, lo, hi, ambiguous in rows:
            if hi > FREEZE:
                raise RuntimeError(f"{uni}/{code} 区段右端 {hi} 越过冻结线")
            lines.append(f"{qlib_code(code)}\t{_iso(lo)}\t{_iso(hi)}")
            amb += bool(ambiguous)
        (P.instruments / f"{uni}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        out["files"][uni] = {"rows": len(lines), "codes": len({r[0] for r in rows}),
                            "ambiguous_rows": amb}
        if dropped:
            out["dropped_codes"][uni] = sorted(dropped)
        out["ambiguous_rows_kept"] += amb
    con.close()
    return out


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def digest() -> dict[str, Any]:
    """逐文件 sha256 落 ``files.sha256``，manifest 只记它的 sha256（Merkle 根）。

    46,512 个 bin 文件的哈希直接塞进 JSON 会有几 MB，且没人会去读；
    但"只记目录不记文件"又等于没记。折中：明细单独一个文件，manifest 记根。
    """
    P = paths()
    entries = []
    total = 0
    for p in sorted(P.provider_dir.rglob("*")):
        if not p.is_file() or p.name in (P.files_digest.name, P.manifest.name):
            continue
        size = p.stat().st_size
        total += size
        entries.append(f"{_sha256(p)}  {size}  {p.relative_to(P.provider_dir)}")
    P.files_digest.write_text("\n".join(entries) + "\n", encoding="utf-8")
    return {"files": len(entries), "bytes": total,
            "files_sha256_digest": _sha256(P.files_digest)}


def build(*, verbose: bool = True, restrict: "set[str] | None" = None) -> dict[str, Any]:
    P = paths()
    cfg.harden_umask()
    cfg.create_dir(P.provider_dir)
    started = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    if verbose:
        print(f"[1/4] 日历 → {P.calendar_file}")
    cal_info = build_calendar()
    if verbose:
        print(f"      {cal_info['days']} 天，{cal_info['start']} … {cal_info['end']}")
        print(f"      求值右端 {cal_info['right_edges']}")
        print(f"[2/4] instruments → {P.instruments}")
    ins_info = build_instruments(restrict=restrict)
    if verbose:
        print(f"      {ins_info['files']}")
        print(f"[3/4] features → {P.features}（约 5,800 只 × {len(FIELDS)} 字段）")
    feat = build_features(verbose=verbose)
    if verbose:
        print(f"      {feat['codes']} 只票 / {feat['files']} 个文件 / {feat['rows_written']} 行")
        print("[4/4] 逐文件 sha256")
    dig = digest()
    manifest = {
        "card": "2.1a",
        "channel": P.channel,
        "built_at": started,
        "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "freeze_date": cfg.FREEZE_DATE,
        "source": {
            "daily": str(P.tables_dir / "daily.parquet"),
            "adj_factor": str(P.tables_dir / "adj_factor.parquet"),
            "trade_cal": str(P.tables_dir / "trade_cal.parquet"),
            "universe_pit": str(P.universe_pit),
        },
        "fields": list(FIELDS),
        "adjustment": {
            "convention": "back_adjusted_rebased_to_freeze_line",
            "formula_factor": "adj_factor(c,t) / adj_factor(c, L_c)",
            "L_c": "max{t <= freeze : adj_factor(c,t) exists}",
            "price_fields_times_factor": sorted(PRICE_FIELDS),
            "fields_divided_by_factor": sorted(INVERSE_FIELDS),
            "fields_unadjusted": sorted(AS_IS_FIELDS),
            "invariant_close_over_factor_is_raw": True,
            "invariant_vwap_times_volume_is_amount": True,
            "norm_base_table": str(P.norm_base),
        },
        "units": {"amount": "CNY", "volume": "shares", "vwap": "CNY/share",
                  "note": "社区 release 的 amount 是千元、volume 是手；相差 1000× 与 100×"},
        "vwap": {"formula": "amount / volume (raw), then × factor",
                 "volume_nonpositive_policy": "null"},
        "calendar": cal_info,
        "instruments": ins_info,
        "features": {k: v for k, v in feat.items() if k != "codes_price_without_factor"},
        "codes_price_without_factor": feat["codes_price_without_factor"],
        "holding_periods": list(HOLDING_PERIODS),
        "digest": dig,
    }
    P.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    if verbose:
        print(f"完成 → {P.manifest}")
    return manifest


# ---------------------------------------------------------------- 数据卡

#: 数据卡落点。**由本函数生成，不要直接改 .md** —— 重建即丢（M1 收尾踩过）。
DATA_CARD: Path = cfg.DATA_CARDS / "qlib_provider.md"


def render_data_card(manifest: "dict[str, Any] | None" = None) -> Path:
    """把 manifest 渲染成数据卡。可脱离 build 单独跑（读已落盘的 manifest）。"""
    P = paths()
    m = manifest if manifest is not None else json.loads(P.manifest.read_text(encoding="utf-8"))
    cal = m["calendar"]
    edges = cal["right_edges"]
    feat = m["features"]
    ins = m["instruments"]["files"]
    dig = m["digest"]
    n_amb = m["instruments"]["ambiguous_rows_kept"]

    L = []
    A = L.append
    A("# 数据卡：v1 冻结 qlib provider（卡 2.1a）")
    A("")
    A(f"落点 `{P.provider_dir}` · 通道 `{m.get('channel', 'private')}`"
      f" · 冻结线 `{m['freeze_date']}` · 构建于 `{m['finished_at']}`")
    A(f"· `files.sha256` 根 `{dig['files_sha256_digest'][:16]}…`"
      f"（{dig['files']} 个文件 / {dig['bytes']:,} 字节）")
    A("")
    A("> **本文件由 `snapshots/qlib_provider.py::render_data_card()` 生成。**")
    A("> 直接改 `.md` 会在下次重建时丢掉 —— 要改口径请改代码。")
    A("")
    if m.get("channel", "private") != "private":
        A("> ⚠️ **这份卡是用私有通道的模板渲染的。**下面正文里有一批**写死的**实测数字")
        A("> （单位判据的 99.9843% / 14,581,977 行、与社区 release 的逐项比较、"
          "第 8 节的 P-1..P-4 计数）——")
        A("> **那些是私有通道的数**，不是这条通道的。凡是「本次构建现算」的数"
          "（日历、instruments、")
        A("> 归一化基准计数、digest）都来自本通道的 manifest，可以照读。")
        A("> **本通道自己的陷阱与对账数字见** "
          "`ops/reports/public/data_channel_notes.md`。")
        A("")
    A("## 1. 为什么自建，而不是用现成的两份")
    A("")
    A("签字裁定（方案 C），三重理由，按硬度排序：")
    A("")
    A("1. **S3 主指标 Fid% 是被测因子值对 gold 的秩相关。** gold 若算自社区 bin、"
      "而 agent 拿到的是网关快照，任何不一致都**无法归因**是 agent 错还是数据本来就不同 —— "
      "主指标不可解释，并会污染「跨后端一致性」这个署名指标。")
    A("2. **τ 是要签字的数字**，标定口径必须与评测口径是同一份数据。")
    A("3. 本方案下 provider 日历里**物理上没有**冻结线之后的交易日 —— "
      "红线 7 从「每次调用的自觉」变成**结构保证**。"
      f"实测 qlib 自己的 `D.calendar()` 看到的上界就是 `{cal['end']}`。")
    A("")
    A("「先 A 后 C」的折中**未采纳**：两版 τ 只有一版能用，且日后容易被误引。")
    A("")
    A("## 2. 单位（实证得出，不是按文档假设）")
    A("")
    A(f"| 列 | 单位 | 与 tushare 原生 | 与社区 release |")
    A("| --- | --- | --- | --- |")
    A("| `amount` | **元** | 原生是千元，湖已归一 | 社区仍是**千元**，差 **1000×** |")
    A("| `volume` | **股** | 原生是手(100 股)，湖已归一 | 社区是**手**，差 **100×** |")
    A("| `vwap` | 元/股 | — | 同 |")
    A("")
    A("**判据不是查文档，是这条硬判据**：`low <= amount/volume <= high` 的行占比。")
    A(f"全表 14,581,977 行、相对容差 {VWAP_BAND_REL_TOL:g} 下 **99.9843%**，逐年均 > 99.6%，")
    A("中位 `vwap/close ≈ 1.0` 且逐年稳定 —— 说明单位没有中途变过。")
    A("若单位按 tushare 文档假设直接相除，这个比率会是 **0%**（差 10 倍）。")
    A("")
    A("## 3. `vwap` 口径")
    A("")
    A("```")
    A("vwap_raw = amount / volume          # 原始值")
    A("vwap     = vwap_raw × factor        # 与其余价格用同一复权因子")
    A("volume <= 0 或缺失  ->  vwap = NULL # 不得 inf、不得 0")
    A("```")
    A("")
    A(f"**判别力披露**：实测全表 `volume <= 0` 的行 **{feat['volume_nonpositive_rows']} 条**，")
    A("所以这条守门在当前数据上是**空转**的。这里不假装它被测过 —— ")
    A("`ops/test_qlib_provider.py::test_inv_vwap_is_null_never_inf_when_volume_nonpositive` "
      "改用**构造数据**直接打 `_adjust()` 来证明守门代码本身有效。")
    A("（它对应的是我们要测 agent 的 S3-ROB-02「非有限值安全传播」，自己的 gold 里先别犯。）")
    A("")
    A("## 4. 复权口径")
    A("")
    A("```")
    A("L_c    = max{ t <= 冻结线 : adj_factor(c, t) 存在 }")
    A("factor = adj_factor(c, t) / adj_factor(c, L_c)")
    A("")
    A("open/high/low/close/vwap  = 原始价 × factor      # 后复权，以冻结线重定基")
    A("volume                    = 原始股数 / factor    # 拆股会让股数跳变，除掉才连续")
    A("amount                    = 原始金额（不复权）   # 钱就是钱")
    A("```")
    A("")
    A("遵循 qlib 惯例：Alpha158/360 的表达式假定 `$close` 是复权价，"
      "存原始价会改变全部因子语义。由构造直接得到两条不变式：")
    A("")
    A("- `$close / $factor == 原始收盘价`（qlib 自己的口径）")
    A("- **`vwap × volume == amount`**，且**与复权无关** —— 白得的内部一致性检查，"
      "任何一处分派写反它立刻红。")
    A("")
    A(f"**归一化基准定死为冻结线**：`factor({m['freeze_date']}) = 1`，"
      "即冻结线当天的价 == 原始价。")
    A(f"实测 **{feat['base_date_is_freeze']} 只**票在冻结线当天在市，基准就是冻结线。")
    A("")
    A(f"⚠ **必要偏离**：另有 **{feat['base_date_earlier']} 只**票在冻结线前已退市/停更，"
      "「冻结线当天」对它们根本不存在。")
    A("这些票以**自身最后一个有 `adj_factor` 的交易日**为基准（该日 `factor = 1`）。"
      "逐票基准落在 `norm_base.parquet`，是产物的一部分。")
    A("")
    A("## 5. instruments")
    A("")
    A("取自卡 1.1 的 `universe_pit` **canonical** 口径，不用社区名单 —— "
      "卡 1.1 的产出由此正式成为卡 2.1 的输入，数据面闭环。")
    A("")
    A("| 宇宙 | 区段行数 | 去重码数 | 其中 `ambiguous` |")
    A("| --- | ---: | ---: | ---: |")
    for u in cfg.UNIVERSES_PIT:
        v = ins[u]
        A(f"| `{u}` | {v['rows']:,} | {v['codes']:,} | {v['ambiguous_rows']} |")
    A("")
    A(f"**`ambiguous` 区段照常保留（共 {n_amb} 条）。** provider 是数据层，不做筛选；"
      "排除动作留在任务生成层。")
    A("provider 静默丢弃它们的话我们就有了两个不同的宇宙，"
      "且日后无法测「在模糊区段上会发生什么」。")
    A("")
    A("## 6. calendar，以及它与卡 1.4 的差别")
    A("")
    A(f"`calendars/day.txt` = `trade_cal(SSE, is_open=1)` 且 `<= {m['freeze_date']}`，"
      f"共 **{cal['days']:,}** 天（{cal['start']} … {cal['end']}）。")
    A("**不出 `day_future.txt`** —— 它在 qlib 里就是「允许求值到未来」的开关。")
    A("")
    A("**这与卡 1.4 不冲突，两处规则不同、各自的理由是**：")
    A("")
    A("| | 快照表 `tables/trade_cal.parquet` | provider `calendars/day.txt` |")
    A("| --- | --- | --- |")
    A("| 内容 | **保留** 153 行未来日历（到 2026-12-31） | 截到冻结线 |")
    A("| 理由 | capture_time 语义；T+N 对齐需要知道 8 月 3 日是不是交易日 | "
      "它决定**因子表达式能在哪些日子求值**；冻结线之后本来就没有 bar 可算 |")
    A("")
    A("`ops/test_qlib_provider.py::test_03b_no_future_calendar_and_snapshot_still_has_one` "
      "把这个差别钉住：谁把其中一处「统一」掉，那条就红。")
    A("")
    A("## 7. 可用求值右端（会静默污染结果的那条约束）")
    A("")
    A("持有期 {1,5,20} 日下，最后 h 个交易日的前向收益在冻结线内**不完整**。")
    A("在 t 日收盘求值、收盘后调仓、持有 h 日 → 需要 `t+h` 日的收盘价，故 `t <= cal[-(h+1)]`：")
    A("")
    A("| 持有期 | 可用求值右端 | 距冻结线 |")
    A("| ---: | --- | ---: |")
    for h in HOLDING_PERIODS:
        A(f"| {h} 日 | **{edges[str(h)]}** | {h} 个交易日 |")
    A("")
    A("三个数由 `trade_cal` 现数（`evaluation_right_edge()`），**不写死**。")
    A("**必须进 `calibration.json` 并在评分器里硬拦** —— 不拦的话，"
      "20 日 IC 会在末段用截断/缺失的前向收益计算，被静默偏置，"
      "**而且从指标数值上看不出来**。")
    A("")
    A("## 8. 已知缺陷与边界")
    A("")
    A("| # | 事实 | 影响 | 处置 |")
    A("| --- | --- | --- | --- |")
    A("| P-1 | `vwap` 越出 `[low, high]` 的行（容差 1e-6 后）—— 主因是源侧 `amount` "
      "被舍到整数元，集中在北交所小额成交 | 131 条依赖 `vwap` 的因子 | "
      "**不静默修补**：网关只发 `amount`/`volume`，agent 自己算 vwap 也会得到同一个数；"
      "改了 gold 就与执行面不同源。计数与样例见 `ops/acceptance/card_2.1a_full_verify.json`，登记 N-20 |")
    A("| P-2 | 3 个码（`000022.SZ` `000043.SZ` `300114.SZ`）**有价无名单** —— "
      "代码变更注销，不在 `stock_basic` | 有 features、不在任何 instruments 文件 | "
      "保留 features（丢了会让 `code_alias` 的适配赛道没数据），不塞进名单（会破坏第 ④ 条验收） |")
    A("| P-3 | 2 个码（`000805.SZ` `000787.SZ`）**有名单无价** | 在 `all.txt` 里但无 features | "
      "保留在名单（`universe_pit` 逐区段相等是硬验收），qlib 读出来是 NaN |")
    A("| P-4 | bin 是 **float32** | 反算原始价有 ~1e-7 的相对误差 | "
      "验收用 1e-5 相对容差；实测最大偏差见报告 |")
    A("")
    A("## 9. 与社区 release 的差异清单（跨源比对时会踩的）")
    A("")
    A("| 维度 | 我们 | 社区 `releases/2026-08-26` |")
    A("| --- | --- | --- |")
    A(f"| 日历上界 | {cal['end']}（= 冻结线） | 2026-08-26（越线 18 天） |")
    A("| `day_future.txt` | **无** | 有，到 2026-12-31 |")
    A("| 价格归一 | `factor(冻结线) = 1` | 每票**首日 close = 1** |")
    A("| `amount` | 元 | **千元**（1000×） |")
    A("| `volume` | 股，且 `/factor` | **手**，且 `/factor`（100×） |")
    A("| 字段数 | 8（7 个 required + `factor`） | 10（多 `adjclose` `change`） |")
    A("| instruments | `universe_pit` canonical | 社区自带，含 6 个指数与悬空成分 |")
    A("")
    A("`adjclose` 在「以冻结线重定基」下与 `close` 逐值相同，`change` 可由 `close` 求出 —— "
      "都不出，少一个字段就少一处会漂的口径。")
    A("")
    A("## 10. 复现")
    A("")
    A("```bash")
    A("export GENEBENCH_ROOT=/data/shared/genebench")
    A("cd $GENEBENCH_ROOT/repo && ulimit -n 8192")
    A("$GENEBENCH_ROOT/env/bin/python -m snapshots.qlib_provider")
    A("$GENEBENCH_ROOT/env/bin/python -m pytest ops/test_qlib_provider.py -q")
    A("$GENEBENCH_ROOT/env/bin/python ops/acceptance/card_2_1a_full_verify.py")
    A("```")
    A("")
    cfg.create_dir(P.data_card.parent)
    P.data_card.write_text("\n".join(L) + "\n", encoding="utf-8")
    return P.data_card


if __name__ == "__main__":
    import argparse as _ap
    _p = _ap.ArgumentParser(description="卡 2.1a 冻结 qlib provider")
    _p.add_argument("--card-only", action="store_true",
                    help="只用已落盘的 manifest 重渲染数据卡，不重建 provider")
    _a = _p.parse_args()
    if _a.card_only:
        print(f"数据卡 → {render_data_card()}")
    else:
        _m = build()
        print(f"数据卡 → {render_data_card(_m)}")
