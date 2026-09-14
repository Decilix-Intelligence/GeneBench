# oracle 参考解（数据面私有；在 f01 直跑，经网关 snapshot 后端产 artifact）。gold_token: <<gold_token>>
# 科目 S2-ECO-01：长窗口（2019-01-02 → 2026-07-31）对齐的效率参考（VES 式，BIRD 口径）。
# 判据：① 面板与 gold_panel 逐格相等（Align L1）；② 效率三项相对 oracle 的比值 —— 网关请求次数 / 返回总行数 /
#   墙钟，全部从网关 access_log 与 runner 计时结算，**不采信 artifact 自报**。阈值由卡 5.x 的 scorer 钉，本文件不写。
# oracle 就是「参考实现」，它的取数纪律定义了分母，所以必须是最省的合法路径：
#   E1 /bars 按 code **批量**取（`fields` 只取 close,high,low,volume,status），不按日轮询、不逐码单发。
#      2026-09-07（N-279）实测结论：网关**不接受** `universe=…` 的批量形态 ——
#      `gateway/routers/market.py` 明写「/bars 必须指定至少一个 code」（422），而 `universe=` 作为
#      未知查询参数被 FastAPI 静默丢掉，于是这道题的 oracle 从来没跑通过（两条通道同一条 422）。
#      两条修法里取的是**小改**这条：只动参考轴的这一个文件；让 `/bars` 接 `universe` 会改
#      `declared_reads` 探针的分母口径（N-58 补记②）且**仍然跨不过行数上限**，那是大改。
#   E2 /adj 同样按 code 批量取；/calendar 一次；/universe 一次。
#      **单次回包受网关 `MAX_ROWS`（200 000 行）封顶**：本题 300 只 × 约 1 840 个交易日 ≈ 55 万行，
#      一次拿不完，所以按「每批 MAX_ROWS // 交易日数 只」切。理论最少请求数因此是
#      `2 + 2 × ceil(成分数 / 每批只数)` —— 判据仍是「相对 oracle 的比值」，口径没变，
#      变的是这个分母第一次是**真跑得出来**的数。
#   E3 不发任何重复请求（access_log 里 (path, params) 去重后条数 == 原条数）。
# 本题 missing_row_policy=drop：缺行格子从面板移除，但 missing_rows.count 仍报网格上的缺行数。
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
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
PRICE_COLS = ("close", "high", "low")
N_REQUESTS = 0


#: 网关各端点的列名**不统一**（2026-09-05 实测）：`/calendar` 给 `cal_date`、
#: `/adj` 给 `ts_code`/`trade_date`、`/bars` 给 `code`/`date`。
#: 在**取数边界**上归一一次，比在十几个调用点各改各的可靠 ——
#: 漏一个的表现是 `KeyError: 'date'`，而它只在真跑时才出现。
_COL_ALIASES = {"cal_date": "date", "trade_date": "date", "ts_code": "code"}


#: 归一走**网关客户端**这一层（裁定 2026-09-05）：列名 + 日期值 + 代码写法一处定义，
#: 所有 oracle 共用。模板里各写一份 `_COL_ALIASES` 是三次同族 bug 的来源（N-102 / N-124）。
from reference.gateway_client import MAX_ROWS, assert_join_nonempty, normalize_frame   # noqa: E402


def _chunks(codes: list[str], n_days: int) -> list[list[str]]:
    """按网关行数上限反算每批只数（与 `gateway_client.Client._by_code` 同一条口径）。"""
    per = max(1, MAX_ROWS // max(1, n_days))
    return [codes[i:i + per] for i in range(0, len(codes), per)]


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
    global N_REQUESTS
    N_REQUESTS += 1
    # 身份头**必带**：网关日志按 (task_id, config_id) 切片，缺了这一半就切不出来 ——
    # 表现是 `log=0`「oracle 一次网关都没请求过」，而其实请求了几十次（2026-09-07 实测，
    # 与 S2 其余四题同族；那四题早就带了，只有本题漏着，因为它此前卡在 422 从没走到这一步）。
    r = requests.get(GATEWAY + path, params={**params, "as_of": AS_OF},
                     headers=CTX.headers(), timeout=600)
    r.raise_for_status()
    # 实测（2026-09-05）：`rows` 是**行数（整数）**，数据在 `data` 里。
    # 写 `pd.DataFrame(r.json()["rows"])` 会抛 "DataFrame constructor not properly called!"，
    # 而那句 TODO「与 gateway/routers/market.py 的响应体键名对齐」一直没做 ——
    # 因为这段代码一次都没跑过。
    return _normalize(pd.DataFrame(_rows_of(path, r.json())))


def main() -> None:
    t0 = time.monotonic()
    decl = TASK["declared"]
    assert decl["adjust"] == "post" and decl["missing_row_policy"] == "drop"
    universe = decl["universe_ref"].split("@")[0]
    days = sorted(get("/calendar", start_date=WINDOW["start"], end_date=WINDOW["end"]).query("is_open == 1")["date"])
    members = sorted(get("/universe", universe=universe, date=AS_OF)["code"])
    batches = _chunks(members, len(days))
    bars = pd.concat([get("/bars", code=b, start_date=WINDOW["start"], end_date=WINDOW["end"],
                          fields="close,high,low,volume,status") for b in batches],
                     ignore_index=True)                                                 # E1
    adj = pd.concat([get("/adj", code=b, start_date=WINDOW["start"], end_date=WINDOW["end"])
                     for b in batches], ignore_index=True)                              # E2
    assert N_REQUESTS == 2 + 2 * len(batches)                                           # E3 的最小值

    bars = bars[bars["code"].isin(members)]
    df = bars.merge(adj[["code", "date", "adj_factor"]], on=["code", "date"], how="left")
    for c in PRICE_COLS:
        df[c] = df[c] * df["adj_factor"]                                                  # post
    ok = df[df["status"].isin(["trade", "limit_up", "limit_down"])]
    missing = len(members) * len(days) - len(ok.drop_duplicates(["code", "date"]))     # 网格缺行数
    panel = ok.rename(columns=FIELD_MAP)[list(FIELD_MAP.values())].sort_values(["symbol", "date"])   # drop

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
            "missing_rows": {"count": int(missing), "policy_applied": "drop"},
            # 档位 `s2_adjust_report` 要求申报**实际**用的复权口径（校验器据此判 `adjust_applied_mismatch`）。
            # 本题上面那段 `df[c] * df["adj_factor"]` 走的就是 post，与声明一致。
            "adjust_applied": decl["adjust"],
            # 自报仅供人读；结算用 access_log 与 runner 计时（验行为不验申报）
            "efficiency_self_report": {"gateway_requests": N_REQUESTS, "wall_seconds": round(time.monotonic() - t0, 3)},
        },
    }
    _oracle_write(CTX, artifact)          # 标准路径 + 0600（红线 5：裸 write 吃 umask 落 0664，网关守门当场拒起）


if __name__ == "__main__":
    sys.exit(main())
