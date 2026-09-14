# oracle 参考解（数据面私有；在 f01 直跑，经网关 snapshot 后端产 artifact）。gold_token: <<gold_token>>
"""S6 组合构建 oracle —— ROB-01：欠定语义探针（rebalance_frequency 未声明 → declarations 标 unresolved，不补默认）

网关端点（GATEWAY=http://gateway:18080，snapshot 后端，请求头带 x-genebench-task-id / x-genebench-config-id）：
  /calendar?as_of&start_date&end_date              → is_open：窗口内的交易日序列（调仓日只能从这里取）
  /bars?as_of&code&start_date&end_date&fields=close → reference_close（显式 fields=close，与 2.3-c 读取集探针一致）
  /universe?as_of&date                              → csi300 成分（校验信号里的 symbol 都在宇宙内；不在的不入选）
信号来源：inputs[0]（work/signal_<id>.parquet，列 date/symbol/value；value ∈ 数 / null / "flat"），
  parquet metadata 里有上游 S5 的 artifact_id —— 写进 provenance。oracle 在 f01 直接读 reference/signals/<id>/slice.parquet。

产出 S6 artifact 各字段的来源：
  declarations              ← taskspec.declared 原样回填（欠定字段写 "unresolved"，绝不补默认值）
  payload.targets[].date    ← 调仓日（按 rebalance_frequency 从 /calendar 的交易日里取，见 rebalance_days）
  payload.targets[].solver_status ← 求解结果（optimal / infeasible / not_converged）
  payload.targets[].positions[]   ← 台账六字段：
      symbol           信号文件里的写法原样
      score            该调仓日信号值
      previous_weight  上一调仓日 target_weight（首日 0）
      target_weight    本日求解结果
      delta_weight     target − previous
      reference_close  /bars fields=close 该日 close
  payload.cash_ratio        ← null（N-26 留位）
  provenance                ← [{"stage": "S5", "artifact_id": <信号 metadata>}]
"""
from __future__ import annotations

import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from reference.gateway_client import iso_date as _iso_date
import requests

# 统一 I/O 契约（裁定 2026-09-05）：读标准位置的任务规格、经网关取数、写标准 artifact 路径。
# **不接受任何 stage 特定的 env/argv** —— 从任务目录读得出来的东西，一律不从环境拿。
# 协议的**显式欠定标记**（`artifact_schema.UNRESOLVED` = "unresolved"）。
# 不在这里重抄那个字面串：抄第二份，哪天协议换了标记，这五份 gold 会安静地继续用旧的。
from reference.artifact_schema import UNRESOLVED as _UNRESOLVED
from reference.oracle_io import context as _oracle_context
from reference.oracle_io import write as _oracle_write
from reference.oracle_io import write_private as _write_private
CTX = _oracle_context(__file__)
GATEWAY, TASK_DIR = CTX.gateway, CTX.task_dir
ARTIFACT_PATH = CTX.out
W_TOL = 1e-9


# ---------------------------------------------------------------- 网关

def _get(path: str, **params) -> list[dict]:
    task = yaml_task()
    h = {"x-genebench-task-id": task["task_id"], "x-genebench-config-id": "oracle"}
    r = requests.get(GATEWAY + path, params=params, headers=h, timeout=60)
    r.raise_for_status()
    return r.json()["data"]


def yaml_task() -> dict:
    import yaml
    return yaml.safe_load((TASK_DIR / "task.yaml").read_text(encoding="utf-8"))


def trading_days(as_of: str, start: str, end: str) -> list[str]:
    rows = _get("/calendar", as_of=as_of, start_date=start, end_date=end)
    # 网关 `/calendar` 的日期列是 `cal_date`（`YYYYMMDD`，2026-09-05 实测；S2 模板同样记过）；
    # 信号夹具与题面窗口都是 ISO —— 这里统一成 ISO，别让两种写法在 key(d) 里相遇。
    return sorted(_iso_date(r["cal_date"]) for r in rows if r.get("is_open"))


_CLOSE: dict[str, dict[str, float | None]] = {}
_WINDOW: dict | None = None


def close_on(as_of: str, code: str, date: str) -> float:
    """该标的在 `date` 的 close。**按标的一次拉整窗再查表**：网关单次 `/bars` ≈ 1.2 s（2026-09-05 实测），
    逐 (标的, 日) 取会让一道题打 6 000+ 次、跑两小时以上。同一端点、同一 as_of、同一字段，
    整窗切片里那一天的值与单日请求的值相同 —— 数值不变，只是少打网关。"""
    global _WINDOW
    if code not in _CLOSE:
        if _WINDOW is None:
            _WINDOW = yaml_task()["window"]
        rows = _get("/bars", as_of=as_of, code=code, start_date=_WINDOW["start"], end_date=_WINDOW["end"],
                    fields="close")
        table: dict[str, float | None] = {}
        for r in rows:
            d = str(r.get("date") or r.get("trade_date") or "")
            if len(d) == 8 and d.isdigit():
                d = f"{d[:4]}-{d[4:6]}-{d[6:]}"
            table[d] = r.get("close")
        _CLOSE[code] = table
    c = _CLOSE[code].get(date)
    if c is None:
        raise RuntimeError(f"{code} 在 {date} 无 close —— 入选前应已按信号 null 过滤，这里不该到")
    return float(c)


def _close_on_single_day(as_of: str, code: str, date: str) -> float:
    rows = _get("/bars", as_of=as_of, code=code, start_date=date, end_date=date, fields="close")
    if not rows or rows[0].get("close") is None:
        raise RuntimeError(f"{code} 在 {date} 无 close —— 入选前应已按信号 null 过滤，这里不该到")
    return float(rows[0]["close"])


def rebalance_days(freq: str, days: list[str]) -> list[str]:
    """daily = 每个交易日；weekly = 每个 ISO 周的最后一个交易日；monthly = 每月最后一个交易日（与 phrasebook 措辞一致）。"""
    if freq == "daily":
        return list(days)
    key = (lambda d: datetime.fromisoformat(d).isocalendar()[:2]) if freq == "weekly" else (lambda d: d[:7])
    out, last = [], {}
    for d in days:
        last[key(d)] = d
    return sorted(last.values())


# ---------------------------------------------------------------- 信号

def load_signal(task: dict) -> tuple[pd.DataFrame, str]:
    """返回 (df[date, symbol, value], 上游 artifact_id)。oracle 在 f01 读 reference/ 的切片；容器内 agent 读 work/。"""
    inp = task["inputs"][0]
    p = Path(inp["origin"]) if Path(inp["origin"]).exists() else TASK_DIR / inp["path"]
    import pyarrow.parquet as pq
    t = pq.read_table(p)
    meta = {k.decode(): v.decode() for k, v in (t.schema.metadata or {}).items()}
    df = t.to_pandas()
    # 上游信号 parquet 的 schema metadata 里**没有** `artifact_id` 时的兜底值。
    #
    # 病灶（N-543，用户裁定 ② 走 A，2026-09-10）：原兜底值是字面串
    # `"TODO:signal-artifact-id-missing"` —— 一个**看起来像值的非值**。协议只要求
    # `artifact_id` 是非空串（`artifact_schema` 的 `provenance_ref_malformed` 就查这个），
    # 于是这个 TODO 串一路通过校验，进了五份 S6 gold，又随 `broken.json` 进了适配赛道四例
    # （`adapt-l1-08` / `l2-07` / `l2-08` / `l3-06`）。适配臂的 INSTRUCTION 规则 1 要求
    # 「源里没有的写成显式 unresolved」—— 被测方照做，oracle 却要求原样抄回那个 TODO 串，
    # `scorer/adaptation.py::match_oracle` 于是在 `provenance` 上判不一致。
    # **被罚的正是照规则做的那一方**，已发表的适配表因此偏低约 13 个百分点。
    #
    # 为什么改这里而不是在 `match_oracle` 里把两者判等价：后者是**判据变更**，
    # 而且等于再掩盖一次「协议本来就有一个显式欠定标记」这件事。这里修的是根因。
    # 本文件的模块 docstring 早就写着「欠定字段写 "unresolved"，绝不补默认值」——
    # provenance 这一处只是没跟上。
    return df, meta.get("artifact_id", _UNRESOLVED)


def eligible(sig_day: pd.DataFrame) -> dict[str, float]:
    """null（无观点）与 "flat"（主动空仓）都不可入选；返回 symbol → score。"""
    out = {}
    for r in sig_day.itertuples(index=False):
        v = r.value
        if v is None or v == "flat" or (isinstance(v, float) and math.isnan(v)):
            continue
        out[r.symbol] = float(v)
    return out


def n_names(constraints: dict) -> int:
    """等权 + max_weight 上限 + 最大化总分 ⇒ 持有 floor(1/max_weight) 只，各 max_weight。"""
    return int(math.floor(1.0 / constraints["max_weight"] + 1e-9))


# ---------------------------------------------------------------- 求解（各模板不同）

def solve_day(scores: dict[str, float], prev: dict[str, float], constraints: dict) -> tuple[str, dict[str, float]]:
    n = n_names(constraints)
    top = sorted(scores, key=lambda s: (-scores[s], s))[:n]
    return "optimal", {s: constraints["max_weight"] for s in top}


def solve_all(days, sig, declared, under, as_of) -> None:
    """探针题的诚实解 = **诚实终止**：依赖未声明口径的量算不出来，出 null，不出 0，也不私下挑一个取值。

    2026-09-07 裁定（N-103 的证据落地时一并了结那句 TODO）：原先出「窗口首个交易日建仓」这一条，
    理由是「任何节奏下首日都要建仓且解相同」。**判据不这么看** ——
    `reference/artifact_schema.PAYLOAD_DEPENDS_ON["S6"]["targets"]` 里就写着 `rebalance_frequency`，
    于是校验器对这份产物判 `computed_despite_unresolved`（真跑实测，2026-09-07）：
    「targets 依赖的口径被标了 unresolved，却把数算出来了 —— 等于私下挑了一个取值」。
    而本题的实测证据（`DIVERGENCE_EVIDENCE` 里那条：三份冻结独立实现逐可行值各跑一遍，
    私有 79 处 / 公开 81 处指标超 daily 档 ε 带）正是「三种节奏**不**数值等价」的直接证明 ——
    首日相同也不足以让 `targets` 这个**整体**变得与节奏无关。改法与 S7 `rob_underdetermined` 同形（N-93）。

    返回 `None`：调用方据此把 `payload.targets` 置空。`days` / `sig` / `declared` / `as_of`
    保留在签名里 —— 它们是「本来要拿来算」的输入，删掉会让下一个人以为这道题不需要它们。
    """
    if "rebalance_frequency" not in under:
        raise SystemExit("本模板专供探针题；规定题请用 cor_ledger")
    return None


# ---------------------------------------------------------------- 组装

def ledger(day: str, as_of: str, scores: dict[str, float], prev: dict[str, float],
           target: dict[str, float]) -> list[dict]:
    rows = []
    for sym in sorted(set(prev) | set(target)):
        p, t = prev.get(sym, 0.0), target.get(sym, 0.0)
        if abs(p) < W_TOL and abs(t) < W_TOL:
            continue
        rows.append({"symbol": sym, "score": scores.get(sym, 0.0),
                     "previous_weight": p, "target_weight": t, "delta_weight": t - p,
                     "reference_close": close_on(as_of, sym, day)})
    return rows


def main() -> None:
    task = yaml_task()
    spec = json.loads((TASK_DIR / "taskspec.json").read_text(encoding="utf-8")) if (TASK_DIR / "taskspec.json").exists() else task
    declared, under = spec["declared"], spec.get("underdetermined") or []
    decl_out = {**declared, **{f: "unresolved" for f in under}}
    as_of, w = task["as_of"], task["window"]
    sig, upstream = load_signal(task)
    days = trading_days(as_of, w["start"], w["end"])
    targets = solve_all(days, sig, declared, under, as_of)
    # 诚实终止：**被依赖的那几个叶子**才置空，不依赖的照常出（`honest_halt_fields` 逐叶子判）。
    from reference import artifact_schema as _sch
    halted = sorted(_sch.honest_halt_fields("S6", decl_out, list(under)))
    art = {
        "schema_version": "1.0", "artifact_id": f"{task['task_id']}-oracle", "stage": "S6",
        "task_id": task["task_id"], "config_id": "oracle", "arm": "strict",
        "seed": 0, "as_of": as_of, "produced_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provenance": [{"stage": "S5", "artifact_id": upstream}],
        "declarations": decl_out,
        "payload": {**{k: None for k in halted}, "targets": targets, "cash_ratio": None},
    }
    ts = {k: task[k] for k in ("task_id", "stage", "declared", "underdetermined")}
    v = _sch.validate(art, task=ts)
    assert v.ok, [str(x) for x in v.findings]                     # ⑨' (1) 诚实终止本身必须干净
    import copy as _copy
    mut = _copy.deepcopy(art)
    mut["declarations"]["rebalance_frequency"] = "daily"          # ⑨' (2) 换成一个具体取值
    assert "silent_completion" in _sch.validate(mut, task=ts).codes, \
        "校验器对静默补全不响 —— 空探针"
    (TASK_DIR / "gold").mkdir(parents=True, exist_ok=True)
    _write_private(TASK_DIR / "gold" / "underdetermined_note.json",
                   {"field": "rebalance_frequency", "engine_value": None,
                    "halted_payload_fields": halted,
                    "why_no_equivalence":
                        "rebalance_frequency 的三个可行值在 weighting_scheme=equal 下**不**数值等价："
                        "三份冻结独立实现逐可行值各跑一遍，私有通道 79 处 / 公开通道 81 处指标超 daily 档 ε 带"
                        "（DIVERGENCE_EVIDENCE 那一条），因此 oracle 不得替 agent 挑一个 —— 诚实终止。"})
    _oracle_write(CTX, art)               # 标准路径 + 0600（红线 5）
    print("wrote", ARTIFACT_PATH, "halted", halted, file=sys.stderr)


if __name__ == "__main__":
    main()
