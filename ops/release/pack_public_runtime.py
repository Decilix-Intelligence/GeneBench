#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""**公开运行物料包**：把「跑得起来、算得出分」所缺的那两堆打成第三个发布附件。

    $PY ops/release/pack_public_runtime.py --dry-run    # 只说要打什么、多大
    $PY ops/release/pack_public_runtime.py             # 打包 + SHA256SUMS + MANIFEST.json + README
    $PY ops/release/pack_public_runtime.py --built-at 2026-09-13T00:00:00+00:00   # 可复现构建

**为什么会有这个包（2026-09-13 外部验收报出来的缺件 ②③）**
v1.0.16 发的两个附件是**数据面**（公开 provider、公开 gold 子集）；公开树是 `git archive`
出来的**仓库**。而这两堆东西**既不在仓库里，也不在那两个附件里**：

* `reference/tasks/public/v1.0-smoke-public/` —— 公开题集的**物化实例**。它是
  `ops/mk_instances.py` 按 `genetask/templates` 生成后落在 `$GENEBENCH_ROOT` 下的，
  按红线 6「大产物不进 git」天然在 `git archive HEAD` 的射程之外。
  后果有两层：① `ops/freeze_v10.py --check-all` 的**公开根算不出来** ——
  `build_channel_fixtures()` 在目录不存在时返回 `{}`，18 道题的夹具真值整段缺，
  现算根变成 `c5639e55…` 而清单记的是 `3e5ab441…`；② `ops/run_joblist.py --channel public`
  与 `ops/score_runs.py` 都以它为**题集根**，没有它连 s1-cor-01 都起不来。
* `snapshots/public_v1/calibration.json` 与 `snapshots/public_v1/epsilon/` —— τ / ε / IC 族
  的单一事实来源。`ops/score_runs.py` 自己写着「公开树请先按 README 把 Release 附件解到
  `snapshots/public_v1/`」，但**没有任何一个附件装着它**。

**上一轮单机演练为什么看不见这两件缺**：演练跑在 f02，而 f02 的 `/data/genebench_runner/`
下这两堆本来就有（题集是同步过去的、标定是边车读的），于是「照 README 走一遍」在那台机器上
一路绿灯 —— 缺件只有在**一台干净机器**上才会显形。

**这个包里有答案面，这是有意的（红线 2 按 v1.0.16 的容器边界口径）**
题集实例里带 `solution/`（每道题的参考解与 gold artifact）、`gold/`、`scorer.yaml`、
`tests_test_outputs.py`。`scorer/score_run.py:328` 把 `task_dir/work` 当 gold 目录、
`:291-292` 读 `task.yaml` 与 `taskspec.json` —— **不带这些就算不出分**，和 v1.0.16
公开树「带全部答案面」是同一条裁定（N-627 走 B，见公开树的 `EXCLUDED.txt`）。
红线 2 在本版的口径是**容器边界**：答案面永不挂进 agent 容器。因此本脚本
:func:`assert_dest_is_not_on_the_exec_plane` 把落点硬挡在会同步到执行面的路径之外，
并且**不提供**任何推送开关 —— 推 bundle 只走 `ops/push_bundle_to_f02.sh`，那条路不认识本包。

**两道打包时的硬门（不是口头承诺）**

1. :func:`assert_fixtures_match_frozen` —— 拿**要打进包的那棵树**现算一遍
   `freeze_v10.build_channel_fixtures()`，与 `ops/manifests/v1.0-smoke-public.json` 里
   已冻的 `channel_fixtures` **逐件比**，不等就当场抛。这道门挡的是
   「打了一个包，用户解开之后冻结根还是对不上」——那正是本卡要修的病，
   不能让修法本身重犯一次。
2. :func:`assert_calibration_intact` —— `calibration.json` 的现算 sha 必须等于随它一起
   落盘的 `calibration.sha256`；且包里**只许**出现公开通道那一份
   （`snapshots/public_v1/`），命中 `snapshots/v1/` 就抛。

**确定性**：复用 `pack_public_provider.write_tar`（条目排序、mtime=0、uid=gid=0、
权限归一、gzip 头 mtime=0）。包里唯一带构建时刻的是 `MANIFEST.json` 的 `built_at`，
所以口径是「同一棵树 + 同一个 `--built-at` → tar.gz 逐字节相同」。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import genebench_config as cfg                      # noqa: E402
from ops.release import pack_public_provider as PP  # noqa: E402
from ops.release.pack_gold_subset import (          # noqa: E402
    assert_dest_is_not_on_the_exec_plane, dest_default,
)

PACKAGE_NAME: str = "genebench_public_runtime_v1"
TARBALL: str = f"{PACKAGE_NAME}.tar.gz"
SUMS_NAME: str = "runtime_SHA256SUMS"
MANIFEST_NAME: str = "runtime_MANIFEST.json"
README_NAME: str = "runtime_README.md"

#: 公开题集的目录名**不在这里定义** —— 从 `ops/freeze_v10.PUBLIC_SET_ID` 取。
#: 在这里抄一份的表现是「打的是一批、冻的是另一批」，与 N-605 记的那个病同形。

#: 标定物料里随包发的那几件。`epsilon/` 整个目录随包 —— 评分**读的是**
#: `calibration.json.epsilon`（`scorer/l3.py:833`），`epsilon/` 是它的**产地与证据**
#: （三份实现 + 逐频率产物 + `MANIFEST.sha256` + `build_info.json`），
#: 不随包发的话「这条带是怎么来的」在外部就无从复核。
CALIB_FILES: tuple[str, ...] = ("calibration.json", "calibration.sha256")
CALIB_DIRS: tuple[str, ...] = ("epsilon",)

#: 包里**绝不许**出现的东西。命中就拒绝打包。
#: 注意这里**没有** `solution/` / `gold/` / `scorer.yaml` —— 那是有意带的（见模块文档）。
FORBIDDEN_SUBSTRINGS: tuple[str, ...] = (
    "tasks/private/", "snapshots/v1/", "memory_probe_answers/", "runs_in/",
)
FORBIDDEN_NAMES: tuple[str, ...] = (
    ".env", "secrets.env", "github.env", "id_ed25519", "id_rsa",
)
FORBIDDEN_SUFFIXES: tuple[str, ...] = (".pem", ".key")


class RuntimePackError(RuntimeError):
    pass


# ------------------------------------------------------------------ 物料

def tasks_source(gb_root=None) -> pathlib.Path:
    """公开题集实例的源目录。**从 `freeze_v10` 取**，不另抄一个字面量。"""
    from ops import freeze_v10 as F
    if gb_root is None:
        return F.public_answer_root()
    return (pathlib.Path(gb_root) / "reference" / "tasks" / "public" / F.PUBLIC_SET_ID)


def snapshot_source(gb_root=None) -> pathlib.Path:
    if gb_root is None:
        return cfg.snapshot_root("public")
    return pathlib.Path(gb_root) / "snapshots" / cfg.PUBLIC_VERSION


def collect(gb_root=None) -> list[PP.Entry]:
    """包内两棵子树。`arcname` 就是**它在 `$GENEBENCH_ROOT` 下的相对路径** ——
    所以落位是 `tar -xzf … --strip-components=1 -C "$GENEBENCH_ROOT"` 一条命令，
    不需要用户自己 `cp -a` 拼路径（拼错的表现是「解开了但还是缺」）。"""
    from ops import freeze_v10 as F
    ts, ss = tasks_source(gb_root), snapshot_source(gb_root)
    if not ts.is_dir():
        raise RuntimePackError(f"公开题集不在：{ts} —— 先 `ops/mk_instances.py` 物化公开通道")
    out: list[PP.Entry] = []
    prefix = f"reference/tasks/public/{F.PUBLIC_SET_ID}"
    for arc, p in PP._walk(ts, prefix):
        out.append(PP.Entry(arc, p, p.stat().st_size, PP._sha256(p)))
    sp = f"snapshots/{cfg.PUBLIC_VERSION}"
    for name in CALIB_FILES:
        p = ss / name
        if not p.is_file():
            raise RuntimePackError(f"标定物料不在：{p}")
        out.append(PP.Entry(f"{sp}/{name}", p, p.stat().st_size, PP._sha256(p)))
    for d in CALIB_DIRS:
        root = ss / d
        if not root.is_dir():
            raise RuntimePackError(f"标定目录不在：{root}")
        for arc, p in PP._walk(root, f"{sp}/{d}"):
            out.append(PP.Entry(arc, p, p.stat().st_size, PP._sha256(p)))
    out.sort(key=lambda e: e.arcname)
    return out


# ------------------------------------------------------------------ 两道硬门

def assert_no_forbidden(entries: list[PP.Entry]) -> None:
    bad: list[str] = []
    for e in entries:
        n = pathlib.PurePosixPath(e.arcname).name
        if any(s in e.arcname for s in FORBIDDEN_SUBSTRINGS):
            bad.append(e.arcname)
        elif n in FORBIDDEN_NAMES or n.startswith(".env") or any(
                n.endswith(s) for s in FORBIDDEN_SUFFIXES):
            bad.append(e.arcname)
    if bad:
        raise RuntimePackError("包里出现不许出现的内容，拒绝打包：" + "；".join(sorted(set(bad))[:10]))


def assert_fixtures_match_frozen(gb_root=None) -> dict[str, Any]:
    """**本包存在的理由就是这道门**：要打进包的这棵树，现算的 `channel_fixtures`
    必须逐件等于已冻公开清单里记的那份。不等 = 用户解开之后冻结根照样对不上。"""
    from ops import freeze_v10 as F
    man = json.loads(F.OUT_PUBLIC.read_text(encoding="utf-8"))
    rec = man.get("channel_fixtures") or {}
    cur = F.build_channel_fixtures(tasks_source(gb_root))
    if cur != rec:
        only_pkg = sorted(set(cur) - set(rec))
        only_man = sorted(set(rec) - set(cur))
        diff = sorted(k for k in set(cur) & set(rec) if cur[k] != rec[k])
        raise RuntimePackError(
            "要打的题集与已冻公开清单不符，拒绝打包 —— 打出去用户也对不上根。"
            f"\n  只在包里: {only_pkg}\n  只在清单: {only_man}\n  同题不同字节: {diff}"
            f"\n  清单: {F.OUT_PUBLIC}")
    return {"tasks": len(rec), "files": sum(len(v) for v in rec.values()),
            "public_root_recorded": man.get("root"),
            "set_version": man.get("set_version")}


def assert_calibration_intact(gb_root=None) -> dict[str, Any]:
    ss = snapshot_source(gb_root)
    got = PP._sha256(ss / "calibration.json")
    want = (ss / "calibration.sha256").read_text(encoding="utf-8").split()[0].strip()
    if got != want:
        raise RuntimePackError(
            f"calibration.json 的现算 sha {got[:16]}… ≠ 随它落盘的 calibration.sha256 "
            f"{want[:16]}… —— 标定物料自相矛盾，拒绝打包")
    d = json.loads((ss / "calibration.json").read_text(encoding="utf-8"))
    return {"sha256": got, "tau": d.get("tau", {}).get("value"),
            "card": d.get("card"), "freeze_date": d.get("freeze_date"),
            "ready_for_scoring": d.get("ready_for_scoring"),
            "outstanding": d.get("outstanding")}


# ------------------------------------------------------------------ 三件产物

def build_manifest(entries: list[PP.Entry], *, repo: pathlib.Path, gb_root=None,
                   fx: dict[str, Any], calib: dict[str, Any],
                   built_at: "str | None" = None) -> dict[str, Any]:
    from ops import freeze_v10 as F
    tasks = [e for e in entries if e.arcname.startswith("reference/")]
    snap = [e for e in entries if e.arcname.startswith("snapshots/")]
    return {
        "package": PACKAGE_NAME,
        "role": "public_runtime_material",
        "what": "公开题集实例 + 公开通道标定物料 —— 仓库与前两个附件都装不下的那两堆",
        "why": "2026-09-13 外部验收（干净 Mac）报出的缺件 ②③：公开冻结根算不出来、评分链路缺 calibration",
        "built_at": built_at or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "code_head": PP._git_head(repo),
        "public_set_id": F.PUBLIC_SET_ID,
        "contents": [
            {"prefix": f"reference/tasks/public/{F.PUBLIC_SET_ID}/",
             "files": len(tasks), "bytes": sum(e.size for e in tasks),
             "what": "公开题集的物化实例（题面 / arms / work 夹具 / solution / gold / scorer.yaml）",
             "answer_plane": True,
             "note": "带答案面是 v1.0.16 的裁定（N-627 走 B）。红线 2 在本版是容器边界口径："
                     "答案面永不挂进 agent 容器 —— 见公开树 EXCLUDED.txt 与 README §4 ①。"},
            {"prefix": f"snapshots/{cfg.PUBLIC_VERSION}/",
             "files": len(snap), "bytes": sum(e.size for e in snap),
             "what": "公开通道 calibration.json（τ/ε/IC 族的单一事实来源）+ epsilon/ 产物目录",
             "answer_plane": False,
             "note": "τ/ε 是**阈值**不是解。评分读的是 calibration.json.epsilon；"
                     "epsilon/ 随包是为了让外部能复核这条带的产地。"},
        ],
        "files": len(entries),
        "bytes": sum(e.size for e in entries),
        "fixtures_gate": fx,
        "calibration": calib,
        "axes": PP._axes_for_attachment(repo),
        "verify": f"tar -xzf {TARBALL} && (cd {PACKAGE_NAME} && sha256sum -c {SUMS_NAME})",
        "install": f"tar -xzf {TARBALL} --strip-components=1 -C \"$GENEBENCH_ROOT\"",
        "not_reproducible_here": [
            "τ/ε/IC 阈值算在**换面之前**的 gold 上（known_limits_v1.md「换面」一节）；"
            "重算排 v1.0.17，本包不重算、也不重冻。",
            "calibration.json 里的 provider/gold 路径是**发布方的绝对路径**"
            "（/data/shared/genebench/snapshots/public_v1/…）—— 评分不读它们，"
            "只有 ops/test_public_chain.py 的一条断言读，外部环境下那条会红。",
        ],
        "sha256": {e.arcname: e.sha256 for e in entries},
    }


README_TEMPLATE = """# GeneBench 公开运行物料 {version}

这是 v1.0.16 的**第三个** Release 附件。前两个是数据面（公开 provider、公开 gold 子集），
这一个装的是「跑得起来、算得出分」所必需、而**仓库与前两个附件都没有**的两堆：

| 包内前缀 | 件数 | 字节 | 是什么 |
| --- | ---: | ---: | --- |
| `reference/tasks/public/{set_id}/` | {n_tasks} | {b_tasks} | 公开题集的物化实例（题面 / arms / work 夹具 / solution / gold / scorer.yaml） |
| `snapshots/{pub}/` | {n_snap} | {b_snap} | 公开通道 `calibration.json`（τ/ε/IC 族）+ `epsilon/` 产物目录 |

## 落位（一条命令）

```sh
tar -xzf {tarball}                                   # ① 先整包解开，校一遍
(cd {pkg} && sha256sum -c {sums})
tar -xzf {tarball} --strip-components=1 -C "$GENEBENCH_ROOT"   # ② 再落位
```

`--strip-components=1` 把包内顶层目录剥掉，于是两棵子树正好落到
`$GENEBENCH_ROOT/reference/tasks/public/{set_id}/` 与 `$GENEBENCH_ROOT/snapshots/{pub}/`。

## 落位之后该绿的两件事

```sh
cd "$GENEBENCH_ROOT/repo"
python3 ops/freeze_v10.py --check-all        # 三条轴全绿；公开根 = {root}

# 评分链路能加载到标定。**不要**拿 `ops/score_runs.py --help` 当判据 ——
# argparse 在读任何文件之前就退了，它证明不了标定在不在。
GENEBENCH_CHANNEL=public python3 -c \
  "import genebench_config as c; from scorer import l3; \
   print('tau =', l3.load_calibration(c.calibration_path())['tau']['value'])"
```

公开根**必须**回到 `{root}`。对不上就先逐件比 `{sums}`：少一件、多一件、
或者换行/权限被改过，都会让 `channel_fixtures` 那一段变。**不要**用 `--write-public`
把它"改绿" —— 那是重冻，会让已发的通行证全部作废。

## 这个包里有答案面，这是有意的

题集实例带每道题的参考解（`solution/`）、gold 与评分口径（`scorer.yaml`）。
没有它们 `scorer/score_run.py` 算不出分（它把 `task_dir/work` 当 gold 目录）。
这与 v1.0.16 公开树「带全部答案面」是同一条裁定；红线 2 在本版的口径是**容器边界**：
答案面永不挂进 agent 容器。代价（题面与参考解在公网、有进训练语料的风险）
是设计性限制，记在 `ops/reports/known_limits_v1.md`。

## 它复现不了什么

- τ/ε/IC 阈值算在**换面之前**的 gold 上，与现包的 gold 子集不同源；贴近阈值的样本
  可能翻转判定。重算排 v1.0.17。
- `calibration.json` 里记着发布方的绝对路径（`provider.dir` 等）。评分**不读**它们，
  但 `ops/test_public_chain.py` 有一条断言读，外部环境下那条会红 —— 已登记。

构建：`{code_head}` / `{built_at}`。逐件 sha256 见 `{manifest}`。
"""


def render_readme(man: dict[str, Any]) -> str:
    from ops import freeze_v10 as F
    t, s = man["contents"][0], man["contents"][1]
    return README_TEMPLATE.format(
        version=cfg.PUBLIC_VERSION, set_id=F.PUBLIC_SET_ID, pub=cfg.PUBLIC_VERSION,
        n_tasks=t["files"], b_tasks=f'{t["bytes"]:,}',
        n_snap=s["files"], b_snap=f'{s["bytes"]:,}',
        sums=SUMS_NAME, tarball=TARBALL, manifest=MANIFEST_NAME, pkg=PACKAGE_NAME,
        root=man["fixtures_gate"]["public_root_recorded"],
        code_head=man["code_head"], built_at=man["built_at"])


# ------------------------------------------------------------------ 打包

def pack(*, gb_root=None, repo=None, dest=None, tar: bool = True,
         verbose: bool = True, built_at: "str | None" = None) -> dict[str, Any]:
    repo = pathlib.Path(repo) if repo is not None else pathlib.Path(__file__).resolve().parents[2]
    dest = pathlib.Path(dest) if dest is not None else dest_default(gb_root)
    assert_dest_is_not_on_the_exec_plane(dest, gb_root)

    fx = assert_fixtures_match_frozen(gb_root)
    calib = assert_calibration_intact(gb_root)
    entries = collect(gb_root)
    assert_no_forbidden(entries)

    man = build_manifest(entries, repo=repo, gb_root=gb_root, fx=fx, calib=calib,
                         built_at=built_at)
    sums = PP.sums_text(entries)
    readme = render_readme(man)
    man_bytes = (json.dumps(man, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
    inline = [(SUMS_NAME, sums.encode("utf-8")),
              (MANIFEST_NAME, man_bytes),
              (README_NAME, readme.encode("utf-8"))]

    result: dict[str, Any] = {"dest": str(dest), "files": len(entries),
                              "bytes": man["bytes"], "fixtures_gate": fx,
                              "calibration_sha256": calib["sha256"]}
    if not tar:
        result["dry_run"] = True
        return result

    dest.mkdir(parents=True, exist_ok=True)
    PP.write_tar(dest / TARBALL, entries, inline, verbose=verbose, root_name=PACKAGE_NAME)
    for name, data in ((SUMS_NAME, sums.encode("utf-8")),
                       (MANIFEST_NAME, man_bytes),
                       (README_NAME, readme.encode("utf-8"))):
        (dest / name).write_bytes(data)
        PP._harden(dest / name)
    tarball = dest / TARBALL
    result["tarball"] = str(tarball)
    result["tarball_bytes"] = tarball.stat().st_size
    result["tarball_sha256"] = PP._sha256(tarball)

    PP.record_attachment(repo, {
        "name": TARBALL,
        "role": "public_runtime_material",
        "what": "公开题集实例 + 公开通道标定物料（缺件 ②③，2026-09-13 外部验收报出）",
        "bytes": result["tarball_bytes"],
        "sha256": result["tarball_sha256"],
        "files_inside": len(entries) + len(inline),
        "bytes_inside": man["bytes"],
        "built_at": man["built_at"],
        "code_head": man["code_head"],
        "axes": man["axes"],
        "install": man["install"],
        "download_url": "",
    })
    (dest / "runtime_pack_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    PP._harden(dest / "runtime_pack_result.json")
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="打公开运行物料包（第三个 Release 附件）")
    ap.add_argument("--dry-run", action="store_true", help="只算、不写包")
    ap.add_argument("--dest", default=None, help="落点（默认 $GB/release/<public_version>/）")
    ap.add_argument("--gb-root", default=None, help="物料根（默认 $GENEBENCH_ROOT）")
    ap.add_argument("--built-at", default=None, help="构建时刻（给可复现构建用）")
    ap.add_argument("-q", "--quiet", action="store_true")
    a = ap.parse_args(argv)
    try:
        r = pack(gb_root=a.gb_root, dest=a.dest, tar=not a.dry_run,
                 verbose=not a.quiet, built_at=a.built_at)
    except (RuntimePackError, PP.PackageError) as exc:
        print(f"[拒绝] {exc}", file=sys.stderr)
        return 2
    print(json.dumps(r, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
