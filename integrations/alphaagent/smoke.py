#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""无 LLM 的通路自检：面板 → AlphaAgent DSL 求值 → values.parquet → artifact.json。

**它证明什么**：镜像里 AlphaAgent 装上了、它的 DSL 解析器与算子库能在网关来的
面板上算出因子值、产物写得出来且过协议 validator。
**它不证明什么**：模型那一段（`run_trajectory`）——那要真 key，只在真跑里发生。
所以这里的 DSL 是**手写死的一条**，不是模型写的；它的唯一用途是把 LLM 之外的
每一环都点亮一次，出了事能立刻分清是「链路坏了」还是「模型没写对」。

用法（在 f02 的容器里，很轻，几十次 GET，**不需要 gateway_lock**）：
  docker run --rm -e GENEBENCH_GATEWAY=http://192.168.1.48:18080 \
      gb-alphaagent-u:r1 python3 /opt/gb_alphaagent/smoke.py
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from glue import bootstrap  # noqa: E402

bootstrap.apply()

import genebench_client as gb             # noqa: E402
from genebench_client import emit         # noqa: E402
from glue import agent, instruction, panel as panel_mod  # noqa: E402

TASK = pathlib.Path(os.environ.get("GB_SMOKE_TASK_DIR", "/tmp/gb_alphaagent/smoke_task"))
AS_OF = os.environ.get("GB_SMOKE_AS_OF", "2026-07-31")
W_START = os.environ.get("GB_SMOKE_START", "2026-06-01")
W_END = os.environ.get("GB_SMOKE_END", "2026-06-30")
N_CODES = int(os.environ.get("GB_SMOKE_CODES", "20"))

#: 手写的一条 DSL：题面 s3-cor-01 那条 `(-1 * correlation(open, volume, 10))`
#: 在 AlphaAgent DSL 里的逐算子对应写法。窗口 10 与 lookback 一致。
HAND_DSL = "MULTIPLY(-1, TS_CORR($open, $volume, 10))"

#: 合成题面。**不抄真题**（真题里的校验串是每份 bundle 各自的，不该进仓库），
#: 只复刻它的槽位写法 —— 解析器要认的正是这些槽位。
INSTRUCTION = f"""按下列声明完成任务。
任务（S3）：按下面的源方言原文实现因子。
因子：smoke.wq006_like
源方言原文：`(-1 * correlation(open, volume, 10))`
除题面列出的输入材料外，数据只能经网关获取：{os.environ.get('GENEBENCH_GATEWAY', 'http://gateway:18080')}
可用端点：/bars /adj /calendar /limits /universe /tradability
as_of={AS_OF}
window={W_START} 到 {W_END}
universe=csi300
本次任务的口径（逐项）：
- required_fields=[open, volume]（这个因子只需要开盘价与成交量，接口值 [open, volume]）
- lookback=10（回看窗口 10 个交易日，接口值 10）
- eval_frequency=daily（按日频评估，接口值 daily）
- operator_semantics={{correlation: pearson_rolling_window}}（接口值 {{correlation: pearson_rolling_window}}）
- param_order=[series_a, series_b, window]（接口值 [series_a, series_b, window]）
- nonfinite_policy=propagate（接口值 propagate）
- warmup_policy=null_until_full（接口值 null_until_full）
校验串：SMOKE-NOT-A-REAL-CANARY
"""


def main() -> int:
    # 独立身份：不与任何真跑的切片键冲突（施工契约 B6）。
    os.environ.setdefault("GENEBENCH_TASK_ID", "smoke-alphaagent")
    os.environ.setdefault("GENEBENCH_CONFIG_ID", "cfg-alphaagent-smoke")
    os.environ.setdefault("GENEBENCH_ARM", "smoke")
    os.environ.setdefault("GENEBENCH_RUN_ID", "smoke-alphaagent-1")

    TASK.mkdir(parents=True, exist_ok=True)
    (TASK / "INSTRUCTION.md").write_text(INSTRUCTION, encoding="utf-8")

    spec = instruction.parse(INSTRUCTION)
    print("[smoke] spec:", instruction.summary(spec), flush=True)

    gb.set_as_of(spec.as_of)
    cli = gb.client()
    fields = spec.declarations["required_fields"]
    codes = cli.members(spec.universe, spec.as_of)[:N_CODES]
    bars = cli.bars(codes, spec.window_start, spec.window_end, fields=fields)
    pan = panel_mod.build_panel(bars, fields)
    info = panel_mod.panel_summary(pan)
    pan.attrs["gb_panel_info"] = info
    print("[smoke] 面板:", json.dumps(info, ensure_ascii=False), flush=True)

    # 走的是真跑里那一个 ImplementTools，只是没有模型来调它。
    tools = agent.ImplementTools(pan, spec.declarations.get("lookback"))
    res = tools.dispatch("submit_expression",
                         {"multi_line_expr": HAND_DSL, "factor_name": "smoke",
                          "comment": "手写的逐算子对应写法"})
    print("[smoke] dispatch:", json.dumps(res, ensure_ascii=False, default=str)[:2000], flush=True)
    if not res.get("ok"):
        print("!! DSL 求值没过 —— 这条通路是坏的。", flush=True)
        return 2

    # prompt 也点一次：算子清单是从 alphaagent 的注册表现算的，装不上就会在这里炸。
    prompt = agent.build_prompt(spec, info)
    print(f"[smoke] system prompt {len(prompt)} 字符，算子清单条数 "
          f"{prompt.count(chr(10) + '- `')}", flush=True)

    row = tools.evaluated[-1]
    import numpy as np
    import pandas as pd
    s = row["values"]
    if isinstance(s, pd.DataFrame):
        s = s.iloc[:, 0]
    s = pd.Series(s)
    s.index = pan.index
    idx = s.index.to_frame(index=False)
    frame = pd.DataFrame({
        "date": pd.to_datetime(idx["datetime"]).dt.strftime("%Y-%m-%d"),
        "code": idx["instrument"].astype(str),
        "value": pd.to_numeric(np.asarray(s.to_numpy()), errors="coerce").astype("float64"),
    }).sort_values(["date", "code"]).reset_index(drop=True)
    out_parquet = TASK / "values.parquet"
    frame.to_parquet(out_parquet, index=False)
    import hashlib
    sha = hashlib.sha256(out_parquet.read_bytes()).hexdigest()

    st = row["stats"]
    art = emit.emit_s3(
        factor_id=spec.factor_id, expression=spec.expression,
        values_ref={"coverage": st["coverage"], "sha256": sha},
        nonfinite={"inf_count": st["inf_count"], "nan_count": st["nan_count"],
                   "replaced_count": 0},
        warmup={"nonnull_before_warmup": st["nonnull_before_warmup"]},
        approximated_operators=[],
        degeneracy={"is_constant": st["is_constant"], "alert": st["is_constant"]},
        declarations=spec.declarations, as_of=spec.as_of)
    p = art.write(TASK / "artifact.json")
    print(f"[smoke] wrote {p}；rows={len(frame)} sha256={sha[:16]}… stats="
          f"{json.dumps(st, ensure_ascii=False)}", flush=True)
    print("[smoke] SMOKE-OK", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
