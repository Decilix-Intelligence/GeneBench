# -*- coding: utf-8 -*-
"""N-68：拉 **v1 宇宙并集** 的全窗口日线（裁定 2026-09-05：不建全市场，全市场留 v1.1）。

**范围**：`snapshots/v1/qlib_provider/instruments/{csi300,csi500,csi1000}.txt` 的并集
= **3,575 只**（全部沪深；baostock 不服务北交所，而三个 universe 里本来就没有北交所，
所以这里没有 N-70 那个缺口）。窗口 2009-01-05..2026-07-31。

**四条约束**（裁定原文）：按宇宙分批、每请求留间隔、**非交易时段**、`bs_cache` 续跑。

「非交易时段」在这里是**硬判据**而不是自觉：A 股交易时段内直接拒绝启动。
理由不是礼貌 —— 是对方在交易时段的服务压力最大，而我们这个批次要跑 7 个多小时。
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
sys.path.insert(0, "/tmp/bsx/baostock-0.9.3")

import pandas as pd

FIELDS = "date,code,open,high,low,close,preclose,volume,amount,turn,tradestatus,isST"
START, END = "2009-01-05", "2026-07-31"
CACHE = pathlib.Path(os.environ.get("RECON_CACHE", "/data/shared/genebench/scratch/bs_cache"))
UNION = pathlib.Path("/data/shared/genebench/scratch/v1_union.txt")
#: 每个请求之间的间隔（秒）。单次查询本身要 7 秒，这里再留一点余量。
SLEEP = float(os.environ.get("FETCH_SLEEP", "0.3"))


class TradingHours(RuntimeError):
    pass


def assert_not_trading_hours(now: dt.datetime | None = None) -> None:
    """A 股交易时段内**拒绝启动**。

    判据取北京时间：工作日 09:00–15:30。**宽一点**（早半小时、晚半小时）——
    边界上宁可不跑，也不要在开盘前一分钟压上去。
    """
    now = now or dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))
    if now.weekday() >= 5:
        return
    if dt.time(9, 0) <= now.time() <= dt.time(15, 30):
        raise TradingHours(
            f"现在是北京时间 {now:%Y-%m-%d %H:%M}（工作日交易时段）—— **拒绝启动**。"
            f"这个批次要跑 7 个多小时，裁定要求非交易时段跑。"
            f"周末或 15:30 之后再来；真要强跑就显式加 --force 并说明理由")


def to_bs(code: str) -> str:
    """`SH600000` / `600000.SH` → `sh.600000`。"""
    c = code.strip().upper()
    if "." in c:
        num, ex = c.split(".")
    else:
        ex, num = c[:2], c[2:]
    return {"SH": "sh", "SZ": "sz", "BJ": "bj"}[ex] + "." + num


def canonical(code: str) -> str:
    """统一成湖里的写法 `600000.SH`。

    并集文件是 qlib 写法 `SH600000`，而 `bs_cache` 里已有的 188 只是
    对账那一轮按湖的写法存的 —— 两种写法混用会让**已经拉过的又拉一遍**
    （实测：第一版跑出来「已缓存 0 只」）。缓存键只许有一种形状。
    """
    c = code.strip().upper()
    if "." in c:
        return c
    return f"{c[2:]}.{c[:2]}"


def load_union() -> list[str]:
    if not UNION.is_file():
        raise SystemExit(f"缺 {UNION} —— 先跑并集计算")
    return [canonical(x) for x in UNION.read_text(encoding="utf-8").splitlines() if x.strip()]


def main(argv=None) -> int:
    import baostock as bs

    ap = argparse.ArgumentParser(description="拉 v1 宇宙并集的全窗口日线（可续跑）")
    ap.add_argument("--limit", type=int, default=0, help="只拉前 N 只（调试用）")
    ap.add_argument("--force", action="store_true", help="**明知在交易时段仍要跑**")
    a = ap.parse_args(argv)
    try:
        assert_not_trading_hours()
    except TradingHours as e:
        if not a.force:
            print(f"[红] {e}", file=sys.stderr)
            return 2
        print(f"[黄] --force：{e}", file=sys.stderr)

    codes = load_union()
    if a.limit:
        codes = codes[: a.limit]
    CACHE.mkdir(parents=True, exist_ok=True)
    CACHE.chmod(0o700)
    todo = [c for c in codes if not (CACHE / f"{c}.parquet").exists()]
    print(f"并集 {len(codes)} 只；已缓存 {len(codes) - len(todo)} 只；本轮要拉 {len(todo)} 只",
          flush=True)
    if not todo:
        print("全部已在缓存里 —— 没有要拉的")
        return 0

    lg = bs.login()
    assert lg.error_code == "0", (lg.error_code, lg.error_msg)
    t0, ok, failed = time.time(), 0, []
    try:
        for i, code in enumerate(todo, 1):
            r = bs.query_history_k_data_plus(to_bs(code), FIELDS, start_date=START,
                                             end_date=END, frequency="d", adjustflag="3")
            if r.error_code != "0":
                failed.append((code, r.error_code, r.error_msg))
            else:
                rows = []
                while r.next():
                    rows.append(r.get_row_data())
                if rows:
                    cf = CACHE / f"{code}.parquet"
                    pd.DataFrame(rows, columns=FIELDS.split(",")).to_parquet(cf, index=False)
                    cf.chmod(0o600)         # 红线 5：umask 002 下 to_parquet 落 0664
                    ok += 1
                else:
                    failed.append((code, "empty", "0 行"))
            time.sleep(SLEEP)
            if i % 50 == 0:
                el = time.time() - t0
                print(f"  {i}/{len(todo)}  成功 {ok}  失败 {len(failed)}  "
                      f"{el/60:.1f} 分钟  预计还要 {(len(todo)-i)*el/i/60:.0f} 分钟", flush=True)
    finally:
        bs.logout()
    print(f"\n完成：成功 {ok}，失败 {len(failed)}，耗时 {(time.time()-t0)/60:.1f} 分钟")
    if failed:
        print("失败前 10：", failed[:10])
    #: 失败**不静默** —— 落一份清单，续跑时它们仍在 todo 里。
    (CACHE.parent / "v1_union_failed.txt").write_text(
        "\n".join(f"{c}\t{a_}\t{b}" for c, a_, b in failed) + "\n", encoding="utf-8")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
