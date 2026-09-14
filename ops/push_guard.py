# -*- coding: utf-8 -*-
"""推送到执行面前的**守门**（2026-09-04，红线接触后补）。

**它为什么存在**：本轮我自己犯过一次 —— 用一条手写的
`rsync -a /data/shared/genebench/scratch/a1/ f02:/data/genebench_runner/a1/`
把整棵目录推了过去，其中 `reference/` 含 `canary.json`（gold_token）、
D 面 `task.yaml`、`solution/solve.py`、`scorer.yaml`。
**那是「答案面上执行面」，红线。** 发现后立即删除并核实 f02 上零残留。

**判据是封闭的**：不列「不许推什么」（黑名单会漏），而是复用
`genetask.bundle` 已经定义好的**「bundle 里允许有什么」**——
`X_ALLOWED_FILES` + `X_ALLOWED_PREFIXES`。多一个文件就红。

外加一条**内容**判据：任何文件里出现 gold 串的形状即红 ——
路径判据挡结构，内容判据挡「一个被塞进 work/ 的答案文件」。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

# 直接当脚本跑时 sys.path[0] 是 ops/,仓库根不在路径上。相对推导,不硬编码。
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from genetask.bundle import X_ALLOWED_FILES, X_ALLOWED_PREFIXES

#: gold 串的**形状**（`genetask/packager.py::_token` 的产物：`GBC-G-<16 hex>`）。
#: 判形状不判具体值 —— 具体值每次打包都换。
GOLD_TOKEN_RE = re.compile(r"GBC-G-[0-9a-f]{16}")
#: 只在数据面出现的文件名。**这是纵深，不是判据** —— 判据是上面的允许集。
ANSWER_PLANE_NAMES = ("canary.json", "scorer.yaml", "taskspec.json",
                      "equivalence.md", "slots.json", "_ledger.jsonl",
                      "solve.py", "oracle_artifact.json", "slice.parquet")
ANSWER_PLANE_SEGMENTS = ("reference", "gold", "solution", "scorer")

TEXT_SUFFIXES = (".py", ".yaml", ".yml", ".json", ".md", ".txt", ".jsonl", ".sh")

#: **整集不许上执行面**的 set_id（红队 2026-09-07 finding 8，红线 B2）。
#: 上面两道判据查的是「树里有没有答案面的**形状**」；这张表管的是**语义**。
#:
#: **`v1.0-adapt` 这条已于 2026-09-10 显式解除（用户裁定 N-348）——记因照录，不要凭猜恢复：**
#:   * 原文：「适配赛道题源 = 33 道出集规定题的 oracle 产物（探针题不入）……守门 ops/push_guard.py
#:     里『按集拒 v1.0-adapt』要显式解除并**记因**」。
#:   * **解除的后果，用户已知情并写进裁定**：这些题的 oracle 产物由此进入执行面 —— **跑过适配
#:     赛道的被测方，主赛道这些题算「可能已见过答案」**。写在
#:     `ops/specs/fairness_protocol.md` §7、`ops/reports/known_limits_v1.md`、
#:     `ops/specs/adaptation_track.md` §7，并随适配表与主表的脚注一起印出来。
#:   * **保留的更窄的门见 `ADAPT_SET_IDS` / `ADAPT_DEST_PREFIX`**：解除的是「整集不许推」，
#:     不是「随便往哪儿推」。适配 bundle 只许落在执行面的**适配根**下，落点必须**显式声明**
#:     （没声明 = 拒，不是 = 放行）—— 混进主赛道的 batch 目录仍然是红线 B2 的事故。
SET_IDS_NOT_PUSHABLE: dict[str, str] = {}
#: 通行证里自报「本 bundle 的内容由答案面派生」的 origin 值。
#: **适配集是这条的唯一例外**（N-348）：它的内容按裁定就是 gold 派生的，且已在别处记了因。
ORIGINS_NOT_PUSHABLE: tuple[str, ...] = ("gold_derived",)
#: 按 N-348 放行的赛道集。放行不等于没门 —— 见下面两条。
ADAPT_SET_IDS: tuple[str, ...] = ("v1.0-adapt",)
#: 适配 bundle 在执行面上**唯一**允许的落点前缀。主赛道的 batch 目录（m6/ v1demo/ a1/ …）不在其中。
ADAPT_DEST_PREFIX = "/data/genebench_runner/adapt/"
#: 落点从哪里来。`assert_pushable(..., dest=...)` 优先；命令行第三个参数次之；再次是这个环境变量
#: （`ops/push_bundle_to_f02.sh` 调 push_guard 时会把环境原样传下来）。
#: **三者都没有 = 拒**：适配集的落点判据不能靠「大概推对了地方」。
DEST_ENV = "GENEBENCH_PUSH_DEST"
#: 从 bundle 的 task.yaml 里读 set_id。**用正则不用 yaml**：这条判据要在任何一台机器上
#: 都能跑，而 yaml 在执行面是软依赖（`runner/inject.py` 为此也是局部 import）。
_SET_ID_RE = re.compile(r"(?m)^set_id:\s*['\"]?([A-Za-z0-9._:+-]+)")


class PushBlocked(RuntimeError):
    """推送被拦。**不放宽判据、不加例外** —— 红线一侧没有「这次算了」。"""


def check_bundle_tree(bundle_dir) -> list[str]:
    """一个 bundle 目录能不能推。空列表 = 绿。"""
    root = Path(bundle_dir)
    if not root.is_dir():
        return [f"不是目录：{root}"]
    bad: list[str] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = str(p.relative_to(root))
        if rel not in X_ALLOWED_FILES and not rel.startswith(X_ALLOWED_PREFIXES):
            bad.append(f"允许集之外：{rel}（bundle 只许 {X_ALLOWED_FILES}+{X_ALLOWED_PREFIXES}）")
        if p.name in ANSWER_PLANE_NAMES:
            bad.append(f"**答案面文件名**：{rel}")
        if set(Path(rel).parts) & set(ANSWER_PLANE_SEGMENTS):
            bad.append(f"**答案面路径段**：{rel}")
        if p.suffix in TEXT_SUFFIXES:
            try:
                txt = p.read_text(encoding="utf-8", errors="replace")
            except OSError as e:
                bad.append(f"读不了 {rel}（{e}）—— 读不了 ≠ 查过了没有")
                continue
            m = GOLD_TOKEN_RE.search(txt)
            if m:
                bad.append(f"**gold 串**出现在 {rel}（形状 {m.group(0)[:10]}…）")
    return bad


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_manifest(bundle_dir, manifest_path) -> list[str]:
    """通行证与**真的要推的那棵树**是不是同一棵（D-21：两个独立标识符必须对齐）。

    上面的 `check_bundle_tree` 管「树里不许有什么」，这里管「树就是通行证说的那棵」。
    两件事都要：一棵合法形状但内容被改过的树能过前者，过不了这里。
    """
    from ops.freeze_v10 import frozen_ref

    root, mp = Path(bundle_dir), Path(manifest_path)
    if not mp.is_file():
        return [f"通行证不在：{mp} —— **没有通行证不等于通行证没问题**"]
    try:
        m = json.loads(mp.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return [f"通行证读不出来（{e}）"]
    bad: list[str] = []
    if tuple(m.get("allowed_files") or ()) != X_ALLOWED_FILES or \
            tuple(m.get("allowed_prefixes") or ()) != X_ALLOWED_PREFIXES:
        bad.append("通行证里的允许集与 genetask.bundle 的不一致 —— 它描述的是另一份契约")
    if m.get("check_export"):
        bad.append(f"通行证里 check_export 非空（{len(m['check_export'])} 条）—— 导出自检就没过")
    declared = dict(m.get("files") or {})
    on_disk = {str(p.relative_to(root)): p for p in root.rglob("*") if p.is_file()}
    for extra in sorted(set(on_disk) - set(declared)):
        bad.append(f"树里有通行证没写的文件：{extra}")
    for missing in sorted(set(declared) - set(on_disk)):
        bad.append(f"通行证写了但树里没有：{missing}")
    for rel in sorted(set(declared) & set(on_disk)):
        got = _sha256(on_disk[rel])
        if got != declared[rel]:
            bad.append(f"内容与通行证不符：{rel}（记 {declared[rel][:12]}… 实 {got[:12]}…）")
    try:
        cur = frozen_ref()          # verify=True：现算一遍冻结根，不是读记录值（F7）
    except Exception as e:                                    # noqa: BLE001
        bad.append(f"取不到当前冻结引用（{e}）—— 无法判断 bundle 是不是过期的")
    else:
        if m.get("frozen_manifest") != cur:
            bad.append(f"bundle 的冻结引用已过期：通行证 {m.get('frozen_manifest')} ≠ 当前 {cur}"
                       "\n    → **重新导出**，不要改通行证")
    return bad


def check_pushable_set(bundle_dir, manifest_path=None, dest: str | None = None) -> list[str]:
    """**按集**判：这一集的内容允许上执行面吗（红线 B2，红队 2026-09-07 finding 8）。

    `check_bundle_tree` 查形状、`check_manifest` 查「树就是通行证说的那棵」——
    两道都看不见「这份合法形状的 work/input/*.json 里装的是别的题的答案」。
    判据长在**集**上（`set_id` / 通行证的 `origin`），因为它本来就是集一级的性质：
    单个文件怎么看都是干净的。
    """
    bad: list[str] = []
    sids: set[str] = set()
    tp = Path(bundle_dir) / "task.yaml"
    if tp.is_file():
        m = _SET_ID_RE.search(tp.read_text(encoding="utf-8", errors="replace"))
        if m:
            sids.add(m.group(1))
    origin = None
    if manifest_path is not None and Path(manifest_path).is_file():
        try:
            mm = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            mm = {}
        if mm.get("set_id"):
            sids.add(str(mm["set_id"]))
        origin = mm.get("origin")
    for sid in sorted(sids):
        if sid in SET_IDS_NOT_PUSHABLE:
            bad.append(f"**整集不许上执行面**：set_id={sid} —— {SET_IDS_NOT_PUSHABLE[sid]}")
    is_adapt = bool(sids & set(ADAPT_SET_IDS))
    if is_adapt:
        # **N-348 解除「按集拒」之后保留的那道更窄的门。** 判据是**落点**：
        # 适配 bundle 的 work/input/broken.json 内容上就是主赛道那几道题的答案，
        # 放它上执行面是裁定过的，把它放进**主赛道的 batch 目录**不是。
        d = dest if dest is not None else os.environ.get(DEST_ENV)
        if not d:
            bad.append(
                f"适配集 bundle 没有声明落点 —— set_id={sorted(sids)} 按 N-348 允许上执行面，"
                f"但只许落在 {ADAPT_DEST_PREFIX} 下，而这一次**落点不明**。"
                f"\n    → 推之前显式给：`{DEST_ENV}=<目标目录> ops/push_bundle_to_f02.sh …`"
                f"（或 `push_guard.py <bundle> <manifest> <目标目录>`）。"
                f"\n    **没声明不等于推对了地方。**")
        elif not str(d).rstrip("/").startswith(ADAPT_DEST_PREFIX.rstrip("/") + "/") \
                and str(d).rstrip("/") != ADAPT_DEST_PREFIX.rstrip("/"):
            bad.append(f"适配集 bundle 的落点 {d} 不在 {ADAPT_DEST_PREFIX} 下 —— "
                       f"N-348 放行的是**适配赛道**，不是把这些内容混进主赛道的 batch 目录")
    if origin in ORIGINS_NOT_PUSHABLE and not is_adapt:
        bad.append(f"通行证自报 origin={origin!r} —— 由答案面派生的内容不上执行面")
    return bad


def assert_pushable(bundle_dir, manifest_path=None, dest: str | None = None) -> None:
    bad = check_bundle_tree(bundle_dir)
    if manifest_path is not None:
        bad += check_manifest(bundle_dir, manifest_path)
    # **第三道，按集**（红队 finding 8）：形状干净不等于内容可以上执行面。
    bad += check_pushable_set(bundle_dir, manifest_path, dest)
    if bad:
        raise PushBlocked(
            "推送被拦（答案面不上执行面）：\n  " + "\n  ".join(bad)
            + "\n\n判据是**封闭**的：bundle 里只许有 task.yaml + arms/ + image/ + work/。"
            "\n不要在这里加例外 —— 2026-09-04 的那次泄漏就是一条手写 rsync 绕过了这条判据。")


def main(argv=None) -> int:
    import sys
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) not in (2, 3):
        print("用法：push_guard.py <bundle_dir> <manifest.json> [<f02 目标目录>]", file=sys.stderr)
        return 2
    rc = 0
    for d in args[:1]:
        try:
            assert_pushable(d, args[1], args[2] if len(args) > 2 else None)
            print(f"[绿] {d}")
        except PushBlocked as e:
            print(f"[红] {e}", file=sys.stderr)
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
