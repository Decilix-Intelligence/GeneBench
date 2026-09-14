"""卡 5.3（线 C / C3，2026-09-05）：遥测结算 + 报告器 —— Table A / Table B → CSV → LaTeX。

口径来自 `ops/specs/GeneBench指标规格_v1.md` §2/§3（与《指标对接决定 v1》一致处按后者）：

* **SR** = 存在可评分终端产物的比例（L1）。分母按 `failure_modes.sr_denominator` —— **只排除 `unscorable_harness`**，
  泄漏留在分母。比率类指标先在任务内对种子取均值，再对任务宏平均（§0）。
* **pass@1** = mean_t mean_s succ；succ = 闸门 valid ∧ L3 通过（诚实终止题按 `correct_handling`）。
* **pass^k** = mean_t C(c,k)/C(n,k)（τ-bench 无偏估计；n<k 的任务**不进均值**并计数报出，不补 0）。
* **ProgressRate** = mean_t mean_s 1[产物过 V_k 结构检查]。单阶段题就是「不 malformed」；八阶段 1/8 加权只对 Chain 题
  有意义（v1 冒烟集全是单阶段题，这里按阶段指示实现，Chain 版留待有 Chain 题再接）。
* **Steps** = 每次运行经边车的模型调用次数（网络侧计数，不采信自报）。
* **$** = 每 run 的 `cost_usd` 均值（与 Steps / Latency 同为逐 run 均值口径，对应规格 §3 的「$/task」）。
  单价来自 `runner/pricing.yaml`（卡 1.5，带 `source_url`）；DeepSeek 分高峰/低谷两档而边车不记档位，
  表里取高峰价 —— **这一列是成本上界，不是账单实数**，表下要写这句。缺价或缺 usage 的 run 不进均值；
  一条都算不出时 `$` 为空而不是 0。tokens（prompt / completion，网络侧 usage）照旧单列。
* **Latency** = `run.json.elapsed_s` 的均值（runner 侧真值）。
* **Recov** = 在至少被 validator 拒过一次的运行里，最终 valid 的比例（只有 GQ 臂有 validator.log；
  裸臂没有这条回路 → 空，不是 0）。
* **越权率** = Σ 拒绝(403) / Σ 数据与操作请求，网络侧结算；本次运行日志不可得 → 不进分子分母。

空值纪律与三态同一：**算不出就是 None，不是 0**——0 会进均值与排名。CSV 里写空串，LaTeX 里写 `---`。
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from math import comb
from pathlib import Path
from typing import Any, Iterable

from runner.c42 import failure_modes as FM

#: 四条版本轴。**与 `scorer.score_run.VERSION_AXES` 逐字一致** ——
#: 不在这里 import 它（`score_run` 拖着 runner/网关那一整棵依赖树，报告器得能单独跑），
#: 一致性由 `ops/test_scorer_report.py::test_version_axes_same_as_score_run` 钉住。
VERSION_AXES: tuple[str, ...] = ("set_version", "reference_version", "runner_version", "image_digest")

#: ρ̄（S5 的逐日秩相关均值）与 ε-agr（S7 的带内率）里有组合字符与希腊字母 ——
#: 写成码位，免得复制粘贴时被规范化成别的形状（表头一旦漂了，`--filter` 与测试一起失效）。
RHO_BAR: str = "\u03c1\u0304"                 # ρ + U+0304 组合长音符
EPS_AGR: str = "\u03b5-agr"                    # ε-agr

#: **⑩ 主表固定十九列**（2026-09-10 用户裁定）：`SR / P@1 / $` + 每阶段两列。
#: 列名与顺序**写死**，由 `ops/test_report_columns.py` 逐字钉住（列集相等 + 顺序相等）。
#:
#: 为什么要写死：主表是发布件，读者会把两次发布的同一列并排读。列一旦按「行里有什么键」
#: 动态生成，加一个诊断量就会把表挤宽、去一个就会静默消失 —— 而消失的那一列不会报错。
#:
#: 逐列的定义 / 数据源 / 闸门条件 / 不可得时显示什么，见 `ops/reports/report_spec_v1.md`。
MAIN_TABLE_COLUMNS: tuple[str, ...] = (
    "SR", "P@1", "$",
    "Cov", "Prov",              # S1
    #: **⑥-c（2026-09-11 用户裁定）**：S2 的保真列由 `Align` 换成 `CellAgree`（表头 `Cell%`）。
    #: `Align` 量的是**申报**（字段映射到金标 schema 的正确率），`CellAgree` 量的是**内容**
    #: （面板逐格比对的一致率）。`Adj` 留作**有效性列**（复权口径与任务声明一致）。
    "Cell%", "Adj",             # S2
    "Fid", "Decl",              # S3
    "IC-agr", "Set",            # S4
    "Sig", RHO_BAR,             # S5
    "W-agr", "Cons",            # S6
    EPS_AGR, "Ledger",          # S7
    "Audit", "Ovr",             # S8
)

#: 主表的身份列（不是指标）。**主表 = 身份列 + 十九列**，一列不多一列不少。
TABLE_A_INDEX_COLUMNS: tuple[str, ...] = ("config_id", "arm", "arm_kind", "n_tasks", "n_runs")

#: 主表**不许有**的那一类列：把多阶段合成一个数的总分（⑪ 取消聚合）。
#: 这里列的是名字模式，`ops/test_report_columns.py` 拿它断言主表里一个都没有 ——
#: 「以后别人加一列 total 上去」是这条裁定最可能的破法，而加列不会报错。
AGGREGATE_COLUMN_NAMES: tuple[str, ...] = ("total", "总分", "overall", "composite", "score",
                                           "effect", "aggregate")

#: Table A 是**诊断件，不是发布件**（⑥-b，2026-09-11 用户裁定）：它带 `effect` 这一列，
#: 而 ⑪ 明写 effect 不进发布表。发布表只有三张 —— 主表 `table_main` + 两张全量指标表
#: （`metrics_agent` / `metrics_stage`）。`table_a` / `table_b` 照旧出、照旧归档**留证据**，
#: 但不进发布件清单、不供引用；判据在 `ops/mk_release_manifest.py::DIAGNOSTIC_NOT_RELEASE`
#: 与 `ops/archive_signoff.py::RELEASE_TABLES`，落盘时旁边还会写一份 `table_a.NOTE.md`。
#:
#: Table A 的 CSV 列。**内容与顺序一字不动**（2026-09-10 卡 C）——
#: `ops/test_results_db.py` 的七条「从结果库出的表与既有 `ops/reports/<batch>/table_a.csv`
#: 逐格相同」按列集逐字节比；改这里等于把那七条判红，而那不是回归，是因为列集变了。
#: 主表是**另一张表**（`MAIN_TABLE_COLUMNS` + `main_table()`），`effect` 不在其中。
#: Table A 的行里现在**多出**主表要用的十九列键 —— `DictWriter(extrasaction="ignore")`
#: 会把多余的键丢掉，既有 CSV 因此一个字节都不变。
TABLE_A_COLUMNS: tuple[str, ...] = (
    "config_id", "arm", "arm_kind", "n_tasks", "n_runs",
    "SR", "pass@1", "pass^3", "ProgressRate", "effect", "Steps", "$", "Latency", "Recov", "越权率",
    "tokens_prompt", "tokens_completion", "pass^3_tasks_with_3_runs", "overreach_observable_runs",
    "unsettled_runs", "unbounded_requests", "budget_exhausted_runs",
    #: 红队 5.1 finding D2：`effect` 是均值，`None` 不进均值 —— 10 个 run 里只有 1 个算得出
    #: 与 10 个都算得出，在表上是**同一个数**。分子的样本量必须与那个数并排。
    "effect_settled_runs",
    #: 红队 5.1 finding E1：四条版本轴。混了就写 `MIXED:a|b`，不静默合并。
    *VERSION_AXES,
)


# ------------------------------------------------------------------ 空值词汇（⑪）

#: **没有读数**：这一格的 run 全部落在「拒绝 / 诚实终止 / 未结算 / 预算截断」四类里。
#: 三种格式各自的写法：CSV 与 Markdown 写这个字符本身，LaTeX 写 `---`。
NO_READING: str = "\u2014"                       # EM DASH
#: **不可观测**：这一格有可用的 run，但这个量在这些 run 上检不了
#: （网关日志不可得、基准价不在事件链里、旧版 scorer 没产出这个量……）。
#: **与 0 不同，也与 `NO_READING` 不同** —— 0 是「测了，是零」，`—` 是「没有读数」，
#: `unobservable` 是「这次根本测不了」。三者混在一起，恒绿的门就看不出来了。
UNOBSERVABLE: str = "unobservable"

#: **不适用**：这个量在这一阶段**根本不定义**（全量阶段表是「阶段 × 全部指标」的宽表，
#: 某一阶段不定义的列就是一个不适用的格）。**与「空」不同** —— 空的定义是
#: 「这一格一个 run 都没有」（规格 §9.0）。两者同形的话，「S3 没有 Prov 这个量」
#: 与「S3 一道题都没跑」在表上读起来一模一样（红队 V2.rt finding 7）。
NOT_APPLICABLE: str = "n/a"

#: 四类「没有读数」的原因（⑪）。顺序即判定优先级（红队 V2.rt finding 1 之后：诚实终止判在最前）。
WITHHELD_REASONS: tuple[str, ...] = ("honest_halt", "budget_exhausted", "rejected", "unsettled")


def withheld_reason(r: dict) -> str | None:
    """这条 run 为什么给不出读数；给得出就是 None。

    * `honest_halt` —— 题面欠定、产物如实标 unresolved 并停下（`correct_handling`）。
      **判在最前**（红队 V2.rt finding 1）：诚实终止的 run 往往**同时**带一条预算记录 ——
      它把预算用到闸上才如实停下。先判 `budget` 会把全库唯一一条真诚实终止
      （`m6/s7-rob-02.strict.cfg-codex-deepseek.r01`）判成预算截断，于是
      `honest_halt_rate` 这一列在全库每一行都是 0.0 —— **结构上恒为 0 的列**
      看不出是恒绿还是真零，正好把规格 §9.3「它高不是坏事」那句话变成读不出来的假话。
      判据来源也因此与规格 §9.3 的「数据源 = `record.correct_handling`」对上了。
    * **给得出读数的 run 不在这四类里**：闸门 `valid` 且 `l3_pass` 有值就是有读数，
      哪怕它路上撞过预算闸。这是本函数第一行 docstring 的原义，之前没落到代码里 ——
      一条有读数的 run 被判成「没有读数」，会让本来该是 `unobservable` 的格子写成 `—`。
    * `budget_exhausted` —— 边车真的发过 429（记录里的 `budget`），或状态就是预算耗尽。
      **判在拒绝之前**：撞闸的 run 多半没交产物，不先判它就会被算成「拒绝」。
    * `rejected` —— 闸门判 invalid（含 malformed），或压根没有可评分产物（交白卷 / harness 错）。
    * `unsettled` —— 有可评分产物、闸门也过了，但判据在 v1 没有输入（`l3_pass is None`）。
    """
    if r.get("correct_handling") is True:
        return "honest_halt"
    if r.get("validity") == "valid" and r.get("l3_pass") is not None:
        return None
    if r.get("budget") or r.get("run_status") == "budget_exhausted":
        return "budget_exhausted"
    if r.get("validity") == "invalid" or r.get("malformed") is True:
        return "rejected"
    try:
        if FM.sr_bucket(str(r.get("run_status"))) != "scorable":
            return "rejected"
    except Exception:                                             # noqa: BLE001
        pass
    if r.get("l3_pass") is None:
        return "unsettled"
    return None


def _numeric(v) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


#: 主表十六个阶段列 → `(阶段, 取数方式, 键)`。
#: 取数方式：`correctness` 取 `record.correctness[键]`；`probe` 取 `record.probe_states[键]`
#: 的三态（clean=1 / violation=0 / unobservable=不可观测）；`overreach` 取 `record.overreach`
#: 的 Σ拒绝/Σ请求（**比率要合并分子分母，不是对逐 run 的比率取均值**）。
STAGE_COLUMN_SOURCES: tuple[tuple[str, str, str, str], ...] = (
    ("Cov",    "S1", "correctness", "Cov"),
    ("Prov",   "S1", "correctness", "Prov"),
    #: ⑥-c：S2 的保真列 = `CellAgree`，不是 `Align`。两者**会分叉，而分叉的方向对被测方有利**：
    #: `ops/reports/i_rehearsal_v2/scores/s2-cor-01.strict.cfg-codex-deepseek.r02.score.json`
    #: 里 `Align = 1.0`（字段全映对了）而 `CellAgree = 0.0`（一个格都没对上）——
    #: 主表放 `Align` 的话，这一行读起来是「S2 做对了」，而它一个数都没算对。
    #: `Align` 没有被删：它照旧进 `l3_pass` 判据、照旧在全量阶段指标表里（规格 §9.2 S2）。
    ("Cell%",  "S2", "correctness", "CellAgree"),
    ("Adj",    "S2", "correctness", "Adj"),
    ("Fid",    "S3", "correctness", "fid_day_rate"),
    ("Decl",   "S3", "correctness", "Decl"),
    ("IC-agr", "S4", "correctness", "within_band_rate"),
    ("Set",    "S4", "correctness", "Set"),
    ("Sig",    "S5", "correctness", "Sig"),
    (RHO_BAR,  "S5", "correctness", "rho_mean"),
    ("W-agr",  "S6", "correctness", "WeightAgree"),
    ("Cons",   "S6", "correctness", "Cons"),
    (EPS_AGR,  "S7", "correctness", "within_band_rate"),
    ("Ledger", "S7", "probe",       "ledger_conservation"),
    ("Audit",  "S8", "correctness", "Audit"),
    ("Ovr",    "S8", "overreach",   ""),
)


def cell_from(rs: list[dict], how: str, key: str):
    """一格：数值 / `NO_READING` / `UNOBSERVABLE` / `None`（这一格一个 run 都没有）。"""
    if not rs:
        return None
    vals: list[float] = []
    num = den = 0
    withheld = 0
    for r in rs:
        if how == "overreach":
            o = r.get("overreach")
            if isinstance(o, dict) and int(o.get("total") or 0) > 0:
                num += int(o.get("denied") or 0)
                den += int(o.get("total") or 0)
                continue
        elif how == "probe":
            st = (r.get("probe_states") or {}).get(key)
            if st in ("clean", "violation"):
                vals.append(1.0 if st == "clean" else 0.0)
                continue
        elif r.get("validity") == "valid":
            #: 正确性量**只取闸门过了的 run**（与 `table_b` 同口径）：闸门失败时效果分
            #: 不产出（不是低分），把 invalid 的 run 的 correctness 混进均值等于给作弊留分。
            #: 探针态与越权率不受这条限制 —— 它们是 L1 的事实，不是效果分。
            v = _numeric((r.get("correctness") or {}).get(key))
            if v is not None:
                vals.append(v)
                continue
        withheld += int(withheld_reason(r) is not None)
    if how == "overreach":
        if den:
            return num / den
    elif vals:
        return sum(vals) / len(vals)
    #: 一个读数都没有。全是四类原因 → `—`；否则这个量在这些 run 上**检不了** → unobservable。
    return NO_READING if withheld == len(rs) else UNOBSERVABLE


def stage_columns(rs: list[dict]) -> dict:
    """主表的十六个阶段列。分阶段切片 —— S4 的列只看 S4 的 run。"""
    by_stage: dict[str, list[dict]] = defaultdict(list)
    for r in rs:
        if _in_denominator(r):
            by_stage[str(r.get("stage"))].append(r)
    return {col: cell_from(by_stage.get(stage, []), how, key)
            for col, stage, how, key in STAGE_COLUMN_SOURCES}


def headline_cell(value, rs: list[dict]):
    """`SR` / `P@1` 这种全阶段列：算得出就是数；算不出时按四类原因判 `—`，否则 unobservable。"""
    if value is not None:
        return value
    counted = [r for r in rs if _in_denominator(r)]
    if not counted:
        return None
    return NO_READING if all(withheld_reason(r) is not None for r in counted) else UNOBSERVABLE


#: 表上写不下 64 位十六进制。`runner_version` 与 `image_digest` 缩成前 12 位 + `…`
#: （全仓一贯的写法，例如冻结门的「记录 111d763b10eeb83f…」）。
#: **完整值留在 `records.json` 里** —— 表是给人读的，记录才是证据。
_HEXISH = "0123456789abcdef"


def _short_version(v: str) -> str:
    """哈希形态的版本轴缩写；`1.0.12` / `r1.0.19` 这种短版本号原样返回。"""
    if "@sha256:" in v:
        name, _, dig = v.partition("@sha256:")
        return f"{name}@sha256:{dig[:12]}…" if len(dig) > 12 else v
    if len(v) > 16 and all(c in _HEXISH for c in v.lower()):
        return v[:12] + "…"
    return v


def _in_denominator(r: dict) -> bool:
    """这条 run 进不进比率类的分母：**只排除 `unscorable_harness`**（与 SR 同口径）。

    认不出的 `run_status`（历史数据里可能有已经改名的状态）**留在分母** —— 与 `arm_kind`
    同一条纪律：报告器读的是旧记录，「这份旧数据画不出来了」不是报告器该做的裁定；
    而默默把它移出分母会抬高比率，方向对我们有利，正是最该防的那种。
    """
    try:
        return FM.sr_bucket(str(r.get("run_status"))) not in FM.EXCLUDED_FROM_DENOMINATOR
    except Exception:                                             # noqa: BLE001
        return True


def version_cell(rs: list[dict], axis: str) -> str | None:
    """这一组 run 在某条版本轴上的取值：唯一就写它，混了就写 `MIXED:a|b`，全缺就 None。

    红队 5.1 finding E1（视角⑥）：`ops/reports/m6_all` 是 m6（题面 `1.0.7` / 参考 `r1.0.8`）
    与 m6b（`1.0.9` / `r1.0.14`）合出来的，`table_a` 按 `(config_id, arm)` 分组 ——
    **两个题面版本的 run 合成了同一行 pass@1**，而表上没有一列说得出这件事。
    这里不替调用方拒绝，只把事实写在表上：`MIXED:` 一出现，那一行就不是一个可比的读数。
    """
    vals = sorted({_short_version(str(r[axis])) for r in rs if r.get(axis) not in (None, "")})
    if not vals:
        return None
    return vals[0] if len(vals) == 1 else "MIXED:" + "|".join(vals)


def pass_hat_k(c: int, n: int, k: int) -> float | None:
    """τ-bench 的 pass^k 无偏估计 C(c,k)/C(n,k)。n < k 时**无定义**（返回 None，不是 0）。"""
    if k <= 0 or n < k:
        return None
    if c < k:
        return 0.0
    return comb(c, k) / comb(n, k)


def _mean(xs: Iterable[float | None]) -> float | None:
    v = [x for x in xs if x is not None]
    return (sum(v) / len(v)) if v else None


def _succ(r: dict) -> float | None:
    """succ ∈ {0, 1}；**None = 本题本版结算不了**（不是失败）。

    `l3_pass is None` 的合法来源只有一种：判据在 v1 上没有输入 —— 例如 S4 的 IC 族**没有标定 ε 带**
    （`calibration.json` 只标了回测指标）。把它记 0 等于说「这次运行错了」，而事实是「我们没法判」。
    未结算的运行不进 pass@1 / pass^k 的分子**也不进分母**，单列 `unsettled_runs` 报出来 ——
    藏起来的话，主表上「S4 全 0」会被读成模型不行。
    """
    if r.get("sr_bucket") != "scorable":
        return 0.0                                       # 没有可评分产物 = 没成功，这是判得了的
    if r.get("validity") != "valid":
        return 0.0                                       # 闸门失败 = invalid，判得了
    if r.get("correct_handling") is True:                # 诚实终止：正确处理即成功
        return 1.0
    if r.get("l3_pass") is None:
        return None
    return 1.0 if r.get("l3_pass") is True else 0.0


def _structure_pass(r: dict) -> float:
    return 1.0 if (r.get("sr_bucket") == "scorable" and not r.get("malformed")) else 0.0


def arm_kind(arm: str) -> str:
    """臂的 `kind`（`genetask/arms.yaml`）。认不出的臂记 `unknown` —— **不抛**：
    报告器读的是历史 run 的记录，里面可能有已经从注册表里删掉的臂名，
    而「这份旧数据画不出来了」不是报告器该做的裁定。
    """
    try:
        from genetask.bundle import ARM_BY_ID
    except Exception:                                             # noqa: BLE001
        return "unknown"
    a = ARM_BY_ID.get(str(arm))
    return a.kind if a else "unknown"


def waived_rules_for(kind: str) -> tuple[str, ...]:
    """该 kind 免掉的等价规则码（公平性协议 §6.6.2）。`instruction_variant` 之外恒空。
    与 `genetask.render.WAIVED_FOR_VARIANT` **同源** —— 表上写的免例与建题时真的免掉的
    是同一份清单，不是这里再抄一遍。
    """
    if kind != "instruction_variant":
        return ()
    try:
        from genetask.render import WAIVED_FOR_VARIANT
    except Exception:                                             # noqa: BLE001
        return ()
    return tuple(WAIVED_FOR_VARIANT)


def table_a(records: list[dict], *, k: int = 3) -> list[dict]:
    by_cfg: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in records:
        by_cfg[(r["config_id"], r["arm"])].append(r)
    rows = []
    for (cfg, arm), rs in sorted(by_cfg.items()):
        by_task: dict[str, list[dict]] = defaultdict(list)
        for r in rs:
            by_task[r["task_id"]].append(r)
        sr_t, p1_t, pk_t, prog_t = [], [], [], []
        unsettled = 0
        for tid, trs in by_task.items():
            statuses = [r["run_status"] for r in trs]
            denom = FM.sr_denominator(statuses)
            counted = [r for r in trs if FM.sr_bucket(r["run_status"]) not in FM.EXCLUDED_FROM_DENOMINATOR]
            if denom == 0:
                continue                                  # 这题全是 harness 错：不进任何均值
            sr_t.append(sum(1 for r in counted if r["sr_bucket"] == "scorable") / denom)
            succ = [_succ(r) for r in counted]
            settled = [x for x in succ if x is not None]
            unsettled += len(succ) - len(settled)
            if settled:                                   # 一条都判不了的题不进 pass@1（不是记 0）
                p1_t.append(sum(settled) / len(settled))
                pk = pass_hat_k(int(sum(settled)), len(settled), k)
                if pk is not None:
                    pk_t.append(pk)
            prog_t.append(sum(_structure_pass(r) for r in counted) / denom)
        steps = _mean(r.get("steps") for r in rs)
        latency = _mean(r.get("latency_s") for r in rs)
        recov_pool = [r for r in rs if r.get("validator_rejections") not in (None, 0)]
        recov = (sum(1 for r in recov_pool if r.get("validity") == "valid") / len(recov_pool)) if recov_pool else None
        ov = [r["overreach"] for r in rs if isinstance(r.get("overreach"), dict)]
        ov_total = sum(o["total"] for o in ov)
        overreach = (sum(o["denied"] for o in ov) / ov_total) if ov_total else None
        tp = [r.get("tokens_prompt") for r in rs if r.get("tokens_prompt") is not None]
        tc = [r.get("tokens_completion") for r in rs if r.get("tokens_completion") is not None]
        #: 「一次都没有」与「日志不可得」必须分开：前者是 0，后者是 None（红队 5.rt finding 3）。
        ub = [x for x in (r.get("unbounded_requests") for r in rs) if isinstance(x, int)]
        rows.append({
            #: `arm_kind`（§6.6.3）：instruction_variant 臂与 protocol 臂**不同轴**，
            #: 主表要分块，块首写明它免了哪些等价规则 —— 见 `to_latex`。
            "config_id": cfg, "arm": arm, "arm_kind": arm_kind(arm),
            "n_tasks": len(by_task), "n_runs": len(rs),
            "SR": _mean(sr_t), "pass@1": _mean(p1_t), f"pass^{k}": _mean(pk_t),
            "ProgressRate": _mean(prog_t), "Steps": steps,
            #: 卡 1.5：由 `runner.pricing.cost_usd` 逐 run 算好后放进记录，这里只取均值。
            #: `_mean` 对全 None 返回 None —— 空列与 0 在主表上含义相反。
            "$": _mean(r.get("cost_usd") for r in rs), "Latency": latency,
            "Recov": recov, "越权率": overreach,
            "tokens_prompt": (sum(tp) if tp else None), "tokens_completion": (sum(tc) if tc else None),
            f"pass^{k}_tasks_with_{k}_runs": len(pk_t), "overreach_observable_runs": len(ov),
            "unsettled_runs": unsettled, "effect": _mean(r.get("effect") for r in rs),
            #: 没界定右端的取数请求（遥测）：**总数**而不是均值 —— 它是行为计数，不是比率。
            #: 红队 5.rt finding 3：旧写法 `(sum(...) or None)` 把**真值 0** 翻成 None，
            #: 落到 CSV 是空串、落到 LaTeX 是 `---` —— 与「网关日志不可得」完全同形。
            #: 一个一次都没发过无右端取数请求的 agent（正是我们想看到的好结果），
            #: 在表上长得跟「我们看不见」一模一样。三态按**有没有可用样本**判，
            #: 与同一函数里 `tokens_prompt` / `tokens_completion` 的写法对齐。
            "unbounded_requests": (sum(ub) if ub else None),
            #: 撞了预算闸的 run 数（N-130）：与「交白卷」分开报，否则主表读不出是谁把它停下的。
            #: 红队 5.rt finding 2：判据是**边车真的发过 429**（记录里的 `budget`，
            #: `scorer.score_run.budget_exhausted` 只在那时才写非 None），不是 `run_status` ——
            #: 撞了闸但**已经把 artifact 写下来**的 run，`run_status` 是 `ok`，而它同样是被
            #: 预算停下的。v1demo 实测 8 个 run 全部撞了 600k token 闸，旧口径两臂各写 3，
            #: 真值是 4/4，而漏掉的那两个恰是全表仅有的两个进了 pass@1 分子的 run。
            #: 口径与 `ops.results_db.enrich` 的 `budget_exhausted` 同源；旧记录没有
            #: `budget` 键时退回状态口径，**只多不少**。
            "budget_exhausted_runs": sum(1 for r in rs if r.get("budget")
                                         or r.get("run_status") == "budget_exhausted"),
            #: `effect` 那个均值是几个 run 上算出来的。
            "effect_settled_runs": sum(1 for r in rs if r.get("effect") is not None),
            **{ax: version_cell(rs, ax) for ax in VERSION_AXES},
        })
        #: ⑩ 的十九列。`pass@1` / `SR` 的**原值**留在行里（诊断列与历史测试读它），
        #: 发布列 `P@1` / `SR` 另按四态词汇出 —— 主表上 `None` 是「这一格没有 run」，
        #: 而「有 run 但没有读数」必须写成 `—`，两件事在表上不能同形。
        row = rows[-1]
        #: `SR` / `pass@1` 的**原值**（数或 None）一个字不动 —— 历史 CSV 按它逐格比。
        #: 主表要的四态写法由 `main_table()` 在**出表时**套上去：
        #: 「有 run 但没有读数」在主表上写 `—`，在 Table A 上仍是空。
        row["P@1"] = headline_cell(row["pass@1"], rs)
        row["unobservable_probes_mean"] = _mean(len(r.get("unobservable") or []) for r in rs)
        row.update(stage_columns(rs))
    return rows


def main_table(records: list[dict], *, k: int = 3) -> list[dict]:
    """**主表**（⑩）：身份列 + 固定十九列，一列不多一列不少。

    行还是 `table_a` 出的那一份 —— 聚合口径**只有一处**。这里只做两件事：
    ① 把列选成发布口径；② 给 `SR` 套上四态词汇（`P@1` 与十六个阶段列在 `table_a` 里已经套过）。

    `$` 不套：它是遥测，不是判据。一次被闸门拒的运行照样花了钱，把它的成本写成 `—`
    等于说这笔钱没花 —— 缺价或缺 usage 时它仍然是空（`None`），口径见 `ops/reports/report_spec_v1.md`。
    """
    by_cfg: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in records:
        by_cfg[(r["config_id"], r["arm"])].append(r)
    out: list[dict] = []
    for row in table_a(records, k=k):
        rs = by_cfg[(row["config_id"], row["arm"])]
        cells = {c: row.get(c) for c in TABLE_A_INDEX_COLUMNS}
        for c in MAIN_TABLE_COLUMNS:
            cells[c] = headline_cell(row.get("SR"), rs) if c == "SR" else row.get(c)
        out.append(cells)
    return out


def table_b(records: list[dict]) -> list[dict]:
    """各阶段 correctness 指标（§3 的 30 列口径里 v1 已能结算的那些）：按 (config, arm, stage) 对 **valid** 运行取均值；
    另报 invalid 率、诚实终止数与 unobservable 族数。"""
    by: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for r in records:
        by[(r["config_id"], r["arm"], r["stage"])].append(r)
    rows = []
    for (cfg, arm, stage), rs in sorted(by.items()):
        valid = [r for r in rs if r.get("validity") == "valid"]
        metrics: dict[str, list[float]] = defaultdict(list)
        for r in valid:
            for key, val in (r.get("correctness") or {}).items():
                if isinstance(val, (int, float)) and not isinstance(val, bool):
                    metrics[key].append(float(val))
        #: 分母与 SR 同口径：**只排除 `unscorable_harness`**（`failure_modes.EXCLUDED_FROM_DENOMINATOR`）。
        #: 红队 5.1 finding D3：旧写法拿 `len(rs)` 当分母，harness 自己坏掉的那些 run
        #: `validity` 是 None，进不了分子却占着分母 —— 于是「harness 越不稳，invalid 率看起来越低」。
        #: 两个 run、一个 harness 错一个 invalid，真实的 invalid 率是 1.0，旧口径给 0.5。
        denom_rs = [r for r in rs if _in_denominator(r)]
        row: dict[str, Any] = {"config_id": cfg, "arm": arm, "arm_kind": arm_kind(arm),
                               "stage": stage, "n_runs": len(rs), "n_runs_denom": len(denom_rs),
                               "invalid_rate": (sum(1 for r in denom_rs if r.get("validity") == "invalid") / len(denom_rs)) if denom_rs else None,
                               "honest_halts": sum(1 for r in rs if r.get("correct_handling") is True),
                               "unobservable_probes_mean": _mean(len(r.get("unobservable") or []) for r in rs),
                               **{ax: version_cell(rs, ax) for ax in VERSION_AXES}}
        for key in sorted(metrics):
            row[key] = _mean(metrics[key])
        rows.append(row)
    return rows


def write_csv(rows: list[dict], path: Path, columns: tuple[str, ...] | None = None) -> Path:
    cols = list(columns) if columns else sorted({k for r in rows for k in r}, key=lambda k: (k not in TABLE_A_COLUMNS, k))
    path = Path(path)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: ("" if r.get(c) is None else r.get(c)) for c in cols})
    return path


def _tex_escape(s: str) -> str:
    return (str(s).replace("\\", r"\textbackslash{}").replace("_", r"\_").replace("%", r"\%")
            .replace("&", r"\&").replace("#", r"\#").replace("$", r"\$").replace("^", r"\^{}"))


def _fmt(v, digits: int) -> str:
    #: 三态在 LaTeX 里的写法（⑪）：`—` 写 `---`，`unobservable` 写成斜体的原词
    #: （**不是** `---` —— 「没有读数」与「检不了」是两件事）。
    #: `None`（这一格没有 run）沿用 `---`：LaTeX 表上它与 `—` 同形，要分开看 CSV。
    if v == NO_READING:
        return "---"
    if v == UNOBSERVABLE:
        return r"\textit{unobservable}"
    if v == NOT_APPLICABLE:
        #: 第五态（红队 V2.rt finding 7）：不适用。与 `unobservable` 同样用斜体原词 ——
        #: 它们都是「这里没有数」的**原因**，写成 `---` 就与「没有 run」混了。
        return r"\textit{n/a}"
    if v is None or v == "":
        return "---"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, float):
        return f"{v:.{digits}f}"
    return _tex_escape(v)


#: 分块顺序。参照臂在最前 —— 后面每一块都是「与它比」的结果。
ARM_KIND_ORDER: tuple[str, ...] = ("baseline", "protocol", "instruction_variant", "unknown")

#: 每一块的块首（§6.6.3 要求块首说明这一块是什么）。
ARM_KIND_BLOCK_HEAD: dict[str, str] = {
    "baseline": "参照臂（baseline）",
    "protocol": "协议臂（protocol）—— 与参照臂的差异是投放的工件",
    "instruction_variant": "指令变体臂（instruction_variant）—— 差异在题面措辞，"
                           "与工件层的干预不同轴，不与协议臂并排读（§6.6.3）",
    "unknown": "臂注册表里认不出的臂（历史数据）",
}


#: **适配赛道把主赛道规定题的 oracle 产物送上了执行面**（2026-09-10 用户裁定 N-348）。
#: 这句话要跟着**每一张**结果表走 —— 适配表与主表都要带：读主表的人必须知道，
#: 一个跑过适配赛道的被测方在这些题上「可能已见过答案」。
ADAPT_ORACLE_EXPOSURE_NOTE = (
    "脚注（N-348，2026-09-10 用户裁定）：适配赛道 v1.0-adapt 的题源是**出集规定题的 oracle 产物**"
    "（探针题不入），这些产物随适配 bundle 进入执行面。**跑过适配赛道的被测方，主赛道这些题算"
    "「可能已见过答案」**；口径与逐题清单见 ops/specs/fairness_protocol.md §7 与 "
    "ops/reports/known_limits_v1.md。")


def to_latex(rows: list[dict], columns: tuple[str, ...], *, caption: str, label: str,
             digits: int = 3, block_by_kind: bool | None = None,
             footnote: str | None = ADAPT_ORACLE_EXPOSURE_NOTE) -> str:
    """booktabs 表。空值写 `---`（不是 0）。本仓库没有 `gen_v6`（实施稿卡 5.3 提到的现有脚本不在仓内，
    见 tickets），这里是最小可用的替代出口，列选择由调用方给。

    `block_by_kind`（公平性协议 §6.6.3，红队 2026-09-07 finding 4）：按 `arm_kind` 分块，
    `instruction_variant` 块的块首逐条写出它免了哪些等价规则。
    `None` = **自动**：每一行都带 `arm_kind` 且不止一种 kind 时分块。

    为什么这条不能只写在协议里：`hint` 这类臂与参照臂的差异**只是一句话**，
    把它排进协议臂那一列，读者会把「提示涨了 3 分」读成「协议涨了 3 分」。
    """
    kinds = [r.get("arm_kind") for r in rows if r.get("arm_kind")]
    if block_by_kind is None:
        block_by_kind = bool(rows) and len(kinds) == len(rows) and len(set(kinds)) > 1
    align = "l" * sum(1 for c in columns if c in ("config_id", "arm", "arm_kind", "stage")) + \
            "r" * sum(1 for c in columns if c not in ("config_id", "arm", "arm_kind", "stage"))
    head = " & ".join(_tex_escape(c) for c in columns) + r" \\"

    def _line(r: dict) -> str:
        return " & ".join(_fmt(r.get(c), digits) for c in columns) + r" \\"

    if not block_by_kind:
        body = "\n".join(_line(r) for r in rows)
    else:
        present = [k for k in ARM_KIND_ORDER if k in set(kinds)]
        present += sorted({str(k) for k in kinds} - set(ARM_KIND_ORDER))
        chunks: list[str] = []
        for k in present:
            sub = [r for r in rows if r.get("arm_kind") == k]
            if not sub:
                continue
            title = ARM_KIND_BLOCK_HEAD.get(k, f"kind = {k}")
            waived = waived_rules_for(k)
            if waived:
                title += "；免掉的等价规则：" + " ".join(waived)
            if chunks:
                chunks.append(r"\midrule")
            chunks.append(f"\\multicolumn{{{len(columns)}}}{{l}}"
                          f"{{\\textit{{{_tex_escape(title)}}}}}" + r" \\")
            chunks += [_line(r) for r in sub]
        body = "\n".join(chunks)
    # **脚注进 caption**（N-348）：进 caption 而不是表尾，是因为表尾那行会被复制表格的人裁掉，
    # 而 caption 跟着表走。给 `footnote=None` 可以关掉 —— 但关掉之前先想清楚谁会读这张表。
    if footnote:
        caption = f"{caption}　{footnote}"
    return "\n".join([
        r"\begin{table}[t]", r"\centering", f"\\caption{{{_tex_escape(caption)}}}", f"\\label{{{label}}}",
        f"\\begin{{tabular}}{{{align}}}", r"\toprule", head, r"\midrule", body, r"\bottomrule",
        r"\end{tabular}", r"\end{table}", ""])


def load_records(paths: Iterable[Path]) -> list[dict]:
    out = []
    for p in paths:
        d = json.loads(Path(p).read_text(encoding="utf-8"))
        out.append(d["record"] if "record" in d else d)
    return out


# ============================================================== 适配赛道（卡 4.2-a）

#: 适配赛道表的列。计数与比例并列 —— 只给比例的话，10 例里 1 例与 100 例里 10 例在表上同形。
TABLE_ADAPTATION_COLUMNS: tuple[str, ...] = (
    "config_id", "arm", "level", "n",
    "first_pass", "repaired_pass", "correct_flag", "blocked", "failed",
    "first_pass_rate", "repaired_pass_rate", "correct_flag_rate", "blocked_rate", "failed_rate",
    "resolved_rate", "as_expected_rate", "validator_rejections_mean",
    #: 四条版本轴（红队 W.rt finding 8）。Table A 一直带着它们，适配表此前一条都没有 ——
    #: 于是这张表**看不出它是在哪一版题面与哪一版参考轴上算出来的**，与 `VERSIONS.md` §2
    #: 记作「一次真事故」的 m6_all 混轴表同形。`set_version` / `reference_version` 由
    #: `ops/reports/adapt/adapt_report.py::axes_for` 作为**声明值**写进结果库；
    #: `runner_version` / `image_digest` 适配赛道的记录里没有，按空值出（LaTeX 写 `---`）。
    *VERSION_AXES,
    # **每一行都带这条脚注**（N-348）。CSV 没有「表尾注」这种东西，而这句话不能只活在 .tex 里：
    # 读 table.csv 的人和读 table.tex 的人要看到同一件事。
    "note",
)


def table_adaptation(records: list[dict], *, levels: tuple[str, ...] = ("L1", "L2", "L3")) -> list[dict]:
    """适配赛道：按 (config, arm, level) 数五类结局 + 比例；每个 (config, arm) 另出一行 `level="ALL"`。

    口径（`scorer/adaptation.py`）：`first_pass` 首次通过 / `repaired_pass` 修复后通过 /
    `correct_flag` 正确标记（L3 专属）/ `blocked` 拦截 / `failed` 失败。

    * `resolved_rate` = (首次通过 + 修复后通过 + 正确标记) / n —— 「这份上游产物最后接进来了吗」；
      **拦截不算失败也不算成功**：正确地拒绝一份修不了的产物是协议要的行为，把它计进分子会奖励硬修。
    * `as_expected_rate` = 结局 == 该例 `expected_outcome` 的比例（L1/L2 期望首次通过，L3 期望正确标记）。
    * `validator_rejections_mean` 只在**有** validator.log 的运行上取均值（裸臂没有这条回路 → 不进分母，
      与 Table A 的 `Recov` 同一条空值纪律）。
    """
    from scorer.adaptation import OUTCOMES

    def _row(cfg: str, arm: str, level: str, rs: list[dict]) -> dict:
        n = len(rs)
        row: dict[str, Any] = {"config_id": cfg, "arm": arm, "level": level, "n": n}
        counts = {o: sum(1 for r in rs if r.get("outcome") == o) for o in OUTCOMES}
        for o in OUTCOMES:
            row[o] = counts[o]
            row[f"{o}_rate"] = (counts[o] / n) if n else None
        row["resolved_rate"] = ((counts["first_pass"] + counts["repaired_pass"]
                                 + counts["correct_flag"]) / n) if n else None
        row["as_expected_rate"] = (sum(1 for r in rs
                                       if r.get("expected_outcome") is not None
                                       and r.get("outcome") == r.get("expected_outcome")) / n) if n else None
        row["validator_rejections_mean"] = _mean(r.get("validator_rejections") for r in rs)
        for ax in VERSION_AXES:                           # 红队 W.rt finding 8：轴跟着表走
            row[ax] = version_cell(rs, ax)
        row["note"] = ADAPT_ORACLE_EXPOSURE_NOTE          # N-348：脚注跟着表走
        return row

    by: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in records:
        by[(r["config_id"], r["arm"])].append(r)
    rows: list[dict] = []
    for (cfg, arm), rs in sorted(by.items()):
        for level in levels:
            sub = [r for r in rs if r.get("level") == level]
            if sub:
                rows.append(_row(cfg, arm, level, sub))
        rows.append(_row(cfg, arm, "ALL", rs))
    return rows
