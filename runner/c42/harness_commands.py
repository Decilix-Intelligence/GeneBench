# -*- coding: utf-8 -*-
"""三配置的**容器内调用命令**（A1，2026-09-05 通宵）。

在此之前仓库里没有任何一处给出 harness 的调用命令 —— `run_once(command=…)` 是必填参数，
可 registry 只记了 config_id/harness/model，命令从来没写下来。

**形态**：compose 模板把 `command: {command}` 当 YAML 标量写进去，长命令里的引号会把 YAML
打坏。这里一律返回 **JSON 数组**（`["sh", "-c", "..."]`）—— JSON 是合法的 YAML 流序列，
引号与换行都由 JSON 转义兜住，compose 原样交给 `sh -c`。

**题面从哪来**：run dir 的 `work/INSTRUCTION.md` 挂在容器的 `/task/INSTRUCTION.md`（P8 核过它必在）。
**模型从哪来**：容器 env 里已有 `OPENAI_BASE_URL` / `LLM_BASE_URL`（边车反代）与占位 key；
命令**只读这些变量**，不写死任何主机名 —— 写死就绕过了边车。

**OpenHands 1.11.0 没有 CLI**（`openhands-ai` 只装了 `openhands.sdk` 与 servers，
`python -m openhands.core.main` 与 `openhands` 命令都不存在 —— 2026-09-05 在 f02 离线实测），
所以用 SDK 写一段最小驱动：`LLM` → `Agent(默认工具集，关浏览器)` → `Conversation(workspace=/task)`
→ `send_message(题面)` → `run()`。驱动内联在命令里（heredoc），**不往 work/ 里放文件** ——
work/ 是 P8 封闭的，多一个文件就红。

**RD-Agent(Q)**：适配器只有「LLM 写因子」被给定代码替换的降级路径（`adapters/rdagent_q/adapter.py`），
真 LLM 驱动的循环没有实现 → 本模块**不给它命令**，调用方拿到 `None` 就该记 BLOCKED。
"""
from __future__ import annotations

import json
from pathlib import Path

from ..registry import RegistryError

INSTRUCTION = "/task/INSTRUCTION.md"

_CODEX = (
    'export CODEX_HOME=/task/.codex && mkdir -p "$$CODEX_HOME" && cd /task && '
    'codex exec -c model_provider=deepseek '
    "-c 'model_providers.deepseek={name=\"DeepSeek\",base_url=\"'\"$$OPENAI_BASE_URL\"'\",env_key=\"OPENAI_API_KEY\"}' "
    '-c model=deepseek-chat --skip-git-repo-check --ephemeral '
    '--dangerously-bypass-approvals-and-sandbox -C /task '
    f'"$$(cat {INSTRUCTION})"'
)

_OPENHANDS_DRIVER = '''
import os, sys
os.environ.setdefault("OPENHANDS_SUPPRESS_BANNER", "1")
from openhands.sdk import LLM, Agent, Conversation
from openhands.tools import get_default_tools
llm = LLM(model="openai/deepseek-chat", api_key=os.environ["LLM_API_KEY"],
          base_url=os.environ["LLM_BASE_URL"], temperature=0.0)
agent = Agent(llm=llm, tools=get_default_tools(enable_browser=False))
conv = Conversation(agent, workspace="/task")
conv.send_message(open("/task/INSTRUCTION.md", encoding="utf-8").read())
conv.run()
conv.close()
'''.strip("\n")

_OPENHANDS = "cd /task && export HOME=/task/.oh_home && mkdir -p $$HOME && python - <<'GBOH'\n" + _OPENHANDS_DRIVER + "\nGBOH"


#: compose 会在**解析文件时**就把 `$VAR` 插值掉（2026-09-05 实测：`mkdir -p "$CODEX_HOME"` 变成
#: `mkdir: cannot create directory ''`，两臂 3 秒退出、零次模型调用）。要让 `$` 活到容器里的 sh，
#: 必须写成 `$$`；`$(cat …)` 同理。OpenHands 那条是 python heredoc、读 os.environ，没有裸 `$`。
#: OpenHands SDK 的 `LLMProfileStore` 要写 `~/.openhands/profiles`；任务容器以 uid 1000 跑、HOME 不可写
#: （2026-09-05 实测：`PermissionError: /.openhands`，两臂 20 秒退出、零次调用）。HOME 指到 /task 下。
def command_for(harness: str, *, repo_root=None) -> str | None:
    """返回 compose 可直接用的命令（JSON 数组字符串）；没有实现的 harness 返回 `None`。

    **先查数据、再回退硬编码**（W-0）：`harnesses/<id>/launch.json` 与
    `integrations/<id>/launch.json` 里按 `harness` 名找；找不到才落到下面两条常量。
    阶段二/三的代理各自只加自己的目录，**不再改这个文件** —— 这就是数据驱动的全部目的。

    `_CODEX` / `_OPENHANDS` 两条常量**故意留着**：它们是
    `ops/test_launch_registry.py` 的期望值，迁移后 launch.json 渲出来的命令
    必须与它们**逐字节相同**。删掉常量就等于把「迁移有没有改动题面之外的东西」
    这个问题变成不可回答。
    """
    spec = discover_launch_specs(repo_root).get(harness)
    if spec is not None:
        return json.dumps(spec["command"])
    if harness == "Codex CLI":
        return json.dumps(["sh", "-c", _CODEX])
    if harness == "OpenHands":
        return json.dumps(["sh", "-c", _OPENHANDS])
    return None

# ---------------------------------------------------------------------------
# 数据驱动的启动清单（W-0，2026-09-06）
# ---------------------------------------------------------------------------
#: 放启动清单的两棵树。`harnesses/` = 阶段三的通用 CLI；`integrations/` = 阶段二的专用系统。
#: **目录名就是 id**，一个 id 一个目录，目录里 `launch.json` + `config.yaml` + `Dockerfile`。
LAUNCH_ROOTS: tuple[str, ...] = ("harnesses", "integrations")
LAUNCH_FILE = "launch.json"

#: `launch.json` 的键**全集**（缺一个或多一个都红）。
#: 为什么不许多余键：多出来的键在这里是静默的，在读它的人眼里却像是生效了 ——
#: 「写了没生效」比「写错了报错」难查一个数量级。
LAUNCH_KEYS: tuple[str, ...] = (
    "harness", "paradigm", "image", "command", "env_required", "notes")

#: 范式轴（卡 4.2 §18）。P1 通用 agent / P2 多智能体框架 / P3 领域专用循环。
PARADIGMS: tuple[str, ...] = ("P1", "P2", "P3")

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _validate_launch(spec, where: str) -> dict:
    if not isinstance(spec, dict):
        raise RegistryError(f"{where}: launch.json 顶层必须是对象")
    missing = [k for k in LAUNCH_KEYS if k not in spec]
    extra = [k for k in spec if k not in LAUNCH_KEYS]
    if missing or extra:
        raise RegistryError(
            f"{where}: launch.json 键集必须**恰好**是 {list(LAUNCH_KEYS)}"
            f"（缺 {missing}；多 {extra}）")
    if not isinstance(spec["harness"], str) or not spec["harness"].strip():
        raise RegistryError(f"{where}: harness 必须是非空字符串")
    if spec["paradigm"] not in PARADIGMS:
        raise RegistryError(
            f"{where}: paradigm={spec['paradigm']!r} 不在 {list(PARADIGMS)}")
    if not isinstance(spec["image"], str) or not spec["image"].strip():
        raise RegistryError(f"{where}: image 必须是非空镜像名")
    cmd = spec["command"]
    if (not isinstance(cmd, list) or not cmd
            or not all(isinstance(x, str) for x in cmd)):
        raise RegistryError(f"{where}: command 必须是非空的字符串数组")
    env = spec["env_required"]
    if not isinstance(env, list) or not all(isinstance(x, str) and x for x in env):
        raise RegistryError(f"{where}: env_required 必须是字符串数组")
    if not isinstance(spec["notes"], str):
        raise RegistryError(f"{where}: notes 必须是字符串")
    return spec


def launch_dirs(repo_root=None) -> list[Path]:
    """`harnesses/` 与 `integrations/` 下每个含 `launch.json` 的目录，按路径排序。"""
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT
    out: list[Path] = []
    for r in LAUNCH_ROOTS:
        base = root / r
        if not base.is_dir():
            continue
        for d in sorted(p for p in base.iterdir() if p.is_dir()):
            if (d / LAUNCH_FILE).is_file():
                out.append(d)
    return out


def discover_launch_specs(repo_root=None) -> dict[str, dict]:
    """按 harness 名索引的启动清单。**同名两份即红** —— 静默取其一会让

    「我明明加了却没生效」变成一次长调查。**不缓存**：清单是数据不是常量，
    一次 run 里只读几次，省下的那点时间不值一个「改了没重启」的坑。
    """
    out: dict[str, dict] = {}
    seen: dict[str, Path] = {}
    for d in launch_dirs(repo_root):
        p = d / LAUNCH_FILE
        try:
            spec = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise RegistryError(f"{p}: launch.json 读不出来（{type(e).__name__}: {e}）") from e
        spec = _validate_launch(spec, str(p))
        h = spec["harness"]
        if h in seen:
            raise RegistryError(
                f"harness 名重复：{h!r} 同时出现在 {seen[h]} 与 {p} —— "
                f"一个 harness 只能有一份启动清单")
        seen[h] = p
        out[h] = spec
    return out


