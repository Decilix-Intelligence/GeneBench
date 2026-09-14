# 来源：f02 `/data/genebench_runner/build/cx/Dockerfile`（由 build/harness_build.sh 生成）。
# **内容一字未改**，抄回仓库只为让镜像的来历可复核 —— 构建仍在 f02 跑（f01 没有容器运行时）。
#   镜像名 gb-cx-u:r1
#   digest sha256:961e3878b28fc13ef2600254c4c4cbaceb7c337e2944fc173eaba1335752561a
#   基座   gb-base:bookworm-r1（统一基座，N-62）
# ↓↓↓ 以下为原文
FROM gb-base:bookworm-r1
RUN npm install -g "@openai/codex@0.153.2" 2>&1 | tail -3 && codex --version
