#!/usr/bin/env bash
# 凭据路径的端到端验收（裁定 (a)，2026-09-04）。跑在 f02，**要真调一次模型**。
#
# A 档测不了的那部分：真 key 到底有没有进容器、边车换 key 之后上游认不认、
# usage 抽不抽得出来、预算闸拦不拦得住。这四件事只有真跑才知道 ——
# 第一次跑就抓到两个：`llm_log` 因为 `_now()` 不存在**一条都没写**
# （响应正常返回，看起来一切都好），以及 chunked 响应让 `usage` 抽成 `{}`。
#
# **key 从不 echo**：它经进程环境传给 compose，compose 里只有 ${...} 引用。
set -euo pipefail
D=${D:-/data/genebench_runner/fwprobe/cred}
SECRETS=${SECRETS:-$HOME/.config/genebench/secrets.env}
[ -f "$SECRETS" ] || { echo "缺 $SECRETS —— 凭据由用户以环境变量落到 runner 配置"; exit 2; }

docker run --rm --network none -v "$(dirname "$D"):/x" alpine:3.20 \
  sh -c "rm -rf /x/$(basename "$D")" >/dev/null 2>&1 || true
install -d -m 700 "$D/work" "$D/log"
cp /data/genebench_runner/exec/runner/c41/egress_proxy.py "$D/"
cp /data/genebench_runner/fwprobe/cred_agent.py "$D/work/agent.py"

cd /data/genebench_runner/exec && D="$D" python3 - <<'PY'
import os, pathlib, sys
sys.path.insert(0, ".")
from runner.c41 import runner_core as RC
D = pathlib.Path(os.environ["D"])
text = RC.format_compose(
    task_id="s1-cor-01", run_id="cred.r01", project="gb-cred", arm="open",
    config_id="cfg-rdagent-deepseek", image="python:3.11-alpine",
    command="python3 /task/agent.py",
    task_subnet=RC.TASK_SUBNET, egress_subnet=RC.EGRESS_SUBNET, gateway=RC.GATEWAY,
    proxy_py=str(D / "egress_proxy.py"), workdir=str(D / "work"),
    logdir=str(D / "log"), model_upstream="api.deepseek.com",
    max_calls=5, max_tokens=5000)
bad = RC.lint_compose(text, expect_workdir=D / "work", runs_root=D.parent)
assert not bad, bad
(D / "compose.yml").write_text(text)
print("lint 全过（含 L-10 降权 / L-11 真 key 不进容器）")
PY

set -a; . "$SECRETS"; set +a
export GENEBENCH_MODEL_API_KEY="$DEEPSEEK_API_KEY"
cd "$D"
docker compose -f compose.yml up -d gateway >/dev/null
trap 'docker compose -f "$D/compose.yml" down -v >/dev/null 2>&1' EXIT
sleep 3
docker compose -f compose.yml run --rm task

echo
echo "== 宿主侧复核 =="
if grep -rqF "$DEEPSEEK_API_KEY" "$D" 2>/dev/null; then
  echo "!!! 真 key 出现在 run dir 里"; exit 1
fi
echo "真 key 不在 run dir（含 llm_log / compose.yml）✓"
grep -q 'GENEBENCH_MODEL_API_KEY: "${GENEBENCH_MODEL_API_KEY}"' compose.yml \
  && echo "compose 里是 \${...} 引用而非字面量 ✓"

cd /data/genebench_runner/exec && D="$D" python3 - <<'PY'
import os, sys
sys.path.insert(0, ".")
from runner.c42 import llm_trace as LT
t = LT.load(os.environ["D"])
assert t, "llm_log 空 —— 证据源没写出来（第一次跑就是这个）"
u = LT.usage_totals(t)
assert u and u["total_tokens"] > 0, f"usage 抽不出来（chunked 没解开？）：{u}"
print(f"llm_log：steps={LT.steps(t)} usage={u} 拒绝={len(LT.budget_denials(t))}")
print("tokens 交叉核（自报=网络侧）:", LT.cross_check_tokens(u["total_tokens"], t)["status"])
print("tokens 交叉核（自报离谱）:", LT.cross_check_tokens(u["total_tokens"] * 100, t)["status"])
PY
echo
echo "凭据路径过：真 key 只在边车，容器只有占位串，自带凭据被拒，usage 有网络侧证据。"
