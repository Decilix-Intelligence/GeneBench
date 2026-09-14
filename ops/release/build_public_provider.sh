#!/usr/bin/env bash
# 形态 B：**在你自己的机器上**建一份 GeneBench 公开数据通道，然后跟我们的包比校验和。
#
#   ./ops/release/build_public_provider.sh --root ~/genebench --package ./genebench_public_provider_v1
#
# 比对通过 = 你不用信我们那个 tar.gz，你自己建的那份和它逐字节相同。
#
# 四段（每段都可以单独跑，中间断了直接重跑，取数与建集都能续）：
#   1 preflight  Python ≥ 3.10 / pip install baostock==0.9.3 / 检查包目录
#   2 fetch      按并集名单拉 baostock —— **交易时段拒绝启动**（判据在
#                ops/acceptance/card_2_5_fetch_union.py，本脚本不放宽它）
#   3 build      走 ops/build_public_channel.py 建表 / 可交易性 / provider
#   4 compare    与包里的 SHA256SUMS 逐文件比
#
# 全量取数 3,575 只要 7 小时以上，务必挑非交易时段（周末，或工作日 15:30 之后）。
# 已经有缓存时 2 会自动跳过已下载的票。
set -euo pipefail

ROOT=""; PACKAGE=""; STAGES="preflight,fetch,build,compare"; LIMIT=0; PY="${PYTHON:-python3}"
usage() {
  sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
  echo
  echo "选项：--root DIR --package DIR [--stages a,b,c] [--limit N] [--python PATH]"
  exit "${1:-0}"
}
while [ $# -gt 0 ]; do
  case "$1" in
    --root) ROOT="$2"; shift 2 ;;
    --package) PACKAGE="$2"; shift 2 ;;
    --stages) STAGES="$2"; shift 2 ;;
    --limit) LIMIT="$2"; shift 2 ;;
    --python) PY="$2"; shift 2 ;;
    -h|--help) usage 0 ;;
    *) echo "认不出的参数：$1" >&2; usage 2 ;;
  esac
done
[ -n "$ROOT" ] && [ -n "$PACKAGE" ] || usage 2

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ROOT="$(mkdir -p "$ROOT" && cd "$ROOT" && pwd)"
PACKAGE="$(cd "$PACKAGE" && pwd)"
export GENEBENCH_ROOT="$ROOT"
export PYTHONDONTWRITEBYTECODE=1
umask 077
has() { case ",$STAGES," in *",$1,"*) return 0 ;; *) return 1 ;; esac; }
say() { printf '\n=== %s === %s\n' "$1" "$(date -u +%FT%TZ)"; }

if has preflight; then
  say "1/4 preflight"
  "$PY" - <<'PYEOF'
import sys
assert sys.version_info >= (3, 10), f"要 Python ≥ 3.10，现在是 {sys.version.split()[0]}"
missing = []
for m in ("pandas", "pyarrow", "numpy", "duckdb"):
    try:
        __import__(m)
    except ImportError:
        missing.append(m)
assert not missing, f"缺依赖：{missing} —— pip install {' '.join(missing)}"
print("依赖齐")
PYEOF
  "$PY" -c "import baostock" 2>/dev/null || "$PY" -m pip install "baostock==0.9.3"
  "$PY" -c "import baostock, sys; print('baostock', getattr(baostock,'__version__','?'))"
  for f in SHA256SUMS MANIFEST.json provider/instruments/all.txt; do
    [ -f "$PACKAGE/$f" ] || { echo "[红] 包里缺 $f —— --package 指的不是解开的包目录？" >&2; exit 2; }
  done
  mkdir -p "$ROOT/scratch"; chmod 700 "$ROOT" "$ROOT/scratch"
  cp -f "$PACKAGE/universe/v1_union.txt" "$ROOT/scratch/v1_union.txt"
  chmod 600 "$ROOT/scratch/v1_union.txt"
  echo "并集名单 $(wc -l < "$ROOT/scratch/v1_union.txt") 行 → $ROOT/scratch/v1_union.txt"
fi

if has fetch; then
  say "2/4 fetch（非交易时段；全量约 7 小时，可续跑）"
  ARGS=(--root "$ROOT" --union "$ROOT/scratch/v1_union.txt")
  [ "$LIMIT" != "0" ] && ARGS+=(--limit "$LIMIT" --quotes-only)
  "$PY" "$REPO/ops/release/fetch_public_quotes.py" "${ARGS[@]}"
fi

if has build; then
  say "3/4 build（表 / 单位门 / 可交易性 / provider）"
  "$PY" "$REPO/ops/release/rebuild_public_provider.py" --root "$ROOT" --package "$PACKAGE"
fi

if has compare; then
  say "4/4 compare（与包里的 SHA256SUMS 逐文件比）"
  "$PY" "$REPO/ops/release/pack_public_provider.py" --root "$ROOT" --repo "$REPO" \
        --compare "$PACKAGE/SHA256SUMS"
fi

say "完成"
echo "你的 provider：$ROOT/snapshots/public_v1/qlib_provider"
