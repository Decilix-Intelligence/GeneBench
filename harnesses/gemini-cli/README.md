# `gemini-cli` —— Google Gemini CLI（P1 通用 agent）

| | |
|---|---|
| harness 名 | `Gemini CLI`（`launch.json` 与 `config.yaml` 的 `harness` 字段，也是 `command_for()` 的查找键） |
| 镜像 | `gb-gemini-cli-u:r1`，digest `sha256:03d5bddf2502257c3b4690ae8cf3813da07d0002e0d529c1c762e96f008a7108` |
| 版本 | `@google/gemini-cli@0.58.0`（npm，构建期装在统一基座上） |
| 范式 | P1 |
| 配置 | `cfg-gemini-cli-deepseek`，**`enabled: false`** |
| 模型状态 | **待换** —— 见 §6。链路已真跑验证到边车，但没有够得着的上游会说 Gemini 协议 |

> **一句话结论**：Gemini CLI 能在 GeneBench 里起来、能读到题面、能把请求经边车发出去并落
> `llm_log` —— 这些都有真跑证据（§4）。**它拿不到模型输出**，因为它说的是 Gemini API 协议，
> 而我们够得着的上游（DeepSeek）只服务 OpenAI 兼容与 Anthropic 兼容两套。
> 差的不是适配代码，是**一个会说 Gemini 协议的、够得着的端点**（§6）。

---

## 1. 它到底支不支持自定义 base URL

支持 —— 但要把两件事分开，混起来会得出错误结论：

| 问题 | 答案 | 证据 |
|---|---|---|
| 有没有 **OpenAI 兼容** provider？ | **没有** | 0.58.0 整个包里 `OPENAI_BASE_URL` / `OPENAI_API_KEY` / `OPENAI_MODEL` **各 0 处命中** |
| 有没有 **自定义 base URL** 的正式配置？ | **有**：`GOOGLE_GEMINI_BASE_URL` | 包内 `bundle/docs/reference/configuration.md` 有正式条目 |

`bundle/docs/reference/configuration.md` 的原文要点：

* `GOOGLE_GEMINI_BASE_URL` —— 覆盖 Gemini API 请求的默认 base URL，
  **在 `gemini-api-key` 认证下生效**；
* 「必须是合法 URL。出于安全，除非指向 `localhost`（或 `127.0.0.1` / `[::1]`），
  否则必须用 HTTPS。」

⚠ **那条 HTTPS 限制在 0.58.0 里没有被强制。** 这是实测结论，不是推断：
容器内把 `GOOGLE_GEMINI_BASE_URL` 设成 `http://gateway:8081` 后，
CLI 没有报任何校验错，而是直接走到了网络层（`TypeError: fetch failed sending request`
——那是连不上主机，不是拒绝这个 URL）。所以**边车这条路是通的**，
我们不需要为它放宽任何判据，也不需要在容器里再架一层 TLS。

> 这一条值得写下来的原因：如果只读文档，会得出「base URL 必须 https，
> 而边车是 http，所以接不上」的结论，然后去做一件不必要的事
> （给边车加 TLS、或者把 harness 判为完全不可接）。**读文档得到的是限制，
> 实测得到的是行为**，这次两者不一致。

### 别指望的两条

* **`gemini gemma` / local model routing**：那是给**路由决策**用的本地 Gemma
  （LiteRT-LM，`classifier.host` 只接受 `http://localhost:<port>`），
  不是主模型端点，也需要下载模型权重。与我们无关。
* **自定义请求头**：0.58.0 没有 `customHeaders` 之类的设置项（查过 `configuration.md`）。
  所以「让它改发 `Authorization`」这条路不存在 —— 好消息是也不需要，见 §3。

---

## 2. 怎么把模型指过来

`launch.json` 的命令（`$$` 是 compose 的转义，见 `harnesses/README.md` 铁律一）：

```sh
export HOME=/task/.gemini_home
GB_SETTINGS_DIR="$$HOME/.gemini"
mkdir -p "$$GB_SETTINGS_DIR"
printf '%s' '{"general":{"enableAutoUpdate":false,"enableAutoUpdateNotification":false},
              "privacy":{"usageStatisticsEnabled":false},
              "security":{"auth":{"selectedType":"gemini-api-key"},
                          "folderTrust":{"enabled":false}}}' > "$$GB_SETTINGS_DIR/settings.json"
export NO_COLOR=1
export GEMINI_API_KEY="$$OPENAI_API_KEY"
export GOOGLE_GEMINI_BASE_URL="$${OPENAI_BASE_URL%/v1}"
cd /task && gemini -p "$$(cat /task/INSTRUCTION.md)" -m deepseek-chat \
  --approval-mode yolo --skip-trust -o text
```

逐条为什么：

* **`GOOGLE_GEMINI_BASE_URL="$${OPENAI_BASE_URL%/v1}"`** —— 边车注入的是
  `http://gateway:8081/v1`，而 Gemini CLI 自己会在 base URL 后面接
  `/v1beta/models/<model>:streamGenerateContent`。所以要把尾巴上的 `/v1` 削掉，
  否则路径变成 `/v1/v1beta/...`。**主机名一个字都没写死**，仍然只从
  `env_required` 列的变量取（铁律二）。写法与 `harnesses/claude-code` 那份同源
  （那边是 `$${OPENAI_BASE_URL%/v1}/anthropic`）。
* **`security.auth.selectedType=gemini-api-key`** —— 不预写这一条，CLI 在非交互下
  只打一行 `Invalid auth method selected.` 就退出，**零次模型调用**，
  看起来像「跑过了」。这是本 harness 最容易踩的一个坑。
* **`security.folderTrust.enabled=false` + `--skip-trust`** —— 不加的话
  `/task` 不是受信任目录，CLI 打
  `Approval mode overridden to "default" because the current folder is not trusted`，
  把 `yolo` 降回逐次确认，于是在非交互下卡死或什么都不做。
* **`general.enableAutoUpdate=false`** —— 省掉起步时那次到 npm 的出网。
  运行期容器挂在 `internal: true` 的 `gb_task` 上，唯一出口是边车；
  留着它只会换来一次无谓的超时等待。
* **`-m deepseek-chat`** —— 让 `config.yaml` 的 `model`、`launch.json` 的 `-m`、
  以及请求 path 里的模型名三处一致。模型名会**进 URL**
  （`/v1beta/models/deepseek-chat:streamGenerateContent`），这一点和 OpenAI 兼容那套
  （模型名在 body 里）不同，排障时看 `llm_log` 的 `path` 就能确认模型名传对没有。
* **`HOME=/task/.gemini_home`** —— 容器以 uid 1000 跑、`HOME` 不可写；
  `/task` 就是 run dir 的 `work/`，是唯一可写处。

---

## 3. 鉴权：为什么边车一行都不用改

Gemini CLI 发的鉴权头是 **`x-goog-api-key`**，不是 `Authorization`。
一开始看这像是要改边车（`runner/c41/egress_proxy.py` 的 `_replace_auth` 只认
`authorization`）。**读完代码发现不用改**，而且现有实现恰好把这条路走通了：

1. `_client_key(head)` 只读 `authorization` 头 → 读不到 → 返回 `None`；
2. `if key and key != PLACEHOLDER_KEY:` → `key` 是 `None`，**整个条件不成立**
   → **不会**判 `403 foreign_credential`；
3. `_replace_auth()` 遍历完发现 `seen_auth` 仍是 `False`
   → 执行 `out.insert(1, f"authorization: Bearer {real_key}")`，**插入**一条真 key 的
   `Authorization`。

于是上游收到的是一条带**正确 Bearer 真 key** 的请求。
`GEMINI_API_KEY` 里那把占位 key（`sk-genebench-placeholder`）会被原样放进
`x-goog-api-key` 转发上去 —— 占位 key 是**公开的**（写在 `egress_proxy.py` 里），
不构成凭据泄露。

> **所以本卡没有改任何共享文件。** 预算闸、`llm_log`、出向白名单三样对这个 harness
> 全部照常生效。真要给别的 harness 加 `x-api-key` 一类的头替换时，
> 请先照上面这三步核一遍：现有实现对「没有 `Authorization`」的情形是**接受并补上**，
> 不是拒绝。

---

## 4. 真跑证据

三件事分开验，因为它们会一起失败但原因完全不同：**镜像**、**命令**（含鉴权头）、
**端到端真跑**。

### 4.1 镜像

```
gb-gemini-cli-u:r1
digest sha256:03d5bddf2502257c3b4690ae8cf3813da07d0002e0d529c1c762e96f008a7108
```

在 f02 用**本目录的 `Dockerfile`** 经 `harnesses/build.sh gemini-cli` 构建
（基座 `gb-base:bookworm-r1`，`sha256:fd1e2fd0c7ae…`）。
`gemini --version` → `0.58.0`。

### 4.2 命令与鉴权头（假上游冒烟，**零次真 API 调用**）

在容器里起一个只会打印请求的假上游，把 `OPENAI_BASE_URL` 指过去，
跑的是**从 `launch.json` 取出、把 `$$` 按 compose 收成 `$` 之后**的那一条命令
（不是另写一条相似的）。假上游收到：

```
POST /v1beta/models/deepseek-chat:streamGenerateContent?alt=sse
H host: 127.0.0.1:8081
H user-agent: GeminiCLI-tui/0.58.0/deepseek-chat (linux; x64; terminal)
H x-goog-api-client: google-genai-sdk/1.30.0 gl-node/v22.23.2
H content-type: application/json
H x-goog-api-key: sk-genebench-placeholder
BODY 48418 bytes; head=b'{"contents":[{"parts":[{"text":"<session_context>...
```

四条结论，每条都是后面某个判断的前提：

1. **path 是 `/v1beta/models/<model>:streamGenerateContent`** —— 模型名在 **URL 里**，
   不在 body 里（和 OpenAI 兼容那套相反）。排障时看 `llm_log` 的 `path` 就知道模型名传对没有。
2. **`/v1` 削对了** —— path 是 `/v1beta/…` 而不是 `/v1/v1beta/…`。
3. **鉴权头是 `x-goog-api-key`，没有 `Authorization`** —— §3 那一整节的事实基础。
4. 假上游回一条正常的 Gemini 响应后，CLI 打出了 `SMOKE_OK` 并 `exit 0` ——
   **说明只要上游会说这个协议，这个 harness 就是通的**。
   （冒烟没有产出 `artifact.json`：假上游只回了一句话、没有驱动工具调用，
   那是冒烟的设计，不是 harness 的毛病。）

脚本留在 `/data/shared/genebench/scratch/3.2-gemini-cli/smoke/`
（`fake_upstream.py` / `cmd.sh` / `smoke.sh`）。

### 4.3 端到端真跑（batch `h_gemini-cli`，题 `s2-cor-01`，两臂各 1 次）

出集/推送/真跑/结算四条命令按 `harnesses/README.md` §4，真跑包在
`ops/gateway_lock.py` 里。**真跑时把 `config.yaml` 临时翻成 `enabled: true`**
（`by_id()` 只认主表里的 config_id），跑完翻回 `false` —— 仓库里现在是 `false`。
复现时要照做，这一步不能省。

| | strict | open |
|---|---|---|
| `run_id` | `s2-cor-01.strict.cfg-gemini-cli-deepseek.r01` | `s2-cor-01.open.cfg-gemini-cli-deepseek.r01` |
| 容器退出码 | 1 | 1 |
| `elapsed_s` | 15.839 | 15.229 |
| `llm_log` 条数（`decision=="allow"`） | **1** | **1** |
| `artifact.json` | 无 | 无 |
| 结算 | `no_artifact`，`validity=None`，`steps=1` | 同左 |

两臂的 `llm_log.jsonl` 各一行，逐字一致（除时间戳）：

```json
{"decision": "allow", "status": 404, "method": "POST",
 "path": "/v1beta/models/deepseek-chat:streamGenerateContent?alt=sse",
 "upstream": "api.deepseek.com", "reason": null, "usage": {}, "budget": {"calls": 1, "tokens": 0}}
```

**这一行就是本卡的全部结论**，它同时证明了三件事和证伪了一件：

* `decision: "allow"` —— 边车**接受**了这个请求。没有 `403 foreign_credential`，
  也就是 §3 那条推理（`x-goog-api-key` 不被当成自带凭据、边车会补 `Authorization`）
  **在真链路上成立**，不只是读代码读出来的。
* `upstream: "api.deepseek.com"` + path 原样 —— 边车按原样转发了 path，
  容器→边车→上游三段全通。
* `budget: {"calls": 1}` —— 预算闸正常计数。
* `status: 404` —— **DeepSeek 不服务 Gemini 协议**。这就是 `enabled: false` 的理由，
  而且它是被**测出来**的，不是猜的：同一个上游在 OpenAI 兼容路径上对
  `cfg-codex-deepseek` 一直是 200。

`work/` 里两臂都有 `.gemini_home`（说明 `HOME` 重定向在 uid 1000 下真的可写）、
`INSTRUCTION.md`、`S2.json`、`provider`；strict 臂多一个 `protocol/` —— 两臂差异符合预期。

**为什么没有重试**：失败原因是上游协议不匹配，是确定性的，不是我们链路的抖动 ——
重试会拿到一模一样的 404，只是多烧 2 次调用。按纪律「重试只在失败原因是我们的链路时才算数」。

产物与报告：

* 结算 `ops/reports/h_gemini-cli/`（`summary.md` / `table_a.*` / `table_b.*` /
  `records.json` / `scores/`）。表头带「接入/harness 验证，**不是实验数据**」——
  `SR=0.0` 说的是「这个上游不会说这个协议」，**不是**「Gemini CLI 能力差」。
  把它读成后者是本卡最容易被误读的地方。
* f02 run 根 `/data/genebench_runner/h_gemini-cli/runs/runs/`
  （注意是两层 `runs` —— `--run-root` 下面还会再建一层）。
* bundle 与通行证 `/data/shared/genebench/staging/h_gemini-cli_s2-cor-01/`。

### 4.4 上游可达性（实测，不是查资料）

从 f02 直连（构建期网络，非任务容器）：

| 主机 | 结果 |
|---|---|
| `generativelanguage.googleapis.com` | `curl` 退 **`000`** —— 连不上 |
| `api.deepseek.com` | **`401`** —— 可达（边缘在，只是没带 key） |

---

## 5. 已知限制

* **拿不到模型输出**（§6）—— 这是当前唯一挡住它进主表的事。
* `Ripgrep is not available. Falling back to GrepTool.` —— 基座没装 ripgrep，
  CLI 自动回退到内置 grep。功能不受影响，不必为它往镜像里加东西
  （镜像只装 harness 本身）。
* `Warning: 256-color support not detected.` —— 容器里没有 TTY，无害；
  `NO_COLOR=1` 已经把彩色输出关掉，免得 ANSI 转义混进 `-o text` 的输出。
* 启动期两行 `[STARTUP] Phase 'cleanup_ops' was started but never ended.`
  是 CLI 自己的计时器噪声，与我们无关。
* CLI 会在 `HOME`（`/task/.gemini_home`）下写会话与临时文件。它们在容器退出后
  由 `verify_run_dir_unchanged()` 按 `harvest.PRODUCED_*` 归进 `unexpected`，
  不影响 P8（P8 在注入结束时结账，管的是注入期的文件集）。

---

## 6. 模型待换

`config.yaml` 现在是 `enabled: false`。**不是因为缺 key，是因为缺一个够得着的端点。**

两条路都堵死了，各有各的理由：

| 上游 | 说 Gemini 协议？ | 够得着？ | 在 `MODEL_API_ALLOW` 里？ |
|---|---|---|---|
| `generativelanguage.googleapis.com` | 是 | **否** —— f02 实测 `curl` 退 `000` | 否 |
| `api.deepseek.com` | **否**（只有 OpenAI 兼容 + Anthropic 兼容） | 是（`401`，即边缘可达） | 是 |

要把开关翻过来，**三件事缺一不可**：

1. **一把 `GEMINI_API_KEY`**，落到 f02 的 `~/.config/genebench/secrets.env`（`0600`）；
2. **把 `generativelanguage.googleapis.com` 加进出向白名单** ——
   `config.yaml` 的 `base_url` 与 `runner/c41/egress_proxy.py::MODEL_API_ALLOW`
   两处必须同源（`ops/test_c41.py` 有一条**键集相等**的断言）。
   `MODEL_API_ALLOW` 是共享文件，按共享文件规则改；
3. **一条能到那个域名的出口** —— 这条是硬的：现在从 f02 根本连不上。
   先把 ①② 做完再实测一次，不要反过来。

翻开关时还要复核 `assert_registry_sane` 的「所有已启用配置同一模型」：
现在主表上是清一色 `deepseek-chat`（v1.0 的实验设计是**一个模型 × 多种 harness**），
把 `model` 改成 `gemini-2.5-pro` 之类会当场红 —— 那是设计如此，
换模型得先过 M7 的实验设计审定，不是把断言放宽。

**换过去要改的地方一共三处**：`config.yaml` 的 `base_url` / `model`、
`launch.json` 的 `-m`、`MODEL_API_ALLOW`。`launch.json` 里
`GOOGLE_GEMINI_BASE_URL` 那一行**不用动** —— 它取的是边车地址，
而边车转发到哪由 `base_url` 决定。

---

## 7. 复现

```sh
# f01
cd /data/shared/genebench/repo
ops/push_exec_to_f02.sh --with-launch-data
ssh -o ConnectTimeout=120 ljn@192.168.1.219 \
  'cd /data/genebench_runner/exec && sh harnesses/build.sh gemini-cli'
```

出集 → 推送 → 真跑 → 结算的四条命令见 `harnesses/README.md` §4。
本 harness 用过的那一组记在 §4。
