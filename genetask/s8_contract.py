# -*- coding: utf-8 -*-
"""S8 模拟盘的**契约常量**：委托状态机迁移表 + 可交易性词汇。**零依赖**（只用标准库），
**尤其不 import `reference/`**。

为什么单独成文件（用户裁定 ⑧，2026-09-10）：`gateway/sim_engine.py` 顶上那一行
`from reference.artifact_schema import LEGAL_TRANSITIONS, TRADABILITY_STATES, UNTRADABLE_STATES`
是全树**唯一**一条「网关 import 答案面」。它的代价不是风格 —— 红线 B2 要求 `reference/`
不上执行面，而单机双容器形态里网关与 harness 同机起；带着这一行的网关
**在执行面根本 import 不起来**，于是手册 §1.1「两种形态跑同一套代码」那句话不成立。

为什么不各留一份（本文件唯一值得写下来的判断）：抄第二份，两份必然漂，而漂的表现是
「校验器说合法、环境说非法」或者反过来，**两边都不报错** —— `gateway/sim_engine.py`
自己的模块 docstring 逐字写着这条，并据此选择了 import 而不是重抄。⑧ 要改的不是那个判断，
是**被 import 的那一端住在答案面**。所以是「抽出来共用」，不是「各留一份」。

放在 `genetask/` 而不是 `reference/` 或 `gateway/`：
* `genetask/` 与 `gateway/` 都在执行面拿得到（`ops/push_exec_to_f02.sh` 同步 genetask/ops/runner/vendor），
  但常量的**另一个消费者是 `reference/artifact_schema.py`**，而答案面 import 网关代码同样别扭；
  `genetask/` 是两边都本来就依赖的那一层。
* `genetask/pin.py` 早就示范过这条路：「冻结物的契约常量、零依赖、单独一个文件、
  由 `schema.py` 再导出」。同一个理由、同一个形状，不新发明。

**本文件不许 import `genetask.schema`**：它顶层 `from reference import artifact_schema`，
import 它等于把答案面原样拖回来 —— 那正是本文件要拆掉的那条边。
`ops/test_s8_contract.py` 用 AST（不是 grep 字符串）钉住「`gateway/**` 与本文件都不 import reference」。
"""
from __future__ import annotations

#: **可交易性状态的词汇**（`/tradability` 的 `status` 列）。单一定义在这里 ——
#: 卡 4.4 的模拟盘引擎原先自抄了一份 `ok/suspend/limit_up/limit_down/delisted/no_data`，
#: 其中 `ok`/`limit_up`/`limit_down`/`delisted` **都不是真实取值**，于是那几条拒单分支
#: 从来不触发，而未知状态还 fail-open（红队 2026-09-04）。涨跌停由 `limit_*` 字段判，
#: 不是 status 的取值 —— 两件事不要混。
TRADABILITY_STATES: frozenset[str] = frozenset({"trade", "suspend", "no_data"})
#: 不可成交的状态。`trade` 之外一律不可成交（fail-closed）。
UNTRADABLE_STATES: frozenset[str] = TRADABILITY_STATES - {"trade"}

#: **委托状态机的合法迁移**（契约 §5）。`gateway/sim_engine.py` 的 `ORDER_STATES` 由它的
#: 节点集导出，`reference/artifact_schema.py` 的 `$.payload.*.state` 枚举也由它导出 ——
#: 三处同源，改这里一处三处一起动。
LEGAL_TRANSITIONS: frozenset[tuple[str, str]] = frozenset({
    ("idle", "ordered"), ("ordered", "filled"), ("ordered", "cancelled"),
    ("ordered", "partial"), ("partial", "filled"), ("partial", "cancelled"),
    ("filled", "idle"), ("cancelled", "idle"),
})
