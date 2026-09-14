# -*- coding: utf-8 -*-
"""NO_DATA 的**留痕**。

为什么必须留痕
--------------
新闻 / 财务 / 资金流在本环境里没有数据源。如果垫片只是抛一个异常就完事，
那么「被测系统尝试去拿新闻」这件事在数据面上**什么都没有** —— 而「什么都没有」
与「它根本没想过要新闻」不可区分。卡 5.1 的结算只认网关 `access_log`，
不采信 artifact 自报；所以这一次尝试必须在 access_log 里有一行。

怎么留的（**不改 `gateway/`**，2026-09-06 在生产网关上实测确认）
--------------------------------------------------------------
`gateway/app.py` 的 `_log_and_time` 是 **HTTP 中间件**，它在路由之前/之后各跑一段，
**未匹配到路由的请求同样经过它**。实测：

    GET /nodata/news?as_of=2026-06-30   → 404，响应带 x-genebench-ts
    $GB/logs/gateway_access.jsonl 里得到
    {"path": "/nodata/news", "params": {"as_of": "2026-06-30", "api": "..."},
     "decision": "deny", "reason": "unclassified", "status": 404, ...}

于是留痕**不需要网关加端点**：垫片打一个网关白名单之外的路径，中间件照记。
`params` 里带 `api=` 与 `kind=`，日志里就能看出是哪个兼容接口触发的。

**为什么不打 `/fundamentals`**：它是白名单里真实存在的端点，打它会得到 200
（私有通道下三大报表是可查的）—— 那等于把「题面没告诉 agent 它有」的数据递到手里
（N-58① 裁定：`/fundamentals` 不发放给 v1 的任何一道题）。留痕不能以泄题为代价。

本地兜底
--------
只有在**网关那一次探针本身失败**（连不上）时才写本地
`/task/log/client_nodata.jsonl`（或 `GENEBENCH_CLIENT_NODATA_LOG` 指定的路径）。
网关记得下时不写第二份 —— 两份记录必然漂，而漂的表现是「两边对不上，且都自称权威」。
"""
from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path
from typing import Any

from .errors import GenebenchClientError, NoData

#: 留痕路径的前缀。**刻意不在网关白名单里** —— 404 才是我们要的那条日志。
NODATA_PREFIX: str = "/nodata"

#: 粗分类。日志按它聚合（「这次运行一共尝试了几次新闻」）。
KINDS: tuple[str, ...] = (
    "news", "fundamentals", "moneyflow", "insider", "macro", "holders",
    "index_weight", "corporate_actions", "sentiment", "other")

#: 本地兜底日志。容器里 `/task/log/` 是 run dir 的一部分（P8 文件集封闭对它是宽的）。
LOCAL_LOG_ENV: str = "GENEBENCH_CLIENT_NODATA_LOG"
_DEFAULT_LOCAL_LOG = Path("/task/log/client_nodata.jsonl")


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="milliseconds")


def _local_log_path() -> Path | None:
    raw = (os.environ.get(LOCAL_LOG_ENV) or "").strip()
    if raw:
        return Path(raw)
    return _DEFAULT_LOCAL_LOG if _DEFAULT_LOCAL_LOG.parent.is_dir() else None


def _write_local(entry: dict[str, Any]) -> bool:
    """best-effort。写不成就算了 —— 留痕失败不许把一次 NO_DATA 变成一次崩溃。"""
    path = _local_log_path()
    if path is None:
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return True
    except OSError:
        return False


def trace(client, kind: str, api: str, **detail: Any) -> bool:
    """在网关 access_log 上留下这一次 NO_DATA。返回**是否留痕成功**。

    永远不抛：留痕是观测，观测失败不该改变被观测的行为。
    """
    k = kind if kind in KINDS else "other"
    params: dict[str, Any] = {"kind": k, "api": api}
    for key, val in detail.items():
        if val is None:
            continue
        params[key] = ",".join(map(str, val)) if isinstance(val, (list, tuple)) else str(val)
    try:
        params.setdefault("as_of", client._as_of(detail.get("as_of")))
    except GenebenchClientError:
        pass                       # as_of 拿不到照样留痕：那本身就是一条有信息的记录
    try:
        _, ts, _ = client.request("GET", f"{NODATA_PREFIX}/{k}", params=params,
                                  tolerate=(400, 402, 403, 404, 405, 422, 429))
        if ts:
            return True
    except GenebenchClientError:
        ts = None
    _write_local({"ts": _now(), "kind": k, "api": api,
                  "run_id": getattr(client, "run_id", ""),
                  "task_id": getattr(client, "task_id", ""),
                  "config_id": getattr(client, "config_id", ""),
                  "params": {k2: v for k2, v in params.items() if k2 not in ("kind", "api")},
                  "note": "网关留痕失败，这是本地兜底"})
    return False


def raise_no_data(client, kind: str, api: str, **detail: Any):
    """留痕**然后**抛 `NoData`。顺序不可换 —— 先抛就没有痕迹了。"""
    traced = trace(client, kind, api, **detail)
    raise NoData(kind, api, traced=traced,
                 detail={k: v for k, v in detail.items() if v is not None})
