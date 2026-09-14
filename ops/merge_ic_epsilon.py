#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""N-117：把 `ic_epsilon_dual.json` 合进 `calibration.json` 的 `epsilon` 节（新键 `ic_family`）。

    cd $REPO && $GENEBENCH_ROOT/env/bin/python ops/merge_ic_epsilon.py            # 合并
    cd $REPO && $GENEBENCH_ROOT/env/bin/python ops/merge_ic_epsilon.py --check    # 只验，不写

**这份文件的全部难点是"只多不少"**：`calibration.json` 是 τ 与回测 ε 的落盘处，
S3 / S5 / S7 的判据都从它读数。往里加一个键**不许**顺手改动任何既有值 ——
一个被重排的浮点尾数就足以让"这一轮与上一轮不可比"，而那件事不会有任何报错。

所以合并走三道闸，**任何一道不过就不落盘**：

1. **原文件必须已是规范序列化**（`json.dumps(..., ensure_ascii=False, indent=2)` 的逐字节结果）。
   不是的话就没法说"只多不少"——差异会混进缩进与转义，验不出来。
2. **结构相等**：新文件去掉 `epsilon.ic_family` 之后，与原对象**逐值相等**（浮点按 `==`，
   不设容差：这里要的就是"一个尾数都没动"）。
3. **行级只增不减**：逐行 diff 里，删除行只允许是"末尾多了个逗号"的那一种
   （往 dict 里插键必然让前一个兄弟键的收尾行加一个逗号），其余任何删除都判红。

备份落 `<calibration>.pre_n117.bak`（0600），带原文件的 sha256 一起记进产物。
"""
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import genebench_config as cfg                                   # noqa: E402
from ops import ic_epsilon as ICE                                # noqa: E402

CALIB: Path = cfg.SNAPSHOTS_V1 / "calibration.json"
SRC: Path = ICE.OUT_DEFAULT
KEY: str = "ic_family"

#: 进 `calibration.json` 的逐指标字段。全量证据（逐宇宙分布、样本数明细）留在
#: `ic_epsilon_dual.json` 里 —— `calibration.json` 是**判据**，不是标定报告。
BAND_FIELDS: tuple[str, ...] = ("tolerance_kind", "unit", "status", "epsilon",
                                "diff_quantiles", "diff_max", "diff_at_band_quantile",
                                "epsilon_if_max_rule", "max_rel_diff", "n_samples",
                                "zero_diff_ratio", "note")

#: 从标定产物原样搬进来的口径字段（scorer 不读，但签字人要在**一处**看全）。
CARRY: tuple[str, ...] = ("card", "method", "built_at", "code_head", "multiplier",
                          "noise_floor", "implausible_threshold", "band_quantile",
                          "band_rule", "tolerance_rule", "declaration",
                          "implementation_pair", "icir_annualization_ambiguity",
                          "no_ci_calibration", "calibrated", "implausible",
                          "no_freedom", "no_pair", "usable", "usable_metrics",
                          "unusable_metrics", "verdict", "by_window_sensitivity",
                          "sample_coverage")

__all__ = ["build_block", "merge", "verify", "CALIB", "SRC", "KEY"]


def _canon(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def build_block(src_payload: dict, *, src_path: Path, src_sha256: str) -> dict:
    """标定产物 → 进 `calibration.json` 的 `ic_family` 块（裁剪，不改数）。"""
    by_h: dict[str, Any] = {}
    for h, blk in (src_payload.get("by_holding_period") or {}).items():
        per = {m: {k: v for k, v in rec.items() if k in BAND_FIELDS}
               for m, rec in (blk.get("by_metric") or {}).items()}
        by_h[h] = {"by_metric": per, "n_samples": blk.get("n_samples"),
                   "calibrated": blk.get("calibrated"), "implausible": blk.get("implausible"),
                   "no_freedom": blk.get("no_freedom"), "no_pair": blk.get("no_pair"),
                   "usable": blk.get("usable")}
    block: dict[str, Any] = {k: src_payload[k] for k in CARRY if k in src_payload}
    block.update({
        "ticket": "N-117",
        "why": ("S4 的 tolerance.kind 是 epsilon，而这份文件此前只标定了**回测指标** —— "
                "IC 族一个带都没有 → scorer.l3.compare_epsilon 一格都比不了 → l3_pass=None "
                "→ 锚点退化 → S4 的 effect 永远扣住。"),
        "keyed_by": "holding_period（不是 by_frequency 的调仓频率）—— IC 族的分歧随持有期走。",
        "read_by": "scorer.l3.ic_family_band()",
        "source": str(src_path),
        "source_sha256": src_sha256,
        "scope": src_payload.get("inputs"),
        "by_holding_period": by_h,
    })
    return block


def _line_diff_only_adds(before: str, after: str) -> "list[str]":
    """行级 diff：返回**不被允许**的删除行。允许的删除只有"同一行末尾多了逗号"。"""
    bad: list[str] = []
    sm = difflib.SequenceMatcher(None, before.splitlines(), after.splitlines(), autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("equal", "insert"):
            continue
        old = before.splitlines()[i1:i2]
        new = after.splitlines()[j1:j2]
        # replace / delete：逐条看是不是"只多了个逗号"
        for k, line in enumerate(old):
            cand = new[k] if k < len(new) else ""
            if cand.rstrip() != line.rstrip() + "," and cand.rstrip() != line.rstrip():
                bad.append(f"{tag} @原第 {i1 + k + 1} 行: {line!r} → {cand!r}")
    return bad


def verify(before_bytes: bytes, after_bytes: bytes) -> dict:
    """三道闸。任何一道不过就抛。"""
    before_obj = json.loads(before_bytes)
    after_obj = json.loads(after_bytes)
    # 闸 1：原文件是规范序列化
    if _canon(before_obj).encode("utf-8") != before_bytes:
        raise SystemExit("原 calibration.json 不是规范序列化（json.dumps indent=2, ensure_ascii=False）—— "
                         "无法逐字节论证「只多不少」，停下。")
    # 闸 2：去掉新键后逐值相等
    stripped = json.loads(after_bytes)
    got = (stripped.get("epsilon") or {}).pop(KEY, None)
    if got is None:
        raise SystemExit(f"新文件里没有 epsilon.{KEY} —— 合并没生效。")
    if stripped != before_obj:
        raise SystemExit(f"去掉 epsilon.{KEY} 之后与原对象不相等 —— 有既有值被动过，停下。")
    # 闸 3：行级只增不减
    bad = _line_diff_only_adds(before_bytes.decode("utf-8"), after_bytes.decode("utf-8"))
    if bad:
        raise SystemExit("行级 diff 里有不被允许的删除/改写：\n  " + "\n  ".join(bad[:20]))
    nb = len(before_bytes.decode("utf-8").splitlines())
    na = len(after_bytes.decode("utf-8").splitlines())
    return {"lines_before": nb, "lines_after": na, "lines_added": na - nb,
            "sha256_before": hashlib.sha256(before_bytes).hexdigest(),
            "sha256_after": hashlib.sha256(after_bytes).hexdigest(),
            "structural_identity_ex_new_key": True,
            "line_diff_additions_only": True}


def merge(calib_path: Path = CALIB, src_path: Path = SRC, *, check_only: bool = False,
          log=print) -> dict:
    if not src_path.is_file():
        raise SystemExit(f"标定产物不存在：{src_path}（先跑 ops/ic_epsilon.py）")
    src_bytes = src_path.read_bytes()
    src_payload = json.loads(src_bytes)
    src_sha = hashlib.sha256(src_bytes).hexdigest()
    bak = calib_path.with_suffix(".json.pre_n117.bak")
    # **基线一律取备份**（存在的话）。重跑标定后再合一次是常事，若拿"已经带着旧
    # ic_family 的当前文件"当基线，「只多不少」就退化成「和上一次比只多不少」——
    # 而上一次可能已经把某个既有值挤掉了，那件事将永远查不出来。
    if bak.is_file():
        before_bytes = bak.read_bytes()
        log(f"[note] 以备份为基线（本次是**重合**）：{bak}")
    else:
        before_bytes = calib_path.read_bytes()
    obj = json.loads(before_bytes)
    if "epsilon" not in obj:
        raise SystemExit("calibration.json 里没有 epsilon 节 —— 结构不对，停下。")
    obj["epsilon"].pop(KEY, None)
    obj["epsilon"][KEY] = build_block(src_payload, src_path=src_path, src_sha256=src_sha)
    after_bytes = _canon(obj).encode("utf-8")
    report = verify(before_bytes, after_bytes)
    report.update({"calibration": str(calib_path), "source": str(src_path),
                   "source_sha256": src_sha, "key": KEY, "check_only": check_only,
                   "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                   "usable": src_payload.get("usable"),
                   "calibrated": src_payload.get("calibrated"),
                   "implausible": src_payload.get("implausible"),
                   "no_freedom": src_payload.get("no_freedom")})
    if check_only:
        log("[check] 三道闸全过，未落盘。")
        return report
    if not bak.exists():
        bak.write_bytes(before_bytes)
        bak.chmod(0o600)
        report["backup"] = str(bak)
    else:
        report["backup"] = f"{bak}（已存在，未覆盖）"
    calib_path.write_bytes(after_bytes)
    calib_path.chmod(0o600)
    log(f"合并完成：+{report['lines_added']} 行；"
        f"{report['sha256_before'][:12]} → {report['sha256_after'][:12]}；备份 {report['backup']}")
    return report


def main(argv: "list[str] | None" = None) -> int:
    cfg.harden_umask()
    p = argparse.ArgumentParser(description="N-117：ic_epsilon_dual.json → calibration.json.epsilon.ic_family")
    p.add_argument("--calibration", default=str(CALIB))
    p.add_argument("--source", default=str(SRC))
    p.add_argument("--check", action="store_true", help="只验三道闸，不写")
    p.add_argument("--report", default=None, help="把合并报告写到这个 json")
    a = p.parse_args(argv)
    rep = merge(Path(a.calibration), Path(a.source), check_only=a.check)
    if a.report:
        rp = Path(a.report)
        cfg.create_dir(rp.parent)
        rp.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
        rp.chmod(0o600)
        print(f"→ {rp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
