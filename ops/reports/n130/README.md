# N-130 复验：S7 在 300 次 / 18M 的档位里做得完（2026-09-10，W1 第 5 项）

**结论：N-130 可关。** 它记的那件事 ——「S7 在 ≤300 次调用的预算里做不完」——
**不成立了**，而且原因不是模型变强了，是**上一次的闸设在 90 次**。
这一次两臂各自**自己停下来**，一次 `budget_exceeded` 都没有：

| 臂 | 调用（全部 `decision=allow`） | prompt tokens | completion | 合计 tokens | 墙钟 | `run_status` | `sr_bucket` |
|---|---|---|---|---|---|---|---|
| `open`（裸臂） | **64** / 300 | 3,960,233 | 76,853 | **4,037,086** / 18M | 1464 s | `identity_mismatch` | `unscorable_agent` |
| `strict`（协议臂） | **87** / 300 | 5,580,144 | 82,935 | **5,663,079** / 18M | 1967 s | `violation` | **`scorable`** |

`budget_exhausted_runs = 0`（两臂都是）。`llm_log.jsonl` 里 64 / 87 行**全是 `allow`**，
没有一行 `budget_exceeded`。产物：两臂都落了 `work/artifact.json` + `work/ledger.parquet`。

**「有可评分产物」这一条达成**：`strict` 臂的 `sr_bucket = scorable`、`malformed = False`、
`validator_rejections = 0`，走完了评分器，判 `validity = invalid`，
卡在 `gate_failed = ['attribution_conservation']`（台账归因守恒）——
**那是一条内容判据，不是预算、不是格式**。S7 的 ε 路径从此有了真 agent 产物。

`open` 臂差一点：产物本身成形，但 `task_id` / `config_id` 两个字段被写成了 canary nonce
（`GBC-C-0d46b8780c87d7b0`），`arm` 写成 `"C"`、`seed` 写成 `0` —— 身份对不上，
判 `identity_mismatch` 进 `unscorable_agent`。**这也不是预算**。

## 与 2026-09-06 那四个 run 的对照

| run | 调用闸 | token 闸 | 停在 | 产物 |
|---|---|---|---|---|
| `r02.strict` | 150 | 3 M | **token 闸**（3,010,362，第 43 次）| 无 |
| `r02.open` | 150 | 3 M | **token 闸**（3,001,366，第 67 次）| 无 |
| `r03.strict` | **90** | 20 M | **调用闸**（90/90，token 只用 5.2 M）| 无 |
| `r03.open` | **90** | 20 M | **调用闸**（90/90，token 只用 5.6 M）| 无 |
| **本次 strict** | 300 | 18 M | **自己停的**（87 次 / 5.66 M）| **有，且 scorable** |
| **本次 open** | 300 | 18 M | **自己停的**（64 次 / 4.04 M）| 有（身份写错） |

`r03.strict` 停在 90/90 而这次 87 次就收工 —— **上一次离终点只差几次调用**。
N-130 原文那句「它缺的是回合数，不是上下文」判断是对的，缺的量比想象的小。

## 预算档：为什么走的是 300 / 18M，以及 6M 够不够

用户裁定原文有两处并列：「**S7 用 300 次 / 6M 跑一道验**」与「**走档位，不显式给**」。
`BUDGET_TIERS["S7"]` 是 300 次 / 18M，两者对不上 —— **CONFLICT，按「走档位」做**，
理由是：6M 那一档会在约第 100 次调用上撞 token 闸，而撞闸的表现是
「agent 做到一半自己放弃了」，**它长得像结论** —— 那正好会把 N-130
错误地关成「已知限制」。护栏定低了而把它读成能力，是这一整轮（N-388）在反对的事。

**事后看，两种读法这次都跑得完**：strict 用了 5.66 M，离 6M 还差 5.6%；open 用了 4.04 M。
也就是说 6M 那一档**这一次**够用，但余量只有一次调用左右。这个数据留在这里，
下次要收紧 S7 的 token 档时按它算，不要按 18M 反推。

跑批当场的证据：run 目录 `compose.yml` 与边车 `egress.jsonl` 的 `ready` 行都写着
`max_calls: 300, max_tokens: 18000000`，`budget_override = {}` —— **没有显式给过任何一个**。

## 三次尝试，前两次零调用（都是我们的链路，不是 agent）

真跑记账只有 **151 次**（64 + 87），因为前两次尝试**一次模型调用都没发生**：

1. **10:08–10:40，codex 卡在 `Reading additional input from stdin...`（32 分钟，0 次调用）。**
   `runner_core` 用的是 `docker compose run --rm task`，而 `run` **会把父进程的 stdin
   透传进容器**。我的调用链（ssh → nohup → gateway_lock → ssh f02 → run_f02_a1 → compose run）
   一路都是**开着的管道**，于是 codex 在等一个永远不来的 EOF。
   **修法**：起跑脚本 `< /dev/null`。**根治在 `runner_core`**（`compose run -T` 或
   `stdin=DEVNULL`）—— 已登记，见 `ops/tickets_inbox/W1.md`。
   这条坑的恶劣之处：容器一直 `Up`、`docker logs` 只有一行、`llm_log.jsonl` 干脆不存在，
   **看起来像「agent 在思考」**，而 `--timeout 7800` 会让它这么「思考」两个小时。
2. **10:41，`边车起不来`（0 次调用）。** 上一步我在 f01 杀了 `run_joblist`，
   **f02 上的容器没跟着死**，还占着 `gb_task` 网络，于是 `compose down -v` 删网络失败、
   新的 `compose up gateway` 起不来。**杀跑批要连对面的容器一起收**（`docker rm -f`）。
3. **11:26–12:00，strict 补跑成功。** 用 `--retry-failed` 时还撞到一条：
   清单被筛成只剩 `strict` 一行，出集步骤看到 `arms=['strict']` 当场拒
   （「没有参照臂 `open`」）—— 补跑单臂要加 `--no-export`（bundle 早在 f02 上）。

**结果库里那条幽灵行已显式摘掉**：第 2 次尝试把 strict 记成了 `no_artifact` 收进库，
而那个 run 根本没跑起来。留着它，Table A 上就永远有一个「S7 strict 交白卷」的读数，
而那件事没有发生过。备份 `$GB/results/v1/results.jsonl.w1bak-20260910T121025`，
处置口径就是库自己那句报错给的（「先把这一批从 results.jsonl 里显式摘掉并记在票据里」）。

## 产物与路径

* 表：`ops/reports/n130/table_a.{csv,md,tex}`（`strict` 行 `SR=1 / ProgressRate=1 / pass@1=0`）
* 逐 run：`ops/reports/n130/records.json`、`ops/reports/n130/scores/`、`summary.md`
* 清单：`$GB/runs_in/n130/jobs.jsonl`（终态 `done 2`）
* 执行面：`f02:/data/genebench_runner/n130/runs/runs/s7-cor-01.{open,strict}.cfg-codex-deepseek.r01/`
  （`work/artifact.json`、`work/ledger.parquet`、`log/llm_log.jsonl`、`log/egress.jsonl`）
* 真 API 累计 `ops/api_usage.py`：**2668 → 2819 次**（77 → 79 个 run），本次增量 **151 次 / 2 个 run**。

## 留给下一张卡的两条

* **`attribution_conservation` 为什么不过**：这是 S7 判据里的内容项，
  这一次是**第一次**有真 agent 产物走到它面前。差在哪没查（不在本卡范围）。
* **`identity_mismatch` 是不是题面问题**：裸臂把 canary nonce 抄进了 `task_id` / `config_id`。
  协议臂没犯（validator 拦了 0 次，说明它自己就写对了）。
  两臂同一份题面 —— 值得看一眼题面里身份字段那段话是不是有歧义。

## 这一次读数的一条限定：网关在跑的过程中被自己的内存线杀了四次

10:55、11:32、11:36、11:40 各一次 `result 'oom-kill'` —— 是**单元自己的 `MemoryMax=6G`**
（N-125 划的线），不是系统 OOM。期间只有这一个 run 在打网关（网关锁串行）。
每次重启 = 守门约 70 s + 网关 bind 约 60 s，**这两分钟里 agent 的请求全是失败的**。

**对本报告结论的影响：没有。** 结论是「预算不再是瓶颈」，而两臂都是
**自己停下来的**（64 / 87 次，远不到 300；`llm_log` 全 `allow`）——
链路抖动只会让它更早放弃，不会让它「假装做完」。

**对细项读数的影响：有，且分不开。** `overreach.malformed_requests = 15`
（`asof_missing` 7 / `param_malformed` 7 / 未分类 1）里，有多少是 agent 自己写错的请求、
有多少是重启窗口里被打断的半截请求，**现在没有办法区分** ——
要拿这一批去谈「S7 的请求规范性」得先把网关不 OOM 的那一版跑出来。
`gate_failed=['attribution_conservation']` 是算在产物内容上的，不经过这条路径，不受影响。

票据与两个方向见 `ops/tickets_inbox/W1.md` §6。
