# -*- coding: utf-8 -*-
"""qlib provider 树的**定位器**。

**这里不重写 provider 适配层，也不从网关现造 provider。** 现成的那一层是：

* 规格：`ops/specs/card_4.3_two_arm_injector.md` §7（PA-1..PA-6）；
* 物化与核根：`runner/provider_adapter.py::materialize()` / `place_for_arm()`；
* 用法示例：`runner/c42/adapters/rdagent_q/adapter.py`（``PROVIDER = "/task/provider"``）。

为什么本模块只是个定位器
------------------------
**PA-6：provider 物化在注入期（f02 runner 侧，可信方），不在容器里。**
容器里跑物化 = 让不可信方决定自己拿到什么数据。所以到了容器里，provider
已经是一份**核过根的既成事实**，被测系统要做的只有一件事：知道它在哪、把
``provider_uri`` 交给 ``qlib.init``。

**PA-3：两臂不共享 provider 目录、不共享只读挂载。** 所以这里的 `ensure()`
默认**原地返回**，不复制 —— 复制一份到别处只会多一个可写入口。
只有调用方明确给了 `dest` 时才复制，且复制后核文件数与总字节数（截断在这里
不会抛异常，症状是「因子算出来了，就是数不对」）。

用法::

    import qlib
    from genebench_client import qlib_provider
    qlib.init(**qlib_provider.qlib_init_kwargs())      # provider_uri=/task/provider, region=cn
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from .errors import GenebenchClientError

#: 容器里 provider 的落点。compose 把 run dir 的 ``work/`` 挂成 ``/task``，
#: `runner/provider_adapter.py::WORK_PROVIDER_REL = "provider"` → ``/task/provider``。
CONTAINER_PROVIDER_URI: str = "/task/provider"

#: 覆盖用的环境变量。TK-4 的备用落点（**条件式批准，现在没启用**；
#: 路径写在 `ops/status_lock.py::TK4_CONTAINER_PATH` 里，本文件**刻意不复写那个字面量** ——
#: `ops/test_status_lock.py::test_tk4_fallback_path_is_not_enabled` 全仓扫它，
#: 写进来就等于宣布启用，而启用要同步改写卡 4.1 的 FS-A/T10）若将来启用，也走这个变量。
PROVIDER_ENV: str = "GENEBENCH_PROVIDER_URI"

#: qlib 的地区。A 股冻结 provider 一律 ``cn``。
REGION: str = "cn"


class ProviderMissing(GenebenchClientError):
    """provider 树不在。**不回落到社区 channel** —— 那是运行期换数据源（PA-5）。"""


def provider_uri() -> str:
    """provider 树的路径。**存在性是判据，不是假设。**"""
    raw = (os.environ.get(PROVIDER_ENV) or "").strip() or CONTAINER_PROVIDER_URI
    p = Path(raw)
    if not p.is_dir():
        raise ProviderMissing(
            f"provider 树不在 {p} —— 它由 runner 在**注入期**物化并核过根"
            f"（卡 4.3 §7 PA-2/PA-6），容器里只该读不该造。"
            f"**不要回落到 qlib 社区 channel**：那是运行期换数据源（PA-5），"
            f"而且社区那份的 amount 是千元、volume 是手，与本环境差 1000×/100×。"
            f"路径不对请设 {PROVIDER_ENV}")
    return str(p)


def stats(root: str | None = None) -> dict:
    """文件数与总字节。`ensure()` 的复制后自检用它，调用方也可以拿来记账。"""
    p = Path(root or provider_uri())
    n, size = 0, 0
    for f in p.rglob("*"):
        if f.is_file():
            n += 1
            size += f.stat().st_size
    return {"root": str(p), "n_files": n, "n_bytes": size}


def ensure(dest: str | os.PathLike | None = None) -> str:
    """确认 provider 可用，返回可直接喂给 ``qlib.init`` 的 ``provider_uri``。

    * ``dest`` 为空（正常路径）→ 原地校验并返回，**不复制**（PA-3）。
    * ``dest`` 给了且与源不同 → 复制一份，复制后**核文件数与总字节数**。
      盘满时 `copytree` 可能只写了一半而返回成功 —— 那是一个不会抛异常的错误。
      注意这里核的是**规模**不是 sha256 根：根的权威校验在
      `runner/provider_adapter.py`（可信方，注入期），容器里再核一遍
      既拿不到 pin 文件，也不构成第二个权威。
    """
    src = provider_uri()
    if dest is None:
        return src
    d = Path(dest)
    if d.resolve() == Path(src).resolve():
        return src
    before = stats(src)
    if before["n_files"] == 0:
        raise ProviderMissing(f"{src} 是空目录 —— 没有 provider 可用")
    if d.exists():
        raise ProviderMissing(
            f"{d} 已存在 —— 不覆盖：两臂**不共享** provider（PA-3），"
            f"覆盖也会让「这一份是哪一版」这个问题答不出来")
    d.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, d)
    after = stats(d)
    if (after["n_files"], after["n_bytes"]) != (before["n_files"], before["n_bytes"]):
        shutil.rmtree(d, ignore_errors=True)
        raise ProviderMissing(
            f"复制到 {d} 后规模对不上（{after['n_files']}/{after['n_bytes']} ≠ "
            f"{before['n_files']}/{before['n_bytes']}）—— 复制被截断。"
            f"症状会是「因子算出来了，就是数不对」，所以这里当场抛而不是继续")
    return str(d)


def qlib_init_kwargs(dest: str | os.PathLike | None = None) -> dict:
    """``qlib.init(**qlib_init_kwargs())``。"""
    return {"provider_uri": ensure(dest), "region": REGION}
