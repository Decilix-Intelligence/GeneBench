# -*- coding: utf-8 -*-
"""W2-1：把 `factor_library/compiled/` 三件冻结件收进仓库，并与 gold 逐条对账。

    $PY snapshots/public/recover_factor_library.py            # 只对账，不写
    $PY snapshots/public/recover_factor_library.py --write    # 拷贝进仓库 + 对账

**这三件不是「丢了」**：它们一直在数据湖
`$LAKE/reference/factor_library/compiled/`（`reference.factor_exec.FACTOR_LIB`
就是从那里读的），只是 `PUBLIC_FROZEN_ARTIFACTS` 用的是**仓库相对路径**，
而仓库里没有这棵子树 —— 于是 `ops/mk_release_manifest.py` 把它们记成缺件。
公开包必须自足（拿到包的人没有我们的湖），所以把它们**钉进仓库**。

对账不看「文件在不在」，看**它们还是不是当初算出 gold 的那三份**：

1. 后端分布（`fx.load_records()` 自带的硬核对）：644 / 66 / 82 + blocked 24；
2. 从**仓库副本**重新推导 `reference.operator_flags` 的两个集合，
   与 2026-09-01 写进快照的 `operator_convention_suspect.json` **逐条比**
   —— 对得上就说明算子冲突名单（13 条 τ 排除 / 23 条 gold 存疑）是从这三份来的；
3. 用 13 条 τ 排除名单去筛互检逐格明细，复现报告 §10 的 **141 因子 / 379,950 格**。

对不上就 **exit 1 并把差异打出来**，不凑数。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import genebench_config as cfg  # noqa: E402

REPO = Path(__file__).resolve().parents[2]

#: 仓库内的落点 —— 逐字等于 `PUBLIC_FROZEN_ARTIFACTS` 里声明的那三条相对路径。
DEST = REPO / "factor_library" / "compiled"
#: 上游（湖）。只读，本脚本从不往这里写。
SRC = cfg.LAKE / "reference" / "factor_library" / "compiled"
NAMES = ("qlib_native.jsonl", "qlib_panel.jsonl", "blocked.jsonl")

#: 报告 §10「剔掉源方言用 Ts_Rank 的 13 条」那一行的两个数。
EXPECTED_TAU_TRIMMED = {"factors": 141, "cells": 379950}


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def copy_in() -> dict[str, dict]:
    cfg.create_dir(DEST)
    (DEST.parent).chmod(0o700)
    out = {}
    for n in NAMES:
        s, d = SRC / n, DEST / n
        if not s.is_file():
            raise SystemExit(f"上游缺件：{s}")
        shutil.copyfile(s, d)
        d.chmod(0o600)
        out[n] = {"sha256": sha256(d), "bytes": d.stat().st_size,
                  "src_sha256": sha256(s), "same": sha256(d) == sha256(s)}
    return out


def reconcile() -> dict:
    """从**仓库副本**读记录，重新推导 gold 侧的标注并与快照里的比对。"""
    from reference import factor_exec as fx

    if not (DEST / NAMES[0]).is_file():
        raise SystemExit(f"仓库副本不存在，先跑 --write：{DEST}")
    fx.FACTOR_LIB = DEST                      # 关键：读仓库副本，不读湖
    recs, prov = fx.load_records()            # 后端分布对不上会自己抛

    from reference import operator_flags as of

    side = json.loads((cfg.SNAPSHOTS_V1 / "gold_factors" /
                       "operator_convention_suspect.json").read_text(encoding="utf-8"))
    comparable = [x["id"] for x in json.loads(
        (cfg.OPS / "acceptance" / "card_2.1b_crosscheck.json").read_text(encoding="utf-8"))["rows"]]

    gs = of.gold_suspect(recs)
    te = of.tau_excluded(comparable, recs)

    diffs: list[str] = []
    if gs != side["gold_suspect"]:
        diffs.append(f"gold_suspect 不一致：多 {sorted(set(gs)-set(side['gold_suspect']))} "
                     f"少 {sorted(set(side['gold_suspect'])-set(gs))}")
    if te != side["tau_excluded"]:
        diffs.append(f"tau_excluded 不一致：多 {sorted(set(te)-set(side['tau_excluded']))} "
                     f"少 {sorted(set(side['tau_excluded'])-set(te))}")

    # —— 报告 §10：剔掉 13 条之后的因子数与格数
    import pandas as pd
    cells = pd.read_parquet(cfg.SNAPSHOTS_V1 / "crosscheck" / "rank_ic_cells_csi300.parquet")
    col = "factor_id" if "factor_id" in cells.columns else cells.columns[0]
    rho = next((c for c in ("rho", "rank_ic", "spearman") if c in cells.columns), None)
    kept = cells[~cells[col].isin(te)]
    if rho is not None:
        kept = kept[kept[rho].notna()]
        if "degenerate" in kept.columns:
            kept = kept[~kept["degenerate"].astype(bool)]
    got = {"factors": int(kept[col].nunique()), "cells": int(len(kept))}
    if got != EXPECTED_TAU_TRIMMED:
        diffs.append(f"§10 「剔 Ts_Rank 13 条」对不上：实测 {got}，报告 {EXPECTED_TAU_TRIMMED}")

    return {"backend_counts": prov["backend_counts"], "files": prov["files"],
            "gold_suspect_n": len(gs), "tau_excluded_n": len(te),
            "tau_trimmed": got, "cells_columns": list(cells.columns), "diffs": diffs}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="从湖拷进仓库")
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args()

    copied = copy_in() if a.write else {}
    if copied:
        for n, m in copied.items():
            print(f"  收进 {n}  {m['bytes']:,} B  sha256={m['sha256'][:16]}…  "
                  f"与湖一致={m['same']}")
    rep = reconcile()
    rep["copied"] = copied
    print(f"后端分布 {rep['backend_counts']}")
    print(f"gold 存疑 {rep['gold_suspect_n']} 条 · τ 排除 {rep['tau_excluded_n']} 条 · "
          f"剔后 {rep['tau_trimmed']}")
    if a.json:
        a.json.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
        a.json.chmod(0o600)
    if rep["diffs"]:
        print("对账不通过：")
        for d in rep["diffs"]:
            print("  ✗ " + d)
        return 1
    print("对账通过：重生成的标注与 2026-09-01 写进快照的逐条相同。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
