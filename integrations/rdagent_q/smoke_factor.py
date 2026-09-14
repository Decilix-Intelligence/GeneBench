# -*- coding: utf-8 -*-
"""**只给 f01 走查用**的一份 `factor.py`（降级路径的输入）。

为什么要有它：f01 上没有边车、没有真 key，模型那一步跑不了。走查要验的是**链路**
（题面 → 网关取数 → qlib 面板 → RD-Agent 执行 → result.h5 → values.parquet → artifact
→ 协议 validator），把「模型写代码」那一步换成一份给定的代码，其余全部真跑。
这与既有 `runner/c42/adapters/rdagent_q/adapter.py` 的降级路径是同一条路（N-105）。

**它算的因子是走查专用的假题面里那个**（`(open / delay(open, 5) - 1)`），
故意**不是**任何一道被计分的真题。理由是这份文件会随构建上下文被 scp 到执行面 ——
把一道真题的解法放到执行面上，即使不进镜像，也是不该有的东西。
"""
import pandas as pd


def calculate_factor():
    df = pd.read_hdf("daily_pv.h5", key="data")
    s = df["$open"].unstack("instrument")
    out = (s / s.shift(5) - 1.0).stack(future_stack=True).sort_index()
    out.name = "demo_open_ret5"
    out.to_frame().to_hdf("result.h5", key="data", mode="w")


if __name__ == "__main__":
    calculate_factor()
