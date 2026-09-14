# oracle 参考解（数据面私有；在 f01 直跑，经网关 snapshot 后端产 artifact）。gold_token: <<gold_token>>
# 科目 S2-OPS-01：流程与审计留痕。判据（全 L1，逐条硬判）：
#   P1 /task/panel.csv 存在，规范序列化（UTF-8、无索引、列序 = 目标命名顺序、(symbol,date) 升序、%.6f），
#      sha256(文件字节) == panel_ref.sha256，数据行数 == panel_ref.rows；
#   P2 field_map 的值集 == 目标命名列集（恰好相等、无重复），键列在内；
#   P3 /task/missing_rows.csv 行数 == missing_rows.count，且其 (symbol,date) 集合 == 可交易性视图上 status ∈
#      {suspend,no_data} 的网格格子（这一条同时是 calendar 探针的基准）；
#   P4 declarations 与 taskspec.declared JSON 相等；produced_at 可被 datetime.fromisoformat 解析且带 tzinfo。
# 面板正确性仍与 gold_panel 逐格比（Align L1）；但本题的科目分主要落在 P1–P4。
from __future__ import annotations

import csv
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
PANEL_PATH = str(CTX.task_dir / "solution" / "panel.csv")
MISSING_PATH = str(CTX.task_dir / "solution" / "missing_rows.csv")

#: 目标命名顺序（alignment_target 的列序）。TODO：从卡 2.1 面板 schema 读。
TARGET_COLUMNS = ["symbol", "date", "close", "high", "low", "volume"]
FIELD_MAP = {"code": "symbol", "date": "date", "close": "close", "high": "high", "low": "low", "volume": "volume"}
PRICE_COLS = ("close", "high", "low")


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


def canonical_csv(df: pd.DataFrame, cols: list[str]) -> bytes:
    """规范序列化：列序固定、(symbol,date) 升序、%.6f、无索引、UTF-8、LF。"""
    df = df[cols].sort_values(cols[:2]).reset_index(drop=True)
    return df.to_csv(index=False, float_format="%.6f", lineterminator="\n").encode("utf-8")


def main() -> None:
    decl = TASK["declared"]
    assert decl["adjust"] == "post" and decl["missing_row_policy"] == "keep_missing"
    universe = decl["universe_ref"].split("@")[0]
    days = sorted(get("/calendar", start_date=WINDOW["start"], end_date=WINDOW["end"]).query("is_open == 1")["date"])
    members = sorted(get("/universe", universe=universe, date=AS_OF)["code"])

    rows, missing = [], []
    for code in members:
        bars = get("/bars", code=code, start_date=WINDOW["start"], end_date=WINDOW["end"],
                   fields="close,high,low,volume,status")
        adj = get("/adj", code=code, start_date=WINDOW["start"], end_date=WINDOW["end"])
        df = bars.merge(adj[["date", "adj_factor"]], on="date", how="left").set_index("date")
        for d in days:
            if d not in df.index or df.at[d, "status"] in ("suspend", "no_data"):
                missing.append({"symbol": code, "date": d})
                rows.append({"symbol": code, "date": d})                      # keep_missing：空值行
            else:
                r = df.loc[d]
                rows.append({"symbol": code, "date": d, "volume": r["volume"],
                             **{c: r[c] * r["adj_factor"] for c in PRICE_COLS}})   # post
    panel = pd.DataFrame(rows)
    panel_bytes = canonical_csv(panel, TARGET_COLUMNS)                          # P1
    with open(PANEL_PATH, "wb") as fh:
        fh.write(panel_bytes)
    with open(MISSING_PATH, "w", encoding="utf-8", newline="") as fh:            # P3
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["symbol", "date"])
        for m in sorted(missing, key=lambda x: (x["symbol"], x["date"])):
            w.writerow([m["symbol"], m["date"]])

    assert set(FIELD_MAP.values()) == set(TARGET_COLUMNS) and len(set(FIELD_MAP.values())) == len(FIELD_MAP)  # P2
    artifact = {
        "schema_version": "1.0", "artifact_id": f"{TASK['task_id']}-oracle", "stage": "S2",
        "task_id": TASK["task_id"], "config_id": "oracle", "arm": "strict", "seed": 0, "as_of": AS_OF,
        "produced_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),          # P4
        "provenance": [],
        "declarations": dict(decl),                                                        # P4
        "payload": {
            "panel_ref": {"rows": int(len(panel)), "n_symbols": len(members), "n_dates": len(days),
                          "sha256": hashlib.sha256(panel_bytes).hexdigest(), "path": "/task/panel.csv"},
            "field_map": FIELD_MAP,
            "missing_rows": {"count": len(missing), "policy_applied": "keep_missing", "path": "/task/missing_rows.csv"},
            # 档位 `s2_adjust_report` 要求申报**实际**用的复权口径（校验器据此判 `adjust_applied_mismatch`，
            # 探针族 adjust_fingerprint）。cor_01 一直有，这两个模板漏了 —— 于是它们的 oracle 产物
            # 一直被判 `payload_profile_key_missing`，而那条 finding 混在跑批的红里没人分开看。
            "adjust_applied": decl["adjust"],
        },
    }
    _oracle_write(CTX, artifact)          # 标准路径 + 0600（红线 5：裸 write 吃 umask 落 0664，网关守门当场拒起）


if __name__ == "__main__":
    sys.exit(main())
