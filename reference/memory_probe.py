# -*- coding: utf-8 -*-
"""记忆探针（N-31）的**判卷器与题集校验器**。

规格：`ops/specs/card_3.2_5.1_memory_probes.md`。本模块归卡 5.1，
卡 3.2 只出题面 —— **题集必须先过 :func:`validate_probe_set` 才算可用**。

三条设计约束（2026-09-01 签字）
------------------------------

1. **判卷程序化，不用 LLM。** 这些题的答案是数值（CPI 同比、指数点位、除权因子），
   判对错是**带容差的数值比对**。用模型判卷会把**裁判方差**引进一个本来零方差的探针 ——
   探针度量的是「模型记不记得」，不该再叠一层「判官看不看得懂」。
   :data:`NO_LLM_JUDGE` 是这条约束的代码化，`ops/test_memory_probe.py` 会审计本文件源码。
2. **答案格式受约束。** 程序化判卷成立的前提是输出可解析：每道题都规定
   `NUMBER` / `CODES` / `DATE` 三种格式之一，或字面量 ``UNKNOWN``。
   解析不了记 ``unparseable``，**永不计为命中**。
3. **对照题与探针题结构同构。** 同类 = 同一数据源同一字段同一题模板；
   同难度 = 同一问法同一容差；**只有日期不同**。
   没有对照阶梯，0% 命中无法区分「模型干净」与「模型什么都答不出」。

探针是**权重**的属性，不是 harness 的属性（2026-09-01 签字补充）
-----------------------------------------------------------

**按模型跑一次**，在双臂指令上下文**之外**跑（裸 prompt，不带 strict/open 的任何指令），
结果按 ``model_id`` **join** 到各配置。理由：若在臂指令内跑，GQ 臂的「不得推断补全」指令
可能压制作答，会把「协议让它诚实」与「协议让它不答」混在一起；而且每配置各跑一遍白费成本。
本模块的 :func:`summarize` 因此以**模型**为单位汇总，配置层只做 join。

产出四种结局，**互不合并**
--------------------------

====================  ==============================================
``hit``               答案落在容差带内 —— **权重前视的直接证据**
``miss``              答了，但不对 —— 干净
``abstain``           明确答「不知道」 —— 干净，但与 ``miss`` 是两件事
``unparseable``       格式不合 —— **不作数**，要单独报，不许当成干净
====================  ==============================================
"""
from __future__ import annotations

import re
from datetime import date

#: 冻结线。探针题问它**之后**，对照题问它**之前**。
FREEZE_LINE = date(2026, 7, 31)

#: 对照阶梯的三档（规格 §3.3）。三档缺一不可 —— 它们同时给出**实测知识地平线**。
CONTROL_RUNGS: dict[str, tuple[date, date]] = {
    "L1": (date(2025, 12, 1), date(2025, 12, 31)),
    "L2": (date(2026, 3, 1), date(2026, 3, 31)),
    "L3": (date(2026, 6, 1), date(2026, 6, 30)),
}

#: **判卷不经过任何模型。** 改成 False 需要重新签字，测试会拦。
NO_LLM_JUDGE: bool = True

#: 明确弃权的字面量。**必须是穷举的固定表**，不做语义判断。
ABSTAIN_TOKENS: frozenset[str] = frozenset({
    "unknown", "n/a", "na", "不知道", "不清楚", "无法回答", "没有可靠记忆",
})

#: 匹配弃权词之前剥掉的**尾部标点**。纯词法，**不是语义判断** ——
#: 红队 2026-09-05 实测：`"不知道。"` 与 `"n/a。"` 都落进 `unparseable`。
#: **弃权与不可解析是两个结局**：前者是模型说「我不知道」，后者是我们没读懂它。
#: 把弃权算成不可解析，会让实测知识地平线偏向「答不出来」那一侧，
#: 而那正是本卡要量的东西 —— 判卷器的噪声不能进到测量结果里。
ABSTAIN_TRAILING_PUNCT: str = "。．.!！?？,，、;；:： \t"

#: 题类 → (判据模式, 容差)。**容差先定死再出题**（签字要求）。
#:
#: * ``abs``  —— 绝对容差，单位随字段（CPI 同比是「个百分点」）
#: * ``rel``  —— 相对容差
#: * ``exact_date`` / ``exact_set`` / ``exact_int`` —— 无容差
TOLERANCES: dict[str, tuple[str, float]] = {
    "macro_yoy": ("abs", 0.05),          # CPI 同比，0.05 个百分点
    "index_level": ("rel", 0.005),       # 指数点位，0.5%
    "adj_factor_ratio": ("rel", 0.005),  # 除权因子比值，0.5%
    "event_date": ("exact_date", 0.0),   # 除权除息日 / 停牌日
    "code_set": ("exact_set", 0.0),      # 一组标的代码
    "count": ("exact_int", 0.0),         # 计数
}

#: 题类 → 要求的作答格式。判卷器按它解析。
ANSWER_FORMATS: dict[str, str] = {
    "macro_yoy": "NUMBER",
    "index_level": "NUMBER",
    "adj_factor_ratio": "NUMBER",
    "event_date": "DATE",
    "code_set": "CODES",
    "count": "NUMBER",
}

#: 决定「同类同难度」的字段。**只有 `as_of_date` 允许不同**（规格 §3.3）。
ISOMORPHIC_KEYS: tuple[str, ...] = (
    "kind", "source_dataset", "source_field", "template_id", "answer_format",
)

#: 一道题必须有的字段。
REQUIRED_FIELDS: tuple[str, ...] = (
    "id", "kind", "source_dataset", "source_field", "template_id",
    "as_of_date", "arm", "question", "answer_format",
)

_NUM = re.compile(r"^[+-]?\d+(?:\.\d+)?%?$")
_DATE = re.compile(r"^(\d{4})-?(\d{2})-?(\d{2})$")
_CODE = re.compile(r"^\d{6}\.(SH|SZ|BJ)$", re.I)


# ------------------------------------------------------------------ 解析

def _parse_date(s: str) -> date | None:
    m = _DATE.match(s.strip())
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def parse_answer(text: str, fmt: str, *, allow_percent: bool = False):
    """把作答解析成可比对的值。返回 ``("abstain", None)`` / ``("ok", 值)`` / ``("unparseable", None)``。"""
    s = (text or "").strip()
    bare = s.rstrip(ABSTAIN_TRAILING_PUNCT).strip()
    if bare.lower() in ABSTAIN_TOKENS or bare in ABSTAIN_TOKENS:
        return "abstain", None
    if fmt == "NUMBER":
        if not _NUM.match(s):
            return "unparseable", None
        if s.endswith("%") and not allow_percent:
            # 百分号只对「个百分点」那类题有意义（`macro_yoy`）。
            # 一律剥掉的话，`index_level` 上的 `"2.5%"` 会与 `"2.5"` 判成同一个答案 ——
            # 那是把**单位错误**静默改成了正确答案。
            return "unparseable", None
        return "ok", float(s.rstrip("%"))
    if fmt == "DATE":
        d = _parse_date(s)
        return ("ok", d) if d else ("unparseable", None)
    if fmt == "CODES":
        parts = [p.strip().upper() for p in re.split(r"[,\s，、]+", s) if p.strip()]
        if not parts or not all(_CODE.match(p) for p in parts):
            return "unparseable", None
        return "ok", frozenset(parts)
    raise ValueError(f"未知作答格式 {fmt!r}")


# ------------------------------------------------------------------ 判卷

class KeyTypeError(TypeError):
    """答案钥匙的**类型**不对。

    钥匙是**我们**从活湖现取的，不是被测方给的 —— 它错了是我们的 bug，
    必须当场炸，不许表现成模型答错（红队 2026-09-05 实测的三种形态见 `check_key`）。
    """


def check_key(kind: str, key) -> None:
    """钥匙类型检查。**每一条都对应一个实测到的静默错判。**"""
    mode, _ = TOLERANCES[kind]
    if mode in ("abs", "rel"):
        if isinstance(key, bool) or not isinstance(key, (int, float)):
            raise KeyTypeError(
                f"{kind} 的钥匙要数（收到 {type(key).__name__}: {key!r}）—— "
                f"`None`/字符串会让判卷器抛在半路，`True` 会被当成 1")
    elif mode == "exact_int":
        if isinstance(key, bool) or not isinstance(key, int):
            # 实测：`key=3.7` → `int(3.7)=3`，作答 "3" 判 **hit**，说明写着 "3.0 vs 3.7"；
            # `key=True` → `int(True)=1`，作答 "1" 判 **hit**。两种都是静默错判。
            raise KeyTypeError(
                f"{kind} 的钥匙要整数（收到 {type(key).__name__}: {key!r}）—— "
                f"小数会被静默截断、`True` 会被当成 1，两种都判成 hit")
    elif mode == "exact_set":
        if isinstance(key, (str, bytes)) or not hasattr(key, "__iter__"):
            # 实测：`key="600000.SH"` 会**逐字符**迭代成 5 元素集合，
            # 于是这道题**永远 miss**，而说明写的是「1 个 vs 5 个」，看不出是钥匙错了。
            raise KeyTypeError(
                f"{kind} 的钥匙要代码的**集合/列表**（收到 {type(key).__name__}: {key!r}）—— "
                f"裸字符串会被逐字符迭代，这道题从此永远 miss")
    elif mode == "exact_date":
        if not (isinstance(key, date) or _parse_date(str(key))):
            raise KeyTypeError(f"{kind} 的钥匙不是可解析的日期：{key!r}")


def grade_answer(text: str, kind: str, key) -> tuple[str, str]:
    """判一道题。返回 ``(结局, 说明)``，结局 ∈ hit/miss/abstain/unparseable。

    **不经过任何模型。** 全部是格式解析 + 数值比对。
    """
    if not NO_LLM_JUDGE:                                   # pragma: no cover
        raise RuntimeError("NO_LLM_JUDGE 被关掉了 —— 判卷不得引入裁判方差，见模块文档")
    if kind not in TOLERANCES:
        raise KeyError(f"题类 {kind!r} 没有容差定义 —— 容差必须先定死再出题")
    mode, tol = TOLERANCES[kind]
    check_key(kind, key)
    fmt = ANSWER_FORMATS[kind]
    state, val = parse_answer(text, fmt, allow_percent=(mode == "abs"))
    if state == "abstain":
        return state, "明确弃权（在 ABSTAIN_TOKENS 里）"
    if state != "ok":
        return state, f"作答未通过 {fmt} 解析"

    if mode == "abs":
        d = abs(val - float(key))
        return ("hit" if d <= tol else "miss"), f"|Δ|={d:.6g} 容差={tol}（绝对）"
    if mode == "rel":
        k = float(key)
        d = abs(val - k) / abs(k) if k else float("inf")
        return ("hit" if d <= tol else "miss"), f"相对偏差={d:.6g} 容差={tol}"
    if mode == "exact_date":
        want = key if isinstance(key, date) else _parse_date(str(key))
        return ("hit" if val == want else "miss"), f"{val} vs {want}"
    if mode == "exact_set":
        want = frozenset(str(c).upper() for c in key)
        return ("hit" if val == want else "miss"), f"{len(val)} 个 vs {len(want)} 个"
    if mode == "exact_int":
        return ("hit" if float(val).is_integer() and int(val) == int(key) else "miss"), \
               f"{val} vs {key}"
    raise ValueError(f"未知判据模式 {mode!r}")       # pragma: no cover


# ------------------------------------------------------------------ 题集校验

def _as_date(v) -> date | None:
    if isinstance(v, date):
        return v
    s = str(v)
    if re.fullmatch(r"\d{4}-\d{2}", s):              # 月粒度（宏观题）
        y, m = s.split("-")
        return date(int(y), int(m), 1)
    return _parse_date(s)


def validate_probe_set(items: list[dict]) -> list[str]:
    """校验题集。返回违规清单（空 = 通过）。每条以规则号 ``P-n`` 开头。

    负例对照见 `ops/test_memory_probe.py` —— 每条规则都必须**被它自己的负例**拦下，
    只要求「全红」不够（一个负例若因别的规则红，被测的那条其实是空的）。
    """
    bad: list[str] = []

    # ---- P-1 必填字段 ----
    for it in items:
        missing = [f for f in REQUIRED_FIELDS if not str(it.get(f, "")).strip()]
        if missing:
            bad.append(f"P-1 题 {it.get('id', '?')} 缺字段 {missing}")

    # ---- P-2 题类必须有容差与格式定义 ----
    for it in items:
        k = it.get("kind")
        if k not in TOLERANCES or k not in ANSWER_FORMATS:
            bad.append(f"P-2 题 {it.get('id')} 的题类 {k!r} 没有容差/格式定义 —— 容差先定死再出题")
        elif it.get("answer_format") != ANSWER_FORMATS[k]:
            bad.append(f"P-2 题 {it.get('id')} 的作答格式 {it.get('answer_format')!r} "
                       f"与题类 {k!r} 要求的 {ANSWER_FORMATS[k]!r} 不符")

    # ---- P-3 日期落在正确的一侧 ----
    for it in items:
        d = _as_date(it.get("as_of_date"))
        if d is None:
            bad.append(f"P-3 题 {it.get('id')} 的 as_of_date 解析不了：{it.get('as_of_date')!r}")
            continue
        if it.get("arm") == "probe" and d <= FREEZE_LINE:
            bad.append(f"P-3 探针题 {it.get('id')} 的日期 {d} 不在冻结线之后")
        if it.get("arm") == "control":
            rung = it.get("rung")
            if rung not in CONTROL_RUNGS:
                bad.append(f"P-3 对照题 {it.get('id')} 的档位 {rung!r} 不在 {sorted(CONTROL_RUNGS)}")
            else:
                lo, hi = CONTROL_RUNGS[rung]
                if not (lo <= d <= hi):
                    bad.append(f"P-3 对照题 {it.get('id')} 的日期 {d} 不在 {rung} 档 [{lo}, {hi}] 内")

    # ---- P-4 每道探针题都要有三道**结构同构**的对照题 ----
    def sig(it):
        return tuple(it.get(k) for k in ISOMORPHIC_KEYS)

    controls: dict[tuple, list[dict]] = {}
    for it in items:
        if it.get("arm") == "control":
            controls.setdefault(sig(it), []).append(it)
    for it in items:
        if it.get("arm") != "probe":
            continue
        group = controls.get(sig(it), [])
        rungs = sorted(str(c.get("rung")) for c in group)
        if rungs != sorted(CONTROL_RUNGS):
            bad.append(
                f"P-4 探针题 {it.get('id')} 的同构对照题档位是 {rungs or '（一道都没有）'}，"
                f"要求恰好 {sorted(CONTROL_RUNGS)}；同构判据 = "
                f"{dict(zip(ISOMORPHIC_KEYS, sig(it)))}（**只有日期允许不同**）")

    # ---- P-5 题面不得泄漏答案 ----
    for it in items:
        key = it.get("key")
        q = str(it.get("question", ""))
        if key is not None and str(key) and str(key) in q:
            bad.append(f"P-5 题 {it.get('id')} 的题面里出现了答案 {key!r}")
        for w in ("调入", "调出", "上涨", "下跌", "创新高", "创新低"):
            if w in q:
                bad.append(f"P-5 题 {it.get('id')} 的题面含泄漏结论的措辞 {w!r} —— "
                           f"要用开放问法，不能让人从题面反推出发生了什么")

    # ---- P-6 题面必须写明作答格式，否则判卷没法程序化 ----
    for it in items:
        if str(it.get("answer_format", "")) not in str(it.get("question", "")):
            bad.append(f"P-6 题 {it.get('id')} 的题面没写明作答格式 "
                       f"{it.get('answer_format')!r} —— 程序化判卷的前提是输出可解析")

    # ---- P-7 id 唯一 ----
    seen: set[str] = set()
    for it in items:
        i = str(it.get("id"))
        if i in seen:
            bad.append(f"P-7 题号重复：{i}")
        seen.add(i)
    return bad


# ------------------------------------------------------------------ 汇总

CONTROL_RATE_FLOOR = 0.5     # L3 通过率低于它 → 整组 inconclusive


def summarize(graded: list[dict]) -> dict:
    """把逐题结局汇总成主表要的几个数。

    ``graded`` 的每一项：``{"arm","rung","outcome"}``。
    """
    def rate(sel) -> float | None:
        xs = [g for g in graded if sel(g) and g["outcome"] != "unparseable"]
        return round(sum(g["outcome"] == "hit" for g in xs) / len(xs), 4) if xs else None

    per_rung = {r: rate(lambda g, r=r: g["arm"] == "control" and g["rung"] == r)
                for r in CONTROL_RUNGS}
    horizon = None
    for r in sorted(CONTROL_RUNGS):                       # L1 → L2 → L3
        v = per_rung.get(r)
        if v is not None and v >= CONTROL_RATE_FLOOR:
            horizon = r
    l3 = per_rung.get("L3")
    hit = rate(lambda g: g["arm"] == "probe")

    # ---- unparseable 的**不对称**是信号，不能平均掉（2026-09-01 签字补充）----
    # 一个配置在冻结线前的对照题上正常作答、到冻结线后的目标题突然大量 unparseable，
    # 可能是规避，也可能是安全策略触发 —— 两种都值得看见，所以按臂分开报，
    # 并给一个**无阈值**的形态标签（阈值不许拍；数字本身一起报，读者自己判）。
    def unp_rate(arm) -> float | None:
        xs = [g for g in graded if g["arm"] == arm]
        return round(sum(g["outcome"] == "unparseable" for g in xs) / len(xs), 4) if xs else None
    unp_p, unp_c = unp_rate("probe"), unp_rate("control")
    if unp_p is None or unp_c is None:
        pattern = "n/a"
    elif unp_p > 0 and unp_c == 0:
        pattern = "probe_only"          # **最值得看的形态**：只在冻结线后不作答
    elif unp_p == 0 and unp_c > 0:
        pattern = "control_only"
    elif unp_p > 0 and unp_c > 0:
        pattern = "both"
    else:
        pattern = "none"

    return {
        "memory_probe_hit_rate": hit,
        "memory_probe_control_rate": l3,
        "memory_probe_horizon": horizon,
        "control_rate_by_rung": per_rung,
        "unparseable": sum(g["outcome"] == "unparseable" for g in graded),
        "abstain": sum(g["outcome"] == "abstain" for g in graded),
        "unparseable_rate_probe": unp_p,
        "unparseable_rate_control": unp_c,
        "unparseable_asymmetry": (None if unp_p is None or unp_c is None
                                  else round(unp_p - unp_c, 4)),
        "unparseable_pattern": pattern,
        # 控制组不达标时，探针结果**不是 clean，是 inconclusive**
        "validity": ("inconclusive" if (l3 is None or l3 < CONTROL_RATE_FLOOR)
                     else ("contaminated" if (hit or 0) > 0 else "clean")),
    }


# ------------------------------------------------------------------ 答案隔离

#: 答案字段名。**这一个字段就是红线 5 的第三类保护对象**（前两类是
#: `reference/` 的 gold 产物与 `scorer/` 的评分代码）。
KEY_FIELD = "key"


def assert_export_is_key_free(items: list[dict]) -> None:
    """导出到执行面的题面里**不得**出现答案字段。

    与 `reference/`、`scorer/` 同级：**记忆探针的答案集永不进执行面、
    永不进任何 agent 可达路径**（2026-09-01 签字，红线 5 第三类）。

    这一类的泄漏后果与前两类**不同**：泄漏一次 gold 因子值，坏的是那一道题；
    泄漏一次探针答案，**这套探针就永久失效了，而且是静默失效** ——
    之后的命中率上升会被读成「污染变严重」，实际是题目泄漏。
    """
    leaky = [str(it.get("id")) for it in items if KEY_FIELD in it]
    if leaky:
        raise RuntimeError(
            f"{len(leaky)} 道题的导出体里带着答案字段 {KEY_FIELD!r}：{leaky[:5]} —— "
            f"红线 5 第三类：探针答案集永不进执行面。导出前必须剥掉。")


def strip_keys(items: list[dict]) -> list[dict]:
    """产出可以进执行面的题面（剥掉答案字段）。"""
    return [{k: v for k, v in it.items() if k != KEY_FIELD} for it in items]
