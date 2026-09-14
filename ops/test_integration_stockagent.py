# -*- coding: utf-8 -*-
"""卡 2.7（内部演练）接入 StockAgent 的判据。

分三族：
  * **接入形态**（五件套的键集、命名、Dockerfile 里那几行「少了就当场炸」的东西）；
  * **题面解析**（两臂两种写法都要认，且三处「偷值」都不许发生）；
  * **翻译规则**（决策 → 一格信号的三态：数 / null / flat）。

需要 import 上游包的那一族只在**镜像里**跑得到（f01 没有容器运行时，
上游也只装在 gb-stockagent:r1 里）—— 那一族在这里 skip，真门在
`integrations/stockagent/smoke.py` 的 `upstream.replacement_points` 与 `gemini.trap` 两项。
"""
from __future__ import annotations

import ast
import json
import pathlib
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
HERE = REPO / "integrations" / "stockagent"
sys.path.insert(0, str(REPO / "integrations" / "genebench_client" / "src"))


def _load(stem: str):
    """按**路径**加载，挂在一个带前缀的模块名下。

    **不能 `sys.path.insert(HERE)` 然后 `from glue import ...`**：
    每个 P2 接入都有一个叫 `glue` 的包，先 import 的那一个会占住
    `sys.modules["glue"]`，后面别人再 import 就拿到我的模块。
    pytest 是**先把所有测试文件 import 一遍再开跑**的，所以肇事者甚至不会自己红 ——
    红的是别人（本卡第一版全量里 `ops/test_integration_rdagent_q.py` 挂了 8 条）。
    """
    import importlib.util
    name = f"_stockagent_glue_{stem}"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, HERE / "glue" / f"{stem}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


I = _load("instruction")
S = _load("signals")
seams = _load("seams")

# 两臂的真实写法（逐字取自 reference/tasks/v1.0-smoke/s5-eco-01/arms/，只留与解析相关的行）。
STRICT = """按下列声明完成任务。
除题面列出的输入材料外，数据只能经网关获取：http://gateway:18080
可用端点：/bars /adj /calendar /limits /universe /tradability
as_of=2026-07-31
window=2026-01-05 到 2026-07-31
universe=csi300
本次任务的口径（逐项）：
- value_semantics=score（信号值是可比的分数，不是秩，接口值 score）
- signal_frequency=daily（信号按日生成，接口值 daily）
- direction=higher_is_long（信号越大越看多，接口值 higher_is_long）
- universe_ref=csi300@2026-07-31（标的范围是截至 2026-07-31 的沪深300成分股，按 PIT 宇宙，接口值 csi300@2026-07-31）
- missing_policy=keep_null（无观点的格子保持为空，不填 0，接口值 keep_null）
- input_factors=[gtja_191.001, gtja_191.002, gtja_191.003]（输入因子是三条，接口值 [gtja_191.001, gtja_191.002, gtja_191.003]）
"""

OPEN = """按下列声明完成任务。
除题面列出的输入材料外，数据只能经本环境的数据网关获取，网关在 http://gateway:18080
网关提供这些端点：/bars /adj /calendar /limits /universe /tradability
本次任务的 as_of 是 2026-07-31
计算窗口（window）是 2026-01-05 到 2026-07-31
标的范围（universe）是 csi300
本次任务的口径（逐项）：
- 信号值是可比的分数，不是秩（字段 value_semantics，接口值 score）
- 信号按日生成（字段 signal_frequency，接口值 daily）
- 信号越大越看多（字段 direction，接口值 higher_is_long）
- 标的范围是截至 2026-07-31 的沪深300成分股，按 PIT 宇宙（字段 universe_ref，接口值 csi300@2026-07-31）
- 无观点的格子保持为空，不填 0（字段 missing_policy，接口值 keep_null）
- 输入因子是 gtja_191.001、gtja_191.002、gtja_191.003 三条（字段 input_factors，接口值 [gtja_191.001, gtja_191.002, gtja_191.003]）
"""

S5_FIELDS = ("value_semantics", "signal_frequency", "direction",
             "universe_ref", "missing_policy", "input_factors")


# ------------------------------------------------------------------ 五件套

def _launch():
    return json.loads((HERE / "launch.json").read_text(encoding="utf-8"))


def test_launch_json_key_set_is_exactly_six():
    assert set(_launch()) == {"harness", "paradigm", "image", "command",
                              "env_required", "notes"}


def test_launch_json_is_p2_and_command_escapes_every_dollar():
    spec = _launch()
    assert spec["paradigm"] == "P2"
    joined = " ".join(spec["command"])
    # 单个 `$` 会被 compose 的变量展开提前吃掉（N-101）：命令看起来对、跑起来是空的。
    singles = [i for i, ch in enumerate(joined)
               if ch == "$" and joined[i - 1:i] != "$" and joined[i + 1:i + 2] != "$"]
    assert not singles, f"命令里有裸 $：{joined}"


def test_launch_image_tag_is_the_one_the_dockerfile_builds():
    """`launch.json` 的 image 与我们真的 build 出来的 tag 必须是同一个名字。
    对不上的表现是「构建成功了，跑的还是旧镜像」——不会有任何东西变红。"""
    readme = (HERE / "README.md").read_text(encoding="utf-8")
    assert _launch()["image"] in readme


def test_home_is_not_under_task():
    """`/task` 就是 run dir 的 `work/` 本身；HOME 落在它下面会进 run.json 的 unexpected。"""
    joined = " ".join(_launch()["command"])
    assert "HOME=/task" not in joined and "HOME=/tmp" in joined


def _config():
    import yaml
    return yaml.safe_load((HERE / "config.yaml").read_text(encoding="utf-8"))


def test_config_yaml_key_set_is_exactly_seven():
    assert set(_config()) == {"config_id", "harness", "model", "base_url",
                              "api_key_env", "note", "enabled"}


def test_config_base_url_is_https_and_key_env_is_named_like_a_key():
    cfg = _config()
    assert cfg["base_url"].startswith("https://")
    assert cfg["api_key_env"].endswith("_API_KEY")


def test_config_host_is_not_a_market_data_host():
    """红线：行情/新闻源域名一律不得入表 —— 那等于让被测系统绕过数据面。"""
    from urllib.parse import urlparse
    from runner.registry import MARKET_DATA_HOSTS
    host = urlparse(_config()["base_url"]).hostname
    assert host not in set(MARKET_DATA_HOSTS)


def test_config_id_and_harness_are_unique_across_both_trees():
    from runner import registry as R
    from runner.c42 import harness_commands as H
    ids = [c.config_id for c in R.CONFIGS]
    assert ids.count(_config()["config_id"]) == 1
    assert sorted(H.discover_launch_specs()).count(_launch()["harness"]) == 1


def test_config_harness_matches_launch_harness():
    assert _config()["harness"] == _launch()["harness"]


# ------------------------------------------------------------------ pin（D-21）

def _pin():
    return json.loads((HERE / "pin.json").read_text(encoding="utf-8"))


def test_pin_has_the_d21_keys_and_at_least_one_of_commit_or_dist():
    pin = _pin()
    for k in ("paper_url", "repo_url", "commit", "license", "runnable_check"):
        assert pin.get(k), f"pin.json 少 {k}"
    assert pin["commit"] or pin["dist"], "commit 与 dist 至少要有一个"
    assert len(pin["commit"]) == 40


def test_pin_license_is_a_finding_not_a_guess():
    """上游仓库里没有 LICENSE 文件、GitHub API 的 license 是 null。
    那么 pin 里就得写 `none_declared` 并给出依据，**不许猜一个 MIT**。"""
    pin = _pin()
    assert pin["license"] == "none_declared"
    assert pin.get("license_evidence")


def test_pin_records_every_vendored_source_with_a_hash():
    pin = _pin()
    assert pin["source_tarball_sha256"] and len(pin["source_tarball_sha256"]) == 64
    assert pin["source_files_sha256"], "逐文件哈希是这份 pin 的硬证据"
    assert "agent.py" in pin["source_files_sha256"]
    for v in pin["vendored"]:
        assert len(v["tarball_sha256"]) == 64 and len(v["commit"]) == 40


def test_pin_runnable_check_chdirs_first():
    """上游 log/custom_logger.py 在 import 期开一个相对 CWD 的 FileHandler；
    不 chdir 的 runnable_check 在构建期实测报 FileNotFoundError: '/task/log/test.txt'。"""
    assert "chdir" in _pin()["runnable_check"]


# ------------------------------------------------------------------ Dockerfile

def _dockerfile():
    return (HERE / "Dockerfile").read_text(encoding="utf-8")


def test_dockerfile_installs_setuptools_before_the_shim():
    """基座里没有 setuptools。少这一行，`--no-build-isolation` 那条当场
    `BackendUnavailable: Cannot import 'setuptools.build_meta'`（本卡 build1.log 实测）。"""
    t = _dockerfile()
    assert "setuptools" in t
    assert t.index("setuptools") < t.index("--no-build-isolation")


def test_dockerfile_opens_the_read_bit_for_non_root():
    """仓库文件是 0600（红线 5），COPY 保模式，容器以非 root 跑。"""
    assert "chmod -R a+rX" in _dockerfile()


def test_dockerfile_verifies_the_vendored_tarballs():
    assert "sha256sum -c" in _dockerfile()


def test_dockerfile_does_not_clone_at_build_time():
    """GitHub 在构建网里不保证可达；`git clone` 一个可能连不上的地址不是正路。"""
    assert "git clone" not in _dockerfile()


def test_dockerfile_installs_no_market_data_client_and_no_second_model_client():
    """装了 tushare/yfinance/akshare 等于在镜像里留一条绕过数据面的路；
    装了 google-generativeai 等于留一条绕过边车的路。两样都不装。"""
    t = _dockerfile() + (HERE / "requirements.gb.txt").read_text(encoding="utf-8")
    lines = [ln for ln in t.splitlines() if not ln.strip().startswith("#")]
    body = "\n".join(lines)
    for bad in ("tushare", "yfinance", "akshare", "baostock", "google-generativeai"):
        assert bad not in body, f"Dockerfile/requirements 里出现了 {bad}"


# ------------------------------------------------------------------ 题面解析

@pytest.mark.parametrize("text,label", [(STRICT, "strict"), (OPEN, "open")])
def test_both_arms_parse_to_the_same_three_slots(text, label):
    assert I.as_of(text) == "2026-07-31"
    assert I.window(text) == ("2026-01-05", "2026-07-31")
    assert I.universe(text) == "csi300"


@pytest.mark.parametrize("text", [STRICT, OPEN])
def test_both_arms_yield_all_six_declaration_values(text):
    got = I.declarations(text, list(S5_FIELDS))
    assert set(got) == set(S5_FIELDS)
    assert got["value_semantics"] == "score"
    assert got["universe_ref"] == "csi300@2026-07-31"
    assert got["input_factors"] == ["gtja_191.001", "gtja_191.002", "gtja_191.003"]


def test_universe_is_not_stolen_by_the_endpoint_list():
    """题面里有一行 `可用端点：… /universe /tradability`。任何「找 universe 后面
    那个词」的解析器都会取到 `tradability` —— 而网关照样返回一个成分表、
    信号照样算得出来，**产物上完全看不出来**，只是标的池整个换了。"""
    only_endpoints = "网关提供这些端点：/bars /adj /calendar /limits /universe /tradability\n"
    with pytest.raises(I.InstructionError):
        I.universe(only_endpoints)


def test_as_of_is_not_stolen_by_the_date_inside_universe_ref():
    """`universe_ref=csi300@2026-07-31` 里也有一个日期。它恰好与 as_of 相同，
    所以取错了**不会报错也不会差** —— 直到某道题的两个日期不一样为止。
    防法是：口径行不参与 as_of 的取值。"""
    text = "- universe_ref=csi300@2020-01-01（接口值 csi300@2020-01-01）\nas_of=2026-07-31\n"
    assert I.as_of(text) == "2026-07-31"


def test_missing_slot_raises_instead_of_guessing():
    with pytest.raises(I.InstructionError):
        I.as_of("这道题什么也没说")


def test_declaration_values_come_from_the_interface_value_not_the_prose():
    """open 臂那行散文里「分数」「秩」两个词都在，取错就会把 `rank` 当成答案。"""
    line = "- 信号值是可比的分数，不是秩（字段 value_semantics，接口值 score）\n"
    assert I.declarations(line, ["value_semantics"]) == {"value_semantics": "score"}


# ------------------------------------------------------------------ 翻译规则

class _FakeMarket:
    def __init__(self, tradable=True):
        self._t = tradable

    def tradable(self, day, code):
        return self._t


class _FakeFactors:
    def __init__(self, missing=False):
        self._m = missing

    def all_missing(self, day, code):
        return self._m


def _rec(actions):
    r = S.Recorder()
    r.day = 1
    for i, a in enumerate(actions):
        r.note(i, 1, a)
    return r


def test_score_is_net_signed_flow_over_all_decisions():
    rec = _rec([{"action_type": "buy", "stock": "A"},
                {"action_type": "buy", "stock": "A"},
                {"action_type": "sell", "stock": "A"},
                {"action_type": "no"}])
    out = S.to_signals(rec, days=["2026-07-31"], slot_of_code={"600000.SH": "A"},
                       market=_FakeMarket(), factors=_FakeFactors())
    assert out == [{"date": "2026-07-31", "symbol": "600000.SH", "value": 0.25}]


def test_all_no_is_flat_not_zero():
    """题面：主动空仓写 flat，且**主动空仓不得写 0**。"""
    rec = _rec([{"action_type": "no"}, {"action_type": "no"}])
    out = S.to_signals(rec, days=["2026-07-31"], slot_of_code={"600000.SH": "A"},
                       market=_FakeMarket(), factors=_FakeFactors())
    assert out[0]["value"] == "flat"


def test_a_score_of_zero_stays_a_number():
    """买卖抵消算出来的 0 是一个分数，不是「主动空仓」。两者含义相反，不许互相改写。"""
    rec = _rec([{"action_type": "buy", "stock": "A"}, {"action_type": "sell", "stock": "A"}])
    out = S.to_signals(rec, days=["2026-07-31"], slot_of_code={"600000.SH": "A"},
                       market=_FakeMarket(), factors=_FakeFactors())
    assert out[0]["value"] == 0.0 and out[0]["value"] != "flat"


def test_untradable_cell_is_null():
    rec = _rec([{"action_type": "buy", "stock": "A"}])
    out = S.to_signals(rec, days=["2026-07-31"], slot_of_code={"600000.SH": "A"},
                       market=_FakeMarket(tradable=False), factors=_FakeFactors())
    assert out[0]["value"] is None


def test_cell_with_every_input_factor_missing_is_null():
    rec = _rec([{"action_type": "buy", "stock": "A"}])
    out = S.to_signals(rec, days=["2026-07-31"], slot_of_code={"600000.SH": "A"},
                       market=_FakeMarket(), factors=_FakeFactors(missing=True))
    assert out[0]["value"] is None


def test_a_day_with_no_decisions_at_all_is_null_not_flat():
    """一条决策都没有，是「系统没给出看法」，不是「它决定空仓」。"""
    out = S.to_signals(S.Recorder(), days=["2026-07-31"],
                       slot_of_code={"600000.SH": "A"},
                       market=_FakeMarket(), factors=_FakeFactors())
    assert out[0]["value"] is None


# ------------------------------------------------------------------ 接线层自律

def _literals(path: pathlib.Path) -> list[str]:
    """取 AST 里的字符串字面量。**不用 grep 源码** —— 那会把解释「为什么要换掉
    行情源」的注释也算命中，那是一条恒红的门。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def test_no_hostname_is_written_into_the_glue():
    bad = ("yahoo", "yfinance.com", "finnhub", "tushare.pro", "akshare",
           "reddit.com", "stocktwits", "api.deepseek.com", "api.openai.com",
           "generativelanguage.googleapis.com", "yunwu.ai")
    hits = []
    for p in sorted(HERE.rglob("*.py")):
        for lit in _literals(p):
            for b in bad:
                if b in lit:
                    hits.append((p.name, b))
    assert not hits, hits


def test_base_url_only_comes_from_the_env_vars_launch_json_declares():
    lits = _literals(HERE / "glue" / "seams.py")
    assert "OPENAI_BASE_URL" in lits
    declared = set(_launch()["env_required"])
    assert {"OPENAI_BASE_URL", "OPENAI_API_KEY", "GENEBENCH_GATEWAY"} <= declared


def _code_literals(path: pathlib.Path) -> list[str]:
    """AST 里的字符串字面量，**去掉 docstring**。

    第一版这条判据是 grep 源码的，于是被 `glue/instruction.py` 那句
    「`GENEBENCH_ARM` **不读**」的说明文字命中 —— 一条恒红的门。
    （与卡 2.6-tradingagents 记的是同一个教训，我自己又踩了一次。）
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                docs.add(id(body[0].value))
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs]


def test_run_py_does_not_branch_on_the_arm():
    """两臂的差异只能是「题面的表达形式」与「协议工件的有无」。
    读 GENEBENCH_ARM 去改行为（改超参、改重试、改模型）是干预本身。"""
    for p in sorted(HERE.rglob("*.py")):
        assert "GENEBENCH_ARM" not in _code_literals(p), f"{p.name} 读了 GENEBENCH_ARM"


def test_default_model_path_is_the_sidecar_not_the_stub():
    """smoke 里那个确定性桩只有显式传进去才走得到；默认必须是 `seams.Sidecar`。"""
    src = (HERE / "run.py").read_text(encoding="utf-8")
    assert "sidecar = seams.Sidecar()" in src
    assert "StubSidecar" not in src


def test_every_registered_replacement_point_names_a_real_upstream_attribute():
    """需要 import 上游 —— 上游只装在镜像里。这里 skip，真门在 smoke.py。"""
    try:
        import util  # noqa: F401
    except Exception:
        pytest.skip("上游只装在 gb-stockagent:r1 里；真门是 smoke.py 的 upstream.replacement_points")
    import importlib
    for mod, attr, _why in seams.REPLACEMENTS:
        obj = importlib.import_module(mod)
        for part in attr.split("."):
            assert hasattr(obj, part), f"{mod}.{attr} 不在了"
            obj = getattr(obj, part)


def test_scratch_is_not_under_task():
    assert not str(seams.SCRATCH).startswith("/task")


# ------------------------------------------------------------------ 文档与账本

def test_readme_says_what_was_replaced_and_what_it_costs():
    t = (HERE / "README.md").read_text(encoding="utf-8")
    for anchor in ("参考价", "none_declared", "复现", "sha256:", "已知偏离"):
        assert anchor in t, f"README 缺「{anchor}」一节"


def test_coverage_matrix_has_a_stockagent_row_with_eight_stage_cells():
    # 表里每一行的系统名都带反引号（`| \`finmem\` | P2 | …`）—— 第一版这条判据漏了它，
    # 于是「行加了但判据说没加」。
    rows = [ln for ln in (REPO / "integrations" / "COVERAGE.md")
            .read_text(encoding="utf-8").splitlines()
            if ln.strip().startswith("| `stockagent`")]
    assert len(rows) == 1, "COVERAGE.md 里 stockagent 应当恰好一行"
    cells = [c.strip() for c in rows[0].strip().strip("|").split("|")]
    assert len(cells) >= 9, cells
