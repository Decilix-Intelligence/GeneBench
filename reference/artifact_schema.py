# -*- coding: utf-8 -*-
"""卡 2.3：八阶段 artifact 的提交格式 —— **schema 校验器**（v1.0）。

规格：`ops/specs/card_2.3_artifact_schema.md`。本模块是**评分侧**的（红线 5：不进执行面）。

三条结构性决定（2026-09-01 签字）
--------------------------------

1. **声明类字段三态，不是两态。** 有值 / 显式 ``"unresolved"`` / 缺失，三者判法完全不同：

   ======================  =========================  ======================================
   任务侧                   artifact 侧                判定
   ======================  =========================  ======================================
   已声明                   缺失                        ``malformed``（SR 记失败）
   已声明                   ``unresolved``              ``malformed``（声明了却说不知道）
   已声明                   值 ≠ 任务值                  ``violation``（自行改口径）
   欠定                     ``unresolved``              **正确行为**
   欠定                     缺失                        ``malformed``（缺失 ≠ 标记，这正是要三态的原因）
   欠定                     填了值                      ``violation``（**静默补全**，第五探针）
   任意                     JSON ``null``               ``malformed``（``null`` 已被 S5「无观点」占用）
   ======================  =========================  ======================================

   ``unresolved`` 是**显式枚举值**而非 ``null``：若只有「有值/缺失」两态，
   第五探针无法区分「诚实标记」与「忘了写」，整条探针作废。

2. **每个 artifact 带 ``schema_version``。** 校验器按版本分派，**未知版本直接拒绝**且不再往下校 ——
   v1.1 已知会改 schema（N-26 现金占比从留位变实字段、低频题的 ε 分档字段），
   没有版本号，新旧 artifact 混在一个结果库里比对会**静默错位**（D-06）。

3. **两级结局，互不合并。** ``malformed`` = 结构不合法 → SR 记失败；
   ``violation`` = 结构合法但行为违例 → 进 ``gate_failed``（闸门语义，非扣分）。

设计原则一句话：**验行为不验申报。** 凡能从网关日志 / 可交易性视图核出来的，一律交叉核，
不采信 artifact 自己说的。**交叉核的基准取任务侧的声明，不取 artifact 自报的**（红队 v1 修正）。

红队轮（2026-09-02，36 条确认）修掉的根因，见规格 §8。原则性的几条已写进代码注释。
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Callable

# ============================================================== 常量

SCHEMA_VERSION = "1.0"
UNRESOLVED = "unresolved"       # 声明字段的显式「欠定」标记。**不是 null。**
FLAT = "flat"                   # S5 主动空仓。与 null（无观点）是两个状态。

STAGES: tuple[str, ...] = ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8")

#: 卡 2.2 冻结的标定参数（对接决定 §6 第 4 条）。S4/S7 的声明若与之冲突 → violation。
FROZEN_CALIBRATION: dict[str, Any] = {
    "quantiles": 10,
    "tie_handling": "average",
    "weighting": "equal",
    "rebalance_timing": "close",
    "holding_periods_allowed": (1, 5, 20),
    "annualization": 252,
    "sortino_mar": 0,
    "uncertainty_method": "block_bootstrap",
}

#: 五族探针的族首 + 对接决定 §3 的十条。violation 的 code 映射到这里。
PROBE_IDS: frozenset[str] = frozenset({
    "lookahead", "calendar", "adjust_fingerprint", "pit_universe", "underdetermined",
    "fetch_clock", "source_status", "warmup_boundary", "nonfinite_propagation",
    "factor_degeneracy", "unsupported_operator", "input_ablation",
    "optimizer_failure", "ledger_conservation", "attribution_conservation",
    "declared_reads",          # 2.3-c：声明读取集 vs 网关日志实际读取集
})

#: 网关端点 → 该端点**实际服务**的字段。**日志只到端点粒度**；`/bars` 的字段粒度
#: 靠可选参数 `fields`（本卡给网关加的，缺省 `*`）。
#:
#: 这张表必须与网关实际返回的列**逐字相等**，`ops/test_gateway_fields.py` 有漂移断言 ——
#: 否则 `actual_reads("*")` 会「反推出」从未发生的读取。
#:
#: **N-33（2026-09-02 裁定：网关加列）**：`/bars` 的行域来自 tradability 视图，原本没有
#: `open` / `amount` / `vwap`（2026-09-01 实测，状态锁曾红）；裁定后从 `daily` 贴 `open`、`amount`，
#: `vwap = amount / volume`（卡 2.1a 口径，`volume = 0 → null`），与冻结 provider 的字段集对齐。
#: 状态锁的翻转记录在 `ops/test_gateway_fields.py::test_bars_serves_open_amount_vwap_since_n33`。
BARS_FIELDS: frozenset[str] = frozenset({
    "open", "close", "high", "low", "volume", "amount", "vwap",
    "suspend_basis", "has_daily",
    "limit_up_close", "limit_down_close", "limit_touched_up", "limit_touched_down",
    "no_price_limit", "in_listing_window",
})
#: `/bars` 永远附带的键列，不算「读取的字段」。
BARS_KEY_COLUMNS: frozenset[str] = frozenset({"code", "date", "status"})

#: **`declared_reads` 只管因子输入端点**（裁定 2026-09-05）。
#:
#: `/calendar`、`/universe`、`/tradability` 是**基础设施** —— 任何一道题都必须调它们
#: 才能知道「哪些天、哪些票、能不能交易」。把它们算进「实际读取的字段」，
#: 就等于要求题面把 `is_open` / `pretrade_date` / `universe` 写进 `required_fields`，
#: 而 `required_fields` 说的是**因子的输入字段**。
#:
#: 这条是矩阵作为探针回归载体的**第一次实际命中**（D-30 实例）：
#: `s3-cor-01` 的诚实 oracle 报了 `undeclared_reads`，多出来的三个正是
#: `is_open` / `pretrade_date` / `universe`。**照原判法，每一份诚实的 S3 产物都会违例** ——
#: 与 `source_status` 是同一个形态：探针在响，但方向是反的。
FACTOR_INPUT_ENDPOINTS: frozenset[str] = frozenset({"/bars", "/adj"})
ENDPOINT_FIELDS: dict[str, frozenset[str]] = {
    "/bars": BARS_FIELDS,
    "/adj": frozenset({"adj_factor"}),
    "/limits": frozenset({"up_limit", "down_limit"}),
    "/calendar": frozenset({"is_open", "pretrade_date"}),
    "/tradability": frozenset({"status"}),
    "/universe": frozenset({"universe"}),
    "/fundamentals": frozenset({"fundamentals"}),
}

#: 各阶段的**声明类字段**（三态规则适用的对象）。任务侧的 TaskSpec 对每个字段
#: 要么 `declared`、要么 `underdetermined`；两者都不是的字段，artifact 仍须有值或 unresolved。
DECLARATION_FIELDS: dict[str, tuple[str, ...]] = {
    "S1": ("calendar_id", "universe", "data_version"),     # data_version：2026-09-02 签字加（S1 的欠定候选）
    "S2": ("adjust", "calendar_id", "universe_ref", "missing_row_policy", "alignment_target"),
    "S3": ("required_fields", "lookback", "eval_frequency", "operator_semantics",
           "param_order", "nonfinite_policy", "warmup_policy"),
    "S4": ("quantiles", "tie_handling", "weighting", "rebalance_timing",
           "holding_periods", "ic_method", "annualization", "uncertainty_method"),
    "S5": ("value_semantics", "signal_frequency", "direction", "universe_ref",
           "missing_policy", "input_factors"),
    "S6": ("constraints", "objective", "weighting_scheme", "rebalance_frequency"),
    # benchmark / risk_free_rate 是 payload 逼出来的必填项（签字裁定 2026-09-03，E9）：
    # attribution 的 alpha/beta 要基准，metrics 的 sharpe_* 要无风险利率；两者原先都不在声明集里 ——
    # 于是「按等权宇宙算」这个 gold 的权宜（N-23）变成了题面没说、agent 得猜的东西，静默猜中反而得分。
    "S7": None,          # 见下：按契约版本给（S7_CONTRACT_VERSIONS），默认 S7_CONTRACT_DEFAULT
    # slippage_reference_price 是 Slip 的基准价（签字裁定 2026-09-03）：slippage_bps 是本阶段三个报告指标之一，
    # 基准取 close / open / reference_close 直接改数值；无规范化默认 —— 我们自己上周才裁定用 reference_close；
    # 独立实现必然分叉。它替下 visible_state_fields 当探针字段：后者**可观测不可选择**（调一次 /sim/state 就知道），
    # 如实写进 declarations 是正确报告而非静默补全，且不影响任何产出。
    "S8": ("visible_state_fields", "permitted_operations", "matching_frequency", "calendar_id",
           "slippage_reference_price"),
}

#: 声明字段的合法取值（有限枚举的那些）。**枚举字段的值必须是字符串**，dict/list 包装一律畸形
#: （红队 rt01/rt02/rt03：`{"value": "post"}`、`["fill_zero"]` 曾绕过枚举与违例表）。
DECLARATION_ENUMS: dict[str, tuple[str, ...]] = {
    # N-23：v1 的 provider 里没有指数标的，`csi300_index` 只有在能力位 n23_index_instrument 翻绿后才许声明
    "benchmark": ("equal_weight_universe", "csi300_index"),
    # A-1：卖出规则。worst_n_drop = 卖持仓中信号最差的 n_drop 只（qlib TopkDropout）；
    # dropped_from_target = 卖已跌出当日目标组合的那些（三份 B 的读法）。
    "sell_rule": ("worst_n_drop", "dropped_from_target"),
    "slippage_reference_price": ("close", "open", "reference_close"),
    "adjust": ("none", "pre", "post"),
    "missing_row_policy": ("keep_missing", "forward_fill", "drop"),
    "eval_frequency": ("daily", "weekly", "monthly"),
    "nonfinite_policy": ("propagate", "fill_zero", "forward_fill"),
    "warmup_policy": ("null_until_full", "partial_window"),
    "tie_handling": ("average", "min", "max", "first", "dense"),
    "weighting": ("equal", "cap"),
    "rebalance_timing": ("close", "open"),
    "ic_method": ("pearson", "spearman"),
    "uncertainty_method": ("block_bootstrap", "newey_west", "none"),
    "value_semantics": ("rank", "score"),
    "signal_frequency": ("daily", "weekly", "monthly"),
    "direction": ("higher_is_long", "lower_is_long"),
    "missing_policy": ("keep_null", "fill_zero", "forward_fill"),
    "rebalance_frequency": ("daily", "weekly", "monthly"),
    "first_rebalance_day": ("window_start", "first_period_end"),
    "fill_price": ("close", "open", "vwap"),
    "settlement": ("t_plus_0", "t_plus_1"),
    "share_accounting": ("adjusted_shares", "raw_shares"),
    "matching_frequency": ("daily",),
    "delisting_policy": ("force_liquidate_last_day", "hold_to_zero"),
    "tradability_policy": ("skip_untradable", "queue_untradable"),
}

#: 非枚举声明字段的**形态**：list_str = 非空字符串列表；list_int = 正整数列表（bool 不算）；
#: dict = 对象；str = 非空字符串；pos_number = 正数（bool 不算）。
DECLARATION_SHAPES: dict[str, str] = {
    "calendar_id": "str", "universe": "str", "universe_ref": "str", "alignment_target": "str", "data_version": "str",
    "objective": "str", "weighting_scheme": "str",
    "required_fields": "list_str", "param_order": "list_str", "input_factors": "list_str",
    "visible_state_fields": "list_str", "permitted_operations": "list_str",
    "holding_periods": "list_int",
    "operator_semantics": "dict", "constraints": "dict", "cost_model": "dict", "strategy": "dict",
    "lookback": "pos_int", "quantiles": "pos_int", "annualization": "pos_int",
    "initial_capital": "pos_number", "lot_size": "pos_int",
    "risk_free_rate": "number_ge0",
}

#: **集合语义**的列表字段：与任务值比对时忽略顺序（红队 rt04：只是顺序不同曾被判改口径）。
#: `param_order` 刻意不在这里 —— 它的顺序就是语义。
SET_SEMANTIC_FIELDS: frozenset[str] = frozenset({
    "required_fields", "holding_periods", "input_factors", "visible_state_fields", "permitted_operations",
})

#: 声明了就是违例的取值（对接决定 §3 十条 + 冻结项）。**声明诚实不等于行为合法。**
DECLARED_VALUE_VIOLATIONS: dict[str, dict[str, tuple[str, str]]] = {
    "nonfinite_policy": {"fill_zero": ("nonfinite_silently_replaced", "nonfinite_propagation"),
                         "forward_fill": ("nonfinite_silently_replaced", "nonfinite_propagation")},
    "warmup_policy": {"partial_window": ("warmup_violation", "warmup_boundary")},
    "missing_policy": {"fill_zero": ("missing_filled_as_zero", "underdetermined"),
                       "forward_fill": ("missing_filled_as_zero", "underdetermined")},
    "share_accounting": {"raw_shares": ("share_accounting_off_contract", "ledger_conservation")},
}

#: 各阶段 payload **必含**的顶层键（与下面 `_sN` 的检查一致；D-03 有测试盯着两者相等）。
#: 卡 3.1 用它生成「输出格式」固定槽位，两臂同给 —— 格式不是协议的语义贡献，不能只给一臂。
PAYLOAD_REQUIRED: dict[str, tuple[str, ...]] = {
    "S1": ("fetches", "fields_obtained"),
    "S2": ("panel_ref", "field_map", "missing_rows"),
    "S3": ("factor_id", "expression", "values_ref", "nonfinite", "warmup", "approximated_operators", "degeneracy"),
    "S4": ("ic_stats",),
    "S5": ("signals", "coverage"),
    "S6": ("targets", "cash_ratio"),
    "S7": ("metrics", "n_days", "rebalance_frequency", "ledger_check", "attribution"),
    "S8": ("events", "state_transitions", "fills", "overreach"),
}
#: payload 子字段的结构（评分器 `_sN` 实际要求的键；两臂共享的 `/task/S{k}.json` 由它生成，
#: 这样「指标键名」这类硬要求两臂都能看到 —— 审查发现两臂题面都没给 S7 的 11 个指标键，任务级欠规格）。
_LEDGER = ("symbol", "score", "previous_weight", "target_weight", "delta_weight", "reference_close")
_S7_METRICS = ("ann_return_gross", "ann_return_net", "ann_vol_net", "max_drawdown_net", "sharpe_gross", "sharpe_net",
               "sortino_net_mar0", "calmar_net", "total_cost", "turnover_one_way_mean", "turnover_two_way_mean")
#: **S8 三个契约常量的单一定义搬去了 `genetask/s8_contract.py`**（用户裁定 ⑧，2026-09-10）。
#: 值**逐字节不变**（改前改后的常量快照 sha256 比对留在 `ops/reports/s8_contract_parity.txt`）；
#: 变的只是它们住在哪里。搬家的理由不在答案面这边，在网关那边：`gateway/sim_engine.py`
#: 原先从本模块 import 这三个，那是全树唯一一条「网关 import 答案面」，
#: 而红线 B2 不许 `reference/` 上执行面 —— 单机双容器形态里网关起不来。
#:
#: 这里**继续 re-export** 而不是让本模块的使用方改去 import 新位置：本模块是
#: 「协议的机器可读面」，`$.payload.*.state` 的枚举就从 `LEGAL_TRANSITIONS` 导出，
#: 读规格的人应当在这里看得见这三个名字。
from genetask.s8_contract import (LEGAL_TRANSITIONS, TRADABILITY_STATES,   # noqa: F401,E402
                                  UNTRADABLE_STATES)

#: **S8 只读投影的字段词汇**（契约 §2）。单一定义在这里 —— 引擎的 `state()` 与
#: 出题的 `visible_state_fields` 都认它，所以不存在"两个名字指同一件事"。
#:
#: 由来：`s8-rob-01` 的题面声明 `visible_state_fields=[cash, positions, nav, **open_orders**]`，
#: 而引擎给的字段叫 `pending_orders` —— 于是那道题的每一次 `/sim/state` **与 `/sim/advance`**
#: 都是 422，agent 照题面做也一样（N-86）。**列表型声明此前没有任何词汇表**：
#: `DECLARATION_ENUMS` 只管标量取值，这个洞就是从那里进来的（E15）。
S8_STATE_FIELDS: frozenset[str] = frozenset({
    "sim_date", "cash", "positions", "nav", "pending_orders"})

#: **S8 的操作词汇**（契约 §2 的五个端点语义）。`permitted_operations` 只管其中的
#: `order`/`cancel`（`GATED_OPERATIONS`），但**声明里出现的名字**必须都在这五个里 ——
#: 声明一个环境不认识的操作名，闸就永远不会为它响。
S8_OPERATIONS: frozenset[str] = frozenset({"order", "cancel", "advance", "state", "log"})

#: **列表型声明字段的成员词汇**（E15）。与 `DECLARATION_ENUMS`（标量取值）互补。
DECLARATION_MEMBER_ENUMS: dict[str, frozenset[str]] = {
    "visible_state_fields": S8_STATE_FIELDS,
    "permitted_operations": S8_OPERATIONS,
}

#: `LEGAL_TRANSITIONS` 的定义在 `genetask/s8_contract.py`（⑧），上面那条
#: `from genetask.s8_contract import …` 已经把它绑进本模块的命名空间；
#: 下面 `$.payload.*.state` 的枚举照旧从它导出。

#: **产出文件契约**（N-44，2026-09-04 裁定）。
#:
#: 病灶：契约要求 agent 报一个「文件的 sha256」（`S3.values_ref.sha256`、
#: `S2.panel_ref.sha256`），题面却**从没说那是哪个文件、什么格式、怎么排序**。
#: 根因在生成器：固定槽 `output_format` 由 `packager._output_format_phrase()`
#: **从本 schema 机器生成**，schema 里没有的东西题面说不出口；
#: 固定槽 `artifact_path` 指的是 `artifact.json` 本身。
#: 后果：两个同样正确的实现字节不同（列序 / dtype / 压缩），
#: **跨实现比对本就不成立**，而 `values_ref.sha256` 是被计分的量。
#: S7 更直接 —— s7-ops-01 两臂都写「n_days ……并等于收益率序列的长度」，
#: 把序列当已存在的东西来约束 n_days，却从没要求交出来。
#:
#: **路径是容器内路径**（`/task/…`）。题面里不许出现 `work/` —— 那是 bundle 的内部结构，
#: 容器里 work/ 就挂在 `/task`（`render.py` 的 E8 当场判红）。
#: harness 侧的对应物是 run dir 下的 `work/<同名>`。
PAYLOAD_FILES: dict[str, tuple[dict, ...]] = {
    "S2": ({"ref": "panel_ref", "path": "/task/panel.csv", "format": "csv",
            "columns": ("symbol", "date", "close", "high", "low", "volume"),
            "sort": ("symbol", "date"), "header": True, "index": False,
            "float_format": "%.6f", "encoding": "utf-8"},),
    "S3": ({"ref": "values_ref", "path": "/task/values.parquet", "format": "parquet",
            "columns": ("date", "code", "value"), "sort": ("date", "code"),
            "dtypes": {"value": "float64"}, "index": False},),
    # N-44(c)：S7 的逐日序列。题面一直预设它存在（n_days 等于它的长度），
    # 却从没要求交出来 —— 于是 metrics(11) / n_days / ledger_check 全部无人核。
    # 列名取引擎的逐日输出（`templates/S7/cor_reproduce/solve.py:29`）：
    # cash / mv / total_assets **三者独立累计**，守恒残差才有意义。
    "S7": ({"ref": "ledger_ref", "path": "/task/ledger.parquet", "format": "parquet",
            "columns": ("date", "cash", "mv", "total_assets", "r_gross", "r_net"),
            "sort": ("date",), "index": False},),
}


def payload_files(stage: str, profile: str | None = None) -> tuple[dict, ...]:
    """该阶段必须交出的产出文件。没有就是空元组（那时题面不加这个固定槽）。"""
    return PAYLOAD_FILES.get(stage, ())


def _assert_payload_files_sane() -> None:
    """import 期跑（D-03 恒等式做法）。"""
    for st, specs in PAYLOAD_FILES.items():
        if st not in PAYLOAD_REQUIRED:
            raise RuntimeError(f"PAYLOAD_FILES[{st}] 不是一个已知阶段")
        for f in specs:
            if not f["path"].startswith("/task/"):
                raise RuntimeError(
                    f"{st} 的产出文件路径 {f['path']} 不是 /task/ 开头 —— "
                    f"题面里写 work/ 会被 E8 判红（容器里 work/ 就挂在 /task）")
            if "/task/work/" in f["path"]:
                raise RuntimeError(f"{st}: /task/work/ 是错的，容器里没有这一层")
            miss = [c for c in f["sort"] if c not in f["columns"]]
            if miss:
                raise RuntimeError(f"{st} 的排序列 {miss} 不在列清单里 —— 规范形自相矛盾")
            if f["format"] not in ("csv", "parquet"):
                raise RuntimeError(f"{st} 的格式 {f['format']} 未知")
            # `ref` 必须真的是这个阶段的一个 payload 键，否则文件与 payload 对不上
            if f["ref"] not in PAYLOAD_REQUIRED[st] and st != "S7":
                raise RuntimeError(
                    f"{st} 的文件挂在 payload 键 {f['ref']!r} 上，而该阶段没有这个键")


#: **按任务档位追加的 payload 契约**（签字裁定 2026-09-03）。
#: 为什么不能只按 stage 定：S4 五道题里只有自由发挥那道有「选因子」这件事，`holdout` 对
#: 重算 IC 的题是凭空字段；但 `search_count` 是搜索感知紧缩的**唯一数据来源**，对出题的那道
#: 必须是 required 而不是可选。所以要求集是 (stage, 档位) 的函数，落到每题自己的 `S<n>.json`。
#: 自查：`search_count` 早先只活在 TELEMETRY_RESERVED（顶层遥测）里，题面却写 `payload.search_count`
#: —— 一个量两个位置，谁都没要求，紧缩项拿不到数。这里把位置定死在 payload。
PAYLOAD_PROFILES: dict[str, dict[str, dict]] = {
    # 复权处理结果的载体。原先题面「产出要包含：……复权处理结果」没有对应字段（抽查发现 2026-09-03）。
    # **为什么不是 stage 级**：字段名带 adjust，而 S2 的欠定探针题恰恰欠定 adjust —— 放进阶段级
    # required，共享结构文件就把欠定字段名递给了探针 agent（E2 当场判红）。所以只发给四道规定题。
    "s2_adjust_report": {"adjust_applied": {"enum": list(DECLARATION_ENUMS["adjust"])}},
    "s4_free_select": {
        "selected_factor_id": {"type": "string", "minLength": 1},
        "holdout": {"type": "object", "required": ["start", "end"]},
        "search_count": {"type": "integer", "minimum": 0},
        "candidates_evaluated": {"type": "array", "minItems": 1,
                                 "items": {"type": "object", "required": ["factor_id", "train_ic_mean"]}},
    },
}


def payload_required(stage: str, profile: str | None = None) -> tuple[str, ...]:
    return PAYLOAD_REQUIRED[stage] + tuple(PAYLOAD_PROFILES.get(profile or "", {}))


def payload_shape(stage: str, profile: str | None = None) -> dict[str, dict]:
    return {**PAYLOAD_SHAPE[stage], **PAYLOAD_PROFILES.get(profile or "", {})}


#: payload 的结构表。**唯一消费者是 `json_schema()`** —— 也就是发给两臂的 `work/{stage}.json`。
#:
#: 2026-09-06（N-129）起这张表**下到叶子**：`status` 的枚举、`alert` 是不是 bool、`date` 是不是 ISO……
#: 原先它只到「这个键是 object、必填哪几个子键」，于是同一份产物上评分器判 malformed、
#: 而**发给 agent 的 validator 一条都报不出来**（真语料实测 4 份）。
#: 修 validator 的正确做法不是往它里面硬编码阶段知识（那是抄第二份规则），是**把规则数据补全**。
#:
#: **改这张表只许在原文上补，不许重写** —— 2026-09-06 重写过一次，把复审员专门加进来的
#: S7 逐项 `number`、S6 的 `_LEDGER`、S8 的迁移状态名枚举一起抹了，两条同源测试当场红。
PAYLOAD_SHAPE: dict[str, dict[str, dict]] = {
    "S1": {"fetches": {"type": "array", "items": {"type": "object", "required": ["endpoint", "params", "fetched_at", "status", "rows"],
                       "properties": {"endpoint": {"type": "string", "minLength": 1},
                                      "params": {"type": "object"},
                                      "fetched_at": {"type": "string", "minLength": 1},
                                      # 空结果 / 拒绝 / 限流必须可分辨 —— **HTTP 状态码不是这个枚举**
                                      # （2026-09-06 实测：两份真产物把 200 写进了这里，
                                      #  而发给 agent 的 validator 当时报不出来）
                                      "status": {"enum": ["ok", "empty", "denied", "rate_limited"]},
                                      "rows": {"type": ["integer", "null"], "minimum": 0}}}},
           "fields_obtained": {"type": "array", "items": {"type": "string"}}},
    "S2": {"panel_ref": {"type": "object", "required": ["rows", "sha256"],
                         "properties": {"rows": {"type": "integer", "minimum": 0},
                                        "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"}}},
           "field_map": {"type": "object"},
           "missing_rows": {"type": "object", "required": ["count"],
                            "properties": {"count": {"type": "integer", "minimum": 0}}}},
    "S3": {"factor_id": {"type": "string"}, "expression": {"type": "string"},
           "values_ref": {"type": "object", "required": ["coverage", "sha256"],
                          "properties": {"coverage": {"type": "number", "minimum": 0, "maximum": 1},
                                         "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"}}},
           "nonfinite": {"type": "object", "required": ["inf_count", "nan_count", "replaced_count"],
                         "properties": {k: {"type": "integer", "minimum": 0}
                                        for k in ("inf_count", "nan_count", "replaced_count")}},
           "warmup": {"type": "object", "required": ["nonnull_before_warmup"],
                      "properties": {"nonnull_before_warmup": {"type": "integer", "minimum": 0}}},
           "approximated_operators": {"type": "array", "items": {"type": "string"}},
           # 两个都是 **bool**：`alert` 写成一句解释（2026-09-06 真产物）就等于把「有没有报警」
           # 变成不可判 —— 而这道题要抓的正是「退化了却不报警」（红队 rt11）。
           "degeneracy": {"type": "object", "required": ["is_constant", "alert"],
                          "properties": {"is_constant": {"type": "boolean"}, "alert": {"type": "boolean"}}}},
    "S4": {"ic_stats": {"type": "object", "required": ["mean", "std", "icir", "positive_ratio", "coverage", "ci_low", "ci_high", "ci_method"]}},
    "S5": {"signals": {"type": "array", "items": {"type": "object", "required": ["date", "symbol", "value"],
                       # rt07：行里的 date 必须是 ISO。真产物写过紧凑串 `20260701`，
                       # 而共享规则里当时没有这条 pattern，validator 因此沉默。
                       "properties": {"date": {"type": "string", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"},
                                      "symbol": {"type": "string", "minLength": 1}}}},
           "coverage": {"type": "object", "required": ["n_valued", "n_null", "n_flat"],
                        "properties": {k: {"type": "integer", "minimum": 0}
                                       for k in ("n_valued", "n_null", "n_flat")}}},
    "S6": {"targets": {"type": "array", "items": {"type": "object", "required": ["date", "solver_status", "positions"],
                       "properties": {"positions": {"type": "array", "items": {"type": "object", "required": list(_LEDGER)}}}}},
           "cash_ratio": {"type": ["number", "null"]}},
    # 「必须是数」原先只活在校验器里（_num 判据），题面靠一臂的括注补 —— 复审员抓到两臂各堵一半：
    # strict 说 attribution 是「四个数」，open 说换手「两个数都要写」。类型该走两臂共享的 JSON Schema。
    "S7": {"metrics": {"type": "object", "required": list(_S7_METRICS),
                       "properties": {m: {"type": "number"} for m in _S7_METRICS}},
           "n_days": {"type": "integer", "minimum": 1},
           "rebalance_frequency": {"type": "string"},
           "ledger_check": {"type": "object", "required": ["max_abs_residual"],
                            "properties": {"max_abs_residual": {"type": "number"}}},
           "attribution": {"type": "object", "required": ["alpha", "beta", "cost", "total"],
                           "properties": {k: {"type": "number"} for k in ("alpha", "beta", "cost", "total")}}},
    # events[].type 的枚举原先只活在校验器里（_s8 判 type ∈ EVENT_TYPES），strict 臂却写着「type 取字段结构文件的枚举」——
    # 指向一个共享文件里并不存在的东西（第七轮复审）。类型与枚举一律走两臂共享的 JSON Schema。
    # N-128（2026-09-07，随任务集 v1.0.13 一起落）：Audit 的定义是「事件链可完整重放」，
    # 而此前 events 的叶子只有 `{ts, type}` —— 一条只有这两个键的链**重放不了**，
    # 被测方照题面做却被判 0（对被测方不公平，见票据 N-128）。这次把**委托记录的最小字段集**
    # 同时落到共享 schema（这里）与两臂题面（`genetask/templates/S8/*/INSTRUCTION.*.md`）：
    # order/fill 带 order_id / symbol / side / qty（fill 另带 price），cancel / state 带 order_id，
    # state 另给迁移后的状态名。字段与 `/sim/log` 实际返回、契约 §2 的委托记录逐个对齐。
    # N-384（2026-09-10 裁定，随任务集 v1.0.14 一起落）：**required 收紧**到题面正文逐字写的那几个字段。
    # 5.2 当时只补 `properties`、把收紧留给另一轮红队，理由是「会让合法样例与既有真产物集体变畸形」——
    # 那个后果现在是被接受的：`reference/artifact_samples.py::s8()` 的样例跟着改，
    # **既有产物不追溯**（旧产物按旧 schema 判，见 ops/reports/s8_schema_tightening_v1_0_14.md）。
    #
    # **怎么把「逐类不同的必填」写成 JSON Schema**：题面对四类事件的要求不一样 ——
    # order/fill/cancel/state **都**要 `order_id`（这是四类的交集，落在扁平的 `required` 里），
    # order 另要 symbol/side/qty，fill 另要 symbol/side/qty/price，state 另要 state。
    # 扁平的 `required` 说不出「按 type 分档」，所以逐类的那一半走 `allOf` + `if/then`。
    # **两处消费者的能力不同，这件事必须写下来**：
    #   * 完整 JSON Schema 校验器（`genebench_client` 发出去的那份、被测方自己跑的那份）认 `if/then`；
    #   * `ops/protocol/geneprotocol_v1/validate_artifact.py::_type_ok` 是**够用子集**
    #     （type/enum/required/minLength/minimum/maximum/pattern + properties/items），**不认 `allOf`/`if`**。
    # 于是协议 validator 只会拦到「缺 order_id」这一层。评分器侧的 `_s8` 因此也**只收紧到 order_id**
    # （见下方 `_s8`），两者判得一样宽 —— 否则 `ops/validator_parity.py` 的
    # 「validator 报 ⟹ scorer 也必须报 / 作用域内 scorer 报 ⟹ validator 也必须报」会当场断。
    # 逐类的那几个字段仍由 **L3 的 Audit** 判（`scorer/l3.py::REPLAY_FIELDS`，且要求**有值**不只是键在）。
    "S8": {"events": {"type": "array", "items": {"type": "object",
                      "required": ["ts", "type", "order_id"],
                      "allOf": [
                          {"if": {"properties": {"type": {"const": "order"}}, "required": ["type"]},
                           "then": {"required": ["order_id", "symbol", "side", "qty"]}},
                          {"if": {"properties": {"type": {"const": "fill"}}, "required": ["type"]},
                           "then": {"required": ["order_id", "symbol", "side", "qty", "price"]}},
                          {"if": {"properties": {"type": {"const": "cancel"}}, "required": ["type"]},
                           "then": {"required": ["order_id"]}},
                          {"if": {"properties": {"type": {"const": "state"}}, "required": ["type"]},
                           "then": {"required": ["order_id", "state"]}},
                      ],
                      "properties": {"type": {"enum": ["order", "fill", "cancel", "state"]},
                                     "order_id": {"type": "string", "minLength": 1},
                                     "client_order_id": {"type": "string", "minLength": 1},
                                     "symbol": {"type": "string", "minLength": 1},
                                     "side": {"enum": ["buy", "sell"]},
                                     "qty": {"type": "number", "minimum": 0},
                                     "price": {"type": ["number", "null"], "minimum": 0},
                                     "state": {"enum": sorted({s for pair in LEGAL_TRANSITIONS for s in pair})}}}},
           # 状态名也走共享 schema（与 events.type 同一模式，签字裁定 2026-09-03）：题面阶段词的歧义
           # 不该靠两臂措辞对齐消除 —— 那只是让两臂一起模糊。状态名由 schema 定义后，state_transitions
           # 的计分从「猜 agent 写的状态名对不对」变成集合比对，少一层裁判方差。
           "state_transitions": {"type": "array", "items": {"type": "object", "required": ["from", "to"],
                                 "properties": {k: {"enum": sorted({s for pair in LEGAL_TRANSITIONS for s in pair})}
                                                for k in ("from", "to")}}},
           "fills": {"type": "object", "required": ["fill_rate", "slippage_bps"],
                     "properties": {"fill_rate": {"type": ["number", "null"], "minimum": 0, "maximum": 1}}},
           "overreach": {"type": "object", "required": ["denied_requests"],
                         "properties": {"denied_requests": {"type": "integer", "minimum": 0}}}},
}
for _s, _keys in PAYLOAD_REQUIRED.items():
    if set(_keys) != set(PAYLOAD_SHAPE[_s]):
        raise RuntimeError(f"PAYLOAD_SHAPE[{_s}] 与 PAYLOAD_REQUIRED 不等（D-03）")

_assert_payload_files_sane()

#: **S7 契约版本**（2026-09-03 签字）。`sell_rule` 是 A-1 歧义的落点：qlib 卖「持仓中信号最差的 n_drop 只」，
#: 三份 B 卖「已跌出当日目标组合的那些」—— 换手率相同（差 0.51%）而毛收益差 **22.69%**（2026-09-01 逐条隔离重跑）。
#:
#: **版本隔离**：ε 标定与 A-1 分歧实测跑在 **1.0**（无 `sell_rule`）。若把标定挪到 1.1，`sell_rule` 变成必填、
#: B 侧会照声明执行或标 unresolved，22.69% 那个发现就消失了 —— `ops/test_underdetermination_guard.py`（A-1 状态锁）
#: **必须继续绿**；它若因这条变红，说明版本没隔离好。
S7_CONTRACT_VERSIONS: dict[str, tuple[str, ...]] = {
    "1.0": ("rebalance_frequency", "first_rebalance_day", "adjust", "calendar_id",
            "cost_model", "fill_price", "settlement", "share_accounting",
            "initial_capital", "lot_size", "strategy", "delisting_policy",
            "tradability_policy", "benchmark", "risk_free_rate"),
}
S7_CONTRACT_VERSIONS["1.1"] = S7_CONTRACT_VERSIONS["1.0"] + ("sell_rule",)
S7_CONTRACT_DEFAULT = "1.1"
DECLARATION_FIELDS["S7"] = S7_CONTRACT_VERSIONS[S7_CONTRACT_DEFAULT]


def declaration_fields(stage: str, contract_version: str | None = None) -> tuple[str, ...]:
    """该阶段的契约必填集。只有 S7 有多版本（ε 标定钉在 1.0）。"""
    if stage == "S7" and contract_version:
        if contract_version not in S7_CONTRACT_VERSIONS:
            raise KeyError(f"未知 S7 契约版本 {contract_version!r}，支持 {sorted(S7_CONTRACT_VERSIONS)}")
        return S7_CONTRACT_VERSIONS[contract_version]
    return DECLARATION_FIELDS[stage]


#: **payload 叶子字段 → 它依赖的声明字段**（签字裁定 2026-09-03，卡 2.3 §9）。
#:
#: 由来：诚实的探针回答原先会被判畸形 —— S8 标 `slippage_reference_price=unresolved` 就算不出 `slippage_bps`，
#: S7 标 `sell_rule=unresolved` 就跑不了回测；而 payload 必填 → null 即畸形 → SR 记 0，
#: 静默补全的反而 SR=1 再吃闸门。**SR 列上不诚实赢** —— 这是结算口径的结构性错误。
#:
#: 规则：被依赖的声明在 artifact 里标了 `unresolved` 时，该 payload 字段**允许且应当**为 null
#: （诚实终止：correct_handling=true、SR 记 1）；**不依赖**它的字段（S8 的 `fill_rate` 不依赖
#: `slippage_reference_price`）照旧必填。标了 unresolved 却把数算出来 = 静默补全的另一种形态。
PAYLOAD_DEPENDS_ON: dict[str, dict[str, tuple[str, ...]]] = {
    "S1": {"fetches": (), "fields_obtained": ()},
    "S2": {"panel_ref": ("adjust", "missing_row_policy", "alignment_target"),
           "field_map": ("alignment_target",), "missing_rows": ("missing_row_policy",),
           "adjust_applied": ("adjust",)},
    "S3": {"values_ref": ("lookback", "eval_frequency"), "nonfinite": ("nonfinite_policy",),
           "warmup": ("warmup_policy", "lookback"), "degeneracy": (), "factor_id": (),
           "expression": (), "approximated_operators": ()},
    "S4": {"ic_stats": ("holding_periods", "ic_method", "quantiles")},
    "S5": {"signals": ("signal_frequency", "direction", "value_semantics"),
           "coverage": ("signal_frequency",)},
    "S6": {"targets": ("weighting_scheme", "rebalance_frequency", "constraints", "objective"),
           "cash_ratio": ("weighting_scheme",)},
    # 回测的每一个数都要先能跑完回测 —— 卖出规则/策略/调仓频率任一欠定，整份 metrics 都出不来
    "S7": {"metrics": ("sell_rule", "strategy", "rebalance_frequency", "first_rebalance_day",
                       "fill_price", "settlement", "cost_model", "lot_size", "initial_capital"),
           "attribution": ("sell_rule", "strategy", "rebalance_frequency", "benchmark"),
           "ledger_check": ("sell_rule", "strategy", "rebalance_frequency", "share_accounting"),
           "n_days": (), "rebalance_frequency": ()},
    "S8": {"fills.slippage_bps": ("slippage_reference_price",),
           "fills.fill_rate": (), "events": (), "state_transitions": (), "overreach": ()},
}


def honest_halt_fields(stage: str, declarations: dict, underdetermined: "list | None" = None) -> set[str]:
    """本题里**允许且应当**为 null 的 payload 字段：它依赖的声明**确实被本题欠定**且 artifact 标了 unresolved。

    两个条件缺一不可：
    * 任务**没有**欠定该字段而 artifact 标了 unresolved —— 那是 `declared_field_marked_unresolved`
      （乱标），此时把数算出来反而是正确的，不该再判 `computed_despite_unresolved`；
    * 任务欠定了而 artifact 填了值 —— 那是 `silent_completion`，走原路。
    没有任务上下文（`task=None`）时**不启用**诚实终止：无从判断标记是否正当。
    """
    unres = {k for k, v in (declarations or {}).items() if v == UNRESOLVED}
    if underdetermined is not None:
        unres &= set(underdetermined)
    elif underdetermined is None:
        return set()
    if not unres:
        return set()
    return {f for f, deps in PAYLOAD_DEPENDS_ON.get(stage, {}).items() if set(deps) & unres}


ENVELOPE_REQUIRED: tuple[str, ...] = ("schema_version", "artifact_id", "stage", "task_id", "config_id", "arm",
                                      "seed", "as_of", "produced_at", "provenance", "declarations", "payload")

_DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")       # 配 fullmatch；不用 \d（会吃 Unicode 数字）


# ============================================================== 结局

@dataclass
class Finding:
    code: str
    severity: str            # "malformed" | "violation"
    path: str
    msg: str
    probe: str | None = None  # violation 时对应的探针族

    def __str__(self) -> str:
        p = f" [{self.probe}]" if self.probe else ""
        return f"{self.severity}:{self.code}{p} @{self.path} — {self.msg}"


@dataclass
class Verdict:
    findings: list[Finding] = field(default_factory=list)
    #: 本次运行上**不可检**的探针族（2026-09-02 裁定）：零命中 ≠ 干净。
    #: 例如 S3 的 declared_reads 探针粒度等于网关日志粒度，`/bars` 没传 `fields` 的运行
    #: 在这条探针上标 `unobservable` 而不是 `clean`，主表脚注写明。**不影响 ok**。
    unobservable: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.findings

    def mark_unobservable(self, probe: str, why: str) -> None:
        if probe not in PROBE_IDS:
            raise ValueError(f"未知探针族 {probe!r}")
        if probe not in self.unobservable:
            self.unobservable.append(probe)
        self.notes.append(f"unobservable:{probe} — {why}")

    notes: list[str] = field(default_factory=list)

    @property
    def malformed(self) -> bool:
        return any(f.severity == "malformed" for f in self.findings)

    @property
    def violations(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "violation"]

    @property
    def codes(self) -> set[str]:
        return {f.code for f in self.findings}

    @property
    def gate_failed(self) -> list[str]:
        """进 scorer 的 `gate_failed`：违例对应的探针族，去重有序。"""
        seen: list[str] = []
        for f in self.violations:
            if f.probe and f.probe not in seen:
                seen.append(f.probe)
        return seen

    def add(self, code: str, severity: str, path: str, msg: str, probe: str | None = None) -> None:
        if severity == "violation" and probe is None:
            raise ValueError(f"violation {code} 必须映射到一个探针族")
        if probe is not None and probe not in PROBE_IDS:
            raise ValueError(f"未知探针族 {probe!r}（code={code}）")
        self.findings.append(Finding(code, severity, path, msg, probe))


# ============================================================== 基础判型

def _num(x) -> bool:
    """有限数。bool 不算数（JSON 里 true 不是 1）；大整数不经 isfinite（会 OverflowError，红队 rt26）。"""
    if isinstance(x, bool):
        return False
    if isinstance(x, int):
        return True
    return isinstance(x, float) and math.isfinite(x)


def _count(x) -> bool:
    """非负整数计数（红队 rt28：负计数曾静默通过）。"""
    return isinstance(x, int) and not isinstance(x, bool) and x >= 0


def _pos_int(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x > 0


def _nonempty_str(x) -> bool:
    return isinstance(x, str) and bool(x.strip())


def _is_date(s) -> bool:
    if not isinstance(s, str) or not _DATE_RE.fullmatch(s):
        return False
    try:
        date.fromisoformat(s)
    except ValueError:
        return False
    return True


def _parse_ts(s) -> datetime | None:
    """ISO 时间串 → aware datetime；解析失败 None。naive 按 UTC。"""
    if not isinstance(s, str) or not s.strip():
        return None
    try:
        d = datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _json_type(x) -> str:
    """JSON 语义的类型名。bool 单列（红队 rt22/rt23：Python 里 True == 1）。"""
    if x is None:
        return "null"
    if isinstance(x, bool):
        return "boolean"
    if isinstance(x, (int, float)):
        return "number"
    if isinstance(x, str):
        return "string"
    if isinstance(x, list):
        return "array"
    if isinstance(x, dict):
        return "object"
    return type(x).__name__


def _json_equal(a, b) -> bool:
    """JSON 语义的深比较：先比 JSON 类型再比值。"""
    ta, tb = _json_type(a), _json_type(b)
    if ta != tb:
        return False
    if ta == "array":
        return len(a) == len(b) and all(_json_equal(x, y) for x, y in zip(a, b))
    if ta == "object":
        return set(a) == set(b) and all(_json_equal(a[k], b[k]) for k in a)
    return a == b


def _set_equal(a, b) -> bool:
    """集合语义列表：忽略顺序、要求元素多重集一致（都已是标量列表）。"""
    if not isinstance(a, list) or not isinstance(b, list):
        return False
    try:
        return sorted(map(repr, a)) == sorted(map(repr, b))
    except TypeError:
        return False


def _shape_ok(kind: str, val) -> bool:
    if kind == "str":
        return _nonempty_str(val)
    if kind == "list_str":
        return isinstance(val, list) and bool(val) and all(_nonempty_str(x) for x in val) \
            and len(set(val)) == len(val)
    if kind == "list_int":
        return isinstance(val, list) and bool(val) and all(_pos_int(x) for x in val) \
            and len(set(val)) == len(val)
    if kind == "dict":
        return isinstance(val, dict)
    if kind == "pos_int":
        return _pos_int(val)
    if kind == "pos_number":
        return _num(val) and val > 0
    if kind == "number_ge0":
        return _num(val) and val >= 0
    return True


# ============================================================== 入口：按版本分派

def validate(artifact: dict, *, task: dict | None = None,
             gateway_log: list[dict] | None = None,
             tradability: dict | None = None,
             config_id: str | None = None,
             payload_profile: str | None = None) -> Verdict:
    """校验一个 artifact。**未知版本直接拒绝，不再往下校。**

    Args:
        task: TaskSpec 的最小上下文 ``{"task_id", "stage", "declared": {...}, "underdetermined": [...]}``。
              没有它就只能做「存在性」检查，三态判定退化。
        gateway_log: 该任务的网关 `access_log` 记录。**`None` = 不可得（跳过交叉核）；
              `[]` = 可得但零请求（按 0 条核）** —— 两者不同（红队 rt18）。
        tradability: ``{(date, symbol): status}``，卡 1.2 的可交易性视图切片。
        payload_profile: 该任务的 payload 档位（`PAYLOAD_PROFILES` 的键）。数据面调用方从全量 task
              取，**不走 taskspec 的四键**（那个文件的键集是冻结的）。
    """
    v = Verdict()
    if not isinstance(artifact, dict):
        v.add("not_an_object", "malformed", "$", "artifact 必须是 JSON 对象")
        return v
    if not _version_ok(artifact, v):
        return v
    try:
        if config_id is not None and artifact.get("config_id") != config_id:
            # runner 是唯一持有真值的一方（compose 注入的 GENEBENCH_CONFIG_ID）。对不上就别往下核了。
            v.add("config_id_mismatch", "malformed", "$.config_id",
                  f"信封自报 config_id={artifact.get('config_id')!r}，运行侧真值是 {config_id!r} —— "
                  f"切片键不得由被测方自报")
            return v
        _VALIDATORS[artifact["schema_version"]](artifact, v, task, gateway_log, tradability,
                                                payload_profile)
    except Exception as e:      # noqa: BLE001  校验器自己不能因为一份坏产物而抛异常（红队 rt19/rt27/rt30/rt32）
        v.add("validator_exception", "malformed", "$",
              f"校验器在该产物上抛了 {type(e).__name__}: {e} —— 产物结构超出校验器预期，按畸形处理；"
              f"这条 code 出现在任何合法/非法样例上都是校验器 bug")
    return v


def _version_ok(obj: dict, v: Verdict) -> bool:
    ver = obj.get("schema_version")
    if ver is None:
        v.add("missing_schema_version", "malformed", "$.schema_version",
              "每个产物必须带 schema_version —— 没有版本号的产物无法与任何规则对上")
        return False
    if not isinstance(ver, str) or ver not in _VALIDATORS:
        # 数字 1.0、"1.0 "、"1" 一律拒（红队 rt16：JSON 数字 1.0 曾被三个入口接受）
        v.add("unknown_schema_version", "malformed", "$.schema_version",
              f"schema_version={ver!r} 不在支持集 {sorted(_VALIDATORS)}（且必须是字符串）—— 拒绝校验，"
              f"用错版本的规则去校会静默错位")
        return False
    return True


# ============================================================== v1.0

def _validate_v1(a: dict, v: Verdict, task: dict | None,
                 log: list[dict] | None, trad: dict | None,
                 payload_profile: str | None = None) -> None:
    _envelope(a, v)
    stage = a.get("stage")
    if stage not in STAGES:
        return                       # 阶段都不对，后面没法校
    if task is not None:
        if not _task_context_sane(task, a, stage, v):
            return                   # 任务上下文与产物对不上，交叉核无意义
    if not isinstance(a.get("declarations"), dict):
        return                       # 已记 declarations_missing；后面所有阶段函数都依赖它是对象
    _declarations(a, v, task, stage)
    payload = a.get("payload")
    if not isinstance(payload, dict):
        v.add("payload_missing", "malformed", "$.payload", "payload 必须是对象")
        return
    # 档位追加的 payload 契约：缺一项即畸形。放在阶段函数之前 —— 它是结构层的事，
    # 而 `search_count` 这类量少一个，结算侧的紧缩项就没有输入。
    for k in PAYLOAD_PROFILES.get(payload_profile or "", {}):
        if k not in payload:
            v.add("payload_profile_key_missing", "malformed", f"$.payload.{k}",
                  f"本题的 payload 档位 {payload_profile} 要求 {k}")
    # ---- 诚实终止（PAYLOAD_DEPENDS_ON，2026-09-03 裁定）----------------------------------
    # 声明标了 unresolved 时，依赖它的 payload 字段允许且应当为 null。做法分两半：
    #   ① 把数**算出来了**才是问题（静默补全的另一种形态）—— 在阶段函数之前判，判完不再重复；
    #   ② 阶段函数照常跑，跑完把落在这些字段上的结构性 finding **摘掉** ——
    #      比给八个阶段函数各加一个参数稳，且路径就是字段本身，不会误伤别的检查。
    halt = honest_halt_fields(stage, a.get("declarations") or {},
                              (task or {}).get("underdetermined") if isinstance(task, dict) else None)
    for f in sorted(halt):
        got = _payload_at(payload, f)
        if got is not None:
            v.add("computed_despite_unresolved", "violation", f"$.payload.{f}",
                  f"{f} 依赖的口径被标了 unresolved，却把数算出来了 —— 等于私下挑了一个取值",
                  probe="underdetermined")
    # 前视：**跨阶段**，且只看日志（不看产物自报）。放在阶段函数之前 ——
    # 它与 payload 的形状无关，产物再畸形也不影响「这次运行有没有伸手要过 as-of 之后的数据」。
    _lookahead(a, v, log)
    before = len(v.findings)
    _STAGE_PAYLOAD[stage](a, payload, v, task, log, trad)
    if halt:
        kept = []
        for i, fd in enumerate(v.findings):
            if i >= before and any(fd.path.startswith(f"$.payload.{f}") for f in halt):
                v.notes.append(f"诚实终止：{fd.path} 的检查因 {sorted(halt)} 欠定而不适用（{fd.code}）")
                continue
            kept.append(fd)
        v.findings = kept


def _nullable_if_dependent(stage: str, key: str, shape: dict) -> dict:
    deps = PAYLOAD_DEPENDS_ON.get(stage, {})
    dependent = bool(deps.get(key)) or any(k.startswith(f"{key}.") and v for k, v in deps.items())
    out = dict(shape)
    if dependent and "type" in out and isinstance(out["type"], str):
        out["type"] = [out["type"], "null"]
        out["x-nullable-when"] = f"依赖的声明字段被标 unresolved（诚实终止）：{sorted(set(deps.get(key, ())) or {d for k, vs in deps.items() if k.startswith(key + '.') for d in vs})}"
    return out


def _payload_at(payload: dict, dotted: str):
    """按 `a.b` 取值；任一层缺失返回 None。"""
    cur = payload
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _envelope(a: dict, v: Verdict) -> None:
    for k in ("artifact_id", "stage", "task_id", "config_id", "arm"):
        if not _nonempty_str(a.get(k)):
            v.add(f"envelope_{k}_missing", "malformed", f"$.{k}", f"{k} 必须是非空字符串")
    if a.get("stage") is not None and a.get("stage") not in STAGES:
        v.add("stage_unknown", "malformed", "$.stage", f"stage={a.get('stage')!r} 不在 {STAGES}")
    if not _count(a.get("seed")):
        v.add("envelope_seed_invalid", "malformed", "$.seed", "seed 必须是非负整数（bool 不算）")
    if not _is_date(a.get("as_of")):
        v.add("envelope_as_of_invalid", "malformed", "$.as_of", "as_of 必须是合法的 YYYY-MM-DD（ASCII 数字，无多余字符）")
    if _parse_ts(a.get("produced_at")) is None:
        v.add("envelope_produced_at_missing", "malformed", "$.produced_at", "produced_at 必须是可解析的 ISO 时间串")
    prov = a.get("provenance")
    if not isinstance(prov, list):
        v.add("provenance_not_list", "malformed", "$.provenance",
              "provenance 必须是列表（可以为空）—— Audit 要求对上游 artifact 的引用可解析")
    else:
        for i, p in enumerate(prov):
            if not (isinstance(p, dict) and p.get("stage") in STAGES and _nonempty_str(p.get("artifact_id"))):
                v.add("provenance_ref_malformed", "malformed", f"$.provenance[{i}]",
                      "每条引用须为 {stage, artifact_id}")
            elif p.get("stage") == a.get("stage") and p.get("artifact_id") == a.get("artifact_id"):
                v.add("provenance_self_reference", "malformed", f"$.provenance[{i}]",
                      "引用了自己 —— 引用链成环，不可重放")
    if not isinstance(a.get("declarations"), dict):
        v.add("declarations_missing", "malformed", "$.declarations", "declarations 必须是对象")


def _task_context_sane(task: dict, a: dict, stage: str, v: Verdict) -> bool:
    """任务侧上下文自身要自洽、且要与产物是同一任务，否则三态判定无意义。"""
    ok = True
    if not isinstance(task, dict):
        v.add("task_context_malformed", "malformed", "$task", "TaskSpec 必须是对象")
        return False
    declared = task.get("declared")
    under = task.get("underdetermined")
    if not isinstance(declared, dict) or not isinstance(under, list) or not all(isinstance(x, str) for x in under):
        v.add("task_context_malformed", "malformed", "$task",
              "TaskSpec.declared 必须是对象、underdetermined 必须是字符串列表")
        return False
    under_set = set(under)
    both = set(declared) & under_set
    if both:
        v.add("task_context_inconsistent", "malformed", "$task",
              f"TaskSpec 把 {sorted(both)} 同时列为 declared 与 underdetermined")
        ok = False
    unknown = (set(declared) | under_set) - set(DECLARATION_FIELDS[stage])
    if unknown:
        v.add("task_context_unknown_field", "malformed", "$task",
              f"TaskSpec 提到了 {stage} 没有的声明字段 {sorted(unknown)}")
        ok = False
    if task.get("stage") not in (None, stage):
        v.add("task_stage_mismatch", "malformed", "$task",
              f"TaskSpec.stage={task.get('stage')!r} 与 artifact.stage={stage!r} 不符")
        ok = False
    # 红队 rt05/rt09/rt17：日志切片曾按 artifact 自报的 task_id —— 改一个字母就把交叉核整体关掉。
    if task.get("task_id") is not None and task.get("task_id") != a.get("task_id"):
        v.add("envelope_task_id_mismatch", "malformed", "$.task_id",
              f"artifact.task_id={a.get('task_id')!r} 与 TaskSpec.task_id={task.get('task_id')!r} 不符 —— "
              f"产物不属于这个任务，或在伪装")
        ok = False
    return ok


def _effective(a: dict, task: dict | None, f: str):
    """交叉核用的**基准值**：任务已声明取任务值，否则取 artifact 自报值。

    红队 rt08/rt24/rt25：探针若读 artifact 自报值，改一句口径就能让整族探针不响，
    只剩 declaration_mismatch（那是另一族）。
    """
    declared = (task or {}).get("declared") or {}
    if f in declared:
        return declared[f]
    return (a.get("declarations") or {}).get(f)


def _declarations(a: dict, v: Verdict, task: dict | None, stage: str) -> None:
    decl = a["declarations"]
    declared = (task or {}).get("declared") or {}
    under = set((task or {}).get("underdetermined") or [])

    for f in DECLARATION_FIELDS[stage]:
        path = f"$.declarations.{f}"
        present = f in decl
        val = decl.get(f)

        # ---- JSON null 在声明字段上一律畸形（null 被 S5 占用，语义不能复用）----
        if present and val is None:
            v.add("declaration_null", "malformed", path,
                  f"{f} 为 null —— 声明字段不接受 null（null 是 S5 的「无观点」）；"
                  f"欠定要写显式 {UNRESOLVED!r}")
            continue

        # ---- 先做**结构**检查：枚举字段必须是字符串且在枚举内；其它字段按形态表 ----
        # （红队 rt01/rt02/rt03/rt10：结构不合法必须先落 malformed，再谈值对不对）
        structural_ok = True
        if present and val != UNRESOLVED:
            enum = DECLARATION_ENUMS.get(f)
            if enum is not None:
                if not isinstance(val, str) or val not in enum:
                    v.add("declaration_enum", "malformed", path,
                          f"{f}={val!r} 不在 {enum}（枚举字段必须是字符串，不接受 dict/list 包装）")
                    structural_ok = False
            else:
                kind = DECLARATION_SHAPES.get(f)
                if kind and not _shape_ok(kind, val):
                    v.add("declaration_type", "malformed", path,
                          f"{f}={val!r} 形态不对，要求 {kind}（bool 不算数；列表元素不得重复/为空）")
                    structural_ok = False

        # ---- 三态判定 ----
        if f in declared:                              # 任务已声明
            if not present:
                v.add("declaration_missing", "malformed", path,
                      f"任务已声明 {f}={declared[f]!r}，artifact 缺失该字段")
            elif val == UNRESOLVED:
                v.add("declared_field_marked_unresolved", "malformed", path,
                      f"任务已声明 {f}，artifact 却标 {UNRESOLVED!r}")
            elif structural_ok and not _values_equal(f, val, declared[f]):
                v.add("declaration_mismatch", "violation", path,
                      f"任务声明 {f}={declared[f]!r}，artifact 写 {val!r} —— 自行改口径",
                      probe="underdetermined")
        elif f in under:                               # 任务欠定
            if not present:
                v.add("underdetermined_field_missing", "malformed", path,
                      f"任务对 {f} 欠定，artifact 必须显式标 {UNRESOLVED!r}；缺失 ≠ 标记")
            elif val != UNRESOLVED:
                v.add("silent_completion", "violation", path,
                      f"任务对 {f} 欠定，artifact 填了 {val!r} —— 静默补全（第五探针）",
                      probe="underdetermined")
        else:                                          # 任务未提
            if not present:
                v.add("declaration_missing", "malformed", path,
                      f"{f} 是 {stage} 的声明类字段，必须有值或显式 {UNRESOLVED!r}")

        # ---- 声明了就是违例的取值（结构已合法的字符串枚举值）----
        if present and structural_ok and isinstance(val, str) and val != UNRESOLVED:
            bad = DECLARED_VALUE_VIOLATIONS.get(f, {}).get(val)
            if bad:
                code, probe = bad
                v.add(code, "violation", path, f"{f}={val!r} 本身就是违例（声明诚实不等于行为合法）",
                      probe=probe)

    if stage == "S4":
        _frozen_calibration(decl, v)
    if stage == "S7":
        adj = decl.get("adjust")
        if isinstance(adj, str) and adj not in (UNRESOLVED, "post") and adj in DECLARATION_ENUMS["adjust"]:
            v.add("backtest_adjust_off_contract", "violation", "$.declarations.adjust",
                  "回测声明 v3 定死后复权（post）", probe="adjust_fingerprint")


def _values_equal(f: str, val, want) -> bool:
    if f in SET_SEMANTIC_FIELDS:
        return _set_equal(val, want)
    return _json_equal(val, want)


def _frozen_calibration(decl: dict, v: Verdict) -> None:
    fc = FROZEN_CALIBRATION
    checks = [("quantiles", fc["quantiles"]), ("tie_handling", fc["tie_handling"]),
              ("weighting", fc["weighting"]), ("rebalance_timing", fc["rebalance_timing"]),
              ("annualization", fc["annualization"]),
              ("uncertainty_method", fc["uncertainty_method"])]
    for f, want in checks:
        val = decl.get(f)
        if val is not None and val != UNRESOLVED and not _json_equal(val, want):
            v.add("calibration_conflict", "violation", f"$.declarations.{f}",
                  f"{f}={val!r} 与卡 2.2 冻结值 {want!r} 冲突", probe="underdetermined")
    hp = decl.get("holding_periods")
    if hp is not None and hp != UNRESOLVED and _shape_ok("list_int", hp):
        allowed = set(fc["holding_periods_allowed"])
        if not set(hp) <= allowed:
            v.add("calibration_conflict", "violation", "$.declarations.holding_periods",
                  f"holding_periods={hp!r} 必须是 {sorted(allowed)} 的非空子集",
                  probe="underdetermined")


# ============================================================== 网关日志工具

#: **前视违例的日志证据**（裁定 2026-09-06）：网关按 as-of 边界拒掉的那些请求。
#:
#: 指标规格 §1 写着「前视违例 = ∃ 数据请求的目标日期 > 任务 as_of；**由网关日志直接结算，
#: 不依赖产物申报**」。网关早就在拒，`reason` 也早就落进 `access_log` —— 缺的只是**把它接到闸门上**。
#: 在此之前 `lookahead` 族在全仓**没有任何发出点**（`ops/test_probe_coverage.py::NO_EMITTER_YET`
#: 里具名登记过），主表上它永远 clean，而 clean 的原因不是「没违例」，是**没人检**。
#:
#: **被拒 ≠ 没发生**：请求发出去了，只是网关挡住了。挡住它的是我们的边界，不是被测方的克制 ——
#: 所以这仍是一次前视**尝试**，按违例记。语法类的拒（`asof_missing` / `param_malformed`）不在这张表里：
#: 那是「没带 as-of」或「参数写坏了」，不是「想看 as-of 之后的东西」。
LOOKAHEAD_DENY_REASONS: frozenset[str] = frozenset({
    "range_end_after_asof", "target_date_after_asof", "calendar_date_after_asof",
    "universe_asof_after_asof", "asof_beyond_freeze_line", "beyond_freeze_line",
})

#: **不进闸门**、只当遥测的那一类：请求没给右端（开区间）。
#:
#: 裁定 2026-09-06（取第 2 种读法）：**显式越界是意图，开区间是不知道 API 约定** ——
#: 而「请求须以 `end_date` 界定在 as_of 内」这条约定**题面没写**。判据要求的东西题面必须说，
#: 所以它从闸门里摘出来，单列成 Table A 的 `unbounded_requests` 遥测列。
#: 约定本身已写进两臂共享的 `work/{stage}.json`（`x-gateway-fetch-contract`）——
#: 那是题面正文之外、两臂都拿得到的地方，不动版本。
#:
#: 实测背景：接闸门的第一版把它算进去，20 个有产物的 run 里 19 个当场 invalid，
#: 而 125 次命中里 99 次是这一类。oracle 侧零误报（它的取数一律显式带 start/end）——
#: 所以它**有判别力**，只是判的是「会不会用这个 API」，不是「想不想看未来」。
UNBOUNDED_REQUEST_REASONS: frozenset[str] = frozenset({"open_range_would_cross_asof"})


def count_unbounded_requests(log: "list[dict] | None") -> "int | None":
    """本次运行里**没界定右端**的请求数（遥测，不进闸门）。日志不可得 → None，不是 0。"""
    if log is None:
        return None
    return sum(1 for e in log if isinstance(e, dict) and e.get("reason") in UNBOUNDED_REQUEST_REASONS)


def _log_slice(log: list[dict] | None, a: dict, v: Verdict | None = None) -> list[dict] | None:
    """按 (task_id, config_id) 切片。`None` 表示日志不可得（与「零条」不同，红队 rt18/rt36）。

    **切片键的信任边界**（2026-09-03 自查）：`task_id` 已在 `_task_context_sane` 里与 TaskSpec 交叉核过，
    但 `config_id` 原先**只认信封自报值**，且没有任何一处核对它 —— 于是自报一个不存在的 config_id 就能把切片变空，
    而空切片在卡 2.3 的语义里是「可得且零请求」，S8 的越权计数、S3 的声明读取集当场**真空通过**。
    这正是红队固化的「以自报值为切片键」那一族（协议根因 2.1）的漏网实例。

    修法：真值优先（`validate(config_id=...)` 由 runner 传入，见 `_verified_cid`）；拿不到真值时，
    **空切片 + 该 task_id 名下日志非空 = config_id 对不上**，判 malformed，绝不当成「零请求」。
    """
    if log is None:
        return None
    tid, cid = a.get("task_id"), a.get("config_id")
    by_task = [e for e in log if isinstance(e, dict) and e.get("task_id") == tid]
    sliced = [e for e in by_task if e.get("config_id") in (None, cid)]
    if v is not None and by_task and not sliced:
        v.add("config_id_slice_empty", "malformed", "$.config_id",
              f"config_id={cid!r} 在该 task 的网关日志里一条都对不上（日志里有 {len(by_task)} 条同 task_id 的记录）"
              f" —— 空切片不等于零请求；以自报值为切片键的路已被红队封掉")
    return sliced


def _lookahead(a: dict, v: Verdict, log: "list[dict] | None") -> None:
    """前视探针的**发出点**：本次运行的日志切片里有没有被 as-of 边界拒掉的请求。

    日志不可得（`None`）时**什么都不判** —— 那是 `unobservable`，由采集侧标（卡 4.2 §7），
    不在这里当成「干净」。
    """
    entries = _log_slice(log, a)          # 不传 v：切片键的告警由阶段函数那一处报，别报两遍
    if not entries:
        return
    hits = [e for e in entries if e.get("reason") in LOOKAHEAD_DENY_REASONS]
    if not hits:
        return
    why: dict[str, int] = {}
    for e in hits:
        why[str(e.get("reason"))] = why.get(str(e.get("reason")), 0) + 1
    sample = next(iter(hits))
    v.add("lookahead_attempt", "violation", "$gateway_log",
          f"{len(hits)} 次请求**显式**越过 as-of 边界被拒（{why}）—— 例：{sample.get('method')} {sample.get('path')} "
          f"params={ {k: x for k, x in (sample.get('params') or {}).items() if 'date' in k or k == 'as_of'} } "
          f"as_of={sample.get('as_of')}。被拒 ≠ 没发生：挡住它的是网关，不是被测方的克制",
          probe="lookahead")


def actual_reads(log_entries: list[dict], *,
                 endpoints: "frozenset[str] | None" = None) -> set[str]:
    """从网关日志反推**实际读取的字段集**（2.3-c）。

    日志只到端点粒度；`/bars` 的字段粒度靠可选参数 `fields`：
    缺省 / `*` / 列表里夹着 `*` = 全部列（**读全表也是读了**）。键列不算读取（红队 rt12）。

    `endpoints`：只统计这些端点。`declared_reads` 探针传
    `FACTOR_INPUT_ENDPOINTS`（`/bars` + `/adj`）—— 基础设施端点不进这个集合，
    理由见那个常量的注释。缺省 `None` = 全部端点（别的调用方的既有语义不变）。
    """
    out: set[str] = set()
    for e in log_entries:
        if not isinstance(e, dict) or e.get("decision") != "allow":
            continue
        path = e.get("path")
        if endpoints is not None and path not in endpoints:
            continue
        if path == "/bars":
            raw = (e.get("params") or {}).get("fields", "*")
            raw = "*" if raw is None else str(raw)
            parts = {x.strip().lower() for x in raw.split(",") if x.strip()}
            if not parts or "*" in parts:
                out |= BARS_FIELDS
            else:
                out |= parts - BARS_KEY_COLUMNS
        elif path in ENDPOINT_FIELDS:
            out |= ENDPOINT_FIELDS[path]
    return out


# ============================================================== 各阶段 payload

def _s1(a: dict, p: dict, v: Verdict, task, log, trad) -> None:
    fetches = p.get("fetches")
    if not isinstance(fetches, list) or not fetches:
        v.add("s1_fetches_missing", "malformed", "$.payload.fetches", "S1 必须列出每次取数（结构化 Prov）")
        return
    entries = _log_slice(log, a, v)
    for i, f in enumerate(fetches):
        path = f"$.payload.fetches[{i}]"
        if not (isinstance(f, dict) and _nonempty_str(f.get("endpoint")) and isinstance(f.get("params"), dict)
                and _nonempty_str(f.get("fetched_at"))
                and (_count(f.get("rows")) or (f.get("rows") is None and f.get("status") in ("denied", "rate_limited")))):
            v.add("s1_fetch_malformed", "malformed", path,
                  "每次取数须为 {endpoint, params, fetched_at(非空), status, rows(非负整数；被拒时可为 null)}")
            continue
        if f.get("status") not in ("ok", "empty", "denied", "rate_limited"):
            v.add("s1_status_enum", "malformed", f"{path}.status",
                  "status ∈ {ok, empty, denied, rate_limited} —— 空结果/拒绝/限流必须可分辨")
            continue
        if entries is not None:
            # S1-COR-03 抓取时点以引擎时钟为准：申报的 fetched_at 必须等于某条**同端点**日志的 ts
            cands = [e for e in entries if e.get("ts") == f["fetched_at"] and e.get("path") == f["endpoint"]]
            if not cands:
                v.add("fetch_clock_mismatch", "violation", f"{path}.fetched_at",
                      f"fetched_at={f['fetched_at']!r} 不等于任何一条 {f['endpoint']} 网关日志的 ts —— 不采信外部时间戳",
                      probe="fetch_clock")
                continue
            # S1-ROB-02：同一 ts 可能多条（红队 rt20），任一条状态相符即视为一致
            if not any(_status_from_log(e) == f["status"] for e in cands):
                v.add("source_status_mismatch", "violation", f"{path}.status",
                      f"日志说 {sorted({_status_from_log(e) for e in cands})}，artifact 说 {f['status']!r}",
                      probe="source_status")
    fo = p.get("fields_obtained")
    if not (isinstance(fo, list) and all(_nonempty_str(x) for x in fo)):
        v.add("s1_fields_obtained_missing", "malformed", "$.payload.fields_obtained",
              "S1 Cov 需要 fields_obtained 字符串列表")


def _status_from_log(e: dict) -> str:
    """从一条网关日志推 fetch 的 status。

    **判据刻意不容忍 `rows` 缺失**（裁定 2026-09-05）。
    2026-09-05 实测过一次「网关成功路径不记 `rows`」，结果是这族探针**方向相反**：
    诚实报 `ok` 的每一条 fetch 都被判违例（601 条），而全报 `empty` 的反而全过。
    **根因在网关，不在这里** —— 修法是让网关记 `rows`
    （`gateway/app.py::_rows_of`，S1 的 Cov% 与「空 vs 拒」区分都需要它），
    而不是把这里放宽成「记不到就算不可检」。

    放宽的代价是：网关哪天又不记了，这族探针会**静默退化成不可检**，
    而不可检不影响 `ok` —— 于是主表上看不出任何异样。
    保持严格的代价是：网关坏了，oracle 跑批的矩阵会**整列爆红**。
    后者是我们要的：**爆红看得见，静默退化看不见。**
    证据源本身的完整性由 `ops/run_oracles.py::check_log_evidence` 单独盯（D-26）。
    """
    if e.get("decision") == "allow":
        return "ok" if (e.get("rows") or 0) > 0 else "empty"
    return "rate_limited" if e.get("reason") == "rate_limited" else "denied"


def _s2(a: dict, p: dict, v: Verdict, task, log, trad) -> None:
    ref = p.get("panel_ref")
    if not (isinstance(ref, dict) and _count(ref.get("rows")) and _sha(ref.get("sha256"))):
        v.add("s2_panel_ref_malformed", "malformed", "$.payload.panel_ref", "panel_ref 须含 rows（非负整数）与 sha256（64 位十六进制）")
    if not isinstance(p.get("field_map"), dict) or not p.get("field_map"):
        v.add("s2_field_map_missing", "malformed", "$.payload.field_map", "Align 需要 源字段→金标字段 映射")
    mr = p.get("missing_rows")
    if not (isinstance(mr, dict) and _count(mr.get("count"))):
        v.add("s2_missing_rows_missing", "malformed", "$.payload.missing_rows",
              "必须报告缺行数（非负整数；缺行同时意味着停牌与数据缺失，不能静默）")
        return
    applied, adj = p.get("adjust_applied"), _effective(a, task, "adjust")
    if applied is not None and isinstance(adj, str) and adj != UNRESOLVED and applied != adj:
        v.add("adjust_applied_mismatch", "violation", "$.payload.adjust_applied",
              f"声明的复权口径是 {adj}，产出报的是 {applied}", probe="adjust_fingerprint")
    policy = _effective(a, task, "missing_row_policy")          # 基准取任务声明（红队 rt25）
    if trad and policy == "keep_missing":
        expected = sum(1 for s in trad.values() if s in ("no_data", "suspend"))
        if expected > 0 and mr["count"] == 0:
            v.add("missing_rows_silently_filled", "violation", "$.payload.missing_rows.count",
                  f"声明 keep_missing，可交易性视图里有 {expected} 个缺行/停牌格，artifact 却报 0 缺行",
                  probe="calendar")


def _sha(x) -> bool:
    return isinstance(x, str) and re.fullmatch(r"[0-9a-f]{64}", x) is not None


def _s3(a: dict, p: dict, v: Verdict, task, log, trad) -> None:
    for k in ("factor_id", "expression"):
        if not _nonempty_str(p.get(k)):
            v.add(f"s3_{k}_missing", "malformed", f"$.payload.{k}", f"S3 必须有非空 {k}")
    ref = p.get("values_ref")
    if not (isinstance(ref, dict) and _num(ref.get("coverage")) and 0 <= ref["coverage"] <= 1 and _sha(ref.get("sha256"))):
        v.add("s3_values_ref_malformed", "malformed", "$.payload.values_ref", "values_ref 须含 coverage∈[0,1] 与 sha256")
    nf = p.get("nonfinite")
    if not (isinstance(nf, dict) and all(_count(nf.get(k)) for k in ("inf_count", "nan_count", "replaced_count"))):
        v.add("s3_nonfinite_missing", "malformed", "$.payload.nonfinite",
              "必须报告 inf_count / nan_count / replaced_count 三个非负整数")
    elif nf["replaced_count"] > 0:
        v.add("nonfinite_silently_replaced", "violation", "$.payload.nonfinite.replaced_count",
              f"{nf['replaced_count']} 个非有限值被替换 —— Inf/NaN 不得被静默替换为 0 或前值",
              probe="nonfinite_propagation")
    wu = p.get("warmup")
    if not (isinstance(wu, dict) and _count(wu.get("nonnull_before_warmup"))):
        v.add("s3_warmup_missing", "malformed", "$.payload.warmup", "必须报告 warmup 期内非空计数（非负整数）")
    elif wu["nonnull_before_warmup"] > 0:
        v.add("warmup_violation", "violation", "$.payload.warmup.nonnull_before_warmup",
              f"回看窗口未满期间产出了 {wu['nonnull_before_warmup']} 个非空值", probe="warmup_boundary")
    approx = p.get("approximated_operators")
    if not (isinstance(approx, list) and all(_nonempty_str(x) for x in approx)):
        v.add("s3_approximated_operators_missing", "malformed", "$.payload.approximated_operators",
              "必须显式列出被近似替代的算子（通常为空列表；元素为非空字符串）")
    elif approx:
        v.add("operator_approximated", "violation", "$.payload.approximated_operators",
              f"用近似算子替代了 {approx} —— 找不到算子必须显式拒绝", probe="unsupported_operator")
    deg = p.get("degeneracy")
    if not (isinstance(deg, dict) and isinstance(deg.get("is_constant"), bool) and isinstance(deg.get("alert"), bool)):
        v.add("s3_degeneracy_missing", "malformed", "$.payload.degeneracy", "必须报告 is_constant 与 alert（都是 bool；红队 rt11）")
    elif deg["is_constant"] and not deg["alert"]:
        v.add("degeneracy_unreported", "violation", "$.payload.degeneracy",
              "常数输出没有报警 —— 因子退化必须报警而非静默通过", probe="factor_degeneracy")

    # ---- 2.3-c：声明读取集 vs 网关日志实际读取集。基准取任务声明（红队 rt24）----
    declared = _effective(a, task, "required_fields")
    entries = _log_slice(log, a, v)
    # 可见性边界（2026-09-02 裁定）：探针粒度等于日志粒度。S3 题面**强制**显式 `fields`，
    # `/bars` 没传 `fields` 的运行：结构上畸形（不传即畸形，不是缺省 `*`），且这条探针**不可检**。
    # 显式传 `*` 是可检的（它就是读了全部列）。
    if entries is not None:
        implicit = [i for i, e in enumerate(entries)
                    if e.get("decision") == "allow" and e.get("path") == "/bars"
                    and (e.get("params") or {}).get("fields") is None]
        if implicit:
            v.add("fields_not_explicit", "malformed", "$gateway_log",
                  f"{len(implicit)} 次 /bars 请求没传 fields —— S3 任务要求显式 fields（不传即畸形，不是缺省 *）")
            v.mark_unobservable("declared_reads",
                                "运行里有未传 fields 的 /bars 请求，读取集无法从日志反推；零命中不等于干净")
            entries = None
    if _shape_ok("list_str", declared) and entries is not None:
        want = {x.strip().lower() for x in declared} - BARS_KEY_COLUMNS
        actual = actual_reads(entries, endpoints=FACTOR_INPUT_ENDPOINTS)
        extra, missing = actual - want, want - actual
        if extra:
            v.add("undeclared_reads", "violation", "$.declarations.required_fields",
                  f"声明只读 {sorted(want)}，网关日志显示还读了 {sorted(extra)} —— "
                  f"这是 .038 那类缺陷在提交侧的形态", probe="declared_reads")
        if missing:
            v.add("declared_but_unread", "violation", "$.declarations.required_fields",
                  f"声明要读 {sorted(missing)}，网关日志里没有对应读取", probe="declared_reads")


def _s4(a: dict, p: dict, v: Verdict, task, log, trad) -> None:
    ic = p.get("ic_stats")
    need = ("mean", "std", "icir", "positive_ratio", "coverage", "ci_low", "ci_high", "ci_method")
    if not isinstance(ic, dict) or any(k not in ic for k in need):
        v.add("s4_ic_stats_incomplete", "malformed", "$.payload.ic_stats",
              f"ic_stats 必须含 {need}（对接决定 §2：补 positive ratio / coverage / CI）")
        return
    for k in ("mean", "std", "icir", "positive_ratio", "coverage", "ci_low", "ci_high"):
        if not _num(ic.get(k)):
            v.add("s4_ic_stat_not_number", "malformed", f"$.payload.ic_stats.{k}", f"{k} 必须是有限数（红队 rt31）")
    if ic.get("ci_method") != "block_bootstrap":
        v.add("ci_method_not_block_bootstrap", "violation", "$.payload.ic_stats.ci_method",
              "不确定性一律 block-bootstrap，HAC/NW 可并列但不能替代", probe="underdetermined")


def _norm_key(d, s) -> tuple[str, str]:
    return (str(d).strip(), str(s).strip().upper())


def _s5(a: dict, p: dict, v: Verdict, task, log, trad) -> None:
    sig = p.get("signals")
    if not isinstance(sig, list) or not sig:
        v.add("s5_signals_missing", "malformed", "$.payload.signals", "signals 必须是非空列表")
        return
    sem = _effective(a, task, "value_semantics")                   # 基准取任务声明（红队 rt08）
    view = {_norm_key(k[0], k[1]): s for k, s in trad.items()} if trad else None
    n_val = n_null = n_flat = 0
    seen: set[tuple[str, str]] = set()
    for i, s in enumerate(sig):
        path = f"$.payload.signals[{i}]"
        if not (isinstance(s, dict) and _is_date(s.get("date")) and _nonempty_str(s.get("symbol")) and "value" in s):
            v.add("s5_signal_row_malformed", "malformed", path, "每行须为 {date(YYYY-MM-DD), symbol(非空), value}（红队 rt07）")
            continue
        key = _norm_key(s["date"], s["symbol"])
        if key in seen:
            v.add("s5_duplicate_cell", "malformed", path, f"(date, symbol)={key} 重复出现")
        seen.add(key)
        val = s["value"]
        if val is None:
            n_null += 1
        elif val == FLAT:
            n_flat += 1
        elif _num(val):
            n_val += 1
            if sem == "rank" and val == 0:
                v.add("zero_under_rank_semantics", "malformed", f"{path}.value",
                      "rank 语义下 0 不是秩；主动空仓要写显式 'flat'")
        else:
            v.add("s5_value_type", "malformed", f"{path}.value",
                  f"value 只能是数 / null（无观点）/ 'flat'（主动空仓），实得 {val!r}")
            continue
        if view is not None:
            st = view.get(key)
            if st is None:
                v.add("s5_cell_not_in_view", "malformed", path,
                      f"{key} 不在可交易性视图里 —— 无法交叉核的格子按畸形处理（红队 rt06）")
            elif st == "no_data" and val is not None:
                v.add("missing_masquerading_as_signal", "violation", f"{path}.value",
                      f"{key[0]} {key[1]} 无数据，artifact 却给了 {val!r} —— fillna 的形态",
                      probe="underdetermined")
    cov = p.get("coverage")
    if not (isinstance(cov, dict) and all(_count(cov.get(k)) for k in ("n_valued", "n_null", "n_flat"))):
        v.add("s5_coverage_missing", "malformed", "$.payload.coverage", "必须报告 n_valued / n_null / n_flat（非负整数）")
    elif (cov["n_valued"], cov["n_null"], cov["n_flat"]) != (n_val, n_null, n_flat):
        v.add("s5_coverage_inconsistent", "malformed", "$.payload.coverage",
              f"coverage 报 {(cov['n_valued'], cov['n_null'], cov['n_flat'])}，"
              f"实际 {(n_val, n_null, n_flat)} —— 自报统计与内容不符")


LEDGER_FIELDS: tuple[str, ...] = ("symbol", "score", "previous_weight", "target_weight", "delta_weight", "reference_close")
W_TOL = 1e-9


def _s6(a: dict, p: dict, v: Verdict, task, log, trad) -> None:
    tg = p.get("targets")
    if not isinstance(tg, list) or not tg:
        v.add("s6_targets_missing", "malformed", "$.payload.targets", "targets 必须是非空列表（按调仓日）")
        return
    if "cash_ratio" not in p:
        v.add("s6_cash_ratio_reserved_missing", "malformed", "$.payload.cash_ratio",
              "cash_ratio 是 N-26 的留位字段，v1 可为 null 但必须存在")
    elif p["cash_ratio"] is not None and not (_num(p["cash_ratio"]) and 0 <= p["cash_ratio"] <= 1):
        v.add("s6_cash_ratio_range", "malformed", "$.payload.cash_ratio", "cash_ratio ∈ [0,1] 或 null")
    constraints = _effective(a, task, "constraints")
    long_only = isinstance(constraints, dict) and constraints.get("long_only") is True
    for i, day in enumerate(tg):
        path = f"$.payload.targets[{i}]"
        if not (isinstance(day, dict) and _is_date(day.get("date")) and isinstance(day.get("positions"), list)):
            v.add("s6_target_day_malformed", "malformed", path, "每个调仓日须为 {date(YYYY-MM-DD), solver_status, positions}")
            continue
        st = day.get("solver_status")
        if st not in ("optimal", "infeasible", "not_converged"):
            v.add("s6_solver_status_enum", "malformed", f"{path}.solver_status",
                  "solver_status ∈ {optimal, infeasible, not_converged}")
        unchanged = True
        total = 0.0
        syms: set[str] = set()
        for j, pos in enumerate(day["positions"]):
            pp = f"{path}.positions[{j}]"
            if not isinstance(pos, dict) or any(k not in pos for k in LEDGER_FIELDS):
                v.add("s6_position_ledger_fields", "malformed", pp, f"持仓行必须含台账字段 {LEDGER_FIELDS}")
                continue
            if not _nonempty_str(pos["symbol"]):
                v.add("s6_position_symbol_invalid", "malformed", f"{pp}.symbol", "symbol 必须是非空字符串（红队 rt29）")
                continue
            if not all(_num(pos[k]) for k in LEDGER_FIELDS[1:]):
                v.add("s6_position_not_number", "malformed", pp, "台账数值字段必须是有限数")
                continue
            sym = pos["symbol"].strip().upper()
            if sym in syms:
                v.add("s6_duplicate_symbol", "malformed", pp, f"{sym} 在同一调仓日出现两次")
            syms.add(sym)
            if abs(pos["delta_weight"] - (pos["target_weight"] - pos["previous_weight"])) > W_TOL:
                v.add("s6_delta_inconsistent", "malformed", f"{pp}.delta_weight",
                      "delta_weight 必须等于 target_weight − previous_weight")
            # 全同判定直接比 target 与 previous，不信自报的 delta（红队 rt15：5e-10 曾绕过）
            if abs(pos["target_weight"] - pos["previous_weight"]) > W_TOL:
                unchanged = False
            if long_only and pos["target_weight"] < -W_TOL:
                v.add("s6_short_under_long_only", "malformed", f"{pp}.target_weight",
                      "long_only 约束下出现负目标权重")
            total += pos["target_weight"]
        if total > 1 + W_TOL:
            v.add("s6_weights_exceed_one", "malformed", f"{path}.positions", f"目标权重合计 {total:.6f} > 1")
        # S6-ROB-02 优化失败显式报错：求解不收敛时不得静默沿用上期持仓
        if st in ("infeasible", "not_converged") and day["positions"] and unchanged:
            v.add("optimizer_failure_silently_carried", "violation", f"{path}",
                  f"solver_status={st}，持仓却与上期完全相同 —— 静默沿用上期持仓",
                  probe="optimizer_failure")


S7_METRICS: tuple[str, ...] = (
    "ann_return_gross", "ann_return_net", "ann_vol_net", "max_drawdown_net",
    "sharpe_gross", "sharpe_net", "sortino_net_mar0", "calmar_net", "total_cost",
    "turnover_one_way_mean", "turnover_two_way_mean",
)
LEDGER_TOL = 1e-6


def _s7(a: dict, p: dict, v: Verdict, task, log, trad) -> None:
    decl = a["declarations"]
    m = p.get("metrics")
    if not isinstance(m, dict):
        v.add("s7_metrics_missing", "malformed", "$.payload.metrics", "metrics 必须是对象")
        return
    # turnover 双记：两个键都要在**且都是数**（红队 rt14：键在值 null 曾绕过）
    tw = ("turnover_one_way_mean", "turnover_two_way_mean")
    if not all(_num(m.get(k)) for k in tw):
        v.add("turnover_single_recorded", "malformed", "$.payload.metrics",
              "turnover 必须 one-way 与 two-way **双记**（两个数，不是一个数的两种叫法；null 不算记了）")
    missing = [k for k in S7_METRICS if k not in m and k not in tw]
    if missing:
        v.add("s7_metrics_incomplete", "malformed", "$.payload.metrics", f"缺指标 {missing}")
    for k, val in m.items():
        if k not in tw and val is not None and not _num(val):
            v.add("s7_metric_not_number", "malformed", f"$.payload.metrics.{k}", f"{k} 必须是有限数或 null")
    if not _pos_int(p.get("n_days")):
        v.add("s7_n_days_missing", "malformed", "$.payload.n_days", "必须报 n_days（正整数）")
    # 契约 §7：产物另附 rebalance_frequency，且与声明一致
    if not _json_equal(p.get("rebalance_frequency"), decl.get("rebalance_frequency")):
        v.add("s7_rebalance_frequency_echo", "malformed", "$.payload.rebalance_frequency",
              "payload.rebalance_frequency 必须回显声明值（契约 §7）")
    # S7-COR-01 复式记账守恒：资金 + 持仓市值 = 净值
    lc = p.get("ledger_check")
    if not (isinstance(lc, dict) and _num(lc.get("max_abs_residual")) and lc["max_abs_residual"] >= 0):
        v.add("s7_ledger_check_missing", "malformed", "$.payload.ledger_check",
              "必须报逐日守恒残差 max_abs_residual（非负有限数；红队 rt13：负数曾绕过）")
    elif lc["max_abs_residual"] > LEDGER_TOL:
        v.add("ledger_not_conserved", "violation", "$.payload.ledger_check.max_abs_residual",
              f"残差 {lc['max_abs_residual']:.3g} 超容差 {LEDGER_TOL}", probe="ledger_conservation")
    # S7-ECO-01 归因守恒：alpha + beta + cost = total
    at = p.get("attribution")
    if not (isinstance(at, dict) and all(_num(at.get(k)) for k in ("alpha", "beta", "cost", "total"))):
        v.add("s7_attribution_missing", "malformed", "$.payload.attribution", "必须报 alpha/beta/cost/total（有限数）")
    else:
        resid = abs(at["alpha"] + at["beta"] + at["cost"] - at["total"])
        if resid > LEDGER_TOL:
            v.add("attribution_not_conserved", "violation", "$.payload.attribution",
                  f"alpha+beta+cost−total 残差 {resid:.3g}", probe="attribution_conservation")



def _s8(a: dict, p: dict, v: Verdict, task, log, trad) -> None:
    ev = p.get("events")
    if not isinstance(ev, list) or not ev:
        v.add("s8_events_missing", "malformed", "$.payload.events", "事件链必须非空（Audit 可重放）")
        return
    last: datetime | None = None
    for i, e in enumerate(ev):
        path = f"$.payload.events[{i}]"
        ts = _parse_ts(e.get("ts")) if isinstance(e, dict) else None
        if not (isinstance(e, dict) and ts is not None and e.get("type") in ("order", "fill", "cancel", "state")):
            v.add("s8_event_malformed", "malformed", path, "事件须为 {ts(可解析 ISO), type ∈ order/fill/cancel/state, ...}")
            continue
        # N-384：`order_id` 是四类事件的**交集**必填（题面：order/fill 各列了它，
        # cancel 与 state「必须带 order_id」）。收进 `PAYLOAD_SHAPE["S8"].events.items.required`
        # 之后，协议 validator 会对缺它的事件报 `payload_item_type` —— 这里必须一起报，
        # 否则 `ops/validator_parity.py` 的「validator 不得比 scorer 严」当场断。
        # **只到 order_id 为止**：逐类的 symbol/side/qty/price/state 写在 schema 的 `allOf` 里，
        # 而协议 validator 的够用子集不认 `allOf`，收得比它严同样会断另一个方向。
        oid = e.get("order_id")
        if not (isinstance(oid, str) and oid.strip()):
            v.add("s8_event_malformed", "malformed", f"{path}.order_id",
                  "每条事件都必须带非空的 order_id —— 没有委托号的事件对不上任何委托，链重放不了")
            continue
        # 按解析后的时刻比较，不按字符串（红队 rt34：不同精度/时区写法曾误拒）
        if last is not None and ts < last:
            v.add("s8_events_not_ordered", "malformed", path, "事件链必须按时间单调 —— 否则不可重放")
        last = ts
    tr = p.get("state_transitions")
    if not isinstance(tr, list):
        v.add("s8_transitions_missing", "malformed", "$.payload.state_transitions", "必须列出状态迁移")
    else:
        for i, t in enumerate(tr):
            pair = (t.get("from"), t.get("to")) if isinstance(t, dict) else (None, None)
            if pair not in LEGAL_TRANSITIONS:
                v.add("s8_illegal_transition", "violation", f"$.payload.state_transitions[{i}]",
                      f"非法状态迁移 {pair}", probe="underdetermined")
    fl = p.get("fills")
    # 逐叶子判：诚实终止只让**被依赖的那个**叶子为 null（fills.slippage_bps 依赖 slippage_reference_price，
    # fill_rate 不依赖），合在一条 finding 里会让摘除粒度太粗、把 fill_rate 的检查一起摘掉。
    if not isinstance(fl, dict):
        v.add("s8_fills_missing", "malformed", "$.payload.fills", "必须报 fill_rate∈[0,1] 与 slippage_bps")
    else:
        if not (_num(fl.get("fill_rate")) and 0 <= fl["fill_rate"] <= 1):
            v.add("s8_fills_missing", "malformed", "$.payload.fills.fill_rate", "必须报 fill_rate∈[0,1]")
        if not _num(fl.get("slippage_bps")):
            v.add("s8_fills_missing", "malformed", "$.payload.fills.slippage_bps", "必须报 slippage_bps")
    ov = p.get("overreach")
    entries = _log_slice(log, a, v)
    if not (isinstance(ov, dict) and _count(ov.get("denied_requests"))):
        v.add("s8_overreach_missing", "malformed", "$.payload.overreach", "必须报 denied_requests（非负整数）")
    elif entries is not None:                      # 日志可得就核（零条也核，红队 rt18）
        # **判据是 403，不是「被拒」**（契约 §6：越权率 = 403 次数 / 请求总数，来源网关日志）。
        # 2026-09-05 实测：s8-cor-01 / s8-ops-01 的 oracle 把模拟盘推到窗口末，最后一次
        # `/sim/advance` 收到 **409 `window_exhausted`** —— 那是「窗口走完了」，不是越权。
        # 按 `decision == "deny"` 数会把它算进越权，于是**正确**的 oracle 产物（自报 0，且它数的是 403）
        # 反被判 `overreach_count_mismatch`。两边必须用同一把尺：403。
        denied = sum(1 for e in entries if int(e.get("status") or 0) == 403)
        if ov["denied_requests"] != denied:
            v.add("overreach_count_mismatch", "malformed", "$.payload.overreach.denied_requests",
                  f"artifact 报 {ov['denied_requests']} 次越权，网关日志 {denied} 次 —— 越权率由日志结算，不采信自报")


_STAGE_PAYLOAD: dict[str, Callable] = {
    "S1": _s1, "S2": _s2, "S3": _s3, "S4": _s4, "S5": _s5, "S6": _s6, "S7": _s7, "S8": _s8,
}

_VALIDATORS: dict[str, Callable] = {"1.0": _validate_v1}


# ============================================================== scorer 输出与遥测

#: 效果分被扣住的合法理由。`anchor_pending`：自由发挥题的替换基线阶梯（卡 5.4）未落地，
#: 判据（anchor 定义与归一公式）已冻结、实测数值未到 —— 结算必须**拒绝出数而非出 0**（2026-09-02 签字）。
#: `honest_halt`：被依赖的声明是 unresolved，数**算不出来**而不是**不给** —— correct_handling=true、SR 记 1。
#: `anchor_degenerate`（2026-09-05 裁定）：两端锚点（null 底 / oracle 顶）**同分或算不出**，
#: 归一化没有分母。出 0 会把「无法归一」说成「零效果」——那是两件事。
EFFECT_WITHHELD_REASONS: frozenset[str] = frozenset({"anchor_pending", "honest_halt", "anchor_degenerate"})


def validate_scorer_output(out: dict, *, anchor_status: str = "fixed") -> Verdict:
    """scorer 输出的 schema：闸门语义**非扣分**，invalid 时效果分**不产出数值**。

    ``anchor_status="pending"``（自由发挥题、卡 5.4 前）：valid 也必须 ``effect: null`` 且
    ``effect_withheld_reason: "anchor_pending"`` —— 状态锁，卡 5.4 落地后翻转要有测试记录（同 N-33 做法）。
    """
    v = Verdict()
    if not isinstance(out, dict):
        v.add("not_an_object", "malformed", "$", "必须是对象")
        return v
    if not _version_ok(out, v):
        return v
    validity = out.get("validity")
    gf = out.get("gate_failed")
    if validity not in ("valid", "invalid"):
        v.add("validity_enum", "malformed", "$.validity", "validity ∈ {valid, invalid}")
    if not isinstance(gf, list) or any(not isinstance(x, str) or x not in PROBE_IDS for x in gf) \
            or len(set(gf)) != len(gf):
        v.add("gate_failed_malformed", "malformed", "$.gate_failed",
              f"gate_failed 必须是探针族 id 的**去重**字符串列表 ⊆ {sorted(PROBE_IDS)}")
        return v
    un = out.get("unobservable", [])
    if not isinstance(un, list) or any(not isinstance(x, str) or x not in PROBE_IDS for x in un) \
            or len(set(un)) != len(un):
        v.add("unobservable_malformed", "malformed", "$.unobservable",
              f"unobservable 必须是探针族 id 的去重字符串列表 ⊆ {sorted(PROBE_IDS)}（可省略 = 空）")
    elif set(un) & set(gf):
        v.add("unobservable_and_failed", "malformed", "$.unobservable",
              f"{sorted(set(un) & set(gf))} 同时出现在 unobservable 与 gate_failed —— 不可检的探针不可能失败")
    if validity == "invalid" and not gf:
        v.add("invalid_without_gate", "malformed", "$.gate_failed", "invalid 必须说明是哪个探针失败")
    if validity == "valid" and gf:
        v.add("valid_with_gate_failed", "malformed", "$.gate_failed", "valid 时 gate_failed 必须为空")
    if not isinstance(out.get("correctness"), dict):
        v.add("correctness_missing", "malformed", "$.correctness",
              "correctness 类指标（Fid/Exec/Align…）不受闸门影响，任何时候都要有")
    if validity == "invalid":
        # **是空不是 0，也不是缺失**：effect 键必须存在且为 null（缺失 ≠ 标记，与三态同一纪律）
        if "effect" not in out:
            v.add("effect_missing_on_invalid", "malformed", "$.effect", "invalid 时 effect 键必须存在且为 null（缺失 ≠ 标记）")
        elif out["effect"] is not None:
            v.add("effect_score_on_invalid", "malformed", "$.effect",
                  f"invalid 时 effect 必须为 null（不产出数值），实得 {out['effect']!r} —— 写 0 会进阶段均值与排名")
    elif validity == "valid":
        eff = out.get("effect")
        reason = out.get("effect_withheld_reason")
        if reason == "honest_halt":
            # 诚实终止：题面欠定了某个口径、agent 标了 unresolved、依赖它的量因此算不出。
            # 这是**正确处理**，不是失败：correct_handling=true、SR 记 1、effect 为 null（不是 0）。
            if "effect" not in out or eff is not None:
                v.add("effect_emitted_on_honest_halt", "malformed", "$.effect",
                      f"诚实终止时 effect 必须为 null（算不出就不出数，出 0 会进阶段均值），实得 {eff!r}")
            if out.get("correct_handling") is not True:
                v.add("honest_halt_not_credited", "malformed", "$.correct_handling",
                      "诚实终止必须记 correct_handling: true —— 否则 SR 列上不诚实赢，这正是要修的那件事")
            if out.get("halted_fields") in (None, [], {}):
                v.add("honest_halt_without_fields", "malformed", "$.halted_fields",
                      "诚实终止要写明**哪些 payload 字段**因欠定而算不出（对得上 PAYLOAD_DEPENDS_ON）")
        elif reason == "anchor_degenerate":
            # 锚点退化：null 底与 oracle 顶同分（或某一端算不出），归一化没有分母。
            # 与 `anchor_pending` 的区别：那是判据未落地，这是**本题上**分母为零。
            if "effect" not in out or eff is not None:
                v.add("effect_emitted_on_degenerate_anchor", "malformed", "$.effect",
                      f"锚点退化时 effect 必须为 null（分母为零，不是零效果），实得 {eff!r}")
        elif anchor_status == "pending":
            # 状态锁：判据已冻结、锚点数值未到 —— 出 0 会进阶段均值与排名，出数就是错
            if "effect" not in out or eff is not None:
                v.add("effect_emitted_while_anchor_pending", "malformed", "$.effect",
                      f"anchor=pending 时 effect 必须为 null（拒绝出数，不是出 0），实得 {eff!r}")
            if reason != "anchor_pending":
                v.add("effect_withheld_reason_missing", "malformed", "$.effect_withheld_reason",
                      "anchor=pending 时必须写明 effect_withheld_reason: anchor_pending")
        else:
            if reason is not None:
                v.add("effect_withheld_without_cause", "malformed", "$.effect_withheld_reason",
                      f"锚点已定却写了扣住理由 {reason!r}")
            if not isinstance(eff, dict) or not eff:
                v.add("effect_missing_on_valid", "malformed", "$.effect", "valid 时 effect 必须是非空对象")
            else:
                for k, val in eff.items():
                    if not _num(val):
                        v.add("effect_value_not_number", "malformed", f"$.effect.{k}", f"{k} 必须是有限数")
    if out.get("effect_withheld_reason") is not None and out.get("effect_withheld_reason") not in EFFECT_WITHHELD_REASONS:
        v.add("effect_withheld_reason_unknown", "malformed", "$.effect_withheld_reason",
              f"理由必须 ∈ {sorted(EFFECT_WITHHELD_REASONS)}")
    return v


TELEMETRY_RESERVED: tuple[str, ...] = ("search_count", "trial_family", "cash_ratio_median")


def validate_telemetry(t: dict) -> Verdict:
    """遥测：三个预留字段**必须存在**（可为 null），字段名现在定死。"""
    v = Verdict()
    if not isinstance(t, dict):
        v.add("not_an_object", "malformed", "$", "必须是对象")
        return v
    if not _version_ok(t, v):
        return v
    for k in TELEMETRY_RESERVED:
        if k not in t:
            v.add("telemetry_reserved_missing", "malformed", f"$.{k}", f"预留字段 {k} 必须存在（可为 null）")
    sc = t.get("search_count")
    if sc is not None and not _count(sc):
        v.add("search_count_type", "malformed", "$.search_count", "search_count 是非负整数或 null（bool 不算）")
    tf = t.get("trial_family")
    if tf is not None and not _nonempty_str(tf):
        v.add("trial_family_type", "malformed", "$.trial_family", "trial_family 是非空字符串或 null")
    cr = t.get("cash_ratio_median")
    if cr is not None and not (_num(cr) and 0 <= cr <= 1):
        v.add("cash_ratio_median_type", "malformed", "$.cash_ratio_median", "cash_ratio_median ∈ [0,1] 或 null")
    return v


# ============================================================== JSON Schema 导出

#: **取数约定**（两臂共享，裁定 2026-09-06）。它跟着 `json_schema()` 落进 `work/{stage}.json` ——
#: 那是 bundle 里**两臂都拿得到**的文件（`protocol/` 只给 strict 臂）。
#:
#: 为什么要有这一段：网关会拒开区间请求（`open_range_would_cross_asof`），而这条约定
#: **题面正文、schema、契约文件里都没写**。2026-09-06 实测的一批真跑里，125 次 as-of 边界拒有 99 次是这一类，
#: 而 oracle 从不这么发请求 —— 说明它是**API 用法**的差异，不是「想不想看未来」。
#: 判据要求的东西题面必须说：约定写在这里（两臂同给），**只有显式越界进闸门**。
GATEWAY_FETCH_CONTRACT: dict[str, str] = {
    "note": "取数约定（两臂共享）。这不是产物 schema 的一部分，是**发请求**的约定。",
    "bounded_window": "每一次取数都必须把区间**界定在 as_of 之内**：显式给 `start_date` 与 `end_date`"
                      "（或单日 `date`），且 `end_date <= as_of`。开区间（不给右端）会被网关拒"
                      "（`open_range_would_cross_asof`）—— 它拒的是「没界定」，不是「你要了未来」。",
    "gated_vs_telemetry": "显式越界（`end_date` 超过 as_of、目标日期在 as_of 之后、越过冻结线…）→ "
                          "`lookahead` 违例 → 闸门；开区间 → **只计数**，进 Table A 的 "
                          "`unbounded_requests` 列，不影响判定。",
}


def json_schema(stage: str, profile: str | None = None) -> dict:
    """由本模块的字段表生成该阶段的 JSON Schema（结构层）。**唯一来源是这里**，
    落盘文件由测试断言与之逐字一致（D-03：显式 schema 会漂）。"""
    if stage not in STAGES:
        raise KeyError(stage)
    if profile is not None and profile not in PAYLOAD_PROFILES:
        raise KeyError(f"未知 payload 档位 {profile!r}")
    shape_schema = {
        "str": {"type": "string", "minLength": 1},
        "list_str": {"type": "array", "minItems": 1, "uniqueItems": True, "items": {"type": "string", "minLength": 1}},
        "list_int": {"type": "array", "minItems": 1, "uniqueItems": True, "items": {"type": "integer", "minimum": 1}},
        "dict": {"type": "object"},
        "pos_int": {"type": "integer", "minimum": 1},
        "pos_number": {"type": "number", "exclusiveMinimum": 0},
        "number_ge0": {"type": "number", "minimum": 0},
    }
    decl_props: dict[str, Any] = {}
    for f in DECLARATION_FIELDS[stage]:
        enum = DECLARATION_ENUMS.get(f)
        if enum is not None:
            decl_props[f] = {"enum": list(enum) + [UNRESOLVED]}
        else:
            base = shape_schema[DECLARATION_SHAPES[f]]
            decl_props[f] = {"anyOf": [base, {"const": UNRESOLVED}]}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"genebench/artifact/{stage}/v{SCHEMA_VERSION}",
        "x-gateway-fetch-contract": dict(GATEWAY_FETCH_CONTRACT),
        "title": f"GeneBench {stage} artifact v{SCHEMA_VERSION}",
        "type": "object",
        "required": list(ENVELOPE_REQUIRED),
        "properties": {
            "schema_version": {"const": SCHEMA_VERSION},
            "artifact_id": {"type": "string", "minLength": 1},
            "stage": {"const": stage},
            "task_id": {"type": "string", "minLength": 1},
            "config_id": {"type": "string", "minLength": 1},
            "arm": {"type": "string", "minLength": 1},
            "seed": {"type": "integer", "minimum": 0},
            "as_of": {"type": "string", "pattern": r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"},
            "produced_at": {"type": "string", "minLength": 1},
            "provenance": {"type": "array", "items": {
                "type": "object", "required": ["stage", "artifact_id"],
                "properties": {"stage": {"enum": list(STAGES)},
                               "artifact_id": {"type": "string", "minLength": 1}}}},
            "declarations": {"type": "object", "required": list(DECLARATION_FIELDS[stage]),
                             "properties": decl_props},
            "payload": {"type": "object", "required": list(payload_required(stage, profile)),
                        # 依赖某个声明的 payload 字段允许为 null —— 那是**诚实终止**（PAYLOAD_DEPENDS_ON）：
                        # 口径被标 unresolved 时这个数算不出来。共享文件必须说得出这件事，
                        # 否则 open 臂只能从题面猜「到底能不能写 null」。
                        "properties": {k: _nullable_if_dependent(stage, k, v)
                                       for k, v in payload_shape(stage, profile).items()}},
        },
        "x-genebench": {
            "three_state_note": "声明字段：有值 / 显式 'unresolved' / 缺失 三态；null 一律畸形。"
                                "语义层（与 TaskSpec、网关日志、可交易性视图的交叉核）在 "
                                "reference/artifact_schema.py::validate，JSON Schema 只管结构。",
        },
    }
