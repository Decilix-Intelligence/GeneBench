# -*- coding: utf-8 -*-
"""收尾卡（2026-09-10）的判据。

钉三件事，每一件都**从源头现算再和落盘的文字比**，不写死数字：
1. 票据合并没有丢东西、没有撞号（八个收件箱 → `ops/tickets.md` 一节 + 改名 `.merged`）；
2. 签字包是**这一版**的（版本轴与 `ops/freeze_v10.py` 现值一致）、逐件 sha256 对得上、0400、
   清单声明了却不存在的件如实进 `declared_but_missing`；
3. 六节报告里的数与它们的**出处**一致（发布件 blocker、实例数、适配赛道三个数）。

**不重复别处已经钉住的东西** —— 实例层有 `ops/test_instances.py`、适配赛道有 `ops/test_y2.py`、
发布清单有 `ops/test_release_manifest.py`。这里只钉「收口这一步有没有把它们串错」。
"""
from __future__ import annotations

import hashlib
import json
import re
import stat
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from ops import archive_signoff as AS                          # noqa: E402
from ops import freeze_v10 as FZ                               # noqa: E402

CARDS = ("W1", "W2", "W3", "X1", "Y1", "Y1b", "Y2", "W.rt")
SECTION = "## 2026-09-10 收尾卡（可发布 + 实例扩张）"
REPORT = _REPO / "ops" / "reports" / "wrapup_report.md"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def _tickets() -> tuple[str, str]:
    t = _read(_REPO / "ops" / "tickets.md")
    assert SECTION in t, "收尾卡那一节不在 ops/tickets.md 里"
    i = t.index(SECTION)
    return t[:i], t[i:]


def _signed_dir() -> Path:
    ts = json.loads((_REPO / "ops" / "manifests" / "v1.0-smoke.json").read_text(encoding="utf-8"))
    rf = json.loads((_REPO / "ops" / "manifests" / "v1.0-smoke.reference.json").read_text(encoding="utf-8"))
    return AS.ARCHIVE / f"v{ts['set_version']}_{rf['reference_version']}"


# ============================================================ 1. 票据合并

def test_八个收件箱都改名merged了_原名一个不留():
    d = _REPO / "ops" / "tickets_inbox"
    for c in CARDS:
        assert (d / f"{c}.md.merged").is_file(), f"{c}.md.merged 不在"
        assert not (d / f"{c}.md").exists(), f"{c}.md 还在 —— 并完要改名，否则下一张卡会再并一次"


def test_新发的号连号_不与旧节撞号():
    head, new = _tickets()
    ids = re.findall(r"\*\*(N-\d+)\*\*\s*\|", new)
    assert ids, "新节里一条发号的票据都没有"
    assert len(ids) == len(set(ids)), "新节内部撞号"
    nums = sorted(int(x.split("-")[1]) for x in ids)
    assert nums == list(range(nums[0], nums[-1] + 1)), f"发号不连续：{nums[0]}..{nums[-1]}"
    for x in set(ids):
        assert f"**{x}**" not in head, f"{x} 与旧节撞号"


def test_新节从旧节的最大号续编():
    head, new = _tickets()
    old_max = max(int(m) for m in re.findall(r"N-(\d+)", head))
    new_min = min(int(x.split("-")[1]) for x in re.findall(r"\*\*(N-\d+)\*\*\s*\|", new))
    assert new_min == old_max + 1, f"旧节最大 N-{old_max}，新节从 N-{new_min} 起 —— 要紧接着续"


def test_每张卡都有条目并进来了():
    _, new = _tickets()
    for c in CARDS:
        assert f"出处：{c}" in new or f"出处：{c}、" in new or f"出处：{c} " in new, \
            f"{c} 的条目没有在新节里标出处"


def test_既有编号按更新写_没有被重新发号():
    """N-127 / N-383 这些是既有票据，合并时只能「更新」，重新发号会让历史指错地方。"""
    head, new = _tickets()
    for old in ("N-127", "N-128", "N-130", "N-348", "N-383", "N-384", "N-409"):
        assert f"**{old} 更新**" in new, f"{old} 应当以「更新」写在新节里"
        assert old in head, f"{old} 本来就该在旧节里 —— 夹具前提不成立"


def test_handoff_的两段都在_W1那段没被动():
    h = _read(_REPO / "ops" / "HANDOFF.md")
    assert "## §18 W1（2026-09-10）" in h, "W1 的 §18 不见了 —— 共享文件只许追加"
    assert "## §18.2 收尾卡（2026-09-10 收口）" in h, "收尾卡的 §18.2 不在"
    assert h.index("## §18 W1") < h.index("## §18.2 收尾卡"), "§18.2 必须追加在 W1 那一段之后"


# ============================================================ 2. 签字包

def test_签字包是这一版的_版本轴与冻结现值一致():
    d = _signed_dir()
    assert d.is_dir(), f"{d} 不在 —— 签字包没重出"
    m = json.loads((d / "MANIFEST.json").read_text(encoding="utf-8"))
    assert m["set_version"] == FZ.SET_VERSION
    assert m["reference_version"] == FZ.REFERENCE_VERSION
    assert len(m["set_root"]) == 64 and len(m["reference_root"]) == 64


def test_签字包逐件sha256对得上_且都是0400():
    d = _signed_dir()
    m = json.loads((d / "MANIFEST.json").read_text(encoding="utf-8"))
    assert m["files"], "一个文件都没归档"
    for rel, sha in m["files"].items():
        p = d / AS._dst_name(rel)
        assert p.is_file(), f"{rel} 在 MANIFEST 里但盘上没有"
        assert hashlib.sha256(p.read_bytes()).hexdigest() == sha, f"{rel} 的 sha 对不上"
        assert stat.S_IMODE(p.stat().st_mode) == 0o400, f"{rel} 不是 0400"
    assert stat.S_IMODE((d / "MANIFEST.json").stat().st_mode) == 0o400


def test_清单声明了却不存在的件_如实进declared_but_missing():
    d = _signed_dir()
    m = json.loads((d / "MANIFEST.json").read_text(encoding="utf-8"))
    # 卡 H：签字包按通道出两份，这份是**私有**那一份 —— 按私有通道的清单核。
    declared = list(AS.items_for("private")) + list(AS.ROOT_ITEMS)
    assert set(m["files"]) | set(m["declared_but_missing"]) == set(declared), \
        "归档件 + 缺件 ≠ 清单声明的件 —— 有件被悄悄跳过了"
    for rel in m["declared_but_missing"]:
        base = _REPO / "ops" / "reports" / rel if rel in AS.ITEMS else _REPO / rel
        assert not base.is_file(), f"{rel} 明明在，不该记成缺件"


def test_同名冲突断言还在_且这一版没有同名():
    names = [AS._dst_name(r) for r in AS.ITEMS] + [AS._dst_name(r) for r in AS.ROOT_ITEMS]
    assert len(names) == len(set(names)), "清单里有两件会落成同一个文件名"
    src = (_REPO / "ops" / "archive_signoff.py").read_text(encoding="utf-8")
    assert "归档文件名冲突" in src, "同名冲突那条断言被删了"


def test_本轮扩的十一件都在清单里():
    added = ("probe_matrix_instances.md", "probe_run_instances.cumulative.json",
             "public/probe_matrix_instances.md", "public/probe_run_instances.cumulative.json",
             "adapt/table.csv", "adapt/table.tex", "adapt/summary.md",
             "adapt/oracle_matrix.md", "adapt/records.json",
             "public/instruments_rebuild.md", "public/factor_library_recovery.md")
    for rel in added:
        assert rel in AS.ITEMS, f"{rel} 不在 ITEMS 里"
    # 上一版就在清单里的四类，别被这次扩清单挤掉
    for rel in ("known_limits_v1.md", "m6_public/v1_0_readiness_public.md",
                "m6_public/validator_validation_v1_public.md"):
        assert rel in AS.ITEMS, rel
    for rel in ("RELEASE_MANIFEST.json", "VERSIONS.md"):
        assert rel in AS.ROOT_ITEMS, rel


# ============================================================ 3. 六节报告与它的出处

def test_报告七节齐():
    t = _read(REPORT)
    assert t, "ops/reports/wrapup_report.md 不在"
    for h in ("## 一、", "## 二、", "## 三、", "## 四、", "## 五、", "## 六、", "## 七、"):
        assert h in t, f"缺 {h}"


def test_报告里的blocker与发布清单一致():
    t = _read(REPORT)
    rm = json.loads((_REPO / "RELEASE_MANIFEST.json").read_text(encoding="utf-8"))
    for b in rm["blockers"]:
        assert b["id"] in t, f"blocker {b['id']} 在清单里但报告没提"
    # 正文是 2026-09-10 那天的记录 —— 那天 `releasable=false`，**不要改它**。
    assert "releasable=false" in t.lower(), "正文里当天的 releasable=false 被改掉了"
    # 但清单现算已经不是那天的值时，报告必须**在别处写明现值**（§〇 现值更新），
    # 否则读者会把当天的 false 当成今天的结论。
    if rm["releasable"]:
        assert f"`releasable={str(rm['releasable']).lower()}`" in t, \
            "发布清单现算 releasable=true，而报告里没有一处写明现值 —— 补 §〇 现值更新"


def test_报告里的实例数与冻结清单一致():
    t = _read(REPORT)
    ts = json.loads((_REPO / "ops" / "manifests" / "v1.0-smoke.json").read_text(encoding="utf-8"))
    c = ts["instances"]["counts"]
    assert f"{c['instances']} 实例" in t, f"报告里没有「{c['instances']} 实例」"
    assert f"{c['bases']} 模板" in t, f"报告里没有「{c['bases']} 模板」"


def test_报告里的适配赛道三个数与摘要一致():
    t = _read(REPORT)
    s = _read(_REPO / "ops" / "reports" / "adapt" / "summary.md")
    m = re.search(r"例：(\d+)；有 oracle：(\d+)；有真运行：(\d+)", s)
    assert m, "适配赛道摘要的形态变了"
    n, n_oracle, n_run = m.groups()
    assert f"有真运行 {n_run}" in t
    assert n == n_oracle == n_run == "30"


def test_报告里的版本轴与冻结现值一致():
    """正文写的是当天那一版；**现值两条轴也必须在报告里出现**（§〇 现值更新）——
    否则这份报告会把一版旧轴当成现值递给读者。"""
    t = _read(REPORT)
    assert FZ.SET_VERSION in t and FZ.REFERENCE_VERSION in t, \
        f"报告里没有现值两条轴（{FZ.SET_VERSION} / {FZ.REFERENCE_VERSION}）—— 补 §〇 现值更新"
    assert FZ.SET_VERSION_PUBLIC in t, \
        f"报告里没有公开任务集轴 {FZ.SET_VERSION_PUBLIC}（裁定 ①）"


def test_两条未达成没有被写成达成():
    """完成定义 ①（18 个公开 run）与 ②（单机形态①）今天都没做到 ——
    这条测试在它们真被做到之前**必须一直绿**；真做到了就来改它。"""
    t = _read(REPORT)
    i = t.index("## 一、")
    j = t.index("## 二、")
    sec = t[i:j]
    assert "未达成（0/18）" in sec, "①（公开通道 18 个 run）的判被改动了 —— 确认它真的跑完了再改这条"
    jobs = Path("/data/shared/genebench/runs_in/m6_public/jobs.jsonl")
    if jobs.is_file():
        rows = [json.loads(l) for l in jobs.read_text(encoding="utf-8").splitlines() if l.strip()]
        done = [r for r in rows if r.get("status") != "pending"]
        if not done:
            return
        # 跑成了 —— 正文那一行仍是当天的记录，但报告必须在别处写出**现在跑成了几个**。
        assert f"{len(done)}/{len(rows)} 跑成" in t, \
            (f"清单里已经有 {len(done)}/{len(rows)} 行跑过了，而报告里没有一处写明现值 —— "
             f"补 §〇 现值更新（正文那一行是历史记录，别改）")
