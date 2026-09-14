"""RD-Agent(Q) 适配器本体。**只做转录与切片。**"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from runner.c42 import origin as OR
from runner.c42 import upstream_pins as UP
from runner.c42.adapters import base as AB

#: 容器内的落点。四个默认值都在 `/task` 之外（实测），必须全部改到这里来。
WORKSPACE = "/task/out/rdagent/workspace"
PICKLE_CACHE = "/task/out/rdagent/pickle_cache"
DATA_FOLDER = "/task/out/rdagent/source_data"
LOG_DIR = "/task/out/rdagent/log"
#: 冻结 provider 的挂载点（卡 4.3 P7b 放进去的，两臂各一份）。
PROVIDER = "/task/provider"
#: 因子路径实际读的面板文件名（`scenarios/qlib/experiment/utils.py` 实测）。
PANEL_FILES = ("daily_pv.h5", "daily_pv_all.h5", "daily_pv_debug.h5")
#: 因子实现的产物（`factor.py:194` 实测）。
RESULT_H5 = "result.h5"


def env_overrides() -> dict[str, str]:
    """把四个默认路径全部改到 `/task` 下。

    **环境变量名不是猜的**：`RD_AGENT_SETTINGS` 无 `env_prefix`（`RDAgentSettings`），
    `FactorCoSTEERSettings` 的 `model_config` 写着 `env_prefix="FACTOR_CoSTEER_"`（实测）。
    大小写敏感 —— pydantic-settings 默认大小写不敏感，但前缀里的 `CoSTEER` 照抄上游。
    """
    return {
        "WORKSPACE_PATH": WORKSPACE,
        "PICKLE_CACHE_FOLDER_PATH_STR": PICKLE_CACHE,
        "FACTOR_CoSTEER_data_folder": DATA_FOLDER,
        "FACTOR_CoSTEER_data_folder_debug": DATA_FOLDER,
        "LOG_TRACE_PATH": LOG_DIR,
    }


class RDAgentQAdapter(AB.Adapter):
    key = "rdagent_q"
    #: **只有 S3**。回测路径要 qlib + conda（或 Docker），本轮不落；
    #: 声明能做而做不了，会让「框架做不了这个阶段」变成「它做了但做错了」。
    stages = frozenset({"S3"})

    def declared_outputs(self) -> tuple[str, ...]:
        return (WORKSPACE, PICKLE_CACHE, DATA_FOLDER, LOG_DIR)

    # ---- 数据面（§11.1）----

    #: 派生脚本的版本 —— 改了它，派生出来的 h5 就不是同一份东西。
    #: 与 provider 根 hash 一起记进 `inject.json`（裁定 2026-09-04）：
    #: **「这份 h5 是从哪份 provider、用哪段代码派生的」必须可追**，
    #: 否则两次运行的因子值不同时，分不清是 agent 变了还是我们的面板变了。
    MATERIALIZE_VERSION = "1"

    @classmethod
    def materialize(cls, work: Path, panel, *, provider_root_sha256: str) -> dict:
        """把冻结 provider 的面板落成因子路径要的 HDF5。**全部写在 `/task` 下。**

        明确否决稿甲的宿主挂载方案：无宿主 bind-mount、无 NFS
        （卡 4.1 FS-1/FS-2 与本卡硬约束）。

        `panel` 由调用方从**冻结 provider**（容器内 `/task/provider`）取。
        本函数不取数：取数要经网关并留下 `provider_reads.jsonl`（§11.1 的读取钩子），
        那是调用方的事，不是落盘函数的事。

        返回**血统记录**（进 `inject.json`）：派生脚本版本 + provider 根 hash +
        每个 h5 的字节摘要 + 面板形状。**M6 用全量 provider 派生，不用冒烟子集**
        —— 子集派生出来的面板标的数不同，因子值与覆盖率都不可比。
        """
        if not provider_root_sha256:
            raise AB.AdapterError(
                "派生 h5 必须记 provider 根 hash —— 不记的话，"
                "两次运行的因子值不同时分不清是 agent 变了还是我们的面板变了")
        out = Path(work) / "out" / "rdagent" / "source_data"
        out.mkdir(parents=True, exist_ok=True)
        files: dict[str, str] = {}
        for name in PANEL_FILES:
            p = out / name
            panel.to_hdf(p, key="data", mode="w")
            files[name] = hashlib.sha256(p.read_bytes()).hexdigest()
        return {
            "derived_by": f"{__name__}.RDAgentQAdapter.materialize",
            "materialize_version": cls.MATERIALIZE_VERSION,
            "provider_root_sha256": provider_root_sha256,
            "rows": int(len(panel)),
            "n_symbols": int(panel.index.get_level_values(-1).nunique())
            if getattr(panel.index, "nlevels", 1) > 1 else None,
            "files": files,
        }

    # ---- 运行 ----

    def run(self, ctx: dict) -> AB.FrameworkRun:
        """跑 RD-Agent 的因子实现执行器。

        **降级形态（无 LLM 时）**：`ctx["factor_code"]` 直接给一份 `factor.py`，
        跳过「LLM 写代码」那一步，其余（执行、产物、转录）全部真跑。
        这条绿灯证明的是**链路**，不是模型 —— §18.3 要求把这句写进验收文本。
        """
        import rdagent  # noqa: F401  —— 先 import 再核形状
        UP.assert_upstream_shape(rdagent, self.key)

        from rdagent.components.coder.factor_coder.factor import (
            FactorFBWorkspace, FactorTask)

        for k, v in env_overrides().items():
            os.environ.setdefault(k, v)

        work = Path(ctx["work_dir"])
        task = FactorTask(
            factor_name=ctx["factor_id"], factor_description=ctx["description"],
            factor_formulation=ctx["expression"], version=1)
        ws = FactorFBWorkspace(target_task=task)
        ws.inject_files(**{"factor.py": ctx["factor_code"]})
        feedback, df = ws.execute(data_type=ctx.get("data_type", "Debug"))
        return AB.FrameworkRun(
            work_dir=work, stage="S3", task_id=ctx["task_id"],
            config_id=ctx["config_id"], arm=ctx["arm"],
            outputs={"result": Path(ws.workspace_path) / RESULT_H5},
            final_state={"execution_feedback": feedback,
                         "rows": 0 if df is None else int(len(df))},
            stdout=str(feedback)[-4000:])

    # ---- 转录 ----

    def declarations(self, run: AB.FrameworkRun) -> AB.Transcribed:
        """RD-Agent 的原生产物里**没有 `declarations`**（§18.1）。

        所以这里返回**空**，并把每个契约字段标 `absent` —— artifact 因此 malformed，
        那是**正确结论**：这个框架在没读我们契约的情况下确实没做出声明。
        编一个默认值填进去会把「框架不会做」变成「框架做错了」，那是两个结论。
        """
        decl = json.loads(run.outputs["declarations"].read_text(encoding="utf-8")) \
            if "declarations" in run.outputs else {}
        origins = {f"$.declarations.{k}": OR.Source.agent_artifact for k in decl}
        return AB.Transcribed(decl, origins)

    def payload(self, run: AB.FrameworkRun) -> AB.Transcribed:
        """只转录**框架自己写的字节**。行数、覆盖率、摘要这些**不在这里算** ——
        它们是旁路证据，走 `harness_values()`。"""
        pay = json.loads(run.outputs["payload"].read_text(encoding="utf-8")) \
            if "payload" in run.outputs else {}
        origins = {f"$.payload.{k}": OR.Source.framework_output for k in pay}
        return AB.Transcribed(pay, origins)

    def harness_values(self, run: AB.FrameworkRun) -> dict:
        """R 侧证据：从**框架产出的 result.h5** 重算，与 agent 自报值比对。

        取不到（没产物 / 读不了）就返回 `None` —— `unverified`，**不是** `agree`。
        """
        p = run.outputs.get("result")
        if p is None or not Path(p).exists():
            return {k: None for k in
                    ("values_ref.rows", "values_ref.n_dates", "values_ref.n_symbols",
                     "values_ref.coverage", "values_ref.sha256",
                     "nonfinite.inf_count", "nonfinite.nan_count",
                     "degeneracy.is_constant")}
        return values_evidence(Path(p))


def values_evidence(path: Path) -> dict:
    """从值序列文件重算 R 侧证据。**口径按 gold**（卡 4.2 §9 与红队复核）：

    * `coverage` = `isfinite` 计数 ÷ (n_dates × n_symbols)，不是 `notna`；
    * `is_constant` = `unique(finite)` 是否 ≤ 1，**不是**方差是否为 0
      （全 NaN 列的方差是 NaN 不是 0）；
    * `sha256` = **文件字节**摘要，不是重新序列化后的摘要。
    """
    import numpy as np
    import pandas as pd

    # 按扩展名读：RD-Agent 自己的中间产物是 `result.h5`，而**题面契约**的产出物是
    # `/task/values.parquet`（N-44）。写死 `read_hdf` 会让契约那份读不了 ——
    # 实测撞过一次（HDF5ExtError），因为契约文件根本不是 h5。
    suf = Path(path).suffix.lower()
    if suf in (".parquet", ".pq"):
        df = pd.read_parquet(path)
    elif suf in (".csv",):
        df = pd.read_csv(path)
    else:
        df = pd.read_hdf(path)
    if isinstance(df, pd.Series):
        df = df.to_frame("value")
    col = df.columns[-1]
    v = pd.to_numeric(df[col], errors="coerce").to_numpy(dtype="float64")
    # 维度既可能在 MultiIndex 上（RD-Agent 的 result.h5），也可能是普通列
    # （契约的 values.parquet：date / code / value）—— 两种都要认。
    if df.index.nlevels > 1:
        idx = df.index.to_frame(index=False)
        n_dates = int(idx.iloc[:, 0].nunique())
        n_syms = int(idx.iloc[:, 1].nunique()) if idx.shape[1] > 1 else 0
    else:
        cols = [c for c in df.columns if c != col]
        n_dates = int(df[cols[0]].nunique()) if cols else 0
        n_syms = int(df[cols[1]].nunique()) if len(cols) > 1 else 0
    finite = np.isfinite(v)
    cells = (n_dates * n_syms) or len(v)
    return {
        "values_ref.rows": int(len(df)),
        "values_ref.n_dates": n_dates,
        "values_ref.n_symbols": n_syms,
        "values_ref.coverage": float(finite.sum()) / cells if cells else 0.0,
        "values_ref.sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
        "nonfinite.inf_count": int(np.isinf(v).sum()),
        "nonfinite.nan_count": int(np.isnan(v).sum()),
        "degeneracy.is_constant": bool(len(np.unique(v[finite])) <= 1),
    }
