# 数据卡：gold 因子面板（卡 2.1b）

落点 `/data/shared/genebench/snapshots/v1/gold_factors` · 窗口 `2015-05-29` … `2026-07-31` · provider digest `54fdda39c60bf848…`

> **本文件由 `ops/mk_gold_data_card.py` 生成。** 直接改 `.md` 会在下次重建时丢。

## 1. 规模

| 宇宙 | 交易日 | 行数 | 字节 | 因子 | 三路后端失败 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `csi300` | 2,716 | 626,373,405 | 2,639,585,197 | 792 | 0 |
| `csi500` | 2,716 | 1,035,353,925 | 4,494,216,396 | 792 | 0 |
| `csi1000` | 2,716 | 2,056,343,886 | 8,873,270,989 | 792 | 0 |

每因子一个 parquet，长表 `(date, code, value)`，`value` 为 **float64**，只保留当日在成分内的格。

## 2. ⚠ 能力边界：这批 gold 算不出什么（N-23）

**这一节必须在 M3 出题前被看见** —— 否则 S5/S6/S7 的题面可能要求系统交付**我们自己都算不出来的指标**，那题就不成立。

| 指标族 | 能不能算 | 原因 |
| --- | :---: | --- |
| 年化收益 / 波动 / Sharpe / Sortino / MDD / Calmar / 换手 / 胜率 | ✅ | 都从组合逐日收益自己算，不经过基准 |
| IC / RankIC / 分位单调性 / Top-Bottom spread | ✅ | 只需要因子值与前向收益 |
| **IR / alpha / 超额收益 / 信息比率** | ❌ | **v1 provider 没有指数标的** —— instruments 取自 `universe_pit`，里面只有股票，`SH000300` 不存在 |
| 卡 2.1 里 5 条 `point_in_time_benchmark_or_fama_french_inputs_unavailable` 的 blocked 因子 | ❌ | 同源：需要 MKT/SMB/HML 序列 |

**卡 2.2b 的参考回测用「等权宇宙收益」当基准，那是权宜，不是 v1 的正式基准定义。**
它只为让 qlib 的 `PortfolioMetrics` 能初始化；ε 用到的指标**没有一项经过基准**。
**不要让它悄悄变成正式基准** —— 要正式基准就得先把指数写进 provider（会改 provider 的 sha256）。

## 3. ⚠ 检查的覆盖限度：这批数据里可能还有我们看不见的缺陷

双实现互检是我们**唯一**能照出「参考实现算错了」的手段。它的覆盖是**不完整的**：

| | 条数 |
| --- | ---: |
| KunQuant 后端的可执行因子 | 82 |
| **其中有第二实现、可被互检裁定的** | **51** |
| **无第二实现、互检看不见的** | **31** |

**已经在可比的那 51 条里查出 1 条真缺陷**（`worldquant_101.038`，见第 4 节）。**那 31 条里若有同类字段错位，当前方法照不出来。**

为查这类缺陷写过一个 (算子, 字段实参) 比较器，扫全部 82 条。**它的第一版比的是字段*集合*，对「同一组字段换了位置」恒返回 0** —— 是一次空转的扫描，已作废；现行版本先在 `.038` 上验过判别力才出结论。即便如此，它对没有第二实现的 31 条仍然只能做静态比对，不能裁定数值。

**读这批 gold 的人必须知道这条限度。** 登记在 N-22。

## 4. 算子语义与实现缺陷的标注

两类问题**表现完全一样**（能算出数、能跑通、数值看起来正常），处置**不同**：

| 类别 | 条数 | 含义 | 处置 |
| --- | ---: | --- | --- |
| `operator_convention_suspect` | **23** | 算子语义未被因子定义绑定，两个引擎的读法都合法 | gold 标注存疑；**S3 出题避开**；移出 τ 样本 |
| `reference_implementation_defect` | **1** | 参考实现**读错了输入字段**，一方就是错的 | **gold 不可用**；移出 τ 样本；修正登记 N-24 |

- **`worldquant_101.038`** —— KunQuant 的 alpha038 在 ts_rank 的实参上用了 open，而源方言公式写的是 close —— 字段错位，与归一化约定无关。

下游**必须**调 API 而不是抄名单：

```python
from reference.operator_flags import tasks_should_avoid, gold_unusable
tasks_should_avoid()   # S3 出题要避开的（约定存疑）
gold_unusable()        # gold 值根本不可用的（实现缺陷）
```

## 4b. A↔B 的**未归因残差**，与**知情保留**的欠定项（都不是未解决缺陷）

**参考回测 A（qlib TopkDropout）与三份独立实现 B 的 `ann_return_gross` 差 **22.69%**，而 `turnover_two_way_mean` 只差 **0.51%**。**

换掉的**金额**几乎一样、换的**标的**不同。**这个 22.69% 是「未归因残差」——成因未知。**

本卡此前写的是「定位到声明里的开放歧义 **A-1**（`n_drop` 卖「持仓中信号最差的」还是「已跌出目标组合的」）」，**该归因已于 2026-09-03 撤回**：它是**排除法**得出的（排除了费用口径与 `risk_degree` 后把剩余项安给 A-1），**从未做过隔离实验**。

**隔离实验反而排除了 A-1。** 在**同一份实现内部**切换 `sell_rule` 的两种读法、其余一切不变，三份 B 的 `ann_return_gross` 相对差只有 **0.38%–0.45%**（daily ε=0.237%，B1 5 项 / B2 6 项 / B3 6 项超带 → **material**）—— **与 22.69% 相差约 50 倍，A-1 解释不了这个数。**

**这个残差仍是知情保留的，不是 bug，不要顺手修掉。** A 与 B 完全收敛没有独立价值（daily 档 ε 已 usable）；变的只是**我们不再声称知道它的成因**。**A-1 也仍是知情保留的欠定项**，凭它自身 material 的实测效应当 S7 首要题源（N-25）—— 但它**不再**被当作 22.69% 的解释。

`ops/test_underdetermination_guard.py` 锁的是**这个未归因残差仍然存在**；它变红说明有人改了 A 或 B，先去查什么变了。

## 5. 数值口径

- **float64，不是 float32**。首版用 float32，pandas 只发一句 `overflow encountered in cast`，产物层完全看不见。秩相关**对饱和不是不变的**（一批大数被压成同一个 `inf` 会并列，Fid% 虚高）。
| 宇宙 | 若用 float32 会溢出的格 | 真 `inf` 的格（参考实现的诚实输出）|
| --- | ---: | ---: |
| `csi300` | 2,469 | 33,310 |
| `csi500` | 1,649 | 53,161 |
| `csi1000` | 2,477 | 112,916 |

- `inf` **保留不筛** —— 那是参考实现的诚实输出（除零 / 幂爆炸），筛选留给评分层（同 `ambiguous` 区段的处理原则：数据层不做筛选）。
- 暖机 600 天，与钉版本 loader 的默认一致。

## 6. 求值右端

gold 因子值算到冻结线当天；**右端约束是给前向收益的**，由评分器硬拦：

| 持有期 | 可用右端 |
| ---: | --- |
| 1 日 | `20260730` |
| 5 日 | `20260724` |
| 20 日 | `20260703` |

## 7. 复现

```bash
export GENEBENCH_ROOT=/data/shared/genebench
cd $GENEBENCH_ROOT/repo && ulimit -n 8192
$GENEBENCH_ROOT/env/bin/python -m reference.factor_exec --universe csi300 --start 2015-05-29 --end 2026-07-31
$GENEBENCH_ROOT/env/bin/python -m reference.factor_exec --universe csi500 --start 2015-05-29 --end 2026-07-31
$GENEBENCH_ROOT/env/bin/python -m reference.factor_exec --universe csi1000 --start 2015-05-29 --end 2026-07-31
$GENEBENCH_ROOT/env/bin/python -m reference.operator_flags
$GENEBENCH_ROOT/env/bin/python ops/mk_gold_data_card.py
```

