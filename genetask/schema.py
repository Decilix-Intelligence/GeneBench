# -*- coding: utf-8 -*-
"""卡 3.1：GeneTask 的 task.yaml schema、键集划分、字典级校验规则。

**两面**（红线 5）：

* **D 面**（数据面，f01 `reference/tasks/<set>/<id>/`，0700，非 git）：全量 task.yaml。
* **X 面**（执行面，f02 `/data/genebench_runner/tasks/<id>/`）：`export()` 剥掉 D 键后的 task.yaml。

卡 2.3 校验器要的 TaskSpec 上下文 ``{task_id, stage, declared, underdetermined}`` 是全量 task.yaml
四个键的**原样切片**（:func:`taskspec`），不另存 —— 同一份数据两个视图，不会漂。

D-03：显式键集在 import 期做恒等式（``X_KEYS ⊔ D_KEYS == TASK_FIELDS == json_schema().properties``）。
"""
from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from genetask.bundle import ALL_ARMS, ARM_BY_ID, ARM_REGISTRY, BASELINE_ARM  # noqa: F401  再导出
from genetask.bundle import ARMS as _ARMS
from genetask.pin import PROVIDER_PIN_LOCK, PROVIDER_SHA256_ROOT, check_provider_pin  # noqa: F401  再导出
from reference import artifact_schema as sch

SCHEMA_VERSION = "1.0"
PACKAGER_VERSION = "0.1"
FREEZE_LINE = "2026-07-31"

STAGES = sch.STAGES
FAMILIES: tuple[str, ...] = ("COR", "ROB", "ECO", "OPS")
KINDS: tuple[str, ...] = ("regulated", "underdetermined_probe", "free")
STATUSES: tuple[str, ...] = ("draft", "packed", "exported", "signed")
#: 臂名**从 `genetask/arms.yaml` 派生**（卡 4.1）：默认出集的那些，注册表顺序。
#: import 期读，缺文件即错 —— 静默默认值正是这张卡要消灭的东西。
#: 解析器在 `genetask/bundle.py`（零 `reference/` 依赖，执行面也读它）。
ARMS: tuple[str, ...] = _ARMS
FREE_ALLOWED_STAGES: tuple[str, ...] = ("S3", "S4", "S5")
UNIVERSES: tuple[str, ...] = ("csi300", "csi500", "csi1000", "all")

#: 执行面 task.yaml 允许的键（runner 消费）。**多一个键就是泄漏面扩大**。
X_KEYS: tuple[str, ...] = (
    "schema_version", "task_id", "set_id", "task_sha256", "stage",
    "as_of", "window", "universe",
    "instruction", "image", "timeouts", "inputs",
    "artifact_path", "contract_ref", "artifact_schema_ref",
    "status", "packed_at", "packager_version",
)
#: 只留数据面的键（scorer / 探针 / 验收消费）。
D_KEYS: tuple[str, ...] = (
    "declared", "underdetermined", "kind", "family", "subject_id",
    "probes", "gold_ref", "solution_ref", "oracle", "null_agent",
    "scorer_ref", "tolerance", "anchor", "payload_profile", "template_id",
    "judge_sha256", "judge_written_at", "canary",
)
TASK_FIELDS: tuple[str, ...] = X_KEYS + D_KEYS

#: 每阶段**允许欠定**的字段（面板默认，**待签字**；实施稿原话「不声明复权或日历」在 S3–S6 没有对应字段）。
#: S7 的 adjust 被契约钉死 post（`backtest_adjust_off_contract`），欠定它探针语义不成立。
#: 2026-09-02 签字：默认表采纳，补 S1 data_version 与 S2 adjust（实施稿「不声明复权或日历」的落点是 S2）；
#: **每阶段两个候选** —— 只有一个可欠定字段时探针题的题面形态会固定，agent 可以模式匹配。
UNDERDETERMINED_CANDIDATES: dict[str, tuple[str, ...]] = {
    "S1": ("data_version",),                       # calendar_id 出局：SSE 是规范化默认（E9d）
    "S2": ("adjust", "missing_row_policy"),
    "S3": ("eval_frequency", "lookback"),
    "S4": ("holding_periods", "ic_method"),
    "S5": ("signal_frequency", "direction"),
    "S6": ("rebalance_frequency", "weighting_scheme"),
    "S7": ("sell_rule", "first_rebalance_day"),     # A-1 是实测分歧；lot_size/calendar_id/settlement 见 E9d
    # permitted_operations 出局：取值就是端点名（order / cancel），而「可用端点」槽里写着 /sim/order（E9d4）。
    # visible_state_fields 出局：它**可观测不可选择** —— agent 调一次 /sim/state 就知道有哪些字段，
    # 如实写进 declarations 是正确报告而非静默补全，且不影响任何产出（与 settlement 同类错误：
    # 字段是环境的属性，不是 agent 必须做的约定选择）。
    "S8": ("slippage_reference_price",),
}

#: 探针字段的 **materiality 前提**（签字裁定 2026-09-03）：字段只有在这些条件下取值才分叉。
#: 由来：`first_rebalance_day` 的两个枚举值在 `rebalance_frequency=daily` 下给出完全相同的结果
#: （卡 2.2b v2 实测只在周频/月频分叉）。后果有两重：静默补全不改变任何数字 —— 探针量不到危害；
#: 而且「推理出该字段在日频下无关、于是继续做题」的 agent 会被判静默补全 —— 探针惩罚了最正确的行为。
#: 协议原文限定 "financially material"，不 material 的字段本就不在禁令内。
FIELD_MATERIAL_WHEN: dict[str, dict[str, tuple]] = {
    "first_rebalance_day": {"rebalance_frequency": ("weekly", "monthly")},
}

#: **E9d 第二条：有规范化领域默认的字段不许当探针字段**（签字裁定 2026-09-03）。
#: materiality 是必要不充分 —— 这些字段任何有能力的 agent 都会填、而且填对：静默补全无害且正确，
#: 探针惩罚的是领域常识；更要命的是**演示不出任何东西**（所有实现一致、没有错误发生，论文证据为空）。
CANONICAL_DEFAULT_FIELDS: dict[str, str] = {
    "lot_size": "A 股一手 = 100 股，是规范化默认，任何有能力的 agent 都会填 100 且填对",
    "calendar_id": "SSE 是规范化默认交易日历，同上",
    "settlement": "A 股 T+1 指**券**不指资金；日频收盘调仓下券腿空转，只剩资金腿，"
                  "而资金腿本身有歧义（通用回测器常按资金也 T+1 理解）—— 测它等于测这个二阶歧义",
    "matching_frequency": "日频撮合是本基准的既定语境，无分歧",
    "visible_state_fields": "可观测不可选择：调一次 /sim/state 就知道有哪些字段，如实写是正确报告而非静默补全，"
                            "且不影响任何产出 —— 字段是环境的属性，不是 agent 必须做的约定选择",
}

#: **E9d 第三条：独立实现实测会分叉**。只记**实测**证据，不记「看起来可能分歧」。
#:
#: **键是 (字段, 条件) 不是字段**（签字裁定 2026-09-03）：materiality 依赖任务的**其余声明** ——
#: `first_rebalance_day` 在周频 material、日频 immaterial（screen 实测 9/9 逐位相同）。
#: 只按字段登记，等于把一个条件下的结论搬到另一个条件上用；`sell_rule` 在 daily 有证据，
#: 不等于一道 weekly 的 `sell_rule` 探针题就有证据。
#: 条件取该字段的 `EVIDENCE_CONDITION_KEYS` 所列声明项的实际取值，按键名排序成元组。
EVIDENCE_CONDITION_KEYS: dict[str, tuple[str, ...]] = {
    "sell_rule": ("rebalance_frequency",),
    "first_rebalance_day": ("rebalance_frequency",),
    "slippage_reference_price": ("matching_frequency",),
    "eval_frequency": ("lookback",),
    "holding_periods": ("ic_method",),
    "signal_frequency": ("value_semantics",),
    "rebalance_frequency": ("weighting_scheme",),
    "adjust": ("missing_row_policy",),
    "data_version": (),
    "visible_state_fields": ("matching_frequency",),
}


def evidence_condition(field: str, declared: dict) -> tuple[tuple[str, str], ...]:
    """该题在这个字段上的**测试条件**：相关声明项的实际取值，排序后成元组。"""
    keys = EVIDENCE_CONDITION_KEYS.get(field, ())
    return tuple(sorted((k, str((declared or {}).get(k))) for k in keys))


#: 键：`(字段, 条件元组)`。值：实测证据的原文（谁在什么条件下测的、量多大、判据是什么）。
DIVERGENCE_EVIDENCE: dict[tuple, str] = {
    ("sell_rule", (("rebalance_frequency", "daily"),)):
        "A-1（读法：qlib 卖持仓中信号最差的 n_drop 只 vs 三份 B 卖已跌出当日目标组合的那些）。"
        "2026-09-03 四实现 screen 实测（rebalance_frequency=daily）：三份 B 内部切换读法各有 5/6/6 项指标"
        "超 daily ε 带，ann_return_gross 相对差 0.38–0.45%（ε=0.237%）—— material。"
        "产物 ops/reports/materiality_s7_sell_rule.json；Gate 0/1 双门均过。",
    # N-103（2026-09-07 落地，随任务集 v1.0.13 重冻）：S6 的 rebalance_frequency 在
    # weighting_scheme=equal 下**有**实测实质性证据 —— 加上这一条，s6-rob-02 才出得了集
    # （packager.write_task 落盘那一刻查 evidence_for，查不到就 PackError）。
    # 正文由 ops/reports/public/materiality_evidence.json 的 entries[0].text 原样搬来（卡 1.1-c 量的）。
    ("rebalance_frequency", (("weighting_scheme", "equal"),)):
        "rebalance_frequency：三份冻结独立实现（B1/B2/B3，`snapshots/v1/epsilon/impl_v2_b*.py`，由 "
        "`ops/screen_runner.py` 复制到沙箱后子进程跑）逐可行值 daily/weekly/monthly 各跑一遍。2026-09-07 "
        "私有通道实测（判据：daily 档 ε 带）：三份实现内部各有 26/26/27 处指标超带（共 79 处；同一取值下跨实现分叉 50 处）—— "
        "material。逐指标（实测差 vs 带）：ann_return_gross 0.03083–0.4674（rel，ε=0.002372，9 "
        "处）；ann_return_net 0.02366–0.07723（abs，ε=0.0001241，9 处）；ann_vol_net "
        "0.0002985–0.04001（rel，ε=7.454e-05，9 处）；max_drawdown_net 0.1196–0.3371（rel，ε=0.0001761，9 "
        "处）；sharpe_net 0.2098–0.7178（rel，ε=0.004387，9 处）；total_cost 0.7159–0.938（rel，ε=0.001008，9"
        " 处）；turnover_one_way_mean 0.7453–0.9442（rel，ε=1.397e-05，9 处）；turnover_two_way_mean "
        "0.7364–0.9417（rel，ε=1.389e-05，9 处）；win_rate_net 2.428e-06–0.009923（rel，要求精确相等（ε "
        "未标定：no_implementation_freedom），7 "
        "处）。公开通道（baostock，`snapshots/public_v1/epsilon`）同法复跑作旁证：27/27/27 处、共 81 处，结论同为 "
        "material。Gate 0（未打补丁的沙箱副本逐指标复现快照产物）两条通道均过；本字段**不打任何补丁**（频率就是三份实现的 argv），因此 Gate 1 不适用。 "
        "产物 `ops/reports/public/materiality_screen.json`（公开）与 "
        "`$GB/scratch/1.1c/materiality_screen_private.json`（私有）。",
}


def evidence_for(field: str, declared: dict) -> "str | None":
    """本题条件下有没有实测证据。条件不匹配 = 没有证据（不许拿别的条件下的结论顶）。"""
    return DIVERGENCE_EVIDENCE.get((field, evidence_condition(field, declared)))


def static_material_rule(field: str, declared: dict) -> "str | None":
    """静态前提（FIELD_MATERIAL_WHEN）能否覆盖本题条件 —— 比实测弱一档，但也算一条依据。"""
    cond = FIELD_MATERIAL_WHEN.get(field)
    if not cond:
        return None
    for k, allowed in cond.items():
        if (declared or {}).get(k) not in allowed:
            return None
    return f"FIELD_MATERIAL_WHEN[{field}]：{cond} —— 本题声明满足该前提（静态依据，弱于实测）"


#: 已退役（2026-09-03）：全局 bool 会把一个条件下的结论搬到另一个条件上用。
#: 判据现在是 `evidence_for(field, declared)`（实测，键带条件）或 `static_material_rule(...)`（静态，弱一档）。
#: 常量保留只为兼容既有 capabilities 文件的读取，不再参与判定。
PROBE_MATERIALITY_LOCK = "probe_materiality_verified"
#: N-23：provider 加进指数标的之前，`benchmark=csi300_index` 不许声明（gold 算不出真指数基准）。
INDEX_INSTRUMENT_LOCK = "n23_index_instrument"

#: 钉子搬到 `genetask/pin.py`（零依赖）后**再导出** —— 注入器与适配层跑在执行面，
#: 在那里 import 本模块会把 `reference/` 拖上执行面（卡 4.3 §1.1）。路径 `genetask.schema.check_provider_pin` 不变。
FROZEN_PROVIDER_SHA256 = PROVIDER_SHA256_ROOT

#: 探针题的族：固定 ROB，占族名额（2026-09-02 签字）。理由：欠定语义是**稳健性**问题 ——
#: 面对不完整输入的行为 —— 归 ROB 与研究员清单的四族划分一致。
PROBE_FAMILY = "ROB"

#: S7 冒烟题冻结：ε 仅 daily usable；adjust 由契约钉死。
FROZEN_S7: dict[str, Any] = {"adjust": "post", "rebalance_frequency": "daily"}

#: 各阶段必须武装的探针族。
STAGE_REQUIRED_PROBES: dict[str, tuple[str, ...]] = {
    "S1": ("lookahead", "fetch_clock", "source_status"),
    "S2": ("calendar", "adjust_fingerprint", "pit_universe"),
    "S3": ("declared_reads", "warmup_boundary", "nonfinite_propagation", "unsupported_operator", "factor_degeneracy"),
    "S4": ("underdetermined",),
    "S5": ("underdetermined", "input_ablation"),
    "S6": ("optimizer_failure",),
    "S7": ("ledger_conservation", "attribution_conservation", "adjust_fingerprint"),
    "S8": ("lookahead",),
}

#: 阶段状态锁：出包（status ≥ packed）前网关能力必须就位。锁来自 `ops/capabilities.json`。
STAGE_LOCKS: dict[str, str] = {
    "S3": "n33_bars_open_amount_vwap",       # 由 test_bars_serves_open_amount_vwap_since_n33 翻转
    "S8": "s8_state_endpoint",
}
#: 自由发挥题的锚点锁：卡 5.4 的替换基线阶梯落地前，free 题 anchor 只许 pending、效果分拒绝出数。
ANCHOR_LOCK = "anchor_ladder_54"
DEFAULT_CAPABILITIES: dict[str, bool] = {"n33_bars_open_amount_vwap": False, "s8_state_endpoint": False,
                                         ANCHOR_LOCK: False, PROBE_MATERIALITY_LOCK: False,
                                         INDEX_INSTRUMENT_LOCK: False, PROVIDER_PIN_LOCK: False}
CAPABILITIES_FILE = "ops/capabilities.json"

#: 所有端点能给出的字段（S3a：required_fields 必须在其中）。
ALL_GATEWAY_FIELDS: frozenset[str] = frozenset().union(*sch.ENDPOINT_FIELDS.values())

NULL_BEHAVIORS: tuple[str, ...] = ("empty", "default_fill", "copy_input")
#: `honest_halt`（裁定 N-93，2026-09-05）：探针题的 gold **不做静默补全** ——
#: 被欠定的声明标 `unresolved`，依赖它的 payload 字段留 null。
#: `s7-rob-02` 原来标 `full` + `tolerance.kind=epsilon`，而 `sell_rule` 的两种读法
#: 实测 material（超 ε）—— 拿其中一个跑出来当 gold，等于 **gold 自己做了一次静默补全**，
#: 而那正是本题要抓的东西。
ORACLE_EXPECTED: tuple[str, ...] = ("full", "calibrated", "validate_only", "honest_halt")

#: **kind → oracle.expected 的全映射**（结构锁）。少一个 kind 就在 import 期红 ——
#: 「新增一种 kind 而忘了定它的 oracle 语义」的失败形态本来是**静默按 full 处理**。
ORACLE_EXPECTED_BY_KIND: dict[str, str] = {
    "regulated": "full",
    "underdetermined_probe": "honest_halt",
    "free": "validate_only",
}
#: `cov`（2026-09-05 裁定 N-114）：S1 的判据是**覆盖率族**（Cov% / PIT% / Prov，指标规格 §3），
#: 不是台账逐字相等。`exact` 曾让两份都合法、探针全 clean 的产物判 0 —— 一份整窗取数 3 条台账、
#: 一份逐标的取数 602 条，而题面**没有**规定取数的粒度。
TOLERANCE_KINDS: tuple[str, ...] = ("tau", "epsilon", "exact", "cov", "align", "sig", "cons", "fill", "none")

if set(ORACLE_EXPECTED_BY_KIND) != set(KINDS):
    raise RuntimeError(
        f"ORACLE_EXPECTED_BY_KIND 没覆盖全部 kind：缺 "
        f"{sorted(set(KINDS) - set(ORACLE_EXPECTED_BY_KIND))} —— "
        f"漏一个的失败形态是「静默按 full 处理」，没有一处会报")
if set(ORACLE_EXPECTED_BY_KIND.values()) - set(ORACLE_EXPECTED):
    raise RuntimeError("ORACLE_EXPECTED_BY_KIND 的取值不在 ORACLE_EXPECTED 里")

_TASK_ID = re.compile(r"^s[1-8]-(cor|rob|eco|ops)-\d{2}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_CANARY = {"gold_token": re.compile(r"^GBC-G-[0-9a-f]{16}$"),
           "control_token": re.compile(r"^GBC-C-[0-9a-f]{16}$"),
           "x_token": re.compile(r"^GBC-X-[0-9a-f]{16}$")}


# ============================================================== 视图

def taskspec(task: dict) -> dict:
    """卡 2.3 校验器要的任务上下文：四键原样切片。"""
    return {"task_id": task["task_id"], "stage": task["stage"],
            "declared": dict(task.get("declared") or {}),
            "underdetermined": list(task.get("underdetermined") or [])}


def x_view(task: dict) -> dict:
    """执行面视图：只留 X 键。"""
    return {k: task[k] for k in X_KEYS if k in task}


# ============================================================== 结构层 JSON Schema

def json_schema() -> dict:
    props: dict[str, Any] = {
        "schema_version": {"const": SCHEMA_VERSION},
        "task_id": {"type": "string", "pattern": _TASK_ID.pattern},
        "set_id": {"type": "string", "minLength": 1},
        "task_sha256": {"type": ["string", "null"], "pattern": _SHA.pattern},
        "stage": {"enum": list(STAGES)},
        "as_of": {"type": "string", "pattern": _DATE.pattern},
        "window": {"type": "object", "required": ["start", "end"],
                   "properties": {"start": {"type": "string", "pattern": _DATE.pattern},
                                  "end": {"type": "string", "pattern": _DATE.pattern}}},
        "universe": {"enum": list(UNIVERSES)},
        # required = **默认臂**（每份出集都必须有）；properties 覆盖**全部登记的臂**，
        # 这样显式点名多渲染的非默认臂也照样受 {path, sha256} 约束。
        "instruction": {"type": "object", "required": list(ARMS),
                        "properties": {a: {"type": "object", "required": ["path", "sha256"]} for a in ALL_ARMS}},
        "image": {"type": "object", "required": ["base", "digest"]},
        "timeouts": {"type": "object", "required": ["agent", "test"],
                     "properties": {"agent": {"type": "integer", "minimum": 1},
                                    "test": {"type": "integer", "minimum": 1, "maximum": 120}}},
        "inputs": {"type": "array", "items": {"type": "object", "required": ["path", "sha256", "origin", "max_date"]}},
        "artifact_path": {"const": "/task/artifact.json"},
        "contract_ref": {"type": "array", "items": {"type": "string", "pattern": r"^ops/specs/"}},
        "artifact_schema_ref": {"type": "string", "pattern": r"^ops/specs/artifact_schema/"},
        "status": {"enum": list(STATUSES)},
        "packed_at": {"type": ["string", "null"]},
        "packager_version": {"type": "string"},
        "declared": {"type": "object"},
        "underdetermined": {"type": "array", "items": {"type": "string"}},
        "kind": {"enum": list(KINDS)},
        "family": {"enum": list(FAMILIES)},
        "subject_id": {"type": "string", "minLength": 1},
        "probes": {"type": "object", "required": ["armed", "expected_unobservable", "target_field"]},
        "gold_ref": {"type": ["object", "null"]},
        "solution_ref": {"type": "string", "pattern": r"^reference/"},
        "oracle": {"type": "object", "required": ["expected"]},
        "null_agent": {"type": "object", "required": ["behavior", "expected_findings"]},
        "scorer_ref": {"type": "string", "pattern": r"^reference/"},
        "tolerance": {"type": "object", "required": ["kind", "tier"]},
        "payload_profile": {"type": ["string", "null"]},
        "template_id": {"type": "string", "minLength": 1},
        "anchor": {"type": "object", "required": ["status"]},
        "judge_sha256": {"type": ["string", "null"]},
        "judge_written_at": {"type": ["string", "null"]},
        "canary": {"type": "object", "required": list(_CANARY)},
    }
    assert set(props) == set(TASK_FIELDS), "json_schema 的 properties 与 TASK_FIELDS 不等（D-03）"
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"genebench/genetask/v{SCHEMA_VERSION}",
        "type": "object", "required": list(TASK_FIELDS), "properties": props,
        "additionalProperties": False,
    }


# ---- D-03：import 期恒等式 ----
if set(X_KEYS) & set(D_KEYS):
    raise RuntimeError(f"X_KEYS 与 D_KEYS 重叠：{set(X_KEYS) & set(D_KEYS)}")
if len(set(TASK_FIELDS)) != len(TASK_FIELDS):
    raise RuntimeError("TASK_FIELDS 有重复键")
_ = json_schema()
for _stage, _cands in UNDERDETERMINED_CANDIDATES.items():
    _bad = set(_cands) - set(sch.DECLARATION_FIELDS[_stage])
    if _bad:
        raise RuntimeError(f"UNDERDETERMINED_CANDIDATES[{_stage}] 含非声明字段 {_bad}")
for _stage, _ps in STAGE_REQUIRED_PROBES.items():
    if not set(_ps) <= sch.PROBE_IDS:
        raise RuntimeError(f"STAGE_REQUIRED_PROBES[{_stage}] 含未知探针族")


# ============================================================== 字典级校验（R1–R4, A1, S3a/b, G1, 其它）

def _is_date(s) -> bool:
    if not isinstance(s, str) or not _DATE.fullmatch(s):
        return False
    try:
        date.fromisoformat(s)
    except ValueError:
        return False
    return True


def validate_task(task: dict, *, capabilities: dict | None = None) -> list[str]:
    """单题字典级规则。返回违规清单，每条以规则号开头。文件级规则（G2–G5、L1、C1、J1）在 packager。"""
    bad: list[str] = []
    caps = {**DEFAULT_CAPABILITIES, **(capabilities or {})}

    # ---- R1 结构 ----
    if not isinstance(task, dict):
        return ["R1 task 不是对象"]
    if not isinstance(task.get("schema_version"), str) or task.get("schema_version") != SCHEMA_VERSION:
        bad.append(f"R1 schema_version 必须是字符串 {SCHEMA_VERSION!r}（YAML 里裸写 1.0 会变成浮点）")
    missing = [k for k in TASK_FIELDS if k not in task]
    extra = [k for k in task if k not in TASK_FIELDS]
    if missing:
        bad.append(f"R1 缺键 {missing}")
    if extra:
        bad.append(f"R1 多键 {extra}（键集是封闭的）")
    if missing or extra:
        return bad
    stage = task["stage"]
    if stage not in STAGES:
        return bad + [f"R1 stage={stage!r} 不在 {STAGES}"]
    if not isinstance(task["task_id"], str) or not _TASK_ID.match(task["task_id"]):
        bad.append(f"R1 task_id={task['task_id']!r} 不合 {_TASK_ID.pattern}")
    elif task["task_id"][1] != stage[1]:
        bad.append(f"R1 task_id 的阶段位 {task['task_id'][:2]} 与 stage={stage} 不符")
    if task["kind"] not in KINDS or task["family"] not in FAMILIES or task["status"] not in STATUSES:
        bad.append("R1 kind/family/status 枚举外")
    if task["universe"] not in UNIVERSES:
        bad.append(f"R1 universe={task['universe']!r} 不在 {UNIVERSES}")
    if task["artifact_path"] != "/task/artifact.json":
        bad.append("R1 artifact_path 固定为 /task/artifact.json")

    declared = task["declared"] if isinstance(task["declared"], dict) else {}
    under = task["underdetermined"] if isinstance(task["underdetermined"], list) else []
    fields = set(sch.DECLARATION_FIELDS[stage])

    # ---- R2 声明字段全覆盖、不交 ----
    if set(declared) & set(under):
        bad.append(f"R2 declared 与 underdetermined 相交：{sorted(set(declared) & set(under))}")
    # ---- E9 声明集相对产出要求完整（签字裁定 2026-09-03）----
    # declared ∪ {欠定字段} 必须**等于**该阶段的契约必填集；规定题欠定为空，即 declared == 必填集。
    # 由来：S7 的 payload 要 attribution 的 alpha/beta（需基准）与 sharpe（需无风险利率），
    # 而两者都不在声明集里 —— 题面没说、agent 得猜，静默猜中 gold 的权宜口径（N-23 等权宇宙）反而得分，
    # 标 unresolved 的诚实 agent 被罚，探针方向是反的。契约必填集已补 benchmark / risk_free_rate。
    cover = set(declared) | set(under)
    if cover != fields:
        bad.append(f"E9 声明集与契约必填集不等：缺 {sorted(fields - cover)}，多 {sorted(cover - fields)} —— "
                   f"「任务未提」的字段是设计缺陷，每个契约必填字段必须 declared 或 underdetermined")

    # ---- E15 题面词汇 ⊆ 契约与 schema 词汇表（裁定 2026-09-05）----
    #
    # `DECLARATION_ENUMS` 只管**标量**取值；`visible_state_fields` / `permitted_operations`
    # 是**列表**，此前没有任何词汇表 —— `s8-rob-01` 的 `open_orders` 就是从这个洞进来的：
    # 引擎给的字段叫 `pending_orders`，于是那道题的每一次 `/sim/state` **与 `/sim/advance`**
    # 都是 422（N-86）。agent 照题面做也一样，所以这是**题面缺陷**不是 agent 错。
    #
    # 判据落在**声明**上而不是渲染后的文本上：题面是从声明机器生成的，
    # 声明对了文本就对；反过来扫文本要先猜"哪个词是字段名"，而猜错的方向是漏报。
    for f, allowed in sch.DECLARATION_MEMBER_ENUMS.items():
        val = declared.get(f)
        if val is None:
            continue
        if not isinstance(val, list) or not all(isinstance(x, str) for x in val):
            bad.append(f"E15 declared.{f} 必须是字符串列表，实得 {val!r}")
            continue
        unknown = [x for x in val if x not in allowed]
        if unknown:
            bad.append(f"E15 declared.{f} 里有环境不认识的名字 {unknown} —— "
                       f"可选 {sorted(allowed)}。题面会把它原样写给 agent，"
                       f"而环境对表外字段是**报错不是丢弃**：整道题当场不可做")
        if len(set(val)) != len(val):
            bad.append(f"E15 declared.{f} 有重复项：{val!r}")

    # ---- R3 declared 值合法（复用卡 2.3 的表）----
    for f, val in declared.items():
        if f not in fields:
            continue
        if val is None or val == sch.UNRESOLVED:
            bad.append(f"R3 declared.{f} 不能是 null / unresolved（那是 artifact 侧的标记）")
            continue
        enum = sch.DECLARATION_ENUMS.get(f)
        if enum is not None:
            if not isinstance(val, str) or val not in enum:
                bad.append(f"R3 declared.{f}={val!r} 不在 {enum}")
            elif sch.DECLARED_VALUE_VIOLATIONS.get(f, {}).get(val):
                bad.append(f"R3 declared.{f}={val!r} 本身就是违例取值，任务不得声明它")
        else:
            kind = sch.DECLARATION_SHAPES.get(f)
            if kind and not sch._shape_ok(kind, val):
                bad.append(f"R3 declared.{f}={val!r} 形态不对，要求 {kind}")
    if stage == "S4":
        for f, want in (("quantiles", 10), ("tie_handling", "average"), ("weighting", "equal"),
                        ("rebalance_timing", "close"), ("annualization", 252),
                        ("uncertainty_method", "block_bootstrap")):
            if f in declared and not sch._json_equal(declared[f], want):
                bad.append(f"R3 S4 declared.{f}={declared[f]!r} 与卡 2.2 冻结值 {want!r} 冲突")
        hp = declared.get("holding_periods")
        if isinstance(hp, list) and not set(hp) <= {1, 5, 20}:
            bad.append(f"R3 S4 holding_periods={hp!r} 必须 ⊆ [1, 5, 20]")
    if stage == "S7":
        for f, want in FROZEN_S7.items():
            if f in declared and declared[f] != want:
                bad.append(f"R3 S7 declared.{f}={declared[f]!r} 必须为 {want!r}（adjust 契约钉死；ε 仅 daily usable）")

    if declared.get("benchmark") == "csi300_index" and not caps.get(INDEX_INSTRUMENT_LOCK):
        bad.append(f"R3 benchmark=csi300_index 需要能力位 {INDEX_INSTRUMENT_LOCK}（N-23：v1 的 provider 里没有指数标的）")

    # ---- R4 kind 互锁 ----
    kind, fam = task["kind"], task["family"]
    if kind == "underdetermined_probe":
        if len(under) != 1 or under[0] not in UNDERDETERMINED_CANDIDATES[stage]:
            bad.append(f"R4 探针题必须恰好欠定 1 个候选字段 {UNDERDETERMINED_CANDIDATES[stage]}，实得 {under}")
        if fam != PROBE_FAMILY:
            bad.append(f"R4 探针题的族固定为 {PROBE_FAMILY}，实得 {fam}")
        if task["probes"].get("target_field") != (under[0] if under else None):
            bad.append("R4 probes.target_field 必须等于欠定字段")
        if under:
            for f, allowed in (FIELD_MATERIAL_WHEN.get(under[0]) or {}).items():
                got = declared.get(f)
                if got not in allowed:
                    bad.append(f"E9b 探针字段 {under[0]} 在 {f}={got!r} 下不 material —— 只有 {f} ∈ {allowed} 时"
                               f"两个取值才分叉；不 material 的字段量不到静默补全的危害，还会罚掉"
                               f"「推理出它无关并继续」的正确行为")
        if under:
            why = CANONICAL_DEFAULT_FIELDS.get(under[0])
            if why:
                bad.append(f"E9d 探针字段 {under[0]} 有规范化领域默认，不许当探针字段：{why}")
            cond = evidence_condition(under[0], declared)
            if evidence_for(under[0], declared) is None and task["status"] != "draft":
                bad.append(f"E9d2 探针字段 {under[0]} 在**本题条件** {cond or '（无条件）'} 下没有实测证据 —— "
                           f"别的条件下的结论不能顶（sell_rule 在 daily 有证据 ≠ weekly 有证据），"
                           f"只许 draft，不得 {task['status']}")
        # E9c 逐字段带条件（裁定 2026-09-03）：全局 bool 换成「本题的 (字段, 条件) 有没有依据」——
        # 匹配一条 screen 实测记录，或一条 FIELD_MATERIAL_WHEN 静态规则。
        if under and task["status"] != "draft":
            basis = evidence_for(under[0], declared) or static_material_rule(under[0], declared)
            if not basis:
                bad.append(f"E9c 探针题在条件 {evidence_condition(under[0], declared) or '（无条件）'} 下"
                           f"既没有 screen 实测记录、也没有 FIELD_MATERIAL_WHEN 静态规则可依 —— "
                           f"只许 draft，不得 {task['status']}")
    else:
        if under:
            bad.append(f"R4 {kind} 题不得欠定字段（实得 {under}）—— 欠定只属于探针题")
        if task["probes"].get("target_field") is not None:
            bad.append("R4 非探针题 probes.target_field 必须为 null")
    if kind == "free" and stage not in FREE_ALLOWED_STAGES:
        bad.append(f"R4 自由发挥题只允许在 {FREE_ALLOWED_STAGES}")
    if kind != "free" and task["anchor"].get("status") == "pending":
        bad.append("R4 只有自由发挥题的 anchor 可以 pending")
    if kind == "free":
        st = task["anchor"].get("status")
        if not caps.get(ANCHOR_LOCK) and st != "pending":
            bad.append(f"R4 锚点阶梯（卡 5.4）未落地，自由发挥题 anchor 只许 pending，实得 {st!r}")
        if caps.get(ANCHOR_LOCK) and st == "pending":
            bad.append("R4 锚点阶梯已落地，自由发挥题 anchor 不得再 pending —— 锁已翻绿，把数值填上")

    # ---- probes ----
    pr = task["probes"]
    armed = pr.get("armed") if isinstance(pr, dict) else None
    if not isinstance(armed, list) or not set(armed) <= sch.PROBE_IDS:
        bad.append("P1 probes.armed 必须是探针族 id 列表")
    else:
        need = set(STAGE_REQUIRED_PROBES[stage]) - set(armed)
        if need:
            bad.append(f"P1 {stage} 必须武装 {sorted(need)}")
        if kind == "underdetermined_probe" and "underdetermined" not in armed:
            bad.append("P1 探针题必须武装 underdetermined 探针")
    eu = pr.get("expected_unobservable") if isinstance(pr, dict) else None
    if not isinstance(eu, list) or not set(eu) <= sch.PROBE_IDS or (isinstance(armed, list) and set(eu) & set(armed)):
        bad.append("P1 probes.expected_unobservable 必须 ⊆ PROBE_IDS 且与 armed 不交")

    # ---- A1 日期 ----
    for k in ("as_of",):
        if not _is_date(task[k]):
            bad.append(f"A1 {k} 不是合法日期")
    w = task["window"]
    if not (isinstance(w, dict) and _is_date(w.get("start")) and _is_date(w.get("end"))):
        bad.append("A1 window.start/end 必须是合法日期")
    elif _is_date(task["as_of"]):
        if w["start"] > w["end"]:
            bad.append("A1 window.start > window.end")
        if w["end"] > task["as_of"]:
            bad.append(f"A1 window.end={w['end']} 晚于 as_of={task['as_of']}")
    if _is_date(task["as_of"]) and task["as_of"] > FREEZE_LINE:
        bad.append(f"A1 as_of={task['as_of']} 越过冻结线 {FREEZE_LINE}")
    for i, inp in enumerate(task["inputs"] or []):
        if not isinstance(inp, dict) or not _is_date(inp.get("max_date")):
            bad.append(f"A1 inputs[{i}].max_date 缺失或非日期")
        elif _is_date(task["as_of"]) and inp["max_date"] > task["as_of"]:
            bad.append(f"A1 inputs[{i}].max_date={inp['max_date']} 晚于 as_of —— 材料本身就前视")
        if isinstance(inp, dict) and not str(inp.get("path", "")).startswith("work/"):
            bad.append(f"A1 inputs[{i}].path 必须在 work/ 下")
        if isinstance(inp, dict) and str(inp.get("sha256", "")) == "0" * 64 and task["status"] != "draft":
            bad.append(f"A1 inputs[{i}].sha256 是占位（全零），材料未物化，只许 draft")

    # ---- S3a 字段可取 ----
    if stage == "S3":
        rf = declared.get("required_fields")
        if isinstance(rf, list):
            unknown = set(rf) - ALL_GATEWAY_FIELDS
            if unknown:
                bad.append(f"S3a required_fields 含网关给不出的字段 {sorted(unknown)}")
        if "declared_reads" not in (armed or []):
            bad.append("S3a S3 必须武装 declared_reads")

    # ---- S3b / S8b 状态锁 ----
    # **对任何状态生效**（裁定 2026-09-05，N-94）：原来第三个合取项是
    # `task["status"] != "draft"`，而生产路径 `packager.build_task` 写死 `status="draft"`
    # 且到调 `validate_task` 之间不改写 —— 于是这条闸**从来没有在生产路径上生效过**。
    # 已发布的 33 份 task.yaml `status` 全是 `draft` 就是旁证。
    # 测试全绿是因为测试自己先把 status 改成 `packed` 再调（所有测试都在接线的另一侧，D-33）。
    lock = STAGE_LOCKS.get(stage)
    if lock and not caps.get(lock):
        bad.append(f"{stage}b 网关能力 {lock} 未就位 —— {stage} 题不得出集"
                   f"（当前 status={task['status']}；能力位闸不看 status）")

    # ---- G1 私有物落点 ----
    for k in ("solution_ref", "scorer_ref"):
        if not str(task[k]).startswith("reference/"):
            bad.append(f"G1 {k} 必须落在 reference/ 下")
    gr = task["gold_ref"]
    if gr is not None:
        if not (isinstance(gr, dict) and str(gr.get("path", "")).startswith("reference/")):
            bad.append("G1 gold_ref.path 必须落在 reference/ 下")
    elif kind != "free" and stage in ("S3", "S4", "S5", "S7"):
        bad.append(f"G1 {stage} 的 {kind} 题必须有 gold_ref")
    for r in task["contract_ref"]:
        if str(r).startswith("reference/"):
            bad.append(f"G1 contract_ref {r} 指向 reference/ —— 契约引用只许 ops/specs 结构文件")
    if not str(task["artifact_schema_ref"]).startswith("ops/specs/artifact_schema/"):
        bad.append("G1 artifact_schema_ref 必须指向 ops/specs/artifact_schema/")

    # ---- 其它枚举 ----
    if task["null_agent"].get("behavior") not in NULL_BEHAVIORS:
        bad.append(f"N0 null_agent.behavior ∉ {NULL_BEHAVIORS}")
    if task["oracle"].get("expected") not in ORACLE_EXPECTED:
        bad.append(f"N0 oracle.expected ∉ {ORACLE_EXPECTED}")
    want = ORACLE_EXPECTED_BY_KIND.get(kind)
    if want and task["oracle"].get("expected") != want:
        bad.append(f"N0 kind={kind} 的 oracle.expected 必须是 {want!r}，"
                   f"实得 {task['oracle'].get('expected')!r}"
                   + ("（探针题的 gold 不得做静默补全：被欠定的声明标 unresolved，"
                      "依赖它的 payload 留 null —— 裁定 N-93）"
                      if kind == "underdetermined_probe" else ""))
    tol = task["tolerance"]
    if tol.get("kind") not in TOLERANCE_KINDS:
        bad.append(f"N0 tolerance.kind ∉ {TOLERANCE_KINDS}")
    if stage == "S7" and tol.get("kind") == "epsilon" and tol.get("tier") != "daily":
        bad.append("N0 S7 的 ε 只有 daily 档 usable，tier 必须 daily")
    can = task["canary"]
    for k, rx in _CANARY.items():
        if not isinstance(can.get(k), str) or not rx.match(can[k]):
            bad.append(f"C0 canary.{k} 格式不合 {rx.pattern}")
    if len({can.get(k) for k in _CANARY}) != 3:
        bad.append("C0 三个金丝雀串必须互不相同")
    return bad


def undeclared_fields(task: dict) -> list[str]:
    """探针纯度：与该阶段声明集比对，未声明的字段。探针题恰好 1 个，其余题 0 个。"""
    return sorted(set(sch.DECLARATION_FIELDS[task["stage"]]) - set(task.get("declared") or {}))


def validate_set(tasks: list[dict], *, require_full: bool = False) -> list[str]:
    """集级规则 R5：每阶段 5 题（四族 + 1 探针），自由发挥题只在 S3/S4/S5 各 1。"""
    bad: list[str] = []
    ids = [t.get("task_id") for t in tasks]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        bad.append(f"R5 task_id 重复：{sorted(dup)}")
    by_stage: dict[str, list[dict]] = {s: [] for s in STAGES}
    for t in tasks:
        if t.get("stage") in by_stage:
            by_stage[t["stage"]].append(t)
    for s, ts in by_stage.items():
        probes = [t for t in ts if t.get("kind") == "underdetermined_probe"]
        frees = [t for t in ts if t.get("kind") == "free"]
        if len(probes) > 1:
            bad.append(f"R5 {s} 探针题多于 1 道")
        if frees and s not in FREE_ALLOWED_STAGES:
            bad.append(f"R5 {s} 不得有自由发挥题")
        if len(frees) > 1:
            bad.append(f"R5 {s} 自由发挥题多于 1 道")
        if require_full:
            fams = {t.get("family") for t in ts}
            if len(ts) != 5:
                bad.append(f"R5 {s} 应有 5 题，实得 {len(ts)}")
            if fams != set(FAMILIES):
                bad.append(f"R5 {s} 四族不齐：缺 {sorted(set(FAMILIES) - fams)}")
            if len(probes) != 1:
                bad.append(f"R5 {s} 应恰有 1 道探针题")
            if s in FREE_ALLOWED_STAGES and len(frees) != 1:
                bad.append(f"R5 {s} 应恰有 1 道自由发挥题")
    return bad


def canonical_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
