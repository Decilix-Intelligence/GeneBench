# -*- coding: utf-8 -*-
"""把卡 2.1b 的互检 JSON 渲染成签字用的报告（分位数表 + 直方图）。

    cd $REPO && $GENEBENCH_ROOT/env/bin/python ops/render_crosscheck_report.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import genebench_config as cfg  # noqa: E402
from reference import factor_crosscheck as fc  # noqa: E402

OUT = cfg.REPORTS / "factor_crosscheck_2.1b.md"
PS = ("p01", "p05", "p10", "p25", "p50", "p75", "p90", "p99")


def qrow(name: str, d: dict) -> str:
    if not d:
        return f"| {name} | — | — | — | — | — | — | — | — | — | — |"
    cells = " | ".join(f"{d.get(k, float('nan')):.6f}" for k in PS)
    return (f"| {name} | {d.get('n', 0):,} | {d.get('mean', float('nan')):.6f} | "
            f"{cells} | {d.get('min', float('nan')):.6f} |")


def bar(frac: float, width: int = 34) -> str:
    n = int(round(frac * width))
    return "█" * n + "·" * (width - n)


def hist_block(title: str, hist: list, total: int) -> list[str]:
    L = [f"**{title}**（n = {total:,}）", "", "```"]
    for b in hist:
        L.append(f"[{b['lo']:>6.3f}, {b['hi']:>6.3f})  {bar(b['frac'])}  "
                 f"{b['frac']:7.3%}  {b['n']:>9,}")
    L.append("```")
    L.append("")
    return L


def render() -> Path:
    r = json.loads(fc.REPORT_JSON.read_text(encoding="utf-8"))
    t = r["tau_candidates"]
    c = r["contamination"]
    D = r["distributions"]
    L: list[str] = []
    A = L.append

    A("# 卡 2.1b 报告：792 条因子三路后端执行 + 双实现互检秩相关分布")
    A("")
    A(f"宇宙 `{r['universe']}` · 窗口 `{r['start']}` … `{r['end']}` · "
      f"生成于 `{r['built_at']}` · 用时 {r['elapsed_s']}s")
    A("")
    A("> **这份报告的三个数是 τ 的候选值，等签字。**"
      " 口径按 2026-09-01 第二批冻结（F-1…F-5），全文见 `ops/specs/GeneBench秩相关与标定口径_v1.md`。")
    A("")

    A("## 1. τ 的三种取法（F-3 要求的三个数）")
    A("")
    A("| 取法 | 值 | 说明 |")
    A("| --- | ---: | --- |")
    A(f"| **① 逐日分布 P10（= τ）** | **{t['pooled_factor_x_day_p10']:.6f}** | "
      f"全因子 × 全交易日二维分布的 P10。判定粒度 = (因子, 日)，标定粒度也是 (因子, 日) |")
    A(f"| ② 因子级 P10（先对时间取均值） | {t['factor_level_mean_p10']:.6f} | "
      f"**不作 τ**，只作参照 |")
    A(f"| ②' 因子级 P10（先对时间取中位） | {t['factor_level_median_p10']:.6f} | 同上 |")
    A(f"| **③ ① − ②** | **{t['delta_pooled_minus_factor_mean']:+.6f}** | 见下面的解读 |")
    A("")
    delta = t["delta_pooled_minus_factor_mean"]
    A(f"**差值解读**：① 比 ② 低 {abs(delta):.6f}。"
      "差越大，说明失配**越集中在少数日子**而不是均匀摊在时间上 —— "
      "先对时间平均会把那些日子藏进均值，而 S3 的 Fid% 恰恰是逐日判的。")
    A("")

    A("## 2. 分位数表（三种分布）")
    A("")
    A("| 分布 | n | mean | " + " | ".join(PS) + " | min |")
    A("| --- | ---: | ---: |" + " ---: |" * (len(PS) + 1))
    A(qrow("逐 (因子,日) —— **剔 degenerate 后**（τ 的样本）", D["pooled_kept"]))
    A(qrow("逐 (因子,日) —— 剔除前", D["pooled_raw_before_degenerate_removal"]))
    A(qrow("因子级（时间均值）", D["factor_level_mean"]))
    A(qrow("因子级（时间中位）", D["factor_level_median"]))
    A("")

    A("## 3. 分布图")
    A("")
    L += hist_block("逐 (因子, 日)，剔 degenerate 后 —— **τ 就取自这条分布的 P10**",
                    D["pooled_kept_hist"], D["pooled_kept"].get("n", 0))
    L += hist_block("逐 (因子, 日)，剔除前（对照，看污染）",
                    D["pooled_raw_hist"], D["pooled_raw_before_degenerate_removal"].get("n", 0))
    L += hist_block("因子级（时间均值）", D["factor_level_mean_hist"],
                    D["factor_level_mean"].get("n", 0))

    A("## 4. degenerate 排除前后的 τ 对比（污染程度）")
    A("")
    A("| | 值 |")
    A("| --- | ---: |")
    A(f"| 剔除前 τ | {c['tau_before_degenerate_removal']:.6f} |")
    A(f"| **剔除后 τ** | **{c['tau_after_degenerate_removal']:.6f}** |")
    A(f"| 位移 | {c['shift']:+.6f} |")
    A(f"| 被剔的格数 | {c['cells_removed']:,} / {r['cells_total']:,}（{c['cells_removed_frac']:.3%}）|")
    A("")
    u = r["unique_value_ratio_observed"]
    A(f"**阈值落点**：实测 `min(唯一值数A, 唯一值数B) / 截面有效标的数` 的分布 —— "
      f"P0.1 = {u.get('p00', u.get('p0', float('nan'))):.4f}、"
      f"P1 = {u.get('p01', float('nan')):.4f}、P5 = {u.get('p05', float('nan')):.4f}、"
      f"P10 = {u.get('p10', float('nan')):.4f}、P50 = {u.get('p50', float('nan')):.4f}；"
      f"低于签字指定阈值 {fc.DEGENERATE_UNIQUE_RATIO:.0%} 的占 **{u['frac_below_threshold']:.3%}**。")
    A("")
    A(f"**阈值来源**：{r['methodology']['degenerate_threshold_source']}")
    A("")

    A("## 5. 剔除率的两个维度（F-5）")
    A("")
    A("**按后端**：")
    A("")
    A("| 后端 | 因子数 | 格数 | degenerate 率 |")
    A("| --- | ---: | ---: | ---: |")
    for b, v in r["per_backend"].items():
        A(f"| `{b}` | {v['factors']} | {v['cells']:,} | {v['degenerate_rate']:.3%} |")
    A("")
    A("**按日**：")
    A("")
    dd = r["degenerate_by_day"]
    A(f"共 {dd['days']:,} 个交易日；剔除率分位 "
      + " · ".join(f"P{k[1:]} = {v:.3%}" for k, v in dd["rate_quantiles"].items()
                   if k.startswith("p")))
    A("")
    A("最差 10 天：")
    A("")
    A("| 日期 | 剔除率 | 剔/总 |")
    A("| --- | ---: | ---: |")
    for row in dd["worst_10_days"]:
        A(f"| {row['date']} | {row['rate']:.2%} | {row['degen']}/{row['cells']} |")
    A("")
    df = r["degenerate_by_factor"]
    A(f"**全窗 degenerate 的因子（进 N-17 首批测试样本）**：{len(df['all_window_degenerate'])} 条")
    if df["all_window_degenerate"]:
        A("")
        A("```")
        for x in df["all_window_degenerate"]:
            A(f"  {x}")
        A("```")
    A("")
    if df["rate_above_50pct"]:
        A(f"**剔除率 > 50% 的因子**：{len(df['rate_above_50pct'])} 条")
        A("")
        A("| 因子 | 后端 | 剔除率 |")
        A("| --- | --- | ---: |")
        for x in df["rate_above_50pct"][:20]:
            A(f"| `{x['id']}` | `{x['backend']}` | {x['rate']:.2%} |")
        A("")

    A("## 6. 按后端对分层的分布（先报分布，不预设结论）")
    A("")
    A("| 后端 | 因子 | 逐日 P10 | 逐日 P50 | 逐日 mean | 因子级均值 P10 | degenerate 率 |")
    A("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for b, v in r["per_backend"].items():
        p, f2 = v["pooled"], v["factor_level_mean"]
        A(f"| `{b}` | {v['factors']} | **{v['tau_pooled_p10']:.6f}** | "
          f"{p.get('p50', float('nan')):.6f} | {p.get('mean', float('nan')):.6f} | "
          f"{f2.get('p10', float('nan')):.6f} | {v['degenerate_rate']:.3%} |")
    A("")
    for b, v in r["per_backend"].items():
        L += hist_block(f"`{b}` 逐 (因子, 日) 分布", v["pooled_hist"], v["pooled"].get("n", 0))

    A("## 7. 互检不上的那些，以及为什么")
    A("")
    A("| 类别 | 条数 | 说明 |")
    A("| --- | ---: | --- |")
    sc = r["skipped_counts"]
    A(f"| `same_engine` | {sc['same_engine']} | `qlib_panel_loader` 的 66 条：A/B 会落在**同一个引擎**上，"
      f"是自证式比较，混进 τ 的样本会把 τ 往上拉 |")
    A(f"| `parse_fail` | {sc['parse_fail']} | 源方言原文解析不了（三元 `?:`、`SEQUENCE`、"
      f"`local_core_v1` 本来就是 qlib 语法）|")
    A(f"| `eval_fail` | {sc['eval_fail']} | 解析得动但面板求值器没有那个算子（`ADV20` / `SUMAC` / `SELF` 等）|")
    A(f"| `no_gold` | {sc['no_gold']} | gold 里没有该因子 |")
    A(f"| `no_overlap` | {sc['no_overlap']} | 窗口内没有一个有效截面 |")
    A("")
    A(f"**可比 {r['comparable_factors']} 条**（实施稿要求 ≥ {r['min_required']}）。")
    A("")

    A("## 8. 最差 20 条（τ 的下界藏在这里）")
    A("")
    A("| 因子 | 族 | 后端 | 时间均值 ρ | 时间中位 ρ | 该因子 P10 | 最小 ρ | 有效日 | degenerate 率 |")
    A("| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for x in r["worst_20_factors"]:
        A(f"| `{x['id']}` | {x['family']} | `{x['backend']}` | {x['mean_rho_kept']:.4f} | "
          f"{x['median_rho_kept']:.4f} | {x['p10_rho_kept']:.4f} | {x['min_rho_kept']:.4f} | "
          f"{x['days_kept']:,} | {x['degenerate_rate']:.2%} |")
    A("")
    A("## 9. 复现")
    A("")
    A("```bash")
    A("export GENEBENCH_ROOT=/data/shared/genebench")
    A("cd $GENEBENCH_ROOT/repo && ulimit -n 8192")
    A(f"$GENEBENCH_ROOT/env/bin/python -m reference.factor_exec "
      f"--universe {r['universe']} --start {r['start']} --end {r['end']}")
    A(f"$GENEBENCH_ROOT/env/bin/python -m reference.factor_crosscheck "
      f"--universe {r['universe']} --start {r['start']} --end {r['end']}")
    A("$GENEBENCH_ROOT/env/bin/python ops/render_crosscheck_report.py")
    A("$GENEBENCH_ROOT/env/bin/python -m pytest ops/test_factor_exec.py -q")
    A("```")
    A("")
    A(f"逐格明细（{r['cells_total']:,} 行）落 `{r['cells_parquet']}`。")
    A("")
    cfg.create_dir(OUT.parent)
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    OUT.chmod(0o600)
    return OUT


if __name__ == "__main__":
    print(render())
