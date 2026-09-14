# -*- coding: utf-8 -*-
"""受算子语义冲突影响的因子集合 —— **下游要用的是这里，不是那份 .md**。

    cd $REPO && $GENEBENCH_ROOT/env/bin/python -m reference.operator_flags

签字裁定（N-21 走 C）落地成两个集合，各有各的用途：

* :data:`GOLD_SUSPECT` —— KunQuant 侧用到 ``ts_rank`` 的因子。它们的 **gold 值**
  依赖一个**未被因子定义绑定**的归一化约定，标注为「算子约定存疑」。
  **S3 出题必须避开**（`tasks_should_avoid()`）。
* :data:`TAU_EXCLUDED` —— 可比因子里源方言使用 ``Ts_Rank`` 的。移出 τ 样本。

**两个集合不相等，也不该相等**：排除规则定在「语义未绑定」而不是「观察到分歧」。
`qlib_expression` 侧的 4 条实测 ρ ≈ 1.0（qlib 的 `Rank` 与面板求值器碰巧都用 pct），
但**一致是巧合不是约定** —— 按「观察到分歧才排除」会让 τ 随巧合变松，所以照样排除。

论证与逐条证据见 ``ops/specs/operator_semantics_conflicts.md``（由
``ops/mk_operator_conflicts.py`` 生成）。
"""
from __future__ import annotations

import inspect
import json
import re
from pathlib import Path
from typing import Any

import genebench_config as cfg
from reference import factor_exec as fx

#: 落在快照里，与 gold 同目录 —— 谁读 gold 谁就看得见这份标注。
SIDECAR: Path = fx.GOLD_DIR / "operator_convention_suspect.json"

#: 触发标注的算子。v1 只有这一个；日后若再查出同类，加进来并重新生成。
CONFLICT_OPS: tuple[str, ...] = ("ts_rank",)

#: **参考实现缺陷** —— 与算子约定分歧是两回事，必须分开。
#:
#: * 约定分歧（`gold_suspect`）：两个引擎**都没错**，错的是「同名即同义」这个假设。
#:   `ts_rank` 在一边归一化到 `(0,1]`、在另一边返回原位次序 `[1,w]`，
#:   两种都是对 `Ts_Rank` 的合法读法，因为因子定义没绑定值域。
#: * **实现缺陷**（本集合）：一方**读错了输入字段**，与约定无关，就是错。
#:
#: `worldquant_101.038`：源方言写 `Ts_Rank(close, 10)`，
#: KunQuant 的 `alpha038` 写 `ts_rank(self.open, 10)` —— **close 被写成了 open**。
#: 它在 gold 里算得出数、跑得通、数值看起来正常，只有双实现互检把它照出来
#: （实测 mean ρ = +0.8955，而形式分析预测应当 ρ ≈ 1）。
#:
#: 处置比「存疑」更重：**从 τ 样本与 gold 可用集一并排除**。修 KunQuant 侧登记 N-24 待评估。
DEFECTIVE: dict[str, str] = {
    "worldquant_101.038": (
        "KunQuant 的 alpha038 在 ts_rank 的实参上用了 open，"
        "而源方言公式写的是 close —— 字段错位，与归一化约定无关。"
    ),
}

_TS = re.compile(r"\bTS[_]?RANK\b", re.I)

__all__ = ["gold_suspect", "tau_excluded", "tasks_should_avoid", "SIDECAR", "build"]


def _kunquant_source(rec: dict[str, Any]) -> str:
    import KunQuant.predefined.Alpha101 as A

    fn = getattr(A, str(rec["compiled_expression"]).rsplit(".", 1)[-1], None)
    return inspect.getsource(fn) if fn else ""


def gold_suspect(recs: "list[dict] | None" = None) -> list[str]:
    """gold 值依赖**未绑定算子约定**的因子（KunQuant 侧用了 ``ts_rank``）。

    **不含** :data:`DEFECTIVE` —— 那是另一类问题，处置也不同（见 :func:`gold_defective`）。
    """
    recs = recs or fx.load_records()[0]
    out = []
    for r in recs:
        if r.get("executable") and r["execution_backend"] == "qlib_kunquant_loader":
            if any(re.search(rf"\b{op}\b", _kunquant_source(r), re.I) for op in CONFLICT_OPS):
                out.append(r["id"])
    return sorted(set(out) - set(DEFECTIVE))


def gold_defective() -> dict[str, str]:
    """参考实现有缺陷的因子 → **gold 不可用**，不是「存疑」。"""
    return dict(DEFECTIVE)


def gold_unusable() -> frozenset[str]:
    """gold 可用集之外的因子。评分与出题都不许用它们的 gold 值。"""
    return frozenset(DEFECTIVE)


def tau_excluded(comparable: list[str], recs: "list[dict] | None" = None) -> list[str]:
    """可比因子里源方言使用 ``Ts_Rank`` 的 —— 移出 τ 样本。"""
    recs = recs or fx.load_records()[0]
    by = {r["id"]: r for r in recs}
    return sorted(set(i for i in comparable if _TS.search(str(by[i]["expression"])))
                  | (set(DEFECTIVE) & set(comparable)))


def tasks_should_avoid() -> frozenset[str]:
    """S3 出题要避开的因子。**卡 3.2 的题源生成器必须调这个，不要自己抄名单。**"""
    if SIDECAR.exists():
        return frozenset(json.loads(SIDECAR.read_text(encoding="utf-8"))["gold_suspect"])
    return frozenset(gold_suspect())


def build(comparable: "list[str] | None" = None, *, verbose: bool = True) -> dict[str, Any]:
    recs, _ = fx.load_records()
    if comparable is None:
        rep = json.loads((cfg.OPS / "acceptance" / "card_2.1b_crosscheck.json")
                         .read_text(encoding="utf-8"))
        comparable = [x["id"] for x in rep["rows"]]
    gs = gold_suspect(recs)
    te = tau_excluded(comparable, recs)
    payload = {
        "decision": "N-21 → C（签字人 2026-09-01）",
        "why": ("GeneQuant 协议规定算子语义须绑定在因子定义上、不得由任何一方隐式补全。"
                "评测方替因子库拍板一种归一化，等于自己犯了被测方要被判违例的错误。"),
        "conflict_ops": list(CONFLICT_OPS),
        "gold_suspect": gs,
        "gold_suspect_n": len(gs),
        "gold_suspect_meaning": ("这些因子的 gold 值依赖 KunQuant 的原位 ts_rank 约定，"
                                 "而因子定义没有绑定该算子的值域。**S3 出题必须避开。**"),
        "tau_excluded": te,
        "tau_excluded_n": len(te),
        "tau_excluded_meaning": "移出 τ 样本；规则定在「语义未绑定」而非「观察到分歧」。",
        "overlap": sorted(set(gs) & set(te)),
        "defective": DEFECTIVE,
        "defective_n": len(DEFECTIVE),
        "defective_meaning": ("参考实现读错了输入字段 —— 与算子约定无关，就是错。"
                              "**从 τ 样本与 gold 可用集一并排除**（比「存疑」更重）。"
                              "修 KunQuant 侧登记 N-24 待评估。"),
        "gold_unusable": sorted(DEFECTIVE),
        "two_classes": ("同一个因子名在两个成熟实现之间，既可能因**约定不同**而值域不同"
                        "（两边都没错），也可能因**实现错误**而输入字段都不同（一边错了）。"
                        "**两者在产物层面表现完全一样**：能算出数、能跑通、数值看起来正常。"),
        "evidence": "ops/specs/operator_semantics_conflicts.md",
    }
    cfg.create_dir(SIDECAR.parent)
    SIDECAR.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    SIDECAR.chmod(0o600)
    if verbose:
        print(f"gold 约定存疑 {len(gs)} 条 · gold 不可用(缺陷) {len(DEFECTIVE)} 条 · "
              f"τ 排除 {len(te)} 条 · 交集 {len(payload['overlap'])} 条")
        print(f"→ {SIDECAR}")
    return payload


if __name__ == "__main__":
    build()
