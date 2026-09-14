# -*- coding: utf-8 -*-
"""接线④：场景。**用子类，不改内核。**

顶替的是**一个**方法：

    rdagent.scenarios.qlib.experiment.factor_experiment.QlibFactorScenario.get_runtime_environment

上游那一份（`factor_experiment.py:88`）的做法是
`get_runtime_environment_by_env(get_factor_env())` —— 它起一个 `LocalEnv`，
在里面 `python runtime_info.py` 把「你有什么运行环境」采出来喂进 prompt。
两条在本环境里不成立的前提：

  1. `get_factor_env()` 造 `CondaConf(conda_env_name=os.environ.get("CONDA_DEFAULT_ENV"))`，
     没有 conda 时 `conda_env_name=None` → pydantic `ValidationError`，**场景根本建不起来**
     （`glue/bootstrap.py` 给了个字符串把这一关过掉）；
  2. 过掉之后 `conda run` 失败 → `bin_path=""` → `PATH` 里没有 `python`，
     采集脚本报 `timeout: failed to run command 'python'`，而这句错误**会原样进 prompt**
     成为「你的运行环境」。实测见 `ops/reports/i_rdagent_q/probe5.txt`。

所以这里给一句**真话**（镜像里实际有什么）替掉那次采集。这不是绕过检查 ——
被替掉的是一次"采集"，替上去的是同一件事实的、我们能核对的写法。

其余全部沿用上游：background / output_format / interface / strategy 的提示词
一个字没动，`get_source_data_desc()` 仍然是上游的 `get_data_folder_intro()`
（它读 `glue/panel.py` 落下的那份面板，所以模型看到的列就是网关真给的列）。
"""
from __future__ import annotations

import platform
import sys


def _runtime_desc() -> str:
    import numpy
    import pandas
    return (f"Python {sys.version.split()[0]} on {platform.system()} "
            f"({platform.machine()}), offline container.\n"
            f"pandas {pandas.__version__}, numpy {numpy.__version__}, "
            f"pytables available for HDF5.\n"
            "No network access at runtime. No conda. Only the standard scientific "
            "stack that is already installed may be used; do not pip install anything.")


def make_scenario():
    """返回一个可用的 `QlibFactorScenario` 子类实例。"""
    from rdagent.scenarios.qlib.experiment.factor_experiment import QlibFactorScenario

    class GeneBenchFactorScenario(QlibFactorScenario):
        """只顶替 `get_runtime_environment`（见模块 docstring）。"""

        def get_runtime_environment(self) -> str:  # noqa: D102
            return _runtime_desc()

    return GeneBenchFactorScenario()
