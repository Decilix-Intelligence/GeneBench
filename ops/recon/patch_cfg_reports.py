"""给 genebench_config 加一个 REPORTS 常量(卡 1.1-reconcile 的人读报告目录)。

刻意做成**幂等的定点插入**而不是整文件覆盖:同一时间可能有别的卡在改这个文件,
整文件推上去会把别人的改动抹掉。
"""
import pathlib
import sys

TARGET = pathlib.Path(__file__).resolve().parents[2] / "genebench_config.py"
src = TARGET.read_text(encoding="utf-8")

if "REPORTS" in src:
    print("already patched, no-op")
    sys.exit(0)

ANCHOR_ALL = '    "OPS",\n'
NEW_ALL = '    "OPS",\n    "REPORTS",\n'
ANCHOR_DEF = '''#: 运维:tickets.md / progress.md / 特权事项
OPS: Path = REPO / "ops"
'''
NEW_DEF = ANCHOR_DEF + '''
#: 人读报告目录(卡 1.1 的对账报告等)。小文本、进 git、会被原样贴给人看,
#: 所以和 `ops/` 一样留在 REPO 里,不落 `SNAPSHOTS`。
REPORTS: Path = OPS / "reports"
'''

for anchor in (ANCHOR_ALL, ANCHOR_DEF):
    if src.count(anchor) != 1:
        raise SystemExit(f"锚点不唯一或不存在,拒绝改:{anchor!r}")

src = src.replace(ANCHOR_ALL, NEW_ALL).replace(ANCHOR_DEF, NEW_DEF)
TARGET.write_text(src, encoding="utf-8")
print("patched", TARGET)
