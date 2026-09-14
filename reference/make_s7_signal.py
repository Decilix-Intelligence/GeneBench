# -*- coding: utf-8 -*-
"""生成 S7 的专用信号夹具 `s7_dedicated_signal_v1`（裁定 N-84，2026-09-05）。

裁定原文：`s7_dedicated_signal_v1` = 冻结 ε 面板的 `signal` 列 ——
**ε 就是在这个信号上标定的，换信号 ε 失效**。所以这份夹具不是"随便挑一个因子"，
它是 ε 的一部分；抽取过程必须可复现、可核对。

产出（每道 S7 题的任务目录下）：

* `work/signal.parquet` —— 三列 `(date, code, signal)`，`date` 是 `YYYY-MM-DD` 字符串，
  `code` 是契约 §1 的 `SH600000` 形态；
* `work/signal.meta.json` —— `{stage, artifact_id, sha256, max_date, rows, source}`，
  oracle 的 `provenance` 从这里抄（`solve.py` 的 ⑧）。

**为什么 `stage` 填 `S3`**：schema 只认 `S1..S8`（`ops/specs/artifact_schema/v1.0/S7.json`），
而这份产物的形态是"因子值序列"，那是 S3 的形态。它**不是**任何一道已发布 S3 题的 gold
（N-47 记着「明确不复用任何 S5 题的 gold」，同理不复用 S3 的）——
`artifact_id` 用 `s7_dedicated_signal_v1` 把这件事写在脸上。

**默认不动 `task.yaml`**：题面 `inputs[].sha256` 现在是 `null`，填上它是**任务集面的改动**，
要跟着那次夹具生成一起推版本（裁定：夹具生成那次正当推任务集版本）。
所以填 sha 要显式 `--write-taskyaml`，不给就只落夹具与 meta。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import genebench_config as cfg                                        # noqa: E402

SIGNAL_ID = "s7_dedicated_signal_v1"
SIGNAL_STAGE = "S3"
#: 唯一来源。**不接受调用方指定** —— 换了源，ε 就不再是这份 gold 的 ε。
SOURCE_PANEL = cfg.SNAPSHOTS / "v1" / "epsilon" / "bt_input_csi300_v2.parquet"
#: 题面 `inputs` 里声明的两个路径，逐字对齐（`ops/test_s7_signal_fixture.py` 盯着）。
SIGNAL_REL = "work/signal.parquet"
META_REL = "work/signal.meta.json"
TASK_SET = "v1.0-smoke"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def extract(source: Path = SOURCE_PANEL) -> pd.DataFrame:
    """从冻结 ε 面板抽 `(date, code, signal)`。丢掉 signal 为空的行。

    丢空行不丢信息：下游是按 `(date, code)` 左连接，"不在夹具里"与"在夹具里但为空"
    连接之后都是 NaN。留着只是让夹具大一倍。
    """
    df = pd.read_parquet(source, columns=["date", "code", "signal"])
    out = df[df["signal"].notna()].copy()
    out["date"] = out["date"].astype(str)
    out["code"] = out["code"].astype(str)
    return out.sort_values(["date", "code"]).reset_index(drop=True)


def s7_task_dirs(set_id: str = TASK_SET) -> list[Path]:
    root = cfg.GENEBENCH_ROOT / "reference" / "tasks" / set_id
    return sorted(p for p in root.glob("s7-*") if (p / "task.yaml").exists())


def declared_inputs(task_dir: Path) -> list[dict]:
    doc = yaml.safe_load((task_dir / "task.yaml").read_text(encoding="utf-8"))
    return list(doc.get("inputs") or [])


def write_fixture(task_dir: Path, sig: pd.DataFrame) -> dict:
    """把夹具与 meta 落到一道题的任务目录下，返回 meta。"""
    inputs = declared_inputs(task_dir)
    want = {SIGNAL_REL, META_REL}
    got = {str(i.get("path", "")) for i in inputs}
    if not want <= got:
        raise ValueError(f"{task_dir.name} 的题面 inputs 是 {sorted(got)}，"
                         f"缺 {sorted(want - got)} —— 夹具不许落到题面没声明的路径上")
    origins = {str(i.get("path")): str(i.get("origin", "")) for i in inputs}
    if origins.get(SIGNAL_REL) != f"signal:{SIGNAL_ID}":
        raise ValueError(f"{task_dir.name} 声明的 origin 是 {origins.get(SIGNAL_REL)!r}，"
                         f"不是 signal:{SIGNAL_ID}")

    work = cfg.create_dir(task_dir / "work")
    p = work / "signal.parquet"
    sig.to_parquet(p, index=False, compression="zstd")
    p.chmod(0o600)
    meta = {
        "stage": SIGNAL_STAGE,
        "artifact_id": SIGNAL_ID,
        "sha256": sha256_file(p),
        "max_date": str(sig["date"].max()),
        "min_date": str(sig["date"].min()),
        "rows": int(len(sig)),
        "source": str(SOURCE_PANEL),
        "source_sha256": sha256_file(SOURCE_PANEL),
    }
    m = work / "signal.meta.json"
    m.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    m.chmod(0o600)
    meta["meta_sha256"] = sha256_file(m)
    return meta


def write_params(shas: dict) -> int:
    """把 sha 写回 **params**（题面的源头）。走 `make_fixtures.write_params_shas` ——
    两处各写一份"怎么回填"的逻辑，迟早会漂开一处。"""
    from reference.make_fixtures import write_params_shas
    return write_params_shas(shas)


def write_taskyaml(task_dir: Path, meta: dict) -> None:
    """把 sha 填进题面 `inputs`。**这是任务集面的改动**，跟着夹具那次一起推版本。"""
    f = task_dir / "task.yaml"
    doc = yaml.safe_load(f.read_text(encoding="utf-8"))
    for item in doc.get("inputs") or []:
        if item.get("path") == SIGNAL_REL:
            item["sha256"] = meta["sha256"]
        elif item.get("path") == META_REL:
            item["sha256"] = meta["meta_sha256"]
    head = f.read_text(encoding="utf-8").split("\n", 1)[0]      # 保留首行的 gold_token 注释
    body = yaml.safe_dump(doc, allow_unicode=True, sort_keys=False)
    f.write_text(f"{head}\n{body}" if head.startswith("#") else body, encoding="utf-8")


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--set-id", default=TASK_SET)
    ap.add_argument("--write-params", action="store_true",
                    help="把 sha 写回 params（题面的源头；任务集面改动，要跟着推版本）")
    a = ap.parse_args(argv)

    sig = extract()
    dirs = s7_task_dirs(a.set_id)
    if not dirs:
        raise SystemExit(f"{a.set_id} 下没有 s7-* 任务目录")
    rows, shas = [], {}
    for d in dirs:
        meta = write_fixture(d, sig)
        shas[d.name] = {SIGNAL_REL: meta["sha256"], META_REL: meta["meta_sha256"]}
        rows.append({"task": d.name, **{k: meta[k] for k in
                                        ("sha256", "rows", "min_date", "max_date")}})
    distinct = {r["sha256"] for r in rows}          # 名字别再用 shas —— 它已经是回填表了
    if len(distinct) != 1:
        raise SystemExit(f"同一份信号在不同题里 sha 不同：{distinct} —— 写出过程不确定")
    n_sha = write_params(shas) if a.write_params else 0
    print(json.dumps({"signal_id": SIGNAL_ID, "tasks": rows,
                      "params_sha_written": n_sha}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
