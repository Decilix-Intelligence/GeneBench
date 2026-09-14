#!/usr/bin/env python3
"""GeneQuant 协议 v1 —— artifact 自检 CLI。**容器内可运行**。

    python3 /task/protocol/validate_artifact.py /task/artifact.json

这是协议臂相对裸臂多出的**执行机制**（公平性协议 §3.2：语义内容两臂都给，
剩给协议臂的只有三态强制、结构化反馈、修复回路）。

**它是 scorer L1 的子集**，边界是硬的：
* **不含**任何需要网关日志的探针（前视、越权、declared_reads）——那些的证据在数据面；
* **不含** gold、不比数；
* **不联网**；
* **零 `reference/` 依赖**（与 `genetask/bundle.py`、`genetask/pin.py` 同一条纪律，
  AST + 子进程双自证）。规则**全数据驱动**：四个 JSON 由注入器随工件一起放进 `/task/protocol/`。

`ops/test_protocol_validator.py` 有一条一致性测试：**validator 与 scorer L1 在同一语料上的
子集判定逐条相同** —— 否则就是「两份必然漂」的第四个实例。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

#: 规则数据（注入器放进 /task/protocol/）。**没有硬编码的规则** ——
#: 硬编码一份就等于把 reference 的表抄进了执行面，而抄的那份必然漂。
RULES = {
    "schema": "artifact_schema.json",          # 该阶段的 JSON Schema（结构层）
    "contract": "contract.json",               # 该阶段契约必填集 + 枚举
    "depends": "payload_depends_on.json",      # PAYLOAD_DEPENDS_ON 依赖图
    "task": "task.json",                       # task_id / stage / declared_fields（只有键名）
}

UNRESOLVED = "unresolved"

#: **validator 的作用域**（裁定 2026-09-04）。显式列出它负责的违例类别 ——
#: 有了这张表，子集一致性才能补上**反向**判据：
#: 作用域**内**，scorer L1 报 ⟹ validator 也必须报；
#: 否则 agent 过了 validator 却在 scorer 的同类项上失败，**修复回路就在撒谎**。
#: 作用域**外**（网关日志探针、比数）只要求前一方向（validator 报 ⟹ scorer 报）。
SCOPE: frozenset[str] = frozenset({
    "envelope_missing", "envelope_type", "stage_mismatch", "task_id_mismatch",
    "declarations_missing", "payload_missing",
    "declaration_missing", "declaration_null", "declaration_enum", "declaration_extra",
    "silent_completion",
    "payload_key_missing", "payload_type", "payload_item_type",
    "computed_despite_unresolved",
    "coverage_mismatch", "not_monotonic", "not_finite",
    "not_an_object", "not_json",
})

#: scorer 侧属于本作用域的 code（两边命名不同，这张表是**唯一**的对照点）。
#: 它必须与 SCOPE 一一对应地覆盖 —— `ops/test_protocol_validator.py` 有一致性断言。
SCORER_SCOPE: frozenset[str] = frozenset({
    "not_an_object", "missing_schema_version", "unknown_schema_version",
    "envelope_missing_field", "envelope_bad_type",
    "declarations_missing", "payload_missing",
    "declaration_missing", "declaration_null", "declaration_not_in_enum",
    "declaration_unknown_field", "declaration_mismatch",
    "computed_despite_unresolved",
    "s1_fetches_missing", "s1_fields_obtained_missing",
    "s2_panel_ref_malformed", "s2_field_map_missing", "s2_missing_rows_missing",
    "s3_values_ref_malformed", "s4_ic_stats_incomplete", "s4_ic_stat_not_number",
    "s5_signals_missing", "s5_coverage_missing", "s5_coverage_mismatch",
    "s6_targets_missing", "s7_metrics_incomplete", "s8_events_missing",
    "s8_fills_missing", "s8_state_transitions_missing",
    "payload_profile_key_missing",
    # ---- 2026-09-06（N-129）新纳入：**叶子级**的结构判据。
    # 规则数据（`work/{stage}.json`）下到叶子之后，validator 靠 `_type_ok` 的下钻就能判这些 ——
    # 它们此前在作用域之外，于是「validator 一条不报、scorer 判 malformed」是**合规**的，
    # 而修复回路因此在真产物上一次都没启动（实测 4 份）。语料一致性由
    # `ops/validator_parity.py` 在 121 份真 artifact 上守着。
    "s1_status_enum", "s1_fetch_malformed",
    "s3_factor_id_missing", "s3_expression_missing", "s3_values_ref_malformed",
    "s3_nonfinite_missing", "s3_warmup_missing", "s3_degeneracy_missing",
    "s3_approximated_operators_missing",
    "s5_signal_row_malformed", "s5_value_type", "s5_coverage_inconsistent",
    "s7_metrics_missing", "s7_n_days_missing", "s7_ledger_check_missing", "s7_attribution_missing",
    "s8_event_malformed", "s8_transitions_missing", "s8_overreach_missing",
    "s2_panel_ref_malformed_leaf",
})



class Violation(dict):
    """结构化违例。字段与 scorer 的 Finding 对齐：code / severity / path / msg。"""

    def __init__(self, code: str, severity: str, path: str, msg: str):
        super().__init__(code=code, severity=severity, path=path, msg=msg)


def _load(rules_dir: Path) -> dict:
    out = {}
    for k, fn in RULES.items():
        p = rules_dir / fn
        if not p.is_file():
            raise SystemExit(f"规则文件缺失：{p} —— validator 不猜规则，缺一个就不跑")
        out[k] = json.loads(p.read_text(encoding="utf-8"))
    return out


def _at(payload: dict, dotted: str):
    cur = payload
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _type_ok(val, spec: dict) -> bool:
    """够用的 JSON Schema 子集：type / enum / required / minLength / minimum / maximum / pattern，
    **并逐层下钻** `properties` 与 `items`。

    2026-09-06（N-129）补的就是「下钻」这一半：此前它只判到「这个键是 object、必填的子键在不在」，
    于是三类真实错误一条都报不出来 ——
    `status` 写成 HTTP 200（枚举）、`alert` 写成一句话（bool）、`date` 写成紧凑串（pattern）。
    规则数据（`work/{stage}.json`）里现在有这些约束了，这里必须真的去看它们，
    否则「规则补全了」只是文件变长。**仍然没有任何阶段知识** —— 全按数据判。
    """
    import re as _re

    if "enum" in spec:
        return val in spec["enum"]
    t = spec.get("type")
    types = t if isinstance(t, list) else ([t] if t else [])
    if not types:
        return True
    ok = False
    for ty in types:
        if ty == "null" and val is None:
            ok = True
        elif ty == "boolean" and isinstance(val, bool):
            ok = True
        elif ty == "string" and isinstance(val, str):
            ok = len(val) >= spec.get("minLength", 0)
            if ok and spec.get("pattern"):
                ok = _re.search(spec["pattern"], val) is not None
        elif ty == "integer" and isinstance(val, int) and not isinstance(val, bool):
            ok = spec.get("minimum", float("-inf")) <= val <= spec.get("maximum", float("inf"))
        elif ty == "number" and isinstance(val, (int, float)) and not isinstance(val, bool):
            ok = spec.get("minimum", float("-inf")) <= val <= spec.get("maximum", float("inf"))
        elif ty == "array" and isinstance(val, list):
            ok = len(val) >= spec.get("minItems", 0)
            item = spec.get("items")
            if ok and isinstance(item, dict):
                ok = all(_type_ok(x, item) for x in val)
        elif ty == "object" and isinstance(val, dict):
            ok = all(k in val for k in spec.get("required", []))
            if ok:
                for k, sub in (spec.get("properties") or {}).items():
                    if k in val and not _type_ok(val[k], sub):
                        ok = False
                        break
        if ok:
            break
    return ok


def validate(artifact: dict, rules: dict) -> list[Violation]:
    """返回结构化违例列表。空列表 = 这一层没查出问题（**不等于满分**）。"""
    out: list[Violation] = []
    schema, contract = rules["schema"], rules["contract"]
    task, depends = rules["task"], rules["depends"]
    stage = task["stage"]

    if not isinstance(artifact, dict):
        return [Violation("not_an_object", "malformed", "$", "artifact 必须是 JSON 对象")]

    # ---- V1 信封 ----
    for k in schema.get("required", []):
        if k not in artifact:
            out.append(Violation("envelope_missing", "malformed", f"$.{k}", f"信封缺 {k}"))
    props = schema.get("properties", {})
    for k, spec in props.items():
        if k in artifact and k not in ("declarations", "payload") and not _type_ok(artifact[k], spec):
            out.append(Violation("envelope_type", "malformed", f"$.{k}",
                                 f"{k} 的取值 {artifact[k]!r} 不合 schema"))
    if artifact.get("stage") != stage:
        out.append(Violation("stage_mismatch", "malformed", "$.stage",
                             f"stage={artifact.get('stage')!r}，本题是 {stage}"))
    if artifact.get("task_id") != task["task_id"]:
        out.append(Violation("task_id_mismatch", "malformed", "$.task_id",
                             f"task_id 与本题不符"))

    decl = artifact.get("declarations")
    if not isinstance(decl, dict):
        out.append(Violation("declarations_missing", "malformed", "$.declarations",
                             "declarations 必须是对象"))
        return out
    payload = artifact.get("payload")
    if not isinstance(payload, dict):
        out.append(Violation("payload_missing", "malformed", "$.payload", "payload 必须是对象"))
        return out

    # ---- V2 声明集**对契约必填集**的完整性（三态） ----
    required_decl = contract["declaration_fields"]
    enums = contract.get("declaration_enums", {})
    for f in required_decl:
        if f not in decl:
            out.append(Violation("declaration_missing", "malformed", f"$.declarations.{f}",
                                 f"契约必填的声明字段 {f} 缺失 —— "
                                 f"三态是「有值 / 显式 unresolved / 缺失」，缺失一律畸形"))
            continue
        v = decl[f]
        if v is None:
            out.append(Violation("declaration_null", "malformed", f"$.declarations.{f}",
                                 f"{f} 是 null —— null 不是三态之一；不确定要写 {UNRESOLVED!r}"))
        elif v != UNRESOLVED and f in enums and v not in enums[f]:
            out.append(Violation("declaration_enum", "malformed", f"$.declarations.{f}",
                                 f"{f}={v!r} 不在 {enums[f]}"))
    for f in sorted(set(decl) - set(required_decl)):
        out.append(Violation("declaration_extra", "malformed", f"$.declarations.{f}",
                             f"多出声明字段 {f} —— 键集必须与契约必填集精确相等"))
    # ---- V2b 未声明字段填了具体值（裁定 2026-09-04）----
    # 判据的**边界**是这条检查能不能存在的关键：
    #   * 只在「有具体值」**且**「任务未声明」时触发 —— agent 填错了，顶回去；
    #   * 字段是 `unresolved` 或**缺失**时**不提它** —— 缺失走上面的通用文案，
    #     不区分是不是探针字段。
    # 这条线把 validator 与探针分开：validator **不替 agent 清点**（不说「你少标了哪个」），
    # 只在它把不该填的填了的时候说一声。
    # 差集算得出来：契约必填集在 contract.json，任务声明的字段**名**在 task.json，
    # 两者都已在容器内 —— 后者本来就写在题面的「本次任务的口径（逐项）」里。
    declared_by_task = set(task.get("declared_fields") or [])
    for f in sorted(set(decl) & set(required_decl)):
        if f in declared_by_task:
            continue
        v = decl[f]
        if v is None or v == UNRESOLVED:
            continue                    # unresolved / 缺失不在这条判据的范围内
        out.append(Violation("silent_completion", "violation", f"$.declarations.{f}",
                             f"{f} 该字段任务未声明，却填了具体值 {v!r}"))


    # ---- V3 payload 必填 + 结构 ----
    pay_spec = props.get("payload", {})
    for k in pay_spec.get("required", []):
        if k not in payload:
            out.append(Violation("payload_key_missing", "malformed", f"$.payload.{k}",
                                 f"payload 缺 {k}"))
    for k, spec in (pay_spec.get("properties") or {}).items():
        if k in payload and not _type_ok(payload[k], spec):
            out.append(Violation("payload_type", "malformed", f"$.payload.{k}",
                                 f"{k} 的结构不合 schema"))

    # ---- V4 依赖图（诚实终止） ----
    for leaf, deps in (depends.get(stage) or {}).items():
        unresolved_deps = [d for d in deps if decl.get(d) == UNRESOLVED]
        if not unresolved_deps:
            continue
        got = _at(payload, leaf)
        if got is not None:
            out.append(Violation("computed_despite_unresolved", "violation",
                                 f"$.payload.{leaf}",
                                 f"{leaf} 依赖的口径 {unresolved_deps} 被标了 {UNRESOLVED}，"
                                 f"却把数算出来了 —— 等于私下挑了一个取值"))

    # ---- V5 内部一致性（不需要 gold 的那些） ----
    out += _internal(stage, payload, contract)
    return out


def _internal(stage: str, payload: dict, contract: dict) -> list[Violation]:
    """阶段内的自洽检查。**规则来自 contract.json**，不硬编码阶段知识。"""
    out: list[Violation] = []
    for rule in contract.get("internal_consistency", []):
        kind = rule.get("kind")
        if kind == "count_matches_list":
            lst, counts = _at(payload, rule["list"]), _at(payload, rule["counts"])
            if not isinstance(lst, list) or not isinstance(counts, dict):
                continue
            field, mapping = rule["item_field"], rule["buckets"]
            tally = {k: 0 for k in mapping}
            for item in lst:
                v = item.get(field) if isinstance(item, dict) else None
                for bucket, match in mapping.items():
                    if (match == "null" and v is None) or \
                       (match == "flat" and v == "flat") or \
                       (match == "valued" and v is not None and v != "flat"):
                        tally[bucket] += 1
            for bucket, n in tally.items():
                if counts.get(bucket) != n:
                    out.append(Violation("coverage_mismatch", "malformed",
                                         f"$.payload.{rule['counts']}.{bucket}",
                                         f"{bucket}={counts.get(bucket)!r}，"
                                         f"按 {rule['list']} 实际数是 {n}"))
        elif kind == "monotonic":
            seq = _at(payload, rule["path"])
            if isinstance(seq, list):
                vals = [x.get(rule["field"]) for x in seq if isinstance(x, dict)]
                vals = [v for v in vals if v is not None]
                if vals != sorted(vals):
                    out.append(Violation("not_monotonic", "malformed",
                                         f"$.payload.{rule['path']}",
                                         f"{rule['field']} 必须单调不减"))
        elif kind == "finite":
            for dotted in rule["paths"]:
                v = _at(payload, dotted)
                if isinstance(v, float) and (v != v or v in (float("inf"), float("-inf"))):
                    out.append(Violation("not_finite", "malformed", f"$.payload.{dotted}",
                                         f"{dotted} 必须是有限数"))
    return out


def _append_log(rules_dir: Path, artifact_path: Path, violations: list) -> None:
    """每次调用写一行 `validator.log`（裁定 2026-09-04）。

    卡 4.2 采集它，把**首次尝试静默补全**与**最终状态**拆成两个指标：
    首次带 `silent_completion` 的调用 = 首次尝试；主表探针列报**首次尝试率**
    （两臂可比 —— 裸臂没有 validator，首次即最终），最终率单列显示协议强制的效果。
    """
    import datetime
    import hashlib
    try:
        sha = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    except OSError:
        sha = None
    entry = {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "artifact_sha256": sha,
        "artifact_path": str(artifact_path),
        "n_violations": len(violations),
        "violations": [{"code": v["code"], "severity": v["severity"], "path": v["path"]}
                       for v in violations],
    }
    try:
        with open(rules_dir / "validator.log", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass          # 日志写不了不该让自检失败 —— 它是遥测，不是判据


def main() -> int:
    ap = argparse.ArgumentParser(
        description="GeneQuant v1 artifact 自检（scorer L1 的子集；不联网、不比数、不含探针）")
    ap.add_argument("artifact", nargs="?", default="/task/artifact.json")
    ap.add_argument("--rules-dir", default=str(HERE))
    ap.add_argument("--json", action="store_true", help="按 JSON 输出（便于脚本消费）")
    a = ap.parse_args()

    path = Path(a.artifact)
    if not path.is_file():
        print(f"找不到 {path}", file=sys.stderr)
        return 2
    try:
        art = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        v = [Violation("not_json", "malformed", "$", f"不是合法 JSON：{e}")]
        print(json.dumps(v, ensure_ascii=False, indent=1) if a.json else f"畸形：{e}")
        return 1

    rules = _load(Path(a.rules_dir))
    out = validate(art, rules)
    _append_log(Path(a.rules_dir), path, out)
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
    elif not out:
        print("通过：这一层没查出问题。\n"
              "注意 —— 它是评分的**子集**：不含前视/越权这类需要网关日志的检查，也不比数。")
    else:
        print(f"{len(out)} 条违例：")
        for v in out:
            print(f"  [{v['severity']}] {v['code']} @ {v['path']}\n      {v['msg']}")
    return 1 if out else 0


if __name__ == "__main__":
    raise SystemExit(main())
