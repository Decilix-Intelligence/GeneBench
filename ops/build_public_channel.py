#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公开通道数据面的**一条命令**（卡 1.1-a）。

    cd $REPO && ulimit -n 8192 && $PY ops/build_public_channel.py            # 从零走完
    $PY ops/build_public_channel.py --step tables --step tradability          # 只跑某几步
    $PY ops/build_public_channel.py --dry-run                                 # 只说要做什么
    $PY ops/build_public_channel.py --step provider --force                   # 重跑某步

产出（**都不进 git**，每个目录带 `MANIFEST.sha256` + `build_info.json`）::

    $SNAPSHOTS/public_v1/tables/         网关后端读的表（6 张）
    $SNAPSHOTS/public_v1/tradability/    可交易性视图，按年分区
    $SNAPSHOTS/public_v1/qlib_provider/  冻结 qlib bin provider（8 字段）
    $SNAPSHOTS/public_v1/build/          中间产物（quotes.parquet），不是交付面
    $SNAPSHOTS/public_v1/state/          断点标记 `<step>.done`

**可续跑**：每步跑完写一个 `.done`（里面是这步的统计 JSON）。再跑一次时
已完成的步骤直接跳过 —— 拉数那步尤其重要：3,575 次请求打第三方免费服务，
「重跑一次全量」不是没有代价的事。

**不做的事**：本脚本不起网关、不跑 pytest、不碰私有通道的任何字节。
起公开网关走 `ops/public_gateway.sh`。
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import genebench_config as cfg          # noqa: E402
from snapshots import qlib_provider as qp      # noqa: E402
from snapshots.public import gates as G        # noqa: E402
from snapshots.public import source as S       # noqa: E402
from snapshots.public import tables as T       # noqa: E402

STEPS: tuple[str, ...] = ("fetch", "tables", "gate", "tradability", "provider", "verify")


def _state(step: str) -> pathlib.Path:
    return cfg.PUBLIC_STATE_DIR / f"{step}.done"


def done(step: str) -> bool:
    return _state(step).is_file()


def mark(step: str, payload: dict[str, Any]) -> None:
    cfg.create_dir(cfg.PUBLIC_STATE_DIR)
    p = _state(step)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                 encoding="utf-8")
    try:
        p.chmod(0o600)
    except OSError:                                        # pragma: no cover
        pass


# ---------------------------------------------------------------- 各步

def step_fetch(args) -> dict[str, Any]:
    """拉公开源：`stock_basic`（1 次）+ 复权因子（并集 3,575 次，可续跑）。

    日线不在这里拉 —— 那一轮是 N-68 做的，缓存在 `$GB/scratch/bs_cache`。
    交易时段拒绝启动这条判据在 `fetch_adj` / `fetch_basic` 里，不在这里重写第二份。
    """
    from snapshots.public import fetch_adj as FA
    from snapshots.public import fetch_basic as FB
    out = {"basic": FB.fetch(force=args.force_trading_hours)}
    out["adj"] = FA.fetch(S.union_codes(), force=args.force_trading_hours)
    return out


def step_tables(args) -> dict[str, Any]:
    stats = T.build_tables(verbose=True)
    info = T.write_manifest(T.TABLES_DIR, kind="public_v1/tables", extra={
        "tables": list(T.PUBLIC_TABLE_NAMES),
        "rows": {k: stats[k] for k in ("daily_rows", "suspend_rows", "limit_rows",
                                       "adj_rows", "calendar_days", "stock_basic_rows")},
        "codes": stats["codes"],
    })
    return {"stats": stats, "manifest": info}


def step_gate(args) -> dict[str, Any]:
    """**换源前置门**（B0②/B2）：`low <= amount/volume <= high` 的行占比 ≥ 99%。

    在公开 `daily` 全表上跑，不抽样 —— 抽样过了不等于全表过了，而单位错时
    这个比率是 **0%**，全表跑一次的代价只是几十秒。
    """
    import pyarrow.parquet as pq
    frame = pq.read_table(T.TABLES_DIR / "daily.parquet",
                          columns=["low", "high", "close", "volume", "amount"]).to_pandas()
    rep = G.assert_vwap_band(frame, source="baostock 公开源（公开 daily 全表）")
    return {"rows": rep.rows, "in_band": rep.in_band, "ratio": rep.ratio,
            "median_vwap_over_close": rep.median_vwap_over_close,
            "pre_close_source": G.PRE_CLOSE_SOURCE}


def step_tradability(args) -> dict[str, Any]:
    stats = T.build_tradability(verbose=True)
    info = T.write_manifest(T.TRADABILITY_DIR, kind="public_v1/tradability", extra={
        "rows": stats["rows"], "status_counts": stats["status_counts"],
        "years": sorted(stats["years"]),
    })
    return {"stats": stats, "manifest": info}


def step_provider(args) -> dict[str, Any]:
    """公开 qlib provider。**复用 `snapshots/qlib_provider.py` 的既有构建逻辑**，
    只把输入源与落点换成公开通道的（`qp.using("public")`）—— 不复制一份 builder。
    """
    import pyarrow.parquet as pq
    codes = set(pq.read_table(T.TABLES_DIR / "daily.parquet",
                              columns=["ts_code"]).column("ts_code").to_pylist())
    with qp.using("public"):
        manifest = qp.build(verbose=True, restrict=codes)
        card = qp.render_data_card(manifest)
    info = T.write_manifest(cfg.PUBLIC_PROVIDER_DIR, kind="public_v1/qlib_provider", extra={
        "fields": list(qp.FIELDS),
        "codes_with_features": manifest["features"]["codes"],
        "files_sha256_digest": manifest["digest"]["files_sha256_digest"],
        "instruments": manifest["instruments"]["files"],
    })
    return {"digest": manifest["digest"], "calendar": manifest["calendar"],
            "instruments": manifest["instruments"], "data_card": str(card),
            "manifest": info}


def step_verify(args) -> dict[str, Any]:
    """出集自检。**只问能被证伪的问题**，答不上来就红。"""
    import pyarrow.parquet as pq
    out: dict[str, Any] = {}
    tables = {}
    for name in T.PUBLIC_TABLE_NAMES:
        p = T.TABLES_DIR / f"{name}.parquet"
        if not p.is_file():
            raise SystemExit(f"[红] 缺表 {p}")
        tables[name] = pq.read_metadata(p).num_rows
    out["table_rows"] = tables

    # ① 冻结线：任何一张表都不许有冻结线之后的行（红线 7 的结构保证）
    freeze = cfg.FREEZE_DATE.replace("-", "")
    for name, col in (("daily", "trade_date"), ("adj_factor", "trade_date"),
                      ("stk_limit", "trade_date"), ("suspend_d", "trade_date"),
                      ("trade_cal", "cal_date")):
        mx = max(pq.read_table(T.TABLES_DIR / f"{name}.parquet",
                               columns=[col]).column(col).to_pylist())
        if mx > freeze:
            raise SystemExit(f"[红] {name}.{col} 最大值 {mx} 越过冻结线 {freeze}")
        out[f"max_{name}"] = mx

    # ② provider 日历上界 == 冻结线，且没有 day_future.txt
    cal = (cfg.PUBLIC_PROVIDER_DIR / "calendars" / "day.txt").read_text(
        encoding="utf-8").split()
    out["provider_calendar_days"] = len(cal)
    out["provider_calendar_end"] = cal[-1]
    if cal[-1].replace("-", "") != freeze:
        raise SystemExit(f"[红] 公开 provider 日历上界 {cal[-1]} != 冻结线")
    if (cfg.PUBLIC_PROVIDER_DIR / "calendars" / "day_future.txt").exists():
        raise SystemExit("[红] 公开 provider 出现 day_future.txt —— 那是「允许求值到未来」的开关")

    # ③ 两条通道**并列不覆盖**：私有产物的 mtime 不该被本次构建碰过
    out["private_untouched"] = {
        "qlib_provider_manifest": (cfg.SNAPSHOTS_V1 / "qlib_provider" / "manifest.json").stat().st_mtime,
        "tables_manifest": (cfg.SNAPSHOTS_V1 / "tables" / "manifest.json").stat().st_mtime,
    }
    return out


HANDLERS = {"fetch": step_fetch, "tables": step_tables, "gate": step_gate,
            "tradability": step_tradability, "provider": step_provider,
            "verify": step_verify}


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description="建公开通道的数据面（可续跑）")
    ap.add_argument("--step", action="append", choices=STEPS, default=None,
                    help="只跑这些步（可给多次）。不给 = 全部，按 STEPS 顺序")
    ap.add_argument("--dry-run", action="store_true", help="只说要做什么，不动手")
    ap.add_argument("--force", action="store_true", help="忽略 .done，重跑选中的步")
    ap.add_argument("--force-trading-hours", action="store_true",
                    help="**明知在交易时段仍要拉数**（只影响 fetch 步）")
    a = ap.parse_args(argv)
    cfg.harden_umask()
    steps = a.step or list(STEPS)

    print(f"通道 public · 落点 {cfg.SNAPSHOTS_PUBLIC} · 冻结线 {cfg.FREEZE_DATE}")
    for s in steps:
        state = "已完成（跳过）" if done(s) and not a.force else "要跑"
        print(f"  [{state}] {s}")
    if a.dry_run:
        print("--dry-run：什么都没做")
        return 0

    results: dict[str, Any] = {}
    for s in steps:
        if done(s) and not a.force:
            print(f"\n=== {s}：已完成，跳过（要重跑加 --force）===", flush=True)
            continue
        print(f"\n=== {s} ===", flush=True)
        t0 = time.time()
        payload = HANDLERS[s](a)
        payload["seconds"] = round(time.time() - t0, 1)
        mark(s, payload)
        results[s] = payload
        print(f"--- {s} 完成，{payload['seconds']:.1f} 秒 ---", flush=True)
    print("\n" + json.dumps(results, ensure_ascii=False, indent=2, default=str)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
