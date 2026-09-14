#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""形态 B 的取数半段：**复用** `ops/acceptance/card_2_5_fetch_union.py`，不抄第二份。

那个脚本已经把四条约束（按名单分批 / 每请求留间隔 / **非交易时段** / 缓存续跑）
写死在里面了，其中「交易时段拒绝启动」是**硬判据**。抄一份就等于给自己留了一个
可以悄悄放宽的副本 —— 所以这里只做两件事：

1. 把它的两个模块级路径（`UNION` 名单、`CACHE` 缓存目录）改指到用户机器上的位置；
2. 顺带把 `snapshots.public.fetch_adj` / `fetch_basic` 也跑一遍
   （复权因子与 `stock_basic`，它们自己读 `$GENEBENCH_ROOT/scratch`）。

**改指不是放宽**：`assert_not_trading_hours()` 原样生效，`--force` 仍然是它的
`--force`。本模块不提供任何绕过它的入口。

    $PY ops/release/fetch_public_quotes.py --root <数据根> --union <v1_union.txt>
    $PY ops/release/fetch_public_quotes.py --root <数据根> --union <...> --limit 20   # 计时抽样
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import genebench_config as cfg          # noqa: E402


def _fetch_union_module():
    """import 那个已经写好判据的脚本（它的 `main()` 就是取数循环）。"""
    import importlib
    return importlib.import_module("ops.acceptance.card_2_5_fetch_union")


def fetch_quotes(root: pathlib.Path, union: pathlib.Path, *, limit: int = 0,
                 force: bool = False) -> dict[str, Any]:
    """日线。**逻辑全部来自** `card_2_5_fetch_union.main()`，这里只换路径。"""
    fu = _fetch_union_module()
    cache = pathlib.Path(root) / "scratch" / "bs_cache"
    cfg.create_dir(cache)
    fu.CACHE = cache
    fu.UNION = pathlib.Path(union)
    os.environ.setdefault("RECON_CACHE", str(cache))
    argv = ["--limit", str(limit)] if limit else []
    if force:
        argv.append("--force")
    t0 = time.time()
    rc = fu.main(argv)
    n = len(list(cache.glob("*.parquet")))
    return {"rc": rc, "seconds": round(time.time() - t0, 1), "cached_codes": n,
            "cache": str(cache), "union": str(union),
            "codes_requested": limit or len(fu.load_union())}


def fetch_adj_and_basic(force: bool = False) -> dict[str, Any]:
    """复权因子 + `stock_basic`。两者都自己读 `$GENEBENCH_ROOT/scratch`，
    所以调用前 `GENEBENCH_ROOT` 必须已经指向用户的数据根。"""
    from snapshots.public import fetch_adj as FA
    from snapshots.public import fetch_basic as FB
    from snapshots.public import source as S
    out: dict[str, Any] = {}
    t0 = time.time()
    out["basic"] = FB.fetch(force=force)
    out["basic_seconds"] = round(time.time() - t0, 1)
    t1 = time.time()
    out["adj"] = FA.fetch(S.union_codes(), force=force)
    out["adj_seconds"] = round(time.time() - t1, 1)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="形态 B：按并集名单拉公开源（非交易时段）")
    ap.add_argument("--root", required=True, help="数据根（会设成 GENEBENCH_ROOT）")
    ap.add_argument("--union", default=None, help="并集名单（默认 <root>/scratch/v1_union.txt）")
    ap.add_argument("--limit", type=int, default=0, help="只拉前 N 只（计时抽样用）")
    ap.add_argument("--quotes-only", action="store_true", help="只拉日线，不拉复权因子/basic")
    ap.add_argument("--force", action="store_true",
                    help="**明知在交易时段仍要拉**（判据在 card_2_5_fetch_union，本脚本不放宽）")
    a = ap.parse_args(argv)
    root = pathlib.Path(a.root)
    if str(cfg.GENEBENCH_ROOT) != str(root):
        print(f"[红] GENEBENCH_ROOT={cfg.GENEBENCH_ROOT} 与 --root={root} 不一致 —— "
              f"先 export GENEBENCH_ROOT={root} 再跑（fetch_adj/fetch_basic 认的是环境变量）",
              file=sys.stderr)
        return 2
    cfg.harden_umask()
    union = pathlib.Path(a.union) if a.union else root / "scratch" / "v1_union.txt"
    out: dict[str, Any] = {"quotes": fetch_quotes(root, union, limit=a.limit, force=a.force)}
    if not a.quotes_only:
        out.update(fetch_adj_and_basic(force=a.force))
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0 if out["quotes"]["rc"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
