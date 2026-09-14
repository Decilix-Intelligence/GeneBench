#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""卡 5.3 的判据：作业清单的笛卡尔积、状态机、续跑、不自动重试、并发数来源、干跑。

**不打网关、不 ssh、不出集**：真跑那一步在这里全部被 monkeypatch 掉，
凡是「本测试跑起来会真的花钱」的路径都有一条断言钉着它没被走到。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from ops import joblist as JL                                # noqa: E402
from ops import run_joblist as RJ                            # noqa: E402
from runner import registry as REG                           # noqa: E402

DIG = "sha256:" + "a" * 64
from runner import inject as INJ                            # 裁定 ⑮：机器标识

CFG = "cfg-codex-deepseek"
#: 裁定 ⑮：run_id / job_id 末尾的机器标识后缀（本机现算的那一个）。
MSUF = INJ.MACHINE_SEP + INJ.machine_id()


def matrix(**kw) -> dict:
    m = {"name": "t", "batch": "tb", "configs": [CFG],
         "tasks": ["s1-cor-01", "s2-cor-01"], "arms": ["strict", "open"], "seeds": [1],
         "image": "gb-cx-u", "digest": DIG, "timeout_s": 1500}
    m.update(kw)
    return m


@pytest.fixture()
def jobs_file(tmp_path) -> Path:
    p = tmp_path / "jobs.jsonl"
    JL.save(p, JL.gen(matrix()))
    return p


# ------------------------------------------------------------------ 生成

def test_cartesian_product_is_task_x_arm_x_config_x_seed():
    jobs = JL.gen(matrix(tasks=["s1-cor-01", "s2-cor-01", "s3-cor-01"], seeds=[1, 2]))
    assert len(jobs) == 3 * 2 * 1 * 2
    # 外到内的顺序：同一道题的两臂挨在一起
    assert [j["job_id"] for j in jobs[:4]] == [
        # 裁定 ⑮：job_id 末尾带机器标识（`runner.inject.run_id` 算的那一份）。
        f"s1-cor-01.strict.{CFG}.r01{MSUF}", f"s1-cor-01.strict.{CFG}.r02{MSUF}",
        f"s1-cor-01.open.{CFG}.r01{MSUF}", f"s1-cor-01.open.{CFG}.r02{MSUF}"]
    assert len({j["job_id"] for j in jobs}) == len(jobs)
    assert {j["status"] for j in jobs} == {"pending"}
    assert {j["batch"] for j in jobs} == {"tb"}


def test_job_id_is_byte_identical_to_runner_run_id():
    """job_id 与 `runner.inject.run_id` 不同源的话，「这个 job 跑出来的是哪个 run」就要靠映射表。

    裁定 ⑮ 之后 `job_id` **就是 `run_id` 算的**（`make_job` 直接调它），末尾带机器标识。
    前四段仍然逐字钉死。
    """
    from runner.inject import run_id, split_run_id
    j = JL.gen(matrix(tasks=["s5-cor-01"], seeds=[7]))[0]
    assert j["job_id"] == run_id("s5-cor-01", "strict", CFG, 7)
    assert split_run_id(j["job_id"])[0] == f"s5-cor-01.strict.{CFG}.r07"


def test_budget_tier_is_recorded_per_stage():
    """预算档随 stage 走（卡 4.3）：S4/S7 抬档，其余默认档。"""
    j1 = {j["task_id"]: j for j in JL.gen(matrix(tasks=["s1-cor-01", "s4-cor-01", "s7-cor-01"]))}
    assert j1["s1-cor-01"]["budget_tier"] == "default"
    assert j1["s1-cor-01"]["budget"] == dict(REG.RUN_BUDGET_DEFAULT)
    assert j1["s4-cor-01"]["budget_tier"] == "S4"
    assert j1["s4-cor-01"]["budget"] == {"max_calls": 150, "max_tokens": 9_000_000}
    assert j1["s7-cor-01"]["budget"] == {"max_calls": 300, "max_tokens": 18_000_000}
    assert all(j["budget_override"] == {} for j in j1.values())


def test_explicit_budget_override_is_recorded_and_passed_down():
    """矩阵里显式写了预算才传参数；不写就**一个预算参数都不给**（给了会把档位关掉）。"""
    plain = JL.gen(matrix(tasks=["s4-cor-01"]))[0]
    assert " --max-calls" not in RJ.f02_run_cmd(plain)[-1]
    assert " --max-tokens" not in RJ.f02_run_cmd(plain)[-1]
    over = JL.gen(matrix(tasks=["s4-cor-01"], max_calls=20))[0]
    assert over["budget_override"] == {"max_calls": 20}
    assert over["budget"]["max_calls"] == 20
    assert over["budget"]["max_tokens"] == 9_000_000        # 逐键覆盖：tokens 仍走档位
    assert "--max-calls 20" in RJ.f02_run_cmd(over)[-1]
    assert "--max-tokens" not in RJ.f02_run_cmd(over)[-1]


def test_matrix_key_set_is_exact():
    with pytest.raises(JL.JoblistError, match="键集"):
        JL.gen(matrix(**{"nonsense": 1}))
    m = matrix()
    del m["tasks"]
    with pytest.raises(JL.JoblistError, match="键集"):
        JL.gen(m)


@pytest.mark.parametrize("arms, msg", [
    (["strict", "nope", "open"], "未登记的臂"),
    (["strict"], "参照臂"),
    (["open", "strict"], "第一个"),
    (["strict", "strict", "open"], "重复"),
])
def test_arm_set_gates(arms, msg):
    with pytest.raises(JL.JoblistError, match=msg):
        JL.gen(matrix(arms=arms))


def test_unknown_config_and_task_are_rejected_at_gen_time():
    with pytest.raises(REG.RegistryError):
        JL.gen(matrix(configs=["cfg-does-not-exist"]))
    with pytest.raises(JL.JoblistError, match="参数表里没有这些题"):
        JL.gen(matrix(tasks=["s9-nope-01"]))


def test_seeds_must_be_positive_and_unique():
    with pytest.raises(JL.JoblistError, match="seed 必须"):
        JL.gen(matrix(seeds=[0]))
    with pytest.raises(JL.JoblistError, match="重复"):
        JL.gen(matrix(seeds=[1, 1]))


def test_shipped_matrix_is_loadable_and_is_eight_jobs():
    m = JL.load_matrix(_REPO / "ops" / "joblists" / "v1demo.yaml")
    jobs = JL.gen(m)
    assert len(jobs) == 8
    assert sorted({j["task_id"] for j in jobs}) == ["s1-cor-01", "s2-cor-01", "s3-cor-01", "s5-cor-01"]
    assert sorted({j["arm"] for j in jobs}) == ["open", "strict"]
    # 出集必须钉执行面上真有的镜像
    assert all(j["digest"].startswith("sha256:") and len(j["digest"]) == 71 for j in jobs)
    # **两个键都不写**（N-388 已裁定，2026-09-10）：默认档抬到 100 次 / 6,000,000 tokens 之后，
    # 此前那条「显式给 3M」的绕法**作废** —— 3M 比默认档还低，写上去是把预算压下去。
    # 这份矩阵是两份文档点名让读者照抄的最短路径，所以它必须**示范正确做法**：
    # 什么都不写 = 按 stage 取档（S4 150/9M、S7 300/18M、其余 100/6M）。
    # 当初为什么要绕，读数还在：ops/reports/v1demo/ 那 8 个 run 在 600k 默认档下 8/8 撞闸。
    assert all(j["budget_override"] == {} for j in jobs)
    assert all(j["budget"]["max_tokens"] == 6_000_000 for j in jobs)
    assert all(j["budget"]["max_calls"] == 100 for j in jobs)


# ------------------------------------------------------------------ 状态机

def test_state_machine_pending_running_done():
    JL.check_transition("pending", "running")
    JL.check_transition("running", "done")
    JL.check_transition("running", "failed")
    JL.check_transition("running", "budget_exhausted")


@pytest.mark.parametrize("old, new", [
    ("pending", "done"), ("pending", "failed"), ("pending", "budget_exhausted"),
    ("done", "running"), ("failed", "running"), ("budget_exhausted", "done"),
    ("done", "failed"),
])
def test_illegal_transitions_raise(old, new):
    with pytest.raises(JL.JoblistError, match="不合法的状态迁移"):
        JL.check_transition(old, new, "x")


def test_terminal_back_to_pending_is_the_only_way_out():
    for t in JL.TERMINAL:
        JL.check_transition(t, "pending")


def test_update_enforces_the_state_machine(jobs_file):
    jid = JL.load(jobs_file)[0]["job_id"]
    JL.update(jobs_file, jid, status="running")
    JL.update(jobs_file, jid, status="done")
    with pytest.raises(JL.JoblistError, match="不合法的状态迁移"):
        JL.update(jobs_file, jid, status="running")
    assert JL.load(jobs_file)[0]["status"] == "done"


def test_update_is_persisted_and_leaves_other_rows_alone(jobs_file):
    before = JL.load(jobs_file)
    JL.update(jobs_file, before[2]["job_id"], status="running", run_id="rid-1")
    after = JL.load(jobs_file)
    assert after[2]["status"] == "running" and after[2]["run_id"] == "rid-1"
    assert [j["status"] for j in after] == ["pending", "pending", "running"] + ["pending"] * (len(after) - 3)
    assert jobs_file.stat().st_mode & 0o077 == 0             # 红线 5：go-rwx


def test_update_unknown_job_raises(jobs_file):
    with pytest.raises(JL.JoblistError, match="没有 job"):
        JL.update(jobs_file, "no-such-job", status="running")


# ------------------------------------------------------------------ 续跑 / 不自动重试

def test_resume_skips_done(jobs_file):
    jobs = JL.load(jobs_file)
    JL.update(jobs_file, jobs[0]["job_id"], status="running")
    JL.update(jobs_file, jobs[0]["job_id"], status="done")
    todo, skip = JL.select(JL.load(jobs_file), resume=True)
    assert jobs[0]["job_id"] not in [j["job_id"] for j in todo]
    assert jobs[0]["job_id"] in [j["job_id"] for j in skip]
    assert len(todo) == len(jobs) - 1


def test_failed_and_budget_exhausted_are_not_retried_by_default(jobs_file):
    jobs = JL.load(jobs_file)
    for j, st in ((jobs[0], "failed"), (jobs[1], "budget_exhausted")):
        JL.update(jobs_file, j["job_id"], status="running")
        JL.update(jobs_file, j["job_id"], status=st)
    todo, skip = JL.select(JL.load(jobs_file), resume=True)
    ids = [j["job_id"] for j in todo]
    assert jobs[0]["job_id"] not in ids and jobs[1]["job_id"] not in ids
    assert len(skip) == 2
    # 显式重跑才回来，而且**只回来点名的那一种**
    todo2, _ = JL.select(JL.load(jobs_file), retry_status=["failed"])
    ids2 = [j["job_id"] for j in todo2]
    assert jobs[0]["job_id"] in ids2 and jobs[1]["job_id"] not in ids2


def test_retry_status_rejects_unknown_status(jobs_file):
    with pytest.raises(JL.JoblistError, match="未知状态"):
        JL.select(JL.load(jobs_file), retry_status=["nope"])


def test_select_only_task_and_limit(jobs_file):
    todo, _ = JL.select(JL.load(jobs_file), only_tasks=["s2-cor-01"])
    assert {j["task_id"] for j in todo} == {"s2-cor-01"}
    todo2, skip2 = JL.select(JL.load(jobs_file), limit=1)
    assert len(todo2) == 1 and len(skip2) == len(JL.load(jobs_file)) - 1


def test_stat_counts_every_status(jobs_file):
    st = JL.stat(JL.load(jobs_file))
    assert set(st) >= set(JL.STATUSES)
    assert st["pending"] == 4 and sum(st.values()) == 4


# ------------------------------------------------------------------ 并发数来自 registry

def test_concurrency_comes_from_registry(monkeypatch):
    assert REG.RUNNER_CONCURRENCY == 1                        # 默认 1：网关单 worker + gateway_lock 串行
    assert JL.concurrency() == 1
    monkeypatch.setattr(REG, "RUNNER_CONCURRENCY", 4, raising=True)
    assert JL.concurrency() == 4                              # 现读，不缓存


def test_registry_concurrency_is_a_positive_int():
    assert isinstance(REG.RUNNER_CONCURRENCY, int) and REG.RUNNER_CONCURRENCY >= 1


# ------------------------------------------------------------------ 干跑

def test_dry_run_touches_nothing(jobs_file, monkeypatch, capsys):
    """`--dry` 一条命令都不执行、清单一个字节都不改。"""
    def boom(*a, **k):                                        # 任何 subprocess 都是真跑的入口
        raise AssertionError("--dry 竟然起了子进程")
    monkeypatch.setattr(RJ.subprocess, "run", boom)
    monkeypatch.setattr(RJ, "export_and_push", boom)
    before = jobs_file.read_bytes()
    assert RJ.main(["--jobs", str(jobs_file), "--dry"]) == 0
    assert jobs_file.read_bytes() == before
    out = capsys.readouterr().out
    assert "一条都没有执行" in out
    assert "ops/export_bundle.py" in out and "run_f02_a1.py" in out and "score_runs.py" in out


def test_dry_run_prints_no_budget_flags(jobs_file, monkeypatch, capsys):
    monkeypatch.setattr(RJ.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError()))
    RJ.main(["--jobs", str(jobs_file), "--dry"])
    out = capsys.readouterr().out
    assert "--max-calls" not in out and "--max-tokens" not in out


def test_dry_run_export_is_once_per_task(jobs_file, monkeypatch, capsys):
    monkeypatch.setattr(RJ.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError()))
    RJ.main(["--jobs", str(jobs_file), "--dry"])
    out = capsys.readouterr().out
    assert out.count("ops/export_bundle.py") == 2             # 4 个 job、2 道题 → 出集两次
    assert out.count("run_f02_a1.py") == 4


# ------------------------------------------------------------------ 命令拼装

def test_score_cmd_has_the_double_runs_path():
    """`--remote` 少一层 `runs` 会退 0 并打印「runs: 0；问题: 0」——不报错的错（HANDOFF 14.4 §1）。

    **按 `--remote` 取它自己的值**，不取 `[-1]`：卡 6.5 给 `score_cmd` 追加了
    `--ref-tasks` / `--gateway-log`（按通道给题集根与网关日志），命令的最后一个元素
    因此不再是 remote 路径。判据没变，取值方式跟着命令形状走。
    """
    cmd = RJ.score_cmd("v1demo")
    assert cmd[cmd.index("--remote") + 1].endswith("/v1demo/runs/runs")


def test_f02_cmd_is_single_arm_and_carries_the_umask():
    j = JL.gen(matrix(tasks=["s2-cor-01"]))[0]
    inner = RJ.f02_run_cmd(j)[-1]
    assert "--arms strict" in inner and "--arms strict,open" not in inner
    assert inner.startswith("umask 022; export PYTHONDONTWRITEBYTECODE=1;")   # 红线 B7
    assert "--seq 1" in inner and "--config-id cfg-codex-deepseek" in inner


def test_push_uses_the_only_allowed_entry_point():
    j = JL.gen(matrix(tasks=["s2-cor-01"]))[0]
    c = RJ.push_cmd(j, RJ.staging_of(j))
    assert c[0].endswith("ops/push_bundle_to_f02.sh")         # 红线 B2
    assert c[2].startswith("/data/genebench_runner/tb/runner/tasks")


# ------------------------------------------------------------------ 回写

def _record(job_id: str, run_status: str) -> dict:
    return {"run_id": job_id, "run_status": run_status, "validity": None,
            "l3_kind": None, "l3_pass": None, "steps": 3}


def test_writeback_maps_budget_exhausted_to_its_own_state(jobs_file):
    jobs = JL.load(jobs_file)
    for j in jobs[:3]:
        JL.update(jobs_file, j["job_id"], status="running", run_id=j["job_id"])
    recs = [_record(jobs[0]["job_id"], "ok"),
            _record(jobs[1]["job_id"], "budget_exhausted")]
    out = RJ.writeback("tb", jobs_file, [j["job_id"] for j in jobs], records=recs)
    assert out[jobs[0]["job_id"]] == "done"
    assert out[jobs[1]["job_id"]] == "budget_exhausted"
    assert out[jobs[2]["job_id"]] == "failed"                 # 跑了但结算里没有它
    final = {j["job_id"]: j["status"] for j in JL.load(jobs_file)}
    assert final[jobs[3]["job_id"]] == "pending"              # 没被点名的一行不动


def test_writeback_leaves_non_running_rows_alone(jobs_file):
    jobs = JL.load(jobs_file)
    out = RJ.writeback("tb", jobs_file, [j["job_id"] for j in jobs],
                       records=[_record(jobs[0]["job_id"], "ok")])
    assert out == {}
    assert {j["status"] for j in JL.load(jobs_file)} == {"pending"}


# ------------------------------------------------------------------ CLI（gen / stat / reset）

def test_cli_gen_refuses_to_clobber_existing_list(tmp_path):
    p = tmp_path / "j.jsonl"
    args = ["gen", "--batch", "tb", "--configs", CFG, "--tasks", "s1-cor-01",
            "--arms", "strict,open", "--seeds", "1", "--out", str(p)]
    assert JL.main(args) == 0
    with pytest.raises(SystemExit, match="已存在"):
        JL.main(args)
    assert JL.main(args + ["--force"]) == 0


def test_cli_reset_is_explicit(tmp_path, capsys):
    p = tmp_path / "j.jsonl"
    JL.save(p, JL.gen(matrix()))
    jid = JL.load(p)[0]["job_id"]
    JL.update(p, jid, status="running")
    JL.update(p, jid, status="failed")
    JL.main(["reset", str(p), "--status", "failed"])
    assert JL.load(p)[0]["status"] == "pending"


def test_jobs_path_lives_next_to_the_runs_of_that_batch():
    import genebench_config as cfg
    assert JL.jobs_path("v1demo") == cfg.GENEBENCH_ROOT / "runs_in" / "v1demo" / "jobs.jsonl"
