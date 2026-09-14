# -*- coding: utf-8 -*-
"""记忆探针（N-31）的判卷器与题集校验器 —— 判别力优先。

**题目还没出**（归卡 3.2），但判卷规则与同构约束**必须先定死**（签字要求：
「判卷方式先定死再出题」）。所以这里用**合成题集**证明校验器与判卷器**不是空的**：
每条规则都要有一个负例把它拦下，其中几条还要证明它**独立**于其他规则。

题集里的数值全是**合成值**，不是真答案 —— 真答案在
`reference/memory_probe_answers/answers.json`，红线 5 第三类，永不进执行面。
"""
from __future__ import annotations

import sys
from copy import deepcopy
from datetime import date
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from reference import memory_probe as mp        # noqa: E402


# ------------------------------------------------------------------ 合成题集

def _q(fmt: str, body: str) -> str:
    """题面模板：开放问法 + 明确的作答格式 + 明确的弃权出口。"""
    return (f"{body}"
            f"若你对该时段没有可靠记忆，请回答 UNKNOWN。"
            f"作答格式：{fmt}，只输出一个值，不要解释。")


def _cpi(pid: str, when: str, arm: str, rung, key) -> dict:
    return {"id": pid, "kind": "macro_yoy", "source_dataset": "cn_cpi",
            "source_field": "nt_yoy", "template_id": "cpi_yoy_of_month",
            "as_of_date": when, "arm": arm, "rung": rung,
            "answer_format": "NUMBER", "key": key,
            "question": _q("NUMBER", f"全国居民消费价格指数（CPI）在 {when} 的同比变动百分比是多少？")}


def _idx(pid: str, when: str, arm: str, rung, key) -> dict:
    return {"id": pid, "kind": "index_level", "source_dataset": "index_daily",
            "source_field": "close", "template_id": "index_close_on_date",
            "as_of_date": when, "arm": arm, "rung": rung,
            "answer_format": "NUMBER", "key": key,
            "question": _q("NUMBER", f"沪深 300 指数（000300.SH）在 {when} 的收盘点位是多少？")}


#: 合格题集：2 道探针题，每道配 3 道**结构同构**的对照题。
GOOD: list[dict] = [
    _cpi("MP-CPI-P", "2026-08", "probe", None, 1.37),
    _cpi("MP-CPI-L1", "2025-12", "control", "L1", 0.91),
    _cpi("MP-CPI-L2", "2026-03", "control", "L2", 1.02),
    _cpi("MP-CPI-L3", "2026-06", "control", "L3", 1.15),
    _idx("MP-IDX-P", "2026-08-31", "probe", None, 4321.7788),
    _idx("MP-IDX-L1", "2025-12-31", "control", "L1", 3987.6543),
    _idx("MP-IDX-L2", "2026-03-31", "control", "L2", 4102.2211),
    _idx("MP-IDX-L3", "2026-06-30", "control", "L3", 4288.9900),
]


def _mut(fn):
    s = deepcopy(GOOD)
    fn(s)
    return s


def _set(items, pid, **kw):
    for it in items:
        if it["id"] == pid:
            it.update(kw)


#: 负例 -> (题集, 期望命中的规则号, 是否要求「只有这一条」)
CASES: dict[str, tuple[list[dict], str, bool]] = {
    "P-1 缺必填字段": (_mut(lambda s: _set(s, "MP-CPI-L2", id="")), "P-1", True),
    "P-2 作答格式与题类不符": (
        _mut(lambda s: _set(s, "MP-IDX-P", answer_format="DATE")), "P-2", False),
    "P-3 探针题的日期没越过冻结线": (
        _mut(lambda s: _set(s, "MP-IDX-P", as_of_date="2026-07-15")), "P-3", True),
    "P-3b 对照题的日期不在本档区间": (
        _mut(lambda s: _set(s, "MP-CPI-L2", as_of_date="2026-05")), "P-3", True),
    "P-4 少一道对照题": (
        _mut(lambda s: s.remove(next(i for i in s if i["id"] == "MP-CPI-L2"))), "P-4", True),
    "P-4b 对照题换了数据源（不再同构）": (
        _mut(lambda s: _set(s, "MP-IDX-L2", source_dataset="tdx_index_daily")), "P-4", True),
    "P-5 题面里出现了答案": (
        _mut(lambda s: _set(s, "MP-CPI-P", question=_q("NUMBER", "CPI 同比是 1.37 吗？"))),
        "P-5", False),
    "P-5b 题面含泄漏结论的措辞": (
        _mut(lambda s: _set(s, "MP-IDX-P",
                            question=_q("NUMBER", "沪深 300 在 2026 年 8 月上涨了多少点？"))),
        "P-5", True),
    "P-6 题面没写作答格式": (
        _mut(lambda s: _set(s, "MP-CPI-L1", question="CPI 同比多少？")), "P-6", True),
    "P-7 题号重复": (
        _mut(lambda s: _set(s, "MP-IDX-L1", id="MP-CPI-L1")), "P-7", True),
}


# ------------------------------------------------------------------ 题集校验

def test_good_set_passes():
    assert mp.validate_probe_set(GOOD) == [], "合格题集就不干净，后面的负例都不作数"


@pytest.mark.parametrize("name", list(CASES))
def test_each_negative_control_is_caught_by_its_own_rule(name):
    items, want, exclusive = CASES[name]
    found = mp.validate_probe_set(items)
    hit = [v for v in found if v.startswith(want)]
    assert hit, f"{name}：期望命中 {want}，实得 {found or '（全绿）'}"
    if exclusive:
        others = {v.split()[0] for v in found} - {want}
        assert not others, f"{name}：应只由 {want} 拦下，却还命中了 {others}"


def test_P4_is_the_only_rule_that_sees_a_missing_control():
    """P-4 的独立性：删掉一道对照题，别的规则都察觉不到 —— 只有同构判据能。"""
    items, _, _ = CASES["P-4 少一道对照题"]
    found = mp.validate_probe_set(items)
    assert {v.split()[0] for v in found} == {"P-4"}
    assert "只有日期允许不同" in found[0], "P-4 的报错要写清同构判据，否则没法改"


def test_isomorphism_keys_do_not_include_the_date():
    """同构判据里**不能**包含日期 —— 否则「只有日期不同」这条约束自相矛盾。"""
    assert "as_of_date" not in mp.ISOMORPHIC_KEYS


def test_every_kind_has_both_tolerance_and_format():
    assert set(mp.TOLERANCES) == set(mp.ANSWER_FORMATS)
    for kind, (mode, tol) in mp.TOLERANCES.items():
        assert mode in {"abs", "rel", "exact_date", "exact_set", "exact_int"}
        assert tol >= 0


# ------------------------------------------------------------------ 判卷

@pytest.mark.parametrize("text,kind,key,want", [
    # CPI 同比：绝对容差 0.05 个百分点（签字给定）
    ("1.40", "macro_yoy", 1.37, "hit"),
    ("1.42", "macro_yoy", 1.37, "hit"),          # 恰好 0.05，含边界
    ("1.45", "macro_yoy", 1.37, "miss"),
    # 指数点位：相对容差 0.5%（签字给定）
    ("4015", "index_level", 4000.0, "hit"),
    ("4020", "index_level", 4000.0, "hit"),      # 恰好 0.5%
    ("4030", "index_level", 4000.0, "miss"),
    # 弃权与不可解析必须与 miss 分开
    ("UNKNOWN", "macro_yoy", 1.37, "abstain"),
    ("不知道", "index_level", 4000.0, "abstain"),
    ("大概四千多点", "index_level", 4000.0, "unparseable"),
    ("", "macro_yoy", 1.37, "unparseable"),
    # 日期与代码集合无容差
    ("20260814", "event_date", "2026-08-14", "hit"),
    ("2026-08-15", "event_date", "2026-08-14", "miss"),
    ("600519.SH, 000001.SZ", "code_set", ["600519.SH", "000001.SZ"], "hit"),
    ("600519.SH", "code_set", ["600519.SH", "000001.SZ"], "miss"),
])
def test_grade_answer(text, kind, key, want):
    got, why = mp.grade_answer(text, kind, key)
    assert got == want, f"{text!r} → {got}（期望 {want}）：{why}"


def test_tolerance_band_is_not_vacuous():
    """判别力：容差带必须**同时**能判 hit 与 miss。只会判一种的带子是空的。"""
    for kind, key, near, far in [("macro_yoy", 2.0, "2.03", "2.30"),
                                 ("index_level", 5000.0, "5010", "5300")]:
        assert mp.grade_answer(near, kind, key)[0] == "hit"
        assert mp.grade_answer(far, kind, key)[0] == "miss"


def test_unknown_kind_refuses_to_grade():
    """没定容差的题类**不许判卷** —— 容差先定死再出题。"""
    with pytest.raises(KeyError, match="容差"):
        mp.grade_answer("1.0", "some_new_kind", 1.0)


# ------------------------------------------------------------------ 不用 LLM 判卷

def test_no_llm_judge_flag_is_locked():
    assert mp.NO_LLM_JUDGE is True


def test_module_does_not_reach_for_a_model():
    """源码级审计：判卷器里不许出现任何模型/网络调用。

    用模型判卷会把**裁判方差**引进一个本来零方差的探针。
    """
    src = (_REPO / "reference" / "memory_probe.py").read_text(encoding="utf-8")
    code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
    for bad in ("import requests", "import httpx", "urllib.request", "openai",
                "anthropic", "def judge_with_model", "client.messages"):
        assert bad not in code, f"判卷器里出现了 {bad!r} —— 判卷必须程序化"


# ------------------------------------------------------------------ 答案隔离（红线 5 第三类）

def test_export_with_keys_is_refused():
    with pytest.raises(RuntimeError, match="红线 5 第三类"):
        mp.assert_export_is_key_free(GOOD)


def test_stripped_export_passes_and_keeps_everything_else():
    out = mp.strip_keys(GOOD)
    mp.assert_export_is_key_free(out)                     # 不抛
    assert len(out) == len(GOOD)
    assert all("key" not in it for it in out)
    assert {it["id"] for it in out} == {it["id"] for it in GOOD}
    assert all(it["question"] for it in out), "剥答案不能顺手把题面也剥了"


def test_gateway_can_never_route_a_probe_path():
    """网关的字面防线要覆盖第三类不可泄漏物。"""
    from gateway.app import FORBIDDEN_PATH_TOKENS
    assert "probe" in FORBIDDEN_PATH_TOKENS
    assert "answer" in FORBIDDEN_PATH_TOKENS


@pytest.mark.parametrize("pkg", ["runner", "gateway"])
def test_execution_side_never_imports_the_probe_module(pkg):
    """执行面侧的包里不得出现探针模块的任何引用。"""
    for path in sorted((_REPO / pkg).rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        assert "memory_probe" not in text, f"{path} 引用了记忆探针模块（红线 5 第三类）"


# ------------------------------------------------------------------ 汇总与主表三列

def _g(arm, rung, outcome, n=1):
    return [{"arm": arm, "rung": rung, "outcome": outcome} for _ in range(n)]


def test_low_control_rate_is_inconclusive_not_clean():
    """**这是整套探针的关键判据**：控制组答不出时，0% 命中不等于干净。"""
    graded = _g("probe", None, "abstain", 8) + _g("control", "L3", "miss", 8)
    out = mp.summarize(graded)
    assert out["memory_probe_hit_rate"] == 0.0
    assert out["validity"] == "inconclusive", "控制组不达标却判成 clean —— 这正是要防的误读"


def test_hits_with_good_control_is_contaminated():
    graded = (_g("probe", None, "hit", 4) + _g("probe", None, "miss", 4)
              + _g("control", "L3", "hit", 8))
    out = mp.summarize(graded)
    assert out["memory_probe_hit_rate"] == 0.5
    assert out["memory_probe_control_rate"] == 1.0
    assert out["validity"] == "contaminated"


def test_no_hits_with_good_control_is_clean():
    graded = _g("probe", None, "miss", 8) + _g("control", "L3", "hit", 8)
    assert mp.summarize(graded)["validity"] == "clean"


def test_measured_horizon_tracks_the_ladder():
    """实测知识地平线：能可靠答对的最晚一档。"""
    graded = (_g("control", "L1", "hit", 4) + _g("control", "L2", "hit", 4)
              + _g("control", "L3", "miss", 4) + _g("probe", None, "miss", 4))
    out = mp.summarize(graded)
    assert out["memory_probe_horizon"] == "L2"
    assert out["control_rate_by_rung"] == {"L1": 1.0, "L2": 1.0, "L3": 0.0}
    assert out["validity"] == "inconclusive", "L3 没过就不该给结论"


def test_unparseable_is_counted_separately_and_never_a_hit():
    graded = _g("probe", None, "unparseable", 3) + _g("control", "L3", "hit", 4)
    out = mp.summarize(graded)
    assert out["unparseable"] == 3
    assert out["memory_probe_hit_rate"] is None, "全是不可解析时不该编一个 0.0 出来"


def test_abstain_and_miss_are_not_merged():
    a = mp.summarize(_g("probe", None, "abstain", 4) + _g("control", "L3", "hit", 4))
    b = mp.summarize(_g("probe", None, "miss", 4) + _g("control", "L3", "hit", 4))
    assert a["abstain"] == 4 and b["abstain"] == 0
    assert a["memory_probe_hit_rate"] == b["memory_probe_hit_rate"] == 0.0


def test_freeze_line_matches_the_project_freeze_line():
    assert mp.FREEZE_LINE == date(2026, 7, 31)



# ------------------------------------------------- unparseable 的不对称（单独报，不平均）

def test_probe_only_unparseable_pattern_is_surfaced():
    """对照题正常作答、目标题突然大量不可解析 —— 这个形态必须单独报，不能平均掉。"""
    graded = (_g("control", "L3", "hit", 6) + _g("control", "L1", "hit", 6)
              + _g("probe", None, "unparseable", 5) + _g("probe", None, "miss", 1))
    out = mp.summarize(graded)
    assert out["unparseable_pattern"] == "probe_only"
    assert out["unparseable_rate_control"] == 0.0
    assert out["unparseable_rate_probe"] == round(5 / 6, 4)
    assert out["unparseable_asymmetry"] == round(5 / 6, 4)
    # 且总体 unparseable 计数仍在，没有被这个新字段吞掉
    assert out["unparseable"] == 5


@pytest.mark.parametrize("probe_unp,ctrl_unp,want", [
    (0, 0, "none"), (2, 0, "probe_only"), (0, 2, "control_only"), (2, 2, "both"),
])
def test_unparseable_pattern_labels_are_threshold_free(probe_unp, ctrl_unp, want):
    graded = (_g("probe", None, "unparseable", probe_unp) + _g("probe", None, "miss", 4 - probe_unp)
              + _g("control", "L3", "unparseable", ctrl_unp) + _g("control", "L3", "hit", 4 - ctrl_unp))
    assert mp.summarize(graded)["unparseable_pattern"] == want


def test_asymmetry_is_signed_and_symmetric_cases_cancel():
    """判别力：同样的不可解析率在两臂上出现时，不对称量必须为 0。"""
    graded = (_g("probe", None, "unparseable", 2) + _g("probe", None, "miss", 2)
              + _g("control", "L3", "unparseable", 2) + _g("control", "L3", "hit", 2))
    out = mp.summarize(graded)
    assert out["unparseable_asymmetry"] == 0.0 and out["unparseable_pattern"] == "both"


# =============================================================== 红队一轮（2026-09-05，卡 5.1）
# 攻击者 case 原样入库；修前实测输出写在 docstring 里。

def test_rt51_string_key_for_code_set_raises_instead_of_permanent_miss():
    """**A 类**：`exact_set` 的钥匙写成裸字符串会被**逐字符**迭代。

    修前实测：`grade_answer("600000.SH", "code_set", "600000.SH")`
    → `('miss', '1 个 vs 5 个')`。这道题**从此永远 miss**，
    而说明看起来像是模型少答了 4 个代码 —— **错的是我们的钥匙**。
    """
    with pytest.raises(mp.KeyTypeError) as e:
        mp.grade_answer("600000.SH", "code_set", "600000.SH")
    assert "逐字符" in str(e.value)
    assert mp.grade_answer("600000.SH", "code_set", ["600000.SH"])[0] == "hit"


@pytest.mark.parametrize("key,before", [
    (3.7, "('hit', '3.0 vs 3.7')  —— int(3.7)=3，静默截断"),
    (True, "('hit', '1.0 vs True') —— int(True)=1，bool 当成整数"),
])
def test_rt51_non_integer_key_for_count_raises(key, before):
    """**A 类**：`exact_int` 对小数/bool 钥匙静默判 hit。修前：%s""" % ""
    with pytest.raises(mp.KeyTypeError):
        mp.grade_answer("3" if key is not True else "1", "count", key)
    assert mp.grade_answer("3", "count", 3)[0] == "hit", "正常钥匙不许被误伤"


@pytest.mark.parametrize("key", [None, "abc"])
def test_rt51_bad_numeric_key_raises_a_named_error(key):
    """修前是裸的 `TypeError`/`ValueError` 抛在判卷半路，看不出是钥匙的问题。"""
    with pytest.raises(mp.KeyTypeError):
        mp.grade_answer("3", "macro_yoy", key)


@pytest.mark.parametrize("text", ["不知道。", "unknown.", "n/a。", " 不知道 ", "N/A"])
def test_rt51_abstain_survives_trailing_punctuation(text):
    """**B 类**：弃权词带句号就落进 `unparseable`。

    修前实测：`"不知道。"` 与 `"n/a。"` 都是 `unparseable`。
    **弃权与不可解析是两个结局** —— 前者是模型说「我不知道」，后者是我们没读懂它。
    把弃权算成不可解析，会让实测知识地平线偏向「答不出来」那一侧，
    而那正是本卡要量的东西。剥标点是**纯词法**，不违反 `NO_LLM_JUDGE`。
    """
    assert mp.grade_answer(text, "macro_yoy", 2.5)[0] == "abstain"


def test_rt51_abstain_is_not_a_semantic_judgement():
    """边界，**故意不放宽**：`"我不知道"` 仍是 `unparseable`。

    表必须是穷举的固定表；一旦开始猜「这句话是不是弃权」，判卷就引入了裁判方差 ——
    而整张卡的前提是**判卷不经过任何模型**。
    """
    assert mp.grade_answer("我不知道", "macro_yoy", 2.5)[0] == "unparseable"


def test_rt51_abstain_detail_no_longer_says_parse_failed():
    """**C 类（措辞）**：弃权的说明原来写「作答未通过 NUMBER 解析」——
    报告里会把一次明确的拒答写成格式错误。"""
    state, why = mp.grade_answer("不知道", "macro_yoy", 2.5)
    assert state == "abstain" and "弃权" in why and "解析" not in why


def test_rt51_percent_is_only_meaningful_for_percentage_point_kinds():
    """**B 类**：`%` 原来对所有 NUMBER 题一律剥掉。

    于是 `index_level` 上的 `"2.5%"` 与 `"2.5"` 判成同一个答案 ——
    把一个**单位错误**静默改成了正确答案。`%` 只对「个百分点」那类题（`abs` 容差）有意义。
    """
    assert mp.grade_answer("2.5%", "macro_yoy", 2.5)[0] == "hit"
    assert mp.grade_answer("2.5%", "index_level", 2.5)[0] == "unparseable"
    assert mp.grade_answer("2.5", "index_level", 2.5)[0] == "hit"


def test_rt51_check_key_covers_every_tolerance_mode():
    """判据封闭：`TOLERANCES` 里每一种模式都要被 `check_key` 认领。

    漏掉一种的表现是**那种题的钥匙不受检**，而漏没漏在测试全绿时看不出来。
    """
    import inspect
    src = inspect.getsource(mp.check_key)
    modes = {m for m, _ in mp.TOLERANCES.values()}
    missing = [m for m in sorted(modes) if f'"{m}"' not in src]
    assert not missing, f"这些容差模式没有钥匙检查：{missing}"


def test_rt51_legit_grading_still_works():
    """**误拒视角**：正常作答一条都不许被新判据挡住。"""
    assert mp.grade_answer("2.53", "macro_yoy", 2.5)[0] == "hit"
    assert mp.grade_answer("3500.5", "index_level", 3500.0)[0] == "hit"
    assert mp.grade_answer("2026-06-30", "event_date", date(2026, 6, 30))[0] == "hit"
    assert mp.grade_answer("600000.SH, 000001.SZ", "code_set",
                           ["600000.SH", "000001.SZ"])[0] == "hit"
    assert mp.grade_answer("7", "count", 7)[0] == "hit"
