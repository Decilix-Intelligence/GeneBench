#!/bin/sh
# example_minimal 的本地走查：在 f01 上**不起容器**把它跑一遍，打生产网关，过协议 validator。
#
# 为什么不需要 gateway_lock：这是一次几十个请求以内的只读走查（任务书明说
# 「垫片的单元测试直接打生产网关（轻量、几十次请求）不需要锁」），并且用**独立身份**
# （run_id / config_id 见下），不与任何真跑的切片键冲突。
#
#   cd /data/shared/genebench/repo && sh integrations/example_minimal/smoke.sh
set -e
umask 077                       # 红线 5：$GENEBENCH_ROOT 下建的东西必须 go-rwx

GB=${GENEBENCH_ROOT:-/data/shared/genebench}
REPO=${REPO:-$GB/repo}
PY=${PY:-$GB/env/bin/python}
T=$GB/scratch/example_minimal/task

rm -rf "$GB/scratch/example_minimal"
mkdir -p "$T/log"

# ── 一份假题面。真题面由 genetask 的渲染器写出，槽位名是一样的。 ──────────
cat > "$T/INSTRUCTION.md" <<'MDEOF'
# S1 取数留痕（example_minimal 的走查题面，不是真题）

- as_of: 2026-07-31
- universe: csi300
- start_date: 2026-07-01
- end_date: 2026-07-31

把你实际发出去的每一次网关请求记进 `payload.fetches`，产物写到 `/task/artifact.json`。
本题**没有**给 `data_version` 的口径。
MDEOF

# ── 身份：独立 run_id，好在 access_log 里单独切片 ────────────────────────
GENEBENCH_TASK_DIR="$T";                       export GENEBENCH_TASK_DIR
GENEBENCH_GATEWAY=${GENEBENCH_GATEWAY:-http://192.168.1.48:18080}; export GENEBENCH_GATEWAY
GENEBENCH_TASK_ID=example-minimal-smoke;       export GENEBENCH_TASK_ID
GENEBENCH_CONFIG_ID=example-minimal-smoke;     export GENEBENCH_CONFIG_ID
GENEBENCH_RUN_ID=exmin.smoke.$$;               export GENEBENCH_RUN_ID
GENEBENCH_ARM=strict;                          export GENEBENCH_ARM
PYTHONPATH="$REPO/integrations/genebench_client/src${PYTHONPATH:+:$PYTHONPATH}"; export PYTHONPATH
PYTHONDONTWRITEBYTECODE=1;                     export PYTHONDONTWRITEBYTECODE

cd "$REPO"                      # 生成器要 import genetask/，从仓库根跑

echo "== 跑 run.py（run_id=$GENEBENCH_RUN_ID）"
"$PY" "$REPO/integrations/example_minimal/run.py"

# ── 造一份 strict 臂的 /task/protocol/ ────────────────────────────────────
# 它有**五**件东西，不是一件：validate_artifact.py 加**逐题生成的四份规则 JSON**
# （artifact_schema / contract / payload_depends_on / task）。真跑时这四份由注入器
# 在 f01 生成后放进 bundle；这里照同一条路生成，所以走查过的就是容器里那一份。
#   踩过的坑：只 cp 一个 validate_artifact.py 过去，它会当场
#   「规则文件缺失：…/artifact_schema.json —— validator 不猜规则，缺一个就不跑」。
#   那是**对的行为**（不猜规则），不是环境问题。
mkdir -p "$T/protocol"
cp "$REPO/ops/protocol/geneprotocol_v1/validate_artifact.py" "$T/protocol/"

# `declared` 只放题面**真的给了口径**的那些键。这里故意不给 data_version ——
# 于是「契约必填集 − 任务声明集」= {data_version}，validator 会要求产物把它标
# "unresolved"（run.py 正是这么写的）。给全了这道走查就测不到三态那一层。
GB_TASK_JSON='{"task_id": "example-minimal-smoke", "stage": "S1",
               "declared": {"calendar_id": "SSE", "universe": "csi300"}}'
export GB_TASK_JSON
PYTHONDONTWRITEBYTECODE=1 "$PY" - "$T/protocol" <<'GBRULES'
import json, os, sys
from genetask.protocol_rules import write_rules
got = write_rules(json.loads(os.environ["GB_TASK_JSON"]), sys.argv[1])
print("   规则四件：" + ", ".join(sorted(got)))
GBRULES

echo "== 过协议 validator（strict 臂容器里的那一份）"
"$PY" "$T/protocol/validate_artifact.py" "$T/artifact.json" --rules-dir "$T/protocol"

echo "== 产物"
head -c 400 "$T/artifact.json"; echo

chmod -R go-rwx "$GB/scratch/example_minimal"
echo "SMOKE-OK  产物在 $T/artifact.json"
