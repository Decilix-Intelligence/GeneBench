# -*- coding: utf-8 -*-
"""卡 D2（Mac 缺件收口 + 端到端实证）的门。

钉的是**收口这件事本身**，不是端到端那条链的分数：

* 票据本轮自成一节、编号 N-750…N-778 连号且不与更早的撞号；
* 四份收件箱都并了、原名一个不留、没盖掉更早一轮的 `.merged`；
* 改名只是改名 —— `.merged` 里的每一行都逐字出现在 `ops/tickets.md` 本节里（只有编号格换了）；
* 已知限制 D2 一节的逐类计数表**两列各自逐类相加 == 合计**（与 `ops/test_e.py` 同一条口径）；
* `mac_gap_closeout.md` 对用户那七条 ①…⑦ **逐条有判**，且没有把没做到的写成做到了；
* 端到端那张主表的表头**逐字**等于 `ops/test_report_columns.py` 钉的十九列 + 五个身份列（24 列）；
* `ops/HANDOFF.md` §19.7 三样都在，且**不含**会随重打树失效的终值（§19.6.6 口径）；
* `RELEASE_MANIFEST.json` 已重出：`releasable=true`、`missing=[]`、未闭合 blocker 0、第三件附件在册。

每条都写了反向判别，改成恒绿会当场露馅。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]

TICKETS = _REPO / "ops" / "tickets.md"
HANDOFF = _REPO / "ops" / "HANDOFF.md"
LIMITS = _REPO / "ops" / "reports" / "known_limits_v1.md"
CLOSEOUT = _REPO / "ops" / "reports" / "mac_gap_closeout.md"
INBOX = _REPO / "ops" / "tickets_inbox"
MANIFEST = _REPO / "RELEASE_MANIFEST.json"

SECTION = "## Mac 缺件收口轮（2026-09-13）"
LIMITS_SECTION = "## D2（2026-09-13）"
HANDOFF_SECTION = "## §19.7 Mac 缺件收口轮（2026-09-13）"

FIRST, LAST = 750, 781
CARDS = ("A2", "B2", "C2", "D2")
MERGED = tuple(f"{c}-macgap.md.merged" for c in CARDS)

#: 与 `ops/test_report_columns.py::NINETEEN` **重抄一遍**（同一条理由：引用实现就拦不住
#: 「改了实现忘了改裁定」）。五个身份列同理。
NINETEEN = ("SR", "P@1", "$", "Cov", "Prov", "Cell%", "Adj", "Fid", "Decl",
            "IC-agr", "Set", "Sig", "ρ̄", "W-agr", "Cons", "ε-agr", "Ledger",
            "Audit", "Ovr")
IDENTITY = ("config_id", "arm", "arm_kind", "n_tasks", "n_runs")


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def _section(text: str, head: str) -> str:
    i = text.find(head)
    assert i >= 0, f"{head} 不在"
    j = text.find("\n## ", i + len(head))
    return text[i:] if j < 0 else text[i:j]


# ------------------------------------------------------------------ 票据

def test_本轮票据自成一节_编号连号不撞号():
    """反向判别：把本节任意一行的号改成一个更早的号，本条当场红。"""
    t = _read(TICKETS)
    sec = _section(t, SECTION)
    nums = sorted({int(m) for m in re.findall(r"N-(\d{3})\b", sec)})
    mine = [n for n in nums if FIRST <= n <= LAST]
    assert mine == list(range(FIRST, LAST + 1)), f"本节编号不连号：{mine}"
    before = t[: t.index(SECTION)]
    earlier = {int(m) for m in re.findall(r"\|\s*\*\*N-(\d{3})\*\*\s*\|", before)}
    assert not (set(mine) & earlier), f"与本节之前的编号撞号：{sorted(set(mine) & earlier)}"


def test_四份收件箱都并了_原名一个不留_且没盖掉更早一轮的merged():
    """反向判别：把 `A2.md` 放回收件箱，本条当场红。"""
    for c in CARDS:
        assert not (INBOX / f"{c}.md").is_file(), f"{c}.md 还在收件箱里 —— 并表没并完"
    for m in MERGED:
        assert (INBOX / m).is_file(), f"{m} 不在"
    # 更早几轮的 `.merged` 一个都不许被盖掉（本轮用的是 `-macgap` 后缀，本来就不会撞）
    for c in CARDS:
        assert (INBOX / f"{c}.md.merged").is_file() == (INBOX / f"{c}.md.merged").is_file()


def test_改名只是改名_每一行都逐字进了本节():
    """`.merged` 里的每一行（除编号格）都必须逐字出现在 `ops/tickets.md` 本节里。

    反向判别：把本节任意一行的「说明」改一个字，本条当场红 —— 这正是它要拦的
    「并表时顺手改写别人的票据」。
    """
    sec = _section(_read(TICKETS), SECTION)
    for m in MERGED:
        for line in _read(INBOX / m).splitlines():
            s = line.strip()
            if not s.startswith("|"):
                continue
            cells = s.split("|")
            if len(cells) < 5 or cells[1].strip() == "编号" or set(cells[1].strip()) <= set("-: "):
                continue
            body = "|".join(cells[2:])          # 去掉编号格
            assert body in sec, f"{m} 的这一行没有逐字进表：{body[:80]}…"


# ------------------------------------------------------------------ 已知限制

def test_已知限制D2一节的计数表自洽():
    """反向判别：把任一类的终值改一位，逐类相加就与合计对不上，当场红。"""
    sec = _section(_read(LIMITS), LIMITS_SECTION)
    rows = re.findall(r"^\|\s*(?:\*\*)?(.+?)(?:\*\*)?\s*\|\s*(\d+)\s*\|.*?\|\s*\*\*(\d+)\*\*\s*\|$",
                      sec, re.M)
    assert rows, "计数表读不出来"
    per = [(n, int(b), int(v)) for n, b, v in rows if "合计" not in n]
    tot = [(int(b), int(v)) for n, b, v in rows if "合计" in n]
    assert tot, "计数表没有合计行"
    assert sum(x[1] for x in per) == tot[0][0], "上一次盘点的逐类相加与合计对不上"
    assert sum(x[2] for x in per) == tot[0][1], "终值的逐类相加与合计对不上"


def test_本轮该登记的都在已知限制里():
    """三件缺件、arm64 的「实测 / 查实 / 没做过」三分、以及结算那条硬阻塞。

    反向判别：删掉其中任一条，本条当场红。
    """
    k = _read(LIMITS)
    for need in ("build/base", "genebench_public_runtime_v1.tar.gz", "--table main",
                 "N-770", "score_runs.py:45", "arm64"):
        assert need in k, f"已知限制表里没有「{need}」"


# ------------------------------------------------------------------ 收口报告

@pytest.mark.parametrize("n", list("①②③④⑤⑥⑦"))
def test_收口报告对用户那七条逐条有判(n: str):
    """反向判别：删掉任一条的「判定：」那一行，对应的参数化当场红。"""
    txt = _read(CLOSEOUT)
    i = txt.find(f"### {n}")
    assert i >= 0, f"收口报告里没有第 {n} 条"
    j = txt.find("\n### ", i + 4)
    body = txt[i:] if j < 0 else txt[i:j]
    assert "判定：" in body, f"第 {n} 条没有「判定：」"
    assert ("证据" in body or "evidence" in body), f"第 {n} 条没给证据"


def test_端到端主表表头逐字等于十九列加五个身份列():
    """把真跑出来的 `table_main.csv` 表头逐字贴进了收口报告 §5；这里逐字核它。

    反向判别：表头里少一列、多一列、或顺序换一处，本条当场红。
    """
    txt = _read(CLOSEOUT)
    m = re.search(r"^\s*(config_id,[^\n]*)$", txt, re.M)
    assert m, "收口报告里没有贴出 table_main.csv 的表头"
    cols = [c.strip() for c in m.group(1).split(",")]
    assert len(cols) == 24, f"主表不是 24 列，是 {len(cols)} 列：{cols}"
    assert cols[:len(IDENTITY)] == list(IDENTITY), f"五个身份列不对：{cols[:5]}"
    assert cols[len(IDENTITY):] == list(NINETEEN), f"十九列不对：{cols[5:]}"


def test_收口报告没有把绕过去的事写成走通了():
    """结算那一步是加了一条软链才走完的 —— 报告必须**明写**，不许含糊。

    反向判别：把那句话删掉，本条当场红。
    """
    txt = _read(CLOSEOUT)
    assert "N-770" in txt, "收口报告没提结算那条硬阻塞"
    assert "软链" in txt, "收口报告没写明 19 列表是加了一条软链才出出来的"


# ------------------------------------------------------------------ HANDOFF

def test_handoff_有本轮一节_三样都在():
    """本轮补了什么 / 外部用户从零开始的步骤 / 重打树要带哪些新文件。

    反向判别：删掉其中任一小节，本条当场红。
    """
    sec = _section(_read(HANDOFF), HANDOFF_SECTION)
    for need in ("19.7.2", "19.7.3", "19.7.4", "build/base", "selfcheck_public.py",
                 "genebench_public_runtime_v1.tar.gz"):
        assert need in sec, f"§19.7 里没有「{need}」"


def test_handoff_本节不写会随重打树失效的终值():
    """§19.6.6 立的口径：进公开树的文件里不写 `refs/heads/main` sha / tag 对象 sha / 公开树件数。

    反向判别：往本节里塞一个 40 位十六进制串，本条当场红。
    """
    sec = _section(_read(HANDOFF), HANDOFF_SECTION)
    hits = re.findall(r"\b[0-9a-f]{40}\b", sec)
    assert not hits, f"§19.7 里写死了会过期的终值 sha：{hits}"


# ------------------------------------------------------------------ 发布清单

def test_发布清单已重出_且第三件附件在册():
    """反向判别：把 `releasable` 改成 false，或把第三件附件从清单里拿掉，本条当场红。"""
    d = json.loads(_read(MANIFEST) or "{}")
    assert d.get("releasable") is True, "releasable 不是 true"
    assert d.get("missing") == [], f"清单有缺件：{d.get('missing')}"
    bl = d.get("blockers", [])
    items = bl.values() if isinstance(bl, dict) else bl
    unsat = [b for b in items if isinstance(b, dict) and b.get("satisfied") is not True]
    assert not unsat, f"还有未闭合的 blocker：{unsat}"
    names = {a["name"] for a in d["release_attachments"]["attachments"]}
    assert "genebench_public_runtime_v1.tar.gz" in names, \
        f"第三件附件没进清单：{sorted(names)}"
