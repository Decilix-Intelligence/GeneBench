# -*- coding: utf-8 -*-
"""`harnesses/` 的接入契约（阶段三 3.1，2026-09-06）。

**这份测试守的是 `harnesses/README.md` 里那些话的真假**，不是代码的内部一致性。
外部运行者照着 README 加一个 harness，能不能跑通取决于四件事：目录里的文件齐不齐、
`launch.json` 过不过 schema、命令里有没有裸 `$`、`Dockerfile` 是不是从统一基座起。
这四件都会在**真跑到一半**才发作（两臂 3 秒退出、零次调用、日志上看起来"跑过了"），
所以它们必须有一道 import 期就响的门。

最后一条 `test_readme_commands_point_at_real_files` 守的是**文档本身**：
README 里的命令一旦指向不存在的文件，读者的第一反应是"我环境不对"，
而不是"文档漂了" —— 那是最贵的一种错。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
HARNESSES = REPO / "harnesses"
README = HARNESSES / "README.md"
BUILD_SH = HARNESSES / "build.sh"

#: 一个 harness 目录里**必须**有的四件文件（`harnesses/README.md` §1）。
REQUIRED_FILES = ("Dockerfile", "launch.json", "config.yaml", "README.md")

#: 统一基座（N-62）。三个 harness 各用各的官方基座时，pandas/pyarrow 版本差异会混进
#: 主表的「harness 差异」那一列，而 S2/S3/S7 的产出恰恰是数值。
BASE_IMAGE = "gb-base:bookworm-r1"


def harness_dirs() -> list[Path]:
    if not HARNESSES.is_dir():
        return []
    return sorted(p for p in HARNESSES.iterdir() if p.is_dir() and not p.name.startswith("."))


def _ids(dirs):
    return [d.name for d in dirs]


DIRS = harness_dirs()


def test_there_is_at_least_one_harness():
    """空目录会让下面每一条参数化测试**静默通过** —— 0 个用例也是绿的。"""
    assert DIRS, f"{HARNESSES} 下一个 harness 目录都没有"


@pytest.mark.parametrize("d", DIRS, ids=_ids(DIRS))
def test_four_files(d: Path):
    """四件文件缺一件都不算接入完成。

    少 `README.md` 是最常见的那件 —— 它不影响跑，只影响**下一个人**能不能接上。
    """
    missing = [f for f in REQUIRED_FILES if not (d / f).is_file()]
    assert not missing, f"{d} 缺 {missing}（见 harnesses/README.md §1）"


@pytest.mark.parametrize("d", DIRS, ids=_ids(DIRS))
def test_launch_json_passes_schema(d: Path):
    """走 `harness_commands` 自己的校验器，不在这里重写一遍判据。

    重写一遍的后果是两份判据各自漂：真正拦人的是 import 期那一份，
    而这里绿了会让人以为已经核过。
    """
    from runner.c42 import harness_commands as HC

    spec = json.loads((d / "launch.json").read_text(encoding="utf-8"))
    HC._validate_launch(spec, str(d / "launch.json"))          # 抛 RegistryError 即红
    assert set(spec) == set(HC.LAUNCH_KEYS)


@pytest.mark.parametrize("d", DIRS, ids=_ids(DIRS))
def test_command_has_no_bare_dollar(d: Path):
    """N-101：compose 在**解析文件时**就把 `$VAR` 插值掉。

    实测 `mkdir -p "$CODEX_HOME"` 变成 `mkdir: cannot create directory ''`，
    两臂 3 秒退出、零次模型调用，而日志上看起来"跑过了"。
    判据：命令里每一段连续的 `$` 长度必须是**偶数**（`$$` 才活得到容器里的 sh）。
    """
    spec = json.loads((d / "launch.json").read_text(encoding="utf-8"))
    blob = "\n".join(spec["command"])
    odd = [m.group(0) for m in re.finditer(r"\$+", blob) if len(m.group(0)) % 2]
    assert not odd, (
        f"{d}/launch.json 的 command 里有裸 $（{len(odd)} 处）—— "
        f"compose 解析期会把它吃掉，一律写 $$（N-101）")


@pytest.mark.parametrize("d", DIRS, ids=_ids(DIRS))
def test_dockerfile_from_unified_base(d: Path):
    """第一条**有效**指令必须是 `FROM gb-base:bookworm-r1`，且全文只有一条 `FROM`。

    为什么不是"字面第一行"：W-0 要求 Dockerfile 顶部写来历注释（镜像名 + digest + 基座），
    那几行注释正是"抄回来的这份和构建出镜像的那份是同一份"的唯一证据。
    多条 `FROM` 会被注入器 P4c 当场拦掉，在这里先说一遍。
    """
    lines = (d / "Dockerfile").read_text(encoding="utf-8").splitlines()
    eff = [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]
    assert eff, f"{d}/Dockerfile 里没有任何有效指令"
    assert eff[0] == f"FROM {BASE_IMAGE}", (
        f"{d}/Dockerfile 的第一条指令是 {eff[0]!r}，必须是 'FROM {BASE_IMAGE}'（N-62 统一基座）")
    n_from = sum(1 for ln in eff if ln.split(" ", 1)[0].upper() == "FROM")
    assert n_from == 1, f"{d}/Dockerfile 有 {n_from} 条 FROM —— 注入器 P4c 只允许 1 条"


@pytest.mark.parametrize("d", DIRS, ids=_ids(DIRS))
def test_config_yaml_is_readable_by_registry(d: Path):
    """`config.yaml` 能被注册表读、且这一条确实出现在读出来的结果里。

    「registry 能读整棵树」与「**我这一条**被读到了」是两件事：
    前者在别人的目录都合法时也绿。
    """
    from runner import registry as REG

    enabled, pending = REG.load_data_configs(REPO)
    raw = (d / "config.yaml").read_text(encoding="utf-8")
    import yaml
    want = yaml.safe_load(raw)
    assert set(want) == set(REG.CONFIG_KEYS), (
        f"{d}/config.yaml 键集必须恰好是 {list(REG.CONFIG_KEYS)}")
    seen = {c.config_id for c in enabled} | {c.config_id for c in pending}
    assert want["config_id"] in seen, f"{d}/config.yaml 的 config_id 没被 registry 读到"
    # 同一个目录里的两份声明必须说同一个 harness —— 不一致时 `command_for()` 查不到，
    # 表现是"配置能找到、命令是 None、run 记 BLOCKED"，而原因在另一个文件里。
    spec = json.loads((d / "launch.json").read_text(encoding="utf-8"))
    assert want["harness"] == spec["harness"], (
        f"{d}: config.yaml 的 harness={want['harness']!r} ≠ launch.json 的 {spec['harness']!r}")


def test_command_for_finds_every_harness():
    """每个目录的 harness 名都能被 `command_for()` 查到，且回的是自己那条命令。"""
    from runner.c42 import harness_commands as HC

    specs = HC.discover_launch_specs(REPO)
    for d in DIRS:
        spec = json.loads((d / "launch.json").read_text(encoding="utf-8"))
        h = spec["harness"]
        assert h in specs, f"{d}: discover_launch_specs 里没有 {h!r}"
        assert json.loads(HC.command_for(h, repo_root=REPO)) == spec["command"]


def test_build_sh_exists_and_guards_the_base():
    """`harnesses/build.sh` 在，且确实核基座 —— README §3.2 说它做这件事。"""
    assert BUILD_SH.is_file(), "缺 harnesses/build.sh"
    txt = BUILD_SH.read_text(encoding="utf-8")
    assert BASE_IMAGE in txt, "build.sh 里没提统一基座 —— 那它就没在核 FROM"
    assert "docker build" in txt
    assert "launch.json" in txt, "build.sh 的 tag 必须从 launch.json 的 image 取"


# ---------------------------------------------------------------------------
# README 里的命令必须指向真文件
# ---------------------------------------------------------------------------
#: 只看**命令**：围栏代码块里的行，以及带参数的行内代码（`ops/x.sh --flag`）。
#: 不带空格的行内代码（`ops/score_runs.py`）是**引用**不是命令，不在此列。
_SHELLISH = {"", "sh", "shell", "bash", "console", "sh-session"}


def _fenced_shell_lines(md: str) -> list[str]:
    out, inside, lang = [], False, ""
    for ln in md.splitlines():
        m = re.match(r"^\s*```(\S*)\s*$", ln)
        if m:
            if inside:
                inside, lang = False, ""
            else:
                inside, lang = True, m.group(1).lower()
            continue
        if inside and lang in _SHELLISH:
            out.append(ln)
    return out


def _inline_commands(md: str) -> list[str]:
    return [s for s in re.findall(r"`([^`\n]+)`", md) if " " in s]


def _path_token(line: str) -> str | None:
    """一条命令行里那个**该存在的仓库相对路径**；不是命令则 None。"""
    toks = line.strip().split()
    if not toks:
        return None
    if toks[0] == "$PY":
        for t in toks[1:]:
            if not t.startswith("-"):
                return t
        return None
    if toks[0].startswith(("ops/", "harnesses/")):
        return toks[0]
    return None


def test_readme_commands_point_at_real_files():
    """README 里每条以 `$PY` / `ops/` / `harnesses/` 开头的命令，所指的文件都在。

    带 `<占位符>` 或 shell 变量的跳过 —— 那些是模板，不是可执行的命令。
    """
    assert README.is_file(), "缺 harnesses/README.md"
    md = README.read_text(encoding="utf-8")
    cands = _fenced_shell_lines(md) + _inline_commands(md)
    checked, missing = [], []
    for line in cands:
        p = _path_token(line)
        if p is None:
            continue
        p = p.strip("\"'")
        if any(ch in p for ch in "<>$*"):        # 模板占位符 / 变量：不判
            continue
        checked.append(p)
        if not (REPO / p).exists():
            missing.append((p, line.strip()))
    assert checked, "README 里一条可判的命令都没有 —— 提取器多半坏了"
    assert not missing, "README 里的命令指向不存在的文件：\n" + "\n".join(
        f"  {p}   ← {ln}" for p, ln in missing)


def test_readme_covers_the_contract():
    """README 必须真的把契约写出来，不是只有目录结构（W-0 骨架那版就是那样）。"""
    md = README.read_text(encoding="utf-8")
    for needle in ("/task/INSTRUCTION.md", "/task/artifact.json", "$$",
                   BASE_IMAGE, "OPENAI_BASE_URL", "LLM_BASE_URL",
                   "budget_exceeded", "llm_log.jsonl", "MODEL_API_ALLOW",
                   "--with-launch-data", "gateway_lock.py",
                   "ops/export_bundle.py", "ops/push_bundle_to_f02.sh",
                   "ops/score_runs.py"):
        assert needle in md, f"harnesses/README.md 里没写 {needle!r}"
    # 骨架那句"在那之前不要把这里当接入文档读"必须已经消失 —— 否则正文没整合进来。
    assert "在那之前不要把这里当接入文档读" not in md
def test_readme_scoring_remote_has_the_extra_runs_layer():
    """§4④ 的 `--remote` 必须比 ③ 的 `--run-root` **多一层 `runs`**（卡 3.3）。

    这一条不是文风检查，它守的是一种**不报错的错**：run 目录由
    `runner/inject.py` 建在 `run_root / "runs" / <run_id>` 下，
    照旧手册把 `--remote` 写成 `--run-root` 同一个路径，`score_runs.py`
    会退 0 并打印 `runs: 0；问题: 0` —— 读起来像「跑完了但没做出来」，
    真相是**结算根本没找到 run**。3.2-gemini-cli 第一次就撞了。

    判据取自两处、必须一致：手册里的字面命令，和 inject.py 里真正建目录那一行。
    """
    md = README.read_text(encoding="utf-8")
    inj = (REPO / "runner" / "inject.py").read_text(encoding="utf-8")

    # ① 落点确实多一层 —— 手册的说法要有代码撑着，不是背下来的口诀。
    assert 'run_root / "runs" / rid' in inj, (
        "runner/inject.py 不再把 run 建在 run_root/runs/<rid> 下 —— "
        "那么手册 §4④ 的『多一层 runs』就该跟着改，不要只把这条断言删掉")

    # ② 手册里每一条 score_runs.py 的 --remote 都要以 /runs/runs 结尾。
    remotes = re.findall(r"score_runs\.py[^\n]*?--remote\s+(\S+)", md)
    assert remotes, "harnesses/README.md 里找不到带 --remote 的结算命令"
    bad = [r for r in remotes if not r.rstrip("/").endswith("/runs/runs")]
    assert not bad, (
        "harnesses/README.md 的 --remote 少了一层 runs（照抄会得到「runs: 0」而不报错）："
        + "、".join(bad))

    # ③ 而 --run-root 只有一层 —— 两者差的就是那一层。
    roots = re.findall(r"--run-root\s+(\S+)", md)
    assert roots, "harnesses/README.md 里找不到 --run-root"
    assert all(not r.rstrip("/").endswith("/runs/runs") for r in roots), (
        "--run-root 被写成了两层 runs —— 多出来的那一层是 inject.py 自己建的，"
        "写进 --run-root 会变成三层")


# ══════════════════════════════════════════ 阶段三红队修复（3.rt）：手册的九条 major
#
# 这九条 finding 有一个共同的形状：**照文档做、结果是错的，而且没有任何东西会红**。
# 所以判据一律做成**双向**的 —— 一端断言代码/产物侧的事实，另一端断言手册说的是同一件事。
# 只查手册文本的话，实现一改手册就静默变错，那正是这批 finding 的成因。

import sys as _sys

if str(REPO) not in _sys.path:
    _sys.path.insert(0, str(REPO))

RUNNER_CORE = (REPO / "runner" / "c41" / "runner_core.py")
RUN_LOOP = (REPO / "runner" / "run_loop.py")


def _md() -> str:
    return README.read_text(encoding="utf-8")


def _seg(md: str, start: str, end: str) -> str:
    i, j = md.find(start), md.find(end)
    assert i >= 0 and j > i, f"手册里找不到 {start!r}..{end!r} 这一段"
    return md[i:j]


def test_readme_env_table_uses_the_full_genebench_prefixed_names():
    """finding 1：容器里注的是 `GENEBENCH_RUN_ID` / `_CONFIG_ID` / `_ARM`，没有短名。

    按短名（`$$RUN_ID`）取到的是**空串**，而 `env_required` 从不与容器 env 比对 ——
    名字写错是完全静默的。所以表里必须是四个全称。
    """
    src = RUNNER_CORE.read_text(encoding="utf-8")
    from runner.c42.identity import ENV_BY_KEY
    assert ENV_BY_KEY == {"task_id": "GENEBENCH_TASK_ID",
                          "config_id": "GENEBENCH_CONFIG_ID",
                          "arm": "GENEBENCH_ARM"}, ENV_BY_KEY
    for name in ("GENEBENCH_TASK_ID", "GENEBENCH_RUN_ID",
                 "GENEBENCH_CONFIG_ID", "GENEBENCH_ARM"):
        assert f"{name}:" in src, f"COMPOSE_TMPL 里不再注 {name} —— 手册 §2.1 要跟着改"

    md = _md()
    for name in ("GENEBENCH_RUN_ID", "GENEBENCH_CONFIG_ID", "GENEBENCH_ARM"):
        assert name in md, f"手册 §2.1 的环境表里没有 {name}（写短名拿到的是空串）"
    assert "/ `RUN_ID` / `CONFIG_ID` / `ARM`" not in md, (
        "手册里还留着短名那一行 —— 那是容器里不存在的四个名字")


def test_readme_says_env_required_is_registered_but_not_checked():
    """finding 1 的另一半：`env_required` 只被做类型校验，从不与容器 env 比对。

    代码侧的事实：`harness_commands.py` 根本不认识 compose 那张表
    （不 import `runner_core`、不提 `COMPOSE_TMPL`），所以它没有能力比对。
    """
    hc = (REPO / "runner" / "c42" / "harness_commands.py").read_text(encoding="utf-8")
    assert "env_required" in hc
    assert "COMPOSE_TMPL" not in hc and "runner_core" not in hc, (
        "harness_commands.py 现在看得到容器 env 了 —— 那手册那句「只登记、不校验」要跟着改")
    assert "校验器不检查这些变量是否真的存在" in _md(), (
        "手册 §1.2 没写明 env_required 不被校验 —— 读者会以为写错了会有人告诉他")



def _fenced(seg: str) -> str:
    """一段 markdown 里**围栏代码块**的内容 —— 断言「可复制的命令里不许有 X」只能看这里。

    正文里解释「为什么不要给 `--max-tokens`」时一定会出现这个字符串，按整段断言会把
    解释本身判成违规（卡 W.rt 踩过一次）。
    """
    parts = seg.split("```")
    return "\n".join(parts[i] for i in range(1, len(parts), 2))

def test_readme_run_command_passes_an_explicit_max_tokens():
    """finding 2 的**反向**（N-388，2026-09-10 用户裁定后重写）：§4③ 那条可复制的真跑命令里
    **一个预算参数都不许给**。

    默认档现在是 `100 次 / 6,000,000 tokens`，`BUDGET_TIERS` 再按阶段往上抬（S4 9M / S7 18M）。
    显式给的值**逐键赢过档位**，所以旧版本那条「一律显式给 3000000」今天是**把预算压低**：
    3M < 默认的 6M，而且会把 S4 的 9M 与 S7 的 18M 一起打回去。撞闸的现场表现不是报错，
    是「agent 做到一半自己放弃了」。原断言（要求显式 3000000）自 W1 抬档之后一直红。
    """
    from runner import registry as REG
    assert REG.RUN_BUDGET["max_tokens"] == 6_000_000, (
        f"默认档变了（{REG.RUN_BUDGET}）—— 手册 §2.4 与 §4③ 的说法要一起复核")

    md = _md()
    cmd = _fenced(_seg(md, "### ③ 真跑", "### ④ 结算"))
    assert cmd.strip(), "§4③ 里一个命令块都没有 —— 断言会恒绿"
    assert "--max-tokens" not in cmd, (
        "§4③ 的真跑命令里出现了 --max-tokens —— 显式值逐键压过 stage 档位（N-388）")
    assert "--max-calls" not in cmd, (
        "§4③ 的真跑命令里出现了 --max-calls —— 照抄到 S4/S7 的题上等于把档位关掉")
    assert "6,000,000" in md or "6000000" in md, "§2.4 要写出现在的默认档 6,000,000"


def test_readme_never_shows_push_exec_without_with_launch_data():
    """finding 3：`--dry-run` 也必须带 `--with-launch-data`。

    不带的话清单里没有 `harnesses/` 与 `integrations/` —— 恰恰是读者此刻唯一关心的两棵树，
    于是「清单里没有我的东西」被读成「同步坏了」。
    """
    md = _md()
    lines = [l for l in md.splitlines() if "push_exec_to_f02.sh" in l and l.strip().startswith("ops/")]
    assert lines, "手册里找不到 push_exec_to_f02.sh 的命令行"
    bad = [l.strip() for l in lines if "--with-launch-data" not in l]
    assert not bad, ("手册里这几条 push_exec 命令没带 --with-launch-data："
                     + "；".join(bad))
    assert "`harnesses/`、`integrations/` 三棵树" in md or            "`runner/`、`harnesses/`、`integrations/`" in md, (
        "⚠ 那条警告还只提 runner/ —— 实测 --with-launch-data 也会把 harnesses/ 与 "
        "integrations/ 下别人未提交的改动推走")


def test_readme_does_not_teach_readers_to_pre_accept_a_red():
    """finding 4：`len(REG.CONFIGS) == 3` 那条断言早就改掉了。

    手册教读者「翻开关会红，那不是回归」= 教他把一条真红当绿 —— 这是
    「恒红当绿」的入口：将来 `test_c41.py` 真红一条，读者会照手册忽略它。
    """
    t41 = (REPO / "ops" / "test_c41.py").read_text(encoding="utf-8")
    assert "assert len(REG.CONFIGS) == 3" not in t41, (
        "那条断言又回来了 —— 它会被正常施工跑红（每接一个 harness 一次）")
    assert "test_v10_is_one_model_many_harnesses" in t41

    md = _md()
    assert "那不是回归" not in md, "手册还在教读者预先接受一条红"
    assert "现在不会红" in md, "改完要把「该断言已改掉、现在不会红」说清楚，否则读者不知道该信谁"


def test_readme_documents_no_proxy_as_load_bearing():
    """finding 5：`NO_PROXY` 是承重件 —— harness 覆盖掉它，取数就 405（D-10）。"""
    src = RUNNER_CORE.read_text(encoding="utf-8")
    assert 'NO_PROXY: "gateway,localhost,127.0.0.1"' in src, "COMPOSE_TMPL 不再注 NO_PROXY 了"
    assert "405" in src and "L-9" in src, "L-9 判据没了 —— 手册 §2.1 那一行要跟着复核"

    md = _md()
    seg = _seg(md, "### 2.1 容器里能看见什么", "### 2.2")
    assert "NO_PROXY" in seg, "§2.1 的环境表里没有 NO_PROXY"
    assert "不许在命令里覆盖" in seg
    fail = md[md.find("## 5. 常见失败"):]
    assert "405" in fail, "§5 里没有「405 / 像网关坏了」那一行"


def test_readme_points_the_forensics_at_run_json_tails():
    """finding 6：真跑收尾已 `down -v`，容器与 compose 日志都不存在了。

    留存的容器输出只有 `<run_dir>/run.json` 的 `stdout_tail` / `stderr_tail`（各 2000 字符）。
    手册原来把读者指向 `docker compose logs gateway` —— 那是一个空的证据面。
    """
    rl = RUN_LOOP.read_text(encoding="utf-8")
    assert '"stdout_tail": res.stdout_tail' in rl and '"stderr_tail": res.stderr_tail' in rl, (
        "run.json 不再记 stdout_tail/stderr_tail —— 手册 §4③ 的取证面要跟着改")
    assert "[-2000:]" in rl, "尾部长度变了，手册写的 2000 字符要跟着改"
    assert '"down", "-v"' in rl, "不再 down -v 的话，容器日志就还在，手册的说法要复核"

    md = _md()
    for token in ("run.json", "stdout_tail", "stderr_tail", "inject.json",
                  "log/egress.jsonl", "log/llm_log.jsonl"):
        assert token in md, f"手册没写 run dir 取证面的 {token}"
    assert "日志在 `docker compose logs gateway`" not in md, (
        "§5 还在把读者指向 docker compose logs —— 真跑结束时容器已经没了")


def test_readme_covers_identity_mismatch():
    """finding 7：`identity_mismatch` 结算出 SR=0.0 而 `summary` 说「问题: 0」。

    最自然的误读是「agent 答错了」，真实含义是产物信封的三键与真值对不上 ——
    harness 作者最容易撞的一档（三键写死、`--config-id` 传错）。
    """
    from runner.c42 import failure_modes as FM
    assert FM.sr_bucket("identity_mismatch") == "unscorable_agent"

    md = _md()
    assert "identity_mismatch" in md, "手册全文没有 identity_mismatch 这个词"
    assert "unscorable_agent" in md, "要说清它归 unscorable_agent（不是答错）"
    seg = _seg(md, "命令必须做到四件事", "#### 铁律一")
    assert "不许代写" in seg, "§1.2 没写明信封三键由 agent 自己写、harness 不许代写"


def test_readme_warns_that_export_rebuilds_the_answer_plane():
    """finding 8：出集不只是产 bundle，它还**重建**答案面那棵树。

    对一道别的批次已经出过的题重跑 ①，就在共享数据面上重写了它 ——
    手册原来一个字没提，而 §6 还专门强调答案面的重要性。
    """
    eb = (REPO / "ops" / "export_bundle.py").read_text(encoding="utf-8")
    assert "P.write_task(b, ANSWER_ROOT" in eb, (
        "export_one 不再写答案面了 —— 手册 §4① 那句警告要跟着复核")
    assert 'ANSWER_ROOT: Path = cfg.GENEBENCH_ROOT / "reference"' in eb

    md = _md()
    seg = _seg(md, "### ① 出集", "### ② 推送")
    assert "会写答案面" in seg, "§4① 没说出集会重建答案面"
    assert "别在别人结算期间重出集" in seg


def test_readme_says_where_task_ids_come_from():
    """finding 9：题号从哪来。手册原来一个字没说，读者只能跑文档里举例的那一道。"""
    params = REPO / "genetask" / "params" / "v1.0-smoke40.yaml"
    assert params.is_file(), "参数表挪走了 —— 手册 §4 的题号出处要跟着改"
    ids = [l.split(":", 1)[1].strip() for l in params.read_text(encoding="utf-8").splitlines()
           if l.strip().startswith("- task_id:")]
    assert len(ids) >= 10, f"参数表里只剩 {len(ids)} 个题号？"

    md = _md()
    assert "genetask/params/v1.0-smoke40.yaml" in md, "手册没说可选题号在哪张表里"
    sample = re.findall(r"`(s\d-[a-z]{3}-\d{2})`", md)
    unknown = [s for s in set(sample) if s not in ids]
    assert not unknown, f"手册举的题号不在参数表里：{sorted(unknown)}"
