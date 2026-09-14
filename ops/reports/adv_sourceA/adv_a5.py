"""对抗审查 源A 探针 5：DATE/VARCHAR 类型陷阱实证 / 34 例停牌后掉出的去向 / 出场侧滞后 / 数据卡口径核对。"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from collections import defaultdict

os.umask(0o077)
sys.path.insert(0, "/data/shared/genebench/repo")
import duckdb  # noqa: E402
import genebench_config as cfg  # noqa: E402
from snapshots import lake  # noqa: E402

OUT = {}
lake.raise_open_file_limit()
gold = str(cfg.GOLD / "index_weight")

# ---------- 1. 裸 gold(DATE)vs 视图(VARCHAR)：冻结线过滤会怎样 ----------
c = duckdb.connect(":memory:")
c.execute("SET threads=4")
t = {}
one = c.execute(f"SELECT * FROM read_parquet('{gold}/*/*.parquet') LIMIT 1").df()  # noqa: S608
t["gold_columns"] = list(one.columns)
t["gold_row_sample"] = one.astype(str).to_dict("records")
t["gold_typeof"] = c.execute(
    f"SELECT typeof(trade_date) td, typeof(index_code) ic, typeof(con_code) cc "  # noqa: S608
    f"FROM read_parquet('{gold}/*/*.parquet') LIMIT 1"
).df().to_dict("records")
# 文件内部到底有没有 trade_date 列？
import glob  # noqa: E402

f0 = sorted(glob.glob(f"{gold}/*/*.parquet"))[0]
t["single_file_columns"] = list(
    c.execute(f"SELECT * FROM read_parquet('{f0}') LIMIT 1").df().columns  # noqa: S608
)
t["hive_partition_only"] = "trade_date" not in t["single_file_columns"]

for expr, label in [
    ("trade_date <= '20260731'", "compact_string_bound"),
    ("trade_date <= '2026-07-31'", "iso_string_bound"),
    ("trade_date <= DATE '2026-07-31'", "date_bound"),
]:
    try:
        n = int(
            c.execute(
                f"SELECT count(*) n FROM read_parquet('{gold}/*/*.parquet') WHERE {expr}"  # noqa: S608
            ).fetchone()[0]
        )
        t[f"filter_{label}"] = {"rows": n}
    except Exception as e:  # noqa: BLE001
        t[f"filter_{label}"] = {"error": type(e).__name__ + ": " + str(e)[:200]}
try:
    t["cast_compact_to_date"] = str(
        c.execute("SELECT CAST('20260731' AS DATE) d").fetchone()[0]
    )
except Exception as e:  # noqa: BLE001
    t["cast_compact_to_date"] = "ERROR " + type(e).__name__ + ": " + str(e)[:160]
c.close()
OUT["type_trap"] = t

# ---------- 2. 停牌后掉出的 34 例：去向 ----------
with lake.catalog() as con:
    raw = lake.query(
        "SELECT index_code, con_code, trade_date FROM index_weight "
        "WHERE index_code = '000300.SH' AND trade_date <= ? ",
        [lake.FREEZE_DATE_COMPACT],
        conn=con,
    )
    members = defaultdict(set)
    for c2, td in zip(raw["con_code"], raw["trade_date"]):
        members[str(td)].add(str(c2))
    dts = sorted(members)
    ph = ",".join("?" * len(dts))
    dl = lake.query(
        f"SELECT trade_date, ts_code FROM daily WHERE trade_date IN ({ph})",  # noqa: S608
        dts,
        conn=con,
    )
    traded = defaultdict(set)
    for td, ts in zip(dl["trade_date"], dl["ts_code"]):
        traded[str(td)].add(str(ts))

    dropped = []
    for k, d in enumerate(dts[:-1]):
        nq = members[d] - traded.get(d, set())
        nxt = members[dts[k + 1]]
        for cc in sorted(nq - nxt):
            dropped.append((d, cc))
    codes = sorted({cc for _, cc in dropped})
    ph2 = ",".join("?" * len(codes))
    sb = lake.query(
        f"SELECT ts_code, name, list_status, delist_date FROM stock_basic "  # noqa: S608
        f"WHERE ts_code IN ({ph2})",
        codes,
        conn=con,
    ).drop_duplicates("ts_code")
    sbmap = {
        str(a): (str(b), str(cc), str(dd))
        for a, b, cc, dd in zip(sb["ts_code"], sb["name"], sb["list_status"], sb["delist_date"])
    }

fate = []
pos = {d: i for i, d in enumerate(dts)}
for d, cc in dropped:
    later = [x for x in dts if x > d and cc in members[x]]
    fate.append(
        {
            "drop_after_snapshot": d,
            "code": cc,
            "name": sbmap.get(cc, ("?",))[0],
            "list_status": sbmap.get(cc, ("?", "?"))[1],
            "delist_date": sbmap.get(cc, ("?", "?", "?"))[2],
            "returned_at": later[0] if later else None,
            "gap_periods": (pos[later[0]] - pos[d] - 1) if later else None,
        }
    )
OUT["suspended_then_dropped_fate"] = {
    "n": len(fate),
    "n_never_returned": sum(1 for f in fate if f["returned_at"] is None),
    "n_returned_within_1_period": sum(
        1 for f in fate if f["gap_periods"] is not None and f["gap_periods"] <= 1
    ),
    "n_returned_within_6_periods": sum(
        1 for f in fate if f["gap_periods"] is not None and f["gap_periods"] <= 6
    ),
    "detail": fate,
}

# ---------- 3. qlib 出场侧滞后 + 切点粒度（核对数据卡口径）----------
root = cfg.QLIB_RELEASE / "instruments"
with lake.catalog() as con:
    cal = [
        str(x)
        for x in lake.query(
            "SELECT cal_date FROM trade_cal WHERE is_open = 1 AND cal_date <= ? "
            "ORDER BY cal_date",
            [lake.FREEZE_DATE_COMPACT],
            conn=con,
        )["cal_date"].tolist()
    ]
    rawall = lake.query(
        "SELECT index_code, trade_date FROM index_weight WHERE trade_date <= ?",
        [lake.FREEZE_DATE_COMPACT],
        conn=con,
    )
snaps_by_uni = {
    u: sorted(set(rawall.loc[rawall["index_code"] == cfg.UNIVERSE_INDEX_CODE[u], "trade_date"].astype(str)))
    for u in cfg.UNIVERSES
}
calset = set(cal)

qq = {}
for uni in cfg.UNIVERSES:
    p = root / f"{uni}.txt"
    per = defaultdict(list)
    for ln in p.read_text().splitlines():
        if not ln.strip():
            continue
        cd, s, e = ln.split("\t")[:3]
        per[f"{cd[2:]}.{cd[:2]}"].append((s, e))
    merged = defaultdict(list)
    for cd, segs in per.items():
        segs.sort()
        cs, ce = segs[0]
        for s, e in segs[1:]:
            if dt.date.fromisoformat(s) == dt.date.fromisoformat(ce) + dt.timedelta(days=1):
                ce = max(ce, e)
            else:
                merged[cd].append((cs, ce))
                cs, ce = s, e
        merged[cd].append((cs, ce))
    snaps = snaps_by_uni[uni]
    snapset = set(snaps)
    first, last = snaps[0], snaps[-1]

    # 数据卡口径：distinct start 里有多少是快照日 / 交易日
    starts = sorted({s.replace("-", "") for segs in per.values() for s, _ in segs})
    qq[uni] = {
        "n_distinct_starts_all_lines": len(starts),
        "n_distinct_starts_on_snapshot": sum(1 for s in starts if s in snapset),
        "n_distinct_starts_not_trading_day": sum(1 for s in starts if s not in calset),
    }
    # 出场侧滞后：qlib end（非末端）→ 源A 会拖到下一期快照的前一交易日
    exlags = []
    qlib_max_end = max(e for segs in per.values() for _, e in segs)
    for cd, segs in merged.items():
        for s, e in segs:
            ce = e.replace("-", "")
            if e == qlib_max_end:
                continue  # 右截断段，源A 也是 NULL
            if not (first <= ce <= last):
                continue
            nxt = [d for d in snaps if d > ce]
            if not nxt:
                continue
            # 源A 的 out_date = prev_trading_day(nxt[0])
            i = cal.index(nxt[0])
            a_out = cal[i - 1]
            exlags.append(
                (dt.date.fromisoformat(f"{a_out[:4]}-{a_out[4:6]}-{a_out[6:]}")
                 - dt.date.fromisoformat(e)).days
            )
    exlags.sort()
    qq[uni]["exit_lag_days_A_minus_B"] = {
        "n": len(exlags),
        "min": exlags[0] if exlags else None,
        "p50": exlags[len(exlags) // 2] if exlags else None,
        "p90": exlags[int(len(exlags) * 0.9)] if exlags else None,
        "max": exlags[-1] if exlags else None,
        "mean": round(sum(exlags) / len(exlags), 1) if exlags else None,
        "n_negative": sum(1 for x in exlags if x < 0),
    }
OUT["qlib_exit_lag_and_card_check"] = qq

print(json.dumps(OUT, ensure_ascii=False, indent=1, default=str))
