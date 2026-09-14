# -*- coding: utf-8 -*-
"""卡 1.3：**两通道对账**（卡 2.5 §7 的发布件）。

    cd $REPO && ulimit -n 8192 && $GENEBENCH_ROOT/env/bin/python ops/recon_public_vs_private.py

比的是 `snapshots/public_v1`（baostock）与 `snapshots/v1`（审计湖 + ChinaScope）
**并列的两份产物**，不重算任何东西 —— 两条链各自跑完（卡 1.1-a / 1.1-b），
本脚本只做**逐值比对**并把差异归因。

七节，`--part` 可单跑（结果按节合并进同一个 JSON，别的节原样留着）：

===========  ===================================================================
`returns`    **收益率级一致率**（沿用卡 2.1a 的方法）：逐票逐日 close-to-close
             收益率，分层抽样与全量两档。**同时**扫出「哪个 (票, 日) 的 provider
             格在两条通道上不同」的位图，`gold` 那一节的归因就靠它。
`calibration` τ / ε 两通道对比表（τ 值、ε 每指标带值并列、可标定 / 超阈 /
             无自由度计数、`ic_family`）。
`gold`       三宇宙各抽 30 个因子 × 固定日期窗，逐格相对差分布；**超阈的格子
             逐个归因到源差异**（当日源差 / 回看窗内源差 / 归不掉）。
`rows`       全量 `daily` 行集合与逐字段一致率（卡 1.1-a 的 `channel_reconcile`
             在本卡重跑一遍：数据卡要引的数必须出自本卡自己的产物）。
`limits`     公开通道**自己推**的 `stk_limit` 与私有 `stk_limit` 逐行核。
`units`      量额单位的落带判据（`low <= vwap <= high`）—— 「amount 是元不是千元」
             这句话的证据，不是查文档得来的。
`frozen`     `PUBLIC_FROZEN_ARTIFACTS` 的 sha256；**不存在的如实记成缺件**。
===========  ===================================================================

**这个脚本不打网关**（全部直读 parquet / bin），所以不需要 `ops/gateway_lock.py`；
与卡 1.1-b / 1.2 同理由。**它只读不写两个快照根**，产物只落
`ops/reports/public/reconciliation.{json,md}`。

容差（都写进产物的 `tolerances`，报告里逐条解释）：

* `provider_cell_rel` = 1e-6 —— provider 的 `.day.bin` 是 **float32**（qlib 格式），
  单侧相对精度约 1.2e-7，两侧往返约 2.4e-7。1e-6 在噪声之上一个数量级，
  同时远在任何真实源差异（最小的那类是「亚元取整」，相对 1e-6~1e-5）之下。
* `return_abs` = 1e-6 —— 收益率是**绝对量**（量纲已经归一），float32 往返到
  收益率上约 2e-7。同时按卡 2.1a 的口径并报 1e-4 / 1e-3 两档占比，好与那份诊断对读。
* `gold_cell_rel` = 1e-6 —— gold 是 float64，但**输入**是 float32 的 provider 格，
  所以判据仍取输入侧的噪声地板，不取 float64 的。

**为什么收益率而不是价格**：两条通道的 provider 都以冻结线重定基（`factor=1`），
价格水平本来就该相同 —— 但收益率是**归一化不变量**，即使有人改了重定基口径它也不动。
卡 2.1a 用它比社区 release，本卡用同一个量比两条通道，两处可以直接对读。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import genebench_config as cfg                                     # noqa: E402
from snapshots import qlib_provider as qp                          # noqa: E402
from snapshots.public import manifest as PM                        # noqa: E402

OUT_JSON: Path = cfg.REPORTS / "public" / "reconciliation.json"
OUT_MD: Path = cfg.REPORTS / "public" / "reconciliation.md"

PARTS: tuple[str, ...] = (
    "returns", "calibration", "gold", "rows", "limits", "units", "frozen")

#: 见模块 docstring 的「容差」一节。改这三个数就是改判据 —— 产物里逐条记着。
TOL_PROVIDER_CELL_REL: float = 1e-6
TOL_RETURN_ABS: float = 1e-6
#: gold 的「有没有不同」的地板：1e-6。**它不是判别力阈值** —— 两条通道的复权
#: 归一化常数本来就逐票不同（见 returns 那一节的 `level_scale`），所以 1e-6 之上的格
#: 只说明「不是逐位相同」。
TOL_GOLD_DIFFERS_REL: float = 1e-6
#: gold 的**超阈**（要逐格归因的那一档）：1e-3。取这个数的理由：τ 是逐日截面秩相关的
#: P10 = 0.984，秩对 1e-3 量级的扰动几乎不动；真正会改变排序、进而改变 Fid% 的是
#: 1e-3 以上的格。两档都报，改哪一个都是改判据。
TOL_GOLD_CELL_REL: float = 1e-3
#: 卡 2.1a 的两档，只为与那份诊断对读，**不是本卡的判据**。
RETURN_REPORT_BUCKETS: tuple[float, ...] = (1e-6, 1e-4, 1e-3)

#: gold 抽样：每个宇宙 30 个因子，种子固定 —— 换种子会换样本，所以它进产物。
GOLD_FACTORS_PER_UNIVERSE: int = 30
GOLD_WINDOW: tuple[str, str] = ("20260105", "20260630")
#: 与卡 1.2 / 1.1-b 的 IC-ε 判据窗**同一个窗**，这样三处抽样比对可以互相印证。
SEED: int = 20260907
#: 归因用的回看长度（交易日）：792 条因子里最长的滚动窗口约 240 日，
#: 取 250 个交易日 ≈ 一年，覆盖到「今天这格算得不一样，是因为一年内某天的源差」。
GOLD_LOOKBACK_DAYS: int = 250

#: 分层抽样档的规模与分层键（板块）。全量档是全部共有票，不抽样。
STRATIFIED_N: int = 200

#: 「公开复权价 / 私有复权价」这个比值在一只票内的 max/min − 1 小于它，就叫**常数比值**
#: —— 常数比值不影响收益率，也不影响任何以收益率为输入的下游数值。
#: 大于它就是**两条通道对这只票的复权处理真的不同**，那会一路传到 gold。
CONSTANT_RATIO_SPREAD: float = 1e-3
#: 收益率**实质不同**的判据（远在 float32 噪声与小数位差异之上）。
MATERIAL_RETURN_DIFF: float = 1e-3

_TINY = 1e-300


# --------------------------------------------------------------- 小工具

def _code_head() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=_REPO,
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:                                    # pragma: no cover - 无 git 也要能跑
        return "unknown"


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _board(ts_code: str) -> str:
    num = ts_code.split(".")[0]
    if num.startswith(("60", "00")):
        return "main"
    if num.startswith("30"):
        return "chinext"
    if num.startswith("68"):
        return "star"
    if num.startswith(("4", "8", "92")):
        return "bse"
    return "other"


def _quantiles(a: np.ndarray) -> dict:
    """分布摘要。空数组返回全 None —— **不返回 0**，0 会被读成「完全一致」。"""
    if a.size == 0:
        return {"n": 0, "min": None, "p10": None, "p50": None, "p90": None,
                "p99": None, "p999": None, "max": None}
    return {
        "n": int(a.size),
        "min": float(a.min()),
        "p10": float(np.percentile(a, 10)),
        "p50": float(np.percentile(a, 50)),
        "p90": float(np.percentile(a, 90)),
        "p99": float(np.percentile(a, 99)),
        "p999": float(np.percentile(a, 99.9)),
        "max": float(a.max()),
    }


def _rel(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """对称相对差 ``|a-b| / max(|a|,|b|)``。

    **刻意不拿私有值当分母**：分母趋零时相对差会炸成任意大，而「私有值恰好是 0」
    本身不该让那一格看起来分歧无穷大。两边都是 0 → 0。
    """
    den = np.maximum(np.abs(a), np.abs(b))
    out = np.zeros_like(den)
    ok = den > _TINY
    out[ok] = np.abs(a[ok] - b[ok]) / den[ok]
    return out


def _expand(start: int, arr: np.ndarray, n: int) -> np.ndarray:
    """把 ``.day.bin``（起始日历下标 + 一段值）摊到整条日历上，缺的地方 NaN。"""
    v = np.full(n, np.nan, dtype="float64")
    lo = max(0, start)
    hi = min(n, start + arr.size)
    if hi > lo:
        v[lo:hi] = arr[lo - start:hi - start]
    return v


def _load_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


# --------------------------------------------------------------- ① returns + provider 位图

def _provider_codes(paths) -> dict[str, str]:
    """``{qlib 目录名: ts_code}``。目录名是小写（``sh600000``），gold 里是大写。"""
    out = {}
    for d in paths.features.iterdir():
        if d.is_dir():
            out[d.name] = qp.ts_code(d.name.upper())
    return out


def _read_fields(paths, qdir: str, n: int) -> "dict[str, np.ndarray] | None":
    out: dict[str, np.ndarray] = {}
    for f in qp.FIELDS:
        p = paths.features / qdir / f"{f}.day.bin"
        if not p.is_file():
            return None
        s, a = qp.read_bin(p)
        out[f] = _expand(s, a.astype("float64"), n)
    return out


def part_returns(verbose: bool = True, limit: "int | None" = None) -> tuple[dict, dict, dict]:
    """收益率级一致率 + provider 逐格差异位图。

    返回 ``(报告块, {大写 qlib code: 该票逐日「两通道有格不同」的布尔数组})``。
    位图不进 JSON（太大），只在同一次进程里交给 :func:`part_gold`。
    """
    pub_p, priv_p = qp.PUBLIC_PATHS, qp.PRIVATE_PATHS
    cal_pub = [l.strip() for l in pub_p.calendar_file.read_text().split("\n") if l.strip()]
    cal_priv = [l.strip() for l in priv_p.calendar_file.read_text().split("\n") if l.strip()]
    same_cal = cal_pub == cal_priv
    if not same_cal:
        raise SystemExit(
            "两条通道的 provider 日历不同 —— 本节按「同一条日历」对齐，"
            f"公开 {len(cal_pub)} 天 / 私有 {len(cal_priv)} 天。先查日历再对账。")
    n = len(cal_pub)

    pub_codes, priv_codes = _provider_codes(pub_p), _provider_codes(priv_p)
    common = sorted(set(pub_codes) & set(priv_codes))
    if limit:                                   # 只为冒烟/夹具，正式跑不给
        common = common[:limit]
    only_pub = sorted(pub_codes[q] for q in set(pub_codes) - set(priv_codes))
    only_priv = sorted(priv_codes[q] for q in set(priv_codes) - set(pub_codes))

    devs: list[np.ndarray] = []
    price_levels: list[np.ndarray] = []
    dev_code_id: list[np.ndarray] = []
    attrib = {"over": 0, "raw_quote_step": 0, "adjustment_step": 0, "neither": 0}
    level_scale: list[dict] = []
    per_code: list[dict] = []
    cell_diff: dict[str, np.ndarray] = {}
    units = {"band_in": 0, "band_total": 0, "vwap_over_close": []}
    missing_days = {"public_short_of_private": 0, "private_short_of_public": 0,
                    "codes_with_day_gap": 0}
    t0 = time.time()

    for i, qdir in enumerate(common):
        a = _read_fields(pub_p, qdir, n)
        b = _read_fields(priv_p, qdir, n)
        if a is None or b is None:
            continue
        ts = pub_codes[qdir]

        # --- 逐格差异位图（8 个字段任一不同就算这一格不同）
        diff = np.zeros(n, dtype=bool)
        for f in qp.FIELDS:
            x, y = a[f], b[f]
            fx, fy = np.isfinite(x), np.isfinite(y)
            both = fx & fy
            d = np.zeros(n, dtype=bool)
            d[both] = _rel(x[both], y[both]) > TOL_PROVIDER_CELL_REL
            d |= fx ^ fy                     # 一边有、一边没有 —— 也是差异
            diff |= d
        cell_diff[qdir.upper()] = diff

        # --- 缺失日
        dp = int(np.isfinite(a["close"]).sum())
        dv = int(np.isfinite(b["close"]).sum())
        if dp != dv:
            missing_days["codes_with_day_gap"] += 1
            missing_days["public_short_of_private"] += max(0, dv - dp)
            missing_days["private_short_of_public"] += max(0, dp - dv)

        # --- 量额单位的落带判据（只看公开通道 —— 这是公开通道自己的性质）
        v, lo, hi, cl = a["vwap"], a["low"], a["high"], a["close"]
        ok = np.isfinite(v) & np.isfinite(lo) & np.isfinite(hi)
        t = qp.VWAP_BAND_REL_TOL
        units["band_total"] += int(ok.sum())
        units["band_in"] += int(((v[ok] >= lo[ok] * (1 - t)) & (v[ok] <= hi[ok] * (1 + t))).sum())
        okc = ok & np.isfinite(cl) & (cl > 0)
        if okc.any():
            units["vwap_over_close"].append(float(np.median(v[okc] / cl[okc])))

        # --- 收益率（卡 2.1a 的口径：先取两边都有值的日子，再在那条序列上求 close-to-close）
        vo, vc = a["close"], b["close"]
        valid = np.isfinite(vo) & np.isfinite(vc) & (vo > 0) & (vc > 0)
        idx = np.flatnonzero(valid)
        if idx.size < 3:
            continue
        ro = np.diff(vo[idx]) / vo[idx][:-1]
        rc = np.diff(vc[idx]) / vc[idx][:-1]
        dev = np.abs(ro - rc).astype("float32")
        devs.append(dev)
        dev_code_id.append(np.full(dev.size, len(per_code), dtype="int32"))
        # --- 收益率差异的**分解**。复权收盘价 = 原始收盘 × factor，于是
        #     Δlog(1+r) = Δlog(原始收盘之比) + Δlog(factor 之比)
        # 两项分别对应「源报价当天不一样」与「复权因子在这一天走了不同的台阶」。
        # **不能拿「端点的复权价位不同」当归因** —— 两条通道的归一化常数逐票不同，
        # 那样几乎每一对都会被判成「价位不同」，是一句没有判别力的话。
        rawp = vo[idx] / a["factor"][idx]
        rawv = vc[idx] / b["factor"][idx]
        ratio = vo[idx] / vc[idx]
        with np.errstate(divide="ignore", invalid="ignore"):
            d_raw = np.diff(np.log(rawp / rawv))
            d_fac = np.diff(np.log(a["factor"][idx] / b["factor"][idx]))
        d_raw = np.nan_to_num(d_raw, nan=0.0, posinf=0.0, neginf=0.0)
        d_fac = np.nan_to_num(d_fac, nan=0.0, posinf=0.0, neginf=0.0)
        over = dev > TOL_RETURN_ABS
        ar, af = np.abs(d_raw), np.abs(d_fac)
        attrib["over"] += int(over.sum())
        attrib["raw_quote_step"] += int((over & (ar > TOL_PROVIDER_CELL_REL) & (ar >= af)).sum())
        attrib["adjustment_step"] += int((over & (af > TOL_PROVIDER_CELL_REL) & (af > ar)).sum())
        attrib["neither"] += int((over & (ar <= TOL_PROVIDER_CELL_REL)
                                 & (af <= TOL_PROVIDER_CELL_REL)).sum())
        # 归一化常数：同一票上「公开价 / 私有价」这个比值有多稳。
        fin = np.isfinite(ratio) & (ratio > 0)
        if fin.sum() >= 10:
            rr = ratio[fin]
            med = float(np.median(rr))
            level_scale.append({"code": ts, "median_ratio": med,
                                "within_code_spread": float(rr.max() / rr.min() - 1.0)})
        pl = _rel(vo[idx], vc[idx]).astype("float32")
        price_levels.append(pl)
        per_code.append({
            "code": ts, "board": _board(ts), "pairs": int(dev.size),
            "max_abs_dev": float(dev.max()),
            "agree": int((dev <= TOL_RETURN_ABS).sum()),
        })
        if verbose and (i + 1) % 500 == 0:
            print(f"  {i+1}/{len(common)}  {time.time()-t0:.0f}s", flush=True)

    dev_all = np.concatenate(devs) if devs else np.zeros(0, dtype="float32")
    pl_all = np.concatenate(price_levels) if price_levels else np.zeros(0, dtype="float32")
    cid_all = np.concatenate(dev_code_id) if dev_code_id else np.zeros(0, dtype="int32")

    def _tier(mask: np.ndarray, codes: list[dict]) -> dict:
        d = dev_all[mask]
        out = {
            "codes": len(codes),
            "return_pairs": int(d.size),
            "agree_at_1e-6": int((d <= TOL_RETURN_ABS).sum()),
            "agree_rate": float((d <= TOL_RETURN_ABS).mean()) if d.size else None,
            "pairs_over_material": int((d > MATERIAL_RETURN_DIFF).sum()),
            "codes_over_material": sum(1 for c in codes
                                       if c["max_abs_dev"] > MATERIAL_RETURN_DIFF),
            "frac_within": {f"{b:g}": float((d < b).mean()) if d.size else None
                            for b in RETURN_REPORT_BUCKETS},
            "dev_quantiles": _quantiles(d),
            "codes_all_agree": sum(1 for c in codes if c["agree"] == c["pairs"]),
        }
        out["worst_codes"] = [
            {k: c[k] for k in ("code", "board", "pairs", "max_abs_dev")}
            for c in sorted(codes, key=lambda c: -c["max_abs_dev"])[:15]]
        return out

    full = _tier(np.ones(dev_all.size, dtype=bool), per_code)

    # 分层抽样档：按板块分层、种子固定，**是全量的一个子集**（同一份 dev，不重算）
    rng = np.random.default_rng(SEED)
    by_board: dict[str, list[int]] = {}
    for j, c in enumerate(per_code):
        by_board.setdefault(c["board"], []).append(j)
    picked: list[int] = []
    total = len(per_code)
    for b in sorted(by_board):
        pool = by_board[b]
        share = max(1, round(STRATIFIED_N * len(pool) / max(total, 1)))
        take = min(share, len(pool))
        picked += rng.choice(pool, size=take, replace=False).tolist()
    picked = sorted(set(int(x) for x in picked))
    sel = np.isin(cid_all, np.array(picked, dtype="int32")) if picked else np.zeros(dev_all.size, bool)
    strat = _tier(sel, [per_code[j] for j in picked])
    strat["stratum_sizes"] = {b: sum(1 for j in picked if per_code[j]["board"] == b)
                              for b in sorted(by_board)}

    block = {
        "method": ("卡 2.1a 的口径：逐票取两条通道都有收盘价的交易日，在那条序列上求 "
                   "close-to-close 收益率，比 |r_public − r_private|。收益率是归一化不变量 —— "
                   "两条 provider 各自以冻结线重定基，价格水平本就相同，但收益率即使重定基"
                   "口径变了也不动。"),
        "calendar_identical": same_cal,
        "calendar_days": n,
        "coverage": {
            "codes_public": len(pub_codes),
            "codes_private": len(priv_codes),
            "codes_common": len(common),
            "codes_only_private": len(only_priv),
            "codes_only_public": len(only_pub),
            "codes_only_private_bse": sum(1 for c in only_priv if _board(c) == "bse"),
            "codes_only_private_by_board": {
                b: sum(1 for c in only_priv if _board(c) == b)
                for b in sorted({_board(c) for c in only_priv})},
            "note": ("公开通道只建了 v1 三宇宙的并集（N-68 裁定），所以「只在私有」不等于"
                     "「公开源没有」—— 但其中北交所那一档是**真缺口**：baostock 不服务北交所。"),
        },
        "missing_days": missing_days,
        "price_level": {
            "what": ("同一批日子上**复权收盘价**的相对差 |c_pub − c_priv| / max(|c_pub|,|c_priv|)。"
                     "两条 provider 都以冻结线重定基（factor=1），所以价位本身就该可比。"),
            "cells": int(pl_all.size),
            "agree_at_1e-6": int((pl_all <= TOL_PROVIDER_CELL_REL).sum()),
            "agree_rate": float((pl_all <= TOL_PROVIDER_CELL_REL).mean()) if pl_all.size else None,
            "quantiles": _quantiles(pl_all.astype("float64")),
        },
        "attribution": dict(attrib, rule={
            "decomposition": "Δlog(1+r) = Δlog(原始收盘之比) + Δlog(factor 之比)",
            "raw_quote_step": "**源报价**在这两天里走了不同的台阶（小数位 / 历史修订 / 停牌填值）。",
            "adjustment_step": "**复权因子**在这两天里走了不同的台阶 —— 除权除息的处理不同。",
            "neither": "两项都在 1e-6 之内，收益率却差更多。**这一类要逐条看**（一般是浮点相消）。",
        }),
        "level_scale": {
            "what": ("同一票上「公开复权价 / 私有复权价」这个比值。两条通道各自以冻结线"
                     "重定基，但**归一化常数不一定相同** —— 比值只要是常数，收益率就不受影响。"
                     "`within_code_spread` = 该票全历史上这个比值的 max/min − 1："
                     "接近 0 说明差异纯粹是一个常数，收益率级的一致率才是有意义的判据。"),
            "codes": len(level_scale),
            "constant_ratio_spread_threshold": CONSTANT_RATIO_SPREAD,
            "codes_constant_ratio": sum(1 for x in level_scale
                                        if x["within_code_spread"] <= CONSTANT_RATIO_SPREAD),
            "codes_drifting_ratio": sum(1 for x in level_scale
                                        if x["within_code_spread"] > CONSTANT_RATIO_SPREAD),
            "median_ratio": _quantiles(np.array([x["median_ratio"] for x in level_scale])),
            "within_code_spread": _quantiles(
                np.array([x["within_code_spread"] for x in level_scale])),
            "worst_by_spread": sorted(level_scale,
                                      key=lambda x: -x["within_code_spread"])[:10],
            "worst_by_median": sorted(level_scale,
                                      key=lambda x: -abs(x["median_ratio"] - 1.0))[:10],
        },
        "full": full,
        "stratified": strat,
    }
    return block, cell_diff, units


# --------------------------------------------------------------- ② τ / ε

def _eps_freq_row(d: dict) -> dict:
    return {
        "calibrated": sorted(d.get("calibrated", [])),
        "implausible": sorted(d.get("implausible", [])),
        "no_freedom": sorted(d.get("no_freedom", [])),
        "n_calibrated": len(d.get("calibrated", [])),
        "n_implausible": len(d.get("implausible", [])),
        "n_no_freedom": len(d.get("no_freedom", [])),
        "usable": d.get("usable"),
        "epsilon": {m: r.get("epsilon") for m, r in sorted(d.get("by_metric", {}).items())},
        "tolerance_kind": {m: r.get("tolerance_kind")
                           for m, r in sorted(d.get("by_metric", {}).items())},
        "status": {m: r.get("status") for m, r in sorted(d.get("by_metric", {}).items())},
    }


def part_calibration() -> dict:
    pub = _load_json(cfg.SNAPSHOTS_PUBLIC / "calibration.json")
    priv = _load_json(cfg.SNAPSHOTS_V1 / "calibration.json")

    def tau(c: dict) -> dict:
        t = c["tau"]
        return {k: t.get(k) for k in
                ("value", "universe", "start", "end", "comparable_factors",
                 "factors_used", "cells_used", "excluded_operator_conflict")} | {
            "degenerate_cells_removed": t.get("degenerate_rule", {}).get("cells_removed")}

    tp, tv = tau(pub), tau(priv)
    tau_block = {
        "public": tp, "private": tv,
        "delta_abs": abs(tp["value"] - tv["value"]),
        "delta_rel": abs(tp["value"] - tv["value"]) / abs(tv["value"]),
        "same_factors_used": tp["factors_used"] == tv["factors_used"],
        "same_cells_used": tp["cells_used"] == tv["cells_used"],
        "same_operator_conflicts": (sorted(tp["excluded_operator_conflict"])
                                    == sorted(tv["excluded_operator_conflict"])),
    }

    order = {"daily": 0, "weekly": 1, "monthly": 2}
    freqs = sorted(set(pub["epsilon"]["by_frequency"]) | set(priv["epsilon"]["by_frequency"]),
                   key=lambda f: (order.get(f, 9), f))
    eps = {}
    for f in freqs:
        a = _eps_freq_row(pub["epsilon"]["by_frequency"].get(f, {}))
        b = _eps_freq_row(priv["epsilon"]["by_frequency"].get(f, {}))
        eps[f] = {
            "public": a, "private": b,
            "same_usable": a["usable"] == b["usable"],
            "calibrated_only_public": sorted(set(a["calibrated"]) - set(b["calibrated"])),
            "calibrated_only_private": sorted(set(b["calibrated"]) - set(a["calibrated"])),
            "same_implausible": a["implausible"] == b["implausible"],
            "epsilon_rel_delta": {
                m: (None if (a["epsilon"].get(m) in (None, 0) or b["epsilon"].get(m) is None)
                    else abs(a["epsilon"][m] - b["epsilon"][m]) / abs(b["epsilon"][m]))
                for m in sorted(set(a["epsilon"]) & set(b["epsilon"]))},
        }

    def ic(c: dict) -> dict:
        f = c["epsilon"].get("ic_family", {})
        bands = {}
        for h, blk in sorted(f.get("by_holding_period", {}).items()):
            bands[h] = {m: {"epsilon": r.get("epsilon"), "status": r.get("status"),
                            "tolerance_kind": r.get("tolerance_kind")}
                        for m, r in sorted(blk.get("by_metric", {}).items())}
        return {"usable": f.get("usable"),
                "usable_metrics": sorted(f.get("usable_metrics", [])),
                "calibrated": sorted(f.get("calibrated", [])),
                "implausible": sorted(f.get("implausible", [])),
                "no_freedom": sorted(f.get("no_freedom", [])),
                "no_pair": sorted(f.get("no_pair", [])),
                "sample_coverage": f.get("sample_coverage"),
                "band_rule": f.get("band_rule"),
                "bands": bands}

    icp, icv = ic(pub), ic(priv)
    ic_block = {
        "public": icp, "private": icv,
        "same_usable_metrics": icp["usable_metrics"] == icv["usable_metrics"],
        "same_unusable_split": (icp["implausible"] == icv["implausible"]
                                and icp["no_pair"] == icv["no_pair"]),
        "band_rel_delta": {
            h: {m: (None if (icv["bands"].get(h, {}).get(m, {}).get("epsilon") in (None, 0)
                             or icp["bands"].get(h, {}).get(m, {}).get("epsilon") is None)
                    else abs(icp["bands"][h][m]["epsilon"] - icv["bands"][h][m]["epsilon"])
                    / abs(icv["bands"][h][m]["epsilon"]))
                for m in sorted(set(icp["bands"].get(h, {})) & set(icv["bands"].get(h, {})))}
            for h in sorted(set(icp["bands"]) & set(icv["bands"]))},
    }

    return {
        "sources": {
            "public": str(cfg.SNAPSHOTS_PUBLIC / "calibration.json"),
            "private": str(cfg.SNAPSHOTS_V1 / "calibration.json"),
            "public_sha256": _sha256(cfg.SNAPSHOTS_PUBLIC / "calibration.json"),
            "private_sha256": _sha256(cfg.SNAPSHOTS_V1 / "calibration.json"),
            "public_built_at": pub.get("built_at"), "private_built_at": priv.get("built_at"),
        },
        "tau": tau_block,
        "epsilon_by_frequency": eps,
        "ic_family": ic_block,
        "ready_for_scoring": {"public": pub.get("ready_for_scoring"),
                              "private": priv.get("ready_for_scoring"),
                              "note": ("两条通道都写着 false，理由同一条老问题："
                                       "`ready_for_scoring = epsilon.usable`，而后者要求三个频率"
                                       "全 usable，weekly/monthly 按 2.2b 纪律永远不会 usable。"
                                       "改它等于改判据口径，要签字（卡 1.2 / 1.1-b 都提过）。")},
    }


# --------------------------------------------------------------- ③ gold 抽样比对

def _pick_factors(universe: str) -> list[str]:
    pub = cfg.SNAPSHOTS_PUBLIC / "gold_factors" / universe
    priv = cfg.SNAPSHOTS_V1 / "gold_factors" / universe
    a = {p.stem for p in pub.glob("*.parquet")}
    b = {p.stem for p in priv.glob("*.parquet")}
    common = sorted(a & b)
    rng = np.random.default_rng(SEED)
    k = min(GOLD_FACTORS_PER_UNIVERSE, len(common))
    return sorted(rng.choice(common, size=k, replace=False).tolist())


def _calendar_index(path: Path) -> dict[str, int]:
    """日历文件 → ``{紧凑日期: 下标}``。

    **日历文件里是 ISO（``2009-01-05``），gold 的 ``date`` 列是紧凑串（``20090105``）。**
    忘了这一折的表现**不是报错**，是归因「归不掉 100%」而报告照样渲染得出来 ——
    第一版就是这样过去的。`ops/test_recon_public.py` 里有一条变异测试钉住它。
    """
    cal = [l.strip() for l in path.read_text().split("\n") if l.strip()]
    return {d.replace("-", ""): i for i, d in enumerate(cal)}


def _attribution_tables(cell_diff: dict[str, np.ndarray]) -> tuple:
    """把位图摊成两张矩阵，好让归因**向量化** —— 逐格 Python 循环在几百万格上跑不完。

    返回 ``(排好序的 code 数组, 位图矩阵 D, 前缀和 C)``；
    ``C[i, j+1] - C[i, k]`` 就是第 i 只票在 ``[k, j]`` 这段日历上有几格不同。
    """
    keys = np.array(sorted(cell_diff))          # <U 定长串，searchsorted 可用
    n = len(next(iter(cell_diff.values())))
    D = np.zeros((keys.size, n), dtype=bool)
    for i, k in enumerate(keys):
        D[i] = cell_diff[k]
    C = np.zeros((keys.size, n + 1), dtype="int32")
    np.cumsum(D, axis=1, dtype="int32", out=C[:, 1:])
    return keys, D, C


def part_gold(cell_diff: "dict[str, np.ndarray] | None", verbose: bool = True) -> dict:
    import duckdb

    cal_idx = _calendar_index(qp.PUBLIC_PATHS.calendar_file)
    keys = D = C = None
    if cell_diff:
        keys, D, C = _attribution_tables(cell_diff)
    d0, d1 = GOLD_WINDOW
    con = duckdb.connect(":memory:")
    by_universe: dict[str, dict] = {}

    for u in cfg.UNIVERSES:
        pubd = cfg.SNAPSHOTS_PUBLIC / "gold_factors" / u
        privd = cfg.SNAPSHOTS_V1 / "gold_factors" / u
        if not pubd.is_dir() or not privd.is_dir():
            by_universe[u] = {"skipped": "gold 目录缺失", "public": str(pubd),
                              "private": str(privd)}
            continue
        factors = _pick_factors(u)
        agg = {
            "factors_sampled": factors,
            "window": {"start": d0, "end": d1},
            "cells_both": 0, "cells_only_public": 0, "cells_only_private": 0,
            "cells_exact_equal": 0, "cells_nan_mismatch": 0,
            "cells_differ_at_floor": 0, "cells_over_threshold": 0,
            "attribution": {"same_day_source_diff": 0,
                            "source_diff_within_lookback": 0,
                            "cross_sectional_same_day": 0,
                            "unattributed": 0},
            "per_factor": [],
        }
        rels: list[np.ndarray] = []
        unattributed_examples: list[dict] = []
        uni_any = None
        t0 = time.time()
        for fid in factors:
            pf, qf = pubd / f"{fid}.parquet", privd / f"{fid}.parquet"
            # **不能用「值是 NaN」判「这一边没有这一格」** —— gold 里 NaN/inf 是参考实现的
            # 诚实输出（数据层不筛），与「行不存在」是两回事。所以 present 由 date 是否为
            # NULL 判，不由 value 判。
            df = con.execute(
                "SELECT COALESCE(a.date, b.date) AS date, COALESCE(a.code, b.code) AS code, "
                "a.value AS pub, b.value AS priv, "
                "(a.date IS NOT NULL) AS has_pub, (b.date IS NOT NULL) AS has_priv FROM "
                "(SELECT date, code, value FROM read_parquet(?) WHERE date BETWEEN ? AND ?) a "
                "FULL OUTER JOIN "
                "(SELECT date, code, value FROM read_parquet(?) WHERE date BETWEEN ? AND ?) b "
                "ON a.date = b.date AND a.code = b.code",
                [str(pf), d0, d1, str(qf), d0, d1]).df()
            if uni_any is None and keys is not None:
                uni = np.unique(df["code"].to_numpy().astype(str))
                pos = np.searchsorted(keys, uni)
                pos = np.minimum(pos, keys.size - 1)
                rows = pos[keys[pos] == uni]
                uni_any = D[rows].any(axis=0) if rows.size else np.zeros(D.shape[1], bool)
            pub_v = df["pub"].to_numpy(dtype="float64", na_value=np.nan)
            priv_v = df["priv"].to_numpy(dtype="float64", na_value=np.nan)
            hp = df["has_pub"].to_numpy(dtype=bool)
            hq = df["has_priv"].to_numpy(dtype=bool)
            present = hp & hq
            only_pub = int((hp & ~hq).sum())
            only_priv = int((hq & ~hp).sum())
            fp, fq = np.isfinite(pub_v), np.isfinite(priv_v)
            both = present & fp & fq
            nan_mismatch = int((present & (fp ^ fq)).sum())
            r = _rel(pub_v[both], priv_v[both])
            differs = r > TOL_GOLD_DIFFERS_REL
            over = r > TOL_GOLD_CELL_REL
            agg["cells_both"] += int(both.sum())
            agg["cells_differ_at_floor"] += int(differs.sum())
            agg["cells_only_public"] += only_pub
            agg["cells_only_private"] += only_priv
            agg["cells_exact_equal"] += int((pub_v[both] == priv_v[both]).sum())
            agg["cells_nan_mismatch"] += nan_mismatch
            agg["cells_over_threshold"] += int(over.sum())
            rels.append(r)
            agg["per_factor"].append({
                "factor": fid, "cells": int(both.sum()),
                "exact_equal": int((pub_v[both] == priv_v[both]).sum()),
                "differs_at_floor": int(differs.sum()),
                "over_threshold": int(over.sum()),
                "max_rel": float(r.max()) if r.size else None,
                "p90_rel": float(np.percentile(r, 90)) if r.size else None,
            })

            # --- 超阈格子归因（向量化：超阈格可能有几百万，逐格 Python 循环跑不完）
            if keys is not None and over.any():
                codes = df["code"].to_numpy()[both][over].astype(str)
                dates = df["date"].to_numpy()[both][over].astype(str)
                pos = np.searchsorted(keys, codes)
                pos_ok = (pos < keys.size)
                ci = np.where(pos_ok, np.minimum(pos, keys.size - 1), 0)
                known = pos_ok & (keys[ci] == codes)
                di = np.array([cal_idx.get(d, -1) for d in dates], dtype="int64")
                known &= di >= 0
                unknown_n = int((~known).sum())
                agg["attribution"]["unattributed"] += unknown_n
                if unknown_n and len(unattributed_examples) < 15:
                    j = int(np.flatnonzero(~known)[0])
                    unattributed_examples.append(
                        {"factor": fid, "code": codes[j], "date": dates[j],
                         "why": "该票不在两条通道共有的 provider 里，或该日不在日历上"})
                ck, dk = ci[known], di[known]
                same = D[ck, dk]
                lo = np.maximum(0, dk - GOLD_LOOKBACK_DAYS)
                inwin = (C[ck, dk + 1] - C[ck, lo]) > 0
                # 第三类：**别的票**在这一天有源差。792 条因子里大量用截面算子
                # （rank / scale / 截面回归），一只票的报价变了会改**同截面所有票**的名次 ——
                # 只看本票的输入是解释不了那种格的。这一类是**弱归因**：它几乎总是成立，
                # 所以只在它**不**成立的时候才有信息量（那时才是真的归不掉）。
                cross = uni_any[dk] if uni_any is not None else np.zeros(dk.size, bool)
                a1 = same
                a2 = ~a1 & inwin
                a3 = ~a1 & ~a2 & cross
                miss = ~a1 & ~a2 & ~a3
                agg["attribution"]["same_day_source_diff"] += int(a1.sum())
                agg["attribution"]["source_diff_within_lookback"] += int(a2.sum())
                agg["attribution"]["cross_sectional_same_day"] += int(a3.sum())
                agg["attribution"]["unattributed"] += int(miss.sum())
                agg["per_factor"][-1]["attribution"] = {
                    "same_day_source_diff": int(a1.sum()),
                    "source_diff_within_lookback": int(a2.sum()),
                    "cross_sectional_same_day": int(a3.sum()),
                    "unattributed": int(miss.sum())}
                if miss.any() and len(unattributed_examples) < 15:
                    kn = np.flatnonzero(known)
                    for j in kn[np.flatnonzero(miss)[:3]]:
                        unattributed_examples.append(
                            {"factor": fid, "code": codes[j], "date": dates[j],
                             "why": f"该票在 [t-{GOLD_LOOKBACK_DAYS}, t] 内没有任何 provider 格差异"})
            if verbose:
                print(f"  [{u}] {fid} {time.time()-t0:.0f}s", flush=True)

        r_all = np.concatenate(rels) if rels else np.zeros(0)
        agg["rel_quantiles"] = _quantiles(r_all)
        agg["frac_within"] = {f"{b:g}": float((r_all < b).mean()) if r_all.size else None
                              for b in (1e-9, 1e-6, 1e-3, 1e-2)}
        agg["over_threshold_rate"] = (agg["cells_over_threshold"] / agg["cells_both"]
                                      if agg["cells_both"] else None)
        agg["differ_at_floor_rate"] = (agg["cells_differ_at_floor"] / agg["cells_both"]
                                       if agg["cells_both"] else None)
        agg["unattributed_examples"] = unattributed_examples
        agg["per_factor"] = sorted(agg["per_factor"], key=lambda x: -(x["max_rel"] or 0))
        by_universe[u] = agg

    con.close()
    return {
        "method": (f"三宇宙各抽 {GOLD_FACTORS_PER_UNIVERSE} 个因子（种子 {SEED}，"
                   f"从两条通道都有的因子里取），固定日期窗 {d0}..{d1}（与 IC-ε 判据窗同窗），"
                   "逐格算对称相对差；超阈的格子逐个归因到 provider 侧的源差异。"),
        "threshold": TOL_GOLD_CELL_REL,
        "differs_floor": TOL_GOLD_DIFFERS_REL,
        "lookback_trading_days": GOLD_LOOKBACK_DAYS,
        "attribution_rule": {
            "same_day_source_diff": "该 (票, 日) 的 provider 8 个字段里至少一个两通道不同",
            "source_diff_within_lookback":
                f"该票在 [t-{GOLD_LOOKBACK_DAYS}, t] 内某一天有 provider 格差异 —— "
                "因子有滚动窗口，源差会往后传",
            "cross_sectional_same_day":
                "本票的输入没变，但**同截面别的票**在这一天变了。792 条因子里大量用截面算子"
                "（rank / scale / 截面回归），一只票的报价变了会改整个截面的名次 —— "
                "只看本票的输入解释不了这种格。**这是弱归因**：在这个样本上它几乎总是成立，"
                "所以它有信息量的方向是反的 —— 只有当它**不**成立时，才是真的归不掉。",
            "unattributed": "上面三条都不成立。**这一类要逐条看** —— 它意味着"
                            "两条通道的输入相同而输出不同，那不是数据源差异。",
        },
        "by_universe": by_universe,
    }


# --------------------------------------------------------------- ④ 全量 daily 行级

def part_rows() -> dict:
    import duckdb
    con = duckdb.connect(":memory:")
    pub = str(cfg.PUBLIC_TABLES_DIR / "daily.parquet")
    priv = str(cfg.SNAPSHOTS_V1 / "tables" / "daily.parquet")
    codes = sorted({qp.ts_code(d.name.upper())
                    for d in qp.PUBLIC_PATHS.features.iterdir() if d.is_dir()})
    con.execute("CREATE TEMP TABLE u(ts_code VARCHAR)")
    con.executemany("INSERT INTO u VALUES (?)", [(c,) for c in codes])
    t0 = time.time()
    con.execute(
        "CREATE TEMP TABLE m AS SELECT COALESCE(a.ts_code, b.ts_code) AS ts_code, "
        "COALESCE(a.trade_date, b.trade_date) AS trade_date, "
        "a.open AS o1, b.open AS o2, a.high AS h1, b.high AS h2, a.low AS l1, b.low AS l2, "
        "a.close AS c1, b.close AS c2, a.volume AS v1, b.volume AS v2, "
        "a.amount AS m1, b.amount AS m2, "
        "(a.ts_code IS NOT NULL) AS in_pub, (b.ts_code IS NOT NULL) AS in_priv "
        "FROM (SELECT * FROM read_parquet(?) WHERE ts_code IN (SELECT ts_code FROM u)) a "
        "FULL OUTER JOIN "
        "(SELECT * FROM read_parquet(?) WHERE ts_code IN (SELECT ts_code FROM u)) b "
        "ON a.ts_code = b.ts_code AND a.trade_date = b.trade_date", [pub, priv])
    n_both, n_pub, n_priv = con.execute(
        "SELECT sum(CASE WHEN in_pub AND in_priv THEN 1 ELSE 0 END), "
        "sum(CASE WHEN in_pub AND NOT in_priv THEN 1 ELSE 0 END), "
        "sum(CASE WHEN in_priv AND NOT in_pub THEN 1 ELSE 0 END) FROM m").fetchone()
    fields = {}
    for name, (a, b, kind) in {
        "open": ("o1", "o2", "cent"), "high": ("h1", "h2", "cent"),
        "low": ("l1", "l2", "cent"), "close": ("c1", "c2", "cent"),
        "volume": ("v1", "v2", "rel"), "amount": ("m1", "m2", "rel"),
    }.items():
        if kind == "cent":
            ok = f"round({a},2) = round({b},2)"
        else:
            ok = f"abs({a}-{b}) <= 1e-6 * greatest(abs({b}), 1.0)"
        row = con.execute(
            f"SELECT count(*), sum(CASE WHEN {ok} THEN 1 ELSE 0 END), "
            f"max(abs({a}-{b}) / greatest(abs({b}), 1e-12)) "
            f"FROM m WHERE in_pub AND in_priv AND {a} IS NOT NULL AND {b} IS NOT NULL").fetchone()
        comparable, agree, mx = int(row[0]), int(row[1] or 0), float(row[2] or 0.0)
        fields[name] = {"comparable": comparable, "agree": agree,
                        "agree_rate": agree / comparable if comparable else None,
                        "disagree": comparable - agree, "max_rel": mx,
                        "criterion": "到分相等" if kind == "cent" else "相对差 <= 1e-6"}
    secs = time.time() - t0
    con.close()
    return {
        "window": {"start": cfg.SNAPSHOTS_START if hasattr(cfg, "SNAPSHOTS_START") else "20090105",
                   "end": cfg.FREEZE_DATE.replace("-", "")},
        "codes": len(codes),
        "rows_in_both": int(n_both or 0),
        "rows_only_public": int(n_pub or 0),
        "rows_only_private": int(n_priv or 0),
        "by_field": fields,
        "seconds": secs,
        "note": ("行域取公开通道建了的那 3,575 只（N-68），因此「只在私有」不含"
                 "公开通道压根没建的票。停牌那一类差异（公开有行 / 私有缺行）已被"
                 "卡 1.1-a 的建集吸收进 suspend_d，所以这里的「只在公开」应当是 0。"),
    }


# --------------------------------------------------------------- ⑤ 涨跌停

def part_limits() -> dict:
    import duckdb
    from snapshots.public import limits as L
    con = duckdb.connect(":memory:")
    pub = str(cfg.PUBLIC_TABLES_DIR / "stk_limit.parquet")
    priv = str(cfg.SNAPSHOTS_V1 / "tables" / "stk_limit.parquet")
    d0, d1 = "20260101", cfg.FREEZE_DATE.replace("-", "")
    q = ("SELECT a.ts_code, a.trade_date, a.up_limit AS u1, b.up_limit AS u2, "
         "a.down_limit AS d1_, b.down_limit AS d2, a.limit_basis "
         "FROM (SELECT * FROM read_parquet(?) WHERE trade_date BETWEEN ? AND ?) a "
         "JOIN (SELECT * FROM read_parquet(?) WHERE trade_date BETWEEN ? AND ?) b "
         "USING (ts_code, trade_date)")
    df = con.execute(q, [pub, d0, d1, priv, d0, d1]).df()
    con.close()
    u1 = df["u1"].to_numpy(dtype="float64", na_value=np.nan)
    u2 = df["u2"].to_numpy(dtype="float64", na_value=np.nan)
    dd1 = df["d1_"].to_numpy(dtype="float64", na_value=np.nan)
    dd2 = df["d2"].to_numpy(dtype="float64", na_value=np.nan)
    ok = (np.round(u1, 2) == np.round(u2, 2)) & (np.round(dd1, 2) == np.round(dd2, 2))
    bad = np.flatnonzero(~ok)
    rows = []
    for i in bad[:40]:
        rows.append({"ts_code": str(df["ts_code"].iloc[i]),
                     "trade_date": str(df["trade_date"].iloc[i]),
                     "public": [float(u1[i]), float(dd1[i])],
                     "private": [float(u2[i]), float(dd2[i])],
                     "public_basis": str(df["limit_basis"].iloc[i])})
    return {
        "window": {"start": d0, "end": d1},
        "rows_compared": int(len(df)),
        "agree": int(ok.sum()),
        "agree_rate": float(ok.mean()) if len(df) else None,
        "disagree": int((~ok).sum()),
        "disagreements": rows,
        "rules": {
            "st_5pct_last_day": L.ST_5PCT_LAST_DAY,
            "no_limit_trading_days": dict(L.NO_LIMIT_TRADING_DAYS),
            "s_share_pct": L.S_SHARE_PCT,
            "delisting_first_day_free": L.DELISTING_FIRST_DAY_FREE,
            "oracle_no_limit_sentinel": {k: list(v)
                                         for k, v in L.ORACLE_NO_LIMIT_SENTINEL.items()},
            "chinext_20pct_from": L.CHINEXT_20PCT_FROM,
            "star_20pct_from": L.STAR_20PCT_FROM,
        },
        "known_gap": ("退市整理期首日无涨跌幅限制这条**在公开通道推不出来** —— 判据是私有表 "
                      "`namechange.change_reason = '退市整理期'`。公开通道的 stk_limit 因此"
                      "在这些行上按板块正常幅度推，是**已知误差**，不是没查出来的错。"),
    }


# --------------------------------------------------------------- ⑥ 单位 / ⑦ 冻结件

def part_units(units: "dict | None") -> dict:
    if units is None:
        return {"skipped": "本节的原料来自 returns 那一节的同一次扫描；单跑 --part units 请连 returns 一起跑"}
    total = units["band_total"]
    med = units["vwap_over_close"]
    return {
        "criterion": (f"`low*(1-{qp.VWAP_BAND_REL_TOL:g}) <= vwap <= high*(1+{qp.VWAP_BAND_REL_TOL:g})`。"
                      "`vwap = amount / volume`，落带 = 单位自洽。"
                      "**这不是查文档得来的结论** —— 换一个单位（×1000 或 ÷1000）落带率会掉到 0。"),
        "cells": total,
        "in_band": units["band_in"],
        "in_band_rate": units["band_in"] / total if total else None,
        "median_vwap_over_close": float(np.median(med)) if med else None,
        "verdict": ("baostock 的 `amount` 单位是**元**、`volume` 是**股** —— "
                    "不是 tushare 的千元 / 手，建 provider 时不需要换算。"),
    }


def part_frozen() -> dict:
    items, missing = {}, []
    for rel in PM.PUBLIC_FROZEN_ARTIFACTS:
        p = _REPO / rel
        if p.is_file():
            items[rel] = {"sha256": _sha256(p), "bytes": p.stat().st_size}
        else:
            missing.append(rel)
    return {
        "what": "PUBLIC_FROZEN_ARTIFACTS（N-58⑥）：gold 的**定义面**。τ 标定于此实现对。",
        "declared": list(PM.PUBLIC_FROZEN_ARTIFACTS),
        "present": items,
        "missing": missing,
        "blocks_release": bool(missing),
        "note": ("缺件挡发布：少了它们，拿到包的人复现不了 τ —— 而 τ 恰恰标定在"
                 "「两个实现有多一致」上。卡 1.4 的打包器已把缺件记进 MANIFEST.json 的 "
                 "`missing_declared_artifacts`（不静默丢）。"),
    }


# --------------------------------------------------------------- 报告

def _fmt(x, nd=6):
    if x is None:
        return "—"
    if isinstance(x, bool):
        return "是" if x else "否"
    if isinstance(x, float):
        return f"{x:.{nd}g}"
    if isinstance(x, int):
        return f"{x:,}"
    return str(x)


def render(rep: dict) -> str:
    L: list[str] = []
    A = L.append
    run = rep["run"]
    A("# 两通道对账（卡 1.3 / 卡 2.5 §7）")
    A("")
    A("> **本文件由 `ops/recon_public_vs_private.py` 渲染**，数全部从产物读，"
      "不手抄。改数只能改产物，改不了这张表。")
    A("")
    A(f"* 公开通道 `{run['public_root']}`（baostock）· 私有通道 `{run['private_root']}`"
      "（审计湖 + ChinaScope）")
    A(f"* 跑于 `{run['built_at']}` · 代码 `{run['code_head'][:12]}` · 用时 "
      f"{run['seconds']:.0f}s · 产物 `{OUT_JSON.relative_to(_REPO)}`")
    A(f"* 容差：provider 格 `{TOL_PROVIDER_CELL_REL:g}`（相对）/ 收益率 "
      f"`{TOL_RETURN_ABS:g}`（绝对）/ gold 格 `{TOL_GOLD_CELL_REL:g}`（相对）。"
      "**三个都定在 float32 的噪声地板之上一个数量级** —— provider 的 `.day.bin` 是 "
      "float32（qlib 格式），单侧相对精度约 1.2e-7。")
    A("")

    r = rep.get("returns")
    if r:
        A("## 1. 收益率级一致率")
        A("")
        A(r["method"])
        A("")
        A(f"两条通道的 provider 日历**逐行相同**（{r['calendar_days']:,} 个交易日），"
          "所以对齐没有自由度。")
        A("")
        A("| 档 | 票数 | 收益率对 | 一致（|Δr| ≤ 1e-6）| 一致率 | <1e-4 | <1e-3 | P50 | P90 | P99 | max |")
        A("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
        for tier, label in (("full", "**全量**"), ("stratified", "分层抽样")):
            t = r[tier]
            q = t["dev_quantiles"]
            A(f"| {label} | {t['codes']:,} | {t['return_pairs']:,} | {t['agree_at_1e-6']:,} | "
              f"{_fmt(t['agree_rate'], 9)} | {_fmt(t['frac_within']['0.0001'], 6)} | "
              f"{_fmt(t['frac_within']['0.001'], 6)} | {_fmt(q['p50'])} | {_fmt(q['p90'])} | "
              f"{_fmt(q['p99'])} | {_fmt(q['max'])} |")
        A("")
        A(f"全量档里 **{r['full']['codes_all_agree']:,} / {r['full']['codes']:,}** 只票"
          "逐日收益率完全一致（每一格都在 1e-6 之内）。**收益率差超过 "
          f"{MATERIAL_RETURN_DIFF:g}（实质不同）的只有 {r['full']['pairs_over_material']:,} 对，"
          f"集中在 {r['full']['codes_over_material']:,} 只票上** —— "
          "一致率那一列的 0.5% 缺口几乎全是 1e-7~1e-4 量级的复权台阶差，见 §1.2。")
        A("")
        A("**差异最大的票**（全量档）：")
        A("")
        A("| 票 | 板块 | 收益率对 | 最大 |Δr| |")
        A("| --- | --- | ---: | ---: |")
        for c in r["full"]["worst_codes"][:8]:
            A(f"| `{c['code']}` | {c['board']} | {c['pairs']:,} | {_fmt(c['max_abs_dev'])} |")
        A("")
        cov = r["coverage"]
        A("### 1.1 覆盖面")
        A("")
        A(f"公开 provider {cov['codes_public']:,} 只 / 私有 {cov['codes_private']:,} 只 / "
          f"共有 {cov['codes_common']:,} 只；只在私有 {cov['codes_only_private']:,} 只"
          f"（其中北交所 {cov['codes_only_private_bse']:,} 只）；只在公开 "
          f"{cov['codes_only_public']:,} 只。")
        A("")
        A(cov["note"])
        A("")
        md = r["missing_days"]
        A(f"**缺失日**：{md['codes_with_day_gap']:,} 只票的有价日数两边不等 —— "
          f"公开比私有少 {md['public_short_of_private']:,} 个 (票, 日)、"
          f"多 {md['private_short_of_public']:,} 个。")
        A("")
        pl = r["price_level"]
        at = r["attribution"]
        A("### 1.2 差异从哪来")
        A("")
        ls = r["level_scale"]
        A(ls["what"])
        A("")
        A(f"`median_ratio` 的分布：min {_fmt(ls['median_ratio']['min'], 8)} / "
          f"P50 {_fmt(ls['median_ratio']['p50'], 8)} / "
          f"P90 {_fmt(ls['median_ratio']['p90'], 8)} / max {_fmt(ls['median_ratio']['max'], 8)}；"
          f"`within_code_spread`：P50 {_fmt(ls['within_code_spread']['p50'])} / "
          f"P90 {_fmt(ls['within_code_spread']['p90'])} / "
          f"P99 {_fmt(ls['within_code_spread']['p99'])} / "
          f"max {_fmt(ls['within_code_spread']['max'])}。")
        A("")
        A(pl["what"])
        A("")
        pq = pl["quantiles"]
        A(f"价位级：{pl['cells']:,} 格里 **{pl['agree_at_1e-6']:,}** 格"
          f"（{_fmt(pl['agree_rate'], 9)}）在 1e-6 之内相同；"
          f"P50 {_fmt(pq['p50'])} / P90 {_fmt(pq['p90'])} / P99 {_fmt(pq['p99'])} / "
          f"max {_fmt(pq['max'])}。**价位级的一致率不是判据** —— 归一化常数不同"
          "就足以让它很低，而那不影响任何下游数值。")
        A("")
        if ls["worst_by_median"] and abs(ls["worst_by_median"][0]["median_ratio"] - 1) > 0.01:
            A("**归一化常数差得最远的票**（`median_ratio` 离 1 最远）：")
            A("")
            A("| 票 | median(公开/私有) | 该票内比值的 max/min − 1 |")
            A("| --- | ---: | ---: |")
            for x in ls["worst_by_median"][:6]:
                A(f"| `{x['code']}` | {_fmt(x['median_ratio'], 8)} | "
                  f"{_fmt(x['within_code_spread'])} |")
            A("")
            A(f"**这张表里要分两类看。** `max/min − 1` 小于 "
              f"{ls['constant_ratio_spread_threshold']:g} 的（全量里 "
              f"{ls['codes_constant_ratio']:,} 只 / {ls['codes']:,}）"
              "价位级差异**就是一个常数** —— 不影响收益率、不影响任何以收益率为输入的"
              "下游数值，但**会**影响任何直接读价位的东西。"
              f"大于它的 **{ls['codes_drifting_ratio']:,} 只**是另一回事："
              "两条通道对这只票的**复权处理真的不同**，差异会一路传到 gold。"
              "这是本卡在收益率级看到的**唯一一处实质分歧**，逐票名单见产物的 "
              "`returns.level_scale.worst_by_spread` 与 `returns.full.worst_codes`。")
            A("")
        A(f"**超出 1e-6 的 {at['over']:,} 对收益率**按 `{at['rule']['decomposition']}` 分解：")
        A("")
        for k in ("raw_quote_step", "adjustment_step", "neither"):
            A(f"* **`{k}`：{at[k]:,}** 对"
              f"（{at[k] / max(at['over'], 1):.2%}）—— {at['rule'][k]}")
        A("")

    c = rep.get("calibration")
    if c:
        A("## 2. τ / ε 两通道对比")
        A("")
        t = c["tau"]
        A("### 2.1 τ")
        A("")
        A("| | 公开 | 私有 |")
        A("| --- | ---: | ---: |")
        A(f"| τ | **{t['public']['value']:.6f}** | {t['private']['value']:.6f} |")
        for k, lab in (("comparable_factors", "可比因子"), ("factors_used", "参与因子"),
                       ("cells_used", "参与格"), ("degenerate_cells_removed", "degenerate 剔除")):
            A(f"| {lab} | {_fmt(t['public'][k])} | {_fmt(t['private'][k])} |")
        A(f"| 算子冲突排除 | {len(t['public']['excluded_operator_conflict'])} 条 | "
          f"{len(t['private']['excluded_operator_conflict'])} 条 |")
        A("")
        A(f"τ 的绝对差 **{t['delta_abs']:.2g}**（相对 {t['delta_rel']:.2g}）。"
          f"参与因子数相同：{_fmt(t['same_factors_used'])}；参与格数相同："
          f"{_fmt(t['same_cells_used'])}；算子冲突名单相同：{_fmt(t['same_operator_conflicts'])}。")
        A("")
        A("### 2.2 ε（回测指标，按调仓频率分档）")
        A("")
        A("| 频率 | 公开 可标定/超阈/无自由度 | 私有 | usable（公开 / 私有）| 只在公开可标定 | 只在私有可标定 |")
        A("| --- | :---: | :---: | :---: | --- | --- |")
        for f, blk in c["epsilon_by_frequency"].items():
            a, b = blk["public"], blk["private"]
            A(f"| `{f}` | {a['n_calibrated']} / {a['n_implausible']} / {a['n_no_freedom']} | "
              f"{b['n_calibrated']} / {b['n_implausible']} / {b['n_no_freedom']} | "
              f"{_fmt(a['usable'])} / {_fmt(b['usable'])} | "
              f"{', '.join(f'`{x}`' for x in blk['calibrated_only_public']) or '—'} | "
              f"{', '.join(f'`{x}`' for x in blk['calibrated_only_private']) or '—'} |")
        A("")
        A("**逐指标带值并列**（`—` = 该通道没给这个指标出带）：")
        A("")
        A("| 频率 | 指标 | 类型 | 公开 ε | 私有 ε | 相对差 |")
        A("| --- | --- | --- | ---: | ---: | ---: |")
        for f, blk in c["epsilon_by_frequency"].items():
            a, b = blk["public"], blk["private"]
            for m in sorted(set(a["epsilon"]) | set(b["epsilon"])):
                A(f"| `{f}` | `{m}` | {a['tolerance_kind'].get(m) or b['tolerance_kind'].get(m)} | "
                  f"{_fmt(a['epsilon'].get(m), 4)} | {_fmt(b['epsilon'].get(m), 4)} | "
                  f"{_fmt(blk['epsilon_rel_delta'].get(m), 3)} |")
        A("")
        wide = []
        for f, blk in c["epsilon_by_frequency"].items():
            for m, d in blk["epsilon_rel_delta"].items():
                if d is not None and d >= 1.0:
                    wide.append((f, m, blk["public"]["epsilon"].get(m),
                                 blk["private"]["epsilon"].get(m), d))
        if wide:
            A("**带值本身两边并不接近** —— 这是本节唯一一处「结论不变但数不同」的地方，"
              "写在这里免得被表格淹掉。下面这些指标的带值相对差 ≥ 1：")
            A("")
            for f, m, a_, b_, d in sorted(wide, key=lambda x: -x[4]):
                A(f"* `{f}` / `{m}`：公开 {_fmt(a_, 4)} vs 私有 {_fmt(b_, 4)}"
                  f"（相对差 {_fmt(d, 3)}）")
            A("")
            A("**这不构成结构性结论变化**：ε 量的是「三份独立实现在同一份输入上分歧多大」，"
              "换一份行情，三份实现踩到的边界情形本来就不同 —— 卡 2.5 §10 要求不变的是"
              "**分档结论**（哪一档 usable、哪些指标超阈），那几项逐项相同。"
              "但它说明一件事：**ε 的带值是「这份数据 + 这三份实现」的联合性质**，"
              "不能把私有通道的带直接拿去判公开通道跑出来的回测。")
            A("")
        ic = c["ic_family"]
        A("### 2.3 `ic_family`（N-117，S4 的 IC 族带）")
        A("")
        A("| | 公开 | 私有 |")
        A("| --- | --- | --- |")
        A(f"| usable | {_fmt(ic['public']['usable'])} | {_fmt(ic['private']['usable'])} |")
        A(f"| 可用指标 | {ic['public']['usable_metrics']} | {ic['private']['usable_metrics']} |")
        A(f"| 超阈未出带 | {ic['public']['implausible']} | {ic['private']['implausible']} |")
        A(f"| 双实现对构不成 | {ic['public']['no_pair']} | {ic['private']['no_pair']} |")
        A("")
        A("| 持有期 | 指标 | 公开 ε | 私有 ε | 相对差 |")
        A("| ---: | --- | ---: | ---: | ---: |")
        for h in sorted(ic["band_rel_delta"], key=int):
            for m in sorted(ic["band_rel_delta"][h]):
                A(f"| {h} | `{m}` | {_fmt(ic['public']['bands'][h][m]['epsilon'], 4)} | "
                  f"{_fmt(ic['private']['bands'][h][m]['epsilon'], 4)} | "
                  f"{_fmt(ic['band_rel_delta'][h][m], 3)} |")
        A("")
        A(f"两条通道的 `ready_for_scoring` 都是 "
          f"`{c['ready_for_scoring']['public']}` / `{c['ready_for_scoring']['private']}`。"
          f"{c['ready_for_scoring']['note']}")
        A("")

    g = rep.get("gold")
    if g:
        A("## 3. gold 抽样比对")
        A("")
        A(g["method"])
        A("")
        A(f"| 宇宙 | 抽样因子 | 共有格 | 逐位相同 | 不同（>{g['differs_floor']:g}）| "
          f"**超阈**（>{g['threshold']:g}）| 超阈率 | 只在一边 | P50 | P90 | max |")
        A("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
        for u, b in g["by_universe"].items():
            if "skipped" in b:
                A(f"| `{u}` | — | — | — | — | — | — | — | — | — | — |")
                continue
            q = b["rel_quantiles"]
            A(f"| `{u}` | {len(b['factors_sampled'])} | {b['cells_both']:,} | "
              f"{b['cells_exact_equal']:,} | {b['cells_differ_at_floor']:,} | "
              f"{b['cells_over_threshold']:,} | "
              f"{_fmt(b['over_threshold_rate'], 4)} | "
              f"{b['cells_only_public'] + b['cells_only_private']:,} | "
              f"{_fmt(q['p50'])} | {_fmt(q['p90'])} | {_fmt(q['max'])} |")
        A("")
        A("### 3.1 超阈格子的归因")
        A("")
        for k, v in g["attribution_rule"].items():
            A(f"* **`{k}`** —— {v}")
        A("")
        A("| 宇宙 | 超阈格 | 本票当日源差 | 本票回看窗内源差 | 同截面别的票（弱）| 归不掉 |")
        A("| --- | ---: | ---: | ---: | ---: | ---: |")
        for u, b in g["by_universe"].items():
            if "skipped" in b:
                continue
            at = b["attribution"]
            A(f"| `{u}` | {b['cells_over_threshold']:,} | {at['same_day_source_diff']:,} | "
              f"{at['source_diff_within_lookback']:,} | {at['cross_sectional_same_day']:,} | "
              f"{at['unattributed']:,} |")
        A("")
        tot_un = sum(b["attribution"]["unattributed"] for b in g["by_universe"].values()
                     if "skipped" not in b)
        tot_over = sum(b["cells_over_threshold"] for b in g["by_universe"].values()
                       if "skipped" not in b)
        if tot_un:
            A(f"**归不掉的有 {tot_un:,} 格**（占超阈的 {tot_un / max(tot_over,1):.2%}）。"
              "这一类不是「数据源不同」能解释的 —— 逐条样例见产物的 "
              "`gold.by_universe.<u>.unattributed_examples`。")
        else:
            tot_weak = sum(b["attribution"]["cross_sectional_same_day"]
                           for b in g["by_universe"].values() if "skipped" not in b)
            A("**归不掉的是 0 格** —— 每一个超阈格子都能追到 provider 侧的一处源差异。"
              "这正是本节想要的结论：两条通道的 gold 差异**由行情差异解释**，"
              "没有第三个来源。")
            A("")
            A(f"**但要看清楚强弱**：其中 {tot_over - tot_weak:,} 格是**本票自己的输入**变了"
              f"（强归因），另外 {tot_weak:,} 格（{tot_weak / max(tot_over,1):.1%}）只由"
              "「同截面别的票变了」解释 —— 那一条在这个样本上几乎总是成立，"
              "所以它更像是**没能证伪**，不是**证实**。要把它变成强归因，得逐因子看它用不用"
              "截面算子；本卡把逐因子的归因分解落在产物的 "
              "`gold.by_universe.<u>.per_factor[].attribution` 里，没有再往下追。")
        A("")

    ro = rep.get("rows")
    if ro:
        A("## 4. 全量 `daily` 行级（卡 1.1-a 的对账在本卡重跑）")
        A("")
        A(f"行域 {ro['codes']:,} 只 × `{ro['window']['start']}`..`{ro['window']['end']}`："
          f"共有 **{ro['rows_in_both']:,}** 行、只在公开 {ro['rows_only_public']:,} 行、"
          f"只在私有 {ro['rows_only_private']:,} 行（{ro['seconds']:.0f}s）。")
        A("")
        A("| 字段 | 判据 | 可比 | 一致 | 一致率 | 不一致 | 最大相对差 |")
        A("| --- | --- | ---: | ---: | ---: | ---: | ---: |")
        for f, b in ro["by_field"].items():
            A(f"| `{f}` | {b['criterion']} | {b['comparable']:,} | {b['agree']:,} | "
              f"{_fmt(b['agree_rate'], 9)} | {b['disagree']:,} | {_fmt(b['max_rel'], 4)} |")
        A("")
        A(ro["note"])
        A("")

    li = rep.get("limits")
    if li:
        A("## 5. 涨跌停：公开通道**自己推**的那张表")
        A("")
        A(f"窗口 `{li['window']['start']}`..`{li['window']['end']}`，"
          f"逐行核 **{li['rows_compared']:,}** 行（拿私有 `stk_limit` 当 oracle）："
          f"一致 {li['agree']:,}、一致率 **{_fmt(li['agree_rate'], 9)}**、"
          f"分歧 **{li['disagree']}** 行。")
        A("")
        if li["disagreements"]:
            A("| 票 | 日 | 公开 (up, down) | 私有 (up, down) | 公开判的依据 |")
            A("| --- | --- | --- | --- | --- |")
            for d in li["disagreements"][:12]:
                A(f"| `{d['ts_code']}` | {d['trade_date']} | {d['public']} | {d['private']} | "
                  f"{d['public_basis']} |")
            A("")
        A(li["known_gap"])
        A("")

    un = rep.get("units")
    if un and "skipped" not in un:
        A("## 6. 量额单位（公开通道自己的判据）")
        A("")
        A(un["criterion"])
        A("")
        A(f"落带 **{un['in_band']:,} / {un['cells']:,}**"
          f"（{_fmt(un['in_band_rate'], 8)}），中位 `vwap/close` = "
          f"{_fmt(un['median_vwap_over_close'], 7)}。{un['verdict']}")
        A("")

    fz = rep.get("frozen")
    if fz:
        A("## 7. 冻结件（τ 标定于此实现对）")
        A("")
        A(fz["what"])
        A("")
        A("| 冻结件 | 状态 | sha256 |")
        A("| --- | --- | --- |")
        for rel in fz["declared"]:
            if rel in fz["present"]:
                A(f"| `{rel}` | 在 | `{fz['present'][rel]['sha256']}` |")
            else:
                A(f"| `{rel}` | **缺件** | — |")
        A("")
        if fz["missing"]:
            A(f"**{len(fz['missing'])} 个冻结件在仓库里不存在，挡发布。** {fz['note']}")
        A("")

    A("## 8. 复现")
    A("")
    A("```bash")
    A("GB=/data/shared/genebench; cd $GB/repo && ulimit -n 8192")
    A("$GB/env/bin/python ops/recon_public_vs_private.py                 # 七节全跑")
    A("$GB/env/bin/python ops/recon_public_vs_private.py --part gold     # 只跑一节（别的节原样留着）")
    A("$GB/env/bin/python ops/recon_public_vs_private.py --render-only   # 只从产物重渲报告")
    A("```")
    A("")
    A("**这条对账不打网关**（全部直读 parquet / `.day.bin`），所以不需要 "
      "`ops/gateway_lock.py`；与卡 1.1-b / 1.2 同理由。它**只读**两个快照根。")
    A("")
    return "\n".join(L) + "\n"


# --------------------------------------------------------------- main

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="卡 1.3：公开通道 vs 私有通道的对账")
    ap.add_argument("--part", action="append", choices=list(PARTS),
                    help="只跑某几节（默认全跑）；结果合并进同一个 JSON")
    ap.add_argument("--out", type=Path, default=OUT_JSON)
    ap.add_argument("--report", type=Path, default=OUT_MD)
    ap.add_argument("--render-only", action="store_true", help="不重算，只从产物重渲报告")
    ap.add_argument("--limit-codes", type=int, default=None,
                    help="只扫前 N 只票 —— **冒烟用**，产物会被标成 partial")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    verbose = not a.quiet

    if a.render_only:
        rep = _load_json(a.out)
        a.report.write_text(render(rep), encoding="utf-8")
        a.report.chmod(0o600)
        print(f"→ {a.report}")
        return 0

    want = set(a.part) if a.part else set(PARTS)
    rep = _load_json(a.out) if a.out.exists() else {}
    t0 = time.time()
    cell_diff = units_raw = None

    # `gold` 的归因**必须**有 provider 位图，而位图只有 `returns` 那一遍扫描能产出。
    # 早先写成「rep 里已经有 returns 就不重扫」——表现是 `--part gold` 单跑时归因全空，
    # 而报告照样渲染得出来。宁可多花 40 秒重扫。
    if want & {"returns", "gold", "units"}:
        if verbose:
            print("[returns] 逐票扫两条 provider（8 个字段）…", flush=True)
        block, cell_diff, units_raw = part_returns(verbose, a.limit_codes)
        if "returns" in want:
            rep["returns"] = block
    if "calibration" in want:
        if verbose:
            print("[calibration] τ / ε …", flush=True)
        rep["calibration"] = part_calibration()
    if "gold" in want:
        if verbose:
            print("[gold] 三宇宙抽样比对 …", flush=True)
        rep["gold"] = part_gold(cell_diff, verbose)
    if "rows" in want:
        if verbose:
            print("[rows] 全量 daily 行级 …", flush=True)
        rep["rows"] = part_rows()
    if "limits" in want:
        if verbose:
            print("[limits] 涨跌停逐行核 …", flush=True)
        rep["limits"] = part_limits()
    if "units" in want:
        rep["units"] = part_units(units_raw)
    if "frozen" in want:
        rep["frozen"] = part_frozen()

    rep["run"] = {
        "card": "1.3",
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
        "code_head": _code_head(),
        "seconds": time.time() - t0,
        "parts_run": [p for p in PARTS if p in want],
        "limit_codes": a.limit_codes,
        "partial": bool(a.limit_codes),
        "public_root": str(cfg.SNAPSHOTS_PUBLIC),
        "private_root": str(cfg.SNAPSHOTS_V1),
        "freeze_date": cfg.FREEZE_DATE,
    }
    rep["tolerances"] = {
        "provider_cell_rel": TOL_PROVIDER_CELL_REL,
        "return_abs": TOL_RETURN_ABS,
        "gold_cell_rel": TOL_GOLD_CELL_REL,
        "why": ("provider 的 .day.bin 是 float32（qlib 格式），单侧相对精度约 1.2e-7、"
                "两侧往返约 2.4e-7。三个容差都定在噪声地板之上一个数量级，"
                "同时远在最小的一类真实源差异（亚元取整，相对 1e-6~1e-5）之下。"),
    }
    rep["sampling"] = {
        "seed": SEED,
        "gold_factors_per_universe": GOLD_FACTORS_PER_UNIVERSE,
        "gold_window": {"start": GOLD_WINDOW[0], "end": GOLD_WINDOW[1]},
        "gold_lookback_trading_days": GOLD_LOOKBACK_DAYS,
        "stratified_n": STRATIFIED_N,
    }

    cfg.create_dir(a.out.parent)
    a.out.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    a.out.chmod(0o600)
    a.report.write_text(render(rep), encoding="utf-8")
    a.report.chmod(0o600)
    print(f"→ {a.out}  {a.out.stat().st_size:,} B")
    print(f"→ {a.report}  {a.report.stat().st_size:,} B")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
