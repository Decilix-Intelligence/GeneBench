# -*- coding: utf-8 -*-
"""as_of 强制与越界判定 —— **全网关唯一的一份实现**。

所有端点都必须过这里，不许各写各的。理由：越界有**六条**不同的路径
（见 `Reason`），只堵最显眼的那条等于没堵。把判定收进一个模块，
新增端点时漏判会立刻在 `ops/test_gateway.py` 的参数化里暴露。

两条不变量：

1. **as_of 自身也要夹到冻结线**（红线 7）。``as_of=2026-09-01`` 不是
   "看见未来"，是"越过 v1 的数据边界"，同样 403。
2. **判定必须先于取数**。403 要在碰湖之前发生，否则"查完再判"会在
   日志里留下一次实际读取 —— 卡 5.1 结算前视时分不清"读了但没给"
   和"根本没读"。
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Iterable

import genebench_config as cfg

from .errors import GatewayDenied, Reason

#: 冻结线的紧凑形态。v1 的一切上界。
FREEZE_COMPACT: str = cfg.FREEZE_DATE.replace("-", "")

_COMPACT = re.compile(r"^\d{8}$")
_DASHED = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


def normalize_date(value: str, *, field: str) -> str:
    """把 ``YYYY-MM-DD`` / ``YYYYMMDD`` 归一成紧凑 ``YYYYMMDD``。

    **刻意只认这两种**。`2026/07/31`、带时区、带空格、带 `T00:00:00`
    一律拒 —— 宽进严出在 as_of 这种授权参数上是反模式：
    一个被"好心"解析成别的日期的输入，就是一次静默越权。

    Raises:
        GatewayDenied: 422 / `PARAM_MALFORMED`。
    """
    if value is None:
        raise GatewayDenied(
            Reason.PARAM_MALFORMED, f"{field} 不能为空", status=422,
            context={"field": field},
        )
    raw = value.strip()
    if _COMPACT.match(raw):
        compact = raw
    else:
        m = _DASHED.match(raw)
        if not m:
            raise GatewayDenied(
                Reason.PARAM_MALFORMED,
                f"{field}={value!r} 格式非法；只接受 YYYY-MM-DD 或 YYYYMMDD",
                status=422,
                context={"field": field, "value": value},
            )
        compact = "".join(m.groups())
    try:
        dt.date(int(compact[:4]), int(compact[4:6]), int(compact[6:]))
    except ValueError as exc:
        raise GatewayDenied(
            Reason.PARAM_MALFORMED,
            f"{field}={value!r} 不是一个真实日期（{exc}）",
            status=422,
            context={"field": field, "value": value},
        ) from exc
    return compact


def parse_asof(value: str | None) -> str:
    """校验 as_of 并返回紧凑形态。

    Raises:
        GatewayDenied: 缺参 422 / 格式非法 422 / 越过冻结线 403。
    """
    if value is None or str(value).strip() == "":
        raise GatewayDenied(
            Reason.ASOF_MISSING,
            "as_of 是必填参数：网关的每一次取数都必须声明视角日期",
            status=422,
        )
    try:
        compact = normalize_date(str(value), field="as_of")
    except GatewayDenied as exc:
        # 归一化失败时换成 as_of 专属的 reason 码，便于日志聚合
        raise GatewayDenied(
            Reason.ASOF_MALFORMED, exc.detail, status=422, context=exc.context
        ) from exc
    if compact > FREEZE_COMPACT:
        raise GatewayDenied(
            Reason.ASOF_BEYOND_FREEZE,
            f"as_of={compact} 越过 v1 冻结线 {FREEZE_COMPACT}（红线 7）",
            context={"as_of": compact, "freeze_line": FREEZE_COMPACT},
        )
    return compact


#: 运行内 `as_of` 上界的提供者。由 `routers/sim.py` 在 import 时注册 ——
#: 这样 `asof` 不反向 import sim（会成环），而**判定仍然只在本模块做一次**
#: （模块注释的那条：所有端点都必须过这里，不许各写各的）。
_RUN_CEILING = None


def register_run_ceiling(fn) -> None:
    global _RUN_CEILING
    _RUN_CEILING = fn


def run_asof_ceiling(run_id: str | None, task_id: str | None) -> str | None:
    """这次运行的 `as_of` 上界（紧凑形态）。没有模拟盘会话就没有额外上界。

    **键是 `run_id` 不是 `config_id`**（裁定 N-88，2026-09-05）：`config_id` 在同一次
    benchmark 里可以有多个（三配置），而"这次运行"只有一个 —— 用 config_id 当键，
    换一个 config_id 就是一个新会话、新上界、新账户。`run_id` 由边车从 run dir 渲染的
    环境变量注入，容器改不到（ID-1/ID-2，且 N-91 把行界走私那条旁路封了）。
    """
    if _RUN_CEILING is None or not run_id or not task_id:
        return None
    d = _RUN_CEILING(run_id, task_id)
    return normalize_date(d, field="sim_date") if d else None


#: S8 题的 task_id 前缀。**阶段从 task_id 取**，而 task_id 由边车按 runner 真值注入 ——
#: 不是被测方自报的字段（N-36 的同族判据）。
S8_TASK_PREFIX = "s8-"


def guard_run_ceiling(as_of: str, run_id: str | None, task_id: str | None) -> str:
    """**S8 的前视堵在这里**（卡 4.4 §2.2）。

    没有它，S8 的前视是**免费**的：agent 在 `sim_date = 2026-03-02` 时直接向
    `/bars` 请求 `as_of=2026-07-31`，拿到未来三个月的价格再决定今天下什么单。
    数据面全程合法（没越冻结线）、网关日志全绿，而这次运行的交易决策是拿未来做出来的。

    **沿用既有的越界 reason，不新造一个 sim 专用的** —— 前视就是前视，
    卡 5.1 的探针按同一批 reason 结算。
    """
    ceiling = run_asof_ceiling(run_id, task_id)
    # **没有上界不等于没有约束**（红队 2026-09-05）。S8 的上界来自模拟盘会话；
    # 会话还没建起来时，`ceiling` 是 None，于是这道门整体静默 ——
    # agent 只要先取数后交易，前视就是免费的。判据取 task_id 的阶段前缀：
    # 它来自 runner 真值（边车注入），不是被测方自报的东西。
    if not ceiling and str(task_id or "").startswith(S8_TASK_PREFIX):
        raise GatewayDenied(
            Reason.ASOF_BEYOND_FREEZE,
            f"S8 运行（task_id={task_id}）还没有模拟盘会话，因而没有 as_of 上界 —— "
            f"先建会话（任一 /sim/* 请求）再取数。**没有上界不是放行的理由**："
            f"先取完未来数据再开始交易，数据面全程合法而决策是拿未来做的",
            context={"as_of": as_of, "run_ceiling": None, "task_id": task_id,
                     "freeze_line": FREEZE_COMPACT},
        )
    if ceiling and as_of > ceiling:
        raise GatewayDenied(
            Reason.ASOF_BEYOND_FREEZE,
            f"as_of={as_of} 越过本次运行的上界 {ceiling}（当前 sim_date）—— "
            f"推进之后上界才前移。在 sim_date 之前就取到 sim_date 之后的数据，"
            f"等于拿未来做今天的交易决策，而数据面全程看起来合法",
            context={"as_of": as_of, "run_ceiling": ceiling,
                     "freeze_line": FREEZE_COMPACT},
        )
    return as_of


def guard_target(
    target: str, as_of: str, *, field: str, reason: Reason = Reason.TARGET_AFTER_ASOF
) -> str:
    """单个目标日期不得晚于 as_of。"""
    compact = normalize_date(target, field=field)
    if compact > as_of:
        raise GatewayDenied(
            reason,
            f"{field}={compact} 晚于 as_of={as_of}",
            context={"field": field, "value": compact, "as_of": as_of},
        )
    return compact


def guard_range(
    start: str | None,
    end: str | None,
    as_of: str,
    *,
    require_end: bool = False,
) -> tuple[str, str]:
    """区间的三条越界路径一次堵完，返回夹紧后的 ``(start, end)``。

    - 显式 ``end > as_of`` → 403 `RANGE_END_AFTER_ASOF`
    - **开区间**（不给 end）→ 403 `OPEN_RANGE_AFTER_ASOF`，除非
      调用方接受"隐式夹到 as_of"。默认**拒绝**：开区间的语义是
      "一直到最新"，而"最新"在 as_of 视角下是未定义的，静默夹紧
      等于替调用方做了一个它没声明的决定。
    - ``start > end`` → 422

    Args:
        require_end: True 时缺 end 直接 422（用于必须显式声明窗口的端点）。
    """
    lo = normalize_date(start, field="start_date") if start else None
    if end is None or str(end).strip() == "":
        if require_end:
            raise GatewayDenied(
                Reason.PARAM_MALFORMED,
                "end_date 必填：本端点不接受开区间",
                status=422,
            )
        raise GatewayDenied(
            Reason.OPEN_RANGE_AFTER_ASOF,
            "不接受开区间：不给 end_date 等于要“到最新为止”，"
            "而“最新”在 as_of 视角下未定义。请显式给 end_date（<= as_of）。",
            context={"as_of": as_of},
        )
    hi = guard_target(end, as_of, field="end_date", reason=Reason.RANGE_END_AFTER_ASOF)
    if lo is None:
        lo = "19900101"
    if lo > hi:
        raise GatewayDenied(
            Reason.PARAM_MALFORMED,
            f"start_date={lo} 晚于 end_date={hi}",
            status=422,
            context={"start_date": lo, "end_date": hi},
        )
    return lo, hi


def guard_codes(codes: Iterable[str] | None) -> list[str] | None:
    """代码列表基本校验（形如 ``600000.SH``）。"""
    if not codes:
        return None
    out: list[str] = []
    for c in codes:
        raw = str(c).strip().upper()
        if not re.match(r"^[0-9A-Z]{6}\.[A-Z]{2}$", raw):
            raise GatewayDenied(
                Reason.PARAM_MALFORMED,
                f"code={c!r} 不是湖内形态（形如 600000.SH）",
                status=422,
                context={"code": c},
            )
        out.append(raw)
    return sorted(set(out))
