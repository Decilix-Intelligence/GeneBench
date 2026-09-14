# 版本说明：四条版本轴，以及「可比」的定义

> **一句话**：GeneBench 的一次结果只有在**四条轴全部相同**时才与另一次可比。
> 版本号不是装饰，它是「这两次运行为什么不可比」的答案 ——
> 根 hash 只告诉你「不一样」，不告诉你「哪不一样、为什么」。

**当前值（2026-09-12）**

| 轴 | 当前值 | 根 hash |
| --- | --- | --- |
| 任务集 `set_version`（私有通道） | **1.0.16** | `d9ebd5412ac4cc7e…` |
| 任务集 `set_version`（**公开通道**，见 §1.1a） | **p1.0.0** | `3e5ab441a991c411…` |
| 参考面 `reference_version` | **r1.0.23** | `dddabe440163b36e…` |
| 协议 `protocol_version` | `geneprotocol_v1@<12 位摘要>`（**逐 run 反算**，见 §1.3） | — |
| 数据通道 `channel` | `private` \| `public`（**两条并列，不覆盖**） | — |

> 三条根都不是手抄的：`$PY ops/mk_release_manifest.py --check` 会现算并与这张表比，
> 对不上就非零退出。**这张表陈了一版的后果**实测过（2026-09-12 红队最终轮）：
> 同一棵公开树里权威文档写 1.0.15 / r1.0.22、发布清单写 1.0.16 / r1.0.23，
> 拿到树的人不知道该信哪一份。

---

## 1. 四条轴各是什么、什么时候变

### 1.1 任务集轴 `set_version`

**回答的问题**：*agent 看到的东西变了吗？*

覆盖面（冻结根，`ops/freeze_v10.py`）：

* 模板目录里 agent 看得见的文件：`INSTRUCTION.strict.md` / `INSTRUCTION.open.md` /
  `template.yaml` / `Dockerfile` / `scorer.yaml` / `tests/test_outputs.py`；
* 渲染器与规则代码：`genetask/{render,packager,schema,pin,bundle,mk_templates}.py`、
  `genetask/params/v1.0-smoke40.yaml`、`genetask/phrasebook.yaml`、**`genetask/arms.yaml`**；
* 目录整棵收进来的两处：`ops/specs/artifact_schema/`（会被逐字节复制成 bundle 里的
  `work/<stage>.json`，**两臂都拿得到**）与 `genetask/arms/`（指令变体臂的固定文本，
  **agent 直接读到它**）；
* 出集清单（哪些题进集）与**题面指纹**。

**什么时候变**：上面任何一项的字节变了，或出集清单变了。
**题面指纹变了是致命项** —— 必须人工签字后才可重冻。
输入变了而题面没变（例如给打包器加个与渲染无关的函数）**只重冻、不推版本号**，
但仍然会被报出来：输入变了意味着下一次改动可能就会改到题面。

**注意一个反直觉的地方**：`canary.control_token` 是每次打包新生成的 nonce，
所以同一份模板两次 build 出来的 `instruction[arm].sha256` **必然不同**——
**不要拿渲染产物的 sha 当基准**。真正稳定的是模板 + 措辞表 + 参数表 + 渲染器代码。

### 1.1a 公开通道的任务集轴 `set_version`（`p1.0.0`）

**回答的问题**：*拿到公开包的人手上是哪一份题？*

按 2026-09-11 用户裁定 ①，**公开通道有自己的任务集轴**，与私有轴并列、各自冻结、
各自发通行证。两条轴的关系是：

* **题面那一半逐字段相同** —— 同一批模板、同一张参数表、同一个题面指纹；
* **不同的只有三样**：集名（`v1.0-smoke-public`）、版本号（`p1.0.0` 而不是 `1.0.16`）、
  记因（`REVISIONS_PUBLIC`）；
* 外加**多一段**：公开树上 `inputs[]` 声明的**夹具真实 sha**（`channel_fixtures`）进公开根 ——
  换一份公开夹具而不重冻，通行证当场对不上。

因此「我这份公开包是哪一版」的答案是 `p1.0.0` / 根 `3e5ab441a991c411…`，
**不是** `1.0.16`。查法：`GENEBENCH_CHANNEL=public $PY ops/freeze_v10.py --check-all`
（见 §3 ①），或直接读 `ops/manifests/v1.0-smoke-public.json` 的 `set_version` 与现算根。

重冻公开轴：`GENEBENCH_CHANNEL=public $PY ops/freeze_v10.py --write-public`。

---

### 1.2 参考面轴 `reference_version`

**回答的问题**：*我们算 gold 的方式变了吗？*

覆盖面：40 个模板的 `solve.py`（答案面）+ 参考模块
（`reference/oracle_io.py`、`reference/gateway_client.py`、各阶段 `*_oracle_common.py`、
`reference/b2_engine.py`、`reference/make_s7_signal.py`、`reference/make_epsilon_panel.py`、
`reference/make_fixtures.py`）。

**为什么要与任务集轴拆开**（裁定 2026-09-05）：`solve.py` 原来住在模板文件清单里，
于是每修一个 oracle 都要推一次**任务集版本** —— 2026-09-05 一天之内推了 1.0.3 / 1.0.4 / 1.0.5
三次，其中**两次题面一个字没动**。版本号一旦这样跳，「这两次运行为什么不可比」就答不清楚了：
看到 v1.0.3 → v1.0.5 的人无从知道被测方看到的东西其实完全一样。

**副作用留档**：拆轴那次任务集内容一个字没变，但 root **值变了**（覆盖的字段集变了）。
所以清单里另记一个 `root_scope` 字段 —— 事后比两个 root 的人能看出「不一样」是因为
覆盖面变了，而不是题面动了。

### 1.3 协议轴 `protocol_version`

**回答的问题**：*这个 run 拿到的是哪一版协议工件？*

取值形如 `geneprotocol_v1@<12 位摘要>`，摘要 = 封闭清单三件
（`validate_artifact.py` / `README.md` / `contract.md`）逐件 `名:sha256` 排序后再哈希
（`ops/results_db.py:144`）。

**它是逐 run 反算的，不是按批声明的**：从 `runs_in/<batch>/<run_id>/inject.json` 的
`files["work/protocol/<件>"]` 取那次注入**真的放进去的字节**。理由是清单会变 ——
实测 m6 那批注进容器的 `validate_artifact.py` 是 `f8b8ad26…`，而今天清单里写的是 `ca26c78f…`。
拿今天的清单去追认历史批次是错的。

**裸臂记 `geneprotocol_v1@none`**，因为它本来就不发协议工件。
`none` 与摘要并排出现**不算混轴**（`mixed_axes` 对这条轴按 `arm_kind` 分组判）——
那是事实：两个臂跑在同一次发布上。**协议臂之间**出现两个摘要才是混轴，那一条拒绝出表。

**半份清单不构成一个版本**：`doc` 臂实测只拿到三件里的两件，它在这条轴上同样记 `none`。
逐件的投放差异是**臂**的定义（`genetask/arms.yaml`），在 `arm` / `arm_kind` 两列上看。

### 1.4 数据通道轴 `channel`

**回答的问题**：*网关背后是哪一套快照？*

取值 `private`（内网数据湖派生）或 `public`（baostock 公开行情）。
**同一道题在两条通道上不是同一道题** —— 两条通道的覆盖面、停牌表示、复权口径、
涨跌停推导都不同（逐条见 `ops/data_cards/README.md` 与 `ops/data_cards/public_channel.md`）。

伴随字段 `channel_build`（公开快照 `build_info.json` 的摘要）是**元信息不是轴**：
轴要能分组，而 build 指纹每重建一次就变一个值。

---

## 2. 「可比」的定义

> **两次运行可比 ⟺ 四条轴的取值全部相同。**

四条轴**缺一即拒**入库（`ops/results_db.py:81`）—— 一条不知道自己是哪一版跑出来的记录，
进了库就再也切不开，只能重跑。出表时**混轴默认拒绝**（要 `--allow-mixed-axes` 显式放行）。

这条纪律是从一次真事故来的：`ops/reports/m6_all` 是 m6（题面 `1.0.7`）与 m6b（`1.0.9`）
合出来的，`table_a` 按 `(config_id, arm)` 分组，两个题面版本的 run **合成了同一行 pass@1**。
表上写了 `MIXED:`，但**没有任何一步拦着不让出这张表**。

### 一个容易读混的地方：主表上「四条版本轴」出现两次

| 出现位置 | 是哪四条 | 用途 |
| --- | --- | --- |
| Table A / Table B 的**列** | `set_version` / `reference_version` / `runner_version` / `image_digest` | **注入面**：这次运行是怎么装配起来的 |
| 表**脚注**与结果库 | `set_version` / `reference_version` / `protocol_version` / `channel` | **可比性**：这两行数能不能放在一起读 |

两组都自称「四条版本轴」（N-404，登记不修）。**判可比性用的是第二组。**

---

## 3. 怎么查当前值

```sh
GB=/data/shared/genebench; PY=$GB/env/bin/python; cd $GB/repo

# ① 两条冻结轴的版本号与根 hash（现算并与已冻结的清单逐段比对；漂了就非零退出）
$PY ops/freeze_v10.py                                   # 任务集轴：一致 / 输入漂移 / 致命漂移
$PY -c "from ops.freeze_v10 import reference_ref; print(reference_ref())"

# ② 直接读已冻结的清单（不现算，快）
$PY -c "import json; m=json.load(open('ops/manifests/v1.0-smoke.json')); \
        print(m['set_version'], m['root'][:16], m['counts'])"
$PY -c "import json; m=json.load(open('ops/manifests/v1.0-smoke.reference.json')); \
        print(m['reference_version'])"

# ③ 今天仓库里那一版协议的轴值（**只用于新结算，不用于追认历史批次**）
$PY -c "from ops.results_db import protocol_version_repo; print(protocol_version_repo())"

# ④ 结果库里真正出现过的四轴组合（混轴在这里看得见）
$PY ops/results_db.py versions

# ⑤ 某一次运行自己记的轴（每个 run 的注入章）
$PY -c "import json,sys; print(json.load(open(sys.argv[1]))['frozen_manifest'])" \
      $GB/runs_in/<批>/<run_id>/inject.json
```

**重冻结命令**（题面未变时只重冻、不推版本号；两条轴**分两次**写）：

```sh
flock /data/shared/genebench/locks/heavy.lock \
    $PY ops/freeze_v10.py --write             # 任务集轴
flock /data/shared/genebench/locks/heavy.lock \
    $PY ops/freeze_v10.py --write-reference   # 参考轴
```

> ⚠ **重冻会让所有已发通行证作废**：`code` 在根字段里 → 根 hash 变 →
> 注入器对所有旧 bundle 当场拒。所以重冻要挑**没有在途 bundle** 的时刻做，
> 并把已导出的 bundle 重新导出。**这件事不能顺手做，它是一次发布动作。**

---

## 4. 历史（摘要）

完整的逐次 why/what 见 [`CHANGELOG.md`](CHANGELOG.md)（由 `ops/mk_release_manifest.py --write-changelog`
从 `ops/freeze_v10.py` 的 `REVISIONS` / `REFERENCE_REVISIONS` 渲染，**不手抄**）。这里只给形状：

| 轴 | 起点 | 当前 | 次数 | 一句话 |
| --- | --- | --- | ---: | --- |
| 任务集（私有通道） | `1.0.1`（2026-09-04） | **`1.0.16`**（2026-09-11） | 17 条记录 | 只有**改到 agent 看得见的东西**才推。其中两条被**改判**为参考面变更（1.0.3 / 1.0.5），记录保留 —— 删掉比留着更容易让人以为没发生过 |
| 参考面 | `r1.0.0`（2026-09-05，拆轴起点） | **`r1.0.23`**（2026-09-11） | 24 条记录 | 每修一个 oracle / 改一次 gold 的算法就推一次。拆轴之前这些改动被记在任务集轴上，那是拆轴要修的问题本身 |
| 任务集（**公开通道**，§1.1a） | `p1.0.0`（2026-09-11，公开轴起点） | **`p1.0.0`**（2026-09-11） | 1 条记录 | 与私有轴**并列不覆盖**：题面逐字相同，换掉的是集名、版本号、记因，外加多一段夹具真值（`channel_fixtures`）进根 |

> **这条历史遗留已经清掉了**（裁定 ⑦ / N-573，2026-09-12）：`ops/freeze_v10.py` 的
> `REVISIONS` 曾经只有 6 条（`1.0.1`…`1.0.6`），拆轴之后新增的**任务集**记录被写进了
> `REFERENCE_REVISIONS` 元组。现在 `REVISIONS` 是活代码、`1.0.6` 至今逐条补录，
> 三个元组各归各轴（任务集 17 条 / 参考面 24 条 /
> 公开任务集 1 条），`CHANGELOG.md` 与 `ops/manifests/*.json` 的变更记录都由它重出。

**两次已经排队、等用户签字的 bump**（本阶段不许自行推进）：

| 待推 | 为什么 | 代价 | 票据 |
| --- | --- | --- | --- |
| 参考轴（下一号） | 去掉 `reference/s8_oracle_common.py::fill_metrics` 的 `sign`，与规格 §3 对齐 | 要**重出 S8 四题的 gold** | N-383 |
| 任务集（下一号） | 收紧 S8 `events` 的 `required` | 要**另一轮红队**：收紧会让参考样例与既有 121 份真产物集体变畸形，那是判据变更 | N-384 |

---

## 5. 版本号之外：还有两样东西决定结果可不可信

版本轴回答「可不可比」。下面两样回答「这个数能不能引」：

1. **标定产物** `snapshots/<通道>/calibration.json` —— τ 与 ε 的值。
   **换 gold 引擎就要重标 ε**；ε 与 gold 出自同一次标定。
   当前 `ready_for_scoring` 是 `false`、`epsilon.usable` 是 `false`
   （只有 `by_frequency.daily` 这一档 `usable=true`）—— 逐档状态见
   `ops/specs/metrics_as_implemented_v1.md` 的 S4 / S7 两节。
2. **预算档** —— `runner/registry.py` 的 `RUN_BUDGET` 与 `BUDGET_TIERS`。
   预算档没给够的时候「能力读数」会变成「预算读数」：`ops/reports/v1demo/` 的 **8/8**
   撞的是 token 闸（调用数只用到 18–22 / 100），那张表上的 `SR=0.25` 读的不是能力。
   **N-388 已裁定并落地**：默认档现在是 `max_calls = 100` / `max_tokens = 6_000_000`，
   并按阶段分档（S4 = 9 M、S7 = 300 次 / 18 M，见 `BUDGET_TIERS`）。
   真跑**不要**再显式给 `--max-tokens` —— 显式给的值会赢过阶段档，把 S4 / S7 压回默认档。
