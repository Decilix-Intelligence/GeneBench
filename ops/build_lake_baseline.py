"""生成 `ops/lake_baseline.json`(+ 同名 .md)—— 卡 0.2 的产物。

对 `snapshots/v1_tables.py` 登记的每张 v1 依赖表做一次体检:视图在不在、
多少行多少列、日期列覆盖到哪天、gold 有多少分区、最新分区是哪个、
**冻结线过没过**、以及 —— 卡 0.2 补救新增 —— **这张表还活着吗**。

谁说了算(卡 0.2 补救 D2:审计降级为旁证)
------------------------------------------
`rows` / `columns` / `min_date` / `max_date` 一律 **`duckdb` 只读连接现场重算**。
`$LAKE/manifests/coverage-audit-latest.json` 的对应值保留,但改名成
`audit_rows` / `audit_columns` / `audit_min_date` / `audit_max_date`,
并带上 `audit_as_of` —— 它只是**旁证**,不再是判据。

为什么不能再信审计:它的 timer 是
``OnCalendar=Mon..Fri *-*-* 23:20:00 Asia/Shanghai``(= 15:20 UTC,
另有 `RandomizedDelaySec=5m`,实测落在 15:22)。**周末不跑**,所以周一早上拿到的
`as_of` 天然是上周五 —— 滞后 1-3 天是**结构性**的,不是偶发故障。
本卡第一版基线就是抄了 as_of=20260828 的审计值,于是 5 张表的
`rows`/`max_date` 与现场对不上(如 `income_vip` 393932→401367、20260822→20260829)。

数据来源
--------
1. duckdb 只读连接 —— 视图是否存在、列名清单、**行数、日期列 min/max**(权威)。
2. `os.scandir` —— gold 分区名/数量/最新分区,**新鲜度的正确来源**
   (不是 crawler_state 的 watermarks,那是补数游标)。
3. `coverage-audit-latest.json` —— 只当旁证,进 `audit_*` 字段。

跑法::

    cd $REPO && $GENEBENCH_ROOT/env/bin/python ops/build_lake_baseline.py

进程退出码:全部表过冻结线且视图齐全 = 0,否则 = 1。
**停更表不影响退出码** —— 它们对 v1 的 ≤ 冻结线窗口不构成数据缺口,
但必须被显式列出来(见 `summary.stalled_tables`)。
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# ⚠️ 收紧 umask 必须发生在**任何仓库内 import 之前**,不能等到 main()。
#
# 本机默认 umask 是 002。CPython 在 import 一个模块时就会现建 `__pycache__/`
# 写字节码 —— 那一刻 main() 还没跑,`cfg.harden_umask()` 也还没被调到,
# 于是 `snapshots/__pycache__` 会落成 **0775**,踩掉卡 0.1 的红线 5 递归审计
# (`ops/test_env.py::test_every_dir_under_root_blocks_group_and_world`)。
# 这不是假想:本卡第一次跑 builder 就真的把它建成了 0775。
#
# 这里的字面量 0o077 是刻意重复 `cfg.REQUIRED_UMASK` 的 —— 它必须早于
# `import genebench_config` 生效,拿不到常量。下面紧跟一条断言,防止两处漂移。
# **后续所有非 pytest 入口(runner / scorer / 网关)都要照抄这三行。**
# ---------------------------------------------------------------------------
_PREVIOUS_UMASK = os.umask(0o077)

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import genebench_config as cfg  # noqa: E402
from snapshots import lake, v1_tables  # noqa: E402

assert 0o077 == cfg.REQUIRED_UMASK, (
    f"上面硬写的 umask 0o077 与 cfg.REQUIRED_UMASK={oct(cfg.REQUIRED_UMASK)} 漂移了"
)

#: 湖自带的全量覆盖审计。**只当旁证**(见模块 docstring)。
COVERAGE_AUDIT: Path = cfg.LAKE / "manifests" / "coverage-audit-latest.json"

#: 审计 timer 的实测排班 —— 解释 `audit_*` 为什么天然滞后。
COVERAGE_AUDIT_CADENCE: str = (
    "quant-datahub-coverage-audit.timer: "
    "OnCalendar=Mon..Fri *-*-* 23:20:00 Asia/Shanghai(=15:20 UTC)"
    "+ RandomizedDelaySec=5m(实测落在 15:22 UTC)。"
    "**周末不触发** —— 周六/周日/周一上午取到的 as_of 一律是上周五,"
    "滞后 1-3 天是**结构性的,不是偶发故障**。"
    "所以 audit_* 只当旁证,rows/columns/min_date/max_date 一律以现场重算为准。"
)

#: 产物。
BASELINE_JSON: Path = cfg.OPS / "lake_baseline.json"
BASELINE_MD: Path = cfg.OPS / "lake_baseline.md"


def _freeze_bound_for(partition_value: str) -> str | None:
    """按分区值的形态,给出与之同形态的冻结线上界。

    `2026-07-31` 形态 → ``'2026-07-31'``;`202607` 形态 → ``'202607'``;
    `20260731` 形态 → ``'20260731'``。认不出形态返回 `None`。
    """
    if len(partition_value) == 10 and partition_value[4] == "-" and partition_value[7] == "-":
        return cfg.FREEZE_DATE
    if len(partition_value) == 8 and partition_value.isdigit():
        return lake.FREEZE_DATE_COMPACT
    if len(partition_value) == 6 and partition_value.isdigit():
        return lake.FREEZE_DATE_COMPACT[:6]
    return None


# ==========================================================================
# 新鲜度 / 停更(卡 0.2 补救 D3)
#
# 冻结线只回答"历史够不够",**不回答"这张表还活着吗"**。
# 实测 6 张表 max_date 越过了冻结线(于是判据 ② 一片绿)却早已停更 ——
# 卡 1.3 的网关作者若照这份基线判新鲜度,必踩坑。
# 下面这组**纯函数**(不碰 IO)是那把尺子,builder 和验收测试共用同一份实现,
# 免得两处逻辑漂移。
# ==========================================================================


def compact(value: str) -> str:
    """把 `2026-08-05` 归一成 `20260805`;已经是紧凑形态就原样返回。"""
    return value.replace("-", "")


def days_between(earlier: str, later: str) -> int:
    """两个 `YYYYMMDD` 之间的**日历**天数(``later - earlier``)。"""
    def parse(v: str) -> date:
        v = compact(v)
        return date(int(v[:4]), int(v[4:6]), int(v[6:8]))

    return (parse(later) - parse(earlier)).days


def freshness_date(
    *,
    semantics: str,
    date_column: str | None,
    live_max: str | None,
    latest_capture: str | None,
) -> tuple[str | None, str]:
    """这张表的数据"新到哪天",以及这个答案是**从哪来的**。

    两条规则,顺序不能反:

    1. `capture_time` 分区(`snapshot_date`)的表,新鲜度**只看快照日**,
       哪怕它有日期列。这是 H4 的正面用法:`trade_cal` 有 `cal_date` 且
       max 到 **20261231** —— 那是快照里预写的**未来日历**,拿它当新鲜度
       会让一张从 2026-08-05 起再没抄过的表变成"全湖最新",
       还会把整个湖的新鲜度基准拖到年底。
    2. 其余表看 `max(date_column)` 的**现场**值。

    Returns:
        ``(新鲜度日期 YYYYMMDD 或 None, 这个答案的来源说明)``。
    """
    if semantics == "capture_time":
        if latest_capture:
            return compact(latest_capture), "latest_capture_partition(snapshot_date)"
        return None, "capture_time 分区但一个快照都没有"
    if date_column and live_max:
        return compact(live_max), f"live max({date_column})"
    return None, "无日期列且非 capture_time 分区 —— 新鲜度判不了"


def lake_frontier(
    freshness: dict[str, str | None], cadences: dict[str, str]
) -> str | None:
    """湖侧"最新的一天" —— 全部 `trading_day` 节奏表里最新的那个新鲜度日期。

    为什么拿湖**自己**当基准而不是拿墙上时钟:体检可能在任何时候跑
    (周末、假期、补数窗口),用 `today()` 会让同一份数据在周一和周六得出
    不同结论。用"湖里跑得最快的那张表"当基准,判的是**表之间的相对滞后**,
    这正是要回答的问题:同样是日频表,凭什么 `daily` 到 08-28 而
    `limit_list_d` 停在 08-05。

    **已知局限**(写下来,别让下一个人以为它全能):如果全部日频表**一起**
    停更,基准会跟着一起退,谁也不会被标红。所以 baseline 另外记了
    `frontier_lag_from_generated_at_days`(基准离体检时刻多远)当旁证 ——
    那个数一大,说明该怀疑的是整个湖,不是某一张表。
    """
    values = [
        v for ds, v in freshness.items() if v and cadences.get(ds) == "trading_day"
    ]
    return max(values) if values else None


def stall_verdict(
    *,
    cadence: str,
    fresh: str | None,
    frontier: str | None,
) -> dict[str, Any]:
    """这张表停更了吗 —— `True` / `False` / `None`(判不了)。

    判据:``滞后天数 = frontier - 本表新鲜度日期``,超过该节奏的容忍度
    (`v1_tables.CADENCE_TOLERANCE_DAYS`)就算停更。

    `None` 是**认真的第三种答案**:`irregular` 节奏(区间表)和拿不到
    新鲜度日期的表,一律判不了。不许因为判不了就默认它是活的 ——
    那正是这次补救要堵的那种"沉默的绿"。
    """
    tolerance = v1_tables.stale_after_days(cadence)
    if fresh is None or frontier is None or tolerance is None:
        return {
            "lag_days": None,
            "stale_after_days": tolerance,
            "stalled": None,
            "stall_reason": (
                f"判不了:cadence={cadence}"
                f"(容忍度={tolerance})、新鲜度日期={fresh}、湖侧基准={frontier}"
            ),
        }
    lag = days_between(fresh, frontier)
    stalled = lag > tolerance
    return {
        "lag_days": lag,
        "stale_after_days": tolerance,
        "stalled": stalled,
        "stall_reason": (
            f"{'停更' if stalled else '仍在更新'}:新鲜度 {fresh} 落后湖侧基准 "
            f"{frontier} 共 {lag} 天,{cadence} 节奏的容忍度是 {tolerance} 天"
        ),
    }


#: 本卡实测出来的湖侧陷阱。写进 baseline 是为了让卡 1.3/1.4 的作者不用重踩一遍。
KNOWN_HAZARDS: tuple[dict[str, str], ...] = (
    {
        "id": "H1",
        "title": "关掉 union_by_name 是**静默丢列**,不是报错",
        "evidence": (
            "read_gold('daily', 'trade_date=2026-08-0*') 在 union_by_name=False 下"
            "安静地返回 13 列(丢了 last_seen_at),=True 返回 14 列。duckdb 按第一个"
            "文件的 schema 绑定,后面文件多出来的列直接不要。"
        ),
        "impact": "卡 1.3/1.4 跨分区取数若关掉 union,会在无任何报错的情况下少一列。",
        "mitigation": "lake.read_gold() 默认 union_by_name=True;只读单分区时才可关。",
    },
    {
        "id": "H2",
        "title": "schema 漂移是**逐分区**的,不是按时间整齐切分",
        "evidence": (
            "income 的 ts_code=000001.SZ 有 89 列,而 300325.SZ/301381.SZ/920992.BJ "
            "都是 88 列;balancesheet 156/155、cashflow 101/100 同理。"
            "daily 则是按时间切:trade_date=2026-08-06 起从 13 列变 14 列。"
        ),
        "impact": "拿单个分区探 schema 会得出'没漂移'的错误结论。",
        "mitigation": "本基线对每张表抽样首/中/末/冻结窗口末共 4 个分区,报并集与漂移列。",
    },
    {
        "id": "H3",
        "title": "还有**列类型**漂移,会在跨分区读时抛异常",
        "evidence": (
            "read_gold('income', 'ts_code=00000*', union_by_name=False) 抛 "
            "ConversionException: failed to cast column \"oper_cost\"。"
        ),
        "impact": "三大报表跨票取数是 v1 基本面因子的主路径,踩上就整批失败。",
        "mitigation": "同 H1:走 union_by_name=True。",
    },
    {
        "id": "H4",
        "title": "snapshot_date 分区是**抓取时间**,不是数据时间",
        "evidence": (
            "trade_cal / stock_basic / index_basic 的快照最早 2026-08-05,全部晚于"
            "冻结线 2026-07-31;但 trade_cal 的 cal_date 覆盖 20090101→20261231。"
        ),
        "impact": "按分区截冻结线会得出'这些表在 v1 窗口内没有数据'的错误结论。",
        "mitigation": (
            "lake.partition_semantics() 把它标成 capture_time;PIT 语义走表内字段"
            "(list_date/delist_date/cal_date)回溯,不选快照。"
        ),
    },
    {
        "id": "H5",
        "title": "默认 fd 上限 1024,查全表必炸",
        "evidence": (
            "finance01 默认 RLIMIT_NOFILE soft=1024 / hard=1048576;catalog 视图是 "
            "read_parquet('<gold>/<ds>/**/*.parquet'),daily 有 4289 个分区文件。"
        ),
        "impact": "SELECT * FROM daily 直接 'Too many open files'。",
        "mitigation": "lake.raise_open_file_limit() 抬 soft 到 8192(无需特权);大表走 read_gold 定向分区。",
    },
    {
        "id": "H6",
        "title": "**过了冻结线 ≠ 这张表还活着**",
        "evidence": (
            "limit_list_d 的 gold 分区硬停在 trade_date=2026-08-05,而 daily 在其后"
            "还有 17 个交易日分区;income/balancesheet/cashflow 的 max(ann_date) 停在 "
            "20260804,孪生的 _vip 表已到 20260828/29;namechange 停在 20260806、"
            "dividend 停在 20260801;trade_cal 只有 1 个 snapshot_date=2026-08-05 分区、"
            "index_basic 只有 2 个(最新 2026-08-06),从此再没抄过。"
            "这 6 张表的 max_date 全都 >= 20260731,于是在只看冻结线的基线里**一片绿**。"
        ),
        "impact": (
            "卡 1.3 的网关若照'过冻结线'判新鲜度,会把停更表当成实时表对外供数;"
            "对 v1 的 ≤2026-07-31 窗口它们不构成数据缺口,但**语义是错的**。"
        ),
        "mitigation": (
            "baseline 的 summary.stalled_tables 显式列出停更表;每张表带 "
            "update_cadence / lag_days / stalled 三个字段,md 里'过冻结线'与"
            "'仍在更新'分成**两列**渲染,不再合并成同一种绿。"
        ),
    },
    {
        "id": "H7",
        "title": "coverage-audit 周末不跑,`as_of` 天然滞后 1-3 天",
        "evidence": COVERAGE_AUDIT_CADENCE,
        "impact": (
            "本卡第一版基线直接抄了 as_of=20260828 的审计值,于是 5 张表对不上现场:"
            "stock_st 337072/20260825、income_vip 393932/20260822、"
            "balancesheet_vip 343135/20260822、cashflow_vip 407461/20260822、"
            "st_history 1221 行 —— 全部低于现场重算值。"
        ),
        "mitigation": (
            "rows/columns/min_date/max_date 一律现场重算(lake.column_range),"
            "审计值降级成 audit_* 前缀的旁证并标注 audit_as_of。"
        ),
    },
)


def _probe_partitions(parts: list[str], upto: list[str]) -> list[str]:
    """挑几个分区去量 schema 漂移:首、中、末,外加冻结窗口内最后一个。

    刻意不止取一个 —— 漂移是**逐分区**的,拿一个分区当代表会得出"没漂移"的
    错误结论(实测 `income` 只有 `ts_code=000001.SZ` 多一列)。
    """
    if not parts:
        return []
    picks = [parts[0], parts[len(parts) // 2], parts[-1]]
    if upto:
        picks.append(upto[-1])
    seen: list[str] = []
    for p in picks:
        if p not in seen:
            seen.append(p)
    return seen


def _audit_entry(audit: dict[str, Any], dataset: str) -> dict[str, Any]:
    """取审计里某个数据集的条目;没有就给一个 status=absent 的空壳。"""
    entry = audit.get("datasets", {}).get(dataset)
    if entry is None:
        return {"status": "absent_from_audit"}
    return entry


def build_entry(
    table: v1_tables.TableSpec,
    audit: dict[str, Any],
    audit_as_of: str | None,
    views: set[str],
    conn: Any,
) -> dict[str, Any]:
    """给一张表做体检,产出 `lake_baseline.json` 里的一条。"""
    ds = table.dataset
    a = _audit_entry(audit, ds)

    view_exists = ds in views
    column_names = lake.describe_view(ds, conn=conn) if view_exists else []

    parts = lake.gold_partitions(ds)
    part_key = lake.gold_partition_key(ds)
    semantics = lake.partition_semantics(ds)
    latest_part = parts[-1] if parts else None
    latest_value = lake.split_partition(latest_part)[1] if latest_part else None

    # 只有 data_time 分区能拿来截冻结线。capture_time(snapshot_date)是"哪天抄的表",
    # entity_code(ts_code / l3_code)干脆与时间无关 —— 对它们截线只会得出错误结论。
    bound = (
        _freeze_bound_for(latest_value)
        if (semantics == "data_time" and latest_value)
        else None
    )
    upto = lake.partitions_upto(ds, bound) if bound is not None else []

    # ---- 现场重算(D2:这里才是判据,审计只是旁证)----
    date_column = table.date_column
    if date_column and view_exists and date_column not in column_names:
        raise RuntimeError(
            f"{ds}:登记表声明 date_column={date_column!r},但 catalog 视图里没有这一列"
            f"(现有列:{column_names[:12]}...)。改 snapshots/v1_tables.py。"
        )

    if view_exists and date_column:
        rng = lake.column_range(
            ds, date_column, bound=lake.FREEZE_DATE_COMPACT, conn=conn
        )
        rows = rng["rows"]
        min_date, max_date = rng["min"], rng["max"]
        max_date_upto_freeze = rng["max_upto"]
    elif view_exists:
        rows = lake.count_rows(ds, conn=conn)
        min_date = max_date = max_date_upto_freeze = None
    else:
        rows = None
        min_date = max_date = max_date_upto_freeze = None

    if date_column and max_date:
        freeze_line_ok: bool | None = str(max_date) >= lake.FREEZE_DATE_COMPACT
        freeze_check = (
            f"现场 max({date_column})={max_date} >= {lake.FREEZE_DATE_COMPACT}"
        )
    elif date_column and not max_date:
        freeze_line_ok = False
        freeze_check = f"date_column={date_column} 但现场查不到 max —— 视为不合格"
    else:
        freeze_line_ok = None
        freeze_check = "n/a:无日期列(区间表/元数据表),冻结线不适用"

    # ---- 分区间 schema 漂移 ----
    # 视图的列 = 全部分区列的并集,不等于任一分区的真实列,而且**逐分区都可能不同**
    # (实测 income 的 000001.SZ 有 89 列、多数分区 88 列)。所以抽样多个分区,
    # 报"并集/交集/漂移列",而不是拿一个分区当代表。
    probe_parts = _probe_partitions(parts, upto)
    probe_cols: dict[str, list[str]] = {}
    if view_exists:
        for p in probe_parts:
            probe_cols[p] = list(lake.read_gold(ds, p, limit=0, conn=conn).columns)
    union_cols: set[str] = set().union(*probe_cols.values()) if probe_cols else set()
    inter_cols: set[str] = (
        set.intersection(*(set(v) for v in probe_cols.values())) if probe_cols else set()
    )
    drifting = sorted(union_cols - inter_cols)
    only_in_view = [c for c in column_names if c not in union_cols]

    # ---- 审计对账(旁证,不是判据)----
    audit_deltas: dict[str, Any] = {}
    if a.get("rows") is not None and rows is not None and a["rows"] != rows:
        audit_deltas["rows"] = {"audit": a["rows"], "live": rows, "delta": rows - a["rows"]}
    if a.get("max_date") and max_date and str(a["max_date"]) != str(max_date):
        audit_deltas["max_date"] = {"audit": str(a["max_date"]), "live": str(max_date)}
    if a.get("columns") is not None and a["columns"] != len(column_names):
        audit_deltas["columns"] = {"audit": a["columns"], "live": len(column_names)}
    if (a.get("date_column") or None) != date_column:
        audit_deltas["date_column"] = {
            "audit": a.get("date_column"),
            "registry": date_column,
            "why": table.date_column_why,
        }

    notes = [table.notes] if table.notes else []
    if only_in_view or drifting:
        sizes = ", ".join(f"{p}={len(c)}列" for p, c in probe_cols.items())
        notes.append(
            f"⚠️ 分区间 schema 漂移:catalog 视图 {len(column_names)} 列(全分区并集),"
            f"抽样分区实际为 {sizes}"
            + (f";抽样间就不一致的列 {drifting}" if drifting else "")
            + (f";视图有而抽样分区都没有的列 {only_in_view}" if only_in_view else "")
            + "。按视图列清单写取数代码会要到取不到的列;"
            "跨分区读**必须** union_by_name=True(关掉是**静默丢列**,不是报错)。"
        )
    if semantics == "entity_code":
        notes.append(
            f"分区键是 {part_key}(实体码),'最新分区' {latest_part} 只是字典序最大的代码,"
            f"**不能当新鲜度**;新鲜度看 {date_column or '表内字段区间'}。"
        )
    elif semantics == "capture_time":
        notes.append(
            f"分区键是 {part_key}(**抓取时间**,不是数据时间):快照 {parts[0]} → {latest_part} "
            f"**全部晚于冻结线 {cfg.FREEZE_DATE}**,冻结窗口内根本没有快照可选。"
            f"这不是数据缺口 —— 这类表的 PIT 语义在**字段**上"
            f"(list_date/delist_date/cal_date),网关必须走字段回溯而不是选快照。"
        )
    if audit_deltas:
        notes.append(
            f"审计(as_of={audit_as_of})与现场重算有出入 {sorted(audit_deltas)} ——"
            f"**以现场为准**,审计值见 audit_* 字段(H7:审计周末不跑,天然滞后 1-3 天)。"
        )
    if a.get("cross_snapshot_repeated_key_rows"):
        notes.append(
            f"多快照表:跨快照重复主键 {a['cross_snapshot_repeated_key_rows']} 行"
            f"(同一 code 在多个 snapshot 里各有一行,取数必须先选定快照)。"
        )

    return {
        # —— 卡 0.2 要求的字段(全部现场重算)——
        "dataset": ds,
        "view_exists": view_exists,
        "rows": rows,
        "columns": len(column_names),
        "date_column": date_column,
        "min_date": min_date,
        "max_date": max_date,
        "gold_partition_count": len(parts),
        "latest_gold_partition": latest_part,
        "used_by_cards": list(table.used_by_cards),
        "freeze_line_ok": freeze_line_ok,
        "notes": "；".join(notes),
        # —— 判据的出处 ——
        "values_source": "live_recompute(duckdb read_only)",
        "date_column_source": "snapshots/v1_tables.py",
        "date_column_why": table.date_column_why,
        "max_date_upto_freeze": max_date_upto_freeze,
        "freeze_line_check": freeze_check,
        # —— 审计旁证(D2:降级,不再是判据)——
        "audit_as_of": audit_as_of,
        "audit_status": a.get("status"),
        "audit_rows": a.get("rows"),
        "audit_columns": a.get("columns"),
        "audit_date_column": a.get("date_column"),
        "audit_min_date": a.get("min_date"),
        "audit_max_date": a.get("max_date"),
        "audit_agrees_with_live": not audit_deltas,
        "audit_deltas": audit_deltas,
        # —— 补充证据 ——
        "role": table.role,
        "why_needed": table.why,
        "column_names": column_names,
        "gold_partition_key": part_key,
        "partition_semantics": semantics,
        "gold_latest_partition_value": lake.gold_latest_value(ds),
        "gold_latest_capture": lake.gold_latest_capture(ds),
        "gold_partitions_upto_freeze": len(upto) if bound is not None else None,
        "latest_gold_partition_upto_freeze": upto[-1] if upto else None,
        "schema_probe_partitions": list(probe_cols),
        "columns_in_probe_partitions": {p: len(c) for p, c in probe_cols.items()},
        "columns_drifting_across_probes": drifting,
        "columns_only_in_view": only_in_view,
        # —— 新鲜度 / 停更(D3,下面第二遍补齐 lag/stalled)——
        "update_cadence": table.update_cadence,
    }


def annotate_freshness(entries: list[dict[str, Any]]) -> str | None:
    """第二遍:算湖侧基准,给每条补上新鲜度与停更判定。

    必须是**第二遍** —— 基准是全部日频表的最大值,单张表体检时还不知道。
    """
    cadences = {e["dataset"]: e["update_cadence"] for e in entries}
    freshness: dict[str, str | None] = {}
    sources: dict[str, str] = {}
    for e in entries:
        fresh, src = freshness_date(
            semantics=e["partition_semantics"],
            date_column=e["date_column"],
            live_max=e["max_date"],
            latest_capture=e["gold_latest_capture"],
        )
        freshness[e["dataset"]] = fresh
        sources[e["dataset"]] = src

    frontier = lake_frontier(freshness, cadences)

    for e in entries:
        ds = e["dataset"]
        e["freshness_date"] = freshness[ds]
        e["freshness_source"] = sources[ds]
        e.update(
            stall_verdict(
                cadence=e["update_cadence"], fresh=freshness[ds], frontier=frontier
            )
        )
        if e["stalled"] is True:
            e["notes"] = (
                f"⛔ 停更(体检判定):{e['stall_reason']}。"
                f"注意它 freeze_line_ok={e['freeze_line_ok']} —— "
                f"**过了冻结线不等于这张表还活着**(H6)。；" + e["notes"]
            )
        elif e["stalled"] is None:
            e["notes"] = f"❔ 新鲜度判不了:{e['stall_reason']}。；" + e["notes"]
    return frontier


def build() -> dict[str, Any]:
    """跑完整体检,返回 baseline 字典(不落盘)。"""
    lake.raise_open_file_limit()
    audit = json.loads(COVERAGE_AUDIT.read_text(encoding="utf-8"))
    audit_as_of = audit.get("as_of")

    with lake.catalog() as conn:
        views = set(lake.list_views(conn))
        entries = [
            build_entry(t, audit, audit_as_of, views, conn) for t in v1_tables.V1_TABLES
        ]

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    frontier = annotate_freshness(entries)

    missing_view = [e["dataset"] for e in entries if not e["view_exists"]]
    stale = [
        {
            "dataset": e["dataset"],
            "date_column": e["date_column"],
            "max_date": e["max_date"],
            "shortfall_days": None,
        }
        for e in entries
        if e["freeze_line_ok"] is False
    ]
    no_date = [e["dataset"] for e in entries if e["freeze_line_ok"] is None]

    stalled_tables = [
        {
            "dataset": e["dataset"],
            "update_cadence": e["update_cadence"],
            "freshness_date": e["freshness_date"],
            "freshness_source": e["freshness_source"],
            "lag_days": e["lag_days"],
            "stale_after_days": e["stale_after_days"],
            "freeze_line_ok": e["freeze_line_ok"],
            "why_it_looks_green": (
                f"max_date={e['max_date']} >= 冻结线 {lake.FREEZE_DATE_COMPACT},"
                f"只看判据 ② 会判成绿"
                if e["freeze_line_ok"]
                else "无日期列,判据 ② 不适用"
            ),
            "used_by_cards": e["used_by_cards"],
        }
        for e in entries
        if e["stalled"] is True
    ]
    unknown_freshness = [e["dataset"] for e in entries if e["stalled"] is None]

    return {
        "card": "0.2",
        "generated_at": generated_at,
        "generator": "ops/build_lake_baseline.py",
        "freeze_line": lake.FREEZE_DATE_COMPACT,
        "freeze_line_iso": cfg.FREEZE_DATE,
        "sources": {
            "authoritative": (
                "duckdb 只读现场重算(rows/columns/min_date/max_date)"
                " + os.scandir(gold 分区)"
            ),
            "coverage_audit": str(COVERAGE_AUDIT),
            "coverage_audit_role": "旁证 only —— 见 audit_* 字段与 H7",
            "coverage_audit_as_of": audit_as_of,
            "coverage_audit_generated_at": audit.get("generated_at"),
            "coverage_audit_status": audit.get("status"),
            "coverage_audit_cadence": COVERAGE_AUDIT_CADENCE,
            "catalog": str(cfg.CATALOG),
            "gold": str(cfg.GOLD),
            "catalog_view_count": len(views),
        },
        "summary": {
            "datasets": len(entries),
            "view_exists_all": not missing_view,
            "missing_views": missing_view,
            "dated_tables": sum(1 for e in entries if e["freeze_line_ok"] is not None),
            "freeze_line_ok_all": not stale,
            "freeze_line_failures": stale,
            "no_date_column_tables": no_date,
            "capture_time_tables": [
                e["dataset"]
                for e in entries
                if e["partition_semantics"] == "capture_time"
            ],
            "entity_code_tables": [
                e["dataset"]
                for e in entries
                if e["partition_semantics"] == "entity_code"
            ],
            "schema_drift_tables": [
                e["dataset"]
                for e in entries
                if e["columns_only_in_view"] or e["columns_drifting_across_probes"]
            ],
            # —— D3:停更清单。**这是与 verdict 正交的一维** ——
            "lake_frontier_date": frontier,
            "lake_frontier_definition": (
                "全部 update_cadence=trading_day 的表里最新的那个新鲜度日期。"
                "拿湖自己当基准(而不是墙上时钟),判的是表之间的相对滞后。"
            ),
            "frontier_lag_from_generated_at_days": (
                days_between(frontier, compact(generated_at[:10])) if frontier else None
            ),
            "stalled_tables": stalled_tables,
            "stalled_count": len(stalled_tables),
            "unknown_freshness_tables": unknown_freshness,
            "freshness_verdict": (
                "ALL_FRESH" if not stalled_tables else "STALLED_TABLES_PRESENT"
            ),
            "stalled_tables_note": (
                f"这 {len(stalled_tables)} 张表**已停更但仍然过冻结线**,"
                f"所以在只看判据 ② 的基线里是一片绿(H6)。"
                f"对 v1 的 ≤{cfg.FREEZE_DATE} 窗口它们**不构成数据缺口**,"
                f"因此不影响本卡 verdict;但卡 1.3 的网关**不得**拿 freeze_line_ok "
                f"当新鲜度判据,要读本字段。"
            ),
            "verdict": "PASS" if (not missing_view and not stale) else "FAIL",
            "verdict_scope": (
                "verdict 只回答卡 0.2 的四条判据(视图齐全 + 过冻结线 + 无日期列表可计数"
                " + lake.py 无写路径),**不**回答'表还活不活'——那是 freshness_verdict。"
            ),
        },
        "known_hazards": KNOWN_HAZARDS,
        "datasets": entries,
        "excluded": [dict(x) for x in v1_tables.EXCLUDED],
        "derived_views": [dict(x) for x in v1_tables.DERIVED_VIEWS],
    }


def render_markdown(baseline: dict[str, Any]) -> str:
    """把 baseline 渲染成人读的 markdown(给复核用,不参与验收)。"""
    s = baseline["summary"]
    lines = [
        "# 湖只读基线(卡 0.2)",
        "",
        f"- 生成时间(UTC):`{baseline['generated_at']}`",
        f"- 冻结线:**{baseline['freeze_line']}**(`freeze_line_ok = max_date >= 冻结线`)",
        f"- **数值口径**:{baseline['sources']['authoritative']}",
        f"- 旁证:`{baseline['sources']['coverage_audit']}`"
        f"(as_of={baseline['sources']['coverage_audit_as_of']},"
        f"status={baseline['sources']['coverage_audit_status']})"
        f" —— {baseline['sources']['coverage_audit_role']}",
        f"- catalog:`{baseline['sources']['catalog']}`"
        f"({baseline['sources']['catalog_view_count']} 个视图)",
        "",
        f"- **卡 0.2 判据**:**{s['verdict']}** —— {s['datasets']} 张表,"
        f"视图齐全={s['view_exists_all']},过冻结线={s['freeze_line_ok_all']}"
        f"(其中 {len(s['no_date_column_tables'])} 张无日期列,冻结线不适用)",
        f"- **新鲜度(另一维)**:**{s['freshness_verdict']}** —— "
        f"{s['stalled_count']} 张停更,{len(s['unknown_freshness_tables'])} 张判不了。"
        f"湖侧基准 `{s['lake_frontier_date']}`。",
        "",
        f"> ⚠️ **两列不是一回事**。{s['stalled_tables_note']}",
        "",
        "## 逐表",
        "",
        "| 数据集 | 视图 | 行数 | 列 | 日期列 | 覆盖 | gold 分区 | 分区语义 "
        "| 最新分区 | 过冻结线 | 仍在更新 | 哪张卡要用 |",
        "| --- | --- | ---: | ---: | --- | --- | ---: | --- | --- | --- | --- | --- |",
    ]
    for e in baseline["datasets"]:
        ok = {True: "✅", False: "❌ **FAIL**", None: "—(无日期列)"}[e["freeze_line_ok"]]
        if e["stalled"] is True:
            alive = f"⛔ **停更 {e['lag_days']} 天**"
        elif e["stalled"] is False:
            alive = f"✅ 活(滞后 {e['lag_days']} 天)"
        else:
            alive = "❔ 判不了"
        cover = f"{e['min_date']}→{e['max_date']}" if e["date_column"] else "—"
        rows = "—" if e["rows"] is None else f"{e['rows']:,}"
        lines.append(
            f"| `{e['dataset']}` | {'✅' if e['view_exists'] else '❌'} "
            f"| {rows} | {e['columns']} | {e['date_column'] or '—'} "
            f"| {cover} | {e['gold_partition_count']:,} | {e['partition_semantics']} "
            f"| `{e['latest_gold_partition']}` "
            f"| {ok} | {alive} | {', '.join(e['used_by_cards'])} |"
        )
    lines += [
        "",
        "> **`过冻结线` 与 `仍在更新` 是两件独立的事,刻意分成两列。**"
        "前者回答'v1 的 ≤ 冻结线窗口取不取得到数'(卡 0.2 的判据),"
        "后者回答'这张表今天还在长吗'(卡 1.3 网关要的)。"
        "实测有表**前者绿、后者红** —— 把它们合并成同一种绿正是这次补救要堵的洞。",
        "",
        "> 分区语义三类,混起来就会得出错误结论:`data_time` = 分区值是数据日期"
        "(最新分区 = 新鲜度,可截冻结线);`capture_time` = 分区值是**我们哪天抄的表**"
        "(这几张的快照全在冻结线之后,但数据本身覆盖到 2009 年);"
        "`entity_code` = 分区值是 ts_code/l3_code,与时间无关。",
    ]

    lines += ["", "## ⛔ 停更表(过了冻结线,但已经不长了)", ""]
    if not s["stalled_tables"]:
        lines.append("_本次体检没有测出停更表。_")
    else:
        lines += [
            f"湖侧基准 `{s['lake_frontier_date']}`({s['lake_frontier_definition']})",
            "",
            "| 数据集 | 节奏 | 新鲜度 | 新鲜度来源 | 滞后 | 容忍 | 为什么看着是绿的 | 哪张卡要用 |",
            "| --- | --- | --- | --- | ---: | ---: | --- | --- |",
        ]
        for t in s["stalled_tables"]:
            lines.append(
                f"| `{t['dataset']}` | {t['update_cadence']} | {t['freshness_date']} "
                f"| {t['freshness_source']} | **{t['lag_days']} 天** "
                f"| {t['stale_after_days']} 天 | {t['why_it_looks_green']} "
                f"| {', '.join(t['used_by_cards'])} |"
            )
    if s["unknown_freshness_tables"]:
        lines += [
            "",
            f"❔ **新鲜度判不了**的表:"
            f"{', '.join('`' + d + '`' for d in s['unknown_freshness_tables'])}"
            f" —— 区间表没有单一时间轴。基线里 `stalled=null`,"
            f"**不许**因为判不了就当它是活的。",
        ]

    lines += ["", "## 已知陷阱(本卡实测,卡 1.3/1.4 别再踩一遍)", ""]
    for h in baseline["known_hazards"]:
        lines += [
            f"### {h['id']} —— {h['title']}",
            "",
            f"- **实测证据**:{h['evidence']}",
            f"- **影响**:{h['impact']}",
            f"- **已做的规避**:{h['mitigation']}",
            "",
        ]
    lines += ["## 逐表备注(踩坑)", ""]
    for e in baseline["datasets"]:
        lines.append(f"### `{e['dataset']}` —— {e['role']}")
        lines.append("")
        lines.append(f"- **哪张卡要用**:{', '.join(e['used_by_cards'])}")
        lines.append(f"- **为什么非它不可**:{e['why_needed']}")
        lines.append(f"- 冻结线判据:`{e['freeze_line_check']}`")
        lines.append(
            f"- 新鲜度判据:`{e['stall_reason']}`(来源:{e['freshness_source']})"
        )
        if e["date_column_why"]:
            lines.append(f"- 为什么是这一列:{e['date_column_why']}")
        if e["audit_deltas"]:
            lines.append(
                f"- 审计对账(as_of={e['audit_as_of']}):{json.dumps(e['audit_deltas'], ensure_ascii=False)}"
            )
        if e["notes"]:
            lines.append(f"- 备注:{e['notes']}")
        lines.append("")
    lines += ["## 明确不进 v1 的表", ""]
    for x in baseline["excluded"]:
        lines.append(f"- **`{x['dataset']}`** —— {x['reason']} _(重议时机:{x['revisit']})_")
    lines += ["", "## catalog 里的派生视图(不是数据源,但好用)", ""]
    for x in baseline["derived_views"]:
        lines.append(f"- **`{x['view']}`**(由 {x['built_from']} 拼出)—— {x['use']}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    # umask 已在 import 期收紧(见文件头);这里再调一次是幂等的兜底。
    cfg.harden_umask()
    baseline = build()
    BASELINE_JSON.write_text(
        json.dumps(baseline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    BASELINE_MD.write_text(render_markdown(baseline), encoding="utf-8")

    s = baseline["summary"]
    print(f"wrote {BASELINE_JSON}")
    print(f"wrote {BASELINE_MD}")
    print(
        f"datasets={s['datasets']} view_exists_all={s['view_exists_all']} "
        f"freeze_line_ok_all={s['freeze_line_ok_all']} verdict={s['verdict']}"
    )
    print(
        f"frontier={s['lake_frontier_date']} freshness={s['freshness_verdict']} "
        f"stalled={s['stalled_count']} unknown={len(s['unknown_freshness_tables'])}"
    )
    for e in baseline["datasets"]:
        flag = {True: "OK ", False: "FAIL", None: "n/a "}[e["freeze_line_ok"]]
        alive = {True: "STALLED", False: "alive  ", None: "unknown"}[e["stalled"]]
        print(
            f"  {flag} {alive} {e['dataset']:20s} rows={str(e['rows']):>12s} "
            f"cols={str(e['columns']):>4s} {str(e['date_column'] or '-'):>12s} "
            f"max={str(e['max_date'] or '-'):>10s} lag={str(e['lag_days']):>5s} "
            f"parts={e['gold_partition_count']:>5d}"
        )
    if s["freeze_line_failures"]:
        print("\n冻结线未过:")
        for f in s["freeze_line_failures"]:
            print(f"  {f['dataset']}: {f['date_column']} max={f['max_date']}")
    if s["stalled_tables"]:
        print("\n⛔ 停更(过了冻结线但已经不长了 —— 卡 1.3 别拿它判新鲜度):")
        for t in s["stalled_tables"]:
            print(
                f"  {t['dataset']:20s} {t['freshness_source']:32s} "
                f"{t['freshness_date']} 落后 {t['lag_days']} 天"
                f"(容忍 {t['stale_after_days']} 天)"
            )
    return 0 if s["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
