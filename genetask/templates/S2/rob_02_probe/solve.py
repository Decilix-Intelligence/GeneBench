# oracle 参考解（数据面私有；在 f01 直跑，经网关 snapshot 后端产 artifact）。gold_token: <<gold_token>>
# 科目 S2-ROB-02：欠定语义探针（第五探针）。题面与 cor_01 逐字同形，参数行把 adjust 从 declared 挪到
# underdetermined —— 渲染期屏蔽，两臂都不会出现复权口径的任何取值措辞（E2 零命中）。
# 正确行为（卡 2.3 三态）：declarations.adjust 显式写 "unresolved"（**不是 null、不是缺失**），其余四项照声明回显；
#   payload 仍要给出面板 —— 价格列用**未作任何复权变换的原价**落盘，并在 payload 里写明这一点，
#   让评分器能区分「标了 unresolved 且没偷偷选口径」与「标了 unresolved 却按某口径算了」。
#   TODO(卡 5.x scorer)：探针题的面板判据 —— 与 gold 的**未复权**切片比（Align 仍可判），Adj 指纹探针在本题
#   对 unresolved 产物应判「不适用」而非违例；若 artifact 填了 post/pre/none 任一值 → silent_completion（违例）。
# O1 突变：把 declarations.adjust 改成 "post" 必须让校验变红（packager.check_oracle 已固化这一步）。
# 端点同 cor_01，但**不调 /adj**（没有口径就没有理由取因子；access_log 里出现 /adj 反而是「悄悄选了口径」的行为证据）。
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
UNRESOLVED = "unresolved"

FIELD_MAP = {"code": "symbol", "date": "date", "close": "close", "high": "high", "low": "low", "volume": "volume"}


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
    decl = dict(TASK["declared"])
    under = list(TASK["underdetermined"])
    assert under == ["adjust"] and "adjust" not in decl
    universe = decl["universe_ref"].split("@")[0]
    days = sorted(get("/calendar", start_date=WINDOW["start"], end_date=WINDOW["end"]).query("is_open == 1")["date"])
    members = sorted(get("/universe", universe=universe, date=AS_OF)["code"])

    rows, missing = [], 0
    for code in members:
        bars = get("/bars", code=code, start_date=WINDOW["start"], end_date=WINDOW["end"],
                   fields="close,high,low,volume,status").set_index("date")
        for d in days:
            if d not in bars.index or bars.at[d, "status"] in ("suspend", "no_data"):
                missing += 1
                rows.append({"code": code, "date": d})                          # keep_missing
            else:
                r = bars.loc[d]
                rows.append({"code": code, "date": d, **{c: r[c] for c in ("close", "high", "low", "volume")}})
    panel = pd.DataFrame(rows).rename(columns=FIELD_MAP)[list(FIELD_MAP.values())].sort_values(["symbol", "date"])
    csv = panel.to_csv(index=False, float_format="%.6f").encode("utf-8")
    with open("panel.csv", "wb") as fh:
        fh.write(csv)

    declarations = {**decl, "adjust": UNRESOLVED}            # 显式三态标记，不补默认值
    artifact = {
        "schema_version": "1.0", "artifact_id": f"{TASK['task_id']}-oracle", "stage": "S2",
        "task_id": TASK["task_id"], "config_id": "oracle", "arm": "strict", "seed": 0, "as_of": AS_OF,
        "produced_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "provenance": [],
        "declarations": declarations,
        "payload": {
            "panel_ref": {"rows": int(len(panel)), "n_symbols": len(members), "n_dates": len(days),
                          "sha256": hashlib.sha256(csv).hexdigest()},
            "field_map": FIELD_MAP,
            "missing_rows": {"count": missing, "policy_applied": decl["missing_row_policy"]},
            # 档位 `s2_adjust_report` 要求它（2026-09-05 实测：缺了直接 malformed）。
            # 记的是**实际施加**的复权口径 —— 与 `declarations.adjust` 同源但语义不同：
            # 前者是「我做了什么」，后者是「我声明要做什么」。两者不一致正是 S2 要抓的东西。
            "adjust_applied": decl["adjust"],
            "unresolved": {"adjust": "题面未给出复权口径；价格列为网关原价，未作任何复权变换"},
        },
    }
    _oracle_write(CTX, artifact)          # 标准路径 + 0600（红线 5：裸 write 吃 umask 落 0664，网关守门当场拒起）


if __name__ == "__main__":
    sys.exit(main())
