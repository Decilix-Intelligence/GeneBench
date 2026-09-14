"""卡 4.1/4.3 的**正式 run 循环**：一次运行从注入到收产物的完整路径。

    inject → verify_run_dir_unchanged → compose up → wait → harvest → verify(产出物)

**为什么它必须是正式代码**（裁定 2026-09-04）：在此之前这条循环只存在于
测试脚本与手工命令里 —— 于是「起容器前复核」这道门没有调用点（`verify_run_dir_unchanged`
写好了却没人调），而 T5/T10 的探针脚本正是在注入之后被写进 `work/` 的，
**P8 一个字都没说**。门有了、门后没人，这个形态本轮已经出现三次。

跑在 f02（执行面）：**零 `reference/` 依赖**，与 `runner/inject.py` 同一条纪律。

4.2 的采集器往 `harvest` 这一步接：`RunResult.work_dir` 与 `RunResult.log_dir`
是它的输入；退出后那次复核的允许集**由采集器定义**（`c42.harvest.produced_allowlist`），
本模块不再自带占位清单。
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from genetask.bundle import PackError
from runner import inject as INJ
from runner.c42 import harvest as HV

#: 起容器**前**那次复核的允许集是**空**的（P8 之后到 up 之前零变化）；
#: 容器**退出后**那次的允许集来自卡 4.2 的 `harvest.produced_allowlist(stage, arm)`
#: —— **让定义产出物的人定义允许集**（裁定 2026-09-04）。占位常量已收掉：
#: 留一份手抄清单在这里，采集器改了产出物它不会跟着改，而漂开的方向是**放行**。

#: 起容器前那次复核的允许集 —— **空**。
NOTHING_ALLOWED: tuple[str, ...] = ()


class RunError(RuntimeError):
    """循环中止。**不吞** —— 每一步失败都要带着它自己的名字冒出来。"""


@dataclass
class RunResult:
    run_id: str
    run_dir: Path
    arm: str
    config_id: str
    exit_code: int
    started_at: str
    finished_at: str
    elapsed_s: float
    stdout_tail: str = ""
    stderr_tail: str = ""
    new_files: dict[str, str] = field(default_factory=dict)
    unexpected: list[str] = field(default_factory=list)

    @property
    def work_dir(self) -> Path:
        return self.run_dir / "work"

    @property
    def log_dir(self) -> Path:
        return self.run_dir / "log"


def _sh(*args: str, timeout: int | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def _allowed(rel: str, allow: tuple[str, ...]) -> bool:
    return any(rel == a or (a.endswith("/") and rel.startswith(a)) for a in allow)


def verify_unchanged(run_dir: Path, *, allow: tuple[str, ...],
                     stage: str) -> list[str]:
    """`INJ.verify_run_dir_unchanged` 的带允许集版本。

    允许集是**加法**：清单之外的新增一律红。
    「注入后被改 / 被删」在任何阶段都不许 —— 允许集只放行**新增**。
    """
    bad: list[str] = []
    for line in INJ.verify_run_dir_unchanged(run_dir):
        if line.startswith("注入后被加："):
            rel = line.split("：", 1)[1].split(" ——")[0].strip()
            if _allowed(rel, allow):
                continue
        bad.append(f"[{stage}] {line}")
    return bad


def run_once(bundle_dir, arm: str, *, run_root, provider_root, config_id: str,
             manifest: dict, expect_frozen_root: str, command: str,
             seq: int = 1, timeout_s: int = 1800,
             keep_containers: bool = False) -> RunResult:
    """一次完整运行。任一步失败即 `RunError`，**不降级、不继续**。"""
    run_dir = None
    try:
        inj = INJ.inject(bundle_dir, arm, run_root=run_root, provider_root=provider_root,
                         config_id=config_id, manifest=manifest,
                         expect_frozen_root=expect_frozen_root, command=command, seq=seq)
    except PackError as e:
        raise RunError(f"注入失败：{e}") from e
    run_dir = inj.run_dir

    # ---- 起容器**之前**：P8 之后到 up 之间零变化 ----
    # 这道门在此之前没有调用点 —— 而 T5/T10 的探针脚本正是从这个窗口进去的。
    bad = verify_unchanged(run_dir, allow=NOTHING_ALLOWED, stage="up 之前")
    if bad:
        raise RunError("起容器前复核未过（P8 之后有人动过 run dir）：\n  " + "\n  ".join(bad))

    cf = run_dir / "compose.yml"
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    t0 = time.time()
    up = _sh("docker", "compose", "-f", str(cf), "up", "-d", "gateway", timeout=120)
    if up.returncode != 0:
        raise RunError(f"边车起不来：{up.stderr[-400:]}")
    time.sleep(2)
    try:
        r = _sh("docker", "compose", "-f", str(cf), "run", "--rm", "task",
                timeout=timeout_s)
        rc, out, err = r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        # 超时**不是**失败 —— 它是一个可结算的结果（agent 没做完）。
        # 但容器必须收掉，否则下一个 run 会撞上残留。
        rc, out, err = 124, "", f"超时（{timeout_s}s）"
    finally:
        if not keep_containers:
            _sh("docker", "compose", "-f", str(cf), "down", "-v", timeout=120)
    elapsed = time.time() - t0
    finished = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # ---- 容器退出**之后**：新增必须落在产出物清单里 ----
    allow = HV.produced_allowlist(manifest["stage"], arm)
    after = verify_unchanged(run_dir, allow=allow, stage="退出之后")
    new_files = _new_since_injection(run_dir)

    res = RunResult(run_id=inj.run_id, run_dir=run_dir, arm=arm, config_id=config_id,
                    exit_code=rc, started_at=started, finished_at=finished,
                    elapsed_s=round(elapsed, 3),
                    stdout_tail=(out or "")[-2000:], stderr_tail=(err or "")[-2000:],
                    new_files=new_files, unexpected=after)
    _write_run_json(res)
    return res


def _new_since_injection(run_dir: Path) -> dict[str, str]:
    """容器跑完之后**新增**的文件（相对 inject.json 记的那份清单）。"""
    inj = json.loads((run_dir / "inject.json").read_text(encoding="utf-8"))
    known = set(inj.get("files") or {}) | {"inject.json", "run.json"}
    out: dict[str, str] = {}
    for p in sorted(run_dir.rglob("*")):
        if not p.is_file():
            continue
        rel = str(p.relative_to(run_dir))
        if rel not in known:
            out[rel] = INJ._sha_file(p)
    return out


def _write_run_json(res: RunResult) -> None:
    """一次运行的**运行侧**记录。与 inject.json 分开：
    那份记「注入了什么」，这份记「跑出了什么」——两件事不该混在一个文件里。"""
    payload = {
        "run_id": res.run_id, "arm": res.arm, "config_id": res.config_id,
        "exit_code": res.exit_code, "started_at": res.started_at,
        "finished_at": res.finished_at, "elapsed_s": res.elapsed_s,
        "new_files": res.new_files, "unexpected": res.unexpected,
        "stdout_tail": res.stdout_tail, "stderr_tail": res.stderr_tail,
    }
    (res.run_dir / "run.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
