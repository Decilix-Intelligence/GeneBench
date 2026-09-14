# -*- coding: utf-8 -*-
"""公开源的 `stock_basic` 全量拉取（卡 1.1-a）。

    $PY -m snapshots.public.fetch_basic [--force]

**一次请求**拿全市场（实测 8,940 行 / 36.9 秒，含指数与基金，本模块不筛，
筛在 `source.read_basic()` 里按 `type=1` 做）。上市日（`ipoDate`）是
§3 涨跌停推导里「新股前 N 个交易日无限制」那条规则的唯一输入。

约束与 `fetch_adj` 同一份（都从 `ops/acceptance/card_2_5_fetch_union.py` import）：
北京时间工作日 09:00–15:30 拒绝启动；缓存在即跳过。
"""
from __future__ import annotations

import argparse
import sys

import pandas as pd

import genebench_config as cfg
from snapshots.public import fetch_adj as FA
from snapshots.public import source as S

FIELDS = ("code", "code_name", "ipoDate", "outDate", "type", "status")


def fetch(*, force: bool = False, refresh: bool = False) -> dict:
    if S.BASIC_CACHE.is_file() and not refresh:
        n = len(pd.read_parquet(S.BASIC_CACHE))
        print(f"已有缓存 {S.BASIC_CACHE}（{n} 行）—— 跳过", flush=True)
        return {"rows": n, "cached": True}
    u = FA._union_module()
    try:
        u.assert_not_trading_hours()
    except u.TradingHours as e:
        if not force:
            raise
        print(f"[黄] --force：{e}", file=sys.stderr, flush=True)

    sys.path.insert(0, FA.bsx_path())
    import baostock as bs

    lg = bs.login()
    if lg.error_code != "0":
        raise RuntimeError(f"baostock login 失败：{lg.error_code} {lg.error_msg}")
    try:
        r = bs.query_stock_basic()
        if r.error_code != "0":
            raise RuntimeError(f"query_stock_basic 失败：{r.error_code} {r.error_msg}")
        rows = []
        while r.next():
            rows.append(r.get_row_data())
    finally:
        bs.logout()
    if not rows:
        # 零行**不是**「拉到了」—— 落一个空表下去，后面每一条上市日判定都会静默走偏。
        raise RuntimeError("query_stock_basic 返回 0 行 —— 不落盘，停下")
    frame = pd.DataFrame(rows, columns=list(FIELDS))
    cfg.create_dir(S.BASIC_CACHE.parent)
    frame.to_parquet(S.BASIC_CACHE, index=False)
    S.BASIC_CACHE.chmod(0o600)
    print(f"stock_basic → {S.BASIC_CACHE}（{len(frame)} 行）", flush=True)
    return {"rows": len(frame), "cached": False}


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description="拉 baostock stock_basic 全量")
    ap.add_argument("--force", action="store_true", help="**明知在交易时段仍要跑**")
    ap.add_argument("--refresh", action="store_true", help="已有缓存也重拉")
    a = ap.parse_args(argv)
    cfg.harden_umask()
    fetch(force=a.force, refresh=a.refresh)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
