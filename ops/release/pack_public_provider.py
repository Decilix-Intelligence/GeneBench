#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""**形态 A**：把公开通道打成一个可下载的冻结包（卡 1.4 / 卡 2.5 §9）。

    $PY ops/release/pack_public_provider.py --dry-run       # 只说要打什么、多大
    $PY ops/release/pack_public_provider.py                 # 打包 + SHA256SUMS + MANIFEST.json
    $PY ops/release/pack_public_provider.py --no-tar        # 只出校验和与清单（快，给形态 B 比对用）
    $PY ops/release/pack_public_provider.py --compare <SHA256SUMS>   # 拿别处重建的树来比

产出三件（互相自洽，缺一不可）::

    genebench_public_provider_v1.tar.gz   包体，**确定性 tar**（见下）
    SHA256SUMS                            逐文件 sha256，`sha256sum -c` 可直接校
    MANIFEST.json                         内容清单 / 构建 HEAD / 冻结线 / 数据源 / 许可状态

**落点由许可状态决定**（`DATA_LICENSE` 顶部那一行，`ops/test_env.py` 有锁盯着）::

    pending_license_text →  $GB/release/_staging_unpublished/public_v1/    （备好，不发）
    granted              →  $GB/release/public_v1/                          （可发）

`test_env.py::test_no_published_provider_package_while_license_text_is_pending`
扫的是 `$GB/snapshots/public`，扫不到 `$GB/release/` —— **但那条锁的意思**是
「许可原文没入库就不许存在打好待发的包」。按那个意思办：pending 期间包只落
`_staging_unpublished/`，且本脚本**拒绝**往可发布路径写。本模块另有
`assert_nothing_published_while_pending()` 把这条判据搬到 `$GB/release/` 上，
由 `ops/test_release_forms.py` 盯着 —— 不是放宽既有那条，是把它的射程补齐。

**确定性 tar**：条目按 arcname 排序、`mtime=0`、`uid=gid=0`、`uname=gname=""`、
权限归一（文件 0644 / 无目录条目），gzip 头的 mtime 也置 0。
同一棵树打两次字节相同 —— 否则「校验和」这个词没有意义。
包里唯一带构建时刻的是 `MANIFEST.json` 的 `built_at`，所以**整包**的可复现口径是
「同一棵树 + 同一个 `--built-at` → tar.gz 逐字节相同」（`--built-at` 见下）。

**A↔B 比对分三堆**（`compare()`）：**数据面**逐文件差一个字节就是红；
`BUILD_STAMPED`（带构建时刻/绝对路径）与 `PACKAGE_PROVIDED`（`docs/`、`selfbuild/`
这两堆**来自仓库工作树**的随包副本）各单列一堆，不判红 —— 理由见那两张表上面的注释。

**包里没有什么**（红线 2，`ops/test_release_forms.py` 有反面测试）：
`scorer/`、`runs_in/`、`gold/`、`memory_probe_answers/` 一个字节都没有；
`reference/` 只有 `PUBLIC_FROZEN_ARTIFACTS` 明列的 `factorlib_pinned/` 三个文件
（N-58⑥：**gold 的定义面**，少了它拿到包的人复现不了 τ）。
本包**不推 f02**、不进 bundle —— 推 f02 只走 `ops/push_bundle_to_f02.sh`。
"""
from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import gzip
import hashlib
import io
import json
import os
import pathlib
import subprocess
import sys
import tarfile
import time
from typing import Any, Iterable, NamedTuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import genebench_config as cfg          # noqa: E402
from snapshots.public import manifest as PM     # noqa: E402

#: 包名。版本跟着 `cfg.PUBLIC_VERSION`（`public_v1`）走，不另起一套版本号。
PACKAGE_NAME: str = "genebench_public_provider_v1"
TARBALL: str = f"{PACKAGE_NAME}.tar.gz"
SUMS_NAME: str = "SHA256SUMS"
MANIFEST_NAME: str = "MANIFEST.json"
README_NAME: str = "README.md"

#: gzip 压缩级。**写死**：级别变了包的字节就变了，而校验和是对外承诺的东西。
GZIP_LEVEL: int = 6

#: `DATA_LICENSE` 的两种状态（与 `ops/test_env.py::LICENSE_STATES` 同源，值不许分叉）。
LICENSE_STATES: tuple[str, ...] = ("pending_license_text", "granted")

#: 包里绝对不许出现的答案面前缀（红线 2）。命中任何一条就 **拒绝打包**。
FORBIDDEN_SUBSTRINGS: tuple[str, ...] = (
    "scorer/", "runs_in/", "gold/", "memory_probe_answers/", "reference/oracle",
)
#: `reference/` 下唯一放行的白名单 = 物料清单里明列的冻结件。
REFERENCE_ALLOWLIST: tuple[str, ...] = tuple(
    a for a in PM.PUBLIC_FROZEN_ARTIFACTS if a.startswith("reference/"))

#: **构建戳文件**：内容里带构建时刻或绝对路径，两次构建必然不同。
#: 它们**不参与**形态 A↔B 的逐字节比对 —— 但仍在 `SHA256SUMS` 里（包体完整性要它们）。
#: 每一条都写清"为什么它不可能相同"，不写理由的不许进这张表。
BUILD_STAMPED: dict[str, str] = {
    "*/build_info.json": "含 built_at（构建时刻）与 code_head（构建时的 git HEAD）",
    "provider/manifest.json": "含 built_at/finished_at 与 source 的绝对路径（随 GENEBENCH_ROOT 变）",
    "provider/MANIFEST.sha256": "逐文件表里含 manifest.json 的 sha256，随它一起变",
}

#: **随包副本**：内容取自**仓库工作树**、不是数据面的产物（`docs/` 与 `selfbuild/`）。
#: 形态 B 的 `--compare` 是「拿你重建出来的树与包里的 SHA256SUMS 逐文件比」，而这两堆在
#: 重建侧取的是**当前仓库**里的同名文件 —— 仓库里的文档改一个字，比对就多一条 `differ`，
#: 而重建出来的**数据**一个字节都没变。
#: 实测（红队 2026-09-07）：包是 09-06 打的，数据卡 09-07 14:40 改过，于是形态 B 的
#: compare 段整段变红（`differ 1`、退出码 1），外部用户按手册做到第 4 步必然失败 ——
#: 而那一跑的 28,645 个数据文件全部逐字节相同。**判据被一份 markdown 拖红**。
#: 处置与 `BUILD_STAMPED` 同构：**仍在 `SHA256SUMS` 里**（包体完整性要它们；
#: `sha256sum -c` 校的是**包内副本**，与仓库当前状态无关），但 A↔B 比对时
#: **以包内副本为准**、单列一堆报出来，不判红。
#: **数据面不适用这条** —— 数据面差一个字节就是红，那才是这份校验和承诺的东西。
PACKAGE_PROVIDED: dict[str, str] = {
    "docs/*": "随包发的文档副本（许可/数据卡/建设记录），源在仓库工作树 —— 改文档不改数据",
    "selfbuild/*": "形态 B 脚本的随包副本，源在仓库工作树 —— 脚本改版不改已发布的那份数据",
}


class PackageError(RuntimeError):
    pass


class Entry(NamedTuple):
    arcname: str        # 包内路径
    src: pathlib.Path   # 源文件
    size: int
    sha256: str

    @property
    def deterministic(self) -> bool:
        return not any(fnmatch.fnmatch(self.arcname, pat) for pat in BUILD_STAMPED)

    @property
    def package_provided(self) -> bool:
        """随包副本（`docs/` / `selfbuild/`）：A↔B 比对以包内副本为准，不判红。"""
        return any(fnmatch.fnmatch(self.arcname, pat) for pat in PACKAGE_PROVIDED)


# ------------------------------------------------------------------ 许可状态

def read_license_state(repo: "pathlib.Path | None" = None) -> str:
    """读 `DATA_LICENSE` 顶部的状态。**解析口径与 `ops/test_env.py` 一字不差**。"""
    repo = pathlib.Path(repo) if repo is not None else pathlib.Path(__file__).resolve().parents[2]
    f = repo / "DATA_LICENSE"
    if not f.is_file():
        raise PackageError(f"缺 {f} —— 没有许可声明就不许打包")
    txt = f.read_text(encoding="utf-8")
    hits = [s for s in LICENSE_STATES if f"`{s}`" in txt or f"**状态：`{s}`**" in txt]
    if not hits:
        raise PackageError(f"{f} 里读不出状态（应为 {LICENSE_STATES} 之一）")
    return hits[0]


def release_root(gb_root: "pathlib.Path | None" = None) -> pathlib.Path:
    return (pathlib.Path(gb_root) if gb_root is not None else cfg.GENEBENCH_ROOT) / "release"


def published_dir(gb_root=None) -> pathlib.Path:
    """**可发布**落点。许可 granted 之前这里必须是空的。"""
    return release_root(gb_root) / cfg.PUBLIC_VERSION


def staging_dir(gb_root=None) -> pathlib.Path:
    """**备好但不发**的落点（许可 pending 期间）。"""
    return release_root(gb_root) / "_staging_unpublished" / cfg.PUBLIC_VERSION


def dest_for(state: str, gb_root=None) -> pathlib.Path:
    return published_dir(gb_root) if state == "granted" else staging_dir(gb_root)


ARCHIVE_SUFFIXES: tuple[str, ...] = (".tar", ".gz", ".tgz", ".zip")


def assert_nothing_published_while_pending(gb_root=None, repo=None) -> None:
    """把 `test_env` 那条锁的射程补到 `$GB/release/` 上。

    `test_env` 扫的是 `$GB/snapshots/public`；包实际落在 `$GB/release/`。
    锁的**意思**是「许可原文没入库就不许存在打好待发的包」——
    意思不随目录名改变，所以这里按同样的判据再判一次可发布路径。
    """
    if read_license_state(repo) != "pending_license_text":
        return
    pub = published_dir(gb_root)
    if not pub.is_dir():
        return
    bad = sorted(str(p.relative_to(pub)) for p in pub.rglob("*")
                 if p.is_file() and p.suffix in ARCHIVE_SUFFIXES)
    if bad:
        raise PackageError(
            f"许可原文还没入库，可发布路径 {pub} 下却已经有包：{bad[:5]}。"
            f"发布形态可以准备，发布本身要等原文 —— 包应落 {staging_dir(gb_root)}")


# ------------------------------------------------------------------ 物料

def _sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_head(repo: pathlib.Path) -> str:
    try:
        out = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=30)
        return out.stdout.strip() or "unknown"
    except Exception:                                       # pragma: no cover
        return "unknown"


def _walk(root: pathlib.Path, prefix: str) -> Iterable[tuple[str, pathlib.Path]]:
    for p in sorted(root.rglob("*")):
        if p.is_file():
            yield f"{prefix}/{p.relative_to(root).as_posix()}", p


def components(gb_root=None, repo=None) -> list[dict[str, Any]]:
    """包的**内容清单**（一处定义，MANIFEST 与打包共用同一份）。

    `build/`（中间产物 quotes.parquet，409MB）与 `state/`（断点标记）**不进包** ——
    它们不是交付面，带上只会让下载的人以为那是数据的一部分。
    """
    gb = pathlib.Path(gb_root) if gb_root is not None else cfg.GENEBENCH_ROOT
    repo = pathlib.Path(repo) if repo is not None else pathlib.Path(__file__).resolve().parents[2]
    pub = gb / "snapshots" / cfg.PUBLIC_VERSION
    return [
        {"prefix": "provider", "src": pub / "qlib_provider", "kind": "dir", "required": True,
         "what": "冻结 qlib bin provider（8 字段 × v1 并集），含 files.sha256"},
        {"prefix": "tradability", "src": pub / "tradability", "kind": "dir", "required": True,
         "what": "可交易性视图，按年分区（网关 /bars 的行域）"},
        {"prefix": "tables", "src": pub / "tables", "kind": "dir", "required": True,
         "what": "网关后端读的六张表（daily/adj_factor/stk_limit/suspend_d/trade_cal/stock_basic）"},
        # **宇宙这一层有两样东西，别混成一句**（2026-09-12 裁定 ①）：
        # `v1_union.txt` 是**取数名单** —— 决定 `provider/features/` 里有哪些票的 bin，
        #   3,575 只 = v1 三宇宙并集，与 features/ 一一对应，形态 B 照它取数才能重建出同一棵树；
        # `universe_pit.parquet` 等三件是**宇宙定义面** —— 哪天哪只票在哪个指数里，
        #   由卡 A 从 baostock 成分接口（query_hs300_stocks / query_zz500_stocks）重建，
        #   不含任何 tushare / 私有 universe_pit 派生行，**不含 csi1000**。
        # 两者都在 `universe/` 下，`what` 里逐件说清是哪一种 —— 混在一起会让人
        # 把「包里有 3,575 只的行情」读成「包里有 3,575 只的宇宙定义」。
        {"prefix": "universe", "src": pub / "universe", "kind": "pairs", "required": True,
         "pairs": [("v1_union.txt", gb / "scratch" / "v1_union.txt"),
                   ("universe_pit.parquet", pub / "universe" / "universe_pit.parquet"),
                   ("build_info.json", pub / "universe" / "build_info.json"),
                   ("MANIFEST.sha256", pub / "universe" / "MANIFEST.sha256")],
         "what": "宇宙定义面（`universe_pit.parquet`：baostock 成分接口重建的 PIT 名单，"
                 "csi300 / csi500，无 tushare 派生行、无 csi1000）"
                 "＋ 取数名单（`v1_union.txt`：3,575 只，形态 B 的取数输入，与 features/ 对应）"},
        {"prefix": "frozen", "src": repo, "kind": "listed", "required": False,
         "items": list(PM.PUBLIC_FROZEN_ARTIFACTS),
         "what": "PUBLIC_FROZEN_ARTIFACTS（N-58⑥）：gold 的定义面，τ 标定于此实现对"},
        {"prefix": "docs", "src": repo, "kind": "listed", "required": True,
         "items": ["DATA_LICENSE", "ops/data_cards/public_channel.md",
                   "ops/reports/public/data_channel_notes.md",
                   "ops/reports/public/qlib_provider_public.md"],
         "what": "许可与来源声明、数据卡、公开通道建设记录"},
        {"prefix": "selfbuild", "src": repo, "kind": "listed", "required": True,
         "items": ["ops/release/build_public_provider.sh",
                   "ops/release/fetch_public_quotes.py",
                   "ops/release/universe_from_instruments.py",
                   "ops/release/rebuild_public_provider.py",
                   "ops/release/pack_public_provider.py"],
         "what": "形态 B（用户自建）的脚本 —— 不下载本包也能重建出同一份数据"},
    ]


def collect(gb_root=None, repo=None) -> tuple[list[Entry], list[str]]:
    """把物料清单摊平成逐文件条目。返回 `(entries, missing)`。

    **缺件不静默**：`required=False` 的缺件记进 `missing` 并写进 MANIFEST，
    不是当它不存在。静默丢的表现是「包里少了 gold 的定义面，而没人知道」。
    """
    entries: list[Entry] = []
    missing: list[str] = []
    for comp in components(gb_root, repo):
        src = pathlib.Path(comp["src"])
        if comp["kind"] == "dir":
            if not src.is_dir():
                if comp["required"]:
                    raise PackageError(f"缺必需目录 {src}（组件 {comp['prefix']}）")
                missing.append(comp["prefix"])
                continue
            pairs = list(_walk(src, comp["prefix"]))
        elif comp["kind"] == "file":
            if not src.is_file():
                if comp["required"]:
                    raise PackageError(f"缺必需文件 {src}（组件 {comp['prefix']}）")
                missing.append(comp["prefix"])
                continue
            pairs = [(f"{comp['prefix']}/{src.name}", src)]
        elif comp["kind"] == "pairs":
            # **显式 (包内名, 源文件) 对**：同一个前缀下的文件来自不同目录时用它。
            # 缺件判据与 listed 一致 —— required 的缺件直接抛，不静默丢。
            pairs = []
            for arcname, p in comp["pairs"]:
                p = pathlib.Path(p)
                if not p.is_file():
                    if comp["required"]:
                        raise PackageError(f"缺必需文件 {p}（组件 {comp['prefix']}/{arcname}）")
                    missing.append(f"{comp['prefix']}/{arcname}")
                    continue
                pairs.append((f"{comp['prefix']}/{arcname}", p))
        else:                                               # listed
            pairs = []
            for rel in comp["items"]:
                p = src / rel
                if not p.is_file():
                    if comp["required"]:
                        raise PackageError(f"缺必需文件 {p}（组件 {comp['prefix']}）")
                    missing.append(f"{comp['prefix']}/{rel}")
                    continue
                pairs.append((f"{comp['prefix']}/{rel}", p))
        for arc, p in pairs:
            entries.append(Entry(arc, p, p.stat().st_size, _sha256(p)))
    entries.sort(key=lambda e: e.arcname)
    assert_no_answer_plane(entries)
    return entries, missing


def assert_no_answer_plane(entries: Iterable[Entry]) -> None:
    """红线 2 的**打包侧守门**。命中就抛，不打包。"""
    bad: list[str] = []
    for e in entries:
        rel = e.arcname.split("/", 1)[1] if "/" in e.arcname else e.arcname
        for s in FORBIDDEN_SUBSTRINGS:
            if s in e.arcname or e.arcname.endswith(s.rstrip("/")):
                bad.append(f"{e.arcname}（命中 {s}）")
        if rel.startswith("reference/") and rel not in REFERENCE_ALLOWLIST:
            bad.append(f"{e.arcname}（reference/ 白名单外）")
    if bad:
        raise PackageError("包里出现答案面内容，拒绝打包：" + "；".join(sorted(set(bad))[:10]))


# ------------------------------------------------------------------ 三件产物

def sums_text(entries: Iterable[Entry], extra: "dict[str, str] | None" = None) -> str:
    """`sha256sum -c` 能直接吃的格式：`<hex>  <相对路径>`，按路径排序。"""
    rows = {e.arcname: e.sha256 for e in entries}
    rows.update(extra or {})
    return "".join(f"{rows[k]}  {k}\n" for k in sorted(rows))


def parse_sums(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        hexd, _, name = line.partition("  ")
        if not name:
            raise PackageError(f"SHA256SUMS 行认不出：{line!r}")
        out[name] = hexd
    return out


def build_manifest(entries: list[Entry], missing: list[str], *, state: str,
                   gb_root, repo, dest: pathlib.Path,
                   built_at: "str | None" = None) -> dict[str, Any]:
    """**包里不写落点**：`dest` 只用来判许可，不进 MANIFEST。

    写进去的表现是：同一棵树打到两个目录，`tar.gz` 差 97 个字节 ——
    而我们对外承诺的正是「你自己打一遍能得到同一个包」。落点记在
    `pack_result.json`（留在打包机器上，不进包）。
    """
    repo = pathlib.Path(repo)
    comps = []
    for comp in components(gb_root, repo):
        pre = comp["prefix"]
        mine = [e for e in entries if e.arcname.split("/", 1)[0] == pre]
        comps.append({"prefix": pre, "what": comp["what"], "files": len(mine),
                      "bytes": sum(e.size for e in mine),
                      "source": str(comp["src"])})
    det = [e for e in entries if e.deterministic]
    return {
        "package": PACKAGE_NAME,
        "channel": "public",
        "public_version": cfg.PUBLIC_VERSION,
        "card": "1.4（形态 A：冻结 provider 下载包）",
        "built_at": built_at or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "code_head": _git_head(repo),
        "freeze_line": cfg.FREEZE_DATE,
        "data_source": {
            "provider": "baostock（public-api.baostock.com:10030），运营方 阿尔法联合（上海）软件技术有限公司",
            "client": "PyPI baostock==0.9.3（BSD —— 那是库的许可，不是数据的）",
            "apis": ["query_history_k_data_plus(adjustflag=3)", "query_adjust_factor",
                     "query_stock_basic"],
            "window": {"start": "20090105", "end": cfg.FREEZE_DATE.replace("-", "")},
            "coverage_note": "baostock 不服务北交所；公开 all 宇宙 = v1 三宇宙并集 3,575 只（N-68/N-70）",
            # 2026-09-12 裁定 ①：换面之后这段旧文本已经不真，定点改写（卡 A 交接第 2 条）。
            "universe_definition_note": (
                "宇宙定义面由 baostock 成分接口重建（query_hs300_stocks / query_zz500_stocks），"
                "在 §2 授权射程内，不含任何 tushare / 私有 universe_pit 派生行；"
                "**csi1000 不入本包**（baostock 0.9.3 没有该指数的成分接口）。"
                "包里另有一份 `universe/v1_union.txt`（3,575 只）：那是**取数名单**不是宇宙定义 —— "
                "`provider/features/` 保留了只在 csi1000 里的 1,658 只票的 bin，"
                "所以 `instruments/all.txt`（1,917 行）与 features/（3,575 只）**本来就对不上**，"
                "理由见 ops/reports/public/instruments_switch.md §3"),
        },
        "license": {
            "state": state,
            "text_in_repo": state == "granted",
            "published": False,
            "publishable": state == "granted",
            "where_to_replace": "DATA_LICENSE 的「## 2. 许可原文」一节 —— 合同原文到位后只改这一处",
            "note": "「口头已取得」与「有原文可查」是两回事；后来的人只能读到后者",
        },
        "contents": comps,
        "missing_declared_artifacts": missing,
        "files": len(entries),
        "bytes": sum(e.size for e in entries),
        "deterministic_files": len(det),
        "deterministic_bytes": sum(e.size for e in det),
        "build_stamped": {k: v for k, v in BUILD_STAMPED.items()},
        "package_provided": {k: v for k, v in PACKAGE_PROVIDED.items()},
        "sha256": {e.arcname: e.sha256 for e in entries},
        "gzip_level": GZIP_LEVEL,
        "verify": [
            f"tar xzf {TARBALL}",
            f"cd {PACKAGE_NAME} && sha256sum -c {SUMS_NAME}",
        ],
    }


README_TEMPLATE = """# GeneBench 公开数据通道 {version}

**冻结线 {freeze}** · 数据源 baostock · 许可状态 `{state}` · **published: false**

## 校验

    tar xzf {tarball}
    cd {pkg} && sha256sum -c {sums}

`MANIFEST.json` 里有逐文件 sha256、构建 HEAD、数据源声明与许可状态。

## 目录

| 目录 | 是什么 |
| --- | --- |
{table}

## 不下载本包，自己建一份（形态 B）

**先要一份完整仓库** —— `selfbuild/` 里那五个脚本 import 的是仓库里的
`genebench_config` / `snapshots.public` / `ops.build_public_channel`，
单独拿出来跑不起来。`selfbuild/` 是仓库里同名文件的副本，
拿 `{sums}` 对一下就知道它们没被改过。

> **仓库地址**（2026-09-11 裁定 ㉑）：本体 https://github.com/Decilix-Intelligence/GeneBench.git，
> 协议工件单独一棵 https://github.com/Decilix-Intelligence/GeneQuant.git。
> **拿不到仓库也不影响你用这个包**：`provider/`、`tables/`、`tradability/`、`universe/`
> 都是数据，形态 A 自足。

    git clone https://github.com/Decilix-Intelligence/GeneBench.git  &&  cd GeneBench
    pip install baostock==0.9.3 pandas pyarrow numpy duckdb
    ops/release/build_public_provider.sh --root <你的数据根> --package <本包解开后的目录>

它做四件事：装 `baostock==0.9.3` → **非交易时段**按并集名单分批拉取 →
走 `ops/build_public_channel.py` 生成 provider → 与本包的 `{sums}` 逐文件比对。
比对通过 = 你不用信我们的包，你自己那份和它字节相同。

**取数要挂一夜**：3,575 只 × 约 7.4 秒 ≈ **7.4 小时**，加上复权因子约 27 分钟。
交易时段（北京时间工作日 09:00–15:30）脚本**拒绝启动**。断了直接重跑，会续。
建集部分在 12 核机器上约 **6.5 分钟**。

## 想打出字节相同的包（而不只是相同的数据）

包里唯一带构建时刻的是 `MANIFEST.json` 的 `built_at`。要复现**包体** sha256，
打包时给同一个时刻：

    ops/release/pack_public_provider.py --built-at {built_at}

不给也没关系 —— **数据**的逐文件校验和不依赖它。

`{sums}` 里有两类文件**不参与** A↔B 的逐字节比对（`sha256sum -c` 照旧校它们 ——
那校的是包内副本）：

* `MANIFEST.json` 的 `build_stamped` 那三条模式：带构建时刻/绝对路径，两次构建必然不同；
* `MANIFEST.json` 的 `package_provided` 那两条模式（`docs/`、`selfbuild/`）：
  **随包副本**，源在仓库工作树。仓库里的文档或脚本改过之后，比对**以包内副本为准**
  并单列一堆报出来 —— 改一份文档不该把「数据是否重建得出来」这个判据拖红。

**其余（全部数据面）必须逐字节相同**，差一个字节就是红。

## 许可

见 `docs/DATA_LICENSE`。状态是 `pending_license_text` 时**本包不对外发布**。
"""


def render_readme(manifest: dict[str, Any]) -> str:
    table = "\n".join(f"| `{c['prefix']}/` | {c['what']} |" for c in manifest["contents"])
    return README_TEMPLATE.format(version=manifest["public_version"],
                                  freeze=manifest["freeze_line"],
                                  state=manifest["license"]["state"],
                                  built_at=manifest["built_at"],
                                  tarball=TARBALL, pkg=PACKAGE_NAME, sums=SUMS_NAME,
                                  table=table)


def _tarinfo(name: str, size: int) -> tarfile.TarInfo:
    ti = tarfile.TarInfo(name)
    ti.size = size
    ti.mtime = 0
    ti.mode = 0o644
    ti.uid = ti.gid = 0
    ti.uname = ti.gname = ""
    ti.type = tarfile.REGTYPE
    return ti


def write_tar(dest_tar: pathlib.Path, entries: list[Entry],
              inline: list[tuple[str, bytes]], *, verbose: bool = False,
              root_name: "str | None" = None) -> None:
    """**确定性** tar.gz：条目排序、时间戳归零、属主归零、gzip 头 mtime=0。

    `root_name` 是包内顶层目录名，默认本包的 `PACKAGE_NAME`；
    `ops/release/pack_gold_subset.py` 复用本函数时给它自己的包名 ——
    确定性 tar 的口径只该有一处实现，抄第二份迟早分叉。
    """
    root_name = root_name or PACKAGE_NAME
    items: list[tuple[str, Any]] = [(e.arcname, e) for e in entries]
    items += [(name, data) for name, data in inline]
    items.sort(key=lambda x: x[0])
    tmp = dest_tar.with_suffix(dest_tar.suffix + ".part")
    n = 0
    with open(tmp, "wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw,
                           compresslevel=GZIP_LEVEL, mtime=0) as gz:
            with tarfile.open(fileobj=gz, mode="w", format=tarfile.GNU_FORMAT) as tar:
                for name, obj in items:
                    arc = f"{root_name}/{name}"
                    if isinstance(obj, bytes):
                        tar.addfile(_tarinfo(arc, len(obj)), io.BytesIO(obj))
                    else:
                        with open(obj.src, "rb") as fh:
                            tar.addfile(_tarinfo(arc, obj.size), fh)
                    n += 1
                    if verbose and n % 5000 == 0:
                        print(f"  ... {n}/{len(items)} 个条目", flush=True)
    os.replace(tmp, dest_tar)
    try:
        dest_tar.chmod(0o600)
    except OSError:                                         # pragma: no cover
        pass


def _harden(p: pathlib.Path) -> None:
    try:
        p.chmod(0o600)
    except OSError:                                         # pragma: no cover
        pass


def pack(*, gb_root=None, repo=None, dest: "pathlib.Path | None" = None,
         tar: bool = True, verbose: bool = True,
         built_at: "str | None" = None) -> dict[str, Any]:
    repo = pathlib.Path(repo) if repo is not None else pathlib.Path(__file__).resolve().parents[2]
    state = read_license_state(repo)
    assert_nothing_published_while_pending(gb_root, repo)
    dest = pathlib.Path(dest) if dest is not None else dest_for(state, gb_root)
    if state != "granted" and dest.resolve() == published_dir(gb_root).resolve():
        raise PackageError(
            f"许可状态是 {state}，拒绝往可发布路径 {dest} 写 —— 用 {staging_dir(gb_root)}")
    t0 = time.time()
    cfg.create_dir(dest)
    entries, missing = collect(gb_root, repo)
    t_collect = time.time() - t0
    if verbose:
        print(f"物料：{len(entries)} 个文件 / {sum(e.size for e in entries)/1e9:.3f} GB"
              f"（逐文件 sha256 用时 {t_collect:.1f} 秒）")
        if missing:
            print(f"[黄] 清单里声明了但不存在：{missing}")

    man = build_manifest(entries, missing, state=state, gb_root=gb_root, repo=repo,
                         dest=dest, built_at=built_at)
    man_bytes = (json.dumps(man, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    readme_bytes = render_readme(man).encode("utf-8")
    sums = sums_text(entries, extra={
        MANIFEST_NAME: hashlib.sha256(man_bytes).hexdigest(),
        README_NAME: hashlib.sha256(readme_bytes).hexdigest(),
    })
    inline = [(MANIFEST_NAME, man_bytes), (README_NAME, readme_bytes),
              (SUMS_NAME, sums.encode("utf-8"))]

    for name, data in inline:
        p = dest / name
        p.write_bytes(data)
        _harden(p)

    out: dict[str, Any] = {"dest": str(dest), "state": state, "files": len(entries),
                           "bytes": sum(e.size for e in entries), "missing": missing,
                           "seconds_hash": round(t_collect, 1)}
    if tar:
        t1 = time.time()
        dest_tar = dest / TARBALL
        if verbose:
            print(f"打包 → {dest_tar}（gzip -{GZIP_LEVEL}，确定性 tar）", flush=True)
        write_tar(dest_tar, entries, inline, verbose=verbose)
        out["seconds_tar"] = round(time.time() - t1, 1)
        out["tarball"] = str(dest_tar)
        out["tarball_bytes"] = dest_tar.stat().st_size
        t2 = time.time()
        out["tarball_sha256"] = _sha256(dest_tar)
        out["seconds_tar_sha256"] = round(time.time() - t2, 1)
        if verbose:
            print(f"包体 {out['tarball_bytes']/1e9:.3f} GB，{out['seconds_tar']:.1f} 秒，"
                  f"sha256 {out['tarball_sha256']}")
    out["seconds_total"] = round(time.time() - t0, 1)
    if tar:
        out["attachments_recorded"] = str(record_attachment(repo, {
            "name": TARBALL, "role": "public_provider",
            "what": "公开通道冻结 provider 包（形态 A）",
            "bytes": out["tarball_bytes"], "sha256": out["tarball_sha256"],
            "files_inside": out["files"], "bytes_inside": out["bytes"],
            "built_at": man["built_at"], "code_head": man["code_head"],
            "axes": _axes_for_attachment(repo), "download_url": "",
        }))
    (dest / "pack_result.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    _harden(dest / "pack_result.json")
    return out



# ------------------------------------------------------------------ 发布附件登记表

#: **发布附件登记表**（仓库内，`ops/mk_release_manifest.py` 的唯一出处）。
#: 两个附件落在 `$GB/release/<public>/` —— 那是机器本地路径，仓库里看不到。
#: 清单要逐件记附件的 `sha256`，就得有一份**在仓库里、可复现、能被测试喂假数据**
#: 的出处。口径照 `ops/reports/i_rehearsal_v2/package_inventory.json`：
#: 生成件落进仓库，清单生成器只读它、不自己去扫盘。
ATTACHMENTS_JSON: str = "ops/release/attachments.json"


def record_attachment(repo: pathlib.Path, entry: dict[str, Any]) -> pathlib.Path:
    """幂等地把一个发布附件登记进 :data:`ATTACHMENTS_JSON`。

    按 `name` 覆盖同名条目、按 `name` 排序落盘 —— 同一个包打两次，表的内容相同。
    `download_url` **留空**由上传那一步回填（卡 D）：空串与「没填」是同一件事，
    写一个假地址才是问题。
    """
    p = pathlib.Path(repo) / ATTACHMENTS_JSON
    doc: dict[str, Any] = {"generated_by": "ops/release/pack_*.py",
                           "what": "GitHub Release 的附件逐件登记（文件名 / 字节数 / sha256 / "
                                   "构建 HEAD / 四条版本轴 / 下载地址）",
                           "note": "download_url 由上传那一步回填；空串 = 还没上传。"
                                   "本表由打包脚本写，手改会被下一次打包覆盖。",
                           "attachments": []}
    if p.is_file():
        try:
            old = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(old, dict) and isinstance(old.get("attachments"), list):
                doc = old
                doc.setdefault("attachments", [])
        except json.JSONDecodeError:                        # pragma: no cover
            pass
    keep = [a for a in doc["attachments"] if a.get("name") != entry.get("name")]
    prev = next((a for a in doc["attachments"] if a.get("name") == entry.get("name")), {})
    #: 已经回填过的下载地址**不许被重新打包抹掉**。
    if prev.get("download_url") and not entry.get("download_url"):
        entry = dict(entry, download_url=prev["download_url"])
    doc["attachments"] = sorted(keep + [entry], key=lambda a: a.get("name", ""))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    _harden(p)
    return p


def _axes_for_attachment(repo: pathlib.Path) -> "dict[str, Any]":
    """四条版本轴**从冻结清单现读**（与 `ops/mk_release_manifest.py` 同源的三份文件）。

    读不出来就如实返回 `{"error": ...}` —— 编一个版本号比缺一个版本号坏得多。
    """
    try:
        from ops import freeze_v10 as F
        m = pathlib.Path(repo) / "ops" / "manifests"
        ts = json.loads((m / "v1.0-smoke.json").read_text(encoding="utf-8"))
        ps = json.loads((m / "v1.0-smoke-public.json").read_text(encoding="utf-8"))
        rf = json.loads((m / "v1.0-smoke.reference.json").read_text(encoding="utf-8"))
        return {"set_version": ts["set_version"], "set_root": ts.get("root"),
                "public_set_version": ps["set_version"], "public_set_root": ps.get("root"),
                "reference_version": rf["reference_version"],
                "reference_root": F.reference_root(rf),
                "protocol_version": "geneprotocol_v1@<逐 run 反算，见 VERSIONS.md §1.3>"}
    except Exception as exc:                                # pragma: no cover
        return {"error": f"{type(exc).__name__}: {exc}"}

# ------------------------------------------------------------------ 形态 B 的比对

def compare(sums_path: pathlib.Path, gb_root=None, repo=None) -> dict[str, Any]:
    """拿别处（形态 B）重建出来的树，与形态 A 的 `SHA256SUMS` 逐文件比。

    判据分四堆，**分开报**：`same` / `differ` / `build_stamped_differ` /
    `package_provided_differ`（外加 `only_in_*`）。后两堆都是**预期内**的差异，
    混进 `differ` 会淹没真问题 —— `differ` 里只该剩**数据面**的真差异。

    **只有内容漂移走那两堆**：某个文件只在一边（`only_in_*`）照旧判红 ——
    那是包的**文件清单**变了（打包面的改动），不是「有人改了一份随包发的文档」。
    """
    expected = parse_sums(pathlib.Path(sums_path).read_text(encoding="utf-8"))
    entries, missing = collect(gb_root, repo)
    got = {e.arcname: e.sha256 for e in entries}
    det = {e.arcname: e.deterministic for e in entries}
    prov = {e.arcname: e.package_provided for e in entries}
    for meta in (MANIFEST_NAME, README_NAME, SUMS_NAME):
        expected.pop(meta, None)

    same, differ, stamped, provided, only_a, only_b = [], [], [], [], [], []
    for name in sorted(set(expected) | set(got)):
        if name not in got:
            only_a.append(name)
        elif name not in expected:
            only_b.append(name)
        elif expected[name] == got[name]:
            same.append(name)
        elif not det.get(name, True):
            stamped.append(name)
        elif prov.get(name, False):
            provided.append(name)
        else:
            differ.append(name)
    return {"same": len(same), "differ": differ, "build_stamped_differ": stamped,
            "package_provided_differ": provided,
            "only_in_package": only_a, "only_in_rebuild": only_b,
            "missing_declared": missing,
            "ok": not differ and not only_a and not only_b,
            "deterministic_total": sum(1 for n in got if det[n]),
            "package_provided_total": sum(1 for n in got if prov[n])}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="形态 A：打公开通道的冻结包")
    ap.add_argument("--root", default=None, help="GENEBENCH 根（默认 cfg.GENEBENCH_ROOT）")
    ap.add_argument("--repo", default=None, help="仓库根（默认本文件的上上级）")
    ap.add_argument("--dest", default=None, help="落点（默认按许可状态决定）")
    ap.add_argument("--no-tar", action="store_true", help="只出 SHA256SUMS/MANIFEST，不打 tar")
    ap.add_argument("--dry-run", action="store_true", help="只说要打什么、多大")
    ap.add_argument("--built-at", default=None, metavar="ISO8601",
                    help="**可复现构建**：写死 MANIFEST 的 built_at。"
                         "给同一棵树 + 同一个 --built-at，tar.gz 字节相同")
    ap.add_argument("--compare", default=None, metavar="SHA256SUMS",
                    help="形态 B：把当前树与这份校验和逐文件比对")
    a = ap.parse_args(argv)
    cfg.harden_umask()

    if a.compare:
        rep = compare(pathlib.Path(a.compare), a.root, a.repo)
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        if rep["ok"]:
            print(f"[绿] 逐文件相同 {rep['same']} 个（其中确定性文件 "
                  f"{rep['deterministic_total']} 个）；构建戳差异 "
                  f"{len(rep['build_stamped_differ'])} 个（预期内）；随包副本差异 "
                  f"{len(rep['package_provided_differ'])} 个"
                  f"（预期内：docs/ 与 selfbuild/ 取自仓库工作树，以包内副本为准）")
            for name in rep["package_provided_differ"]:
                print(f"      随包副本已改：{name}（不影响数据面判据）")
            return 0
        print(f"[红] 不一致：differ={len(rep['differ'])} "
              f"only_in_package={len(rep['only_in_package'])} "
              f"only_in_rebuild={len(rep['only_in_rebuild'])}"
              f"（另有随包副本差异 {len(rep['package_provided_differ'])} 个，不计入判红）",
              file=sys.stderr)
        return 1

    state = read_license_state(a.repo)
    dest = pathlib.Path(a.dest) if a.dest else dest_for(state, a.root)
    if a.dry_run:
        entries, missing = collect(a.root, a.repo)
        by = {}
        for e in entries:
            k = e.arcname.split("/", 1)[0]
            b = by.setdefault(k, [0, 0])
            b[0] += 1
            b[1] += e.size
        print(f"许可状态 {state} → 落点 {dest}")
        for k in sorted(by):
            print(f"  {k:<12} {by[k][0]:>6} 个文件  {by[k][1]/1e6:>9.1f} MB")
        print(f"  合计       {len(entries):>6} 个文件  "
              f"{sum(e.size for e in entries)/1e9:.3f} GB")
        if missing:
            print(f"  [黄] 声明了但不存在：{missing}")
        print("--dry-run：什么都没打")
        return 0

    out = pack(gb_root=a.root, repo=a.repo, dest=dest, tar=not a.no_tar, built_at=a.built_at)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
