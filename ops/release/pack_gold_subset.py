#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""**gold 子集包**：把 130 实例真正用到的那 41 件公开 gold 打成可下载的附件（裁定 ②）。

    $PY ops/release/pack_gold_subset.py --dry-run     # 只说要打什么、多大
    $PY ops/release/pack_gold_subset.py               # 打包 + SHA256SUMS + MANIFEST.json
    $PY ops/release/pack_gold_subset.py --built-at 2026-09-12T00:00:00+00:00   # 可复现构建

产出四件，落点与形态 A 同一个目录（`$GB/release/<public_version>/`）::

    genebench_public_gold_subset_v1.tar.gz   包体，**确定性 tar**（口径与形态 A 同源）
    gold_subset_SHA256SUMS                   逐文件 sha256，`sha256sum -c` 可直接校
    gold_subset_MANIFEST.json                内容清单 / 构建 HEAD / 四条版本轴 / 许可状态
    gold_subset_README.md                    怎么校、怎么用、它复现不了什么

**取哪一份 gold —— 这是本脚本唯一容易搞错的事**
子集取自 `$GB/snapshots/<public_version>/gold_factors_r2/`，**不是** `gold_factors/`。
`gold_factors/` 是**旧 instruments**（tushare 派生的成分表）的产物；2026-09-12 裁定 ①
把公开包的宇宙定义面换成 baostock 重建结果之后，卡 A 按新成分全量重算，落在旁路根
`gold_factors_r2/`，并出了逐件清单 `gold_subset_public.json`（41 件 rel/bytes/sha256）。
`ops/reports/i_rehearsal_v2/gold_subset.json` 里公开通道那 41 行的 sha256
**41/41 已经不成立** —— 照它打，用户按 README 的校验命令做一遍就是红。
所以本脚本：**清单从 `gold_factors_r2/gold_subset_public.json` 读，逐件现算 sha256 与它比，
对不上当场抛** —— 「打包时顺手重算一遍校验和」等于把这道门拆了。

**这是答案面（红线 2）——落点只许是发布目录，绝不许上执行面**
gold 是答案面。它作为**公开下载附件**发布是用户 2026-09-12 的明文裁定（②），
与红线 2 不冲突：红线 2 管的是「不进 f02、不进容器、不进 bundle」。本脚本因此
:func:`assert_dest_is_not_on_the_exec_plane` 硬挡了那几个路径前缀，且**不提供**
任何推送开关 —— 推 bundle 只走 `ops/push_bundle_to_f02.sh`，那条路不认识本包。

**确定性**：条目排序、`mtime=0`、`uid=gid=0`、权限归一、gzip 头 mtime=0
（直接复用 `pack_public_provider.write_tar`，口径只有一处实现）。包里唯一带构建时刻的
是 `MANIFEST.json` 的 `built_at`，所以整包的可复现口径是
「同一棵树 + 同一个 `--built-at` → tar.gz 逐字节相同」。
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import sys
import time
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import genebench_config as cfg                      # noqa: E402
from ops.release import pack_public_provider as PP  # noqa: E402

PACKAGE_NAME: str = "genebench_public_gold_subset_v1"
TARBALL: str = f"{PACKAGE_NAME}.tar.gz"
SUMS_NAME: str = "gold_subset_SHA256SUMS"
MANIFEST_NAME: str = "gold_subset_MANIFEST.json"
README_NAME: str = "gold_subset_README.md"

#: 包内顶层目录名（tar 里的第一层）。**段名是 `gold_factors` 不是 `gold`** ——
#: `ops/test_env.py::_gold_offenders` 的判据是「路径**段**等于 gold」，
#: 解开到 `$GB` 下的任何地方都不会把那条门误伤成红。
GOLD_PREFIX: str = "gold_factors"

#: 子集清单的默认出处（卡 A 的旁路根）。
SUBSET_ROOT_NAME: str = "gold_factors_r2"
SUBSET_LIST_NAME: str = "gold_subset_public.json"

#: 随包的文档副本。与形态 A 的 `docs/` 同义：源在仓库工作树，改文档不改数据。
DOCS: tuple[str, ...] = (
    "DATA_LICENSE",
    "ops/data_cards/gold_subset_v1.md",
    "ops/reports/public/instruments_switch.md",
)

#: **执行面前缀**：落点命中任何一条就拒绝（红线 2 的打包侧守门）。
EXEC_PLANE_PREFIXES: tuple[str, ...] = (
    "scratch/f02_bundle", "staging", "runs_in", "scratch/exec", "release/trees",
)


class GoldPackError(RuntimeError):
    pass


# ------------------------------------------------------------------ 落点

def dest_default(gb_root=None) -> pathlib.Path:
    """与形态 A 同一个目录 —— 两个附件放两处会让人只下到一个。"""
    return PP.dest_for(PP.read_license_state(), gb_root)


def assert_dest_is_not_on_the_exec_plane(dest: pathlib.Path, gb_root=None) -> None:
    """红线 2：答案面不上执行面。**落点判据，不是口头承诺**。"""
    gb = pathlib.Path(gb_root) if gb_root is not None else cfg.GENEBENCH_ROOT
    try:
        rel = pathlib.Path(dest).resolve().relative_to(pathlib.Path(gb).resolve()).as_posix()
    except ValueError:
        return                      # 根本不在 $GB 下，与执行面同步无关
    for pre in EXEC_PLANE_PREFIXES:
        if rel == pre or rel.startswith(pre + "/"):
            raise GoldPackError(
                f"拒绝往 {dest} 写 —— `{pre}` 会同步到执行面，而本包是答案面（红线 2）")


# ------------------------------------------------------------------ 物料

def read_subset_list(source_root: pathlib.Path) -> dict[str, Any]:
    p = source_root / SUBSET_LIST_NAME
    if not p.is_file():
        raise GoldPackError(
            f"缺子集清单 {p} —— 没有清单就不知道 130 实例用到的是哪 41 件，拒绝打包")
    d = json.loads(p.read_text(encoding="utf-8"))
    if not d.get("files"):
        raise GoldPackError(f"{p} 里没有 files —— 清单是空的")
    return d


def collect(source_root: pathlib.Path, repo: pathlib.Path) -> tuple[list[PP.Entry], dict[str, Any]]:
    """摊平成逐文件条目，**逐件现算 sha256 与清单比**，对不上当场抛。"""
    sub = read_subset_list(source_root)
    entries: list[PP.Entry] = []
    mismatched: list[str] = []
    for row in sub["files"]:
        p = source_root / row["rel"]
        if not p.is_file():
            raise GoldPackError(f"清单里有而盘上没有：{p}")
        got = PP._sha256(p)
        if got != row["sha256"]:
            mismatched.append(f"{row['rel']}：清单 {row['sha256'][:12]}… ≠ 现算 {got[:12]}…")
            continue
        entries.append(PP.Entry(f"{GOLD_PREFIX}/{row['rel']}", p, p.stat().st_size, got))
    if mismatched:
        raise GoldPackError(
            "子集清单与盘上的 gold 对不上，拒绝打包（发出去的分会与发出去的校验和不符）：\n  "
            + "\n  ".join(mismatched[:10]))
    for rel in DOCS:
        p = repo / rel
        if not p.is_file():
            raise GoldPackError(f"缺必需的随包文档 {p}")
        entries.append(PP.Entry(f"docs/{rel}", p, p.stat().st_size, PP._sha256(p)))
    entries.sort(key=lambda e: e.arcname)
    return entries, sub


# ------------------------------------------------------------------ 四条版本轴

def axes(repo: pathlib.Path) -> dict[str, Any]:
    """四条轴**从冻结清单现读**，不从 RELEASE_MANIFEST 抄 —— 抄会多一次漂移的机会。"""
    from ops import freeze_v10 as F
    m = repo / "ops" / "manifests"
    ts = json.loads((m / "v1.0-smoke.json").read_text(encoding="utf-8"))
    ps = json.loads((m / "v1.0-smoke-public.json").read_text(encoding="utf-8"))
    rf = json.loads((m / "v1.0-smoke.reference.json").read_text(encoding="utf-8"))
    return {
        "set_version": ts["set_version"], "set_root": ts.get("root"),
        "public_set_version": ps["set_version"], "public_set_root": ps.get("root"),
        "reference_version": rf["reference_version"], "reference_root": F.reference_root(rf),
        "protocol_version": "geneprotocol_v1@<逐 run 反算，见 VERSIONS.md §1.3>",
        "comparable_iff": "四条轴全部相同",
    }


def build_manifest(entries: list[PP.Entry], sub: dict[str, Any], *, repo: pathlib.Path,
                   source_root: pathlib.Path, state: str,
                   built_at: "str | None" = None) -> dict[str, Any]:
    """**包里不写落点**（口径与形态 A 一致：写进去同一棵树打到两个目录字节就不同）。"""
    gold = [e for e in entries if e.arcname.startswith(GOLD_PREFIX + "/")]
    docs = [e for e in entries if e.arcname.startswith("docs/")]
    return {
        "package": PACKAGE_NAME,
        "channel": "public",
        "public_version": cfg.PUBLIC_VERSION,
        "card": "C（裁定 ②：gold 子集附件）",
        "built_at": built_at or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "code_head": PP._git_head(repo),
        "freeze_line": cfg.FREEZE_DATE,
        "axes": axes(repo),
        "what_is_in_here": (
            "130 个出集实例真正用到的公开 gold 因子子集 —— 逐件 parquet，"
            "两个宇宙（csi300 / csi500）。**不是全量 gold**（全量 16.0 GB，超发布线）"),
        "subset_rule": {
            "source_list": f"snapshots/{cfg.PUBLIC_VERSION}/{SUBSET_ROOT_NAME}/{SUBSET_LIST_NAME}",
            "n_factors": sub.get("n_files"),
            "computed_on_instruments": sub.get("computed_on_instruments"),
            "provider_files_sha256_digest": sub.get("provider_files_sha256_digest"),
            "supersedes": sub.get("supersedes"),
            "limitation": (
                "子集能复现夹具内容，**不能重新推导池子的选取** —— build_pool() 的合格判定"
                "要扫全族每一条（gtja_191 186 条 / worldquant_101 82 条 / qlib_alpha158 158 条）。"
                "要重新推导得有全量 gold，走手册 §1.4 (b) 的重建链"),
        },
        "computed_on": {
            "provider_root": sub.get("provider_files_sha256_digest"),
            "note": (
                "本子集算在**卡 A 换面之后**的公开 provider 上（宇宙定义面由 baostock 成分接口重建）。"
                "已发布的 18 个公开 run 与 calibration.json / crosscheck / ε 建在**旧** provider 上，"
                "两者不同源 —— 见 docs/ops/reports/public/instruments_switch.md 与 known_limits_v1.md"),
        },
        "license": {
            "state": state,
            "text_in_repo": state == "granted",
            "publishable": state == "granted",
            "note": "gold 是本基准算出来的派生量，随包的 DATA_LICENSE 说的是它的上游行情数据",
        },
        "contents": [
            {"prefix": f"{GOLD_PREFIX}/", "files": len(gold), "bytes": sum(e.size for e in gold),
             "what": f"公开 gold 子集（源 {source_root}）"},
            {"prefix": "docs/", "files": len(docs), "bytes": sum(e.size for e in docs),
             "what": "许可声明、子集数据卡、换面报告（随包副本，源在仓库工作树）"},
        ],
        "files": len(entries),
        "bytes": sum(e.size for e in entries),
        "sha256": {e.arcname: e.sha256 for e in entries},
        "gzip_level": PP.GZIP_LEVEL,
        "verify": [f"tar xzf {TARBALL}", f"cd {PACKAGE_NAME} && sha256sum -c {SUMS_NAME}"],
    }


README_TEMPLATE = """# GeneBench 公开 gold 子集 {version}

**冻结线 {freeze}** · 通道 public · 许可状态 `{state}` · **{n} 个文件 / {mb:.1f} MiB**

## 校验

    tar xzf {tarball}
    cd {pkg} && sha256sum -c {sums}

`{manifest}` 里有逐文件 sha256、构建 HEAD、四条版本轴、子集规则与许可状态。

## 这是什么

`{prefix}/` 下是 **130 个出集实例真正用到的那 {n_gold} 件 gold 因子面板**
（两个宇宙 csi300 / csi500，逐件 parquet）。**不是全量 gold** —— 全量 16.0 GB，
超过发布线（裁定 ⑯）。

## 它复现不了什么（**明写，不糊**）

* **推导不出池子的选取**：`build_pool()` 的合格判定要扫全族每一条
  （gtja_191 186 条 / worldquant_101 82 条 / qlib_alpha158 158 条）。
  子集只够复现夹具**内容**，要重新推导得有全量 gold，走手册 §1.4 (b) 的重建链。
* **与已发布的 18 个公开 run 不同源**：本子集算在 2026-09-12 换面**之后**的公开
  provider 上（宇宙定义面由 baostock 成分接口重建，`csi1000` 不在内）；
  那 18 个 run 与随包的 `calibration.json` / ε 阈值算在**换面之前**那一版名单上。
  详见 `docs/ops/reports/public/instruments_switch.md` 与仓库的
  `ops/reports/known_limits_v1.md`。

## 想打出字节相同的包

包里唯一带构建时刻的是 `{manifest}` 的 `built_at`。给同一个时刻就能复现包体 sha256：

    ops/release/pack_gold_subset.py --built-at {built_at}

## 许可

见 `docs/DATA_LICENSE`。gold 是本基准算出来的派生量，那份声明说的是它的上游行情数据。
"""


def render_readme(man: dict[str, Any]) -> str:
    gold = next(c for c in man["contents"] if c["prefix"] == f"{GOLD_PREFIX}/")
    return README_TEMPLATE.format(
        version=man["public_version"], freeze=man["freeze_line"],
        state=man["license"]["state"], n=man["files"], mb=man["bytes"] / (1 << 20),
        tarball=TARBALL, pkg=PACKAGE_NAME, sums=SUMS_NAME, manifest=MANIFEST_NAME,
        prefix=GOLD_PREFIX, n_gold=gold["files"], built_at=man["built_at"])


# ------------------------------------------------------------------ 打包

def pack(*, gb_root=None, repo=None, source_root=None, dest=None,
         tar: bool = True, verbose: bool = True,
         built_at: "str | None" = None) -> dict[str, Any]:
    repo = pathlib.Path(repo) if repo is not None else pathlib.Path(__file__).resolve().parents[2]
    gb = pathlib.Path(gb_root) if gb_root is not None else cfg.GENEBENCH_ROOT
    source_root = (pathlib.Path(source_root) if source_root is not None
                   else gb / "snapshots" / cfg.PUBLIC_VERSION / SUBSET_ROOT_NAME)
    state = PP.read_license_state(repo)
    dest = pathlib.Path(dest) if dest is not None else PP.dest_for(state, gb_root)
    if state != "granted" and dest.resolve() == PP.published_dir(gb_root).resolve():
        raise GoldPackError(f"许可状态是 {state}，拒绝往可发布路径 {dest} 写")
    assert_dest_is_not_on_the_exec_plane(dest, gb_root)

    t0 = time.time()
    cfg.create_dir(dest)
    entries, sub = collect(source_root, repo)
    t_collect = time.time() - t0
    if verbose:
        print(f"物料：{len(entries)} 个文件 / {sum(e.size for e in entries)/(1<<20):.1f} MiB"
              f"（逐文件 sha256 用时 {t_collect:.1f} 秒）")

    man = build_manifest(entries, sub, repo=repo, source_root=source_root,
                         state=state, built_at=built_at)
    man_bytes = (json.dumps(man, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    readme_bytes = render_readme(man).encode("utf-8")
    sums = PP.sums_text(entries, extra={
        MANIFEST_NAME: hashlib.sha256(man_bytes).hexdigest(),
        README_NAME: hashlib.sha256(readme_bytes).hexdigest(),
    })
    inline = [(MANIFEST_NAME, man_bytes), (README_NAME, readme_bytes),
              (SUMS_NAME, sums.encode("utf-8"))]
    for name, data in inline:
        p = dest / name
        p.write_bytes(data)
        PP._harden(p)

    out: dict[str, Any] = {"dest": str(dest), "state": state, "files": len(entries),
                           "bytes": sum(e.size for e in entries),
                           "source_root": str(source_root),
                           "seconds_hash": round(t_collect, 1)}
    if tar:
        t1 = time.time()
        dest_tar = dest / TARBALL
        if verbose:
            print(f"打包 → {dest_tar}（gzip -{PP.GZIP_LEVEL}，确定性 tar）", flush=True)
        PP.write_tar(dest_tar, entries, inline, verbose=verbose, root_name=PACKAGE_NAME)
        out["seconds_tar"] = round(time.time() - t1, 1)
        out["tarball"] = str(dest_tar)
        out["tarball_bytes"] = dest_tar.stat().st_size
        out["tarball_sha256"] = PP._sha256(dest_tar)
        if verbose:
            print(f"包体 {out['tarball_bytes']/(1<<20):.1f} MiB，{out['seconds_tar']:.1f} 秒，"
                  f"sha256 {out['tarball_sha256']}")
    out["seconds_total"] = round(time.time() - t0, 1)
    out["built_at"] = man["built_at"]
    out["code_head"] = man["code_head"]
    out["axes"] = man["axes"]
    if tar:
        out["attachments_recorded"] = str(PP.record_attachment(repo, {
            "name": TARBALL, "role": "public_gold_subset",
            "what": "130 实例用到的公开 gold 因子子集（裁定 ②）",
            "bytes": out["tarball_bytes"], "sha256": out["tarball_sha256"],
            "files_inside": out["files"], "bytes_inside": out["bytes"],
            "built_at": man["built_at"], "code_head": man["code_head"],
            "axes": man["axes"], "download_url": "",
        }))
    (dest / "gold_subset_pack_result.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    PP._harden(dest / "gold_subset_pack_result.json")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="裁定 ②：打公开 gold 子集附件")
    ap.add_argument("--root", default=None, help="GENEBENCH 根（默认 cfg.GENEBENCH_ROOT）")
    ap.add_argument("--repo", default=None, help="仓库根（默认本文件的上上级）")
    ap.add_argument("--source-root", default=None,
                    help=f"gold 子集的源根（默认 $GB/snapshots/<public>/{SUBSET_ROOT_NAME}）")
    ap.add_argument("--dest", default=None, help="落点（默认按许可状态决定，与形态 A 同目录）")
    ap.add_argument("--no-tar", action="store_true", help="只出校验和与清单，不打 tar")
    ap.add_argument("--dry-run", action="store_true", help="只说要打什么、多大")
    ap.add_argument("--built-at", default=None, metavar="ISO8601",
                    help="**可复现构建**：写死 MANIFEST 的 built_at。"
                         "同一棵树 + 同一个 --built-at → tar.gz 字节相同")
    a = ap.parse_args(argv)
    cfg.harden_umask()

    repo = pathlib.Path(a.repo) if a.repo else pathlib.Path(__file__).resolve().parents[2]
    gb = pathlib.Path(a.root) if a.root else cfg.GENEBENCH_ROOT
    source_root = (pathlib.Path(a.source_root) if a.source_root
                   else gb / "snapshots" / cfg.PUBLIC_VERSION / SUBSET_ROOT_NAME)
    if a.dry_run:
        entries, sub = collect(source_root, repo)
        by: dict[str, list[int]] = {}
        for e in entries:
            k = e.arcname.split("/", 1)[0]
            b = by.setdefault(k, [0, 0])
            b[0] += 1
            b[1] += e.size
        state = PP.read_license_state(repo)
        print(f"许可状态 {state} → 落点 {PP.dest_for(state, a.root)}")
        print(f"源根 {source_root}（清单 {SUBSET_LIST_NAME}，逐件 sha256 与清单**已核对一致**）")
        for k in sorted(by):
            print(f"  {k:<14} {by[k][0]:>4} 个文件  {by[k][1]/(1<<20):>8.1f} MiB")
        print(f"  合计         {len(entries):>4} 个文件  "
              f"{sum(e.size for e in entries)/(1<<20):.1f} MiB")
        print("--dry-run：什么都没打")
        return 0

    out = pack(gb_root=a.root, repo=a.repo, source_root=a.source_root, dest=a.dest,
               tar=not a.no_tar, built_at=a.built_at)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
