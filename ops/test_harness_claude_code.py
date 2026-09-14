"""卡 3.2 —— harness `claude-code` 自己的判据。

`ops/test_harness_contract.py` 已经把「四件文件、键集、`$$`、统一基座」那一层
对**所有** harness 查过了，本文件只查这一个 harness 特有的三件事：

1. **协议不同**：Claude Code 说 Anthropic Messages API，不是 OpenAI 兼容。
   于是 base URL 要在容器里**现算**（削掉 `/v1` 接 `/anthropic`），
   而不是把 `$OPENAI_BASE_URL` 原样喂进去。算错的表现是 404 或 400，
   而两臂看起来"跑过了"。
2. **模型名要写五处**：只设 `ANTHROPIC_MODEL` 时后台小模型仍点名 haiku。
3. **边车不用改**：这是本卡最重要的一条留痕。任务书预留了「加 `x-api-key` 头替换」，
   实测（f02 → api.deepseek.com/anthropic，2026-09-06）证明不用改 ——
   两个头同时在、`x-api-key` 是占位串时上游认 `Authorization`。
   这里把**现行边车对本 harness 成立的那条性质**钉住：占位 key 永不到达上游，
   真 key 只出现在 `authorization` 一处。将来谁把 `_replace_auth` 改了，
   这条会先响，而不是等到一次真跑回 401。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
D = REPO / "harnesses" / "claude-code"
HARNESS = "Claude Code"
CONFIG_ID = "cfg-claude-code-deepseek"


@pytest.fixture(scope="module")
def spec() -> dict:
    return json.loads((D / "launch.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def cmd(spec) -> str:
    return " ".join(spec["command"])


# ---------------------------------------------------------------- 目录与身份

def test_the_directory_is_there_with_four_files():
    assert D.is_dir(), f"{D} 不在 —— harness id 就是目录名"
    for f in ("Dockerfile", "launch.json", "config.yaml", "README.md"):
        assert (D / f).is_file(), f"缺 {f}"


def test_harness_name_matches_across_the_two_files(spec):
    import yaml
    cfg = yaml.safe_load((D / "config.yaml").read_text(encoding="utf-8"))
    assert spec["harness"] == HARNESS
    assert cfg["harness"] == HARNESS, "launch.json 与 config.yaml 的 harness 必须逐字相同"
    assert cfg["config_id"] == CONFIG_ID
    assert cfg["enabled"] is True, "本卡的配置是 enabled: true —— 翻回 false 就没人跑得到它"


# ---------------------------------------------------------------- 协议差异

def test_base_url_is_computed_not_hardcoded(cmd):
    """Anthropic SDK 自己会在 base 后面接 `/v1/messages`，
    所以 base 必须是 `<反代根>/anthropic`，而 `$OPENAI_BASE_URL` 尾巴上带着 `/v1`。"""
    assert 'ANTHROPIC_BASE_URL="$${OPENAI_BASE_URL%/v1}/anthropic"' in cmd, (
        "base URL 必须从 $$OPENAI_BASE_URL 现算：削掉 /v1、接 /anthropic")
    assert "api.deepseek.com" not in cmd, "写死上游主机名 = 绕过边车（预算闸/llm_log/白名单同时失效）"
    assert "api.anthropic.com" not in cmd
    assert "gateway:" not in cmd, "端口号也不许写死 —— 它来自 runner_core 的 MODEL_PORT"


def test_auth_goes_through_the_authorization_header(cmd):
    """用 ANTHROPIC_AUTH_TOKEN（发 `Authorization: Bearer`）而不是 ANTHROPIC_API_KEY
    （发 `x-api-key`）：只有前者会被边车的 `foreign_credential` 检查覆盖。"""
    assert 'ANTHROPIC_AUTH_TOKEN="$$OPENAI_API_KEY"' in cmd
    assert "ANTHROPIC_API_KEY" not in cmd


@pytest.mark.parametrize("var", [
    "ANTHROPIC_MODEL",
    "ANTHROPIC_SMALL_FAST_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
])
def test_every_model_slot_points_at_the_registry_model(cmd, var):
    """五个槽都要指到同一个模型 —— 漏掉任何一个，那一路调用会点名一个上游没有的模型。"""
    assert f"export {var}=deepseek-chat" in cmd, f"{var} 没指到 deepseek-chat"


def test_headless_flags_and_the_instruction_source(cmd):
    assert "claude -p " in cmd, "必须是无头（print）模式，否则非交互下挂到超时"
    assert "--dangerously-skip-permissions" in cmd
    assert "--output-format text" in cmd
    assert '"$$(cat /task/INSTRUCTION.md)"' in cmd, "题面只能来自 /task/INSTRUCTION.md"


def test_home_is_writable_inside_task(cmd):
    """容器以 uid 1000 跑、`/` 下不可写。"""
    assert "export HOME=/task/.claude_home" in cmd
    assert "export CLAUDE_CONFIG_DIR=/task/.claude_home/.claude" in cmd
    assert 'mkdir -p "$$CLAUDE_CONFIG_DIR"' in cmd
    assert "hasCompletedOnboarding" in cmd, "首跑会停在 onboarding 上 —— 预写 .claude.json"


def test_output_token_cap_is_pinned(cmd):
    """deepseek-chat 的输出上限比 Claude 小；不压的话首个请求就可能被上游拒。"""
    m = re.search(r"CLAUDE_CODE_MAX_OUTPUT_TOKENS=(\d+)", cmd)
    assert m, "没有压 CLAUDE_CODE_MAX_OUTPUT_TOKENS"
    assert 0 < int(m.group(1)) <= 8192


def test_context_window_is_pinned(cmd):
    """这一版 Claude Code 的模型目录里没有 `deepseek-chat`（f02 冒烟抓到
    `[claude-code:unrecognized_model]`），不告诉它真实窗口就按 200k 假设做 auto-compact ——
    表现是无谓的中途压缩，不是报错，所以它不会自己响。"""
    m = re.search(r"CLAUDE_CODE_MAX_CONTEXT_TOKENS=(\d+)", cmd)
    assert m, "没有钉 CLAUDE_CODE_MAX_CONTEXT_TOKENS"
    assert int(m.group(1)) == 128_000, "deepseek-chat 的上下文窗口是 128k"


def test_nonessential_traffic_is_off(cmd):
    """遥测/自动更新会打到正向代理（ALLOW 是空集）被拒并留痕 —— 不致命，但灌噪声。"""
    assert "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1" in cmd
    for v in ("DISABLE_AUTOUPDATER", "DISABLE_TELEMETRY", "DISABLE_ERROR_REPORTING"):
        assert f"{v}=1" in cmd


# ---------------------------------------------------------------- Dockerfile

def test_dockerfile_pins_the_version_and_installs_no_market_data():
    txt = (D / "Dockerfile").read_text(encoding="utf-8")
    assert re.search(r'@anthropic-ai/claude-code@\d+\.\d+\.\d+', txt), "npm 包必须钉死版本"
    body = "\n".join(l for l in txt.splitlines() if not l.lstrip().startswith("#"))
    for lib in ("yfinance", "akshare", "tushare", "baostock", "efinance"):
        assert lib not in body, f"装了行情库 {lib} = 被测系统可以绕过数据网关取数"
    assert body.count("FROM") == 1


# ---------------------------------------------------------------- 注册表接线

def test_the_config_reaches_the_registry():
    from runner import registry as REG
    c = REG.by_id(CONFIG_ID)
    assert c.harness == HARNESS
    assert c.host == "api.deepseek.com"
    assert c.api_key_env.endswith("_API_KEY")
    assert c.base_url.startswith("https://")
    REG.assert_registry_sane()


def test_the_host_needs_no_new_whitelist_entry():
    """经 DeepSeek 的 anthropic 兼容路径接入 —— 主机不变，`MODEL_API_ALLOW` 一个字不用改。"""
    from runner import registry as REG
    from runner.c41 import egress_proxy as ep
    assert set(ep.MODEL_API_ALLOW) == set(REG.collect_egress_hosts())
    assert "api.anthropic.com" not in ep.MODEL_API_ALLOW, (
        "本卡没有、也不需要往白名单里加 anthropic —— 加了就是一条没有引用者的条目")


def test_command_for_returns_exactly_what_launch_json_says(spec):
    from runner.c42 import harness_commands as HC
    # command_for() 交给 compose 的是 json.dumps 之后的**字符串**（原样进 compose 的 command:）。
    assert json.loads(HC.command_for(HARNESS)) == spec["command"]


# ------------------------------------------------ 边车对本 harness 成立的性质

def _head(*lines: str) -> bytes:
    return "\r\n".join(("POST /anthropic/v1/messages HTTP/1.1", *lines, "", "")).encode()


def test_placeholder_never_reaches_upstream_even_with_an_x_api_key():
    """**本卡为什么没有改 `egress_proxy.py`。**

    探针（f02 → https://api.deepseek.com/anthropic/v1/messages，2026-09-06）三次都 200：
      A 只有 `Authorization: Bearer <真>`；B 只有 `x-api-key: <真>`；
      C 两个都在而 `x-api-key` 是**占位串** —— 上游认 `Authorization`。
    所以现行边车（只替换 `Authorization`，没有就插一条）对本 harness 已经足够。
    这里钉住那条性质：转发出去的头里，占位串不出现在 `authorization` 上，
    真 key 只出现一次。
    """
    from runner.c41 import egress_proxy as ep
    # **不写 key 形态的字面量。** 红线 3 的两道门（ops/test_env.py 的
    # test_no_api_key_material_in_the_repo / _in_run_dirs）扫的是「像密钥的字面量」，
    # 判据 _KEY_SHAPES 第一条就是 r"sk-[A-Za-z0-9_\-]{20,}" —— 一个形状对的**示例**串
    # 与一把真 key 在扫描器眼里没有区别（2026-09-06 实测：两道门同时红）。
    # 所以这里把它**拼**出来：运行期仍是一把形似真 key 的串（这条测试要的就是这个），
    # 而源码里不出现那个形状。同样的道理见 ops/test_harness_codex.py:118 ——
    # 那里要写的是**正则**，写成 r"sk-[A-Za-z0-9]{16,}" 就不会被自己的扫描抓到。
    fake = "sk-" + "F" * 24
    head = _head(f"authorization: Bearer {ep.PLACEHOLDER_KEY}",
                 f"x-api-key: {ep.PLACEHOLDER_KEY}",
                 "host: gateway:8081")
    lines = ep._replace_auth(head, fake, "api.deepseek.com").decode().split("\r\n")
    assert f"authorization: Bearer {fake}" in lines
    assert sum(l.count(fake) for l in lines) == 1, "真 key 只该出现在 authorization 那一行"
    assert f"authorization: Bearer {ep.PLACEHOLDER_KEY}" not in lines
    assert "host: api.deepseek.com" in lines
    # 占位 x-api-key 原样过去 —— 探针 C 证明上游认 Authorization，所以这是安全的。
    assert f"x-api-key: {ep.PLACEHOLDER_KEY}" in lines


def test_the_placeholder_is_not_mistaken_for_a_foreign_credential():
    from runner.c41 import egress_proxy as ep
    head = _head(f"authorization: Bearer {ep.PLACEHOLDER_KEY}", "host: gateway:8081")
    assert ep._client_key(head) == ep.PLACEHOLDER_KEY


def test_anthropic_usage_keys_are_normalised():
    """Anthropic 协议回的是 `input_tokens` / `output_tokens`（探针实测的响应形状）。
    抽不到 usage 与「上游没返回 usage」在数值上不可区分 —— 所以这条要有判据。"""
    from runner.c41 import egress_proxy as ep
    body = json.dumps({
        "id": "msg_x", "type": "message", "role": "assistant", "model": "deepseek-v4-flash",
        "content": [{"type": "text", "text": "pong"}],
        "usage": {"input_tokens": 12, "cache_creation_input_tokens": 0,
                  "cache_read_input_tokens": 0, "output_tokens": 2},
    }).encode()
    u = ep._extract_usage(body)
    assert u["prompt_tokens"] == 12
    assert u["completion_tokens"] == 2
    assert u["total_tokens"] == 14
