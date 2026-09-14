# 数据卡总入口（八份）

> **这一页回答三个问题**：哪张卡描述哪份数据、这份数据属于**私有**还是**公开**通道、
> 以及每张卡的六个固定字段（源 / 窗口 / 覆盖 / 已知陷阱 / 缺口 / 校验和）分别是什么。
>
> **为什么统一表在这里、而不是逐卡改成同一个模板**：八份里有 **六份是代码生成的**
> （下表「生成器」列），`.md` 手改会在下次重建时丢；第七份 `public_channel.md` 由
> `ops/test_recon_public.py` 逐个数字核出处，往里加数就要同时加出处注释。
> 所以本入口把六字段**对齐在这一层**，逐卡正文保持各自生成器的格式 —— 要改逐卡格式
> 就得改六个生成模块，那是另一张卡的事（已登记 `ops/tickets_inbox/6.3.md`）。

---

## 0. 两条数据通道

GeneBench 的同一套题跑在**两条互不覆盖**的数据通道上。**同一道题在两条通道上不是同一道题**
（数据通道是四条版本轴之一，见 [`VERSIONS.md`](../../VERSIONS.md)）。

| 通道 | 落点 | 行情来自 | 谁能拿到 | 覆盖它的数据卡 |
| --- | --- | --- | --- | --- |
| **私有** `private` | `$GENEBENCH_ROOT/snapshots/v1` | 内网数据湖（tushare 派生） | 只在 f01 内网 | `qlib_provider` · `universe_pit` · `tradability` · `gold_factors` · `s7_backtest_gold` · `fixture_s4_eco_pool_v1` · `fixture_s6_signals` |
| **公开** `public` | `$GENEBENCH_ROOT/snapshots/public_v1` | baostock 公开行情 | 随发布包分发（**许可原文到位后**，见 [`DATA_LICENSE`](../../DATA_LICENSE)） | `public_channel` |

**两条通道共用的那一块**：宇宙定义面（谁在指数里）**只有私有一份**——
baostock 没有指数成分历史，公开通道的 `instruments/` 是私有 `universe_pit` 的派生物随包发。
它的再分发依据**尚未确认**（`DATA_LICENSE` §5）。

**答案面不在这里**：`reference/` / `scorer/` / `gold/` 的任何内容都不进公开包、不进执行面
（红线 2）。下表里 `gold_factors` 与 `s7_backtest_gold` 描述的是**我们怎么算 gold**，
不是发给被测系统的输入。

---

## 1. 八张卡的统一速览

六个字段的含义固定如下，逐卡正文里更细的口径以正文为准：

* **源** —— 数据从哪来（上游服务 / 上游表 / 由哪段代码派生）；
* **窗口** —— 时间跨度，右端一律不得越过冻结线 `2026-07-31`（红线 3）；
* **覆盖** —— 规模与范围（多少票 / 多少天 / 多少行 / 哪几个宇宙）；
* **已知陷阱** —— 照直觉用会得到错结果的地方，逐卡正文里有完整一节；
* **缺口** —— 这份数据**算不出什么**（不是缺陷，是边界）；
* **校验和** —— 拿什么值确认「我手上这份和卡上写的是同一份」。

| 卡 | 通道 | 源 | 窗口 | 覆盖 | 已知陷阱（正文节） | 缺口 | 校验和 | 生成器 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [`qlib_provider.md`](qlib_provider.md) | 私有 | 数据湖 `daily` / `adj_factor` → 自建 qlib bin provider | … → `2026-07-31` | 三宇宙并集 × 8 字段的 bin 树 | §2 单位（`amount` 元 / `volume` 股，与社区 release 差 1000× / 100×）、§4 复权口径、§7 可用求值右端、§9 与社区 release 的差异清单 | §8 已知缺陷与边界；无指数标的 | `files.sha256` 根（卡首行 digest） | `snapshots/qlib_provider.py::render_data_card` |
| [`universe_pit.md`](universe_pit.md) | 私有 | 源A 湖 `index_weight` 月末快照 ∪ 源B qlib `instruments`，∩ 源C 在市窗口 | `2009-01-05` → `2026-07-31` | csi300 / csi500 / csi1000 + 并集 | §3 两源分歧与容忍口径、§5.1 月内调整被抹平、§5.2 左右截断语义、§5.3 第三源不是历史注册表 | §5 已知局限；§6 不该拿它做什么 | 机器可读版 `ops/universe_pit.json`；两份中间产物 parquet 的 sha256 记在对账报告 | `snapshots/universe_build.py::render_data_card` |
| [`tradability.md`](tradability.md) | 私有 | 湖 `daily` + `suspend_d` + `stk_limit` + `trade_cal` | `2009-01-05` → `2026-07-31` | 15,073,606 行 / 4,269 个交易日 / 五档互斥 `status` | 「`suspend` 与 `no_data` 的分界」一节、「无涨跌幅限制」哨兵、「不要用 `stk_limit.pre_close`」、「日历只有 SSE」 | 「不该拿它做什么」一节；验收切片 `tradability_acceptance` **不许**拼进任何窗口 | 按年分区 parquet；生成时间写在卡首 | `snapshots/tradability.py` |
| [`gold_factors.md`](gold_factors.md) | 私有（**答案面**） | 冻结 provider + 三路因子后端（`qlib_expression` / `qlib_kunquant_loader` / …） | `2015-05-29` → `2026-07-31` | 三宇宙 × 792 因子，每因子一个 parquet 长表 | §3 检查的覆盖限度、§4 算子语义与实现缺陷标注、§4b 未归因残差与知情保留 | §2 能力边界：**IR / alpha / 超额 / 信息比率算不出**（v1 provider 没有指数标的） | provider digest（卡首行）+ 逐因子 parquet | `ops/mk_gold_data_card.py` |
| [`s7_backtest_gold.md`](s7_backtest_gold.md) | 私有（**答案面**） | 三份独立回测实现 B1/B2/B3 中的 **B2**，输入是 gold 信号 + 冻结面板 | 五道 S7 题各自的声明窗口（全部 `daily`） | 每题一份 `oracle_artifact.json` + `ledger.parquet` | §4 两条会被误当成缺陷的事；`ann_return_net` 接近 0 导致相对差看起来大 | ε 与 gold **同一次标定**，换 gold 引擎必须重标 ε | `snapshots/v1/epsilon/impl_v2_b2.py`（冻结件）；§5 复算命令 | 手写 |
| [`fixture_s4_eco_pool_v1.md`](fixture_s4_eco_pool_v1.md) | 私有（**题面输入**） | 从三个因子族按 ID 等距抽样（**不看 IC**，避免选择泄漏） | `2026-01-05` → `2026-06-30` | csi300，30 条因子 / 1,003,974 行 | 抽样规则本身就是陷阱防线：按 IC 选会造成选择泄漏 | 排除了全窗 degenerate 与覆盖率 < 0.95 的因子 | sha 写回 `genetask/params/v1.0-smoke40.yaml`（参考轴 r1.0.7 记因） | `reference/make_fixtures.py::write_pool_card` |
| [`fixture_s6_signals.md`](fixture_s6_signals.md) | 私有（**题面输入**） | S5 oracle 在 `gtja_191.001 × csi300` 上的 gold 输出，及其稀疏化派生 | `2026-05-06` → `2026-07-31` | 两份信号：稠密 `s5_gtja001_csi300_v1`、稀疏 `s6_sparse_coverage_csi300_v1` | 稀疏版**每第 7 个交易日**只留 3 只 —— 那些日子在 `max_weight=0.1` 下**构造无可行解**，是判据的输入不是缺陷 | 只覆盖 S6 的五道题 | sha 写回 params（同上） | `reference/make_fixtures.py::write_signal_card` |
| [`public_channel.md`](public_channel.md) | **公开** | baostock `query_history_k_data_plus` / `query_adjust_factor` / `query_stock_basic` | `20090105` → `20260731` | 见卡 §1（每个数带 `src` 出处注释） | §3 不服务北交所、§4 停牌是「有行 + `tradestatus=0`」、§5 量额单位、§6 复权口径（最深的坑）、§7 涨跌停要自己推（已知误差 4 行） | §8 缺失日；宇宙定义面推不出来，只能随包发 | `public_v1/tables/build_info.json` + 包内 `SHA256SUMS` | 手写（`ops/test_recon_public.py` 逐数核出处） |

---

## 2. 怎么核「我手上这份和卡上写的是同一份」

```sh
GB=/data/shared/genebench; PY=$GB/env/bin/python; cd $GB/repo

# 私有 provider 的 digest 与规模（卡首行那一串就是它）
sed -n '1,6p' ops/data_cards/qlib_provider.md

# 公开通道的构建指纹（窗口 / 票数 / 构建时刻）
$PY -c "import json, genebench_config as c; \
        print(json.load(open(c.SNAPSHOTS_PUBLIC / 'tables' / 'build_info.json')))"

# 公开发布包：逐文件校验和
sha256sum -c SHA256SUMS        # 包内自带
```

发布包与两条形态（下载 / 自建）的完整判据见
[`ops/reports/public/release_forms.md`](../reports/public/release_forms.md)，
许可状态见 [`DATA_LICENSE`](../../DATA_LICENSE)。

---

## 3. 谁在读这些卡

| 读者 | 从哪张卡开始 |
| --- | --- |
| 想跑一遍 benchmark 的外部用户 | `public_channel.md` → `ops/reports/public/release_forms.md` |
| 想知道「这个数是怎么来的」 | `qlib_provider.md`（行情）→ `universe_pit.md`（宇宙）→ `tradability.md`（能不能交易） |
| 想复现 gold / τ / ε | `gold_factors.md` → `s7_backtest_gold.md` → `ops/specs/GeneBench秩相关与标定口径_v1.md` |
| 想知道某道题的输入是什么 | `fixture_s4_eco_pool_v1.md` / `fixture_s6_signals.md` |

指标口径本身不在数据卡里，在
[`ops/specs/metrics_as_implemented_v1.md`](../specs/metrics_as_implemented_v1.md)
（规格怎么说 / 实现在哪 / 现在真的在判吗）。
