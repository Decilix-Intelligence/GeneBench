# 来源：**本仓库自建**（阶段三 3.2，2026-09-06）。与 codex/openhands 那两份不同 ——
# 它们是从 f02 的 build/ 抄回来的，这一份自始至终就是构建源本身：
# `harnesses/build.sh claude-code` 读的就是这个文件，没有第二份。
#   镜像名 gb-claude-code-u:r1
#   digest sha256:51f06443cc7a61322360c4eb38bc868713d763be3a5fb170f438a20cf2be466c（2026-09-06 在 f02 用**这一份**构建出来的）
#   基座   gb-base:bookworm-r1（统一基座，N-62）
#   包     @anthropic-ai/claude-code@2.1.263（npm，2026-09-06 的 latest）
#          dist.shasum    724f3282ee21318b227a6a20cbc66af331ee0fa4
#          dist.integrity sha512-kvvBK6/69iTRYnq0TKVyxVZs1CxYCJGojshQSP+2qaDb66A2xtI4zbCuqkZUWLkFGmHSRqhFf/ATpzH2UNKcwg==
#          engines.node   >=22.0.0 —— 基座是 node v22.23.2，够；换基座时先核这一条，
#                         不够的表现是 npm 装得下、`claude` 一跑就报引擎不符。
#   行情库 无（红线：被测系统必须经数据网关取数）
# ↓↓↓ 以下为构建原文
FROM gb-base:bookworm-r1
RUN npm install -g "@anthropic-ai/claude-code@2.1.263" 2>&1 | tail -3 && claude --version
