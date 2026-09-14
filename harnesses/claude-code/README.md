# `claude-code` —— Claude Code（Anthropic 官方 CLI，P1 通用 agent）

| | |
|---|---|
| harness 名 | `Claude Code`（`launch.json` 与 `config.yaml` 的 `harness` 字段，也是 `command_for()` 的查找键） |
| 镜像 | `gb-claude-code-u:r1`，digest `sha256:51f06443cc7a61322360c4eb38bc868713d763be3a5fb170f438a20cf2be466c` |
| 版本 | `@anthropic-ai/claude-code@2.1.263`（npm，构建期装在统一基座上；shasum `724f3282ee21318b227a6a20cbc66af331ee0fa4`） |
| 范式 | P1 |
| 被测配置 | `cfg-claude-code-deepseek`（本目录的 `config.yaml`，**`enabled: true`**） |
| 状态 | **模型待换** —— 现在跑的模型是 `deepseek-chat`，不是 Claude |

## 为什么这个 harness 和别的不一样

Codex CLI 与 OpenHands 说的都是 **OpenAI 兼容**协议，容器里那两个
`OPENAI_BASE_URL` / `LLM_BASE_URL` 直接就能用。Claude Code 说的是
**Anthropic Messages API**（`POST {base}/v1/messages`，鉴权头是
`x-api-key` 或 `Authorization: Bearer`）—— 两套协议的请求体、头、路径都不同，
所以不能把 `$OPENAI_BASE_URL` 原样喂给它。

而 `api.anthropic.com` 从 f01/f02 两台机都是 **403（地区封锁，N-32）**。
出路是 DeepSeek 提供的 **Anthropic 兼容端点**：

```
https://api.deepseek.com/anthropic/v1/messages
```

主机仍是 `api.deepseek.com` —— **出向白名单（`MODEL_API_ALLOW`）一个字都不用改**，
`registry.collect_egress_hosts()` 与它的键集相等断言也照旧成立。变的只是**路径**。

## 怎么把模型指过去

边车的模型反向代理**按原样转发 path**（`runner/c41/egress_proxy.py::model_reverse_proxy`
只替换 `Authorization` 与 `Host`，不重写 path）。所以只要让容器把请求发到
`/anthropic/v1/messages`，到上游就正好是 DeepSeek 的兼容路径。

容器里 `OPENAI_BASE_URL` 是 `http://gateway:8081/v1`，Anthropic SDK 会自己在 base 后面接
`/v1/messages`，于是 base 要写成**削掉尾巴上的 `/v1` 再接 `/anthropic`**：

```sh
export ANTHROPIC_BASE_URL="$${OPENAI_BASE_URL%/v1}/anthropic"     # → http://gateway:8081/anthropic
export ANTHROPIC_AUTH_TOKEN="$$OPENAI_API_KEY"                    # 占位 key，边车换成真 key
export ANTHROPIC_MODEL=deepseek-chat
claude -p "$$(cat /task/INSTRUCTION.md)" --dangerously-skip-permissions --output-format text
```

**主机名一个字都没写死** —— 满足「base URL 只从 `env_required` 列的变量取」这条铁律
（写死就绕过边车，于是预算闸、`llm_log.jsonl`、出向白名单三样同时失效，而表面上一切正常）。

逐个 flag / 变量：

| 东西 | 干什么 | 不设的后果 |
|---|---|---|
| `-p "<题面>"` | 无头（print）模式，一次问答后退出 | 不加就进 TUI，非交互下挂到超时 |
| `--dangerously-skip-permissions` | 跳过每次写文件的交互审批与目录信任对话框 | 第一次要写 `/task/artifact.json` 时停下来等确认 |
| `--output-format text` | 纯文本输出到 stdout | 默认也是 text；显式写出来是为了将来换 `json` 时有一处可改 |
| `ANTHROPIC_AUTH_TOKEN` | 发 `Authorization: Bearer <占位>` | 用 `ANTHROPIC_API_KEY` 会改发 `x-api-key`，见下面「已知限制」第 1 条 |
| `ANTHROPIC_MODEL` 等**五个** `ANTHROPIC_*_MODEL` | 主模型 + 后台小模型全部指到 `deepseek-chat` | 只设 `ANTHROPIC_MODEL` 时后台调用仍点名 haiku，上游 model not found |
| `CLAUDE_CODE_MAX_OUTPUT_TOKENS=8000` | 压到 deepseek-chat 的输出上限内 | 首个请求就可能被上游按 `max_tokens` 超限拒掉 |
| `CLAUDE_CODE_MAX_CONTEXT_TOKENS=128000` | 告诉 Claude Code `deepseek-chat` 的真实上下文窗口 | 这一版的模型目录里没有 `deepseek-chat`，不设就按 **200k** 假设做 auto-compact —— 表现是无谓的中途压缩，不是报错 |
| `HOME=/task/.claude_home`、`CLAUDE_CONFIG_DIR=$$HOME/.claude` | 配置目录指到可写处 | 容器以 uid 1000 跑、`/` 下不可写 → 起步就 `PermissionError` |
| 预写 `.claude.json` | `hasCompletedOnboarding` / `bypassPermissionsModeAccepted` / 目录信任 | 首跑可能停在 onboarding 或信任对话框上 |
| `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` 与四个 `DISABLE_*` | 关遥测 / 自动更新 / 错误上报 | 那些请求会打到 `HTTP_PROXY`（`gateway:3128`，`ALLOW` 是空集）被拒并留痕 —— 不致命，但会往 `egress.jsonl` 里灌噪声 |

`NO_PROXY` 不用自己设：compose 模板里已经有 `gateway,localhost,127.0.0.1`，
所以到边车的那条明文请求不会被绕进正向代理。

## 边车这边为什么不用改

任务书预留了「需要加 `x-api-key` 头替换就改 `egress_proxy.py`」这一步。**实测结论是不用改**，
证据是 2026-09-06 在 f02 上对 `https://api.deepseek.com/anthropic/v1/messages` 打的三次探针
（脚本 `/data/shared/genebench/scratch/3.2/probe_anthropic.sh`，全程没有打印 key）：

| 探针 | 请求头 | 结果 |
|---|---|---|
| A | 只有 `Authorization: Bearer <真 key>` | **200** |
| B | 只有 `x-api-key: <真 key>` | **200** |
| C | `Authorization: Bearer <真 key>` **+** `x-api-key: sk-genebench-placeholder` | **200** |

C 是关键的一条：**两个头同时在、而 `x-api-key` 是占位串时，上游认 `Authorization`**。
也就是说即使 Claude Code 顺手带上一个占位 `x-api-key`，现行边车
（只替换 `Authorization`、没有的话就插一条）也已经足够。

代价是留了一个**边缘缺口**：`_client_key()` 只读 `authorization`，
所以 agent 把自带凭据放进 `x-api-key` 时不会被判 `foreign_credential`。
按上面 C 的证据，那把 key 在**这个上游**上也不会被采用（`Authorization` 优先），
所以不构成预算闸绕过。已登记 `ops/tickets_inbox/3.2-claude-code.md`（N-?），
**没有动共享文件 `runner/c41/egress_proxy.py`**。

## 冒烟（不打真 API 的那一半证据）

真跑之前先在 f02 上对着一个**假的 Anthropic 上游**跑了一遍
（`/data/shared/genebench/scratch/3.2/smoke_f02.sh`，`docker run --network host --user 1000:1000`，
命令直接从 `launch.json` 取、把 `$$` 还原成 `$`）。它证明的是链路那一半，零次真调用：

* 容器以 uid 1000 起得来，`HOME=/task/.claude_home` 可写，**没有停在 onboarding 或信任对话框上**；
* 请求 path 是 **`/anthropic/v1/messages?beta=true`** —— 边车原样转发 path，
  而 DeepSeek 对带这个查询串的请求回 200（第二次探针实测，与不带的那次同形）；
* 鉴权头是 **`authorization: Bearer sk-genebench-placeholder`**，
  **`x-api-key` 是 `null`** —— 这是「边车不用改」那条结论的直接证据；
* 请求体里 `model=deepseek-chat`、`max_tokens=8000`（`CLAUDE_CODE_MAX_OUTPUT_TOKENS` 生效）；
* 抓到一条 `[claude-code:unrecognized_model]` 警告 —— 由此加了 `CLAUDE_CODE_MAX_CONTEXT_TOKENS`。

冒烟里没有产物：假上游只会回一句纯文本，agent 没有工具调用可做。
**产物那一半只有真跑能证明**，见下面「真跑证据」。

## 已知限制

1. **模型待换。** 这一条是本 harness 现在最大的限制：跑的是 `deepseek-chat`，
   不是 Claude。要换回 Claude 真模型需要两样东西 ——
   ① 用户把 `ANTHROPIC_API_KEY` 落到 f02 的 `~/.config/genebench/secrets.env`（0600）；
   ② 一条能到达 `api.anthropic.com` 的出口（现在两台机都是 403 地区封锁，N-32）。
   换的时候要同时改三处，缺一处就是红（这是设计如此）：
   `config.yaml` 的 `model` / `base_url` / `api_key_env`、
   `runner/c41/egress_proxy.py::MODEL_API_ALLOW` 加 `api.anthropic.com`（共享文件规则）、
   以及 `launch.json` 里那五个 `ANTHROPIC_*_MODEL`。
   还要注意 `assert_registry_sane` 要求**所有已启用配置同一模型** ——
   单独把这一条换成 Claude 会当场红，那是 v1.0「一个模型 × 多种 harness」的实验设计，
   要混模型得先过 M7 的实验设计审定。
2. **`deepseek-chat` 在 Anthropic 兼容端点上的模型名会被上游改写。** 探针里请求
   `model=deepseek-chat`、响应里 `"model":"deepseek-v4-flash"`。
   所以别拿响应里的 `model` 字段当切片键 —— 切片键是 `config_id`。
3. **Anthropic 协议的 `usage` 键名与 OpenAI 不同**：`input_tokens` / `output_tokens`。
   边车的 `_norm_usage` 已经把这两个名字归一到 `prompt_tokens` / `completion_tokens`
   （`_USAGE_ALIASES`），所以 `llm_log` 里的 `usage` 与别的 harness 同形 —— 不用额外做什么，
   但换协议时值得先核这一条：抽不到 usage 与「上游没返回 usage」在数值上不可区分。
4. **`$` 一律写 `$$`**（N-101）。本命令里有三处：`$$CLAUDE_CONFIG_DIR`、
   `$${OPENAI_BASE_URL%/v1}`、`$$(cat /task/INSTRUCTION.md)`。写成裸 `$` 的表现是
   两臂 3 秒退出、零次模型调用，而日志上看起来"跑过了"。
5. **产物必须落在 `/task/artifact.json`。** 容器里的 `/task` 就是 run dir 的 `work/`。
   Claude Code 自己在运行期还会往 `/task/.claude_home` 里写配置与会话记录 ——
   那些进 `verify_run_dir_unchanged()` 的 `unexpected`，不是红。

6. **预算闸的 token 计数不含 `cache_read_input_tokens` —— 本 harness 上差 20 多倍。**
   边车的 `_norm_usage()` 在上游没给 `total_tokens` 时按
   `prompt_tokens + completion_tokens` 自己加（`egress_proxy.py:777`），
   而 Anthropic 协议把命中缓存的那部分输入单独记在 `cache_read_input_tokens` 里，
   **不在 `input_tokens` 内**。两个 run 的实测：
   闸计到的 `total_tokens` 合计 **247 055**，同一批 `llm_log` 里
   `cache_read_input_tokens` 合计 **5 387 136**（`open` 3 343 616 + `strict` 2 043 520）。
   也就是说 `--max-tokens` 这一闸在本 harness 上**比它以为的宽约 22 倍**。
   `--max-calls` 不受影响（一次调用就是一条），所以现在真正兜底的是 calls 那一闸。
   这不是本 harness 的故障，是边车的口径问题（`runner/c41/egress_proxy.py` 是共享文件）——
   已登记 `ops/tickets_inbox/3.2-claude-code.md`，**本卡没有改它**。
   实用后果：给本 harness 设 `--max-tokens` 时别指望它能挡住成本，按 `--max-calls` 设闸。
7. **别拿响应里的 `usage` 反推「上下文有多长」。** 单次请求最大 `prompt_tokens` 只有
   **17 934**（两臂都是），但 `cache_read` 每次上千到几万 —— 真实喂给模型的上下文
   比 `prompt_tokens` 大得多。Codex 那边是相反的形状（每次重发整个上下文，
   `prompt_tokens` 43k~68k、没有缓存），所以两个 harness 的 token 数**不可直接相比**。

## 真跑证据

batch `h_claude-code`，题目 `s2-cor-01`，两臂各一次（`--seq 1`），
镜像 `gb-claude-code-u:r1`（digest 见上表），2026-09-06。
真跑那条命令包在 `ops/gateway_lock.py` 里（N-125），从 f01 侧 ssh 到 f02。

| | `strict` | `open` |
|---|---|---|
| run_id | `s2-cor-01.strict.cfg-claude-code-deepseek.r01` | `s2-cor-01.open.cfg-claude-code-deepseek.r01` |
| `run_status` / `exit_code` | ok / 0 | ok / 0 |
| **`sr_bucket`** | **`scorable`** | **`scorable`** |
| **`validity`** | **`valid`** | **`valid`** |
| `steps`（= `llm_log` 里 `decision=="allow"` 的条数） | **35** | **62** |
| `gate_failed` / `unobservable` / `findings` | 空 / 空 / 空 | 空 / 空 / 空 |
| 16 个探针 | 全 `clean` | 全 `clean` |
| 产物 | `work/artifact.json` 898 B + `work/panel.csv` 2 783 973 B | `work/artifact.json` 2 109 B + `work/panel.csv` 2 783 973 B |
| Align / Adj / Cal | 1.0 / 1.0 / 1.0 | 0.0 / 1.0 / 1.0 |
| effect（两档锚归一） | 100.0 | 75.33 |
| tokens（prompt / completion） | 51 198 / 48 196 | 66 757 / 80 904 |
| 墙钟 | 577.3 s | 798.5 s |

`--max-calls 100` 那一闸**两臂都没撞**（35 与 62），`budget_exhausted_runs = 0`。

落点：

* run 根 f02:`/data/genebench_runner/h_claude-code/runs/runs/`；
  拉回 f01 的那份在 `/data/shared/genebench/runs_in/h_claude-code/`；
* 结算表 `ops/reports/h_claude-code/`（`scores/*.score.json`、`table_a.csv`、
  `table_b.csv`、`records.json`、`summary.md`）——
  表头带「不是实验数据」：**它证明的是链路，不是模型能力**；
* 记账：`ops/api_usage.py` 从 1 377 次涨到 **1 474** 次（+97 = 35 + 62），36 个 run。

两条值得写下来的观察（都是**实验观察，不是 harness 故障**）：

1. `strict` 臂 `Align = 1.0`、`open` 臂 `Align = 0.0` —— 裸臂没把字段名对齐到
   `market_view_v1`。两臂的 `INSTRUCTION.md` 不同、其余文件逐字节相同（E-ARM），
   所以这个差就是协议臂的差。
2. `unexpected_files` 里是 `work/.claude_home/**`（Claude Code 自己的配置与会话记录）。
   这不是红：`work/` 的 P8 封闭在**注入时**结账，运行期写的东西由
   `verify_run_dir_unchanged()` 按 `harvest.PRODUCED_*` 分类。
   **`.claude_home` 里没有断链的符号链接** —— 这一点特意查过：
   Codex 的 `.codex/tmp/arg0/` 有，照搬回 f01 之后网关的红线 5 守门 `stat` 不到它们、
   拒绝启动（2026-09-05 实测 10 分钟数据面停摆），所以 `ops/score_runs.py` 给它加了
   `--exclude=.codex/`。本 harness **不需要**那样一条排除。

### 收尾复核（2026-09-06，第二位代理，零次新的真调用）

把 f01 拉回的两份 `log/llm_log.jsonl` 重新数了一遍，与 f02 上的原件行数一致
（`open` 62 行 / `strict` 35 行，f02:`/data/genebench_runner/h_claude-code/runs/runs/`）：

| | `strict` | `open` |
|---|---|---|
| `decision` | `allow` × **35**（无 deny） | `allow` × **62**（无 deny） |
| HTTP `status` | `200` × 35 | `200` × 62 |
| `upstream` | `api.deepseek.com` × 35 | `api.deepseek.com` × 62 |
| `path` | `/anthropic/v1/messages?beta=true` × 35 | 同上 × 61，`/anthropic/v1/messages/count_tokens?beta=true` × 1 |
| `usage` 有数 | 35 / 35 | 61 / 62（`count_tokens` 那条本来就不回 `usage`） |
| `usage` 键 | `prompt_tokens` / `completion_tokens` / `total_tokens` / `cache_creation_input_tokens` / `cache_read_input_tokens` | 同左 |
| 请求头里的 `authorization` | `<stripped>` | `<stripped>` |

三条结论：

* **wire 形状确实是 Anthropic Messages，不是 OpenAI 兼容** —— path 是 `/v1/messages`
  （不是 `/v1/chat/completions`），请求头带 `anthropic-version: 2023-06-01` 与
  `anthropic-beta: claude-code-…`，`User-Agent: claude-cli/2.1.263 (external, sdk-cli)`。
  这条是「这个 harness 真的在说它自己的协议」的机器证据，不是从文档推的。
* **`llm_log` 里没有真凭据。** `request_head` 里 `authorization` 一律是 `<stripped>`
  （边车的 `_strip_auth()`）；整棵 `$GB/runs_in/h_claude-code/` 里所有 key 形态的命中
  都是那条具名例外的占位串 `sk-genebench-placeholder`（出现在容器抄下来的
  `compose.yml` / `egress_proxy.py` 与 Claude Code 自己的会话 jsonl 里），
  **没有一处是真 key**。
* **上游自报的模型是 `deepseek-v4-flash`**（96 个响应体里全是它），而我们请求的是
  `deepseek-chat` —— 与 Codex 那边 1 196 次的统计同结论。见「已知限制」第 2 条。

## 构建（在 f02）

```sh
# 在 f01：先把 exec 树同步过去（**必带 --with-launch-data**，否则 f02 上 by_id 找不到 config_id）
cd /data/shared/genebench/repo && ops/push_exec_to_f02.sh --with-launch-data

# 在 f02（build.sh 没有执行位，一律用 sh 调）：
ssh -o ConnectTimeout=120 ljn@192.168.1.219 \
  'cd /data/genebench_runner/exec && sh harnesses/build.sh claude-code --dry-run'
ssh -o ConnectTimeout=120 ljn@192.168.1.219 \
  'cd /data/genebench_runner/exec && sh harnesses/build.sh claude-code'
```

tag 从 `launch.json` 的 `image` 取（`gb-claude-code-u:r1`）。**tag 已存在时真构建会被拒**——
那是故意的：重打一个被 `--digest` 钉住的 tag 会让所有已出集 bundle 的通行证对不上。
要新版本就换 tag（改 `launch.json` 的 `image`），再把新 digest 回填到本文件与
`Dockerfile` 顶部注释。

复核「仓库里这份 Dockerfile 就是构建出现网镜像的那一份」：用 `--tag gb-claude-code-u:r1-verify`
重建、比 digest、一致后 `docker rmi` 掉验证 tag。**不要用 `--no-cache`「更严格地」复核** ——
`npm install` 不是逐字节可复现的，那会装到同一版本却产出不同的层 digest，
那不是回归，是方法本身不适用（见 `harnesses/codex/README.md §4`）。

现网核过（2026-09-06 收尾）：f02 上 `gb-claude-code-u:r1` 的 image ID 是
`sha256:51f06443cc7a61322360c4eb38bc868713d763be3a5fb170f438a20cf2be466c`，
与本文件表头、`Dockerfile` 顶部注释、以及出集时 `--digest` 传的那一串**逐位相同**。

## 出集 → 推送 → 真跑 → 结算（本 harness 实测过的四条命令，照抄）

```sh
cd /data/shared/genebench/repo
PY=/data/shared/genebench/env/bin/python
DIG=sha256:51f06443cc7a61322360c4eb38bc868713d763be3a5fb170f438a20cf2be466c
STG=/data/shared/genebench/staging/h_claude-code_s2-cor-01

# ① 出集（--image 是**不带 tag 的仓库名**）
rm -rf "$STG"
$PY ops/export_bundle.py s2-cor-01 --staging "$STG" --digest "$DIG" --image gb-claude-code-u

# ② 推送（唯一允许的入口，答案面守门在这里，别手写 rsync）
ops/push_bundle_to_f02.sh "$STG/tasks/s2-cor-01" \
  /data/genebench_runner/h_claude-code/runner/tasks "$STG/s2-cor-01.manifest.json"

# ③ 真跑（**必须包在网关锁里**，N-125；不拿锁并发 = 网关 OOM）
$PY ops/gateway_lock.py --what "3.2-claude-code:真跑 s2-cor-01 / cfg-claude-code-deepseek" -- \
  ssh -o ConnectTimeout=120 ljn@192.168.1.219 \
  "umask 022; export PYTHONDONTWRITEBYTECODE=1; cd /data/genebench_runner && \
   python3 exec/ops/run_f02_a1.py \
     --bundle   /data/genebench_runner/h_claude-code/runner/tasks/s2-cor-01 \
     --manifest /data/genebench_runner/h_claude-code/runner/tasks/s2-cor-01.manifest.json \
     --config-id cfg-claude-code-deepseek --arms strict,open --seq 1 \
     --timeout 1500 --max-calls 100 --max-tokens 3000000 \
     --run-root    /data/genebench_runner/h_claude-code/runs \
     --results-dir /data/genebench_runner/h_claude-code/results"

# ④ 结算（注意 runs/runs —— 见下面那条）
$PY ops/score_runs.py --batch h_claude-code \
  --remote /data/genebench_runner/h_claude-code/runs/runs

# ⑤ 记账
$PY ops/api_usage.py
```

三条容易踩的：

* **`--remote` 要写 `.../runs/runs`。** `run_f02_a1.py --run-root X` 会在 `X/runs/` 下面
  **再建一层**，真跑得到的 run dir 是 `<run-root>/runs/<run_id>`。照
  `harnesses/README.md §4④` 抄的结果是 **「runs: 0；问题: 0」** ——
  不报错、退 0、看起来像「跑完了但没结果」的**假成功**。已登记票据。
* **`--max-tokens` 给 3 000 000，别用默认的 600 000。** 本 harness 两臂实测计到
  99 394 与 147 661，默认值够；但那是**没数 `cache_read` 的口径**（已知限制第 6 条），
  且换题目后上下文会长，留余量比事后重跑便宜。真正的护栏是 `--max-calls 100`。
* **`umask 022; export PYTHONDONTWRITEBYTECODE=1`**（红线 7）。f02 上少了这两句，
  0775 的 `__pycache__` 会把 f01 侧的红线 5 守门跑红，连累别的代理。
