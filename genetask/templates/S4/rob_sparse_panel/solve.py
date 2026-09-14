# oracle 参考解（数据面私有；在 f01 直跑，经网关 snapshot 后端产 artifact）。gold_token: <<gold_token>>
# S4-ROB-01：脏面板下的 IC 复算。题源：D-06 #2（gtja_191.017 在 float32 下 2,469 格溢出）+ 卡 1.2 的停牌/缺行坑。
# 材料构造（f01，物化 inputs 时做）：取 gold_args.factor_id 的 gold 面板（float64），**不做任何替换**——
#   它天然含 Inf/NaN 与 |value|>1e30 的格；再确认窗口内 csi300 至少有 3 只停牌 ≥5 日的票（tradability 视图查）。
# 判别力（D-06）：材料落盘前先跑一次「坏解」——fillna(0) 与 float32 cast 两种——ic_stats 必须与 oracle 明显不同，
#   否则这道题的陷阱是空的，换因子。
#
# 端点用法与 cor_ic_recompute 相同（/calendar /universe /tradability /bars(fields="close,has_daily") /adj）。
import json, sys

import yaml
from pathlib import Path

import numpy as np
import pandas as pd

# 统一 I/O 契约（裁定 2026-09-05）：读标准位置的任务规格、经网关取数、写标准 artifact 路径。
# **不接受任何 stage 特定的 env/argv** —— 从任务目录读得出来的东西，一律不从环境拿。
from reference.oracle_io import context as _oracle_context
from reference.oracle_io import write as _oracle_write
CTX = _oracle_context(__file__)

TASK = yaml.safe_load(Path("task.yaml").read_text(encoding="utf-8"))   # 数据面全量 task.yaml
D = TASK["declared"]
SEED, N_BOOT, BLOCK_LEN = 0, 1000, 20


def gw(path: str, **params) -> pd.DataFrame:
    raise NotImplementedError          # TODO: 同 cor_ic_recompute


def classify_invalid(factor, in_universe, tradable, has_close, fwd):
    """按题面四类计数；一个格子只记第一个命中的原因（顺序：nonfinite → missing_value → untradable → no_forward_close）。
    只在 PIT 宇宙内的格子计数——不在宇宙里的格子不是「无效」，是「不在样本」。"""
    inu = in_universe
    present = factor.notna()
    nonfinite = inu & present & ~np.isfinite(factor.where(present, 0.0))
    missing = inu & ~present
    untradable = inu & present & ~nonfinite & ~tradable
    no_fwd = inu & present & ~nonfinite & tradable & (~has_close | fwd.isna())
    valid = inu & present & ~nonfinite & tradable & has_close & fwd.notna()
    counts = {k: int(v.to_numpy().sum()) for k, v in
              (("nonfinite", nonfinite), ("missing_value", missing), ("untradable", untradable), ("no_forward_close", no_fwd))}
    return valid, counts


def main() -> None:
    panel = pd.read_parquet("work/factor_panel.parquet")
    assert panel["value"].dtype == np.float64, "面板必须保持 float64（题面禁止窄化）"
    from reference import s4_oracle_common as s4
    from reference.gateway_client import Client
    X = s4.build_inputs(Client.for_context(CTX), TASK, max(D["holding_periods"]))
    factor = s4.load_factor_panel("work/factor_panel.parquet").reindex(index=X["window"], columns=X["codes"])
    adj_close, in_universe, tradable, has_close = (X["adj_close"], X["in_universe"],
                                                   X["tradable"], X["has_close"])
    n_universe = in_universe.sum(axis=1)
    by_h, invalid = {}, {}
    for h in sorted(D["holding_periods"]):
        fwd = s4.forward_returns(factor.index, adj_close, h)
        valid, counts = classify_invalid(factor, in_universe, tradable, has_close, fwd)
        invalid[str(h)] = counts
        # Spearman 对 Inf 不安全 —— 先按 valid 过滤再 rank（ic_series 只用 valid 格）
        ic, n_valid = s4.ic_series(factor, fwd, valid, D["tie_handling"])
        by_h[str(h)] = s4.summarize(ic, n_valid, n_universe, SEED, D)
    h0 = str(min(D["holding_periods"]))
    art = {
        "schema_version": "1.0", "artifact_id": f"{TASK['task_id']}-oracle", "stage": "S4",
        "task_id": TASK["task_id"], "config_id": "oracle", "arm": "strict", "seed": SEED,
        "as_of": TASK["as_of"], "produced_at": pd.Timestamp.utcnow().isoformat(), "provenance": [],
        "declarations": dict(D),
        "payload": {"ic_stats": by_h[h0], "ic_by_horizon": by_h,
                    "invalid_cells": invalid[h0], "invalid_cells_by_horizon": invalid},
    }
    _oracle_write(CTX, art)               # 标准路径 + 0600（红线 5）
if __name__ == "__main__":
    main()
