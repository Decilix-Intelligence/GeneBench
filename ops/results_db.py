#!/usr/bin/env python3
"""卡 5.4（线 C，2026-09-07）：**结果库** —— 主表 / Table B / 适配赛道表的单一来源。

为什么要有它：到今天为止，「一次结算的结果」只存在于 `ops/reports/<batch>/` 里 ——
每批一份 `records.json` 加一堆已经聚合好的 CSV。于是三件事做不到：

1. **跨批查询**：「所有 `set_version=1.0.12` 的 strict 臂」要靠人去 16 个目录里 glob；
2. **混轴可见**：`ops/reports/m6_all` 是 m6（题面 `1.0.7`）与 m6b（`1.0.9`）合出来的，
   `table_a` 按 `(config_id, arm)` 分组，两个题面版本的 run **合成了同一行 pass@1**
   （红队 5.1 finding E1）。表上写了 `MIXED:`，但**没有任何一步拦着不让出这张表**；
3. **四条版本轴齐全**：记录里现在带的是 `set_version` / `reference_version` /
   `runner_version` / `image_digest`（`scorer.score_run.VERSION_AXES` —— 那是**注入面**
   的四条），而票据 N-207 说的四个「版本字段」是 `set_version` / `reference_version` /
   `protocol_version` / `channel`。后两条**一条都不在记录里**。

本模块落 `$GENEBENCH_ROOT/results/v1/results.jsonl`（追加式，一行一条 run 记录）
+ `index.json`（元信息）。它**不重算任何判据** —— 判据在 `scorer/` 里，这里只是收纳与检索。

四条版本轴（`AXES`）
--------------------
* `set_version` —— 任务集轴，取自记录（`inject.json.frozen_manifest.set_version`）；
* `reference_version` —— 参考轴，同上（`reference_manifest.reference_version`）；
* `protocol_version` —— 协议轴，`geneprotocol_v1@<12 位摘要>`，摘要 = 封闭清单
  （`ops/mk_protocol_manifest.py::STATIC` 那三件：`validate_artifact.py` / `README.md` /
  `contract.md`）逐件 `名:sha256` 排序后再哈希。
  **为什么不直接读 `MANIFEST.json` 的 `version`**：那个键根本不存在（清单里只有
  `protocol_id` / `status` / `released_at` / `artifacts`），而 `artifacts` 是会变的 ——
  实测 m6 那批注进容器的 `validate_artifact.py` 是 `f8b8ad26…`，今天清单里写的是
  `ca26c78f…`。所以协议轴必须**按 run 当时真的注进去的字节**算，不能拿今天的清单去追认。
  取值由 `protocol_by_run()` 从 `runs_in/<batch>/<run_id>/inject.json` 的
  `files["work/protocol/<件>"]` **逐 run** 反算 —— 那是 runner 注入时盖的章。
  裸臂（`open`）不发协议工件，逐 run 记 `NO_PROTOCOL`（红队 5.rt finding 4）。
  **这里原来是按批取值的**，理由是「按臂取值会让每一批都变成混轴、每张表都出不来」——
  那个担心是真的，但解法不是把轴写粗：批级声明盖在裸臂上，`--filter protocol_version=<摘要>`
  就会选出一堆从来没见过该协议的 run，而这条轴的立卡理由恰恰是「哪个 run 拿到了哪一版协议」。
  现在的解法是逐 run 写轴 + `mixed_axes` 对这条轴**按 arm_kind 分组判**：裸臂那一组恒为
  `none`，它与协议臂的摘要并排**不算混轴**（事实是两个臂跑在同一次发布上）；
  协议臂之间出现两个摘要才是混轴，那一条仍然拒绝出表。
* `channel` —— 数据通道（`genebench_config.CHANNELS`：`private` / `public`）。
  通道决定网关背后是哪套快照表，**同一道题在两条通道上不是同一道题**。
  伴随字段 `channel_build`（公开通道快照的 `build_info.json` 摘要）是元信息不是轴：
  轴要能分组，而 build 指纹每重建一次就变一个值。

主键 = `(batch, run_id)`，不是 `run_id`
--------------------------------------
实测冲突：`s2-cor-01.strict.cfg-codex-deepseek.r01` 在 `a4`（`set_version=1.0.12`）与
`m6`（`1.0.7`）里各有一条，**是两次不同的运行**（`run_id` 由 task/arm/config/seq 拼成，
不含批次，跨批必然会撞）。按裸 `run_id` 去重会把后进来的那条判成「内容冲突」而拒掉 ——
丢数据比留一个可见的重名更糟。所以键取 `(batch, run_id)`，重名在 `index.json` 的
`run_id_reused_across_batches` 里单列，`versions()` 也会带出来。

用法::

    python ops/results_db.py backfill                    # 把 ops/reports/*/records.json 全收进来
    python ops/results_db.py versions                    # 库里出现过的版本轴组合
    python ops/results_db.py query --filter batch=m6 --filter arm=strict
    python ops/results_db.py stat
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import genebench_config as cfg                              # noqa: E402
from ops import report_io as RIO                            # noqa: E402

SCHEMA_VERSION = "1.0"

#: 四条版本轴（票据 N-207 的「四个版本字段」）。**缺一即拒** —— 一条不知道自己是哪一版
#: 跑出来的记录，进了库就再也切不开（红队 5.1 finding E1 的教训：只能重跑）。
AXES: tuple[str, ...] = ("set_version", "reference_version", "protocol_version", "channel")

#: **被取代**的行（N-645，用户裁定 ⑤）。重算改了判据值时，旧行不删、只标 ——
#: 「曾经发表过的是哪一版」是可查的事实，删掉它等于把已经发出去的那张表变成无出处。
#: 读侧默认**不过滤**：`query(superseded=...)` 显式筛；出表侧自己决定要不要排除。
SUPERSEDED_FIELD = "superseded"
SUPERSEDED_AT = "superseded_at"
SUPERSEDED_BY = "superseded_by"
SUPERSEDED_NOTE = "superseded_note"

#: 身份键。`seed` 就是记录里的 `seq`（runner 的 `--seq N`，一个种子一次运行）——
#: 库里两个名字都留着，取哪个都对得上。
IDENTITY: tuple[str, ...] = ("batch", "task_id", "config_id", "arm", "seed", "run_id")

#: 主赛道记录必须带的结算字段（**键必须在**，值可以是 None —— 「算不出」与「没这一列」不同）。
RESULT_FIELDS: tuple[str, ...] = (
    "validity", "sr_bucket", "run_status", "correctness", "effect",
    "l3_kind", "l3_pass", "l3_score", "steps",
    "tokens_prompt", "tokens_completion", "cost_usd",
    "probe_states", "overreach", "unbounded_requests", "budget_exhausted",
)

#: 适配赛道记录的身份键（`scorer.adaptation.AdaptationResult.as_record`：没有 task_id / seq）。
IDENTITY_ADAPT: tuple[str, ...] = ("batch", "example_id", "config_id", "arm", "run_id")
RESULT_FIELDS_ADAPT: tuple[str, ...] = ("level", "outcome", "valid", "matched", "expected_outcome")

#: 机器标识（用户裁定 ⑮，2026-09-10）。值由 `runner.inject.machine_id()` 算，
#: 这里只**认**它：新记录从 `run_id` 的 `@` 段反算，旧记录没有这一段 → 字段整个不出现。
#:
#: **为什么是「不出现」而不是 `None`**：`ingest` 按 `content_hash` 判「同主键内容是否一致」，
#: 给既有记录补一个 `machine_id: null` 会让库里那 126 条的指纹全变一遍 ——
#: 于是 `run_joblist` 每跑完一批做的那次幂等回填会在「同主键内容不同」上当场抛。
#: 一个字段的默认值能把整条流水线打红，这就是为什么它只在真的算得出来时才写。
MACHINE_FIELD = "machine_id"
#: 与 `runner.inject.MACHINE_SEP` 同一个字符。**不 import runner** —— 结果库跑在数据面，
#: `runner.inject` 顶层拉执行面的东西；一个字符的常量不值得把那条依赖拽进来（两处各有测试钉住相等）。
MACHINE_SEP = "@"

PROTOCOL_ID = "geneprotocol_v1"
#: 这次注入**没有完整的封闭清单三件**时，协议轴上的显式取值（红队 5.rt finding 4）。
#: 「这次注入里没有那一版协议」是一个事实，不是「不知道」—— 所以它有名字，而不是 None：
#: 空值进不了库（四条轴缺一即拒），而拿这一批 GQ 臂的摘要去盖裸臂，等于说裸臂见过它没见过的东西。
#:
#: **不等于「一个协议工件都没有」**：实测 `a4` 的 `doc` 臂注进去的是三件里的两件
#: （`work/protocol/{README.md,contract.md}`，没有 `validate_artifact.py`），`hint` 臂一件都没有，
#: 两者在这条轴上都记 `none` —— 因为这条轴量的是「拿到的是哪一版**封闭清单**」，
#: 而半份清单不构成一个版本（`protocol_digest` 缺件即抛，不拿两件凑一个摘要）。
#: 逐件的投放差异是**臂**的定义（`genetask/arms.yaml`），在 `arm` / `arm_kind` 两列上看，
#: 不在这条轴上看。
NO_PROTOCOL = f"{PROTOCOL_ID}@none"
#: 协议封闭清单里**每道题都一样**的那三件（与 `ops/mk_protocol_manifest.py::STATIC` 同源）。
PROTOCOL_STATIC: tuple[str, ...] = ("validate_artifact.py", "README.md", "contract.md")
PROTOCOL_MANIFEST = _REPO / "ops" / "protocol" / PROTOCOL_ID / "MANIFEST.json"

#: 合表目录：它们的记录是别的批的**副本**（`ops/combine_batches.py` 只加了一个 `batch` 字段）。
#: 收它们等于把同一条 run 收两遍 —— 库里只收原批。
DERIVED_BATCHES: frozenset[str] = frozenset({"m6_all"})


class ResultsDBError(RuntimeError):
    pass


# ------------------------------------------------------------------ 落点

def db_root(root: Path | str | None = None) -> Path:
    return Path(root) if root is not None else (cfg.RESULTS / "v1")


def results_path(root: Path | str | None = None) -> Path:
    return db_root(root) / "results.jsonl"


def index_path(root: Path | str | None = None) -> Path:
    return db_root(root) / "index.json"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------ 协议轴

def protocol_digest(shas: dict[str, str]) -> str:
    """封闭清单三件 → `geneprotocol_v1@<12 位>`。缺件即抛（不拿两件凑一个摘要）。"""
    missing = [n for n in PROTOCOL_STATIC if not shas.get(n)]
    if missing:
        raise ResultsDBError(f"协议封闭清单缺件：{missing}")
    body = "\n".join(f"{n}:{shas[n]}" for n in PROTOCOL_STATIC)
    return f"{PROTOCOL_ID}@{hashlib.sha256(body.encode('utf-8')).hexdigest()[:12]}"


def protocol_version_repo() -> str:
    """**今天仓库里**那一版协议的轴值。只用于新结算，不用于追认历史批次。"""
    m = json.loads(PROTOCOL_MANIFEST.read_text(encoding="utf-8"))
    return protocol_digest(dict(m.get("artifacts") or {}))


def protocol_version_from_inject(inj: dict) -> str | None:
    """一次注入真的把哪一版协议放进了 `work/protocol/`。裸臂没有 → None（不是「没有协议」）。"""
    files = inj.get("files") or {}
    shas = {n: files.get(f"work/protocol/{n}") for n in PROTOCOL_STATIC}
    if not all(shas.values()):
        return None
    return protocol_digest({k: str(v) for k, v in shas.items()})


def protocol_version_from_runs(batch: str, runs_in: Path | str | None = None) -> tuple[str | None, dict[str, int]]:
    """从 `runs_in/<batch>/*/inject.json` 反算这一批的协议轴。

    返回 `(唯一取值或 None, {摘要: 出现次数})`。一批里出现两个取值 → 返回 None ——
    那不是「选一个」的场合，那是这一批本身跨了协议版本，必须由人来裁定。
    """
    base = Path(runs_in) if runs_in is not None else (cfg.GENEBENCH_ROOT / "runs_in")
    seen: dict[str, int] = {}
    d = base / batch
    if d.is_dir():
        for inj_p in sorted(d.glob("*/inject.json")):
            try:
                inj = json.loads(inj_p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            v = protocol_version_from_inject(inj)
            if v:
                seen[v] = seen.get(v, 0) + 1
    if len(seen) == 1:
        return next(iter(seen)), seen
    return None, seen


def protocol_by_run(batch: str, runs_in: Path | str | None = None) -> dict[str, str]:
    """**逐 run** 的协议轴：`runs_in/<batch>/<run_id>/inject.json` → 这次注入真的放进去的那一版。

    红队 5.rt finding 4：协议轴过去是**批级声明**，`enrich` 把这一批 GQ 臂的摘要盖在全部记录上。
    两条后果：① `--filter protocol_version=<摘要>` 会把从来没见过该协议的裸臂 run 一起选出来，
    而协议轴的立卡理由恰恰是「strict 臂拿到的协议工件在两批之间换过一版而没人记得下来」；
    ② 一个纯裸臂的批（oracle / null_agent / 控制批）反算不出摘要，于是永远进不了库。

    改成逐 run 写轴：拿到协议工件的 run 写摘要，没拿到的写 `NO_PROTOCOL`。**同一批里
    `none` 与摘要并排出现不算混轴** —— 见 `mixed_axes`：那是按 `arm_kind` 分组判的，
    裸臂那一组的取值恒为 `none`，事实是两个臂跑在同一次发布上。

    目录名就是 `run_id`（`runner.inject` 建的 run 目录）。读不到 `inject.json` 的 run
    **不在返回值里** —— 那是「不知道」，由调用方决定退回批级取值还是拒。
    """
    base = Path(runs_in) if runs_in is not None else (cfg.GENEBENCH_ROOT / "runs_in")
    out: dict[str, str] = {}
    d = base / batch
    if not d.is_dir():
        return out
    for inj_p in sorted(d.glob("*/inject.json")):
        try:
            inj = json.loads(inj_p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out[inj_p.parent.name] = protocol_version_from_inject(inj) or NO_PROTOCOL
    return out


# ------------------------------------------------------------------ 通道轴

def channel_build(ch: str) -> str | None:
    """通道快照的 build 指纹（元信息，不是轴）。私有通道的快照没有 `build_info.json` → None。"""
    root = cfg.snapshot_root(ch)
    infos = sorted(root.glob("*/build_info.json")) if root.is_dir() else []
    if not infos:
        return None
    h = hashlib.sha256()
    for p in infos:
        h.update(p.name.encode())
        h.update(str(p.parent.name).encode())
        h.update(p.read_bytes())
    return h.hexdigest()[:12]


# ------------------------------------------------------------------ 记录

def track_of(rec: dict) -> str:
    """主赛道还是适配赛道。判据取记录自己的形状（适配赛道记录带 `outcome` + `level`）。"""
    return "adaptation" if ("outcome" in rec and "level" in rec) else "main"


def _canon(rec: dict) -> str:
    return json.dumps(rec, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(rec: dict) -> str:
    """一条记录的内容指纹（去掉库自己盖的元信息 —— 那些不是判据）。"""
    body = {k: v for k, v in rec.items() if k not in ("_ingested_at", "_content_sha256")}
    return hashlib.sha256(_canon(body).encode("utf-8")).hexdigest()


def machine_from_run_id(rid: Any) -> str | None:
    """``<task>.<arm>.<config>.rNN@<machine_id>`` → `machine_id`；没有那一段 → `None`。

    **不猜**：2026-09-10 之前的 run_id 里没有机器段，它们的机器是「不知道」，不是本机 ——
    把本机的标识盖上去，等于用今天的事实追认昨天的运行（`protocol_version` 那条轴
    踩过同样的坑，见模块开头）。
    """
    if not isinstance(rid, str) or MACHINE_SEP not in rid:
        return None
    _, _, m = rid.partition(MACHINE_SEP)
    return m or None


def machine_of(rec: dict) -> str | None:
    """一条记录是哪台机器跑出来的。记录自带 `machine_id` 优先，其次从 `run_id` 反算。"""
    m = rec.get(MACHINE_FIELD)
    if isinstance(m, str) and m:
        return m
    return machine_from_run_id(rec.get("run_id"))


def key_of(rec: dict) -> str:
    """主键 = `(machine_id, batch, run_id)`（用户裁定 ⑮）。

    **向后兼容**：机器段认不出来（旧 run_id、旧记录）时退回 `(batch, run_id)` ——
    也就是库里已有的那 126 条键**一个字节都不变**，`ingest` 的幂等与内容比对照旧成立。
    新的 run_id 自带机器段，两台机器的同名 batch 因此天然不撞。
    """
    b, rid = rec.get("batch"), rec.get("run_id")
    if not b or not rid:
        raise ResultsDBError(f"记录没有 (batch, run_id)：batch={b!r} run_id={rid!r}")
    m = machine_of(rec)
    k = f"{m}/{b}/{rid}" if m else f"{b}/{rid}"
    # **被取代的旧行让出主键**（N-645，用户裁定 ⑤，2026-09-11）。
    # 重算之后同一个 run 有了新的判据值，而主键是 `(machine, batch, run_id)` —— 同键。
    # 覆盖是不许的（结果库不是可以被悄悄改写的东西），删行更不许：
    # 删了就查不到「曾经发表过偏低那版」，而签字包里那张表**已经发出去了**。
    # 于是旧行改挂一个带时刻的后缀，让出主键，留在库里可查。
    if rec.get(SUPERSEDED_FIELD):
        k += f"~superseded@{rec.get(SUPERSEDED_AT) or 'unknown'}"
    return k


def validate_record(rec: dict) -> list[str]:
    """这条记录能不能进库。返回问题清单（空 = 可以进）。**不修，只判**。"""
    problems: list[str] = []
    for ax in AXES:
        if rec.get(ax) in (None, ""):
            problems.append(f"缺版本轴 {ax}")
    track = track_of(rec)
    ident = IDENTITY_ADAPT if track == "adaptation" else IDENTITY
    fields = RESULT_FIELDS_ADAPT if track == "adaptation" else RESULT_FIELDS
    for k in ident:
        if k == "seed":
            if rec.get("seed") is None and rec.get("seq") is None:
                problems.append("缺身份键 seed/seq")
            continue
        if rec.get(k) in (None, ""):
            problems.append(f"缺身份键 {k}")
    for k in fields:
        if k not in rec:
            problems.append(f"缺结算字段 {k}")
    if rec.get("channel") not in cfg.CHANNELS:
        problems.append(f"channel={rec.get('channel')!r} 不在 {cfg.CHANNELS}")
    return problems


def enrich(records: Iterable[dict], *, batch: str, protocol_version: str, channel: str,
           axes_source: dict[str, str] | None = None,
           protocol_versions: dict[str, str] | None = None) -> list[dict]:
    """给一批 `scorer` 出的记录补上库要的东西：`batch` / `seed` / 两条缺的轴 / 派生布尔。

    **只补库自己的字段，不动任何判据值。**

    `protocol_versions`（`protocol_by_run()` 的返回，`run_id → 轴值`）给了就**逐 run 写轴**
    （红队 5.rt finding 4）；某个 run 不在里面（读不到它的 `inject.json`）才退回批级的
    `protocol_version`。适配赛道记录没有对应的注入目录，走的也是这条退路。
    """
    ch = cfg.assert_channel(channel)
    per_run = dict(protocol_versions or {})
    out: list[dict] = []
    for r in records:
        rec = dict(r)
        rec["batch"] = rec.get("batch") or batch
        if rec.get("seed") is None:
            rec["seed"] = rec.get("seq")
        rec["protocol_version"] = per_run.get(str(rec.get("run_id"))) or protocol_version
        m = machine_of(rec)
        if m:                                               # 算不出来就**不写这个键**（见 MACHINE_FIELD）
            rec[MACHINE_FIELD] = m
        rec["channel"] = ch
        rec["channel_build"] = channel_build(ch)
        rec["track"] = track_of(rec)
        if rec["track"] == "main":
            #: 「撞了我们的预算闸」是个二值事实，主表要能直接切；口径与
            #: `scorer.score_run.budget_exhausted` 同源（边车的 429，不是事后拿 calls 反推）。
            rec["budget_exhausted"] = bool(rec.get("budget")) or rec.get("run_status") == "budget_exhausted"
        rec["axes_source"] = dict(axes_source or {})
        out.append(rec)
    return out


# ------------------------------------------------------------------ 读

def load(root: Path | str | None = None) -> list[dict]:
    p = results_path(root)
    if not p.is_file():
        return []
    out: list[dict] = []
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except ValueError as e:
            raise ResultsDBError(f"{p}:{i} 不是合法 JSON：{e}") from e
    return out


def _match(rec: dict, field: str, want: Any) -> bool:
    got = rec.get(field)
    if isinstance(want, (list, tuple, set, frozenset)):
        return any(_match(rec, field, w) for w in want)
    if isinstance(got, bool) or isinstance(want, bool):
        if isinstance(want, str):
            return str(got).lower() == want.strip().lower()
        return got == want
    if isinstance(want, str) and not isinstance(got, str):
        return str(got) == want
    return got == want


def query(root: Path | str | None = None, *, records: list[dict] | None = None, **filters) -> list[dict]:
    """按字段等值（或值列表 = 或）过滤。**保持入库顺序** —— 顺序会影响浮点求和的最后几位，
    而「表逐格相同」这条验收判的就是那几位。"""
    rows = records if records is not None else load(root)
    for f, want in filters.items():
        rows = [r for r in rows if _match(r, f, want)]
    return rows


def axis_values(records: Iterable[dict]) -> dict[str, list[str]]:
    vals: dict[str, set[str]] = {ax: set() for ax in AXES}
    for r in records:
        for ax in AXES:
            if r.get(ax) not in (None, ""):
                vals[ax].add(str(r[ax]))
    return {ax: sorted(v) for ax, v in vals.items()}


def mixed_axes(records: Iterable[dict]) -> dict[str, list[str]]:
    """哪几条轴在这一组记录里不止一个取值。空 = 同轴，可以出表。

    协议轴例外，按 `arm_kind` 分组判（红队 5.rt finding 4）：裸臂那一组的取值恒为
    `NO_PROTOCOL`，所以「`none` 与某一个摘要并排」**不是混轴** —— 事实是同一批里两个臂
    跑在同一次发布上，其中一个臂本来就不发协议工件。真正的混轴是**协议臂之间**出现了
    两个摘要（`m6` 的 `7e8ad97d1f7a` 与 `a4` 的 `d6fbcaa08302` 合成一行，就是这一条要拦的）。
    等价写法：把 `none` 摘掉之后还剩两个以上取值才算混。
    """
    vals = axis_values(records)
    out = {ax: v for ax, v in vals.items() if ax != "protocol_version" and len(v) > 1}
    injected = [v for v in vals.get("protocol_version", []) if v != NO_PROTOCOL]
    if len(injected) > 1:
        out["protocol_version"] = vals["protocol_version"]
    return out


def versions(root: Path | str | None = None, *, records: list[dict] | None = None) -> list[dict]:
    """库里出现过的**版本轴组合**：每种组合一行，带 run 数与来源批次。

    混轴时下游必须能看见 —— 这就是「看见」的地方：组合多于一种，就说明库里的东西
    不是一次可比的读数，`ops/mk_tables.py` 会据此拒绝出表。
    """
    rows = records if records is not None else load(root)
    agg: dict[tuple, dict] = {}
    for r in rows:
        k = tuple(str(r.get(ax)) for ax in AXES)
        e = agg.setdefault(k, {**dict(zip(AXES, k)), "n_runs": 0, "batches": set(), "tracks": set()})
        e["n_runs"] += 1
        e["batches"].add(str(r.get("batch")))
        e["tracks"].add(str(r.get("track") or track_of(r)))
    out = []
    for k in sorted(agg):
        e = agg[k]
        out.append({**{ax: e[ax] for ax in AXES}, "n_runs": e["n_runs"],
                    "batches": sorted(e["batches"]), "tracks": sorted(e["tracks"])})
    return out


def run_id_reuse(records: Iterable[dict]) -> dict[str, list[str]]:
    """同一个 `run_id` 出现在几个批里（主键必须带 batch 的理由，见模块开头）。"""
    seen: dict[str, list[str]] = {}
    for r in records:
        seen.setdefault(str(r.get("run_id")), []).append(str(r.get("batch")))
    return {k: sorted(set(v)) for k, v in seen.items() if len(set(v)) > 1}


# ------------------------------------------------------------------ 写

def _write_index(root: Path | str | None, rows: list[dict]) -> Path:
    by_batch: dict[str, int] = {}
    for r in rows:
        b = str(r.get("batch"))
        by_batch[b] = by_batch.get(b, 0) + 1
    by_machine: dict[str, int] = {}
    for r in rows:
        k = machine_of(r) or "（未知：run_id 里没有机器段）"
        by_machine[k] = by_machine.get(k, 0) + 1
    idx = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": _now(),
        "axes": list(AXES),
        "n_records": len(rows),
        "machines": {k: by_machine[k] for k in sorted(by_machine)},
        "batches": {k: by_batch[k] for k in sorted(by_batch)},
        "version_combos": versions(records=rows),
        "mixed_axes_in_db": mixed_axes(rows),
        "run_id_reused_across_batches": run_id_reuse(rows),
        "results_file": str(results_path(root)),
    }
    return RIO.write_json(index_path(root), idx)




def supersede(*, batch: str, root: Path | str | None = None, by: str, note: str,
              at: str | None = None, track: str | None = None) -> dict:
    """把某一批（可限 `track`）**还没被标过**的行标成 `superseded`。**不删行、不改判据值。**

    Args:
        by: 取代它的那一版是什么（例如 `r1.0.22`）——「新的在哪」要查得到。
        note: 为什么被取代。不写原因等于没标。
        at: 标记时刻（`None` = 现在）。它进主键后缀，所以同一批标两次不会撞。

    Returns:
        `{"marked": n, "at": ..., "keys": [...]}`。
    """
    from datetime import datetime, timezone
    stamp = at or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = results_path(root)
    if not path.exists():
        raise ResultsDBError(f"库不在：{path}")
    marked, keys = 0, []
    with open(path, "r+", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            fh.seek(0)
            rows = [json.loads(l) for l in fh.read().splitlines() if l.strip()]
            for r in rows:
                if r.get("batch") != batch or r.get(SUPERSEDED_FIELD):
                    continue
                if track and r.get("track") != track:
                    continue
                r[SUPERSEDED_FIELD] = True
                r[SUPERSEDED_AT] = stamp
                r[SUPERSEDED_BY] = by
                r[SUPERSEDED_NOTE] = note
                r["_content_sha256"] = content_hash(r)
                marked += 1
                keys.append(key_of(r))
            fh.seek(0)
            fh.truncate()
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    path.chmod(0o600)
    return {"marked": marked, "at": stamp, "keys": keys}


def ingest(records: Iterable[dict], *, batch: str | None = None,
           root: Path | str | None = None) -> dict:
    """把一批记录收进库。**幂等**：主键 `(batch, run_id)` 已在库里且内容一致 → 跳过；
    内容不一致 → 抛 `ResultsDBError`，**不覆盖**（结果库不是可以被悄悄改写的东西）。

    Returns:
        `{"added": n, "duplicate": n, "keys": [...]}`。
    """
    recs = [dict(r) for r in records]
    for r in recs:
        if batch and not r.get("batch"):
            r["batch"] = batch
        r.setdefault("track", track_of(r))
    bad = [(key_of(r) if r.get("run_id") else "?", p) for r in recs for p in [validate_record(r)] if p]
    if bad:
        lines = [f"  {k}: {'；'.join(p)}" for k, p in bad[:20]]
        raise ResultsDBError(f"{len(bad)} 条记录进不了库（四条版本轴 / 身份键 / 结算字段缺件）：\n"
                             + "\n".join(lines))
    RIO.secure_dir(db_root(root))
    path = results_path(root)
    if not path.exists():
        path.touch(mode=0o600)
    path.chmod(0o600)
    added, dup = 0, 0
    with open(path, "r+", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            existing: dict[str, str] = {}
            order: list[dict] = []
            fh.seek(0)
            for line in fh.read().splitlines():
                if not line.strip():
                    continue
                e = json.loads(line)
                existing[key_of(e)] = e.get("_content_sha256") or content_hash(e)
                order.append(e)
            fresh: list[dict] = []
            for r in recs:
                k, h = key_of(r), content_hash(r)
                if k in existing:
                    if existing[k] != h:
                        raise ResultsDBError(
                            f"{k} 已在库里且内容不同（库 {existing[k][:12]}… ≠ 新 {h[:12]}…）。"
                            f"结果库只追加不覆盖 —— 要换判据请换一个 batch 名，"
                            f"或先把这一批从 results.jsonl 里显式摘掉并记在票据里。")
                    dup += 1
                    continue
                if any(key_of(x) == k for x in fresh):
                    raise ResultsDBError(f"同一次 ingest 里 {k} 出现了两次")
                r["_ingested_at"] = _now()
                r["_content_sha256"] = h
                fresh.append(r)
            if fresh:
                fh.seek(0, 2)
                for r in fresh:
                    fh.write(_canon(r) + "\n")
                added = len(fresh)
            all_rows = order + fresh
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    _write_index(root, all_rows)
    RIO.secure_tree(db_root(root))
    return {"added": added, "duplicate": dup, "n_total": len(all_rows),
            "keys": [key_of(r) for r in recs]}


# ------------------------------------------------------------------ 回填

def discoverable_batches(reports: Path | None = None) -> list[str]:
    base = reports or (_REPO / "ops" / "reports")
    out = []
    for d in sorted(p for p in base.iterdir() if p.is_dir()):
        if d.name in DERIVED_BATCHES:
            continue
        p = d / "records.json"
        if p.is_file() and json.loads(p.read_text(encoding="utf-8")):
            out.append(d.name)
    return out


def backfill_batch(batch: str, *, root: Path | str | None = None, channel: str = "private",
                   reports: Path | None = None, runs_in: Path | None = None) -> dict:
    """一个 batch 的 `records.json` → 库。协议轴**逐 run** 从 `runs_in/<batch>` 反算。

    三种情形（红队 5.rt finding 4）：

    * 反算出**一个**摘要 → 它是这一批的协议臂跑的那一版；裸臂逐 run 记 `NO_PROTOCOL`。
    * 反算出**两个以上** → 这一批本身跨了协议版本，必须由人裁定，拒。
    * 一个都没有：读得到注入（`inject.json` 在，里面没有协议工件）= **纯裸臂的批**
      （oracle / null_agent / 控制批），按 `NO_PROTOCOL` 收进库；连注入都读不到 = 真的
      不知道，仍然拒 —— 不拿今天仓库里的版本去追认。
    """
    base = reports or (_REPO / "ops" / "reports")
    recs = json.loads((base / batch / "records.json").read_text(encoding="utf-8"))
    per_run = protocol_by_run(batch, runs_in)
    pv, seen = protocol_version_from_runs(batch, runs_in)
    if pv is None:
        if seen:
            raise ResultsDBError(
                f"{batch}: 这一批里有 {len(seen)} 个协议摘要（{seen}）—— 那不是「选一个」的场合，"
                f"是这一批本身跨了协议版本，必须由人裁定。")
        if not per_run:
            raise ResultsDBError(
                f"{batch}: 协议轴反算不出（runs_in/{batch} 里 GQ 臂的注入摘要 = {seen or '无'}）。"
                f"不给它一个默认值 —— 「今天仓库里的协议版本」不是这一批当时跑的那一版。")
        pv = NO_PROTOCOL          # 读到了注入、一件协议工件都没有 = 整批都是裸臂
    rows = enrich(recs, batch=batch, protocol_version=pv, channel=channel,
                  protocol_versions=per_run,
                  axes_source={"set_version": "record(inject.frozen_manifest)",
                               "reference_version": "record(inject.reference_manifest)",
                               "protocol_version":
                                   f"runs_in/{batch}/<run_id>/inject.json:files[work/protocol/*]"
                                   f"（逐 run；裸臂 = {NO_PROTOCOL}）",
                               "channel": "backfill:declared"})
    r = ingest(rows, batch=batch, root=root)
    r["batch"], r["protocol_version"], r["channel"] = batch, pv, channel
    r["n_records"] = len(recs)
    return r


# ------------------------------------------------------------------ CLI

def _kv(pairs: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for p in pairs or []:
        if "=" not in p:
            raise SystemExit(f"--filter 要写成 k=v：{p!r}")
        k, _, v = p.partition("=")
        vals = [x for x in v.split(",") if x != ""]
        out[k.strip()] = vals[0] if len(vals) == 1 else vals
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="GeneBench 结果库（单一来源）")
    ap.add_argument("--db", default=None, help="库根（默认 $GENEBENCH_ROOT/results/v1）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_bf = sub.add_parser("backfill", help="把 ops/reports/*/records.json 全收进库")
    p_bf.add_argument("--batch", action="append", default=None, help="只收这些批（默认全部）")
    p_bf.add_argument("--channel", default="private")
    p_bf.add_argument("--report", default=str(_REPO / "ops" / "reports" / "results_db_backfill.md"))
    p_bf.add_argument("--no-verify", action="store_true", help="不做「与既有 CSV 逐格相同」的核对")

    p_in = sub.add_parser("ingest", help="收一个批")
    p_in.add_argument("--batch", required=True)
    p_in.add_argument("--channel", default="private")

    p_sup = sub.add_parser("supersede", help="把一批旧行标成 superseded（不删行）")
    p_sup.add_argument("--batch", required=True)
    p_sup.add_argument("--track", default=None, help="只标这一个赛道（main / adaptation）")
    p_sup.add_argument("--by", required=True, help="取代它的那一版（如 r1.0.22）")
    p_sup.add_argument("--note", required=True, help="为什么被取代 —— 不写原因等于没标")

    sub.add_parser("versions", help="库里出现过的版本轴组合")
    sub.add_parser("stat", help="库的元信息")

    p_q = sub.add_parser("query", help="按字段过滤")
    p_q.add_argument("--filter", action="append", default=[])
    p_q.add_argument("--fields", default="batch,run_id,arm,run_status,validity,l3_pass,effect")
    p_q.add_argument("--json", action="store_true")

    a = ap.parse_args(argv)
    root = a.db

    if a.cmd == "backfill":
        batches = a.batch or discoverable_batches()
        results, errs = [], []
        for b in batches:
            try:
                results.append(backfill_batch(b, root=root, channel=a.channel))
            except ResultsDBError as e:
                errs.append(f"{b}: {e}")
        rows = load(root)
        print(f"收了 {len(results)} 批；库里现在 {len(rows)} 条")
        for r in results:
            print(f"  {r['batch']}: +{r['added']} 重复 {r['duplicate']}  protocol={r['protocol_version']}")
        for e in errs:
            print(f"  ！{e}")
        from ops import mk_tables as MT                      # 循环依赖：延迟到用时再引
        report = MT.write_backfill_report(Path(a.report), results=results, errors=errs,
                                          root=root, verify=not a.no_verify)
        print(f"→ {report}")
        return 0 if not errs else 1

    if a.cmd == "ingest":
        r = backfill_batch(a.batch, root=root, channel=a.channel)
        print(json.dumps({k: v for k, v in r.items() if k != "keys"}, ensure_ascii=False))
        return 0

    if a.cmd == "supersede":
        r = supersede(batch=a.batch, root=root, by=a.by, note=a.note, track=a.track)
        print(json.dumps({k: v for k, v in r.items() if k != "keys"}, ensure_ascii=False))
        print(f"  标了 {r['marked']} 行（旧行留在库里，主键后缀 ~superseded@{r['at']}）")
        return 0

    if a.cmd == "versions":
        for v in versions(root):
            print(f"{v['set_version']} / {v['reference_version']} / {v['protocol_version']} / "
                  f"{v['channel']}  n={v['n_runs']}  批={','.join(v['batches'])}")
        mx = mixed_axes(load(root))
        print(f"混轴：{mx or '无（全库同轴）'}")
        return 0

    if a.cmd == "stat":
        p = index_path(root)
        print(p.read_text(encoding="utf-8") if p.is_file() else "（库还是空的）")
        return 0

    if a.cmd == "query":
        rows = query(root, **_kv(a.filter))
        if a.json:
            print(json.dumps(rows, ensure_ascii=False, indent=1))
        else:
            fields = [f for f in a.fields.split(",") if f]
            print("\t".join(fields))
            for r in rows:
                print("\t".join("" if r.get(f) is None else str(r.get(f)) for f in fields))
            print(f"# {len(rows)} 条")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
