# -*- coding: utf-8 -*-
"""收尾卡 v2（2026-09-11 到可分发）的判据。

与 `ops/test_wrapup.py`（收尾卡 v1）同一个形状，钉的是**这一轮**的收口有没有把东西串错：

1. 票据合并：十个收件箱 → `ops/tickets.md` 新一节 + 全部改名 `.merged`，连号、不撞号、
   既有票据按「**N-xxx 更新**」写（写成 `**N-xxx**` 会让同一个号在同一份文件里出现两次）；
2. 表：21 个批按 ⑩ 的十九列口径重出 —— 表头**只有一种**、`table_a` 的 LaTeX label **互异**
   （重复 label 不会让 LaTeX 报错，只会让 `\\ref` 指错表，比编译失败难发现得多）；
3. 签字包是**这一版**的、逐件 sha256 对得上、0400、本轮扩的件都在清单里；
4. 报告里的数与它们的**出处**一致（blocker、版本轴、适配赛道三个数），
   且三条未达成**没有被写成达成**。

**不重复别处已经钉住的东西** —— 十九列有 `ops/test_report_columns.py`、
发布清单有 `ops/test_release_manifest.py`、适配赛道有 `ops/test_X2.py`。
"""
from __future__ import annotations

import csv
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
from scorer import report as SR                                # noqa: E402

#: 本轮十张卡的收件箱**落盘名**。`X1` 与 `Y2` 这两个卡号更早一轮用过，
#: 而那一轮的 `X1.md.merged` / `Y2.md.merged` 还在 —— 直接 `mv X1.md X1.md.merged`
#: 会把上一轮那份**整个盖掉**（本卡真踩了一次，N-652）。所以本轮这两张改名收尾。
#: 卡 Y1 当时就是为了躲同一件事才把自己的收件箱叫 `Y1-rehearsal.md`。
CARDS = ("A", "B", "C", "X1-public", "X2", "Y1-rehearsal", "Y2-export", "Z", "V2.rt", "V2")
#: 本轮各卡**写在收件箱里的原名**：并完这些名字底下不许再有 `.md`。
RAW_NAMES = ("A", "B", "C", "X1", "X2", "Y1-rehearsal", "Y2", "Z", "V2.rt", "V2")
SECTION = "## 2026-09-1x 收尾卡 v2（到可分发）"
REPORT = _REPO / "ops" / "reports" / "wrapup_v2_report.md"
REPORTS = _REPO / "ops" / "reports"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def _tickets() -> tuple[str, str]:
    t = _read(_REPO / "ops" / "tickets.md")
    assert SECTION in t, "收尾卡 v2 那一节不在 ops/tickets.md 里"
    i = t.index(SECTION)
    return t[:i], t[i:]


def _assert_no_group_other(p: Path, label: str) -> None:
    """签字包的件**不许有 group / other 位**。

    **N-815**：这里原来断言恰好 `0400`。`git clone` 不保留 0400（落地成 0600），
    于是这条在**任何 clone 上恒红** —— 外部用户一跑就看见一条红，而包本身没有任何问题。
    这道门要验的是「签字包不外泄、不被就地改」，射程收在 group/other 三位上：
    `0400` 与 `0600` 都过，`0440` / `0604` 这类**真的泄出去**的照样红。
    """
    mode = stat.S_IMODE(p.stat().st_mode)
    assert mode & 0o077 == 0, f"{label} 的模式 {mode:#o} 带 group/other 位"


def _signed_dir() -> Path:
    ts = json.loads((_REPO / "ops" / "manifests" / "v1.0-smoke.json").read_text(encoding="utf-8"))
    rf = json.loads((_REPO / "ops" / "manifests" / "v1.0-smoke.reference.json").read_text(encoding="utf-8"))
    return AS.ARCHIVE / f"v{ts['set_version']}_{rf['reference_version']}"


def _repo_report_dirs() -> set[str] | None:
    """`ops/reports/` 下**仓库自己交付**的那批目录名；这棵树不是 git 树就回 None。"""
    import subprocess
    try:
        p = subprocess.run(["git", "-C", str(_REPO), "ls-files", "-z", "ops/reports/"],
                           capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    if p.returncode != 0 or not p.stdout:
        return None
    out = {parts[2] for rel in p.stdout.split("\0")
           if len(parts := rel.split("/")) >= 4 and parts[:2] == ["ops", "reports"]}
    return out or None


def _main_table_dirs() -> list[Path]:
    """出过主表的**发布方那批**目录。

    **N-813**：这里原来扫 `ops/reports/*` 下**任何**含 `table_main.csv` 的目录。
    用户照 README §2.4 出一次表（那条命令只产 `table_main.csv` + `table_main.axes.json`）
    就把自己的输出目录圈了进来，`test_每个出了主表的批都有两张全量指标表` 当场红 ——
    **在任何外部 clone 上，做对了反而红**。

    修法是**收窄射程、不放宽判据**：只看仓库自己交付的那批目录（`git ls-files` 认得的），
    被圈进来的那六件**仍然逐件查**。拿不到 git（下的是 tar 包、或不在 git 树里）就退回原来的
    全扫 —— 那种树上本来也没有用户自己的输出目录。
    `test_主表表头只有一种_且与十九列口径逐字相等` 里的 `>= 20` 是这条收窄的下限守卫：
    收窄收过头（例如 git 认不出任何一个）会在那里当场红，不会静默变成空集。
    """
    tracked = _repo_report_dirs()
    dirs = [d for d in sorted(REPORTS.iterdir())
            if d.is_dir() and (d / "table_main.csv").is_file()]
    if tracked is not None:
        dirs = [d for d in dirs if d.name in tracked]
    return dirs


# ============================================================ 1. 票据合并

def test_十个收件箱都改名merged了_原名一个不留():
    d = _REPO / "ops" / "tickets_inbox"
    for c in CARDS:
        assert (d / f"{c}.md.merged").is_file(), f"{c}.md.merged 不在"
    for c in RAW_NAMES:
        assert not (d / f"{c}.md").exists(), f"{c}.md 还在 —— 并完要改名，否则下一张卡会再并一次"


def test_改名没有盖掉更早一轮的merged():
    """`mv <卡>.md <卡>.md.merged` 在卡号被复用时会**静默覆盖**上一轮那份。

    判据：HEAD 里已经存在的每一个 `*.md.merged`，内容必须与 HEAD 逐字节相同 ——
    合并这一步只该**新增** `.merged`，不该改动任何一个既有的。
    盖掉了也不会有人发现（文件还在、名字没变、只是内容成了另一张卡的），
    所以这条测试在的意义就是让它发不出去。
    """
    import subprocess
    d = _REPO / "ops" / "tickets_inbox"
    listed = subprocess.run(["git", "ls-tree", "--name-only", "HEAD", "ops/tickets_inbox/"],
                            cwd=_REPO, capture_output=True, text=True)
    if listed.returncode != 0:
        pytest.skip("这里不是 git 工作树")
    bad = []
    for rel in listed.stdout.split():
        if not rel.endswith(".md.merged"):
            continue
        old = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=_REPO,
                             capture_output=True)
        p = _REPO / rel
        if not p.is_file():
            bad.append(f"{rel}：HEAD 里有、盘上没了")
        elif p.read_bytes() != old.stdout:
            bad.append(f"{rel}：内容与 HEAD 不同 —— 多半是被同名的 mv 盖了")
    assert not bad, "既有的 .merged 被动过：\n  " + "\n  ".join(bad)


def test_新节内部不撞号_且与旧节不撞号():
    head, new = _tickets()
    ids = re.findall(r"\*\*(N-\d+)\*\*\s*\|", new)
    assert ids, "新节里一条发号的票据都没有"
    assert len(ids) == len(set(ids)), "新节内部撞号"
    for x in set(ids):
        assert f"**{x}**" not in head, f"{x} 与旧节撞号"


def test_新节发的号连号():
    _, new = _tickets()
    nums = sorted(int(x.split("-")[1]) for x in re.findall(r"\*\*(N-\d+)\*\*\s*\|", new))
    assert nums == list(range(nums[0], nums[-1] + 1)), f"发号不连续：{nums[0]}..{nums[-1]}"


def test_既有票据按更新写_没有被重新发号():
    """N-484 / N-518 / N-543 是既有票据，卡 A 那次重冻把它们修掉了。

    合并时只能写成「更新」：重新发号会让别人输出里引的号指错地方，
    而写成 `**N-484**` 会让同一个号在 ops/tickets.md 里出现两次。
    """
    head, new = _tickets()
    for old in ("N-484", "N-518", "N-543"):
        assert f"**{old} 更新**" in new, f"{old} 应当以「更新」写在新节里"
        assert f"**{old}**" in head, f"{old} 本来就该在旧节里 —— 夹具前提不成立"


def test_每张卡都有条目并进来了():
    _, new = _tickets()
    names = {"A": "卡 A", "B": "卡 B", "C": "卡 C", "X1-public": "卡 X1", "X2": "卡 X2",
             "Y1-rehearsal": "卡 Y1", "Y2-export": "卡 Y2", "Z": "卡 Z",
             "V2.rt": "红队修复卡 V2.rt", "V2": "收尾卡 v2"}
    for c in CARDS:
        assert names[c] in new, f"{c}（{names[c]}）的条目没有在新节里标出处"


def test_handoff_的19与19_2都在_卡B那段在前():
    h = _read(_REPO / "ops" / "HANDOFF.md")
    assert "## §19 排网格" in h, "卡 B 的 §19 不见了 —— 共享文件只许追加"
    assert "## §19.2 收尾卡 v2" in h, "收尾卡 v2 的 §19.2 不在"
    assert h.index("## §19 排网格") < h.index("## §19.2 收尾卡 v2"), \
        "§19.2 必须追加在卡 B 那一段之后"


# ============================================================ 2. 各批的表

def test_主表表头只有一种_且与十九列口径逐字相等():
    want = (*SR.TABLE_A_INDEX_COLUMNS, *SR.MAIN_TABLE_COLUMNS)
    dirs = _main_table_dirs()
    assert len(dirs) >= 20, f"只有 {len(dirs)} 个批出了主表 —— 重出没跑全"
    seen = {tuple(_read(d / "table_main.csv").splitlines()[0].split(",")) for d in dirs}
    assert seen == {want}, f"表头不止一种或与十九列口径不符：{seen - {want}}"


def test_每个出了主表的批都有两张全量指标表():
    for d in _main_table_dirs():
        for f in ("table_main.md", "table_main.tex",
                  "metrics_agent.csv", "metrics_agent.md",
                  "metrics_stage.csv", "metrics_stage.md"):
            assert (d / f).is_file(), f"{d.name} 缺 {f}"


def test_各批的latex_label互异():
    """重复 `\\label` 不会让 LaTeX 报错，只会让 `\\ref` 指到后编译的那一个。

    `m6_public` / `n130` / `rehearsal_v1` / `v1demo` 四个批原本都是 `tab:a`。
    """
    labels: dict[str, list[str]] = {}
    for d in sorted(x for x in REPORTS.iterdir() if x.is_dir()):
        for f in ("table_a.tex", "table_main.tex", "table_b.tex"):
            p = d / f
            if not p.is_file():
                continue
            m = re.search(r"\\label\{(.*?)\}", _read(p))
            if m:
                labels.setdefault(m.group(1), []).append(f"{d.name}/{f}")
    dup = {k: v for k, v in labels.items() if len(v) > 1}
    assert not dup, f"LaTeX label 撞号：{dup}"


def test_主表里没有聚合列_effect一列不留():
    for d in _main_table_dirs():
        hdr = _read(d / "table_main.csv").splitlines()[0].split(",")
        bad = [c for c in hdr if c in SR.AGGREGATE_COLUMN_NAMES]
        assert not bad, f"{d.name} 的主表里有聚合列 {bad} —— ⑪ 明写不出总分、effect 不进发布表"


def test_从库来的适配表没有被落进发布目录():
    """结果库的适配切片是陈的（N-645：`failed` 11 而重算后是 7）。

    `mk_tables --table adaptation` 出的表来自结果库；把它落进 `ops/reports/adapt/`
    就是在同一个目录里放两张数不一样的表。回灌结果库之前，这个文件不该存在。
    """
    p = REPORTS / "adapt" / "table_adaptation.csv"
    assert not p.is_file(), (
        "ops/reports/adapt/table_adaptation.csv 在 —— 它来自结果库，而结果库的适配切片"
        "还没回灌（N-645）。要么先 `adapt_report.py score --no-pull --ingest`，"
        "要么别把这张表落在这里。")


# ============================================================ 3. 签字包

def test_签字包是这一版的():
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
        _assert_no_group_other(p, rel)
    for extra in ("MANIFEST.json", "README.md"):
        _assert_no_group_other(d / extra, extra)


def test_包里没有清单没记的文件():
    d = _signed_dir()
    m = json.loads((d / "MANIFEST.json").read_text(encoding="utf-8"))
    known = {AS._dst_name(r) for r in m["files"]} | {"MANIFEST.json", "README.md"}
    extra = sorted(p.name for p in d.iterdir() if p.name not in known)
    assert not extra, f"包里有而 MANIFEST 没记的文件：{extra}"


def test_清单声明了却不存在的件_如实进declared_but_missing():
    d = _signed_dir()
    m = json.loads((d / "MANIFEST.json").read_text(encoding="utf-8"))
    # 卡 H：签字包按通道出两份，这份是**私有**那一份 —— 按私有通道的清单核。
    declared = set(AS.items_for("private")) | set(AS.ROOT_ITEMS)
    assert set(m["files"]) | set(m["declared_but_missing"]) == declared, \
        "归档的 + 缺件 ≠ 清单声明的 —— 有件被静默跳过了"


def test_同名冲突断言还在_且这一版没有同名():
    src = _read(_REPO / "ops" / "archive_signoff.py")
    assert "归档文件名冲突" in src, "同名冲突断言被删了 —— 归档目录是平的，没有它就会静默覆盖"
    names = [AS._dst_name(r) for r in (*AS.ITEMS, *AS.ROOT_ITEMS)]
    assert len(names) == len(set(names)), "清单里已经有两件会落成同一个文件名"


def test_本轮扩的十件都在清单里():
    for rel in ("m6_all/metrics_agent.csv", "m6_all/metrics_agent.md",
                "m6_all/metrics_stage.csv", "m6_all/metrics_stage.md",
                "m6_public/metrics_agent.csv", "m6_public/metrics_stage.csv",
                "report_spec_v1.md", "rehearsal_v2.md", "push_instructions.md"):
        assert rel in AS.ITEMS, f"{rel} 不在 ITEMS 里"
    assert "genequant/MANIFEST.json" in AS.ROOT_ITEMS


def test_签字包逐件登记了它提到的版本轴():
    """`MANIFEST.set_version` 只说**包**的轴。包里有些是**生成的报告**，
    正文里写着自己那一刻的轴 —— 重冻之后没重跑生成器的那几份会带着上一版的轴被签进来。
    这是如实登记不是门（`VERSIONS.md` 本来就该列历次版本）。"""
    m = json.loads((_signed_dir() / "MANIFEST.json").read_text(encoding="utf-8"))
    assert "axis_mentions" in m and "mentions_other_axes" in m
    assert m["axis_mentions"], "一个件都没登记 —— 正则或后缀过滤坏了"
    assert set(m["mentions_other_axes"]) <= set(m["axis_mentions"]), \
        "mentions_other_axes 里有 axis_mentions 没有的件"
    # 判别力：`VERSIONS.md` 一定提到不止当前这一版，它必须出现在名单里
    assert "VERSIONS.md" in m["mentions_other_axes"], \
        "VERSIONS.md 没被登记 —— 它列着历次版本，判别力测试的前提不成立"


# ============================================================ 4. 报告

def test_报告八节齐():
    t = _read(REPORT)
    assert t, "ops/reports/wrapup_v2_report.md 不在"
    for h in ("## 一、", "## 二、", "## 三、", "## 四、", "## 五、", "## 六、", "## 七、", "## 八、"):
        assert h in t, f"报告缺 {h}"


def test_报告里的blocker与发布清单一致():
    t = _read(REPORT)
    rm = json.loads(_read(_REPO / "RELEASE_MANIFEST.json"))
    open_ = [b["id"] for b in rm["blockers"] if not b.get("satisfied")]
    for b in rm["blockers"]:
        assert b["id"] in t, f"报告没提 blocker {b['id']}"
    assert len(rm["blockers"]) == 5, "blocker 条数变了 —— 报告第一节的「五条」要跟着改"
    # **未闭合的 blocker 集合**不钉死在某一天：钉死的话，用户裁定关掉一条就会把这条测试跑红，
    # 而真正要拦的是「报告与清单不一致」。报告里必须如实写出**现算的条数** ——
    # 手改成「全闭」而清单里还有未闭合的，下面这句当场红。
    assert f"未闭合 blocker **{len(open_)} 条**" in t, \
        f"报告没有如实写出未闭合 blocker 的条数（清单现算 {len(open_)} 条：{open_}）"
    assert f"`releasable={str(rm['releasable']).lower()}`" in t, \
        "报告里的 releasable 与发布清单不一致"


def test_报告里的版本轴与freeze现值一致():
    t = _read(REPORT)
    assert f"**{FZ.SET_VERSION}**" in t, f"报告没写现值任务集 {FZ.SET_VERSION}"
    assert f"**{FZ.REFERENCE_VERSION}**" in t, f"报告没写现值参考面 {FZ.REFERENCE_VERSION}"
    ts = json.loads((_REPO / "ops" / "manifests" / "v1.0-smoke.json").read_text(encoding="utf-8"))
    assert ts["root"] in t, "报告里的任务集根与清单现值不符"


def test_报告里的适配赛道三个数与表一致():
    t = _read(REPORT)
    rows = list(csv.DictReader((REPORTS / "adapt" / "table.csv").open(encoding="utf-8")))
    allrow = [r for r in rows if r["level"] == "ALL"][0]
    assert allrow["failed"] in t, f"报告里的 failed 与 adapt/table.csv（{allrow['failed']}）不符"
    assert round(float(allrow["resolved_rate"]), 4) == 0.7667 or \
        f"{float(allrow['resolved_rate']):.4f}" in t
    for lvl, key in (("L1", "first_pass"), ("L2", "first_pass"), ("L3", "correct_flag")):
        v = [r for r in rows if r["level"] == lvl][0][key]
        assert f"**{v}**" in t or f" {v}" in t, f"报告里没有 {lvl} 的 {key}={v}"


def test_报告里的实例数与矩阵一致():
    t = _read(REPORT)
    pm = _read(REPORTS / "probe_matrix_instances.md")
    m = re.search(r"零 finding 的实例 (\d+)/(\d+)", pm)
    assert m, "实例矩阵的首句变了 —— 判据前提不成立"
    assert f"**{m.group(1)}/{m.group(2)}**" in t or f"{m.group(1)}/{m.group(2)}" in t, \
        f"报告里的实例数与矩阵（{m.group(1)}/{m.group(2)}）不符"


def test_三条未达成没有被写成达成():
    """⑦ / ⑮ / ⑲ 三条本轮**没有**做到。

    「部分达成」这一档不存在 —— 有一半没做到就是未达成。这条测试防的是
    下一次有人顺手把它们改成绿的，而挡着的那件事还在。
    """
    t = _read(REPORT)
    assert "**未达成 3 条**" in t, "小结里的未达成条数被改了"
    for tag in ("⑦", "⑮", "⑲"):
        i = t.rindex(f"| {tag} |")
        row = t[i:t.index("\n", i)]
        assert "**未达成" in row, f"{tag} 那一行没有写成未达成：{row[:120]}"


def test_报告说出了结果库的适配切片是陈的():
    """N-645：`genebench export` 导出的是结果库切片，而那一份还没回灌。

    ② 判「达成」是因为裁定字面那四件都做完了；导出的数不对是另一件事。
    这条测试防的是「② 绿了，于是没人再提导出的数」。
    """
    t = _read(REPORT)
    assert "N-645" in t, "报告没提 N-645"
    assert "genebench export" in t and "结果库" in t
    assert "不要因为 ② 是绿的就以为导出的适配数是对的" in t, \
        "小结里那句提醒被删了 —— 它是 ② 判达成的前提"
