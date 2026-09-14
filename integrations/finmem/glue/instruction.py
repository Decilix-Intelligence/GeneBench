# -*- coding: utf-8 -*-
"""题面固定槽的读取。

写法与 `integrations/tradingagents/glue/run.py` 同源（同一批坑，不重新踩一遍）：

* **两臂的题面表达形式不同**（这是两臂唯一允许的差异之一），所以判据不能挂在标点上：
  strict 是 `as_of=2026-07-31`，open 是 `本次任务的 as_of 是 2026-07-31`。
* 键名前的 `(?<![/A-Za-z0-9_])` 不是装饰：题面里有一行
  `可用端点：/bars /adj /calendar /limits /universe /tradability`，
  没有这个否定后顾，`universe` 会先命中那一行、再越过 ` /` 取到 `tradability`
  —— 一个**长得像成功**的错值。
* 取不到就退出，**不猜默认值**：猜出来的 `as_of` 会让越界变成合法请求，
  而产物上完全看不出来。
"""
from __future__ import annotations

import re

_FILL = r"[^0-9A-Za-z]{0,10}"
_DATE = r"(?:\d{4}-\d{2}-\d{2}|\d{8})"

_DECL_LINE = re.compile(r"^\s*[-*]\s*(.+?)\s*$", re.M)
_DECL_KEY = re.compile(r"(?:字段\s*([a-z_]+)|^([a-z_]+)\s*=)")
_DECL_VAL = re.compile(r"接口值\s*([^）)]+)")


def slot(text: str, key: str, *, pattern: str = r"[A-Za-z0-9_.@:+-]+") -> str:
    m = re.search(rf"(?<![/A-Za-z0-9_]){re.escape(key)}(?![A-Za-z0-9_]){_FILL}({pattern})", text)
    if not m:
        raise SystemExit(f"INSTRUCTION.md 里没有槽位 {key!r}。**不猜默认值** —— "
                         f"请按题面的写法改 slot()。")
    return m.group(1)


def window(text: str) -> tuple[str, str]:
    """窗口两端。**两端都要** —— 开区间会被网关拒（`open_range_would_cross_asof`）。"""
    m = re.search(rf"(?<![/A-Za-z0-9_])window(?![A-Za-z0-9_]){_FILL}({_DATE}){_FILL}({_DATE})", text)
    if not m:
        raise SystemExit("INSTRUCTION.md 的 window 槽取不到两端 —— **不猜**；"
                         "开区间会被网关拒（open_range_would_cross_asof）。")
    return m.group(1), m.group(2)


def declarations(text: str, fields) -> dict:
    """从「本次任务的口径（逐项）」里逐条取。

    **题面没给的那一项标 `"unresolved"`** —— 缺失 ≠ 标记，两者判定不同。
    """
    got: dict[str, str] = {}
    for raw in _DECL_LINE.findall(text):
        km = _DECL_KEY.search(raw)
        if not km:
            continue
        key = km.group(1) or km.group(2)
        vm = _DECL_VAL.search(raw)
        if vm:
            val = vm.group(1).strip()
        elif km.group(2):
            val = raw.split("=", 1)[1].split("（")[0].split("(")[0].strip()
        else:
            continue
        got[key] = val
    out: dict = {}
    for f in fields:
        v = got.get(f)
        if v is None:
            out[f] = "unresolved"
        elif v.startswith("[") and v.endswith("]"):
            items = [x.strip() for x in v[1:-1].split(",") if x.strip()]
            out[f] = items or "unresolved"
        else:
            out[f] = v
    return out
