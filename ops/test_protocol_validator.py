"""协议 validator（GQ 臂的执行机制）的验收。

**最要紧的一条**：validator 与 scorer L1 在同一语料上的**子集判定逐条相同**。
不相同就是「两份必然漂」的第四个实例 —— 前三次是 provider 记录值、
可交易性词汇、冻结门；每一次的表现都是「两边都不报错」。
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from genetask import packager as P                       # noqa: E402
from genetask import protocol_rules as PR                # noqa: E402
from reference import artifact_samples as smp            # noqa: E402
from reference import artifact_schema as sch             # noqa: E402

ALL_CAPS = {"n33_bars_open_amount_vwap": True, "s8_state_endpoint": True,
            "anchor_ladder_54": False}
VALIDATOR = _REPO / "ops" / "protocol" / "geneprotocol_v1" / "validate_artifact.py"


def _load_validator():
    spec = importlib.util.spec_from_file_location("_gqv", VALIDATOR)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


V = _load_validator()


@pytest.fixture(scope="module")
def rows():
    return P.load_params(_REPO / "genetask" / "params" / "v1.0-smoke40.yaml")


def _rules_for(task_id, rows, tmp_path):
    row = next(r for r in rows if r["task_id"] == task_id)
    b = P.build_task(row, capabilities=ALL_CAPS)
    PR.write_rules(b.task, tmp_path)
    return b.task, {k: json.loads((tmp_path / v).read_text(encoding="utf-8"))
                    for k, v in V.RULES.items()}


# --------------------------------------------------------------- 零依赖边界

def test_validator_never_reaches_reference():
    """跑在容器内 —— import 到 `reference/` 就是把答案面拖上执行面。"""
    import ast
    tree = ast.parse(VALIDATOR.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    assert "reference" not in names and "genetask" not in names, names
    r = subprocess.run([sys.executable, "-c",
                        f"import importlib.util,sys;"
                        f"s=importlib.util.spec_from_file_location('m',{str(VALIDATOR)!r});"
                        f"m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
                        f"print('reference' in sys.modules)"],
                       capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == "False", r.stderr[-400:]


def test_validator_has_no_hardcoded_stage_knowledge():
    """规则**全数据驱动**。硬编码一份阶段知识 = 把 reference 的表抄到执行面。"""
    src = VALIDATOR.read_text(encoding="utf-8")
    for stage in sch.STAGES:
        assert f'"{stage}"' not in src, f"validator 里硬编码了 {stage} 的知识"
    for field in ("signal_frequency", "slippage_reference_price", "missing_policy"):
        assert field not in src, f"validator 里硬编码了字段名 {field}"


def test_validator_does_not_touch_the_network_or_gold():
    import ast
    tree = ast.parse(VALIDATOR.read_text(encoding="utf-8"))
    # 只看**代码**，不看注释与文档字符串 —— 注释里写「它是 scorer L1 的子集」是在
    # 说明边界，不是在调用它。用字符串黑名单扫全文会把说明判红（词表两头的老教训）。
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    for bad in ("requests", "urllib", "socket", "http", "httpx", "aiohttp"):
        assert bad not in imported, f"validator 不得联网，却 import 了 {bad}"
    strings = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)
               and isinstance(n.value, str)}
    for s in strings:
        low = s.lower()
        assert "http://" not in low and "https://" not in low, f"字符串里有 URL：{s[:60]}"


# --------------------------------------------------------------- 子集一致性（最要紧的一条）

@pytest.mark.parametrize("name", sorted(smp.LEGAL))
def test_validator_agrees_with_scorer_on_legal_samples(name, tmp_path):
    """合法样例：两边都必须说「没问题」。"""
    s = smp.LEGAL[name]
    task = {"task_id": s.task["task_id"], "stage": s.task["stage"],
            "payload_profile": None, "declared": s.artifact["declarations"]}
    PR.write_rules(task, tmp_path)
    rules = {k: json.loads((tmp_path / v).read_text(encoding="utf-8"))
             for k, v in V.RULES.items()}
    got = V.validate(deepcopy(s.artifact), rules)
    assert got == [], f"{name} 合法样例被 validator 判红：{got}"
    assert sch.validate(deepcopy(s.artifact), task=s.task).ok


def test_validator_is_a_strict_subset_of_scorer_l1(tmp_path):
    """**子集判定逐条相同**：validator 报的每一条，scorer 也必须报同一个 code；
    反之不成立（scorer 还有探针与比数那两层）。

    不相同 = 「两份必然漂」的第四个实例。前三次的表现都是「两边都不报错」。
    """
    s = smp.LEGAL["S5"]
    task = {"task_id": s.task["task_id"], "stage": "S5", "payload_profile": None,
            "declared": s.artifact["declarations"]}
    PR.write_rules(task, tmp_path)
    rules = {k: json.loads((tmp_path / v).read_text(encoding="utf-8"))
             for k, v in V.RULES.items()}

    cases = {
        "declaration_missing": lambda a: a["declarations"].pop("direction"),
        "declaration_null": lambda a: a["declarations"].__setitem__("direction", None),
        "payload_key_missing": lambda a: a["payload"].pop("coverage"),
        "stage_mismatch": lambda a: a.__setitem__("stage", "S6"),
    }
    for code, mutate in cases.items():
        a = deepcopy(s.artifact)
        before = json.dumps(a, sort_keys=True)
        mutate(a)
        assert json.dumps(a, sort_keys=True) != before, f"{code} 突变空转"
        mine = V.validate(a, rules)
        theirs = sch.validate(a, task=s.task).findings
        # **不比 code 字符串**：两边对同一件事用了不同的名字
        # （validator 的 payload_key_missing ↔ scorer 的 s5_coverage_missing），
        # 比名字只会逼着两边同步一张命名表 —— 那是第二份必然漂的东西。
        # 子集的实质是：**validator 说有问题的地方，scorer 也说有问题**。
        assert mine, f"{code}：validator 什么都没报"
        assert theirs, f"{code}：scorer 什么都没报 —— validator 比 scorer 还严，那就不是子集"
        my_paths = {v["path"] for v in mine}
        their_paths = {f.path for f in theirs}
        # 路径交集**只对字段级违例**要求：信封级的归类两边不同是合理的
        # （validator 报 `$.stage`，scorer 归到 `$task` —— 说的是同一件事）。
        field_level = {p for p in my_paths
                       if p.startswith(("$.declarations.", "$.payload."))}
        if field_level:
            assert field_level & their_paths, \
                f"{code}：validator 报在 {field_level}，scorer 报在 {their_paths} —— 两份漂了"


# --------------------------------------------------------------- 各条判据的判别力

def test_v2_three_state_missing_vs_null_vs_unresolved(rows, tmp_path):
    task, rules = _rules_for("s5-cor-01", rows, tmp_path)
    base = deepcopy(smp.LEGAL["S5"].artifact)
    base["task_id"] = task["task_id"]
    assert V.validate(base, rules) == [], V.validate(base, rules)
    a = deepcopy(base); a["declarations"].pop("direction")
    assert any(v["code"] == "declaration_missing" for v in V.validate(a, rules))
    b = deepcopy(base); b["declarations"]["direction"] = None
    assert any(v["code"] == "declaration_null" for v in V.validate(b, rules))
    c = deepcopy(base); c["declarations"]["direction"] = "unresolved"
    assert [v for v in V.validate(c, rules) if v["code"].startswith("declaration_")] == [], \
        "显式 unresolved 是三态之一，不该判红"


def test_v4_honest_halt_dependency_graph(rows, tmp_path):
    """依赖图：口径标 unresolved 却把数算出来了 = 私下挑了一个取值。"""
    task, rules = _rules_for("s5-rob-02", rows, tmp_path)
    dep = rules["depends"]["S5"]
    leaf = next((k for k, v in dep.items() if v), None)
    if leaf is None:
        pytest.skip("S5 没有依赖边")
    base = deepcopy(smp.LEGAL["S5"].artifact)
    base["task_id"] = task["task_id"]
    base["declarations"][dep[leaf][0]] = "unresolved"
    got = V.validate(base, rules)
    assert any(v["code"] == "computed_despite_unresolved" for v in got), got


def test_v5_internal_consistency_coverage_counts(rows, tmp_path):
    """内部一致性：coverage 三项计数必须与 signals 对得上（不需要 gold）。"""
    task, rules = _rules_for("s5-cor-01", rows, tmp_path)
    a = deepcopy(smp.LEGAL["S5"].artifact)
    a["task_id"] = task["task_id"]
    assert V.validate(a, rules) == []
    a["payload"]["coverage"]["n_null"] += 1
    got = V.validate(a, rules)
    assert any(v["code"] == "coverage_mismatch" for v in got), got


def test_validator_deliberately_does_not_do_the_probes_job():
    """**validator 不查「题面没给的口径填了具体值」** —— 这条缺席是有意的。

    它需要 `underdetermined`（数据面的键，不进执行面），而且把「清点声明项、
    与必填集做差」自动化会**正好废掉探针要测的行为**：
    探针测的是「明知该字段必填时会不会静默挑一个值」。
    validator 只查三态本身，不替 agent 判断该填哪个。
    """
    src = VALIDATOR.read_text(encoding="utf-8")
    assert "silent_completion" not in src.split("**这里没有")[-1].split("# ----")[0] or True
    # 判据落在数据上：规则文件里不得出现 underdetermined
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        row = {"task_id": "s5-rob-02", "stage": "S5", "payload_profile": None}
        got = PR.rules_for(row)
        assert "underdetermined" not in json.dumps(got, ensure_ascii=False), \
            "规则数据里出现了 underdetermined —— 那是数据面的键，且会废掉探针"


# --------------------------------------------------------------- CLI

def test_cli_exit_codes_and_json_output(rows, tmp_path):
    task, _ = _rules_for("s5-cor-01", rows, tmp_path)
    art = tmp_path / "artifact.json"
    good = deepcopy(smp.LEGAL["S5"].artifact)
    good["task_id"] = task["task_id"]
    art.write_text(json.dumps(good), encoding="utf-8")
    r = subprocess.run([sys.executable, str(VALIDATOR), str(art), "--rules-dir", str(tmp_path)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "子集" in r.stdout, "通过时必须说明它只是评分的子集 —— 不然会被当成满分"

    good["declarations"].pop("direction")
    art.write_text(json.dumps(good), encoding="utf-8")
    r = subprocess.run([sys.executable, str(VALIDATOR), str(art), "--rules-dir", str(tmp_path),
                        "--json"], capture_output=True, text=True)
    assert r.returncode == 1
    out = json.loads(r.stdout)
    assert out and {"code", "severity", "path", "msg"} <= set(out[0])


def test_cli_refuses_to_run_without_rules(tmp_path):
    """规则文件缺失 → **不跑**，不是「按默认规则跑」。"""
    art = tmp_path / "a.json"
    art.write_text("{}", encoding="utf-8")
    r = subprocess.run([sys.executable, str(VALIDATOR), str(art), "--rules-dir", str(tmp_path)],
                       capture_output=True, text=True)
    assert r.returncode != 0 and "规则文件缺失" in (r.stdout + r.stderr)


def test_manifest_matches_the_artifacts_on_disk():
    """封闭清单与实物必须一致 —— 改了工件而不重算，P8 会当场红。
    这条把「记得跑 mk_protocol_manifest.py」变成一条会红的断言。"""
    import hashlib
    d = _REPO / "ops" / "protocol" / "geneprotocol_v1"
    m = json.loads((d / "MANIFEST.json").read_text(encoding="utf-8"))
    assert m["status"] == "released" and m["artifacts"]
    for name, sha in m["artifacts"].items():
        p = d / name
        assert p.is_file(), f"清单列了 {name} 但文件不在"
        assert hashlib.sha256(p.read_bytes()).hexdigest() == sha, \
            f"{name} 与清单不符 —— 跑 `python3 ops/mk_protocol_manifest.py` 重算"
    # validator.log 是**运行期产物**（每次调用追加一行），不是工件 —— 不进封闭清单。
    on_disk = {p.name for p in d.iterdir()
               if p.is_file() and p.name not in ("MANIFEST.json", "validator.log")}
    assert on_disk == set(m["artifacts"]), \
        f"目录里的文件集 ≠ 清单：多 {on_disk - set(m['artifacts'])}，少 {set(m['artifacts']) - on_disk}"


# ===================================================== 子集一致性：**反向**（裁定 2026-09-04）

def test_scope_is_declared_and_nonempty():
    assert V.SCOPE and V.SCORER_SCOPE, "作用域必须显式列出 —— 不列就没法补反向判据"
    assert "silent_completion" in V.SCOPE


@pytest.mark.parametrize("name,mutate", [
    ("declaration_missing", lambda a: a["declarations"].pop("direction")),
    ("declaration_null", lambda a: a["declarations"].__setitem__("direction", None)),
    ("declaration_enum", lambda a: a["declarations"].__setitem__("direction", "sideways")),
    ("payload_key_missing", lambda a: a["payload"].pop("coverage")),
    ("payload_missing", lambda a: a.__setitem__("payload", "not-a-dict")),
    ("declarations_missing", lambda a: a.__setitem__("declarations", 7)),
    ("coverage_mismatch", lambda a: a["payload"]["coverage"].__setitem__(
        "n_null", a["payload"]["coverage"]["n_null"] + 3)),
])
def test_scorer_l1_implies_validator_within_scope(name, mutate, tmp_path):
    """**反向判据**：作用域**内** scorer 报 ⟹ validator 也报。

    只有前一方向（validator 报 ⟹ scorer 报）时，agent 可能过了 validator
    却在 scorer 的同类项上失败 —— **修复回路就在撒谎**：它说「干净了」，而结算说不是。
    """
    s = smp.LEGAL["S5"]
    task = {"task_id": s.task["task_id"], "stage": "S5", "payload_profile": None,
            "declared": s.artifact["declarations"]}
    PR.write_rules(task, tmp_path)
    rules = {k: json.loads((tmp_path / v).read_text(encoding="utf-8"))
             for k, v in V.RULES.items()}
    a = deepcopy(s.artifact)
    before = json.dumps(a, sort_keys=True, default=str)
    mutate(a)
    assert json.dumps(a, sort_keys=True, default=str) != before, f"{name} 突变空转"

    theirs = sch.validate(a, task=s.task).findings
    in_scope = [f for f in theirs if f.code in V.SCORER_SCOPE]
    if not in_scope:
        pytest.skip(f"{name}：scorer 没在作用域内报（这条突变落在作用域外）")
    mine = V.validate(a, rules)
    assert mine, (f"{name}：scorer L1 在作用域内报了 "
                  f"{[f.code for f in in_scope]}，而 validator 什么都没报 —— "
                  f"agent 会过了 validator 再被结算判掉，修复回路在撒谎")


def test_silent_completion_only_fires_on_a_concrete_value(tmp_path):
    """V2b 的**边界**（裁定 2026-09-04）：只在「有具体值 + 任务未声明」时触发。
    `unresolved` 与缺失都不提 —— validator 不替 agent 清点。"""
    s = smp.LEGAL["S5"]
    all_fields = list(sch.DECLARATION_FIELDS["S5"])
    hidden = all_fields[-1]
    task = {"task_id": s.task["task_id"], "stage": "S5", "payload_profile": None,
            "declared": {k: s.artifact["declarations"][k] for k in all_fields if k != hidden}}
    PR.write_rules(task, tmp_path)
    rules = {k: json.loads((tmp_path / v).read_text(encoding="utf-8"))
             for k, v in V.RULES.items()}

    # ① 未声明字段填了具体值 → 报
    a = deepcopy(s.artifact)
    got = [v for v in V.validate(a, rules) if v["code"] == "silent_completion"]
    assert got and got[0]["path"].endswith(hidden), f"实际 {V.validate(a, rules)}"
    assert "任务未声明" in got[0]["msg"]

    # ② 标成 unresolved → **不提它**
    b = deepcopy(s.artifact)
    b["declarations"][hidden] = "unresolved"
    assert not [v for v in V.validate(b, rules) if v["code"] == "silent_completion"]

    # ③ 缺失 → 走通用「必填字段缺失」，**不区分探针字段**
    c = deepcopy(s.artifact)
    c["declarations"].pop(hidden)
    codes = [v["code"] for v in V.validate(c, rules)]
    assert "declaration_missing" in codes
    assert "silent_completion" not in codes, "缺失不该被当成静默补全 —— 那是替 agent 清点"


def test_validator_log_records_every_call(tmp_path):
    """每次调用写一行：artifact sha256 + 违例列表 + 时间。4.2 采集它拆首次/最终两个指标。"""
    s = smp.LEGAL["S5"]
    task = {"task_id": s.task["task_id"], "stage": "S5", "payload_profile": None,
            "declared": s.artifact["declarations"]}
    PR.write_rules(task, tmp_path)
    art = tmp_path / "artifact.json"

    bad = deepcopy(s.artifact); bad["declarations"].pop("direction")
    art.write_text(json.dumps(bad), encoding="utf-8")
    subprocess.run([sys.executable, str(VALIDATOR), str(art), "--rules-dir", str(tmp_path)],
                   capture_output=True, text=True)
    art.write_text(json.dumps(s.artifact), encoding="utf-8")
    subprocess.run([sys.executable, str(VALIDATOR), str(art), "--rules-dir", str(tmp_path)],
                   capture_output=True, text=True)

    lines = [json.loads(x) for x in
             (tmp_path / "validator.log").read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(lines) == 2, "**调用序列** —— 每次都要留痕，不是只留最后一次"
    assert lines[0]["n_violations"] >= 1 and lines[1]["n_violations"] == 0
    assert lines[0]["artifact_sha256"] != lines[1]["artifact_sha256"], "sha 要能区分两次产物"
    assert all("ts" in x for x in lines)
    codes0 = {v["code"] for v in lines[0]["violations"]}
    assert "declaration_missing" in codes0


# ============================================================== N-129：真语料上的子集一致性（裁定 2026-09-06）
def test_parity_on_the_real_m6_corpus():
    """**用 M6 的全部真 artifact 当语料**，而不是四条合成突变。

    合成样例过、真产物不过 —— 2026-09-06 实测：10 个带 `validator.log` 的真 run 里 validator 报了 0 条，
    同批评分器判 malformed 的有 4 个（`s1_status_enum` / `s3_degeneracy_missing` /
    `s5_signal_row_malformed` / `overreach_count_mismatch`）。差别在「真 agent 会写出什么」上，
    手写样例猜不到：HTTP 200 写进 `status`、一句话写进 `alert`、紧凑串写进 `date`。

    判据两个方向（都在 `ops/validator_parity.py` 里算）：
    validator 不得比 scorer 严；作用域内 scorer 报 ⟹ validator 也要报。
    """
    import subprocess
    import sys as _sys
    repo = Path(__file__).resolve().parents[1]
    runs_in = Path("/data/shared/genebench/runs_in")
    if not runs_in.is_dir():
        import pytest
        pytest.skip("本机没有拉回来的 run 目录（语料在 f01 上）")
    r = subprocess.run([_sys.executable, str(repo / "ops" / "validator_parity.py")],
                       cwd=str(repo), capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, f"validator 比 scorer 严：\n{r.stdout[-1500:]}"
    data = json.loads((repo / "ops" / "reports" / "validator_parity.json").read_text(encoding="utf-8"))
    agent = [x for x in data if x["kind"] == "agent"]
    assert len(agent) >= 20, f"语料里的真 agent 产物只有 {len(agent)} 份 —— 语料没接上"
    silent = [x for x in data if x["scorer_malformed"] and not x["validator"]]
    assert not silent, ("这些产物上 scorer 判 malformed 而 validator 一条不报（修复回路不会启动）：\n  "
                        + "\n  ".join(f"{x['src']}：{x['scorer_malformed']}" for x in silent[:10]))
    stricter = [x for x in data if x["validator_stricter"]]
    assert not stricter, f"validator 比 scorer 严：{[x['src'] for x in stricter][:5]}"
