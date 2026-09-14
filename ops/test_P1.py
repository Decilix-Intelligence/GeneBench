#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""卡 P1：把「默认值指着发布方那台机器」这一类扫干净，并补上**机器无关性**判据。

本卡修的是同一个病的两处形态，两处都由 2026-09-13 的 Mac 外部验收实测到：

1. **写死的绝对路径**（N-770 及同族）。`ops/score_runs.py` 的 `RUNS_IN` 写死
   `/data/shared/genebench/runs_in`，而 `ops/results_db.py::protocol_by_run()` 用的是
   `cfg.GENEBENCH_ROOT / "runs_in"` —— **在发布方那台机器上这两条是同一个路径，
   所以这处分叉在内网永远看不见**；外部单机用户跑完了结算不出分，要补两条软链才通。
2. **清单的内容取决于跑它的那台机器**（用户裁定 ②）。`mk_release_manifest.blockers()`
   的 `no_clone_url` 那一格写着「有 remote」/ 别的文本，而内网工作树没有远端、
   **任何 clone 都有 origin**；`public_channel_zero_runs` 那一格读的是 `$GB` 下的跑批清单，
   那份清单不进仓库。两格都在 `blockers` 里、`blockers` 在 `FATAL_KEYS` 里，
   于是 `--check` 在**每一个外部 clone 上**退 1，而 README §5 把退 1 定义成「判据变了，停下」。

判别力放在哪里（这三条缺一条，剩下的就都能恒绿）：

* `test_清单在有remote与没有remote的同一棵树上逐字节相同` —— 正面；
* `test_这条机器无关性比对自己有判别力` —— 反面：把「有没有 remote」重新写回清单，比对必须当场红；
* `test_不带主机段时rsync的源与改动前逐字相同` —— 发布方那台的行为**逐字不变**（改动的反向约束）。

这套测试**不依赖 `/data`、不依赖 market_lake、不依赖发布方的解释器与网关地址**，
在外部干净 clone 上跑得起来；要数据面才能判的两条自己 `skip` 并说清缺什么。
"""
from __future__ import annotations

import inspect
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import genebench_config as cfg                       # noqa: E402
from ops import mk_release_manifest as MR            # noqa: E402

#: 本卡扫过的六个模块：结算 / 出集 / 外部自检三条链路上的全部。
#: 判据与任务书给的一样 —— `grep -rn '"/data/shared' ops/*.py`。
SCANNED = (
    "ops/score_runs.py", "ops/run_controls.py", "ops/guard_modes.py",
    "ops/readiness_report.py", "ops/run_probe_mutations.py", "ops/validator_parity.py",
)

#: 基座构建上下文那五件（N-755 / N-778）。
BASE_BUILD_ITEMS = (
    "build/README.md", "build/base/Dockerfile", "build/base/requirements.txt",
    "build/base/constraints.txt", "build/base/README.md",
)

#: 造临时树时用的地址。**只写进 `.git/config`，不 fetch、不 push** ——
#: 判据刻意不查可达性（见 `clone_urls_declared` 的 docstring）。
FAKE_ORIGIN = "https://github.invalid/does-not-matter/GeneBench.git"


# ==================================================================== ① 写死的绝对路径

def test_三条链路的源码里没有发布方的绝对路径():
    """任务书给的判据原样跑一遍：这六个文件里不许再出现 `"/data/shared` 字面量。

    为什么盯**字面量**而不只是盯常量的值：常量改对了、下一行的 `--help` 里又手写一份
    的形态本轮就有一例（`run_probe_mutations` 的 `--answer-root`，而且手写那份
    **少一层 `public/`**、路径根本不存在）。字面量是封闭判据，常量值不是。
    """
    bad: list[str] = []
    for rel in SCANNED:
        for i, ln in enumerate((REPO / rel).read_text(encoding="utf-8").splitlines(), 1):
            if '"/data/shared' in ln or "'/data/shared" in ln:
                bad.append(f"{rel}:{i}: {ln.strip()}")
    assert not bad, "还有写死的发布方路径：\n" + "\n".join(bad)


def _import_constants(root: Path) -> dict[str, str]:
    """在一个 `GENEBENCH_ROOT=<root>` 的子进程里读出六个模块的落点常量。

    必须起子进程：`cfg.GENEBENCH_ROOT` 在 import 时刻定值，本进程里改环境变量没用。
    """
    code = (
        "import json, sys\n"
        f"sys.path.insert(0, {str(REPO)!r})\n"
        "out = {}\n"
        "from ops import score_runs as A\n"
        "out['score_runs.RUNS_IN'] = str(A.RUNS_IN)\n"
        "out['score_runs.REF_TASKS'] = str(A.REF_TASKS)\n"
        "from ops import run_controls as B\n"
        "out['run_controls.ANSWER_ROOT'] = str(B.ANSWER_ROOT)\n"
        "out['run_controls.GATEWAY_LOG'] = str(B.GATEWAY_LOG)\n"
        "out['run_controls.PUBLIC_ANSWER_ROOT'] = str(B.PUBLIC_ANSWER_ROOT)\n"
        "out['run_controls.PUBLIC_GATEWAY_LOG'] = str(B.PUBLIC_GATEWAY_LOG)\n"
        "from ops import guard_modes as C\n"
        "out['guard_modes.EXTERNAL_ROOTS'] = C.EXTERNAL_ROOTS[0]\n"
        "out['guard_modes.ANSWER_PLANE_ROOTS'] = C.ANSWER_PLANE_ROOTS[0]\n"
        "from ops import readiness_report as D\n"
        "out['readiness_report.RUNS_IN'] = str(D.RUNS_IN)\n"
        "from ops import run_probe_mutations as E\n"
        "out['run_probe_mutations.ANSWER_ROOT'] = str(E.ANSWER_ROOT)\n"
        "out['run_probe_mutations.PUBLIC_ANSWER_ROOT'] = str(E.PUBLIC_ANSWER_ROOT)\n"
        "from ops import validator_parity as F\n"
        "out['validator_parity.ANSWER_ROOT'] = str(F.ANSWER_ROOT)\n"
        "out['validator_parity.RUNS_IN'] = str(F.RUNS_IN)\n"
        "print(json.dumps(out))\n"
    )
    env = dict(os.environ, GENEBENCH_ROOT=str(root), PYTHONDONTWRITEBYTECODE="1")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       timeout=600, env=env, cwd=str(REPO))
    if r.returncode != 0:
        tail = (r.stderr or "")[-600:]
        if "ModuleNotFoundError" in tail:
            pytest.skip(f"本机装不全这六个模块的依赖：{tail.strip().splitlines()[-1]}")
        pytest.fail(f"读常量的子进程失败：{tail}")
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_六个模块的落点跟着GENEBENCH_ROOT走(tmp_path):
    """换一个 `$GENEBENCH_ROOT`，这些常量必须**整体跟着搬**。

    写死的那一版在这条下面会当场红：它的值不会动。
    """
    root = tmp_path / "gb_elsewhere"
    got = _import_constants(root)
    # `guard_modes.EXTERNAL_ROOTS[0]` 就是根本身，其余是根下面的东西。
    stuck = {k: v for k, v in got.items()
             if v != str(root) and not v.startswith(str(root) + os.sep)}
    assert not stuck, f"换了 GENEBENCH_ROOT 之后没跟着搬的常量：{stuck}"


def test_发布方那台的取值一字未动():
    """**改动的反向约束**：`GENEBENCH_ROOT` 取默认值时，六个模块的常量与改动前逐字相同。"""
    got = _import_constants(Path("/data/shared/genebench"))
    assert got == {
        "score_runs.RUNS_IN": "/data/shared/genebench/runs_in",
        "score_runs.REF_TASKS": "/data/shared/genebench/reference/tasks/v1.0-smoke",
        "run_controls.ANSWER_ROOT": "/data/shared/genebench/reference/tasks/v1.0-smoke",
        "run_controls.GATEWAY_LOG": "/data/shared/genebench/logs/gateway_access.jsonl",
        "run_controls.PUBLIC_ANSWER_ROOT":
            "/data/shared/genebench/reference/tasks/public/v1.0-smoke-public",
        "run_controls.PUBLIC_GATEWAY_LOG":
            "/data/shared/genebench/logs/gateway_access_public.jsonl",
        "guard_modes.EXTERNAL_ROOTS": "/data/shared/genebench",
        "guard_modes.ANSWER_PLANE_ROOTS": "/data/shared/genebench/reference",
        "readiness_report.RUNS_IN": "/data/shared/genebench/runs_in",
        "run_probe_mutations.ANSWER_ROOT": "/data/shared/genebench/reference/tasks/v1.0-smoke",
        "run_probe_mutations.PUBLIC_ANSWER_ROOT":
            "/data/shared/genebench/reference/tasks/public/v1.0-smoke-public",
        "validator_parity.ANSWER_ROOT": "/data/shared/genebench/reference/tasks/v1.0-smoke",
        "validator_parity.RUNS_IN": "/data/shared/genebench/runs_in",
    }


def test_公开题集根三处同值():
    """`run_controls` / `run_joblist` / `run_probe_mutations` 三处的题集根必须逐字相同。

    第二次分叉的代价红队 2026-09-07 实测过（N-304）：手写那份少一层 `public/`，
    照着 `--help` 抄命令直接失败，而报告头里写的是对的。
    """
    from ops import run_controls as RC                # noqa: PLC0415
    from ops import run_joblist as RJ                 # noqa: PLC0415
    from ops import run_probe_mutations as RM         # noqa: PLC0415
    assert RC.PUBLIC_ANSWER_ROOT == RJ.PUBLIC_ANSWER_ROOT == RM.PUBLIC_ANSWER_ROOT
    assert RC.ANSWER_ROOT == RJ.PRIVATE_ANSWER_ROOT == RM.ANSWER_ROOT
    assert RC.GATEWAY_LOG == RJ.PRIVATE_GATEWAY_LOG
    assert RC.PUBLIC_GATEWAY_LOG == RJ.PUBLIC_GATEWAY_LOG


def test_结算与入库的run根同源():
    """结算（`score_runs`）与入库（`results_db`）必须从**同一个**根找 run 目录。

    分叉的表现卡 D2 实测过：只接结算那一头，入库就报「协议轴反算不出」——
    要**两条软链一起补**才通。修好之后外部用户不该需要任何软链。
    """
    from ops import results_db as DB                  # noqa: PLC0415
    from ops import score_runs as SRN                 # noqa: PLC0415
    assert SRN.RUNS_IN == cfg.GENEBENCH_ROOT / "runs_in"
    src = inspect.getsource(DB.protocol_by_run)
    assert 'cfg.GENEBENCH_ROOT / "runs_in"' in src, (
        "results_db.protocol_by_run 的默认根变了 —— 它与 score_runs.RUNS_IN 必须同源")


# ==================================================================== ② score_runs 的入口

def test_score_runs给了显式的run根与远端主机入口():
    r = subprocess.run([sys.executable, str(REPO / "ops" / "score_runs.py"), "--help"],
                       capture_output=True, text=True, timeout=300, cwd=str(REPO))
    assert r.returncode == 0, r.stderr[-600:]
    assert "--runs-root" in r.stdout, "没有显式的 run 根入口（N-770）"
    assert "--remote-host" in r.stdout, "`--remote` 仍然只能指向发布方那台"


@pytest.mark.parametrize("s,exp", [
    ("/data/genebench_runner/a1/runs/runs", (None, "/data/genebench_runner/a1/runs/runs")),
    ("ljn@192.168.1.219:/data/x", ("ljn@192.168.1.219", "/data/x")),
    ("box:/d/r", ("box", "/d/r")),
    # 冒号在斜杠**之后** = 本机路径里带冒号，不是主机段
    ("/data/a:b", (None, "/data/a:b")),
    ("", (None, "")),
])
def test_远端写法的解析(s, exp):
    from ops import score_runs as SRN                 # noqa: PLC0415
    assert SRN.split_remote(s) == exp


def test_不带主机段时rsync的源与改动前逐字相同(tmp_path, monkeypatch):
    """**发布方那台的行为逐字不变**：`run_joblist` 传的是一个不带主机段的裸路径。

    同时钉住两条新路：`--remote` 自带主机段时以它为准；`--remote-host local` 不走 ssh。
    """
    from ops import score_runs as SRN                 # noqa: PLC0415
    seen: dict[str, list[str]] = {}

    class _R:
        returncode = 0
        stderr = ""

    def fake_run(cmd, **kw):
        seen["cmd"] = list(cmd)
        return _R()

    monkeypatch.setattr(SRN.subprocess, "run", fake_run)
    SRN.pull("a1", "/data/genebench_runner/a1/runs/runs", runs_root=tmp_path)
    assert seen["cmd"][-2] == "ljn@192.168.1.219:/data/genebench_runner/a1/runs/runs/"
    SRN.pull("a1", "box:/home/u/runs", runs_root=tmp_path)
    assert seen["cmd"][-2] == "box:/home/u/runs/"
    SRN.pull("a1", "/home/u/runs", host=SRN.LOCAL_HOST, runs_root=tmp_path)
    assert seen["cmd"][-2] == "/home/u/runs/", "同机结算不该再走 ssh"


def test_run根不在时当场说清楚而不是静默出一张空表(tmp_path):
    """外部单机上最贵的那个形态：结算**退 0** 并打印「runs: 0；问题: 0」——
    一张什么都没有的表，看起来像「跑完了、没问题」。"""
    calib = cfg.calibration_path()
    if not calib.is_file():
        pytest.skip(f"本机没有标定 {calib}（结算入口在读 run 目录之前先要它）")
    r = subprocess.run(
        [sys.executable, str(REPO / "ops" / "score_runs.py"), "--batch", "p1_no_such_batch",
         "--no-pull", "--runs-root", str(tmp_path)],
        capture_output=True, text=True, timeout=600, cwd=str(REPO))
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode != 0, out[-800:]
    assert "没有 run 目录" in out, out[-800:]
    assert str(tmp_path / "p1_no_such_batch") in out, out[-800:]


# ==================================================================== ③ 清单的机器无关性

def _tree(dst: Path, *, remote: str | None) -> Path:
    """造一棵**内容与本仓库相同**的临时 git 树：顶层逐项 symlink + 自己的 `.git`。

    为什么 symlink 而不是 copy：这棵树只被 `mk_release_manifest.build()` **读**，
    而 copy 一份仓库是几百 MB 的事，一条测试不该那么贵。`build()` 读的是
    `repo / <相对路径>`，symlink 被 `is_file()` / `read_bytes()` 透明解析，
    所以两棵树读到的字节与本仓库逐字节相同 —— 两次生成之间**只差一个 origin**。
    """
    dst.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(dst)], check=True, capture_output=True, timeout=300)
    for p in REPO.iterdir():
        if p.name == ".git":
            continue
        (dst / p.name).symlink_to(p)
    if remote:
        subprocess.run(["git", "-C", str(dst), "remote", "add", "origin", remote],
                       check=True, capture_output=True, timeout=300)
    return dst


def _canonical(m: dict) -> bytes:
    """清单的**逐字节比对形态**：只把 `generated_at`（本次生成的时刻）归一化掉。

    其余一个字段都不许放过 —— 放过哪一格，哪一格就可以偷偷与机器有关。
    """
    m = dict(m)
    m["generated_at"] = "<归一化>"
    return json.dumps(m, ensure_ascii=False, sort_keys=True, indent=1).encode("utf-8")


def _two_trees(tmp_path: Path) -> tuple[Path, Path]:
    if not shutil.which("git"):
        pytest.skip("本机没有 git")
    a = _tree(tmp_path / "with_origin", remote=FAKE_ORIGIN)
    b = _tree(tmp_path / "no_origin", remote=None)
    assert "[remote " in (a / ".git" / "config").read_text(encoding="utf-8")
    assert "[remote " not in (b / ".git" / "config").read_text(encoding="utf-8")
    return a, b


def test_清单在有remote与没有remote的同一棵树上逐字节相同(tmp_path):
    """用户裁定 ②：同一棵树，只差一个 `origin`，生成出来的清单必须**逐字节相同**。

    这正是 2026-09-13 Mac 外部验收撞到的那条：内网工作树没有远端、任何 clone 都有，
    于是 `--check` 在每一个外部 clone 上都退 1，而 README §5 把退 1 定义成「判据变了，停下」。
    """
    a, b = _two_trees(tmp_path)
    ma, mb = _canonical(MR.build(a)), _canonical(MR.build(b))
    assert ma == mb, "同一棵树、只差一个 origin，生成出了两份不同的清单"


def test_这条机器无关性比对自己有判别力(tmp_path, monkeypatch):
    """**反面**：把「有没有 remote」重新写回清单，上面那条比对必须当场红。

    没有这一条，一个把两边都返回同一个常量的实现也会全绿。
    """
    a, b = _two_trees(tmp_path)
    real = MR.blockers

    def leaky(repo, missing, dl, spdx):
        rows = [dict(x) for x in real(repo, missing, dl, spdx)]
        cfg_txt = (repo / ".git" / "config").read_text(encoding="utf-8", errors="replace")
        rows[0]["status_now"] = "有 remote" if "[remote " in cfg_txt else "没有 remote"
        return rows

    monkeypatch.setattr(MR, "blockers", leaky)
    assert _canonical(MR.build(a)) != _canonical(MR.build(b)), (
        "把机器差异写回清单之后比对仍然相同 —— 那条正面测试是恒绿的")


def test_外部clone上判据字段不漂(tmp_path):
    """`--check` 判红的就是 `FATAL_KEYS` 这几格。一棵**有 origin** 的干净树上必须全绿。

    `files` 不在这一条里（生成件每跑一次换一份 sha，由 `--check` 的退出码 3 报）——
    与 `ops/test_release_manifest.py` 同一条纪律。
    """
    a, _ = _two_trees(tmp_path)
    old = json.loads((REPO / "RELEASE_MANIFEST.json").read_text(encoding="utf-8"))
    fatal, _drift = MR.classify_drift(MR.build(a), old)
    assert fatal == [], f"有 origin 的树上判据字段漂了：{fatal}"


def test_公开通道那条背书也不看机器(tmp_path):
    """同一个病的第二处：这条 blocker 从前读 `$GB` 下的跑批清单，而那份清单不进仓库。

    现在读仓库里的结算产物，所以 `$GENEBENCH_ROOT` 指到哪儿都不影响答案。
    """
    assert MR.public_channel_runs(REPO) == MR.public_channel_runs(), "默认参数不是本仓库"
    # **行为上的证明**（比读源码可靠）：发布方那台上 `$GB/runs_in/m6_public/jobs.jsonl`
    # 就在那儿，如果还在读它，下面这一行会读出一个数而不是 None。
    # 反向：树上没有那份产物 ⇒ 不适用（不是「满足」）；空表 ⇒ 不满足。
    assert MR.public_channel_runs(tmp_path) is None
    d = tmp_path / "ops" / "reports" / "m6_public"
    d.mkdir(parents=True)
    (d / "records.json").write_text("[]", encoding="utf-8")
    assert MR.public_channel_runs(tmp_path) == (0, 0)
    bl = next(x for x in MR.blockers(tmp_path, [], "granted", "Apache-2.0")
              if x["id"] == "public_channel_zero_runs")
    assert bl["satisfied"] is False, "一个 run 都没有却说背书到位"


# ==================================================================== ④ 基座那五件

def test_基座构建上下文五件在发布件清单里():
    """N-755 / N-778：清单不收这五件 = 清单说交付完整，而基座仍然缺件。"""
    declared = {rel for items in MR.RELEASE_ITEMS.values() for rel in items}
    missing_decl = sorted(set(BASE_BUILD_ITEMS) - declared)
    assert not missing_decl, f"RELEASE_ITEMS 里没有：{missing_decl}"
    for rel in BASE_BUILD_ITEMS:
        assert (REPO / rel).is_file(), f"声明了却不在工作树上：{rel}"


def test_基座那五件真的进了生成出来的清单():
    m = MR.build()
    assert set(BASE_BUILD_ITEMS) <= set(m["files"]), sorted(
        set(BASE_BUILD_ITEMS) - set(m["files"]))
    assert not (set(BASE_BUILD_ITEMS) & set(m["missing"])), m["missing"]
    for rel in BASE_BUILD_ITEMS:
        assert m["files"][rel]["sha256"], rel


def test_仓库根的build不再被gitignore挡住():
    """`.gitignore` 第 6 行那条不锚定的 `build/` 会连仓库自己的构建上下文一起挡掉。

    代价不是「少了一个目录」，是**在 build/ 下新建文件 `git status` 不提醒** ——
    漏 add 的表现正好是「我这台构得出来、别人 clone 下来构不出来」。
    """
    if not shutil.which("git"):
        pytest.skip("本机没有 git")
    for rel in ("build/base/Dockerfile", "build/base/a_new_file_nobody_added_yet.txt"):
        r = subprocess.run(["git", "-C", str(REPO), "check-ignore", "-v", rel],
                           capture_output=True, text=True, timeout=300)
        assert r.returncode == 1, f"{rel} 仍然被 ignore：{r.stdout.strip()}"
