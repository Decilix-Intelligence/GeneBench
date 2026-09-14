# -*- coding: utf-8 -*-
"""卡 6.2：运行者手册 `docs/OPERATOR_MANUAL.md` 的判据。

**这份测试要挡住的是哪一类失败**：手册与仓库漂开。手册里那条命令指的文件被人挪走了、
某个 `--flag` 被改名或删掉了 —— 这两件事**不会让别的任何测试变红**，
而它们恰恰就是「外部运行者按手册能不能用」的全部内容：
用户看到的是 `No such file or directory` 或 `unrecognized arguments`，
而那两句话看起来都像是**他自己**装错了。

所以判据两条（照卡 3.rt 的**双向**写法）：

  ① 手册里提到的每个仓库路径真的存在（占位 `<...>` / `{...}` / `*` 除外）；
  ② 手册里每条命令用到的每个 `--flag`，在对应脚本的 `--help` 里真的有。

**双向的另一半**：光有上面两条还不够 —— 一个匹配不到任何东西的正则同样是全绿的。
所以另有三条「提取器自己没瞎」的下界断言（`test_the_extractors_actually_found_things`），
以及一组「手册说的与代码里的是同一件事」的对照（七个配置键、两组四条版本轴、锁的落点）。

`--help` 是**真的去跑**那个脚本拿的（带 120 秒超时、`PYTHONDONTWRITEBYTECODE=1`）。
拿不到 `--help` 的脚本（`.sh`）退回「flag 字面量在脚本正文里出现过」。
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
MANUAL = REPO / "docs" / "OPERATOR_MANUAL.md"
PY = sys.executable

TEXT = MANUAL.read_text(encoding="utf-8") if MANUAL.exists() else ""


# ============================================================ 手册在不在

def test_manual_exists_and_is_not_a_stub():
    assert MANUAL.exists(), "docs/OPERATOR_MANUAL.md 不在 —— 它是外部运行者的入口"
    assert len(TEXT) > 12000, (
        f"手册只有 {len(TEXT)} 字符 —— 八节（部署/加配置/加 harness/接系统/跑清单/"
        f"结算读表/常见错误/附录）装不下")


REQUIRED_SECTIONS = (
    "## 1. 部署",
    "## 2. 加配置",
    "## 3. 加一个通用 harness",
    "## 4. 接一个专用系统",
    "## 5. 跑一批",
    "## 6. 结算与读表",
    "## 7. 常见错误",
    "## 8. 附录",
)


@pytest.mark.parametrize("head", REQUIRED_SECTIONS)
def test_every_required_section_is_present(head: str):
    assert head in TEXT, f"手册缺一节：{head}"


# ============================================================ ① 路径

#: 仓库里的一级目录 —— 命令与正文里出现 `<这些>/...` 的形态就当成一条仓库路径来核。
TOP = ("ops", "harnesses", "integrations", "docs",
       "runner", "gateway", "genetask", "reference", "scorer", "snapshots")
_PATH = re.compile(r"(?<![A-Za-z0-9_./-])(?:%s)/[A-Za-z0-9_./-]*" % "|".join(TOP))


def _placeholder(tok: str) -> bool:
    """占位符不核：`<id>`、`{stage}`、`table_*.csv` 这类。"""
    return any(ch in tok for ch in "<>{}*")


def _clean(raw: str) -> str:
    return raw.rstrip(".,;:)`\"'/")


def referenced_paths() -> list[str]:
    """手册里提到的仓库路径。

    占位符要从**两头**认：token 自身带 `<>{}*` 的（`ops/joblists/<name>.yaml`），
    以及 token 恰好停在占位符前面的（`ops/reports/signed/v<集版本>_…`、`ops/test_*`）——
    后者只看 token 自己是看不出来的，要看紧跟其后的那个字符。
    """
    out = set()
    for m in _PATH.finditer(TEXT):
        nxt = TEXT[m.end():m.end() + 1]
        if nxt in ("<", "{", "*"):
            continue
        tok = _clean(m.group(0))
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
def test_every_repo_path_named_in_the_manual_exists(rel: str):
    """手册指的每个仓库路径都在。

    这是「外部运行者按手册能否用」的最低限度：文件被挪走而手册没改，
    用户拿到的是 `No such file or directory`，而那看起来像他自己装错了。
    """
    out = judge_path(rel)
    if out.startswith("SKIP:"):
        pytest.skip(out[len("SKIP:"):])


# ============================================================ ② --flag

#: 命令行里的脚本 token。允许前缀（`exec/ops/run_f02_a1.py` 是执行面上那份的写法）。
_SCRIPT = re.compile(r"(?:[A-Za-z0-9_./-]*/)?(?:%s)/[A-Za-z0-9_./-]*\.(?:py|sh)" % "|".join(TOP))
_FLAG = re.compile(r"(?<![\w-])--[a-z][a-z0-9-]*")
_SUBCMD = re.compile(r"^[a-z][a-z_]+$")

#: `--help` 拿不到的（shell 脚本）退回正文字面量搜索。
_SHELLISH = (".sh",)


def _resolve_script(tok: str) -> Path | None:
    """把命令里的 token 解成仓库里的真文件。

    `exec/ops/run_f02_a1.py` 是执行面 `exec/` 树里的同一个文件 —— 剥掉前缀再解。
    解不出来就返回 None（那条 flag 不判，但会被下界断言数出来）。
    """
    cand = [tok]
    for i, part in enumerate(tok.split("/")):
        if part in TOP:
            cand.append("/".join(tok.split("/")[i:]))
            break
    for c in cand:
        p = REPO / c
        if p.is_file():
            return p
    return None


def _code_lines() -> list[list[str]]:
    """按代码块切：每个 ``` 围栏内的行是一段。手册正文（散文）不参与 flag 判据。"""
    blocks, cur, inside = [], [], False
    for line in TEXT.splitlines():
        if line.lstrip().startswith("```"):
            if inside:
                blocks.append(cur); cur = []
            inside = not inside
            continue
        if inside:
            cur.append(line)
    if cur:
        blocks.append(cur)
    return blocks


def flag_uses() -> list[tuple[str, str, str]]:
    """→ `(脚本相对路径, 子命令或 '', flag)` 三元组。

    归属规则：一条 flag 归**最近一个在它之前出现过的脚本 token**。
    续行（上一行以 `\\` 结尾）沿用上一行的脚本；否则每一行重置 ——
    否则 `grep -n -- --gateway …` 这种紧跟在命令后面的行会把 flag 记到上一条命令头上。
    """
    out: list[tuple[str, str, str]] = []
    for block in _code_lines():
        cur_script: Path | None = None
        cur_sub = ""
        cont = False
        for line in block:
            if not cont:
                cur_script, cur_sub = None, ""
            # 逐个「事件」按位置扫：脚本 token 换绑定，flag 落到当前绑定上
            events = [(m.start(), "s", m.group(0)) for m in _SCRIPT.finditer(line)]
            events += [(m.start(), "f", m.group(0)) for m in _FLAG.finditer(line)]
            events.sort()
            for pos, kind, tok in events:
                if kind == "s":
                    cur_script = _resolve_script(tok)
                    cur_sub = ""
                    tail = line[pos + len(tok):].split()
                    if tail and _SUBCMD.match(tail[0]):
                        cur_sub = tail[0]
                elif cur_script is not None:
                    out.append((str(cur_script.relative_to(REPO)), cur_sub, tok))
            cont = line.rstrip().endswith("\\")
    # 去重，顺序稳定
    return sorted(set(out))


def _help_text(script: Path, sub: str) -> str:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", COLUMNS="200")
    argv = [PY, str(script)] + ([sub] if sub else []) + ["--help"]
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=120,
                           cwd=str(REPO), env=env)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return (r.stdout or "") + (r.stderr or "")


_HELP_CACHE: dict[tuple[str, str], str] = {}


def help_of(rel: str, sub: str) -> str:
    key = (rel, sub)
    if key not in _HELP_CACHE:
        p = REPO / rel
        if p.suffix in _SHELLISH:
            _HELP_CACHE[key] = p.read_text(encoding="utf-8", errors="replace")
        else:
            text = _help_text(p, sub)
            if sub and "--help" not in text:      # 子命令不认，退回顶层 help
                text = _help_text(p, "")
            _HELP_CACHE[key] = text
    return _HELP_CACHE[key]


@pytest.mark.parametrize("rel,sub,flag", flag_uses())
def test_every_flag_used_in_the_manual_really_exists(rel: str, sub: str, flag: str):
    """手册写的每个 `--flag`，那个脚本真的认。

    `.py` 判据是**真的跑一次 `--help`**（子命令的话先试 `<sub> --help`，
    不认再退回顶层）；`.sh` 没有 argparse，判据是 flag 字面量在脚本正文里出现过。
    反过来漂开的表现是 `unrecognized arguments: --xxx`，而运行者会以为是自己抄错了。
    """
    text = help_of(rel, sub)
    assert text, f"{rel} 的 --help 一个字都拿不到 —— 判据自身失效，先修这个"
    where = f"{rel}{(' ' + sub) if sub else ''}"
    assert flag in text, (
        f"手册在 `{where}` 上用了 {flag}，但它的 --help 里没有这个开关。"
        f"要么手册过期了，要么这次改名漏了一处。")


# ============================================================ 双向：提取器自己没瞎

def test_the_extractors_actually_found_things():
    """一个匹配不到任何东西的正则同样是全绿的 —— 所以给三条下界。

    数字取的是「明显低于现状、但高到足以证明提取器在工作」的量级：
    手册收口时实测 路径 60+ / flag 45+ / 脚本 12+。
    """
    paths = referenced_paths()
    uses = flag_uses()
    scripts = {rel for rel, _, _ in uses}
    assert len(paths) >= 40, f"只提取到 {len(paths)} 条仓库路径 —— 提取器多半坏了"
    assert len(uses) >= 35, f"只提取到 {len(uses)} 条 flag 用法 —— 提取器多半坏了"
    assert len(scripts) >= 10, f"只覆盖到 {len(scripts)} 个脚本：{sorted(scripts)}"


def test_the_manual_covers_the_six_entry_points_of_a_batch():
    """跑一批的六个入口一个都不能少（少一个，运行者就得回去读 HANDOFF）。"""
    for rel in ("ops/joblist.py", "ops/run_joblist.py", "ops/results_db.py",
                "ops/mk_tables.py", "ops/score_runs.py", "ops/export_bundle.py"):
        assert rel in TEXT, f"手册没提 {rel}"


# ============================================================ 手册说的 == 代码里的

def test_the_seven_config_keys_are_exactly_the_registry_ones():
    """§2 的七个键必须与 `runner.registry.CONFIG_KEYS` 逐个对上。

    键集是闭集：多一个键在写它的人眼里像是生效了，其实是静默忽略 ——
    手册漏写或多写一个，等于把那个失败形态搬到运行者头上。
    """
    from runner import registry as REG
    section = TEXT.split("### 2.1")[1].split("### 2.2")[0]
    for k in REG.CONFIG_KEYS:
        assert f"`{k}`" in section, f"手册 §2.1 的七键表里没有 {k}"
    bogus = re.findall(r"^\| `([a-z_]+)` \|", section, flags=re.M)
    assert set(bogus) == set(REG.CONFIG_KEYS), (
        f"手册列的键 {sorted(set(bogus))} ≠ registry.CONFIG_KEYS {sorted(REG.CONFIG_KEYS)}")


def test_the_two_groups_of_four_version_axes_are_both_spelled_out():
    """§6.4 那张「两组四条轴不是同一组」的表 —— 八个名字一个都不能少。

    这是全手册最容易被读错的一处：表列上的四条（注入面写的）与表脚注上的四条
    （库判可比性用的）名字有重叠、含义不同。
    """
    from ops import results_db as DB
    from scorer import report as R
    section = TEXT.split("### 6.4")[1].split("### 6.5")[0]
    for ax in R.VERSION_AXES:
        assert f"`{ax}`" in section, f"§6.4 没写 scorer.report.VERSION_AXES 里的 {ax}"
    for ax in DB.AXES:
        assert f"`{ax}`" in section, f"§6.4 没写 results_db.AXES 里的 {ax}"
    assert set(R.VERSION_AXES) != set(DB.AXES), "两组要是相同的，这一节就不必存在了"


def test_the_gateway_lock_path_in_the_manual_is_the_real_one():
    """§8.2 写的锁落点必须就是代码里那一个（手册按 `$GB/` 相对写，便于搬家）。

    <!-- Y-2026-09-13 -->
    **这条判据本身以前取决于跑它的是不是发布方那台机器**，而这正是本轮要扫的那一族：
    它原来写成 `GL.LOCK.relative_to(cfg.GENEBENCH_ROOT)` —— 在发布方机器上两者同根、跑得通；
    在任何外部机器上 `GL.LOCK` 是写死的发布方绝对路径、`cfg.GENEBENCH_ROOT` 是用户自己的根，
    于是 `relative_to` 抛 **`ValueError`**，而手册 §8.6 恰恰**明确请外部用户跑这个文件**
    （卡 Xfin 在一台外部机器上实测到这一条）。

    **判据要验的东西一个字没放宽**：手册写的锁落点必须与代码里那一个是**同一条**。
    只是改成按「根之下那一截」比，而不是按「相对发布方的根」算 —— 在发布方机器上
    两种算法**逐字同值**，换任何一台机器它也照样有牙（手册把 `locks/` 写成别的，当场红）。
    `ops/gateway_lock.py::LOCK` 自己写死发布方绝对路径是**另一件事**（代码侧，本卡改不到那个
    路径），已登记。
    """
    from ops import gateway_lock as GL
    tail = f"{GL.LOCK.parent.name}/{GL.LOCK.name}"
    assert f"$GB/{tail}" in TEXT, (
        f"手册没写网关锁的真落点（$GB/{tail}）—— "
        f"代码里的锁是 {GL.LOCK}，运行者照手册去找会找错地方")


def test_the_runner_core_constants_named_in_the_manual_still_exist():
    """§1.3 让运行者改的那两个常量，模块里得真有。

    这一条是给**将来**准备的：网关上游地址正在从常量变成环境变量
    （`gateway_addr()` / `GATEWAY_DEFAULT`），常量一旦改名，§1.3 那张表就把运行者指到
    一个不存在的符号上，而**没有别的测试会红**。所以判据写成「两种形态各认一个名字，
    手册必须提到树上真有的那一个」——过渡期两边都绿，改完名字之后手册漏改就红。
    """
    from runner.c41 import runner_core as RC
    assert hasattr(RC, "LAN") and "`runner/c41/runner_core.py::LAN`" in TEXT, \
        "§1.3 得写 runner_core.LAN"
    names = [n for n in ("GATEWAY", "GATEWAY_DEFAULT") if hasattr(RC, n)]
    assert names, "runner_core 里既没有 GATEWAY 也没有 GATEWAY_DEFAULT —— 手册和代码都要查"
    for n in names:
        assert f"`{n}`" in TEXT, (
            f"runner_core 里有 {n}，手册 §1.3 却没提它 —— "
            f"运行者会照着手册去改一个不存在的常量")
    if hasattr(RC, "gateway_addr"):
        assert "GENEBENCH_GATEWAY_ADDR" in TEXT, (
            "树上已经有 gateway_addr()，手册还在只讲改常量 —— §1.3 要补环境变量那条路")


def test_the_default_budget_and_the_documented_workaround_are_both_stated():
    """默认 token 档会把「能力读数」变成「预算读数」——这件事必须写在手册里。

    判据两头都钉：一头是 registry 的**真值**，一头是手册给的绕法与那张待裁定的票。
    抬默认档是用户裁定项（N-388）；在裁定之前手册只能写绕法，不能假装档位够用。
    """
    from runner import registry as REG
    assert f"{REG.RUN_BUDGET['max_tokens']:,}" in TEXT or \
           str(REG.RUN_BUDGET["max_tokens"]) in TEXT, "手册没写默认 token 档的真值"
    assert "3000000" in TEXT, "手册没给显式 3M 的绕法"
    assert "N-388" in TEXT, "手册没写这是一条待用户裁定的票（N-388）"
    assert str(REG.RUNNER_CONCURRENCY) in TEXT.split("### 5.5")[1].split("### 5.6")[0], \
        "§5.5 没写并发数的真值"


def test_the_manual_states_the_three_release_blockers():
    """§0.1 必须如实摆着三件挡发布的事 —— 不许粉饰成「即将可用」。"""
    head = TEXT.split("### 0.2")[0]
    for token in ("baostock", "pending_license_text", "publishable=false",
                  "git remote", "factor_library/compiled"):
        assert token in head, f"§0.1 没写「{token}」这一条"


def test_the_two_deployment_forms_are_both_described():
    """§1 必须两种形态都有，并且单机形态的那条防火墙前提要写出来。"""
    section = TEXT.split("## 1. 部署")[1].split("## 2. 加配置")[0]
    for token in ("形态 ①", "形态 ②", "18080", "internal: true"):
        assert token in section, f"§1 没写「{token}」"
    assert "未端到端验证" in section, (
        "单机形态还没整条跑过 —— 手册必须写明它验到了哪一步，不能让运行者以为是验过的")


def test_the_common_errors_section_covers_every_symptom_the_card_named():
    """§7 至少要覆盖任务书点名的九类症状。"""
    section = TEXT.split("## 7. 常见错误")[1].split("## 8. 附录")[0]
    for token in ("通行证", "budget_exhausted", "no_artifact", "malformed",
                  "identity_mismatch", "ExecStartPre", "gateway.lock",
                  "湖写锁", "--with-launch-data", "混轴"):
        assert token in section, f"§7 没覆盖「{token}」这一类"
