# -*- coding: utf-8 -*-
"""接线②：把 `/task/INSTRUCTION.md` 解析成一个 spec。

**唯一题面是 `/task/INSTRUCTION.md`**（`task.yaml` 不在容器里，见
`integrations/README.md` §1④）。

**两臂的题面是同一件事的两种说法，解析器必须两种都认。**
`ops/specs/fairness_protocol.md` 允许两臂的差异**恰好**是「题面的表达形式」与
「协议工件的有无」。strict 臂写成键值对，open 臂写成中文散文：

    strict:  as_of=2026-07-31                 open:  本次任务的 as_of 是 2026-07-31
    strict:  window=2026-01-05 到 2026-07-31   open:  计算窗口（window）是 …
    strict:  universe=csi300                   open:  标的范围（universe）是 csi300
    strict:  因子：worldquant_101.006           open:  因子编号 worldquant_101.006
    strict:  源方言原文：`(-1 * correlation(…))`  open:  原文是 `…`

所以每一条都写成「**锚点词 + 中间随便什么 + 值**」，而不是「锚点词 = 值」。
**这不是在读 `GENEBENCH_ARM`**：同一份代码对两种写法一视同仁，没有按臂分支 ——
按臂改行为是明令禁止的（`integrations/README.md` §0）。

**槽位取不到就抛，不猜默认值。** 猜出来的 `as_of` 会让越界变成合法请求，
而产物上完全看不出来。

> 写法与 `integrations/rdagent_q/glue/instruction.py` 同源（同一道题、同两臂），
> 但**各自一份** —— 两个接入是两个镜像，不共享 import；把它抽成公共模块会让
> 「改一处影响两个被测方」，那正是范式层不该做的事。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field


class InstructionError(RuntimeError):
    """题面里没有我们必须有的东西。**不给默认值**，直接退出。"""


@dataclass
class Spec:
    as_of: str
    window_start: str
    window_end: str
    universe: str
    factor_id: str
    expression: str
    declarations: dict = field(default_factory=dict)
    raw: str = ""


#: 「锚点词 + 至多 12 个非目标字符 + 值」。`/` 在锚点前后都被排除：题面里有一行
#: `可用端点：/bars /adj /calendar /limits /universe /tradability`，
#: 不排的话 `universe` 会命中那里、被解析成 **tradability** —— 而这种错**没有症状**：
#: 网关照样返回一个成分表，因子照样算得出来，只是标的池整个换了。
_NOT_PATH = r"(?<![/A-Za-z_])"
_GAP = r"[^0-9A-Za-z/\n]{0,12}"
_DATE = r"([0-9]{4}-[0-9]{2}-[0-9]{2})"


def _one(text: str, pattern: str, what: str) -> str:
    m = re.search(pattern, text)
    if not m:
        raise InstructionError(
            f"INSTRUCTION.md 里没有 {what}（正则 {pattern!r}）。"
            "**不猜默认值** —— 题面写法变了就改这里的正则，别填一个看起来合理的值。")
    return m.group(1).strip()


def _coerce(v: str):
    """把「接口值」的字面写法变成 JSON 值。

    题面里出现过四种形态：`[open, volume]`、`10`、`daily`、
    `{correlation: pearson_rolling_window}`。它们**不是 JSON**（没有引号），
    所以逐形态转，而不是 `json.loads` 撞运气。
    转不动的一律原样留成字符串 —— 猜一个结构比留字符串更坏。
    """
    v = v.strip()
    if re.fullmatch(r"-?\d+", v):
        return int(v)
    if re.fullmatch(r"-?\d+\.\d+", v):
        return float(v)
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        return [] if not inner else [x.strip().strip("'\"") for x in inner.split(",")]
    if v.startswith("{") and v.endswith("}"):
        inner = v[1:-1].strip()
        out = {}
        for part in inner.split(","):
            if ":" not in part:
                continue
            k, _, val = part.partition(":")
            out[k.strip().strip("'\"")] = val.strip().strip("'\"")
        return out or v
    return v


def parse(text: str) -> Spec:
    as_of = _one(text, _NOT_PATH + r"as_of" + _GAP + _DATE, "as_of")
    w = re.search(_NOT_PATH + r"window" + _GAP + _DATE + r"\s*(?:到|~|-|至)\s*" + _DATE, text)
    if not w:
        raise InstructionError("INSTRUCTION.md 里没有「window …<起> 到 <止>」。**不猜默认值**。")
    universe = _one(text, _NOT_PATH + r"universe" + _GAP + r"([A-Za-z0-9_.\-]{2,})", "universe")
    # 因子 id 至少三个字符且以字母开头 —— 否则「因子值按…」这种句子会被当成 id。
    factor_id = _one(text, r"因子(?:编号)?" + _GAP + r"([A-Za-z][A-Za-z0-9_.\-]{2,})", "因子 id")
    # strict 是 `源方言原文：\`…\``，open 是 `原文是 \`…\``；两边锚点词都含「原文」。
    expression = _one(text, r"原文[^`\n]{0,6}`([^`]+)`", "源方言原文（反引号里那一段）")

    decls: dict = {}
    for line in text.splitlines():
        if not re.match(r"^\s*[-*]\s", line):
            continue
        # 题面明说「取值用每条给出的接口值」，两臂都把它写在括号里的末尾。
        mv = re.search(r"接口值\s*(.+?)\s*[）)]\s*$", line)
        if not mv:
            m2 = re.match(r"^\s*[-*]\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([^（(\n]+?)\s*$", line)
            if m2:
                decls.setdefault(m2.group(1), _coerce(m2.group(2)))
            continue
        mk = (re.search(r"字段\s*([A-Za-z_][A-Za-z0-9_]*)", line)
              or re.match(r"^\s*[-*]\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", line))
        if mk:
            decls[mk.group(1)] = _coerce(mv.group(1))

    return Spec(as_of=as_of, window_start=w.group(1), window_end=w.group(2),
                universe=universe, factor_id=factor_id, expression=expression,
                declarations=decls, raw=text)


def summary(spec: Spec) -> str:
    return json.dumps({"as_of": spec.as_of, "window": [spec.window_start, spec.window_end],
                       "universe": spec.universe, "factor_id": spec.factor_id,
                       "expression": spec.expression, "declarations": spec.declarations},
                      ensure_ascii=False, indent=1)
