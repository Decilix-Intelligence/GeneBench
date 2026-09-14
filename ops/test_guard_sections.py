# -*- coding: utf-8 -*-
"""**D-27 实施要求**：每个门声称保护的**每一段**，各有一条「喂真改动、必红」。

不允许一条笼统的「整体一致」覆盖多段 —— 那种测试在「少比了一段」时照样绿，
而**「少比了一段」正是这一族缺陷的形态**（N-74：`frozen_ref` 现算了整份清单，
却只比两段，`templates` 从来没被比过）。

每条测试造一份**只在那一段上**与基线不同的输入，其余全部合法 ——
「其余全部合法」是关键，否则红可能来自别的段，那条测试就没有定位能力。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from genetask.bundle import (SKIP_FROZEN_CHECK, X_ALLOWED_FILES, X_ALLOWED_PREFIXES,
                            check_manifest)
from genetask import pin

REPO = Path(__file__).resolve().parents[1]

#: 门 → 它声称保护的段。**这张表是可数的判据** ——
#: 加了一段却忘了补红测试，`test_every_claimed_section_has_a_red_test` 会红。
CLAIMED_SECTIONS: dict[str, tuple[str, ...]] = {
    "check_manifest": ("manifest_version", "check_export", "file_set", "file_sha",
                       "allowed_set", "frozen_root"),
    "check_provider_pin": ("root_exists", "tree_nonempty", "root_sha", "filelist"),
}


# ---------------------------------------------------------------- check_manifest 的六段
def _bundle(tmp_path: Path) -> tuple[Path, dict]:
    """一份**完全合法**的最小 bundle + 通行证。"""
    d = tmp_path / "b"
    (d / "arms").mkdir(parents=True)
    (d / "work").mkdir()
    (d / "task.yaml").write_text("task_id: t1\n", encoding="utf-8")
    (d / "arms" / "INSTRUCTION.strict.md").write_text("x\n", encoding="utf-8")
    (d / "work" / "S1.json").write_text("{}", encoding="utf-8")
    files = {str(p.relative_to(d)): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(d.rglob("*")) if p.is_file()}
    man = {"manifest_version": "1.0", "task_id": "t1", "check_export": [],
           "allowed_files": list(X_ALLOWED_FILES),
           "allowed_prefixes": list(X_ALLOWED_PREFIXES),
           "frozen_manifest": {"root": "r" * 64}, "files": files}
    return d, man


def test_baseline_bundle_is_green(tmp_path):
    """防恒红：完全合法的一份必须绿，否则下面六条红都不作数。"""
    d, m = _bundle(tmp_path)
    assert check_manifest(d, m, expect_frozen_root="r" * 64) == []


def test_section_manifest_version(tmp_path):
    d, m = _bundle(tmp_path)
    m["manifest_version"] = "0.9"
    bad = check_manifest(d, m, expect_frozen_root="r" * 64)
    assert bad and "通行证版本" in bad[0]


def test_section_check_export(tmp_path):
    d, m = _bundle(tmp_path)
    m["check_export"] = ["G3 某处不合规"]
    assert any("check_export" in x for x in check_manifest(d, m, expect_frozen_root="r" * 64))


def test_section_file_set_missing_and_extra(tmp_path):
    d, m = _bundle(tmp_path)
    m2 = {**m, "files": {**m["files"], "work/ghost.json": "0" * 64}}
    assert any("少文件" in x for x in check_manifest(d, m2, expect_frozen_root="r" * 64))
    (d / "work" / "surprise.json").write_text("{}", encoding="utf-8")
    assert any("多文件" in x for x in check_manifest(d, m, expect_frozen_root="r" * 64))


def test_section_file_sha(tmp_path):
    d, m = _bundle(tmp_path)
    k = next(iter(m["files"]))
    m["files"] = {**m["files"], k: "0" * 64}
    assert any("sha256 与通行证不符" in x for x in check_manifest(d, m, expect_frozen_root="r" * 64))


def test_section_allowed_set(tmp_path):
    """两半都要红：**树里多一个越界文件**，以及**通行证自报的允许集与常量不符**。

    后者尤其要紧：通行证跟着 bundle 一起搬，改通行证就能放宽白名单 ——
    那等于让被查的一方定义什么叫合规。
    """
    d, m = _bundle(tmp_path)
    (d / "extra.txt").write_text("x", encoding="utf-8")
    m2 = {**m, "files": {**m["files"], "extra.txt":
                         hashlib.sha256(b"x").hexdigest()}}
    assert any(x.startswith("G4") for x in check_manifest(d, m2, expect_frozen_root="r" * 64))
    (d / "extra.txt").unlink()
    m3 = {**m, "allowed_prefixes": [*X_ALLOWED_PREFIXES, "gold/"]}
    assert any("允许集与本机常量不符" in x
               for x in check_manifest(d, m3, expect_frozen_root="r" * 64))


def test_section_frozen_root(tmp_path):
    """两半：**根不一致**，以及**通行证根本没记根**。"""
    d, m = _bundle(tmp_path)
    assert any("frozen_manifest_mismatch" in x
               for x in check_manifest(d, m, expect_frozen_root="q" * 64))
    m2 = {**m, "frozen_manifest": {}}
    assert any("没记冻结清单根" in x
               for x in check_manifest(d, m2, expect_frozen_root="r" * 64))
    # 反面：显式跳过时不许red —— 否则这条门在开发路径上恒红
    assert check_manifest(d, m2, expect_frozen_root=SKIP_FROZEN_CHECK) == []


# ---------------------------------------------------------------- check_provider_pin 的四段
def _provider(tmp_path: Path) -> Path:
    d = tmp_path / "p"
    (d / "calendars").mkdir(parents=True)
    (d / "calendars" / "day.txt").write_text("2026-07-01\n", encoding="utf-8")
    lines = [f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.stat().st_size}  "
             f"{p.relative_to(d)}" for p in sorted(d.rglob('*')) if p.is_file()]
    (d / "files.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return d


def test_provider_baseline_is_green(tmp_path):
    d = _provider(tmp_path)
    assert pin.check_provider_pin(d, expect=pin.provider_root_sha256(d)) == []


def test_section_root_exists(tmp_path):
    """**不存在 ≠ 跳过检查**（F1）。"""
    bad = pin.check_provider_pin(tmp_path / "nope", expect="x" * 64)
    assert bad and "不存在" in bad[0]


def test_section_tree_nonempty(tmp_path):
    """空树也能算出一个稳定的 sha256 —— 但那不是冻结 provider。"""
    d = tmp_path / "empty"
    d.mkdir()
    bad = pin.check_provider_pin(d, expect="x" * 64)
    assert bad and "为空" in bad[0]


def test_section_root_sha(tmp_path):
    d = _provider(tmp_path)
    bad = pin.check_provider_pin(d, expect="0" * 64)
    assert bad and "sha256 根" in bad[0]


def test_section_filelist(tmp_path):
    """根 hash 只证明**清单**没被动过。换掉一个文件而不动清单，根 hash 一个字不变。"""
    d = _provider(tmp_path)
    exp = pin.provider_root_sha256(d)
    (d / "calendars" / "day.txt").write_text("2026-07-02\n", encoding="utf-8")   # 只改内容
    assert pin.provider_root_sha256(d) == exp, "前提搭错：改内容不该动根 hash"
    assert pin.check_provider_pin(d, expect=exp), "逐文件那一层没拦住"


# ---------------------------------------------------------------- 段数可数
@pytest.mark.parametrize("guard", sorted(CLAIMED_SECTIONS))
def test_every_claimed_section_has_a_red_test(guard):
    """**判据是可数的**：门声称保护几段，验收里就要有几条红测试，一段一条。"""
    here = Path(__file__).read_text(encoding="utf-8")
    missing = [s for s in CLAIMED_SECTIONS[guard] if f"def test_section_{s}" not in here]
    assert not missing, f"{guard} 的这些段没有对应的红测试：{missing}"


def test_the_section_registry_is_not_empty_or_stale():
    assert CLAIMED_SECTIONS and all(v for v in CLAIMED_SECTIONS.values())
    assert len(CLAIMED_SECTIONS["check_manifest"]) == 6
    assert len(CLAIMED_SECTIONS["check_provider_pin"]) == 4


# ---------------------------------------------------------------- 两条版本轴（裁定 2026-09-05）
def test_export_manifest_carries_both_axes(tmp_path):
    """通行证要同时记**两个版本** —— 只记一个的话，两次 gold 算法不同的运行
    会看起来完全可比（`frozen_manifest` 相同、而 `reference_manifest` 无从比较）。"""
    import inspect

    from genetask import packager as P
    sig = inspect.signature(P.export_manifest)
    assert "reference_ref" in sig.parameters, "出通行证时没有参考面引用这一入参"
    src = inspect.getsource(P.export_manifest)
    assert '"reference_manifest"' in src


def test_inject_json_records_both_axes():
    """`inject.json` 是运行侧的记录 —— 两个版本都要在里面。"""
    src = (REPO / "runner" / "inject.py").read_text(encoding="utf-8")
    assert '"frozen_manifest"' in src and '"reference_manifest"' in src


def test_comparability_needs_both(tmp_path):
    """**可比性判据**：两条轴任一不同，两次运行就不可比。

    这条把判据写成可执行的形式，免得它只活在文档里。
    """
    def comparable(a: dict, b: dict) -> bool:
        return (a.get("frozen_manifest") == b.get("frozen_manifest")
                and a.get("reference_manifest") == b.get("reference_manifest"))

    base = {"frozen_manifest": {"root": "t1"}, "reference_manifest": {"reference_root": "r1"}}
    assert comparable(base, dict(base))
    assert not comparable(base, {**base, "frozen_manifest": {"root": "t2"}})
    assert not comparable(base, {**base, "reference_manifest": {"reference_root": "r2"}}), \
        "参考面不同却判成可比 —— 那正是拆轴要防的事"
