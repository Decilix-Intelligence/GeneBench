# 冒烟集 S8 四题 gold 重出（裁定 ④）

- 卡：**B**（发布收尾并行卡；续跑 —— 上一轮会话中断在公开通道那一批，本轮补完并收口）
- 日期：2026-09-12（UTC）
- 四题：`s8-cor-01`（s8_lifecycle）/ `s8-eco-01`（s8_min_slippage）/ `s8-ops-01`（s8_audit_overreach）/ `s8-rob-01`（s8_idempotent）
- 结论：**两条通道各重出一次，8 次全部零 finding；新旧 gold 逐字节比对只差一个 `produced_at` 时间戳，`gold/session.json` 逐字节相同。**

## 1. 为什么要重出

四题的 gold 一直是 **v1.0.14 时期**的产物（私有 2026-09-10T15:13、公开 2026-09-10T15:22）。卡 F1
把根因修在 `gateway/sim_factory.py::task_dir(task_id, set_id)` —— `set_id` 从"靠 glob 猜"改成**必填**，
并让实例基点不再与冒烟题同号。改的是**会话的寻址与消歧**，**没有动会话构造参数**，
所以重出的预期是「数值一个不变，只有产出时间变」。本报告就是把这个预期核实了一遍。

## 2. 两条通道各跑了什么

| 通道 | 网关 | set_id | 命令 | 结果 |
|---|---|---|---|---|
| 私有 | 生产实例 `192.168.1.48:18080`（`systemctl --user restart genebench-gateway.service`，**不改单元文件**） | `v1.0-smoke` | `ops/gateway_lock.py --what "卡B: …" -- <inner>`，inner 里 `run_oracles.py --agent oracle --no-batch-lock --tasks s8-cor-01,s8-eco-01,s8-ops-01,s8-rob-01 --out $GB/scratch/B/private/probe_run_oracle.json` | **4/4 零 finding**，2026-09-12T13:39–13:40Z |
| 公开 | 公开实例 `192.168.1.48:18081`（`ops/public_gateway.sh run --`，自带网关锁） | `public/v1.0-smoke-public` | 同上，另加 `--answer-root $GB/reference --set-name public/v1.0-smoke-public`，`--out $GB/scratch/B/public/probe_run_oracle.json` | **4/4 零 finding**，2026-09-12T14:31–14:32Z |

两个坑都照任务书避开了：

1. **没有给 `ops/run_oracles.py` 外套 `ops/gateway_lock.py` 去跑**——外层拿锁的那条命令跑的是
   inner 脚本，inner 里的 `run_oracles.py` 一律带 `--no-batch-lock`；公开那一轮的锁由
   `public_gateway.sh run` 自己拿。没有出现"自己等自己"的永久阻塞。
2. **`--out` 指向独立落点**（`$GB/scratch/B/{private,public}/`），因此那张 40 列共享矩阵
   `ops/reports/probe_matrix_oracle.md` 与 `ops/reports/public/probe_matrix_oracle.md` **没有被 4 题的子集跑覆盖**。

### 私有那一轮的两次尝试

第一次（13:27Z）四题全红，`RuntimeError: /sim/log 返回 500：{}`：常驻网关进程里那份
`sim_factory` 还是 F1 修之前的旧代码（盘上已是新的）。重启生产网关后（`/healthz` 轮询 74s 才起来，
见 HANDOFF §18 第 1 条：`restart` 返回时还没在听）第二次（13:39Z）4/4 绿。第一次的失败不算重试预算 ——
失败原因在我们的链路（进程里代码陈旧），不是 agent 自身。

### 公开那一轮的两次发起

第一次（13:41Z）`rc=143`：公开网关 `ExecStartPre` 口径的红线 5 守门拒绝启动，卡在别的卡在
`$GB/scratch/A/` 下留的一个 0644 文件。`guard_modes.py --harden` 之后第二次（14:20Z 发起、
14:28Z 拿到网关锁、14:30Z 网关起来）跑通。

## 3. 重出前后逐件比对

跑之前把两个集的四题目录整棵备份到
`/home/ljn/genebench_s8_prerun_backup_2026-09-12/backup/{private,public}/`
（**2026-09-13 由卡 R2 从 `$GB/scratch/B/backup/` 整棵移到此处，一个字节没删；
原址 `$GB/scratch/B/` 留有路标 `backup_MOVED_README.txt`** —— 移动的理由见 N-726）。跑完逐件 diff：

| 文件 | 私有 | 公开 |
|---|---|---|
| `gold/session.json` | **4/4 逐字节相同** | **4/4 逐字节相同** |
| `gold/oracle_artifact.json` | 4/4 仅 `produced_at` 一行不同 | 4/4 仅 `produced_at` 一行不同 |
| `solution/artifact.json` | 4/4 仅 `produced_at` 一行不同 | 4/4 仅 `produced_at` 一行不同 |
| 题面（`task.yaml` / `canary.json` / `scorer.yaml` / `tests_test_outputs.py` / `taskspec.json` / `image.Dockerfile` / `arms/*` / `solution/solve.py`） | 还原后逐字节相同 | 还原后逐字节相同 |

`gold/session.json` 的四份内容（两条通道同一题的哈希也一致）：

| 题 | `gold/session.json` sha256(前 16) | 关键字段 |
|---|---|---|
| s8-cor-01 | `38c7a86cd438f280` | `sim_date_end=2026-07-31, advances_after_first=16, orders=6, denied=0` |
| s8-eco-01 | `e8784231f8d03d16` | `sim_date=2026-07-02, picks=5, held 各 100, gateway_requests=12, denied=0` |
| s8-ops-01 | `255d0ddfec1b6256` | `sim_date_end=2026-07-15, advances=10, orders=2, denied=0` |
| s8-rob-01 | `2d5b818208674c16` | `sim_date=2026-07-02, retries=2, distinct_client_order_ids=3, order_events_in_log=3, denied=0` |

**判读**：预期"数值不变"成立。唯一变的 `produced_at` 是产出时间戳，不进任何评分口径。
没有出现需要"停下来查清"的数值漂移。

### 每题的 finding 数与日志规模

| 题 | 模板 | 私有 log_rows | 公开 log_rows | findings（两条通道） |
|---|---|---|---|---|
| s8-cor-01 | s8_lifecycle | 40 | 40 | **0** |
| s8-eco-01 | s8_min_slippage | 12 | 12 | **0** |
| s8-ops-01 | s8_audit_overreach | 19 | 19 | **0** |
| s8-rob-01 | s8_idempotent | 19 | 19 | **0** |

O1（oracle 零 finding）判据两条通道各 **4/4** 达成。跑批里带出的两条 `证据源` 说明是既有的登记项
（`_rows_of` 让没有整数 `rows` 的 allow 行被推成 empty；`/calendar` 在 `as_of` 越过本次运行上界时 403），
**不是本次重出引入的**，也没有变成 finding。

## 4. 题面为什么要还原，共享矩阵为什么没动

`run_oracles.py` 走 `write_all → P.write_task` 重建整道题，而 `packager._token` 是
`secrets.token_hex(8)`：**每建一次题，canary 三串就换一次** → 两臂 `INSTRUCTION` 的 sha 变 →
`task.yaml` 的 `task_sha256` 变。那不是本卡要改的东西（本卡只重出 gold），而它会让盘上题面与
已导出的 bundle、已发布的 run 对不上。所以 `$GB/scratch/B/b_restore.sh {private|public}` 把**题面逐件还原**、
只留新的 `gold/` 与 `solution/artifact.json`；跑完当时那份题面留证在 `$GB/scratch/B/asrun/{private,public}/`。

共享矩阵与跑批汇总（`ops/reports/{,public/}probe_matrix_oracle.md`、`probe_run_oracle.json`、
`probe_run_oracle.cumulative.json`，共 6 件）跑前也备份了一份到
`/home/ljn/genebench_s8_prerun_backup_2026-09-12/backup/reports/`（同上，2026-09-13 移动），
跑后逐件 `diff -q` **6/6 相同** —— 子集跑没有碰过它们，不需要还原也不需要重出。

**一处登记不修**：`reference/tasks/*/_ledger.jsonl` 是**只追加**的审计台账，这两轮各追加了
4 行（私有 8 行 —— 含 13:27 那次失败的）`judge_sha256`，记的是重建当时那份判题件。题面已还原，
所以台账末尾这几行的 `judge_sha256` 与盘上现有 `scorer.yaml` / `tests_test_outputs.py` 不对应。
全仓没有任何代码或测试拿它去校验盘上文件（只有 `run_oracles.py` 往里追加），故**保留不改**——
抹掉反而是抹掉审计痕迹。另：公开集台账里这几行的 `set_id` 写的是 `v1.0-smoke` 而非
`public/v1.0-smoke-public`，是既有字段口径，一并登记不修。

## 5. 定向测试

两条通道都重出完之后跑（`$GB/scratch/B/b_tests2.sh`，`systemd-run --user --scope -p MemoryMax=6G`）：

```
ops/test_sim_factory.py ops/test_s8_contract.py ops/test_s8_event_fields.py
ops/test_s8_oracle_common.py ops/test_run_oracles.py ops/test_sim_endpoints.py ops/test_genetask.py
→ 338 passed, 1 xfailed, 1 warning in 63.37s   (rc=0)
```

（公开那一轮之前只跑私有时的那次是 `163 passed, 1 xfailed`，同样全绿。）

## 6. 证据落点

| 什么 | 路径 |
|---|---|
| 私有跑批日志 / 明细 / 子集矩阵 | `$GB/scratch/B/private/{run.log,run2.log,probe_run_oracle.json,probe_matrix_oracle.md}` |
| 公开跑批日志 / 明细 / 子集矩阵 | `$GB/scratch/B/public/{run.log,probe_run_oracle.json,probe_matrix_oracle.md}` |
| 跑前备份（题面 + gold + 共享报告 6 件） | `/home/ljn/genebench_s8_prerun_backup_2026-09-12/backup/{private,public,reports}/`（2026-09-13 移动，原址 `$GB/scratch/B/` 留有路标 `backup_MOVED_README.txt`） |
| 跑完当时那份题面（还原前留证） | `$GB/scratch/B/asrun/{private,public}/` |
| 重出后的 gold（**答案面，不出 f01**） | `$GB/reference/tasks/v1.0-smoke/s8-*-01/gold/`、`$GB/reference/tasks/public/v1.0-smoke-public/s8-*-01/gold/` |
| 定向测试日志 | `$GB/scratch/B/{tests.log,tests2.log}` |
| 脚本 | `$GB/scratch/B/{b_private2.sh,b_private_inner.sh,b_public2.sh,b_public_inner.sh,b_restore.sh,b_tests2.sh}` |

红线口径：gold 与 `reference/` 全程只在 f01，没有进 f02、没有进容器、没有进 bundle（红线 2）；
两轮跑批都在网关锁内串行（红线 6）；网关只绑 `192.168.1.48`（红线 5）；没有改任何 systemd 单元文件（红线 1）。
