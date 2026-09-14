# -*- coding: utf-8 -*-
"""卡 A9：**单机形态实现成一条不含跨机步骤的路径**（用户裁定 ①②，2026-09-14）。

这份测试守的是三件事，它们各自对应本轮那四条 block 的**根因**，而不是症状：

1. **形态是显式判据，不是嗅探。** `--topology` > `GENEBENCH_TOPOLOGY` > `dual`。
   病因是：以前没有「形态」这个概念，跨机与否靠代码里写死的发布方路径与 `ssh` 目标
   **隐式**决定；而 Linux 可以 `mkdir /data` 把那些路径造出来（卡 D2 那次就是这么绕的），
   **macOS 根卷只读、`sudo mkdir /data` 直接失败** —— 于是这条缺陷在 Linux 上永远不显形。
2. **单机分支一次 ssh 都不发；双机分支仍走原路、仍核 timer。** 裁定 ①：单机路径
   **不调** `ops/push_exec_to_f02.sh` 与 `ops/push_bundle_to_f02.sh` —— 单机没有「推」这件事；
   那两个脚本本卡**一个字节都没动**，也没有加任何 `--force` 之类的绕过开关。
3. **根全部从 `cfg.GENEBENCH_ROOT` 现算，而发布方那台的取值逐字不变。** 裁定 ②。
   最要紧的一条不是「把常量改成函数」，是**换根之后互斥还成不成立**（红线 B6）——
   `test_gateway_lock_still_serialises_within_one_root` 真起两个进程量它。

**判据的静态一半**在 `test_single_machine_path_has_no_data_literal`：沿单机路径的入口集合
+ 它们 import 的本仓模块，`/data` 字面量必须 0 命中，豁免是**逐字闭集**（每一行原文照抄、
每个文件写明理由）。动态那一半（`GENEBENCH_ROOT` 指临时目录 + 不许访问 `/data` 跑通
clone → 三件附件 → 起网关 → 出集 → 一个 job → 出表）是裁定 ③ 那道门，不在本卡。
"""
from __future__ import annotations

import ast
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import genebench_config as cfg                              # noqa: E402
from runner import placement as PL                          # noqa: E402
from runner import placement_dual as PD                     # noqa: E402

PUSH_BUNDLE_SH = REPO / "ops" / "push_bundle_to_f02.sh"
PUSH_EXEC_SH = REPO / "ops" / "push_exec_to_f02.sh"

#: 发布方那台执行面的根。**本测试里出现它是故意的**：这条断言的全部内容就是
#: 「不设任何环境变量时，双机取值与本卡改动之前逐字相同」。
PUBLISHER_RUNNER_ROOT = "/data/genebench_runner"
PUBLISHER_GENEBENCH_ROOT = "/data/shared/genebench"


@pytest.fixture()
def clean_env(monkeypatch):
    """把本卡认的三个环境变量清干净 —— 断言「发布方默认值」时必须是这个状态。"""
    for k in (PL.TOPOLOGY_ENV, PL.RUNNER_ROOT_ENV, PL.RUNNER_PY_ENV):
        monkeypatch.delenv(k, raising=False)
    return monkeypatch


# ===========================================================================
# ① 形态：显式判据
# ===========================================================================
def test_topology_defaults_to_dual(clean_env):
    """不给就是 `dual` —— 发布方那台不设任何东西，行为一个字不变。"""
    assert PL.resolve_topology() == PL.DUAL
    assert PL.resolve_topology(None) == PL.DUAL


def test_topology_is_explicit_never_sniffed(clean_env):
    """**判据里不许有嗅探**：没有 hostname、没有「`/data` 在不在」、没有 uname。

    这一条不是洁癖：本轮四条 block 的共同根因就是「判据依赖这台机器能不能造出那些路径」。
    """
    src = (REPO / "runner" / "placement.py").read_text(encoding="utf-8")
    fn = src.split("def resolve_topology", 1)[1].split("\ndef ", 1)[0]
    for bad in ("gethostname", "uname", "platform", "Path(\"/data", "exists()", "is_dir()"):
        assert bad not in fn, f"resolve_topology 里出现了嗅探：{bad}"


def test_topology_env_and_flag_must_agree(clean_env):
    clean_env.setenv(PL.TOPOLOGY_ENV, "single")
    assert PL.resolve_topology("single") == PL.SINGLE
    assert PL.resolve_topology() == PL.SINGLE
    with pytest.raises(SystemExit) as e:
        PL.resolve_topology("dual")
    assert "不一致" in str(e.value)


def test_unknown_topology_is_refused(clean_env):
    with pytest.raises(SystemExit):
        PL.resolve_topology("f02ish")


# ===========================================================================
# ② 根：单机现算 / 双机逐字不变
# ===========================================================================
def test_publisher_values_are_byte_identical(clean_env):
    """**发布方那台的取值必须逐字节不变。** 这是本卡最硬的一条回归锁。"""
    assert str(PL.runner_root()) == PUBLISHER_RUNNER_ROOT
    assert PD.RUNNER_ROOT_DEFAULT == PUBLISHER_RUNNER_ROOT
    assert str(PL.exec_dest()) == PUBLISHER_RUNNER_ROOT + "/exec"
    assert PL.runner_py() == "python3"


def test_gateway_lock_path_on_the_publisher_is_unchanged(clean_env, monkeypatch):
    """`ops/gateway_lock.py:34` 原来写死的就是这个字符串（N-838）。"""
    from ops import gateway_lock as GL
    monkeypatch.delenv(GL.LOCK_ENV, raising=False)
    if os.environ.get("GENEBENCH_ROOT"):
        pytest.skip("本进程带着 GENEBENCH_ROOT 覆盖，测不了发布方默认值")
    assert str(GL.lock_path()) == PUBLISHER_GENEBENCH_ROOT + "/locks/gateway.lock"


def test_single_roots_are_computed_from_genebench_root(clean_env):
    """裁定 ②：单机路径上的根**全部从 `cfg.GENEBENCH_ROOT` 现算**。"""
    clean_env.setenv(PL.TOPOLOGY_ENV, "single")
    assert PL.runner_root() == cfg.GENEBENCH_ROOT / "genebench_runner"
    assert PL.exec_dest() == cfg.GENEBENCH_ROOT / "genebench_runner" / "exec"
    assert PL.guard_log() == cfg.GENEBENCH_ROOT / "genebench_runner" / "logs" / "answer_plane.jsonl"
    assert PL.local_apg_log().is_relative_to(cfg.GENEBENCH_ROOT)


def test_explicit_runner_root_wins_over_both_topologies(clean_env, tmp_path):
    clean_env.setenv(PL.RUNNER_ROOT_ENV, str(tmp_path / "rr"))
    assert PL.runner_root("single") == tmp_path / "rr"
    assert PL.runner_root("dual") == tmp_path / "rr"


# ===========================================================================
# ③ 单机分支：一次 ssh 都不发；双机分支：仍走原路、仍核 timer
# ===========================================================================
def _job(batch="v1demo", task="s1-cor-01"):
    return {"batch": batch, "task_id": task, "config_id": "cfg-codex-deepseek", "arm": "strict",
            "seed": 1, "timeout_s": 1500, "digest": "sha256:deadbeef", "budget_override": {}}


def test_dual_run_command_still_goes_through_ssh(clean_env):
    import ops.run_joblist as RJ
    c = RJ.f02_run_cmd(_job(), "public", "dual")
    assert c[0] == "ssh" and c[1:3] == ["-o", "ConnectTimeout=120"]
    assert c[-1].startswith("umask 022; export PYTHONDONTWRITEBYTECODE=1;")       # 红线 B7
    assert PUBLISHER_RUNNER_ROOT + "/v1demo/runner/tasks/s1-cor-01" in c[-1]


def test_dual_push_still_goes_through_the_only_allowed_entry_point(clean_env):
    """红线 B2：双机推送仍然只走 `ops/push_bundle_to_f02.sh`，落点仍在发布方执行面根下。"""
    import ops.run_joblist as RJ
    c = RJ.push_cmd(_job(), Path("/tmp/st"), "dual")
    assert c[0].endswith("ops/push_bundle_to_f02.sh")
    assert c[2] == PUBLISHER_RUNNER_ROOT + "/v1demo/runner/tasks"


def test_dual_push_script_still_checks_the_remote_timer_and_has_no_bypass():
    """**N-842 那道 timer 核查是双机形态的真判据** —— 不许放宽、不许加绕过开关（裁定 ①）。"""
    sh = PUSH_BUNDLE_SH.read_text(encoding="utf-8")
    assert "genebench-answer-plane-scan.timer" in sh
    assert "systemctl --user is-enabled $TIMER" in sh and "systemctl --user is-active $TIMER" in sh
    assert "/data/genebench_runner/*) : ;;" in sh          # ② 落点判据一字未动
    for bypass in ("--force", "--skip-timer", "--no-timer", "SKIP_TIMER", "GENEBENCH_FORCE"):
        assert bypass not in sh, f"push_bundle_to_f02.sh 里出现了绕过开关 {bypass}"


def test_single_run_command_sends_no_ssh(clean_env):
    """裁定 ①：单机形态整条路径不含 `ssh`。这一条量的是真跑那一段。"""
    import ops.run_joblist as RJ
    c = RJ.f02_run_cmd(_job(), "public", "single")
    assert c[0] == "bash" and c[1] == "-c"
    assert "ssh" not in c and "ssh " not in c[-1]
    assert c[-1].startswith("umask 077; export PYTHONDONTWRITEBYTECODE=1; "
                            f"export {PL.RUNNER_ROOT_ENV}=")
    assert str(cfg.GENEBENCH_ROOT / "genebench_runner") in c[-1]


def test_single_score_command_settles_on_this_machine(clean_env):
    """同机结算必须 `--remote-host local`（`ops/score_runs.py::LOCAL_HOST`）——
    不给它，`pull()` 会去连**发布方的执行面**，而报错停在 ssh 那一层（卡 D2 实测）。"""
    import ops.run_joblist as RJ
    c = RJ.score_cmd("v1demo", "public", "single")
    assert c[c.index("--remote-host") + 1] == "local"
    assert c[c.index("--remote") + 1].startswith(str(cfg.GENEBENCH_ROOT / "genebench_runner"))
    d = RJ.score_cmd("v1demo", "public", "dual")
    assert "--remote-host" not in d                       # 双机那条一字未动
    assert d[d.index("--remote") + 1].startswith(PUBLISHER_RUNNER_ROOT)


def test_single_plane_probes_do_not_ssh(clean_env, monkeypatch):
    """公开通道真跑前那两件前置探针，单机形态下在本机跑 —— 不发 ssh。"""
    import ops.run_joblist as RJ
    seen = []

    def fake_sh(cmd, **kw):
        seen.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 1, "", "")

    monkeypatch.setattr(RJ, "_sh", fake_sh)
    RJ.probe_f02_gateway("public", "single")
    monkeypatch.setattr(RJ, "provider_dir", lambda ch: cfg.GENEBENCH_ROOT / "snapshots")
    monkeypatch.setattr("genetask.pin.provider_root_sha256", lambda p: "0" * 64)
    RJ.probe_f02_provider("public", "single")
    assert seen, "探针一条命令都没发？"
    for cmd in seen:
        assert cmd[0] != "ssh", f"单机形态的探针发了 ssh：{cmd}"


def test_place_functions_refuse_on_dual(clean_env, tmp_path):
    """本地落位只在单机形态下可用；双机形态请走那两个脚本（红线 B2 的唯一入口）。"""
    for fn, args in ((PL.place_exec_tree, ()),
                     (PL.place_bundle, (tmp_path, tmp_path / "d", tmp_path / "m.json"))):
        with pytest.raises(PL.PlacementError) as e:
            fn(*args, "dual") if args else fn("dual")
        assert "单机形态" in str(e.value)


def test_place_bundle_runs_the_same_gates_in_the_same_order_and_never_ssh(clean_env, tmp_path,
                                                                         monkeypatch):
    """**答案面纪律一条没松**：落位走的是同一批门、同一份实现，只是不 ssh。

    顺序与 `ops/push_bundle_to_f02.sh` 逐条对应：push_guard → 容器边界（主口径，
    两条 `--mount` 都声明）→ 本地拷贝 → 落地树扫（**显式** `--root` / `--log`）。
    """
    clean_env.setenv(PL.TOPOLOGY_ENV, "single")
    clean_env.setenv(PL.RUNNER_ROOT_ENV, str(tmp_path / "rr"))
    src = tmp_path / "tasks" / "s1-cor-01"
    (src / "work").mkdir(parents=True)
    man = tmp_path / "s1-cor-01.manifest.json"
    man.write_text("{}", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_run(cmd, **kw):
        calls.append([str(x) for x in cmd])
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(PL, "_run", fake_run)
    monkeypatch.setattr(PL, "_scan_tree", PL._scan_tree)          # 走真实现（内部调 fake_run）
    got = PL.place_bundle(src, tmp_path / "rr" / "v1demo" / "runner" / "tasks", man)
    assert got["topology"] == "single"

    flat = [" ".join(c) for c in calls]
    assert any(c[0] != "ssh" for c in calls)
    for c in calls:
        assert c[0] not in ("ssh", "scp"), f"单机落位发了 {c[0]}：{c}"
    assert any("ops/push_guard.py" in s for s in flat), "没调 push_guard"
    cont = [c for c in calls if "--mode" in c and c[c.index("--mode") + 1] == "container"]
    assert len(cont) == 1, "容器边界口径（主口径）没跑，或跑了不止一次"
    assert f"{src}/work:/task" in cont[0] and f"{src}:/task" in cont[0]
    assert "--log" in cont[0]
    tree = [c for c in calls if "answer_plane_guard.py" in " ".join(c) and c not in cont]
    assert tree, "落地之后没有树口径扫描"
    for c in tree:
        assert "--root" in c and "--log" in c, \
            f"树扫描没有显式传 --root/--log（会吃 answer_plane_guard 的发布方默认值）：{c}"
    assert flat.index([s for s in flat if "push_guard" in s][0]) < flat.index(" ".join(cont[0]))


def test_place_bundle_refuses_a_destination_outside_the_runner_root(clean_env, tmp_path,
                                                                    monkeypatch):
    """`ops/push_bundle_to_f02.sh` ② 那道「落点必须在执行面根下」的判据，单机这边还在 ——
    只是根**现算**，不是写死的 `/data/genebench_runner/`。"""
    clean_env.setenv(PL.TOPOLOGY_ENV, "single")
    clean_env.setenv(PL.RUNNER_ROOT_ENV, str(tmp_path / "rr"))
    (tmp_path / "rr").mkdir()
    src = tmp_path / "b"
    src.mkdir()
    man = tmp_path / "m.json"
    man.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(PL, "_run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, "", ""))
    with pytest.raises(PL.PlacementError) as e:
        PL.place_bundle(src, tmp_path / "elsewhere", man)
    assert "执行面根" in str(e.value)


def test_exec_whitelist_matches_the_shell_script_verbatim():
    """**两份清单 = 两个真相。** `runner/placement.py` 的白名单必须与
    `ops/push_exec_to_f02.sh` 的同名 shell 数组逐项相同 —— 漂移的表现是
    「执行面上 import 不了整棵 runner，数据面一切正常」（那个脚本自己记着 2026-09-04 那次）。
    """
    sh = PUSH_EXEC_SH.read_text(encoding="utf-8")

    def arr(name: str) -> tuple[str, ...]:
        m = re.search(rf"^{name}=\((.*?)\)\s*$", sh, re.M | re.S)
        assert m, f"push_exec_to_f02.sh 里找不到数组 {name}"
        return tuple(m.group(1).split())

    assert arr("GENETASK_FILES") == PL.GENETASK_FILES
    assert arr("GENETASK_DIRS") == PL.GENETASK_DIRS
    assert arr("OPS_FILES") == PL.OPS_FILES
    assert arr("OPS_DIRS") == PL.OPS_DIRS
    assert arr("SYNC_DIRS") == PL.SYNC_DIRS
    assert arr("FORBIDDEN_SEGMENTS") == PL.FORBIDDEN_SEGMENTS
    assert arr("FORBIDDEN_NAMES") == PL.FORBIDDEN_NAMES
    assert "OPS_EMPTY_INIT=1" in sh and PL.OPS_EMPTY_INIT is True
    assert "RUNNER_WHOLE=1" in sh and PL.RUNNER_WHOLE is True
    # `--with-launch-data` 带的那两棵树
    assert "for d in harnesses integrations; do" in sh
    assert PL.LAUNCH_DIRS == ("harnesses", "integrations")


# ===========================================================================
# ④ 红线 B6：换了锁根之后，互斥还成不成立（**这一条比改常量本身重要**）
# ===========================================================================
def _lock_cmd(hold_s: float) -> list[str]:
    return [sys.executable, str(REPO / "ops" / "gateway_lock.py"), "--what", "A9-holder",
            "--", sys.executable, "-c", f"import time; time.sleep({hold_s})"]


def _wait_for_holder(lock: Path, timeout_s: float = 20.0) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        try:
            if "A9-holder" in lock.read_text(encoding="utf-8"):
                return True
        except OSError:
            pass
        time.sleep(0.2)
    return False


def test_gateway_lock_still_serialises_within_one_root(tmp_path, monkeypatch):
    """**同一台机器、同一个 `GENEBENCH_ROOT` 下的两个进程仍然互斥**（红线 B6）。

    真起两个进程量，不是读代码推断：一个拿着锁，另一个 `--nowait` 必须拿不到。
    """
    root = tmp_path / "gbA"
    root.mkdir()
    env = dict(os.environ, GENEBENCH_ROOT=str(root))
    env.pop("GENEBENCH_GATEWAY_LOCK", None)
    lock = root / "locks" / "gateway.lock"
    holder = subprocess.Popen(_lock_cmd(12), env=env, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
    try:
        assert _wait_for_holder(lock), f"持锁进程没在 20 s 内写进 {lock}"
        p = subprocess.run([sys.executable, str(REPO / "ops" / "gateway_lock.py"),
                            "--nowait", "--what", "A9-contender", "--", sys.executable, "-c", "pass"],
                           env=env, capture_output=True, text=True, timeout=60)
        assert p.returncode != 0, "同一个 GENEBENCH_ROOT 下第二个进程竟然拿到了网关锁 —— 互斥没了"
        assert "网关被占着" in (p.stdout + p.stderr)
    finally:
        holder.terminate()
        holder.wait(timeout=30)


def test_gateway_lock_of_two_roots_are_independent_deployments(tmp_path):
    """**不同 `GENEBENCH_ROOT` 之间本来就该互不干扰** —— 那是两套独立部署。

    这不是「互斥丢了」，是「两套部署各锁各的」。同机两套根却共用同一个网关实例时，
    用 `GENEBENCH_GATEWAY_LOCK` 把两边指到同一个文件（`lock_path()` 的 docstring）。
    """
    a, b = tmp_path / "gbA", tmp_path / "gbB"
    a.mkdir(); b.mkdir()
    env_a = dict(os.environ, GENEBENCH_ROOT=str(a))
    env_b = dict(os.environ, GENEBENCH_ROOT=str(b))
    for e in (env_a, env_b):
        e.pop("GENEBENCH_GATEWAY_LOCK", None)
    holder = subprocess.Popen(_lock_cmd(12), env=env_a, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
    try:
        assert _wait_for_holder(a / "locks" / "gateway.lock")
        p = subprocess.run([sys.executable, str(REPO / "ops" / "gateway_lock.py"),
                            "--nowait", "--what", "A9-other-root", "--", sys.executable, "-c", "pass"],
                           env=env_b, capture_output=True, text=True, timeout=60)
        assert p.returncode == 0, f"另一套部署被挡住了：{p.stdout}{p.stderr}"
        assert (b / "locks" / "gateway.lock").is_file()
    finally:
        holder.terminate()
        holder.wait(timeout=30)


def test_gateway_lock_env_override_lets_two_roots_share_one_gateway(tmp_path):
    """例外的口子：`GENEBENCH_GATEWAY_LOCK` 指同一个文件 → 两套根重新互斥。"""
    shared = tmp_path / "shared.lock"
    env_a = dict(os.environ, GENEBENCH_ROOT=str(tmp_path / "a"), GENEBENCH_GATEWAY_LOCK=str(shared))
    env_b = dict(os.environ, GENEBENCH_ROOT=str(tmp_path / "b"), GENEBENCH_GATEWAY_LOCK=str(shared))
    (tmp_path / "a").mkdir(); (tmp_path / "b").mkdir()
    holder = subprocess.Popen(_lock_cmd(12), env=env_a, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
    try:
        assert _wait_for_holder(shared)
        p = subprocess.run([sys.executable, str(REPO / "ops" / "gateway_lock.py"),
                            "--nowait", "--what", "A9-shared", "--", sys.executable, "-c", "pass"],
                           env=env_b, capture_output=True, text=True, timeout=60)
        assert p.returncode != 0, "共用锁文件时竟然没互斥"
    finally:
        holder.terminate()
        holder.wait(timeout=30)


def test_every_gateway_lock_caller_goes_through_one_implementation():
    """拿这把锁的调用方**逐个核过**：都走 `ops/gateway_lock.py` 这一份，没有第二份实现。"""
    callers = {"ops/run_joblist.py": "from ops.gateway_lock import gateway_lock",
               "ops/run_oracles.py": "from ops.gateway_lock import gateway_lock",
               "ops/public_gateway.sh": "ops/gateway_lock.py"}
    for rel, needle in callers.items():
        assert needle in (REPO / rel).read_text(encoding="utf-8"), f"{rel} 不再走那一份实现？"
    for rel in ("ops/run_joblist.py", "ops/run_oracles.py"):
        tree = ast.parse((REPO / rel).read_text(encoding="utf-8"))
        calls = [n for n in ast.walk(tree)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                 and n.func.attr == "flock"]
        assert not calls, f"{rel} 自己写了第二份 flock 调用 —— 那就不是同一把锁了"


# ===========================================================================
# ⑤ 单机分支一次都不 import 双机那个模块
# ===========================================================================
def test_single_branch_never_imports_the_dual_module(tmp_path):
    """双机默认值关在 `runner/placement_dual.py` 里，而单机分支**永远走不到它**。

    这不是风格：它就是「单机路径上 `/data` 字面量零次」那条判据的**动态**一半。
    """
    root = tmp_path / "gb"
    root.mkdir()
    env = dict(os.environ, GENEBENCH_ROOT=str(root), GENEBENCH_TOPOLOGY="single",
               GENEBENCH_RUNNER_ROOT=str(root / "genebench_runner"),
               GENEBENCH_CHANNEL="public", PYTHONDONTWRITEBYTECODE="1")
    code = (
        "import sys, json\n"
        f"sys.path.insert(0, {str(REPO)!r})\n"
        "import ops.run_joblist as RJ\n"
        "job = {'batch':'v1demo','task_id':'s1-cor-01','config_id':'c','arm':'strict',"
        "'seed':1,'timeout_s':1500,'digest':'sha256:x','budget_override':{}}\n"
        "out = [RJ.f02_run_cmd(job,'public','single'), RJ.score_cmd('v1demo','public','single'),\n"
        "       RJ.bundle_dest(job,'single'), RJ.runner_root('single')]\n"
        "print(json.dumps({'dual_imported': 'runner.placement_dual' in sys.modules,\n"
        "                  'has_ssh': any('ssh' in str(x) for x in out)}))\n"
    )
    p = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True,
                       text=True, timeout=300)
    assert p.returncode == 0, p.stderr[-2000:]
    got = json.loads(p.stdout.strip().splitlines()[-1])
    assert got["dual_imported"] is False, "单机分支把双机那个模块 import 进来了"
    assert got["has_ssh"] is False, "单机分支拼出来的命令里有 ssh"


def test_run_joblist_pins_the_runner_root_into_the_process_env_on_single():
    """单机形态下 `main()` 必须把执行面根钉进本进程环境 —— 否则惰性 import 进来的
    `runner.c41.runner_core.ROOT` 会取**双机默认**，落位与真跑就指着两个根。"""
    s = (REPO / "ops" / "run_joblist.py").read_text(encoding="utf-8")
    assert "os.environ.setdefault(PL.RUNNER_ROOT_ENV, runner_root(a.topology))" in s


# ===========================================================================
# ⑥ 判据的静态一半：单机路径上 "/data" 字面量出现零次
# ===========================================================================
#: 单机路径的**入口集合**（README §2.4 的四条命令实际调到的入口；卡 A9 第 1 步那张表）。
SINGLE_PATH_ENTRIES: tuple[str, ...] = (
    "ops/joblist.py",          # ① 生成清单
    "ops/run_joblist.py",      # ②④ 干跑 / 真跑六段
    "runner/placement.py",     # ③ exec 树与 bundle 的**本地落位**（替代两个 push 脚本）
    "ops/score_runs.py",       # ④ 结算
    "ops/results_db.py",       # ④ 入库
    "ops/mk_tables.py",        # ⑤ 出表
)

#: **不在单机路径上**、因而不参与本门的文件。**逐字闭集，不许用通配。**
SINGLE_PATH_EXCLUDED: dict[str, str] = {
    "runner/placement_dual.py":
        "双机形态专用：它存在的唯一理由就是把发布方执行面的绝对路径关进一个"
        "单机分支不 import 的文件里。`test_single_branch_never_imports_the_dual_module` "
        "真起一个 single 进程证明它没被 import。",
}

#: 豁免：**每一行原文照抄**（闭集），每个文件写明理由。新加任何一行 `/data` 都会红。
DATA_LITERAL_EXEMPT: dict[str, tuple[str, ...]] = {
    'genebench_config.py': (
        # 理由：仓库**唯一**声明允许出现绝对路径字面量的模块（它自己的 docstring 明写）；单机用户设 `GENEBENCH_ROOT` 之后 `_DEFAULT_ROOT` 不再被取用，`LAKE`/`QLIB_RELEASE` 只在「自己重建数据面」那条链上用，不在 §2.4 单机路径上。
        '禁止把 `/data/shared/genebench`、`/home/ljn/projects/data/...` 之类',
        '当前落点 `/data/shared/genebench` 是**临时**的:`/data` 是 root:root 0755,',
        'ljn 无法 `mkdir /data/genebench`,规范落点需要一条人工特权命令',
        'GENEBENCH_ROOT=/data/genebench python -m gateway.app',
        '#: 临时落点。规范落点 `/data/genebench` 需要 T-01 特权窗口后才能启用。',
        '_DEFAULT_ROOT = "/data/shared/genebench"',
        '#: 目录 mode 必须是 0700 —— `/data/shared` 是 1777 的公共目录,',
        'LAKE: Path = Path("/home/ljn/projects/data/market_lake")',
        'QLIB_RELEASE: Path = Path("/home/ljn/projects/data/qlib/releases/2026-08-26")',
        '#: `/data/shared` 是 1777 的公共目录,答案产物(`reference/`、`scorer/`)',
    ),
    'genetask/schema.py': (
        # 理由：docstring 里对 X 面落点的举例，不参与取值。
        '* **X 面**（执行面，f02 `/data/genebench_runner/tasks/<id>/`）：`export()` 剥掉 D 键后的 task.yaml。',
    ),
    'ops/export_bundle.py': (
        # 理由：docstring 里的照抄命令与一句提示文案，不参与取值。
        'flock /data/shared/genebench/locks/heavy.lock \\',
        '/data/shared/genebench/env/bin/python ops/freeze_v10.py --write',
        'f"/data/genebench_runner/<run>/runner/tasks {r[\'manifest\']}")',
    ),
    'ops/freeze_v10.py': (
        # 理由：冻结清单里两条被截断的**说明文本**（字符串内容是记因，不是路径取值）。
        '"交易日只留 3 个最小代码。三者 sha 写回 params；数据卡 `ops/data_cards/fixture_s"',
        '"件 + 两臂干注入 run dir 全部文件」sha256 逐条相同（`/data/shared/genebench/s"',
    ),
    'ops/gateway_lock.py': (
        # 理由：`lock_path()` docstring 里写「以前这里写死的是什么」—— 记因，不是取值；取值已从 `cfg.GENEBENCH_ROOT` 现算。
        '以前这里写死 `/data/shared/genebench/locks/gateway.lock`，而真跑**每个 job**',
        '都进这个上下文（`ops/run_joblist.py::run_one`）—— 于是在一台造不出 `/data` 的机器上',
    ),
    'ops/joblist.py': (
        # 理由：docstring 里的历史举例（2026 年那个没有状态的 shell 循环），不参与取值。
        '的 shell 循环（`f02:/data/genebench_runner/m6/run_m6.sh`）—— 它没有状态。断在第五道题上，',
    ),
    'ops/mk_tables.py': (
        # 理由：表脚里渲染给读者的「复现命令」用了发布方的解释器路径 —— **这是一处真缺陷**（外部单机用户照抄不到），已登记 N-850；它不改变本进程取任何路径，故不挡本门。
        '"PY=/data/shared/genebench/env/bin/python; cd /data/shared/genebench/repo",',
    ),
    'ops/push_guard.py': (
        # 理由：`ADAPT_DEST_PREFIX` 是**适配赛道**（`set_id == v1.0-adapt`）专用的落点前缀；§2.4 那四道题的 `set_id` 不是它，这条判据在单机路径上不取用。另一条是 docstring 里的事故复盘。
        '`rsync -a /data/shared/genebench/scratch/a1/ f02:/data/genebench_runner/a1/`',
        'ADAPT_DEST_PREFIX = "/data/genebench_runner/adapt/"',
    ),
    'ops/run_controls.py': (
        # 理由：三控侧的 docstring 照抄命令与一处记因；三控不在 §2.4 单机路径上。
        '--answer-root /data/shared/genebench/reference/tasks/public/v1.0-smoke-public \\\\',
        '--gateway-log /data/shared/genebench/logs/gateway_access_public.jsonl --out <落点>',
        '#: 发布方那台上 `cfg.GENEBENCH_ROOT == /data/shared/genebench`，所以值一字未动。',
        '"复现这一跑（**照抄整条**；`GB=/data/shared/genebench`、`PY=$GB/env/bin/python`）：", "",',
    ),
    'ops/run_joblist.py': (
        # 理由：`topology()` docstring 里解释病因的那一句（「这台机器能不能造出 `/data/...`」），不参与取值。
        '`/data/...`」，它在 Linux 上就永远是绿的，只有 macOS（根卷只读）才显形。',
    ),
    'ops/run_probe_mutations.py': (
        # 理由：注释里的记因，不参与取值。
        '#: （发布方那台上 `cfg.GENEBENCH_ROOT` 就是 `/data/shared/genebench`）——',
    ),
    'ops/score_runs.py': (
        # 理由：模块 docstring 的用法举例与 `split_remote` 的反例说明；取值侧 `RUNS_IN` 已从 `cfg` 现算（N-770）。
        '拉回来的 run 目录落 `/data/shared/genebench/runs_in/<batch>/`（0700），不进仓库。',
        'python ops/score_runs.py --batch a1 --remote /data/genebench_runner/a1/runs/runs [--no-pull]',
        '只认**冒号出现在第一个斜杠之前**的那种写法 —— `/data/a:b` 是一个本机路径，',
    ),
    'reference/__init__.py': (
        # 理由：注释里解释 0700 保护的理由，不参与取值。
        '目录靠 `$GENEBENCH_ROOT` 的 0700 保护(`/data/shared` 是 1777 公共目录)。',
    ),
    'reference/make_fixtures.py': (
        # 理由：注释里的数据卡文件名（`fixture_s4_eco_pool_v1.md` 撞上子串 `/data`），不是路径。
        '#: 选取规则与最终清单写进夹具数据卡（`ops/data_cards/fixture_s4_eco_pool_v1.md`）。',
    ),
    'runner/c41/runner_core.py': (
        # 理由：`DATA_ROOTS` 不是「根」，是**禁挂**宿主数据目录的黑名单（作用是拒绝，不是取值），换机器只会让它少拒一点、不会让它错拒；其余四条是注释里的攻击面说明。`ROOT` 本卡已改成 `GENEBENCH_RUNNER_ROOT` 优先。
        '`GENEBENCH_RUNNER_ROOT` 之后根本走不到这里（卡 A9：单机路径上 `/data` 字面量零次）。"""',
        '#: **不要**把 `/data` 本身写进来 —— 那会让规则恒红（run dir 也在 /data 下），',
        'DATA_ROOTS: tuple[str, ...] = ("/data/shared", "/data/market_lake_f02",',
        '"/data/genebench_runner/manifests",',
        '"/data/genebench_runner/provider")',
        '# 原先只收绝对路径 —— 相对路径（`./sneak`、`../../data/shared`）与 `${VAR}` 插值',
        '# 符号链接可以在 lint 之后、容器启动之前被改指向 /data/shared（TOCTOU），',
        '# `volumes: {sneak: {driver_opts: {type: none, device: /data/shared, o: bind}}}` 是一个',
    ),
    'runner/f02/answer_plane_guard.py': (
        # 理由：`DEFAULT_ROOT` / `DEFAULT_LOG` 是这道门**命令行的默认值**，而 f02 上那个每小时的 systemd timer 正吃这两个默认 —— 动它等于悄悄改掉「兜底扫描扫哪棵树」。单机路径上**永远显式传 `--root` 与 `--log`**（`runner/placement._scan_tree` / `place_bundle`，本文件有一条测试钉住），所以默认值不被取用。另两条是 docstring。
        '# 扫 `/data/genebench_runner` 整棵，命中即删。',
        '① **不要求挂载源此刻存在**：`- /data/shared/genebench/reference:/task/ref` 这一条，',
        'DEFAULT_ROOT = "/data/genebench_runner"',
        'DEFAULT_LOG = "/data/genebench_runner/logs/answer_plane.jsonl"',
    ),
    'runner/inject.py': (
        # 理由：两条注释（边车老路径的记因、挂载点解析的说明），不参与取值。
        '#: `/data/genebench_runner/egress_proxy.py` —— 一个 run dir **之外**的固定路径，',
        '# 生产上 /data 挂载点也常有一层）。不 resolve 的话，L-5a 会拿注入器自己写的',
    ),
    'runner/placement.py': (
        # 理由：本模块 docstring 里解释病因与判据的三句，以及「单机现算、零 `/data` 字面量」那一句本身；不参与取值。
        'Linux 上，而 Linux 可以 `mkdir /data` 把写死的路径造出来（卡 D2 那次正是这么绕的），',
        '**macOS 根卷只读、`sudo mkdir /data` 直接失败**，于是这一条在 Linux 上永远不显形。',
        '**不靠「这台机器像不像发布方」判**（没有 hostname 嗅探、没有 `/data` 存在性探测）——',
        '* 单机：`cfg.GENEBENCH_ROOT / "genebench_runner"` —— **现算**，零 `/data` 字面量；',
    ),
}


def _repo_module_path(mod: str) -> Path | None:
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


def single_path_closure() -> list[Path]:
    """单机路径的入口集合 + 它们 import 的**本仓**模块（传递闭包）。"""
    seen: set[Path] = set()
    stack = [REPO / e for e in SINGLE_PATH_ENTRIES]
    while stack:
        f = stack.pop()
        if f in seen or not f.is_file():
            continue
        rel = str(f.relative_to(REPO))
        if rel in SINGLE_PATH_EXCLUDED or rel.startswith("ops/test_"):
            continue
        seen.add(f)
        for m in _imports_of(f):
            p = _repo_module_path(m)
            if p is not None:
                stack.append(p)
    return sorted(seen)


def test_single_path_closure_covers_the_four_commands():
    """闭包要真的把 §2.4 那几条命令的入口都算进去，否则这道门是空的。"""
    rels = {str(p.relative_to(REPO)) for p in single_path_closure()}
    for e in SINGLE_PATH_ENTRIES:
        assert e in rels, f"入口 {e} 不在闭包里"
    assert "genebench_config.py" in rels and "runner/c41/runner_core.py" in rels
    assert "runner/placement_dual.py" not in rels
    assert len(rels) >= 40, f"闭包只有 {len(rels)} 个文件 —— 走塌了"


def test_single_machine_path_has_no_data_literal():
    """**裁定 ③ 的静态判据：单机路径上 `/data` 字面量出现零次。**

    豁免是 `DATA_LITERAL_EXEMPT` 那个**逐字闭集** —— 每一行原文照抄、每个文件写明理由。
    新出现的任何一行 `/data`（哪怕在已豁免的文件里）都会让这条红。
    """
    bad: list[str] = []
    for f in single_path_closure():
        rel = str(f.relative_to(REPO))
        allowed = DATA_LITERAL_EXEMPT.get(rel, ())
        for i, ln in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if "/data" not in ln:
                continue
            if ln.strip() in allowed:
                continue
            bad.append(f"{rel}:{i}: {ln.strip()}")
    assert not bad, (
        "单机路径上出现了未豁免的 `/data` 字面量（共 %d 行）：\n  " % len(bad)
        + "\n  ".join(bad[:20])
        + "\n\n要么把它从 `cfg.GENEBENCH_ROOT` 现算（首选），"
          "要么把它搬进 `runner/placement_dual.py`（双机专用），"
          "要么原文照抄进 `DATA_LITERAL_EXEMPT` 并写明理由 —— **不许用通配**。")


def test_the_exempt_list_is_closed_and_current():
    """豁免清单不许留死条目（文件没了、或那一行已经改掉）—— 否则它会悄悄放宽。"""
    stale: list[str] = []
    for rel, lines in DATA_LITERAL_EXEMPT.items():
        f = REPO / rel
        if not f.is_file():
            stale.append(f"{rel}（文件不在了）")
            continue
        have = {ln.strip() for ln in f.read_text(encoding="utf-8").splitlines() if "/data" in ln}
        for ln in lines:
            if ln not in have:
                stale.append(f"{rel}: {ln[:80]}")
    assert not stale, "豁免清单里有死条目，清掉：\n  " + "\n  ".join(stale)


# ===========================================================================
# ⑦ 真落一次 exec 树：临时根 + ssh 垫片，证明**一次 ssh 都没发**
# ===========================================================================
@pytest.mark.skipif(shutil.which("rsync") is None, reason="本机没有 rsync")
def test_place_exec_tree_really_lands_and_sends_no_ssh(tmp_path):
    """把 exec 树真落一次到一个**临时** `GENEBENCH_ROOT`，`PATH` 前面垫上会报错的
    `ssh` / `scp` —— 落完了垫片日志必须是空的。

    这条同时验掉 N-840（`push_exec_to_f02.sh` 的两个发布方默认路径 → rc=127）：
    单机路径根本不调那个脚本。
    """
    shim = tmp_path / "shim"
    shim.mkdir()
    log = tmp_path / "ssh_calls.log"
    for name in ("ssh", "scp", "rsh"):
        p = shim / name
        p.write_text(f'#!/bin/sh\necho "{name} $*" >> {log}\nexit 97\n', encoding="utf-8")
        p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    root = tmp_path / "gb"
    root.mkdir(mode=0o700)
    env = dict(os.environ,
               PATH=f"{shim}:{os.environ.get('PATH', '')}",
               GENEBENCH_ROOT=str(root), GENEBENCH_TOPOLOGY="single",
               GENEBENCH_RUNNER_PY=sys.executable, PYTHONDONTWRITEBYTECODE="1")
    env.pop("GENEBENCH_RUNNER_ROOT", None)
    p = subprocess.run([sys.executable, "-m", "runner.placement",
                        "--topology", "single", "--place-exec", "--with-launch-data"],
                       cwd=str(REPO), env=env, capture_output=True, text=True, timeout=900)
    assert p.returncode == 0, f"落位失败：\n{p.stdout[-3000:]}\n{p.stderr[-3000:]}"
    got = json.loads(p.stdout[p.stdout.index("{"):])
    dest = Path(got["dest"])
    assert dest == root / "genebench_runner" / "exec"
    assert (dest / "runner" / "c42" / "harness_commands.py").is_file()
    assert (dest / "genetask" / "arms.yaml").is_file()
    assert (dest / "harnesses").is_dir() and (dest / "integrations").is_dir()
    assert got["parity_bytes"] and got["parity_bytes"] > 0
    # **答案面一件都没落地**（红线 B2，树口径）
    for name in PL.FORBIDDEN_NAMES:
        assert not list(dest.rglob(name)), f"落位树里出现答案面文件名 {name}"
    for seg in PL.FORBIDDEN_SEGMENTS:
        assert not list(dest.rglob(seg)), f"落位树里出现禁段 {seg}"
    # **一次 ssh 都没发**
    assert not log.exists(), f"单机落位发了 ssh/scp：{log.read_text(encoding='utf-8')[:800]}"
    # 红线 5：落出来的目录一律 go-rwx
    loose = [str(d) for d in dest.rglob("*") if d.is_dir()
             and (d.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO))][:5]
    assert not loose, f"落位树里有对组/其它开放的目录：{loose}"
