# -*- coding: utf-8 -*-
"""**接入成本遥测**（卡 2.5，2026-09-06）。

「接一个系统要花多少功夫」是 GeneBench 自带的一个测量项，不是实验记录：
范式层声称「接口定义在范式层，接入责任在被测方」，这句话只有在**接入成本可测**
的时候才是可证伪的。所以每个接入都要记 —— 记的是**接入这件事**，不是 agent 的表现。

量三样，三样都不靠人回忆：

* **active minutes** —— `begin`..`end` 去掉 `pause`..`resume` 段。人会离开去干别的，
  把挂钟时间当工时会把「等一个 90 分钟的 flock」记成「接入花了两小时」。
* **LOC** —— `git diff --numstat <begin 时 HEAD>..HEAD -- integrations/<id>` 的增删行，
  加上该目录**当前**的非空行数。两个数都要：前者是「改了多少」，后者是
  「最后剩下多少」，而未提交的工作只在后者里看得见。
* **返工次数** —— `rework` 事件的条数。返工是接入成本里最真实的一项，
  而它恰恰是事后最想不起来的一项（「没花多久」通常等于「忘了那两次白干」）。

落点是 `integrations/COST.jsonl`，**一行一个事件**，键集恰好 12 个（缺的写 `null`）。
为什么固定键集：这份 JSONL 会被 `report` 拉成表，一条少了键的记录在表上表现为
「那一格是空的」——和「那一项真的是 0」长得一模一样。

`COST.md` 由 `report` 从 JSONL **生成**，不手写：手写的表会和 JSONL 漂开，
而漂开的表现是「表看起来是对的」。

并发
----
`COST.jsonl` 是**共享文件**（并发施工规则 C）。追加走 `fcntl.flock` 独占锁，
锁的就是这个文件本身 —— 不另立锁文件：多一个锁文件就多一条「有人没拿这把锁」的路径。
读走共享锁。写只追加，从不重排、不重写。

用法
----
    PY=/data/shared/genebench/env/bin/python; cd /data/shared/genebench/repo

    $PY -m integrations.cost begin  --system tradingagents --who agent --note "起手"
    $PY -m integrations.cost pause  --system tradingagents --note "等网关锁"
    $PY -m integrations.cost resume --system tradingagents
    $PY -m integrations.cost rework --system tradingagents --why "镜像里 HOME 不可写，命令重写"
    $PY -m integrations.cost loc    --system tradingagents          # 只看，不记事件
    $PY -m integrations.cost end    --system tradingagents --outcome passed_real_task
    $PY -m integrations.cost report                                  # 生成 integrations/COST.md

`--at <ISO8601 带时区>` 是**补记**用的：忘了敲 `begin` 的时候按真实时刻补一条，
而不是把「忘了记」写成「花了 0 分钟」。补记的时刻**原样入账**，不做任何修正。
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

#: 仓库根（`integrations/cost/__init__.py` 的上上级）。CLI 的 `--repo` 覆盖它。
REPO_ROOT = Path(__file__).resolve().parents[2]

JSONL_REL = "integrations/COST.jsonl"
MD_REL = "integrations/COST.md"

#: 一条记录的**键全集**，顺序即列序。缺的写 `null`，不许省。
FIELDS: tuple[str, ...] = (
    "ts", "system", "event", "who", "head", "active_minutes",
    "loc_added", "loc_deleted", "loc_total", "rework_count", "outcome", "note",
)

#: 事件轴。`loc` 与 `report` 是**查询**，不产生事件 —— 查一次就记一条会让
#: 「看了几眼」混进「干了多少活」。
EVENTS: tuple[str, ...] = ("begin", "pause", "resume", "rework", "end")

#: 结局轴（任务书原文三选一）。
OUTCOMES: tuple[str, ...] = ("passed_real_task", "blocked", "abandoned")

WHO: tuple[str, ...] = ("agent", "human")

#: 数非空行时不下钻的目录：生成物不是接入成本。
SKIP_DIRS: frozenset[str] = frozenset({"__pycache__", ".git", ".pytest_cache", ".mypy_cache"})

FILE_MODE = 0o600


class CostError(RuntimeError):
    """成本账本用错了 / 读坏了。**不静默** —— 静默的表现是数偏小。"""


# ---------------------------------------------------------------------------
# 路径与时刻
# ---------------------------------------------------------------------------
def jsonl_path(repo_root=None) -> Path:
    return Path(repo_root if repo_root is not None else REPO_ROOT) / JSONL_REL


def md_path(repo_root=None) -> Path:
    return Path(repo_root if repo_root is not None else REPO_ROOT) / MD_REL


def now_ts() -> str:
    """当前时刻，UTC、带时区、秒级。"""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_ts(ts: str, where: str = "") -> datetime:
    """ISO8601 → aware datetime。**不接受不带时区的** ——
    裸时刻在跨机记账里会静默偏 8 小时，而 8 小时的 active_minutes 看起来只是「那天干得久」。"""
    try:
        d = datetime.fromisoformat(str(ts))
    except (TypeError, ValueError) as e:
        raise CostError(f"{where}ts={ts!r} 不是 ISO8601（{e}）") from e
    if d.tzinfo is None:
        raise CostError(f"{where}ts={ts!r} 没有时区 —— 请写成 2026-09-06T15:30:00+00:00 这样")
    return d


# ---------------------------------------------------------------------------
# 账本读写
# ---------------------------------------------------------------------------
def _ordered(rec: dict) -> dict:
    unknown = [k for k in rec if k not in FIELDS]
    if unknown:
        raise CostError(f"记录里有 FIELDS 之外的键 {unknown} —— 键集必须恰好是 {list(FIELDS)}")
    return {k: rec.get(k) for k in FIELDS}


def parse_lines(lines, where: str = "COST.jsonl") -> list[dict]:
    """一批行 → 事件表。**坏行当场炸，不跳过** ——
    跳过一行的后果是下游每个数都偏小，而偏小和「这个接入很省事」长得一样。"""
    out: list[dict] = []
    for i, raw in enumerate(lines, 1):
        if not raw.strip():
            continue
        try:
            rec = json.loads(raw)
        except ValueError as e:
            raise CostError(f"{where}:{i} 不是合法 JSON（{e}）") from e
        if not isinstance(rec, dict):
            raise CostError(f"{where}:{i} 顶层不是对象")
        missing = [k for k in FIELDS if k not in rec]
        extra = [k for k in rec if k not in FIELDS]
        if missing or extra:
            raise CostError(
                f"{where}:{i} 键集必须**恰好**是 {list(FIELDS)}（缺 {missing}；多 {extra}）")
        if rec.get("event") not in EVENTS:
            raise CostError(f"{where}:{i} event={rec.get('event')!r} 不在 {list(EVENTS)}")
        parse_ts(rec["ts"], where=f"{where}:{i} ")
        out.append(rec)
    return out


def _read_all(fd) -> str:
    os.lseek(fd, 0, os.SEEK_SET)
    buf = b""
    while True:
        chunk = os.read(fd, 65536)
        if not chunk:
            return buf.decode("utf-8")
        buf += chunk


def _write_md(repo_root, events) -> Path:
    """把报表写出来。**调用者必须已经持有账本的独占锁** —— 见 `append_event` 的说明。"""
    p = md_path(repo_root)
    p.write_text(render_markdown(summarize(events)), encoding="utf-8")
    try:
        os.chmod(p, FILE_MODE)
    except OSError:                                         # pragma: no cover
        pass
    return p


def read_events(repo_root=None) -> list[dict]:
    """读全部事件（共享锁）。"""
    p = jsonl_path(repo_root)
    if not p.is_file():
        return []
    fd = os.open(p, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_SH)
        text = _read_all(fd)
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    return parse_lines(text.splitlines(), where=str(p))


def append_event(rec: dict, repo_root=None) -> Path:
    """独占锁下追加一行，**并在同一把锁里重算 `COST.md`**。

    为什么把重算塞进来：`COST.md` 是从账本导出来的，两者漂开的表现是
    「表看起来是对的」。留一个「记完事件记得跑 report」的人肉步骤，
    等于把这份漂当成纪律问题 —— 而纪律问题最后总会发生。

    锁就是账本文件本身（`O_APPEND` + `fcntl.flock`），不另立锁文件：
    多一个锁文件就多一条「有人没拿这把锁」的路径。**所以这里不能调用
    `read_events()`** —— 它会在另一个 fd 上再要一次锁，同进程直接自锁死。
    """
    p = jsonl_path(repo_root)
    if not p.parent.is_dir():
        raise CostError(f"{p.parent} 不在 —— 成本账本只落在仓库的 integrations/ 下")
    line = json.dumps(_ordered(rec), ensure_ascii=False) + "\n"
    fd = os.open(p, os.O_RDWR | os.O_CREAT | os.O_APPEND, FILE_MODE)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        os.write(fd, line.encode("utf-8"))
        _write_md(repo_root, parse_lines(_read_all(fd).splitlines(), where=str(p)))
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    try:                                                    # 红线 5：go-rwx
        os.chmod(p, FILE_MODE)
    except OSError:                                         # pragma: no cover
        pass
    return p


# ---------------------------------------------------------------------------
# 会话与 active minutes
# ---------------------------------------------------------------------------
def sessions(events, system: str) -> list[list[dict]]:
    """某系统的会话切片：每段以 `begin` 起，以 `end` 收；**最后一段可以是开着的**。

    一个系统允许多段（中断几天再接着干就是两段），报表把它们**相加**。
    """
    out: list[list[dict]] = []
    cur: list[dict] | None = None
    for e in events:
        if e.get("system") != system:
            continue
        ev = e["event"]
        if ev == "begin":
            if cur is not None:
                raise CostError(
                    f"{system}: 上一段还没 end 就又 begin 了（{cur[0]['ts']} → {e['ts']}）")
            cur = [e]
            continue
        if cur is None:
            raise CostError(f"{system}: {ev} 出现在 begin 之前（{e['ts']}）")
        cur.append(e)
        if ev == "end":
            out.append(cur)
            cur = None
    if cur is not None:
        out.append(cur)
    return out


def state(events, system: str) -> str:
    """`none` / `active` / `paused` —— 状态是**从账本算出来的**，不另存一份。"""
    ss = sessions(events, system)
    if not ss or ss[-1][-1]["event"] == "end":
        return "none"
    return "paused" if ss[-1][-1]["event"] == "pause" else "active"


def active_minutes(session) -> float:
    """一段会话的净工时（分钟，两位小数）。

    `pause` 之后没 `resume` 就 `end` 的，那段暂停算到 `end` 为止 —— 这是**照实记**：
    人确实是暂停着收的尾。不为了好看把它算成在干活。
    """
    if not session or session[0]["event"] != "begin":
        raise CostError("会话必须以 begin 起头")
    t0 = parse_ts(session[0]["ts"])
    last = parse_ts(session[-1]["ts"])
    paused = 0.0
    pause_at = None
    for e in session[1:]:
        t = parse_ts(e["ts"])
        if t < t0:
            raise CostError(f"事件时刻倒流：{e['ts']} 早于 begin 的 {session[0]['ts']}")
        if e["event"] == "pause":
            if pause_at is None:
                pause_at = t
        elif e["event"] in ("resume", "end"):
            if pause_at is not None:
                paused += (t - pause_at).total_seconds()
                pause_at = None
    if pause_at is not None:                                # 开着的会话，正暂停中
        paused += (last - pause_at).total_seconds()
    net = (last - t0).total_seconds() - paused
    return round(max(net, 0.0) / 60.0, 2)


def rework_count(session) -> int:
    return sum(1 for e in session if e["event"] == "rework")


# ---------------------------------------------------------------------------
# LOC
# ---------------------------------------------------------------------------
def _git(repo_root, *args) -> str:
    p = subprocess.run(["git", "-C", str(repo_root), *args],
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise CostError(f"git {' '.join(args)} 失败（rc={p.returncode}）：{p.stderr.strip()}")
    return p.stdout


def git_head(repo_root=None) -> str:
    return _git(repo_root if repo_root is not None else REPO_ROOT,
                "rev-parse", "HEAD").strip()


def numstat(repo_root, base: str, system: str) -> tuple[int, int]:
    """`git diff --numstat <base>..HEAD -- integrations/<system>` 的增删行。

    二进制文件那两列是 `-` —— **跳过**（它没有「行」这个概念），不当成 0 也不当成报错。
    """
    out = _git(repo_root, "diff", "--numstat", f"{base}..HEAD",
               "--", f"integrations/{system}")
    added = deleted = 0
    for line in out.splitlines():
        cols = line.split("\t")
        if len(cols) < 3 or cols[0] == "-" or cols[1] == "-":
            continue
        added += int(cols[0])
        deleted += int(cols[1])
    return added, deleted


def count_nonblank(directory) -> int:
    """目录当前的非空行数。解码不了的（二进制）跳过；生成物目录不下钻。"""
    base = Path(directory)
    if not base.is_dir():
        return 0
    total = 0
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            f = Path(dirpath) / name
            if f.is_symlink() or f.suffix == ".pyc":
                continue
            try:
                text = f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            total += sum(1 for ln in text.splitlines() if ln.strip())
    return total


def loc_for(repo_root, system: str, base: str) -> dict:
    """三个 LOC 数。`base` 一般是该会话 `begin` 时的 HEAD。"""
    added, deleted = numstat(repo_root, base, system)
    return {"loc_added": added, "loc_deleted": deleted,
            "loc_total": count_nonblank(Path(repo_root) / "integrations" / system)}


# ---------------------------------------------------------------------------
# 报表
# ---------------------------------------------------------------------------
def summarize(events) -> dict:
    """按系统汇总。顺序 = 各系统**第一次 begin** 的先后（读表的人按施工顺序看）。"""
    order: list[str] = []
    for e in events:
        if e["system"] not in order:
            order.append(e["system"])
    rows = []
    for sysname in order:
        ss = sessions(events, sysname)
        ends = [s[-1] for s in ss if s[-1]["event"] == "end"]
        last_end = ends[-1] if ends else None
        #: 收了口的会话以 `end` 记下的数为准（`end --rework` 会比数事件多一次）；
        #: 还开着的会话现数事件 —— 两者相加，别让开着的那段在表上消失。
        rework = 0
        for s in ss:
            e = s[-1]
            if e["event"] == "end" and isinstance(e.get("rework_count"), int):
                rework += e["rework_count"]
            else:
                rework += rework_count(s)
        rows.append({
            "system": sysname,
            "sessions": len(ss),
            "who": ss[0][0].get("who") if ss else None,
            "active_minutes": round(sum(active_minutes(s) for s in ss), 2),
            "rework_count": rework,
            "loc_added": last_end.get("loc_added") if last_end else None,
            "loc_deleted": last_end.get("loc_deleted") if last_end else None,
            "loc_total": last_end.get("loc_total") if last_end else None,
            "outcome": last_end.get("outcome") if last_end else None,
            "open": ss[-1][-1]["event"] != "end" if ss else False,
        })
    total = {
        "systems": len(rows),
        "active_minutes": round(sum(r["active_minutes"] for r in rows), 2),
        "rework_count": sum(r["rework_count"] for r in rows),
        "loc_total": sum(r["loc_total"] or 0 for r in rows),
    }
    return {"rows": rows, "total": total}


def render_markdown(summary: dict) -> str:
    t = summary["total"]
    lines = [
        "# 接入成本（机器统计）", "",
        "> 本文由 `python -m integrations.cost report` 从 `COST.jsonl` **生成**，",
        "> 不要手改 —— 手改的表会和账本漂开，而漂开的表现是「表看起来是对的」。", "",
        f"**合计：{t['systems']} 个接入 / {t['active_minutes']:.1f} 净工时分钟 / "
        f"返工 {t['rework_count']} 次 / 目录现存 {t['loc_total']} 非空行。**", "",
        "口径：净工时 = `begin`..`end` 去掉 `pause`..`resume` 段；"
        "增删行 = `git diff --numstat <begin 时 HEAD>..HEAD -- integrations/<id>`；"
        "现存行 = 该目录当前非空行数（未提交的工作只在这一列里看得见）。", "",
        "| 接入 | 谁 | 净工时(min) | 增行 | 删行 | 现存非空行 | 返工 | 结局 |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for r in summary["rows"]:
        def _n(v):
            return "—" if v is None else str(v)
        outcome = r["outcome"] or ("进行中" if r["open"] else "—")
        lines.append(
            f"| `{r['system']}` | {r['who'] or '—'} | {r['active_minutes']:.1f} | "
            f"{_n(r['loc_added'])} | {_n(r['loc_deleted'])} | {_n(r['loc_total'])} | "
            f"{r['rework_count']} | {outcome} |")
    if not summary["rows"]:
        lines.append("| （还没有接入记录） | — | 0.0 | — | — | — | 0 | — |")
    lines.append("")
    return "\n".join(lines)


def write_report(repo_root=None) -> tuple[Path, dict]:
    """`report` 子命令：从账本重算 `COST.md`。

    每次 `append_event` 已经顺手重算过一遍，所以这条命令的日常用途是
    **把手改过的 `COST.md` 改回去**，以及在夹具/离线场景下单独出表。
    同样在账本的独占锁里做 —— 与追加互斥，读到的一定是完整的账本。
    """
    p = jsonl_path(repo_root)
    if not p.is_file():
        return _write_md(repo_root, []), summarize([])
    fd = os.open(p, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        events = parse_lines(_read_all(fd).splitlines(), where=str(p))
        out = _write_md(repo_root, events)
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    return out, summarize(events)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _blank() -> dict:
    return {k: None for k in FIELDS}


def _require_state(events, system: str, allowed, verb: str) -> str:
    st = state(events, system)
    if st not in allowed:
        raise CostError(
            f"{system} 当前状态是 {st!r}，不能 {verb}（要求 {list(allowed)}）。"
            f"看一眼：python -m integrations.cost report")
    return st


def _warn_missing_dir(repo_root, system: str) -> None:
    """`--system` 打错了不该是一次静默的记账。

    实测（2026-09-06 手册走查）：写错 id 会照样记下一条事件，而 LOC 永远是 0 ——
    **而 0 和「这个接入一行都没改」在表上长得一模一样**。所以提醒一句；
    不报错，因为「先 begin 再 mkdir」是正当顺序。
    """
    d = Path(repo_root) / "integrations" / system
    if not d.is_dir():
        print(f"提醒：{d} 还不在。--system 要写 integrations/<id> 的**目录名**；"
              f"打错了的话 LOC 会一直是 0。", file=sys.stderr)


def _head_or_none(repo_root):
    try:
        return git_head(repo_root)
    except (CostError, OSError, FileNotFoundError):
        return None


def _base_head(events, system: str) -> str:
    ss = sessions(events, system)
    if not ss:
        raise CostError(f"{system} 还没有 begin —— LOC 的基线是 begin 时的 HEAD")
    head = ss[-1][0].get("head")
    if not head:
        raise CostError(f"{system} 的 begin 没记下 HEAD（当时不在 git 仓库里？）")
    return head


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m integrations.cost",
        description="接入成本遥测：active minutes / LOC / 返工次数 → integrations/COST.jsonl")
    ap.add_argument("--repo", default=str(REPO_ROOT), help="仓库根（默认：本文件所在的仓库）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def _common(p, *, at=True):
        p.add_argument("--system", required=True, help="接入 id = integrations/<id> 的目录名")
        p.add_argument("--note", default=None, help="一句话，写给不在场的人看")
        if at:
            p.add_argument("--at", default=None,
                           help="补记：事件的真实时刻（ISO8601 带时区）。默认现在")

    p = sub.add_parser("begin", help="开始接一个系统")
    _common(p)
    p.add_argument("--who", required=True, choices=WHO)

    _common(sub.add_parser("pause", help="离开（等锁、等人、去干别的）"))
    _common(sub.add_parser("resume", help="回来接着干"))

    p = sub.add_parser("rework", help="记一次返工")
    _common(p)
    p.add_argument("--why", required=True, help="返工的原因，一句话")

    p = sub.add_parser("end", help="收口：结算工时与 LOC")
    _common(p)
    p.add_argument("--outcome", required=True, choices=OUTCOMES)
    p.add_argument("--rework", action="store_true",
                   help="收口这一下本身也是返工（等价于 end 之前先记一次 rework）")

    p = sub.add_parser("loc", help="只看 LOC，不记事件")
    p.add_argument("--system", required=True)
    p.add_argument("--base", default=None, help="基线 sha（默认：最近一次 begin 的 HEAD）")

    sub.add_parser("report", help="从 JSONL 生成 integrations/COST.md")

    a = ap.parse_args(argv)
    repo = Path(a.repo)

    if a.cmd == "report":
        path, summary = write_report(repo)
        t = summary["total"]
        print(f"写了 {path}")
        print(f"{t['systems']} 个接入 / {t['active_minutes']:.1f} 分钟 / "
              f"返工 {t['rework_count']} 次")
        return 0

    if a.cmd == "loc":
        events = read_events(repo)
        base = a.base or _base_head(events, a.system)
        loc = loc_for(repo, a.system, base)
        print(f"{a.system}  基线 {base[:12]}..HEAD")
        print(f"  增 {loc['loc_added']} 行 / 删 {loc['loc_deleted']} 行 / "
              f"现存非空 {loc['loc_total']} 行")
        return 0

    events = read_events(repo)
    ts = a.at or now_ts()
    parse_ts(ts, where="--at ")
    rec = _blank()
    rec.update({"ts": ts, "system": a.system, "event": a.cmd,
                "head": _head_or_none(repo), "note": a.note})

    if a.cmd == "begin":
        _require_state(events, a.system, ("none",), "begin")
        rec["who"] = a.who
        rec["rework_count"] = 0
        _warn_missing_dir(repo, a.system)
        if rec["head"] is None:
            raise CostError("begin 时拿不到 HEAD —— LOC 的基线就没了；先确认 --repo 是个 git 仓库")
    elif a.cmd == "pause":
        _require_state(events, a.system, ("active",), "pause")
    elif a.cmd == "resume":
        _require_state(events, a.system, ("paused",), "resume")
    elif a.cmd == "rework":
        _require_state(events, a.system, ("active", "paused"), "rework")
        rec["note"] = a.why
        rec["rework_count"] = rework_count(sessions(events, a.system)[-1]) + 1
    elif a.cmd == "end":
        _require_state(events, a.system, ("active", "paused"), "end")
        session = sessions(events, a.system)[-1] + [rec]
        rec["outcome"] = a.outcome
        rec["who"] = session[0].get("who")
        rec["active_minutes"] = active_minutes(session)
        rec["rework_count"] = rework_count(session) + (1 if a.rework else 0)
        try:
            rec.update(loc_for(repo, a.system, _base_head(events, a.system)))
        except CostError as e:                              # 不因为 git 算不出来就卡住收口
            print(f"LOC 未能计算：{e}", file=sys.stderr)
            rec["note"] = f"[LOC 未能计算：{e}] {rec['note'] or ''}".strip()
        if not any(rec.get(k) for k in ("loc_added", "loc_deleted", "loc_total")):
            _warn_missing_dir(repo, a.system)
            print(f"提醒：{a.system} 的 LOC 三个数全是 0 —— 目录空着，或者 --system 打错了。",
                  file=sys.stderr)

    append_event(rec, repo)
    print(json.dumps(_ordered(rec), ensure_ascii=False))
    return 0
