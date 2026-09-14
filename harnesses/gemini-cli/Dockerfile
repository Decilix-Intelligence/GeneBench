# 来源：**本仓库自建**（阶段三 3.2 harness「Gemini CLI」，2026-09-06）。
# 与 codex/openhands 那两份不同 —— 它们是从 f02 的 build/ 抄回来的，
# 这一份自始至终就是构建源本身：`harnesses/build.sh gemini-cli` 读的就是这个文件，
# 没有第二份。
#   镜像名 gb-gemini-cli-u:r1
#   digest sha256:03d5bddf2502257c3b4690ae8cf3813da07d0002e0d529c1c762e96f008a7108（2026-09-06 在 f02 用**这一份**构建出来的）
#   基座   gb-base:bookworm-r1（统一基座，N-62）
#   包     @google/gemini-cli@0.58.0（npm，2026-09-06 的 latest）
#          dist.shasum    31fdcb4e46f2185519fa2e131a3901f8ffa1989a
#          dist.integrity sha512-++LtUYMcLE8dVxMcuwv6kIp8+h6z+std/7iVE+vSunkrwNDaWMFkWw/psv2RSySWjr2A1SsEEIGCK0xULWY2sA==
#          unpackedSize   97,987,180 字节 / 449 个文件（bundle 自带 docs/，
#                         「这一版到底支持哪些环境变量」是从它里面查出来的，不是读网上的文档）
#          engines.node   >=20 —— 基座是 node v22.23.2，够；换基座时先核这一条，
#                         不够的表现是 npm 装得下、`gemini` 一跑就报引擎不符。
#   行情库 无（红线：被测系统必须经数据网关取数）
# ↓↓↓ 以下为构建原文
FROM gb-base:bookworm-r1
RUN npm install -g "@google/gemini-cli@0.58.0" 2>&1 | tail -3 && gemini --version
