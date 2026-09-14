# -*- coding: utf-8 -*-
"""接线④：让 AlphaAgent 自己的 agent 循环在这道题上跑起来。

**用的是系统的哪些件（一件都没改）**

  * `alphaagent.factor.mining.loop.run_trajectory` —— 它的多轮工具调用主循环
    （原生 OpenAI `tool_calls` + 并行分发 + JSONL 轨迹 + 停不下来时的 nudge）。
  * `alphaagent.dsl.catalog.operator_catalog_markdown()` —— 它的算子清单，
    从 `alphaagent.dsl.registry` 现算（不是抄一份表，抄的那份必然漂）。
  * `alphaagent.dsl.eval.eval_factor` / `compile_multi_line_factor` —— 它的
    DSL 解析器与算子库，因子值就是它算出来的。
  * `alphaagent.dsl.core.errors.MultiLineFactorEvalError` —— 它的结构化报错
    （阶段 / 生成码行号 / 用户源码行），原样回给模型，这正是它自己迭代的方式。

**替换了哪两处，以及为什么**

  1. `alphaagent.factor.mining.tools.FactorEvalTools` → 本模块的 `ImplementTools`。
     `run_trajectory` 只依赖三个方法（`schemas` / `dispatch` / `result_to_content`），
     所以这是**同形替换**，不是改它的代码。
     **为什么必须换**：`FactorEvalTools` 的两个工具（`eval_on_train_set` /
     `eval_on_val_set`）要一个**前瞻 label 列**才能算 IC，而 label 由未来的
     收盘价造 —— 本题的 `required_fields` 是题面给的那几列，为了造 label 去多取
     一列 `close` 就是越权读取（S3 的声明读取集探针从 access_log 反推）。
     所以工具换成「在题面窗口的面板上求这一个因子并如实清点」。

  2. `alphaagent.factor.mining.prompts.build_system_prompt` → 本模块的
     `build_prompt`。**为什么必须换**：那份 prompt 的正文是挖掘目标
     （`abs(ic) ≥ 0.005`、`icir`、`monthly_corr_robustness`、`submit_factor` 入库
     判据……），全部建立在有 label 的前提上；照搬会让模型去追一组这道题里
     根本不存在的指标，白烧调用预算。本模块的 prompt 只保留它**真正的那一半**：
     算子清单（现算）+ DSL 写法约定，另一半换成题面自己的话。
     被换掉的那半在 README §3「已知限制」里写明了。

**没有用到的那部分系统**（写在这里免得被误读成「跑过了」）：FactorZoo 入库与
AST 相似度去重（`factor/zoo/similarity.py`）、IC/ICIR/MLS-FMB 评估
（`factor/metrics.py`）、`submit_factor` 的查重与增量 memmap 因子库 ——
它们都要 label 与一个持久因子库，这道题两样都没有。
"""
from __future__ import annotations

import json
import pathlib
from typing import Any

#: 声明给模型的兜底选取规则。**在跑之前就写进 system prompt**，不是事后挑一个 ——
#: 「取最后一次成功求值的」是确定性的先后顺序，不是按好坏排名（best-of-N 是被禁的）。
FALLBACK_RULE = "最后一次成功求值的表达式"

_EVAL_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "multi_line_expr": {
            "type": "string",
            "description": "多行因子 DSL：可含赋值行，最后一行为因子值；列用 $列名 引用，算子大写。",
        },
        "factor_name": {"type": "string", "description": "这次尝试的名字，便于你自己对照。"},
    },
    "required": ["multi_line_expr"],
    "additionalProperties": False,
}

_SUBMIT_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        **_EVAL_PARAMETERS["properties"],
        "comment": {"type": "string", "description": "一句话说明这条 DSL 为什么就是题面那条表达式。"},
    },
    "required": ["multi_line_expr", "comment"],
    "additionalProperties": False,
}


def _stats(values, panel, lookback) -> dict:
    """对一次求值结果做**清点**。每一项都数得出来，没有一处是「应该是多少」。"""
    import numpy as np
    import pandas as pd

    if isinstance(values, pd.DataFrame):
        values = values.iloc[:, 0]
    v = pd.to_numeric(pd.Series(values).to_numpy(), errors="coerce").astype("float64")
    finite = np.isfinite(v)

    dts = panel.index.get_level_values("datetime")
    n_dates = int(dts.nunique())
    n_syms = int(panel.index.get_level_values("instrument").nunique())
    cells = n_dates * n_syms
    coverage = (float(finite.sum()) / cells) if cells else 0.0

    warm = 0
    if isinstance(lookback, int) and lookback > 1 and len(v):
        early = list(sorted(pd.unique(dts))[: lookback - 1])
        # `Index.isin` 返回的已经是 ndarray，别再 `.to_numpy()`（实测 AttributeError）。
        mask = np.asarray(pd.Index(dts).isin(early), dtype=bool)
        warm = int(finite[mask].sum())

    uniq = np.unique(v[finite])
    return {
        "rows": int(len(v)),
        "panel_cells": cells,
        "coverage": min(max(coverage, 0.0), 1.0),
        "inf_count": int(np.isinf(v).sum()),
        "nan_count": int(np.isnan(v).sum()),
        "nonnull_before_warmup": warm,
        "is_constant": bool(len(uniq) <= 1),
        "n_distinct_finite": int(len(uniq)),
    }


class ImplementTools:
    """与 `FactorEvalTools` 同形（`schemas` / `dispatch` / `result_to_content`）。"""

    def __init__(self, panel, lookback, *, preview_rows: int = 3) -> None:
        self.panel = panel
        self.lookback = lookback
        self.preview_rows = preview_rows
        #: 每一次成功求值都按顺序记下来（表达式 + 清点）。兜底规则取这里的最后一条。
        self.evaluated: list[dict] = []
        #: 模型显式交付的那一条（可能不止一次调用，取最后一次成功的）。
        self.submitted: dict | None = None

    # ---- run_trajectory 依赖的三个方法 -------------------------------------

    def schemas(self) -> list[dict[str, Any]]:
        return [
            {"type": "function", "function": {
                "name": "evaluate_expression",
                "description": (
                    "用 AlphaAgent 的 DSL 解析器与算子库在题面窗口的面板上求值，"
                    "返回清点结果（覆盖率、Inf/NaN 计数、暖机期内的非空个数、是否常数、前几行样例）。"
                    "解析或求值失败时返回结构化报错（阶段、生成码行号、你写的哪一行）。"),
                "parameters": _EVAL_PARAMETERS}},
            {"type": "function", "function": {
                "name": "submit_expression",
                "description": (
                    "【正式交付】确定这条 DSL 就是题面那条表达式的实现。会先求值一次，"
                    "成功才算交付（stored=true）。这是唯一的交付方式。"),
                "parameters": _SUBMIT_PARAMETERS}},
        ]

    def dispatch(self, name: str, arguments: Any) -> dict[str, Any]:
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments) if arguments.strip() else {}
            except json.JSONDecodeError as e:
                return {"ok": False, "error": f"invalid_tool_arguments_json: {e}",
                        "error_type": "JSONDecodeError"}
        if not isinstance(arguments, dict):
            return {"ok": False, "error": "tool_arguments_must_be_object",
                    "error_type": "ToolArgumentsError"}
        expr = arguments.get("multi_line_expr")
        if not isinstance(expr, str) or not expr.strip():
            return {"ok": False, "error": "multi_line_expr_required_non_empty_string",
                    "error_type": "ToolArgumentsError"}
        factor_name = arguments.get("factor_name") or "expr"
        if name not in ("evaluate_expression", "submit_expression"):
            return {"ok": False, "error": f"unknown_tool: {name}", "error_type": "UnknownTool"}

        out = self._evaluate(expr, factor_name)
        if name == "submit_expression":
            out["stored"] = bool(out.get("ok"))
            if out.get("ok"):
                self.submitted = {"multi_line_expr": expr, "factor_name": factor_name,
                                  "comment": arguments.get("comment"), "stats": out["stats"]}
            else:
                out["hint"] = "求值没过，这条没有被记为交付。修好再交。"
        return out

    @staticmethod
    def result_to_content(result: dict[str, Any]) -> str:
        return json.dumps(result, ensure_ascii=False, default=str)

    # ---- 真正干活的那一段 ---------------------------------------------------

    def _evaluate(self, expr: str, factor_name: str) -> dict[str, Any]:
        from alphaagent.dsl.core.errors import MultiLineFactorEvalError
        from alphaagent.dsl.eval import compile_multi_line_factor, eval_factor

        try:
            generated = compile_multi_line_factor(
                expr, columns=["$" + str(c) for c in self.panel.columns])
            values = eval_factor(expr, self.panel)
        except MultiLineFactorEvalError as e:
            # 系统自己的结构化报错，原样回给模型 —— 这正是它自己迭代的方式。
            return {"ok": False, "error_type": type(e).__name__,
                    "phase": getattr(e, "phase", None), "problem": getattr(e, "problem", None),
                    "generated_code": getattr(e, "generated_code", None),
                    "your_line_no": getattr(e, "user_line_no", None),
                    "your_line_text": getattr(e, "user_line_text", None),
                    "available_columns": ["$" + str(c) for c in self.panel.columns]}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error_type": type(e).__name__, "error": str(e)[:2000],
                    "available_columns": ["$" + str(c) for c in self.panel.columns]}

        st = _stats(values, self.panel, self.lookback)
        row = {"factor_name": factor_name, "multi_line_expr": expr,
               "generated_code": generated, "stats": st, "values": values}
        self.evaluated.append(row)
        return {"ok": True, "factor_name": factor_name, "generated_code": generated,
                "stats": st, "preview": self._preview(values)}

    def _preview(self, values) -> list[dict]:
        import pandas as pd
        s = values.iloc[:, 0] if isinstance(values, pd.DataFrame) else pd.Series(values)
        head = s.head(self.preview_rows)
        out = []
        for idx, val in head.items():
            dt, inst = (idx if isinstance(idx, tuple) else (idx, ""))
            out.append({"datetime": str(pd.Timestamp(dt).date()), "instrument": str(inst),
                        "value": (None if val != val else float(val))})
        return out


def build_prompt(spec, panel_info: dict) -> str:
    """system prompt = AlphaAgent 现算的算子清单 + DSL 写法 + **题面自己的话**。

    题面正文原样贴进来（`spec.raw`），不做转述 —— 转述一次就多一个我们编的口径。
    """
    from alphaagent.dsl.catalog import operator_catalog_markdown

    cols = "、".join(f"`${c}`" for c in panel_info["columns"])
    return f"""你是 AlphaAgent 的因子实现智能体。这一次的任务**不是挖掘新因子**，而是
**把题面给定的那条源方言表达式，用本仓库的 DSL 精确实现出来**。

# 面板

索引 `(datetime, instrument)`，主频 1d。**可用列只有这些**：{cols}。
共 {panel_info['rows']} 行 = {panel_info['n_dates']} 个交易日 × 至多
{panel_info['n_instruments']} 只标的，日期范围 {panel_info['date_min']} ~ {panel_info['date_max']}。
**没有列出来的列就是没有**（没有复权价、没有市值、没有行业码、没有基本面列）；
引用不存在的列会当场报错，不要试。

# DSL 写法

- 引用列写 `$列名`；算子大写；可以多行，前面几行是赋值，**最后一行是因子值**。
- 时序算子（`TS_*`、`DELTA`、`DELAY` 等）在**每个 instrument 各自的时间序列**上算；
  截面算子（`RANK`、`CS_*`）在**每个 datetime 的截面**上跨 instrument 算。
- 常数直接写数字；负号可以写 `-1 * X`，也有 `NEG(X)`。

## 可用算子（本仓库注册表现算）

{operator_catalog_markdown()}

# 工具与交付

- `evaluate_expression`：求值并返回清点结果。失败时返回结构化报错，照着改。
- `submit_expression`：**唯一的交付方式**。想好了就交，交完就可以停。
  你若一直不交，我们按事先说好的规则取「{FALLBACK_RULE}」—— 所以别把最好的那次
  留在中间轮次。

# 题面（原文，逐字）

```
{spec.raw}
```

# 你要注意的三件事（都来自上面的题面，不是我加的）

1. `expression` 照抄原文、算子不得自行替换 —— 你的 DSL 必须与原文**逐算子对应**，
   不是"效果差不多"。
2. 暖机口径：`warmup_policy` 与 `lookback` 见题面。清点结果里的
   `nonnull_before_warmup` 就是**暖机期内被你算出了值的格子数**；题面要求
   回看窗口未满的日期输出空值时，这个数应当是 0。
3. `nonfinite_policy` 见题面 —— 该传播就传播，不要 fillna。
"""


def mine(*, panel, spec, client, model: str, log_dir, max_turns: int,
         max_tokens: int, verbose: bool = True):
    """跑一次 AlphaAgent 的 agent 循环。返回 `(chosen, tools, messages)`。

    `chosen` 是 `{multi_line_expr, values, stats, source}` 或 `None`
    （`source` ∈ {`submit_expression`, `fallback_last_evaluated`}）。
    """
    from alphaagent.factor.mining.loop import run_trajectory

    lookback = spec.declarations.get("lookback")
    tools = ImplementTools(panel, lookback)
    system_prompt = build_prompt(spec, panel.attrs["gb_panel_info"])
    user_message = (
        f"请把题面给的源方言原文 `{spec.expression}` 用本仓库 DSL 实现出来，"
        f"先用 evaluate_expression 验一遍，确认无误后 submit_expression 交付。")

    log_dir = pathlib.Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    messages = run_trajectory(
        client=client, model=model, system_prompt=system_prompt,
        user_message=user_message, tools=tools, log_jsonl=log_dir / "trajectory.jsonl",
        max_turns=max_turns, max_tool_calls_per_round=4, max_tool_workers=1,
        min_tool_call_rounds_before_allow_stop=1, temperature=None,
        max_tokens=max_tokens, printer=None)

    if tools.submitted is not None:
        expr = tools.submitted["multi_line_expr"]
        row = next(r for r in reversed(tools.evaluated) if r["multi_line_expr"] == expr)
        return ({"multi_line_expr": expr, "values": row["values"], "stats": row["stats"],
                 "generated_code": row["generated_code"], "source": "submit_expression"},
                tools, messages)
    if tools.evaluated:
        row = tools.evaluated[-1]
        return ({"multi_line_expr": row["multi_line_expr"], "values": row["values"],
                 "stats": row["stats"], "generated_code": row["generated_code"],
                 "source": "fallback_last_evaluated"}, tools, messages)
    return None, tools, messages
