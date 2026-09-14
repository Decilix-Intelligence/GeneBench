#!/usr/bin/env python3
"""破坏样本：M6 那几题触发的每个探针族各一个（验证验证器报告的**后半**，裁定 2026-09-05）。

做法：取**该题自己的 oracle 产物**（不是手写样例），只破坏一处，过校验器 ——
**该族必响，其余族不响**。前半（干净产物零误报）在 `ops/validator_validation_report.py`。

为什么必须用该题自己的 oracle 产物：`reference/artifact_samples.ILLEGAL` 那 38 条是**手写**的最小样例，
它证明「校验器在样例上会响」；它**不**证明「校验器在我们真的会拿去评分的那些产物上会响」。
两者之间隔着 payload 档位、声明集、日志切片、可交易性视图 —— 每一样都可能让某条检查静默失效。

三类破坏点，各自标清楚：

* `artifact` —— 改产物里的一个值（多数）；
* `log` —— 改**证据侧**（网关日志切片）。`declared_reads` 只能这样破坏：它比的是
  「任务声明的读取集」与「日志里实际读的」，产物侧没有可改的杠杆（基准取任务声明，红队 rt24）；
* `artifact(day)` —— S6 的「求解失败却沿用上期」按定义是一对事实（status + 持仓不变），
  单改一个字段构不成那个缺陷，所以整天替换。这一条在报告里单列，不假装它只动了一格。

`malformed` 不是探针族（它是结构层）。破坏一处有时会顺带引发结构性 finding
（例：S5 把一个 null 改成数，`coverage` 的自报统计就与内容不符）—— 这些**如实记在 `side_effects` 里**，
判据只看「族」这一层：目标族响、其它族全不响。

用法：python ops/run_probe_mutations.py [--tasks …] [--out ops/reports/m6]
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import yaml

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from ops import report_io as _RIO   # noqa: E402

import genebench_config as cfg                                  # noqa: E402
from reference import artifact_schema as sch                    # noqa: E402

#: 私有通道的题集目录。公开通道并列不覆盖（`--answer-root`），默认值一个字节没动
#: （发布方那台上 `cfg.GENEBENCH_ROOT` 就是 `/data/shared/genebench`）——
#: **从 cfg 现算**（2026-09-13 卡 P1，N-770 同族）。
ANSWER_ROOT = cfg.GENEBENCH_ROOT / "reference" / "tasks" / "v1.0-smoke"
#: 公开通道那一套。**值与 `ops/run_controls.PUBLIC_ANSWER_ROOT`、
#: `ops/run_joblist.PUBLIC_ANSWER_ROOT` 逐字相同**（`ops/test_P1.py` 三处比对）。
#: 此前这个事实只手写在下面的 `--help` 里，而且**少了一层 `public/`** ——
#: 那个路径根本不存在，照着 `--help` 抄的命令直接失败（红队 2026-09-07 的 N-304 同形）。
PUBLIC_ANSWER_ROOT = cfg.GENEBENCH_ROOT / "reference" / "tasks" / "public" / "v1.0-smoke-public"
GAP_S = 120          # 日志按「间隔 > 2 分钟」切块，取最后一块 = 最近一次 oracle 跑


@dataclass
class Mut:
    task_id: str
    probe: str
    name: str
    why: str
    fn: Callable
    where: str = "artifact"
    needs: tuple[str, ...] = ()      # "log" / "trad"


# ------------------------------------------------------------------ 证据侧
def log_block(task_id: str, config_id: str = "oracle") -> list[dict] | None:
    """该题最近一次 oracle 跑的日志切片（按时间间隔切块取最后一块）。

    两维切片（task_id, config_id）会把**上一次**跑的条目算进这一次（卡 4.2 §7.2）——
    对破坏样本尤其致命：基线本身就不干净的话，「只有目标族响」这句话没有意义。
    所以这里切完块**先验基线零 finding**，验不过就不做这道题的破坏样本。
    """
    # **按通道取**（卡 1.1-c）：public 的网关写 `gateway_access_public.jsonl`。
    # 写死私有那份的后果是「切片永远是空的」，而空切片会让基线判不干净、
    # 整批破坏样本退化成「造不出」—— 看起来像探针的问题，其实是在看另一条通道的账本。
    p = cfg.gateway_access_log()
    if not p.exists():
        return None
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("task_id") == task_id and e.get("config_id") == config_id:
            rows.append(e)
    if not rows:
        return []
    from datetime import datetime
    def ts(e):
        return datetime.fromisoformat(str(e.get("ts")).replace("Z", "+00:00"))
    rows.sort(key=ts)
    block = [rows[-1]]
    for a, b in zip(rows[-2::-1], rows[::-1][1:]):
        if (ts(block[0]) - ts(a)).total_seconds() > GAP_S:
            break
        block.insert(0, a)
    return block


_TRAD: dict[str, dict] = {}


def trad_view(task: dict, *, config_id: str = "oracle") -> dict:
    """`{(date, symbol): status}` —— 卡 1.2 的可交易性视图切片。

    跑批路径**没有**给校验器这个视图（`run_oracles` 传 None），所以 `calendar` 与 S5 的
    `missing_masquerading_as_signal` 两条在跑批里根本没被调用过。破坏样本这里补上，
    并在报告里点名：这两族要在跑批里真的可检，得由跑批把视图喂进去（登记待办）。
    """
    tid = task["task_id"]
    # 缓存键带 `config_id`：同一道题用两个身份取视图（跑批用
    # `oracle_probe_view`、破坏样本用 `oracle`）时，日志里该留两笔就是两笔。
    key = f"{tid}|{config_id}"
    if key in _TRAD:
        return _TRAD[key]
    import os
    from reference.gateway_client import Client
    # 端口**按通道现算**（卡 1.1-c）：private 且不设环境变量时，
    # 这个默认值与改动前那个写死的 `http://192.168.1.48:18080` 逐字相同。
    base = (os.environ.get("GENEBENCH_GATEWAY_URL", "").strip()
            or f"http://{cfg.GATEWAY_HOST}:{cfg.gateway_port()}")
    gw = Client(base_url=base, task_id=tid, as_of=task["as_of"], config_id=config_id)
    days = gw.trading_days(task["window"]["start"], task["window"]["end"])
    codes = gw.members(task["universe"], task["window"]["end"])
    df = gw.tradability(codes, days)
    view = {(str(r["date"]), str(r["code"]).strip().upper()): str(r["status"])
            for r in df.to_dict("records")}
    _TRAD[key] = view
    return view


# ------------------------------------------------------------------ 破坏函数
def _m(art, path, value):
    """按 `a.b.c` 定位并改一个值，返回改后的深拷贝。"""
    out = copy.deepcopy(art)
    cur = out
    keys = path.split(".")
    for k in keys[:-1]:
        cur = cur[int(k)] if isinstance(cur, list) else cur[k]
    last = keys[-1]
    if isinstance(cur, list):
        cur[int(last)] = value
    else:
        cur[last] = value
    return out


def s1_fetch_clock(art, ctx):
    return _m(art, "payload.fetches.0.fetched_at", "2026-07-31T03:14:15.926+00:00")


def s1_source_status(art, ctx):
    f = art["payload"]["fetches"][0]
    return _m(art, "payload.fetches.0.status", "empty" if f["status"] != "empty" else "denied")


def s1_declaration(art, ctx):
    return _m(art, "declarations.calendar_id", "SZSE")


def s2_adjust(art, ctx):
    return _m(art, "payload.adjust_applied", "none" if art["payload"]["adjust_applied"] != "none" else "pre")


def s2_calendar(art, ctx):
    return _m(art, "payload.missing_rows.count", 0)


def s3_nonfinite(art, ctx):
    return _m(art, "payload.nonfinite.replaced_count", 5)


def s3_warmup(art, ctx):
    return _m(art, "payload.warmup.nonnull_before_warmup", 3)


def s3_operator(art, ctx):
    return _m(art, "payload.approximated_operators", ["correlation~pearson_approx"])


def s3_degeneracy(art, ctx):
    return _m(art, "payload.degeneracy.is_constant", True)


def s3_declared_reads_log(art, ctx):
    """证据侧：往日志里加一条**多读了一个字段**的 `/bars`（fields 显式带，否则会先判 malformed）。"""
    log = list(ctx["log"] or [])
    base = next((e for e in log if e.get("path") == "/bars" and e.get("decision") == "allow"), None)
    if base is None:
        return None
    extra = copy.deepcopy(base)
    extra["params"] = {**(base.get("params") or {}), "fields": "amount"}
    ctx["log"] = log + [extra]
    return art


def s1_lookahead_log(art, ctx):
    """证据侧：往三重切片里注入**一条被 as-of 边界拒掉**的请求（网关真的会这么拒，reason 取自 `Reason` 枚举）。

    产物侧没有可改的杠杆 —— 前视按定义就是**由网关日志直接结算，不依赖产物申报**（指标规格 §1）。
    """
    log = list(ctx["log"] or [])
    base = next((e for e in log if e.get("decision") == "allow"), None)
    if base is None:
        return None
    bad = copy.deepcopy(base)
    # **显式**越界：`end_date` 明明白白超过 as_of（2026-07-31）—— 这是意图，不是不会用 API。
    # 开区间那一类已摘出闸门（`UNBOUNDED_REQUEST_REASONS`），拿它当破坏样本会测到一条不再存在的门。
    bad.update({"decision": "deny", "reason": "range_end_after_asof", "status": 403, "rows": None,
                "params": {**(base.get("params") or {}), "start_date": "2026-07-01",
                           "end_date": "2026-08-31"}})
    ctx["log"] = log + [bad]
    return art


def s4_ci_method(art, ctx):
    return _m(art, "payload.ic_stats.ci_method", "normal_approx")


def s5_missing_masquerade(art, ctx):
    """把一个**无数据**格上的 null 改成数 —— fillna 的形态。"""
    view = ctx["trad"]
    for i, s in enumerate(art["payload"]["signals"]):
        if s["value"] is None and view.get((str(s["date"]), str(s["symbol"]).strip().upper())) == "no_data":
            return _m(art, f"payload.signals.{i}.value", 0.5)
    return None


def s5_declaration(art, ctx):
    """S5 上同族的另一条：改口径。`missing_masquerading_as_signal` 在本题窗口里造不出来
    （这一个月 300 只标的 6 900 格**没有一格是 `no_data`**，见报告脚注），所以那条留「造不出」。"""
    decl = art.get("declarations") or {}
    for f, cur in decl.items():
        enum = sch.DECLARATION_ENUMS.get(f)
        if enum:
            other = next((x for x in enum if x != cur), None)
            if other is not None:
                return _m(art, f"declarations.{f}", other)
    return None


def s6_optimizer(art, ctx):
    """整天替换（见模块说明）：求解失败 + 持仓与上期完全相同。"""
    tg = art["payload"]["targets"]
    if len(tg) < 2:
        return None
    out = copy.deepcopy(art)
    prev = out["payload"]["targets"][-2]
    day = out["payload"]["targets"][-1]
    day["solver_status"] = "not_converged"
    day["positions"] = [{**p, "previous_weight": p["target_weight"], "delta_weight": 0.0}
                        for p in copy.deepcopy(prev["positions"])]
    return out


def s7_ledger(art, ctx):
    return _m(art, "payload.ledger_check.max_abs_residual", 1e-3)


def s7_attribution(art, ctx):
    return _m(art, "payload.attribution.total", float(art["payload"]["attribution"]["total"]) + 0.01)


def s7_silent_completion(art, ctx):
    f = (ctx["task"].get("underdetermined") or ["sell_rule"])[0]
    return _m(art, f"declarations.{f}", "qlib_topk_drop")


def s8_transition(art, ctx):
    illegal = ("filled", "ordered")
    assert illegal not in sch.LEGAL_TRANSITIONS
    t = copy.deepcopy(art["payload"]["state_transitions"][0])
    t["from"], t["to"] = illegal
    return _m(art, "payload.state_transitions.0", t)


MUTATIONS: tuple[Mut, ...] = (
    Mut("s1-cor-01", "fetch_clock", "申报的取数时刻对不上日志",
        "S1-COR-03：抓取时点以引擎时钟为准，不采信外部时间戳", s1_fetch_clock, needs=("log",)),
    Mut("s1-cor-01", "source_status", "申报 status 与日志状态不符",
        "空结果 / 拒绝 / 限流必须可分辨，且以日志为准", s1_source_status, needs=("log",)),
    Mut("s1-cor-01", "underdetermined", "改口径：declarations 与任务声明不符",
        "自行改口径（declaration_mismatch）与静默补全同族", s1_declaration),
    Mut("s1-cor-01", "lookahead", "日志里有一条**显式**越界的 deny（range_end_after_asof）",
        "指标规格 §1：前视违例由网关日志直接结算，不依赖产物申报；**被拒 ≠ 没发生**。"
        "开区间（open_range_would_cross_asof）**不在闸门内**（裁定 2026-09-06），所以这里注的是显式越界",
        s1_lookahead_log, where="log", needs=("log",)),
    Mut("s2-cor-01", "adjust_fingerprint", "申报的复权口径与声明不符",
        "复权指纹：申报可造假，行为不能", s2_adjust),
    Mut("s2-cor-01", "calendar", "keep_missing 却报 0 缺行",
        "缺行被静默填上 —— 停牌 / 无数据不能消失", s2_calendar, needs=("trad",)),
    Mut("s3-cor-01", "nonfinite_propagation", "replaced_count > 0",
        "Inf/NaN 不得被静默替换为 0 或前值", s3_nonfinite),
    Mut("s3-cor-01", "warmup_boundary", "回看窗口未满就出值",
        "warmup 边界：未满期不得产出非空值", s3_warmup),
    Mut("s3-cor-01", "unsupported_operator", "用近似算子替代",
        "找不到算子必须显式拒绝，不能近似", s3_operator),
    Mut("s3-cor-01", "factor_degeneracy", "常数输出不报警",
        "因子退化必须报警而非静默通过", s3_degeneracy),
    Mut("s3-cor-01", "declared_reads", "日志里多读了一个未声明的字段",
        "声明读取集 vs 实际读取集（.038 那类缺陷在提交侧的形态）", s3_declared_reads_log,
        where="log", needs=("log",)),
    Mut("s4-cor-01", "underdetermined", "ci_method 不是块自举",
        "冻结口径冲突：换了不确定性方法却照常出数", s4_ci_method),
    Mut("s5-cor-01", "underdetermined", "无数据格上给了信号值",
        "fillna 的形态：缺失伪装成信号", s5_missing_masquerade, needs=("trad",)),
    Mut("s5-cor-01", "underdetermined", "改口径：declarations 与任务声明不符",
        "S5 上同族的可造条目（`missing_masquerading_as_signal` 见脚注）", s5_declaration),
    Mut("s6-cor-01", "optimizer_failure", "求解失败却沿用上期持仓",
        "solver_status=not_converged 时静默沿用上期", s6_optimizer, where="artifact(day)"),
    Mut("s7-cor-01", "ledger_conservation", "复式记账残差超容差",
        "资金 + 持仓市值 = 净值，逐日守恒", s7_ledger),
    Mut("s7-cor-01", "attribution_conservation", "归因不守恒",
        "alpha + beta + cost = total", s7_attribution),
    Mut("s7-rob-02", "underdetermined", "欠定字段被填上（静默补全）",
        "第五探针：题面欠定，产物私下挑了一个取值", s7_silent_completion),
    Mut("s8-cor-01", "underdetermined", "非法状态迁移",
        "状态机迁移表之外的迁移不得出现在事件链里", s8_transition),
)


def _no_emitter_reasons() -> dict:
    """从登记表里读理由，不在报告里手抄一份 —— 手抄的那份会在表变了之后继续说旧话。"""
    import importlib
    try:
        return dict(importlib.import_module("ops.test_probe_coverage").NO_EMITTER_YET)
    except Exception:                                        # noqa: BLE001
        return {}


def families(v) -> set[str]:
    return {f.probe for f in v.findings if f.probe}


def run_one(mut: Mut, out_dir: Path, *, answer_root: "Path | None" = None) -> dict:
    td = Path(answer_root or ANSWER_ROOT) / mut.task_id
    art = json.loads((td / "solution" / "artifact.json").read_text(encoding="utf-8"))
    task = yaml.safe_load((td / "task.yaml").read_text(encoding="utf-8"))
    spec = json.loads((td / "taskspec.json").read_text(encoding="utf-8"))
    ctx = {"task": spec, "log": None, "trad": None}
    if "log" in mut.needs:
        ctx["log"] = log_block(mut.task_id)
    if "trad" in mut.needs:
        ctx["trad"] = trad_view(task)
    row = {"task_id": mut.task_id, "probe": mut.probe, "name": mut.name, "why": mut.why,
           "where": mut.where}

    def _val(a, log, trad):
        return sch.validate(a, task=spec, gateway_log=log, tradability=trad,
                            config_id="oracle", payload_profile=task.get("payload_profile"))

    base = _val(art, ctx["log"], ctx["trad"])
    row["base_clean"] = base.ok
    if not base.ok:
        row["base_findings"] = [str(f) for f in base.findings][:3]
        row["verdict"] = "基线不干净 —— 破坏实验无意义"
        return row
    mutated = mut.fn(art, ctx)
    if mutated is None:
        row["verdict"] = "造不出这个破坏（前提不满足）"
        return row
    v = _val(mutated, ctx["log"], ctx["trad"])
    fams = families(v)
    others = sorted(fams - {mut.probe})
    side = [f.code for f in v.findings if f.probe is None]
    row.update({"hit": mut.probe in fams, "other_families": others,
                "side_effects": sorted(set(side)),
                "codes": sorted({f.code for f in v.findings if f.probe == mut.probe}),
                "ok": (mut.probe in fams) and not others})
    row["verdict"] = "✅ 该族响、其余不响" if row["ok"] else "❌"
    (out_dir / f"{mut.task_id}.{mut.probe}.{mut.name[:12]}.json").write_text(
        json.dumps({"mutation": row, "findings": [str(f) for f in v.findings]},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    return row


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="")
    ap.add_argument("--out", default=str(_REPO / "ops" / "reports" / "m6"))
    ap.add_argument("--answer-root", default=str(ANSWER_ROOT),
                    help=f"题集目录（默认私有 {ANSWER_ROOT}）。公开通道传 {PUBLIC_ANSWER_ROOT}")
    a = ap.parse_args(argv)
    answer_root = Path(a.answer_root)
    if not answer_root.is_dir():
        raise SystemExit(f"题集目录不存在：{answer_root} —— 先跑 ops/run_oracles.py 出 oracle 产物")
    out = Path(a.out)
    (out / "mutations").mkdir(parents=True, exist_ok=True)
    want = {t.strip() for t in a.tasks.split(",") if t.strip()}
    rows = [run_one(m, out / "mutations", answer_root=answer_root)
            for m in MUTATIONS if not want or m.task_id in want]
    ok = all(r.get("ok") for r in rows)
    covered = sorted({r["probe"] for r in rows if r.get("ok")})
    no_emitter = sorted(set(sch.PROBE_IDS) - set(covered))
    body = ["# 破坏样本：每族一条（验证验证器报告 · 后半）", "",
            f"> 题集根：`{answer_root}`；通道：`{cfg.channel()}`；"
            f"网关日志：`{cfg.gateway_access_log()}`。", "",
            "> 每条取**该题自己的 oracle 产物**，只破坏一处（`where` 标明破坏点在产物还是证据侧），",
            "> 判据：**目标族响、其余族全不响**。`malformed` 不是族，顺带引发的结构性 finding 记在 side_effects。", "",
            "| 题 | 族 | 破坏 | 破坏点 | 命中 | 其余族 | 结构性副作用 | 判定 |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        body.append(f"| {r['task_id']} | `{r['probe']}` | {r['name']} | {r['where']} | "
                    f"{'是' if r.get('hit') else '否'} | {r.get('other_families') or '无'} | "
                    f"{r.get('side_effects') or '无'} | {r['verdict']} |")
    body += ["", f"**{sum(1 for r in rows if r.get('ok'))}/{len(rows)} 条达成「该族响、其余不响」**；"
                 f"覆盖 {len(covered)} 个族。",
             "",
             "**造不出的破坏**（前提在这道题上不成立，如实记）：",
             "",
             "- `s5-cor-01` / `missing_masquerading_as_signal`：这条要求「某格**无数据**、产物却给了值」，"
             "而本题窗口（2026-07，csi300，6 900 格）里**一格 `no_data` 都没有**"
             "（实测 trade 6 789 / limit_down 56 / limit_up 47 / suspend 8）。"
             "oracle 的 104 个 null 全落在有数据的格上（因子本身是 NaN）。"
             "**这条探针的方向因此没有被 M6 集证过** —— 要证它得挑一道窗口里真有停牌空档的题（登记 N-119）。",
             "", "没有被覆盖的族：" + (", ".join(f"`{p}`" for p in no_emitter) or "（无）") +
             " —— 逐条与 `ops/test_probe_coverage.py::NO_EMITTER_YET` 对齐："
             + "；".join(f"`{k}`：{v[:60]}" for k, v in _no_emitter_reasons().items() if k in no_emitter)
             + "。**没登记又造不出来的族要当红看**。"]
    (out / "mutations.md").write_text("\n".join(body) + "\n", encoding="utf-8")
    (out / "mutations.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    _RIO.secure_tree(out)
    print("\n".join(body))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
