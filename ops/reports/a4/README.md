# a4：臂机制数据驱动的真跑（卡 4.1 步骤 6）

**在问什么**：`genetask/arms.yaml` 落地之后，一个**只写在配置里**的臂能不能真的跑起来 ——
出集、推送、注入、真调模型、结算，全程不改代码。

**跑的是什么**

| 项 | 值 |
| --- | --- |
| 题 | `s2-cor-01`（S2 / COR，默认预算档 100 次 / 600,000 tokens） |
| 配置 | `cfg-codex-deepseek`（Codex CLI，deepseek-chat，经边车） |
| 臂 | `strict`（protocol，内置）、`doc`（protocol，**非默认**）、`hint`（instruction_variant，**非默认**） |
| bundle | 四臂出集（`build_task(..., arms=("strict","open","doc","hint"))`），`set_version` 1.0.12 / `reference_version` r1.0.19 |
| 答案面 | `$GB/reference/a4_arms/tasks/v1.0-smoke/s2-cor-01`（**不是**已发布的 40 题那份 —— 别的代理正在用它） |
| 结算 | `ops/score_runs.py --batch a4 --remote /data/genebench_runner/a4/runs/runs --ref-tasks $GB/reference/a4_arms/tasks/v1.0-smoke` |

## 结果

| run | 结局 | validity | 模型调用 | 说明 |
| --- | --- | --- | --- | --- |
| `strict.r01` | budget_exhausted | — | 22 | token 档 600k 在第 22 次调用撞上（每次 prompt ~45k） |
| `doc.r01` | budget_exhausted | — | 19 | 同上 |
| `hint.r01` | budget_exhausted | — | 24 | 同上 |
| `strict.r02` | ok | **valid** | 37 | l3=align |
| `doc.r02` | ok | **valid** | 41 | l3=align |
| `hint.r02` | timeout | — | 67 | 1500 s 墙钟到点，没落 artifact |

r01 三臂**同时**撞的是 S2 的默认 token 档（600,000）——那是**我们这一侧的闸**，
不是 agent 自身的失败，所以按纪律做了一次重试（r02，只抬 token 上限到 3M，
调用次数仍按 stage 档）。卡 4.3 的 `--max-tokens` help 里就写着这件事：
「Codex 裸臂在第 22 次调用就撞了 600k（每次 45k prompt）」。

## 这次跑证明了什么

1. **一个只写在配置里的臂能跑通全程。** `doc` 臂从来没有出现在任何 `.py` 里：
   它的存在是 `genetask/arms.yaml` 的 12 行 + 一份 MANIFEST。它出了集、进了 bundle、
   被注入器按自己的清单投放了工件、真调了 41 次模型、结算出 `validity=valid`。
2. **strict 臂没有被泛化改坏。** 同一份四臂 bundle 里，strict 臂拿到的仍是
   3 件封闭清单工件 + 4 份逐题规则 JSON，注入前后 sha 逐条对上（`ops/test_arms_registry.py`），
   `validity=valid`、`l3=align`。
3. **投放集合的差异是真的。** `doc` 臂的 `work/protocol/` 里只有 `README.md` 与 `contract.md`；
   **没有 `validate_artifact.py`，也没有逐题规则 JSON** —— 这正是「把规则写给 agent 看」
   与「给它一个能跑的验证器」之间的那条线。

## 这次跑**没有**回答的

* **一题一次，不比分数。** SR / pass@1 那几列在 n=1 上没有意义，别引用。
  这次要的是「机制通不通」，不是「哪个臂更强」。
* **`hint` 臂没有可评分的产出。** 两次都没落 artifact（r01 撞档、r02 墙钟到点）。
  一个**值得记下来的观察**：`hint` 臂 r02 用了 67 次调用，而 strict 37 次、doc 41 次 ——
  追加的那句「先读结构文件再动手」看起来把 agent 带进了更长的路径。
  这是 n=1 的现象，不是结论；但它恰好是公平性协议 §6.6.3 要求
  「instruction_variant 臂在主表上单列」的那类东西：它与工件层的干预不同轴。
* **重试额度已经用掉。** 同一目标 1 次 + 1 次重试是纪律上限，所以 `hint` 臂就停在这里。
  下一个人要补这条，先把 `--timeout` 抬到 2400 s 再跑（r02 的失败是墙钟不是预算）。

## 已知问题（票据里各有一条）

* **超时的 run 会漏一个容器。** `hint.r02` 被判 timeout 之后，
  `gb-s2-cor-01-hint-cfg-codex-deepseek-r02-task-run-…` 又跑了 25 分钟才被手工停掉。
  拆除路径没有覆盖 `docker compose run` 起的那个一次性容器。
* **`ops/export_bundle.py::export_one` 没有 `arms` 参数**，所以多臂 bundle 目前得另写脚本
  （本次用 `$GB/scratch/4.1/build_a4.py`，它逐步复刻 `export_one` 的每一道门）。
