# -*- coding: utf-8 -*-
"""`ops/push_guard.py` 的判别力测试。

**这张门是补的,不是设计的** —— 2026-09-04 我用一条手写 rsync 把 `reference/`
推上了执行面。所以这里每条测试都要能**证伪**「门在干活」这句话:
恒绿的门(什么都放行)和恒红的门(连合法 bundle 都拦)一样等于没有门(F7)。
"""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path

import pytest

from genetask.bundle import X_ALLOWED_FILES, X_ALLOWED_PREFIXES
from genetask.packager import _token
from ops.freeze_v10 import frozen_ref
from ops.push_guard import (GOLD_TOKEN_RE, PushBlocked, _sha256, assert_pushable,
                            check_bundle_tree, check_manifest)

GUARD_SRC = Path(__file__).resolve().parent / "push_guard.py"


def _bundle(root: Path) -> Path:
    """按真 X bundle 的形状造一棵树 —— 含**合法**的 control/x 串。

    合法串必须在场,否则「不拦」这件事没有信息量:一棵空树当然过。
    """
    d = root / "s1-cor-01"
    (d / "arms").mkdir(parents=True)
    (d / "image" / "tests").mkdir(parents=True)
    (d / "work" / "protocol").mkdir(parents=True)
    (d / "task.yaml").write_text(f"# x_token: {_token('X')}\ntask_id: s1-cor-01\n", encoding="utf-8")
    (d / "arms" / "INSTRUCTION.strict.md").write_text(f"校验串：{_token('C')}\n", encoding="utf-8")
    (d / "image" / "Dockerfile").write_text("FROM python:3.11-slim\n", encoding="utf-8")
    (d / "image" / "tests" / "test_outputs.py").write_text("def test_x(): pass\n", encoding="utf-8")
    (d / "work" / "S1.json").write_text(json.dumps({"stage": "S1"}), encoding="utf-8")
    (d / "work" / "protocol" / "task.json").write_text("{}", encoding="utf-8")
    return d


# ---------------------------------------------------------------- 门要放行合法的
def test_real_shaped_bundle_passes(tmp_path):
    """合法 bundle 必须绿。**这条防恒红** —— control/x 串在场也不许误伤。"""
    assert check_bundle_tree(_bundle(tmp_path)) == []


def test_control_and_x_tokens_are_not_gold(tmp_path):
    """`GBC-C-`/`GBC-X-` 是设计上要进执行面的。判据只针对 `GBC-G-`。"""
    for _ in range(200):
        assert GOLD_TOKEN_RE.fullmatch(_token("G")), "真 gold 串没被认出来 —— 门形同虚设"
        assert not GOLD_TOKEN_RE.search(_token("C"))
        assert not GOLD_TOKEN_RE.search(_token("X"))


# ---------------------------------------------------------------- 门要拦非法的
def test_the_actual_incident_shape_is_refused(tmp_path):
    """**当晚真实发生的那棵树**:bundle 旁边多一个 `reference/`。"""
    d = _bundle(tmp_path)
    ref = d / "reference" / "tasks" / "v1.0-smoke" / "s1-cor-01"
    ref.mkdir(parents=True)
    (ref / "canary.json").write_text(json.dumps({"gold_token": _token("G")}), encoding="utf-8")
    bad = check_bundle_tree(d)
    assert bad, "答案面目录被放行了 —— 这正是 2026-09-04 那次泄漏"
    joined = "\n".join(bad)
    assert "canary.json" in joined and "gold" in joined


def test_gold_token_inside_allowed_prefix_is_refused(tmp_path):
    """**这条是判别力的核心**:文件名无辜、路径在允许集内,只有内容判据能抓住。

    去掉 `GOLD_TOKEN_RE` 那段,本条必红 —— 说明内容扫描是承重的,不是装饰。
    """
    d = _bundle(tmp_path)
    leak = d / "work" / "notes.json"
    leak.write_text(json.dumps({"hint": f"see {_token('G')}"}), encoding="utf-8")
    rel = str(leak.relative_to(d))
    assert rel.startswith(X_ALLOWED_PREFIXES), "前提搭错了:这条得落在允许前缀里才有意义"
    assert rel not in X_ALLOWED_FILES
    bad = check_bundle_tree(d)
    assert any("gold" in b and "work/notes.json" in b for b in bad), bad


def test_answer_plane_name_inside_allowed_prefix_is_refused(tmp_path):
    """`arms/` 在允许集里,但 `arms/scorer.yaml` 是答案面。文件名判据是第二层纵深。"""
    d = _bundle(tmp_path)
    (d / "arms" / "scorer.yaml").write_text("threshold: 0.5\n", encoding="utf-8")
    assert any("scorer.yaml" in b for b in check_bundle_tree(d))


@pytest.mark.parametrize("seg", ["reference", "gold", "solution", "scorer"])
def test_answer_plane_path_segment_is_refused(tmp_path, seg):
    """**只有路径段判据能抓的形状**:目录名是答案面的,但文件名无辜、路径在允许前缀内、
    内容里也没有 gold 串。M7 突变(拆掉路径段判据)就活在这里。"""
    d = _bundle(tmp_path)
    p = d / "work" / seg / "notes.md"
    p.parent.mkdir(parents=True)
    p.write_text("# 只是笔记\n", encoding="utf-8")
    rel = str(p.relative_to(d))
    assert rel.startswith(X_ALLOWED_PREFIXES) and p.name not in ("canary.json",)
    assert not GOLD_TOKEN_RE.search(p.read_text(encoding="utf-8")), "前提搭错:内容里不该有 gold 串"
    assert any("路径段" in b and rel in b for b in check_bundle_tree(d)), check_bundle_tree(d)


@pytest.mark.parametrize("rel", ["extra.txt", "solution/solve.py", "gold/answers.json"])
def test_files_outside_the_allowlist_are_refused(tmp_path, rel):
    d = _bundle(tmp_path)
    p = d / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x\n", encoding="utf-8")
    assert any(rel in b for b in check_bundle_tree(d))


def test_assert_pushable_raises(tmp_path):
    d = _bundle(tmp_path)
    (d / "canary.json").write_text("{}", encoding="utf-8")
    with pytest.raises(PushBlocked):
        assert_pushable(d)


def test_missing_dir_is_refused_not_silently_green(tmp_path):
    """路径打错不能表现成「查过了,没问题」。"""
    assert check_bundle_tree(tmp_path / "nope") != []


def test_unreadable_file_is_a_finding(tmp_path):
    """读不了 ≠ 查过了没有(F7)。权限异常必须响,不能当成绿。"""
    d = _bundle(tmp_path)
    p = d / "work" / "opaque.json"
    p.write_text("{}", encoding="utf-8")
    os.chmod(p, 0o000)
    try:
        if os.access(p, os.R_OK):
            pytest.skip("本进程仍能读 0000 文件(root?),这条判据在此环境无法证伪")
        assert any("读不了" in b for b in check_bundle_tree(d))
    finally:
        os.chmod(p, 0o600)


# ---------------------------------------------------------------- 判据是封闭的
def test_allowlist_is_imported_from_bundle_not_copied():
    """允许集必须**引自** `genetask.bundle`。抄一份会随时间漂,漂了就没人知道。

    用 AST 判,不查散文 —— 否则这条注释自己就能让门变绿(D-25)。
    """
    tree = ast.parse(GUARD_SRC.read_text(encoding="utf-8"))
    imported = {n.name for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.module == "genetask.bundle"
                for n in node.names}
    assert {"X_ALLOWED_FILES", "X_ALLOWED_PREFIXES"} <= imported
    assigned = {t.id for node in ast.walk(tree) if isinstance(node, ast.Assign)
                for t in node.targets if isinstance(t, ast.Name)}
    assert not ({"X_ALLOWED_FILES", "X_ALLOWED_PREFIXES"} & assigned), \
        "允许集被本地覆盖了 —— 判据不再封闭"


def test_shell_wrapper_calls_the_guard():
    """`push_bundle_to_f02.sh` 必须真的调门,而不是「旁边放着一个门」(D-20)。"""
    sh = GUARD_SRC.parent / "push_bundle_to_f02.sh"
    assert sh.exists(), "守门脚本不在"
    txt = sh.read_text(encoding="utf-8")
    needle = GUARD_SRC.name  # 运行时拼,不写字面量 —— 门不查自己的散文
    call = [l for l in txt.splitlines() if needle in l and "$" in l]
    assert call, f"脚本里没有真的调用 {needle} 的那一行"
    line = call[0]
    assert "SRC" in line and "MANIFEST" in line, \
        f"调门的那一行没把通行证一起传进去（M17 就活在这里）：{line}"
    assert 'MANIFEST="' in txt and '$3' in txt, "通行证不是从第三个参数来的"
    assert "set -euo pipefail" in txt, "门失败必须让脚本停下"
    # N-61：推完必须调**对面自己的**门，而不是在这里再写一遍 grep。
    guard = "answer_plane_guard.py"
    assert guard in txt, f"推送脚本没有调用接收侧的 {guard}"
    assert "test -f" in txt, "对面缺门时必须停下 —— 缺门不等于没问题"
    assert "grep -rqE" not in txt, "还留着本地重写的一份 grep —— 判据要只有一处"
    # N-61：兜底 timer 的**活性**要在依赖它的这一刻检查。
    # 实测它会悄悄变成 disabled —— 门还在，每小时没人来按它。
    assert "is-enabled" in txt and "is-active" in txt, "没检查兜底扫描 timer 是否还活着"
    assert "genebench-answer-plane-scan.timer" in txt


# ---------------------------------------------------------------- 通行证要对上树
def _manifest(d: Path, out: Path, **over) -> Path:
    """照真导出器的形状现造一份通行证（哈希是**现算**的，不是抄的）。"""
    m = {"manifest_version": "1.0", "task_id": "s1-cor-01", "set_id": "v1.0-smoke",
         "stage": "S1", "packager_version": "0.1",
         "allowed_files": list(X_ALLOWED_FILES), "allowed_prefixes": list(X_ALLOWED_PREFIXES),
         "check_export": [], "frozen_manifest": frozen_ref(),
         "files": {str(f.relative_to(d)): _sha256(f) for f in sorted(d.rglob("*")) if f.is_file()}}
    m.update(over)
    out.write_text(json.dumps(m, indent=1), encoding="utf-8")
    return out


def test_matching_manifest_passes(tmp_path):
    d = _bundle(tmp_path)
    assert check_manifest(d, _manifest(d, tmp_path / "manifest.json")) == []


def test_one_flipped_byte_is_caught(tmp_path):
    """**通行证判据的核心**：形状全合法，只有一个字节变了。树判据放行，这里必须拦。"""
    d = _bundle(tmp_path)
    mp = _manifest(d, tmp_path / "manifest.json")
    victim = d / "arms" / "INSTRUCTION.strict.md"
    victim.write_text(victim.read_text(encoding="utf-8") + " ", encoding="utf-8")
    assert check_bundle_tree(d) == [], "前提搭错：改过的树在形状上仍应合法"
    assert any("内容与通行证不符" in b and "INSTRUCTION.strict.md" in b
               for b in check_manifest(d, mp))


def test_extra_and_missing_files_are_caught(tmp_path):
    d = _bundle(tmp_path)
    mp = _manifest(d, tmp_path / "manifest.json")
    (d / "work" / "surprise.json").write_text("{}", encoding="utf-8")
    (d / "work" / "S1.json").unlink()
    bad = check_manifest(d, mp)
    assert any("通行证没写" in b and "surprise.json" in b for b in bad), bad
    assert any("树里没有" in b and "S1.json" in b for b in bad), bad


def test_stale_frozen_ref_is_caught(tmp_path):
    """题面重冻结之后，旧 bundle 必须被拦下重导，而不是改通行证。"""
    d = _bundle(tmp_path)
    stale = dict(frozen_ref()); stale["root"] = "0" * 64
    mp = _manifest(d, tmp_path / "manifest.json", frozen_manifest=stale)
    assert any("冻结引用已过期" in b for b in check_manifest(d, mp))


def test_nonempty_check_export_is_caught(tmp_path):
    d = _bundle(tmp_path)
    mp = _manifest(d, tmp_path / "manifest.json", check_export=["G3 某处不合规"])
    assert any("check_export" in b for b in check_manifest(d, mp))


def test_manifest_declaring_other_allowlist_is_caught(tmp_path):
    d = _bundle(tmp_path)
    mp = _manifest(d, tmp_path / "manifest.json", allowed_prefixes=["arms/", "image/", "work/", "gold/"])
    assert any("允许集" in b for b in check_manifest(d, mp))


def test_absent_manifest_is_a_finding_not_a_pass(tmp_path):
    """没有通行证 ≠ 通行证没问题。"""
    d = _bundle(tmp_path)
    assert check_manifest(d, tmp_path / "nope.json") != []
    with pytest.raises(PushBlocked):
        assert_pushable(d, tmp_path / "nope.json")


# ---------------------------------------------------------------- D-27 实施要求：段数可数
#: `push_guard` 声称保护的段。**加一段却忘了补红测试，下面那条会红。**
CLAIMED_SECTIONS: dict[str, str] = {
    "allowlist_path": "test_files_outside_the_allowlist_are_refused",
    "gold_token_content": "test_gold_token_inside_allowed_prefix_is_refused",
    "answer_plane_name": "test_answer_plane_name_inside_allowed_prefix_is_refused",
    "answer_plane_path_segment": "test_answer_plane_path_segment_is_refused",
    "unreadable": "test_unreadable_file_is_a_finding",
    "manifest_allowed_set": "test_manifest_declaring_other_allowlist_is_caught",
    "manifest_file_sha": "test_one_flipped_byte_is_caught",
    "manifest_file_set": "test_extra_and_missing_files_are_caught",
    "manifest_check_export": "test_nonempty_check_export_is_caught",
    "manifest_frozen_ref": "test_stale_frozen_ref_is_caught",
    "manifest_absent": "test_absent_manifest_is_a_finding_not_a_pass",
}


def test_every_claimed_section_has_a_red_test():
    """**判据是可数的**：门声称保护几段，验收里就要有几条红测试，一段一条（D-27 实施要求）。

    不允许一条笼统的「整体一致」覆盖多段 —— 那种测试在「少比了一段」时照样绿，
    而少比一段正是这一族缺陷的形态（N-74）。
    """
    here = Path(__file__).read_text(encoding="utf-8")
    missing = {s: t for s, t in CLAIMED_SECTIONS.items() if f"def {t}" not in here}
    assert not missing, f"这些段没有对应的红测试：{missing}"
    assert len(CLAIMED_SECTIONS) == 11
