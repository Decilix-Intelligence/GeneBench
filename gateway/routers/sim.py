# -*- coding: utf-8 -*-
"""模拟盘端点（卡 4.4）：``/sim/state`` ``/sim/order`` ``/sim/cancel``
``/sim/advance`` ``/sim/log``。

**挂在数据网关同一服务、同一端口下**（卡 4.4 §1.1）：任务容器只被允许打到网关，
另起一个服务就要么再开一条出向白名单、要么让 `/sim/*` 从任务网络够不着 ——
前者放宽隔离面，后者根本跑不起来。

**两条与既有网关一致的纪律**：

* 拒绝一律经 `GatewayDenied` 抛 —— 于是它自动落进 `access_log`
  （`app.py` 的 exception handler）。**先前 sim 的拒单抛的是 `SimError`，
  永远进不了 access_log，于是「越权率」根本没有数据源**（N-45）。
* 切片键取 **runner 真值**，不取请求头里的自报值 —— 头是被测方给的。
  这是 N-36 那个洞的环境侧对应物：**不在环境侧把它还原**。
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request

import genebench_config as cfg

from .. import asof as _asof
from ..errors import GatewayDenied, Reason
from ..sim_engine import SimEngine, SimError

router = APIRouter()

#: 会话表：`(run_id, task_id)` → 引擎。**键是 runner 真值**（裁定 N-88，2026-09-05）。
#:
#: 为什么不是 `config_id`：同一次 benchmark 里 config_id 可以有多个（三配置各跑一遍），
#: 而"这次运行"只有一个。拿 config_id 当键，换一个 config_id 就是一个**全新账户**
#: （现金复位、`sim_date` 复位）—— 被测方可以并行试很多条交易序列再挑最好的重放。
#: `run_id` 由边车从 run dir 渲染的环境变量注入（ID-1/ID-2），容器改不到；
#: N-91 把「行界走私」那条能伪造任意身份头的旁路也封了。
#: 进程内存 —— 一次 benchmark 运行期间网关常驻，会话随进程生灭。
#: 落盘的权威是 `/sim/log`（契约 §6 的 Audit 判据由它结算），不是这张表。
#: **键里带 `set_id`**（N-578，用户裁定 ③，2026-09-11）：同一个 `task_id` 在
#: `v1.0-smoke` 与 `v1.0-instances` 里各有一份，窗口与宇宙可以不同。
#: 不带它，同号不同题共用一个账户 —— 表现是「持仓里有一批不属于这道题的票」，没有一处会报。
_SESSIONS: dict[tuple[str, str, str], SimEngine] = {}

#: 工厂登记时一并记下的、本进程服务的出集。`None` = 还没登记过工厂。
_FACTORY_SET_ID: str | None = None


def factory_set_id() -> str:
    """会话键与工厂都用它。没登记过工厂时退回默认集 —— 那条路只在单测里走得到。"""
    from ..sim_factory import DEFAULT_SET_ID
    return _FACTORY_SET_ID or DEFAULT_SET_ID


class SessionError(GatewayDenied):
    pass


def reset_sessions() -> None:
    """测试与换任务时清干净。生产路径不调 —— 会话跨任务复用会让 T+1 与冻结现金串。"""
    _SESSIONS.clear()


def register_session(run_id: str, task_id: str, engine: SimEngine,
                     *, set_id: str | None = None) -> SimEngine:
    """直接装配（测试与本地装配用）。`set_id` 不给就用本进程登记的那个。"""
    _SESSIONS[(run_id, task_id, set_id or factory_set_id())] = engine
    return engine


#: 会话工厂。**回答「会话从哪来」这个结构问题**：
#: runner 在 f02、网关在 f01，runner **没有**办法把一个进程内对象递过来。
#: 所以会话在**首次被用到时**由网关这一侧按 `(config_id, task_id)` 造 ——
#: 构造参数（日历、收盘价、可交易性、声明）全部来自**数据面**，
#: 而且全部是 agent 在题面里已经看得到的东西（task.yaml 的 X 面），不含答案面。
#:
#: **不做成第六个端点**：`/sim/session` 会是一条被测方够得着的装配路径 ——
#: 它能自己造一个 permitted_operations 全开的会话，越权就测不出来了。
#: 白名单是逐条登记的五条，多一条在启动自检上当场红。
_FACTORY = None


def register_session_factory(fn, *, set_id: str | None = None) -> None:
    """登记工厂，并**一并登记本进程服务的出集**（N-578）。

    `set_id=None` 时退回 `sim_factory.DEFAULT_SET_ID` —— 只有单测会走到那条路，
    生产路径上 `sim_factory.register()` 总是显式传。
    """
    global _FACTORY, _FACTORY_SET_ID
    from ..sim_factory import DEFAULT_SET_ID
    _FACTORY = fn
    _FACTORY_SET_ID = set_id or DEFAULT_SET_ID


def current_sim_date(run_id: str, task_id: str) -> str | None:
    """给 `asof.guard_run_ceiling` 用：这次运行的 `as_of` 上界 = 当前 `sim_date`。

    **会话在这里也会被物化**（红队 2026-09-05）：原来只 `.get()`，
    于是「还没碰过 `/sim/*`」= 没有会话 = **没有上界**。
    S8 的 agent 只要先把数据取完再开始交易，前视就是**免费**的 ——
    而这正是 `guard_run_ceiling` 存在的理由。取数这一步本身必须能建会话。

    S1..S7 不受影响：工厂对非 S8 任务返回 `None`。
    """
    if not run_id:
        return None
    sid = factory_set_id()
    eng = _SESSIONS.get((run_id, task_id, sid))
    if eng is None and _FACTORY is not None:
        eng = _FACTORY(run_id, task_id, set_id=sid)
        if eng is not None:
            _SESSIONS[(run_id, task_id, sid)] = eng
    return eng.sim_date if eng is not None else None


_asof.register_run_ceiling(current_sim_date)


def _identity(request: Request) -> tuple[str, str]:
    """五个端点**全部要求**身份头（契约 §2）。缺任一即拒，且落 access_log。

    **返回 `(run_id, task_id)`** —— 会话键（N-88）。`config_id` 仍然必需（日志按它分列），
    但**不进键**：它在同一次运行里可以变，而会话不该跟着变。
    `run_id` 也必需且**不许缺**：缺了就退回按 config_id 建会话，
    那正好是这条裁定要堵的洞（fail-closed，不是"没有就算了"）。
    """
    from ..app import HEADER_CONFIG_ID, HEADER_RUN_ID, HEADER_TASK_ID
    cid = request.headers.get(HEADER_CONFIG_ID)
    tid = request.headers.get(HEADER_TASK_ID)
    rid = request.headers.get(HEADER_RUN_ID)
    missing = [n for n, v in ((HEADER_CONFIG_ID, cid), (HEADER_TASK_ID, tid),
                              (HEADER_RUN_ID, rid)) if not v]
    if missing:
        raise GatewayDenied(
            Reason.PARAM_MALFORMED,
            f"缺必需头 {missing} —— 五个 /sim 端点都要求身份头（契约 §2）；"
            f"没有身份就没有会话，也无法把这次请求切进任何一次运行",
            status=422, context={"missing": missing})
    return rid, tid


def _engine(request: Request) -> SimEngine:
    rid, tid = _identity(request)
    sid = factory_set_id()
    eng = _SESSIONS.get((rid, tid, sid))
    if eng is None and _FACTORY is not None:
        eng = _FACTORY(rid, tid, set_id=sid)
        if eng is not None:
            _SESSIONS[(rid, tid, sid)] = eng
    if eng is None:
        raise GatewayDenied(
            Reason.DATASET_NOT_EXPOSED,
            f"这次运行没有模拟盘会话（run_id={rid}, task_id={tid}）—— "
            f"会话按 (run_id, task_id) 由数据面工厂构造；"
            f"自报一个别的 config_id 不会凭空造出一个",
            status=404, context={"run_id": rid, "task_id": tid})
    return eng


async def _body(request: Request) -> dict[str, Any]:
    """POST 的 JSON body。

    **⚠ 已知洞的补丁（卡 4.4 §1.3）**：`SCALAR_PARAMS` 中间件只查 query string，
    **管不到 POST 的 JSON body**。body 里的重复键要自己顶回去 ——
    语义与中间件一致：**歧义由调用方消除，环境不替它择一**。
    `json.loads` 默认「后者胜」，那正是「静默择一」。
    """
    raw = await request.body()
    if not raw:
        return {}
    dup: list[str] = []

    def _pairs(items):
        seen = set()
        for k, v in items:
            if k in seen:
                dup.append(k)
            seen.add(k)
        return dict(items)

    try:
        obj = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise GatewayDenied(Reason.PARAM_MALFORMED, f"body 不是 JSON：{e}",
                            status=422) from None
    if dup:
        raise GatewayDenied(
            Reason.PARAM_MALFORMED,
            f"body 里有重复键 {sorted(set(dup))} —— 授权参数不接受重复值，"
            f"歧义必须由调用方消除，环境不替你择一（与 SCALAR_PARAMS 同一条语义）",
            status=422, context={"duplicate": sorted(set(dup))})
    if not isinstance(obj, dict):
        raise GatewayDenied(Reason.PARAM_MALFORMED, "body 必须是 JSON 对象", status=422)
    return obj


def _need_json_int(body: dict, key: str) -> int:
    """JSON 整数，**bool 不算**（红队 2026-09-05）。

    原来这里写的是 `int(body[key])`。后果是引擎里那条
    `not isinstance(qty, int) or isinstance(qty, bool)` **在 HTTP 路径上是死代码** ——
    实测：`qty=300.0` / `qty="300"` 都返回 200 accepted，`qty=300.7` 被**静默截断**成 300。
    机制在，保护不在（D-06）：判据写在引擎里，而没有任何请求能把原值送到它面前。
    """
    v = body[key]
    if isinstance(v, bool) or not isinstance(v, int):
        raise GatewayDenied(
            Reason.PARAM_MALFORMED,
            f"{key} 必须是 JSON 整数（收到 {type(v).__name__}: {v!r}）—— "
            f"环境不替调用方做类型转换：`\"300\"`、`300.0`、`true` 各自是不同的意思，"
            f"强转会把其中两种静默变成第三种",
            status=422, context={"field": key, "got": type(v).__name__}) from None
    return v


def _need_json_number(body: dict, key: str) -> float:
    """JSON 数字（int 或 float，**bool 不算**）。

    `reference_close` 尤其不能强转：它是**冻结额**的计算基准
    （`need = qty * reference_close * (1+fee)`）。实测 `reference_close=true` → 1.0，
    于是 10 元的股票按 1 元冻结 —— **凭空十倍杠杆**，而 `insufficient_cash` 全程不响。
    """
    v = body[key]
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise GatewayDenied(
            Reason.PARAM_MALFORMED,
            f"{key} 必须是 JSON 数字（收到 {type(v).__name__}: {v!r}）—— "
            f"它是冻结额与 Slip 记录的基准，强转等于让调用方自己定基准",
            status=422, context={"field": key, "got": type(v).__name__}) from None
    return float(v)


def _need_json_str(body: dict, key: str) -> str:
    """JSON 字符串。`str(...)` 强转会把 `{"a":1}` 变成 `"{'a': 1}"` ——
    实测那样的撤单请求返回 200 `not_found`：**一个格式错误被报成了业务结果**。"""
    v = body[key]
    if not isinstance(v, str):
        raise GatewayDenied(
            Reason.PARAM_MALFORMED,
            f"{key} 必须是 JSON 字符串（收到 {type(v).__name__}: {v!r}）—— "
            f"强转后查不到会返回 not_found，把「请求写错了」报成「这单不存在」",
            status=422, context={"field": key, "got": type(v).__name__}) from None
    return v


def _translate(e: SimError) -> GatewayDenied:
    """`SimError` → `GatewayDenied`。**这是 N-45 的修法。**

    引擎是纯的（不含 HTTP、不落文件），所以它抛自己的异常；
    但**拒绝必须以与网关 deny 同一格式、同一切片键落 access_log**，
    否则越权率没有数据源 —— 而 `access_log` 只在 `GatewayDenied` 的 handler 里写。
    """
    reason = {
        "operation_not_permitted": Reason.OPERATION_NOT_PERMITTED,
        "window_exhausted": Reason.WINDOW_EXHAUSTED,
    }.get(e.code, Reason.PARAM_MALFORMED)
    return GatewayDenied(reason, str(e), status=e.status, context={"sim_code": e.code})


def _visible(eng: SimEngine) -> tuple[str, ...] | None:
    return getattr(eng, "visible_state_fields", None)


# --------------------------------------------------------------- 端点


@router.get("/sim/state")
def sim_state(request: Request) -> dict[str, Any]:
    """只读投影（§2.4）。`pending_orders` 在这里**看得见、改不了** ——
    可写的投影会产生两条修改路径，两条路径的审计事件不可能一直对齐，
    `Audit` 重放就会出现「日志重放的终态 ≠ 端点报的终态」，而两边都自称权威。"""
    eng = _engine(request)
    try:
        return eng.state(_visible(eng))
    except SimError as e:
        raise _translate(e) from None


@router.get("/sim/log")
def sim_log(request: Request) -> dict[str, Any]:
    """**权威**（§4）。`/sim/state` 与它不一致时以它为准。

    与 `access_log` **分开落**：那份记「谁在什么 as_of 下请求了什么」
    （前视与越权的结算源），这份记「模拟盘内部发生了什么」（Fill / Slip / Audit 的结算源）。
    合并会让「网络侧证据」与「环境内部叙述」混成一份，而后者部分来自被测方的输入。
    """
    eng = _engine(request)
    try:
        return {"events": eng.audit_log(), "sim_date": eng.sim_date}
    except SimError as e:
        raise _translate(e) from None


@router.post("/sim/order")
async def sim_order(request: Request) -> dict[str, Any]:
    """按 `client_order_id` 幂等：重复提交返回同一个 `order_id`，**不产生第二条 order 事件**。"""
    eng = _engine(request)
    body = await _body(request)
    need = ("symbol", "side", "qty", "client_order_id", "reference_close")
    miss = [k for k in need if k not in body]
    if miss:
        raise GatewayDenied(
            Reason.PARAM_MALFORMED,
            f"委托体缺 {miss} —— `reference_close` 是**提交时价的记录**，"
            f"无论 Slip 基准取哪一个都要带（契约 §2，与基准口径是两回事）",
            status=422, context={"missing": miss})
    try:
        return eng.submit(symbol=_need_json_str(body, "symbol"),
                          side=_need_json_str(body, "side"),
                          qty=_need_json_int(body, "qty"),
                          client_order_id=_need_json_str(body, "client_order_id"),
                          reference_close=_need_json_number(body, "reference_close"))
    except SimError as e:
        raise _translate(e) from None
    except (TypeError, ValueError) as e:
        raise GatewayDenied(Reason.PARAM_MALFORMED, f"委托体字段类型不对：{e}",
                            status=422) from None


@router.post("/sim/cancel")
async def sim_cancel(request: Request) -> dict[str, Any]:
    """撤单的**唯一**路径（§2.4）。幂等。"""
    eng = _engine(request)
    body = await _body(request)
    if "order_id" not in body:
        raise GatewayDenied(Reason.PARAM_MALFORMED, "缺 order_id", status=422)
    oid = _need_json_str(body, "order_id")
    try:
        return eng.cancel(oid)
    except SimError as e:
        raise _translate(e) from None


@router.post("/sim/advance")
async def sim_advance(request: Request) -> dict[str, Any]:
    """恰好前进**一个交易日**，**不接受目标日期参数**，不可回退（§2.1）。

    **这不是靠文档禁止，是靠接口形状** —— 端点收不到日期参数，就没有可以违反的规则。
    带任何 body 键进来一律拒：接受一个被忽略的参数，等于让调用方以为它生效了。
    """
    eng = _engine(request)
    body = await _body(request)
    if body:
        raise GatewayDenied(
            Reason.PARAM_MALFORMED,
            f"/sim/advance 不接受任何参数（实得 {sorted(body)}）—— "
            f"接受目标日期就等于把「跳日」和「回看」交给被测方去自律："
            f"跳日绕过 T+1 与冻结现金，回退让同一天被撮合两次。"
            f"收不到参数，就没有可以违反的规则",
            status=422, context={"unexpected": sorted(body)})
    try:
        return eng.advance(_visible(eng))
    except SimError as e:
        raise _translate(e) from None
