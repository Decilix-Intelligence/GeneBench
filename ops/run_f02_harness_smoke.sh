#!/usr/bin/env bash
# 通用 harness 的容器内验收（裁定 2026-09-04）：**镜像 + 调用命令**，不做 §10 适配层。
#
# 核两件 A 档核不了的事：
# ① 版本命令（harness 类 Pin 的唯一核验点 —— 它没有我们 import 的符号）；
# ② **工具调用**能不能用 —— 判据不是「模型答了话」，是「它调了工具、
#    读到了文件、并把结果写了出来」。前者只证明聊天通道通。
set -euo pipefail
D=${D:-/data/genebench_runner/fwprobe/cxrun}
SECRETS=${SECRETS:-$HOME/.config/genebench/secrets.env}
CX_IMG=${CX_IMG:-gb-cx:0.153.2}
OH_IMG=${OH_IMG:-gb-oh:1.11.0}

echo "== 1. 版本命令（harness 类 Pin 的核验点）=="
docker run --rm --network none "$CX_IMG" codex --version
docker run --rm --network none "$OH_IMG" python -c \
  "import importlib.metadata as m; print('openhands-ai', m.version('openhands-ai'))"

echo
echo "== 2. Codex CLI × DeepSeek 工具调用实测 =="
[ -f "$SECRETS" ] || { echo "缺 $SECRETS"; exit 2; }
[ -f "$D/compose.yml" ] || { echo "缺 $D/compose.yml（先跑一次准备脚本）"; exit 2; }
rm -f "$D"/log/*.jsonl
set -a; . "$SECRETS"; set +a
export GENEBENCH_MODEL_API_KEY="$DEEPSEEK_API_KEY"
cd "$D"
docker compose -f compose.yml up -d gateway >/dev/null
trap 'docker compose -f "$D/compose.yml" down -v >/dev/null 2>&1' EXIT
sleep 3
docker compose -f compose.yml run --rm task 2>&1 | tail -8

echo
echo "== 3. 边车侧证据 =="
cd /data/genebench_runner/exec && D="$D" python3 - <<'PY'
import os, sys
sys.path.insert(0, ".")
from runner.c42 import llm_trace as LT
t = LT.load(os.environ["D"])
assert t, "llm_log 空"
u = LT.usage_totals(t)
assert u and u["total_tokens"] > 0, f"usage 抽不出来：{u}"
print(f"steps={LT.steps(t)} usage={u}")
paths = {r.get("path") for r in LT.calls(t) or []}
print("上游路径:", sorted(paths))
assert paths == {"/v1/responses"}, \
    f"Codex 0.153.2 走的是 Responses API；路径变了说明上游或配置改了：{paths}"
PY
echo
echo "通用 harness 验收过：版本可核、工具调用链通、边车侧有 usage 证据。"
