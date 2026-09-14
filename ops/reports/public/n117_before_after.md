# N-117 前后对比 —— S4 的 IC 族拿到 ε 带之后

生成于 `ops/ic_epsilon.py` + `ops/merge_ic_epsilon.py`，代码 HEAD `10c2dbc82ca4`，标定产物 `/data/shared/genebench/snapshots/v1/epsilon/ic_epsilon_dual.json`（sha256 `565da2272ab881a4…`）。

## 0. 一句话

S4 的 `tolerance.kind` 是 `epsilon`，而 `calibration.json` 此前只标定了**回测指标** —— IC 族一个带都没有，`scorer.l3.compare_epsilon` 一格都比不了，`l3_pass=None` → 锚点退化 → **effect 永远扣住**（票据 N-117）。本卡用「qlib 口径 vs 纯 pandas 口径」的双实现给 IC 族标了带，S4 的那一条 run 从「未结算」变成「已结算且通过」。

## 1. 标定怎么做的

* **实现 A（qlib 口径）**：`qlib.contrib.eva.alpha.calc_ic` —— 它就是 `SigAnaRecord._generate` 的计算路径（运行时核对源码，核不上直接抛）。qlib `0.9.8.dev32`。
* **实现 B（纯 pandas 口径）**：逐截面 `rank(平局 average) → Pearson`，最小截面门槛 5。
* **实现 C**：与 B 同一份汇总代码，只把题面的「当日不可交易」读成 `status ∈ {suspend, no_data}`（涨跌停当天股票是成交的）。
* 分歧取**全对最大**（A|B、A|C、B|C），与 2.2b 的 `compare_pairwise` 同法。

**三份实现吃同一份「已声明」的输入面**：题面把无效格逐条写死了（因子非有限 / 当日不可交易 / 远期收盘缺失 / 远期日期越过 as_of），把**已声明**的东西量进 ε 会得到一条宽到没有判别力的带。留给自由度的是题面**没写**的那几处：
  1. 「当日不可交易」指什么：`trade` 之外全算，还是只算停牌 / 无数据（涨跌停约占 10% 的格）
  1. 最小截面门槛（题面没写）
  1. positive_ratio / coverage 的分母算不算 NaN 日
  1. 一格都没有的交易日进不进 coverage

**样本面**：判据窗 `2026-01-05..2026-06-30`（= v1.0 冒烟集 S4 题的窗），csi1000 792 因子、csi300 792 因子、csi500 792 因子，持有期 [1, 5, 20]，共 7128 条 A/B/C 记录。

**带规则**：ε = 分歧分布的 P90 × 1.5。2.2b 的样本面是一次回测（3 份实现两两比 = 3 个数），取最大是唯一可能；这里的样本面是一个分布，取最大 = 让带被最病态的那个因子绑架。P90 是 τ 的 P10 的镜像（`GeneBench秩相关与标定口径_v1.md` F-2 允许 10% 的尾巴落在门外）。每条带同时报 P50/P90/P95/P99/max 与 `epsilon_if_max_rule`。

## 2. 标出来的带

| 持有期 | 指标 | 容差类型 | P50 | P90 | max | **ε** | 若按 max 定带 | 状态 |
|---|---|---|---:|---:|---:|---:|---:|---|
| 1 | `mean` | absolute | 0.003677 | 0.008558 | 0.06242 | **0.01284** | 0.09362 | `calibrated` |
| 1 | `std` | relative | 0.008156 | 0.01706 | 0.3262 | **0.02559** | 0.4893 | `calibrated` |
| 1 | `icir` | absolute | 0.3863 | 0.8176 | 2.089 | **1.226** | 3.134 | `calibrated` |
| 1 | `positive_ratio` | relative | 0.01852 | 0.05714 | 0.1718 | **—** | 0.2578 | `implausible_stop_and_report` |
| 1 | `coverage` | relative | 0.01529 | 0.01696 | 0.0431 | **0.02544** | 0.06466 | `calibrated` |
| 1 | `ci_low` | relative | — | — | — | **—** | — | `no_pair_in_qlib_path` |
| 1 | `ci_high` | relative | — | — | — | **—** | — | `no_pair_in_qlib_path` |
| 5 | `mean` | absolute | 0.0006518 | 0.001959 | 0.08037 | **0.002938** | 0.1205 | `calibrated` |
| 5 | `std` | relative | 0.0109 | 0.02408 | 0.4328 | **0.03612** | 0.6492 | `calibrated` |
| 5 | `icir` | absolute | 0.06432 | 0.2203 | 3.43 | **0.3304** | 5.145 | `calibrated` |
| 5 | `positive_ratio` | relative | 0.01852 | 0.05172 | 0.1552 | **—** | 0.2328 | `implausible_stop_and_report` |
| 5 | `coverage` | relative | 0.01521 | 0.01693 | 0.0431 | **0.0254** | 0.06466 | `calibrated` |
| 5 | `ci_low` | relative | — | — | — | **—** | — | `no_pair_in_qlib_path` |
| 5 | `ci_high` | relative | — | — | — | **—** | — | `no_pair_in_qlib_path` |
| 20 | `mean` | absolute | 0.001573 | 0.004495 | 0.1167 | **0.006742** | 0.175 | `calibrated` |
| 20 | `std` | relative | 0.01175 | 0.0255 | 0.3665 | **0.03824** | 0.5497 | `calibrated` |
| 20 | `icir` | absolute | 0.1503 | 0.382 | 3.444 | **0.5729** | 5.167 | `calibrated` |
| 20 | `positive_ratio` | relative | 0.01786 | 0.05 | 0.1608 | **—** | 0.2412 | `implausible_stop_and_report` |
| 20 | `coverage` | relative | 0.01531 | 0.01696 | 0.0431 | **0.02544** | 0.06466 | `calibrated` |
| 20 | `ci_low` | relative | — | — | — | **—** | — | `no_pair_in_qlib_path` |
| 20 | `ci_high` | relative | — | — | — | **—** | — | `no_pair_in_qlib_path` |

**裁定**：4/5 个 IC 指标拿到带：['coverage', 'icir', 'mean', 'std']。超阈未出带：['positive_ratio']（按 2.2b 纪律，>5% 的相对分歧不像实现自由度，多半是声明没写清 —— 停下汇报）。双实现对构不成：['ci_low', 'ci_high']（qlib 口径没有 bootstrap 区间）。L3 逐指标按 status 取带，因此 S4 的 l3_pass 仍然算得出来。

### 两条没出带的，各自的理由

* **`positive_ratio` 超阈**：P90 相对分歧 h=1 5.71%、h=5 5.17%、h=20 5.00%，都在 5% 之上。按 2.2b 的纪律：超阈的**不写成 ε**，停下汇报 —— 过宽的 ε 会让判据失去判别力。根因是题面「当日不可交易」没定义到 status 档位（见票据）。钉死那一条之后这个带会窄一个数量级。
* **`ci_low` / `ci_high` 构不成双实现对**：qlib 口径没有 bootstrap 区间，双实现对构不成 —— 不出带，L3 跳过。

### ICIR 的年化不是容差，是声明歧义

SigAnaRecord 的 ICIR = ic.mean()/ic.std()，**不年化**；S4 题面声明 annualization=252 而参考实现年化（×√annualization）。 两者差 **15.87 倍**。标定时**两边都年化** —— 量的才是实现自由度而不是单位差。年化与否本身按 2.2b 的纪律属于「声明没写清」，登记为票据，不写成 ε。

### 分歧随宇宙与随窗怎么走

| 宇宙 | 样本 | mean | std | icir | positive_ratio | coverage |（绝对分歧 P90）
|---|---:|---:|---:|---:|---:|---:|
| csi1000 | 2376 | 0.007272 | 0.004239 | 0.6828 | 0.02586 | 0.01692 |
| csi300 | 2376 | 0.003074 | 0.002191 | 0.229 | 0.01724 | 0.007845 |
| csi500 | 2376 | 0.006834 | 0.004159 | 0.6244 | 0.02586 | 0.01527 |

小宇宙的分歧系统性更大（停牌与涨跌停的格更多）—— 带是三个宇宙**合池**出的，因此对 csi300 偏宽、对 csi1000 偏紧。

| 窗 | 因子 | 覆盖宇宙 | mean | std | icir | positive_ratio | coverage |（P90）
|---|---:|---|---:|---:|---:|---:|---:|
| 2025-01-02..2025-06-30 | 792 | csi300 | 0.003371 | 0.01502 | 0.3011 | 0.02972 | 0.00487 |
| 2025-07-01..2025-12-31 | 792 | csi1000,csi300,csi500 | 0.003728 | 0.01109 | 0.3189 | 0.04 | 0.008542 |
| 2026-01-05..2026-06-30 | 792 | csi1000,csi300,csi500 | 0.006487 | 0.02341 | 0.5536 | 0.05357 | 0.01696 |

换窗后 P90 在**同一数量级**内移动（最大约 2–3 倍），没有出现数量级跳变 —— 量到的不是「这半年的行情」。另两个窗的样本没跑满三宇宙（并行跑批按时间盒收口），只作敏感性参考，**带本身只用判据窗**。

## 3. 合并进 `calibration.json`：只多不少

* 新键：`epsilon.ic_family`；`526` 行 → `1151` 行（**+625**）
* sha256：`5e33296ba2576965…` → `6920dd1fb6804aff…`
* 备份：`/data/shared/genebench/snapshots/v1/calibration.json.pre_n117.bak（已存在，未覆盖）`
* 三道闸（`ops/merge_ic_epsilon.verify()`，任何一道不过就不落盘）：
  1. 原文件必须已是规范序列化 —— 不然「逐字节不变」无从论证；
  2. **结构相等**：新文件去掉 `epsilon.ic_family` 后与原对象逐值相等 → `True`；
  3. **行级只增不减**：删除行只允许是「末尾多了个逗号」那一种 → `True`。

`ready_for_scoring` 与 `outstanding` 两个字段**没有动**（它们现在与事实不符，已登记票据）。

## 4. S4 那一条 run 的前后

`ops/reports/m6/scores/s4-cor-01.strict.cfg-codex-deepseek.r02.score.json`

| 字段 | 之前 | 之后 |
|---|---|---|
| `l3_kind` | `epsilon` | `epsilon` |
| `l3_pass` | `None` | `True` |
| `l3_score` | `None` | `1.0` |
| `effect` | `None` | `100.0` |
| `effect_withheld_reason` | `anchor_degenerate` | `None` |
| `anchor.floor` / `anchor.ceiling` | `None` / `None` | `0.0` / `1.0` |
| 比了几格 | 0（`l3_note`：gold payload 里没有任何带标定 ε 的指标）| 16（`n_band_ic_family`=16，`n_band_backtest`=0）|
| `max_band_ratio` | — | 0.4880（最紧的那一格用掉了带的 48.8%）|

**真 agent 与 gold 的逐项差**（同一条 run）：`mean` / `std` / `icir` / `positive_ratio` 在三个持有期上与 gold **差 0（逐位相同）**；只有 `coverage` 差 1.178%（相对）与 bootstrap CI 不同。`coverage` 报 1.000000 说明它**没按题面剔无效格**却把分母也换掉了 —— 一个「数算对了但口径没照做」的干净实例。那 1.178% 落在 `coverage` 带（ε=0.02544）之内，因此判过。

## 5. 主表的前后

| 批 | 配置 / 臂 | `unsettled_runs` 前 → 后 | `pass@1` 前 → 后 | `effect` 前 → 后 |
|---|---|---|---|---|
| m6 | cfg-codex-deepseek / open | 0 → 0 | 0.5 → 0.5 | 100.0 → 100.0 |
| m6 | cfg-codex-deepseek / strict | 1 → 0 | 0.375 → 0.4375 | 100.0 → 100.0 |
| m6_all | cfg-codex-deepseek / open | 0 → 0 | 0.3333333333333333 → 0.3333333333333333 | 100.0 → 100.0 |
| m6_all | cfg-codex-deepseek / strict | 1 → 0 | 0.25 → 0.2916666666666667 | 100.0 → 100.0 |

## 6. 私有通道数值不变

重结算前后逐字段比对 29 份 `*.score.json`（m6 21 份 + m6b 8 份）：**28 份逐字节相同**，唯一有差异的就是上面那一条 S4 run，且差异**全是新增键**（`band:*` / `n_band_*` / `anchor.*`）与三个此前为 `None` 的字段（`l3_pass` / `l3_score` / `effect`）变成真值。比对脚本 `/data/shared/genebench/scratch/1.2/diffcheck.py`，改动前的报告快照 `/data/shared/genebench/scratch/1.2/before/`（`reports.sha256` 100 个文件）。

## 7. 怎么复跑

```bash
cd $REPO
# 跑批（不打网关，因此不需要 gateway_lock）；三个宇宙可以并行，各写各的断点盘
$PY ops/ic_epsilon.py --universes csi300 --state $GB/scratch/1.2/samples_csi300.jsonl \
     --out $GB/scratch/1.2/ic_epsilon_csi300.json
# 出带（只用判据窗；断点盘目录会被整目录读进来）
$PY ops/ic_epsilon.py --aggregate-only --state $GB/scratch/1.2/state \
     --windows 2026-01-05..2026-06-30 --out $GB/snapshots/v1/epsilon/ic_epsilon_dual.json
# 合并（--check 只验不写）
$PY ops/merge_ic_epsilon.py --report $GB/scratch/1.2/merge_report.json
# 重结算
$PY ops/score_runs.py --batch m6 --no-pull && $PY ops/score_runs.py --batch m6b --no-pull \
  && $PY ops/combine_batches.py m6 m6b
```

`ops/ic_epsilon.py --aggregate-only` 在 `usable=False` 时**退出码是 1**（与 2.2b 的 `reference/epsilon_dual` 一致：只要还有指标超阈，这一族的标定就没收完）。这不代表出带失败 —— 见 §2 的裁定。
