# -*- coding: utf-8 -*-
"""**执行面自己的门**：落地即扫，命中即删（N-61 补强，2026-09-05 裁定）。

**为什么发送侧的门不够**：`ops/push_guard.py` 拦的是**我们自己调用它的时候**。
2026-09-05 那次泄漏就是一条手写 `rsync` 绕过了它 —— 判据只存在于发送方的注意力里。
「判据要能在我不在场时否决我」，**这个文件是那句话的实现**：
它长在执行面上，不问东西是谁送来的、也不问送的人当时在想什么。

**三类判据**（裁定原文）：

1. **gold 串**：`GBC-G-` + 16 位十六进制。**流式二进制扫全部文件，不按类型豁免** ——
   「答案面的任何派生副本都是答案面：缓存、字节码、版本库对象、备份」（D-24），
   按后缀白名单扫等于给 `.parquet` 里的一份免检。
2. **答案面文件名**：六个（裁定逐条给定）。
3. **答案面目录名**：`reference/` / `solution/`，命中即整棵删。
4. **路径里的 gold 串**：任何一段路径名本身就是串（`mkdir <gold 串>`）。
   真机实测漏过一次 —— 前三条查的是「内容」与「已知名字」，
   而一个**以串命名的目录**两样都不占：里面的文件可以完全干净。

**命中即删，并以 access_log 同格式记 `answer_plane_detected`。**
删之前先记 sha256 与字节数 —— **证据要留，内容不留**。

**零引用面**：本文件跑在 f02，不 import `reference/`、不 import 网关。
与 `gateway/access_log.py` 的记录格式一致这件事，由 f01 的
`ops/test_answer_plane_guard.py` **断言**，不靠「照着抄的时候很小心」
（D-21：一条记录里两个独立来源的形状必须有对齐断言）。
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

#: gold 串的**形状**（`genetask/packager.py::_token` 的产物）。判形状不判具体值。
GOLD_TOKEN_RE = re.compile(rb"GBC-G-[0-9a-f]{16}")

#: 答案面文件名（裁定逐条给定，2026-09-05）。
ANSWER_PLANE_NAMES: tuple[str, ...] = (
    "canary.json", "scorer.yaml", "solve.py", "equivalence.md",
    "slots.json", "_ledger.jsonl",
)

#: 答案面目录名。命中即整棵删。
ANSWER_PLANE_DIRS: tuple[str, ...] = ("reference", "solution")

#: 记进日志的 reason 码。与网关的 `Reason` 分开 —— 它不是网关的拒绝，是执行面的自查。
REASON = "answer_plane_detected"

#: `GOLD_TOKEN_RE` 的**文本版**。从同一个模式派生，**不另抄一份** ——
#: 抄一份会漂，而漂的表现是「扫描认得出、脱敏认不出」，脱敏就等于没做。
_GOLD_TEXT_RE = re.compile(GOLD_TOKEN_RE.pattern.decode("ascii"))

#: 流式扫描的块大小与重叠。重叠必须 ≥ 串长-1，否则跨块边界的串会漏（串长 22，取 32）。
_CHUNK = 1 << 20
_OVERLAP = 32


class GuardError(RuntimeError):
    pass


def redact(text: str) -> str:
    """把 gold 串换成不可还原的短摘要。**写进证据文件的任何文本都要过这里。**

    2026-09-05 真机实测的一个自噬循环：日志与闩都住在扫描根**里面**，
    而我往日志里写了一句带完整合成串的注解 —— 下一轮扫描把**日志自己**判成
    `gold_token` 并**删掉了**。证据文件因为记录了证据而变成违禁品，
    于是整条审计链被它自己的门清空。

    两道修法缺一不可：① 写出去的文本一律脱敏（这里）；
    ② 本门自己的两个文件**拒绝自删**（见 `OWNED`）。
    只做 ② 会留下一个「日志里可以藏答案面」的口子；只做 ① 挡不住别人往日志里写。
    """
    return _GOLD_TEXT_RE.sub(
        lambda m: "<gold:redacted " + token_ref(m.group(0)) + ">", text)


@dataclass(frozen=True)
class Hit:
    """一处命中。`kind` ∈ gold_token / answer_plane_name / answer_plane_dir / unreadable。"""

    path: str            # 相对 root
    #: gold_token / gold_token_in_path / answer_plane_name / answer_plane_dir / unreadable
    kind: str
    detail: str
    size: int
    sha256: str
    is_dir: bool = False


def _sha256_and_size(p: Path) -> tuple[str, int]:
    h, n = hashlib.sha256(), 0
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            h.update(chunk)
            n += len(chunk)
    return h.hexdigest(), n


def has_gold(p: Path) -> str | None:
    """流式找 gold 串。返回命中的串或 None。**不按后缀豁免。**"""
    tail = b""
    with p.open("rb") as f:
        while True:
            chunk = f.read(_CHUNK)
            if not chunk:
                return None
            m = GOLD_TOKEN_RE.search(tail + chunk)
            if m:
                return m.group(0).decode("ascii")
            tail = chunk[-_OVERLAP:]


def token_ref(tok: str) -> str:
    """命中串的**可对照引用**：sha256 前 8 位。

    原来写的是 `tok[:10]`，即 `GBC-G-` + 4 位十六进制 —— 那仍然是串的一部分。
    「证据要留，内容不留」应当贯彻到底：哈希引用一样能把两条记录对上，
    而且**不含原串的任何一位**。日志因此也不会再被自己的扫描判成命中。
    """
    return "sha256:" + hashlib.sha256(tok.encode("ascii")).hexdigest()[:8]


def scan(root) -> list[Hit]:
    """**纯扫描，不删任何东西。**

    符号链接不跟进 —— 跟进会让扫描走出 root，而删除阶段拒绝 root 之外的路径，
    两者不一致就会留下「报了却删不掉」的永久红。
    """
    base = Path(root).resolve()
    if not base.is_dir():
        raise GuardError(f"扫描根不是目录：{base}")
    hits: list[Hit] = []
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        d = Path(dirpath)
        for name in sorted(dirnames):
            if name in ANSWER_PLANE_DIRS:
                hits.append(Hit(str((d / name).relative_to(base)), "answer_plane_dir",
                                f"答案面目录名 {name}/", 0, "", is_dir=True))
            elif _GOLD_TEXT_RE.search(name):
                # 目录名**本身**是串。里面的东西可以完全干净 ——
                # 前三条判据一条都不占，而目录名会随每一次 `ls` 泄漏出去。
                hits.append(Hit(str((d / name).relative_to(base)), "gold_token_in_path",
                                f"目录名含 gold 串（{token_ref(_GOLD_TEXT_RE.search(name).group(0))}）",
                                0, "", is_dir=True))
        for name in sorted(filenames):
            p = d / name
            if p.is_symlink():
                continue
            rel = str(p.relative_to(base))
            if _GOLD_TEXT_RE.search(name):
                m = _GOLD_TEXT_RE.search(name)
                hits.append(Hit(rel, "gold_token_in_path",
                                f"文件名含 gold 串（{token_ref(m.group(0))}）", 0, ""))
                continue
            try:
                sha, size = _sha256_and_size(p)
                tok = has_gold(p)
                if name in ANSWER_PLANE_NAMES:
                    # 文件名已经够判了，但**内容也要记** —— 事后评估一次泄漏有多重，
                    # 靠的是「这份东西里有没有 gold 串」，而不是「它叫什么名字」。
                    detail = f"答案面文件名 {name}"
                    if tok:
                        detail += f"；且含 gold 串（{token_ref(tok)}）"
                    hits.append(Hit(rel, "answer_plane_name", detail, size, sha))
                    continue
            except OSError as e:
                # 读不了要**响**，不许当成「查过了没有」（F7）。
                hits.append(Hit(rel, "unreadable", f"读不了（{e}）", -1, ""))
                continue
            if tok:
                hits.append(Hit(rel, "gold_token", f"gold 串（{token_ref(tok)}）", size, sha))
    return hits


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="milliseconds")


#: 与 `gateway/access_log.py` 的 entry **同键同序**。加字段只许往 `extra` 里加。
RECORD_KEYS: tuple[str, ...] = (
    "ts", "config_id", "task_id", "run_id", "arm", "method", "path", "params",
    "as_of", "decision", "reason", "status", "backend", "rows", "elapsed_ms",
    "freeze_line", "pid", "extra",
)


def record(hit: Hit, *, root: str, phase: str, deleted: bool | None,
           error: str | None = None, reason: str = REASON) -> dict:
    """一条日志记录。

    `phase`：`detected`（**删之前**先落一条 —— 进程死在删的中途也留得下证据）
    / `purged`（删之后的结果）。
    """
    return {
        "ts": _now(),
        "config_id": None,
        "task_id": None,
        "run_id": None,
        "arm": None,
        "method": "SCAN",
        # **路径也脱敏**：目录/文件名里可以直接带串（`mkdir <gold 串>`），
        # 原样写进日志会让日志自己再次变成违禁品 —— 这正是自噬循环的另一个入口。
        "path": redact(hit.path),
        "params": {"root": root, "phase": phase},
        "as_of": None,
        "decision": "deny",
        "reason": reason,
        "status": 0,
        "backend": "f02_answer_plane_guard",
        "rows": None,
        "elapsed_ms": None,
        # **不留字面量**（裁定 2026-09-05，N-95）：这里曾写死 "2026-07-31"，
        # 而 `genebench_config.FREEZE_DATE` 是另一份互不知情的字面量。改一处不改另一处，
        # 守门记的冻结线就与全局的分叉 —— 分叉的表现是「日志里的冻结线是对的」而实际不是。
        # 取不到就记 `None`（诚实的"不知道"），**不拿一个可能过期的常量顶上**。
        # 值由 f01 侧的推送脚本从 `cfg.FREEZE_DATE` 写进 f02 的 systemd 单元。
        "freeze_line": os.environ.get("GENEBENCH_FREEZE_DATE") or None,
        "pid": os.getpid(),
        "extra": {"kind": hit.kind, "detail": redact(hit.detail), "size": hit.size,
                  "sha256": hit.sha256, "is_dir": hit.is_dir,
                  "deleted": deleted, "error": error},
    }


def append(log_path, entry: dict) -> None:
    p = Path(log_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(p.parent, 0o700)
    except OSError:
        pass
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass


def owned_paths(log_path) -> set[Path]:
    """**本门自己的三个文件**：日志、闩、**以及它自己的源码**。

    它们住在扫描根里面，但绝不许被自己删掉。源码那条是 2026-09-05 真机实测加的：
    我在一句注释里写了一个完整的示例串，下一轮扫描把**门自己**删了，
    此后每次运行都是 `rc=2 文件不存在` —— **门把自己关掉了，而且看起来像环境坏了**。

    注意这**不是豁免**：它们照样被扫、照样进日志、照样落闩 ——
    只是处置从「删除」换成「拒绝自删，标人工处置」。
    豁免会造出一个「往日志里藏答案面」的口子，这里没有那个口子。
    """
    lp = Path(log_path)
    return {lp.resolve(strict=False),
            latch_path(log_path).resolve(strict=False),
            Path(__file__).resolve()}


def purge(hits, root, *, log_path, dry_run: bool = False) -> list[dict]:
    """删除命中项并落日志。返回 `purged` 阶段的记录。

    顺序：**目录先删**（整棵），再删剩下的文件 —— 反过来会对已经消失的文件报错。
    每一项**先记 detected、再删、再记 purged**。
    """
    base = Path(root).resolve()
    owned = owned_paths(log_path)
    out: list[dict] = []
    for h in sorted(hits, key=lambda x: (not x.is_dir, x.path)):
        append(log_path, record(h, root=str(base), phase="detected", deleted=None))
        if (base / h.path).resolve(strict=False) in owned:
            r = record(h, root=str(base), phase="purged", deleted=False,
                       error="这是本门自己的证据文件，**拒绝自删** —— 需人工处置。"
                             "（写出去的文本已脱敏；这里还命中说明是别人写进去的）")
            append(log_path, r)
            out.append(r)
            continue
        if h.kind == "unreadable":
            r = record(h, root=str(base), phase="purged", deleted=False,
                       error="读不了，未删 —— 需人工处置")
            append(log_path, r)
            out.append(r)
            continue
        deleted, err = False, None
        try:
            resolved = (base / h.path).resolve()
            # **删除只许发生在 root 之内，且不许是 root 自己。**
            if resolved == base or base not in resolved.parents:
                raise GuardError(f"拒绝删除 root 之外或 root 自身：{resolved}")
            if dry_run:
                err = "dry-run，未删"
            elif h.is_dir:
                if resolved.is_dir():
                    shutil.rmtree(resolved)
                deleted = not resolved.exists()
            else:
                if resolved.exists():
                    resolved.unlink()
                deleted = not resolved.exists()
        except (OSError, GuardError) as e:
            err = f"{type(e).__name__}: {e}"
        r = record(h, root=str(base), phase="purged", deleted=deleted, error=err)
        append(log_path, r)
        out.append(r)
    return out


#: 门的**三个自有文件**：源码 + systemd 的两个单元（裁定 2026-09-05）。
#: `~` 会在读取时展开；单元不存在时记 `None`（**不是省略**）——
#: 「没装单元」与「装了但没记」必须分得开。
OWN_FILES: tuple[str, ...] = (
    __file__,
    "~/.config/systemd/user/genebench-answer-plane-scan.service",
    "~/.config/systemd/user/genebench-answer-plane-scan.timer",
)

#: 自身完整性的基线。部署时用 `--write-identity` 生成，之后每次运行先核。
IDENTITY_NAME = "answer_plane_guard.identity.json"


def identity() -> dict:
    """三个自有文件的 sha256。读不到的记 `None` 并附原因。"""
    out: dict[str, dict] = {}
    for raw in OWN_FILES:
        p_ = Path(raw).expanduser()
        try:
            out[str(p_)] = {"sha256": _sha256_and_size(p_)[0], "size": p_.stat().st_size}
        except OSError as e:
            out[str(p_)] = {"sha256": None, "size": None, "error": f"{type(e).__name__}: {e}"}
    return out


def identity_path() -> Path:
    return Path(__file__).resolve().parent / IDENTITY_NAME


def check_identity() -> list[str]:
    """自身完整性核对。返回不一致的描述（空 = 一致或没有基线）。

    **说清它能挡什么、不能挡什么**：改了门的人当然也能改这份基线，
    所以它**挡不住蓄意篡改** —— 它挡的是**部署漂移**：
    推了一半、推了旧版本、文件损坏。真正的防篡改在另一侧 ——
    `inject.py` 把这三个 sha 记进 `inject.json`，由 **f01** 拿仓库里的那份去比。
    自证与他证要分开，不能让被查方自己出具唯一的证明。
    """
    ip = identity_path()
    if not ip.is_file():
        return []                       # 没有基线：不报不一致，但 `--write-identity` 会提示
    try:
        want = json.loads(ip.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return [f"完整性基线读不出来（{e}）"]
    got = identity()
    bad = []
    for k, w in want.items():
        g = got.get(k)
        if g is None:
            bad.append(f"基线里有 {k}，现在读不到")
        elif g.get("sha256") != w.get("sha256"):
            bad.append(f"{k} 的 sha256 变了：基线 {str(w.get('sha256'))[:12]}… "
                       f"实为 {str(g.get('sha256'))[:12]}…")
    for k in set(got) - set(want):
        bad.append(f"多出一个自有文件 {k}（基线里没有）")
    return bad


# ═══════════════════════════════════════════════════════════════════════════
# **容器边界口径**（v1.0.16 起 —— 用户裁定 2026-09-11，N-627 走 B）
# ═══════════════════════════════════════════════════════════════════════════
#
# 旧口径（v1.0.15 及以前）是**执行面口径**：「答案面不上执行面」——
# f02 这台机器上的任何一棵树里都不许出现答案面。它的实现就是上面的 `scan()`：
# 扫 `/data/genebench_runner` 整棵，命中即删。
#
# **为什么改**：用户裁定公开树**带全部答案面**（oracle 源码、gold 子集、
# calibration、评分器）—— 外部用户要能自己算分，否则这个基准对外只有一半。
# 一旦答案面可以公开，「哪台机器上有它」就不再是判据了：
# 公网上人人都能 clone 到它，而 f02 恰恰是**我们控制得最严的**那台机器。
#
# **新口径 = 容器边界**，两条判据：
#   ① **答案面永不挂进 agent 容器** —— 判的是**挂载面**（compose 的 volumes 全家），
#      不是「这台机器上有没有」。
#   ② **run dir 里不得出现答案面** —— run dir 是 agent 写得到、事后要归档进结果库的地方。
#   单机形态（外部用户在自己机器上跑）下，②的等价表述是「答案面位于 `/task` 之外」。
#
# **处置为什么与树模式相反 —— 容器模式绝不删**：
# 树模式里命中的是一份**不该在那儿的副本**，删掉它是止损。
# 容器模式里命中的往往是**答案面本体**（`$GB/reference`、`gold/`、公开树的 `scorer/`）——
# 它只是被错误地挂了进去。**删它等于把基准本身删了。**
# 所以容器模式的处置是 **拒绝启动 + 落闩 + 记日志**，一个字节都不动。
# 这不是「弱一点的门」：在它该管的那个时刻（容器还没起来），拒绝启动是**完整**的止损。
#
# **树模式没有退役**：它降为第二道 —— f02 上那个每小时的 timer 照跑，
# 因为私有通道的执行面**仍然**不该有答案面（私有 gold 全量不公开）。
# 两道门的判据不同、处置不同、reason 码不同，日志里要分得开。

#: 容器模式的 reason 码。与树模式的 `answer_plane_detected` **分开** ——
#: 两者的处置完全不同（删 vs 拒绝启动），合成一个码会让事后分不清当时发生了什么。
REASON_MOUNT = "answer_plane_mounted"


@dataclass(frozen=True)
class Mount:
    """一条挂载：**宿主侧的 source** 被挂进容器的 `target`。

    `source` **原样保留**（可能是相对路径、`~`、`${VAR}` 插值）——
    规范化会让「看不懂的挂载」长得像一条正常挂载，而看不懂 ≠ 没有挂载。
    """

    service: str
    source: str
    target: str
    raw: str = ""

    def label(self) -> str:
        return f"{self.service}:{self.source}→{self.target}"


def _as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def _split_short(spec: str) -> tuple[str, str]:
    """短语法 `src:dst[:opts]`。只有 Linux 路径，不管 Windows 盘符。"""
    parts = str(spec).split(":")
    if len(parts) == 1:
        return "", parts[0]            # 匿名卷：没有宿主侧
    return parts[0], parts[1]


def compose_mounts(compose_path) -> list[Mount]:
    """从一份 compose 里抽出**整个挂载面**。

    **看所有服务，不只 `task`**：边车与任务容器在同一个 compose 项目里，
    只看 `task` 会漏掉「挂给边车、边车再递给任务」这一步（而那一步我们自己就在用：
    `logdir` 同时挂给两边）。信任边界是**容器**，不是某一个服务名。

    三种 bind 写法**一条都不许漏**（判据与 `runner/c41/runner_core.py::lint_compose`
    的 L-5 / L-5b 同源 —— 2026-09-04 红队实测过第三种对 grep 完全沉默）：
      ① 短语法 `- /host:/container:ro`
      ② 长语法 `- {type: bind, source: /host, target: /container}`
      ③ 顶层 named volume 的 `driver_opts: {type: none, device: /host, o: bind}`
    """
    p = Path(compose_path)
    text = p.read_text(encoding="utf-8")
    try:
        import yaml                                        # noqa: PLC0415
    except ImportError as e:                               # pragma: no cover
        # **读不出来要响**，不许当成「查过了没有挂载」（与 F7 同一条原则）。
        raise GuardError(f"解析不了 compose（缺 PyYAML：{e}）：{p}") from e
    try:
        doc = yaml.safe_load(text) or {}
    except yaml.YAMLError as e:
        raise GuardError(f"compose 不是合法 YAML：{p}（{e}）") from e
    if not isinstance(doc, dict):
        raise GuardError(f"compose 顶层不是映射：{p}")

    out: list[Mount] = []
    svcs = doc.get("services") or {}
    named_to_service: dict[str, str] = {}
    for sname, svc in (svcs.items() if isinstance(svcs, dict) else []):
        for vol in _as_list((svc or {}).get("volumes")):
            if isinstance(vol, dict):
                src, dst = str(vol.get("source") or ""), str(vol.get("target") or "")
                raw = repr(vol)
            else:
                src, dst = _split_short(str(vol))
                raw = str(vol)
            if src and not src.startswith("/"):
                named_to_service.setdefault(src, str(sname))
            out.append(Mount(str(sname), src, dst, raw))

    tv = doc.get("volumes")
    for vname, vdef in ((tv or {}) if isinstance(tv, dict) else {}).items():
        opts = ((vdef or {}).get("driver_opts") or {}) if isinstance(vdef, dict) else {}
        dev = str(opts.get("device") or "")
        if not dev:
            continue
        out.append(Mount(named_to_service.get(str(vname), f"<volume {vname}>"), dev,
                         f"<named volume {vname}>", repr(vdef)))
    return out


def _judge_mount_source(host: Path, prefix: str) -> list[Hit]:
    """对一个**已存在的**宿主挂载源跑答案面判据，`Hit.path` 打上挂载前缀。

    目录走 `scan()` —— **同一套判据，不另写一份**：另写一份就会漂，
    而漂的表现是「树模式认得出、容器模式认不出」。
    """
    if host.is_dir():
        return [Hit(f"{prefix}/{h.path}", h.kind, h.detail, h.size, h.sha256, h.is_dir)
                for h in scan(host)]
    try:
        sha, size = _sha256_and_size(host)
        tok = has_gold(host)
    except OSError as e:
        return [Hit(prefix, "unreadable", f"挂载源读不了（{e}）", -1, "")]
    if host.name in ANSWER_PLANE_NAMES:
        detail = f"挂载源就是答案面文件 {host.name}"
        if tok:
            detail += f"；且含 gold 串（{token_ref(tok)}）"
        return [Hit(prefix, "answer_plane_name", detail, size, sha)]
    if tok:
        return [Hit(prefix, "gold_token", f"挂载源含 gold 串（{token_ref(tok)}）", size, sha)]
    return []


def scan_mount_face(mounts, *, run_dir=None) -> list[Hit]:
    """**容器边界口径的判据本体。纯判断，一个字节都不删。**

    判两件事：
      ① 挂进容器的每一个宿主路径里不得出现答案面（含**路径本身**就是答案面的情形）；
      ② `run_dir` 整棵里不得出现答案面。

    ① **不要求挂载源此刻存在**：`- /data/shared/genebench/reference:/task/ref` 这一条，
    哪怕现在 `reference/` 还没建出来，**声明本身就是违规** —— 容器起来的那一刻它就在那儿。
    「检查时不存在」与「运行时不存在」是两个时刻（同 L-5a 那条 TOCTOU）。
    """
    hits: list[Hit] = []
    for mt in mounts:
        prefix = f"mount[{mt.service}:{mt.target or '?'}]{mt.source or '?'}"
        if not mt.source:
            hits.append(Hit(prefix, "unreadable",
                            f"解析不出挂载源的条目 {mt.raw!r} —— 看不懂的挂载不许放行："
                            f"看不懂 ≠ 没有挂载", -1, ""))
            continue
        if not mt.source.startswith("/"):
            # 相对路径 / `~` / `${VAR}` 插值 / 匿名卷 / 普通 named volume：
            # compose 在**运行时**才解析，此刻看不出它指向哪。扫不了要说出来，不许当绿。
            hits.append(Hit(prefix, "unreadable",
                            f"挂载源不是绝对路径（{mt.source!r}）—— 运行时才解析，"
                            f"此刻判不了它指向哪", -1, ""))
            continue
        host = Path(mt.source)
        # **先判路径名，再判内容**：路径名的判据对「源还不存在」也成立。
        seg = next((s for s in host.parts if s in ANSWER_PLANE_DIRS), None)
        if seg is not None:
            hits.append(Hit(prefix, "answer_plane_dir",
                            f"挂载源路径里有答案面目录段 {seg}/ → 容器内 {mt.target}",
                            0, "", is_dir=host.is_dir()))
            continue
        m = _GOLD_TEXT_RE.search(str(host))
        if m:
            hits.append(Hit(prefix, "gold_token_in_path",
                            f"挂载源路径含 gold 串（{token_ref(m.group(0))}）"
                            f" → 容器内 {mt.target}", 0, "", is_dir=host.is_dir()))
            continue
        if host.name in ANSWER_PLANE_NAMES and not host.exists():
            hits.append(Hit(prefix, "answer_plane_name",
                            f"挂载源就是答案面文件名 {host.name}（此刻不存在，"
                            f"容器起来时会在）", 0, ""))
            continue
        if not host.exists():
            hits.append(Hit(prefix, "unreadable",
                            f"挂载源此刻不存在（{mt.source}）—— 容器起来时它会在，"
                            f"扫不了不等于扫过了", -1, ""))
            continue
        hits.extend(_judge_mount_source(host, prefix))
    if run_dir is not None:
        rd = Path(run_dir)
        if not rd.is_dir():
            hits.append(Hit(f"run_dir[{rd}]", "unreadable", "run dir 不是目录", -1, ""))
        else:
            hits.extend(Hit(f"run_dir/{h.path}", h.kind, h.detail, h.size, h.sha256, h.is_dir)
                        for h in scan(rd))
    return hits


def scan_container(compose_path=None, *, run_dir=None, extra_mounts=()) -> list[Hit]:
    """便捷入口：compose（可选）+ 手工声明的挂载（可选）+ run dir（可选）。"""
    mounts = list(compose_mounts(compose_path)) if compose_path else []
    mounts.extend(extra_mounts)
    return scan_mount_face(mounts, run_dir=run_dir)


def parse_mount_arg(s: str) -> Mount:
    """`--mount /host:/container`，或 `--mount /host`（target 未知时记 `?`）。"""
    src, _, dst = s.partition(":")
    return Mount("<cli>", src, dst or "?", s)


DEFAULT_ROOT = "/data/genebench_runner"
DEFAULT_LOG = "/data/genebench_runner/logs/answer_plane.jsonl"

#: **闩**。任何一次命中都会写它，而**干净的一轮不会清它** ——
#: 它要一直留到有人来看。
#:
#: 为什么光靠 systemd 的 failed 状态不够（2026-09-05 真机实测）：
#: timer 每小时跑一次，下一次干净运行会把上一次的 failed 覆盖掉；
#: 凌晨三点拦下的一次泄漏，到早上在 `systemctl --user --failed` 里已经看不见了。
#: **「在我不在场时否决我」还要求「在我不在场时留住证据」。**
LATCH_NAME = "ANSWER_PLANE_INCIDENT"


def latch_path(log_path) -> Path:
    return Path(log_path).parent / LATCH_NAME


def trip_latch(log_path, recs: list[dict]) -> Path:
    """写闩。**追加不覆盖** —— 第二次事件不许把第一次的记录顶掉。"""
    p = latch_path(log_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{_now()}  答案面命中 {len(recs)} 项，已按 N-61 处置。"
             f"明细见 {Path(log_path).name}（reason={REASON}）。"]
    for r in recs:
        e = r["extra"]
        # `detail` 里带命中串的哈希引用 —— 闩要能和日志里的条目对上，
        # 而对上靠的是引用，不是原串。
        lines.append(redact(f"    [{e['kind']}] {r['path']}  已删={e['deleted']}  "
                            f"文件sha256={e['sha256'][:16]}  {e['detail']}"))
    lines.append("    **这个文件不会被下一次干净扫描清掉。看过并处置之后，人手删除。**")
    with p.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n\n")
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass
    return p


def main_container(a) -> int:
    """**容器边界口径的入口。退出码 0 = 干净 / 1 = 有命中 / 2 = 扫不了。**

    与树模式的唯一实质差别：**不删**。命中的往往是答案面本体
    （`$GB/reference`、gold、公开树的 `scorer/`）—— 删它等于把基准本身删了。
    在它该管的那个时刻（容器还没起来），**拒绝启动**就是完整的止损。
    """
    mounts = [parse_mount_arg(s) for s in (a.mount or [])]
    if a.compose is None and not mounts and a.run_dir is None:
        print("[红] 容器模式至少要给一个 --compose / --mount / --run-dir —— "
              "什么都不给的一次「绿」是假的", file=sys.stderr)
        return 2
    try:
        hits = scan_container(a.compose, run_dir=a.run_dir, extra_mounts=mounts)
    except (GuardError, OSError) as e:
        print(f"[红] {e}", file=sys.stderr)
        return 2
    face = f"compose={a.compose} mounts={len(mounts)} run_dir={a.run_dir}"
    if not hits:
        print(f"[绿] 容器边界无答案面命中（{face}）")
        return 0
    recs = []
    for h in hits:
        r = record(h, root=face, phase="detected", deleted=False,
                   error="容器边界口径：**拒绝启动，一个字节都不删** —— "
                         "命中的往往是答案面本体，删它等于把基准删了",
                   reason=REASON_MOUNT)
        append(a.log, r)
        recs.append(r)
    latch = trip_latch(a.log, recs)
    for r in recs:
        e = r["extra"]
        print(f"  [{e['kind']}] {r['path']}  {e['detail']}", file=sys.stderr)
    print(f"\n**容器边界命中 {len(hits)} 项 —— 拒绝启动。**"
          f"记录见 {a.log}；闩已落在 {latch}", file=sys.stderr)
    return 1


def main(argv=None) -> int:
    """退出码：**0 = 干净**；1 = 有命中（不论删没删干净）；2 = 扫不了。

    「有命中」本身就是事件，**不因为删干净了就当成功** ——
    调用方（推送脚本、timer）要能靠退出码知道「刚才发生过一次泄漏」。
    systemd 那边**故意不写 `SuccessExitStatus=1`**：命中就让 unit 进 failed，
    立刻可见；而 failed 会被下一次干净运行覆盖，所以另有 `LATCH_NAME` 这道闩。
    """
    ap = argparse.ArgumentParser(
        description="答案面守门：--mode container（容器边界口径，拒绝启动不删）"
                    " / --mode tree（执行面树口径，命中即删）")
    ap.add_argument("--mode", choices=("tree", "container"), default="tree",
                    help="v1.0.16 起 container 是**主口径**；tree 保留为第二道"
                         "（私有通道执行面仍不该有答案面）。默认仍是 tree —— "
                         "f02 上那个每小时 timer 的命令行没变，改默认值会把它悄悄改掉。")
    ap.add_argument("--compose", default=None,
                    help="container 模式：从这份 compose 抽挂载面（三种 bind 写法全看）")
    ap.add_argument("--mount", action="append", default=[],
                    help="container 模式：再补一条挂载 `/host[:/container]`，可重复")
    ap.add_argument("--run-dir", default=None, help="container 模式：本 run 的 run dir")
    ap.add_argument("--root", default=DEFAULT_ROOT)
    ap.add_argument("--log", default=DEFAULT_LOG)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--print-identity", action="store_true",
                    help="打印三个自有文件的 sha256 并退出（部署与 inject.json 用）")
    ap.add_argument("--write-identity", action="store_true",
                    help="把当前 identity 写成基线（**部署时**用，不要在别的时候用）")
    a = ap.parse_args(argv)
    if a.mode == "container":
        return main_container(a)
    if a.print_identity:
        print(json.dumps(identity(), ensure_ascii=False, indent=1))
        return 0
    if a.write_identity:
        ip = identity_path()
        ip.write_text(json.dumps(identity(), ensure_ascii=False, indent=1), encoding="utf-8")
        try:
            os.chmod(ip, 0o600)
        except OSError:
            pass
        print(f"完整性基线已写 {ip}")
        return 0

    # **先核自身，再扫别人。** 不一致时**照常扫** ——
    # 因为自检失败而停掉这道门，等于让「改坏它」成为关掉它的办法。
    drift = check_identity()
    if drift:
        for d in drift:
            print(f"  **门自身完整性不一致**：{d}", file=sys.stderr)
        h = Hit(str(identity_path().name), "guard_integrity", "；".join(drift)[:300], 0, "")
        append(a.log, record(h, root=a.root, phase="detected", deleted=None))
        trip_latch(a.log, [record(h, root=a.root, phase="purged", deleted=False,
                                  error="自身完整性不一致 —— 不自删，需人工核对部署")])
    try:
        hits = scan(a.root)
    except GuardError as e:
        print(f"[红] {e}", file=sys.stderr)
        return 2
    if not hits:
        if drift:
            # 树是干净的，但**门自己漂了** —— 那同样是一件必须被人看见的事。
            # 返回 0 的话，部署少写一次 `--write-identity` 就再也没人知道。
            print(f"[黄] {a.root} 无答案面命中，但**门自身完整性不一致**（见闩）",
                  file=sys.stderr)
            return 1
        print(f"[绿] {a.root} 无答案面命中")
        return 0
    recs = purge(hits, a.root, log_path=a.log, dry_run=a.dry_run)
    for r in recs:
        e = r["extra"]
        print(f"  [{e['kind']}] {r['path']}  已删={e['deleted']}  {e['error'] or ''}",
              file=sys.stderr)
    left = [r for r in recs if not r["extra"]["deleted"]]
    latch = trip_latch(a.log, recs)
    print(f"\n**答案面命中 {len(hits)} 项**，未删 {len(left)} 项。"
          f"记录见 {a.log}；闩已落在 {latch}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
