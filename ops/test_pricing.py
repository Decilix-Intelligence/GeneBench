# -*- coding: utf-8 -*-
"""卡 1.5 价目表的红测：缺价出 None（不是 0）、手算一例对得上、每行有出处、注册表里的
model 都能定价、以及 `$` 列真的由 `cost_usd` 填。"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from runner import pricing as PR
from runner import registry as REG
from scorer import report as R

REPO = Path(__file__).resolve().parents[1]
YAML_PATH = REPO / "runner" / "pricing.yaml"


# ——— 表本身 ————————————————————————————————————————————————

def test_every_row_has_a_source_url_and_currency():
    """价没有出处就是一个凭空的数 —— 主表上没法回答「这个 $ 是怎么来的」。"""
    doc = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))
    rows = doc["prices"]
    assert rows, "价目表是空的"
    for r in rows:
        assert (r.get("source_url") or "").startswith("https://"), f"{r.get('model')} 没有 source_url"
        assert r.get("currency") == "USD", f"{r.get('model')} 的 currency 不是 USD"


def test_placeholder_rows_say_why_they_have_no_price():
    """留位行（价 null）必须写清为什么 —— 否则「没接」与「忘了填」不可分。"""
    for r in PR.load():
        if r.get("input_per_mtok") is None:
            assert r.get("note"), f"{r['model']} 价是 null 却没写 note"


def test_alias_of_inherits_the_price_but_keeps_its_own_identity():
    """`deepseek-chat` 是注册表写的 id，上游实际服务的是 `deepseek-v4-flash`。
    别名继承价，**不另抄一份数字**（抄的那份必然漂）。"""
    chat, flash = PR.price_of("deepseek-chat"), PR.price_of("deepseek-v4-flash")
    assert chat is not None and flash is not None
    for f in PR.PRICE_FIELDS:
        assert chat[f] == flash[f]
    assert chat["model"] == "deepseek-chat"      # 身份不被别名吃掉


def test_registry_models_are_all_priced():
    """注册表里跑得起来的每个 model 都要有非 null 的价 —— 否则主表的 `$` 列是空的，
    而空列不会让任何测试变红（这条测试就是为了让它变红）。"""
    for c in REG.CONFIGS:
        p = PR.price_of(c.model)
        assert p is not None, f"{c.config_id} 的 model {c.model!r} 在价目表里没有可用的价"
        assert p["input_per_mtok"] > 0 and p["output_per_mtok"] > 0
        assert PR.row_of(c.model)["base_url_host"] == c.host, \
            f"{c.model!r} 的 base_url_host 与注册表的 {c.host!r} 对不上"


# ——— 缺价三态 ————————————————————————————————————————————————

def test_missing_price_is_none_not_zero():
    u = {"prompt_tokens": 1000, "completion_tokens": 100}
    assert PR.cost_usd(u, "claude") is None          # 留位行：有 row，没 price
    assert PR.row_of("claude") is not None
    assert PR.price_of("claude") is None
    assert PR.cost_usd(u, "没有这个模型") is None      # 表外：连 row 都没有
    assert PR.row_of("没有这个模型") is None
    assert PR.cost_usd(u, None) is None


def test_missing_usage_is_none_but_zero_tokens_is_zero():
    """`None` = 我们算不出；`0.0` = 调了但没 token。两件事在主表上必须可分。"""
    assert PR.cost_usd(None, "deepseek-chat") is None
    assert PR.cost_usd({}, "deepseek-chat") is None
    assert PR.cost_usd({"total_tokens": 0}, "deepseek-chat") is None      # 只有合计，分不出进出
    assert PR.cost_usd({"prompt_tokens": 0, "completion_tokens": 0}, "deepseek-chat") == 0.0


# ——— 算价 ————————————————————————————————————————————————

def test_hand_computed_cost():
    """手算：deepseek-v4-flash 高峰价 input 0.44 / output 1.32（每 1M token）。
    真语料里的一条 usage：prompt 8678、completion 334。
        (8678 × 0.44 + 334 × 1.32) / 1e6 = (3818.32 + 440.88) / 1e6 = 0.0042592
    """
    u = {"prompt_tokens": 8678, "completion_tokens": 334, "total_tokens": 9012}
    assert PR.cost_usd(u, "deepseek-v4-flash") == pytest.approx(0.0042592, abs=1e-12)
    assert PR.cost_usd(u, "deepseek-chat") == pytest.approx(0.0042592, abs=1e-12)


def test_cache_hit_tokens_are_billed_at_the_cache_price():
    """命中的输入按 0.014、其余按 0.44：
        (600 × 0.44 + 400 × 0.014 + 100 × 1.32) / 1e6 = (264 + 5.6 + 132) / 1e6 = 0.0004016
    """
    u = {"prompt_tokens": 1000, "prompt_cache_hit_tokens": 400, "completion_tokens": 100}
    assert PR.cost_usd(u, "deepseek-v4-flash") == pytest.approx(0.0004016, abs=1e-12)
    #: 没有命中数时按整价 —— 严格更贵（上界方向）
    plain = PR.cost_usd({"prompt_tokens": 1000, "completion_tokens": 100}, "deepseek-v4-flash")
    assert plain > PR.cost_usd(u, "deepseek-v4-flash")


def test_cache_hit_is_clamped_to_prompt_tokens():
    """命中数被上游写得比 prompt_tokens 还大时不能算出负的 miss。"""
    u = {"prompt_tokens": 100, "prompt_cache_hit_tokens": 999, "completion_tokens": 0}
    got = PR.cost_usd(u, "deepseek-v4-flash")
    assert got == pytest.approx(100 * 0.014 / 1e6, abs=1e-12)


# ——— 接进结算 ————————————————————————————————————————————————

def _rec(cost, cfg="cfg-x", arm="strict", task="t1"):
    return {"task_id": task, "stage": "S1", "config_id": cfg, "arm": arm, "seq": 1,
            "run_status": "ok", "sr_bucket": "scorable", "validity": "valid",
            "malformed": False, "l3_pass": True, "steps": 3, "latency_s": 1.0,
            "cost_usd": cost}


def test_table_a_dollar_column_comes_from_cost_usd():
    rows = R.table_a([_rec(0.001, task="t1"), _rec(0.003, task="t2")])
    assert len(rows) == 1
    assert rows[0]["$"] == pytest.approx(0.002)


def test_table_a_dollar_column_is_empty_not_zero_when_nothing_is_priced():
    """一条都算不出时 `$` 必须是 None —— 0 会进均值与排名。"""
    rows = R.table_a([_rec(None, task="t1"), _rec(None, task="t2")])
    assert rows[0]["$"] is None
    assert "$" in R.TABLE_A_COLUMNS


def test_pricing_module_does_not_depend_on_the_reference_plane():
    """价目表要跑在执行面（f02）—— 那里没有 `reference/`。"""
    src = (REPO / "runner" / "pricing.py").read_text(encoding="utf-8")
    for line in src.splitlines():
        s = line.strip()
        assert not (s.startswith("import reference") or s.startswith("from reference")), \
            f"pricing.py 引了参考面：{s}"
