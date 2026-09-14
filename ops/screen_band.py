"""screen 的带判据。形状 = materiality.py 要的 outside_band(metric, a, b) -> bool。

四种 tolerance.kind（schema.py 的 TOLERANCE_KINDS）各走各的：
  epsilon → 读 snapshots/v1/epsilon/epsilon_dual_<tier>.json 的 epsilon_by_metric
  exact   → a != b 即超带（S1/S2/S5/S6/S8 的探针题都是 exact）
  none    → 本题不进结算（s4-rob-02）
  tau     → 面板秩相关下限，形状不是逐指标带（s3-rob-02）
后两种抛 BandUndecided：让整题记 inconclusive 并停下汇报，**不许**退化成常数容差。
"""
from __future__ import annotations
import json
from pathlib import Path
from reference import epsilon_dual as ED

CAL = Path("/data/shared/genebench/snapshots/v1/epsilon")


class BandUndecided(RuntimeError):
    """判据未裁定。按 run_materiality_screen.py:131：「跑不起来」不是「没差别」。"""


def _rel(a: float, b: float) -> float:            # 与 epsilon_dual.py 的 _rel 同式，抄一份避免依赖私有名
    m = max(abs(a), abs(b))
    return abs(a - b) / m if m > 0 else 0.0


class Band:
    def __init__(self, tolerance: dict):
        self.kind = tolerance.get("kind")
        self.tier = tolerance.get("tier", "daily")
        self.table: dict = {}
        if self.kind == "epsilon":
            doc = json.loads((CAL / f"epsilon_dual_{self.tier}.json").read_text())
            if not doc.get("usable"):
                # weekly: ann_return_gross implausible；monthly: 另有 sharpe_net / total_cost
                raise BandUndecided(f"ε 带 {self.tier} 档 usable=false，不许用作判据")
            self.table = doc["epsilon_by_metric"]

    def outside(self, metric: str, a, b) -> bool:
        if self.kind == "exact":
            return a != b
        if self.kind != "epsilon":
            raise BandUndecided(f"tolerance.kind={self.kind!r} 没有逐指标带判据"
                                f"（τ 是面板秩相关下限，none 表示本题不进结算）")
        rec = self.table.get(metric)
        if rec is None:
            raise BandUndecided(f"指标 {metric} 不在 {self.tier} 档 ε 表里（该表只覆盖 9 个回测指标）")
        eps, status = rec.get("epsilon"), rec.get("status")
        if eps is None:
            if status == "no_implementation_freedom":
                return a != b                     # 【待签字 §7-①】按「要求精确相等」处理
            if status == "invalid_below_noise_floor":
                raise BandUndecided(f"{metric} 在噪声底以下，本指标不进比较")
            raise BandUndecided(f"{metric} 的 ε 是 {status} —— 不得用其他指标的 ε 代填，停下汇报")
        return abs(a - b) > eps if ED.tolerance_kind(metric) == "absolute" else _rel(a, b) > eps
