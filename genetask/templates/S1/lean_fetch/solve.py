# oracle 参考解（数据面私有；在 f01 直跑，经网关 snapshot 后端产 artifact）。gold_token: <<gold_token>>
"""S1 oracle 公共骨架 —— 本文件由卡 3.2 按科目填；下方 TODO 是必须核对的接口细节，思路已定。

约定（卡 1.3 / 2.3）：
  * 网关 URL 由环境变量 GENEBENCH_GATEWAY_URL 给（f01 上是 http://192.168.1.48:18080；容器内是 http://gateway:18080）；
  * 每个请求带头 x-genebench-task-id=<task_id>、x-genebench-config-id=oracle（卡 3.1 §2.3：oracle 走真实网关，日志切片按 (task_id, config_id)）；
  * 每个请求必带 as_of=<task.as_of>；重复出现的标量参数（as_of/start_date/end_date/date/universe/…）会被网关 422，不要拼两次；
  * /bars 必须显式传 fields（缺省或 * = 读全表，会被 actual_reads 反推成超读）；
  * 声明字段从本目录 taskspec.json 读：declared 原样回填，underdetermined 的字段写显式 "unresolved"（不是 null、不是缺失）；
  * payload.fetches[i].fetched_at 必须等于网关日志里那条请求的 ts —— 用网关回包携带的时间戳，绝不用本地时钟；
  * status 映射：HTTP 200 且 rows>0 → ok；HTTP 200 且 rows==0 → empty；403（as-of 越界等 deny）→ denied；429 → rate_limited；
    被拒/限流时 rows 写 null，这次请求照样入台账（不许只留重试成功的那次）。
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

# 统一 I/O 契约（裁定 2026-09-05）：读标准位置的任务规格、经网关取数、写标准 artifact 路径。
# **不接受任何 stage 特定的 env/argv**。
from reference.oracle_io import context as _oracle_context
from reference.oracle_io import write as _oracle_write
CTX = _oracle_context(__file__)
HERE = CTX.task_dir
GATEWAY = CTX.gateway
CONFIG_ID = "oracle"
SCHEMA_VERSION = "1.0"


def load_task() -> tuple[dict, dict]:
    """规格已由统一契约读好 —— 这里只是保留旧名字，不再重复读文件。"""
    return CTX.task, CTX.spec


def declarations(spec: dict) -> dict:
    d = dict(spec["declared"])
    for f in spec["underdetermined"]:
        d[f] = "unresolved"
    return d


def gw_get(path: str, params: dict, task_id: str) -> dict:
    """一次网关请求 → 一条 fetches 记录。返回 {"record": {...}, "data": [...]}。"""
    import requests                                       # 只在 f01 的 env 里有；容器内不需要本文件
    r = requests.get(GATEWAY + path, params=params,
                     headers={"x-genebench-task-id": task_id, "x-genebench-config-id": CONFIG_ID}, timeout=60)
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    # 网关在**每个**响应上回显这次请求在 access_log 里的那条 ts（`gateway/app.py::TS_HEADER`）。
    # **绝不用本地时钟，也不去读日志自己填** —— 后者会让被核的值与核它的基准同源，
    # 交叉核就成了恒真。缺头就让它是 None，由校验器判 malformed，不许猜一个。
    fetched_at = r.headers.get("x-genebench-ts")
    if r.status_code == 200:
        # 行数的字段名逐端点不同（实测）：/bars、/adj 给 `rows`+`data`；
        # /universe 给 `size`+`members`。取不到就按实际拿到的列表长度算，
        # **不默认 0** —— 0 会被判成 empty，而 empty 与「我不认识这个回包」是两回事。
        rows = body.get("rows", body.get("size"))
        if rows is None:
            rows = len(body.get("data") or body.get("members") or [])
        rows = int(rows)
        status = "ok" if rows > 0 else "empty"
    elif r.status_code == 429:
        status, rows = "rate_limited", None
    else:
        status, rows = "denied", None
    rec = {"endpoint": path, "params": dict(params), "fetched_at": fetched_at, "status": status, "rows": rows}
    return {"record": rec, "data": body.get("data") or [],
            "members": body.get("members") or [], "fields": body.get("fields") or []}


def universe_codes(task: dict, task_id: str, fetches: list) -> list[str]:
    """成分列表：`GET /universe?as_of=&universe=&date=`（参数名与回包形状 2026-09-05 实测）。

    回包是 `{"size": 300, "members": ["000001.SZ", ...]}` —— **成员是字符串列表**，
    不是 `data` 里的 dict 行。照 `data`/`code` 取会拿到空列表，
    而空列表会让整道题「一次 bars 都没取」却仍然产出 artifact。
    """
    p = {"as_of": task["as_of"], "universe": task["universe"], "date": task["window"]["end"]}
    res = gw_get("/universe", p, task_id)
    fetches.append(res["record"])
    codes = list(res["members"])
    if not codes:
        raise SystemExit(f"/universe 没给出成分（rows={res['record']['rows']}）—— "
                         f"取不到成分就不该产出 artifact，那会是一份看起来合法的空壳")
    return codes


def envelope(task: dict, spec: dict, payload: dict) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": f"{task['task_id']}-oracle",
        "stage": "S1", "task_id": task["task_id"], "config_id": CONFIG_ID, "arm": "strict", "seed": 0,
        "as_of": task["as_of"], "produced_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "provenance": [], "declarations": declarations(spec), "payload": payload,
    }


REQUIRED = ["close"]                                     # 科目 S1-ECO-01：actual_reads(log) == {close} 且 len(fetches) ≤ n_codes + 1


def main() -> None:
    task, spec = load_task()
    tid, w = task["task_id"], task["window"]
    fetches: list[dict] = []
    codes = universe_codes(task, tid, fetches)             # 恰 1 次 /universe
    # TODO 核对 /bars 是否接受批量 code（逗号列表或 universe 参数）。若接受，预算改为 ≤ 2 条，scorer 的预算常数同步改；
    #      若不接受，逐标的 1 次、整窗一次、fields=close —— 这就是预算 n_codes + 1 的来源。
    seen: set[str] = set()
    for code in codes:
        if code in seen:
            continue                                       # 同标的同窗不重复
        seen.add(code)
        p = {"as_of": task["as_of"], "code": code, "start_date": w["start"], "end_date": w["end"], "fields": "close"}
        fetches.append(gw_get("/bars", p, tid)["record"])
    payload = {"fetches": fetches, "fields_obtained": ["close"]}
    art = envelope(task, spec, payload)
    out = _oracle_write(CTX, art)          # 标准路径 + 0600（红线 5）
    assert len(fetches) <= len(codes) + 1
    # O1 自检：reference.artifact_schema.actual_reads(<access_log 切片>) == {"close"}
    print("wrote", out, "fetches", len(fetches), "budget", len(codes) + 1)


if __name__ == "__main__":
    main()
