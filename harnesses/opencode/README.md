# harness `opencode`

[opencode](https://opencode.ai)（npm 包 `opencode-ai`，仓库 `sst/opencode`）的 GeneBench 接入。
范式 **P1**：一个容器 + `/task/INSTRUCTION.md` 进、`/task/artifact.json` 出。
接入的通用规则、四件文件的 schema、出集/推送/真跑/结算四条命令都在
[`harnesses/README.md`](../README.md)，本文只写 **opencode 这一个 harness 特有的东西**。

| | |
|---|---|
| id / 目录 | `opencode` |
| `harness` 名 | `opencode` |
| `config_id` | `cfg-opencode-deepseek`（`enabled: true`） |
| 镜像 | `gb-opencode-u:r1` |
| 包 | `opencode-ai@1.18.26`（npm，2026-09-01 发布） |
| 协议 | **OpenAI 兼容**：`POST <baseURL>/chat/completions` |
| 模型 | `deepseek-chat`，经边车 → `https://api.deepseek.com`。**不是「模型待换」** |

---

## 1. 怎么把模型指到 OpenAI 兼容端点

opencode 内置的 provider 目录来自 models.dev，里面没有我们的边车。要指到自己的端点，
用它的**自定义 provider**：写一个 `opencode.json`，`npm` 字段选 provider 实现，
`options.baseURL` 指到端点，`options.apiKey` 用 `{env:VAR}` 语法从环境变量取。

`launch.json` 的命令在容器里现写这份配置（逐字）：

```json
{
  "provider": {
    "gbgw": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "GeneBench gateway (OpenAI compatible)",
      "options": { "baseURL": "$OPENAI_BASE_URL", "apiKey": "{env:OPENAI_API_KEY}" },
      "models": { "deepseek-chat": { "name": "deepseek-chat",
                                     "limit": { "context": 128000, "output": 8000 } } }
    }
  },
  "permission": "allow",
  "autoupdate": false,
  "share": "disabled"
}
```

然后 `opencode run --auto --title genebench -m gbgw/deepseek-chat "$(cat /task/INSTRUCTION.md)"`。

逐条说清楚哪个 flag / 键干什么（每一条都是实测出来的，不是抄文档的）：

* **`npm: "@ai-sdk/openai-compatible"`** —— 这个 provider 实现打的是 `/chat/completions`。
  写成 `@ai-sdk/openai` 会走 `/responses`（OpenAI 的新协议），DeepSeek 不服务那条路。
  它**已经打进 opencode 的单文件二进制**：`docker run --network none` 全程跑通（§4.1），
  官方 troubleshooting 里那条「provider 包在运行期动态安装到 `~/.cache/opencode`」对本 harness 不成立，
  **不需要构建期预热**。这一条值得记住 —— 只读文档会得出「运行期要出网装包、得把 npm 放进白名单」的相反结论。
* **`options.baseURL`** 直接用容器里的 `$OPENAI_BASE_URL`（`http://gateway:8081/v1`）。
  provider 会在它后面接 `/chat/completions`，于是边车看到的是 `POST /v1/chat/completions` —— 正是它要的形状。
  **主机名一个字都没写死**（铁律二）。
* **`options.apiKey: "{env:OPENAI_API_KEY}"`** —— opencode 支持这个语法。结果是
  `Authorization: Bearer sk-genebench-placeholder`，正好是边车 `_client_key()` 认的那个头，
  于是 `_replace_auth()` 换成真 key。**边车一行都不用改。**
* **`limit.context` / `limit.output` 必须自己写。** 自定义 provider 的模型不走 models.dev，
  opencode 不知道上下文还剩多少。`context: 128000` 是 deepseek-chat 的真实窗口；
  `output: 8000` 会被**原样发成请求体里的 `max_tokens`**（假上游抓到 `"max_tokens":8000`），
  写满 8192 有被上游按超限拒掉的风险，与 `harnesses/claude-code/README.md` 同源取 8000。
* **`--title genebench` 不是装饰，它省掉一次模型调用。** 不给 `--title` 时 opencode 会
  **先额外打一次模型**生成会话标题 —— 假上游抓到那次请求的 system 提示逐字是
  `You are a title generator. You output ONLY a thread title.`。那一次白白吃掉一次预算闸计数
  （`RUN_BUDGET.max_calls = 100`）。给了 `--title` 之后第一条请求就是正题。
* **`--auto` 与配置里的 `permission: "allow"` 两条都给。** 非交互下没有人按 y，
  缺了会挂在权限确认上直到 `--timeout` 砍掉。实测两条都在时 `bash` 工具直接执行、
  写出了 `/task/artifact.json`。
* **`HOME=/task/.opencode_home`**（并 `mkdir -p`）。容器以 uid 1000 跑、HOME 不可写。
  opencode 的四棵 XDG 目录全部从 HOME 派生，实测落在：
  `~/.config/opencode`（配置）、`~/.local/state/opencode`（锁）、
  `~/.local/share/opencode`（日志、session、repos）、`~/.cache/opencode`（bin）。
  只设 `XDG_*` 不设 `HOME` 是不够的。
* **`OPENCODE_DISABLE_AUTOUPDATE=1` + `autoupdate: false`** 省掉起步时那次到 npm 的出网；
  **`OPENCODE_DISABLE_LSP_DOWNLOAD=1`** 挡掉 LSP 服务器的运行期下载（运行期唯一的出口是边车，
  下不动，只会白等）；**`share: "disabled"`** 挡掉会话分享（那是往 opencode.ai 发数据）。
* **`opencode run [message..]` 吃位置参数，不吃 stdin。** 题面用 `"$(cat /task/INSTRUCTION.md)"` 传。

> `$` 在 `launch.json` 里一律写 `$$`（N-101）—— 上面这些是收成 `$` 之后的样子。

---

## 2. 版本与来历

| | |
|---|---|
| 包 | `opencode-ai@1.18.26` |
| `dist.shasum` | `ffdac376880c2a6b8a58fcbbc1445dbb1f79aa09` |
| `dist.integrity` | `sha512-XFPIj/yJZN8eBi4+uTjsnYAd/QezCM+/OUa3JbtL7tKQF4fGHR4onZx2d6oUGqbVs4CNONQ8QFKejeW+qVJIEA==` |
| 发布 | 2026-09-01（`latest` 是 2026-09-04 的 1.18.29，特意退一格取放了几天的那一版） |
| 容器里自报 | `opencode --version` → `1.18.26` |

**这个包是启动器 + 平台二进制，不是 JS 应用。** `opencode-ai` 本身只有 7.8 KB
（`LICENSE` / `package.json` / `postinstall.mjs` / 479 字节的 `bin/opencode.exe` 占位符），
`dependencies` 为空；真正的可执行体在 12 个 `optionalDependencies` 里，linux/x64 是
`opencode-linux-x64@1.18.26`，一个 **Bun 编译的单文件二进制**，解包 184,625,280 字节（~176 MB）。
`postinstall.mjs` 挑平台、把二进制硬链接成 `bin/opencode.exe`、再 `--version` 自验。
两个后果：

* 镜像会比别的 harness 大一截（f02 实测 `gb-opencode-u:r1` 约 1.1 GB DISK USAGE / 300 MB CONTENT）。这是预期的。
* `postinstall.mjs` 里 grep 不到任何 `fetch` / `http(s)://` / 下载 URL，唯一的网络动作是 npm 自身 ——
  **构建不需要 GitHub**（f02 上 GitHub 可达性对本 harness 不构成风险），也不需要往镜像里塞 Bun
  （二进制自带运行时，`node` 只在 postinstall 用一下）。

---

## 3. 已知限制

1. **每一轮工具调用都重发整个上下文**（OpenAI 兼容的多轮就是这个形状）。假上游实测三次请求
   30,825 → 31,152 → 31,479 字节，几乎全是 prompt。真题上实测每次约 30k token：
   **是 token 先撞闸，不是 calls** —— 34 次调用吃掉 104.8 万 token（§4.2），而 calls 上限是 100。
   与 `harnesses/codex/README.md` §2 同一类问题、不同数量级。
   真跑一律显式给 `--max-tokens 3000000`，别用 `RUN_BUDGET` 的 600k 默认值。
2. **opencode 会往配置文件里插一行 `"$schema"`。** 启动时它把
   `"$schema": "https://opencode.ai/config.json"` 写回 `opencode.json`（实测：写进去的是紧凑 JSON，
   跑完读出来第一行多了这条）。只是编辑器提示用的字段，不影响行为，**也不会去下载那个 URL**
   （`--network none` 下一切正常）。看到配置文件被改过不要以为是污染。
3. **默认工具面里有 `webfetch`。** 出向白名单只放模型 API 域名，所以 agent 调 `webfetch`
   会被正向代理拒掉并留痕 —— 这是设计如此（红线 5），不是 harness 坏了。
4. **`opencode models` 会列出上百个内置 provider 的模型**（models.dev 的目录打进了二进制）。
   那些都指向公网端点、在容器里一个都用不了；能用的只有我们的 `gbgw/deepseek-chat`。
   `-m` 必须显式给，形式是 `provider/model`。
5. **不要用 `opencode upgrade`**：版本是被 `--digest` 钉住的镜像的一部分，升级等于让通行证对不上。

---

## 4. 真跑证据

### 4.1 假上游冒烟（零真调用，`--network none`）

在 f02 上用 `launch.json` 里**逐字**的命令（`$$` 按 compose 收成 `$`）打一个只说 OpenAI 兼容协议的
假上游，容器 `--network none --user 1000:1000`（只剩 loopback，等价于「除边车外无出口」）：

```
uid=1000 gid=1000 groups=1000
REQ #1 POST /v1/chat/completions bytes=30825 tools=['bash','edit','glob','grep','read','skill','task','todowrite','webfetch','write'] msgs=2 last_role=user
REQ #2 POST /v1/chat/completions bytes=31152 ... msgs=4 last_role=tool
REQ #3 POST /v1/chat/completions bytes=31479 ... msgs=6 last_role=tool
H authorization: <31 chars: Bearer sk-genebench-plac...>
--- opencode exit=0 ---
/task/artifact.json  -rw-r--r-- 1 1000 1000 14  {"smoke":"ok"}
```

这一次冒烟同时证明了五件事：① 运行期**不需要出网**（provider 包不动态安装）；
② 请求形状是 `POST /v1/chat/completions` + `Authorization: Bearer <占位>`，边车不用改；
③ `--auto` + `permission: "allow"` 在非交互下真的不问；④ 工具调用能落盘到 `/task/artifact.json`；
⑤ `--title` 之后第一条请求就是正题（没有那次标题调用）。
脚本留在 `/data/shared/genebench/scratch/3.2-opencode/smoke/`。

### 4.2 一道真题双臂（batch `h_opencode`）

见 `ops/reports/h_opencode/`。真跑证据与逐 run 的 validity / steps / `llm_log` 条数见下表。

**batch `h_opencode` / 题 `s2-cor-01` / `cfg-opencode-deepseek` / 双臂各 1 次**（2026-09-07，f02）。
两臂都 `exit_code=0`、都产出了可评分且 **valid** 的 artifact，16 个探针全 `clean`、`gate_failed=[]`：

| | strict | open |
|---|---|---|
| `run_status` / `sr_bucket` / `validity` | ok / scorable / **valid** | ok / scorable / **valid** |
| `steps` | 34 | 52 |
| `llm_log` 条数（全部 `decision=allow`） | **34** | **52** |
| `status` / `upstream` / `path` | 34×200 / 全 `api.deepseek.com` / 全 `/v1/chat/completions` | 52×200 / 同左 / 同左 |
| prompt / completion tokens | 1,031,923 / 15,882 | 1,615,989 / 27,477 |
| L3 | `align` pass=False score=0.816 | `align` pass=False score=0.524 |
| Align / Adj / Cal / CellAgree | 1.0 / 1.0 / 1.0 / 0.264 | 0.0 / 1.0 / 1.0 / 0.097 |
| effect（两档锚） | 100.0 | 69.9 |
| 越权（`gateway_access_log` 403） | 3 / 337 | 3 / 1103 |
| latency | 405.6 s | 643.5 s |

怎么读这张表：**这是接入验证，不是实验数据**（`ops/reports/h_opencode/` 的表头也这么写）。
它要证明的只有一件事 —— **这条 harness 链路是通的**：题面进得去、模型调用经边车出得去、
工具能落盘、产物能被 scorer 收走并判成 valid。`l3_pass=False` 是这道题本身的难度，
不是链路问题；别把这里的数和 m6 的主表放在同一列。

三条从真跑里读出来的事实：

1. **86 次调用全部 `decision=allow` / `status=200` / `upstream=api.deepseek.com` /
   `path=/v1/chat/completions`** —— 边车原样接受并转发，一次 `foreign_credential`、
   一次 `budget_exceeded` 都没有。`{env:OPENAI_API_KEY}` → `Authorization: Bearer <占位>` 这条路成立。
2. **是 token 先撞闸，不是 calls。** 两臂 `llm_log` 的 `usage.total_tokens` 合计
   strict 1,047,805 / open 1,643,466，而 calls 只有 34 / 52。用 `RUN_BUDGET` 的默认
   `max_tokens: 600_000` 会在第 20 次调用左右撞闸（`llm_log` 尾部全是 `budget_exceeded`），
   **看起来像 agent 半途放弃**。所以 §5 那条命令里显式写了 `--max-tokens 3000000`。
   与 `harnesses/codex/README.md` §2 是同一类问题、不同数量级：Codex 每次 43k~68k，
   opencode 每次约 30k（prompt 占 98%，多轮工具调用每一轮都重发整个上下文）。
3. **`work/.opencode_home/**` 会进 `unexpected_files`。** run dir 结账时按
   `harvest.PRODUCED_*` 允许集分类，agent 运行期写的 HOME（config / opencode.db / log）
   落在允许集外。这不是错，和 `claude-code` 的 `.claude_home`、`codex` 的 `.codex` 同理 ——
   看到这份清单不必去查「谁往 work/ 里塞了文件」。

原始证据：
`/data/shared/genebench/runs_in/h_opencode/s2-cor-01.{strict,open}.cfg-opencode-deepseek.r01/log/llm_log.jsonl`
（f02 原件在 `/data/genebench_runner/h_opencode/runs/runs/<run_id>/`），
结算表 `ops/reports/h_opencode/{summary.md,table_a.csv,table_b.csv,records.json}`。

---

## 5. 出集 → 推送 → 真跑 → 结算（照抄）

```sh
cd /data/shared/genebench/repo
PY=/data/shared/genebench/env/bin/python
DIG=<harnesses/build.sh opencode 打印的 sha256:...>
STG=/data/shared/genebench/staging/h_opencode_s2-cor-01

# ① 出集
rm -rf "$STG"
$PY ops/export_bundle.py s2-cor-01 --staging "$STG" --digest "$DIG" --image gb-opencode-u

# ② 推送（唯一允许的入口）
ops/push_bundle_to_f02.sh "$STG/tasks/s2-cor-01" \
  /data/genebench_runner/h_opencode/runner/tasks "$STG/s2-cor-01.manifest.json"

# ③ 真跑（必须包在网关锁里，N-125；--max-tokens 显式给大，见 §3.1）
$PY ops/gateway_lock.py --what "3.2-opencode:真跑 s2-cor-01 / cfg-opencode-deepseek" -- \
  ssh -o ConnectTimeout=120 ljn@192.168.1.219 \
  "umask 022; export PYTHONDONTWRITEBYTECODE=1; cd /data/genebench_runner && \
   python3 exec/ops/run_f02_a1.py \
     --bundle   /data/genebench_runner/h_opencode/runner/tasks/s2-cor-01 \
     --manifest /data/genebench_runner/h_opencode/runner/tasks/s2-cor-01.manifest.json \
     --config-id cfg-opencode-deepseek --arms strict,open --seq 1 \
     --timeout 1500 --max-calls 100 --max-tokens 3000000 \
     --run-root    /data/genebench_runner/h_opencode/runs \
     --results-dir /data/genebench_runner/h_opencode/results"

# ④ 结算 —— 注意是 runs/runs（run_f02_a1 会在 --run-root 下再建一层）
$PY ops/score_runs.py --batch h_opencode --remote /data/genebench_runner/h_opencode/runs/runs
```

构建（在 f02 的 exec 树里，`sh` 调，没有执行位）：

```sh
cd /data/shared/genebench/repo && ops/push_exec_to_f02.sh --with-launch-data
ssh -o ConnectTimeout=120 ljn@192.168.1.219 \
  'cd /data/genebench_runner/exec && sh harnesses/build.sh opencode --dry-run'
ssh -o ConnectTimeout=120 ljn@192.168.1.219 \
  'cd /data/genebench_runner/exec && sh harnesses/build.sh opencode'
```

---

## 6. 「模型待换」状态

**不待换。** 本 harness 说的就是 OpenAI 兼容协议，DeepSeek 正是一个 OpenAI 兼容端点，
链路上没有协议缺口 —— 这一点与 `gemini-cli`（上游不说 Gemini 协议、真跑到 404、
`enabled: false`）正相反。`config.yaml` 是 `enabled: true`，
`base_url` 的 host `api.deepseek.com` 已在 `MODEL_API_ALLOW` 里，**本卡没有改那个共享文件**。

真要换成别的模型（比如 opencode 自带目录里的某个 provider），要同时改四处并过 M7 的实验设计审定：
`config.yaml` 的 `model`/`base_url`、`launch.json` 里 `-m` 与 `models` 块的模型名、
`egress_proxy.py::MODEL_API_ALLOW`（共享文件规则）、以及 `assert_registry_sane`
要求的「所有已启用配置同一模型」—— 混模型会当场红，那是设计如此。
---

## §9 换到 Qwen（用户裁定 ⑲，2026-09-10）—— **前置未齐，今天仍指 DeepSeek**

裁定是「opencode 启动脚本改用 Qwen（dashscope 的 OpenAI 兼容端点）验链路一道真题」。
**没有切**，因为三件前置里缺一件。下面是**实测到的前置状态**与**切换的完整判据**，
不是计划：谁补上那件缺的，照着做就行。

### 9.1 三件前置，2026-09-11 实测

| # | 前置 | 怎么查 | 实测 |
|---|---|---|---|
| (a) | f02 上有 `DASHSCOPE_API_KEY` | `grep -qE '^ *(export +)?DASHSCOPE_API_KEY=' ~/.config/genebench/secrets.env; echo $?` | **没有**。那个文件 0600 / 53 字节，里面**只有 `DEEPSEEK_API_KEY` 一个变量名** |
| (b) | `dashscope.aliyuncs.com` 在出向白名单 | `runner/c41/egress_proxy.py::MODEL_API_ALLOW` | **不在**（表里只有 `api.deepseek.com`）—— 而且**现在就不该在**，见 §9.3 |
| (c) | f02 连得到该域名 | 从 f02 `curl -o /dev/null -w '%{http_code}' https://dashscope.aliyuncs.com/compatible-mode/v1/models` | **通**：`401` / 0.17 s（401 = 到了上游、没带凭据）。DNS 解到 IPv6 |

**(a) 缺** → 按施工契约记 BLOCKED，不伪造 key、不往白名单里加一个没人用的域名。
key 到位的判据就是上表 (a) 那条命令退出码为 0 —— **不要 `cat` / `echo` 那个文件**（红线 3）。

### 9.2 key 到了之后要改什么

* **key 变量名**：`DASHSCOPE_API_KEY`。落点是 f02 的 `~/.config/genebench/secrets.env`（**0600**），
  一行 `DASHSCOPE_API_KEY=…`。边车从那里读，注入到上游请求；
  **容器里只有占位 key**（`sk-genebench-placeholder`），agent 看不到真 key。
  名字必须以 `_API_KEY` 结尾 —— `runner/registry.py::_one_config_sane` 判这一条。
* **端点**：`https://dashscope.aliyuncs.com/compatible-mode/v1`（OpenAI 兼容：
  `POST <baseURL>/chat/completions`）。`base_url` 必须 https，同样是 `_one_config_sane` 判的。
* **白名单域名**：`dashscope.aliyuncs.com` 进 `runner/c41/egress_proxy.py::MODEL_API_ALLOW`
  的键。那是**共享文件**，按共享文件规则改（flock 内读-改-提交，只追加不重排）。
* **模型名**：`qwen-plus` 之类，同时要改 `launch.json` 里自定义 provider 的 `models` 键
  与 `-m gbgw/<模型名>`，以及 `limit.context` / `limit.output`（自定义 provider 不走
  models.dev，这两个数必须自己写；`limit.output` 会被原样发成请求体的 `max_tokens`）。

### 9.3 会撞上的那条硬判据：**所有已启用配置必须同一模型**

`runner/registry.py::assert_registry_sane` 要求 `CONFIGS`（= `enabled: true` 的那些）
**模型字段全相同**。今天 13 条全是 `deepseek-chat`。这不是一条可以放宽的卫生检查，
是 **v1.0 的实验设计**：*一个模型 × 多种 harness* —— 主表上暴露出来的差异才归因到 harness，
不是归因到模型。**把 opencode 这条直接改成 Qwen 会让 13 条变成「12 条 deepseek + 1 条 qwen」，
当场红**；而放宽那条断言要过 M7，**本卡不许放宽**。

保守做法（不碰断言）：

1. **新开一个目录** `harnesses/opencode-qwen/`，`config.yaml` 写 **`enabled: false`**。
   `load_data_configs` 会把它收进 `PENDING_CONFIGS` 而**不进** `CONFIGS` ——
   于是它既不参与「同一模型」判据，也**不进** `collect_egress_hosts()`，
   `ops/test_c41.py` 那条「键集相等」的断言因此**不会**要求白名单里有 dashscope
   （这正是 §9.1 (b) 说「现在就不该在」的原因：白名单里一个没人用的域名是纯粹的敞口）。
   `_one_config_sane` 对 `enabled: false` 的也照判三条，所以 base_url / key 名写错照样当场红。
2. 真跑时用**显式 config** 走那条 pending 的（`by_id` 对 pending 会明确报
   「登记了但 enabled: false」，不是「未知 config_id」—— 这是设计好的显式状态）。
   把它翻成 `true` 之前必须先复核「同一模型」那条判据怎么办，**那是 M7 的事**。
3. `harnesses/opencode/`（本目录，DeepSeek 那条）**保持不动**：它是现网 13 条之一，
   把它改掉等于从主表里拿走一条正在用的配置。

> **为什么不是「改本目录的 config.yaml」**：那个文件是**主表里的一条**。
> 换掉它的 `model` 要么让主表红（enabled 时），要么让主表少一条（翻成 false 时），
> 两种都不是「加一个待验的链路」该付的代价。

### 9.4 顺带：**Qwen Code 不做**（裁定 ⑲）

`@qwen-code/qwen-code` 这个 CLI **不接**。它曾经出现在 `runner/c42/upstream_pins.py`
的 codex 那条 `note` 里，措辞是「不通就换 @qwen-code/qwen-code 的 OpenAI 兼容模式」——
那是 2026-09-04 的**备选方案**，codex 那条链路后来实测通了，备选没有被启用，
现在这条备选也被裁定**不做**。本目录与 `harnesses/README.md` 里没有任何地方
把它当计划中的一项；`upstream_pins.py` 那句陈旧措辞已登记（见 `ops/tickets_inbox/B.md`，
那个文件不在本卡的路径里）。

**用 Qwen 的是本节说的 opencode + dashscope 兼容端点，不是 Qwen Code。**
