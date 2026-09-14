# -*- coding: utf-8 -*-
"""§12 状态锁的判据。每条**查现实**，不查 `status_lock.py` 里那张表自己的字段。

查表 = F7（只读记录值等于没查）：把 `state` 从「未启用」改成「已启用」
不该让任何东西变绿，改**实现**才该。
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

from ops import status_lock as SL

sys.path.insert(0, str(SL.REPO / "runner" / "c41"))
import runner_core as RC                                   # noqa: E402


# ---------------------------------------------------------------- 表本身的自洽
def test_every_ruling_has_a_reality_criterion():
    assert len(SL.RULINGS) == 5
    for r in SL.RULINGS:
        assert r.reality.strip() and r.decision.strip(), r
        assert r.state in ("已实现", "挂起", "实测已有·配额待定", "未启用", "归 v2"), r.state


# ---------------------------------------------------------------- TK-1
def _compose(workdir: str, runs_root: str) -> str:
    return RC.format_compose(
        project="lock", task_subnet="172.31.250.0/24", egress_subnet="172.31.251.0/24",
        proxy_py="/opt/p.py", h11_dir="/opt/h11",
        logdir=f"{workdir}/../log", gateway="192.168.1.48:18080",
        task_id="t1", run_id="r1", config_id="c1", arm="strict",
        image="python:3.11-alpine@sha256:" + "a" * 64, workdir=workdir,
        command="sh -c true", model_upstream="api.deepseek.com",
        max_calls=1, max_tokens=1)


def test_tk1_sibling_run_dir_is_refused(tmp_path):
    """TK-1 的**行为锁**：同一 runs 根下**别的** run dir 必须被 L-5a 拦下。

    这正是裁定里说的「判据 2 单独成立时同一 runs 根下别的 run dir 绕得过」的反面。
    """
    runs = tmp_path / "runs"
    mine, other = runs / "r1" / "work", runs / "r2" / "work"
    mine.mkdir(parents=True); other.mkdir(parents=True)
    assert RC.lint_compose(_compose(str(mine), str(runs)),
                           expect_workdir=mine, runs_root=runs) == [], \
        "基线就不干净，负例不作数"
    bad = RC.lint_compose(_compose(str(other), str(runs)),
                          expect_workdir=mine, runs_root=runs)
    assert any("L-5a" in b for b in bad), bad


def test_tk1_both_walls_use_the_same_wording():
    """「两处措辞一致」是 TK-1 的裁定原文 —— 两条互斥规则同时挂在墙上就等于没裁。"""
    t43 = SL.CARD_43.read_text(encoding="utf-8")
    t41 = SL.CARD_41.read_text(encoding="utf-8")
    assert SL.L5_TIGHTENED_PHRASE in t43, "卡 4.3 的裁定原文不见了"
    assert SL.L5_TIGHTENED_PHRASE in t41, (
        "卡 4.1 的规则表还写着收紧前的 L-5 措辞 —— "
        f"两面墙不一致。要求出现：{SL.L5_TIGHTENED_PHRASE!r}")


# ---------------------------------------------------------------- TK-2
_EXEC_CALLS = ("run", "check_call", "check_output", "Popen", "call", "system", "popen")


def test_tk2_no_code_actually_invokes_the_host_firewall():
    """TK-2 是「挂起」：散文里出现 ufw/iptables 不算做了，**执行**它才算。

    用 AST 找子进程调用里的字面量，不做全文 grep —— 全文 grep 会命中解释拓扑的注释，
    包括本文件自己（D-25）。
    """
    needles = ("ufw", "iptables", "nft")
    offenders: list[str] = []
    for f in sorted(SL.REPO.rglob("*.py")):
        rel = str(f.relative_to(SL.REPO))
        if rel.startswith((".git/", "ops/test_")) or "/templates/" in rel:
            continue
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"), filename=rel)):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else (fn.id if isinstance(fn, ast.Name) else "")
            if name not in _EXEC_CALLS:
                continue
            for lit in ast.walk(node):
                if isinstance(lit, ast.Constant) and isinstance(lit.value, str) \
                        and any(n in lit.value.split() or lit.value.startswith(n) for n in needles):
                    offenders.append(f"{rel}:{lit.lineno} {lit.value[:60]!r}")
    assert not offenders, ("TK-2 的状态是「挂起」，但代码里真的在执行主机防火墙命令：\n  "
                           + "\n  ".join(offenders))


def test_tk2_registration_survives():
    """缓办 ≠ 撤销。登记条目必须还在卡里，否则「保留登记」这半句就落空了。"""
    t = SL.CARD_43.read_text(encoding="utf-8")
    assert "TK-2" in t and "缓办" in t


# ---------------------------------------------------------------- TK-3
def test_tk3_no_quota_number_is_hardcoded():
    """裁定是「不定数」。出现一个写死的配额阈值就说明有人替签字人定了。"""
    src = (SL.REPO / "runner" / "inject.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    bad = [f"{n.targets[0].id}={n.value.value}" for n in ast.walk(tree)
           if isinstance(n, ast.Assign) and len(n.targets) == 1
           and isinstance(n.targets[0], ast.Name) and isinstance(n.value, ast.Constant)
           and isinstance(n.value.value, (int, float))
           and any(k in n.targets[0].id.upper() for k in ("QUOTA", "MAX_RUNS", "DISK_LIMIT"))]
    assert not bad, f"TK-3 还没定数，代码里却有配额常量：{bad}"


def test_tk3_measurement_is_recorded_and_self_consistent():
    """实测数要能自洽：落盘占用必须**大于**表观字节（46,544 个小文件的块开销）。

    这条不是装饰 —— 「按表观字节定阈值」正是 F10 的入口。
    """
    m = SL.TK3_F02_MEASUREMENT
    assert m["files"] > 40000 and m["apparent_bytes"] > 4e8
    on_disk_mib = float(m["on_disk_human"].rstrip("M"))
    apparent_mib = m["apparent_bytes"] / 1024 / 1024
    assert on_disk_mib > apparent_mib * 1.2, (
        f"落盘 {on_disk_mib}M 没有显著大于表观 {apparent_mib:.0f}M —— "
        f"要么数抄错了，要么这条提醒失去了理由")


# ---------------------------------------------------------------- TK-4
def test_tk4_fallback_path_is_not_enabled():
    """条件式批准 = 现在**没启用**。它一旦出现在实现里，卡 4.1 的 FS-A 就同时失效了。"""
    offenders = []
    for f in sorted(SL.REPO.rglob("*.py")):
        rel = str(f.relative_to(SL.REPO))
        if rel.startswith((".git/", "ops/test_", "ops/status_lock.py")):
            continue
        if SL.TK4_CONTAINER_PATH in f.read_text(encoding="utf-8"):
            offenders.append(rel)
    assert not offenders, (
        f"TK-4 的备用路径出现在 {offenders} —— 启用它必须同步改写 FS-A/T10，"
        f"否则会留下一条恒红的旧断言（裁定原文：不许留一条永远绿不了的旧断言）")


def test_tk4_fs_a_assertion_is_still_the_active_one():
    t = SL.CARD_41.read_text(encoding="utf-8")
    assert "ls /data" in t and "必须失败" in t


# ---------------------------------------------------------------- TK-5
def test_tk5_manifest_is_unsigned():
    """归 v2 = 现在没有签名。**做一个假的密码学保证比没有更坏**（裁定原文）。"""
    from genetask import bundle as B
    from genetask import packager as P
    src = ast.parse((Path(B.__file__)).read_text(encoding="utf-8"))
    names = {n.id for n in ast.walk(src) if isinstance(n, ast.Name)} | \
            {n.attr for n in ast.walk(src) if isinstance(n, ast.Attribute)}
    assert not ({"verify", "signature", "sign", "pubkey"} & names), \
        "check_manifest 侧出现了验签符号 —— TK-5 的状态该改了"
    psrc = ast.parse(Path(P.__file__).read_text(encoding="utf-8"))
    pnames = {n.id for n in ast.walk(psrc) if isinstance(n, ast.Name)} | \
             {n.attr for n in ast.walk(psrc) if isinstance(n, ast.Attribute)}
    assert not ({"signature", "sign", "pubkey"} & pnames), \
        "出通行证的那一侧出现了签名符号 —— TK-5 的状态该改了"


def test_tk5_boundary_is_written_down():
    """边界必须写在纸上：论文里不许把清单说成「保证了完整性」。"""
    t = SL.CARD_43.read_text(encoding="utf-8")
    assert "清单没有签名" in t and "目录权限" in t


# ---------------------------------------------------------------- 锁本身要能红
def test_the_lock_is_not_vacuous(tmp_path, monkeypatch):
    """判别力：把两面墙里的一面换成收紧前的措辞，TK-1 的一致性锁必须红。"""
    fake = tmp_path / "card41.md"
    fake.write_text("| L-5 | 任务容器只许挂自己的 `tasks/<id>` 目录 |\n", encoding="utf-8")
    monkeypatch.setattr(SL, "CARD_41", fake)
    with pytest.raises(AssertionError):
        test_tk1_both_walls_use_the_same_wording()
