"""pytest 会话级的进程收紧 —— 让"测试自己产出的目录"也守红线 5。

为什么需要这个文件
------------------
本机 umask 是 **002**。pytest 与 CPython 会在仓库里现建目录
(`.pytest_cache/`、`__pycache__/`),走的是 ``0o777 & ~umask`` → **0775**。
`ops/test_env.py::test_every_dir_under_root_blocks_group_and_world` 会递归审计
`$GENEBENCH_ROOT` 下每一个目录,如果不收紧 umask,**测试会因为自己刚建的缓存目录
而失败** —— 而且那个失败是真的:0775 的 `__pycache__` 里躺着 `scorer/` 的字节码。

所以这里在会话最早期把 umask 收到 `cfg.REQUIRED_UMASK`(0077)。
只影响本进程及其子进程,不写任何配置文件(红线 2)。

conftest.py 在 rootdir 被 pytest 最早加载(早于 cacheprovider 建 `.pytest_cache`),
是唯一能赶在缓存目录创建之前生效的位置。
"""

from __future__ import annotations

import sys
from pathlib import Path

# 仓库根就是本文件所在目录(pytest rootdir)。相对推导,不硬编码绝对路径。
_REPO_ROOT = Path(__file__).resolve().parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import genebench_config as cfg  # noqa: E402

#: 收紧前的 umask,留档给需要还原的场景(也让"本机是 002"这件事可被观测)。
PREVIOUS_UMASK: int = cfg.harden_umask()

# ---------------------------------------------------------------------------
# 收紧 umask 挡不住的那一个目录:**conftest 自己的字节码缓存**。
#
# CPython 是在 import 本文件的**那一刻**写 `__pycache__/conftest.*.pyc` 的 ——
# 比上面那行 `harden_umask()` 还早。于是 `repo/__pycache__` 会带着本机的 002
# umask 落成 **0775**,而它之后建的每一个目录都是 0700。
# 结果就是 `ops/test_env.py::test_every_dir_under_root_blocks_group_and_world`
# 在**缓存被清干净后的第一次跑**(全新 clone、`git clean`、手工 rm)必红,
# 而缓存还在时又是绿的 —— 一个只在干净环境下复现的假绿。卡 0.2 实测踩到。
#
# 先有鸡还是先有蛋,没法靠"更早调用"解决;只能在这里做一次**幂等收敛**:
# 已经存在的缓存目录统统 chmod 回 `REQUIRED_DIR_MODE`。`cfg.create_dir()`
# 对已存在的目录就是纯 chmod,正好干这个。
# ---------------------------------------------------------------------------
_CACHE_DIRS = [_REPO_ROOT / ".pytest_cache", *_REPO_ROOT.rglob("__pycache__")]

#: 本次收敛(chmod)了哪些目录,便于排查。
CONVERGED_CACHE_DIRS: list[str] = []
for _cache in _CACHE_DIRS:
    if not _cache.is_dir():
        continue
    if _cache.stat().st_mode & cfg.FORBIDDEN_MODE_BITS:
        CONVERGED_CACHE_DIRS.append(str(_cache))
    cfg.create_dir(_cache)


# --------------------------------------------------------------------------
# `lake` 标记（N-42 的兜底，2026-09-04）
# --------------------------------------------------------------------------
#: 触湖的测试单独归类。湖被 19 个爬虫持续写，只读锁会被抢 ——
#: 这类失败是**假红**，与真红混在一张清单里会训练人忽略红色，
#: 而 M6 的结算跑在同一套套件上。
#: 用法：`-m lake` 只跑触湖的，`-m "not lake"` 跳过它们。


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "lake: 触及 market_lake 的 duckdb catalog —— 失败可能是锁争用（假红），"
        "报告里与其他失败分开列",
    )
    config.addinivalue_line(
        "markers",
        "network: 需要外网（白名单条目可达性）—— 默认跳过。用 `-m network` 显式跑。"
        "不默认跑是因为一次网络抖动会变成一条假红，而这条测试要回答的是"
        "「这个域名到底能不能用」，抖动不是答案",
    )


def pytest_collection_modifyitems(config, items):
    """自动给触湖的测试打标 —— 靠人记得加标记，下一个新测试就会漏。

    顺带：`network` 标记的测试默认跳过（除非命令行显式 `-m network`）。
    """
    import pytest as _pytest
    if "network" not in (config.getoption("-m") or ""):
        _skip_net = _pytest.mark.skip(reason="需要外网；用 `-m network` 显式跑")
        for _it in items:
            if _it.get_closest_marker("network"):
                _it.add_marker(_skip_net)
    lake_files = ("test_qlib_provider", "test_universe", "test_lake",
                  "test_gateway", "test_env", "test_datahub", "test_tradability")
    for item in items:
        name = item.nodeid
        if any(f in name for f in lake_files):
            item.add_marker(_pytest.mark.lake)


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """把 lake 类失败与其他失败**分开列** —— 这是把假红与真红分开的兜底。"""
    failed = terminalreporter.stats.get("failed", [])
    if not failed:
        return
    lake_fail = [r for r in failed if "lake" in {m for m in getattr(r, "keywords", {})}]
    other = [r for r in failed if r not in lake_fail]
    tr = terminalreporter
    tr.write_sep("=", "失败分类（N-42）")
    tr.write_line(f"非湖类失败 {len(other)} 条 —— **这些是真红，必须查**")
    for r in other:
        tr.write_line(f"  {r.nodeid}")
    tr.write_line(f"触湖类失败 {len(lake_fail)} 条 —— 可能是 duckdb 只读锁争用；"
                  f"单跑复现一次再下结论，别直接当假红")
    for r in lake_fail:
        tr.write_line(f"  {r.nodeid}")
