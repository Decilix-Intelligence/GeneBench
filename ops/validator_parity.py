#!/usr/bin/env python3
"""N-129：**协议 validator 与评分器 L1 子集的一致性**，语料 = M6 的全部真 artifact。

为什么要用真 artifact 而不是手写样例：`ops/test_protocol_validator.py` 已经在**四条合成突变**上
测过子集关系，而 2026-09-06 的实测是：10 个带 `validator.log` 的真 run 里，validator 调用 18 次、
报出违例 **0** 次，同批评分器判 `malformed` 的有 **4** 个。合成样例过、真产物不过 ——
差别就在「真 agent 会写出什么」这件事上，手写样例猜不到。

**判据两个方向**（`validate_artifact.SCOPE` / `SCORER_SCOPE` 定义作用域）：

* 作用域**内**：scorer 报 ⟹ validator 也必须报（**反向**判据 —— 这条不成立，修复回路就在撒谎）；
* 全域：validator 报 ⟹ scorer 也必须报（validator 不得比 scorer 严）。

比对**只喂 artifact**（`gateway_log=None`、`tradability=None`）—— 要证据的那几族（前视、declared_reads、
越权计数…）本来就不在工件侧可见，把它们算进差集是在要求 validator 做它做不到的事。

用法：python ops/validator_parity.py [--out ops/reports/validator_parity.md]
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

import yaml

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "ops" / "protocol" / "geneprotocol_v1"))

import genebench_config as cfg                         # noqa: E402
import validate_artifact as V                          # noqa: E402
from genetask import packager as P                     # noqa: E402
from genetask import protocol_rules as PR              # noqa: E402
from ops import report_io as RIO                       # noqa: E402
from reference import artifact_schema as sch           # noqa: E402

#: **从 `cfg` 现算**（2026-09-13 卡 P1，N-770 同族）。发布方那台上值一字未动。
ANSWER_ROOT = cfg.GENEBENCH_ROOT / "reference" / "tasks" / "v1.0-smoke"
RUNS_IN = cfg.GENEBENCH_ROOT / "runs_in"
OUT = _REPO / "ops" / "reports" / "validator_parity.md"


def corpus() -> list[dict]:
    """真 artifact（两批 run）+ 三控的三桩。每条带 `task_id` 与来源标签。"""
    got: list[dict] = []
    for b in ("m6", "m6b", "a1"):
        d = RUNS_IN / b
        if not d.is_dir():
            continue
        for rd in sorted(d.iterdir()):
            f = rd / "work" / "artifact.json"
            inj = rd / "inject.json"
            if not (f.is_file() and inj.is_file()):
                continue
            try:
                art = json.loads(f.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue                    # 不是 JSON 的产物由 run_status 分类，不进一致性语料
            got.append({"src": f"{b}/{rd.name}", "kind": "agent",
                        "task_id": json.loads(inj.read_text(encoding="utf-8"))["task_id"],
                        "artifact": art})
    for td in sorted(ANSWER_ROOT.iterdir()):
        if not (td / "task.yaml").is_file():
            continue
        task = yaml.safe_load((td / "task.yaml").read_text(encoding="utf-8"))
        for name, kind in (("solution/artifact.json", "oracle"),
                           ("solution/artifact.null.json", "null")):
            p = td / name
            if p.is_file():
                got.append({"src": f"{td.name}/{name}", "kind": kind, "task_id": td.name,
                            "artifact": json.loads(p.read_text(encoding="utf-8"))})
        try:
            got.append({"src": f"{td.name}/filler", "kind": "filler", "task_id": td.name,
                        "artifact": P.null_artifact(task, "default_fill")})
        except Exception:                              # noqa: BLE001
            pass
    return got


def _rules_for(task_id: str, tmp: Path) -> tuple[dict, dict]:
    td = ANSWER_ROOT / task_id
    task = yaml.safe_load((td / "task.yaml").read_text(encoding="utf-8"))
    spec = json.loads((td / "taskspec.json").read_text(encoding="utf-8"))
    out = tmp / task_id
    PR.write_rules(task, out)
    rules = {k: json.loads((out / v).read_text(encoding="utf-8")) for k, v in V.RULES.items()}
    return rules, {"spec": spec, "task": task}


def compare(row: dict, rules: dict, ctx: dict) -> dict:
    art = row["artifact"]
    mine = V.validate(art, rules)
    theirs = sch.validate(art, task=ctx["spec"], gateway_log=None, tradability=None,
                          payload_profile=ctx["task"].get("payload_profile"))
    scorer_mal = {f.code for f in theirs.findings if f.severity == "malformed"}
    mine_codes = {v["code"] for v in mine}
    # 作用域内 scorer 报了、validator 没报 → **反向缺口**（必修）
    gap = sorted((scorer_mal & sch_scope()) - ({"__any__"} if mine_codes else set()))
    if mine_codes:
        gap = []                                        # validator 报了东西就不算「什么都没说」
    # validator 报了、scorer 一条 malformed 都没有 → validator 比 scorer 严（不许）
    stricter = sorted(mine_codes) if (mine_codes and not scorer_mal) else []
    # 作用域外、但**只看 artifact 就能判**的 scorer code → 扩作用域的候选
    cand = sorted(scorer_mal - sch_scope())
    return {"src": row["src"], "kind": row["kind"], "task_id": row["task_id"],
            "validator": sorted(mine_codes), "scorer_malformed": sorted(scorer_mal),
            "reverse_gap": gap, "validator_stricter": stricter, "scope_candidates": cand}


def sch_scope() -> set:
    return set(V.SCORER_SCOPE)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)
    rows = corpus()
    res = []
    with tempfile.TemporaryDirectory(prefix="gb-parity-") as tmp:
        cache: dict = {}
        for r in rows:
            if r["task_id"] not in cache:
                try:
                    cache[r["task_id"]] = _rules_for(r["task_id"], Path(tmp))
                except Exception as e:                  # noqa: BLE001
                    cache[r["task_id"]] = None
                    print(f"  规则造不出来：{r['task_id']}（{type(e).__name__}: {e}）")
            if cache[r["task_id"]] is None:
                continue
            rules, ctx = cache[r["task_id"]]
            res.append(compare(r, rules, ctx))
    gaps = [r for r in res if r["reverse_gap"]]
    strict = [r for r in res if r["validator_stricter"]]
    cands = Counter(c for r in res for c in r["scope_candidates"])
    silent = [r for r in res if r["scorer_malformed"] and not r["validator"]]
    body = ["# 协议 validator × 评分器 L1 子集一致性（N-129，语料 = M6 全部真 artifact）", "",
            f"语料 **{len(res)}** 份：真 agent 产物 {sum(1 for r in res if r['kind'] == 'agent')}、"
            f"oracle {sum(1 for r in res if r['kind'] == 'oracle')}、"
            f"null {sum(1 for r in res if r['kind'] == 'null')}、"
            f"filler {sum(1 for r in res if r['kind'] == 'filler')}。",
            "",
            "> 比对只喂 artifact（`gateway_log=None`、`tradability=None`）—— 要证据的那几族本来就不在工件侧可见。",
            "",
            "## 判定", "",
            f"- **validator 比 scorer 严**（不许）：{len(strict)} 份",
            f"- **作用域内反向缺口**（scorer 报、validator 沉默）：{len(gaps)} 份",
            f"- **scorer 报了而 validator 完全沉默**（不限作用域）：{len(silent)} 份 —— 修复回路在这些产物上没启动",
            "", "## 作用域外、但只看 artifact 就能判的 scorer code（扩作用域的候选）", "",
            "| code | 出现份数 |", "| --- | ---: |"]
    for c, n in cands.most_common():
        body.append(f"| `{c}` | {n} |")
    if silent:
        body += ["", "## 逐份：scorer 报了、validator 沉默", "",
                 "| 来源 | 桩 | scorer 的 malformed |", "| --- | --- | --- |"]
        for r in silent[:40]:
            body.append(f"| `{r['src']}` | {r['kind']} | {', '.join('`' + c + '`' for c in r['scorer_malformed'])} |")
    RIO.write_text(Path(a.out), "\n".join(body) + "\n")
    RIO.write_json(Path(a.out).with_suffix(".json"), res)
    print("\n".join(body[:24]))
    print(f"→ {a.out}")
    return 0 if not strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
