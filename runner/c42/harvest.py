"""卡 4.2 §3：采集顺序 + 产物采集。

**硬顺序**（每一处相邻对都有一个会静默的失败在等着）::

    load_bundle → check_bundle → render → lint → preflight(provider) → up → run
      → harvest → down -v → canary.scan → parse → classify → record_strict
      → to_scorer_input        (仅 run_status=="ok" 且非 malformed)

| 相邻对 | 反了会怎样 |
| --- | --- |
| `lint` 在 `up` 之前 | 否则一个违规 compose 已经把端口发布到 LAN 了才被拦（卡 4.1 L-6） |
| `preflight` 在 `up` 之前 | 否则用错 provider 跑完一整轮，产物看起来完全正常 |
| **`harvest` 在 `down -v` 之前** | `down -v` 删卷；产物随卷一起消失，表现为 `no_artifact` —— **与 agent 真没写产物不可分** |
| `canary.scan` 在 `parse` 之前 | 泄漏必须压过一切分类结论（§2.2） |
| `classify` 在 `record_strict` 之前 | 落库要写 `run_status`，没有分类就只能写 `None`（现行 4.1 的形态） |
| `to_scorer_input` 最后且**有条件** | §16 |

**顺序是被断言的，不是被约定的**：`ops/test_c42.py::test_harvest_order` 用 monkeypatch 把每一步
换成记录器，跑一次，断言调用序列**逐项相等**（期望序列是测试里的**字面量**，不从本模块 import
—— 从这里 import 就成了同义反复）。理由与卡 4.1 的 lint 同：拓扑保证只在代码长成那个样子时成立，
「长成那个样子」必须可测。

**§2.1 的病灶在这里治**：现行 `c41/runner_core.py` 里 lint 未过与 `starts != 1` 是 `raise` ——
那几题连一行都不写进库，不是「失败」而是「**不存在**」，分母悄悄变小、SR 悄悄变高。
本模块把前置步骤的异常**接住并翻译成 `harness_error`**，然后**照样往下走到 record_strict**。
"""
from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from runner.c42 import failure_modes as FM
from runner.c42 import visibility as VIS

#: 容器里 work/ 的挂载点。产物落在它之外就是 harness 的配置错误，不是 agent 的失败。
TASK_MOUNT = "/task"

#: artifact 的落点（相对 work/）。
ARTIFACT_REL = "artifact.json"

#: 超过它即 `artifact_oversize`。S5 的逐格信号可以很长，所以不能定得太紧；
#: 定这个上限是为了挡「把整个数据集回吐进 artifact」那种形态，不是为了省空间。
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024

#: **本卡定义的产出物清单** —— 卡 4.3 的 `verify_run_dir_unchanged()` 在容器退出后
#: 那一次复核用它做允许集（裁定 2026-09-04：**让定义产出物的人定义允许集**）。
#: 路径相对 run dir。带 `/` 结尾的是前缀。
PRODUCED_COMMON: tuple[str, ...] = (
    "work/artifact.json",        # 被测方的产物
    "work/out/",                 # §8 的发射区（emission.jsonl 及适配器的同类记录）
    "log/",                      # 边车与出向日志
)
#: 阶段特有的产出**文件**（相对 run dir；容器里就是 `/task/<同名>`）。
#:
#: **镜像自 `reference/artifact_schema.py::PAYLOAD_FILES`**（N-44 之后题面才有这三条）。
#: 同源断言在 `ops/test_c42.py` —— 抄一份到执行面而没人盯着，本仓已栽过三次。
#:
#: 这里曾经写死 `work/panel.parquet` / `work/values.parquet` 并**是错的**：
#: 那两个路径只出现在 gold 的 solve.py 里，题面从没告诉过 agent。
#: N-44 把规范形写进了题面（固定槽 `fixed:output_files`，两臂机器生成），
#: 于是采集器可以重新知道路径 —— 按扩展名放宽的那版 glob 随之撤掉。
PRODUCED_BY_STAGE: dict[str, tuple[str, ...]] = {
    "S2": ("work/panel.csv",),
    "S3": ("work/values.parquet",),
    "S7": ("work/ledger.parquet",),
}

#: 题面**仍**未固定路径的阶段。N-44 之后只剩 S4 —— 它的输入面板是题面给的材料，
#: 产出只在 payload 里（ic_stats），没有产出文件契约。
#: 放宽只到**数据扩展名**：`work/probe.py` 这类照样进 `unexpected`。
PRODUCED_DATA_GLOBS: dict[str, tuple[str, ...]] = {
    "S4": ("work/*.parquet",),
}
#: strict 臂多出来的：validator 的调用序列（卡 4.3 协议工件 v1）。
PRODUCED_STRICT: tuple[str, ...] = ("work/protocol/validator.log",)


class HarvestError(RuntimeError):
    pass


class FrameworkOutputOutsideTaskMount(HarvestError):
    """§3.3 第一条。RD-Agent 与 TradingAgents 都默认往 `~/.rdagent`、`./results`、`/tmp` 写；
    那些路径**不在**我们挂的 `work/` 里，`down -v` 之后就没了。让它静默返回空 harvest
    等于把 harness 的配置错误记成 agent 的 `no_artifact`。"""


def produced_allowlist(stage: str, arm: str) -> tuple[str, ...]:
    out = PRODUCED_COMMON + PRODUCED_BY_STAGE.get(stage, ()) + PRODUCED_DATA_GLOBS.get(stage, ())
    return out + PRODUCED_STRICT if arm == "strict" else out


def assert_outputs_under_mount(declared_outputs, *, mount: str = TASK_MOUNT) -> None:
    """§3.3 第一条的**落点在配置期**，不在事后。

    事后查不了：`down -v` 之后挂载外的字节已经没了，我们连「它曾经在那儿」都看不见。
    所以判据是适配器**声明**的产出路径 —— 每个适配器必须把它的框架往哪写声明出来，
    本函数核这些路径都在 `/task` 之下。声明与实际不符是适配器自己的验收（B 档）。
    """
    bad = []
    for p in declared_outputs:
        s = str(p)
        if not s.startswith("/"):
            bad.append(f"{s}（相对路径 —— 落在哪取决于框架的 cwd，不可核）")
        elif not (s == mount or s.startswith(mount.rstrip("/") + "/")):
            bad.append(s)
    if bad:
        raise FrameworkOutputOutsideTaskMount(
            f"框架声明往 {bad} 写产物，而只有 {mount} 是挂出来的 —— "
            f"`down -v` 之后那些字节会随卷消失，表现为 no_artifact，"
            f"与 agent 真没写产物**不可分**")


@dataclass
class Harvest:
    """一次采集的结果。`status_hint` 是**分类的输入**，不是结论
    （`leaked` / `timeout` 压在它前面，见 §2.2）。"""

    run_dir: Path
    artifact_bytes: bytes | None = None
    artifact: dict | None = None
    status_hint: str = "ok"
    emissions_path: Path | None = None
    files: dict[str, int] = field(default_factory=dict)     # 相对 run dir → 字节数
    unexpected: list[str] = field(default_factory=list)
    egress_starts: int | None = None
    #: 网关日志的三态（§7）。`None` = 不可得，`[]` = 可得且零请求。
    gateway_log: list[dict] | None = None
    #: `[(probe, reason)]` —— 进 `Verdict.mark_unobservable`（在数据面做）。
    unobservable: list = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return self.artifact_bytes is None and not self.files


def _rel_allowed(rel: str, allow: tuple[str, ...]) -> bool:
    """三种写法：精确路径、`前缀/`、以及 glob（含 `*`）。

    glob 只用于题面**没固定路径**的阶段（见 `PRODUCED_DATA_GLOBS`）——
    有固定路径时写 glob 是把封闭判据白白放宽。
    """
    for a in allow:
        if rel == a:
            return True
        if a.endswith("/") and rel.startswith(a):
            return True
        if "*" in a and fnmatch.fnmatch(rel, a):
            return True
    return False


def collect(run_dir, *, stage: str, arm: str, declared_outputs=(),
            known_files=(), mount: str = TASK_MOUNT,
            task_id: str | None = None, config_id: str | None = None,
            started_at: str | None = None, finished_at: str | None = None,
            gateway_log_path=None) -> Harvest:
    """采集。**必须在 `down -v` 之前调用。**

    §3.3 第二条：**不许返回空 harvest 而不报错。** 空 harvest 只有两种合法来源 ——
    agent 真的没写（→ `no_artifact`），或框架写到了别处（→ 上一条 raise）。
    二者必须可分，所以先核声明路径，再看有没有产物。
    """
    assert_outputs_under_mount(declared_outputs, mount=mount)
    rd = Path(run_dir)
    if not rd.is_dir():
        raise HarvestError(f"run dir 不存在：{rd} —— 采集器不替上游造目录")
    allow = produced_allowlist(stage, arm)
    known = set(known_files) | {"inject.json", "run.json"}
    h = Harvest(run_dir=rd)
    for p in sorted(rd.rglob("*")):
        if not p.is_file():
            continue
        rel = str(p.relative_to(rd))
        if rel in known:
            continue
        h.files[rel] = p.stat().st_size
        if not _rel_allowed(rel, allow):
            h.unexpected.append(rel)

    em = rd / "work" / "out" / "emission.jsonl"
    h.emissions_path = em if em.exists() else None

    elog = rd / "log" / "egress.jsonl"
    if elog.exists():
        h.egress_starts = sum(
            1 for line in elog.read_text(encoding="utf-8", errors="replace").splitlines()
            if line.strip() and _is_ready(line))

    # 可见性三态在这里接进来。此前 `visibility()` 全仓库只有测试在调 ——
    # 「门有了、门后没人」这个形态本轮已经出现四次（P8 之后的复核、边车漂开、
    # 起容器前复核、这一处）。不接的后果是静默的：`declared_reads` 这族既不核也不标，
    # 主表上看不出它没被测过。
    if task_id and config_id and started_at and finished_at:
        h.gateway_log, h.unobservable = VIS.visibility(
            gateway_log_path or (rd / "log" / "gateway_access.jsonl"),
            task_id=task_id, config_id=config_id,
            started_at=started_at, finished_at=finished_at)
    else:
        h.unobservable = [(p, "采集时没拿到 (task_id, config_id, 时间窗) —— 无法三重切片")
                          for p in VIS.LOG_DEPENDENT_PROBES]

    art = rd / "work" / ARTIFACT_REL
    if not art.exists():
        h.status_hint = "no_artifact"
        return h
    raw = art.read_bytes()
    h.artifact_bytes = raw
    if not raw.strip():
        h.status_hint = "artifact_empty"
        return h
    if len(raw) > MAX_ARTIFACT_BYTES:
        h.status_hint = "artifact_oversize"
        return h
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        h.status_hint = "artifact_not_utf8"
        return h
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        # 截断与「压根不是 JSON」分开：截断多半是超时或写盘中断，
        # 归到 not_json 会把「预算耗尽」误读成「写坏了」（§2.2 同一条理由）。
        h.status_hint = "artifact_truncated" if _looks_truncated(text) else "artifact_not_json"
        return h
    if not isinstance(obj, dict):
        h.status_hint = "artifact_not_json"
        return h
    h.artifact = obj
    return h


def _is_ready(line: str) -> bool:
    try:
        return json.loads(line).get("event") == "ready"
    except Exception:
        return False


def _looks_truncated(text: str) -> bool:
    t = text.strip()
    return bool(t) and t[0] in "{[" and t[-1] not in "}]"


# --------------------------------------------------------------- 顺序

#: **顺序即语义**。改这个元组就是改上面那张表，不是改一个列表。
HARVEST_ORDER: tuple[str, ...] = (
    "load_bundle", "check_bundle", "render", "lint", "preflight", "up", "run",
    "harvest", "down", "canary_scan", "parse", "classify", "record_strict",
    "to_scorer_input",
)

#: 前置步骤炸了归哪种 harness 故障（§2.2：我们自己坏了不能记在 agent 头上）。
STEP_FAULT: dict[str, str] = {
    "load_bundle": "bundle", "check_bundle": "bundle",
    "render": "lint", "lint": "lint",
    "preflight": "provider_pin",
    "up": "docker_up",
    # 产物落在挂载外是**我们**把框架的运行时配错了，不是 agent 没写产物。
    "harvest": "runtime_dependency",
}


@dataclass
class Steps:
    """一步一个可调用对象，签名统一 `(ctx) -> value`。

    做成数据而不是一串直写的调用，是为了让 §3.2 的顺序断言能把每一步换成记录器；
    直写的调用只能靠读代码确认顺序，读代码不是断言。
    """

    load_bundle: Callable
    check_bundle: Callable
    render: Callable
    lint: Callable
    preflight: Callable
    up: Callable
    run: Callable
    harvest: Callable
    down: Callable
    canary_scan: Callable
    parse: Callable
    classify: Callable
    record_strict: Callable
    to_scorer_input: Callable


def run_pipeline(steps: Steps, ctx: dict) -> dict:
    """按 `HARVEST_ORDER` 跑一次。返回 `ctx`（里面有 `run_status` 与 `scorer_input`）。

    三条不变量：

    1. **`down` 一定执行** —— 放在 `finally` 里。超时路径不例外，否则下一个 run 撞上残留
       （表现为 `stale_state`，而根因是上一轮没收干净）。
    2. **前置步骤的异常不吞也不逃** —— 翻译成 `harness_error` 并**继续**走到 `record_strict`。
       让它 `raise` 出去就是 §2.1 那个「连一行都不写进库」的病。
    3. **`to_scorer_input` 有条件**：`run_status == "ok"` 且非 malformed（§16）。
    """
    order = list(HARVEST_ORDER)
    i_harvest, i_down = order.index("harvest"), order.index("down")
    if i_harvest > i_down:
        raise HarvestError("harvest 排到了 down 之后 —— 产物会随卷一起消失")
    ctx.setdefault("run_status", None)
    ctx.setdefault("harness_fault", None)
    started = False
    try:
        for name in order[:i_down]:                    # load_bundle … harvest
            try:
                ctx[name] = getattr(steps, name)(ctx)
            except Exception as e:                     # noqa: BLE001 —— 故意全接
                fault = STEP_FAULT.get(name)
                if fault is None:
                    raise
                ctx["run_status"] = FM.status_for_fault(fault)
                ctx["harness_fault"] = fault
                ctx["harness_error_detail"] = f"{name}: {type(e).__name__}: {e}"
                break
            if name == "up":
                started = True
    finally:
        if started or ctx.get("force_down"):
            ctx["down"] = steps.down(ctx)              # ← 不变量 1
        else:
            ctx["down"] = None
    for name in order[i_down + 1:-1]:                  # canary_scan … record_strict
        ctx[name] = getattr(steps, name)(ctx)
        if name == "classify" and ctx.get(name) is not None:
            # 覆盖式赋值会让 harness_error 被 classify 的结论盖掉 —— 我们自己坏了导致的
            # 超时就会记在 agent 头上（§2.2 优先级的第二条）。按优先级取，不按先后取。
            prev = ctx.get("run_status")
            ctx["run_status"] = FM.worst(prev, ctx[name]) if prev else ctx[name]
    status = ctx.get("run_status")
    ctx["scorer_input"] = (steps.to_scorer_input(ctx)                 # ← 不变量 3
                           if status == "ok" else None)
    return ctx
