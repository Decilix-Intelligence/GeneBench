# -*- coding: utf-8 -*-
"""卡 2.6：接入 `integrations/rdagent_q/`（RD-Agent(Q)）的判据。

三类断言，各自能独立跑红：

  ① **钉**（`pin.json`）—— D-21 的字段齐全，且跨字段判据成立：从 PyPI 装的，
     PyPI 自己声明的仓库必须就是 `repo_url`；`commit` 与 `dist_sha256` 与
     `runner/c42/upstream_pins.py` 同源（两处漂了就红）。
  ② **接线**（`glue/`）—— 我们顶替的每一个上游属性**真的存在**。
     这一族需要装了 `rdagent` 的解释器；f01 的 venv 没有它，所以 skip 并说明
     （镜像里跑同一份文件是绿的，见 README「证据」一节）。
  ③ **形**（`launch.json` / `config.yaml` / `Dockerfile`）—— 键集、无裸 `$`、
     FROM 统一基座。这一族不需要任何外部依赖，永远真跑。

外加一条**题面解析**的判据：拿一份真的 S3 题面（逐字抄自 m6 那次真跑的
`work/INSTRUCTION.md`）过 `glue.instruction.parse`，七项口径必须一字不差地出来。
那是这个接入唯一一处「读题」的代码，读错的表现是 declarations 静默变形。
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
HERE = REPO / "integrations" / "rdagent_q"

if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


def _json(name):
    return json.loads((HERE / name).read_text(encoding="utf-8"))


# ────────────────────────────── ① 钉 ──────────────────────────────

PIN_REQUIRED = ("paper_url", "repo_url", "commit", "dist", "dist_repo_url",
                "license", "runnable_check", "retrieved_at")


def test_pin_has_every_d21_field():
    pin = _json("pin.json")
    missing = [k for k in PIN_REQUIRED if not pin.get(k)]
    assert not missing, f"pin.json 缺 D-21 字段：{missing}"


def _norm(url: str) -> str:
    return url.rstrip("/").lower().removesuffix(".git")


def test_pin_cross_field_pypi_repo_matches_repo():
    """从 PyPI 装的，**PyPI 声明的仓库必须就是 repo**。

    这一条不是形式检查：`tradingagents` 上就撞过一次同名不同项目（N-51）。
    """
    pin = _json("pin.json")
    assert pin["dist"].startswith("rdagent=="), pin["dist"]
    assert _norm(pin["dist_repo_url"]) == _norm(pin["repo_url"]), \
        f"PyPI 声明的仓库 {pin['dist_repo_url']} ≠ pin 的 repo {pin['repo_url']}"


def test_pin_agrees_with_upstream_pins():
    """与 `runner/c42/upstream_pins.py` 同源：两处漂了，「我们跑的是哪份代码」就有两个答案。"""
    from runner.c42.upstream_pins import PINS
    up = PINS["rdagent_q"]
    pin = _json("pin.json")
    assert pin["commit"] == up.commit
    assert pin["dist"] == up.dist
    assert pin["dist_sha256"] == up.dist_sha256
    assert _norm(pin["repo_url"]) == _norm(up.repo)


def test_pin_commit_and_sha_are_well_formed():
    pin = _json("pin.json")
    assert len(pin["commit"]) == 40 and all(c in "0123456789abcdef" for c in pin["commit"])
    assert len(pin["dist_sha256"]) == 64


# ────────────────────────────── ③ 形 ──────────────────────────────

def test_launch_json_key_set_is_exactly_six():
    spec = _json("launch.json")
    assert set(spec) == {"harness", "paradigm", "image", "command", "env_required", "notes"}, \
        sorted(spec)
    assert spec["paradigm"] == "P2"
    assert spec["harness"] == "rdagent_q"


def test_launch_command_has_no_bare_dollar():
    """`$` 一律写 `$$`（N-101）。写一个 `$` 的表现是「命令看起来对、跑起来是空的」。"""
    cmd = " ".join(_json("launch.json")["command"])
    i = 0
    while i < len(cmd):
        if cmd[i] == "$":
            assert i + 1 < len(cmd) and cmd[i + 1] == "$", f"裸 $ 在第 {i} 位：{cmd}"
            i += 2
            continue
        i += 1


def test_launch_env_required_lists_the_model_side_vars():
    """base URL **只从 env_required 列的变量取**；写死主机名就绕过了边车。"""
    env = _json("launch.json")["env_required"]
    assert "GENEBENCH_GATEWAY" in env
    assert "OPENAI_BASE_URL" in env and "OPENAI_API_KEY" in env


def test_no_hardcoded_model_host_anywhere_in_the_integration():
    """接线层里不许出现模型 API 的主机名 —— 出现即等于绕过边车。"""
    from runner.registry import CONFIGS
    hosts = {c.base_url.split("//", 1)[-1].split("/", 1)[0] for c in CONFIGS}
    for f in sorted(HERE.rglob("*.py")) + [HERE / "launch.json", HERE / "Dockerfile"]:
        text = f.read_text(encoding="utf-8")
        for h in hosts:
            assert h not in text, f"{f.name} 里写死了模型主机 {h}"


def test_config_yaml_key_set_is_exactly_seven_and_enabled():
    import yaml
    cfg = yaml.safe_load((HERE / "config.yaml").read_text(encoding="utf-8"))
    assert set(cfg) == {"config_id", "harness", "model", "base_url",
                        "api_key_env", "note", "enabled"}, sorted(cfg)
    assert cfg["config_id"] == "cfg-rdagent_q-deepseek"
    assert cfg["harness"] == "rdagent_q"
    assert cfg["model"] == "deepseek-chat"
    assert cfg["base_url"].startswith("https://")
    assert cfg["api_key_env"].endswith("_API_KEY")
    assert cfg["enabled"] is True


def test_the_config_is_actually_in_the_main_table():
    """`enabled: true` 要真的合并进 `CONFIGS`，且 `config_id` / `harness` 不与人重名。"""
    from runner.registry import CONFIGS
    ids = [c.config_id for c in CONFIGS]
    assert "cfg-rdagent_q-deepseek" in ids
    assert len(set(ids)) == len(ids), ids
    harnesses = [c.harness for c in CONFIGS]
    assert len(set(harnesses)) == len(harnesses), harnesses


def test_launch_spec_is_discoverable_and_points_at_our_image():
    from runner.c42.harness_commands import discover_launch_specs
    spec = discover_launch_specs()["rdagent_q"]
    assert spec["image"] == _json("launch.json")["image"] == "gb-rdagent_q-u:r1"


def test_dockerfile_first_effective_line_is_the_shared_base():
    """第一条**有效**指令必须是 `FROM gb-base:bookworm-r1`（N-62；顶部允许注释）。"""
    lines = [l.strip() for l in (HERE / "Dockerfile").read_text(encoding="utf-8").splitlines()]
    first = next(l for l in lines if l and not l.startswith("#"))
    assert first == "FROM gb-base:bookworm-r1", first


def test_dockerfile_installs_the_pinned_version_and_the_shim():
    body = (HERE / "Dockerfile").read_text(encoding="utf-8")
    assert '"rdagent==0.8.0"' in body, "Dockerfile 装的版本要与 pin.json 的 dist 一致"
    assert _json("pin.json")["dist"] == "rdagent==0.8.0"
    assert "/opt/genebench_client" in body, "垫片要进镜像（COPY + pip install --no-index）"
    assert "--no-index" in body, "垫片不在任何 index 上，且运行期装包被禁"


# ─────────────────────── 题面解析（不需要 rdagent）───────────────────────

#: 逐字抄自 m6 那次真跑的 `s3-cor-01.strict.cfg-codex-deepseek.r01/work/INSTRUCTION.md`。
REAL_S3_INSTRUCTION = """按下列声明完成任务。
任务（S3）：按下面的源方言原文实现因子，在计算窗口（上面给出的计算窗口）内逐截面计算，产出 S3 artifact（payload 含 factor_id、expression、values_ref、nonfinite、warmup、approximated_operators、degeneracy）。
因子：worldquant_101.006
源方言原文：`(-1 * correlation(open, volume, 10))`
因子值按下列口径算：expression 照抄原文，算子不得自行替换
payload.expression 照抄原文
暖机从计算窗口首日起算，不得用窗口之前的数据把前几个截面补出来。
除题面列出的输入材料外，数据只能经网关获取：http://gateway:18080
可用端点：/bars /adj /calendar /limits /universe /tradability
as_of=2026-07-31
window=2026-01-05 到 2026-07-31
universe=csi300
输入材料：无；所需数据全部经网关获取
取数时 /bars 必须显式传 fields 参数（不传即判畸形）
本次任务的口径（逐项）：
- required_fields=[open, volume]（这个因子只需要开盘价与成交量，接口值 [open, volume]）
- lookback=10（回看窗口 10 个交易日，接口值 10）
- eval_frequency=daily（按日频评估，接口值 daily）
- operator_semantics={correlation: pearson_rolling_window}（correlation 是两条序列在滚动窗口内的 Pearson 相关系数，接口值 {correlation: pearson_rolling_window}）
- param_order=[series_a, series_b, window]（算子参数顺序：第一条序列、第二条序列、窗口长度，接口值 [series_a, series_b, window]）
- nonfinite_policy=propagate（Inf/NaN 原样传播，不替换为 0 或前值，接口值 propagate）
- warmup_policy=null_until_full（回看窗口未满的日期输出空值，接口值 null_until_full）
产出要包含：非有限值（Inf/NaN）计数、暖机期处理、退化（常数输出）报警。

凡题面没有给出的口径，不得自行补一个默认值，须在 declarations 里显式标记 unresolved。
产出路径：/task/artifact.json
校验串：GBC-C-fd47ce9e45b1cb81
"""


def test_instruction_parser_reads_a_real_s3_task_verbatim():
    from glue import instruction
    spec = instruction.parse(REAL_S3_INSTRUCTION)
    assert spec.as_of == "2026-07-31"
    assert (spec.window_start, spec.window_end) == ("2026-01-05", "2026-07-31")
    assert spec.universe == "csi300"
    assert spec.factor_id == "worldquant_101.006"
    assert spec.expression == "(-1 * correlation(open, volume, 10))"
    assert spec.declarations == {
        "required_fields": ["open", "volume"],
        "lookback": 10,
        "eval_frequency": "daily",
        "operator_semantics": {"correlation": "pearson_rolling_window"},
        "param_order": ["series_a", "series_b", "window"],
        "nonfinite_policy": "propagate",
        "warmup_policy": "null_until_full",
    }


def test_instruction_parser_refuses_to_invent_a_missing_slot():
    """槽位没了就抛。**猜一个 as_of 会让越界变成合法请求，而产物上看不出来。**"""
    from glue import instruction
    without = REAL_S3_INSTRUCTION.replace("as_of=2026-07-31\n", "")
    with pytest.raises(instruction.InstructionError):
        instruction.parse(without)


def test_the_declaration_keys_cover_what_the_stage_schema_requires():
    """题面给的七项恰好就是 S3 的声明字段集 —— 少一项 `emit` 会写 `unresolved`，
    多一项就是我们解析出了题面没有的东西。"""
    sys.path.insert(0, str(REPO / "integrations" / "genebench_client" / "src"))
    from genebench_client import emit

    from glue import instruction
    got = set(instruction.parse(REAL_S3_INSTRUCTION).declarations)
    assert got == set(emit.declaration_fields("S3")), sorted(got)


def test_code_shape_round_trips_between_the_gateway_and_qlib():
    """网关是 `600000.SH`，qlib 是 `SH600000`。产出文件要回到题面那一种写法。"""
    from glue import panel
    for c in ("600000.SH", "000001.SZ", "300059.SZ"):
        assert panel.to_gateway_code(panel.to_qlib_code(c)) == c
    assert panel.to_qlib_code("600000.SH") == "SH600000"
    # 认不出来的写法**原样返回**，不猜：猜错会把一个标的悄悄改名。
    assert panel.to_qlib_code("weird") == "weird"


# ────────────────────────────── ② 接线 ──────────────────────────────

def _skip_without_rdagent():
    pytest.importorskip(
        "rdagent",
        reason="rdagent 只装在 gb-rdagent_q-u:r1 镜像里，f01 的 venv 没有它 —— "
               "这一族判据在镜像里跑（见 integrations/rdagent_q/README.md「证据」一节）")


def test_every_declared_replacement_point_exists_upstream():
    """我们顶替的每一个上游属性都要**真的存在**。上游改名要炸在这里，不是炸在真跑里。"""
    _skip_without_rdagent()
    import importlib

    from glue.bootstrap import REPLACEMENTS
    assert REPLACEMENTS, "替换点清单不许是空的 —— 空检查恒真（§10）"
    for rep in REPLACEMENTS:
        mod = importlib.import_module(rep["module"])
        obj = mod
        for part in rep["attr"].split("."):
            assert hasattr(obj, part), f"{rep['module']}:{rep['attr']} 里 {part} 不在了"
            obj = getattr(obj, part)


def test_the_one_method_we_override_exists_upstream():
    """`glue/scenario.py` 唯一覆写的方法。"""
    _skip_without_rdagent()
    from rdagent.scenarios.qlib.experiment.factor_experiment import QlibFactorScenario
    assert hasattr(QlibFactorScenario, "get_runtime_environment")


def test_the_costeer_knob_we_pass_is_a_real_constructor_parameter():
    """`knowledge_self_gen=False` 必须是上游自己的形参，不是我们塞进去的 kwarg。"""
    _skip_without_rdagent()
    import inspect
    from rdagent.components.coder.CoSTEER import CoSTEER
    sig = inspect.signature(CoSTEER.__init__)
    assert "knowledge_self_gen" in sig.parameters
    assert sig.parameters["knowledge_self_gen"].default is True


def test_replacement_list_is_documented_not_just_listed():
    """每一条替换都要说清 via / why —— 「改了什么」不解释「为什么」等于没记。"""
    from glue.bootstrap import REPLACEMENTS
    for rep in REPLACEMENTS:
        assert set(rep) == {"module", "attr", "via", "why"}, rep
        assert rep["why"].strip() and rep["via"].strip(), rep


def test_bootstrap_moves_every_rdagent_output_out_of_task():
    """RD-Agent 的四个落点全部离开 `/task` —— 落在 `/task` 下会进 run.json 的 unexpected。"""
    from glue import bootstrap
    for p in (bootstrap.WORKSPACE, bootstrap.PICKLE_CACHE, bootstrap.DATA_FOLDER,
              bootstrap.LOG_DIR, bootstrap.PROMPT_CACHE):
        assert not p.startswith("/task"), p


#: 同一道题的 **open 臂**题面（逐字抄自 `s3-cor-01.open.cfg-rdagent_q-deepseek.r01/work/INSTRUCTION.md`）。
#: 两臂的差异只允许是「题面的表达形式」与「协议工件的有无」——
#: 所以同一份解析代码必须两种写法都认，且**不许按臂分支**。
REAL_S3_INSTRUCTION_OPEN = """按下列声明完成任务。
请把下面这条因子按它的源方言原文实现出来，在计算窗口（见 上面给出的计算窗口）内对每个截面、每只标的算出值，并如实报告非有限值、暖机期与退化情况
产出一份 S3 artifact（payload 里要有 factor_id、payload.expression、values_ref、nonfinite、warmup、approximated_operators、degeneracy 这几个键）。
因子编号 worldquant_101.006，原文是 `(-1 * correlation(open, volume, 10))`。
因子值按下列口径算：payload 里的 expression 请照抄原文，算子不要自行替换
暖机从计算窗口的第一天起算，不要拿窗口之前的数据把开头几个截面补出来。
除题面列出的输入材料外，数据只能经本环境的数据网关获取，网关在 http://gateway:18080
网关提供这些端点：/bars /adj /calendar /limits /universe /tradability
本次任务的 as_of 是 2026-07-31
计算窗口（window）是 2026-01-05 到 2026-07-31
标的范围（universe）是 csi300
给你的材料：无；所需数据全部经网关获取
取数时向 /bars 必须明确列出要的字段（fields 参数），不传会被判畸形
本次任务的口径（逐项）：
- 这个因子只需要开盘价与成交量（字段 required_fields，接口值 [open, volume]）
- 回看窗口 10 个交易日（字段 lookback，接口值 10）
- 按日频评估（字段 eval_frequency，接口值 daily）
- correlation 是两条序列在滚动窗口内的 Pearson 相关系数（字段 operator_semantics，接口值 {correlation: pearson_rolling_window}）
- 算子参数顺序：第一条序列、第二条序列、窗口长度（字段 param_order，接口值 [series_a, series_b, window]）
- Inf/NaN 原样传播，不替换为 0 或前值（字段 nonfinite_policy，接口值 propagate）
- 回看窗口未满的日期输出空值（字段 warmup_policy，接口值 null_until_full）
产出要包含：非有限值（Inf/NaN）计数、暖机期处理、退化（常数输出）报警。

凡题面没有给出的口径，不得自行补一个默认值，须在 declarations 里显式标记 unresolved。
把结果写到 /task/artifact.json
校验串：GBC-C-80f8dd9d06531973
"""


def test_the_open_arm_phrasing_parses_to_exactly_the_same_spec():
    """第一次真跑时 open 臂 exit_code=1、零产物，就是因为解析器只认 strict 的键值写法。

    这条判据把那次失败钉住：两臂解析出来的 spec 必须**逐字段相等**。
    """
    from glue import instruction
    a = instruction.parse(REAL_S3_INSTRUCTION)
    b = instruction.parse(REAL_S3_INSTRUCTION_OPEN)
    assert (a.as_of, a.window_start, a.window_end, a.universe, a.factor_id, a.expression) == \
           (b.as_of, b.window_start, b.window_end, b.universe, b.factor_id, b.expression)
    assert a.declarations == b.declarations


def test_universe_is_not_stolen_by_the_endpoint_list():
    """题面里有一行 `可用端点：… /universe /tradability`。

    锚点没防住路径时，`universe` 会被解析成 **"tradability"** —— 而那种错**没有症状**：
    网关照样返回一个成分表，因子照样算得出来，只是标的池整个换了。
    """
    from glue import instruction
    for text in (REAL_S3_INSTRUCTION, REAL_S3_INSTRUCTION_OPEN):
        assert instruction.parse(text).universe == "csi300"


def test_the_parser_does_not_branch_on_the_arm():
    """公平性：不许读 `GENEBENCH_ARM` 去改行为（`integrations/README.md` §0）。

    判据走 AST 而不是 grep：这几个文件的文档里**要写**「这里没有按臂分支」这句话，
    而 grep 分不开「代码里出现」与「文档里提到」—— 第一版就是这么误报的。
    docstring 与注释不算，任何**其它**位置的这个字符串都算。
    """
    import ast
    for f in sorted((HERE / "glue").glob("*.py")) + [HERE / "run.py"]:
        tree = ast.parse(f.read_text(encoding="utf-8"))
        docs = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
                body = getattr(node, "body", [])
                if body and isinstance(body[0], ast.Expr) and \
                        isinstance(body[0].value, ast.Constant) and \
                        isinstance(body[0].value.value, str):
                    docs.add(id(body[0].value))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value == "GENEBENCH_ARM" \
                    and id(node) not in docs:
                raise AssertionError(f"{f.name}:{node.lineno} 代码里读了 GENEBENCH_ARM")
            if isinstance(node, ast.Name) and node.id == "GENEBENCH_ARM":
                raise AssertionError(f"{f.name}:{node.lineno}")
