# 公开通道跑批小结（卡 1.1-c）

> 通道 `public`（baostock，`snapshots/public_v1`），网关 18081，日志 `/data/shared/genebench/logs/gateway_access_public.jsonl`；
> 题集 `$GB/reference/tasks/public/v1.0-smoke-public`（与私有 `v1.0-smoke` **并列不覆盖**；**多一层 `public/` 是必须的** —— `gateway/sim_factory.task_dir` 是 `(reference/tasks).glob("*/<task_id>")`，直接并列会让私有生产网关的 S8 四题一起 500）。

## ① 逐题 oracle 矩阵（O1：零 finding）

**32/40 题零 finding**（落盘的 33 题里 32 题零 finding；另 7 道探针题被 E9c 拦在**落盘之前**，见 §④）。

> 完成定义写的是「33 题零 finding」。**私有通道的累积记录当前也是 32/40** —— 唯一多出来的那道红是 `s2-eco-01`，它打 `/bars?universe=…` 不给 `code`、网关 422，两条通道同样红且早于本卡（见票据）。所以两条通道**逐题一致**。

喂了可交易性视图（N-120）的题：**28/32**（分母是有产物、真判过的那些）；没喂的题上 `calendar` 与 `missing_masquerading_as_signal` 两条**没被调用过**，那两格是不可得不是干净

| 题 | 阶段 | 零 finding | rc | 日志条数 | 视图格数 | 网关耗时 | findings |
| --- | --- | --- | --- | --- | --- | --- | --- |
| s1-cor-01 | S1 | ✅ | 0 | 601 | 6900 | 150.9 s | — |
| s1-eco-01 | S1 | ✅ | 0 | 501 | 11500 | 226.7 s | — |
| s1-ops-01 | S1 | ✅ | 0 | 301 | 1500 | 134.6 s | — |
| s1-rob-01 | S1 | ✅ | 0 | 303 | 3000 | 131.5 s | — |
| s1-rob-02 | S1 | ❌ | None | None | None | — s | — |
| s2-cor-01 | S2 | ✅ | 0 | 602 | 41700 | 6.9 s | — |
| s2-eco-01 | S2 | ❌ | 1 | None | None | — s | requests.exceptions.HTTPError: 422 Client Error: Unprocessable Entity for url: http://192.168.1.48:18081/bars?universe=c |
| s2-ops-01 | S2 | ✅ | 0 | 602 | 6900 | 159.9 s | — |
| s2-rob-01 | S2 | ✅ | 0 | 502 | 69500 | 224.3 s | — |
| s2-rob-02 | S2 | ❌ | None | None | None | — s | — |
| s3-cor-01 | S3 | ✅ | 0 | 302 | 41700 | 136.2 s |   return val.stack(dropna=False).rename("value") |
| s3-eco-01 | S3 | ✅ | 0 | 302 | 41700 | 135.8 s |   return val.stack(dropna=False).rename("value") |
| s3-ops-01 | S3 | ✅ | 0 | 302 | 41700 | 141.6 s |   return (left * right).stack(dropna=False).rename("value") |
| s3-rob-01 | S3 | ✅ | 0 | 302 | 41700 | 136.5 s |   return val.stack(dropna=False).rename("value") |
| s3-rob-02 | S3 | ❌ | None | None | None | — s | — |
| s4-cor-01 | S4 | ✅ | 0 | 583 | 34800 | 6.1 s | — |
| s4-eco-01 | S4 | ✅ | 0 | 583 | 34800 | 7.0 s | — |
| s4-ops-01 | S4 | ✅ | 0 | 583 | 34800 | 6.7 s | — |
| s4-rob-01 | S4 | ✅ | 0 | 583 | 34800 | 6.0 s | — |
| s4-rob-02 | S4 | ❌ | None | None | None | — s | — |
| s5-cor-01 | S5 | ✅ | 0 | 72 | 6900 | 0.3 s | 写出 /data/shared/genebench/reference/tasks/public/v1.0-smoke-public/s5-cor-01/solution/artifact.json：{'n_valued': 6796, ' |
| s5-eco-01 | S5 | ✅ | 0 | 420 | 41700 | 2.3 s | 写出 /data/shared/genebench/reference/tasks/public/v1.0-smoke-public/s5-eco-01/solution/artifact.json：{'n_valued': 39247,  |
| s5-ops-01 | S5 | ✅ | 0 | 72 | 6900 | 0.4 s | 写出 /data/shared/genebench/reference/tasks/public/v1.0-smoke-public/s5-ops-01/solution/artifact.json：{'n_valued': 6796, ' |
| s5-rob-01 | S5 | ✅ | 0 | 72 | 6900 | 0.4 s | 写出 /data/shared/genebench/reference/tasks/public/v1.0-smoke-public/s5-rob-01/solution/artifact.json：{'n_valued': 6125, ' |
| s5-rob-02 | S5 | ❌ | None | None | None | — s | — |
| s6-cor-01 | S6 | ✅ | 0 | 100 | 6900 | 46.4 s | wrote /data/shared/genebench/reference/tasks/public/v1.0-smoke-public/s6-cor-01/solution/artifact.json days 23 |
| s6-eco-01 | S6 | ✅ | 0 | 35 | 18600 | 15.7 s | wrote /data/shared/genebench/reference/tasks/public/v1.0-smoke-public/s6-eco-01/solution/artifact.json days 13 |
| s6-ops-01 | S6 | ✅ | 0 | 57 | 18600 | 25.7 s | wrote /data/shared/genebench/reference/tasks/public/v1.0-smoke-public/s6-ops-01/solution/artifact.json days 3 |
| s6-rob-01 | S6 | ✅ | 0 | 91 | 6900 | 41.3 s | wrote /data/shared/genebench/reference/tasks/public/v1.0-smoke-public/s6-rob-01/solution/artifact.json days 23 |
| s6-rob-02 | S6 | ❌ | None | None | None | — s | — |
| s7-cor-01 | S7 | ✅ | 0 | 1837 | 545400 | 75.4 s | — |
| s7-eco-01 | S7 | ✅ | 0 | 1837 | 545400 | 77.7 s | — |
| s7-ops-01 | S7 | ✅ | 0 | 1838 | 545400 | 80.0 s | — |
| s7-rob-01 | S7 | ✅ | 0 | 1837 | 545400 | 72.6 s | — |
| s7-rob-02 | S7 | ✅ | 0 | 1 | 545400 | 0.0 s | — |
| s8-cor-01 | S8 | ✅ | 0 | 40 | None | 2.6 s | — |
| s8-eco-01 | S8 | ✅ | 0 | 12 | None | 0.5 s | — |
| s8-ops-01 | S8 | ✅ | 0 | 19 | None | 0.9 s | — |
| s8-rob-01 | S8 | ✅ | 0 | 19 | None | 1.3 s | — |
| s8-rob-02 | S8 | ❌ | None | None | None | — s | — |

网关侧合计：15,127 次请求 / 34.2 分钟（逐题首末时间戳之差求和）；最慢三题：`s1-eco-01` 3.8 分、`s2-rob-01` 3.7 分、`s2-ops-01` 2.7 分。
可交易性视图（`config_id=oracle_probe_view`，N-120）另计 32,934 次请求 —— **它们不进 `config_id=oracle` 的切片**，所以不会被交叉核当成 oracle 读了未声明的字段。

### 没能零 finding 的题（逐题原因）

- **s1-rob-02**（rc=None）：落盘被拦：PackError: E9c/E9d2 探针题 s1-rob-02 不落盘：字段 data_version 在条件 （无条件） 下既无 screen 实测记录、也无 FIELD_MATERIAL_WHEN 静态规则 —— 先跑 ops/run_materiality_screen.py 或补静态前提
- **s2-eco-01**（rc=1）： in raise_for_status
    raise HTTPError(http_error_msg, response=self)
requests.exceptions.HTTPError: 422 Client Error: Unprocessable Entity for url: http://192.168.1.48:18081/bars?universe=csi300&start_date=2019-01-02&end_date=2026-07-31&fields=close%2Chigh%2Clow%2Cvolume%2Cstatus&as_of=2026-07-31
- **s2-rob-02**（rc=None）：落盘被拦：PackError: E9c/E9d2 探针题 s2-rob-02 不落盘：字段 adjust 在条件 (('missing_row_policy', 'keep_missing'),) 下既无 screen 实测记录、也无 FIELD_MATERIAL_WHEN 静态规则 —— 先跑 ops/run_materiality_screen.py 或补静态前提
- **s3-rob-02**（rc=None）：落盘被拦：PackError: E9c/E9d2 探针题 s3-rob-02 不落盘：字段 eval_frequency 在条件 (('lookback', '24'),) 下既无 screen 实测记录、也无 FIELD_MATERIAL_WHEN 静态规则 —— 先跑 ops/run_materiality_screen.py 或补静态前提
- **s4-rob-02**（rc=None）：落盘被拦：PackError: E9c/E9d2 探针题 s4-rob-02 不落盘：字段 holding_periods 在条件 (('ic_method', 'spearman'),) 下既无 screen 实测记录、也无 FIELD_MATERIAL_WHEN 静态规则 —— 先跑 ops/run_materiality_screen.py 或补静态前提
- **s5-rob-02**（rc=None）：落盘被拦：PackError: E9c/E9d2 探针题 s5-rob-02 不落盘：字段 signal_frequency 在条件 (('value_semantics', 'score'),) 下既无 screen 实测记录、也无 FIELD_MATERIAL_WHEN 静态规则 —— 先跑 ops/run_materiality_screen.py 或补静态前提
- **s6-rob-02**（rc=None）：落盘被拦：PackError: E9c/E9d2 探针题 s6-rob-02 不落盘：字段 rebalance_frequency 在条件 (('weighting_scheme', 'equal'),) 下既无 screen 实测记录、也无 FIELD_MATERIAL_WHEN 静态规则 —— 先跑 ops/run_materiality_screen.py 或补静态前提
- **s8-rob-02**（rc=None）：落盘被拦：PackError: E9c/E9d2 探针题 s8-rob-02 不落盘：字段 slippage_reference_price 在条件 (('matching_frequency', 'daily'),) 下既无 screen 实测记录、也无 FIELD_MATERIAL_WHEN 静态规则 —— 先跑 ops/run_materiality_screen.py 或补静态前提

## ② 三控走完整评分器

- oracle 桩 9 题，每族零 finding：✅（effect=100 的 8 题，扣住的 1 题）
- null 桩 9 题，SR 记 0：✅
- filler 桩 on `s7-rob-02`，命中 silent_completion 且 effect 为 null：✅

**三条判据全绿。**明细 `controls.md`。

## ③ 逐族破坏样本

- 18/19 条达成「该族响、其余不响」；造不出 1 条；失败 0 条
- 被证过方向的族（14）：`adjust_fingerprint`、`attribution_conservation`、`calendar`、`declared_reads`、`factor_degeneracy`、`fetch_clock`、`ledger_conservation`、`lookahead`、`nonfinite_propagation`、`optimizer_failure`、`source_status`、`underdetermined`、`unsupported_operator`、`warmup_boundary`
  - **s5-cor-01 / underdetermined**：造不出这个破坏（前提不满足）

## ④ materiality screen（八道探针题）

- material 2/8：`s6-rob-02`、`s7-rob-02`
- 闸门：{'baseline_reproduces': True, 'baseline_detail': [], 'patch_neutral:P-SELL': True, 'patch_neutral_detail:P-SELL': []}
- 其余六题 `inconclusive`：**这套 harness 结构上量不到那六个字段**（三份冻结实现是 S7 的回测引擎），逐条理由见 `materiality_screen.md`。「量不到」不是「没差别」——**不许据此翻锁**。

**七道探针题因此仍被 E9c 拦在落盘之前**（`s7-rob-02` 是唯一有证据、能落盘的那道）。`s6-rob-02` 的证据本轮已量到（N-103），条目在 `materiality_evidence.json`，但写进 `genetask/schema.py::DIVERGENCE_EVIDENCE` 要推任务集版本 —— 本卡无授权，只登记。

## ⑤ 验证验证器报告（五部分）

- 报告：`validator_validation_v1_public.md`
- 判定：通过
- 零误报：是（有产物且零 finding 32，有 finding 0，没跑/没产物 8；零 finding 的题数为 0 时不成立）
- 必命中：是（38/38）
- 三态：是
- 逐族破坏样本：是（18/19，覆盖 14 族）
- 三控：是
