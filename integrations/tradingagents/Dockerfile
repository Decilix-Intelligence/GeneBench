# TradingAgents（TauricResearch，v0.4.0 / commit 2448d0a1）的 GeneBench 接入镜像。
#
# 构建上下文是 f02 上的 /data/genebench_runner/build/tradingagents/，里面要有三样：
#   tradingagents/        本目录（含 glue/）
#   genebench_client/     垫片（integrations/genebench_client）
#   TradingAgents-2448d0a12576f9b2ddcd5980a0630833423d1e1b.tar.gz
#                         源码压缩包 —— **codeload.github.com 在 f02 的构建网里不可达**
#                         （实测 curl 超时），所以不在 Dockerfile 里 clone/curl：
#                         在本地 Mac 下载 → scp 到 f01 → scp 到 f02 → 这里 COPY 进去。
#                         sha256 在下面逐字核对，核不上当场断。
#
#   在 f01：
#     scp -r integrations/tradingagents integrations/genebench_client \
#            ljn@192.168.1.219:/data/genebench_runner/build/tradingagents/
#   在 f02（只许从 f01 进）：
#     cd /data/genebench_runner/build/tradingagents
#     docker build -t gb-tradingagents-u:r1 -f tradingagents/Dockerfile .
FROM gb-base:bookworm-r1

# ① 垫片（取数 + emit）。走镜像不走 exec 树。
#
# 基座 python:3.12-slim **没有 setuptools**，而 genebench_client 的
# build-backend 就是 setuptools.build_meta：照 integrations/README §1② 那三行
# 直接 `--no-index --no-build-isolation` 会当场
# `BackendUnavailable: Cannot import 'setuptools.build_meta'`（本卡实测，已记票据）。
# 所以先把构建后端装上（**这一步走 index，构建期出网是允许的**），
# 垫片本身仍然 `--no-index`：它不在任何 index 上，也不该去公网找。
RUN pip install --no-cache-dir "setuptools>=61" wheel
COPY genebench_client/ /opt/genebench_client/
RUN pip install --no-cache-dir --no-index --no-build-isolation /opt/genebench_client

# ② 上游本体。**先核字节再装** —— 版本号不是钉，摘要才是。
ARG TA_COMMIT=2448d0a12576f9b2ddcd5980a0630833423d1e1b
ARG TA_SHA256=f4f81e7538992b094a0610d38c919cc2777344bf4ebee55d740818fc323db94d
COPY TradingAgents-${TA_COMMIT}.tar.gz /tmp/ta.tar.gz
RUN set -eux; \
    echo "${TA_SHA256}  /tmp/ta.tar.gz" | sha256sum -c -; \
    mkdir -p /opt/src; tar xzf /tmp/ta.tar.gz -C /opt/src; \
    pip install --no-cache-dir "/opt/src/TradingAgents-${TA_COMMIT}"; \
    rm -f /tmp/ta.tar.gz

# ③ 接线层（不改上游源码：monkeypatch vendor 表 + 配置 + 入口）。
#
# **COPY 会原样带上宿主的文件权限**，而 $GENEBENCH_ROOT 全树受红线 5 守门、
# 一律是 0600 —— 于是接线层进了镜像也是 0600，而容器以**非 root** 跑：
# `python3: can't open file '/opt/tradingagents_glue/run.py': [Errno 13] Permission denied`，
# 两臂 13 秒退出、`no_artifact`（本卡第一次真跑就是这么挂的，已记票据）。
# 所以 COPY 之后必须显式放开读权限。
COPY tradingagents/glue/ /opt/tradingagents_glue/
RUN chmod -R a+rX /opt/tradingagents_glue

# 容器以非 root 跑、HOME 不可写：全部指到可写层，**不要指到 /task 下**
# （那会往 run dir 的 work/ 里多放文件，破 P8 文件集封闭）。
ENV HOME=/tmp/h \
    XDG_CACHE_HOME=/tmp/h/.cache \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TRADINGAGENTS_RESULTS_DIR=/tmp/ta/logs \
    TRADINGAGENTS_CACHE_DIR=/tmp/ta/cache \
    TRADINGAGENTS_MEMORY_LOG_PATH=/tmp/ta/memory/trading_memory.md

WORKDIR /task
