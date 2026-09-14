# 形态① 单机双容器：走到哪一步，卡在哪一件（卡 X1）

> 2026-09-10，f02（`192.168.1.219`）。落点 `/data/genebench_runner/single_node/`。
> 本节只写**实测**：每一条都有命令与输出；读不出结论的地方写「没走到」，不写「应该可以」。

## 0. 一句话

**手册 §1.3 那个「唯一不试就不知道」的点已经解掉了** —— 用户放行 `172.31.240.0/22 → 18080`
之后，容器打得到本机宿主的 LAN 网关（**200**）。出集与推送两步在单机落点上真跑并全绿。
**新卡住的是另一件、而且更深**：数据面网关的 import 链穿到了**答案面**
（`gateway/sim_engine.py` → `reference.artifact_schema`），
而形态① 要求网关与容器同机 —— 于是「起网关」这一步与**红线 B2**（`reference/` 不进执行面）直接撞车。
这不是配置问题，**要一次裁定**（见 §4）。

## 1. 已验：容器 → 本机宿主 LAN 网关（手册 §1.3 那张表要改）

放行前（卡 6.4，2026-09-08）三种宿主自身地址**全部超时**。放行后（本卡，2026-09-10）：

| 从哪儿 | 到哪儿 | 结果 |
| --- | --- | --- |
| 宿主 | `192.168.1.219:18080` | **200** |
| 容器（`172.31.242.0/24`） | `192.168.1.219:18080` ← **本机宿主 LAN** | **200** |
| 容器 | `172.17.0.1:18080`（docker0） | 连接被拒 —— 监听只绑了 LAN 地址，**不是防火墙** |
| 容器（对照） | `192.168.1.48:18080`（f01） | **200** |

复现：`$GB/scratch/X1/x1_probe3.sh`（scp 到 f02 上 `sh` 跑）。
探针用 `python3 -m http.server 18080 --bind 192.168.1.219` 当靶子、`gb-base:bookworm-r1` 当容器
（**`gb-base` 里没有 `curl`**，用 `urllib` 打；第一版用 curl 全 000，那不是网络结论）。

**踩过一次**：建探针网时 `--subnet 172.31.240.0/24` 报 `Pool overlaps` ——
f02 上有一张**残留**的 compose 网 `gb-s2-cor-01-hint-cfg-codex-deepseek-r02_gb_task` 占着这一段。
那一轮四个目标全 000（**包括对照**），差点被读成「放行没生效」。
判读规矩：**对照那一行不是 200，整张表作废**。

## 2. 已验：出集 → 推送（在单机落点上真跑）

```sh
STG=$GB/staging/single_node_s1-cor-01
$PY ops/export_bundle.py s1-cor-01 --staging "$STG" \
    --digest sha256:961e3878b28fc13ef2600254c4c4cbaceb7c337e2944fc173eaba1335752561a --image gb-cx-u
ops/push_bundle_to_f02.sh "$STG/tasks/s1-cor-01" \
    /data/genebench_runner/single_node/runner/tasks "$STG/s1-cor-01.manifest.json"
```

两步 `rc=0`。推送守门四条全过，其中**卡 X1 点名要看的那条**：
执行面的 `genebench-answer-plane-scan.timer` 是 `enabled + active`（`systemctl --user` 现查），
所以推送**没有**被拒 —— 「timer 不存在要不要装」这件事**在 f02 上不成立**，不需要用户裁定。
落地扫描 `[绿] /data/genebench_runner/single_node/runner/tasks/s1-cor-01 无答案面命中`。

## 3. 已验：数据面「引用一份现成快照」（手册 §1.4 缺的第三条路）

在 f01 上把这条配方走通了（形态① 的落点卡在 §4，所以配方本身单独验）：

```sh
ROOT=$GB/scratch/X1/refroot                       # 一个新的 GENEBENCH_ROOT
mkdir -p $ROOT/snapshots/public_v1 $ROOT/logs $ROOT/results && chmod -R go-rwx $ROOT
ln -s $GB/snapshots/public_v1/tables $ROOT/snapshots/public_v1/tables   # ← 引用，不复制
cd $GB/repo && GENEBENCH_ROOT=$ROOT GENEBENCH_CHANNEL=public \
  GENEBENCH_GATEWAY_PORT=18082 GENEBENCH_GATEWAY_BACKEND=snapshot \
  PYTHONDONTWRITEBYTECODE=1 $PY -m gateway.run --workers 1
```

实测：**50 秒**起来，`/healthz` = 200 且自报
`tables_dir=/data/shared/genebench/scratch/X1/refroot/snapshots/public_v1/tables`、
`exposed_datasets` 五个（说明它真的读了那份 `manifest.json`），
`/calendar?start_date=20260701&end_date=20260710&as_of=20260731` 取回 **10 行真数据**。
**没有重建、没有解发布包**，省掉的是 §1.4(b) 那条约 4 小时 15 分的链。

要点三条（都是踩出来的）：
* 目录布局必须照 `$GB` 的约定：`<root>/snapshots/<版本>/tables`。版本目录名按通道取
  （`private` → `v1`、`public` → `public_v1`，`genebench_config.snapshot_tables_dir()`）。
* `tables` 那一层用**软链**就行，网关跟着走；`<root>` 及其下每个目录仍要 `0700`。
* 端口用 `GENEBENCH_GATEWAY_PORT` 显式错开，别和生产网关抢 18080。

## 4. 卡住的那一件：网关的 import 链穿到答案面

在 f02 上把网关起起来时（`GENEBENCH_ROOT=<单机根>`、`PYTHONPATH=<运行库>:<repo>`）：

```
File ".../gb/repo/gateway/app.py", line 26, in <module>
    from .routers import market, reference, sim
File ".../gb/repo/gateway/routers/sim.py", line 28, in <module>
    from ..sim_engine import SimEngine, SimError
File ".../gb/repo/gateway/sim_engine.py", line 20, in <module>
    from reference.artifact_schema import (LEGAL_TRANSITIONS, TRADABILITY_STATES, UNTRADABLE_STATES)
ModuleNotFoundError: No module named 'reference'
```

* 这是**唯一**一处（`grep -rn "from reference" gateway/ snapshots/` 只有这一行）。
* 被引的是三个常量（合法状态迁移 / 可交易状态 / 不可交易状态），**不是任何题的答案**；
  `runner/f02/answer_plane_guard.scan` 单独扫 `reference/artifact_schema.py` **命中 0**。
* 但 `reference/artifact_schema.py` 自己的模块 docstring 写着
  「本模块是**评分侧**的（红线 5：不进执行面）」，而**红线 B2 的措辞是整棵 `reference/` 不进 f02**。
* 形态② 看不见这个问题：网关跑在 f01，`reference/` 本来就在同一台机上。
  **形态① 一定会撞上**，因为它要求网关与容器同机。

于是手册 §1.1 那句「**两种形态跑的是同一套代码**，差别只在三个常量与一条防火墙规则」
**今天不成立**：形态① 还要求 `reference.artifact_schema` 出现在执行面那台机器上。

### 要裁的两个方向

* **① 把这三个常量搬出 `reference/`**（例如落到 `genetask/` 或一个新的协议侧模块），
  `reference/artifact_schema.py` 与 `gateway/sim_engine.py` 都从新家 import。
  语义对：它们是**协议 schema**，不是参考解。代价：`reference/` 模块在**参考轴冻结根**里
  → 要推 `REFERENCE_VERSION`（r1.0.21；N-383 本来就要推一版重出 S8 gold，**并成一次**）。
* **② 裁定「`reference/artifact_schema.py` 允许出现在执行面」**，把 B2 的措辞从
  「整棵 `reference/`」改成逐文件（并让 `push_bundle_to_f02.sh` / `answer_plane_guard`
  显式豁免它）。代价：B2 从一条**看目录名就能判**的红线，变成一条要逐文件判的红线 ——
  而 B2 之所以有效正是因为它不需要判断。

**倾向 ①**。理由：把协议 schema 从答案面搬出来，两种形态就真的是同一套代码了；
而 ② 是为了迁就一个 import 去松掉一条目录级红线，**下一次是谁再加一个 import 没人拦得住**。

## 5. 另一件事实：f02 今天装不出数据面 Python 环境（不挡设计，挡今天）

f02 没有 `python3.12-venv`（`ensurepip` 缺失）且无 sudo。绕过去了（从 `gb-base:bookworm-r1`
里 `docker cp` 出 pip），**真正的墙是出网速度**：

| 试的 | 结果 |
| --- | --- |
| `pip install pandas==2.2.3`（12.7 MB） | **900 s 没下完**，`rc=124` |
| `pip install duckdb==1.4.3`（20.5 MB） | 下完了，**约 26 分钟**（实测 ~13 KB/s，用 `du -sb /tmp/pip-unpack-*` 前后差量量的） |
| f01 侧同一批包 | 一样慢（400 s 超时） |

绕法（已用）：`docker create gb-rd-u:r1` + `docker cp .../site-packages` → `$SN/imgpkgs`（1.7 GB），
`PYTHONPATH` 指过去。**代价是版本漂移**，写清楚不藏：

| 包 | f01 数据面 | f02 单机（从镜像取） |
| --- | --- | --- |
| pandas | 2.2.3 | **2.3.3** |
| numpy | 1.26.4 | **2.5.2** |
| pyarrow | 20.0.0 | **25.0.1** |
| fastapi | 0.141.1 | 0.141.1（同） |
| duckdb | 1.4.3 | 1.4.3（同，单独装的） |

**这套漂移的环境没有产出过任何数**（网关根本没起来），所以不存在「用它算出来的数进了表」。
真要在 f02 上立一个数据面，得先解决出网速度或做一份离线 wheelhouse —— 登记，不在本卡修。

## 6. 现场留下了什么 / 收掉了什么

* **收掉**：`/data/genebench_runner/single_node/gb/snapshots/v1/tables`（1.5 GB 私有快照表）。
  网关既然起不来，这份数据面素材没有留在执行面的理由（rsync 只要 14 秒，要用再推）。
* **留着**：`single_node/{env,imgpkgs,pipsrc,gb/repo,runner/tasks/s1-cor-01,probe}` ——
  裁定下来之后接着走的人不必重来。`gb/repo` 里的 `genebench_config.py`
  已按手册 §1.3 把 `GATEWAY_HOST` 改成 `192.168.1.219`（**只改 f02 这份副本**，f01 的没动）。
* **答案面**：推之前两次 `answer_plane_guard.scan` 都是 **0 命中**（代码 staging 36 个文件 / 表目录 23 个文件）。

## 7. 没走到的（不猜）

真跑一道题双臂、结算、出表 —— **一步都没走**，因为网关没起来。
这三步与形态② 逐字相同（同一个 `run_f02_a1.py` / `score_runs.py` / `mk_tables.py`），
但「与形态② 相同」是推理不是实测，**本报告不把它记成已验**。
