"""卡 0.2 验收:湖只读基线。

四条判据(卡面原文):

① 清单内**全部表** `view_exists=True`
② **全部 `date_column` 非空的表** `max_date >= 20260731`(冻结线)
③ **无日期列的表**能正常查到行数
④ `snapshots/lake.py` 里**没有任何写路径**(源码级断言)

除了这四条,还顺手钉死几件后续卡会依赖的事实:
连接确实是只读的(引擎级)、上下文管理器确实会关连接、
`read_gold` 确实拦得住路径穿越、`query` 确实拦得住往文件系统写的语句。

判据从哪儿取数(卡 0.2 补救 D1:产物不许自证)
----------------------------------------------
**判据 ②、③ 一律现场复算,一个数都不从 `lake_baseline.json` 里读。**

补救前这里是个自证循环:``max_date = ENTRIES[ds]["max_date"]`` 然后断言
它 ``>= FREEZE_DATE_COMPACT`` —— 全程只在跟 JSON 自己的字段做字符串比较,
一次都没向 catalog 求过 ``max()``。**JSON 里写什么就过什么**,
体检产物给自己出成绩单。判据 ③ 同病:现场取了 `count_rows` 却只断言 ``> 0``,
从不与 `entry["rows"]` 对账;判据 ① 的 ``entry["columns"] == len(entry["column_names"])``
更是纯 JSON 内部自洽,现场一列都没查。

现在:`live` fixture 用只读连接把 22 张表全量重算一遍(实测 ~13s),
判据只认它;JSON 的对应字段改为**被对账的一方**。

湖是活的 —— 对账怎么才不是空话
-------------------------------
逐字相等在活湖上不是一个良定义的不变量:体检跑完之后 ETL 还会继续写,
`adj_factor` 在本次补救期间就从 4289 个分区涨到 4290。真拿 ``==`` 去卡,
测试第二天下午必红,然后就没人看了 —— 这不是严格,是把闸门废掉。
(实测:补救前的套件正是因此**已经红了 2 条**,
``test_gold_partitions_are_the_freshness_source[adj_factor]`` 与 ``[stock_basic]``。)

所以按"这个量会不会动"分三类对账:

* **冻结线以内的量 —— 逐字相等。** `max_date_upto_freeze`、
  `gold_partitions_upto_freeze`、`latest_gold_partition_upto_freeze`。
  历史是不动的,这些数不该变;变了就是真出事,必须红。
  **这是对账的主力**,也是杀掉自证循环的那把锁。
* **结构 —— 逐字相等。** 现场 `DESCRIBE` 的列清单、`date_column`、
  分区键、分区语义、`view_exists`。
* **会前进的量 —— 方向 + 预算。** `max_date` / `rows` / 分区数。
  JSON **不许比现场更新**(那意味着凭空写了个更漂亮的数),
  落后也不许超过 `BASELINE_DRIFT_BUDGET_DAYS` —— 超了就是产物过期,
  失败信息直接告诉你去重跑 builder。

跑法::

    cd $REPO && $GENEBENCH_ROOT/env/bin/python -m pytest ops/test_lake_baseline.py -v

注意:本测试**要连真实数据湖**(只读)。湖是活的,外部 ETL 会周期性读写 catalog,
`lake.open_catalog()` 自带 5 次重试;偶发的一次失败重跑即可,连续失败才是故障。
"""

from __future__ import annotations

import ast
import json
import sys
from datetime import date
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import genebench_config as cfg  # noqa: E402
from snapshots import lake, v1_tables  # noqa: E402

# builder 里的新鲜度/停更判定是**纯函数**,验收直接复用同一份实现 ——
# 两处各写一遍才是真危险(逻辑一漂移,测试就开始证明一个不存在的东西)。
# 复用的是**算法**,喂进去的数据仍然是现场重算的,不是 JSON 里的。
if str(cfg.OPS) not in sys.path:
    sys.path.insert(0, str(cfg.OPS))
import build_lake_baseline as builder  # noqa: E402

BASELINE_JSON = cfg.OPS / "lake_baseline.json"
BASELINE_MD = cfg.OPS / "lake_baseline.md"

#: 产物允许比现场落后多少天。超过就是**产物过期**,不是"差不多"。
#:
#: 14 天怎么来的:审计口径的表(`ann_date` 那批)本来就有 1-3 天的结构性滞后(H7),
#: 日频表遇上长假会有 9-10 天不动 —— 预算必须吃得下这些才不会天天误报;
#: 而真正的停更表实测落后 25-30 天,离 14 有十几天的安全间隔,不会来回翻。
BASELINE_DRIFT_BUDGET_DAYS = 14

#: 行数允许的相对偏差。日频大表一天长约 5000 行,14 天约 0.5%,3% 留了足够余量。
BASELINE_DRIFT_BUDGET_ROWS_PCT = 3.0

#: **按分区数**算漂移的表：`snapshot_date` 分区语义（每天全量抄一份）。
#: 对它们用"行数百分比"是错的标定 —— 日增就是一整份副本（`stock_basic`
#: 实测 5,892 行/天 ≈ 5.3%），3% 的预算保证 24 小时内必红，
#: 而红的原因是"湖在正常工作"。这类表的漂移量纲是**分区**，不是行。
#: 分区预算沿用 `BASELINE_DRIFT_BUDGET_PARTITIONS`，不另设。
def _drift_is_measured_in_partitions(dataset: str) -> bool:
    return lake.partition_semantics(dataset) == "capture_time"

#: 分区数允许比现场少多少个(只许现场更多 —— 分区只增不减)。
BASELINE_DRIFT_BUDGET_PARTITIONS = 15


# --------------------------------------------------------------------------
# 装载
# --------------------------------------------------------------------------


def _load_baseline() -> dict:
    try:
        return json.loads(BASELINE_JSON.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - 缺文件由 test_baseline_json_exists 报红
        return {}


BASELINE = _load_baseline()
ENTRIES = {e["dataset"]: e for e in BASELINE.get("datasets", [])}

#: ⚠️ `DATED` / `DATELESS` **从登记表推导,不从 baseline 推导**。
#:
#: 补救前它们是 ``[d for d, e in ENTRIES.items() if e.get("date_column")]`` ——
#: 那是自证循环的第二个入口:JSON 只要把某张表的 `date_column` 写成 null,
#: 这张表就悄悄从判据 ② 的参数化里消失,测试全绿,而没有任何一条用例会提到它。
#: 现在"哪些表该被查冻结线"由 `snapshots/v1_tables.py` 说了算,产物改不动它。
DATED = sorted(t.dataset for t in v1_tables.V1_TABLES if t.date_column)
DATELESS = sorted(t.dataset for t in v1_tables.V1_TABLES if not t.date_column)


@pytest.fixture(scope="module")
def conn():
    """整个模块共用一条只读连接 —— 别每个用例都开一条去捶湖。"""
    lake.raise_open_file_limit()
    with lake.catalog() as connection:
        yield connection


@pytest.fixture(scope="module")
def live(conn):
    """**现场**把 22 张表全量重算一遍 —— 本模块的唯一判据来源(D1)。

    一张表一次全扫,实测合计 ~13s(`balancesheet` 单表 ~2s)。
    module 作用域:只算一遍,给所有用例共用。

    Returns:
        ``{dataset: {columns, rows, min, max, max_upto, parts, semantics,
        part_key, latest_part, upto_parts, latest_upto}}``
    """
    lake.raise_open_file_limit()
    out: dict[str, dict] = {}
    for table in v1_tables.V1_TABLES:
        ds = table.dataset
        cols = lake.describe_view(ds, conn=conn)
        parts = lake.gold_partitions(ds)
        semantics = lake.partition_semantics(ds)
        latest_value = lake.split_partition(parts[-1])[1] if parts else None
        bound = (
            builder._freeze_bound_for(latest_value)
            if (semantics == "data_time" and latest_value)
            else None
        )
        upto = lake.partitions_upto(ds, bound) if bound is not None else []

        if table.date_column:
            rng = lake.column_range(
                ds, table.date_column, bound=lake.FREEZE_DATE_COMPACT, conn=conn
            )
        else:
            rng = {
                "rows": lake.count_rows(ds, conn=conn),
                "min": None,
                "max": None,
                "max_upto": None,
            }
        out[ds] = {
            "columns": cols,
            "rows": rng["rows"],
            "min": rng["min"],
            "max": rng["max"],
            "max_upto": rng["max_upto"],
            "parts": parts,
            "semantics": semantics,
            "part_key": lake.split_partition(parts[-1])[0] if parts else None,
            "latest_part": parts[-1] if parts else None,
            "upto_count": len(upto) if bound is not None else None,
            "latest_upto": upto[-1] if upto else None,
        }
    return out


@pytest.fixture(scope="module")
def live_freshness(live):
    """由现场值算出的新鲜度 / 湖侧基准 / 停更判定(D3)。

    喂给 `builder` 那组纯函数的**全部输入都来自 `live`**,
    baseline 只是后面被对账的一方。
    """
    cadences = {t.dataset: t.update_cadence for t in v1_tables.V1_TABLES}
    fresh: dict[str, str | None] = {}
    source: dict[str, str] = {}
    for table in v1_tables.V1_TABLES:
        ds = table.dataset
        f, src = builder.freshness_date(
            semantics=live[ds]["semantics"],
            date_column=table.date_column,
            live_max=live[ds]["max"],
            latest_capture=lake.gold_latest_capture(ds),
        )
        fresh[ds], source[ds] = f, src
    frontier = builder.lake_frontier(fresh, cadences)
    verdicts = {
        ds: builder.stall_verdict(
            cadence=cadences[ds], fresh=fresh[ds], frontier=frontier
        )
        for ds in fresh
    }
    return {
        "frontier": frontier,
        "freshness": fresh,
        "source": source,
        "verdicts": verdicts,
        "stalled": sorted(d for d, v in verdicts.items() if v["stalled"] is True),
        "unknown": sorted(d for d, v in verdicts.items() if v["stalled"] is None),
    }


def _days_short(max_date: str) -> int:
    """离冻结线还差多少天(用于 FAIL 时如实报差距)。"""
    y, m, d = int(max_date[:4]), int(max_date[4:6]), int(max_date[6:8])
    f = lake.FREEZE_DATE_COMPACT
    fy, fm, fd = int(f[:4]), int(f[4:6]), int(f[6:8])
    return (date(fy, fm, fd) - date(y, m, d)).days


def _regen() -> str:
    return (
        f"产物过期。重跑:cd {cfg.REPO} && {cfg.PYTHON} ops/build_lake_baseline.py"
    )


# ==========================================================================
# 0. 产物与清单本身
# ==========================================================================


def test_baseline_json_exists():
    """`ops/lake_baseline.json` 必须存在且能解析。"""
    assert BASELINE_JSON.exists(), (
        f"{BASELINE_JSON} 不存在。先跑:"
        f"cd {cfg.REPO} && {cfg.PYTHON} ops/build_lake_baseline.py"
    )
    assert BASELINE, f"{BASELINE_JSON} 解析为空"
    assert BASELINE.get("card") == "0.2"


def test_baseline_freeze_line_is_the_configured_one():
    """baseline 用的冻结线必须就是 `cfg.FREEZE_DATE`,不许各写各的。"""
    assert BASELINE["freeze_line"] == lake.FREEZE_DATE_COMPACT == "20260731"
    assert BASELINE["freeze_line_iso"] == cfg.FREEZE_DATE == "2026-07-31"


def test_baseline_covers_the_registry_exactly():
    """baseline 的表集合 == `snapshots/v1_tables.py` 的登记表集合。"""
    assert set(ENTRIES) == set(v1_tables.V1_TABLE_NAMES), (
        f"baseline 与清单不一致:\n"
        f"  清单有 baseline 没有:{sorted(set(v1_tables.V1_TABLE_NAMES) - set(ENTRIES))}\n"
        f"  baseline 有清单没有:{sorted(set(ENTRIES) - set(v1_tables.V1_TABLE_NAMES))}"
    )


def test_registry_covers_the_mandated_families():
    """卡面点名必须覆盖的表,一张都不能少。"""
    mandated = {
        # 行情量价
        "daily", "adj_factor", "daily_basic", "stk_limit", "suspend_d",
        # 日历
        "trade_cal",
        # 宇宙
        "index_weight", "stock_basic", "namechange", "stock_st",
        "st_history", "index_member_all",
        # 基本面三大报表及其 _vip
        "income", "income_vip", "balancesheet", "balancesheet_vip",
        "cashflow", "cashflow_vip",
        # 指数
        "index_daily",
    }
    missing = mandated - set(v1_tables.V1_TABLE_NAMES)
    assert not missing, f"v1 清单漏了卡面点名的表:{sorted(missing)}"


@pytest.mark.parametrize("dataset", v1_tables.V1_TABLE_NAMES)
def test_registry_entry_says_which_card_needs_it(dataset):
    """每张表都要说明"哪张卡要用它",而且要说清为什么。"""
    spec = v1_tables.spec(dataset)
    assert spec.used_by_cards, f"{dataset} 没登记 used_by_cards"
    assert all(c[0].isdigit() for c in spec.used_by_cards), (
        f"{dataset} 的 used_by_cards 不像卡号:{spec.used_by_cards}"
    )
    assert len(spec.why) >= 20, f"{dataset} 的 why 太敷衍:{spec.why!r}"
    assert len(spec.role) >= 4, f"{dataset} 没写 role"
    assert ENTRIES[dataset]["used_by_cards"] == list(spec.used_by_cards)


def test_registry_has_no_duplicates():
    names = list(v1_tables.V1_TABLE_NAMES)
    assert len(names) == len(set(names)), "v1 清单里有重复登记"


@pytest.mark.parametrize("dataset", v1_tables.V1_TABLE_NAMES)
def test_registry_declares_a_cadence_and_a_reason_for_its_date_column(dataset):
    """`date_column` 与 `update_cadence` 必须在登记表里、而且写了理由(D3/D5)。"""
    spec = v1_tables.spec(dataset)
    assert spec.update_cadence in v1_tables.UPDATE_CADENCES, (
        f"{dataset} 的 update_cadence={spec.update_cadence!r} 不合法"
    )
    assert len(spec.date_column_why) >= 8, (
        f"{dataset} 没写清 date_column={spec.date_column!r} 是怎么选的 —— "
        f"'有几个日期列'和'哪个是 PIT 可见时间轴'是两个问题,必须留证。"
    )
    assert ENTRIES[dataset]["update_cadence"] == spec.update_cadence
    assert ENTRIES[dataset]["date_column"] == spec.date_column


# ==========================================================================
# ① 清单内全部表 view_exists=True(**列数与现场 DESCRIBE 对账**)
# ==========================================================================


@pytest.mark.parametrize("dataset", v1_tables.V1_TABLE_NAMES)
def test_view_exists(dataset, conn, live):
    """判据 ①:catalog 里必须有这张视图,且 baseline 的列清单 == 现场 DESCRIBE。

    补救前这里只断言 ``entry["columns"] == len(entry["column_names"])`` ——
    那是 JSON 跟自己比,现场一列都没查过(D1)。
    """
    entry = ENTRIES[dataset]
    assert entry["view_exists"] is True, f"baseline 记录 {dataset} 视图不存在"
    assert lake.view_exists(dataset, conn=conn) is True, (
        f"现场查:catalog 里没有视图 {dataset}"
    )
    assert entry["column_names"], f"{dataset} 的列清单是空的"

    live_cols = live[dataset]["columns"]
    assert entry["column_names"] == live_cols, (
        f"{dataset}:baseline 的列清单与现场 DESCRIBE 不一致。\n"
        f"  只在 baseline 里:{sorted(set(entry['column_names']) - set(live_cols))}\n"
        f"  只在现场:      {sorted(set(live_cols) - set(entry['column_names']))}\n"
        f"{_regen()}"
    )
    assert entry["columns"] == len(live_cols), (
        f"{dataset}:baseline 记 {entry['columns']} 列,现场 DESCRIBE {len(live_cols)} 列。"
        f"{_regen()}"
    )


# ==========================================================================
# ② 全部 date_column 非空的表 max_date >= 20260731 —— **现场判**
# ==========================================================================


@pytest.mark.parametrize("dataset", DATED)
def test_freeze_line(dataset, live):
    """判据 ②(**本卡的验收判据**):有日期列的表必须覆盖到冻结线。

    ⚠️ 判据取的是 `live[ds]["max"]`(现场 ``max(date_column)``),
    **不是** `ENTRIES[ds]["max_date"]`。JSON 在这条用例里只是被对账的一方。
    """
    spec = v1_tables.spec(dataset)
    live_max = live[dataset]["max"]
    assert live_max, (
        f"{dataset} 登记了 date_column={spec.date_column} 却现场查不到 max"
    )
    assert live_max >= lake.FREEZE_DATE_COMPACT, (
        f"{dataset} 未过冻结线:现场 max({spec.date_column})={live_max},"
        f"距 {lake.FREEZE_DATE_COMPACT} 还差 {_days_short(str(live_max))} 天"
    )
    assert ENTRIES[dataset]["freeze_line_ok"] is True, (
        f"{dataset} 现场过线,但 baseline 里 "
        f"freeze_line_ok={ENTRIES[dataset]['freeze_line_ok']}"
    )


def test_no_dated_table_is_stale(live):
    """把所有未过线的表**一次列全**,别让 -k 只跑到第一张就以为只有一张。"""
    stale = [
        (d, v1_tables.spec(d).date_column, live[d]["max"])
        for d in DATED
        if not (live[d]["max"] and live[d]["max"] >= lake.FREEZE_DATE_COMPACT)
    ]
    assert not stale, f"现场复算:未过冻结线 {lake.FREEZE_DATE_COMPACT} 的表:{stale}"
    assert BASELINE["summary"]["freeze_line_ok_all"] is True
    assert BASELINE["summary"]["verdict"] == "PASS"


@pytest.mark.parametrize("dataset", DATED)
def test_baseline_dates_reconcile_with_live_recompute(dataset, live):
    """**产物不许自证**(D1 的正面锁):JSON 的日期字段要与现场对得上。

    分两档:

    * `max_date_upto_freeze` —— **逐字相等**。冻结线以内是历史,不该动。
      这是对账的主力:它一相等,就说明 JSON 里的日期确实来自这张表,
      而不是抄来的、猜的、或者上一版留下的。
    * `max_date`(无上界)—— 会随 ETL 前进,所以只卡**方向 + 预算**:
      JSON 不许比现场还新,落后也不许超过 `BASELINE_DRIFT_BUDGET_DAYS`。
    """
    entry = ENTRIES[dataset]
    spec = v1_tables.spec(dataset)
    got, want = entry["max_date_upto_freeze"], live[dataset]["max_upto"]
    assert got == want, (
        f"{dataset}:baseline 记 max({spec.date_column}) 截到冻结线 = {got},"
        f"现场重算 = {want}。冻结线以内是历史,这个数不该变 —— "
        f"要么 baseline 的数不是从这张表来的,要么湖侧改了历史。{_regen()}"
    )

    json_max, live_max = entry["max_date"], live[dataset]["max"]
    assert json_max <= live_max, (
        f"{dataset}:baseline 的 max_date={json_max} **比现场 {live_max} 还新**。"
        f"湖只会往前走,产物比现实更新只有一种解释:这个数不是量出来的。"
    )
    drift = builder.days_between(json_max, live_max)
    assert drift <= BASELINE_DRIFT_BUDGET_DAYS, (
        f"{dataset}:baseline 的 max_date={json_max} 已落后现场 {live_max} 共 "
        f"{drift} 天(预算 {BASELINE_DRIFT_BUDGET_DAYS} 天)。{_regen()}"
    )


@pytest.mark.parametrize("dataset", v1_tables.V1_TABLE_NAMES)
def test_baseline_rows_reconcile_with_live_recompute(dataset, live):
    """行数也要与现场对账(D2:`rows` 现在是现场值,不再抄审计)。"""
    entry = ENTRIES[dataset]
    live_rows = live[dataset]["rows"]
    assert isinstance(entry["rows"], int) and entry["rows"] > 0
    assert live_rows > 0, f"{dataset} 现场 count(*) 拿到 {live_rows}"
    drift_pct = abs(live_rows - entry["rows"]) / live_rows * 100
    if _drift_is_measured_in_partitions(dataset):
        # capture_time 表按分区算漂移（见 _drift_is_measured_in_partitions 的说明）。
        # 这里不是跳过检查 —— 分区预算那条测试照样管着它。
        pytest.skip(
            f"{dataset} 是 capture_time 表，漂移按分区数算，不按行数百分比"
        )
    assert drift_pct <= BASELINE_DRIFT_BUDGET_ROWS_PCT, (
        f"{dataset}:baseline 记 {entry['rows']:,} 行,现场 {live_rows:,} 行,"
        f"偏差 {drift_pct:.2f}%(预算 {BASELINE_DRIFT_BUDGET_ROWS_PCT}%)。{_regen()}"
    )
    assert entry["values_source"].startswith("live_recompute"), (
        f"{dataset} 的 values_source={entry['values_source']!r} —— "
        f"D2 要求 rows/columns/日期一律以现场重算为准"
    )


@pytest.mark.parametrize("dataset", v1_tables.V1_TABLE_NAMES)
def test_audit_values_are_demoted_to_evidence_not_verdict(dataset):
    """审计值必须以 `audit_*` 前缀保留,并标注 `audit_as_of`(D2)。

    保留是为了可追溯(能回答"当初为什么写成那个数"),
    改名是为了**不可能再被误当判据** —— 一个叫 `max_date` 的字段,
    下一个人一定会拿它去判新鲜度。
    """
    entry = ENTRIES[dataset]
    for key in (
        "audit_rows", "audit_columns", "audit_date_column",
        "audit_min_date", "audit_max_date", "audit_as_of",
    ):
        assert key in entry, f"{dataset} 缺 {key}"
    assert entry["audit_as_of"] == BASELINE["sources"]["coverage_audit_as_of"]
    assert entry["audit_as_of"], f"{dataset} 的 audit_as_of 是空的"
    assert "audit_agrees_with_live" in entry
    if not entry["audit_agrees_with_live"]:
        assert entry["audit_deltas"], f"{dataset} 说与审计不一致却没列出差异"


def test_coverage_audit_lag_is_documented_as_structural():
    """审计天然滞后这件事必须写在产物里(D2),否则下一个人还会照抄它的数。"""
    cadence = BASELINE["sources"]["coverage_audit_cadence"]
    assert "Mon..Fri" in cadence, f"没写清 timer 排班:{cadence}"
    assert "15:2" in cadence or "23:20" in cadence, f"没写清触发时刻:{cadence}"
    assert "周末" in cadence and "结构性" in cadence, (
        f"没说清周末滞后是结构性的而非偶发:{cadence}"
    )
    assert BASELINE["sources"]["coverage_audit_role"].startswith("旁证")
    hazards = {h["id"]: h for h in BASELINE["known_hazards"]}
    assert "H7" in hazards, "审计滞后没被登记成已知陷阱"


# ==========================================================================
# ③ 无日期列的表能正常查到行数(**并与 baseline 对账**)
# ==========================================================================


def test_there_are_dateless_tables():
    """清单里确实存在无日期列的表 —— 否则判据 ③ 是空跑。"""
    assert DATELESS, "清单里一张无日期列的表都没有,判据 ③ 形同虚设"


@pytest.mark.parametrize("dataset", DATELESS)
def test_dateless_table_row_count(dataset, conn, live):
    """判据 ③:无日期列的表(区间表/多快照表/元数据表)照样能查到行数。

    补救前这里现场取了 `count_rows` 却只断言 ``> 0``,与 `entry["rows"]` 从不对账
    —— 于是 JSON 里的行数写成什么都过。现在两边必须对得上(D1)。
    """
    entry = ENTRIES[dataset]
    assert entry["date_column"] is None
    assert entry["min_date"] is None and entry["max_date"] is None
    assert entry["freeze_line_ok"] is None, (
        f"{dataset} 没有日期列,freeze_line_ok 应该是 null(不适用),"
        f"不该粉饰成 {entry['freeze_line_ok']}"
    )
    assert "n/a" in entry["freeze_line_check"]

    live_rows = lake.count_rows(dataset, conn=conn)
    assert live_rows > 0, f"{dataset} 现场 count(*) 拿到 {live_rows}"
    assert live_rows == live[dataset]["rows"]
    drift_pct = abs(live_rows - entry["rows"]) / live_rows * 100
    if _drift_is_measured_in_partitions(dataset):
        # capture_time 表按分区算漂移（见 _drift_is_measured_in_partitions 的说明）。
        # 这里不是跳过检查 —— 分区预算那条测试照样管着它。
        pytest.skip(
            f"{dataset} 是 capture_time 表，漂移按分区数算，不按行数百分比"
        )
    assert drift_pct <= BASELINE_DRIFT_BUDGET_ROWS_PCT, (
        f"{dataset}:baseline 记 {entry['rows']:,} 行,现场 {live_rows:,} 行。{_regen()}"
    )


@pytest.mark.parametrize("dataset", v1_tables.V1_TABLE_NAMES)
def test_gold_partitions_are_the_freshness_source(dataset, live):
    """gold 分区目录必须列得出来 —— 它才是新鲜度的正确来源。

    分区数与最新分区会随 ETL 前进(补救前这里用 ``==`` 卡,
    `adj_factor` 一多出一个分区就红),所以:**冻结线以内逐字相等,
    冻结线以外只卡方向 + 预算**。
    """
    entry = ENTRIES[dataset]
    parts = live[dataset]["parts"]
    assert parts, f"{dataset} 在 {cfg.GOLD} 下没有分区目录"

    # 结构:逐字相等
    assert live[dataset]["part_key"] == entry["gold_partition_key"]
    assert entry["partition_semantics"] in lake.PARTITION_SEMANTICS
    assert entry["partition_semantics"] == live[dataset]["semantics"]

    # 会前进的量:只许现场更多,且不许落后太多
    assert len(parts) >= entry["gold_partition_count"], (
        f"{dataset} 现场只有 {len(parts)} 个分区,少于 baseline 记的 "
        f"{entry['gold_partition_count']} 个 —— 分区**只增不减**,少了是真出事。"
    )
    grew = len(parts) - entry["gold_partition_count"]
    assert grew <= BASELINE_DRIFT_BUDGET_PARTITIONS, (
        f"{dataset} 自 baseline 生成以来多了 {grew} 个分区"
        f"(预算 {BASELINE_DRIFT_BUDGET_PARTITIONS})。{_regen()}"
    )
    assert parts[-1] >= entry["latest_gold_partition"], (
        f"{dataset} 现场最新分区 {parts[-1]} 早于 baseline 记的 "
        f"{entry['latest_gold_partition']}"
    )

    if entry["partition_semantics"] == "data_time":
        # 冻结窗口内的分区是历史,逐字相等
        assert entry["gold_partitions_upto_freeze"] == live[dataset]["upto_count"], (
            f"{dataset} 冻结窗口内的分区数变了:baseline "
            f"{entry['gold_partitions_upto_freeze']} vs 现场 "
            f"{live[dataset]['upto_count']}。历史不该动。{_regen()}"
        )
        assert entry["latest_gold_partition_upto_freeze"] == live[dataset]["latest_upto"]
        assert entry["gold_partitions_upto_freeze"] > 0, (
            f"{dataset} 在冻结线 {cfg.FREEZE_DATE} 之前没有任何分区"
        )
        assert entry["gold_latest_partition_value"] is not None
    else:
        # 非数据时间分区:**不许**假装能截冻结线
        assert entry["gold_partitions_upto_freeze"] is None
        assert entry["gold_latest_partition_value"] is None


def test_capture_time_tables_are_flagged_not_papered_over(conn):
    """`snapshot_date` 分区的表:快照全在冻结线之后,这件事必须被明确标注。

    `stock_basic` / `trade_cal` / `index_basic` 的 gold 分区是**抓取日期**,
    最早一个快照是 2026-08-05,全部晚于冻结线 2026-07-31。若把它当数据日期去截线,
    会得出"这些表在 v1 窗口内没有数据"的错误结论 —— 而 `trade_cal` 实际覆盖
    20090101→20261231。基线必须把这一点写进 notes,卡 1.3 的网关要按字段回溯实现。
    """
    capture = BASELINE["summary"]["capture_time_tables"]
    assert set(capture) >= {"stock_basic", "trade_cal"}, (
        f"capture_time 表识别不全:{capture}"
    )
    for ds in capture:
        entry = ENTRIES[ds]
        earliest = lake.gold_partitions(ds)[0]
        assert lake.split_partition(earliest)[1] > cfg.FREEZE_DATE, (
            f"{ds} 的最早快照 {earliest} 竟然在冻结线之前 —— 这条结论要重写"
        )
        assert "抓取时间" in entry["notes"], f"{ds} 的 notes 没标注抓取时间语义"
        assert lake.gold_latest_capture(ds) is not None
        assert lake.gold_latest_value(ds) is None
        assert lake.partitions_upto(ds) == []
    # trade_cal 的数据本身远远越过冻结线(且含未来日历),证明"没有快照" ≠ "没有数据"
    row = conn.execute(
        "SELECT min(cal_date), max(cal_date) FROM trade_cal"
    ).fetchone()
    assert str(row[0]) <= "20090105" and str(row[1]) >= "20261231", (
        f"trade_cal 覆盖范围变了:{row}"
    )


# ==========================================================================
# D3:停更表 —— "过了冻结线" ≠ "这张表还活着"
# ==========================================================================


def test_summary_has_a_stalled_tables_field():
    """`summary` 必须有 `stalled_tables` 字段(补救前**根本不存在**)。"""
    s = BASELINE["summary"]
    for key in (
        "stalled_tables", "stalled_count", "unknown_freshness_tables",
        "lake_frontier_date", "freshness_verdict", "stalled_tables_note",
    ):
        assert key in s, f"summary 缺 {key} —— 停更表会被渲染成和活表同一种绿"
    assert s["stalled_count"] == len(s["stalled_tables"])
    assert s["freshness_verdict"] in ("ALL_FRESH", "STALLED_TABLES_PRESENT")


def test_stalled_tables_match_live_recompute(live_freshness):
    """停更清单必须能被**现场**复算出来,不是 JSON 里手写的一串名字。"""
    s = BASELINE["summary"]
    got = sorted(t["dataset"] for t in s["stalled_tables"])
    want = live_freshness["stalled"]
    assert got == want, (
        f"baseline 的停更清单与现场复算不一致:\n"
        f"  baseline: {got}\n  现场:     {want}\n"
        f"湖侧基准 {live_freshness['frontier']}。"
        f"如果是某张表**恢复更新**了,那是好事 —— 重跑 builder,"
        f"并回头修 v1_tables.py 里那条 ⛔ 备注与卡 1.3 的假设。{_regen()}"
    )
    assert sorted(s["unknown_freshness_tables"]) == live_freshness["unknown"]
    # D-02：湖是活的，前沿日期**每天都会前进**，等值断言不是时间不变量 ——
    # 2026-09-02 实测：baseline 记 20260901、现场 20260902，停更清单其实完全一致。
    # 正确形式是单调不变量：现场前沿不得**倒退**到 baseline 之前（倒退才说明湖被回删/改写）。
    assert live_freshness["frontier"] >= s["lake_frontier_date"], (
        f"现场湖前沿 {live_freshness['frontier']} 早于 baseline 的 {s['lake_frontier_date']} —— "
        f"湖倒退了？那不是抖动，是回删/改写历史。{_regen()}"
    )


def test_the_measured_stalled_tables_are_still_these_eight(live_freshness):
    """把本卡实测的 8 张停更表钉死 —— 这条同时是**金丝雀**。

    卡 1.3 的网关会照这份结论决定"哪些表不能拿来判新鲜度"。
    哪天某张表恢复更新(或又多停一张),这条会红,提醒回来改结论,
    而不是让一份过期的判断继续指导下游。
    """
    expected = {
        "limit_list_d",     # gold 分区硬停在 trade_date=2026-08-05
        "income",           # max(ann_date)=20260804,孪生 _vip 已到 08-29
        "balancesheet",     # 同上
        "cashflow",         # 同上
        "namechange",       # max(ann_date)=20260806
        "dividend",         # max(ann_date)=20260801,滞后最久
        "trade_cal",        # 只有 1 个 snapshot_date=2026-08-05,从未刷新
        "index_basic",      # 只有 2 个快照,最新 2026-08-06
    }
    got = set(live_freshness["stalled"])
    assert got == expected, (
        f"停更表集合变了:多出 {sorted(got - expected)},恢复 {sorted(expected - got)}。"
        f"这不一定是坏事,但 v1_tables.py 的 ⛔ 备注、baseline 的 H6、"
        f"以及卡 1.3 的新鲜度假设都要跟着改。"
    )


def test_freeze_line_green_does_not_imply_alive(live_freshness):
    """本次补救的**核心命题**:确实存在"过了冻结线但已经停更"的表。

    这条要是空跑(一张这样的表都没有),说明两维已经合流,
    `stalled_tables` 也就失去意义了 —— 那时该回来重新想这套判据。
    """
    both = [
        d
        for d in live_freshness["stalled"]
        if ENTRIES[d]["freeze_line_ok"] is True
    ]
    assert both, (
        "没有任何一张表'过冻结线且停更' —— D3 的前提不成立了,回来重审这套判据。"
    )
    # 实测这类表有 6 张(另外 2 张 trade_cal/index_basic 是 capture 语义)
    assert len(both) >= 5, f"只剩 {both} 一类,结论需要复核"
    for ds in both:
        assert ENTRIES[ds]["stalled"] is True
        assert ENTRIES[ds]["freeze_line_ok"] is True, (
            f"{ds} 应当是'绿在冻结线、红在新鲜度'的样本"
        )


@pytest.mark.parametrize(
    "dataset",
    ["limit_list_d", "income", "balancesheet", "cashflow",
     "namechange", "dividend", "trade_cal", "index_basic"],
)
def test_every_stalled_table_is_marked_in_its_notes(dataset):
    """每张停更表的 `notes` 必须**明确写着它停更了**,不能只写"覆盖范围"。

    补救前 `limit_list_d` 的 notes 只有一句"只覆盖 20200102 起" ——
    说的是**起点**,只字未提它**终点也停了**。读的人会以为它一直更新到今天。
    """
    entry = ENTRIES[dataset]
    notes = entry["notes"]
    assert "停更" in notes, f"{dataset} 的 notes 没写它停更了:{notes[:160]}"
    assert "⛔" in notes, f"{dataset} 的 notes 缺显式停更标记:{notes[:160]}"
    assert entry["stalled"] is True
    assert isinstance(entry["lag_days"], int) and entry["lag_days"] > 0
    assert entry["stall_reason"], f"{dataset} 没写停更判据"
    # 登记表(而不只是自动生成的那句)也要留痕,免得重跑 builder 就丢了
    assert "⛔" in v1_tables.spec(dataset).notes, (
        f"{dataset} 的停更结论只写在生成的 notes 里,"
        f"snapshots/v1_tables.py 的登记备注也要写 —— 那才是人会去读的地方"
    )


def test_limit_list_d_stall_is_quantified_against_daily(live):
    """`limit_list_d` 的停更要有**可核对的量**:它比 daily 少了多少个交易日分区。"""
    ll = [p for p in live["limit_list_d"]["parts"]]
    dd = [p for p in live["daily"]["parts"]]
    assert ll[-1] == "trade_date=2026-08-05", (
        f"limit_list_d 的最新分区变了:{ll[-1]} —— 停更结论要重写"
    )
    behind = [p for p in dd if p > ll[-1]]
    assert len(behind) >= 17, (
        f"daily 在 limit_list_d 最新分区之后只有 {len(behind)} 个分区,"
        f"实测应 >= 17"
    )
    assert "17" in ENTRIES["limit_list_d"]["notes"] or "17" in v1_tables.spec(
        "limit_list_d"
    ).notes, "limit_list_d 的备注没写清它落后 daily 多少个交易日分区"


def test_vip_twins_diverge_and_that_is_recorded(live):
    """三大报表与其 `_vip` 孪生表的分叉是**可测的**,不是印象。"""
    for base, vip in (
        ("income", "income_vip"),
        ("balancesheet", "balancesheet_vip"),
        ("cashflow", "cashflow_vip"),
    ):
        gap = builder.days_between(live[base]["max"], live[vip]["max"])
        assert gap >= 20, (
            f"{base} 与 {vip} 的 max(ann_date) 只差 {gap} 天"
            f"({live[base]['max']} vs {live[vip]['max']}) —— 分叉结论要复核"
        )
        assert "停更" in ENTRIES[base]["notes"]
        assert ENTRIES[vip]["stalled"] is False, f"{vip} 不该被判成停更"


def test_index_weight_is_not_mistaken_for_stalled(live_freshness):
    """反例:`index_weight` 滞后 30 天但**不是停更** —— 它是月末节奏。

    这条守的是判据的另一头:容忍度要是拍脑袋定成一个数,
    月末快照表会被误报,然后所有人开始无视停更清单。
    """
    assert "index_weight" not in live_freshness["stalled"]
    v = live_freshness["verdicts"]["index_weight"]
    assert v["stalled"] is False
    assert v["lag_days"] > v1_tables.CADENCE_TOLERANCE_DAYS["trading_day"], (
        f"index_weight 只滞后 {v['lag_days']} 天,还没超过日频容忍度 —— "
        f"这条反例不再有说服力,换一张表或改判据"
    )
    assert v1_tables.spec("index_weight").update_cadence == "month_end"


def test_markdown_separates_freeze_line_from_liveness():
    """`lake_baseline.md` 必须把"过冻结线"和"仍在更新"渲染成**两列**(D3)。"""
    assert BASELINE_MD.exists(), f"{BASELINE_MD} 不存在。{_regen()}"
    md = BASELINE_MD.read_text(encoding="utf-8")
    assert "| 过冻结线 | 仍在更新 |" in md, (
        "md 的逐表清单没有把两维分开渲染 —— 停更表又会被画成同一种绿"
    )
    assert "## ⛔ 停更表" in md, "md 缺停更表小节"
    for ds in ("limit_list_d", "dividend", "trade_cal"):
        assert f"| `{ds}` |" in md
    assert "停更" in md and "两件独立的事" in md


def test_markdown_renders_live_values_not_audit_values():
    """md 渲染的必须是现场值(D2)。拿几个审计与现场已知不一致的数当探针。"""
    md = BASELINE_MD.read_text(encoding="utf-8")
    for ds in ("income_vip", "balancesheet_vip", "cashflow_vip", "stock_st", "st_history"):
        entry = ENTRIES[ds]
        assert f"{entry['rows']:,}" in md, (
            f"md 里找不到 {ds} 的现场行数 {entry['rows']:,}"
        )
        if entry["audit_rows"] and entry["audit_rows"] != entry["rows"]:
            assert f"| {entry['audit_rows']:,} |" not in md, (
                f"md 的表格里出现了 {ds} 的**审计**行数 {entry['audit_rows']:,},"
                f"应当渲染现场值 {entry['rows']:,}"
            )


# ==========================================================================
# D5:日期列与分区语义不许自相矛盾
# ==========================================================================


@pytest.mark.parametrize("dataset", v1_tables.V1_TABLE_NAMES)
def test_date_column_and_partition_semantics_do_not_contradict(dataset, live):
    """同一张表不许既"有时间语义的分区"又"没有日期列"(D5)。

    补救前 `st_history` 正是这样:审计给它 `date_column=None`,
    而它的分区键是 `published_month` → `partition_semantics="data_time"`。
    一张表同时被判成"分区值是数据日期"和"表里没有日期",两个结论互斥。
    """
    spec = v1_tables.spec(dataset)
    semantics = live[dataset]["semantics"]
    if semantics == "data_time":
        assert spec.date_column is not None, (
            f"{dataset} 的分区语义是 data_time(分区值 = 数据日期),"
            f"却登记成没有日期列 —— 这两个结论互斥,必须选一个。"
        )
    if spec.date_column is not None:
        assert spec.date_column in live[dataset]["columns"], (
            f"{dataset} 登记 date_column={spec.date_column!r},现场视图里没有这一列"
        )
        assert live[dataset]["min"] and live[dataset]["max"], (
            f"{dataset} 的 date_column={spec.date_column!r} 现场查不出区间"
        )
    else:
        assert semantics in ("capture_time", "entity_code"), (
            f"{dataset} 没有日期列,分区语义却是 {semantics}"
        )


def test_st_history_date_column_is_resolved_from_the_table_not_the_audit(live, conn):
    """`st_history` 的 D5 定点回归:审计说没有日期列,表里其实有两个。"""
    entry = ENTRIES["st_history"]
    assert entry["audit_date_column"] is None, (
        "审计已经给出 date_column 了?那这条回归可以简化了"
    )
    assert entry["date_column"] == "pub_date"
    assert entry["date_column_source"] == "snapshots/v1_tables.py"
    assert entry["partition_semantics"] == "data_time"
    assert entry["freeze_line_ok"] is True, (
        "st_history 现在是有日期列的表,必须真正接受冻结线判据"
    )

    # 现场证明两列都在、都全非空,且 imp_date 会晚于 pub_date(所以 PIT 取 pub_date)
    cols = live["st_history"]["columns"]
    assert {"pub_date", "imp_date"} <= set(cols)
    row = conn.execute(
        "SELECT count(*), count(pub_date), count(imp_date), "
        "max(pub_date), max(imp_date) FROM st_history"
    ).fetchone()
    total, n_pub, n_imp, max_pub, max_imp = row
    assert n_pub == total and n_imp == total, (
        f"st_history 的日期列不再是全表非空:{n_pub}/{n_imp} of {total}"
    )
    assert str(max_imp) >= str(max_pub), (
        f"imp_date({max_imp}) 不再晚于等于 pub_date({max_pub}) —— "
        f"选 pub_date 的理由要重写"
    )
    assert "pub_date" in v1_tables.spec("st_history").date_column_why


# ==========================================================================
# ④ lake.py 里没有任何写路径(源码级断言)
# ==========================================================================

LAKE_PATH = Path(lake.__file__)
LAKE_SOURCE = LAKE_PATH.read_text(encoding="utf-8")
LAKE_TREE = ast.parse(LAKE_SOURCE)


def _docstring_ids(tree: ast.AST) -> set[int]:
    """收集"是 docstring"的字符串节点 id —— 文档里可以谈写操作,代码里不行。"""
    out: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            body = getattr(node, "body", None)
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                out.add(id(body[0].value))
    return out


DOCSTRING_IDS = _docstring_ids(LAKE_TREE)


def _code_strings() -> list[str]:
    """lake.py 里**非 docstring** 的全部字符串字面量(含 f-string 的常量段)。"""
    return [
        node.value
        for node in ast.walk(LAKE_TREE)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in DOCSTRING_IDS
    ]


def _dotted(node: ast.AST) -> str:
    """把 `a.b.c` 形态的调用目标还原成点号串;还原不出来返回空串。"""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    elif parts:
        parts.append("<expr>")
    return ".".join(reversed(parts))


def test_lake_source_never_opens_a_writable_connection():
    """④-a:源码里不许出现非只读的连接写法。"""
    squeezed = "".join(LAKE_SOURCE.split())
    for bad in ("read_only=False", "readonly=False", "access_mode='automatic'"):
        assert bad not in squeezed, f"{LAKE_PATH} 里出现了 {bad}"
    assert "read_only=True" in squeezed, f"{LAKE_PATH} 里没有只读连接"


#: **具名例外**（N-42，2026-09-04）：`_parquet_conn` 开的是 `:memory:` 连接，
#: 用来跑纯 `read_parquet` 语句 —— 只读、不碰 catalog、没有底层文件。
#: duckdb **拒绝**以只读模式开内存库，所以「每个 connect 都带 read_only=True」
#: 对它无法满足；而这条基线守的是**对湖的连接**，它与湖无关。
#: 理由与本文件给对抗审计员写的那条（`CONNECT_SCAN_EXEMPT_TREES` 注释）一致。
#:
#: 例外**只认这一个函数名**，不是放宽成通配 —— 别处再写 `:memory:` 照样红。
MEMORY_CONN_EXEMPT = frozenset({"_parquet_conn"})


def _inside_exempt_function(call: ast.AST) -> bool:
    for fn in ast.walk(LAKE_TREE):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and \
                fn.name in MEMORY_CONN_EXEMPT:
            if any(n is call for n in ast.walk(fn)):
                return True
    return False


def test_memory_conn_exemption_is_narrow():
    """例外只覆盖那一个函数，且它开的确实是 `:memory:` —— 不是随便什么连接。"""
    for fn in ast.walk(LAKE_TREE):
        if not (isinstance(fn, ast.FunctionDef) and fn.name in MEMORY_CONN_EXEMPT):
            continue
        calls = [n for n in ast.walk(fn)
                 if isinstance(n, ast.Call) and _dotted(n.func).endswith("connect")]
        assert len(calls) == 1, f"{fn.name} 里有 {len(calls)} 个 connect，例外只许一个"
        arg = calls[0].args[0] if calls[0].args else None
        assert isinstance(arg, ast.Constant) and arg.value == ":memory:", \
            f"{fn.name} 的例外只对 :memory: 成立，实际 {getattr(arg, 'value', None)!r}"


def test_lake_source_every_connect_call_is_read_only():
    """④-b:每一处 connect 调用都必须显式带只读关键字(不许裸调用)。"""
    connects = [
        node
        for node in ast.walk(LAKE_TREE)
        if isinstance(node, ast.Call) and _dotted(node.func).endswith("connect")
    ]
    assert connects, f"{LAKE_PATH} 里一个 connect 调用都没有?"
    for call in connects:
        if _inside_exempt_function(call):
            continue
        kwargs = {kw.arg: kw.value for kw in call.keywords}
        assert "read_only" in kwargs, (
            f"第 {call.lineno} 行的 connect 是**裸调用**,没写只读关键字"
        )
        value = kwargs["read_only"]
        assert isinstance(value, ast.Constant) and value.value is True, (
            f"第 {call.lineno} 行的 connect 只读参数不是字面量 True"
        )


#: 会往文件系统 / 数据库落字节的调用名。
FORBIDDEN_CALLS = frozenset(
    {
        "open", "write", "writelines", "write_text", "write_bytes",
        "mkdir", "makedirs", "rmdir", "removedirs", "remove", "unlink",
        "rmtree", "rename", "renames", "replace", "touch", "truncate",
        "chmod", "chown", "symlink", "link", "mkfifo", "mknod",
        "to_parquet", "to_csv", "to_json", "to_sql", "to_feather", "to_pickle",
        "NamedTemporaryFile", "mkstemp", "mkdtemp",
    }
)


def test_lake_source_calls_no_write_api():
    """④-c:源码里不许调用任何写文件 / 建目录的 API。"""
    hits = []
    for node in ast.walk(LAKE_TREE):
        if not isinstance(node, ast.Call):
            continue
        dotted = _dotted(node.func)
        tail = dotted.rsplit(".", 1)[-1] if dotted else ""
        if tail in FORBIDDEN_CALLS:
            hits.append(f"第 {node.lineno} 行:{dotted}()")
    assert not hits, f"{LAKE_PATH} 里出现写路径调用:{hits}"


#: 写语义的 SQL 动词。用**整词**匹配,避免 `update_flag` 这类字段名误伤。
WRITE_SQL_VERBS = (
    "insert", "update", "delete", "drop", "alter", "create", "attach", "detach",
    "copy", "truncate", "merge", "export", "import", "vacuum", "checkpoint",
    "commit", "rollback", "grant", "revoke", "upsert", "overwrite", "persist",
)


def test_lake_source_has_no_write_sql_literals():
    """④-d:非 docstring 的字符串字面量里不许出现写语义 SQL 动词。

    docstring 被豁免 —— 文档必须能解释"为什么不写湖",
    但**能被执行到的字符串**里一个写动词都不许有。
    """
    import re

    hits = []
    for text in _code_strings():
        for verb in WRITE_SQL_VERBS:
            if re.search(rf"(?<![A-Za-z_]){verb}(?![A-Za-z_])", text, re.IGNORECASE):
                hits.append((verb, text[:120]))
    assert not hits, f"{LAKE_PATH} 的代码字符串里出现写语义动词:{hits}"


def test_lake_source_does_not_lean_on_watermarks():
    """④-e:代码里不许出现 crawler_state / watermark —— 那是补数游标不是新鲜度。

    (docstring 里可以讲这个坑,代码里不许真去读。)
    """
    hits = [
        s for s in _code_strings()
        if "crawler_state" in s.lower() or "watermark" in s.lower()
    ]
    assert not hits, f"lake.py 的代码字符串里引用了补数游标:{hits}"


#: 有写能力、lake 不该碰的模块。
FORBIDDEN_IMPORTS = frozenset(
    {"shutil", "tempfile", "pickle", "csv", "sqlite3", "subprocess", "socket"}
)


def test_lake_source_imports_nothing_write_capable():
    """④-f:不许 import 具备写/外联能力的模块。"""
    imported: set[str] = set()
    for node in ast.walk(LAKE_TREE):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    bad = imported & FORBIDDEN_IMPORTS
    assert not bad, f"{LAKE_PATH} import 了不该碰的模块:{sorted(bad)}"


#: 允许直连数据湖的文件(仓库相对路径)。加白名单要写理由。
#:
#: * `snapshots/lake.py` —— 就是访问层本身。
#: * `ops/test_env.py` —— 卡 0.1 的红线自检,必须亲手开一条连接去证明
#:   引擎级只读(`access_mode=READ_ONLY` + 写语句被顶回),而且它不对任何人供数。
#: * 本文件 —— 同理,还要验"连接关没关"。
#: **只读我们自己冻结的快照、从不碰湖**的文件。卡 2.1a 引入。
#:
#: 上面那条守门要防的是"绕过 `lake.py` 去够**活湖**" —— 只读语义、重试、线程上限、
#: fd 上限，全都是为**活的 catalog**（有并发 ETL 写者持锁）准备的。
#: 这几个文件用 ``duckdb.connect(":memory:")`` 读 ``$SNAPSHOTS/v1/`` 下我们自己冻的
#: parquet：没有锁、没有写者、没有 catalog，那套保护在这里无事可做，
#: 而 provider 必须能在**湖不可达时重建**，硬走 lake.py 反而制造一个假依赖。
#:
#: 免死金牌**不是白给的**：`test_snapshot_only_connectors_never_reach_the_lake`
#: 逐文件验它们的每一处 connect 都只开 ``":memory:"``、且源码里不出现
#: ``cfg.CATALOG`` / ``cfg.LAKE`` / ``cfg.GOLD``。谁往这几个文件里加一条真连接，
#: 那条就红 —— 白名单挡不住它。
SNAPSHOT_ONLY_CONNECTORS = frozenset({
    "snapshots/qlib_provider.py",
    "ops/test_qlib_provider.py",
    "ops/acceptance/card_2_1a_full_verify.py",
    # 卡 1.3 的两通道对账：只读 $SNAPSHOTS/{v1,public_v1} 下我们自己冻的 parquet，
    # 三处 connect 全是 ":memory:"，源码里不出现 cfg.CATALOG / cfg.LAKE / cfg.GOLD。
    # 走 lake.py 反而要挂上活 catalog 的只读锁 —— 而 19 个爬虫正持着它（N-42）。
    "ops/recon_public_vs_private.py",
    "ops/test_recon_public.py",
})

CONNECT_ALLOWLIST = frozenset(
    {"snapshots/lake.py", "ops/test_env.py", "ops/test_lake_baseline.py"}
) | SNAPSHOT_ONLY_CONNECTORS

#: 不参与扫描的子树。`ops/recon/` 是第一轮服务器侦察的**存档证据**
#: (一次性探针 + 它们的 `.out` 输出),不是会被 import 或调度的运行代码;
#: 改写它们等于篡改侦察记录。它们本来也都是 `read_only=True`。
#: ``ops/reports/adv_*/`` 是**对抗审计员**的一次性探针。审计员必须绕过被审计的
#: 模块（``snapshots/lake.py``）独立取数 —— 经它取证等于让被告自证清白，
#: 正是卡 0.2 的 D1 刚修掉的“自证循环”。这些脚本用
#: ``duckdb.connect(":memory:")`` + ``read_parquet(gold)``，只读、不碰 catalog、
#: 不被 import 也不被调度；留在仓库里是为了审计结论可复现。
CONNECT_SCAN_EXEMPT_TREES = ("ops/recon/", "ops/reports/adv_")


def _connect_call_sites(path: Path) -> list[int]:
    """AST 找出文件里**真正的** connect 调用行号。

    刻意不用文本 grep:`genebench_config.py` 的注释和 `snapshots/__init__.py`
    的 docstring 都写着"必须 ``duckdb.connect(..., read_only=True)``" ——
    那是**文档**,不是调用。文本扫描会把写文档的人抓起来,这不对。
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return []
    imports_duckdb = any(
        (isinstance(n, ast.Import) and any(a.name.split(".")[0] == "duckdb" for a in n.names))
        or (isinstance(n, ast.ImportFrom) and (n.module or "").split(".")[0] == "duckdb")
        for n in ast.walk(tree)
    )
    if not imports_duckdb:
        return []
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _dotted(node.func).endswith("connect")
    ]


def test_lake_is_the_only_module_that_connects_to_the_lake():
    """除白名单外,整个仓库只能经 `snapshots/lake.py` 访问数据湖。

    卡 0.1 的 `test_every_duckdb_connect_in_repo_is_read_only` 管的是
    "每处连接都带只读标志";这条更进一步 —— **根本不该有第二处连接**。
    只读语义、重试、线程上限、fd 上限只在 lake.py 里被盯着,绕过它就全丢了。
    """
    offenders = []
    scanned = 0
    for path in sorted(cfg.REPO.rglob("*.py")):
        if any(p in {".git", "__pycache__", "env", ".pytest_cache"} for p in path.parts):
            continue
        rel = str(path.relative_to(cfg.REPO))
        if rel in CONNECT_ALLOWLIST or rel.startswith(CONNECT_SCAN_EXEMPT_TREES):
            continue
        scanned += 1
        for lineno in _connect_call_sites(path):
            offenders.append(f"{rel}:{lineno}")
    assert scanned > 0, "一个文件都没扫到,扫描器本身坏了"
    assert not offenders, (
        f"这些地方绕过 snapshots/lake.py 直连了数据湖:{offenders}。"
        f"要么改走 lake,要么把理由写进 CONNECT_ALLOWLIST。"
    )


# ==========================================================================
# 附加:把"只读"从源码级钉到引擎级 + 行为级
# ==========================================================================


def test_snapshot_only_connectors_never_reach_the_lake():
    """`SNAPSHOT_ONLY_CONNECTORS` 的免死金牌必须**当场兑现**。

    白名单是按文件名给的，粒度太粗：日后谁往 `qlib_provider.py` 里加一条
    `duckdb.connect(cfg.CATALOG)`，上面那条守门会**静默放行**。
    这条把它补上 —— 逐文件验两件事：

    1. 每一处 `*.connect(...)` 的第一个位置参数都是字面量 ``":memory:"``；
    2. 源码里不出现 `cfg.CATALOG` / `cfg.LAKE` / `cfg.GOLD`。

    判别力：先断言真的扫到了 connect 调用，否则这条在任何实现上都恒绿。
    """
    forbidden = ("CATALOG", "LAKE", "GOLD")
    total_calls = 0
    problems: list[str] = []
    for rel in sorted(SNAPSHOT_ONLY_CONNECTORS):
        path = cfg.REPO / rel
        assert path.exists(), f"白名单里的 {rel} 不存在 —— 白名单发霉了"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        calls = [n for n in ast.walk(tree)
                 if isinstance(n, ast.Call) and _dotted(n.func).endswith("connect")]
        total_calls += len(calls)
        for node in calls:
            arg = node.args[0] if node.args else None
            ok = isinstance(arg, ast.Constant) and arg.value == ":memory:"
            if not ok:
                problems.append(f"{rel}:{node.lineno} connect 的参数不是 ':memory:'")
        for node in ast.walk(tree):
            if (isinstance(node, ast.Attribute) and node.attr in forbidden
                    and _dotted(node).startswith("cfg.")):
                problems.append(f"{rel}:{node.lineno} 引用了 cfg.{node.attr}")
    assert total_calls >= len(SNAPSHOT_ONLY_CONNECTORS), (
        f"只扫到 {total_calls} 处 connect —— 这条断言当前是空的，去查扫描器")
    assert not problems, problems


def test_connection_is_read_only_at_engine_level(conn):
    """引擎级防线:写语句必须被 duckdb 顶回来(源码干净 ≠ 运行时安全)。"""
    import duckdb

    for stmt in (
        "CREATE TABLE gb_probe_should_fail(a INTEGER)",
        "INSERT INTO daily SELECT * FROM daily LIMIT 0",
        "DELETE FROM daily",
    ):
        with pytest.raises((duckdb.Error, RuntimeError)):
            conn.execute(stmt)


def test_threads_are_capped_on_entry(conn):
    """湖是共享生产资产:连接一打开就把线程数收到 DEFAULT_THREADS。"""
    value = conn.execute("SELECT current_setting('threads')").fetchone()[0]
    assert int(value) == lake.DEFAULT_THREADS == 2


def test_context_manager_always_closes():
    """上下文管理器必须保证连接被关闭 —— 正常路径和异常路径都是。"""
    import duckdb

    with lake.catalog() as c:
        assert c.execute("SELECT 1").fetchone()[0] == 1
    with pytest.raises((duckdb.Error, RuntimeError)):
        c.execute("SELECT 1")

    class Boom(RuntimeError):
        pass

    leaked = None
    with pytest.raises(Boom):
        with lake.catalog() as c2:
            leaked = c2
            raise Boom
    with pytest.raises((duckdb.Error, RuntimeError)):
        leaked.execute("SELECT 1")


def test_open_catalog_returns_a_usable_connection_that_caller_closes():
    """`open_catalog()` 返回裸连接,调用方自己关。"""
    import duckdb

    c = lake.open_catalog()
    try:
        assert c.execute("SELECT 42").fetchone()[0] == 42
    finally:
        c.close()
    with pytest.raises((duckdb.Error, RuntimeError)):
        c.execute("SELECT 1")


def test_read_gold_reads_a_targeted_partition(conn):
    """`read_gold` 走定向分区 —— 这是绕开 "too many open files" 的正道。"""
    part = ENTRIES["daily"]["latest_gold_partition_upto_freeze"]
    assert part == "trade_date=2026-07-31", f"冻结线当天的分区没了?拿到 {part}"
    df = lake.read_gold("daily", part, conn=conn)
    assert len(df) > 1000, f"{part} 只读到 {len(df)} 行"
    assert "ts_code" in df.columns and "close" in df.columns
    assert len(df.columns) == ENTRIES["daily"]["columns_in_probe_partitions"][part]


def test_union_by_name_default_because_turning_it_off_silently_drops_columns(conn):
    """陷阱 H1 的活体钉子:关掉 `union_by_name` 是**静默丢列**,不是报错。

    这条测试同时是**金丝雀** —— 如果哪天湖侧把历史分区补齐了、漂移消失了,
    它会红,提醒我们回头把 `lake.py` 与 baseline 里的 H1/H2 结论改掉。
    """
    span = "trade_date=2026-08-0*"  # 跨 2026-08-06 这个漂移点
    wide = lake.read_gold("daily", span, limit=1, conn=conn)
    narrow = lake.read_gold("daily", span, limit=1, union_by_name=False, conn=conn)
    assert len(wide.columns) > len(narrow.columns), (
        f"daily 跨 {span} 的分区漂移消失了(union={len(wide.columns)} 列,"
        f"非 union={len(narrow.columns)} 列)。这是好事,但 lake.py 与 "
        f"ops/lake_baseline.json 里的 H1/H2 结论需要重写。"
    )
    assert "last_seen_at" in wide.columns
    assert "last_seen_at" not in narrow.columns, (
        "关掉 union_by_name 竟然也拿到了 last_seen_at —— H1 的机制变了"
    )
    # 默认必须是安全的那一侧
    assert list(lake.read_gold("daily", span, limit=1, conn=conn).columns) == list(
        wide.columns
    )


def test_schema_drift_is_recorded_per_partition_not_guessed():
    """陷阱 H2:漂移是逐分区的,基线必须抽样多个分区而不是拿一个当代表。"""
    drift = BASELINE["summary"]["schema_drift_tables"]
    assert drift, "一张漂移表都没测出来?抽样逻辑可能坏了"
    for ds, entry in ENTRIES.items():
        probes = entry["schema_probe_partitions"]
        assert len(probes) >= 1
        assert set(probes) == set(entry["columns_in_probe_partitions"])
        if entry["gold_partition_count"] >= 4:
            assert len(probes) >= 3, f"{ds} 只抽了 {len(probes)} 个分区,不足以看出漂移"
    # income 是"逐分区漂移"的样本:抽样分区之间列数就不一致
    income = ENTRIES["income"]
    assert income["columns_drifting_across_probes"], (
        f"income 的抽样分区之间不再有列差:{income['columns_in_probe_partitions']}"
    )


def test_financial_statements_need_union_by_name_or_they_blow_up(conn):
    """陷阱 H3:三大报表跨票读时**列类型**也漂移,关掉 union 会直接抛异常。

    跨票取数是 v1 基本面因子的主路径,这条要是回归了整批因子会挂。
    """
    import duckdb

    glob = "ts_code=00000*"
    ok = lake.read_gold("income", glob, limit=5, conn=conn)
    assert len(ok.columns) >= 88
    with pytest.raises(duckdb.Error) as exc:
        lake.read_gold("income", glob, limit=5, union_by_name=False, conn=conn)
    assert "cast" in str(exc.value).lower(), (
        f"H3 的失败机制变了:{str(exc.value)[:200]}"
    )


def test_known_hazards_are_carried_in_the_baseline():
    """把本卡实测的陷阱钉进产物 —— 后面的卡读 JSON 就够,不用重踩。"""
    hazards = {h["id"]: h for h in BASELINE["known_hazards"]}
    assert set(hazards) >= {"H1", "H2", "H3", "H4", "H5", "H6", "H7"}
    for h in hazards.values():
        assert h["evidence"] and h["impact"] and h["mitigation"]


def test_read_gold_column_projection_and_limit(conn):
    df = lake.read_gold(
        "daily", "trade_date=2026-07-31", columns=["ts_code", "close"], limit=5, conn=conn
    )
    assert list(df.columns) == ["ts_code", "close"]
    assert len(df) == 5


@pytest.mark.parametrize(
    "bad_glob", ["../../etc", "/absolute/path", "trade_date=2026-07-31;DROP", ""]
)
def test_read_gold_rejects_path_escape(bad_glob):
    """分区 glob 不许越出数据集目录,也不许夹带第二条语句。"""
    with pytest.raises(lake.LakeError):
        lake.read_gold("daily", bad_glob)


@pytest.mark.parametrize("bad_ds", ["../daily", "daily; --", "Daily", "", "da ily"])
def test_dataset_name_is_validated(bad_ds):
    with pytest.raises(lake.LakeError):
        lake.gold_dir(bad_ds)


def test_query_rejects_statements_that_can_write_files(tmp_path):
    """只读连接挡不住 `COPY ... TO 'file'`(那是写文件系统),白名单挡得住。

    D6:光断言"抛了 LakeError"是不够的 —— 那只证明**这次调用**失败了,
    没证明**文件没被创建**。异常也可能发生在写完之后。所以这里把目标路径
    指到 tmp_path(测试独占、事前必不存在),事后逐个断言它没被创建出来。
    """
    csv_target = tmp_path / "gb_should_never_exist.csv"
    db_target = tmp_path / "gb_should_never_exist_db"
    parquet_target = tmp_path / "gb_should_never_exist.parquet"
    targets = [csv_target, db_target, parquet_target]
    for t in targets:
        assert not t.exists(), f"前置条件坏了:{t} 事前就存在"

    statements = (
        f"COPY (SELECT 1) TO '{csv_target}'",
        f"COPY (SELECT 1) TO '{parquet_target}' (FORMAT PARQUET)",
        "CREATE TABLE t AS SELECT 1",
        f"EXPORT DATABASE '{db_target}'",
    )
    for stmt in statements:
        with pytest.raises(lake.LakeError):
            lake.query(stmt)

    for t in targets:
        assert not t.exists(), (
            f"语句被 LakeError 拒了,但 {t} 还是被创建出来了 —— "
            f"说明拦截发生在写盘**之后**,白名单没起到它该起的作用"
        )
    assert not any(tmp_path.iterdir()), (
        f"{tmp_path} 里出现了不该有的东西:{sorted(p.name for p in tmp_path.iterdir())}"
    )


def test_query_rejects_session_state_changes(conn):
    """D4:`SET` 不在白名单里 —— 它能绕过本模块承诺的线程上限。

    `SET` 既不写库也不写文件,所以只读连接和"写路径"审计**都拦不住它**;
    但实测 ``lake.query("SET threads=12")`` 能把线程数从 2 抬到 12,
    直接推翻 lake.py 自述的"湖是共享生产资产,不许把 12 核吃满"。
    白名单要挡的不只是"写",是"一切能改变本模块承诺的语义的语句"。
    """
    assert "set" not in lake._ALLOWED_STATEMENT_HEADS, (
        "白名单里又出现了 set —— 它能绕过线程上限,不许放行"
    )
    before = int(conn.execute("SELECT current_setting('threads')").fetchone()[0])
    assert before == lake.DEFAULT_THREADS == 2

    for stmt in (
        "SET threads=12",
        "set threads = 12",
        "SET GLOBAL threads=12",
        "SET memory_limit='200GB'",
    ):
        with pytest.raises(lake.LakeError) as exc:
            lake.query(stmt, conn=conn)
        assert "白名单" in str(exc.value)

    after = int(conn.execute("SELECT current_setting('threads')").fetchone()[0])
    assert after == before == lake.DEFAULT_THREADS, (
        f"线程数被改了:{before} -> {after}。白名单没拦住 SET。"
    )


def test_thread_cap_is_reachable_through_the_supported_entry_point():
    """剔掉 `SET` 没有误伤:要调线程数,走 `open_catalog(threads=...)`。

    这条是 D4 的配套 —— 证明我们堵的是**绕过去的路**,不是需求本身。
    """
    c = lake.open_catalog(threads=4)
    try:
        assert int(c.execute("SELECT current_setting('threads')").fetchone()[0]) == 4
    finally:
        c.close()
    with pytest.raises(lake.LakeError):
        lake.open_catalog(threads=0)


def test_query_allows_reads(conn):
    df = lake.query("SELECT 1 AS one", conn=conn)
    assert df["one"].tolist() == [1]


def test_freshness_helper_only_speaks_for_time_partitions():
    """`gold_latest_value` 只对时间序分区给答案,免得把 ts_code 当成日期。

    ⚠️ 这里对 baseline 只能要求**单调不回退**,不能要求逐字相等。
    湖是**活的**(外部 ETL 每天在写),``gold_latest_partition_value`` 是**冻结**的记录;
    写 ``==`` 等于把"活的新鲜度"钉进静态基线,每过一天这条就红一次 ——
    2026-08-31 的合议验收实测撞上:现场 ``'2026-08-31'`` vs baseline ``'2026-08-28'``,
    M0 验收因此 303 passed / 1 failed,而根因与被验收的卡毫无关系。
    同文件 `test_gold_partitions_match_baseline` 对 ``latest_gold_partition`` 立的就是
    ``>=`` 这条约定,这里对齐它。**判别力没有因此下降**:下面第二条断言把返回值钉死在
    "daily 现场最新分区的值"上,helper 认错列 / 认错数据集照样必红。
    """
    live = lake.gold_latest_value("daily")
    assert live >= ENTRIES["daily"]["gold_latest_partition_value"], (
        f"daily 现场新鲜度 {live} 早于 baseline 记的 "
        f"{ENTRIES['daily']['gold_latest_partition_value']} —— 湖回退了?{_regen()}"
    )
    assert live == lake.split_partition(lake.latest_gold_partition("daily"))[1], (
        f"gold_latest_value('daily') = {live},但现场最新分区是 "
        f"{lake.latest_gold_partition('daily')} —— helper 读的不是这张表的分区值"
    )
    assert live >= cfg.FREEZE_DATE
    # income 是 ts_code 分区 —— 最新分区是字典序最大的代码,不是新鲜度
    assert lake.gold_latest_value("income") is None
    assert lake.latest_gold_partition("income").startswith("ts_code=")


def test_partitions_upto_freeze_line_never_leaks_the_future():
    """冻结线工具:截出来的分区一个都不许越过 `cfg.FREEZE_DATE`(红线 7)。"""
    parts = lake.partitions_upto("daily")
    assert parts, "daily 在冻结线之前没有分区?"
    for p in parts:
        assert lake.split_partition(p)[1] <= cfg.FREEZE_DATE
    assert parts[-1] == "trade_date=2026-07-31"
    assert len(parts) < len(lake.gold_partitions("daily"))


def test_column_range_is_bounded_by_the_freeze_line(conn):
    """`lake.column_range` 的 bound 必须真的截住 —— 它是 D1 对账的量具。"""
    unbounded = lake.column_range("daily", "trade_date", conn=conn)
    bounded = lake.column_range(
        "daily", "trade_date", bound=lake.FREEZE_DATE_COMPACT, conn=conn
    )
    assert unbounded["max_upto"] is None, "没给 bound 时不该有 max_upto"
    assert bounded["max_upto"] == "20260731"
    assert bounded["max_upto"] <= lake.FREEZE_DATE_COMPACT
    assert bounded["max"] == unbounded["max"] >= lake.FREEZE_DATE_COMPACT
    assert bounded["rows"] == unbounded["rows"] > 0
    with pytest.raises(lake.LakeError):
        lake.column_range("daily", "trade_date; --", conn=conn)


def test_raise_open_file_limit_is_effective():
    """默认 soft fd 只有 1024,查全表会 "too many open files" —— 抬上去且不需要特权。"""
    import resource

    old, new = lake.raise_open_file_limit()
    assert new >= min(lake.OPEN_FILE_TARGET, resource.getrlimit(resource.RLIMIT_NOFILE)[1])
    assert resource.getrlimit(resource.RLIMIT_NOFILE)[0] >= new
    assert old <= new


# --------------------------------------------------------------- 湖锁来源核实（2026-09-05）

def test_the_union_fetcher_does_not_touch_the_lake():
    """**N-68 的取数脚本完全不碰湖** —— 它只读一个文本清单 + 打 baostock。

    这条钉住一个事实：两个后台批次并发时 `test_universe_source_a` 系列的假红
    **不是 N-68 造成的**。湖锁争用的来源是外部 ETL（19 个爬虫），
    那是既有的、已登记的家族（`test_catalog_opens_read_only` 的注释就写着
    「外部 ETL 在写，非本测试所为」）。

    把「谁在持锁」写成判据，是为了下次再看到假红时不用重新猜。
    """
    import ast

    src = (Path(__file__).resolve().parents[1] / "ops" / "acceptance"
           / "card_2_5_fetch_union.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not ({"catalog", "connect"} & names), "取数脚本碰湖了 —— 它不该碰"
    assert "lake" not in {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}


def test_the_reconciler_reads_parquet_without_taking_the_catalog_lock():
    """对账脚本走 `lake.query` + `read_parquet` —— **不开 catalog**（N-42 的纪律）。"""
    import ast

    src = (Path(__file__).resolve().parents[1] / "ops" / "acceptance"
           / "card_2_5_source_reconcile.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    attrs = [n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)]
    assert "query" in attrs, "对账脚本没有走 lake.query"
    assert "catalog" not in attrs, "对账脚本开了 catalog —— 它读的是 parquet，不需要"
    assert "read_parquet" in src


def test_the_limit_oracle_holds_the_catalog_only_around_its_queries():
    """涨跌停验收**确实**要开 catalog（它查 `stk_limit` / `daily` / `namechange` 视图），
    但必须是 `with` 包住查询、查完就关 —— 不许在整个脚本生命周期里持着。"""
    src = (Path(__file__).resolve().parents[1] / "ops" / "acceptance"
           / "card_2_5_limit_oracle.py").read_text(encoding="utf-8")
    assert "with lake.catalog(" in src, "没有用上下文管理器 —— 连接可能不会被关"
    assert src.count("lake.catalog(") == 1, "开了不止一次 catalog"
