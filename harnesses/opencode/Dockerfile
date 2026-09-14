# 来源：**本仓库自建**（阶段三 3.2-opencode，2026-09-07）。构建源就是这一份 ——
# `harnesses/build.sh opencode` 读的是本文件，没有第二份。
#   镜像名 gb-opencode-u:r1
#   digest sha256:20ac2e3617670148602b7cc40c8e1e53910499e322572ebd1cd9bb15d48536ca（2026-09-07 在 f02 用**这一份**构建）
#   基座   gb-base:bookworm-r1（统一基座，N-62）
#   包     opencode-ai@1.18.26（npm；2026-09-01 发布。latest 是 2026-09-04 的 1.18.29，
#          特意退一格取放了几天的那一版）
#          dist.shasum    ffdac376880c2a6b8a58fcbbc1445dbb1f79aa09
#          dist.integrity sha512-XFPIj/yJZN8eBi4+uTjsnYAd/QezCM+/OUa3JbtL7tKQF4fGHR4onZx2d6oUGqbVs4CNONQ8QFKejeW+qVJIEA==
#          注意：opencode-ai 这个包本身只有 7.8 KB（启动器 + postinstall），真正的可执行体是
#          optionalDependencies 里的 **opencode-linux-x64@1.18.26** —— 一个 Bun 编译的单文件二进制，
#          解包 184,625,280 字节（~176 MB），由 postinstall.mjs 按平台挑出来硬链接成 bin/opencode.exe。
#          所以镜像会比别的 harness 大一截（f02 实测 gb-opencode-u:r1 约 1.1 GB DISK USAGE），这是预期的。
#          postinstall.mjs 里没有任何 fetch / http(s):// / 下载 URL，唯一的网络动作是 npm 自身 ——
#          **构建不需要 GitHub**（f02 上 GitHub 可达性对本 harness 不构成风险），npm 够了。
#   运行期 **不需要出网**：@ai-sdk/openai-compatible 已经打进二进制里，自定义 provider 不会在运行期
#          npm/bun install（f02 上用 `docker run --network none` 实测跑通，见 README §4.1）。
#   行情库 无（红线：被测系统必须经数据网关取数）
# ↓↓↓ 以下为构建原文
FROM gb-base:bookworm-r1
RUN npm install -g "opencode-ai@1.18.26" 2>&1 | tail -3 && opencode --version
