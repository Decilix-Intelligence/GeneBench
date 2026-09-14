# -*- coding: utf-8 -*-
"""IN-1 / IN-2：**按运行动态分配** compose 子网，并用真的 `overlaps()` 判否。

**为什么必须换掉子串判据（卡 4.3 §IN-2 原文）**：`lint_compose` 的 L-4 原来写的是
``"10.42." in text``。`10.40.0.0/13` **覆盖** 10.42/16 与 10.43/16，
却一个禁用子串都不含 —— **当场假绿**，而后果是任务网段和 k3s 的 pod/service 网撞上，
症状是「偶发连不上」，不是「配置报错」。

**为什么必须动态分配（IN-1）**：`TASK_SUBNET` 原来是常量 `172.31.240.0/24`。
两臂并发跑就必然抢同一个网段 —— docker 会拒绝第二个，或者更糟：
两个 compose 项目各自建网成功但地址重叠，容器间路由行为取决于建网顺序。

**docker 自己的默认地址池也在 172.16/12 里**，所以硬编码一个 172.31.240 是在跟
docker 抢地址。因此候选必须与 `docker network inspect` 的**实时**结果一起判否。
"""
from __future__ import annotations

import ipaddress
import json
import subprocess
from dataclasses import dataclass

Net = ipaddress.IPv4Network


@dataclass(frozen=True)
class Reserved:
    net: Net
    why: str


#: 必须避开的网段，**每条写清是谁的**。理由要能被证伪：说不出是谁的就不该在这。
RESERVED: tuple[Reserved, ...] = (
    Reserved(Net("10.42.0.0/16"), "k3s pod cidr（finance02 上在跑）"),
    Reserved(Net("10.43.0.0/16"), "k3s service cidr"),
    Reserved(Net("10.88.0.0/16"), "cni 默认网段"),
    Reserved(Net("192.168.1.0/24"), "LAN —— 数据面网关与两台机自己都在这"),
    Reserved(Net("100.64.0.0/10"), "tailscale CGNAT —— 反向可达性就藏在这一段"),
)

#: 分配池：`/20` 切成 16 个 `/24`，即 **8 组**（task + egress 各一）并发运行。
POOL: Net = Net("172.31.240.0/20")
PREFIX: int = 24


class SubnetExhausted(RuntimeError):
    """池子用完。**不回绕、不缩小前缀** —— 静默复用等于两个运行共享网段。"""


def overlaps_any(net: Net, others) -> list[str]:
    """`net` 与哪些东西重叠。空列表 = 不重叠。

    `others` 里可以是 `Reserved`、`IPv4Network` 或字符串。
    """
    hits: list[str] = []
    for o in others:
        if isinstance(o, Reserved):
            cand, why = o.net, o.why
        else:
            cand, why = (o if isinstance(o, Net) else Net(str(o), strict=False)), "已分配"
        if net.overlaps(cand):
            hits.append(f"{net} 与 {cand} 重叠（{why}）")
    return hits


def docker_allocated(*, run=subprocess.run, timeout: int = 20) -> list[Net]:
    """`docker network inspect` 当前已分配的每一个网段。

    **拿不到就抛**，不返回空列表：空列表与「docker 上一个网都没有」长得一模一样，
    而两者的含义相反（F7 —— 查不了 ≠ 查过了没有）。
    """
    ids = run(["docker", "network", "ls", "-q"], capture_output=True, text=True,
              timeout=timeout, check=True).stdout.split()
    if not ids:
        return []
    out = run(["docker", "network", "inspect", *ids], capture_output=True, text=True,
              timeout=timeout, check=True).stdout
    nets: list[Net] = []
    for n in json.loads(out):
        for cfg in ((n.get("IPAM") or {}).get("Config") or []):
            s = cfg.get("Subnet")
            if s:
                try:
                    nets.append(Net(s, strict=False))
                except ValueError:
                    continue                      # IPv6 等，不参与 v4 判否
    return nets


def candidates(pool: Net = POOL, prefix: int = PREFIX) -> list[tuple[Net, Net]]:
    """池里所有**连续两个** /24 的组合（不重叠地成对切）。"""
    subs = list(pool.subnets(new_prefix=prefix))
    return [(subs[i], subs[i + 1]) for i in range(0, len(subs) - 1, 2)]


def pick_pair(taken=(), *, pool: Net = POOL, prefix: int = PREFIX) -> tuple[Net, Net]:
    """选一组 (task, egress)。与 RESERVED 和 `taken` 全部判否。"""
    blockers = list(RESERVED) + list(taken)
    why_skipped: list[str] = []
    for a, b in candidates(pool, prefix):
        bad = overlaps_any(a, blockers) + overlaps_any(b, blockers)
        if not bad:
            return a, b
        why_skipped.append(f"{a}/{b}: " + "；".join(bad))
    raise SubnetExhausted(
        f"池 {pool} 里 {len(candidates(pool, prefix))} 组候选全部被占/冲突：\n  "
        + "\n  ".join(why_skipped)
        + "\n**不回绕复用** —— 两个运行共享网段的后果比排队等更糟。")


def allocate(*, require_docker: bool = True, run=subprocess.run) -> dict:
    """给一次运行分配子网，返回可直接写进 `inject.json` 的记录。"""
    if require_docker:
        taken = docker_allocated(run=run)
        probe = f"docker network inspect：{len(taken)} 个网段"
    else:
        taken, probe = [], "**未探测**（require_docker=False）—— 并发安全性在此路径下没有保证"
    a, b = pick_pair(taken)
    return {"task_subnet": str(a), "egress_subnet": str(b),
            "pool": str(POOL), "docker_probe": probe,
            "reserved": [f"{r.net} {r.why}" for r in RESERVED],
            "taken_at_alloc": [str(n) for n in taken]}
