# -*- coding: utf-8 -*-
"""as-of 数据网关的应用装配。

红线 4：**绑定 LAN 具体地址，禁止监听 0.0.0.0**。
tailscale 把自己的 ACCEPT 插在 ufw 之前，`0.0.0.0` 就等于对**整个 tailnet**
敞开，而 tailnet 里有第三方账号的节点。防线在两处：
`cfg.assert_no_wildcard_bind()`（run.py 调用）+ 本模块的 `ALLOWED_ROUTES` 白名单。

红线 5：网关**只答数据，不答答案**。`reference/` 与 `scorer/` 不在任何路由里，
且 `ALLOWED_ROUTES` 是**白名单**——新增端点必须显式登记，漏登记的失败形态是
"404"（响的）而不是"意外可达"（哑的）。
"""
from __future__ import annotations

import json
import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

import genebench_config as cfg

from . import access_log, asof, backends
from .errors import GatewayDenied, Reason
from .routers import market, reference, sim

#: **网关允许存在的全部路由。**任何不在这里的 path 都是 bug。
#: 启动时用 `assert_route_whitelist()` 校验，`ops/test_gateway.py` 也会核。
ALLOWED_ROUTES: frozenset[str] = frozenset(
    {
        "/healthz",
        "/bars",
        "/adj",
        "/calendar",
        "/limits",
        "/universe",
        "/tradability",
        "/fundamentals",
        # 卡 4.4：五个端点**逐条**登记。
        # 为什么不写 `/sim/{op}` 一条通配：一条通配会让「实现里多写了一个
        # 没在契约里的操作」变成**静默可达**；逐条列时，多出来的那个
        # 在启动自检 `assert_route_whitelist()` 上当场红。
        "/sim/state",
        "/sim/order",
        "/sim/cancel",
        "/sim/advance",
        "/sim/log",
    }
)

#: 绝不允许出现在任何路由里的字样（红线 5 的字面防线）。
FORBIDDEN_PATH_TOKENS: tuple[str, ...] = ("reference", "scorer", "gold", "answer", "probe")

HEADER_CONFIG_ID = "x-genebench-config-id"
HEADER_TASK_ID = "x-genebench-task-id"
#: ID-2/ID-3（卡 4.3 §6.5）：由**边车**在入口注入，任务容器改不到。
#: 网关照记不核 —— 核在边车那一侧（先剥后注）。切片键是 run_id。
HEADER_RUN_ID = "x-gb-run-id"
HEADER_ARM = "x-gb-arm"


def _identity(request) -> dict:
    """四个身份字段。**用 `.get()` 取第一个** —— 边车已经剥干净了同名重复头；
    若某天边车没剥，这里取到的会是伪造值，而 T15 正是盯着这条端到端断言。"""
    h = request.headers
    return {"config_id": h.get(HEADER_CONFIG_ID), "task_id": h.get(HEADER_TASK_ID),
            "run_id": h.get(HEADER_RUN_ID), "arm": h.get(HEADER_ARM)}

#: 只允许出现一次的参数。重复出现即 422 —— 见中间件里的说明。
#: `code` 不在其列：它本来就是可重复的多值参数。
SCALAR_PARAMS: tuple[str, ...] = (
    "as_of", "start_date", "end_date", "date", "universe", "scope",
    "statement", "mode", "fields",
)


#: 每个响应回显**这次请求在 `access_log` 里的那条 `ts`**（卡 2.6 / B8）。
#:
#: oracle 的 `payload.fetches[i].fetched_at` 必须等于日志里那条的 ts。
#: 让 oracle 自己去读日志填这个值，等于**被核的值与核它的基准同源** ——
#: 交叉核就成了恒真。回显之后这条比对才有信息量：
#: 值由网关在**响应时**给出，核对在**结算时**从日志另取一次。
TS_HEADER = "x-genebench-ts"


#: 缓冲回包以读取行数时的上限。超过就不缓冲，`rows` 记 `None`（= 推不出），
#: **而不是记 0** —— 校验器那侧把 `None` 当「不可检」，把 0 当「真的零行」。
_ROWS_BUFFER_LIMIT = 16 << 20


async def _buffer(response):
    """把中间件收到的流式响应读成一个普通响应，好从 body 里取 `rows`。

    `@app.middleware("http")` 给到的是 `_StreamingResponse`，`.body` 是空的 ——
    直接读 `.body` 会永远拿到 `None`，于是「记了行数」这件事**看起来做了、其实没做**
    （实测：三条端点的日志 rows 全是 None，而回包里明明有 5 / 5 / 300）。
    """
    from starlette.responses import Response as _Resp
    # **必须读完。** 第一版在超限时 `break` 掉、又把原响应放行 ——
    # 那个响应的 body_iterator 已经被消费了一半，客户端收到的是**空/截断的 body**
    # （实测：`/fundamentals` 200 但 `r.json()` 直接 JSONDecodeError）。
    # 读一半就放行是这里唯一不能做的事：要么全读并重建，要么一个字节都不碰。
    chunks = [c async for c in response.body_iterator]
    body = b"".join(chunks)
    out = _Resp(content=body, status_code=response.status_code,
                headers=dict(response.headers), media_type=response.media_type)
    # 超大回包只是**不解析行数**（rows 记 None = 推不出），响应本身照常完整返回。
    return out, (body if len(body) <= _ROWS_BUFFER_LIMIT else b"")


def _rows_of(body: bytes):
    if not body:
        return None
    try:
        obj = json.loads(body)
    except (ValueError, TypeError):
        return None
    n = obj.get("rows") if isinstance(obj, dict) else None
    return n if isinstance(n, int) and not isinstance(n, bool) else None


def _with_ts(response, entry):
    """把 access_log 那条的 ts 挂到响应头上。`entry` 是 `access_log.record()` 的返回值。"""
    try:
        response.headers[TS_HEADER] = entry["ts"]
    except (KeyError, TypeError, AttributeError):
        pass          # 回显失败不许影响这次请求本身；缺头会被 oracle 侧当成 fetched_at 缺失而报红
    return response


def create_app() -> FastAPI:
    app = FastAPI(
        title="GeneBench as-of 数据网关",
        version=cfg.SNAPSHOT_VERSION,
        docs_url=None,       # 不开 /docs：少一个可探测面
        redoc_url=None,
        openapi_url=None,
    )
    app.include_router(market.router)
    app.include_router(reference.router)
    app.include_router(sim.router)
    # S8 的会话工厂。**没有它，五个 /sim/* 端点一律 404** —— 而在此之前
    # 只有测试注册过工厂，所以真网关上 S8 四道题从来跑不通，且没有一条测试会红。
    from . import sim_factory
    sim_factory.register(app)

    @app.get("/healthz")
    def healthz() -> dict[str, Any]:
        """不需要 as_of，但**同样记日志** —— 探活也是一次访问。"""
        return {
            "ok": True,
            "freeze_line": cfg.FREEZE_DATE,
            "backend": backends.default_backend(),
            "bind": f"{cfg.GATEWAY_HOST}:{cfg.gateway_port()}",
            "exposed_datasets": sorted(backends.exposed_datasets()),
            # 卡 1.1-a：**探活要能一眼看出这是哪条通道**。两个实例外观一模一样时，
            # 「对着公开网关核私有数字」这种错会一直不被发现。
            "channel": cfg.channel(),
            "tables_dir": str(backends.tables_dir()),
        }

    @app.middleware("http")
    async def _log_and_time(request: Request, call_next):  # noqa: ANN202
        started = time.perf_counter()
        params = dict(request.query_params)
        ident = _identity(request)
        cid, tid = ident["config_id"], ident["task_id"]

        # ── 重复的标量参数一律拒，不择一 ─────────────────────────────
        # 探针实测过的真漏洞：`as_of=2026-06-30&as_of=2026-07-31` 时
        # FastAPI 取**最后一个**（宽的那个）并放行，而调用方完全可以
        # 声称自己给的是第一个。授权参数出现歧义却被静默择一，就是一次
        # 可否认的越权。这里在**路由之前**顶回去。
        for key in SCALAR_PARAMS:
            if len(request.query_params.getlist(key)) > 1:
                exc = GatewayDenied(
                    Reason.PARAM_MALFORMED,
                    f"{key} 出现了 {len(request.query_params.getlist(key))} 次。"
                    f"授权参数不接受重复值——歧义必须由调用方消除，网关不替你择一。",
                    status=422,
                    context={key: request.query_params.getlist(key)},
                )
                _e = access_log.record(
                    method=request.method, path=request.url.path, params=params,
                    as_of=params.get("as_of"), decision="deny", status=422,
                    reason=exc.reason.value, backend=backends.default_backend(),
                    extra=exc.context, **ident,
                )
                return _with_ts(JSONResponse(status_code=422, content=exc.payload()), _e)

        # ── 运行内 as_of 上界（卡 4.4 §2.2）─────────────────────────
        # 判定**必须先于取数**（asof.py 不变量 2）：先取后判会在日志里留下一次
        # 实际读取，卡 5.1 结算前视时分不清「读了但没给」与「根本没读」。
        # 放在中间件是因为它是**唯一**看得见每一个请求的地方 —— 逐端点调用漏一个
        # 就是一条免费的前视通道，而漏了没有任何东西会说。
        # 判定本身仍在 `asof.py` 里（那条「不许各写各的」的纪律）。
        if params.get("as_of"):
            try:
                # 走 `parse_asof` 而不是 `normalize_date`：前者会把归一化失败翻成
                # **as_of 专属的** reason（`asof_malformed`），后者抛的是通用的
                # `param_malformed`。`reason` 是卡 5.1 的结算键 —— 中间件抢在路由前
                # 判、却报了另一个码，探针那边就按错的族聚合了（实测 8 条测试当场红）。
                asof.guard_run_ceiling(asof.parse_asof(params["as_of"]),
                                       ident.get("run_id"), tid)
            except GatewayDenied as exc:
                _e2 = access_log.record(
                    method=request.method, path=request.url.path, params=params,
                    as_of=params.get("as_of"), decision="deny", status=exc.status,
                    reason=exc.reason.value, backend=backends.default_backend(),
                    extra=exc.context, **ident,
                )
                return _with_ts(JSONResponse(status_code=exc.status,
                                             content=exc.payload()), _e2)

        try:
            response = await call_next(request)
        except GatewayDenied:
            raise
        elapsed = (time.perf_counter() - started) * 1000.0
        rebuilt, raw = await _buffer(response)
        if rebuilt is not None:
            response = rebuilt
        # 被 exception handler 处理过的请求已经记过日志，避免重复
        if not getattr(request.state, "logged", False):
            entry = access_log.record(
                rows=_rows_of(raw),
                method=request.method,
                path=request.url.path,
                params=params,
                as_of=params.get("as_of"),
                decision="allow" if response.status_code < 400 else "deny",
                status=response.status_code,
                reason=None if response.status_code < 400 else "unclassified",
                backend=backends.default_backend(),
                elapsed_ms=round(elapsed, 2),
                **ident,
            )
            _with_ts(response, entry)
        return response

    @app.exception_handler(GatewayDenied)
    async def _denied(request: Request, exc: GatewayDenied):  # noqa: ANN202
        params = dict(request.query_params)
        access_log.record(
            method=request.method,
            path=request.url.path,
            params=params,
            as_of=params.get("as_of"),
            decision="deny",
            status=exc.status,
            reason=exc.reason.value,
            backend=backends.default_backend(),
            extra=exc.context or None,
            **_identity(request),
        )
        request.state.logged = True
        return JSONResponse(status_code=exc.status, content=exc.payload())

    assert_route_whitelist(app)
    return app


def registered_paths(app: FastAPI) -> set[str]:
    """递归收集**全部**路由路径。

    ⚠️ 这里有个真踩过的坑：FastAPI 0.141 把 `include_router()` 进来的路由
    包成 ``_IncludedRouter``，它自己的 ``path`` 是 ``None``，也**没有** ``.routes``
    —— 真正的 `APIRoute` 藏在 ``.original_router.routes`` 里
    （实测该对象的公开属性只有 ``original_router`` / ``effective_candidates`` /
    ``include_context`` / ``matches`` 等）。只看顶层 ``r.path`` 会**只看到 /healthz**，
    于是 `assert_route_whitelist()` 空跑通过 —— 一个看起来是绿的假护栏。
    第一版我以为下钻 ``.routes`` 就够了，仍然只收到 1 条；
    `assert_route_whitelist()` 里那条"收到的路由数不得少于白名单"的自检
    就是当场把这个错版本顶回来的东西，别删。
    """
    out: set[str] = set()
    seen: set[int] = set()

    def walk(obj) -> None:
        if obj is None or id(obj) in seen:
            return
        seen.add(id(obj))
        path = getattr(obj, "path", None)
        if isinstance(path, str) and path.startswith("/"):
            out.add(path)
        sub = getattr(obj, "routes", None)
        # `effective_candidates` 在这个版本里是**方法**不是列表，别顺手加进来
        if isinstance(sub, (list, tuple)):
            for item in sub:
                walk(item)
        walk(getattr(obj, "original_router", None))

    for r in app.routes:
        walk(r)
    return out - {"/openapi.json"}


def assert_route_whitelist(app: FastAPI) -> None:
    """启动即校验：没有计划外的路由，也没有触碰答案面的路径。"""
    paths = registered_paths(app)
    if len(paths) < len(ALLOWED_ROUTES):
        raise RuntimeError(
            f"只收集到 {len(paths)} 条路由（{sorted(paths)}），少于白名单的 "
            f"{len(ALLOWED_ROUTES)} 条。这多半是 registered_paths() 又没下钻到 "
            f"_IncludedRouter —— 白名单校验会因此空跑通过，是假护栏。"
        )
    extra = paths - ALLOWED_ROUTES
    if extra:
        raise RuntimeError(
            f"出现了不在白名单里的路由：{sorted(extra)}。"
            f"新增端点必须先登记进 gateway.app.ALLOWED_ROUTES（红线 5）。"
        )
    for p in paths:
        low = p.lower()
        for token in FORBIDDEN_PATH_TOKENS:
            if token in low:
                raise RuntimeError(
                    f"路由 {p} 含禁用字样 {token!r}：网关只答数据，不答答案（红线 5）。"
                )


app = create_app()
