# -*- coding: utf-8 -*-
"""卡 1.4：把 v1 依赖表冻到 ``$SNAPSHOTS/v1/tables/``。

用法::

    cd $REPO && ulimit -n 8192 && $GENEBENCH_ROOT/env/bin/python -m snapshots.build_snapshot

三条设计约束，每条都有踩过的坑做背书：

1. **另起子目录。** 落 ``tables/`` 而不是 ``v1/`` 根下 —— ``v1/`` 里已经躺着
   卡 1.1 的 ``universe/`` 与卡 1.2 的 ``tradability/``，manifest 混进去会
   把它们一起算成"v1 依赖表快照"（tickets N-14 特意点过这一条）。

2. **冻结线含边界当天。** ``<= 2026-07-31``，不是 ``<``。

3. **三大报表不能只按 ``ann_date`` 截。** 网关判可见性用的是 ``f_ann_date``
   （实测同季有 14 行两者不等，且 ``ann_date`` 更早），两列不保证同序。
   只按 ``ann_date`` 截，理论上会丢掉 ``ann_date > 冻结线`` 而
   ``f_ann_date <= 冻结线`` 的行 —— 那正是"本该可见却被静默丢掉"。
   所以报表类用 ``ann_date <= L OR f_ann_date <= L``（超集），
   真正的 PIT 过滤留给网关。``verify_statement_bound()`` 会实测这个风险有多大。

COPY 走**独立的只读连接**，不经 `lake.query()` —— 它的语句白名单会拦 COPY，
那是承重的红线防线（卡 0.2 的 D6 实测过：把 copy 放进白名单，
``COPY (SELECT 1) TO '/tmp/x.csv'`` 真的会落一个 4 字节文件）。**不要为了图省事去放松它。**
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

import duckdb

import genebench_config as cfg
from snapshots import lake, v1_tables

TABLES_DIR: Path = cfg.SNAPSHOTS / cfg.SNAPSHOT_VERSION / "tables"
MANIFEST: Path = TABLES_DIR / "manifest.json"
FREEZE: str = lake.FREEZE_DATE_COMPACT

#: 三大报表（含 vip）——截断口径特殊，见模块 docstring 第 3 条。
STATEMENTS: frozenset[str] = frozenset(
    {"income", "income_vip", "balancesheet", "balancesheet_vip",
     "cashflow", "cashflow_vip"}
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def where_clause(spec: v1_tables.TableSpec) -> str:
    """这张表的冻结线截断条件。空串 = 全量拷。

    三类不截：

    - **无日期列**（stock_basic / index_member_all / index_basic）。
    - **capture_time 语义**（分区键是 ``snapshot_date`` = "我们哪天抄的表"）。
      典型是 ``trade_cal``：它的 ``cal_date`` 覆盖到 2026-12-31，那是**预写的
      未来日历**，在冻结时点就已经合法存在。按 ``cal_date`` 截会把未来日历
      整段砍掉 —— 而 T+N 对齐正需要它。这与卡 0.2 补救 D3 立的规矩同源：
      capture_time 表的时间语义不在它的日期列上。
      （首版我按 ``cal_date`` 截了，双后端一致性当场炸出 6574 vs 6421。）
    - 报表类走**超集**口径，见模块 docstring 第 3 条。
    """
    col = spec.date_column
    if col is None:
        return ""
    if lake.partition_semantics(spec.dataset) == "capture_time":
        return ""
    if spec.dataset in STATEMENTS:
        # 超集：两列任一在线内就留。真正的 PIT 由网关按 f_ann_date 判。
        return f"WHERE ({col} <= '{FREEZE}' OR f_ann_date <= '{FREEZE}')"
    return f"WHERE {col} <= '{FREEZE}'"


def build_one(con: duckdb.DuckDBPyConnection, spec: v1_tables.TableSpec) -> dict[str, Any]:
    ds = spec.dataset
    target = TABLES_DIR / f"{ds}.parquet"
    clause = where_clause(spec)
    con.execute(
        f"COPY (SELECT * FROM \"{ds}\" {clause}) TO '{target}' "  # noqa: S608
        f"(FORMAT PARQUET, COMPRESSION ZSTD)"
    )
    target.chmod(0o600)

    src_rows = con.execute(f'SELECT count(*) FROM "{ds}"').fetchone()[0]  # noqa: S608
    snap_rows = con.execute(
        f"SELECT count(*) FROM read_parquet('{target}')"  # noqa: S608
    ).fetchone()[0]
    entry: dict[str, Any] = {
        "dataset": ds,
        "path": target.name,
        "sha256": _sha256(target),
        "bytes": target.stat().st_size,
        "rows": int(snap_rows),
        "source_rows": int(src_rows),
        "date_column": spec.date_column,
        "where": clause or None,
        "truncated_by_freeze_line": bool(clause),
        "partition_semantics": lake.partition_semantics(ds),
        "used_by_cards": list(spec.used_by_cards),
    }
    if spec.date_column:
        rng = con.execute(
            f"SELECT min({spec.date_column}), max({spec.date_column}) "  # noqa: S608
            f"FROM read_parquet('{target}')"
        ).fetchone()
        entry["snapshot_min_date"] = str(rng[0]) if rng[0] is not None else None
        entry["snapshot_max_date"] = str(rng[1]) if rng[1] is not None else None
        srng = con.execute(
            f'SELECT max({spec.date_column}) FROM "{ds}"'  # noqa: S608
        ).fetchone()
        entry["source_max_date"] = str(srng[0]) if srng[0] is not None else None
    return entry


def verify_statement_bound(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """实测"只按 ann_date 截会丢多少本该可见的行"。

    这不是装饰 —— 它是模块 docstring 第 3 条那个判断的**证据**。
    若哪天结果不再是 0，说明两列的序关系变了，超集口径就从"保险"变成"必需"。
    """
    out: dict[str, Any] = {}
    for ds in sorted(STATEMENTS):
        row = con.execute(
            f"SELECT count(*) FROM \"{ds}\" "  # noqa: S608
            f"WHERE f_ann_date IS NOT NULL AND f_ann_date <= '{FREEZE}' "
            f"AND (ann_date IS NULL OR ann_date > '{FREEZE}')"
        ).fetchone()
        out[ds] = int(row[0])
    return out


def stalled_from_baseline() -> tuple[list[dict[str, Any]], set[str]]:
    """把卡 0.2 基线里的停更表清单带进 manifest。返回 ``(明细, 名字集合)``。

    ``freeze_line_ok`` 与"这张表还活着"是两个信号，卡 0.2 的 D3 就是栽在
    把它们渲染成同一种绿。快照 manifest 必须把停更状态原样带出来。

    ⚠️ 第一版我写成 ``sorted(str(x) for x in stalled)`` —— 基线里
    ``stalled_tables`` 是**一串 dict**（每条带 lag_days / freshness_source /
    why_it_looks_green），被我 str() 成了一串 dict 的字面量。后果是
    ``entry["source_stalled"]`` 恒为 False，而配套那条测试因为两边都空
    **恒真通过**。又一个自证式的假绿 —— 现在明细原样保留，名字单独抽一份。
    """
    path = cfg.OPS / "lake_baseline.json"
    if not path.exists():
        return [], set()
    data = json.loads(path.read_text(encoding="utf-8"))
    raw = data.get("summary", {}).get("stalled_tables") or []
    details: list[dict[str, Any]] = []
    names: set[str] = set()
    for item in raw:
        if isinstance(item, dict):
            details.append(item)
            if item.get("dataset"):
                names.add(str(item["dataset"]))
        else:
            names.add(str(item))
            details.append({"dataset": str(item)})
    details.sort(key=lambda d: d.get("dataset", ""))
    return details, names


def build() -> dict[str, Any]:
    cfg.harden_umask()
    cfg.create_dir(TABLES_DIR)
    lake.raise_open_file_limit()
    specs = v1_tables.V1_TABLES
    stalled_details, stalled = stalled_from_baseline()
    entries: list[dict[str, Any]] = []
    # 湖是**活的**：datahub 的 ETL 会周期性持写锁（实测撞到过 PID 256892）。
    # 默认 5 次 ×1s 对一次跑批太短，这里给到 40 次 ×15s ≈ 10 分钟。
    with lake.catalog(retries=40, retry_wait=15.0) as con:
        bound_risk = verify_statement_bound(con)
        for spec in specs:
            entry = build_one(con, spec)
            entry["source_stalled"] = spec.dataset in stalled
            entries.append(entry)
    manifest = {
        "snapshot_version": cfg.SNAPSHOT_VERSION,
        "freeze_line": cfg.FREEZE_DATE,
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(
            timespec="seconds"
        ),
        "table_count": len(entries),
        "total_rows": sum(e["rows"] for e in entries),
        "total_bytes": sum(e["bytes"] for e in entries),
        "stalled_datasets": sorted(stalled),
        "stalled_tables": stalled_details,
        "statement_bound_risk": {
            "question": (
                "只按 ann_date 截断，会丢掉多少 f_ann_date <= 冻结线 但 "
                "ann_date > 冻结线 的行（= 本该可见却被静默丢掉）"
            ),
            "measured": bound_risk,
            "mitigation": "报表类用 (ann_date <= L OR f_ann_date <= L) 超集口径",
        },
        "tables": entries,
    }
    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    MANIFEST.chmod(0o600)
    return manifest


def read_manifest() -> dict[str, Any]:
    if not MANIFEST.exists():
        raise FileNotFoundError(f"没有 manifest：{MANIFEST}。先跑 python -m snapshots.build_snapshot")
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def main() -> int:
    m = build()
    print(
        f"表 {m['table_count']} 张 / 行 {m['total_rows']:,} / "
        f"{m['total_bytes'] / 2**30:.2f} GiB → {TABLES_DIR}"
    )
    print("停更表：", ", ".join(m["stalled_datasets"]) or "(无)")
    print("报表截断风险实测：", m["statement_bound_risk"]["measured"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
