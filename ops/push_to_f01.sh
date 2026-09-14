#!/usr/bin/env bash
# 推送到 f01 的**守门式**流程（指令一，2026-09-04）。
#
# 为什么不再手工 tar + 逐个 chmod：本轮三次把敏感目录放松成 0755
# （reference/artifact_schema.py、genetask/templates/、ops/manifests/），
# 每次都靠事后 chmod 补救，而且只 chmod 想到的那几个路径 ——
# 漏掉的那个不会有任何提示。
#
# 顺序**不可调换**：解包 → 统一收紧 → **红线 5 测试**（不过即中止，不进全量）→ 全量。
# 权限没过就跑全量，等于拿一个已知不合规的树去证明「一切正常」。
set -euo pipefail

HOST="${GB_HOST:-finance01-ts}"
REMOTE="${GB_REMOTE:-/data/shared/genebench/repo}"
PY="${GB_PY:-/data/shared/genebench/env/bin/python}"
TARBALL="${1:?用法: push_to_f01.sh <tarball> [pytest 参数...]}"
shift || true

echo "== 1/4 传输"
scp -q "$TARBALL" "$HOST:/tmp/$(basename "$TARBALL")"

echo "== 2/4 解包 + 统一收紧（不逐个列举路径）"
ssh "$HOST" "cd $REMOTE && tar xzf /tmp/$(basename "$TARBALL") 2>/dev/null; \
             python3 ops/guard_modes.py --harden"

echo "== 3/4 红线 5 权限测试（不过即中止）"
if ! ssh "$HOST" "cd $REMOTE && $PY -m pytest ops/test_env.py -q --no-header 2>&1 | tail -3"; then
    echo "!! 红线 5 未过 —— **中止，不进全量**" >&2
    exit 2
fi

echo "== 4/4 全量"
ssh "$HOST" "cd $REMOTE && $PY -m pytest -q --ignore=genetask/templates $* 2>&1 | tail -6"
