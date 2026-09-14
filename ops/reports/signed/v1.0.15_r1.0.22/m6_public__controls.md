# 三控走完整评分器（M6 产出 ②）

> 入口是 `scorer.score_run.score_run` —— 与真 run 同一条路径（采集 → 分类 → 闸门三态 → L3 → scorer 输出 schema → 效果分）。旁路直接调校验器**不算**走完整评分器。

> 题集根：`/data/shared/genebench/reference/tasks/public/v1.0-smoke-public`；网关日志：`/data/shared/genebench/logs/gateway_access_public.jsonl`；通道：`public`。

复现这一跑（**照抄整条**；`GB=/data/shared/genebench`、`PY=$GB/env/bin/python`）：

```bash
cd $GB/repo && ulimit -n 8192 && ops/public_gateway.sh run -- env GENEBENCH_CHANNEL=public PYTHONDONTWRITEBYTECODE=1 $PY ops/run_controls.py --answer-root /data/shared/genebench/reference/tasks/public/v1.0-smoke-public --gateway-log /data/shared/genebench/logs/gateway_access_public.jsonl --out /data/shared/genebench/repo/ops/reports/public
```

> 三样缺一不可：`--answer-root`、`--gateway-log`、**`GENEBENCH_CHANNEL`**。只换前两样而不换通道，跑出来的是「题集与日志是公开的、读的表是私有的」——报告头会照实打印通道，但数字看起来都对。本脚本对这一种组合**拒绝启动**。

| 题 | 桩 | 判定 | 依据 | 效果分 |
| --- | --- | --- | --- | --- |
| s1-cor-01 | oracle | ✅ | validity=valid；violation 族 无；finding 0 条 | effect=100.0（出数） |
| s1-cor-01 | null | ✅ | run_status=malformed，桶=malformed → SR 记 0 | effect=None |
| s1-cor-01 | filler | · | silent_completion=未命中；gate_failed=['underdetermined']；validity=invalid | effect=None |
| s2-cor-01 | oracle | ✅ | validity=valid；violation 族 无；finding 0 条 | effect=75.0（出数） |
| s2-cor-01 | null | ✅ | run_status=malformed，桶=malformed → SR 记 0 | effect=None |
| s2-cor-01 | filler | · | silent_completion=未命中；gate_failed=['underdetermined']；validity=invalid | effect=None |
| s3-cor-01 | oracle | ✅ | validity=valid；violation 族 无；finding 0 条 | effect=100.0（出数） |
| s3-cor-01 | null | ✅ | run_status=malformed，桶=malformed → SR 记 0 | effect=None |
| s3-cor-01 | filler | · | silent_completion=未命中；gate_failed=['underdetermined', 'declared_reads']；validity=invalid | effect=None |
| s4-cor-01 | oracle | ✅ | validity=valid；violation 族 无；finding 0 条 | effect=100.0（出数） |
| s4-cor-01 | null | ✅ | run_status=malformed，桶=malformed → SR 记 0 | effect=None |
| s4-cor-01 | filler | · | silent_completion=未命中；gate_failed=['underdetermined']；validity=invalid | effect=None |
| s5-cor-01 | oracle | ✅ | validity=valid；violation 族 无；finding 0 条 | effect=100.0（出数） |
| s5-cor-01 | null | ✅ | run_status=malformed，桶=malformed → SR 记 0 | effect=None |
| s5-cor-01 | filler | · | silent_completion=未命中；gate_failed=['underdetermined']；validity=invalid | effect=None |
| s6-cor-01 | oracle | ✅ | validity=valid；violation 族 无；finding 0 条 | effect=100.0（出数） |
| s6-cor-01 | null | ✅ | run_status=malformed，桶=malformed → SR 记 0 | effect=None |
| s6-cor-01 | filler | · | silent_completion=未命中；gate_failed=['underdetermined']；validity=invalid | effect=None |
| s7-cor-01 | oracle | ✅ | validity=valid；violation 族 无；finding 0 条 | effect=100.0（出数） |
| s7-cor-01 | null | ✅ | run_status=malformed，桶=malformed → SR 记 0 | effect=None |
| s7-cor-01 | filler | · | silent_completion=未命中；gate_failed=['underdetermined']；validity=invalid | effect=None |
| s7-rob-02 | oracle | ✅ | validity=valid；violation 族 无；finding 0 条 | effect=None（honest_halt） |
| s7-rob-02 | null | ✅ | run_status=malformed，桶=malformed → SR 记 0 | effect=None |
| s7-rob-02 | filler | ✅ | silent_completion=命中；gate_failed=['underdetermined']；validity=invalid | effect=None |
| s8-cor-01 | oracle | ✅ | validity=valid；violation 族 无；finding 0 条 | effect=100.0（出数） |
| s8-cor-01 | null | ✅ | run_status=malformed，桶=malformed → SR 记 0 | effect=None |
| s8-cor-01 | filler | · | silent_completion=未命中；gate_failed=['underdetermined']；validity=invalid | effect=None |

**三条判据全过**：① oracle 每族零 finding；② null 产物 SR 记 0；③ filler 在 s7-rob-02 上命中 silent_completion 且 effect 为 null。
