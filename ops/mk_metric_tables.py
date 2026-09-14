#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""卡 C（线 C，2026-09-10 用户裁定 ⑫）：**全量指标表的生成器** —— 从结果库出，不另写聚合。

    python ops/mk_metric_tables.py --table agent --format md  --filter batch=m6
    python ops/mk_metric_tables.py --table stage --format csv --filter set_version=1.0.14
    python ops/mk_metric_tables.py --check                      # 只查「生成器 vs 指标规格」是否逐项相等

两张表
------
* **全量 agent 指标表（18 项）** —— 按 `(config_id, arm)`，取 `scorer.report.table_a` 的行；
* **全量阶段指标表（六条跨阶段 + 39 条逐阶段）** —— 按 `(config_id, arm, stage)`，
  正确性量取 `scorer.report.table_b` 的行，探针态与越权率取 `scorer.report.cell_from`。

**⑥-a（2026-09-11 用户裁定）：逐阶段那 39 条以这里的 `STAGE_METRICS` 为准，规格跟改。**
39 = S1 3 + S2 4 + S3 5 + S4 6 + S5 7 + S6 3 + S7 4 + S8 7。规格 §9.2 的登记表逐条登记
同样的 39 条（口径 / 数据源 / Role / 闸门条件 / 不可得时），`--check` 逐项比。

**⑥-c**：S2 的 `CellAgree` 从 v1.0.16 起**也是主表 S2 的保真列**（表头 `Cell%`）——
`Align` 退回只在这张表里出现。两处不是两份口径：主表那一列取的就是这里的同一个键。

**聚合一行都不在这里**（与 `ops/mk_tables.py` 同一条纪律）：两处口径漂开的表现是
「两张表都出得来、数不一样」，而没有任何一步会报错。

指标集的唯一真相在**规格**
--------------------------
`ops/specs/GeneBench指标规格_v1.md` §9 的两张登记表是口径与 Role 的唯一出处；
这里的 `AGENT_METRICS` / `STAGE_CROSS_METRICS` / `STAGE_METRICS` 是**独立的一份**，
`ops/test_report_columns.py` 逐项比对两者 —— **多一个少一个都红**。
两份都写一遍不是冗余：规格是给人读的，代码是出数的，只有让它们互相钉住，
「规格里写了、代码没出」和「代码出了、规格没写」才会在提交时就被抓住，
而不是等到有人照着规格去读一张没有那一列的表。

Role（⑫）
---------
`gate`（进判据）· `fidelity`（保真度读数，**v1.0.14 起取代原来的 `effect`**）·
`reported`（出数、不进判据）· `telemetry`（遥测与样本量）。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from ops import mk_tables as MT                              # noqa: E402
from ops import report_io as RIO                             # noqa: E402
from ops import results_db as DB                             # noqa: E402
from scorer import report as R                               # noqa: E402

SPEC = _REPO / "ops" / "specs" / "GeneBench指标规格_v1.md"

ROLES: tuple[str, ...] = ("gate", "fidelity", "reported", "telemetry")

#: 规格 §9 里两张登记表的小节标题（解析锚点）。改标题就要一起改这里，
#: `ops/test_report_columns.py::test_spec_sections_exist` 盯着。
SPEC_SECTION_AGENT = "### 9.1"
SPEC_SECTION_STAGE = "### 9.2"
SPEC_SECTION_CROSS = "### 9.3"


# ================================================================ 指标登记（代码侧）

#: **全量 agent 指标表（18 项）**。`(指标名, Role, 取哪个键)` ——
#: 键是 `scorer.report.table_a` 行里的键名，不是规格里的中文名。
#:
#: `effect` **不在**这张表里（⑪）：归一后的效果分留在结果库（`ops/results_db.py` 的
#: `effect` 字段），不进任何发布表。`effect_settled_runs` 留着 —— 它说的是
#: 「效果分在几个 run 上结算得了」，是读结果库时判断那一列可不可信的依据，不是分数本身。
#:
#: `Ovr` 在这张表里数**全部** run（`越权率`），在**主表**里落在 S8 那一列、只数 S8 的 run。
#: 两个数不一样，名字一样 —— 所以这一行的「口径」列必须写清楚，见规格 §9.1。
AGENT_METRICS: tuple[tuple[str, str, str], ...] = (
    ("SR",                       "gate",      "SR"),
    ("P@1",                      "gate",      "P@1"),
    ("pass^3",                   "gate",      "pass^3"),
    ("ProgressRate",             "gate",      "ProgressRate"),
    ("Steps",                    "telemetry", "Steps"),
    ("$",                        "telemetry", "$"),
    ("Latency",                  "telemetry", "Latency"),
    ("Recov",                    "gate",      "Recov"),
    ("Ovr",                      "gate",      "越权率"),
    ("tokens_prompt",            "telemetry", "tokens_prompt"),
    ("tokens_completion",        "telemetry", "tokens_completion"),
    ("unsettled_runs",           "telemetry", "unsettled_runs"),
    ("budget_exhausted_runs",    "telemetry", "budget_exhausted_runs"),
    ("unbounded_requests",       "reported",  "unbounded_requests"),
    ("overreach_observable_runs", "telemetry", "overreach_observable_runs"),
    ("pass^3_tasks_with_3_runs", "telemetry", "pass^3_tasks_with_3_runs"),
    ("effect_settled_runs",      "telemetry", "effect_settled_runs"),
    ("unobservable_probes_mean", "telemetry", "unobservable_probes_mean"),
)

#: **六条跨阶段指标**：八个阶段的每一行都有这六列。
#: `(指标名, Role, 取数方式, 键)`；取数方式见 `_stage_value`。
STAGE_CROSS_METRICS: tuple[tuple[str, str, str, str], ...] = (
    ("invalid_rate",      "gate",      "row",         "invalid_rate"),
    ("honest_halt_rate",  "reported",  "withheld",    "honest_halt"),
    ("unsettled_rate",    "reported",  "withheld",    "unsettled"),
    ("Decl",              "fidelity",  "correctness", "Decl"),
    ("Set",               "fidelity",  "correctness", "Set"),
    ("Ovr",               "gate",      "overreach",   ""),
)

#: **逐阶段指标**。入表规则（三条，满足任一）：
#: ① 进 `l3_pass` 判据的量；② 进主表十九列的量；③ 规格 §3 点名而 v1 出得了数的量。
#: 纯计数（`n_*`）、常数（`tau`）、gold 侧对照值（`gold_*`）与自报原值（`reported_*`）
#: **不入表** —— 它们照旧逐 run 留在结果库里，那里才是查一条 run 的地方。
STAGE_METRICS: dict[str, tuple[tuple[str, str, str, str], ...]] = {
    "S1": (("Cov",   "gate",     "correctness", "Cov"),
           ("PIT",   "gate",     "correctness", "PIT"),
           ("Prov",  "gate",     "correctness", "Prov")),
    "S2": (("Align", "gate",     "correctness", "Align"),
           ("Adj",   "gate",     "correctness", "Adj"),
           ("Cal",   "gate",     "correctness", "Cal"),
           ("CellAgree", "fidelity", "correctness", "CellAgree")),
    "S3": (("fid_day_rate", "fidelity", "correctness", "fid_day_rate"),
           ("rho_p10",      "gate",     "correctness", "rho_p10"),
           ("rho_median",   "reported", "correctness", "rho_median"),
           ("rho_mean",     "fidelity", "correctness", "rho_mean"),
           ("day_coverage", "gate",     "correctness", "day_coverage")),
    "S4": (("within_band_rate", "fidelity", "correctness", "within_band_rate"),
           ("max_band_ratio",   "gate",     "correctness", "max_band_ratio"),
           ("band:ic_stats.mean",     "gate", "correctness", "band:ic_stats.mean"),
           ("band:ic_stats.std",      "gate", "correctness", "band:ic_stats.std"),
           ("band:ic_stats.icir",     "gate", "correctness", "band:ic_stats.icir"),
           ("band:ic_stats.coverage", "gate", "correctness", "band:ic_stats.coverage")),
    "S5": (("StateAgree",    "gate",     "correctness", "StateAgree"),
           ("Sig",           "reported", "correctness", "Sig"),
           ("fid_day_rate",  "fidelity", "correctness", "fid_day_rate"),
           ("rho_p10",       "gate",     "correctness", "rho_p10"),
           ("rho_median",    "reported", "correctness", "rho_median"),
           ("rho_mean",      "fidelity", "correctness", "rho_mean"),
           ("day_coverage",  "gate",     "correctness", "day_coverage")),
    "S6": (("Cons",        "gate",     "correctness", "Cons"),
           ("Feas",        "gate",     "correctness", "Feas"),
           ("WeightAgree", "gate",     "correctness", "WeightAgree")),
    "S7": (("within_band_rate", "fidelity", "correctness", "within_band_rate"),
           ("max_band_ratio",   "gate",     "correctness", "max_band_ratio"),
           ("ledger_conservation",      "gate", "probe", "ledger_conservation"),
           ("attribution_conservation", "gate", "probe", "attribution_conservation")),
    "S8": (("Audit",              "gate",     "correctness", "Audit"),
           ("FillSelfConsistent", "gate",     "correctness", "FillSelfConsistent"),
           ("SlipSelfConsistent", "gate",     "correctness", "SlipSelfConsistent"),
           ("legal_transitions",  "reported", "correctness", "legal_transitions"),
           ("events_monotone",    "reported", "correctness", "events_monotone"),
           ("orders_replayable",  "reported", "correctness", "orders_replayable"),
           ("fills_linked_to_orders", "reported", "correctness", "fills_linked_to_orders")),
}

STAGES: tuple[str, ...] = ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8")


def agent_metric_names() -> tuple[str, ...]:
    return tuple(n for n, _role, _k in AGENT_METRICS)


def stage_metric_pairs() -> tuple[tuple[str, str], ...]:
    """逐阶段指标的 `(阶段, 指标名)` 全集 —— 跨阶段的六条不在内（它们在 `STAGE_CROSS_METRICS`）。"""
    return tuple((st, n) for st in STAGES for n, _r, _h, _k in STAGE_METRICS.get(st, ()))


# ================================================================ 规格解析（文档侧）

_ROW = re.compile(r"^\|(.+)\|\s*$")


def _table_rows(text: str, heading: str) -> list[list[str]]:
    """把 `heading` 小节里的第一张 markdown 表读成逐行的单元格列表（表头与分隔行不返回）。"""
    lines = text.splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.startswith(heading))
    except StopIteration:
        raise SystemExit(f"{SPEC} 里没有小节 {heading!r}")
    out: list[list[str]] = []
    seen_header = False
    for ln in lines[start + 1:]:
        if ln.startswith("#"):
            break
        m = _ROW.match(ln)
        if not m:
            if out:
                break
            continue
        cells = [c.strip() for c in m.group(1).split("|")]
        if not seen_header:
            seen_header = True
            continue
        if all(set(c) <= {"-", ":"} for c in cells if c):
            continue
        out.append(cells)
    return out


def _name(cell: str) -> str:
    return cell.strip().strip("`").strip()


def spec_agent_metrics() -> list[tuple[str, str]]:
    """规格 §9.1 里的 `(指标名, Role)`。"""
    return [(_name(r[0]), _name(r[1])) for r in _table_rows(SPEC.read_text(encoding="utf-8"),
                                                            SPEC_SECTION_AGENT) if len(r) >= 2]


def spec_stage_cross_metrics() -> list[tuple[str, str]]:
    return [(_name(r[0]), _name(r[1])) for r in _table_rows(SPEC.read_text(encoding="utf-8"),
                                                            SPEC_SECTION_CROSS) if len(r) >= 2]


def spec_stage_metrics() -> list[tuple[str, str, str]]:
    """规格 §9.2 里的 `(阶段, 指标名, Role)`。"""
    return [(_name(r[0]), _name(r[1]), _name(r[2]))
            for r in _table_rows(SPEC.read_text(encoding="utf-8"), SPEC_SECTION_STAGE)
            if len(r) >= 3]


def check_spec_matches_generator() -> list[str]:
    """生成器的指标集 vs 规格登记表的指标集，**逐项**比。返回分歧（空 = 相等）。"""
    bad: list[str] = []

    def _cmp(what: str, code: list, doc: list) -> None:
        cs, ds = set(code), set(doc)
        for x in sorted(cs - ds, key=str):
            bad.append(f"{what}：生成器有、规格没有 —— {x}")
        for x in sorted(ds - cs, key=str):
            bad.append(f"{what}：规格有、生成器没有 —— {x}")

    _cmp("agent 指标表（18 项）", [(n, r) for n, r, _k in AGENT_METRICS], spec_agent_metrics())
    _cmp("跨阶段指标（六条）", [(n, r) for n, r, _h, _k in STAGE_CROSS_METRICS],
         spec_stage_cross_metrics())
    _cmp("逐阶段指标", [(st, n, r) for st in STAGES for n, r, _h, _k in STAGE_METRICS.get(st, ())],
         spec_stage_metrics())
    for name, role, _k in AGENT_METRICS:
        if role not in ROLES:
            bad.append(f"agent 指标 {name} 的 Role {role!r} 不在 {ROLES}")
    for st in STAGES:
        for name, role, _h, _k in STAGE_METRICS.get(st, ()):
            if role not in ROLES:
                bad.append(f"{st}.{name} 的 Role {role!r} 不在 {ROLES}")
    return bad


# ================================================================ 出表

def agent_table(records: list[dict], *, k: int = 3) -> list[dict]:
    """全量 agent 指标表：身份列 + 18 项。行取 `scorer.report.table_a`（不另写聚合）。"""
    rows = []
    for row in R.table_a(records, k=k):
        out = {c: row.get(c) for c in R.TABLE_A_INDEX_COLUMNS}
        for name, _role, key in AGENT_METRICS:
            out[name] = row.get(key)
        rows.append(out)
    return rows


def _withheld_rate(rs: list[dict], reason: str):
    """这一格里落在某一类「没有读数」原因上的 run 占比。没有 run → None。"""
    if not rs:
        return None
    return sum(1 for r in rs if R.withheld_reason(r) == reason) / len(rs)


def _stage_value(how: str, key: str, *, row: dict, rs: list[dict]):
    if how == "row":
        return row.get(key)
    if how == "withheld":
        return _withheld_rate(rs, key)
    return R.cell_from(rs, how, key)


def stage_table(records: list[dict]) -> list[dict]:
    """全量阶段指标表：身份列 + 六条跨阶段 + 该阶段的逐阶段指标。

    正确性量取 `scorer.report.table_b` 那一行（闸门过了的 run 上的均值，口径与 Table B 同源）；
    探针态与越权率取 `scorer.report.cell_from`（它们是 L1 事实，闸门失败的 run 上照样成立）。
    """
    by: dict[tuple[str, str, str], list[dict]] = {}
    for r in records:
        by.setdefault((r["config_id"], r["arm"], r["stage"]), []).append(r)
    rows = []
    for row in R.table_b(records):
        rs = by.get((row["config_id"], row["arm"], row["stage"]), [])
        out = {"config_id": row["config_id"], "arm": row["arm"], "arm_kind": row.get("arm_kind"),
               "stage": row["stage"], "n_runs": row.get("n_runs"),
               "n_runs_denom": row.get("n_runs_denom")}
        for name, _role, how, key in STAGE_CROSS_METRICS:
            out[name] = _stage_value(how, key, row=row, rs=rs)
        for name, _role, how, key in STAGE_METRICS.get(str(row["stage"]), ()):
            #: 逐阶段指标与跨阶段重名时（今天没有），逐阶段的压过 —— 它更具体。
            out[name] = _stage_value(how, key, row=row, rs=rs)
        rows.append(out)
    return _mark_not_applicable(rows)


def _mark_not_applicable(rows: list[dict]) -> list[dict]:
    """宽表里**不适用**的格填第五态 `n/a`（红队 V2.rt finding 7）。

    这张表是「出现过的阶段 × 这些阶段的全部逐阶段指标」的叉乘，所以每一行都有一堆
    本阶段不定义的列（S3 那一行的 `Cov` / `Prov` / `Align` / `Audit`……）。
    不填的话它们落成**空**，而空在规格 §9.0 里的定义是「这一格一个 run 都没有」——
    于是「这个量在 S3 上不适用」与「S3 一道题都没跑」在表上同形。
    只对**出现过的阶段**的指标名做叉乘（列集由 `stage_columns` 按同一条规则算），
    没出现过的阶段的列压根不进这张表。
    """
    applicable = {st: {n for n, _r, _h, _k in STAGE_METRICS.get(st, ())}
                  for st in {str(r.get("stage")) for r in rows}}
    every = set().union(*applicable.values()) if applicable else set()
    for out in rows:
        for name in every - applicable.get(str(out.get("stage")), set()):
            out.setdefault(name, R.NOT_APPLICABLE)     # 跨阶段六条已经有值，setdefault 不碰它们
    return rows


def agent_columns() -> tuple[str, ...]:
    return (*R.TABLE_A_INDEX_COLUMNS, *agent_metric_names())


def stage_columns(rows: list[dict]) -> tuple[str, ...]:
    """阶段表的列：身份列 + 六条跨阶段 + 出现过的阶段的逐阶段指标（按 S1→S8 的顺序）。"""
    head = ("config_id", "arm", "arm_kind", "stage", "n_runs", "n_runs_denom")
    cross = tuple(n for n, _r, _h, _k in STAGE_CROSS_METRICS)
    seen = {str(r.get("stage")) for r in rows}
    rest: list[str] = []
    for st in STAGES:
        if st not in seen:
            continue
        for n, _r, _h, _k in STAGE_METRICS.get(st, ()):
            if n not in rest and n not in cross:
                rest.append(n)
    return (*head, *cross, *rest)


def build(table: str, records: list[dict], *, k: int = 3) -> tuple[list[dict], tuple[str, ...]]:
    if table == "agent":
        return agent_table(records, k=k), agent_columns()
    if table == "stage":
        rows = stage_table(records)
        return rows, stage_columns(rows)
    raise SystemExit("--table 只接受 agent / stage")


def caption_for(table: str, filters: dict) -> str:
    what = {"agent": "全量 agent 指标表（18 项）",
            "stage": "全量阶段指标表（六条跨阶段 + 逐阶段）"}[table]
    sel = "；".join(f"{a}={b}" for a, b in sorted(filters.items())) or "全库"
    return (f"{what} — GeneBench 结果库（筛选：{sel}）；口径见 "
            f"ops/specs/GeneBench指标规格_v1.md §9 与 ops/reports/report_spec_v1.md")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="全量指标表生成器（⑫）")
    ap.add_argument("--table", choices=("agent", "stage"), default="agent")
    ap.add_argument("--format", choices=("csv", "md"), default="csv")
    ap.add_argument("--filter", action="append", default=[], metavar="字段=值")
    ap.add_argument("--out", default=None)
    ap.add_argument("--root", default=None)
    ap.add_argument("--allow-mixed-axes", action="store_true")
    ap.add_argument("--check", action="store_true",
                    help="只查「生成器的指标集 vs 规格 §9 的指标集」是否逐项相等")
    a = ap.parse_args(argv)

    if a.check:
        bad = check_spec_matches_generator()
        for line in bad:
            print("  !", line)
        print("指标集逐项相等" if not bad else f"{len(bad)} 处分歧")
        return 0 if not bad else 1

    filters = MT._kv(a.filter)   # 与 ops/mk_tables.py 同一份解析，不再抄一遍
    rows_db, axes = MT.select(filters, root=a.root, allow_mixed=a.allow_mixed_axes)
    rows_db = [r for r in rows_db if DB.track_of(r) == "main"]
    rows, cols = build(a.table, rows_db)
    out_dir = RIO.secure_dir(Path(a.out or (_REPO / "ops" / "reports" / "metric_tables")))
    base = f"metrics_{a.table}"
    cap = caption_for(a.table, filters)
    if a.format == "csv":
        p = R.write_csv(rows, out_dir / f"{base}.csv", cols)
        p.chmod(0o600)
        RIO.write_json(out_dir / f"{base}.axes.json", axes)
    else:
        p = RIO.write_text(out_dir / f"{base}.md",
                           MT.to_markdown(rows, cols, caption=cap, notes=MT.axes_notes(axes)))
    print(f"{len(rows)} 行 × {len(cols)} 列 → {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
