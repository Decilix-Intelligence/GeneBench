#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""example_minimal —— 30 行的 P2 被测系统（正文恰好 30 行，`ops/test_integrations_readme.py` 数着）。

它做的事只有三件，正好是 P2 的三件责任：
  ① 从 `/task/INSTRUCTION.md` 读题（**唯一题面**；`task.yaml` 不在容器里）；
  ② 用垫片经网关取一段数（带 `as_of`、带身份头、显式 `fields`、闭区间）；
  ③ 用 `emit` 写 `/task/artifact.json`（S1 取数留痕）。

**它不调 LLM** —— S1 是取数留痕，没有需要模型判断的地方。真要接模型只有两行，
写在本目录 README.md 的「LLM 怎么接」一节。

刻意**不做**的三件事（做了就不是最小示例，而是替你答题）：
  * 不给 `as_of` 编默认值 —— 槽位缺了当场退出。猜出来的那个值会让越界变成合法请求，
    而产物上完全看不出来。
  * 不把越界窗口截回 `as_of` —— 题面给什么就送什么，由网关判 403。自己截会让那次
    前视尝试在 access_log 上消失，而结算只认 access_log。
  * 题面没给的口径（这里是 `data_version`）标 `"unresolved"`，不填一个「常见默认值」。
    静默补全是被单独测量的一族行为。

`cli.ledger` 里**被拒的那些也在**，也照样进 `fetches`：如实记录尝试过的全部操作对你有利，
删掉不会让你得分 —— 合法性判定在评分器那边，它读的是网关日志，不是你的产物。
"""
import os, pathlib, re
import genebench_client as gb
from genebench_client import emit

TASK = pathlib.Path(os.environ.get("GENEBENCH_TASK_DIR", "/task"))
FIELDS = ["close", "volume"]
# 固定槽的三种写法（`- as_of: 2026-07-31`、表格行、`` `as_of` = ... ``）都收；收不到就退出。
_SLOT = r"[`*_\s|]*{k}[`*_\s]*[:：=|]+\s*[`\"']?(?P<v>[^\s`\"'|,)]+)"

def slot(text, key):
    m = re.search(_SLOT.format(k=re.escape(key)), text, re.I)
    if not m:
        raise SystemExit(f"INSTRUCTION.md 里没有槽位 {key!r}。**不猜默认值** —— 请按题面写法改 slot()。")
    return m.group("v")

def main():
    text = (TASK / "INSTRUCTION.md").read_text(encoding="utf-8")
    as_of, universe = slot(text, "as_of"), slot(text, "universe")
    start, end = slot(text, "start_date"), slot(text, "end_date")
    gb.set_as_of(as_of)                          # 启动时一次；三处都取不到就抛，不猜
    cli = gb.client()                            # 身份头与网关地址从环境变量取
    codes = cli.members(universe, as_of)[:5]     # PIT 成分，单日
    bars = cli.bars(codes, start, end, fields=FIELDS)   # fields 显式给；闭区间
    fetches = [emit.fetch(r["path"], r["params"], fetched_at=r["ts"],   # ts 来自响应头
                          rows=r["rows"], status=r["status"]) for r in cli.ledger]
    art = emit.emit_s1(fetches=fetches, as_of=as_of,
                       fields_obtained=sorted(c for c in bars.columns if c in FIELDS),
                       declarations={"calendar_id": "SSE", "universe": universe,
                                     "data_version": "unresolved"})
    out = art.write(TASK / "artifact.json")
    print(f"wrote {out}  fetches={len(fetches)}  rows={len(bars)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
