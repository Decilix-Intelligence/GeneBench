# -*- coding: utf-8 -*-
"""接线⑤：跑 RD-Agent 自己的因子实现循环（CoSTEER），**模型经边车**。

这是本接入的主路：把题面的因子交给 RD-Agent 的 `FactorCoSTEER`，由**它**驱动
「写 `factor.py` → 本地子进程执行 → 评估 → 再写」的多轮循环。写代码的是模型，
执行的是上游的 `FactorFBWorkspace.execute()`（`version=1` 走 `subprocess` 直接跑
`{python_bin} factor.py`，**不经 Docker** —— 实测，所以在我们的容器里跑得动）。

与既有 `runner/c42/adapters/rdagent_q/adapter.py` 的关系：那一份只有**降级路径**
（`ctx["factor_code"]` 直接给一份 `factor.py`，跳过模型），N-105 记的就是
「真 LLM 驱动循环未实现」。本模块补的正是那一步，且**不改内核**：`adapters/` 一个字没动。

降级路径这里也留着，但它**只在没有模型可用时**（f01 走查）被显式打开
（`GB_RDAGENT_FACTOR_CODE`），并且会在 stdout 上打横幅 —— 它证明的是链路，不是模型。
"""
from __future__ import annotations

import os
import pathlib
import traceback
from pathlib import Path


class DevelopFailed(RuntimeError):
    """循环没跑出可用的值。**不假装跑出来了。**"""


def _task(spec):
    from rdagent.components.coder.factor_coder.factor import FactorTask
    desc = (f"Implement the factor `{spec.factor_id}` exactly as written in the source "
            f"dialect below. Do not substitute operators with approximations.\n"
            f"Source dialect: {spec.expression}\n"
            f"Evaluation window: {spec.window_start} .. {spec.window_end} (inclusive).\n"
            f"Warm-up starts at the first day of the window; do NOT use data before "
            f"the window to fill the first rows.\n"
            f"Task-given conventions (follow them literally): {spec.declarations}")
    return FactorTask(factor_name=spec.factor_id, factor_description=desc,
                      factor_formulation=spec.expression, version=1,
                      variables={k: str(v) for k, v in spec.declarations.items()})


def _salvage_code():
    """从工作区目录里捡回**模型已经写出来的** `factor.py`。

    为什么不从 `evolve_agent.evolving_trace` 捡：那份 trace 是在**一轮走完之后**才
    append 的，而实测撞到的失败点在第一轮的评估器里 —— 那时 trace 还是空的。
    工作区却已经在盘上了：`FBWorkspace` 一 inject_files 就落盘
    （`RD_AGENT_SETTINGS.workspace_path/<uuid>/factor.py`）。

    只读盘，不改上游任何对象。返回 `(代码文本, 工作区路径)`，捡不到返回 `(None, None)`
    —— 捡不到时调用方要把**原来那个异常**抛出去，不是抛一句「打捞失败」。
    """
    from .bootstrap import WORKSPACE

    best = None
    for f in pathlib.Path(WORKSPACE).glob("*/factor.py"):
        st = f.stat()
        if best is None or st.st_mtime > best[0]:
            best = (st.st_mtime, f)
    if best is None:
        return None, None
    return best[1].read_text(encoding="utf-8"), best[1].parent


def run_costeer(spec):
    """跑真循环。返回 `(values_df, meta)`；跑不出来抛 `DevelopFailed`。"""
    from rdagent.components.coder.factor_coder import FactorCoSTEER

    from .scenario import make_scenario

    scen = make_scenario()
    task = _task(spec)
    try:
        from rdagent.scenarios.qlib.experiment.factor_experiment import QlibFactorExperiment
        exp = QlibFactorExperiment(sub_tasks=[task])
    except Exception:                      # noqa: BLE001
        # qlib 场景的实验容器要一份模板工作区；拿不到就退回基类 —— 循环本身不依赖它。
        from rdagent.components.coder.factor_coder.factor import FactorExperiment
        exp = FactorExperiment(sub_tasks=[task])

    # `knowledge_self_gen=False` 是**上游自己的构造参数**（`CoSTEER.__init__` 的形参），
    # 不是 monkeypatch。关掉的原因是它跑完一轮之后会调 `rag.generate_knowledge()` →
    # `create_embedding()` → 打 **embedding 端点**（默认 `text-embedding-3-small`）。
    # 本环境只发一个 chat 模型（"一个模型 × 多种 harness" 是主表的切片键），
    # 边车后面没有 embedding 可打，那一次调用必然失败 —— 实测：一轮实现与评估都成功了，
    # 却在收尾建知识图谱时炸掉，整个 develop() 抛 RuntimeError，前面的成果全丢。
    # **`with_knowledge` 保持 True**：关掉它 `implement_one_task` 会拿 `None` 去取
    # `queried_knowledge.task_to_former_failed_traces[...]`（上游那一行没有 None 分支）。
    coder = FactorCoSTEER(scen, knowledge_self_gen=False)
    mode = "costeer_llm_loop"
    try:
        exp = coder.develop(exp)
        wss = list(getattr(exp, "sub_workspace_list", []) or [])
    except Exception as e:                                      # noqa: BLE001
        # **打捞**：`develop()` 抛出时，模型已经写好的 `factor.py` 会随异常一起没了 ——
        # 而那份代码正是这次运行真正产出的东西。实测撞到过：评估器要模型回
        # `output_format_decision` 这个键，模型没给，上游重试若干次后 `KeyError`，
        # 此时代码早已写好、也已经跑过一遍。
        code, wsdir = _salvage_code()
        if not code:
            raise
        print(f"!! develop() 抛了 {e!r}；从 {wsdir} 打捞回模型写好的 factor.py，"
              "重跑一遍取值。**代码仍然是模型写的**，不是我们给的。", flush=True)
        df, meta = run_degraded(spec, code)
        meta["mode"] = "costeer_llm_loop_salvaged"
        meta["salvaged_from"] = str(wsdir)
        meta["develop_error"] = repr(e)
        return df, meta
    if not wss:
        raise DevelopFailed("CoSTEER 跑完了但没有 sub_workspace —— 没有代码可执行")
    ws = wss[0]
    feedback, df = ws.execute(data_type="Debug")
    if df is None or len(df) == 0:
        raise DevelopFailed(f"因子代码没有产出值。执行反馈：{str(feedback)[-1500:]}")
    return df, {"mode": mode,
                "workspace": str(getattr(ws, "workspace_path", "")),
                "factor_code": (ws.file_dict or {}).get("factor.py", ""),
                "execution_feedback": str(feedback)[-4000:]}


def run_degraded(spec, factor_code: str):
    """降级路径：**给定**一份 `factor.py`，跳过模型，其余（执行、读值）照跑。

    与 `adapters/rdagent_q/adapter.py::RDAgentQAdapter.run` 同形。
    它证明的是**链路**（面板→执行→值→产物），不是模型 —— 用它出的证据必须这么说。
    """
    from rdagent.components.coder.factor_coder.factor import FactorFBWorkspace

    ws = FactorFBWorkspace(target_task=_task(spec))
    ws.inject_files(**{"factor.py": factor_code})
    feedback, df = ws.execute(data_type="Debug")
    if df is None or len(df) == 0:
        raise DevelopFailed(f"降级路径也没产出值。执行反馈：{str(feedback)[-1500:]}")
    return df, {"mode": "degraded_given_code",
                "workspace": str(getattr(ws, "workspace_path", "")),
                "factor_code": factor_code,
                "execution_feedback": str(feedback)[-4000:]}


def develop(spec):
    """选路并跑。返回 `(values_df | None, meta)` —— **失败不抛给调用方**，
    因为调用方还要如实写一份「我什么都没算出来」的产物（覆盖率 0），
    那比不写产物更有信息量。"""
    code_path = os.environ.get("GB_RDAGENT_FACTOR_CODE")
    if code_path:
        print("=" * 72, flush=True)
        print("!! 降级路径：factor.py 由 GB_RDAGENT_FACTOR_CODE 给定，**模型没有参与**。", flush=True)
        print("!! 这份产物是链路证据（面板→执行→值→artifact），不是模型能力证据。", flush=True)
        print("=" * 72, flush=True)
        try:
            return run_degraded(spec, Path(code_path).read_text(encoding="utf-8"))
        except Exception as e:                                  # noqa: BLE001
            return None, {"mode": "degraded_given_code", "error": repr(e),
                          "traceback": traceback.format_exc()[-3000:]}
    try:
        return run_costeer(spec)
    except Exception as e:                                      # noqa: BLE001
        print(f"!! CoSTEER 循环失败：{e!r}", flush=True)
        return None, {"mode": "costeer_llm_loop", "error": repr(e),
                      "traceback": traceback.format_exc()[-3000:]}
