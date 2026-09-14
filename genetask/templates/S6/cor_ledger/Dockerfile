FROM python:3.12-slim-bookworm@sha256:0000000000000000000000000000000000000000000000000000000000000000
# 依赖一律在构建期装（构建时联网、运行时断网，卡 4.1 L-8）。真 digest 在 f02 export 时钉。
#
# **统一基座**（N-62 裁定 2026-09-05）。为什么不是三个 harness 各用各的官方基座：
# 三条配置的全部意义是「同一模型、三种 harness，**固定模型效应**」。
# 实测三个基座是 python:3.12-slim / node:22-slim / RD-Agent 自带，
# pandas 只有 RD 那个有、且版本与题面钉的不一致 —— 那样主表上「harness 差异」
# 这一列里就混进了运行时差异，而 S2/S3/S7 的产出是 parquet/csv 数值，
# pandas 与 pyarrow 版本恰恰会影响它们。
#
# python 取 3.12（OpenHands 官方基座就是 3.12；题面原来钉 3.11 没有特殊理由）。
# 数值栈取**三个 harness 要求里最高的那个**（RD-Agent 的 2.3.3 / 25.0.1）。
ARG NODE_VERSION=22.23.2
ARG NODE_SHA256=d60acfe00a2932254bb0ad20e01b0d74397a0875595de719654b214f4b03f307
# Node 走**官方 tarball + 钉 sha256**，不走 `curl | bash` 的安装脚本 ——
# 后者是一条无法复核的供应链入口，而本项目对 npm 包都钉 dist_integrity。
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends curl ca-certificates xz-utils; \
    curl -fsSLo /tmp/node.tar.xz "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz"; \
    echo "${NODE_SHA256}  /tmp/node.tar.xz" | sha256sum -c -; \
    tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1; \
    rm -f /tmp/node.tar.xz; \
    apt-get purge -y curl xz-utils; apt-get autoremove -y; rm -rf /var/lib/apt/lists/*; \
    node --version; npm --version
RUN pip install --no-cache-dir pandas==2.3.3 pyarrow==25.0.1
COPY tests/ /opt/tests/
WORKDIR /task
CMD ["sh", "-c", "sleep 3600"]
