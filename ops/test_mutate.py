# -*- coding: utf-8 -*-
"""`ops/mutate.py` 的判据。

**自证工具本身也要有判别力。** 突变自证在 2026-09-05 说过一次谎
（`__pycache__` 没清，pytest 跑的是没突变的那份），
所以这里每一条都在问同一个问题：**这个跑板会不会报出假的结论。**
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from ops.mutate import Mutation, run

TARGET = '''def answer():
    return 42
'''
TESTSRC = '''from mod_under_test import answer


def test_answer():
    assert answer() == 42
'''


def _lab(tmp_path: Path) -> tuple[Path, list[str]]:
    """一个最小实验场：被突变的模块 + 盯着它的测试。"""
    (tmp_path / "mod_under_test.py").write_text(TARGET, encoding="utf-8")
    t = tmp_path / "test_mod.py"
    t.write_text(TESTSRC, encoding="utf-8")
    (tmp_path / "conftest.py").write_text(
        "import sys\nfrom pathlib import Path\n"
        "sys.path.insert(0, str(Path(__file__).parent))\n", encoding="utf-8")
    return tmp_path / "mod_under_test.py", [str(t)]


def test_a_landed_mutation_that_breaks_the_test_is_killed(tmp_path):
    mod, tests = _lab(tmp_path)
    (out,) = run([Mutation("改返回值", str(mod), "return 42", "return 43")],
                 tests=tests, quiet=True)
    assert out.landed and out.killed
    assert out.sha_before != out.sha_after, "报告里没有落地证据（sha 没变）"


def test_a_landed_mutation_that_the_tests_miss_is_a_survivor(tmp_path):
    """**存活**与**没落地**必须分得开 —— 混成一个就看不出是「测试不够」还是「脚本写错」。"""
    mod, tests = _lab(tmp_path)
    (out,) = run([Mutation("加一句无关代码", str(mod), "def answer():",
                           "def unused():\n    pass\n\n\ndef answer():")],
                 tests=tests, quiet=True)
    assert out.landed and not out.killed
    assert out.verdict == "**存活**"


def test_a_mutation_whose_target_is_absent_is_not_a_survivor(tmp_path):
    mod, tests = _lab(tmp_path)
    (out,) = run([Mutation("目标不存在", str(mod), "没有这一句", "x")], tests=tests, quiet=True)
    assert not out.landed and not out.killed
    assert out.verdict == "**突变没落地**"
    assert out.sha_before == out.sha_after


def test_the_file_is_restored_whatever_happens(tmp_path):
    mod, tests = _lab(tmp_path)
    before = hashlib.sha256(mod.read_bytes()).hexdigest()
    run([Mutation("改返回值", str(mod), "return 42", "return 43")], tests=tests, quiet=True)
    assert hashlib.sha256(mod.read_bytes()).hexdigest() == before, "跑完没还原"


def test_stale_bytecode_cannot_hide_a_mutation(tmp_path):
    """**这就是那次说谎的机制。**

    先让解释器把原始模块编译进 `__pycache__`，再跑突变。
    不清缓存的话，pytest 有可能加载旧字节码 —— 突变会被报成「存活」，
    而**同一个机制可以反过来**把没杀死的报成杀死。
    """
    mod, tests = _lab(tmp_path)
    import py_compile
    py_compile.compile(str(mod), doraise=True)
    cache = mod.parent / "__pycache__"
    assert cache.is_dir() and any(cache.iterdir()), "前提搭错：缓存没建出来"
    (out,) = run([Mutation("改返回值", str(mod), "return 42", "return 43")],
                 tests=tests, quiet=True)
    assert out.killed, "旧字节码把突变藏起来了 —— 跑板没清缓存"


def test_occurrence_selects_the_right_site(tmp_path):
    """同一句出现多次时，要能指定改第几处 —— 否则只能改第一处，覆盖不到别的分支。"""
    mod = tmp_path / "mod_under_test.py"
    mod.write_text("def a():\n    return 1\n\n\ndef b():\n    return 1\n", encoding="utf-8")
    t = tmp_path / "test_mod.py"
    t.write_text("from mod_under_test import a, b\n\n\ndef test_b():\n    assert b() == 1\n",
                 encoding="utf-8")
    (tmp_path / "conftest.py").write_text(
        "import sys\nfrom pathlib import Path\n"
        "sys.path.insert(0, str(Path(__file__).parent))\n", encoding="utf-8")
    first, second = [run([Mutation(f"第{i}处", str(mod), "    return 1", "    return 2",
                                   occurrence=i)], tests=[str(t)], quiet=True)[0]
                     for i in (1, 2)]
    assert first.landed and not first.killed, "改 a() 不该被只测 b() 的用例杀死"
    assert second.landed and second.killed, "改 b() 必须被杀死"
