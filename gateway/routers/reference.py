# -*- coding: utf-8 -*-
"""参考侧端点：``/universe`` ``/tradability`` ``/fundamentals``。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

import genebench_config as cfg
from snapshots import tradability as tr
from snapshots import universe_build as ub

from .. import backends
from ..asof import guard_codes, guard_target, parse_asof
from ..errors import GatewayDenied, Reason

router = APIRouter()

#: 三大报表（含 vip 孪生表）。**只有这些**进 v1 基本面。
STATEMENTS: tuple[str, ...] = (
    "income", "income_vip",
    "balancesheet", "balancesheet_vip",
    "cashflow", "cashflow_vip",
)

#: 报表的 PIT 可见性字段。用 **f_ann_date**（实际公告日）而不是 ann_date。
#: 实测同一季有 14 行 / 7 只票两者不等，且**全部 ann_date 更早**（最长提前 19 天）
#: —— 用 ann_date 就是提前 19 天看见财报。
VISIBILITY_COL: str = "f_ann_date"

#: ⚠️ **N-15：f_ann_date 存在大量 NULL。**
#: income_vip 全表 5,708 行 NULL（2026Q1 占 5,686 行 / 5,678 只票 = 该季 27.7%），
#: 成因是分区间 schema 漂移 + 视图 union_by_name=true（部分分区根本没这一列）。
#:
#: 于是过滤条件怎么写，差一个**全市场级前视泄漏**：
#:   * ``f_ann_date <= as_of``            → NULL 被 SQL 判为 UNKNOWN，**丢弃** ✅
#:   * ``NOT (f_ann_date > as_of)``       → 同样 UNKNOWN，**也丢弃**，但语义不明显
#:   * ``coalesce(f_ann_date, ann_date)`` → 🔴 **前视泄漏**，绝对禁止
#:
#: 本模块显式写 ``f_ann_date IS NOT NULL AND f_ann_date <= as_of`` ——
#: 不依赖三值逻辑的直觉，把意图写在脸上。
#: 已实测的缓解事实：那 5,678 只票**每一只都同时**有非 NULL 行
#: （"只有 NULL 行"的票 = 0），所以严格丢弃不会丢掉任何公司。
PIT_WHERE: str = f"{VISIBILITY_COL} IS NOT NULL AND {VISIBILITY_COL} <= ?"


@router.get("/universe")
def universe(
    as_of: str | None = Query(None),
    universe: str = Query(...),
    date: str | None = Query(None),
    scope: str = Query("canonical"),
    ctx: dict[str, Any] = None,  # noqa: ARG001
) -> dict[str, Any]:
    """某个交易日的 PIT 成分。

    走卡 1.1 的 `universe_at()` —— 它对越界**抛错**而不是静默给冻结线那天的名单。
    网关把 ValueError 翻成 403，不能让它变成 500（500 会让调用方以为是网关坏了，
    而不是"你越界了"）。
    """
    a = parse_asof(as_of)
    d = guard_target(date or a, a, field="date", reason=Reason.UNIVERSE_AFTER_ASOF)
    if universe not in cfg.UNIVERSES_PIT:
        raise GatewayDenied(
            Reason.UNKNOWN_UNIVERSE,
            f"universe={universe!r} 不认识；可选 {list(cfg.UNIVERSES_PIT)}",
            status=422,
            context={"universe": universe},
        )
    try:
        members = ub.universe_at(universe, d, scope=scope)
    except ValueError as exc:
        raise GatewayDenied(
            Reason.BEYOND_FREEZE_LINE, str(exc),
            context={"universe": universe, "date": d, "scope": scope},
        ) from exc
    return {
        "as_of": a, "universe": universe, "date": d, "scope": scope,
        "size": len(members),
        # `rows` 与 `size` 同值：中间件与 oracle 都只认 `rows`（卡 2.6 / B8）。
        # 各端点各起一个名字的话，「日志里的行数」就要在两处各写一份优先级，
        # 而那两份必然漂 —— 漂了的表现是 source_status 交叉核**永远不一致**。
        "rows": len(members),
        "note": (
            "csi300 在 20091231→20100128 共 20 个交易日规模是 298（指数合并退市空缺）——"
            "**不要**把规模恒等于名义值当不变量。"
        ),
        "members": members,
    }


from functools import lru_cache


@lru_cache(maxsize=6)
def _tradability_year(year: int, channel: str = ""):
    """按年缓存整表。`channel` 只作**缓存键**（卡 1.1-a）——
    一个进程只跑一条通道，但把通道写进键，可以让「同一个进程里换了通道
    却拿到上一条通道的行」这种事不可能发生。"""
    return tr.read_tradability(year, root=cfg.tradability_dir(channel or None))


@lru_cache(maxsize=256)
def _tradability_day(year: int, compact: str, channel: str = "") -> dict[str, dict[str, Any]]:
    """某一天全部 code 的行：`code → row_dict`。行内容 = `tradability_at` 会返回的同一行。"""
    frame = _tradability_year(year, cfg.channel())
    hit = frame[frame["date_compact"] == compact]
    return {str(r["code"]): r for r in hit.to_dict(orient="records")}


@router.get("/tradability")
def tradability(
    as_of: str | None = Query(None),
    code: list[str] | None = Query(None),
    date: str | None = Query(None),
    ctx: dict[str, Any] = None,  # noqa: ARG001
) -> dict[str, Any]:
    """某日某票的可交易性（卡 1.2 的五档 status）。"""
    a = parse_asof(as_of)
    d = guard_target(date or a, a, field="date")
    codes = guard_codes(code)
    if not codes:
        raise GatewayDenied(
            Reason.PARAM_MALFORMED, "/tradability 必须指定至少一个 code", status=422
        )
    # **按年缓存整表，再按日过滤、按 code 取行**（2026-09-05）。原来逐 code 调
    # `tr.tradability_at()`，而它**每次都把整年 parquet 读一遍**（几百万行）——
    # 100 个 code 一次请求 ≈ 11 s，S5 一道题 69 次就撞 600 s 超时；
    # 放宽窗口的 S6 信号要 180 次，根本跑不完。行的形状与 `tradability_at` 一字不差
    # （`to_dict()` 同一行），N-10 的「没这一行 → status=None」语义也照旧。
    compact = d.replace("-", "")
    if compact > cfg.FREEZE_DATE.replace("-", ""):
        raise GatewayDenied(Reason.BEYOND_FREEZE_LINE,
                            f"{d} 超过冻结线 {cfg.FREEZE_DATE}", context={"date": d})
    day = _tradability_day(int(compact[:4]), compact, cfg.channel())
    rows: list[dict[str, Any]] = []
    for c in codes:
        row = day.get(c)
        rows.append(dict(row) if row is not None else {"code": c, "date": d, "status": None})
    return {
        "as_of": a, "date": d, "rows": len(rows),
        "note": (
            "status=null 表示产物里没有这一行。⚠️ 已知口径缺陷（tickets N-10）："
            "'这天不是交易日' 与 '这天没这只票' 目前无法区分。"
        ),
        "data": rows,
    }


@router.get("/fundamentals")
def fundamentals(
    as_of: str | None = Query(None),
    statement: str = Query("income"),
    code: list[str] | None = Query(None),
    end_date: str | None = Query(None),
    ctx: dict[str, Any] = None,  # noqa: ARG001
) -> dict[str, Any]:
    """三大报表，**严格 PIT**。

    可见性 = ``f_ann_date IS NOT NULL AND f_ann_date <= as_of``（见 N-15）。

    **update_flag 取版规则**：同一 ``(ts_code, end_date)`` 在 as_of 时点
    可能已有多版。取**当时能看见的最新那一版** —— 按 ``f_ann_date`` 降序，
    同日再按 ``update_flag`` 降序取第一条。**不是**取最终版：
    "2026-04-25 那天看到的是哪一版"和"这一期最后定稿是哪一版"是两个问题，
    benchmark 要的是前者。
    """
    a = parse_asof(as_of)
    # 公开通道**不服务财务**（卡 2.5 §1 确认项 + N-58①）。拒绝发生在
    # **参数校验之前**：先校验参数的话，一个拼错的 statement 会得到 422，
    # 而调用方会以为「拼对了就能查」。这里一律 403，理由说清是源侧不成立。
    if cfg.channel() == "public":
        raise GatewayDenied(
            Reason.DATASET_NOT_EXPOSED,
            "公开通道不服务 /fundamentals：baostock 的季频财务**无 f_ann_date**，"
            "而 v1 的 PIT 判据是 `f_ann_date IS NOT NULL AND <= as_of` 且禁止 "
            "`coalesce(f_ann_date, ann_date)`（全市场级前视泄漏）——"
            "「用公开源补一份财务表」这条路不成立，不是「暂时没建」。",
            context={"channel": "public", "statement": str(statement),
                     "endpoint": "/fundamentals"},
        )
    name = str(statement).strip().lower()
    if name not in STATEMENTS:
        # 走白名单机制给出有信息量的拒绝（fina_indicator 会命中 BLOCKED_DATASETS）
        backends.assert_exposed(name)
        raise GatewayDenied(
            Reason.DATASET_NOT_EXPOSED,
            f"statement={name!r} 不是三大报表之一；v1 只暴露 {list(STATEMENTS)}",
            context={"statement": name, "supported": list(STATEMENTS)},
        )
    codes = guard_codes(code)
    where = PIT_WHERE
    params: list[Any] = [a]
    if codes:
        where += " AND ts_code IN (" + ",".join(["?"] * len(codes)) + ")"
        params += codes
    if end_date:
        where += " AND end_date = ?"
        params.append(guard_target(end_date, "99991231", field="end_date"))
    cols = (
        "ts_code, ann_date, f_ann_date, end_date, end_type, update_flag, "
        "total_revenue, n_income"
        if name.startswith("income")
        else "ts_code, ann_date, f_ann_date, end_date, end_type, update_flag"
    )
    out = backends.read_table(name, where=where, params=params, columns=cols)
    picked = out
    if len(out):
        picked = (
            out.sort_values(
                ["ts_code", "end_date", "f_ann_date", "update_flag"],
                ascending=[True, True, False, False],
            )
            .groupby(["ts_code", "end_date"], as_index=False)
            .head(1)
            .sort_values(["ts_code", "end_date"])
        )
    return {
        "as_of": a,
        "statement": name,
        "visibility": PIT_WHERE.replace("?", repr(a)),
        "rows": len(picked),
        "rows_before_version_pick": len(out),
        "note": (
            "严格 PIT：f_ann_date 为 NULL 的行一律丢弃（N-15，income_vip 全表 5,708 行 NULL）。"
            "禁止 coalesce(f_ann_date, ann_date) —— 那是全市场级前视泄漏。"
            "同一 (ts_code,end_date) 取 as_of 当时可见的最新版，不是最终版。"
        ),
        "data": picked.to_dict(orient="records"),
    }
