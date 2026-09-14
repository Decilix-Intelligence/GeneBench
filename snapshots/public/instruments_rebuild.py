# -*- coding: utf-8 -*-
"""W2-2：**只用 baostock 的成分接口**重建 csi300 / csi500 的 PIT 成分名单。

    $PY snapshots/public/instruments_rebuild.py fetch      # 取数（联网，非交易时段）
    $PY snapshots/public/instruments_rebuild.py build      # 由缓存出 instruments 与逐日成员
    $PY snapshots/public/instruments_rebuild.py verify     # 随机抽 40 天回查 API
    $PY snapshots/public/instruments_rebuild.py reconcile  # 与私有 universe_pit 对账

**为什么要重建**：现在公开包里的 `instruments/{csi300,csi500,csi1000}.txt` 派生自
私有 `universe_pit`（上游 tushare 的 `index_weight` + qlib 名单），**不在 baostock
的许可射程内**。公开包要自足 —— 数据面必须整条链都能用公开源重放。

**csi1000 没有对应接口**：baostock 0.9.3 只提供 `query_hs300_stocks` /
`query_zz500_stocks` / `query_sz50_stocks`，**没有中证 1000**（实测 `dir(bs)`）。
所以本脚本只重建 csi300 与 csi500，csi1000 仍依赖私有派生名单 —— 记为已知限制。

**2026-09-12（卡 A，用户裁定 ①）：重建结果已经替换进公开包** —— `instruments/{csi300,csi500}.txt` 逐字节取自本脚本的产物，
`all.txt` 逐行由公开 `daily` 表算出，`csi1000.txt` **从公开包删除**。
换面记录与逐项证据见 `ops/reports/public/instruments_switch.md`。

## 取数为什么不是「逐日 4,269 次」

`query_hs300_stocks(date=d)` 回的每一行都带 `updateDate` —— 那是**该名单版本的生效日**，
对 d 单调不减（版本只会往前走）。于是「a 与 b 的 updateDate 相同」⇒
**(a, b) 之间一次调整都没发生**，中间那些天的成分与 a 逐字相同，不必再问。

所以走「跨 5 个交易日探一步；`updateDate` 变了就在这 5 天里二分找**第一个**变化点」：
`{u_d == u_a}` 在 (a, b] 上是个前缀，二分是**精确**的，不是近似。
请求数从 8,538 降到 ~2,400，暴露在对方服务上的时间也短 —— 这个接口今天上午还
拒连了半小时（见报告）。单调性**每一步都断言**，破了就当场停。

正确性不靠这段论证背书：`verify` 会随机抽 40 个交易日**重新问一次 API**，
与建出来的成员集合逐字比对。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, "/data/shared/genebench/scratch/W2/bs")

import genebench_config as cfg  # noqa: E402

OUT = cfg.SNAPSHOTS_PUBLIC / "instruments_rebuild"
CACHE = OUT / "bs_cache"
CAL = cfg.SNAPSHOTS_PUBLIC / "qlib_provider" / "calendars" / "day.txt"

#: baostock 只有这两个能用于 v1 的宇宙。`sz50` 用不上，`zz1000` **不存在**。
INDICES: dict[str, str] = {"csi300": "query_hs300_stocks", "csi500": "query_zz500_stocks"}

START, END = "2009-01-05", "2026-07-31"
STRIDE = int(os.environ.get("W2_STRIDE", "5"))
SLEEP = float(os.environ.get("W2_SLEEP", "0.15"))
RETRY = 6


class TradingHours(RuntimeError):
    pass


def assert_not_trading_hours(now: dt.datetime | None = None) -> None:
    """判据逐字照 `ops/acceptance/card_2_5_fetch_union.assert_not_trading_hours`。"""
    now = now or dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))
    if now.weekday() >= 5:
        return
    if dt.time(9, 0) <= now.time() <= dt.time(15, 30):
        raise TradingHours(
            f"现在是北京时间 {now:%Y-%m-%d %H:%M}（工作日交易时段）—— **拒绝启动**。"
            f"周末或 15:30 之后再来")


def calendar() -> list[str]:
    days = [l.strip() for l in CAL.read_text(encoding="utf-8").splitlines() if l.strip()]
    return [d for d in days if START <= d <= END]


def to_qlib(bs_code: str) -> str:
    """`sh.600000` → `SH600000`（instruments 的写法）。"""
    ex, num = bs_code.split(".")
    return {"sh": "SH", "sz": "SZ", "bj": "BJ"}[ex] + num


def to_lake(bs_code: str) -> str:
    """`sh.600000` → `600000.SH`（`universe_pit` 的写法）。"""
    ex, num = bs_code.split(".")
    return f"{num}.{ex.upper()}"


# ------------------------------------------------------------------ 取数

_LOGGED_IN = False


def _login():
    global _LOGGED_IN
    import baostock as bs
    if not _LOGGED_IN:
        lg = bs.login()
        if lg.error_code != "0":
            raise RuntimeError(f"baostock 登录失败 {lg.error_code} {lg.error_msg}")
        _LOGGED_IN = True
    return bs


def _logout():
    global _LOGGED_IN
    if _LOGGED_IN:
        import baostock as bs
        bs.logout()
        _LOGGED_IN = False


def cache_path(uni: str, date: str) -> Path:
    return CACHE / uni / f"{date}.json"


def fetch_day(uni: str, date: str, *, force: bool = False) -> dict:
    """一天一个 json：`{"update": "...", "codes": [...]}`。缓存命中就不联网。"""
    p = cache_path(uni, date)
    if p.is_file() and not force:
        return json.loads(p.read_text(encoding="utf-8"))
    last = None
    for attempt in range(RETRY):
        try:
            bs = _login()
            fn = getattr(bs, INDICES[uni])
            r = fn(date=date)
            if r.error_code != "0":
                raise RuntimeError(f"{r.error_code} {r.error_msg}")
            rows = []
            while r.next():
                rows.append(r.get_row_data())
            ups = {x[0] for x in rows}
            if len(ups) > 1:
                raise RuntimeError(f"{uni} {date} 一次回了多个 updateDate：{sorted(ups)}")
            rec = {"update": (ups.pop() if ups else ""),
                   "codes": sorted(to_qlib(x[1]) for x in rows),
                   "n": len(rows)}
            cfg.create_dir(p.parent)
            p.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
            p.chmod(0o600)
            time.sleep(SLEEP)
            return rec
        except Exception as e:                                   # noqa: BLE001
            last = e
            _logout()
            time.sleep(2.0 * (attempt + 1))
    raise RuntimeError(f"{uni} {date} 取数失败（重试 {RETRY} 次）：{last}")


def fetch(uni: str, days: list[str]) -> dict[str, dict]:
    """跨步 + 二分。返回 `date -> rec`（只含**真正问过**的那些天）。"""
    asked: dict[str, dict] = {}

    def ask(i: int) -> dict:
        d = days[i]
        if d not in asked:
            asked[d] = fetch_day(uni, d)
        return asked[d]

    n = len(days)
    a = 0
    ra = ask(0)
    print(f"[{uni}] {days[0]} update={ra['update']} n={ra['n']}", flush=True)
    while a < n - 1:
        b = min(a + STRIDE, n - 1)
        rb = ask(b)
        if rb["update"] < ra["update"]:
            raise RuntimeError(f"[{uni}] updateDate 不单调：{days[a]}={ra['update']} "
                               f"> {days[b]}={rb['update']} —— **停下**，跨步推断的前提破了")
        if rb["update"] == ra["update"]:
            a, ra = b, rb
            continue
        lo, hi = a + 1, b
        while lo < hi:                       # (a, b] 上第一个 update != ra 的位置
            mid = (lo + hi) // 2
            rm = ask(mid)
            if rm["update"] < ra["update"]:
                raise RuntimeError(f"[{uni}] updateDate 不单调（二分内）：{days[mid]}")
            if rm["update"] == ra["update"]:
                lo = mid + 1
            else:
                hi = mid
        a = lo
        ra = ask(a)
        print(f"[{uni}] 换版 {days[a]} update={ra['update']} n={ra['n']} "
              f"（累计问了 {len(asked)} 次）", flush=True)
    print(f"[{uni}] 取数完成：问了 {len(asked)} 次 / {n} 个交易日", flush=True)
    return asked


# ------------------------------------------------------------------ 建集

def daily_members(uni: str, days: list[str]) -> dict[str, list[str]]:
    """把「问过的那些天」补成逐日成员。补法就是跨步推断的那条前提。"""
    cur: list[str] | None = None
    cur_up = ""
    out: dict[str, list[str]] = {}
    for d in days:
        p = cache_path(uni, d)
        if p.is_file():
            rec = json.loads(p.read_text(encoding="utf-8"))
            cur, cur_up = rec["codes"], rec["update"]
        if cur is None:
            raise RuntimeError(f"{uni} {d} 之前没有任何已知版本")
        out[d] = cur
    return out


def intervals(members: dict[str, list[str]], days: list[str]) -> list[tuple[str, str, str]]:
    """逐日成员 → 连续区间 `(code, in_date, out_date)`，右端**闭**。"""
    idx = {d: i for i, d in enumerate(days)}
    runs: dict[str, list[list[int]]] = {}
    for d in days:
        i = idx[d]
        for c in members[d]:
            r = runs.setdefault(c, [])
            if r and r[-1][1] == i - 1:
                r[-1][1] = i
            else:
                r.append([i, i])
    out = []
    for c, rs in runs.items():
        for s, e in rs:
            out.append((c, days[s], days[e]))
    return sorted(out)


def build(days: list[str]) -> dict:
    cfg.create_dir(OUT)
    rep = {}
    for uni in INDICES:
        mem = daily_members(uni, days)
        iv = intervals(mem, days)
        txt = OUT / f"{uni}.txt"
        txt.write_text("".join(f"{c}\t{a}\t{b}\n" for c, a, b in iv), encoding="utf-8")
        txt.chmod(0o600)
        jl = OUT / f"{uni}_daily.jsonl"
        with jl.open("w", encoding="utf-8") as fh:
            for d in days:
                fh.write(json.dumps({"date": d, "codes": mem[d]}, ensure_ascii=False) + "\n")
        jl.chmod(0o600)
        sizes = sorted({len(mem[d]) for d in days})
        rep[uni] = {"rows": len(iv), "codes": len({c for c, _, _ in iv}),
                    "daily_sizes": sizes[:3] + (["…"] if len(sizes) > 6 else []) + sizes[-3:],
                    "txt": str(txt), "daily": str(jl)}
        print(f"[{uni}] 区间 {len(iv)} 行 / 去重 {rep[uni]['codes']} 只 / "
              f"逐日成员数 {min(sizes)}…{max(sizes)}", flush=True)
    (OUT / "build_info.json").write_text(json.dumps(
        {"built_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
         "source": "baostock 0.9.3 query_hs300_stocks / query_zz500_stocks",
         "window": [START, END], "trading_days": len(days), "stride": STRIDE,
         "csi1000": "baostock 无中证1000成分接口 —— 未重建",
         "per_universe": rep}, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "build_info.json").chmod(0o600)
    return rep


# ------------------------------------------------------------------ 回查

def verify(days: list[str], k: int = 40, seed: int = 20260910) -> int:
    """随机抽 k 天**重新问 API**，与建出来的逐日成员逐字比对。"""
    rnd = random.Random(seed)
    bad = []
    for uni in INDICES:
        mem = daily_members(uni, days)
        for d in rnd.sample(days, k):
            live = fetch_day(uni, d, force=True)
            if sorted(live["codes"]) != sorted(mem[d]):
                a, b = set(live["codes"]), set(mem[d])
                bad.append(f"{uni} {d}: API 多 {sorted(a - b)[:5]} / 建出来多 {sorted(b - a)[:5]}")
    print(f"回查 {k} 天 × {len(INDICES)} 个宇宙：{'全部一致' if not bad else str(len(bad)) + ' 天不一致'}")
    for x in bad:
        print("  ✗ " + x)
    return 1 if bad else 0


# ------------------------------------------------------------------ 对账

def private_daily(uni: str, days: list[str]) -> dict[str, set[str]]:
    import pandas as pd
    d = pd.read_parquet(cfg.SNAPSHOTS_V1 / "universe" / "universe_pit.parquet")
    d = d[d["universe"] == uni]
    idx = {x: i for i, x in enumerate(days)}
    out: dict[str, set[str]] = {x: set() for x in days}
    for code, a, b in zip(d["code"], d["in_date"], d["out_date"]):
        num, ex = str(code).split(".")
        q = ex + num
        i, j = idx.get(str(a)), idx.get(str(b))
        if i is None:
            i = next((k for k, x in enumerate(days) if x >= str(a)), None)
        if j is None:
            j = next((k for k in range(len(days) - 1, -1, -1) if days[k] <= str(b)), None)
        if i is None or j is None or i > j:
            continue
        for k in range(i, j + 1):
            out[days[k]].add(q)
    return out


def reconcile(days: list[str]) -> dict:
    rep: dict = {"window": [START, END], "trading_days": len(days), "universes": {}}
    for uni in INDICES:
        pub = {d: set(v) for d, v in daily_members(uni, days).items()}
        prv = private_daily(uni, days)
        jac, only_pub, only_prv, exact = [], {}, {}, 0
        for d in days:
            a, b = pub[d], prv[d]
            u = a | b
            j = len(a & b) / len(u) if u else 1.0
            jac.append(j)
            if a == b:
                exact += 1
            for c in a - b:
                only_pub.setdefault(c, []).append(d)
            for c in b - a:
                only_prv.setdefault(c, []).append(d)
        import statistics as st
        srt = sorted(jac)

        def q(p):
            return srt[min(len(srt) - 1, int(p * len(srt)))]

        # 进出场日期差：按 code 比第一天 / 最后一天
        def edges(m):
            e = {}
            for d in days:
                for c in m[d]:
                    if c not in e:
                        e[c] = [d, d]
                    else:
                        e[c][1] = d
            return e

        ep, eq2 = edges(pub), edges(prv)
        in_diff, out_diff = [], []
        for c in set(ep) & set(eq2):
            if ep[c][0] != eq2[c][0]:
                in_diff.append({"code": c, "public": ep[c][0], "private": eq2[c][0]})
            if ep[c][1] != eq2[c][1]:
                out_diff.append({"code": c, "public": ep[c][1], "private": eq2[c][1]})
        rep["universes"][uni] = {
            "days_identical": exact, "days_total": len(days),
            "jaccard": {"mean": round(st.fmean(jac), 6), "min": round(min(jac), 6),
                        "p01": round(q(0.01), 6), "p10": round(q(0.10), 6),
                        "p50": round(q(0.50), 6)},
            "codes_public": len(ep), "codes_private": len(eq2),
            "codes_only_public": sorted(set(ep) - set(eq2)),
            "codes_only_private": sorted(set(eq2) - set(ep)),
            "member_days_only_public": sum(len(v) for v in only_pub.values()),
            "member_days_only_private": sum(len(v) for v in only_prv.values()),
            "in_date_differs": len(in_diff), "out_date_differs": len(out_diff),
            "in_date_diff_sample": sorted(in_diff, key=lambda x: x["code"])[:40],
            "out_date_diff_sample": sorted(out_diff, key=lambda x: x["code"])[:40],
            "gaps_only_public": {c: [v[0], v[-1], len(v)] for c, v in
                                 sorted(only_pub.items(), key=lambda kv: -len(kv[1]))[:60]},
            "gaps_only_private": {c: [v[0], v[-1], len(v)] for c, v in
                                  sorted(only_prv.items(), key=lambda kv: -len(kv[1]))[:60]},
        }
        r = rep["universes"][uni]
        print(f"[{uni}] 逐日完全相同 {exact}/{len(days)} 天 · Jaccard 均 "
              f"{r['jaccard']['mean']} 最低 {r['jaccard']['min']} · "
              f"只在公开 {len(r['codes_only_public'])} 只 / 只在私有 "
              f"{len(r['codes_only_private'])} 只", flush=True)
    p = OUT / "reconcile.json"
    p.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    p.chmod(0o600)
    print(f"→ {p}")
    return rep


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["fetch", "build", "verify", "reconcile", "all"])
    ap.add_argument("--force", action="store_true", help="交易时段强跑")
    ap.add_argument("--k", type=int, default=40)
    a = ap.parse_args()
    days = calendar()
    if a.cmd in ("fetch", "verify", "all"):
        try:
            assert_not_trading_hours()
        except TradingHours as e:
            if not a.force:
                print(f"[红] {e}", file=sys.stderr)
                return 2
            print(f"[黄] --force：{e}", file=sys.stderr)
    rc = 0
    try:
        if a.cmd in ("fetch", "all"):
            cfg.create_dir(CACHE)
            OUT.chmod(0o700)
            for uni in INDICES:
                fetch(uni, days)
        if a.cmd in ("build", "all"):
            build(days)
        if a.cmd in ("verify", "all"):
            rc |= verify(days, a.k)
        if a.cmd in ("reconcile", "all"):
            reconcile(days)
    finally:
        _logout()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
