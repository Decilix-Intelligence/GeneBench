"""补证：18 个 entry 标记里两只新股的上市日；1309 个无行情样本的 suspend_d 覆盖率。"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

os.umask(0o077)
sys.path.insert(0, "/data/shared/genebench/repo")
import genebench_config as cfg  # noqa: E402
from snapshots import lake  # noqa: E402

OUT = {}
lake.raise_open_file_limit()
with lake.catalog() as con:
    OUT["list_dates"] = lake.query(
        "SELECT ts_code, name, list_date, list_status FROM stock_basic "
        "WHERE ts_code IN ('601668.SH','601618.SH','002075.SZ','600001.SH','600357.SH')",
        conn=con,
    ).drop_duplicates("ts_code").astype(str).to_dict("records")

    raw = lake.query(
        "SELECT con_code, trade_date FROM index_weight "
        "WHERE index_code = '000300.SH' AND trade_date <= ?",
        [lake.FREEZE_DATE_COMPACT],
        conn=con,
    )
    members = defaultdict(set)
    for c, td in zip(raw["con_code"], raw["trade_date"]):
        members[str(td)].add(str(c))
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
    sd = lake.query(
        f"SELECT trade_date, ts_code, suspend_type FROM suspend_d "  # noqa: S608
        f"WHERE trade_date IN ({ph})",
        dts,
        conn=con,
    )
    susp = defaultdict(dict)
    for td, ts, st in zip(sd["trade_date"], sd["ts_code"], sd["suspend_type"]):
        susp[str(td)][str(ts)] = str(st)

n = 0
flags = defaultdict(int)
for d in dts:
    for c in members[d] - traded.get(d, set()):
        n += 1
        flags[susp.get(d, {}).get(c, "<no suspend_d row>")] += 1
OUT["no_quote_suspend_flag_breakdown"] = {"total": n, "by_flag": dict(flags)}

# 18 个 entry 标记的 code 在 20091231 之前是否曾出现在 csi300 名单里
entry_codes = ["000631.SZ", "000780.SZ", "002007.SZ", "002275.SZ", "600062.SH",
               "600161.SH", "600166.SH", "600239.SH", "600246.SH", "600312.SH",
               "600369.SH", "600517.SH", "600648.SH", "600657.SH", "601099.SH",
               "601107.SH", "601618.SH", "601668.SH"]
OUT["entry_flag_codes_history"] = {
    c: {
        "ever_member_before_20091231": sorted(
            d for d in dts if d < "20091231" and c in members[d]
        )[-3:],
        "in_20091130": c in members["20091130"],
    }
    for c in entry_codes
}
print(json.dumps(OUT, ensure_ascii=False, indent=1, default=str))
