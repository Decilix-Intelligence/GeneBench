#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""**双机形态专用**的落位常量与命令（卡 A9，2026-09-14）。

这个模块存在的唯一理由是：把「发布方那台执行面的绝对路径」**关进一个单机路径不 import
的文件里**。用户 2026-09-14 的裁定 ③ 给了一条静态判据 ——「单机路径上 `/data` 字面量
出现零次」——而双机形态的默认根 `/data/genebench_runner` 又必须**逐字不变**
（发布方那台机器上的行为不许动）。两条同时成立的做法只有一个：让它待在一个
**只有 `topology == dual` 的分支才会 import** 的模块里。

`runner/placement.py` 对它的 import 因此是**函数内**的，不是模块顶层的 ——
这不是风格，是判据本身：`ops/test_A9.py::test_single_branch_never_imports_the_dual_module`
真起一个 `GENEBENCH_TOPOLOGY=single` 的进程，跑完单机那条落位，再看
`sys.modules` 里有没有这个模块名。有 = 红。

**这个文件里的东西一个字都不要往单机分支上搬。**
"""
from __future__ import annotations

from pathlib import Path

#: 发布方执行面（f02）的根。**逐字不变** —— `ops/push_bundle_to_f02.sh:69`、
#: `ops/push_exec_to_f02.sh:31`、`ops/api_usage.py::DEFAULT_F02_ROOT`、
#: `runner/f02/answer_plane_guard.py::DEFAULT_ROOT` 是同一个值。
RUNNER_ROOT_DEFAULT = "/data/genebench_runner"

#: 数据面→执行面的 ssh 目标默认值（与 `ops/run_joblist.py::F02` 同一套口径）。
F02_DEFAULT = "ljn@192.168.1.219"

#: ssh 一律带这个超时（契约 A）。
SSH_OPTS: tuple[str, ...] = ("-o", "ConnectTimeout=120")


def ssh_cmd(target: str, inner: str) -> list[str]:
    """把一条命令包成 `ssh <opts> <target> <inner>`。双机形态专用。"""
    return ["ssh", *SSH_OPTS, target, inner]


def push_bundle_script(repo: Path) -> Path:
    """红线 B2：推 bundle 的**唯一**入口。单机形态不调它（裁定 ①）。"""
    return Path(repo) / "ops" / "push_bundle_to_f02.sh"


def push_exec_script(repo: Path) -> Path:
    """exec 树同步的唯一入口（W-0）。单机形态不调它（裁定 ①）。"""
    return Path(repo) / "ops" / "push_exec_to_f02.sh"
