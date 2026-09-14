# oracle 参考解（数据面私有；在 f01 直跑，经网关 snapshot 后端产 artifact）。gold_token: <<gold_token>>
# S4-OPS-01：与 cor_ic_recompute 同一套 IC 计算，外加审计轨迹。结算（卡 5.x）除比 ic_stats 外还核：
#   ① audit.input_sha256 == 实测 work/factor_panel.parquet 的 sha256 == meta.json.sha256；
#   ② audit.fetches 与网关 access_log 按 (endpoint, params) 逐条对得上（验行为不验申报：多报少报都违例）；
#   ③ provenance 含 meta.json 的 S3 artifact_id；④ seed == audit.bootstrap.seed；
#   ⑤ Repro：用 /task/solve_s4.py 同 seed 在数据面重跑，ic_stats 逐位相同（CORE-Bench 复现范式）。
import hashlib, json, sys

import yaml
from pathlib import Path

import pandas as pd

# 统一 I/O 契约（裁定 2026-09-05）：读标准位置的任务规格、经网关取数、写标准 artifact 路径。
# **不接受任何 stage 特定的 env/argv** —— 从任务目录读得出来的东西，一律不从环境拿。
from reference.oracle_io import context as _oracle_context
from reference.oracle_io import write as _oracle_write
CTX = _oracle_context(__file__)

TASK = yaml.safe_load(Path("task.yaml").read_text(encoding="utf-8"))   # 数据面全量 task.yaml
D = TASK["declared"]
SEED, N_BOOT, BLOCK_LEN = 0, 1000, 20
FETCHES: list[dict] = []


def gw(path: str, **params) -> pd.DataFrame:
    """同 cor 模板，但每次请求都追加到 FETCHES（endpoint, params, rows），顺序即发出顺序。"""
    raise NotImplementedError


def sha256_file(p: str) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main() -> None:
    meta = json.loads(Path("work/factor_panel.meta.json").read_text())   # {sha256, source_stage:"S3", artifact_id, factor_id}
    input_sha = sha256_file("work/factor_panel.parquet")
    assert input_sha == meta["sha256"], "材料哈希与 meta 不符——材料被动过"
    from reference import s4_oracle_common as s4
    from reference.gateway_client import Client
    gw = Client.for_context(CTX)
    X = s4.build_inputs(gw, TASK, max(D["holding_periods"]))
    by_h = s4.ic_by_horizon(s4.load_factor_panel("work/factor_panel.parquet"), X, D, SEED)
    # 审计里的取数清单 = 客户端台账（每次请求的 endpoint/params/fetched_at/status/rows），
    # 不是手写的；手写的清单与真实请求会漂，而漂开正是本题要抓的。
    FETCHES.extend(gw.ledger)
    art = {
        "schema_version": "1.0", "artifact_id": f"{TASK['task_id']}-oracle", "stage": "S4",
        "task_id": TASK["task_id"], "config_id": "oracle", "arm": "strict", "seed": SEED,
        "as_of": TASK["as_of"], "produced_at": pd.Timestamp.utcnow().isoformat(),
        "provenance": [{"stage": "S3", "artifact_id": meta["artifact_id"]}],
        "declarations": dict(D),
        "payload": {"ic_stats": by_h.get(str(min(D["holding_periods"]))), "ic_by_horizon": by_h,
                    "audit": {"input_sha256": input_sha, "fetches": FETCHES,
                              "bootstrap": {"seed": SEED, "n_resamples": N_BOOT, "block_length": BLOCK_LEN},
                              "code_sha256": sha256_file(__file__)}},
    }
    _oracle_write(CTX, art)               # 标准路径 + 0600（红线 5）
if __name__ == "__main__":
    main()
