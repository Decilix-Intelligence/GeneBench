# -*- coding: utf-8 -*-
"""数据驱动的启动清单与配置合并（W-0）。

**这份测试的核心是一条等式**：迁移到 `launch.json` 之后，
`command_for()` 的输出必须与迁移前的硬编码常量**逐字节相同**。
`_CODEX` / `_OPENHANDS` 两条常量因此**故意留在源码里当期望值** ——
删掉它们，「迁移有没有顺手改动送进容器的那条命令」就变成不可回答的问题，
而那条命令一个字符错（比如 `$` 没写成 `$$`）就是两臂 3 秒退出、零次模型调用。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from runner import registry as REG
from runner.c42 import harness_commands as HC

REPO = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# ① 迁移的逐字节等价
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("harness, const", [
    ("Codex CLI", "_CODEX"),
    ("OpenHands", "_OPENHANDS"),
])
def test_migrated_command_is_byte_identical_to_the_old_constant(harness, const):
    want = json.dumps(["sh", "-c", getattr(HC, const)])
    assert HC.command_for(harness) == want


@pytest.mark.parametrize("harness, hid", [
    ("Codex CLI", "codex"),
    ("OpenHands", "openhands"),
])
def test_command_really_comes_from_launch_json_not_the_fallback(harness, hid):
    """确认它**走的是数据那条路** —— 否则上面那条等式会被回退路径永绿。"""
    p = REPO / "harnesses" / hid / "launch.json"
    assert p.is_file(), f"{p} 不在 —— 迁移没做完"
    spec = json.loads(p.read_text(encoding="utf-8"))
    assert spec["harness"] == harness
    assert json.dumps(spec["command"]) == HC.command_for(harness)
    specs = HC.discover_launch_specs()
    assert harness in specs and specs[harness]["image"]


def test_fallback_still_works_when_there_is_no_launch_data(tmp_path):
    """空树 → 回退到硬编码，输出仍然一样。**回退不是死代码，是兜底路径。**"""
    assert HC.discover_launch_specs(tmp_path) == {}
    assert HC.command_for("Codex CLI", repo_root=tmp_path) == \
        json.dumps(["sh", "-c", HC._CODEX])
    assert HC.command_for("RD-Agent(Q)", repo_root=tmp_path) is None


def test_rdagent_still_has_no_command():
    """N-105 裁定不修：RD-Agent(Q) 没有 LLM 驱动路径，拿到 None 就该记 BLOCKED。"""
    assert HC.command_for("RD-Agent(Q)") is None


# ---------------------------------------------------------------------------
# ② launch.json 的判据（负例：每一条都必须能红）
# ---------------------------------------------------------------------------
GOOD = {
    "harness": "Fake Harness",
    "paradigm": "P2",
    "image": "gb-fake:r1",
    "command": ["sh", "-c", "echo hi"],
    "env_required": ["OPENAI_BASE_URL"],
    "notes": "夹具",
}


def _write(root: Path, tree: str, hid: str, spec) -> Path:
    d = root / tree / hid
    d.mkdir(parents=True)
    p = d / "launch.json"
    p.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    return p


def test_good_fixture_is_accepted(tmp_path):
    _write(tmp_path, "integrations", "fake", GOOD)
    got = HC.discover_launch_specs(tmp_path)
    assert list(got) == ["Fake Harness"]
    assert HC.command_for("Fake Harness", repo_root=tmp_path) == \
        json.dumps(["sh", "-c", "echo hi"])


def test_duplicate_harness_name_across_the_two_trees_is_red(tmp_path):
    _write(tmp_path, "harnesses", "fake_a", GOOD)
    _write(tmp_path, "integrations", "fake_b", GOOD)
    with pytest.raises(REG.RegistryError, match="harness 名重复"):
        HC.discover_launch_specs(tmp_path)


@pytest.mark.parametrize("mutate, why", [
    (lambda s: s.pop("image"), "缺键"),
    (lambda s: s.update(extra=1), "多键"),
    (lambda s: s.update(paradigm="P9"), "范式不在轴上"),
    (lambda s: s.update(command="sh -c echo"), "command 不是数组"),
    (lambda s: s.update(command=[]), "command 空"),
    (lambda s: s.update(command=["sh", 3]), "command 里不是字符串"),
    (lambda s: s.update(harness="  "), "harness 空"),
    (lambda s: s.update(env_required="OPENAI_BASE_URL"), "env_required 不是数组"),
    (lambda s: s.update(notes=None), "notes 不是字符串"),
])
def test_bad_launch_json_is_red(tmp_path, mutate, why):
    spec = dict(GOOD)
    mutate(spec)
    _write(tmp_path, "harnesses", "fake", spec)
    with pytest.raises(REG.RegistryError):
        HC.discover_launch_specs(tmp_path)


def test_unparsable_launch_json_is_red_not_skipped(tmp_path):
    d = tmp_path / "harnesses" / "fake"
    d.mkdir(parents=True)
    (d / "launch.json").write_text("{ not json", encoding="utf-8")
    with pytest.raises(REG.RegistryError, match="读不出来"):
        HC.discover_launch_specs(tmp_path)


# ---------------------------------------------------------------------------
# ③ config.yaml 的合并
# ---------------------------------------------------------------------------
CFG = ("config_id: cfg-fake-deepseek\n"
       "harness: Fake Harness\n"
       "model: deepseek-chat\n"
       "base_url: https://api.deepseek.com\n"
       "api_key_env: DEEPSEEK_API_KEY\n"
       "note: 夹具\n"
       "enabled: true\n")


def _cfg(root: Path, tree: str, hid: str, text: str) -> Path:
    d = root / tree / hid
    d.mkdir(parents=True, exist_ok=True)
    p = d / "config.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_enabled_config_is_merged_and_disabled_one_is_only_registered(tmp_path):
    _cfg(tmp_path, "integrations", "fake", CFG)
    _cfg(tmp_path, "integrations", "later",
         CFG.replace("cfg-fake-deepseek", "cfg-later-deepseek")
            .replace("Fake Harness", "Later Harness")
            .replace("enabled: true", "enabled: false"))
    enabled, pending = REG.load_data_configs(tmp_path)
    assert [c.config_id for c in enabled] == ["cfg-fake-deepseek"]
    assert [c.config_id for c in pending] == ["cfg-later-deepseek"]
    merged, pend2 = REG.merge_configs(repo_root=tmp_path)
    assert len(merged) == len(REG.BUILTIN_CONFIGS) + 1
    assert merged[:len(REG.BUILTIN_CONFIGS)] == REG.BUILTIN_CONFIGS
    assert pend2 == pending


def test_data_config_colliding_with_a_builtin_id_is_red(tmp_path):
    _cfg(tmp_path, "integrations", "fake",
         CFG.replace("cfg-fake-deepseek", "cfg-codex-deepseek"))
    with pytest.raises(REG.RegistryError, match="与内置的重名"):
        REG.merge_configs(repo_root=tmp_path)


@pytest.mark.parametrize("text, why", [
    (CFG.replace("https://api.deepseek.com", "http://api.deepseek.com"), "不是 https"),
    (CFG.replace("https://api.deepseek.com", "https://finnhub.io"), "指向行情源"),
    (CFG.replace("DEEPSEEK_API_KEY", "DEEPSEEK_TOKEN"), "环境变量名后缀"),
    (CFG.replace("enabled: true", "enabled: yes-please"), "enabled 不是布尔"),
    (CFG.replace("model: deepseek-chat\n", ""), "缺键"),
    (CFG + "extra: 1\n", "多键"),
    (CFG.replace("config_id: cfg-fake-deepseek", "config_id: ''"), "空字符串"),
])
def test_bad_config_yaml_is_red(tmp_path, text, why):
    _cfg(tmp_path, "harnesses", "fake", text)
    with pytest.raises(REG.RegistryError):
        REG.load_data_configs(tmp_path)


def test_disabled_config_still_has_to_pass_the_per_config_checks(tmp_path):
    """翻开关的那一刻没有人会重新审 base_url —— 所以现在就审。"""
    _cfg(tmp_path, "harnesses", "fake",
         CFG.replace("enabled: true", "enabled: false")
            .replace("https://api.deepseek.com", "https://news.google.com"))
    with pytest.raises(REG.RegistryError, match="行情/新闻源"):
        REG.load_data_configs(tmp_path)


# ---------------------------------------------------------------------------
# ④ 仓库现状：两份模板是 enabled:false，且没有把内置那三条挤掉
# ---------------------------------------------------------------------------
def test_repo_templates_are_disabled_and_builtins_untouched():
    n = len(REG.BUILTIN_CONFIGS)
    assert REG.CONFIGS[:n] == REG.BUILTIN_CONFIGS, "内置三条必须原样在最前面"
    pending_ids = {c.config_id for c in REG.PENDING_CONFIGS}
    assert {"cfg-codex-deepseek", "cfg-openhands-deepseek"} <= pending_ids, \
        "两份模板必须是 enabled: false —— 内置配置已覆盖它们"
    REG.assert_registry_sane()


def test_by_id_tells_you_when_a_config_is_registered_but_disabled(monkeypatch):
    c = REG.Config("cfg-pending-probe", "Pending Harness", "deepseek-chat",
                   REG.DEEPSEEK, "DEEPSEEK_API_KEY", "夹具")
    monkeypatch.setattr(REG, "PENDING_CONFIGS", (c,))
    with pytest.raises(REG.RegistryError, match="enabled: false"):
        REG.by_id("cfg-pending-probe")
    with pytest.raises(REG.RegistryError, match="未知 config_id"):
        REG.by_id("cfg-does-not-exist-at-all")


def test_flipping_a_template_to_enabled_would_be_red(tmp_path):
    """模板翻成 true 就与内置重名 —— 这正是把它们留成 false 的意义。"""
    src = (REPO / "harnesses" / "codex" / "config.yaml").read_text(encoding="utf-8")
    _cfg(tmp_path, "harnesses", "codex", src.replace("enabled: false", "enabled: true"))
    with pytest.raises(REG.RegistryError, match="与内置的重名"):
        REG.merge_configs(repo_root=tmp_path)


# ---------------------------------------------------------------------------
# ⑤ Dockerfile 抄回来了，而且抄的是那一份
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("hid, image, pin", [
    ("codex", "gb-cx-u:r1", "@openai/codex@0.153.2"),
    ("openhands", "gb-oh-u:r1", "openhands-ai==1.11.0"),
])
def test_dockerfile_copied_back_with_provenance(hid, image, pin):
    p = REPO / "harnesses" / hid / "Dockerfile"
    text = p.read_text(encoding="utf-8")
    assert "/data/genebench_runner/build/" in text, "顶部要写清来源"
    assert image in text and "sha256:" in text, "顶部要写清镜像名与 digest"
    assert "FROM gb-base:bookworm-r1" in text
    assert pin in text
    spec = json.loads((REPO / "harnesses" / hid / "launch.json").read_text(encoding="utf-8"))
    assert spec["image"] == image
