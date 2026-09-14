#!/usr/bin/env python3
"""v1.0 冒烟集的三个对照 agent 验收表：**N1**(null) / **O1**(oracle) / **F1**(default_filler)。

三个各证明一件不同的事（2026-09-03 裁定）：
* **N1**：什么都不产出的 agent 必须被判别出来 —— 证明题目不是「随便交点什么都能过」；
* **O1**：oracle 的产物零 finding，且一次已知突变必须变红 —— 证明校验不是空的；
  探针题上 oracle 的「满分」= `correct_handling=true` + `effect withheld_honest_halt` + SR=1，
  **不是效果分满分**（探针题的 oracle 本来就不该有效果分）；
* **F1**：把欠定字段填上最合理的默认值并把数照常算出来 —— 必须触发 `silent_completion` 且效果分记 invalid。
  N1 走不到静默补全那条路（什么都不产出 → 畸形），O1 走的是正确路径；只有 F1 端到端地证明
  **schema → 校验器 → 闸门 → scorer 三态**这条链对静默补全真的会响。

跑法：`/data/shared/genebench/env/bin/python ops/acceptance_v10_controls.py`
产物：`ops/reports/acceptance_v1.0_controls.{json,md}`
"""
from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from genetask import packager as P            # noqa: E402
from genetask import schema as S              # noqa: E402
from reference import artifact_samples as smp  # noqa: E402
from reference import artifact_schema as sch   # noqa: E402

CAPS = {"n33_bars_open_amount_vwap": True, "s8_state_endpoint": True, "anchor_ladder_54": False}
PARAMS = Path(__file__).resolve().parents[1] / "genetask" / "params" / "v1.0-smoke40.yaml"
OUT_DIR = Path(__file__).resolve().parents[1] / "ops" / "reports"
OUT_STEM = "acceptance_v1.0_controls"   # with_suffix 会把 .0_controls 当扩展名，所以自己拼

#: v1.0 出集范围（裁定 2026-09-03）：32 道规定题 + 唯一有实测证据的探针题。
IN_V10 = lambda t: t["kind"] != "underdetermined_probe" or t["task_id"] == "s7-rob-02"


def oracle_like(task: dict) -> dict:
    """「像 oracle」的产物：合法样例骨架 + 本题声明；欠定字段标 unresolved、依赖它的量诚实终止。"""
    base = deepcopy(smp.LEGAL[task["stage"]].artifact)
    base["task_id"] = task["task_id"]
    decl = deepcopy(task["declared"])
    for f in task["underdetermined"]:
        decl[f] = sch.UNRESOLVED
    base["declarations"] = decl
    if task["stage"] == "S7":
        base["payload"]["rebalance_frequency"] = decl["rebalance_frequency"]
    for f in sch.honest_halt_fields(task["stage"], decl, task["underdetermined"]):
        cur, *rest = f.split(".")
        if rest:
            if isinstance(base["payload"].get(cur), dict):
                base["payload"][cur][rest[0]] = None
        else:
            base["payload"][cur] = None
    return base


def main() -> int:
    rows, out = P.load_params(PARAMS), []
    for r in rows:
        b = P.build_task(r, capabilities=CAPS)
        t = b.task
        n1 = P.check_null(t) or ["ok"]
        o1 = P.check_oracle(t, oracle_like(t)) or ["ok"]
        f1 = (P.check_filler(t) or ["ok"]) if t["underdetermined"] else ["n/a（规定题无欠定字段）"]
        ok = all(x[0] in ("ok",) or x[0].startswith("n/a") for x in (n1, o1, f1))
        out.append({"task_id": t["task_id"], "stage": t["stage"], "family": t["family"], "kind": t["kind"],
                    "in_v10": IN_V10(t), "build_ok": b.ok, "e6_flags": len(b.review),
                    "N1": n1[0], "O1": o1[0], "F1": f1[0], "pass": ok and b.ok and not b.review})
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"{OUT_STEM}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    v10 = [x for x in out if x["in_v10"]]
    bad = [x for x in out if not x["pass"]]
    md = ["# v1.0 冒烟集验收：三个对照 agent（N1 / O1 / F1）", "",
          f"- 起草 **{len(out)}** 题；**v1.0 出集 {len(v10)} 题**（32 规定 + s7-rob-02，裁定 2026-09-03）",
          f"- 三控全过：**{sum(1 for x in out if x['pass'])}/{len(out)}**；构建红 0、E6 标记 0 为前提", "",
          "| task | 阶段 | 族 | 类型 | 出集 | N1 | O1 | F1 |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for x in out:
        md.append(f"| `{x['task_id']}` | {x['stage']} | {x['family']} | {x['kind']} | "
                  f"{'✅' if x['in_v10'] else '—'} | {x['N1'][:28]} | {x['O1'][:28]} | {x['F1'][:28]} |")
    md += ["", "**读法**：N1 = null_agent 必须被判别出来；O1 = oracle 零 finding + 已知突变必须变红；",
           "F1 = 静默补全必须触发 `silent_completion` 且效果分记 invalid（探针题专属，规定题 n/a）。",
           "", f"未过：{[x['task_id'] for x in bad] or '无'}"]
    (OUT_DIR / f"{OUT_STEM}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md[:6]))
    print(f"\n写出 {OUT_DIR / (OUT_STEM + '.json')} 与 {OUT_DIR / (OUT_STEM + '.md')}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
