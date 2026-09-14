#!/usr/bin/env python3
"""重算协议工件的封闭清单。改了任何一件工件都要跑一次 —— 不跑，P8 会当场红。

**这就是封闭清单该有的行为**：清单不是「目录里当时有什么」，而是「哪几个文件、每个是什么内容」。
改了内容而不重算，等于清单与实物脱节 —— P8 抓的正是这个。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

D = Path(__file__).resolve().parent / "protocol" / "geneprotocol_v1"
#: 封闭清单只管**每道题都一样**的那部分。四份规则 JSON 逐题生成，
#: 走 P8 的 expect_work 文件集封闭，不进这里。
STATIC = ("validate_artifact.py", "README.md", "contract.md")


def main() -> int:
    m = json.loads((D / "MANIFEST.json").read_text(encoding="utf-8"))
    old = dict(m.get("artifacts") or {})
    m["artifacts"] = {n: hashlib.sha256((D / n).read_bytes()).hexdigest() for n in STATIC}
    (D / "MANIFEST.json").write_text(json.dumps(m, ensure_ascii=False, indent=1) + "\n",
                                     encoding="utf-8")
    changed = [n for n in STATIC if old.get(n) != m["artifacts"][n]]
    print(f"清单已重算（{len(STATIC)} 件）；变动 {changed or '无'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
