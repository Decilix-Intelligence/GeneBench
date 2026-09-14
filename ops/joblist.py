#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""作业清单（卡 5.3，线 C，2026-09-07）：把「config × 任务 × 臂 × 种子」摊平成一份 `jobs.jsonl`。

    python ops/joblist.py gen --matrix ops/joblists/v1demo.yaml
    python ops/joblist.py gen --batch x --configs cfg-codex-deepseek \
        --tasks s1-cor-01,s2-cor-01 --arms strict,open --seeds 1
    python ops/joblist.py stat  $GB/runs_in/v1demo/jobs.jsonl
    python ops/joblist.py list  $GB/runs_in/v1demo/jobs.jsonl --status pending

**为什么清单要先落盘再跑**（这是本卡的全部理由）：在此之前一批真跑是一个 `for t in …; do`
的 shell 循环（`f02:/data/genebench_runner/m6/run_m6.sh`）—— 它没有状态。断在第五道题上，
「哪几道跑过了」这个问题只能靠翻 `results/` 目录名回答；而「第三道题撞了预算闸」与
「第三道题根本没起」在那个目录里长得一模一样。清单把**每一个 (task, arm, config, seed)
的去向**写成一行，于是续跑是查询而不是回忆。

`job_id` = `<task_id>.<arm>.<config_id>.r<NN>@<machine_id>` —— **就是 `runner.inject.run_id` 算的**（不是抄一份）。末尾的机器标识见裁定 ⑮ 与该函数的说明；跑批时 f01 会把自己的 `GENEBENCH_MACHINE_ID` 送给 f02，两边因此仍然逐字相同。
两个 id 不同源的话，「这个 job 跑出来的是哪个 run」就要靠一张映射表，而映射表会漂。

**状态机**（`TRANSITIONS`）::

    pending ──► running ──► done | failed | budget_exhausted
       └──────► skipped
    任何终态 ──► pending   （**只有显式 retry / reset 走这条**，不会自动发生）

`failed` 与 `budget_exhausted` 都是**终态**，运行器不会自动重跑它们（卡 5.3 的判据）。
撞闸尤其不该自动重跑：同样的预算档跑第二次仍然会撞，而重跑会让
`runner.inject` 的「run dir 已存在」当场抛（F9：不覆盖遥测）。

**预算档只记不改**：`budget` / `budget_tier` 是 `runner.registry.budget_for(stage)` 在
生成清单那一刻的读数，写进 job 是为了让「这一行当时按哪档跑的」事后查得到。
运行器**不把它作为参数传下去** —— 传下去就等于显式覆盖，反而把档位机制关掉了
（`ops/run_f02_a1.py --max-calls` 的语义；卡 4.3）。要显式压档得在矩阵里写
`max_calls` / `max_tokens`，那时 `budget_override` 非空，运行器才会把参数传下去。
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import genebench_config as cfg                              # noqa: E402
from genetask import bundle as GB                           # noqa: E402
from ops import report_io as RIO                            # noqa: E402
from runner import registry as REG                          # noqa: E402

SCHEMA_VERSION = "1.0"

PARAMS: Path = _REPO / "genetask" / "params" / "v1.0-smoke40.yaml"

#: job 的状态全集。
STATUSES: tuple[str, ...] = ("pending", "running", "done", "failed", "budget_exhausted", "skipped")
#: 终态 —— 运行器默认跳过它们（`--resume` 之外，第一次跑也跳过：清单是可以被人预先标 skipped 的）。
TERMINAL: tuple[str, ...] = ("done", "failed", "budget_exhausted", "skipped")

#: 合法的状态迁移。**写死一张表**而不是「随便改」：一个 job 从 `done` 悄悄回到 `running`
#: 的表现是结果库里同一主键出现两份内容不同的记录，而结果库对那个当场抛（卡 5.4）。
TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"pending", "running", "skipped"}),
    "running": frozenset({"done", "failed", "budget_exhausted", "pending"}),
    "done": frozenset({"pending"}),
    "failed": frozenset({"pending"}),
    "budget_exhausted": frozenset({"pending"}),
    "skipped": frozenset({"pending", "running", "skipped"}),
}

#: 矩阵 YAML 的键**全集**（与 `runner.registry.CONFIG_KEYS` 同一条纪律：多一个键在这里是
#: 静默的，在写它的人眼里却像是生效了）。
MATRIX_REQUIRED: tuple[str, ...] = ("name", "batch", "configs", "tasks", "arms", "seeds")
MATRIX_OPTIONAL: tuple[str, ...] = ("image", "digest", "timeout_s", "max_calls", "max_tokens", "note")

#: job 记录的键全集（顺序即写盘顺序无关 —— 落盘用 `sort_keys`）。
JOB_KEYS: tuple[str, ...] = (
    "job_id", "batch", "task_id", "stage", "arm", "config_id", "seed",
    "budget_tier", "budget", "budget_override", "image", "digest", "timeout_s",
    "status", "attempts", "run_id", "created_at", "started_at", "ended_at", "error", "note")


class JoblistError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------ 落点

def jobs_path(batch: str, root: Path | str | None = None) -> Path:
    """一个批的清单落点。**在 `runs_in/<batch>/` 下** —— 与这一批的 run 目录同宿，
    清 `runs_in/<batch>` 时清单跟着走，不会留下一份指向已经不存在的 run 的清单。"""
    base = Path(root) if root is not None else cfg.GENEBENCH_ROOT / "runs_in"
    return base / batch / "jobs.jsonl"


# ------------------------------------------------------------------ 元信息

def stage_map(params: Path | str | None = None) -> dict[str, str]:
    """`task_id → stage`，取自参数表。**用 `packager.load_params`**，不自己解一遍 YAML ——
    出集用哪张表判「这道题在不在」，这里就得用同一张。"""
    from genetask import packager as P                      # 惰性：packager 比本模块重得多
    return {r["task_id"]: r.get("stage") for r in P.load_params(Path(params or PARAMS))}


def budget_of(stage: str | None, override: dict | None = None) -> tuple[str, dict[str, int]]:
    """`(档位名, 预算)`。档位名是 `registry.BUDGET_TIERS` 的键，或 `"default"`。

    `override` 里给了哪个键就覆盖哪个键（与 `run_f02_a1.py --max-calls/--max-tokens` 的
    **逐键**语义相同）。
    """
    key = str(stage).strip().upper() if stage else ""
    tier = key if key in REG.BUDGET_TIERS else "default"
    b = dict(REG.budget_for(stage))
    for k, v in (override or {}).items():
        if v is not None:
            b[k] = int(v)
    return tier, b


def concurrency() -> int:
    """并发数**从 registry 取**（卡 5.3 判据）。这里不给默认值兜底 —— 常量不在就该红。"""
    return int(REG.RUNNER_CONCURRENCY)


# ------------------------------------------------------------------ 生成

def check_arms(arms: Iterable[str]) -> tuple[str, ...]:
    """清单里的臂集合。判据与 `ops/export_bundle.py::check_arms` 同源（那边是出集侧的门，
    这边是**生成清单时**就红 —— 一个跑到出集才发现臂写错的清单等于白排一晚上）。"""
    ids = tuple(str(a).strip() for a in arms if str(a).strip())
    if not ids:
        raise JoblistError("arms 是空的")
    if len(set(ids)) != len(ids):
        raise JoblistError(f"arms 里有重复：{list(ids)}")
    unknown = [a for a in ids if a not in GB.ARM_BY_ID]
    if unknown:
        raise JoblistError(f"未登记的臂 {unknown} —— 臂集合定义在 genetask/arms.yaml，"
                           f"现在登记的是 {list(GB.ALL_ARMS)}")
    if GB.BASELINE_ARM not in ids:
        raise JoblistError(f"arms {list(ids)} 里没有参照臂 {GB.BASELINE_ARM!r} —— "
                           f"等价规则以它为参照，缺了它出集侧当场拒")
    if ids[0] == GB.BASELINE_ARM:
        raise JoblistError(
            f"arms 的**第一个**是参照臂 {GB.BASELINE_ARM!r}：{list(ids)}。"
            f"出集把第一个臂当干预臂写进等价表，写反了会得到一张 "
            f"{GB.BASELINE_ARM} vs {GB.BASELINE_ARM} 的全绿空表。"
            f"把干预臂写在前面。")
    return ids


def make_job(batch: str, task_id: str, arm: str, config_id: str, seed: int, *,
             stage: str | None, image: str | None = None, digest: str | None = None,
             timeout_s: int = 1500, override: dict | None = None, note: str = "") -> dict:
    """一行 job。`job_id` 与 `runner.inject.run_id` 逐字相同 —— **因为就是它算的**。

    以前这里是一份手抄的 f-string，两处「刻意逐字相同」靠一条测试守着。裁定 ⑮ 给
    `run_id` 加机器标识之后，手抄的那份就得再抄一遍机器标识的取法（含 `GENEBENCH_MACHINE_ID`
    的覆盖语义）—— 抄漏一处的表现是 `job_id != run_id`，于是「这个 job 跑出来的是哪个 run」
    要靠一张会漂的映射表。所以改成直接调那一份。

    **惰性 import**：`runner.inject` 顶层拉执行面的东西（pin / bundle / registry / c41），
    而 `ops/joblist.py` 被一堆只生成清单、不碰执行面的地方 import。
    """
    from runner.inject import run_id as _run_id           # 同源，见 docstring
    tier, budget = budget_of(stage, override)
    return {
        "job_id": _run_id(task_id, arm, config_id, int(seed)),
        "batch": batch, "task_id": task_id, "stage": stage, "arm": arm,
        "config_id": config_id, "seed": int(seed),
        "budget_tier": tier, "budget": budget,
        "budget_override": {k: v for k, v in (override or {}).items() if v is not None},
        "image": image, "digest": digest, "timeout_s": int(timeout_s),
        "status": "pending", "attempts": 0, "run_id": None,
        "created_at": _now(), "started_at": None, "ended_at": None,
        "error": None, "note": note,
    }


def gen(matrix: dict, *, params: Path | str | None = None) -> list[dict]:
    """矩阵 → job 列表。**笛卡尔积的顺序是 task × arm × config × seed**（外到内）——
    同一道题的两臂挨在一起，于是「跑到一半停了」留下的是完整的题，不是半道题。
    """
    missing = [k for k in MATRIX_REQUIRED if k not in matrix]
    extra = [k for k in matrix if k not in MATRIX_REQUIRED + MATRIX_OPTIONAL]
    if missing or extra:
        raise JoblistError(f"矩阵的键集必须是 {list(MATRIX_REQUIRED)}（必填）"
                           f" + {list(MATRIX_OPTIONAL)}（可选）：缺 {missing}；多 {extra}")
    batch = str(matrix["batch"]).strip()
    if not batch:
        raise JoblistError("batch 不能为空")
    tasks = [str(t).strip() for t in matrix["tasks"] if str(t).strip()]
    configs = [str(c).strip() for c in matrix["configs"] if str(c).strip()]
    seeds = [int(s) for s in matrix["seeds"]]
    arms = check_arms(matrix["arms"])
    if not tasks or not configs or not seeds:
        raise JoblistError(f"tasks/configs/seeds 都不能是空的（{len(tasks)}/{len(configs)}/{len(seeds)}）")
    if any(s < 1 for s in seeds):
        raise JoblistError(f"seed 必须 ≥ 1（run_id 里是 r{seeds[0]:02d} 这种两位数）：{seeds}")
    if len(set(seeds)) != len(seeds):
        raise JoblistError(f"seeds 里有重复：{seeds}")
    for c in configs:
        REG.by_id(c)                                        # 未知 / enabled:false → RegistryError
    smap = stage_map(params)
    unknown = [t for t in tasks if t not in smap]
    if unknown:
        raise JoblistError(f"参数表里没有这些题：{unknown}")
    if len(set(tasks)) != len(tasks):
        raise JoblistError(f"tasks 里有重复：{tasks}")

    override = {k: matrix.get(k) for k in ("max_calls", "max_tokens")}
    jobs: list[dict] = []
    for t in tasks:
        for a in arms:
            for c in configs:
                for s in seeds:
                    jobs.append(make_job(batch, t, a, c, s, stage=smap[t],
                                         image=matrix.get("image"), digest=matrix.get("digest"),
                                         timeout_s=int(matrix.get("timeout_s") or 1500),
                                         override=override, note=str(matrix.get("note") or "")))
    ids = [j["job_id"] for j in jobs]
    if len(set(ids)) != len(ids):                            # 理论上到不了这里；到了就是判据漏了
        raise JoblistError(f"job_id 撞了：{sorted({i for i in ids if ids.count(i) > 1})}")
    return jobs


def load_matrix(path: Path | str) -> dict:
    import yaml
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise JoblistError(f"{path}: 矩阵顶层必须是映射")
    return raw


# ------------------------------------------------------------------ 读写

_PROC_LOCK = threading.Lock()


@contextlib.contextmanager
def _locked(path: Path):
    fh = open(path, "r+", encoding="utf-8")
    fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
    try:
        yield fh
    finally:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        fh.close()


def _line(job: dict) -> str:
    return json.dumps(job, ensure_ascii=False, sort_keys=True)


def save(path: Path | str, jobs: list[dict]) -> Path:
    """整份写盘。0600 / 0700（红线 5）。"""
    p = Path(path)
    RIO.secure_dir(p.parent)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text("".join(_line(j) + "\n" for j in jobs), encoding="utf-8")
    tmp.chmod(0o600)
    os.replace(tmp, p)
    p.chmod(0o600)
    return p


def load(path: Path | str) -> list[dict]:
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def check_transition(old: str, new: str, job_id: str = "") -> None:
    if new not in STATUSES:
        raise JoblistError(f"{job_id}: 未知状态 {new!r}（可选 {list(STATUSES)}）")
    if new not in TRANSITIONS[old]:
        raise JoblistError(
            f"{job_id}: 不合法的状态迁移 {old} → {new}。合法的是 {sorted(TRANSITIONS[old])}。"
            f"从终态回 pending 只有显式 retry / reset 一条路。")


def update(path: Path | str, job_id: str, **fields) -> dict:
    """改一行、整份重写（清单是几十行的东西，原地改字节换来的复杂度不值）。**线程安全 + 文件锁**。"""
    p = Path(path)
    with _PROC_LOCK, _locked(p) as fh:
        fh.seek(0)
        rows = [json.loads(x) for x in fh.read().splitlines() if x.strip()]
        hit = None
        for r in rows:
            if r["job_id"] != job_id:
                continue
            if "status" in fields:
                check_transition(r["status"], fields["status"], job_id)
            r.update(fields)
            hit = r
        if hit is None:
            raise JoblistError(f"清单里没有 job {job_id!r}")
        fh.seek(0)
        fh.truncate()
        fh.write("".join(_line(r) + "\n" for r in rows))
        fh.flush()
    p.chmod(0o600)
    return hit


def stat(jobs: Iterable[dict]) -> dict[str, int]:
    out = {s: 0 for s in STATUSES}
    for j in jobs:
        out[j["status"]] = out.get(j["status"], 0) + 1
    return out


def select(jobs: list[dict], *, resume: bool = False, retry_status: Iterable[str] = (),
           only_tasks: Iterable[str] = (), limit: int | None = None) -> tuple[list[dict], list[dict]]:
    """`(要跑的, 跳过的)`。

    * 终态一律不跑 —— `resume` 与否都一样。**`--resume` 不是「跳过 done」的开关**：
      跳过终态是常态，`resume` 只是允许清单里已经有终态行（不 resume 时清单里
      出现终态会被当成「你是不是想续跑」而提醒，但仍然跳过，不会重跑）。
    * `retry_status` 里的状态**先被重置成 pending**（调用方负责落盘）。
    """
    only = {str(t) for t in only_tasks if str(t).strip()}
    retry = {str(s) for s in retry_status}
    bad = retry - set(STATUSES)
    if bad:
        raise JoblistError(f"--retry-status 里有未知状态 {sorted(bad)}（可选 {list(STATUSES)}）")
    run, skip = [], []
    for j in jobs:
        if only and j["task_id"] not in only:
            skip.append(j)
            continue
        if j["status"] in retry and j["status"] in TERMINAL:
            run.append(j)
            continue
        if j["status"] in TERMINAL:
            skip.append(j)
            continue
        run.append(j)
    if limit is not None:
        skip.extend(run[limit:])
        run = run[:limit]
    return run, skip


# ------------------------------------------------------------------ CLI

def _csv(s: str | None) -> list[str]:
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="GeneBench 作业清单（卡 5.3）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("gen", help="生成 jobs.jsonl")
    g.add_argument("--matrix", default=None, help="ops/joblists/<name>.yaml")
    g.add_argument("--batch", default=None)
    g.add_argument("--configs", default=None)
    g.add_argument("--tasks", default=None)
    g.add_argument("--arms", default="strict,open")
    g.add_argument("--seeds", default="1")
    g.add_argument("--image", default=None)
    g.add_argument("--digest", default=None)
    g.add_argument("--timeout-s", type=int, default=1500)
    g.add_argument("--out", default=None, help="默认 $GENEBENCH_ROOT/runs_in/<batch>/jobs.jsonl")
    g.add_argument("--params", default=str(PARAMS))
    g.add_argument("--force", action="store_true", help="清单已存在时覆盖（**会丢掉已有状态**）")

    s = sub.add_parser("stat", help="状态计数")
    s.add_argument("path")

    l = sub.add_parser("list", help="逐行列出")
    l.add_argument("path")
    l.add_argument("--status", default=None)
    l.add_argument("--json", action="store_true")

    rb = sub.add_parser("rebudget", help="把**还没跑过**的行的预算档按当前 registry 重新物化")
    rb.add_argument("path")
    rb.add_argument("--dry", action="store_true", help="只报要改哪些行，不写")

    r = sub.add_parser("reset", help="把某些状态显式重置成 pending（**显式动作**）")
    r.add_argument("path")
    r.add_argument("--status", required=True, help="逗号分隔，例如 failed 或 failed,budget_exhausted")

    a = ap.parse_args(argv)

    if a.cmd == "gen":
        if a.matrix:
            m = load_matrix(a.matrix)
            if a.batch:
                m["batch"] = a.batch
        else:
            if not (a.batch and a.configs and a.tasks):
                raise SystemExit("不给 --matrix 就必须给 --batch / --configs / --tasks")
            m = {"name": a.batch, "batch": a.batch, "configs": _csv(a.configs),
                 "tasks": _csv(a.tasks), "arms": _csv(a.arms), "seeds": [int(x) for x in _csv(a.seeds)]}
            if a.image:
                m["image"] = a.image
            if a.digest:
                m["digest"] = a.digest
            m["timeout_s"] = a.timeout_s
        jobs = gen(m, params=a.params)
        out = Path(a.out) if a.out else jobs_path(m["batch"])
        if out.exists() and not a.force:
            raise SystemExit(f"{out} 已存在 —— 覆盖会丢掉已有状态。要覆盖加 --force；"
                             f"要续跑用 ops/run_joblist.py --jobs {out} --resume")
        save(out, jobs)
        print(f"{len(jobs)} 个 job → {out}")
        print(json.dumps(stat(jobs), ensure_ascii=False))
        return 0

    if a.cmd == "stat":
        print(json.dumps(stat(load(a.path)), ensure_ascii=False))
        return 0

    if a.cmd == "list":
        for j in load(a.path):
            if a.status and j["status"] != a.status:
                continue
            print(_line(j) if a.json else
                  f"{j['status']:<17} {j['job_id']:<52} {j['stage'] or '-':<3} "
                  f"{j['budget_tier']:<7} calls={j['budget']['max_calls']} "
                  f"tok={j['budget']['max_tokens']} run_id={j['run_id'] or '-'}")
        return 0

    if a.cmd == "rebudget":
        # **只动 `pending` 且没有 `run_id` 的行**：跑过的行里那个 `budget` 是遥测
        # （「这一行当时按哪档跑的」），改它等于伪造现场。还没跑过的行里它只是一个
        # 会过期的缓存 —— `RUN_BUDGET` 改过之后（N-388）它就与真跑档位对不上了，
        # 而 `--dry` 打印的正是它（红队 W.rt finding 2）。
        n, rows = 0, load(a.path)
        for j in rows:
            if j["status"] != "pending" or j.get("run_id"):
                continue
            tier, budget = budget_of(j.get("stage"), j.get("budget_override"))
            if (tier, budget) == (j.get("budget_tier"), j.get("budget")):
                continue
            print(f"  {j['job_id']}: {j.get('budget_tier')}/{j.get('budget')} → {tier}/{budget}")
            if not a.dry:
                update(a.path, j["job_id"], budget_tier=tier, budget=budget)
            n += 1
        print(f"{'要改' if a.dry else '已重新物化'} {n} 行（共 {len(rows)} 行）")
        return 0

    if a.cmd == "rebudget":
        # **只动 `pending` 且没有 `run_id` 的行**：跑过的行里那个 `budget` 是遥测
        # （「这一行当时按哪档跑的」），改它等于伪造现场。还没跑过的行里它只是一个
        # 会过期的缓存 —— `RUN_BUDGET` 改过之后（N-388）它就与真跑档位对不上了，
        # 而 `--dry` 打印的正是它（红队 W.rt finding 2）。
        n, rows = 0, load(a.path)
        for j in rows:
            if j["status"] != "pending" or j.get("run_id"):
                continue
            tier, budget = budget_of(j.get("stage"), j.get("budget_override"))
            if (tier, budget) == (j.get("budget_tier"), j.get("budget")):
                continue
            print(f"  {j['job_id']}: {j.get('budget_tier')}/{j.get('budget')} → {tier}/{budget}")
            if not a.dry:
                update(a.path, j["job_id"], budget_tier=tier, budget=budget)
            n += 1
        print(f"{'要改' if a.dry else '已重新物化'} {n} 行（共 {len(rows)} 行）")
        return 0

    if a.cmd == "reset":
        want = set(_csv(a.status))
        n = 0
        for j in load(a.path):
            if j["status"] in want:
                update(a.path, j["job_id"], status="pending", error=None, ended_at=None)
                n += 1
        print(f"重置 {n} 行 → pending")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
