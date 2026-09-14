# -*- coding: utf-8 -*-
"""验收：`reference/b2_engine.py` 这层包装**没有改变实现 B2 的任何一个数**。

裁定 N-83 把 S7 的 gold 定为实现 B2。包装是为了让它能被 oracle 调用
（喂我们自己拼的面板、按题面声明设常量、把逐日台账取出来）——
只要包装动了一丁点算术，gold 就错了，而 11 项指标会一起偏、没有一处报错。

四道门，缺一不可：

| 门 | 判据 | 它挡住什么 |
| --- | --- | --- |
| **G0a 包装中性** | 包装的产出 **逐位**等于「今天原样重跑未打补丁的 B2 子进程」的产出（11/11 项）| 包装把面板/常量喂错了 |
| **G0b 环境漂移** | 今天重跑两次必须互相逐位相同；与 2026-09-01 的冻结产物之差必须 ≤ 噪声地板 1e-13 | 把「环境漂了」误当成「包装错了」，或反过来 |
| **G1 台账中性** | 打了台账补丁 vs 没打，同一份面板同一份配置 → 指标**逐位相同** | 台账补丁改了算术 |
| **G2 开关有效**（阳性对照）| `worst_n_drop` 与 `dropped_from_target` 的指标**必须不同** | 开关没接上而 G0/G1 照样绿（恒绿的门） |
| **G3 上层一致** | `s7_oracle_common.metrics(daily, INIT_CASH)` 与 B2 自己的 `metrics()` 在共有的 8 项上逐位相同 | 逐日表的列义与 B2 对不上（尤其 `ta_pre_trade` 的 NaN/inf 口径） |

G2 是 D-30 的那一半：只有 G0/G1 的话，一个「开关根本没接线」的包装可以全绿。

**G0 为什么要拆成 a/b**（2026-09-05 实测）：直接拿包装的产出对冻结产物，
`ann_vol_net` / `max_drawdown_net` / `sharpe_net` 三项对不上（相对差 2.4e-16 ~ 3.5e-15）。
把**未打补丁的 B2 原样子进程重跑一遍**，差的是**同样三项、同样的值** ——
也就是说漂的不是包装，是「今天的环境」与「2026-09-01 生成那份产物的环境」。
判据要落在它保护的那一侧（D-28）：证明包装中性，就得对**今天的** B2 比；
环境漂移是另一件事，另设一条判据、另记一张票（N-89）。
合成一条的话，包装真出了 1e-15 的错也会被「反正冻结产物本来就对不上」盖过去。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import genebench_config as cfg                                        # noqa: E402
from reference import b2_engine as b2                                 # noqa: E402
from reference import s7_oracle_common as cor                         # noqa: E402

EPS_DIR = cfg.SNAPSHOTS / "v1" / "epsilon"
FROZEN_PANEL = EPS_DIR / "bt_input_csi300_v2.parquet"
FROZEN_OUT = EPS_DIR / "out_v2_b2_daily.json"
TASK = cfg.GENEBENCH_ROOT / "reference" / "tasks" / "v1.0-smoke" / "s7-cor-01" / "task.yaml"

#: `metrics()` 里的非数值键，不进逐位比较。
NON_NUMERIC = ("rebalance_frequency",)

#: `epsilon_dual_daily.json` 记的噪声地板。环境漂移必须落在它之下。
NOISE_FLOOR = 1e-13


def declared() -> dict:
    return yaml.safe_load(TASK.read_text(encoding="utf-8"))["declared"]


def _bitwise_equal(a: dict, b: dict) -> list[str]:
    """返回**不逐位相同**的键。用 float 的原始位模式比，不用 isclose ——
    「差一点」在这里不是可以接受的，它意味着算术变了。"""
    bad = []
    for k in sorted(set(a) | set(b)):
        x, y = a.get(k), b.get(k)
        if isinstance(x, float) and isinstance(y, float):
            if np.float64(x).tobytes() != np.float64(y).tobytes():
                bad.append(k)
        elif x != y:
            bad.append(k)
    return bad


def run_once(panel: pd.DataFrame, conf: dict, *, ledger: bool) -> tuple[dict, pd.DataFrame | None]:
    if ledger:
        daily = b2.run(panel, conf)
        return daily.attrs["b2_metrics"], daily
    # 不打台账那一路：直接走 B2 的原始调用链，与包装完全一样地喂参数。
    mod = b2.load(conf["sell_rule"], ledger=False)
    for c in b2._MUTABLE_CONSTANTS:                                   # noqa: SLF001
        setattr(mod, c, conf[c])
    dates = sorted(pd.unique(panel["date"].astype(str)))
    mod.START, mod.END = dates[b2.WARMUP_DAYS], dates[-1]
    mod.INPUT = str(FROZEN_PANEL)
    d, _c, A = mod.load_panel()
    dates_w, S = mod.build_window(d, A)
    top, n_top = mod.build_targets(S)
    return mod.run(conf["rebalance_frequency"], dates_w, S, top, n_top), None


def rerun_untouched(freq: str, tag: str) -> dict:
    """原样重跑冻结的 B2 脚本（子进程，不打任何补丁）—— screen_runner 的 Gate 0 做法。"""
    import shutil
    import subprocess
    import tempfile as _tf
    root = cfg.create_dir(cfg.GENEBENCH_ROOT / "scratch" / "b2_gate0")
    with _tf.TemporaryDirectory(dir=root, prefix=tag) as t:
        d = Path(t)
        shutil.copy2(EPS_DIR / "impl_v2_b2.py", d / "impl_v2_b2.py")
        (d / FROZEN_PANEL.name).symlink_to(FROZEN_PANEL)
        r = subprocess.run([sys.executable, str(d / "impl_v2_b2.py"), freq],
                           cwd=d, capture_output=True, text=True, timeout=1800)
        if r.returncode != 0:
            raise RuntimeError(f"原样重跑失败：{r.stderr[-400:]}")
        return json.loads((d / f"out_v2_b2_{freq}.json").read_text(encoding="utf-8"))


def _max_rel(a: dict, b: dict) -> float:
    worst = 0.0
    for k in set(a) & set(b):
        if isinstance(a[k], float) and isinstance(b[k], float):
            worst = max(worst, abs(a[k] - b[k]) / max(abs(b[k]), 1e-18))
    return worst


def main() -> int:
    panel = pd.read_parquet(FROZEN_PANEL)
    frozen = json.loads(FROZEN_OUT.read_text(encoding="utf-8"))
    decl = declared()
    rep: dict = {"declared_sell_rule": decl.get("sell_rule"),
                 "frozen_out": str(FROZEN_OUT)}

    conf_contract = b2.config_from_declared({**decl, "sell_rule": "dropped_from_target"})
    conf_declared = b2.config_from_declared(decl)
    rep["config_contract"] = {k: v for k, v in conf_contract.items() if not isinstance(v, dict)}

    m_noled, _ = run_once(panel, conf_contract, ledger=False)
    m_led, daily = run_once(panel, conf_contract, ledger=True)
    m_decl, _dd = run_once(panel, conf_declared, ledger=True)

    today_a = rerun_untouched("daily", "a")
    today_b = rerun_untouched("daily", "b")

    rep["G0a_wrapper_matches_todays_b2"] = {
        "mismatched_keys": _bitwise_equal(m_led, today_a),
        "n_metrics": len(today_a),
    }
    rep["G0b_environment_drift"] = {
        "two_reruns_today_agree": not _bitwise_equal(today_a, today_b),
        "keys_drifted_vs_frozen": _bitwise_equal(
            {k: v for k, v in today_a.items() if k not in NON_NUMERIC},
            {k: v for k, v in frozen.items() if k not in NON_NUMERIC}),
        "max_rel_drift_vs_frozen": _max_rel(today_a, frozen),
        "noise_floor": NOISE_FLOOR,
    }
    rep["G1_ledger_patch_is_neutral"] = {"mismatched_keys": _bitwise_equal(m_noled, m_led)}
    rep["G2_sell_rule_switch_bites"] = {
        "changed_keys": _bitwise_equal(m_led, m_decl),
        "dropped_from_target": {k: m_led[k] for k in ("ann_return_gross", "total_cost")},
        "worst_n_drop": {k: m_decl[k] for k in ("ann_return_gross", "total_cost")},
    }

    up = cor.metrics(daily, conf_contract["INIT_CASH"])
    shared = sorted(set(up) & set(m_led) - set(NON_NUMERIC))
    rep["G3_upper_layer_agrees"] = {
        "compared": shared,
        "mismatched_keys": _bitwise_equal({k: up[k] for k in shared},
                                          {k: m_led[k] for k in shared}),
    }
    resid = float((daily.cash + daily.mv - daily.total_assets).abs().max())
    rep["ledger_max_abs_residual"] = resid
    rep["ledger_note"] = ("B2 把 total_assets 直接算成 cash + mv，所以 gold 上这个残差"
                          "**按构造恒为 0**。它不是空判据：探针核的是 agent 的 artifact。")
    rep["daily_rows"] = int(len(daily))
    rep["daily_columns"] = list(daily.columns)

    rep["ok"] = (not rep["G0a_wrapper_matches_todays_b2"]["mismatched_keys"]
                 and rep["G0b_environment_drift"]["two_reruns_today_agree"]
                 and rep["G0b_environment_drift"]["max_rel_drift_vs_frozen"] <= NOISE_FLOOR
                 and not rep["G1_ledger_patch_is_neutral"]["mismatched_keys"]
                 and bool(rep["G2_sell_rule_switch_bites"]["changed_keys"])
                 and not rep["G3_upper_layer_agrees"]["mismatched_keys"])

    out = Path(__file__).resolve().parents[1] / "reports" / "s7_b2_wrapper_gate.json"
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    out.chmod(0o600)
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
