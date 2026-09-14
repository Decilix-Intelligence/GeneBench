# 来源：**本仓库自建**（阶段三 3.2 harness「Grok CLI」，2026-09-06）。
# 与 codex/openhands 那两份不同 —— 它们是从 f02 的 build/ 抄回来的，
# 这一份自始至终就是构建源本身：`harnesses/build.sh grok-cli` 读的就是这个文件，
# 没有第二份。
#   镜像名 gb-grok-cli-u:r1
#   digest sha256:262527929889632c7ca5546e0821c1bb0297e9b41151ce55bf1e56d8c12b8f0c（2026-09-06 在 f02 用**这一份**构建出来的）
#          **两次构建、两个 digest，都出自这一份**：上面这个是 2026-09-07 05:30 那次，
#          也是**真跑证据用的那一个**（bundle 的 image/Dockerfile 钉的就是它）；
#          05:41 因为断线重连后两个驱动脚本撞车又构建了一次，得到
#          sha256:41a726a459240ffacc48e3e78ddb6829fd5a03182375126186ecfe13e768d0a4，
#          f02 上的 tag gb-grok-cli-u:r1 现在指的是后者，前者作为悬空镜像还在。
#          两者的差别只可能来自 npm 当刻解析出的依赖树（^ 范围，随包无 lockfile），
#          不是这份文件变了 —— 这正是 README §3 那条「digest 钉的是构建那一刻的依赖树」。
#   基座   gb-base:bookworm-r1（统一基座，N-62）
#   包     grok-dev@1.1.7（npm，2026-09-06 的 latest；time.modified 2026-05-15）
#          dist.shasum    e67dc2739cd613ffdfc88b693ee8a36617b81171
#          dist.integrity sha512-x0VvjIrtJYjnxdTE4mqz2x9NUtNRra2BzlD7McNznM3Jxm1fI85RUC4MoOZX487hIbYmG/RCLifksEcSwrZ9oQ==
#          engines.node   >=18.0.0 —— **这条 engines 是错的，别信它**（见下面 bun 那段）
#          bin            grok -> dist/index.js
#   运行时 bun@1.4.2（npm，`npm i -g bun` 只是 2 个包：bun 壳 + 平台二进制，
#          全程走 registry.npmjs.org，**不碰 GitHub releases**，所以在 f02 装得上）
#
#   **为什么必须装 bun，而 package.json 的 engines 说 node>=18 就够**：
#     ① dist/index.js 的 shebang 是 `#!/usr/bin/env bun`；
#     ② dist 是 tsc 输出的 ESM，import 路径**不带扩展名**（`from "./agent/agent"`），
#        Node 的 ESM 解析器直接 ERR_MODULE_NOT_FOUND；
#     ③ 更硬的一条：dist/storage/db.js 第一行是 `import { Database } from "bun:sqlite"` ——
#        这是 Bun 独有的内建模块，Node 上没有等价物，任何 loader 补丁都绕不过去。
#     实机复现（f02，gb-base:bookworm-r1 容器内）：
#        `grok --help` → /usr/bin/env: 'bun': No such file or directory
#        `node $(npm root -g)/grok-dev/dist/index.js --help`
#            → Error [ERR_MODULE_NOT_FOUND]: Cannot find module '.../dist/agent/agent'
#     所以「engines.node>=18」只描述了语法层，没描述运行时依赖。**照它读会得出「装了就能跑」，
#     实际是装得上、一跑就没了。**
#
#   包里还有一条备选路：dist/grok-standalone（= dist/grok-bin，70,464,544 字节，
#   `bun build --compile` 出来的单文件二进制，随包发布）。它不需要另装 bun。
#   本 harness **没有**用它，理由：那条路上「跑的是哪一版 grok」只能靠二进制自报，
#   而走 `npm i -g bun + grok`，跑的就是 dist/ 里那些可读的 .js，出问题能直接读源码定位
#   （本卡的 GROK_MAX_TOKENS / recapsEnabled 两个坑都是这么读出来的）。
#
#   行情库 无（红线：被测系统必须经数据网关取数）
# ↓↓↓ 以下为构建原文
FROM gb-base:bookworm-r1
RUN npm install -g "bun@1.4.2" "grok-dev@1.1.7" 2>&1 | tail -3 \
 && bun --version \
 && timeout 60 grok --version </dev/null
