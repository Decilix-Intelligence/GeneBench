# -*- coding: utf-8 -*-
"""**突变自证**的统一跑板（D-29，2026-09-05 裁定补记）。

**为什么要收进仓库**：突变自证在 2026-09-05 说过一次谎 ——
`__pycache__` 里的旧字节码没清，pytest 跑的是**没突变的那份代码**，
4 个突变被报成「存活」。那一次谎报的方向是安全的（把杀死报成存活，逼我去补测试），
**但同一个机制可以反过来**：源码大小不变、mtime 落在同一秒，
一个**真的没被杀死**的突变会被报成「杀死」，而那份自证从此是假的。

因此这里把三条硬性做法固定下来：

1. 每次跑测试之前 `rmtree` 掉被突变模块的 `__pycache__`；
2. **显式断言突变已落地**（写回之后重读比对），不靠「替换函数返回了不同字符串」推断；
3. 报告附**落地证据** —— 被突变文件的 sha256 前后变化，并在还原后断言 sha 回到原值。

用法（写一个小脚本调它，不要再在 `/tmp` 里重抄一遍）::

    from ops.mutate import Mutation, run
    run([Mutation("门恒绿", "runner/f02/answer_plane_guard.py",
                  "    bad: list[str] = []", "    return []")],
        tests=["ops/test_answer_plane_guard.py"])
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
PYTHON = "/data/shared/genebench/env/bin/python"


@dataclass(frozen=True)
class Mutation:
    """一个突变。`old` 必须在文件里**恰好能找到**，否则记「没落地」而不是「存活」。"""

    name: str
    #: 仓库相对路径；**绝对路径也接受**（测试用 tmp_path 时需要）。
    path: str
    old: str
    new: str
    #: 第几处（`old` 出现多次时）。默认第 1 处。
    occurrence: int = 1


@dataclass
class Outcome:
    name: str
    landed: bool
    killed: bool
    sha_before: str
    sha_after: str
    summary: str
    failed_tests: list[str]

    @property
    def verdict(self) -> str:
        if not self.landed:
            return "**突变没落地**"
        return "杀死" if self.killed else "**存活**"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _apply(src: str, m: Mutation) -> str | None:
    """把第 `occurrence` 处 `old` 换成 `new`。找不到那一处 → `None`。"""
    idx, start = 0, 0
    for _ in range(m.occurrence):
        idx = src.find(m.old, start)
        if idx < 0:
            return None
        start = idx + 1
    return src[:idx] + m.new + src[idx + len(m.old):]


def _clear_pycache(path: Path) -> None:
    shutil.rmtree(path.parent / "__pycache__", ignore_errors=True)


def run(mutations: list[Mutation], *, tests: list[str], timeout: int = 300,
        quiet: bool = False) -> list[Outcome]:
    """逐个突变跑一遍测试。**无论成败都还原**，并断言还原成功。"""
    out: list[Outcome] = []
    for m in mutations:
        f = Path(m.path) if Path(m.path).is_absolute() else _REPO / m.path
        orig = f.read_text(encoding="utf-8")
        sha0 = _sha(orig)
        mutated = _apply(orig, m)
        if mutated is None or mutated == orig:
            out.append(Outcome(m.name, False, False, sha0[:10], sha0[:10],
                               "替换目标不存在（或替换后无变化）", []))
            continue
        f.write_text(mutated, encoding="utf-8")
        # ② 断言真的落到了磁盘上 —— 不靠推断
        assert f.read_text(encoding="utf-8") == mutated, f"{m.path} 写回没生效"
        sha1 = _sha(mutated)
        assert sha1 != sha0, "突变前后 sha 相同 —— 那不是一个突变"
        _clear_pycache(f)                                   # ① 缓存必须清
        try:
            r = subprocess.run([PYTHON, "-m", "pytest", *tests, "-q", "--no-header",
                                "-p", "no:cacheprovider"],
                               cwd=str(_REPO), capture_output=True, text=True, timeout=timeout)
            lines = r.stdout.splitlines()
            summary = next((l for l in reversed(lines)
                            if " passed" in l or " failed" in l), "?")
            failed = sorted({l.split("::")[1].split(" ")[0]
                             for l in lines if l.startswith("FAILED") and "::" in l})
            out.append(Outcome(m.name, True, bool(r.returncode), sha0[:10], sha1[:10],
                               summary, failed))
        finally:
            f.write_text(orig, encoding="utf-8")
            _clear_pycache(f)
            assert _sha(f.read_text(encoding="utf-8")) == sha0, f"{m.path} 还原失败"
    if not quiet:
        report(out)
    return out


def report(outcomes: list[Outcome]) -> None:
    """打印报告。**每条都带落地证据**（sha 变化），不只报杀死率。"""
    w = max((len(o.name) for o in outcomes), default=8)
    for o in outcomes:
        print(f"  {o.name:<{w}}  {o.verdict:<12}  sha {o.sha_before}→{o.sha_after}  "
              f"{o.summary} | {','.join(o.failed_tests[:2])}")
    bad = [o for o in outcomes if not o.landed or not o.killed]
    print(f"\n  共 {len(outcomes)} 个；**存活/没落地 {len(bad)}**"
          + (f"：{[o.name for o in bad]}" if bad else ""))


def main(argv=None) -> int:
    print(__doc__.split("用法")[0].strip()[:400], file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
