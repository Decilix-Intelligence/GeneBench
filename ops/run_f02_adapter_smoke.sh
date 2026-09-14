#!/usr/bin/env bash
# 卡 4.2 §10/§11 的**容器内**验收。跑在 f02（执行面），A 档跑不到的那部分。
#
# 四条容器测试的纪律（2026-09-04 升级为「有实证的纪律」）在这里延续：
# **规格预言了一个失败形态不等于实现免疫** —— 本脚本的第一次运行就抓到
# 「原生数据路径扫描器是恒绿的」（它只看直接 import，而原生工具隔一跳才到 yfinance）。
set -euo pipefail
EXEC=/data/genebench_runner/exec
PROBE=/data/genebench_runner/fwprobe
PROVIDER=/data/genebench_runner/provider/qlib_provider_54fdda39
RD_IMG=${RD_IMG:-gb-probe-rd:0.8.0}
#: **TauricResearch 的 v0.4.0**，从 codeload 的 tag 压缩包装。
#: 不是 PyPI 上那个同名包（Mai0313/tradingagents，3 stars）—— 见 N-51。
TA_IMG=${TA_IMG:-gb-probe-ta:tauric-v0.4.0}

echo "== 1. 上游钉死：两个框架各四条判别力 =="
for pair in "$RD_IMG rdagent_q" "$TA_IMG tradingagents"; do
  set -- $pair
  docker run --rm --network none --user "$(id -u):$(id -g)" -e HOME=/tmp \
    -v "$EXEC:/exec:ro" \
    -v "$PROBE/verify_pin.py:/v.py:ro" "$1" python /v.py "$2"
done

echo
echo "== 2. RD-Agent(Q) 降级冒烟：冻结 provider → 框架执行器 → 转录 → 交叉核 =="
# 容器**必须**以调用者的 uid 跑：以 root 跑会把 root 属主的文件写进 bind mount，
# 之后 harness（非 root）连删都删不掉。实测：不加 --user 时上一轮的
# result.h5 / pickle_cache 全是 root:root，`rm -rf` 报 Permission denied。
# 真 compose 今天**没有**这条（N-48），本脚本先自己守住。
UIDGID="$(id -u):$(id -g)"
docker run --rm --network none -v "$PROBE:/probe" alpine:3.20 \
  sh -c 'rm -rf /probe/tasksmoke' >/dev/null 2>&1 || true
install -d -m 700 "$PROBE/tasksmoke"
docker run --rm --network none --user "$UIDGID" -e HOME=/task -v "$EXEC:/exec:ro" \
  -v "$PROBE/tasksmoke:/task" -v "$PROVIDER:/task/provider:ro" \
  -v "$PROBE/smoke_rd.py:/s.py:ro" "$RD_IMG" python /s.py

echo
echo "== 3. TradingAgents 降级冒烟：§11.2 替换缝（含非空证明与混入必红）=="
docker run --rm --user "$UIDGID" -e HOME=/tmp -v "$EXEC:/exec:ro" \
  -v "$PROBE/smoke_ta.py:/s.py:ro" "$TA_IMG" python /s.py

echo
echo "全部通过。**这两条绿灯证明的是链路与数据面替换，不是模型**（§18.3 的措辞要求）："
echo "  RD-Agent(Q)：「LLM 写因子代码」那一步被换成给定代码，其余全部真跑；"
echo "  TradingAgents（TauricResearch v0.4.0）：图跑不动（无 LLM 凭据），证明的是 vendor 表的 11 个方法一个不留地被换掉、route_to_vendor 真派发到网关、PIT 守卫在线。"
