# -*- coding: utf-8 -*-
"""公开通道的**复权因子**拉取（卡 1.1-a，沿用 N-68 的四条约束）。

    $PY -m snapshots.public.fetch_adj [--limit N] [--force]

`bs_cache` 里的日线是 `adjustflag=3`（不复权），**没有**复权因子这一列；
公开 provider 的 `factor` 与网关 `/adj` 都要它，所以必须再拉一遍
`query_adjust_factor`（3,575 只）。

**四条约束与 `ops/acceptance/card_2_5_fetch_union.py` 是同一份**（直接 import 那个
文件里的 `assert_not_trading_hours` / `to_bs` / `canonical` / `SLEEP`，不抄第二份 ——
抄一份的表现是「两个拉取脚本的交易时段判据慢慢漂开」，而漂开没人会发现）：

1. 北京时间工作日 09:00–15:30 **拒绝启动**（`--force` 才越过，且打黄字）；
2. 每个请求之间留 `FETCH_SLEEP` 秒；
3. **可续跑** —— 每只票一个 parquet，存在即跳过；
4. 失败清单落盘，不静默。

**窗口从 1990-01-01 起，不是 2009-01-05。** baostock 的 `backAdjustFactor` 是
**自上市累计**的：只从 2009 起拉，`sh.600000` 拿到的第一条就是 `2.969727`
（1999 上市，之前的除权事件被起始日截掉了），于是「第一条之前 factor=1」这个
假设当场作废，2009 年初那一段会被系统性算错。从 1990 拉，第一条就是上市日
那条 `1.000000`（`sz.300750` / `sh.688111` / `sz.002415` 实测都是），
「首事件之前 = 1.0」才成立。
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import pathlib
import sys
import time

import pandas as pd

import genebench_config as cfg

#: baostock 客户端库的落点。**不装进 env**（红线 2 的邻居：env 是评测环境，
#: 拉数脚本的依赖不该混进去）。/tmp 被清了就按卡的裁定装到 `$GB/scratch/bsx/`。
BSX_CANDIDATES: tuple[str, ...] = (
    "/tmp/bsx/baostock-0.9.3",
    str(cfg.GENEBENCH_ROOT / "scratch" / "bsx"),
)

#: 复权因子缓存（一只票一个 parquet，续跑靠它）。
ADJ_CACHE: pathlib.Path = pathlib.Path(
    os.environ.get("PUBLIC_ADJ_CACHE", str(cfg.GENEBENCH_ROOT / "scratch" / "bs_adj_cache"))
)
FAILED_LIST: pathlib.Path = ADJ_CACHE.parent / "v1_union_adj_failed.txt"

#: 日线缓存与并集名单 —— 与 N-68 那一轮同一份，不另起。
BS_CACHE: pathlib.Path = pathlib.Path(
    os.environ.get("RECON_CACHE", str(cfg.GENEBENCH_ROOT / "scratch" / "bs_cache"))
)
UNION: pathlib.Path = cfg.GENEBENCH_ROOT / "scratch" / "v1_union.txt"

#: `backAdjustFactor` 的累计起点。见模块 docstring。
ADJ_START = "1990-01-01"
ADJ_END = cfg.FREEZE_DATE

FIELDS = ("code", "dividOperateDate", "foreAdjustFactor", "backAdjustFactor", "adjustFactor")

#: 连续失败到这个数就判定「会话掉了」并重登。**不是重试策略，是故障归因**：
#: 实测一次会话掉线会把剩下 1,500 只全部记成失败，而失败清单读起来像数据问题。
RELOGIN_AFTER: int = 5


def bsx_path() -> str:
    """baostock 库的实际落点。两个候选都没有就抛 —— 不静默装到 env 里。"""
    for p in BSX_CANDIDATES:
        if pathlib.Path(p).is_dir():
            return p
    raise RuntimeError(
        f"找不到 baostock 客户端库，候选 {BSX_CANDIDATES}。"
        f"按卡 2.5 的裁定：从 PyPI 装到 {BSX_CANDIDATES[1]}（**不要装进 env**）："
        f" pip install --target {BSX_CANDIDATES[1]} baostock==0.9.3"
    )


def _union_module():
    """import `ops/acceptance/card_2_5_fetch_union.py` —— 四条约束只有一份实现。"""
    path = cfg.REPO / "ops" / "acceptance" / "card_2_5_fetch_union.py"
    spec = importlib.util.spec_from_file_location("_card_2_5_fetch_union", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"读不到 {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_union() -> list[str]:
    u = _union_module()
    return u.load_union()


def fetch(codes: list[str], *, force: bool = False, verbose: bool = True) -> dict:
    """拉复权因子，续跑。返回统计。"""
    u = _union_module()
    try:
        u.assert_not_trading_hours()
    except u.TradingHours as e:  # noqa: PERF203
        if not force:
            raise
        print(f"[黄] --force：{e}", file=sys.stderr, flush=True)

    sys.path.insert(0, bsx_path())
    import baostock as bs

    cfg.create_dir(ADJ_CACHE)
    todo = [c for c in codes if not (ADJ_CACHE / f"{c}.parquet").exists()]
    if verbose:
        print(f"并集 {len(codes)} 只；已缓存 {len(codes) - len(todo)} 只；本轮要拉 {len(todo)} 只",
              flush=True)
    stats = {"codes": len(codes), "cached": len(codes) - len(todo), "fetched": 0,
             "empty": 0, "failed": 0, "seconds": 0.0}
    if not todo:
        return stats

    lg = bs.login()
    if lg.error_code != "0":
        raise RuntimeError(f"baostock login 失败：{lg.error_code} {lg.error_msg}")
    t0 = time.time()
    failed: list[tuple[str, str, str]] = []
    consec = 0
    stats["relogins"] = 0
    try:
        for i, code in enumerate(todo, 1):
            r = bs.query_adjust_factor(code=u.to_bs(code), start_date=ADJ_START,
                                       end_date=ADJ_END)
            if r.error_code != "0" and consec + 1 >= RELOGIN_AFTER:
                # **连续失败到阈值 = 会话掉了，不是这些票有问题。**
                # 重登一次再试这一只；仍失败才算真失败。
                print(f"  [重登] 连续 {consec + 1} 次失败（{r.error_code} {r.error_msg}），"
                      f"重新登录后重试 {code}", flush=True)
                try:
                    bs.logout()
                except Exception:               # noqa: BLE001  登出失败不该挡住重登
                    pass
                time.sleep(3.0)
                lg2 = bs.login()
                stats["relogins"] += 1
                if lg2.error_code != "0":
                    raise RuntimeError(f"重新登录失败：{lg2.error_code} {lg2.error_msg}")
                consec = 0
                r = bs.query_adjust_factor(code=u.to_bs(code), start_date=ADJ_START,
                                           end_date=ADJ_END)
            if r.error_code != "0":
                consec += 1
                failed.append((code, r.error_code, r.error_msg))
            else:
                consec = 0
                rows = []
                while r.next():
                    rows.append(r.get_row_data())
                # **零事件是合法结果**（从未除权的票），照样落盘 —— 不落的话
                # 每次续跑都会把它们再拉一遍，而且分不清「没拉过」与「拉了是空」。
                cf = ADJ_CACHE / f"{code}.parquet"
                pd.DataFrame(rows, columns=list(FIELDS)).to_parquet(cf, index=False)
                cf.chmod(0o600)     # 红线 5：umask 002 下 to_parquet 落 0664
                stats["fetched"] += 1
                if not rows:
                    stats["empty"] += 1
            time.sleep(u.SLEEP)
            if verbose and i % 200 == 0:
                el = time.time() - t0
                print(f"  {i}/{len(todo)}  成功 {stats['fetched']}  失败 {len(failed)}  "
                      f"{el/60:.1f} 分钟  预计还要 {(len(todo)-i)*el/i/60:.0f} 分钟", flush=True)
    finally:
        bs.logout()
    stats["seconds"] = round(time.time() - t0, 1)
    stats["failed"] = len(failed)
    FAILED_LIST.write_text("\n".join(f"{c}\t{a}\t{b}" for c, a, b in failed) + "\n",
                           encoding="utf-8")
    try:
        FAILED_LIST.chmod(0o600)
    except OSError:
        pass
    if verbose:
        print(f"完成：拉到 {stats['fetched']}（其中零事件 {stats['empty']}），"
              f"失败 {stats['failed']}，耗时 {stats['seconds']/60:.1f} 分钟", flush=True)
    return stats


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description="拉 v1 宇宙并集的复权因子（可续跑）")
    ap.add_argument("--limit", type=int, default=0, help="只拉前 N 只（调试用）")
    ap.add_argument("--force", action="store_true", help="**明知在交易时段仍要跑**")
    a = ap.parse_args(argv)
    cfg.harden_umask()
    codes = load_union()
    if a.limit:
        codes = codes[: a.limit]
    fetch(codes, force=a.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
