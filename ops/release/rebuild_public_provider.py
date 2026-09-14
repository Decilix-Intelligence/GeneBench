#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""形态 B 的建集半段：在用户机器上，从已下载的缓存重建出公开 provider。

**不复制 builder**。建集这件事只有一条实现（`ops/build_public_channel.py`），
本脚本只补它在用户机器上缺的那一块：

* `step_provider` 要读**私有** `universe_pit`（宇宙定义面，tushare 派生，公开源推不出来）
  → 用包里的 `provider/instruments/*.txt` 反建一份最小投影
  （`ops/release/universe_from_instruments.py`），落在 `<root>/snapshots/v1/universe/`；
* `step_verify` 要比对私有快照的 mtime（「两条通道并列不覆盖」）
  → 用户机器上没有私有通道，这一步**跳过并说明**，不是「验证通过」。

跑完立刻做两件判据检查（**都能被证伪**）：

1. 反建的 `instruments/*.txt` 与包里的**逐字节相同** —— 不同说明反投影错了；
2. 整棵树与包里的 `SHA256SUMS` 逐文件比（`pack_public_provider.compare`）。

    $PY ops/release/rebuild_public_provider.py --root <数据根> --package <解开的包目录>
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import time
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import genebench_config as cfg          # noqa: E402
from ops.release import pack_public_provider as PP      # noqa: E402
from ops.release import universe_from_instruments as UFI    # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[2]
#: 用户机器上要跑的建集步骤。`fetch` 已经在 `fetch_public_quotes.py` 做过；
#: `verify` 依赖私有通道，跳过（见 docstring）。
STEPS: tuple[str, ...] = ("tables", "gate", "tradability", "provider")


class RebuildError(RuntimeError):
    pass


def stage_universe(package: pathlib.Path, root: pathlib.Path) -> dict[str, Any]:
    src = pathlib.Path(package) / "provider" / "instruments"
    if not src.is_dir():
        raise RebuildError(f"包里没有 {src} —— 宇宙定义面随包发布，少了就重建不出 provider")
    out = pathlib.Path(root) / "snapshots" / "v1" / "universe" / "universe_pit.parquet"
    return UFI.write_universe_pit(src, out, verbose=False)


def run_build(root: pathlib.Path, steps=STEPS, *, python=None,
              force: bool = False) -> dict[str, Any]:
    """跑 `ops/build_public_channel.py`（**同一条建集实现**）。"""
    import os
    env = dict(os.environ)
    env["GENEBENCH_ROOT"] = str(root)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    cmd = [python or sys.executable, str(REPO / "ops" / "build_public_channel.py")]
    for s in steps:
        cmd += ["--step", s]
    if force:
        cmd.append("--force")
    t0 = time.time()
    p = subprocess.run(cmd, cwd=str(REPO), env=env, text=True,
                       capture_output=True, timeout=6 * 3600)
    took = round(time.time() - t0, 1)
    tail = "\n".join((p.stdout or "").splitlines()[-25:])
    if p.returncode != 0:
        raise RebuildError(f"建集失败（rc={p.returncode}，{took} 秒）：\n{tail}\n"
                           f"--- stderr ---\n{(p.stderr or '')[-2000:]}")
    return {"seconds": took, "steps": list(steps), "tail": tail}


def assert_instruments_byte_identical(package: pathlib.Path, root: pathlib.Path) -> dict[str, str]:
    """反建的宇宙定义面必须与包里的**逐字节相同**。

    这一条是**判别力**所在：反投影只要错一格（码的写法、日期形态、排序），
    这里立刻红 —— 而如果只看「provider 建出来了」，错的定义面照样能建出一棵树。
    """
    pkg = pathlib.Path(package) / "provider" / "instruments"
    got = pathlib.Path(root) / "snapshots" / cfg.PUBLIC_VERSION / "qlib_provider" / "instruments"
    report: dict[str, str] = {}
    bad = []
    for f in sorted(pkg.glob("*.txt")):
        a, b = f, got / f.name
        if not b.is_file():
            bad.append(f"{f.name}：重建后不存在")
            continue
        ha, hb = PP._sha256(a), PP._sha256(b)
        report[f.name] = hb
        if ha != hb:
            bad.append(f"{f.name}：包里 {ha[:16]}… vs 重建 {hb[:16]}…")
    if not report:
        raise RebuildError(f"{pkg} 里一个 instruments 都没有")
    if bad:
        raise RebuildError("反建的宇宙定义面与包里不一致：" + "；".join(bad))
    return report


def rebuild(root, package, *, steps=STEPS, python=None, force: bool = False,
            verbose: bool = True) -> dict[str, Any]:
    root, package = pathlib.Path(root), pathlib.Path(package)
    out: dict[str, Any] = {"root": str(root), "package": str(package)}
    t0 = time.time()
    if verbose:
        print(f"[1/4] 反建宇宙定义面 → {root}/snapshots/v1/universe/", flush=True)
    out["universe"] = stage_universe(package, root)
    if verbose:
        print(f"[2/4] 建集（{','.join(steps)}）—— 走 ops/build_public_channel.py", flush=True)
    out["build"] = run_build(root, steps, python=python, force=force)
    if verbose:
        print(f"      {out['build']['seconds']} 秒")
        print("[3/4] 反建的 instruments 与包里逐字节比", flush=True)
    out["instruments_identical"] = assert_instruments_byte_identical(package, root)
    sums = package / PP.SUMS_NAME
    if verbose:
        print(f"[4/4] 整棵树与 {sums} 逐文件比", flush=True)
    if not sums.is_file():
        raise RebuildError(f"包里没有 {sums} —— 没有校验和就没有可比的判据")
    out["compare"] = PP.compare(sums, gb_root=root, repo=REPO)
    out["seconds_total"] = round(time.time() - t0, 1)
    out["verify_step_skipped"] = (
        "build_public_channel 的 verify 步比对私有快照的 mtime（两条通道并列不覆盖），"
        "用户机器上没有私有通道 —— 跳过，不当作「验证通过」")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="形态 B：在用户机器上重建公开 provider 并比校验和")
    ap.add_argument("--root", required=True)
    ap.add_argument("--package", required=True, help="形态 A 的包解开后的目录")
    ap.add_argument("--step", action="append", default=None, choices=STEPS)
    ap.add_argument("--force", action="store_true", help="忽略断点，重跑选中的步")
    a = ap.parse_args(argv)
    if str(cfg.GENEBENCH_ROOT) != str(pathlib.Path(a.root)):
        print(f"[红] GENEBENCH_ROOT={cfg.GENEBENCH_ROOT} 与 --root={a.root} 不一致 —— "
              f"先 export GENEBENCH_ROOT={a.root}", file=sys.stderr)
        return 2
    cfg.harden_umask()
    out = rebuild(a.root, a.package, steps=tuple(a.step or STEPS), force=a.force)
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    ok = out["compare"]["ok"]
    prov = out["compare"].get("package_provided_differ") or []
    print(("[绿] " if ok else "[红] ") +
          f"逐文件相同 {out['compare']['same']}，differ {len(out['compare']['differ'])}，"
          f"构建戳差异 {len(out['compare']['build_stamped_differ'])}（预期内），"
          f"随包副本差异 {len(prov)}（预期内：docs/ 与 selfbuild/ 取自仓库工作树，以包内副本为准）")
    for name in prov:
        print(f"      随包副本已改：{name}（不影响数据面判据）")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
