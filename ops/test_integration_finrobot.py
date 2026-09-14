# -*- coding: utf-8 -*-
"""卡 2.6：接入示例 `integrations/finrobot/` 的判据。

五族：

1. `pin.json` 齐全 + 跨字段判据（**从 PyPI 装的那一条**：PyPI 声明的仓库必须就是
   `repo_url`；版本号在 `dist` / `version_declared` / `dist_repo_url` /
   `source_tarball` 四处必须是同一个）。
2. `launch.json` / `config.yaml` 的键集与硬约束（六键 / 七键、命令里没有裸 `$`、
   base_url 是 https、`api_key_env` 结尾、host 不在行情源表里）。
3. `Dockerfile` 从统一基座起、上游按**字节摘要**装、接线层显式放开读权限。
4. 接线层的替换点**在被替换的模块里确实存在**。f01 上装不起 FinRobot
   （autogen/chromadb 那一串不在这台机器上），所以这里对着 `upstream_api.json`
   这份**与 `pin.json` 同一个 sha256 绑定**的快照核；活体那一遍在镜像里
   （`smoke_in_container.py`，每次真跑前 `run.py` 也跑一次）。
   另外用一份形状相同的**替身模块**跑 `install()` / `patch_library()` /
   `assert_no_native_datasource()` 的正反两例 —— 证明那道门会红。
5. `run.py` 的题面解析：`as_of` / `window` / 声明三项，**两臂的真题面各跑一遍**
   （两臂表达形式不同是设计，判据不能挂在标点上），外加 ledger → `fetches`
   的三条转换规则。
"""
from __future__ import annotations

import importlib
import json
import re
import sys
import types
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
HERE = REPO / "integrations" / "finrobot"
PKG_SRC = REPO / "integrations" / "genebench_client" / "src"

for _p in (str(REPO), str(PKG_SRC)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

GLUE = importlib.import_module("integrations.finrobot.glue.gateway_sources")
RUN = importlib.import_module("integrations.finrobot.glue.run")

_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")

#: 两臂的真题面（`ops/export_bundle.py s1-cor-01` 出的那一份，逐字）。
#: 两臂**只允许**差在题面的表达形式与协议工件的有无，所以解析器必须两臂都吃得下。
INSTRUCTION_STRICT = """按下列声明完成任务。
任务（S1）：经数据网关取指定字段与窗口的日线，把每一次取数写成结构化记录。
要求字段：close、volume、adj_factor。
取法：close 与 volume 走 /bars 并显式传 fields
adj_factor 走 /adj。
窗口：上面给出的计算窗口
标的：声明的指数在窗口末日的成分，经 /universe 取
成分不得手写，一律经 /universe 取
除题面列出的输入材料外，数据只能经网关获取：http://gateway:18080
可用端点：/bars /adj /calendar /limits /universe /tradability
as_of=2026-07-31
window=2026-07-01 到 2026-07-31
输入材料：无；所需数据全部经网关获取
本次任务的口径（逐项）：
- calendar_id=SSE（交易日按上海证券交易所日历，接口值 SSE）
- universe=csi300（沪深300成分股，接口值 csi300）
- data_version=v1（v1 冻结快照，接口值 v1）
产出：payload.fetches 逐次列 {endpoint, params, fetched_at, status, rows}
产出路径：/task/artifact.json
"""

INSTRUCTION_OPEN = """按下列声明完成任务。
请通过数据网关，把指定标的在指定窗口内的日线取回来，并把每一次取数写成结构化记录。
要求字段：close、volume、adj_factor。
取法：close 与 volume 走 /bars 并显式传 fields
adj_factor 走 /adj。
标的：声明的指数在窗口末日的成分，经 /universe 取
除题面列出的输入材料外，数据只能经本环境的数据网关获取，网关在 http://gateway:18080
网关提供这些端点：/bars /adj /calendar /limits /universe /tradability
本次任务的 as_of 是 2026-07-31
计算窗口（window）是 2026-07-01 到 2026-07-31
本次任务的口径（逐项）：
- 交易日按上海证券交易所日历（字段 calendar_id，接口值 SSE）
- 标的范围是沪深300成分股（字段 universe，接口值 csi300）
- 数据用 v1 冻结快照（字段 data_version，接口值 v1）
把结果写到 /task/artifact.json
"""

S1_DECLARATION_FIELDS = ("calendar_id", "universe", "data_version")


@pytest.fixture(scope="module")
def pin() -> dict:
    return json.loads((HERE / "pin.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def launch() -> dict:
    return json.loads((HERE / "launch.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def config() -> dict:
    return yaml.safe_load((HERE / "config.yaml").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def upstream() -> dict:
    return json.loads((HERE / "upstream_api.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def dockerfile() -> str:
    return (HERE / "Dockerfile").read_text(encoding="utf-8")


# ------------------------------------------------------------------ 1. pin.json


def test_pin_has_every_field_d21_asks_for(pin):
    for key in ("paper_url", "repo_url", "commit", "dist", "dist_repo_url",
                "license", "runnable_check", "runnable_check_result", "retrieved_at"):
        assert pin.get(key), f"pin.json 缺 {key} —— 半年后没人能复现这次接入的是哪一版"


def test_pin_urls_are_https(pin):
    assert pin["paper_url"].startswith("https://")
    assert pin["repo_url"].startswith("https://github.com/")
    assert pin["dist_repo_url"].startswith("https://pypi.org/")


def test_pin_pins_bytes_not_names(pin):
    assert _HEX40.fullmatch(pin["commit"]), f"commit 不是 40 位 hex：{pin['commit']!r}"
    assert _HEX64.fullmatch(pin["source_sha256"]), "source_sha256 不是 64 位 hex"


def test_pypi_declared_repo_is_the_repo(pin):
    """**从 PyPI 装的跨字段判据**：PyPI 自己声明的仓库必须就是我们钉的仓库。

    同名不同项目是真出过的事（N-51：PyPI 上的 `tradingagents` 不是文献里那个）。
    这条判据不是"看着像"，是"它自己怎么说"。
    """
    assert pin["dist_declared_repo"].rstrip("/") == pin["repo_url"].rstrip("/")


def test_version_is_the_same_number_in_every_field(pin):
    """`dist` / `version_declared` / `dist_repo_url` / `source_tarball` 四处同一个版本。

    四处各写各的时，最先漂的一处不会有人发现 —— 而漂了之后每一处单看都成立。
    """
    v = pin["version_declared"]
    assert pin["dist"].endswith("==" + v), f"{pin['dist']} 与 version_declared={v} 对不上"
    assert f"/{v}/" in pin["dist_repo_url"]
    assert f"-{v}.tar.gz" in pin["source_tarball"]


def test_runnable_check_is_a_command_and_has_a_result(pin):
    assert pin["runnable_check"].startswith("python3 -c"), "runnable_check 要是一条能跑的命令"
    assert pin["runnable_check_result"].strip(), "只有命令没有结果 = 没人真跑过"


# ------------------------------------------------------- 2. launch.json / config.yaml


def test_launch_keys_are_exactly_six(launch):
    assert set(launch) == {"harness", "paradigm", "image", "command", "env_required", "notes"}


def test_launch_is_p2_and_names_our_image(launch, config):
    assert launch["paradigm"] == "P2"
    assert launch["image"] == "gb-finrobot-u:r1"
    assert launch["harness"] == config["harness"] == "finrobot"


def test_launch_command_has_no_bare_dollar(launch):
    """命令里的 `$` 一律写 `$$`（N-101）。

    写一个 `$` 的结果是变量在 compose 展开时被提前吃掉，
    而现场表现是"命令看起来对、跑起来是空的"。
    """
    cmd = " ".join(launch["command"])
    assert "$" in cmd, "这条命令本来就有变量，测试样本别退化"
    assert not re.search(r"(?<!\$)\$(?!\$)", cmd), f"命令里有裸 $：{cmd}"


def test_launch_command_does_not_write_into_task(launch):
    """`HOME` / 缓存一律指到 `/tmp`。落进 `/task` 会破 run dir 的 P8 文件集封闭。"""
    cmd = " ".join(launch["command"])
    for m in re.findall(r"(?:HOME|MPLCONFIGDIR|XDG_CACHE_HOME|GENEBENCH_FR_SCRATCH)=(\S+)", cmd):
        assert m.startswith("/tmp"), f"{m} 不在 /tmp 下"


def test_launch_env_required_covers_gateway_and_sidecar(launch):
    assert {"GENEBENCH_GATEWAY", "OPENAI_BASE_URL", "OPENAI_API_KEY"} <= set(launch["env_required"])


def test_config_keys_are_exactly_seven(config):
    assert set(config) == {"config_id", "harness", "model", "base_url",
                           "api_key_env", "note", "enabled"}


def test_config_passes_the_three_gates(config):
    from runner.registry import MARKET_DATA_HOSTS
    from urllib.parse import urlparse

    assert config["base_url"].startswith("https://")
    assert config["api_key_env"].endswith("_API_KEY")
    host = urlparse(config["base_url"]).hostname or ""
    assert host not in set(MARKET_DATA_HOSTS), \
        "行情/新闻源域名一律不得入表 —— 那等于让被测系统绕过数据面"
    assert config["enabled"] is True


def test_config_is_actually_in_the_registry(config):
    """`enabled: true` 要真的合并进主表，并且 `config_id` / `harness` 不与别人撞。"""
    from runner import registry as REG
    from runner.c42.harness_commands import discover_launch_specs

    ids = [c.config_id for c in REG.CONFIGS]
    assert config["config_id"] in ids
    assert len(ids) == len(set(ids)), f"config_id 撞了：{ids}"
    assert config["harness"] in discover_launch_specs()


# ------------------------------------------------------------------ 3. Dockerfile


def test_dockerfile_starts_from_the_shared_base(dockerfile):
    assert re.search(r"^FROM gb-base:bookworm-r1$", dockerfile, re.M)


def test_dockerfile_verifies_bytes_before_installing_upstream(dockerfile, pin):
    """版本号不是钉，摘要才是 —— 而且摘要要与 `pin.json` 里那个逐字相同。"""
    assert pin["source_sha256"] in dockerfile
    assert "sha256sum -c" in dockerfile


def test_dockerfile_does_not_fetch_upstream_at_build_time(dockerfile):
    """不在 Dockerfile 里 `git clone` / `curl` 上游：构建网可达与否不是我们能保证的事。"""
    assert "git clone" not in dockerfile
    assert not re.search(r"^\s*RUN[^\n]*\bcurl\b", dockerfile, re.M)


def test_dockerfile_installs_the_client_offline(dockerfile):
    assert "--no-index" in dockerfile, "垫片不在任何 index 上，去公网找是错的"


def test_dockerfile_opens_read_permission_on_the_glue(dockerfile):
    """`$GENEBENCH_ROOT` 全树 0600（红线 5），COPY 原样带过去，而容器以非 root 跑。"""
    assert re.search(r"chmod -R a\+rX /opt/finrobot_glue", dockerfile)


def test_market_data_libs_are_not_installed_in_the_image():
    """`yfinance` / `tushare` 有意不装 —— 装了就是一条绕过网关的路。"""
    reqs = (HERE / "requirements.gb.txt").read_text(encoding="utf-8")
    lines = [ln.strip() for ln in reqs.splitlines()
             if ln.strip() and not ln.strip().startswith("#")]
    for banned in ("yfinance", "tushare", "akshare", "pandas_datareader", "pandas-datareader"):
        assert not any(ln.split("=")[0].split("[")[0].strip().lower() == banned for ln in lines), \
            f"{banned} 进了依赖表"
    resolved = (HERE / "resolved_deps.txt").read_text(encoding="utf-8").lower()
    for banned in ("yfinance==", "tushare==", "akshare=="):
        assert banned not in resolved, f"镜像里真装了 {banned} —— 快照与意图对不上"


# ------------------------------------------- 4. 替换点在被替换的模块里确实存在


def test_upstream_snapshot_is_tied_to_the_pinned_bytes(pin, upstream):
    """快照与 `pin.json` 绑同一个 sha256。绑不上时这份快照说的就是**另一版**的事。"""
    assert upstream["source_sha256"] == pin["source_sha256"]


def test_every_replacement_point_exists_upstream(upstream):
    for cls_name, items in GLUE._NO_DATA_SPEC.items():
        known = set(upstream["classes"][cls_name])
        for meth, _kind, _why in items:
            assert meth in known, f"上游 {cls_name} 没有 {meth} —— 替换点是空的"
    for cls_name, items in GLUE._GATEWAY_SPEC.items():
        known = set(upstream["classes"][cls_name])
        for meth, _impl in items:
            assert meth in known, f"上游 {cls_name} 没有 {meth}"


def test_replacement_table_covers_every_public_method(upstream):
    """漏一个方法 = 留一条**原生**数据源，网关日志上完全看不见。"""
    covered = {f"{c}.{m}" for c, items in GLUE._NO_DATA_SPEC.items() for m, _k, _w in items}
    covered |= {f"{c}.{m}" for c, items in GLUE._GATEWAY_SPEC.items() for m, _i in items}
    upstream_all = {f"{c}.{m}" for c, ms in upstream["classes"].items() for m in ms}
    assert upstream_all - covered == set(), f"没换的上游方法：{sorted(upstream_all - covered)}"


def test_added_tools_are_not_upstream_methods(upstream):
    """新增的三个工具**不是**上游本来就有的（README §4 分开列，别读成上游自带）。"""
    upstream_names = {m for ms in upstream["classes"].values() for m in ms}
    for fn in GLUE.ADDED_TOOLS:
        assert fn.__name__ not in upstream_names, f"{fn.__name__} 其实是上游方法"


def _fake_upstream(monkeypatch, methods: dict[str, list[str]]):
    """一份形状与上游相同的替身：类 + 同名方法（方法体连不上任何东西）。"""
    ds = types.ModuleType("finrobot.data_source")
    for cls_name, ms in methods.items():
        ns = {}
        for m in ms:
            def _make(name: str):
                def _native(symbol: str = "") -> str:
                    return f"native {name}"
                _native.__name__ = name
                return _native
            ns[m] = staticmethod(_make(m))
        setattr(ds, cls_name, type(cls_name, (), ns))
    pkg = types.ModuleType("finrobot")
    pkg.data_source = ds
    monkeypatch.setitem(sys.modules, "finrobot", pkg)
    monkeypatch.setitem(sys.modules, "finrobot.data_source", ds)
    return ds


def test_install_marks_everything_and_the_guard_is_clean(monkeypatch, upstream):
    _fake_upstream(monkeypatch, upstream["classes"])
    table = GLUE.install()
    assert len(table) == sum(len(v) for v in upstream["classes"].values())
    GLUE.assert_no_native_datasource()          # 不该抛


def test_the_guard_goes_red_when_one_method_stays_native(monkeypatch, upstream):
    """定向破坏：留一个原生方法，守门必须红。**恒绿的门证明不了任何事。**"""
    ds = _fake_upstream(monkeypatch, upstream["classes"])
    GLUE.install()
    ds.YFinanceUtils.get_something_new = staticmethod(lambda: "native")
    with pytest.raises(RuntimeError, match="还是上游原件"):
        GLUE.assert_no_native_datasource()


def test_install_refuses_when_upstream_lost_a_method(monkeypatch, upstream):
    """上游哪天删/改名一个方法，接线**当场退出**，不静默少换一个。"""
    shrunk = {k: list(v) for k, v in upstream["classes"].items()}
    shrunk["FinnHubUtils"] = [m for m in shrunk["FinnHubUtils"] if m != "get_company_news"]
    _fake_upstream(monkeypatch, shrunk)
    with pytest.raises(RuntimeError, match="上游没有 FinnHubUtils.get_company_news"):
        GLUE.install()


def test_patch_library_rebinds_stale_toolkit_entries(monkeypatch, upstream):
    """`agent_library` 在模块层抓函数对象；早一步 import 就抓到原生实现。

    这一条盯的正是那次实测（镜像内自检抓到的第一处）：`install()` 之后
    `library` 里仍是原件，`patch_library()` 必须把它们重绑回来。
    """
    ds = _fake_upstream(monkeypatch, upstream["classes"])
    stale = ds.FinnHubUtils.get_company_news            # install() 之前抓的那份
    library = {"Market_Analyst": {"name": "Market_Analyst", "toolkits": [stale]}}
    GLUE.install()
    assert not getattr(library["Market_Analyst"]["toolkits"][0], GLUE.MARK, False)
    rebound = GLUE.patch_library(library)
    assert rebound == ["Market_Analyst.get_company_news"]
    assert getattr(library["Market_Analyst"]["toolkits"][0], GLUE.MARK, False)


def test_nodata_replacement_keeps_the_upstream_signature(monkeypatch, upstream):
    """替身的签名必须照抄上游 —— autogen 从签名生成工具 schema，
    `*args, **kwargs` 会让 agent **组装期**就 `TypeError`（本卡实测）。
    """
    import inspect

    ds = _fake_upstream(monkeypatch, upstream["classes"])
    GLUE.install()
    sig = inspect.signature(ds.FinnHubUtils.get_company_news)
    assert list(sig.parameters) == ["symbol"], f"签名没照抄上游：{sig}"


def test_key_columns_match_the_scorer_side():
    """`fields_obtained` 减掉的键列必须与评分侧同源，否则产物看起来"多读了一个字段"。"""
    from reference.artifact_schema import BARS_KEY_COLUMNS
    assert set(BARS_KEY_COLUMNS) <= set(GLUE.KEY_COLUMNS)


def test_glue_module_must_not_stringify_its_annotations():
    """`from __future__ import annotations` 会让 `Annotated[...]` 到 pydantic 手里
    变成解析不了的 ForwardRef —— 同样是**组装期**炸（本卡实测）。
    """
    src = (HERE / "glue" / "gateway_sources.py").read_text(encoding="utf-8")
    assert not re.search(r"^from __future__ import annotations\s*$", src, re.M), \
        "这条 future import 会让工具 schema 在 agent 组装期炸"


# ------------------------------------------------------------------ 5. run.py 的解析


@pytest.mark.parametrize("text,arm", [(INSTRUCTION_STRICT, "strict"), (INSTRUCTION_OPEN, "open")])
def test_slots_parse_on_both_arms(text, arm):
    assert RUN.slot(text, "as_of", pattern=RUN._DATE) == "2026-07-31", arm
    assert RUN.window(text) == ("2026-07-01", "2026-07-31"), arm


@pytest.mark.parametrize("text,arm", [(INSTRUCTION_STRICT, "strict"), (INSTRUCTION_OPEN, "open")])
def test_declarations_parse_on_both_arms(text, arm):
    assert RUN.declarations(text, S1_DECLARATION_FIELDS) == {
        "calendar_id": "SSE", "universe": "csi300", "data_version": "v1"}, arm


def test_universe_slot_does_not_swallow_the_endpoint_line():
    """题面里有 `可用端点：/bars /adj /calendar /limits /universe /tradability`。

    没有否定后顾时 `universe` 会命中那一行、取到 **tradability** ——
    一个长得像成功的错值（tradingagents 那张卡实测抓到）。
    """
    assert RUN.slot(INSTRUCTION_STRICT, "universe") != "tradability"


def test_missing_slot_exits_instead_of_guessing():
    with pytest.raises(SystemExit):
        RUN.slot("题面里什么都没有", "as_of", pattern=RUN._DATE)


def test_declaration_not_in_the_instruction_is_marked_unresolved():
    """题面没给的口径标 `"unresolved"`，**不填默认值**（静默补全是被单独测量的一族）。"""
    got = RUN.declarations(INSTRUCTION_STRICT, ("calendar_id", "adjust_policy"))
    assert got["adjust_policy"] == "unresolved"


def test_ledger_rows_become_fetches_one_for_one():
    from genebench_client import emit

    ledger = [
        {"path": "/universe", "params": {"universe": "csi300"}, "status": 200,
         "ts": "2026-09-07T11:00:00.000+00:00", "rows": 300},
        {"path": "/bars", "params": {"fields": "close,volume"}, "status": 200,
         "ts": "2026-09-07T11:00:01.000+00:00", "rows": 0},
        {"path": "/nodata/news", "params": {"kind": "news"}, "status": 404,
         "ts": "2026-09-07T11:00:02.000+00:00", "rows": None},
        {"path": "/bars", "params": {}, "status": 403,
         "ts": "2026-09-07T11:00:03.000+00:00", "rows": None},
    ]
    out = RUN._ledger_to_fetches(ledger, emit)
    assert [f["status"] for f in out] == ["ok", "empty", "empty", "denied"]
    assert [f["fetched_at"] for f in out] == [e["ts"] for e in ledger], \
        "fetched_at 必须逐字等于网关回包里的时间戳，不重排格式"


def test_a_request_without_a_gateway_timestamp_is_dropped_not_invented():
    """连不上网关的那条没有 `fetched_at` 可填 —— **不编一个**，宁可不进产物。"""
    from genebench_client import emit

    out = RUN._ledger_to_fetches(
        [{"path": "/bars", "params": {}, "status": None, "ts": None, "rows": None,
          "error": "connection refused"}], emit)
    assert out == []


def test_fields_obtained_counts_columns_and_drops_key_columns():
    GLUE.COLUMNS_SEEN.clear()
    GLUE.COLUMNS_SEEN.update({"code", "date", "status", "close", "volume"})
    try:
        assert GLUE.fields_obtained() == ["close", "volume"]
    finally:
        GLUE.COLUMNS_SEEN.clear()
