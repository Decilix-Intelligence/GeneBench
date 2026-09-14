# 数据卡：v1 冻结 qlib provider（卡 2.1a）

落点 `/data/shared/genebench/snapshots/public_v1/qlib_provider` · 通道 `public` · 冻结线 `2026-07-31` · 构建于 `2026-09-06T15:47:21+00:00`
· `files.sha256` 根 `f7dda2899071b07a…`（28605 个文件 / 362,864,621 字节） —— 2026-09-12 卡 A 换宇宙定义面之后的值；此前是 `561348660a3175b1…`

> **本文件由 `snapshots/qlib_provider.py::render_data_card()` 生成。**
> 直接改 `.md` 会在下次重建时丢掉 —— 要改口径请改代码。

> ⚠️ **这份卡是用私有通道的模板渲染的。**下面正文里有一批**写死的**实测数字
> （单位判据的 99.9843% / 14,581,977 行、与社区 release 的逐项比较、第 8 节的 P-1..P-4 计数）——
> **那些是私有通道的数**，不是这条通道的。凡是「本次构建现算」的数（日历、instruments、
> 归一化基准计数、digest）都来自本通道的 manifest，可以照读。
> **本通道自己的陷阱与对账数字见** `ops/reports/public/data_channel_notes.md`。

## 1. 为什么自建，而不是用现成的两份

签字裁定（方案 C），三重理由，按硬度排序：

1. **S3 主指标 Fid% 是被测因子值对 gold 的秩相关。** gold 若算自社区 bin、而 agent 拿到的是网关快照，任何不一致都**无法归因**是 agent 错还是数据本来就不同 —— 主指标不可解释，并会污染「跨后端一致性」这个署名指标。
2. **τ 是要签字的数字**，标定口径必须与评测口径是同一份数据。
3. 本方案下 provider 日历里**物理上没有**冻结线之后的交易日 —— 红线 7 从「每次调用的自觉」变成**结构保证**。实测 qlib 自己的 `D.calendar()` 看到的上界就是 `2026-07-31`。

「先 A 后 C」的折中**未采纳**：两版 τ 只有一版能用，且日后容易被误引。

## 2. 单位（实证得出，不是按文档假设）

| 列 | 单位 | 与 tushare 原生 | 与社区 release |
| --- | --- | --- | --- |
| `amount` | **元** | 原生是千元，湖已归一 | 社区仍是**千元**，差 **1000×** |
| `volume` | **股** | 原生是手(100 股)，湖已归一 | 社区是**手**，差 **100×** |
| `vwap` | 元/股 | — | 同 |

**判据不是查文档，是这条硬判据**：`low <= amount/volume <= high` 的行占比。
全表 14,581,977 行、相对容差 1e-06 下 **99.9843%**，逐年均 > 99.6%，
中位 `vwap/close ≈ 1.0` 且逐年稳定 —— 说明单位没有中途变过。
若单位按 tushare 文档假设直接相除，这个比率会是 **0%**（差 10 倍）。

## 3. `vwap` 口径

```
vwap_raw = amount / volume          # 原始值
vwap     = vwap_raw × factor        # 与其余价格用同一复权因子
volume <= 0 或缺失  ->  vwap = NULL # 不得 inf、不得 0
```

**判别力披露**：实测全表 `volume <= 0` 的行 **0 条**，
所以这条守门在当前数据上是**空转**的。这里不假装它被测过 —— 
`ops/test_qlib_provider.py::test_inv_vwap_is_null_never_inf_when_volume_nonpositive` 改用**构造数据**直接打 `_adjust()` 来证明守门代码本身有效。
（它对应的是我们要测 agent 的 S3-ROB-02「非有限值安全传播」，自己的 gold 里先别犯。）

## 4. 复权口径

```
L_c    = max{ t <= 冻结线 : adj_factor(c, t) 存在 }
factor = adj_factor(c, t) / adj_factor(c, L_c)

open/high/low/close/vwap  = 原始价 × factor      # 后复权，以冻结线重定基
volume                    = 原始股数 / factor    # 拆股会让股数跳变，除掉才连续
amount                    = 原始金额（不复权）   # 钱就是钱
```

遵循 qlib 惯例：Alpha158/360 的表达式假定 `$close` 是复权价，存原始价会改变全部因子语义。由构造直接得到两条不变式：

- `$close / $factor == 原始收盘价`（qlib 自己的口径）
- **`vwap × volume == amount`**，且**与复权无关** —— 白得的内部一致性检查，任何一处分派写反它立刻红。

**归一化基准定死为冻结线**：`factor(2026-07-31) = 1`，即冻结线当天的价 == 原始价。
实测 **3354 只**票在冻结线当天在市，基准就是冻结线。

⚠ **必要偏离**：另有 **221 只**票在冻结线前已退市/停更，「冻结线当天」对它们根本不存在。
这些票以**自身最后一个有 `adj_factor` 的交易日**为基准（该日 `factor = 1`）。逐票基准落在 `norm_base.parquet`，是产物的一部分。

## 5. instruments

取自卡 1.1 的 `universe_pit` **canonical** 口径，不用社区名单 —— 卡 1.1 的产出由此正式成为卡 2.1 的输入，数据面闭环。

| 宇宙 | 区段行数 | 去重码数 | 其中 `ambiguous` |
| --- | ---: | ---: | ---: |
| `csi300` | 1,507 | 825 | 1 |
| `csi500` | 3,025 | 1,738 | 2 |
| `csi1000` | 4,455 | 2,839 | 1 |
| `all` | 3,575 | 3,575 | 0 |

**`ambiguous` 区段照常保留（共 4 条）。** provider 是数据层，不做筛选；排除动作留在任务生成层。
provider 静默丢弃它们的话我们就有了两个不同的宇宙，且日后无法测「在模糊区段上会发生什么」。

## 6. calendar，以及它与卡 1.4 的差别

`calendars/day.txt` = `trade_cal(SSE, is_open=1)` 且 `<= 2026-07-31`，共 **4,269** 天（2009-01-05 … 2026-07-31）。
**不出 `day_future.txt`** —— 它在 qlib 里就是「允许求值到未来」的开关。

**这与卡 1.4 不冲突，两处规则不同、各自的理由是**：

| | 快照表 `tables/trade_cal.parquet` | provider `calendars/day.txt` |
| --- | --- | --- |
| 内容 | **保留** 153 行未来日历（到 2026-12-31） | 截到冻结线 |
| 理由 | capture_time 语义；T+N 对齐需要知道 8 月 3 日是不是交易日 | 它决定**因子表达式能在哪些日子求值**；冻结线之后本来就没有 bar 可算 |

`ops/test_qlib_provider.py::test_03b_no_future_calendar_and_snapshot_still_has_one` 把这个差别钉住：谁把其中一处「统一」掉，那条就红。

## 7. 可用求值右端（会静默污染结果的那条约束）

持有期 {1,5,20} 日下，最后 h 个交易日的前向收益在冻结线内**不完整**。
在 t 日收盘求值、收盘后调仓、持有 h 日 → 需要 `t+h` 日的收盘价，故 `t <= cal[-(h+1)]`：

| 持有期 | 可用求值右端 | 距冻结线 |
| ---: | --- | ---: |
| 1 日 | **2026-07-30** | 1 个交易日 |
| 5 日 | **2026-07-24** | 5 个交易日 |
| 20 日 | **2026-07-03** | 20 个交易日 |

三个数由 `trade_cal` 现数（`evaluation_right_edge()`），**不写死**。
**必须进 `calibration.json` 并在评分器里硬拦** —— 不拦的话，20 日 IC 会在末段用截断/缺失的前向收益计算，被静默偏置，**而且从指标数值上看不出来**。

## 8. 已知缺陷与边界

| # | 事实 | 影响 | 处置 |
| --- | --- | --- | --- |
| P-1 | `vwap` 越出 `[low, high]` 的行（容差 1e-6 后）—— 主因是源侧 `amount` 被舍到整数元，集中在北交所小额成交 | 131 条依赖 `vwap` 的因子 | **不静默修补**：网关只发 `amount`/`volume`，agent 自己算 vwap 也会得到同一个数；改了 gold 就与执行面不同源。计数与样例见 `ops/acceptance/card_2.1a_full_verify.json`，登记 N-20 |
| P-2 | 3 个码（`000022.SZ` `000043.SZ` `300114.SZ`）**有价无名单** —— 代码变更注销，不在 `stock_basic` | 有 features、不在任何 instruments 文件 | 保留 features（丢了会让 `code_alias` 的适配赛道没数据），不塞进名单（会破坏第 ④ 条验收） |
| P-3 | 2 个码（`000805.SZ` `000787.SZ`）**有名单无价** | 在 `all.txt` 里但无 features | 保留在名单（`universe_pit` 逐区段相等是硬验收），qlib 读出来是 NaN |
| P-4 | bin 是 **float32** | 反算原始价有 ~1e-7 的相对误差 | 验收用 1e-5 相对容差；实测最大偏差见报告 |

## 9. 与社区 release 的差异清单（跨源比对时会踩的）

| 维度 | 我们 | 社区 `releases/2026-08-26` |
| --- | --- | --- |
| 日历上界 | 2026-07-31（= 冻结线） | 2026-08-26（越线 18 天） |
| `day_future.txt` | **无** | 有，到 2026-12-31 |
| 价格归一 | `factor(冻结线) = 1` | 每票**首日 close = 1** |
| `amount` | 元 | **千元**（1000×） |
| `volume` | 股，且 `/factor` | **手**，且 `/factor`（100×） |
| 字段数 | 8（7 个 required + `factor`） | 10（多 `adjclose` `change`） |
| instruments | `universe_pit` canonical | 社区自带，含 6 个指数与悬空成分 |

`adjclose` 在「以冻结线重定基」下与 `close` 逐值相同，`change` 可由 `close` 求出 —— 都不出，少一个字段就少一处会漂的口径。

## 10. 复现

```bash
export GENEBENCH_ROOT=/data/shared/genebench
cd $GENEBENCH_ROOT/repo && ulimit -n 8192
$GENEBENCH_ROOT/env/bin/python -m snapshots.qlib_provider
$GENEBENCH_ROOT/env/bin/python -m pytest ops/test_qlib_provider.py -q
$GENEBENCH_ROOT/env/bin/python ops/acceptance/card_2_1a_full_verify.py
```

