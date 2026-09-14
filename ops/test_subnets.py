# -*- coding: utf-8 -*-
"""IN-1 / IN-2 与 T7 的判据（线 A / A4）。

核心那条是 **`10.40.0.0/13`**：它覆盖 k3s 的 10.42/16 与 10.43/16，
却**一个禁用子串都不含**。旧的 L-4 写的是 `"10.42." in text` —— 对它完全沉默。
所以这里的第一条测试不是「有没有判据」，是「判据认不认得出这个反例」。
"""
from __future__ import annotations

import ipaddress
import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "runner" / "c41"))
import negctl_lint as NC                                    # noqa: E402
import runner_core as RC                                    # noqa: E402
import subnets as S                                         # noqa: E402

Net = ipaddress.IPv4Network


# ---------------------------------------------------------------- T7：判据认得出超网
def test_supernet_that_contains_k3s_is_caught():
    """子串判据的盲区。**这条红了整个 IN-2 就白做了。**"""
    hits = S.overlaps_any(Net("10.40.0.0/13"), S.RESERVED)
    assert len(hits) >= 2, hits
    text = NC.BASE.replace("172.31.240.0/24", "10.40.0.0/13")
    assert "10.42." not in text and "10.43." not in text, \
        "前提搭错：这个反例的全部意义是**不含**禁用子串"
    assert [b for b in RC.lint_compose(text) if b.startswith("L-4")]


@pytest.mark.parametrize("cidr", ["10.42.9.0/24", "10.43.0.0/16", "10.88.1.0/24",
                                  "192.168.1.0/25", "100.100.7.0/24", "10.40.0.0/13"])
def test_every_reserved_family_is_refused(cidr):
    text = NC.BASE.replace("172.31.240.0/24", cidr)
    assert [b for b in RC.lint_compose(text) if b.startswith("L-4")], cidr


def test_clean_compose_is_still_green():
    """防恒红：默认网段必须放行，否则这条规则会被注释掉。"""
    assert [b for b in RC.lint_compose(NC.BASE) if b.startswith("L-4")] == []


def test_missing_subnet_declaration_is_a_finding():
    """**没声明**与**声明了个好的**在日志里长得一样 —— 前者让 docker 从 172.16/12 自选。"""
    text = NC.BASE.replace("      config:\n        - subnet: 172.31.240.0/24\n", "")
    text = text.replace("      config:\n        - subnet: 172.31.241.0/24\n", "")
    text = text.replace("    ipam:\n", "")
    assert [b for b in RC.lint_compose(text) if b.startswith("L-4")]


def test_unparseable_subnet_is_a_finding_not_a_pass():
    text = NC.BASE.replace("172.31.240.0/24", "172.31.999.0/24")
    bad = [b for b in RC.lint_compose(text) if b.startswith("L-4")]
    assert bad and "解析不出来" in bad[0]


# ---------------------------------------------------------------- IN-1：按运行分配
def test_pool_gives_eight_disjoint_pairs():
    pairs = S.candidates()
    assert len(pairs) == 8
    seen: list[Net] = []
    for a, b in pairs:
        assert not S.overlaps_any(a, seen) and not S.overlaps_any(b, [*seen, a])
        seen += [a, b]


def test_pick_pair_avoids_reserved_and_taken():
    first = S.pick_pair()
    second = S.pick_pair(taken=list(first))
    assert not S.overlaps_any(second[0], list(first)), (first, second)
    assert not S.overlaps_any(second[1], list(first))
    for n in first + second:
        assert not S.overlaps_any(n, S.RESERVED)


def test_pool_exhaustion_raises_instead_of_wrapping():
    """回绕复用 = 两个运行共享网段。宁可停下，不许悄悄复用。"""
    taken = [n for pair in S.candidates() for n in pair]
    with pytest.raises(S.SubnetExhausted):
        S.pick_pair(taken=taken)


def test_docker_allocated_networks_are_avoided():
    """docker 自己的默认池就在 172.16/12 里 —— 不查它就是在跟 docker 抢地址。"""
    fake = [{"IPAM": {"Config": [{"Subnet": "172.31.240.0/22"}]}}]

    def run(cmd, **kw):
        out = "netid1\n" if cmd[:3] == ["docker", "network", "ls"] else json.dumps(fake)
        return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")

    alloc = S.allocate(run=run)
    a = Net(alloc["task_subnet"])
    assert not a.overlaps(Net("172.31.240.0/22")), alloc
    assert "1 个网段" in alloc["docker_probe"]


def test_docker_probe_failure_raises_not_empty():
    """查不了 ≠ 查过了没有（F7）。返回空列表会与「docker 上一个网都没有」混掉。"""
    def run(cmd, **kw):
        raise subprocess.CalledProcessError(1, cmd, stderr="daemon 不在")
    with pytest.raises(subprocess.CalledProcessError):
        S.docker_allocated(run=run)


def test_skipping_the_probe_is_recorded_loudly():
    """`require_docker=False` 下没有并发保证，这件事必须写进记录，不能只是没写。"""
    alloc = S.allocate(require_docker=False)
    assert "未探测" in alloc["docker_probe"] and alloc["taken_at_alloc"] == []


def test_every_reserved_entry_says_whose_it_is():
    """说不出是谁的网段就不该在表里 —— 无从证伪的条目会永远留着。"""
    for r in S.RESERVED:
        assert r.why.strip() and len(r.why) > 4, r


# ---------------------------------------------------------------- 门后必须有人
def test_injector_no_longer_uses_the_constant_subnets():
    """源码级最低限：注入器不许再引常量网段。**行为判据在 `ops/test_inject.py`**
    （`test_in1_allocation_reaches_compose_and_inject_json`）—— 这里只挡住回退。"""
    src = (_REPO / "runner" / "inject.py").read_text(encoding="utf-8")
    assert "RC.TASK_SUBNET" not in src and "RC.EGRESS_SUBNET" not in src, \
        "还在用常量网段 —— IN-1 没落地"
