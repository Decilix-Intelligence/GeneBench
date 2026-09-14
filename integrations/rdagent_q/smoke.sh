#!/bin/sh
# rdagent_q 的走查：**在真镜像里**把整条链路跑一遍（模型那一步换成给定代码）。
#
#   cd /data/shared/genebench/repo && sh integrations/rdagent_q/smoke.sh
#
# 它验的是链路，不是模型：题面 → 网关取数 → qlib 面板 → RD-Agent 的
# FactorFBWorkspace 真执行 → result.h5 → values.parquet → artifact.json →
# 协议 validator。「模型写 factor.py」那一步由 smoke_factor.py 顶上（降级路径，
# 与 runner/c42/adapters/rdagent_q/adapter.py 同形，N-105）。
#
# 为什么在 f02 的容器里跑而不是在 f01：rdagent 只装在镜像里，f01 的 venv 没有它。
# 顺带的好处是走查跑的就是**真镜像**，不是一份"看起来一样"的环境。
# 为什么不需要 gateway_lock：几十个只读请求，且用独立的 run_id/config_id 切片
# （施工契约 B6 的例外条款）。
set -e
umask 077                       # 红线 5：$GENEBENCH_ROOT 下建的东西必须 go-rwx

GB=${GENEBENCH_ROOT:-/data/shared/genebench}
REPO=${REPO:-$GB/repo}
PY=${PY:-$GB/env/bin/python}
F02=${F02:-ljn@192.168.1.219}
RB=/data/genebench_runner/build/rdagent_q/smoke
IMG=${IMG:-gb-rdagent_q-u:r1}
OUT=$GB/scratch/2.6/smoke

rm -rf "$OUT"; mkdir -p "$OUT"

# ── 一份**走查专用的假题面**。它的因子故意不是任何一道被计分的真题 ────────
# （smoke_factor.py 的 docstring 说明了理由：这份代码会随构建上下文上执行面。）
cat > "$OUT/INSTRUCTION.md" <<'MDEOF'
按下列声明完成任务。
任务（S3）：按下面的源方言原文实现因子，在计算窗口内逐截面计算，产出 S3 artifact。
因子：demo.open_ret5
源方言原文：`(open / delay(open, 5) - 1)`
as_of=2026-07-31
window=2026-06-01 到 2026-07-31
universe=csi300
本次任务的口径（逐项）：
- required_fields=[open]（只需要开盘价，接口值 [open]）
- lookback=5（回看窗口 5 个交易日，接口值 5）
- eval_frequency=daily（按日频评估，接口值 daily）
- operator_semantics={delay: shift_n_trading_days}（delay 是按交易日平移，接口值 {delay: shift_n_trading_days}）
- param_order=[series, window]（算子参数顺序，接口值 [series, window]）
- nonfinite_policy=propagate（Inf/NaN 原样传播，接口值 propagate）
- warmup_policy=null_until_full（回看窗口未满输出空值，接口值 null_until_full）
产出文件：/task/values.parquet（parquet），列按此顺序：date、code、value，按 date、code 升序排序，不写行索引，value 为 float64
产出路径：/task/artifact.json
MDEOF

RUN_ID=rdq.smoke.$$

echo "== 送到 f02（$RB）"
ssh -o ConnectTimeout=120 "$F02" "rm -rf $RB && mkdir -p $RB/task"
scp -q -o ConnectTimeout=120 "$OUT/INSTRUCTION.md" "$F02:$RB/task/"
scp -q -o ConnectTimeout=120 "$REPO/integrations/rdagent_q/smoke_factor.py" "$F02:$RB/"

echo "== 在 $IMG 里跑（降级路径：GB_RDAGENT_FACTOR_CODE）"
ssh -o ConnectTimeout=120 "$F02" "cd $RB && docker run --rm \
  --user \$(id -u):\$(id -g) \
  -v $RB/task:/task -v $RB/smoke_factor.py:/opt/smoke_factor.py:ro \
  -e HOME=/tmp/h -e PYTHONDONTWRITEBYTECODE=1 \
  -e GENEBENCH_GATEWAY=http://192.168.1.48:18080 \
  -e GENEBENCH_TASK_ID=rdagent-q-smoke -e GENEBENCH_CONFIG_ID=rdagent-q-smoke \
  -e GENEBENCH_RUN_ID=$RUN_ID -e GENEBENCH_ARM=strict \
  -e GB_RDAGENT_FACTOR_CODE=/opt/smoke_factor.py \
  $IMG sh -c 'mkdir -p /tmp/h && cd /task && python3 /opt/rdagent_q/run.py'" 2>&1 | tee "$OUT/run.log"

echo "== 取回产物"
scp -q -o ConnectTimeout=120 "$F02:$RB/task/artifact.json" "$OUT/"
scp -q -o ConnectTimeout=120 "$F02:$RB/task/values.parquet" "$OUT/"

echo "== 造一份 strict 臂的 /task/protocol/（validator + 逐题生成的四份规则 JSON）"
mkdir -p "$OUT/protocol"
cp "$REPO/ops/protocol/geneprotocol_v1/validate_artifact.py" "$OUT/protocol/"
GB_TASK_JSON='{"task_id": "rdagent-q-smoke", "stage": "S3",
  "declared": {"required_fields": ["open"], "lookback": 5, "eval_frequency": "daily",
               "operator_semantics": {"delay": "shift_n_trading_days"},
               "param_order": ["series", "window"], "nonfinite_policy": "propagate",
               "warmup_policy": "null_until_full"}}'
export GB_TASK_JSON
cd "$REPO"
PYTHONDONTWRITEBYTECODE=1 "$PY" - "$OUT/protocol" <<'GBRULES'
import json, os, sys
from genetask.protocol_rules import write_rules
print("   规则四件：" + ", ".join(sorted(write_rules(json.loads(os.environ["GB_TASK_JSON"]), sys.argv[1]))))
GBRULES

echo "== 过协议 validator（strict 臂容器里的那一份）"
"$PY" "$OUT/protocol/validate_artifact.py" "$OUT/artifact.json" --rules-dir "$OUT/protocol"

echo "== 产物"
head -c 600 "$OUT/artifact.json"; echo
chmod -R go-rwx "$GB/scratch/2.6"
echo "SMOKE-OK  产物在 $OUT/artifact.json"
