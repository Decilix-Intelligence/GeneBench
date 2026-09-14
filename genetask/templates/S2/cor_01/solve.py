# oracle 参考解（数据面私有；在 f01 直跑，经网关 snapshot 后端产 artifact）。gold_token: <<gold_token>>
# 科目 S2-COR-01：复权 + 字段对齐 + 缺行如实报告。判据 = 与 gold_panel 逐格相等（Align/Adj 全 L1）。
#
# 网关端点（全部带 as_of=<task.as_of>，参数名以 gateway/routers/market.py 为准）：
#   GET /calendar?start_date=W0&end_date=W1                → 交易日（is_open=1）
#   GET /universe?universe=<U>&date=<as_of>                 → universe_ref 时点的 PIT 成分名单
#   GET /bars?code=<c>&start_date=W0&end_date=W1&fields=close,high,low,volume,status,has_daily
#   GET /adj?code=<c>&start_date=W0&end_date=W1             → adj_factor
# 复权：post = 未复权价 × adj_factor；pre = 未复权价 × adj_factor / adj_factor[as_of]；none = 原价。
# 缺行：网格 = 交易日 × 当日成分；格子在 /bars 里无行、或 status ∈ {suspend, no_data} → 缺行。
#   keep_missing → 网格全保留，缺行格子价格列为空值（**不得**前值/零/邻日填充）；
#   drop → 缺行格子从面板移除；forward_fill → 前值填充（本题不用）。
#   TODO(卡 2.1 面板)：market_view_v1 对 keep_missing 的表示（空值行 vs 无行）以面板数据卡为准，二者择一后钉死。
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone

import pandas as pd
import requests

# 统一 I/O 契约（裁定 2026-09-05）：读标准位置的任务规格、经网关取数、写标准 artifact 路径。
# **不接受任何 stage 特定的 env/argv** —— 从任务目录读得出来的东西，一律不从环境拿。
from reference.oracle_io import context as _oracle_context
from reference.oracle_io import write as _oracle_write
CTX = _oracle_context(__file__)
GATEWAY, TASK, WINDOW = CTX.gateway, CTX.spec, CTX.window
AS_OF, OUT = CTX.as_of, str(CTX.out)

#: 目标命名（alignment_target=market_view_v1）。TODO：从卡 2.1 的面板 schema 读，不要手抄。
FIELD_MAP = {"code": "symbol", "date": "date", "close": "close", "high": "high", "low": "low", "volume": "volume"}
PRICE_COLS = ("close", "high", "low")
BARS_FIELDS = "close,high,low,volume,status,has_daily"


#: 网关各端点的列名**不统一**（2026-09-05 实测）：`/calendar` 给 `cal_date`、
#: `/adj` 给 `ts_code`/`trade_date`、`/bars` 给 `code`/`date`。
#: 在**取数边界**上归一一次，比在十几个调用点各改各的可靠 ——
#: 漏一个的表现是 `KeyError: 'date'`，而它只在真跑时才出现。
_COL_ALIASES = {"cal_date": "date", "trade_date": "date", "ts_code": "code"}


#: 归一走**网关客户端**这一层（裁定 2026-09-05）：列名 + 日期值 + 代码写法一处定义，
#: 所有 oracle 共用。模板里各写一份 `_COL_ALIASES` 是三次同族 bug 的来源（N-102 / N-124）。
from reference.gateway_client import assert_join_nonempty, normalize_frame   # noqa: E402


def _normalize(df):
    return normalize_frame(df)


def _rows_of(path: str, body: dict):
    """把回包摊成行。**`/universe` 与别的端点形状不同**（2026-09-05 实测）：
    它给 `{"size": N, "members": [代码字符串, …]}`，没有 `data`，也没有 `code` 列。
    在边界上摊平一次，调用点就只见到统一的 `code` 列。"""
    if path.rstrip("/").endswith("/universe"):
        return [{"code": c} for c in (body.get("members") or [])]
    return body.get("data") or []

def get(path: str, **params) -> pd.DataFrame:
    # 身份头**必带**：网关日志按 (task_id, config_id) 切片，缺了这一半就切不出来 ——
    # 表现是 `log=0`「oracle 一次网关都没请求过」，而其实请求了几百次。
    r = requests.get(GATEWAY + path, params={**params, "as_of": AS_OF},
                     headers=CTX.headers(), timeout=120)
    r.raise_for_status()
    # 实测（2026-09-05）：`rows` 是**行数（整数）**，数据在 `data` 里。
    # 写 `pd.DataFrame(r.json()["rows"])` 会抛 "DataFrame constructor not properly called!"，
    # 而那句 TODO「与 gateway/routers/market.py 的响应体键名对齐」一直没做 ——
    # 因为这段代码一次都没跑过。
    return _normalize(pd.DataFrame(_rows_of(path, r.json())))


def main() -> None:
    decl = TASK["declared"]
    adjust = decl["adjust"]                                   # 规定题：一定已声明
    universe = decl["universe_ref"].split("@")[0]
    cal = get("/calendar", start_date=WINDOW["start"], end_date=WINDOW["end"])
    days = sorted(cal.loc[cal["is_open"] == 1, "date"])
    members = sorted(get("/universe", universe=universe, date=AS_OF)["code"])

    frames = []
    for code in members:
        bars = get("/bars", code=code, start_date=WINDOW["start"], end_date=WINDOW["end"], fields=BARS_FIELDS)
        adj = get("/adj", code=code, start_date=WINDOW["start"], end_date=WINDOW["end"])
        df = bars.merge(adj[["date", "adj_factor"]], on="date", how="left")
        if adjust == "post":
            for c in PRICE_COLS:
                df[c] = df[c] * df["adj_factor"]
        elif adjust == "pre":
            base = adj.sort_values("date")["adj_factor"].iloc[-1]        # as_of 时点的因子
            for c in PRICE_COLS:
                df[c] = df[c] * df["adj_factor"] / base
        df = df[df["status"].isin(["trade", "limit_up", "limit_down"])]  # suspend/no_data 视为缺行
        frames.append(df.assign(code=code))
    have = pd.concat(frames, ignore_index=True)

    grid = pd.MultiIndex.from_product([members, days], names=["code", "date"]).to_frame(index=False)
    panel = grid.merge(have, on=["code", "date"], how="left")
    # 归一之后**还得真的对上** —— merge 对不上不报错，只给一列 NaN（N-124 就是这么进 gold 的）。
    assert_join_nonempty(panel, on=["code", "date"], left=grid, right=have,
                         value_col="close", what="S2 网格 × 行情")
    missing = int(panel["close"].isna().sum())
    if decl["missing_row_policy"] == "drop":
        panel = panel.dropna(subset=["close"])
    elif decl["missing_row_policy"] == "forward_fill":
        panel = panel.sort_values(["code", "date"]).groupby("code").ffill()
    # keep_missing：网格保留、缺行格子留空

    panel = panel.rename(columns=FIELD_MAP)[list(FIELD_MAP.values())].sort_values(["symbol", "date"])
    csv = panel.to_csv(index=False, float_format="%.6f").encode("utf-8")
    sha = hashlib.sha256(csv).hexdigest()
    # **答案面产物落 `gold/`**（S7 一直是这么放的）。r1.0.16 之前这里是裸 `open("panel.csv","wb")`：
    # 落在题目录根、吃 umask（0664，红线 5）、也不在结算侧会去找的地方 ——
    # 于是 S2 的 L3 判不了内容，只剩三项描述性指标（N-124 的尾巴）。
    from reference.oracle_io import write_private as _wp
    _wp(CTX.task_dir / "gold" / "panel.csv", csv)

    artifact = {
        "schema_version": "1.0", "artifact_id": f"{TASK['task_id']}-oracle", "stage": "S2",
        "task_id": TASK["task_id"], "config_id": "oracle", "arm": "strict", "seed": 0, "as_of": AS_OF,
        "produced_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "provenance": [],
        "declarations": dict(decl),
        "payload": {
            "panel_ref": {"rows": int(len(panel)), "n_symbols": len(members), "n_dates": len(days), "sha256": sha},
            "field_map": FIELD_MAP,
            "missing_rows": {"count": missing, "policy_applied": decl["missing_row_policy"]},
            # 档位 `s2_adjust_report` 要求它（2026-09-05 实测：缺了直接 malformed）。
            # 记的是**实际施加**的复权口径 —— 与 `declarations.adjust` 同源但语义不同：
            # 前者是「我做了什么」，后者是「我声明要做什么」。两者不一致正是 S2 要抓的东西。
            "adjust_applied": decl["adjust"],
        },
    }
    _oracle_write(CTX, artifact)          # 标准路径 + 0600（红线 5：裸 write 吃 umask 落 0664，网关守门当场拒起）
    # TODO(O1)：写出后用 reference.artifact_schema.validate(artifact, task=TASK, tradability=切片) 断零 finding，
    #           再把 declarations.adjust 突变成另一枚举值，断 declaration_mismatch 变红。


if __name__ == "__main__":
    sys.exit(main())
