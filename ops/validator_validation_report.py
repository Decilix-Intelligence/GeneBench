#!/usr/bin/env python3
"""「验证验证器」报告 v1（M6 产出 ②，卡 5.1 验收）：三件事各给证据，不给形容词。

① 干净产物零误报：`ops/reports/probe_run_oracle.json`（40 题 oracle 真跑的 O1 矩阵）—— 每题的 findings 必须为空；
② 注入违例必命中：`reference.artifact_samples.ILLEGAL`（红队样例，每条带期望 code 与严重级）逐条过校验器；
③ 三态判定正确：`ops/test_scorer_gate.py`（violation / unobservable / clean 逐族，unobservable ∩ gate_failed = ∅）的通过数；
④ **逐族破坏样本**：`ops/run_probe_mutations.py` —— 取 M6 每题**自己的 oracle 产物**只破坏一处，该族必响、其余不响；
⑤ **三控走完整评分器**：`ops/run_controls.py` —— oracle / null / filler 三桩从生产入口 `score_run` 走一遍。

④ 与 ② 不是重复：② 证「校验器在**手写样例**上会响」，④ 证「校验器在**我们真拿去评分的那些产物**上会响」——
中间隔着 payload 档位、声明集、日志切片、可交易性视图，每一样都可能让某条检查静默失效。

用法：python ops/validator_validation_report.py → ops/reports/validator_validation_v1.md
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from ops import report_io as _RIO   # noqa: E402

from reference import artifact_samples as AS                # noqa: E402
from reference.artifact_schema import PROBE_IDS, validate   # noqa: E402

OUT = _REPO / "ops" / "reports" / "validator_validation_v1.md"
#: 私有通道的两个默认目录。**默认值不许动** —— `ops/readiness_report.py` 无参调用 part4/part5。
REPORTS_DIR = _REPO / "ops" / "reports" / "m6"          # ④⑤ 的明细（mutations.json / controls.json）
O1_DIR = _REPO / "ops" / "reports"                      # ① 的 O1 矩阵（probe_run_oracle*.json）


def part1(o1_dir: "Path | None" = None) -> tuple[list[str], dict]:
    """`probe_run_oracle.json` 的行：`ok` = 跑了、rc=0、**有产物**、零 finding（run_oracles.Result.ok，2026-09-05 修过恒绿）；
    `findings` 非空 = 校验器命中；其余 = 没跑 / 没产物（校验器一条都没查，不算零误报）。"""
    # **读累积的那一份**：单次跑批的文件会被定点重跑整份覆盖（2026-09-06 实测：报告曾退化成 4 题）。
    d = Path(o1_dir or O1_DIR)
    cum = d / "probe_run_oracle.cumulative.json"
    p = cum if cum.is_file() else d / "probe_run_oracle.json"
    rows = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else []
    clean = [r for r in rows if r.get("ok") is True]
    dirty = [r for r in rows if r.get("findings")]
    absent = [r for r in rows if r.get("ok") is not True and not r.get("findings")]
    ages = sorted({str(r.get("at", ""))[:16] for r in rows if r.get("at")})
    lines = [f"- 数据源：`{p.name}`（{len(ages)} 次跑批的累积：{', '.join(ages) or '未记时刻'}）",
             f"- 题数：{len(rows)}；有产物且零 finding：{len(clean)}；有 finding：{len(dirty)}；"
             f"没跑 / 没产物（不算零误报）：{len(absent)}",
             f"- 零 finding 的题：{', '.join(r['task_id'] for r in clean)[:400]}",
             f"- 没跑 / 没产物：{', '.join(r['task_id'] + (('（' + r['note'][:40] + '）') if r.get('note') else '') for r in absent)[:600]}"]
    for r in dirty:
        lines.append(f"  - **{r['task_id']}** findings: {r['findings'][:3]}")
    return lines, {"n_tasks": len(rows), "n_clean": len(clean), "n_dirty": len(dirty), "n_absent": len(absent)}


def part2() -> tuple[list[str], dict]:
    hits, misses, by_probe = 0, [], Counter()
    for ill in AS.ILLEGAL:
        v = validate(ill.artifact, task=ill.task, gateway_log=ill.log, tradability=ill.trad, config_id=AS.CFG)
        codes = v.codes
        ok = ill.code in codes and any(f.severity == ill.severity for f in v.findings if f.code == ill.code)
        if ok:
            hits += 1
            for f in v.findings:
                if f.code == ill.code and f.probe:
                    by_probe[f.probe] += 1
        else:
            misses.append(f"{ill.name}: 期望 {ill.code}/{ill.severity}，实得 {sorted(codes)}")
    lines = [f"- 红队样例：{len(AS.ILLEGAL)} 条；命中期望 code+严重级：{hits}；未命中：{len(misses)}"]
    lines += [f"  - **未命中** {m}" for m in misses]
    covered = sorted(by_probe)
    lines.append(f"- 被样例命中过的探针族：{len(covered)}/{len(PROBE_IDS)} —— {', '.join(covered)}")
    lines.append(f"- 样例里**没有**任何 violation 命中的族：{', '.join(sorted(set(PROBE_IDS) - set(covered)))}")
    return lines, {"n_illegal": len(AS.ILLEGAL), "hits": hits, "misses": len(misses), "probes_covered": covered}


def _load(name: str, reports_dir: "Path | None" = None):
    p = Path(reports_dir or REPORTS_DIR) / name
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def part4(reports_dir: "Path | None" = None) -> tuple[list[str], dict]:
    rows = _load("mutations.json", reports_dir)
    if rows is None:
        return ["- **没跑** `ops/run_probe_mutations.py` —— 后半缺席"], {"ok": False, "n": 0, "hit": 0, "families": []}
    hit = [r for r in rows if r.get("ok")]
    unmade = [r for r in rows if not r.get("ok") and "造不出" in str(r.get("verdict"))]
    fail = [r for r in rows if not r.get("ok") and r not in unmade]
    fams = sorted({r["probe"] for r in hit})
    lines = [f"- 破坏样本 {len(rows)} 条：**该族响、其余不响** {len(hit)} 条；造不出 {len(unmade)} 条；失败 {len(fail)} 条",
             f"- 被破坏样本证过方向的族（{len(fams)}）：{', '.join(fams)}",
             f"- 没有发出点、因而造不出样本的族：{', '.join(sorted(set(PROBE_IDS) - set(fams)))}"
             "（在 `ops/test_probe_coverage.py::NO_EMITTER_YET` 具名登记）"]
    for r in unmade + fail:
        lines.append(f"  - **{r['task_id']} / {r['probe']}**：{r.get('verdict')}")
    return lines, {"ok": not fail, "n": len(rows), "hit": len(hit), "families": fams}


def part5(reports_dir: "Path | None" = None) -> tuple[list[str], dict]:
    rows = _load("controls.json", reports_dir)
    if rows is None:
        return ["- **没跑** `ops/run_controls.py` —— 三控缺席"], {"ok": False, "n_records": 0, "n_tasks": 0}
    by: dict = {}
    for r in rows:
        by.setdefault(r["control"], []).append(r)
    orc, nul = by.get("oracle", []), by.get("null", [])
    fil = [r for r in by.get("filler", []) if r["task_id"] == "s7-rob-02"]
    o_ok = bool(orc) and all(r["validity"] == "valid" and not r["findings"] for r in orc)
    n_ok = bool(nul) and all(r["sr_bucket"] != "scorable" for r in nul)
    f_ok = bool(fil) and all(any("silent_completion" in f for f in r["findings"])
                             and r["validity"] == "invalid" and r["effect"] is None for r in fil)
    lines = [f"- oracle 桩 {len(orc)} 题：每族零 finding {'✅' if o_ok else '❌'}"
             f"（效果分：{sum(1 for r in orc if r['effect'] == 100.0)} 题 = 100，"
             f"{sum(1 for r in orc if r['effect'] is None)} 题扣住 —— 扣住理由见 controls.md）",
             f"- null 桩 {len(nul)} 题：SR 记 0 {'✅' if n_ok else '❌'}",
             f"- filler 桩 on s7-rob-02：silent_completion 命中且 effect 为 null {'✅' if f_ok else '❌'}"]
    return lines, {"ok": o_ok and n_ok and f_ok, "n_records": len(rows),
                   "n_tasks": len({r["task_id"] for r in rows})}


def part3() -> tuple[list[str], dict]:
    r = subprocess.run([sys.executable, "-m", "pytest", "ops/test_scorer_gate.py", "ops/test_scorer_l3.py",
                        "ops/test_scorer_report.py", "-q"], cwd=str(_REPO), capture_output=True, text=True, timeout=600)
    tail = (r.stdout.strip().splitlines() or [""])[-1]
    return [f"- 评分器三态 / L3 / 报告器红测：`{tail}`（rc={r.returncode}）"], {"pytest_tail": tail, "rc": r.returncode}


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description="验证验证器报告 v1（五部分）")
    ap.add_argument("--channel", default="",
                    help="private / public。**只在 main 里设进环境**，不在 import 期改 —— "
                         "import 期改环境会把任何 import 本模块的进程整个翻到另一条通道")
    ap.add_argument("--reports-dir", default="",
                    help="④⑤ 明细目录（mutations.json / controls.json），默认 ops/reports/m6")
    ap.add_argument("--o1-dir", default="",
                    help="① 的 O1 矩阵目录（probe_run_oracle*.json），默认 ops/reports")
    ap.add_argument("--out", default="", help="报告落点，默认 ops/reports/validator_validation_v1.md")
    a = ap.parse_args(argv)
    if a.channel:
        os.environ["GENEBENCH_CHANNEL"] = a.channel
    reports_dir = Path(a.reports_dir) if a.reports_dir else REPORTS_DIR
    o1_dir = Path(a.o1_dir) if a.o1_dir else O1_DIR
    out = Path(a.out) if a.out else OUT
    l1, s1 = part1(o1_dir)
    l2, s2 = part2()
    l3, s3 = part3()
    l4, s4 = part4(reports_dir)
    l5, s5 = part5(reports_dir)
    # 零误报要**有干净产物**才成立 —— 全是「没产物」时 n_dirty 也是 0，那是恒绿（F7 / D-06）。
    verdict = (s1["n_clean"] > 0 and s1["n_dirty"] == 0 and s2["misses"] == 0 and s3["rc"] == 0
               and s4["ok"] and s5["ok"])
    body = ["# 验证验证器报告 v1（2026-09-05）", "",
            "> 卡 5.1 验收原文：每探针一组保真/破坏扰动单测 —— 对 oracle 产物注入已知违例必须命中、干净产物零误报。",
            "> 本报告给三件事的机器证据；「方向未证实」的族（f1 矩阵全零，N-110）**不因本报告转绿**。", "",
            f"> 通道 `{_channel()}`；O1 矩阵目录 `{o1_dir}`；④⑤ 明细目录 `{reports_dir}`。", "",
            "## ① 干净产物零误报（O1 矩阵）", *l1, "",
            "## ② 注入违例必命中（红队样例）", *l2, "",
            "## ③ 三态判定", *l3, "",
            "## ④ 逐族破坏样本（取该题自己的 oracle 产物，只破坏一处）", *l4,
            "", f"> 明细：`{reports_dir}/mutations.md`。", "",
            "## ⑤ 三控走完整评分器", *l5,
            "", f"> 明细：`{reports_dir}/controls.md`。", "",
            f"## 判定：{'通过' if verdict else '**未通过**'}",
            f"- 零误报：{'是' if (s1['n_clean'] > 0 and s1['n_dirty'] == 0) else '否'}"
            f"（有产物且零 finding {s1['n_clean']}，有 finding {s1['n_dirty']}，没跑/没产物 {s1['n_absent']}；"
            f"零 finding 的题数为 0 时不成立）",
            f"- 必命中：{'是' if s2['misses'] == 0 else '否'}（{s2['hits']}/{s2['n_illegal']}）",
            f"- 三态：{'是' if s3['rc'] == 0 else '否'}",
            f"- 逐族破坏样本：{'是' if s4['ok'] else '否'}（{s4['hit']}/{s4['n']}，覆盖 {len(s4.get('families', []))} 族）",
            f"- 三控：{'是' if s5['ok'] else '否'}",
            "",
            "边界（不是脚注装饰，是可证伪的限制）：",
            "- ②的样例覆盖的族只有上面列出的那些；没被任何样例命中的族，其「必命中」**没有证据**。",
            "- 依赖网关日志的四族（declared_reads / fetch_clock / lookahead / source_status）在数据面结算时读 f01 的 access_log 三重切片；"
            "在 f02 侧不可得 → unobservable（不是 clean）。",
            "- ①里「没产物」的题不算零误报（校验器一条都没查）。"]
    _RIO.secure_dir(out.parent)
    out.write_text("\n".join(body) + "\n", encoding="utf-8")
    out.chmod(0o600)
    print("\n".join(body))
    return 0 if verdict else 1


def _channel() -> str:
    """当前通道。**运行时读**，不在 import 期定死。"""
    import genebench_config as _cfg
    return _cfg.channel()


if __name__ == "__main__":
    raise SystemExit(main())
