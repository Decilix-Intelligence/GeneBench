# -*- coding: utf-8 -*-
"""卡 2.6-alphaagent 的判据：`integrations/alphaagent/` 这一个接入是不是**齐的、真的**。

四族，对应任务书第 6 条：

  A. `pin.json` 齐全，且**跨字段判据**过（D-21）。这里的跨字段判据不是「PyPI
     声明的仓库就是 repo」—— 本接入不从 PyPI 装（PyPI 上没有这个包），所以换成
     三条同样可核的：dist_repo_url 必须指向 repo_url 的同一个 commit；
     Dockerfile 里核的 sha256 必须与 pin 里的 dist_sha256 逐字相同；
     license 是 `none_declared` 时，README 必须写明为什么（仓库里没有 LICENSE）。
  B. `launch.json` 六键、`config.yaml` 七键，命令里**没有裸 `$`**（N-101）。
  C. `Dockerfile` FROM 统一基座，且不含几条会毁掉这个接入的写法
     （git clone / 装 tushare / 装 numba / 运行期装包）。
  D. glue 的**替换点在被替换的模块里确实存在** —— 这一族要 import 上游包，
     装不起来就 skip 并说明（任务书第 6 条明写）。

**恒绿自证**：A/B/C 三族读的是磁盘上的真文件，改坏任一处都会红（收口时做过四处
定向破坏，见 ops/tickets_inbox/2.6-alphaagent.md「恒绿自证」一节）。
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
D = ROOT / "integrations" / "alphaagent"

PIN = D / "pin.json"
LAUNCH = D / "launch.json"
CONFIG = D / "config.yaml"
DOCKERFILE = D / "Dockerfile"
README = D / "README.md"


def _json(p: pathlib.Path):
    return json.loads(p.read_text(encoding="utf-8"))


# ───────────────────────────── A. pin.json ─────────────────────────────

def test_the_five_piece_set_is_all_there():
    """五件套 + 入口 + 接线目录，缺一个这个接入就不完整。"""
    for name in ("Dockerfile", "launch.json", "config.yaml", "pin.json", "README.md",
                 "run.py", "smoke.py"):
        assert (D / name).is_file(), f"integrations/alphaagent/{name} 不在"
    assert (D / "glue").is_dir()
    assert (D / "glue" / "__init__.py").is_file()


def test_pin_has_every_d21_field():
    pin = _json(PIN)
    for k in ("paper_url", "repo_url", "commit", "dist", "dist_repo_url", "license",
              "runnable_check", "runnable_check_result", "retrieved_at", "note"):
        assert k in pin and str(pin[k]).strip(), f"pin.json 缺 {k}"
    assert re.fullmatch(r"[0-9a-f]{40}", pin["commit"]), "commit 必须是 40 位 sha"
    assert re.match(r"^\d{4}-\d{2}-\d{2}T", pin["retrieved_at"])


def test_pin_cross_field_the_dist_url_points_at_the_pinned_commit_of_the_pinned_repo():
    """跨字段判据①：tarball 的下载地址必须就是 repo_url 的那个 commit。

    这一条是「版本号不等于源码」的替代品：不从 PyPI 装时，能钉住「装的是哪一版」
    的只有「哪个仓 + 哪个 commit + 哪串摘要」三件套自洽。
    """
    pin = _json(PIN)
    owner_repo = pin["repo_url"].rstrip("/").split("github.com/")[-1]
    assert owner_repo, "repo_url 不是 github 地址？跨字段判据要改"
    assert owner_repo in pin["dist_repo_url"], \
        f"dist_repo_url 里没有 {owner_repo}：钉的仓和下的源码对不上"
    assert pin["commit"] in pin["dist_repo_url"], \
        "dist_repo_url 里没有 pin 的 commit：下的不是钉的那一版"


def test_pin_cross_field_the_sha256_is_the_one_the_dockerfile_checks():
    """跨字段判据②：pin 里的摘要必须就是构建期真核的那一串。

    两处漂了就等于没钉 —— 而漂的那一天，构建照样成功。
    """
    pin = _json(PIN)
    sha = pin["dist_sha256"]
    assert re.fullmatch(r"[0-9a-f]{64}", sha), "dist_sha256 形态不对"
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert sha in text, "Dockerfile 没有核 pin.json 里的那一串 sha256"
    assert "sha256sum -c -" in text, "Dockerfile 里没有真的去核（只写了个常量不算）"


def test_pin_cross_field_an_undeclared_license_must_be_explained_in_the_readme():
    """跨字段判据③：license 写 none_declared 时，README 必须给出处。

    猜一个 MIT 比空着更坏；空着而不说明，下一个人会以为是漏填。
    """
    pin = _json(PIN)
    if pin["license"] != "none_declared":
        pytest.skip(f"license 是 {pin['license']!r}，这条只管 none_declared")
    text = README.read_text(encoding="utf-8")
    assert "LICENSE" in text and "none_declared" in text, \
        "pin 写了 none_declared，README 里却没写清楚为什么"


def test_pin_says_out_loud_that_head_is_not_the_paper_version():
    """这个仓库的 git 历史起于 2026-07（论文是 2025-02）—— HEAD 是重写后的版本。

    不写这一句，读者会拿论文里的数字来解释本接入的结果。
    """
    pin = _json(PIN)
    note = pin["note"]
    assert "不是论文那一版" in note or "not the paper" in note.lower(), \
        "pin.note 必须点明 HEAD 与论文版本的关系"


# ───────────────────────── B. launch.json / config.yaml ─────────────────────────

LAUNCH_KEYS = {"harness", "paradigm", "image", "command", "env_required", "notes"}
CONFIG_KEYS = {"config_id", "harness", "model", "base_url", "api_key_env", "note", "enabled"}


def test_launch_json_key_set_is_exactly_six():
    spec = _json(LAUNCH)
    assert set(spec) == LAUNCH_KEYS, f"键集不对：多 {set(spec) - LAUNCH_KEYS}，少 {LAUNCH_KEYS - set(spec)}"
    assert spec["paradigm"] == "P2"
    assert spec["harness"] == "alphaagent"
    assert isinstance(spec["command"], list) and spec["command"][:2] == ["sh", "-c"]
    assert isinstance(spec["env_required"], list) and spec["env_required"]


def test_launch_command_has_no_bare_dollar():
    """N-101：这份 JSON 过一层 compose 变量展开，写一个 `$` 会被提前吃掉 ——
    现场表现是「命令看起来对、跑起来是空的」。所以 `$` 必须成对。"""
    cmd = " ".join(_json(LAUNCH)["command"])
    stripped = cmd.replace("$$", "")
    assert "$" not in stripped, f"命令里有裸 $：{cmd!r}"


def test_launch_env_required_covers_what_run_py_actually_reads():
    """声明要的环境变量必须覆盖入口真读的那几个 —— 否则注入器不会注入，
    而现场表现是「跑起来直接退」。"""
    need = set(_json(LAUNCH)["env_required"])
    src = (D / "run.py").read_text(encoding="utf-8")
    assert "GENEBENCH_GATEWAY" in need
    for var in ("OPENAI_BASE_URL", "OPENAI_API_KEY"):
        assert var in src, f"run.py 没读 {var}？env_required 与实现漂了"
        assert var in need, f"run.py 读了 {var} 而 env_required 没列"


def test_config_yaml_key_set_is_exactly_seven_and_passes_the_three_gates():
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert set(cfg) == CONFIG_KEYS, f"键集不对：{sorted(set(cfg) ^ CONFIG_KEYS)}"
    assert cfg["harness"] == _json(LAUNCH)["harness"], "config 与 launch 的 harness 名不一致"
    assert cfg["base_url"].startswith("https://"), "base_url 必须 https"
    assert cfg["api_key_env"].endswith("_API_KEY"), "api_key_env 必须以 _API_KEY 结尾"
    assert isinstance(cfg["enabled"], bool)
    assert cfg["model"] == "deepseek-chat", "所有 enabled 配置必须同一模型"


def test_config_id_and_harness_name_are_unique_across_both_trees():
    """`harnesses/` 与 `integrations/` 两棵树之间也不许重复 —— 重名当场 RegistryError，
    而静默取其一会把「我明明加了却没生效」变成一次长调查。"""
    mine_cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    mine_launch = _json(LAUNCH)
    others_cfg, others_harness = [], []
    for tree in ("harnesses", "integrations"):
        base = ROOT / tree
        if not base.is_dir():
            continue
        for p in sorted(base.glob("*/config.yaml")):
            if p.parent.name == "alphaagent":
                continue
            got = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            others_cfg.append(got.get("config_id"))
        for p in sorted(base.glob("*/launch.json")):
            if p.parent.name == "alphaagent":
                continue
            others_harness.append(json.loads(p.read_text(encoding="utf-8")).get("harness"))
    assert mine_cfg["config_id"] not in others_cfg, "config_id 与别的接入重名"
    assert mine_launch["harness"] not in others_harness, "harness 名与别的接入重名"


# ───────────────────────────── C. Dockerfile ─────────────────────────────

def test_dockerfile_starts_from_the_shared_base():
    first = next(ln for ln in DOCKERFILE.read_text(encoding="utf-8").splitlines()
                 if ln.strip().upper().startswith("FROM"))
    assert first.strip() == "FROM gb-base:bookworm-r1", f"基座不对：{first!r}"


def _dockerfile_instructions() -> str:
    """只留**指令行**，把注释掐掉。

    这一步不是讲究：Dockerfile 的注释里正当地写着「**不在 Dockerfile 里 git clone**」，
    照整份文本 grep 会把那句解释判成违规 —— 而那正是它在解释的东西。
    """
    return "\n".join(ln for ln in DOCKERFILE.read_text(encoding="utf-8").splitlines()
                     if not ln.lstrip().startswith("#"))


def test_dockerfile_does_not_reach_the_network_for_source():
    """`git clone` 一个可能连不上的地址是被点名禁止的写法（README §1②）。"""
    assert "git clone" not in _dockerfile_instructions()
    assert "COPY alphaagent-b42cb397.tar.gz" in DOCKERFILE.read_text(encoding="utf-8"), \
        "上游源码必须是 COPY 进来的 tarball"


def test_dockerfile_installs_neither_tushare_nor_numba():
    """两条都不是洁癖：

    tushare 是行情源客户端 —— 装了就给被测系统留了一条绕过数据面的路（红线 5）；
    numba 要把基座的 numpy 2.5.2 降到 <2 —— 那是动统一基座的数值栈，
    而 S3 的产出正是 parquet 数值。
    """
    blob = "\n".join(ln for ln in _dockerfile_instructions().splitlines()
                     if "pip install" in ln or (ln.startswith("      ") and "==" in ln))
    for banned in ("tushare", "numba", "agentscope"):
        assert banned not in blob, f"Dockerfile 的 pip install 里出现了 {banned}"


def test_dockerfile_makes_the_glue_readable_by_a_non_root_container_user():
    """$GENEBENCH_ROOT 全树 0600（红线 5），而 COPY 原样带权限、容器非 root ——
    不 chmod 的后果是 `Permission denied`、两臂十几秒退出、判 no_artifact。"""
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert re.search(r"chmod\s+-R\s+a\+rX\s+/opt/gb_alphaagent", text), \
        "接线层 COPY 之后没有 chmod -R a+rX"


def test_the_glue_lives_under_a_name_that_cannot_shadow_the_upstream_package():
    """接线层若放在 /opt/alphaagent，`python3 /opt/alphaagent/run.py` 会把该目录
    放进 sys.path[0]，与 site-packages 里的 `alphaagent` 抢同一个顶层名字。"""
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "/opt/gb_alphaagent" in text
    assert not re.search(r"COPY\s+\S+\s+/opt/alphaagent/", text)


# ───────────────────────── D. 替换点确实存在 ─────────────────────────

def _upstream():
    """import 上游包，**按本接入真正的用法**。

    那句 `compat.install("tushare")` 不是为了让测试过：镜像里没装 tushare（红线 5），
    而上游 `alphaagent/data/__init__.py` 顶层就 import 它 —— 不顶替，这一族在容器里
    照样 `ModuleNotFoundError`（实测过一次）。`glue/bootstrap.py` 在真跑里做的
    就是同一件事，测试与实现走同一条路才有意义。
    """
    pytest.importorskip(
        "alphaagent",
        reason="上游 alphaagent 只装在接入镜像 gb-alphaagent-u:r1 里，f01 的解释器上没有；"
               "这一族判据在容器里跑（见 README §5.5「怎么复现」）。")
    compat = pytest.importorskip(
        "genebench_client.compat",
        reason="垫片没装 —— 这一族与真跑走同一条 import 路径，缺了垫片就不是同一条路。")
    compat.install("tushare")


def test_the_module_we_shadow_really_is_the_one_that_imports_tushare():
    """glue/bootstrap.py 顶替 `sys.modules["tushare"]`。**被顶替的那个 import
    必须真的在上游里** —— 它哪天不 import tushare 了，这处接线就成了无用的仪式，
    而无用的仪式看起来和有用的一模一样。"""
    _upstream()
    import alphaagent.data.tushare_client as tc  # noqa: F401
    src = pathlib.Path(tc.__file__).read_text(encoding="utf-8")
    assert re.search(r"^import tushare as ts$", src, re.M), \
        "上游 tushare_client 不再 `import tushare as ts` —— bootstrap 的顶替点要重定"


def test_the_three_upstream_callables_the_glue_leans_on_exist():
    """agent.py 同形替换的是 FactorEvalTools 与 build_system_prompt，
    但它**调用**的是这三个 —— 少一个，接线当场 ImportError。"""
    _upstream()
    from alphaagent.dsl.catalog import operator_catalog_markdown
    from alphaagent.dsl.eval import compile_multi_line_factor, eval_factor
    from alphaagent.factor.mining.loop import run_trajectory
    for fn in (operator_catalog_markdown, compile_multi_line_factor, eval_factor, run_trajectory):
        assert callable(fn)


def test_our_tools_have_exactly_the_shape_run_trajectory_requires():
    """`run_trajectory` 只依赖三个方法 —— 这正是「同形替换」成立的条件。
    上游哪天多依赖一个方法，这条会红，那时才该改 glue。"""
    _upstream()
    import inspect

    import alphaagent.factor.mining.loop as loop
    # 读**整个模块**而不是 run_trajectory 一个函数：`dispatch` 是它经
    # `_dispatch_parallel(tools, ...)` 间接调的，只看函数体会漏掉（实测漏过一次）。
    src = inspect.getsource(loop)
    used = {m for m in ("schemas", "dispatch", "result_to_content") if f"tools.{m}" in src}
    assert used == {"schemas", "dispatch", "result_to_content"}, \
        f"run_trajectory 用到的 tools 方法变了：{used}"

    import sys
    sys.path.insert(0, str(D))
    try:
        from glue.agent import ImplementTools
    finally:
        sys.path.remove(str(D))
    for m in used:
        assert callable(getattr(ImplementTools, m, None)), f"ImplementTools 少了 {m}"


def test_ts_corr_is_a_rolling_pearson_with_the_param_order_the_task_declares():
    """题面声明 `operator_semantics={correlation: pearson_rolling_window}`、
    `param_order=[series_a, series_b, window]`。上游 `TS_CORR(df1, df2, window)`
    正好是这个语义与这个参数顺序 —— 这是「逐算子对应」而不是「效果差不多」的依据。"""
    _upstream()
    import inspect

    from alphaagent.dsl.core.operators import TS_CORR
    params = list(inspect.signature(TS_CORR).parameters)
    assert params == ["df1", "df2", "window"], f"TS_CORR 的参数顺序变了：{params}"
    assert "Pearson" in (inspect.getdoc(TS_CORR) or ""), "TS_CORR 不再自称 Pearson"
