# 公开通道的重建链（卡 1.1-b）

> **这不是数据卡。** 这里记的是「同一份代码在公开数据面上跑一遍，每一步花了多久、出了多少东西、结论变没变」。「私有」那一列是**对照**，用来回答卡 2.5 §10 的「结构性结论是否不变」——**不是**在说公开通道自己量到了那些数。

* 链条：`gold（三宇宙）→ 互检（2.1b）→ τ → ε（daily/weekly/monthly）→ IC-ε（N-117）→ calibration.json`
* 一条命令：`$PY ops/run_public_chain.py`（可续跑，`--step` 单跑一步，`--dry-run` 只看）
* 公开落点：`/data/shared/genebench/snapshots/public_v1`；私有落点：`/data/shared/genebench/snapshots/v1`（两条**并列不覆盖**）
* 参考版本：**r1.0.19**（本卡推的那一版；理由见 `ops/freeze_v10.py` 的 `REFERENCE_REVISIONS`）

## 0. 为什么这一版要改 gold 的内存形态（读这一节再看用时）

这条链前两次都**没跑完**：`gold csi1000` 被内核 OOM 杀掉两次（`exit=137`），第二次是 2026-09-07 05:20Z，anon-rss **22 GB**，把 f01 整机拖到失联两小时。

根因不是「数据大」，是 `reference/factor_exec.run()` 的形态：**792 个因子面板同时压在内存里**，等全部算完才进 `write_gold`。csi1000 的面板是 2716×2839 的 float64，792 张合起来常驻约 22 GiB —— 而 f01 只有 30 GiB 且是共用机（同期还有别人的全量 pytest 与用户自己的爬虫）。

**能看出「是换页不是慢」的那个数**：私有那次 `write_gold` 是 7.8 秒一个 parquet（792 个共 1 小时 43 分）；公开这两次退化到**一小时写一个**，被杀之前 2.7 小时一个文件都没写出来。也就是说它不是在算，是在换页里空转。

改法（r1.0.19）：加 `PanelStore` / `SpillPanelStore` 面板暂存面 —— 求值边算边把面板交出去，`--spill-dir` 落到临时盘，`write_gold` 写完一个放一个。**产物逐字节不变**（暂存面只决定面板在被消费之前放在哪，用 pickle 原样进出）。

| | 改之前 | 改之后 |
| --- | --- | --- |
| gold 单进程峰值 RSS | csi1000 约 22 GiB（被 OOM 杀） | **6.93 GiB**（本次全链实测） |
| 私有 csi300 峰值 RSS | 约 7 GiB（同一形态外推） | **0.88 GiB**（不变性重建实测） |
| 落盘速度 | 7.8 s/因子（私有健康时）→ 3600 s/因子（换页中） | 约 2–5 s/因子 |
| 暂存盘占用 | — | csi300 约 5.1 GB（跑完自删） |

**并行度**：三宇宙**串行**（`--jobs 1`）。开了暂存之后单宇宙只要 1 GiB 上下，并行是跑得动的，但三宇宙的瓶颈是落盘不是 CPU，并行省不下多少，而 f01 是共用机 —— 宁可慢。整条链在 `flock $GB/locks/heavy.lock` 内跑，并用 `systemd-run --user --scope -p MemoryMax=20G` 封顶。

## 1. 每步：命令 / 用时 / 产出

| 步 | 命令 | 用时 | 产出 | 失败 |
| --- | --- | --- | --- | --- |
| universe | `--step universe` | 0s | `universe/universe_pit.parquet`（沿用 v1，sha256 `f1c4e6b20479…`） | 0 |
| gold `csi300` | `python -m reference.factor_exec --universe csi300 --spill-dir …` | 32.5 分钟 | 792 因子 / 792 个 parquet / 626,373,010 行 / 2.5 GiB | 0 |
| gold `csi500` | `python -m reference.factor_exec --universe csi500 --spill-dir …` | 58.6 分钟 | 792 因子 / 792 个 parquet / 1,035,358,864 行 / 4.2 GiB | 0 |
| gold `csi1000` | `python -m reference.factor_exec --universe csi1000 --spill-dir …` | 115.4 分钟 | 792 因子 / 792 个 parquet / 2,056,342,961 行 / 8.3 GiB | 0 |
| 互检（τ 原料） | `--step crosscheck` | 2.8 分钟 | 159 条可比 / 431,843 格 / 保留 414,857 | 0（见 1.1） |
| ε 面板 | `reference.make_epsilon_panel.build()` | 4s | `bt_input_csi300_v2.parquet` 984,960 行 | 0 |
| ε 三份实现 × 三频率 | `impl_v2_b{1,2,3}.py daily weekly monthly` | 4s | 9 份 `out_v2_b*_*.json` | 0 |
| ε 出带 | `epsilon_dual.compare_pairwise` | — | 3 份 `epsilon_dual_<freq>.json` | 0 |
| IC-ε 跑批 | `ops/ic_epsilon.py --universes <u> --state …`（`--ic-jobs 2`） | 70.3 分钟 | 样本 7,128 条（{'csi300': 2376, 'csi500': 2376, 'csi1000': 2376}） | 0 |
| IC-ε 出带 | `--aggregate-only --windows 2026-01-05..2026-06-30` | — | `ic_epsilon_dual.json` | 0 |
| calibration | `--step calibration` | 2s | `calibration.json` sha256 `cf45c2dfad84…` | 0 |

起 2026-09-07T06:47:44+00:00 / 止 2026-09-07T11:03:02+00:00。

### 1.1 失败清单

* `gold csi300`：三路后端 qlib_expression 644/644 / qlib_panel_loader 66/66 / qlib_kunquant_loader 82/82；失败 0 条
    * 全 NaN 的因子 0 个；非有限格 33,283 个（inf **按设计保留**，gold 是数据层，筛选留给评分层）；若用 float32 会溢出 2,469 格。
* `gold csi500`：三路后端 qlib_expression 644/644 / qlib_panel_loader 66/66 / qlib_kunquant_loader 82/82；失败 0 条
    * 全 NaN 的因子 0 个；非有限格 54,000 个（inf **按设计保留**，gold 是数据层，筛选留给评分层）；若用 float32 会溢出 1,651 格。
* `gold csi1000`：三路后端 qlib_expression 644/644 / qlib_panel_loader 66/66 / qlib_kunquant_loader 82/82；失败 0 条
    * 全 NaN 的因子 0 个；非有限格 112,861 个（inf **按设计保留**，gold 是数据层，筛选留给评分层）；若用 float32 会溢出 2,477 格。

**三宇宙的三路后端都是 644 / 66 / 82 满产，失败 0 条** —— 与私有那次同一形状。

* `crosscheck`：792 条里 159 条进得了互检，其余按类记账 —— same_engine 66, parse_fail 527, eval_fail 40, no_gold 0, no_overlap 0。**这不是「跑挂了 N 条」**：`same_engine` 是同一引擎没有第二实现可比，`parse_fail` / `eval_fail` 是第二实现那一侧解析不了 / 算不出来 —— 两者都是「没有可比对**象**」，不是本次运行的失败。
    * 与私有那次**逐项相同**：是（私有 same_engine 66, parse_fail 527, eval_fail 40, no_gold 0, no_overlap 0）。公开通道换的是行情，不是因子库，所以这一组数**本来就该一模一样** —— 它对上了，反过来说明互检读的确实是同一份因子库。

## 2. τ

| | 公开 | 私有（对照） |
| --- | --- | --- |
| τ | **0.983981** | 0.984006 |
| 参与的因子 | 141 | 141 |
| 参与的格 | 379,950 | 379,950 |
| 排除（算子冲突） | 13 条 | 13 条 |
| degenerate 剔除的格 | 16,986 | 16,987 |

**算子冲突名单是否不变：是**（两边都是 ['gtja_191.005', 'gtja_191.044', 'gtja_191.085', 'gtja_191.117', 'worldquant_101.004', 'worldquant_101.026', 'worldquant_101.029', 'worldquant_101.035', 'worldquant_101.038', 'worldquant_101.052', 'worldquant_101.066', 'worldquant_101.073', 'worldquant_101.084']）。

τ 的差 = 0.000025（相对 0.0025%）。卡 2.5 §10 的判据是「同一量级」——同一量级，结论不变。

## 3. ε（回测指标，按调仓频率分档）

| 频率 | 公开：可标定 / 超阈 / 无自由度 / usable | 私有（对照） |
| --- | --- | --- |
| daily | 9 / 0 / 0 / **True** | 8 / 0 / 1 / True |
| weekly | 8 / 1 / 0 / **False** | 8 / 1 / 0 / False |
| monthly | 6 / 3 / 0 / **False** | 6 / 3 / 0 / False |

* **weekly 超阈未出带**：['ann_return_gross']（私有：['ann_return_gross']）——按 2.2b 的纪律，超阈的**不写成 ε**，停下汇报。
* **monthly 超阈未出带**：['ann_return_gross', 'sharpe_net', 'total_cost']（私有：['ann_return_gross', 'sharpe_net', 'total_cost']）——按 2.2b 的纪律，超阈的**不写成 ε**，停下汇报。

* **daily 的可标定名单两边不同**：公开多出 ['win_rate_net']，公开少了 []。具体是 `win_rate_net` —— 私有通道三份实现在这个指标上**完全同值**，于是标成 `no_implementation_freedom`（按纪律「不得用其他指标的 ε 代填」，也就是不判）；公开通道上三份实现**真的分开了**，于是量到一条带。**这是多一条带，不是少一条** —— `daily.usable` 两边都是 True，分档结论不变。但它说明一件事：「`win_rate_net` 没有实现自由度」这句话是**这份数据的性质**，不是这三份实现的性质，换一份行情就不成立了。已登记票据。

**分档结论是否不变（daily 可用 / weekly 与 monthly 不可用）：是**。

weekly / monthly 标 `usable:false` 的**理由与私有通道同一条**：各自有指标的全对最大相对分歧超过 5% 的超阈线（签字建议值），按 `reference/epsilon_dual.py` 的第 3 条约束，超阈的不写成 ε 而是停下汇报 —— 过宽的 ε 会让 S7 失去判别力。低频档的调仓次数少、单次决策权重大，分歧被结构性放大，这一点两条通道都一样。

## 4. IC-ε（N-117，S4 的 IC 族带）

| | 公开 | 私有（对照） |
| --- | --- | --- |
| verdict | 4/5 个 IC 指标拿到带：['coverage', 'icir', 'mean', 'std']。超阈未出带：['positive_ratio']（按 2.2b 纪律，>5% 的相对分歧不像实现自由度，多半是声明没写清 —— 停下汇报）。双实现对构不成：['ci_low', 'ci_high']（qlib 口径没有 bootstrap 区间）。L3 逐指标按 status 取带，因此 S4 的 l3_pass 仍然算得出来。 | 4/5 个 IC 指标拿到带：['coverage', 'icir', 'mean', 'std']。超阈未出带：['positive_ratio']（按 2.2b 纪律，>5% 的相对分歧不像实现自由度，多半是声明没写清 —— 停下汇报）。双实现对构不成：['ci_low', 'ci_high']（qlib 口径没有 bootstrap 区间）。L3 逐指标按 status 取带，因此 S4 的 l3_pass 仍然算得出来。 |
| usable | False | False |
| 可用指标 | ['coverage', 'icir', 'mean', 'std'] | ['coverage', 'icir', 'mean', 'std'] |
| 未出带 | {'implausible': ['positive_ratio'], 'no_freedom': [], 'no_pair': ['ci_low', 'ci_high']} | {'implausible': ['positive_ratio'], 'no_freedom': [], 'no_pair': ['ci_low', 'ci_high']} |

| 持有期 | 指标 | 公开 ε | 私有 ε（对照） | 类型 |
| --- | --- | --- | --- | --- |
| 1 | coverage | 0.02544 | 0.02544 | relative |
| 1 | icir | 1.227 | 1.226 | absolute |
| 1 | mean | 0.01284 | 0.01284 | absolute |
| 1 | std | 0.02558 | 0.02559 | relative |
| 5 | coverage | 0.0254 | 0.0254 | relative |
| 5 | icir | 0.3304 | 0.3304 | absolute |
| 5 | mean | 0.002934 | 0.002938 | absolute |
| 5 | std | 0.0361 | 0.03612 | relative |
| 20 | coverage | 0.02544 | 0.02544 | relative |
| 20 | icir | 0.573 | 0.5729 | absolute |
| 20 | mean | 0.006743 | 0.006742 | absolute |
| 20 | std | 0.03822 | 0.03824 | relative |

## 5. 结构性结论核对（卡 2.5 §10）

| 结论 | 私有 | 公开 | 变了吗 |
| --- | --- | --- | --- |
| τ 的量级 | 0.984006 | 0.983981 | 否 |
| ε[daily].usable | True | True | 否 |
| ε[weekly].usable | False | False | 否 |
| ε[monthly].usable | False | False | 否 |
| 算子冲突名单 | 13 条 | 13 条 | 否 |
| IC 族可用指标 | ['coverage', 'icir', 'mean', 'std'] | ['coverage', 'icir', 'mean', 'std'] | 否 |

## 6. 复现

```bash
GB=/data/shared/genebench; cd $GB/repo && ulimit -n 8192
$GB/env/bin/python ops/run_public_chain.py --dry-run     # 只看要做什么
$GB/env/bin/python ops/run_public_chain.py               # 全链，已完成的步自动跳过
$GB/env/bin/python ops/run_public_chain.py --step gold --universes csi300 --force
# 查三个关键数
$GB/env/bin/python -c "import json;d=json.load(open('$GB/snapshots/public_v1/calibration.json'));print(d['tau']['value']);print({f:v['usable'] for f,v in d['epsilon']['by_frequency'].items()});print(d['epsilon']['ic_family']['usable_metrics'])"
```

**这条链不打网关**（gold / 互检 / ε / IC-ε 全部直读 parquet），所以不需要 `ops/gateway_lock.py`；与卡 1.2 同理由。

## 7. 私有通道数值不变（硬判据）

本卡改了 `reference/` 里五个模块 —— 按红线，必须拿出「私有通道产物逐字节不变」的证据，而不是「测试都绿」。

| 判据 | 做法 | 结果 |
| --- | --- | --- |
| 私有 gold 全量 | 用改动后的代码（**且开着 spill**）把私有 `csi300` 的 gold 重建到另一个根，与线上那份逐文件 sha256 比 | **792 个 parquet 全同**，differ 0 —— 通过 |
| 私有 `calibration.json` | 用改动后的代码重建到另一个路径，与线上那份逐字节比 | 顶层只有 `built_at` 变；换回原值后 sha256 = `6920dd1f…`，与线上完全一致 |
| 公开 gold 的新旧代码对照 | 被 OOM 杀掉那次（**旧代码路径**）已经写出的 3 个 `csi1000` parquet，与本次（新代码 + spill）重写的同名文件比 | **3/3 逐字节相同** |

三条合起来说的是同一件事：**暂存面只改变面板在被 `write_gold` 消费之前放在哪，不改变任何一个落盘的数**。这一条也有测试盯着（`ops/test_public_chain.py` 里「内存版与落盘版出来的 parquet 逐字节相同」「帧的 dtype/index/NaN/inf 原样进出」两条，变异「暂存面偷偷降精度」会打红）。

**证据文件**（都在 `$GB/scratch/1.1b/`）：`priv_orig.sha256` / `priv_rebuild.sha256` / `priv_gold.diff`（空）/ `prove_priv.log` / `prove_cal.py` 的输出 / `public_csi1000_oldcode.sha256` / `chain.rss` / `chain.log`。

