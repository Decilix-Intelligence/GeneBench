# 数据卡：S7 回测 gold（实现 B2）

**产物**：`reference/tasks/<set>/s7-*/gold/{oracle_artifact.json, ledger.parquet}`
**引擎**：`reference/b2_engine.py` → 冻结的 `snapshots/v1/epsilon/impl_v2_b2.py`
**裁定**：N-83（2026-09-05）—— gold 必须遵守书面契约；qlib 有未归因偏离（N-39）
且偏离清单未成，**不能定义 gold**；qlib 作对账参照。

---

## 0. 速览（六字段，与 `ops/data_cards/README.md` 同一张表结构）

| 字段 | 值 |
| --- | --- |
| **源** | 三份互相独立的回测实现 B1/B2/B3 中的 **B2**；输入 = gold 信号 + 冻结面板 |
| **窗口** | 五道已发布 S7 题各自声明的窗口，**全部 `daily`** 频率 |
| **覆盖** | 每题一份 `oracle_artifact.json` + `ledger.parquet` |
| **已知陷阱** | §4 两条会被误当成缺陷的事；`ann_return_net` 本身接近 0，相对差看起来大不代表实现有问题 |
| **缺口** | ε 与 gold **出自同一次标定** —— 换 gold 引擎就要重标 ε；`weekly` / `monthly` 档的 ε `usable=false` |
| **校验和** | 冻结件 `snapshots/v1/epsilon/impl_v2_b2.py`；复算命令见 §5 |

> 通道：**私有**（答案面）。八张卡的总入口与统一对照表见
> [`README.md`](README.md)。

---

## 1. 为什么是 B2，以及 B1/B3 是什么关系

`ops/specs/backtest_contract.md` v3 是三份**互相独立**实现的唯一输入。
它们没有读过 qlib，也没有读过彼此。日频（已发布的五道 S7 题**全部**声明 `daily`）实测：

| 指标 | B1 | B2 | B3 | 最大相对差 |
| --- | --- | --- | --- | --- |
| `ann_return_gross` | 0.05534877102065461 | 0.05543641860012283 | 0.05543641860012283 | 1.58e-03 |
| `ann_return_net` | 0.0016293442565344929 | 0.001712044430068893 | 0.001712044430068893 | 4.83e-02 |
| `ann_vol_net` | 0.23205557579081026 | 0.23206710730171387 | 0.23206710730171395 | 4.97e-05 |
| `max_drawdown_net` | -0.529119542384421 | -0.5290574251835538 | -0.5290574251835536 | 1.17e-04 |

**B2 与 B3 在日频下逐位相同**（9 项里 5 项完全相等，其余的差在 1e-16 量级）；
**B1 是那个异类，而它与另外两份的差就是 ε 的标定量本身**
（`snapshots/v1/epsilon/epsilon_dual_daily.json`，`multiplier` 1.5）。

所以选 B2 当 gold 不是在三个候选里挑一个"更准的"——
B2/B3 给出同一个答案，B1 给出另一个，ε 正是用来覆盖这段差的。
**ε 与 gold 出自同一次标定，换 gold 引擎就要重标 ε。**

`ann_return_net` 三份之间差 4.8%，是因为它本身接近 0（1.7e-03）——
ε 对它已改用**绝对**容差（1.24e-04）。不是缺陷，记在这里免得下次当 bug 查。

**周频 / 月频不可用**：`epsilon_dual_{weekly,monthly}.json` 的 `usable` 都是 false
（月频 `ann_return_net` 三份 0.05396 / 0.05410 / 0.04308，相对差 **20.4%**；
与 N-38 记的「b3 没有 `first_rebalance_day` 的首日建仓步骤」一致）。
`config_from_declared` 对这两档直接报错 —— gold 出得来但判不了（N-85）。

## 2. 包装做了什么、没做什么

**没做**：没有重写 B2。重写等于毁掉它的独立性，而 ε 量的正是"两份独立实现同一份声明会差多少"。

**做了**两层内存补丁，都带门：

| 补丁 | 内容 | 中性证明 |
| --- | --- | --- |
| P-SELL | `sell_rule` 的两种读法做成开关 | 打完的源码 sha256 必须等于 `0dd4a45a976eda24…` —— 这个值是 2026-09-03 materiality screen 记在 `ops/reports/materiality_s7_sell_rule.json` 里的。**逐字节相同 = 与那次实测用的是同一份补丁** |
| LEDGER | 逐日记 `cash` / `mv` / `r_gross` / `r_net` | 全部是赋值语句；`s7_b2_wrapper_gate` 的 G1 用"打了 vs 没打"跑同一份面板，11 项指标**逐位相同** |

**为什么 `sell_rule` 必须是开关**：契约 §5 的字面是「卖已跌出目标组合的」
（`dropped_from_target`，也是 B2 的原读法），而**已发布的四道 S7 题声明 `worst_n_drop`**
（题面对 agent 写着「每期从持仓里卖掉信号最差的那几只」，即 qlib 读法）。
两种读法实测 material（B1 `ann_return_gross` 差 0.4460% 而 ε 是 0.2372%）。
写死任何一边都会让 gold 与一半的题对不上，而没有一处会报错。
`s7-rob-02` 就是拿这条歧义（A-1）做欠定探针的。

## 3. 面板与信号

**面板**：`s7_oracle_common.fetch_panel` 经网关拼契约 §1 的八列全格面板，
与冻结 ε 面板 `bt_input_csi300_v2.parquet` **逐格相同**
（984,960 格；`close`/`factor` 逐位相等，三个布尔列各 0 格不一致 ——
`ops/reports/s7_panel_vs_frozen.json`）。两侧数据源不同（qlib `D.features` / 网关 `/bars`×`/adj`），
`in_universe` 的来源也不同（qlib instruments 区间 / `/universe` 逐日 PIT）。

**精度是可比性的一部分**：`close`/`factor` 落 **float32**。
float64 与 float32 逐格只差 ~6e-08，但整手取整是不连续算子，
光这一个 dtype 差别就吃掉 `turnover_two_way_mean` **33.8% 的 ε 预算**
（`ops/reports/s7_panel_dtype_effect.json`）。`signal` 是 float64。

**信号**：`s7_dedicated_signal_v1` = 冻结 ε 面板的 `signal` 列（`qlib_alpha158.ROC20`），
由 `reference/make_s7_signal.py` 抽成 `work/signal.parquet`（545,677 行，
sha256 `4597e07783b9e442982c81fe61d1c76d1b1b25040aa1937b9aa2620e7088b78e`）。
**ε 是在这个信号上标定的，换信号 ε 失效**（裁定 N-84）。

## 4. 两条会被误当成缺陷的事

1. **冻结的 ε 产物在当前环境不再逐位复现**：原样重跑未打补丁的 B2，
   `ann_vol_net` / `max_drawdown_net` / `sharpe_net` 三项与 2026-09-01 的 JSON 差
   2.4e-16 ~ 3.5e-15（低于噪声地板 1e-13，比最小的 ε 小十个数量级）。
   今天连跑两次互相逐位相同，所以不是随机性。「冻结」指冻结**输入与代码**，
   **不含冻结数值**（N-89）。
2. **`ledger_check.max_abs_residual` 在 gold 上恒为 0**：B2 把 `total_assets`
   直接算成 `cash + mv`，所以残差按构造为零。它不是空判据 ——
   `ledger_conservation` 探针核的是 **agent 的 artifact**。

## 5. 复算

```bash
/data/shared/genebench/env/bin/python ops/acceptance/s7_b2_wrapper_gate.py     # 四门
/data/shared/genebench/env/bin/python ops/acceptance/s7_panel_vs_frozen.py     # 面板逐位
/data/shared/genebench/env/bin/python ops/run_oracles.py --tasks s7-cor-01 --agent oracle
```
