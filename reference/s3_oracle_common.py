# -*- coding: utf-8 -*-
"""S3 五道题共用的 oracle 骨架（卡 3.2 的 TODO，2026-09-05 落地）。

五个 `solve.py` 只提供 `FACTOR_ID / EXPRESSION / LOOKBACK / FIELDS / compute()`，
取数、暖机、非有限值统计、落盘与信封全部在这里 —— **一处实现，五处共用**。

**端点形状全部按 2026-09-05 实测写**，不按文档假设。原来 `s3-cor-01` 里
三处都是错的，而它们从没被发现，因为**这段代码一次都没跑过**：

| 处 | 原来写的 | 实测 |
| --- | --- | --- |
| `/calendar` 的日期列 | `d["date"]` | **`cal_date`**（`YYYYMMDD`）|
| `/universe` 的参数名 | `name=` | **`universe=`**（`name=` 直接 422）|
| `/universe` 的回包 | `["data"]` 里取 `u["code"]` | **`{"size": N, "members": [str, …]}`** |

`fetched_at` 一律取网关回显的 `x-genebench-ts`：**不用本地时钟，也不去读日志自己填** ——
后者会让被核值与核它的基准同源，交叉核就成了恒真。
"""
from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

from reference.oracle_io import Context, envelope, write

#: 网关在每个响应上回显的、这次请求在 `access_log` 里的 ts。
TS_HEADER = "x-genebench-ts"


class S3OracleError(RuntimeError):
    pass


def get(ctx: Context, path: str, **params) -> tuple[dict, str | None]:
    """一次网关请求。返回 `(回包, 网关回显的 ts)`。

    `as_of` **由这里统一附加** —— 逐处手写会漏，而漏掉的那次是一条免费的前视通道。
    """
    q = urllib.parse.urlencode({"as_of": ctx.as_of, **params})
    req = urllib.request.Request(f"{ctx.gateway}{path}?{q}", headers=ctx.headers())
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r), r.headers.get(TS_HEADER)


def calendar(ctx: Context) -> pd.DatetimeIndex:
    """窗口内的**开市日**。字段是 `cal_date`（`YYYYMMDD`），不是 `date`。"""
    body, _ = get(ctx, "/calendar", start_date=ctx.window["start"], end_date=ctx.window["end"])
    days = [d["cal_date"] for d in body.get("data") or [] if d.get("is_open")]
    if not days:
        raise S3OracleError(f"/calendar 没给出开市日（rows={body.get('rows')}）—— "
                            f"取不到日历就不该往下算")
    # **索引必须命名 `date`**：不命名的话，`compute()` 里 `reindex(cal)` 之后
    # `stack()` 出来的索引名是 `(None, "code")`，`reset_index()` 给出 `level_0` ——
    # `emit` 里 `out["date"]` 当场 KeyError。实测 S3 四题全倒在这里。
    return pd.DatetimeIndex(pd.to_datetime(pd.Series(days), format="%Y%m%d"), name="date")


def members(ctx: Context) -> list[str]:
    """成分。参数名是 `universe=`，回包是 `{"size", "members"}`（字符串列表）。"""
    body, _ = get(ctx, "/universe", universe=ctx.universe, date=ctx.window["end"])
    codes = list(body.get("members") or [])
    if not codes:
        raise S3OracleError(f"/universe 没给出成分（size={body.get('size')}）—— "
                            f"取不到成分就不该产出 artifact，那会是一份看起来合法的空壳")
    return codes


def fetch_panel(ctx: Context, fields: list[str]) -> tuple[pd.DataFrame, pd.DatetimeIndex]:
    """按题目宇宙逐票取 `/bars`，**显式传 fields**（缺省 = 读全表，会被反推成超读）。"""
    cal = calendar(ctx)
    frames = []
    for code in members(ctx):
        body, _ = get(ctx, "/bars", code=code, start_date=ctx.window["start"],
                      end_date=ctx.window["end"], fields=",".join(fields))
        rows = body.get("data") or []
        if rows:
            frames.append(pd.DataFrame(rows).assign(code=code))
    if not frames:
        raise S3OracleError("/bars 一行都没取到 —— 面板为空时不许继续")
    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index(["date", "code"]).sort_index(), cal


def emit(ctx: Context, values: pd.Series, cal: pd.DatetimeIndex, *, factor_id: str,
         expression: str, lookback: int, coverage_floor: float,
         approximated: list | None = None) -> Path:
    """落 `work/values.parquet` + artifact。**落点在任务目录下**，不在 cwd。"""
    out = values.reset_index().sort_values(["date", "code"])
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    import genebench_config as cfg

    work = cfg.create_dir(ctx.task_dir / "work")     # 红线 5：不裸 mkdir
    vpath = work / "values.parquet"
    out.to_parquet(vpath, index=False)
    vpath.chmod(0o600)
    v = out["value"].to_numpy(dtype="float64")
    first_valid = cal[lookback - 1].strftime("%Y-%m-%d")
    after = (out["date"] >= first_valid).to_numpy()
    finite = np.isfinite(v)
    n_dates, n_syms = out["date"].nunique(), out["code"].nunique()
    coverage = float(finite.sum() / max(1, n_dates * n_syms))
    payload = {
        "factor_id": factor_id, "expression": expression,
        "values_ref": {"rows": int(len(out)), "n_dates": int(n_dates), "n_symbols": int(n_syms),
                       "coverage": coverage,
                       "sha256": hashlib.sha256(vpath.read_bytes()).hexdigest()},
        "nonfinite": {"inf_count": int(np.isinf(v).sum()),
                      "nan_count": int((np.isnan(v) & after).sum()),
                      "replaced_count": 0},
        "warmup": {"lookback": lookback, "first_valid_date": first_valid,
                   "nonnull_before_warmup": int((~np.isnan(v) & ~after).sum())},
        "approximated_operators": list(approximated or []),
        "degeneracy": {"is_constant": bool(np.unique(v[finite]).size <= 1),
                       "alert": bool(np.unique(v[finite]).size <= 1 or coverage < coverage_floor),
                       "coverage": coverage},
    }
    return write(ctx, envelope(ctx, payload))


#: N-17：792 条实测覆盖率分布的 P5。**待签字**；签后从 `calibration.json` 读。
COVERAGE_FLOOR = 0.0574


def run(*, factor_id: str, expression: str, lookback: int, fields: list[str],
        compute, ctx: Context, coverage_floor: float = COVERAGE_FLOOR,
        approximated: list | None = None) -> Path:
    """五道 S3 题的公共入口。`compute(df, cal) -> pd.Series`。"""
    df, cal = fetch_panel(ctx, fields)
    return emit(ctx, compute(df, cal), cal, factor_id=factor_id, expression=expression,
                lookback=lookback, coverage_floor=coverage_floor, approximated=approximated)
