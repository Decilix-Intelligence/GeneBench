# -*- coding: utf-8 -*-
"""S7 的 gold 引擎：**实现 B2 的包装接口**（裁定 N-83，2026-09-05）。

裁定原文：gold 必须遵守书面契约；qlib 有未归因偏离（N-39）且偏离清单未成，
**不能定义 gold**。B2 与 B3 日频逐位相同，B1 的差异即 ε 的来源。qlib 作对账参照。

**这个模块不重写 B2，它加载冻结的那一份。** `snapshots/v1/epsilon/impl_v2_b2.py`
（sha256 见 `B2_SHA256`）一个字节都不改 —— 它是 2026-09-01 那次「唯一输入是
`backtest_contract.md`、没有读过 qlib 也没有读过另外两份实现」的独立实现，
重写一遍就等于毁掉它的独立性，而 ε 量的正是「两份独立实现同一份声明会差多少」。

**两层补丁，都在内存里打，都带 sha 门**：

| 补丁 | 做什么 | 怎么证明它没改算法 |
| --- | --- | --- |
| **P-SELL** | 把 `sell_rule` 的两种读法做成开关 | 打完的源码 sha256 必须等于 `P_SELL_PATCHED_SHA256` —— 这个值是 2026-09-03 那次 materiality screen 记在 `ops/reports/materiality_s7_sell_rule.json` 里的。**逐字节相同 = 与那次实测用的是同一份补丁** |
| **LEDGER** | 逐日记下 `cash` / `mv` / `r_gross` / `r_net` | 只有赋值语句，**没有一处改变已有变量的值**；`ops/acceptance/s7_b2_wrapper_gate.py` 用「打了台账 vs 没打台账」跑同一份面板，11 项指标必须**逐位相同** |

**为什么 `sell_rule` 必须是开关而不是写死**：契约 §5 的字面是「卖已跌出目标组合的」
（= `dropped_from_target`，也是 B2 的原读法），而**已发布的四道 S7 题声明的是
`worst_n_drop`**（题面对 agent 写着「每期从持仓里卖掉信号最差的那几只」，即 qlib 读法）。
两种读法实测 **material**（B1 `ann_return_gross` 差 0.4460% 而 ε 是 0.2372%）。
写死任何一边，都会让 gold 与四道题里的一半对不上，而没有一处会报错。
A-1 这条歧义的登记见 `reference/artifact_schema.py:371`，
`s7-rob-02` 就是拿它做欠定探针的（`underdetermined: [sell_rule]`）。
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import genebench_config as cfg

#: 冻结的实现 B2。**不改、不复制到仓库里**。
B2_SOURCE = cfg.SNAPSHOTS / "v1" / "epsilon" / "impl_v2_b2.py"
B2_SHA256 = "83a8134750746b2f64ce180eb21b1b8f57aeaefa8e590aaddb65d417bb0f982a"

#: 打完 P-SELL 之后的源码 sha256。**来自 2026-09-03 materiality screen 的记录**
#: （`ops/reports/materiality_s7_sell_rule.json` → `impls.B2.patched_sha256`）。
#: 对上了，就说明本模块用的补丁与那次实测用的**逐字节相同** —— 这不是我自己给自己发的证书。
P_SELL_PATCHED_SHA256 = "0dd4a45a976eda240691eceaca66bd3863e55793bc18dc6cf92bda993061d76f"

#: 契约 §1：面板含 6 天暖机。`ops/test_backtest_b2.py` 有一条把它与
#: `reference.s7_oracle_common.WARMUP_DAYS` 绑住（D-21：同值两份必须有断言）。
WARMUP_DAYS = 6

_SW = ('\n# --- screen 开关（materiality 用；只加开关，不改算法）---------------------------\n'
       'import os as _os\n'
       '_GB_SELL_RULE = _os.environ.get("GB_SELL_RULE", "dropped_from_target")\n'
       '# ------------------------------------------------------------------------------\n')

#: 与 `ops/screen_runner.py::SWITCH_EDITS["P-SELL"]["B2"]` **必须逐字相同**
#: （`ops/test_backtest_b2.py::test_p_sell_edits_match_the_screen_harness`）。
P_SELL_EDITS: tuple[tuple[str, str], ...] = (
    ('INPUT = os.path.join(BASE, "bt_input_csi300_v2.parquet")',
     'INPUT = os.path.join(BASE, "bt_input_csi300_v2.parquet")' + _SW),
    ("                cand = held[~np.isin(held, tgt)]",
     '                cand = held if _GB_SELL_RULE == "worst_n_drop"'
     " else held[~np.isin(held, tgt)]"),
)

#: 台账补丁。**逐条都只是赋值**：没有一行改变 B2 已有变量的取值或求值次序。
#: 需要它的理由：S7 的 artifact 要 `ledger_check.max_abs_residual`
#: （= max |cash + mv − total_assets|），而 B2 只把三者的和存进 `ta_post`，
#: 没有把 `cash` 与 `mv` 分开留下来。少了它就只能在包装里**另算一遍**持仓市值 ——
#: 那等于在 gold 里塞进第二份实现，而两份会漂。
LEDGER_EDITS: tuple[tuple[str, str], ...] = (
    ("ANN = 252                     # §6",
     "ANN = 252                     # §6\n"
     "_GB_LEDGER = {}               # [ledger] 逐日台账；只写不读，B2 自己从不碰它"),
    ("    ta_post = np.zeros(n_days)     # 当日收盘、成交之后的总资产",
     "    ta_post = np.zeros(n_days)     # 当日收盘、成交之后的总资产\n"
     "    _gb_cash = np.zeros(n_days)    # [ledger]\n"
     "    _gb_mv = np.zeros(n_days)      # [ledger]"),
    ("        if e > prev:\n            ta_post[prev:e] = cash + Vf[prev:e] @ q",
     "        if e > prev:\n            ta_post[prev:e] = cash + Vf[prev:e] @ q\n"
     "            _gb_mv[prev:e] = Vf[prev:e] @ q          # [ledger]\n"
     "            _gb_cash[prev:e] = cash                  # [ledger]"),
    ("        ta_post[e] = cash + Vf[e] @ q\n        cost_d[e] = cost",
     "        ta_post[e] = cash + Vf[e] @ q\n"
     "        _gb_mv[e] = Vf[e] @ q                        # [ledger]\n"
     "        _gb_cash[e] = cash                           # [ledger]\n"
     "        cost_d[e] = cost"),
    ("    if prev < n_days:\n        ta_post[prev:] = cash + Vf[prev:] @ q",
     "    if prev < n_days:\n        ta_post[prev:] = cash + Vf[prev:] @ q\n"
     "        _gb_mv[prev:] = Vf[prev:] @ q                # [ledger]\n"
     "        _gb_cash[prev:] = cash                       # [ledger]"),
    ("    return metrics(freq, ta_post, ta_pre, cost_d, sell_d, buy_d)",
     "    _GB_LEDGER.clear()                               # [ledger]\n"
     "    _GB_LEDGER.update({\"cash\": _gb_cash, \"mv\": _gb_mv, \"ta_post\": ta_post,\n"
     "                       \"ta_pre\": ta_pre, \"cost_d\": cost_d,\n"
     "                       \"sell_d\": sell_d, \"buy_d\": buy_d})\n"
     "    return metrics(freq, ta_post, ta_pre, cost_d, sell_d, buy_d)"),
    ("    r_gross = (ta_post + cost_d) / prev_ta - 1.0",
     "    r_gross = (ta_post + cost_d) / prev_ta - 1.0\n"
     "    _GB_LEDGER[\"r_net\"] = r_net                      # [ledger]\n"
     "    _GB_LEDGER[\"r_gross\"] = r_gross                  # [ledger]"),
)

SELL_RULES = ("dropped_from_target", "worst_n_drop")


class WrapperError(RuntimeError):
    pass


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _apply(src: str, edits, what: str) -> str:
    """逐条**精确**替换：锚点必须恰好命中一次，否则立刻报错。

    不走 `patch -p0` —— 模糊匹配会悄悄打歪，而打歪的表现是「跑出来了、数不对」。
    """
    for anchor, repl in edits:
        n = src.count(anchor)
        if n != 1:
            raise WrapperError(
                f"{what} 的锚点在 B2 源码里命中 {n} 次（要求恰好 1 次）："
                f"{anchor.strip()[:60]!r} —— 冻结源码变了，补丁必须重对，不许模糊匹配")
        src = src.replace(anchor, repl)
    return src


def source(*, ledger: bool = True) -> str:
    """读冻结源码 → 打 P-SELL（核 sha）→ 打台账。"""
    raw = B2_SOURCE.read_text(encoding="utf-8")
    got = _sha(raw)
    if got != B2_SHA256:
        raise WrapperError(f"{B2_SOURCE} 的 sha256 是 {got}，钉的是 {B2_SHA256} —— "
                           f"gold 引擎的源码变了，这不是可以顺手放过的事")
    patched = _apply(raw, P_SELL_EDITS, "P-SELL")
    got = _sha(patched)
    if got != P_SELL_PATCHED_SHA256:
        raise WrapperError(
            f"打完 P-SELL 的 sha256 是 {got}，而 2026-09-03 materiality screen 记的是 "
            f"{P_SELL_PATCHED_SHA256} —— 本模块的补丁与那次实测用的**不是同一份**，"
            f"于是 sell_rule 的 material 证据不能拿来给这份 gold 背书")
    return _apply(patched, LEDGER_EDITS, "LEDGER") if ledger else patched


@contextlib.contextmanager
def _sell_rule_env(rule: str):
    """P-SELL 在**导入时**读环境变量。这里用与 screen 完全相同的机制，
    而不是导入后改模块属性 —— 换机制就等于换了一个没被那次实测覆盖的路径。"""
    if rule not in SELL_RULES:
        raise WrapperError(f"sell_rule={rule!r} 不在 {SELL_RULES}")
    old = os.environ.get("GB_SELL_RULE")
    os.environ["GB_SELL_RULE"] = rule
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("GB_SELL_RULE", None)
        else:
            os.environ["GB_SELL_RULE"] = old


def load(sell_rule: str, *, ledger: bool = True):
    """把（补丁后的）B2 装成一个模块对象。每次都是**新的**模块 ——
    B2 的常量是模块全局，复用会让上一次运行的声明漏进这一次。"""
    name = f"_gb_b2_{sell_rule}_{'led' if ledger else 'raw'}"
    spec = importlib.util.spec_from_loader(name, loader=None)
    mod = importlib.util.module_from_spec(spec)
    mod.__file__ = str(B2_SOURCE)
    with _sell_rule_env(sell_rule):
        exec(compile(source(ledger=ledger), str(B2_SOURCE), "exec"), mod.__dict__)  # noqa: S102
    if mod._GB_SELL_RULE != sell_rule:                                # noqa: SLF001
        raise WrapperError("P-SELL 开关没生效")
    return mod


# ------------------------------------------------------------------ 声明 → 配置

#: 声明字段 → B2 常量名。值是 `(常量名, 换算函数)`；`None` 表示**引擎不用它**，
#: 只做取值断言（见 `_EXPECTED`）。少一条就 raise —— 静默忽略一个声明字段的表现是
#: 「题面声明了、gold 没照做」，而两边都不会报。
_CONSTANTS: dict[str, tuple[str, Any]] = {
    "initial_capital": ("INIT_CASH", float),
    "lot_size": ("LOT", int),
}

#: 引擎不消费、但取值必须是这一个的字段。B2 是照契约写死的，
#: 声明成别的值而引擎照跑，就是「声明与实现不一致且无人报错」。
_EXPECTED: dict[str, Any] = {
    "adjust": "post",
    "fill_price": "close",
    "settlement": "t_plus_1",
    "share_accounting": "adjusted_shares",
    "delisting_policy": "force_liquidate_last_day",
    "tradability_policy": "skip_untradable",
    "risk_free_rate": 0,
    "first_rebalance_day": "window_start",
}

#: 引擎完全不碰、由上层（`s7_oracle_common`）消费的字段。
_PASSTHROUGH = ("calendar_id", "benchmark")


def config_from_declared(declared: dict) -> dict:
    """题面 `declared` → B2 的运行配置。**逐字段可测、无法映射即报错。**

    这个函数是 N-83 裁定里「声明→配置的映射逐字段可测」的落点：
    每一个声明字段要么变成 B2 的一个常量、要么被断言成契约写死的那个取值、
    要么显式登记为「引擎不消费」。**没有第四种情况** ——
    第四种情况就是「题面写了什么都不影响 gold」。
    """
    d = dict(declared)
    cfg_out: dict[str, Any] = {}

    for field, expect in _EXPECTED.items():
        if field not in d:
            raise WrapperError(f"声明缺 {field} —— 契约必填，缺失不许拿默认值顶上")
        got = d.pop(field)
        if got != expect:
            raise WrapperError(
                f"{field}={got!r}，而实现 B2 是照 {expect!r} 写的。"
                f"照跑等于「声明与实现不一致且无人报错」；要支持别的取值得先改契约与实现")
        cfg_out[field] = got

    for field, (const, cast) in _CONSTANTS.items():
        if field not in d:
            raise WrapperError(f"声明缺 {field}")
        cfg_out[const] = cast(d.pop(field))

    strat = d.pop("strategy", None)
    if not isinstance(strat, dict) or strat.get("type") != "TopkDropout":
        raise WrapperError(f"strategy 必须是 TopkDropout，实得 {strat!r}")
    for k, const in (("topk", "TOPK"), ("n_drop", "NDROP")):
        if k not in strat:
            raise WrapperError(f"strategy 缺 {k}")
        cfg_out[const] = int(strat[k])

    cm = d.pop("cost_model", None)
    if not isinstance(cm, dict):
        raise WrapperError("cost_model 缺失或不是对象")
    for k in ("buy_bps", "sell_bps", "min_cost_cny", "impact_cost"):
        if k not in cm:
            raise WrapperError(f"cost_model 缺 {k}")
    if float(cm["impact_cost"]) != 0.0:
        raise WrapperError(f"impact_cost={cm['impact_cost']!r}；B2 不计滑点（契约 §3），"
                           f"非零值照跑就是把一条声明当空气")
    cfg_out["BUY_RATE"] = float(cm["buy_bps"]) / 10_000.0
    cfg_out["SELL_RATE"] = float(cm["sell_bps"]) / 10_000.0
    cfg_out["MIN_COST"] = float(cm["min_cost_cny"])
    cfg_out["impact_cost"] = 0.0

    freq = d.pop("rebalance_frequency", None)
    if freq not in ("daily", "weekly", "monthly"):
        raise WrapperError(f"rebalance_frequency={freq!r} 不在契约 §2 的三档里")
    if freq != "daily":
        raise WrapperError(
            f"rebalance_frequency={freq!r}：weekly/monthly 两档的 ε 目前 usable=false"
            f"（N-85），gold 出得来但判不了。v1 只放 daily")
    cfg_out["rebalance_frequency"] = freq

    rule = d.pop("sell_rule", None)
    if rule not in SELL_RULES:
        raise WrapperError(f"sell_rule={rule!r} 不在 {SELL_RULES}（A-1 歧义的两个读法）")
    cfg_out["sell_rule"] = rule

    for field in _PASSTHROUGH:
        if field in d:
            cfg_out[field] = d.pop(field)

    if d:
        raise WrapperError(
            f"声明里有本包装不认识的字段 {sorted(d)} —— 静默忽略的表现是"
            f"「题面声明了、gold 没照做」，而两边都不报")
    return cfg_out


# ------------------------------------------------------------------ 跑

_MUTABLE_CONSTANTS = ("INIT_CASH", "LOT", "TOPK", "NDROP", "BUY_RATE", "SELL_RATE", "MIN_COST")

DAILY_COLUMNS = ("date", "cash", "mv", "total_assets", "r_gross", "r_net",
                 "buy_val", "sell_val", "cost_abs", "ta_pre_trade")


def run(panel: pd.DataFrame, config: dict) -> pd.DataFrame:
    """跑 gold 引擎，返回契约 §7 的逐日表（列见 `DAILY_COLUMNS`）。

    **窗口从面板自己推**（`START` = 第 `WARMUP_DAYS+1` 个日期，`END` = 最后一个）：
    面板已经把窗口编码进去了，再从别处取一份就有了两个可能不一致的来源（D-32）。
    """
    dates = sorted(pd.unique(panel["date"].astype(str)))
    if len(dates) <= WARMUP_DAYS:
        raise WrapperError(f"面板只有 {len(dates)} 个交易日，不够 {WARMUP_DAYS} 天暖机 + 窗口")

    b2 = load(config["sell_rule"])
    for const in _MUTABLE_CONSTANTS:
        if const not in config:
            raise WrapperError(f"配置缺 {const}")
        setattr(b2, const, config[const])
    b2.START, b2.END = dates[WARMUP_DAYS], dates[-1]

    root = cfg.create_dir(cfg.GENEBENCH_ROOT / "scratch" / "b2_runs")
    with tempfile.TemporaryDirectory(dir=root) as tmp:
        p = Path(tmp) / "bt_input_csi300_v2.parquet"
        panel.to_parquet(p, index=False, compression="zstd")
        p.chmod(0o600)
        b2.INPUT = str(p)
        d, _codes, A = b2.load_panel()
        dates_w, S = b2.build_window(d, A)
        top, n_top = b2.build_targets(S)
        summary = b2.run(config["rebalance_frequency"], dates_w, S, top, n_top)

    led = b2._GB_LEDGER                                               # noqa: SLF001
    missing = [k for k in ("cash", "mv", "ta_post", "ta_pre", "cost_d",
                           "sell_d", "buy_d", "r_net", "r_gross") if k not in led]
    if missing:
        raise WrapperError(f"台账缺 {missing} —— 补丁没打上，而没打上的表现是"
                           f"「ledger_check 恒为 0」，那正是 F7")
    daily = pd.DataFrame({
        "date": [str(x) for x in dates_w],
        "cash": led["cash"], "mv": led["mv"], "total_assets": led["ta_post"],
        "r_gross": led["r_gross"], "r_net": led["r_net"],
        "buy_val": led["buy_d"], "sell_val": led["sell_d"], "cost_abs": led["cost_d"],
        # 非事件日 `ta_pre` 是 NaN；B2 的换手用 `inf` 顶（当日分子恒为 0，0/inf = 0）。
        # 这里就落 `inf`，好让上层 `s7_oracle_common.metrics` 算出与 B2 相同的换手。
        "ta_pre_trade": np.where(np.isnan(led["ta_pre"]), np.inf, led["ta_pre"]),
    })
    daily.attrs["b2_metrics"] = summary
    daily.attrs["sell_rule"] = config["sell_rule"]
    return daily[list(DAILY_COLUMNS)]
