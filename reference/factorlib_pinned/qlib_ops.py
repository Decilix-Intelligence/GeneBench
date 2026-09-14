from __future__ import annotations

import math

import numpy as np
import pandas as pd
from qlib.data.base import Expression
from qlib.data.ops import ElemOperator, PairOperator, Rolling


def _operand(value: object, instrument: str, start_index: int, end_index: int, *args: object):
    if isinstance(value, Expression):
        return value.load(instrument, start_index, end_index, *args)
    return value


class CnSma(ElemOperator):
    """Chinese-formula SMA: Y[t] = M/N * X[t] + (N-M)/N * Y[t-1]."""

    def __init__(self, feature: Expression, N: int, M: int):
        if int(N) <= 0 or int(M) <= 0 or int(M) > int(N):
            raise ValueError(f"CnSma expects 0 < M <= N, got N={N}, M={M}")
        self.N = int(N)
        self.M = int(M)
        super().__init__(feature)

    def __str__(self) -> str:
        return f"CnSma({self.feature},{self.N},{self.M})"

    def _load_internal(self, instrument, start_index, end_index, *args):
        series = self.feature.load(instrument, start_index, end_index, *args)
        return series.ewm(alpha=self.M / self.N, adjust=False, ignore_na=True, min_periods=1).mean()

    def get_longest_back_rolling(self):
        alpha = self.M / self.N
        effective = int(math.ceil(math.log(1e-6) / math.log(1 - alpha))) if alpha < 1 else 1
        return self.feature.get_longest_back_rolling() + effective - 1

    def get_extended_window_size(self):
        left, right = self.feature.get_extended_window_size()
        alpha = self.M / self.N
        effective = int(math.ceil(math.log(1e-6) / math.log(1 - alpha))) if alpha < 1 else 1
        return max(left + effective - 1, left), right


class DecayLinear(Rolling):
    """Linearly weighted rolling mean with the newest value carrying weight N."""

    def __init__(self, feature: Expression, N: int):
        super().__init__(feature, int(N), "decay_linear")

    def _load_internal(self, instrument, start_index, end_index, *args):
        series = self.feature.load(instrument, start_index, end_index, *args)

        def weighted(value: np.ndarray) -> float:
            weights = np.arange(1, len(value) + 1, dtype=float)
            valid = ~np.isnan(value)
            if not valid.any():
                return np.nan
            return float(np.dot(value[valid], weights[valid]) / weights[valid].sum())

        return series.rolling(self.N, min_periods=1).apply(weighted, raw=True)


class TsProduct(Rolling):
    def __init__(self, feature: Expression, N: int):
        super().__init__(feature, int(N), "product")

    def _load_internal(self, instrument, start_index, end_index, *args):
        series = self.feature.load(instrument, start_index, end_index, *args)
        return series.rolling(self.N, min_periods=1).apply(np.nanprod, raw=True)


class DaysSinceMax(Rolling):
    def __init__(self, feature: Expression, N: int):
        super().__init__(feature, int(N), "days_since_max")

    def _load_internal(self, instrument, start_index, end_index, *args):
        series = self.feature.load(instrument, start_index, end_index, *args)

        def age(value: np.ndarray) -> float:
            return np.nan if np.isnan(value).all() else float(len(value) - 1 - np.nanargmax(value))

        return series.rolling(self.N, min_periods=1).apply(age, raw=True)


class DaysSinceMin(Rolling):
    def __init__(self, feature: Expression, N: int):
        super().__init__(feature, int(N), "days_since_min")

    def _load_internal(self, instrument, start_index, end_index, *args):
        series = self.feature.load(instrument, start_index, end_index, *args)

        def age(value: np.ndarray) -> float:
            return np.nan if np.isnan(value).all() else float(len(value) - 1 - np.nanargmin(value))

        return series.rolling(self.N, min_periods=1).apply(age, raw=True)


class PairMax(PairOperator):
    def _load_internal(self, instrument, start_index, end_index, *args):
        left = _operand(self.feature_left, instrument, start_index, end_index, *args)
        right = _operand(self.feature_right, instrument, start_index, end_index, *args)
        return np.maximum(left, right)


class PairMin(PairOperator):
    def _load_internal(self, instrument, start_index, end_index, *args):
        left = _operand(self.feature_left, instrument, start_index, end_index, *args)
        right = _operand(self.feature_right, instrument, start_index, end_index, *args)
        return np.minimum(left, right)


class SignedPower(PairOperator):
    def _load_internal(self, instrument, start_index, end_index, *args):
        base = _operand(self.feature_left, instrument, start_index, end_index, *args)
        exponent = _operand(self.feature_right, instrument, start_index, end_index, *args)
        return np.sign(base) * np.power(np.abs(base), exponent)


CUSTOM_QLIB_OPS = [CnSma, DecayLinear, TsProduct, DaysSinceMax, DaysSinceMin, PairMax, PairMin, SignedPower]
