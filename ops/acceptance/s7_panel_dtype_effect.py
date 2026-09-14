# -*- coding: utf-8 -*-
"""量：面板的**存储精度**把 gold 挪动了多少，占 ε 的多少。

由来（2026-09-05）：冻结的 ε 面板 `bt_input_csi300_v2.parquet` 的 `close`/`factor` 存的是
**float32**；而 `s7_oracle_common.fetch_panel` 经网关拼出来的是 **float64**
（原始 close 两位小数 × adj_factor 四位小数，在 float64 里算完就是 float64）。
两份面板逐格相对差 ~6e-08（见 `s7_panel_vs_frozen.json`），但回测里有**整手取整**
——一个不连续的算子——它会把 1e-8 的价差放大成"多买一手/少买一手"。

第一次跑通 s7-cor-01 时实测：`ann_return_gross` 在两份面板上差 **1.2e-04**，
而该指标的 ε 是 2.37e-03。**这不是噪声，是 ε 预算的 5%**。
所以要逐项量、和 ε 比，并且把结论写进 gold 数据卡 —— 而不是因为"看起来很小"放过。

判据：**每一项的 |Δ| 必须显著小于该项的 ε**（这里取 1/3 作为"显著"的门）。
任一项越过，说明 gold 的可比性依赖于一个没被声明的实现细节（存储精度），必须先裁。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import genebench_config as cfg                                        # noqa: E402
from reference import b2_engine as b2                                 # noqa: E402
from reference import s7_oracle_common as cor                         # noqa: E402
from reference.gateway_client import Client                           # noqa: E402

EPS_DIR = cfg.SNAPSHOTS / "v1" / "epsilon"
FROZEN_PANEL = EPS_DIR / "bt_input_csi300_v2.parquet"
EPSILON = EPS_DIR / "epsilon_dual_daily.json"
TASK = cfg.GENEBENCH_ROOT / "reference" / "tasks" / "v1.0-smoke" / "s7-cor-01" / "task.yaml"
GATEWAY = "http://192.168.1.48:18080"
#: |Δ| 必须小于 ε 的这个比例才算"精度不影响可比性"。
BUDGET_FRACTION = 1.0 / 3.0


def epsilons() -> dict:
    d = json.loads(EPSILON.read_text(encoding="utf-8"))
    return {k: (v["epsilon"], v["tolerance_kind"]) for k, v in d["epsilon_by_metric"].items()
            if v.get("epsilon") is not None}


def main() -> int:
    task = yaml.safe_load(TASK.read_text(encoding="utf-8"))
    conf = b2.config_from_declared(task["declared"])

    gw = Client(GATEWAY, task_id="acceptance-s7-dtype", as_of=task["as_of"])
    live = cor.fetch_panel(gw, {"window": task["window"], "as_of": task["as_of"],
                                "universe": task["universe"]})
    live = live.merge(pd.read_parquet(FROZEN_PANEL, columns=["date", "code", "signal"]),
                      on=["date", "code"], how="left", suffixes=("_drop", ""))
    live = live[["date", "code", "close", "factor", "in_universe",
                 "has_price", "is_delisted", "signal"]]
    frozen = pd.read_parquet(FROZEN_PANEL)

    m_live = b2.run(live, conf).attrs["b2_metrics"]
    m_frozen = b2.run(frozen, conf).attrs["b2_metrics"]

    eps = epsilons()
    rows = {}
    worst = 0.0
    for k, (e, kind) in eps.items():
        if k not in m_live or not isinstance(m_live[k], float):
            continue
        a, b_ = m_live[k], m_frozen[k]
        delta = abs(a - b_) if kind == "absolute" else abs(a - b_) / max(abs(b_), 1e-18)
        frac = delta / e if e else float("inf")
        worst = max(worst, frac)
        rows[k] = {"gateway_float64": a, "frozen_float32": b_, "kind": kind,
                   "delta": delta, "epsilon": e, "fraction_of_epsilon": frac}

    rep = {
        "dtypes_live": {c: str(live[c].dtype) for c in ("close", "factor", "signal")},
        "dtypes_frozen": {c: str(frozen[c].dtype) for c in ("close", "factor", "signal")},
        "sell_rule": conf["sell_rule"],
        "budget_fraction": BUDGET_FRACTION,
        "metrics": rows,
        "worst_fraction_of_epsilon": worst,
        "worst_metric": max(rows, key=lambda k: rows[k]["fraction_of_epsilon"]) if rows else None,
        "ok": worst < BUDGET_FRACTION,
    }
    out = Path(__file__).resolve().parents[1] / "reports" / "s7_panel_dtype_effect.json"
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    out.chmod(0o600)
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
