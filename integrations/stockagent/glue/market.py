# -*- coding: utf-8 -*-
"""数据端 —— 全部经网关，一个主机名都不写死。

StockAgent 的原生形态是一个**完全封闭的模拟市场**：股票 A/B/C/D 是虚构的，
初值、三年财报、季报文本全部写死在 `util.py` 与 `prompt/agent_prompt.py` 里，
运行期**一次外部取数都没有**。所以本接入的数据端不是「把它的取数换掉」，
而是「把它虚构的那部分换成真的」：

* 标的：`/universe` 的 PIT 成分（题面 `universe` 与 `as_of`），与题面给的因子面板取交集；
* 参考价：`/bars`，`fields` 显式给（`close`,`volume`）；
* 可交易性：`/tradability`，逐日单日（决定哪些格子写 `null`）；
* 交易日：`/calendar`；
* 财报：**本环境没有** → `/nodata/fundamentals` 留痕一次，prompt 里写 `[NO_DATA]`。

**窗口内前视的防线在这里**：agent 在模拟第 d 天看到的价量与因子值，
一律只到第 d 天（含）为止。网关那一层只挡 `as_of` 之后的东西，
「窗口之内、信号日之后」这一段它看不见 —— 那条线必须由接入层自己守。
"""
from __future__ import annotations

import json
import pathlib
from typing import Any

import pandas as pd

import genebench_client as gb
from genebench_client import nodata as _nodata
from genebench_client.codes import iso_date, to_lake

BARS_FIELDS = ["close", "volume"]


class Market:
    """一次运行的全部行情事实。构造时取完，之后**只按日切片**。"""

    def __init__(self, cli, *, universe: str, as_of: str, start: str, end: str,
                 codes: list[str], days: list[str]) -> None:
        self.cli = cli
        self.universe = universe
        self.as_of = as_of
        self.codes = list(codes)
        self.days = list(days)
        self.start, self.end = start, end
        self.bars = cli.bars(codes, start, end, fields=BARS_FIELDS)
        self._close: dict[tuple[str, str], float] = {}
        self._volume: dict[tuple[str, str], float] = {}
        if not self.bars.empty:
            for _, r in self.bars.iterrows():
                key = (str(r["date"]), str(r["code"]))
                if pd.notna(r.get("close")):
                    self._close[key] = float(r["close"])
                if pd.notna(r.get("volume")):
                    self._volume[key] = float(r["volume"])
        self._tradable: dict[tuple[str, str], str | None] = {}
        for d in self.days:
            td = cli.tradability(codes, d)
            for c in codes:
                self._tradable[(d, c)] = None
            if not td.empty:
                for _, r in td.iterrows():
                    self._tradable[(str(r["date"]), str(r["code"]))] = (
                        None if pd.isna(r.get("status")) else str(r["status"]))
        self.fundamentals_traced = _nodata.trace(
            cli, "fundamentals", "stockagent.prompt.FIRST_DAY_FINANCIAL_REPORT",
            note="upstream ships hardcoded fictional statements; this environment has no source")

    def close(self, day: str, code: str) -> float | None:
        return self._close.get((day, code))

    def last_close_upto(self, day: str, code: str) -> float | None:
        """第 d 天（含）之前最后一个有收盘价的日子。**不许越过 d** —— 窗口内前视。"""
        for d in reversed([x for x in self.days if x <= day]):
            v = self._close.get((d, code))
            if v is not None:
                return v
        hist = sorted(d for (d, c) in self._close if c == code and d <= day)
        return self._close[(hist[-1], code)] if hist else None

    def tradable(self, day: str, code: str) -> bool:
        """`no_data` 与「产物里根本没这一行」都算不可交易 —— 那些格子写 `null`。"""
        st = self._tradable.get((day, code))
        return st is not None and st != "no_data"

    def brief(self, day: str, mapping: dict[str, str],
              factors: "Factors | None" = None) -> str:
        """给 agent 看的当日市场简报。**只到 day（含）为止。**"""
        lines = ["The stocks in this market are real listed A-share companies.",
                 "Symbol mapping and the most recent market data available to you today:"]
        past = [d for d in self.days if d <= day]
        for slot in sorted(mapping):
            code = mapping[slot]
            lines.append(f"  Stock {slot} = {code}")
            for d in past[-5:]:
                px, vol = self._close.get((d, code)), self._volume.get((d, code))
                lines.append(
                    f"    {d}  close={'n/a' if px is None else round(px, 4)}"
                    f"  volume={'n/a' if vol is None else int(vol)}"
                    f"  tradable={'yes' if self.tradable(d, code) else 'no'}")
            if factors is not None:
                for fid in factors.ids:
                    v = factors.value(fid, day, code)
                    lines.append(f"    factor {fid} @{day} = "
                                 f"{'n/a' if v is None else round(v, 6)}")
        lines.append("Company financial statements: [NO_DATA] "
                     "(this environment provides no fundamentals source; "
                     "do not assume any figures).")
        return "\n".join(lines)


class Factors:
    """题面 `inputs[]` 点名的因子面板。读的是本地文件，不经网关（它们是夹具）。"""

    def __init__(self, inputs_dir: pathlib.Path) -> None:
        self.dir = inputs_dir
        self.ids: list[str] = []
        self._v: dict[str, dict[tuple[str, str], float]] = {}
        manifest = inputs_dir / "manifest.json"
        entries: list[dict[str, Any]] = []
        if manifest.exists():
            raw = json.loads(manifest.read_text(encoding="utf-8"))
            entries = raw if isinstance(raw, list) else raw.get("factors", raw.get("items", []))
        for ent in entries:
            fid = str(ent.get("factor_id") or ent.get("id") or "")
            rel = str(ent.get("path") or "")
            p = (inputs_dir / pathlib.Path(rel).name) if rel else None
            if not fid or p is None or not p.exists():
                continue
            df = pd.read_parquet(p)
            self.ids.append(fid)
            # **归一在这里做一次**：题面给的因子面板用的是 `20260105` + `SH600000`
            # （紧凑日期 + qlib/面板写法），而网关一路用的是 `2026-01-05` + `600000.SH`。
            # 不归一的后果是**一次不报错的空 join** —— 每个格子都查不到因子值，
            # 于是每个格子都判「三条因子全空 → null」，产物是一张全 null 的面板，
            # 而**产物上完全看不出来哪里错了**（演练实测：8 格全 null，smoke4.log）。
            self._v[fid] = {(iso_date(r["date"]), to_lake(str(r["code"]))): float(r["value"])
                            for _, r in df.iterrows() if pd.notna(r.get("value"))}

    @property
    def codes(self) -> set[str]:
        out: set[str] = set()
        for m in self._v.values():
            out |= {c for (_, c) in m}
        return out

    def value(self, fid: str, day: str, code: str) -> float | None:
        return self._v.get(fid, {}).get((day, code))

    def all_missing(self, day: str, code: str) -> bool:
        """三条因子在这个格子上全空 —— 题面点名的 `null` 条件之一。"""
        return all(self.value(f, day, code) is None for f in self.ids) if self.ids else False


def pick_codes(cli, universe: str, as_of: str, factors: Factors, k: int) -> list[str]:
    """选 k 只标的：PIT 成分 ∩ 因子面板，按代码排序取前 k。

    **确定性**（排序取前 k，不随机）是有意的：换一次运行就换一批标的，
    两臂之间、两次运行之间都没法比。
    """
    members = cli.members(universe, as_of)
    pool = [c for c in members if c in factors.codes] if factors.ids else members
    if not pool:
        pool = members
    return sorted(pool)[:k]
