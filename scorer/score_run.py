"""线 C 的入口（2026-09-05）：一个从 f02 拉回数据面的 run 目录 + 一个题目录 → 一份 scorer 输出 + 一条主表记录。

顺序照卡 4.2 §3：harvest（采集 + 可见性三态）→ classify（run_status）→ gate（校验器 + 三态）
→ L3（按 tolerance.kind）→ scorer 输出（过 `validate_scorer_output`，过不了就抛——半成品不许进主表）。

* run_status 的分类表是 `runner.c42.failure_modes`（不手抄一份）；
* **效果分 = 两桩锚定归一**（裁定 2026-09-05）：`100 × (agent − null) / (oracle − null)`，夹 [0, 100]。
  底 = 该题 null_agent 产物的同一判据标量，顶 = oracle 产物的（自比，按构造为 1）。
  `invalid` / 诚实终止 / **锚点退化**（两端同分或某端算不出）时 effect 为 **null**，不是 0。
  这不是卡 5.4：那张卡是**替换基线阶梯**（多档基线），仍未落地（`anchor_ladder_54=false`）；
  这里只有两桩，判据与公式由本次裁定给定，`anchor_status` 因此取题面的 `anchor.status`（各题都是 `fixed`）。
* `$`（`cost_usd`）：网络侧 usage × `runner/pricing.yaml` 的价（卡 1.5）。**缺价或缺 usage 就是 None，不是 0。**
  DeepSeek 分高峰/低谷两档而边车不记落在哪一档，价目表取高峰价 —— 这个数因此是**成本上界**，不是账单实数。
* 遥测：Steps / tokens 取**网络侧**（边车的 llm trace，`runner.c42.llm_trace`），Latency 取 runner 侧 `run.json`，
  Recov 取 GQ 臂的 `work/protocol/validator.log`，越权率取边车 `log/egress.jsonl` 里带状态码的转发事件；
  没有就是 None。

用法：
    python -m scorer.score_run --run <run_dir> --task <task_dir> --out <dir>
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import yaml

from reference import artifact_schema as ASch
from reference.artifact_schema import validate_scorer_output
from runner.c42 import failure_modes as FM
from runner.c42 import harvest as HV
from runner.c42 import llm_trace as LT
from runner import pricing as PR
from runner import registry as REG
from runner.c42 import visibility as VIS
from ops import report_io as RIO
from scorer import gate as G
from scorer import l3 as L3
from scorer.l3 import L3Result

REPO = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "1.0"


class ScoreError(RuntimeError):
    pass


#: 一条记录的**四条版本轴**（红队 5.1 finding E1/E2）。全部取自 `inject.json` —— 那是 runner
#: 在投放时盖的章，不是产物自报的东西。
#:
#: 为什么必须逐条落进记录：`ops/reports/m6_all` 就是 m6（`1.0.7` / `r1.0.8`）与 m6b
#: （`1.0.9` / `r1.0.14`）合出来的，`table_a` 按 `(config_id, arm)` 分组，两个题面版本、
#: 两个参考实现版本的 run **合成了同一行 pass@1**，而表上没有任何一列说得出这件事。
#: 记录里连字段都没有，事后也切不开 —— 只能重跑。
VERSION_AXES: tuple[str, ...] = ("set_version", "reference_version", "runner_version", "image_digest")


def version_axes(inj: dict) -> dict[str, str | None]:
    """从 `inject.json` 取四条版本轴。缺就是 None（不填一个默认值假装一致）。"""
    fm = inj.get("frozen_manifest") or {}
    rm = inj.get("reference_manifest") or {}
    img = inj.get("image")
    return {"set_version": (fm.get("set_version") or None),
            "reference_version": (rm.get("reference_version") or None),
            "runner_version": (inj.get("runner_version") or None),
            "image_digest": (str(img) if img else None)}


def anchor_status_from_task(task: dict) -> str:
    """锚点状态取**题面**（`task.yaml` 的 `anchor.status`，各题都是 `fixed`）。

    2026-09-05 之前这里读 `ops/capabilities.json` 的 `anchor_ladder_54` —— 那把锁问的是
    **替换基线阶梯**（卡 5.4，多档基线）落地没有，而两桩锚定（null 底 / oracle 顶）不需要它。
    用错的锁会让所有题的 effect 永远 null，而「永远 null」与「本题算不出」不可分。
    """
    return str(((task.get("anchor") or {}).get("status")) or "pending")


def null_artifact(task_dir: Path) -> dict | None:
    """该题 null_agent 的产物（`ops/run_oracles.py --agent f1` 产出）。锚点的**底**。"""
    p = Path(task_dir) / "solution" / "artifact.null.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


_ANCHOR_CACHE: dict[tuple[str, str, str], dict] = {}

#: gold 的 payload 文件（`PAYLOAD_FILES[stage]`）可能落在哪一层。**顺序即优先级**。
#: 实测：S2 的面板在 `gold/`（r1.0.16 起），S3 的因子面板在 `work/`，早期 S2 还在题目录根。
GOLD_PAYLOAD_DIRS: tuple[str, ...] = ("gold", "work", "")


def gold_payload_dir(task_dir: Path, stage: str) -> Path | None:
    """gold 的 payload 文件真的在哪一层。找不到就 None（不猜一个）。"""
    from reference.artifact_schema import PAYLOAD_FILES
    names = [Path(f["path"]).name for f in PAYLOAD_FILES.get(stage, ())]
    if not names:
        return None
    for sub in GOLD_PAYLOAD_DIRS:
        d = Path(task_dir) / sub if sub else Path(task_dir)
        if any((d / n).is_file() for n in names):
            return d
    return None


def anchor(task_dir: Path, *, kind: str, stage: str, spec: dict, calib: dict | None) -> dict:
    """两桩锚点：`{"floor": …, "ceiling": …}`（同一判据标量，算不出就是 None）。按 (task_id, stage, kind) 缓存。"""
    key = (str(task_dir), stage, kind)
    if key in _ANCHOR_CACHE:
        return _ANCHOR_CACHE[key]
    gold, null = gold_artifact(task_dir), null_artifact(task_dir)
    out: dict = {"floor": None, "ceiling": None, "kind": "two_rung",
                 "floor_source": "null_agent", "ceiling_source": "oracle",
                 "formula": "100 × (agent − null) / (oracle − null)，夹 [0, 100]"}
    #: **oracle 自比要拿 oracle 自己的产物文件**（红队 5.1 finding D1）。
    #: 旧代码把自比的「agent 侧」写死成 `task_dir/"work"` —— 那是 agent 可见的输入目录。
    #: S2 的题目录根本没有 `work/`，于是 `CellAgree` 判 0.0、天花板 = (1+1+1+0)/4 = **0.75**，
    #: 而 agent 真跑拿到 1.0 → `raw = 1/0.75 > 1` → 夹成 **effect = 100**，`clamped: true` 是唯一的痕迹。
    #: 分母偏小对**所有** agent 一起生效：0.5 分的产物会被算成 66.7 而不是 50。
    gdir = gold_payload_dir(Path(task_dir), stage) or (Path(task_dir) / "work")
    out["ceiling_payload_dir"] = str(gdir)
    if gold is not None:
        # 顶 = oracle 自比。**不是**直接写 1.0：万一某个 kind 的自比不等于 1（例如 gold 自己就缺件），
        # 写死的 1.0 会把那件事藏起来，而藏起来的分母会让所有 agent 的 effect 一起偏低。
        c = L3.compare(kind, stage=stage, agent_artifact=gold, gold_artifact=gold, task=spec,
                       agent_dir=gdir, gold_dir=Path(task_dir) / "work", calib=calib)
        out["ceiling"] = c.score
    if null is not None and gold is not None:
        f = L3.compare(kind, stage=stage, agent_artifact=null, gold_artifact=gold, task=spec,
                       agent_dir=Path(task_dir) / "solution", gold_dir=Path(task_dir) / "work", calib=calib)
        out["floor"] = f.score
    _ANCHOR_CACHE[key] = out
    return out


def effect_of(l3: L3Result | None, anc: dict) -> tuple[dict | None, dict, str | None]:
    """`(effect, anchor_meta, withheld_reason)`。算不出就 `(None, …, "anchor_degenerate")` —— 不出 0。

    `effect` 里**只放有限数**（`validate_scorer_output` 逐值判型）；口径元数据放同级的 `anchor` 键。
    """
    if l3 is None or l3.score is None:
        return None, dict(anc), "anchor_degenerate"
    lo, hi = anc.get("floor"), anc.get("ceiling")
    if lo is None or hi is None or (hi - lo) <= 0:
        return None, dict(anc), "anchor_degenerate"
    #: 非有限的判据标量（nan / inf）**不出数**：`max(0.0, nan)` 在 Python 里返回 0.0，
    #: 于是「算出来是 NaN」会被静默夹成 **effect = 0**，与「真的一分没拿到」不可分。
    if not all(math.isfinite(float(x)) for x in (l3.score, lo, hi)):
        return None, {**anc, "nonfinite_anchor_or_metric": True}, "anchor_degenerate"
    raw = (l3.score - lo) / (hi - lo)
    if raw > 1.0 + 1e-9:
        #: 选手的判据标量高过 oracle 自比的天花板 —— 那不是「超常发挥」，是**天花板坏了**
        #: （红队 5.1 finding D1 就是这么发生的：ceiling=0.75，所有 ≥0.75 的产物一律夹成 100）。
        #: 夹到 100 会把坏掉的分母藏进一个漂亮的满分里；按锚点退化扣住，才看得见。
        return None, {**anc, "ceiling_below_agent": True, "raw_ratio": float(raw),
                      "metric_kind": l3.kind}, "anchor_degenerate"
    eff = {"score": round(100.0 * min(1.0, max(0.0, raw)), 4), "raw_metric": float(l3.score),
           "anchor_floor": float(lo), "anchor_ceiling": float(hi)}
    meta = {**anc, "clamped": not (0.0 <= raw <= 1.0), "metric_kind": l3.kind}
    return eff, meta, None


def gold_artifact(task_dir: Path) -> dict | None:
    for rel in ("solution/artifact.json", "gold/oracle_artifact.json"):
        p = task_dir / rel
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
    return None


def model_of(config_id: str) -> str | None:
    """这次运行用的 model id —— **只从 `runner.registry` 取**，不从产物或日志里认。

    `oracle` / `null_agent` 这类不在注册表里的 config_id → `None`（于是 `cost_usd` 也是 None）：
    它们根本没调模型，给它们编一个价等于在主表上凭空造一笔钱。
    """
    try:
        return REG.by_id(config_id).model
    except REG.RegistryError:
        pass
    # `enabled: false` 的 harness 配置（`PENDING_CONFIGS`）**也真的花了钱** —— 它们经边车
    # 指的就是 DeepSeek。不给它们模型，`cost_usd` 会是 None，而那个 None 与「上游拒绝、
    # 压根没有 usage」的 None 长得一模一样，结论却相反（卡 3.3：grok-cli 有 104 条 usage，
    # gemini-cli 一条都没有）。给了模型之后两者可分：前者出数，后者仍是 None 但 `cost_model` 有值。
    # 这些配置不进主表切片（切片键集是 `CONFIGS`），所以只影响各自那张接入验证表。
    for c in REG.PENDING_CONFIGS:
        if c.config_id == config_id:
            return c.model
    return None


def budget_exhausted(run_dir: Path) -> dict | None:
    """这次运行是不是**撞了我们的预算闸**（边车的 429）。返回 `{calls, tokens, max_*}` 或 None。

    判据取边车自己的记录（`log/llm_log.jsonl` 里 `decision=deny` 且带 `budget`）—— 那是闸门**执行**的地方，
    不是我们事后拿 `calls >= max_calls` 反推：反推会把「刚好用满但自己停了」也算成撞闸。
    """
    p = run_dir / "log" / "llm_log.jsonl"
    if not p.is_file():
        return None
    for line in reversed(p.read_text(encoding="utf-8", errors="replace").splitlines()):
        if not line.strip():
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("decision") == "deny" and int(e.get("status") or 0) == 429 and e.get("budget"):
            b = dict(e["budget"])
            b["detail"] = str(e.get("detail", ""))[:120]
            return b
    return None


def validator_rejections(run_dir: Path) -> int | None:
    """GQ 臂 validator 拒过几次（`n_violations > 0` 的行数）。没有日志 → None（裸臂没有这条回路）。"""
    p = run_dir / "work" / "protocol" / "validator.log"
    if not p.is_file():
        return None
    n = 0
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            n += int(json.loads(line).get("n_violations", 0) > 0)
        except (json.JSONDecodeError, TypeError, AttributeError):
            continue
    return n


def overreach_from_gateway_log(log: list[dict] | None) -> dict | None:
    """越权率的分子/分母 —— **网关日志**结算（指标规格 §1/§3：越权 = 被网关拒的请求 / 请求总数）。

    这是首选来源：网关是唯一持有「拒了没有、为什么拒」真值的一方，产物自报的 `overreach.denied_requests`
    只用来核对（`overreach_count_mismatch`）。日志不可得 → None（不可结算），**不是** 0：
    「一次都没越权」与「我们看不见」在主表上必须可分。
    """
    if log is None:
        return None
    from scorer.l3 import NON_DATA_PATHS
    data = [e for e in log if e.get("path") not in NON_DATA_PATHS]
    if not data:
        return None
    # **判据是 403，不是「被拒」**（契约 §6 写死：越权率 = 403 次数 / 请求总数，来源网关日志）。
    # 403 = 授权语义（「东西在，但你的视角下不该看/不该做」），422 = 语法错（参数写坏了）。
    # 把 422 算进越权率会让「参数拼错」与「想看未来」变成同一个数 —— 那两件事含义相反：
    # 一个是笨拙，一个是越界。422 单列成 malformed_requests。
    over = [e for e in data if int(e.get("status") or 0) == 403]
    malformed = [e for e in data if int(e.get("status") or 0) not in (200, 403)]
    why: dict[str, int] = {}
    for e in over:
        k = str(e.get("reason") or "unclassified")
        why[k] = why.get(k, 0) + 1
    why_m: dict[str, int] = {}
    for e in malformed:
        k = str(e.get("reason") or "unclassified")
        why_m[k] = why_m.get(k, 0) + 1
    return {"denied": len(over), "total": len(data), "source": "gateway_access_log(403)",
            "reasons": why, "malformed_requests": len(malformed), "malformed_reasons": why_m}


def overreach_from_egress(run_dir: Path) -> dict | None:
    """网络侧越权率的分子/分母：边车转发到网关的请求里带状态码的那些；403 计拒绝。
    一条带状态码的都没有 → None（不可得），不是 {0, 0}。"""
    p = run_dir / "log" / "egress.jsonl"
    if not p.is_file():
        return None
    total = denied = 0
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("kind") != "http_identity" or e.get("event") not in ("forward", "deny"):
            continue
        st = e.get("status")
        if st is None:
            continue
        total += 1
        denied += int(int(st) == 403)
    return {"denied": denied, "total": total} if total else None


def score_run(run_dir: Path, task_dir: Path, *, out_dir: Path, anchor_status: str | None = None,
              calib: dict | None = None, gateway_log_path: Path | None = None) -> dict:
    run_dir, task_dir, out_dir = Path(run_dir), Path(task_dir), Path(out_dir)
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    inj = json.loads((run_dir / "inject.json").read_text(encoding="utf-8"))
    task = yaml.safe_load((task_dir / "task.yaml").read_text(encoding="utf-8"))
    spec = json.loads((task_dir / "taskspec.json").read_text(encoding="utf-8"))
    if inj["task_id"] != task["task_id"]:
        raise ScoreError(f"run 是 {inj['task_id']} 的，题目录是 {task['task_id']} 的")
    stage, arm, config_id, task_id = task["stage"], inj["arm"], inj["config_id"], task["task_id"]
    anchor_st = anchor_status or anchor_status_from_task(task)
    kind = (task.get("tolerance") or {}).get("kind", "exact")

    h = HV.collect(run_dir, stage=stage, arm=arm, declared_outputs=(), known_files=inj.get("files") or (),
                   task_id=task_id, config_id=config_id,
                   started_at=run["started_at"], finished_at=run["finished_at"],
                   gateway_log_path=gateway_log_path)
    if gateway_log_path is not None:
        # 数据面结算：网关 access_log 就在本机（f01）。T-13 说的「跨机取回未定」是 f02 拉不到 f01 的日志，
        # 不是 f01 自己读不到自己的日志 —— 所以这里显式关掉 pending 标志，按 (task_id, config_id, 时间窗) 三重切片。
        # 切片键全是 runner/网关侧真值（config_id 由边车注入、时间窗取 run.json），不取产物自报的任何东西。
        h.gateway_log, h.unobservable = VIS.visibility(
            gateway_log_path, task_id=task_id, config_id=config_id,
            started_at=run["started_at"], finished_at=run["finished_at"], cross_host_pending=False)
    status = "timeout" if run.get("exit_code") == 124 else h.status_hint
    budget = budget_exhausted(run_dir)
    if status == "no_artifact" and budget:
        # 没交产物**且**撞了闸：这是「预算耗尽」，不是「交白卷」（N-130）。
        status = "budget_exhausted"
    gate = None
    l3 = None
    if status == "ok" and h.artifact is not None:
        if h.artifact.get("config_id") != config_id:
            status = "identity_mismatch"
        else:
            gate = G.gate(h.artifact, task=spec, gateway_log=h.gateway_log,
                          unobservable_marks=list(h.unobservable), config_id=config_id,
                          payload_profile=task.get("payload_profile"))
            status = "malformed" if gate.malformed else ("violation" if gate.gate_failed else "ok")
    bucket = FM.sr_bucket(status)
    if bucket == "scorable" and gate is not None:
        l3 = L3.compare(kind, stage=stage, agent_artifact=h.artifact, gold_artifact=gold_artifact(task_dir),
                        task=spec, agent_dir=run_dir / "work", gold_dir=task_dir / "work", calib=calib,
                        gateway_log=h.gateway_log, as_of=task.get("as_of"))
        #: ⑬ 核六列里的 `Decl%` / `Set%`：申明率与**比法无关**（八个 kind 都要），
        #: 所以不塞进 `L3.compare` 的分派里，在这里统一贴上。
        #: 只进 `correctness`（报出），**不动 `l3.score` 与 `l3_pass`** —— 它是新出的量，
        #: 掺进判据会让已经签字的那一批结果换一套分数。
        l3.correctness.update(L3.declaration_metrics(h.artifact, stage=stage, task=spec))

    out: dict | None = None
    if gate is not None and bucket == "scorable":
        out = {"schema_version": SCHEMA_VERSION, "validity": gate.validity,
               "gate_failed": sorted(gate.gate_failed), "unobservable": sorted(gate.unobservable),
               "correctness": dict(l3.correctness) if l3 else {}, "effect": None}
        if gate.validity == "valid":
            if l3 is not None and l3.correct_handling is True:
                out.update({"effect_withheld_reason": "honest_halt", "correct_handling": True,
                            "halted_fields": list(l3.halted_fields)})
            elif anchor_st == "pending":
                out["effect_withheld_reason"] = "anchor_pending"
            else:
                anc = anchor(task_dir, kind=kind, stage=stage, spec=spec, calib=calib)
                eff, meta, why = effect_of(l3, anc)
                out["effect"], out["anchor"] = eff, meta
                if why:
                    out["effect_withheld_reason"] = why
        #: `correctness` 里不许有 inf / nan（红队 5.1 finding A3）：`validate_scorer_output`
        #: 只判 `effect` 里的每个值是不是有限数，`correctness` 它只判「是个对象」，
        #: 于是 `max_band_ratio = inf` 一路写进 `*.score.json` 与 `records.json`，
        #: 落下的是裸 `Infinity` —— Python 读得回来，别人的严格 JSON 解析器读不回来。
        out["correctness"], nonfinite = L3.sanitize(out["correctness"])
        if nonfinite:
            out["correctness"]["nonfinite_keys"] = len(nonfinite)
        v = validate_scorer_output(out, anchor_status=anchor_st)
        if not v.ok:
            raise ScoreError("scorer 输出没过自己的 schema（半成品不进主表）：\n  " + "\n  ".join(map(str, v.findings)))

    trace = LT.load(run_dir)
    usage = LT.usage_totals(trace) or {}
    corr, corr_nonfinite = L3.sanitize(dict(l3.correctness) if l3 else {})
    record = {
        "task_id": task_id, "stage": stage, "config_id": config_id, "arm": arm,
        "seq": inj.get("seq"), "run_id": inj["run_id"],
        #: 四条版本轴 + scorer 自己的 schema 版本。**记录里带着它们，表才切得开**。
        **version_axes(inj), "scorer_schema_version": SCHEMA_VERSION,
        "run_status": status, "sr_bucket": bucket,
        "validity": (gate.validity if gate else None), "malformed": (gate.malformed if gate else None),
        "gate_failed": (list(gate.gate_failed) if gate else []),
        "unobservable": (list(gate.unobservable) if gate else []),
        "probe_states": (dict(gate.probe_states) if gate else {}),
        "findings": (list(gate.findings) if gate else []),
        "l3_kind": (l3.kind if l3 else None), "l3_pass": (l3.l3_pass if l3 else None),
        "l3_score": ((l3.score if (l3.score is None or math.isfinite(float(l3.score))) else None)
                     if l3 else None),
        "effect": ((out or {}).get("effect") or {}).get("score") if out else None,
        "effect_withheld_reason": (out or {}).get("effect_withheld_reason") if out else None,
        "anchor": (out or {}).get("anchor"),
        "correctness": corr,
        "correctness_nonfinite_keys": (sorted(corr_nonfinite) or None),
        "correct_handling": (l3.correct_handling if l3 else None), "l3_note": (l3.note if l3 else ""),
        "steps": LT.steps(trace), "tokens_prompt": usage.get("prompt_tokens"),
        "tokens_completion": usage.get("completion_tokens"),
        #: 主表 `$` 列（卡 1.5）。价目表缺价 / 这次没有网络侧 usage → None，**不是 0**。
        "cost_usd": PR.cost_usd(usage, model_of(config_id)), "cost_model": model_of(config_id),
        "latency_s": run.get("elapsed_s"), "validator_rejections": validator_rejections(run_dir),
        "overreach": overreach_from_gateway_log(h.gateway_log) or overreach_from_egress(run_dir),
        #: 没界定右端的取数请求数（遥测，不进闸门 —— 裁定 2026-09-06 取第 2 种读法）
        "unbounded_requests": ASch.count_unbounded_requests(h.gateway_log),
        "budget": budget,
        "anchor_status": anchor_st, "unexpected_files": list(h.unexpected),
    }
    RIO.secure_dir(out_dir)          # 裸 mkdir 的中间层只受 umask 管（0775）→ 红线 5
    dst = out_dir / f"{inj['run_id']}.score.json"
    RIO.write_json(dst, {"scorer_output": out, "record": record})
    return {"scorer_output": out, "record": record, "path": str(dst)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--task", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--anchor-status", default=None, choices=(None, "fixed", "pending"))
    a = ap.parse_args(argv)
    r = score_run(Path(a.run), Path(a.task), out_dir=Path(a.out), anchor_status=a.anchor_status)
    rec = r["record"]
    print(f"{rec['run_id']}: status={rec['run_status']} validity={rec['validity']} "
          f"gate_failed={rec['gate_failed']} l3={rec['l3_kind']}:{rec['l3_pass']} → {r['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
