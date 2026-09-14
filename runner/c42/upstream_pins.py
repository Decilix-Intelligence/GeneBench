"""卡 4.2 §10：上游钉死。

**目的**：上游改一个字段名，我们要炸在 **import**，不要炸在
「**这个 harness×model 做不了 S3**」这条**会被写进论文**的结论里。
后者是最贵的失败：它不报错、有数字、方向一致，而且看起来像一个发现。

**钉的是「我们实际跑的那份字节」**（2026-09-04 实测后的落法）。规格原文要求
`commit`「40 位 hex，**不得留空**」，但两个框架的实际情况不同：

* **RD-Agent**：PyPI 的 `0.8.0` 与 GitHub 的 `v0.8.0` 标签对得上，两者都钉。
* **TradingAgents**：PyPI 已到 `0.7.0`（2026-05-21），而 GitHub 最新标签只到 `v0.4.0`
  —— `0.5.0` 之后的发布**没有对应的 git 标签**。给它填一个 v0.4.0 的 SHA
  **比留空更坏**：那是一句关于「我们跑的是哪份代码」的假话。

所以判据改成：`commit`（40 hex）与 `dist_sha256`（64 hex）**至少有一个**，
且 `dist_sha256` 必须是**我们真正安装的那个 wheel** 的摘要。留空 commit 的那条
必须写明 `commit_absent_reason` —— 空着不解释，整条断言就退化成「有这个仓库就行」。

**形状字段（`required_*`）一律 `None` 起步。** 空元组是**空检查**：
`all(x in got for x in ())` 恒真。所以未探测时是 `None`，`assert_upstream_shape()`
见 `None` 直接抛 —— 适配器在实测填表之前**根本 import 不进来**。
§10 写着「不许凭记忆填」，这是它的机械形态。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

def _norm_repo(url: str) -> str:
    return url.rstrip("/").lower().removesuffix(".git")


_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class PinError(RuntimeError):
    pass


@dataclass(frozen=True)
class Pin:
    #: 两类上游的**核验义务不同**，所以要显式分开（裁定 2026-09-04）：
    #:
    #: * `adapter` —— 我们写了 §10 适配层的（RD-Agent(Q) / TradingAgents）。
    #:   它的形状（符号、文件、state 键）必须**实测填写**，上游改名要炸在 import。
    #: * `harness` —— **镜像 + 调用命令**，不做适配层（OpenHands / Codex CLI）。
    #:   它没有我们 import 的符号，形状字段无从填起；核的是**命令与版本**
    #:   （容器里跑 `version_cmd`）。
    #:
    #: 硬把 harness 塞进 adapter 的义务里，只会逼出一份编出来的 `required_attrs`
    #: —— 那比没有更坏（§10 开头那条：空检查恒真）。
    repo: str
    #: 见上：两类上游的核验义务不同。
    kind: str = "adapter"          # adapter | harness
    #: `harness` 用：在容器里跑它核版本。`adapter` 留空。
    version_cmd: tuple[str, ...] = ()
    #: 分发包。PyPI 写 `name==version`，npm 写 `name@version`。从 git 装则留空。
    dist: str = ""
    #: 分发渠道。**必须显式写** —— `@openai/codex@0.153.2` 里有两个 `@`，
    #: 靠猜分隔符会在 scope 包上错（`@openai/codex` 的 scope 本身带 `@`）。
    dist_kind: str = "pypi"          # pypi | npm
    #: 我们实际装的那份**字节**的 sha256（PyPI wheel，或 codeload 的 tar.gz）。
    dist_sha256: str = ""
    #: **PyPI 为这个 dist 声明的 Repository URL。**
    #:
    #: 加这一栏是因为 2026-09-04 撞到了：PyPI 的 `tradingagents` 属于
    #: **Mai0313/tradingagents**（3 stars，`author_email` 是 mai@mai0313.com），
    #: 而不是文献里那个 **TauricResearch/TradingAgents**（102456 stars）。
    #: 两者同名。先前的钉法 `repo=TauricResearch + dist=PyPI tradingagents`
    #: 把**两个不同项目**写在了同一条 Pin 上 —— 而 `assert_pins_wellformed()`
    #: 只查 hex 位数，永远发现不了。
    #:
    #: 这正是 §10 开头写的那种最贵的失败：不报错、有数字、方向一致，
    #: 论文会说「我们跑了 TradingAgents 基线」，实际跑的是一个同名重写。
    dist_repo_url: str = ""
    #: npm 自己的字节完整性串（`sha512-<base64>`）。npm 不给 hex sha256，
    #: 而**它才是 npm 装包时真正校验的那个东西** —— 硬要转成 hex 反而离真相远了。
    dist_integrity: str = ""
    #: 对得上的 git 提交；对不上就留空并写明理由。
    commit: str = ""
    commit_absent_reason: str = ""
    #: **实测**填。`None` = 还没在 f02 上跑过 probe，`assert_upstream_shape()` 会拒。
    required_attrs: tuple[str, ...] | None = None
    #: 装出来的**包内**必须有的文件（import 期可核）。
    required_files: tuple[str, ...] | None = None
    #: 框架一次运行的**产物**文件名（跑完才可核）。与 `required_files` 分开，
    #: 因为两者的可核时机不同 —— 混成一栏会让「包里没有 result.h5」被当成上游改了。
    output_files: tuple[str, ...] = ()
    required_state_keys: tuple[str, ...] | None = None
    note: str = ""

    #: **可 import 的包名**。与 `dist` 分开：从 git 装时没有 `dist`，
    #: 而包名照样要有 —— 先前从 `dist` 推包名，`dist=""` 时推出空串，
    #: `importlib.import_module("")` 抛 `Empty module name`（实测）。
    pkg: str = ""

    @property
    def name(self) -> str:
        if self.pkg:
            return self.pkg
        if not self.dist:
            return ""
        return (self.dist.rsplit("@", 1)[0] if self.dist_kind == "npm"
                else self.dist.split("==")[0])

    @property
    def version(self) -> str | None:
        if not self.dist:
            return None
        if self.dist_kind == "npm":
            return self.dist.rsplit("@", 1)[1]
        return self.dist.split("==")[1]


PINS: dict[str, Pin] = {
    "rdagent_q": Pin(
        repo="https://github.com/microsoft/RD-Agent",
        pkg="rdagent",
        dist="rdagent==0.8.0",
        dist_sha256="5914499f7e896d5547d414a51db12332c78b2e4862595a98e895608450e65123",
        # PyPI 自己声明的 homepage（实测）。与 `repo` 一致 —— 与 tradingagents 那条
        # 形成对照：同一道门，一个通过、一个当场红。
        dist_repo_url="https://github.com/microsoft/RD-Agent/",
        commit="274e274d5dbb72cc2ea139d1a7c93d73ce9b1198",   # tag v0.8.0，api.github.com 实测解析
        # 以下三项全部在 f02 的 gb-probe-rd:0.8.0 容器里实测打印（§10：不许凭记忆填）。
        required_attrs=(
            "rdagent.core.conf:RD_AGENT_SETTINGS.workspace_path",
            "rdagent.core.conf:RD_AGENT_SETTINGS.pickle_cache_folder_path_str",
            "rdagent.components.coder.factor_coder.config:FACTOR_COSTEER_SETTINGS.python_bin",
            "rdagent.components.coder.factor_coder.config:FACTOR_COSTEER_SETTINGS.data_folder",
            "rdagent.components.coder.factor_coder.config:FACTOR_COSTEER_SETTINGS.file_based_execution_timeout",
            "rdagent.components.coder.factor_coder.factor:FactorTask",
            "rdagent.components.coder.factor_coder.factor:FactorFBWorkspace.execute",
            "rdagent.utils.env:LocalEnv",
        ),
        required_files=("components/coder/factor_coder/factor.py",
                        "components/coder/factor_coder/factor_execution_template.txt",
                        "utils/env.py", "core/conf.py"),
        #: 相对**因子工作区**。`result.h5` 的位置在 factor.py:194 写死。
        output_files=("factor.py", "result.h5"),
        #: 因子路径没有 TradingAgents 那种 `final_state` 字典；我们真正依赖的是
        #: `execute()` 的返回契约 —— (feedback 字符串, 值 DataFrame)。
        required_state_keys=("execution_feedback", "rows"),
        note="wheel 上传 2025-11-03；PyPI 版本与 git 标签一一对应，两者都钉。"
             "因子路径经 LocalEnv 本地子进程跑，不经 Docker（实测）",
    ),
    "tradingagents": Pin(
        # **文献里的那个**：102456 stars。2026-09-04 之前本条曾错误地把
        # TauricResearch 的 repo 与 PyPI（Mai0313 的同名包）写在一起 —— 见 N-51。
        repo="https://github.com/TauricResearch/TradingAgents",
        # 从 codeload 的 tag 压缩包装，不从 PyPI（PyPI 那个名字是别人的项目）。
        pkg="tradingagents",
        dist="",
        #: `codeload.github.com/.../tar.gz/<commit>` 的字节摘要（实测）。
        #: **权威的钉是 `commit`** —— GitHub 生成的 tar.gz 字节不保证跨时间稳定，
        #: 这个摘要只作旁证。
        dist_sha256="f4f81e7538992b094a0610d38c919cc2777344bf4ebee55d740818fc323db94d",
        commit="2448d0a12576f9b2ddcd5980a0630833423d1e1b",   # tag v0.4.0（实测解析）
        # 以下三项在 f02 的 `gb-probe-ta:tauric-v0.4.0` 里实测打印（§10：不许凭记忆填）。
        required_attrs=(
            "tradingagents.graph.trading_graph:TradingAgentsGraph.propagate",
            "tradingagents.dataflows.interface:route_to_vendor",
            "tradingagents.dataflows.interface:VENDOR_METHODS",
            "tradingagents.dataflows.interface:TOOLS_CATEGORIES",
            "tradingagents.dataflows.config:set_config",
            "tradingagents.agents.utils.agent_states:AgentState",
            "tradingagents.default_config:DEFAULT_CONFIG",
        ),
        required_files=("dataflows/interface.py", "dataflows/config.py",
                        "dataflows/y_finance.py", "graph/trading_graph.py",
                        "agents/utils/agent_states.py", "default_config.py"),
        #: `AgentState` 的 **16** 个键（实测）。上游改键名要炸在这里。
        #: 注意：与那个同名包（Mai0313）的 14 键**不是一回事**，见 N-51。
        required_state_keys=(
            "asset_type", "company_of_interest", "final_trade_decision",
            "fundamentals_report", "instrument_context", "investment_debate_state",
            "investment_plan", "market_report", "messages", "news_report",
            "past_context", "risk_debate_state", "sender", "sentiment_report",
            "trade_date", "trader_investment_plan"),
        output_files=("logs/", "cache/", "memory/trading_memory.md"),
        note="v0.4.0 是 TauricResearch 的最新标签（HEAD 9dee508c… 在 2026-09-01，"
             "晚于冻结线且无标签）。requires-python >=3.10，实测装在 3.12 上。"
             "vendor 注册表 VENDOR_METHODS 有 11 个方法 × 4 家厂商 —— 那是 §11.2 的替换缝",
    ),
}


#: **通用 harness**（裁定 2026-09-04）：镜像 + 调用命令，**不做 §10 适配层**。
#: 它们读 INSTRUCTION.md、直接写 artifact.json —— 走的是卡 4.3 注入器已支持的裸臂路径。
#: 但**上游仍然要钉**：一个 harness 换了版本、工具调用行为变了，
#: 主表上会表现为「这个 harness 做不了这个阶段」——§10 开头写的那种最贵的失败。
PINS.update({
    "openhands": Pin(
        kind="harness",
        version_cmd=("python", "-c",
                     "import importlib.metadata as m; print(m.version('openhands-ai'))"),
        repo="https://github.com/OpenHands/OpenHands",
        pkg="openhands",
        dist="openhands-ai==1.11.0",
        dist_kind="pypi",
        dist_repo_url="https://github.com/OpenHands/OpenHands",
        #: wheel 的 sha256（PyPI 实测，上传 2026-07-09）。
        dist_sha256="833de097150d498ffc7e175869df4723aec4a6b3c0be27545ca37089e6452c8f",
        commit="",
        commit_absent_reason="PyPI 的 1.11.0 与 git 标签的对应关系未核 —— "
                             "**不填一个没核过的 SHA**（N-51 的教训：两个字段各自都真、"
                             "放在一起是假话）。钉住的是 wheel 的字节摘要",
        note="py >=3.12,<3.14。走 LLM_BASE_URL + openai/deepseek-chat 形态。"
             "默认运行时是 docker sandbox —— 容器内要切到本地/CLI 形态，待实测",
    ),
    "codex_cli": Pin(
        kind="harness",
        version_cmd=("codex", "--version"),
        repo="https://github.com/openai/codex",
        pkg="codex",                       # 命令名，不是 python 模块
        dist="@openai/codex@0.153.2",
        dist_kind="npm",
        dist_repo_url="https://github.com/openai/codex",
        dist_sha256="",
        #: npm registry 实测。**这才是 npm 装包时真正校验的那个东西**。
        dist_integrity=("sha512-IRocJlE+jCZGYHwIJWBja2nDswTSZY4sNddQgU5xiR/"
                        "mVWxo5WcO8pqcajXJea1XDoNK9CaVzizVhUxDhFkU6g=="),
        commit="",
        commit_absent_reason="npm 包，版本核对由容器里的 `codex --version` 做；"
                             "registry 给的 shasum 是 sha1、integrity 是 sha512，"
                             "两个都不是 hex sha256，所以钉 integrity 而不是硬转",
        note="走 config.toml 的 model_providers 段指到 DeepSeek。"
             "**工具调用兼容性要在 M6 前用一道真题实测** —— 不通就换 "
             "@qwen-code/qwen-code 的 OpenAI 兼容模式，registry 相应改并保持"
             "「同模型三 harness」的约束（裁定 2026-09-04）",
    ),
})


def assert_pins_wellformed() -> None:
    """import 期跑。**钉的是字节，不是名字。**"""
    for key, pin in PINS.items():
        if not pin.repo.startswith("https://"):
            raise PinError(f"{key}: repo 不是 https URL")
        if pin.dist_kind not in ("pypi", "npm"):
            raise PinError(f"{key}: dist_kind={pin.dist_kind!r} 未知")
        if pin.dist and pin.dist_kind == "pypi" and "==" not in pin.dist:
            raise PinError(f"{key}: PyPI 的 dist 要写成 name==version，实为 {pin.dist!r}")
        if pin.dist and pin.dist_kind == "npm" and "@" not in pin.dist[1:]:
            raise PinError(f"{key}: npm 的 dist 要写成 name@version，实为 {pin.dist!r}")
        if pin.dist_sha256 and not _HEX64.fullmatch(pin.dist_sha256):
            raise PinError(f"{key}: dist_sha256 不是 64 位 hex —— 版本号不是钉，字节摘要才是")
        if not pin.name:
            raise PinError(f"{key}: 既没有 pkg 也没有 dist")
        if pin.kind not in ("adapter", "harness"):
            raise PinError(f"{key}: kind={pin.kind!r} 未知")
        if pin.kind == "harness" and not pin.version_cmd:
            raise PinError(f"{key}: harness 必须给 version_cmd —— "
                           f"它没有我们 import 的符号，版本命令是唯一的核验点")
        if pin.kind == "adapter" and pin.version_cmd:
            raise PinError(f"{key}: adapter 不用 version_cmd，形状由 required_* 核")
        if not (pin.commit or pin.dist_sha256 or pin.dist_integrity):
            raise PinError(f"{key}: commit / dist_sha256 / dist_integrity 都没有 —— "
                           f"什么都没钉住")
        if pin.dist_integrity and not pin.dist_integrity.startswith(("sha512-", "sha256-")):
            raise PinError(f"{key}: dist_integrity 形状不对（npm 的是 `sha512-<base64>`）")
        # **来源一致性**：从 PyPI 装的，PyPI 声明的仓库必须就是 `repo`。
        if pin.dist:
            if not pin.dist_repo_url:
                raise PinError(
                    f"{key}: 从 PyPI 装却没记 dist_repo_url —— 同名不同项目是真实发生过的事"
                    f"（PyPI 的 tradingagents 属于 Mai0313，不是 TauricResearch）")
            if _norm_repo(pin.dist_repo_url) != _norm_repo(pin.repo):
                raise PinError(
                    f"{key}: repo={pin.repo} 与 PyPI 声明的 {pin.dist_repo_url} "
                    f"**是两个项目** —— 这条 Pin 会让论文说「我们跑了 X」而实际跑的是同名的另一个")
        if pin.commit:
            if not _HEX40.fullmatch(pin.commit):
                raise PinError(f"{key}: commit 不是 40 位 hex")
            if pin.commit_absent_reason:
                raise PinError(f"{key}: 有 commit 却写了缺失理由 —— 两者只能有一个")
        elif not pin.commit_absent_reason:
            raise PinError(
                f"{key}: commit 留空却没写理由。空着不解释，整条断言就退化成"
                f"「有这个仓库就行」——§10 明确禁止的那种")


def assert_upstream_shape(module, key: str, *, pin: "Pin | None" = None) -> None:
    """由**两个 adapter 模块在模块级**调用。形状没实测过就拒绝放行。

    `pin` 只给判别力测试注入用 —— 生产调用一律走 `PINS[key]`。
    """
    pin = pin or PINS[key]
    if pin.kind == "harness":
        raise PinError(
            f"{key} 是 harness 不是 adapter —— 它没有我们 import 的符号。"
            f"版本核对跑 `{' '.join(pin.version_cmd)}`（在容器里，"
            f"见 ops/run_f02_harness_smoke.sh）")
    missing = [n for n in ("required_attrs", "required_files", "required_state_keys")
               if getattr(pin, n) is None]
    if missing:
        raise PinError(
            f"{key} 的 {missing} 还没实测填写 —— §10：「在 f02 跑 probe_shapes()，"
            f"把 final_state 键、产物文件名与 conf 键**实测打印**出来再填，不许凭记忆填」。"
            f"注意不能填空元组充数：`all(x in got for x in ())` 恒真，那是空检查")
    if not pin.name:
        raise PinError(f"{key}: 既没有 pkg 也没有 dist —— 不知道该 import 什么")
    if pin.dist_kind == "npm":
        # npm 包不是 python 模块 —— 版本核对由 `ops/run_f02_harness_smoke.sh`
        # 在容器里跑 `<cmd> --version` 做。这里只核形状与来源。
        return
    got_version = _installed_version(pin.name)
    if pin.version and got_version is not None and got_version != pin.version:
        raise PinError(f"{key}: 装的是 {got_version}，钉的是 {pin.version}")
    for spec in pin.required_attrs:
        _resolve(spec, key)
    base = _package_dir(pin.name)
    if base is not None:
        miss = [f for f in pin.required_files if not (base / f).exists()]
        if miss:
            raise PinError(f"{key}: 上游包里少了 {miss} —— 文件名变了或包结构改了")


def _package_dir(name: str):
    import importlib
    try:
        mod = importlib.import_module(name)
    except ImportError:
        return None
    from pathlib import Path
    paths = list(getattr(mod, "__path__", []) or [])
    return Path(paths[0]) if paths else None


def _installed_version(dist: str) -> str | None:
    """版本取自**发行元数据**，不取 `module.__version__`。

    实测两个框架的顶层模块**都没有** `__version__`（rdagent 还是命名空间包，
    `__file__` 是 None）—— 依赖那个属性等于这条检查从来没跑过。
    """
    try:
        from importlib.metadata import PackageNotFoundError, version
        return version(dist)
    except Exception:
        return None


def _resolve(spec: str, key: str):
    """解析 `包.模块:属性.子属性`。

    用 `importlib` 而不是从顶层模块 `getattr` 下钻：`rdagent` 是**命名空间包**，
    `rdagent.utils` 在 import 之前根本不是它的属性 —— 从顶层下钻会把
    「还没 import」误报成「上游少了这个符号」。
    """
    import importlib
    mod_name, _, path = spec.partition(":")
    if not path:
        raise PinError(f"{key}: required_attrs 要写成 `模块:属性`，实为 {spec!r}")
    try:
        obj = importlib.import_module(mod_name)
    except ImportError as e:
        raise PinError(f"{key}: import {mod_name} 失败 —— {e}") from None
    for part in path.split("."):
        if not hasattr(obj, part):
            raise PinError(
                f"{key}: 上游少了 {spec} —— 现在炸在 import，"
                f"而不是炸成「这个 harness 做不了这个阶段」那条结论")
        obj = getattr(obj, part)
    return obj


def assert_state_keys(state, key: str) -> None:
    """跑完之后核 `final_state` 的键。上游改键名要在这里响。"""
    pin = PINS[key]
    if pin.required_state_keys is None:
        raise PinError(f"{key}: required_state_keys 未实测")
    missing = [k for k in pin.required_state_keys if k not in state]
    if missing:
        raise PinError(f"{key}: final_state 缺键 {missing}（上游改了键名？）")


assert_pins_wellformed()
