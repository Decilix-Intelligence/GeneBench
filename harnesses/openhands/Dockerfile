# 来源：f02 `/data/genebench_runner/build/oh/Dockerfile`（由 build/harness_build.sh 生成）。
# **内容一字未改**，抄回仓库只为让镜像的来历可复核 —— 构建仍在 f02 跑（f01 没有容器运行时）。
#   镜像名 gb-oh-u:r1
#   digest sha256:ccfae0c3fd9164fbd460396f99e8d1dc935eea79d00779755124d3884abf6f18
#   基座   gb-base:bookworm-r1（统一基座，N-62）
# ↓↓↓ 以下为原文
FROM gb-base:bookworm-r1
RUN pip install --no-cache-dir "openhands-ai==1.11.0" 2>&1 | tail -3 && python -c "import openhands.sdk; print('oh ok')"
