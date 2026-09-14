# -*- coding: utf-8 -*-
"""接线①：**在 import rdagent 之前**把它的配置指到 `/task` 与 `/tmp` 下。

为什么必须在 import 之前：RD-Agent 的每一份设置都是 `pydantic-settings` 的
**模块级单例**（`RD_AGENT_SETTINGS` / `FACTOR_COSTEER_SETTINGS` / `LLM_SETTINGS`
都在各自模块的最后一行实例化）。实例化那一刻就把环境变量读完了 —— 之后再改
`os.environ` 对已经建好的对象没有任何作用，而现场表现是「我明明设了，它还是写到
默认路径」。所以本模块**不 import rdagent**，只摆环境变量；`run.py` 的顺序是
`bootstrap.apply()` → `import rdagent…`。

**这里一行内核代码都没改。** 全部是上游自己声明的配置入口（`env_prefix` 见下），
每一条都在 `REPLACEMENTS` 里登记了「顶替的是哪个对象的哪个属性」，
`ops/test_integration_rdagent_q.py` 会 import 上游逐条核这些属性真的存在。
"""
from __future__ import annotations

import os

#: 容器里 `/task` 就是 run dir 的 `work/` 本身（`runner/c41/runner_core.py` 的
#: `- {workdir}:/task`）。落在它下面的东西会进 `run.json` 的 `unexpected`，
#: 而 run dir 有 P8 文件集封闭核对 —— 所以 RD-Agent 的工作区、缓存、日志
#: **一律指到 `/tmp`**，`/task` 下只留题面点名的两个产出（`artifact.json`、`values.parquet`）。
#: 这与 `integrations/README.md` §1④ 给 P2 的写法一致（P1 那边写 `/task` 是另一回事，见那一节的 CONFLICT 框）。
ROOT = os.environ.get("GB_RDAGENT_ROOT", "/tmp/rdagent_q")
WORKSPACE = f"{ROOT}/workspace"
PICKLE_CACHE = f"{ROOT}/pickle_cache"
DATA_FOLDER = f"{ROOT}/source_data"
LOG_DIR = f"{ROOT}/log"
PROMPT_CACHE = f"{ROOT}/prompt_cache.db"

#: 每一条 = (上游模块, 我们顶替的属性路径, 用的入口, 为什么)。
#: **不是注释而是数据**：测试拿它去 import 上游做属性存在性检查，上游改名当场红。
REPLACEMENTS: tuple[dict[str, str], ...] = (
    {"module": "rdagent.core.conf", "attr": "RD_AGENT_SETTINGS.workspace_path",
     "via": "env WORKSPACE_PATH",
     "why": "默认落在 CWD（容器里就是 /task）下的 git_ignore_folder/RD-Agent_workspace，会破 P8 文件集封闭"},
    {"module": "rdagent.core.conf", "attr": "RD_AGENT_SETTINGS.pickle_cache_folder_path_str",
     "via": "env PICKLE_CACHE_FOLDER_PATH_STR", "why": "同上"},
    {"module": "rdagent.components.coder.factor_coder.config",
     "attr": "FACTOR_COSTEER_SETTINGS.data_folder", "via": "env FACTOR_CoSTEER_data_folder",
     "why": "因子代码执行时从这里 link 源数据；我们把网关取来的面板落在这里"},
    {"module": "rdagent.components.coder.factor_coder.config",
     "attr": "FACTOR_COSTEER_SETTINGS.data_folder_debug", "via": "env FACTOR_CoSTEER_data_folder_debug",
     "why": "execute(data_type=\"Debug\") 读的是这一个；场景描述 get_data_folder_intro() 也读它"},
    {"module": "rdagent.components.coder.factor_coder.config",
     "attr": "FACTOR_COSTEER_SETTINGS.max_loop", "via": "env FACTOR_CoSTEER_max_loop",
     "why": "上游默认 10 轮。实测每轮 3 次模型调用（实现 1 + 评估 2），所以 5 轮 ≈ 15 次，离 RUN_BUDGET 的 100 次闸还远；给到 5 是为了让 RD-Agent **自己的**评审循环有机会修掉它自己写出来的语法错（2 轮那次就是没修完就到头了）"},
    {"module": "rdagent.components.coder.factor_coder.config",
     "attr": "FACTOR_COSTEER_SETTINGS.python_bin", "via": "env FACTOR_CoSTEER_python_bin",
     "why": "因子代码经 subprocess 跑 `{python_bin} factor.py`，镜像里没有裸 `python`"},
    {"module": "rdagent.components.coder.factor_coder.config",
     "attr": "FACTOR_COSTEER_SETTINGS.file_based_execution_timeout",
     "via": "env FACTOR_CoSTEER_file_based_execution_timeout",
     "why": "上游默认 3600 秒，比整题的 --timeout 还长；超时会表现成「跑了一半就没了」"},
    {"module": "rdagent.oai.llm_conf", "attr": "LLM_SETTINGS.chat_model", "via": "env CHAT_MODEL",
     "why": "默认 gpt-4-turbo；改成 openai/deepseek-chat 走边车的 OpenAI 兼容口"},
    {"module": "rdagent.oai.llm_conf", "attr": "LLM_SETTINGS.backend", "via": "env BACKEND",
     "why": "显式钉住 LiteLLM 后端，不靠默认值（默认值随上游版本走）"},
    {"module": "rdagent.oai.llm_conf", "attr": "LLM_SETTINGS.prompt_cache_path",
     "via": "env PROMPT_CACHE_PATH", "why": "默认相对 CWD，落进 /task 会破 P8"},
    {"module": "rdagent.oai.llm_conf", "attr": "LLM_SETTINGS.max_retry", "via": "env MAX_RETRY",
     "why": "默认 10 次重试；一次网络抖动能吃掉十分之一的调用预算"},
    {"module": "rdagent.oai.llm_conf", "attr": "LLM_SETTINGS.chat_stream", "via": "env CHAT_STREAM",
     "why": "关流式：usage 直接在响应体里，边车的记账少一层归一"},
)


def _env(**kv: str) -> None:
    """只 `setdefault` —— 外面（launch.json / 真跑命令）显式给的一律优先。"""
    for k, v in kv.items():
        os.environ.setdefault(k, v)


def apply() -> dict[str, str]:
    """摆好全部环境变量，返回实际生效的那一份（进日志，便于事后对账）。"""
    for d in (ROOT, WORKSPACE, PICKLE_CACHE, DATA_FOLDER, LOG_DIR):
        os.makedirs(d, exist_ok=True)

    _env(
        # ① 落点：全部离开 /task
        WORKSPACE_PATH=WORKSPACE,
        PICKLE_CACHE_FOLDER_PATH_STR=PICKLE_CACHE,
        LOG_TRACE_PATH=LOG_DIR,
        PROMPT_CACHE_PATH=PROMPT_CACHE,
        # 大小写照抄上游：`FactorCoSTEERSettings.model_config` 写的就是 `FACTOR_CoSTEER_`。
        FACTOR_CoSTEER_data_folder=DATA_FOLDER,
        FACTOR_CoSTEER_data_folder_debug=DATA_FOLDER,
        # ② 预算：上游 10 轮 × 每轮 4~5 次调用会撞 RUN_BUDGET 的 100 次闸
        FACTOR_CoSTEER_max_loop=os.environ.get("GB_RDAGENT_MAX_LOOP", "5"),
        FACTOR_CoSTEER_file_based_execution_timeout="300",
        FACTOR_CoSTEER_python_bin="python3",
        # ③ CondaConf.conda_env_name 是 `str`（不是 `str | None`），取不到当场
        #    pydantic ValidationError —— 上游假设自己跑在 conda 里。给一个字符串即可：
        #    `conda run` 在本镜像里必然失败，失败时上游把 bin_path 置空并继续（实测）。
        CONDA_DEFAULT_ENV="none",
        # ④ 模型：只经边车。base URL 只从 env 取，绝不写死主机名。
        BACKEND="rdagent.oai.backend.LiteLLMAPIBackend",
        CHAT_MODEL=os.environ.get("GB_RDAGENT_CHAT_MODEL", "openai/deepseek-chat"),
        CHAT_STREAM="False",
        ENABLE_RESPONSE_SCHEMA="False",
        MAX_RETRY="2",
        LOG_LLM_CHAT_CONTENT="False",
        # litellm 一 import 就去 raw.githubusercontent.com 拉「模型价目表」。
        # 运行期出向白名单里只有模型 API 域名，那次 CONNECT 必然被边车拒并留痕 ——
        # 留下的是一条**我们不需要、却会被当成越权尝试去读**的记录。
        # 这个开关让它用随包发行的本地副本（实测：设了之后启动不再有那条 WARNING）。
        LITELLM_LOCAL_MODEL_COST_MAP="True",
    )

    # LiteLLM 的 openai 兼容路由读 `OPENAI_API_BASE`；边车注入的名字是
    # `OPENAI_BASE_URL`（也可能两个都给）。这里只做**名字之间的搬运**，
    # 值全部来自 launch.json 的 env_required 所列变量，一个主机名都不写死。
    base = os.environ.get("OPENAI_API_BASE") or os.environ.get("OPENAI_BASE_URL") \
        or os.environ.get("LLM_BASE_URL")
    if base:
        _env(OPENAI_API_BASE=base, OPENAI_BASE_URL=base)
    key = os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY")
    if key:
        _env(OPENAI_API_KEY=key)

    keys = ("WORKSPACE_PATH", "PICKLE_CACHE_FOLDER_PATH_STR", "LOG_TRACE_PATH",
            "PROMPT_CACHE_PATH", "FACTOR_CoSTEER_data_folder",
            "FACTOR_CoSTEER_data_folder_debug", "FACTOR_CoSTEER_max_loop",
            "FACTOR_CoSTEER_python_bin", "CHAT_MODEL", "BACKEND", "CHAT_STREAM",
            "MAX_RETRY", "OPENAI_API_BASE")
    # **不回显 OPENAI_API_KEY**（红线 3：凭据不进日志）—— 容器里那把是占位串，
    # 但「占位串也不打」这条纪律要在代码里，不能靠「反正是假的」。
    return {k: os.environ.get(k, "") for k in keys}
