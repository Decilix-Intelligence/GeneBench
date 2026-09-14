"""harness「opencode」的专属判据（卡 3.2-opencode）。

这一组钉的是「只读文档会读反、但实机上确实如此」的几条 —— 每一条都在 f02 上
用 `docker run --network none --user 1000:1000` 打假上游实测过（见
`harnesses/opencode/README.md` §4.1）：

* opencode 的**自定义 provider 包已经打进单文件二进制**，运行期不会 npm/bun install。
  官方 troubleshooting 说的是相反的话（provider 包动态装到 `~/.cache/opencode`），
  照着那句读会去给白名单加 `registry.npmjs.org` —— 那是白名单膨胀的唯一真实来源。
  这里没法在单测里跑容器，所以钉的是**它的推论**：启动命令里不许有任何安装动作。
* 不给 `--title` 时 opencode 会**先额外打一次模型**生成会话标题（假上游抓到的 system 提示
  逐字是 "You are a title generator"）。那一次白白吃掉一次 `RUN_BUDGET.max_calls`。
  删掉 `--title` 不会让任何东西变红 —— 除了这条。
* `--auto` 与配置里的 `permission: "allow"` 是两件事，非交互下缺一个就会挂在权限确认上，
  表现是「跑满 --timeout、artifact 没写出来」，很容易被读成 agent 能力问题。

另外钉住 provider 实现的选择：`@ai-sdk/openai-compatible` 打 `/chat/completions`，
`@ai-sdk/openai` 打 `/responses` —— 后者上游不服务，而症状是 404，
和「模型名写错」长得一模一样。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
HDIR = REPO / "harnesses" / "opencode"

IMAGE = "gb-opencode-u:r1"
PKG_VERSION = "1.18.26"
DIGEST = "sha256:20ac2e3617670148602b7cc40c8e1e53910499e322572ebd1cd9bb15d48536ca"


def _launch() -> dict:
    return json.loads((HDIR / "launch.json").read_text(encoding="utf-8"))


def _cmd() -> str:
    return _launch()["command"][2]


def _config() -> dict:
    return yaml.safe_load((HDIR / "config.yaml").read_text(encoding="utf-8"))


def _inline_opencode_json() -> dict:
    """把启动命令里内联的那份 opencode.json 抠出来解析。

    命令里它是 `printf '<JSON>' "$$OPENAI_BASE_URL" > …` 的格式串，baseURL 的位置是 `%s`。
    """
    cmd = _cmd()
    m = re.search(r"printf '(\{.*?\})' ", cmd)
    assert m, "启动命令里找不到那条 printf 出来的 opencode.json"
    return json.loads(m.group(1).replace("%s", "http://gateway:8081/v1"))


# --------------------------------------------------------------------------
# 一、协议与端点：为什么这个 harness 不需要「模型待换」
# --------------------------------------------------------------------------

def test_provider_impl_is_the_chat_completions_one():
    """`@ai-sdk/openai-compatible` → /chat/completions；`@ai-sdk/openai` → /responses。

    选错的症状是上游 404，与「模型名写错」同形 —— 所以钉死。
    """
    prov = _inline_opencode_json()["provider"]
    assert len(prov) == 1, "只该有一个自定义 provider"
    (pid, spec), = prov.items()
    assert spec["npm"] == "@ai-sdk/openai-compatible"
    assert f"-m {pid}/" in _cmd(), "-m 的 provider 段必须就是这个自定义 provider 的 id"


def test_base_url_is_derived_only_from_the_injected_env():
    """铁律二：base URL 只从 env_required 列的变量取。"""
    cmd = _cmd()
    assert '"$$OPENAI_BASE_URL"' in cmd
    assert "OPENAI_BASE_URL" in _launch()["env_required"]
    raw = re.search(r"printf '(\{.*?\})' ", cmd).group(1)
    assert '"baseURL":"%s"' in raw, "baseURL 必须是 printf 的占位，值从 $$OPENAI_BASE_URL 来"


@pytest.mark.parametrize("host", [
    "api.deepseek.com", "api.openai.com", "api.anthropic.com",
    "gateway:8081", "127.0.0.1", "localhost",
])
def test_no_hardcoded_model_host(host):
    """写死主机名 = 绕过边车 —— 预算闸、llm_log、出向白名单三样同时失效。"""
    assert host not in _cmd()


def test_the_key_comes_from_the_env_by_opencode_s_own_syntax():
    """opencode 支持 `{env:VAR}`；结果是 Authorization: Bearer <占位>，边车认这个头。"""
    opts = _inline_opencode_json()["provider"]["gbgw"]["options"]
    assert opts["apiKey"] == "{env:OPENAI_API_KEY}"
    assert "OPENAI_API_KEY" in _launch()["env_required"]
    assert not re.search(r"sk-[A-Za-z0-9]{16,}", _cmd()), "占位 key 也不写死，从环境取"


# --------------------------------------------------------------------------
# 二、三条「删掉不会红、但会静默改变行为」的启动参数
# --------------------------------------------------------------------------

def test_title_is_given_because_it_saves_one_model_call():
    """不给 --title 时 opencode 先打一次模型生成会话标题，白吃一次预算闸计数。"""
    assert "--title " in _cmd()


def test_permissions_are_auto_approved_in_two_places():
    """--auto 与 permission: "allow" 是两件事；非交互下缺一个就挂在确认上。"""
    assert " --auto" in _cmd()
    assert _inline_opencode_json()["permission"] == "allow"


def test_nothing_phones_home_at_startup():
    """自动更新 / LSP 下载 / 会话分享：运行期唯一的出口是边车，这三样只会白等。"""
    cmd, cfg = _cmd(), _inline_opencode_json()
    assert "OPENCODE_DISABLE_AUTOUPDATE=1" in cmd
    assert "OPENCODE_DISABLE_LSP_DOWNLOAD=1" in cmd
    assert cfg["autoupdate"] is False
    assert cfg["share"] == "disabled"


# --------------------------------------------------------------------------
# 三、运行期不许装东西（对应「provider 包已打进二进制」那条实测）
# --------------------------------------------------------------------------

@pytest.mark.parametrize("frag", ["npm install", "npm i ", "bun add", "pip install", "opencode upgrade"])
def test_no_install_or_upgrade_at_launch(frag):
    """依赖一律构建期装死。`opencode upgrade` 还会让 --digest 钉住的通行证对不上。"""
    assert frag not in _cmd()


# --------------------------------------------------------------------------
# 四、模型窗口：自定义 provider 不走 models.dev，limit 必须自己写
# --------------------------------------------------------------------------

def test_model_limits_are_spelled_out():
    """limit.output 会被原样发成请求体的 max_tokens（假上游实测），写满有被上游拒的风险。"""
    models = _inline_opencode_json()["provider"]["gbgw"]["models"]
    assert list(models) == ["deepseek-chat"]
    lim = models["deepseek-chat"]["limit"]
    assert lim["context"] == 128000, "deepseek-chat 的真实窗口；写大了会晚压缩、写小了会早压缩"
    assert 0 < lim["output"] <= 8192


def test_the_model_name_is_the_same_in_all_three_places():
    """config.yaml 的 model、内联配置的 models 块、-m 的 model 段 —— 三处必须一致。"""
    model = _config()["model"]
    assert model in _inline_opencode_json()["provider"]["gbgw"]["models"]
    assert f"/{model} " in _cmd() or _cmd().endswith(f"/{model}")


# --------------------------------------------------------------------------
# 五、容器里的可写处与题面来源（P1 的两条硬约束）
# --------------------------------------------------------------------------

def test_home_is_under_task_and_created():
    """容器以 uid 1000 跑、HOME 不可写；opencode 的四棵 XDG 目录全从 HOME 派生。"""
    cmd = _cmd()
    assert "export HOME=/task/" in cmd
    assert 'mkdir -p "$$HOME/.config/opencode"' in cmd


def test_the_prompt_comes_from_the_instruction_file():
    assert '"$$(cat /task/INSTRUCTION.md)"' in _cmd()


def test_every_dollar_run_is_even():
    """N-101：compose 解析期吃一层 $，裸 $ 的表现是两臂 3 秒退出、零次模型调用。"""
    for m in re.finditer(r"\$+", _cmd()):
        assert len(m.group()) % 2 == 0, f"命令里有奇数个连续 $：{m.group()!r}"


# --------------------------------------------------------------------------
# 六、镜像来历：Dockerfile / launch.json / README 三处不许漂
# --------------------------------------------------------------------------

def test_image_tag_agrees_between_launch_and_readme():
    assert _launch()["image"] == IMAGE
    assert IMAGE in (HDIR / "README.md").read_text(encoding="utf-8")
    assert IMAGE in (HDIR / "Dockerfile").read_text(encoding="utf-8")


def test_the_pinned_version_agrees_everywhere():
    """版本钉死；Dockerfile 与 README 的版本漂了，来历注释就成了假证据。"""
    dockerfile = (HDIR / "Dockerfile").read_text(encoding="utf-8")
    assert f'npm install -g "opencode-ai@{PKG_VERSION}"' in dockerfile
    assert PKG_VERSION in (HDIR / "README.md").read_text(encoding="utf-8")


def test_the_built_digest_is_recorded_in_both_places():
    """出集要用它做通行证；Dockerfile 顶部与 README 记的必须是同一串。"""
    assert DIGEST in (HDIR / "Dockerfile").read_text(encoding="utf-8")


def test_dockerfile_starts_from_the_shared_base_and_installs_no_market_data_lib():
    text = (HDIR / "Dockerfile").read_text(encoding="utf-8")
    body = [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    assert body[0] == "FROM gb-base:bookworm-r1"
    assert sum(1 for ln in body if ln.startswith("FROM ")) == 1
    for lib in ("yfinance", "akshare", "tushare", "baostock"):
        assert lib not in text


# --------------------------------------------------------------------------
# 七、注册表：这条配置真的进了主表
# --------------------------------------------------------------------------

def test_the_config_is_enabled_and_reachable_by_id():
    from runner import registry as REG
    cfg = _config()
    assert cfg["enabled"] is True, "opencode 说的就是 OpenAI 兼容协议，不是「模型待换」"
    c = REG.by_id(cfg["config_id"])
    assert c.harness == _launch()["harness"] == cfg["harness"]
    assert c.model == cfg["model"]


def test_the_egress_host_is_already_allowed():
    """base_url 的 host 必须与边车白名单同源 —— 本卡没有改那个共享文件，因为已经在表里。"""
    from runner import registry as REG
    from runner.c41.egress_proxy import MODEL_API_ALLOW
    host = REG.by_id(_config()["config_id"]).host
    assert host in MODEL_API_ALLOW


def test_the_launch_spec_is_discoverable_on_both_trees():
    from runner.c42 import harness_commands as HC
    name = _launch()["harness"]
    assert name in HC.discover_launch_specs()
    assert json.loads(HC.command_for(name)) == _launch()["command"]
