# -*- coding: utf-8 -*-
"""卡 1.4 验收：快照 manifest 完整 + **同一查询两后端结果一致**。

立场同前几卡：**不写自证式断言**。
- 一致性比对是真的两条路径：``live`` 走 catalog 视图，``snapshot`` 走 parquet 文件。
  不是"两边都读 parquet"然后自己跟自己比。
- `assert_frame_equal` **不放水**：不传 ``check_dtype=False`` / ``check_like=True``
  （那会把比对削成"形状差不多就行"）。只做排序与索引归一化 —— 行序不是语义。
- 另有一条**篡改必红**的负控：改一个字节，sha256 与一致性都必须炸。
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import genebench_config as cfg  # noqa: E402
from snapshots import build_snapshot as bs  # noqa: E402
from snapshots import lake, v1_tables  # noqa: E402

FREEZE = lake.FREEZE_DATE_COMPACT

pytestmark = pytest.mark.skipif(
    not bs.MANIFEST.exists(),
    reason="快照还没建：先跑 python -m snapshots.build_snapshot",
)


@pytest.fixture(scope="module")
def manifest() -> dict:
    return bs.read_manifest()


@pytest.fixture(scope="module")
def con():
    lake.raise_open_file_limit()
    with lake.catalog(retries=40, retry_wait=15.0) as c:
        yield c


def _norm(df: pd.DataFrame) -> pd.DataFrame:
    """只归一化行序与索引 —— 列名、列序、dtype、值一律不动。"""
    if df.empty:
        return df.reset_index(drop=True)
    return df.sort_values(list(df.columns)).reset_index(drop=True)


# ======================================================================
# manifest 完整性
# ======================================================================


def test_manifest_covers_every_v1_table(manifest):
    listed = {t["dataset"] for t in manifest["tables"]}
    expected = {s.dataset for s in v1_tables.V1_TABLES}
    assert listed == expected, f"漏/多：{sorted(listed ^ expected)}"
    assert manifest["table_count"] == len(expected) == 22


def test_manifest_sha256_matches_the_actual_file(manifest):
    for entry in manifest["tables"]:
        path = bs.TABLES_DIR / entry["path"]
        assert path.exists(), f"manifest 记了 {entry['path']} 但文件不在"
        assert bs._sha256(path) == entry["sha256"], f"{entry['dataset']} sha256 对不上"
        assert path.stat().st_size == entry["bytes"]


def test_manifest_rows_match_the_actual_parquet(manifest, con):
    for entry in manifest["tables"]:
        path = bs.TABLES_DIR / entry["path"]
        n = con.execute(
            f"SELECT count(*) FROM read_parquet('{path}')"  # noqa: S608
        ).fetchone()[0]
        assert int(n) == entry["rows"], f"{entry['dataset']} 行数对不上"


def test_manifest_carries_the_stall_signal(manifest):
    """"过了冻结线"与"这张表还活着"是两个信号（卡 0.2 D3）。

    ⚠️ 第一版这条测试**恒真**：`stalled_tables` 当时被误存成一串 dict 的
    str()，与 dataset 名交不上，于是"flagged 空 == 交集空"照样绿。
    现在钉死"必须真的标出 8 张"，空集直接判失败。
    """
    assert "stalled_datasets" in manifest and "stalled_tables" in manifest
    names = set(manifest["stalled_datasets"])
    assert names, "停更清单是空的 —— 卡 0.2 实测有 8 张，这里不该为空"
    assert all(isinstance(x, str) for x in names), "stalled_datasets 应该是名字不是对象"
    flagged = {t["dataset"] for t in manifest["tables"] if t.get("source_stalled")}
    in_v1 = names & {t["dataset"] for t in manifest["tables"]}
    assert flagged == in_v1, f"标记与清单不符：{sorted(flagged ^ in_v1)}"
    assert len(flagged) >= 8, f"只标出 {len(flagged)} 张，卡 0.2 实测是 8 张"
    # 明细必须带得动"为什么它看起来是绿的"
    detailed = {d.get("dataset") for d in manifest["stalled_tables"] if d.get("why_it_looks_green")}
    assert detailed, "停更明细丢了 why_it_looks_green —— 那正是 D3 要传达的东西"


def test_snapshot_lives_outside_the_repo():
    assert bs.TABLES_DIR.is_relative_to(cfg.SNAPSHOTS)
    assert not str(bs.TABLES_DIR).startswith(str(cfg.REPO))
    assert not str(bs.TABLES_DIR).startswith("/home/")


def test_snapshot_dir_is_separate_from_card_1_1_and_1_2(manifest):
    """N-14 点过：不能和 universe/ tradability/ 混在一起。"""
    names = {p.name for p in bs.TABLES_DIR.iterdir()}
    assert "universe" not in names and "tradability" not in names
    assert bs.TABLES_DIR.name == "tables"


# ======================================================================
# 冻结线硬验（含边界当天）
# ======================================================================


@pytest.mark.parametrize(
    "spec", [s for s in v1_tables.V1_TABLES if s.date_column], ids=lambda s: s.dataset
)
def test_no_row_beyond_the_freeze_line(spec, con):
    """红线 7：日期列不得越过冻结线。**两类有据可查的例外**，不是网开一面：

    - **capture_time 表**（trade_cal）：它的时间语义不在 ``cal_date`` 上，
      而在 ``snapshot_date``（我们哪天抄的表）。``cal_date`` 排到 2026-12-31
      是**预写的未来日历**，冻结时点本就合法存在，砍掉它 T+N 对齐就断了。
      这类表的冻结线不变量由 `test_capture_time_tables_are_not_truncated`
      与 `test_trade_cal_keeps_the_future_calendar` 两条**正反面**看住。
    - **三大报表**：走 ``ann_date`` / ``f_ann_date`` 超集口径，
      允许 ``ann_date`` 越线但必须是被 ``f_ann_date`` 捞回来的。
    """
    path = bs.TABLES_DIR / f"{spec.dataset}.parquet"
    col = spec.date_column
    if lake.partition_semantics(spec.dataset) == "capture_time":
        entry = next(
            t for t in bs.read_manifest()["tables"] if t["dataset"] == spec.dataset
        )
        assert entry["truncated_by_freeze_line"] is False
        assert entry["rows"] == entry["source_rows"], (
            f"{spec.dataset} 是 capture_time，应全量拷；行数与源不等说明被截过"
        )
        return
    if spec.dataset in bs.STATEMENTS:
        # 超集口径：允许 ann_date 越线，但必须是被 f_ann_date 捞回来的
        bad = con.execute(
            f"SELECT count(*) FROM read_parquet('{path}') "  # noqa: S608
            f"WHERE {col} > '{FREEZE}' AND "
            f"(f_ann_date IS NULL OR f_ann_date > '{FREEZE}')"
        ).fetchone()[0]
        assert int(bad) == 0, f"{spec.dataset} 有 {bad} 行两列都越线"
        return
    bad = con.execute(
        f"SELECT count(*) FROM read_parquet('{path}') WHERE {col} > '{FREEZE}'"  # noqa: S608
    ).fetchone()[0]
    assert int(bad) == 0, f"{spec.dataset} 有 {bad} 行越过冻结线"


def test_boundary_day_itself_is_included(con):
    """截断是 ``<=`` 不是 ``<`` —— 边界当天不能被切掉。"""
    path = bs.TABLES_DIR / "daily.parquet"
    n = con.execute(
        f"SELECT count(*) FROM read_parquet('{path}') WHERE trade_date = '{FREEZE}'"  # noqa: S608
    ).fetchone()[0]
    live = con.execute(
        f"SELECT count(*) FROM daily WHERE trade_date = '{FREEZE}'"  # noqa: S608
    ).fetchone()[0]
    assert int(n) == int(live) > 0, "冻结线当天的行被切掉了或对不上"


def test_capture_time_tables_are_not_truncated(manifest):
    """capture_time 表按日期列截 = 砍掉预写的未来日历（卡 0.2 D3 的同源坑）。

    首版我按 ``cal_date`` 截了 trade_cal，双后端一致性当场炸出 6574 vs 6421 ——
    那 153 行正是 2026-08-01…2026-12-31 的未来日历，冻结时点本就合法存在。
    """
    capture = [t for t in manifest["tables"]
               if t.get("partition_semantics") == "capture_time"]
    assert capture, "一张 capture_time 表都没有？分类逻辑变了，回来看"
    for entry in capture:
        assert entry["truncated_by_freeze_line"] is False, (
            f"{entry['dataset']} 是 capture_time 却被按日期列截断了"
        )
        assert entry["rows"] == entry["source_rows"]
    assert any(e["dataset"] == "trade_cal" for e in capture)


def test_trade_cal_keeps_the_future_calendar(con):
    """未来日历必须留着 —— T+N 对齐要用它。"""
    path = bs.TABLES_DIR / "trade_cal.parquet"
    n = con.execute(
        f"SELECT count(*) FROM read_parquet('{path}') WHERE cal_date > '{FREEZE}'"  # noqa: S608
    ).fetchone()[0]
    assert int(n) > 0, "未来日历被砍掉了"


@pytest.mark.parametrize("ds", ["stock_basic", "index_member_all", "index_basic"])
def test_dateless_tables_are_copied_whole(ds, con, manifest):
    """无日期列的表不按日期截 —— 按它们的 capture/entity 语义，截了就错。"""
    entry = next(t for t in manifest["tables"] if t["dataset"] == ds)
    assert entry["truncated_by_freeze_line"] is False
    assert entry["rows"] == entry["source_rows"]


# ======================================================================
# 双后端一致（**真的两条路径**）
# ======================================================================

QUERIES: list[tuple[str, str, str]] = [
    ("daily 边界当天", "daily",
     f"SELECT ts_code, trade_date, open, high, low, close, volume FROM {{src}} "
     f"WHERE trade_date = '{FREEZE}'"),
    ("adj_factor 单票(夹冻结线)", "adj_factor",
     f"SELECT * FROM {{src}} WHERE ts_code = '600519.SH' AND trade_date <= '{FREEZE}'"),
    ("stk_limit 一个月", "stk_limit",
     "SELECT * FROM {src} WHERE trade_date >= '20260701' AND trade_date <= '20260731'"),
    ("suspend_d(夹冻结线)", "suspend_d",
     f"SELECT * FROM {{src}} WHERE trade_date <= '{FREEZE}'"),
    # ⚠️ `trade_cal` 也从等值比对里拿掉了。它今天能逐行相等**纯属运气**——
    # 它恰好是 8 张停更表之一（冻在 2026-08-05）。依赖"一张停更表继续停更"
    # 是隐藏假设：湖侧 ETL 一恢复，这条就和 stock_basic 一样过夜即红。
    # capture_time 表统一由子集不变量看住（见下面参数化的 prefix 测试），
    # "不截"这件事由 test_capture_time_tables_are_not_truncated 与
    # test_trade_cal_keeps_the_future_calendar 正反两条管。
    ("income 单票", "income",
     "SELECT ts_code, ann_date, f_ann_date, end_date, update_flag FROM {src} "
     "WHERE ts_code = '600519.SH'"),
    ("income_vip 的 NULL f_ann_date", "income_vip",
     "SELECT count(*) AS n FROM {src} WHERE f_ann_date IS NULL"),
    ("index_weight 末期", "index_weight",
     f"SELECT * FROM {{src}} WHERE trade_date = '{FREEZE}'"),

    ("dividend 一年", "dividend",
     "SELECT * FROM {src} WHERE ann_date >= '20260101' AND ann_date <= '20260731'"),

]


def test_equality_queries_exclude_growing_capture_tables():
    """护栏：**等值比对里不许出现 capture_time 表**。

    `stock_basic` 是每天全量抄一份的多快照表。我试过三种"应该时间不变"的查询，
    三种都过夜即红：
      · 全表 `SELECT *`            → live 每天 +5,892 行
      · `DISTINCT` 静态字段         → 新上市带来新 code
      · `count(DISTINCT ts_code)`  → 同上
    根因是这类表**没有**任何全表等值查询是时间不变的：新增码会进来，
    退市还会**回改**已有码的 `list_status` / `delist_date`。

    所以规则是：等值比对只对冻结线内可截断的表做；
    还在长的 capture 表由 `test_growing_capture_table_snapshot_is_a_prefix_of_live`
    用**子集不变量**看住（快照 ⊆ live，且不含 live 之外的行）。
    这条测试防的是有人日后"顺手加回来"。
    """
    offenders = [
        ds for _, ds, _ in QUERIES
        if lake.partition_semantics(ds) == "capture_time"
    ]
    assert not offenders, (
        f"等值比对里混进了 capture_time 表：{offenders}。"
        f"它们没有时间不变的全表查询，只能用子集不变量。"
    )
    # 反过来也要有判别力：真的存在这样的表，否则本条测试是空的
    from snapshots import v1_tables

    capture = [
        s.dataset for s in v1_tables.V1_TABLES
        if lake.partition_semantics(s.dataset) == "capture_time"
    ]
    assert capture, "一张 capture_time 表都没有？分类逻辑变了，回来看"


@pytest.mark.parametrize("label,ds,tmpl", QUERIES, ids=[q[0] for q in QUERIES])
def test_two_backends_agree(label, ds, tmpl, con):
    live = con.execute(tmpl.format(src=f'"{ds}"')).df()
    path = bs.TABLES_DIR / f"{ds}.parquet"
    snap = con.execute(tmpl.format(src=f"read_parquet('{path}')")).df()
    assert len(live) > 0 or len(snap) > 0, f"{label} 两边都空，这条查询没有判别力"
    assert_frame_equal(_norm(live), _norm(snap))


def test_cross_table_join_agrees(con):
    """跨表 join —— 单表一致不代表 join 起来还一致。"""
    tmpl = (
        "SELECT d.ts_code, d.trade_date, d.close, a.adj_factor "
        "FROM {daily} d JOIN {adj} a "
        "ON d.ts_code = a.ts_code AND d.trade_date = a.trade_date "
        f"WHERE d.trade_date = '{FREEZE}' AND d.ts_code < '002000.SZ'"
    )
    live = con.execute(tmpl.format(daily='"daily"', adj='"adj_factor"')).df()
    snap = con.execute(
        tmpl.format(
            daily=f"read_parquet('{bs.TABLES_DIR / 'daily.parquet'}')",
            adj=f"read_parquet('{bs.TABLES_DIR / 'adj_factor.parquet'}')",
        )
    ).df()
    assert len(live) > 0
    assert_frame_equal(_norm(live), _norm(snap))


# ======================================================================
# 负控：篡改必红
# ======================================================================


def test_tampering_is_detected(tmp_path, manifest, con):
    """改一个字节，sha256 与一致性都必须炸 —— 证明上面的断言不是恒真。"""
    entry = next(t for t in manifest["tables"] if t["dataset"] == "suspend_d")
    src = bs.TABLES_DIR / entry["path"]
    victim = tmp_path / entry["path"]
    shutil.copy2(src, victim)

    assert bs._sha256(victim) == entry["sha256"], "复制品本身就对不上，测试环境有问题"

    raw = bytearray(victim.read_bytes())
    mid = len(raw) // 2
    raw[mid] ^= 0xFF
    victim.write_bytes(bytes(raw))

    assert bs._sha256(victim) != entry["sha256"], "改了一个字节 sha256 却没变？"

    # 一致性侧也要炸：要么读不出来，要么内容不等
    tmpl = "SELECT * FROM {src}"
    live = con.execute(tmpl.format(src='"suspend_d"')).df()
    try:
        snap = con.execute(
            tmpl.format(src=f"read_parquet('{victim}')")  # noqa: S608
        ).df()
    except Exception:
        return  # parquet 直接读不动，也算被抓到
    with pytest.raises(AssertionError):
        assert_frame_equal(_norm(live), _norm(snap))


def test_missing_file_is_detected(manifest):
    """manifest 里记着但文件没了 —— 必须被 sha256 那条测出来。"""
    entry = manifest["tables"][0]
    ghost = bs.TABLES_DIR / "definitely_not_here.parquet"
    assert not ghost.exists()
    with pytest.raises(FileNotFoundError):
        bs._sha256(ghost)


# ======================================================================
# 网关后端开关
# ======================================================================


def test_gateway_defaults_to_snapshot_once_manifest_exists(monkeypatch):
    """manifest 一落地，网关默认后端就该是 snapshot —— 配置驱动，不用改代码。"""
    from gateway import backends

    monkeypatch.delenv("GENEBENCH_GATEWAY_BACKEND", raising=False)
    assert backends.SNAPSHOT_MANIFEST == bs.MANIFEST
    assert backends.default_backend() == "snapshot"


def test_gateway_can_read_from_the_snapshot_backend(monkeypatch):
    from fastapi.testclient import TestClient

    from gateway.app import app

    monkeypatch.setenv("GENEBENCH_GATEWAY_BACKEND", "snapshot")
    client = TestClient(app)
    r = client.get(
        "/adj",
        params={"as_of": cfg.FREEZE_DATE, "code": "600519.SH",
                "start_date": "2026-07-01", "end_date": "2026-07-31"},
    )
    assert r.status_code == 200, r.text[:300]
    assert r.json()["rows"] > 0


CAPTURE_TABLES = [
    s.dataset for s in v1_tables.V1_TABLES
    if lake.partition_semantics(s.dataset) == "capture_time"
]


@pytest.mark.parametrize("ds", CAPTURE_TABLES)
def test_growing_capture_table_snapshot_is_a_prefix_of_live(ds, con, manifest):
    """还在长的 capture_time 表：快照必须是 live 的**前缀**，不是等于它。

    `stock_basic` 每天全量抄一份，live 每过一天就多约 5,892 行。
    "同一查询两后端结果一致"对它只在快照那一瞬成立 —— 我第一版就是这么写的，
    过夜即红，而红的原因是"湖在正常工作"。

    正确的不变量有两条，缺一不可：
    1. **子集**：快照里的每一行都还在 live 里（湖没有回删/改写历史）；
    2. **不多**：快照没有 live 之外的行（不是我们自己造的数据）。
    """
    path = bs.TABLES_DIR / f"{ds}.parquet"
    # 比较列取该表的全部非审计列（`first_seen_at`/`last_seen_at` 是抓取时间戳，
    # 同一行在不同快照里会变，拿它比会把"抄了两次"误判成"内容变了"）。
    described = con.execute(
        f"DESCRIBE SELECT * FROM read_parquet('{path}')"  # noqa: S608
    ).df()
    cols = ", ".join(
        f'"{c}"' for c in described["column_name"]
        if c not in ("first_seen_at", "last_seen_at", "source")
    )
    only_in_snap = con.execute(
        f"SELECT count(*) FROM ("  # noqa: S608
        f"  SELECT DISTINCT {cols} FROM read_parquet('{path}') EXCEPT "
        f"  SELECT DISTINCT {cols} FROM \"{ds}\")"
    ).fetchone()[0]
    assert int(only_in_snap) == 0, (
        f"快照里有 {only_in_snap} 组 live 里没有的记录 —— "
        f"要么湖改写了历史，要么快照不是从这个湖来的"
    )
    assert len(CAPTURE_TABLES) >= 2, "capture_time 表少于 2 张？参数化没覆盖到"
    live_n = con.execute(f'SELECT count(*) FROM "{ds}"').fetchone()[0]  # noqa: S608
    snap_n = con.execute(
        f"SELECT count(*) FROM read_parquet('{path}')"  # noqa: S608
    ).fetchone()[0]
    assert snap_n <= live_n, "快照行数比 live 还多，方向反了"
    entry = next(t for t in manifest["tables"] if t["dataset"] == ds)
    assert entry["rows"] == snap_n, "manifest 与实际快照行数对不上"
