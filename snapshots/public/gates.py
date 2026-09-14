# -*- coding: utf-8 -*-
"""卡 2.5 公开通道的**前置门**（裁定 2026-09-04，N-58② / ③）。

两道门，都在「从公开源建 gold」**之前**跑：

* **单位门**（B0②）：`low <= amount/volume <= high` 的行占比 ≥ 99%。
  这条判据**比任何文档核对都硬** —— tushare 原生 `amount` 是千元、`vol` 是手，
  直接相除得到的数差 10 倍；**社区 release 的 `amount` 仍是千元**
  （卡 2.1a 实测 `amount_社区/amount_湖 = 0.001`，4221 天里只有 1 个取值）。
  `vwap = amount/volume` 直接依赖这个归一 —— 换源不做同样变换，
  792 条里凡是用 `vwap` 的全部差 1000 倍，**而 gold 会照常算出数**。
* **前收门**（B0③）：涨跌停推导的前收**取 `daily.pre_close`**，
  不取 `stk_limit.pre_close` —— 后者在私有湖里**全为 NULL**（实测）。

**不过即停并记 BLOCKED，不放宽判据。**
"""
from __future__ import annotations

from dataclasses import dataclass

#: 与卡 2.1a **同一个常量**。抄一份到这里会漂，而漂的表现是
#: 「公开通道过了门、私有通道没过」，两边都不报错。
from snapshots.qlib_provider import VWAP_BAND_REL_TOL

#: 单位门的通过线。卡 2.1a 在私有湖上实测 **99.9843%**（逐年均 > 99.6%）。
#: 99% 是**放宽后**的通过线 —— 公开源的停牌/异常行占比可能不同，
#: 但差 1000 倍时这个比率会掉到 **0%**，所以 99% 与 99.98% 在判别力上等价。
VWAP_BAND_MIN_RATIO: float = 0.99


class PublicChannelBlocked(RuntimeError):
    """公开通道的前置门没过。**停下记 BLOCKED，不放宽判据。**"""


@dataclass(frozen=True)
class BandReport:
    rows: int
    in_band: int
    ratio: float
    median_vwap_over_close: float | None

    @property
    def passed(self) -> bool:
        return self.rows > 0 and self.ratio >= VWAP_BAND_MIN_RATIO


def vwap_band_report(df) -> BandReport:
    """`low <= amount/volume <= high` 的行占比（相对容差与卡 2.1a 同）。

    只看 `volume > 0` 的行 —— `volume <= 0` 时 vwap 记 NULL（2.1a 口径），
    把它们算进分母会让比率随停牌天数变化，而那与单位对不对无关。
    """
    import numpy as np
    need = ("low", "high", "close", "volume", "amount")
    miss = [c for c in need if c not in df.columns]
    if miss:
        raise PublicChannelBlocked(f"单位门缺列 {miss} —— 缺列不是「过了」")
    vol = df["volume"].astype("float64").to_numpy()
    amt = df["amount"].astype("float64").to_numpy()
    lo = df["low"].astype("float64").to_numpy()
    hi = df["high"].astype("float64").to_numpy()
    cl = df["close"].astype("float64").to_numpy()
    ok_rows = np.isfinite(vol) & (vol > 0) & np.isfinite(amt) & np.isfinite(lo) & np.isfinite(hi)
    n = int(ok_rows.sum())
    if n == 0:
        raise PublicChannelBlocked("单位门：没有 volume>0 的可判行 —— 零行不是「过了」")
    vwap = amt[ok_rows] / vol[ok_rows]
    tol = VWAP_BAND_REL_TOL
    lo_ok = vwap >= lo[ok_rows] * (1 - tol)
    hi_ok = vwap <= hi[ok_rows] * (1 + tol)
    in_band = int((lo_ok & hi_ok).sum())
    med = None
    c = cl[ok_rows]
    good = np.isfinite(c) & (c != 0)
    if good.any():
        med = float(np.median(vwap[good] / c[good]))
    return BandReport(rows=n, in_band=in_band, ratio=in_band / n,
                      median_vwap_over_close=med)


def assert_vwap_band(df, *, source: str) -> BandReport:
    """**公开 provider 建成后的第一道门**（B2）。不过即抛。"""
    rep = vwap_band_report(df)
    if not rep.passed:
        raise PublicChannelBlocked(
            f"单位门未过（源={source}）：`low <= amount/volume <= high` 只在 "
            f"{rep.ratio:.4%} 的行上成立（要求 ≥ {VWAP_BAND_MIN_RATIO:.0%}，"
            f"可判行 {rep.rows}）；中位 vwap/close = {rep.median_vwap_over_close}。"
            f"\\n差 1000 倍时这个比率是 0%，差 10 倍时也接近 0% —— "
            f"**这不是精度问题，是单位没归一**。停下记 BLOCKED，不要放宽这条线。")
    return rep


# --------------------------------------------------------------- 前收（B0③）

#: 涨跌停推导的**前收来源**。
#:
#: **不是 `stk_limit.pre_close`** —— 私有湖里那一列**全为 NULL**（实测），
#: 而卡 2.5 §3 原文写的是「按板块规则从**前收盘**推」。输入假设因此改为 `daily.pre_close`。
#: 公开源（baostock）的日线也带 `preclose`，同一位置。
PRE_CLOSE_SOURCE: str = "daily.pre_close"
PRE_CLOSE_FORBIDDEN: tuple[str, ...] = ("stk_limit.pre_close",)


def assert_pre_close_source(source: str) -> None:
    if source in PRE_CLOSE_FORBIDDEN:
        raise PublicChannelBlocked(
            f"前收不能取 {source} —— 私有湖里那一列全为 NULL（实测）。"
            f"取 {PRE_CLOSE_SOURCE}（公开源同一位置叫 preclose）")
    if source != PRE_CLOSE_SOURCE:
        raise PublicChannelBlocked(
            f"前收来源 {source!r} 未登记 —— 换来源要改 `PRE_CLOSE_SOURCE` 并说明，"
            f"不是在调用点传一个别的字符串")
