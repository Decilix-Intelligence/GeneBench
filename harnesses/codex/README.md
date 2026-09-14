# `codex` —— OpenAI Codex CLI（P1 通用 agent）

| | |
|---|---|
| harness 名 | `Codex CLI`（`launch.json` 与 `config.yaml` 的 `harness` 字段，也是 `command_for()` 的查找键） |
| 镜像 | `gb-cx-u:r1`，digest `sha256:961e3878b28fc13ef2600254c4c4cbaceb7c337e2944fc173eaba1335752561a` |
| 版本 | `@openai/codex@0.153.2`（npm，构建期装在统一基座上） |
| 范式 | P1 |
| 内置配置 | `cfg-codex-deepseek`（在 `runner/registry.py::BUILTIN_CONFIGS` 里；本目录的 `config.yaml` 因此 `enabled: false`） |
| 模型状态 | **待换** —— 注册表写 `deepseek-chat`，上游实际服务的是 `deepseek-v4-flash`（见 §6） |

**这是 GeneBench 里跑得最多的一个 harness**（A1 冒烟、M6-lite 构造验收、M6b 都用它），
所以下面的每一条都是真跑出来的，不是读文档写的。§5 给出每一条的证据路径。

---

## 1. 怎么把模型指到 OpenAI 兼容端点

Codex 用 `-c` 覆盖配置，在**命令行上**造一个 provider，不写配置文件：

```
codex exec -c model_provider=deepseek \
  -c 'model_providers.deepseek={name="DeepSeek",base_url="'"$$OPENAI_BASE_URL"'",env_key="OPENAI_API_KEY"}' \
  -c model=deepseek-chat --skip-git-repo-check --ephemeral \
  --dangerously-bypass-approvals-and-sandbox -C /task "$$(cat /task/INSTRUCTION.md)"
```

要点：

* `base_url` 从 **`$$OPENAI_BASE_URL`** 取（边车注入的 `http://gateway:8081/v1`）。
  那一串引号（`"'"$$OPENAI_BASE_URL"'"`）是为了让变量在 TOML 值里展开，
  别"整理"它 —— 去掉之后 base_url 会变成字面量 `$OPENAI_BASE_URL`，
  Codex 报的是一个和网络无关的解析错。
* `env_key="OPENAI_API_KEY"` 让 Codex 从环境取 key，容器里那把是**占位** key
  `sk-genebench-placeholder`，边车转发时替换成真 key。
* `--ephemeral` + `--skip-git-repo-check`：`/task` 不是 git 仓库，不加就直接退出。
* `--dangerously-bypass-approvals-and-sandbox`：容器本身就是沙箱（`cap_drop: [ALL]`、
  `no-new-privileges`、`gb_task` 是 `internal: true` 的网络），再叠一层交互式审批
  会让非交互的 `codex exec` 卡住等输入。
* 题面是**位置参数**，不是 stdin：`"$$(cat /task/INSTRUCTION.md)"`。

换一个 OpenAI 兼容的模型，只需要动 `config.yaml` 的 `model` / `base_url` / `api_key_env`
与命令里的 `-c model=`；**不要**在命令里写死主机名 —— 写死就绕过边车，
而绕过边车的表现是"跑通了"，只是那一批的出向不再受白名单与预算闸管。
改 `base_url` 必须同时在 `runner/c41/egress_proxy.py::MODEL_API_ALLOW` 里加那个 host（共享文件）。

---

## 2. 预算：本 harness 最容易踩的一条

**`--max-calls` 不是 Codex 的约束闸，`--max-tokens` 才是。**

Codex 每次调用都把整个上下文重发一遍，实测 prompt 占总 token 的 **97~98%**，
每次调用的 prompt 在 **43k~68k** 之间（随题面与已走步数增长）。于是：

| 你给的 `--max-tokens` | 实际能跑到第几次调用 |
|---|---|
| 600,000（`registry.RUN_BUDGET` 的默认值） | 约 **13 次** |
| 3,000,000（M6 用的值） | 约 **44~66 次** |
| 20,000,000 | 撞不到，先撞 `--max-calls` |

`runner/registry.py:84` 那句注释说 600k "够 100 次长上下文调用" —— **对本 harness 不成立**，
差一个数量级。M6 的九次 `budget_exhausted` 全部出在 S4/S7 这两道长任务上（见 §5 的表）。
按 100 次调用配 token 上限的话，Codex 需要 **4.3M~6.8M**。

没有裁定改默认值（那是成本护栏、不是判据，且要连带别的 harness 一起掂量），
所以**跑 S4/S7 时请显式给 `--max-tokens`**，别用默认值。已登记
`ops/tickets_inbox/3.2-codex.md`。

判据侧注意：预算撞闸时边车回的是 **429**、`llm_log` 里 `reason == "budget_exceeded"`。
`registry.py:83` 注释里那个 402 是旧措辞。**认 `reason`，别 match 状态码**
（那一位数字将来会被统一，`reason` 不会）。

---

## 3. 已知限制 / 踩过的坑

* **`CODEX_HOME` 必须指到 `/task` 下。** 任务容器以 uid 1000 跑、HOME 不可写，
  Codex 起来第一件事就是写配置目录 → `PermissionError`。命令里先
  `export CODEX_HOME=/task/.codex && mkdir -p "$$CODEX_HOME"`。
* **`$` 一律写 `$$`**（N-101）。compose 在解析文件时就插值：`mkdir -p "$CODEX_HOME"`
  会变成 `mkdir: cannot create directory ''`，**两臂 3 秒退出、零次模型调用**，
  而日志上看起来像是"跑过了"。
* **`.codex/tmp/arg0/` 里有断链的符号链接。** `ops/score_runs.py` 的 `pull()` 因此
  `--exclude=.codex/`：照搬回 f01 之后网关的红线 5 守门 `stat` 不到它们 → **拒绝启动网关**
  （2026-09-05 实测：10 分钟数据面停摆）。产物与日志都不在 `.codex/` 里，排除掉没有损失。
  **改 `score_runs.py` 的 rsync 排除项时不要顺手删掉这一条**，`ops/test_harness_codex.py`
  会拦。
* **裸臂（open）吃 token 尤其凶**：A1 实测每次调用约 45k prompt，第 22 次就撞了当时 600k 的
  `--max-tokens`。见 §2。
* Codex 自己会往 `/task` 里写工作文件。`work/` 是 P8 封闭的，但封闭是在**注入时**结账、
  容器退出后由卡 4.3 的 `verify_run_dir_unchanged()` 按 `harvest.PRODUCED_*` 允许集复核 ——
  多出来的文件进 `unexpected`，不是红，但会出现在报告里。

---

## 4. 构建与镜像来历

构建在 **f02**（f01 没有容器运行时），读的是**本目录的 `Dockerfile`**：

```
# 在 f01：先把 exec 树同步过去（必带 --with-launch-data）
ops/push_exec_to_f02.sh --with-launch-data
# 在 f02：
cd /data/genebench_runner/exec && sh harnesses/build.sh codex --dry-run
```

`gb-cx-u:r1` 这个 tag **已经存在**，真构建会被 `build.sh` 拒绝 —— 那是故意的：
重打一个被 `--digest` 钉住的 tag 会让所有已出集 bundle 的通行证对不上。
要复核来历就构建到一个临时 tag 上再比 digest：

```
sh harnesses/build.sh codex --tag gb-cx-u:r1-verify
```

2026-09-06（卡 3.2）实测：digest = `sha256:961e3878b28f…`，与现网 `gb-cx-u:r1` **逐位相同**，
即"仓库里这份 Dockerfile 就是构建出现网镜像的那一份"。验证用的 tag 已 `docker rmi`。

一句注意：上面这次比对命中了 docker 的**层缓存**（`Using cache`），
它证明的是"同一基座 + 同一条 `RUN` 指令 → 同一条层链"，这正是我们要的判据。
**不要改用 `--no-cache` 来"更严格地"复核** —— `npm install` 不是逐字节可复现的，
`--no-cache` 会装到同一个版本但产出不同的层 digest，那不是回归，是这个方法本身不适用。

---

## 5. 真跑证据

Codex 是三个 harness 里证据最多的一个。M6 + M6b 合计 **29 个 run**，全部 `cfg-codex-deepseek`：

| 结局 | run 数 | 可评分？ |
|---|---|---|
| `ok` / validity=`valid` | 8 | 是 |
| `violation` / validity=`invalid` | 5 | 是 |
| `malformed` / validity=`invalid`、`sr_bucket=malformed` | 7 | **否**（artifact 采到了，但结构不合规） |
| `budget_exhausted` / validity=`null`、`sr_bucket=unscorable_agent` | 9 | **否**（agent 没做完，撞了预算闸） |

按卡 3.2 的口径（`no_artifact` / `malformed` 不算可评分）：**13/29 可评分**。
注意 `malformed` 那 7 个 scorer 其实**给出了** `validity=invalid` —— 若按"有 validity"
去数会得到 20/29，那是把口径放宽了一格。两个数字都不是坏消息，但别混着用。

**关键的一条：29 个 run 里没有一次 `no_artifact`。** 也就是说 harness 侧的产物路径
（`/task/artifact.json`）是对的 —— 每一次容器退出时都有东西可采。不可评分的 16 次
全部落在 agent 自己身上（7 次写出结构不合规的 artifact，9 次没做完就撞了预算闸），
没有一次需要"修 harness 后重试"。`steps` 跨 29 个 run 的范围是 **21~90**。

主表（M6 与 M6b 合并）：

- `cfg-codex-deepseek` / strict：SR=0.542 pass@1=0.25 ProgressRate=0.542 Steps=41.1 Latency=582.7 越权率=0.045
- `cfg-codex-deepseek` / open：SR=0.5 pass@1=0.333 ProgressRate=0.5 Steps=42.7 Latency=755.1 越权率=0.021

证据路径：

| 什么 | 在哪 |
|---|---|
| 合并报告（表 A/B、逐 run 记录） | `ops/reports/m6_all/`（`records.json` / `summary.md` / `table_a.csv` / `table_b.csv`） |
| 模型身份的网络侧证据 | `ops/reports/m6_all/served_model_evidence.json` |
| M6 单批报告 | `ops/reports/m6/` |
| M6b 单批报告 | `ops/reports/m6b/` |
| 原始 run 目录（21 个，含 `log/llm_log.jsonl`） | `$GENEBENCH_ROOT/runs_in/m6/` |
| 原始 run 目录（8 个） | `$GENEBENCH_ROOT/runs_in/m6b/` |
| A1 冒烟的 run 目录 | `$GENEBENCH_ROOT/runs_in/a1/` |

（`$GENEBENCH_ROOT` = `/data/shared/genebench`，在 f01 上。`runs_in/` 是**数据面**，
不进执行面、不进 bundle。）

---

## 6. 模型待换

`config.yaml` / `BUILTIN_CONFIGS` 里写的是 `deepseek-chat`，**但上游服务的不是它**。

`ops/reports/m6_all/served_model_evidence.json`（读 29 个 `llm_log.jsonl` 的响应体自报字段）：

* 响应体自报 `model` 的计数：`deepseek-v4-flash` **1196** 次，没有任何一次是 `deepseek-chat`；
* 上游 `/v1/models` 现在列的是 `deepseek-v4-flash` / `deepseek-v4-flash-vision-exp` / `deepseek-v4-pro`；
* 官方定价页与 `/v1/models` 都已**不再列** `deepseek-chat`。

也就是说 `deepseek-chat` 现在是上游的一个 alias。价目表因此把它做成 `deepseek-v4-flash`
的 `alias_of`，不另抄一份数字。**这一条不影响已有结论的可比性**（同一批 run 里所有配置
指的是同一个上游实体），但它意味着：

* 报告里"模型 = deepseek-chat"这句话要按 alias 读，不是按 served id 读；
* 换模型（无论换成 `deepseek-v4-pro` 还是别家）**要先过 M7 的实验设计审定** ——
  `registry.assert_registry_sane` 要求所有 enabled 配置同一模型，这是"固定模型效应"
  的设计，混模型会当场红。

---

## 7. 出集 → 推送（本 harness 的实测命令）

卡 3.2 在 `s2-cor-01` 上真跑过这两条（**没有**真跑模型）：

```
cd /data/shared/genebench/repo
PY=/data/shared/genebench/env/bin/python
DIG=sha256:961e3878b28fc13ef2600254c4c4cbaceb7c337e2944fc173eaba1335752561a
STG=/data/shared/genebench/staging/h_codex_s2-cor-01

rm -rf "$STG"
$PY ops/export_bundle.py s2-cor-01 --staging "$STG" --digest "$DIG" --image gb-cx-u
ops/push_bundle_to_f02.sh "$STG/tasks/s2-cor-01" \
    /data/genebench_runner/h_codex/runner/tasks "$STG/s2-cor-01.manifest.json"
```

`--image` 给的是**不带 tag 的仓库名 `gb-cx-u`**（不是 `gb-codex-u`，那个镜像不存在）；
`pin_image_digest` 把 bundle 的 `image/Dockerfile` 第一行改写成
`FROM gb-cx-u@sha256:961e3878b28f…`。

**读 bundle 时的一个陷阱**：`tasks/<id>/task.yaml` 里还有一个 `image:` 块，写着
`base: python:3.11-alpine` 和一个全零 digest。那是**死字段**，注入器读的是
`image/Dockerfile`。别照着它去判断跑的是哪个镜像。已登记 `ops/tickets_inbox/3.2-codex.md`。

真跑与结算的命令见 `harnesses/README.md` §4（真跑必须包在 `ops/gateway_lock.py` 里）。
