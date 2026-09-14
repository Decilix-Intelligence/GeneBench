# -*- coding: utf-8 -*-
"""**oracle 的 I/O 契约锁**（裁定 2026-09-05 (b)）。

> oracle 的 I/O 契约 = agent 的 I/O 契约：读**标准位置**的任务规格、经**网关**取数、
> 写**标准 artifact 路径**，其余**不接受任何 stage 特定的 env/argv**。

**为什么要锁**：40 题的 oracle 一次都没跑过，于是七个阶段长出了**六套**互不相同的
调用约定 —— 光「artifact 写哪里」就有四个名字。它们从没冲突过，
因为没有一个被执行过。**没有锁的话，下一个人写第八套也不会有人知道。**

判据一律走 **AST**，不做文本 grep —— 本文件与规格里到处写着那些环境变量名，
文本判据会命中散文本身（D-25）。
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from reference.oracle_io import GATEWAY_ENV, OUT_ENV

REPO = Path(__file__).resolve().parents[1]
TPL = REPO / "genetask" / "templates"

#: **唯一**允许直接读的环境变量：网关地址是**部署事实**，不是任务事实。
#: 产出路径由 `oracle_io.context()` 统一处理，`solve.py` 自己不该再读它。
ALLOWED_ENV = frozenset({GATEWAY_ENV, OUT_ENV})

#: 骨架文件（`<stage>/base/solve.py`）不参与 —— 它们只有一句 `raise SystemExit`。
def _is_skeleton(src: str) -> bool:
    return "骨架" in src and len(src.splitlines()) < 12


def _solve_files() -> list[Path]:
    return sorted(p for p in TPL.rglob("solve.py") if not _is_skeleton(p.read_text(encoding="utf-8")))


def env_names(tree: ast.AST) -> set[str]:
    """AST 找 `os.environ[...]` / `os.environ.get(...)` 里的名字。"""
    out: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Subscript) and isinstance(n.value, ast.Attribute) \
                and n.value.attr == "environ":
            if isinstance(n.slice, ast.Constant) and isinstance(n.slice.value, str):
                out.add(n.slice.value)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and n.func.attr == "get" and isinstance(n.func.value, ast.Attribute) \
                and n.func.value.attr == "environ":
            if n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
                out.add(n.args[0].value)
    return out


def uses_argv(tree: ast.AST) -> bool:
    return any(isinstance(n, ast.Attribute) and n.attr == "argv" for n in ast.walk(tree))


def test_there_is_something_to_check():
    files = _solve_files()
    assert len(files) >= 30, f"只扫到 {len(files)} 个 solve.py —— 判据可能扫空了（恒绿）"


@pytest.mark.parametrize("p", _solve_files(), ids=lambda p: f"{p.parent.parent.name}/{p.parent.name}")
def test_no_stage_specific_env(p: Path):
    """**从任务目录读得出来的东西，一律不从环境拿。**

    env 里的那份可以与题面不一致，而没有任何东西会说 ——
    一个用 `GENEBENCH_WINDOW` 跑出来的 gold，窗口可以和 `task.yaml` 写的不是一个。
    """
    names = env_names(ast.parse(p.read_text(encoding="utf-8"), filename=str(p)))
    extra = sorted(names - ALLOWED_ENV)
    assert not extra, (
        f"{p.parent.parent.name}/{p.parent.name} 直接读了 {extra}；"
        f"只许 {sorted(ALLOWED_ENV)}，其余走 `reference.oracle_io.context(__file__)`")


@pytest.mark.parametrize("p", _solve_files(), ids=lambda p: f"{p.parent.parent.name}/{p.parent.name}")
def test_no_argv(p: Path):
    """`sys.argv` 也是 stage 特定入参 —— 换个调用方就散架。"""
    assert not uses_argv(ast.parse(p.read_text(encoding="utf-8"), filename=str(p))), \
        f"{p.parent.parent.name}/{p.parent.name} 还在用 sys.argv"


@pytest.mark.parametrize("p", _solve_files(), ids=lambda p: f"{p.parent.parent.name}/{p.parent.name}")
def test_obtains_context_from_the_standard_place(p: Path):
    """每个 oracle 都要**从标准位置**取上下文。"""
    src = p.read_text(encoding="utf-8")
    assert "oracle_io" in src and "_oracle_context(__file__)" in src, \
        f"{p.parent.parent.name}/{p.parent.name} 没有走 oracle_io 的统一契约"


# ---------------------------------------------------------------- 判别力
def test_the_env_detector_actually_detects(tmp_path):
    """喂一个真的读 stage 特定 env 的源码，判据必须命中 —— 否则上面三条是恒绿。"""
    src = ('import os\n'
           'A = os.environ["GENEBENCH_WINDOW_START"]\n'
           'B = os.environ.get("GENEBENCH_TASKSPEC", "x")\n'
           'C = os.environ.get("GENEBENCH_GATEWAY_URL", "y")\n')
    names = env_names(ast.parse(src))
    assert names == {"GENEBENCH_WINDOW_START", "GENEBENCH_TASKSPEC", "GENEBENCH_GATEWAY_URL"}
    assert sorted(names - ALLOWED_ENV) == ["GENEBENCH_TASKSPEC", "GENEBENCH_WINDOW_START"]


def test_the_argv_detector_actually_detects():
    assert uses_argv(ast.parse("import sys\nx = sys.argv[1]\n"))
    assert not uses_argv(ast.parse("x = 1\n"))


def test_the_allowed_set_is_derived_not_copied():
    """允许集从 `oracle_io` **引**，不抄 —— 抄一份会漂，漂了这道锁就名存实亡。"""
    import reference.oracle_io as OIO
    assert ALLOWED_ENV == frozenset({OIO.GATEWAY_ENV, OIO.OUT_ENV})


def test_skeletons_are_excluded_for_a_stated_reason():
    """豁免要能被证伪：骨架文件必须真的还是骨架。"""
    skel = [p for p in TPL.rglob("solve.py") if _is_skeleton(p.read_text(encoding="utf-8"))]
    assert skel, "一个骨架都没有 —— 豁免条件可能写错了"
    for p in skel:
        assert p.parent.name == "base", f"非 base 目录却被当成骨架豁免：{p}"


# ---------------------------------------------------------------- 自足性（D-31 推论，裁定 2026-09-05）

def template_imports(tree: ast.AST) -> set[str]:
    """AST 找出「import 了 `genetask.templates.…`」的模块名。"""
    out: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and (n.module or "").startswith("genetask.templates"):
            out.add(n.module)
        if isinstance(n, ast.Import):
            out |= {a.name for a in n.names if a.name.startswith("genetask.templates")}
    return out


@pytest.mark.parametrize("p", _solve_files(), ids=lambda p: f"{p.parent.parent.name}/{p.parent.name}")
def test_a_template_never_imports_another_template(p: Path):
    """**自足性也是契约的一部分**（D-31 推论）。

    S7 的四个 oracle 写着 `from genetask.templates.S7.cor_reproduce import solve` ——
    **模板 import 模板**。落到任务目录的那份因此不是自足的：
    被 import 的 trunk 永远从**模板目录**执行，`__file__` 指向模板，
    统一契约当场判「任务规格缺失」（2026-09-05 实测，S7 四题全倒）。

    共用主干要抽到 `reference/` 下的公共模块（S3 的 `s3_oracle_common` 就是），
    **不能靠 import 兄弟模板**。
    """
    bad = sorted(template_imports(ast.parse(p.read_text(encoding="utf-8"), filename=str(p))))
    assert not bad, (
        f"{p.parent.parent.name}/{p.parent.name} import 了模板 {bad} —— "
        f"共用主干抽到 reference/ 下，不要 import 兄弟模板（D-31 推论）")


def test_the_template_import_detector_actually_detects():
    """判别力：喂一段真的 import 兄弟模板的源码，判据必须命中。"""
    src = ("from genetask.templates.S7.cor_reproduce import solve as cor\n"
           "import genetask.templates.S3.cor01_wq006_corr.solve\n"
           "from reference.s3_oracle_common import run\n")
    got = template_imports(ast.parse(src))
    assert got == {"genetask.templates.S7.cor_reproduce",
                   "genetask.templates.S3.cor01_wq006_corr.solve"}
    assert "reference.s3_oracle_common" not in got, "误伤了 reference/ 下的公共层"
