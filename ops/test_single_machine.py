#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""卡 B9（用户裁定 ③）：**在 `/data` 不可及的条件下，单机形态这条路走不走得通。**

这道门要证明的事（任务书原话）：`GENEBENCH_ROOT` 指向一个临时目录、**且不允许访问
`/data`** 时，跑通 `clone → 三件附件 → 起网关 → 出集 → 一个 job → 出表`。

**三层，做到哪层写哪层**（本文件逐条对应）
--------------------------------------
* **① 静态层**：单机路径入口的传递闭包里 `/data` 字面量的**取值位**为零。
  这一层**独立重算**，不采信卡 A9 的转述：入口集合是它的**超集**（把起网关、`--harden`、
  外部自检、**执行面入口 `ops/run_f02_a1.py`** 也算进来），而且每一行按 AST 判它
  到底是注释、文档串，还是真会改变本进程取值的那种。**卡 A9 的闭包漏了执行面入口** ——
  那正是本卡量到 N-855 的地方（`ops/run_joblist.py` 是用**子进程字符串**调它的，
  AST 闭包走不到）。
* **② 运行时断言层**：`sys.addaudithook` 拦 `open` / `exec` / 子进程参数，断言整个
  跑批进程树里没有任何以 `/data` 开头的 open。靠 `PYTHONPATH` 里的 `sitecustomize`
  进每一个 Python 子进程。**覆盖不到**非 Python 子进程（`docker` / `rsync` / `git`）——
  那一层本卡在 f02 上用 `strace -f` 另外量过，但 `strace` 不是每台机器都有，
  所以本文件里它是可选的。
* **③ 遮蔽层**：**做不到，如实写**。f02（Ubuntu 24.04）上
  `kernel.apparmor_restrict_unprivileged_userns=1`，`unshare -r -m` 与 `bwrap` 都在
  `setting up uid map: Permission denied` 上退，而本机无 sudo、装不了东西
  （docker.io 被墙）。所以本卡的 `/data` 不可及是**断言**出来的，不是**遮蔽**出来的：
  第 ②层能证明「我们的 Python 没去开它」，**不能**证明「就算去开也开不到」。
  `test_layer3_shadowing_is_not_available` 把这件事写成一条会跑的记录。

**真跑那一段允许大声 skip，但 skip 不是绿**：`test_real_run_preconditions` 把每一条
前置逐条打出来（docker / key / 网关 / 容器打不打得到宿主 / 执行面 provider），
缺哪条说哪条。
"""
from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PY = sys.executable

# ===========================================================================
# ① 静态层：独立重算闭包 + `/data` 取值位
# ===========================================================================

#: 外部单机用户照 README §2.1 / §2.3 / §2.4 真会敲到的 Python 入口。
#: **比卡 A9 的 `SINGLE_PATH_ENTRIES` 多 10 个**，多的那几条是本卡加的：
#: 起网关（`gateway/app.py`）、收紧（`ops/guard_modes.py`）、外部自检
#: （`ops/selfcheck_public.py`）、以及**执行面那个入口**（`ops/run_f02_a1.py`）。
ENTRIES: tuple[str, ...] = (
    "ops/guard_modes.py",            # §2.1 --harden
    "ops/selfcheck_public.py",       # §2.1 外部自检
    "gateway/app.py",                # §2.3 起网关
    "ops/joblist.py",                # §2.4 ① 生成清单
    "ops/run_joblist.py",            # §2.4 ②④ 干跑 / 真跑六段
    "runner/placement.py",           # §2.4 ③ exec 树与 bundle 的本地落位
    "ops/gateway_lock.py",           # §2.4 ④ 每个 job 都进这个上下文
    "ops/export_bundle.py",          # §2.4 ④ 出集
    "ops/push_guard.py",             # §2.4 ④ 落位守门
    "ops/run_f02_a1.py",             # §2.4 ④ **执行面入口**（子进程调用，卡 A9 的闭包够不着）
    "runner/inject.py",              # 执行面注入
    "runner/c41/runner_core.py",     # 执行面 compose 渲染
    "runner/f02/answer_plane_guard.py",
    "ops/score_runs.py",             # §2.4 ④ 结算
    "ops/results_db.py",             # §2.4 ④ 入库
    "ops/mk_tables.py",              # §2.4 ⑤ 出表
)

#: 不参与本门的文件（**逐字闭集**，每条写明理由）。
EXCLUDED: dict[str, str] = {
    "runner/placement_dual.py":
        "双机形态专用：它存在的唯一理由就是把发布方执行面的绝对路径关进一个单机分支"
        "不 import 的文件里（卡 A9）。本文件另有一条测试真起一个 single 进程证明它没被 import。",
}

#: **取值位**豁免（`/data` 出现在真会改变取值的位置，但不在单机路径上取用）。
#: 逐字闭集，每条写明理由；**不许用通配**。
VALUE_EXEMPT: dict[str, tuple[str, ...]] = {
    "genebench_config.py": (
        # 仓库唯一声明允许出现绝对路径字面量的模块；单机用户设了 GENEBENCH_ROOT 之后
        # `_DEFAULT_ROOT` 不再被取用（本文件 test_root_comes_from_env 真起进程量过）。
        # LAKE / QLIB_RELEASE 只在「自己重建数据面」那条链上用，不在 §2.4 上。
        '_DEFAULT_ROOT = "/data/shared/genebench"',
        'LAKE: Path = Path("/home/ljn/projects/data/market_lake")',
        'QLIB_RELEASE: Path = Path("/home/ljn/projects/data/qlib/releases/2026-08-26")',
    ),
    "ops/export_bundle.py": (
        # f-string 拼的**提示文案**（打给人看的下一步命令），不参与本进程取任何路径。
        'f"/data/genebench_runner/<run>/runner/tasks {r[\'manifest\']}")',
    ),
    "ops/freeze_v10.py": (
        # 冻结清单里两条被截断的**说明文本**（字符串内容是记因，不是路径取值）。
        '"交易日只留 3 个最小代码。三者 sha 写回 params；数据卡 `ops/data_cards/fixture_s"',
        '"件 + 两臂干注入 run dir 全部文件」sha256 逐条相同（`/data/shared/genebench/s"',
    ),
    "ops/mk_tables.py": (
        # 表脚里渲染给读者的「复现命令」写死发布方解释器与仓库路径 —— **这是一处真缺陷**
        # （外部单机用户照抄不到），卡 A9 已登记 N-850；它不改变本进程取任何路径，故不挡本门。
        '"PY=/data/shared/genebench/env/bin/python; cd /data/shared/genebench/repo",',
    ),
    "ops/push_guard.py": (
        # 适配赛道（set_id == v1.0-adapt）专用的落点前缀；§2.4 那四道题的 set_id 不是它。
        'ADAPT_DEST_PREFIX = "/data/genebench_runner/adapt/"',
    ),
    "ops/run_controls.py": (
        # 三控侧打给人看的复现命令；三控不在 §2.4 单机路径上。
        '"复现这一跑（**照抄整条**；`GB=/data/shared/genebench`、`PY=$GB/env/bin/python`）：", "",',
    ),
    "ops/run_f02_a1.py": (
        # 打给人看的文案（`--dry` 时 provider 指到数据面那一份），不参与取值。
        # 另一条（`--provider-root` 帮助里的 f02 绝对路径）在卡 F10 改掉了：
        # 现在写的是「<执行面根>/provider/…」。三条真取值也在卡 F10 改成现算（N-855 已关）。
        '"/data/shared/genebench/snapshots/v1/qlib_provider。"',
    ),
    "runner/c41/runner_core.py": (
        # DATA_ROOTS 不是「根」，是**禁挂**宿主数据目录的黑名单（作用是拒绝，不是取值）：
        # 换一台机器只会让它少拒一点，不会让它错拒。
        'DATA_ROOTS: tuple[str, ...] = ("/data/shared", "/data/market_lake_f02",',
        '"/data/genebench_runner/manifests",',
        '"/data/genebench_runner/provider")',
    ),
    "runner/f02/answer_plane_guard.py": (
        # 这道门**命令行的默认值**，而 f02 上那个每小时的 systemd timer 正吃这两个默认 ——
        # 动它等于悄悄改掉「兜底扫描扫哪棵树」（卡 A9 的 N-852，刻意不动）。
        # 单机路径上永远显式传 --root / --log（本文件 test_guard_always_gets_explicit_root 钉住）。
        'DEFAULT_ROOT = "/data/genebench_runner"',
        'DEFAULT_LOG = "/data/genebench_runner/logs/answer_plane.jsonl"',
    ),
}


#: **不是豁免，是登记在案的缺陷**（N-855，卡 B9 2026-09-14 实测）。
#: 这三行是**真取值**，而且都在**执行面入口** `ops/run_f02_a1.py` 上 ——
#: 卡 A9 的静态门看不到它们，因为 `ops/run_joblist.py` 是用**子进程字符串**调这个文件的，
#: AST 闭包走不到子进程。把它们单列在这里有两个作用：
#:   ① 本门有一个**封闭**的基线，新出现的 `/data` 取值位照样红；
#:   ② `test_known_defects_are_exactly_these` 钉住这个集合**只能缩不能长**。
#: **真正的判据是 `test_exec_face_provider_root_comes_from_runner_root` 那条 xfail** ——
#: 那条一转绿（XPASS），就该把这三行从本清单删掉。
#: **N-855 已关**（卡 F10，2026-09-14）：那三行都改成从执行面根现算了
#: （`runner_root()` = `runner.c41.runner_core.ROOT`，与 `ops/run_joblist.probe_f02_provider`
#: 认同一个 `GENEBENCH_RUNNER_ROOT`、回落同一个 `placement_dual.RUNNER_ROOT_DEFAULT`），
#: 并且真跑路径上多了一条当场拒（`run_f02_a1.assert_provider_same_source`）。
#: **空集是它应该的样子**：这张表的作用是给上面那道静态门一个**封闭**基线，
#: 新出现的 `/data` 取值位照样红；留着已经修好的条目只会让门悄悄放宽。
KNOWN_DEFECT: dict[str, tuple[str, ...]] = {}


def _mod_path(mod: str) -> Path | None:
    p = REPO / (mod.replace(".", "/") + ".py")
    if p.is_file():
        return p
    p2 = REPO / mod.replace(".", "/") / "__init__.py"
    return p2 if p2.is_file() else None


def _imports_of(path: Path) -> set[str]:
    out: set[str] = set()
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return out
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom) and not n.level and n.module:
            out.add(n.module)
            out |= {f"{n.module}.{a.name}" for a in n.names}
    return out


def closure() -> list[Path]:
    seen: set[Path] = set()
    stack = [REPO / e for e in ENTRIES]
    while stack:
        f = stack.pop()
        if f in seen or not f.is_file():
            continue
        rel = str(f.relative_to(REPO))
        if rel in EXCLUDED or rel.startswith("ops/test_"):
            continue
        seen.add(f)
        for m in _imports_of(f):
            p = _mod_path(m)
            if p is not None:
                stack.append(p)
    return sorted(seen)


def _literal_expr_lines(p: Path) -> set[int]:
    """docstring / 纯字面量表达式语句占的行号（那些行里的 `/data` 是**说明**，不是取值）。"""
    out: set[int] = set()
    try:
        tree = ast.parse(p.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return out
    for n in ast.walk(tree):
        if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) \
                and isinstance(n.value.value, str):
            for i in range(n.lineno, (n.end_lineno or n.lineno) + 1):
                out.add(i)
    return out


def value_position_hits() -> list[tuple[str, int, str]]:
    """闭包里 `/data` 出现在**取值位**（不是注释、不是文档串）的每一行。"""
    hits: list[tuple[str, int, str]] = []
    for f in closure():
        rel = str(f.relative_to(REPO))
        docs = _literal_expr_lines(f)
        for i, ln in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if "/data" not in ln:
                continue
            s = ln.strip()
            if s.startswith("#") or i in docs:
                continue
            hits.append((rel, i, s))
    return hits


def test_closure_is_a_superset_of_card_A9():
    """本门的闭包必须**包含**卡 A9 那六个入口，而且要更宽 —— 否则这是同一道门再跑一遍。"""
    rels = {str(p.relative_to(REPO)) for p in closure()}
    for e in ("ops/joblist.py", "ops/run_joblist.py", "runner/placement.py",
              "ops/score_runs.py", "ops/results_db.py", "ops/mk_tables.py"):
        assert e in rels, f"卡 A9 的入口 {e} 不在本门闭包里"
    # 本门**额外**要覆盖的：起网关与执行面入口。卡 A9 的闭包两个都没有。
    for e in ("gateway/app.py", "ops/guard_modes.py", "ops/run_f02_a1.py", "runner/inject.py"):
        assert e in rels, f"本门自己加的入口 {e} 不在闭包里"
    assert "runner/placement_dual.py" not in rels
    assert len(rels) >= 50, f"闭包只有 {len(rels)} 个文件 —— 走塌了"


def test_no_unexempted_data_literal_at_value_positions():
    """**裁定 ③ 的静态判据（第 ①层）**：单机路径闭包里 `/data` 的取值位必须全在闭集里。

    注释与文档串不算 —— 它们不改变本进程取哪个路径，而把它们塞进豁免清单只会让清单
    长到没人看。真正要盯的是这一类：`X = "/data/..."`、`Path("/data/...")`、
    传给函数的实参。
    """
    bad = [f"{rel}:{i}: {s}" for rel, i, s in value_position_hits()
           if s not in VALUE_EXEMPT.get(rel, ()) and s not in KNOWN_DEFECT.get(rel, ())]
    assert not bad, (
        "单机路径的**取值位**上出现了未豁免的 `/data`（共 %d 行）：\n  " % len(bad)
        + "\n  ".join(bad[:20])
        + "\n\n要么从 `cfg.GENEBENCH_ROOT` / `GENEBENCH_RUNNER_ROOT` 现算（首选），"
          "要么搬进 `runner/placement_dual.py`（双机专用），"
          "要么原文照抄进本文件的 `VALUE_EXEMPT` 并写明理由 —— **不许用通配**。")


def test_known_defects_are_exactly_these():
    """N-855 的那几行**只能缩不能长**。

    缩（修好了）→ 本条红，提醒把它从 `KNOWN_DEFECT` 里删掉、顺手把上面那条 xfail 也删掉。
    长（又新写了一行）→ 上面那条静态门先红。
    """
    live = {(rel, s) for rel, _i, s in value_position_hits()}
    gone = [f"{rel}: {s}" for rel, lines in KNOWN_DEFECT.items() for s in lines
            if (rel, s) not in live]
    assert not gone, (
        "N-855 登记的这几行已经不在盘上了（好事）——\n  " + "\n  ".join(gone)
        + "\n把它们从 `KNOWN_DEFECT` 里删掉，并把 "
          "`test_exec_face_provider_root_comes_from_runner_root` 的 xfail 标记一起删掉。")


def test_value_exempt_list_has_no_dead_entries():
    """豁免清单不许留死条目 —— 否则它会悄悄放宽。"""
    live = {(rel, s) for rel, _i, s in value_position_hits()}
    stale = [f"{rel}: {s[:80]}" for rel, lines in VALUE_EXEMPT.items() for s in lines
             if (rel, s) not in live]
    assert not stale, "VALUE_EXEMPT 里有死条目，清掉：\n  " + "\n  ".join(stale)


# ---------------------------------------------------------------- N-855（卡 F10 已修，xfail 去掉）
def test_exec_face_provider_root_comes_from_runner_root(tmp_path, monkeypatch):
    """执行面 provider 根必须跟着 `GENEBENCH_RUNNER_ROOT` 走。"""
    monkeypatch.setenv("GENEBENCH_RUNNER_ROOT", str(tmp_path / "runner_root"))
    out = subprocess.run(
        [PY, "-c", "import sys; sys.path.insert(0, '.'); import ops.run_f02_a1 as R; "
                   "print(R.provider_default('public'))"],
        cwd=REPO, capture_output=True, text=True, timeout=120,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    assert out.returncode == 0, out.stderr[-800:]
    assert "/data" not in out.stdout, (
        f"执行面 provider 根算出来是 {out.stdout.strip()} —— 它没跟着 GENEBENCH_RUNNER_ROOT 走")


# ---------------------------------------------------------------- N-857（卡 F10 已修，xfail 去掉）
def test_guard_modes_is_importable_on_an_exec_tree(tmp_path):
    """把 exec 树的 `ops/` 那几件按白名单铺出来，`guard_modes` 必须 import 得进。"""
    import runner.placement as PL                                   # noqa: PLC0415
    ops = tmp_path / "exec" / "ops"
    ops.mkdir(parents=True)
    for f in PL.OPS_FILES:
        shutil.copy2(REPO / "ops" / f, ops / f)
    (ops / "__init__.py").write_text("", encoding="utf-8")
    out = subprocess.run(
        [PY, "-c", "import importlib.util, pathlib; "
                   "s = importlib.util.spec_from_file_location('_g', "
                   "pathlib.Path('exec/ops/guard_modes.py')); "
                   "m = importlib.util.module_from_spec(s); s.loader.exec_module(m); print('ok')"],
        cwd=tmp_path, capture_output=True, text=True, timeout=120,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": ""})
    assert out.returncode == 0, (
        "exec 树上加载 guard_modes 失败（注入器 P0 走的就是这条）：\n" + out.stderr[-900:])


# ===========================================================================
# ② 运行时断言层：审计钩子
# ===========================================================================

#: 这份 `sitecustomize` 与 `$GB/scratch/B9/sitecustomize.py` **同源**（本卡在 f02 上
#: 真跑时用的就是它）。放在这里是为了让这道门在外部干净 clone 上也能跑。
SITECUSTOMIZE = '''
import os, sys, traceback
_DENY = tuple(p for p in (os.environ.get("GB_AUDIT_DENY") or "/data").split(",") if p)
_ALLOW = tuple(p for p in (os.environ.get("GB_AUDIT_ALLOW") or "").split(",") if p)
_LOGP = os.environ.get("GB_AUDIT_LOG") or ""
_fd = os.open(_LOGP, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600) if _LOGP else -1
_busy = False
_EV = {"open": (0,), "os.mkdir": (0,), "os.rmdir": (0,), "os.remove": (0,),
       "os.unlink": (0,), "os.rename": (0, 1), "os.replace": (0, 1), "os.link": (0, 1),
       "os.symlink": (0, 1), "os.listdir": (0,), "os.scandir": (0,), "os.chdir": (0,),
       "os.chmod": (0,), "shutil.copyfile": (0, 1), "shutil.copytree": (0, 1),
       "shutil.move": (0, 1), "shutil.rmtree": (0,)}
def _t(v):
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace")
    if isinstance(v, str):
        return v
    if hasattr(v, "__fspath__"):
        try:
            return _t(v.__fspath__())
        except Exception:
            return ""
    return ""
def _bad(s):
    if any(s == a or s.startswith(a + "/") for a in _ALLOW):
        return False
    return any(s == d or s.startswith(d + "/") for d in _DENY)
def _hit(ev, what):
    global _busy
    _busy = True
    try:
        msg = ("\\n[卡B9 ②层] %s 路径: 事件=%s 路径=%s pid=%s argv=%s\\n%s\\n"
               % (_DENY, ev, what, os.getpid(), " ".join(sys.argv[:4]),
                  "".join(traceback.format_stack()[:-2])))
        if _fd >= 0:
            os.write(_fd, msg.encode("utf-8", "replace"))
        os.write(2, msg.encode("utf-8", "replace"))
    finally:
        _busy = False
    raise RuntimeError("卡 B9 ②层：碰了 %s（%s：%s）" % (_DENY, ev, what))
def _hook(ev, args):
    if _busy:
        return
    idx = _EV.get(ev)
    if idx is not None:
        for i in idx:
            if i < len(args):
                s = _t(args[i])
                if s and _bad(s):
                    _hit(ev, s)
        return
    if ev in ("subprocess.Popen", "os.exec", "os.posix_spawn", "os.spawn"):
        for a in args:
            s = _t(a)
            if s and _bad(s):
                _hit(ev, s)
            elif isinstance(a, (list, tuple)):
                for x in a:
                    u = _t(x)
                    if u and _bad(u):
                        _hit(ev, u)
sys.addaudithook(_hook)
'''

SHIM = "#!/bin/sh\necho \"$0 $*\" >> \"$GB_SSH_LOG\"\nexit 42\n"


def _allow_prefixes(deny: str) -> list[str]:
    """要放行的前缀 —— **只有落在 deny 前缀之下的那几个才会非空**。

    发布方那台上仓库与 venv 都在 `/data/shared/genebench/` 下；外部机器上一个都不是。
    """
    ds = [d for d in deny.split(",") if d]
    cand = {str(REPO), sys.prefix, sys.base_prefix, str(Path(sys.executable).parent)}
    return sorted({c for c in cand if any(c == d or c.startswith(d + "/") for d in ds)})


def test_the_allow_list_is_empty_off_the_publisher_box():
    """放行清单只在**仓库或解释器本身就落在 `/data` 下**的机器上非空。

    也就是：这条放行是给发布方那台准备的（仓库 `/data/shared/genebench/repo`、
    venv `/data/shared/genebench/env`）。外部单机用户的树在 `$GB/repo`、
    venv 在 `$GB/env`，两样都不以 `/data` 开头，放行清单为空 ——
    **这道门在外部机器上是满射程的。**
    """
    allow = _allow_prefixes("/data")
    if not str(REPO).startswith("/data"):
        assert allow == [], f"仓库不在 /data 下，放行清单却非空：{allow}"
    else:
        assert all(a.startswith("/data") for a in allow), allow
        print(f"[发布方那台] 放行前缀：{allow}（仓库与 venv 都落在 /data 下）")


def _lab(tmp_path: Path, deny: str) -> dict:
    """搭一个「①PATH 上的 ssh/scp 一调就 42 ②审计钩子拦 deny 前缀」的实验台。

    **`GB_AUDIT_ALLOW` 放行三样东西自己所在的前缀：仓库、解释器、venv。**
    在发布方那台上这三样全在 `/data/shared/genebench/` 下（仓库 `…/repo`、
    解释器 `…/env/bin/python`），不放行的话这道门会被「读自己的源码 / 读 stdlib」
    淹掉，量不到真正要盯的东西 —— **数据根与执行面根**。
    **外部机器上这个放行是空的**（仓库在 `$GB/repo`、解释器在 `$GB/env`，
    都不以 `/data` 开头），所以它不会悄悄放宽外部那一侧；
    `test_the_allow_list_is_empty_off_the_publisher_box` 把这一点钉住。
    """
    audit = tmp_path / "audit"
    audit.mkdir()
    (audit / "sitecustomize.py").write_text(SITECUSTOMIZE, encoding="utf-8")
    shim = tmp_path / "shim"
    shim.mkdir()
    for n in ("ssh", "scp", "rsh", "sftp"):
        p = shim / n
        p.write_text(SHIM, encoding="utf-8")
        p.chmod(0o700)
    hits = tmp_path / "audit_hits.log"
    sshlog = tmp_path / "ssh_calls.log"
    hits.touch()
    sshlog.touch()
    env = {**os.environ,
           "PATH": f"{shim}{os.pathsep}{os.environ.get('PATH', '')}",
           "PYTHONPATH": str(audit),
           "PYTHONDONTWRITEBYTECODE": "1",
           "GB_AUDIT_DENY": deny,
           "GB_AUDIT_ALLOW": ",".join(_allow_prefixes(deny)),
           "GB_AUDIT_LOG": str(hits),
           "GB_SSH_LOG": str(sshlog)}
    return {"env": env, "hits": hits, "ssh": sshlog}


def test_the_audit_hook_actually_catches_a_forbidden_open(tmp_path):
    """**先证明这道门不是假的**：钩子拦的是一个本机真有的前缀，open 它必须炸。

    用 `tmp_path` 下自己造的前缀，不用 `/data` —— 这条要在**任何**机器上都能跑，
    包括根本没有 `/data` 的 macOS。
    """
    fake = tmp_path / "fakedata"
    fake.mkdir()
    (fake / "x.txt").write_text("hi", encoding="utf-8")
    lab = _lab(tmp_path, str(fake))
    p = subprocess.run([PY, "-c", f"open({str(fake / 'x.txt')!r}).read()"],
                       capture_output=True, text=True, timeout=120, env=lab["env"])
    assert p.returncode != 0, "钩子没拦住 —— 这道门是假的"
    assert "卡B9 ②层" in (p.stderr or ""), p.stderr[-500:]
    assert lab["hits"].read_text(encoding="utf-8").strip(), "钩子日志是空的"


def test_root_comes_from_env_not_from_the_default_constant(tmp_path):
    """`GENEBENCH_ROOT` 一设，`genebench_config` 的默认常量就不再被取用。"""
    p = subprocess.run(
        [PY, "-c", "import genebench_config as c; print(c.GENEBENCH_ROOT)"],
        cwd=REPO, capture_output=True, text=True, timeout=120,
        env={**os.environ, "GENEBENCH_ROOT": str(tmp_path / "r"),
             "PYTHONDONTWRITEBYTECODE": "1"})
    assert p.returncode == 0, p.stderr[-500:]
    assert p.stdout.strip() == str(tmp_path / "r")
    assert "/data" not in p.stdout


def test_where_and_dry_touch_no_data_and_send_no_ssh(tmp_path):
    """§2.4 那几条里**不需要数据面**的两条：`--where` 与 `resolve_topology`。

    临时 `GENEBENCH_ROOT` + 审计钩子（deny=`/data`）+ PATH 垫片。
    """
    lab = _lab(tmp_path, "/data")
    lab["env"]["GENEBENCH_ROOT"] = str(tmp_path / "gb")
    lab["env"]["GENEBENCH_TOPOLOGY"] = "single"
    p = subprocess.run([PY, "-m", "runner.placement", "--topology", "single", "--where"],
                       cwd=REPO, capture_output=True, text=True, timeout=180, env=lab["env"])
    assert p.returncode == 0, (p.stdout + p.stderr)[-1200:]
    where = json.loads(p.stdout)
    assert where["topology"] == "single"
    for k in ("genebench_root", "runner_root", "exec_dest", "guard_log"):
        assert not where[k].startswith("/data"), f"{k} = {where[k]}"
    assert not lab["hits"].read_text(encoding="utf-8").strip(), \
        "审计钩子命中：\n" + lab["hits"].read_text(encoding="utf-8")[:2000]
    assert not lab["ssh"].read_text(encoding="utf-8").strip(), \
        "发了 ssh：\n" + lab["ssh"].read_text(encoding="utf-8")[:500]


def test_single_branch_never_imports_the_dual_module(tmp_path):
    """单机分支不许把 `runner/placement_dual` 拉进来 —— 它是那几个 `/data` 常量的住处。"""
    lab = _lab(tmp_path, "/data")
    lab["env"]["GENEBENCH_ROOT"] = str(tmp_path / "gb")
    p = subprocess.run(
        [PY, "-c", "import sys; sys.path.insert(0, '.'); import runner.placement as P; "
                   "P.runner_root('single'); "
                   "print('placement_dual' in sys.modules)"],
        cwd=REPO, capture_output=True, text=True, timeout=180, env=lab["env"])
    assert p.returncode == 0, (p.stdout + p.stderr)[-900:]
    assert p.stdout.strip().endswith("False"), \
        "单机分支把 runner.placement_dual import 进来了：" + p.stdout


@pytest.mark.skipif(shutil.which("rsync") is None, reason="本机没有 rsync")
def test_place_exec_tree_lands_locally_without_ssh_or_data(tmp_path):
    """§2.4 ③ 单机那一条**真跑一次**：exec 树落到临时根，全程 0 次 ssh、0 次 `/data` open。

    这一条是 N-840 的反面判据：单机路径根本不调 `ops/push_exec_to_f02.sh`
    （那个脚本的 `GENEBENCH_PY` / `GENEBENCH_EXEC_STAGE` 默认指发布方绝对路径 → rc=127）。
    """
    lab = _lab(tmp_path, "/data")
    gb = tmp_path / "gb"
    gb.mkdir(mode=0o700)
    lab["env"]["GENEBENCH_ROOT"] = str(gb)
    p = subprocess.run([PY, "-m", "runner.placement", "--place-exec", "--topology", "single",
                        "--no-verify"],
                       cwd=REPO, capture_output=True, text=True, timeout=900, env=lab["env"])
    assert p.returncode == 0, (p.stdout + p.stderr)[-2000:]
    r = json.loads(p.stdout)
    assert r["topology"] == "single"
    assert not r["dest"].startswith("/data"), r["dest"]
    assert set(r["synced"]) >= {"genetask", "ops", "runner"}
    assert (Path(r["dest"]) / "runner" / "c41" / "runner_core.py").is_file()
    assert not lab["ssh"].read_text(encoding="utf-8").strip(), \
        "落位过程里发了 ssh：\n" + lab["ssh"].read_text(encoding="utf-8")[:800]
    assert not lab["hits"].read_text(encoding="utf-8").strip(), \
        "落位过程里开了 /data：\n" + lab["hits"].read_text(encoding="utf-8")[:2000]
    # 红线 5：落点每一级 0700
    for d in (gb, Path(r["dest"]).parent, Path(r["dest"])):
        assert (d.stat().st_mode & 0o077) == 0, f"{d} 权限 {oct(d.stat().st_mode)}"


def test_guard_always_gets_explicit_root_and_log():
    """单机落位调 `answer_plane_guard` 时**永远显式传** `--root` / `--log`。

    不传就会吃它 CLI 里那两个 `/data` 默认值（N-852 刻意不动那两个默认，
    因为 f02 上每小时那个 systemd timer 正吃它们）。
    """
    src = (REPO / "runner" / "placement.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    calls = 0
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        flat = ast.unparse(n)
        # 只看**外层那次调用**（`_run([...])`）——`ast.walk` 会把参数里的
        # `str(_REPO / … / 'answer_plane_guard.py')` 也当成一个 Call 走一遍。
        if not flat.startswith("_run(") or "answer_plane_guard.py" not in flat:
            continue
        calls += 1
        # 两种口径：容器模式声明的是 `--mount`（没有树可扫），树模式才有 `--root`。
        # **两种都必须显式给 `--log`** —— 那才是会掉回 `/data` 默认值的那个。
        assert "'--log'" in flat or '"--log"' in flat, f"这一处没传 --log：{flat[:200]}"
        if "'--mode', 'container'" not in flat and '"--mode", "container"' not in flat:
            assert "'--root'" in flat or '"--root"' in flat, \
                f"树口径这一处没传 --root：{flat[:200]}"
        else:
            assert "--mount" in flat, f"容器口径这一处没声明 --mount：{flat[:200]}"
    assert calls >= 2, f"placement.py 里只找到 {calls} 处 answer_plane_guard 调用（要两种口径都有）"


# ---------------------------------------------------------------- N-862（卡 F10 已修，xfail 去掉）
def test_single_runner_root_is_pruned_from_the_audited_tree(tmp_path, monkeypatch):
    """单机执行面根**仍然**落在 `$GENEBENCH_ROOT` 里面（那就是裁定 ② 的落点），
    但它必须**不在模式审计里** —— 否则上一个 run 自己写出来的 0644 产物
    （容器/边车落的 `log/llm_log.jsonl` 等）会让下一个 run 的 P0 当场拒（N-862）。

    **修法选的是原 xfail 里写的 ②「P0 的审计根排除执行面 run 根」**（卡 F10，2026-09-14）：
    `ops/guard_modes.RUN_PRODUCT_ROOTS` 把那棵树剪掉，取值与 `runner/placement.runner_root()`
    同源；`<run 产物根>/exec`（**代码树**）作为独立的根加回来，所以 0775 的 `__pycache__`
    照样红。判别力的两面反证在 `ops/test_F10.py::test_run产物剪枝不许伤到判别力`。
    """
    monkeypatch.setenv("GENEBENCH_ROOT", str(tmp_path / "gb"))
    monkeypatch.delenv("GENEBENCH_RUNNER_ROOT", raising=False)
    out = subprocess.run(
        [PY, "-c", "import sys; sys.path.insert(0, '.'); "
                   "import genebench_config as c, runner.placement as P; "
                   "from ops import guard_modes as G; "
                   "print(c.GENEBENCH_ROOT); print(P.runner_root('single')); "
                   "print(G.RUN_PRODUCT_ROOTS[0]); print(G.EXTERNAL_ROOTS[0]); "
                   "print(G.roots.__module__)"],
        cwd=REPO, capture_output=True, text=True, timeout=120,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    assert out.returncode == 0, out.stderr[-800:]
    gb, rr, pruned, audited = (Path(x) for x in out.stdout.split()[:4])
    assert audited == gb, f"审计根不是 $GENEBENCH_ROOT 了（{audited}）—— 这条要重新判"
    assert gb in rr.parents, (
        f"单机执行面根 {rr} 不在 {gb} 下了 —— 裁定 ② 的落点变了，本条判据要重写")
    assert pruned == rr, (
        f"被剪掉的是 {pruned}，而执行面根是 {rr} —— 两处不同源，"
        f"run 产物又会回到审计里（N-862）")


# ===========================================================================
# ③ 遮蔽层：做不到，如实记一条
# ===========================================================================

def test_layer3_shadowing_is_not_available_here():
    """**第 ③层（把 `/data` 真遮掉）在本项目的机器上起不来 —— 这条把结论写成可跑的记录。**

    实测（2026-09-14，f02 = Ubuntu 24.04 / 无 sudo）：
      * `unshare -r -m …` → `unshare: write failed /proc/self/uid_map: Operation not permitted`
      * `bwrap --dev-bind / / --tmpfs /data …` → `bwrap: setting up uid map: Permission denied`
      * 成因：`kernel.apparmor_restrict_unprivileged_userns = 1`（Ubuntu 24.04 默认），
        翻它要 root；docker.io 被墙，也装不了别的东西。
    所以本门的 `/data` 不可及是**第 ②层断言**出来的：能证明「我们的 Python 没去开它」，
    **不能**证明「就算去开也开不到」。非 Python 子进程（docker / rsync / git）由
    `strace -f` 另外量（本卡在 f02 上量过：exec 树落位 0 命中）。
    本条不判红 —— 它记录的是**这台机器的能力**，不是仓库的缺陷。
    """
    have = {n: shutil.which(n) for n in ("unshare", "bwrap", "strace")}
    works = False
    if have["unshare"]:
        p = subprocess.run(["unshare", "-r", "-m", "true"], capture_output=True,
                           text=True, timeout=60)
        works = p.returncode == 0
    print(textwrap.dedent(f"""
        [卡 B9 ③层] 本机遮蔽能力：{have}
        unshare -r -m 可用 = {works}
        可用时，这道门的更强跑法是：
          unshare -r -m sh -c 'mount -t tmpfs none /data; <整条 §2.4 命令>'
        不可用时，射程止于第 ②层（见本函数 docstring）。"""))
    assert isinstance(works, bool)


# ===========================================================================
# 真跑那一段：允许大声 skip，**逐条打出为什么**
# ===========================================================================

def _preconditions() -> list[str]:
    miss: list[str] = []
    if shutil.which("docker") is None:
        miss.append("没有 docker：真跑要容器运行时（`sh harnesses/build.sh <id>` 也要）")
    else:
        p = subprocess.run(["docker", "info"], capture_output=True, timeout=120)
        if p.returncode != 0:
            miss.append("docker 命令在，但连不上 daemon（`docker info` 失败）")
    if not (Path.home() / ".config" / "genebench" / "secrets.env").is_file():
        miss.append("没有 ~/.config/genebench/secrets.env：真跑要模型 key（README §2.1）")
    import genebench_config as cfg                                   # noqa: PLC0415
    gw = f"http://{cfg.GATEWAY_HOST}:{cfg.GATEWAY_PUBLIC_PORT}/healthz"
    try:
        import urllib.request                                        # noqa: PLC0415
        with urllib.request.urlopen(gw, timeout=5) as r:             # noqa: S310
            if json.loads(r.read()).get("channel") != "public":
                miss.append(f"{gw} 起来了，但 channel 不是 public")
    except Exception as e:                                           # noqa: BLE001
        miss.append(f"公开通道网关打不通（{gw}）：{type(e).__name__} —— "
                    f"`ops/public_gateway.sh start`")
    import runner.placement as PL                                    # noqa: PLC0415
    prov = PL.runner_root("single") / "provider"
    if not prov.is_dir() or not any(prov.iterdir()):
        miss.append(f"执行面上没有 provider（{prov}）—— 单机形态要从 "
                    f"$GENEBENCH_ROOT/snapshots/public_v1/qlib_provider 本机 cp 过去")
    miss += _container_to_host_check()
    return miss


def _container_to_host_check() -> list[str]:
    """**单机形态特有的那一条**：容器打不打得到宿主上的网关（README §2.3 ①）。

    双机形态下这条不存在（容器打的是另一台机器，走 FORWARD 链，docker 自己开了）；
    单机形态下包走**宿主自己的 INPUT 链**，而 docker 不在那条链上插规则 ——
    要机器主人跑一条 `sudo ufw allow from <容器网段> to any port <网关端口> proto tcp`。
    **量不到就写「没量到」，不要写「通过」。**
    """
    if shutil.which("docker") is None:
        return []                                   # 上面已经报过「没有 docker」
    import genebench_config as cfg                                   # noqa: PLC0415
    from runner.c41 import runner_core as RC                         # noqa: PLC0415
    img = next((i for i in ("gb-base:bookworm-r1", "alpine:3.20", "busybox:latest")
                if subprocess.run(["docker", "image", "inspect", i],
                                  capture_output=True, timeout=60).returncode == 0), None)
    if img is None:
        return ["容器打不打得到宿主网关：**没量到**（本机没有 gb-base / alpine / busybox 任一镜像）"]
    net = "gb-b9-c2h-probe"
    subprocess.run(["docker", "network", "rm", net], capture_output=True, timeout=60)
    mk = subprocess.run(["docker", "network", "create", "--subnet", RC.EGRESS_SUBNET, net],
                        capture_output=True, text=True, timeout=120)
    if mk.returncode != 0:
        return [f"容器打不打得到宿主网关：**没量到**（建探针网 {RC.EGRESS_SUBNET} 失败："
                f"{(mk.stderr or '').strip()[:120]}）"]
    try:
        code = ("import socket,sys; s=socket.socket(); s.settimeout(6); "
                "sys.exit(s.connect_ex((%r, %d)))" % (cfg.GATEWAY_HOST, cfg.GATEWAY_PUBLIC_PORT))
        rc = None
        for probe in (["python3", "-c", code],
                      ["nc", "-z", "-w6", cfg.GATEWAY_HOST, str(cfg.GATEWAY_PUBLIC_PORT)]):
            r = subprocess.run(["docker", "run", "--rm", "--network", net, img, *probe],
                               capture_output=True, text=True, timeout=180)
            if r.returncode != 127:            # 127 = 这个镜像里没有这个探针工具，换一个
                rc = r.returncode
                break
        if rc is None:
            return [f"容器打不打得到宿主网关：**没量到**（镜像 {img} 里既没有 python3 也没有 nc）"]
        if rc != 0:
            return [f"**容器打不到宿主网关** {cfg.GATEWAY_HOST}:{cfg.GATEWAY_PUBLIC_PORT}"
                    f"（从 {RC.EGRESS_SUBNET} 出发，rc={rc}）—— README §2.3 ① 那条"
                    f" `sudo ufw allow from {RC.EGRESS_SUBNET} to any port "
                    f"{cfg.GATEWAY_PUBLIC_PORT} proto tcp` 还没跑（要 root）"]
    except subprocess.TimeoutExpired:
        return ["**容器打不到宿主网关**（探针超时）—— README §2.3 ①"]
    finally:
        subprocess.run(["docker", "network", "rm", net], capture_output=True, timeout=60)
    return []


def test_real_run_preconditions():
    """**skip 不是绿**：真跑那一段缺哪条前置，这里逐条打出来。

    2026-09-14 在 f02 上跑这道门时，缺的是最后一条之外的另一条 —— **容器打不到宿主网关**
    （README §2.3 ① 那条 `sudo ufw allow from <容器网段> to any port <网关端口>`，
    要 root，本机无 sudo）。实测：从运行时真用的 `172.31.241.0/24` 出发，
    `192.168.1.219:18081` / `:22` / `172.31.241.1` / docker0 / tailscale 地址**全部超时**，
    而同一个容器打**另一台机器**的 22 端口是通的（FORWARD 链 docker 开了，INPUT 链没有）。
    那一条不是本仓库的缺陷，是单机形态本来就要机器主人执行的一步。
    """
    miss = _preconditions()
    if miss:
        pytest.skip("真跑前置没齐（逐条）：\n  - " + "\n  - ".join(miss))
    assert True
