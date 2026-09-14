# oracle 参考解（数据面私有；在 f01 直跑，经网关 snapshot 后端产 artifact）。gold_token: <<gold_token>>
"""S7-OPS-01 回测复现（操作规范：来源引用 / 声明回显 / 日数对账 / 信封）—— oracle 骨架。

主干复用 cor_reproduce/solve.py。本题 oracle 的重点是把审计口径的每一条都**独立复核一次**并留证，
这些复核项就是卡 5.x scorer 对本题的判据来源（D-11：判据先落盘）：

  a. provenance：恰一条 {stage, artifact_id}，两值 == work/signal.meta.json 的对应键；
     另核 meta.sha256 == sha256(work/signal.parquet)（材料完整性；agent 不必报，但 gold 里要有）。
  b. declarations：canonical_json(artifact.declarations) == canonical_json(task.declared)（键集、取值、类型全等；
     红队 rt01–rt03：枚举值被 dict/list 包装曾绕过 —— 这里逐字节比）。
  c. n_days：== len(/calendar 在 [window.start, window.end] 内 is_open 的日期) == len(daily)；
     三者不等即本题材料或引擎有问题，不出包。写 gold/n_days_check.json。
  d. payload.rebalance_frequency == declared.rebalance_frequency（契约 §7）。
  e. 信封：schema_version 是 str、stage/task_id/as_of 与 task 一致、produced_at 带时区、artifact_id 非空。
  f. 守恒残差 ≤ 1e-6。

scorer 侧（卡 5.x）对 agent 产物按 a–f 逐条硬判，任一不满足记 malformed；指标另按 ε 带判。
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

# 共用主干在 reference/ 下 —— **不 import 兄弟模板**（D-31 推论）
from reference import s7_oracle_common as cor

# 统一 I/O 契约（裁定 2026-09-05）：读标准位置的任务规格、经网关取数、写标准 artifact 路径。
# **不接受任何 stage 特定的 env/argv** —— 从任务目录读得出来的东西，一律不从环境拿。
from reference.oracle_io import context as _oracle_context
from reference.oracle_io import write as _oracle_write
from reference.oracle_io import write_private as _write_private
CTX = _oracle_context(__file__)


def canonical(o) -> str:
    return json.dumps(o, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def audit(art: dict, task: dict, meta: dict, n_open_days: int, n_daily: int, td: Path) -> None:
    prov = art["provenance"]
    assert len(prov) == 1 and prov[0] == {"stage": meta["stage"], "artifact_id": meta["artifact_id"]}, "a. provenance"
    sha = hashlib.sha256((td / "work" / "signal.parquet").read_bytes()).hexdigest()
    assert sha == meta["sha256"], "a. signal.parquet 与 meta.sha256 不符 —— 材料被动过"
    assert canonical(art["declarations"]) == canonical(task["declared"]), "b. declarations 不是逐字节回显"
    assert art["payload"]["n_days"] == n_open_days == n_daily, f"c. n_days {art['payload']['n_days']} / 日历 {n_open_days} / 引擎 {n_daily}"
    assert art["payload"]["rebalance_frequency"] == task["declared"]["rebalance_frequency"], "d. 回显"
    assert isinstance(art["schema_version"], str) and art["stage"] == task["stage"] \
        and art["task_id"] == task["task_id"] and art["as_of"] == task["as_of"], "e. 信封"
    assert datetime.fromisoformat(art["produced_at"]).tzinfo is not None, "e. produced_at 无时区"
    assert art["artifact_id"], "e. artifact_id 空"
    assert art["payload"]["ledger_check"]["max_abs_residual"] <= 1e-6, "f. 守恒"
    _write_private(td / "gold" / "n_days_check.json", {"calendar_open_days": n_open_days, "engine_days": n_daily, "artifact_n_days": art["payload"]["n_days"]})


def main(task_dir: str, arm: str = "strict") -> None:
    from reference import artifact_schema as sch
    from reference.gateway_client import Client
    td = Path(task_dir)
    task = cor.load_task(td)
    gw = Client.for_context(CTX)
    panel = cor.fetch_panel(gw, task, CTX.task_dir)
    daily = cor.run_engine(panel, task["declared"])
    meta = json.loads((td / "work" / "signal.meta.json").read_text(encoding="utf-8"))
    art = cor.build_artifact(task, daily, panel, meta, arm)
    w = task["window"]
    # `/calendar` 的实测签名是 `start_date`/`end_date`，**不收 `calendar_id`**
    # （湖里只有 SSE 一种日历，深市沿用是本项目的约定 —— 见 `gateway/routers/market.py`
    # 的 `CALENDAR_CAVEAT`）。原来这里写的是 `gw.get(..., calendar_id=..., start=...)`，
    # 三处都不对，而且 `Client` 根本没有 `.get` —— 只有真跑才现形。
    audit(art, task, meta, len(gw.trading_days(w["start"], w["end"])), len(daily), td)
    v = sch.validate(art, task={k: task[k] for k in ("task_id", "stage", "declared", "underdetermined")})
    assert v.ok, [str(f) for f in v.findings]
    # N-44：逐日台账按契约落盘（`/task/ledger.parquet` 的 gold 侧对应物）。
    # 走 `files_io.write_contracted` 而不是各写一遍 to_parquet ——
    # 五个模板各抄一遍的下场是它们慢慢漂开，而漂开表现为
    # 「同一道题两次 gold 的 sha 不同」，没有任何东西报错。
    from reference.files_io import write_contracted
    write_contracted(daily, "S7", Path(task_dir) / "gold")
    # **标准 artifact 路径**（统一 I/O 契约 D-31）—— 跑批的校验器只看这一处。
    # 只写 gold/ 的话，`run_oracles` 找不到产物，而「找不到」曾被记成「零 finding」。
    _oracle_write(CTX, art)
    _write_private(td / "gold" / "oracle_artifact.json", art)


if __name__ == "__main__":
    main(str(_oracle_context(__file__).task_dir))
