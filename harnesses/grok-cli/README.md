# harness：Grok CLI（id = `grok-cli`）

> 一句话：**链路全通、模型也会说话，但它在 DeepSeek 上一步也走不动 ——
> `@ai-sdk/xai` 的流式 chunk schema 只认 xAI「一片 = 一次完整工具调用」的形状，
> DeepSeek（以及 OpenAI 本身）的标准分片被整片丢弃，于是每一次工具调用的参数都是 `{}`。
> 这不是模型差、也不是我们的边车，有假上游对照实验（§5）。所以 `config.yaml` 是 `enabled: false`。**

> 次要但同样会咬人的两条：运行时必须是 **Bun** 而不是 Node（包自己的 `engines` 是错的，§2）；
> bun 的运行时转译缓存默认往 `$HOME` 写 297 个文件，而 `HOME` 在 `/task` 下（§4⑤）。

四件文件：`Dockerfile` / `launch.json` / `config.yaml` / 本文件。通用规则见
[`harnesses/README.md`](../README.md)，这里只写 Grok CLI 独有的东西。

---

## 1. 这是哪个包（D-21 结案）

「Grok CLI」这个名字下有两个 npm 包，**选错了会去调一个停更 9 个月的实现**：

| npm 包 | latest | 最后发布 | 结论 |
|---|---|---|---|
| `@vibe-kit/grok-cli` | 0.0.34 | 2025-11-27 | **停更，不用**。只在这里记一句，免得后人再查一遍 |
| `grok-dev` | **1.1.7** | 2026-05-15 | **本 harness 用这个**。仓库 superagent-ai/grok-cli，README 的安装命令是 `bun add -g grok-dev` |

钉版本用的凭据（`npm view grok-dev@1.1.7`，2026-09-06 在 f02 容器内实取）：

```
dist.shasum    e67dc2739cd613ffdfc88b693ee8a36617b81171
dist.integrity sha512-x0VvjIrtJYjnxdTE4mqz2x9NUtNRra2BzlD7McNznM3Jxm1fI85RUC4MoOZX487hIbYmG/RCLifksEcSwrZ9oQ==
bin            { grok: 'dist/index.js' }
engines        { node: '>=18.0.0' }      ← **这一行是错的，见 §2**
```

> npm 的网页 `www.npmjs.com` 抓取会 403；元数据一律从 `https://registry.npmjs.org/<pkg>` 取。

---

## 2. 必须装 Bun —— 而 `engines` 说 node 就够

这是本 harness 最容易踩的一条，因为**包自己的元数据在骗人**。三层证据，一层比一层硬：

1. `dist/index.js` 的 shebang 是 `#!/usr/bin/env bun`。
2. `dist/` 是 `tsc` 的输出，ESM import **不带扩展名**（`from "./agent/agent"`）——
   Node 的 ESM 解析器解不了。
3. `dist/storage/db.js` 第一行是 `import { Database } from "bun:sqlite"`。
   **这是 Bun 独有的内建模块**，Node 上没有等价物，写什么 loader 补丁都绕不过去。

f02 实机复现（`gb-base:bookworm-r1` 容器内，`npm i -g grok-dev@1.1.7` 之后）：

```
$ grok --help
/usr/bin/env: 'bun': No such file or directory

$ node $(npm root -g)/grok-dev/dist/index.js --help
Error [ERR_MODULE_NOT_FOUND]: Cannot find module '.../dist/agent/agent'
    imported from .../dist/index.js
```

修法就是 Dockerfile 里那一行：`npm install -g "bun@1.4.2" "grok-dev@1.1.7"`。
`npm i -g bun` 装的是 2 个包（bun 壳 + 平台二进制），**全程 registry.npmjs.org，
不碰 GitHub releases** —— 这一点很要紧，f02 上 docker.io 被墙、GitHub 未必可达，
而 npm 实测 200。

> 包里还随发了 `dist/grok-standalone`（= `dist/grok-bin`，70,464,544 字节，
> `bun build --compile` 的单文件二进制），走那条路可以不装 bun。**本 harness 没用它**：
> 那样「跑的到底是哪一版 grok」只能靠二进制自报，而走 `bun + grok` 跑的就是 `dist/` 里
> 那些可读的 `.js` —— §4 里两个坑都是直接读源码读出来的，不是撞出来的。

---

## 3. 怎么把模型指到我们的端点

三个环境变量，都是从包里读出来的（`dist/utils/settings.js:178-186`）：

| 变量 | 作用 | 默认值 |
|---|---|---|
| `GROK_BASE_URL` | API base URL | `https://api.x.ai/v1` |
| `GROK_API_KEY` | 鉴权 | 无（也可 `~/.grok/user-settings.json`） |
| `GROK_MODEL` | 模型名 | 内置 `grok-4.3` |

`launch.json` 里就是三行 `export`：

```sh
export GROK_API_KEY="$OPENAI_API_KEY"
export GROK_BASE_URL="$OPENAI_BASE_URL"      # 原样，不削尾巴
export GROK_MODEL=deepseek-chat
```

**为什么可以原样给**：xAI 的默认 base URL 自带 `/v1`，和边车注入的
`$OPENAI_BASE_URL`（`http://gateway:8081/v1`）形状一致 ——
不像 claude-code 要 `${OPENAI_BASE_URL%/v1}/anthropic`、gemini 要 `${OPENAI_BASE_URL%/v1}`。
**主机名一个字都没写死**，仍然只从 `env_required` 列的变量取。

请求路径与鉴权头不是猜的，是从依赖包里读出来的
（`@ai-sdk/xai@3.0.130`，`dist/index.js:566` 与 `:665`、`:3584`）：

```js
const url = `${this.config.baseURL ?? "https://api.x.ai/v1"}/chat/completions`;
// 流式分支额外带 stream: true, stream_options: { include_usage: true }
Authorization: `Bearer ${loadApiKey({ apiKey, environmentVariableName: "XAI_API_KEY" })}`
```

也就是 **`POST $GROK_BASE_URL/chat/completions`，`Authorization: Bearer`** ——
标准 OpenAI 兼容形状，DeepSeek 直接服务。边车的 `_replace_auth` 认得这个头，
容器里的占位 key 会被换成真 key。**边车一行都不用改**，`MODEL_API_ALLOW`
也不用加域名（上游就是已在白名单里的 `api.deepseek.com`）。

> 一条可复现性的边角：`grok-dev` 对 `@ai-sdk/xai` 的依赖写的是 `^3.0.67`（浮动范围），
> `npm i -g` 会解析成当时最新的 3.x（本卡构建时是 3.0.130）。所以**镜像 digest 钉住的是
> 「构建那一刻的依赖树」**，不是「grok-dev@1.1.7 这个名字」。这和 codex/gemini 两个
> harness 同性质（都没有随包发布 lockfile），不是本 harness 特有的问题 ——
> 复核镜像来历要比 digest，不要指望重装能得到同一棵树。

### 无头（非交互）怎么跑

```sh
grok -p "<题面>" -m <model> --no-sandbox --format text
```

* `-p, --prompt` 就是无头开关（`dist/index.js:290`），走 `runHeadless()`，不起 TUI。
* `--format text|json`，默认 `text`。
* **不需要任何「自动批准工具」的开关。** 全仓只有 `paid_request`（x402 钱包付费）
  走 `tool-approval-request`，其余工具在 headless 路径上直接执行。
* **workspace-trust 也不会问。** `resolveWorkspaceTrustSandboxMode` 只在**交互式**分支
  被调用（`dist/index.js:330`），`-p` 在它之前就 `return` 了 ——
  所以**不用**预写 `.grok/workspace-trust.json`。（D-21 当初的预判是要预写；读源码之后
  这条撤销。若将来要跑交互式，那份文件才有用。）
* `--no-sandbox` 是防御性的：sandbox 默认已是 `off`（`settings.js:427`），
  但 `/task` 下若有 `.grok/settings.json` 会被当项目设置读进来；容器里也没有 Shuru sandbox。
* **不要用 `-k/--api-key`**：`resolveConfig` 会把它 `saveUserSettings` 落盘到
  `~/.grok/user-settings.json`（`dist/index.js:262`）—— 那等于把 key 写进文件。
  用 `GROK_API_KEY` 环境变量，`getApiKey()` 只读不写。

---

## 4. 两个会安静吃掉预算的坑（读源码读出来的）

### ① `GROK_MAX_TOKENS` 不设 → 第一个请求就被上游拒

`Agent` 构造函数（`dist/agent/agent.js:402`）：

```js
const envMax = Number(process.env.GROK_MAX_TOKENS);
this.maxTokens = Number.isFinite(envMax) && envMax > 0 ? envMax : 16_384;
```

默认 **16384**，而 `deepseek-chat` 的输出上限是 8192。不设的话第一个请求就按
`max_tokens` 超限被上游拒掉。`launch.json` 里设 `GROK_MAX_TOKENS=8000`。
（和 claude-code 的 `CLAUDE_CODE_MAX_OUTPUT_TOKENS` 是同一个坑，值得当成
「接 OpenAI 兼容 harness 的固定检查项」。）

### ② `recapsEnabled` 默认开 → 每轮白白多打一次注定失败的请求

`loadRecapsEnabled()`（`settings.js:446`）是 `!== false`，也就是**默认开**。
开着的话每轮结束会调 `refreshSessionRecap`（`agent.js:644`），
而它用的模型是**写死的** `grok-4.20-non-reasoning`（`grok/client.js` 的
`DEFAULT_RECAP_MODEL`）。在 DeepSeek 上这个模型名不存在，请求必然失败 ——
失败被 `catch` 吞掉，**不报错、不影响结果**，但**照样占掉一次预算闸计数**。

修法是启动前预写 `$HOME/.grok/user-settings.json`：

```json
{"recapsEnabled": false, "sandboxMode": "off"}
```

> 同一族的 `generateTitle`（也写死 `grok-4.20-non-reasoning`）只在 TUI 里调
> （`dist/ui/app.js:1657`），headless 不会碰；`checkForUpdate` 同理
> （`ui/app.js:1464`）—— 所以运行期只有边车这一个出口。

### ③ 顺带一条：模型名不认识不是错误

`deepseek-chat` 不在内置 `MODELS` 表里 → `normalizeModelId` **原样返回**
（`grok/models.js:80`），`getModelInfo` 返回 `undefined`。
后果只有一个：自动压缩被跳过（`agent.js:1231` / `1495` 都是 `if (modelInfo)`）。
单题单轮用不到压缩，所以不是错误 —— 但**长任务上就没有自动 compaction 兜底**，
届时靠的是 overflow recovery。

### ④ HOME 必须可写，而且只认 `HOME`

`grok` 的**全部**状态都在 `os.homedir()/.grok` 下：`user-settings.json`、
`grok.db`（bun:sqlite，headless 也会开，因为 `persistSession` 默认 true）、
`workspace-trust.json`。容器以 uid 1000 跑、HOME 不可写 →
按铁律把 `HOME` 指到 `/task/.grok_home` 并 `mkdir -p`。
**它没有 `GROK_HOME` 这类变量**，别去设一个不存在的（`utils/settings.js:60`
直接用 `os.homedir()`）。

### ⑤ bun 的运行时转译缓存会往 `/task` 写 297 个文件

`HOME` 指到 `/task/.grok_home` 之后，bun 会把**运行时转译缓存**写在
`$HOME/.bun/install/cache/@t@/*.pile`。真跑实测：`run.json` 的 `unexpected` 里
躺着 297 条「注入后被加：…… 它不在任何清单里，容器却会看到它」—— P8 的封闭性检查
被这堆缓存淹掉，真有问题的文件反而看不见了。

修法是 `launch.json` 里那一行：

```sh
export BUN_RUNTIME_TRANSPILER_CACHE_PATH=0
```

容器内实测（假上游、零真调用，脚本 `scratch/3.2-grok-cli/smoke/smoke_tree2.sh`）：

| 设置 | `/task` 下文件数 | 工具还跑不跑得动 |
|---|---|---|
| 什么都不设 | **301**（297 个 `.pile`） | 跑得动 |
| `BUN_INSTALL_CACHE_DIR=/tmp/...` | 301（**没用**） | 跑得动 |
| `BUN_INSTALL=/tmp/.bun` | 301（**没用**） | 跑得动 |
| `BUN_RUNTIME_TRANSPILER_CACHE_PATH=0` | **4** | 跑得动 |

> 前两个变量管的是**包安装**缓存，转译缓存是另一套 —— 名字很像，别猜，实测。
> **这条是真跑之后加的**：证据里那两个 run 用的是没有这一行的命令，所以它们的
> `unexpected` 里有 297 条噪声。它只改缓存落点，不碰模型调用路径。

---

## 5. 真跑证据（batch `h_grok-cli`，2026-09-07）

报告在 `ops/reports/h_grok-cli/`（含 `NOTE.md`：这两个 0 该怎么读），
run 原件在 f02 `/data/genebench_runner/h_grok-cli/runs/runs/<run_id>/`。
一道真题 `s2-cor-01`，双臂各 1 次，经边车、上游 `api.deepseek.com`。

| 臂 | run_id | 退出码 | 时长 | llm_log | decision / status | 产物 | sr_bucket | validity |
|---|---|---|---|---|---|---|---|---|
| strict | `s2-cor-01.strict.cfg-grok-cli-deepseek.r01` | 0 | 128.4 s | 101 | 100×`allow`/200 + 1×`deny`/429 | 无 | `budget_exhausted` | 无 |
| open | `s2-cor-01.open.cfg-grok-cli-deepseek.r01` | 0 | 24.5 s | 4 | 4×`allow`/200 | 无 | `no_artifact` | 无 |

**两臂都没有可评分产物，而原因不在链路。** 104 条 llm_log 里，除最后那条预算闸的 429 外
全部 `decision=allow / status=200 / upstream=api.deepseek.com`：key 注入、预算闸、
日志、出向白名单都按设计工作。那条 429 长这样，正是它该有的样子：

```json
{"error": "denied", "reason": "budget_exceeded", "detail": "calls=100 已达上限 100"}
```

### 卡在哪一层：工具调用的参数被**客户端**丢掉了

会话库 `work/.grok_home/.grok/grok.db`（bun:sqlite）里，strict 臂 103 次
`tool_calls` **无一例外** `args_json = {}`，`tool_results` 全是同一句：

```
Invalid input for tool bash: Type validation failed: Value: {}.
  path: ["command"], expected string, received undefined
```

而**同一时刻网线上是有参数的** —— `llm_log` 里那条 SSE 逐字可读（strict 第 4 条，
完整、带 `[DONE]`）：

```
{"tool_calls":[{"index":0,"id":"call_00_...","type":"function",
                "function":{"name":"bash","arguments":""}}]}
{"tool_calls":[{"index":0,"function":{"arguments":"{"}}]}
{"tool_calls":[{"index":0,"function":{"arguments":"\""}}]}
{"tool_calls":[{"index":0,"function":{"arguments":"command"}}]}   ← 续片只带 index
...
```

根因在 `@ai-sdk/xai@3.0.130` 的 `dist/index.mjs`。它的流式 chunk schema 把
`tool_calls` 的每一片都当成**一次完整的工具调用**：

```js
tool_calls: z4.array(z4.object({
  id: z4.string(),                    // 必填
  type: z4.literal("function"),       // 必填
  function: z4.object({ name: z4.string(), arguments: z4.string() })  // 均必填
})).nullish()
```

紧接着的 transform 对每一片直接 `tool-input-start` → `tool-input-delta` →
`tool-input-end` → `tool-call` 一气呵成，**没有按 index 累积的分支**。
xAI 自家 API 确实一片发全，所以这份 provider 在 xAI 上是对的；
而 DeepSeek / OpenAI 的标准形状是「首片带 id/type/name、续片只带 index + 参数片段」——
续片一律通不过 zod → 被整片丢弃 → 累积到的参数只有首片那个空串 → `{}`。

### 假上游对照实验（零真调用，三组）

`scratch/3.2-grok-cli/smoke/{fake_upstream.py,smoke.sh}`：容器内起一个只说 SSE 的
假上游，`GROK_BASE_URL` 指到 `127.0.0.1`，换三种形状各跑一次 `grok -p`，
跑完读 `grok.db` 看工具参数。

| MODE | 上游发的形状 | `grok.db` 里的 `args_json` | 工具 |
|---|---|---|---|
| `frag` | 首片带 id/type/name，续片只带 index + 参数片段（**DeepSeek / OpenAI 的形状**） | `{}` | 失败 |
| `whole` | 参数一整块，但仍只带 index | `{}` | 失败 |
| `xai` | 一片就是完整一次调用（id/type/name/arguments 齐全，**xAI 的形状**） | `{"command":"echo HELLO_FROM_TOOL"}` | **成功，输出 HELLO_FROM_TOOL** |

`xai` 那一组同时证明了另一件事：**除了这一层，本 harness 的接线全是对的** ——
HOME、无头 `-p`、工具注册（40 个）、`--no-sandbox`、会话库、退出码，都正常。

### 顺带记一笔：模型是怎么被这条 bug 拖垮的

strict 臂那 100 次调用不是模型在乱打。它每次都发出**参数完整**的 `bash` 调用，
每次都被回一句「command 是 undefined」，于是道歉、重试、再道歉；到第 100 次时，
它自己的输出已经退化成真的空参数（`arguments: "{}"`，见 llm_log 第 99 条）——
**先有客户端丢参数，后有模型退化**，顺序别读反了。stdout 尾巴里那句
「I've made dozens of empty tool calls」是结果，不是原因。

### 能不能修

不能，也不该在本卡修：

* **换 `@ai-sdk/xai` 的版本没用。** `3.0.67 / 3.0.90 / 3.0.110 / 3.0.130` 四个版本的
  chunk schema 逐字相同（`grok-dev` 声明的范围是 `^3.0.67`，整个范围都一样）。
* **`grok-dev` 没有换 provider 的开关。** `dist/grok/client.js:1` 就是
  `import { createXai } from "@ai-sdk/xai"`，`createProvider()` 里写死，
  没有任何 `openai-compatible` 的分支（尽管那个包作为传递依赖就躺在 node_modules 里，
  而且它**有**按 index 累积的实现）。
* **在容器里 patch 那份 zod schema 可以让表格好看**，但那时主表上跑的就不是 Grok CLI，
  而是「Grok CLI + 我们改过的 provider」—— 与 gemini-cli 那张卡拒绝写协议翻译层是同一个理由，
  也与统一基座（N-62）要消除运行时差异同源。

所以 `config.yaml` 是 `enabled: false`：**跑得起来、链路全通、但在 DeepSeek 上拿不到
可评分产物的配置不进主表。** 换一个真 xAI 端点（§6）它就该能跑。

---

## 6. 模型待换（对本 harness 是硬前置，不是化妆）

注册表里登记的模型是 `deepseek-chat`，**不是 `grok-*`**。
和另外几个 harness 不同的是：对 Grok CLI，换模型不是「换个名字更好看」，
而是**能不能拿到产物**的前提 —— 见 §5 那条 provider 的 chunk schema。
现在跑的是「Grok CLI 这套 harness × DeepSeek 这个模型」——
这正是 v1.0 的实验设计（一个模型 × 多种 harness），主表上暴露的是 harness 差异。

要换回真 Grok，三件前置，缺一不可：

1. **`XAI_API_KEY`** 落到 f02 的 `~/.config/genebench/secrets.env`（0600）。
2. **`api.x.ai` 进 `runner/c41/egress_proxy.py::MODEL_API_ALLOW`**，
   并与本目录 `config.yaml` 的 `base_url` 同源（`ops/test_c41.py` 有键集**相等**断言）。
3. **过 M7 的实验设计审定**：`assert_registry_sane` 要求**所有已启用配置同一模型**，
   把这一条换成 `grok-4.3` 会让别的配置当场红。这不是可以随手放宽的断言。

改动点是三处：`config.yaml` 的 `model` / `base_url`、`launch.json` 的 `-m` 与
`GROK_MODEL`、`MODEL_API_ALLOW`。**`GROK_BASE_URL` 那一行不用动** ——
它取的是 `$OPENAI_BASE_URL`，指向边车，上游是谁由注册表决定。

---

## 7. 构建 / 出集 / 推送 / 真跑 / 结算

全部命令与坑见 [`harnesses/README.md`](../README.md) §3–§5。本 harness 的具体参数：

```sh
# f01：同步 exec 树（**必带 --with-launch-data**，否则 f02 上 by_id 找不到 config_id）
cd /data/shared/genebench/repo && ops/push_exec_to_f02.sh --with-launch-data

# f02：构建（build.sh 没有执行位，一律用 sh 调；tag 取 launch.json 的 image）
ssh ljn@192.168.1.219 'cd /data/genebench_runner/exec && sh harnesses/build.sh grok-cli --dry-run'
ssh ljn@192.168.1.219 'cd /data/genebench_runner/exec && sh harnesses/build.sh grok-cli'
#   → 打印的 digest 回填到本目录 Dockerfile 顶部注释，并作为下面的 --digest

# f01：出集
PY=/data/shared/genebench/env/bin/python
STG=/data/shared/genebench/staging/h_grok-cli_s2-cor-01
rm -rf "$STG"
$PY ops/export_bundle.py s2-cor-01 --staging "$STG" --digest "<digest>" --image gb-grok-cli-u

# f01：推送（唯一允许的入口）
ops/push_bundle_to_f02.sh "$STG/tasks/s2-cor-01" \
  /data/genebench_runner/h_grok-cli/runner/tasks "$STG/s2-cor-01.manifest.json"

# f01：真跑（**必须包在网关锁里**，N-125）
$PY ops/gateway_lock.py --what "3.2-grok-cli:真跑 s2-cor-01" -- \
  ssh -o ConnectTimeout=120 ljn@192.168.1.219 \
  "umask 022; export PYTHONDONTWRITEBYTECODE=1; cd /data/genebench_runner && \
   python3 exec/ops/run_f02_a1.py \
     --bundle   /data/genebench_runner/h_grok-cli/runner/tasks/s2-cor-01 \
     --manifest /data/genebench_runner/h_grok-cli/runner/tasks/s2-cor-01.manifest.json \
     --config-id cfg-grok-cli-deepseek --arms strict,open --seq 1 \
     --timeout 1500 --max-calls 100 --max-tokens 3000000 \
     --run-root    /data/genebench_runner/h_grok-cli/runs \
     --results-dir /data/genebench_runner/h_grok-cli/results"

# f01：结算 —— **注意 runs/runs 那一层**
$PY ops/score_runs.py --batch h_grok-cli --remote /data/genebench_runner/h_grok-cli/runs/runs
```

> `run_f02_a1.py --run-root <X>` 会在 `<X>/runs/` **下面再建一层**，
> 所以结算的 `--remote` 要写到 `runs/runs`。照 `harnesses/README.md` §4④ 抄会得到
> 「runs: 0；问题: 0」—— 不报错、退 0，看起来像「跑完了但没结果」。
> （gemini-cli 那张卡实测抓到的，已登记在 `ops/tickets_inbox/3.2-gemini-cli.md`。）
