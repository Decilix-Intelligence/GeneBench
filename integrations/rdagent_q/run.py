#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RD-Agent(Q) 作为 GeneBench 被测方（P2）的入口。

顺序是**有讲究的**，不能重排：

  ① `glue.bootstrap.apply()` —— 摆环境变量。必须在任何 `import rdagent` **之前**：
     RD-Agent 的设置是模块级 pydantic 单例，import 那一刻就把 env 读完了。
  ② 读题面 `/task/INSTRUCTION.md`（唯一题面）→ `set_as_of` → 经垫片取数。
  ③ 把取到的数落成 RD-Agent 因子路径认得的 qlib 面板。
  ④ 交给 RD-Agent 自己的 `FactorCoSTEER` 循环（模型经边车）。
  ⑤ 写题面点名的产出文件 `/task/values.parquet`，再用 `emit` 写 `/task/artifact.json`。

**跑不出值时也写产物**：覆盖率如实写 0，不编一列数。
「什么都没算出来」是一个结论；空产物则什么都不是。
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from glue import bootstrap  # noqa: E402

ENV_SNAPSHOT = bootstrap.apply()          # ← 必须在 import rdagent 之前

import genebench_client as gb             # noqa: E402
from genebench_client import emit         # noqa: E402
from glue import develop, instruction, panel  # noqa: E402

TASK = pathlib.Path(os.environ.get("GENEBENCH_TASK_DIR", "/task"))
VALUES_PATH = TASK / "values.parquet"


def _values_frame(df):
    """RD-Agent 的 `result.h5` → 题面契约的长表（date / code / value）。

    契约（题面逐字给出，也在 `genetask/file_contract.py::FILE_SPECS["S3"]`）：
    列序 `date, code, value`，按 `date, code` 升序，不写行索引，`value` 是 float64。
    **一条都不许省** —— 少一条，两个同样正确的实现字节就不同，而字节摘要是被计分的量。
    """
    import pandas as pd

    if hasattr(df, "to_frame") and getattr(df, "ndim", 2) == 1:
        df = df.to_frame("value")
    df = df.copy()
    col = df.columns[-1]
    if getattr(df.index, "nlevels", 1) > 1:
        idx = df.index.to_frame(index=False)
        dates, codes = idx.iloc[:, 0], idx.iloc[:, 1]
    else:                                   # 极少见：模型把维度写成了普通列
        cols = [c for c in df.columns if c != col]
        if len(cols) < 2:
            raise RuntimeError(f"读不出 (date, code) 两维；实得列 {list(df.columns)}")
        dates, codes = df[cols[0]], df[cols[1]]
    out = pd.DataFrame({
        "date": pd.to_datetime(dates).dt.strftime("%Y-%m-%d"),
        "code": [panel.to_gateway_code(c) for c in codes],
        "value": pd.to_numeric(df[col].to_numpy(), errors="coerce").astype("float64"),
    })
    return out.sort_values(["date", "code"]).reset_index(drop=True)


def _write_values(frame):
    frame.to_parquet(VALUES_PATH, index=False)
    return hashlib.sha256(VALUES_PATH.read_bytes()).hexdigest()


def _stats(frame, panel_df, lookback):
    """从**落盘的那一份**重算自报值。全部是清点，没有一处是"应该是多少"。"""
    import numpy as np
    import pandas as pd

    v = frame["value"].to_numpy(dtype="float64")
    finite = np.isfinite(v)
    # 覆盖率的分母是**面板的格子数**（题面窗口 × universe），不是产出的行数 ——
    # 只写出一半的行而每行都有限，覆盖率不该是 1。
    n_dates = int(panel_df.index.get_level_values(0).nunique())
    n_syms = int(panel_df.index.get_level_values(1).nunique())
    cells = n_dates * n_syms
    coverage = (float(finite.sum()) / cells) if cells else 0.0

    warm = 0
    if isinstance(lookback, int) and lookback > 1 and len(frame):
        days = sorted(pd.unique(panel_df.index.get_level_values(0)))[: lookback - 1]
        early = {pd.Timestamp(d).strftime("%Y-%m-%d") for d in days}
        m = frame["date"].isin(early).to_numpy()
        warm = int(np.isfinite(v[m]).sum())
    uniq = np.unique(v[finite])
    is_const = bool(len(uniq) <= 1)
    return {
        "values_ref": {"coverage": min(max(coverage, 0.0), 1.0), "sha256": None,
                       "rows": int(len(frame)), "n_dates": n_dates, "n_symbols": n_syms},
        # `replaced_count` 是**我们这一层**替换掉的个数。这一层一个都没替
        # （nonfinite_policy=propagate 时这正是题面要的），所以是 0。
        "nonfinite": {"inf_count": int(np.isinf(v).sum()),
                      "nan_count": int(np.isnan(v).sum()), "replaced_count": 0},
        "warmup": {"nonnull_before_warmup": warm},
        "degeneracy": {"is_constant": is_const, "alert": is_const},
    }


def main() -> int:
    print("[rdagent_q] env:", json.dumps(ENV_SNAPSHOT, ensure_ascii=False), flush=True)

    spec = instruction.parse((TASK / "INSTRUCTION.md").read_text(encoding="utf-8"))
    print("[rdagent_q] spec:", instruction.summary(spec), flush=True)

    gb.set_as_of(spec.as_of)                       # 启动时一次；取不到就抛，不猜
    cli = gb.client()

    fields = spec.declarations.get("required_fields")
    if not isinstance(fields, list) or not fields:
        raise SystemExit("题面没有给 required_fields（或形态不是列表）。"
                         "**不猜**：S3 的 /bars 不显式传 fields 是畸形不是缺省。")
    codes = cli.members(spec.universe, spec.as_of)
    bars = cli.bars(codes, spec.window_start, spec.window_end, fields=fields)
    pan = panel.build_panel(bars, fields)
    digests = panel.write_panel(pan, bootstrap.DATA_FOLDER)
    print(f"[rdagent_q] 面板 {pan.shape} 落到 {bootstrap.DATA_FOLDER}：{digests}", flush=True)

    values, meta = develop.develop(spec)
    print("[rdagent_q] develop:", json.dumps(
        {k: v for k, v in meta.items() if k != "factor_code"}, ensure_ascii=False)[:4000], flush=True)
    if meta.get("factor_code"):
        print("[rdagent_q] ---- factor.py（系统写出来的那一份）----", flush=True)
        print(meta["factor_code"][:6000], flush=True)
        print("[rdagent_q] ---- factor.py 结束 ----", flush=True)

    import pandas as pd
    if values is None:
        print("!! 没有算出任何因子值 —— 如实写一份覆盖率 0 的产物，不编数。", flush=True)
        frame = pd.DataFrame({"date": pd.Series(dtype="object"),
                              "code": pd.Series(dtype="object"),
                              "value": pd.Series(dtype="float64")})
    else:
        frame = _values_frame(values)
    sha = _write_values(frame)
    st = _stats(frame, pan, spec.declarations.get("lookback"))
    st["values_ref"]["sha256"] = sha
    print("[rdagent_q] stats:", json.dumps(st, ensure_ascii=False), flush=True)

    art = emit.emit_s3(
        factor_id=spec.factor_id,
        expression=spec.expression,
        values_ref={"coverage": st["values_ref"]["coverage"], "sha256": sha},
        nonfinite=st["nonfinite"],
        warmup=st["warmup"],
        # 空列表与「没写」不是一件事：前者是「我没做近似」。题面明说算子不得自行替换，
        # 我们这一层也没有替换 —— 模型写的代码里有没有近似**我们无从核验**，
        # 这一点写在 README 的「已知限制」里，不在这里用一个猜出来的值遮掉。
        approximated_operators=[],
        degeneracy=st["degeneracy"],
        declarations=spec.declarations,
        as_of=spec.as_of,
    )
    out = art.write(TASK / "artifact.json")
    print(f"[rdagent_q] wrote {out}；values.parquet rows={len(frame)} sha256={sha[:16]}…", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
