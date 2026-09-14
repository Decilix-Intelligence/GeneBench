# -*- coding: utf-8 -*-
"""访问日志 —— 卡 5.1 前视探针**事后结算的唯一依据**。

落 ``$GENEBENCH_ROOT/logs/gateway_access.jsonl``（**不落 repo**），一行一 JSON。

字段宁多勿少：探针要能从日志单独回答"这个 task 在这个 config 下，
有没有请求过 as_of 之后的数据、被拦了没有"。所以**请求全文**（含全部
查询参数）要落，不能只落路径。
"""
from __future__ import annotations

import datetime as dt
import json
import os
import threading
from pathlib import Path
from typing import Any

import genebench_config as cfg

#: 日志文件。用 cfg.LOGS 派生，T-01 搬家时跟着走。
#:
#: **按通道分文件**（卡 1.1-a）：private = `gateway_access.jsonl`（与既有逐字节同名），
#: public = `gateway_access_public.jsonl`。两条通道混写一份的话，
#: 卡 5.1 的越权率就分不清是哪条通道产生的。
#: 取值在 **import 期**定下来 —— 通道由进程启动前的环境变量决定，进程内不会变；
#: 测试仍然照旧 monkeypatch 这个名字。
ACCESS_LOG: Path = cfg.gateway_access_log()

#: 多 worker 下的写锁。单进程 uvicorn 够用；将来上多 worker 要换成
#: 每 worker 一个文件或走 syslog —— 已在 README 注明，不要静默改成追加无锁。
_LOCK = threading.Lock()

#: 落日志时要抹掉的参数名（当前为空 —— 网关不接受任何凭据类参数）。
#: 留这个钩子是因为将来若加了 token，绝不能让它进日志。
REDACT_KEYS: frozenset[str] = frozenset()


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


def ensure_log_dir() -> Path:
    cfg.create_dir(cfg.LOGS)
    return ACCESS_LOG


def record(
    *,
    method: str,
    path: str,
    params: dict[str, Any],
    as_of: str | None,
    decision: str,
    status: int,
    reason: str | None = None,
    backend: str | None = None,
    rows: int | None = None,
    config_id: str | None = None,
    task_id: str | None = None,
    #: ID-4（卡 4.3 §6.5）：**加法**，默认 None，不动既有列与既有字段序。
    #: 切片键退化为 run_id —— 它蕴含臂、配置与第几次重跑，两臂并发同 config 也不串。
    run_id: str | None = None,
    arm: str | None = None,
    elapsed_ms: float | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """写一行。返回写出去的那个 dict（便于测试直接断言）。

    Args:
        decision: ``allow`` 或 ``deny``。
        reason: `errors.Reason` 的值；allow 时为 None。
    """
    safe = {k: v for k, v in params.items() if k not in REDACT_KEYS}
    entry: dict[str, Any] = {
        "ts": _now(),
        "config_id": config_id,
        "task_id": task_id,
        "run_id": run_id,
        "arm": arm,
        "method": method,
        "path": path,
        "params": safe,
        "as_of": as_of,
        "decision": decision,
        "reason": reason,
        "status": status,
        "backend": backend,
        "rows": rows,
        "elapsed_ms": elapsed_ms,
        "freeze_line": cfg.FREEZE_DATE,
        "pid": os.getpid(),
    }
    if extra:
        entry["extra"] = extra
    line = json.dumps(entry, ensure_ascii=False, sort_keys=False)
    target = ensure_log_dir()
    with _LOCK:
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        try:
            os.chmod(target, 0o600)
        except OSError:
            pass
    return entry


def read_all(path: Path | None = None) -> list[dict[str, Any]]:
    """读回全部记录（测试用）。文件不存在返回空列表。"""
    target = path or ACCESS_LOG
    if not target.exists():
        return []
    out: list[dict[str, Any]] = []
    for raw in target.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if raw:
            out.append(json.loads(raw))
    return out


def tail(n: int = 1, path: Path | None = None) -> list[dict[str, Any]]:
    return read_all(path)[-n:]
