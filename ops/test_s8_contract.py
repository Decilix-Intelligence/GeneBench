# -*- coding: utf-8 -*-
"""卡 A ⑧：S8 契约常量抽成零 `reference` 依赖的模块之后，**那条边真的断了吗**。

这个文件要回答的不是「常量还在不在」，是三件事：

1. **网关一条 `import reference` 都不许再有** —— 用 AST，不 grep 字符串。
   `gateway/sim_engine.py` 的注释里现在还写着「原先这一行是全树唯一一条网关 import reference」，
   grep 会把那句解释判红，逼下一个人把理由删掉（`ops/test_budget_tiers.py::
   test_registry_does_not_import_reference` 的同一条论证，写法也照抄它）。
2. **值逐字节没变** —— 搬家不是改协议。改前的快照钉死在这里。
3. **只有一份** —— `reference` 与 `gateway` 拿到的必须是**同一个对象**，不是两份相等的。
   相等只在今天成立；同一个对象在明天也成立。
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from genetask import s8_contract as C                   # noqa: E402

#: 搬家**之前**在 f01 上现算的三个常量（2026-09-10，`ops/reports/s8_contract_parity.txt`）。
#: 写死在测试里而不是从任一侧读：从被测方读回来再比，比的是它自己（F7）。
FROZEN = {
    "LEGAL_TRANSITIONS": [["cancelled", "idle"], ["filled", "idle"], ["idle", "ordered"],
                          ["ordered", "cancelled"], ["ordered", "filled"], ["ordered", "partial"],
                          ["partial", "cancelled"], ["partial", "filled"]],
    "TRADABILITY_STATES": ["no_data", "suspend", "trade"],
    "UNTRADABLE_STATES": ["no_data", "suspend"],
}
FROZEN_SHA256 = "315a9ba4fa860b7cb53b4c8f57c4606f8e1efedfcfd187191cebbe4a1f365dba"
NAMES = tuple(sorted(FROZEN))


def _imported_modules(path: Path) -> set[str]:
    mods: set[str] = set()
    for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(n, ast.Import):
            mods |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            mods.add(n.module)
    return mods


# ------------------------------------------------------------------ ① 那条边断了

GATEWAY_PY = sorted(p for p in (_REPO / "gateway").rglob("*.py"))


def test_there_is_something_to_check():
    """遍历为空时上面那条会**恒绿**。先证明确实扫到了东西。"""
    assert len(GATEWAY_PY) >= 3, [str(p) for p in GATEWAY_PY]


@pytest.mark.parametrize("path", GATEWAY_PY, ids=lambda p: str(p.relative_to(_REPO)))
def test_gateway_does_not_import_the_answer_plane(path):
    """红线 B2：`reference/` 不上执行面。单机双容器形态里网关与 harness 同机起 ——
    带着 `import reference` 的网关在那里**根本 import 不起来**。"""
    bad = sorted(m for m in _imported_modules(path)
                 if m == "reference" or m.startswith("reference."))
    assert not bad, f"{path.relative_to(_REPO)} import 了答案面模块 {bad}"


def test_the_contract_module_is_zero_dependency():
    """契约模块自己也不许把 `reference/` 或 `genetask.schema` 拖回来 ——
    后者顶层 `from reference import artifact_schema`，import 它等于原样拖回。"""
    mods = _imported_modules(_REPO / "genetask" / "s8_contract.py")
    bad = sorted(m for m in mods
                 if m == "reference" or m.startswith("reference.")
                 or m in ("genetask.schema", "gateway") or m.startswith("gateway."))
    assert not bad, f"契约模块 import 了 {bad} —— 它必须是零依赖的"


def test_importing_the_engine_really_loads_no_reference_module():
    """AST 只看静态 import。这一条在**干净子进程**里真 import 一次引擎，
    数 `sys.modules` 里有几个 `reference.*` —— 惰性 import 与传递依赖只有这样才抓得到。"""
    code = ("import sys; sys.path.insert(0, %r);"
            "import gateway.sim_engine;"
            "print(sorted(m for m in sys.modules if m.split('.')[0] == 'reference'))" % str(_REPO))
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         cwd=str(_REPO), timeout=300)
    assert out.returncode == 0, out.stderr[-2000:]
    assert out.stdout.strip() == "[]", f"引擎把这些答案面模块拖进来了：{out.stdout.strip()}"


# ------------------------------------------------------------------ ② 值没变

def _norm(x):
    return sorted([list(i) if isinstance(i, tuple) else i for i in x])


@pytest.mark.parametrize("name", NAMES)
def test_the_constant_is_byte_for_byte_what_it_was(name):
    assert _norm(getattr(C, name)) == FROZEN[name]


def test_the_three_together_hash_to_the_recorded_snapshot():
    """逐个比过了还比一次合起来的 sha —— 它是重冻记因里引用的那个数，
    改任何一个都会让它变，而记因里那句「值逐字节不变」就不再成立。"""
    import hashlib
    blob = json.dumps({n: _norm(getattr(C, n)) for n in NAMES},
                      ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(blob.encode()).hexdigest() == FROZEN_SHA256


# ------------------------------------------------------------------ ③ 只有一份

@pytest.mark.parametrize("name", NAMES)
def test_both_sides_hold_the_same_object_not_two_equal_copies(name):
    """`is`，不是 `==`。两份相等的常量今天绿、漂开的那天也不会红 ——
    `gateway/sim_engine.py` 的模块 docstring 说的就是这个失败形态。"""
    from reference import artifact_schema as A
    from gateway import sim_engine as E
    src = getattr(C, name)
    assert getattr(A, name) is src, f"reference 侧的 {name} 不是契约模块那一份"
    if hasattr(E, name):
        assert getattr(E, name) is src, f"网关侧的 {name} 不是契约模块那一份"


def test_the_contract_module_is_the_only_definition():
    """全树只许有一处 `NAME: frozenset… =` 的赋值。再出现第二处就是又抄了一份 ——
    而抄第二份正是这次搬家要消灭的东西。"""
    roots = ("gateway", "genetask", "reference", "runner", "scorer")
    hits: dict[str, list[str]] = {n: [] for n in NAMES}
    for r in roots:
        for p in sorted((_REPO / r).rglob("*.py")):
            for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
                tgts = ([node.target] if isinstance(node, ast.AnnAssign) else
                        list(node.targets) if isinstance(node, ast.Assign) else [])
                for t in tgts:
                    if isinstance(t, ast.Name) and t.id in hits:
                        hits[t.id].append(str(p.relative_to(_REPO)))
    for n in NAMES:
        assert hits[n] == ["genetask/s8_contract.py"], f"{n} 的定义出现在 {hits[n]}"


# ------------------------------------------------------------------ ④ 语义还自洽

def test_the_state_machine_is_still_coherent():
    from gateway import sim_engine as E
    assert E.ORDER_STATES == frozenset(s for pair in C.LEGAL_TRANSITIONS for s in pair)
    assert E.V1_UNREACHABLE <= E.ORDER_STATES
    assert C.UNTRADABLE_STATES == C.TRADABILITY_STATES - {"trade"}
    assert "trade" not in C.UNTRADABLE_STATES


def test_the_schema_enum_still_derives_from_the_transition_table():
    """`$.payload.*.state` 的枚举是从 `LEGAL_TRANSITIONS` 的节点集导出的。
    搬家之后要是变成了别的来源，这里会红。"""
    from reference import artifact_schema as A
    want = sorted({s for pair in C.LEGAL_TRANSITIONS for s in pair})
    blob = json.dumps(A.json_schema("S8"), ensure_ascii=False, sort_keys=True)
    needle = json.dumps(want, ensure_ascii=False)
    assert needle in blob, f"S8 的 JSON Schema 里找不到由迁移表导出的 state 枚举 {want}"
    # **反向对照**：这条断言是「某个串在一大团 JSON 里」——很容易在重构后变成恒真。
    # 多一个不存在的状态就必须找不到，否则说明上面那句什么也没证明。
    assert json.dumps(sorted(want + ["zzz_not_a_state"]), ensure_ascii=False) not in blob
