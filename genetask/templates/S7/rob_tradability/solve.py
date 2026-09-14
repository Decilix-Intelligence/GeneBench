# oracle 参考解（数据面私有；在 f01 直跑，经网关 snapshot 后端产 artifact）。gold_token: <<gold_token>>
"""S7-ROB-01 回测复现（鲁棒性：四种可交易性形态 + 涨跌停）—— oracle 骨架。

主干与 S7-COR-01 的 solve.py 完全相同（取数 ②、引擎 ④、指标 ⑤、守恒 ⑥、归因 ⑦、信封 ⑧），
本题 oracle 多做的是**材料成立性断言**与**形态抽查点**，两者都写进 gold/ 供签字人核：

  ②' 形态判定（契约 §1，四列必须独立推导，不得从一个 status 标签映射出来）：
       in_universe  ← /universe（PIT 成分，逐日）
       has_price    ← /bars 的 close 非 NaN 且 /tradability.status ∉ {suspend, no_data}
       is_delisted  ← date > last_priced_date(code) 且 code 已退市（/universe 退市标记）
                      —— 「停牌仍上市」= has_price False & is_delisted False；「真退市」= is_delisted True
       limit_hit    ← |post_close/pre_close − 1| ≥ 0.095（契约 §4 判定式；pre_close 未知 → 不触板）
  ④' 材料成立性（任一不满足 → 本题回炉，不出包）：窗口内四形态各至少出现一次、
       至少一只标的在 is_delisted 翻 True 当天仍被持有（否则退市强制清仓规则空转 —— D-06）、
       至少一个持仓日触及涨跌停。把 (形态, code, date) 各抽 1 条写进 gold/probe_points.json。
  ⑤' 引擎逐日表额外导出：force_liquidated[{date, code, value, fee}]、suspended_valuation[{date, code, last_close}]，
       用于核「退市清仓计卖出费用、计入换手分子、不占 n_drop」（契约 §4）与「停牌按最后有效 close 估值」。
  ⑥' 守恒残差在退市清仓日与停牌估值日**单独**再算一次 max，写进 gold/ledger_by_regime.json；
       artifact 里只报总的 max_abs_residual。

其余步骤直接复用 cor_reproduce/solve.py（import 即可，不复制）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

# 共用主干在 reference/ 下 —— **不 import 兄弟模板**（D-31 推论）
from reference import s7_oracle_common as cor    # 主干：取数 / 引擎 / 指标 / 信封

# 统一 I/O 契约（裁定 2026-09-05）：读标准位置的任务规格、经网关取数、写标准 artifact 路径。
# **不接受任何 stage 特定的 env/argv** —— 从任务目录读得出来的东西，一律不从环境拿。
from reference.oracle_io import context as _oracle_context
from reference.oracle_io import write as _oracle_write
from reference.oracle_io import write_private as _write_private
CTX = _oracle_context(__file__)

REGIMES = {
    "normal":       lambda p: p.in_universe & p.has_price & ~p.is_delisted,
    "dropped":      lambda p: ~p.in_universe & p.has_price & ~p.is_delisted,
    "suspended":    lambda p: ~p.has_price & ~p.is_delisted,
    "delisted":     lambda p: p.is_delisted,
}


def assert_material(panel: pd.DataFrame, daily: pd.DataFrame, task_dir: Path) -> None:
    """④' 材料成立性 + 抽查点。"""
    points = {}
    for name, sel in REGIMES.items():
        rows = panel[sel(panel)]
        assert len(rows), f"窗口内没有形态 {name} —— 本题材料不成立，回炉"
        points[name] = rows.iloc[0][["code", "date"]].to_dict()
    # TODO: 由引擎导出的 force_liquidated 断言非空（退市当天仍在持仓）
    # TODO: 由引擎导出的 limit 日志断言至少一个持仓日触板
    _write_private(task_dir / "gold" / "probe_points.json", points)


def main(task_dir: str, arm: str = "strict") -> None:
    from reference import artifact_schema as sch
    from reference.gateway_client import Client
    td = Path(task_dir)
    task = cor.load_task(td)
    gw = Client.for_context(CTX)
    panel = cor.fetch_panel(gw, task, CTX.task_dir)
    daily = cor.run_engine(panel, task["declared"])
    assert_material(panel, daily, td)
    meta = json.loads((td / "work" / "signal.meta.json").read_text(encoding="utf-8"))
    art = cor.build_artifact(task, daily, panel, meta, arm)
    v = sch.validate(art, task={k: task[k] for k in ("task_id", "stage", "declared", "underdetermined")})
    assert v.ok, [str(f) for f in v.findings]
    # N-44：逐日台账按契约落盘（`/task/ledger.parquet` 的 gold 侧对应物）。
    # 走 `files_io.write_contracted` 而不是各写一遍 to_parquet ——
    # 五个模板各抄一遍的下场是它们慢慢漂开，而漂开表现为
    # 「同一道题两次 gold 的 sha 不同」，没有任何东西报错。
    from reference.files_io import write_contracted
    write_contracted(daily, "S7", Path(task_dir) / "gold")
    # **标准 artifact 路径**（统一 I/O 契约 D-31）—— 跑批的校验器只看这一处。
    # 只写 gold/ 的话，`run_oracles` 找不到产物，而「找不到」曾被记成「零 finding」。
    _oracle_write(CTX, art)
    _write_private(td / "gold" / "oracle_artifact.json", art)


if __name__ == "__main__":
    main(str(_oracle_context(__file__).task_dir))
