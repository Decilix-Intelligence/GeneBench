"""卡 4.2：产物采集器 / 评分接口 / 适配层（执行面代码）。

**零 `reference/` 依赖**，与 `runner/inject.py`、`genetask/bundle.py` 同一条纪律：
这些模块跑在 f02，import 到 `reference/` 就等于把答案面拖上执行面
（`ops/test_inject.py::test_t11_execution_plane_modules_never_reach_reference` 盯着）。

本包里凡是**镜像自 `reference/` 的常量**（`origin.UNRESOLVED`、`origin.PAYLOAD_LEAVES`、
`visibility.LOG_DEPENDENT_PROBES`），都在 `ops/test_c42.py` 里配了一条**同源断言** ——
抄一份到执行面而没人盯着，本仓库已经栽过三次（provider 记录值、可交易性词汇、冻结门）。
"""
