"""卡 E（发布收尾：票据合并 / HANDOFF / 六节短报告 / 已知限制终态）的门。

这些断言钉的是**收口这件事本身**：票据连号不撞号、收件箱改名没盖掉更早一轮的、
报告六节齐且六条裁定逐条有判、已知限制的计数表自洽、以及报告里引的几个数
与权威出处（`RELEASE_MANIFEST.json` / `push_result.md`）**同源**。

每条都留了反向判别（写在各自的 docstring 里）：判据被改成恒绿的话，
反向判别那一步会当场红。
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]

TICKETS = _REPO / "ops" / "tickets.md"
HANDOFF = _REPO / "ops" / "HANDOFF.md"
REPORT = _REPO / "ops" / "reports" / "publish_report.md"
LIMITS = _REPO / "ops" / "reports" / "known_limits_v1.md"
INBOX = _REPO / "ops" / "tickets_inbox"
MANIFEST = _REPO / "RELEASE_MANIFEST.json"
PUSH = _REPO / "ops" / "reports" / "push_result.md"

SECTION = "## 发布收尾卡（2026-09-12）"
#: 本轮四张卡写在收件箱里的原名 —— 并完这些名字底下不许再有 `.md`。
RAW = ("A", "B", "C", "D")
#: 本轮改名的落点。**不是** `<卡>.md.merged` —— 那几个名字被收尾卡 v2 占了（N-725）。
MERGED = tuple(f"{c}-publish.md.merged" for c in RAW)

FIRST, LAST = 703, 726


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def _section(text: str, head: str) -> str:
    i = text.find(head)
    assert i >= 0, f"{head} 不在"
    j = text.find("\n## ", i + len(head))
    return text[i:] if j < 0 else text[i:j]


# --------------------------------------------------------------------------- 票据

def test_本轮的票据自成一节_且编号连号不撞号():
    """反向判别：把本节任意一行的 `N-71x` 改成一个更早的号，本条当场红。"""
    t = _read(TICKETS)
    sec = _section(t, SECTION)
    nums = sorted({int(m) for m in re.findall(r"N-(\d{3})\b", sec)})
    mine = [n for n in nums if n >= FIRST]
    assert mine == list(range(FIRST, LAST + 1)), f"本节编号不连号：{mine}"
    before = t[: t.index(SECTION)]
    earlier = {int(m) for m in re.findall(r"N-(\d{3})\b", before)}
    assert not (set(mine) & earlier), f"与本节之前的编号撞号：{sorted(set(mine) & earlier)}"


def test_四个收件箱都并了_原名一个不留_且没盖掉更早一轮的merged():
    """N-652 那次事故的形状：卡号被复用时 `mv A.md A.md.merged` 会**静默覆盖**上一轮那份。

    反向判别：把本轮某一份改名成 `A.md.merged`，`test_改名没有盖掉更早一轮的merged`
    （`ops/test_V2.py`）会当场红 —— 那条测试与本条是同一道门的两面。
    """
    for name in MERGED:
        assert (INBOX / name).is_file(), f"{name} 不在 —— 并完要改名，否则下一张卡会再并一次"
    for c in RAW:
        assert not (INBOX / f"{c}.md").exists(), f"{c}.md 还在"
    for c in ("A", "B", "C"):
        old = INBOX / f"{c}.md.merged"
        assert old.is_file(), f"{c}.md.merged（收尾卡 v2 那一轮的）不该消失"


def test_改名只是改名_内容与合并时读的那一份逐字节相同():
    """反向判别：往任一 `*-publish.md.merged` 里加一行，本条当场红（与 HEAD 比）。"""
    listed = subprocess.run(["git", "ls-tree", "--name-only", "HEAD", "ops/tickets_inbox/"],
                            cwd=_REPO, capture_output=True, text=True)
    if listed.returncode != 0:
        pytest.skip("这里不是 git 工作树")
    names = set(listed.stdout.split())
    for c, name in zip(RAW, MERGED):
        rel_new = f"ops/tickets_inbox/{name}"
        rel_old = f"ops/tickets_inbox/{c}.md"
        src = rel_new if rel_new in names else rel_old
        if src not in names:
            pytest.skip(f"{c} 的收件箱还没进 HEAD")
        blob = subprocess.run(["git", "show", f"HEAD:{src}"], cwd=_REPO, capture_output=True)
        assert blob.returncode == 0
        assert (INBOX / name).read_bytes() == blob.stdout, f"{name} 与 HEAD 里那份不同"


def test_每一条票据都留了出处():
    """合并规则：重复条目合并、**出处列在说明末尾**。反向判别：删掉某一行的「出处：」当场红。"""
    sec = _section(_read(TICKETS), SECTION)
    rows = [r for r in sec.splitlines() if r.startswith("| **N-")]
    assert len(rows) >= 24, f"本节只有 {len(rows)} 行"
    bad = [r.split("|")[1].strip() for r in rows if "出处：" not in r]
    assert bad == [], f"这些行没写出处：{bad}"


# --------------------------------------------------------------------------- HANDOFF

def test_handoff_有本轮一节_三样都在():
    """任务书要的三样：本版是什么 / 六条裁定速判 / 接手先跑的命令。"""
    h = _read(HANDOFF)
    sec = _section(h, "## §19.5 发布收尾卡")
    for need in ("本版是什么", "六条裁定速判", "接手先跑"):
        assert need in sec, f"§19.5 缺「{need}」"
    assert sec.count("ssh finance01-ts") >= 3, "接手要跑的命令不足三条"


def test_handoff_与报告记的远端sha是同一个():
    """反向判别：把 HANDOFF 里那个 sha 改一个字符，本条当场红。"""
    want = "bd0513a47d1ad273d4cc21fdbdfb5604b2487645"
    for p in (HANDOFF, REPORT):
        assert want in _read(p), f"{p.name} 里没有远端终值 sha"
    assert "6ce7664e84e467c39d11bb4ec88209bdae6a7c92" in _read(REPORT), "GeneQuant 的远端值不在报告里"


# --------------------------------------------------------------------------- 报告

def test_报告六节齐():
    r = _read(REPORT)
    for head in ("## 一、", "## 二、", "## 三、", "## 四、", "## 五、", "## 六、"):
        assert head in r, f"报告缺 {head}"


def test_六条裁定逐条有判_而且未达成的那条没被写成达成():
    """反向判别：把 ③ 那一行的「未达成」改成「达成」，本条当场红 ——
    判据不是「出现了六行」，而是「③ 必须仍标着未达成，且报告里仍有 BLOCKED 一节」。
    """
    r = _read(REPORT)
    sec = _section(r, "## 二、")
    rows = [x for x in sec.splitlines() if x.startswith("| ①") or x.startswith("| ②")
            or x.startswith("| ③") or x.startswith("| ④") or x.startswith("| ⑤") or x.startswith("| ⑥")]
    assert len(rows) == 6, f"裁定表只有 {len(rows)} 行"
    for row in rows:
        assert "达成" in row, f"这一条没给判：{row[:40]}"
    third = [x for x in rows if x.startswith("| ③")][0]
    assert "未达成" in third, "③ 还没做成（Release 没建），不许写成达成"
    blocked = _section(r, "## 三、BLOCKED")
    assert "contents=write" in blocked and "403" in blocked, "BLOCKED 一节要写出当下的拦路原因"


def test_报告引的附件数值与清单同源():
    """反向判别：把报告里任一个 `bytes` 或 sha 改一位，本条当场红。"""
    m = json.loads(_read(MANIFEST))
    atts = m["release_attachments"]["attachments"]
    assert atts, "清单里没有附件登记"
    r = _read(REPORT)
    for a in atts:
        assert a["sha256"][:16] in r, f"{a['name']} 的 sha 不在报告里"
        assert f"{a['bytes']:,}" in r, f"{a['name']} 的字节数不在报告里"


def test_附件还没上传时_报告必须把它记成blocked():
    """双向门：`download_url` 一旦回填，报告里那句「一个 Release 都没有」就必须改掉；
    反过来，只要还有空的 `download_url`，报告里就必须有 BLOCKED 一节。
    """
    m = json.loads(_read(MANIFEST))
    atts = m["release_attachments"]["attachments"]
    pending = [a["name"] for a in atts if not a.get("download_url")]
    r = _read(REPORT)
    if pending:
        assert "## 三、BLOCKED" in r, f"还有 {len(pending)} 件没上传，报告必须记 BLOCKED"
        assert "附件清单为空" in r, "附件清单为空这件事要在报告里说出来"
    else:
        assert "附件清单为空" not in r, "附件已上传，报告里那句话要改掉"


def test_报告的全量数字与日志同源_不是手写的():
    """反向判别：把报告里的 passed 数改一位，本条与日志对不上当场红。
    日志不在（换了机器 / scratch 清过）时跳过，不假装绿。
    """
    log = Path("/data/shared/genebench/scratch/E/pytest_full.log")
    if not log.is_file():
        pytest.skip("本轮的全量日志不在这台机器上")
    tail = log.read_text(encoding="utf-8", errors="replace")[-4000:]
    m = re.search(r"(\d+) failed, (\d+) passed", tail)
    assert m, "日志里没有 pytest 的汇总行"
    failed, passed = m.group(1), m.group(2)
    r = _read(REPORT)
    assert f"{passed} passed" in r, f"报告写的 passed 与日志（{passed}）对不上"
    assert f"{failed} failed" in r, f"报告写的 failed 与日志（{failed}）对不上"


# --------------------------------------------------------------------------- 已知限制

def test_已知限制的终态计数表自洽():
    """反向判别：把任一类的终值改一位，逐类相加就与合计对不上，当场红。"""
    sec = _section(_read(LIMITS), "## 发布收尾卡（2026-09-12）：这张表的**终态**")
    rows = re.findall(r"^\|\s*(?:\*\*)?(.+?)(?:\*\*)?\s*\|\s*(\d+)\s*\|.*?\|\s*\*\*(\d+)\*\*\s*\|$",
                      sec, re.M)
    assert rows, "计数表读不出来"
    per = [(name, int(before), int(now)) for name, before, now in rows if "合计" not in name]
    total = [(int(b), int(n)) for name, b, n in rows if "合计" in name]
    assert total, "计数表没有合计行"
    assert sum(x[1] for x in per) == total[0][0], "上一次盘点的逐类相加与合计对不上"
    assert sum(x[2] for x in per) == total[0][1], "终值的逐类相加与合计对不上"


def test_本轮该登记的三类都在已知限制里():
    """裁定 ①/⑥ 点名要登记的：csi1000 不入公开包、18 个公开读数跑在旧 provider 上、
    以及本卡之外发现的一切（这里抽查卡 B 交接的两条 `_ledger` 与本卡量到的那条红）。
    反向判别：删掉其中任一条，本条当场红。
    """
    k = _read(LIMITS)
    for need in ("csi1000", "18 个公开 run", "_ledger.jsonl",
                 "test_gold_only_lives_under_reference_or_snapshots", "sim_factory"):
        assert need in k, f"已知限制表里没有「{need}」"


def test_签字包是只读归档_本卡一个字节没改():
    """反向判别：改动签字包里任何一件，`git status --porcelain` 就会列出来，本条当场红。"""
    st = subprocess.run(["git", "status", "--porcelain", "ops/reports/signed/"],
                        cwd=_REPO, capture_output=True, text=True)
    if st.returncode != 0:
        pytest.skip("这里不是 git 工作树")
    assert st.stdout.strip() == "", f"签字包被动过：\n{st.stdout}"
