#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""卡 U：终核卡在**外部 clone** 上抓到的那条 block（N-818）与四条「第一屏就会撞」的门。

每条都写成**双向**：判据被改回去时当场红，判据被放宽成恒绿时反面那一半当场红。

* **N-818** —— `ops/guard_modes.py` 的 `check()` 跟随符号链接取 mode、`harden()` 却跳过
  符号链接，**两者口径相反**。于是 `python3.12 -m venv $GB/env`（README §2.1 逐字那一行）
  留下的 `bin/python*` 三条软链指向系统解释器（0755、root 所有）→ `check()` 判红线 5 违例
  → 网关**拒绝启动**，而提示语让人去跑 `--harden`，`harden()` 在结构上又永远修不好它。
  这里的四条钉住修法：口径一致、判别力不降、提示语不说空话。
* **N-819** —— `ops/test_pack_release.py` 的守卫只守落位产物，不守打包器真正要的输入，
  于是外部 clone 上**落位前 skip、落位后 3 failed**（越照文档做对越会看到红）。
* **N-821 / N-822 / N-823** —— `ops/selfcheck_public.py` 与 `ops/test_env.py` 的三处文案。
"""
from __future__ import annotations

import importlib.util
import os
import pathlib
import stat
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

_spec = importlib.util.spec_from_file_location("_guard_u", REPO / "ops" / "guard_modes.py")
G = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(G)


# ═════════════════════════════ N-818：守门与符号链接 ═════════════════════════════

@pytest.fixture
def root(tmp_path, monkeypatch):
    """一棵**只有 `EXTERNAL_ROOTS` 这一个根**的树（仓库根用一个不存在的路径顶掉）。"""
    monkeypatch.setattr(G, "EXTERNAL_ROOTS", ())
    monkeypatch.setattr(G, "ANSWER_PLANE_ROOTS", (str(tmp_path / "reference"),))
    return tmp_path


@pytest.fixture
def outside_0755(tmp_path_factory):
    """根**之外**一个 0755 的实体文件 —— 系统解释器（`/usr/bin/python3.12`）的替身。

    用替身不用真解释器：真解释器在别的机器上可能不是 0755，那样这条测试就成了
    「这台机器恰好如此」的另一种说法 —— 与 D-06 同族。
    """
    d = tmp_path_factory.mktemp("system_like")
    p = d / "python3.12"
    p.write_text("#!/bin/sh\n", encoding="utf-8")
    p.chmod(0o755)
    return p


def test_根下真实的0644文件和0775目录照样判红(root):
    """**判别力的正面**：这一条不过，N-818 的修法就是把门拆了。"""
    (root / "loose_dir").mkdir()
    (root / "loose_dir" / "loose.txt").write_text("x", encoding="utf-8")
    G.harden(root)
    os.chmod(root / "loose_dir", 0o775)
    os.chmod(root / "loose_dir" / "loose.txt", 0o644)
    bad = G.check(root)
    assert any("loose_dir" in x and "0o775" in x for x in bad), bad
    assert any("loose.txt" in x and "0o644" in x for x in bad), bad
    # 反面：`--harden` 对**真实**的这两件必须真收得掉，且收完就绿。
    assert G.harden(root) >= 2
    assert G.check(root) == [], G.check(root)


def test_指向根外0755文件的软链不判红_而软链本身还在盘上(root, outside_0755):
    """**判别力的反面**（N-818 本体）：`bin/python -> /usr/bin/python3.12` 这种链
    不该判红 —— 判了也修不掉（`harden()` 不替人 chmod 根外的东西），
    而一道**永远红且修不好**的门只会被绕过（与恒绿同族）。"""
    (root / "env" / "bin").mkdir(parents=True)
    link = root / "env" / "bin" / "python3.12"
    link.symlink_to(outside_0755)
    G.harden(root)
    bad = G.check(root)
    assert bad == [], f"指向根外 0755 实体文件的软链不该判红，实得 {bad}"
    assert link.is_symlink(), "守门不许替人删链接"
    assert oct(outside_0755.stat().st_mode & 0o777) == "0o755", "守门不许去改根外那个文件"


def test_venv形状的三条软链_harden之后守门退0(root, outside_0755):
    """把 `python3.12 -m venv` 的 `bin/` 逐条复刻出来：三条链、两跳、终点在根外。

    这正是 README §2.1 / 手册 §1.2 让外部用户敲的那一行的产物
    （2026-09-13 卡 Tfin 在干净 Ubuntu 上实测：`python -> python3.12`、
    `python3 -> python3.12`、`python3.12 -> /usr/bin/python3.12`）。
    """
    b = root / "env" / "bin"
    b.mkdir(parents=True)
    (b / "python3.12").symlink_to(outside_0755)
    (b / "python3").symlink_to("python3.12")
    (b / "python").symlink_to("python3.12")
    (root / "env" / "pyvenv.cfg").write_text("home = /usr/bin\n", encoding="utf-8")
    os.chmod(root / "env" / "pyvenv.cfg", 0o644)           # 外部 umask 022 的真实产物
    # ① 实体文件照样被抓到 —— 门没瞎
    assert any("pyvenv.cfg" in x for x in G.check(root)), G.check(root)
    # ② `--harden`（文档给的修法）这一次必须真修得好，且**一次就好**
    assert G.harden(root) >= 1
    assert G.check(root) == [], G.check(root)
    # ③ 再 harden 一次收紧 0 个条目、门仍然绿 —— 不是「每次都要再跑一遍」的死循环
    assert G.harden(root) == 0
    assert G.check(root) == []


def test_check与harden对符号链接是同一个口径(root, outside_0755):
    """**病灶本身**：`check()` 报得出、而 `harden()` 修不掉的**模式违例**，一条都不许有。

    反面判别：把 `check()` 里那条 `if islink: continue` 删掉，本条当场红
    （`harden()` 返回 0，`check()` 仍报三条）。
    """
    b = root / "env" / "bin"
    b.mkdir(parents=True)
    (b / "python").symlink_to(outside_0755)
    (root / "dir_link").symlink_to(outside_0755.parent)
    for _ in range(3):
        n = G.harden(root)
        if n == 0:
            break
    mode_violations = [x for x in G.check(root) if "对组/其它开放" in x]
    assert mode_violations == [], (
        "`harden()` 收紧 0 个条目之后 `check()` 还在报模式违例 —— "
        f"两者口径又岔开了：{mode_violations}")


def test_答案面根下的软链仍然一律判违例(root, outside_0755):
    """**没有被一起放宽**：答案面根（`reference/` `runs_in/` `gold/`）下的符号链接
    判据一个字不改 —— 那条门管的是「链接指到哪去了」，与模式无关（裁定 2026-09-05）。"""
    ref = root / "reference"
    ref.mkdir()
    (ref / "live").symlink_to(outside_0755)
    (ref / "dangling").symlink_to("/nowhere/at/all")
    G.harden(root)
    bad = [x for x in G.check(root) if "符号链接" in x]
    assert any("live" in x and "指向" in x for x in bad), bad
    assert any("dangling" in x and "断链" in x for x in bad), bad


def test_提示语不对harden修不好的情形说去harden(root, outside_0755):
    """③：**一句修不好的提示比没有提示更贵** —— 它让人以为自己哪一步敲错了。"""
    # (a) 纯模式违例：照旧指向 `--harden`
    (root / "loose.txt").write_text("x", encoding="utf-8")
    os.chmod(root / "loose.txt", 0o644)
    hint = G.fix_hint(G.check(root))
    assert "--harden" in hint and "修不好" not in hint, hint
    G.harden(root)

    # (b) 答案面软链：必须明说 `--harden` 修不好
    ref = root / "reference"
    ref.mkdir()
    (ref / "dangling").symlink_to("/nowhere/at/all")
    bad = G.check(root)
    assert bad, "夹具没造出违例"
    hint = G.fix_hint(bad)
    assert "修不好" in hint, hint
    with pytest.raises(SystemExit) as e:
        G.assert_modes(root, who="网关")
    msg = str(e.value)
    assert "修不好" in msg, msg
    assert msg.rstrip().splitlines()[-1].strip() != "修：python3 ops/guard_modes.py --harden", msg


def test_harden不去碰符号链接的目标(root, outside_0755):
    """`harden()` 的 `if islink: continue` 是**故意**的：它不替人改根外的东西。
    这一条钉住它 —— 哪天有人为了「让 check 绿」改成跟随链接 chmod，那就成了
    「守门悄悄改了系统文件」。"""
    (root / "link").symlink_to(outside_0755)
    G.harden(root)
    assert oct(outside_0755.stat().st_mode & 0o777) == "0o755"
    assert stat.S_ISLNK((root / "link").lstat().st_mode)


# ═════════════════════════════ N-819：打包器测试的守卫 ═════════════════════════════

def _pack_mod():
    from ops.release import pack_public_provider as PP
    return PP


def test_打包器守卫盖住打包器的全部必需输入(monkeypatch):
    """守卫必须盖到 `$GENEBENCH_ROOT/scratch/v1_union.txt` —— 那是**打包前的发布方
    中间件**，既不在仓库里也不在三件附件里（附件里那份在
    `snapshots/public_v1/universe/v1_union.txt`，**路径不同**）。

    判据**从 `PP.components()` 现算**，所以这条同时钉住「以后加组件也会被盖到」。
    """
    import ops.test_pack_release as T

    seen: list[pathlib.Path] = []
    monkeypatch.setattr(T, "_need", lambda p: seen.append(pathlib.Path(p)))
    T._need_packager_inputs()

    PP = _pack_mod()
    want: list[pathlib.Path] = []
    for comp in PP.components():
        if not comp.get("required"):
            continue
        src = pathlib.Path(comp["src"])
        if comp["kind"] in ("dir", "file"):
            want.append(src)
        elif comp["kind"] == "pairs":
            want += [pathlib.Path(p) for _a, p in comp["pairs"]]
        elif comp["kind"] == "listed":
            want += [src / rel for rel in comp["items"]]
    assert want, "组件表读不出来"
    missing = sorted(str(p) for p in want if p not in seen)
    assert not missing, f"守卫漏了打包器要的这些输入：{missing[:5]}"
    assert any(p.name == "v1_union.txt" and p.parent.name == "scratch" for p in seen), \
        f"守卫没盖到打包前的 scratch/v1_union.txt —— N-819 会复发：{[str(p) for p in seen][:5]}"


def test_打包器那三条在发布方机器上照样真跑_不是被skip掉(tmp_path):
    """**判别力不许被 skip 吃掉**：发布方机器上那些输入全在，三条必须真跑。

    外部机器上这条自己 skip（那正是 N-819 要的行为），所以它不会变成「只在 f01 绿」。
    """
    PP = _pack_mod()
    absent = []
    for comp in PP.components():
        if not comp.get("required"):
            continue
        src = pathlib.Path(comp["src"])
        if comp["kind"] in ("dir", "file"):
            cand = [src]
        elif comp["kind"] == "pairs":
            cand = [pathlib.Path(p) for _a, p in comp["pairs"]]
        else:
            cand = [src / rel for rel in comp["items"]]
        absent += [p for p in cand if not p.exists()]
    if absent:
        pytest.skip(f"这台不是发布方机器（缺 {absent[0]} 等 {len(absent)} 件）")
    import ops.test_pack_release as T
    T._need_packager_inputs()          # 全在 → 一条都不许 skip
    entries, _missing = PP.collect()
    assert any(e.arcname == "universe/v1_union.txt" for e in entries)


# ═════════════════════════ N-821 / N-822 / N-823：自检文案 ═════════════════════════

def _self_mod():
    spec = importlib.util.spec_from_file_location(
        "_selfcheck_u", REPO / "ops" / "selfcheck_public.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_附件候选目录里有仓库根_否则照文档做完第一次自检必然看不到附件(monkeypatch):
    """README §2.1a 的 `curl -L -O` 紧接在 §2.1 的 `cd $REPO` 之后 —— 包落在**仓库根**下。"""
    S = _self_mod()
    cands = S._downloads_candidates(None)
    assert S.REPO_ROOT in cands, \
        f"仓库根不在候选里 —— README 让人下到那儿，自检却不去那儿找：{[str(p) for p in cands]}"
    # 反面：`--downloads` 指过来时仍然只认那一个，不许偷偷多找几处
    assert S._downloads_candidates("/tmp/xyz") == [pathlib.Path("/tmp/xyz")]


def test_找过的目录不重复打印(monkeypatch, tmp_path):
    """`$GENEBENCH_ROOT` 与「仓库父目录」重合是常态（`REPO=$GB/repo`），
    重合时那句「找过：…」会把同一个路径打印两遍。"""
    S = _self_mod()
    gb = tmp_path / "gb"
    (gb / "repo").mkdir(parents=True)
    monkeypatch.setattr(S, "REPO_ROOT", gb / "repo")
    monkeypatch.setenv("GENEBENCH_ROOT", str(gb))
    monkeypatch.chdir(gb / "repo")
    cands = S._downloads_candidates(None)
    keys = [str(p.resolve()) for p in cands]
    assert len(keys) == len(set(keys)), f"候选目录有重复：{keys}"
    assert str((gb / "downloads").resolve()) in keys


def test_只缺一个包时第5项指回第2项_而不是说树不完整(monkeypatch):
    """真因是 `genetask/packager.py` 的 `import yaml` 抛 `ModuleNotFoundError` ——
    树是完整的、目录也是对的。原文案把用户支去查一件没坏的事。"""
    S = _self_mod()
    trace = ("Traceback (most recent call last):\n"
             '  File "ops/freeze_v10.py", line 1, in <module>\n'
             "ModuleNotFoundError: No module named 'yaml'")
    monkeypatch.setattr(S, "_run_in_repo", lambda *a, **k: (1, "", trace))
    it = S.check_freeze()
    blob = f"{it.detail}\n{it.fix}"
    assert it.status == S.RED
    assert "ModuleNotFoundError" in blob, blob
    assert "第 2 项" in blob, blob
    assert "这棵树不完整" not in blob, blob

    # 反面：不是 import 错误时，原来那句诊断要留着（别把它一起删了）
    monkeypatch.setattr(S, "_run_in_repo", lambda *a, **k: (1, "", "什么都没打印"))
    it2 = S.check_freeze()
    blob2 = f"{it2.detail}\n{it2.fix}"
    assert it2.status == S.RED and "这棵树不完整" in blob2, blob2


def test_test_env的开头不再说两个附件():
    """N-810 修了四处，`ops/test_env.py` 的 docstring 是漏掉的第五处。"""
    head = (REPO / "ops" / "test_env.py").read_text(encoding="utf-8")[:2000]
    assert "两个附件落位" not in head, "第五处还在"
    assert "发布附件落位" in head
