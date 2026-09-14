# -*- coding: utf-8 -*-
"""oracle 侧的网关客户端（S7 需要，其余阶段也可用）。

**端点形状全部按 2026-09-05 实测写**，不按文档假设 —— 那一天 40 题真跑，
S1/S2/S3/S5 的取数代码在同一批形状上各错各的，因为**没有一个被执行过**：

| 端点 | 实测 |
| --- | --- |
| `/calendar` | 参数 `start_date`/`end_date`（写 `start`/`end` **直接 403**）；日期列 **`cal_date`**（`YYYYMMDD`）|
| `/universe` | 参数 `universe=`（`name=` **直接 422**）；回包 `{"size": N, "members": [代码…]}`，**只接单日** |
| `/bars` | `code` 是**重复参数**、可一次多票 + 日期区间；`{rows, fields, data:[{code,date,status,…}]}` |
| `/adj` | 同样收多票 + 区间；`data:[{ts_code, trade_date, adj_factor}]`，**日期是 `YYYYMMDD`**|
| `/tradability` | `code` 重复参数，但 `date` **单日**，不接区间 |

两处最容易静默出错的地方：

* `rows` 是**行数（整数）**，不是数据 —— 数据在 `data` 里；
* `/bars` 给 `YYYY-MM-DD`、`/adj` 给 `YYYYMMDD`。**同一个网关的两个端点日期格式不同**，
  不归一就 merge，得到的是一张全 NaN 的表，而 merge 本身不报错。

`fetched_at` 一律取网关回显的 `x-genebench-ts`：不用本地时钟，
也不去读 `access_log` 自己填 —— 后者会让被核值与核它的基准同源，交叉核成恒真。
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

import pandas as pd

#: 网关在每个响应上回显的、这次请求在 `access_log` 里的 ts。
TS_HEADER = "x-genebench-ts"

#: 端点间列名不统一，在**取数边界**归一一次。
#: 本进程的标记。一个进程 = 一次运行 = 一个模拟盘会话（会话键 `(run_id, task_id)`，N-88）。
_PROC_TAG = f"p{os.getpid()}-{int(time.time())}"


def _default_run_id(config_id: str, task_id: str) -> str:
    """没显式给 run_id 时的缺省值：**每个进程一个**（`<config>.<task>.p<pid>-<启动时刻>`）。

    2026-09-05 实测：缺省曾是 `f"{config_id}.{task_id}"` —— 常量。而 S8 的模拟盘会话键是
    `(run_id, task_id)`（N-88），于是**同一道题的第二次 oracle 跑批复用了第一次的会话**：
    `sim_date` 已经推到窗口末，`/sim/advance` 直接 409 `window_exhausted`。
    表现是 s8-cor-01 崩、s8-ops-01 的 `denied_requests: 0` 与日志里的 1 次拒对不上 ——
    两个症状，同一个根因：**会话没有随运行重新开始**。

    真跑批里 run_id 由 runner 注入（每次运行不同），所以这条只影响数据面直跑的 oracle；
    但「数据面直跑」正是 gold 的产出路径。

    **后缀在 import 时算一次**：逐请求算的话（`int(time.time())` 每秒一变）同一个进程里的
    `/sim/log` 与 `/sim/state` 会落到**两个会话**上，表现为「刚问到的 sim_date 下一句就越界」。
    """
    return f"{config_id}.{task_id}.{_PROC_TAG}"


COL_ALIASES = {"cal_date": "date", "trade_date": "date", "ts_code": "code"}

#: 网关 `gateway/routers/market.py::MAX_ROWS`。超过即 422，而 422 在下面会记成 `denied` ——
#: 表现成「网关拒绝了 oracle」，排查方向完全错。所以分批按它算，不写死批大小。
MAX_ROWS = 200_000

#: `/tradability` 一次带多少 code。300 个拼一条 URL 约 5.7 KB，贴着 h11 的 8190 上限。
TRADABILITY_CHUNK = 100


class GatewayError(RuntimeError):
    pass


def to_panel_code(code: str) -> str:
    """网关 `600000.SH` → 契约 §1 的 `SH600000`。"""
    num, _, mkt = str(code).partition(".")
    return f"{mkt.upper()}{num}"


def to_gateway_code(code: str) -> str:
    """契约 `SH600000` → 网关 `600000.SH`。"""
    c = str(code).upper()
    return f"{c[2:]}.{c[:2]}" if c[:2].isalpha() else c


_DATE_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")


def iso_date(d) -> str:
    """`20260105` → `2026-01-05`；已经是 ISO 的原样返回。

    **归一在网关客户端这一层做**（裁定 2026-09-05）：网关各端点的日期写法不统一 ——
    `/calendar` 给 `cal_date`（紧凑串 `20260105`），`/bars` / `/adj` 给 ISO。
    列名归一（`COL_ALIASES`）早就有了，**值没归一**，于是两路数据在 join 或输出上相遇时静默出错：

    * S5（N-102）：因子面板 code 是 `SH600000`、宇宙是 `600000.SH` → reindex 全 NaN → gold 6 900 行全 null；
    * S6（N-102）：`trading_days` 取 `r["date"]`（不存在）→ 五题 KeyError；
    * S2（N-124）：`grid`（紧凑日期）merge `have`（ISO）→ 一行都对不上 → **gold 面板 41 700 行价格全空**，
      而 `missing_rows.count` 恰好等于总行数，看着像个正经数 —— 是 M6 的真 agent 报 44 才顶出来的。

    三次同族。所以归一收进这里，模板不再各写一份 `_COL_ALIASES`。
    """
    x = str(d)
    return f"{x[:4]}-{x[4:6]}-{x[6:]}" if len(x) == 8 and x.isdigit() else x


def normalize_frame(df: "pd.DataFrame") -> "pd.DataFrame":
    """网关回包的统一归一：**列名 + 日期值 + 代码写法**。取数的每一处都该走它。"""
    df = df.rename(columns={k: v for k, v in COL_ALIASES.items() if k in df.columns})
    if "date" in df.columns:
        df["date"] = df["date"].map(iso_date)
    if "code" in df.columns:
        df["code"] = df["code"].astype(str).str.strip().map(to_gateway_code)
    return df


class JoinEmpty(GatewayError):
    """归一之后 join 仍然对不上 —— 这是**静默出空**那一族的守门。"""


def assert_join_nonempty(merged: "pd.DataFrame", *, on: "list[str] | str", left: "pd.DataFrame",
                         right: "pd.DataFrame", value_col: str, what: str = "join") -> "pd.DataFrame":
    """merge 完必须**真的对上了**：`value_col` 不能整列为空。

    `pandas.merge(how="left")` 对不上时不报错，只给你一列 NaN —— 而一列 NaN 会一路走到 gold 里
    （N-124 的形态）。判据放在**生产路径**上（D-33），并把两侧的键样例打出来，
    让「为什么对不上」在报错那一刻就看得见，而不是等谁去 diff 两份 parquet。
    """
    keys = [on] if isinstance(on, str) else list(on)
    if len(merged) and merged[value_col].notna().sum() == 0:
        ls = {k: sorted(map(str, left[k].dropna().unique()))[:2] for k in keys if k in left.columns}
        rs = {k: sorted(map(str, right[k].dropna().unique()))[:2] for k in keys if k in right.columns}
        raise JoinEmpty(f"{what}：{len(merged)} 行里 `{value_col}` **全为空** —— 两侧键对不上。"
                        f"左样例 {ls}；右样例 {rs}（写法不同？先过 normalize_frame）")
    return merged


@dataclass
class Client:
    """一个 oracle 的网关会话。**每次请求都带身份头与 `as_of`。**

    身份头不是可选项：网关日志按 `(task_id, config_id)` 切片，
    缺了这一半，日志里切出来是 0 条 —— 表现成「一次都没请求过」，
    而其实请求了几百次（2026-09-05 实测，S2 就是这样）。
    """

    base_url: str
    task_id: str
    as_of: str
    config_id: str = "oracle"
    #: 会话键的一半（N-88）。数据面的 oracle 不经边车，自己填 ——
    #: 它不在威胁模型里（对手是容器里的被测方），但**必须填**：
    #: `/sim/*` 对缺头是 fail-closed 的，缺了直接 422。
    run_id: str = ""      # 空 = 用 `_default_run_id()`（**每个进程一个**，见那里的说明）
    timeout: int = 300
    #: 每次请求的台账：`{endpoint, params, fetched_at, status, rows}`，
    #: 直接可以喂给 S1 的 `payload.fetches`。
    ledger: list[dict] = field(default_factory=list)

    @classmethod
    def for_context(cls, ctx, **kw) -> "Client":
        """从统一 I/O 契约的 `Context` 造客户端（D-31：网关地址来自环境，其余一律来自 task.yaml）。"""
        return cls(base_url=ctx.gateway, task_id=ctx.task_id, as_of=ctx.as_of,
                   config_id=getattr(ctx, "config_id", "oracle"), **kw)

    def _headers(self) -> dict:
        return {"x-genebench-task-id": self.task_id,
                "x-genebench-config-id": self.config_id,
                "x-gb-run-id": self.run_id or _default_run_id(self.config_id, self.task_id)}

    def get_json(self, path: str, **params) -> tuple[dict, str | None, int]:
        """一次请求。返回 `(回包, 网关回显的 ts, HTTP 状态)`。**拒绝也记台账。**"""
        q = urllib.parse.urlencode({"as_of": self.as_of, **params}, doseq=True)
        req = urllib.request.Request(f"{self.base_url}{path}?{q}", headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                body, ts, code = json.load(r), r.headers.get(TS_HEADER), r.status
        except urllib.error.HTTPError as e:
            ts = e.headers.get(TS_HEADER) if e.headers else None
            try:
                body = json.load(e)
            except Exception:                                        # noqa: BLE001
                body = {}
            code = e.code
        rows = body.get("rows") if isinstance(body.get("rows"), int) else None
        status = ("denied" if code == 403 else "rate_limited" if code == 429
                  else "ok" if (rows or 0) > 0 else "empty" if code == 200 else "denied")
        self.ledger.append({"endpoint": path, "params": dict(params), "fetched_at": ts,
                            "status": status, "rows": rows if code == 200 else None})
        return body, ts, code

    def post_json(self, path: str, body: dict) -> tuple[dict, int]:
        """POST（`/sim/order`、`/sim/cancel`、`/sim/advance` 都是 POST）。

        与 `get_json` 一样：**拒绝也记台账**。403 在 S8 里是有意义的观测
        （越权率按它结算），吞掉它等于把判据的分子抹成 0。
        """
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}{path}?" + urllib.parse.urlencode({"as_of": self.as_of}),
            data=data, method="POST",
            headers={**self._headers(), "content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                payload, ts, code = json.load(r), r.headers.get(TS_HEADER), r.status
        except urllib.error.HTTPError as e:
            ts = e.headers.get(TS_HEADER) if e.headers else None
            try:
                payload = json.load(e)
            except Exception:                                        # noqa: BLE001
                payload = {}
            code = e.code
        status = ("denied" if code == 403 else "rate_limited" if code == 429
                  else "ok" if code == 200 else "denied")
        self.ledger.append({"endpoint": path, "params": dict(body), "fetched_at": ts,
                            "status": status, "rows": None})
        return payload, code

    def frame(self, path: str, **params) -> pd.DataFrame:
        """回包 → 归一列名的 DataFrame。`/universe` 的 `members` 摊成 `code` 列。"""
        body, _, code = self.get_json(path, **params)
        if code != 200:
            raise GatewayError(f"{path} 返回 {code}：{str(body)[:200]}")
        if path.rstrip("/").endswith("/universe"):
            rows = [{"code": c} for c in (body.get("members") or [])]
        else:
            rows = body.get("data") or []
        return normalize_frame(pd.DataFrame(rows))     # 列名 + 日期值 + 代码写法，一处归一

    # ---------------------------------------------------------------- 常用取数
    def trading_days(self, start: str, end: str) -> list[str]:
        df = self.frame("/calendar", start_date=start, end_date=end)
        if df.empty or "is_open" not in df.columns:
            raise GatewayError(f"/calendar 没给出可用的日历（列 {list(df.columns)}）")
        # `frame()` 已经在**边界**把日期归一成 ISO（r1.0.14）—— 这里再按 `%Y%m%d` 解一次就会当场抛。
        # ISO 串的字典序 == 时间序，直接排。留一条判据：混进非 ISO 的写法要看得见，不要静默排错。
        d = sorted(df.loc[df["is_open"].astype(bool), "date"].astype(str))
        bad = [x for x in d if not _DATE_ISO.fullmatch(x)]
        if bad:
            raise GatewayError(f"/calendar 归一后仍有非 ISO 日期 {bad[:3]} —— 归一层漏了这条路径")
        return d

    def members(self, universe: str, date: str) -> list[str]:
        df = self.frame("/universe", universe=universe, date=date)
        if df.empty:
            raise GatewayError(f"/universe 在 {date} 没给出成分 —— 取不到成分就不该往下算")
        return sorted(df["code"].astype(str).str.strip())

    def bars(self, codes: list[str], start: str, end: str, fields: list[str]) -> pd.DataFrame:
        """分批取 `/bars`。**`fields` 显式传** —— 缺省会被 `actual_reads` 反推成读全表。"""
        return self._by_code("/bars", codes, start, end, fields=",".join(fields))

    def adj(self, codes: list[str], start: str, end: str) -> pd.DataFrame:
        return self._by_code("/adj", codes, start, end)

    def _by_code(self, path: str, codes: list[str], start: str, end: str, **extra) -> pd.DataFrame:
        span = self._session_span(start, end)
        per = max(1, MAX_ROWS // span)
        out = []
        for i in range(0, len(codes), per):
            df = self.frame(path, code=codes[i:i + per], start_date=start, end_date=end, **extra)
            if not df.empty:
                out.append(df)
        if not out:
            raise GatewayError(f"{path} 在 {start}..{end} 一行都没取到 —— 面板为空时不许继续")
        df = pd.concat(out, ignore_index=True)
        return df.assign(date=pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d"))

    @staticmethod
    def _session_span(start: str, end: str) -> int:
        """把日历天粗折成交易日，只用来定分批大小（宁可估多，估多只是多发几次请求）。"""
        return max(1, int((pd.Timestamp(end) - pd.Timestamp(start)).days * 250 / 365) + 1)

    def tradability(self, codes: list[str], days: list[str]) -> pd.DataFrame:
        """逐日 × 分批。`code` 是**重复参数**，`date` **单日** —— 两处都与直觉不同。"""
        out = []
        for day in days:
            for i in range(0, len(codes), TRADABILITY_CHUNK):
                df = self.frame("/tradability", date=day, code=codes[i:i + TRADABILITY_CHUNK])
                if not df.empty:
                    out.append(df)
        return pd.concat(out, ignore_index=True) if out else pd.DataFrame(
            columns=["code", "date", "status"])
