#!/usr/bin/env bash
# SIM-N（卡 4.4 §5）：从 f02 的**任务容器**（internal 网络、只经边车）打 /sim/state。
#
# 为什么不能在 A 档测：判据是「它挂在网关**同端口**下、任务容器**经既有白名单**够得着」
# —— 那需要真的起网关、真的起容器、真的走边车。TestClient 测不了「同端口」。
#
# 这一跑顺带把卡 4.3 的 ID-1..ID-5 端到端验了：agent 不发身份头 / 伪造身份头，
# 网关看到的都是 runner 真值（边车先剥后注）。
set -euo pipefail
D=${D:-/data/genebench_runner/fwprobe/simn}
docker run --rm --network none -v "$(dirname "$D"):/x" alpine:3.20 \
  sh -c "rm -rf /x/$(basename "$D")" >/dev/null 2>&1 || true
install -d -m 700 "$D/work" "$D/log"
cp /data/genebench_runner/exec/runner/c41/egress_proxy.py "$D/"
cp /data/genebench_runner/fwprobe/sim_n.py "$D/work/agent.py"

cd /data/genebench_runner/exec && python3 - <<'PY'
import os, pathlib, sys
sys.path.insert(0, ".")
from runner.c41 import runner_core as RC
D = pathlib.Path(os.environ.get("D", "/data/genebench_runner/fwprobe/simn"))
text = RC.format_compose(
    task_id="s8-cor-01", run_id="simn.r01", project="gb-simn", arm="open",
    config_id="cfg-simn", image="python:3.11-alpine", command="python3 /task/agent.py",
    task_subnet="172.31.250.0/24", egress_subnet="172.31.251.0/24", gateway=RC.GATEWAY,   # 与 runner 的分配池错开（与 A1 并跑时 Pool overlaps，2026-09-05）
    proxy_py=str(D / "egress_proxy.py"), h11_dir="/data/genebench_runner/exec/vendor/h11",
    model_upstream="api.deepseek.com", max_calls=1, max_tokens=1,   # 边车只认 registry 的上游（§15 同源）；SIM-N 不碰模型，预算闸给 1 只是让它能起来
    workdir=str(D / "work"), logdir=str(D / "log"))
bad = RC.lint_compose(text, expect_workdir=D / "work", runs_root=D.parent)
assert not bad, bad
(D / "compose.yml").write_text(text)
print("lint 九条 + L-10 全过")
PY

cd "$D"
export GENEBENCH_MODEL_API_KEY="${GENEBENCH_MODEL_API_KEY:-sk-simn-no-model}"   # 边车启动要这个变量在（模型反代用）；SIM-N 不碰模型，给个占位
docker compose -f compose.yml up -d gateway >/dev/null
trap 'docker compose -f "$D/compose.yml" down -v >/dev/null 2>&1' EXIT
sleep 3
docker compose -f compose.yml run --rm task
