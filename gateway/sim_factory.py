# -*- coding: utf-8 -*-
"""S8 模拟盘的**会话工厂**：`(config_id, task_id)` → `SimEngine`。

**它回答的是「会话从哪来」这个结构问题**（`routers/sim.py` 的模块 docstring 写过，
但生产路径上一直**没有人注册过工厂**）——`_FACTORY is None` 时五个 `/sim/*` 端点
一律 404「这次运行没有模拟盘会话」。也就是说：S8 的四道题在真网关上从来跑不通，
而这件事没有任何一条测试会红，因为测试自己注册工厂（`ops/test_sim_endpoints.py:450`）。
`ops/test_sim_factory.py::test_production_app_registers_a_factory` 是补上的那条。

**构造参数全部来自数据面，且全部是 agent 在题面里已经看得到的东西**：

| 参数 | 来源 | 为什么不来自别处 |
| --- | --- | --- |
| `permitted_operations` / `visible_state_fields` / `slippage_reference_price` | 该题 `task.yaml` 的 `declared` | D-32：题面读得出来的，一律不从环境拿 |
| `calendar` | 湖 `trade_cal`（`declared.calendar_id` 指定的交易所）| 与 `/calendar` 同源，两处不一致会让 agent 与环境对不上日子 |
| `closes` / 涨跌停 | 冻结的 tradability 产物 | 与 `/tradability`、`/bars` 同源 |
| `opens` | 湖 `daily` | `slippage_reference_price=open` 时才用得到；缺了会让滑点静默取错基准 |

**不读答案面**：只从 `task.yaml` 取 `window` / `universe` / `declared` 四个键，
canary 段与 gold token 一个字都不碰（`ops/test_sim_factory.py` 有一条盯着）。

**不做成端点**：`/sim/session` 会是一条被测方够得着的装配路径 ——
它能自己造一个 `permitted_operations` 全开的会话，越权就测不出来了。
"""
from __future__ import annotations

import functools
import os
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

import genebench_config as cfg
from snapshots import tradability as tr
from snapshots import universe_build as ub

from . import backends
from .sim_engine import SimEngine

#: 只有 `s8-` 开头的任务有模拟盘。其余阶段返回 `None` ——
#: 返回一个空引擎会给 S1..S7 凭空造出一个 `as_of` 上界（`current_sim_date` 拿它当上界）。
TASK_PREFIX = "s8-"

#: 题面 `declared` 里、本工厂**认得**的键。多出来的键说明契约动了而工厂没跟上，
#: 静默忽略的话表现是「声明了但环境没照做」，没有一处会报。
KNOWN_DECLARED = frozenset({"visible_state_fields", "permitted_operations",
                            "matching_frequency", "calendar_id",
                            "slippage_reference_price"})

#: v1 只做日频撮合。别的频率不是「先按日频顶上」，是**不认识**。
SUPPORTED_MATCHING = ("daily",)

#: 本进程造过的会话：`{run_id, task_id}`，按发生顺序。
#:
#: **为什么还留着**（N-88 已按裁定关闭：键从 `config_id` 改成 `run_id`）：
#: `run_id` 由边车注入、容器改不到，所以容器内的被测方再也开不出第二个会话。
#: 但**不经边车的调用方**（f01 上的 oracle、手写脚本）仍然自己填头 ——
#: 那一侧不是威胁模型里的对手，可它一旦填错，表现是「同一道题多出一个会话」。
#: 留痕是纵深：同一个 `task_id` 出现第二个 `run_id`，这里就有两条。
SESSIONS_CREATED: list[dict[str, str]] = []


def creation_ledger(task_id: str | None = None) -> list[dict[str, str]]:
    return [r for r in SESSIONS_CREATED if task_id is None or r["task_id"] == task_id]


def reset_ledger() -> None:
    SESSIONS_CREATED.clear()


#: 本进程服务的出集。**没有默认值可猜** —— 见 `task_dir`。
SET_ID_ENV = "GENEBENCH_SET_ID"
DEFAULT_SET_ID = "v1.0-smoke"


def configured_set_id() -> str:
    """网关这一次服务的是哪个出集。部署事实，不是任务事实，所以走环境变量。"""
    return os.environ.get(SET_ID_ENV) or DEFAULT_SET_ID


def task_dir(task_id: str, set_id: str) -> Path:
    """**`set_id` 必填**（N-578，用户裁定 ③，2026-09-11）。

    原来它可以不给，缺了就 glob `tasks/*/<task_id>`。那条路在实例层落盘之后**走不通**：
    `v1.0-smoke/s8-cor-01` 与 `v1.0-instances/s8-cor-01` 同时存在，glob 命中两个，
    函数按设计 `RuntimeError` 不猜 —— 于是 S8 四道题的 gold 一份都算不出来。
    根因在发号规则（已在 `ops/mk_instances.allocate_task_ids` 改掉），
    但**光改发号规则不够**：盘上那些已经落好的旧目录不会自己消失，
    而「猜」这件事本身就不该留在生产路径上。
    """
    if not set_id:
        raise ValueError(
            f"task_dir 的 set_id 必填：同一个 task_id 可以在多个出集里各有一份"
            f"（{task_id} 在 v1.0-smoke 与 v1.0-instances 都有），"
            f"按哪一份构造会话是歧义。网关侧从 {SET_ID_ENV} 取（默认 {DEFAULT_SET_ID}）")
    d = cfg.GENEBENCH_ROOT / "reference" / "tasks" / set_id / task_id
    if not (d / "task.yaml").is_file():
        raise FileNotFoundError(f"找不到 {set_id}/{task_id} 的任务目录（{d}）")
    return d


def read_task_face(task_id: str, set_id: str) -> dict[str, Any]:
    """只取 X 面的四个键。**不返回整份 task.yaml** —— 返回整份就等于把答案面递给了调用方。"""
    doc = yaml.safe_load((task_dir(task_id, set_id) / "task.yaml").read_text(encoding="utf-8"))
    face = {k: doc[k] for k in ("stage", "window", "universe", "declared") if k in doc}
    missing = [k for k in ("stage", "window", "universe", "declared") if k not in face]
    if missing:
        raise ValueError(f"{task_id} 的 task.yaml 缺 {missing} —— 缺了不许拿默认值顶上")
    if face["stage"] != "S8":
        raise ValueError(f"{task_id} 的 stage 是 {face['stage']}，不是 S8")
    unknown = sorted(set(face["declared"]) - KNOWN_DECLARED)
    if unknown:
        raise ValueError(f"{task_id} 声明了本工厂不认识的字段 {unknown} —— "
                         f"静默忽略会让「声明了但环境没照做」永远发现不了")
    return face


def trading_days(exchange: str, start: str, end: str) -> list[str]:
    out = backends.read_table(
        "trade_cal",
        where="exchange = ? AND cal_date >= ? AND cal_date <= ?",
        params=[exchange, start.replace("-", ""), end.replace("-", "")],
        columns="cal_date, is_open")
    if out is None or len(out) == 0:
        raise RuntimeError(f"{exchange} 在 {start}..{end} 没有日历行 —— 模拟盘没有可推进的日子")
    d = out.loc[out["is_open"].astype(bool), "cal_date"].astype(str).str.replace("-", "", regex=False)
    return sorted(pd.to_datetime(d, format="%Y%m%d").dt.strftime("%Y-%m-%d"))


def window_symbols(universe: str, days: list[str]) -> list[str]:
    """窗口内**任一日**在成分里的票的并集。

    只取首日名单是不够的：窗口中途调入的票，agent 从 `/universe` 看得到、
    下单却会因为 `closes` 里没有它而被当成「没有价格」拒掉 —— 而拒掉的理由
    与真正的停牌拒单**长得一模一样**。
    """
    seen: set[str] = set()
    for d in days:
        seen.update(ub.universe_at(universe, d.replace("-", "")))   # 它只收紧凑串
    return sorted(seen)


@functools.lru_cache(maxsize=4)
def _tradability_year(year: int) -> pd.DataFrame:
    return tr.read_tradability(years=[year])


#: 湖里 tradability 的 `status` 取值（2026 分区实测：trade / suspend / limit_up / limit_down）
#: → 引擎认识的三个（`reference.artifact_schema.TRADABILITY_STATES`）。
#:
#: **涨跌停不是「不可交易」**：那两天票在交易，只是价格贴在板上 ——
#: 契约里涨停**只挡买**、跌停**只挡卖**（`sim_engine._match` 的 307-310 行）。
#: 原样把 `limit_up` 塞进 `tradable`，引擎走的是 fail-closed 分支
#: （`unknown_tradability:limit_up`），**买卖两边一起拒**，而 gold 会照样出数。
STATUS_TO_ENGINE = {"trade": "trade", "suspend": "suspend", "no_data": "no_data",
                    "limit_up": "trade", "limit_down": "trade"}

#: 板上收盘的判据。实测 `status == "limit_up"` 与 `limit_up_close` **逐行等价**
#: （2026-07 窗口：1991 行对 1991 行；`limit_down` 1253 对 1253）。
#: **不用 `limit_touched_*`** —— 盘中触板但收盘没封住的有 912 行 status 是 `trade`，
#: 而撮合在收盘，收盘能成交就不该拒。
LIMIT_STATUS = {"limit_up": "up", "limit_down": "down"}


def market_frames(symbols: list[str], days: list[str]) -> dict[str, Any]:
    """一次读，出四样：`closes` / `opens` / `tradable` / 涨跌停两个集合。

    合并成一个函数是有意的：分两个函数各读一遍 tradability，
    两份过滤条件会慢慢漂开，而漂开的表现是「拒单理由与价格来自不同的日子」。
    """
    years = sorted({int(d[:4]) for d in days})
    t = pd.concat([_tradability_year(y) for y in years], ignore_index=True)
    t = t.assign(date=t["date"].astype(str).str.slice(0, 10),
                 code=t["code"].astype(str).str.strip().str.upper())
    day_set, sym_set = set(days), set(symbols)
    t = t[t.date.isin(day_set) & t.code.isin(sym_set)]
    if t.empty:
        raise RuntimeError(f"tradability 在 {days[0]}..{days[-1]} 对这 {len(symbols)} 只票"
                           f"一行都没有 —— 空盘不许当成「全部停牌」往下跑")
    seen = set(t.status.dropna().astype(str).unique())
    unknown = sorted(seen - set(STATUS_TO_ENGINE))
    if unknown:
        raise RuntimeError(f"tradability 出现本工厂没登记的 status {unknown} —— "
                           f"映射表漏一个取值，引擎会走 fail-closed 把它当成两边都拒，"
                           f"而 gold 照样出数（`sim_engine._match` 的 unknown_tradability 分支）")

    closes: dict[tuple[str, str], float] = {}
    tradable: dict[tuple[str, str], str] = {}
    up: set[tuple[str, str]] = set()
    dn: set[tuple[str, str]] = set()
    for r in t.itertuples():
        key = (r.date, r.code)
        if pd.notna(r.close):
            closes[key] = float(r.close)
        st = str(r.status) if pd.notna(r.status) else "no_data"
        tradable[key] = STATUS_TO_ENGINE[st]
        side = LIMIT_STATUS.get(st)
        if side == "up":
            up.add(key)
        elif side == "down":
            dn.add(key)

    ph = ", ".join("?" * len(symbols))
    daily = backends.read_table("daily", where=f"ts_code IN ({ph})", params=list(symbols),
                                columns="ts_code, trade_date, open")
    opens: dict[tuple[str, str], float] = {}
    if daily is not None and len(daily):
        n = daily["trade_date"].astype(str).str.slice(0, 10).str.replace("-", "", regex=False)
        daily = daily.assign(date=n.str[:4] + "-" + n.str[4:6] + "-" + n.str[6:8],
                             code=daily["ts_code"].astype(str).str.strip().str.upper())
        daily = daily[daily.date.isin(day_set)]
        opens = {(r.date, r.code): float(r.open) for r in daily.itertuples() if pd.notna(r.open)}
    if not opens:
        raise RuntimeError("daily 里一个 open 都没匹配上 —— "
                           "`slippage_reference_price=open` 的题会静默拿不到基准价")
    return {"closes": closes, "opens": opens, "tradable": tradable,
            "limit_up": up, "limit_down": dn}


def build_engine(run_id: str, task_id: str, *, set_id: str) -> "SimEngine | None":
    """工厂本体。非 S8 返回 `None`（**不是**空引擎）。

    `set_id` **必填无默认**（N-578，裁定 ③）：默认值在这里意味着「同号就挑一个」，
    而同号的两道题窗口与宇宙都可以不同 —— 挑错了表现是「账户里有一批不属于这道题的持仓」，
    没有一处会报。调用方（`gateway/routers/sim.py` 的工厂注册与两处物化路径）一并改。
    """
    if not task_id.startswith(TASK_PREFIX):
        return None
    face = read_task_face(task_id, set_id)
    d = face["declared"]
    freq = d.get("matching_frequency")
    if freq not in SUPPORTED_MATCHING:
        raise ValueError(f"{task_id} 声明 matching_frequency={freq!r}，v1 只做 {SUPPORTED_MATCHING}")
    days = trading_days(d.get("calendar_id", "SSE"), face["window"]["start"], face["window"]["end"])
    symbols = window_symbols(face["universe"], days)
    mkt = market_frames(symbols, days)
    eng = SimEngine(
        calendar=days, window_end=days[-1],
        closes=mkt["closes"], opens=mkt["opens"], tradable=mkt["tradable"],
        limit_up=mkt["limit_up"], limit_down=mkt["limit_down"],
        slippage_reference_price=d.get("slippage_reference_price"),
        permitted_operations=tuple(d["permitted_operations"]))
    # `visible_state_fields` 不是 SimEngine 的 dataclass 字段 —— router 用 getattr 取。
    # 在这里挂上，是为了让「题面声明了什么」与「端点返回什么」只有一个来源。
    eng.visible_state_fields = tuple(d["visible_state_fields"])
    SESSIONS_CREATED.append({"run_id": run_id, "task_id": task_id})
    return eng


def register(app=None, *, set_id: str | None = None) -> None:
    """把工厂挂进 router。`create_app()` 里调一次。

    **本进程服务的 `set_id` 在这里定下来**，随工厂一起登记 —— 会话键因此带得上它
    （`routers/sim.py::_SESSIONS`），同号不同集的两道题不会共用一个账户。
    """
    from .routers import sim
    sim.register_session_factory(build_engine, set_id=set_id or configured_set_id())
