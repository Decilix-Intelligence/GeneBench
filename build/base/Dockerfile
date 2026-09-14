# GeneBench 统一基座 gb-base:bookworm-r1
# ---------------------------------------------------------------------------
# 这份 Dockerfile 就是构出 gb-base:bookworm-r1 的那一份。此前它只住在发布方
# f02 的 /data/genebench_runner/build/base/ 下、**不在仓库里** —— 于是外部用户
# clone 下来之后，harnesses/build.sh 会告诉他「去某台他没有的机器上构基座」。
# 2026-09-13 的 Mac 外部验收正是卡在这一条（缺件①）。搬进仓库之后，
# 一台只有 Docker 的干净机器光凭这棵树就能把基座构出来。
#
# 为什么要有统一基座（N-62 裁定 2026-09-05）：三条配置的全部意义是
# 「同一模型、三种 harness，**固定模型效应**」。三个 harness 各用各的官方基座时
# （python:3.12-slim / node:22-slim / RD-Agent 自带），pandas 只有 RD 那个有、
# 且版本与题面钉的不一致 —— 主表上「harness 差异」那一列里就混进了运行时差异，
# 而 S2/S3/S7 的产出恰恰是 parquet/csv 数值，pandas 与 pyarrow 版本会影响它们。
#
# python 取 3.12（OpenHands 官方基座就是 3.12；题面原来钉 3.11 没有特殊理由）。
# 数值栈取**三个 harness 要求里最高的那个**（RD-Agent 的 pandas 2.3.3 / pyarrow 25.0.1）。
#
# 依赖一律在构建期装（构建时联网、运行时断网，卡 4.1 L-8）。
#
# 构建：见同目录 README.md。多架构说明见 ops/reports/base_image_portability.md。
# ---------------------------------------------------------------------------

# 钉的是 **OCI image index**（manifest list）的 digest，不是某一个架构的镜像 digest。
# 实测（2026-09-13 直查 registry-1.docker.io）：该 index 有 10 条 manifest，
# 含 linux/amd64（sha256:9c47360a2a0355e2d…）与 linux/arm64/v8（sha256:d04f49f5882f49a3b…），
# 版本 3.12.14-slim-bookworm。也就是说**同一行 FROM 在 x86_64 与 Apple Silicon 上都解析得出**，
# docker 按构建平台自己挑那一条 —— 不需要为 arm64 换 digest。
FROM python:3.12-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254

# Node 走**官方 tarball + 钉 sha256**，不走 `curl | bash` 的安装脚本 ——
# 后者是一条无法复核的供应链入口，而本项目对 npm 包都钉 dist_integrity。
#
# **tarball 与 sha256 是按架构分的**：x64 与 arm64 是两个不同的包、两个不同的哈希。
# 2026-09-13 之前这里只钉了 x64 的那一个，于是在 Apple Silicon 上必然
# 「下到 arm64 的包、拿 x64 的哈希去核」→ sha256sum -c 当场失败。
# 两个值都取自 https://nodejs.org/dist/v22.23.2/SHASUMS256.txt（2026-09-13 实取，HTTP 200）。
ARG NODE_VERSION=22.23.2
ARG NODE_SHA256_AMD64=d60acfe00a2932254bb0ad20e01b0d74397a0875595de719654b214f4b03f307
ARG NODE_SHA256_ARM64=fff4078c5def658577f92c88db7db3bc0072924bfb93fe52c1e744a54e94abb8

# 架构从 `dpkg --print-architecture` 取，**不是** BuildKit 的 ${TARGETARCH}：
# f02 的 docker 29 没装 buildx（只有 docker-compose / docker-trust 两个 CLI 插件），
# 走的是 legacy builder，那里 TARGETARCH 不一定有值 —— 空值会让下面的 case 落到
# 「不支持的架构」分支，而真正的原因跟架构无关。dpkg 在两种 builder、
# 本机构建与 --platform 模拟构建下都给出正确的 amd64 / arm64。
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends curl ca-certificates xz-utils; \
    debArch="$(dpkg --print-architecture)"; \
    case "${debArch}" in \
      amd64) nodeArch=x64;   nodeSha="${NODE_SHA256_AMD64}" ;; \
      arm64) nodeArch=arm64; nodeSha="${NODE_SHA256_ARM64}" ;; \
      *) echo "!! 基座只支持 amd64 与 arm64，本次构建平台是 [${debArch}]。" >&2; \
         echo "   要加一个架构：去 https://nodejs.org/dist/v${NODE_VERSION}/SHASUMS256.txt" >&2; \
         echo "   取 node-v${NODE_VERSION}-linux-<arch>.tar.xz 那一行的 sha256，照上面的样子加一个 ARG 与一条 case。" >&2; \
         exit 1 ;; \
    esac; \
    curl -fsSLo /tmp/node.tar.xz "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-${nodeArch}.tar.xz"; \
    echo "${nodeSha}  /tmp/node.tar.xz" | sha256sum -c -; \
    tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1; \
    rm -f /tmp/node.tar.xz; \
    apt-get purge -y curl xz-utils; apt-get autoremove -y; rm -rf /var/lib/apt/lists/*; \
    node --version; npm --version

# requirements.txt = 直接依赖（题面钉的那两个）；constraints.txt = 连传递依赖一起钉死，
# 取自既有 gb-base:bookworm-r1 里的 `pip freeze`。两份分开的理由：
# 读者要看的是「这个基座为什么装 pandas/pyarrow」，而机器要的是「一字不差地重现」。
COPY requirements.txt constraints.txt /tmp/gb-base/
RUN pip install --no-cache-dir -r /tmp/gb-base/requirements.txt -c /tmp/gb-base/constraints.txt \
    && rm -rf /tmp/gb-base

WORKDIR /task
CMD ["sh", "-c", "sleep 3600"]
