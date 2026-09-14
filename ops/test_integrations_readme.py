# -*- coding: utf-8 -*-
"""卡 2.4：接入指南 `integrations/README.md` 与 30 行最小示例的判据。

**这份测试要挡住的是哪一类失败**：手册与仓库漂开。手册里那条命令指的文件被人挪走了、
`COVERAGE.md` 的表头被改成七列、最小示例被改到跑不动 —— 这三件事都**不会**让别的测试变红，
而它们恰恰是「外部用户按手册能不能用」的全部内容。

所以判据是三条：
  ① 手册里每条命令提到的仓库路径**真的存在**（占位 `<...>` 除外）；
  ② `example_minimal` **真的能跑**，且产物过协议 validator；
  ③ `COVERAGE.md` 存在且表头恰好是 S1..S8。

②那条打生产网关（几十个请求以内、只读、独立身份），按任务书属于「不需要 gateway_lock」
的那一类。网关确实没了的时候它 skip；连不上以外的任何失败照红。
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
INTEG = REPO / "integrations"
README = INTEG / "README.md"
COVERAGE = INTEG / "COVERAGE.md"
EXAMPLE = INTEG / "example_minimal"

TEXT = README.read_text(encoding="utf-8") if README.exists() else ""


# ---------------------------------------------------------------- ① 手册里的路径

#: 仓库里的一级目录。命令里出现 `<这些>/...` 的形态就当成一条仓库路径来核。
TOP = ("ops", "integrations", "harnesses", "runner", "gateway", "reference", "genetask")
_PATH = re.compile(r"(?<![\w./-])(?:%s)/[\w./-]+" % "|".join(TOP))
_MODULE = re.compile(r"-m\s+([a-z_][\w.]*)")


def _placeholder(tok: str) -> bool:
    """占位符不核：`<id>`、`<你的卡号>`、`{stage}` 这类。"""
    return any(ch in tok for ch in "<>{}*") or tok.endswith((".", ","))


def _referenced_paths() -> list[str]:
    out: list[str] = []
    for raw in _PATH.findall(TEXT):
        tok = raw.rstrip(".,;:)`\"'")
        if not _placeholder(tok):
            out.append(tok)
    return sorted(set(out))


def test_readme_exists():
    assert README.exists(), "integrations/README.md 不在 —— 接入指南是 P2 作者的入口"
    assert len(TEXT) > 4000, "手册太短了，八步 + 常见失败装不下"


@pytest.mark.parametrize("rel", _referenced_paths())
def test_every_repo_path_named_in_the_readme_exists(rel: str):
    """手册指的每个仓库路径都在。

    这条是「外部用户按手册能否用」的最低限度：命令里的文件被挪走了而手册没改，
    用户看到的是 `No such file or directory`，而那看起来像**他自己**装错了。
    """
    assert (REPO / rel).exists(), (
        f"手册里提到 {rel}，但仓库里没有这个路径。"
        f"要么改手册，要么这次移动漏了一处。")


def test_every_module_invocation_in_the_readme_resolves():
    """`$PY -m integrations.cost` 这类要真有那个包。"""
    for mod in set(_MODULE.findall(TEXT)):
        if mod in ("pytest", "pip", "venv"):
            continue
        d = REPO / Path(*mod.split("."))
        assert d.is_dir() or d.with_suffix(".py").exists(), f"手册里 -m {mod}，但仓库里没有它"


def test_every_relative_link_in_the_readme_resolves():
    """`[...](x/y)` 形式的相对链接（相对 integrations/）。"""
    bad = []
    for target in re.findall(r"\]\(([^)]+)\)", TEXT):
        if target.startswith(("http://", "https://", "#")) or _placeholder(target):
            continue
        t = target.split("#", 1)[0]
        if t and not (INTEG / t).exists():
            bad.append(target)
    assert not bad, f"这些相对链接指向不存在的东西：{bad}"


# ---------------------------------------------------------------- 手册自身的形态

def test_the_three_paradigms_are_all_explained_in_one_place():
    for token in ("P1", "P2", "P3", "/task/protocol"):
        assert token in TEXT, f"三范式那一节缺 {token}"
    assert "harnesses/README.md" in TEXT, "P1/P3 要把读者指到 harnesses/README.md"


def test_the_eight_steps_are_numbered_and_each_carries_a_command():
    """八步每一步都要有一条可以复制的命令 —— 「大概这样做」不是手册。"""
    for step in "①②③④⑤⑥⑦⑧":
        assert step in TEXT, f"接入八步里缺第 {step} 步"


def test_the_merged_sections_are_not_kept_twice():
    """卡 2.2 与卡 2.5 追加的两节被**整合**进来，不是并排放两份。

    两份的表现是：读者照着旧的那份做，而旧的那份没人维护。
    """
    heads = [l for l in TEXT.splitlines() if l.startswith("## ")]
    assert sum("接入成本怎么记" in h for h in heads) == 1, heads
    assert sum("取数垫片" in h for h in heads) == 1, heads
    assert "接入成本怎么记（卡 2.5）" not in TEXT, "卡 2.5 的旧标题还在 —— 整合没做干净"


def test_the_budget_gate_is_documented_as_429_not_402():
    """规格冲突的落点：预算闸实报 429 `budget_exceeded`，全树没有 HTTP 402。

    照 402 写重试分支的被测方，那条分支永远不触发 —— 所以手册必须写 429，
    并且必须把这处冲突讲出来而不是悄悄改掉。
    """
    assert "budget_exceeded" in TEXT
    assert "429" in TEXT
    seg = TEXT[TEXT.find("### 3.3"): TEXT.find("### 3.4")]
    assert "402" in seg, "要显式说明「写 402 的地方是错的」，不能只把数字换掉"



def _fenced(seg: str) -> str:
    """一段 markdown 里**围栏代码块**的内容 —— 断言「可复制的命令里不许有 X」只能看这里。

    正文里解释「为什么不要给 `--max-tokens`」时一定会出现这个字符串，按整段断言会把
    解释本身判成违规（卡 W.rt 踩过一次）。
    """
    parts = seg.split("```")
    return "\n".join(parts[i] for i in range(1, len(parts), 2))

def test_the_budget_default_and_the_explicit_override_are_both_right():
    """预算这件事在手册里出现四处，四处必须说的是同一件事。

    **N-388（2026-09-10 用户裁定）之后这条断言整个翻了个方向**：权威
    `runner/registry.py::RUN_BUDGET` 的默认档从 600,000 抬到 **6,000,000**，
    于是旧的绕法「真跑时显式给 `--max-tokens 3000000`」变成**把预算压低**
    （3M < 6M，而且显式值逐键赢过 `BUDGET_TIERS`，S4 的 9M 与 S7 的 18M 会一起被打回去）。
    所以现在两件事要在：默认值写的是 6,000,000，**可复制的命令里一个预算参数都不给**。

    原断言（`RUN_BUDGET["max_tokens"] == 600_000` + 命令里要有 3000000）自 W1 抬档之后一直红 ——
    W1 同步了 `README.md` / `docs/OPERATOR_MANUAL.md` / `ops/joblists` / `P2_CONTRACT.md`，
    **漏了 `integrations/README.md` 与 `harnesses/README.md`**（红队 W.rt finding 3）。
    """
    from runner import registry as REG
    assert REG.RUN_BUDGET["max_tokens"] == 6_000_000, (
        f"RUN_BUDGET 变了（现在 {REG.RUN_BUDGET}）—— 手册里的默认值要跟着改")
    assert REG.RUN_BUDGET["max_calls"] == 100, REG.RUN_BUDGET

    assert "RUN_BUDGET" in TEXT, "手册要指出预算的权威在 runner/registry.py::RUN_BUDGET"
    assert "6,000,000" in TEXT or "6_000_000" in TEXT, "默认值 6M 要写出来"
    assert "43k" in TEXT or "43,000" in TEXT, "要给出「6M 是怎么算的」的量级依据"

    # 可复制的那条真跑命令里，预算参数一个都不给 —— 让注入器按 stage 取档。
    cmd = _fenced(TEXT[TEXT.find("### ⑥"):TEXT.find("### ⑦")])
    assert cmd.strip(), "§1⑥ 里一个命令块都没有 —— 断言会恒绿"
    assert "--max-tokens" not in cmd, "§1⑥ 的真跑命令不许给 --max-tokens（逐键压过档位）"
    assert "--max-calls" not in cmd, "§1⑥ 的真跑命令不许给 --max-calls（会把 S4/S7 档位关掉）"


def test_the_cross_tree_name_uniqueness_rule_is_stated():
    """`harness` 名与 `config_id` 跨 harnesses/ 与 integrations/ 两棵树也不许重复。

    这是 W-0 schema 的硬规则，`RegistryError` 在 import 期就抛。手册漏了它，
    读者的表现是「我明明加了却没生效」—— 那会变成一次长调查。
    """
    seg = TEXT[TEXT.find("### ②"):TEXT.find("### ③")]
    assert seg, "找不到 §1② 那一节"
    assert "两棵树" in seg and "不许重复" in seg, (
        "跨树重名这条规则不在 §1②（建目录那一步）里 —— 读者是在那一步给 harness "
        "命名的，写在别处等于没写")
    assert "RegistryError" in seg, "要写明重名的后果是 import 期 RegistryError"


def test_the_home_divergence_from_harnesses_readme_is_declared():
    """手册对 P2 说 HOME 放 /tmp，而 harnesses/README.md 对 P1 说放 /task 下。

    两条都跑得通，但读者会同时读到这两份。默默给一条、当另一条不存在，
    表现是读者按另一份做完之后不知道自己踩没踩到 P8 的 `unexpected`。
    所以必须**显式**把出入讲出来，并说清各自的理由。
    """
    seg = TEXT[TEXT.find("### ④"):TEXT.find("### ⑤")]
    assert "/tmp" in seg, "§1④ 要给出 P2 的写法"
    assert "harnesses/README.md" in seg, "§1④ 要指出与 harnesses/README.md 的出入"
    assert "unexpected" in seg, "要说明落在 /task 下的代价是 run.json 的 unexpected"
    hr = (REPO / "harnesses" / "README.md")
    if hr.exists():
        assert "`/task` 下的可写处" in hr.read_text(encoding="utf-8"), (
            "harnesses/README.md 的原文变了 —— §1④ 引的那句要跟着核一遍")


def test_the_common_failures_section_covers_all_ten():
    seg = TEXT[TEXT.find("## 3. 常见失败的含义"):]
    for token in ("403", "422", "budget_exceeded", "NoData", "no_artifact",
                  "malformed", "EAI_AGAIN", "HOME", "0775"):
        assert token in seg, f"常见失败一节里没有 {token}"
    assert "3 秒" in seg or "3秒" in seg, "「两臂 3 秒退出」那条不在"


# ---------------------------------------------------------------- ③ COVERAGE.md

def test_coverage_exists_and_its_header_is_s1_to_s8():
    assert COVERAGE.exists(), "integrations/COVERAGE.md 不在"
    lines = [l for l in COVERAGE.read_text(encoding="utf-8").splitlines()
             if l.strip().startswith("|")]
    header = next((l for l in lines if "S1" in l and "S8" in l), None)
    assert header, "找不到那张矩阵的表头"
    cells = [c.strip().strip("`*") for c in header.strip().strip("|").split("|")]
    stages = [c for c in cells if re.fullmatch(r"S[1-8]", c)]
    assert stages == [f"S{i}" for i in range(1, 9)], (
        f"表头的阶段列必须恰好是 S1..S8，实际是 {stages}")


def test_coverage_defines_every_cell_value_it_allows():
    text = COVERAGE.read_text(encoding="utf-8")
    for v in ("passed", "invalid", "malformed", "no_artifact"):
        assert f"`{v}`" in text, f"COVERAGE.md 没有定义格值 {v}"
    assert "只写" in text and "实测" in text, "必须写明「只写实测过的」"


def test_coverage_rows_only_use_defined_values():
    """已经写进去的行，格值必须是定义过的那五个之一 —— 「应该能跑」不是格值。"""
    allowed = {"passed", "invalid", "malformed", "no_artifact", "—", "-", ""}
    text = COVERAGE.read_text(encoding="utf-8")
    body = text[text.find("| 系统"):].splitlines()[2:]
    bad = []
    for line in body:
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
        for c in cells[2:10]:
            if c not in allowed:
                bad.append((line.split("|")[1].strip(), c))
    assert not bad, f"COVERAGE.md 里有没定义过的格值：{bad}"


# ---------------------------------------------------------------- ② 最小示例

def test_example_minimal_is_a_complete_five_piece_set():
    for name in ("run.py", "Dockerfile", "pin.json", "README.md", "smoke.sh"):
        assert (EXAMPLE / name).exists(), f"example_minimal 少了 {name}"


def _body_lines(src: str) -> list[str]:
    """正文 = 去掉模块 docstring、空行、纯注释行之后剩下的。"""
    lines = src.splitlines()
    s = next(i for i, l in enumerate(lines) if l.startswith('"""'))
    e = next(i for i, l in enumerate(lines) if i > s and l.rstrip().endswith('"""'))
    skip = set(range(s, e + 1))
    return [l for i, l in enumerate(lines)
            if l.strip() and not l.strip().startswith("#") and i not in skip]


def test_the_thirty_line_example_is_actually_thirty_lines():
    """手册说「30 行」，那它就得是 30 行。

    这条不是形式主义：最小示例的价值全在「小到能一眼读完」，
    悄悄长到 80 行之后它就成了另一个要维护的系统。
    """
    n = len(_body_lines((EXAMPLE / "run.py").read_text(encoding="utf-8")))
    assert n == 30, f"run.py 正文 {n} 行，手册说 30 行"


def test_the_readme_excerpt_is_verbatim_run_py():
    """手册 §2 贴的那段代码必须与 `run.py` 逐字一致。

    手册里的代码块是读者第一眼看到的东西，也是最容易悄悄漂开的东西：
    改了文件没改手册，读者照着手册抄一份**跑不起来的**代码，而且看不出是谁错了。
    """
    m = re.search(r"```python\n# integrations/example_minimal/run\.py[^\n]*\n(.*?)```",
                  TEXT, re.S)
    assert m, "手册 §2 里找不到那段 run.py 摘录"
    excerpt = m.group(1).rstrip()
    src = (EXAMPLE / "run.py").read_text(encoding="utf-8").splitlines()
    s = next(i for i, l in enumerate(src) if l.startswith("import os,"))
    e = next(i for i, l in enumerate(src) if l.strip() == 'if __name__ == "__main__":')
    assert excerpt == "\n".join(src[s:e]).rstrip(), (
        "手册里的摘录与 run.py 不一致 —— 改了文件请把手册那一段一起换掉")


def test_the_example_never_guesses_as_of():
    src = (EXAMPLE / "run.py").read_text(encoding="utf-8")
    assert "SystemExit" in src, "槽位缺失时必须退出，不是取一个默认值"
    assert not re.search(r"as_of\s*=\s*[\"']20\d\d", src), "示例里不许写死一个 as_of"


@pytest.mark.parametrize("name", ["launch.json", "config.yaml"])
def test_example_launch_and_config_match_the_w0_schema(name: str):
    """六个键 / 七个键，缺一个多一个都在 import 期 RegistryError。"""
    p = EXAMPLE / name
    if not p.exists():
        pytest.skip(f"{name} 不在（示例可以只给代码）")
    if name == "launch.json":
        spec = json.loads(p.read_text(encoding="utf-8"))
        assert set(spec) == {"harness", "paradigm", "image", "command",
                             "env_required", "notes"}
        assert spec["paradigm"] == "P2"
        cmd = " ".join(spec["command"])
        for m in re.finditer(r"\$+", cmd):
            assert len(m.group()) % 2 == 0, f"命令里的 $ 要写成 $$（N-101）：{cmd}"
    else:
        keys = {l.split(":", 1)[0].strip() for l in p.read_text(encoding="utf-8").splitlines()
                if l.strip() and not l.strip().startswith("#") and ":" in l}
        assert keys == {"config_id", "harness", "model", "base_url",
                        "api_key_env", "note", "enabled"}
        assert "enabled: false" in p.read_text(encoding="utf-8")


def test_example_pin_json_has_the_d21_keys():
    pin = json.loads((EXAMPLE / "pin.json").read_text(encoding="utf-8"))
    assert set(pin) == {"paper_url", "repo_url", "commit", "dist",
                        "dist_repo_url", "license", "runnable_check"}
    assert pin["runnable_check"], "runnable_check 不能空 —— 它回答「镜像里到底装没装上」"


# ---------------------------------------------------------------- 真跑一遍

def _gateway_url() -> str:
    try:
        import genebench_config as cfg
        return f"http://{cfg.GATEWAY_HOST}:{cfg.gateway_port()}"
    except Exception:
        return os.environ.get("GENEBENCH_GATEWAY", "http://192.168.1.48:18080")


def _narrow_gate():
    """复用卡 2.2 那道**更窄**的门（只放行回环与网关主机）。

    `ops/test_env.py` 的 session 级离线守卫会把「打 LAN 上的网关」判成出网，
    于是全量里凡是要局域网的测试都红（单跑全绿）。卡 2.2 的自救是在真打期间换上
    一道**更严**的门。守卫修好之后这里会自然回落到 `nullcontext`。
    """
    try:
        from ops.test_genebench_client import _only_gateway_egress  # type: ignore
        return _only_gateway_egress()
    except Exception:
        return contextlib.nullcontext()


def test_the_example_runs_end_to_end_and_its_artifact_passes_the_validator(tmp_path):
    """按手册跑一遍最小示例：打生产网关取数、写产物、过协议 validator。

    这是本卡唯一一条**真运行**的判据。它红了通常意味着三件事之一：
    垫片的接口变了、题面槽位写法变了、或者 validator 的规则变了 —— 三件都该红。
    """
    gb = Path(os.environ.get("GENEBENCH_ROOT", "/data/shared/genebench"))
    if not gb.is_dir():
        pytest.skip(f"{gb} 不在 —— 这条判据只在数据面（f01）上有意义")
    smoke = EXAMPLE / "smoke.sh"
    env = dict(os.environ)
    env["GENEBENCH_GATEWAY"] = _gateway_url()
    env["REPO"] = str(REPO)
    env["PY"] = sys.executable
    with _narrow_gate():
        proc = subprocess.run(["sh", str(smoke)], cwd=str(REPO), env=env,
                              capture_output=True, text=True, timeout=600)
    out = proc.stdout + proc.stderr
    if proc.returncode != 0 and ("连不上网关" in out or "GatewayUnreachable" in out):
        pytest.skip(f"网关不在（不是本卡的失败）：{out[-300:]}")
    assert proc.returncode == 0, f"smoke.sh 没跑通：\n{out[-3000:]}"
    assert "SMOKE-OK" in out, out[-2000:]

    art = json.loads((gb / "scratch/example_minimal/task/artifact.json").read_text("utf-8"))
    assert art["stage"] == "S1"
    assert art["declarations"]["data_version"] == "unresolved", (
        "题面没给的口径必须是显式 unresolved —— 这正是示例要示范的那件事")
    assert art["payload"]["fetches"], "一次请求都没记进 fetches"
    for f in art["payload"]["fetches"]:
        assert f["status"] in ("ok", "empty", "denied", "rate_limited")
        assert f["fetched_at"], "fetched_at 必须取自响应头 x-genebench-ts"


# ══════════════════════════════════════════ 阶段二红队修复（2.rt）：手册的三条 major
#
# 判据都做成**双向**的：一端断言代码/schema 的事实，另一端断言手册说的是同一件事。
# 只查手册文本的话，等实现改了手册就静默变错 —— 那正是这三条 finding 的成因。

def test_the_readme_addresses_declarations_by_its_real_json_path():
    """finding 3：`/task/{stage}.json` 顶层**没有** `declarations` 这一键。

    照旧文档写 `json.load(...)["declarations"]["required"]` 当场 `KeyError`，
    而这是「少写一个声明键」（头号畸形来源）的唯一指引。
    """
    spec = json.loads((REPO / "ops" / "specs" / "artifact_schema" / "v1.0" / "S2.json")
                      .read_text(encoding="utf-8"))
    assert "declarations" not in spec, (
        "S2.json 顶层现在有 declarations 了 —— 手册里的读法要跟着改回去")
    assert "declarations" in spec["properties"], "properties.declarations 不在了"
    assert "required" in spec["properties"]["declarations"]

    assert "properties.declarations.required" in TEXT or \
           '["properties"]["declarations"]["required"]' in TEXT, \
        "手册没有给出真实的 JSON 路径"
    assert "`declarations.required`" not in TEXT, (
        "手册里还有裸的 `declarations.required` —— 那个路径在文件里不存在")


def test_the_readme_names_the_contracted_output_file_as_a_legal_new_file():
    """finding 6 与它的连带：`artifact.json` **不是**唯一该新建的文件。

    S2/S3/S7 的题面固定槽点名一个产出文件（`/task/panel.csv` 等），采集侧的允许集里
    有它；手册原来写「唯一该新建的文件」+「中间产物不要落进 /task」，照做就交不出
    `panel_ref.sha256` 指的那个文件。
    """
    sys.path.insert(0, str(REPO))
    from genetask.file_contract import FILE_SPECS
    from runner.c42 import harvest

    for stage, specs in FILE_SPECS.items():
        for sp in specs:
            assert sp["path"] in TEXT, (
                f"手册没写 {stage} 的产出文件 {sp['path']} —— 被测方不知道要交它")
            rel = "work/" + sp["path"].rsplit("/", 1)[-1]
            assert rel in harvest.PRODUCED_BY_STAGE.get(stage, ()), (
                f"{rel} 不在采集侧允许集里 —— 手册与 harvest 漂开了")
    assert "唯一该新建的文件" not in TEXT, (
        "「唯一该新建的文件」这句话对 S2/S3/S7 是错的")


def test_the_readme_warns_that_compat_fields_do_not_reach_the_gateway():
    """finding 1：compat 层的 `fields` 只裁剪返回值，读取集仍是完整列集。

    这是唯一一条「按手册做、本地全绿、评分侧判 undeclared_reads」的路径。
    代码侧的事实：三个 compat 层向网关请求的是写死的完整列集。
    """
    compat = REPO / "integrations" / "genebench_client" / "src" / "genebench_client" / "compat"
    full = '"open", "high", "low", "close", "volume", "amount"'
    hard = [p.name for p in sorted(compat.glob("*.py"))
            if full in p.read_text(encoding="utf-8")]
    assert hard, ("三个 compat 层都不再按完整列集请求了 —— 手册里的 finding 1 警告要跟着改")

    seg = TEXT[TEXT.find("### ③ 把系统的数据层换成垫片"):TEXT.find("### ④ 配置指向")]
    assert "只裁剪返回值" in seg, "§1③ 没有警告 compat 的 fields 不落到网关请求上"
    assert "declared_reads" in seg and "bars(" in seg, "§1③ 没给出替代写法"
