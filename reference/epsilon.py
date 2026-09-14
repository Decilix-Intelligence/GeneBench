# -*- coding: utf-8 -*-
"""卡 2.2：ε 标定 —— **跨库版本**，不是五种子。

    cd $REPO && $GENEBENCH_ROOT/env/bin/python -m reference.epsilon

**为什么不是五种子**（签字裁定，见 `ops/specs/design_notes.md` D-05）：
qlib 的回测在同一 gold 信号上**完全确定性** ——
``TopkDropoutStrategy`` 默认 ``method_sell="bottom"`` / ``method_buy="top"``（`"random"` 只是可选值），
``qlib/backtest/exchange.py:638`` 是 ``random.seed(0); random.shuffle(...)``，
种子**硬编码为 0**、注释自陈 *"the final stock_id order is fixed"*。
外部传任何 seed 都不生效，五种子极差**必为 0** —— 那是标定**失效**，不是标定成功。
照搬会得到一条永远通过的零容差验收测试，直到某天换库版本才全红。

**改用的标定源**：同一份 gold 信号、同一份回测代码，在 numpy/pandas 版本不同的环境里跑，
取各指标极差 ×1.5。环境是**整份复制主 env 再换这两个包** —— 其余 208 个包与 pyqlib
逐字节相同，把变量隔离到只剩 numpy/pandas。

**三条硬要求**（签字原话）：

1. **逐指标分别给 ε**，不给全局单值 —— Sharpe 与 MDD 的浮点敏感度本来就不同；
2. 每个版本组合的**完整包清单**进 manifest；
3. 某指标极差仍为 0 → **单独标注**「该指标在当前实现下完全确定性」，
   **不许用其他指标的 ε 代填**。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import genebench_config as cfg
from reference import backtest as bt

#: 参与标定的环境。**主 env 必须在列**（它是基准组合）。
ENVS: tuple[tuple[str, Path], ...] = (
    ("baseline", cfg.GENEBENCH_ROOT / "env"),
    ("pandas_minor", cfg.GENEBENCH_ROOT / "env_b"),
    ("numpy_pandas_minor", cfg.GENEBENCH_ROOT / "env_c"),
    ("pandas_major", cfg.GENEBENCH_ROOT / "env_d"),
)

#: ε = 极差 × 这个系数（实施稿卡 2.2 原文）。
EPSILON_MULTIPLIER: float = 1.5

#: **标定源有效性下限**。相对极差若全都低于这个数，说明这个标定源根本没让数值动 ——
#: 那是 D-05 说的"标定失效"，与 E-1 的"五种子极差为 0"是同一种失败，只是没有恰好等于 0。
#:
#: 取 1e-10：float64 的相对精度是 2.2e-16，1,818 步累积后放大几百个 ULP 也还在 1e-13 量级；
#: 1e-10 留了三个数量级的余量，任何**真实的实现差异**都会远超它。
#: **这条守门写死在代码里，不靠自觉** —— 因为它拦的正是"跑完看见很小的数然后解释一下就用了"。
SOURCE_EFFECTIVE_MIN_RELATIVE_SPREAD: float = 1e-10

#: 进 ε 的指标。换手双记两项都在（第一批冻结项第 4 条）。
METRICS: tuple[str, ...] = (
    "ann_return_gross", "ann_return_net", "ann_vol_gross", "ann_vol_net",
    "sharpe_gross", "sharpe_net", "sortino_net_mar0",
    "max_drawdown_gross", "max_drawdown_net", "calmar_net",
    "total_cost", "turnover_one_way_mean", "turnover_two_way_mean",
    "turnover_two_way_sum", "win_rate_net",
)

#: **通道相关的模块属性**（卡 1.1-b，PEP 562 ``__getattr__``）：不设
#: ``GENEBENCH_CHANNEL`` 时逐字等于既有常量，设成 ``public`` 时落到
#: ``snapshots/public_v1/epsilon/``。做成属性而不是改成函数，是为了让
#: 下游（``reference/calibration.py``、``ops/screen_band.py``、验收脚本）
#: 一个字都不用改 —— 逐个去改的话，漏掉一处的表现是「公开链读了私有 ε」。

def out_path(ch: "str | None" = None) -> Path:
    """该通道的 ``epsilon.json``（跨库版本那一版，作废但保留作反面记录）。"""
    return cfg.epsilon_dir(ch) / "epsilon.json"


def __getattr__(name: str):
    if name == "OUT":
        return out_path()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["ENVS", "EPSILON_MULTIPLIER", "METRICS", "calibrate", "OUT", "out_path"]


def run_one(name: str, env_dir: Path, factor: str) -> dict[str, Any]:
    py = env_dir / "bin" / "python"
    if not py.exists():
        raise FileNotFoundError(f"{name} 的解释器不存在：{py}")
    out = cfg.epsilon_dir() / f"bt_{factor}_{name}.json"
    cfg.create_dir(out.parent)
    r = subprocess.run(
        [str(py), "-m", "reference.backtest", "--factor", factor, "--out", str(out)],
        cwd=str(cfg.REPO), capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"{name} 回测失败：\n{r.stdout[-1500:]}\n{r.stderr[-2500:]}")
    return json.loads(out.read_text(encoding="utf-8"))


def calibrate(factor: str = "qlib_alpha158.ROC20", *, verbose: bool = True) -> dict[str, Any]:
    runs: dict[str, dict[str, Any]] = {}
    for name, d in ENVS:
        if verbose:
            print(f"[{name}] {d} …", flush=True)
        runs[name] = run_one(name, d, factor)
        k = runs[name]["env"]["key"]
        if verbose:
            print(f"  numpy={k['numpy']} pandas={k['pandas']} pyqlib={k['pyqlib']}", flush=True)

    # pyqlib 必须在所有环境里相同 —— 否则变量没隔离干净，ε 说明不了任何事
    pyq = {n: r["env"]["key"]["pyqlib"] for n, r in runs.items()}
    if len(set(pyq.values())) != 1:
        raise RuntimeError(f"pyqlib 版本在各环境间不一致：{pyq}。变量没隔离干净，ε 无意义。")
    combos = {n: (r["env"]["key"]["numpy"], r["env"]["key"]["pandas"]) for n, r in runs.items()}
    if len(set(combos.values())) != len(combos):
        raise RuntimeError(f"有两个环境的 numpy/pandas 组合相同：{combos}。"
                           f"这样的极差恒为 0，是**标定失效**而不是确定性 —— 见 D-05。")

    eps: dict[str, Any] = {}
    for m in METRICS:
        vals = {n: r["metrics"].get(m) for n, r in runs.items()}
        nums = [v for v in vals.values() if isinstance(v, (int, float)) and v == v]
        if len(nums) < 2:
            eps[m] = {"values": vals, "status": "insufficient", "epsilon": None,
                      "note": "可用值不足两个，无法取极差"}
            continue
        spread = float(max(nums) - min(nums))
        rec: dict[str, Any] = {
            "values": vals, "min": float(min(nums)), "max": float(max(nums)),
            "spread": spread, "epsilon": spread * EPSILON_MULTIPLIER,
            "relative_spread": (spread / abs(max(nums, key=abs))
                                if max(nums, key=abs) else None),
        }
        if spread == 0.0:
            rec["status"] = "deterministic"
            rec["epsilon"] = 0.0
            rec["note"] = ("该指标在当前实现与这些库版本组合下**完全确定性**（极差恰为 0）。"
                           "**不得用其他指标的 ε 代填**；若日后需要非零容差，"
                           "必须先找到一个能让它变动的标定源。")
        else:
            rec["status"] = "calibrated"
        eps[m] = rec

    det = [m for m in METRICS if eps[m].get("status") == "deterministic"]

    # ---- 标定源有效性检验（D-05 / E-1 的制度化） ----
    rels = [abs(r["relative_spread"]) for r in eps.values()
            if r.get("relative_spread") is not None]
    max_rel = max(rels) if rels else 0.0
    source_effective = max_rel >= SOURCE_EFFECTIVE_MIN_RELATIVE_SPREAD
    payload = {
        "card": "2.2-epsilon",
        "method": "cross_library_version",
        "why_not_seeds": ("qlib 回测在同一 gold 信号上完全确定性："
                          "TopkDropoutStrategy 默认 method_sell=bottom/method_buy=top；"
                          "exchange.py:638 硬编码 random.seed(0) 且注释自陈 "
                          '"the final stock_id order is fixed"。'
                          "五种子极差必为 0 = 标定失效。见 design_notes D-05。"),
        "multiplier": EPSILON_MULTIPLIER,
        "signal_factor": factor,
        "backtest_config": runs["baseline"]["config"],
        "environments": {n: {"dir": str(d), "key_versions": runs[n]["env"]["key"],
                             "python": runs[n]["env"]["python"],
                             "platform": runs[n]["env"]["platform"],
                             "packages": runs[n]["env"]["packages"]}
                         for n, d in ENVS},
        "pyqlib_held_constant": next(iter(set(pyq.values()))),
        "epsilon_by_metric": eps,
        "deterministic_metrics": det,
        "n_metrics": len(METRICS),
        "n_calibrated": len(METRICS) - len(det),
        "source_effectiveness": {
            "max_relative_spread": max_rel,
            "threshold": SOURCE_EFFECTIVE_MIN_RELATIVE_SPREAD,
            "effective": source_effective,
            "float64_relative_eps": 2.220446049250313e-16,
            "verdict": ("标定源有效" if source_effective else
                        "**标定源失效**：跨这些库版本的分歧全部落在 float64 舍入量级，"
                        "ε 会退化成一条比特级相等的验收断言。与 E-1 的「五种子极差为 0」同形。"),
        },
        "status": "calibrated" if source_effective else "source_ineffective_awaiting_decision",
        "float_noise_floor_relative": max_rel,
        "floor_note": ("这个数是有用的副产品：无论日后 ε 改用哪个标定源，"
                       "它都必须**明显高于**这个浮点噪声地板，否则量到的还是舍入。"),
    }
    dest = out_path()
    cfg.create_dir(dest.parent)
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    dest.chmod(0o600)
    if verbose:
        print("\n指标                              极差          ε=极差×1.5  状态")
        for m in METRICS:
            e = eps[m]
            sp = e.get("spread")
            ep = e.get("epsilon")
            sp_s = "—" if sp is None else format(sp, ".6g")
            ep_s = "—" if ep is None else format(ep, ".6g")
            print(f"{m:<26}{sp_s:>16}{ep_s:>16}  {e.get('status')}")
        print(f"\n完全确定性的 {len(det)} 项：{det}")
        print(f"最大相对极差 {max_rel:.3g}（float64 相对精度 2.22e-16）")
        print(f"→ {dest}")
    if not source_effective:
        print("\n" + "=" * 74)
        print("⚠ 标定源失效 —— 按 E-1 / D-05 停下汇报，不产出可用的 ε。")
        print(f"  跨 {len(ENVS)} 个库版本组合的最大相对极差只有 {max_rel:.3g}，")
        print(f"  低于有效性下限 {SOURCE_EFFECTIVE_MIN_RELATIVE_SPREAD:g}，即全是 float64 舍入。")
        print("  把它写成 ε 会得到一条**比特级相等**的验收断言 —— ")
        print("  和照搬「五种子极差」一样，是永远通过直到某天全红的零容差测试。")
        print("=" * 74)
    return payload


def main(argv: "list[str] | None" = None) -> int:
    p = argparse.ArgumentParser(description="卡 2.2 ε 标定（跨库版本）")
    p.add_argument("--factor", default="qlib_alpha158.ROC20")
    a = p.parse_args(argv)
    calibrate(a.factor)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
