#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""卡 1.1-b：**公开通道的重建链** —— 一条命令从 gold 跑到 `calibration.json`。

    cd $REPO && ulimit -n 8192 && $GENEBENCH_ROOT/env/bin/python ops/run_public_chain.py
    …… --dry-run                 # 只说要做什么，不动手
    …… --step gold --force       # 只跑一步（--force 忽略断点重跑）
    …… --universes csi300        # gold / IC-ε 只做这个宇宙

链条（卡 2.5 §5 的「重建链」，与私有通道**同一份代码**）::

    universe → gold（三宇宙）→ crosscheck（2.1b 互检 → τ 的原料）
             → epsilon（面板 + 三份冻结实现 × 三个频率）
             → ic_epsilon（N-117 的 IC 族带）→ calibration（τ + ε + ic_family）

**通道怎么切**：本脚本在 :func:`main` 里把 ``GENEBENCH_CHANNEL=public`` 设进自己的
进程环境（**只在 main 里，不在 import 期** —— 放在模块顶上的表现是：任何 import 了
本模块的进程整个翻到公开通道，`ops/test_calibration.py` 就是这么被拖着去读
`snapshots/public_v1/calibration.json` 而 17 条 ERROR 的），
于是 ``genebench_config`` 的那组落点函数（``gold_dir`` / ``crosscheck_dir`` /
``epsilon_dir`` / ``calibration_path``）与 ``reference/`` 里几个通道相关的
模块属性（``fx.GOLD_DIR`` / ``ed.OUT`` / ``cal.OUT`` …）**一起**指向
``snapshots/public_v1/``。子进程继承同一个环境变量。
不设它时这条链就是私有链 —— 两条通道跑的是同一份代码，这正是重点：
复制一份「公开版链路」的表现是两边口径慢慢漂开，而两边都照常算得出数。

**两个模块的落点是 ops 侧显式覆盖的**（见 :func:`channel_overrides`）——
``reference/factor_crosscheck.py`` 与 ``reference/backtest.py`` 不在卡 1.1-b
的授权路径里，所以没有去改它们；覆盖表由
``ops/test_public_chain.py::test_channel_overrides_cover_every_private_rooted_path``
钉住：这两个模块**任何时候新长出一个指向 `snapshots/v1/` 的模块级路径**，
那条测试就红 —— 不是靠人记得回来补。

**这条链不打网关**（gold / 互检 / ε / IC-ε 全部直读 parquet），
所以不需要 ``ops/gateway_lock.py``；与卡 1.2 同理由。
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import genebench_config as cfg                                    # noqa: E402

CHANNEL: str = "public"

#: 链条顺序。``--step`` 只跑其中一步；不给 ``--step`` 就按这个顺序全跑。
STEPS: tuple[str, ...] = ("universe", "gold", "crosscheck", "epsilon",
                          "ic_epsilon", "calibration")

#: 三份**冻结的**独立实现（卡 2.2b）。公开通道原样复制这三份代码去跑公开面板 ——
#: **不重写**：重写等于换掉了「两份诚实实现的自然分歧」里的一份，量到的就不是同一件事。
IMPL_FILES: tuple[str, ...] = ("impl_v2_b1.py", "impl_v2_b2.py", "impl_v2_b3.py")

#: ε 的三个调仓频率档（`calibration._epsilon()` 按这三个名字找文件）。
FREQS: tuple[str, ...] = ("daily", "weekly", "monthly")

#: 互检（= τ 的原料）的窗口与宇宙。与私有通道那次逐字相同，否则 τ 不可比。
CROSSCHECK_UNIVERSE: str = "csi300"
CROSSCHECK_START: str = "2015-05-29"

#: gold 的窗口。与私有三份 manifest 里记的一样。
GOLD_START: str = "2015-05-29"

#: IC-ε 出带用的判据窗（卡 1.2 定的；换窗 = 换带，两条通道必须同窗才可比）。
IC_BAND_WINDOW: str = "2026-01-05..2026-06-30"


def state_marker(step: str) -> Path:
    return cfg.PUBLIC_STATE_DIR / f"chain_{step}.done"


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def _write(p: Path, text: str) -> None:
    cfg.create_dir(p.parent)
    p.write_text(text, encoding="utf-8")
    p.chmod(0o600)


# --------------------------------------------------------------------- 覆盖表

def _override_map() -> "dict[tuple[str, str], Path]":
    """``(模块, 属性) → 公开通道落点``。

    只覆盖**不在本卡授权路径里**的那两个模块。授权路径里的模块
    （``factor_exec`` / ``calibration`` / ``epsilon`` / ``epsilon_dual`` /
    ``make_epsilon_panel``）已经自己按 ``GENEBENCH_CHANNEL`` 走，不在这里。
    """
    return {
        ("reference.factor_crosscheck", "CELLS_DIR"): cfg.crosscheck_dir(CHANNEL),
        ("reference.factor_crosscheck", "REPORT_JSON"): cfg.crosscheck_report(CHANNEL),
        ("reference.backtest", "RESULT_DIR"): cfg.epsilon_dir(CHANNEL),
    }


@contextlib.contextmanager
def channel_overrides():
    """把覆盖表里的模块属性临时指到公开落点，退出时**一定**还原。

    还原是硬要求：同一个进程里如果后面还有私有通道的动作（本卡的不变性比对就有），
    留一个指向公开根的模块常量下去，表现是「私有产物被写进了公开目录」——
    两边都不报错。
    """
    import importlib

    saved: list[tuple[Any, str, Any]] = []
    try:
        for (modname, attr), value in _override_map().items():
            mod = importlib.import_module(modname)
            saved.append((mod, attr, getattr(mod, attr)))
            setattr(mod, attr, value)
        yield
    finally:
        for mod, attr, old in reversed(saved):
            setattr(mod, attr, old)


# ------------------------------------------------------------------ 各步实现

def step_universe(a: argparse.Namespace, log: Callable[[str], None]) -> dict[str, Any]:
    """宇宙轴：把 v1 的 ``universe_pit.parquet`` 复制进公开快照根。

    **宇宙轴沿用 v1，不从 baostock 重建**（卡 2.5 §1 第 4 项裁定 / N-68，
    与卡 1.1-a 的 ``PUBLIC_PATHS.universe_pit`` 是同一条）：「谁在指数里」是
    定义不是行情。这里复制一份进公开根，是为了让公开包**自足** ——
    外部用户手里没有 ``snapshots/v1/``，而 ``ops/ic_epsilon.py`` 的 preflight
    要求 ``universe/universe_pit.parquet`` 就在快照根下。
    """
    src = cfg.universe_pit_parquet("private")
    dst = cfg.universe_pit_parquet(CHANNEL)
    cfg.create_dir(dst.parent)
    if not src.is_file():
        raise SystemExit(f"私有宇宙表不存在：{src}")
    shutil.copy2(src, dst)
    dst.chmod(0o600)
    s = _sha256(dst)
    if s != _sha256(src):
        raise SystemExit("复制后 sha256 不同 —— 停下")
    log(f"  universe_pit.parquet → {dst}（sha256 {s[:12]}，与 v1 逐字节相同）")
    return {"src": str(src), "dst": str(dst), "sha256": s,
            "note": "宇宙轴沿用 v1（N-68）；不是从公开源重建的，数据卡里要写明。"}


def _gold_done(universe: str) -> bool:
    m = cfg.gold_dir(CHANNEL) / universe / "manifest.json"
    if not m.is_file():
        return False
    try:
        d = json.loads(m.read_text(encoding="utf-8"))
    except Exception:
        return False
    return d.get("write", {}).get("factors") == 792 and not d.get("failures")


def step_gold(a: argparse.Namespace, log: Callable[[str], None]) -> dict[str, Any]:
    """三宇宙 gold。每个宇宙**一个子进程**；子进程退出时内存才真的还回去。

    **默认给 ``--spill-dir``。** 不给的话 ``factor_exec`` 把 792 个面板同时压在
    内存里：csi1000 实测常驻约 22 GiB，而 f01 只有 30 GiB 且是共用机 ——
    2026-09-07 05:20Z 内核就是这么把公开 csi1000 那一次收走的（``exit=137``），
    而且被杀之前已经退化到「一小时写一个 parquet」。给了之后峰值只剩几 GiB，
    产物逐字节不变。``--no-spill`` 可以关掉（比对用）。
    """
    todo = [u for u in a.universes if a.force or not _gold_done(u)]
    skipped = [u for u in a.universes if u not in todo]
    for u in skipped:
        log(f"  {u}：已完成，跳过")
    out: dict[str, Any] = {"skipped": skipped, "ran": {}}
    running: list[tuple[str, subprocess.Popen, float, Path]] = []
    for u in todo:
        logf = cfg.PUBLIC_STATE_DIR / f"gold_{u}.log"
        cfg.create_dir(logf.parent)
        cmd = [sys.executable, "-m", "reference.factor_exec", "--universe", u,
               "--start", GOLD_START, "--end", cfg.FREEZE_DATE]
        if not a.no_spill:
            cmd += ["--spill-dir", str(Path(a.spill_root) / u)]
        log(f"  起 {u}：{' '.join(cmd)}  → {logf}")
        fh = logf.open("w", encoding="utf-8")
        pr = subprocess.Popen(cmd, cwd=str(_REPO), stdout=fh, stderr=subprocess.STDOUT,
                              env=dict(os.environ, GENEBENCH_CHANNEL=CHANNEL))
        running.append((u, pr, time.time(), logf))
        while len(running) >= a.jobs:
            running = _reap(running, out, log)
    while running:
        running = _reap(running, out, log)
    bad = [u for u, r in out["ran"].items() if r["returncode"] != 0 or not _gold_done(u)]
    if bad:
        raise SystemExit(f"gold 失败：{bad}（看 {cfg.PUBLIC_STATE_DIR}/gold_*.log）")
    return out


def _reap(running, out, log):
    """等最早那个子进程结束，记账。"""
    u, pr, t0, logf = running[0]
    rc = pr.wait()
    el = round(time.time() - t0, 1)
    m = cfg.gold_dir(CHANNEL) / u / "manifest.json"
    st = json.loads(m.read_text(encoding="utf-8"))["write"] if m.is_file() else {}
    out["ran"][u] = {"returncode": rc, "elapsed_s": el, "log": str(logf),
                     "factors": st.get("factors"), "rows": st.get("rows"),
                     "bytes": st.get("bytes")}
    log(f"  {u} 结束 rc={rc} 用时 {el}s 因子 {st.get('factors')} 行 {st.get('rows'):,}"
        if st.get("rows") else f"  {u} 结束 rc={rc} 用时 {el}s")
    return running[1:]


def step_crosscheck(a: argparse.Namespace, log: Callable[[str], None]) -> dict[str, Any]:
    """2.1b 互检 —— τ 的原料。窗口与宇宙与私有那次逐字相同，否则 τ 不可比。"""
    from reference import factor_crosscheck as fc

    with channel_overrides():
        assert fc.CELLS_DIR == cfg.crosscheck_dir(CHANNEL), fc.CELLS_DIR
        rep = fc.crosscheck(CROSSCHECK_UNIVERSE, CROSSCHECK_START, cfg.FREEZE_DATE,
                            verbose=not a.quiet)
        # `crosscheck()` 自己不落报告（它 return），这里按私有那次的落点写。
        _write(cfg.crosscheck_report(CHANNEL),
               json.dumps(rep, ensure_ascii=False, indent=2))
    log(f"  可比因子 {rep['comparable_factors']} / 格 {rep['cells_total']:,} / "
        f"保留 {rep['cells_kept']:,} / τ候选 {rep['tau_candidates']['pooled_factor_x_day_p10']:.6f}")
    return {"comparable_factors": rep["comparable_factors"],
            "cells_total": rep["cells_total"], "cells_kept": rep["cells_kept"],
            "tau_candidates": rep["tau_candidates"],
            "report": str(cfg.crosscheck_report(CHANNEL))}


def step_epsilon(a: argparse.Namespace, log: Callable[[str], None]) -> dict[str, Any]:
    """ε：面板 → 三份冻结实现 × 三个频率 → 全对最大差 × 1.5。"""
    from reference import epsilon_dual as ed
    from reference import make_epsilon_panel as mep

    eps = cfg.epsilon_dir(CHANNEL)
    cfg.create_dir(eps)
    panel = eps / "bt_input_csi300_v2.parquet"
    info: dict[str, Any] = {}

    if a.force or not panel.is_file():
        t = time.time()
        df = mep.build()
        info["panel"] = {"path": str(panel), "rows": int(len(df)),
                         "elapsed_s": round(time.time() - t, 1),
                         "sha256": _sha256(panel)}
        log(f"  面板 {len(df):,} 行 / {info['panel']['elapsed_s']}s → {panel}")
    else:
        info["panel"] = {"path": str(panel), "rows": None, "skipped": True,
                         "sha256": _sha256(panel)}
        log(f"  面板已存在，跳过：{panel}")

    # 三份实现的代码**原样复制**（不改一个字），并记 sha256 证明与私有那次同一份。
    src_dir = cfg.epsilon_dir("private")
    impls: dict[str, Any] = {}
    for name in IMPL_FILES:
        s, d = src_dir / name, eps / name
        if not s.is_file():
            raise SystemExit(f"冻结实现不存在：{s}")
        shutil.copy2(s, d)
        d.chmod(0o600)
        impls[name] = {"sha256": _sha256(d), "same_as_private": _sha256(d) == _sha256(s)}
    log(f"  三份冻结实现已就位：{ {k: v['sha256'][:12] for k, v in impls.items()} }")
    info["implementations"] = impls

    runs: dict[str, Any] = {}
    for name in IMPL_FILES:
        t = time.time()
        pr = subprocess.run([sys.executable, str(eps / name), *FREQS],
                            cwd=str(eps), capture_output=True, text=True,
                            env=dict(os.environ, GENEBENCH_CHANNEL=CHANNEL))
        runs[name] = {"returncode": pr.returncode, "elapsed_s": round(time.time() - t, 1)}
        if pr.returncode != 0:
            _write(eps / f"{name}.err.log", pr.stdout + "\n" + pr.stderr)
            raise SystemExit(f"{name} 失败 rc={pr.returncode}，看 {eps}/{name}.err.log")
        log(f"  {name} 三频率跑完 {runs[name]['elapsed_s']}s")
    info["runs"] = runs

    per_freq: dict[str, Any] = {}
    for freq in FREQS:
        outs = {f"B{i}": eps / f"out_v2_b{i}_{freq}.json" for i in (1, 2, 3)}
        miss = [str(p) for p in outs.values() if not p.is_file()]
        if miss:
            raise SystemExit(f"{freq} 少了实现产物：{miss}")
        rep = ed.compare_pairwise(outs, label=freq, verbose=not a.quiet)
        per_freq[freq] = {"calibrated": rep["calibrated"], "implausible": rep["implausible"],
                          "no_freedom": rep["no_freedom"], "usable": rep["usable"]}
        log(f"  ε[{freq}] 可标定 {len(rep['calibrated'])} · 超阈 {len(rep['implausible'])} · "
            f"无自由度 {len(rep['no_freedom'])} · usable={rep['usable']}")
    info["by_frequency"] = per_freq
    return info


def step_ic_epsilon(a: argparse.Namespace, log: Callable[[str], None]) -> dict[str, Any]:
    """N-117 的 IC 族带。样本盘按宇宙分开（可断点续跑），再聚合出带。"""
    eps = cfg.epsilon_dir(CHANNEL)
    snap = cfg.snapshot_root(CHANNEL)
    state = eps / "ic_state"
    cfg.create_dir(state)
    out = eps / "ic_epsilon_dual.json"
    info: dict[str, Any] = {"per_universe": {}}

    procs: list[tuple[str, subprocess.Popen, float, Path]] = []
    for u in a.universes:
        sp = state / f"{u}.jsonl"
        logf = cfg.PUBLIC_STATE_DIR / f"ic_epsilon_{u}.log"
        cfg.create_dir(logf.parent)
        # **跑批也只跑判据窗**：`ic_epsilon.py` 默认跑三个窗，那是 3 倍的工作量，
        # 而带只用判据窗出（卡 1.2 定的）。两条通道必须**同窗**才可比。
        cmd = [sys.executable, "ops/ic_epsilon.py",
               "--gold-dir", str(cfg.gold_dir(CHANNEL)), "--provider-dir", str(snap),
               "--universes", u, "--state", str(sp), "--windows", IC_BAND_WINDOW,
               "--out", str(eps / f"ic_epsilon_{u}.json"), "--quiet"]
        log(f"  起 {u}：{' '.join(cmd)}  → {logf}")
        fh = logf.open("w", encoding="utf-8")
        procs.append((u, subprocess.Popen(cmd, cwd=str(_REPO), stdout=fh,
                                          stderr=subprocess.STDOUT,
                                          env=dict(os.environ, GENEBENCH_CHANNEL=CHANNEL)),
                      time.time(), sp))
        while len([p for p in procs if p[1].poll() is None]) >= a.ic_jobs:
            time.sleep(5)
    for u, pr, t0, sp in procs:
        rc = pr.wait()
        n = sum(1 for _ in sp.open(encoding="utf-8")) if sp.is_file() else 0
        # **退出码 1 是正常的**：只要还有指标超阈，`ic_epsilon.py` 就返回 1
        # （与 2.2b 同纪律）。真失败看 verdict 与样本数，不看退出码。
        info["per_universe"][u] = {"returncode": rc, "elapsed_s": round(time.time() - t0, 1),
                                   "samples": n}
        log(f"  {u} 结束 rc={rc}（1 = 有指标超阈，不是跑失败）样本 {n} "
            f"用时 {info['per_universe'][u]['elapsed_s']}s")
        if n == 0:
            raise SystemExit(f"{u} 一条样本都没出 —— 看 {cfg.PUBLIC_STATE_DIR}/ic_epsilon_{u}.log")

    cmd = [sys.executable, "ops/ic_epsilon.py", "--aggregate-only",
           "--gold-dir", str(cfg.gold_dir(CHANNEL)), "--provider-dir", str(snap),
           "--state", str(state), "--windows", IC_BAND_WINDOW, "--out", str(out)]
    log(f"  聚合：{' '.join(cmd)}")
    pr = subprocess.run(cmd, cwd=str(_REPO), capture_output=True, text=True,
                        env=dict(os.environ, GENEBENCH_CHANNEL=CHANNEL))
    _write(cfg.PUBLIC_STATE_DIR / "ic_epsilon_aggregate.log", pr.stdout + "\n" + pr.stderr)
    if not out.is_file():
        raise SystemExit(f"聚合没出产物：{out}（rc={pr.returncode}）")
    d = json.loads(out.read_text(encoding="utf-8"))
    info.update({"out": str(out), "aggregate_returncode": pr.returncode,
                 "verdict": d.get("verdict"), "usable": d.get("usable"),
                 "usable_metrics": d.get("usable_metrics"),
                 "unusable_metrics": d.get("unusable_metrics")})
    log(f"  ic_family usable={d.get('usable')} 可用 {d.get('usable_metrics')}")
    return info


def step_calibration(a: argparse.Namespace, log: Callable[[str], None]) -> dict[str, Any]:
    """τ + ε + ic_family 汇成公开 `calibration.json`，并跑一遍 N-117 的三道闸。"""
    import snapshots.qlib_provider as qp
    from ops import merge_ic_epsilon as mie
    from reference import calibration as cal

    dest = cfg.calibration_path(CHANNEL)
    with channel_overrides(), qp.using(CHANNEL):
        payload = cal.build(verbose=not a.quiet)
    raw = dest.read_bytes()

    # ---- 三道闸：ic_family 是**只多不少**地加进来的 ------------------------
    # `build()` 原生就把 ic_family 写进去了（不再走事后合并），但「只多不少」
    # 这件事仍然要证。做法：把 ic_family 摘掉当基线，再用 `merge_ic_epsilon`
    # 那份**同一段代码**把它加回去，比对结果**与落盘文件逐字节相同**。
    obj = json.loads(raw)
    ic = obj["epsilon"].pop("ic_family", None)
    if ic is None:
        raise SystemExit("公开 calibration.json 里没有 epsilon.ic_family —— 停下")
    before = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
    src = cfg.epsilon_dir(CHANNEL) / "ic_epsilon_dual.json"
    src_raw = src.read_bytes()
    obj["epsilon"]["ic_family"] = mie.build_block(
        json.loads(src_raw), src_path=src, src_sha256=hashlib.sha256(src_raw).hexdigest())
    after = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
    gates = mie.verify(before, after)
    if after != raw:
        raise SystemExit("build() 原生写的 ic_family 与 merge_ic_epsilon 产出的不一致 —— 停下")
    gates["native_block_equals_merge_block"] = True

    t, e = payload["tau"], payload["epsilon"]
    log(f"  τ = {t['value']:.6f}（{t['factors_used']} 因子 / {t['cells_used']:,} 格）")
    for f, v in e["by_frequency"].items():
        log(f"  ε[{f}] 可标定 {len(v['calibrated'])} · 超阈 {len(v['implausible'])} · "
            f"无自由度 {len(v['no_freedom'])} · usable={v['usable']}")
    log(f"  ic_family usable_metrics={e.get('ic_family', {}).get('usable_metrics')}")
    log(f"  三道闸：+{gates['lines_added']} 行，去掉新键后与基线逐值相等")
    return {"path": str(dest), "sha256": _sha256(dest), "tau": t["value"],
            "tau_factors_used": t["factors_used"], "tau_cells_used": t["cells_used"],
            "epsilon_by_frequency": {f: {"calibrated": v["calibrated"],
                                         "implausible": v["implausible"],
                                         "no_freedom": v["no_freedom"],
                                         "usable": v["usable"]}
                                     for f, v in e["by_frequency"].items()},
            "ic_family_usable_metrics": e.get("ic_family", {}).get("usable_metrics"),
            "ic_family_unusable_metrics": e.get("ic_family", {}).get("unusable_metrics"),
            "ready_for_scoring": payload["ready_for_scoring"],
            "n117_gates": gates}


HANDLERS: dict[str, Callable] = {
    "universe": step_universe, "gold": step_gold, "crosscheck": step_crosscheck,
    "epsilon": step_epsilon, "ic_epsilon": step_ic_epsilon, "calibration": step_calibration,
}


def main(argv: "list[str] | None" = None) -> int:
    p = argparse.ArgumentParser(description="卡 1.1-b：公开通道重建链")
    p.add_argument("--step", choices=STEPS, default=None, help="只跑这一步")
    p.add_argument("--force", action="store_true", help="忽略断点，重跑")
    p.add_argument("--dry-run", action="store_true", help="只说要做什么")
    p.add_argument("--universes", nargs="+", default=list(cfg.UNIVERSES))
    p.add_argument("--jobs", type=int, default=1,
                   help="gold 的并行度。**默认 1**：机器 30 GiB 且是共用机，"
                        "并行跑大宇宙历史上被 OOM killer 收走过两次。开了 spill "
                        "（默认开）单个宇宙只要几 GiB，但仍建议串行 —— 三宇宙的瓶颈"
                        "是落盘不是 CPU，并行省不下多少。")
    p.add_argument("--ic-jobs", type=int, default=3, help="IC-ε 的并行度（每进程约 2 GiB）")
    p.add_argument("--spill-root", default=str(cfg.GENEBENCH_ROOT / "scratch" / "gold_spill"),
                   help="gold 的面板暂存根（每个宇宙一个子目录，跑完自删）")
    p.add_argument("--no-spill", action="store_true",
                   help="不暂存，面板全留内存 —— 只在「跟旧行为逐字节比对」时用")
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--report", default=None, help="把运行记账写到这个 json")
    a = p.parse_args(argv)

    cfg.harden_umask()
    # 在这里设，不在 import 期设：见模块 docstring「通道怎么切」。
    # `setdefault` 而不是直接赋值 —— 显式设成 private 的人应该看到下面那句拒绝，
    # 而不是被我们悄悄改成 public。
    os.environ.setdefault(cfg.CHANNEL_ENV, CHANNEL)
    if cfg.channel() != CHANNEL:
        raise SystemExit(f"GENEBENCH_CHANNEL={cfg.channel()!r} —— 本脚本只跑公开通道")
    cfg.create_dir(cfg.PUBLIC_STATE_DIR)

    steps = [a.step] if a.step else list(STEPS)
    lines: list[str] = []

    def log(s: str) -> None:
        lines.append(s)
        if not a.quiet or a.dry_run:
            print(s, flush=True)

    run_rec: dict[str, Any] = {
        "card": "1.1-b", "channel": CHANNEL,
        "started_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "snapshot_root": str(cfg.snapshot_root(CHANNEL)), "steps": {},
    }
    for s in steps:
        mark = state_marker(s)
        if mark.exists() and not a.force and not a.step:
            log(f"[{s}] 已完成（{mark.name}），跳过")
            run_rec["steps"][s] = {"skipped": True}
            continue
        if a.dry_run:
            log(f"[{s}] 会跑（断点 {mark}）")
            run_rec["steps"][s] = {"dry_run": True}
            continue
        log(f"[{s}] 开始 {dt.datetime.now().strftime('%H:%M:%S')}")
        t0 = time.time()
        rec = HANDLERS[s](a, log)
        el = round(time.time() - t0, 1)
        rec["elapsed_s"] = el
        run_rec["steps"][s] = rec
        _write(mark, json.dumps(rec, ensure_ascii=False, indent=2, default=str))
        log(f"[{s}] 完成，用时 {el}s")

    run_rec["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    if a.report:
        _write(Path(a.report), json.dumps(run_rec, ensure_ascii=False, indent=2, default=str))
        print(f"→ {a.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
