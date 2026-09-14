# -*- coding: utf-8 -*-
"""两条守门：① 锁住 A↔B 的**未归因残差**；② qlib 口径漂移哨兵。

**为什么要锁**：A↔B 的 `ann_return_gross` 差 22.69% **不是缺陷**，
是**知情保留**的欠定度量。**它的成因尚未归因** —— 隔离实验已排除 `sell_rule`
（单独效应仅 0.38%–0.45%，与 22.69% 差约 50 倍）。
锁的对象是**这个残差本身仍然存在**，不是任何一条候选成因。
日后有人「顺手把它修好」= 烧掉一个还没查清的观测量，而且**不会有任何东西报错**。

**为什么要哨兵**：`§8` 记了六条「qlib 与我们声明**已核对一致**」的条目。
pyqlib 版本已钉死，但升级迟早发生 —— 届时这条测试是唯一会响的东西。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import genebench_config as cfg  # noqa: E402

EPS = cfg.SNAPSHOTS_V1 / "epsilon"
QLIB = cfg.ENV / "lib" / "python3.10" / "site-packages" / "qlib"


def _m(p: Path) -> dict:
    d = json.loads(p.read_text(encoding="utf-8"))
    return d["metrics"] if "metrics" in d else d


# ================================================= ① A↔B 未归因残差状态锁

@pytest.mark.skipif(not (EPS / "bt_A_rd1.json").exists(), reason="实现 A 的产物尚未生成")
def test_ab_unattributed_residual_is_still_present():
    """A↔B 的**未归因残差**必须**仍然存在**。它消失 = 有人改了 A 或 B。

    **锁的是现象，不是成因。** 这个残差的成因**未归因**：
    隔离实验（同一份实现内部单切 `sell_rule`）已把 `sell_rule` / A-1 排除在外
    —— 它的单独效应只有 0.38%–0.45%，与 22.69% 差约 50 倍。
    所以本测试不假设任何一条成因，只断言残差还在。

    判据是两条一起看，因为这个残差的**特征**就是「换手一样、收益不一样」：
    单看收益差会把别的改动也误报进来。
    """
    a = _m(EPS / "bt_A_rd1.json")
    bs = [_m(EPS / f"out_v2_b{n}_daily.json") for n in (1, 2, 3)]
    bg = sum(x["ann_return_gross"] for x in bs) / 3
    bt = sum(x["turnover_two_way_mean"] for x in bs) / 3
    gross_rel = abs(a["ann_return_gross"] - bg) / abs(bg)
    turn_rel = abs(a["turnover_two_way_mean"] - bt) / abs(bt)

    assert turn_rel < 0.03, (
        f"A↔B 的换手差已升到 {turn_rel:.2%}（原为 0.51%）—— "
        f"这个残差的**特征**（换手一样、收益不一样）不成立了，先去查是什么变了。")
    assert gross_rel > 0.10, (
        f"\n\nA↔B 的 ann_return_gross 差已降到 {gross_rel:.2%}（原为 22.69%）。\n"
        f"**这不是修好了一个 bug —— 这是抹掉了一个还没查清的观测量。**\n"
        f"这 22.69% 是 A↔B 的**未归因残差**：**成因未归因**。\n"
        f"  隔离实验（同一份实现内部单切 `sell_rule`）已把 sell_rule / A-1 **排除**：\n"
        f"  它的单独效应只有 0.38%–0.45%（daily ε=0.237%），与 22.69% 差约 50 倍。\n"
        f"  已排除的还有：费用口径、total_cost 取数通道（N-28）、risk_degree。\n"
        f"**它消失说明有人改了 A 或 B —— 先去查什么变了**，不要直接改本测试的阈值。\n"
        f"排查顺序：\n"
        f"  · 实现 A 的产物 {EPS / 'bt_A_rd1.json'}（qlib 版本 / 参数 / 口径转换）\n"
        f"  · 三份 B 的产物 out_v2_b{{1,2,3}}_daily.json 与快照里的实现源码\n"
        f"  · 输入 parquet 与窗口是否被换过\n"
        f"确认是有意为之（例如残差终于被归因并消除）之后，同步更新这四处再改本测试：\n"
        f"  · ops/specs/backtest_contract.md §9（未归因残差 + 知情保留）与歧义清单\n"
        f"  · ops/data_cards/gold_factors.md\n"
        f"  · ops/reports/ambiguity_impact_2.2b.md\n"
        f"  · ops/tickets.md 的 N-27 / N-25\n")


def test_unattributed_residual_is_documented_in_all_three_places():
    """三处都要写明这是**未归因残差**且是知情保留的 —— 少一处，读到那处的人就会去修它。

    还要写明归因是怎么被撤回的（隔离实验），否则「定位到 A-1」那条排除法结论会复活。
    """
    for p, what in (
        (cfg.OPS / "specs" / "backtest_contract.md", "声明"),
        (cfg.DATA_CARDS / "gold_factors.md", "gold 数据卡"),
        (cfg.REPORTS / "ambiguity_impact_2.2b.md", "ε/歧义报告"),
    ):
        assert p.exists(), p
        t = p.read_text(encoding="utf-8")
        assert "22.69%" in t, f"{what} 里没写这个差异的量"
        assert "未归因残差" in t, f"{what} 里没写明这 22.69% 是**未归因残差**（成因未定）"
        assert ("知情保留" in t or "知情地保留" in t), f"{what} 里没写明这是知情保留"
        assert "隔离实验" in t, (
            f"{what} 里没写隔离实验 —— 「sell_rule/A-1 已被排除」这条会丢，"
            f"排除法归因「定位到 A-1」就会复活")


# =============================================================== ② qlib 漂移哨兵

@pytest.fixture(scope="module")
def src() -> dict[str, str]:
    files = {"exchange": QLIB / "backtest" / "exchange.py",
             "account": QLIB / "backtest" / "account.py",
             "strategy": QLIB / "contrib" / "strategy" / "signal_strategy.py"}
    missing = [str(p) for p in files.values() if not p.exists()]
    if missing:
        pytest.skip(f"qlib 源码不可读：{missing}")
    return {k: p.read_text(encoding="utf-8", errors="replace") for k, p in files.items()}


def test_sentinel_cost_basis_is_dealt_value_after_rounding(src):
    """§8 已核① 费用基数 = **实际成交金额**（在取整/裁剪之后算）。"""
    e = src["exchange"]
    assert re.search(r"trade_val\s*=\s*order\.deal_amount\s*\*\s*trade_price", e), \
        "qlib 不再用 order.deal_amount * trade_price 作费用基数 —— §8 已核① 失效"
    assert re.search(r"trade_cost\s*=\s*max\(\s*trade_val\s*\*\s*cost_ratio\s*,\s*self\.min_cost", e), \
        "qlib 的 trade_cost 公式变了 —— §8 已核① / ③ 需重核"


def test_sentinel_no_stamp_duty_or_transfer_fee(src):
    """§8 已核② 卖出侧只有 close_cost，无印花税/过户费独立项。"""
    e = src["exchange"]
    for bad in ("stamp_duty", "stamp_tax", "transfer_fee"):
        assert bad not in e, f"qlib 新增了 {bad} —— 我们的 0.0015 可能重复计税，§8 已核② 失效"


def test_sentinel_deal_price_close_has_no_vwap_fallback(src):
    """§8 已核④ `deal_price='close'` 不会隐式回退到 vwap/open。"""
    e = src["exchange"]
    assert re.search(r'buy_price\s*=\s*sell_price\s*=\s*deal_price', e) or \
           re.search(r'deal_price', e), "deal_price 处理逻辑变了"
    m = re.search(r"def get_deal_price.*?(?=\n    def )", e, re.S)
    if m:
        body = m.group(0)
        assert "vwap" not in body.lower(), "get_deal_price 里出现了 vwap 回退 —— §8 已核④ 失效"


def test_sentinel_hold_thresh_and_limit_defaults(src):
    """§8 已核⑤⑥ T+1 与涨跌停双向禁止的**默认值**没变。"""
    s = src["strategy"]
    assert re.search(r"hold_thresh\s*=\s*1\b", s), "hold_thresh 默认不再是 1 —— T+1 假设失效"
    assert re.search(r"forbid_all_trade_at_limit\s*=\s*True", s), \
        "forbid_all_trade_at_limit 默认不再是 True —— 涨跌停双向禁止假设失效"


def test_sentinel_report_columns_still_mean_what_we_think(src):
    """§8 缺口① 的地基：`total_cost` 是绝对金额、`cost` 是**费用率**。

    这条是 N-28 的根因。若 qlib 改了这两列的语义，
    `reference/backtest.py::_total_cost` 会**静默**给出错的数。
    """
    a = src["account"]
    assert re.search(r"cost_rate\s*=\s*now_cost\s*/\s*last_account_value", a), \
        "qlib 的 cost 列不再是 now_cost/last_account_value —— N-28 的修法需重核"
    assert re.search(r"total_cost\s*=\s*self\.accum_info\.get_cost", a), \
        "account.py 的 total_cost 不再取自 accum_info.get_cost（累计绝对费用）—— N-28 的修法需重核"


def test_sentinel_risk_degree_default_is_still_declared_gap(src):
    """§8 缺口③：`risk_degree` 默认值。我们显式传 1.0，但默认值变了要知道。"""
    s = src["strategy"]
    m = re.search(r"risk_degree\s*:\s*float\s*=\s*([0-9.]+)", s) or \
        re.search(r"risk_degree\s*=\s*([0-9.]+)", s)
    assert m, "找不到 risk_degree 默认值 —— §8 缺口③ 需重核"
    assert m.group(1) == "0.95", (
        f"risk_degree 默认值从 0.95 变成了 {m.group(1)} —— "
        f"§8 缺口③ 的描述要更新（我们显式传 1.0，行为不变，但文档会误导）")


def test_sentinel_fee_reserve_is_still_commented_out(src):
    """§8 缺口④：qlib **不做**费用预留（那行被注释掉）。"""
    s = src["strategy"]
    assert re.search(r"#\s*value\s*=\s*value\s*/\s*\(\s*1\s*\+\s*.*open_cost", s), \
        ("qlib 的费用预留行不再是注释状态 —— §8 缺口④ 失效，"
         "S7 判据里的口径转换要重做")
