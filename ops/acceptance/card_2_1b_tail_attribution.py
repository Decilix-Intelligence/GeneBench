# -*- coding: utf-8 -*-
"""卡 2.1b 附加分析：τ 尾部归因。

    cd $REPO && $GENEBENCH_ROOT/env/bin/python ops/acceptance/card_2_1b_tail_attribution.py

**为什么要做这一步**：τ 的定义是"两个**诚实**实现之间能有多不一致"。
如果尾部其实是**一处已识别的引擎约定差异**造成的，那 τ 量到的就不是实现容差，
而是"我们的第二实现用了另一种 ts_rank 约定" —— 把它写进 τ 会让阈值过松。
所以在签字之前必须先问：**尾部是不是可归因的？**
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import genebench_config as cfg  # noqa: E402
from reference import factor_crosscheck as fc  # noqa: E402
from reference import factor_exec as fx  # noqa: E402

OUT = cfg.OPS / "acceptance" / "card_2.1b_tail_attribution.json"
REPORT = cfg.REPORTS / "factor_crosscheck_2.1b.md"
TSRANK = re.compile(r"\bTS[_]?RANK\b", re.I)


def p(a, q):
    return float(np.percentile(a, q)) if len(a) else float("nan")


def main() -> int:
    cells = pd.read_parquet(cfg.SNAPSHOTS_V1 / "crosscheck" / "rank_ic_cells_csi300.parquet")
    rep = json.loads(fc.REPORT_JSON.read_text(encoding="utf-8"))
    recs, _ = fx.load_records()
    by = {r["id"]: r for r in recs}
    ids = [x["id"] for x in rep["rows"]]
    uses = {i for i in ids if TSRANK.search(str(by[i]["expression"]))}

    k = cells[np.isfinite(cells["rho"]) & ~cells["degenerate"]]

    def scope(name, df):
        r = df["rho"].to_numpy()
        return {"scope": name, "cells": int(len(df)),
                "factors": int(df["factor_id"].nunique()),
                "p01": p(r, 1), "p10": p(r, 10), "p50": p(r, 50), "mean": float(r.mean())}

    scopes = [
        scope("全部 159 条（当前 τ）", k),
        scope("剔掉源方言用 Ts_Rank 的 13 条", k[~k["factor_id"].isin(uses)]),
        scope("只看用 Ts_Rank 的 13 条", k[k["factor_id"].isin(uses)]),
    ]
    for b in sorted(k["backend"].unique()):
        kb = k[k["backend"] == b]
        scopes.append(scope(f"{b} 全部", kb))
        scopes.append(scope(f"{b} 剔 Ts_Rank", kb[~kb["factor_id"].isin(uses)]))

    low = sorted([x for x in rep["rows"]
                  if x["mean_rho_kept"] == x["mean_rho_kept"] and x["mean_rho_kept"] < 0.9],
                 key=lambda z: z["mean_rho_kept"])
    for x in low:
        x["uses_ts_rank"] = x["id"] in uses
        x["translation_notes"] = str(by[x["id"]].get("translation_notes") or "")

    out = {
        "card": "2.1b-attribution",
        "question": "τ 的尾部是不是可归因到一处已识别的引擎约定差异？",
        "finding": {
            "mechanism": (
                "两个引擎的 ts_rank 归一化不同：面板求值器用 "
                "`rolling(w, min_periods=w).rank(pct=True)` → 值域 (0, 1]；"
                "KunQuant 的 `TsRank` 用 `num_less + (num_eq+1)/2` → 值域 [1, w]。"
                "实测同一列 volume：面板 0.0312…1.0000，KunQuant 的 WQAlpha35 −0…14880。"),
            "when_it_matters": (
                "只在 ts_rank 的**绝对量纲**参与组合时才改变截面序："
                "`1 - ts_rank(·)`、`max(rank(·), ts_rank(·))`、`rank(·) + ts_rank(·)`、"
                "`pow(ts_rank(·), ·)`。若 ts_rank 被 `rank()` 包住或只做常数缩放，截面序不变，ρ ≡ 1。"),
            "comparable_factors_using_ts_rank": sorted(uses),
            "n_using": len(uses),
            "gold_blast_radius": {
                "kunquant_factors_using_ts_rank": 24,
                "of_total_kunquant": 82,
                "note": ("这 24 条的 **gold** 也是用 KunQuant 的原位约定算的。"
                         "WQ101 原文里 `alpha073 = max(rank(·), Ts_Rank(·, 17))` —— "
                         "把归一化的截面 rank 与 ts_rank 放进同一个 max，"
                         "只有当两者都在 [0,1] 时才说得通；否则 ts_rank 永远赢。"
                         "**这是 gold 可能有缺陷的证据，不只是 τ 的问题** —— 见 N-21。"),
            },
        },
        "scopes": scopes,
        "factors_below_0.9": low,
        "unexplained": [x["id"] for x in low
                        if not x["uses_ts_rank"] and "epair" not in x["translation_notes"]
                        and "ormalize" not in x["translation_notes"]],
        "documented_source_repairs": [
            {"id": x["id"], "mean_rho": x["mean_rho_kept"], "notes": x["translation_notes"]}
            for x in low if ("epair" in x["translation_notes"] or "ormalize" in x["translation_notes"])],
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT.chmod(0o600)

    # 追加一节到报告
    L = ["", "---", "", "## 10. τ 尾部归因（签字前必须先看这一节）", "",
         "**问题**：τ 的定义是「两个**诚实**实现之间能有多不一致」。"
         "如果尾部其实是**一处已识别的引擎约定差异**造成的，"
         "那 τ 量到的不是实现容差，而是「我们的第二实现用了另一种约定」——写进 τ 会让阈值过松。", "",
         "**机制（已实测确认，不是推测）**：", "",
         "| 引擎 | `ts_rank` 实现 | 实测值域 |", "| --- | --- | --- |",
         "| 面板求值器（实现 B） | `rolling(w, min_periods=w).rank(pct=True)` | `(0, 1]`（volume 实测 0.0312…1.0000）|",
         "| KunQuant（实现 A = gold） | `num_less + (num_eq+1)/2` | `[1, w]`（WQAlpha35 实测 −0…14880）|", "",
         "只在 `ts_rank` 的**绝对量纲**参与组合时才改变截面序 —— "
         "`1 - ts_rank(·)`、`max(rank(·), ts_rank(·))`、`rank(·) + ts_rank(·)`、`pow(ts_rank(·), ·)`；"
         "若被 `rank()` 包住或只做常数缩放，截面序不变、ρ ≡ 1。", "",
         "**量化**：", "",
         "| 口径 | 因子 | 格数 | P10（τ） | P01 | P50 |",
         "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for s in scopes:
        L.append(f"| {s['scope']} | {s['factors']} | {s['cells']:,} | **{s['p10']:.6f}** | "
                 f"{s['p01']:.4f} | {s['p50']:.6f} |")
    L += ["",
          f"**13 条（占 159 的 8.2%）解释了两个后端层之间几乎全部的差距**："
          f"`qlib_kunquant_loader` 剔掉它们之后从 0.827044 升到 0.954298，"
          f"而 `qlib_expression` 几乎不动（0.987855 → 0.986509）。", "",
          "**mean ρ < 0.9 的 11 条，逐条归因**：", "",
          "| 因子 | 后端 | mean ρ | 用 Ts_Rank | 归因 |",
          "| --- | --- | ---: | :---: | --- |"]
    for x in low:
        if x["uses_ts_rank"]:
            why = "ts_rank 约定差异"
        elif "epair" in x["translation_notes"] or "ormalize" in x["translation_notes"]:
            why = f"**目录刻意修补过源文**：{x['translation_notes'][:70]}"
        else:
            why = "**未解释**"
        L.append(f"| `{x['id']}` | `{x['backend']}` | {x['mean_rho_kept']:+.4f} | "
                 f"{'是' if x['uses_ts_rank'] else '否'} | {why} |")
    L += ["",
          "**对 gold 的爆炸半径（这一条比 τ 更要紧）**：82 条 KunQuant 因子里 **24 条**用到 `ts_rank`，"
          "它们的 **gold 也是用 KunQuant 的原位约定算的**。",
          "WQ101 原文的 `alpha073 = max(rank(·), Ts_Rank(·, 17))` —— "
          "把归一化的截面 `rank` 与 `Ts_Rank` 放进同一个 `max`，"
          "**只有当两者都在 [0,1] 时才说得通**，否则原位的 `ts_rank` 永远赢。",
          "**这是 gold 可能有缺陷的证据，不只是 τ 的问题。** 已登记 **N-21**，等裁定：",
          "修它会改变这 24 条的 gold，进而改变 τ —— 所以必须在签 τ 之前决定，不能之后补。", ""]
    s = REPORT.read_text(encoding="utf-8")
    if "## 10. τ 尾部归因" not in s:
        REPORT.write_text(s.rstrip() + "\n" + "\n".join(L) + "\n", encoding="utf-8")
    print(f"→ {OUT}\n→ {REPORT}（已追加 §10）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
