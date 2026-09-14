# -*- coding: utf-8 -*-
"""镜像内无头自检：**不调模型**，只打生产网关的几十次 GET。

它证明的是整条接线通不通：题面两种写法都解析得出来、网关取数与 NoData 留痕在位、
上游那五个替换点都还在、四天两只票的模拟能跑完、产物过 emit 的构造。
模型那一头用一个**确定性桩**顶替 —— 桩返回的是格式合法的 JSON，
所以 `secretary` 的格式校验、撮合、记录、翻译全都是真的在跑。

用法（在 f02）：
    GENEBENCH_TASK_DIR=<一份 task 目录> python3 /opt/stockagent/smoke.py
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))


class StubSidecar:
    """确定性桩。按调用序号轮流给 buy / sell / no，贷款一律拒，预测一律 no。

    **它不是模型**：判据里有一条盯着 `run.py` 默认走的是 `seams.Sidecar`，
    这条路只有 smoke 显式传进去才走得到。
    """

    def __init__(self) -> None:
        self.calls = 0
        self.stopped_reason = None

    def chat(self, messages, temperature=1.0):
        self.calls += 1
        last = messages[-1]["content"] if messages else ""
        if "loan" in last and "loan_type" in last:
            return 'I will not borrow today. {"loan": "no"}'
        if "buy_A" in last:
            return ('Tomorrow I stay put. '
                    '{"buy_A":"no","buy_B":"no","sell_A":"no","sell_B":"no","loan":"no"}')
        if "post" in last.lower() or "forum" in last.lower() and "action_type" not in last:
            return "Nothing notable today."
        n = self.calls % 3
        if n == 0:
            return 'Holding. {"action_type": "no"}'
        if n == 1:
            return 'Buying a little. {"action_type": "buy", "stock": "A", "amount": 1, "price": 1.0}'
        return 'Trimming. {"action_type": "sell", "stock": "B", "amount": 1, "price": 1.0}'


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def ck(name, ok, detail=""):
        checks.append((name, bool(ok), str(detail)))

    from glue import instruction as I
    from glue import seams

    strict = "as_of=2026-07-31\nwindow=2026-01-05 到 2026-07-31\nuniverse=csi300\n"
    prose = ("可用端点：/bars /adj /calendar /limits /universe /tradability\n"
             "本次任务的 as_of 是 2026-07-31\n"
             "计算窗口（window）是 2026-01-05 到 2026-07-31\n"
             "标的范围（universe）是 csi300\n"
             "- 标的范围是截至 2026-07-31 的沪深300成分股（字段 universe_ref，接口值 csi300@2026-07-31）\n")
    ck("parse.strict", (I.as_of(strict), I.window(strict), I.universe(strict))
       == ("2026-07-31", ("2026-01-05", "2026-07-31"), "csi300"))
    ck("parse.prose", (I.as_of(prose), I.window(prose), I.universe(prose))
       == ("2026-07-31", ("2026-01-05", "2026-07-31"), "csi300"),
       "散文臂：as_of 后面是「是」不是「=」，universe 不许被 /universe 偷走")
    ck("parse.declarations", I.declarations(prose, ["universe_ref"])
       == {"universe_ref": "csi300@2026-07-31"})

    seams.prepare_cwd()
    seams.install_gemini_trap()
    up = pathlib.Path(os.environ.get("GENEBENCH_SA_UPSTREAM",
                                     str(pathlib.Path(__file__).resolve().parent / "upstream")))
    sys.path.insert(0, str(up))
    missing = []
    import importlib
    for mod, attr, _why in seams.REPLACEMENTS:
        m = importlib.import_module(mod)
        obj = m
        for part in attr.split("."):
            if not hasattr(obj, part):
                missing.append(f"{mod}.{attr}")
                break
            obj = getattr(obj, part)
    ck("upstream.replacement_points", not missing, f"缺: {missing}")

    try:
        import google.generativeai as genai
        genai.configure(api_key="x")
        ck("gemini.trap", False, "陷阱没生效 —— 它应该抛")
    except RuntimeError:
        ck("gemini.trap", True)

    import run as entry
    stub = StubSidecar()
    summary = entry.run(sidecar=stub)
    ck("pipeline.artifact", pathlib.Path(summary["artifact"]).exists(), summary["artifact"])
    ck("pipeline.cells", summary["cells"] > 0, summary["cells"])
    ck("pipeline.decisions", summary["decisions"] > 0, summary["decisions"])
    ck("pipeline.nodata_traced", summary["fundamentals_nodata_traced"],
       "网关上没留下 /nodata/fundamentals 那一行")
    art = json.loads(pathlib.Path(summary["artifact"]).read_text(encoding="utf-8"))
    cov = art["payload"]["coverage"]
    ck("artifact.coverage_matches",
       cov["n_valued"] + cov["n_null"] + cov["n_flat"] == len(art["payload"]["signals"]), cov)
    ck("artifact.no_unresolved_left",
       "unresolved" not in art["declarations"].values(), art["declarations"])
    ck("llm.stub_only", stub.calls > 0, stub.calls)

    for name, ok, detail in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")
    print(json.dumps(summary, ensure_ascii=False))
    bad = [n for n, ok, _ in checks if not ok]
    print("RESULT " + ("SMOKE-OK" if not bad else f"SMOKE-FAIL {bad}"))
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
