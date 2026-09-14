# -*- coding: utf-8 -*-
"""卡 4.3：**按阶段的预算档**（S7 300 / S4 150 / 其余默认 100）。

判三件事，每件对应一个真实的失败模式：

1. **档位真的走到 compose 里。** 只在源码里 grep 一个常量名不算 —— 那证明不了渲染时
   用的是它。这里造三份真 bundle（S2 / S4 / S7）走一遍注入器，读 run dir 里落下来的
   `compose.yml`。接错了的表现是：真跑照样起来、agent 在第 100 次调用停住、`llm_log`
   尾部一片 `budget_exceeded`、分数照出 —— **这个失败长得像结论**，没有任何东西会红。
2. **显式参数仍然赢过档位。** `ops/run_f02_a1.py --max-calls/--max-tokens` 是就地改
   `REG.RUN_BUDGET`；档位不能把人显式给的值吃掉，否则「我给了 --max-tokens 3000000」
   会变成一句空话，而现场看不出来。
3. **手册里的数字与档位表逐字一致。** 手册是外部接入方唯一会读的东西；两处漂开的
   表现是「照手册配的人配了一个不存在的闸」。

`import` 面：本文件跑在 f01（它 import `genetask.packager`，那是答案面）。被测的
`runner/registry.py` 自己**不许** import `reference/` —— 阶段名在 registry 里另抄一份，
`test_stage_names_do_not_drift_from_the_schema` 盯着两处不漂。
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from genetask import packager as P                   # noqa: E402
from genetask import pin                             # noqa: E402
from runner import inject as INJ                     # noqa: E402
from runner import registry as REG                   # noqa: E402

ALL_CAPS = {"n33_bars_open_amount_vwap": True, "s8_state_endpoint": True,
            "anchor_ladder_54": False}
PARAMS40 = _REPO / "genetask" / "params" / "v1.0-smoke40.yaml"

#: 三道题各代表一档：S2 走默认档、S4 与 S7 各有自己的档。
#: **必须是三个不同的档**，否则「按 stage 取」和「写死一个数」这两种实现都能过。
CASES = {"s2-cor-01": "S2", "s4-cor-01": "S4", "s7-cor-01": "S7"}


# --------------------------------------------------------------- fixtures
# 与 ops/test_inject.py 同一套造 bundle 的手法。**故意复制而不是 import 它** ——
# 跨测试文件共享 fixture 会让「别人改了他那份 fixture」变成本文件的红。

@pytest.fixture(scope="module")
def rows():
    return P.load_params(PARAMS40)


@pytest.fixture(scope="module")
def bundles(tmp_path_factory, rows):
    """三道题各一份真 bundle + 通行证（f01 侧全流程）。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("_fz43", _REPO / "ops" / "freeze_v10.py")
    fz = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fz)

    root = tmp_path_factory.mktemp("f01-budget")
    out = {}
    for tid in CASES:
        row = next(r for r in rows if r["task_id"] == tid)
        b = P.build_task(row, capabilities=ALL_CAPS)
        assert b.ok, (tid, b.problems)
        task_dir = P.write_task(b, root / tid / "reference", capabilities=ALL_CAPS)
        bundle = P.export_task(task_dir, root / tid / "runner")
        assert P.pin_image_digest(bundle, "sha256:" + "a" * 64) == []
        ce = P.check_export(bundle, P.gold_sha_set(task_dir), b.task["canary"])
        assert ce == [], (tid, ce)
        man = P.export_manifest(task_dir, bundle, check_export_result=ce,
                                frozen_ref=fz.frozen_ref())
        out[tid] = {"bundle": bundle, "manifest": man, "frozen_root": fz.frozen_ref()["root"]}
    return out


def _write_filelist(root: Path) -> None:
    lines = []
    for f in sorted(root.rglob("*")):
        if not f.is_file() or f.name in ("files.sha256", "manifest.json"):
            continue
        b = f.read_bytes()
        lines.append(f"{hashlib.sha256(b).hexdigest()}  {len(b)}  {f.relative_to(root)}")
    (root / "files.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture
def provider(tmp_path):
    d = tmp_path / "provider"
    (d / "calendars").mkdir(parents=True)
    (d / "calendars" / "day.txt").write_text("2026-07-01\n2026-07-02\n", encoding="utf-8")
    (d / "instruments").mkdir()
    (d / "instruments" / "csi300.txt").write_text("SH600000\t2026-01-01\t2026-12-31\n",
                                                  encoding="utf-8")
    _write_filelist(d)
    return d


def _compose_for(bundles, provider, monkeypatch, tmp_path, tid: str) -> str:
    """注入一臂（`open`：不需要协议工件），返回落盘的 compose 文本。"""
    monkeypatch.setattr(pin, "PROVIDER_SHA256_ROOT", pin.provider_root_sha256(provider))
    e = bundles[tid]
    r = INJ.inject(e["bundle"], "open", run_root=tmp_path / f"rr-{tid}",
                   provider_root=provider, config_id="cfg-a",
                   model_upstream="",          # 测注入机制，不起模型反代
                   manifest=e["manifest"], expect_frozen_root=e["frozen_root"],
                   command='sh -c "true"', require_docker=False, check_modes=False)
    return (r.run_dir / "compose.yml").read_text(encoding="utf-8")


def _budget_in(text: str) -> tuple[int, int]:
    calls = re.search(r"--max-calls\s+(\d+)", text)
    tokens = re.search(r"--max-tokens\s+(\d+)", text)
    assert calls and tokens, f"compose 里没有预算闸参数：\n{text[:600]}"
    return int(calls.group(1)), int(tokens.group(1))


# --------------------------------------------------------------- ① 档位进 compose

@pytest.mark.parametrize("tid", sorted(CASES))
def test_the_tier_reaches_the_compose_that_actually_runs(bundles, provider, monkeypatch,
                                                         tmp_path, tid):
    """S7 的题注出来的 compose 里必须是 300，S4 是 150，S2 是默认的 100。

    这条是本卡唯一的**行为**判据：它走的是真 bundle → 真注入器 → 真 compose 文件。
    """
    stage = CASES[tid]
    want = REG.budget_for(stage)
    got_calls, got_tokens = _budget_in(_compose_for(bundles, provider, monkeypatch,
                                                    tmp_path, tid))
    assert (got_calls, got_tokens) == (want["max_calls"], want["max_tokens"]), (
        f"{tid}（{stage}）注出来的 compose 预算是 {got_calls} 次 / {got_tokens} tokens，"
        f"档位表说的是 {want} —— 档位没走到真正会跑的那份文件里")


def test_the_three_cases_are_actually_three_different_tiers():
    """三道题必须落在三个不同的档 —— 否则「写死一个数」也能过上面那条。"""
    got = {s: REG.budget_for(s)["max_calls"] for s in CASES.values()}
    assert got == {"S2": 100, "S4": 150, "S7": 300}, got


def test_stage_is_read_from_the_bundles_own_task_yaml(bundles):
    """档位的输入是 bundle 自己说的 `stage`，不是调用方另给的参数。"""
    import yaml
    for tid, stage in CASES.items():
        x = yaml.safe_load((bundles[tid]["bundle"] / "task.yaml").read_text(encoding="utf-8"))
        assert x["stage"] == stage, (tid, x.get("stage"))


# --------------------------------------------------------------- ② 显式覆盖

def test_an_explicit_override_still_beats_the_tier(monkeypatch):
    """`ops/run_f02_a1.py --max-calls N` 就地改 `RUN_BUDGET`；那个值必须赢过档位。

    输的话，「我给了 --max-tokens 3000000」变成一句空话，**而现场看不出来**。
    """
    monkeypatch.setitem(REG.RUN_BUDGET, "max_calls", 42)
    assert REG.budget_for("S7")["max_calls"] == 42, "显式覆盖被档位吃掉了"
    assert REG.budget_for("S4")["max_calls"] == 42
    assert REG.budget_for("S1")["max_calls"] == 42


def test_the_override_is_per_key_not_all_or_nothing(monkeypatch):
    """只给 `--max-calls` 时，`max_tokens` 仍然走档位 —— 否则给一个参数会把另一个悄悄打回默认。"""
    monkeypatch.setitem(REG.RUN_BUDGET, "max_calls", 42)
    b = REG.budget_for("S7")
    assert b == {"max_calls": 42, "max_tokens": REG.BUDGET_TIERS["S7"]["max_tokens"]}, b


def test_run_f02_a1_still_writes_into_run_budget():
    """覆盖语义靠「就地改 `RUN_BUDGET`」实现 —— 那行还在，`budget_for` 才认得出覆盖。"""
    src = (_REPO / "ops" / "run_f02_a1.py").read_text(encoding="utf-8")
    assert 'REG.RUN_BUDGET["max_calls"] = int(a.max_calls)' in src
    assert 'REG.RUN_BUDGET["max_tokens"] = int(a.max_tokens)' in src


# --------------------------------------------------------------- ③ 档位表自身

def test_default_tier_is_the_ruled_value():
    """默认档 = **裁定值**（N-388，用户 2026-09-10）：100 次 / 6,000,000 tokens。

    2026-09-10 之前这里钉的是 600,000，函数名还叫 `..._is_unchanged`。改名是有意的：
    这条断言的作用不是「别动它」，而是「动它必须是一次裁定」——
    默认档同时是 P2 契约与两份手册里到处写着的那个数，悄悄漂一次没人会发现。
    """
    assert REG.RUN_BUDGET_DEFAULT == {"max_calls": 100, "max_tokens": 6_000_000}


def test_budget_for_returns_a_copy_not_the_table():
    a = REG.budget_for("S7")
    a["max_calls"] = -1
    assert REG.BUDGET_TIERS["S7"]["max_calls"] == 300, "budget_for 把档位表交出去了"
    assert REG.budget_for("S7")["max_calls"] == 300


@pytest.mark.parametrize("stage", [None, "", "S9", "s7 ", "nonsense"])
def test_unknown_stage_falls_back_to_the_default_tier_without_raising(stage):
    """注入器跑在 f02：为一个拼错的 stage 中止注入，换来的是「真跑起不来」而不是「预算不对」。

    `"s7 "` 这条顺带钉住大小写与空白的归一 —— 它该拿到 S7 的档。
    """
    b = REG.budget_for(stage)
    if str(stage or "").strip().upper() == "S7":
        assert b == REG.BUDGET_TIERS["S7"]
    else:
        assert b == REG.RUN_BUDGET_DEFAULT


def test_sanity_gate_rejects_a_stage_name_that_does_not_exist(monkeypatch):
    """拼错的档位是**静默失效**的（`budget_for` 查不到就回默认档）。所以要在 import 期红。"""
    monkeypatch.setattr(REG, "BUDGET_TIERS", {"S9": {"max_calls": 300, "max_tokens": 18_000_000}})
    with pytest.raises(REG.RegistryError, match="S9"):
        REG.assert_registry_sane()


def test_sanity_gate_rejects_a_tier_below_the_default(monkeypatch):
    """档位只能往上抬 —— 往下压是另一件事，不能借「分档」这个名义悄悄发生。"""
    monkeypatch.setattr(REG, "BUDGET_TIERS", {"S7": {"max_calls": 50, "max_tokens": 18_000_000}})
    with pytest.raises(REG.RegistryError, match="比默认档"):
        REG.assert_registry_sane()


def test_sanity_gate_rejects_a_tier_missing_a_key(monkeypatch):
    """少一个键 = 那一项悄悄回落到默认值。"""
    monkeypatch.setattr(REG, "BUDGET_TIERS", {"S7": {"max_calls": 300}})
    with pytest.raises(REG.RegistryError, match="键集"):
        REG.assert_registry_sane()


def test_the_real_table_passes_its_own_gate():
    """恒绿的负例没有意义 —— 正例也要跑一遍。"""
    REG.assert_registry_sane()


def test_stage_names_do_not_drift_from_the_schema():
    """`registry.BUDGET_STAGES` 是**另抄的一份**（registry 不许 import reference，红线 B2）。

    抄来的东西会漂；漂了的表现是档位判据放行一个不存在的阶段名。
    这里在 f01 侧（答案面可读）逐字比对两处。
    """
    from reference import artifact_schema as sch
    assert REG.BUDGET_STAGES == sch.STAGES, (REG.BUDGET_STAGES, sch.STAGES)


def test_registry_does_not_import_reference():
    """阶段名要是哪天「顺手改成 import 过来的」，这条就红 —— 那是把答案面拖上执行面。

    只看 `import` 语句，不 grep 字符串：注释里提到 `reference` 是在**解释为什么不 import**，
    把它也判红等于逼人把理由删掉。
    """
    import ast
    tree = ast.parse((_REPO / "runner" / "registry.py").read_text(encoding="utf-8"))
    mods: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module)
    bad = sorted(m for m in mods if m == "reference" or m.startswith("reference."))
    assert not bad, f"runner/registry.py import 了答案面模块 {bad}"


# --------------------------------------------------------------- ④ 手册对齐

MANUALS = ("harnesses/README.md", "integrations/README.md")


@pytest.mark.parametrize("rel", MANUALS)
def test_the_manuals_carry_the_same_numbers_as_the_table(rel):
    """手册是外部接入方唯一会读的东西。两处漂开 = 照手册配的人配了个不存在的闸。"""
    text = (_REPO / rel).read_text(encoding="utf-8")
    assert "BUDGET_TIERS" in text, f"{rel} 没提档位表在哪"
    for stage, tier in sorted(REG.BUDGET_TIERS.items()):
        assert stage in text, f"{rel} 没写 {stage} 这一档"
        assert str(tier["max_calls"]) in text, \
            f"{rel} 没写 {stage} 的调用上限 {tier['max_calls']}"
    assert str(REG.RUN_BUDGET_DEFAULT["max_calls"]) in text, f"{rel} 没写默认档"


@pytest.mark.parametrize("rel", MANUALS + ("ops/specs/fairness_protocol.md",))
def test_no_manual_hardcodes_a_call_cap_outside_the_table(rel):
    """手册里凡是写死的 `--max-calls N`，N 必须是档位表里真实存在的一个数。

    验收配置（fairness §6.5）也一并扫：它现在不写预算数字，将来有人补进去时这条会接住。
    """
    legal = {REG.RUN_BUDGET_DEFAULT["max_calls"]} | {t["max_calls"] for t in REG.BUDGET_TIERS.values()}
    text = (_REPO / rel).read_text(encoding="utf-8")
    bad = [n for n in re.findall(r"--max-calls\s+(\d+)", text) if int(n) not in legal]
    assert not bad, f"{rel} 里写死了档位表之外的调用上限 {bad}（合法值 {sorted(legal)}）"
