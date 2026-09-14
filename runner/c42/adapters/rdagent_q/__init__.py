"""RD-Agent(Q) 适配层（卡 4.2 §10 / §11.1）。

**实测结论（2026-09-04，在 f02 的 `gb-probe-rd:0.8.0` 容器里跑出来的，不是凭记忆）**：

* RD-Agent 硬依赖 `docker`，但**因子路径不用它**。
  `components/coder/factor_coder/factor.py:163-169` 是
  `subprocess.check_output(f"{FACTOR_COSTEER_SETTINGS.python_bin} {execution_code_path}",
  shell=True, cwd=self.workspace_path, ...)` —— **本地子进程**。
  用 Docker 的是**回测**路径（`scenarios/qlib/experiment/workspace.py:20` 的 `QTDockerEnv`），
  而那条由 `MODEL_COSTEER_SETTINGS.env_type` 选，**默认值实测是 `"conda"` 不是 `"docker"`**。
* 因子产物：`workspace_path / "result.h5"`（factor.py:194，`pd.read_hdf` 读）。
* 因子的输入数据不是 qlib provider 树，是 `daily_pv.h5` / `daily_pv_all.h5` / `daily_pv_debug.h5`
  （`scenarios/qlib/experiment/utils.py:24-46`），放在 `FACTOR_CoSTEER_data_folder` 下。
  **这修正了 §11.1 的前提**：跑因子阶段不需要 provider 树，只需要一张面板 HDF5；
  provider 树是**回测**路径（`qrun conf.yaml`）才要的。
* 四个默认路径落在 `/task` 之外，必须改配置（否则 §3.3 的
  `framework_output_outside_task_mount`）：`RD_AGENT_SETTINGS.workspace_path`
  = `/git_ignore_folder/RD-Agent_workspace`、`pickle_cache_folder_path_str` = `/pickle_cache`、
  `FACTOR_CoSTEER_data_folder` = `git_ignore_folder/factor_implementation_source_data`（相对路径，
  落在哪取决于 cwd —— 相对路径本身就不可核，§3.3 因此把它一并判违规）。

**数据面**：走冻结 provider（容器内 `/task/provider`），**不接社区 channel**。
`materialize()` 把 provider 落成因子路径要的面板 HDF5，全部写在 `/task` 下。
"""
