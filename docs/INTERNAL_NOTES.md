# 内部工程说明

**读者**：在这台机器上**施工**的人（改代码、建数据面、跑批、收口）。
不是外部运行者（那读 [`OPERATOR_MANUAL.md`](OPERATOR_MANUAL.md)），
不是被测方（那读 [`../integrations/P2_CONTRACT.md`](../integrations/P2_CONTRACT.md)）。

这份文件是**原 `README.md` 里面向施工方那半边**搬过来的（卡 6.1，2026-09-08）。
README 改成了外部读者的入口，这些内容仍然成立，只是不该占着入口的位置。

**与 [`../ops/HANDOFF.md`](../ops/HANDOFF.md) 的关系**：HANDOFF 按施工阶段组织，
记「谁做了什么、为什么这么定、踩过哪些坑」，是**逐阶段交接**；
本文只留**任何一天动手之前都要知道**的几件事，篇幅刻意短。
两者冲突时以 HANDOFF 为准（它随卡更新，本文不）。

---

## 1. 配置常量：唯一允许写绝对路径的地方

```python
import genebench_config as cfg
cfg.REPO, cfg.SNAPSHOTS, cfg.FREEZE_DATE, cfg.GATEWAY_HOST
```

仓库根 = `$GENEBENCH_ROOT/repo`。仓库**之外**的同级目录（不入 git，大产物只落这里、不落 `/home`）：

```
$GENEBENCH_ROOT/env         隔离运行环境（Python 3.10）        cfg.ENV
$GENEBENCH_ROOT/logs        施工 / 运行日志                    cfg.LOGS
$GENEBENCH_ROOT/snapshots   冻结数据快照（parquet / duckdb）   cfg.SNAPSHOTS
$GENEBENCH_ROOT/results     跑分结果                           cfg.RESULTS
$GENEBENCH_ROOT/wheels      离线 wheel 缓存                    cfg.WHEELS
$GENEBENCH_ROOT/pip.conf    pip 镜像配置（见 §3）              cfg.PIP_CONF
```

**每一条都有对应的 `cfg` 常量，一条都不许在代码里现拼。**
`logs/` 就吃过这个亏：目录先建了、日志也写了，却没有常量 ——
搬家时那「唯一一行」带不走它，是卡 0.1 的修复补上的。

---

## 2. 建目录的唯一正确姿势

**本机 umask 是 002。** 裸 `mkdir` / `os.makedirs` 会**静默**产出 0775 的组/世界可读目录 ——
卡 0.1 的 `env/`、`logs/`、`ops/acceptance/` 就是这么歪的。
`os.makedirs(p, mode=0o700)` 也**不够**：Python 3.7 起 `mode` 只作用于最后一级，
中间层照样是 `0o777 & ~umask`。

```python
import genebench_config as cfg

cfg.harden_umask()                      # 每个进程入口调一次（umask -> 0077）
cfg.create_dir(cfg.RESULTS / "run_42")  # 每一级都保证 0700
```

为什么较真：`$GENEBENCH_ROOT` 的父目录是 **1777 的公共目录**，任何本机用户都能进；
只有 0700 才挡得住旁人 `cat` 走标准答案。这是「答案面不上执行面」的**物理保障**那一半。

`ops/test_env.py` 会**递归**审计 `$GENEBENCH_ROOT` 下每个目录，
并对 `reference/` 与 `scorer/` 的目录与文件另加硬断言。
豁免的只有 `env/` 与 `.git/` 两个第三方子树的**内部**（它们的根仍被断言 0700 ——
根不可穿越 = 里面什么权限都进不去），理由写在该测试的 `MODE_AUDIT_EXEMPT_SUBTREES` 注释里。

**踩过的两个常见现场**：

* 用 `scp` 传上来的文件是 0644 → `$GB` 下**一个** 0644 文件就能让网关起不来
  （服务的 `ExecStartPre` 就是权限守门）。传完立刻 `chmod -R go-rwx <目录>`，
  远端命令一律 `umask 077` 开头。
* 提交之后 `.git/index` 变回 0664。收回来：

```sh
$PY -c "from ops import report_io as R; R.secure_tree('/data/shared/genebench/repo')"
$PY ops/guard_modes.py --harden        # 应打印「敏感根权限合规」
```

---

## 3. pip 镜像

镜像配置落在 **`$GENEBENCH_ROOT/pip.conf`**（清华源）。
刻意**没有**写 `~/.config/pip/pip.conf` —— 那是用户既有配置，不许碰。所以用法是显式指定：

```sh
PIP_CONFIG_FILE=$GENEBENCH_ROOT/pip.conf pip install <pkg>
```

嫌长就在自己的 shell 里 `export PIP_CONFIG_FILE=$GENEBENCH_ROOT/pip.conf`，
**别写进任何共享配置**。

装包一律装进 `$GENEBENCH_ROOT/env`；`qlib_env` 那个基础解释器**只读使用，禁止 pip install 进去**。

---

## 4. 落点与搬家

当前落点 `/data/shared/genebench` 是**临时**的：`/data` 是 `root:root 0755`，
普通用户 `mkdir /data/genebench` 会被拒。规范落点需要一次人工特权窗口
（票据在 [`../ops/tickets.md`](../ops/tickets.md)）。

搬家的改动面只有两处：`genebench_config.py` 里 `_DEFAULT_ROOT` 那一行，加一次 `mv`。
或者干脆不改代码：

```sh
GENEBENCH_ROOT=/data/genebench python -m gateway.app
```

这也正是**禁止把绝对路径散落到代码里**的理由。

---

## 5. 数据湖已知陷阱（私有通道）

写查询之前先看一眼，省得重踩：

* gold 全表扫会 **"Too many open files"**。先 `ulimit -n 8192`，
  或直接 `read_parquet('<GOLD>/<ds>/<partition>/*.parquet')` 读定向分区。
* **停牌票在 `daily` 里是缺行**，不是显式标记。必须 join `suspend_d`（S=停牌 / R=复牌）+ `trade_cal`。
* **`stk_limit.pre_close` 全为 NULL**。判触板只能用 `daily.close/high/low` 比 `up_limit`/`down_limit`。
* `trade_cal` **只有 SSE 一个交易所**，含未来日历到 20261231。
* `index_weight` 只有三个宽基，**月末快照**，冻结在 20260731。
* `stock_basic` 是**多快照表**（`snapshot_date=YYYY-MM-DD`），只有 18 个快照；
  更早的状态只能靠 `list_date` / `delist_date` 回溯。
* qlib instruments 代码是 `SH600000` 前缀式，**同一 code 多行 = 多个区间段**；湖里是 `600000.SH`。
* `fina_indicator` **只有 ann_date，无 f_ann_date**（做不了严格 PIT），v1 不进网关。
* `stk_factor_pro` 有 bfq / hfq / qfq 三口径，**v1 统一走 `adj_factor`**，三价口径不进网关。
* 数据湖一律**只读**：`connect(str(cfg.CATALOG), read_only=True)`。
  湖上有别的常驻进程；跑批时看到 `test_lake_baseline` 一类的红，
  多半是外部进程持着湖的写锁，不是回归。

公开通道的对应陷阱另有一份，逐条在 [`../ops/data_cards/public_channel.md`](../ops/data_cards/public_channel.md)。

---

## 6. 内存纪律

这台机器只有 30 GB 内存 + 8 GB swap，宿主上还有别人的进程。已经被 OOM 收走过整机两小时。

* **重活**（gold 重算 / IC-ε / oracle 矩阵 / materiality screen / 对账全量 / 打包）
  必须拿 `$GENEBENCH_ROOT/locks/heavy.lock`，**全机同一时刻只跑一个**。
* 重活一律封顶：`systemd-run --user --scope -p MemoryHigh=16G -p MemoryMax=20G <cmd>`
  （不可用就 `ulimit -v`），日志里记峰值 rss；起之前 `free -g` 看 available，不够就等。
* **全量 pytest** 自己串行（另一把锁），用 `-p MemoryMax=6G` 封顶；跑之前 `ulimit -n 8192`。
* 面板类作业的 `--spill-root` **默认开着，别关**：792 个面板同时压内存时常驻 22 GiB。
* 不要在这台机器上留常驻轮询循环。

锁有哪几把、各管什么，在 [`OPERATOR_MANUAL.md`](OPERATOR_MANUAL.md) §8.2。

---

## 7. 进度纪律

每完成一张任务卡：跑该卡验收测试 → 结果追加到 [`../ops/progress.md`](../ops/progress.md)
→ **验收未过不进下一卡**。每条记录含：卡号、时间（UTC）、做了什么、验收命令、验收输出摘要、PASS/FAIL。

需要特权（sudo / 改系统服务 / 改防火墙）的事项**不执行**，一律登记：
逐卡写到 `ops/tickets_inbox/<卡号>.md`，收口时合进 [`../ops/tickets.md`](../ops/tickets.md)
（格式与规矩见 [`../ops/tickets_inbox/README.md`](../ops/tickets_inbox/README.md)）。

改了发布件之后有两条**顺序不能反**的收尾命令（`CHANGELOG.md` 自己也是发布件，
它的 sha 在清单里）：

```sh
$PY ops/mk_release_manifest.py --write-changelog && chmod 600 CHANGELOG.md   # 只在改了重冻记因时需要
$PY ops/mk_release_manifest.py && chmod 600 RELEASE_MANIFEST.json            # 每次改发布件都要
```
