# -*- coding: utf-8 -*-
"""从参数表**一步导出**一个可推送的 X 面 bundle（f01 数据面）。

**为什么要有这个文件**（2026-09-04 夜，N-61）：我之前是用一次性脚本手工串
`build_task → write_task → export_task → pin_image_digest → export_manifest` 的，
把 D 面写进了 `scratch/a1/reference/`，X 面写进 `scratch/a1/runner/` —— **同一个父目录**。
然后一条 `rsync -a scratch/a1/ f02:...` 把两棵树一起送上了执行面。

判据不该长在人的注意力里。所以：

* **答案面固定落 `$GENEBENCH_ROOT/reference/`**（`ops/test_env.py` 的
  `GOLD_ALLOWED_ROOTS` 只认这个根与 `snapshots/`），调用方无权指定；
* bundle 落哪由调用方给，但**导出前后各查一次**：bundle 的**整个暂存根**下
  不许出现任何答案面形状 —— 这就是那次泄漏的形状。

`--digest` 必填：`pin_image_digest` 必须在 `export_manifest` 之前跑
（通行证记的是钉好之后的 sha256），而真 digest 只有执行面知道。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import genebench_config as cfg
from genetask import bundle as GB
from genetask import packager as P
from ops.freeze_v10 import OUT as FROZEN_MANIFEST
from ops.freeze_v10 import frozen_ref
from ops.push_guard import (ANSWER_PLANE_NAMES, ANSWER_PLANE_SEGMENTS,
                            GOLD_TOKEN_RE, PushBlocked, check_bundle_tree)

#: **答案面唯一合法的落点。** 与 `ops/test_env.py::GOLD_ALLOWED_ROOTS` 同源 ——
#: 那条 lint 审计的是 `$GENEBENCH_ROOT` 下第一段路径。
ANSWER_ROOT: Path = cfg.GENEBENCH_ROOT / "reference"

PARAMS: Path = _REPO_ROOT / "genetask" / "params" / "v1.0-smoke40.yaml"


class ExportBlocked(RuntimeError):
    pass


def assert_staging_has_no_answer_plane(staging_root) -> None:
    """**结构判据**：bundle 的暂存根下不许有答案面。

    `push_guard.check_bundle_tree` 查的是 bundle **自己**那棵树；这条查的是它**旁边**。
    那次泄漏两条都躲过了 —— bundle 自己是干净的，脏的是同级的 `reference/`，
    而当时没有任何判据看那一层。
    """
    root = Path(staging_root)
    bad: list[str] = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if set(rel.parts) & set(ANSWER_PLANE_SEGMENTS) or p.name in ANSWER_PLANE_NAMES:
            bad.append(f"答案面形状：{rel}")
        elif p.is_file() and p.suffix in (".py", ".yaml", ".yml", ".json", ".md", ".jsonl", ".txt"):
            try:
                if GOLD_TOKEN_RE.search(p.read_text(encoding="utf-8", errors="replace")):
                    bad.append(f"**gold 串**：{rel}")
            except OSError as e:
                bad.append(f"读不了 {rel}（{e}）—— 读不了 ≠ 查过了没有")
    if bad:
        raise ExportBlocked(
            f"暂存根 {root} 里有答案面，**不许推**：\n  " + "\n  ".join(bad)
            + "\n\n答案面固定落 " + str(ANSWER_ROOT) + " —— 不要把它导到 bundle 旁边。")


def _reference_ref() -> dict:
    """参考轴的冻结引用（`ops/freeze_v10.reference_ref`），与任务集轴并列进通行证。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("freeze_v10", Path(__file__).resolve().parent / "freeze_v10.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.reference_ref()


#: 臂注册表的仓库相对路径 —— 它在 `ops/freeze_v10.CODE_FILES` 里（改它就是改冻结输入）。
ARMS_YAML_REL = "genetask/arms.yaml"


def check_arms(arms) -> tuple[str, ...] | None:
    """出集要渲染的臂。`None` = 注册表里 `default: true` 的那些（与本参数不存在时逐字节相同）。

    三条闸（红队 2026-09-07 finding 1 / finding 5）：

    ① **臂名必须登记**（`build_task` 也查一次；这里先查是为了把「怎么加臂」说出来）；
    ② **参照臂必须在里面** —— 没有 baseline 的一组臂没有任何可比对象；
    ③ **第一个臂必须是干预臂**。`packager.build_task` 把 `arm_ids[0]` 当干预臂写进
       `Built.strict`，而 `arms/equivalence.md` 比的是 `Built.strict` vs `Built.open`：
       写成 `--arms open,hint` 会得到一张 **open vs open** 的等价表 —— `ok=True`、
       `problems` 为空、两侧逐字节相同（红队实测）。顺序在这里是语义，不许靠人记得。
    """
    if arms is None:
        return None
    ids = tuple(str(x).strip() for x in arms if str(x).strip())
    if not ids:
        raise ExportBlocked("--arms 给了空集 —— 不给这个参数就是默认两臂，给了就要点名")
    if len(set(ids)) != len(ids):
        raise ExportBlocked(f"--arms 里有重复的臂：{list(ids)}")
    unknown = [a for a in ids if a not in GB.ARM_BY_ID]
    if unknown:
        raise ExportBlocked(
            f"未登记的臂 {unknown} —— 臂集合定义在 {ARMS_YAML_REL}（公平性协议 §6.6），"
            f"现在登记的是 {list(GB.ALL_ARMS)}")
    if GB.BASELINE_ARM not in ids:
        raise ExportBlocked(
            f"--arms {list(ids)} 里没有参照臂 {GB.BASELINE_ARM!r} —— "
            f"等价规则以它为参照，缺了它没有任何东西可比")
    if ids[0] == GB.BASELINE_ARM:
        raise ExportBlocked(
            f"--arms 的**第一个**臂是参照臂 {GB.BASELINE_ARM!r}：`{','.join(ids)}`。"
            f"建题把第一个臂当**干预臂**写进等价表（packager.build_task 的 "
            f"`strict, open_ = rendered[arm_ids[0]], rendered[BASELINE_ARM]`），"
            f"于是 equivalence.md 会拿 {GB.BASELINE_ARM} 跟 {GB.BASELINE_ARM} 比 —— "
            f"全绿、无 problems、两侧逐字节相同，而**什么都没查**。"
            f"把干预臂写在前面，例如 `--arms {','.join([a for a in ids if a != GB.BASELINE_ARM][:1] + [GB.BASELINE_ARM] + [a for a in ids[1:] if a != GB.BASELINE_ARM])}`")
    return ids


def arm_registry_freshness() -> dict:
    """臂注册表与**已发布的冻结清单**一致吗（红队 2026-09-07 finding 3）。

    `genetask/arms.yaml` 在 `ops/freeze_v10.CODE_FILES` 里：加一个臂就让工作树与清单
    不一致，而在此之前**出集 / 推送 / 注入全程没有任何东西红**（`frozen_ref` 刻意
    不硬比 `code` 段：给打包器加个无关函数不该让已发通行证作废）。这里不改那条判据，
    而是把这件事**记进每一张通行证**：`in_sync=false` 的通行证是可查的，
    「谁也不知道这次跑的是哪一版臂集合」不再是无痕的。

    重冻命令（同版本重冻，题面未变时不推版本）：
        flock /data/shared/genebench/locks/heavy.lock \
            /data/shared/genebench/env/bin/python ops/freeze_v10.py --write
    **重冻会让所有已发通行证作废**（`code` 在 `ROOT_FIELDS` 里 → root 变 → 注入器 P3 拒），
    所以要挑没有在途 bundle 的时刻做，并把已导出的 bundle 重新导出。
    """
    cur = hashlib.sha256((_REPO_ROOT / ARMS_YAML_REL).read_bytes()).hexdigest()
    frozen = None
    try:
        m = json.loads(Path(FROZEN_MANIFEST).read_text(encoding="utf-8"))
        frozen = (m.get("code") or {}).get(ARMS_YAML_REL)
    except (OSError, ValueError):
        frozen = None
    return {"path": ARMS_YAML_REL, "sha256": cur, "frozen_sha256": frozen,
            "in_sync": bool(frozen) and frozen == cur,
            "registered_arms": list(GB.ALL_ARMS), "default_arms": list(GB.ARMS)}


def export_one(task_id: str, staging_root, digest: str, *,
               params: Path = PARAMS, capabilities: dict | None = None,
               image: str | None = None,
               arms: "tuple[str, ...] | list[str] | None" = None) -> dict:
    """建题 → 落答案面 → 导 bundle → 钉 digest → 出通行证。任一步红即抛。

    `arms`：要出哪几个臂（`genetask/arms.yaml` 里登记过的 id，顺序是语义 —— 见
    `check_arms`）。`None` = 默认臂集合，**行为与本参数不存在时逐字节相同**。
    非默认臂只有在这里点名才会进 bundle（红队 2026-09-07 finding 1：在此之前
    「只凭文档加不出臂的集」——手册那条命令固定走两臂）。
    """
    rows = [r for r in P.load_params(params) if r["task_id"] == task_id]
    if len(rows) != 1:
        raise ExportBlocked(f"参数表里 {task_id} 命中 {len(rows)} 行（要恰好 1 行）")
    arm_ids = check_arms(arms)
    b = P.build_task(rows[0], capabilities=capabilities, arms=arm_ids)
    if not b.ok:
        raise ExportBlocked(f"{task_id} 建题不过：\n  " + "\n  ".join(b.problems))

    cfg.create_dir(ANSWER_ROOT)
    task_dir = P.write_task(b, ANSWER_ROOT, capabilities=capabilities)
    bad = P.check_private_files(task_dir)
    if bad:
        raise ExportBlocked(f"数据面自检不过（{len(bad)} 条）：\n  " + "\n  ".join(bad[:8]))

    staging = cfg.create_dir(staging_root)
    bundle = P.export_task(task_dir, staging)

    # 夹具随 bundle（N-84/N-99）：题面 inputs[] 声明的每个文件都必须真的在 bundle 里，否则 agent 拿到的是一道没材料的题。
    _missing = [i["path"] for i in (b.task.get("inputs") or []) if not (Path(bundle) / i["path"]).is_file()]
    if _missing:
        raise ExportBlocked(f"{task_id} 声明的输入不在 bundle 里（夹具没生成？）：{_missing}")
    bad = P.pin_image_digest(bundle, digest, image=image)
    if bad:
        raise ExportBlocked("钉 digest 失败：\n  " + "\n  ".join(bad))

    ce = P.check_export(bundle, P.gold_sha_set(task_dir), b.task["canary"])
    # **两条版本轴都进通行证**（裁定 2026-09-05）：只记任务集的话，两次 gold 算法不同的运行
    # 会看起来完全可比。2026-09-05 通宵实测：这里原来没传 reference_ref，通行证里 `reference_manifest: {}`。
    manifest = P.export_manifest(task_dir, bundle, check_export_result=ce, frozen_ref=frozen_ref(),
                                 reference_ref=_reference_ref())
    # **这次出的是哪几个臂、用的是哪一版臂注册表**（红队 finding 1/3）。
    # `check_manifest` 不比这两个键（比了会让所有旧通行证作废），但它们让
    # 「这份 bundle 的臂集合从哪来」变成事后查得到的事。
    manifest["arms"] = sorted(b.task["instruction"])
    manifest["arm_registry"] = arm_registry_freshness()
    mp = staging / f"{task_id}.manifest.json"
    mp.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    mp.chmod(0o600)

    # 两道**出口**判据：bundle 自己干净 + 它旁边也干净。
    tree_bad = check_bundle_tree(bundle)
    if tree_bad:
        raise PushBlocked("导出的 bundle 自己就不干净：\n  " + "\n  ".join(tree_bad))
    assert_staging_has_no_answer_plane(staging)
    return {"task_dir": str(task_dir), "bundle": str(bundle), "manifest": str(mp),
            "frozen": manifest["frozen_manifest"], "arms": manifest["arms"],
            "arm_registry": manifest["arm_registry"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="导出一个 X 面 bundle（答案面固定落 reference/）")
    ap.add_argument("task_id")
    ap.add_argument("--staging", required=True, help="bundle 落点（**不会**放答案面）")
    ap.add_argument("--digest", required=True, help="任务镜像的真 sha256:...（来自执行面）")
    ap.add_argument("--image", default=None,
                    help="把 FROM 的 repo 换成执行面上真有的镜像名（如 gb-cx）。"
                         "统一基座未建时的过渡形态，偏离记进报告")
    ap.add_argument("--params", default=str(PARAMS))
    ap.add_argument("--arms", default=None,
                    help="逗号分隔的臂名（默认 = 注册表里 default: true 的那些）。"
                         "**第一个必须是干预臂**，参照臂要在里面："
                         "`--arms strict,open,<新臂>`。臂集合见 genetask/arms.yaml 与"
                         "公平性协议 §6.6；出完用 `ops/run_f02_a1.py --dry` 本地核一遍")
    a = ap.parse_args(argv)
    try:
        # 能力位闸的输入与 run_oracles 同源：不传的话 build_task 按「全未就位」判，S3/S8 恒红（2026-09-05 实测）。
        caps = json.loads((_REPO_ROOT / "ops" / "capabilities.json").read_text(encoding="utf-8"))
        r = export_one(a.task_id, a.staging, a.digest, params=Path(a.params), image=a.image,
                       capabilities=caps,
                       arms=([x.strip() for x in a.arms.split(",") if x.strip()] if a.arms else None))
    except (ExportBlocked, PushBlocked, P.PackError) as e:
        print(f"[红] {e}", file=sys.stderr)
        return 1
    if not r["arm_registry"]["in_sync"]:
        print(f"[黄] 臂注册表与已发布的冻结清单不一致（{ARMS_YAML_REL}：盘上 "
              f"{r['arm_registry']['sha256'][:12]}… ≠ 清单 "
              f"{str(r['arm_registry']['frozen_sha256'])[:12]}…）—— 通行证里记成 "
              f"arm_registry.in_sync=false。同版本重冻：`flock $GB/locks/heavy.lock "
              f"$PY ops/freeze_v10.py --write`，**但重冻会让所有已发通行证作废**"
              f"（root 覆盖 code 段），挑没有在途 bundle 的时刻做（公平性协议 §6.6.5）",
              file=sys.stderr)
    print(json.dumps(r, ensure_ascii=False, indent=1))
    # <!-- H10-2026-09-14 --> 下一步按形态分岔；单机没有「推」这件事。
    print("\n下一步 —— **按形态二选一**：")
    print(f"  双机：ops/push_bundle_to_f02.sh {r['bundle']} "
          f"/data/genebench_runner/<run>/runner/tasks {r['manifest']}")
    print("  单机：**不必推** —— `ops/run_joblist.py --topology single` 会用 "
          "`runner.placement.place_bundle()` 在本机落位，调的是**同一批门、同一份实现、"
          "同样顺序**；执行面根从 GENEBENCH_ROOT 现算（GENEBENCH_RUNNER_ROOT 可覆盖）。")
    print("  两种形态都不许手工 cp / rsync 绕过守门。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
