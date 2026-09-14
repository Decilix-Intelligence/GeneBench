"""卡 4.2：**harness 无关的轨迹源**（裁定 2026-09-04）。

边车逐请求把 request / response / usage 记进 run dir 的 `log/llm_log.jsonl`
（`Authorization` 剥掉再落盘）。采集器从这里取，**不再逐 harness 写轨迹提取器**。

**为什么这条比逐 harness 提取器强**：

* 有几个 harness 就有几种提取器，就有几种漂法 —— 而 OpenHands 的轨迹格式改一次，
  Steps 就悄悄少一半，主表上看不出来；
* **两臂经的是同一个边车** —— 轨迹口径因此天然对称。逐 harness 提取器要
  自己保证两臂对称，而那是靠人记得；
* 它同时是三件事的来源：`Steps`（模型调用序列）、`search_count` 的第二佐证
  （生成的候选表达式计数）、`usage`（§13.4「自报 tokens 要有网络侧佐证」的那一侧）。

**本模块零 `reference` 依赖** —— 它跑在执行面。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

LLM_LOG_REL = "log/llm_log.jsonl"

#: **归一映射，与 `runner/c41/egress_proxy.py` 逐字同源**
#: （`ops/test_llm_usage_shapes.py::test_the_two_alias_tables_are_the_same_table` 盯着相等）。
#: 为什么有两份：边车要**单文件**挂进容器（`/opt/egress_proxy.py`），不能 import 本模块 ——
#: 与 `MODEL_API_ALLOW` / `registry.collect_egress_hosts()` 是同一条纪律：
#: 两份字面量 + 一条相等断言，比一份「理论上共享、实际上漂了」的 import 可靠。
USAGE_ALIASES: dict[str, str] = {"input_tokens": "prompt_tokens",
                                 "output_tokens": "completion_tokens"}
CACHED_KEYS: tuple[str, ...] = ("cached_tokens", "cache_read_input_tokens",
                                "prompt_cache_hit_tokens")
DETAIL_KEYS: tuple[str, ...] = ("prompt_tokens_details", "input_tokens_details")

#: 归一后的键。`cached_prompt_tokens` 是**另记一列**，没有并进 `total_tokens` ——
#: 并进去会让 m6/m6b 那批走 Responses API、压根没有这个字段的历史 run 不可比，
#: 而成本护栏的收益不抵可比性的损失（3.2-claude-code 与本卡同结论，票据 N-? 登记）。
CANON_KEYS: tuple[str, ...] = ("prompt_tokens", "completion_tokens",
                               "cached_prompt_tokens", "total_tokens")

#: `wire_shape` 的取值域（与 `egress_proxy.WIRE_SHAPES` 同源，同样由测试盯着）。
WIRE_SHAPES: tuple[str, ...] = ("chat_completions", "responses",
                                "anthropic_messages", "unknown")


def normalize_usage(u: dict | None, path: str = "") -> dict:
    """把任一形状的 usage 归一。**读取侧的历史兼容层** —— 新记录由边车写入时就已归一，
    但 2026-09-07 之前落盘的 llm_log 里只有 `prompt/completion/total`
    加各家原始的缓存键，`cached_prompt_tokens` 与 `wire_shape` 都还没有。
    对已经写下的证据只能在读的时候补，补不了的（被截掉的流式尾巴）就是补不了。
    """
    if not isinstance(u, dict) or not u:
        return {}
    out: dict = {}
    for k, v in u.items():
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            out[USAGE_ALIASES.get(k, k)] = int(v)
    cached = None
    for dk in DETAIL_KEYS:
        d = u.get(dk)
        if not isinstance(d, dict):
            continue
        for ck in CACHED_KEYS:
            v = d.get(ck)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                cached = int(v)
                break
        if cached is not None:
            break
    if cached is None:
        for ck in CACHED_KEYS:
            v = out.get(ck)
            if isinstance(v, int):
                cached = v
                break
    if cached is not None:
        out["cached_prompt_tokens"] = cached
    if "total_tokens" not in out and ("prompt_tokens" in out or "completion_tokens" in out):
        out["total_tokens"] = out.get("prompt_tokens", 0) + out.get("completion_tokens", 0)
    if not out:
        return {}
    shape = u.get("wire_shape")
    out["wire_shape"] = shape if shape in WIRE_SHAPES else _shape_from(path, u)
    return out


def _shape_from(path: str, raw: dict) -> str:
    p = (path or "").split("?", 1)[0].rstrip("/").lower()
    if p.endswith("/chat/completions"):
        return "chat_completions"
    if p.endswith("/responses"):
        return "responses"
    if p.endswith("/messages") or p.endswith("/messages/count_tokens"):
        return "anthropic_messages"
    if "cache_read_input_tokens" in raw or "cache_creation_input_tokens" in raw:
        return "anthropic_messages"
    if "prompt_tokens" in raw:
        return "chat_completions"
    if "input_tokens" in raw:
        return "responses"
    return "unknown"


def usage_of(rec: dict) -> dict | None:
    """一条记录的归一 usage。**没有就是 `None`，不是 0** ——
    「上游没给」与「用了 0 个 token」在数值上不可分而结论相反。
    """
    u = normalize_usage(rec.get("usage"), rec.get("path") or "")
    return u or None


def usage_absent_reason(rec: dict) -> str | None:
    """这条为什么没有 usage。有 usage → `None`。

    * `upstream_error`：上游拒了（gemini-cli 的两个 run 就是 404 —— 那是
      **上游拒绝、无 usage**，不是「这次用了 0 个 token」）；
    * `empty_body` / `no_usage_in_body`：上游 200 但体里没有；
    * `truncated_no_usage`：我们的副本被截了（边车 2026-09-07 起会自己标）。
    """
    if usage_of(rec):
        return None
    said = rec.get("usage_absent")
    if isinstance(said, str) and said:
        return said
    st = rec.get("status")
    if isinstance(st, int) and st >= 400:
        return "upstream_error"
    if rec.get("response_truncated"):
        return "truncated_no_usage"
    return "empty_body" if not (rec.get("response_body") or "") else "no_usage_in_body"


class TraceError(RuntimeError):
    pass


def load(run_dir) -> list[dict] | None:
    """三态，与 `visibility.load_gateway_log` 同一条纪律：

    * 文件不存在 → `None`（**边车没记**，或这次运行根本没配模型代理）；
    * 存在且零条 → `[]`（**记了，但一次模型调用都没有**）。

    `[]` 与 `None` 在数值上不可区分而结论相反 —— 前者说「这个 agent 一次模型都没调」
    （那是一个**关于被测系统的发现**），后者说「我们没测到」。
    """
    p = Path(run_dir) / LLM_LOG_REL
    if not p.exists():
        return None
    out: list[dict] = []
    for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as e:
            # 与出向日志同一条理由（D-23）：写坏的行不能当成「这段时间没调用」。
            raise TraceError(f"{p}:{i} 不是 JSON：{e}") from None
        out.append(rec)
    return out


def calls(trace: list[dict] | None) -> list[dict] | None:
    """真正到达上游的模型调用（`decision == "allow"`）。"""
    if trace is None:
        return None
    return [r for r in trace if r.get("decision") == "allow"]


def steps(trace: list[dict] | None) -> int | None:
    """**Steps** = 模型调用次数。取不到就是 `None`，不是 0 ——
    0 是「它一次都没调」，那是关于被测系统的结论。"""
    c = calls(trace)
    return None if c is None else len(c)


def usage_totals(trace: list[dict] | None) -> dict | None:
    """§13.4 的**网络侧**证据：自报 tokens 要有它佐证。"""
    c = calls(trace)
    if c is None:
        return None
    tot = {k: 0 for k in CANON_KEYS}
    seen = False
    for r in c:
        u = usage_of(r) or {}
        for k in tot:
            v = u.get(k)
            if isinstance(v, (int, float)):
                tot[k] += int(v)
                seen = True
    return tot if seen else None


def usage_coverage(trace: list[dict] | None) -> dict | None:
    """每个 harness 的 llm_log **完不完整**：几条 allow、几条有 usage、缺的是哪一种。

    这是本模块唯一回答「这张表上的空格是谁的责任」的地方 ——
    `missing_reasons` 里 `upstream_error` 说的是被测链路，
    `truncated_no_usage` 说的是**我们的抽取器**。混成一个数就分不开了。
    """
    c = calls(trace)
    if c is None:
        return None
    reasons: dict[str, int] = {}
    shapes: dict[str, int] = {}
    have = 0
    for r in c:
        u = usage_of(r)
        if u:
            have += 1
            s = u.get("wire_shape") or "unknown"
        else:
            why = usage_absent_reason(r) or "unknown"
            reasons[why] = reasons.get(why, 0) + 1
            s = _shape_from(r.get("path") or "", r.get("usage") or {})
        shapes[s] = shapes.get(s, 0) + 1
    return {"calls": len(c), "with_usage": have, "missing": len(c) - have,
            "missing_reasons": dict(sorted(reasons.items())),
            "wire_shapes": dict(sorted(shapes.items()))}


def budget_denials(trace: list[dict] | None) -> list[dict] | None:
    """预算闸拒绝过几次。进遥测作预算曲线数据。"""
    if trace is None:
        return None
    return [r for r in trace if r.get("reason") == "budget_exceeded"]


#: 候选表达式的形状。`search_count` 的**第二佐证** —— agent 自报的搜索次数
#: 与「它到底让模型生成了几个候选」是两个数，对不上就说明自报值不可信。
_EXPR_HINT = re.compile(r'"(?:expression|factor_formulation|formula)"\s*:\s*"', re.I)


def candidate_expressions(trace: list[dict] | None) -> int | None:
    """从响应体里数生成过的候选表达式。

    **这是佐证不是判据**：一次响应里可能带多个候选，也可能一个都不带。
    它的用途是与 `payload.search_count` 比 —— 差得离谱时说明自报值不可信，
    而不是拿它去**替代**自报值（那会变成 harness 替 agent 声明，§1 禁的那件事）。
    """
    c = calls(trace)
    if c is None:
        return None
    n = 0
    for r in c:
        body = r.get("response_body") or ""
        n += len(_EXPR_HINT.findall(body))
    return n


def cross_check_tokens(self_reported: int | None, trace: list[dict] | None,
                       *, tol_ratio: float = 0.25) -> dict:
    """§13.4：`tokens > 0` 而网络侧一次调用都没有 → `telemetry_unbacked`。

    容差给得松（默认 25%）是**故意**的：harness 自报的口径与上游 usage 的口径
    本来就不同（有的算 system prompt，有的不算）。这条要抓的是**数量级的谎**，
    不是精度差 —— 收得太紧会让每一次运行都报一条假 finding。
    """
    net = usage_totals(trace)
    n_calls = steps(trace)
    if self_reported is None:
        return {"status": "unverified", "detail": "harness 没自报 tokens"}
    if net is None:
        # **「一次都没调」与「调了但上游没给 usage」是两个结论。**
        # 混成一个会让后者被报成 `telemetry_unbacked` —— 那是指着被测方说谎，
        # 而说谎的是我们的抽取器（实测：Codex 的 Responses API 把 usage 嵌在
        # `response.usage` 里，第一版抽取器只认顶层，于是真调了 3 次却报没调）。
        if n_calls:
            return {"status": "usage_unavailable", "calls": n_calls,
                    "detail": f"网络侧有 {n_calls} 次调用，但上游没给 usage —— "
                              f"**不能据此判自报值不实**"}
        if self_reported > 0:
            return {"status": "telemetry_unbacked",
                    "detail": f"自报 {self_reported} tokens，而网络侧一次调用都没有"}
        return {"status": "agree", "detail": "两边都是 0"}
    got = net["total_tokens"]
    if got == 0 and self_reported > 0:
        return {"status": "telemetry_unbacked",
                "detail": f"自报 {self_reported}，网络侧 usage 合计 0"}
    lo, hi = got * (1 - tol_ratio), got * (1 + tol_ratio)
    ok = lo <= self_reported <= hi
    return {"status": "agree" if ok else "mismatch",
            "self_reported": self_reported, "network": got,
            "detail": "" if ok else f"自报 {self_reported} 与网络侧 {got} 差得超过 {tol_ratio:.0%}"}
