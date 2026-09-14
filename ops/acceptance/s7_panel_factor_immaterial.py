# -*- coding: utf-8 -*-
"""证明：`factor` 在**无价格**的格上取什么值，对 S7 的任何指标都没有影响。

**为什么需要这条**：网关拼出的面板与冻结 ε 面板在 46,265 个格上 `factor` 空值形态不同 ——
全部是 `close` 为空的格（冻结面板残留 qlib 上市窗口内的因子，本仓按契约 §1 置空）。
「三份实现都只写 `close / factor`，所以读不到」是**论证**不是判据（D-28）。
这里把它变成实测：喂真改动（把那些格的 factor 全置 NaN），三份实现的指标必须**逐位不变**。

对照方向同样要在（D-30）：再喂一个**会被读到**的改动 —— 把**有价格**的格的 factor 乘 1.01 ——
必须让指标动。只有「该动的动了、不该动的没动」两半都成立，这条才算证完。
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PY = "/data/shared/genebench/env/bin/python"
SNAP = Path("/data/shared/genebench/snapshots/v1/epsilon")
PANEL_NAME = "bt_input_csi300_v2.parquet"
WORK = Path("/data/shared/genebench/scratch/s7_factor_immat")
FREQ = "daily"                                  # 已发布的五道 S7 题全部 declared daily
IMPLS = {"B1": ("impl_v2_b1.py", "out_v2_b1_{f}.json", ["{f}"]),
         "B2": ("impl_v2_b2.py", "out_v2_b2_{f}.json", ["{f}"]),
         "B3": ("impl_v2_b3.py", "out_v2_b3_{f}.json", [])}
#: 字符串/机械计数不进比较。
SKIP = ("n_days", "rebalance_frequency", "total_cost_source", "freq")


def variants(ref: pd.DataFrame) -> dict[str, pd.DataFrame]:
    unpriced = ref.close.isna()
    blanked = ref.copy()
    blanked.loc[unpriced, "factor"] = np.nan                     # 待证的那处差异
    perturbed = ref.copy()
    perturbed.loc[~unpriced, "factor"] = perturbed.loc[~unpriced, "factor"] * 1.01   # 阳性对照
    return {"base": ref, "blanked": blanked, "perturbed": perturbed}


def run_impl(name: str, panel: pd.DataFrame, tag: str) -> dict:
    src, out_tmpl, argv = IMPLS[name]
    d = WORK / tag / name
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    shutil.copy2(SNAP / src, d / src)
    panel.to_parquet(d / PANEL_NAME, index=False, compression="zstd")
    cmd = [PY, str(d / src)] + [a.format(f=FREQ) for a in argv]
    r = subprocess.run(cmd, cwd=d, capture_output=True, text=True, timeout=3600)
    out = d / out_tmpl.format(f=FREQ)
    if r.returncode != 0 or not out.exists():
        raise RuntimeError(f"{name}/{tag} 失败 rc={r.returncode}: {r.stderr[-500:]}")
    return json.loads(out.read_text())


def diff(a: dict, b: dict) -> dict:
    keys = sorted((set(a) | set(b)) - set(SKIP))
    return {k: [a.get(k), b.get(k)] for k in keys if a.get(k) != b.get(k)}


def main() -> int:
    ref = pd.read_parquet(SNAP / PANEL_NAME)
    v = variants(ref)
    rep: dict = {"freq": FREQ,
                 "unpriced_cells": int(ref.close.isna().sum()),
                 "factor_present_on_unpriced_in_frozen": int(
                     (ref.close.isna() & ref.factor.notna()).sum()),
                 "impls": {}}
    for name in IMPLS:
        base = run_impl(name, v["base"], "base")
        blanked = run_impl(name, v["blanked"], "blanked")
        perturbed = run_impl(name, v["perturbed"], "perturbed")
        rep["impls"][name] = {
            "blanked_diff": diff(base, blanked),          # 必须空 —— 无价格上的 factor 读不到
            "perturbed_diff_keys": sorted(diff(base, perturbed)),  # 必须非空 —— 阴性对照会绿到底
            "n_metrics": len([k for k in base if k not in SKIP]),
        }
    rep["ok"] = all(not r["blanked_diff"] and r["perturbed_diff_keys"]
                    for r in rep["impls"].values())
    out = Path(__file__).resolve().parents[1] / "reports" / "s7_panel_factor_immaterial.json"
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    out.chmod(0o600)
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    shutil.rmtree(WORK, ignore_errors=True)
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
