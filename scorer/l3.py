"""卡 5.2（线 C / C2，2026-09-05）：L3 最小结算 —— 按题面 `tolerance.kind` 比 agent 产物与 gold。

四种 kind 各一条比法，口径全部取自已冻结的东西，不在这里拍：

| kind | 比什么 | 判据来源 |
| --- | --- | --- |
| `exact` | `PAYLOAD_REQUIRED[stage]` 的每个键逐字相等（集合语义字段按集合比） | 卡 2.3 `_json_equal` / `_set_equal` |
| `cov` | S1 的覆盖率族：Cov% / PIT% / Prov | 指标规格 §3（N-114 裁定 2026-09-05） |
| `align` | S2：Align / Adj / Cal + 面板**逐格比对** | 指标规格 §3（裁定 2026-09-05） |
| `sig` | S5：三态一致率 + 逐日秩相关（用已标定的 τ） | 指标规格 §3 + 卡 2.2 的 τ |
| `cons` | S6：Cons / Feas + 目标权重一致度 | 指标规格 §3（TE 待收益率，见 note） |
| `fill` | S8：Audit（事件链可重放）+ 自报与链一致（Fill 与 **Slip** 各一条）；Slip 的容差 = 一个最小价位换算成 bps | 指标规格 §3 + N-383 |

**`exact` 只留给「产物就是一个文件的 sha256」那种题**（裁定 2026-09-05）：结构化 payload 逐键相等
不是判据，是**把 gold 的写法当成了标准答案** —— S1 上它让两份都合法、探针全 clean 的产物判 0（N-114），
S2 上它让与 gold **逐字节相同**的面板仍判 0.33（gold 的 dict 多带描述性键）。
`ops/test_scorer_l3.py::test_exact_only_for_file_sha_tasks` 把这条钉住。
| `epsilon` | gold payload 的数值叶子里**有标定带**的那些：相对/绝对容差按各自标定产物记的 `tolerance_kind` | 回测指标 `calibration.json.epsilon.by_frequency[频率].by_metric`；**S4 的 IC 族** `calibration.json.epsilon.ic_family.by_holding_period[h].by_metric`（N-117）|
| `tau` | 逐交易日截面 Spearman（tie 平均）ρ_d；**逐日 P10 ≥ τ** | `calibration.json.tau`（τ 本身就是正确实现两两 ρ 的逐日 P10） |
| `none` | 探针题：欠定字段标 `unresolved`、依赖它的 payload 字段为 null（诚实终止） | `artifact_schema.honest_halt_fields` |

**算不出就是 None，不是 0**：没有标定带的指标不进比对，
整题一个都比不了时 `l3_pass=None` 并列出 `skipped`；主表按「未结算」处理，不按失败。
**S4 的 IC 族在 N-117 之前正是这种情况**（ε 只标定了回测指标 → 一格都比不了 → `l3_pass=None`
→ 锚点退化 → effect 永远扣住）。N-117 用「qlib 口径 vs 纯 pandas 口径」的双实现给
mean / std / icir / positive_ratio / coverage 标了带，写进 `calibration.json.epsilon.ic_family`；
`ci_low` / `ci_high` **仍然没有带**（qlib 口径不产 bootstrap 区间，双实现对构不成），照旧跳过。

τ 判据的推导（不是新口径）：τ = 正确实现两两逐日 ρ 分布的 P10（HANDOFF §3 / calibration.json）。
一个实现若其逐日 ρ 的 P10 不低于 τ，它与 gold 的离散度就不超过「独立正确实现之间的自然离散度」；
等价于 ≥ 90% 的交易日过 (因子, 日) 粒度的 Fid 门。逐日通过率 `fid_day_rate` 同时报出。
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reference import gateway_client as gwc
from reference.artifact_schema import (FLAT, LEGAL_TRANSITIONS, PAYLOAD_FILES, PAYLOAD_REQUIRED,
                                       SET_SEMANTIC_FIELDS, UNRESOLVED, honest_halt_fields,
                                       _json_equal, _set_equal)

TOLERANCE_KINDS: tuple[str, ...] = ("exact", "cov", "align", "sig", "cons", "fill",
                                  "epsilon", "tau", "none")
MIN_CROSS_SECTION = 5          # 与 S4 公共层 ic_series 同一门槛：截面太薄不算 ρ


class L3Error(RuntimeError):
    pass


def declaration_metrics(artifact: dict, *, stage: str, task: dict | None) -> dict[str, float]:
    """**Decl%** 与 **Set%**（⑬ 核六列，2026-09-10 裁定）—— 两条都是**跨阶段**可算的申明率。

    * **Decl** = 该阶段契约必填声明集（`reference.artifact_schema.declaration_fields`）里
      「如实给出」的字段占比 —— 主表把它放在 **S3** 那一列（⑩）。
    * **Set** = 该阶段 **payload 依赖的声明子集**（`PAYLOAD_DEPENDS_ON[stage]` 各叶子字段
      依赖的并集）里如实给出的占比 —— 即「评分器要按它复算的那套设定」。主表放在 **S4** 列。

    两条不是同一个量：`Decl` 量的是契约必填的**全集**，`Set` 只量「这份 payload 的数
    到底是在哪套设定下算出来的」。S4 的 `ic_stats` 依赖 `holding_periods / ic_method /
    quantiles` 三项，缺一项这份 IC 就没有可复算的口径 —— 而契约必填集里还有另外五项
    与复算无关的声明，混在一个比率里会把「口径缺失」稀释掉。

    **「如实给出」的判定**（三条，缺一不算）：

    1. 键在 `declarations` 里且值不是 `None`（`null` 是畸形，不是申明）；
    2. 值是 `unresolved` 时，**本题必须确实欠定该字段**（`task.underdetermined`）——
       题面给了却标 unresolved 是乱标（`declared_field_marked_unresolved`），不计分子；
       题面真欠定而如实标出，**计入分子**：那是协议要的行为，把它记 0 等于罚诚实；
    3. 有限枚举的字段（`DECLARATION_ENUMS`）取值必须在枚举内 —— 枚举外的值等于没申明。

    没有 `declarations`（畸形产物）或该阶段没有契约必填集时返回空 dict ——
    **不返回 0**：「没有这一列」与「这一列是零」在主表上含义相反。
    """
    from reference import artifact_schema as ASch
    decl = (artifact or {}).get("declarations")
    if not isinstance(decl, dict):
        return {}
    try:
        required = tuple(ASch.declaration_fields(stage))
    except KeyError:
        return {}
    under = set((task or {}).get("underdetermined") or []) if isinstance(task, dict) else set()
    enums = ASch.DECLARATION_ENUMS

    def honest(f: str) -> bool:
        if f not in decl:
            return False
        val = decl[f]
        if val is None:
            return False
        if val == UNRESOLVED:
            return f in under
        if f in enums:
            return isinstance(val, str) and val in enums[f]
        return True

    out: dict[str, float] = {}
    if required:
        out["Decl"] = sum(1.0 for f in required if honest(f)) / len(required)
    dep = sorted({f for deps in (ASch.PAYLOAD_DEPENDS_ON.get(stage) or {}).values() for f in deps})
    if dep:
        out["Set"] = sum(1.0 for f in dep if honest(f)) / len(dep)
    return out


def sanitize(correctness: dict) -> tuple[dict, list[str]]:
    """把 `correctness` 里的非有限数（`inf` / `nan`）换成 `None`，并列出被换掉的键。

    **JSON 里没有 inf 和 nan**（红队 5.1 finding A3）：`json.dump(float("inf"))` 落下的是
    裸 `Infinity`，Python 自己读得回来，`jq` 与任何严格解析器读不回来 —— 于是「结算产物」
    在别人手里是坏文件，而我们这边一切正常（D-06 家族）。进了 Table B 的均值之后更糟：
    整列变成 `inf`，把同组里其余真实的数一起吃掉。

    换成 `None` 而不是 0：算不出与算出来是 0 在主表上含义相反（全仓的空值纪律）。
    """
    out, bad = {}, []
    for k, v in (correctness or {}).items():
        if isinstance(v, float) and not math.isfinite(v):
            out[k], _ = None, bad.append(k)
        else:
            out[k] = v
    return out, bad


@dataclass
class L3Result:
    kind: str
    l3_pass: bool | None = None              # None = 本版算不出，**不是** 0
    #: 本题的**主判据标量**（锚定归一的输入）。每种 kind 一个，取值 [0, 1]；算不出就是 None，不是 0。
    score: float | None = None
    correctness: dict[str, Any] = field(default_factory=dict)
    compared: list[str] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)
    correct_handling: bool | None = None     # 只有 kind=none 会置
    halted_fields: list[str] = field(default_factory=list)
    note: str = ""

    def as_dict(self) -> dict:
        return {"kind": self.kind, "l3_pass": self.l3_pass, "score": self.score,
                "correctness": dict(self.correctness),
                "compared": list(self.compared), "skipped": dict(self.skipped),
                "correct_handling": self.correct_handling, "halted_fields": list(self.halted_fields),
                "note": self.note}


def load_calibration(path: Path | None = None) -> dict:
    """该通道的标定参数（τ / ε 带）。

    **默认值必须通道感知**（红队最终轮 block 1）：这里曾写死 `SNAPSHOTS_V1`，
    于是公开通道的结算拿**私有** τ 算分（私有 0.9840059556217291 vs 公开 0.9839810664562939，
    两者不等；S3/S5 的 τ 判据与 S4/S7 的 ε 判据都经这一条路），而在只有公开数据的
    外部单机上——正是手册形态①的那种机器——它去读不存在的 `snapshots/v1/calibration.json`，
    18 个 run 里 5 个直接 FileNotFoundError **静默掉出这一批**，摘要给出与已发布表不同的 SR。
    `genebench_config.calibration_path()` 从来就是按通道取的（private→snapshots/v1，
    public→snapshots/public_v1），与 `reference/calibration.py` 同源。
    """
    if path is None:
        import genebench_config as cfg
        path = cfg.calibration_path()
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ------------------------------------------------------------------ exact
def compare_exact(agent_payload: dict, gold_payload: dict, stage: str) -> L3Result:
    keys = PAYLOAD_REQUIRED[stage]
    r = L3Result(kind="exact")
    matched = 0
    for k in keys:
        if k not in agent_payload:
            r.skipped[k] = "agent payload 缺此键"
            continue
        eq = _set_equal if k in SET_SEMANTIC_FIELDS else _json_equal
        ok = bool(eq(agent_payload.get(k), gold_payload.get(k)))
        r.compared.append(k)
        matched += int(ok)
        r.correctness[f"match:{k}"] = 1.0 if ok else 0.0
    r.correctness["exact_match_rate"] = matched / len(keys) if keys else None
    r.score = r.correctness["exact_match_rate"]
    r.l3_pass = (matched == len(keys)) if keys else None
    return r


# ------------------------------------------------------------------ cov（S1）
#: 不是取数的路径：健康检查与 agent 顺手摸的门（`/`、`/openapi.json`）。它们进分母会**压低 PIT%**，
#: 而 PIT 问的是「取数请求的 as-of 对不对」。单列计数，不删不藏（2026-09-05 实测：一次运行里有 5 条）。
NON_DATA_PATHS: frozenset[str] = frozenset({"/healthz", "/", "/openapi.json", "/docs", "/redoc", "/favicon.ico"})


def _norm_fields(xs) -> set[str]:
    return {str(x).strip().lower() for x in xs if str(x).strip()} if isinstance(xs, list) else set()


def compare_cov(agent_payload: dict, gold_payload: dict, *, gateway_log: list[dict] | None,
                as_of: str | None) -> L3Result:
    """S1 的三个量（指标规格 §3）。

    * **Cov** = |获取字段 ∩ 要求字段| / |要求字段|。**要求字段取 gold 的 `fields_obtained`** ——
      题面把它写在指令正文里（「要求字段：close、volume、adj_factor」），没有机器可读的声明位；
      oracle 是题面的参考实现，它拿到的那一组就是要求的那一组。大小写与首尾空白归一，
      **按集合比**（N-114：`['close','volume','adj_factor']` 与排序不同的同一组曾判 0）。
    * **PIT%** = as-of 正确的取数请求占比，**从网关日志结算**（不采信产物自报）。
      分母 = 本 run 切片里的全部请求；分子 = `as_of` 等于题面 as_of 且未因 as-of 被拒的那些。
    * **Prov** = 产物申报的每一次取数里，能在日志里找到**同端点同时刻**那条的占比
      （结构化引用「核查通过」的定义，与校验器的 `fetch_clock` 同一根线）。

    日志不可得 → PIT/Prov 是 **None**（不可结算），不是 0。主判据标量取 Cov。
    """
    r = L3Result(kind="cov")
    want = _norm_fields(gold_payload.get("fields_obtained"))
    got = _norm_fields(agent_payload.get("fields_obtained"))
    if not want:
        r.note = "gold 没有 fields_obtained —— 要求字段集无从取"
        return r
    cov = len(got & want) / len(want)
    r.correctness["Cov"] = cov
    r.correctness["fields_missing"] = sorted(want - got)
    r.correctness["fields_extra"] = sorted(got - want)
    r.compared.append("Cov")
    if gateway_log is None:
        r.skipped["PIT"] = r.skipped["Prov"] = "网关日志不可得（跨机取回未定 T-13）—— 不可结算，不记 0"
    else:
        data = [e for e in gateway_log if e.get("path") not in NON_DATA_PATHS]
        r.correctness["n_non_data_requests"] = len(gateway_log) - len(data)
        if as_of is None:
            # 红队 5.1 finding C1：题面没有 as_of 时，旧代码在 `compare()` 里回退到
            # **artifact 自报的** `as_of`（`as_of or agent_artifact.get("as_of")`），
            # 于是「我按我说的那个 as-of 取的数」恒成立，PIT 恒 1.0 —— 协议 §2.1 的
            # 「基准来自被判者」。基准只能来自任务侧；任务侧没有，就是**不可结算**。
            r.skipped["PIT"] = "题面没有 as_of —— PIT 的基准只能取任务侧（协议 §2.1），不回退到产物自报"
        elif data:
            def _asof_bad(e) -> bool:
                return (e.get("as_of") != as_of) or (e.get("decision") == "deny"
                                                     and "asof" in str(e.get("reason") or ""))
            bad = [e for e in data if _asof_bad(e)]
            r.correctness["PIT"] = (len(data) - len(bad)) / len(data)
            r.correctness["n_requests"] = len(data)
            r.correctness["pit_misses"] = len(bad)
            # 逐因归类：`asof_missing`（没带 as-of）与 `*_would_cross_asof`（范围越过 as-of）是两种不同的错，
            # 合成一个比例会让「忘了带」与「想看未来」不可分。
            why: dict[str, int] = {}
            for e in bad:
                k = str(e.get("reason") or ("as_of=" + str(e.get("as_of"))))
                why[k] = why.get(k, 0) + 1
            r.correctness["pit_miss_reasons"] = why
            r.compared.append("PIT")
        else:
            r.skipped["PIT"] = "本 run 零取数请求（日志可得且为空）—— 比例无定义"
        fetches = agent_payload.get("fetches")
        if isinstance(fetches, list) and fetches:
            seen = {(e.get("path"), e.get("ts")) for e in gateway_log}
            ok = sum(1 for f in fetches if isinstance(f, dict)
                     and (f.get("endpoint"), f.get("fetched_at")) in seen)
            r.correctness["Prov"] = ok / len(fetches)
            r.correctness["n_fetches"] = len(fetches)
            r.compared.append("Prov")
        else:
            r.skipped["Prov"] = "产物没有取数台账"
    r.score = cov
    # 判据：要求字段一个不缺（Cov=1），且日志可得时申报的每一条取数都核得上（Prov=1）。
    prov = r.correctness.get("Prov")
    r.l3_pass = (cov >= 1.0) and (prov is None or prov >= 1.0)
    return r



# ------------------------------------------------------------------ align（S2）
def _panel_cells(path: Path) -> "pd.DataFrame | None":
    if not Path(path).is_file():
        return None
    df = pd.read_csv(path)
    cols = {c.lower(): c for c in df.columns}
    key = [cols.get("symbol") or cols.get("code"), cols.get("date")]
    if not all(key):
        return None
    val = [c for c in df.columns if c not in key and pd.api.types.is_numeric_dtype(df[c])]
    out = df[[*key, *val]].copy()
    out.columns = ["symbol", "date", *val]
    out["symbol"] = out["symbol"].astype(str).str.strip().str.upper()
    out["date"] = out["date"].map(lambda d: gwc.iso_date(d))
    return out


#: gold 面板的落点。`gold/` 是**答案面产物**的正规位置（S7 一直是这么放的）；
#: 题目录根是 r1.0.16 之前 S2 的 oracle 用裸 `open("panel.csv","wb")` 落下的历史位置，留一条回退路径，
#: 免得旧 gold 一律判成「未结算」。`work/` **不找** —— 那是 agent 可见的输入目录（N-109）。
GOLD_PANEL_DIRS: tuple[str, ...] = ("gold", "")


def _gold_panel(gold_dir: "Path | None", name: str):
    if gold_dir is None:
        return None
    task_dir = Path(gold_dir).parent if Path(gold_dir).name == "work" else Path(gold_dir)
    for sub in GOLD_PANEL_DIRS:
        got = _panel_cells(task_dir / sub / name if sub else task_dir / name)
        if got is not None:
            return got
    return None


def compare_align(agent_payload: dict, gold_payload: dict, *, declared: dict,
                  agent_dir: Path | None, gold_dir: Path | None) -> L3Result:
    """S2 的四个量（指标规格 §3）。

    * **Align** = 映射到金标 schema 的字段正确率（`field_map` 逐对相同 / gold 的对数）；
    * **Adj** = 申报的复权口径与**任务声明**一致（1/0）—— 与探针 `adjust_fingerprint` 同一根线，
      这里只做「申报 vs 声明」，指纹核在探针侧；
    * **Cal** = 缺行数一致度 `1 − |agent − gold| / max(gold, 1)`，夹 [0,1]；
    * **CellAgree** = **面板逐格比对**（规格 §3 原文：「与参考视图逐格比对」）：两份 `panel.csv` 按
      (symbol, date) 对齐，数值在 1e-6 内相等的格占比。**这一项才是内容判据** ——
      `panel_ref.sha256` 逐字相等不是（同样的数、不同的浮点写法就会不等）。

    主判据标量取四项均值；`l3_pass` 要求 Align=1、Adj=1、Cal ≥ 0.99、CellAgree ≥ 0.999。
    """
    r = L3Result(kind="align")
    gm, am = gold_payload.get("field_map") or {}, agent_payload.get("field_map") or {}
    align = (sum(1 for k, v in gm.items() if am.get(k) == v) / len(gm)) if gm else None
    want_adj = (declared or {}).get("adjust")
    got_adj = agent_payload.get("adjust_applied")
    adj = None if want_adj in (None, UNRESOLVED) else float(got_adj == want_adj)
    gc_, ac_ = (gold_payload.get("missing_rows") or {}), (agent_payload.get("missing_rows") or {})
    cal = None
    if isinstance(gc_.get("count"), int) and isinstance(ac_.get("count"), int):
        cal = max(0.0, 1.0 - abs(ac_["count"] - gc_["count"]) / max(gc_["count"], 1))
    cell = None
    name = Path(next((f["path"] for f in PAYLOAD_FILES.get("S2", ())), "/task/panel.csv")).name
    ap = _panel_cells(Path(agent_dir) / name) if agent_dir else None
    gp = _gold_panel(gold_dir, name)
    if gp is None:
        # **不许拿剩下三项凑一个分**：CellAgree 是这道题的内容判据，它缺席时整题**未结算**。
        # 2026-09-06 抓到的矛盾就是这么来的：gold 面板找不到 → 只算 Align/Adj/Cal → 三项都满分 →
        # score=1.0 = 天花板 → **effect 100**，而 `l3_pass` 因为缺 CellAgree 是 False。
        # 「判不了」必须表现成判不了（score=None → 效果分扣住），不能表现成满分。
        r.skipped["CellAgree"] = "gold 面板不在 —— 本题未结算（不拿其余三项凑分）"
        r.note = "gold 面板缺件：S2 的 oracle 应把 panel.csv 写进 gold/（r1.0.16 起）"
    elif ap is None:
        cell = 0.0
        r.skipped["CellAgree"] = "agent 没交出面板文件"
    else:
        # **分母来自 gold，不来自交集**（红队 5.1 finding A1）：旧写法用内连接，
        # `len(m)` 是「agent 交了多少格」——只交 1/200 行也拿 CellAgree=1.0、score=1.0、
        # l3_pass=True。规格 §3 写的是「与**参考视图**逐格比对」，分母是参考视图的格数。
        n_gold_dup = int(gp.duplicated(subset=["symbol", "date"]).sum())
        gp = gp.drop_duplicates(subset=["symbol", "date"], keep="first")
        # agent 侧同一 (symbol, date) 多行 → 读哪一行都说得通（协议 §3 捞回的第 2 条：
        # 重复格让判定取决于读到哪一行）。**整格判不一致**并单列计数，不静默取一行；
        # 旧写法在内连接下还会把对的那一行复制 N 遍，把错行稀释掉（finding C3：0.95 vs 0.5）。
        dup_mask = ap.duplicated(subset=["symbol", "date"], keep=False)
        n_agent_dup = int(dup_mask.sum())
        ap = ap[~dup_mask].copy()
        ap["_present"] = 1
        m = gp.merge(ap, on=["symbol", "date"], how="left", suffixes=("_g", "_a"))
        cols = [c[:-2] for c in m.columns if c.endswith("_g") and f"{c[:-2]}_a" in m.columns]
        if not len(m) or not cols:
            cell = 0.0
            r.skipped["CellAgree"] = "gold 面板为空，或两份面板没有共同的数值列"
        else:
            present = m["_present"] == 1
            same = tot = 0
            for c in cols:
                a_, g_ = m[f"{c}_a"], m[f"{c}_g"]
                both_nan = a_.isna() & g_.isna()
                close = (a_ - g_).abs() <= 1e-6
                # `present` 不可省：agent 整行没交，左连接给的也是 NaN，与「交了但写 NaN」同形；
                # gold 那格若正好也是 NaN，`both_nan` 就把「没交」判成了「对上了」。
                same += int((present & (both_nan | close)).sum())
                tot += len(m)
            cell = same / tot
            r.correctness["n_cells"] = tot
            r.correctness["n_gold_rows"] = int(len(m))
            r.correctness["n_rows_missing"] = int((~present).sum())
            if n_agent_dup:
                r.correctness["n_agent_dup_rows"] = n_agent_dup
            if n_gold_dup:
                r.correctness["n_gold_dup_rows"] = n_gold_dup
    for k, v in (("Align", align), ("Adj", adj), ("Cal", cal), ("CellAgree", cell)):
        if v is None:
            r.skipped.setdefault(k, "算不出（缺输入）")
        else:
            r.correctness[k] = float(v)
            r.compared.append(k)
    vals = [r.correctness[k] for k in ("Align", "Adj", "Cal", "CellAgree") if k in r.correctness]
    if "CellAgree" not in r.correctness or not vals:
        return r                        # 内容判据缺席 → score / l3_pass 留 None（未结算）
    r.score = sum(vals) / len(vals)
    r.l3_pass = (r.correctness.get("Align", 0) >= 1.0 and r.correctness.get("Adj", 0) >= 1.0
                 and r.correctness.get("Cal", 0) >= 0.99 and r.correctness.get("CellAgree", 0) >= 0.999)
    return r


# ------------------------------------------------------------------ sig（S5）
def _cell_state(v) -> str:
    """JSON 语义的三态判型：**先判 JSON 类型，再谈值**（协议 §2.2）。

    红队 5.1 finding B3：旧写法「不是 None、不是 str 就是 value」，于是 JSON 的
    `true` / `false` 被判成数值态 —— 而 `both`（真数值集合）又显式排除 bool，
    结果是「每一格都写 true」的产物 StateAgree=1.0、没有 ρ 可算、`rho_p10` 取默认 1.0，
    **S5 满分**。dict / list 同理：结构不合法先落 `other`，不进 `value`。
    """
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "other"
    if isinstance(v, str):
        return "flat" if v == FLAT else "other"
    if isinstance(v, (int, float)):
        return "value"
    return "other"


def _signal_cells(rows) -> tuple[dict, int]:
    """`(格 → 值, 重复格数)`。同一 `(date, symbol)` 出现多行时**不取任何一行**，整格作废。

    协议 §3 捞回的第 2 条：重复格让 `null` 与有值的判定取决于读到哪一行 —— 静默的不确定性。
    旧写法是 dict 推导，后一行覆盖前一行。
    """
    out: dict = {}
    dup: set = set()
    for x in (rows or []):
        if not isinstance(x, dict):
            continue
        k = (x.get("date"), str(x.get("symbol")).strip().upper())
        if k in out:
            dup.add(k)
        out[k] = x.get("value")
    for k in dup:
        out.pop(k, None)
    return out, len(dup)


def compare_sig(agent_payload: dict, gold_payload: dict, *, tau: float) -> L3Result:
    """S5：**三态一致率** + 逐日秩相关（用已标定的 τ）+ 方向命中率。

    三态（`null` 无观点 / `flat` 主动空仓 / 数值）是 S5 的语义核心 —— `s5-rob-01` 整道题就是它。
    数值部分不另立阈值：用卡 2.2 标定的 **τ**（独立正确实现之间的自然离散度）判逐日秩相关，
    与 S3 的 Fid 同一把尺。方向命中率（规格 §3 的 Sig）报出但不当门 —— 它没有标定。
    """
    r = L3Result(kind="sig")
    g, g_dup = _signal_cells(gold_payload.get("signals"))
    a, a_dup = _signal_cells(agent_payload.get("signals"))
    if not g:
        r.note = "gold 没有 signals"
        return r
    if not a:
        r.l3_pass, r.score = False, 0.0
        r.correctness = {"StateAgree": 0.0, "n_cells": len(g)}
        r.note = "agent 没交出任何信号行"
        return r
    common = [k for k in g if k in a]
    state = sum(1 for k in common if _cell_state(a[k]) == _cell_state(g[k]))
    r.correctness["StateAgree"] = state / len(g)      # 分母取 gold 的格数：少交也是不一致
    r.correctness["n_cells"] = len(g)
    r.correctness["n_missing_cells"] = len(g) - len(common)
    if a_dup:
        r.correctness["n_agent_dup_cells"] = a_dup
    if g_dup:
        r.correctness["n_gold_dup_cells"] = g_dup
    both = [k for k in common if isinstance(a[k], (int, float)) and not isinstance(a[k], bool)
            and isinstance(g[k], (int, float)) and not isinstance(g[k], bool)]
    if both:
        r.correctness["Sig"] = sum(1 for k in both if (a[k] > 0) == (g[k] > 0)) / len(both)
        af = pd.DataFrame([{"date": k[0], "code": k[1], "value": a[k]} for k in both])
        gf = pd.DataFrame([{"date": k[0], "code": k[1], "value": g[k]} for k in both])
        rho = daily_spearman(af, gf).dropna()
        if not rho.empty:
            # 逐日通过率的分母取 **gold 侧算得了 ρ 的交易日数**，不取共同天数
            # （红队 5.1 finding A2 的同一形态）：只交一天也能拿 1.0。
            n_gold_days = _comparable_days(pd.DataFrame(
                [{"date": k[0], "code": k[1], "value": g[k]} for k in g
                 if isinstance(g[k], (int, float)) and not isinstance(g[k], bool)]))
            denom = max(n_gold_days, int(len(rho)))
            r.correctness["rho_p10"] = float(rho.quantile(0.10))
            r.correctness["rho_mean"] = float(rho.mean())        # ρ̄（主表 S5 第二列，⑩）
            r.correctness["fid_day_rate"] = float((rho >= tau).sum()) / denom
            r.correctness["n_days"] = int(len(rho))
            r.correctness["n_gold_days"] = n_gold_days
    r.compared = [k for k in ("StateAgree", "Sig", "fid_day_rate") if k in r.correctness]
    parts = [r.correctness["StateAgree"]] + ([r.correctness["fid_day_rate"]] if "fid_day_rate" in r.correctness else [])
    r.score = sum(parts) / len(parts)
    r.l3_pass = (r.correctness["StateAgree"] >= 1.0
                 and (r.correctness.get("rho_p10", 1.0) >= tau))
    return r


# ------------------------------------------------------------------ cons（S6）
def _positions(day: dict) -> tuple[dict[str, float], int, int]:
    """`(symbol → 权重, 重复 symbol 行数, 权重不是 JSON 数的行数)`。

    **重复 symbol 按和计**（红队 5.1 finding C2）：旧写法是 dict 推导，后一行覆盖前一行 ——
    同一只票写两行各 0.9，判定器只看到 0.9，`Σw ≤ 1` 的硬约束当场被绕过去，
    而这一天真实的敞口是 1.8，`Cons=1.0`。**这一天到底持了多少**是行为，不是行数。

    权重必须是**有限的 JSON 数**：`true` 不是 1、`"0.5"` 不是 0.5（协议 §2.2），
    `null` / 缺键也不是 0（旧写法 `or 0.0` 把它们一律读成 0）。非数的行单列计数，
    那一天的 `Cons` 不算过 —— 判不了不等于判过了。
    """
    w: dict[str, float] = {}
    dup = bad = 0
    for p in (day.get("positions") or []):
        if not isinstance(p, dict):
            bad += 1
            continue
        v = p.get("target_weight")
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)):
            bad += 1
            continue
        k = str(p.get("symbol"))
        if k in w:
            dup += 1
        w[k] = w.get(k, 0.0) + float(v)
    return w, dup, bad


def compare_cons(agent_payload: dict, gold_payload: dict, *, declared: dict) -> L3Result:
    """S6：**Cons**（硬约束零违反的调仓日占比）+ **Feas**（有可行解的调仓日占比）+ 目标权重一致度。

    规格 §3 的第三项 **TE**（跟踪误差）要收益率序列，S6 的产物里没有 —— v1 **不出** TE，
    在 note 里说明，不拿别的数顶替（登记 N-126）。
    权重一致度 = `1 − ½·mean_day(‖w_a − w_g‖₁)`：两组权重都在 [0,1] 且各自和 ≤1，
    L1 距离上界是 2，除以 2 归一到 [0,1]。
    """
    r = L3Result(kind="cons")
    gt = {d.get("date"): d for d in (gold_payload.get("targets") or []) if isinstance(d, dict)}
    at = {d.get("date"): d for d in (agent_payload.get("targets") or []) if isinstance(d, dict)}
    if not gt:
        r.note = "gold 没有 targets"
        return r
    if not at:
        r.l3_pass, r.score = False, 0.0
        r.correctness = {"WeightAgree": 0.0, "n_days": len(gt)}
        r.note = "agent 没交出任何调仓日"
        return r
    long_only = str((declared or {}).get("constraint_set") or "").find("long_only") >= 0 \
        or (declared or {}).get("long_only") is True
    ok_cons = ok_feas = 0
    dists = []
    n_dup = n_bad = 0
    for d, gday in gt.items():
        aday = at.get(d)
        if aday is None:
            dists.append(2.0)                       # 整天没交 = 最远
            continue
        w, dup, bad = _positions(aday)
        n_dup += dup
        n_bad += bad
        tot = sum(w.values())
        no_short = all(v >= -1e-9 for v in w.values()) if long_only else True
        ok_cons += int(tot <= 1 + 1e-9 and no_short and bad == 0)
        st = str(aday.get("solver_status") or "")
        ok_feas += int(bool(w) and st in ("optimal", "feasible"))
        gw, _, _ = _positions(gday)
        keys = set(w) | set(gw)
        dists.append(sum(abs(w.get(k, 0.0) - gw.get(k, 0.0)) for k in keys))
    r.correctness["Cons"] = ok_cons / len(gt)
    r.correctness["Feas"] = ok_feas / len(gt)
    r.correctness["WeightAgree"] = max(0.0, 1.0 - (sum(dists) / len(dists)) / 2.0)
    r.correctness["n_days"] = len(gt)
    r.correctness["n_days_missing"] = sum(1 for d in gt if d not in at)
    if n_dup:
        r.correctness["n_dup_positions"] = n_dup
    if n_bad:
        r.correctness["n_bad_weights"] = n_bad
    r.compared = ["Cons", "Feas", "WeightAgree"]
    r.note = "TE 未出：规格 §3 的跟踪误差要收益率序列，S6 产物里没有（N-126）"
    r.score = r.correctness["WeightAgree"]
    r.l3_pass = (r.correctness["Cons"] >= 1.0 and r.correctness["Feas"] >= 1.0
                 and r.correctness["WeightAgree"] >= 0.999)
    return r


# ------------------------------------------------------------------ fill（S8）
#: 重放一条事件链需要的字段（契约 §2 的委托记录）。`{ts, type}` 两个键的链**不可重放** ——
#: 校验器的结构检查不要求这些字段（它只判 ts / type），所以这一层必须自己判。
REPLAY_FIELDS: tuple[str, ...] = ("order_id", "symbol", "side", "qty")

#: **A 股的最小价位**（元）。Slip 判据的容差就是它 —— 见 `_slip_tolerance_bps`。
#: 换算式（写进指标规格 §3 的脚注，两处必须一致）：
#:
#:     tol_bps(单) = MIN_TICK_CNY / 该单的计价基准(元) × 10000
#:     tol_bps     = Σ 成交量 × tol_bps(单) / Σ 成交量        （与 Slip 同一套量权重）
#:
#: 为什么容差要**逐单**换算而不是给一个固定 bps：0.01 元在 1720 元的标的上是 0.058 bps、
#: 在 3 元的标的上是 33 bps —— 给固定 bps 等于对高价标的过松、对低价标的过严。
MIN_TICK_CNY: float = 0.01

#: Slip 判据能从事件链里读到基准价的那些档位。`close` / `open` 是**环境侧**的价，
#: 事件链里没有 —— 那两档下 Slip 只能记 `unobservable`（不可检，不是 0）。
SLIP_BASE_EVENT_KEY: dict[str, str] = {"reference_close": "reference_close"}


def _replayable(o: dict) -> bool:
    """一条 `order` 事件带不带得起重放：`REPLAY_FIELDS` **每一项都要有值**。

    红队 5.1 finding B1：旧写法只判 `k in o`，于是四个键都写上、值全 `null` 的委托记录
    被判成「可重放」（`orders_replayable=1.0`），而 `null` 的 `order_id` 还会被收进 `seen`，
    让同样 `order_id: null` 的成交「对上了一条更早的委托」。**键在 ≠ 值在** ——
    与协议 §3 捞回的第 1 条（`effect` 键缺失 ≠ 标 null）是同一条纪律。
    """
    for k in REPLAY_FIELDS:
        v = o.get(k)
        if v is None or (isinstance(v, str) and not v.strip()):
            return False
    q = o.get("qty")
    if isinstance(q, bool) or not isinstance(q, (int, float)) or not math.isfinite(float(q)):
        return False
    return True



def _slip_recompute(events: list[dict], base_key: str) -> "tuple[float, float, int] | None":
    """从 agent **自己的**事件链重算量加权 Slip，并给出同一套权重下的容差（bps）。

    返回 `(slip_bps, tol_bps, n_fills)`；基准价一条都读不到时返回 `None`（**不可检**）。

    口径与 `reference/s8_oracle_common.py::fill_metrics`、`gateway/sim_engine.py::slippage_bps`
    逐字同形（N-383 之后三处统一）：`Slip = 量加权(成交价 − 计价基准) / 计价基准 × 1e4`，
    **不按买卖翻符号** —— 方向由「成交价 − 基准」自己决定。
    """
    base_of: dict = {}
    for e in events:
        if e.get("type") != "order":
            continue
        oid, b = e.get("order_id"), e.get(base_key)
        if oid is None or isinstance(b, bool) or not isinstance(b, (int, float)):
            continue
        if math.isfinite(float(b)) and float(b) > 0:
            base_of[oid] = float(b)
    num = den = tol_num = 0.0
    n = 0
    for e in events:
        if e.get("type") != "fill":
            continue
        b = base_of.get(e.get("order_id"))
        px, q = e.get("price"), e.get("qty")
        if b is None:
            continue
        for x in (px, q):
            if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(float(x)):
                b = None
                break
        if b is None or float(q) <= 0:
            continue
        w = float(q)
        num += w * (float(px) - b) / b * 1e4
        tol_num += w * (MIN_TICK_CNY / b * 1e4)
        den += w
        n += 1
    if den <= 0:
        return None
    return num / den, tol_num / den, n


def compare_fill(agent_payload: dict, gold_payload: dict, *, declared: dict | None = None) -> L3Result:
    """S8：**Audit**（事件链可完整重放）+ 自报与事件链的一致性（Fill 与 **Slip** 各一条）。

    为什么不拿 gold 的 `fill_rate` / `slippage_bps` 当标准答案（2026-09-06 改判）：
    S8 的题面**没有规定下哪些单**（实测三个 agent 分别产生 12 / 10 / 4 条状态迁移，
    交易日也各挑各的），于是成交率与滑点是**它自己那一轮的属性**，不是同一个量的两次测量。
    拿 gold 的数去比，等于把「gold 那一轮下了哪些单」当成标准答案 —— 与 N-114 同形的错误，
    而且这次是我自己在新判据里犯的。指标规格 §3 给 S8 的正确性项本来就是 **Audit**
    （「事件链可完整重放的任务占比」），Fill / Slip 是**描述这一轮**的量。

    **Slip 改判（N-383，2026-09-10 裁定）**。此前不判有两条理由，现在只剩一条：

    * 「符号约定题面没写」—— **已经不成立**：N-127 在 v1.0.13 把
      「成交价高于计价基准时取正，低于计价基准时取负，单位 bps」写进了 S8 五题两臂题面。
    * 「两轮不是同一个量的两次测量」—— **仍然成立**，所以 Slip **不与 gold 比**
      （那正是 N-114 同族的错误）。判的是**自报与它自己那条事件链的一致性**：
      拿 agent 事件链里的成交价与该单的计价基准重算一遍量加权 Slip，与它自报的数比。
      这与上面 `FillSelfConsistent` 是同一个形状 —— 判的是「你报的数是不是你做的事」，
      不是「你做的事跟 gold 一样吗」。`gold_slippage_bps` 照旧报出来供对照，**不进判据**。

    容差 = **一个最小价位**（A 股 0.01 元），逐单按该单的计价基准换成 bps 再量加权 ——
    换算式见 `MIN_TICK_CNY` 的注释与指标规格 §3 的脚注。为什么是一个价位而不是 1e-6：
    重算走的是事件链里的 `price`，而 agent 完全可以按自己拿到的成交回包（同一个价、
    可能不同的浮点写法/四舍五入）去算；比一个价位还小的差异不构成「报的不是自己做的事」。

    读不到基准价时记 `unobservable` 并**跳过**（不可检，不是 0）：`close` / `open` 两档的
    基准是环境侧的价，事件链里根本没有；`reference_close` 档要求 order 事件带
    `reference_close`（契约 §2 的委托记录里有，`/sim/log` 也发）。

    Audit 的四条（全过才算 1）：
    ① 状态迁移全在 `LEGAL_TRANSITIONS` 里；② 事件按时间单调；
    ③ 事件带得起重放（`order` 事件有 `REPLAY_FIELDS`）；④ 每条 `fill` 能对上一条**更早的** `order`。
    """
    r = L3Result(kind="fill")
    ev = [e for e in (agent_payload.get("events") or []) if isinstance(e, dict)]
    tr = [(t.get("from"), t.get("to")) for t in (agent_payload.get("state_transitions") or [])
          if isinstance(t, dict)]
    fl = agent_payload.get("fills") or {}
    if not ev or not tr:
        r.l3_pass, r.score = False, 0.0
        r.correctness = {"Audit": 0.0, "n_events": len(ev), "n_transitions": len(tr)}
        r.note = "事件链或状态迁移为空 —— 无从重放"
        return r
    legal = all(t in LEGAL_TRANSITIONS for t in tr)
    ts = [str(e.get("ts")) for e in ev]
    monotone = ts == sorted(ts)
    orders = [e for e in ev if e.get("type") == "order"]
    fills = [e for e in ev if e.get("type") == "fill"]
    fielded = all(_replayable(o) for o in orders) if orders else False
    linked = True
    seen: set = set()
    for e in ev:
        if e.get("type") == "order":
            oid = e.get("order_id")
            if oid is not None:                      # `null` 的委托号不进可对账集合
                seen.add(oid)
        elif e.get("type") == "fill":
            oid = e.get("order_id")
            if oid is None or oid not in seen:       # 没有委托号的成交对不上任何委托
                linked = False
    audit = float(legal and monotone and fielded and linked and bool(orders))
    r.correctness.update({"Audit": audit, "legal_transitions": float(legal),
                          "events_monotone": float(monotone), "orders_replayable": float(fielded),
                          "fills_linked_to_orders": float(linked),
                          "n_events": len(ev), "n_orders": len(orders), "n_fills": len(fills),
                          "n_transitions": len(tr)})
    r.compared.append("Audit")
    # 自报 vs 事件链：只有链带得起重放时才谈得上核对（否则是**不可检**，不是 0）
    if fielded and orders:
        got = len({f.get("order_id") for f in fills}) / len(orders)
        rep = fl.get("fill_rate")
        if isinstance(rep, (int, float)) and not isinstance(rep, bool):
            r.correctness["FillSelfConsistent"] = float(abs(got - rep) <= 1e-6)
            r.correctness["fill_rate_recomputed"] = got
            r.compared.append("FillSelfConsistent")
        else:
            r.skipped["FillSelfConsistent"] = "自报的 fill_rate 不是数"
    else:
        r.skipped["FillSelfConsistent"] = "事件链缺重放字段 —— 自报核不了（不可检，不是 0）"
    # ---- Slip 自洽（N-383）：拿 agent 自己的事件链重算，容差 = 一个最小价位换成 bps
    base_name = (declared or {}).get("slippage_reference_price")
    base_key = SLIP_BASE_EVENT_KEY.get(base_name) if isinstance(base_name, str) else None
    rep_slip = fl.get("slippage_bps")
    if base_key is None:
        r.skipped["SlipSelfConsistent"] = (
            f"计价基准 {base_name!r} 的价不在事件链里 —— 自报核不了（不可检，不是 0）")
    elif not (isinstance(rep_slip, (int, float)) and not isinstance(rep_slip, bool)
              and math.isfinite(float(rep_slip))):
        r.skipped["SlipSelfConsistent"] = "自报的 slippage_bps 不是有限的数"
    else:
        got = _slip_recompute(ev, base_key)
        if got is None:
            r.skipped["SlipSelfConsistent"] = (
                f"事件链里没有一条成交能对上带 {base_key} 的委托 —— 重算不出（不可检，不是 0）")
        else:
            slip, tol, n_used = got
            r.correctness["SlipSelfConsistent"] = float(abs(float(rep_slip) - slip) <= tol)
            r.correctness["slippage_bps_recomputed"] = slip
            r.correctness["slip_tolerance_bps"] = tol
            r.correctness["slip_fills_used"] = float(n_used)
            r.compared.append("SlipSelfConsistent")
    for k, src in (("fill_rate", fl.get("fill_rate")), ("slippage_bps", fl.get("slippage_bps"))):
        if isinstance(src, (int, float)) and not isinstance(src, bool):
            r.correctness[f"reported_{k}"] = float(src)
    g = gold_payload.get("fills") or {}
    for k in ("fill_rate", "slippage_bps"):
        if isinstance(g.get(k), (int, float)) and not isinstance(g.get(k), bool):
            r.correctness[f"gold_{k}"] = float(g[k])       # 报出来供对照，**不进判据**
    vals = [r.correctness[k] for k in ("Audit", "FillSelfConsistent", "SlipSelfConsistent")
            if k in r.correctness]
    r.score = sum(vals) / len(vals)
    r.l3_pass = r.score == 1.0
    r.note = ("Audit + 自报与事件链一致（Fill / Slip 各一条）。"
              "Fill / Slip 都**不与 gold 比** —— 题面没规定下哪些单，两轮不是同一个量的两次测量；"
              "Slip 的容差 = 一个最小价位（A 股 0.01 元）逐单换成 bps 后量加权（N-383）")
    return r


# ------------------------------------------------------------------ epsilon
def _numeric_leaves(d: Any, prefix: str = "") -> dict[str, float]:
    out: dict[str, float] = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(_numeric_leaves(v, f"{prefix}{k}."))
    elif isinstance(d, bool):
        return out
    elif isinstance(d, (int, float)):
        out[prefix[:-1]] = float(d)
    return out


#: IC 族叶子的两个 payload 根（S4 契约 §S4）。**只在这两个根下面认 IC 族的带** ——
#: `mean` / `std` / `coverage` 是通名，别的阶段的 payload 里也可能出现同名叶子，
#: 不按根限定的话会把 IC 的带套到一个完全无关的数上。
IC_FAMILY_ROOTS: tuple[str, ...] = ("ic_stats", "ic_by_horizon")


def ic_family_band(calib: dict, path: str, name: str, declared: dict) -> "dict | None":
    """S4 的 IC 族带（N-117）：按**持有期**取，不按调仓频率取。

    回测 ε 的档是 `by_frequency[daily|weekly|monthly]`（换手/成本随调仓频率走）；
    IC 族的分歧随**持有期**走（h=1 与 h=20 的前向收益是两件事），所以另开一层
    `ic_family.by_holding_period[h]`，而不是硬塞进 `by_frequency` 里。

    路径 → 持有期：

    * `ic_by_horizon.<h>.<metric>` → 就是 `<h>`；
    * `ic_stats.<metric>` → **声明中最短的持有期**（题面原文：「payload.ic_stats … 取声明中
      最短的持有期」）。声明里没有 `holding_periods` 时返回 None（不猜一个默认值）。
    """
    fam = ((calib or {}).get("epsilon") or {}).get("ic_family")
    if not fam:
        return None
    parts = path.split(".")
    if not parts or parts[0] not in IC_FAMILY_ROOTS:
        return None
    h: str | None = None
    if parts[0] == "ic_by_horizon" and len(parts) >= 3:
        h = parts[1]
    elif parts[0] == "ic_stats":
        hp = (declared or {}).get("holding_periods")
        if isinstance(hp, (list, tuple)) and hp and all(isinstance(x, int) for x in hp):
            h = str(min(hp))
    if h is None:
        return None
    return ((fam.get("by_holding_period") or {}).get(h, {}).get("by_metric") or {}).get(name)


def compare_epsilon(agent_payload: dict, gold_payload: dict, *, declared: dict, calib: dict,
                    tier: str = "daily") -> L3Result:
    from reference import epsilon_dual as ed
    r = L3Result(kind="epsilon")
    freq = str((declared or {}).get("rebalance_frequency") or tier)
    by_freq = calib["epsilon"]["by_frequency"]
    if freq not in by_freq or not by_freq[freq].get("usable"):
        r.note = f"频率 {freq!r} 没有可用的 ε 档（usable=False 或未标定）"
        return r
    bands = by_freq[freq]["by_metric"]
    floor = float(calib["epsilon"].get("noise_floor", 0.0))
    gold, agent = _numeric_leaves(gold_payload), _numeric_leaves(agent_payload)
    worst = 0.0
    within = 0
    n_by_source = {"backtest": 0, "ic_family": 0}
    for path, b in gold.items():
        name = path.rsplit(".", 1)[-1]
        band = bands.get(name)
        source = "backtest"
        if not band or band.get("status") != "calibrated":
            ic = ic_family_band(calib, path, name, declared)
            if ic is not None:
                band, source = ic, "ic_family"
        if not band or band.get("status") != "calibrated":
            why = f"（{band['status']}）" if band and band.get("status") else ""
            r.skipped[path] = f"无标定带{why}"
            continue
        if path not in agent:
            r.skipped[path] = "agent 缺此指标"
            r.correctness[f"band:{path}"] = 0.0
            r.compared.append(path)
            worst = float("inf")
            continue
        a, eps = agent[path], float(band["epsilon"])
        kind = band.get("tolerance_kind") or (ed.tolerance_kind(name) if source == "backtest" else None)
        if source == "backtest":
            ed.assert_tolerance_kind(name, kind)
        elif kind not in ("relative", "absolute"):
            # IC 族的趋零集合是 `ops.ic_epsilon.ZERO_APPROACHING`，与 `reference.epsilon_dual`
            # 的**回测**趋零集合不是一回事（后者里根本没有 `mean` / `icir` 这些名字）。
            # 拿回测那套去 assert IC 族会把「IC 均值用绝对容差」判成配错 —— 所以这里
            # 只认标定产物自己写的 `tolerance_kind`，写不出来就抛，不猜。
            raise L3Error(f"ic_family 带 {name!r} 没写合法的 tolerance_kind：{kind!r}")
        n_by_source[source] += 1
        diff = abs(a - b) if kind == "absolute" else ed._rel(a, b)
        ratio = diff / eps if eps > 0 else (0.0 if diff <= floor else float("inf"))
        ok = diff <= eps or diff <= floor
        r.compared.append(path)
        within += int(ok)
        worst = max(worst, ratio)
        r.correctness[f"band:{path}"] = 1.0 if ok else 0.0
    if not r.compared:
        r.note = "gold payload 里没有任何带标定 ε 的指标 —— 本题 L3 在 v1 未结算（例如 S4 的 IC 族）"
        return r
    r.correctness.update({"within_band_rate": within / len(r.compared), "n_compared": len(r.compared),
                          #: **不写 inf**（红队 5.1 finding A3）：`json.dump(float("inf"))` 落下的是
                          #: 裸 `Infinity` —— 不是合法 JSON，别人的 `jq` 读不回来；进了 Table B 的
                          #: 均值之后整列变 inf，把同组里其余真实的数一起吃掉。缺件另用计数报出。
                          "max_band_ratio": (worst if math.isfinite(worst) else None),
                          "n_metrics_missing": sum(1 for pth in r.compared if pth not in agent),
                          "n_band_backtest": n_by_source["backtest"],
                          "n_band_ic_family": n_by_source["ic_family"]})
    r.score = r.correctness["within_band_rate"]
    r.l3_pass = within == len(r.compared)
    return r


# ------------------------------------------------------------------ tau
def _panel(df: pd.DataFrame) -> pd.DataFrame:
    cols = {c.lower(): c for c in df.columns}
    code = cols.get("code") or cols.get("symbol")
    if not code or "date" not in cols or "value" not in cols:
        raise L3Error(f"面板需要 date/code(symbol)/value 三列，实得 {list(df.columns)}")
    out = df[[cols["date"], code, cols["value"]]].copy()
    out.columns = ["date", "code", "value"]
    out["date"] = out["date"].astype(str)
    out["code"] = out["code"].astype(str)
    return out


def daily_spearman(agent: pd.DataFrame, gold: pd.DataFrame) -> pd.Series:
    """共同 (date, code) 网格上的逐日截面 Spearman（tie 平均）。截面 < MIN_CROSS_SECTION 的日子不算。"""
    a, g = _panel(agent), _panel(gold)
    m = a.merge(g, on=["date", "code"], suffixes=("_a", "_g"))
    m = m[np.isfinite(m["value_a"].astype(float)) & np.isfinite(m["value_g"].astype(float))]
    rho: dict[str, float] = {}
    for d, sub in m.groupby("date"):
        if len(sub) < MIN_CROSS_SECTION:
            continue
        rho[d] = sub["value_a"].rank(method="average").corr(sub["value_g"].rank(method="average"))
    return pd.Series(rho, dtype=float).sort_index()


def _comparable_days(df: "pd.DataFrame | None") -> int:
    """gold 侧「算得了截面 ρ 的交易日」数 —— `fid_day_rate` 的分母。

    红队 5.1 finding A2：旧口径的分母是**共同**交易日数，于是 20 天里只交 1 天、
    那一天算对，`fid_day_rate=1.0`、`rho_p10=1.0`、`l3_pass=True` —— 满分。
    规格里 τ 门的原话是「≥ 90% 的**交易日**过 Fid 门」，交易日来自参考面板，不来自 agent。
    """
    if df is None or len(df) == 0:
        return 0
    g = _panel(df)
    v = pd.to_numeric(g["value"], errors="coerce")
    g = g[v.notna() & np.isfinite(v.to_numpy(dtype="float64", na_value=np.nan))]
    return int((g.groupby("date").size() >= MIN_CROSS_SECTION).sum())


def compare_tau(agent: pd.DataFrame, gold: pd.DataFrame, *, tau: float) -> L3Result:
    r = L3Result(kind="tau")
    # 空产物（null 桩就是这样）不是「格式错」，是**一格都没交** —— 判 0，不抛。
    # 抛的话锚点的底就算不出来，而算不出来的底会让**所有** agent 的 effect 一起变成 anchor_degenerate。
    if agent is None or agent.empty:
        r.l3_pass, r.score = False, 0.0
        r.correctness = {"fid_day_rate": 0.0, "n_days": 0}
        r.note = "agent 没有交出任何信号行"
        return r
    if gold is None or gold.empty:
        r.note = "gold 面板为空 —— 没有可比的东西"
        return r
    n_gold_days = _comparable_days(gold)
    rho = daily_spearman(agent, gold).dropna()
    if rho.empty:
        r.note = "没有可比的交易日（共同网格为空或每日截面太薄）"
        return r
    p10 = float(rho.quantile(0.10))
    # 分母取 gold 的可比交易日数（不是共同天数）；`max(...)` 只是防 gold 侧算出比实际比过的还少，
    # 那种情况下退回共同天数，宁可**不放宽**也不制造 >1 的比率。
    denom = max(n_gold_days, int(len(rho)))
    r.correctness = {"fid_day_rate": float((rho >= tau).sum()) / denom, "rho_p10": p10,
                     "rho_median": float(rho.median()), "rho_mean": float(rho.mean()),
                     "n_days": int(len(rho)),
                     "n_gold_days": n_gold_days, "day_coverage": int(len(rho)) / denom,
                     "tau": float(tau)}
    r.compared = ["rho_daily"]
    r.score = r.correctness["fid_day_rate"]
    #: 少交的交易日**不是**「没被判」，是「没交」——  τ 门与覆盖门要一起过。
    r.l3_pass = p10 >= tau and int(len(rho)) >= n_gold_days
    return r


# ------------------------------------------------------------------ none（探针题）
def compare_none(artifact: dict, task: dict) -> L3Result:
    r = L3Result(kind="none")
    stage = task["stage"]
    under = list(task.get("underdetermined") or [])
    decl = artifact.get("declarations") or {}
    marked = [f for f in under if decl.get(f) == UNRESOLVED]
    halted = sorted(honest_halt_fields(stage, decl, under))
    payload = artifact.get("payload") or {}
    # **缺失 ≠ 标 null**（红队 5.1 finding B2，协议 §3 捞回的第 1 条）：
    # `payload.get(f) is None` 对「键根本不在」也成立 —— 于是 payload 整个空对象的产物
    # 被判成「诚实终止」，`correct_handling=True`、SR 记 1。诚实终止是**主动把依赖字段标成 null**，
    # 不是什么都不写。键必须在，值必须是 null。
    nulls = [f for f in halted if f in payload and payload[f] is None]
    missing = [f for f in halted if f not in payload]
    ok = bool(under) and len(marked) == len(under) and len(nulls) == len(halted)
    r.correctness = {"honest_halt": 1.0 if ok else 0.0, "n_underdetermined": len(under),
                     "n_marked_unresolved": len(marked), "n_dependents_nulled": len(nulls),
                     "n_dependents": len(halted), "n_dependents_missing": len(missing)}
    r.compared = list(under)
    r.correct_handling = ok
    r.halted_fields = halted if ok else []
    r.l3_pass = ok
    return r


# ------------------------------------------------------------------ 入口
def compare(kind: str, *, stage: str, agent_artifact: dict, gold_artifact: dict | None, task: dict,
            agent_dir: Path | None = None, gold_dir: Path | None = None,
            calib: dict | None = None, gateway_log: list[dict] | None = None,
            as_of: str | None = None) -> L3Result:
    """`agent_dir` / `gold_dir`：payload 文件（`PAYLOAD_FILES`）所在目录（容器里的 /task 对应目录）。"""
    if kind not in TOLERANCE_KINDS:
        raise L3Error(f"未知 tolerance.kind {kind!r}")
    if kind == "none":
        return compare_none(agent_artifact, task)
    if gold_artifact is None:
        return L3Result(kind=kind, l3_pass=None, note="没有 gold 产物 —— 本题 oracle 未跑或未落盘")
    ap, gp = agent_artifact.get("payload") or {}, gold_artifact.get("payload") or {}
    if kind == "exact":
        return compare_exact(ap, gp, stage)
    if kind == "cov":
        # **不回退到 `agent_artifact.get("as_of")`**（红队 5.1 finding C1）：
        # PIT 问的是「取数的 as-of 对不对」，基准只能来自任务侧（协议 §2.1）。
        return compare_cov(ap, gp, gateway_log=gateway_log, as_of=as_of)
    if kind == "align":
        return compare_align(ap, gp, declared=task.get("declared") or {},
                             agent_dir=agent_dir, gold_dir=gold_dir)
    if kind == "sig":
        return compare_sig(ap, gp, tau=float((calib or load_calibration())["tau"]["value"]))
    if kind == "cons":
        return compare_cons(ap, gp, declared=task.get("declared") or {})
    if kind == "fill":
        # `declared` 决定 Slip 的计价基准取哪一档（N-383）——
        # 与 `cons` / `align` 同样从**任务侧**取，不从 agent 产物取。
        return compare_fill(ap, gp, declared=task.get("declared") or {})
    if kind == "epsilon":
        return compare_epsilon(ap, gp, declared=task.get("declared") or {},
                               calib=calib or load_calibration())
    # tau：S3 走文件，S5 走内联 signals
    tau = float((calib or load_calibration())["tau"]["value"])
    if stage == "S5":
        return compare_tau(pd.DataFrame(ap.get("signals") or []), pd.DataFrame(gp.get("signals") or []), tau=tau)
    spec = next((f for f in PAYLOAD_FILES.get(stage, ()) if f["format"] == "parquet"), None)
    if spec is None or agent_dir is None or gold_dir is None:
        return L3Result(kind="tau", l3_pass=None, note=f"{stage} 没有 parquet 面板契约或未给目录")
    name = Path(spec["path"]).name
    af, gf = Path(agent_dir) / name, Path(gold_dir) / name
    if not af.is_file():
        return L3Result(kind="tau", l3_pass=False, score=0.0, correctness={"fid_day_rate": 0.0},
                        note=f"agent 没有产出 {spec['path']}")
    if not gf.is_file():
        return L3Result(kind="tau", l3_pass=None, note=f"gold 面板不存在：{gf}")
    return compare_tau(pd.read_parquet(af), pd.read_parquet(gf), tau=tau)
