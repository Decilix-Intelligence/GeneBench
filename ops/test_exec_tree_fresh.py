#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""卡 G10（用户裁定 ④）：**从零铺一棵执行面树，再在那棵树上跑一次注入冒烟。**

用户的纪律原话
--------------
> **「f02 上能跑靠的是历次手工遗留物；从零铺一遍才知道什么从没被交付过。」**

这道门要挡住的是哪一类失败
--------------------------
一台长期手工维护的机器上「能跑」，证明的是**这台机器**能跑，不是**这套交付物**能跑。
2026-09-14 第一次真的从零铺一遍（卡 F10），当场掉出三条**从来没有被交付过**的东西：

* **N-856**：`exec/vendor/h11` 不在仓库里，也没有任何文档化步骤会铺它 ——
  f02 上那份是 2026-09-05 手工跑容器测试留下的。而 `runner/c41/egress_proxy.py` 是
  **模块级** `import h11`，于是**一棵从零铺的执行面 import 不了整棵 runner**；
* **N-857**：`ops/guard_modes.py` 模块级 `import genebench_config`，而 exec 白名单不含它 ——
  f02 上双机当时能跑，只因为那棵 exec 树是 2026-09-10 的旧版；
* **N-881**：`mkdir -m 700 -p "$DEST/$d"` 的 `-m` 只作用在最后一段，`$DEST` 根自己吃
  umask 落成 0775 —— 既有那棵 `exec/` 是 2026-09 手工 `mkdir` 出来的 0700，所以**永远不显形**。

三条的共同形状与 `ops/specs/design_notes.md` 的 **D-06** 家族同源，而且是它的**时间维**：
D-06 那一支是「判据取决于跑它的是不是发布方那台机器」，这一条是
「判据取决于**这台机器历史上被手工修过什么**」。逐条写在 design_notes 的 **D-34**。

判据形状（**两半，缺一不可**）
------------------------------
**上半：真铺、真跑。** 每次都把执行面树铺进一棵**这一刻才出现的目录**
（`tmp_path`，铺之前断言它不存在），然后用**执行面自己那个解释器**
（`runner.placement.runner_py()`，默认 `python3`）跑四段冒烟：

  * **A** —— 整棵 runner import 得起来，且 `h11` 来自**这棵树自己的** `vendor/`（N-856）；
  * **B** —— `runner.inject.preflight(check_modes=True)` 返回空（N-857 / N-881）；
  * **C** —— 执行面真用的 provider 父目录 == 数据面探针扫的那一个（N-855）；
  * **D** —— `ops/run_f02_a1.py --dry` 全量注入 P0–P9 + 公平性逐条比臂。

四段一律 **`cwd` 在仓库之外**跑。这不是讲究：`cwd` 在仓库里时 `genebench_config`
从当前目录就 import 得到，`CONFIG_AVAILABLE` 变成 `True`，**N-857 的现场就复现不出来**
（本文件写就的当天实测过一次，差点把一条空判据当成绿的）。

**下半：判别力自证。** 把卡 F10 修掉的那几条**逐条注入回一棵临时副本**，
每一条都必须让对应那一段**当场红**；同一棵副本不注入时同一段必须**绿**
（否则「红」证明不了任何东西）。副本用完即弃，仓库原文件**逐字节零改动**——
每条都在断言里核过 sha256。这与 D-06 第 11 例（`assert_mutated`）是同一条纪律：
**靠注入证明判别力的测试，先要证明自己真的注入了。**

两种形态都覆盖
--------------
* **单机**：`runner/placement.py --place-exec` —— 本机落位，**无 ssh**，每台机器都能跑；
* **双机**：`ops/push_exec_to_f02.sh` —— 那条路上「从零铺一遍」靠的是三步
  （h11 随树船运 / `$DEST` 根收权限 / 第 0 步解释器核查），本文件把这三步**逐条钉住**，
  每条配一面反证（从脚本正文里删掉那一行 → 该条必红）。**真推**那一半是
  **显式 opt-in**（见 `GENEBENCH_FRESH_EXEC_PARENT`）：一次 `pytest` 不该在没人要求的时候
  往另一台机器上推东西。

**skip 不是绿**：前置缺了哪一件，`test_这道门这次到底跑到了哪里` 会**逐条**打出来。

跑法::

    ulimit -n 8192
    PYTHONDONTWRITEBYTECODE=1 python -m pytest -p no:cacheprovider ops/test_exec_tree_fresh.py -q
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PY = sys.executable
PUSH_EXEC_SH = REPO / "ops" / "push_exec_to_f02.sh"

if str(REPO) not in sys.path:                       # 让 `from runner import …` 在裸 pytest 下也成立
    sys.path.insert(0, str(REPO))

from runner import placement as PL                  # noqa: E402

#: 卡 F10 那次改到的、本门要保证**零改动**的仓库文件。
#: 注入只许发生在副本里 —— 这张表是它的反面证明。
UNTOUCHED: tuple[str, ...] = (
    "ops/guard_modes.py",
    "ops/run_f02_a1.py",
    "runner/placement.py",
    "runner/c41/egress_proxy.py",
    "ops/push_exec_to_f02.sh",
)


def _digest(rels: tuple[str, ...] = UNTOUCHED) -> dict[str, str]:
    return {r: hashlib.sha256((REPO / r).read_bytes()).hexdigest() for r in rels}


# ===========================================================================
# 前置：**缺了就大声说**（skip 不是绿）
# ===========================================================================

def _exec_py() -> str:
    """执行面那个解释器 —— 就是真跑会用的那一个，不换成 `sys.executable`。

    换成 `sys.executable` 会把 N-856 整条遮掉：发布方的 venv 里本来就有 h11，
    而执行面上**只有**这棵树的 `vendor/` 里那一份。
    """
    return PL.runner_py()


def missing_preconditions() -> list[str]:
    """铺一棵全新执行面树、并在上面跑 A/B/C 三段，缺哪一件。"""
    miss: list[str] = []
    if shutil.which("rsync") is None:
        miss.append("没有 `rsync` —— `runner/placement` 与 `ops/push_exec_to_f02.sh` 都用它同步")
    epy = _exec_py()
    if shutil.which(epy) is None and not Path(epy).is_file():
        miss.append(f"执行面解释器 `{epy}` 不在 PATH 上 —— "
                    f"要么装上，要么把 `{PL.RUNNER_PY_ENV}` 指到你要用的那个")
    else:
        p = subprocess.run([epy, "-c", "import sys; print(sys.version_info[:2])"],
                           capture_output=True, text=True, timeout=120)
        if p.returncode != 0:
            miss.append(f"执行面解释器 `{epy}` 跑不起来：{(p.stderr or '')[:200]}")
    return miss


@pytest.fixture(scope="module")
def preconditions() -> list[str]:
    return missing_preconditions()


@pytest.fixture(scope="module")
def fresh_tree(tmp_path_factory, preconditions) -> dict:
    """铺一棵**这一刻才出现的**执行面树，返回 `{root, dest, laid}`。

    「全新」是判据本身，所以铺之前断言它**不存在**：既有那棵树上四段全绿说明不了什么 ——
    它靠的正是历次手工遗留物。
    """
    if preconditions:
        pytest.skip("从零铺一棵执行面树的前置没齐（逐条）：\n  - " + "\n  - ".join(preconditions))
    root = tmp_path_factory.mktemp("gb_fresh") / "root"
    assert not root.exists(), f"{root} 已经在了 —— 这道门要的是一棵**全新**的树"
    root.mkdir(mode=0o700)
    dest = root / "genebench_runner" / "exec"
    assert not dest.exists(), "落点在铺之前就存在 —— 那就不是「从零」了"
    env = dict(os.environ, GENEBENCH_ROOT=str(root), GENEBENCH_TOPOLOGY=PL.SINGLE,
               PYTHONDONTWRITEBYTECODE="1")
    env.pop(PL.RUNNER_ROOT_ENV, None)
    env.pop("PYTHONPATH", None)
    p = subprocess.run([PY, "-m", "runner.placement", "--topology", PL.SINGLE,
                        "--place-exec", "--with-launch-data"],
                       cwd=str(REPO), env=env, capture_output=True, text=True, timeout=1800)
    assert p.returncode == 0, (
        "从零铺执行面树就失败了 —— 这正是这道门要抓的那一类：\n"
        f"{p.stdout[-3000:]}\n{p.stderr[-3000:]}")
    laid = json.loads(p.stdout[p.stdout.index("{"):])
    assert Path(laid["dest"]) == dest, laid
    return {"root": root, "dest": dest, "laid": laid}


def _seg_env(root: Path) -> dict[str, str]:
    """执行面那一侧的环境：单机形态**必须**把执行面根钉进进程环境
    （`ops/run_joblist.py` 在单机分支就是这么做的），否则 `runner_core.ROOT`
    回落到双机默认值。"""
    env = dict(os.environ, GENEBENCH_ROOT=str(root), GENEBENCH_TOPOLOGY=PL.SINGLE,
               PYTHONDONTWRITEBYTECODE="1")
    env[PL.RUNNER_ROOT_ENV] = str(root / "genebench_runner")
    env.pop("PYTHONPATH", None)
    return env


# ===========================================================================
# 四段冒烟。**每段一个独立退码**，和卡 F10 在 f02 上手跑的那份 A/B/C/D 同形。
# ===========================================================================

_SEG_A = """
import sys
sys.path.insert(0, "__TREE__")
from runner import inject, run_loop, registry            # noqa: F401
from runner.c41 import runner_core, egress_proxy         # noqa: F401
h = egress_proxy.h11
assert h.__file__.startswith("__TREE__"), "h11 不是这棵树自己的那一份：" + str(h.__file__)
assert runner_core.PLACEHOLDER_KEY_LITERAL, "runner_core 没拿到边车占位量"
print("A 绿 | h11", h.__version__, "|", h.__file__)
"""

_SEG_B = """
import sys
sys.path.insert(0, "__TREE__")
from pathlib import Path
from runner import inject as INJ
g = INJ._load_guard()
print("CONFIG_AVAILABLE =", g.CONFIG_AVAILABLE)
print("roots =", [str(x) for x in g.roots()])
bad = INJ.preflight(Path("__P0__"), require_docker=False, check_modes=True)
print("P0 =", bad if bad else "[] 绿")
raise SystemExit(1 if bad else 0)
"""

_SEG_C = """
import sys
sys.path.insert(0, "__TREE__")
from ops import run_f02_a1 as A1
rr = A1.runner_root()
pp = A1.RUNNER_PROVIDER_ROOT
print("runner_root =", rr)
print("provider_parent =", pp)
if pp != rr / "provider":
    print("[红] 执行面真用的 provider 父目录与探针扫的那一个不同源")
    raise SystemExit(1)
print("C 绿", rr)
"""

SEGMENTS: dict[str, str] = {"A": _SEG_A, "B": _SEG_B, "C": _SEG_C}
SEG_SAYS = {
    "A": "整棵 runner 在这棵树上 import 得起来，h11 来自树自己的 vendor/（N-856）",
    "B": "P0 前置自检 `preflight(check_modes=True)` 返回空（N-857 / N-881）",
    "C": "执行面真用的 provider 父目录 == 数据面探针扫的那一个（N-855）",
}


def run_segment(name: str, tree: Path, root: Path) -> subprocess.CompletedProcess:
    """跑一段冒烟。**`cwd` 一律在仓库之外** —— 否则 `genebench_config` 从当前目录
    就 import 得到，N-857 的现场根本复现不出来。"""
    src = SEGMENTS[name].replace("__TREE__", str(tree)).replace("__P0__", str(root / "p0"))
    return subprocess.run([_exec_py(), "-c", src], cwd=str(root), env=_seg_env(root),
                          capture_output=True, text=True, timeout=900)


def _fmt(p: subprocess.CompletedProcess) -> str:
    return f"rc={p.returncode}\n--- stdout ---\n{p.stdout[-2500:]}\n--- stderr ---\n{p.stderr[-2500:]}"


@pytest.mark.parametrize("seg", sorted(SEGMENTS), ids=[f"段{s}" for s in sorted(SEGMENTS)])
def test_全新执行面树上冒烟四段(seg: str, fresh_tree):
    p = run_segment(seg, fresh_tree["dest"], fresh_tree["root"])
    assert p.returncode == 0, (
        f"一棵**从零铺的**执行面树上，冒烟 {seg} 段不绿 —— {SEG_SAYS[seg]}\n"
        f"（既有那棵树上它可能是绿的：那说明不了什么，绿的是历次手工遗留物）\n{_fmt(p)}")


def test_段A的h11确实来自这棵树而不是发布方环境(fresh_tree):
    """N-856 的正面证据：`vendor/h11` **随树船运**，不是靠机器上碰巧装了它。"""
    v = fresh_tree["dest"] / "vendor" / "h11" / "__init__.py"
    assert v.is_file(), f"从零铺的树里没有 {v} —— h11 又一次没被交付"
    p = run_segment("A", fresh_tree["dest"], fresh_tree["root"])
    assert p.returncode == 0, _fmt(p)
    assert str(fresh_tree["dest"]) in p.stdout, p.stdout


def test_段B在一棵拿不到发布方配置的树上跑(fresh_tree):
    """N-857 的现场条件：执行面上 `genebench_config` **本来就不该在**。

    这一条同时钉住上面那个 `cwd` 取舍 —— 它一旦被人「顺手改回仓库根」，
    `CONFIG_AVAILABLE` 会变成 `True`，B 段就退化成一条空判据。
    """
    p = run_segment("B", fresh_tree["dest"], fresh_tree["root"])
    assert p.returncode == 0, _fmt(p)
    assert "CONFIG_AVAILABLE = False" in p.stdout, (
        "执行面这一侧居然拿到了发布方配置 —— 这一段跑的现场不对（`cwd` 落在仓库里了？）：\n"
        + _fmt(p))
    assert str(fresh_tree["dest"]) in p.stdout, (
        "守门没把注入器自己这棵树列进审计根：\n" + _fmt(p))


def test_段C两侧同源_数据面探针与执行面读的是同一棵树(fresh_tree):
    """N-855：执行面真用的 provider 父目录，与 `ops/run_joblist.probe_f02_provider`
    扫的那一个，必须是**同一个值**。两处不同源时**两边都不报错** —— 这才是它的危险处。"""
    root = fresh_tree["root"]
    p = run_segment("C", fresh_tree["dest"], root)
    assert p.returncode == 0, _fmt(p)
    q = subprocess.run(
        [PY, "-c", "from ops import run_joblist as RJ; print(RJ.runner_root('single'))"],
        cwd=str(REPO), env=_seg_env(root), capture_output=True, text=True, timeout=600)
    assert q.returncode == 0, _fmt(q)
    probe_root = q.stdout.strip()
    assert probe_root in p.stdout, (
        f"数据面探针扫 {probe_root}，执行面读的却是另一棵：\n{_fmt(p)}")


# ===========================================================================
# D 段：`--dry` 全量注入。缺 bundle 就**逐条**说清怎么造一个。
# ===========================================================================

#: 显式指一个已出集的 X 面 bundle 暂存目录（里面是 `tasks/<id>/` 与 `<id>.manifest.json`）。
BUNDLE_ENV = "GENEBENCH_FRESH_SMOKE_BUNDLE"
#: 显式指一份 provider 根（`--dry` 只用来把路径填进注入器，不判同源）。
PROVIDER_ENV = "GENEBENCH_FRESH_SMOKE_PROVIDER"


def _data_root() -> Path:
    import genebench_config as cfg
    return cfg.GENEBENCH_ROOT


def _provider_by_channel() -> tuple[str, Path] | None:
    """把一份 provider 根**配到它自己那条通道**上。

    钉子表里存的是**前缀**（`private` 8 位、`public` 16 位），所以这里按前缀比 ——
    与 `runner/inject.py` 的 P2 同一个口径。

    为什么不能随手拿一份：注入器 P2 比的是「这棵 provider 的根 sha256 == 该通道的冻结钉子」。
    本门第一次写就时随手取了 `snapshots/*/qlib_provider` 里的第一个，配上一个私有通道的
    bundle —— P2 当场红成「provider 变了（N-23 的 v1.1 重建？）」，而 provider 一点问题都没有。
    那正是 `provider_pin_expect` 的 docstring 警告过的那种误导。所以这里**按钉子反查通道**。
    """
    from genetask import pin
    from runner import inject as INJ
    snaps = _data_root() / "snapshots"
    cands = sorted(snaps.glob("*/qlib_provider")) if snaps.is_dir() else []
    pv = (os.environ.get(PROVIDER_ENV) or "").strip()
    if pv:
        cands = [Path(pv)]
    for ch in sorted(INJ.provider_pin_by_channel()):
        want = INJ.provider_pin_expect(ch)
        for d in cands:
            if not d.is_dir():
                continue
            try:
                if pin.provider_root_sha256(d).startswith(want):
                    return ch, d
            except Exception:                       # noqa: BLE001 —— 算不出来就换下一份
                continue
    return None


def find_dry_inputs() -> tuple[tuple[Path, Path] | None, tuple[str, Path] | None, list[str]]:
    """找 `--dry` 要的 bundle 与 (通道, provider)。找不到就**逐条**说缺什么、怎么补。"""
    why: list[str] = []
    bundle: tuple[Path, Path] | None = None
    stages: list[Path] = []
    v = (os.environ.get(BUNDLE_ENV) or "").strip()
    if v:
        stages = [Path(v)]
    else:
        st = _data_root() / "staging"
        stages = sorted(p for p in st.iterdir() if p.is_dir()) if st.is_dir() else []
    for s in stages:
        for m in sorted(s.glob("*.manifest.json")):
            d = s / "tasks" / m.name[: -len(".manifest.json")]
            if d.is_dir():
                bundle = (d, m)
                break
        if bundle:
            break
    if bundle is None:
        why.append(f"找不到一个已出集的 X 面 bundle（`<暂存目录>/tasks/<task_id>/` + "
                   f"`<暂存目录>/<task_id>.manifest.json`）。造一个：`ops/export_bundle.py`；"
                   f"或者把暂存目录指过来：`{BUNDLE_ENV}=<目录>`")
    got = _provider_by_channel()
    if got is None:
        why.append(f"找不到一份**根 sha256 与某条通道的冻结钉子对得上**的 provider 根"
                   f"（`<数据根>/snapshots/*/qlib_provider`）。按 README §2.1a ③ 落位，"
                   f"或者 `{PROVIDER_ENV}=<目录>` 指过来")
    return bundle, got, why


def run_segment_D(tree: Path, root: Path, bundle: tuple[Path, Path],
                  provider: tuple[str, Path], run_root: Path) -> subprocess.CompletedProcess:
    d, m = bundle
    ch, pdir = provider
    return subprocess.run(
        [_exec_py(), str(tree / "ops" / "run_f02_a1.py"), "--dry",
         "--bundle", str(d), "--manifest", str(m), "--channel", ch,
         "--config-id", "cfg-codex-deepseek", "--arms", "strict,open",
         "--run-root", str(run_root), "--provider-root", str(pdir)],
        cwd=str(root), env=_seg_env(root), capture_output=True, text=True, timeout=1800)


def test_段D全量注入冒烟(fresh_tree, tmp_path):
    """`--dry`：P0–P9 全走一遍 + `work/` 装配 + 公平性逐条比臂。**不起容器、不调模型、不读凭据。**"""
    bundle, provider, why = find_dry_inputs()
    if why:
        pytest.skip("D 段（`--dry` 全量注入）的输入没齐（逐条）：\n  - " + "\n  - ".join(why)
                    + "\n**这是 skip，不是绿** —— A/B/C 三段与判别力自证不受影响。")
    p = run_segment_D(fresh_tree["dest"], fresh_tree["root"], bundle, provider, tmp_path / "dry")
    assert p.returncode == 0, (
        "从零铺的执行面树上 `--dry` 全量注入不过：\n" + _fmt(p))
    assert "[绿]" in p.stdout, "公平性比臂那一条没打出绿：\n" + _fmt(p)


# ===========================================================================
# 判别力自证：把卡 F10 修掉的缺陷**逐条注入回一棵临时副本**，每条必须当场红
# ===========================================================================

_ANCHOR_857 = ("try:\n    import genebench_config as _cfg")
_ANCHOR_855 = 'RUNNER_PROVIDER_ROOT = runner_root() / "provider"'


def _rewrite(path: Path, old: str, new: str, *, what: str) -> str:
    """在副本里做一次**有据可查**的改写。改不动就红 —— 「注入了什么都没改」与恒绿同族
    （D-06 第 11 例：`assert_mutated`）。"""
    before = path.read_text(encoding="utf-8")
    assert old in before, f"注入 {what} 失败：副本里找不到锚点 {old!r} —— 锚点漂了，先修这道门"
    after = before.replace(old, new, 1)
    assert after != before, f"注入 {what} 之后副本逐字节没变 —— 这条反证是空的"
    path.write_text(after, encoding="utf-8")
    return f"{path.name}: {what}"


def inject_856(tree: Path, root: Path) -> str:
    """N-856：**h11 从来没被交付过** —— 把随树船运的那一份拿走，回到 f02 上
    「靠 2026-09-05 手工遗留物」之前的世界。"""
    v = tree / "vendor" / "h11"
    assert v.is_dir(), "副本里本来就没有 vendor/h11 —— 这条反证是空的"
    shutil.rmtree(v)
    return "删掉 vendor/h11（= 它从来没被交付过）"


def inject_857(tree: Path, root: Path) -> str:
    """N-857：把守门的 `genebench_config` 改回**模块级**（无条件）import。"""
    return _rewrite(tree / "ops" / "guard_modes.py",
                    _ANCHOR_857,
                    "if True:\n    import genebench_config as _cfg",
                    what="守门改回模块级 import genebench_config（N-857）")


def inject_881(tree: Path, root: Path) -> str:
    """N-881：把全新执行面树的**根自己**放成 0775 —— `mkdir -m 700 -p "$DEST/$d"`
    没收紧 `$DEST` 时就是这个样子。"""
    tree.chmod(0o775)
    assert tree.stat().st_mode & 0o077, "副本根没真的放开 —— 这条反证是空的"
    return "把树根 chmod 0775（= `$DEST` 根吃了 umask）"


def inject_855(tree: Path, root: Path) -> str:
    """N-855：把执行面的 provider 父目录改回**发布方那台的写死值**，与探针不再同源。"""
    new = ('RUNNER_PROVIDER_ROOT = __import__("pathlib").Path(\n'
           '    __import__("runner.placement_dual", fromlist=["x"]).RUNNER_ROOT_DEFAULT) / "provider"')
    return _rewrite(tree / "ops" / "run_f02_a1.py", _ANCHOR_855, new,
                    what="provider 父目录改回发布方写死值（N-855）")


#: **逐条闭集**：卡 F10 修掉的每一条，配一面反证。`(编号, 注入器, 打哪一段, 说的是什么)`
DEFECTS: tuple[tuple[str, object, str, str], ...] = (
    ("N-856", inject_856, "A", "exec/vendor/h11 从来没被交付过"),
    ("N-857", inject_857, "B", "守门模块级 import genebench_config，执行面上没有它"),
    ("N-881", inject_881, "B", "全新 $DEST 根落成 0775"),
    ("N-855", inject_855, "C", "provider 父目录写死，与数据面探针不同源"),
)


@pytest.fixture
def tree_copy(fresh_tree, tmp_path) -> Path:
    dst = tmp_path / "copy"
    shutil.copytree(fresh_tree["dest"], dst, symlinks=True)
    return dst


@pytest.mark.parametrize("nid,inject,seg,says", DEFECTS, ids=[d[0] for d in DEFECTS])
def test_把卡F10修掉的缺陷逐条注入回副本_对应那一段必须当场红(
        nid: str, inject, seg: str, says: str, tree_copy: Path, fresh_tree):
    """**判别力自证。** 没有这一组，上面那四段绿了也说明不了什么。"""
    before = _digest()
    ok = run_segment(seg, tree_copy, fresh_tree["root"])
    assert ok.returncode == 0, (
        f"**没注入**的同一棵副本上 {seg} 段就已经不绿了 —— 那么下面这条「红」证明不了任何东西：\n"
        + _fmt(ok))
    what = inject(tree_copy, fresh_tree["root"])
    bad = run_segment(seg, tree_copy, fresh_tree["root"])
    assert bad.returncode != 0, (
        f"把 {nid}（{says}）注入回副本之后，{seg} 段**照样绿** —— 这道门拦不住它。\n"
        f"注入的是：{what}\n{_fmt(bad)}")
    assert _digest() == before, "注入跑到仓库原文件上去了 —— 副本没隔离干净"


def test_注入只发生在副本里_仓库原文件零改动(fresh_tree, tmp_path):
    """把四条一次全注进同一棵副本，再核仓库那五个文件逐字节没动。"""
    before = _digest()
    dst = tmp_path / "all"
    shutil.copytree(fresh_tree["dest"], dst, symlinks=True)
    did = [inject(dst, fresh_tree["root"]) for _nid, inject, _s, _w in DEFECTS]
    assert len(did) == len(DEFECTS)
    shutil.rmtree(dst, ignore_errors=True)
    assert _digest() == before, "仓库原文件被动过了"


# ===========================================================================
# 双机形态：「从零铺一遍」在 `ops/push_exec_to_f02.sh` 上靠的是这三步
# ===========================================================================

#: **逐条闭集**，不是通用扫描：一棵**全新**的执行面目录能起来，靠的就是这三步。
#: 每条 = `(编号, 说的是什么, 正文里必须有的锚点)`。
FRESH_STEPS: tuple[tuple[str, str, str], ...] = (
    ("N-856", "h11 随 exec 树船运（唯一实现在 runner/placement.stage_vendor）",
     r"runner\.placement --stage-vendor"),
    ("N-881", "$DEST 根自己收成 0700（`-m 700` 只作用在最后一段）",
     r"chmod go-rwx \$\(printf %q \"\$DEST\"\)"),
    ("N-851", "第 0 步先核解释器在不在，而不是走到第 3 步才 rc=127",
     r"if \[ ! -x \"\$PY\" \]"),
)

PUSH_TEXT = PUSH_EXEC_SH.read_text(encoding="utf-8") if PUSH_EXEC_SH.is_file() else ""


def fresh_steps_missing(text: str) -> list[str]:
    """判据本体：写成函数，好让反证拿一份**改坏了的副本文本**喂进来。"""
    return [f"{nid}：{says}（找不到 /{pat}/）"
            for nid, says, pat in FRESH_STEPS if not re.search(pat, text)]


@pytest.mark.parametrize("nid,says,pat", FRESH_STEPS, ids=[s[0] for s in FRESH_STEPS])
def test_双机推送脚本带着从零铺一遍要的那三步(nid: str, says: str, pat: str):
    assert PUSH_TEXT, f"{PUSH_EXEC_SH} 读不到"
    assert re.search(pat, PUSH_TEXT), (
        f"`ops/push_exec_to_f02.sh` 里找不到 {nid} 那一步：{says}。\n"
        f"没有它，这个脚本只能往**已经被人手工修过**的目录上推 —— "
        f"一棵全新的执行面目录推完起不来。")


@pytest.mark.parametrize("nid,says,pat", FRESH_STEPS, ids=[s[0] for s in FRESH_STEPS])
def test_反证_从脚本副本里删掉那一行判据必须红(nid: str, says: str, pat: str):
    """判别力自证：把这一步从**一份临时副本文本**里拿掉，`fresh_steps_missing` 必须点它的名。"""
    broken = re.sub(pat, "（本行在副本里被删掉了）", PUSH_TEXT)
    assert broken != PUSH_TEXT, f"副本没真的改动 —— {nid} 这条反证是空的"
    hits = fresh_steps_missing(broken)
    assert any(h.startswith(nid) for h in hits), (
        f"删掉 {nid} 那一步之后判据照样不红 —— 它是一条空判据。现有命中：{hits}")
    assert not fresh_steps_missing(PUSH_TEXT), "原文上判据就不绿"


def test_这三步的顺序_h11进staging在扫描之前_DEST收权限在同步之前():
    """顺序也是判据的一部分：h11 要跟着过第 2/3 步那两道扫描，
    `$DEST` 要在第 4 步 rsync **之前**就已经是 0700。"""
    i_vendor = PUSH_TEXT.index("--stage-vendor")
    i_scan2 = PUSH_TEXT.index("== 2/6")
    i_chmod = PUSH_TEXT.index("chmod go-rwx")
    i_sync = PUSH_TEXT.index("== 4/6")
    assert i_vendor < i_scan2, "h11 铺在禁段/禁名扫描之后 —— 它就绕过了那两道门"
    assert i_chmod < i_sync, "$DEST 根收权限排在同步之后 —— 中间那一段仍然是 0775"


# ===========================================================================
# 双机真推：**显式 opt-in**。一次 pytest 不该在没人要求时往另一台机器上推东西。
# ===========================================================================

#: 指一个**父目录**（在执行面那台机器上）。本门会在它下面造一个**这一刻才出现的**子目录、
#: 推完、跑完冒烟、然后把那个子目录删掉。既有的 `exec/` 一个字节都不碰。
FRESH_PARENT_ENV = "GENEBENCH_FRESH_EXEC_PARENT"


def _ssh(host: str, inner: str, timeout: int = 1800) -> subprocess.CompletedProcess:
    return subprocess.run(["ssh", "-o", "ConnectTimeout=120", host, inner],
                          capture_output=True, text=True, timeout=timeout)


def dual_preconditions() -> tuple[str | None, str | None, list[str]]:
    why: list[str] = []
    parent = (os.environ.get(FRESH_PARENT_ENV) or "").strip() or None
    host = (os.environ.get("GENEBENCH_F02") or "").strip() or None
    if parent is None:
        why.append(f"没设 `{FRESH_PARENT_ENV}`（执行面上的一个父目录）—— "
                   f"**这一半是显式 opt-in**：一次 pytest 不该在没人要求的时候往另一台机器上推东西")
    if host is None:
        why.append("没设 `GENEBENCH_F02`（`<你>@<执行面主机>`）")
    if shutil.which("ssh") is None:
        why.append("没有 `ssh`")
    if not why:
        p = _ssh(host, "echo ok", timeout=300)          # type: ignore[arg-type]
        if p.returncode != 0 or "ok" not in p.stdout:
            why.append(f"`ssh {host}` 不通：{(p.stderr or '')[:200]}")
    return parent, host, why


def test_双机真推到一棵全新目录再跑冒烟(tmp_path):
    """裁定 ④ 的双机那一半：推到一棵**不存在的**目录，推完在那棵树上跑 A/B/C。

    为什么必须是全新的目录：既有那棵 `exec/` 上四段全绿说明不了什么 ——
    它靠的是历次手工遗留物（h11 是手工复制的、根的 0700 是手工 `mkdir` 的）。
    """
    parent, host, why = dual_preconditions()
    if why:
        pytest.skip("双机真推那一半没跑（逐条）：\n  - " + "\n  - ".join(why)
                    + "\n**这是 skip，不是绿** —— 单机那一半与判别力自证照跑。")
    import time
    dest = f"{parent.rstrip('/')}/exec_fresh_{time.strftime('%Y%m%dT%H%M%S')}"
    assert _ssh(host, f"test -e {dest}").returncode != 0, \
        f"{dest} 已经在了 —— 这道门要的是一棵**全新**的目录"
    stage = tmp_path / "exec_push"
    env = dict(os.environ, GENEBENCH_EXEC_DEST=dest, GENEBENCH_EXEC_STAGE=str(stage),
               PYTHONDONTWRITEBYTECODE="1")
    try:
        p = subprocess.run(["bash", str(PUSH_EXEC_SH), "--with-launch-data"],
                           cwd=str(REPO), env=env, capture_output=True, text=True, timeout=3600)
        assert p.returncode == 0, "推到一棵全新执行面目录就失败了：\n" + _fmt(p)
        for seg in ("A", "B", "C"):
            src = SEGMENTS[seg].replace("__TREE__", dest).replace("__P0__", dest + "_p0")
            # **源码走 base64**，不走 shell 引号：这段源码里有中文、有双引号、有换行，
            # 直接内联一次就能被远端 shell 吃掉一层转义，而失败形态是 `SyntaxError`，
            # 读起来像「这棵树坏了」—— 与本门要抓的那类误导同形。
            b64 = base64.b64encode(src.encode("utf-8")).decode("ascii")
            q = _ssh(host, "umask 022; export PYTHONDONTWRITEBYTECODE=1; cd "
                           f"{parent} && python3 -c 'import base64;exec(base64.b64decode(\"{b64}\"))'")
            assert q.returncode == 0, (
                f"一棵**从零推上去的**执行面树上，冒烟 {seg} 段不绿 —— {SEG_SAYS[seg]}\n" + _fmt(q))
        print(f"双机真推 + A/B/C 三段在一棵全新目录上跑完：{dest}")
    finally:
        if dest.count("/") >= 2 and "exec_fresh_" in dest:
            _ssh(host, f"rm -rf {dest} {dest}_p0")


# ===========================================================================
# skip 不是绿：这道门这次到底跑到了哪里
# ===========================================================================

def test_这道门这次到底跑到了哪里():
    """**逐条**把「跑了什么 / 没跑什么 / 为什么」打出来，并守住一条下界：
    单机那一半（真铺 + A/B/C + 四条判别力自证）在任何一台机器上都必须真的跑。"""
    lines = [f"执行面解释器：{_exec_py()}"]
    miss = missing_preconditions()
    lines.append("单机从零铺 + A/B/C：" + ("**跑**" if not miss else "跳过 —— " + "；".join(miss)))
    _b, _p, dwhy = find_dry_inputs()
    lines.append("D 段 `--dry` 全量注入：" + ("**跑**" if not dwhy else "跳过 —— " + "；".join(dwhy)))
    _pa, _h, why2 = dual_preconditions()
    lines.append("双机真推到全新目录：" + ("**跑**" if not why2 else "跳过 —— " + "；".join(why2)))
    print("\n".join("  " + x for x in lines))
    assert not miss, (
        "单机那一半没跑，这道门这次什么都没证明（**skip 不是绿**）：\n  - "
        + "\n  - ".join(miss) + "\n" + "\n".join("  " + x for x in lines))
    assert len(DEFECTS) >= 4, "判别力自证少于四条 —— 那几条缺陷不是都有反面判据"
