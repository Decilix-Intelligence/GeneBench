# -*- coding: utf-8 -*-
"""`python -m integrations.cost …` 的入口。

用错了（状态不对、时刻没带时区、账本坏了）**印一行人话退 2**，不甩 traceback：
这个 CLI 是给正在接系统的人顺手敲的，traceback 会让人以为是工具坏了而不是自己敲错了。
"""
from __future__ import annotations

import sys

from . import CostError, main

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CostError as e:
        print(f"接入成本账本：{e}", file=sys.stderr)
        raise SystemExit(2) from None
