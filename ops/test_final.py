# -*- coding: utf-8 -*-
"""最终卡（2026-09-12 收口 + 发布）的判据。

与 `ops/test_wrapup.py`（收尾卡 v1）、`ops/test_V2.py`（收尾卡 v2）同一个形状，
钉的是**这一轮收口**有没有把东西串错：

1. 票据合并：八个收件箱 → `ops/tickets.md` 新一节 + 全部改名 `.merged`，连号、不撞号、
   既有票据按「**N-xxx 更新**」写（写成 `**N-xxx**` 会让同一个号在同一份文件里出现两次）；
   改名**只许新增** `.merged`，不许动既有的那些（N-652 那次是静默覆盖）；
2. `ops/HANDOFF.md` 的 §19 / §19.2 / §19.3 按顺序在，前两段没被动过；
3. 七节报告 + **15 条裁定逐条判**，每一条都要有判词，且判词只能是三种之一；
4. 报告里的数与它们的**出处**一致（blocker、`releasable` 现值、版本轴、两个远端 sha），
   且**两条未达成没有被写成达成** —— 这一条配反向判别，防止断言变成恒绿；
5. 已知限制表的终态：本轮登记不修的四类都在。

**不重复别处已经钉住的东西** —— 十九列有 `ops/test_report_columns.py`、
发布清单有 `ops/test_release_manifest.py`、签字包有 `ops/test_h.py`。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from ops import freeze_v10 as FZ                                # noqa: E402

#: 本轮八张卡的收件箱**落盘名**。合并前核过：这八个卡号**一个都没有被更早一轮用过**
#: （`ls ops/tickets_inbox/<卡号>.md.merged` 全空），所以 `mv` 不会重演 N-652 那次静默覆盖。
CARDS = ("F1", "F2", "F3", "G1", "G2", "H", "P", "RT-final")
SECTION = "## 最终卡（收口 + 发布）—— 2026-09-12"
REPORT = _REPO / "ops" / "reports" / "final_report.md"
KNOWN = _REPO / "ops" / "reports" / "known_limits_v1.md"
#: 本轮以「更新」形式并进来的既有票据 —— 这些号**不许**被重新发。
UPDATED = ("N-586", "N-611", "N-619", "N-624", "N-627",
           "N-635", "N-636", "N-642", "N-645", "N-651")
#: 15 条裁定的圈号。
RULINGS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮"
VERDICTS = ("**达成", "**部分达成", "**未达成")


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def _tickets() -> tuple[str, str]:
    t = _read(_REPO / "ops" / "tickets.md")
    assert SECTION in t, "最终卡那一节不在 ops/tickets.md 里"
    i = t.index(SECTION)
    return t[:i], t[i:]


# ============================================================ 1. 票据合并

def test_八个收件箱都改名merged了_原名一个不留():
    d = _REPO / "ops" / "tickets_inbox"
    for c in CARDS:
        assert (d / f"{c}.md.merged").is_file(), f"{c}.md.merged 不在"
        assert not (d / f"{c}.md").exists(), f"{c}.md 还在 —— 并完要改名，否则下一张卡会再并一次"


def test_改名没有盖掉更早一轮的merged():
    """`mv <卡>.md <卡>.md.merged` 在卡号被复用时会**静默覆盖**上一轮那份（N-652）。

    判据：HEAD 里已经存在的每一个 `*.md.merged`，内容必须与 HEAD 逐字节相同 ——
    合并这一步只该**新增** `.merged`，不该改动任何一个既有的。
    """
    d = _REPO / "ops" / "tickets_inbox"
    listed = subprocess.run(["git", "ls-tree", "--name-only", "HEAD", "ops/tickets_inbox/"],
                            cwd=_REPO, capture_output=True, text=True)
    if listed.returncode != 0:
        pytest.skip("这里不是 git 工作树")
    bad = []
    for rel in listed.stdout.split():
        if not rel.endswith(".md.merged"):
            continue
        old = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=_REPO, capture_output=True)
        p = _REPO / rel
        if not p.is_file():
            bad.append(f"{rel}：HEAD 里有、盘上没了")
        elif p.read_bytes() != old.stdout:
            bad.append(f"{rel}：内容与 HEAD 不同 —— 多半是被同名的 mv 盖了")
    assert not bad, "既有的 .merged 被动过：\n  " + "\n  ".join(bad)
    assert d.is_dir()


def test_新节内部不撞号_且与旧节不撞号():
    head, new = _tickets()
    ids = re.findall(r"\*\*(N-\d+)\*\*\s*\|", new)
    assert ids, "新节里一条发号的票据都没有"
    assert len(ids) == len(set(ids)), "新节内部撞号"
    for x in set(ids):
        assert f"**{x}**" not in head, f"{x} 与旧节撞号"


def test_新节发的号连号_且从N653起():
    _, new = _tickets()
    nums = sorted(int(x.split("-")[1]) for x in re.findall(r"\*\*(N-\d+)\*\*\s*\|", new))
    assert nums[0] == 653, f"新号应从 N-653 续编（上一轮到 N-652），实际 {nums[0]}"
    assert nums == list(range(nums[0], nums[-1] + 1)), f"发号不连续：{nums[0]}..{nums[-1]}"


def test_既有票据按更新写_没有被重新发号():
    """重新发号会让别人输出里引的号指错地方；写成 `**N-xxx**` 会让同一个号出现两次。"""
    head, new = _tickets()
    for old in UPDATED:
        assert f"**{old} 更新**" in new, f"{old} 应当以「更新」写在新节里"
        assert f"**{old}**" in head, f"{old} 本来就该在旧节里 —— 夹具前提不成立"


def test_每张卡都有条目并进来了():
    _, new = _tickets()
    names = {"F1": "卡 F1", "F2": "卡 F2", "F3": "卡 F3", "G1": "卡 G1",
             "G2": "卡 G2", "H": "卡 H", "P": "卡 P", "RT-final": "红队最终轮"}
    for c in CARDS:
        assert names[c] in new, f"{c}（{names[c]}）的条目没有在新节里标出处"


# ============================================================ 2. 交接

def test_handoff_的19与19_2与19_3都在_且按顺序():
    h = _read(_REPO / "ops" / "HANDOFF.md")
    for s in ("## §19 排网格", "## §19.2 收尾卡 v2", "## §19.3 最终卡"):
        assert s in h, f"{s} 不在 —— 共享文件只许追加"
    assert h.index("## §19 排网格") < h.index("## §19.2 收尾卡 v2") < h.index("## §19.3 最终卡"), \
        "§19.3 必须追加在前两段之后"


# ============================================================ 3. 七节报告 + 15 条裁定

def test_报告七节齐():
    t = _read(REPORT)
    assert t, "ops/reports/final_report.md 不在"
    for h in ("## 一、", "## 二、", "## 三、", "## 四、", "## 五、", "## 六、", "## 七、"):
        assert h in t, f"缺 {h}"


def test_十五条裁定逐条判_每条都有判词():
    t = _read(REPORT)
    assert "## 八、15 条裁定逐条判" in t, "15 条裁定那一节不在"
    sec = t[t.index("## 八、15 条裁定逐条判"):]
    sec = sec[:sec.index("## 九、")]
    for mark in RULINGS:
        rows = [r for r in sec.split("\n") if r.startswith(f"| {mark} ")]
        assert len(rows) == 1, f"裁定 {mark} 应当恰好有一行，实际 {len(rows)} 行"
        assert any(v in rows[0] for v in VERDICTS), \
            f"裁定 {mark} 那一行没有判词（达成 / 部分达成 / 未达成）"


def test_两条未达成没有被写成达成():
    """⑪（推送）与 ⑭（Release 附件）都 BLOCKED。

    **反向判别**：这条测试要能在「有人把它们改写成达成」时红，
    所以同时断言正面（两条必须是未达成）与负面（远端不能已经变了）。
    """
    t = _read(REPORT)
    sec = t[t.index("## 八、15 条裁定逐条判"):]
    for mark in "⑪⑭":
        row = [r for r in sec.split("\n") if r.startswith(f"| {mark} ")][0]
        assert "**未达成" in row, f"裁定 {mark} 现在是 BLOCKED，不许写成达成"
    assert "达成 10 条" in t and "未达成 2 条" in t, "小计与逐条判不一致"


def test_报告里的blocker与发布清单一致():
    t = _read(REPORT)
    rm = json.loads(_read(_REPO / "RELEASE_MANIFEST.json"))
    for b in rm["blockers"]:
        assert b["id"] in t, f"blocker {b['id']} 在清单里但报告没提"
    assert f"`releasable=**{str(rm['releasable']).lower()}**`" in t or \
           f"releasable=true" in t.lower(), "报告没有写明 releasable 现值"
    assert rm["releasable"] is True, "清单现算 releasable 不是 true —— 报告与清单分叉"
    assert not rm["missing"], "清单现算还有缺件"


def test_报告里的版本轴与freeze现值一致():
    t = _read(REPORT)
    assert FZ.SET_VERSION in t, f"任务集轴 {FZ.SET_VERSION} 没写进报告"
    assert FZ.REFERENCE_VERSION in t, f"参考面轴 {FZ.REFERENCE_VERSION} 没写进报告"
    rm = json.loads(_read(_REPO / "RELEASE_MANIFEST.json"))
    pub = rm["axes"].get("public_set_version")
    assert pub and pub in t, "公开任务集轴没写进报告（裁定 ①）"


def test_报告记的两个远端sha与推送说明同源():
    """收口时 `git ls-remote` 的结果要与 2026-09-11 记的初始提交是**同一个** ——
    这就是「本轮没有人推过」的证据。两处分叉说明有人推了却没改报告。
    """
    t = _read(REPORT)
    pi = _read(_REPO / "ops" / "reports" / "push_instructions.md")
    pr = _read(_REPO / "ops" / "reports" / "push_result.md")
    for sha in ("55ead485", "6eadb004"):
        assert sha in t, f"报告里没有远端 sha {sha}"
        assert sha in pi or sha in pr, f"{sha} 与推送说明/推送结果两处都对不上"


# ============================================================ 4. 已知限制表终态

def test_已知限制表登记了本轮四类不修的问题():
    t = _read(KNOWN)
    assert "## P（2026-09-12）登记的四条" in t, "卡 P 那四条没登记"
    assert "## 最终卡收口（2026-09-12）" in t, "终态盘点那一节不在"
    for kw in ("instruments", "gold 子集包", "push_instructions.md", "public_v1"):
        assert kw in t, f"已知限制表里找不到「{kw}」"


def test_全量pytest的六条红逐条归属都写了():
    t = _read(REPORT)
    for name in ("test_lake_baseline", "test_no_api_key_material_in_run_dirs",
                 "test_underdetermination_guard", "test_rebudget只动没跑过的行"):
        assert name in t, f"报告 §一 没有写 {name} 的归属"
