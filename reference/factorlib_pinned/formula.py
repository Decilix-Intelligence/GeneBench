from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from lark import Lark, Token, Transformer


_GRAMMAR = r"""
?start: expr
?expr: ternary
?ternary: or_expr [QMARK expr COLON expr] -> ternary
?or_expr: and_expr (OR_OP and_expr)* -> chain
?and_expr: equality (AND_OP equality)* -> chain
?equality: comparison (EQ_OP comparison)* -> chain
?comparison: sum (CMP_OP sum)* -> chain
?sum: product (ADD_OP product)* -> chain
?product: power (MUL_OP power)* -> chain
?power: unary (POW_OP power)? -> power
?unary: UNARY_OP unary -> unary
      | atom
?atom: NUMBER -> number
     | NAME "(" [args] ")" -> call
     | NAME ("." NAME)+ -> dotted
     | NAME -> name
     | "(" expr ")"
?args: expr ("," expr)*

QMARK: "?"
COLON: ":"
OR_OP.2: "||" | /OR/i
AND_OP: "&&" | "&"
EQ_OP: "==" | "=" | "!=" | "<>"
CMP_OP: "<=" | ">=" | "<" | ">"
ADD_OP: "+" | "-"
MUL_OP: "*" | "/"
POW_OP: "^"
UNARY_OP: "+" | "-" | "!"
NAME: /[A-Za-z_][A-Za-z0-9_]*/
NUMBER: /(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?/

%import common.WS
%ignore WS
"""


@dataclass(frozen=True)
class FormulaNode:
    kind: str
    value: str | float | None = None
    children: tuple["FormulaNode", ...] = ()


class _ToFormulaNode(Transformer):
    def number(self, values: list[Token]) -> FormulaNode:
        return FormulaNode("number", float(values[0]))

    def name(self, values: list[Token]) -> FormulaNode:
        return FormulaNode("name", str(values[0]).upper())

    def dotted(self, values: list[Token]) -> FormulaNode:
        return FormulaNode("name", ".".join(str(value).upper() for value in values))

    def args(self, values: list[FormulaNode]) -> tuple[FormulaNode, ...]:
        return tuple(values)

    def call(self, values: list[object]) -> FormulaNode:
        name = str(values[0]).upper()
        args: tuple[FormulaNode, ...] = ()
        if len(values) == 2:
            value = values[1]
            args = value if isinstance(value, tuple) else (value,)  # type: ignore[assignment]
        return FormulaNode("call", name, args)

    def unary(self, values: list[object]) -> FormulaNode:
        return FormulaNode("unary", str(values[0]), (values[1],))  # type: ignore[arg-type]

    def power(self, values: list[object]) -> FormulaNode:
        if len(values) == 1:
            return values[0]  # type: ignore[return-value]
        return FormulaNode("binary", str(values[1]), (values[0], values[2]))  # type: ignore[arg-type]

    def chain(self, values: list[object]) -> FormulaNode:
        node: FormulaNode = values[0]  # type: ignore[assignment]
        for index in range(1, len(values), 2):
            node = FormulaNode("binary", str(values[index]).upper(), (node, values[index + 1]))  # type: ignore[arg-type]
        return node

    def ternary(self, values: list[object]) -> FormulaNode:
        if len(values) == 1:
            return values[0]  # type: ignore[return-value]
        return FormulaNode("ternary", None, (values[0], values[2], values[4]))  # type: ignore[arg-type]


_PARSER = Lark(_GRAMMAR, parser="lalr", transformer=_ToFormulaNode(), maybe_placeholders=False)


_NORMALIZATIONS = (
    (".*", "*"),
    ("./", "/"),
    ("–", "-"),
    ("SM A", "SMA"),
    ("CLOS E", "CLOSE"),
    ("C LOSE", "CLOSE"),
    ("OP EN", "OPEN"),
    ("D ELAY", "DELAY"),
    ("D E LAY", "DELAY"),
    ("HGIH", "HIGH"),
    ("DELAT", "DELTA"),
    ("COVIANCE", "COVARIANCE"),
    ("SMEAN", "SMA"),
)


def normalize_formula(expression: str) -> str:
    value = expression.strip().rstrip(";")
    for old, new in _NORMALIZATIONS:
        value = value.replace(old, new)
    value = re.sub(r"\bVOL\b", "VOLUME", value, flags=re.IGNORECASE)
    value = re.sub(r"\)\s*\(", ")*(", value)
    return value


def parse_formula(expression: str) -> FormulaNode:
    parsed = _PARSER.parse(normalize_formula(expression))
    if not isinstance(parsed, FormulaNode):
        raise TypeError(f"unexpected formula parse result: {type(parsed)!r}")
    return parsed


def walk(node: FormulaNode) -> Iterable[FormulaNode]:
    yield node
    for child in node.children:
        yield from walk(child)


def formula_calls(node: FormulaNode) -> set[str]:
    return {str(value.value) for value in walk(node) if value.kind == "call"}


def formula_names(node: FormulaNode) -> set[str]:
    return {str(value.value) for value in walk(node) if value.kind == "name"}


_FIELDS = {
    "OPEN": "$open",
    "HIGH": "$high",
    "LOW": "$low",
    "CLOSE": "$close",
    "VOLUME": "$volume",
    "AMOUNT": "$amount",
    "VWAP": "$vwap",
    "RET": "($close/Ref($close,1)-1)",
    "RETURNS": "($close/Ref($close,1)-1)",
}


_CROSS_SECTIONAL_CALLS = {"RANK", "SCALE", "XMAX", "XMIN"}


class QlibExpressionError(ValueError):
    pass


def _integer(node: FormulaNode) -> int:
    if node.kind != "number":
        raise QlibExpressionError("window must be numeric")
    value = float(node.value)
    rounded = int(round(value))
    if abs(value - rounded) > 1e-9 or rounded <= 0:
        raise QlibExpressionError(f"window must be a positive integer, got {value}")
    return rounded


def _number_text(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return repr(float(value))


def compile_qlib_expression(node: FormulaNode) -> tuple[str, tuple[str, ...]]:
    """Compile a per-instrument formula to Qlib's expression language.

    Cross-sectional operations deliberately fail here and are routed to the
    panel loader.  The returned custom-op names must be registered with
    ``qlib.init(custom_ops=...)``.
    """

    custom_ops: set[str] = set()

    def constant(value: FormulaNode) -> float | None:
        if value.kind == "number":
            return float(value.value)
        if value.kind == "unary":
            inner = constant(value.children[0])
            if inner is None:
                return None
            if value.value == "+":
                return inner
            if value.value == "-":
                return -inner
            return None
        if value.kind == "binary":
            left, right = (constant(child) for child in value.children)
            if left is None or right is None:
                return None
            if value.value == "+":
                return left + right
            if value.value == "-":
                return left - right
            if value.value == "*":
                return left * right
            if value.value == "/":
                return left / right
            if value.value == "^":
                return left**right
        return None

    def emit(value: FormulaNode) -> str:
        folded = constant(value)
        if folded is not None:
            return _number_text(folded)
        if value.kind == "number":
            return _number_text(float(value.value))
        if value.kind == "name":
            name = str(value.value)
            if name not in _FIELDS:
                raise QlibExpressionError(f"unsupported identifier: {name}")
            return _FIELDS[name]
        if value.kind == "unary":
            op = str(value.value)
            inner = emit(value.children[0])
            if op == "!":
                return f"Not({inner})"
            return inner if op == "+" else f"(0-{inner})"
        if value.kind == "binary":
            left = emit(value.children[0])
            right = emit(value.children[1])
            op = str(value.value).upper()
            mapped = {"=": "==", "<>": "!=", "AND": "&", "&&": "&", "OR": "|", "||": "|"}.get(op, op)
            if mapped == "^":
                return f"Power({left},{right})"
            return f"({left}{mapped}{right})"
        if value.kind == "ternary":
            condition, if_true, if_false = (emit(child) for child in value.children)
            return f"If({condition},{if_true},{if_false})"
        if value.kind != "call":
            raise QlibExpressionError(f"unsupported node: {value.kind}")

        name = str(value.value).upper()
        args = value.children
        if name in _CROSS_SECTIONAL_CALLS:
            raise QlibExpressionError(f"cross-sectional operation requires panel loader: {name}")
        if name in {"ABS", "SIGN", "LOG"} and len(args) == 1:
            return f"{name.title()}({emit(args[0])})"
        if name in {"DELAY", "REF"} and len(args) in {1, 2}:
            window = 1 if len(args) == 1 else _integer(args[1])
            return f"Ref({emit(args[0])},{window})"
        if name == "DELTA" and len(args) == 2:
            return f"Delta({emit(args[0])},{_integer(args[1])})"
        rolling = {
            "SUM": "Sum",
            "MEAN": "Mean",
            "MA": "Mean",
            "STD": "Std",
            "STDDEV": "Std",
            "TSMIN": "Min",
            "TS_MIN": "Min",
            "TSMAX": "Max",
            "TS_MAX": "Max",
            "TSRANK": "Rank",
            "TS_RANK": "Rank",
            "TS_ARGMAX": "IdxMax",
            "TS_ARGMIN": "IdxMin",
        }
        if name in rolling and len(args) == 2:
            return f"{rolling[name]}({emit(args[0])},{_integer(args[1])})"
        if name in {"CORR", "CORRELATION"} and len(args) == 3:
            return f"Corr({emit(args[0])},{emit(args[1])},{_integer(args[2])})"
        if name == "COVARIANCE" and len(args) == 3:
            return f"Cov({emit(args[0])},{emit(args[1])},{_integer(args[2])})"
        if name in {"SMA"} and len(args) == 3:
            custom_ops.add("CnSma")
            return f"CnSma({emit(args[0])},{_integer(args[1])},{_integer(args[2])})"
        if name in {"DECAYLINEAR", "DECAY_LINEAR", "WMA"} and len(args) == 2:
            custom_ops.add("DecayLinear")
            return f"DecayLinear({emit(args[0])},{_integer(args[1])})"
        if name in {"PRODUCT", "PROD"} and len(args) == 2:
            custom_ops.add("TsProduct")
            return f"TsProduct({emit(args[0])},{_integer(args[1])})"
        if name in {"LOWDAY", "HIGHDAY"} and len(args) == 2:
            op = "DaysSinceMin" if name == "LOWDAY" else "DaysSinceMax"
            custom_ops.add(op)
            return f"{op}({emit(args[0])},{_integer(args[1])})"
        if name == "COUNT" and len(args) == 2:
            return f"Sum(If({emit(args[0])},1,0),{_integer(args[1])})"
        if name == "SUMIF" and len(args) == 3:
            return f"Sum(If({emit(args[2])},{emit(args[0])},0),{_integer(args[1])})"
        if name == "SLOPE" and len(args) == 2:
            return f"Slope({emit(args[0])},{_integer(args[1])})"
        if name in {"MAX", "MIN"} and len(args) == 2:
            if (
                args[0].kind != "number"
                and args[1].kind == "number"
                and float(args[1].value) > 0
            ):
                op = "Max" if name == "MAX" else "Min"
                return f"{op}({emit(args[0])},{_integer(args[1])})"
            op = "PairMax" if name == "MAX" else "PairMin"
            custom_ops.add(op)
            return f"{op}({emit(args[0])},{emit(args[1])})"
        if name == "SIGNEDPOWER" and len(args) == 2:
            custom_ops.add("SignedPower")
            return f"SignedPower({emit(args[0])},{emit(args[1])})"
        if name == "CUMPOS" and len(args) == 1:
            raise QlibExpressionError("CUMPOS requires full-history panel execution")
        raise QlibExpressionError(f"unsupported function or arity: {name}/{len(args)}")

    return emit(node), tuple(sorted(custom_ops))
