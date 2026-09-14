# -*- coding: utf-8 -*-
"""**逐题跑 oracle**（卡 2.6 / B8）：把 40 道题的参考解真跑一遍，并逐条校验。

**为什么必须真跑**：每个 `solve.py` 的末尾都写着一句
`# 自检：oracle 必须零 finding（O1）… assert validate(...)` —— **注释着的**。
门写在那儿，门后没有实现者（同 P4b 的形态）。在跑过之前，
「40 题都有 oracle」这句话的全部依据是「文件不是骨架」。

**O1 判据**：oracle 产出的 artifact 必须 **零 finding**。
不是「没有 violation」—— `malformed` 同样算，因为 oracle 是我们自己写的，
它连格式都对不上的话，用它当 gold 只会把错误传下去。

**网关必须真起**：交叉核要拿 `access_log` 的真实切片
（卡 3.1 R15：oracle 真跑一次网关）。`gateway_log=None` 是「不可得」，
会让整族交叉核退化成跳过 —— 那样跑出来的绿是假的。
"""
from __future__ import annotations

import argparse
import contextlib
import functools
import json
import os
import subprocess
from datetime import datetime, timezone
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import genebench_config as cfg
from genetask import packager as P
from ops.export_bundle import ANSWER_ROOT
from reference import artifact_schema as sch
from reference.artifact_schema import PROBE_IDS
from reference.oracle_io import GATEWAY_ENV

PARAMS = _REPO / "genetask" / "params" / "v1.0-smoke40.yaml"
ORACLE_CONFIG_ID = "oracle"

#: 跑批取**可交易性视图**时用的身份（N-120）。**不与 oracle 共用 config_id**：
#: 交叉核按 `(task_id, config_id, 时间窗)` 三维切片，而 `run_controls.oracle_window`
#: 与 `run_probe_mutations.log_block` 是按「间隔 > 2 分钟」切块取最后一块。
#: 视图那几次 `/tradability` 若也记成 `oracle`，就会混进那一块 —— 于是 `declared_reads`
#: 看见几次题面没声明的读取，**一个纯取证动作把被取证的东西判红**。
TRAD_VIEW_CONFIG_ID = "oracle_probe_view"


def gateway_url() -> str:
    """本次跑批要打的网关。

    **端口按通道现算，`GENEBENCH_GATEWAY_URL` 优先**（卡 1.1-c）。原来这里是
    `f"http://{cfg.GATEWAY_HOST}:{cfg.GATEWAY_PORT}"` —— 写死私有端口，
    且 `run_one` 会拿它**覆盖**子进程的 `GENEBENCH_GATEWAY_URL`，
    于是 `GENEBENCH_CHANNEL=public` 跑出来的 oracle 全都打在私有网关上：
    数字照样出，只是来自另一份数据，没有一处会报错。

    `GENEBENCH_GATEWAY_URL` 是 `reference/oracle_io.py` 声明的**唯一**允许的环境变量
    （它是部署事实不是任务事实），所以这里认它、也只认它。
    private 通道且不设环境变量时，返回值与改动前**逐字相同**。
    """
    env = os.environ.get(GATEWAY_ENV, "").strip()
    if env:
        return env
    return f"http://{cfg.GATEWAY_HOST}:{cfg.gateway_port()}"


def __getattr__(name: str):
    """`GATEWAY_URL` 保留成模块属性（PEP 562）：既有调用方一个字都不用改，
    但它现在**按通道现算**而不是 import 期定死。"""
    if name == "GATEWAY_URL":
        return gateway_url()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


#: 没有归属探针族的 finding（`malformed` 一律没有 probe）。
#: 它们照样要进矩阵 —— 「结构就不对」与「某族探针响了」是两回事，
#: 但两者在 oracle 上都必须是零。
MALFORMED_ROW = "(malformed)"


def check_log_evidence(entries: list[dict] | None) -> list[str]:
    """**证据源本身**的完整性（D-26）。

    `_status_from_log` 的判据刻意不容忍 `rows` 缺失 —— 缺了就会把诚实的 `ok`
    判成不一致。那是**网关的缺陷**，不是 artifact 的。
    判据保持严格（爆红看得见），而「为什么爆红」由这里点名。
    """
    if entries is None:
        return ["网关日志切片不可得（None）—— 交叉核整族退化，这时候的绿是假的"]
    bad: list[str] = []
    if not entries:
        bad.append("网关日志切片是空的（0 条）—— oracle 一次网关都没请求过？")
    n_bad = [e for e in entries
             if e.get("decision") == "allow"
             and not (isinstance(e.get("rows"), int) and not isinstance(e.get("rows"), bool))]
    if n_bad:
        bad.append(f"{len(n_bad)}/{len(entries)} 条 allow 日志没有整数 `rows` —— "
                   f"`_status_from_log` 会把它们推成 empty，于是诚实的 ok 全被判违例。"
                   f"**根因在网关**（gateway/app.py::_rows_of），不在 artifact")
    return bad


@dataclass
class Result:
    task_id: str
    stage: str
    template_id: str
    ran: bool = False
    rc: int | None = None
    stderr: str = ""
    artifact: Path | None = None
    findings: list[str] = field(default_factory=list)
    log_rows: int | None = None
    #: 喂给校验器的可交易性视图有多少格（N-120）。`None` = **没喂**（不可得或被 --no-tradability 关掉），
    #: 那时 `calendar` 与 `missing_masquerading_as_signal` 两条没被调用过。
    tradability_rows: int | None = None
    evidence: list[str] = field(default_factory=list)
    probes: dict[str, int] = field(default_factory=dict)
    note: str = ""

    @property
    def ok(self) -> bool:
        """**必须真的有产物**（2026-09-05 修）。

        原来是 `ran and rc == 0 and not findings` —— 没有 artifact 时
        `findings` 恰好是空的，于是「校验器一条都没查」被记成「零 finding」。
        S7 五题就是这样：它们把产物写到 `gold/oracle_artifact.json`，
        而这里找的是 `solution/artifact.json`，找不到却整列绿。
        恒绿的门与恒红的一样会被绕过（F7 / D-06）。
        """
        return (self.ran and self.rc == 0 and self.artifact is not None
                and not self.findings)


def gateway_up(url: "str | None" = None, timeout: float = 3.0) -> bool:
    url = url or gateway_url()
    try:
        with urllib.request.urlopen(url + "/healthz", timeout=timeout) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError):
        return False


def wait_gateway(url: "str | None" = None, secs: float = 20.0) -> bool:
    url = url or gateway_url()
    end = time.time() + secs
    while time.time() < end:
        if gateway_up(url):
            return True
        time.sleep(0.5)
    return False


def log_slice(task_id: str, config_id: str = ORACLE_CONFIG_ID,
              since: str | None = None, until: str | None = None) -> list[dict] | None:
    """该题的 `access_log` 切片。

    **切片键取任务侧与基础设施侧**（`task_id` 由请求头带、`config_id` 由我们注入），
    不取 artifact 自报的任何东西（红队协议 §2.1）。
    日志文件不存在 → `None`（不可得），**不是** `[]`（可得但零条）。
    """
    # **按通道取**（卡 1.1-c）：public 的网关写 `gateway_access_public.jsonl`。
    # 写死私有那份的后果是「切片永远是空的」——`check_log_evidence` 会把它
    # 读成「oracle 一次网关都没请求过」，而真相是我们在看另一条通道的账本。
    p = cfg.gateway_access_log()
    if not p.exists():
        return None
    out: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("task_id") != task_id or e.get("config_id") != config_id:
            continue
        # **第三维：时间窗**（卡 4.2 §7.2）。两维切片会把**上一次**跑同一道题的条目算进这一次 ——
        # 2026-09-05 实测：S8 三题的 oracle 自报 `denied_requests: 0`（这一次确实没越权），
        # 校验器却看见 11 / 3 / 2 次拒（都来自当天更早的几次尝试），判 `overreach_count_mismatch`。
        # 时间戳按字符串比即可：两侧都是同一个网关写的 ISO-8601 带偏移，同格式同精度。
        ts = str(e.get("ts") or "")
        if (since and ts < since) or (until and ts > until):
            continue
        out.append(e)
    return out


def write_all(rows: list[dict], *, capabilities: dict | None = None,
              answer_root: "Path | None" = None, set_name: str = ""
              ) -> tuple[dict[str, Path], dict[str, str]]:
    """把题落到**答案面唯一合法的根**。落点不是参数（N-61 / D-28）。

    返回 `(能落盘的, 落不了的原因)`。**一道落不了不许拖垮整批** ——
    探针题的 E9c 锁（「字段在该条件下没有 materiality 实测记录」）是一道**设计上就该红**的门，
    它不是这批跑的失败，是那道题还没到能出 oracle 的时候。
    """
    root = Path(answer_root or ANSWER_ROOT)
    # `set_name` 非空时：先落进一个**同根下的暂存参考根**，再整体搬到 `tasks/<set_name>/`。
    # 为什么不直接写：`P.write_task` 的落点是 `<root>/tasks/<set_id>/`，而 `set_id`
    # 在冻结根里（题面轴），**不许为了换个目录名去改它**。它还会往同一层的
    # `_ledger.jsonl` 追加一行 —— 直接用私有根就会把公开通道的行写进私有台账。
    # `set_name` 允许带一层目录（public/v1.0-smoke-public），暂存目录名里把斜杠换掉
    stage = root / (".stage-" + set_name.replace("/", "_")) if set_name else root
    cfg.create_dir(stage)
    built: dict[str, Path] = {}
    blocked: dict[str, str] = {}
    for r in rows:
        tid = r["task_id"]
        try:
            b = P.build_task(r, capabilities=capabilities)
            if not b.ok:
                blocked[tid] = f"建题不过：{'; '.join(b.problems[:2])}"
                continue
            built[tid] = P.write_task(b, stage, capabilities=capabilities)
        except Exception as e:                                    # noqa: BLE001
            blocked[tid] = f"{type(e).__name__}: {e}"
    if set_name:
        built = _relocate(built, stage, root / "tasks" / set_name)
    return built, blocked


def _relocate(built: dict[str, Path], stage: Path, dest: Path) -> dict[str, Path]:
    """把暂存参考根下的题目录（连同 `_ledger.jsonl`）搬到 `dest`，**逐文件覆盖**。

    **不许 rmtree 目标题目录**：题面 `inputs` 声明的夹具住在 `<task>/work/`
    （`reference/make_fixtures.py` / `reference/make_s7_signal.py` 物化的），
    而唯一可行的顺序是「先跑一次 oracle 把题目录建出来 → 物化夹具 → 再跑一次 oracle」。
    整目录替换会在第二次跑批时把夹具删干净，表现是 S4/S5/S6/S7 十六道题一起
    `FileNotFoundError`，而日志里看不出是谁删的。

    逐文件覆盖与 `P.write_task` 写进已存在目录时的行为**同形**：它也只覆盖自己那几个文件。

    搬完删暂存根 —— 留着的话下一次跑批会在**两个地方**各有一份题目录，
    而 `solve.py` 是按 `cwd` 找 `task.yaml` 的：跑的是哪一份将取决于谁先被找到。
    """
    import shutil

    cfg.create_dir(dest)
    out: dict[str, Path] = {}
    for tid, d in built.items():
        tgt = dest / tid
        cfg.create_dir(tgt)
        for f in sorted(p for p in d.rglob("*") if p.is_file()):
            q = tgt / f.relative_to(d)
            cfg.create_dir(q.parent)
            if q.exists():
                q.unlink()
            shutil.move(str(f), str(q))
            q.chmod(0o600)
        shutil.rmtree(d, ignore_errors=True)
        tgt.chmod(0o700)
        out[tid] = tgt
    for led in stage.rglob("_ledger.jsonl"):
        with open(dest / "_ledger.jsonl", "a", encoding="utf-8") as fh:
            fh.write(led.read_text(encoding="utf-8"))
        (dest / "_ledger.jsonl").chmod(0o600)
    shutil.rmtree(stage, ignore_errors=True)
    dest.chmod(0o700)
    return out


#: 本次跑批的时刻（每行都盖这个章）。
_NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")


def _batch_lock(what: str):
    """跑批要**独占网关**（N-125）：单 worker + 共用 access_log，叠着跑的后果见 `ops/gateway_lock.py`。"""
    from ops.gateway_lock import gateway_lock
    return gateway_lock(what)


def tradability_view(task: dict) -> "tuple[dict | None, str]":
    """N-120：把**可交易性视图**取来喂给校验器，取不到就照实说不可得。

    为什么跑批必须喂：`calendar`（缺行被静默填上）与 S5 的
    `missing_masquerading_as_signal` 两条检查**只在拿到视图时才被调用**。
    跑批原来传 `tradability=None`，于是这两族在 40 题上一次都没判过 ——
    而矩阵里它们显示为 `·`（判过且零）。**不可得与零长得一样**，
    正是 `None` / `[]` 那一族错误（红队 rt18）。

    视图与 `ops/run_probe_mutations.py::trad_view` 是**同一份代码**（破坏样本
    正是靠它才造得出 `calendar` 与 `missing_masquerading_as_signal` 两条）——
    两边各搭一份的话，跑批判绿而破坏样本判红时，没人分得清是探针的事还是视图的事。

    取不到时返回 `(None, 一句话说明)`：调用方把它记进 `evidence`，
    报告里于是看得见「这一轮这两族没被调用过」。**不假装 clean。**
    """
    from ops.run_probe_mutations import trad_view
    try:
        return trad_view(task, config_id=TRAD_VIEW_CONFIG_ID), ""
    except Exception as e:                                    # noqa: BLE001
        return None, (f"可交易性视图取不到（{type(e).__name__}: {e}）—— 本题的 `calendar` 与 "
                      f"`missing_masquerading_as_signal` 两条**没被调用过**，它们的零是不可得不是干净")



#: oracle 子进程的**全局**墙钟。不要为了让某一道题跑完而放宽它 —— 放宽全局等于把
#: 「哪道题真的慢」这件事从此看不见，而慢正是 S2 长窗口实例唯一的症状。
ORACLE_TIMEOUT_DEFAULT = 600

#: **逐实例超时覆盖**（用户裁定 ⑥，2026-09-11）。键是 `task_id`，值是秒。
#: 每一条都必须是**量过的**：写进来之前先单跑一次记墙钟与峰值 rss，把实测写在注释里。
#:
#: * ``s2-rob-04`` —— 13 个月窗口（2025-07-01..2026-07-31，是基点的两倍多）。
#:   **实测 834 s（13:54.49）/ 峰值 RSS 220 MB / rc=0**，产物正常落盘；
#:   此前它是这批里唯一一道 `超时 600s`，而超时把它记成「没产出」，
#:   于是矩阵上它与「跑了但有 finding」长得一样。给 1800 s ≈ 实测的 2.2 倍留量。
#:   **窗口不动**（裁定 ⑥ 原文）：窗口正是这道题要考的东西。
ORACLE_TIMEOUT_OVERRIDES: "dict[str, int]" = {
    "s2-rob-04": 1800,
}


def oracle_timeout(row: dict) -> int:
    """本题的 oracle 墙钟。优先级：题行里的 ``oracle_timeout`` > 覆盖表 > 全局默认。

    题行那一路是留给**参数表**的（`genetask/params/v1.0-instances.yaml` 带一个
    `oracle_timeout` 字段）—— 但参数表自 v1.0.15 起进了冻结根（`instances_fingerprint`
    已进 `ROOT_FIELDS`），**往里加一个字段就作废所有已发通行证**。所以现在走覆盖表；
    等哪一次重冻顺手把它搬进参数表时，这个函数一个字都不用改。
    """
    v = row.get("oracle_timeout")
    if v is None:
        v = ORACLE_TIMEOUT_OVERRIDES.get(row.get("task_id"), ORACLE_TIMEOUT_DEFAULT)
    try:
        v = int(v)
    except (TypeError, ValueError, OverflowError):
        # OverflowError 是 `float('inf')` 那一路 —— 漏掉它，「超时设成无穷大」
        # 会以一个 traceback 而不是一句话结束，而 traceback 不会说是哪道题。
        raise SystemExit(f"{row.get('task_id')} 的 oracle_timeout 不是整数：{v!r}")
    if v <= 0:
        raise SystemExit(f"{row.get('task_id')} 的 oracle_timeout 要 > 0，拿到 {v}")
    return v


def run_one(task_dir: Path, row: dict, *, tradability: bool = True) -> Result:
    res = Result(row["task_id"], row["stage"], row["template_id"])
    solve = task_dir / "solution" / "solve.py"
    if not solve.is_file():
        res.note = f"没有 {solve}"
        return res
    out = task_dir / "solution" / "artifact.json"
    env = dict(os.environ,
               GENEBENCH_GATEWAY_URL=gateway_url(),
               GENEBENCH_ORACLE_OUT=str(out),
               PYTHONPATH=str(_REPO))
    started = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    tmo = oracle_timeout(row)
    try:
        p = subprocess.run([sys.executable, str(solve)], cwd=str(task_dir),
                           capture_output=True, text=True, timeout=tmo, env=env)
    except subprocess.TimeoutExpired:
        res.ran, res.rc, res.stderr = True, -1, f"超时 {tmo}s"
        return res
    finished = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    res.ran, res.rc = True, p.returncode
    res.stderr = (p.stderr or "").strip()[-1200:]
    if p.returncode != 0:
        return res
    if not out.exists():
        res.note = (f"rc=0 但没有产物 {out} —— oracle 必须写**标准 artifact 路径**"
                    f"（统一 I/O 契约 D-31：`GENEBENCH_ORACLE_OUT`）。"
                    f"写到别处 = 校验器一条都没查，而那会被记成「零 finding」")
        return res
    res.artifact = out
    try:
        art = json.loads(out.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        res.findings = [f"artifact 读不出来：{e}"]
        return res
    spec = json.loads((task_dir / "taskspec.json").read_text(encoding="utf-8"))
    import yaml
    task = yaml.safe_load((task_dir / "task.yaml").read_text(encoding="utf-8"))
    rows_ = log_slice(row["task_id"], since=started, until=finished)
    res.log_rows = None if rows_ is None else len(rows_)
    res.evidence = check_log_evidence(rows_)
    # **视图在日志切片取完之后才取**（N-120）：它自己也走网关，先取的话
    # 那几条 `/tradability` 会落进 [started, finished] 窗口里，
    # 于是「oracle 读了什么」这条证据被取证动作本身污染。
    trad, trad_note = tradability_view(task) if tradability else (None, "")
    if trad_note:
        res.evidence.append(trad_note)
    res.tradability_rows = None if trad is None else len(trad)
    v = sch.validate(art, task=spec, gateway_log=rows_, tradability=trad,
                     config_id=ORACLE_CONFIG_ID,
                     payload_profile=task.get("payload_profile"))
    res.findings = [str(f) for f in v.findings]
    res.probes = probe_counts(v)
    return res


def run_f1(task_dir: Path, row: dict) -> Result:
    """**F1 填充器**（null_agent）：不跑 solve.py，直接按题面声明的 behavior 造一份产物。

    它是 D-30 的另一半 —— 「诚实产物零 finding」只证明探针**不误伤**，
    还要有「特定错误产物上有 finding」才证明它**朝着对的方向**在判。

    `gateway_log=[]`（**可得但零请求**，不是 `None`）：填充器一次网关都没调过，
    这是事实，不是「日志取不到」。两者在校验器里语义不同（红队 rt18）。
    """
    import yaml

    res = Result(row["task_id"], row["stage"], row["template_id"], ran=True, rc=0)
    task = yaml.safe_load((task_dir / "task.yaml").read_text(encoding="utf-8"))
    spec = json.loads((task_dir / "taskspec.json").read_text(encoding="utf-8"))
    behavior = (task.get("null_agent") or {}).get("behavior")
    if not behavior:
        res.note = "题面没有 null_agent.behavior"
        res.ran = False
        return res
    art = P.null_artifact(task, behavior)
    out = task_dir / "solution" / "artifact.null.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(art, ensure_ascii=False, indent=1), encoding="utf-8")
    out.chmod(0o600)
    res.artifact = out
    res.log_rows = 0
    v = sch.validate(art, task=spec, gateway_log=[], config_id="null",
                     payload_profile=task.get("payload_profile"))
    res.findings = [str(f) for f in v.findings]
    res.probes = probe_counts(v)
    res.note = f"behavior={behavior}"
    return res


def probe_counts(verdict) -> dict[str, int]:
    """一个 Verdict → `{探针族: finding 数}`。`malformed` 归到 `MALFORMED_ROW`。"""
    out: dict[str, int] = {}
    for f in verdict.findings:
        key = f.probe if f.probe else MALFORMED_ROW
        out[key] = out.get(key, 0) + 1
    return out


def rows_as_results(rows: "list[dict]") -> list:
    """`probe_run_*.json` 的行 → `render_matrix` 认得的对象（只用到 `task_id` / `probes` / `artifact`）。

    `artifact` 不落在 json 里，按与 `ops/merge_o1.py` **同一条**规则还原：
    ok 或有 finding = 判过（有产物），其余 = 没产出 artifact（矩阵里画 `n/a`，不画 `·`）。
    """
    from types import SimpleNamespace
    return [SimpleNamespace(task_id=r["task_id"], stage=r.get("stage"),
                            template_id=r.get("template_id"), ok=r.get("ok"), rc=r.get("rc"),
                            findings=r.get("findings") or [], probes=r.get("probes") or {},
                            artifact=(r["task_id"] if r.get("ok") or r.get("findings") else None),
                            log_rows=r.get("log_rows"), note=r.get("note", ""),
                            evidence=r.get("evidence", []),
                            # 视图喂没喂过是**三态**：喂了 N 行 / 喂了 0 行 / 根本没喂（None）。
                            # 缺这个字段 render_matrix 会当场 AttributeError（merge_o1.py 也一直缺）。
                            tradability_rows=r.get("tradability_rows"),
                            stderr=r.get("stderr_tail", ""))
            for r in rows]


def render_matrix(results: list[Result], *, agent: str, tier: str = "custom/full") -> str:
    """**探针族 × 题目**的 finding 计数矩阵（裁定 2026-09-05）。

    * `agent=oracle`：**任一格非零即探针缺陷**，不是 oracle 缺陷。
      诚实的参考解在自己的题上不该触发任何一族。
    * `agent=f1`：**每族在其适用题上必须非零**。全零的族说明它「有发出点、
      有测试提到过族名」，却**从来没有在真产物上响过** —— 方向未经证实（D-30）。
    """
    rows = sorted(PROBE_IDS) + [MALFORMED_ROW]
    ordered = sorted(results, key=lambda x: x.task_id)
    tasks = [r.task_id for r in ordered]
    by = {r.task_id: r.probes for r in results}
    # **「没跑成」与「跑了且干净」不能长得一样。**
    # 第一版把两者都画成 `·`（零），于是 36 题崩在调用约定上的那一轮，
    # 矩阵显示**全零**、看起来像「所有探针都干净」—— 而其实什么都没判过。
    # 这与 `None`/`[]` 是同一族错误：不可得 ≠ 零。
    evaluable = {r.task_id for r in results if r.artifact is not None}
    n_a = [t for t in tasks if t not in evaluable]
    lines = [f"# 探针族 × 题目 finding 矩阵（agent = `{agent}`，档 = `{tier}`）", "",
             "> **档**（裁定 2026-09-05）：`smoke` = S1 四题（约 20 分钟，探针/oracle 有改动时跑）；",
             "> `full` = 40 题（**翻 D-30 第三列只认这一档**）。",
             "> 网关流量参考：S1/S3 每题约 5 分钟、600–900 次请求 —— 进 M7 的排网格参考。", ""]
    if agent == "oracle":
        lines += ["> **判据：全零。** 任一格非零 = **探针缺陷**，不是 oracle 缺陷 ——",
                  "> 诚实的参考解在自己的题上不该触发任何一族。逐条归因修探针。", ""]
    else:
        lines += ["> **判据（改注 2026-09-05）：`filler` 只针对静默补全那一族。** 它按题面 "
                  "`null_agent.behavior` 造产物（`empty` / `default_fill`），能触发的就是「欠定字段被填上」"
                  "与「口径被改」这一类 —— 也就是 `underdetermined` 族。",
                  "> **其余族一整行全零不再记作「方向未经证实」**：它们的方向由**各自的负例**证 ——",
                  "> `ops/run_probe_mutations.py`（取该题自己的 oracle 产物只破坏一处，该族必响、其余不响）",
                  "> 与 `reference/artifact_samples.ILLEGAL`（38 条手写非法样例）。",
                  "> 仍然为真的那一半：一整行全零**不能**被读成「这一族在这批题上干净」。", ""]
    lines += [f"**可判题目 {len(evaluable)}/{len(tasks)}**"
              + (f"；**没产出 artifact、因而不可判的 {len(n_a)} 题**："
                 + "、".join(f"`{t}`" for t in n_a[:12])
                 + ("…" if len(n_a) > 12 else "") if n_a else ""),
              "",
              "> `·` = 判过且零；`n/a` = **没产出 artifact，什么都没判**。",
              "> 两者不能混 —— 混了的话「36 题崩了」会显示成「全部干净」。", ""]
    lines.append("| 探针族 | " + " | ".join(tasks) + " | 行合计 |")
    lines.append("| --- |" + " --- |" * (len(tasks) + 1))

    def _cell(t: str, fam: str) -> str:
        if t not in evaluable:
            return "n/a"
        n = by.get(t, {}).get(fam, 0)
        return f"**{n}**" if n else "·"

    for fam in rows:
        cells = [_cell(t, fam) for t in tasks]
        tot_f = sum(by.get(t, {}).get(fam, 0) for t in evaluable)
        lines.append(f"| `{fam}` | " + " | ".join(cells) + f" | {tot_f} |")
    tot = [(str(sum(by.get(t, {}).values())) if t in evaluable else "n/a") for t in tasks]
    grand = sum(sum(by.get(t, {}).values()) for t in evaluable)
    lines.append("| **列合计** | " + " | ".join(tot) + f" | {grand} |")
    # 「全零」只在**可判**的题上算 —— 在没跑成的题上算全零，等于把崩溃当干净。
    silent = [f for f in sorted(PROBE_IDS)
              if not any(by.get(t, {}).get(f) for t in evaluable)]
    fed = [r.task_id for r in results if r.tradability_rows is not None]
    lines += ["", f"**喂了可交易性视图的题（N-120）**：{len(fed)}/{len(tasks)}"
              + ("" if len(fed) == len(tasks) else
                 " —— 没喂的题上 `calendar` 与 `missing_masquerading_as_signal` "
                 "两条**没被调用过**，它们那两格的 `·` 是不可得不是干净")]
    lines += ["", f"**在这 {len(evaluable)} 道可判题上全零的族（{len(silent)}）**："
                  + ("、".join(f"`{x}`" for x in silent) or "（无）"),
              "", "> 在 `oracle` 上全零是**应该的**；它**不能**用来说明这些族方向对 ——",
              "> 方向由 `ops/reports/m6/mutations.md`（逐族破坏样本，D-30 的另一半）证；",
              "> `filler` 那张矩阵只证 `underdetermined` 一族（改注 2026-09-05）。"]
    return "\n".join(lines) + "\n"



# ===== Y1b 实例层 =====
#
# **为什么实例层要单独一套渲染**：`render_matrix` 把题目摊成**列**。
# 40 题时它是一张 40 列的表，130 个实例时它是一张 130 列的表 —— 宽到没人读得完，
# 而且读者会把「实例」当成「新题」。实例不是新题：它是同一行参数表沿
# window / universe / factor_pool 换了取值。所以口径必须一直是
# 「**40 模板 / N 实例**」，矩阵也拆成两张：
#
#   表一 探针族 × **基点**（40 列，与出集那张同形），格子是该基点**所有实例**的 finding 合计；
#   表二 **逐实例**明细（instance_id / task_id / 参数 / 可判 / finding 数）。
#
# 身份的单位是**参数表的一行**（= 基点 task_id），不是模板目录 ——
# `S1/source_status` 被 `s1-rob-01` 与 `s1-rob-02` 两行复用，
# 按模板目录聚合会把两道题的实例混进同一列。见 `ops/mk_instances.py` 的模块 docstring。

#: 实例集的题集目录名（答案面落点 = `<ANSWER_ROOT>/tasks/<set_name>`，N-61 / D-28）。
INSTANCE_SET_NAME = "v1.0-instances"

#: 公开通道的实例集目录名。与私有**并列不覆盖**。
INSTANCE_SET_NAME_PUBLIC = "public/v1.0-instances-public"


def instance_rows(stages: str = "") -> "tuple[list[dict], dict[str, dict]]":
    """实例行 + 逐实例元数据。

    行直接取 `ops/mk_instances.Instance.row` —— 那正是 `packager.build_task` 的入参，
    与出集那 40 行**同形**，所以 `write_all` / `run_one` 一个字都不用改。

    返回 `(rows, meta)`；`meta[task_id]` 带 `instance_id` / `base_task_id` /
    `is_base` / `params_norm`，它们要**跟着结果一起落盘**，否则从累积文件渲矩阵时
    「这一行是哪个基点的哪个变体」就丢了。
    """
    from ops import mk_instances as MI

    spec = MI.load_spec()
    insts = MI.enumerate_instances(spec)
    want = {s.strip().upper() for s in stages.split(",") if s.strip()}
    rows: list[dict] = []
    meta: dict[str, dict] = {}
    for i in insts:
        if want and i.stage not in want:
            continue
        if i.task_id in meta:
            raise SystemExit(
                f"实例 task_id 撞了：{i.task_id}（{meta[i.task_id]['instance_id']} vs {i.instance_id}）—— "
                f"同 task_id 两份题面会让答案面互相覆盖，停下")
        rows.append(dict(i.row))
        meta[i.task_id] = {"instance_id": i.instance_id, "base_task_id": i.base_task_id,
                           "is_base": bool(i.is_base), "fingerprint": i.fingerprint,
                           "params_norm": i.norm, "stage": i.stage,
                           "template_id": i.template_id}
    return rows, meta


def _params_brief(norm: dict) -> str:
    """规范化参数字典 → 一行人读得懂的字。基准实例（空字典）显式写「基准」。"""
    if not norm:
        return "（基准）"
    out = []
    for k in sorted(norm):
        v = norm[k]
        s = str(v)
        if len(s) > 46:
            s = s[:43] + "…"
        out.append(f"{k}={s}")
    return "；".join(out)



#: 「没判成」的四类。**分类靠 note / stderr 的实证文本**，不靠猜。
#: `(类名, 关键词, 判法)`。**判法要么 `all` 要么 `any`，一类一类地说清楚** ——
#: 一刀切用 `any` 的后果实测过：`s4-eco-03` 的 stderr 是
#: `ValueError: work/factor_pool.parquet 里没有 'nan' 的行`，夹具**在**（2.6 MB），
#: 崩的是参考解自己挑因子那一步；只因为带了 `work/` 就被归成「缺夹具」。
#: 把「参考解崩了」显示成「缺件」，正是这一页要防的那种事。
_NA_KINDS = (
    ("挂起的探针题实例（设计如此）", ("E9c/E9d2",), "any"),
    ("缺夹具", ("FileNotFoundError", "work/"), "all"),
    ("与出集撞号（sim 会话工厂）", ("在多个出集里都有", "/sim/log"), "any"),
    #: **不要钉死秒数**：逐实例超时（X2 ⑥）之后 s2-rob-04 超时会印 `超时 1800s`，
    #: 钉 600 的话它就从「跑超时」掉进「没归类」—— 分类器把一类真失败显示成不认识的东西。
    ("跑超时", ("超时 ", "TimeoutExpired"), "any"),
)


def _why_not_evaluated(row: dict) -> str:
    """一行没产出 artifact 的原因归类。认不出的一律归「其余（要查）」——**不猜**。"""
    blob = f"{row.get('note') or ''}\n{row.get('stderr_tail') or ''}"
    for name, needles, how in _NA_KINDS:
        hit = all(n in blob for n in needles) if how == "all" else any(n in blob for n in needles)
        if hit:
            return name
    return "其余（要查）"


def _roster() -> "tuple[int, dict[str, str]]":
    """全名册：`(实例总数, {task_id: instance_id})`。取不到就退回 `(0, {})` ——
    **取不到时不许拿本批行数冒充总数**，那正好把「只跑了一半」写成「全跑完了」。"""
    try:
        _, meta = instance_rows()
    except Exception:                                       # noqa: BLE001
        return 0, {}
    return len(meta), {t: m["instance_id"] for t, m in meta.items()}


def _roster_stages() -> dict:
    """`{task_id: stage}`。覆盖率一节要靠它分辨「整阶段缺席」与「零散漏跑」。"""
    try:
        _, meta = instance_rows()
    except Exception:                                       # noqa: BLE001
        return {}
    return {t: m["stage"] for t, m in meta.items()}


def _export_set_o1(channel: str) -> dict:
    """出集那批 oracle 的结论：`{task_id: ok}`。取不到返回 `{}`（**不是**当成全绿）。"""
    import json as _json
    p = (_REPO / "ops" / "reports" / ("public" if channel == "public" else "")
         / "probe_run_oracle.cumulative.json")
    if not p.is_file():
        return {}
    try:
        return {r["task_id"]: bool(r.get("ok")) for r in _json.loads(p.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return {}

def render_matrix_instances(rows: "list[dict]", *, channel: str = "private",
                            n_templates: int = 40, set_name: str = "") -> str:
    """**按实例**渲 O1 矩阵：表一按基点聚合，表二逐实例展开。

    `rows` 是 `probe_run_instances.cumulative.json` 的行（含 Y1b 加的实例元数据）。
    没有元数据的旧行照样能渲 —— 它们的基点按 `task_id` 自己算，明细里标 `?`。
    """
    fams = sorted(PROBE_IDS) + [MALFORMED_ROW]
    rows = sorted(rows, key=lambda r: (str(r.get("stage") or ""), str(r["task_id"])))
    # **可判 = 真有产物**。`ok` 或有 finding 都说明校验器查过；其余是「什么都没判」。
    # 这与 `rows_as_results` 是同一条规则 —— 两处不一致的话，同一份数据两张表会给出不同的分母。
    def _evaluable(r: dict) -> bool:
        return bool(r.get("ok") or r.get("findings"))

    bases: dict[str, list[dict]] = {}
    for r in rows:
        b = str((r.get("base_task_id") or r["task_id"]))
        bases.setdefault(b, []).append(r)
    base_ids = sorted(bases)

    n_inst = len(rows)
    n_eval = sum(1 for r in rows if _evaluable(r))
    zero = [r for r in rows if _evaluable(r) and not (r.get("probes") or {})]
    nonzero = [r for r in rows if _evaluable(r) and (r.get("probes") or {})]
    na = [r for r in rows if not _evaluable(r)]

    ch = "私有" if channel == "private" else "公开"
    L: list[str] = []
    L += [f"# 实例层 O1 矩阵（{ch}通道，agent = `oracle`）", "",
          f"> **口径：{n_templates} 模板 / {n_inst} 实例。** 「模板」= 出集参数表的 "
          f"{n_templates} 行（模板**目录**只有 39 个 —— `S1/source_status` 被 `s1-rob-01` 与 "
          f"`s1-rob-02` 两行复用）；「实例」= 同一行参数沿 window / universe / factor_pool "
          f"换取值得到的变体，**不是新题**。身份的单位是参数表的一行，见 `ops/mk_instances.py`。", ""]
    if set_name:
        L += [f"> 答案面落点：`$GB/reference/tasks/{set_name}/`。", ""]
    L += ["> **判据（O1）：全零。** 但**两类行的归因是相反的**，别混着读 ——", "",
          "> * **探针族**那些行非零 = **探针缺陷**：诚实的参考解在自己的题上不该触发任何一族。",
          "> * **`(malformed)`** 那一行非零 = **oracle 自己的产物格式不对**。产物是我们写的，"
          "它连格式都对不上，用它当 gold 只会把错误传下去（`run_oracles` 模块 docstring）。",
          "",
          "> 实例只换取值不换题型，所以两条对实例都逐字成立 —— 而**换了取值才现形**的问题，"
          "正是这一页存在的理由。", "",
          f"**零 finding 的实例 {len(zero)}/{n_inst}**；"
          f"**非零的 {len(nonzero)}**；"
          f"**没产出 artifact、因而什么都没判的 {len(na)}**。"
          f"（可判 {n_eval}/{n_inst}）", "",
          "> `·` = 判过且零；`n/a` = 该基点**一个实例都没产出 artifact**；"
          "数字 = 该基点所有实例的 finding 合计。**不可得与零不能长得一样。**", ""]

    # ---------------- 表一：探针族 × 基点（聚合）
    L += ["## 表一 探针族 × 基点（实例聚合）", ""]
    L.append("| 探针族 | " + " | ".join(base_ids) + " | 行合计 |")
    L.append("| --- |" + " --- |" * (len(base_ids) + 1))

    def _cell(b: str, fam: str) -> str:
        ev = [r for r in bases[b] if _evaluable(r)]
        if not ev:
            return "n/a"
        n = sum((r.get("probes") or {}).get(fam, 0) for r in ev)
        return f"**{n}**" if n else "·"

    for fam in fams:
        cells = [_cell(b, fam) for b in base_ids]
        tot = sum((r.get("probes") or {}).get(fam, 0)
                  for b in base_ids for r in bases[b] if _evaluable(r))
        L.append(f"| `{fam}` | " + " | ".join(cells) + f" | {tot} |")
    col_tot = []
    for b in base_ids:
        ev = [r for r in bases[b] if _evaluable(r)]
        col_tot.append(str(sum(sum((r.get("probes") or {}).values()) for r in ev)) if ev else "n/a")
    grand = sum(sum((r.get("probes") or {}).values()) for r in rows if _evaluable(r))
    L.append("| **列合计** | " + " | ".join(col_tot) + f" | {grand} |")
    L += ["",
          "| 基点 | 实例数 | 可判 | 零 finding | 非零 |",
          "| --- | --- | --- | --- | --- |"]
    for b in base_ids:
        grp = bases[b]
        ev = [r for r in grp if _evaluable(r)]
        z = [r for r in ev if not (r.get("probes") or {})]
        L.append(f"| `{b}` | {len(grp)} | {len(ev)} | {len(z)} | {len(ev) - len(z)} |")

    # ---------------- 表二：逐实例明细
    L += ["", "## 表二 逐实例明细", "",
          "| 实例 id | task_id | 基点 | 参数 | 可判 | finding | 视图行 | 日志行 |",
          "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        iid = str(r.get("instance_id") or "?")
        b = str(r.get("base_task_id") or "?")
        pb = _params_brief(r.get("params_norm") or {})
        ev = _evaluable(r)
        nf = sum((r.get("probes") or {}).values()) if ev else 0
        fin = ("·" if ev and not nf else (f"**{nf}**" if ev else "n/a"))
        tr = r.get("tradability_rows")
        lr = r.get("log_rows")
        L.append(f"| `{iid}` | `{r['task_id']}` | `{b}` | {pb} | "
                 f"{'是' if ev else '否'} | {fin} | "
                 f"{'—' if tr is None else tr} | {'—' if lr is None else lr} |")

    # ---------------- 非零与不可判：逐条列原因
    L += ["", "## 非零的实例（逐条原因）", ""]
    if not nonzero:
        L += ["（无）—— 在这批可判的实例上 O1 全绿。", ""]
    else:
        for r in nonzero:
            fams_hit = "、".join(f"`{k}`×{v}" for k, v in sorted((r.get("probes") or {}).items()))
            L += [f"* `{r.get('instance_id') or r['task_id']}`（task_id `{r['task_id']}`，"
                  f"基点 `{r.get('base_task_id') or '?'}`）：{fams_hit}"]
            for f in (r.get("findings") or [])[:6]:
                L.append(f"  * {str(f)[:260]}")
        L.append("")
    L += ["## 没产出 artifact 的实例（什么都没判）", ""]
    if not na:
        L += ["（无）", ""]
    else:
        kinds: dict[str, list[dict]] = {}
        for r in na:
            kinds.setdefault(_why_not_evaluated(r), []).append(r)
        L += ["| 归类 | 个数 |", "| --- | --- |"]
        for k in sorted(kinds, key=lambda x: -len(kinds[x])):
            L.append(f"| {k} | {len(kinds[k])} |")
        L.append("")
        for k in sorted(kinds, key=lambda x: -len(kinds[x])):
            L += [f"**{k}**", ""]
            for r in kinds[k]:
                why = (r.get("note") or "").strip()
                if not why:
                    tail = (r.get("stderr_tail") or "").strip().splitlines()
                    why = tail[-1] if tail else "（无说明）"
                L += [f"* `{r.get('instance_id') or r['task_id']}`（task_id `{r['task_id']}`，"
                      f"基点 `{r.get('base_task_id') or '?'}`，rc={r.get('rc')}）：{str(why)[:300]}"]
            L.append("")

    # ---------------- 覆盖率：对着**全名册**报，不对着本批报
    total, roster = _roster()
    roster_stage = _roster_stages()
    if total:
        ran = {r["task_id"] for r in rows}
        missing = sorted(set(roster) - ran)
        L += ["## 覆盖率（对着全名册，不对着本批）", "",
              f"**跑过的 {len(ran)}/{total} 个实例**；**本轮一次都没跑的 {len(missing)} 个**。", ""]
        if missing:
            # 「整个阶段一个都没跑」= 范围没覆盖到；「零散缺几个」= 漏跑。两件事分开说。
            ran_stages = {str(r.get("stage") or "") for r in rows}
            miss_by_stage: dict[str, list[str]] = {}
            for t in missing:
                miss_by_stage.setdefault(str(roster_stage.get(t) or "?"), []).append(t)
            whole = sorted(s for s in miss_by_stage if s not in ran_stages)
            partial = sorted(s for s in miss_by_stage if s in ran_stages)
            L += ["> 没跑 ≠ 跑过且干净。下面这些实例在本页**没有任何结论**。", ""]
            if whole:
                L += [f"**整个阶段一个都没跑：{'、'.join(whole)}** —— 合计 "
                      f"{sum(len(miss_by_stage[s]) for s in whole)} 个实例。"
                      f"这是**范围没覆盖到**，不是漏跑。", ""]
            for s in partial:
                ts = miss_by_stage[s]
                L += [f"**{s} 还差 {len(ts)} 个**：" + "、".join(f"`{t}`" for t in ts), ""]
            if whole:
                L += ["<details><summary>整阶段缺席的实例清单（展开）</summary>", ""]
                for s in whole:
                    L += [f"* {s}：" + "、".join(f"`{t}`" for t in miss_by_stage[s])]
                L += ["", "</details>", ""]
    else:
        L += ["## 覆盖率", "",
              "> **名册取不到**（`ops/mk_instances.py` 枚举失败）——"
              "本页只能说「跑过的这些」，说不出「一共该有多少」。"
              "**不拿本批行数冒充总数。**", ""]
    L += ["---", "",
          "> **三控与破坏样本不按实例重跑**（Y1b 裁定）：`ops/run_controls.py` 与 "
          "`ops/run_probe_mutations.py` 验的是**判据面** —— 「探针会不会误伤诚实产物」"
          "与「破坏一处该族会不会响」。那两件事的被测对象是**校验器**，不是题面；"
          "换窗口 / 换宇宙 / 换因子池不会换掉校验器的任何一条分支。"
          "实例层要证的是「同一道题换了取值，参考解仍然零 finding」——"
          "这正是本页的表一与表二。重跑三控只会得到逐字相同的结论，"
          "代价是 130 × 三控的网关时间。", ""]
    # ---------------- 基准实例 vs 出集同题
    exp = _export_set_o1(channel)
    base_rows_ = [r for r in rows if r.get("is_base")]
    if exp and base_rows_:
        agree, real, infra, unknown = [], [], [], []
        for r in base_rows_:
            t = r["task_id"]
            mine = bool(r.get("ok"))
            if t not in exp:
                unknown.append((t, mine))
            elif exp[t] == mine:
                agree.append((t, mine))
            elif not _evaluable(r):
                # 实例层**根本没判成**（缺夹具 / 撞号 / 挂起）——上一节已逐条给过原因。
                # 它不是「同一道题两次结论不同」，把它算进告警会把真告警埋掉。
                infra.append((t, _why_not_evaluated(r)))
            else:
                real.append((t, mine, exp[t]))
        L += ["## 基准实例 vs 出集同题（一致性对照）", "",
              "> 基准实例 = 参数一个都没换的那个实例，与出集的同号题**是同一道题**"
              "（同一行参数、同一份题面），只是在实例集里**另跑了一遍**。"
              "两边结论必须一致；**两边都判过、结论却不同**只有两种可能 —— "
              "要么题面其实不同（实例生成器漂了），要么 O1 本身不稳定。**两种都得知道。**", "",
              f"**一致 {len(agree)}**；**两边都判过但结论不同 {len(real)}（这一栏非零就是告警）**；"
              f"**实例层没判成、对不上的 {len(infra)}（基础设施，原因见上一节）**；"
              f"**出集那边没有记录、对不了的 {len(unknown)}**。", ""]
        for t, mine, theirs in real:
            L.append(f"* **告警** `{t}`：两边都判过，实例层 ok={mine}，出集 ok={theirs}")
        for t, why in infra:
            L.append(f"* 没判成 `{t}`：{why}（出集那边是绿的）")
        for t, mine in unknown:
            L.append(f"* 对不了 `{t}`：出集的 `probe_run_oracle.cumulative.json` 里没有这一行"
                     f"（实例层 ok={mine}）")
        L.append("")
    elif base_rows_:
        L += ["## 基准实例 vs 出集同题（一致性对照）", "",
              "> **出集那批的结论取不到**（`probe_run_oracle.cumulative.json` 不在或读不出）——"
              "这一节没有结论，**不当成一致**。", ""]

    ages = sorted({str(r.get("at", "?"))[:16] for r in rows})
    L += [f"> **本矩阵渲自累积文件**：{n_inst} 行、{len(ages)} 次跑批"
          f"（{', '.join(ages)}）。逐行 `at` 标着这一行是哪一次跑出来的，"
          f"**只有更新的行会覆盖更旧的**。", ""]
    return "\n".join(L)



def _result_row(r: "Result", meta: "dict[str, dict] | None" = None) -> dict:
    """一个 `Result` → 落盘的一行。**实例元数据跟着结果一起落盘**（Y1b）。

    为什么不能只落 `task_id`：矩阵是从**累积文件**渲的（红队阶段六），
    而「这一行是哪个基点的哪个变体、换了什么取值」只有跑批当时知道。
    不落盘的话，隔一批再渲矩阵就只剩一列 `task_id` —— 而实例的 `task_id`
    是发号发出来的（`s4-rob-05`），从它看不出基点是 `s4-rob-01` 还是别的。
    """
    row = {"task_id": r.task_id, "stage": r.stage, "template_id": r.template_id,
           "ok": r.ok, "rc": r.rc, "log_rows": r.log_rows, "note": r.note,
           "evidence": r.evidence, "probes": r.probes, "at": _NOW,
           "tradability_rows": r.tradability_rows,
           "stderr_tail": r.stderr[-600:], "findings": r.findings}
    m = (meta or {}).get(r.task_id)
    if m:
        row.update({k: m[k] for k in ("instance_id", "base_task_id", "is_base",
                                      "fingerprint", "params_norm")})
    return row

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="逐题跑 oracle 并校验（O1：零 finding）")
    ap.add_argument("--tier", choices=("smoke", "full"), default="",
                    help="smoke=S1 四题（约 20 分钟，探针/oracle 有改动时跑）；"
                         "full=40 题（翻 D-30 第三列时跑）")
    ap.add_argument("--tasks", default="", help="逗号分隔；与 --tier 二选一")
    ap.add_argument("--params", default=str(PARAMS))
    ap.add_argument("--start-gateway", action="store_true",
                    help="自己起网关并在结束时**保证停掉**（跑测试前网关必须是停的）")
    ap.add_argument("--agent", choices=("oracle", "f1"), default="oracle",
                    help="oracle=跑参考解；f1=按题面 null_agent.behavior 造填充产物")
    ap.add_argument("--out", default="")
    ap.add_argument("--answer-root", default="",
                    help="答案面参考根（默认 ops/export_bundle.ANSWER_ROOT）。"
                         "公开通道与私有**并列不覆盖**，所以要能换根")
    ap.add_argument("--set-name", default="",
                    help="题集目录名（默认用题自己的 set_id）。公开通道用 v1.0-smoke-public")
    ap.add_argument("--no-batch-lock", action="store_true",
                    help="**外层已经持有网关锁时**才加（例如 ops/public_gateway.sh run -- …，它自己就是 ops/gateway_lock.py 起的）。"
                         "网关锁是 fcntl.flock，同一把锁在**另一个进程**里再拿一次会永久阻塞 —— "
                         "表现是「网关起来了、批一条都没跑、也不报错」。裸跑时不要加：不拿锁并发 = 网关 OOM（N-125）")
    ap.add_argument("--instances", action="store_true",
                    help="**跑实例层**（Y1b）：题行取自 ops/mk_instances.py 枚举出来的约 130 个实例，"
                         "而不是 --params 的 40 行。落点默认 v1.0-instances，"
                         "明细默认 ops/reports/probe_run_instances.json，矩阵 probe_matrix_instances.md")
    ap.add_argument("--stages", default="",
                    help="--instances 时只跑这些阶段（逗号分隔，如 S1,S2）。分批跑用它")
    ap.add_argument("--resume", action="store_true",
                    help="跳过累积文件里**已经零 finding**的题 —— 分批 / 断点续跑用。"
                         "有 finding 的与没产出的照跑（它们正是要重试的那些）")
    ap.add_argument("--limit", type=int, default=0,
                    help="本批最多跑几道（0=不限）。与 --resume 合用即「每次推进 N 道」")
    ap.add_argument("--no-tradability", action="store_true",
                    help="不给校验器喂可交易性视图（N-120 之前的行为）。"
                         "喂了才谈得上 calendar 与 missing_masquerading_as_signal 被调用过")
    a = ap.parse_args(argv)
    reports = _REPO / "ops" / "reports"
    if not a.out:
        a.out = str(reports / f"probe_run_{a.agent}.json")

    meta: dict[str, dict] = {}
    if a.instances:
        rows, meta = instance_rows(a.stages)
        if not a.set_name:
            a.set_name = (INSTANCE_SET_NAME_PUBLIC if cfg.channel() == "public"
                          else INSTANCE_SET_NAME)
        if a.out == str(reports / f"probe_run_{a.agent}.json"):
            a.out = str(reports / "probe_run_instances.json")
    else:
        rows = P.load_params(a.params)
        if a.stages:
            raise SystemExit("--stages 只在 --instances 时有意义（出集那 40 行用 --tasks 选）")
    #: **分档**（裁定 2026-09-05）：探针或 oracle 有改动 → 冒烟档；
    #: 翻 D-30 第三列 → 全量档。矩阵报告里标明本次是哪一档。
    SMOKE = ("s1-cor-01", "s1-rob-01", "s1-eco-01", "s1-ops-01")
    if a.tier == "smoke" and not a.tasks:
        a.tasks = ",".join(SMOKE)
    tier = a.tier or ("smoke" if set(a.tasks.split(",")) == set(SMOKE) else "custom/full")
    want = [t for t in a.tasks.split(",") if t.strip()]
    if want:
        rows = [r for r in rows if r["task_id"] in want]
        missing = sorted(set(want) - {r["task_id"] for r in rows})
        if missing:
            raise SystemExit(f"参数表里没有：{missing}")
    # **续跑**（Y1b）：130 个实例分批跑，跳过累积文件里**已经零 finding** 的。
    # 只跳零 finding 的那些 —— 有 finding 与没产出的正是要重试的，跳了就再也修不掉。
    if a.resume:
        cumf = Path(a.out).with_suffix(".cumulative.json")
        done: set = set()
        if cumf.is_file():
            done = {x["task_id"] for x in json.loads(cumf.read_text(encoding="utf-8"))
                    if x.get("ok")}
        n0 = len(rows)
        rows = [r for r in rows if r["task_id"] not in done]
        print(f"--resume：累积里已零 finding 的 {len(done)} 题跳过，本批 {len(rows)}/{n0}")
    if a.limit and len(rows) > a.limit:
        rows = rows[:a.limit]
        print(f"--limit：本批只跑前 {a.limit} 道")
    if not rows:
        print("本批没有要跑的题（--resume 把它们都跳了？）—— 直接退出，不去动矩阵")
        return 0

    proc = None
    if a.start_gateway:
        if gateway_up():
            raise SystemExit("网关已经在跑 —— 不去接管别人起的进程；要么别加 --start-gateway，"
                             "要么先把它停掉。接管会让「谁该负责停」变得没人负责")
        proc = subprocess.Popen([sys.executable, "-m", "gateway.run"], cwd=str(_REPO),
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        if not wait_gateway():
            err = ""
            if proc is not None:
                proc.terminate()
                try:
                    err = (proc.communicate(timeout=5)[1] or b"").decode()[-800:]
                except subprocess.TimeoutExpired:
                    proc.kill()
            raise SystemExit(f"网关没起来（{gateway_url()}）。**没有网关就没有交叉核**，"
                             f"这时候跑出来的绿是假的。\n{err}")
        caps = json.loads((_REPO / "ops" / "capabilities.json").read_text(encoding="utf-8"))
        caps = {k: v for k, v in caps.items() if isinstance(v, bool)}
        dirs, blocked = write_all(rows, capabilities=caps,
                                  answer_root=Path(a.answer_root) if a.answer_root else None,
                                  set_name=a.set_name)
        runner = (functools.partial(run_one, tradability=not a.no_tradability)
                  if a.agent == "oracle" else run_f1)
        results = []
        # **独占网关**（N-125）：跑批与 agent 真跑不许叠着打单 worker。
        # `f1` 填充器一次网关都不调，不用占锁 —— 占了反而会挡住真跑。
        lock = (_batch_lock(f"run_oracles --agent {a.agent} {len(rows)} 题")
                if a.agent == "oracle" and not a.no_batch_lock else contextlib.nullcontext())
        with lock:
            for r in rows:
                if r["task_id"] in dirs:
                    results.append(runner(dirs[r["task_id"]], r))
                else:
                    results.append(Result(r["task_id"], r["stage"], r["template_id"],
                                          note="落盘被拦：" + blocked[r["task_id"]]))
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()

    okn = sum(1 for r in results if r.ok)
    label = "oracle（O1：零 finding）" if a.agent == "oracle" else "F1 填充器（每族应非零）"
    print(f"\n=== {label}：{okn}/{len(results)} 零 finding ===\n")
    for r in sorted(results, key=lambda x: x.task_id):
        flag = "✓" if r.ok else "✗"
        head = f"  {flag} {r.task_id:<12} {r.stage} {r.template_id:<24} rc={r.rc} log={r.log_rows}"
        print(head)
        for e in r.evidence:
            print(f"      **证据源**: {e[:150]}")
        if not r.ok:
            if r.note:
                print(f"      {r.note}")
            if r.stderr:
                print("      stderr: " + r.stderr.splitlines()[-1][:160])
            for f in r.findings[:4]:
                print(f"      finding: {f[:160]}")
    out = Path(a.out)
    cfg.create_dir(out.parent)
    out.write_text(json.dumps(
        # 每行带 `at`：定点重跑会**整份覆盖**这个文件，`ops/merge_o1.py` 靠它把旧批与新批拼起来，
        # 并让「这一行是哪一次跑出来的」在矩阵页脚看得见 —— 不带时间戳的拼接就是在编一张现在并不成立的表。
        [_result_row(r, meta) for r in sorted(results, key=lambda x: x.task_id)],
        ensure_ascii=False, indent=1), encoding="utf-8")
    out.chmod(0o600)
    # **累积那一份**：定点重跑会整份覆盖上面这个文件，于是「40 题的 O1 矩阵」跑一次 4 题就只剩 4 行 ——
    # 两份报告都从它读数，结果是**报告悄悄退化成局部**（2026-09-06 实测：验证验证器报告 ① 显示 4 题）。
    # 累积文件按 task_id 取**最新**的那一行（每行带 `at`），谁也不会因为一次定点重跑而消失。
    cum = out.with_suffix(".cumulative.json")
    prev = {r["task_id"]: r for r in json.loads(cum.read_text(encoding="utf-8"))} if cum.is_file() else {}
    for r in sorted(results, key=lambda x: x.task_id):
        row = _result_row(r, meta)
        if prev.get(r.task_id, {}).get("at", "") <= _NOW:
            prev[r.task_id] = row
    cum.write_text(json.dumps([prev[k] for k in sorted(prev)], ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    cum.chmod(0o600)
    # 矩阵与明细**必须落在同一个目录**：两条通道并列跑时，明细写进 ops/reports/public/
    # 而矩阵仍写 ops/reports/ 的话，公开那一跑会把私有的矩阵**就地覆盖**，
    # 而覆盖后的文件从内容上看不出是哪条通道跑的。默认 --out 时 parent 仍是 ops/reports/，行为不变。
    mat = out.parent / ("probe_matrix_instances.md" if a.instances
                        else f"probe_matrix_{a.agent}.md")
    # **矩阵也从累积文件渲**（红队阶段六 major）。此前它渲的是「这一次跑批的 results」：
    # 定点重跑一道题，40 题的矩阵就地变成「可判题目 1/1」，而两份报告都还写着
    # 「数据源是累积文件，定点重跑不会把它打回局部」—— 明细是累积的，矩阵不是。
    # 读者按引用去查，看到的是一张单列矩阵，会以为「只判了一道题」。
    cum_rows = json.loads(cum.read_text(encoding="utf-8"))
    md = (render_matrix_instances(cum_rows, channel=cfg.channel(), set_name=a.set_name)
          if a.instances else
          render_matrix(rows_as_results(cum_rows), agent=a.agent, tier=tier))
    if len(cum_rows) > len(results) and not a.instances:
        ages = sorted({str(r.get("at", "?"))[:16] for r in cum_rows})
        md += (f"\n> **本矩阵渲自累积文件** `{cum.name}`：{len(cum_rows)} 行、"
               f"{len(ages)} 次跑批（{', '.join(ages)}）。本次跑批只覆盖了其中 {len(results)} 题"
               f"（{', '.join(sorted(r.task_id for r in results))}）——"
               f"逐行 `at` 标着这一行是哪一次跑出来的，**只有更新的行会覆盖更旧的**。\n")
    mat.write_text(md, encoding="utf-8")
    mat.chmod(0o600)
    print(f"\n明细 {out}\n矩阵 {mat}")
    if a.agent == "oracle":
        return 0 if okn == len(results) else 1
    # F1 侧的判据是**每族在其适用题上非零**，全零才是问题 —— 与 oracle 侧相反。
    silent = [f for f in sorted(PROBE_IDS)
              if not any(r.probes.get(f) for r in results)]
    print(f"F1：本批全零的族 {len(silent)} 个" + (f"：{silent}" if silent else ""))
    return 1 if silent else 0


if __name__ == "__main__":
    raise SystemExit(main())
