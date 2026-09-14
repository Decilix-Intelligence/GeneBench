from __future__ import annotations

import json
import math
import os
import re
import warnings
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from qlib.data import D
from qlib.data.dataset.loader import DataLoader

from .formula import FormulaNode, parse_formula


RAW_FIELDS = {
    "OPEN": "$open",
    "HIGH": "$high",
    "LOW": "$low",
    "CLOSE": "$close",
    "VOLUME": "$volume",
    "AMOUNT": "$amount",
    "VWAP": "$vwap",
}


def _window(value: Any) -> int:
    if isinstance(value, pd.DataFrame):
        raise ValueError("rolling window cannot be a panel")
    number = int(round(float(value)))
    if number <= 0:
        raise ValueError(f"rolling window must be positive, got {value}")
    return number


def _as_frame(value: Any, template: pd.DataFrame) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        return value
    return pd.DataFrame(value, index=template.index, columns=template.columns, dtype=float)


def _pair(left: Any, right: Any, template: pd.DataFrame, function) -> pd.DataFrame:
    return pd.DataFrame(
        function(_as_frame(left, template).to_numpy(), _as_frame(right, template).to_numpy()),
        index=template.index,
        columns=template.columns,
    )


def _rolling_weighted(frame: pd.DataFrame, window: int) -> pd.DataFrame:
    denominator = window * (window + 1) / 2
    result = sum((index + 1) * frame.shift(window - 1 - index) for index in range(window)) / denominator
    valid = sum(frame.shift(window - 1 - index).notna().astype(int) for index in range(window))
    return result.where(valid == window)


def _rolling_age(frame: pd.DataFrame, window: int, find_max: bool) -> pd.DataFrame:
    def age(values: np.ndarray) -> float:
        if np.isnan(values).any():
            return np.nan
        position = np.argmax(values) if find_max else np.argmin(values)
        return float(len(values) - 1 - position)

    return frame.rolling(window, min_periods=window).apply(age, raw=True)


def _rolling_slope(frame: pd.DataFrame, window: int) -> pd.DataFrame:
    x = np.arange(1, window + 1, dtype=float)
    x -= x.mean()
    denominator = float(np.dot(x, x))

    def slope(values: np.ndarray) -> float:
        if np.isnan(values).any():
            return np.nan
        return float(np.dot(values - values.mean(), x) / denominator)

    return frame.rolling(window, min_periods=window).apply(slope, raw=True)


class PanelFormulaEvaluator:
    """Evaluate a formula on date-by-instrument panels without changing semantics."""

    def __init__(self, fields: dict[str, pd.DataFrame]):
        missing = set(RAW_FIELDS) - set(fields)
        if missing:
            raise ValueError(f"panel evaluator is missing fields: {sorted(missing)}")
        self.fields = fields
        self.template = fields["CLOSE"]

    def evaluate(self, node: FormulaNode) -> Any:
        if node.kind == "number":
            return float(node.value)
        if node.kind == "name":
            name = str(node.value)
            if name in self.fields:
                return self.fields[name]
            if name in {"RET", "RETURNS"}:
                return self.fields["CLOSE"] / self.fields["CLOSE"].shift(1) - 1
            raise ValueError(f"unsupported panel identifier: {name}")
        if node.kind == "unary":
            value = self.evaluate(node.children[0])
            if node.value == "-":
                return -value
            if node.value == "+":
                return value
            if node.value == "!":
                return ~value.astype(bool)
            raise ValueError(f"unsupported unary operator: {node.value}")
        if node.kind == "binary":
            left = self.evaluate(node.children[0])
            right = self.evaluate(node.children[1])
            op = str(node.value).upper()
            if op == "+":
                return left + right
            if op == "-":
                return left - right
            if op == "*":
                return left * right
            if op == "/":
                return left / right
            if op == "^":
                return np.power(left, right)
            if op in {"=", "=="}:
                return left == right
            if op in {"!=", "<>"}:
                return left != right
            if op == "<":
                return left < right
            if op == "<=":
                return left <= right
            if op == ">":
                return left > right
            if op == ">=":
                return left >= right
            if op in {"&", "&&", "AND"}:
                return _as_frame(left, self.template).astype(bool) & _as_frame(right, self.template).astype(bool)
            if op in {"|", "||", "OR"}:
                return _as_frame(left, self.template).astype(bool) | _as_frame(right, self.template).astype(bool)
            raise ValueError(f"unsupported binary operator: {op}")
        if node.kind == "ternary":
            condition = _as_frame(self.evaluate(node.children[0]), self.template).astype(bool)
            if_true = _as_frame(self.evaluate(node.children[1]), self.template)
            if_false = _as_frame(self.evaluate(node.children[2]), self.template)
            return if_true.where(condition, if_false)
        if node.kind != "call":
            raise ValueError(f"unsupported formula node: {node.kind}")

        name = str(node.value).upper()
        values = [self.evaluate(value) for value in node.children]
        if name == "ABS":
            return np.abs(values[0])
        if name == "SIGN":
            return np.sign(values[0])
        if name == "LOG":
            return np.log(values[0])
        if name in {"DELAY", "REF"}:
            return _as_frame(values[0], self.template).shift(1 if len(values) == 1 else _window(values[1]))
        if name == "DELTA":
            frame, window = _as_frame(values[0], self.template), _window(values[1])
            return frame - frame.shift(window)
        if name in {"SUM", "MEAN", "MA", "STD", "STDDEV", "TSMIN", "TS_MIN", "TSMAX", "TS_MAX", "PRODUCT", "PROD"}:
            frame, window = _as_frame(values[0], self.template), _window(values[1])
            rolling = frame.rolling(window, min_periods=window)
            if name == "SUM":
                return rolling.sum()
            if name in {"MEAN", "MA"}:
                return rolling.mean()
            if name in {"STD", "STDDEV"}:
                return rolling.std()
            if name in {"TSMIN", "TS_MIN"}:
                return rolling.min()
            if name in {"TSMAX", "TS_MAX"}:
                return rolling.max()
            return rolling.apply(np.prod, raw=True)
        if name in {"TSRANK", "TS_RANK"}:
            frame, window = _as_frame(values[0], self.template), _window(values[1])
            return frame.rolling(window, min_periods=window).rank(pct=True)
        if name in {"TS_ARGMAX", "TS_ARGMIN"}:
            frame, window = _as_frame(values[0], self.template), _window(values[1])
            find_max = name == "TS_ARGMAX"
            return frame.rolling(window, min_periods=window).apply(
                lambda item: float((np.argmax(item) if find_max else np.argmin(item)) + 1), raw=True
            )
        if name in {"CORR", "CORRELATION", "COVARIANCE"}:
            left = _as_frame(values[0], self.template)
            right = _as_frame(values[1], self.template)
            rolling = left.rolling(_window(values[2]), min_periods=_window(values[2]))
            return rolling.corr(right) if name != "COVARIANCE" else rolling.cov(right)
        if name == "RANK":
            return _as_frame(values[0], self.template).rank(axis=1, pct=True, method="average")
        if name == "SCALE":
            frame = _as_frame(values[0], self.template)
            return frame.div(frame.abs().sum(axis=1).replace(0, np.nan), axis=0)
        if name in {"DECAYLINEAR", "DECAY_LINEAR", "WMA"}:
            return _rolling_weighted(_as_frame(values[0], self.template), _window(values[1]))
        if name == "SMA":
            frame, n, m = _as_frame(values[0], self.template), _window(values[1]), _window(values[2])
            if m > n:
                raise ValueError(f"SMA requires M <= N, got {m} > {n}")
            return frame.ewm(alpha=m / n, adjust=False, ignore_na=True, min_periods=1).mean()
        if name in {"MAX", "MIN"}:
            first, second = values
            if isinstance(first, pd.DataFrame) and not isinstance(second, pd.DataFrame) and float(second) > 0:
                rolling = first.rolling(_window(second), min_periods=_window(second))
                return rolling.max() if name == "MAX" else rolling.min()
            function = np.maximum if name == "MAX" else np.minimum
            return _pair(first, second, self.template, function)
        if name == "COUNT":
            condition = _as_frame(values[0], self.template).astype(bool)
            window = _window(values[1])
            return condition.astype(float).rolling(window, min_periods=window).sum()
        if name == "SUMIF":
            frame = _as_frame(values[0], self.template)
            window = _window(values[1])
            condition = _as_frame(values[2], self.template).astype(bool)
            return frame.where(condition, 0.0).rolling(window, min_periods=window).sum()
        if name in {"LOWDAY", "HIGHDAY"}:
            return _rolling_age(_as_frame(values[0], self.template), _window(values[1]), name == "HIGHDAY")
        if name == "SLOPE":
            return _rolling_slope(_as_frame(values[0], self.template), _window(values[1]))
        if name == "SIGNEDPOWER":
            base = _as_frame(values[0], self.template)
            exponent = _as_frame(values[1], self.template)
            return np.sign(base) * np.power(np.abs(base), exponent)
        if name == "XMAX":
            frame = _as_frame(values[0], self.template)
            return pd.DataFrame(
                np.repeat(frame.max(axis=1).to_numpy()[:, None], frame.shape[1], axis=1),
                index=frame.index,
                columns=frame.columns,
            )
        if name == "XMIN":
            frame = _as_frame(values[0], self.template)
            return pd.DataFrame(
                np.repeat(frame.min(axis=1).to_numpy()[:, None], frame.shape[1], axis=1),
                index=frame.index,
                columns=frame.columns,
            )
        if name == "CUMPOS":
            frame = _as_frame(values[0], self.template)
            positive = frame.where(frame > 1, 1.0).fillna(1.0)
            return positive.cumprod()
        raise ValueError(f"unsupported panel function: {name}/{len(values)}")


def _read_catalog(root: Path, family: str) -> list[dict[str, Any]]:
    path = root / "catalog" / f"{family}.jsonl"
    if not path.is_file():
        raise FileNotFoundError(f"factor catalog is missing: {path}; run factor-sync first")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _load_start(start_time: Any, warmup: int) -> Any:
    if start_time is None:
        return None
    calendar = D.calendar(end_time=start_time, freq="day")
    if not len(calendar):
        return start_time
    return calendar[max(0, len(calendar) - warmup - 1)]


def _raw_panels(instruments: Any, start_time: Any, end_time: Any, warmup: int) -> dict[str, pd.DataFrame]:
    raw = D.features(
        instruments,
        list(RAW_FIELDS.values()),
        start_time=_load_start(start_time, warmup),
        end_time=end_time,
        freq="day",
    )
    raw.columns = list(RAW_FIELDS)
    if raw.index.names == ["instrument", "datetime"]:
        raw = raw.swaplevel().sort_index()
    if raw.index.names != ["datetime", "instrument"]:
        raw.index = raw.index.set_names(["datetime", "instrument"])
    panels: dict[str, pd.DataFrame] = {}
    for name in RAW_FIELDS:
        panels[name] = raw[name].unstack("instrument").sort_index()
    return panels


@lru_cache(maxsize=1)
def _kunquant_alpha101_module():
    try:
        from KunQuant.Driver import KunCompilerConfig
        from KunQuant.Op import Builder, Input, Output
        from KunQuant.Stage import Function
        from KunQuant.jit import cfake
        from KunQuant.predefined import Alpha101
    except ImportError as exc:
        raise RuntimeError("KunQuant==0.1.11 is required for WorldQuant 101") from exc

    builder = Builder()
    with builder:
        data = Alpha101.AllData(
            open=Input("open"),
            high=Input("high"),
            low=Input("low"),
            close=Input("close"),
            volume=Input("volume"),
            amount=Input("amount"),
            vwap=Input("vwap"),
        )
        for function in Alpha101.all_alpha:
            Output(function(data), function.__name__)
    function = Function(builder.ops)
    library = cfake.compileit(
        [("alpha101", function, KunCompilerConfig(input_layout="TS", output_layout="TS", split_source=12))],
        "finance01_alpha101_0_1_11",
        cfake.CppCompilerConfig(),
    )
    return library.getModule("alpha101")


def _worldquant_panels(fields: dict[str, pd.DataFrame], names: set[str]) -> dict[str, pd.DataFrame]:
    from KunQuant.runner import KunRunner as kr

    module = _kunquant_alpha101_module()
    inputs = {
        source.lower(): np.ascontiguousarray(fields[source].to_numpy(dtype=np.float32))
        for source in RAW_FIELDS
    }
    executor = kr.createMultiThreadExecutor(max(1, min(8, os.cpu_count() or 1)))
    output = kr.runGraph(executor, module, inputs, 0, len(fields["CLOSE"]))
    results: dict[str, pd.DataFrame] = {}
    for alpha_name, values in output.items():
        number = int(alpha_name[-3:])
        catalog_name = f"WQAlpha{number}"
        if catalog_name not in names:
            continue
        array = values - 0.5 if number == 1 else values
        results[catalog_name] = pd.DataFrame(
            array, index=fields["CLOSE"].index, columns=fields["CLOSE"].columns
        ).where(fields["CLOSE"].notna())
    return results


def _full_history_cumpos(instruments: Any, end_time: Any) -> pd.DataFrame:
    raw = D.features(instruments, ["$close"], start_time=None, end_time=end_time, freq="day")
    raw.columns = ["close"]
    if raw.index.names == ["instrument", "datetime"]:
        raw = raw.swaplevel().sort_index()
    close = raw["close"].unstack("instrument").sort_index()
    ratio = close / close.shift(1)
    return ratio.where(ratio > 1, 1.0).fillna(1.0).cumprod().where(close.notna())


def _stack_panel(frame: pd.DataFrame, name: str) -> pd.Series:
    series = frame.stack(future_stack=True)
    series.name = name
    series.index = series.index.set_names(["datetime", "instrument"])
    return series


class FactorLibraryDataLoader(DataLoader):
    """Qlib DataLoader for converted factor families.

    ``worldquant_101`` uses the pinned KunQuant implementation for the 82
    factors without industry inputs. ``gtja_191`` combines native Qlib
    expressions with a vectorized panel evaluator for true cross-sectional
    operations.
    """

    def __init__(self, family: str, catalog_root: str, warmup: int = 600):
        if family not in {"worldquant_101", "gtja_191"}:
            raise ValueError(f"unsupported converted family: {family}")
        self.family = family
        self.catalog_root = Path(catalog_root).expanduser()
        self.warmup = int(warmup)

    def load(self, instruments=None, start_time=None, end_time=None) -> pd.DataFrame:
        warnings.filterwarnings("ignore", message="divide by zero encountered in log", category=RuntimeWarning)
        process_filter = "ignore:divide by zero encountered in log:RuntimeWarning"
        current_filter = os.environ.get("PYTHONWARNINGS", "")
        if process_filter not in current_filter:
            os.environ["PYTHONWARNINGS"] = ",".join(value for value in (current_filter, process_filter) if value)
        instruments = "all" if instruments is None else instruments
        if isinstance(instruments, str):
            if re.fullmatch(r"(?:SH|SZ|BJ)\d{6}", instruments, flags=re.IGNORECASE):
                instruments = [instruments.upper()]
            else:
                instruments = D.instruments(instruments)
        rows = [row for row in _read_catalog(self.catalog_root, self.family) if row.get("executable")]
        if not rows:
            raise RuntimeError(f"no executable records in {self.family}")
        fields = _raw_panels(instruments, start_time, end_time, self.warmup)
        outputs: dict[str, pd.DataFrame] = {}
        if self.family == "worldquant_101":
            outputs.update(_worldquant_panels(fields, {str(row["name"]) for row in rows}))
        else:
            native = [row for row in rows if row.get("execution_backend") == "qlib_expression"]
            if native:
                frame = D.features(
                    instruments,
                    [str(row["compiled_expression"]) for row in native],
                    start_time=_load_start(start_time, self.warmup),
                    end_time=end_time,
                    freq="day",
                )
                frame.columns = [str(row["name"]) for row in native]
                if frame.index.names == ["instrument", "datetime"]:
                    frame = frame.swaplevel().sort_index()
                for row in native:
                    outputs[str(row["name"])] = frame[str(row["name"])].unstack("instrument")
            evaluator = PanelFormulaEvaluator(fields)
            for row in rows:
                if row.get("execution_backend") != "qlib_panel_loader":
                    continue
                if row.get("id") == "gtja_191.143":
                    value = _full_history_cumpos(instruments, end_time).reindex(
                        index=fields["CLOSE"].index,
                        columns=fields["CLOSE"].columns,
                    )
                else:
                    try:
                        value = evaluator.evaluate(parse_formula(str(row["compiled_expression"])))
                    except Exception as exc:
                        raise RuntimeError(f"failed to evaluate converted factor {row['id']}: {exc}") from exc
                outputs[str(row["name"])] = _as_frame(value, fields["CLOSE"]).where(fields["CLOSE"].notna())

        missing = sorted({str(row["name"]) for row in rows} - set(outputs))
        if missing:
            raise RuntimeError(f"converted backend did not produce factors: {missing}")
        stacked: list[pd.Series] = []
        for row in rows:
            frame = outputs[str(row["name"])]
            if start_time is not None:
                frame = frame.loc[pd.Timestamp(start_time) :]
            if end_time is not None:
                frame = frame.loc[: pd.Timestamp(end_time)]
            stacked.append(_stack_panel(frame, str(row["name"])))
        result = pd.concat(stacked, axis=1)
        return result.dropna(how="all").sort_index()
