# -*- coding: utf-8 -*-
"""T12：provider 的**路径无关性**——同一组查询在 f01 与容器内结果逐字节相同。

两处都跑这一个文件，各自输出一个 JSON，再比 sha256：

    f01:  python3 t12_provider_queries.py /data/shared/genebench/snapshots/v1/qlib_provider
    容器:  python3 /task/protocol/t12_provider_queries.py /task/provider

**为什么必须测而不是推**（卡 4.3 §7 末）：`ops/test_qlib_provider.py` 查的是
「provider digest 与 **manifest 里的绝对路径**」，`calibration.json` 里也记着**绝对路径**；
容器内 provider 落在 `/task/provider`，与 f01 的绝对路径不同。
路径无关性是**测出来的**，不是推出来的；测不过才走 TK-4（容器内同路径落盘）——
**它是备用路径，不是默认路径**。

不依赖 qlib：直接读 provider 的二进制格式。理由——容器镜像里没有 qlib，
而装它就等于把「容器内能不能装包」这个变量混进这条判据。
读格式本身反而更硬：它证明的是**字节层面**一致，不是「某个库读出来一样」。
"""
from __future__ import annotations

import hashlib
import json
import struct
import sys
from pathlib import Path

#: 固定的查询集。**写死**，不随机 —— 两处必须问同样的问题。
QUERIES = [
    ("calendar_head", None), ("calendar_tail", None), ("calendar_count", None),
    ("instruments", "csi300"),
]
#: 抽样的标的与字段：取字典序最小的若干只，避免"随机抽样两边抽到不同的"。
N_CODES = 5
FIELDS = ("close", "volume", "factor")


def _read_bin(p: Path) -> list[float]:
    """qlib 的 `.day.bin`：4 字节起始索引 + 若干 float32。**按字节读**，不经 qlib。"""
    raw = p.read_bytes()
    if len(raw) < 4:
        return []
    n = (len(raw) - 4) // 4
    return list(struct.unpack(f"<{n}f", raw[4:4 + n * 4]))


def collect(root: Path) -> dict:
    out: dict = {"queries": {}}
    cal = root / "calendars" / "day.txt"
    days = cal.read_text(encoding="utf-8").split()
    out["queries"]["calendar_count"] = len(days)
    out["queries"]["calendar_head"] = days[:5]
    out["queries"]["calendar_tail"] = days[-5:]

    inst_dir = root / "instruments"
    files = sorted(p.name for p in inst_dir.iterdir() if p.is_file())
    out["queries"]["instrument_files"] = files
    for name in files[:2]:
        text = (inst_dir / name).read_text(encoding="utf-8")
        out["queries"][f"instruments::{name}"] = {
            "lines": len(text.splitlines()),
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "head": text.splitlines()[:3],
        }

    feat = root / "features"
    codes = sorted(p.name for p in feat.iterdir() if p.is_dir())[:N_CODES]
    out["queries"]["n_codes_total"] = len(list(feat.iterdir()))
    out["queries"]["sample_codes"] = codes
    for code in codes:
        for field in FIELDS:
            f = feat / code / f"{field}.day.bin"
            if not f.is_file():
                out["queries"][f"{code}/{field}"] = None
                continue
            vals = _read_bin(f)
            # **逐字节**的证据：文件 sha + 前后若干个值（值本身用 repr 保精度）
            out["queries"][f"{code}/{field}"] = {
                "sha256": hashlib.sha256(f.read_bytes()).hexdigest(),
                "n": len(vals),
                "head": [repr(v) for v in vals[:3]],
                "tail": [repr(v) for v in vals[-3:]],
            }
    blob = json.dumps(out["queries"], ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))
    out["result_sha256"] = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    # **不记 root 路径** —— 记了它两处必然不同，判据就自己废了。
    # 路径无关正是本测试要证明的东西。
    return out


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: t12_provider_queries.py <provider_root> [--json]", file=sys.stderr)
        return 2
    root = Path(sys.argv[1])
    if not root.is_dir():
        print(f"provider 根不存在：{root}", file=sys.stderr)
        return 2
    out = collect(root)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
