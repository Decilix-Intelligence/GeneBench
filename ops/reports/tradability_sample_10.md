# 卡 1.2 验收 (b):10 条判定链路取证

> 本文件由 `snapshots/tradability.py` 生成,**不要手改** —— 手改会和产物漂移。

## 这张表怎么用

每一行给出**从三个源头到 `status` 的完整链路**:`trade_cal` 说这天开不开市、
`daily` 有没有行、`suspend_d` 怎么说、`stk_limit` 的上下限对上 `daily` 的 OHLC。
拿这四条原始证据,任何人都能自己推一遍 `status`,不必信产物。

复核用的判定规则(与 `snapshots/tradability.py::classify` 一字不差):

```
daily 无行 + 有停牌证据            -> suspend
daily 无行 + 无停牌证据            -> no_data
daily 有行 + |close-up_limit|<tol  -> limit_up      (收盘封板)
daily 有行 + |close-down_limit|<tol-> limit_down    (收盘封板)
daily 有行 + 其它                  -> trade
tol = 1e-06
「无涨跌幅限制」哨兵(-> 四个触板列强制 False),三条腿取并集:
    (up_limit >= 99000 or up_limit <= 0)
    (down_limit <= 0.01)
    ((up_limit - down_limit) / (up_limit + down_limit) >= 0.5 or up_limit + down_limit <= 0)
```

## 抽样规则

- 随机种子 `20260731`,从冻结产物里**等概率**抽 `50` 条。
- 这 50 条的 status 分布:`trade`=48、`suspend`=2、`limit_up`=0、`limit_down`=0、`no_data`=0。
- 取证的 10 条按 status **分层**挑(规则见 `pick_samples` 的 docstring),每条都标了它是从 50 条里来的还是补抽的。

## 取证表

### 1. `600791.SH` @ `2009-06-30` → **`trade`**

*来源:来自 50 条随机样本*

| 环节 | 湖里查到什么 | 对 status 的作用 |
|---|---|---|
| `trade_cal` | 交易所 `SSE`,`is_open=1` | 开市 → 缺行才有「停牌 vs 缺数据」之分 |
| `daily` | **有 1 行**:pre_close=7.00,OHLC = 7.00/7.10/6.82/6.86,volume=11938619 | 有行 → 只可能是 `trade`/`limit_up`/`limit_down` |
| `suspend_d` | **0 行** | 当天无停复牌事件;`suspend_basis=none` |
| `stk_limit` | **有 1 行**:`up_limit=7.70`,`down_limit=6.30` | 比价 → `limit_up_close=否`,`limit_touched_up=否`,`limit_down_close=否`,`limit_touched_down=否` |

产物这一行:`in_listing_window=是`、`has_daily=是`、`has_limit=是`、`intraday_halt=否`。

### 2. `601000.SH` @ `2016-01-07` → **`suspend`**

*来源:来自 50 条随机样本*

| 环节 | 湖里查到什么 | 对 status 的作用 |
|---|---|---|
| `trade_cal` | 交易所 `SSE`,`is_open=1` | 开市 → 缺行才有「停牌 vs 缺数据」之分 |
| `daily` | **0 行(缺行)** | 缺行 → 只可能是 `suspend`/`no_data` |
| `suspend_d` | **有 1 行**:`suspend_type=S`,`suspend_timing=NULL` | S=停牌;`suspend_basis=suspend_d_S` |
| `stk_limit` | **有 1 行**:`up_limit=9.08`,`down_limit=7.43` | 比价 → `limit_up_close=否`,`limit_touched_up=否`,`limit_down_close=否`,`limit_touched_down=否` |

产物这一行:`in_listing_window=是`、`has_daily=否`、`has_limit=是`、`intraday_halt=否`。

### 3. `600804.SH` @ `2021-08-30` → **`limit_up`**

*来源:50 条里没有 `limit_up`,同种子从全表该状态补抽*

| 环节 | 湖里查到什么 | 对 status 的作用 |
|---|---|---|
| `trade_cal` | 交易所 `SSE`,`is_open=1` | 开市 → 缺行才有「停牌 vs 缺数据」之分 |
| `daily` | **有 1 行**:pre_close=5.54,OHLC = 5.84/6.09/5.75/6.09,volume=204756785 | 有行 → 只可能是 `trade`/`limit_up`/`limit_down` |
| `suspend_d` | **0 行** | 当天无停复牌事件;`suspend_basis=none` |
| `stk_limit` | **有 1 行**:`up_limit=6.09`,`down_limit=4.99` | 比价 → `limit_up_close=是`,`limit_touched_up=是`,`limit_down_close=否`,`limit_touched_down=否` |

产物这一行:`in_listing_window=是`、`has_daily=是`、`has_limit=是`、`intraday_halt=否`。

### 4. `002100.SZ` @ `2015-06-19` → **`limit_down`**

*来源:50 条里没有 `limit_down`,同种子从全表该状态补抽*

| 环节 | 湖里查到什么 | 对 status 的作用 |
|---|---|---|
| `trade_cal` | 交易所 `SSE`,`is_open=1` | 开市 → 缺行才有「停牌 vs 缺数据」之分 |
| `daily` | **有 1 行**:pre_close=15.04,OHLC = 14.71/14.71/13.54/13.54,volume=20853737 | 有行 → 只可能是 `trade`/`limit_up`/`limit_down` |
| `suspend_d` | **0 行** | 当天无停复牌事件;`suspend_basis=none` |
| `stk_limit` | **有 1 行**:`up_limit=16.54`,`down_limit=13.54` | 比价 → `limit_up_close=否`,`limit_touched_up=否`,`limit_down_close=是`,`limit_touched_down=是` |

产物这一行:`in_listing_window=是`、`has_daily=是`、`has_limit=是`、`intraday_halt=否`。

### 5. `000498.SZ` @ `2010-03-15` → **`no_data`**

*来源:50 条里没有 `no_data`,同种子从全表该状态补抽*

| 环节 | 湖里查到什么 | 对 status 的作用 |
|---|---|---|
| `trade_cal` | 交易所 `SSE`,`is_open=1` | 开市 → 缺行才有「停牌 vs 缺数据」之分 |
| `daily` | **0 行(缺行)** | 缺行 → 只可能是 `suspend`/`no_data` |
| `suspend_d` | **0 行** | 当天无停复牌事件;`suspend_basis=none` |
| `stk_limit` | **0 行** | `has_limit=False` → 四个触板列强制 `False`,那是**没法判**不是**没触板** |

产物这一行:`in_listing_window=是`、`has_daily=否`、`has_limit=否`、`intraday_halt=否`。

### 6. `000100.SZ` @ `2010-12-02` → **`trade`**

*来源:来自 50 条随机样本(补足名额)*

| 环节 | 湖里查到什么 | 对 status 的作用 |
|---|---|---|
| `trade_cal` | 交易所 `SSE`,`is_open=1` | 开市 → 缺行才有「停牌 vs 缺数据」之分 |
| `daily` | **有 1 行**:pre_close=3.53,OHLC = 3.58/3.58/3.53/3.55,volume=22009573 | 有行 → 只可能是 `trade`/`limit_up`/`limit_down` |
| `suspend_d` | **0 行** | 当天无停复牌事件;`suspend_basis=none` |
| `stk_limit` | **有 1 行**:`up_limit=3.88`,`down_limit=3.18` | 比价 → `limit_up_close=否`,`limit_touched_up=否`,`limit_down_close=否`,`limit_touched_down=否` |

产物这一行:`in_listing_window=是`、`has_daily=是`、`has_limit=是`、`intraday_halt=否`。

### 7. `002348.SZ` @ `2010-09-14` → **`trade`**

*来源:来自 50 条随机样本(补足名额)*

| 环节 | 湖里查到什么 | 对 status 的作用 |
|---|---|---|
| `trade_cal` | 交易所 `SSE`,`is_open=1` | 开市 → 缺行才有「停牌 vs 缺数据」之分 |
| `daily` | **有 1 行**:pre_close=22.29,OHLC = 22.29/22.43/22.03/22.20,volume=1592830 | 有行 → 只可能是 `trade`/`limit_up`/`limit_down` |
| `suspend_d` | **0 行** | 当天无停复牌事件;`suspend_basis=none` |
| `stk_limit` | **有 1 行**:`up_limit=24.52`,`down_limit=20.06` | 比价 → `limit_up_close=否`,`limit_touched_up=否`,`limit_down_close=否`,`limit_touched_down=否` |

产物这一行:`in_listing_window=是`、`has_daily=是`、`has_limit=是`、`intraday_halt=否`。

### 8. `600193.SH` @ `2011-05-06` → **`trade`**

*来源:来自 50 条随机样本(补足名额)*

| 环节 | 湖里查到什么 | 对 status 的作用 |
|---|---|---|
| `trade_cal` | 交易所 `SSE`,`is_open=1` | 开市 → 缺行才有「停牌 vs 缺数据」之分 |
| `daily` | **有 1 行**:pre_close=18.40,OHLC = 18.00/18.45/17.38/18.38,volume=11048025 | 有行 → 只可能是 `trade`/`limit_up`/`limit_down` |
| `suspend_d` | **0 行** | 当天无停复牌事件;`suspend_basis=none` |
| `stk_limit` | **有 1 行**:`up_limit=20.24`,`down_limit=16.56` | 比价 → `limit_up_close=否`,`limit_touched_up=否`,`limit_down_close=否`,`limit_touched_down=否` |

产物这一行:`in_listing_window=是`、`has_daily=是`、`has_limit=是`、`intraday_halt=否`。

### 9. `002206.SZ` @ `2012-07-31` → **`trade`**

*来源:来自 50 条随机样本(补足名额)*

| 环节 | 湖里查到什么 | 对 status 的作用 |
|---|---|---|
| `trade_cal` | 交易所 `SSE`,`is_open=1` | 开市 → 缺行才有「停牌 vs 缺数据」之分 |
| `daily` | **有 1 行**:pre_close=5.65,OHLC = 5.69/5.74/5.46/5.69,volume=1356492 | 有行 → 只可能是 `trade`/`limit_up`/`limit_down` |
| `suspend_d` | **0 行** | 当天无停复牌事件;`suspend_basis=none` |
| `stk_limit` | **有 1 行**:`up_limit=6.22`,`down_limit=5.09` | 比价 → `limit_up_close=否`,`limit_touched_up=否`,`limit_down_close=否`,`limit_touched_down=否` |

产物这一行:`in_listing_window=是`、`has_daily=是`、`has_limit=是`、`intraday_halt=否`。

### 10. `600112.SH` @ `2012-02-10` → **`trade`**

*来源:来自 50 条随机样本(补足名额)*

| 环节 | 湖里查到什么 | 对 status 的作用 |
|---|---|---|
| `trade_cal` | 交易所 `SSE`,`is_open=1` | 开市 → 缺行才有「停牌 vs 缺数据」之分 |
| `daily` | **有 1 行**:pre_close=14.09,OHLC = 13.93/14.27/13.86/14.11,volume=9432167 | 有行 → 只可能是 `trade`/`limit_up`/`limit_down` |
| `suspend_d` | **0 行** | 当天无停复牌事件;`suspend_basis=none` |
| `stk_limit` | **有 1 行**:`up_limit=15.50`,`down_limit=12.68` | 比价 → `limit_up_close=否`,`limit_touched_up=否`,`limit_down_close=否`,`limit_touched_down=否` |

产物这一行:`in_listing_window=是`、`has_daily=是`、`has_limit=是`、`intraday_halt=否`。

