# -*- coding: utf-8 -*-
"""卡 6.1：根 `README.md` 与 `docs/INTERNAL_NOTES.md` 的判据。

**这份测试要挡住的是哪一类失败**：README 是外部读者的**第一个**页面 ——
它指错一个路径、少写一件挡发布的事、或者把 `releasable` 说成 true，
都**不会让别的任何测试变红**，而读者付出的代价是「照着入口走了两步就走不通」，
或者更糟：拿一个不能发的东西去发。

判据四组：

  ① README 里提到的每个仓库路径真的存在（占位 `<…>` / `{…}` / `*` 除外）；
  ② README 与 INTERNAL_NOTES 里每个 markdown 链接的目标真的在（相对根 / 相对 `docs/` 解析）；
  ③ README 的**发布状态**一节与 `RELEASE_MANIFEST.json` 逐条一致 ——
     `releasable`、未闭合 blocker 的**条数**、`missing` 的**三个文件名**、
     以及四条版本轴与出集题数；
  ④ 命令块里每条 `--flag` 在对应脚本里真的有。

**双向**：光有上面四组还不够 —— 一个匹配不到任何东西的正则同样全绿。
所以另有一组「提取器自己没瞎」的下界断言（`test_the_extractors_actually_found_things`），
以及一组「原 README 里仍然成立的内容没有在搬家时丢掉」的核对
（`test_the_internal_half_of_the_old_readme_survived_the_move`）。

**③ 是这份测试存在的主要理由。** README §5 那一节是**如实的**，不是宣传语；
它与清单的一致性必须由机器盯着，而不是靠写文档的人自觉。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
README = REPO / "README.md"
NOTES = REPO / "docs" / "INTERNAL_NOTES.md"
MANIFEST = REPO / "RELEASE_MANIFEST.json"
PY = sys.executable

TEXT = README.read_text(encoding="utf-8") if README.exists() else ""
NOTES_TEXT = NOTES.read_text(encoding="utf-8") if NOTES.exists() else ""


def manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


# ============================================================ 在不在

def test_readme_exists_and_is_not_a_stub():
    assert README.exists(), "根 README.md 不在 —— 它是外部读者的入口"
    assert len(TEXT) > 6000, (
        f"README 只有 {len(TEXT)} 字符 —— 「是什么 / 三范式 / 快速开始 / 仓库布局 / "
        f"发布状态 / 引用」六件事装不下")


def test_internal_notes_exists():
    assert NOTES.exists(), (
        "docs/INTERNAL_NOTES.md 不在 —— 原 README 里面向施工方的内容搬到了那里，"
        "README §7 指着它")


REQUIRED_SECTIONS = (
    "## 0. 是什么",
    "## 1. 三范式",
    "## 2. 快速开始",
    "## 3. 仓库布局",
    "## 4. 设计约束",
    "## 5. 发布状态",
    "## 6. 许可与引用",
)


@pytest.mark.parametrize("head", REQUIRED_SECTIONS)
def test_every_required_section_is_present(head: str):
    assert head in TEXT, f"README 缺一节：{head}"


# ============================================================ ① 仓库路径

#: 仓库里的一级目录 —— 正文与命令里出现 `<这些>/...` 的形态就当成一条仓库路径来核。
TOP = ("ops", "harnesses", "integrations", "docs", "runner", "gateway",
       "genetask", "reference", "scorer", "snapshots", "tasks")
_PATH = re.compile(r"(?<![A-Za-z0-9_./-])(?:%s)/[A-Za-z0-9_./-]*" % "|".join(TOP))


def _placeholder(tok: str) -> bool:
    return any(ch in tok for ch in "<>{}*")


def referenced_paths() -> list[str]:
    """README 里提到的仓库路径。

    占位符要从**两头**认：token 自身带 `<>{}*` 的，以及 token 恰好停在占位符前面的
    （`ops/reports/<你的目录>`）—— 后者只看 token 自己是看不出来的，要看紧跟其后的那个字符。
    """
    out: set[str] = set()
    for m in _PATH.finditer(TEXT):
        nxt = TEXT[m.end():m.end() + 1]
        if nxt in ("<", "{", "*"):
            continue
        tok = m.group(0).rstrip(".,;:)`\"'/")
        if tok and not _placeholder(tok):
            out.add(tok)
    return sorted(out)



# -------------------------------------------------------- 射程：哪些路径**按设计**不在仓库里
# <!-- Y-2026-09-13 -->
#: 文档里出现、但**按设计就不在这棵仓库里**的路径 —— **逐字闭集**，值是「为什么不在」。
#:
#: 为什么要有这张表：这几条文档说的都是**真话**，而判据照样把它们判红，
#: 打出来的话还会把人支去找一个不存在的遗漏（卡 Xfin 在一台外部机器上实测到 4 条这样的红）。
#:
#: **收窄射程不等于放宽判据**：只有**逐字**在这张表里的才换根判，
#: 拼错一个字母（`snapshots/public_v2`）或换一层（`reference/tasks/publik`）照样按仓库路径判红 ——
#: 由 `test_the_runtime_path_exemption_is_literal` 反面证明。
#: 文档将来提到新的运行期路径时，这道门会红到有人把它显式加进来为止，**这是刻意的**。
RUNTIME_ONLY_PATHS = {
    "reference/memory_probe_answers":
        "记忆探针的答案面 —— README 原话就是「**不在这个包里**，钥匙一旦公开就立刻失效」",
    "reference/tasks/public":
        "公开题集实例 —— 第三件附件解开后落在 $GENEBENCH_ROOT 下，不随仓库发",
    "reference/tasks/public/v1.0-smoke-public":
        "同上，公开题集那一棵的根",
    "snapshots/public_v1":
        "公开快照（provider / gold 子集）—— 前两件附件解开后落在 $GENEBENCH_ROOT 下，不随仓库发",
}


def judge_path(rel: str) -> str:
    """判一条文档里提到的路径。判不过就 AssertionError；返回 `SKIP:` 开头 = 这次没能判。

    普通路径按 `REPO / rel` 判（一个字没放宽）。
    `RUNTIME_ONLY_PATHS` 里那几条**换根判**：`$GENEBENCH_ROOT / rel` 真有就是正判。
    """
    why = RUNTIME_ONLY_PATHS.get(rel)
    if why is None:
        assert (REPO / rel).exists(), (
            f"文档里提到 {rel}，但仓库里没有它。要么改文档，要么这次移动漏了一处。")
        return f"{rel}：在仓库里"
    if (REPO / rel).exists():
        return f"{rel}：按设计不在仓库里（{why}），但这棵树上它恰好也在"
    root = os.environ.get("GENEBENCH_ROOT")
    if root and (Path(root) / rel).exists():
        return f"{rel}：不在仓库里（{why}）——在 $GENEBENCH_ROOT 下核到了"
    return ("SKIP:%s **按设计不在仓库里**（%s）；这次也没能在 $GENEBENCH_ROOT 下核到它"
            "（GENEBENCH_ROOT=%s）。文档没说假话，别去找这个「遗漏」。"
            % (rel, why, root or "未设"))


def test_the_runtime_path_exemption_is_literal():
    """反面：豁免是**逐字**的 —— 拼错一个字母、换一层，照样按仓库路径判红。

    「收窄射程」最容易滑成「放宽判据」。这条断言就是把那条滑坡钉住的。
    """
    for bad in ("reference/tasks/publik",
                "reference/tasks/public/v1.0-smoke-publik",
                "reference/memory_probe_answer",
                "snapshots/public_v2",
                "snapshots/public_v1/qlib_provider",
                "ops/joblst.py",
                "ops/reports/d2e2e"):
        assert bad not in RUNTIME_ONLY_PATHS, f"{bad} 不该在豁免表里"
        assert not (REPO / bad).exists(), f"{bad} 居然真的在仓库里 —— 这条反面判据要换一个"
        with pytest.raises(AssertionError):
            judge_path(bad)


#: 这张豁免表是 README 与手册**两份门共用**的，所以「文档真的提到过」要按两份的并集判 ——
#: 手册从不提记忆探针的答案面，那很正常，不该因此逼着谁去删表里那一条。
_DOC_TEXTS = tuple((REPO / rel).read_text(encoding="utf-8")
                   for rel in ("README.md", "docs/OPERATOR_MANUAL.md")
                   if (REPO / rel).exists())


def test_the_runtime_path_exemption_only_covers_paths_the_docs_really_name():
    """豁免表里的每一条都得是 README 或手册**真的提到过**的 —— 否则它是一条没人用的放宽。"""
    assert _DOC_TEXTS, "README 与手册都读不到 —— 这条判据没有底子"
    for rel in RUNTIME_ONLY_PATHS:
        assert any(rel in t for t in _DOC_TEXTS), (
            f"豁免表里有 {rel}，README 与手册却都没提它 —— 把它删掉，别留一条没人用的放宽")

@pytest.mark.parametrize("rel", referenced_paths())
def test_every_repo_path_named_in_the_readme_exists(rel: str):
    """README 指的每个仓库路径都在。

    唯一允许不存在的是清单自己声明为缺件的那几条（`RELEASE_MANIFEST.json` 的 `missing`）——
    README §5 就是**为了**说它们缺而提它们的。
    """
    if rel in manifest()["missing"]:
        pytest.skip(f"{rel} 是清单声明的缺件（README §5 正是为了说它缺才提它）")
    out = judge_path(rel)
    if out.startswith("SKIP:"):
        pytest.skip(out[len("SKIP:"):])


# ============================================================ ② markdown 链接

_LINK = re.compile(r"\]\(([^)\s]+)\)")


def _links(text: str, base: Path) -> list[tuple[str, Path]]:
    out = []
    for m in _LINK.finditer(text):
        tgt = m.group(1)
        if tgt.startswith(("#", "http://", "https://", "mailto:")):
            continue
        out.append((tgt, (base / tgt).resolve()))
    return out


README_LINKS = _links(TEXT, REPO)
NOTES_LINKS = _links(NOTES_TEXT, NOTES.parent if NOTES.exists() else REPO)


@pytest.mark.parametrize("tgt,path", README_LINKS, ids=[t for t, _ in README_LINKS])
def test_every_readme_link_target_exists(tgt: str, path: Path):
    assert path.exists(), f"README 的链接 `{tgt}` 指向 {path}，那里没有东西"


@pytest.mark.parametrize("tgt,path", NOTES_LINKS, ids=[t for t, _ in NOTES_LINKS])
def test_every_internal_notes_link_target_exists(tgt: str, path: Path):
    assert path.exists(), f"INTERNAL_NOTES 的链接 `{tgt}` 指向 {path}，那里没有东西"


# ============================================================ ③ 发布状态

_CN = {0: "零", 1: "一", 2: "两", 3: "三", 4: "四", 5: "五", 6: "六",
       7: "七", 8: "八", 9: "九", 10: "十"}


def test_the_release_status_section_says_what_the_manifest_says():
    """README §5 与 `RELEASE_MANIFEST.json` 的 `releasable` 一致。

    这一条不允许「暂时先写成能发、回头再改」：清单的 `releasable` 是**推导**出来的，
    README 只是把它翻译成人话。两边分叉时红的是 README。
    """
    m = manifest()
    body = TEXT.split("## 5. 发布状态", 1)[1].split("\n## ", 1)[0]
    if m["releasable"]:
        assert "releasable = false" not in body, (
            "清单说 releasable=true，README §5 还写着 false —— 该改 README 了")
    else:
        assert "releasable = false" in body, (
            "清单说 releasable=false，README §5 必须原样写出来。"
            "「三件挡发布的事」这一节是这份 README 可信的理由，不许粉饰。")


def test_the_number_of_open_blockers_matches_the_manifest():
    m = manifest()
    n = len([b for b in m["blockers"] if not b["satisfied"]])
    body = TEXT.split("## 5. 发布状态", 1)[1].split("\n## ", 1)[0]
    assert f"未闭合的{_CN[n]}条" in body, (
        f"清单里有 {n} 条未闭合的 blocker，README §5 没有写「未闭合的{_CN[n]}条」。"
        f"blocker 增减时这一节必须跟着改 —— 少写一条就是粉饰。")


@pytest.mark.parametrize("bid", [b["id"] for b in json.loads(
    MANIFEST.read_text(encoding="utf-8"))["blockers"] if not b["satisfied"]])
def test_every_open_blocker_is_visible_in_the_readme(bid: str):
    """每条未闭合的 blocker 在 README 里都能被读者认出来。

    比 id 字面量更可靠的是**那件事本身**的关键词 —— 读者读的是中文正文，不是 id。
    """
    tell = {
        "data_license_text": "pending_license_text",
        "no_clone_url": "git remote",
        "frozen_artifacts_missing": "factor_library",
        "code_license_undecided": "代码许可未定",
        "public_channel_zero_runs": "公开通道一个 run 都没有",
    }
    assert bid in tell, (
        f"清单里出现了一条 README 没认过的 blocker：{bid}。"
        f"给它补一句正文，并把关键词加进这张表 —— 别让新 blocker 悄悄不见。")
    assert tell[bid] in TEXT, f"blocker {bid} 在 README 里找不到（关键词 {tell[bid]!r}）"


def test_the_missing_frozen_artifacts_are_named_one_by_one():
    """三个缺件逐个点名，不许缩写成「有几个文件缺失」。"""
    for rel in manifest()["missing"]:
        stem = Path(rel).stem            # qlib_native / qlib_panel / blocked
        assert stem in TEXT, (
            f"清单说 {rel} 缺，README 没点它的名（{stem}）。"
            f"缺件是外部用户复现不了 τ 的直接原因，必须逐个写出来。")


def test_the_axes_and_task_counts_in_the_readme_are_the_real_ones():
    m = manifest()
    assert m["axes"]["set_version"] in TEXT, "README 写的任务集版本与清单对不上"
    assert m["axes"]["reference_version"] in TEXT, "README 写的参考面版本与清单对不上"
    assert m["freeze_line"] in TEXT, "README 写的冻结线与清单对不上"
    c = m["task_counts"]
    assert f"**{c['released']} 道题**" in TEXT, (
        f"README §0.2 说的出集题数与清单的 {c['released']} 对不上")
    assert str(c["drafted"]) in TEXT and str(c["held"]) in TEXT, (
        f"README §0.2 要同时写清草拟 {c['drafted']} / 扣住 {c['held']}，"
        f"只写出集数会让人以为「一共就这么多题」")


def test_the_per_stage_counts_add_up_to_the_released_total():
    """§0.2 那张表逐阶段的题数加起来 == 出集总数。

    表里的数是手写的，加不起来就是抄错了 —— 而抄错的表比没有表更糟。
    """
    m = manifest()
    ids = [t["task_id"] for t in json.loads(
        (REPO / "ops" / "manifests" / "v1.0-smoke.json").read_text(encoding="utf-8")
    )["released_tasks"]]
    real = {f"S{i}": sum(1 for t in ids if t.startswith(f"s{i}-")) for i in range(1, 9)}
    rows = re.findall(r"^\|\s*\*\*(S[1-8])\*\*[^|]*\|[^|]*\|\s*(\d+)\s*\|", TEXT, re.M)
    assert len(rows) == 8, f"§0.2 的八阶段表只解析出 {len(rows)} 行（应为 8）"
    got = {s: int(n) for s, n in rows}
    assert got == real, f"§0.2 表里的逐阶段题数 {got} 与出集清单 {real} 不符"
    assert sum(got.values()) == m["task_counts"]["released"]


# ============================================================ ④ 命令里的 flag

_SCRIPT = re.compile(r"(?<![A-Za-z0-9_./-])((?:%s)/[A-Za-z0-9_./-]+\.(?:py|sh))"
                     % "|".join(TOP))
_FLAG = re.compile(r"(?<![A-Za-z0-9-])--[a-z][a-z0-9-]*")


def command_flags() -> list[tuple[str, str]]:
    """命令块里 `(脚本, --flag)` 的配对。

    只认**围栏代码块**里的行，且行上要有一个仓库脚本 —— 正文里散着的 `--max-tokens`
    不配对到任何脚本（它属于哪个脚本要看上下文，机器猜不准，猜错了是恒红）。
    """
    out: set[tuple[str, str]] = set()
    inside = False
    for line in TEXT.splitlines():
        if line.startswith("```"):
            inside = not inside
            continue
        if not inside:
            continue
        s = _SCRIPT.search(line)
        if not s:
            continue
        for f in _FLAG.findall(line):
            out.add((s.group(1), f))
    return sorted(out)


def _help_text(rel: str) -> str:
    """真的去跑那个脚本拿 `--help`。

    **`.sh` 一律不跑。** 这几个 shell 脚本（推 bundle / 推 exec 树 / 起停网关）
    没有 `--help` 分支，敲下去就是**真的开始推**。判据宁可弱一点，
    也不能让一次 `pytest` 把东西推上执行面 —— 它们退回源码字面量核对。
    """
    if not rel.endswith(".py"):
        return ""
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    try:
        r = subprocess.run([PY, str(REPO / rel), "--help"], cwd=REPO, env=env,
                           capture_output=True, text=True, timeout=120)
        return (r.stdout or "") + (r.stderr or "")
    except Exception:
        return ""


@pytest.mark.parametrize("rel,flag", command_flags(),
                         ids=[f"{r}{f}" for r, f in command_flags()])
def test_every_flag_used_in_the_readme_really_exists(rel: str, flag: str):
    """README 命令里的每个 `--flag` 在脚本里真的有。

    先看 `--help` 的真实输出；带子命令的脚本（`ops/joblist.py gen --matrix`）
    与 `.sh` 拿不到全部开关，退回「字面量在脚本正文里出现过」——
    开关被改名或删掉时，两条路都会红。
    """
    src = (REPO / rel).read_text(encoding="utf-8", errors="replace")
    if flag in _help_text(rel) or flag in src:
        return
    pytest.fail(f"README 让读者敲 `{rel} {flag}`，但 {rel} 的 --help 与源码里都没有它。"
                f"用户看到的是 unrecognized arguments，而那看起来像他自己装错了。")


# ============================================================ 双向：提取器没瞎

def test_the_extractors_actually_found_things():
    """下界断言：一个匹配不到任何东西的正则同样全绿。

    这三个数是「提取器没瞎」的**下界**，不是覆盖率目标 —— 别把它们当 KPI 往上调。
    """
    paths, links, flags = referenced_paths(), README_LINKS, command_flags()
    assert len(paths) >= 25, f"只从 README 里提出 {len(paths)} 条仓库路径，提取器多半瞎了"
    assert len(links) >= 20, f"只提出 {len(links)} 个 markdown 链接，提取器多半瞎了"
    assert len(flags) >= 8, f"只提出 {len(flags)} 对 (脚本, flag)，提取器多半瞎了"


def test_the_readme_points_at_all_five_reader_entrances():
    """README 顶部那张「你是谁 → 从哪读起」的表，五个入口一个都不能少。"""
    for doc in ("docs/OPERATOR_MANUAL.md", "harnesses/README.md",
                "integrations/README.md", "integrations/P2_CONTRACT.md",
                "ops/HANDOFF.md", "VERSIONS.md"):
        assert doc in TEXT, f"README 没有指向 {doc} —— 那类读者会走丢"


def test_the_three_paradigms_each_get_their_own_paragraph():
    for p in ("**P1", "**P2", "**P3"):
        assert p in TEXT, f"README §1 缺 {p} 那一段"
    assert "/task/protocol/" in TEXT, "P3 的定义离不开 `/task/protocol/` 这个目录名"


# ============================================================ 双向：搬家没丢东西

MOVED_TOPICS = {
    "pip 镜像": "PIP_CONFIG_FILE",
    "建目录的正确姿势": "harden_umask",
    "落点搬迁": "_DEFAULT_ROOT",
    "数据湖陷阱：句柄": "Too many open files",
    "数据湖陷阱：停牌缺行": "suspend_d",
    "数据湖陷阱：涨跌停": "pre_close",
    "进度纪律": "progress.md",
}


@pytest.mark.parametrize("topic,tell", sorted(MOVED_TOPICS.items()))
def test_the_internal_half_of_the_old_readme_survived_the_move(topic: str, tell: str):
    """原 README 里仍然成立的施工内容没有在改写时丢掉，只是换了地方。

    「把 README 改成对外入口」的失败形态不是写得不好看，而是**顺手删掉了别人还在用的东西**。
    """
    assert tell in NOTES_TEXT, (
        f"原 README 的「{topic}」（关键词 {tell!r}）在 docs/INTERNAL_NOTES.md 里找不到 —— "
        f"改写 README 时不许把它丢了")


def test_the_design_constraints_section_kept_the_hard_ones():
    """原 README 的「红线」一节对外部运行者仍然有用，改写成「设计约束」时不许缩水。"""
    body = TEXT.split("## 4. 设计约束", 1)[1].split("\n## ", 1)[0]
    for tell in ("0.0.0.0", "0700", "2026-07-31", "internal: true"):
        assert tell in body, f"§4 少了一条硬约束（关键词 {tell!r}）"


# ============================================================ ⑤ 单机路径（卡 G10，裁定 ⑤）
#
# **为什么要有这一组。** 2026-09-14 实测：`placement` / `topology` / `single` /
# `push_exec` 这几个字在本文件与 `ops/test_docs_consistency.py` 里**命中 0 次** ——
# 三道文档门全绿，却一条都没拦住交付终核在干净 Mac 上量到的 3 条 block + 6 条 major。
# 用户点破的就是这一句：**门全绿却一条都没拦住，靠的是派卡时人对交接。**
#
# 这一组**不是通用扫描器**（契约禁止新增扫描类自查），是一张**逐条闭集**的事实表，
# 与 `ops/test_docs_consistency.py` 同形。判据都写成**吃 `text` 的函数**，
# 为的是让反证能喂一份「改回旧写法」的临时副本进去 —— 判别力不该只存在于读代码的人脑子里。


def readme_section(head: str, text: str | None = None) -> str:
    """取 README 的一节正文（到下一个同级或更高级标题为止）。"""
    t = TEXT if text is None else text
    assert head in t, f"README 缺一节：{head}"
    body = t.split(head, 1)[1]
    return body.split("\n### ", 1)[0].split("\n## ", 1)[0]


def fenced_blocks(body: str) -> list[str]:
    """一节里的**全部**围栏代码块。

    「只取第一个块」是这类判据踩过的坑：§2.4 在 2026-09-14 被拆成三个块
    （干跑 / 单机 / 双机）之后，一条只看第一个块的旧判据当场变成假红。
    """
    out: list[str] = []
    cur: list[str] = []
    inside = False
    for ln in body.splitlines():
        if ln.startswith("```"):
            if inside:
                out.append("\n".join(cur))
                cur = []
            inside = not inside
            continue
        if inside:
            cur.append(ln)
    return out


def single_machine_problems(text: str | None = None) -> list[str]:
    """§2.4 的**单机那一支**：逐条闭集，每条都说清楚「不写会怎样」。"""
    p: list[str] = []
    body = readme_section("### 2.4 最短路径", text)
    blocks = fenced_blocks(body)
    single = [b for b in blocks if "runner.placement" in b and "--place-exec" in b]
    dual = [b for b in blocks if "push_exec_to_f02.sh" in b]
    if not single:
        p.append("§2.4 里没有**单机**那一支的照抄命令（`runner.placement --place-exec`）—— "
                 "单机用户照 §2.4 走会被指去推一台不属于他的机器")
    if not dual:
        p.append("§2.4 里没有**双机**那一支的照抄命令（`ops/push_exec_to_f02.sh`）—— "
                 "本项目自己的形态从 §2.4 消失了")
    for b in single:
        runs = [ln for ln in b.splitlines() if "run_joblist.py" in ln and "--resume" in ln]
        if not runs:
            p.append("单机那个代码块里没有真跑命令（`run_joblist.py … --resume`）")
        for ln in runs:
            if "--topology single" not in ln:
                p.append("单机那条真跑命令没带 `--topology single` —— **不给就是双机**，"
                         f"会得到一条 ssh 到别人机器的命令：{ln.strip()[:90]}")
    if "--check-plane" not in body:
        p.append("§2.4 没给 `--check-plane`（只探不跑的执行面前置自查）")
    if "provider_pin_expect(" not in body:
        p.append("§2.4 没给「执行面上还要一份 provider」那一步（目录名那 8 位**现算**）—— "
                 "它是「有 docker、有 key 也走不到表」的直接原因")
    return p


#: **绝对句 → 它必须带的形态限定**。逐条闭集：这几句单独读都是真话，
#: 但**少了形态限定就会把单机用户指向另一条路**（用户裁定 ⑤ 第 ④ 条）。
TOPOLOGY_QUALIFIED_ABSOLUTES: tuple[tuple[str, str], ...] = (
    ("只有这两个脚本", "双机"),
    ("没有「推」这件事", "单机"),
    ("直接 cp 就行", "单机"),
)
#: 形态限定要出现在绝对句**前面**多少个字以内。
_QUALIFIER_WINDOW = 24


def absolute_sentence_problems(text: str | None = None) -> list[str]:
    """「只有一条路 / 不要直接 cp」这类绝对句，不许在**没有形态限定**的情况下出现。"""
    t = TEXT if text is None else text
    p: list[str] = []
    for phrase, qualifier in TOPOLOGY_QUALIFIED_ABSOLUTES:
        hits = list(re.finditer(re.escape(phrase), t))
        if not hits:
            p.append(f"绝对句「{phrase}」在 README 里找不到了 —— "
                     f"这条判据当场变空，要么把它改准，要么连同这一行一起删")
            continue
        for m in hits:
            win = t[max(0, m.start() - _QUALIFIER_WINDOW):m.start()]
            if qualifier not in win:
                p.append(f"绝对句「{phrase}」前 {_QUALIFIER_WINDOW} 字里没有形态限定"
                         f"「{qualifier}」：…{win[-40:]!r}")
    return p


def test_the_readme_gives_both_topologies_for_the_shortest_path():
    """§2.4 ③④ 两步按形态分岔，两支都在，且单机那条真跑带 `--topology single`。"""
    bad = single_machine_problems()
    assert not bad, "README §2.4 的单机那一支不完整：\n  - " + "\n  - ".join(bad)


def test_absolute_sentences_are_topology_qualified():
    bad = absolute_sentence_problems()
    assert not bad, ("README 里有**没带形态限定**的绝对句 —— 它们会把单机用户指错路：\n  - "
                     + "\n  - ".join(bad))


def test_the_readme_names_the_single_machine_entry_points():
    """单机那条路的两个入口在 README 里都要点名，不然读者无从知道自己手上已经有它了。"""
    for tell in ("runner/placement.py", "--place-exec", "--topology single|dual",
                 "GENEBENCH_TOPOLOGY"):
        assert tell in TEXT, (
            f"README 没提 {tell!r} —— 单机用户读不到「这条路已经在本树里」。"
            f"2026-09-14 之前这几个字在两份文档门里命中 0 次，而门全是绿的。")


# ---------------------------------------------------------- 反证：改回旧写法必须红

def test_the_single_machine_assertions_go_red_on_the_old_wording():
    """把 §2.4 改回**旧写法**（2026-09-14 之前那一版：一个块、只有双机、没有形态开关），
    上面那条判据必须当场红。"""
    body = readme_section("### 2.4 最短路径")
    blocks = fenced_blocks(body)
    single = [b for b in blocks if "runner.placement" in b and "--place-exec" in b]
    assert single, "现文里就没有单机那个块 —— 这条反证是空的"
    old = TEXT.replace(single[0], "（旧写法：当时这个块根本不在）")
    assert old != TEXT, "副本逐字节没变 —— 这条反证是空的"
    bad = single_machine_problems(old)
    assert bad, "把单机那个块整块拿掉之后判据照样绿 —— 它是一条空判据"


def test_the_topology_flag_assertion_goes_red_when_the_flag_is_dropped():
    """只把 `--topology single` 从真跑那条命令上拿掉（别的一个字不动）—— 必须红。

    这是最容易悄悄发生的一次退化：命令还在、看起来也对，只是**默认回了 dual**。
    """
    old = TEXT.replace(" --topology single", "")
    assert old != TEXT, "副本逐字节没变 —— 这条反证是空的"
    bad = single_machine_problems(old)
    assert any("--topology single" in b for b in bad), (
        f"拿掉 `--topology single` 之后判据没点它的名：{bad}")


def test_the_absolute_sentence_assertion_goes_red_when_the_qualifier_is_dropped():
    """把形态限定从绝对句前面拿掉 —— 必须红，而且要点到那一句的名。"""
    for phrase, qualifier in TOPOLOGY_QUALIFIED_ABSOLUTES:
        i = TEXT.index(phrase)
        win = TEXT[max(0, i - _QUALIFIER_WINDOW):i]
        old = TEXT[:max(0, i - _QUALIFIER_WINDOW)] + win.replace(qualifier, "") + TEXT[i:]
        assert old != TEXT, f"「{phrase}」那一处副本没变 —— 这条反证是空的"
        bad = absolute_sentence_problems(old)
        assert any(phrase in b for b in bad), (
            f"把「{qualifier}」从「{phrase}」前面拿掉之后判据没点它的名：{bad}")
