#!/usr/bin/env python3
"""卡 5.4（线 C，2026-09-07）：**三张表全部从结果库生成** —— CSV / Markdown / LaTeX。

    python ops/mk_tables.py --table a --format csv   --filter batch=m6 --out ops/reports/x
    python ops/mk_tables.py --table b --format md    --filter set_version=1.0.12
    python ops/mk_tables.py --table adaptation --format latex --filter batch=adapt

聚合逻辑**一行都不在这里** —— Table A / Table B / 适配赛道表分别调
`scorer.report.table_a` / `table_b` / `table_adaptation`。这个文件只做三件事：
选记录（`ops.results_db.query`）、拦混轴、把行渲染成三种格式。
再写一份聚合等于把口径分成两处，而两处口径漂开的表现是「两张表都出得来、数不一样」。

**混轴保护**（本卡的判据 2）
---------------------------
所选记录的四条版本轴（`results_db.AXES`：set / reference / protocol / channel）
不全同时，**默认拒绝出表**并列出分歧。`--allow-mixed-axes` 显式放行，放行后
md / latex 的表脚注里逐条写明混了哪些值，CSV 旁边落一份 `<表名>.axes.json`。

为什么这条要成为一道门而不只是一列：`ops/reports/m6_all` 就是 m6（题面 `1.0.7`）与
m6b（`1.0.9`）合出来的，`table_a` 按 `(config_id, arm)` 分组 —— 两个题面版本的 run
合成了同一行 pass@1。红队 5.1 让表把它写成 `MIXED:1.0.7|1.0.9`，但**没有任何一步拦着**。
论文里那一行会被当成一个可比的读数读，而它不是。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from ops import report_io as RIO                             # noqa: E402
from ops import results_db as DB                             # noqa: E402
from scorer import report as R                               # noqa: E402

TABLES = ("main", "a", "b", "adaptation")
FORMATS = ("csv", "md", "latex")

#: **⑥-b（2026-09-11 用户裁定）：`table_a` / `table_b` 是诊断件，不是发布件。**
#: 发布表只有三张 —— 主表 `table_main`（⑩ 的固定十九列）+ 两张全量指标表
#: （`metrics_agent` / `metrics_stage`，见 `ops/mk_metric_tables.py`）。
#: `effect` 这一列留在 Table A 里（⑪ 只说它不进**发布表**，没说不再算），
#: 正因为它还在，Table A 更不能被人当发布表引用 —— 所以落盘时旁边写一份说明。
DIAGNOSTIC_TABLES: tuple[str, ...] = ("a", "b")

#: 说明文件的文件名模板。**与表同目录、同前缀** —— 归档目录是平的，
#: 名字里看不出出处的话，`table_a.csv` 与它的说明会走散。
DIAGNOSTIC_NOTE_NAME = "table_{t}.NOTE.md"

_DIAGNOSTIC_NOTE_BODY = """\
# `table_{t}.csv` 是**诊断件，不是发布件**

> ⑥-b（2026-09-11 用户裁定）。这一页与表同目录，改表的生成器会把它重写一遍。

| | |
| --- | --- |
| 这是什么 | Table {T}：{what} |
| 能不能引用 | **不能**。它带 `effect` 这一类归一/聚合列，而裁定 ⑪ 明写 effect 不进发布表 |
| 那该引用哪张 | 同目录的 `table_main.csv`（⑩ 的固定十九列）与 `metrics_agent.*` / `metrics_stage.*`（⑫ 的两张全量指标表） |
| 为什么还留着 | 留证据。逐格核对「结果库出的表 == 既有的表」靠的就是它（`ops/mk_tables.py::verify_batch`），删了就核不了 |
| 逐列口径 | 主表在 `ops/reports/report_spec_v1.md`；全部指标在 `ops/specs/GeneBench指标规格_v1.md` §9 |

诊断件不进发布件清单：判据在 `ops/mk_release_manifest.py::DIAGNOSTIC_NOT_RELEASE`
与 `ops/archive_signoff.py::RELEASE_TABLES`，测试在 `ops/test_report_columns.py`。
"""

_DIAGNOSTIC_WHAT = {
    "a": "按 `(config_id, arm)` 的 agent 级诊断表（含 `effect`、pass^k、遥测与四条版本轴）",
    "b": "按 `(config_id, arm, stage)` 的阶段级诊断表（逐阶段的正确性量原值）",
}


def write_diagnostic_note(out_dir: Path, table: str) -> Path:
    """在诊断表旁边写一份「这张表不能当发布表引用」的说明。幂等。"""
    out_dir = RIO.secure_dir(Path(out_dir))
    body = _DIAGNOSTIC_NOTE_BODY.format(t=table, T=table.upper(),
                                        what=_DIAGNOSTIC_WHAT.get(table, "诊断表"))
    return RIO.write_text(out_dir / DIAGNOSTIC_NOTE_NAME.format(t=table), body)

#: LaTeX 默认列。CSV 出全列（`TABLE_A_COLUMNS`，与 `ops/score_runs.py` 逐字一致，
#: 「与既有 CSV 逐格相同」这条验收靠它），LaTeX 是给人读的，26 列排不进 booktabs。
LATEX_A_COLUMNS: tuple[str, ...] = (
    "config_id", "arm", "SR", "pass@1", "pass^3", "ProgressRate", "Steps", "$", "Latency", "Recov", "越权率")


class MixedAxesError(RuntimeError):
    pass


def caption_for(table: str, filters: dict) -> str:
    """表头必须写清这批数是什么（与 `ops/score_runs.py::caption_for` 同一条纪律）：
    库里到今天为止**一条实验数据都没有**，全是构造验收与接入验证。"""
    what = {"main": "主表（固定十九列）", "a": "Table A", "b": "Table B",
            "adaptation": "Table Adaptation"}[table]
    sel = "；".join(f"{k}={v}" for k, v in sorted(filters.items())) or "全库"
    return f"{what} — GeneBench 结果库（筛选：{sel}）；构造验收 / 接入验证，**不是实验数据**"


# ------------------------------------------------------------------ 选记录

def select(filters: dict | None = None, *, root=None, allow_mixed: bool = False,
           records: list[dict] | None = None) -> tuple[list[dict], dict]:
    """按筛选条件取记录 + 拦混轴。返回 `(records, axes_report)`。"""
    f = dict(filters or {})
    rows = DB.query(root, records=records, **f)
    mixed = DB.mixed_axes(rows)
    axes = {"filters": f, "n_records": len(rows), "axis_values": DB.axis_values(rows),
            "mixed_axes": mixed, "allow_mixed_axes": bool(allow_mixed),
            "version_combos": DB.versions(records=rows)}
    if mixed and not allow_mixed:
        detail = "；".join(f"{k}: {' | '.join(v)}" for k, v in sorted(mixed.items()))
        raise MixedAxesError(
            f"所选的 {len(rows)} 条记录跨了版本轴，默认不出表 —— 分歧：{detail}。"
            f"这不是一个可比的读数（同一行会把两个版本的 run 合成一个 pass@1）。"
            f"确实要合就加 --allow-mixed-axes，表脚注会写明。")
    return rows, axes


# ------------------------------------------------------------------ 出行

def build(table: str, records: list[dict], *, k: int = 3) -> tuple[list[dict], tuple[str, ...] | None]:
    """→ `(rows, csv 列)`。`None` 列 = 交给 `scorer.report.write_csv` 的默认列序
    （Table B 就是这么出的，「逐格相同」要求连列序都一样）。"""
    if table == "main":
        #: ⑩ 主表：身份列 + **固定十九列**。行由 `scorer.report.main_table` 出
        #: （聚合口径只有一处：它自己调 `table_a`）。
        #: 先筛主赛道：**适配赛道的记录没有 task_id**（`scorer.adaptation` 的记录按 example_id 走），
        #: 混进来 `table_a` 会在 `r["task_id"]` 上直接 KeyError。适配赛道有它自己的表。
        return (R.main_table([r for r in records if DB.track_of(r) == "main"], k=k),
                (*R.TABLE_A_INDEX_COLUMNS, *R.MAIN_TABLE_COLUMNS))
    if table == "a":
        return R.table_a(records, k=k), R.TABLE_A_COLUMNS
    if table == "b":
        return R.table_b(records), None
    if table == "adaptation":
        adapt = [r for r in records if DB.track_of(r) == "adaptation"]
        return R.table_adaptation(adapt), R.TABLE_ADAPTATION_COLUMNS
    raise SystemExit(f"--table 只接受 {TABLES}")


def default_columns(rows: list[dict]) -> tuple[str, ...]:
    """`scorer.report.write_csv` 的默认列序，逐字镜像（md / latex 要与 CSV 同列同序）。"""
    return tuple(sorted({key for r in rows for key in r},
                        key=lambda key: (key not in R.TABLE_A_COLUMNS, key)))


# ------------------------------------------------------------------ 渲染

def _md_cell(v) -> str:
    if v is None or v == "":
        return ""
    if isinstance(v, float):
        return f"{v:.6g}"
    return str(v).replace("|", r"\|").replace("\n", " ")


def to_markdown(rows: list[dict], columns: tuple[str, ...], *, caption: str,
                notes: list[str] | None = None) -> str:
    out = [f"# {caption}", "",
           "| " + " | ".join(str(c) for c in columns) + " |",
           "| " + " | ".join("---" for _ in columns) + " |"]
    for r in rows:
        out.append("| " + " | ".join(_md_cell(r.get(c)) for c in columns) + " |")
    if notes:
        out += [""] + [f"> {n}" for n in notes]
    return "\n".join(out) + "\n"


def axes_notes(axes: dict) -> list[str]:
    """表脚注：四条版本轴逐条写出来。混轴放行时**必须**说明混了哪些值。"""
    notes = []
    mixed = axes.get("mixed_axes") or {}
    for ax in DB.AXES:
        vals = axes["axis_values"].get(ax) or []
        if ax in mixed:
            notes.append(f"**{ax} 混轴**：{' | '.join(vals)} —— 这一列的行不是一个可比的读数")
        elif len(vals) == 1:
            notes.append(f"{ax} = {vals[0]}")
        elif not vals:
            notes.append(f"{ax} = （空）")
        else:
            #: 协议轴上「裸臂 = none + 协议臂 = 某个摘要」不是混轴（红队 5.rt finding 4，
            #: 判据在 `DB.mixed_axes`）。脚注要把这件事说清楚，否则读者看到两个取值
            #: 会以为这张表被合过。
            if ax == "protocol_version":
                injected = [v for v in vals if v != DB.NO_PROTOCOL]
                notes.append(f"{ax} = {' | '.join(injected) or '（无）'}"
                             f"（裸臂在协议轴上记 `{DB.NO_PROTOCOL}` —— 它们不投放协议工件，"
                             f"与协议臂并排不算混轴）")
            else:
                notes.append(f"{ax} = {' | '.join(vals)}")
    notes.append(f"记录数 {axes['n_records']}；筛选 "
                 f"{'；'.join(f'{k}={v}' for k, v in sorted(axes['filters'].items())) or '全库'}")
    if axes.get("mixed_axes") and axes.get("allow_mixed_axes"):
        notes.append("本表由 `--allow-mixed-axes` 显式放行；跨版本轴的行按 `(config_id, arm)` "
                     "合并，读数不可与单版本的表并排比较。")
    return notes


# ------------------------------------------------------------------ 落盘

def write_table(table: str, fmt: str, rows: list[dict], columns, axes: dict, out_dir: Path,
                *, name: str | None = None, caption: str | None = None,
                label: str | None = None, digits: int = 3) -> Path:
    out_dir = RIO.secure_dir(Path(out_dir))
    base = name or f"table_{table}"
    cap = caption or caption_for(table, axes.get("filters") or {})
    cols = tuple(columns) if columns else default_columns(rows)
    if fmt == "csv":
        p = out_dir / f"{base}.csv"
        R.write_csv(rows, p, columns if columns else None)
        p.chmod(0o600)
        RIO.write_json(out_dir / f"{base}.axes.json", axes)
    elif fmt == "md":
        p = RIO.write_text(out_dir / f"{base}.md",
                           to_markdown(rows, cols, caption=cap, notes=axes_notes(axes)))
    elif fmt == "latex":
        tex_cols = LATEX_A_COLUMNS if (table == "a" and columns == R.TABLE_A_COLUMNS) else cols
        if table == "main":
            #: 主表的十九列**一列都不许裁**（⑩）——  booktabs 排不下就横排小字，
            #: 不是挑几列出来：挑过的主表与没挑过的主表长得一样，读者分不出。
            tex_cols = cols
        body = R.to_latex(rows, tuple(tex_cols), caption=cap,
                          label=label or f"tab:{table}", digits=digits)
        body += "\n" + "\n".join("% " + n.replace("**", "") for n in axes_notes(axes)) + "\n"
        p = RIO.write_text(out_dir / f"{base}.tex", body)
    else:
        raise SystemExit(f"--format 只接受 {FORMATS}")
    #: ⑥-b：诊断表旁边永远有一份说明。放在**落盘的那一步**而不是调用方，
    #: 是因为漏写不会报错 —— 一张没有说明的 `table_a.csv` 与发布表长得一模一样。
    if table in DIAGNOSTIC_TABLES:
        write_diagnostic_note(out_dir, table)
    return p


# ------------------------------------------------------------------ 回填核对

def verify_batch(batch: str, *, root=None, reports: Path | None = None) -> dict:
    """从结果库出的 Table A / B 与 `ops/reports/<batch>/` 里既有的 CSV **逐格**比。

    不同就是聚合逻辑漂了 —— 报出来，不修表。
    """
    import csv as _csv
    import io
    base = reports or (_REPO / "ops" / "reports")
    res = {"batch": batch, "tables": {}}
    rows_db, _axes = select({"batch": batch}, root=root, allow_mixed=True)
    for t, fname in (("a", "table_a.csv"), ("b", "table_b.csv")):
        old_p = base / batch / fname
        if not old_p.is_file():
            res["tables"][t] = {"status": "既有 CSV 不存在", "diffs": []}
            continue
        rows, columns = build(t, rows_db)
        buf = io.StringIO()
        cols = list(columns) if columns else list(default_columns(rows))
        w = _csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: ("" if r.get(c) is None else r.get(c)) for c in cols})
        #: **`newline=""` 读**：`read_text` 默认把 `\r\n` 翻成 `\n`，而 `csv.writer` 写的就是
        #: `\r\n` —— 用默认读法比，两份逐字节相同的 CSV 也会判成「不同」，
        #: 于是这道验收永远只能报「0 格不同」而报不出「逐格相同」。
        with open(old_p, encoding="utf-8", newline="") as _fh:
            old_txt = _fh.read()
        new_txt = buf.getvalue()
        if new_txt == old_txt:
            res["tables"][t] = {"status": "逐格相同", "diffs": [], "n_rows": len(rows)}
            continue
        new_rows = list(_csv.reader(io.StringIO(new_txt)))
        old_rows = list(_csv.reader(io.StringIO(old_txt)))
        diffs = []
        for i in range(max(len(new_rows), len(old_rows))):
            a = new_rows[i] if i < len(new_rows) else []
            b = old_rows[i] if i < len(old_rows) else []
            for j in range(max(len(a), len(b))):
                x = a[j] if j < len(a) else "<缺列>"
                y = b[j] if j < len(b) else "<缺列>"
                if x != y:
                    diffs.append({"row": i, "col": j, "db": x, "既有": y})
        res["tables"][t] = {"status": f"{len(diffs)} 格不同", "diffs": diffs[:40], "n_rows": len(rows)}
    return res


def write_backfill_report(path: Path, *, results: list[dict], errors: list[str],
                          root=None, verify: bool = True) -> Path:
    rows = DB.load(root)
    vers = DB.versions(records=rows)
    lines = ["# 结果库回填与核对（卡 5.4）", "",
             f"库：`{DB.results_path(root)}`；记录 **{len(rows)}** 条；版本轴组合 **{len(vers)}** 种。", "",
             "## 怎么用", "",
             "```bash",
             "PY=/data/shared/genebench/env/bin/python; cd /data/shared/genebench/repo",
             # <!-- H10-2026-09-14 --> 上面那一行是**发布方那台**的落点，**逐字不动**：
             # 它逐字是 ops/test_A9.py 与 ops/test_single_machine.py 两份豁免清单里的条目，
             # 改掉就让那两道门出现死条目而变红 —— 真修要与那两个测试文件同批。
             # 补两行渲染出去的注释，别让外部读者照着发布方的路径敲。
             "# ↑ 上面那两个值是**发布方那台**的。换一台机器（含外部单机用户）请改成自己的根：",
             "#   PY=$GENEBENCH_ROOT/env/bin/python; cd $GENEBENCH_ROOT/repo",
             "# 新结算之后把这一批收进库（幂等，收两遍不会重）",
             "$PY ops/results_db.py ingest --batch <batch>",
             "# 库里都有哪些版本轴组合（混轴在这里看得见）",
             "$PY ops/results_db.py versions",
             "# 三张表，三种格式；--filter 可重复，值用逗号分隔即「或」",
             "$PY ops/mk_tables.py --table a --format csv   --filter batch=m6            --out ops/reports/m6",
             "$PY ops/mk_tables.py --table b --format md    --filter set_version=1.0.12  --out /tmp/x",
             "$PY ops/mk_tables.py --table adaptation --format latex --filter batch=adapt --out /tmp/x",
             "# 跨版本合表：默认拒绝，必须显式放行（放行后表脚注会写明混了哪些值）",
             "$PY ops/mk_tables.py --table a --format csv --filter batch=m6,m6b --allow-mixed-axes --out /tmp/x",
             "```", "",
             "四条版本轴 = `set_version` / `reference_version` / `protocol_version` / `channel`",
             "（票据 N-207 的「四个版本字段」）。**缺一即拒**：一条不知道自己是哪一版跑出来的记录，",
             "进了库就再也切不开。主键是 `(batch, run_id)` 而不是裸 `run_id` —— 见下面的重名表。", "",
             "## 收了哪些批", "",
             "| batch | records.json | 入库 | 重复 | protocol_version | channel |",
             "| --- | --- | --- | --- | --- | --- |"]
    for r in results:
        lines.append(f"| `{r['batch']}` | {r.get('n_records')} | {r['added']} | {r['duplicate']} | "
                     f"`{r['protocol_version']}` | {r['channel']} |")
    if errors:
        lines += ["", "## 没收进来的", ""] + [f"- {e}" for e in errors]
    lines += ["", "## 版本轴组合", "",
              "| set_version | reference_version | protocol_version | channel | run 数 | 批 |",
              "| --- | --- | --- | --- | --- | --- |"]
    for v in vers:
        lines.append(f"| {v['set_version']} | {v['reference_version']} | `{v['protocol_version']}` | "
                     f"{v['channel']} | {v['n_runs']} | {', '.join(v['batches'])} |")
    lines += ["", "## 已知限制", "",
              "- **适配赛道还没有记录**：`scorer.adaptation.AdaptationResult.as_record` 出的记录不带"
              "四条版本轴（也没有 `task_id` / `seq`），`ops/reports/adapt/records.json` 现在是空的"
              "（真跑被红线 B2 闸住）。库的适配赛道通路已经通（`--table adaptation` 出得来表，"
              "身份键走 `IDENTITY_ADAPT`），但要真收记录，得先让 `adapt_report.py` 把四条轴写进记录。",
              "- **公开通道没有可结算的 run**：`ops/reports/public/` 里只有三控与对账，没有 `records.json`。"
              "所以库里 `channel` 现在只有 `private` 一个取值；回填时它是**声明**的（`axes_source.channel"
              "= backfill:declared`），不是从记录里读出来的 —— 记录里根本没有这一项。",
              "- **协议轴是逐 run 反算的**（红队 5.rt finding 4 之后）：取 "
              "`runs_in/<batch>/<run_id>/inject.json` 里这次注入真的拿到的 "
              "`work/protocol/{validate_artifact.py,README.md,contract.md}` 三件的 sha。"
              f"裸臂不发协议工件 → 逐 run 记 `{DB.NO_PROTOCOL}`（**显式**「这次没有协议工件」，"
              "不是「不知道」）；同一批里 `none` 与摘要并排**不算混轴**（`results_db.mixed_axes` "
              "按 arm_kind 分组判），协议臂之间出现两个摘要才算。"
              "一批里反算出两个摘要 → 拒（人来裁定）；连 `inject.json` 都读不到 → 拒，"
              "不拿今天仓库里的版本去追认。纯裸臂的批（oracle / 控制批）现在收得进来了。"]
    reuse = DB.run_id_reuse(rows)
    lines += ["", "## 跨批重名的 run_id（主键必须带 batch 的理由）", ""]
    lines += ([f"- `{k}`：{', '.join(v)}" for k, v in sorted(reuse.items())] or ["- 无"])
    if verify:
        lines += ["", "## 与既有 CSV 逐格核对", "",
                  "| batch | Table A | Table B |", "| --- | --- | --- |"]
        detail: list[str] = []
        for r in results:
            v = verify_batch(r["batch"], root=root)
            lines.append(f"| `{r['batch']}` | {v['tables'].get('a', {}).get('status', '—')} | "
                         f"{v['tables'].get('b', {}).get('status', '—')} |")
            for t, tv in v["tables"].items():
                if tv["diffs"]:
                    detail.append(f"### `{r['batch']}` Table {t.upper()}")
                    detail += [f"- 第 {d['row']} 行第 {d['col']} 列：库 `{d['db']}` ≠ 既有 `{d['既有']}`"
                               for d in tv["diffs"]]
        if detail:
            lines += ["", "### 不同的格"] + detail
    return RIO.write_text(Path(path), "\n".join(lines) + "\n")


# ------------------------------------------------------------------ CLI

def _kv(pairs: list[str]) -> dict:
    return DB._kv(pairs)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="从结果库生成 Table A / Table B / 适配赛道表")
    ap.add_argument("--table", required=True, choices=TABLES)
    ap.add_argument("--format", default="csv", choices=FORMATS)
    ap.add_argument("--filter", action="append", default=[], help="k=v（可重复；v 用逗号分隔即「或」）")
    ap.add_argument("--out", required=True)
    ap.add_argument("--db", default=None)
    ap.add_argument("--name", default=None, help="输出文件名（不含扩展名）")
    ap.add_argument("--caption", default=None)
    ap.add_argument("--label", default=None)
    ap.add_argument("--allow-mixed-axes", action="store_true")
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--write-notes-only", action="store_true",
                    help="⑥-b：只在 --out 目录里补写诊断件说明（不出表、不读结果库）")
    a = ap.parse_args(argv)
    if a.write_notes_only:
        for t in DIAGNOSTIC_TABLES:
            if (Path(a.out) / f"table_{t}.csv").is_file():
                print(write_diagnostic_note(Path(a.out), t))
        RIO.secure_tree(Path(a.out))
        return 0
    filters = _kv(a.filter)
    try:
        records, axes = select(filters, root=a.db, allow_mixed=a.allow_mixed_axes)
    except MixedAxesError as e:
        print(f"拒绝出表：{e}", file=sys.stderr)
        return 3
    if not records:
        print(f"没有记录匹配 {filters or '（无筛选）'}", file=sys.stderr)
    rows, columns = build(a.table, records, k=a.k)
    p = write_table(a.table, a.format, rows, columns, axes, Path(a.out),
                    name=a.name, caption=a.caption, label=a.label)
    RIO.secure_tree(Path(a.out))
    print(f"{len(rows)} 行 ← {len(records)} 条记录 → {p}")
    if axes["mixed_axes"]:
        print(f"（混轴放行：{axes['mixed_axes']}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
