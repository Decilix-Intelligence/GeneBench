# -*- coding: utf-8 -*-
"""代码别名表（M1 收尾指令 2②）。

收录对账 §4.10 自动识别出的 `ts_code` 映射对。**状态一律 `auto_inferred_pending_confirmation`**
—— 判据只有"分歧日集合 Jaccard ≥ 50% + 一源独有"，**没有**工商变更或交易所公告佐证。

**用途边界（M1 签字裁定）**：

- ✅ 对账：解释两源为什么在同一实体上用了不同的码；
- ✅ 后续适配赛道：跨源数据拼接时的候选映射；
- ❌ **不进 `universe_pit` 本体** —— 宇宙表继续用湖的**当前码**口径。
  理由：把未经确认的映射写进宇宙定义，等于让一个自动推断决定"这只票在不在成分里"，
  而这恰恰是 benchmark 要考的东西。

要把某一对升级成已确认，改 `status` 并在 `evidence` 里写上公告出处 —— 
`ops/test_code_alias.py` 有一条测试盯着"没有 evidence 的不许标成 confirmed"。
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

import genebench_config as cfg

#: 产物落点。与宇宙产物同目录，但**是独立文件** —— 不混进 universe_pit。
ALIAS_PARQUET: Path = cfg.UNIVERSE_DIR / "code_alias.parquet"
ALIAS_JSON: Path = cfg.OPS / "code_alias.json"

#: 状态枚举。`auto_inferred_pending_confirmation` 是唯一允许自动写入的值。
STATUSES: tuple[str, ...] = (
    "auto_inferred_pending_confirmation",
    "confirmed",
    "rejected",
)

#: 允许的用途。写进产物，让下游一眼看到边界。
ALLOWED_USES: tuple[str, ...] = ("reconciliation", "adaptation_track")
FORBIDDEN_USES: tuple[str, ...] = ("universe_pit", "task_generation", "scoring")


@dataclass
class Alias:
    universe: str
    code_a: str          # 湖/源A 侧的码（universe_pit 本体用的就是这个）
    code_b: str          # 源B(qlib) 侧的码
    day_set_jaccard: float
    span_start: str
    span_end: str
    n_disagreement_td: int
    status: str = "auto_inferred_pending_confirmation"
    evidence: str = ""   # 升级成 confirmed 必须填：公告/工商变更出处
    note: str = ""

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"status={self.status!r} 不认识；只接受 {STATUSES}")
        if self.status == "confirmed" and not self.evidence.strip():
            raise ValueError(
                f"{self.code_a}↔{self.code_b} 标成 confirmed 但 evidence 是空的。"
                f"自动推断不能自己把自己升级 —— 要有公告出处。"
            )


def from_reconciliation(path: Path | None = None) -> list[Alias]:
    """从对账产物的 `code_mapping_pairs` 生成。"""
    target = path or (cfg.OPS / "universe_reconciliation.json")
    data = json.loads(target.read_text(encoding="utf-8"))
    pairs = data.get("code_mapping_pairs") or []
    out: list[Alias] = []
    for p in pairs:
        # 只在源B 出现的码 = qlib 侧的码；另一侧是湖的当前码
        b_side = p["only_in_source"] == "B"
        code_b = p["code_only_in_that_source"] if b_side else p["counterpart_code_in_other_source"]
        code_a = p["counterpart_code_in_other_source"] if b_side else p["code_only_in_that_source"]
        out.append(
            Alias(
                universe=p["universe"],
                code_a=code_a,
                code_b=code_b,
                day_set_jaccard=float(p["day_set_jaccard"]),
                span_start=p["disagreement_span"][0],
                span_end=p["disagreement_span"][1],
                n_disagreement_td=int(p["n_disagreement_td"]),
                note="对账 §4.10 自动推断；判据仅 Jaccard>=0.5 + 一源独有，无公告佐证",
            )
        )
    return sorted(out, key=lambda a: (a.universe, a.code_a, a.code_b))


def build() -> tuple[pd.DataFrame, dict[str, Any]]:
    cfg.harden_umask()
    aliases = from_reconciliation()
    frame = pd.DataFrame([asdict(a) for a in aliases])
    cfg.create_dir(cfg.UNIVERSE_DIR)
    frame.to_parquet(ALIAS_PARQUET, index=False)
    ALIAS_PARQUET.chmod(0o600)
    summary: dict[str, Any] = {
        "card": "1.1-followup-code-alias",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "n_pairs": len(aliases),
        "by_status": frame["status"].value_counts().to_dict() if len(frame) else {},
        "allowed_uses": list(ALLOWED_USES),
        "forbidden_uses": list(FORBIDDEN_USES),
        "caveat": (
            "全部为自动推断，未经公告确认。**不进 universe_pit 本体**——"
            "宇宙表继续用湖的当前码口径（M1 签字裁定）。"
        ),
        "pairs": [asdict(a) for a in aliases],
    }
    ALIAS_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    ALIAS_JSON.chmod(0o600)
    return frame, summary


def read() -> pd.DataFrame:
    if not ALIAS_PARQUET.exists():
        raise FileNotFoundError(f"没有 {ALIAS_PARQUET}；先跑 python -m snapshots.code_alias")
    return pd.read_parquet(ALIAS_PARQUET)


def main() -> int:
    frame, summary = build()
    print(f"{summary['n_pairs']} 对别名 → {ALIAS_PARQUET}")
    for _, r in frame.iterrows():
        print(f"  {r['universe']:8s} {r['code_a']} ↔ {r['code_b']}  "
              f"J={r['day_set_jaccard']:.4f}  {r['span_start']}..{r['span_end']}  "
              f"{r['n_disagreement_td']} td  [{r['status']}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
