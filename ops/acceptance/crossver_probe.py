#!/usr/bin/env python3
"""跨版本数值核（A1 前置；N-62 统一基座）。

同一份 **agent 可见**的因子面板（bundle 里的 work/ 文件，不是参考面产物），在 f01 的 oracle 环境
（pandas 2.2.3 / numpy 1.26 / pyarrow 20）与统一基座（pandas 2.3.3 / numpy 2.x / pyarrow 25）里
各算一遍下面这些量，输出 JSON（浮点用 repr），两边逐键 diff 定位差异。
只用面板自己——不碰网关、不碰 reference/ ——所以可以进容器（--network none，只读挂载）。

    python crossver_probe.py work/factor_panel.parquet > out.json
"""
import hashlib
import io
import json
import sys

import numpy as np
import pandas as pd


def r(v) -> str:
    return repr(float(v))


def main(path: str) -> None:
    import pyarrow
    df = pd.read_parquet(path)
    out = {"versions": {"python": sys.version.split()[0], "pandas": pd.__version__,
                        "numpy": np.__version__, "pyarrow": pyarrow.__version__},
           "rows": int(len(df)), "columns": list(map(str, df.columns)),
           "dtypes": {str(c): str(t) for c, t in df.dtypes.items()}}
    # 1. parquet 往返 sha（pyarrow 版本差异最先在这里露头；不同不等于错，只是要知道）
    buf = io.BytesIO()
    df.to_parquet(buf, index=False)
    out["parquet_roundtrip_sha"] = hashlib.sha256(buf.getvalue()).hexdigest()
    val = "value" if "value" in df.columns else [c for c in df.columns if df[c].dtype.kind == "f"][0]
    piv = df.pivot(index="date", columns="code", values=val).sort_index()
    piv.columns = piv.columns.map(str)
    x = piv.sort_index(axis=1).astype("float64")
    out["panel_shape"] = list(x.shape)
    out["nan_count"] = int(x.isna().sum().sum())
    out["value_sum"] = r(np.nansum(x.to_numpy()))
    out["value_sum_float32"] = r(np.nansum(x.to_numpy(dtype=np.float32), dtype=np.float32))
    out["float32_cast_sha"] = hashlib.sha256(np.nan_to_num(x.to_numpy(dtype=np.float32)).tobytes()).hexdigest()
    # 2. 逐日截面 rank 自相关（d 与 d+5）：rank 平局处理 + corr 实现的跨版本一致性
    lag = x.shift(-5)
    s = pd.Series(dtype=float)
    for tie in ("average", "min", "first"):
        ics = []
        for d in x.index[:-5]:
            a, b = x.loc[d], lag.loc[d]
            m = a.notna() & b.notna()
            if int(m.sum()) < 5:
                continue
            ics.append(a[m].rank(method=tie).corr(b[m].rank(method=tie)))
        s = pd.Series(ics)
        out[f"rank_autocorr_{tie}"] = {"n": int(len(s)), "mean": r(s.mean()), "std": r(s.std(ddof=1)),
                                       "q025": r(s.quantile(0.025)), "q975": r(s.quantile(0.975))}
    # 3. 移动块自举（default_rng 流 + quantile 的跨版本稳定性）—— S4 summarize 同款
    rng = np.random.default_rng(0)
    arr = s.to_numpy()
    n, bl = len(arr), 20
    nb = int(np.ceil(n / bl))
    means = np.empty(1000)
    for b in range(1000):
        st = rng.integers(0, n - bl + 1, size=nb)
        means[b] = np.concatenate([arr[i:i + bl] for i in st])[:n].mean()
    out["bootstrap"] = {"q025": r(np.quantile(means, 0.025)), "q975": r(np.quantile(means, 0.975)),
                        "first5": [r(v) for v in means[:5]]}
    # 4. 常用面板算子
    out["pct_change_mean"] = r(x.pct_change(fill_method=None).stack().mean())
    out["rolling20_mean_sum"] = r(x.rolling(20).mean().stack().sum())
    out["groupby_code_std_sum"] = r(df.groupby("code")[val].std(ddof=1).sum())
    out["describe_sha"] = hashlib.sha256(x.describe().to_json().encode()).hexdigest()
    print(json.dumps(out, indent=1, sort_keys=True))


if __name__ == "__main__":
    main(sys.argv[1])
