#!/usr/bin/env python3
"""卡 4.2-a：把适配例打成 bundle（最小方式）+ 出通行证 + 记 `ops/manifests/v1.0-adapt.json`。

**为什么不走 `genetask/packager` 的现有入口**：`packager.build_task` 从
`genetask/params/v1.0-smoke40.yaml` 的参数表建题，题面由 `genetask/templates/<stage>/` 的
八套阶段模板 + phrasebook 渲染，`task_id` 还被 `genetask/schema.py::_TASK_ID`
（`^s[1-8]-(cor|rob|eco|ops)-\\d{2}$`）钉死 —— 适配题既不是那八个阶段模板中的任何一个，
`adapt-l1-01` 也不合那条正则。硬塞进去要改冻结根（`genetask/` 全在 `ops/freeze_v10.py` 的
CODE_FILES/TEMPLATE_FILES 里），那就得推任务集版本，而**适配集本来就不进 v1.0-smoke 冻结集**。
所以这里用最小方式自己生成 bundle，**判据仍然是别人的**：

* 允许集与通行证结构取 `genetask.bundle`（`X_ALLOWED_FILES` / `X_ALLOWED_PREFIXES` /
  `MANIFEST_VERSION`），不在这里第二次定义；
* 出集前过 `ops/push_guard` 的**树 + 通行证**两道（`check_bundle_tree` + `check_manifest`），
  过不了就抛，**不放宽 guard**。第三道 `check_pushable_set`（按集/按落点判，红线 B2）
  刻意**不在这里**调：它问的是「推到哪儿」，而这里要做的是「在答案面把它打出来」——
  打得出来 ≠ 推得上去，推的那一侧（`assert_pushable(..., dest=…)`）才判落点；
* Dockerfile 过 `genetask.bundle.lint_dockerfile`（L1）。

**这份 bundle 现在可以推 f02 了**（2026-09-10 用户裁定 N-348，卡 Y2）：题源改成
**出集规定题的 oracle 产物**，而裁定明写「这些题的 oracle 产物由此进入执行面 —— 跑过适配赛道的
被测方，主赛道这些题算『可能已见过答案』」。`ops/push_guard.SET_IDS_NOT_PUSHABLE` 里那条按集拒
已显式解除并记因；换上的更窄的门是**落点**：只许落在 `/data/genebench_runner/adapt/` 下，
且落点必须显式声明（`GENEBENCH_PUSH_DEST=… ops/push_bundle_to_f02.sh …`）。

**打包这一侧的落点闸照旧**：暂存根必须在 `$GENEBENCH_ROOT/staging/` 下。它管的是「bundle 在
数据面上生在哪里」，与推不推得上去是两件事 —— 一个打到 `/tmp` 的适配 bundle 谁都扫不到。

用法：
    python ops/pack_adaptation.py --pack                 # 打全部 30 例到默认暂存根
    python ops/pack_adaptation.py --pack --only adapt-l1-01
    # 钉真 digest + 多写一个臂的题面（**钉在出通行证之前** —— 见 pack_one）
    python ops/pack_adaptation.py --pack --only adapt-l1-01 \
        --digest sha256:<64 hex> --arms strict,open,adapt
    python ops/pack_adaptation.py --write-set-manifest   # 写 ops/manifests/v1.0-adapt.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import yaml

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import genebench_config as cfg                                            # noqa: E402
from reference import artifact_schema as sch                              # noqa: E402
from genetask.bundle import (ALL_ARMS, ARM_BY_ID,                       # noqa: E402
                             IMAGE_DIGEST_PLACEHOLDER, MANIFEST_VERSION,
                             X_ALLOWED_FILES, X_ALLOWED_PREFIXES, lint_dockerfile)
from ops import adaptation_track as AT                                    # noqa: E402
from ops.push_guard import check_bundle_tree, check_manifest              # noqa: E402

#: 适配集的 bundle **只许**落在这里。理由见模块头。
STAGING_ROOT: Path = cfg.GENEBENCH_ROOT / "staging" / "adapt_bundles"
#: 默认写哪几个臂的题面。**第一个必须是干预臂**（N-364：出集把 `arm_ids[0]` 当干预臂）——
#: 适配赛道的干预臂是 `adapt`（投放 `/task/adaptation/`），参照臂是裸臂 `open`。
#: `strict` 一并写着：它是主赛道的协议臂，留着才比得出「协议臂 vs 适配臂」。
DEFAULT_ARMS: tuple[str, ...] = ("adapt", "open", "strict")
SET_MANIFEST: Path = _REPO / "ops" / "manifests" / "v1.0-adapt.json"
IMAGE_BASE = "gb-cx-u:r1"
PACKAGER_VERSION = "0.1-adapt"


class PackBlocked(RuntimeError):
    pass


def _sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _w(p: Path, text: str) -> str:
    cfg.create_dir(p.parent)
    p.write_text(text, encoding="utf-8")
    p.chmod(0o600)
    return _sha_bytes(text.encode("utf-8"))


INSTRUCTION = """# 任务：把上游交来的产物修成合规产物

`/task/input/broken.json` 是**上游交来的产物**。它大体上是对的，但**不是按本协议的口径写的**。

请把它修成合规产物，写到 `/task/artifact.json`。

## 你手上有什么

| 路径 | 是什么 |
| --- | --- |
| `/task/input/broken.json` | 上游产物（要修的那份）|
| `/task/input/source_meta.json` | 上游的交付说明：来自谁、哪些路径用的是源侧单位、哪一项上游根本不带 |
| `/task/{stage}.json` | 目标 schema：本阶段产物的结构与字段口径 |
| `/task/adaptation/` | **若存在**：本赛道的适配规则（单位表、字段映射、可接纳性条文）|
| `/task/protocol/` | **若存在**：本阶段契约与自检 CLI |

## 规则

1. **源里没有的，不许补。** 上游没带的口径，把该声明字段写成显式 `"unresolved"`
   （或按目标 schema 的说法标 `unsupported`），并且**不要**产出依赖它的数 ——
   那些字段应当为 `null`。挑一个默认值而不说，等于把不确定性藏进一个看起来很确定的数字里。
2. **能从源里纠正的，纠正。** 单位错配与字段/枚举/代码写法的差异，按源里带的信息换算或翻译。
   拿不准换算方向时，先在产物内部找能定死它的那个恒等式（同一份产物里往往另有一个字段
   与它相等或由它算出）。
3. **不要重做上游的工作。** 这道题只要求把这份产物修成合规产物，不要求你重新取数、重新计算。
4. 信封字段（`task_id` / `config_id` / `arm` / `stage` / `as_of` / `seed` / `produced_at`）
   按本次运行的实际值写，不要照抄上游那份。

## 产出

一个 JSON 文件，路径 `/task/artifact.json`，结构见 `/task/{stage}.json`。
"""

TESTS_PY = '''"""容器内自检：产出在不在、是不是 JSON、信封齐不齐。**不判对错。**"""
import json
import os

ENVELOPE = ("schema_version", "artifact_id", "stage", "task_id", "config_id", "arm",
            "seed", "as_of", "produced_at", "provenance", "declarations", "payload")


def test_artifact_written():
    p = "/task/artifact.json"
    assert os.path.isfile(p), "没有产出 /task/artifact.json"
    with open(p, encoding="utf-8") as fh:
        a = json.load(fh)
    assert isinstance(a, dict), "产出必须是 JSON 对象"
    missing = [k for k in ENVELOPE if k not in a]
    assert not missing, "信封缺字段：%s" % (missing,)
'''

DOCKERFILE = f"""# 适配赛道（v1.0-adapt）用统一基座 {IMAGE_BASE}（卡 4.1 已在 f02 上就位）。
# digest 是**占位**：真值只有执行面知道，推送前由 genetask.packager.pin_image_digest 钉。
FROM {IMAGE_BASE}@{IMAGE_DIGEST_PLACEHOLDER}
WORKDIR /task
"""


def _source_context(source_task: str) -> dict:
    """题源的 as_of / window / universe / payload_profile —— **只取这四项标量**，
    D 面的其余键（declared / oracle / canary / tolerance …）一个都不进 bundle。"""
    p = AT.SOURCE_ROOT / source_task / "task.yaml"
    t = yaml.safe_load(p.read_text(encoding="utf-8"))
    return {"as_of": t["as_of"], "window": dict(t["window"]), "universe": t["universe"],
            "payload_profile": t.get("payload_profile")}


def pack_one(example_id: str, staging_root: Path = STAGING_ROOT,
             reference_root: Path = AT.OUT_ROOT, *,
             digest: str | None = None, image: str | None = None,
             arms: tuple[str, ...] = DEFAULT_ARMS) -> dict:
    """一例 → 一个 bundle + 一份通行证。树与通行证过不了守门就抛。

    `digest`：任务镜像的真 `sha256:…`。**给了就在出通行证之前钉**（红队 2026-09-07
    finding 6）。此前只能事后钉，而通行证是在**占位** Dockerfile 上算的：钉完再推，
    `push_guard` 必然报「内容与通行证不符：image/Dockerfile」，注入器 P3 同样红；
    不钉又过不了 P4b（占位 digest 意味着跑的是没钉住的镜像）。两头堵死 ——
    也就是说 `ops/reports/adapt/README.md` 原来的步骤①②在第④步之前就是死路。

    `arms`：给哪几个臂各写一份题面（内容相同 —— 适配模块是投放的工件，不由题面提及）。
    没写进来的臂在注入时由 P6b 当场拒（此前是裸 `FileNotFoundError`，finding 7）。
    """
    staging_root = Path(staging_root).resolve()
    if not str(staging_root).startswith(str((cfg.GENEBENCH_ROOT / "staging").resolve())):
        raise PackBlocked(
            f"暂存根 {staging_root} 不在 $GENEBENCH_ROOT/staging 下 —— 适配 bundle 的 "
            f"work/input/broken.json 是出集规定题 oracle 产物只破一处的结果，内容上就是那几道题的"
            f"答案；N-348 放行的是「推到执行面的适配根」，不是「生在任何地方」。"
            f"生在受审计的暂存根下，红线 5 的守门与答案面扫描才看得见它。")
    ex_dir = Path(reference_root) / example_id
    mutation = json.loads((ex_dir / "mutation.json").read_text(encoding="utf-8"))
    broken = (ex_dir / "broken.json").read_text(encoding="utf-8")
    stage = mutation["stage"]
    ctx = _source_context(mutation["source_task"])

    out = cfg.create_dir(staging_root / "tasks" / example_id)
    files: dict[str, str] = {}
    instr = INSTRUCTION.replace("{stage}", stage)
    arms = tuple(dict.fromkeys(arms))                 # 去重、保序
    unknown = [a for a in arms if a not in ARM_BY_ID]
    if unknown:
        raise PackBlocked(f"未登记的臂 {unknown} —— 臂集合定义在 genetask/arms.yaml"
                          f"（公平性协议 §6.6），现在登记的是 {list(ALL_ARMS)}")
    for arm in arms:
        files[f"arms/INSTRUCTION.{arm}.md"] = _w(out / "arms" / f"INSTRUCTION.{arm}.md", instr)
    bad = lint_dockerfile(DOCKERFILE)
    if bad:
        raise PackBlocked("Dockerfile 过不了 L1：\n  " + "\n  ".join(bad))
    files["image/Dockerfile"] = _w(out / "image" / "Dockerfile", DOCKERFILE)
    files["image/tests/test_outputs.py"] = _w(out / "image" / "tests" / "test_outputs.py", TESTS_PY)
    files[f"work/{stage}.json"] = _w(
        out / "work" / f"{stage}.json",
        json.dumps(sch.json_schema(stage, ctx["payload_profile"]), ensure_ascii=False, indent=1) + "\n")
    files["work/input/broken.json"] = _w(out / "work" / "input" / "broken.json", broken)
    files["work/input/source_meta.json"] = _w(
        out / "work" / "input" / "source_meta.json",
        json.dumps(mutation["source_meta"], ensure_ascii=False, indent=1) + "\n")

    task = {
        "schema_version": "1.0",
        "task_id": example_id,
        "set_id": AT.SET_ID,
        "task_sha256": None,
        "stage": stage,
        "as_of": ctx["as_of"],
        "window": ctx["window"],
        "universe": ctx["universe"],
        "instruction": {a: {"path": f"arms/INSTRUCTION.{a}.md",
                            "sha256": files[f"arms/INSTRUCTION.{a}.md"]} for a in arms},
        "image": {"base": IMAGE_BASE, "digest": IMAGE_DIGEST_PLACEHOLDER},
        "timeouts": {"agent": 1800, "test": 60},
        "inputs": [{"path": "work/input/broken.json", "sha256": files["work/input/broken.json"],
                    "origin": "ops/adaptation_track.py", "max_date": ctx["as_of"]},
                   {"path": "work/input/source_meta.json",
                    "sha256": files["work/input/source_meta.json"],
                    "origin": "ops/adaptation_track.py", "max_date": ctx["as_of"]}],
        "artifact_path": "/task/artifact.json",
        "contract_ref": ["ops/specs/adaptation_track.md"],
        "artifact_schema_ref": f"ops/specs/artifact_schema/v1.0/{stage}.json",
        "status": "exported",
        #: **刻意留 null**：写时间戳会让同一份内容每次打包出不同的 sha256，
        #: 于是「bundle 变了没有」这个问题永远答「变了」。
        "packed_at": None,
        "packager_version": PACKAGER_VERSION,
    }
    files["task.yaml"] = _w(out / "task.yaml", yaml.safe_dump(task, allow_unicode=True, sort_keys=False))

    # **钉 digest 在出通行证之前**（红队 finding 6；与 ops/export_bundle.py::export_one
    # 同一个顺序）。钉完只有 image/Dockerfile 变，重算它这一条的 sha ——
    # 通行证记的是**钉好之后**的那棵树，否则钉与不钉两条路都通不过守门。
    if digest:
        from genetask.packager import pin_image_digest
        bad = pin_image_digest(out, digest, image=image)
        if bad:
            raise PackBlocked("钉 digest 失败：\n  " + "\n  ".join(bad))
        files["image/Dockerfile"] = _sha_bytes((out / "image" / "Dockerfile").read_bytes())

    from ops.freeze_v10 import frozen_ref, reference_ref
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "task_id": example_id, "set_id": AT.SET_ID, "stage": stage,
        "packager_version": PACKAGER_VERSION,
        "allowed_files": list(X_ALLOWED_FILES), "allowed_prefixes": list(X_ALLOWED_PREFIXES),
        "check_export": [],
        # **如实自报来源**（N-348）。`push_guard.ORIGINS_NOT_PUSHABLE` 一般会因为它拒推；
        # 适配集是那条的唯一例外，而例外的记因在 push_guard 里，不在这里。
        # 瞒着不写才是问题：判据要能长在「这份 bundle 说自己是什么」上。
        "origin": "gold_derived",
        "track": "adaptation",
        "source_note": "work/input/broken.json = 出集规定题的 oracle 产物只破一处的结果",
        "frozen_manifest": frozen_ref(),
        "reference_manifest": reference_ref(),
        "files": {k: files[k] for k in sorted(files)},
    }
    mp = staging_root / f"{example_id}.manifest.json"
    mp.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    mp.chmod(0o600)
    # **树 + 通行证两道照过，不放宽判据**。但这里不调 `assert_pushable`：
    # 它的第三道 `check_pushable_set` 判的是**落点**（N-348 之后：适配 bundle 只许落在
    # /data/genebench_runner/adapt/ 下，且落点必须显式声明），而打包这一刻还没有落点。
    # **打得出来 ≠ 推得上去**：落点的判据在 push_guard 那一侧，推的时候才问。
    bad = check_bundle_tree(out) + check_manifest(out, mp)
    if bad:
        raise PackBlocked("bundle 过不了守门（树 + 通行证）：\n  " + "\n  ".join(bad))
    return {"example_id": example_id, "bundle": str(out), "manifest": str(mp),
            "n_files": len(files)}


def pack_all(staging_root: Path = STAGING_ROOT, only: tuple[str, ...] = (),
             reference_root: Path = AT.OUT_ROOT, *, digest: str | None = None,
             image: str | None = None, arms: tuple[str, ...] = DEFAULT_ARMS) -> list[dict]:
    rows = []
    for ex in AT.EXAMPLES:
        if only and ex.example_id not in only:
            continue
        rows.append(pack_one(ex.example_id, staging_root, reference_root,
                             digest=digest, image=image, arms=arms))
    return rows


# ============================================================== 集清单


def set_manifest(reference_root: Path = AT.OUT_ROOT) -> dict:
    idx = json.loads((Path(reference_root) / "_index.json").read_text(encoding="utf-8"))
    rows = idx["examples"]
    root = hashlib.sha256(json.dumps([[r["example_id"], r["example_sha256"]] for r in rows],
                                     ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    levels: dict[str, int] = {}
    for r in rows:
        levels[r["level"]] = levels.get(r["level"], 0) + 1
    return {
        "set_id": AT.SET_ID,
        "set_version": "0.1.0",
        "status": "draft",
        "_what": "适配赛道最小版的 30 例。**不进 v1.0-smoke 冻结集**：题面、判据、结局定义都另立，"
                 "任务集轴的 SET_VERSION 不因它变动。",
        "_root": "root = sha256(按 example_id 排序的 [example_id, example_sha256] 列表的 JSON)；"
                 "example_sha256 = sha256(该例四个产物文件名 → 内容 sha256 的 JSON)。",
        "levels": levels,
        "n": len(rows),
        "root": root,
        "products_root": str(reference_root),
        "protocol_module": {"protocol_id": "geneprotocol_v1_adapt",
                            "artifacts": AT.module_manifest()["artifacts"]},
        "pushable": "2026-09-10 起可推（用户裁定 N-348）。本集的 bundle 携带出集规定题 oracle 产物"
                    "只破一处的内容；**后果**：跑过本赛道的被测方，主赛道这些题算「可能已见过答案」。"
                    "落点只许 /data/genebench_runner/adapt/，且必须显式声明"
                    "（ops/push_guard.ADAPT_DEST_PREFIX / GENEBENCH_PUSH_DEST）。",
        "exposed_source_tasks": sorted({r["source_task"] for r in rows}),
        "examples": [{k: r[k] for k in ("example_id", "level", "family", "stage", "source_task",
                                        "site", "expected_outcome", "files", "example_sha256")}
                     for r in rows],
    }


def write_set_manifest(reference_root: Path = AT.OUT_ROOT) -> Path:
    SET_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    SET_MANIFEST.write_text(json.dumps(set_manifest(reference_root), ensure_ascii=False, indent=1) + "\n",
                            encoding="utf-8")
    return SET_MANIFEST


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--staging", default=str(STAGING_ROOT))
    ap.add_argument("--only", default="")
    ap.add_argument("--pack", action="store_true")
    ap.add_argument("--digest", default=None,
                    help="任务镜像的真 sha256:…（来自执行面）。**给了就在出通行证之前钉** —— "
                         "事后钉会让通行证与树对不上（红队 finding 6）")
    ap.add_argument("--image", default=None, help="把 FROM 的 repo 换成执行面上真有的镜像名")
    ap.add_argument("--arms", default=",".join(DEFAULT_ARMS),
                    help="给哪几个臂各写一份题面（内容相同）。**第一个必须是干预臂**（N-364）；"
                         "默认 adapt,open,strict。少写一个臂，注入时 P6b 当场拒")
    ap.add_argument("--write-set-manifest", action="store_true")
    a = ap.parse_args(argv)
    only = tuple(x.strip() for x in a.only.split(",") if x.strip())
    if a.pack:
        rows = pack_all(Path(a.staging), only, digest=a.digest, image=a.image,
                        arms=tuple(x.strip() for x in a.arms.split(",") if x.strip()))
        for r in rows:
            print(f"[绿] {r['example_id']:<14} {r['n_files']} 个文件 → {r['bundle']}")
        print(f"{len(rows)} 个 bundle 过了守门的前两道（树 + 通行证）。推送："
              f"GENEBENCH_PUSH_DEST=/data/genebench_runner/adapt/tasks/<id> "
              f"ops/push_bundle_to_f02.sh <bundle> <同一个目录> <manifest>（N-348）。")
    if a.write_set_manifest:
        p = write_set_manifest()
        m = json.loads(p.read_text(encoding="utf-8"))
        print(f"集清单已写：{p}  root={m['root'][:16]}…  n={m['n']}  levels={m['levels']}")
    if not (a.pack or a.write_set_manifest):
        ap.error("给一个动作：--pack 或 --write-set-manifest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
