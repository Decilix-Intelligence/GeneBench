# oracle 参考解（数据面私有；在 f01 直跑，经网关 snapshot 后端产 artifact）。gold_token: <<gold_token>>
# S4-COR-01：在冻结评估设定下对 gold 因子面板复算 IC 族。gold = 同一脚本在 f01 对 gold_args.factor_id 的输出。
#
# 端点用法（参数名以网关 OpenAPI 为准，每次请求都带 as_of）：
#   /calendar   {start, end, as_of}                → is_open==1 的交易日序列 D；持有期 h 的「远期日」= D 中 d 之后第 h 个交易日
#   /universe   {universe, date, as_of}            → 每个 d 的 PIT 成分名单 U_d（不用一份静态名单）
#   /tradability {code|codes, start, end, as_of}   → status；d 日 status != "trade" 的格子无效（收盘后调仓要求 d 日可成交）
#   /bars       {code|codes, start, end, fields="close,has_daily", as_of}  → 收盘价；has_daily==0 的日子视为缺
#   /adj        {code|codes, start, end, as_of}    → adj_factor；adj_close = close * adj_factor（后复权，与 S2 口径一致）
#   取价区间要覆盖到 window.end 之后 max(h) 个交易日（仍 ≤ as_of；窗口 end 已选在 as_of 前 ≥20 个交易日）。
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

TASK = yaml.safe_load(Path("task.yaml").read_text(encoding="utf-8"))   # 数据面全量 task.yaml（含 as_of / window / declared）
D = TASK["declared"]
PANEL = "work/factor_panel.parquet"
GATEWAY = "http://gateway:18080"
SEED = 0
N_BOOT, BLOCK_LEN = 1000, 20       # 待冻结：CI 的 block 长度 / 重采样次数不在声明字段里（见 notes）


def gw(path: str, **params) -> pd.DataFrame:
    """GET GATEWAY+path，params 加 as_of；返回 DataFrame。TODO: requests + 分页 + 422/403 直接抛。"""
    raise NotImplementedError


# forward_returns / ic_series / block_bootstrap_ci / summarize 已收进 reference/s4_oracle_common（D-31）


def main() -> None:
    assert D["ic_method"] == "spearman" and D["rebalance_timing"] == "close"
    # 共用主干在 reference/ 下（D-31）。第一版这里是 `adj_close = … = None` 的 TODO 桩。
    from reference import s4_oracle_common as s4
    from reference.gateway_client import Client
    X = s4.build_inputs(Client.for_context(CTX), TASK, max(D["holding_periods"]))
    factor = s4.load_factor_panel(PANEL)
    by_h = s4.ic_by_horizon(factor, X, D, SEED)
    art = {
        "schema_version": "1.0", "artifact_id": f"{TASK['task_id']}-oracle", "stage": "S4",
        "task_id": TASK["task_id"], "config_id": "oracle", "arm": "strict", "seed": SEED,
        "as_of": TASK["as_of"], "produced_at": pd.Timestamp.utcnow().isoformat(), "provenance": [],
        "declarations": dict(D),
        "payload": {"ic_stats": by_h[str(min(D["holding_periods"]))], "ic_by_horizon": by_h},
    }
    _oracle_write(CTX, art)               # 标准路径 + 0600（红线 5）
if __name__ == "__main__":
    main()
