# -*- coding: utf-8 -*-
"""卡 2.2 产出：``calibration.json`` —— 所有冻结口径 + τ + ε 的**单一事实来源**。

    cd $REPO && $GENEBENCH_ROOT/env/bin/python -m reference.calibration

**评分器只许从这里读参数，不许自己拍。** 任何一项改动都要重新签字。

三批来源，全部在这份文件里合流：

* **第一批冻结**（`ops/specs/README.md` 第 4 条）—— 10 分位 / 平局平均法 / 等权 /
  收盘后调仓 / 持有期 {1,5,20} / Sharpe 年化 √252 且 gross-net 分开 / Sortino MAR=0 /
  turnover **one-way 与 two-way 双记** / IC 汇总补 positive ratio 与 coverage /
  不确定性一律 **block-bootstrap**（HAC 可并列不可替代）。
* **第二批冻结**（`ops/specs/GeneBench秩相关与标定口径_v1.md`）—— F-1…F-5 与 E-1。
* **本卡实测** —— τ、ε、可用求值右端、算子冲突排除集。
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import genebench_config as cfg
from reference import epsilon as ep
from reference import factor_crosscheck as fc
from reference import operator_flags as of
from snapshots import qlib_provider as qp

#: **通道相关的模块属性**（卡 1.1-b，PEP 562 ``__getattr__``）：不设
#: ``GENEBENCH_CHANNEL`` 时逐字等于 ``cfg.SNAPSHOTS_V1 / "calibration.json"``，
#: 设成 ``public`` 时落到 ``snapshots/public_v1/calibration.json``。
#: 做成属性而不是改成函数，是为了让下游（``scorer/l3.py`` 的 ``load_calibration``、
#: 各验收脚本）一个字都不用改。


def out_path(ch: "str | None" = None) -> Path:
    """该通道的 ``calibration.json`` 落点。"""
    return cfg.calibration_path(ch)


def __getattr__(name: str):
    if name == "OUT":
        return out_path()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

#: block-bootstrap 的参数。**不许在评分器里另拍。**
#: 块长用 n^(1/3) 向上取整（Politis–White 一类规则的常用近似），
#: 由样本长度现算而不是写死一个数 —— 写死会在换窗口时静默失配。
BOOTSTRAP: dict[str, Any] = {
    "method": "moving_block_bootstrap",
    "block_length_rule": "ceil(n_obs ** (1/3))",
    "n_resamples": 1000,
    "ci_level": 0.95,
    "seed": 20260731,
    "applies_to": ["IC", "RankIC", "quantile_spread", "alpha", "sharpe"],
    "note": ("对接决定 §不确定性：IC/spread/alpha/Sharpe 一律给 block-bootstrap 区间。"
             "Newey–West/HAC **可以并列报告，但不得替代** —— 原规格只对 IC 的 t 值做 NW 是窄口径。"),
}

NEWEY_WEST: dict[str, Any] = {
    "enabled": True,
    "role": "并列报告，不得替代 block-bootstrap",
    "lag_rule": "floor(4 * (n_obs/100) ** (2/9))",
    "significance_line": "t > 3（Harvey–Liu 多重检验校正线）",
}


def _tau() -> dict[str, Any]:
    rep = json.loads(cfg.crosscheck_report().read_text(encoding="utf-8"))
    cells = pd.read_parquet(cfg.crosscheck_dir()
                            / f"rank_ic_cells_{rep['universe']}.parquet")
    comparable = [x["id"] for x in rep["rows"]]
    excluded = of.tau_excluded(comparable)
    k = cells[np.isfinite(cells["rho"]) & ~cells["degenerate"]]
    kept = k[~k["factor_id"].isin(excluded)]
    return {
        "value": float(np.percentile(kept["rho"], fc.TAU_QUANTILE)),
        "definition": ("逐交易日截面 Spearman（tie 平均法），"
                       f"取「全因子 × 全交易日」二维分布的 P{int(fc.TAU_QUANTILE)}"),
        "F-2_not": "**不是**先对时间平均再取分位 —— S3 的 Fid% 判定粒度就是 (因子, 日)",
        "universe": rep["universe"], "start": rep["start"], "end": rep["end"],
        "comparable_factors": rep["comparable_factors"],
        "factors_used": int(kept["factor_id"].nunique()),
        "cells_used": int(len(kept)),
        "excluded_operator_conflict": excluded,
        "excluded_reason": ("N-21 → C：算子语义须绑定在因子定义上，评测方不得隐式补全。"
                            "排除规则定在「源方言使用了语义未绑定的 Ts_Rank」，"
                            "而不是「观察到了分歧」。"),
        "degenerate_rule": {
            "unique_ratio_threshold": fc.DEGENERATE_UNIQUE_RATIO,
            "min_cross_section": fc.MIN_CROSS_SECTION,
            "source": fc.DEGENERATE_THRESHOLD_SOURCE,
            "cells_removed": int(cells["degenerate"].sum()),
            "removal_raises_tau": True,
            "note": "剔除使 τ 上升（常数截面此前在拖低尾部），**不是**放宽容差",
        },
        "reference": {
            "report": "ops/reports/factor_crosscheck_2.1b.md",
            "cells": rep["cells_parquet"],
            "attribution": "ops/acceptance/card_2.1b_tail_attribution.json",
        },
    }


def _epsilon() -> dict[str, Any]:
    """ε：**双实现分档标定**（卡 2.2b v2）。

    跨库版本那一版（`reference/epsilon.py`）已**作废** —— 见 design_notes D-05：
    跨 4 个 numpy/pandas 组合的最大相对极差只有 8.53e-14，全是 float64 舍入，
    照它定容差等于要求比特级相等。这里保留它作反面记录。
    """
    from reference import epsilon_dual as ed

    per_freq: dict[str, Any] = {}
    for freq in ("daily", "weekly", "monthly"):
        f = cfg.epsilon_dir() / f"epsilon_dual_{freq}.json"
        if not f.exists():
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        per_freq[freq] = {
            "n_implementations": d["n_implementations"],
            "by_metric": {m: {k: v for k, v in r.items() if k != "values"}
                          for m, r in d["epsilon_by_metric"].items()},
            "calibrated": d["calibrated"], "implausible": d["implausible"],
            "no_freedom": d["no_freedom"], "usable": d["usable"],
        }
    sup_p = ep.out_path()
    sup = json.loads(sup_p.read_text(encoding="utf-8")) if sup_p.exists() else {}
    payload: dict[str, Any] = {
        "method": "dual_independent_implementation_pairwise",
        "contract": "ops/specs/backtest_contract.md（v2）",
        "multiplier": ed.MULTIPLIER,
        "noise_floor": ed.NOISE_FLOOR,
        "implausible_threshold": ed.IMPLAUSIBLE_REL_DIFF,
        "tolerance_rule": {
            "relative": "尺度无关且不趋零的指标",
            "absolute": (f"构造上可能趋零：{sorted(ed.ZERO_APPROACHING)}；"
                         f"ε = |A−B| 绝对差 × {ed.MULTIPLIER}，单位 = {ed.ABSOLUTE_UNIT}"),
            "why": ("相对容差施加在趋零量上没有意义：ann_return_net 的相对差可达 20%+，"
                    "但那是毛收益减成本拖累的小差被放大。"),
            "enforced_by": "reference.epsilon_dual.assert_tolerance_kind()（配错直接抛）",
        },
        "rebalance_frequency_is_required": True,
        "by_frequency": per_freq,
        "no_global_epsilon": ("逐指标**且逐频率**分别给。ε 随调仓频率跨约 3 个数量级 —— "
                              "S7 判回测必须按题面声明的频率取对应那一档；"
                              "**低频题需要更宽的容差**（调仓次数少，单次决策的权重大）。"),
        "superseded_cross_version": {
            "max_relative_spread": sup.get("source_effectiveness", {}).get("max_relative_spread"),
            "verdict": ("标定源失效，全是 float64 舍入；保留作反面记录（D-05 第二实例）。"
                        "环境完整包清单仍在 $SNAPSHOTS/v1/epsilon/epsilon.json。"),
            "environments": {n: v.get("key_versions")
                             for n, v in sup.get("environments", {}).items()},
        },
        "usable": bool(per_freq) and all(v["usable"] for v in per_freq.values()),
        "zero_spread_policy": ("差为 0 的指标标 no_implementation_freedom，"
                               "**不得用其他指标的 ε 代填**"),
    }
    ic = _ic_family()
    if ic is not None:
        payload["ic_family"] = ic
    return payload


def _ic_family() -> "dict[str, Any] | None":
    """N-117：S4 的 **IC 族** ε 带（``ops/ic_epsilon.py`` 的产物）。

    **为什么收进 build() 而不是事后合并**：卡 1.2 是用 ``ops/merge_ic_epsilon.py``
    把这个块**插进已经落盘的** ``calibration.json`` 的。那样做留下一个陷阱 ——
    再跑一次 ``calibration.build()`` 就会把它抹掉，S4 于是回到 ``l3_pass=None``
    / ``effect=None``，**而没有任何一处会报错**（`calibration.json` 里少一个键，
    `scorer.l3.ic_family_band()` 查不到带就跳过那一格）。公开通道要从零重建这条链，
    正好会踩上它，所以在这里收口。

    块的内容仍由 ``ops.merge_ic_epsilon.build_block`` 产出 —— **同一份代码**，
    不在这里另写一遍裁剪规则（另写一遍的表现是：两条路各自演化，某天
    ``calibration.json`` 里的带与 ``ic_epsilon_dual.json`` 里的对不上）。
    ``ops/test_public_chain.py::test_native_ic_family_equals_the_merged_one``
    拿**私有通道现成的那份**逐值比对钉住这件事。

    产物不存在 → 返回 ``None``（这条链还没跑到 N-117 那一步），不是错误。
    """
    src = cfg.epsilon_dir() / "ic_epsilon_dual.json"
    if not src.is_file():
        return None
    from ops import merge_ic_epsilon as mie

    raw = src.read_bytes()
    return mie.build_block(json.loads(raw), src_path=src,
                           src_sha256=hashlib.sha256(raw).hexdigest())


def build(*, verbose: bool = True, out: "Path | None" = None) -> dict[str, Any]:
    """建 ``calibration.json``。

    Args:
        out: 落点。``None`` = 该通道的 ``calibration.json``。给一个别的路径可以在
            **不覆盖既有产物**的前提下重建一遍做逐字节比对
            （卡 1.1-b 的私有通道不变性证据就是这么取的）。
    """
    pp = qp.PATHS_BY_CHANNEL[cfg.channel()]
    edges = qp.evaluation_right_edges()
    payload: dict[str, Any] = {
        "schema_version": 1,
        "card": "2.2",
        "built_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "freeze_date": cfg.FREEZE_DATE,
        "provider": {
            "dir": str(pp.provider_dir),
            "digest": json.loads(pp.manifest.read_text())["digest"]["files_sha256_digest"],
        },

        # ---------------- 第一批冻结（对接决定 / README 第 4 条）----------------
        "scoring": {
            "quantiles": 10,
            "tie_handling": "average",
            "weighting": "equal",
            "rebalance_timing": "after_close",
            "holding_periods": list(qp.HOLDING_PERIODS),
            "annualization_factor": 252,
            "sharpe": {"annualized": True, "sqrt_factor": 252,
                       "gross_and_net_reported_separately": True},
            "sortino": {"MAR": 0.0},
            "turnover": {
                "one_way": True, "two_way": True,
                "both_required": True,
                "note": "**双记是两个数**。只记一个下游算成本会差一倍（第一批冻结最易漏的一处）",
            },
            "ic_summary": {
                "per_cross_section_then_time_series": True,
                "report": ["mean", "std", "ICIR", "positive_ratio", "coverage", "CI"],
                "positive_ratio_required": True, "coverage_required": True,
            },
            "uncertainty": {"block_bootstrap": BOOTSTRAP, "newey_west": NEWEY_WEST},
            "gate_semantics": ("五探针任一失败 → 该次运行的阶段效果分记 `invalid`，"
                               "不进 module ranking；**不是扣分**。"
                               "扣分制会奖励作弊：带前视的因子 IC 更高，扣几分后仍可能胜出。"),
        },

        # ---------------- 第二批冻结（F-1…F-5 / E-1）----------------
        "rank_correlation": {
            "F-1_algorithm": "逐交易日截面 Spearman（tie 平均法），再对时间取分布",
            "F-2_tau_quantile": fc.TAU_QUANTILE,
            "F-2_pooled_not_time_averaged": True,
            "F-4_degenerate_threshold": fc.DEGENERATE_UNIQUE_RATIO,
            "F-4_min_cross_section": fc.MIN_CROSS_SECTION,
        },
        "tau": _tau(),
        "epsilon": _epsilon(),

        # ---------------- 本卡实测的硬拦项 ----------------
        "evaluation_right_edge": {
            "by_holding_period": {str(h): v for h, v in edges.items()},
            "must_hard_block": True,
            "why": ("持有期 h 日下，最后 h 个交易日的前向收益在冻结线内不完整。"
                    "不拦的话 20 日 IC 会在末段用截断/缺失的前向收益计算，"
                    "**被静默偏置，而且从指标数值上看不出来**。"),
            "source": "snapshots.qlib_provider.evaluation_right_edge()，从 trade_cal 现数",
        },
        "operator_conflicts": {
            "decision": "N-21 → C",
            "gold_suspect": sorted(of.tasks_should_avoid()),
            "s3_must_avoid": True,
            "api": "reference.operator_flags.tasks_should_avoid()",
            "evidence": "ops/specs/operator_semantics_conflicts.md",
        },
    }
    payload["ready_for_scoring"] = bool(payload["epsilon"]["usable"])
    payload["outstanding"] = ([] if payload["ready_for_scoring"]
                              else ["epsilon: 标定源失效，等换源后回填（E-1 / D-05）"])
    dest = out or out_path()
    cfg.create_dir(dest.parent)
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    dest.chmod(0o600)
    if verbose:
        t, e = payload["tau"], payload["epsilon"]
        print(f"τ = {t['value']:.6f}（{t['factors_used']} 因子 / {t['cells_used']:,} 格，"
              f"排除 {len(t['excluded_operator_conflict'])} 条算子冲突）")
        for f, v in e["by_frequency"].items():
            print(f"ε[{f}] 可标定 {len(v['calibrated'])} · 超阈 {len(v['implausible'])} · "
                  f"无自由度 {len(v['no_freedom'])} · usable={v['usable']}")
        icf = e.get("ic_family")
        if icf:
            print(f"ε[ic_family] 可用 {icf.get('usable_metrics')} · "
                  f"未出带 {icf.get('unusable_metrics')}")
        print(f"求值右端 {payload['evaluation_right_edge']['by_holding_period']}")
        print(f"→ {dest}")
    return payload


if __name__ == "__main__":
    build()
