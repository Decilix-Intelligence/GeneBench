# -*- coding: utf-8 -*-
"""生成 gold 因子面板的数据卡。

    cd $REPO && $GENEBENCH_ROOT/env/bin/python ops/mk_gold_data_card.py

**由代码生成，不要直接改 .md** —— 重建即丢（M1 收尾踩过）。
"""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import genebench_config as cfg
from reference import factor_exec as fx
from reference import operator_flags as of

OUT = cfg.DATA_CARDS / "gold_factors.md"


def main() -> int:
    mans = {}
    for u in cfg.UNIVERSES_PIT:
        p = fx.GOLD_DIR / u / "manifest.json"
        if p.exists():
            mans[u] = json.loads(p.read_text(encoding="utf-8"))
    if not mans:
        raise SystemExit("一个 gold manifest 都没有")
    any_m = next(iter(mans.values()))
    susp = of.gold_suspect()
    defe = of.gold_defective()

    L = []; A = L.append
    A("# 数据卡：gold 因子面板（卡 2.1b）")
    A("")
    A(f"落点 `{fx.GOLD_DIR}` · 窗口 `{any_m['start']}` … `{any_m['end']}` · "
      f"provider digest `{any_m['provider']['digest'][:16]}…`")
    A("")
    A("> **本文件由 `ops/mk_gold_data_card.py` 生成。** 直接改 `.md` 会在下次重建时丢。")
    A("")
    A("## 1. 规模")
    A("")
    A("| 宇宙 | 交易日 | 行数 | 字节 | 因子 | 三路后端失败 |")
    A("| --- | ---: | ---: | ---: | ---: | ---: |")
    for u, m in mans.items():
        w = m["write"]
        fail = sum(v["failed"] for v in m["per_backend"].values())
        A(f"| `{u}` | {m['trading_days']:,} | {w['rows']:,} | {w['bytes']:,} | "
          f"{w['factors']} | {fail} |")
    A("")
    A("每因子一个 parquet，长表 `(date, code, value)`，`value` 为 **float64**，"
      "只保留当日在成分内的格。")
    A("")
    A("## 2. ⚠ 能力边界：这批 gold 算不出什么（N-23）")
    A("")
    A("**这一节必须在 M3 出题前被看见** —— 否则 S5/S6/S7 的题面可能要求系统交付"
      "**我们自己都算不出来的指标**，那题就不成立。")
    A("")
    A("| 指标族 | 能不能算 | 原因 |")
    A("| --- | :---: | --- |")
    A("| 年化收益 / 波动 / Sharpe / Sortino / MDD / Calmar / 换手 / 胜率 | ✅ | 都从组合逐日收益自己算，不经过基准 |")
    A("| IC / RankIC / 分位单调性 / Top-Bottom spread | ✅ | 只需要因子值与前向收益 |")
    A("| **IR / alpha / 超额收益 / 信息比率** | ❌ | **v1 provider 没有指数标的** —— instruments 取自 `universe_pit`，里面只有股票，`SH000300` 不存在 |")
    A("| 卡 2.1 里 5 条 `point_in_time_benchmark_or_fama_french_inputs_unavailable` 的 blocked 因子 | ❌ | 同源：需要 MKT/SMB/HML 序列 |")
    A("")
    A("**卡 2.2b 的参考回测用「等权宇宙收益」当基准，那是权宜，不是 v1 的正式基准定义。**")
    A("它只为让 qlib 的 `PortfolioMetrics` 能初始化；ε 用到的指标**没有一项经过基准**。")
    A("**不要让它悄悄变成正式基准** —— 要正式基准就得先把指数写进 provider（会改 provider 的 sha256）。")
    A("")
    A("## 3. ⚠ 检查的覆盖限度：这批数据里可能还有我们看不见的缺陷")
    A("")
    A("双实现互检是我们**唯一**能照出「参考实现算错了」的手段。它的覆盖是**不完整的**：")
    A("")
    A("| | 条数 |")
    A("| --- | ---: |")
    A("| KunQuant 后端的可执行因子 | 82 |")
    A("| **其中有第二实现、可被互检裁定的** | **51** |")
    A("| **无第二实现、互检看不见的** | **31** |")
    A("")
    A("**已经在可比的那 51 条里查出 1 条真缺陷**（`worldquant_101.038`，见第 4 节）。"
      "**那 31 条里若有同类字段错位，当前方法照不出来。**")
    A("")
    A("为查这类缺陷写过一个 (算子, 字段实参) 比较器，扫全部 82 条。"
      "**它的第一版比的是字段*集合*，对「同一组字段换了位置」恒返回 0** —— "
      "是一次空转的扫描，已作废；现行版本先在 `.038` 上验过判别力才出结论。"
      "即便如此，它对没有第二实现的 31 条仍然只能做静态比对，不能裁定数值。")
    A("")
    A("**读这批 gold 的人必须知道这条限度。** 登记在 N-22。")
    A("")
    A("## 4. 算子语义与实现缺陷的标注")
    A("")
    A("两类问题**表现完全一样**（能算出数、能跑通、数值看起来正常），处置**不同**：")
    A("")
    A("| 类别 | 条数 | 含义 | 处置 |")
    A("| --- | ---: | --- | --- |")
    A(f"| `operator_convention_suspect` | **{len(susp)}** | 算子语义未被因子定义绑定，两个引擎的读法都合法 | gold 标注存疑；**S3 出题避开**；移出 τ 样本 |")
    A(f"| `reference_implementation_defect` | **{len(defe)}** | 参考实现**读错了输入字段**，一方就是错的 | **gold 不可用**；移出 τ 样本；修正登记 N-24 |")
    A("")
    for fid, why in defe.items():
        A(f"- **`{fid}`** —— {why}")
    A("")
    A("下游**必须**调 API 而不是抄名单：")
    A("")
    A("```python")
    A("from reference.operator_flags import tasks_should_avoid, gold_unusable")
    A("tasks_should_avoid()   # S3 出题要避开的（约定存疑）")
    A("gold_unusable()        # gold 值根本不可用的（实现缺陷）")
    A("```")
    A("")
    A("## 4b. 已知且**知情保留**的欠定项（不是未解决缺陷）")
    A("")
    A("**参考回测 A（qlib TopkDropout）与三份独立实现 B 的 `ann_return_gross` 差 **22.69%**，"
      "而 `turnover_two_way_mean` 只差 **0.51%**。**")
    A("")
    A("换掉的**金额**几乎一样、换的**标的**不同 —— 这是**选股规则**的差异，"
      "定位到声明里的开放歧义 **A-1**（`n_drop` 卖「持仓中信号最差的」还是「已跌出目标组合的」）。")
    A("")
    A("**这是签字裁定后知情保留的欠定样本，不是 bug，不要顺手修掉。** "
      "两种卖出规则都合理、换手率完全相同、分歧从任何交易强度指标上都看不出来 —— "
      "这正是它作为 S7 首要题源的价值（N-25）。")
    A("")
    A("`ops/test_underdetermination_guard.py` 会在这个差异消失时变红并提示重新裁定。")
    A("")
    A("## 5. 数值口径")
    A("")
    w = any_m["write"]
    A(f"- **float64，不是 float32**。首版用 float32，pandas 只发一句 "
      f"`overflow encountered in cast`，产物层完全看不见。"
      f"秩相关**对饱和不是不变的**（一批大数被压成同一个 `inf` 会并列，Fid% 虚高）。")
    A("| 宇宙 | 若用 float32 会溢出的格 | 真 `inf` 的格（参考实现的诚实输出）|")
    A("| --- | ---: | ---: |")
    for u, m in mans.items():
        A(f"| `{u}` | {m['write']['would_overflow_float32']:,} | {m['write']['nonfinite_cells']:,} |")
    A("")
    A("- `inf` **保留不筛** —— 那是参考实现的诚实输出（除零 / 幂爆炸），"
      "筛选留给评分层（同 `ambiguous` 区段的处理原则：数据层不做筛选）。")
    A(f"- 暖机 {any_m['warmup_days']} 天，与钉版本 loader 的默认一致。")
    A("")
    A("## 6. 求值右端")
    A("")
    A("gold 因子值算到冻结线当天；**右端约束是给前向收益的**，由评分器硬拦：")
    A("")
    A("| 持有期 | 可用右端 |")
    A("| ---: | --- |")
    for k, v in sorted(any_m["evaluation_right_edges"].items(), key=lambda x: int(x[0])):
        A(f"| {k} 日 | `{v}` |")
    A("")
    A("## 7. 复现")
    A("")
    A("```bash")
    A("export GENEBENCH_ROOT=/data/shared/genebench")
    A("cd $GENEBENCH_ROOT/repo && ulimit -n 8192")
    for u in mans:
        A(f"$GENEBENCH_ROOT/env/bin/python -m reference.factor_exec "
          f"--universe {u} --start {any_m['start']} --end {any_m['end']}")
    A("$GENEBENCH_ROOT/env/bin/python -m reference.operator_flags")
    A("$GENEBENCH_ROOT/env/bin/python ops/mk_gold_data_card.py")
    A("```")
    A("")
    cfg.create_dir(OUT.parent)
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    OUT.chmod(0o600)

    # 把限度与能力边界也写进每个 manifest —— 读 manifest 的人也要看得见
    for u, m in mans.items():
        m["coverage_limits"] = {
            "kunquant_executable": 82, "comparable_by_crosscheck": 51,
            "not_adjudicable": 31,
            "note": ("双实现互检是唯一能照出「参考实现算错了」的手段，覆盖不完整："
                     "31 条无第二实现的因子里若有同类字段错位，当前方法看不见。见 N-22 与数据卡 §3。"),
        }
        m["capability_boundary"] = {
            "cannot_compute": ["IR", "alpha", "excess_return", "information_ratio"],
            "reason": "v1 provider 没有指数标的（instruments 取自 universe_pit，只有股票）",
            "ticket": "N-23",
            "benchmark_caveat": ("卡 2.2b 参考回测用等权宇宙当基准是**权宜**，"
                                 "不是 v1 的正式基准定义。"),
        }
        m["operator_flags"] = {
            "convention_suspect": susp, "convention_suspect_n": len(susp),
            "defective": defe, "defective_n": len(defe),
            "api": "reference.operator_flags.tasks_should_avoid() / gold_unusable()",
        }
        p = fx.GOLD_DIR / u / "manifest.json"
        p.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
        p.chmod(0o600)
    print(f"→ {OUT}  {OUT.stat().st_size} B；已给 {len(mans)} 份 manifest 补写限度与边界")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
