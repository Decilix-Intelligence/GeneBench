"""适配器契约。两个框架各实现一遍，**共用同一个出口**。

出口只有一个（`build_artifact`），因为「适配层不得代 agent 做决定」这条纪律
只有落在**唯一出口**上才守得住：多一条旁路，多一处可以绕过 `origin` 的地方。
"""
from __future__ import annotations

import ast
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from runner.c42 import origin as OR
from runner.c42 import upstream_pins as UP

#: 容器里唯一挂出来的可写面。框架往这之外写的东西 `down -v` 之后就没了（§3.3）。
TASK_MOUNT = "/task"


class AdapterError(RuntimeError):
    pass


@dataclass
class FrameworkRun:
    """一次框架运行的**原始**产物位置。适配器在这上面做转录，不在这上面做判断。"""

    work_dir: Path
    stage: str
    task_id: str
    config_id: str
    arm: str
    exit_code: int = 0
    final_state: dict = field(default_factory=dict)
    outputs: dict[str, Path] = field(default_factory=dict)   # 逻辑名 → 文件
    emissions_path: Path | None = None
    stdout: str = ""


@dataclass
class Transcribed:
    """`(值, 来源)` —— 适配器交出来的东西。**没有第三个字段**：
    没有「我算的值」这一栏，算的东西走 `harness_values()` 落旁路。"""

    values: dict
    origins: dict


class Adapter(ABC):
    #: `upstream_pins.PINS` 的键。
    key: str = ""
    #: 这个框架能落哪些阶段。落不了的阶段不该有一条 `harness_error` 之外的记录。
    stages: frozenset[str] = frozenset()

    def __init__(self) -> None:
        if self.key not in UP.PINS:
            raise AdapterError(f"适配器 key={self.key!r} 不在 upstream_pins.PINS 里")

    # ---- 子类实现 ----

    @abstractmethod
    def declared_outputs(self) -> tuple[str, ...]:
        """框架往哪些**容器内绝对路径**写产物。

        由 `harvest.assert_outputs_under_mount()` 在**配置期**核。事后核不了 ——
        `down -v` 之后挂载外的字节已经没了，我们连「它曾经在那儿」都看不见。
        """

    @abstractmethod
    def run(self, ctx: dict) -> FrameworkRun: ...

    @abstractmethod
    def declarations(self, run: FrameworkRun) -> Transcribed:
        """**只转录 agent 自己写的字节**。框架配置（conf.yaml）的读数不许进这里 ——
        它走 `origin.config_provenance()` 落 provenance（§4.3）。"""

    @abstractmethod
    def payload(self, run: FrameworkRun) -> Transcribed: ...

    def harness_values(self, run: FrameworkRun) -> dict:
        """旁路证据（R 重算 / S 日志读数），交给 `origin.cross_check_all`。
        **不进 artifact**。默认什么都不给 —— 给不出就是 `unverified`，不是 `agree`。"""
        return {}

    # ---- 唯一出口 ----

    def build_artifact(self, run: FrameworkRun, *, profile: str | None = None) -> dict:
        decl = self.declarations(run)
        pay = self.payload(run)
        if run.stage not in self.stages:
            raise AdapterError(
                f"{self.key} 落不了 {run.stage} —— 强行产出一份 artifact 会让"
                f"「这个框架做不了这个阶段」变成「它做了但做错了」，那是两个结论")
        OR.check_declaration_origins(decl.origins)
        OR.assert_not_authored_unresolved(decl.values, decl.origins)
        declarations = OR.transcribe_declarations(decl.values, decl.origins)
        payload = OR.transcribe_payload(pay.values, pay.origins,
                                        stage=run.stage, profile=profile)
        return {
            # 信封由 harness 写是合法的（§5.2），但**只有信封**。
            "schema_version": "1.0", "stage": run.stage, "task_id": run.task_id,
            "config_id": run.config_id, "arm": run.arm,
            "declarations": declarations, "payload": payload,
        }


# --------------------------------------------------------------- 源码级扫描


def assert_no_native_data_path(pkg_dir, forbidden: dict[str, str],
                               *, allow: tuple[str, ...] = ()) -> None:
    """§11.2：原生数据源必须被**整体替换**。

    按 **AST** 找 import，不按 grep 找字符串 —— 注释里出现 `yfinance` 不算数据路径，
    而 `importlib.import_module("yf" + "inance")` 这种 grep 也抓不到（AST 同样抓不到，
    所以本函数**不是**唯一防线：§11.2 的「黑掉网关对照」查的是**结果**，两者都要有。
    一个查「配置对不对」，一个查「行为对不对」。
    """
    hits: list[str] = []
    for py in sorted(Path(pkg_dir).rglob("*.py")):
        rel = str(py.relative_to(pkg_dir))
        if any(re.fullmatch(a, rel) for a in allow):
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            mods: list[str] = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods = [node.module]
            for m in mods:
                top = m.split(".")[0]
                if top in forbidden:
                    hits.append(f"{rel}:{node.lineno} import {m} —— {forbidden[top]}")
    if hits:
        raise AdapterError(
            "原生数据路径还在（§11.2 要求整体替换为经网关的实现）：\n  "
            + "\n  ".join(hits[:20])
            + (f"\n  …共 {len(hits)} 处" if len(hits) > 20 else ""))


def assert_scan_is_not_vacuous(pkg_dir, forbidden: dict[str, str]) -> None:
    """**非空证明**：扫描器必须能在**未替换**的源码上命中。

    与卡 3.1 C1、§14.3 金丝雀非空证明同一条理由：扫不到不等于没有，
    也可能是扫描器在扫空。这条在替换**之前**跑一次，命中即证明扫描器活着。
    """
    try:
        assert_no_native_data_path(pkg_dir, forbidden)
    except AdapterError:
        return
    raise AdapterError(
        f"扫描器在 {pkg_dir} 上一处都没命中 —— 未替换的上游源码里必然有原生数据路径，"
        f"零命中说明扫描器在扫空，那么替换之后的「零命中」也不作数")
