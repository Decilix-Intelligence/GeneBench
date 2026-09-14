# -*- coding: utf-8 -*-
"""**每一个探针族都必须有人能让它响**（线 C / C1，2026-09-05）。

`PROBE_IDS` 有 16 个族。审计发现其中 **3 个在全仓库里没有任何发出点** ——
`Verdict.add(..., probe=X)` 一次都不会带上它们。也就是说：这三族**恒绿**，
主表上它们永远是 clean，而 clean 的原因不是「没违例」，是**没人检**。

**恒绿的门与恒红的一样会被绕过**（F7 的镜像面）。所以这里把状态写成表：
一个族要么有发出点，要么在 `NO_EMITTER_YET` 里**具名登记**并写清被什么挡着。
新增一个族却忘了实现，这条会当场红；实现了却忘了从表里删，`test_pending_is_not_stale` 会红。
"""
from __future__ import annotations

import ast
import collections
import json
from pathlib import Path

from reference.artifact_schema import PROBE_IDS

REPO = Path(__file__).resolve().parents[1]
_EMIT_CALLS = ("add", "mark_unobservable")

#: **还没有发出点**的探针族，逐条写清被什么挡着。理由必须能被证伪。
#: 2026-09-06：`lookahead` **已接发出点**（`artifact_schema._lookahead`：日志切片里
#: `reason ∈ LOOKAHEAD_DENY_REASONS` 的 deny → 违例 → 闸门）。它从这张表与
#: `DIRECTION_UNVERIFIED` 里一并删掉 —— 留着就是一条**从不触发**的豁免，与死白名单同族。
#: 数据面结算读本机 access_log，所以「跨机取回未定（T-13）」只影响 f02 侧的可检性，不影响它有没有发出点。
NO_EMITTER_YET: dict[str, str] = {
    "pit_universe":
        "需要 PIT 成分视图与 artifact 里的标的清单对照；卡 2.5 的公开通道刚把 "
        "index_weight 这条依赖核实完（N-58），实现归后续。**当前没有任何发出点。**",
    "input_ablation":
        "按定义需要**第二次运行**（消融输入后重跑）才谈得上比较，"
        "属于实验设计范畴 —— 归 M7 审定之后，不在 v1 的单次运行里实现。",
}


#: **第三列**：方向还没证的族，逐条写清缺哪一半（D-30）。
#: 两半是「诚实 oracle 上零 finding」+「特定错误产物上有 finding」。
DIRECTION_UNVERIFIED: dict[str, str] = {
    # 2026-09-05 收敛：其余各族的方向由**逐族破坏样本**证（`ops/reports/m6/mutations.md`：
    # 取该题自己的 oracle 产物只破坏一处，该族响、其余不响）。剩下这三族**没有发出点**，
    # 谈不上方向 —— 与 `NO_EMITTER_YET` 同一批，理由写在那里。
    "pit_universe": "没有发出点（见 NO_EMITTER_YET），谈不上方向",
    "input_ablation": "按定义要第二次运行，归 M7 —— 两半都还没有",
}

_REPORTS = REPO / "ops" / "reports"


def _matrix(agent: str) -> dict[str, dict[str, int]] | None:
    """读某次跑批的**探针族 × 题目**计数。跑批没跑过 → `None`（不可得）。

    `None` 与「跑过且全零」是两回事 —— 前者不能拿来证明任何方向。
    """
    f = _REPORTS / f"probe_run_{agent}.json"
    if not f.is_file():
        return None
    rows = json.loads(f.read_text(encoding="utf-8"))
    return {r["task_id"]: dict(r.get("probes") or {}) for r in rows}


def _mutation_hits() -> set[str]:
    """逐族破坏样本里**该族响、其余不响**的那些族（`ops/run_probe_mutations.py` 的产物）。

    裁定 2026-09-05：方向的第二半由**破坏样本**证 —— f1 填充器只针对静默补全那一族，
    拿它去要求「每族在其适用题上非零」，等于要求一个够不着的判据。
    """
    p = REPO / "ops" / "reports" / "m6" / "mutations.json"
    if not p.is_file():
        return set()
    return {r["probe"] for r in json.loads(p.read_text(encoding="utf-8")) if r.get("ok")}


def _direction_verified() -> tuple[set[str], str]:
    """两半都成立的族：oracle 上零命中（不误伤）+ **在错误产物上命中**（方向对）。

    第二半接受两种证据：f1 矩阵（只覆盖静默补全族）**或**逐族破坏样本。
    """
    o, f1 = _matrix("oracle"), _matrix("f1")
    if o is None or f1 is None:
        missing = [n for n, m in (("oracle", o), ("f1", f1)) if m is None]
        return set(), f"缺矩阵：{missing} —— 没跑过就不能算已证"
    mut = _mutation_hits()
    ok = set()
    for fam in PROBE_IDS:
        zero_on_oracle = not any(c.get(fam) for c in o.values())
        fires = any(c.get(fam) for c in f1.values()) or fam in mut
        if zero_on_oracle and fires:
            ok.add(fam)
    return ok, f"oracle {len(o)} 题 / f1 {len(f1)} 题 / 破坏样本 {len(mut)} 族"


def _emitters() -> dict[str, list[str]]:
    """AST 扫全树：哪些族真的会被发出。**不用文本 grep** —— 规格散文里到处是族名。"""
    out: dict[str, list[str]] = collections.defaultdict(list)
    for f in sorted(REPO.rglob("*.py")):
        rel = str(f.relative_to(REPO))
        if rel.startswith((".git/", "ops/test_")):
            continue
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"), filename=rel)
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            fn = n.func
            name = fn.attr if isinstance(fn, ast.Attribute) else (fn.id if isinstance(fn, ast.Name) else "")
            if name not in _EMIT_CALLS:
                continue
            consts = [a.value for a in n.args if isinstance(a, ast.Constant)]
            consts += [k.value.value for k in n.keywords
                       if k.arg == "probe" and isinstance(k.value, ast.Constant)]
            for c in consts:
                if isinstance(c, str) and c in PROBE_IDS:
                    out[c].append(f"{rel}:{n.lineno}")
    return out


def test_every_probe_family_can_fire_or_is_registered_as_pending():
    emit = _emitters()
    assert emit, "一个发出点都没扫到 —— 扫描器坏了，这条会变成恒绿"
    silent = sorted(p for p in PROBE_IDS if not emit.get(p))
    unregistered = [p for p in silent if p not in NO_EMITTER_YET]
    assert not unregistered, (
        f"这些探针族在全仓库里**没有任何发出点**，也没登记：{unregistered}。"
        f"它们在主表上永远 clean，而 clean 的原因是没人检 —— "
        f"要么实现，要么写进 NO_EMITTER_YET 并说明被什么挡着")


def test_pending_registry_is_not_stale():
    """登记表不能变成僵尸：已经有发出点的族必须从表里删掉。"""
    emit = _emitters()
    stale = sorted(p for p in NO_EMITTER_YET if emit.get(p))
    assert not stale, f"{stale} 已经有发出点了，把它们从 NO_EMITTER_YET 里删掉"


def test_pending_names_are_real_probe_families():
    unknown = sorted(set(NO_EMITTER_YET) - set(PROBE_IDS))
    assert not unknown, f"NO_EMITTER_YET 里有不存在的族名：{unknown}"


def test_pending_reasons_name_what_blocks_them():
    """理由要能被证伪 —— 说不出被什么挡着的条目会永远留着（D-23）。"""
    for p, why in NO_EMITTER_YET.items():
        assert len(why) > 30, f"{p} 的理由太短，说不出被什么挡着：{why!r}"


def test_the_audit_itself_is_discriminating():
    """判别力：喂一段真的带 probe 参数的源码，AST 判据必须认出来。"""
    src = ('v.add("X", "violation", "/p", "m", probe="calendar")\n'
           'v.mark_unobservable("lookahead", "why")\n')
    found = set()
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Call):
            fn = n.func
            name = fn.attr if isinstance(fn, ast.Attribute) else ""
            if name in _EMIT_CALLS:
                found |= {a.value for a in n.args if isinstance(a, ast.Constant) and a.value in PROBE_IDS}
                found |= {k.value.value for k in n.keywords
                          if k.arg == "probe" and isinstance(k.value, ast.Constant)}
    assert found == {"calendar", "lookahead"}, found


# ---------------------------------------------------------------- 第三列：方向（D-30）
def test_direction_is_verified_or_registered():
    """**每族要么方向已证，要么具名登记缺哪一半。**

    两半：诚实 oracle 上零 finding（不误伤）+ 特定错误产物上有 finding（方向对）。
    「有发出点」「测试里提到过族名」都是必要非充分 —— `source_status` 两样都占，
    方向却是反的（实测 601 条假违例）。
    """
    verified, why = _direction_verified()
    unverified = sorted(set(PROBE_IDS) - verified)
    unregistered = [f for f in unverified if f not in DIRECTION_UNVERIFIED]
    assert not unregistered, (
        f"这些族的方向没证、也没登记：{unregistered}（{why}）。"
        f"要么把两张矩阵跑出来，要么写进 DIRECTION_UNVERIFIED 并说明缺哪一半")


def test_direction_registry_is_not_stale():
    verified, _ = _direction_verified()
    stale = sorted(f for f in DIRECTION_UNVERIFIED if f in verified)
    assert not stale, f"{stale} 的方向已经证了，从 DIRECTION_UNVERIFIED 里删掉"


def test_direction_registry_names_the_missing_half():
    for f, why in DIRECTION_UNVERIFIED.items():
        assert f in PROBE_IDS, f"不存在的族名：{f}"
        assert len(why) > 15, f"{f} 的理由说不出缺哪一半：{why!r}"


def test_matrix_absence_is_not_verification():
    """**判别力**：矩阵不存在时，一个族都不许算「已证」。

    这条防的是「跑批还没跑，覆盖表却全绿」—— 那正是 D-30 要消灭的形态。
    """
    import unittest.mock as _m
    with _m.patch.object(__import__(__name__, fromlist=["_matrix"]), "_matrix",
                         lambda agent: None):
        verified, why = _direction_verified()
    assert verified == set() and "缺矩阵" in why


def test_the_silent_families_are_exactly_the_ones_we_know_about():
    """把「今天有几个族是哑的」钉成一个数：多一个少一个都要有人解释。

    2026-09-06：`lookahead` 接了发出点（`artifact_schema._lookahead`），哑族从 3 个变 2 个。
    **数字写在断言里而不是标题里** —— 标题里的数字改起来没人拦，断言会。
    """
    emit = _emitters()
    silent = sorted(p for p in PROBE_IDS if not emit.get(p))
    assert silent == sorted(NO_EMITTER_YET), (
        f"哑族集合变了：现在是 {silent}，登记的是 {sorted(NO_EMITTER_YET)}")
    assert len(PROBE_IDS) == 16 and len(silent) == 2, "哑族数量变了：改之前先说清哪一族接上了/掉了"
