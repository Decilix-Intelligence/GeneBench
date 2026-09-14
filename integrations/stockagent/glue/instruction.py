# -*- coding: utf-8 -*-
"""题面解析 —— 两臂的**表达形式不同**，同一个解析器必须都认。

strict 臂写键值（`as_of=2026-07-31`），open 臂写散文（`本次任务的 as_of 是 2026-07-31`）。
`GENEBENCH_ARM` **不读**（读了就是按臂改行为，那是干预本身）：解析器对两种写法一视同仁。

三处防偷（每一处都有一条具名判据盯着）：

* `universe` 不许被题面里那行 `可用端点：… /universe /tradability` 偷走 ——
  锚点前排除 `/`，后面不许直接跟路径分隔符。偷走之后**产物上完全看不出来**：
  网关照样返回一个成分表、信号照样算得出来，只是标的池整个换了。
* `as_of` 不许被 `universe_ref=csi300@2026-07-31` 里那个日期偷走 —— 锚点后不许跟 `_`/字母。
* 口径行（`- ` 开头那几行）不参与 as_of / window / universe 的取值。
"""
from __future__ import annotations

import re
from typing import Any

_DATE = r"(\d{4}-\d{2}-\d{2})"
#: 锚点与值之间允许的填充：至多 12 个既不是路径分隔符也不是数字的字符。
#: 「至多 12 个」是为了不让锚点跨过一整句话去够上一个不相干的值。
_GAP = r"[^0-9/\n]{0,12}"


class InstructionError(RuntimeError):
    """题面里没有这个槽。**不猜默认值** —— 猜出来的 as_of 会让越界变成合法请求。"""


def _body_lines(text: str) -> str:
    """去掉口径行（`- ` 开头）。它们里面有 `universe_ref=csi300@2026-07-31`，
    会把 as_of 与 universe 两个槽都带偏。"""
    return "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("- "))


def as_of(text: str) -> str:
    body = _body_lines(text)
    m = re.search(r"as_of(?![_A-Za-z])" + _GAP + _DATE, body)
    if not m:
        raise InstructionError("题面里没有 as_of。")
    return m.group(1)


def window(text: str) -> tuple[str, str]:
    body = _body_lines(text)
    m = re.search(r"window(?![_A-Za-z])[^0-9\n]{0,12}" + _DATE
                  + r"\s*(?:到|至|~|-{1,2}|—)\s*" + _DATE, body)
    if not m:
        raise InstructionError("题面里没有 window。")
    return m.group(1), m.group(2)


def universe(text: str) -> str:
    body = _body_lines(text)
    # 锚点前不许是 `/` 或 `_`（挡住 `/universe` 与 `..._universe`），
    # 锚点后不许直接跟字母或 `_`（挡住 `universe_ref`），
    # 中间只放括号/引号/空白，然后必须有一个真正的赋值记号（`=` `:` `：` `是`）。
    m = re.search(r"(?<![/_A-Za-z])universe(?![_A-Za-z])[)）`*_\s]{0,4}[:：=是]+\s*([A-Za-z0-9_]+)", body)
    if not m:
        raise InstructionError("题面里没有 universe。")
    return m.group(1)


def declarations(text: str, fields: "list[str] | tuple[str, ...]") -> dict[str, Any]:
    """口径逐项照抄。

    两臂各自的写法：

        strict: `- value_semantics=score（信号值是可比的分数，不是秩，接口值 score）`
        open:   `- 信号值是可比的分数，不是秩（字段 value_semantics，接口值 score）`

    共同点是每行末尾都有「接口值 <V>）」——**取的就是那一段**，不是括号外面那段散文。
    `fields` 由 `/task/S5.json` 的 `properties.declarations.required` 给出（不是我们列的表）。
    题面没给的字段留给调用方标 `unresolved`（本函数不替它填）。
    """
    got: dict[str, Any] = {}
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("- "):
            continue
        mv = re.search(r"接口值\s*(.+?)\s*[）)]\s*$", s)
        if not mv:
            continue
        value = mv.group(1)
        mk = re.match(r"-\s*([a-z_]+)\s*=", s) or re.search(r"字段\s*([a-z_]+)\s*[，,]", s)
        if not mk:
            continue
        key = mk.group(1)
        if key not in fields:
            continue
        got[key] = _coerce(value)
    return got


def _coerce(value: str) -> Any:
    """`[a, b, c]` → list[str]；其余原样是字符串。**不做别的转换** ——
    接口值是题面逐字给的，改写它就是我们替它答题。"""
    v = value.strip()
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        return [p.strip() for p in inner.split(",") if p.strip()] if inner else []
    return v
