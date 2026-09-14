# -*- coding: utf-8 -*-
"""卡 6.3：`ops/specs/metrics_as_implemented_v1.md` 的**出处核对**。

这份文件的写法承诺是「每一行都指得出实现在哪个文件哪个函数」。承诺要有东西守着，
否则下一次重构 `scorer/` 时它会静默变成一份**看起来仍然准确**的过期文档 ——
与 `ops/test_p2_contract.py` 守 `integrations/P2_CONTRACT.md` 是同一件事，写法照抄那份。

四条判据：

1. 引用的每个 ``文件:行`` 的**文件存在**；
2. 行号**不越界**（不核内容 —— 行号会随提交漂几行，那与「从一开始就是编的」是两回事）；
3. 引用**足够多**（空壳文档同样能让 1、2 通过：没有引用就没有可核的东西）；
4. **「不判」的那些必须写明为什么** —— 逐条点名检查。第 4 条是这份文件的立卡理由：
   一张只列「判了什么」的表，读者会把没出现的指标读成「忘了写」，而不是「有意不判」。

**不 import `scorer/`**（红线 2：答案面不上执行面，本文件将来可能被带进执行面的测试集）。
一切都用正则从文本里读。
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DOC = REPO / "ops" / "specs" / "metrics_as_implemented_v1.md"

#: 与 `ops/test_p2_contract.py::citations` 同一条正则（含中文路径段）。
_CITE = re.compile(r"`([A-Za-z0-9_\-./一-鿿]+\.(?:py|md|json|yaml|yml|sh|jsonl)):(\d+)`")


def body() -> str:
    return DOC.read_text(encoding="utf-8")


def citations(text: str | None = None) -> list[tuple[str, int]]:
    return [(p, int(n)) for p, n in _CITE.findall(text if text is not None else body())]


# ------------------------------------------------------------------ 0. 存在性

def test_doc_exists_and_is_substantial():
    assert DOC.is_file(), f"{DOC} 不存在"
    t = body()
    assert len(t) > 8_000, "正文过短，多半被截断或还没写完"
    for section in ("## 1. Table A 十项", "## 2. Table B 各阶段",
                    "## 3. 一致性署名层", "## 4. 软校验（L2）", "## 5. 一页版"):
        assert section in t, f"缺章节 {section!r}"


# ------------------------------------------------------------------ 1. 出处

def test_every_citation_file_exists():
    cites = citations()
    assert len(cites) >= 40, (
        f"只解析到 {len(cites)} 条 `文件:行` 引用 —— 这份文件承诺「每行都指得出实现」，"
        f"太少说明大段正文没有出处，或者引用格式漂了")
    missing = sorted({p for p, _ in cites if not (REPO / p).is_file()})
    assert not missing, f"引用了不存在的文件：{missing}"


def test_citation_line_numbers_are_in_range():
    """**不核内容，只核没有指到文件之外。**

    指到文件之外说明那次引用从一开始就是编的（或文件被大幅删减），
    这与「行号漂了几行」是两回事。
    """
    lengths: dict[str, int] = {}
    bad: list[str] = []
    for rel, line in citations():
        f = REPO / rel
        if not f.is_file():
            continue
        n = lengths.setdefault(rel, len(f.read_text(encoding="utf-8").splitlines()))
        if line > n:
            bad.append(f"{rel}:{line}（该文件只有 {n} 行）")
    assert not bad, f"引用的行号超出文件范围：{sorted(set(bad))}"


def test_the_citation_checker_would_catch_a_fabricated_one():
    """**判别力**：换一份编造的引用，上面两条必须能抓到。

    没有这一条的话，「正则匹配不到任何东西」也会让前两条全绿。
    """
    fake = "见 `scorer/l3.py:999999` 与 `scorer/不存在的文件.py:1`。"
    got = citations(fake)
    assert len(got) == 2, f"正则漏抓：{got}"
    assert not (REPO / "scorer/不存在的文件.py").is_file()
    n = len((REPO / "scorer" / "l3.py").read_text(encoding="utf-8").splitlines())
    assert 999999 > n, "构造的越界行号已经不越界了 —— 换一个更大的数"


def test_citations_actually_point_at_the_scorer():
    """出处要落在**实现**上，不是落在别的文档上。"""
    files = {p for p, _ in citations()}
    for must in ("scorer/l3.py", "scorer/report.py", "scorer/gate.py", "scorer/score_run.py"):
        assert must in files, f"一条 `{must}:行` 的引用都没有 —— 这份文件是讲实现的"


# ------------------------------------------------------------------ 2. 「不判」必须写明为什么

#: 逐条点名：**这些指标今天不判或不出，文件里必须提到它们**。
#: 只查「提到了」不查措辞 —— 措辞会改，而「漏掉一整个指标」是这条要拦的事。
NOT_JUDGED = (
    ("positive_ratio", "S4 的 IC 族里唯一标定失败的那个（implausible_stop_and_report）"),
    ("ci_low", "qlib 口径不产 bootstrap 区间，双实现对构不成"),
    ("TE", "S6 的跟踪误差要收益率序列，v1 的 S6 产物里没有（N-126）"),
    ("Slip", "S8 的滑点只报不判，且两份实现符号相反（N-127 / N-383）"),
    ("Fill", "同上，S8 题面没规定下哪些单"),
    ("Checkpoint", "v1 没有 Chain 赛道"),
    ("Repro", "同一 run 重跑两次，预算不允许；且产物本来就不逐字节可复现"),
    ("Decay", "窗口太短，半衰期拟合没有统计意义"),
    ("CBC", "要同题跨后端成对的真跑"),
    ("search_count", "字段预留了但 scorer 一处都没读"),
)


def test_every_unjudged_metric_is_named_with_a_reason():
    t = body()
    missing = [f"{k}（{why}）" for k, why in NOT_JUDGED if k not in t]
    assert not missing, (
        "下面这些今天不判 / 不出的指标在文件里一次都没出现 —— "
        "读者会把没出现读成「忘了写」而不是「有意不判」：\n  " + "\n  ".join(missing))


def test_the_three_states_are_defined_before_they_are_used():
    """三态（判 / 只报 / 不出）必须有定义，否则表里的字读不出分寸。"""
    t = body()
    for token in ("**判** =", "**只报** =", "**不出** ="):
        assert token in t, f"三态里缺 {token!r} 的定义"


def test_l2_is_declared_absent_not_omitted():
    """L2 软校验 v1 一处都没启用 —— 这件事必须**明说**，不能靠读者自己数出来。

    它决定了主表上没有任何一格来自 LLM 裁判，也决定了 κ 无从谈起。
    """
    t = body()
    assert "L2" in t and "一处都没启用" in t, "L2 未启用这件事没写明"
    assert "κ" in t, "κ（裁判一致率）没被提到 —— 它是 L2 缺席的直接后果"


def test_gate_semantics_is_stated_as_gate_not_penalty():
    """闸门语义（invalid 而非低分）是 v1 计分制度的地基，必须在文件里说清。"""
    t = body()
    assert "invalid" in t, "没提 invalid"
    assert "扣分" in t, "没有把闸门与扣分制对照 —— 那正是对接决定 §1.1 的论点"
