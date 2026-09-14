#!/usr/bin/env python3
"""网关串行闸：**跑批与 agent 真跑不许同时打网关**（裁定 2026-09-05，N-125）。

为什么要一把锁而不是「注意一下」：网关是**单 worker**（取证完整性要求 —— `access_log` 用进程内锁，
多 worker 会交错写坏行，而前视探针靠这份日志结算）。于是两批负载叠上来的后果是复合的：

* 延迟从 0.15 s 涨到 1.2 s，oracle 的 `/bars` 撞 60 s 读超时（今晚 4 道题这么挂的）；
* RSS 一路涨到系统 OOM，网关被杀（今晚 9 道 oracle + 2 个 M6 run 被打坏）；
* `access_log` 里两批的条目**交错**，而三维切片只按 (task_id, config_id, 时间窗) 切 ——
  同一个 task_id 被两批同时跑时，时间窗也分不开。

锁是**文件锁**（`fcntl.flock`），落在 `$GENEBENCH_ROOT/locks/gateway.lock`。谁要打网关谁拿：
数据面的 `ops/run_oracles.py` 直接用；执行面的真跑从 f01 这一侧起，用 CLI 包一层：

    python ops/gateway_lock.py -- ssh ljn@192.168.1.219 "python3 exec/ops/run_f02_a1.py …"

拿不到就**等**（默认无限等，每 30 s 报一次谁占着）。`--nowait` 则直接退 2。
锁文件里写着持有者（pid / 主机 / 命令 / 起始时刻），等的人能看见在等谁。
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import genebench_config as cfg                              # noqa: E402

#: 锁文件的显式覆盖。**同一台机器上跑两套 `GENEBENCH_ROOT`、却共用同一个网关实例**时用它，
#: 把两边指到同一个文件 —— 见下面 `lock_path()` 的互斥语义那一段。
LOCK_ENV = "GENEBENCH_GATEWAY_LOCK"


def lock_path() -> Path:
    """锁文件。**根从 `cfg.GENEBENCH_ROOT` 现算**（N-838，用户裁定 ②，2026-09-14）。

    以前这里写死 `/data/shared/genebench/locks/gateway.lock`，而真跑**每个 job**
    都进这个上下文（`ops/run_joblist.py::run_one`）—— 于是在一台造不出 `/data` 的机器上
    （macOS 根卷只读），整条真跑路径第一步就死。

    **换根之后互斥还成不成立**（这一条比改常量本身重要）：

    * **同一台机器、同一个 `GENEBENCH_ROOT`** → 同一个锁文件 → `flock` 照旧互斥。
      红线 B6 要的「跑批与真跑串行」在一套部署内部完全成立
      （`ops/test_A9.py` 真起两个进程量过）。
    * **不同 `GENEBENCH_ROOT`** → 不同锁文件 → **互不干扰**。那是两套独立部署，
      本来就该各锁各的。
    * **例外，说清楚**：`GATEWAY_HOST` / `GATEWAY_PORT` 不派生自 `GENEBENCH_ROOT`，
      所以同机两套根**有可能打同一个网关实例**——那一种情形下互斥会丢。
      给它留的口子就是 `GENEBENCH_GATEWAY_LOCK`：两边指同一个文件即可。
      发布方那台不存在这种情形（只有一套根）。

    发布方那台的取值**逐字不变**：`GENEBENCH_ROOT` 不设 →
    `cfg.GENEBENCH_ROOT` 就是 `_DEFAULT_ROOT`，拼出来与改动前同一个字符串。
    """
    v = (os.environ.get(LOCK_ENV) or "").strip()
    return Path(v) if v else cfg.GENEBENCH_ROOT / "locks" / "gateway.lock"


#: 兼容既有 `from ops.gateway_lock import LOCK` 的调用方。**取值在 import 那一刻定**；
#: 进程内改环境变量之后要用 `lock_path()`。
LOCK = lock_path()


def _holder(fh) -> str:
    try:
        fh.seek(0)
        return fh.read(400).strip() or "（未知）"
    except OSError:
        return "（读不到）"


@contextlib.contextmanager
def gateway_lock(what: str, *, wait: bool = True, poll: float = 5.0):
    """独占网关。`what` 写进锁文件，等的人能看见在等谁。"""
    lock = lock_path()
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(lock.parent, 0o700)
    except OSError:
        pass
    fh = open(lock, "a+", encoding="utf-8")
    t0 = time.time()
    said = False
    while True:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if not wait:
                fh.close()
                raise SystemExit(f"网关被占着：{_holder(fh)}（--nowait）")
            if not said or (time.time() - t0) % 30 < poll:
                print(f"等网关锁 {lock}（{int(time.time() - t0)}s）：当前 {_holder(fh)}",
                      file=sys.stderr)
                said = True
            time.sleep(poll)
    try:
        fh.seek(0)
        fh.truncate()
        fh.write(json.dumps({"pid": os.getpid(), "host": socket.gethostname(), "what": what,
                             "since": datetime.now(timezone.utc).isoformat(timespec="seconds")},
                            ensure_ascii=False))
        fh.flush()
        os.chmod(lock, 0o600)
        yield
    finally:
        try:
            fh.seek(0)
            fh.truncate()
            fh.flush()
        except OSError:
            pass
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        fh.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="拿着网关锁跑一条命令")
    ap.add_argument("--what", default="", help="占用说明（默认取命令本身）")
    ap.add_argument("--nowait", action="store_true")
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    a = ap.parse_args(argv)
    cmd = [c for c in a.cmd if c != "--"]
    if not cmd:
        # 不带命令 = 查状态
        lock = lock_path()
        print(f"锁文件：{lock}")
        fh = open(lock, "a+", encoding="utf-8") if lock.exists() else None
        if fh is None:
            print("锁文件不存在 —— 没人占")
            return 0
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            print("空闲")
        except BlockingIOError:
            print(f"占用中：{_holder(fh)}")
        finally:
            fh.close()
        return 0
    with gateway_lock(a.what or " ".join(cmd)[:200], wait=not a.nowait):
        return subprocess.run(cmd).returncode


if __name__ == "__main__":
    raise SystemExit(main())
