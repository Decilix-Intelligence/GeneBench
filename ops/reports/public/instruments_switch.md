# 卡 A：把公开包的宇宙定义面换成 baostock 重建结果

* 做于 2026-09-12（UTC 13:2x–1x:xx），f01；用户裁定 ①
* 前置：卡 W2 的重建产物 `$GB/snapshots/public_v1/instruments_rebuild/`，对账见
  [`instruments_rebuild.md`](instruments_rebuild.md)
* 换面脚本 `$GB/scratch/A/a_switch_provider.py`（幂等）；备份
  `$GB/scratch/A/backup_old_instruments/`
* 守门 `ops/test_a_publish.py`

---

## 0. 一眼看完

| | 换之前 | 换之后 |
| --- | --- | --- |
| `instruments/csi300.txt` | 私有 `universe_pit` 派生（上游 **tushare** `index_weight`），1,507 行 / 825 只 | **baostock `query_hs300_stocks` 重建**，1,026 行 / 825 只 |
| `instruments/csi500.txt` | 同上，3,025 行 / 1,738 只 | **baostock `query_zz500_stocks` 重建**，2,269 行 / 1,708 只 |
| `instruments/csi1000.txt` | 同上，4,455 行 / 2,839 只 | **删除**（baostock 0.9.3 没有中证 1000 的成分接口） |
| `instruments/all.txt` | 3,575 行（私有 `universe_pit` 的 `all`，**147 行的右端是 tushare 口径**） | **1,917 行**，逐行 = 公开 `daily` 表里该票的首末交易日 |
| `universe/universe_pit.parquet` | 与私有那份**逐字节相同**（tushare 派生） | 由新 `instruments/` **反投影**重建，3,295 行（csi300 1,026 / csi500 2,269） |
| `files.sha256` 根 | `561348660a3175b17b906e2b4413e956959d7df4362939b0a85c67cf816c3a92` | **`f7dda2899071b07a933b6ecf73b9f3c6ea0f916df8384b2fdf498aa04d0a8752`** |
| 清单里的文件数 / 字节 | 28,606 / 363,092,471 | **28,605 / 362,864,621** |
| `features/` | 3,575 只 | **一个字节没动**（见 §3） |

**一句话**：公开包的宇宙定义面现在**整条链都是 baostock 的**；代价是 `csi1000` 出包，
以及公开 provider 的根指纹变了一次（连锁清单见 §4）。

---

## 1. 逐行核「不含任何 tushare 派生行」

三个文件三条不同的证据，**都能被证伪**：

| 文件 | 怎么核的 | 结果 |
| --- | --- | --- |
| `csi300.txt` / `csi500.txt` | 与 `instruments_rebuild/` 的产物**逐字节**比 sha256 | **相同** —— 只要有一行是在重建产物之外加工出来的，这里就红（`ops/test_a_publish.py::test_csi300与csi500逐字节等于baostock重建产物`） |
| `all.txt` | 与公开 `daily.parquet`（baostock）逐票的 `min/max(trade_date)` **逐行**比 | **1,917 行全部对上**（`test_all的区段就是公开日线表里的首末交易日_不是universe_pit派生`） |
| `universe/universe_pit.parquet` | 由 `ops/release/universe_from_instruments.py` 从上面三个 txt **反投影**生成 | 只含 `csi300` / `csi500` 两个宇宙；不读任何私有表 |

### 1.1 `all.txt` 为什么不能沿用旧的区段

第一版做法是「码取新两个宇宙的并集、**区段沿用旧 `all.txt`**」。核的时候发现
**1,917 只里有 147 只的区段与公开日线表对不上** —— 旧 `all.txt` 的右端来自私有
`universe_pit` 的退市日（tushare 口径），普遍比 baostock 最后一根 K 线**晚几天到几周**：

| 例 | 旧 all.txt（tushare 口径） | 公开日线表（baostock） |
| --- | --- | --- |
| `SH600001` | `2009-01-05 … 2009-12-28` | `2009-01-05 … 2009-12-15` |
| `SH600005` | `2009-01-05 … 2017-02-13` | `2009-01-05 … 2017-01-23` |
| `SH600094` | `2009-01-05 … 2026-07-31` | **`2011-10-11`** … `2026-07-31` |

那 147 行就是**留在包里的 tushare 派生物**。所以 `all.txt` 改成**逐行由公开 `daily` 表算出来**
（`$GB/scratch/A/a_all_from_baostock.py`）。差异明细 `$GB/scratch/A/all_txt_source.json`。

### 1.2 两只有名单没有行情的票

baostock 的 csi500 里有 **`SZ000022`** 与 **`SZ300114`**，而私有 `universe_pit`
**整张表里根本没有这两个代码**（W2 §3.1 已登记），于是公开通道的行情面也没有它们
（`features/` 下没有这两只的目录）。处置：

* **`csi500.txt` 里照留** —— 上游名单说它在册就是在册，删掉等于替上游拍板；
* **`all.txt` 里不列** —— `all` 的语义是「本包有行情的票」，列一个没有 bin 的码是空头支票；
* **实测 qlib 不会因此炸**：`D.features` 在名单里遇到没有数据的码会**静默跳过**
  （`$GB/scratch/A/a_probe_qlib.py`：csi500 在 2019-01 的某几天返回 499 只，无异常）。
  后果是那些天的 csi500 **实际参与计算的成员少一只**，如实记在这里。

---

## 2. 两个宇宙的 delta（全窗 + gold 窗）

全窗 `2009-01-05 … 2026-07-31`（4,269 个交易日；旧 = 换之前包里那一份）：

| | csi300 | csi500 |
| --- | ---: | ---: |
| 码：只在旧 / 只在新 | **0 / 0** | **32 / 2** |
| 逐日成员集合完全相同的天 | 3,688 / 4,269（86.4%） | 3,088 / 4,269（72.3%） |
| 逐日不同的天 | **581** | **1,181** |
| 「日×成员」格差（对称差） | 20,167 | 53,038 |
| 「日×成员」格总数（旧 / 新） | 1,280,579 / 1,280,700 | 2,134,384 / 2,134,478 |

gold 窗 `2015-05-29 … 2026-07-31`（2,716 个交易日）：

| | csi300 | csi500 |
| --- | ---: | ---: |
| 逐日完全相同的天 | 2,358（86.8%） | 2,089（76.9%） |
| 逐日不同的天 | **358** | **627** |
| 格差合计 / 加的 / 减的 | 12,195 / 6,121 / 6,074 | 31,282 / 15,652 / 15,630 |
| 被碰到的代码数 | 566 | 1,327 |
| 第一 / 最后一个不同的日子 | 2015-06-15 / 2026-06-29 | 2015-06-15 / 2026-06-29 |
| 日均成员（旧 / 新） | 299.983 / **300.000** | 499.984 / 499.992 |

**差的是什么**：W2 §3.2 已经把归因做完了 —— 私有那份把成分调整**吸附到月末**
（上游 `index_weight` 是月频），baostock 给的是**实际生效日**，中位差 **−15 天**。
所以这不是「名单质量差」，是「两份名单在每年 6 月 / 12 月调整的那两周里各说各话」。

明细 `$GB/scratch/A/delta.json`、`$GB/scratch/A/delta_gold_window.json`。

---

## 3. `features/` 怎么处理：**留着**，理由写在这里

只在 csi1000 里的那 1,658 只票，它们的 bin **仍在包里**（`features/` 一个字节没动，
3,575 只）。两条路各自的代价：

| | 留着（**选这条**） | 删掉 |
| --- | --- | --- |
| 许可 | 无问题 —— 那是 baostock 日线，在 §2 授权射程内 | 无问题 |
| 树与清单自洽 | `all.txt` 1,917 行 < `features/` 3,575 只，**对不上**，要在 manifest 里说明 | 自洽 |
| 包体 | 433 MB | 约 233 MB |
| 可逆性 | 可逆 | **不可逆** —— 要再拉一次数（baostock 公开 API 拒连过，W2 §1） |
| 旁证产物 | `snapshots/public_v1/gold_factors/csi1000`（8.9 GB）仍能由这棵树复现 | **复现不出来了** |

**选「留着」的理由**：删掉是**不可逆**的，而留着的唯一代价是 200 MB 与一句说明。
`manifest.json` 与 `build_info.json` 的 `universe_definition_note` 各写了这一句，不静默。
`all` 的语义因此从「本包所有票」收窄成「**本包两个宇宙的票**」——
这不是巧合被打破，是定义被写清楚了。

---

## 4. 旧根还钉在哪里：逐处跟改与留证

换面让公开 provider 的根从 `561348660a3175b1…` 变成 `f7dda2899071b07a…`。

| 处 | 是什么 | 做了什么 |
| --- | --- | --- |
| `runner/inject.py::PUBLIC_PROVIDER_SHA256_ROOT` | **唯一一处功能性钉子**（P2 按通道取） | **改成新值**，注释里留了旧值与换面日期 |
| `ops/data_cards/public_channel.md` | 公开通道数据卡（带 `<!-- src: -->` 自动核对） | provider digest / 文件数两行改新值；表头加一段「2026-09-12 换过宇宙定义面」的说明 |
| `ops/reports/public/qlib_provider_public.md` | 公开 provider 数据卡 | 改新值，并写明此前是什么 |
| `ops/reports/public/release_forms.md` | 发布物料表 | 改新值，**另起一行**记旧值与「签字归档里记的是它」 |
| `DATA_LICENSE` §5 | 许可判断 | 整节改写（见 §6），并记 `561348660a3175b1… → f7dda2899071b07a…` |
| f02 `/data/genebench_runner/provider/` | 按根命名的目录 | **新建** `qlib_provider_f7dda289/` 并 rsync（28,609 个文件，现算根一致）；**旧的 `qlib_provider_56134866/` 不删** |
| `ops/reports/signed/v1.0.16_r1.0.23/`、`ops/reports/signed/public_vp1.0.0_r1.0.23/` | **只读签字归档** | **不改** —— 归档记的就是签字那一刻的事实。两份归档里记的仍是旧根 `561348660a3175b1…`；这件事写在这里、写在 `known_limits_v1.md`，不写进归档 |

### 4.1 验门：两条通道各一次，反向门当场证明有牙

证据 `$GB/scratch/A/gates.log`、`$GB/scratch/A/dry.log`。

换面当时跑过一次；**提交 `0b07713` 之后又原样跑了一次**，四格结论一字不差，证据 `$GB/scratch/A/gates2.log`（含 f02 那一遍）与 `$GB/scratch/A/dry2.log`（两条通道 `--dry` 各 `rc=0`，strict vs open 三条子句逐条对上）。反向门的探针两次都跑完即删、删后复核仍绿。

| 通道 / 机器 | `check_provider_pin` | 拿旧根当 expect | 反向门（塞一个清单外的文件） | `--dry` 注入 |
| --- | --- | --- | --- | --- |
| public / f01 | **绿**（`[]`） | **红**（如实说「根变了」） | **当场红**：`P2 树里有而清单里没有：features/__gate_probe_A__.bin` | **绿**，两臂三条子句逐条对上 |
| public / f02 | **绿** | **红** | **当场红**（同一句） | —— |
| private / f01 | **绿**（`54fdda39`，一个字节没动） | —— | —— | **绿** |

反向门的探针跑完即删，跑完再核一次 `check_provider_pin` 仍绿（`clean_after_probe: true`）。

---

## 5. gold 子集按新成分核一次

<!-- GOLD-SECTION -->

裁定 ① 明文要「gold 子集按重建后的成分核一次，不一致的重算」。
**核了：41 件全部变了。重算了，落在旁路根 `gold_factors_r2/`。**

### 5.1 为什么一定会变：gold 是**按成分掩膜**落盘的

`reference/factor_exec.py::write_gold` 算完整张面板之后 `f.where(mask)`，**只留当日在成分内的格**。所以名单一变，「有哪些 `(date, code)` 行」跟着变 —— §2 已经把行集的差量清出来了：gold 窗内 csi300 差 12,195 格、csi500 差 31,282 格。

### 5.2 重算：落**旁路根**，一个字节不碰既有 `gold_factors/`

```
$PY -m reference.factor_exec --universe {csi300,csi500} \
     --start 2015-05-29 --end 2026-07-31 \
     --gold-root $SNAPSHOTS/public_v1/gold_factors_r2
```

不原地覆盖的理由只有一条：既有 `gold_factors/` 是**旧 instruments 的产物**，`calibration.json` / crosscheck / ε 与**已发布的 18 个公开 run**全都建在它上面（§7）。原地覆盖 = 把那 18 个读数的可复现性一次性抹掉。两份并存，各自记清算在哪一版名单上。

* `csi300`：792 件全部重算完（`rc=0`），与旧 gold **逐字节相同 0 件 / 不同 792 件**。
* `csi500`：792 件全部重算完（`rc=0`），与旧 gold **逐字节相同 0 件 / 不同 792 件**。

峰值 RSS csi300 2.6 GB（34 分）/ csi500 6.5 GB（59 分），封顶 `MemoryMax=20G`，全程持 `heavy.lock`。日志 `$GB/scratch/A/gold_r2.log`。

### 5.3 公开 gold 子集那 41 件：逐件结论

清单口径照 `ops/reports/i_rehearsal_v2/gold_subset.json` 的 `channels.public`（41 件；核之前先确认这 41 件在旧树上的现算 sha 与清单里记的**逐件相同**，确认通过 —— 比的是同一个基准）。

| | 件数 |
| --- | ---: |
| 逐件核过 | **41** |
| 新旧 sha256 **相同** | **0** |
| 新旧 sha256 **不同**（已重算，取新的那份） | **41** |

行集与数值分开看（41 件加总）：

| | 格数 |
| --- | ---: |
| 新增的格（新名单里在、旧名单里不在） | 286,750 |
| 消失的格 | 279,880 |
| 两版**共有**的格 | 33,527,179 |
| 共有的格里**数值变了**的 | **4,511,718**（占共有格 13.5%） |

### 5.4 共有格的值为什么也会变 —— 完全归因，没有余项

「换名单只该改算哪些格、不该改怎么算」是个**错的**直觉，这里把它证伪并归完：三条求值路对名单的敏感度本来就不同。

| 求值后端 | 件 | sha 变 | **共有格值变**的件 | 变了的格 | 为什么 |
| --- | ---: | ---: | ---: | ---: | --- |
| `qlib_expression` | 23 | 23 | **0** | 0 | qlib 先在**整段逐票历史**上求值，再按成分区段切行 —— 算的时候看不见「今天名单里还有谁」，也看不见区段边界。**只有行集变** |
| `qlib_panel_loader` | 6 | 6 | **6** | 2,863,736 | 源方言里带**截面算子**（`RANK(...)`：同一天所有票排序）。截面里站着谁变了，排名就变 |
| `qlib_kunquant_loader` | 12 | 12 | **9** | 1,647,982 | 面板取自 `D.features(D.instruments(uni))`，**逐票序列按成分区段截断**；再叠上 Alpha101 里的 `Rank`。见下面两条 |

**判据（能被证伪的那一条）**：把变了的每一格按代码归位 —— **变了值的格，100% 落在「成分区段本身发生了变化」的票上；落在区段一天没动的票上的格是 0 格。**

这条是本节的门：只要有一格落在区段没动的票上，说明动的就不止是成分（provider 的 bin 变了、求值器变了、暖机变了……），那就得停下来查，而不是接受重算结果。产物 `$GB/scratch/A/gold_attrib.json`。

两条机制各有一个直接证据：

* **截面算子**：`gtja_191.001`（`CORR(RANK(DELTA(LOG(VOLUME),1)), RANK((CLOSE-OPEN)/OPEN), 6)`）在 csi500 上变了 1,247,120 格；而**整条 `qlib_expression` 路**（`qlib_alpha158.*` 23 件）**一格没变**。
* **区段截断**：`worldquant_101.010`（KunQuant `alpha010`，纯时序、**没有任何截面算子**）只变了 121 格，而这 121 格**全部**落在距成分区段端点 ≤ 5 个交易日之内（中位 2 天）——窗口算子在区段的接缝处看见的历史变了。产物 `$GB/scratch/A/gold_edge_attrib2.json`。

> `worldquant_101.006`（同样纯时序）变的格离接缝更远：KunQuant 的滚动相关是**增量式**累积的，起点一移，float32 的舍入差会沿着序列一路带下去。它同样满足上面那条门（全部落在区段变了的票上），**不另开调查**。

### 5.5 新子集清单落在哪 —— 打包（裁定 ②）要从这里取

`$SNAPSHOTS/public_v1/gold_factors_r2/gold_subset_public.json`：41 件逐件 `rel` / `bytes` / `sha256`，合计 159,359,214 B，并记了它算在哪个 provider 根上（`f7dda2899071b07a…`）。

**`ops/reports/i_rehearsal_v2/gold_subset.json` 里公开通道那 41 行的 `sha256` 是旧的**（41/41 行已经不成立）。打 gold 子集包从 `gold_factors_r2/` 取，否则发出去的分与发出去的宇宙定义对不上 —— 已写进 `ops/tickets_inbox/A.md` 与 `ops/data_cards/gold_subset_v1.md`。

**没有跟着重算的**（登记不修，见 `known_limits_v1.md`）：`calibration.json`（τ / ε / IC 族）、`crosscheck/`、`epsilon/` 仍然算在**旧 gold** 上。它们是**阈值**不是读数，重算要连带重跑 IC-ε 与互检全量，超出本卡范围。

逐件原始产物 `$GB/scratch/A/gold_compare.json`（每件 `sha_old` / `sha_new` / `cells_added` / `cells_removed` / `cells_value_changed` / `max_abs_diff_on_common`）。

<!-- /GOLD-SECTION -->

---

## 6. `DATA_LICENSE` §5 改写了什么

| | 换之前 | 换之后 |
| --- | --- | --- |
| 标题 | 「公开包里 `instruments/` 的再分发依据**未确认**」 | 「公开包里 `instruments/` 的再分发依据：**由 baostock 接口重建**」 |
| 结论 | 「**不在 baostock 许可的射程内** […] **发布前须单独确认**」 | 「**在 §2 授权的射程内** […] 发布前不再需要单独确认」 |
| csi1000 | 未提 | 明写**不入公开包**，以及后果（公开包复现不出任何以 csi1000 为宇宙的读数） |
| §0 速览表 | 「另一处未确认的再分发依据」 | 「宇宙定义面（`instruments/`）：由 baostock 成分接口重建，在授权射程内」 |

**一处诚实说明，写在 §5 里没有藏**：§2.0 的授权摘要写的是「再分发**派生日线数据**」，
而成分表是**同一个 API 的另一组接口**返回的。把它算进射程是**仓库所有者的裁定**，
不是从摘要字面推出来的；正文（§2.1）到位时若与这条不符，**以正文为准**。

`ops/test_p.py` 里那条守门（原先钉「未确认」）**换了判据而不是放宽**：
现在钉「§5 说的是重建 / 射程 / csi1000 出包」，并**额外**钉「旧判断的原话不许还留在文件里」——
两个相反的结论同时在一份许可文件里，读者无从分辨。

---

## 7. 已发布的 18 个公开读数跑在**旧 provider** 上

**这件事不修，只登记**（用户裁定 ⑥ / ①：agent run 不重跑）。

* 18 个 run 在 `$GB/runs_in/m6_public/`，`inject.json` 里记的 provider 根是
  `561348660a3175b1…`，f02 上用的是 `qlib_provider_56134866/`；
* **逐个核过：18 个 run 用的宇宙全是 `csi300`。** 核法说清楚，因为这里有个陷阱：
  run 目录里 `work/provider/manifest.json` 与 `build_info.json` **三个宇宙名都出现**（那是 provider 自己的清单，列的是包里发了哪几个 `instruments/*.txt`，不是这道题用了哪个）。按**题面**核 —— `work/INSTRUCTION.md`、`work/S*.json`、`work/protocol/contract.json` —— 18 个 run **一个不落只出现 `csi300`**；
* 18 个 run 的 `inject.json` 钉的 provider 根**全部**是 `561348660a3175b1…`，没有第二个值。产物 `$GB/scratch/A/public_runs_universe.json`；
* 于是这批读数与现在包里的宇宙定义**差在 gold 窗内 358 天 / 12,195 个「日×成员」格**
  （§2），成员集合本身**一只不差**；
* **复现这 18 个读数需要旧 provider**，而旧 provider 在 f02 上**保留着**
  （`qlib_provider_56134866/`，本卡没删）；仓库这一侧只保留了 `instruments/` 的备份
  （`$GB/scratch/A/backup_old_instruments/`）。

同样登记在 `ops/reports/known_limits_v1.md`。
