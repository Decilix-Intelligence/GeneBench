# 公开树能跑结算 —— 验收（卡 G2，2026-09-12）

> 上一版公开树是**剔掉答案面**的，后果记在当时的 `EXCLUDED.txt`：
> 「树里还有 **65 个模块** import `scorer/` 或 `reference/`，因此这棵树跑不了。」
> 本卡按用户裁定 N-627 走 B 重打了树（**带全部答案面**）。这份文件证明那个问题没有了。
>
> 判据跑在**公开树自己那棵树里**（`sys.path` 只指 `/data/shared/genebench/release/trees/genebench`，不指 `$GB/repo`）——
> 否则会从仓库里 import 到答案面，测出来的是仓库不是树。

## ① import 闭包

树里 import 了 `scorer` / `reference` 的模块：**141 个**
（上一版说的「65 个」是同一类计数，口径这次写下来：AST 扫 `import` / `from … import`，
取顶层包名 ∈ {scorer, reference}）。

| | 个数 |
| --- | --- |
| 真的 import 成功 | **101** |
| **因答案面缺失而断链**（`ModuleNotFoundError: scorer/reference`） | **0** |
| 其它异常（环境/副作用，**不是剔除造成的**） | 40 |

**断链 0 个 —— 上一轮那个问题不存在了。**

其它异常逐条（留在这里是因为「没断链」不等于「都跑得起来」，两件事要分开说）：

* `genetask.templates.S1.cov_fields.solve` — OracleIOError: 任务规格缺失：/data/shared/genebench/release/trees/genebench/genetask/templates/S1/task.yaml。oracle 必须从**标准位置**读规格 —— 读不到就停，不许用默认值跑出一份与题面无关的 gold  （非断链）
* `genetask.templates.S1.lean_fetch.solve` — OracleIOError: 任务规格缺失：/data/shared/genebench/release/trees/genebench/genetask/templates/S1/task.yaml。oracle 必须从**标准位置**读规格 —— 读不到就停，不许用默认值跑出一份与题面无关的 gold  （非断链）
* `genetask.templates.S1.prov_ledger.solve` — OracleIOError: 任务规格缺失：/data/shared/genebench/release/trees/genebench/genetask/templates/S1/task.yaml。oracle 必须从**标准位置**读规格 —— 读不到就停，不许用默认值跑出一份与题面无关的 gold  （非断链）
* `genetask.templates.S1.source_status.solve` — OracleIOError: 任务规格缺失：/data/shared/genebench/release/trees/genebench/genetask/templates/S1/task.yaml。oracle 必须从**标准位置**读规格 —— 读不到就停，不许用默认值跑出一份与题面无关的 gold  （非断链）
* `genetask.templates.S2.cor_01.solve` — OracleIOError: 任务规格缺失：/data/shared/genebench/release/trees/genebench/genetask/templates/S2/task.yaml。oracle 必须从**标准位置**读规格 —— 读不到就停，不许用默认值跑出一份与题面无关的 gold  （非断链）
* `genetask.templates.S2.eco_01.solve` — OracleIOError: 任务规格缺失：/data/shared/genebench/release/trees/genebench/genetask/templates/S2/task.yaml。oracle 必须从**标准位置**读规格 —— 读不到就停，不许用默认值跑出一份与题面无关的 gold  （非断链）
* `genetask.templates.S2.ops_01.solve` — OracleIOError: 任务规格缺失：/data/shared/genebench/release/trees/genebench/genetask/templates/S2/task.yaml。oracle 必须从**标准位置**读规格 —— 读不到就停，不许用默认值跑出一份与题面无关的 gold  （非断链）
* `genetask.templates.S2.rob_01.solve` — OracleIOError: 任务规格缺失：/data/shared/genebench/release/trees/genebench/genetask/templates/S2/task.yaml。oracle 必须从**标准位置**读规格 —— 读不到就停，不许用默认值跑出一份与题面无关的 gold  （非断链）
* `genetask.templates.S2.rob_02_probe.solve` — OracleIOError: 任务规格缺失：/data/shared/genebench/release/trees/genebench/genetask/templates/S2/task.yaml。oracle 必须从**标准位置**读规格 —— 读不到就停，不许用默认值跑出一份与题面无关的 gold  （非断链）
* `genetask.templates.S3.cor01_wq006_corr.solve` — OracleIOError: 任务规格缺失：/data/shared/genebench/release/trees/genebench/genetask/templates/S3/task.yaml。oracle 必须从**标准位置**读规格 —— 读不到就停，不许用默认值跑出一份与题面无关的 gold  （非断链）
* `genetask.templates.S3.eco01_free_pv.solve` — OracleIOError: 任务规格缺失：/data/shared/genebench/release/trees/genebench/genetask/templates/S3/task.yaml。oracle 必须从**标准位置**读规格 —— 读不到就停，不许用默认值跑出一份与题面无关的 gold  （非断链）
* `genetask.templates.S3.ops01_gtja012_vwap_audit.solve` — OracleIOError: 任务规格缺失：/data/shared/genebench/release/trees/genebench/genetask/templates/S3/task.yaml。oracle 必须从**标准位置**读规格 —— 读不到就停，不许用默认值跑出一份与题面无关的 gold  （非断链）
* `genetask.templates.S3.rob01_wq054_nonfinite.solve` — OracleIOError: 任务规格缺失：/data/shared/genebench/release/trees/genebench/genetask/templates/S3/task.yaml。oracle 必须从**标准位置**读规格 —— 读不到就停，不许用默认值跑出一份与题面无关的 gold  （非断链）
* `genetask.templates.S3.rob02_gtja046_probe.solve` — OracleIOError: 任务规格缺失：/data/shared/genebench/release/trees/genebench/genetask/templates/S3/task.yaml。oracle 必须从**标准位置**读规格 —— 读不到就停，不许用默认值跑出一份与题面无关的 gold  （非断链）
* `genetask.templates.S4.cor_ic_recompute.solve` — OracleIOError: 任务规格缺失：/data/shared/genebench/release/trees/genebench/genetask/templates/S4/task.yaml。oracle 必须从**标准位置**读规格 —— 读不到就停，不许用默认值跑出一份与题面无关的 gold  （非断链）
* `genetask.templates.S4.eco_free_select.solve` — OracleIOError: 任务规格缺失：/data/shared/genebench/release/trees/genebench/genetask/templates/S4/task.yaml。oracle 必须从**标准位置**读规格 —— 读不到就停，不许用默认值跑出一份与题面无关的 gold  （非断链）
* `genetask.templates.S4.ops_audit_trail.solve` — OracleIOError: 任务规格缺失：/data/shared/genebench/release/trees/genebench/genetask/templates/S4/task.yaml。oracle 必须从**标准位置**读规格 —— 读不到就停，不许用默认值跑出一份与题面无关的 gold  （非断链）
* `genetask.templates.S4.rob_probe_setting.solve` — OracleIOError: 任务规格缺失：/data/shared/genebench/release/trees/genebench/genetask/templates/S4/task.yaml。oracle 必须从**标准位置**读规格 —— 读不到就停，不许用默认值跑出一份与题面无关的 gold  （非断链）
* `genetask.templates.S4.rob_sparse_panel.solve` — OracleIOError: 任务规格缺失：/data/shared/genebench/release/trees/genebench/genetask/templates/S4/task.yaml。oracle 必须从**标准位置**读规格 —— 读不到就停，不许用默认值跑出一份与题面无关的 gold  （非断链）
* `genetask.templates.S5.format_audit.solve` — OracleIOError: 任务规格缺失：/data/shared/genebench/release/trees/genebench/genetask/templates/S5/task.yaml。oracle 必须从**标准位置**读规格 —— 读不到就停，不许用默认值跑出一份与题面无关的 gold  （非断链）
* `genetask.templates.S5.free_signal.solve` — OracleIOError: 任务规格缺失：/data/shared/genebench/release/trees/genebench/genetask/templates/S5/task.yaml。oracle 必须从**标准位置**读规格 —— 读不到就停，不许用默认值跑出一份与题面无关的 gold  （非断链）
* `genetask.templates.S5.freq_unstated.solve` — OracleIOError: 任务规格缺失：/data/shared/genebench/release/trees/genebench/genetask/templates/S5/task.yaml。oracle 必须从**标准位置**读规格 —— 读不到就停，不许用默认值跑出一份与题面无关的 gold  （非断链）
* `genetask.templates.S5.null_vs_flat.solve` — OracleIOError: 任务规格缺失：/data/shared/genebench/release/trees/genebench/genetask/templates/S5/task.yaml。oracle 必须从**标准位置**读规格 —— 读不到就停，不许用默认值跑出一份与题面无关的 gold  （非断链）
* `genetask.templates.S5.rank_signal.solve` — OracleIOError: 任务规格缺失：/data/shared/genebench/release/trees/genebench/genetask/templates/S5/task.yaml。oracle 必须从**标准位置**读规格 —— 读不到就停，不许用默认值跑出一份与题面无关的 gold  （非断链）
* `genetask.templates.S6.cor_ledger.solve` — OracleIOError: 任务规格缺失：/data/shared/genebench/release/trees/genebench/genetask/templates/S6/task.yaml。oracle 必须从**标准位置**读规格 —— 读不到就停，不许用默认值跑出一份与题面无关的 gold  （非断链）
* `genetask.templates.S6.eco_swap_cap.solve` — OracleIOError: 任务规格缺失：/data/shared/genebench/release/trees/genebench/genetask/templates/S6/task.yaml。oracle 必须从**标准位置**读规格 —— 读不到就停，不许用默认值跑出一份与题面无关的 gold  （非断链）
* `genetask.templates.S6.ops_ledger_audit.solve` — OracleIOError: 任务规格缺失：/data/shared/genebench/release/trees/genebench/genetask/templates/S6/task.yaml。oracle 必须从**标准位置**读规格 —— 读不到就停，不许用默认值跑出一份与题面无关的 gold  （非断链）
* `genetask.templates.S6.rob_optimizer_failure.solve` — OracleIOError: 任务规格缺失：/data/shared/genebench/release/trees/genebench/genetask/templates/S6/task.yaml。oracle 必须从**标准位置**读规格 —— 读不到就停，不许用默认值跑出一份与题面无关的 gold  （非断链）
* `genetask.templates.S6.rob_underdetermined.solve` — OracleIOError: 任务规格缺失：/data/shared/genebench/release/trees/genebench/genetask/templates/S6/task.yaml。oracle 必须从**标准位置**读规格 —— 读不到就停，不许用默认值跑出一份与题面无关的 gold  （非断链）
* `genetask.templates.S7.cor_reproduce.solve` — OracleIOError: 任务规格缺失：/data/shared/genebench/release/trees/genebench/genetask/templates/S7/task.yaml。oracle 必须从**标准位置**读规格 —— 读不到就停，不许用默认值跑出一份与题面无关的 gold  （非断链）
* `genetask.templates.S7.eco_attribution.solve` — OracleIOError: 任务规格缺失：/data/shared/genebench/release/trees/genebench/genetask/templates/S7/task.yaml。oracle 必须从**标准位置**读规格 —— 读不到就停，不许用默认值跑出一份与题面无关的 gold  （非断链）
* `genetask.templates.S7.ops_audit.solve` — OracleIOError: 任务规格缺失：/data/shared/genebench/release/trees/genebench/genetask/templates/S7/task.yaml。oracle 必须从**标准位置**读规格 —— 读不到就停，不许用默认值跑出一份与题面无关的 gold  （非断链）
* `genetask.templates.S7.rob_tradability.solve` — OracleIOError: 任务规格缺失：/data/shared/genebench/release/trees/genebench/genetask/templates/S7/task.yaml。oracle 必须从**标准位置**读规格 —— 读不到就停，不许用默认值跑出一份与题面无关的 gold  （非断链）
* `genetask.templates.S7.rob_underdetermined.solve` — OracleIOError: 任务规格缺失：/data/shared/genebench/release/trees/genebench/genetask/templates/S7/task.yaml。oracle 必须从**标准位置**读规格 —— 读不到就停，不许用默认值跑出一份与题面无关的 gold  （非断链）
* `genetask.templates.S8.s8_audit_overreach.solve` — OracleIOError: 任务规格缺失：/data/shared/genebench/release/trees/genebench/genetask/templates/S8/task.yaml。oracle 必须从**标准位置**读规格 —— 读不到就停，不许用默认值跑出一份与题面无关的 gold  （非断链）
* `genetask.templates.S8.s8_idempotent.solve` — OracleIOError: 任务规格缺失：/data/shared/genebench/release/trees/genebench/genetask/templates/S8/task.yaml。oracle 必须从**标准位置**读规格 —— 读不到就停，不许用默认值跑出一份与题面无关的 gold  （非断链）
* `genetask.templates.S8.s8_lifecycle.solve` — OracleIOError: 任务规格缺失：/data/shared/genebench/release/trees/genebench/genetask/templates/S8/task.yaml。oracle 必须从**标准位置**读规格 —— 读不到就停，不许用默认值跑出一份与题面无关的 gold  （非断链）
* `genetask.templates.S8.s8_min_slippage.solve` — OracleIOError: 任务规格缺失：/data/shared/genebench/release/trees/genebench/genetask/templates/S8/task.yaml。oracle 必须从**标准位置**读规格 —— 读不到就停，不许用默认值跑出一份与题面无关的 gold  （非断链）
* `genetask.templates.S8.s8_probe_calendar.solve` — OracleIOError: 任务规格缺失：/data/shared/genebench/release/trees/genebench/genetask/templates/S8/task.yaml。oracle 必须从**标准位置**读规格 —— 读不到就停，不许用默认值跑出一份与题面无关的 gold  （非断链）
* `ops.render_calibration_spec` — KeyError: 'source_effectiveness'  （非断链）

## ② 真跑一次结算代码

在公开树里跑它自己的 scorer / 出集 / 标定测试（**不是 import 一下就算数**）：

```
ops/test_scorer_report.py ops/test_scorer_gate.py ops/test_scorer_l3.py ops/test_report_columns.py ops/test_genetask.py ops/test_export_bundle.py ops/test_calibration.py
```

退出码 **0**，汇总：

```
........................................................................ [ 22%]
........................................................................ [ 45%]
........................................................................ [ 67%]
........................................................................ [ 90%]
................................                                         [100%]
320 passed in 24.78s
```

## 结论

公开树**跑得了结算与出表**：import 闭包无断链，scorer 与 genetask 的测试在树内真跑通过。
