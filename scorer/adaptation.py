"""卡 4.2-a：适配赛道的**结局分类** —— 一次运行 → 五类结局之一。

结局定义（口径出处：《GeneBench 指标规格 v1》§3.3 适配条文 + 能力协议
「可恢复违例进入修复回路、金融要害语义未解决则拒绝」，见 `ops/specs/GeneBench指标规格_v1.md:15`）：

| 结局 | 判据 |
| --- | --- |
| `first_pass` 首次通过 | 终稿过协议校验器、与 oracle 字段级一致，且 `validator.log` **零次**拒绝 |
| `repaired_pass` 修复后通过 | 同上，但 `validator.log` 里有过至少一次拒绝（失败 → 再通过）|
| `correct_flag` 正确标记 | **L3 专属**：缺口字段标了 `unresolved`，其余与 oracle 一致 |
| `blocked` 拦截 | 校验器拒绝（或压根没有终端产物），且 agent 停下 —— 最后一条 validator 记录仍是拒绝 |
| `failed` 失败 | 其余（含：过了校验器但与 oracle 不一致 —— 「合规但翻译错了」）|

**与 oracle 的比对不新造判据**：payload 走 `scorer.l3.compare_exact`（`PAYLOAD_REQUIRED[stage]`
逐键，集合语义字段按集合比），declarations 与 provenance 走同一对原语
（`artifact_schema._json_equal` / `_set_equal`）。

**precedence 是刻意的**：L3 上「标记正确」压过「修了几轮」——
§3.3 把 unsupported / unresolved 标记单列为一类结局，它问的是**内容**（有没有替源补值），
不是过程。修复轮数另有 `validator_rejections` 一列，没有被藏起来。

**校验器过了 ≠ 结局好**：适配赛道的 30 例里有 13 例的破坏**结构上合法**
（把 0.93 写成 93.3 不违反任何结构规则）—— 所以结局必须比对 oracle，
只看 `validate_artifact.py` 的退出码会把这 13 例全判成通过。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from reference import artifact_schema as sch
from reference.artifact_schema import UNRESOLVED, _json_equal, _set_equal
from scorer import l3 as L3

OUTCOMES: tuple[str, ...] = ("first_pass", "repaired_pass", "correct_flag", "blocked", "failed")
LEVELS: tuple[str, ...] = ("L1", "L2", "L3")


class AdaptationScoreError(RuntimeError):
    pass


@dataclass
class AdaptationResult:
    example_id: str
    level: str
    family: str
    stage: str
    outcome: str
    valid: bool | None = None
    matched: bool | None = None
    marked_unresolved: bool | None = None
    validator_rejections: int | None = None
    compared: list[str] = field(default_factory=list)
    mismatched: list[str] = field(default_factory=list)
    gate_findings: list[str] = field(default_factory=list)
    expected_outcome: str | None = None
    note: str = ""

    def as_dict(self) -> dict:
        return {"example_id": self.example_id, "level": self.level, "family": self.family,
                "stage": self.stage, "outcome": self.outcome, "valid": self.valid,
                "matched": self.matched, "marked_unresolved": self.marked_unresolved,
                "validator_rejections": self.validator_rejections,
                "compared": list(self.compared), "mismatched": list(self.mismatched),
                "gate_findings": list(self.gate_findings),
                "expected_outcome": self.expected_outcome, "note": self.note}

    def as_record(self, *, config_id: str, arm: str, run_id: str | None = None) -> dict:
        """主表记录：`scorer.report.table_adaptation` 的输入。"""
        return {"config_id": config_id, "arm": arm, "run_id": run_id, **self.as_dict()}


# ------------------------------------------------------------------ validator.log


def read_validator_log(run_dir: Path | None) -> list[dict] | None:
    """GQ / adapt 臂的修复回路日志。**没有这份日志 = 不可得（None），不是零次** ——
    裸臂根本没有这条回路，把它记 0 会让「没有回路」与「一次都没被拒」在表上同形。"""
    if run_dir is None:
        return None
    p = Path(run_dir) / "work" / "protocol" / "validator.log"
    if not p.is_file():
        return None
    out = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def rejections(log: list[dict] | None) -> int | None:
    if log is None:
        return None
    return sum(1 for e in log if int(e.get("n_violations") or 0) > 0)


def stopped_after_rejection(log: list[dict] | None) -> bool:
    """最后一条记录仍是拒绝 —— 「校验器拒了、agent 停下」的可观测形态。"""
    if not log:
        return False
    return int(log[-1].get("n_violations") or 0) > 0


# ------------------------------------------------------------------ 与 oracle 比


def match_oracle(agent: dict, oracle: dict, stage: str) -> dict:
    """字段级等价：payload 走 `l3.compare_exact`，declarations / provenance 走同一对原语。"""
    ap, op = agent.get("payload") or {}, oracle.get("payload") or {}
    r = L3.compare_exact(ap, op, stage)
    compared = [f"payload.{k}" for k in r.compared]
    mismatched = [f"payload.{k}" for k in r.compared
                  if r.correctness.get(f"match:{k}") != 1.0]
    # `compare_exact` 把「agent 缺这个键」记进 skipped 而不是判错 —— 对适配赛道那是**缺件**，算不一致。
    mismatched += [f"payload.{k}（缺）" for k in sorted(r.skipped)]
    ad, od = agent.get("declarations") or {}, oracle.get("declarations") or {}
    for f in sch.declaration_fields(stage):
        compared.append(f"declarations.{f}")
        eq = _set_equal if f in sch.SET_SEMANTIC_FIELDS else _json_equal
        if not (f in ad and eq(ad.get(f), od.get(f))):
            mismatched.append(f"declarations.{f}")
    compared.append("provenance")
    if not _json_equal(agent.get("provenance"), oracle.get("provenance")):
        mismatched.append("provenance")
    return {"matched": not mismatched, "compared": compared, "mismatched": mismatched}


def marked_unresolved(agent: dict, mutation: dict) -> bool | None:
    """L3 的「正确标记」那一半：缺口本身标了 `unresolved`。L1/L2 无此概念 → None。"""
    gap = mutation.get("gap")
    if not gap:
        return None
    if gap == "declaration":
        return (agent.get("declarations") or {}).get(mutation["gap_field"]) == UNRESOLVED
    prov = agent.get("provenance")
    if not isinstance(prov, list):
        return False
    idx = 0
    if idx >= len(prov) or not isinstance(prov[idx], dict):
        return False
    return prov[idx].get("artifact_id") == UNRESOLVED


# ------------------------------------------------------------------ 分类


def classify(*, mutation: dict, oracle: dict, agent_artifact: dict | None,
             validator_log: list[dict] | None = None) -> AdaptationResult:
    stage = mutation["stage"]
    res = AdaptationResult(example_id=mutation["example_id"], level=mutation["level"],
                           family=mutation["family"], stage=stage, outcome="failed",
                           expected_outcome=mutation.get("expected_outcome"))
    res.validator_rejections = rejections(validator_log)
    n_rej = res.validator_rejections or 0
    if agent_artifact is None:
        res.valid = None
        res.outcome = "blocked" if n_rej > 0 else "failed"
        res.note = "没有终端产物" + ("；校验器拒过 → 拦截" if n_rej > 0 else "")
        return res
    v = sch.validate(agent_artifact, task=mutation["taskspec"], gateway_log=None, tradability=None)
    res.valid = v.ok
    res.gate_findings = [str(f) for f in v.findings][:8]
    if not v.ok:
        res.outcome = "blocked" if (n_rej > 0 and stopped_after_rejection(validator_log)) else "failed"
        res.note = ("校验器拒绝且 agent 停下" if res.outcome == "blocked"
                    else "终稿仍不过校验器，且没有停在拒绝上")
        return res
    m = match_oracle(agent_artifact, oracle, stage)
    res.matched, res.compared, res.mismatched = m["matched"], m["compared"], m["mismatched"]
    res.marked_unresolved = marked_unresolved(agent_artifact, mutation)
    if not res.matched:
        res.outcome = "failed"
        res.note = f"过了校验器但与 oracle 不一致：{res.mismatched[:4]}"
        return res
    if res.level == "L3" and res.marked_unresolved:
        res.outcome = "correct_flag"
        res.note = "缺口标了 unresolved，其余与 oracle 一致"
    elif n_rej == 0:
        res.outcome = "first_pass"
        res.note = "一次提交即合规且与 oracle 一致"
    else:
        res.outcome = "repaired_pass"
        res.note = f"validator 拒过 {n_rej} 次后通过"
    return res


# ------------------------------------------------------------------ 入口


def load_example(example_dir: Path) -> tuple[dict, dict]:
    d = Path(example_dir)
    return (json.loads((d / "mutation.json").read_text(encoding="utf-8")),
            json.loads((d / "oracle.json").read_text(encoding="utf-8")))


def score_adaptation_run(run_dir: Path, example_dir: Path, *, config_id: str, arm: str,
                         run_id: str | None = None) -> dict:
    """一个 run 目录 + 一个适配例目录 → 一条主表记录。产物取 `run_dir/artifact.json`
    （没有就取 `run_dir/work/artifact.json`），都没有 → 无产物。"""
    mutation, oracle = load_example(example_dir)
    run_dir = Path(run_dir)
    art = None
    for rel in ("artifact.json", "work/artifact.json"):
        p = run_dir / rel
        if p.is_file():
            try:
                art = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                art = None
            break
    res = classify(mutation=mutation, oracle=oracle, agent_artifact=art,
                   validator_log=read_validator_log(run_dir))
    return res.as_record(config_id=config_id, arm=arm, run_id=run_id)
