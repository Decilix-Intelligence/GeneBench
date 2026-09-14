# `harnesses/` —— 给 GeneBench 接一个新的通用 harness

面向**外部运行者**：你手上有一个通用 CLI agent（Codex CLI、Claude Code、Aider、
Cline、gemini-cli……），想让它在 GeneBench 上跑一遍。本文是那件事的**全部**手册 ——
读完能接上、能构建、能跑通一道题、能拿到结算表。

范式是 **P1**：一个容器 + 一组环境变量 + `/task/INSTRUCTION.md`（题面）
+ `/task/artifact.json`（产物）。GeneBench 不改你的 agent，也不往它里面塞适配器 ——
它只负责把题面放进去、把模型端点指过来、把产物收走。

> `integrations/` 的结构与本目录**完全一样**，区别只在语义：`harnesses/` 放**通用 CLI**
> （阶段三），`integrations/` 放**专用系统**（阶段二）。两棵树被
> `runner/c42/harness_commands.py::discover_launch_specs()` 与
> `runner/registry.py::load_data_configs()` 一视同仁地遍历，`harness` 名与 `config_id`
> 在**两棵树之间**也不许重复。schema 与命令只写在本文一份，`integrations/README.md` 指过来 ——
> 两份会漂，而漂的表现是「照着文档做却跑不通」。

**为什么是数据驱动**：阶段二/三有十个人并行施工。如果每接一个系统都要改
`harness_commands.py` 与 `registry.py`，那两个文件就是十个人的写冲突现场。
现在每人**只加自己那一个目录**，两个共享文件一行都不用动。

---

## 0. 十分钟版

```
harnesses/<id>/            # 目录名就是 id（小写、`-` 分词）
  Dockerfile               # FROM gb-base:bookworm-r1，只装 harness 本身
  launch.json              # 怎么起：镜像 + 容器内命令 + 必需环境变量
  config.yaml              # 被测配置：config_id / harness / model / base_url / …
  README.md                # 这个 harness 怎么把模型指到 OpenAI 兼容端点、已知限制
```

1. 写这四件文件（§1）。
2. `ops/push_exec_to_f02.sh --with-launch-data` 把它们同步到执行面（§3）。
3. 在 f02 上 `sh harnesses/build.sh <id>` 构建镜像、拿 digest（§3）。
4. 出集 → 推送 → 真跑 → 结算，四条命令（§4）。
5. 跑挂了对着 §5 查。

四件文件缺一件、`launch.json` 键集不对、`command` 里有裸 `$`、`Dockerfile` 不是从统一基座起 ——
`ops/test_harness_contract.py` 都会红。**先跑它，再往下走**：

```sh
cd /data/shared/genebench/repo
ulimit -n 8192
/data/shared/genebench/env/bin/python -m pytest ops/test_harness_contract.py -q -p no:cacheprovider
```

---

## 1. 一个 harness 要提供什么

### 1.1 `Dockerfile`

```dockerfile
# 来源 / 镜像名 / digest 写在顶部注释里（构建后回填，见 §3）
FROM gb-base:bookworm-r1
RUN npm install -g "@example/agent@1.2.3" 2>&1 | tail -3 && example-agent --version
```

铁律四条：

* **`FROM gb-base:bookworm-r1`，只此一条 FROM。** 统一基座是 N-62 的裁定：
  三个 harness 各用各的官方基座时，实测 pandas 只有一个基座有、版本还与题面钉的不一致 ——
  那样主表上「harness 差异」这一列里就混进了运行时差异，而 S2/S3/S7 的产出是
  parquet/csv **数值**，pandas 与 pyarrow 版本恰恰会影响它们。基座已经带好
  `python 3.12 / node 22 / pandas 2.3.3 / pyarrow 25.0.1`。
  多条 `FROM` 会被注入器 P4c 当场拦掉。
* **只装 harness 本身。** 不得装行情库（yfinance、akshare、tushare、baostock…）：
  被测系统必须经数据网关取数，自带行情库等于绕过 as-of 强制 ——
  而绕过之后网关 `access_log` 干干净净、前视探针全绿，**失效是无声的**。
* **构建期可出网，运行期不可。** PyPI / npm 在 f02 实测 200。运行时任务容器挂在
  `internal: true` 的 `gb_task` 网络上，唯一的出口是边车。所以依赖一律构建期装死，
  不要留 `pip install` 在启动命令里（那会被卡 4.1 §3.4 拦：要把包仓库放进出向白名单，
  而那正是白名单膨胀的唯一真实来源）。
<!-- P2-2026-09-13 -->
* **不要 `FROM` 任何公网镜像 —— 只 `FROM gb-base:bookworm-r1`。** 理由是上一条说的统一基座，
  **与网络无关**。会踩网络的是**基座自己**：`build/base/Dockerfile` `FROM` 的是 `docker.io`
  上的 `python:3.12-slim-bookworm`，而 `docker.io` **通不通要按你的机器现判** ——
  发布方内网被墙（所以 f02 上基座是预先构好的，拉不到的表现是一条会被误读成网络抖动的
  pull 超时），**外部机器上这条路是通的**：2026-09-13 在一台干净的 Linux 机器上
  `docker build --no-cache` 实测 **69 秒**构出同一个基座，`pip freeze --all` 与发布方那份逐行相同。

顶部注释按 codex / openhands 那两份的样子写（镜像名 + digest + 基座），
这样镜像的来历在仓库里可复核 —— 构建仍在 f02 跑，f01 没有容器运行时。

### 1.2 `launch.json`

键集**恰好**这六个，缺一个多一个都在 import 期 `RegistryError`：

| 键 | 类型 | 说明 |
|---|---|---|
| `harness` | str | **与 `config.yaml` 的 `harness` 逐字相同**；它是 `command_for()` 的查找键 |
| `paradigm` | `"P1"`\|`"P2"`\|`"P3"` | 范式轴：P1 通用 agent / P2 多智能体框架 / P3 领域专用循环 |
| `image` | str | 镜像名（如 `gb-cx-u:r1`）。digest 由出集时 `--digest` 钉，不写在这里 |
| `command` | str[] | 容器内命令，**JSON 数组**。`command_for()` 原样 `json.dumps` 交给 compose |
| `env_required` | str[] | 命令依赖的环境变量名。**只有名字，没有值**；而且**只登记、不校验** —— `harness_commands.py::_validate_launch` 只核它是不是字符串数组，**校验器不检查这些变量是否真的存在**于容器里。名字抄错是**静默**的，逐字照 §2.1 那张表抄 |
| `notes` | str | 踩过的坑写在这里 —— 下一个人读的是这一栏 |

**同一个 `harness` 名在两棵树里出现两次 = `RegistryError`。**
静默取其一会把「我明明加了却没生效」变成一次长调查。

**构建上下文就是 `harnesses/<id>/` 这个目录本身**（`build.sh` 跑的是
`docker build -t <tag> harnesses/<id>`）。所以：`Dockerfile` 里的 `COPY` 只能
从这个目录里拿东西，而**你可以往这个目录里放自己的文件**（驱动脚本、配置样例……）——
上面那四件是**必需**的，不是**全部**。判据只核四件在不在，多放的文件不会红。

命令必须做到四件事：

1. 把 `HOME`（以及 `<TOOL>_HOME` 之类）指到 **`/task` 下的可写处**并 `mkdir -p`；
2. 以 **`cat /task/INSTRUCTION.md` 的内容**为题面（位置参数或 stdin 都行）；
3. base URL **只从 `env_required` 列的变量取**；
4. 结束前把产物写到 **`/task/artifact.json`**。

产物信封里的 `(task_id, config_id, arm)` **由题面要求 agent 自己写**（从 §2.1 那三个
`GENEBENCH_*` 读），runner 收走产物后拿它与真值三核（`runner/c42/identity.py`）。
对不上即 `identity_mismatch`：整个 run **不可结算**（`sr_bucket = unscorable_agent`、
`scorer_output` 是 `null`），**harness 侧不许代写、不许改写成一致** ——
改写把「产物在伪装」变成「产物正常」，那正是这道核要挡的路。

#### 铁律一：`$` 一律写 `$$`（N-101）

compose 在**解析文件时**就把 `$VAR` 插值掉。实测：`mkdir -p "$CODEX_HOME"` 变成
`mkdir: cannot create directory ''`，**两臂 3 秒退出、零次模型调用**，
而日志上看起来"跑过了"。`$(cat …)` 同理写 `$$(cat …)`。

#### 铁律二：不要写死模型主机名

base URL 只从 `env_required` 列的变量取（§2）。写死主机名就**绕过了边车**，
于是预算闸、`llm_log.jsonl`、出向白名单**三样同时失效**，而表面上一切正常。

#### 铁律三：不要往 `work/` 里放文件

容器里的 `/task` 就是 run dir 的 `work/`，它是 **P8 文件集封闭**的：注入时清点一次，
多一个文件当场红。所以驱动脚本要**内联在命令里**（heredoc），不能先写一个
`work/driver.py` 再跑。agent 自己在运行期写的东西不受 P8 管（P8 在注入结束时结账），
但会被容器退出后的 `verify_run_dir_unchanged()` 按 `harvest.PRODUCED_*` 允许集
分类进 `unexpected`。

#### 示例（`harnesses/codex/launch.json`，现网在跑的那一份）

```json
{
  "harness": "Codex CLI",
  "paradigm": "P1",
  "image": "gb-cx-u:r1",
  "command": ["sh", "-c", "export CODEX_HOME=/task/.codex && mkdir -p \"$$CODEX_HOME\" && cd /task && codex exec -c model_provider=deepseek -c 'model_providers.deepseek={name=\"DeepSeek\",base_url=\"'\"$$OPENAI_BASE_URL\"'\",env_key=\"OPENAI_API_KEY\"}' -c model=deepseek-chat --skip-git-repo-check --ephemeral --dangerously-bypass-approvals-and-sandbox -C /task \"$$(cat /task/INSTRUCTION.md)\""],
  "env_required": ["OPENAI_BASE_URL", "OPENAI_API_KEY"],
  "notes": "compose 解析期会吃 $，命令里一律写 $$（N-101）。CODEX_HOME 指到 /task 下：任务容器以 uid 1000 跑、HOME 不可写。…"
}
```

（`harnesses/openhands/launch.json` 是另一种形态：那个版本**没有 CLI**，
命令里内联了一段 SDK 驱动的 heredoc。两份都别改 ——
`ops/test_launch_registry.py` 断言它们与迁移前的硬编码常量**逐字节相同**。）

### 1.3 `config.yaml`

键集**恰好**这七个：

| 键 | 类型 | 说明 |
|---|---|---|
| `config_id` | str | 主表切片键，进 `x-genebench-config-id`。**与内置三条重名即红** |
| `harness` | str | 与 `launch.json` 的 `harness` 一致 |
| `model` | str | `assert_registry_sane` 要求**所有已启用配置同一模型** |
| `base_url` | str | 必须 `https://`，且主机不得在 `MARKET_DATA_HOSTS` 里 |
| `api_key_env` | str | 必须以 `_API_KEY` 结尾。**只有名字，没有值**（红线：凭据不进仓库） |
| `note` | str | 一句话说明 |
| `enabled` | bool | `true` 合并进 `CONFIGS`；`false` 只登记到 `PENDING_CONFIGS` |

**模型 key 还没到位就写 `enabled: false`，`note` 里写「模型待换」。**
`enabled: false` 的那些**照样过**三条判据（https / `_API_KEY` 后缀 / 非行情源）——
因为翻开关的那一刻不会有人重新审一遍 `base_url` 指到哪。
`enabled: false` 的 `config_id` 也**找不到**：`by_id()` 会明说「登记了但 enabled: false」，
而不是「未知 config_id」。

```yaml
config_id: cfg-example-deepseek
harness: Example Agent
model: deepseek-chat
base_url: https://api.deepseek.com
api_key_env: DEEPSEEK_API_KEY
note: 通用 CLI harness，经 base URL 指到 DeepSeek
enabled: false
```

**关于 `ops/test_c41.py` 那条 `len(REG.CONFIGS) == 3`**：它已于 `c36c5e6` 换成
`test_v10_is_one_model_many_harnesses`（同一模型 + 内置三条仍在 + `config_id` / `harness`
互异），**翻 `enabled` 现在不会把它跑红**。旧手册教读者「预先接受这一条红」——
那是「恒红当绿」的入口。今天仍在这里见到红，说明你的工作树落后，**那就是一条真红**。

### 1.4 `README.md`

一页：这个 harness 怎么把模型指到 OpenAI 兼容端点（贴命令、说清哪个 flag 干什么）、
版本、已知限制、踩过的坑。`harnesses/codex/README.md` 与
`harnesses/openhands/README.md` 是两份可照抄的样子。

---

## 2. 模型端点 env 契约

### 2.1 容器里能看见什么

任务容器的 `environment`（`runner/c41/runner_core.py::COMPOSE_TMPL`，逐字）：

| 变量 | 值 | 说明 |
|---|---|---|
| `OPENAI_BASE_URL` | `http://gateway:8081/v1` | 边车的**模型反向代理** |
| `OPENAI_API_BASE` | `http://gateway:8081/v1` | 同上，老 SDK 用这个名字 |
| `LLM_BASE_URL` | `http://gateway:8081/v1` | 同上，litellm 系用这个名字 |
| `OPENAI_API_KEY` | `sk-genebench-placeholder` | **占位** key |
| `LLM_API_KEY` | `sk-genebench-placeholder` | 同上 |
| `GENEBENCH_GATEWAY` | `http://gateway:18080` | **数据网关**（取行情走它，题面里会说） |
| `GENEBENCH_TASK_ID` / `GENEBENCH_RUN_ID` / `GENEBENCH_CONFIG_ID` / `GENEBENCH_ARM` | | 切片键，写日志用。**四个都带 `GENEBENCH_` 前缀** —— 容器里没有裸的 `RUN_ID` / `ARM`，按短名取到的是空串（同源：`runner/c41/runner_core.py::COMPOSE_TMPL` 与 `runner/c42/identity.py::ENV_BY_KEY`） |
| `HTTP_PROXY` / `HTTPS_PROXY` | `http://gateway:3128` | 正向代理；`ALLOW` 现在是**空集**，一切 CONNECT 都被拒并留痕 |
| `NO_PROXY` / `no_proxy` | `gateway,localhost,127.0.0.1` | 取数据网关走的是**明文 HTTP**，必须绕开上面那个正向代理。**不许在命令里覆盖**（agent CLI 普遍读写这两个变量）—— 把 `gateway` 覆盖掉之后，到网关的请求被 `HTTP_PROXY` 劫给 CONNECT 代理、代理回 **405**，症状看起来像**网关坏了**（D-10；`runner_core.py` 的 L-9 判据盯着这一条） |

> ⚠ **产物 schema 顶层 required 里有 `seed`，而容器里没有 `GENEBENCH_SEED`。**
> 上面那张表就是 `COMPOSE_TMPL` 的全部 —— 四个切片键里**没有 seed**（实测，卡 6.4）。
> 今天唯一能拿到它的地方是 `GENEBENCH_RUN_ID` 的尾巴：`<task>.<arm>.<cfg>.r01` 的
> `r01` 就是 `seed=1`。**别猜 0**：写错的 seed 不会让任何东西变红，它只是把
> 「这是第几次重复」记错。要不要真的注入一个 `GENEBENCH_SEED` 已登记票据。

**真 key 不在任务容器里。** 它只出现在边车服务的 `GENEBENCH_MODEL_API_KEY`，
由 runner 从 f02 的 `~/.config/genebench/secrets.env`（0600）读进进程环境，
compose 里写的是 `${GENEBENCH_MODEL_API_KEY}` 引用 —— **不落 compose.yml、不落 run dir**。

### 2.2 边车怎么替换占位 key

`runner/c41/egress_proxy.py` 的模型反向代理（容器网 `gateway:8081`）逐请求做四件事：

1. 读客户端的 `Authorization`。**不是占位 key 就 403 `foreign_credential`** ——
   agent 自带一把 key 是一条未声明的资源：它绕开预算闸，也让 usage 归属对不上。
2. 查预算（§2.4）。
3. 把 `Authorization` 换成真 key、把 `Host` 换成上游，再对上游起 TLS 转发。
   **真 key 只在 `_replace_auth()` 那一行出现。**
4. 落 `llm_log`（§2.5），`Authorization` 剥掉再落盘。

所以容器里那把 `sk-genebench-placeholder` 是**公开的**，写进任何地方都没有问题。

### 2.3 白名单怎么加域名

出向白名单**只放模型 API 域名**。两处必须同源：

* `runner/registry.py` 里那条配置的 `base_url` 的 host；
* `runner/c41/egress_proxy.py::MODEL_API_ALLOW` 的键。

`ops/test_c41.py` 有一条 **键集相等**（不是包含）的断言，比的就是
`registry.collect_egress_hosts()` 的输出与 `MODEL_API_ALLOW`。手抄的那份必然漂 ——
现表只有 `api.deepseek.com` 一条，先前挂着的 anthropic / openai 两条的引用者写的是
「待 M6 复核」，也就是**没有任何真实配置需要它们**，而且实测 `api.openai.com`
从两台机 TCP 层不通、`api.anthropic.com` 403 地区封锁（N-32）。

**行情 / 新闻源一律不得入表**（`MARKET_DATA_HOSTS`）：放进去等于让被测系统绕过数据面取数。

> 你的 harness 要换模型（换 host）时：改 `config.yaml` 的 `base_url` **必须**同时改
> `MODEL_API_ALLOW`。`MODEL_API_ALLOW` 是共享文件，按共享文件规则改（flock 内读-改-提交，
> 只追加不重排）。**不改就是红**，这正是我们要的。

### 2.4 预算闸

每 run 的上限在 `runner/registry.py::RUN_BUDGET`（`max_calls: 100` / `max_tokens: 6000000`），
由注入器写进边车的 `--max-calls/--max-tokens`。超限时边车**不转发**，直接回一条
`budget_exceeded` 的错误响应，并在 `llm_log` 里落 `decision: "deny"`, `reason: "budget_exceeded"`,
带上当时的 `budget`（`calls`/`tokens` 计数）。

**上限不是一个固定数字，是按阶段的档**（`runner/registry.py::BUDGET_TIERS`，卡 4.3）：
默认 **100 次 / 6,000,000 tokens**（**N-388**，2026-09-10 用户裁定由 600,000 抬上来）；**S4 150 次 / 9,000,000 tokens**；
**S7 300 次 / 18,000,000 tokens**。注入器按 bundle `task.yaml` 里的 `stage` 取档
（`registry.budget_for(stage)`），接入方不用配。真跑命令里显式给的
`--max-calls` / `--max-tokens` **逐键覆盖档位** —— 给了哪个覆盖哪个。
S4 / S7 抬高的理由是它们是**多轮研究循环**：按 100 次跑，现场表现是
「agent 做到一半自己放弃了」，而不是一条显眼的错误。

> ⚠ **状态码：现行实现回的是 `429`，不是 `402`。**
> `runner/registry.py:83` 的注释写的是「超限边车直接 402」，而
> `runner/c41/egress_proxy.py` 里 `_deny_http(cli, 429, "budget_exceeded", …)`。
> **以代码为准（429）**；两处措辞不一致已登记（`ops/tickets_inbox/3.1.md`）。
> 判据请认 `llm_log` 里的 `reason == "budget_exceeded"`，别去 match 状态码 ——
> 那一位数字将来会被统一，而 `reason` 不会。

你的 agent 看到的表现：一次本该正常的 chat/completions 变成 HTTP 错误。
多数 SDK 会重试，重试同样被拒（不计入 calls，因为没转发）。跑批时看到
「后半程全是失败」而 `llm_log` 尾部全是 `budget_exceeded` = 撞闸，不是 harness 坏了。

### 2.5 `llm_log` 的形状与落点

* **落点**：容器里 `/var/log/gb/llm_log.jsonl`；宿主上 **`<run_dir>/log/llm_log.jsonl`**。
  它挂给**边车**，任务容器里看不见 —— agent 改不了自己的证据。
* **形状**：一行一个 JSON 对象。

  ```json
  {"ts": "2026-09-06T…Z", "task_id": "s2-cor-01", "decision": "allow", "status": 200,
   "method": "POST", "path": "/v1/chat/completions", "upstream": "api.deepseek.com",
   "usage": {"prompt_tokens": …, "completion_tokens": …, "total_tokens": …},
   "budget": {"calls": 7, "tokens": 123456},
   "request_head": "…（Authorization 已剥）", "request_body": "…", "response_body": "…"}
  ```

  被拒的那些是 `{"decision": "deny", "reason": "budget_exceeded" | "foreign_credential" | …}`。
* **它是 harness 无关的轨迹源**（裁定 2026-09-04）：Steps 从这里取，
  不逐 harness 写轨迹提取器 —— 逐 harness 的提取器有几个 harness 就有几种漂法，
  而两臂经的是同一个边车。
* 数一个 run 用了多少次真调用 = `decision == "allow"` 的行数。
  `/data/shared/genebench/env/bin/python ops/api_usage.py` 就是机器数这个的。

---

## 3. 构建

### 3.1 先把 `harnesses/` 同步到执行面

f01 是数据面（**没有容器运行时**），构建只能在 f02 跑。`harnesses/` 不在默认同步集里，
**必须加 `--with-launch-data`** —— 不带这个开关，f02 上 `discover_launch_specs()`
返回空、`load_data_configs()` 读不到，`by_id(<你的 config_id>)` 直接找不到。

```sh
cd /data/shared/genebench/repo
ops/push_exec_to_f02.sh --dry-run --with-launch-data   # 先看清单：推哪些文件、删哪些文件
ops/push_exec_to_f02.sh --with-launch-data             # 真推
```

它先在 f01 的 staging 上跑一遍执行面自己那道门（`runner/f02/answer_plane_guard.scan`），
干净才推；推完在 f02 侧再扫一次，并逐字节比对两侧的 `command_for("Codex CLI")`。

**`--dry-run` 也要带 `--with-launch-data`**：不带的话清单里只有 `genetask/` `ops/` `runner/` `vendor/` 四棵树，
`harnesses/` 与 `integrations/` 一行都不出现 —— 而那恰恰是你此刻唯一关心的两棵树。
带上开关时第 1/6 步会打印「`harnesses/` 与 `integrations/` 一并入列」，第 3/6 步扫过的文件数也跟着涨；不带开关看到「清单里没有我的 harness」**不是同步坏了**。

⚠ **它会把工作树里 `runner/`、`harnesses/`、`integrations/` 三棵树下别人未提交的改动也推过去**（后两棵是 `--with-launch-data` 带进同步集的；实测连别人还没提交的 `integrations/COST.jsonl` 一起推走）。推之前 `git status --porcelain` 看一眼，有别人的半成品就等一等。

### 3.2 构建镜像

```sh
ssh ljn@192.168.1.219 'cd /data/genebench_runner/exec && sh harnesses/build.sh <id> --dry-run'
ssh ljn@192.168.1.219 'cd /data/genebench_runner/exec && sh harnesses/build.sh <id>'
```

（从 f01 发起。`f01 → f02` 是架构里**唯一**允许的 ssh 方向，f02 → f01 必须保持不存在。）

`harnesses/build.sh` 做的事：

1. 核四件文件齐全；
2. tag **从 `launch.json` 的 `image` 字段取**（`--tag` 可覆盖）——
   构建与启动读同一个字段，「构建成功了、跑的还是旧镜像」这个坑就不存在；
3. 核 `Dockerfile` 的第一条有效指令是 `FROM gb-base:bookworm-r1`、且只有一条 `FROM`；
4. **基座不在本机就用仓库的 `build/base/` 当场构一次**（`--no-base-build` 关掉这个行为，
   `--dry-run` 只说不构；构建上下文不在时用 `GB_BASE_CONTEXT=<build/base 的路径>` 指过去）。
   构基座要能访问 `docker.io`、`nodejs.org`、`deb.debian.org`、`pypi.org` ——
   **这四个通不通按你的机器现判**：发布方内网到不了 `docker.io`，所以 f02 上基座是预先构好的；
   外部机器上 2026-09-13 实测 `--no-cache` **69 秒**构完（见 `build/base/README.md`）；
5. **目标 tag 已存在时默认拒绝**（要 `--force`；`--dry-run` 只提示、不拦）：重打一个被 `--digest` 钉住的 tag
   会让所有已出集 bundle 的通行证对不上；
6. `docker build`，然后打印 digest（= `docker image inspect --format '{{.Id}}'`，
   就是出集时 `--digest` 要的那一串）。

rsync 落地是 0600、**没有执行位**，所以一律 `sh harnesses/build.sh …`，别指望 `./`。

构建完把 digest 回填到 `harnesses/<id>/Dockerfile` 顶部的来历注释里。

---

## 4. 跑一道题：出集 → 推送 → 真跑 → 结算

四条命令**都在 f01 发起**。术语：`<task>` 是题号（如 `s2-cor-01`；
**可选题号取自 `genetask/params/v1.0-smoke40.yaml` 的 `task_id` 列** ——
`grep task_id genetask/params/v1.0-smoke40.yaml` 列出全部候选。题号写错时
`ops/export_bundle.py` 只回「参数表里 'xxx' 命中 0 行（要恰好 1 行）」，**不列候选**），
`<batch>` 是这一批的名字（如 `w31`，会成为 f02 上的 run 根与 f01 上的报告目录名），
`<config_id>` 是你 `config.yaml` 里那个（要 `enabled: true` 才找得到）。

```sh
cd /data/shared/genebench/repo
PY=/data/shared/genebench/env/bin/python
DIG=<sh256-from-build.sh>          # §3.2 打印的那一串
STG=/data/shared/genebench/staging/<batch>
```

### ① 出集（X 面 → bundle + 通行证）

```sh
rm -rf "$STG"
$PY ops/export_bundle.py <task> --staging "$STG" --digest "$DIG" --image <image-name-without-tag>
```

产物：bundle 在 `$STG/tasks/<task>`，通行证在 `$STG/<task>.manifest.json`。
出集器**不会**把答案面（`reference/` `scorer/` `gold/` …）放进 bundle。

但它**会写答案面**：`export_one` 里 `packager.write_task(b, ANSWER_ROOT)` 把
`$GB/reference/tasks/<set_id>/<task>/`（含 gold 切片）整棵**重建**一遍 ——
重建是确定性的（同一份 params + `ops/capabilities.json` 出同一棵树），
但它落在**共享数据面**上。所以：同一道题被多个批次共用时，
**别在别人结算期间重出集**；换题号自己出自己的那一道。

### ② 推送（**唯一允许的入口**）

```sh
ops/push_bundle_to_f02.sh "$STG/tasks/<task>" /data/genebench_runner/<batch>/runner/tasks "$STG/<task>.manifest.json"
```

别手写 `rsync`：2026-09-04 就是手写 rsync 推了**父目录**，
把同级的 `reference/`（`canary.json` / `scorer.yaml` / `solve.py`）一起送上了执行面。
判据不在人的注意力里，判据在这个脚本里。它还会检查对面每小时的兜底扫描 timer
是不是 `enabled+active`（N-61：门有了、门后没人）。

### ③ 真跑（**必须包在网关锁里**）

```sh
$PY ops/gateway_lock.py --what "<卡号>:真跑 <task> / <config_id>" -- \
  ssh -o ConnectTimeout=120 ljn@192.168.1.219 \
  "umask 022; export PYTHONDONTWRITEBYTECODE=1; cd /data/genebench_runner && \
   python3 exec/ops/run_f02_a1.py \
     --bundle   /data/genebench_runner/<batch>/runner/tasks/<task> \
     --manifest /data/genebench_runner/<batch>/runner/tasks/<task>.manifest.json \
     --config-id <config_id> --arms strict,open --seq 1 \
     --timeout 1500 \
     --run-root    /data/genebench_runner/<batch>/runs \
     --results-dir /data/genebench_runner/<batch>/results"
```

* **锁是必须的**（N-125）：网关是单 worker（取证完整性要求：`access_log` 用进程内锁，
  多 worker 会交错写坏行）。两批负载叠上来实测的后果是复合的 ——
  延迟 0.15 s → 1.2 s、oracle 撞 60 s 读超时、RSS 涨到系统 OOM 把网关杀掉、
  `access_log` 两批条目交错而三维切片分不开。
* `umask 022; PYTHONDONTWRITEBYTECODE=1` 也是必须的：红线 5 守门会拦 0775 的 `__pycache__`。
* **预算参数一个都不给**（**N-388**，2026-09-10 用户裁定）：默认档已经是
  **100 次 / 6,000,000 tokens**，`runner/registry.py::BUDGET_TIERS` 再按阶段往上抬 ——
  **S4 150 次 / 9M**、**S7 300 次 / 18M**，其余走默认（见 §2.4）。不给参数时注入器按 bundle
  的 `stage` 自动取档，接入方什么都不用配。
  **显式给 `--max-tokens` / `--max-calls` 会逐键压过档位**：随手写一个 `100` 会把 S4 的 150
  与 S7 的 300 打回去；随手写一个 `3000000` **比默认档还低**。撞闸的现场表现不是一条显眼的
  错误，是「agent 做到一半自己放弃了」（`llm_log` 尾部一片 `budget_exceeded`，分数照出）——
  §5 里那一行「后半程全是 HTTP 错误」说的就是它。
  **本节 2026-09-10 之前教的「接入验证一律按 3000000 跑」已作废**（该说法比现在的默认档低一半，
  是 600k 时代文档化的绕法）。
* 两臂：`strict` 带协议工件（`/task/protocol/`），`open` 是裸臂。
  两臂的 `INSTRUCTION.md` 不同，**其余文件逐字节相同**（E-ARM 断言）。
* **同一目标最多真跑 1 次 + 1 次重试**，重试只在失败原因是我们的链路（不是 agent 自身）时才算数。

**run dir 的取证面**（`--run-root` 下再一层 `runs/<run_id>/`，见 ④）：

| 路径 | 里面是什么 |
|---|---|
| `run.json` | 运行侧记录：`exit_code` / `elapsed_s` / `new_files` / `unexpected`，以及 **`stdout_tail` / `stderr_tail`（容器输出的尾部各 2000 字符）**。`run_f02_a1.py` 收尾时已 `down -v`，容器与 compose 日志都不存在了 —— **这是唯一留存的容器输出**，起步期的空变量报错、`PermissionError` 都在这里 |
| `inject.json` | 注入侧记录：注了哪些文件、各自 sha256（P8 文件集封闭的账本） |
| `log/egress.jsonl` | 边车的出向事件（`listen` / 放行 / 拒绝）。边车没起时它是空的 |
| `log/llm_log.jsonl` | 每次模型调用一行（§2.5）；`decision == "allow"` 的行数 = 真调用次数 |
| `work/` | 容器里的 `/task`：题面、夹具，以及 agent 写出来的 `artifact.json` |
| `compose.yml` | 这次真正渲染出来的 compose —— 怀疑环境变量注错了就看它 |

### ④ 结算（f01 主动拉，f02 上没有任何回连）

```sh
$PY ops/score_runs.py --batch <batch> --remote /data/genebench_runner/<batch>/runs/runs
```

* **`--remote` 要比 `--run-root` 多一层 `runs`**，这是本手册最容易抄错的一处：
  run 目录是 `runner/inject.py:381` 的 `run_root / "runs" / rid`，
  于是 `--run-root .../<batch>/runs` 真正落到的是 `.../<batch>/runs/runs/<run_id>`。
  少写一层不会报错 —— 它退 0 并打印 **`runs: 0；问题: 0`**，
  看起来像「跑完了但一道题都没做出来」，而实际是**结算根本没找到 run**。
  `ops/test_harness_contract.py::test_readme_scoring_remote_has_the_extra_runs_layer` 盯着这一条。

产物在 `ops/reports/<batch>/`：`scores/<run_id>.score.json`、`table_a.csv/.tex`、
`table_b.csv/.tex`、`records.json`、`summary.md`。

表头（caption）由 `ops/score_runs.py::caption_for()` 给。`m6` / `a1` 有各自的写法，
**其它 batch 名走通用回退**：`Table A — <batch>（接入/harness 验证，不是实验数据）`。
这句"不是实验数据"不是客套 —— 一张长得像主表的表会被当成实验结果读，
而它证明的是链路，不是模型能力。

### ⑤ 记账

```sh
$PY ops/api_usage.py
```

→ `/data/shared/genebench/scratch/api_usage/api_usage.{json,md}`，
从各 run 的 `log/llm_log.jsonl` 数 `decision == "allow"`。

---

## 5. 常见失败：症状 → 含义

| 症状 | 真正的原因 | 怎么修 |
|---|---|---|
| **两臂都 3 秒退出、零次模型调用**，`run.json` 的 `stderr_tail` 里 `mkdir: cannot create directory ''` 之类的空变量（compose 的 `The "XXX" variable is not set` 警告也在那里） | `command` 里写了裸 `$`，compose **解析期**就把它插值成空了（N-101） | 命令里所有 `$` 写成 `$$`，`$(…)` 写成 `$$(…)`。证据看 `<run_dir>/run.json` 的 `stdout_tail` / `stderr_tail`（§4③） |
| **两臂 20 秒退出、零次调用**，`run.json` 的 `stderr_tail` 里 `PermissionError: /.openhands`（或任何 `/` 下的路径） | 容器以 uid 1000 跑、**HOME 不可写**，harness 在起步时写配置目录 | `export HOME=/task/.xxx && mkdir -p $$HOME`；`<TOOL>_HOME` 同理 |
| `EAI_AGAIN` / `getaddrinfo failed` / 连 `gateway` 超时 | **边车没起**。典型是 N-100 那种：宿主与容器共用 `egress_proxy.py`，容器里它是 `/opt/egress_proxy.py`（只有两层父目录），`parents[2]` 直接 `IndexError` | 看 `<run_dir>/log/egress.jsonl` 有没有 `listen` 事件；没有就是边车自己炸了。**别去找 `docker compose logs`** —— 真跑收尾已 `down -v`，容器没了；边车起不来时 compose 的报错落在 `run.json` 的 `stderr_tail` 里（§4③） |
| 取数据网关时 **405**，或一切都像「网关坏了」 | harness 自己的命令覆盖掉了 `NO_PROXY`，到网关的**明文 HTTP** 被 `HTTP_PROXY` 劫给 CONNECT 代理（D-10） | 命令里不要设 `HTTP_PROXY` / `HTTPS_PROXY` / `NO_PROXY`；非设不可时 `NO_PROXY` 必须保留 `gateway`（§2.1） |
| 后半程全是 HTTP 错误，`llm_log` 尾部全是 `reason: "budget_exceeded"` | 撞预算闸（现行状态码 **429**，注释里那个 402 是旧措辞） | 调 `--max-calls` / `--max-tokens`，或接受它 —— 闸是护栏不是判据 |
| `403 foreign_credential` | agent 自带了一把 key（环境里、配置文件里、或写死在命令里） | 让 harness 只从 `OPENAI_API_KEY` / `LLM_API_KEY` 取占位 key |
| 结算出 `run_status: identity_mismatch`、`SR = 0.0`，而 `summary.md` 写「问题: 0」 | **不是 agent 答错**：产物信封的 `(task_id, config_id, arm)` 与容器里的 `GENEBENCH_*` 真值对不上（agent 把三键写死、或 `--config-id` 传错了） | 让 agent 从 `GENEBENCH_TASK_ID` / `GENEBENCH_CONFIG_ID` / `GENEBENCH_ARM` 读这三个值写进信封。它归 `unscorable_agent`、`scorer_output` 是 `null`，所以**主表上看起来像 0 分，其实是没判过**（`runner/c42/identity.py`） |
| 结果里 `no_artifact`，而 agent 明明"做完了" | 产物没写到 **`/task/artifact.json`**（写到别处、或写到了 `work/` 之外的路径） | 容器里的 `/task` **就是** run dir 的 `work/`；`artifact.json` 必须在 `/task/` 根下。写别处 = harness 配置错误，不是 agent 的失败 |
| `no_artifact` 且 run dir 里什么都没有 | 采集顺序被打乱：`harvest` 必须在 `down -v` **之前**，否则产物随卷消失 | 别自己写 up/down，走 `run_f02_a1.py` |
| 红线 5 守门报红、网关**拒绝启动** | 共享树上出现 0775 的 `__pycache__`，或 `$GB` 下有 go 可读的文件 | f02 上跑 runner 一律 `umask 022; export PYTHONDONTWRITEBYTECODE=1`；`$GB` 下自己建的东西 `chmod -R go-rwx` |
| 网关拒绝启动、`stat` 不到某些文件 | Codex 在 `.codex/tmp/arg0/` 下留了**断链的符号链接**，被 rsync 搬回 f01 | `ops/score_runs.py` 已 `--exclude=.codex/`；手工 rsync 时照抄 |
| `by_id: 未知 config_id` （在 f02 上） | `harnesses/` 没同步过去 | `ops/push_exec_to_f02.sh --with-launch-data` |
| `by_id: 登记了但 enabled: false` | `config.yaml` 里开关没翻 | 翻开关。（旧手册在这里让你预先接受 `ops/test_c41.py` 那条 `len(REG.CONFIGS) == 3` 的红 —— **该断言已改掉，现在不会红**，见 §1.3） |
| import 期 `RegistryError: launch.json 键集必须恰好是 …` | 多写了一个键（比如 `description`） | 删掉。多余键在校验器眼里是静默的、在写它的人眼里却像是生效了 |
| `RegistryError: harness 名重复` | 两棵树里有同名 harness | 改名。静默取其一 = 一次长调查 |
| 注入器 `P4c Dockerfile 有 2 条 FROM` | 多阶段构建 | 拆成两个镜像，或把构建产物直接装进单层 |

---

## 6. 边界（本文不管的事）

* **答案面永不上执行面**：`reference/` `scorer/` `runs_in/` `gold/` `memory_probe_answers/`
  的任何内容不进 f02、不进容器、不进 bundle。推送只走 `ops/push_bundle_to_f02.sh`，
  exec 树只走 `ops/push_exec_to_f02.sh`。
* **凭据不进仓库、不进日志、不进对话**：`config.yaml` 里只写变量名。
  真 key 在 f02 的 `~/.config/genebench/secrets.env`（0600），不要 `cat`、不要复制。
* **题面是冻结的**：`genetask/templates`、`genetask/params`、`ops/specs/artifact_schema` 等
  在冻结根下，改动要走重冻结记因（`ops/freeze_v10.py`）。接 harness 不该碰到它们 ——
  碰到了说明方向错了。
* **票据写 `ops/tickets_inbox/<卡号>.md`**，不要直接改 `ops/tickets.md`。
---

## 7. 模型只有 DeepSeek 一条现网链路；Qwen 的状态（⑲，2026-09-11）

**今天全部 13 条 `enabled: true` 的配置都是 `deepseek-chat`，经 `api.deepseek.com`。**
这不是「还没来得及加别的」，是 §2.3 与 `runner/registry.py::assert_registry_sane` 共同钉住的
**v1.0 实验设计：一个模型 × 多种 harness** —— 主表暴露的差异才归因到 harness。
`assert_registry_sane` 会对 `CONFIGS` 判「模型字段全相同」，**加一条别的模型当场红**。
放宽它要过 M7，**任何一张卡都不许顺手放宽**。

要加一条别的模型（比如 Qwen）而**不**动那条断言，路子是 `enabled: false`：
`load_data_configs` 把它收进 `PENDING_CONFIGS`，不进 `CONFIGS` —— 既不参与「同一模型」判据，
也**不进** `collect_egress_hosts()`，所以 §2.3 那条「键集相等」的断言**不会**要求你
往 `MODEL_API_ALLOW` 里加它的域名（反过来说：**没有 enabled 配置需要的域名不许进白名单**，
一个没人用的域名是纯粹的敞口）。`_one_config_sane` 对 pending 的也照判 https / `_API_KEY`
结尾 / 非行情源三条，写错照样当场红。

**Qwen 具体到哪一步了**：裁定是把 `opencode` 指到 dashscope 的 OpenAI 兼容端点
（`https://dashscope.aliyuncs.com/compatible-mode/v1`，key 变量名 `DASHSCOPE_API_KEY`）。
2026-09-11 实测：f02 **连得到**该域名（401 / 0.17 s），但 f02 的
`~/.config/genebench/secrets.env` 里**没有** `DASHSCOPE_API_KEY` —— 缺凭据，**没有切**，
真题也没跑。逐条前置、切换步骤与判据写在
[`harnesses/opencode/README.md`](opencode/README.md) §9。

**`@qwen-code/qwen-code`（Qwen Code CLI）不做**（裁定 ⑲）。它只在
`runner/c42/upstream_pins.py` 的 codex 那条 note 里作为 2026-09-04 的备选出现过，
codex 链路后来实测通了、备选未启用。**本文与手册里没有任何地方把它当计划中的一项。**
