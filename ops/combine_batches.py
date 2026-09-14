#!/usr/bin/env python3
"""把几批 run 的结算记录合成一张表（M6 的两次 pass = 一次构造验收）。

**只合并记录，不重算判据** —— 每条记录是它那一批当时按当时的版本判出来的，
合并表里逐行留着 `set_version` / `reference_version` 的话就能看出哪几行不同源。
（这几批的**任务集**版本之间 instruction 指纹相同，两次 pass 因此在**题面**上可比；判据的差异写在表下。表下那段脚注的版本号**从记录现算**，不手抄 ——手抄过一次就写错了：把 m6 的参考轴 `r1.0.8` 当成了任务集轴，红队阶段六 major。）

用法：python ops/combine_batches.py m6 m6b --out ops/reports/m6_all
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from ops import report_io as RIO                     # noqa: E402
from scorer import report as R                       # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("batches", nargs="+")
    ap.add_argument("--out", default=str(_REPO / "ops" / "reports" / "m6_all"))
    ap.add_argument("--caption", default="Table A — GeneBench v1.0 构造验收（M6-lite 两次 pass 合并；**不是实验数据**）")
    a = ap.parse_args(argv)
    out = RIO.secure_dir(Path(a.out))
    recs, src = [], {}
    for b in a.batches:
        p = _REPO / "ops" / "reports" / b / "records.json"
        if not p.is_file():
            print(f"跳过 {b}：没有 records.json")
            continue
        rows = json.loads(p.read_text(encoding="utf-8"))
        for r in rows:
            r["batch"] = b
        recs += rows
        src[b] = len(rows)
    if not recs:
        raise SystemExit("一条记录都没有")
    ta, tb = R.table_a(recs), R.table_b(recs)
    RIO.write_json(out / "records.json", recs)
    #: ⑩ 的**主表**（固定十九列）。它是**发布表**；`table_a` 是内部诊断表（带 `effect` 那一列，
    #: 而 ⑪ 明写 effect 不进任何发布表）。签字包收的是主表 —— 红队 V2.rt finding 6：
    #: 归档路径上一直没有主表，于是「四轴在表脚注 / 清单 / 签字包三处一致」的第三处对不上。
    main = R.main_table(recs)
    R.write_csv(main, out / "table_main.csv", (*R.TABLE_A_INDEX_COLUMNS, *R.MAIN_TABLE_COLUMNS))
    (out / "table_main.tex").write_text(R.to_latex(
        main, (*R.TABLE_A_INDEX_COLUMNS, *R.MAIN_TABLE_COLUMNS),
        caption=a.caption.replace("Table A", "主表（固定十九列）"), label="tab:main-m6-all"),
        encoding="utf-8")
    R.write_csv(ta, out / "table_a.csv", R.TABLE_A_COLUMNS)
    R.write_csv(tb, out / "table_b.csv")
    (out / "table_a.tex").write_text(R.to_latex(
        ta, ("config_id", "arm", "n_tasks", "SR", "pass@1", "ProgressRate", "effect", "Steps",
             "Latency", "越权率", "unsettled_runs"),
        caption=a.caption, label="tab:a-m6-all"), encoding="utf-8")
    cols_b = tuple(dict.fromkeys(k for r in tb for k in r))
    (out / "table_b.tex").write_text(R.to_latex(
        tb, cols_b, caption=a.caption.replace("Table A", "Table B"), label="tab:b-m6-all"), encoding="utf-8")
    lines = [f"# M6 构造验收合并表（{' + '.join(a.batches)}）", "",
             "| 批 | run 数 |", "| --- | --- |"] + [f"| `{k}` | {v} |" for k, v in src.items()] + ["", "## Table A", ""]
    for r in ta:
        lines.append(f"- {r['config_id']} / {r['arm']}：SR={r['SR']} pass@1={r['pass@1']} "
                     f"ProgressRate={r['ProgressRate']} effect={r['effect']} "
                     f"Steps={r['Steps']} Latency={r['Latency']} 越权率={r['越权率']} 未结算={r['unsettled_runs']}")
    # **脚注里的版本号从记录现算**：手抄过一次就写错了（把 m6 的参考轴 r1.0.8 当成任务集轴，
    # 而那句话是「把两批合成同一行 pass@1」的唯一书面理由 —— 理由里的版本号错了，读者没法判断合并成不成立）。
    axes: dict[str, set] = {}
    for r in recs:
        axes.setdefault(str(r.get("batch", "?")), set()).add(
            (str(r.get("set_version")), str(r.get("reference_version"))))
    axis_txt = "；".join(
        f"`{b}` = 任务集 " + " / ".join(sorted({s for s, _ in v}))
        + " + 参考 " + " / ".join(sorted({x for _, x in v}))
        for b, v in axes.items())
    mixed = len({s for v in axes.values() for s, _ in v}) > 1 or \
            len({x for v in axes.values() for _, x in v}) > 1
    lines += ["", f"> **逐批的四条版本轴**：{axis_txt}。"]
    if mixed:
        lines += ["> **这是一张混轴表** —— `set_version` / `reference_version` 两列因此写 `MIXED:`。",
                  "> 合并的理由是**题面同源**（这几批的任务集版本之间 instruction 指纹相同，只改了 D 面的判据键）；",
                  "> 判据按各自那一批结算时的版本。逐行来源见 `records.json` 的 `batch` 字段。",
                  "> **它证明的是链路跑通，不是任何一个发布版上的构造验收结果**：不要与单轴的表并排，",
                  "> 也不要与 `ops/reports/v1_0_readiness.md` §1 声明的版本混读 ——",
                  "> `VERSIONS.md` §2 把这张表记作「一次真事故」（表上写了 `MIXED:`，但没有任何一步拦着不让出它）。"]
    else:
        lines += ["> 判据按各自那一批结算时的版本。逐行来源见 `records.json` 的 `batch` 字段。"]
    RIO.write_text(out / "summary.md", "\n".join(lines) + "\n")
    RIO.secure_tree(out)
    print("\n".join(lines))
    print(f"→ {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
