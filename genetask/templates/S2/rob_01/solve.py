# oracle 参考解（数据面私有；在 f01 直跑，经网关 snapshot 后端产 artifact）。gold_token: <<gold_token>>
# 科目 S2-ROB-01：缺行 / 停牌 / 成分调整陷阱（材料 = 卡 1.2 可交易性视图的真实坑）。判据：
#   ① 面板与 gold_panel 逐格相等（Align L1）；② missing_rows.count == 可交易性视图里
#   status ∈ {suspend, no_data} 的格子数（calendar 探针：keep_missing 而报 0 即 missing_rows_silently_filled）。
# 本题埋的坑（全部来自卡 1.2 / 1.1 实测，oracle 必须一一踩对）：
#   K1 停牌且 daily 无行（如 000711.SZ@2026-08-28 形态）：/bars 无行 ≠ 「这天不存在」，要算缺行；
#   K2 suspend_d 同日既 S 又 R（161 个 (code,date)）：网关 status 已按「S 压 R、有行压两者」定死，直接信 status，
#      不要自己重判；
#   K3 指数成分在窗口内调整（csi500 与 csi300 同在 2026-06-30 生效一批调入/调出）：universe_ref 是 as_of 时点
#      的 PIT 名单，用它做网格；不得用「窗口内任一时刻在成分内」的并集；
#   K4 无涨跌幅哨兵（no_price_limit=True 的格子 up/down_limit 为 null）：与缺行无关，不要把它当缺行；
#   K5 in_listing_window=False 的行（北交所换码回填等）：网格来自 PIT 名单，这些码不会进网格，
#      若 /bars 给出这类行则忽略。
# 端点同 cor_01；本题 adjust=none，不调 /adj。
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

FIELD_MAP = {"code": "symbol", "date": "date", "close": "close", "high": "high", "low": "low", "volume": "volume"}
MISSING_STATUS = ("suspend", "no_data")


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
    assert decl["adjust"] == "none" and decl["missing_row_policy"] == "keep_missing"
    universe = decl["universe_ref"].split("@")[0]
    cal = get("/calendar", start_date=WINDOW["start"], end_date=WINDOW["end"])
    days = sorted(cal.loc[cal["is_open"] == 1, "date"])
    members = sorted(get("/universe", universe=universe, date=AS_OF)["code"])          # K3

    frames, missing = [], 0
    for code in members:
        bars = get("/bars", code=code, start_date=WINDOW["start"], end_date=WINDOW["end"],
                   fields="close,high,low,volume,status,has_daily,in_listing_window")
        bars = bars[bars["in_listing_window"]]                                          # K5
        by_date = bars.set_index("date")
        for d in days:
            if d not in by_date.index or by_date.at[d, "status"] in MISSING_STATUS:    # K1 / K2
                missing += 1
                frames.append({"code": code, "date": d})                                # keep_missing：留空值行
            else:
                row = by_date.loc[d]
                frames.append({"code": code, "date": d, **{c: row[c] for c in ("close", "high", "low", "volume")}})
    panel = pd.DataFrame(frames).rename(columns=FIELD_MAP)[list(FIELD_MAP.values())].sort_values(["symbol", "date"])
    # TODO(自检)：missing 必须等于 /tradability 在同网格上 status ∈ MISSING_STATUS 的计数 —— 这是 calendar 探针的基准，
    #             oracle 自己先对一遍，不等就是 K1–K5 里有一条踩错。

    csv = panel.to_csv(index=False, float_format="%.6f").encode("utf-8")
    sha = hashlib.sha256(csv).hexdigest()
    with open("panel.csv", "wb") as fh:
        fh.write(csv)
    artifact = {
        "schema_version": "1.0", "artifact_id": f"{TASK['task_id']}-oracle", "stage": "S2",
        "task_id": TASK["task_id"], "config_id": "oracle", "arm": "strict", "seed": 0, "as_of": AS_OF,
        "produced_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "provenance": [],
        "declarations": dict(decl),
        "payload": {
            "panel_ref": {"rows": int(len(panel)), "n_symbols": len(members), "n_dates": len(days), "sha256": sha},
            "field_map": FIELD_MAP,
            "missing_rows": {"count": missing, "policy_applied": "keep_missing"},
            # 档位 `s2_adjust_report` 要求申报**实际**用的复权口径（校验器据此判 `adjust_applied_mismatch`，
            # 探针族 adjust_fingerprint）。cor_01 一直有，这两个模板漏了 —— 于是它们的 oracle 产物
            # 一直被判 `payload_profile_key_missing`，而那条 finding 混在跑批的红里没人分开看。
            "adjust_applied": decl["adjust"],
        },
    }
    _oracle_write(CTX, artifact)          # 标准路径 + 0600（红线 5：裸 write 吃 umask 落 0664，网关守门当场拒起）


if __name__ == "__main__":
    sys.exit(main())
