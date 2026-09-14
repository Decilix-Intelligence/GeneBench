# -*- coding: utf-8 -*-
"""卡 2.2 的参考回测：同一 gold 信号 → qlib TopkDropout → 指标。

    cd $REPO && $GENEBENCH_ROOT/env/bin/python -m reference.backtest --factor <id>

**这是 ε 的被测对象。** ε 不是从"重复跑 N 次"里来的 —— 见 `ops/specs/design_notes.md` D-05：
qlib 的回测在同一 gold 信号上**完全确定性**（`exchange.py` 里 `random.seed(0)` 硬编码，
`TopkDropoutStrategy` 默认 `method_buy/sell` 都是确定性选法）。
五种子极差必为 0，那是**标定失效**不是标定成功。
ε 改由**跨库版本**标定：同一份代码、同一份 gold，在 numpy/pandas 版本不同的 venv 里跑，取极差 ×1.5。

所以本模块有一条硬性设计要求：**除了库版本，其余一切必须逐位可复现** ——
配置写死在 :data:`CONFIG`、信号从 gold parquet 读、不采样、不并行归约。
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import genebench_config as cfg
from reference import factor_exec as fx

RESULT_DIR: Path = cfg.SNAPSHOTS_V1 / "epsilon"

#: 回测配置。**冻结项** —— 改任何一条都要重标 ε。
CONFIG: dict[str, Any] = {
    "universe": "csi300",
    "start": "2019-01-02",
    "end": "2026-07-03",          # = 持有期 20 日的可用求值右端（卡 2.1a）
    "topk": 50,
    "n_drop": 5,
    "account": 1e8,
    "deal_price": "close",
    "open_cost": 0.0005,
    "close_cost": 0.0015,
    "min_cost": 5.0,
    "limit_threshold": 0.095,
    "only_tradable": True,        # 可交易性过滤开启（实施稿卡 2.2 原文）
    "trade_unit": 100,
    "freq": "day",
    "benchmark": "equal_weight_universe",   # v1 provider 无指数标的，见 N-23
    # qlib 的 BaseSignalStrategy 默认 risk_degree=0.95（signal_strategy.py:32），
    # 即只部署 95% 的可用现金 —— 而声明第 5 节「可用现金等额分配」字面隐含 100%。
    # 这是声明缺口 ③，显式写死为 1.0 让实现 A 与声明一致。
    "risk_degree": 1.0,
}

#: 年化因子。与第一批冻结项一致（Sharpe 年化 √252）。
ANN: float = 252.0

__all__ = ["CONFIG", "run_backtest", "metrics", "env_fingerprint"]


def env_fingerprint() -> dict[str, Any]:
    """完整包清单 —— 签字要求「记录每个版本组合的完整包清单进 manifest」。"""
    try:
        from importlib.metadata import distributions
        pkgs = {d.metadata["Name"].lower(): d.version
                for d in distributions() if d.metadata.get("Name")}
    except Exception:
        pkgs = {}
    return {
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "platform": platform.platform(),
        "key": {k: pkgs.get(k) for k in ("numpy", "pandas", "scipy", "pyqlib", "pyarrow")},
        "packages": dict(sorted(pkgs.items())),
    }


def load_signal(factor_id: str, universe: str, start: str, end: str) -> pd.Series:
    """从 gold 读一条因子作为信号，MultiIndex (datetime, instrument)。"""
    p = fx.GOLD_DIR / universe / f"{factor_id}.parquet"
    if not p.exists():
        raise FileNotFoundError(f"gold 里没有 {factor_id}：{p}")
    t = pd.read_parquet(p)
    t = t[(t["date"] >= start.replace("-", "")) & (t["date"] <= end.replace("-", ""))]
    if t.empty:
        raise ValueError(f"{factor_id} 在 {start}..{end} 无数据")
    idx = pd.MultiIndex.from_arrays(
        [pd.to_datetime(t["date"], format="%Y%m%d"), t["code"].astype(str)],
        names=["datetime", "instrument"])
    s = pd.Series(t["value"].to_numpy(dtype="float64"), index=idx, name="score")
    return s.sort_index()


def equal_weight_benchmark(universe: str, start: str, end: str) -> pd.Series:
    """等权宇宙收益作为基准。

    **为什么不是沪深 300 指数**：v1 provider 是**只有股票**的（instruments 取自
    ``universe_pit``，那里面没有指数标的），所以 ``SH000300`` 在 provider 里不存在。
    qlib 的 ``PortfolioMetrics`` 必须有个基准才肯初始化。

    这对 ε **不构成问题** —— ε 用的几个指标（年化收益、Sharpe、MDD、换手）
    都是从 ``report["return"]`` 自己算的，**不经过基准**。
    但基准相对指标（IR / alpha / 超额）在 v1 provider 上**确实拿不到**，
    已登记 N-23，S7 回测题之前必须解决。
    """
    from qlib.data import D

    df = D.features(D.instruments(universe), ["$close/Ref($close,1)-1"],
                    start_time=start, end_time=end, freq="day")
    s = df.iloc[:, 0]
    if s.index.names == ["instrument", "datetime"]:
        s = s.swaplevel().sort_index()
    return s.groupby(level="datetime").mean().fillna(0.0)


def run_backtest(factor_id: str, conf: "dict | None" = None) -> tuple[pd.DataFrame, dict]:
    c = dict(CONFIG, **(conf or {}))
    fx.init_qlib()
    from qlib.backtest import backtest as qbacktest
    from qlib.contrib.strategy import TopkDropoutStrategy

    sig = load_signal(factor_id, c["universe"], c["start"], c["end"])
    strategy = TopkDropoutStrategy(
        signal=sig, topk=c["topk"], n_drop=c["n_drop"],
        only_tradable=c["only_tradable"],
        risk_degree=c["risk_degree"],
    )
    executor = {"class": "SimulatorExecutor", "module_path": "qlib.backtest.executor",
                "kwargs": {"time_per_step": c["freq"], "generate_portfolio_metrics": True}}
    exchange_kwargs = {
        "freq": c["freq"], "limit_threshold": c["limit_threshold"],
        "deal_price": c["deal_price"], "open_cost": c["open_cost"],
        "close_cost": c["close_cost"], "min_cost": c["min_cost"],
        "trade_unit": c["trade_unit"],
    }
    pm, _ind = qbacktest(
        start_time=c["start"], end_time=c["end"], strategy=strategy, executor=executor,
        account=c["account"],
        benchmark=equal_weight_benchmark(c["universe"], c["start"], c["end"]),
        exchange_kwargs=exchange_kwargs,
    )
    return _extract_report(pm), c


def _extract_report(pm: Any) -> pd.DataFrame:
    """从 qlib 的 portfolio_metric_dict 里取出日频 report DataFrame。

    键名随 qlib 版本变（``day`` / ``1day`` / ``freq`` 元组），
    所以按结构找而不是按名字猜 —— 名字猜错了 KeyError 还算好的，
    猜到一个**别的** DataFrame 才是灾难。
    """
    def walk(node):
        if isinstance(node, pd.DataFrame):
            if "return" in node.columns:
                yield node
            return
        if isinstance(node, dict):
            for v in node.values():
                yield from walk(v)
        elif isinstance(node, (list, tuple)):
            for v in node:
                yield from walk(v)

    found = list(walk(pm))
    if not found:
        raise RuntimeError(f"没在回测产物里找到含 'return' 列的 DataFrame；顶层键 = "
                           f"{list(pm.keys()) if isinstance(pm, dict) else type(pm)}")
    if len(found) > 1:
        # 多个候选时取行数最多的那个，并把情况打出来 —— 不静默挑一个
        print(f"  ⚠ 回测产物里有 {len(found)} 个含 'return' 的表，取最长的那个 "
              f"（长度 {[len(f) for f in found]}）", flush=True)
        found.sort(key=len, reverse=True)
    return found[0]


def _total_cost(report: pd.DataFrame, account: "float | None") -> float:
    """全期费用合计 ÷ 初始资金（声明第 6 节的字面口径）。"""
    if "total_cost" in report.columns and account:
        return float(report["total_cost"].astype("float64").iloc[-1] / account)
    # 退路：只有费用率列时无法还原绝对金额，返回旧口径并由调用方标注
    return float(report["cost"].astype("float64").sum()) if "cost" in report else 0.0


def metrics(report: pd.DataFrame, account: float = None) -> dict[str, float]:
    """**逐指标**给数——签字要求「不要只给一个全局数」。

    ⚠ **`total_cost` 必须走绝对金额通道，不能对逐日费用率求和。**

    qlib 的 report 里有**两列同名前缀**的东西（`account.py:288-289`）：

    * ``total_cost`` —— 累计**绝对费用**（元）
    * ``cost``       —— **当日费用率** = ``当日费用 / 上一 bar 收盘总资产``

    首版对 ``cost`` 列求和（= 逐日**比率**相加），得到的量随账户净值路径漂移，
    而声明写的是「全期费用合计 ÷ 初始资金」。实测两者差 **26.39%**
    （0.372950 vs 0.471385），差值正好等于费用加权的 ``TA_{t-1}/TA_0`` 调和均值 **1.263937**。

    **为什么 `turnover` 没被这个坑咬到**：turnover 指标是「逐日比率的**均值**」，
    分子分母都在当日量级上，净值漂移在均值里抵消；
    ``total_cost`` 是「逐日比率的**求和**」，漂移**不抵消**，直接乘进结果。
    """
    r_gross = report["return"].astype("float64")
    cost = report["cost"].astype("float64") if "cost" in report else pd.Series(0.0, index=r_gross.index)
    r_net = r_gross - cost
    turn = report["turnover"].astype("float64") if "turnover" in report else pd.Series(np.nan, index=r_gross.index)

    def ann_ret(x): return float((1.0 + x).prod() ** (ANN / len(x)) - 1.0)
    def ann_vol(x): return float(x.std(ddof=1) * np.sqrt(ANN))
    def sharpe(x):
        s = x.std(ddof=1)
        return float(x.mean() / s * np.sqrt(ANN)) if s > 0 else float("nan")
    def sortino(x):
        d = x[x < 0.0]
        s = d.std(ddof=1) if len(d) > 1 else np.nan
        return float(x.mean() / s * np.sqrt(ANN)) if s and s > 0 else float("nan")
    def mdd(x):
        nav = (1.0 + x).cumprod()
        return float((nav / nav.cummax() - 1.0).min())

    out = {
        "n_days": float(len(r_gross)),
        "ann_return_gross": ann_ret(r_gross), "ann_return_net": ann_ret(r_net),
        "ann_vol_gross": ann_vol(r_gross), "ann_vol_net": ann_vol(r_net),
        "sharpe_gross": sharpe(r_gross), "sharpe_net": sharpe(r_net),
        "sortino_net_mar0": sortino(r_net),
        "max_drawdown_gross": mdd(r_gross), "max_drawdown_net": mdd(r_net),
        # 绝对金额通道；拿不到就退回旧口径并显式标注（不静默）
        "total_cost": _total_cost(report, account),
        "total_cost_source": ("absolute_cumulative/initial_capital"
                              if "total_cost" in report.columns and account
                              else "FALLBACK_sum_of_daily_rates"),
        # turnover 双记（第一批冻结项第 4 条）
        "turnover_one_way_mean": float(turn.mean() / 2.0),
        "turnover_two_way_mean": float(turn.mean()),
        "turnover_two_way_sum": float(turn.sum()),
        "win_rate_net": float((r_net > 0).mean()),
    }
    out["calmar_net"] = (out["ann_return_net"] / abs(out["max_drawdown_net"])
                         if out["max_drawdown_net"] else float("nan"))
    return out


def main(argv: "list[str] | None" = None) -> int:
    p = argparse.ArgumentParser(description="卡 2.2 参考回测")
    p.add_argument("--factor", default="qlib_alpha158.ROC20")
    p.add_argument("--out", default=None, help="结果 JSON 落点（默认按环境指纹命名）")
    a = p.parse_args(argv)
    report, conf = run_backtest(a.factor)
    m = metrics(report, account=conf["account"])
    env = env_fingerprint()
    payload = {"factor": a.factor, "config": conf, "metrics": m, "env": env}
    cfg.create_dir(RESULT_DIR)
    tag = f"np{env['key']['numpy']}_pd{env['key']['pandas']}"
    out = Path(a.out) if a.out else RESULT_DIR / f"bt_{a.factor}_{tag}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    out.chmod(0o600)
    print(f"[{tag}] {a.factor}  天数 {m['n_days']:.0f}")
    for k in ("ann_return_net", "sharpe_net", "max_drawdown_net",
              "turnover_one_way_mean", "turnover_two_way_mean"):
        print(f"    {k:<26} {m[k]!r}")
    print(f"→ {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# --------------------------------------------------------------------------- 实现 B2（gold）
#
# 裁定 N-83（2026-09-05）：**S7 的 gold 引擎是实现 B2**，不是本文件上面那个 qlib 实现（A）。
# qlib 有未归因偏离（N-39）且偏离清单未成，不能定义 gold；A 留作**对账参照**。
#
# 这里只做**再导出**，实现在 `reference/b2_engine.py` —— 两者放在同一个文件里，
# 迟早会有人在改 A 的时候顺手动到 B 的常量，而契约开篇写死了
# 「实现 B 不得阅读 qlib 的 exchange/executor/strategy」。物理隔开是这条纪律的落点。
from reference.b2_engine import (          # noqa: E402,F401
    DAILY_COLUMNS,
    WrapperError,
    config_from_declared,
    run,
)
