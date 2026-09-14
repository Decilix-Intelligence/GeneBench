# -*- coding: utf-8 -*-
"""卡 Y：**3.12 冒烟门** + 本卡三条修复的判据。

**这道门要挡住的是哪一类失败**：*一个默认值或判据，悄悄取决于跑它的是不是发布方那台机器。*
本轮那个实例是**解释器版本** —— 发布方 f01 的解释器是 conda **Python 3.10**，
而 README §1.5 **强制 3.12**；凡是只在 **3.11+** 才报的错，内部**永远照不到**。

具体到本轮那条 block：`ops/joblist.py` 把子命令 `rebudget` **注册了两次**（两个逐字相同的块）。
**3.10 的 `argparse` 不查重**，照跑，`--help` 里打印两遍而已；**3.11 起 `add_parser` 开始查重**，
于是在 3.12 上每次调用都当场抛
`argparse.ArgumentError: argument cmd: conflicting subparser: rebudget` ——
`--help` / `gen` / `stat` / `list` / `reset` 全部起不来，
外部用户照 README §2.4 敲的**第一条**命令就死。内部任何测试都照不到它。

## 门分两层，两层都要

**① 版本无关的那一层**（`test_no_cli_registers_the_same_subcommand_twice`）——
按 **AST** 数每个文件里 `add_parser("<字面量>")` 的名字，同名出现两次就红。
它**在 3.10 上也抓得到本轮这条**，这正是它存在的理由：
不指望「将来有人在 3.12 上跑一次」，而是让这一类第一天就掉出来。
判别力由 `test_the_duplicate_subcommand_scanner_has_teeth` **反面自证**：
往一份真源码的副本里注入一个重复注册 → 当场红；还原 → 绿。

**② 真 3.12 的那一层**（`test_every_documented_cli_starts_on_a_real_312`）——
把**文档里叫用户敲的**每个 CLI 入口在一个**真 3.12 解释器**上跑一次 `--help`。
找不到可用的 3.12 时**大声 skip 并说清楚是为什么**（不许静默变绿）：
`pytest` 的汇总行里会有 skip 计数，`-rs` 能看到原因。
**发布前必须在有 3.12 的环境上跑一次这道门** —— 命令写在 `ops/tickets.md` 本卡那一节。

怎么给它一个 3.12（按这个顺序找第一个**版本 ≥ 3.11 且六个包 import 得进**的）：

    GENEBENCH_PY312=<那个解释器> $PY -m pytest ops/test_Y.py -q -rs

## 另外三组（本卡三条修复各自的判据）

* `F02` 的 env 兜底 —— **发布方那台的取值逐字不变**，外部设了 `GENEBENCH_F02` 就跟着走；
* README §2.4 的最短路径**跑在公开通道上**（`--channel` 默认是 `private`，私有题集不随发布件交付）；
* README §2.1 **先 `--harden` 再 `selfcheck`**，以及 `ops/reports/d2_e2e/` 那份证据在树里。
"""
from __future__ import annotations

import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
OPS = REPO / "ops"
README = REPO / "README.md"
MANUAL = REPO / "docs" / "OPERATOR_MANUAL.md"

README_TEXT = README.read_text(encoding="utf-8") if README.exists() else ""
MANUAL_TEXT = MANUAL.read_text(encoding="utf-8") if MANUAL.exists() else ""

#: 发布方执行面的 ssh 目标。**这个值不许变** —— 补 env 兜底不等于改默认行为。
PUBLISHER_F02 = "ljn@192.168.1.219"

#: README §1.5 点名的六个包。找 3.12 解释器时拿它当「这个解释器能不能跑本项目」的判据。
SIX = ("fastapi", "uvicorn", "pandas", "pyarrow", "duckdb", "yaml")


# ============================================================ ① 版本无关：同名子命令不许注册两次

def add_parser_names(path: Path) -> list[str]:
    """一个 `.py` 里所有 `<x>.add_parser("<字面量>")` 的名字，按出现顺序。

    只认**字面量**：动态拼出来的名字这道门看不见，也不假装看得见。
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
    except SyntaxError:
        return []
    out: list[str] = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_parser"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            out.append(node.args[0].value)
    return out


def duplicate_subcommands(path: Path) -> list[str]:
    """同一个文件里被注册了两次（或更多）的子命令名。"""
    seen: dict[str, int] = {}
    for n in add_parser_names(path):
        seen[n] = seen.get(n, 0) + 1
    return sorted(n for n, c in seen.items() if c > 1)


def _all_py() -> list[Path]:
    return sorted(p for p in REPO.rglob("*.py")
                  if ".git" not in p.parts and "__pycache__" not in p.parts)


def test_no_cli_registers_the_same_subcommand_twice():
    """全树：没有任何文件把同一个子命令名注册两次。

    **3.10 上照跑、3.11 起当场抛** —— 所以这条断言必须是**版本无关**的静态判据，
    否则发布方那台（3.10）永远照不到它。
    """
    bad = {}
    for p in _all_py():
        d = duplicate_subcommands(p)
        if d:
            bad[str(p.relative_to(REPO))] = d
    assert not bad, (
        f"这些文件把同一个子命令注册了不止一次：{bad}。\n"
        f"Python **3.11 起** `add_parser` 查重，于是在 README §1.5 强制的 3.12 上\n"
        f"每次调用都抛 `argparse.ArgumentError: conflicting subparser` —— "
        f"`--help` 在内的**每一条**子命令都起不来。\n"
        f"发布方内部是 3.10（不查重），所以内部任何测试都照不到它：删掉重复的那一份。")


def test_the_duplicate_subcommand_scanner_has_teeth():
    """反面自证：往一份真源码的副本里注入一个重复注册 → 当场红；还原 → 绿。

    一个匹配不到任何东西的扫描器同样是全绿的。这条断言就是为了把那种绿排除掉。
    """
    src = OPS / "joblist.py"
    assert src.is_file(), "ops/joblist.py 不在 —— 这条反面判据没有底子了"
    names = add_parser_names(src)
    assert names, "扫描器在 ops/joblist.py 上一个 add_parser 都没认出来 —— 它多半坏了"
    assert duplicate_subcommands(src) == [], f"ops/joblist.py 现在就有重复：{duplicate_subcommands(src)}"

    text = src.read_text(encoding="utf-8")
    victim = names[0]
    injected = text + (
        '\n\ndef _teeth_probe(sub):\n'
        f'    sub.add_parser("{victim}")\n')
    with tempfile.TemporaryDirectory() as td:
        probe = Path(td) / "joblist_probe.py"
        probe.write_text(injected, encoding="utf-8")
        assert duplicate_subcommands(probe) == [victim], (
            f"注入了一个重复的 {victim!r}，扫描器却没认出来 —— 这道门没有牙")
    # 还原（副本在临时目录里，原文件一个字节没动）
    assert duplicate_subcommands(src) == []


# ============================================================ ② 真 3.12：文档叫用户敲的 CLI 都起得来

#: 文档里出现过的 `ops/<name>.py` 脚本 token。`ops/test_*.py` 不是 CLI，排掉。
_OPS_SCRIPT = re.compile(r"(?<![A-Za-z0-9_./-])ops/([A-Za-z0-9_]+)\.py")


def documented_clis() -> list[str]:
    """README 与手册里叫用户敲的 `ops/*.py` 入口（真的有 argparse 的那些）。"""
    names = set()
    for txt in (README_TEXT, MANUAL_TEXT):
        for m in _OPS_SCRIPT.finditer(txt):
            names.add(m.group(1))
    out = []
    for n in sorted(names):
        if n.startswith("test_") or n in ("conftest",):
            continue
        p = OPS / f"{n}.py"
        if not p.is_file():
            continue
        body = p.read_text(encoding="utf-8", errors="replace")
        if "argparse" not in body:
            continue
        out.append(f"ops/{n}.py")
    return out


def test_the_documented_cli_extractor_actually_found_things():
    """下界：一个匹配不到任何东西的提取器同样让下面那条全绿。"""
    clis = documented_clis()
    assert len(clis) >= 12, f"只提取到 {len(clis)} 个文档点名的 CLI：{clis} —— 提取器多半坏了"
    for must in ("ops/joblist.py", "ops/run_joblist.py", "ops/mk_tables.py",
                 "ops/selfcheck_public.py", "ops/score_runs.py"):
        assert must in clis, f"{must} 没被提取到 —— 提取器多半坏了"


def _interpreter_ok(py: str) -> tuple[bool, str]:
    """这个解释器能不能当「外部用户那台」用：版本 ≥ 3.11 且六个包 import 得进。

    3.11 是分界线，不是 3.12 —— `add_parser` 的查重**从 3.11 开始**，
    所以 3.11 就足以照到本轮这一类；下面挑解释器时按 3.11 收，报文案按 3.12 写。
    """
    try:
        v = subprocess.run([py, "-c", "import sys;print('%d.%d' % sys.version_info[:2])"],
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"起不来（{e}）"
    if v.returncode != 0:
        return False, f"起不来（rc={v.returncode}）"
    ver = v.stdout.strip()
    major, _, minor = ver.partition(".")
    try:
        if (int(major), int(minor)) < (3, 11):
            return False, f"是 {ver}，低于 3.11（argparse 还不查重，照不到这一类）"
    except ValueError:
        return False, f"版本读不出来（{ver!r}）"
    d = subprocess.run([py, "-c", "import " + ",".join(SIX)],
                       capture_output=True, text=True, timeout=180)
    if d.returncode != 0:
        return False, f"是 {ver}，但六个包 import 不进（{d.stderr.strip().splitlines()[-1:]}）"
    return True, ver


def find_real_312() -> tuple[str | None, list[str]]:
    """按顺序找第一个可用的 ≥3.11 解释器。返回 (解释器, 逐个候选为什么不行)。"""
    cands: list[str] = []
    for v in (os.environ.get("GENEBENCH_PY312"),
              os.environ.get("GENEBENCH_ROOT") and
              str(Path(os.environ["GENEBENCH_ROOT"]) / "env" / "bin" / "python"),
              sys.executable,
              shutil.which("python3.12"),
              shutil.which("python3.13"),
              "/opt/homebrew/bin/python3.12",
              "/usr/local/bin/python3.12"):
        if v and v not in cands:
            cands.append(v)
    why = []
    for c in cands:
        if not Path(c).exists() and not shutil.which(c):
            why.append(f"{c}：不在")
            continue
        ok, info = _interpreter_ok(c)
        if ok:
            return c, why
        why.append(f"{c}：{info}")
    return None, why


@pytest.mark.parametrize("rel", documented_clis())
def test_every_documented_cli_starts_on_a_real_312(rel: str):
    """文档叫用户敲的每个入口，在**真 3.12**（≥3.11）上 `--help` 起得来。

    找不到可用的解释器时 **skip 并把每个候选为什么不行逐条说出来** —— 不许静默变绿。
    """
    py, why = find_real_312()
    if py is None:
        pytest.skip(
            "这台机器上没有可用的 3.12（≥3.11 且六个包 import 得进），**这道门没有真的跑**。\n"
            "  逐个候选：" + "；".join(why) + "\n"
            "  给它一个：GENEBENCH_PY312=<解释器> 再跑一次。\n"
            "  **发布前必须在有 3.12 的环境上跑一次这道门**（见 ops/tickets.md 卡 Y 那一节）。")
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(REPO)
    p = subprocess.run([py, rel, "--help"], cwd=str(REPO), env=env,
                       capture_output=True, text=True, timeout=300)
    out = (p.stdout or "") + (p.stderr or "")
    assert "Traceback" not in out and p.returncode == 0, (
        f"{rel} --help 在 {py} 上起不来（rc={p.returncode}）：\n"
        f"{out.strip()[-1200:]}\n"
        f"外部用户照文档敲的第一条命令就是这个 —— 内部 3.10 上它可能是绿的。")


# ============================================================ ③ F02：补了 env 兜底，默认值一个字没变

def _f02_in(env_extra: dict) -> dict:
    env = dict(os.environ)
    env.pop("GENEBENCH_F02", None)
    env.update(env_extra)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(REPO)
    code = ("import sys;sys.path.insert(0,%r);"
            "from ops import run_joblist as RJ, score_runs as SC;"
            "print(RJ.F02);print(SC.F02)" % str(REPO))
    p = subprocess.run([sys.executable, "-c", code], cwd=str(REPO), env=env,
                       capture_output=True, text=True, timeout=300)
    assert p.returncode == 0, f"取 F02 失败：{p.stderr[-800:]}"
    a, b = p.stdout.strip().splitlines()[:2]
    return {"run_joblist": a, "score_runs": b}


def test_the_f02_default_is_byte_for_byte_the_publisher_one():
    """**不设 `GENEBENCH_F02` 时，两处的值逐字仍是发布方的执行面。**

    补兜底不是改默认行为：发布方那台机器上的跑批与结算**一个字节都不受影响**。
    """
    got = _f02_in({})
    assert got["run_joblist"] == PUBLISHER_F02, got
    assert got["score_runs"] == PUBLISHER_F02, got


def test_setting_genebench_f02_actually_moves_both_entry_points():
    """设了 `GENEBENCH_F02`，跑批与结算**两处都跟着走**。

    卡 Xfin 在一台外部机器上实测过没有这条兜底的代价：单机用户设了变量，
    `run_joblist --dry` 打出来的 ssh 目标**仍然是发布方那台**，
    而他只能改源码、且两处文档的「要改哪些常量」表都没列它们。
    """
    mine = "me@127.0.0.1"
    got = _f02_in({"GENEBENCH_F02": mine})
    assert got["run_joblist"] == mine, got
    assert got["score_runs"] == mine, got


def test_both_f02_entry_points_read_the_same_env_name_as_the_push_scripts():
    """口径同源：两个 `.py` 读的变量名与两个推送 `.sh`、`ops/api_usage.py` 是同一个。"""
    for rel in ("ops/run_joblist.py", "ops/score_runs.py", "ops/api_usage.py",
                "ops/push_bundle_to_f02.sh", "ops/push_exec_to_f02.sh"):
        p = REPO / rel
        assert p.is_file(), f"{rel} 不在"
        assert "GENEBENCH_F02" in p.read_text(encoding="utf-8", errors="replace"), (
            f"{rel} 没读 GENEBENCH_F02 —— 五个入口本来就该同源（手册 §1.3）")


# ============================================================ ④ README §2.4：最短路径跑在公开通道上

def _readme_block(head: str, after: str = "```sh", end: str = "```") -> str:
    seg = README_TEXT.split(head, 1)
    assert len(seg) == 2, f"README 里找不到 {head}"
    body = seg[1].split(after, 1)[1].split(end, 1)[0]
    return body


def test_the_run_joblist_channel_default_is_still_private():
    """文档那句「默认是 private」得是真的 —— 它一旦变了，上面那段解释就成了假话。"""
    src = (REPO / "ops" / "run_joblist.py").read_text(encoding="utf-8")
    m = re.search(r'--channel"[^)]*?default=["\'](\w+)["\']', src, flags=re.S)
    assert m, "在 ops/run_joblist.py 里找不到 --channel 的 default —— 判据要跟着改"
    assert m.group(1) == "private", (
        f"run_joblist 的 --channel 默认值是 {m.group(1)!r}，不再是 private —— "
        f"README §2.4 那段「默认值是 private」的解释要跟着改")


def test_the_readme_shortest_path_runs_on_the_public_channel():
    """§2.4 那个代码块里**每条** `run_joblist` 都带 `--channel public`，且块里开了环境变量。

    不带它的代价是**静默跑私有题集**：私有题集按红线 2 永远不随发布件交付，
    外部用户手上只有公开那一份 —— 干跑看起来一切正常，要到真跑才报「找不到任务目录」。
    """
    block = _readme_block("### 2.4 最短路径")
    assert "export GENEBENCH_CHANNEL=public" in block, (
        "§2.4 的代码块里没有 `export GENEBENCH_CHANNEL=public`")
    lines = [ln for ln in block.splitlines() if "run_joblist.py" in ln]
    assert len(lines) >= 2, f"§2.4 里只有 {len(lines)} 条 run_joblist 命令，期望 2 条（干跑 + 真跑）"
    for ln in lines:
        assert "--channel public" in ln, (
            f"§2.4 这条 run_joblist 没带 `--channel public`，外部用户会静默跑私有题集：\n  {ln.strip()}")


def test_the_readme_says_why_the_channel_switch_is_mandatory():
    """光把命令改对不够 —— 得说清楚**为什么**，否则下一个人又会把它删掉。"""
    body = README_TEXT.split("### 2.4 最短路径", 1)[1].split("\n### ", 1)[0]
    for tell in ("默认值是 `private`", "v1.0-smoke-public"):
        assert tell in body, f"§2.4 没写清楚为什么必须带 `--channel public`（缺「{tell}」）"


# ============================================================ ⑤ README §2.1：先收紧、再自检

def test_the_readme_hardens_before_it_selfchecks():
    """§2.1 的块里 `guard_modes --harden` 必须排在 `selfcheck_public.py` **前面**。

    venv 按 README 自己的硬要求建在 `$GB/env`，`pip` 装出来的 `.so`/`.py` 对组/其它开放，
    而那道审计走的正是 `$GB` **全树** —— 先自检就一定是红（外部实测 113 条「模式放松」、
    网关拒启、退 1），而块跑完没人叫他复跑。**照抄跑完最后一眼必须是好的。**
    """
    block = _readme_block("### 2.1 共同前置")
    i_h = block.find("guard_modes.py --harden")
    i_s = block.find("selfcheck_public.py")
    assert i_h >= 0, "§2.1 的块里没有 guard_modes.py --harden"
    assert i_s >= 0, "§2.1 的块里没有 selfcheck_public.py"
    assert i_h < i_s, (
        "§2.1 里 selfcheck 排在 --harden 前面 —— 照抄的人最后一眼会停在一个退 1 的自检上。"
        "要么把两行对调，要么在块尾补一行复跑。")


# ============================================================ ⑥ d2_e2e：文档引的那份证据真的在手上

D2 = REPO / "ops" / "reports" / "d2_e2e"


def test_the_d2_e2e_evidence_the_docs_point_at_is_actually_in_the_tree():
    """README §2.4 与手册 §5.3 拿这次端到端的终态分布劝人「别读成自己配错了」——
    那份证据得真的在读者手上。"""
    assert D2.is_dir(), (
        "ops/reports/d2_e2e/ 不在树里，而 README 与手册都引着它 —— "
        "要么把证据放进来，要么改措辞不再引一个拿不到的目录")
    for f in ("README.md", "run_states.csv", "table_main_excerpt.csv"):
        assert (D2 / f).is_file(), f"ops/reports/d2_e2e/{f} 不在"


def test_the_d2_e2e_distribution_matches_what_both_docs_claim():
    """盘上那六行的终态分布 == 两处文档写的分布。两边分叉时红的是文档。"""
    rows = [ln for ln in (D2 / "run_states.csv").read_text(encoding="utf-8").splitlines()[1:] if ln.strip()]
    assert len(rows) == 6, f"run_states.csv 有 {len(rows)} 行，文档说的是 6 个 run"
    from collections import Counter
    dist = Counter(r.split(",")[1] for r in rows)
    assert dist == Counter({"budget_exhausted": 3, "timeout": 1, "ok": 1, "violation": 1}), dist
    used_full = sum(1 for r in rows if r.split(",")[3] == "100")
    assert used_full == 4, f"用满 100 次调用的是 {used_full} 个，两处文档写的是「四个」"
    for txt, who in ((README_TEXT, "README"), (MANUAL_TEXT, "手册")):
        assert "3 个 `budget_exhausted` / 1 个 `timeout`" in txt, (
            f"{who} 里那句终态分布改了，而 ops/reports/d2_e2e/run_states.csv 没跟着改")


def test_the_d2_e2e_table_header_is_the_24_column_one():
    """那张表的表头 = 19 指标列 + 5 身份列 = 24 列，而且与 README §2.4 说的身份列对得上。

    文件叫 `_excerpt` 而不是 `table_main.csv`：后者是 `ops/test_V2.py::_main_table_dirs()`
    用来**认批**的名字，而 `d2_e2e` 不是一个批的产物目录，是一份摘录证据。
    """
    head = (D2 / "table_main_excerpt.csv").read_text(encoding="utf-8").splitlines()[0]
    cols = head.split(",")
    assert len(cols) == 24, f"表头有 {len(cols)} 列，README §2.4 说的是 24 列：{cols}"
    assert cols[:5] == ["config_id", "arm", "arm_kind", "n_tasks", "n_runs"], cols[:5]
    assert "total" not in cols and "overall" not in cols and "score" not in cols, (
        "主表不许有总分列 —— 少了那一列不是漏了，是刻意的")
