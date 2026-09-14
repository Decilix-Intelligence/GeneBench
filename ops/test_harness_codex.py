# -*- coding: utf-8 -*-
"""`harnesses/codex` 的 harness 专属判据（阶段三 3.2，2026-09-06）。

`ops/test_harness_contract.py` 守的是**每个** harness 都要满足的通用契约
（四件文件、launch schema、无裸 `$`、统一基座）。这一份守的是 **Codex 独有**、
且都**踩过一次**的那些：

* `CODEX_HOME` 没指到 `/task` 下 → 容器里 `PermissionError`（HOME 不可写）；
* 命令里写死了模型主机名 → **绕过边车**，表现是"跑通了"，只是那一批的出向
  不再受白名单与预算闸管 —— 这是最贵的一种"绿"；
* `ops/score_runs.py` 的 `--exclude=.codex/` 被顺手删掉 → 断链符号链接被搬回 f01，
  网关红线 5 守门 `stat` 不到它们 → **拒绝启动网关**（2026-09-05 实测 10 分钟数据面停摆）；
* 三份文件（Dockerfile 的来历注释 / launch.json 的 image / README 的表）里
  digest 与版本号各写各的 → 「复核过来历」这句话失去意义。

这些都是**跨文件**的一致性，任何单个文件自己看都是对的。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
HERE = REPO / "harnesses" / "codex"
LAUNCH = HERE / "launch.json"
CONFIG = HERE / "config.yaml"
DOCKERFILE = HERE / "Dockerfile"
README = HERE / "README.md"

#: 完整的 64 位 digest。README 正文里那些 `sha256:961e3878b28f…` 的省略写法不参与比对。
_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")


@pytest.fixture(scope="module")
def spec() -> dict:
    return json.loads(LAUNCH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def command(spec) -> str:
    return "\n".join(spec["command"])


@pytest.fixture(scope="module")
def dockerfile() -> str:
    return DOCKERFILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def readme() -> str:
    return README.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# ① 容器里跑得起来
# ---------------------------------------------------------------------------
def test_codex_home_is_under_task(command):
    """`CODEX_HOME` 必须导出、指到 `/task` 下、且**先 mkdir 再用**。

    任务容器以 uid 1000 跑、HOME 不可写；Codex 起来第一件事就是写配置目录。
    三条缺一条都是 `PermissionError`，而错误信息里不会提 HOME。
    """
    m = re.search(r"export\s+CODEX_HOME=(\S+)", command)
    assert m, "命令里没有 export CODEX_HOME —— 容器 HOME 不可写，Codex 会 PermissionError"
    home = m.group(1)
    assert home.startswith("/task/"), f"CODEX_HOME={home!r} 必须在 /task 下（HOME 与 / 都不可写）"
    assert "mkdir -p" in command, "CODEX_HOME 要先 mkdir -p —— Codex 不会替你建"
    # 先 mkdir 后用：顺序反了在 shell 里是另一个错，且只在真跑时发作。
    assert command.index("export CODEX_HOME") < command.index("mkdir -p")


def test_instruction_comes_from_the_bundle(command):
    """题面只能来自 `/task/INSTRUCTION.md`，且是**位置参数**不是 stdin。"""
    assert "/task/INSTRUCTION.md" in command, "题面必须从 /task/INSTRUCTION.md 读"
    assert "cat /task/INSTRUCTION.md" in command


def test_required_codex_exec_flags(command):
    """三个必需开关，少哪个都不是"跑得差一点"，而是压根跑不到模型。"""
    for flag, why in (
        ("--skip-git-repo-check", "/task 不是 git 仓库，不加直接退出"),
        ("--ephemeral", "/task 不是 git 仓库，不加直接退出"),
        ("--dangerously-bypass-approvals-and-sandbox",
         "非交互的 codex exec 会卡住等审批输入（容器本身已是沙箱）"),
    ):
        assert flag in command, f"命令里缺 {flag} —— {why}"


# ---------------------------------------------------------------------------
# ② 不绕过边车
# ---------------------------------------------------------------------------
def test_base_url_only_from_env(spec, command):
    """base URL 只能从 `env_required` 列的变量取，**不许写死主机名**。

    写死的表现是"跑通了" —— 只是那一批的出向不再经过边车，
    于是白名单、预算闸、`llm_log` 三样同时失效，而报告上看不出来。
    """
    assert "OPENAI_BASE_URL" in spec["env_required"], "env_required 必须声明 OPENAI_BASE_URL"
    assert "$$OPENAI_BASE_URL" in command, "base_url 必须从 $$OPENAI_BASE_URL 取"

    # 命令里不许出现任何模型厂商的主机名 / 裸 URL。
    bad = re.findall(r"https?://[^\s\"']+", command)
    assert not bad, (
        f"命令里写死了 URL {bad} —— base URL 只能从 env 取，写死就绕过边车")
    for host in ("api.deepseek.com", "api.openai.com", "api.anthropic.com"):
        assert host not in command, f"命令里写死了主机名 {host} —— 那会绕过边车"


def test_api_key_is_taken_from_env_not_inlined(spec, command):
    """key 只能经 `env_key` 从环境取；容器里那把是占位 key，真 key 由边车注入。"""
    assert "OPENAI_API_KEY" in spec["env_required"]
    assert 'env_key="OPENAI_API_KEY"' in command, "必须让 Codex 从环境取 key"
    # 任何形似真 key 的常量都不许出现在命令里（占位 key 也不该硬编码在这儿）。
    assert not re.search(r"sk-[A-Za-z0-9]{16,}", command), "命令里出现了形似 API key 的常量"


# ---------------------------------------------------------------------------
# ③ 镜像来历：三份文件说同一件事
# ---------------------------------------------------------------------------
def test_dockerfile_pins_an_exact_codex_version(dockerfile):
    """npm 包必须钉到确切版本 —— 浮动版本会让"同一个镜像"这句话失去意义。"""
    m = re.search(r"@openai/codex@(\d+\.\d+\.\d+)", dockerfile)
    assert m, "Dockerfile 里没有钉死的 @openai/codex@<x.y.z>"
    assert "@latest" not in dockerfile, "不许装 @latest"


def test_dockerfile_installs_no_market_data_libs(dockerfile):
    """harness 镜像里**不许装行情库**。

    行情库只该出现在题面镜像里。装进 harness 会让 agent 有一条绕过 `/task` 数据的路，
    而那条路不受出向白名单管。
    """
    for lib in ("tushare", "akshare", "baostock", "yfinance", "rqdatac", "jqdatasdk", "qlib"):
        assert lib not in dockerfile.lower(), f"harness 镜像里不许装行情库：{lib}"


def test_digest_agrees_across_dockerfile_and_readme(dockerfile, readme):
    """Dockerfile 顶部的来历注释、README 的表、README §7 的 `DIG=` 必须是同一个 digest。

    这三处各写各的时候，"我复核过镜像来历"这句话就没有对象了。
    """
    in_df = set(_DIGEST_RE.findall(dockerfile))
    in_md = set(_DIGEST_RE.findall(readme))
    assert len(in_df) == 1, f"Dockerfile 里应恰好有一个完整 digest，实际 {sorted(in_df)}"
    assert in_md, "README 里没有写完整的 digest"
    assert in_df == in_md, (
        f"digest 对不上：Dockerfile {sorted(in_df)} vs README {sorted(in_md)}")


def test_image_tag_agrees_across_dockerfile_and_launch(spec, dockerfile):
    """`launch.json` 的 `image` 必须出现在 Dockerfile 的来历注释里。

    `build.sh` 的 tag 是从 `launch.json` 的 `image` 取的；来历注释写着另一个名字时，
    表现是"构建成功了，跑的还是旧镜像"。
    """
    assert spec["image"] in dockerfile, (
        f"Dockerfile 的来历注释里没提 {spec['image']!r}（launch.json 的 image）")


def test_codex_version_agrees_between_dockerfile_and_readme(dockerfile, readme):
    ver = re.search(r"@openai/codex@(\d+\.\d+\.\d+)", dockerfile).group(1)
    assert f"@openai/codex@{ver}" in readme, (
        f"README 的版本与 Dockerfile 装的 {ver} 对不上")


# ---------------------------------------------------------------------------
# ④ 配置：这一份是模板，不是第四条切片
# ---------------------------------------------------------------------------
def test_config_stays_a_template_while_it_collides_with_a_builtin():
    """`config.yaml` 的 `config_id` 与内置重名时，`enabled` 必须是 `false`。

    重名 + `enabled: true` 会让 `merge_configs` 当场红（设计如此：同一条配置不许有两个来源）。
    这条判据是**有条件的** —— 将来若换成一个不与内置重名的 `config_id`，
    它自动让开，不会变成一条挡路的恒红。
    """
    from runner import registry as REG

    want = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    builtin_ids = {c.config_id for c in REG.BUILTIN_CONFIGS}
    if want["config_id"] in builtin_ids:
        assert want["enabled"] is False, (
            f"{want['config_id']!r} 与内置重名，enabled 必须是 false —— "
            f"翻成 true 会让 merge_configs 在 import 期直接红")


def test_the_builtin_codex_config_points_at_this_harness():
    """内置的 `cfg-codex-deepseek` 与本目录说的是同一个 harness 名。"""
    from runner import registry as REG

    c = REG.by_id("cfg-codex-deepseek")
    spec = json.loads(LAUNCH.read_text(encoding="utf-8"))
    assert c.harness == spec["harness"] == "Codex CLI"


# ---------------------------------------------------------------------------
# ⑤ 跨文件的地雷：score_runs 的 .codex 排除项
# ---------------------------------------------------------------------------
def test_score_runs_still_excludes_the_codex_scratch_dir():
    """`ops/score_runs.py` 必须继续排除 `.codex/`。

    Codex 在 `.codex/tmp/arg0/` 下留**断链的符号链接**；照搬回 f01 之后
    网关的红线 5 守门 `stat` 不到它们 → 拒绝启动网关。
    2026-09-05 实测：10 分钟数据面停摆。产物与日志都不在 `.codex/` 里，排除掉没有损失。

    这一条放在 codex 的测试里而不是 `score_runs` 的测试里，是因为**原因在 codex 这边**：
    删掉它的人多半正在读 `score_runs.py`，那里看不出这个排除项是谁要的。
    """
    txt = (REPO / "ops" / "score_runs.py").read_text(encoding="utf-8")
    assert "--exclude=.codex/" in txt, (
        "ops/score_runs.py 不再排除 .codex/ —— 断链符号链接会让网关拒绝启动"
        "（见 harnesses/codex/README.md §3）")


# ---------------------------------------------------------------------------
# ⑥ README 说到了该说的，且指的路径都在
# ---------------------------------------------------------------------------
def test_readme_covers_the_operational_facts(readme):
    """README 必须覆盖"外部用户按手册能否用"真正卡人的那几件事。"""
    for needle, why in (
        ("CODEX_HOME", "不写就 PermissionError"),
        ("$$", "N-101 裸 $"),
        ("OPENAI_BASE_URL", "模型端点怎么指"),
        ("--max-tokens", "本 harness 是 token 先撞闸，不是 calls"),
        ("budget_exceeded", "判据认 reason 不认状态码"),
        ("ops/reports/m6_all/", "真跑证据路径"),
        ("runs_in/m6/", "原始 run 目录"),
        ("deepseek-v4-flash", "模型待换：上游实际服务的 id"),
        ("gb-cx-u", "镜像名"),
    ):
        assert needle in readme, f"harnesses/codex/README.md 里没写 {needle!r}（{why}）"


def test_readme_repo_paths_exist(readme):
    """README 里提到的**仓库内**路径必须真的存在。

    指向不存在的文件时，读者的第一反应是"我环境不对"而不是"文档漂了"——
    那是最贵的一种错。`$GENEBENCH_ROOT` 下的路径不在仓库里，不在此列。
    """
    cands = {s.strip("`") for s in re.findall(r"`(ops/[^`\s]+|harnesses/[^`\s]+)`", readme)}
    missing = sorted(p for p in cands
                     if not any(ch in p for ch in "<>$*") and not (REPO / p).exists())
    assert not missing, f"README 指向不存在的仓库路径：{missing}"
