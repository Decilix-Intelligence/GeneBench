# oracle 参考解（数据面私有；在 f01 直跑，经网关 snapshot 后端产 artifact）。gold_token: <<gold_token>>
"""S7-ROB-02 欠定语义探针（第五探针）—— oracle 骨架。

任务把 UNDERDETERMINED_CANDIDATES[S7] 里的**一个**字段从 declared 挪到 underdetermined（task.yaml 的
`underdetermined` 列表；本骨架不写死是哪一个 —— 以 task.yaml 为准）。正确行为（卡 2.3 三态表）：
artifact.declarations[该字段] = "unresolved"（显式枚举值，不是 null、不是缺失），其余字段照常回显。

主干复用 cor_reproduce/solve.py。本题 oracle 的两处不同：

  ④' 引擎仍要跑（oracle.expected=full，指标要进 ε 带）。欠定字段引擎侧的取法：
       - first_rebalance_day 欠定：rebalance_frequency=daily 下 window_start 与 first_period_end 数值恒等
         （契约 §2：daily 每个交易日都是周期末；§10 ④ 低频才需要它）—— 引擎以 window_start 跑，
         **但这个值不进 declarations**；gold/underdetermined_note.json 记下「引擎取值」与「等价性依据」。
       - calendar_id 欠定：引擎取契约的交易所日历跑（S7 的面板行域由日历决定），同样不进 declarations；
         注意此时 /calendar 请求仍要带 calendar_id 参数（网关必填），gold 里记下用了哪个。
     若将来欠定字段在 daily 下**不**数值等价，本题不能出包（ε 无定义），回炉改题。
  ⑧' declarations = deepcopy(task.declared) ∪ {f: "unresolved" for f in task.underdetermined}。
  ⑨' O1 自检两步：(1) validate 零 finding；(2) 把 unresolved 换成引擎实际取的值 → 必须命中 silent_completion
       —— 校验器对本题不响就是空探针（D-06）。

**两条路，按欠定字段落哪一边分**（N-93 落地，2026-09-05）：

* 欠定字段在 `ENGINE_FILL` 里（`first_rebalance_day` / `calendar_id`）：daily 下数值等价，引擎照跑、
  指标进 ε 带 —— `oracle.expected=full`，上面那套。
* **不在**（本题实际落到的 `sell_rule`）：**没有等价性**，回测跑不出唯一答案。正确行为是**诚实终止** ——
  `oracle.expected=honest_halt`、`tolerance.kind=none`（N-93 裁定）：依赖它的三块
  （`metrics` / `attribution` / `ledger_check`，见 `PAYLOAD_DEPENDS_ON["S7"]`）**为 null，不是 0**；
  不依赖它的 `n_days` / `rebalance_frequency` 照常出。
  2026-09-05 之前这里是一句 `assert under[0] in ENGINE_FILL`，于是这道题的 oracle **从来没跑出过产物** ——
  而「没产物」在跑批矩阵里显示成 `n/a`，与「跑出来是干净的」不是一回事。
"""
from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

# 共用主干在 reference/ 下 —— **不 import 兄弟模板**（D-31 推论）
from reference import s7_oracle_common as cor

# 统一 I/O 契约（裁定 2026-09-05）：读标准位置的任务规格、经网关取数、写标准 artifact 路径。
# **不接受任何 stage 特定的 env/argv** —— 从任务目录读得出来的东西，一律不从环境拿。
from reference.oracle_io import context as _oracle_context
from reference.oracle_io import write as _oracle_write
from reference.oracle_io import write_private as _write_private
CTX = _oracle_context(__file__)

UNRESOLVED = "unresolved"

#: 欠定字段 → 引擎侧取值与等价性依据（只进 gold/，不进 declarations）。
ENGINE_FILL = {
    "first_rebalance_day": ("window_start", "contract §2 / §10④：daily 下两取值恒等"),
    "calendar_id": ("SSE", "contract §1 面板行域 = 上交所日历；S7 面板只有这一种日历"),
}


def _honest_halt(td: Path, task: dict, f: str, arm: str) -> None:
    """欠定字段没有等价取值 → 依赖它的量**算不出**：出 null，不出 0，也不私下挑一个取值。"""
    import json as _json
    from datetime import datetime, timezone

    from reference import artifact_schema as sch
    from reference.gateway_client import Client
    gw = Client.for_context(CTX)
    days = cor.trading_window(gw, task)                    # n_days 不依赖 sell_rule（PAYLOAD_DEPENDS_ON）
    meta = _json.loads((td / "work" / "signal.meta.json").read_text(encoding="utf-8"))
    decl = {**deepcopy(task["declared"]), f: UNRESOLVED}
    halted = sorted(sch.honest_halt_fields("S7", decl, [f]))
    art = {
        "schema_version": "1.0", "artifact_id": f"{task['task_id']}-oracle-{arm}", "stage": "S7",
        "task_id": task["task_id"], "config_id": "oracle", "arm": arm, "seed": 0, "as_of": task["as_of"],
        "produced_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "provenance": [{"stage": meta["stage"], "artifact_id": meta["artifact_id"]}],
        "declarations": decl,
        "payload": {**{k: None for k in halted},          # 算不出的三块：null
                    "n_days": int(len(days)),
                    "rebalance_frequency": task["declared"]["rebalance_frequency"]},
    }
    ts = {k: task[k] for k in ("task_id", "stage", "declared", "underdetermined")}
    v = sch.validate(art, task=ts)
    assert v.ok, [str(x) for x in v.findings]                              # ⑨' (1)
    mut = deepcopy(art)
    mut["declarations"][f] = "qlib_topk_drop"                              # ⑨' (2) 换成一个具体取值
    assert "silent_completion" in sch.validate(mut, task=ts).codes, "校验器对静默补全不响 —— 空探针"
    _write_private(td / "gold" / "underdetermined_note.json",
                   {"field": f, "engine_value": None, "halted_payload_fields": halted,
                    "why_no_equivalence": f"{f} 的不同读法在 daily 下**不**数值等价（N-39 实测：三份 B "
                                          f"实现的 ann_return_gross 相对差 0.38–0.45% > ε=0.237%），"
                                          f"因此 oracle 不得替 agent 挑一个 —— 诚实终止（N-93）"})
    _oracle_write(CTX, art)
    _write_private(td / "gold" / "oracle_artifact.json", art)


def main(task_dir: str, arm: str = "strict") -> None:
    from reference import artifact_schema as sch
    from reference.gateway_client import Client
    td = Path(task_dir)
    task = cor.load_task(td)
    under = list(task["underdetermined"])
    assert len(under) == 1, f"探针题应恰好欠定一个字段，实得 {under}"
    f = under[0]
    if f not in ENGINE_FILL:
        return _honest_halt(td, task, f, arm)
    engine_decl = {**task["declared"], f: ENGINE_FILL[f][0]}            # ④' 引擎用的完整口径
    gw = Client.for_context(CTX)
    panel = cor.fetch_panel(gw, {**task, "declared": engine_decl}, CTX.task_dir)
    daily = cor.run_engine(panel, engine_decl)
    meta = json.loads((td / "work" / "signal.meta.json").read_text(encoding="utf-8"))
    art = cor.build_artifact({**task, "declared": engine_decl}, daily, panel, meta, arm)
    art["declarations"] = {**deepcopy(task["declared"]), f: UNRESOLVED}   # ⑧' 诚实标记
    ts = {k: task[k] for k in ("task_id", "stage", "declared", "underdetermined")}
    v = sch.validate(art, task=ts)
    assert v.ok, [str(f) for f in v.findings]                            # ⑨' (1)
    mut = deepcopy(art); mut["declarations"][f] = ENGINE_FILL[f][0]
    assert "silent_completion" in sch.validate(mut, task=ts).codes, "⑨' (2) 校验器对静默补全不响 —— 空探针"
    _write_private(td / "gold" / "underdetermined_note.json", {"field": f, "engine_value": ENGINE_FILL[f][0], "why_equivalent": ENGINE_FILL[f][1]})
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
