#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AlphaAgent 作为 GeneBench 被测方（P2）的入口。

顺序是**有讲究的**，不能重排：

  ① `glue.bootstrap.apply()` —— 摆环境 + 把 `tushare` 顶替成经网关的垫片。
     必须在任何 `import alphaagent` **之前**：`alphaagent.data.__init__` 顶层就
     `import tushare`，而 agent 循环那条 import 链一定会经过它（见 bootstrap 的 docstring）。
  ② 读题面 `/task/INSTRUCTION.md`（唯一题面）→ `set_as_of` → 经垫片取数。
  ③ 把取到的数落成 AlphaAgent 的 DSL 面板。
  ④ 交给 AlphaAgent 自己的 `run_trajectory` 循环（模型经边车）写 DSL 并求值。
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

ENV_SNAPSHOT = bootstrap.apply()          # ← 必须在 import alphaagent 之前

import genebench_client as gb             # noqa: E402
from genebench_client import emit         # noqa: E402
from glue import agent, instruction, panel as panel_mod  # noqa: E402

TASK = pathlib.Path(os.environ.get("GENEBENCH_TASK_DIR", "/task"))
VALUES_PATH = TASK / "values.parquet"

#: 轮数与单次输出上限。真正的护栏是注入器给边车的 `--max-calls`（每 run 100 次）——
#: 这里只是不让一次运行把预算烧在同一道题上。一轮 = 一次模型调用。
MAX_TURNS = int(os.environ.get("GB_ALPHAAGENT_MAX_TURNS", "10"))
MAX_TOKENS = int(os.environ.get("GB_ALPHAAGENT_MAX_TOKENS", "4096"))


def _llm_client():
    """经**边车**的模型客户端。base URL 只从环境变量取，绝不写死主机名 ——
    写死就绕过了边车，那条路上没有 usage、没有预算闸、什么都看不见。"""
    from openai import OpenAI

    base = os.environ.get("OPENAI_BASE_URL") or os.environ.get("OPENAI_API_BASE") \
        or os.environ.get("LLM_BASE_URL")
    key = os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY")
    if not base:
        raise SystemExit("环境里没有 OPENAI_BASE_URL / OPENAI_API_BASE / LLM_BASE_URL。"
                         "**不猜默认值**：猜一个就等于绕过边车。")
    return OpenAI(base_url=base, api_key=key or "placeholder")


def _values_frame(values, panel):
    """AlphaAgent 的求值结果（与面板同索引的 Series）→ 题面契约的长表。

    契约（题面逐字给出，也在 `genetask/file_contract.py::FILE_SPECS["S3"]`）：
    列序 `date, code, value`，按 `date, code` 升序，不写行索引，`value` 是 float64。
    **一条都不许省** —— 少一条，两个同样正确的实现字节就不同，而字节摘要是被计分的量。

    `value` 在 AlphaAgent 里是 float32（它的加速内核统一输出 float32，
    见 `alphaagent/dsl/core/accel.py`），这里按契约转成 float64。
    **只做类型转换，不做任何数值修改** —— 精度损失是系统自己的选择，写在 README §3。
    """
    import numpy as np
    import pandas as pd

    if isinstance(values, pd.DataFrame):
        values = values.iloc[:, 0]
    s = pd.Series(values)
    s.index = panel.index
    idx = s.index.to_frame(index=False)
    out = pd.DataFrame({
        "date": pd.to_datetime(idx["datetime"]).dt.strftime("%Y-%m-%d"),
        "code": idx["instrument"].astype(str),
        "value": pd.to_numeric(np.asarray(s.to_numpy()), errors="coerce").astype("float64"),
    })
    return out.sort_values(["date", "code"]).reset_index(drop=True)


def _empty_frame():
    import pandas as pd
    return pd.DataFrame({"date": pd.Series(dtype="object"),
                         "code": pd.Series(dtype="object"),
                         "value": pd.Series(dtype="float64")})


def _write_values(frame):
    frame.to_parquet(VALUES_PATH, index=False)
    return hashlib.sha256(VALUES_PATH.read_bytes()).hexdigest()


def _stats_from_file(frame, panel, lookback):
    """从**落盘的那一份**重算自报值。全部是清点，没有一处是「应该是多少」。"""
    import numpy as np
    import pandas as pd

    v = frame["value"].to_numpy(dtype="float64")
    finite = np.isfinite(v)
    # 覆盖率的分母是**面板的格子数**（题面窗口 × universe），不是产出的行数 ——
    # 只写出一半的行而每行都有限，覆盖率不该是 1。
    dts = panel.index.get_level_values("datetime")
    n_dates = int(dts.nunique())
    n_syms = int(panel.index.get_level_values("instrument").nunique())
    cells = n_dates * n_syms
    coverage = (float(finite.sum()) / cells) if cells else 0.0

    warm = 0
    if isinstance(lookback, int) and lookback > 1 and len(frame):
        early = {pd.Timestamp(d).strftime("%Y-%m-%d") for d in sorted(pd.unique(dts))[: lookback - 1]}
        m = frame["date"].isin(early).to_numpy()
        warm = int(finite[m].sum())

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
    print("[alphaagent] env:", json.dumps(ENV_SNAPSHOT, ensure_ascii=False), flush=True)

    spec = instruction.parse((TASK / "INSTRUCTION.md").read_text(encoding="utf-8"))
    print("[alphaagent] spec:", instruction.summary(spec), flush=True)

    gb.set_as_of(spec.as_of)                       # 启动时一次；取不到就抛，不猜
    cli = gb.client()

    fields = spec.declarations.get("required_fields")
    if not isinstance(fields, list) or not fields:
        raise SystemExit("题面没有给 required_fields（或形态不是列表）。"
                         "**不猜**：S3 的 /bars 不显式传 fields 是畸形不是缺省。")
    codes = cli.members(spec.universe, spec.as_of)
    bars = cli.bars(codes, spec.window_start, spec.window_end, fields=fields)
    pan = panel_mod.build_panel(bars, fields)
    info = panel_mod.panel_summary(pan)
    pan.attrs["gb_panel_info"] = info
    print("[alphaagent] 面板:", json.dumps(info, ensure_ascii=False), flush=True)

    chosen = None
    try:
        chosen, tools, _msgs = agent.mine(
            panel=pan, spec=spec, client=_llm_client(),
            model=os.environ.get("GENEBENCH_MODEL", "deepseek-chat"),
            log_dir=bootstrap.LOG_DIR, max_turns=MAX_TURNS, max_tokens=MAX_TOKENS)
        print(f"[alphaagent] agent 结束：求值 {len(tools.evaluated)} 次，"
              f"交付 {'有' if tools.submitted else '无'}", flush=True)
    except Exception as e:  # noqa: BLE001
        # agent 那条路炸了也要交产物：如实写覆盖率 0，把原因打进日志。
        print(f"!! agent 循环失败：{type(e).__name__}: {e}", flush=True)

    import pandas as pd  # noqa: F401
    if chosen is None:
        print("!! 没有算出任何因子值 —— 如实写一份覆盖率 0 的产物，不编数。", flush=True)
        frame = _empty_frame()
        expression_used = None
    else:
        print("[alphaagent] 采用（来源 %s）：" % chosen["source"], flush=True)
        print(chosen["multi_line_expr"], flush=True)
        print("[alphaagent] 系统生成的代码：", chosen["generated_code"], flush=True)
        frame = _values_frame(chosen["values"], pan)
        expression_used = chosen["multi_line_expr"]

    sha = _write_values(frame)
    st = _stats_from_file(frame, pan, spec.declarations.get("lookback"))
    st["values_ref"]["sha256"] = sha
    print("[alphaagent] stats:", json.dumps(st, ensure_ascii=False), flush=True)
    if expression_used is not None:
        print("[alphaagent] 注意：payload.expression 写的是题面原文（题面明令「照抄原文」），"
              "系统实际执行的 DSL 打印在上面，也在 %s 的轨迹里。" % bootstrap.LOG_DIR, flush=True)

    art = emit.emit_s3(
        factor_id=spec.factor_id,
        # 题面明写「expression 照抄原文，算子不得自行替换」「payload.expression 照抄原文」。
        # 所以这里放原文，**不放** AlphaAgent 的 DSL —— 后者在日志与轨迹里可查。
        expression=spec.expression,
        values_ref={"coverage": st["values_ref"]["coverage"], "sha256": sha},
        nonfinite=st["nonfinite"],
        warmup=st["warmup"],
        # 空列表与「没写」不是一件事：前者是「我没做近似」。**这一层**没有替换任何算子；
        # 模型选的 DSL 算子与原文算子是否逐一对应，我们无从核验 —— 这一点写在
        # README 的「已知限制」里，不在这里用一个猜出来的值遮掉。
        approximated_operators=[],
        degeneracy=st["degeneracy"],
        declarations=spec.declarations,
        as_of=spec.as_of,
    )
    out = art.write(TASK / "artifact.json")
    print(f"[alphaagent] wrote {out}；values.parquet rows={len(frame)} sha256={sha[:16]}…",
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
