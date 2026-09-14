#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""落位：**单机形态**把「推」换成「本地落位」（卡 A9，用户裁定 ①②，2026-09-14）。

本轮要修的病不是某一行写死了路径，是**单机形态从来没被真走过**：以前的端到端全在
Linux 上，而 Linux 可以 `mkdir /data` 把写死的路径造出来（卡 D2 那次正是这么绕的），
**macOS 根卷只读、`sudo mkdir /data` 直接失败**，于是这一条在 Linux 上永远不显形。
交付终核在干净 Mac 上量到的四条 block（N-838 / N-840 / N-841 / N-842）全部落在
**从「出集」到「出表」这条路径上的跨机步骤**里。

裁定 ①：**单机形态 = 数据面、执行面、答案面都在同一台机器上，整条路径不含任何
`ssh` / `rsync` 到别的机器 / 远端核查。** 因此单机路径**不调**
`ops/push_exec_to_f02.sh` 与 `ops/push_bundle_to_f02.sh` —— **单机没有「推」这件事**；
那两步换成本模块的 `place_exec_tree()` / `place_bundle()`。
**双机路径逐字节不变**：那两个脚本本卡一个字节都没动（含 N-842 那道 timer 核查），
也没有加任何 `--force` 之类的绕过开关。

形态怎么判（**显式**，不猜）
--------------------------
`--topology single|dual` > 环境变量 `GENEBENCH_TOPOLOGY` > 默认 `dual`。
两者都给且不一致 = **当场拒绝**（与 `--channel` / `GENEBENCH_CHANNEL` 同一套纪律）。
**不靠「这台机器像不像发布方」判**（没有 hostname 嗅探、没有 `/data` 存在性探测）——
那正是本轮在修的病：判据一旦依赖「这台机器能不能造出那些路径」，它在 Linux 上就永远是绿的。

根从哪里来（裁定 ②）
------------------
单机：**全部从 `cfg.GENEBENCH_ROOT` 现算**，`$GENEBENCH_ROOT/genebench_runner`。
双机：`runner/placement_dual.RUNNER_ROOT_DEFAULT`，发布方那台的取值逐字不变。
两种形态都认同一个显式覆盖 `GENEBENCH_RUNNER_ROOT`（**它赢过形态默认**）。

答案面纪律一条没松
----------------
落位走的是**同一批门、同一份实现**，只是不 ssh：
`ops/push_guard.py`（形状 + 通行证逐文件核对）→
`runner/f02/answer_plane_guard.py --mode container`（**主口径**：这个 bundle 挂进
`/task` 会不会让 agent 看见答案面）→ 落地之后再用**树口径**扫一遍落点。
两道门的处置相反（容器模式拒绝启动不删、树模式命中即删），所以两道都要，
这与 `ops/push_bundle_to_f02.sh` 的取舍逐字同源。

**少了什么，说清楚**：双机那条路还核一件事 —— 对面
`genebench-answer-plane-scan.timer` 处于 `enabled + active`（N-61/N-842，每小时兜底扫描）。
单机形态下它是 systemd 的东西、Mac 上根本没有，本模块用**落位即扫**（上面那两道门
在每一次落位时同步跑）替代**每小时一次的周期复查**。差别是那段「落完了、还没跑」的
时间窗里没有第二次复查 —— 记在 `ops/tickets_inbox/A9.md`，**不是**放宽判据。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import genebench_config as cfg                              # noqa: E402

# ------------------------------------------------------------------ 形态

SINGLE = "single"
DUAL = "dual"
TOPOLOGIES: tuple[str, ...] = (SINGLE, DUAL)

#: 形态的环境变量。**默认 `dual`** —— 发布方那台不设它，行为一个字不变。
TOPOLOGY_ENV = "GENEBENCH_TOPOLOGY"
#: 执行面根的显式覆盖。**赢过形态默认**，两种形态都认。
RUNNER_ROOT_ENV = "GENEBENCH_RUNNER_ROOT"
#: 执行面上跑 `run_f02_a1.py` 的解释器。不设 = `python3`（双机那条逐字不变）。
RUNNER_PY_ENV = "GENEBENCH_RUNNER_PY"


class PlacementError(RuntimeError):
    pass


def resolve_topology(explicit: str | None = None) -> str:
    """形态判据。`explicit`（`--topology`）> `GENEBENCH_TOPOLOGY` > `dual`。

    两者都给且不一致 → 当场拒绝并把正确命令打出来。放行的话会得到
    「一半按单机落位、一半按双机 ssh」这种半跨机路径，而它的失败形态是**静默的**。
    """
    env = (os.environ.get(TOPOLOGY_ENV) or "").strip() or None
    exp = (str(explicit).strip() if explicit is not None else "") or None
    for v, who in ((exp, "--topology"), (env, TOPOLOGY_ENV)):
        if v is not None and v not in TOPOLOGIES:
            raise SystemExit(f"[红] {who}={v!r} 不认识；可选 {list(TOPOLOGIES)}")
    if exp and env and exp != env:
        raise SystemExit(
            f"[红] --topology {exp!r} 与环境变量 {TOPOLOGY_ENV}={env!r} 不一致 —— 拒绝启动。\n"
            f"    对齐了再跑：{TOPOLOGY_ENV}={exp} … --topology {exp}")
    return exp or env or DUAL


def is_single(topo: str | None = None) -> bool:
    return resolve_topology(topo) == SINGLE


def runner_root(topo: str | None = None) -> Path:
    """执行面的根。

    * `GENEBENCH_RUNNER_ROOT` 给了就用它（两种形态都认，赢过默认）；
    * 单机：`cfg.GENEBENCH_ROOT / "genebench_runner"` —— **现算**，零 `/data` 字面量；
    * 双机：`runner.placement_dual.RUNNER_ROOT_DEFAULT` —— 发布方那台逐字不变。
      这条 import 是**函数内**的：单机分支永远走不到它（见 `placement_dual` 的 docstring）。
    """
    v = (os.environ.get(RUNNER_ROOT_ENV) or "").strip()
    if v:
        return Path(v)
    if resolve_topology(topo) == SINGLE:
        return cfg.GENEBENCH_ROOT / "genebench_runner"
    from runner import placement_dual as _D
    return Path(_D.RUNNER_ROOT_DEFAULT)


def exec_dest(topo: str | None = None) -> Path:
    """exec 树的落点（双机形态下 = `ops/push_exec_to_f02.sh` 的 `DEST`）。"""
    return runner_root(topo) / "exec"


def guard_log(topo: str | None = None) -> Path:
    """执行面那道树扫描的日志/闩落点。**永远显式传给 guard**，不吃它的 CLI 默认值。"""
    return runner_root(topo) / "logs" / "answer_plane.jsonl"


def local_apg_log() -> Path:
    """数据面这一侧容器模式扫描的日志（与 `push_bundle_to_f02.sh` 的
    `GENEBENCH_APG_LOG` 同一个用途，但根从 `cfg` 现算）。"""
    return cfg.GENEBENCH_ROOT / "logs" / "answer_plane_local.jsonl"


def runner_py() -> str:
    return (os.environ.get(RUNNER_PY_ENV) or "").strip() or "python3"


# ------------------------------------------------------------------ exec 树白名单
#
# **这份清单与 `ops/push_exec_to_f02.sh` 的同名 shell 数组必须逐项相同。**
# 两份清单 = 两个真相，而漂移的表现是「f02 上 import 不了整棵 runner，f01 侧一切正常」
# （那个脚本的注释里记着 2026-09-04 那次）。`ops/test_A9.py` 把两边解出来逐项比对，
# 不一致即红 —— 加一个执行面要用的新模块，两处都要加。

GENETASK_FILES: tuple[str, ...] = ("__init__.py", "bundle.py", "pin.py", "arms.yaml")
GENETASK_DIRS: tuple[str, ...] = ("arms",)
OPS_FILES: tuple[str, ...] = ("guard_modes.py", "run_f02_a1.py", "api_usage.py")
OPS_DIRS: tuple[str, ...] = ("protocol",)
#: 仓库里 `ops/` 是命名空间包，执行面那棵树里却有一个空的 `__init__.py`（铺 exec/ 时留下的）。
#: 照原样补一个，只为让 `--delete` 不去动它 —— 同步的职责是让两边一致，不是顺手改现状。
OPS_EMPTY_INIT = True
RUNNER_WHOLE = True
SYNC_DIRS: tuple[str, ...] = ("genetask", "ops", "runner", "vendor")
#: `--with-launch-data` 额外带的两棵树（不带它，执行面 `by_id` 找不到新加的 config_id）。
LAUNCH_DIRS: tuple[str, ...] = ("harnesses", "integrations")
#: **随 exec 树船运的 vendor 包**（N-856，2026-09-14）。
#: `vendor/h11` 此前**不在仓库里、也没有任何文档化步骤会铺它** —— f02 上那份是
#: 2026-09-05 手工跑 `ops/run_f02_container_tests.sh` 留下的遗留物。而
#: `runner/c41/egress_proxy.py` 是**模块级** `import h11`、`runner_core` 又在 import 期
#: 取它的 `PLACEHOLDER_KEY`：**一棵从零铺的执行面 import 不了整棵 runner**，
#: 而 f01 侧一切正常（与这个脚本自己记着的 2026-09-04 那次同形）。
VENDOR_PKGS: tuple[str, ...] = ("h11",)
#: 绝不许出现在落位树里的路径段（红线 B2）。
FORBIDDEN_SEGMENTS: tuple[str, ...] = ("reference", "scorer", "runs_in", "gold",
                                       "memory_probe_answers", "solution")
#: 答案面文件名（与 `runner/f02/answer_plane_guard.ANSWER_PLANE_NAMES` 同一批）。
FORBIDDEN_NAMES: tuple[str, ...] = ("canary.json", "scorer.yaml", "solve.py",
                                    "equivalence.md", "slots.json", "_ledger.jsonl")

_RSYNC_EXCLUDES = ("--exclude=__pycache__/", "--exclude=.pytest_cache/")


def _run(cmd: list[str], *, cwd: Path | None = None, timeout: int = 1800,
         env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    e = dict(os.environ)
    e.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    if env:
        e.update(env)
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True,
                          text=True, timeout=timeout, env=e)


def assert_single(topo: str | None, what: str) -> str:
    t = resolve_topology(topo)
    if t != SINGLE:
        raise PlacementError(
            f"{what} 只在**单机形态**下可用（现在是 {t}）。双机形态请走既有入口："
            f"`ops/push_exec_to_f02.sh` / `ops/push_bundle_to_f02.sh`（红线 B2 的唯一入口）。")
    return t


def _scan_tree(root: Path, log: Path, *, what: str) -> None:
    """树口径：调**执行面自己那份实现**（不是在这里再写一遍 grep）。命中即停。"""
    log.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    p = _run([sys.executable, str(_REPO / "runner" / "f02" / "answer_plane_guard.py"),
              "--root", str(root), "--log", str(log)], cwd=_REPO)
    if p.returncode != 0:
        raise PlacementError(
            f"{what}：树口径扫描命中 —— 落点上出现答案面，已按 N-61 处置。\n"
            f"{(p.stdout or '')[-1200:]}\n{(p.stderr or '')[-1200:]}")


def _vendor_pin(pkg: str) -> str | None:
    """这个 vendor 包在代码里钉的版本（没钉就是 None）。"""
    if pkg == "h11":
        from runner.c41 import egress_proxy as _EP     # 函数内：它自己就要 h11
        return _EP.H11_VERSION
    return None


def stage_vendor(stage: Path) -> dict:
    """把 `VENDOR_PKGS` 从**发布方自己的运行环境**铺进 staging 的 `vendor/`（N-856）。

    **只有这一份实现**：`ops/push_exec_to_f02.sh` 用 `python -m runner.placement
    --stage-vendor <STAGE>` 调它 —— 两条路径共用一份，而不是再抄一张清单出来
    （两份清单 = 两个真相，`OPS_FILES` 那一对已经为此付过一次代价）。

    铺的是**网关环境自己那份** h11：裁定 2026-09-05 要的不是「版本号相同」，
    是边车与网关跑**同一份字节**（`runner/inject.place_h11` 的 P7d 再把它复制进 run dir）。
    三条当场拒：环境里没有它、版本与代码里钉的不一致、带了编译产物（挂进 musl 容器会炸）。
    """
    import importlib
    stage = Path(stage)
    (stage / "vendor").mkdir(parents=True, exist_ok=True, mode=0o700)
    laid: dict[str, str] = {}
    for pkg in VENDOR_PKGS:
        try:
            mod = importlib.import_module(pkg)
        except ModuleNotFoundError as e:
            raise PlacementError(
                f"铺 vendor 中止：发布方这个环境里没有 {pkg} —— 执行面要的就是"
                f"**网关自己在用的那一份**。先装上再重跑：`{sys.executable} -m pip install {pkg}`"
            ) from e
        src = Path(mod.__file__).resolve().parent
        got = getattr(mod, "__version__", None)
        pin = _vendor_pin(pkg)
        if pin is not None and got != pin:
            raise PlacementError(
                f"铺 vendor 中止：发布方环境里的 {pkg} 是 {got}，代码里钉的是 {pin} —— "
                f"边车与网关必须跑同一份解析器（`runner/c41/egress_proxy.H11_VERSION`），"
                f"否则「两个解析器看法不同」那一类洞就回来了")
        compiled = sorted(str(p.relative_to(src)) for p in src.rglob("*")
                          if p.suffix in (".so", ".pyd", ".dylib"))
        if compiled:
            raise PlacementError(
                f"铺 vendor 中止：{pkg} 带了编译产物 {compiled[:3]} —— 它要被挂进 musl 容器，"
                f"glibc 的 .so 在那里起不来（`runner/inject.place_h11` 同一条判据）")
        _rsync(src, stage / "vendor" / pkg)
        laid[pkg] = f"{got} ← {src}"
    return {"stage": str(stage), "vendored": laid}


def _assert_no_answer_plane_names(stage: Path) -> None:
    bad: list[str] = []
    for seg in FORBIDDEN_SEGMENTS:
        bad += [f"禁段 {seg}：{p}" for p in stage.rglob(seg)]
    for name in FORBIDDEN_NAMES:
        bad += [f"禁名 {name}：{p}" for p in stage.rglob(name)]
    if bad:
        raise PlacementError(
            "落位中止：staging 里出现答案面的段/名。**不要在这里加例外。**\n  "
            + "\n  ".join(bad[:12]))


def place_exec_tree(topo: str | None = None, *, with_launch_data: bool = False,
                    verify: bool = True) -> dict:
    """**单机形态**：把 exec 树本地落位到 `exec_dest()`。不 ssh、不 rsync 到别的机器。

    步骤与 `ops/push_exec_to_f02.sh` 一一对应（白名单 → 禁段禁名断言 → staging 上
    跑执行面自己那道门 → 同步 → 落地即扫 → 逐字节复核），**只把「到对面」换成「到本机」**。
    """
    t = assert_single(topo, "runner/placement.place_exec_tree")
    dest = exec_dest(t)
    stage = cfg.GENEBENCH_ROOT / "staging" / "exec_place"
    if stage.exists():
        shutil.rmtree(stage)
    cfg.create_dir(stage)

    cfg.create_dir(stage / "genetask")
    for f in GENETASK_FILES:
        shutil.copy2(_REPO / "genetask" / f, stage / "genetask" / f)
    for d in GENETASK_DIRS:
        if (_REPO / "genetask" / d).is_dir():
            _rsync(_REPO / "genetask" / d, stage / "genetask" / d)
    cfg.create_dir(stage / "ops")
    for f in OPS_FILES:
        shutil.copy2(_REPO / "ops" / f, stage / "ops" / f)
    if OPS_EMPTY_INIT:
        (stage / "ops" / "__init__.py").write_text("", encoding="utf-8")
        (stage / "ops" / "__init__.py").chmod(0o600)
    for d in OPS_DIRS:
        _rsync(_REPO / "ops" / d, stage / "ops" / d)
    if RUNNER_WHOLE:
        _rsync(_REPO / "runner", stage / "runner")
    stage_vendor(stage)                            # N-856：h11 随树船运，不靠遗留物
    dirs = list(SYNC_DIRS)
    if with_launch_data:
        for d in LAUNCH_DIRS:
            if (_REPO / d).is_dir():
                _rsync(_REPO / d, stage / d)
        dirs += list(LAUNCH_DIRS)

    _assert_no_answer_plane_names(stage)
    # staging 这一道**只读不删**（与 `ops/push_exec_to_f02.sh` 第 3 步同一个取舍：
    # 命中即停、不动文件 —— 该改的是白名单，不是 staging）。落地之后那一道才是
    # 「命中即删 + 落闩」的树模式。
    from runner.f02 import answer_plane_guard as _APG
    hits = _APG.scan(stage)
    if hits:
        raise PlacementError(
            f"落位中止：staging 里有 {len(hits)} 项答案面命中 —— **不要在这里加例外。**\n  "
            + "\n  ".join(f"[{h.kind}] {h.path}  {h.detail}" for h in hits[:12]))

    # 落点**根自己**要 0700（与 `ops/push_exec_to_f02.sh` 第 4 步同一条，卡 F10 实测）：
    # `Path.mkdir(parents=True, mode=0o700)` 的 `mode` 只作用在**最后一段**，
    # 中间段吃 umask —— 单机形态下这棵树在 `$GENEBENCH_ROOT` 之内，一个 0775 的根
    # 会让注入器 P0 与网关的启动守门当场拒（红线 5）。
    dest.mkdir(parents=True, exist_ok=True, mode=0o700)
    for p in (runner_root(t), dest):
        p.chmod(p.stat().st_mode & ~0o077)
    synced = []
    for d in dirs:
        if not (stage / d).is_dir():
            continue                                   # 源目录不在 → 跳过且不 --delete
        (dest / d).mkdir(parents=True, exist_ok=True, mode=0o700)
        _rsync(stage / d, dest / d, delete=True)
        synced.append(d)
    _scan_tree(dest, guard_log(t), what="exec 树落地后")

    parity = None
    if verify:
        here = _run([sys.executable, "-c",
                     "import sys; sys.path.insert(0, '.'); "
                     "from runner.c42 import harness_commands as H; print(H.command_for('Codex CLI'))"],
                    cwd=_REPO)
        there = _run([runner_py(), "-c",
                      "import sys; sys.path.insert(0, '.'); "
                      "from runner.c42 import harness_commands as H; print(H.command_for('Codex CLI'))"],
                     cwd=dest)
        if here.returncode != 0 or there.returncode != 0 or here.stdout != there.stdout:
            raise PlacementError(
                "exec 树落位后逐字节复核不过：两侧 command_for('Codex CLI') 不同（或有一侧根本跑不起来）。\n"
                f"  仓库：rc={here.returncode} {(here.stdout or here.stderr or '')[-300:]}\n"
                f"  落点：rc={there.returncode} {(there.stdout or there.stderr or '')[-300:]}")
        parity = len(here.stdout)
    return {"topology": t, "dest": str(dest), "synced": synced,
            "with_launch_data": bool(with_launch_data), "parity_bytes": parity}


def _rsync(src: Path, dst: Path, *, delete: bool = False) -> None:
    dst.mkdir(parents=True, exist_ok=True, mode=0o700)
    cmd = ["rsync", "-a", "--no-perms", "--chmod=D700,F600", *_RSYNC_EXCLUDES]
    if delete:
        cmd.append("--delete")
    cmd += [f"{str(src).rstrip('/')}/", f"{str(dst).rstrip('/')}/"]
    p = _run(cmd)
    if p.returncode != 0:
        raise PlacementError(f"本地同步失败 {src} → {dst}：{(p.stderr or '')[-500:]}")


def place_bundle(src, dst, manifest, topo: str | None = None) -> dict:
    """**单机形态**：把一个 X 面 bundle 本地落位到 `dst`。不 ssh、不核远端 timer。

    门与 `ops/push_bundle_to_f02.sh` 同源、同一份实现、同样的顺序：
    ① `ops/push_guard.py`（形状 + 通行证逐文件核对）；
    ①c 容器边界口径（**主口径**，v1.0.16 卡 G2）：把 bundle **声明**成将挂到 `/task` 的那个面；
    ② 落点必须在 `runner_root()` 下（**根现算**，不是写死的字符串）；
    ③ 本地拷贝（目录本身，不带尾斜杠语义）+ 通行证随行；
    ④ 落地即扫（树口径，命中即删 + 落闩）。
    """
    t = assert_single(topo, "runner/placement.place_bundle")
    src = Path(src).resolve()
    dst = Path(dst)
    manifest = Path(manifest).resolve()
    root = runner_root(t)

    p = _run([str(cfg.PYTHON) if Path(cfg.PYTHON).exists() else sys.executable,
              str(_REPO / "ops" / "push_guard.py"), str(src), str(manifest)], cwd=_REPO)
    if p.returncode != 0:
        raise PlacementError("落位中止：bundle 没过守门。**不要在这里加例外。**\n"
                             + (p.stdout or "")[-1500:] + (p.stderr or "")[-800:])

    g = _run([sys.executable, str(_REPO / "runner" / "f02" / "answer_plane_guard.py"),
              "--mode", "container", "--mount", f"{src}/work:/task", "--mount", f"{src}:/task",
              "--log", str(local_apg_log())], cwd=_REPO)
    if g.returncode != 0:
        raise PlacementError(
            "落位中止：**容器边界命中** —— 这个 bundle 挂进 /task 会让 agent 看到答案面。\n"
            "（容器模式不删任何东西：命中的往往是答案面本体。请改 bundle，不要改这道门。）\n"
            + (g.stdout or "")[-1200:] + (g.stderr or "")[-800:])

    try:
        dst.resolve().relative_to(root.resolve())
    except ValueError:
        raise PlacementError(f"落位中止：目标 {dst} 不在执行面根 {root} 下") from None

    dst.mkdir(parents=True, exist_ok=True, mode=0o700)
    landed = dst / src.name
    if landed.exists():
        shutil.rmtree(landed)
    _rsync(src, landed)
    shutil.copyfile(manifest, dst / f"{src.name}.manifest.json")
    (dst / f"{src.name}.manifest.json").chmod(0o600)
    _scan_tree(landed, guard_log(t), what=f"bundle 落地后（{landed}）")
    return {"topology": t, "src": str(src), "landed": str(landed),
            "manifest": str(dst / f"{src.name}.manifest.json")}


# ------------------------------------------------------------------ CLI

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="落位（单机形态把「推」换成「本地落位」）。双机形态请走 ops/push_*_to_f02.sh。")
    ap.add_argument("--topology", default=None, choices=list(TOPOLOGIES),
                    help=f"single / dual。不给就读 {TOPOLOGY_ENV}，再不给按 dual")
    ap.add_argument("--place-exec", action="store_true", help="本地落位 exec 树（= 双机的 push_exec）")
    ap.add_argument("--with-launch-data", action="store_true",
                    help="额外带 harnesses/ 与 integrations/（不带它，执行面找不到新 config_id）")
    ap.add_argument("--no-verify", action="store_true", help="跳过落位后的 command_for 逐字节复核")
    ap.add_argument("--where", action="store_true", help="只打印本形态下的几个根，什么都不做")
    ap.add_argument("--stage-vendor", default=None, metavar="STAGE",
                    help="把 vendor 包（h11）铺进给定的 staging 目录后退出。"
                         "`ops/push_exec_to_f02.sh` 调它 —— 两条路径共用同一份实现（N-856）。"
                         "**与形态无关**，所以排在形态判据之前。")
    a = ap.parse_args(argv)
    if a.stage_vendor:
        print(json.dumps(stage_vendor(Path(a.stage_vendor)), ensure_ascii=False, indent=1))
        return 0
    t = resolve_topology(a.topology)
    if a.where or not a.place_exec:
        print(json.dumps({"topology": t, "genebench_root": str(cfg.GENEBENCH_ROOT),
                          "runner_root": str(runner_root(t)), "exec_dest": str(exec_dest(t)),
                          "guard_log": str(guard_log(t))}, ensure_ascii=False, indent=1))
        return 0
    print(json.dumps(place_exec_tree(t, with_launch_data=a.with_launch_data,
                                     verify=not a.no_verify), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
