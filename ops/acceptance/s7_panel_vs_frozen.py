# -*- coding: utf-8 -*-
"""验收：经网关拼出的 S7 面板 ≡ 冻结的 ε 面板（卡 2.6 / B8）。

**为什么这条验收有效**：两侧是两条独立链路 ——

| 列 | 冻结面板（`scratch/export_input2.py`，qlib）| 本仓 oracle（`reference/s7_oracle_common.fetch_panel`，网关）|
| --- | --- | --- |
| `close`/`factor` | qlib `D.features($close,$factor)` | `/bars` 原始 close × (`/adj` adj_factor ÷ as_of 基准) |
| `in_universe` | qlib instruments 的 `in_date/out_date` 区间 | `/universe` **逐日 PIT** 名单 |
| `has_price`/`is_delisted` | 同一套判定式 | 同一套判定式（口径抄自构建脚本，已核对源码）|

前两行是**不同数据源、不同算法**，第三行是同一条规则的两次实现。所以逐格相等
不是自证 —— 它排掉的是「网关取数口径与 ε 那次不同」这一整类错误，
而那类错误的表现是 S7 全部 11 项指标一起偏，没有任何一项报错。

数值判据是**逐位相等**（2026-09-05 起）。此前是「相对差 ≤ 1e-6」——
那时 `fetch_panel` 产出 float64、冻结面板存 float32，只能比到 6e-08。
把 `fetch_panel` 的 `close`/`factor` 落成 float32 之后两侧逐位相同，
判据就该跟着收紧：**能比到位的地方不许留容差**，留着的那点余量只会用来藏错。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from reference.gateway_client import Client                      # noqa: E402
from reference import s7_oracle_common as cor                    # noqa: E402

FROZEN = Path("/data/shared/genebench/snapshots/v1/epsilon/bt_input_csi300_v2.parquet")
GATEWAY = "http://192.168.1.48:18080"
#: 逐位相等之外不留余量。保留常量是为了让报告里的 `n_over_tol` 有个显式的 0 门槛。
TOL = 0.0


def build(window: dict, as_of: str, universe: str) -> tuple[pd.DataFrame, Client]:
    gw = Client(GATEWAY, task_id="acceptance-s7-panel", as_of=as_of)
    return cor.fetch_panel(gw, {"window": window, "as_of": as_of, "universe": universe}), gw


def compare(new: pd.DataFrame, ref: pd.DataFrame) -> dict:
    key = ["date", "code"]
    m = new.merge(ref, on=key, how="outer", suffixes=("_new", "_ref"), indicator=True)
    rep: dict = {
        "cells_new": len(new), "cells_ref": len(ref),
        "only_new": int((m._merge == "left_only").sum()),
        "only_ref": int((m._merge == "right_only").sum()),
        "columns": {},
    }
    both = m[m._merge == "both"]
    # `factor` 在无价的格上没有定义（契约 §1 只给了 `原始价 = close / factor`）。
    # 冻结面板在那里残留 qlib 上市窗口的因子值，本仓按契约置空 —— 这处差异**不放过、要证**：
    # 判据是「两侧都不存在 factor 空而 close 非空的格」+ 一条独立的实质性证明（见 rep["factor_only_where_priced"]）。
    priced = both.close_new.notna() | both.close_ref.notna()
    rep["factor_only_where_priced"] = {
        side: int((both[f"factor_{side}"].isna() & both[f"close_{side}"].notna()).sum())
        for side in ("new", "ref")}
    rep["factor_nan_diff_all_unpriced"] = bool(
        (both.factor_new.isna() != both.factor_ref.isna()).loc[priced].sum() == 0)
    rep["factor_nan_diff_cells"] = int((both.factor_new.isna() != both.factor_ref.isna()).sum())
    both = both  # noqa: PLW0127  （下面按列各自挑可比子集）
    for col in ("close", "factor"):
        a, b = both[f"{col}_new"].astype("float64"), both[f"{col}_ref"].astype("float64")
        ok = a.notna() & b.notna()
        rel = ((a[ok] - b[ok]).abs() / b[ok].abs().clip(lower=1e-12))
        bits_equal = bool((a[ok].astype("float32").to_numpy().view("uint32")
                           == b[ok].astype("float32").to_numpy().view("uint32")).all())
        rep["columns"][col] = {
            "nan_pattern_equal": bool((a.isna() == b.isna()).all()),
            "nan_mismatch": int((a.isna() != b.isna()).sum()),
            "max_rel_diff": float(rel.max()) if len(rel) else None,
            "n_over_tol": int((rel > TOL).sum()),
            "bitwise_equal": bits_equal,
        }
    for col in ("in_universe", "has_price", "is_delisted"):
        d = both[f"{col}_new"].fillna(False).astype(bool) != both[f"{col}_ref"].fillna(False).astype(bool)
        rep["columns"][col] = {"mismatch": int(d.sum()),
                               "examples": both.loc[d, key].head(5).to_dict("records")}
    return rep


def verdict(rep: dict) -> bool:
    if rep["only_new"] or rep["only_ref"]:
        return False
    if any(rep["factor_only_where_priced"].values()) or not rep["factor_nan_diff_all_unpriced"]:
        return False
    for col in ("close", "factor"):
        c = rep["columns"][col]
        if not c["bitwise_equal"] or c["n_over_tol"]:
            return False
        if col == "close" and not c["nan_pattern_equal"]:
            return False
    return not any(rep["columns"][c]["mismatch"] for c in ("in_universe", "has_price", "is_delisted"))


def main() -> int:
    ref = pd.read_parquet(FROZEN)
    window = {"start": "2019-01-02", "end": str(ref.date.max())}
    t0 = time.time()
    new, gw = build(window, as_of="2026-07-31", universe="csi300")
    rep = compare(new.drop(columns=["signal"]), ref.drop(columns=["signal"]))
    rep["wall_seconds"] = round(time.time() - t0, 1)
    rep["gateway_requests"] = len(gw.ledger)
    rep["by_endpoint"] = pd.Series([x["endpoint"] for x in gw.ledger]).value_counts().to_dict()
    rep["denied_or_empty"] = [x for x in gw.ledger if x["status"] not in ("ok",)][:5]
    rep["ok"] = verdict(rep)
    out = Path(__file__).resolve().parents[1] / "reports" / "s7_panel_vs_frozen.json"
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    out.chmod(0o600)
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
