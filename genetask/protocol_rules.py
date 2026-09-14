"""把 `reference/` 的规则表导出成 validator 吃的**数据**（f01 侧，注入前生成）。

为什么是数据而不是代码：validator 跑在**容器内**，不得 import `reference/`。
把规则硬编码进 validator 等于把 reference 的表抄一份到执行面 —— 而抄的那份必然漂
（本仓库已经栽过三次：provider 记录值、可交易性词汇、冻结门）。
生成器在 f01 跑，`ops/test_protocol_validator.py` 有一条一致性测试盯着它别漂。
"""
from __future__ import annotations

import json
from pathlib import Path

from reference import artifact_schema as sch

#: 阶段内的自洽规则（不需要 gold、不需要网关日志的那些）。
#: 放在这里而不是 validator 里 —— 同一个理由：它是 reference 的知识。
INTERNAL_CONSISTENCY: dict[str, list[dict]] = {
    "S5": [{"kind": "count_matches_list", "list": "signals", "counts": "coverage",
            "item_field": "value",
            "buckets": {"n_valued": "valued", "n_null": "null", "n_flat": "flat"}}],
    "S8": [{"kind": "monotonic", "path": "events", "field": "seq"},
           {"kind": "finite", "paths": ["fills.fill_rate", "fills.slippage_bps"]}],
    "S7": [{"kind": "finite", "paths": ["ledger_check.max_abs_residual", "n_days"]}],
}


def rules_for(task: dict) -> dict[str, dict]:
    """给一道题生成四份规则数据。键名与 `validate_artifact.RULES` 对应。"""
    stage = task["stage"]
    profile = task.get("payload_profile")
    return {
        "artifact_schema.json": sch.json_schema(stage, profile),
        "contract.json": {
            "stage": stage,
            "declaration_fields": list(sch.DECLARATION_FIELDS[stage]),
            "declaration_enums": {k: list(v) for k, v in sch.DECLARATION_ENUMS.items()
                                  if k in sch.DECLARATION_FIELDS[stage]},
            "internal_consistency": INTERNAL_CONSISTENCY.get(stage, []),
        },
        "payload_depends_on.json": {stage: {k: list(v) for k, v in
                                            (sch.PAYLOAD_DEPENDS_ON.get(stage) or {}).items()}},
        # `declared_fields` 只放**键名**（不放值）。这不是秘密：题面的
        # 「本次任务的口径（逐项）」把每个字段名连同取值都列出来了，agent 都看得到。
        # 有了它，「契约必填集 − 任务声明集」这个差集 validator 自己算得出来，
        # 不需要 `underdetermined` 那个数据面键（裁定 2026-09-04 纠正了我先前的判断）。
        #
        # **给它不等于替 agent 清点**：validator 只在 agent **填错**时顶回去
        # （给未声明字段填了具体值），不提「你少标了哪个」。缺失走通用文案，
        # 不区分探针字段 —— 那条线是探针与 validator 的分界。
        "task.json": {"task_id": task["task_id"], "stage": stage,
                      "declared_fields": sorted(task.get("declared") or {})},
    }


def write_rules(task: dict, out_dir) -> dict[str, str]:
    """落盘，返回 {相对路径: sha256}（交给 P8 的文件集封闭）。"""
    import hashlib

    import genebench_config as cfg

    out = cfg.create_dir(out_dir)      # 裸 mkdir 的中间层受 umask 管 → 0775（红线 5，N-61）
    got: dict[str, str] = {}
    for name, obj in rules_for(task).items():
        blob = json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
        f = out / name
        f.write_text(blob, encoding="utf-8")
        f.chmod(0o600)
        got[name] = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    return got
