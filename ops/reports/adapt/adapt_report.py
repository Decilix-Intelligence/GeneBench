#!/usr/bin/env python3
"""卡 4.2-b：适配赛道（v1.0-adapt）的**结算与出表**驱动。

为什么它住在 `ops/reports/adapt/` 而不是折进 `ops/score_runs.py`：`score_runs` 是共享文件，
本卡没有它的路径授权（票据 `ops/tickets_inbox/4.2b.md` 记了一条，建议后续折进去）。
两者形状刻意一致 —— rsync 拉回 → 逐 run 结算 → 出表 → `RIO.secure_tree`。
差别只有一处：主赛道走 `scorer.score_run`，适配赛道走 `scorer.adaptation.score_adaptation_run`
（五结局，比对 oracle；口径见 `ops/specs/adaptation_track.md` §5）。

两个子命令，都**不需要有真跑**也能跑通（没有 run 就出 0 行的表 + 30 行的 oracle 矩阵）：

    python ops/reports/adapt/adapt_report.py matrix
        → oracle_matrix.csv / oracle_matrix.md（30 行：level / task / mutation / expected / actual / calls）

    python ops/reports/adapt/adapt_report.py score --remote /data/genebench_runner/adapt/runs/runs
    python ops/reports/adapt/adapt_report.py score --no-pull
        → records.json / table.csv / table.tex / summary.md（外加 matrix，二者始终同批出）

**真跑已放行**（2026-09-10 用户裁定 **N-348**，卡 Y2）：题源改成**出集规定题的 oracle 产物**，
守门那条按集拒显式解除并记因，换成一道落点判据。代价写在 `ops/specs/adaptation_track.md` §7 ——
**跑过本赛道的被测方，主赛道被引用的那些题算「可能已见过答案」**。这句话跟着每一张表走
（`scorer/report.py::ADAPT_ORACLE_EXPOSURE_NOTE`）。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import genebench_config as cfg                                   # noqa: E402
from ops import report_io as RIO                                 # noqa: E402
from scorer import adaptation as AD                              # noqa: E402
from scorer import report as R                                   # noqa: E402

BATCH = "adapt"
SET_ID = "v1.0-adapt"
F02 = "ljn@192.168.1.219"
RUNS_IN: Path = cfg.GENEBENCH_ROOT / "runs_in" / BATCH
EXAMPLES_ROOT: Path = cfg.GENEBENCH_ROOT / "reference" / "adaptation" / SET_ID
OUT: Path = _REPO / "ops" / "reports" / BATCH

#: 表头必须写清这批数是什么（与 `ops/score_runs.py::caption_for` 同一条纪律）。
CAPTION = ("Table Adaptation — GeneBench 适配赛道 v1.0-adapt"
           "（30 例 = L1 单位 / L2 词汇 / L3 缺协议字段 各 10；每级按阶段分层覆盖八个阶段；"
           "题源 = 出集规定题的 oracle 产物，种子固定；**不是主赛道实验数据**）")

MATRIX_COLUMNS = ("example_id", "level", "stage", "source_task", "family", "site",
                  "mutation", "recovery_route", "broken_validator_ok", "expected_outcome",
                  "run_id", "actual_outcome", "as_expected", "valid", "matched",
                  "validator_rejections", "calls", "note")

NOT_RUN = "未运行"


# ------------------------------------------------------------------ 拉取


#: **这一版为准**（X2，2026-09-11）。适配表在 v1.0.14 / r1.0.21 的签字包里**整体偏低约 13 个
#: 百分点**，原因在 oracle 侧不在被测方：S6 的参考解在 `provenance[0].artifact_id` 上留了占位串
#: `TODO:signal-artifact-id-missing`，而被测方按协议写了合法的 `unresolved` —— **判据罚的正是
#: 照规则做的那一方**。r1.0.22（提交 49748ac）把占位串改成协议的 unresolved 标记之后，受影响的
#: 四例（adapt-l1-08 / l2-07 / l2-08 / l3-06）的**既有** agent 产物与新 oracle 在 `provenance`
#: 上逐字节相同，所以是重算不是重跑（真 API 0 次）；第五例 adapt-l3-07 的源也随之变了，但它
#: 前后都因 `provenance: []` 与 oracle 不一致而 failed，结局不变。
RESCORE_NOTE = (
    "**本版为准（X2，2026-09-11）**：v1.0.14 / r1.0.21 签字包内的这张表**整体偏低约 13 个百分点**"
    "（ALL resolved 0.6333 → 0.7667；failed 11 → 7；L1 first_pass 7 → 8、L2 7 → 9、"
    "L3 correct_flag 5 → 6）。**不是被测方表现变了，是 oracle 侧判错**：S6 参考解的 "
    "`provenance[0].artifact_id` 曾是占位串 `TODO:signal-artifact-id-missing`，被测方按协议写了"
    "合法的 `unresolved`，判据罚的是照规则做的那一方。r1.0.22 修根因后，这四例的**既有**产物与新 "
    "oracle 在 `provenance` 上逐字节相同 —— 重算，未重跑，真 API 0 次。记因见 "
    "`ops/freeze_v10.py::REFERENCE_REVISIONS` 的 r1.0.22 条；逐例见 `ops/tickets_inbox/X2.md`。"
)


def pull(remote: str) -> Path:
    """f01 主动 rsync（方向纪律：只有 f01 → f02 这一个 ssh 方向）。排除项与 `ops/score_runs.py` 同源：
    Codex 在 `.codex/tmp/arg0/` 下留断链符号链接，照搬回来会让网关的红线 5 守门拒绝启动。"""
    RUNS_IN.mkdir(parents=True, exist_ok=True, mode=0o700)
    RUNS_IN.chmod(0o700)
    cmd = ["rsync", "-a", "--no-perms", "--chmod=D700,F600",
           "--exclude=.codex/", "--exclude=**/tmp/arg0/",
           f"{F02}:{remote.rstrip('/')}/", f"{RUNS_IN}/"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise SystemExit(f"拉取失败：{r.stderr[-500:]}")
    return RUNS_IN


# ------------------------------------------------------------------ 逐 run 结算


def allowed_calls(run_dir: Path) -> int | None:
    """这次 run 真打出去多少次模型调用 —— `log/llm_log.jsonl` 里 `decision == "allow"` 的条数。
    没有这份日志（run 压根没起来）返回 None，**不返回 0**：0 次调用与「不知道」不是一回事。"""
    p = Path(run_dir) / "log" / "llm_log.jsonl"
    if not p.is_file():
        return None
    n = 0
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            if json.loads(line).get("decision") == "allow":
                n += 1
        except ValueError:
            continue
    return n


def score_all(runs_root: Path) -> tuple[list[dict], list[str]]:
    records: list[dict] = []
    problems: list[str] = []
    if not runs_root.is_dir():
        return records, [f"没有 run 根 {runs_root}（还没有真跑）"]
    for rd in sorted(p for p in runs_root.iterdir() if p.is_dir() and (p / "inject.json").is_file()):
        inj = json.loads((rd / "inject.json").read_text(encoding="utf-8"))
        ex_dir = EXAMPLES_ROOT / inj["task_id"]
        if not (ex_dir / "mutation.json").is_file():
            problems.append(f"{rd.name}: 没有适配例目录 {ex_dir}")
            continue
        try:
            rec = AD.score_adaptation_run(rd, ex_dir, config_id=inj.get("config_id", "?"),
                                          arm=inj.get("arm", "?"), run_id=inj.get("run_id", rd.name))
        except Exception as e:                       # noqa: BLE001  一个 run 坏了不拖垮整批，但要记下来
            problems.append(f"{rd.name}: {type(e).__name__}: {e}")
            continue
        rec["calls"] = allowed_calls(rd)
        try:
            rec["exit_code"] = json.loads((rd / "run.json").read_text(encoding="utf-8")).get("exit_code")
        except (OSError, ValueError):
            rec["exit_code"] = None
        records.append(rec)
    return records, problems


# ------------------------------------------------------------------ 进结果库


def axes_for(rec: dict) -> dict:
    """四条版本轴。**适配赛道的记录本来一条都不带**（`AdaptationResult.as_record` 只出判据），
    于是它进不了结果库，`ops/mk_tables.py --table adaptation` 永远出空表
    （`ops/mk_tables.py` 末尾那条已知限制说的就是这件事）。

    这里补的是**声明值**，来源写在 `axes_source` 里，不假装是从记录里读出来的：
    * `set_version` / `reference_version` 取 `ops/freeze_v10` 的当前值 —— 适配 bundle 的通行证
      里记的 `frozen_manifest` / `reference_manifest` 就是在这两条轴上算的；
    * `protocol_version` 由 `results_db.protocol_by_run` **逐 run 反算**（读 `inject.json` 里
      这次真的投放了哪几件协议工件）。adapt 臂投的是 `geneprotocol_v1_adapt`，不是
      `geneprotocol_v1` 的三件，所以逐 run 反算出来的是显式的 `…@none` —— 那是事实，不是缺值。
    """
    from ops import freeze_v10 as FZ
    return {"set_version": FZ.SET_VERSION, "reference_version": FZ.REFERENCE_VERSION}


def ingest(records: list[dict], *, channel: str = "private") -> dict:
    """把结算记录收进结果库（幂等；内容不一致会抛，不覆盖）。"""
    from ops import results_db as DB
    if not records:
        return {"added": 0, "duplicate": 0, "keys": [], "note": "没有记录"}
    ax = axes_for({})
    per_run = DB.protocol_by_run(BATCH, RUNS_IN.parent)
    rows = [dict(r, **ax) for r in records]
    rows = DB.enrich(rows, batch=BATCH, protocol_version=DB.NO_PROTOCOL, channel=channel,
                     axes_source={"set_version": "declared:freeze_v10",
                                  "reference_version": "declared:freeze_v10",
                                  "protocol_version": "per_run:inject.json",
                                  "channel": "backfill:declared"},
                     protocol_versions=per_run)
    return DB.ingest(rows, batch=BATCH)


# ------------------------------------------------------------------ 30 行矩阵


def load_mutations() -> list[dict]:
    if not EXAMPLES_ROOT.is_dir():
        raise SystemExit(f"没有适配例根 {EXAMPLES_ROOT} —— 先跑 `python ops/adaptation_track.py --write`")
    out = []
    for d in sorted(p for p in EXAMPLES_ROOT.iterdir() if p.is_dir()):
        p = d / "mutation.json"
        if p.is_file():
            out.append(json.loads(p.read_text(encoding="utf-8")))
    return out


def matrix_rows(records: list[dict]) -> list[dict]:
    """每例一行：oracle 侧（左半）与真跑结局（右半）并列。**没有真跑就如实写「未运行」** ——
    这张表的完成定义是「30 例各有 oracle 与一次真运行」，缺哪一半就要一眼看得出缺的是哪一半。"""
    by_ex: dict[str, dict] = {}
    for r in records:                                  # 同一例多次运行取最后一条（run_id 排序）
        by_ex.setdefault(r["example_id"], r)
        if str(r.get("run_id") or "") >= str(by_ex[r["example_id"]].get("run_id") or ""):
            by_ex[r["example_id"]] = r
    rows = []
    for m in load_mutations():
        r = by_ex.get(m["example_id"])
        actual = (r or {}).get("outcome") or NOT_RUN
        rows.append({
            "example_id": m["example_id"], "level": m["level"], "stage": m["stage"],
            "source_task": m["source_task"], "family": m["family"], "site": m["site"],
            "mutation": m["what"], "recovery_route": (m.get("recovery") or {}).get("route"),
            "broken_validator_ok": (m.get("broken_validator") or {}).get("ok"),
            "expected_outcome": m.get("expected_outcome"),
            "run_id": (r or {}).get("run_id") or NOT_RUN,
            "actual_outcome": actual,
            "as_expected": (None if r is None else actual == m.get("expected_outcome")),
            "valid": (r or {}).get("valid"), "matched": (r or {}).get("matched"),
            "validator_rejections": (r or {}).get("validator_rejections"),
            "calls": (r or {}).get("calls"),
            "note": (r or {}).get("note") or "",
        })
    return rows


def matrix_md(rows: list[dict]) -> str:
    head = ("| # | level | 题（源） | 破坏 | 期望结局 | 实际结局 | calls |\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n")
    body = "".join(
        f"| {r['example_id']} | {r['level']} | {r['stage']} / {r['source_task']} | {r['mutation']} "
        f"| {r['expected_outcome']} | {r['actual_outcome']} "
        f"| {'—' if r['calls'] is None else r['calls']} |\n" for r in rows)
    n_run = sum(1 for r in rows if r["actual_outcome"] != NOT_RUN)
    return (f"# 适配赛道 {SET_ID}：oracle × 真跑 逐例对照（{len(rows)} 例）\n\n"
            f"oracle：{len(rows)} / {len(rows)}；真运行：{n_run} / {len(rows)}。\n\n" + head + body)


# ------------------------------------------------------------------ 出表


def write_all(records: list[dict], problems: list[str]) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    RIO.secure_dir(OUT)
    rows = matrix_rows(records)
    R.write_csv(rows, OUT / "oracle_matrix.csv", MATRIX_COLUMNS)
    (OUT / "oracle_matrix.md").write_text(matrix_md(rows), encoding="utf-8")

    # **四条版本轴先贴到每条记录上**（红队 W.rt finding 8）。`AdaptationResult.as_record`
    # 本来一条都不出，于是这张表此前**看不出它是在哪一版题面与哪一版参考轴上算出来的** ——
    # 与 `VERSIONS.md` §2 记作「一次真事故」的 m6_all 混轴表同形，而 Slip 与 S8 events
    # 的口径恰好在 1.0.14 / r1.0.21 这一版变过。`axes_for` 给的是**声明值**，
    # 来源写在结果库的 `axes_source` 里；`runner_version` / `image_digest` 适配记录里没有，
    # 按空值出（`to_latex` 写 `---`，CSV 留空），**不省掉整列**。
    ax = axes_for({})
    table = R.table_adaptation([dict(r, **ax) for r in records])
    R.write_csv(table, OUT / "table.csv", R.TABLE_ADAPTATION_COLUMNS)
    (OUT / "table.tex").write_text(R.to_latex(
        table, ("config_id", "arm", "level", "n", "first_pass", "repaired_pass",
                "correct_flag", "blocked", "failed", "resolved_rate", "as_expected_rate",
                "set_version", "reference_version"),
        caption=CAPTION + f"。轴：set_version={ax['set_version']}、"
                          f"reference_version={ax['reference_version']}"
                          "（声明值，来源 ops/freeze_v10）；runner_version / image_digest"
                          "适配记录里没有，表上写 ---",
        label="tab:adaptation"), encoding="utf-8")
    (OUT / "records.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    n_run = sum(1 for r in rows if r["actual_outcome"] != NOT_RUN)
    dist: dict[str, int] = {}
    for r in records:
        dist[r["outcome"]] = dist.get(r["outcome"], 0) + 1
    lines = [f"# 适配赛道 {SET_ID} 结算摘要", "",
             f"例：{len(rows)}；有 oracle：{len(rows)}；有真运行：{n_run}；结算到的 run：{len(records)}；"
             f"问题：{len(problems)}", "",
             "> **完成定义是「30 例各有 oracle 与一次真运行」，不是「都要通过」。** 结局分布如实报。",
             "",
             "> " + R.ADAPT_ORACLE_EXPOSURE_NOTE, "",
             "> " + RESCORE_NOTE, ""]
    if dist:
        lines += ["## 结局分布（如实报）", ""] + [f"- {k}: {v}" for k, v in sorted(dist.items())] + [""]
    else:
        lines += ["## 结局分布（如实报）", "",
                  "**没有任何真运行** —— 分布为空。这不是「零失败」。",
                  "先跑 `ops/reports/adapt/README.md` 里那串命令（出集 → 推送 → 真跑 → 结算）。", ""]
    for t in table:
        lines.append(f"- {t['config_id']} / {t['arm']} / {t['level']}: n={t['n']} "
                     f"resolved={t['resolved_rate']} as_expected={t['as_expected_rate']}")
    if problems:
        lines += ["", "## 没结算的 run", ""] + [f"- {p}" for p in problems]
    (OUT / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    RIO.secure_tree(OUT)
    return OUT


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("matrix", "score"))
    ap.add_argument("--remote", default=None, help="f02 上的 runs 根（含各 run 目录）")
    ap.add_argument("--no-pull", action="store_true")
    ap.add_argument("--supersede-old", default=None, metavar="BY",
                    help="收库之前把库里**已有**的适配行标成 superseded（值 = 取代它的参考版本号，"
                         "如 r1.0.22）。旧行不删 —— 「曾经发表过偏低那版」要查得到（N-645）")
    ap.add_argument("--ingest", action="store_true",
                    help="结算之后把记录收进结果库（`ops/results_db.py`），"
                         "这样 `ops/mk_tables.py --table adaptation` 出得来真表")
    a = ap.parse_args(argv)
    records: list[dict] = []
    problems: list[str] = []
    if a.cmd == "score":
        if not a.no_pull:
            if not a.remote:
                raise SystemExit("--remote 必填（或 --no-pull）")
            pull(a.remote)
        records, problems = score_all(RUNS_IN)
    out = write_all(records, problems)
    if a.supersede_old:
        from ops import results_db as DB
        s = DB.supersede(batch=BATCH, by=a.supersede_old, track="adaptation",
                         note=("X2（2026-09-11）重算：S6 参考解的 provenance[0].artifact_id 曾是占位串，"
                               "判据罚了照规则做的那一方；r1.0.22 修根因后重算，未重跑，真 API 0 次。"
                               "本行是**重算前**那一版（签字包 v1.0.14 / r1.0.21 里发表的那张表）。"))
        print(f"[库] 旧行标 superseded：{s['marked']} 行 @ {s['at']}")
    if a.ingest:
        try:
            r = ingest(records)
            print(f"[库] added={r['added']} duplicate={r['duplicate']}")
        except Exception as e:                        # noqa: BLE001  收不进库不该毁掉已经出好的表
            print(f"[库] 收不进去（表已经出好了，不影响）：{type(e).__name__}: {e}")
    print((out / "summary.md").read_text(encoding="utf-8"))
    print(f"→ {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
