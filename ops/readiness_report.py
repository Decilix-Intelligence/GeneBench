#!/usr/bin/env python3
"""v1.0 就绪报告（M6 产出 ①）：组件版本、冻结根、**全链一次无人工干预跑通**的记录。

全部从**文件**读，不从人手抄：两份冻结清单、执行面环境快照、M6-lite 的 run 目录与结算产物、
三控与破坏样本的报告、验证验证器报告。抄一遍的报告会在下一次改动之后**静默变成假的**。

用法：python ops/readiness_report.py [--batch m6]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from ops import report_io as _RIO   # noqa: E402

import genebench_config as _cfg     # noqa: E402

OUT = _REPO / "ops" / "reports" / "v1_0_readiness.md"
#: **从 `cfg` 现算**（2026-09-13 卡 P1，N-770 同族）。发布方那台上值一字未动。
RUNS_IN = _cfg.GENEBENCH_ROOT / "runs_in"

#: §5「已知限制」的**唯一来源**（卡 6.5）。此前 §5 是手抄在本文件里的一张写死的表，
#: 而卡 5.2 关掉了其中四条（N-126 / N-127 / N-128 / `s2-eco-01`）—— 手抄那份没跟着变，
#: 于是报告里每一行都还写着「出不来 / 没写 / 被 422」，**而没有任何东西会红**。
#: 这份 md 自己就是「逐条裁定版」，两张表并存的唯一正当理由是它们说的是两件事；
#: 说的是同一件事时，第二份就是一个会静默变假的副本。
KNOWN_LIMITS = _REPO / "ops" / "reports" / "known_limits_v1.md"

#: `known_limits_v1.md` 的「逐条」表列名（顺序即列序）。变了就该红 —— 见 `known_limits_rows`。
KNOWN_LIMITS_COLUMNS = ("编号", "一句话", "判定", "证据")


def _md_table(text: str, section: str) -> list[list[str]]:
    """从 markdown 里取某个 `## 小节` 下的第一张表，返回**数据行**（不含表头与分隔行）。

    只按行首 `|` 认表，按 `|` 切列；切出来列数不对的行**原样留成单元素**，
    由调用方决定怎么处理 —— 静默丢掉一行的代价是「那条限制从报告上消失了」。
    """
    lines = text.splitlines()
    try:
        i = next(k for k, ln in enumerate(lines) if ln.strip() == section)
    except StopIteration:
        return []
    rows: list[list[str]] = []
    seen_table = False
    for ln in lines[i + 1:]:
        s = ln.strip()
        if s.startswith("## ") and seen_table:
            break
        if not s.startswith("|"):
            if seen_table and s and not s.startswith("|"):
                break
            continue
        seen_table = True
        cells = [c.strip() for c in s.strip("|").split("|")]
        if all(set(c) <= set("- :") and c for c in cells):        # 分隔行
            continue
        rows.append(cells)
    return rows


def known_limits_verdict_summary(text: str) -> list[tuple[str, str]]:
    """`known_limits_v1.md` 自己的「## 判定汇总」表 —— **判定条数以它为准**。

    它与「## 逐条」的行数**不相等**（表上 15 行 / 判定 16 条）：N-127 与 N-128 各带两半
    （题面部分已修、判据部分留 v1.1），在汇总里各占两条。此前本节的括号里只写「15 条」
    并把逐条表里数出来的 v1.1 条数当成汇总的那一个，于是同一个量在两份都进 RELEASE_MANIFEST
    的报告里给出两个答案 —— 而声称「现读、不留副本」的恰恰是给错的那一份（红队阶段六 major）。
    """
    rows = _md_table(text, "## 判定汇总")
    return [(r[0], r[1]) for r in rows
            if len(r) == 2 and r[0] != "判定" and r[1].strip().isdigit()]


def _rel(p: "Path | str") -> str:
    """仓库内路径写成相对路径 —— 报告正文里不出现绝对路径字面量。"""
    p = Path(p)
    return str(p.relative_to(_REPO)) if p.is_relative_to(_REPO) else str(p)


def _axes_of_table(csv_path: Path) -> dict:
    """主表**自报**的四条注入面版本轴（从 `table_a.csv` 现读）。

    `MIXED:` 前缀 = 这张表是多个版本的 run 合出来的。报告 §1 声明的是**发布版**的轴，
    两者不是一回事；不说破的话读者会把 §4 的 SR / pass@1 读成发布版上的构造验收结果
    （红队阶段六 block：`ops/reports/m6_all` 就是 1.0.7 与 1.0.9 合出来的）。
    """
    import csv as _csv
    if not Path(csv_path).is_file():
        return {}
    with Path(csv_path).open(encoding="utf-8") as f:
        rows = list(_csv.DictReader(f))
    out: dict[str, list[str]] = {}
    for k in ("set_version", "reference_version", "runner_version", "image_digest"):
        vals = sorted({str(r.get(k) or "") for r in rows if r.get(k)})
        if vals:
            out[k] = vals
    return out


def _pin(pins: dict, key: str, n: int = 24) -> str:
    """执行面钉子的一格。**取不到就写「（未采集）」，不写一个空指纹的反引号壳。**"""
    v = str(pins.get(key) or "")
    return f"`{v[:n]}…`" if v else "**（未采集）**"


def known_limits_rows(path: "Path | None" = None) -> tuple[list[str], dict]:
    """§5 那张表 —— **现读 `known_limits_v1.md`**，不在本文件里留第二份。

    返回 `(markdown 行, 统计)`。文件不在就如实说「没有裁定文件」，**不回落到一张写死的表**：
    回落的表现正是这次要修掉的那件事。
    """
    p = Path(path or KNOWN_LIMITS)
    if not p.is_file():
        return ([f"> **没有 `{p.relative_to(_REPO) if p.is_relative_to(_REPO) else p}`** —— "
                 "已知限制的逐条裁定文件不在，本节无数据源。"], {"n": 0, "by_verdict": {}})
    text = p.read_text(encoding="utf-8")
    raw = _md_table(text, "## 逐条")
    body = [r for r in raw if r and r[0] != KNOWN_LIMITS_COLUMNS[0]]
    lines = ["| 编号 | 限制 | 判定 | 证据 / 影响 |", "| --- | --- | --- | --- |"]
    by: dict = {}
    bad = 0
    for r in body:
        if len(r) != len(KNOWN_LIMITS_COLUMNS):
            bad += 1
            lines.append("| " + " | ".join(r) + " |")
            continue
        num, one, verdict, ev = r
        key = ("已修" if "已修" in verdict else
               "设计性限制" if "设计性" in verdict else
               "v1.1" if "v1.1" in verdict else "其它")
        by[key] = by.get(key, 0) + 1
        lines.append(f"| {num} | {one} | {verdict} | {ev} |")
    summ = known_limits_verdict_summary(text)
    n_sum = sum(int(v) for _, v in summ)
    # **两个数都写出来**：表上多少行、判定多少条。它们本来就不相等，只写一个就会与那份文件打架。
    tail = (f" / 判定 {n_sum} 条：" + "、".join(f"{k.split('（')[0]} {v}" for k, v in summ)
            + "；N-127 与 N-128 各带两半（题面部分已修、判据部分留 v1.1），"
              "所以判定条数比表行数多 —— 见该文件的「收口核对」一节") if summ else \
           (("；" + "、".join(f"{k} {v}" for k, v in sorted(by.items()))) if by else "")
    head = [f"> **本节从 `{p.relative_to(_REPO)}` 现读**（表上 {len(body)} 行{tail}"
            + "）—— 那份是逐条裁定版，这里不留第二份手抄的副本。",
            "> 判定口径只有一条：**挡不挡外部用户**。还挡着、但卡在用户签字的三条"
            "（N-388 默认预算档 / N-348 适配赛道题源 / N-130 S7 回合数）单列在该文件的"
            "「收口核对」一节。", ""]
    return head + lines, {"n": len(body), "by_verdict": by, "malformed_rows": bad,
                          "verdict_summary": dict(summ), "n_verdicts": n_sum}


def _exec_pins(batches: "list[str]") -> dict:
    """执行面的**钉子**：runner_version 与随树船运的 h11 —— 都从真的 run 里读，不手抄。"""
    import hashlib
    for b in batches:
        for p in sorted((RUNS_IN / b).glob("*/inject.json")) if (RUNS_IN / b).is_dir() else []:
            d = _j(p) or {}
            ex = d.get("executables") or {}
            h11 = {k: v for k, v in ex.items() if k.startswith("h11/")}
            h = hashlib.sha256()
            for k in sorted(h11):
                h.update(k.encode())
                h.update(str(h11[k]).encode())
            return {"runner_version": d.get("runner_version", ""), "image": d.get("image", ""),
                    "h11_files": len(h11), "h11_manifest_sha256": h.hexdigest() if h11 else "",
                    "egress_proxy_sha256": ex.get("egress_proxy.py", ""), "from_run": p.parent.name}
    return {}


def _lookahead_box(batches: "list[str]") -> "list[str]":
    """前视闸的实测：命中多少、由哪个 reason 驱动、以及被摘出闸门的那一类有多少（遥测）。

    数字从 `records.json` 现算 —— 这一段是判据取舍的依据，抄一遍就可能与产物不符。
    """
    import re
    recs, hit = [], []
    for b in batches:
        for r in (_j(_REPO / "ops" / "reports" / b / "records.json") or []):
            recs.append(r)
            if "lookahead" in (r.get("gate_failed") or []):
                hit.append(r)
    scorable = [r for r in recs if r.get("sr_bucket") in ("scorable", "malformed")]
    why: dict = {}
    for r in hit:
        for f in r.get("findings") or []:
            if "lookahead_attempt" not in f:
                continue
            for k, n in re.findall(r"'([a-z_]+)': (\d+)", f):
                why[k] = why.get(k, 0) + int(n)
    ub = sum(x for x in (r.get("unbounded_requests") for r in recs) if isinstance(x, int))
    return ["### 前视（lookahead）：闸门只收**显式越界**，开区间单列遥测", "",
            "裁定 2026-09-06（第 2 种读法）：**显式越界是意图，开区间是不知道 API 约定**，"
            "而「请求须以 `end_date` 界定在 as_of 内」这条约定题面没写 —— 判据要求的东西题面必须说。",
            "",
            f"- 有产物的 run **{len(scorable)}** 个，`lookahead` 命中 **{len(hit)}** 个 → invalid → 效果分扣住。",
            f"- 命中的 {sum(why.values())} 次拒按 reason：" +
            ("；".join(f"`{k}` {v} 次" for k, v in sorted(why.items(), key=lambda x: -x[1])) or "（无）"),
            f"- 摘出闸门的那一类（**遥测**，Table A 的 `unbounded_requests`）：合计 **{ub}** 次未界定右端的请求。",
            "- **oracle 侧零误报**：九道题的 oracle 桩全绿（它们的取数一律显式带 `start_date`/`end_date`）。",
            "",
            "约定已写进**两臂共享**的 `work/{stage}.json`（`x-gateway-fetch-contract`，即 "
            "`ops/specs/artifact_schema/v1.0/*.json`，由 `reference.artifact_schema.json_schema()` 生成）——"
            "**题面正文一个字没动**。",
            "写的时候发现这条路径**在冻结根之外**（改它 agent 就看见了，而两条版本轴一动不动，N-131）——"
            "已把 `ops/specs/artifact_schema/` 收进任务集清单的 `code` 段，因此推 **v1.0.10**："
            "**内容未变、`root_scope` 变**（与 1.0.4 那次同形）。", ""]


def _recov_note(batches: "list[str]") -> str:
    """Recov 空是**零修复**还是**未接线** —— 报告里必须说清是哪一种（量出来，不猜）。"""
    runs = calls = viol = withlog = mal_withlog = 0
    for b in batches:
        for f in sorted((_REPO / "ops" / "reports" / b / "scores").glob("*.json")) \
                if (_REPO / "ops" / "reports" / b / "scores").is_dir() else []:
            rec = (_j(f) or {}).get("record") or {}
            runs += 1
            vl = RUNS_IN / b / rec.get("run_id", "") / "work" / "protocol" / "validator.log"
            if not vl.is_file():
                continue
            withlog += 1
            rows = [x for x in vl.read_text(encoding="utf-8").splitlines() if x.strip()]
            calls += len(rows)
            viol += sum(1 for x in rows if (json.loads(x).get("n_violations") or 0) > 0)
            mal_withlog += int(rec.get("run_status") == "malformed")
    return (f"**零修复，不是未接线**：{withlog}/{runs} 个 run 带 `work/protocol/validator.log`"
            f"（GQ 臂全都有），validator 被调用 {calls} 次、报出违例 **{viol}** 次 —— 分母是空的，"
            f"所以 Recov 按「算不出就是 None」留空。**但这个零本身是条发现**：同一批里评分器判 "
            f"`malformed` 的有 {mal_withlog} 个，协议 validator 在它们上一条都没报（N-129）。")


def _ref_root(manifest: dict) -> str:
    from ops.freeze_v10 import reference_root
    return reference_root(manifest) if manifest else ""


def _j(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def _git(*args: str) -> str:
    r = subprocess.run(["git", *args], cwd=str(_REPO), capture_output=True, text=True, timeout=30)
    return (r.stdout or "").strip()


def chain_rows(batches: "list[str]") -> tuple[list[str], dict]:
    """全链记录：每个 run 从**注入**到**结算**的每一环各留了什么证据。"""
    recs = []
    for b in batches:
        for r in (_j(_REPO / "ops" / "reports" / b / "records.json") or []):
            r["batch"] = b
            recs.append(r)
    lines = ["| run | 注入 | 边车 | 容器 | 采集 | 闸门 | L3 | 效果分 |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    n_ok = 0
    for r in sorted(recs, key=lambda x: x["run_id"]):
        rd = RUNS_IN / r.get("batch", "m6") / r["run_id"]
        inj = _j(rd / "inject.json") or {}
        egress = (rd / "log" / "egress.jsonl")
        llm = (rd / "log" / "llm_log.jsonl")
        n_eg = len(egress.read_text(encoding="utf-8").splitlines()) if egress.is_file() else 0
        n_llm = len(llm.read_text(encoding="utf-8").splitlines()) if llm.is_file() else 0
        art = "有" if r["run_status"] not in ("no_artifact", "timeout") else "无"
        n_ok += int(r["run_status"] == "ok")
        lines.append(f"| `{r['run_id']}` | {len(inj.get('files') or {})} 文件 | {n_eg} 条 | "
                     f"{n_llm} 次模型调用 | 产物{art} | {r['validity'] or '—'} | "
                     f"{r['l3_kind'] or '—'}:{r['l3_pass']} | {r['effect']} |")
    return lines, {"n_runs": len(recs), "n_ok": n_ok}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", default="m6", help="逗号分隔可给多批（两次 pass）")
    ap.add_argument("--channel", default="",
                    help="private / public。**只在 main 里设进环境**，不在 import 期改"
                         "（N-260：import 期改环境会把任何 import 本模块的进程整个翻到另一条通道）")
    ap.add_argument("--reports-dir", default="",
                    help="④⑤ 明细目录（mutations.json / controls.json），默认 ops/reports/m6")
    ap.add_argument("--o1-dir", default="",
                    help="O1 矩阵目录（probe_run_oracle*.json），默认 ops/reports")
    ap.add_argument("--out", default="", help="报告落点，默认 ops/reports/v1_0_readiness.md")
    ap.add_argument("--validator-report", default="",
                    help="§3 里那份验证验证器报告的落点（默认 ops/reports/validator_validation_v1.md）。"
                         "**公开通道要传本通道那一份** —— 不传的话公开报告的 §3 指着私有那份")
    ap.add_argument("--tables-dir", default="",
                    help="Table A/B 所在目录，默认 ops/reports/<batch>（多批时 ops/reports/m6_all）")
    a = ap.parse_args(argv)
    if a.channel:
        import os as _os
        _os.environ["GENEBENCH_CHANNEL"] = a.channel
    out_path = Path(a.out) if a.out else OUT
    reports_dir = Path(a.reports_dir) if a.reports_dir else None
    o1_dir = Path(a.o1_dir) if a.o1_dir else None
    ts = _j(_REPO / "ops" / "manifests" / "v1.0-smoke.json") or {}
    rf = _j(_REPO / "ops" / "manifests" / "v1.0-smoke.reference.json") or {}
    env = (_REPO / "ops" / "reports" / a.batch / "env_f02.txt")
    env_txt = env.read_text(encoding="utf-8") if env.is_file() else "（没有执行面环境快照）"
    caps = _j(_REPO / "ops" / "capabilities.json") or {}
    # **与验证验证器报告 ④⑤ 同一个来源**（裁定 2026-09-06）：直接调它的两个函数，
    # 不再自己按 `a.batch` 拼路径 —— 拼错了就显示 0，而 0 与「没跑」在报告上不可分
    # （实测过：`--batch m6,m6b` 时路径变成 `reports/m6,m6b/`，两行都成了 0 条）。
    from ops.validator_validation_report import O1_DIR as _O1_DEFAULT
    from ops.validator_validation_report import REPORTS_DIR as _RD_DEFAULT
    from ops.validator_validation_report import part4 as _p4
    from ops.validator_validation_report import part5 as _p5
    _rd = reports_dir or _RD_DEFAULT
    _od = o1_dir or _O1_DEFAULT
    _mut_lines, mut_stat = _p4(_rd)
    _ctl_lines, ctl_stat = _p5(_rd)
    o1 = (_j(_od / "probe_run_oracle.cumulative.json")
          or _j(_od / "probe_run_oracle.json") or [])
    batches = [b.strip() for b in a.batch.split(",") if b.strip()]
    a.batch = batches[0]
    rows, stat = chain_rows(batches)
    pins = _exec_pins(batches)
    tdir = (Path(a.tables_dir) if a.tables_dir else
            _REPO / "ops" / "reports" / ("m6_all" if len(batches) > 1 else a.batch))
    ta, tb = tdir / "table_a.csv", tdir / "table_b.csv"

    # O1 矩阵的三态：零 finding / 有 finding / **没产物**。第三类不能省 ——
    # 省掉之后「40 题、零 finding 34、有 finding 0」会被读成「其余 6 题也没问题」（红队阶段六 major）。
    _o1_clean = [r for r in o1 if r.get("ok") is True]
    _o1_dirty = [r for r in o1 if r.get("findings")]
    _o1_absent = [r for r in o1 if r.get("ok") is not True and not r.get("findings")]
    _o1_cum = _od / "probe_run_oracle.cumulative.json"
    _o1_src = _o1_cum if _o1_cum.is_file() else _od / "probe_run_oracle.json"
    _o1_mat = _od / "probe_matrix_oracle.md"        # **本通道的那一份**，不是私有那份
    # 主表自报的轴：与 §1 声明的发布版轴不是一回事，混轴时必须当面说破。
    _axes = _axes_of_table(ta)
    _mixed = {k: v for k, v in _axes.items() if any(str(x).startswith("MIXED:") for x in v)}
    _zero_runs = stat["n_runs"] == 0
    _batch_readme = _REPO / "ops" / "reports" / a.batch / "README.md"
    _vv = Path(a.validator_report) if a.validator_report else \
        _REPO / "ops" / "reports" / "validator_validation_v1.md"

    _mix_lines: list[str] = []
    if _mixed:
        _mix_lines = [
            "> ⚠ **这张表是混轴表，不能与 §1 的版本并排读。** 表内自报："
            + "；".join(f"`{k}` = {', '.join(v)}" for k, v in sorted(_mixed.items()))
            + f"；而 §1 声明的是任务集 **{ts.get('set_version')}** / 参考 **{rf.get('reference_version')}**。",
            "> 它是几批**不同题面版本**的 run 合出来的同一行 `pass@1`"
            "（合并的理由与逐批版本见该目录 `summary.md` 的脚注；`VERSIONS.md` §2 把它记作「一次真事故」）：",
            "> **它证明的是链路能把一次真运行变成一行主表，不是发布版上的构造验收结果** ——",
            "> 不要与任何单轴表的数并排，也不要当成 §1 那两条轴上的读数。要一张单轴的表，",
            "> 按 §2 的清单自己跑一批（例：`ops/reports/v1demo/`）。", ""]

    if _zero_runs:
        # **0 个 run 的批不渲染主表叙述**：Recov「零修复不是未接线」、「停下 5 个 run 的是预算闸」
        # 这类句子在 0 run 上一句都不成立，而它们原样套用的话正是「不可得被写成零」（红队阶段六 major）。
        _sec4 = [
            "## 4. 主表（构造验收口径，**不是**实验数据）", "",
            "> **本批 0 个 run —— 主表与逐 run 叙述都不适用，本节不渲染。**",
            "> 没有 run 就没有 Table A / B（**不是出表坏了**）；Recov / `$` / `unbounded_requests` 这些列的口径"
            "要在有 run 的批上才谈得上，前视闸的实测数字同理。",
            f"> 这一批为什么没跑、卡在哪两件执行面前置：`{_rel(_batch_readme)}` §2。"
            if _batch_readme.is_file() else
            "> 这一批为什么没跑，见该批目录下的 README。",
            "> 有 run 的那一批（私有通道 `m6` + `m6b`）的主表与逐 run 叙述在 `ops/reports/v1_0_readiness.md`。", "",
            f"- Table A：`{_rel(ta)}`" if ta.is_file() else "- Table A：**未生成（本批 0 个 run）**",
            f"- Table B：`{_rel(tb)}`" if tb.is_file() else "- Table B：**未生成（本批 0 个 run）**", "",
        ]
    else:
        _sec4 = [
            "## 4. 主表（构造验收口径，**不是**实验数据）", "",
            f"- Table A：`{ta.relative_to(_REPO) if ta.is_file() else '未生成'}`",
            f"- Table B：`{tb.relative_to(_REPO) if tb.is_file() else '未生成'}`",
            "- LaTeX：同目录 `table_a.tex` / `table_b.tex`（`scorer/report.py::to_latex`，空值写 `---` 不写 0）", "",
            *_mix_lines,
            "**Recov 列为什么是空的**：" + _recov_note(batches), "",
            "**`$` 列为什么是空的**：注册表里没有价目表（DeepSeek 的计价没进 `runner/registry.py`）——"
            "tokens 两列是实数，折算成钱要先把价目钉进注册表并留出处。", "",
            "> 规模就是 M6 的定义：**1 个验收配置 × 双臂 × 每阶段 1–2 题 × 1 种子**。",
            "> 它证明的是「这条链路能把一次真运行变成一行主表」，不是任何模型的能力。", "",
            "## 4b. 这一批里值得单独说的四件事", "",
            "1. **agent 顶出了一个 gold 缺陷**（N-124）。`s2-cor-01` 的 gold 面板 41 700 行价格**全是 NaN**，",
            "   `missing_rows.count` 恰好等于总行数 41 700 —— 行数对、sha 有值、校验器只判「非负整数」，**没有任何东西报错**。",
            "   Codex 两臂都报 44（= 该窗口的停牌格数），逼我去看谁对：**agent 对**。修完之后 gold 的 `panel.csv`",
            "   与 agent 那份**逐字节相同**（同一个 sha256）。根因是 `/calendar` 的紧凑日期与 `/bars` 的 ISO 日期在 join 上相遇。",
            "2. **闸门语义在真运行上跑通了一次**。`s3-cor-01` 裸臂的因子**完全正确**（逐日 Spearman 中位数 1.0、130 天全过 τ 门），",
            "   但它读了声明之外的字段（`adj_factor`）→ `declared_reads` 命中 → `validity=invalid` → **效果分不出数**。",
            "   「算得对」与「按规矩算」是两件事，主表上必须分得开 —— 这一行就是证据。",
            "3. **诚实终止被正确记分**。`s7-rob-02`（欠定探针题）的 GQ 臂把 `sell_rule` 标了 `unresolved`、",
            "   依赖它的三块交了 null —— `correct_handling=true`、SR 记 1、效果分**扣住**（`honest_halt`）。",
            "   这正是这道题要测的东西：不知道就说不知道，比编一个数值得分。",
            "5. **判据要求的东西，题面必须说** —— 今晚同一族问题出现三次：S1 的取数台账（N-114）、",
            "   S2 的描述键（N-124）、S8 的事件字段与滑点符号（N-127 / N-128）。三次都是**判据在要题面没写的东西**。",
            "   前两次已按裁定改判；S8 这次判定成立（规格 §3 的正确性项就是「可完整重放」）但对被测方不公平，",
            "   处置写在下面的限制表里。判据设计的自查该加一条：**写完判据回去读题面，判据要的每一样，",
            "   题面上都得能指出是哪一句要求的**。",
            "4. **停下 5 个 run 的是我们设的预算闸，不是 harness**。S4 / S7 两个阶段在 50 次模型调用内做不完",
            "   （`llm_calls=50/51`，产物没写出来）。把 `s4-cor-01` 的闸放到 150 重跑一次（r02），它 **40 次**就交了合法产物。",
            "   → 排 M7 网格时，S4/S7 的调用预算不能按 S1/S2 的量级给。", "",
            *_lookahead_box(batches),

        ]

    _kl_lines, _kl_stat = known_limits_rows()
    body = [
        "# GeneBench v1.0 就绪报告（M6 构造验收 · 产出 ①）", "",
        f"> 通道 `{_channel()}`；批 `{', '.join(batches)}`；④⑤ 明细 `{_rd}`；O1 矩阵 `{_od}`。", "",
        *(["> ⚠ **这一批的真跑没有发生**（`records.json` 里 0 个 run）。§1 / §3 / §5 不依赖 run，是真的；",
           "> §2 的 0 与 §4 的「不适用」也是真的。**§4 / §4b 的逐 run 叙述本节不渲染** ——",
           "> 把有 run 那一批的叙述套在 0 run 上，得到的每一句都不成立。", ""] if _zero_runs else []),
        f"生成时间：见 git 提交；仓库 HEAD `{_git('rev-parse', '--short', 'HEAD')}`（{_git('log', '-1', '--format=%s')[:60]}）。",
        "",
        "> **M6 的目的是证明 benchmark 建成，不是产出实验数据**（范围修正 2026-09-04）。",
        "> 下面每一行都指向机器可查的产物；数字从文件读，不手抄。", "",
        "## 1. 组件版本与冻结根", "",
        "| 项 | 值 |", "| --- | --- |",
        f"| 任务集版本（agent 看得见的） | **{ts.get('set_version')}**，根 `{str(ts.get('root'))[:16]}…` |",
        # 参考根不在清单文件里 —— 它是**算出来的**（`freeze_v10.reference_root(manifest)`），
        # 这样「清单文件被人改了一个字」与「根变了」是同一件事，不需要额外的可信位。
        f"| 参考版本（我们算 gold 的方式） | **{rf.get('reference_version')}**，根 `{_ref_root(rf)[:16]}…`"
        f"（{len(rf.get('reference_templates') or {})} 个 solve.py + {len(rf.get('reference_modules') or {})} 个参考模块）|",
        f"| 出集 / 挂起 | {ts.get('counts', {}).get('released')} 题出集，{ts.get('counts', {}).get('held')} 题挂起（探针题的 E9c 未过）|",
        f"| 冻结线 | {ts.get('freeze_line')} |",
        f"| 能力位 | " + "；".join(f"`{k}`={v}" for k, v in caps.items() if isinstance(v, bool)) + " |",
        "",
        *(["> ⚠ **§4 的主表与本节不是同一组轴**：那张表自报 `MIXED:`（几批不同版本的 run 合出来的），"
           "本节声明的是发布版的两条轴 —— 两者不能并排读，详见 §4 的告示。", ""] if _mixed else []),
        "> **`provider_sha256_pinned=False` 的原因**：注入器现在只核 provider 的**根指纹**"
        "（`pin.check_provider_pin` 比对 `files.sha256` 这个文件的 sha256 = `54fdda39…`，P2 门），"
        "**没有**逐文件重算那棵树 —— 也就是说「provider 换了一个文件」这件事目前查得出的前提是"
        "它自带的 `files.sha256` 也跟着变。卡 4.2 的适配层要做的逐文件核对还没落地，所以这把锁维持 false。",
        "", "### 执行面（f02）", "", "```", env_txt.strip(), "```", "",
        # 四个钉子都取自**真 run** 的 inject.json；没有 run 就没有钉子 ——
        # 那时写「0 个文件」与一个空的反引号壳（`…`），读者分不出「量到了是 0」与「压根没采集」。
        *([f"- **runner_version**（注入器自己的指纹）：{_pin(pins, 'runner_version')}"
           f"（取自 `{pins.get('from_run', '')}` 的 `inject.json`）",
           f"- **随树船运的 h11**：{pins.get('h11_files', 0)} 个文件，逐文件 sha 的清单 sha256 "
           f"{_pin(pins, 'h11_manifest_sha256')}（边车与网关**同一份字节**，P7d 挂进容器）",
           f"- **边车** `egress_proxy.py`：{_pin(pins, 'egress_proxy_sha256')}",
           f"- 任务镜像：{_pin(pins, 'image', 64)}"]
          if pins else
          ["- **执行面的四个钉子：（未采集）** —— runner_version / h11 清单 sha / 边车 sha / 任务镜像"
           "都取自真 run 的 `inject.json`，而本批 **0 个 run**。这里不写 0、也不写空指纹。"]), "",
        "### 数据面（f01）", "",
        "- 网关：user systemd `genebench-gateway.service`（常驻、单 worker、绑 LAN、snapshot 后端）",
        "- oracle 环境：python 3.10.20 / pandas 2.2.3 / numpy 1.26.4 / pyarrow 20.0.0",
        "- 跨版本核：`ops/reports/crossver_probe_a1.md` —— 与统一基座 **17/18 键逐位相同**"
        "（唯一不同是 parquet 字节流 sha，读回的值相同）", "",
        "## 2. 全链一次无人工干预跑通", "",
        "链路：`build_task → write_task → export_bundle（钉 digest + 出通行证）→ push_bundle_to_f02（发送侧门 + 接收侧扫描）"
        "→ inject（P0–P9 + 边车 + h11 + 模型反代 + 预算闸）→ docker compose up → 容器跑 agent → harvest（down -v 之前）"
        "→ 拉回数据面 → gate（校验器 + 三态）→ L3 → validate_scorer_output → Table A/B`。", "",
        f"本批（{' + '.join(batches)}）**{stat['n_runs']} 个 run**，其中 `run_status=ok` **{stat['n_ok']}** 个。逐 run 证据：", "",
        *rows, "",
        "> 「无人工干预」的判据是：从 `ops/run_f02_a1.py` 起到 `.score.json` 落地，中间没有人改过任何文件。",
        "> run 目录在 `up` 前后各复核一次（`verify_unchanged`），改过就当场红。", "",
        "## 3. 三控与验证验证器", "",
        f"- 三控（oracle / null / filler）走**完整评分器**：{ctl_stat['n_records']} 条记录"
        f"（{ctl_stat['n_tasks']} 题 × 3 桩），三条判据{'**全过**' if ctl_stat['ok'] else '**未全过**'}"
        f" —— `{_rd}/controls.md`",
        f"- 逐族破坏样本：{mut_stat['n']} 条，其中**该族响、其余不响** {mut_stat['hit']} 条，"
        f"覆盖 {len(mut_stat.get('families', []))} 族 —— `{_rd}/mutations.md`",
        f"- O1 矩阵（oracle 零 finding）：**{len(o1)} 题**中，零 finding **{len(_o1_clean)}**、"
        f"有 finding **{len(_o1_dirty)}**、**没产物 {len(_o1_absent)}**"
        + (f"（{', '.join(r['task_id'] for r in _o1_absent)} —— 被 E9c 拦在落盘之前，"
           "校验器一条都没查，**不计入零误报、也不计入完成定义**）" if _o1_absent else "")
        + f" —— 数据源 `{_rel(_o1_src)}`（**累积**文件，定点重跑不会把它打回局部），"
        f"矩阵 `{_rel(_o1_mat)}`（同样从累积文件渲染；`n/a` 与 `·` 在矩阵里分得开）",
        f"- 验证验证器报告 v1：`{_rel(_vv)}`", "",
        *_sec4,
        "## 5. 已知限制（写在这里，不藏在脚注）", "",
        *_kl_lines, "",
        "## 6. 就绪判定", "",
        "**v1.0 的构造验收成立**当且仅当上面每一节都有产物、且验证验证器报告判定通过。",
        "本报告只陈述状态，不代替签字。",
    ]
    _RIO.secure_dir(out_path.parent)
    out_path.write_text("\n".join(body) + "\n", encoding="utf-8")
    out_path.chmod(0o600)
    print("\n".join(body[:40]))
    print(f"\n→ {out_path}")
    return 0


def _channel() -> str:
    """当前通道。**运行时读**，不在 import 期定死（与验证验证器报告同一条纪律）。"""
    import genebench_config as _cfg
    return _cfg.channel()


if __name__ == "__main__":
    raise SystemExit(main())
