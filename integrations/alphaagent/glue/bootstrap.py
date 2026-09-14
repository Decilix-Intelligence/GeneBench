# -*- coding: utf-8 -*-
"""接线①：在 `import alphaagent` **之前**把进程环境摆好。

顺序是有讲究的，两件事都必须发生在系统被 import 之前：

**(a) 顶替 `tushare`。** AlphaAgent 的 `alphaagent/data/__init__.py` 顶层就
`from alphaagent.data.tushare_client import get_pro`，而那个模块顶层
`import tushare as ts`。而 `alphaagent/factor/mining/session.py` 又
`from alphaagent.data.panel import load_panel`，于是**只要 import 到
`alphaagent.factor.mining.loop`（我们要用的 agent 循环），就一定会 import 到
`tushare`**。镜像里**没装** tushare（红线 5：不给被测系统一条绕过数据面的路），
所以这里用垫片的 `compat.install("tushare")` 把它顶替成经网关的兼容层
（`integrations/README.md` §1③ 的 (d) 那条写法）。

替换的是什么，说清楚：`sys.modules["tushare"]` →
`genebench_client.compat.tushare`。被替换的上游对象是 tushare 官方包的
`pro_api()` / `DataApi.daily|trade_cal|adj_factor|stk_limit|index_weight|suspend_d`。
**AlphaAgent 自己一行代码都没改** —— 它照样 `import tushare as ts`，
只是拿到的那个模块换了实现，取数走 `http://gateway:18080` 并落 access_log。

> 面板本身**不经 compat 取**：compat 层的 `fields` 只裁剪返回值、不改变网关上的
> 读取集（垫片 README §4），而 S3 的「声明读取集 vs 实际读取集」探针是从
> access_log 反推的。所以 `glue/panel.py` 用 `gb.client().bars(..., fields=[...])`
> 显式声明字段。compat 在这里的职责只有两条：让 import 链走得通；万一系统内部
> 真去取数，那条路也通到网关而不是 tushare.pro。

**(b) 关掉 AlphaAgent 会往仓库根写东西的默认路径。** 它的
`alphaagent/core/paths.py` 把 `ROOT` 算成安装目录的上两级（在镜像里是
site-packages），`logs/factor_mining` 之类是相对当前工作目录 —— 而当前工作目录
是 `/task`，那是 run dir 的 `work/` 本身，多写一个文件就是 run.json 里的
`unexpected`。所以日志目录显式指到 `/tmp` 下（`integrations/README.md` §1④）。
"""
from __future__ import annotations

import os
import pathlib
import sys

#: 中间产物一律落容器可写层，不落 `/task`。
SCRATCH = pathlib.Path("/tmp/gb_alphaagent")
LOG_DIR = SCRATCH / "mining_log"


def apply() -> dict:
    """摆环境 + 顶替 tushare。返回一份可以打进日志的快照（**不含任何 key**）。"""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # HOME 必须可写：AlphaAgent 不主动写 HOME，但 openai / joblib 会摸 ~/.cache。
    home = os.environ.get("HOME") or "/tmp/h"
    if not home.startswith("/tmp"):
        home = "/tmp/h"
    os.environ["HOME"] = home
    pathlib.Path(home).mkdir(parents=True, exist_ok=True)

    # numba 没装 → accel.py 的 njit 退化成恒等装饰器，内核走纯 Python 循环。
    # 这里**不设** FUTURE_ALPHA_MINER_ACCEL_BACKEND：设成 "numba" 会让
    # `_use_cxx_backend()` 返回 False（本来就是），设成 "cxx" 会直接抛。
    # 留空 = auto = 用可用的那个，正是我们要的。

    import genebench_client.compat as compat
    replaced = compat.install("tushare")

    return {
        "home": home,
        "scratch": str(SCRATCH),
        "log_dir": str(LOG_DIR),
        "sys_modules_replaced": replaced,
        "gateway": os.environ.get("GENEBENCH_GATEWAY") or os.environ.get("GENEBENCH_GATEWAY_URL"),
        # 只报**有没有**，不报值。红线 3：凭据不进日志。
        "openai_base_url_set": bool(os.environ.get("OPENAI_BASE_URL")),
        "openai_api_key_set": bool(os.environ.get("OPENAI_API_KEY")),
        "python": sys.version.split()[0],
    }
