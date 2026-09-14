# -*- coding: utf-8 -*-
"""把 calibration.json 渲染成给签字人逐条核对的口径清单。

    cd $REPO && $GENEBENCH_ROOT/env/bin/python ops/render_calibration_spec.py
"""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import genebench_config as cfg
from reference import calibration as cal

OUT = cfg.REPORTS / "calibration_spec_v1.md"
C = json.loads(cal.OUT.read_text(encoding="utf-8"))
s, t, e = C["scoring"], C["tau"], C["epsilon"]
bb, nw = s["uncertainty"]["block_bootstrap"], s["uncertainty"]["newey_west"]
L = []; A = L.append

A("# `calibration.json` 口径清单（逐条核对用）")
A("")
A(f"落点 `{cal.OUT}` · 生成于 `{C['built_at']}` · schema v{C['schema_version']}")
A(f"· provider digest `{C['provider']['digest'][:16]}…`")
A("")
A(f"**整份配置可用于评分：`{C['ready_for_scoring']}`**"
  + ("" if C["ready_for_scoring"] else f" —— 未决项：{C['outstanding']}"))
A("")
A("> 由 `ops/render_calibration_spec.py` 生成。"
  " 每一条都有对应的会红的断言，见 `ops/test_calibration.py`（16 项）。")
A("")
A("## 第一批冻结（对接决定 / `ops/specs/README.md` 第 4 条）")
A("")
A("| # | 冻结项 | calibration.json 里的值 | 落位 |")
A("| ---: | --- | --- | :---: |")
A(f"| 1 | 分位数 | `{s['quantiles']}` | ✅ |")
A(f"| 2 | 平局处理 | `{s['tie_handling']}` | ✅ |")
A(f"| 3 | 权重 | `{s['weighting']}` | ✅ |")
A(f"| 4 | 调仓时点 | `{s['rebalance_timing']}` | ✅ |")
A(f"| 5 | 持有期 | `{s['holding_periods']}` | ✅ |")
A(f"| 6 | Sharpe 年化 | `√{s['sharpe']['sqrt_factor']}`，"
  f"gross/net **分开报** = `{s['sharpe']['gross_and_net_reported_separately']}` | ✅ |")
A(f"| 7 | Sortino MAR | `{s['sortino']['MAR']}` | ✅ |")
A(f"| **8** | **turnover 双记** | `one_way={s['turnover']['one_way']}` · "
  f"`two_way={s['turnover']['two_way']}` · `both_required={s['turnover']['both_required']}` | ✅ |")
A(f"| 9 | IC 汇总 | `{s['ic_summary']['report']}`；"
  f"positive_ratio 与 coverage 均为必报 | ✅ |")
A(f"| **10** | **不确定性用 block-bootstrap** | `{bb['method']}`，"
  f"重抽样 `{bb['n_resamples']}`，CI `{bb['ci_level']}`，种子 `{bb['seed']}`，"
  f"块长规则 `{bb['block_length_rule']}`，作用于 `{bb['applies_to']}` | ✅ |")
A(f"| 10b | Newey–West 的地位 | `enabled={nw['enabled']}`，"
  f"角色写死为「{nw['role']}」 | ✅ |")
A("")
A("**第 8 与第 10 是你点名最容易漏的两条**：")
A("")
A(f"- turnover 双记 —— 不只是配置里写了两个 `True`，"
  f"ε 的指标表里**同时存在** `turnover_one_way_mean` 与 `turnover_two_way_mean` 两项实测值"
  f"（不是一项换算出来的），`test_freeze1_turnover_is_double_recorded` 盯着这一点。")
A(f"- block-bootstrap —— 参数全在（方法/重抽样数/CI/种子/块长规则/作用对象），"
  f"且 `newey_west.role` 里带「不得替代」四个字，"
  f"`test_freeze1_uncertainty_is_block_bootstrap_not_only_newey_west` 直接断言这四个字。")
A("")
A("## 第二批冻结（F-1…F-5）与 τ")
A("")
A("| 项 | 值 |")
A("| --- | --- |")
A(f"| F-1 算法 | 逐交易日截面 Spearman（tie 平均法），再对时间取分布 |")
A(f"| F-2 τ 分位 | P{int(C['rank_correlation']['F-2_tau_quantile'])}，"
  f"`pooled_not_time_averaged = {C['rank_correlation']['F-2_pooled_not_time_averaged']}` |")
A(f"| F-4 degenerate 阈值 | 唯一值数 < `{C['rank_correlation']['F-4_degenerate_threshold']:.0%}` × "
  f"截面标的数；最小截面 `{C['rank_correlation']['F-4_min_cross_section']}` |")
A(f"| **τ** | **`{t['value']:.6f}`** |")
A(f"| τ 的样本 | {t['factors_used']} 因子 / {t['cells_used']:,} 格"
  f"（可比 {t['comparable_factors']} 条，排除 {len(t['excluded_operator_conflict'])} 条算子冲突）|")
A(f"| τ 的窗口 | `{t['universe']}` {t['start']} … {t['end']} |")
A(f"| degenerate 剔除方向 | 剔除**使 τ 上升** = `{t['degenerate_rule']['removal_raises_tau']}`，"
  f"共剔 {t['degenerate_rule']['cells_removed']:,} 格 |")
A("")
A("## 求值右端（硬拦）")
A("")
A("| 持有期 | 可用右端 |")
A("| ---: | --- |")
for k, v in sorted(C["evaluation_right_edge"]["by_holding_period"].items(), key=lambda x: int(x[0])):
    A(f"| {k} 日 | `{v}` |")
A("")
A(f"`must_hard_block = {C['evaluation_right_edge']['must_hard_block']}`；"
  f"来源：{C['evaluation_right_edge']['source']}")
A("")
A("## 算子语义冲突（N-21 → C）")
A("")
A(f"- gold 标注「算子约定存疑」：**{len(C['operator_conflicts']['gold_suspect'])} 条**")
A(f"- S3 出题必须避开：`{C['operator_conflicts']['s3_must_avoid']}`，"
  f"API `{C['operator_conflicts']['api']}`")
A(f"- 证据：`{C['operator_conflicts']['evidence']}`")
A("")
A("## ε —— **待回填**")
A("")
se = e["source_effectiveness"]
A(f"- 状态：`{e['status']}`，可用 = `{e['usable']}`")
A(f"- 方法：`{e['method']}`，倍数 ×{e['multiplier']}")
A(f"- 环境：{len(e['environments'])} 组，pyqlib 全程钉住 `{C['epsilon']['pyqlib_held_constant']}`")
A("")
A("| 组合 | numpy | pandas |")
A("| --- | --- | --- |")
for n, k in e["environments"].items():
    A(f"| `{n}` | {k['numpy']} | {k['pandas']} |")
A("")
A(f"- **最大相对极差 `{se['max_relative_spread']:.3g}`**，有效性下限 `{se['threshold']:g}`，"
  f"float64 相对精度 `{se['float64_relative_eps']:.3g}`")
A(f"- 判定：{se['verdict']}")
A(f"- 完全确定性的指标：`{e['deterministic_metrics']}`（单独标注，**不代填**）")
A(f"- 浮点噪声地板（副产品）：`{e['float_noise_floor_relative']:.3g}`（相对）—— "
  "无论 ε 日后改用哪个标定源，它都必须**明显高于**这个地板，否则量到的还是舍入。")
A("")
A(f"> {e['blocking_note']}")
A("")
cfg.create_dir(OUT.parent)
OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
OUT.chmod(0o600)
print(f"→ {OUT}  {OUT.stat().st_size} B")
