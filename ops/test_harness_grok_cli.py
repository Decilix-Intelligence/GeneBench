"""harness「Grok CLI」的专属判据（卡 3.2）。

本 harness **没有改边车**，也不需要改：Grok CLI 走的是 xAI 的 OpenAI 兼容协议
（`POST $GROK_BASE_URL/chat/completions` + `Authorization: Bearer`），
这正是边车的主路径。它真正独有、也真正踩过的是另外三类东西：

1. **运行时不是 Node 而是 Bun** —— 而包自己的 `engines` 说 `node>=18`。
   判据落在 Dockerfile 上：装不装 `bun` 是「跑得起来」和「一跑就没了」的分界。
2. **两个会安静吃掉预算闸计数的默认值**：`GROK_MAX_TOKENS` 默认 16384
   （deepseek-chat 上限 8192，不压下去第一个请求就被上游拒）；
   `recapsEnabled` 默认开，每轮用**写死的** `grok-4.20-non-reasoning` 再打一次
   注定失败的请求 —— 失败被 `catch` 吞掉，**不报错**，但照样计数。
   这两条的共同点是：出错时**看起来不像出错**，所以必须由测试钉着。
3. **`-k/--api-key` 会把 key 落盘**到 `~/.grok/user-settings.json`
   （`dist/index.js:262` 的 `saveUserSettings`）。红线 3 的边上，值得一条反向判据。

行号引用的是容器内 `$(npm root -g)/grok-dev/dist/**`（grok-dev@1.1.7）与
`@ai-sdk/xai@3.0.130` 的 `dist/index.js`。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
HDIR = REPO / "harnesses" / "grok-cli"


def _launch() -> dict:
    return json.loads((HDIR / "launch.json").read_text(encoding="utf-8"))


def _cmd() -> str:
    return _launch()["command"][2]


def _cfg() -> dict:
    return yaml.safe_load((HDIR / "config.yaml").read_text(encoding="utf-8"))


def _dockerfile() -> str:
    return (HDIR / "Dockerfile").read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# 一、launch.json：模型端点的来历
# --------------------------------------------------------------------------

def test_base_url_is_passed_through_untouched():
    """铁律二：base URL 只从 env_required 列的变量取。

    Grok 与另两个 harness 的差别值得写死一条判据：xAI 的默认 base URL 自带 `/v1`
    （`@ai-sdk/xai` 的 `?? "https://api.x.ai/v1"`），和边车注入的
    `http://gateway:8081/v1` 形状一致 —— 所以这里**不削尾巴**。
    谁要是照 claude-code / gemini 的样子加一个 `%/v1`，请求会打到
    `http://gateway:8081/chat/completions`，上游 404。
    """
    cmd = _cmd()
    assert 'export GROK_BASE_URL="$$OPENAI_BASE_URL"' in cmd
    assert "%/v1" not in cmd, "xAI 的 base URL 本来就带 /v1，不要削尾巴"
    assert "OPENAI_BASE_URL" in _launch()["env_required"]


@pytest.mark.parametrize("host", [
    "api.x.ai", "api.deepseek.com", "api.openai.com",
    "api.anthropic.com", "generativelanguage.googleapis.com", "gateway:8081",
])
def test_no_hardcoded_model_host(host):
    """写死主机名 = 绕过边车 —— 预算闸、llm_log、出向白名单三样同时失效。"""
    assert host not in _cmd()


def test_the_placeholder_key_comes_from_the_env_too():
    cmd = _cmd()
    assert 'export GROK_API_KEY="$$OPENAI_API_KEY"' in cmd
    assert "sk-genebench-placeholder" not in cmd, "占位 key 也不该写死，从环境取"


def test_the_key_is_never_passed_as_a_cli_flag():
    """`-k/--api-key` 会被 `resolveConfig` 落盘到 ~/.grok/user-settings.json
    （dist/index.js:262）。环境变量那条路 `getApiKey()` 只读不写。"""
    cmd = _cmd()
    assert "--api-key" not in cmd
    assert not re.search(r"(?<![\w-])-k(?![\w-])", cmd)


# --------------------------------------------------------------------------
# 二、两个会安静吃掉预算的默认值
# --------------------------------------------------------------------------

def test_max_output_tokens_is_clamped_below_the_upstream_limit():
    """`Agent` 构造函数（agent.js:402）：`GROK_MAX_TOKENS` 不设就是 16384，
    而 deepseek-chat 的输出上限是 8192 —— **第一个请求**就会被上游按
    max_tokens 超限拒掉。表现是「一次调用、零产物」，很容易被读成 agent 没做完。"""
    m = re.search(r"export GROK_MAX_TOKENS=(\d+)", _cmd())
    assert m, "必须显式设 GROK_MAX_TOKENS（默认 16384 > deepseek-chat 的 8192）"
    assert 0 < int(m.group(1)) <= 8192


def test_session_recap_is_turned_off():
    """`loadRecapsEnabled()` 是 `!== false`，即**默认开**（settings.js:446）。
    开着的话每轮结束会用写死的 `grok-4.20-non-reasoning` 再打一次请求
    （agent.js:644 → grok/client.js 的 DEFAULT_RECAP_MODEL），在 DeepSeek 上必然失败，
    失败被 catch 吞掉、**不报错**，但**照样占一次预算闸计数**。"""
    cmd = _cmd()
    assert '"recapsEnabled":false' in cmd
    assert "user-settings.json" in cmd


def test_sandbox_is_explicitly_off():
    """默认已是 off（settings.js:427），但 /task 下若有 .grok/settings.json
    会被当项目设置读进来；容器里也没有 Shuru sandbox。显式关掉。"""
    assert "--no-sandbox" in _cmd()


# --------------------------------------------------------------------------
# 三、无头模式与容器约束
# --------------------------------------------------------------------------

def test_headless_flag_and_instruction_are_wired():
    """`-p/--prompt` 是无头开关（index.js:290），走 runHeadless()、不起 TUI。"""
    cmd = _cmd()
    assert '-p "$$(cat /task/INSTRUCTION.md)"' in cmd
    assert "--format text" in cmd


def test_home_is_redirected_under_task():
    """容器以 uid 1000 跑、HOME 不可写；grok 的**全部**状态都在 os.homedir()/.grok 下
    （user-settings.json、bun:sqlite 的 grok.db、workspace-trust.json）。"""
    cmd = _cmd()
    assert "export HOME=/task/.grok_home" in cmd
    assert 'mkdir -p "$$HOME/.grok"' in cmd


def test_no_invented_home_variable():
    """反向判据：Grok CLI **没有** GROK_HOME 这类变量，settings.js:60 直接用
    os.homedir()。设一个不存在的变量会让下一个人以为 HOME 那行可以省。"""
    assert "GROK_HOME" not in _cmd()


def test_every_dollar_run_is_even():
    """N-101：compose 解析期吃掉一层 $，所以命令里每一段连续的 $ 必须是偶数个。
    落单的 $ 的表现是两臂 3 秒退出、零次调用。"""
    odd = [m.group(0) for m in re.finditer(r"\$+", _cmd()) if len(m.group(0)) % 2]
    assert odd == []


# --------------------------------------------------------------------------
# 四、Dockerfile：Bun 是硬依赖，而包自己的 engines 说不是
# --------------------------------------------------------------------------

def test_bun_is_installed_and_pinned():
    """`dist/storage/db.js` 第一行是 `import { Database } from "bun:sqlite"` ——
    Bun 独有的内建模块，Node 上没有等价物。不装 bun 的表现是
    `/usr/bin/env: 'bun': No such file or directory`（**装得上、一跑就没了**）。"""
    df = _dockerfile()
    assert re.search(r'npm install -g[^\n]*"bun@\d+\.\d+\.\d+"', df), \
        "必须装 bun，且钉死版本"


def test_the_cli_package_is_the_maintained_one_and_pinned():
    """D-21：`@vibe-kit/grok-cli` 停更（latest 0.0.34 / 2025-11-27），
    活跃的是 superagent-ai/grok-cli，npm 包名是 `grok-dev`。"""
    df = _dockerfile()
    assert '"grok-dev@1.1.7"' in df
    assert "@vibe-kit/grok-cli@" not in df, "停更的包不用于构建（只在 README 记一句）"


def test_dockerfile_records_where_the_package_came_from():
    """W-0 要求顶部注明来历。这里再多要一条：dist 的 shasum ——
    「钉死版本」不等于「钉死内容」，版本号可以被重发。"""
    df = _dockerfile()
    assert "e67dc2739cd613ffdfc88b693ee8a36617b81171" in df
    assert "gb-grok-cli-u:r1" in df


def test_single_from_on_the_shared_base():
    df = _dockerfile()
    froms = [ln.strip() for ln in df.splitlines()
             if ln.strip().startswith("FROM ")]
    assert froms == ["FROM gb-base:bookworm-r1"], \
        "N-62 统一基座；注入器 P4c 也只允许 1 条 FROM"


@pytest.mark.parametrize("lib", ["pandas", "pyarrow", "akshare", "tushare", "duckdb"])
def test_no_market_data_library_in_the_image(lib):
    """红线：被测系统必须经数据网关取数，镜像里不许自带行情库。"""
    body = "\n".join(ln for ln in _dockerfile().splitlines()
                     if not ln.lstrip().startswith("#"))
    assert lib not in body


# --------------------------------------------------------------------------
# 五、config.yaml：与 launch.json、与白名单的一致性
# --------------------------------------------------------------------------

def test_harness_name_matches_launch_json():
    assert _cfg()["harness"] == _launch()["harness"] == "Grok CLI"


def test_config_registers_the_upstream_the_sidecar_actually_reaches():
    """config.yaml 的 base_url 登记的是**边车实际转发到的上游**
    （collect_egress_hosts() 拿它和 MODEL_API_ALLOW 对键集），不是 harness 的原产地
    api.x.ai —— 写后者会要求把一个没有 key、也没有配置真在用的主机加进白名单。"""
    cfg = _cfg()
    assert cfg["base_url"] == "https://api.deepseek.com"
    assert cfg["model"] == "deepseek-chat"
    assert cfg["api_key_env"] == "DEEPSEEK_API_KEY"


def test_the_upstream_host_is_already_allowed():
    from runner.c41 import egress_proxy as ep
    host = urlsplit(_cfg()["base_url"]).hostname
    assert host in ep.MODEL_API_ALLOW, \
        "本 harness 不该给白名单加新域名 —— 加了就说明 base_url 写错了"


def test_model_pending_is_stated_in_the_note():
    """接的是「Grok CLI 这套 harness × DeepSeek 这个模型」。
    换回真 Grok 要 XAI key + api.x.ai 进白名单 + 过 M7（同模型断言）。"""
    assert "模型待换" in _cfg()["note"]


def test_config_id_is_unique_across_the_harness_tree():
    ids = {}
    for p in sorted((REPO / "harnesses").glob("*/config.yaml")):
        cid = yaml.safe_load(p.read_text(encoding="utf-8"))["config_id"]
        assert cid not in ids, f"{p} 与 {ids.get(cid)} 的 config_id 重名：{cid}"
        ids[cid] = p
    assert _cfg()["config_id"] in ids


# --------------------------------------------------------------------------
# 六、边车：本 harness 走的是主路径，判据是「它确实走主路径」
# --------------------------------------------------------------------------

# 按 @ai-sdk/xai@3.0.130 的 dist/index.js:566（url）与 :3584（Authorization 头）构造。
GROK_HEAD = (
    b"POST /v1/chat/completions HTTP/1.1\r\n"
    b"host: gateway:8081\r\n"
    b"content-type: application/json\r\n"
    b"authorization: Bearer sk-genebench-placeholder\r\n"
    b"user-agent: ai-sdk/xai/3.0.130 runtime/bun/1.4.2\r\n"
    b"accept-encoding: gzip, deflate\r\n"
    b"\r\n"
)


def _ep():
    from runner.c41 import egress_proxy as ep
    return ep


def test_the_placeholder_is_recognised_not_treated_as_foreign():
    ep = _ep()
    key = ep._client_key(GROK_HEAD)
    assert key == ep.PLACEHOLDER_KEY
    assert not (key and key != ep.PLACEHOLDER_KEY), "占位 key 不该判 foreign_credential"


def test_sidecar_swaps_in_the_real_bearer_and_the_upstream_host():
    ep = _ep()
    out = ep._replace_auth(GROK_HEAD, "REAL-KEY-NOT-A-SECRET", "api.deepseek.com")
    assert b"authorization: Bearer REAL-KEY-NOT-A-SECRET" in out
    assert out.lower().count(b"\r\nauthorization:") == 1, "只该有一条"
    assert b"host: api.deepseek.com" in out
    assert b"sk-genebench-placeholder" not in out, "占位 key 不该被转发到上游"
    # 请求行必须原样保留：/v1/chat/completions 正是 DeepSeek 的端点
    assert out.split(b"\r\n", 1)[0] == b"POST /v1/chat/completions HTTP/1.1"


def test_a_self_supplied_key_would_still_be_rejected():
    """反向判据：agent 真自带了一把 key 时仍要判 foreign_credential。"""
    ep = _ep()
    head = GROK_HEAD.replace(
        b"authorization: Bearer sk-genebench-placeholder",
        b"authorization: Bearer someones-own-key-value")
    key = ep._client_key(head)
    assert key == "someones-own-key-value"
    assert key != ep.PLACEHOLDER_KEY


# --------------------------------------------------------------------------
# 七、真跑之后才知道的两件事（2026-09-07，batch h_grok-cli）
# --------------------------------------------------------------------------

def test_the_bun_runtime_transpiler_cache_is_off():
    """bun 的**运行时转译缓存**默认落在 $HOME/.bun/install/cache/@t@/，
    而 HOME 在 /task 下 —— 真跑实测每次往 /task 写 297 个 .pile，
    run.json 的 unexpected 里于是有 297 条噪声，P8 的封闭性检查被淹掉。

    容器内实测过三种写法：BUN_INSTALL_CACHE_DIR 与 BUN_INSTALL **都不管用**
    （管的是包安装缓存，不是转译缓存），只有这一个管用：297 → 0。
    """
    cmd = _cmd()
    assert "export BUN_RUNTIME_TRANSPILER_CACHE_PATH=0" in cmd
    assert "BUN_INSTALL_CACHE_DIR" not in cmd, "那个变量对转译缓存不管用，写了会误导下一个人"


def test_the_config_stays_out_of_the_main_table_until_a_real_xai_endpoint():
    """**enabled: false 是结论，不是没做完。**

    真跑两臂都跑完、104 次调用除预算闸那条 429 外全部 allow/200，链路无一处可疑；
    但 @ai-sdk/xai 的流式 chunk schema 要求每一片 tool_calls 自带 id/type/function.name，
    DeepSeek（以及 OpenAI 本身）的续片只带 index + 参数片段 —— 续片整片被 zod 丢弃，
    工具参数恒为 {}，agent 一步也走不动。这样的配置进主表只会得到一个
    会被误读成「Grok CLI 能力差」的 0（与 gemini-cli 同理）。

    要重跑：临时翻成 true → ops/push_exec_to_f02.sh --with-launch-data → 跑完翻回来。
    """
    cfg = _cfg()
    assert cfg["enabled"] is False
    assert "拿不到可评分产物" in cfg["note"]


def test_the_reason_is_recorded_where_the_next_person_will_look():
    """判据放在 README 上：下一个人接手时先读的是它，不是这个测试。
    三件都要在：根因（schema）、对照实验（假上游）、以及「不要在容器里 patch」。"""
    readme = (HDIR / "README.md").read_text(encoding="utf-8")
    assert "xaiChatChunkSchema" in readme or "chunk schema" in readme
    assert "假上游" in readme
    assert "HELLO_FROM_TOOL" in readme, "对照实验那一组的证据串要留在文档里"
