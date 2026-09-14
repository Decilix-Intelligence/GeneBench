"""harness「Gemini CLI」的专属判据（卡 3.2）。

本 harness **没有改边车**，但它能跑通恰恰依赖边车的一条**没有被任何测试覆盖**的行为：
「请求里没有 `Authorization` 头」时，`_client_key()` 返回 `None`，
于是 `if key and key != PLACEHOLDER_KEY` 不成立（**不判 foreign_credential**），
随后 `_replace_auth()` 因 `seen_auth is False` 而**插入**一条真 key 的 `Authorization`。

Gemini CLI 发的是 `x-goog-api-key`，不是 `Authorization` —— 真跑实测（f02，
`s2-cor-01.*.cfg-gemini-cli-deepseek.r01` 的 `llm_log`）拿到的是
`decision: "allow"` + 上游 404，而**不是** 403 foreign_credential。
如果哪天有人把「没有 Authorization」改成拒绝（看起来像是收紧安全），
这个 harness 会**静默**失效：表现是 403 而不是 404，而 403 很容易被读成
「agent 自带了 key」去查一件不存在的事。这组测试就是钉住那条行为。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
HDIR = REPO / "harnesses" / "gemini-cli"


def _launch() -> dict:
    return json.loads((HDIR / "launch.json").read_text(encoding="utf-8"))


def _cmd() -> str:
    return _launch()["command"][2]


# --------------------------------------------------------------------------
# 一、launch.json：base URL 的来历
# --------------------------------------------------------------------------

def test_base_url_is_derived_only_from_the_injected_env():
    """铁律二：base URL 只从 env_required 列的变量取，不写死主机名。

    Gemini CLI 自己会在 base URL 后面接 `/v1beta/models/<model>:...`，
    而边车注入的是 `http://gateway:8081/v1` —— 所以要削掉尾巴上的 `/v1`，
    否则 path 变成 `/v1/v1beta/...`（上游 404，且很像是模型名写错）。
    """
    cmd = _cmd()
    assert 'GOOGLE_GEMINI_BASE_URL="$${OPENAI_BASE_URL%/v1}"' in cmd
    assert "OPENAI_BASE_URL" in _launch()["env_required"]


@pytest.mark.parametrize("host", [
    "generativelanguage.googleapis.com", "api.deepseek.com",
    "api.openai.com", "api.anthropic.com", "gateway:8081",
])
def test_no_hardcoded_model_host(host):
    """写死主机名 = 绕过边车 —— 预算闸、llm_log、出向白名单三样同时失效。"""
    assert host not in _cmd()


def test_the_placeholder_key_comes_from_the_env_too():
    cmd = _cmd()
    assert 'GEMINI_API_KEY="$$OPENAI_API_KEY"' in cmd
    assert "sk-genebench-placeholder" not in cmd, "占位 key 也不该写死，从环境取"


# --------------------------------------------------------------------------
# 二、launch.json：两条「不写就零调用退出」的前置
# --------------------------------------------------------------------------

def test_auth_type_is_preselected():
    """不预写 security.auth.selectedType，CLI 只打一行
    `Invalid auth method selected.` 就退出 —— **零次模型调用**，看起来像「跑过了」。"""
    cmd = _cmd()
    assert '"selectedType":"gemini-api-key"' in cmd
    assert '"security"' in cmd


def test_folder_trust_is_disabled_both_ways():
    """/task 不受信任时 approval-mode 被强制降回 default，yolo 失效、非交互下卡住。"""
    cmd = _cmd()
    assert '"folderTrust":{"enabled":false}' in cmd
    assert "--skip-trust" in cmd
    assert "--approval-mode yolo" in cmd


def test_home_is_redirected_under_task():
    """容器以 uid 1000 跑、HOME 不可写；/task 是唯一可写处。"""
    cmd = _cmd()
    assert "export HOME=/task/.gemini_home" in cmd
    assert "mkdir -p" in cmd


def test_instruction_is_the_prompt():
    assert '"$$(cat /task/INSTRUCTION.md)"' in _cmd()


# --------------------------------------------------------------------------
# 三、config.yaml：模型待换的状态要显式
# --------------------------------------------------------------------------

def test_config_is_disabled_and_says_why():
    cfg = yaml.safe_load((HDIR / "config.yaml").read_text(encoding="utf-8"))
    assert cfg["enabled"] is False, (
        "DeepSeek 不服务 Gemini 协议（真跑上游 404）——「跑得起来但拿不到模型输出」"
        "的配置不进主表。要翻开关，见 harnesses/gemini-cli/README.md §6")
    assert "模型待换" in cfg["note"]
    assert cfg["harness"] == _launch()["harness"] == "Gemini CLI"


def test_base_url_registers_the_upstream_the_sidecar_actually_reaches():
    """config.yaml 的 base_url 登记的是**边车实际转发到的上游**：
    `collect_egress_hosts()` 拿它去和 `MODEL_API_ALLOW` 对键集。
    写 Google 的域名会要求把一个不可达、也没有任何配置真在用的主机加进白名单。"""
    cfg = yaml.safe_load((HDIR / "config.yaml").read_text(encoding="utf-8"))
    assert cfg["base_url"] == "https://api.deepseek.com"
    assert cfg["api_key_env"].endswith("_API_KEY")


# --------------------------------------------------------------------------
# 四、边车：本 harness 依赖的那条「没有 Authorization」的行为
# --------------------------------------------------------------------------

# 真跑实测抓到的请求头（f02 冒烟，假上游打印）——照抄，别「整理」。
GEMINI_HEAD = (
    b"POST /v1beta/models/deepseek-chat:streamGenerateContent?alt=sse HTTP/1.1\r\n"
    b"host: gateway:8081\r\n"
    b"user-agent: GeminiCLI-tui/0.58.0/deepseek-chat (linux; x64; terminal)\r\n"
    b"x-goog-api-client: google-genai-sdk/1.30.0 gl-node/v22.23.2\r\n"
    b"content-type: application/json\r\n"
    b"x-goog-api-key: sk-genebench-placeholder\r\n"
    b"accept-encoding: gzip, deflate\r\n"
    b"\r\n"
)


def _ep():
    from runner.c41 import egress_proxy as ep
    return ep


def test_gemini_request_is_not_read_as_a_foreign_credential():
    """x-goog-api-key 不是 Authorization —— key 取不到就是 None，
    而守门条件是 `if key and key != PLACEHOLDER_KEY`，None 不触发。"""
    ep = _ep()
    key = ep._client_key(GEMINI_HEAD)
    assert key is None
    assert not (key and key != ep.PLACEHOLDER_KEY), "不该判 foreign_credential"


def test_sidecar_inserts_the_real_bearer_when_there_is_no_authorization():
    ep = _ep()
    out = ep._replace_auth(GEMINI_HEAD, "REAL-KEY-NOT-A-SECRET", "api.deepseek.com")
    assert b"authorization: Bearer REAL-KEY-NOT-A-SECRET" in out
    assert out.lower().count(b"\r\nauthorization:") == 1, "只该有一条"
    assert b"host: api.deepseek.com" in out, "Host 要换成上游"
    # 请求行必须原样保留：模型名在 path 里，改坏了表现为上游 404
    assert out.split(b"\r\n", 1)[0] == GEMINI_HEAD.split(b"\r\n", 1)[0]


def test_placeholder_is_forwarded_in_x_goog_api_key_and_that_is_fine():
    """占位 key 会被原样转发到上游。它是公开的（写在 egress_proxy.py 里），
    不构成凭据泄露 —— 这条写成测试是为了让下一个人不必重新论证一遍。"""
    ep = _ep()
    out = ep._replace_auth(GEMINI_HEAD, "REAL-KEY-NOT-A-SECRET", "api.deepseek.com")
    assert b"x-goog-api-key: " + ep.PLACEHOLDER_KEY.encode() in out


def test_a_self_supplied_key_would_still_be_rejected():
    """反向判据：真自带了一把 key（写进 Authorization）时仍要判 foreign_credential，
    不能因为迁就 Gemini 就把这道门整个拆了。"""
    ep = _ep()
    head = GEMINI_HEAD.replace(
        b"content-type: application/json\r\n",
        b"content-type: application/json\r\nauthorization: Bearer sk-someones-own-key\r\n")
    key = ep._client_key(head)
    assert key == "sk-someones-own-key"
    assert key != ep.PLACEHOLDER_KEY
