# -*- coding: utf-8 -*-
"""卡 F10（用户裁定 ①）：**五条代码缺陷一次修完**，这份测试守的是它们各自的**根因**。

五条的共同形状是「**在发布方那台机器上永远不显形**」：

* **N-857** `ops/guard_modes.py` 模块级 `import genebench_config`，而 exec 白名单里没有它 ——
  注入器 P0 动态加载这个文件，于是**任何新铺的执行面第一次真跑就炸**。f02 上双机现在能跑，
  只因为那棵 exec 树是 2026-09-10 的旧版；**下一次 `push_exec_to_f02.sh` 会打断双机生产**。
* **N-855** `ops/run_f02_a1.py` 的 provider 父目录写死 `/data/genebench_runner/provider`，
  而同一条路径上 `ops/run_joblist.probe_f02_provider` 查 `runner_root()/provider` —— **两处不同源**。
  f02 上那份恰好存在（双机遗留），于是表现为「**跑起来 ok，只是读了另一棵树**」：**它不报错**。
* **N-856** `runner/c41/egress_proxy.py` 模块级 `import h11`，而 `exec/vendor/h11`
  **不在仓库里、也没有任何文档化步骤会铺它** —— f02 上那份是手工遗留物。
* **N-862 / N-861** P0 审计的那棵树里躺着**上一个 run 自己的产物**（单机形态下执行面根
  在 `$GENEBENCH_ROOT` 里面）；以及 `--harden` 不是一次性的 —— git 一动 `.git/index` 回 0644。
* **N-851（= N-840）** `ops/push_exec_to_f02.sh` 的 `GENEBENCH_PY` / `GENEBENCH_EXEC_STAGE`
  默认发布方绝对路径且**静默使用** → 外部双机用户 rc=127，而这两个变量在文档里 grep 命中 0 次。

**每一条都配一面反证**：判别力不是「改了」，是「该拦的还拦得住」。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import genebench_config as cfg                                  # noqa: E402
from ops import guard_modes as G                                # noqa: E402
from runner import placement as PL                              # noqa: E402

PUSH_EXEC_SH = REPO / "ops" / "push_exec_to_f02.sh"
GUARD_PY = REPO / "ops" / "guard_modes.py"

#: 发布方那台的四个落点。**这里出现它们是故意的**：这条断言的全部内容就是
#: 「不设任何环境变量时，取值与本卡改动之前逐字相同」（与 `ops/test_A9.py` 同一条纪律）。
PUBLISHER_PATHS = {
    "GB_ROOT": "/data/shared/genebench",
    "PY": "/data/shared/genebench/env/bin/python",
    "F02": "ljn@192.168.1.219",
    "DEST": "/data/genebench_runner/exec",
    "STAGE": "/data/shared/genebench/scratch/exec_push",
}
_PUSH_ENV_KEYS = ("GENEBENCH_ROOT", "GENEBENCH_PY", "GENEBENCH_EXEC_STAGE",
                  "GENEBENCH_EXEC_DEST", "GENEBENCH_F02")


def _clean_env(**extra) -> dict:
    env = {k: v for k, v in os.environ.items()
           if k not in _PUSH_ENV_KEYS and k != "GENEBENCH_RUNNER_ROOT"}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.update(extra)
    return env


def _tighten(root: Path) -> None:
    """把一棵夹具树收紧到 0700/0600 —— 之后再单独放松要测的那几个，判据才干净。"""
    for p in [root, *root.rglob("*")]:
        p.chmod(0o700 if p.is_dir() else 0o600)


# ===========================================================================
# N-857：守门不许在执行面上静默跳过
# ===========================================================================
def test_守门里没有模块级的genebench_config_import():
    """exec 白名单里没有 `genebench_config.py`，所以这个 import **不能是模块级**。

    反过来说也成立：哪天有人把它收进白名单了，这条断言要一起改 —— 那时才是真的
    「发布方配置上执行面」，得先逐行核里面有没有不该出去的东西。
    """
    src = GUARD_PY.read_text(encoding="utf-8")
    assert re.search(r"^import genebench_config", src, re.M) is None, \
        "ops/guard_modes.py 又回到了模块级 import genebench_config —— 执行面会在 P0 当场炸（N-857）"
    assert "except ModuleNotFoundError" in src and "CONFIG_AVAILABLE" in src


def test_发布方那台的审计根逐字节不变():
    """**最硬的一条回归锁**：f01 上 `genebench_config` import 得到，两张表一个值不变。"""
    assert G.CONFIG_AVAILABLE is True
    assert G.EXTERNAL_ROOTS == (str(cfg.GENEBENCH_ROOT),)
    assert G.ANSWER_PLANE_ROOTS == (str(cfg.GENEBENCH_ROOT / "reference"),
                                    str(cfg.GENEBENCH_ROOT / "runs_in"),
                                    str(cfg.GENEBENCH_ROOT / "gold"))
    # 双机的执行面根在 `$GENEBENCH_ROOT` **之外** → 剪枝与加回来的那棵都不存在 → 行为不变
    assert G.RUN_PRODUCT_ROOTS == (str(cfg.GENEBENCH_ROOT / "genebench_runner"),)
    assert not Path(G.RUN_PRODUCT_ROOTS[0]).exists()
    assert [str(x) for x in G.roots()] == [str(REPO), str(cfg.GENEBENCH_ROOT)]


def test_没有genebench_config的树上守门照样咬得动(tmp_path):
    """**判别力的正面证明**：一棵**没有** `genebench_config.py` 的树（= 执行面那棵），
    守门仍然抓得到 0644 文件 / 0775 目录 / 0775 `__pycache__`，并且**说出自己降级了**。

    这一条不是形式：`import` 改成可选之后，最容易出的错就是「它跑了、什么都没查、退 0」。
    """
    tree = tmp_path / "exec"
    (tree / "ops").mkdir(parents=True)
    shutil.copyfile(GUARD_PY, tree / "ops" / "guard_modes.py")
    (tree / "runner" / "__pycache__").mkdir(parents=True)
    (tree / "runner" / "__pycache__" / "x.pyc").write_text("x", encoding="utf-8")
    (tree / "loose.txt").write_text("x", encoding="utf-8")
    _tighten(tree)
    (tree / "loose.txt").chmod(0o644)
    (tree / "runner" / "__pycache__").chmod(0o775)
    (tree / "runner" / "__pycache__" / "x.pyc").chmod(0o644)

    p = subprocess.run([sys.executable, "ops/guard_modes.py"], cwd=str(tree),
                       env=_clean_env(), capture_output=True, text=True, timeout=300)
    assert p.returncode == 1, f"守门在一棵有 0644 的树上退了 {p.returncode}：{p.stdout}{p.stderr}"
    err = p.stderr
    assert "loose.txt" in err and "__pycache__" in err, err[:2000]
    assert "没有 genebench_config" in err, "降级了却没说 —— 无声降级与恒绿同族\n" + err[:2000]

    # `--harden` 收得干净 → 退 0（同一棵树，同一个判据）
    p2 = subprocess.run([sys.executable, "ops/guard_modes.py", "--harden"], cwd=str(tree),
                        env=_clean_env(), capture_output=True, text=True, timeout=300)
    assert p2.returncode == 0, p2.stdout + p2.stderr
    assert "收紧" in p2.stdout


def test_P0在守门没查这棵树时当场红(tmp_path, monkeypatch):
    """**N-857 的第二半**：守门可以降级，但不许降级成「什么都没查」。

    真造一个现场（`_load_guard` 换成一个 `roots()` 返回空的桩），验 P0 当场红；
    再把它换成一个**确实把这棵树列进审计根**的桩，验这一条不误红。
    """
    from runner import inject as INJ

    class _Blind:
        @staticmethod
        def roots(repo=None):
            return []

        @staticmethod
        def check(repo=None):
            return []

    monkeypatch.setattr(INJ, "_load_guard", lambda: _Blind)
    bad = INJ.preflight(tmp_path / "run1", require_docker=False, check_modes=True)
    assert any("没把注入器自己这棵树" in x for x in bad), bad

    class _Seeing:
        @staticmethod
        def roots(repo=None):
            return [Path(INJ.__file__).resolve().parents[1]]

        @staticmethod
        def check(repo=None):
            return []

    monkeypatch.setattr(INJ, "_load_guard", lambda: _Seeing)
    ok = INJ.preflight(tmp_path / "run2", require_docker=False, check_modes=True)
    assert not any("没把注入器自己这棵树" in x for x in ok), ok


# ===========================================================================
# N-862 / N-861：上一个 run 不许让下一个 run 起不来
# ===========================================================================
def test_run产物剪枝不许伤到判别力(tmp_path, monkeypatch):
    """**反面测试（本卡要求）**：造一个该拦的 → 必红；造一个 run 自己的正常产物 → 必绿。

    第三条是**剪枝本身的反证**：把 `RUN_PRODUCT_ROOTS` 清空，那个 run 产物立刻变红 ——
    证明上面那条「必绿」不是因为夹具没造对。
    """
    gb = tmp_path / "gb"
    (gb / "reference").mkdir(parents=True)
    rr = gb / "genebench_runner"
    work = rr / "m6" / "runs" / "runs" / "r1" / "work"
    work.mkdir(parents=True)
    pycache = rr / "exec" / "runner" / "__pycache__"
    pycache.mkdir(parents=True)
    ans = gb / "reference" / "a.json"
    ans.write_text("{}", encoding="utf-8")
    pyc = pycache / "x.pyc"
    pyc.write_text("x", encoding="utf-8")
    art = work / "artifact.json"
    art.write_text("{}", encoding="utf-8")
    _tighten(gb)
    ans.chmod(0o644)                      # 该拦的：答案面根下的 0644
    pycache.chmod(0o775)                  # 该拦的：执行面**代码树**里 0775 的 __pycache__
    pyc.chmod(0o644)
    art.chmod(0o644)                      # run 自己的正常产物：容器按它自己的 umask 写的

    monkeypatch.setattr(G, "EXTERNAL_ROOTS", (str(gb),))
    monkeypatch.setattr(G, "ANSWER_PLANE_ROOTS", (str(gb / "reference"),))
    monkeypatch.setattr(G, "RUN_PRODUCT_ROOTS", (str(rr),))
    j = "\n".join(G.check(tmp_path / "norepo"))
    assert str(ans) in j, "答案面根下的 0644 没被抓到 —— 判别力掉了\n" + j[:1500]
    assert str(pycache) in j and str(pyc) in j, \
        "执行面代码树（<run 产物根>/exec）里的 0775 __pycache__ 没被抓到\n" + j[:1500]
    assert str(art) not in j, "run 自己的正常产物被判红了 —— 下一个 run 又起不来（N-862）"

    monkeypatch.setattr(G, "RUN_PRODUCT_ROOTS", ())
    j2 = "\n".join(G.check(tmp_path / "norepo"))
    assert str(art) in j2, "剪枝关掉之后它也不红 —— 上面那条「必绿」是空的"


@pytest.mark.skipif(shutil.which("git") is None, reason="本机没有 git")
def test_harden把自己变成一次性的(tmp_path, monkeypatch):
    """**N-861**：`--harden` 之后再动一次 git，`.git/` 下不许回来 0644。

    对照组（不设 `core.sharedRepository`）必须**回来**，否则这条测试是空的 ——
    2026-09-14 f01 实测：对照组回来 8 条（index、refs/heads/master、3 个 object 目录 + 3 个 object）。
    """
    monkeypatch.setattr(G, "EXTERNAL_ROOTS", ())
    monkeypatch.setattr(G, "ANSWER_PLANE_ROOTS", ())
    monkeypatch.setattr(G, "RUN_PRODUCT_ROOTS", ())
    old_umask = os.umask(0o022)
    try:
        def mk(name: str) -> Path:
            root = tmp_path / name
            root.mkdir()
            subprocess.run(["git", "init", "-q", str(root)], check=True, timeout=120)
            for kv in (("user.email", "f10@example.invalid"), ("user.name", "f10")):
                subprocess.run(["git", "-C", str(root), "config", *kv], check=True, timeout=60)
            (root / "a.txt").write_text("hi", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "a.txt"], check=True, timeout=60)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "t1"], check=True, timeout=120)
            return root

        def commit_again(root: Path) -> None:
            (root / "b.txt").write_text("more", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "b.txt"], check=True, timeout=60)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "t2"], check=True, timeout=120)

        def dotgit_red(root: Path) -> list[str]:
            return [x for x in G.check(root) if f"{root}/.git" in x]

        fixed = mk("fixed")
        G.harden(fixed)
        assert G.harden_git_repos(fixed) == [str(fixed)]
        assert G.harden_git_repos(fixed) == [], "harden_git_repos 不幂等"
        commit_again(fixed)
        assert not dotgit_red(fixed), \
            "设了 core.sharedRepository 还是回来了：\n  " + "\n  ".join(dotgit_red(fixed)[:8])

        ctrl = mk("ctrl")                 # 对照：只 chmod，不设 core.sharedRepository
        G.harden(ctrl)
        commit_again(ctrl)
        assert dotgit_red(ctrl), "对照组没有复现 N-861 —— 这条测试是空的"
    finally:
        os.umask(old_umask)


# ===========================================================================
# N-856：h11 随 exec 树船运，不靠遗留物
# ===========================================================================
def test_vendor只有一份实现():
    """两份清单 = 两个真相（`OPS_FILES` 那一对已经为此付过一次代价）。
    所以这里**不造第二张表**：shell 脚本调的就是 `runner/placement.stage_vendor`。"""
    sh = PUSH_EXEC_SH.read_text(encoding="utf-8")
    assert "-m runner.placement --stage-vendor" in sh, "push_exec 没有铺 vendor（N-856）"
    assert "VENDOR_PKGS=(" not in sh, "shell 里又抄了一张 vendor 清单 —— 两处会漂"
    assert PL.VENDOR_PKGS == ("h11",)
    assert "stage_vendor(stage)" in (REPO / "runner" / "placement.py").read_text(encoding="utf-8"), \
        "单机落位没有铺 vendor —— 两条路径又分叉了"


def test_stage_vendor真把h11铺出来(tmp_path):
    from runner.c41 import egress_proxy as EP
    got = PL.stage_vendor(tmp_path)
    h11 = tmp_path / "vendor" / "h11"
    assert (h11 / "__init__.py").is_file() and (h11 / "_readers.py").is_file()
    assert not list(h11.rglob("*.so")) and not list(h11.rglob("__pycache__"))
    assert EP.H11_VERSION in got["vendored"]["h11"], got
    # 铺出来的就是**网关环境自己那份字节**（裁定 2026-09-05），不是「版本号相同」
    import h11 as _h
    src = Path(_h.__file__).resolve().parent
    assert (h11 / "_readers.py").read_bytes() == (src / "_readers.py").read_bytes()


def test_h11缺了要说人话(tmp_path):
    """**判别力**：造一个真的「没有 h11」的现场，报错必须说清楚该怎么铺。

    在此之前它是一条裸的 `ModuleNotFoundError: No module named 'h11'` ——
    而正确的下一步（重铺 exec 树）在报错里一个字都没有。
    """
    d = tmp_path / "runner" / "c41"
    d.mkdir(parents=True)
    shutil.copyfile(REPO / "runner" / "c41" / "egress_proxy.py", d / "egress_proxy.py")
    p = subprocess.run([sys.executable, "-S", "-c", "import egress_proxy"], cwd=str(d),
                       env={"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"},
                       capture_output=True, text=True, timeout=300)
    assert p.returncode != 0
    assert "vendor/h11" in p.stderr, p.stderr[-2000:]
    assert "push_exec_to_f02.sh" in p.stderr and "placement" in p.stderr, p.stderr[-2000:]


# ===========================================================================
# N-855：provider 根与探针同源，不一致当场拒
# ===========================================================================
def test_provider根与探针同源():
    from ops import run_f02_a1 as A1
    from ops import run_joblist as RJ
    assert A1.RUNNER_PROVIDER_ROOT == Path(RJ.runner_root("dual")) / "provider"
    assert str(A1.RUNNER_PROVIDER_ROOT) == "/data/genebench_runner/provider", \
        "发布方那台的取值变了 —— 双机语义必须逐字不变"
    src = (REPO / "ops" / "run_f02_a1.py").read_text(encoding="utf-8")
    assert 'Path("/data/genebench_runner/provider")' not in src, \
        "provider 父目录又写死了绝对路径（N-855）"


def test_provider根换了根也跟着走(tmp_path):
    """两处必须**同时**跟着 `GENEBENCH_RUNNER_ROOT` 走 —— 一处跟一处不跟就是 N-855 本身。"""
    rr = tmp_path / "rr"
    env = _clean_env(GENEBENCH_RUNNER_ROOT=str(rr))
    code = ("import sys; sys.path.insert(0, '.');\n"
            "from ops import run_f02_a1 as A1\n"
            "from ops import run_joblist as RJ\n"
            "print(A1.RUNNER_PROVIDER_ROOT)\n"
            "print(RJ.runner_root('dual') + '/provider')\n")
    p = subprocess.run([sys.executable, "-c", code], cwd=str(REPO), env=env,
                       capture_output=True, text=True, timeout=600)
    assert p.returncode == 0, p.stdout + p.stderr
    a, b = p.stdout.split()
    assert a == b == str(rr / "provider"), p.stdout


def test_provider根不一致当场拒并打出两个值():
    from ops import run_f02_a1 as A1
    with pytest.raises(SystemExit) as e:
        A1.assert_provider_same_source("/somewhere/else/qlib_provider_x", dry=False)
    msg = str(e.value)
    assert "/somewhere/else/qlib_provider_x" in msg and str(A1.RUNNER_PROVIDER_ROOT) in msg, msg
    # `--dry` 那条路明确要求把 provider 指到数据面那一份 —— 判它会把自查变成死锁
    A1.assert_provider_same_source("/somewhere/else/qlib_provider_x", dry=True)


def test_双机不设变量时inner逐字节不变(monkeypatch):
    """N-855 的传根改动**不许动发布方那条命令**。"""
    from ops import run_joblist as RJ
    monkeypatch.delenv(PL.RUNNER_ROOT_ENV, raising=False)
    job = {"batch": "m6", "task_id": "s1-cor-01", "config_id": "cfg-codex-deepseek",
           "arm": "open", "seed": 1, "timeout_s": 1800}
    cmd = RJ.f02_run_cmd(job, "private", "dual")
    assert PL.RUNNER_ROOT_ENV not in cmd[-1], cmd[-1]
    monkeypatch.setenv(PL.RUNNER_ROOT_ENV, "/tmp/rr_f10")
    cmd2 = RJ.f02_run_cmd(job, "private", "dual")
    assert f"export {PL.RUNNER_ROOT_ENV}=/tmp/rr_f10; " in cmd2[-1], cmd2[-1]


# ===========================================================================
# N-851：push_exec 的落点可配 + 缺了大声说
# ===========================================================================
def test_push_exec落点不设变量时与发布方逐字节相同():
    p = subprocess.run(["bash", str(PUSH_EXEC_SH), "--print-paths"], cwd=str(REPO),
                       env=_clean_env(), capture_output=True, text=True, timeout=300)
    assert p.returncode == 0, p.stdout + p.stderr
    assert json.loads(p.stdout) == PUBLISHER_PATHS, p.stdout


def test_push_exec落点跟着GENEBENCH_ROOT走(tmp_path):
    p = subprocess.run(["bash", str(PUSH_EXEC_SH), "--print-paths"], cwd=str(REPO),
                       env=_clean_env(GENEBENCH_ROOT=str(tmp_path)),
                       capture_output=True, text=True, timeout=300)
    got = json.loads(p.stdout)
    assert got["PY"] == f"{tmp_path}/env/bin/python"
    assert got["STAGE"] == f"{tmp_path}/scratch/exec_push"
    # 单独设 GENEBENCH_PY 赢过它
    p2 = subprocess.run(["bash", str(PUSH_EXEC_SH), "--print-paths"], cwd=str(REPO),
                        env=_clean_env(GENEBENCH_ROOT=str(tmp_path), GENEBENCH_PY="/x/py"),
                        capture_output=True, text=True, timeout=300)
    assert json.loads(p2.stdout)["PY"] == "/x/py"


def test_GB_ROOT的兜底值与genebench_config同源():
    """兜底值漂了就红 —— 两个字面量必须是同一个（否则又是「两个真相」）。"""
    sh = PUSH_EXEC_SH.read_text(encoding="utf-8")
    assert f'GB_ROOT="${{GENEBENCH_ROOT:-{cfg._DEFAULT_ROOT}}}"' in sh, \
        f"shell 里的兜底根与 genebench_config._DEFAULT_ROOT（{cfg._DEFAULT_ROOT}）不一致"


def test_解释器不在时第0步就停而不是走到第3步才rc127():
    p = subprocess.run(["bash", str(PUSH_EXEC_SH), "--with-launch-data"], cwd=str(REPO),
                       env=_clean_env(GENEBENCH_PY="/nonexistent/python"),
                       capture_output=True, text=True, timeout=300)
    assert p.returncode == 2, f"rc={p.returncode}（127 = 又走到第 3 步才炸）\n{p.stdout}{p.stderr}"
    assert "GENEBENCH_PY" in p.stderr and "GENEBENCH_EXEC_STAGE" in p.stderr, p.stderr
    assert "1/6" not in p.stdout, "已经开始建 staging 了 —— 应该在第 0 步就停"


def test_双机的六步与守门顺序一条没动():
    """用户口径：「双机路径不动」= 单机改造不许改双机语义。本卡只动了默认值与 vendor 铺设。"""
    sh = PUSH_EXEC_SH.read_text(encoding="utf-8")
    for step in ("== 1/6 建 staging", "== 2/6 断言：staging 里不含答案面的名字",
                 "== 3/6 用执行面自己那道门扫 staging", "== 4/6 同步",
                 "== 5/6 对面落地即扫", "== 6/6 逐字节复核"):
        assert step in sh, f"第 {step!r} 步没了"
    # 按 `echo` 那一行找，不按裸字符串 —— 注释里也会提到「== 3/6」
    order = [sh.index(f'echo "== {i}/6') for i in range(1, 7)]
    assert order == sorted(order), "六步的顺序被动过了"
    assert "--force" not in sh and "--skip" not in sh, "加了绕过开关"


def test_落点根自己必须是0700():
    """**这一条是「全新执行面目录」那道冒烟当场量出来的**（2026-09-14，f02）。

    `mkdir -m 700 -p A/B` 的 `-m` 只作用在**最后一段**，中间的 `A` 吃 umask（f02 是 022）——
    于是一棵**全新**的 `$DEST` 根落成 0775，而注入器 P0 的红线 5 守门审计的就是这棵树：
    新铺的执行面**第一次真跑就红在自己的根上**（实测 P0 = `红线 5 目录对组/其它开放 0o775
    /data/genebench_runner/exec_f10`）。既有那棵 `exec/` 是 2026-09 手工 `mkdir` 的 0700，
    所以这条**在既有树上永远不显形** —— 用户裁定 ④ 那句话的实例：
    「f02 上能跑靠的是历次手工遗留物；从零铺一遍才知道什么从没被交付过。」
    """
    sh = PUSH_EXEC_SH.read_text(encoding="utf-8")
    assert 'chmod go-rwx $(printf %q "$DEST")' in sh, "push_exec 没有把 $DEST 根收紧"
    pl = (REPO / "runner" / "placement.py").read_text(encoding="utf-8")
    assert "p.chmod(p.stat().st_mode & ~0o077)" in pl, "单机落位没有把落点根收紧"


def test_单机落位真把落点根落成0700(tmp_path, monkeypatch):
    """不只看源码：真落一次，量 `exec_dest()` 与执行面根的 mode。"""
    root = tmp_path / "gb"
    root.mkdir(mode=0o700)
    monkeypatch.setenv("GENEBENCH_ROOT", str(root))
    monkeypatch.setenv("GENEBENCH_TOPOLOGY", "single")
    monkeypatch.setenv("GENEBENCH_RUNNER_PY", sys.executable)
    monkeypatch.delenv("GENEBENCH_RUNNER_ROOT", raising=False)
    old = os.umask(0o022)                  # **故意**用宽 umask —— 这正是病灶的现场
    try:
        p = subprocess.run([sys.executable, "-m", "runner.placement", "--topology", "single",
                            "--place-exec"], cwd=str(REPO),
                           env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
                           capture_output=True, text=True, timeout=900)
    finally:
        os.umask(old)
    assert p.returncode == 0, p.stdout[-3000:] + p.stderr[-3000:]
    dest = Path(json.loads(p.stdout[p.stdout.index("{"):])["dest"])
    for d in (dest, dest.parent):
        assert not (d.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO)), \
            f"{d} 是 {oct(d.stat().st_mode & 0o777)} —— 注入器 P0 会当场拒"
    assert (dest / "vendor" / "h11" / "__init__.py").is_file(), "单机落位没铺 h11（N-856）"
