# -*- coding: utf-8 -*-
"""卡 2.1：`integrations/P2_CONTRACT.md` 的**出处核对**。

这份契约的写法承诺是「每条断言都能在代码里找到出处」。承诺要有东西守着，
否则下一次改网关时契约会静默变成一份**看起来仍然准确**的过期文档 ——
与 D-06 那族「机制在、保护不在」同形。

本测试**不 import `reference/`**（红线 2：答案面不上执行面，本文件将来可能被
带进执行面的测试集）。所有常量都用正则从源文件文本里读出来比对。

三条判据（任务书原文）：

1. 契约里出现的每个端点路径在 `gateway/routers/` 里存在（并且反向：每条注册路由
   都必须在契约里出现 —— 只查一个方向的话，漏写一个端点永远不会红）；
2. 引用的每个 ``(文件:行)`` 的文件存在；
3. 错误码枚举与 `reference/artifact_schema.py` 的 `LOOKAHEAD_DENY_REASONS` 一致。

另附几条同族的漂移断言（列集合、信封必填、拒绝表），理由同上：契约里**逐字抄下来**
的清单只要有一份漂了，照着它写的被测系统就会跑出「文档说能用、实际 422」。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
CONTRACT = REPO / "integrations" / "P2_CONTRACT.md"

ROUTER_FILES = ("gateway/routers/market.py", "gateway/routers/reference.py",
                "gateway/routers/sim.py")

#: 契约里出现、但**不是网关路由**的 `/开头` 记号：容器文件系统路径与模型代理前缀。
#: 用前缀白名单而不是逐条列举，是因为 `/task/...` 下的文件会随阶段增加。
NON_ROUTE_PREFIXES = ("/task", "/tmp", "/opt", "/var", "/v1")

#: 契约里**明确指出不存在**的路径。测试反过来断言它们确实没注册 ——
#: 只把它们从检查里排除掉的话，哪天真加了 `/sim/session`（那条被否决的装配路径），
#: 契约里那句「没有这个端点」就变成假的而没有任何东西说。
ASSERTED_ABSENT = ("/docs", "/redoc", "/sim/session")


# ------------------------------------------------------------------ 工具

def read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def _strip_comments(src: str) -> str:
    out = []
    for line in src.splitlines():
        i = line.find("#")
        out.append(line if i < 0 else line[:i])
    return "\n".join(out)


def const_strings(rel: str, name: str) -> list[str]:
    """从源文件文本里读一个「字符串容器常量」的成员，**不 import**。

    做法：定位行首的 ``name``，从第一个 ``=`` 起做括号配平，取出字面量整段，
    去掉注释后收所有引号串。比 `ast` 简单，且对 `frozenset({...})` /
    `tuple(...)` / 多行都成立。
    """
    src = read(rel)
    m = re.search(rf"^{re.escape(name)}\b[^=\n]*=", src, re.M)
    assert m, f"{rel} 里找不到常量 {name} —— 契约的出处没了，不是测试的问题"
    i = m.end()
    depth, start = 0, None
    for j in range(i, len(src)):
        c = src[j]
        if c in "([{":
            depth += 1
            if start is None:
                start = j
        elif c in ")]}":
            depth -= 1
            if depth == 0:
                return re.findall(r"""["']([^"']+)["']""", _strip_comments(src[start:j + 1]))
    raise AssertionError(f"{rel}:{name} 的字面量括号没配平")


def fenced(name: str) -> list[str]:
    """契约里 ```text name=<name>``` 围栏的逐行内容。"""
    body = CONTRACT.read_text(encoding="utf-8")
    m = re.search(rf"```text name={re.escape(name)}\n(.*?)```", body, re.S)
    assert m, f"契约里缺少 ```text name={name}``` 围栏 —— 判据没有落点"
    return [ln.strip() for ln in m.group(1).splitlines() if ln.strip()]


def registered_routes() -> set[str]:
    out: set[str] = set()
    for rel in ROUTER_FILES:
        out |= set(re.findall(r'@router\.(?:get|post|put|delete)\(\s*"([^"]+)"', read(rel)))
    out |= set(re.findall(r'@app\.(?:get|post)\(\s*"([^"]+)"', read("gateway/app.py")))
    return out


def contract_paths() -> set[str]:
    """契约里所有反引号包住的 `/开头` 记号。"""
    return set(re.findall(r"`(/[a-z][a-z0-9_/]*)`", CONTRACT.read_text(encoding="utf-8")))


def citations() -> list[tuple[str, int]]:
    """契约里所有 `文件:行` 引用。"""
    body = CONTRACT.read_text(encoding="utf-8")
    pat = r"`([A-Za-z0-9_\-./一-鿿]+\.(?:py|md|json|yaml|yml|sh|jsonl)):(\d+)`"
    return [(p, int(n)) for p, n in re.findall(pat, body)]


# ------------------------------------------------------------------ 0. 存在性

def test_contract_exists_and_is_substantial():
    assert CONTRACT.is_file(), f"{CONTRACT} 不存在"
    body = CONTRACT.read_text(encoding="utf-8")
    # 空壳文档同样能让下面每一条判据通过（没有端点、没有引用 = 没有可核的东西）。
    # 与 packager.assert_mutated 同一条教训：不是产物静默错，是测试静默空。
    assert len(body) > 12_000, "契约正文过短，多半是被截断或还没写完"
    for section in ("## 1. 被测系统的三件责任", "## 2. 网关 API 契约",
                    "## 3. artifact", "## 4. 禁止事项", "## 5. 版本与冻结"):
        assert section in body, f"契约缺少章节 {section!r}"


# ------------------------------------------------------------------ 1. 端点

def test_every_path_in_contract_is_a_registered_route():
    routes = registered_routes()
    unknown = sorted(
        p for p in contract_paths()
        if not p.startswith(NON_ROUTE_PREFIXES)
        and p not in ASSERTED_ABSENT
        and p not in routes
    )
    assert not unknown, (
        f"契约里写了 {unknown}，但 gateway/routers 与 gateway/app.py 里没有这些路由 —— "
        f"照着契约发请求会拿到 404。已注册：{sorted(routes)}")


def test_every_registered_route_is_documented():
    missing = sorted(r for r in registered_routes()
                     if f"`{r}`" not in CONTRACT.read_text(encoding="utf-8"))
    assert not missing, (
        f"网关注册了 {missing} 但契约没写 —— 被测方不知道有这些端点。"
        f"只查「契约里的端点存在吗」这一个方向时，漏写一个端点永远不会红")


def test_paths_asserted_absent_are_really_absent():
    routes = registered_routes()
    present = sorted(p for p in ASSERTED_ABSENT if p in routes)
    assert not present, (
        f"契约里说 {present} 不存在，实际已注册 —— 契约在撒谎。"
        f"`/sim/session` 尤其要红：那是被否决的会话装配路径（gateway/routers/sim.py 的说明）")


def test_route_set_matches_gateway_allowed_routes():
    allowed = set(const_strings("gateway/app.py", "ALLOWED_ROUTES"))
    assert registered_routes() == allowed, (
        "解析出的路由集与 gateway.app.ALLOWED_ROUTES 不等 —— 本测试的路由解析漂了，"
        "上面几条断言会跟着变成假绿")


# ------------------------------------------------------------------ 2. 引用

def test_every_citation_file_exists():
    cites = citations()
    assert len(cites) >= 120, (
        f"只解析到 {len(cites)} 条 `文件:行` 引用 —— 契约承诺「每条断言都有出处」，"
        f"太少说明大段正文没有出处，或者引用格式漂了（本测试认反引号包住的 路径:行号）")
    missing = sorted({p for p, _ in cites if not (REPO / p).is_file()})
    assert not missing, f"契约引用了不存在的文件：{missing}"


def test_citation_line_numbers_are_in_range():
    """行号会随提交漂，所以**不核内容**，只核「没有指到文件之外」。

    指到文件之外说明那次引用从一开始就是编的（或文件被大幅删减），
    这与「行号漂了几行」是两回事。
    """
    lengths: dict[str, int] = {}
    bad: list[str] = []
    for rel, line in citations():
        f = REPO / rel
        if not f.is_file():
            continue
        n = lengths.setdefault(rel, len(f.read_text(encoding="utf-8").splitlines()))
        if line > n:
            bad.append(f"{rel}:{line}（该文件只有 {n} 行）")
    assert not bad, f"契约引用的行号超出文件范围：{sorted(set(bad))}"


# ------------------------------------------------------------------ 3. 错误码

def test_lookahead_deny_reasons_match_reference():
    """判据三：契约里的六条越界 reason 必须与 `LOOKAHEAD_DENY_REASONS` 逐字一致。

    **读文件比对，不 import reference**（红线 2）。
    """
    want = set(const_strings("reference/artifact_schema.py", "LOOKAHEAD_DENY_REASONS"))
    got = set(fenced("lookahead_deny_reasons"))
    assert got == want, (
        f"契约的越界 reason 集与 reference/artifact_schema.py::LOOKAHEAD_DENY_REASONS 不等：\n"
        f"  契约多：{sorted(got - want)}\n  契约少：{sorted(want - got)}\n"
        f"这一族 reason 是闸门判据，契约漏一条 = 被测方以为那条不算前视")


def test_unbounded_request_reasons_match_reference():
    want = set(const_strings("reference/artifact_schema.py", "UNBOUNDED_REQUEST_REASONS"))
    got = set(fenced("unbounded_request_reasons"))
    assert got == want, (
        f"「只遥测不进闸门」的 reason 集不等：契约 {sorted(got)} vs 代码 {sorted(want)} —— "
        f"把遥测项写成闸门项，会让被测方以为开区间会判违例")


def test_reason_codes_cover_gateway_enum():
    """契约的 reason 全集 == `gateway/errors.py::Reason` 的全部取值。"""
    src = read("gateway/errors.py")
    body = src.split("class Reason", 1)[1].split("class GatewayDenied", 1)[0]
    want = set(re.findall(r'^\s+[A-Z_]+\s*=\s*"([a-z0-9_]+)"', _strip_comments(body), re.M))
    got = set(fenced("reason_codes"))
    assert got == want, (
        f"契约的 reason 全集与 gateway/errors.py 的 Reason 枚举不等：\n"
        f"  契约多：{sorted(got - want)}\n  契约少：{sorted(want - got)}\n"
        f"reason 原样落 access_log，是越权率与前视的结算键 —— 契约里那张表必须是全集")


def test_lookahead_reasons_are_a_subset_of_gateway_reasons():
    assert set(fenced("lookahead_deny_reasons")) <= set(fenced("reason_codes")), (
        "越界 reason 不是网关 reason 全集的子集 —— 两张表里至少有一张是编的")


# ------------------------------------------------------------------ 4. 逐字清单的漂移

def test_bars_columns_match_gateway():
    assert fenced("bars_key_columns") == list(
        const_strings("gateway/routers/market.py", "KEY_COLUMNS"))
    served = const_strings("gateway/routers/market.py", "BARS_SERVED_COLUMNS")
    assert fenced("bars_served_columns") == list(served), (
        "契约里的 /bars 服务集与 gateway/routers/market.py::BARS_SERVED_COLUMNS 不等 —— "
        "响应列**恰好**等于键列 ∪ 服务集，契约抄错一列，被测方就会拿一个不存在的字段名去 422")
    assert len(served) == 15, f"/bars 服务列应为 15 列（N-58 补记①），实为 {len(served)}"


def test_bars_served_columns_match_scoring_side():
    """网关服务集与结算侧 `BARS_FIELDS` 同源 —— 两边漂了会「反推出」从未发生的读取。"""
    gw = set(const_strings("gateway/routers/market.py", "BARS_SERVED_COLUMNS"))
    sc = set(const_strings("reference/artifact_schema.py", "BARS_FIELDS"))
    assert gw == sc, f"网关多：{sorted(gw - sc)}；结算侧多：{sorted(sc - gw)}"


def test_envelope_required_matches_schema():
    want = const_strings("reference/artifact_schema.py", "ENVELOPE_REQUIRED")
    assert fenced("envelope_required") == list(want), (
        "契约的信封必填键与 reference/artifact_schema.py::ENVELOPE_REQUIRED 不等 —— "
        "少一个键，照契约写的产物会整份 malformed")


def test_market_data_deny_matches_both_sources():
    """行情源拒绝表：契约 == 边车 == 注册表。三处同源（`ops/test_c41.py` 也盯着后两处）。"""
    sidecar = const_strings("runner/c41/egress_proxy.py", "MARKET_DATA_DENY")
    registry = const_strings("runner/registry.py", "MARKET_DATA_HOSTS")
    assert set(sidecar) == set(registry), "边车与注册表的行情源表已经漂开"
    assert fenced("market_data_deny") == list(sidecar), (
        "契约里的行情源拒绝表与 runner/c41/egress_proxy.py::MARKET_DATA_DENY 不等 —— "
        "它是绊线不是完备防线，但契约抄漏一条就等于默许了那一条")


def test_statements_match_gateway():
    assert fenced("statements") == list(
        const_strings("gateway/routers/reference.py", "STATEMENTS")), (
        "契约的三大报表清单与 /fundamentals 实际服务的六张表不等")


def test_env_vars_are_injected_by_the_runner():
    """契约里列的环境变量必须真的由 compose 模板注进任务容器。

    只查「契约写了它」不够：写一个 runner 根本不注的变量名，被测方会读到空值，
    而失败形态是「取数全 422」这种远离病灶的样子。
    """
    core = read("runner/c41/runner_core.py")
    task_block = core.split("  task:", 1)[1]
    missing = [v for v in fenced("env_vars") if f"{v}:" not in task_block]
    assert not missing, (
        f"契约列了 {missing}，但 runner/c41/runner_core.py 的任务服务 environment 里没有 —— "
        f"被测方按契约读会拿到空值")


def test_gateway_and_artifact_paths_match_packager():
    body = CONTRACT.read_text(encoding="utf-8")
    pk = read("genetask/packager.py")
    gw = re.search(r'^GATEWAY_URL\s*=\s*"([^"]+)"', pk, re.M)
    ap = re.search(r'^ARTIFACT_PATH\s*=\s*"([^"]+)"', pk, re.M)
    assert gw and ap
    assert gw.group(1) in body, f"契约没写固定槽回显的网关地址 {gw.group(1)}"
    assert ap.group(1) in body, f"契约没写产物路径 {ap.group(1)}"


def test_run_budget_matches_registry():
    """预算数字是被测方要照着做的硬约束，抄错会让它跑到一半被 429 掐掉。"""
    m = re.search(r"RUN_BUDGET[^=]*=\s*\{([^}]*)\}", read("runner/registry.py"))
    assert m, "runner/registry.py 里找不到 RUN_BUDGET"
    nums = dict(re.findall(r'"(\w+)":\s*([0-9_]+)', m.group(1)))
    body = CONTRACT.read_text(encoding="utf-8")
    calls = int(nums["max_calls"])
    tokens = int(nums["max_tokens"].replace("_", ""))
    assert str(calls) in body, f"契约没写每 run 调用上限 {calls}"
    assert f"{tokens:,}" in body or str(tokens) in body, f"契约没写 token 上限 {tokens}"


@pytest.mark.parametrize("rel", [
    "gateway/routers/market.py", "gateway/routers/reference.py", "gateway/routers/sim.py",
    "gateway/asof.py", "gateway/errors.py", "gateway/access_log.py", "gateway/app.py",
    "runner/inject.py", "runner/c41/egress_proxy.py", "runner/c41/runner_core.py",
    "runner/c42/identity.py", "runner/registry.py", "genetask/packager.py",
    "reference/artifact_schema.py", "ops/freeze_v10.py", "genebench_config.py",
    "ops/protocol/geneprotocol_v1/validate_artifact.py",
    "ops/protocol/geneprotocol_v1/MANIFEST.json",
    "ops/specs/s8_state_contract.md", "ops/specs/fairness_protocol.md",
    "ops/specs/card_2.3_artifact_schema.md",
    "ops/specs/card_4.2_parser_scorer_adapters.md",
    "ops/specs/GeneBench指标规格_v1.md",
    "ops/tickets.md", "ops/HANDOFF.md",
])
def test_first_class_sources_are_cited(rel):
    """附表列的一级来源必须真的被正文引用过 —— 挂一个没引用过的来源等于装作查过。"""
    assert (REPO / rel).is_file(), f"{rel} 不存在"
    body = CONTRACT.read_text(encoding="utf-8")
    assert f"`{rel}`" in body, f"附表/正文没有引用 {rel}"


# ══════════════════════════════════════════ 阶段二红队修复（2.rt）：契约的四条 major
#
# 同样做成双向判据：一端是代码/schema 的事实，一端是契约的措辞。

def test_access_log_params_is_documented_as_a_single_valued_view():
    """finding 2：`params` 不是「全部查询参数」，是它的单值视图。

    `dict(request.query_params)` 对重复出现的 `code` 只留最后一个值 —— 而 §2.5 又要求
    「一次带 100 个 code」，§4.4 又说三族探针只从这份日志结算。契约原来那句
    「params（全部查询参数）」是错的，照它写对账脚本在 `code` 这一列永远对不上。
    """
    src = read("gateway/app.py")
    assert "dict(request.query_params)" in src, (
        "网关不再用单值视图记 params 了 —— 契约 §2.1⑤ 那段警告要跟着改")

    body = CONTRACT.read_text(encoding="utf-8")
    seg = body[body.find("**⑤ 每次请求都进 access_log**"):body.find("### 2.2")]
    assert seg, "找不到 §2.1⑤"
    assert "单值视图" in seg, "契约没说 params 是单值视图"
    assert "最后一个值" in seg, "契约没说重复参数只留最后一个"
    assert "全部查询参数" not in seg, "契约里那句「全部查询参数」还在 —— 它是错的"


def test_the_contract_addresses_declarations_by_its_real_json_path():
    """finding 3：`/task/{stage}.json` 顶层没有 `declarations`。"""
    import json
    spec = json.loads((REPO / "ops" / "specs" / "artifact_schema" / "v1.0" / "S2.json")
                      .read_text(encoding="utf-8"))
    assert "declarations" not in spec and "declarations" in spec["properties"]
    body = CONTRACT.read_text(encoding="utf-8")
    assert "properties.declarations.required" in body, "契约没给真实路径"
    assert "`declarations.required`" not in body, (
        "契约里还有裸的 `declarations.required` —— 那个键在文件里不存在")


def test_the_contract_names_the_contracted_output_files():
    """finding 6 与它的连带：`artifact.json` 不是唯一该新建的文件。

    S2/S3/S7 的题面固定槽点名一个产出文件，容器退出后的 P8 复核允许集里有它；
    契约 §4.3 与自检清单原来都写「只写 /task/artifact.json」。
    """
    import sys
    sys.path.insert(0, str(REPO))
    from genetask.file_contract import FILE_SPECS
    from runner.c42 import harvest

    body = CONTRACT.read_text(encoding="utf-8")
    for stage, specs in FILE_SPECS.items():
        for sp in specs:
            assert sp["path"] in body, f"契约没写 {stage} 的产出文件 {sp['path']}"
            rel = "work/" + sp["path"].rsplit("/", 1)[-1]
            assert rel in harvest.PRODUCED_BY_STAGE.get(stage, ()), (
                f"{rel} 不在 harvest 的允许集里 —— 契约与采集侧漂开了")
    assert "是你唯一该新建的文件" not in body, "§4.3 那句「唯一该新建的文件」还在"


def test_the_contract_warns_that_compat_fields_do_not_reach_the_gateway():
    """finding 1：垫片 compat 层拿不到 `fields` 的控制权，而 §2.4 要求读取集相等。"""
    compat = REPO / "integrations" / "genebench_client" / "src" / "genebench_client" / "compat"
    full = '"open", "high", "low", "close", "volume", "amount"'
    assert [p.name for p in sorted(compat.glob("*.py"))
            if full in p.read_text(encoding="utf-8")], (
        "compat 层不再按完整列集请求了 —— 契约 §2.4 的警告要跟着改")

    body = CONTRACT.read_text(encoding="utf-8")
    seg = body[body.find("**`declared_reads` 只比因子输入端点**"):body.find("#### `/adj` GET")]
    assert "compat" in seg and "做不到" in seg, "§2.4 没有警告 compat 路径拿不到 fields 控制权"
    # 自检清单那一条也要带上，否则照清单逐条打勾的人会打错。
    i = body.find("- [ ] S3 任务显式传 `fields`")
    assert i > 0 and "compat" in body[i:i + 400], "自检清单那一条没带上 compat 的例外"


def test_the_adjustment_paragraph_and_the_shim_table_agree():
    """finding 4：`qfq`/`hfq` 一律 403，而垫片在本地按 adj_factor 真算 —— 两处对读会得出相反结论。

    声明写错是 `declaration_mismatch`（违例），所以两处必须互指。
    """
    assert 'v.add("declaration_mismatch"' in read("reference/artifact_schema.py"), (
        "declaration_mismatch 不再是一个 reason —— §2.4 那句要跟着改")
    body = CONTRACT.read_text(encoding="utf-8")
    seg = body[body.find("#### `/adj` GET"):body.find("#### `/calendar` GET")]
    assert "adj_factor" in seg and "允许的" in seg, "§2.4 没说本地自己算是允许的"
    assert "declaration_mismatch" in seg, "§2.4 没说声明写错是违例"
    assert "genebench_client/README.md" in seg, "§2.4 没有指向垫片 §4 的复权口径行"

    shim = (REPO / "integrations" / "genebench_client" / "README.md").read_text(encoding="utf-8")
    assert "复权口径" in shim, "垫片 §4 的偏离表还没有「复权口径」这一行"
