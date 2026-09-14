#!/usr/bin/env bash
# f02 侧容器测试的**执行通道**（指令二，2026-09-04）：同步 → 触发 → 回传。
#
# T5/T10/T12/T15 是安全关键项，docker 已经在 f02 上（29.1.3 + compose 2.40.3）。
# 它们不能带 skip 进 M6。
#
# **搬什么、不搬什么**（红线：reference/ 与 scorer/ 不对执行面暴露）：
#   搬  runner/（inject、provider_adapter、c41、f02）、genetask/{bundle,pin}.py、
#       ops/protocol/（协议工件）、ops/guard_modes.py
#   不搬 reference/、scorer/、genetask/{schema,packager,render}.py（它们 import reference）
# 同步之后有一条**实测**断言：f02 上 `import reference` 必须失败。
set -euo pipefail

F02="${GB_F02:-finance02-ts}"
DEST="${GB_F02_ROOT:-/data/genebench_runner/exec}"
PY="${GB_F02_PY:-python3}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGE="$(mktemp -d "${TMPDIR:-/tmp}/gbf02.XXXXXX")"
trap 'rm -rf "$STAGE"' EXIT

echo "== 1/4 打包执行面代码（reference/ 与 scorer/ 不在其中）"
mkdir -p "$STAGE/pkg/genetask" "$STAGE/pkg/runner" "$STAGE/pkg/ops"
cp "$HERE/genetask/bundle.py" "$HERE/genetask/pin.py" "$STAGE/pkg/genetask/"
touch "$STAGE/pkg/genetask/__init__.py"
cp -r "$HERE/runner/." "$STAGE/pkg/runner/"
cp -r "$HERE/ops/protocol" "$STAGE/pkg/ops/"
cp "$HERE/ops/guard_modes.py" "$STAGE/pkg/ops/"
touch "$STAGE/pkg/ops/__init__.py"
# h11（裁定 2026-09-05：边车与网关跑**同一份**解析器）。f02 的 python3 没有它也没有 pip，
# 所以从网关环境那一份复制进 vendor/，注入器再从这里挂给边车（P7d）。只带 .py 与 py.typed。
H11_SRC="$("$HERE/../env/bin/python" -c 'import h11,os;print(os.path.dirname(h11.__file__))')"
mkdir -p "$STAGE/pkg/vendor/h11"
cp "$H11_SRC"/*.py "$STAGE/pkg/vendor/h11/"
[ -f "$H11_SRC/py.typed" ] && cp "$H11_SRC/py.typed" "$STAGE/pkg/vendor/h11/"
echo "   h11 $(ls "$STAGE/pkg/vendor/h11" | wc -l) 个文件进 vendor/"
# 兜底：打包内容里不得出现 reference/ 或 scorer/ 的源码
if find "$STAGE/pkg" -name "*.py" | xargs grep -l "^from reference\|^import reference" 2>/dev/null | grep -q .; then
    echo "!! 打包内容里有 import reference —— 中止" >&2
    exit 3
fi
tar czf "$STAGE/exec.tgz" -C "$STAGE/pkg" .

echo "== 2/4 同步到 f02:$DEST"
scp -q "$STAGE/exec.tgz" "$F02:/tmp/gb_exec.tgz"
ssh "$F02" "rm -rf $DEST && mkdir -p $DEST && tar xzf /tmp/gb_exec.tgz -C $DEST && \
            chmod -R go-rwx $DEST"

echo "== 3/4 实测：f02 上 import reference 必须失败"
if ssh "$F02" "cd $DEST && $PY -c 'import reference' 2>/dev/null"; then
    echo "!! f02 上能 import reference —— 答案面泄漏到执行面，中止" >&2
    exit 4
fi
echo "   ✅ import reference 失败（如期）"

echo "== 4/4 跑容器测试"
ssh "$F02" "cd $DEST && $PY runner/f02/verify_container.py ${*:-}"
