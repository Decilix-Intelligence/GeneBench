# -*- coding: utf-8 -*-
"""卡 2.6：接入 `integrations/finmem/` 的判据。

五族，每族都要能被**定向破坏跑红**（恒绿的门证明不了任何事）：

1. `pin.json` 齐全 + 跨字段判据。FinMem **不在任何 index 上**（仓库根的
   `pyproject.toml` 只是 poetry 的本地工程壳，`name = "finmem" / version = "0.0.0"`），
   所以钉的是**源码 tarball 的 sha256 + commit**，判据是「tarball 的 URL 必须由
   `repo_url` 与 `commit` 生成」—— 名字对、字节不对，正是 D-21 要防的那件事。
2. `launch.json` / `config.yaml` 的键集与硬约束（六键 / 七键、`$$`、
   base_url 是 https、`api_key_env` 结尾、host 不在行情源表里），
   且两处发现入口真的收得到它。
3. `Dockerfile` 从统一基座起，源码经 `COPY` 而不是构建期 `git clone` / `curl`，
   `COPY` 之后有 `chmod -R a+rX`（0600 的入口在 `user 1000` 下读不了）。
4. 接线层的替换点**在被替换的模块里确实存在**：装得起上游就对真模块查
   （`puppy.agent.ChatOpenAICompatible` / `puppy.memorydb.OpenAILongerThanContextEmb`），
   装不起来就 skip 并说明 —— f01 上没有那个 3.10 的 venv，真检查在
   `smoke_in_container.py` 的第 2、3 项里（`--network none` 跑，看着两道门先红后绿）。
5. 接线层自己的性质：离线向量后端确定、空文本不产生全零向量、
   决策映射里 `hold` 是 0.0 而「没跑出决策」是 `None`、
   `glue/` 里没有任何写死的主机名、题面槽不被「可用端点」那一行带偏。
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
HERE = REPO / "integrations" / "finmem"
PKG_SRC = REPO / "integrations" / "genebench_client" / "src"

sys.path.insert(0, str(REPO))
if str(PKG_SRC) not in sys.path:
    sys.path.insert(0, str(PKG_SRC))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def pin() -> dict:
    return json.loads((HERE / "pin.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def launch() -> dict:
    return json.loads((HERE / "launch.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def cfg() -> dict:
    return yaml.safe_load((HERE / "config.yaml").read_text(encoding="utf-8"))


# ── 1. pin.json ────────────────────────────────────────────────────────────
def test_pin_has_every_field_d21_asks_for(pin):
    for key in ("paper_url", "repo_url", "commit", "license",
                "runnable_check", "runnable_check_result", "retrieved_at"):
        assert pin.get(key), f"pin.json 缺 {key}"
    assert re.fullmatch(r"[0-9a-f]{40}", pin["commit"]), pin["commit"]
    assert pin["runnable_check_result"] != "PENDING", \
        "runnable_check 还没在镜像里真跑过 —— 那一栏不是留给意图的"


def test_pin_pins_bytes_not_names(pin):
    """跨字段：tarball 的 URL 必须由 repo_url 与 commit 生成，且 sha256 是 64 位。"""
    owner_repo = pin["repo_url"].rstrip("/").split("github.com/", 1)[1]
    assert pin["source_tarball"].endswith(f"{owner_repo}/tar.gz/{pin['commit']}"), \
        f"tarball 指的不是 {owner_repo}@{pin['commit']}：{pin['source_tarball']}"
    assert re.fullmatch(r"[0-9a-f]{64}", pin["source_tarball_sha256"])


def test_pin_is_honest_about_not_being_on_an_index(pin):
    """不是从 PyPI 装的 → `dist` 与 `dist_repo_url` 都必须是 null。

    只填一个（比如写个 `finmem==0.0.0` 却没有落点）会让后来的人以为
    `pip install finmem` 能装到同一份字节。
    """
    assert (pin["dist"] is None) == (pin["dist_repo_url"] is None)
    if pin["dist"] is None:
        assert pin["source_tarball"] and pin["source_tarball_sha256"], \
            "既不从 index 装、又不钉源码字节，这条 pin 什么都没钉住"


def test_pin_deviations_are_listed_not_implied(pin):
    """两处依赖偏离必须在 pin 里点名 —— 藏在 Dockerfile 注释里不算数。"""
    blob = json.dumps(pin["deviations"], ensure_ascii=False)
    assert "torch" in blob
    assert "3.10" in blob


def test_pin_matches_upstream_pins_when_that_table_has_an_entry():
    """`runner/c42/upstream_pins.py` 里**有**这一条时必须逐字一致（现在没有）。

    两处各自都真、放在一起是假话，正是 N-51 那次的形态。这条判据是幂等的：
    等谁把 finmem 加进那张表，它自动开始守。
    """
    from runner.c42 import upstream_pins as UP

    entry = UP.PINS.get("finmem")
    if entry is None:
        pytest.skip("upstream_pins.PINS 里还没有 finmem（票据 2.6-finmem.md N-?）")
    p = json.loads((HERE / "pin.json").read_text(encoding="utf-8"))
    assert getattr(entry, "commit", None) == p["commit"]


# ── 2. launch.json / config.yaml ───────────────────────────────────────────
def test_launch_key_set_is_exactly_six(launch):
    assert set(launch) == {"harness", "paradigm", "image", "command",
                           "env_required", "notes"}
    assert launch["paradigm"] == "P2"


def test_launch_command_has_no_bare_dollar(launch):
    """命令要经一层 compose 变量展开：一个 `$` 会被提前吃掉（N-101）。

    现场表现是「命令看起来对、跑起来是空的」。
    """
    joined = " ".join(launch["command"])
    for m in re.finditer(r"\$+", joined):
        assert len(m.group(0)) % 2 == 0, f"裸 $：…{joined[max(0, m.start() - 30):m.end() + 30]}…"


def test_launch_entry_is_the_310_venv(launch):
    """入口必须是那个 3.10 的 venv —— 基座的 python3 是 3.12，装不上 FinMem 的依赖。"""
    assert "/opt/finmem/venv/bin/python" in " ".join(launch["command"])


def test_launch_home_is_not_under_task(launch):
    """HOME 指到 /task 下会往 run dir 的 work/ 里多放文件，破 P8 文件集封闭。"""
    joined = " ".join(launch["command"])
    assert "HOME=/tmp" in joined and "HOME=/task" not in joined


def test_config_key_set_is_exactly_seven_and_passes_the_three_gates(cfg):
    assert set(cfg) == {"config_id", "harness", "model", "base_url",
                        "api_key_env", "note", "enabled"}
    assert cfg["base_url"].startswith("https://")
    assert cfg["api_key_env"].endswith("_API_KEY")
    from runner.registry import MARKET_DATA_HOSTS

    host = cfg["base_url"].split("://", 1)[1].split("/", 1)[0]
    assert host not in MARKET_DATA_HOSTS, \
        "行情/新闻源域名一律不得入表 —— 那等于让被测系统绕过数据面"


def test_both_discovery_entries_really_pick_it_up(cfg, launch):
    from runner import registry as REG
    from runner.c42 import harness_commands as HC

    ids = [c.config_id for c in REG.CONFIGS]
    assert cfg["config_id"] in ids, ids
    assert len(ids) == len(set(ids)), "config_id 重名 —— 静默取其一会变成一次长调查"
    assert launch["harness"] in HC.discover_launch_specs()
    assert cfg["harness"] == launch["harness"]


# ── 3. Dockerfile ─────────────────────────────────────────────────────────
def test_dockerfile_starts_from_the_shared_base():
    body = (HERE / "Dockerfile").read_text(encoding="utf-8")
    froms = [ln.split()[1] for ln in body.splitlines() if ln.strip().startswith("FROM ")]
    assert froms == ["gb-base:bookworm-r1"], froms


def test_dockerfile_does_not_fetch_the_system_at_build_time(pin):
    """源码经 COPY 进来，**不在 Dockerfile 里 clone/curl**。

    GitHub 在构建网里可不可达是一件会变的事（2.6-tradingagents 那一轮实测超时，
    本轮实测 200）。把它写进 Dockerfile 等于让镜像能不能建取决于当天的网。
    """
    body = (HERE / "Dockerfile").read_text(encoding="utf-8")
    code = "\n".join(ln for ln in body.splitlines() if not ln.strip().startswith("#"))
    assert "git clone" not in code
    assert not re.search(r"^\s*RUN[^\n]*\bcurl\b", code, re.M), \
        "构建期 curl 取源码：不可达的那天镜像就建不出来了"
    assert pin["commit"] in code, "COPY 进来的 tarball 名里必须带 pin 的 commit"


def test_dockerfile_opens_the_entry_for_uid_1000():
    """仓库里是 0600（红线 5），COPY 原样带进镜像，而容器以 user 1000:1000 跑。

    忘了这一步的现场表现是两臂十几秒退出、`no_artifact`
    （2.6-tradingagents 第一次真跑就是这么挂的）。
    """
    body = (HERE / "Dockerfile").read_text(encoding="utf-8")
    assert re.search(r"chmod -R a\+rX[^\n]*/opt/finmem", body)


def test_requirements_are_upstreams_frozen_list_minus_torch():
    body = (HERE / "requirements.gb.txt").read_text(encoding="utf-8")
    pins = [ln for ln in body.splitlines() if ln.strip() and not ln.startswith("#")]
    assert len(pins) > 60, "上游那份冻结清单有 80+ 行，这里只剩几行说明被改过了"
    assert all("==" in ln for ln in pins), "冻结清单里出现了非精确版本"
    assert not any(ln.startswith("torch==") for ln in pins)
    assert not any("download.pytorch.org" in ln for ln in pins)
    # 环境标记是这份清单只能装在 3.10 上的原因；去掉它会让 3.12 上"装了个寂寞"。
    assert sum('python_version < "3.11"' in ln for ln in pins) > 60


# ── 4. 接线点在被替换的模块里确实存在 ──────────────────────────────────────
def _seam_targets() -> dict[str, tuple[str, str]]:
    """接线层声称要顶替的东西：模块 → (属性名, 它在哪个上游文件里)。"""
    return {
        "puppy.chat": ("ChatOpenAICompatible", "puppy/chat.py"),
        "puppy.agent": ("ChatOpenAICompatible", "puppy/agent.py 的 from .chat import"),
        "puppy.memorydb": ("OpenAILongerThanContextEmb", "puppy/memorydb.py:56"),
    }


def test_seam_targets_exist_in_the_modules_they_replace():
    puppy = pytest.importorskip(
        "puppy",
        reason="f01 上没有 FinMem（它要 3.10 + faiss + guardrails，只装在镜像的 venv 里）。"
               "这条的真检查在 integrations/finmem/smoke_in_container.py 第 2、3 项："
               "docker run --network none … → 看着两道门先红后绿。")
    import importlib

    for mod_name, (attr, where) in _seam_targets().items():
        mod = importlib.import_module(mod_name)
        assert hasattr(mod, attr), f"{mod_name} 里没有 {attr}（上游{where}变了）"
    assert all(hasattr(puppy, n) for n in ("LLMAgent", "MarketEnvironment", "RunMode"))


def test_the_seam_modules_name_exactly_those_targets():
    """接线层顶替的名字与上面那张表必须对得上 —— 顶替一个不存在的名字不会报错，
    只会静默无效，那正是最看不见的失效。"""
    chat = (HERE / "glue" / "chat_seam.py").read_text(encoding="utf-8")
    emb = (HERE / "glue" / "embedding_seam.py").read_text(encoding="utf-8")
    assert 'getattr(puppy_chat_module, "ChatOpenAICompatible")' in chat
    assert 'setattr(puppy_agent_module, "ChatOpenAICompatible"' in chat
    assert 'setattr(puppy_memorydb_module, "OpenAILongerThanContextEmb"' in emb


# ── 5. 接线层自己的性质（不需要上游）────────────────────────────────────────
@pytest.fixture(scope="module")
def emb_mod():
    return _load("finmem_embedding_seam", HERE / "glue" / "embedding_seam.py")


@pytest.fixture(scope="module")
def instr_mod():
    return _load("finmem_instruction", HERE / "glue" / "instruction.py")


def test_offline_vectors_are_deterministic_and_never_all_zero(emb_mod, monkeypatch):
    monkeypatch.setenv("GENEBENCH_FINMEM_EMB_PROBE", "0")
    monkeypatch.setattr(emb_mod, "_PROBE", None, raising=False)
    e = emb_mod.GatewayEmb()
    assert e.backend == "offline_hash" and e.get_embedding_dimension() == 1536
    assert (e(["涨了三天"]) == e(["涨了三天"])).all()
    assert not (e(["涨了三天"]) == e(["跌了三天"])).all()
    # 本环境每一天都没有新闻，而上游对「今天没有新闻」的处理是往短期记忆里塞一个空串。
    # 全零向量在 IndexFlatIP 下与任何查询的内积都是 0，检索退化成任取。
    z = e([""])
    assert z.shape == (1, 1536) and z.dtype.name == "float32" and abs(z).sum() > 0
    assert e([]).shape == (0, 1536)


def test_the_probe_is_a_measurement_not_an_assertion(emb_mod):
    """探针必须真打一次并把结果留下来 —— 「deepseek 没有 embeddings」是一件
    实测的事（真跑实测 404），不是一件可以断言的事。"""
    src = (HERE / "glue" / "embedding_seam.py").read_text(encoding="utf-8")
    assert "/embeddings" in src and "status" in src
    assert "def probe(" in src


def test_hold_is_a_decision_and_a_missing_decision_is_not(monkeypatch):
    entry = _load("finmem_entry", HERE / "run.py")
    assert entry.DECISION_SCORE == {"buy": 1.0, "hold": 0.0, "sell": -1.0}
    # 题面写着「无观点的格子不得补 0」；`hold` 与「这一天根本没跑出决策」含义相反。
    assert entry.DECISION_SCORE.get(None) is None
    assert entry.DECISION_SCORE.get("review") is None


def test_no_hardcoded_hostnames_anywhere_in_the_glue():
    """base URL 只从 env_required 列的变量取；写死主机名就绕过了边车与预算闸，
    行情源主机名更是直接绕过数据面。"""
    bad = re.compile(r"https?://(?!127\.0\.0\.1|localhost)[A-Za-z0-9.-]+", re.I)
    hits = []
    for p in sorted((HERE / "glue").glob("*.py")) + [HERE / "run.py"]:
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            m = bad.search(line)
            if m:
                hits.append(f"{p.name}:{i} {m.group(0)}")
    assert not hits, hits


def test_missing_sources_use_kinds_the_client_knows(instr_mod):
    env_mod = _load("finmem_env_data", HERE / "glue" / "env_data.py")
    from genebench_client import nodata

    kinds = {k for k, _api, _slot in env_mod.MISSING_SOURCES}
    assert kinds <= set(nodata.KINDS), kinds
    slots = {slot for _k, _a, slot in env_mod.MISSING_SOURCES}
    # 与 environment.py::OneDateRecord 的三个文本槽逐字对上。
    assert slots == {"news", "filing_k", "filing_q"}


_FAKE_INSTRUCTION = (
    "本次任务的 as_of 是 2026-07-31。\n"
    "可用端点：/bars /adj /calendar /limits /universe /tradability\n"
    "计算窗口（window）是 2026-01-05 到 2026-07-31。\n"
    "标的范围（universe）是 csi300。\n"
    "本次任务的口径（逐项）：\n"
    "- 信号值是分数（字段 value_semantics，接口值 score）\n"
    "- 频率（字段 signal_frequency，接口值 daily）\n"
    "- 方向（字段 direction，接口值 higher_is_long）\n"
    "- 成分参照（字段 universe_ref，接口值 csi300@2026-07-31）\n"
    "- 缺失（字段 missing_policy，接口值 keep_null）\n"
    "- 输入因子（字段 input_factors，接口值 [gtja_191.001, gtja_191.002]）\n"
)


def test_universe_slot_is_not_stolen_by_the_endpoint_line(instr_mod):
    """题面里有 `可用端点：… /universe …`。没有否定后顾，`universe` 会先命中那一行、
    再越过 ` /` 取到 `tradability` —— 一个**长得像成功**的错值。"""
    assert instr_mod.slot(_FAKE_INSTRUCTION, "universe") == "csi300"
    assert instr_mod.slot(_FAKE_INSTRUCTION, "as_of",
                          pattern=r"\d{4}-\d{2}-\d{2}") == "2026-07-31"
    assert instr_mod.window(_FAKE_INSTRUCTION) == ("2026-01-05", "2026-07-31")


def test_a_slot_that_is_absent_exits_instead_of_guessing(instr_mod):
    with pytest.raises(SystemExit):
        instr_mod.slot("题面里什么槽都没有", "as_of", pattern=r"\d{4}-\d{2}-\d{2}")
    with pytest.raises(SystemExit):
        instr_mod.window("只有一端：window 2026-01-05")


def test_a_declaration_the_task_did_not_give_is_marked_not_filled(instr_mod):
    from genebench_client import emit

    fields = emit.declaration_fields("S5")
    got = instr_mod.declarations(_FAKE_INSTRUCTION, fields)
    assert set(got) == set(fields)
    assert got["input_factors"] == ["gtja_191.001", "gtja_191.002"]
    # 缺失 ≠ 标记：题面没给的那一项写显式 "unresolved"，不是省略、也不是编一个默认值。
    thin = instr_mod.declarations("- 方向（字段 direction，接口值 higher_is_long）", fields)
    assert thin["direction"] == "higher_is_long"
    assert thin["value_semantics"] == "unresolved"


def test_the_real_instruction_of_the_task_we_ran_still_parses(instr_mod):
    """拿**真跑用的那份题面**再走一遍两臂。staging 被清掉时 skip。"""
    stg = Path("/data/shared/genebench/staging/i_finmem_s5-eco-01/tasks/s5-eco-01/arms")
    if not stg.is_dir():
        pytest.skip(f"{stg} 不在（staging 已清）")
    for arm in ("strict", "open"):
        text = (stg / f"INSTRUCTION.{arm}.md").read_text(encoding="utf-8")
        assert instr_mod.slot(text, "as_of", pattern=r"\d{4}-\d{2}-\d{2}") == "2026-07-31"
        assert instr_mod.slot(text, "universe") == "csi300"
        assert instr_mod.window(text) == ("2026-01-05", "2026-07-31")


def test_the_readme_quotes_the_digest_of_the_image_that_actually_ran():
    """README 里的 digest 必须是 64 位十六进制，且与 5.3 那条出集命令里的一致 ——
    两处不一致时，复现出来的不是同一个镜像。"""
    body = (HERE / "README.md").read_text(encoding="utf-8")
    digs = set(re.findall(r"sha256:[0-9a-f]{64}", body))
    assert len(digs) == 1, digs
