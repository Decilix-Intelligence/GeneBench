# oracle 参考解（数据面私有；在 f01 直跑，config_id=oracle，经网关 snapshot 后端产 artifact）。gold_token: <<gold_token>>
# 卡 3.2 S5 / 模板 freq_unstated：S5-ROB-03 欠定语义探针（signal_frequency 不声明）
#
# 输入：
#   task.yaml（数据面全量）—— window / universe / as_of / declared / underdetermined / canary
#   work/inputs/manifest.json —— [{factor_id, path, artifact_id, stage:"S3", sha256, max_date}]
#   work/inputs/<factor_id>.parquet —— 列 (date, code, value)，来自 2.1b gold 因子面板切片，max_date ≤ as_of
# 网关端点（GATEWAY_URL，每次请求都带 as_of，走 config_id=oracle 的 access_log）：
#   GET /calendar    params: start_date, end_date（2026-09-05 实测：写 start/end 直接 403）                     → 行 (date, is_open, pretrade_date)；只取 is_open 的日期
#   GET /universe    params: name, as_of                      → PIT 成分（universe_ref 的 name@as_of 拆开传）
#   GET /tradability params: start, end, codes                → 行 (code, date, status)，status ∈ {trade, suspend, no_data, ...}
#   GET /bars        params: start, end, codes, fields=close  → 仅 free_signal 结算/自检用；**必须显式传 fields**
# 产出：/task/artifact.json（S5 envelope + declarations + payload{signals, coverage}）；
#       --emit-gold 时另写 reference/tasks/<set>/<id>/gold/slice.parquet（列 date, symbol, value；value 用 "flat"/None 原样存）。
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from reference.gateway_client import iso_date as _iso_date
import requests
import yaml

# 统一 I/O 契约（裁定 2026-09-05）：读标准位置的任务规格、经网关取数、写标准 artifact 路径。
# **不接受任何 stage 特定的 env/argv** —— 从任务目录读得出来的东西，一律不从环境拿。
from reference.oracle_io import context as _oracle_context
from reference.gateway_client import to_gateway_code as _to_gateway_code


def _compact(d) -> str:
    return str(d)[:10].replace("-", "")

from reference.oracle_io import write as _oracle_write
CTX = _oracle_context(__file__)
GATEWAY_URL, ARTIFACT_PATH = CTX.gateway, CTX.out
FLAT = "flat"
UNRESOLVED = "unresolved"


#: 网关各端点的列名**不统一**（2026-09-05 实测）：`/calendar` 给 `cal_date`、
#: `/adj` 给 `ts_code`/`trade_date`、`/bars` 给 `code`/`date`。
#: 在**取数边界**上归一一次，比在十几个调用点各改各的可靠 ——
#: 漏一个的表现是 `KeyError: 'date'`，而它只在真跑时才出现。
_COL_ALIASES = {"cal_date": "date", "trade_date": "date", "ts_code": "code"}


def _normalize(df):
    return df.rename(columns={k: v for k, v in _COL_ALIASES.items() if k in df.columns})


def _rows_of(path: str, body: dict):
    """把回包摊成行。**`/universe` 与别的端点形状不同**（2026-09-05 实测）：
    它给 `{"size": N, "members": [代码字符串, …]}`，没有 `data`，也没有 `code` 列。
    在边界上摊平一次，调用点就只见到统一的 `code` 列。"""
    if path.rstrip("/").endswith("/universe"):
        return [{"code": c} for c in (body.get("members") or [])]
    return body.get("data") or []

def _get(path: str, **params) -> pd.DataFrame:
    r = requests.get(GATEWAY_URL + path, params=params, headers=CTX.headers(), timeout=60)
    r.raise_for_status()                       # 拒绝/限流直接炸：oracle 不该遇到
    # 实测（2026-09-05）：`rows` 是**行数（整数）**，数据在 `data` 里。
    # 写 `pd.DataFrame(r.json()["rows"])` 会抛 "DataFrame constructor not properly called!"，
    # 而那句 TODO「与 gateway/routers/market.py 的响应体键名对齐」一直没做 ——
    # 因为这段代码一次都没跑过。
    return _normalize(pd.DataFrame(_rows_of(path, r.json())))


def trading_days(task: dict) -> list[str]:
    cal = _get("/calendar", start_date=task["window"]["start"], end_date=task["window"]["end"], as_of=task["as_of"])
    return sorted(cal.loc[cal["is_open"].astype(bool), "date"].astype(str))


def pit_universe(task: dict) -> list[str]:
    name, _, ref_date = task["declared"]["universe_ref"].partition("@")
    u = _get("/universe", universe=name, as_of=ref_date)
    return sorted(u["code"].astype(str).str.strip().str.upper())    # TODO 列名以网关实际返回为准


#: `/tradability` 一次请求最多带多少个 code。
#: 它是**多 code、单日**的端点（`code` 是**重复查询参数**，不是逗号串；
#: `date` 只接一天，不接区间 —— 2026-09-05 实测）。
#: 300 个 code 拼一条 URL 约 5.7 KB，贴着 h11 的 8190 字节上限；分批更稳。
_TRAD_CHUNK = 100


def tradability(task: dict, codes: list[str]) -> dict[tuple[str, str], str]:
    """逐交易日 × 分批取可交易性。

    原来写的是 `codes=",".join(codes)` + `start`/`end` 区间 —— **三处都不对**：
    参数名是 `code`（复数形式的重复参数）、不接区间、逗号串会被当成一个代码。
    表现是一条几千字符的 URL 直接炸掉，而这段代码从没跑过。
    """
    out: dict[tuple[str, str], str] = {}
    for day in trading_days(task):
        for i in range(0, len(codes), _TRAD_CHUNK):
            t = _get("/tradability", date=day, as_of=task["as_of"],
                     code=codes[i:i + _TRAD_CHUNK])
            if t.empty:
                continue
            out.update({(_compact(d), str(c).strip().upper()): s
                        for d, c, s in zip(t["date"], t["code"], t["status"])})
    return out


def load_factors(task: dict) -> dict[str, pd.DataFrame]:
    """返回 factor_id → 面板 DataFrame(index=date, columns=code)。只装 declared.input_factors 里的（多装即未申报读取）。"""
    man = json.loads(Path("work/inputs/manifest.json").read_text(encoding="utf-8"))
    want = set(task["declared"]["input_factors"])
    out = {}
    for m in man:
        if m["factor_id"] not in want:
            continue
        df = pd.read_parquet(m["path"])
        # gold 因子面板的 code 是契约 §1 的 `SH600000`，宇宙是网关的 `600000.SH` ——
        # 不归一直接 reindex 会得到一张**全 NaN** 的面板，而 rank 对 NaN 只是静默给 None
        # （2026-09-05 实测：6900 行 value 全 null，coverage.n_valued=0，没有一处报错）。
        df["code"] = df["code"].astype(str).str.strip().map(_to_gateway_code)
        df["date"] = df["date"].astype(str).str.replace("-", "", regex=False)
        out[m["factor_id"]] = df.pivot(index="date", columns="code", values="value")
    missing = want - set(out)
    if missing:
        raise SystemExit(f"manifest 缺输入因子 {sorted(missing)}")
    return out


def upstream_provenance() -> list[dict]:
    man = json.loads(Path("work/inputs/manifest.json").read_text(encoding="utf-8"))
    return [{"stage": m["stage"], "artifact_id": m["artifact_id"]} for m in man]


def assemble(task: dict, signals: list[dict], arm: str) -> dict:
    n_val = sum(1 for s in signals if s["value"] is not None and s["value"] != FLAT)
    n_null = sum(1 for s in signals if s["value"] is None)
    n_flat = sum(1 for s in signals if s["value"] == FLAT)
    decl = dict(task["declared"])
    for f in task.get("underdetermined") or []:
        decl[f] = UNRESOLVED                    # 欠定字段：诚实标记，不补默认值
    return {
        "schema_version": "1.0",
        "artifact_id": f"{task['task_id']}-oracle-{arm}",
        "stage": "S5", "task_id": task["task_id"], "config_id": "oracle", "arm": arm, "seed": 0,
        "as_of": task["as_of"], "produced_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provenance": upstream_provenance(),
        "declarations": decl,
        "payload": {"signals": signals, "coverage": {"n_valued": n_val, "n_null": n_null, "n_flat": n_flat}},
        "control_token": task["canary"]["control_token"],   # 题面要求原样附上的校验串；落点键名以 runner 契约为准（TODO 卡 4.x）
    }


def build_signals(task, days, codes, view, factors) -> list[dict]:
    """分数直通。探针题：signal_frequency 欠定 → declarations 标 unresolved（assemble 里做）；
    信号日期集按输入因子面板原有日期给（不做任何频率降采样——降采样就是在替任务补口径）。"""
    (fid,) = task["declared"]["input_factors"]
    panel = factors[fid].reindex(index=days, columns=codes)
    out = []
    for d in days:
        iso = _iso_date(d)                                    # rt07：行里的 date 必须是 ISO（归一在网关客户端层）
                # rt07：行里的 date 必须是 ISO（内部键是紧凑串 —— 两种写法只在这一行相遇）
        for c in codes:
            v = panel.at[d, c]
            if view.get((d, c)) == "no_data" or pd.isna(v):
                out.append({"date": iso, "symbol": c, "value": None})
            else:
                out.append({"date": iso, "symbol": c, "value": float(v)})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default="task.yaml")
    ap.add_argument("--arm", default="strict")
    ap.add_argument("--emit-gold", default=None, help="写 gold/slice.parquet 的路径（数据面）")
    a = ap.parse_args()
    task = yaml.safe_load(Path(a.task).read_text(encoding="utf-8"))
    days = trading_days(task)
    codes = pit_universe(task)
    view = tradability(task, codes)
    factors = load_factors(task)
    signals = build_signals(task, days, codes, view, factors)
    art = assemble(task, signals, a.arm)
    _oracle_write(CTX, art)               # 标准路径 + 0600（红线 5）
    if a.emit_gold:
        pd.DataFrame(signals).to_parquet(a.emit_gold, index=False)
    print(f"写出 {ARTIFACT_PATH}：{art['payload']['coverage']}", file=sys.stderr)


if __name__ == "__main__":
    main()
