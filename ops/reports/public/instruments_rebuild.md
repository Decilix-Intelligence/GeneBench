# W2-2：只用 baostock 成分接口重建 csi300 / csi500 的 PIT 名单，并与私有 `universe_pit` 对账

* 做于 2026-09-10（北京时间 17:2x–19:3x，**非交易时段**），f01
* 重建器 `snapshots/public/instruments_rebuild.py`；产物落 `$GB/snapshots/public_v1/instruments_rebuild/`
* **本卡不替换公开包现用的 `instruments/*.txt`** —— 为什么见 §6，那是一次要用户点头的判据变更

---

## 0. 一眼看完

| | csi300 | csi500 | csi1000 |
| --- | --- | --- | --- |
| baostock 有没有成分接口 | `query_hs300_stocks` ✅ | `query_zz500_stocks` ✅ | **没有** ❌ |
| 重建窗口 | 2009-01-05 … 2026-07-31（4,269 个交易日） | 同左 | — |
| 请求数 | 2,528 | 2,528 | — |
| 逐日成分数 | **天天 300**（4,269/4,269） | 500（4,247 天）/ 499（**22 天**，上游自己就少一只） | — |
| 区间行数 / 去重代码 | 1,026 / 825 | 2,269 / 1,708 | — |
| 与私有逐日**完全相同** | **3,572 / 4,269 天（83.7%）** | 2,714 / 4,269 天（63.6%） | — |
| 逐日 Jaccard 均 / 最低 | **0.9874** / 0.8182 | **0.9789** / 0.8149 | — |
| 只在公开一侧的代码 | **0 只** | 2 只 | — |
| 只在私有一侧的代码 | **0 只** | 32 只（全是首 14 天的 qlib 种子名单） | — |

**一句话**：两份名单**成员是同一批**，差的几乎全是**进出场的日期**，而那个差是**系统性的**
—— 私有那份把调整**吸附到月末**（上游 tushare `index_weight` 是月频），
baostock 给的是**实际生效日**（中证的定期调整在 6 月 / 12 月的月中）。中位差 **−15 天**。

---

## 1. 取数：为什么是 2,528 次而不是 4,269 次

`query_hs300_stocks(date=d)` 回的每一行都带 `updateDate` —— **该名单版本的生效日**，
对 `d` 单调不减。于是「a 与 b 的 `updateDate` 相同」⇒ **(a, b) 之间一次调整都没发生**。
所以走「跨 5 个交易日探一步；`updateDate` 变了就在这 5 天里二分找第一个变化点」：
`{u_d == u_a}` 在 (a, b] 上是个前缀，二分**精确**，不是近似。单调性每一步都断言。

实测 baostock 的名单版本是**周频**换的（`updateDate` 基本每周一换），
所以省下来的没有理论上那么多：**2,528 / 4,269 ≈ 每天 0.59 次请求**，两个宇宙合计
5,056 次而不是 8,538 次。用时约 95 分钟（≈1.5 次/秒）。

**为什么在意请求数**：baostock 的公开 API **今天上午拒连过半小时** ——
09:26Z–09:56Z 之间从 f01 与 f02 各试十余次，全部 `ECONNREFUSED`
（DNS 正常解析到 `114.94.20.42`，同机 `1.1.1.1:53` 与 `pypi.org:443` 都通，
**是对方在拒，不是我们的出网被挡**）。10:0x 自己恢复。少问一半就少一半暴露。

### 这条推断不靠论证背书 —— 两道验

1. **随机回查**：随机抽 40 个交易日 × 2 个宇宙 = **80 次重新问 API**，
   与建出来的逐日成员集合**逐字比对，全部一致**
   （`instruments_rebuild.py verify --k 40`，种子 20260910）。
2. **版本内一致性**（`ops/test_W2.py::test_the_short_csi500_days_come_from_upstream_versions_not_from_our_inference`）：
   把每一天回填到它所属的名单版本，**任何一个版本内部的成分数都不许出现两种值**。
   如果我们漏掉了一次调整，短的天会横跨某一版的一部分；实测**没有一个版本是混的**。

### csi500 那 22 个 499 天

落在 **4 个上游名单版本**上：`2019-01-07`、`2019-01-14`、`2021-09-13`、`2021-09-27`。
每一版覆盖的**每一天**都是 499 —— 按上面第 2 道验，这是 **baostock 自己那几版就少一只**，
不是我们的推断漏了。**不修、不补**：补就等于替上游拍板往里塞一只，那正是我们要求被测方不许做的事。

---

## 2. 产物

| 文件 | 大小 | 是什么 |
| --- | ---: | --- |
| `csi300.txt` / `csi500.txt` | 31 KB / 69 KB | 与 qlib `instruments/*.txt` **同形**：`代码\t起\t止`，右端闭，连续区间合并 |
| `csi300_daily.jsonl` / `csi500_daily.jsonl` | 15 MB / 25 MB | 逐日成员集合（对账与复核的底稿） |
| `bs_cache/{csi300,csi500}/<date>.json` | 31 MB / 5,056 个 | 每次真实请求的原始回包（`updateDate` + 代码表），**可续跑、可复核** |
| `build_info.json` / `reconcile.json` / `reconcile_attrib.json` | 1 KB / 43 KB / 1 KB | 构建戳 / 对账明细 / 差异归因 |

**区间表示与现用文件不同形，是有意的**：现用 `instruments/csi300.txt` 里
`SZ000001` 被切成 `2009-01-05..2009-01-22` 与 `2009-01-23..2026-07-31` 两段
（`universe_pit` 的 `segment_id` / `part_idx` 分段），而重建版把**连续在册**的合成一段。
对账因此**不比区间行**，比**逐日成员集合** —— 那是表示无关的。

---

## 3. 对账：差在哪里

### 3.1 成员本身几乎不差

| | csi300 | csi500 |
| --- | ---: | ---: |
| 只在公开（baostock）一侧出现过的代码 | **0** | 2：`SZ000022`、`SZ300114` |
| 只在私有（`universe_pit`）一侧出现过的代码 | **0** | 32 |

* **csi300 是 0 / 0** —— 17.6 年、825 只代码，两份名单**一只不差**。
* **csi500 的 32 只只在私有**：全部来自 `source == qlib_instruments`，
  且**每一只都只有同一段** `2009-01-05..2009-01-22`（14 个交易日）。
  那是窗口最开头、`index_weight`（月频权重）还没覆盖到时用 qlib 名单垫的**种子段**，
  与 baostock 给的 2009 年 1 月实际成分不一致。**把首 14 天排除掉，这 32 只全部消失。**
* **csi500 的 2 只只在公开**：`SZ000022`（364 天）与 `SZ300114`（283 天）在 baostock 的
  csi500 里确实在册，而 `universe_pit` **整张表里根本没有这两个代码**（任何宇宙都没有）。
  这是**私有那份的缺口**，不是重建版多出来的东西 —— 已登记，见 `ops/tickets_inbox/W2.md`。

### 3.2 差的是日期，而且是系统性的

| 归因 | csi300 | csi500 |
| --- | ---: | ---: |
| 进场日不同的代码数 | 485 | 1,212 |
| 其中**私有那个日期正好是某月最后一个交易日** | **374（77.1%）** | **1,017（83.9%）** |
| 其中公开一侧**更早** | 318（65.6%） | 919（75.8%） |
| 进场日差（公开 − 私有）中位 / P10 / P90 | **−15** / −18 / +17 天 | **−15** / −22 / +6 天 |
| 出场日不同的代码数 | 524 | 1,205 |
| 出场日差中位 | −19 天 | −18 天 |

私有 `universe_pit` 的 `in_date` 日号分布也直说了这件事：
csi300 是 `31 日 287 段 / 30 日 277 段 / 29 日 108 段 / 28 日 56 段`
（外加 `5 日 300 段`、`23 日 300 段` —— 那是 2009-01-05 与 2009-01-23 两个种子段）。

**机制**：私有链路的成分来自 tushare 的 `index_weight`，那是**月频权重表**，
一只票进指数只能被记到「它第一次出现在某个月末权重表里」；
baostock 的名单版本是周频的，能给到**实际生效日**。中证 300/500 的定期调整生效日在
6 月与 12 月的**月中**，于是就有了这个稳定的 **−15 天**。

所以「63.8%–83.7% 的天完全相同」这个数**不该读成「名单质量差」** ——
它读的是「两份名单在调整发生的那两周里各说各话，其余时间一模一样」。
逐日 Jaccard 的中位数是 **1.000000**，P10 是 0.94（csi300）/ 0.91（csi500）。

---

## 4. csi1000：**做不了，不是没做**

baostock 0.9.3 提供的成分接口只有三个（实测 `dir(baostock)`）：

    query_hs300_stocks   query_zz500_stocks   query_sz50_stocks

**没有中证 1000**。调不到就是调不到，没有绕法（`query_zz1000_stocks` 不存在）。

结论：**公开包的 `instruments/csi1000.txt` 仍然派生自私有 `universe_pit`**
（上游 tushare 的 `index_weight` + qlib 名单），**不在 baostock 的许可射程内**。
这一条已写进 `ops/reports/known_limits_v1.md`（设计性限制 · 上游），并记为 v1.1。
`ops/test_W2.py::test_baostock_has_no_csi1000_constituent_api` 把它钉在代码里 ——
哪天 baostock 加了这个接口，那条测试会红，提醒有人来做。

---

## 5. 复现

```bash
export GENEBENCH_ROOT=/data/shared/genebench
cd $GENEBENCH_ROOT/repo && ulimit -n 8192
PY=$GENEBENCH_ROOT/env/bin/python
# baostock 是纯 python 包，解到 scratch 即可，不装进共享 env：
$PY -m pip download baostock==0.9.3 -d $GENEBENCH_ROOT/scratch/W2/wh --no-deps
$PY -m zipfile -e $GENEBENCH_ROOT/scratch/W2/wh/baostock-0.9.3-py3-none-any.whl \
      $GENEBENCH_ROOT/scratch/W2/bs/

$PY snapshots/public/instruments_rebuild.py fetch      # ≈95 分钟，非交易时段才肯启动，可续跑
$PY snapshots/public/instruments_rebuild.py build
$PY snapshots/public/instruments_rebuild.py verify --k 40      # 随机回查，联网
flock $GENEBENCH_ROOT/locks/heavy.lock -c \
  "$PY snapshots/public/instruments_rebuild.py reconcile"
$PY -m pytest ops/test_W2.py -q                                 # 18 passed
```

---

## 6. **没有做的一件事，以及为什么**

> **2026-09-12 更新（卡 A，用户裁定 ①）：§6 说的那件事已经做了。**
> 重建结果已经替换进 `$GB/snapshots/public_v1/qlib_provider/instruments/`，
> `csi1000` 出包，公开 provider 的根随之从 `561348660a3175b1…` 变成 `f7dda2899071b07a…`。
> **下面这一节原样保留** —— 它记的是「当时为什么不替换、要谁点头」，那段判断不该被结果抹掉。
> 换面记录、delta 与逐项验门见 [`instruments_switch.md`](instruments_switch.md)。

**没有把重建结果替换进 `$GB/snapshots/public_v1/qlib_provider/instruments/{csi300,csi500}.txt`。**

替换会把公开通道的**宇宙定义**换掉，而公开通道的 gold 因子面板、互检、τ/ε 标定、
`calibration.json` 全都建在现在这份名单上（`reference/factor_exec.py` 的成分掩膜按
`instruments/*.txt` 取）。换名单 = **重算公开 gold + 重标 τ + 重新签字**，
那是判据变更，不是一次数据修补 —— 按 D 条纪律走**保守方向**：
产出证据、把差异量清楚、把决定权交回去。

**要不要换、什么时候换，写成一条待裁定** → `ops/tickets_inbox/W2.md`（N-?）。
本卡给出的两个输入是：① 重建版在成员上与私有几乎无差（csi300 0/0）；
② 它在**进出场日期上更准**（私有那份把调整吸附到了月末，中位晚 15 天）。
换的收益是「公开包在许可上自足」，代价是「公开通道整条 gold 链重跑一遍」。
