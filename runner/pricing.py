"""卡 1.5：**价目表**（2026-09-06）—— 主表 `$` 列的算价机器。

价钉在 `runner/pricing.yaml`（带 `source_url` / `retrieved_at`），本模块只负责查表与算钱。

**三条纪律**：

* **缺价 → `None`，不是 0。** 0 会进均值与排名 —— 主表上「这家没接」会被读成「这家不要钱」，
  而那两件事在结论上相反。这与 `llm_trace` 的三态、`report` 的空值纪律是同一条。
* **`price_of` 只回「能算钱的价」。** 表里有行但价是 null（未接入的留位行）与表里根本没这一行，
  对 `price_of` 都是 `None`；要区分这两者用 `row_of()`（留位行有 row、没有 price）。
* **本模块零 `reference` 依赖，import 期零第三方依赖** —— 它要能在执行面（f02）import。
  `yaml` 只在 `load()` 里局部 import（与 `runner/inject.py:392` 同一个理由：yaml 不是 f02 的硬依赖）。

**价档取上界**：DeepSeek 2026-08-16 起分高峰/低谷两档（低谷是高峰的一半），而边车的
`llm_log.jsonl` 不记这次调用落在哪一档。表里 `*_per_mtok` 取的是**高峰价**，
于是 `cost_usd` 是**成本上界**而不是账单实数。逐条按调用时刻判档 = v1.1。
"""
from __future__ import annotations

from pathlib import Path

PRICING_YAML = Path(__file__).resolve().parent / "pricing.yaml"

#: 价字段（`alias_of` 继承时逐个补空）。单位一律「每 1M token 的美元数」。
PRICE_FIELDS: tuple[str, ...] = ("input_per_mtok", "output_per_mtok", "cache_hit_input_per_mtok")

#: 各家 usage 里「命中缓存的输入 token」叫什么。DeepSeek 是 `prompt_cache_hit_tokens`，
#: OpenAI 是 `prompt_tokens_details.cached_tokens`（边车 `_norm_usage` 只搬平铺的数值键，
#: 所以嵌套那一份到不了这里 —— 两个名字都认，认不到就当没命中，按整价算，那是**上界**）。
CACHE_HIT_KEYS: tuple[str, ...] = ("prompt_cache_hit_tokens", "cached_tokens", "cache_read_input_tokens")

_CACHE: dict[str, list[dict]] | None = None


class PricingError(RuntimeError):
    pass


def load(path: Path | str | None = None, *, force: bool = False) -> list[dict]:
    """读价目表，按文件路径缓存。返回**已解析 `alias_of`** 的行列表（顺序同文件）。"""
    global _CACHE
    p = Path(path or PRICING_YAML)
    key = str(p)
    if not force and _CACHE is not None and key in _CACHE:
        return _CACHE[key]
    import yaml                                    # 局部 import：yaml 不是 f02 的硬依赖
    doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    rows = list(doc.get("prices") or [])
    if not rows:
        raise PricingError(f"{p} 里一行价都没有")
    by_model: dict[str, dict] = {}
    for r in rows:
        m = r.get("model")
        if not m:
            raise PricingError(f"{p} 里有一行没写 model：{r}")
        if m in by_model:
            raise PricingError(f"{p} 里 model 重复：{m!r}")
        by_model[m] = r
    for r in rows:                                  # alias_of：**只补空**，不覆盖已写的值
        tgt = r.get("alias_of")
        if not tgt:
            continue
        if tgt not in by_model:
            raise PricingError(f"{r['model']!r} 的 alias_of 指向表外的 {tgt!r}")
        if by_model[tgt].get("alias_of"):
            raise PricingError(f"{r['model']!r} 的 alias_of 指向另一个别名 {tgt!r}（不做链式解析）")
        for f in PRICE_FIELDS:
            if r.get(f) is None:
                r[f] = by_model[tgt].get(f)
    _CACHE = dict(_CACHE or {})
    _CACHE[key] = rows
    return rows


def row_of(model: str | None, path: Path | str | None = None) -> dict | None:
    """表里那一行（**留位行也算有行**，它的价是 null）。没这一行 → `None`。"""
    if not model:
        return None
    for r in load(path):
        if r.get("model") == model:
            return r
    return None


def price_of(model: str | None, path: Path | str | None = None) -> dict | None:
    """能算钱的价 → `{input_per_mtok, output_per_mtok, cache_hit_input_per_mtok, currency, model, source_url}`。

    **没这一行、或输入/输出价任一为 null → `None`**（缺价，不是 0）。
    `cache_hit_input_per_mtok` 允许是 `None`（那家不分缓存价），不影响本函数出数。
    """
    r = row_of(model, path)
    if r is None:
        return None
    if r.get("input_per_mtok") is None or r.get("output_per_mtok") is None:
        return None
    return {"model": r["model"], "currency": r.get("currency") or "USD",
            "source_url": r.get("source_url"),
            **{f: r.get(f) for f in PRICE_FIELDS}}


def _cache_hit_tokens(usage: dict) -> int:
    for k in CACHE_HIT_KEYS:
        v = usage.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return max(0, int(v))
    return 0


def cost_usd(usage: dict | None, model: str | None, path: Path | str | None = None) -> float | None:
    """这段 usage 花了多少钱（USD）。**算不出就是 `None`，不是 0。**

    算不出的两种来源，都返回 `None`：

    * **缺价**（表里没这个 model，或它是留位行）；
    * **缺 usage**（`usage is None`，或里面一个 token 数都没有）——
      `usage = {}` 与「这次没调模型」在数值上不可分，两边都不该出一个 `0.00` 摆到主表上。
      注意 `{"prompt_tokens": 0, "completion_tokens": 0}` **是**可算的，出 `0.0`：
      那是「调了但没有 token」，与「我们算不出」不是一回事。

    缓存：usage 里带命中数（`CACHE_HIT_KEYS`）且表里有 `cache_hit_input_per_mtok` 时，
    命中的那部分按缓存价、其余按整价。**表里没有缓存价就整段按整价** —— 那会高估，
    而高估是上界方向；低估会让预算曲线说谎。
    """
    p = price_of(model, path)
    if p is None or not isinstance(usage, dict):
        return None
    pt, ct = usage.get("prompt_tokens"), usage.get("completion_tokens")
    pt = int(pt) if isinstance(pt, (int, float)) and not isinstance(pt, bool) else None
    ct = int(ct) if isinstance(ct, (int, float)) and not isinstance(ct, bool) else None
    if pt is None and ct is None:
        return None
    pt, ct = pt or 0, ct or 0
    hit = min(_cache_hit_tokens(usage), pt)
    hit_price = p.get("cache_hit_input_per_mtok")
    if hit_price is None:
        hit = 0                                     # 没有缓存价 → 整段按整价（上界）
    miss = pt - hit
    total = (miss * float(p["input_per_mtok"])
             + hit * float(hit_price or 0.0)
             + ct * float(p["output_per_mtok"])) / 1_000_000.0
    return round(total, 8)
