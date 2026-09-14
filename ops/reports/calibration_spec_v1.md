# `calibration.json` 口径清单（逐条核对用）

落点 `/data/shared/genebench/snapshots/v1/calibration.json` · 生成于 `2026-09-01T08:54:59+00:00` · schema v1
· provider digest `54fdda39c60bf848…`

**整份配置可用于评分：`False`** —— 未决项：['epsilon: 标定源失效，等换源后回填（E-1 / D-05）']

> 由 `ops/render_calibration_spec.py` 生成。 每一条都有对应的会红的断言，见 `ops/test_calibration.py`（16 项）。

## 第一批冻结（对接决定 / `ops/specs/README.md` 第 4 条）

| # | 冻结项 | calibration.json 里的值 | 落位 |
| ---: | --- | --- | :---: |
| 1 | 分位数 | `10` | ✅ |
| 2 | 平局处理 | `average` | ✅ |
| 3 | 权重 | `equal` | ✅ |
| 4 | 调仓时点 | `after_close` | ✅ |
| 5 | 持有期 | `[1, 5, 20]` | ✅ |
| 6 | Sharpe 年化 | `√252`，gross/net **分开报** = `True` | ✅ |
| 7 | Sortino MAR | `0.0` | ✅ |
| **8** | **turnover 双记** | `one_way=True` · `two_way=True` · `both_required=True` | ✅ |
| 9 | IC 汇总 | `['mean', 'std', 'ICIR', 'positive_ratio', 'coverage', 'CI']`；positive_ratio 与 coverage 均为必报 | ✅ |
| **10** | **不确定性用 block-bootstrap** | `moving_block_bootstrap`，重抽样 `1000`，CI `0.95`，种子 `20260731`，块长规则 `ceil(n_obs ** (1/3))`，作用于 `['IC', 'RankIC', 'quantile_spread', 'alpha', 'sharpe']` | ✅ |
| 10b | Newey–West 的地位 | `enabled=True`，角色写死为「并列报告，不得替代 block-bootstrap」 | ✅ |

**第 8 与第 10 是你点名最容易漏的两条**：

- turnover 双记 —— 不只是配置里写了两个 `True`，ε 的指标表里**同时存在** `turnover_one_way_mean` 与 `turnover_two_way_mean` 两项实测值（不是一项换算出来的），`test_freeze1_turnover_is_double_recorded` 盯着这一点。
- block-bootstrap —— 参数全在（方法/重抽样数/CI/种子/块长规则/作用对象），且 `newey_west.role` 里带「不得替代」四个字，`test_freeze1_uncertainty_is_block_bootstrap_not_only_newey_west` 直接断言这四个字。

## 第二批冻结（F-1…F-5）与 τ

| 项 | 值 |
| --- | --- |
| F-1 算法 | 逐交易日截面 Spearman（tie 平均法），再对时间取分布 |
| F-2 τ 分位 | P10，`pooled_not_time_averaged = True` |
| F-4 degenerate 阈值 | 唯一值数 < `5%` × 截面标的数；最小截面 `20` |
| **τ** | **`0.984006`** |
| τ 的样本 | 141 因子 / 379,950 格（可比 159 条，排除 13 条算子冲突）|
| τ 的窗口 | `csi300` 2015-05-29 … 2026-07-31 |
| degenerate 剔除方向 | 剔除**使 τ 上升** = `True`，共剔 16,987 格 |

## 求值右端（硬拦）

| 持有期 | 可用右端 |
| ---: | --- |
| 1 日 | `20260730` |
| 5 日 | `20260724` |
| 20 日 | `20260703` |

`must_hard_block = True`；来源：snapshots.qlib_provider.evaluation_right_edge()，从 trade_cal 现数

## 算子语义冲突（N-21 → C）

- gold 标注「算子约定存疑」：**24 条**
- S3 出题必须避开：`True`，API `reference.operator_flags.tasks_should_avoid()`
- 证据：`ops/specs/operator_semantics_conflicts.md`

## ε —— **待回填**

- 状态：`source_ineffective_awaiting_decision`，可用 = `False`
- 方法：`cross_library_version`，倍数 ×1.5
- 环境：4 组，pyqlib 全程钉住 `0.9.8.dev32`

| 组合 | numpy | pandas |
| --- | --- | --- |
| `baseline` | 1.26.4 | 2.2.3 |
| `pandas_minor` | 1.26.4 | 2.1.4 |
| `numpy_pandas_minor` | 1.25.2 | 2.0.3 |
| `pandas_major` | 1.26.4 | 1.5.3 |

- **最大相对极差 `8.53e-14`**，有效性下限 `1e-10`，float64 相对精度 `2.22e-16`
- 判定：**标定源失效**：跨这些库版本的分歧全部落在 float64 舍入量级，ε 会退化成一条比特级相等的验收断言。与 E-1 的「五种子极差为 0」同形。
- 完全确定性的指标：`['win_rate_net']`（单独标注，**不代填**）
- 浮点噪声地板（副产品）：`8.53e-14`（相对）—— 无论 ε 日后改用哪个标定源，它都必须**明显高于**这个地板，否则量到的还是舍入。

> **ε 尚不可用**：跨库版本的分歧全落在 float64 舍入量级，标定源失效（E-1 / D-05）。calibration.json 的其余部分（含 τ）已定稿，ε 一栏等换标定源后回填，**不得用当前这组机器精度数字代替**。

