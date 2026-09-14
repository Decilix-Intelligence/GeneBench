"""snapshots.universe_qlib —— 源B:qlib community instruments → 可比区间表。

卡 1.1 源B。输入是 `cfg.QLIB_RELEASE / "instruments" / *.txt`,
输出两件:

* `cfg.UNIVERSE_DIR / "qlib_instruments_intervals.parquet"`
  —— 字段 `code, universe, in_date, out_date, raw_code, source_file`
* `cfg.OPS / "universe_source_B.json"` —— 统计摘要 + 区间约定的考据证据

区间约定(本模块最重要的结论,考据过程见 `_convention_evidence()` 与
`ops/universe_source_B.md`)
------------------------------------------------------------------
qlib instruments 的 ``(code, start, end)`` 是**闭日历区间 `[in_date, out_date]`**:

* ``in_date`` 是**生效日**,当天该票**已经**在成分内;100% 落在交易日上。
* ``out_date`` 是**最后一个仍在成分内的日历日**,**不是**退出日;
  退出生效日 = ``out_date + 1 天``。
* ``out_date`` **不保证是交易日**(csi300 只有 68.5% 是),因为它由
  ``下一段 in_date - 1 天`` 的**纯日历**减法得到,会落在周日/节假日上。
  想要"最后一个成分内**交易日**",取 ``<= out_date`` 的最后一个交易日。
* 等价写法:半开**日历**区间 ``[in_date, next_in_date)``。
  **不要**写成 ``[in_date, out_date)`` —— 那会把每段的最后一天整段丢掉,
  在 epoch 边界日上直接损失全部成分(实测:那天的成分数会变成 0)。

**源A/源B 的区间约定必须统一,否则对账结果是垃圾。**
源A(湖 `index_weight`)是**月末时点快照**(某天的成分名单),源B 是**区间**;
把源B 折成某日名单的唯一正确写法是 ``in_date <= D <= out_date``。

三段语义互不相同,禁止混用
-------------------------
* ``all``   —— 每只票**一段**上市区间(6142 行 = 6142 个 code,1 段/code)。
  左端 ``2000-01-04`` 是日历起点(左删失),右端 ``2026-08-26`` 是发布日(右删失),
  都不是真实上市/退市日。**里面混着 6 个指数代码**,不是股票。
* ``csi*``  —— 成分区间**多段**,由上游成分快照日切成 epoch。
* ``csiall``—— 中证全指成分,成员数 1881→5171 随时间变。

冻结线(红线 7)
---------------
产物按 `cfg.FREEZE_DATE` 截断:``in_date > FREEZE`` 的整行丢弃,
``out_date`` 截到 ``min(out_date, FREEZE)``。原始文件里**没有任何一行**天然
``out_date == FREEZE``(已核),所以产物里 ``out_date == cfg.FREEZE_DATE``
**就是右删失标记**(截至冻结线仍在成分内/仍在上市),可以直接这么判。
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pyarrow as pa
import pyarrow.parquet as pq

import genebench_config as cfg
from snapshots import lake

__all__ = [
    "UNIVERSE_ORDER",
    "UNIVERSE_FILES",
    "KNOWN_EXCHANGE_PREFIXES",
    "PARQUET_SCHEMA",
    "Interval",
    "NormalizedCode",
    "instruments_dir",
    "calendar_path",
    "parquet_path",
    "summary_path",
    "doc_path",
    "normalize_code",
    "parse_instruments_file",
    "load_all",
    "apply_freeze",
    "build_summary",
    "write_parquet",
    "write_summary",
    "main",
]

# --------------------------------------------------------------------------
# 输入 / 输出位置(全部派生自 cfg,本模块不出现绝对路径字面量)
# --------------------------------------------------------------------------

#: 宇宙名 → instruments 文件名。顺序即产物里的排序主键顺序。
#: 刻意叫 `UNIVERSE_FILES` 而不是 `UNIVERSES` —— `cfg.UNIVERSES` 是**卡 1.1 源A**
#: 的三个基准宇宙 `("csi300","csi500","csi1000")`,而源B 要把发布里的 6 个文件
#: 全解出来(多 `all`/`csi800`/`csiall`)。两者是包含关系,不是同一个东西,
#: 重名会让下游误以为可以互换。`test_universe_qlib_covers_cfg_universes` 守着这层包含。
UNIVERSE_ORDER: tuple[str, ...] = ("all", "csi300", "csi500", "csi800", "csi1000", "csiall")
UNIVERSE_FILES: dict[str, str] = {name: f"{name}.txt" for name in UNIVERSE_ORDER}

#: 已知的交易所前缀。**不是假设** —— `parse_instruments_file()` 会枚举实际
#: 出现的前缀,遇到不在这里的一律进 `unmapped` 清单上报,**绝不静默丢弃**。
KNOWN_EXCHANGE_PREFIXES: tuple[str, ...] = ("SH", "SZ", "BJ")

#: 湖里的标准形态:6 位数字 + 点 + 交易所。
_SYMBOL_RE = re.compile(r"^\d{6}$")

#: 产物 schema。日期用 date32,不用字符串 —— 区间表的核心操作是比大小,
#: 字符串日期在跨源对账时最容易被写成 `'20260731'` vs `'2026-07-31'` 的坑。
PARQUET_SCHEMA = pa.schema(
    [
        pa.field("code", pa.string(), nullable=False),
        pa.field("universe", pa.string(), nullable=False),
        pa.field("in_date", pa.date32(), nullable=False),
        pa.field("out_date", pa.date32(), nullable=False),
        pa.field("raw_code", pa.string(), nullable=False),
        pa.field("source_file", pa.string(), nullable=False),
    ]
)

#: 同 `universe_build` / `tradability` 的护栏，但这里的"列清单"是写盘时
#: 那个 `from_pydict` 的**字面 dict**，没有独立常量可比，所以改成写盘前断言。
#: 不对称是一样的：dict 多一个键 → 被 schema **静默丢掉**；schema 多一个 → 报错。
#: 产物列清单。**独立于 schema 存在**，就是为了让下面那条 import 期断言有东西可比
#: —— 第一版我只写了写盘时断言，负控当场证明它是摆设：删掉一个 schema 字段
#: 不会红，要等到真正写盘才触发，而那时错误早就提交了。
INTERVAL_COLUMNS: tuple[str, ...] = (
    "code", "universe", "in_date", "out_date", "raw_code", "source_file",
)

_SCHEMA_NAMES = tuple(f.name for f in PARQUET_SCHEMA)
if set(_SCHEMA_NAMES) != set(INTERVAL_COLUMNS):
    raise RuntimeError(
        f"PARQUET_SCHEMA 与 INTERVAL_COLUMNS 对不上："
        f"只在 schema {sorted(set(_SCHEMA_NAMES) - set(INTERVAL_COLUMNS))}，"
        f"只在 COLUMNS {sorted(set(INTERVAL_COLUMNS) - set(_SCHEMA_NAMES))}。"
        f"加列时两处都要改。"
    )


def _assert_payload_matches_schema(payload: "dict") -> "dict":
    """写盘前钉死 payload 的键与 schema 字段完全一致。"""
    if set(payload) != set(_SCHEMA_NAMES):
        raise RuntimeError(
            f"写盘 payload 与 PARQUET_SCHEMA 对不上："
            f"只在 payload {sorted(set(payload) - set(_SCHEMA_NAMES))}，"
            f"只在 schema {sorted(set(_SCHEMA_NAMES) - set(payload))}。"
            f"payload 多出来的键会被 from_pydict **静默丢掉**。"
        )
    return payload

#: 产物文件名。**目录**走 `cfg.UNIVERSE_DIR`(卡 1.1 源A 引入的共享常量),
#: 不在这里另拼一份 `v1/universe` —— 两处各拼一份必然漂移。
_PARQUET_NAME = "qlib_instruments_intervals.parquet"
_SUMMARY_NAME = "universe_source_B.json"
_DOC_NAME = "universe_source_B.md"

#: 单个文件权限(红线 5:umask 是 002,不显式 chmod 会落成组可读)。
_FILE_MODE = 0o600


def instruments_dir() -> Path:
    """qlib 发布里的 instruments 目录。"""
    return cfg.QLIB_RELEASE / "instruments"


def calendar_path() -> Path:
    """qlib 发布自带的日频交易日历(用来验证 in/out 是否交易日)。"""
    return cfg.QLIB_RELEASE / "calendars" / "day.txt"


def source_manifest_path() -> Path:
    """qlib 发布的来源说明(记录上游 repo 与 sha256)。"""
    return cfg.QLIB_RELEASE / "SOURCE.txt"


def parquet_path() -> Path:
    """区间表产物路径:`cfg.UNIVERSE_DIR / qlib_instruments_intervals.parquet`。"""
    return cfg.UNIVERSE_DIR / _PARQUET_NAME


def summary_path() -> Path:
    """统计摘要 JSON 路径。"""
    return cfg.OPS / _SUMMARY_NAME


def doc_path() -> Path:
    """区间约定考据文档路径。"""
    return cfg.OPS / _DOC_NAME


# --------------------------------------------------------------------------
# 数据结构
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class NormalizedCode:
    """一次代码规范化的结果。

    Attributes:
        raw: 原始 qlib 代码,如 ``'SH600000'``。
        code: 规范化后的湖内代码,如 ``'600000.SH'``;映射失败时为 ``None``。
        exchange: 识别出的交易所前缀。
        symbol: 去掉前缀后的代码本体。
        ok: 是否成功映射。
        reason: 失败原因(``ok=True`` 时为 ``''``)。
        anomaly: 映射成功但形态可疑时的标记(如 symbol 不是 6 位数字)。
    """

    raw: str
    code: str | None
    exchange: str
    symbol: str
    ok: bool
    reason: str
    anomaly: str


@dataclass(frozen=True, slots=True)
class Interval:
    """一条区间记录。

    Attributes:
        code: 规范化代码(``600000.SH``)。
        universe: 宇宙名(``csi300``)。
        in_date: 闭区间左端,生效日,当天已在成分内。
        out_date: 闭区间右端,最后一个仍在成分内的日历日。
        raw_code: 原始 qlib 代码(``SH600000``),保留以便回溯。
        source_file: 来源文件名(``csi300.txt``)。
    """

    code: str
    universe: str
    in_date: dt.date
    out_date: dt.date
    raw_code: str
    source_file: str


# --------------------------------------------------------------------------
# 代码规范化
# --------------------------------------------------------------------------


def normalize_code(raw: str) -> NormalizedCode:
    """`SH600000` → `600000.SH`,`SZ000001` → `000001.SZ`,`BJ430017` → `430017.BJ`。

    规则:**前 2 个字符是交易所前缀,其余是代码本体**,拼成 ``<symbol>.<EX>``。
    前缀不在 `KNOWN_EXCHANGE_PREFIXES` 里就判失败并给出原因,
    **不静默丢弃**(调用方必须把失败清单打进摘要)。

    映射成功但本体不是 6 位数字的(实测只有 `SHT00018` 一个),
    照常映射成 ``T00018.SH`` 并在 `anomaly` 上打标,交给调用方上报。

    Args:
        raw: 原始 qlib 代码。

    Returns:
        `NormalizedCode`。
    """
    text = raw.strip()
    if not text:
        return NormalizedCode(raw, None, "", "", False, "空代码", "")
    if len(text) < 3:
        return NormalizedCode(raw, None, "", text, False, f"长度 {len(text)} < 3,拆不出前缀", "")

    exchange = text[:2].upper()
    symbol = text[2:]
    if exchange not in KNOWN_EXCHANGE_PREFIXES:
        return NormalizedCode(
            raw,
            None,
            exchange,
            symbol,
            False,
            f"未知交易所前缀 {exchange!r};已知的是 {list(KNOWN_EXCHANGE_PREFIXES)}",
            "",
        )
    anomaly = "" if _SYMBOL_RE.match(symbol) else f"代码本体 {symbol!r} 不是 6 位数字"
    return NormalizedCode(raw, f"{symbol}.{exchange}", exchange, symbol, True, "", anomaly)


# --------------------------------------------------------------------------
# 解析
# --------------------------------------------------------------------------


def _parse_date(text: str) -> dt.date:
    return dt.date.fromisoformat(text.strip())


def parse_instruments_file(universe: str) -> tuple[list[Interval], dict]:
    """解析一个 instruments 文件。

    格式:三列 tab 分隔 ``code<TAB>start<TAB>end``,
    **同一 code 多行 = 多个区间段**。

    Args:
        universe: 宇宙名,必须是 `UNIVERSE_FILES` 的键。

    Returns:
        ``(区间列表, 解析诊断 dict)``。诊断里含前缀枚举、映射失败清单、
        形态异常清单、坏行清单 —— 一条都不许被静默吞掉。

    Raises:
        KeyError: `universe` 不认识。
        FileNotFoundError: 文件不在。
    """
    filename = UNIVERSE_FILES[universe]
    path = instruments_dir() / filename
    rows: list[Interval] = []
    prefix_counter: collections.Counter[str] = collections.Counter()
    unmapped: list[dict] = []
    anomalies: list[dict] = []
    bad_lines: list[dict] = []
    reversed_rows: list[dict] = []

    with path.open("r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, 1):
            text = line.rstrip("\n")
            if not text.strip():
                continue
            parts = text.split("\t")
            if len(parts) != 3:
                bad_lines.append({"line": lineno, "raw": text[:120], "n_fields": len(parts)})
                continue
            raw_code, start_text, end_text = parts
            norm = normalize_code(raw_code)
            prefix_counter[norm.exchange or "<空>"] += 1
            if not norm.ok or norm.code is None:
                unmapped.append({"line": lineno, "raw_code": raw_code, "reason": norm.reason})
                continue
            if norm.anomaly:
                anomalies.append(
                    {
                        "line": lineno,
                        "raw_code": raw_code,
                        "code": norm.code,
                        "anomaly": norm.anomaly,
                    }
                )
            try:
                in_date = _parse_date(start_text)
                out_date = _parse_date(end_text)
            except ValueError as exc:
                bad_lines.append({"line": lineno, "raw": text[:120], "error": str(exc)})
                continue
            if out_date < in_date:
                reversed_rows.append(
                    {"line": lineno, "raw_code": raw_code, "in": str(in_date), "out": str(out_date)}
                )
                continue
            rows.append(Interval(norm.code, universe, in_date, out_date, raw_code, filename))

    diag = {
        "source_file": filename,
        "n_lines_parsed": len(rows) + len(unmapped) + len(bad_lines) + len(reversed_rows),
        "prefix_enumeration": dict(sorted(prefix_counter.items())),
        "n_unmapped": len(unmapped),
        "unmapped": unmapped,
        "n_symbol_anomalies": len(anomalies),
        "symbol_anomalies": anomalies,
        "n_bad_lines": len(bad_lines),
        "bad_lines": bad_lines,
        "n_reversed_intervals": len(reversed_rows),
        "reversed_intervals": reversed_rows,
    }
    return rows, diag


def load_all() -> tuple[list[Interval], dict[str, dict]]:
    """解析全部 6 个 instruments 文件。

    Returns:
        ``(全部区间, {宇宙名: 诊断})``。
    """
    everything: list[Interval] = []
    diags: dict[str, dict] = {}
    for universe in UNIVERSE_ORDER:
        rows, diag = parse_instruments_file(universe)
        everything.extend(rows)
        diags[universe] = diag
    return everything, diags


# --------------------------------------------------------------------------
# 冻结线(红线 7)
# --------------------------------------------------------------------------


def apply_freeze(rows: Iterable[Interval]) -> tuple[list[Interval], dict]:
    """把区间截到 `cfg.FREEZE_DATE`。

    * ``in_date > FREEZE`` 的行整条丢弃(冻结线之后才出现的票不属于 v1 宇宙)。
    * ``out_date > FREEZE`` 的行把右端截到 FREEZE,并计入"右删失"。

    原始文件里没有任何一行天然 ``out_date == FREEZE``(`build_summary()` 会
    重新核这一点并写进摘要),所以截断后 ``out_date == FREEZE`` 可以直接当
    右删失标记用。

    Args:
        rows: 原始区间。

    Returns:
        ``(截断后的区间, 截断账目)``。
    """
    freeze = dt.date.fromisoformat(cfg.FREEZE_DATE)
    kept: list[Interval] = []
    dropped: collections.Counter[str] = collections.Counter()
    clipped: collections.Counter[str] = collections.Counter()
    natural_freeze_end: collections.Counter[str] = collections.Counter()
    dropped_rows: list[dict] = []

    for row in rows:
        if row.out_date == freeze:
            natural_freeze_end[row.universe] += 1
        if row.in_date > freeze:
            dropped[row.universe] += 1
            if len(dropped_rows) < 50:
                dropped_rows.append(
                    {
                        "universe": row.universe,
                        "code": row.code,
                        "in_date": str(row.in_date),
                        "out_date": str(row.out_date),
                    }
                )
            continue
        if row.out_date > freeze:
            clipped[row.universe] += 1
            kept.append(
                Interval(row.code, row.universe, row.in_date, freeze, row.raw_code, row.source_file)
            )
        else:
            kept.append(row)

    ledger = {
        "freeze_date": cfg.FREEZE_DATE,
        "policy": (
            "in_date > FREEZE 的行整条丢弃;out_date > FREEZE 截到 FREEZE。"
            "截断后 out_date == FREEZE 即右删失。"
        ),
        "n_dropped_in_after_freeze": dict(sorted(dropped.items())),
        "n_clipped_out_after_freeze": dict(sorted(clipped.items())),
        "n_natural_out_eq_freeze_before_clip": dict(sorted(natural_freeze_end.items())),
        "censoring_sentinel_is_unambiguous": sum(natural_freeze_end.values()) == 0,
        "dropped_rows_sample": dropped_rows,
    }
    return kept, ledger


# --------------------------------------------------------------------------
# 区间约定考据
# --------------------------------------------------------------------------


def _load_qlib_calendar() -> list[str]:
    return [
        line.strip()
        for line in calendar_path().read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _structural_evidence(rows: list[Interval]) -> dict:
    """纯结构证据:in/out 是否交易日、相邻段是否 ``out + 1 天 == 下一段 in``。

    这是"闭区间"结论的**内部一致性**证据,不依赖数据湖。
    """
    calendar = set(_load_qlib_calendar())
    by_universe: dict[str, dict] = {}
    for universe in UNIVERSE_ORDER:
        subset = [r for r in rows if r.universe == universe]
        if not subset:
            continue
        per_code: dict[str, list[tuple[dt.date, dt.date]]] = collections.defaultdict(list)
        for r in subset:
            per_code[r.code].append((r.in_date, r.out_date))

        pairs = 0
        adjacent = 0
        overlaps: list[dict] = []
        out_is_prev_trading_day = 0
        for code, segments in per_code.items():
            segments.sort()
            for i in range(len(segments) - 1):
                pairs += 1
                gap = (segments[i + 1][0] - segments[i][1]).days
                if gap == 1:
                    adjacent += 1
                    prev_day = segments[i][1]
                    if prev_day.isoformat() in calendar:
                        out_is_prev_trading_day += 1
                elif gap <= 0 and len(overlaps) < 10:
                    overlaps.append(
                        {"code": code, "seg_a": list(map(str, segments[i])),
                         "seg_b": list(map(str, segments[i + 1]))}
                    )

        in_td = sum(1 for r in subset if r.in_date.isoformat() in calendar)
        out_td = sum(1 for r in subset if r.out_date.isoformat() in calendar)
        out_weekday = collections.Counter(r.out_date.weekday() for r in subset)
        in_weekday = collections.Counter(r.in_date.weekday() for r in subset)
        by_universe[universe] = {
            "n_rows": len(subset),
            "in_date_is_trading_day": in_td,
            "in_date_trading_day_ratio": round(in_td / len(subset), 6),
            "out_date_is_trading_day": out_td,
            "out_date_trading_day_ratio": round(out_td / len(subset), 6),
            "in_weekday_hist": dict(sorted(in_weekday.items())),
            "out_weekday_hist": dict(sorted(out_weekday.items())),
            "consecutive_segment_pairs": pairs,
            "pairs_with_gap_eq_1_calendar_day": adjacent,
            "of_which_out_date_is_a_trading_day": out_is_prev_trading_day,
            "n_overlapping_pairs": len(overlaps),
            "overlap_examples": overlaps,
        }
    return {
        "qlib_calendar": {
            "path_relative_to_release": "calendars/day.txt",
            "n_trading_days": len(calendar),
        },
        "weekday_legend": "0=周一 … 4=周五 5=周六 6=周日",
        "reading": (
            "in_date 100% 是交易日且从不落在周末;out_date 大量落在周日(6)与节假日 —— "
            "说明 out_date 是 `下一段 in_date - 1 日历天` 的纯日历减法结果,"
            "区间右端是**闭**的日历日,不是交易日。"
        ),
        "per_universe": by_universe,
    }


def _epoch_evidence(rows: list[Interval]) -> dict:
    """epoch 结构:同一 ``(in,out)`` 的成员数。

    csi* 的每个 ``(in_date, out_date)`` 就是上游一次成分快照期,
    期内每个成员各一行 —— 成员数应等于指数基数(300/500/800/1000)。
    偏离基数的 epoch 就是上游数据缺口,必须点名。

    `all` 不参与:它是"每票一段上市区间",没有 epoch 结构,
    强算出来的 ``(in,out)`` 分组只是巧合同日,没有含义。
    """
    out: dict[str, dict] = {
        "_note": (
            "只统计 csi*;all.txt 是每票一段上市区间,不存在 epoch 结构,"
            "对它做 (in,out) 分组没有含义。"
        )
    }
    for universe in UNIVERSE_ORDER:
        if universe == "all":
            continue
        subset = [r for r in rows if r.universe == universe]
        if not subset:
            continue
        counter = collections.Counter((r.in_date, r.out_date) for r in subset)
        sizes = collections.Counter(counter.values())
        modal = sizes.most_common(1)[0][0]
        odd = sorted(
            (
                {"in": str(a), "out": str(b), "n_members": n}
                for (a, b), n in counter.items()
                if n != modal
            ),
            key=lambda d: d["in"],
        )
        out[universe] = {
            "n_epochs": len(counter),
            "modal_member_count": modal,
            "member_count_hist": {str(k): v for k, v in sorted(sizes.items())},
            "n_off_modal_epochs": len(odd),
            "off_modal_epochs": odd[:40],
        }
    return out


def _lake_evidence() -> dict:
    """外部证据:拿湖 `index_weight` 的月末时点快照当"真值"验开闭区间。

    做法:对每个快照日 ``D``,分别用**闭**(``in<=D<=out``)和**半开**
    (``in<=D<out``)两种约定把 qlib 区间折成当日名单,与湖里的名单比对称差。
    真正能区分两者的,是 ``D`` 恰好等于某条 ``out_date`` 的那些天。

    注意:这**不是**独立验证 —— qlib 发布的上游同样是 Tushare
    (见 `SOURCE.txt`),两源同宗。它验的是"区间约定"而不是"数据正确性"。
    """
    index_map = {"csi300": "000300.SH", "csi500": "000905.SH", "csi1000": "000852.SH"}
    result: dict = {
        "caveat": (
            "湖 index_weight 与 qlib 发布同宗(上游都是 Tushare,见 SOURCE.txt),"
            "本项验的是区间开闭约定,不构成对数据本身的独立验证。"
        ),
        "per_universe": {},
    }
    for universe, index_code in index_map.items():
        rows, _ = parse_instruments_file(universe)
        segments = [(r.code, r.in_date, r.out_date) for r in rows]
        with lake.catalog() as con:
            dates = [
                str(v)
                for (v,) in con.execute(
                    "SELECT DISTINCT trade_date FROM index_weight WHERE index_code = ? ORDER BY 1",
                    [index_code],
                ).fetchall()
            ]
            closed_total = 0
            halfopen_total = 0
            exact_closed = 0
            discriminating: list[dict] = []
            for compact in dates:
                day = dt.date(int(compact[:4]), int(compact[4:6]), int(compact[6:8]))
                truth = {
                    c
                    for (c,) in con.execute(
                        "SELECT DISTINCT con_code FROM index_weight "
                        "WHERE index_code = ? AND trade_date = ?",
                        [index_code, compact],
                    ).fetchall()
                }
                closed = {c for c, a, b in segments if a <= day <= b}
                halfopen = {c for c, a, b in segments if a <= day < b}
                d_closed = len(truth ^ closed)
                d_half = len(truth ^ halfopen)
                closed_total += d_closed
                halfopen_total += d_half
                exact_closed += int(d_closed == 0)
                if any(b == day for _, _, b in segments):
                    discriminating.append(
                        {
                            "snapshot_date": day.isoformat(),
                            "lake_members": len(truth),
                            "closed_members": len(closed),
                            "closed_symmetric_diff": d_closed,
                            "halfopen_members": len(halfopen),
                            "halfopen_symmetric_diff": d_half,
                        }
                    )
        result["per_universe"][universe] = {
            "lake_index_code": index_code,
            "n_snapshot_dates": len(dates),
            "snapshot_date_range": [dates[0], dates[-1]] if dates else None,
            "closed_total_symmetric_diff": closed_total,
            "halfopen_total_symmetric_diff": halfopen_total,
            "n_snapshots_exactly_matched_by_closed": exact_closed,
            "n_discriminating_dates": len(discriminating),
            "discriminating_dates": discriminating,
            "discriminating_note": (
                "快照日恰好落在某条 out_date 上时,闭区间给出完整名单、"
                "半开区间给出空集 —— 这是开闭之争的判决性证据。"
            ),
        }
    return result


def _named_case_study() -> dict:
    """具名个案:csi300 在 ``2026-06-30`` 生效的那次调整(冻结线之内)。

    * "调出"= 最后一段以 ``2026-06-29`` 收尾且此后再无段。
    * "调入"= 有一段以 ``2026-06-30`` 开头且此前从未出现。

    预期(若 out_date 是"最后一个仍在成分内的日历日"):
    调出者在湖 ``20260529`` 快照里**在**、``20260630`` 快照里**不在**;
    调入者反之。
    """
    rows, _ = parse_instruments_file("csi300")
    per: dict[str, list[tuple[dt.date, dt.date]]] = collections.defaultdict(list)
    for r in rows:
        per[r.code].append((r.in_date, r.out_date))
    for v in per.values():
        v.sort()

    boundary_out = dt.date(2026, 6, 29)
    boundary_in = dt.date(2026, 6, 30)
    leavers = sorted(c for c, v in per.items() if v[-1][1] == boundary_out)
    joiners = sorted(
        c
        for c, v in per.items()
        if any(a == boundary_in for a, _ in v) and not any(b == boundary_out for _, b in v)
    )

    with lake.catalog() as con:
        def members(compact: str) -> set[str]:
            return {
                c
                for (c,) in con.execute(
                    "SELECT DISTINCT con_code FROM index_weight "
                    "WHERE index_code = '000300.SH' AND trade_date = ?",
                    [compact],
                ).fetchall()
            }

        before = members("20260529")
        after = members("20260630")
        names = {}
        for code in leavers + joiners:
            got = con.execute(
                "SELECT name FROM stock_basic WHERE ts_code = ? LIMIT 1", [code]
            ).fetchall()
            names[code] = got[0][0] if got else None

    return {
        "index": "000300.SH (csi300)",
        "effective_date_of_change": boundary_in.isoformat(),
        "qlib_out_date_of_leavers": boundary_out.isoformat(),
        "lake_snapshot_before": "20260529",
        "lake_snapshot_after": "20260630",
        "n_leavers": len(leavers),
        "n_joiners": len(joiners),
        "leavers": leavers,
        "joiners": joiners,
        "leavers_present_in_snapshot_before": sorted(c for c in leavers if c in before),
        "leavers_present_in_snapshot_after": sorted(c for c in leavers if c in after),
        "joiners_present_in_snapshot_before": sorted(c for c in joiners if c in before),
        "joiners_present_in_snapshot_after": sorted(c for c in joiners if c in after),
        "names": names,
        "verdict": (
            "调出者在 out_date 之前的快照里全部在册、在 in_date 当天的快照里全部不在;"
            "调入者恰好相反。=> in_date 是生效日(当天已在成分内),"
            "out_date 是最后一个仍在成分内的日历日(闭区间),退出生效日 = out_date + 1 天。"
        ),
    }


def _lake_resolution(rows: list[Interval]) -> dict:
    """归一化后的代码能不能在湖 `stock_basic` 里落到实处。

    这不是"映射失败"(前缀规则本身没失败),但对账时必须先知道有多少码
    在湖里根本查不到,否则会被当成"源A 漏了"。
    """
    with lake.catalog() as con:
        known = {c for (c,) in con.execute("SELECT DISTINCT ts_code FROM stock_basic").fetchall()}
    out: dict[str, dict] = {"lake_stock_basic_n_codes": len(known), "per_universe": {}}
    for universe in UNIVERSE_ORDER:
        codes = sorted({r.code for r in rows if r.universe == universe})
        if not codes:
            continue
        missing = [c for c in codes if c not in known]
        classified: dict[str, list[str]] = collections.defaultdict(list)
        for code in missing:
            classified[_classify_unresolved(code)].append(code)
        out["per_universe"][universe] = {
            "n_codes": len(codes),
            "n_unresolved_in_lake": len(missing),
            "by_class": {k: len(v) for k, v in sorted(classified.items())},
            "unresolved_excluding_bj_migration": sorted(
                c for c in missing if _classify_unresolved(c) != "bj_pre2025_migration_code"
            ),
            "bj_pre2025_migration_sample": sorted(
                classified.get("bj_pre2025_migration_code", [])
            )[:10],
        }
    return out


def _classify_unresolved(code: str) -> str:
    symbol, _, exchange = code.partition(".")
    if exchange == "BJ":
        return "bj_new_920_code" if symbol.startswith("920") else "bj_pre2025_migration_code"
    if not _SYMBOL_RE.match(symbol):
        return "nonstandard_symbol"
    if (exchange == "SH" and symbol.startswith("000")) or (
        exchange == "SZ" and symbol.startswith("399")
    ):
        return "index_instrument_not_a_stock"
    return "a_share_absent_from_lake_stock_basic"


def _non_stock_entries(rows: list[Interval]) -> dict:
    """指数条目 —— `all.txt` 里混着指数,当股票宇宙用会凭空多出 6 只"票"。"""
    out: dict[str, list[dict]] = {}
    for universe in UNIVERSE_ORDER:
        hits = sorted(
            {
                (r.code, r.raw_code, r.in_date, r.out_date)
                for r in rows
                if r.universe == universe
                and _classify_unresolved(r.code) == "index_instrument_not_a_stock"
            }
        )
        if hits:
            out[universe] = [
                {"code": c, "raw_code": rc, "in_date": str(a), "out_date": str(b)}
                for c, rc, a, b in hits
            ]
    return out


def _segment_stats(rows: list[Interval]) -> dict:
    """每个宇宙的条数 / 去重 code 数 / 日期范围 / 多段分布。"""
    out: dict[str, dict] = {}
    for universe in UNIVERSE_ORDER:
        subset = [r for r in rows if r.universe == universe]
        if not subset:
            continue
        per_code = collections.Counter(r.code for r in subset)
        hist = collections.Counter(per_code.values())
        multi = {c: n for c, n in per_code.items() if n > 1}
        freeze = dt.date.fromisoformat(cfg.FREEZE_DATE)
        out[universe] = {
            "source_file": UNIVERSE_FILES[universe],
            "n_intervals": len(subset),
            "n_distinct_codes": len(per_code),
            "in_date_min": str(min(r.in_date for r in subset)),
            "in_date_max": str(max(r.in_date for r in subset)),
            "out_date_min": str(min(r.out_date for r in subset)),
            "out_date_max": str(max(r.out_date for r in subset)),
            "n_codes_with_multiple_segments": len(multi),
            "max_segments_per_code": max(per_code.values()),
            "segments_per_code_hist": {str(k): v for k, v in sorted(hist.items())},
            "top_codes_by_segments": [
                {"code": c, "n_segments": n} for c, n in per_code.most_common(5)
            ],
            "n_right_censored_at_freeze": sum(1 for r in subset if r.out_date == freeze),
            "exchange_hist": dict(
                sorted(collections.Counter(r.code.split(".")[1] for r in subset).items())
            ),
        }
    return out


# --------------------------------------------------------------------------
# 组装
# --------------------------------------------------------------------------


def _source_manifest() -> dict:
    manifest = source_manifest_path()
    fields: dict[str, str] = {}
    if manifest.exists():
        for line in manifest.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                key, _, value = line.partition("=")
                fields[key.strip()] = value.strip()
    return {
        "qlib_release_dir_name": cfg.QLIB_RELEASE.name,
        "source_txt": fields,
        "note": (
            "上游是 chenditc/investment_data 的 qlib_bin 发布,其成分区间由 Tushare "
            "index_weight 快照生成 —— 与湖里的 index_weight 同宗,不是独立数据源。"
        ),
    }


def build_summary(
    raw_rows: list[Interval],
    frozen_rows: list[Interval],
    diags: dict[str, dict],
    freeze_ledger: dict,
    *,
    with_lake: bool = True,
) -> dict:
    """拼出 `ops/universe_source_B.json` 的内容。

    Args:
        raw_rows: 未截断的区间(用于"原始"口径统计与结构证据)。
        frozen_rows: 截到冻结线后的区间(即产物本身)。
        diags: 各文件的解析诊断。
        freeze_ledger: `apply_freeze()` 的账目。
        with_lake: 是否跑数据湖交叉验证(需要 catalog 只读连接)。

    Returns:
        可直接 `json.dump` 的 dict。
    """
    prefix_global: collections.Counter[str] = collections.Counter()
    unmapped_all: list[dict] = []
    anomalies_all: list[dict] = []
    for universe, diag in diags.items():
        for prefix, n in diag["prefix_enumeration"].items():
            prefix_global[prefix] += n
        for item in diag["unmapped"]:
            unmapped_all.append({"universe": universe, **item})
        for item in diag["symbol_anomalies"]:
            anomalies_all.append({"universe": universe, **item})

    summary: dict = {
        "card": "1.1-sourceB",
        "generated_by": "snapshots.universe_qlib",
        "source": _source_manifest(),
        "output": {
            "parquet_relative_to_snapshots": str(
                parquet_path().relative_to(cfg.SNAPSHOTS)
            ),
            "schema": [
                {"name": f.name, "type": str(f.type), "nullable": f.nullable}
                for f in PARQUET_SCHEMA
            ],
            "sort_order": "universe(按 UNIVERSE_ORDER) → code → in_date",
            "date_dtype_note": "in_date/out_date 是 parquet date32,不是字符串。",
        },
        "interval_convention": {
            "verdict": "闭日历区间 [in_date, out_date]",
            "in_date": "生效日;当天该票已经在成分内;100% 落在交易日上",
            "out_date": (
                "最后一个仍在成分内的日历日(闭);不是退出日,退出生效日 = out_date + 1 天;"
                "不保证是交易日"
            ),
            "equivalent_half_open_form": "[in_date, next_in_date) —— 按日历天,不是按 out_date",
            "how_to_materialise_a_daily_universe": "in_date <= D <= out_date",
            "endpoint_semantics_differ_by_file": {
                "csi*": (
                    "两端都是**日历日**。in_date 是成分调整生效日(实测 100% 是交易日),"
                    "out_date 由 `下一期 in_date - 1 日历天` 得到,只有 68.5%~91.8% 落在交易日上。"
                    "要'最后一个成分内交易日'就取 <= out_date 的最后一个交易日。"
                ),
                "all": (
                    "两端都是**交易日**(实测 100%)。in_date 是该票在本发布里第一个有数据的交易日、"
                    "out_date 是最后一个 —— 不是上市日/退市日:6142 行里 925 行的 in_date 是日历起点 "
                    "2000-01-04(左删失),右端 2026-08-26 是发布日(右删失)。"
                ),
            },
            "trap": (
                "写成 in_date <= D < out_date 会在每个 epoch 边界日丢掉全部成分 —— "
                "实测那天名单直接变成空集。"
            ),
            "cross_source_warning": (
                "源A(湖 index_weight)是月末时点快照,源B 是区间。"
                "两边约定不统一,对账结果就是垃圾:折算必须用闭区间。"
            ),
        },
        "code_normalization": {
            "rule": "前 2 个字符 = 交易所前缀,其余 = 代码本体 → '<symbol>.<EX>'",
            "examples": {
                "SH600000": "600000.SH",
                "SZ000001": "000001.SZ",
                "BJ430017": "430017.BJ",
            },
            "prefixes_found_by_scanning": dict(sorted(prefix_global.items())),
            "prefixes_expected": list(KNOWN_EXCHANGE_PREFIXES),
            "note": (
                "前缀是**扫全量枚举出来的**,不是假设。实测只出现 SH/SZ/BJ 三种;"
                "任何新前缀都会进 unmapped 而不是被丢掉。"
            ),
            "n_unmapped": len(unmapped_all),
            "unmapped": unmapped_all,
            "n_symbol_anomalies": len(anomalies_all),
            "symbol_anomalies": anomalies_all,
        },
        "semantics_warning": {
            "all_txt": (
                "all.txt 是**每只票一段总的上市区间**(1 段/code),"
                "左端 2000-01-04 是日历起点(左删失)、右端是发布日(右删失),"
                "都不是真实上市/退市日;且里面**混着指数代码**。"
            ),
            "csi_txt": "csi*.txt 是**成分区间多段**,语义与 all.txt 不同,禁止混用。",
            "non_stock_entries": _non_stock_entries(raw_rows),
        },
        "freeze": freeze_ledger,
        "parse_diagnostics": diags,
        "per_universe": _segment_stats(frozen_rows),
        "per_universe_raw_before_freeze": _segment_stats(raw_rows),
        "epoch_structure": _epoch_evidence(raw_rows),
        "evidence_structural": _structural_evidence(raw_rows),
        "lake_resolution": _lake_resolution(raw_rows) if with_lake else None,
        "totals": {
            "n_intervals": len(frozen_rows),
            "n_intervals_before_freeze": len(raw_rows),
            "n_distinct_codes_union": len({r.code for r in frozen_rows}),
        },
    }
    if with_lake:
        summary["evidence_lake_crosscheck"] = _lake_evidence()
        summary["evidence_named_case"] = _named_case_study()
    summary["known_data_hazards"] = _known_hazards(summary)
    return summary


def _known_hazards(summary: dict) -> list[dict]:
    """把这轮考据踩出来的坑固化成清单,给对账卡直接用。"""
    epochs = summary["epoch_structure"]
    hazards: list[dict] = [
        {
            "id": "B-01",
            "severity": "high",
            "what": "csi1000 在 2015-05-29 之前只有 3 个成分",
            "detail": (
                "首个 epoch [2014-10-31, 2015-05-28] 只有 3 个成员(应为 1000),"
                "上游快照残缺。该区间的 csi1000 宇宙不可用。"
            ),
            "evidence": epochs.get("csi1000", {}).get("off_modal_epochs", [])[:1],
        },
        {
            "id": "B-02",
            "severity": "high",
            "what": "csi800 在 2012-01-31 之前每期只有 200 个成分",
            "detail": (
                "2007-01-22 ~ 2012-01-30 之间 104 个 epoch 的成员数是 200/204(应为 800),"
                "只有零星几期是完整 800。csi800 早期宇宙不可用。"
            ),
            "evidence": epochs.get("csi800", {}).get("member_count_hist", {}),
        },
        {
            "id": "B-03",
            "severity": "medium",
            "what": "北交所 2025 年代码迁移会把同一家公司在区间表里拆成两个 code",
            "detail": (
                "241 个 43xxxx/83xxxx/87xxxx 老码在 all.txt 里于 2025-09-30 结束,"
                "241 个 920xxx 新码于 2025-10-09 开始。跨 2025-10 的连续性需要额外映射,"
                "老码在湖 stock_basic 里查不到。"
            ),
            "evidence": {"n_old": 241, "n_new": 241, "boundary": ["2025-09-30", "2025-10-09"]},
        },
        {
            "id": "B-04",
            "severity": "medium",
            "what": "all.txt 里混着 6 个指数代码,不是股票",
            "detail": (
                "000300.SH / 000852.SH / 000905.SH / 000906.SH / 000985.SH / 399300.SZ。"
                "当股票宇宙用之前必须过滤,否则凭空多出 6 只'票'。"
            ),
            "evidence": summary["semantics_warning"]["non_stock_entries"].get("all", []),
        },
        {
            "id": "B-05",
            "severity": "medium",
            "what": "T00018.SH 是悬空成分",
            "detail": (
                "csi300 里 7 段(2005-04-08 ~ 2007-01-03),代码本体不是 6 位数字;"
                "既不在 all.txt、也不在 qlib 发布的 features/、也不在湖 stock_basic。"
                "有成分记录但没有任何价格数据。"
            ),
            "evidence": summary["code_normalization"]["symbol_anomalies"],
        },
        {
            "id": "B-06",
            "severity": "medium",
            "what": "指数基数偶发多 1(501/801/1001/1002)与少数(298)",
            "detail": (
                "上游快照在个别期出现成分数偏离基数,直接按 epoch 取名单会拿到 501 只票。"
                "对账时要按期核基数,不要默认 300/500/800/1000。"
            ),
            "evidence": {
                u: v["member_count_hist"] for u, v in epochs.items() if isinstance(v, dict)
            },
        },
        {
            "id": "B-07",
            "severity": "high",
            "what": "源A/源B 同宗,交叉验证不是独立验证",
            "detail": (
                "qlib 发布来自 chenditc/investment_data,其成分数据同样来自 Tushare;"
                "与湖 index_weight 是同一上游。对上不代表数据对,只代表口径一致。"
            ),
            "evidence": summary["source"]["source_txt"],
        },
    ]
    return hazards


# --------------------------------------------------------------------------
# 落盘
# --------------------------------------------------------------------------


def _sorted_rows(rows: list[Interval]) -> list[Interval]:
    rank = {name: i for i, name in enumerate(UNIVERSE_ORDER)}
    return sorted(rows, key=lambda r: (rank[r.universe], r.code, r.in_date, r.out_date))


def write_parquet(rows: list[Interval], path: Path | None = None) -> Path:
    """把区间表写成 parquet(目录 0700,文件 0600)。

    Args:
        rows: 已截到冻结线的区间。
        path: 覆盖默认输出路径(测试用)。

    Returns:
        实际写入的路径。
    """
    target = path or parquet_path()
    cfg.create_dir(target.parent)
    ordered = _sorted_rows(rows)
    table = pa.Table.from_pydict(
        _assert_payload_matches_schema({
            "code": [r.code for r in ordered],
            "universe": [r.universe for r in ordered],
            "in_date": [r.in_date for r in ordered],
            "out_date": [r.out_date for r in ordered],
            "raw_code": [r.raw_code for r in ordered],
            "source_file": [r.source_file for r in ordered],
        }),
        schema=PARQUET_SCHEMA,
    )
    pq.write_table(table, target, compression="zstd")
    os.chmod(target, _FILE_MODE)
    return target


def write_summary(summary: dict, path: Path | None = None) -> Path:
    """把统计摘要写成 JSON(文件 0600)。"""
    target = path or summary_path()
    cfg.create_dir(target.parent)
    target.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=False, default=str) + "\n",
        encoding="utf-8",
    )
    os.chmod(target, _FILE_MODE)
    return target


def main(argv: list[str] | None = None) -> int:
    """构建源B 区间表 + 摘要。

    用法::

        $GENEBENCH_ROOT/env/bin/python -m snapshots.universe_qlib

    ``--no-lake`` 跳过数据湖交叉验证(离线自检用)。
    """
    args = list(sys.argv[1:] if argv is None else argv)
    with_lake = "--no-lake" not in args
    cfg.harden_umask()
    lake.raise_open_file_limit()

    raw_rows, diags = load_all()
    frozen_rows, ledger = apply_freeze(raw_rows)
    summary = build_summary(raw_rows, frozen_rows, diags, ledger, with_lake=with_lake)
    parquet = write_parquet(frozen_rows)
    js = write_summary(summary)

    print(f"parquet: {parquet}  rows={len(frozen_rows)}")
    print(f"summary: {js}")
    for universe, stat in summary["per_universe"].items():
        print(
            f"  {universe:<8} intervals={stat['n_intervals']:>6}"
            f"  codes={stat['n_distinct_codes']:>5}"
            f"  {stat['in_date_min']}..{stat['out_date_max']}"
            f"  多段码={stat['n_codes_with_multiple_segments']:>5}"
        )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
