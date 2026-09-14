# -*- coding: utf-8 -*-
"""**真 API 用量统计**（W-0，2026-09-06）。

在此之前「我们一共打了多少次真 API」这个问题只有一个答案：**人工记账**。
2026-09-06 签字前那个「累计约 1 700 次」就是手记的 —— 它不可复核、不可复现，
也不区分批次与臂。本模块把它换成机器统计。

**数据源**：f02 每个 run 的 `log/llm_log.jsonl`，`decision == "allow"` 计一次。
拒掉的（预算耗尽、越权、非白名单主机）**不计**：它们没有真的打到上游。

**布局**（真机实测）：``<run 根>/<batch>/runs/runs/<run_id>/log/llm_log.jsonl``
—— `--run-root .../m6/runs` 传给 runner，runner 又在下面建了一层 `runs/`。
所以这里对 ``<batch>/runs`` **递归**找 `log/llm_log.jsonl`，不写死层数：
层数变了就统计不到，而「统计不到」看起来和「这批没跑」一模一样。

`run_id` 的形状是 ``<task>.<arm>.<config_id>.rNN``，切片键从名字解析，
**不去读 run 里别的文件** —— 少一处对目录内容的依赖，多一分可离线复算。

**为什么不把 llm_log 整个拉回 f01**：`request_head` 里有原样的请求头。
统计只需要计数，把带 header 的原文搬到数据面是白拿一份风险（红线 3）。
所以远端只跑**本文件自己**（`--emit-summaries`），回来的是逐 run 的计数摘要。

用法
----
    # 统计（在 f01 跑；会 scp 本文件到 f02 执行后删掉）
    /data/shared/genebench/env/bin/python ops/api_usage.py

    # 只统计某几个 batch
    …/python ops/api_usage.py --batches m6 m6b

    # 离线/夹具：统计一棵本地目录（不 ssh）
    …/python ops/api_usage.py --local-root /path/to/run_root

    # 在 f02 上被调用的那一半（不用手工跑）
    python3 api_usage.py --emit-summaries --root /data/genebench_runner

输出：``<out-dir>/api_usage.json`` + ``<out-dir>/api_usage.md``
（默认 `out-dir` = `$GB/scratch/api_usage`，**不写进仓库** —— 它是产物不是代码）。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

#: 执行面 run 根的默认位置。
DEFAULT_F02_ROOT = "/data/genebench_runner"
DEFAULT_F02 = os.environ.get("GENEBENCH_F02", "ljn@192.168.1.219")
DEFAULT_OUT = "/data/shared/genebench/scratch/api_usage"
SSH_OPTS = ["-o", "ConnectTimeout=120"]

#: 这一行**每次都印**。机器统计与人工记账并存的时候，读表的人必须知道以哪个为准。
HISTORY_LINE = (
    "历史口径：2026-09-06 签字前人工记账累计约 1 700 次；"
    "本表为机器统计，以本表为准。")

LOG_NAME = "llm_log.jsonl"


# ---------------------------------------------------------------------------
# 纯函数（夹具测的就是这几个）
# ---------------------------------------------------------------------------
def summarize_lines(lines) -> dict:
    """一份 `llm_log.jsonl` 的摘要。

    坏行**记进 `malformed` 而不是跳过**：静默跳过的表现是「统计出来的数偏小」，
    而偏小和「这批调用少」在表上长得一模一样。
    """
    out = {"allow": 0, "other": 0, "malformed": 0, "by_decision": {},
           "total_tokens": 0, "first_ts": None, "last_ts": None}
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            rec = json.loads(raw)
        except ValueError:
            out["malformed"] += 1
            continue
        if not isinstance(rec, dict):
            out["malformed"] += 1
            continue
        d = rec.get("decision")
        key = d if isinstance(d, str) else "<missing>"
        out["by_decision"][key] = out["by_decision"].get(key, 0) + 1
        if d == "allow":
            out["allow"] += 1
            usage = rec.get("usage")
            if isinstance(usage, dict) and isinstance(usage.get("total_tokens"), int):
                out["total_tokens"] += usage["total_tokens"]
        else:
            out["other"] += 1
        ts = rec.get("ts")
        if isinstance(ts, str):
            if out["first_ts"] is None or ts < out["first_ts"]:
                out["first_ts"] = ts
            if out["last_ts"] is None or ts > out["last_ts"]:
                out["last_ts"] = ts
    return out


def parse_run_id(run_id: str) -> dict:
    """``<task>.<arm>.<config_id>.rNN`` → 切片键。形状不对就**如实记 None**。

    不猜：一个认不出来的 run 名要在表上看得见（`config_id: null`），
    而不是被塞进某个看起来合理的分组里。
    """
    parts = run_id.split(".")
    if len(parts) == 4 and parts[3].startswith("r"):
        return {"task_id": parts[0], "arm": parts[1], "config_id": parts[2],
                "rep": parts[3]}
    return {"task_id": None, "arm": None, "config_id": None, "rep": None}


def find_run_logs(root, batches=None) -> list[dict]:
    """``<root>/<batch>/runs/**/log/llm_log.jsonl``。返回按 (batch, run_id) 排序的清单。

    只认 `<batch>/runs` 下的东西 —— `fwprobe/` 那种一次性探针不是 run，
    把它算进「每 run 预算」的表里会让口径失真。
    """
    base = Path(root)
    out: list[dict] = []
    if not base.is_dir():
        return out
    for bdir in sorted(p for p in base.iterdir() if p.is_dir()):
        if batches and bdir.name not in batches:
            continue
        runs_root = bdir / "runs"
        if not runs_root.is_dir():
            continue
        for log in sorted(runs_root.rglob(f"log/{LOG_NAME}")):
            run_dir = log.parent.parent
            out.append({"batch": bdir.name, "run_id": run_dir.name,
                        "path": str(log)})
    return sorted(out, key=lambda r: (r["batch"], r["run_id"]))


def collect_local(root, batches=None) -> list[dict]:
    """逐 run 摘要（在**有 log 文件的那台机器上**跑）。"""
    recs = []
    for item in find_run_logs(root, batches):
        try:
            with open(item["path"], encoding="utf-8", errors="replace") as fh:
                s = summarize_lines(fh)
            err = None
        except OSError as e:                                    # pragma: no cover
            s = summarize_lines([])
            err = f"{type(e).__name__}: {e}"
        rec = {"batch": item["batch"], "run_id": item["run_id"]}
        rec.update(parse_run_id(item["run_id"]))
        rec.update(s)
        rec["error"] = err
        recs.append(rec)
    return recs


def aggregate(records) -> dict:
    """按 batch / config_id / arm 分组 + 总计。"""
    def _group(key):
        g: dict = {}
        for r in records:
            k = r.get(key)
            k = "<未知>" if k is None else k
            cell = g.setdefault(k, {"runs": 0, "allow": 0, "other": 0,
                                    "malformed": 0, "total_tokens": 0})
            cell["runs"] += 1
            for f in ("allow", "other", "malformed", "total_tokens"):
                cell[f] += r.get(f, 0)
        return dict(sorted(g.items()))

    total = {"runs": len(records), "allow": 0, "other": 0, "malformed": 0,
             "total_tokens": 0}
    for r in records:
        for f in ("allow", "other", "malformed", "total_tokens"):
            total[f] += r.get(f, 0)
    return {"history_note": HISTORY_LINE,
            "by_batch": _group("batch"),
            "by_config_id": _group("config_id"),
            "by_arm": _group("arm"),
            "total": total,
            "runs": records}


def _table(title: str, group: dict) -> list[str]:
    out = [f"### 按 {title}", "",
           "| " + title + " | run 数 | allow（真调用） | 非 allow | 坏行 | tokens |",
           "|---|---:|---:|---:|---:|---:|"]
    for k, v in group.items():
        out.append(f"| `{k}` | {v['runs']} | **{v['allow']}** | {v['other']} | "
                   f"{v['malformed']} | {v['total_tokens']:,} |")
    out.append("")
    return out


def render_markdown(agg: dict) -> str:
    t = agg["total"]
    lines = [
        "# 真 API 用量（机器统计）", "",
        f"> {agg['history_note']}", "",
        f"**总计：{t['allow']} 次真调用**（{t['runs']} 个 run；"
        f"非 allow {t['other']} 条；坏行 {t['malformed']} 条；"
        f"tokens {t['total_tokens']:,}）。", "",
        "口径：f02 各 run 的 `log/llm_log.jsonl` 里 `decision == \"allow\"` 计一次。"
        "被拒的不计 —— 它们没有真的打到上游。", "",
    ]
    lines += _table("batch", agg["by_batch"])
    lines += _table("config_id", agg["by_config_id"])
    lines += _table("arm", agg["by_arm"])
    lines += ["### 逐 run", "",
              "| batch | run_id | allow | 非 allow | tokens |",
              "|---|---|---:|---:|---:|"]
    for r in agg["runs"]:
        lines.append(f"| {r['batch']} | `{r['run_id']}` | **{r['allow']}** | "
                     f"{r['other']} | {r['total_tokens']:,} |")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 取数：远端（f02）与本地
# ---------------------------------------------------------------------------
def collect_remote(f02: str, root: str, batches=None) -> list[dict]:
    """把**本文件**送到 f02 跑一遍 `--emit-summaries`，只把计数摘要拿回来。

    不 `cat` 原始日志：`request_head` 里是原样的请求头，搬到数据面是白拿一份风险。
    也不内联 heredoc 进 ssh（踩过三次）—— 先 scp 文件，再执行。
    """
    me = Path(__file__).resolve()
    remote = f"/tmp/gb_api_usage_{os.getpid()}.py"
    subprocess.run(["scp", "-q", *SSH_OPTS, str(me), f"{f02}:{remote}"], check=True)
    try:
        cmd = ["python3", remote, "--emit-summaries", "--root", root]
        if batches:
            cmd += ["--batches", *batches]
        p = subprocess.run(["ssh", *SSH_OPTS, f02, " ".join(cmd)],
                           check=True, capture_output=True, text=True)
    finally:
        subprocess.run(["ssh", *SSH_OPTS, f02, f"rm -f {remote}"], check=False)
    return json.loads(p.stdout)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="真 API 用量统计（llm_log.jsonl 的 allow 计数）")
    ap.add_argument("--emit-summaries", action="store_true",
                    help="在**有日志的机器上**跑：把逐 run 摘要打成 JSON 到 stdout")
    ap.add_argument("--root", default=DEFAULT_F02_ROOT, help="run 根（f02 侧）")
    ap.add_argument("--local-root", default=None,
                    help="统计一棵本地目录，不 ssh（离线复算/夹具用）")
    ap.add_argument("--f02", default=DEFAULT_F02)
    ap.add_argument("--batches", nargs="*", default=None)
    ap.add_argument("--out-dir", default=DEFAULT_OUT)
    a = ap.parse_args(argv)

    if a.emit_summaries:
        json.dump(collect_local(a.root, a.batches), sys.stdout, ensure_ascii=False)
        return 0

    if a.local_root:
        records = collect_local(a.local_root, a.batches)
        source = f"本地 {a.local_root}"
    else:
        records = collect_remote(a.f02, a.root, a.batches)
        source = f"{a.f02}:{a.root}"

    agg = aggregate(records)
    agg["source"] = source
    out = Path(a.out_dir)
    out.mkdir(mode=0o700, parents=True, exist_ok=True)
    jp = out / "api_usage.json"
    mp = out / "api_usage.md"
    jp.write_text(json.dumps(agg, ensure_ascii=False, indent=1), encoding="utf-8")
    mp.write_text(render_markdown(agg), encoding="utf-8")
    for p in (jp, mp):
        try:
            os.chmod(p, 0o600)
        except OSError:                                         # pragma: no cover
            pass
    print(f"来源：{source}")
    print(f"**总计 {agg['total']['allow']} 次真调用**"
          f"（{agg['total']['runs']} 个 run）")
    print(HISTORY_LINE)
    print(f"写了 {jp}\n写了 {mp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
