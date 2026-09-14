#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""卡 Y2（用户裁定 ⑮ ⑰，2026-09-10）：`genebench` 命令行 —— **结果导出 / 合并** 与 **版本锁**。

    $PY ops/genebench_cli.py axes                     # 四条轴现值 vs RELEASE_MANIFEST（版本锁自检）
    $PY ops/genebench_cli.py export --out <目录> [--filter batch=m6 ...]
    $PY ops/genebench_cli.py merge  <结果包.tar.gz> [--dry]

为什么要有它
------------
到今天为止，「一次结算的结果」只活在**跑它的那台机器**上：结果库是
`$GENEBENCH_ROOT/results/v1/results.jsonl`，一台机器一份。外部用户在自己的机器上跑完
GeneBench，想把读数拼回来 —— 没有任何一条路。拷 `results.jsonl` 过去是最糟的那条：
两份文件行与行之间没有主键约束，拼完之后**没有人知道两边跑的是不是同一套题**
（`set_version` / `reference_version` 不同的两批读数并排放在一张表上，正是红队 5.1
finding E1 那一类：表上看不出来，结论是错的）。

于是两件事：

* **⑮ export / merge**：结果包 = 结果库切片 + run 清单 + **四条版本轴** + **机器标识**，
  自包含、带 sha256；`merge` **先校验四轴一致，不一致当场拒**并列出分歧，一致才合并。
* **⑰ 版本锁**：任一轴与 `RELEASE_MANIFEST.json` 不一致 → **包拒绝运行**。
  自检在入口处跑（本命令的每个子命令、`ops/run_joblist.py`），退非零并说清
  **哪条对不上、怎么修**。

四条轴在这里分两层（合并时按两层分别判）
--------------------------------------
* **装置轴** `set_version` / `reference_version`（各带 root hash）：回答「两台机器跑的是不是
  同一套题、同一套 gold 算法」。两台机器不同 → **拒**。这是 ⑮ 点名的「轴不一致即拒」。
* **逐 run 轴** `protocol_version` / `channel`：**不要求跨包相同** —— 裸臂的协议轴恒为
  `geneprotocol_v1@none`，两条通道也都是合法的运行。要求的是：每条记录自带，
  且落在包 MANIFEST 登记的取值集合里（**包不能对自己撒谎**）。

主键与去重
----------
`(machine_id, batch, run_id)`（`ops/results_db.py::key_of`）。新的 `run_id` 末尾自带
`@<machine_id>`（`runner.inject.run_id`，裁定 ⑮），所以两台机器按同一份清单跑出来的 run
天然不撞。**同主键内容不同 → 报错不覆盖**（`results_db.ingest` 本来就是这条纪律）。

**既有 run_id 不追溯**：2026-09-10 之前的记录没有机器段，合并时**不给它们盖一个机器标识** ——
那是拿今天的事实追认昨天的运行。它们的主键仍是 `(batch, run_id)`；两台机器上真的出现
一对同名旧记录且内容不同时，`merge` 会报「同主键内容不同」并**停下来**，由人裁定。

退出码
------
0 一切正常；2 用法 / 读写错；3 **轴不一致**（版本锁或合并的四轴校验）；
4 合并被拒（同主键内容不同）；5 结果包完整性坏了（sha256 对不上 / 缺件）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import genebench_config as cfg                              # noqa: E402
from ops import report_io as RIO                            # noqa: E402
from ops import results_db as DB                            # noqa: E402

SCHEMA_VERSION = 1
PACKAGE_KIND = "genebench-results-package"
#: 结果包里的三件。缺一即 5（完整性）。
PACKAGE_FILES: tuple[str, ...] = ("MANIFEST.json", "results.jsonl", "runs.json")

#: 版本锁比的**装置轴**四个字段（两条轴各带一个 root hash —— 只比版本号的话，
#: 「号没动、内容动了」这一类漂移看不见，而那正是重冻要解决的问题）。
LOCK_FIELDS: tuple[str, ...] = ("set_version", "set_root", "reference_version", "reference_root")

#: `RELEASE_MANIFEST.json` 的落点。环境变量只**换路径**（发布包解开之后清单不在仓库里），
#: **不是开关** —— 给了一个不存在的路径照样拒。
RELEASE_MANIFEST_ENV = "GENEBENCH_RELEASE_MANIFEST"


class CliError(RuntimeError):
    """用法 / 读写错（退 2）。"""


class AxisError(RuntimeError):
    """四条轴对不上（退 3）。`divergences` 里逐条带 declared / actual / 怎么修。"""

    def __init__(self, message: str, divergences: list[dict]):
        super().__init__(message)
        self.divergences = divergences


class IntegrityError(RuntimeError):
    """结果包坏了（退 5）。"""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------------ ⑰ 版本锁

def release_manifest_path() -> Path:
    v = (os.environ.get(RELEASE_MANIFEST_ENV) or "").strip()
    return Path(v) if v else (_REPO / "RELEASE_MANIFEST.json")


def axes_now(repo: Path | str | None = None) -> dict:
    """**这个装置今天实际是哪四条轴**。取自两份冻结清单 + `ops/freeze_v10.py` 的代码常量。

    代码常量与盘上清单分开取，是因为它们会各走各的：有人改了 `SET_VERSION` 却没
    `freeze_v10.py --write`，两个值就分家 —— 那种装置「现在是哪一版」没有答案，
    必须当成一条分歧报出来，而不是挑一个用。
    """
    r = Path(repo) if repo is not None else _REPO
    ts = json.loads((r / "ops" / "manifests" / "v1.0-smoke.json").read_text(encoding="utf-8"))
    rf = json.loads((r / "ops" / "manifests" / "v1.0-smoke.reference.json").read_text(encoding="utf-8"))
    out = {
        "set_version": ts.get("set_version"),
        "set_root": ts.get("root"),
        "reference_version": rf.get("reference_version"),
        "reference_root": None,
        "channels": list(cfg.CHANNELS),
        "code_set_version": None,
        "code_reference_version": None,
        "protocol_version_in_repo": None,
    }
    try:
        from ops import freeze_v10 as F                     # 只为取两个常量与 reference_root
        out["reference_root"] = F.reference_root(rf)
        out["code_set_version"] = F.SET_VERSION
        out["code_reference_version"] = F.REFERENCE_VERSION
    except Exception as e:                                   # pragma: no cover - 冻结模块坏了是另一类事故
        out["reference_root"] = f"（算不出：{type(e).__name__}: {e}）"
    try:
        out["protocol_version_in_repo"] = DB.protocol_version_repo()
    except Exception:                                        # 协议清单缺件 —— 那条轴逐 run 反算，这里只是参考
        out["protocol_version_in_repo"] = None
    return out


def axes_declared(manifest: Path | str | None = None) -> dict:
    p = Path(manifest) if manifest is not None else release_manifest_path()
    if not p.is_file():
        raise AxisError(
            f"没有发布清单 {p} —— 版本锁没有可比的一方。\n"
            f"  怎么修：在仓库里跑 `{cfg.PYTHON} ops/mk_release_manifest.py` 生成；"
            f"发布包解开之后用 {RELEASE_MANIFEST_ENV}=<包内的 RELEASE_MANIFEST.json> 指过去。",
            [{"axis": "RELEASE_MANIFEST", "declared": None, "actual": str(p),
              "why": "清单文件不存在", "fix": f"{cfg.PYTHON} ops/mk_release_manifest.py"}])
    m = json.loads(p.read_text(encoding="utf-8"))
    ax = dict(m.get("axes") or {})
    ax["_manifest_path"] = str(p)
    return ax


def axis_divergences(declared: dict, actual: dict) -> list[dict]:
    """两边比一遍。空 = 一致。**每条分歧带「怎么修」** —— 只说不一样等于没说。"""
    out: list[dict] = []
    fix_freeze = (f"两条轴各写一次（N-111）：`{cfg.PYTHON} ops/freeze_v10.py --write` 与 "
                  f"`{cfg.PYTHON} ops/freeze_v10.py --write-reference`")
    fix_manifest = f"重新生成发布清单：`{cfg.PYTHON} ops/mk_release_manifest.py`"
    for f in LOCK_FIELDS:
        d, a = declared.get(f), actual.get(f)
        if d != a:
            out.append({
                "axis": f, "declared": d, "actual": a,
                "why": "RELEASE_MANIFEST 里声明的这条轴与本装置现算的值不同 —— "
                       "发布清单是对外的那句「这个包是哪一版」，对不上就不能跑。",
                "fix": f"{fix_manifest}（清单陈旧时）；本装置才是陈的就重冻：{fix_freeze}",
            })
    for code_key, disk_key in (("code_set_version", "set_version"),
                               ("code_reference_version", "reference_version")):
        c, d = actual.get(code_key), actual.get(disk_key)
        if c is not None and c != d:
            out.append({
                "axis": code_key, "declared": d, "actual": c,
                "why": f"`ops/freeze_v10.py` 的代码常量是 {c}，盘上的冻结清单写的是 {d} —— "
                       f"改了常量没重冻。这个装置「现在是哪一版」没有答案。",
                "fix": fix_freeze,
            })
    return out


def check_release_axes(*, repo: Path | str | None = None,
                       manifest: Path | str | None = None) -> dict:
    """版本锁：返回 `{"ok":bool, "declared":…, "actual":…, "divergences":[…]}`。**不抛**。"""
    actual = axes_now(repo)
    try:
        declared = axes_declared(manifest)
        div = axis_divergences(declared, actual)
    except AxisError as e:
        declared, div = {}, e.divergences
    return {"ok": not div, "declared": declared, "actual": actual, "divergences": div}


def format_divergences(div: list[dict], *, where: str) -> str:
    lines = [f"[版本锁] {where}：四条轴与 RELEASE_MANIFEST 对不上，**拒绝运行**（{len(div)} 条分歧）"]
    for d in div:
        lines.append(f"  · {d['axis']}：清单说 {d['declared']!r}，本装置现算 {d['actual']!r}")
        lines.append(f"      为什么拦：{d['why']}")
        lines.append(f"      怎么修：{d['fix']}")
    lines.append(f"  （自检本身：`{cfg.PYTHON} ops/genebench_cli.py axes`）")
    return "\n".join(lines)


def assert_release_axes(*, where: str, repo: Path | str | None = None,
                        manifest: Path | str | None = None) -> dict:
    """入口自检。不一致 → `AxisError`（调用方退 3）。"""
    r = check_release_axes(repo=repo, manifest=manifest)
    if not r["ok"]:
        raise AxisError(format_divergences(r["divergences"], where=where), r["divergences"])
    return r


# ------------------------------------------------------------------ ⑮ export

def local_machine() -> dict:
    """这台机器的标识。算法写在 `runner/inject.py::machine_fingerprint` 的注释里。"""
    from runner.inject import machine_info                  # 惰性：导出不需要执行面的其它东西
    return machine_info()


def record_axes(rec: dict) -> dict:
    return {ax: rec.get(ax) for ax in DB.AXES}


def assert_records_carry_axes(records: Iterable[dict]) -> None:
    """⑰ 的后半句：**导出的每条结果带四轴**。缺一条就不导 —— 导出去也是不可比的读数。"""
    bad = []
    for r in records:
        miss = [ax for ax in DB.AXES if r.get(ax) in (None, "")]
        if miss:
            bad.append(f"{DB.key_of(r)}: 缺 {miss}")
    if bad:
        raise CliError("这些记录没带齐四条版本轴，不能导出（结果库本来就拦这个，"
                       "库里出现它们说明是手改进去的）：\n  " + "\n  ".join(bad[:20]))


def runs_index(records: list[dict]) -> list[dict]:
    """run 清单：一条 run 一行的索引。**权威内容在 `results.jsonl`**，这张表是给人看的。"""
    out = []
    for r in records:
        out.append({
            "machine_id": DB.machine_of(r),
            "batch": r.get("batch"),
            "run_id": r.get("run_id"),
            "track": r.get("track") or DB.track_of(r),
            "task_id": r.get("task_id") or r.get("example_id"),
            "config_id": r.get("config_id"),
            "arm": r.get("arm"),
            "seed": r.get("seed"),
            "run_status": r.get("run_status") or r.get("outcome"),
            "validity": r.get("validity") or r.get("valid"),
            "l3_pass": r.get("l3_pass"),
            "axes": record_axes(r),
            "ingested_at": r.get("_ingested_at"),
        })
    return out


def package_stem(machine_id: str, at: str | None = None) -> str:
    ts = (at or _now()).replace(":", "").replace("-", "")
    return f"genebench-results-{machine_id}-{ts}"


def record_axis_divergences(records: Iterable[dict], actual: dict) -> list[dict]:
    """**包里的记录是不是这个装置这一版跑出来的**。

    记录只带版本号（`set_version` / `reference_version`），两个 root hash 只有装置有 ——
    所以「这个包的四条轴」这句话，只有在记录的版本号与装置现值相同时才说得出口。
    不同 → 默认**不导**（`--archive` 例外，见 :func:`export`）。
    """
    out: list[dict] = []
    seen: set[tuple] = set()
    for r in records:
        for key in ("set_version", "reference_version"):
            got, want = r.get(key), actual.get(key)
            if got != want and (key, got) not in seen:
                seen.add((key, got))
                out.append({
                    "axis": f"record:{key}", "declared": want, "actual": got,
                    "why": f"切片里有 {key}={got!r} 的记录，而本装置现在是 {want!r} —— "
                           f"这些读数不是这一版跑出来的，它们的 root hash 本装置根本不知道。",
                    "fix": "要么只导本版的记录（--filter），要么显式导**归档包** `--archive`"
                           "（包里会写明 root 未知，合并端也必须显式 --archive）。",
                })
    return out


def build_package(records: list[dict], *, out_dir: Path, machine: dict,
                  selection: dict, repo: Path | str | None = None,
                  label: str = "", at: str | None = None, archive: bool = False) -> dict:
    """切片 → 自包含结果包（`.tar.gz` + 同名 `.sha256`）。返回 MANIFEST 的内容 + 落点。"""
    assert_records_carry_axes(records)
    stamp = at or _now()
    out_dir = Path(out_dir)
    RIO.secure_dir(out_dir)
    stem = package_stem(machine["machine_id"], stamp)
    work = out_dir / stem
    if work.exists():
        shutil.rmtree(work)
    RIO.secure_dir(work)

    (work / "results.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
                for r in records), encoding="utf-8")
    RIO.write_json(work / "runs.json", runs_index(records))

    axes = axes_now(repo)
    seen_set = sorted({str(r.get("set_version")) for r in records})
    seen_ref = sorted({str(r.get("reference_version")) for r in records})
    drift = record_axis_divergences(records, axes)
    #: 归档包：记录不是本装置这一版跑出来的。**两个 root 写 None** —— 装置的 root
    #: 描述的不是这些记录，把它盖上去就是拿今天的指纹追认昨天的运行。
    pkg_axes = {f: axes.get(f) for f in LOCK_FIELDS}
    if archive and drift:
        pkg_axes = {"set_version": seen_set[0] if len(seen_set) == 1 else None, "set_root": None,
                    "reference_version": seen_ref[0] if len(seen_ref) == 1 else None,
                    "reference_root": None}
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "kind": PACKAGE_KIND,
        "generated_by": "ops/genebench_cli.py export",
        "exported_at": stamp,
        "label": label,
        #: **机器标识**：谁导出的 + 包里的记录分别是谁跑的（合并之后一个包里可以有多台机器）。
        "machine": machine,
        "record_machines": _count(DB.machine_of(r) or "（未知：run_id 里没有机器段）"
                                  for r in records),
        #: **四条轴**：合并时逐条比这四个。常规包 = 导出装置现值（记录与它逐条相符，
        #: 由 `record_axis_divergences` 保证）；归档包 = 记录自己的版本号 + root 未知。
        "axes": pkg_axes,
        #: 归档包（`--archive`）：装的是**另一版**跑出来的读数。合并端必须也显式 `--archive`，
        #: 而且合进去也不会变得可比 —— 出表那一步照旧按混轴拒绝（`mk_tables`）。
        "archive": bool(archive and drift),
        #: 导出这台机器当时的装置轴（归档包里它与 `axes` 不同；常规包里逐字相同）。
        "installation_axes": {f: axes.get(f) for f in LOCK_FIELDS},
        #: **逐 run 轴**：包里实际出现过的取值。合并时校验「每条记录都落在这里面」。
        "run_axes": {
            "set_version": seen_set,
            "reference_version": seen_ref,
            "protocol_version": sorted({str(r.get("protocol_version")) for r in records}),
            "channel": sorted({str(r.get("channel")) for r in records}),
        },
        "mixed_axes": DB.mixed_axes(records),
        "selection": selection,
        "counts": {
            "n_records": len(records),
            "by_batch": _count(str(r.get("batch")) for r in records),
            "by_track": _count(str(r.get("track") or DB.track_of(r)) for r in records),
        },
        "files": {},
        "note": ("合并前会逐条校验：① 文件 sha256；② 装置轴（set_version/reference_version 及其 root）"
                 "与本机一致；③ 每条记录的四条轴落在 run_axes 里。任一条不过就拒，不合并。"),
    }
    for name in ("results.jsonl", "runs.json"):
        p = work / name
        manifest["files"][name] = {"sha256": _sha_file(p), "bytes": p.stat().st_size}
    RIO.write_json(work / "MANIFEST.json", manifest)

    tgz = out_dir / f"{stem}.tar.gz"
    with tarfile.open(tgz, "w:gz") as tf:
        for name in PACKAGE_FILES:
            tf.add(work / name, arcname=f"{stem}/{name}")
    tgz.chmod(0o600)
    digest = _sha_file(tgz)
    sha_p = out_dir / f"{stem}.tar.gz.sha256"
    RIO.write_text(sha_p, f"{digest}  {tgz.name}\n")
    shutil.rmtree(work)
    RIO.secure_tree(out_dir)
    return {"manifest": manifest, "package": str(tgz), "sha256": digest,
            "sha256_file": str(sha_p), "n_records": len(records)}


def _count(items: Iterable[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for x in items:
        out[x] = out.get(x, 0) + 1
    return {k: out[k] for k in sorted(out)}


def export(*, out_dir: Path, filters: dict[str, Any] | None = None,
           db_root: Path | str | None = None, repo: Path | str | None = None,
           label: str = "", allow_empty: bool = False, at: str | None = None,
           archive: bool = False) -> dict:
    rows = DB.query(db_root, **(filters or {}))
    if not rows and not allow_empty:
        raise CliError(f"这个切片一条记录都没有（过滤条件 {filters or '无'}）。"
                       f"空包多半是过滤条件写错了 —— 真要导空包加 --allow-empty。")
    drift = record_axis_divergences(rows, axes_now(repo))
    if drift and not archive:
        raise AxisError(
            "[导出被拒] 这个切片里有**别的版本**跑出来的读数，常规结果包装不下它们"
            f"（{len(drift)} 条）：\n" + "\n".join(
                f"  · {d['axis']}：本装置 {d['declared']!r}，切片里有 {d['actual']!r}\n"
                f"      为什么拦：{d['why']}\n      怎么办：{d['fix']}" for d in drift[:20]), drift)
    return build_package(rows, out_dir=Path(out_dir), machine=local_machine(),
                         selection={"filters": filters or {}, "db_root": str(db_root or DB.db_root()),
                                    "archive": bool(archive)},
                         repo=repo, label=label, at=at, archive=archive)


# ------------------------------------------------------------------ ⑮ merge

def read_package(path: Path | str, dest: Path) -> tuple[dict, list[dict]]:
    """解包 + 完整性校验。返回 `(manifest, records)`。坏了 → `IntegrityError`。"""
    p = Path(path)
    if not p.is_file():
        raise CliError(f"结果包不存在：{p}")
    sidecar = p.with_name(p.name + ".sha256")
    if sidecar.is_file():
        want = sidecar.read_text(encoding="utf-8").split()[0].strip()
        got = _sha_file(p)
        if want != got:
            raise IntegrityError(f"结果包 sha256 对不上：{sidecar.name} 说 {want[:16]}…，"
                                 f"实际 {got[:16]}… —— 包在路上被改过或传坏了。")
    RIO.secure_dir(dest)
    with tarfile.open(p, "r:gz") as tf:
        members = tf.getmembers()
        for m in members:
            #: 路径穿越防护：只收 `<stem>/<三件之一>` 这种形状的普通文件。
            parts = Path(m.name).parts
            if m.issym() or m.islnk() or not m.isfile() or len(parts) != 2 \
                    or parts[1] not in PACKAGE_FILES or ".." in parts:
                raise IntegrityError(f"结果包里有不该有的成员：{m.name!r}（只收 "
                                     f"<目录>/{{{','.join(PACKAGE_FILES)}}} 这三件普通文件）")
        if hasattr(tarfile, "data_filter"):
            tf.extractall(dest, filter="data")               # type: ignore[arg-type]
        else:                                                # pragma: no cover - 3.10.12 之前
            tf.extractall(dest)
    roots = [d for d in dest.iterdir() if d.is_dir()]
    if len(roots) != 1:
        raise IntegrityError(f"结果包里应当只有一个顶层目录，读到 {[d.name for d in roots]}")
    root = roots[0]
    missing = [n for n in PACKAGE_FILES if not (root / n).is_file()]
    if missing:
        raise IntegrityError(f"结果包缺件：{missing}")
    manifest = json.loads((root / "MANIFEST.json").read_text(encoding="utf-8"))
    if manifest.get("kind") != PACKAGE_KIND:
        raise IntegrityError(f"这不是 GeneBench 结果包（kind={manifest.get('kind')!r}）")
    if int(manifest.get("schema_version") or 0) != SCHEMA_VERSION:
        raise IntegrityError(f"结果包 schema_version={manifest.get('schema_version')!r}，"
                             f"本机认的是 {SCHEMA_VERSION}")
    for name, meta in (manifest.get("files") or {}).items():
        got = _sha_file(root / name)
        if got != meta.get("sha256"):
            raise IntegrityError(f"{name} 的 sha256 与 MANIFEST 不符："
                                 f"清单 {str(meta.get('sha256'))[:16]}… ≠ 实际 {got[:16]}…")
    records = [json.loads(x) for x in (root / "results.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    return manifest, records


def package_axis_divergences(manifest: dict, *, repo: Path | str | None = None,
                             records: list[dict] | None = None,
                             archive: bool = False) -> list[dict]:
    """**先校验四轴一致**（⑮）。两层：四条轴逐字比；逐 run 轴要求「记录 ⊆ 包自己的登记」。

    `archive=True` 时**只跳过第一层**（那是操作员显式说「我知道这是另一版的归档」），
    第二层照判 —— 包自己登记的东西与包里的记录必须对得上，这跟归档不归档无关。
    """
    actual = axes_now(repo)
    declared = dict(manifest.get("axes") or {})
    div: list[dict] = []
    if manifest.get("archive") and not archive:
        div.append({
            "axis": "archive", "declared": True, "actual": False,
            "why": "这是**归档包**：里面的读数是另一版跑出来的（包 MANIFEST 自己写着 "
                   f"axes={declared}，两个 root 未知）。合进本机的库不会让它们变得可比。",
            "fix": "确实要归档就显式 `merge --archive`；想要可比的读数就在同一版上重跑。",
        })
    for f in (() if (manifest.get("archive") and archive) else LOCK_FIELDS):
        d, a = declared.get(f), actual.get(f)
        if d != a:
            div.append({
                "axis": f, "declared": d, "actual": a,
                "why": "这个结果包是在另一条轴上跑出来的 —— 与本机的读数不可比。"
                       "合并等于把两套题的分数放进同一张表（红队 5.1 finding E1）。",
                "fix": "把本机装置切到同一版（重冻 / 换发布包），或者不要合并这个包；"
                       "要看它的内容用 `genebench_cli.py merge --dry` 或直接读包里的 runs.json。",
            })
    for r in (records or []):
        for f, key in (("set_version", "set_version"), ("reference_version", "reference_version")):
            if declared.get(f) is not None and r.get(key) != declared.get(f):
                div.append({
                    "axis": f"record:{DB.key_of(r)}:{key}", "declared": declared.get(f),
                    "actual": r.get(key),
                    "why": "包里这条记录的轴与包 MANIFEST 声明的装置轴不同 —— 包对自己撒了谎。",
                    "fix": "在导出那台机器上重新 export（不要手改包里的文件）。",
                })
                break
        ra = manifest.get("run_axes") or {}
        for key in ("protocol_version", "channel"):
            allowed = ra.get(key) or []
            if allowed and str(r.get(key)) not in [str(x) for x in allowed]:
                div.append({
                    "axis": f"record:{DB.key_of(r)}:{key}", "declared": allowed,
                    "actual": r.get(key),
                    "why": "这条逐 run 轴不在包 MANIFEST 登记的取值集合里。",
                    "fix": "在导出那台机器上重新 export。",
                })
    return div


def merge(path: Path | str, *, db_root: Path | str | None = None,
          repo: Path | str | None = None, dry: bool = False, archive: bool = False) -> dict:
    """结果包 → 本地结果库。**四轴一致才合并**；幂等；同主键内容不同 → 报错不覆盖。"""
    tmp = Path(tempfile.mkdtemp(prefix="gb-merge-"))
    try:
        manifest, records = read_package(path, tmp)
        div = package_axis_divergences(manifest, repo=repo, records=records, archive=archive)
        if div:
            raise AxisError(
                "[合并被拒] 结果包的版本轴与本机不一致，**没有合并任何一条记录**"
                f"（{len(div)} 条分歧）：\n" + "\n".join(
                    f"  · {d['axis']}：包说 {d['declared']!r}，本机 {d['actual']!r}\n"
                    f"      为什么拦：{d['why']}\n      怎么办：{d['fix']}" for d in div[:20]),
                div)
        summary = {
            "package": str(path),
            "package_machine": (manifest.get("machine") or {}).get("machine_id"),
            "n_records_in_package": len(records),
            "axes": dict(manifest.get("axes") or {}),
            "archive": bool(manifest.get("archive")),
            "record_machines": manifest.get("record_machines") or {},
            "dry": bool(dry),
        }
        if dry:
            have = {DB.key_of(r) for r in DB.load(db_root)}
            keys = [DB.key_of(r) for r in records]
            summary.update({"would_add": len([k for k in keys if k not in have]),
                            "would_duplicate": len([k for k in keys if k in have]),
                            "added": 0, "duplicate": 0})
            return summary
        before = len(DB.load(db_root))
        r = DB.ingest(records, root=db_root)
        summary.update({"added": r["added"], "duplicate": r["duplicate"],
                        "n_total": r["n_total"], "n_before": before})
        return summary
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------ CLI

def _print_axes(r: dict) -> None:
    a, d = r["actual"], r["declared"]
    print(f"发布清单：{d.get('_manifest_path') or release_manifest_path()}")
    for f in LOCK_FIELDS:
        mark = "  " if d.get(f) == a.get(f) else "✗ "
        print(f"{mark}{f:<20} 清单 {str(d.get(f))[:24]:<26} 本装置 {str(a.get(f))[:24]}")
    print(f"  代码常量           freeze_v10.SET_VERSION={a.get('code_set_version')} "
          f"REFERENCE_VERSION={a.get('code_reference_version')}")
    print(f"  通道               {a.get('channels')}")
    print(f"  仓库里的协议版本    {a.get('protocol_version_in_repo')}")
    print("版本锁：一致（入口不会拦）" if r["ok"] else format_divergences(r["divergences"], where="axes"))


def _common_options(ap: argparse.ArgumentParser, *, suppress: bool) -> None:
    """`--db` / `--release-manifest` 在**子命令前后都能写**。

    走查（2026-09-11）里按手册敲 `merge <包> --db <库>` 直接撞 argparse 的
    `unrecognized arguments` —— 两个全局开关只挂在主解析器上。把人写命令的习惯当成用法错误，
    是手册与实现之间最便宜的那一类失败。子命令那一份用 `SUPPRESS` 作默认值：不给就**不覆盖**
    前面那个（普通默认值会把全局给的值盖成 None）。
    """
    d = argparse.SUPPRESS if suppress else None
    ap.add_argument("--db", default=d, help="结果库根（默认 $GENEBENCH_ROOT/results/v1）")
    ap.add_argument("--release-manifest", default=d,
                    help=f"RELEASE_MANIFEST.json 的路径（默认仓库根；也可用 {RELEASE_MANIFEST_ENV}）")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="genebench", description="GeneBench 结果导出 / 合并与版本锁（卡 Y2，裁定 ⑮ ⑰）")
    _common_options(ap, suppress=False)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_a = sub.add_parser("axes", help="版本锁自检：四条轴现值 vs RELEASE_MANIFEST（退 3 = 不一致）")
    _common_options(p_a, suppress=True)

    p_e = sub.add_parser("export", help="结果库切片 → 自包含结果包")
    _common_options(p_e, suppress=True)
    p_e.add_argument("--out", required=True, help="落点目录")
    p_e.add_argument("--filter", action="append", default=[], help="k=v（可多次；逗号 = 或）")
    p_e.add_argument("--label", default="", help="给人看的一句话（进 MANIFEST）")
    p_e.add_argument("--allow-empty", action="store_true")
    p_e.add_argument("--archive", action="store_true",
                     help="切片里有**别的版本**跑出来的读数时，导成**归档包**："
                          "包里写明两个 root 未知，合并端必须也显式 --archive。"
                          "**归档不等于可比** —— 出表那一步照旧按混轴拒绝。")

    p_m = sub.add_parser("merge", help="结果包 → 本地结果库（四轴不一致当场拒）")
    _common_options(p_m, suppress=True)
    p_m.add_argument("package", help="<结果包>.tar.gz")
    p_m.add_argument("--dry", action="store_true", help="只校验与试算，不写库")
    p_m.add_argument("--archive", action="store_true",
                     help="收一个**归档包**（另一版跑出来的读数）。不给的话归档包会被拒。")

    a = ap.parse_args(argv)
    manifest_path = a.release_manifest

    try:
        if a.cmd == "axes":
            r = check_release_axes(manifest=manifest_path)
            _print_axes(r)
            return 0 if r["ok"] else 3

        # ⑰：**每个子命令入口都跑版本锁**（merge 也跑 —— 一个轴对不上的装置，
        # 合进来的读数没有可比的对象）。
        assert_release_axes(where=f"genebench {a.cmd}", manifest=manifest_path)

        if a.cmd == "export":
            r = export(out_dir=Path(a.out), filters=DB._kv(a.filter), db_root=a.db,
                       label=a.label, allow_empty=a.allow_empty, archive=a.archive)
            m = r["manifest"]
            print(f"结果包 {r['package']}")
            print(f"  sha256 {r['sha256']}（同名 .sha256 在旁边）")
            print(f"  {r['n_records']} 条记录；机器 {m['machine']['machine_id']}"
                  f"（指纹来源 {m['machine']['fingerprint_source']}）")
            print(f"  轴 {m['axes']['set_version']} / {m['axes']['reference_version']}"
                  f"{'（归档包：两个 root 未知，合并端要 --archive）' if m['archive'] else ''}"
                  f"；批 {m['counts']['by_batch']}")
            if m["mixed_axes"]:
                print(f"  ！这个切片是混轴的：{m['mixed_axes']} —— 合进去也出不了表")
            return 0

        if a.cmd == "merge":
            # `--dry` 必须传下去。走查（2026-09-11）里这里漏了 `dry=a.dry`，
            # 表现是 `merge --dry` **真的写了库**，还照旧打「新增 8 条」——
            # 「只看看」把东西写进去，是这条链路上最贵的一种错。测试见
            # `ops/test_export_merge.py::test_dry跑完库里一条都没多`。
            r = merge(a.package, db_root=a.db, archive=a.archive, dry=a.dry)
            if r["dry"]:
                print(f"[试算] {r['package']}：会新增 {r['would_add']} 条、重复 {r['would_duplicate']} 条")
            else:
                print(f"合并 {r['package']}（机器 {r['package_machine']}）："
                      f"新增 {r['added']} 条、重复 {r['duplicate']} 条；库里现在 {r['n_total']} 条")
            return 0
    except AxisError as e:
        print(str(e), file=sys.stderr)
        return 3
    except DB.ResultsDBError as e:
        print(f"[合并被拒] 同主键内容不同，一条都没写进去：\n{e}", file=sys.stderr)
        return 4
    except IntegrityError as e:
        print(f"[结果包坏了] {e}", file=sys.stderr)
        return 5
    except CliError as e:
        print(f"[用法] {e}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
