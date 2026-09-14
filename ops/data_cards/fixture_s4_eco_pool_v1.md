# 夹具数据卡：`s4_eco_pool_v1`

**宇宙** `csi300` · **窗口** `2026-01-05` … `2026-06-30` · **30 条因子 / 1,003,974 行**

## 选取规则（裁定 N-99 ①，2026-09-05）

* 每族 **10** 条，三族：gtja_191, worldquant_101, qlib_alpha158；
* 按 factor_id 字典序排序，等距下标 round(i·(n−1)/(k−1)) —— **不看 IC**，避免选择泄漏；
* 排除：全窗 degenerate（非空值唯一值 ≤ 1）或覆盖率 < coverage_min（阈值 0.95）。

## 最终清单

### gtja_191（候选 186 → 合格 186 → 取 10）

- `gtja_191.001`
- `gtja_191.022`
- `gtja_191.043`
- `gtja_191.064`
- `gtja_191.085`
- `gtja_191.106`
- `gtja_191.126`
- `gtja_191.147`
- `gtja_191.168`
- `gtja_191.191`

### worldquant_101（候选 82 → 合格 80 → 取 10）

- `worldquant_101.001`
- `worldquant_101.010`
- `worldquant_101.019`
- `worldquant_101.027`
- `worldquant_101.036`
- `worldquant_101.045`
- `worldquant_101.055`
- `worldquant_101.071`
- `worldquant_101.084`
- `worldquant_101.101`

排除 2 条：`worldquant_101.068`(degenerate)、`worldquant_101.086`(degenerate)

### qlib_alpha158（候选 158 → 合格 158 → 取 10）

- `qlib_alpha158.BETA10`
- `qlib_alpha158.CNTP30`
- `qlib_alpha158.IMAX60`
- `qlib_alpha158.KSFT2`
- `qlib_alpha158.MIN60`
- `qlib_alpha158.RESI10`
- `qlib_alpha158.RSV5`
- `qlib_alpha158.SUMP10`
- `qlib_alpha158.VSUMD5`
- `qlib_alpha158.WVMA60`

