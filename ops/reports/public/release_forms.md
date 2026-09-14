# 发布形态：两条都走通并计时（卡 1.4）

> 判据：**同一个 `SHA256SUMS`**。形态 B 在别的机器上重建出来的 provider，
> 必须与形态 A 包里的**逐文件字节相同**。相同才说明「不下载我们的包也能独立验证」。
> （判据的射程是**数据面**：`docs/`、`selfbuild/` 两堆随包副本与 5 个构建戳文件
> 各单列一堆、不判红 —— 为什么，见 §3。）
> 本页所有数字都是 f01 上真跑出来的，不是估的（唯一的估算是全量取数，明确标了「外推」）。

* 建于 2026-09-06，仓库 HEAD 见 `MANIFEST.json` 的 `code_head`
* 许可状态 **`pending_license_text`** → **本包不对外发布**，落在 `_staging_unpublished/`
* 数据面来自卡 1.1-a（`$GB/snapshots/public_v1`），本卡不重建数据，只做发布形态

> **这一页写的是两种形态怎么建、怎么验 —— 不是「外部用户今天就能走完」。**
> 三件事闭合之前，这条链对外不成立（都在 §5，都登记为票，不是被隐瞒）：
>
> 1. **许可原文未入库**：`DATA_LICENSE` 顶部仍是 `pending_license_text`，包落在
>    `_staging_unpublished/`、`MANIFEST.license.publishable=false` —— 按设计**不对外发布**，
>    也就是说外部用户拿不到形态 A 的包；
> 2. **仓库还没有公开地址**（打包机器上 `git remote -v` 是空的），而形态 B 的第一步是
>    「拿一份完整仓库」—— 拿不到仓库的人**做不了形态 B**（包里的 `README.md` 那行
>    `git clone` 是占位符，2026-09-07 已在 `README_TEMPLATE` 里明写成占位符，
>    但 `_staging_unpublished/` 里那一份 README 还是 09-06 打的旧文本，**发布前必须重打一次包**）；
> 3. **`PUBLIC_FROZEN_ARTIFACTS` 声明的 6 个冻结件仓库里只有 3 个**（§5「包里少了什么」），
>    缺的那 3 个是 gold 的定义面，少了它们复现不了 τ。
>
> **在这三条闭合之前，别把这一页当成已交付的用户手册。**（红队 1.rt，2026-09-07）

---

## 0. 一眼看完

| | 形态 A（冻结包下载） | 形态 B（用户自建） |
| --- | --- | --- |
| 入口 | `ops/release/pack_public_provider.py` | `ops/release/build_public_provider.sh` |
| 用时 | **30.7 秒**（冷页缓存 43.1 秒）／ 24.9 秒（热） | **6 分 31 秒** 建集 ＋ **约 7.4 小时** 取数 |
| 产出 | 782,040,927 B 的 `tar.gz`（原始 990,829,153 B / 28,651 个文件） | 与包内容逐字节相同的一棵树 |
| 用户要做的 | 下一个 782 MB 的包，`sha256sum -c` | 装 `baostock==0.9.3`，非交易时段挂一夜 |
| 依赖第三方服务 | 不依赖 | 依赖 baostock 在线 |
| 校验和根 | `SHA256SUMS` 的 sha256 = `a1f2478d9a…` | 同一份 `SHA256SUMS` |

**逐文件比对结果：28,646 个文件全部相同，`differ` 0 个，只在一边 0 个**，
另有 5 个构建戳文件按设计不同（下面第 3 节逐个说明为什么）。

---

## 1. 形态 A —— 冻结 provider 下载包

    cd $GB/repo && $PY ops/release/pack_public_provider.py --dry-run     # 先看要打什么
    $PY ops/release/pack_public_provider.py                              # 打包
    $PY ops/release/pack_public_provider.py --built-at <ISO8601>          # 可复现构建

### 落点由许可状态决定

| `DATA_LICENSE` 顶部状态 | 落点 | `MANIFEST.license.publishable` |
| --- | --- | --- |
| `pending_license_text`（**当前**） | `$GB/release/_staging_unpublished/public_v1/` | `false` |
| `granted` | `$GB/release/public_v1/` | `true` |

`ops/test_env.py::test_no_published_provider_package_while_license_text_is_pending`
扫的是 `$GB/snapshots/public`，**扫不到 `$GB/release/`** —— 但那条锁的**意思**是
「许可原文没入库就不许存在打好待发的包」。所以：

* 打包脚本在 pending 期间**拒绝**往可发布路径写（`PackageError`）；
* `pack_public_provider.assert_nothing_published_while_pending()` 把同一条判据搬到
  `$GB/release/` 上，由 `ops/test_release_forms.py` 盯着。

**没有放宽既有那条测试，是把它的射程补齐。** 建议把 `test_env` 那条也扩到
`$GB/release`（`ops/test_env.py` 不在本卡路径内，已登记 → `ops/tickets_inbox/1.4.md`）。

### 包里有什么（28,651 个文件 / 990,828,077 B）

| 目录 | 文件数 | 大小 | 是什么 |
| --- | ---: | ---: | --- |
| `provider/` | 28,610 | 369.1 MB | 冻结 qlib bin provider（3,575 只 × 8 字段 = 28,600 个 bin）＋ `files.sha256` |
| `tables/` | 8 | 468.0 MB | 网关后端读的六张表 |
| `tradability/` | 20 | 153.5 MB | 可交易性视图，18 个年分区 |
| `universe/` | 1 | 32 KB | v1 三宇宙并集名单 3,575 行（形态 B 的取数输入） |
| `frozen/` | 3 | 35 KB | `PUBLIC_FROZEN_ARTIFACTS` 里**存在的**那 3 个（见第 5 节：另外 3 个不存在） |
| `docs/` | 4 | 60 KB | `DATA_LICENSE`、数据卡、公开通道建设记录 |
| `selfbuild/` | 5 | 48 KB | 形态 B 的脚本 |

**不进包的两块**：`build/quotes.parquet`（409 MB 中间产物）与 `state/`（断点标记）——
它们不是交付面，带上只会让下载的人以为那是数据的一部分。

### 用时（f01，12 核 / 30 G）

| 步骤 | 用时 |
| --- | ---: |
| 逐文件 sha256（28,651 个 / 0.99 GB） | 1.7 秒（热页缓存）／ 16.7 秒（冷） |
| 确定性 tar + gzip -6 | 23.6–28.5 秒 |
| 包体 sha256 | 0.4–0.5 秒 |
| **合计** | **30.7 秒（热页缓存 26.0–30.7 秒；冷 43.1 秒）**，峰值内存 68 MB |

### 确定性

条目按 arcname 排序、`mtime=0`、`uid=gid=0`、`uname=gname=""`、权限归一 0644、
**gzip 头的 mtime 也置 0**。包里唯一带构建时刻的是 `MANIFEST.json` 的 `built_at`，
所以对外的可复现口径是：**同一棵树 ＋ 同一个 `--built-at` → `tar.gz` 逐字节相同**。

实测（换一个落点再打一次）：

    c42c33eee55844d7bb88ed1e8c995db65fc6e144a3aa6f53369c55aa4be3c476  .../release/_staging_unpublished/public_v1/genebench_public_provider_v1.tar.gz
    c42c33eee55844d7bb88ed1e8c995db65fc6e144a3aa6f53369c55aa4be3c476  .../scratch/release_b_rehearsal/packA_repro/genebench_public_provider_v1.tar.gz

> **踩过的坑（值得留着）**：第一版把 `dest`（打包机器上的落点）写进了 `MANIFEST.json`，
> 于是同一棵树打到两个目录，`tar.gz` **差 97 个字节** —— 而我们对外承诺的正是
> 「你自己打一遍能得到同一个包」。`dest` 已移出 MANIFEST（改记在 `pack_result.json`，
> 那个文件留在打包机器上、不进包），`ops/test_release_forms.py` 里加了
> `test_whole_package_is_reproducible_given_the_same_built_at`：**换落点再打，字节必须相同**。

### 包体标识

| | |
| --- | --- |
| `genebench_public_provider_v1.tar.gz` | 782,040,927 B，sha256 `c42c33eee55844d7bb88ed1e8c995db65fc6e144a3aa6f53369c55aa4be3c476` |（`--built-at 2026-09-06T18:00:00+00:00`）
| `SHA256SUMS` | 28,653 行，sha256 `a1f2478d9a6b877c140d92bae1324b277c69f0025ad27d2df30a0e60cb4a88d8` |
| `MANIFEST.json` | 3,319,942 B，sha256 `a142dc8008c968ea9206253dc765b5441e50190958a1a634ae73ea174897e585` |
| provider `files.sha256`（卡 1.1-a 的 Merkle 根） | `f7dda2899071b07a933b6ecf73b9f3c6ea0f916df8384b2fdf498aa04d0a8752` |
| ↑ 2026-09-12 之前的值（v1.0.16 / p1.0.0 签字归档里记的是它） | `561348660a3175b17b906e2b4413e956959d7df4362939b0a85c67cf816c3a92` |
| **↑ 上面三行是 09-06 那次打的** | 许可翻成 `granted`、宇宙定义面换面之后，2026-09-12 重打过，**现值见 §7**（包体、`SHA256SUMS`、`MANIFEST.json` 三个 sha 都变了）|

用户校验就两行（在真包上实测过：**28,653 行全 OK，0.8 秒**）：

    tar xzf genebench_public_provider_v1.tar.gz
    cd genebench_public_provider_v1 && sha256sum -c SHA256SUMS

包里的 `README.md` 写明了四件外部用户会卡住的事：**要先有一份完整仓库**
（`selfbuild/` 里那五个脚本 import 的是仓库里的模块，单拿出来跑不起来，
它们是仓库同名文件的副本，拿 `SHA256SUMS` 对一下就知道没被改）、
**那行 `git clone` 现在是占位符 —— 仓库尚未公开，形态 B 只对已经拿得到仓库的人成立**
（2026-09-07 补；拿不到仓库不影响用这个包，形态 A 自足）、
**取数要挂一夜且交易时段拒绝启动**、以及**要复现包体 sha256 得给同一个 `--built-at`**。

> `_staging_unpublished/` 里那一份 `README.md` 是 09-06 打的，**还是旧文本**。
> 上面这两条（占位符说明、第四堆比对口径）在 `README_TEMPLATE` 里 ——
> **发布前必须重打一次包**，包内 README 与 `MANIFEST.json` 才会带上它们。
> 现在不重打的理由：包不可发布（许可 pending），而重打会让本页记的三个 sha256
> 立刻过期，而阶段二/三还在改 `docs/` 里那几份文档。

---

## 2. 形态 B —— 用户自建

    ops/release/build_public_provider.sh --root <数据根> --package <解开的包目录>

四段，每段可单独跑（`--stages preflight,fetch,build,compare`），取数与建集都能续跑：

| 段 | 做什么 | f01 实测用时 |
| --- | --- | ---: |
| 1 preflight | Python ≥ 3.10 / `pip install baostock==0.9.3` / 校包目录 / 铺并集名单 | **1 秒** |
| 2 fetch | 按并集名单拉 baostock —— **交易时段拒绝启动** | **20 只 148.4 秒** → 全量**外推 7.4 小时** |
| 3 build | 建表 → 单位门 → 可交易性 → provider | **385.7 秒** |
| 4 compare | 与包里 `SHA256SUMS` 逐文件比 | **约 2 秒** |

### 2 fetch 的计时口径（**这是抽样外推，不是实测全量**）

北京时间 2026-09-07 00:5x（**非交易时段**，判据由
`ops/acceptance/card_2_5_fetch_union.py::assert_not_trading_hours` 强制），
干净缓存目录、`--limit 20`：**20 只 148.4 秒，成功 20 失败 0**，即 **7.42 秒/只**
（其中 0.3 秒是显式请求间隔，其余是 baostock 单次全窗口查询本身的耗时）。

外推全量 3,575 只 = **26,530 秒 ≈ 7.37 小时**，与卡 2.5 里「7 个多小时」的判断一致。
另外还要：复权因子 3,575 次（卡 1.1-a 实测 **26.5 分钟**）＋ `stock_basic` 1 次（**37 秒**）。
**合计一夜：约 7.8 小时。**

> 为什么不实测全量：那是 3,575 次打第三方免费服务的请求，且必须整段落在非交易时段。
> 抽样 20 只已经把「每只多久」钉住了，而这个量级下总时间就是线性的（脚本是串行的、
> 每请求固定间隔）。**这一条在报告里明写成外推，不冒充实测。**

### 3 build 的分步用时（干净目录 `$GB/scratch/release_b_rehearsal/root`）

| 步 | 用时 | 产出 |
| --- | ---: | --- |
| 反建宇宙定义面 | < 1 秒 | `snapshots/v1/universe/universe_pit.parquet`（最小投影，见第 4 节） |
| `tables` | 283.4 秒 | 六张表 447 MB（含 1,132 万行涨跌停逐行推导） |
| `gate`（单位门） | 1.0 秒 | 公开 `daily` 全表 10,948,502 行，`low ≤ amount/volume ≤ high` |
| `tradability` | 32.1 秒 | 18 个年分区 147 MB |
| `provider` | 68.4 秒 | 28,600 个 bin，433 MB |
| **建集小计** | **385.7 秒** | |
| 解包 + 播种缓存 + 比对 | 约 6 秒 | |
| **整段 wall clock** | **6 分 31 秒** | |

**排练是真跑的**：`$GB/scratch/release_b_rehearsal/root` 是一个空目录，
`GENEBENCH_ROOT` 指向它，日线/复权/`stock_basic` 三份缓存用 **hardlink** 播种成
「用户已经下载完」的状态，然后走完 3→4。私有通道一个字节没读（`step_verify` 跳过，见第 4 节）。

---

## 3. 校验和一致性：28,646 相同，0 不同

    {"same": 28646, "differ": [], "only_in_package": [], "only_in_rebuild": [],
     "build_stamped_differ": ["provider/MANIFEST.sha256", "provider/build_info.json",
                              "provider/manifest.json", "tables/build_info.json",
                              "tradability/build_info.json"],
     "ok": true, "deterministic_total": 28646}

**28,600 个 bin、4 个 instruments、日历、`norm_base.parquet`、`files.sha256`、
六张表、18 个年分区 —— 逐文件 sha256 全同。**

### 那 5 个不同的文件：逐个归因

| 文件 | 为什么不可能相同 | 处置 |
| --- | --- | --- |
| `provider/manifest.json` | 含 `built_at`/`finished_at`（构建时刻）与 `source.*` 的**绝对路径**（随 `GENEBENCH_ROOT` 变） | 声明为构建戳，仍在 `SHA256SUMS` 里（包体完整性要它），**不参与** A↔B 逐字节比对 |
| `provider/build_info.json` | 含 `built_at` 与 `code_head` | 同上 |
| `provider/MANIFEST.sha256` | 逐文件表里含 `manifest.json` 的 sha256，随它一起变 | 同上 |
| `tables/build_info.json` | 含 `built_at` / `code_head` | 同上 |
| `tradability/build_info.json` | 含 `built_at` / `code_head` | 同上 |

**没有第六个**。也就是说：所有**数据**字节全同，不同的只有「这份东西什么时候、
在哪台机器上建的」这类元信息 —— 而这正是它们该记的东西，修成相同反而是在撒谎。

这三条模式写在 `pack_public_provider.BUILD_STAMPED` 里，**每一条都带理由**，
且 `ops/test_release_forms.py::test_build_stamped_patterns_are_not_zombies`
要求每条模式都必须真的命中包里的文件（D-23：豁免要可证伪）。

`compare()` 把差异分四堆报（`differ` / `build_stamped_differ` /
`package_provided_differ` / `only_in_*`）—— 预期内的差异混进 `differ` 会淹掉真问题，
从 `SHA256SUMS` 里删掉则会让包体校验漏掉它们。

### 第四堆：`docs/` 与 `selfbuild/`（2026-09-07 补，红队实测出来的）

上面那段 JSON 是 09-06 的原文，那时还没有这一堆 —— 而它**当时就已经在漏**：
`docs/` 与 `selfbuild/` 的内容取自**仓库工作树**，`--compare` 在重建侧重新从
**当前仓库**取同样那几个文件去比。于是**只要有人改过那四份文档或那五个脚本中的任何一份**，
逐文件比对就多一条 `differ`。红队 2026-09-07 实测（包 09-06 打、数据卡 09-07 14:40 改过）：

    [红] 逐文件相同 28645，differ 1（docs/ops/data_cards/public_channel.md），构建戳差异 5   → 退出码 1

数据面 28,645 个文件**全部逐字节相同**，判据被**一份 markdown** 拖红；而且会越来越红：
阶段二/三的代理每改一次数据卡或那五个脚本，就多一条。外部用户按手册做到第 4 步必然失败。

处置与构建戳同构（`pack_public_provider.PACKAGE_PROVIDED`，两条模式各带理由）：
**仍在 `SHA256SUMS` 里**（`sha256sum -c` 校的是**包内副本**，与仓库当前状态无关），
但 A↔B 比对**以包内副本为准**、单列一堆、不判红。
**只有内容漂移走这一堆** —— 文件只在一边（`only_in_*`）照旧判红：那是包的**文件清单**变了，
是打包面的改动，不是「有人改了一份随包发的文档」。

测试面此前**照不出**这条：旧夹具打包与比对是同一瞬间取同一份 repo，结构上没有漂移。
补的三条走真实次序（先 pack → **再改仓库** → 再 compare）：

| 测试 | 盯什么 |
| --- | --- |
| `test_a_doc_changed_after_packing_does_not_turn_form_b_red` | 改数据卡 → `ok=true`、`differ=[]`、单列一条；**同一条里把豁免摘掉再验一次红**（豁免要可证伪） |
| `test_a_selfbuild_script_changed_after_packing_is_reported_not_red` | 改 `selfbuild/` 脚本，同上 |
| `test_the_exemption_does_not_leak_onto_the_data_plane` | 文档与数据**同时**改 → 数据那条照旧判红（豁免宽一格就是判据被架空） |

真包上复核过两次（2026-09-07）：

| 比的是什么 | 结果 |
| --- | --- |
| 当前仓库 vs `_staging_unpublished/` 的 `SHA256SUMS` | `ok=true`、`same=28,649`、`package_provided_differ=2`、退出码 **0** |
| **红队留下的形态 B 重建树**（`$GB/scratch/rt_phase1/root`）vs 它解开的那个包 —— 就是形态 B 的 4/4 段本身 | `ok=true`、`same=28,642`、构建戳差异 **5**（第 3 节那五个）、`package_provided_differ=4`（今天改过的两份文档 + 两个脚本）、退出码 **0** |

**同一棵树、同一个包，修之前是 `differ 1` / 退出码 1**（红队那一跑）。
也就是说形态 B 的第 4 步从「对任何人都是红的」变回了「数据面差一个字节才红」。

---

## 4. 形态 B 里两处「公开源做不到」的地方（**明写，不糊**）

### ① 宇宙定义面推不出来，只能随包发

`instruments/{csi300,csi500,csi1000,all}.txt` 来自**私有** `universe_pit`
（`snapshots/qlib_provider.py::build_instruments`），而 `universe_pit` 是 tushare
`index_member_all` 派生的 —— **baostock 没有指数成分历史**。

所以形态 B 里宇宙定义**不是重算的，是随包发的**：
`ops/release/universe_from_instruments.py` 把包里那四个 txt 反投影成
`build_instruments()` 读得懂的最小 parquet（六列），建集照常走同一条实现。

**这不是把定义面藏起来**：重建出的 `instruments/*.txt` 必须与包里的**逐字节相同**，
不同就红 —— 这一条由 `rebuild_public_provider.assert_instruments_byte_identical()`
与 `--compare` 各判一次，排练里两处都绿。

反投影唯一丢的是 `ambiguous` 列（txt 只有三列）。它**只被 `build_instruments` 用来计数**，
不影响 `*.txt` 的字节；模块里显式置 `False` 并在返回值里写明，不假装是原值。
表现：重建树的 `manifest.json` 里 `instruments.*.ambiguous_rows` 是 0。

> **许可上的一条待办**：`instruments/` 不是 baostock 的产物，它的再分发**不在
> baostock 许可的射程内**。已写进 `MANIFEST.json` 的
> `data_source.universe_definition_note`，并登记为票（发布前须单独确认依据）。

### ② `verify` 步在用户机器上跑不了

`ops/build_public_channel.py` 的 `verify` 会比对**私有**快照的 mtime
（「两条通道并列不覆盖」）。用户机器上没有私有通道 → 形态 B **跳过这一步并说明**，
**不当作「验证通过」**。形态 B 的验收由 `--compare` 承担（那是更强的判据：逐文件字节）。
给公开通道补一条自足的 `verify` 已登记为票（v1.1）。

---

## 5. 许可状态与「合同原文到位后要改的唯一一处」

当前 **`pending_license_text`**：再分发许可**已取得**（用户 2026-09-05 告知），
**书面原文尚未入库**。因此：

* 包**已经打好**，落在 `$GB/release/_staging_unpublished/public_v1/`；
* `MANIFEST.json` 里 `license.published = false`、`license.publishable = false`；
* 打包脚本**拒绝**往 `$GB/release/public_v1/` 写。

### 原文到位后要改的**唯一一处**

> **`DATA_LICENSE` 的「## 2. 许可原文」一节** —— 把原文放进
> `ops/terms/baostock/permission/`，在那一节引用文件名、日期与签署方，
> 并把文件**顶部的状态**从 `pending_license_text` 改成 `granted`。

改完之后**不需要动任何代码**：`pack_public_provider.py` 自己读状态，落点自动从
`_staging_unpublished/` 变成 `release/public_v1/`，`publishable` 自动翻 `true`
（`ops/test_release_forms.py::test_publishable_flips_only_when_the_license_text_is_in` 钉着这条）。
`ops/test_env.py::test_license_state_matches_whether_the_text_exists` 会同时要求
「状态说 granted 就必须真有原文」，两边不许各说各话。

`publishable ≠ published`：**发不发是人的决定**，脚本只负责「能不能发」。

### 包里少了什么（**不静默**）

`snapshots/public/manifest.py::PUBLIC_FROZEN_ARTIFACTS` 声明了 6 个冻结件，
仓库里只有 3 个（`reference/factorlib_pinned/{formula,qlib_loader,qlib_ops}.py`）。
另外 3 个 —— `factor_library/compiled/{qlib_native,qlib_panel,blocked}.jsonl` ——
**整个 `factor_library/` 目录都不存在**。

它们是 gold 的**定义面**（「τ 标定于此实现对」），少了它们拿到包的人复现不了 τ。
打包**不静默丢**：记进 `MANIFEST.json` 的 `missing_declared_artifacts`，
`--dry-run` 会打黄字，`ops/test_release_forms.py::test_missing_declared_frozen_artifact_is_recorded_not_swallowed`
盯着这条。已登记为票 —— **这一条挡正式发布**（`published` 翻 true 之前必须补齐或改清单）。

---

## 6. 复现命令（后续代理照抄）

    GB=/data/shared/genebench; PY=$GB/env/bin/python; cd $GB/repo

    # 形态 A
    $PY ops/release/pack_public_provider.py --dry-run
    $PY ops/release/pack_public_provider.py --built-at 2026-09-06T17:00:00+00:00

    # 形态 B（f01 排练：缓存已播种，跳过 fetch）
    ops/release/build_public_provider.sh --root <干净目录> --package <解开的包> \
        --stages preflight,build,compare --python $PY

    # 只比校验和（退出码 0 = 数据面全同；docs/ 与 selfbuild/ 的漂移单列不判红，见 §3）
    GENEBENCH_ROOT=<那个目录> $PY ops/release/pack_public_provider.py \
        --root <那个目录> --repo $GB/repo --compare <包>/SHA256SUMS

    # 取数计时抽样（**非交易时段才跑**）
    GENEBENCH_ROOT=<干净目录> $PY ops/release/fetch_public_quotes.py \
        --root <干净目录> --union <干净目录>/scratch/v1_union.txt --limit 20 --quotes-only

    # 测试
    ulimit -n 8192 && $PY -m pytest ops/test_release_forms.py -q -p no:cacheprovider

f01 上 baostock 没装进 env，源码在 `/tmp/bsx/baostock-0.9.3`：
排练时 `export PYTHONPATH=/tmp/bsx/baostock-0.9.3`（用户机器上走 `pip install baostock==0.9.3`）。

排练产物（**不进 git**）：`$GB/scratch/release_b_rehearsal/{root,pkg,packA_repro,fetch_timing}`；
日志与计时 `$GB/scratch/1.4/{packA,rehearseB,fetch20,finalA}.log`。

<!-- C-SECTION -->

---

## 7. 2026-09-12 重打：两个可发布附件（裁定 ②）

> 本节的数字**全部是 f01 上真跑出来的**，由 `ops/release/pack_*.py` 写进
> `ops/release/attachments.json`，再由 `ops/mk_release_manifest.py` 逐件进
> `RELEASE_MANIFEST.json` 的 `release_attachments` 段。
> **§0 / §1 记的是 2026-09-06 那一次**（许可还是 `pending_license_text`、
> 宇宙定义面还没换）—— 那是一份有日期的记录，本节不去改它，只在这里给现值。

### 7.1 落点与许可

`DATA_LICENSE` 顶部现值是 **`granted`**，于是 `dest_for()` 解出可发布路径：

    $GB/release/public_v1/            ← 两个附件都落这里（脚本按许可**现值**解，不是写死的）
    $GB/release/_staging_unpublished/public_v1/   ← 09-06 那版旧包还在，**不发**（见 known_limits）

### 7.2 两个附件

| | `genebench_public_provider_v1.tar.gz` | `genebench_public_gold_subset_v1.tar.gz` |
| --- | --- | --- |
| 字节 | **782,100,276** | **157,448,605** |
| sha256 | `33083ff242c64a8f0bbbcec332ef4d3ad87daa703b78d95728ccdd1bdefc18e9` | `edc5ea7cf70ffec3589b981cd67b2b9872527ea8001a2495bde8d6c55ec9ef06` |
| 包内文件 / 未压缩字节 | 28,656 / 991,366,097 | 44 / 159,394,437 |
| `--built-at` | `2026-09-12T00:00:00+00:00` | 同左 |
| 构建 HEAD | `4dfa5be41f658402e9f900b4d427e5c1a7e26bc1` | 同左 |
| 校验和文件 | `SHA256SUMS`（28,658 行，`8008d6ccb21b102d…`） | `gold_subset_SHA256SUMS`（46 行，`1c07f0e6d1038738…`） |
| 清单 | `MANIFEST.json`（3,321,178 B，`3b97975606a8ec21…`） | `gold_subset_MANIFEST.json`（8,215 B，`781a5fd2c2e6b4b6…`） |
| 随包 README | `README.md`（3,823 B，`5596413b89e5c717…`） | `gold_subset_README.md`（1,739 B，`bc289705dd4564c7…`） |

四条版本轴（两个附件各自记在自己的 `MANIFEST.json` 与 `attachments.json` 里，值相同）：
任务集 **1.0.16** / 公开任务集 **p1.0.0** / 参考轴 **r1.0.23** / 协议 `geneprotocol_v1@<逐 run 反算>`。

**下载地址**：`attachments.json` 与 `RELEASE_MANIFEST.release_attachments` 里的
`download_url` 现在是**空串** —— 空串就是「还没上传」，由上传那一步（裁定 ③）回填。
再打一次包**不会**把已回填的地址抹掉（`ops/test_pack_release.py::test_重新打包不会抹掉已回填的下载地址`）。

### 7.3 包里有什么（现值）

形态 A（28,656 个文件 / 991,366,097 B）：

| 目录 | 文件数 | 字节 | 是什么 |
| --- | ---: | ---: | --- |
| `provider/` | 28,609 | 368,843,989 | 冻结 qlib bin provider。`instruments/` 只剩 `csi300` / `csi500` / `all` 三个 txt |
| `tables/` | 8 | 468,016,569 | 网关后端读的六张表 |
| `tradability/` | 20 | 153,540,937 | 可交易性视图，18 个年分区 |
| `universe/` | **4** | 56,500 | **两样东西**，见 §7.4 |
| `frozen/` | 6 | 780,121 | `PUBLIC_FROZEN_ARTIFACTS`（现已 6 件全到位） |
| `docs/` | 4 | 64,542 | `DATA_LICENSE`、数据卡、公开通道建设记录 |
| `selfbuild/` | 5 | 63,439 | 形态 B 的脚本 |

gold 子集包（44 个文件 / 159,394,437 B）：`gold_factors/` 41 件（152.0 MiB，
csi300 / csi500 两个宇宙）＋ `docs/` 3 件（`DATA_LICENSE`、子集数据卡、换面报告）。
源根是 **`$GB/snapshots/public_v1/gold_factors_r2/`** —— 卡 A 按 baostock 重建的成分
全量重算的那一份；清单 `gold_subset_public.json` 逐件 sha256 在打包时**现算比对**，
对不上当场抛。旧 `gold_factors/` 那 41 件的 sha **41/41 已经不成立**，照它打会让用户的校验命令当场红。

### 7.4 `universe/` 下的两样东西（**别混成一句**）

| 包内路径 | 是什么 | 出处 |
| --- | --- | --- |
| `universe/universe_pit.parquet`（＋ `build_info.json` / `MANIFEST.sha256`） | **宇宙定义面**：哪天哪只票在哪个指数里。3,295 行，只有 csi300（1,026）与 csi500（2,269） | 卡 A 由 baostock 成分接口重建的 `instruments/` **反投影**生成，**无 tushare 派生行、无 csi1000** |
| `universe/v1_union.txt` | **取数名单**：3,575 只，决定 `provider/features/` 里有哪些票的 bin，形态 B 照它取数才重建得出同一棵树 | v1 三宇宙并集（保留的理由与代价见 [`instruments_switch.md` §3](instruments_switch.md)） |

于是 `instruments/all.txt`（1,917 行）与 `features/`（3,575 只）**本来就对不上** ——
这不是巧合被打破，是定义被写清楚了：`all` 的语义是「本包**两个宇宙**里有行情的票」。
包内 `MANIFEST.json` 的 `universe_definition_note` 把这三句话原样写着。

### 7.5 打完解开核了一遍（流式读 tar，不落盘）

脚本 `$GB/scratch/C/c_verify_pkg.py`，产物 `$GB/scratch/C/verify_pkg.json`：

| 核什么 | 结果 |
| --- | --- |
| `instruments/` 里有没有 `csi1000` | **没有**（整包路径里 `csi1000` 出现 0 次） |
| `csi300.txt` / `csi500.txt` 与 W2 重建产物 | **逐字节相同** |
| `all.txt` 的码是不是 `csi300 ∪ csi500` 的子集 | **是**，1,917 只；并集里多出的 `SZ000022` / `SZ300114` 没有 bin，按设计不列 |
| `universe/` 三件与 `$SNAPSHOTS/public_v1/universe/` | **逐字节相同**，`universes = {csi300: 1026, csi500: 2269}` |
| 答案面（`scorer/` `runs_in/` `gold/` `memory_probe_answers/`、白名单外的 `reference/`） | **命中 0 条** |
| 包内 `SHA256SUMS` 与实际条目 | 28,658 行**逐件相同**，两边都没有多出来的文件 |
| tar 条目属性 | 全部 `mtime=0` / `uid=gid=0` / `0644` / 普通文件 |
| gold 包：41 件与 `gold_subset_public.json` | **逐件相同**；包里没有 `csi1000`；四条轴与 provider 根 `f7dda2899071b07a…` 记在 `MANIFEST.json` 里 |

### 7.6 确定性：连打两次逐字节相同

同一棵树、同一个 `--built-at`，一次落发布目录、一次落 `$GB/scratch/C/det/`，
**8 件产物全部 `SAME`**（`$GB/scratch/C/pack3.log` 的「逐字节比」那一段）：
两个 `tar.gz`、两份 `SHA256SUMS`、两份 `MANIFEST.json`、两份 `README.md`。

判别力也验了：`ops/test_pack_release.py::test_不给built_at的两次必须不同_否则上一条是恒绿的`
—— 换一个 `--built-at`，两个包的 sha **必须**不同。

### 7.7 用时（f01，12 核 / 30 G，全程持 `heavy.lock`）

| | 逐文件 sha256 | 确定性 tar + gzip -6 | 包体 sha256 | 合计 | 峰值 RSS |
| --- | ---: | ---: | ---: | ---: | ---: |
| 形态 A | 1.6 秒 | 27.5 秒 | 0.4 秒 | **29.7 秒** | 69 MB |
| gold 子集 | 0.1 秒 | 4.9 秒 | 0.1 秒 | **5.1 秒** | 25 MB |

### 7.8 复现命令（后续代理照抄）

    GB=/data/shared/genebench; PY=$GB/env/bin/python; cd $GB/repo
    $PY ops/release/pack_public_provider.py --dry-run          # 先看要打什么
    $PY ops/release/pack_gold_subset.py     --dry-run
    flock $GB/locks/heavy.lock -c "cd $GB/repo && \
      $PY ops/release/pack_public_provider.py --built-at 2026-09-12T00:00:00+00:00 && \
      $PY ops/release/pack_gold_subset.py     --built-at 2026-09-12T00:00:00+00:00"
    $PY ops/mk_release_manifest.py            # 重出清单（release_attachments 段随之更新）
    $PY ops/mk_release_manifest.py --check    # 退 0 才算对上
    $PY -m pytest ops/test_pack_release.py ops/test_release_forms.py -q -p no:cacheprovider

外部用户的校验就两行（两个附件各一遍）：

    tar xzf genebench_public_provider_v1.tar.gz
    cd genebench_public_provider_v1 && sha256sum -c SHA256SUMS

    tar xzf genebench_public_gold_subset_v1.tar.gz
    cd genebench_public_gold_subset_v1 && sha256sum -c gold_subset_SHA256SUMS

### 7.9 这两个附件**不**回答的问题（登记，不修）

* **gold 子集算在新名单上，随包的阈值算在旧名单上** —— `calibration.json`（τ / ε / IC 族）、
  `crosscheck/`、`epsilon/` 仍建在换面**之前**的 `gold_factors/` 上，两者不同源。
  已发布的 18 个公开 run 同样跑在旧 provider 上。见 `ops/reports/known_limits_v1.md`。
* **`csi1000` 不入公开包**（baostock 0.9.3 没有该指数的成分接口）—— 公开通道复现不出
  任何以 csi1000 为宇宙的读数。
* **`RELEASE_MANIFEST.package` 那一段是旧数**（读的是 09-06 的演练产物）；
  现值以本节与 `release_attachments` 段为准。

<!-- /C-SECTION -->
