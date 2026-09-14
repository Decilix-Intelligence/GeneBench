#!/usr/bin/env python3
"""把**定点重跑**的几道题并回整批 O1 矩阵。

为什么需要它：`ops/run_oracles.py --tasks a,b` 会用这一次的结果**整份覆盖**
`ops/reports/probe_run_oracle.json` —— 于是修完两道题重跑一次，40 题的矩阵就只剩 2 行了。
合并要留痕：每行记 `at`（这一行是哪一次跑出来的），矩阵页脚写明它是拼的。

用法：python ops/merge_o1.py <整批的 json> [--out ops/reports/probe_run_oracle.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from ops import report_io as RIO                     # noqa: E402
from ops import run_oracles as RO                    # noqa: E402



def _render(rows: "list[dict]", a) -> str:
    """按 `--instances` 分叉：实例层走 `render_matrix_instances`，出集层走原来的 `render_matrix`。

    **两条不能共用一个渲染器**：出集那张把题目摊成列（40 列刚好读得完），
    实例层摊出来是 130 列 —— 宽到没人读得完，而且会把「实例」读成「新题」。
    实例层的口径必须一直是「40 模板 / N 实例」。
    """
    if a.instances:
        import genebench_config as cfg
        return RO.render_matrix_instances(
            rows, channel=(a.channel or cfg.channel()),
            set_name=(a.set_name or RO.INSTANCE_SET_NAME))
    return RO.render_matrix(RO.rows_as_results(rows), agent="oracle", tier="full")

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("base", nargs="?", default="",
                    help="整批跑出来的 probe_run_oracle.json（先拷出来的那份）。"
                         "--render-only 时不需要")
    ap.add_argument("--patch", default="",
                    help="定点重跑的那份（默认就是被覆盖后的当前文件）")
    ap.add_argument("--out", default="")
    ap.add_argument("--matrix", default="")
    # ---- Y1b 实例层 ----
    ap.add_argument("--instances", action="store_true",
                    help="**按实例聚合渲矩阵**（Y1b）：默认读写 probe_run_instances.json / "
                         "probe_matrix_instances.md，矩阵走 run_oracles.render_matrix_instances "
                         "（表一按基点聚合、表二逐实例展开），口径「40 模板 / N 实例」")
    ap.add_argument("--render-only", action="store_true",
                    help="**只渲不并**：拿 --patch 指的那份（或它的 .cumulative.json）"
                         "直接渲一张矩阵。分批跑到一半想看当前覆盖率时用；"
                         "它一个字节都不写进明细文件")
    ap.add_argument("--channel", default="", choices=("", "private", "public"),
                    help="渲报告时标哪条通道（默认按 GENEBENCH_CHANNEL 现算）")
    ap.add_argument("--set-name", default="",
                    help="答案面题集目录名，写进报告抬头（如 v1.0-instances）")
    a = ap.parse_args(argv)
    reports = _REPO / "ops" / "reports"
    stem = "probe_run_instances" if a.instances else "probe_run_oracle"
    mname = "probe_matrix_instances.md" if a.instances else "probe_matrix_oracle.md"
    a.patch = a.patch or str(reports / f"{stem}.json")
    a.out = a.out or str(reports / f"{stem}.json")
    a.matrix = a.matrix or str(reports / mname)

    if a.render_only:
        # 只渲：优先读累积文件（它才是「所有跑过的行」），没有就读 --patch 本身。
        src = Path(a.patch).with_suffix(".cumulative.json")
        if not src.is_file():
            src = Path(a.patch)
        rows = json.loads(src.read_text(encoding="utf-8"))
        md = _render(rows, a)
        RIO.write_text(Path(a.matrix), md)
        print(f"只渲不并：{len(rows)} 行来自 {src} → {a.matrix}")
        return 0

    if not a.base:
        raise SystemExit("要并就得给 base（整批那份）；只想渲矩阵加 --render-only")
    base = {r["task_id"]: r for r in json.loads(Path(a.base).read_text(encoding="utf-8"))}
    patch = {r["task_id"]: r for r in json.loads(Path(a.patch).read_text(encoding="utf-8"))}
    for tid, row in patch.items():
        # **只让更新的覆盖更旧的**：定点重跑与整批的先后由每行的 `at` 定，不由谁先谁后的调用顺序定。
        if base.get(tid, {}).get("at", "") > row.get("at", ""):
            continue
        row["merged_from"] = "targeted_rerun"
        base[tid] = row
    rows = [base[k] for k in sorted(base)]
    RIO.write_json(Path(a.out), rows)
    # 与 `run_oracles` **同一个还原器**：这里此前自己拼过一份，少了 `tradability_rows`，
    # 而 `render_matrix` 用它算「喂了可交易性视图的题」—— 合并一跑就 AttributeError
    # （红队阶段六顺手修；两处各拼一份 SimpleNamespace 本来就是同一个还原器的两份副本）。
    md = _render(rows, a)
    ages = sorted({str(r.get("at", "?"))[:16] for r in rows})
    md += (f"\n> **本矩阵是拼的**：{len(rows)} 行来自 {len(ages)} 次跑批（{', '.join(ages)}）。"
           f"本次并入 {len(patch)} 行（{', '.join(sorted(patch))}）。逐行 `at` / `merged_from` 标了来源与时刻；"
           f"**只有更新的行会覆盖更旧的**。\n")
    # 合并结果同时留一份累积基线 —— 下一次定点重跑就从它接着拼，不必再去找「上一次整批」在哪。
    RIO.write_json(Path(a.out).with_suffix(".cumulative.json"), rows)
    RIO.write_text(Path(a.matrix), md)
    print(f"合并 {len(rows)} 行（其中定点重跑 {len(patch)} 行）→ {a.out}")
    print(f"矩阵 → {a.matrix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
