# -*- coding: utf-8 -*-
"""卡 2.5 §10 的对账（B5 的第一阶段）：**公开源 vs 私有湖，逐值比对**。

**为什么先做抽样而不是全量**：全窗口全市场是 **5,817 只 × 4,269 个交易日**，
实测单只全历史查询 **7.1 秒** ⇒ 全量约 **11.5 小时、5,817 次请求**打在一个免费 API 上。
那是一个需要签字人拍板的量（时间 + 对方负载），已登记 N-68。
**抽样先跑，是为了在花那 11.5 小时之前，先知道会不会有系统性差异。**

抽样按板块分层、种子固定，**可续跑**（逐票落 parquet，重跑跳过已有）。

用法：`python ops/acceptance/card_2_5_source_reconcile.py [N]`（默认 200 只）
"""
from __future__ import annotations

import os
import pathlib
import random
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
sys.path.insert(0, "/tmp/bsx/baostock-0.9.3")     # 未装进 env 的临时解包；见 N-66

import pandas as pd

from snapshots import lake

FIELDS = "date,code,open,high,low,close,preclose,volume,amount,turn,tradestatus,isST"

#: **baostock 不服务北交所。** 实测：`920xxx.BJ` 一律返回
#: `10004011 股票代码未标识sh或sz`（200 只抽样里 14 只全部落空）。
#: 私有湖有北交所（2026-07 有 7,518 行 stk_limit）。这是公开通道的一个**真缺口**，
#: 见 N-70：v1 的三个 universe（csi300/500/1000）全是沪深，因此不阻塞；
#: 但 `all` 这个 universe 在公开通道上**不等于**私有通道的 `all`。
BAOSTOCK_HAS_NO_BSE: bool = True
START, END = "2009-01-05", "2026-07-31"
CACHE = pathlib.Path(os.environ.get("RECON_CACHE", "/data/shared/genebench/scratch/bs_cache"))
#: 逐字段的比对口径。价格比到**分**；量额是浮点，比**相对差**。
PRICE_FIELDS = ("open", "high", "low", "close", "preclose")
VOLUME_FIELDS = ("volume", "amount")
REL_TOL = 1e-6


def to_bs(ts_code: str) -> str:
    num, ex = ts_code.split(".")
    return {"SH": "sh", "SZ": "sz", "BJ": "bj"}[ex] + "." + num


def _gold(dataset: str) -> str:
    """`read_parquet` 的 glob。**刻意不走 catalog** —— catalog 的只读锁与 19 个爬虫争，
    实测这里就撞上过（`Conflicting lock is held ... by user ljn`）。
    `lake.needs_catalog()` 正是为这件事存在的：读 parquet 不需要 catalog（N-42）。"""
    return str(lake.gold_dir(dataset) / "**" / "*.parquet")


def pick(n: int) -> list[str]:
    codes = lake.query(
        f"SELECT DISTINCT ts_code FROM read_parquet('{_gold('stock_basic')}', "
        f"hive_partitioning=true) WHERE list_status='L'")["ts_code"].tolist()
    groups = {"main": [c for c in codes if c.startswith(("60", "00"))],
              "chinext": [c for c in codes if c.startswith("30")],
              "star": [c for c in codes if c.startswith("68")],
              "bse": [c for c in codes if c.startswith(("4", "8", "92"))]}
    random.seed(20260905)
    out: list[str] = []
    for k, pool in groups.items():
        share = max(1, round(n * len(pool) / len(codes)))
        out += random.sample(sorted(pool), min(share, len(pool)))
    return sorted(out)[:n]


def fetch(code: str) -> pd.DataFrame | None:
    import baostock as bs
    f = CACHE / f"{code}.parquet"
    if f.exists():
        return pd.read_parquet(f)
    r = bs.query_history_k_data_plus(to_bs(code), FIELDS, start_date=START, end_date=END,
                                     frequency="d", adjustflag="3")
    if r.error_code != "0":
        print(f"  [跳过] {code}: {r.error_code} {r.error_msg}", flush=True)
        return None
    rows = []
    while r.next():
        rows.append(r.get_row_data())
    df = pd.DataFrame(rows, columns=FIELDS.split(","))
    df.to_parquet(f, index=False)
    f.chmod(0o600)                          # 红线 5：umask 002 下 to_parquet 落 0664
    return df


def main(argv=None) -> int:
    import baostock as bs
    n = int((argv or sys.argv[1:] or ["200"])[0])
    CACHE.mkdir(parents=True, exist_ok=True)
    CACHE.chmod(0o700)
    codes = pick(n)
    print(f"抽样 {len(codes)} 只（按板块分层，种子固定）", flush=True)
    lg = bs.login()
    assert lg.error_code == "0", (lg.error_code, lg.error_msg)
    t0 = time.time()
    got = {}
    for i, c in enumerate(codes, 1):
        d = fetch(c)
        if d is not None and len(d):
            got[c] = d
        if i % 20 == 0:
            print(f"  {i}/{len(codes)}  已取 {sum(len(x) for x in got.values())} 行  "
                  f"{time.time()-t0:.0f}s", flush=True)
    bs.logout()

    pub = pd.concat([d.assign(ts_code=c) for c, d in got.items()], ignore_index=True)
    for col in PRICE_FIELDS + VOLUME_FIELDS + ("turn",):
        pub[col] = pd.to_numeric(pub[col], errors="coerce")
    pub["trade_date"] = pub["date"].str.replace("-", "", regex=False)
    print(f"公开源合计 {len(pub)} 行 / {pub.ts_code.nunique()} 只", flush=True)

    want = "', '".join(sorted(pub.ts_code.unique()))
    # gold parquet 里 `trade_date` 是 **DATE**（catalog 视图对外是 VARCHAR）——
    # 直接拿 'YYYYMMDD' 比会抛 ConversionException。统一在 SQL 里转成紧凑串。
    priv = lake.query(
        f"""SELECT strftime(trade_date, '%Y%m%d') AS trade_date, ts_code,
                   open, high, low, close, pre_close AS preclose, volume, amount
            FROM read_parquet('{_gold('daily')}', hive_partitioning=true)
            WHERE ts_code IN ('{want}')
              AND trade_date BETWEEN DATE '{START}' AND DATE '{END}'""")
    print(f"私有湖 {len(priv)} 行 / {priv.ts_code.nunique()} 只", flush=True)

    m = pub.merge(priv, on=["trade_date", "ts_code"], how="outer",
                  suffixes=("_pub", "_priv"), indicator=True)
    print("\n=== 行集合 ===")
    print(m._merge.value_counts().to_string())
    susp = m[(m._merge == "left_only")]
    if len(susp):
        print("  只在公开源里的行，tradestatus 分布：",
              susp.tradestatus.value_counts().head().to_dict())

    both = m[m._merge == "both"]
    print(f"\n=== 逐字段比对（共有的 {len(both)} 行）===")
    for f in PRICE_FIELDS:
        a, b = both[f + "_pub"], both[f + "_priv"]
        ok = (a.round(2) == b.round(2)) | (a.isna() & b.isna())
        print(f"  {f:<9} 一致 {ok.mean():.8f}  不一致 {int((~ok).sum())}")
    for f in VOLUME_FIELDS:
        a, b = both[f + "_pub"].astype("float64"), both[f + "_priv"].astype("float64")
        den = b.abs().clip(lower=1.0)
        rel = (a - b).abs() / den
        ok = (rel <= REL_TOL) | (a.isna() & b.isna())
        print(f"  {f:<9} 一致 {ok.mean():.8f}（相对 {REL_TOL:g}）  不一致 {int((~ok).sum())}"
              f"  最大相对差 {rel.max():.3g}")
    both.to_parquet(CACHE.parent / "b5_recon_both.parquet", index=False)
    m[m._merge != "both"].to_parquet(CACHE.parent / "b5_recon_diff.parquet", index=False)
    print("\n落盘 b5_recon_both.parquet / b5_recon_diff.parquet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
