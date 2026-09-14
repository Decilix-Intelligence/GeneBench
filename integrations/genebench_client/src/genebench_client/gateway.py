# -*- coding: utf-8 -*-
"""经 GeneBench as-of 数据网关取数的客户端。

**零 `reference/` 依赖**：本包跑在**执行面容器**里，而 `reference/` 是答案面 ——
它既不在容器里，也不许进容器（红线 2）。端点形状、归一写法、`x-genebench-ts`
回显这些**契约**是从 `reference/gateway_client.py` 与 `gateway/routers/*.py`
读来学的，实现是独立写的一份；两边都不 import 对方。

契约里三处最容易静默出错的地方（都实测过）：

1. 参数名是 ``start_date`` / ``end_date``。写成 ``start`` / ``end`` 时网关
   **不报"未知参数"**，而是判**开区间**（``open_range_would_cross_asof``）→ 403。
   症状看起来像语义错误，排查的人会去查 as_of 而不是查拼写（N-50）。
2. 回包里 ``rows`` 是**行数（整数）**，数据在 ``data`` 里。
3. ``/bars`` 给 ISO 日期、``/adj`` / ``/calendar`` 给紧凑串。**同一个网关的两个端点
   日期格式不同**，不归一就 merge，得到一张全 NaN 的表，而 merge 本身不报错。

身份头四个（`x-genebench-task-id` / `x-genebench-config-id` / `x-gb-run-id` /
`x-gb-arm`）从环境变量取。容器里这四个由 compose 注入、由**边车**在网关入口
剥掉重注 —— 所以垫片填什么都改不了日志里的切片键；填它是为了在**没有边车**的
场合（f01 上直跑、单元测试）日志照样能切片。切片键是 `run_id`。
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

import pandas as pd

from .codes import compact_date, iso_date, to_lake
from .errors import (AsOfRequired, BudgetExceeded, GatewayError,
                     GatewayUnreachable, LookaheadDenied, MalformedRequest,
                     RateLimited)

#: 网关在每个响应上回显的、这次请求在 `access_log` 里的那条 ts（卡 2.6 / B8）。
TS_HEADER = "x-genebench-ts"

#: 网关地址的环境变量，**按优先级**。容器里 compose 注入的是 `GENEBENCH_GATEWAY`
#: （`runner/c41/runner_core.py` 的 compose 模板）；`GENEBENCH_GATEWAY_URL` 是
#: 数据面 oracle 那一侧的名字（`reference/oracle_io.py`）。两个都收，谁都不用改。
GATEWAY_ENVS: tuple[str, ...] = ("GENEBENCH_GATEWAY", "GENEBENCH_GATEWAY_URL")

#: as_of 的环境变量缺省。⚠️ **runner 目前不注入它**（实测：compose 模板里没有这一行），
#: 所以容器里通常取不到 —— 正常用法是启动时 `genebench_client.set_as_of(spec["as_of"])`
#: 或每次调用显式传。取不到就抛 `AsOfRequired`，**不猜**。
AS_OF_ENV: str = "GENEBENCH_AS_OF"

#: 身份头 → 环境变量。
IDENTITY_ENVS: dict[str, str] = {
    "x-genebench-task-id": "GENEBENCH_TASK_ID",
    "x-genebench-config-id": "GENEBENCH_CONFIG_ID",
    "x-gb-run-id": "GENEBENCH_RUN_ID",
    "x-gb-arm": "GENEBENCH_ARM",
}

#: `gateway/routers/market.py::MAX_ROWS`。超过即 **422**（不是截断）——
#: 分批要按它算，不写死批大小。
MAX_ROWS: int = 200_000

#: 一条 URL 的字节预算。h11 的请求行上限是 8190；留出余量给 base_url 与其它参数。
#: 超了的表现是 431/连接被拒，**不是**「少取了几只票」。
_URL_BUDGET: int = 6800
#: 一个 `code=600000.SH&` 大约 19 字节。
_BYTES_PER_CODE: int = 19

#: 六个数据端点（`/fundamentals` **不在其列**，见 `nodata.py` 的说明）。
DATA_ENDPOINTS: tuple[str, ...] = (
    "/bars", "/adj", "/calendar", "/limits", "/universe", "/tradability")
#: 五个模拟盘端点。
SIM_ENDPOINTS: tuple[str, ...] = (
    "/sim/state", "/sim/order", "/sim/cancel", "/sim/advance", "/sim/log")

#: 端点间列名不统一，在**取数边界**归一一次。
_COL_ALIASES: dict[str, str] = {"ts_code": "code", "trade_date": "date",
                                "cal_date": "date"}

#: `/bars` 的服务集（`gateway/routers/market.py::BARS_SERVED_COLUMNS`）。
#: 传 `fields` 时未知列名网关会 **422**，不静默忽略 —— 所以这里的清单要跟着它。
BARS_FIELDS: tuple[str, ...] = (
    "suspend_basis", "has_daily",
    "open", "high", "low", "close", "volume", "amount", "vwap",
    "limit_up_close", "limit_down_close", "limit_touched_up", "limit_touched_down",
    "no_price_limit", "in_listing_window")


def normalize_frame(df: pd.DataFrame) -> pd.DataFrame:
    """网关回包的统一归一：**列名 + 日期值 + 代码写法**。取数的每一处都走它。"""
    if df.empty:
        return df
    df = df.rename(columns={k: v for k, v in _COL_ALIASES.items() if k in df.columns})
    if "date" in df.columns:
        df["date"] = df["date"].map(iso_date)
    if "code" in df.columns:
        df["code"] = df["code"].astype(str).str.strip().map(to_lake)
    return df


def _default_base_url() -> str:
    for name in GATEWAY_ENVS:
        v = (os.environ.get(name) or "").strip()
        if v:
            return v.rstrip("/")
    raise GatewayUnreachable(
        f"网关地址没设 —— 取数只能经网关，没有网关就不该有第二条路。"
        f"请设 {' 或 '.join(GATEWAY_ENVS)}（容器里由 compose 注入）")


def _default_identity() -> dict[str, str]:
    return {h: (os.environ.get(e) or "") for h, e in IDENTITY_ENVS.items()}


@dataclass
class Client:
    """一次运行的网关会话。**每次请求都带身份头与 `as_of`。**

    身份头不是可选项：网关日志按 `run_id` 切片，缺了这一半，日志里切出来是 0 条 ——
    表现成「一次都没请求过」，而其实请求了几百次（2026-09-05 实测）。
    """

    base_url: str = ""
    as_of: str = ""
    task_id: str = ""
    config_id: str = ""
    run_id: str = ""
    arm: str = ""
    timeout: int = 300
    #: 每次请求一条：``{method, path, params, status, ts, rows}``。
    #: **拒绝也记** —— 403 是有意义的观测，吞掉它等于把判据的分子抹成 0。
    ledger: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.base_url:
            self.base_url = _default_base_url()
        self.base_url = self.base_url.rstrip("/")
        ident = _default_identity()
        self.task_id = self.task_id or ident["x-genebench-task-id"]
        self.config_id = self.config_id or ident["x-genebench-config-id"]
        self.run_id = self.run_id or ident["x-gb-run-id"]
        self.arm = self.arm or ident["x-gb-arm"]
        if not self.as_of:
            self.as_of = (os.environ.get(AS_OF_ENV) or "").strip()

    # ------------------------------------------------------------ 基础设施

    def _as_of(self, as_of: str | None = None) -> str:
        v = (as_of or self.as_of or "").strip()
        if not v:
            raise AsOfRequired(
                f"没有 as_of —— 它是这个基准的地基。**不猜一个默认值**："
                f"猜出来的那个会让越界变成合法请求，而产物上完全看不出来。"
                f"用 genebench_client.set_as_of('YYYY-MM-DD')、给本次调用传 as_of=，"
                f"或设环境变量 {AS_OF_ENV}")
        return iso_date(v)

    def _headers(self) -> dict[str, str]:
        h = {"x-genebench-task-id": self.task_id,
             "x-genebench-config-id": self.config_id,
             "x-gb-run-id": self.run_id}
        if self.arm:
            h["x-gb-arm"] = self.arm
        return {k: v for k, v in h.items() if v}

    def request(self, method: str, path: str, *, params: dict | None = None,
                body: dict | None = None,
                tolerate: Sequence[int] = ()) -> tuple[Any, str | None, int]:
        """一次请求。返回 ``(回包, 网关回显的 ts, HTTP 状态)``。**每一次都进 ledger。**

        `tolerate` 里的状态码不抛异常（留痕探针要的就是那个 404）。
        """
        url = f"{self.base_url}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params, doseq=True)
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = self._headers()
        if data is not None:
            headers["content-type"] = "application/json"
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                payload, ts, code = self._read(r), r.headers.get(TS_HEADER), r.status
        except urllib.error.HTTPError as exc:
            ts = exc.headers.get(TS_HEADER) if exc.headers else None
            payload, code = self._read(exc), exc.code
        except urllib.error.URLError as exc:
            self.ledger.append({"method": method, "path": path, "params": dict(params or {}),
                                "status": None, "ts": None, "rows": None,
                                "error": str(exc.reason)})
            raise GatewayUnreachable(f"{method} {path} 连不上网关（{self.base_url}）：{exc.reason}") from None
        rows = payload.get("rows") if isinstance(payload, dict) else None
        self.ledger.append({"method": method, "path": path, "params": dict(params or {}),
                            "status": code, "ts": ts,
                            "rows": rows if isinstance(rows, int) else None})
        if code < 400 or code in tolerate:
            return payload, ts, code
        raise self._translate(code, path, payload)

    @staticmethod
    def _read(handle) -> Any:
        try:
            return json.loads(handle.read().decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    @staticmethod
    def _translate(code: int, path: str, payload: Any) -> GatewayError:
        reason = payload.get("reason", "") if isinstance(payload, dict) else ""
        detail = payload.get("detail", "") if isinstance(payload, dict) else ""
        ctx = payload.get("context") if isinstance(payload, dict) else None
        msg = f"{path} → {code} {reason or ''} {detail or payload}".strip()
        if code == 403:
            return LookaheadDenied(msg, reason=reason, detail=detail,
                                   context=ctx if isinstance(ctx, dict) else None,
                                   status=code, path=path, body=payload)
        if code == 422:
            return MalformedRequest(msg, status=code, path=path, body=payload)
        if code == 402:
            return BudgetExceeded(msg, status=code, path=path, body=payload)
        if code == 429:
            return RateLimited(msg, status=code, path=path, body=payload)
        return GatewayError(msg, status=code, path=path, body=payload)

    def get_json(self, path: str, **params) -> dict:
        payload, _, _ = self.request("GET", path, params=params)
        return payload if isinstance(payload, dict) else {}

    def frame(self, path: str, **params) -> pd.DataFrame:
        """回包 → 归一列名/日期/代码的 DataFrame。`/universe` 的 `members` 摊成 `code` 列。"""
        body = self.get_json(path, **params)
        if path.rstrip("/").endswith("/universe"):
            rows: list[dict] = [{"code": c} for c in (body.get("members") or [])]
        else:
            rows = body.get("data") or []
        return normalize_frame(pd.DataFrame(rows))

    # ------------------------------------------------------------ 分批

    @staticmethod
    def _chunks(codes: Sequence[str], span_days: int) -> list[list[str]]:
        """按**两条**上限分批：URL 字节预算 与 `MAX_ROWS`。

        只按其中一条分的后果各不相同 —— 只看行数会撞 h11 的 8190（连接被拒，
        看起来像网关挂了）；只看 URL 会撞 422 `param_malformed`（看起来像参数写错了）。
        """
        by_url = max(1, _URL_BUDGET // _BYTES_PER_CODE)
        by_rows = max(1, MAX_ROWS // max(1, span_days))
        size = max(1, min(by_url, by_rows))
        return [list(codes[i:i + size]) for i in range(0, len(codes), size)]

    def _by_code(self, path: str, codes: Sequence[str], start: str, end: str,
                 *, as_of: str, **extra) -> pd.DataFrame:
        import datetime as _dt
        lo, hi = iso_date(start), iso_date(end)
        span = (_dt.date.fromisoformat(hi) - _dt.date.fromisoformat(lo)).days + 1
        if span < 1:
            raise MalformedRequest(
                f"{path}: start_date={lo} 晚于 end_date={hi} —— 空区间不是零行，是写反了")
        out: list[pd.DataFrame] = []
        for chunk in self._chunks([to_lake(c) for c in codes], span):
            out.append(self.frame(path, as_of=as_of, code=chunk,
                                  start_date=compact_date(lo), end_date=compact_date(hi),
                                  **extra))
        parts = [d for d in out if not d.empty]
        if not parts:
            return pd.DataFrame()
        return pd.concat(parts, ignore_index=True)

    # ------------------------------------------------------------ 六个数据端点

    def healthz(self) -> dict:
        return self.get_json("/healthz")

    def bars(self, codes: str | Iterable[str], start: str, end: str, *,
             fields: Sequence[str] | None = None, as_of: str | None = None) -> pd.DataFrame:
        """日线。**停牌日有行且 `status` 显式**，不是静默空。

        `fields` **显式传**：不传等于「读了全部列」，S3 的「声明读取集 vs 实际读取集」
        探针从 access_log 里反推出来的就是全表。
        """
        a = self._as_of(as_of)
        cs = _as_codes(codes)
        extra: dict[str, Any] = {}
        if fields:
            unknown = sorted(set(fields) - set(BARS_FIELDS))
            if unknown:
                raise MalformedRequest(
                    f"/bars 不认识字段 {unknown}；服务集 {list(BARS_FIELDS)}")
            extra["fields"] = ",".join(fields)
        return self._by_code("/bars", cs, start, end, as_of=a, **extra)

    def adj(self, codes: str | Iterable[str], start: str, end: str, *,
            as_of: str | None = None) -> pd.DataFrame:
        """复权因子。**网关只答 `adj_factor` 一种口径**（三价 bfq/hfq/qfq 不进 v1）。"""
        return self._by_code("/adj", _as_codes(codes), start, end,
                             as_of=self._as_of(as_of))

    def limits(self, codes: str | Iterable[str], start: str, end: str, *,
               as_of: str | None = None) -> pd.DataFrame:
        """涨跌停价。``no_price_limit=True`` 的行 `up_limit`/`down_limit` 是 **null** ——
        不是缺数，是本来就没有涨跌停价。**绝不要把哨兵值当真实涨停价用。**"""
        return self._by_code("/limits", _as_codes(codes), start, end,
                             as_of=self._as_of(as_of))

    def calendar(self, start: str, end: str, *, as_of: str | None = None) -> pd.DataFrame:
        """交易日历（SSE）。⚠️ 湖内只有 SSE，**深市沿用 SSE 日历是本项目的约定，不是数据事实**。"""
        a = self._as_of(as_of)
        return self.frame("/calendar", as_of=a, start_date=compact_date(start),
                          end_date=compact_date(end))

    def trading_days(self, start: str, end: str, *, as_of: str | None = None) -> list[str]:
        df = self.calendar(start, end, as_of=as_of)
        if df.empty or "is_open" not in df.columns:
            return []
        return sorted(df.loc[df["is_open"].astype(int) == 1, "date"].astype(str))

    def universe(self, name: str, date: str | None = None, *, scope: str = "canonical",
                 as_of: str | None = None) -> pd.DataFrame:
        """某个交易日的 PIT 成分。**只接单日**，不接区间。

        可选宇宙：``csi300`` ``csi500`` ``csi1000`` ``all``（`all` = 市场全集，
        不是指数，没有名义规模）。
        """
        a = self._as_of(as_of)
        return self.frame("/universe", as_of=a, universe=name,
                          date=iso_date(date) if date else a, scope=scope)

    def members(self, name: str, date: str | None = None, *, scope: str = "canonical",
                as_of: str | None = None) -> list[str]:
        df = self.universe(name, date, scope=scope, as_of=as_of)
        return [] if df.empty else sorted(df["code"].astype(str))

    def tradability(self, codes: str | Iterable[str], date: str | None = None, *,
                    as_of: str | None = None) -> pd.DataFrame:
        """某日某票的五档可交易性。``date`` **单日**，不接区间。

        ``status=None`` 表示产物里没有这一行。⚠️ 已知口径缺陷（N-10）：
        「这天不是交易日」与「这天没这只票」目前**无法区分**。
        """
        a = self._as_of(as_of)
        d = iso_date(date) if date else a
        cs = [to_lake(c) for c in _as_codes(codes)]
        out = [self.frame("/tradability", as_of=a, code=chunk, date=d)
               for chunk in self._chunks(cs, 1)]
        parts = [x for x in out if not x.empty]
        return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()

    # ------------------------------------------------------------ 五个 sim 端点

    def sim_state(self, *, as_of: str | None = None) -> dict:
        return self.get_json("/sim/state", as_of=self._as_of(as_of))

    def sim_log(self, *, as_of: str | None = None) -> dict:
        return self.get_json("/sim/log", as_of=self._as_of(as_of))

    def sim_order(self, *, symbol: str, side: str, qty: int, client_order_id: str,
                  reference_close: float, as_of: str | None = None) -> dict:
        """委托。`qty` 必须是 **JSON 整数**、`reference_close` 必须是 **JSON 数字** ——
        网关不替调用方做类型转换（`"300"` / `300.0` / `true` 各自是不同的意思）。"""
        if isinstance(qty, bool) or not isinstance(qty, int):
            raise MalformedRequest(f"qty 必须是整数，收到 {type(qty).__name__}: {qty!r}")
        if isinstance(reference_close, bool) or not isinstance(reference_close, (int, float)):
            raise MalformedRequest(
                f"reference_close 必须是数字，收到 {type(reference_close).__name__}")
        payload, _, _ = self.request(
            "POST", "/sim/order", params={"as_of": self._as_of(as_of)},
            body={"symbol": to_lake(symbol), "side": str(side), "qty": qty,
                  "client_order_id": str(client_order_id),
                  "reference_close": float(reference_close)})
        return payload

    def sim_cancel(self, order_id: str, *, as_of: str | None = None) -> dict:
        payload, _, _ = self.request("POST", "/sim/cancel",
                                     params={"as_of": self._as_of(as_of)},
                                     body={"order_id": str(order_id)})
        return payload

    def sim_advance(self, *, as_of: str | None = None) -> dict:
        """恰好前进**一个交易日**，不接受目标日期参数，不可回退。"""
        payload, _, _ = self.request("POST", "/sim/advance",
                                     params={"as_of": self._as_of(as_of)}, body={})
        return payload


def _as_codes(codes: str | Iterable[str]) -> list[str]:
    if isinstance(codes, str):
        parts = [x.strip() for x in codes.replace(",", " ").split() if x.strip()]
    else:
        parts = [str(x).strip() for x in codes if str(x).strip()]
    if not parts:
        raise MalformedRequest("必须指定至少一个 code")
    return parts
