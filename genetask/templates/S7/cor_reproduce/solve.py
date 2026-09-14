# oracle 参考解（数据面私有；在 f01 直跑，经网关 snapshot 后端产 artifact）。gold_token: <<gold_token>>
"""S7-COR-01 回测复现（正确性）—— oracle 骨架。

思路（与 ops/specs/backtest_contract.md v3 逐节对应；撮合引擎用 reference/backtest.py 的实现 B，
**不得**照着 qlib exchange/executor 写 —— D-11：ε 量的是「独立实现同一份声明」的差）：

  ① 读任务：reference/tasks/<set>/<id>/task.yaml → as_of / window / universe / declared / inputs。
  ② 取数（全部经网关，config_id=oracle，每请求带 as_of=task.as_of；端点 → 拿到什么）：
       /calendar?calendar_id=<declared.calendar_id>&start=<window.start − 暖机>&end=<window.end>
                                                            → 开市日序列 D（is_open）
       /universe?universe=<task.universe>&start&end        → in_universe(code, d)   [PIT，逐日成分]
       /bars?codes=<全体曾入选 code>&start&end&fields=close  → 原始 close；返回体 status
                                                              （suspend / no_data → has_price=False）
       /adj?codes&start&end                                 → adj_factor；post_close = close × adj_factor
                                                              （契约 §1：原始价 = close / factor；TODO 核对网关
                                                              adj_factor 的基准日是否 = 契约 factor 的口径）
       /tradability?codes&start&end                         → status ∈ {trade,suspend,limit_up,limit_down,no_data}
     is_delisted(code, d) = d > 该 code 的最后一个有价日 且 该 code 在 as_of 前已退市（/universe 的退市标记）
       —— 「停牌仍上市」与「真退市」必须分开（契约 §1 四形态）。
     涨跌停按契约 §4 判定式 |post_close / pre_close − 1| ≥ 0.095 自算（A-9 已声明局限），
       pre_close = 前一交易日最后一个有效 post_close；窗口内此前无价 → 不视为触板。
  ③ 信号：work/signal.parquet (date, code, signal) 按 (date, code) 左连接到面板；
       work/signal.meta.json {stage, artifact_id, sha256, max_date} → provenance。
  ④ 拼契约 §1 八列面板 [date, code, close(post), factor, in_universe, has_price, is_delisted, signal]
       → reference.backtest.run(panel, config=cfg_from_declared(declared))
     cfg 由 declared 直接映射：strategy.{type,topk,n_drop}、rebalance_frequency、first_rebalance_day、
       cost_model.{buy_bps,sell_bps,min_cost_cny,impact_cost}、lot_size、initial_capital、settlement、
       fill_price、share_accounting、delisting_policy、tradability_policy。
     引擎逐日输出：{date, cash, mv, total_assets, r_gross, r_net, buy_val, sell_val, cost_abs, ta_pre_trade}
       —— cash / mv / total_assets 三者**独立累计**，守恒残差才有意义（不是同一变量的两种叫法）。
  ⑤ 指标（契约 §6 + 卡 2.3 S7_METRICS 11 项，ANN=252，n=len(r)）：
       ann_return_gross/net = prod(1+r)^(ANN/n) − 1
       ann_vol_net          = std(r_net, ddof=1)·√ANN
       sharpe_gross/net     = mean(r)/std(r, ddof=1)·√ANN（rf=0）
       sortino_net_mar0     = mean(r_net)/std(min(r_net, 0), ddof=1)·√ANN（MAR=0，仅下行观测）
       max_drawdown_net     = min(nav/cummax(nav) − 1)，nav = cumprod(1+r_net)
       calmar_net           = ann_return_net / |max_drawdown_net|
       total_cost           = Σ cost_abs / initial_capital   ← **绝对金额通道**（契约 §8 ①；D-06 实例 6）
       turnover_one_way_mean = mean(sell_val / ta_pre_trade)；two_way = mean((buy_val+sell_val)/ta_pre_trade)（A-5）
       收益序列含建仓日（N-5）；换手分子含建仓与退市强制清仓（N-6）。
  ⑥ ledger_check.max_abs_residual = max_d |cash_d + mv_d − total_assets_d|。
  ⑦ attribution：total = ann_return_net；cost = ann_return_net − ann_return_gross；
       bench_d = 当日 in_universe 成分股 post_close 的等权日收益；
       beta = OLS(r_gross ~ bench).slope × ann(bench)；alpha = total − beta − cost（守恒由构造保证）。
  ⑧ 信封：schema_version="1.0", stage="S7", task_id, config_id="oracle", arm, seed=0, as_of,
       produced_at=UTC ISO, provenance=[{stage: meta.stage, artifact_id: meta.artifact_id}],
       declarations=deepcopy(declared)（一字不改）, payload={metrics, n_days, rebalance_frequency, ledger_check, attribution}。
  ⑨ 自检（O1）：reference.artifact_schema.validate(artifact, task=taskspec) 零 finding；
       再对 declared 的任一字段做已知突变 → 必须出 declaration_mismatch。
"""
from __future__ import annotations

import json
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

# 统一 I/O 契约（裁定 2026-09-05）：读标准位置的任务规格、经网关取数、写标准 artifact 路径。
# **不接受任何 stage 特定的 env/argv** —— 从任务目录读得出来的东西，一律不从环境拿。
from reference.oracle_io import context as _oracle_context
from reference.oracle_io import write as _oracle_write
from reference.oracle_io import write_private as _write_private
CTX = _oracle_context(__file__)

from reference.s7_oracle_common import (ANN, WARMUP_DAYS, attribution,  # noqa: F401
                                        build_artifact, fetch_panel, load_task,
                                        metrics, run_engine)


def main(task_dir: str, arm: str = "strict") -> None:
    from reference import artifact_schema as sch
    from reference.gateway_client import Client
    task = load_task(Path(task_dir))
    gw = Client.for_context(CTX)
    panel = fetch_panel(gw, task, CTX.task_dir)
    daily = run_engine(panel, task["declared"])
    meta = json.loads((Path(task_dir) / "work" / "signal.meta.json").read_text(encoding="utf-8"))
    art = build_artifact(task, daily, panel, meta, arm)
    v = sch.validate(art, task={k: task[k] for k in ("task_id", "stage", "declared", "underdetermined")})
    assert v.ok, [str(f) for f in v.findings]                                    # O1
    # N-44：逐日台账按契约落盘（`/task/ledger.parquet` 的 gold 侧对应物）。
    # 走 `files_io.write_contracted` 而不是各写一遍 to_parquet ——
    # 五个模板各抄一遍的下场是它们慢慢漂开，而漂开表现为
    # 「同一道题两次 gold 的 sha 不同」，没有任何东西报错。
    from reference.files_io import write_contracted
    write_contracted(daily, "S7", Path(task_dir) / "gold")
    # **标准 artifact 路径**（统一 I/O 契约 D-31）—— 跑批的校验器只看这一处。
    # 只写 gold/ 的话，`run_oracles` 找不到产物，而「找不到」曾被记成「零 finding」。
    _oracle_write(CTX, art)
    _write_private(Path(task_dir, "gold", "oracle_artifact.json"), art)


if __name__ == "__main__":
    main(str(_oracle_context(__file__).task_dir))
