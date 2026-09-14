# -*- coding: utf-8 -*-
"""卡 2.6：接入示例 `integrations/tradingagents/` 的判据。

四族，每族都要能被**定向破坏跑红**（恒绿的门证明不了任何事）：

1. `pin.json` 齐全 + 跨字段判据（钉的是字节，不是名字），且与
   `runner/c42/upstream_pins.py` 里那条 Pin **逐字一致** —— 两处各自都真、
   放在一起是假话，正是 N-51 那次的形态。
2. `launch.json` / `config.yaml` 的键集与硬约束（六键 / 七键、`$$`、
   base_url 是 https、api_key_env 结尾、host 不在行情源表里）。
3. `Dockerfile` 从统一基座起，且垫片与上游都在**构建期**装完。
4. 接线层的替换点**在被替换的模块里确实存在**：装得起上游就对真模块查，
   装不起就用一份形状相同的替身跑 `install()` / `assert_only_gateway_vendor()`
   的正反两例 —— 后者证明的是「这道门会红」，前者证明的是「上游还长这样」。
"""
from __future__ import annotations

import datetime as _dt
import importlib
import json
import re
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
HERE = REPO / "integrations" / "tradingagents"
PKG_SRC = REPO / "integrations" / "genebench_client" / "src"

for _p in (str(REPO), str(PKG_SRC)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

GLUE = importlib.import_module("integrations.tradingagents.glue.gateway_vendors")
RUN = importlib.import_module("integrations.tradingagents.glue.run")

_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")

#: 上游 v0.4.0 的 vendor 表键集（commit 2448d0a1 实测，11 个）。
#: 上游加一个方法而接线层没跟上，那个方法就留着**原生实现**——
#: 一条未声明的数据源，网关日志上完全看不见。
UPSTREAM_METHODS = frozenset({
    "get_stock_data", "get_indicators",
    "get_fundamentals", "get_balance_sheet", "get_cashflow", "get_income_statement",
    "get_news", "get_global_news", "get_insider_transactions",
    "get_macro_indicators", "get_prediction_markets",
})


@pytest.fixture(scope="module")
def pin() -> dict:
    return json.loads((HERE / "pin.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def launch() -> dict:
    return json.loads((HERE / "launch.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def config() -> dict:
    return yaml.safe_load((HERE / "config.yaml").read_text(encoding="utf-8"))


# ------------------------------------------------------------------ 1. pin.json


def test_pin_has_every_field_d21_asks_for(pin):
    for key in ("paper_url", "repo_url", "commit", "license",
                "runnable_check", "runnable_check_result", "retrieved_at"):
        assert pin.get(key), f"pin.json 缺 {key} —— 半年后没人能复现这次接入的是哪一版"


def test_pin_paper_and_repo_are_https_urls(pin):
    assert pin["paper_url"].startswith("https://")
    assert pin["repo_url"].startswith("https://github.com/")


def test_pin_pins_bytes_not_names(pin):
    """`commit` 与 `source_sha256` 至少有一个，而且形态要对。"""
    commit, sha = pin.get("commit") or "", pin.get("source_sha256") or ""
    assert commit or sha, "commit / source_sha256 都没有 —— 什么都没钉住"
    if commit:
        assert _HEX40.fullmatch(commit), f"commit 不是 40 位 hex：{commit!r}"
    if sha:
        assert _HEX64.fullmatch(sha), f"source_sha256 不是 64 位 hex：{sha!r}"


def test_pin_cross_field_pypi_repo_must_be_the_repo(pin):
    """**跨字段判据**：从 PyPI 装的，PyPI 声明的仓库必须就是 `repo_url`。

    这一条正是 N-51 抓到的形态：PyPI 的 `tradingagents` 属于 Mai0313（3 stars），
    与文献里的 TauricResearch 同名而不同项目。本接入**不从 PyPI 装**，
    所以 `dist` 为空 —— 但**空着不解释就退化成「有这个仓库就行」**，
    所以留空必须写明理由。
    """
    def norm(u: str) -> str:
        return u.rstrip("/").lower().removesuffix(".git")

    if pin.get("dist"):
        assert pin.get("dist_repo_url"), "从 PyPI 装却没给 dist_repo_url —— 版本号不等于源码"
        assert norm(pin["dist_repo_url"]).endswith(norm(pin["repo_url"]).split("github.com/")[-1]), (
            f"PyPI 声明的仓库 {pin['dist_repo_url']!r} 与 repo_url {pin['repo_url']!r} 不是一个项目")
    else:
        assert pin.get("dist_note"), "dist 留空必须写明理由（不写就等于没钉）"


def test_pin_retrieved_at_carries_a_timezone(pin):
    ts = _dt.datetime.fromisoformat(pin["retrieved_at"])
    assert ts.tzinfo is not None, "retrieved_at 必须带时区 —— 裸时刻会静默偏 8 小时"


def test_pin_agrees_with_upstream_pins_verbatim(pin):
    """与 `runner/c42/upstream_pins.py` 那条 Pin 逐字一致。

    两处各自都真、放在一起是假话 —— 这条门就是为了让「漂」当场红。
    """
    up = importlib.import_module("runner.c42.upstream_pins")
    p = up.PINS["tradingagents"]
    assert pin["commit"] == p.commit
    assert pin["source_sha256"] == p.dist_sha256
    assert pin["repo_url"].rstrip("/") == p.repo.rstrip("/")


# ------------------------------------------------------------------ 2. launch / config


def test_launch_json_has_exactly_the_six_keys(launch):
    assert set(launch) == {"harness", "paradigm", "image", "command",
                           "env_required", "notes"}, sorted(launch)


def test_launch_paradigm_is_p2_and_harness_is_the_directory_name(launch):
    assert launch["paradigm"] == "P2"
    assert launch["harness"] == HERE.name


def test_launch_command_has_no_bare_dollar(launch):
    """N-101：命令经一层 compose 变量展开，写一个 `$` 的结果是变量被提前吃掉。

    现场表现是「命令看起来对、跑起来是空的」—— 所以判据是**每个 `$` 都成对**。
    """
    for part in launch["command"]:
        for m in re.finditer(r"\$+", part):
            assert len(m.group(0)) % 2 == 0, f"裸 $：{part!r} 处 {m.group(0)!r}"


def test_launch_env_required_covers_gateway_and_the_sidecar(launch):
    assert "GENEBENCH_GATEWAY" in launch["env_required"]
    assert any(v in launch["env_required"] for v in
               ("OPENAI_BASE_URL", "OPENAI_API_BASE", "LLM_BASE_URL")), \
        "base URL 只许从 env_required 列的变量取，写死主机名就绕过了边车"


def test_launch_image_matches_the_dockerfile_tag_in_readme():
    readme = (HERE / "README.md").read_text(encoding="utf-8")
    launch = json.loads((HERE / "launch.json").read_text(encoding="utf-8"))
    assert launch["image"] in readme, "README 里没有 launch.json 用的镜像名 —— 复现不了"


def test_config_yaml_has_exactly_the_seven_keys(config):
    assert set(config) == {"config_id", "harness", "model", "base_url",
                           "api_key_env", "note", "enabled"}, sorted(config)


def test_config_passes_the_three_gates(config):
    from runner import registry as REG
    assert config["base_url"].startswith("https://"), "base_url 必须 https"
    assert config["api_key_env"].endswith("_API_KEY"), "变量名必须以 _API_KEY 结尾"
    hosts = {h.lower() for h in getattr(REG, "MARKET_DATA_HOSTS", ())}
    host = config["base_url"].split("://", 1)[1].split("/", 1)[0].lower()
    assert host not in hosts, \
        f"{host} 在行情/新闻源域名表里 —— 那等于让被测系统绕过数据面（红线 5）"


def test_config_is_enabled_and_lands_in_the_main_table(config):
    from runner import registry as REG
    assert config["enabled"] is True
    ids = [c.config_id for c in REG.CONFIGS]
    assert config["config_id"] in ids, "enabled 却没进 CONFIGS —— 真跑时 by_id 找不到它"
    assert len(ids) == len(set(ids)), f"config_id 重名：{ids}"
    mine = next(c for c in REG.CONFIGS if c.config_id == config["config_id"])
    assert mine.model == config["model"]


def test_launch_spec_is_discoverable_under_the_declared_harness_name(launch):
    from runner.c42 import harness_commands as HC
    specs = HC.discover_launch_specs()
    assert launch["harness"] in specs, "两处发现入口没找到它 —— f02 上 by_id 会找不到"
    assert specs[launch["harness"]]["image"] == launch["image"]


# ------------------------------------------------------------------ 3. Dockerfile


def test_dockerfile_starts_from_the_shared_base():
    lines = (HERE / "Dockerfile").read_text(encoding="utf-8").splitlines()
    froms = [ln.split(None, 1)[1].strip() for ln in lines
             if ln.strip().upper().startswith("FROM ")]
    assert froms, "Dockerfile 里没有 FROM"
    assert froms[0] == "gb-base:bookworm-r1", \
        f"第一条 FROM 是 {froms[0]!r} —— 统一基座是 gb-base:bookworm-r1（docker.io 被墙，不要 pull 新基础镜像）"


def test_dockerfile_verifies_the_source_tarball_bytes():
    text = (HERE / "Dockerfile").read_text(encoding="utf-8")
    pin = json.loads((HERE / "pin.json").read_text(encoding="utf-8"))
    assert "sha256sum -c" in text, "源码压缩包没有核字节 —— 版本号不是钉"
    assert pin["source_sha256"] in text, "Dockerfile 里的摘要与 pin.json 不是同一个"
    assert pin["commit"] in text


def test_dockerfile_installs_the_shim_without_reaching_an_index():
    text = (HERE / "Dockerfile").read_text(encoding="utf-8")
    line = next(ln for ln in text.splitlines()
                if "pip install" in ln and "/opt/genebench_client" in ln)
    assert "--no-index" in line, \
        "垫片不在任何 index 上；去公网找它只会拿到别的东西（或什么都拿不到）"


def test_dockerfile_does_not_clone_or_curl_at_build_time():
    """GitHub 在 f02 的构建网里不可达（本卡实测 codeload 超时）。

    正路是本地下载 → 两跳 scp → `COPY` 进去。写 `git clone` 会让构建
    在一个**别人复现时可能可达**的地址上摇摆 —— 那种不确定性比失败更贵。
    """
    text = (HERE / "Dockerfile").read_text(encoding="utf-8")
    body = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))
    assert "git clone" not in body
    assert "codeload" not in body and "curl " not in body


def test_home_is_writable_and_not_under_task():
    """`/task` 就是 run dir 的 `work/` 本身：往它下面落东西会破 P8 文件集封闭。"""
    text = (HERE / "Dockerfile").read_text(encoding="utf-8")
    for m in re.finditer(r"^\s*(?:ENV\s+)?(HOME|XDG_CACHE_HOME|TRADINGAGENTS_\w+)=(\S+)",
                         text, re.M):
        assert not m.group(2).startswith("/task"), \
            f"{m.group(1)} 指到了 {m.group(2)} —— 不要指到 /task 下"
    cmd = " ".join(json.loads((HERE / "launch.json").read_text(encoding="utf-8"))["command"])
    for m in re.finditer(r"(HOME|XDG_CACHE_HOME)=(\S+)", cmd):
        assert not m.group(2).startswith("/task"), f"launch.json 里 {m.group(0)}"


# ------------------------------------------------------------------ 4. 接线层


def test_glue_covers_every_upstream_method_exactly_once():
    served, nosrc = set(GLUE.SERVED), set(GLUE.NO_SOURCE)
    assert served & nosrc == set(), f"同一个方法两处都登记了：{sorted(served & nosrc)}"
    assert served | nosrc == UPSTREAM_METHODS, (
        f"漏了 {sorted(UPSTREAM_METHODS - (served | nosrc))}；"
        f"多了 {sorted((served | nosrc) - UPSTREAM_METHODS)}")


def test_no_source_kinds_are_real_shim_categories():
    """粗分类必须在垫片的 `KINDS` 里 —— 写别的会被静默归到 `other`，聚合就失真。"""
    from genebench_client import nodata as nd
    for method, (_what, kind) in GLUE.NO_SOURCE.items():
        assert kind in nd.KINDS, f"{method} 的分类 {kind!r} 不在 nodata.KINDS 里"


def _code_strings(path: Path) -> list[str]:
    """源文件里**除文档字符串以外**的全部字符串字面量。

    直接 grep 源码会把「解释为什么要替换 yfinance」的那句话也算成命中 ——
    那是一条恒红的门（说明文字里不能提被禁的名字），与它要防的事无关。
    判据是**代码里有没有这个主机名**，所以只看字面量，不看散文。
    """
    import ast
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None) or []
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                docstrings.add(id(body[0].value))
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings]


def test_glue_has_no_hardcoded_market_data_host():
    """接线层的**代码**里不许出现任何行情/新闻源主机名。

    出向白名单里只有模型 API，写死了也连不上 —— 但拦在这里比拦在真跑时便宜。
    """
    from runner import registry as REG
    hosts = {h.lower() for h in getattr(REG, "MARKET_DATA_HOSTS", ())}
    assert hosts, "MARKET_DATA_HOSTS 是空的 —— 这条门会恒绿，先去查 registry"
    for path in sorted((HERE / "glue").glob("*.py")):
        for lit in _code_strings(path):
            for h in hosts:
                assert h not in lit.lower(), f"{path.name} 的字面量里有行情源主机 {h}：{lit[:80]!r}"


def test_that_host_gate_is_not_vacuous(tmp_path):
    """**非空证明**：真把一个行情源主机写进字面量，上面那条必须红。"""
    from runner import registry as REG
    host = sorted(REG.MARKET_DATA_HOSTS)[0]
    probe = tmp_path / "probe.py"
    probe.write_text(f'"""说明里提到 {host} 不该算命中。"""\nURL = "https://{host}/x"\n',
                     encoding="utf-8")
    lits = _code_strings(probe)
    assert any(host in x for x in lits), "字面量提取器漏了代码里的主机名"
    assert not any(host in x for x in lits if x.startswith("说明里")), \
        "文档字符串被算进去了 —— 那条门会因为注释而恒红"


class _FakeInterface:
    """形状与上游 `dataflows/interface` 相同的替身（只含被替换的三样）。"""

    def __init__(self):
        self.VENDOR_METHODS = {m: {"yfinance": _native, "alpha_vantage": _native}
                               for m in UPSTREAM_METHODS}
        self.VENDOR_LIST = ["yfinance", "fred", "polymarket", "alpha_vantage"]
        self.TOOLS_CATEGORIES = {"core_stock_apis": {}, "technical_indicators": {},
                                 "fundamental_data": {}, "news_data": {},
                                 "macro_data": {}, "prediction_markets": {}}


def _native(*_a, **_kw):
    return "原生实现"


def test_install_fails_closed_when_the_second_seam_is_unreachable():
    """`install()` 装**两条缝**：第二条一个替换点都找不到时它必须抛。

    fail-closed 是刻意的 —— 「vendor 表换好了、load_ohlcv 那条没换」正是
    第一次真跑的状态：表面上一切就绪，实际有一条活着的原生取数路径。
    """
    with pytest.raises(GLUE.ReplacementError):
        GLUE.install(_FakeInterface(), {}, modules={})


def test_the_door_is_red_before_the_replacement():
    """**非空证明**：没换之前 `assert_only_gateway_vendor` 必须报。

    一道在未替换时也放行的门，证明不了「替换成功了」——
    N-52 那次就是门装在了错的层，恒绿。
    """
    fake = _FakeInterface()
    with pytest.raises(GLUE.ReplacementError):
        GLUE.assert_only_gateway_vendor(fake)


def test_install_replaces_the_whole_table_and_the_door_turns_green():
    fake = _FakeInterface()
    cfg: dict = {}
    mods = _fake_modules()
    before = GLUE.install(fake, cfg, modules=mods)
    GLUE.assert_market_data_seam_closed(mods)      # install() 两条缝都要装
    assert set(before) == UPSTREAM_METHODS
    GLUE.assert_only_gateway_vendor(fake)                      # 不抛即通过
    assert fake.VENDOR_LIST == [GLUE.VENDOR]
    assert set(cfg["data_vendors"]) == set(fake.TOOLS_CATEGORIES)
    assert set(cfg["data_vendors"].values()) == {GLUE.VENDOR}
    assert cfg["tool_vendors"] == {}
    for method, table in fake.VENDOR_METHODS.items():
        assert list(table) == [GLUE.VENDOR], method
        assert table[GLUE.VENDOR].__module__ == GLUE.__name__, method


def test_one_native_survivor_is_enough_to_turn_the_door_red():
    """留一个原生实现在表里就是一条未声明的数据源 —— 必须红。"""
    fake = _FakeInterface()
    GLUE.install(fake, {}, modules=_fake_modules())
    fake.VENDOR_METHODS["get_news"]["yfinance"] = _native
    with pytest.raises(GLUE.ReplacementError) as e:
        GLUE.assert_only_gateway_vendor(fake)
    assert "get_news" in str(e.value)


def test_an_unknown_upstream_method_is_refused_not_ignored():
    """上游多一个方法 → 当场抛，而不是静默留着原生实现。"""
    with pytest.raises(GLUE.ReplacementError):
        GLUE.build_vendor_table(sorted(UPSTREAM_METHODS) + ["get_something_new"])


@pytest.mark.parametrize("attr", [
    "tradingagents.dataflows.interface:VENDOR_METHODS",
    "tradingagents.dataflows.interface:TOOLS_CATEGORIES",
    "tradingagents.dataflows.interface:VENDOR_LIST",
    "tradingagents.dataflows.interface:route_to_vendor",
    "tradingagents.dataflows.config:set_config",
    "tradingagents.default_config:DEFAULT_CONFIG",
    "tradingagents.graph.trading_graph:TradingAgentsGraph",
])
def test_the_replacement_points_exist_in_the_upstream_module(attr):
    """替换点在**被替换的模块里**确实存在。

    上游只装在 f02 的镜像里（f01 没有容器运行时，也没装 TradingAgents），
    所以这里装不起来就 skip 并说明 —— 但 skip 的**理由必须是 import 失败**，
    不是「懒得查」。真装得起来时（在容器里跑本文件）它就是一道真门。
    """
    mod_name, _, name = attr.partition(":")
    try:
        mod = importlib.import_module(mod_name)
    except ImportError as e:
        pytest.skip(f"上游 TradingAgents 没装在这台机器上（只在 f02 的 "
                    f"gb-tradingagents-u:r1 镜像里）：{e}")
    assert hasattr(mod, name), f"{attr} 不在了 —— 上游改了形状，接线层要跟着改"


def test_the_upstream_table_matches_what_the_glue_expects():
    try:
        IF = importlib.import_module("tradingagents.dataflows.interface")
    except ImportError as e:
        pytest.skip(f"上游没装在这台机器上：{e}")
    assert set(IF.VENDOR_METHODS) == UPSTREAM_METHODS, \
        "上游的 vendor 表变了 —— 先核 pin.json 的 commit，再改 UPSTREAM_METHODS"


# ------------------------------------------------------------------ 4a. 第二条缝


class _FakeStockstats:
    """替身：形状与 `dataflows/stockstats_utils` 相同（有 `load_ohlcv` 与 `yf`）。"""

    def __init__(self):
        self.load_ohlcv = _native
        self.yf = object()                       # 假装是真的 yfinance 模块


class _FakeValidator:
    """替身：`from … import load_ohlcv` 的那种模块 —— 引用在 import 期就捕获了。"""

    def __init__(self):
        self.load_ohlcv = _native


def _fake_modules() -> dict:
    return {"tradingagents.dataflows.stockstats_utils": _FakeStockstats(),
            "tradingagents.dataflows.market_data_validator": _FakeValidator(),
            "tradingagents.dataflows.y_finance": _FakeStockstats()}


def test_the_second_seam_door_is_red_before_the_replacement():
    """**非空证明**：`load_ohlcv` 没换之前必须报。

    这条缝是真跑抓出来的：`get_verified_market_snapshot` 是直接绑给行情分析师的
    `@tool`，**不经 `route_to_vendor`** —— 只换 vendor 表的话它照样走 yfinance。
    """
    mods = _fake_modules()
    with pytest.raises(GLUE.ReplacementError):
        GLUE.assert_market_data_seam_closed(mods)


def test_installing_the_second_seam_rebinds_every_holder():
    mods = _fake_modules()
    touched = GLUE.install_market_data_seam(mods)
    GLUE.assert_market_data_seam_closed(mods)               # 不抛即通过
    assert any("market_data_validator:load_ohlcv" in t for t in touched), touched
    for name, mod in mods.items():
        assert mod.load_ohlcv is GLUE.load_ohlcv_via_gateway, name


def test_one_unreplaced_holder_turns_the_second_seam_red():
    mods = _fake_modules()
    GLUE.install_market_data_seam(mods)
    mods["tradingagents.dataflows.market_data_validator"].load_ohlcv = _native
    with pytest.raises(GLUE.ReplacementError) as e:
        GLUE.assert_market_data_seam_closed(mods)
    assert "market_data_validator" in str(e.value)


def test_the_yfinance_trap_raises_on_any_attribute():
    """顶替各模块手里的 `yf`：任何属性访问都抛，把「我们没想到的路」从静默变响亮。"""
    mods = _fake_modules()
    GLUE.install_market_data_seam(mods)
    trap = mods["tradingagents.dataflows.stockstats_utils"].yf
    for name in ("download", "Ticker", "Search"):
        with pytest.raises(GLUE.ReplacementError):
            getattr(trap, name)


def test_the_seam_installer_refuses_a_layout_it_does_not_recognise():
    """一个替换点都没找到就抛 —— 「什么都没换」不许当成「换完了」。"""
    with pytest.raises(GLUE.ReplacementError):
        GLUE.install_market_data_seam({"tradingagents.dataflows.stockstats_utils": object()})


# ------------------------------------------------------------------ 4b. 入口的题面解析

#: **两臂的题面表达形式不同** —— 这是两臂唯一允许的两项差异之一。
#: 下面两份都是真跑 bundle 里那两份的逐字节选（含那行会坑人的端点清单）。
_STRICT = """按下列声明完成任务。
任务（S5）：（自由发挥）用 /task/inputs/ 下的多个输入因子面板构造分数信号。
除题面列出的输入材料外，数据只能经网关获取：http://gateway:18080
可用端点：/bars /adj /calendar /limits /universe /tradability
as_of=2026-07-31
window=2026-01-05 到 2026-07-31
universe=csi300
本次任务的口径（逐项）：
- value_semantics=score（信号值是分数，接口值 score）
- signal_frequency=daily（信号按日生成，接口值 daily）
- direction=higher_is_long（信号越大越看多，接口值 higher_is_long）
- universe_ref=csi300@2026-07-31（按 PIT 宇宙，接口值 csi300@2026-07-31）
- missing_policy=keep_null（无观点的格子保持为空，接口值 keep_null）
- input_factors=[gtja_191.001, gtja_191.002]（接口值 [gtja_191.001, gtja_191.002]）
产出路径：/task/artifact.json
"""

_OPEN = """按下列声明完成任务。
用 /task/inputs/ 下的多个输入因子面板构造你认为预测力最强的分数信号。
除题面列出的输入材料外，数据只能经本环境的数据网关获取，网关在 http://gateway:18080
网关提供这些端点：/bars /adj /calendar /limits /universe /tradability
本次任务的 as_of 是 2026-07-31
计算窗口（window）是 2026-01-05 到 2026-07-31
标的范围（universe）是 csi300
本次任务的口径（逐项）：
- 信号值是分数（字段 value_semantics，接口值 score）
- 信号按日生成（字段 signal_frequency，接口值 daily）
- 信号越大越看多（字段 direction，接口值 higher_is_long）
- 标的范围是截至 2026-07-31 的沪深300成分股，按 PIT 宇宙（字段 universe_ref，接口值 csi300@2026-07-31）
- 无观点的格子保持为空，不填 0（字段 missing_policy，接口值 keep_null）
- 输入因子是 gtja_191.001 与 gtja_191.002（字段 input_factors，接口值 [gtja_191.001, gtja_191.002]）
把结果写到 /task/artifact.json
"""

_INSTRUCTION = _STRICT


@pytest.fixture(params=["strict", "open"])
def instruction(request) -> str:
    return _STRICT if request.param == "strict" else _OPEN


def test_run_reads_the_fixed_slots_on_both_arms(instruction):
    """两臂都要读得出来。

    第一次真跑时 **open 臂当场退出**（`INSTRUCTION.md 里没有槽位 'as_of'`）——
    解析只认了 strict 的 `key=value`，而 open 写的是「本次任务的 as_of 是 …」。
    两臂结果不可比，那比跑不出来更糟。
    """
    assert RUN.slot(instruction, "as_of", pattern=RUN._DATE) == "2026-07-31"
    assert RUN.slot(instruction, "universe") == "csi300"
    assert RUN.window(instruction) == ("2026-01-05", "2026-07-31")


def test_the_endpoint_list_does_not_poison_the_universe_slot(instruction):
    """题面里有一行 `可用端点：… /universe /tradability`。

    没有「键名前不许是 `/`」这条否定后顾，`universe` 会命中那一行、再越过 ` /`
    取到 **tradability** —— 一个**长得像成功**的错值（实测抓到）。
    错的 universe 会让整次取数换一个标的池，而产物上完全看不出来。
    """
    assert "/universe /tradability" in instruction
    assert RUN.slot(instruction, "universe") == "csi300"


def test_run_refuses_to_guess_a_missing_slot():
    """槽位缺了就退出。**猜一个 as_of 会让越界变成合法请求**，而产物上看不出来。"""
    with pytest.raises(SystemExit):
        RUN.slot("题面里什么都没有", "as_of")
    with pytest.raises(SystemExit):
        RUN.window("window=2026-01-05 到")


def test_run_transcribes_the_declarations_verbatim(instruction):
    """两臂的声明行写法不同，读出来的六项必须**逐字相同** —— 那正是两臂可比的前提。"""
    from genebench_client import emit
    fields = emit.declaration_fields("S5")
    got = RUN.declarations(instruction, fields)
    assert set(got) == set(fields), "声明键集必须精确等于契约要求的那一套"
    assert got["value_semantics"] == "score"
    assert got["signal_frequency"] == "daily"
    assert got["direction"] == "higher_is_long"
    assert got["universe_ref"] == "csi300@2026-07-31"
    assert got["missing_policy"] == "keep_null"
    assert got["input_factors"] == ["gtja_191.001", "gtja_191.002"]


def test_a_slot_the_task_did_not_give_is_marked_unresolved_not_filled():
    """**缺失 ≠ 标记**：题面没给的那一项要写显式 `"unresolved"`，不是挑个默认值。"""
    trimmed = "\n".join(ln for ln in _STRICT.splitlines()
                        if not ln.startswith("- direction="))
    from genebench_client import emit
    got = RUN.declarations(trimmed, emit.declaration_fields("S5"))
    assert got["direction"] == "unresolved"


def test_review_becomes_no_opinion_not_zero():
    """上游说「这次的决定没有可解析的评级」时是 `REVIEW` —— 那是无观点，不是 Hold。

    题面写着「无观点的格子不得补 0」，而 `Hold`（0.0）与「没解析出来」含义相反。
    """
    assert RUN.RATING_SCORE.get("review") is None
    assert RUN.RATING_SCORE["hold"] == 0.0
    assert set(RUN.RATING_SCORE) == {"buy", "overweight", "hold", "underweight", "sell"}
    vals = [RUN.RATING_SCORE[k] for k in ("sell", "underweight", "hold", "overweight", "buy")]
    assert vals == sorted(vals), "五档必须是有序映射，否则 direction=higher_is_long 就是假的"


def test_the_artifact_that_the_glue_would_emit_passes_the_reference_validator():
    """把入口那几行拼产物的代码**真跑一遍**，交给参考校验器判。

    不 mock emit：这条要证明的正是「接线层交出来的东西过得了那把尺子」。
    """
    from genebench_client import emit
    decls = RUN.declarations(_INSTRUCTION, emit.declaration_fields("S5"))
    rows = [{"date": "2026-07-31", "symbol": "600000.SH", "value": RUN.RATING_SCORE["buy"]},
            {"date": "2026-07-31", "symbol": "600036.SH", "value": None}]
    art = emit.emit_s5(signals=rows, as_of="2026-07-31", declarations=decls,
                       task_id="s5-eco-01", config_id="cfg-tradingagents-deepseek",
                       arm="strict")
    assert art["payload"]["coverage"] == {"n_valued": 1, "n_null": 1, "n_flat": 0}
    from reference import artifact_schema as AS
    verdict = AS.validate(json.loads(json.dumps(art)))
    assert not verdict.malformed, f"接线层交出来的产物过不了参考校验器：{verdict.codes}"


def test_the_same_validator_does_flag_a_deliberately_broken_artifact():
    """**非空证明**：同一把尺子对一份坏产物必须报 —— 否则上一条是恒绿的。"""
    from genebench_client import emit
    from reference import artifact_schema as AS
    decls = RUN.declarations(_INSTRUCTION, emit.declaration_fields("S5"))
    art = emit.emit_s5(signals=[{"date": "2026-07-31", "symbol": "600000.SH", "value": 1.0}],
                       as_of="2026-07-31", declarations=decls,
                       task_id="s5-eco-01", config_id="cfg-tradingagents-deepseek",
                       arm="strict")
    broken = json.loads(json.dumps(art))
    broken["declarations"].pop("direction")                    # 少一个声明键
    verdict = AS.validate(broken)
    assert verdict.malformed, "删掉一个声明键都不报 —— 这把尺子在这条路径上是恒绿的"
