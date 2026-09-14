# -*- coding: utf-8 -*-
"""红队回归（卡 2.3，2026-09-02）：36 条确认发现，攻击者的 case **原样**入库当夹具。

每条写明修复后的期望：A/B 类要被指定 code 拦下，C 类（误拒）必须通过。
所有 case 都不得再触发 `validator_exception`（校验器自己抛异常也是一种静默失败）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from reference import artifact_schema as sch     # noqa: E402

CASES = _REPO / "ops" / "redteam_cases" / "c23"

#: case 文件名前缀 → (类别, 期望)。期望为 "ok" 或必须出现的 code 集合。
EXPECT: dict[str, tuple[str, object]] = {
    "rt01": ("A", {"declaration_enum"}),
    "rt02": ("A", {"declaration_enum"}),
    "rt03": ("B", {"declaration_enum"}),               # 且不得再报 declaration_mismatch
    "rt04": ("C", "ok"),
    "rt05": ("A", {"envelope_task_id_mismatch"}),
    "rt06": ("A", {"missing_masquerading_as_signal"}),
    "rt07": ("A", {"s5_signal_row_malformed"}),
    "rt08": ("B", {"zero_under_rank_semantics"}),
    "rt09": ("A", {"envelope_task_id_mismatch"}),
    "rt10": ("A", {"declaration_type"}),
    "rt11": ("A", {"s3_degeneracy_missing"}),
    "rt12": ("C", "ok"),
    "rt13": ("A", {"s7_ledger_check_missing"}),
    "rt14": ("A", {"turnover_single_recorded"}),
    "rt15": ("A", {"optimizer_failure_silently_carried"}),
    "rt16": ("A", {"unknown_schema_version"}),
    "rt17": ("A", {"envelope_task_id_mismatch"}),
    "rt18": ("A", {"overreach_count_mismatch"}),
    "rt19": ("B", {"gate_failed_malformed"}),
    "rt20": ("C", "ok"),
    "rt21": ("C", {"s3_nonfinite_missing"}),           # 规格改成与代码一致；case 用的是旧写法，应仍被拦
    "rt22": ("A", {"declaration_type"}),
    "rt23": ("A", {"declaration_mismatch"}),
    "rt24": ("B", {"undeclared_reads"}),
    "rt25": ("B", {"missing_rows_silently_filled"}),
    "rt26": ("B", "no_exception"),
    "rt27": ("B", {"declarations_missing"}),
    "rt28": ("A", {"s3_nonfinite_missing", "s3_warmup_missing"}),
    "rt29": ("A", {"s6_position_symbol_invalid"}),
    "rt30": ("B", {"declarations_missing"}),
    "rt31": ("A", {"s4_ic_stat_not_number"}),
    "rt32": ("B", {"declarations_missing"}),
    "rt33": ("A", {"s1_fetch_malformed"}),
    "rt34": ("C", "ok"),
    "rt35": ("A", {"envelope_as_of_invalid"}),
    "rt36": ("C", "ok"),
}


def _run(case: dict) -> sch.Verdict:
    kind = case.get("kind", "artifact")
    if kind == "scorer":
        return sch.validate_scorer_output(case["artifact"])
    if kind == "telemetry":
        return sch.validate_telemetry(case["artifact"])
    trad = case.get("tradability")
    if trad:
        trad = {tuple(k.split("|", 1)): s for k, s in trad.items()}
    return sch.validate(case["artifact"], task=case.get("task"),
                        gateway_log=case.get("gateway_log"), tradability=trad)


def _files() -> list[Path]:
    return sorted(CASES.glob("rt*.json"))


def test_all_confirmed_cases_are_present_and_expected():
    names = {p.name[:4] for p in _files()}
    assert names == set(EXPECT), {"缺夹具": set(EXPECT) - names, "多夹具": names - set(EXPECT)}


@pytest.mark.parametrize("path", _files(), ids=[p.name for p in _files()])
def test_redteam_case(path: Path):
    kind, want = EXPECT[path.name[:4]]
    case = json.loads(path.read_text(encoding="utf-8"))
    v = _run(case)
    assert "validator_exception" not in v.codes, f"校验器在 {path.name} 上抛了异常：{[str(f) for f in v.findings]}"
    if want == "ok":
        assert v.ok, f"{path.name}（{kind} 类，按规格合法）被误拒：{[str(f) for f in v.findings]}"
    elif want == "no_exception":
        pass
    else:
        assert want <= v.codes, f"{path.name}：期望 {sorted(want)}，实得 {sorted(v.codes) or '（全绿）'}"


def test_rt03_structural_failure_is_not_also_a_mismatch():
    """结构不合法先落 malformed；不能再把它当成「值不同」的违例。"""
    case = json.loads((CASES / "rt03_tristate_03.json").read_text(encoding="utf-8"))
    v = _run(case)
    assert "declaration_enum" in v.codes and "declaration_mismatch" not in v.codes
    assert v.malformed


def test_class_c_cases_are_not_vacuous():
    """判别力：C 类夹具必须真的走到了交叉核（有日志/视图/任务），不是因为上下文为空才通过。"""
    for p in _files():
        if EXPECT[p.name[:4]][1] != "ok":
            continue
        case = json.loads(p.read_text(encoding="utf-8"))
        assert case.get("task") is not None, f"{p.name} 没有任务上下文，通过不说明问题"
