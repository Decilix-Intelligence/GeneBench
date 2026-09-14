#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""形态 B 的一块拼图：**从随包发布的 `instruments/` 反建 `universe_pit` 的最小投影**。

为什么需要这一步：公开 provider 的 `instruments/`（宇宙成分与进出区间）来自
**私有** `universe_pit`（`snapshots/qlib_provider.py::build_instruments`），
而 `universe_pit` 是 tushare `index_member_all` 派生的 —— **公开源推不出来**
（baostock 没有指数成分历史）。所以形态 B 里宇宙定义**不是重算出来的，是随包发的**：
包里的 `provider/instruments/*.txt` 就是定义面，带 sha256。

本模块把那四个 txt 反投影成 `build_instruments()` 读得懂的最小 parquet：
它只 SELECT `code, in_date_compact, out_date_compact, ambiguous`（`WHERE universe=? AND canonical`），
所以最小投影只需要这六列。

**这不是把定义面藏起来**：反建出来的 `instruments/` 必须与包里的**逐字节相同**，
不同就是红 —— 这一条由 `ops/release/rebuild_public_provider.py` 与
`pack_public_provider.py --compare` 各判一次。

`ambiguous` 反投影不回来（txt 里没有这一列，`build_instruments` 也只拿它计数）。
**这里显式置 False 并记在返回值里**，不假装它是原值：manifest 的
`instruments.*.ambiguous_rows` 因此会是 0，而 `*.txt` 的字节不受影响。
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import genebench_config as cfg          # noqa: E402


class ReconstructError(RuntimeError):
    pass


def qlib_to_lake(code: str) -> str:
    """`SH600000` → `600000.SH`（`snapshots/qlib_provider.py::qlib_code` 的逆）。"""
    c = code.strip().upper()
    if len(c) <= 2 or c[:2] not in ("SH", "SZ", "BJ"):
        raise ReconstructError(f"认不出的 qlib 码：{code!r}")
    return f"{c[2:]}.{c[:2]}"


def discover_universes(instruments_dir) -> "tuple[str, ...]":
    """包里**实际发了哪几个**宇宙。

    2026-09-12（卡 A）之前这里写死 ``cfg.UNIVERSES_PIT``（含 `csi1000`）。
    换宇宙定义面之后公开包**只发 csi300 / csi500 / all** —— baostock 没有中证 1000 的
    成分接口 —— 写死那一版会在形态 B 的重建里当场抛「缺 csi1000.txt」，
    而那不是包坏了，是包本来就不发它。

    **但「按目录里有什么就算什么」会把「包被截断」也当成正常**，所以这里多一道交叉核对：
    包里 `provider/manifest.json` 的 ``instruments.files`` 列了哪几个宇宙，目录里就必须
    正好是哪几个。两边对不上 = 包被动过，当场抛。manifest 不在（单独拿一个
    `instruments/` 目录用）时退回目录口径，并要求它非空且是 ``cfg.UNIVERSES_PIT`` 的子集。
    """
    d = pathlib.Path(instruments_dir)
    found = tuple(sorted(f.stem for f in d.glob("*.txt")))
    if not found:
        raise ReconstructError(f"{d} 里一个 *.txt 都没有 —— 宇宙定义面随包发布，缺了就重建不出 provider")
    unknown = [u for u in found if u not in cfg.UNIVERSES_PIT]
    if unknown:
        raise ReconstructError(f"{d} 里有不认识的宇宙文件：{unknown}（认得的只有 {cfg.UNIVERSES_PIT}）")
    man = d.parent / "manifest.json"
    if man.is_file():
        try:
            declared = tuple(sorted(json.loads(man.read_text(encoding="utf-8"))
                                    ["instruments"]["files"]))
        except (KeyError, ValueError) as exc:
            raise ReconstructError(f"{man} 里读不出 instruments.files：{exc}") from exc
        if declared != found:
            raise ReconstructError(
                f"包自报发了 {declared}，而 {d} 里是 {found} —— 两边对不上，这个包被动过")
    return found


def read_instruments(instruments_dir: pathlib.Path,
                     universes: "tuple[str, ...] | None" = None) -> list[dict[str, Any]]:
    universes = universes or discover_universes(instruments_dir)
    rows: list[dict[str, Any]] = []
    for uni in universes:
        f = pathlib.Path(instruments_dir) / f"{uni}.txt"
        if not f.is_file():
            raise ReconstructError(f"缺 {f} —— 宇宙定义面随包发布，少一个就重建不出 provider")
        n = 0
        for ln, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) != 3:
                raise ReconstructError(f"{f}:{ln} 不是三列：{line!r}")
            code, lo, hi = parts
            rows.append({
                "code": qlib_to_lake(code),
                "universe": uni,
                "in_date_compact": lo.replace("-", ""),
                "out_date_compact": hi.replace("-", ""),
                "ambiguous": False,
                "canonical": True,
            })
            n += 1
        if n == 0:
            raise ReconstructError(f"{f} 是空的 —— 空宇宙不是「筛干净了」，是文件坏了")
    return rows


def write_universe_pit(instruments_dir, out_path, *, verbose: bool = True,
                       universes: "tuple[str, ...] | None" = None) -> dict[str, Any]:
    """``universes``：只反建这几个宇宙（卡 A）。

    公开包自 2026-09-12 起**只发 csi300 / csi500**（宇宙定义面改用 baostock 成分接口
    重建，而 baostock 没有中证 1000 的成分接口）。默认仍是 ``cfg.UNIVERSES_PIT``
    —— 私有通道与既有调用方一个字节不变；**不给这个参数时行为与从前一字不差**。
    """
    import pandas as pd
    rows = read_instruments(instruments_dir, universes)
    out_path = pathlib.Path(out_path)
    cfg.create_dir(out_path.parent)
    frame = pd.DataFrame(rows, columns=["code", "universe", "in_date_compact",
                                        "out_date_compact", "ambiguous", "canonical"])
    frame.to_parquet(out_path, index=False)
    try:
        out_path.chmod(0o600)
    except OSError:                                         # pragma: no cover
        pass
    info = {"path": str(out_path), "rows": len(frame),
            "universes": {u: int((frame["universe"] == u).sum())
                          for u in sorted(frame["universe"].unique())},
            "ambiguous_is_reconstructed_as_false": True,
            "why": "instruments/*.txt 只有三列，ambiguous 反投影不回来；它只影响 manifest 的计数，不影响 txt 字节"}
    if verbose:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    return info


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="从包里的 instruments/ 反建 universe_pit 最小投影")
    ap.add_argument("--instruments", required=True, help="包里的 provider/instruments 目录")
    ap.add_argument("--out", required=True, help="落点（<root>/snapshots/v1/universe/universe_pit.parquet）")
    ap.add_argument("--universes", nargs="+", default=None,
                    help="只反建这几个宇宙（不给 = 按包里实际发了哪几个，见 discover_universes）")
    a = ap.parse_args(argv)
    cfg.harden_umask()
    write_universe_pit(a.instruments, a.out,
                       universes=tuple(a.universes) if a.universes else None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
