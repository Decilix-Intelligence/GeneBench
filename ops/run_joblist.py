#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""作业清单运行器（卡 5.3，线 C，2026-09-07）：一份 `jobs.jsonl` → 出集 → 推送 → 真跑 → 结算 → 入库 → 回写状态。

    # 干跑（**不出集、不推、不跑、不改清单**，只把每个 job 会执行的命令打出来）
    $PY ops/run_joblist.py --jobs $GB/runs_in/v1demo/jobs.jsonl --dry

    # 真跑（可续跑；已是终态的 job 一律跳过）
    $PY ops/run_joblist.py --jobs $GB/runs_in/v1demo/jobs.jsonl --resume --tables a,b

**方向纪律**：本文件跑在 **f01 数据面**，出集/结算/入库都在本机，只有「真跑」那一步
`ssh` 到 f02（架构里唯一允许的方向）。f02 上不放任何回连。

**六个阶段**，每一步的门都不在这里重写一遍，而是调既有的那一份：

1. **出集** `ops.export_bundle.export_one` —— **同一 task 只出一次**（一份 bundle 供该题的
   所有臂/种子共用；出集会重建答案面 `$GB/reference/tasks/<set>/<task>/`，出两次等于在
   别人结算期间动答案面，HANDOFF 14.4 §8）。
2. **推送** `ops/push_bundle_to_f02.sh` —— **唯一允许的推送入口**（红线 B2）。
3. **真跑** `ops/gateway_lock.py::gateway_lock` 里包 `ssh … run_f02_a1.py`（红线 B6：
   任何打网关的批任务必须串行）。**一个 job 一次 `--arms <单臂>`** —— 清单的粒度就是
   (task, arm, config, seed)，一次跑两臂的话「strict 成了、open 挂了」写不进两行状态。
4. **结算** `ops/score_runs.py --batch <b> --remote …/runs/runs`（**两层 runs**，
   少一层会退 0 并打印「runs: 0；问题: 0」——不报错的错，HANDOFF 14.4 §1）。
5. **入库** `ops.results_db.backfill_batch`（幂等；协议轴从 `runs_in/<b>/*/inject.json` 反算）。
6. **出表** `ops/mk_tables.py`（从结果库出，不另写一份聚合）。

**并发**（`runner.registry.RUNNER_CONCURRENCY`，**默认 1**）
--------------------------------------------------------
默认 1 的理由不是保守，是**网关只有一个 worker**：`access_log` 用进程内锁写，多 worker
会交错写坏行，而四个探针族靠这份日志结算（`ops/gateway_lock.py` 的模块 docstring）。
于是「同时打网关的真跑」在这套系统里没有 >1 的合法值 —— `gateway_lock` 会把它们排成队，
把并发数调到 3 只会得到三个在 flock 上等着的线程和一份更难读的日志。
**并发真正省时间的是出集这一步**（纯本机、按 task 互不相干），运行器把它放进同一个
线程池；真跑那一步每个线程各自去拿 `gateway_lock`，因此仍然串行 —— 这就是
「与 gateway_lock 兼容」的全部含义。

**撞闸与失败不自动重跑**（卡 5.3 判据）
------------------------------------
`failed` / `budget_exhausted` 都是终态，续跑时**跳过**。重跑只能显式：
`--retry-status failed`。撞闸重跑尤其没有意义 —— 同一档预算跑第二次还是撞，而且
`runner.inject` 见到已存在的 run dir 会当场抛（F9：不覆盖遥测），
所以重跑一个已经跑过的 `job_id` 需要**先换 batch 或换 seed**。

**半途中断怎么办**：`running` 且已经有 `run_id` 的 job = 「跑完了没结算」，续跑时
**不重跑，只补结算**；`running` 且 `run_id` 为空 = 「没真起来」，续跑时退回 `pending`。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import genebench_config as cfg                              # noqa: E402
from ops import joblist as JL                               # noqa: E402
from ops import results_db as DB                            # noqa: E402
from ops import genebench_cli as CLI                        # noqa: E402  （⑰ 版本锁 / ⑮ 机器标识）
from ops.gateway_lock import gateway_lock                   # noqa: E402
from runner import placement as PL                          # noqa: E402  （卡 A9：形态与落位）

#: 执行面的 ssh 目标。**默认值是发布方的执行面**，外部（尤其单机形态）
#: 用环境变量 `GENEBENCH_F02` 指到自己的机器 —— 口径与 `ops/push_bundle_to_f02.sh`、
#: `ops/push_exec_to_f02.sh`、`ops/api_usage.py::DEFAULT_F02` 同一套（手册 §1.3 那张表）。
#: 没有这条兜底的代价卡 Xfin 在一台外部机器上实测过：单机用户设了 `GENEBENCH_F02`，
#: `--dry` 打出来的 ssh 目标**仍然是发布方那台**，而他只能改源码，且不知道要改哪一行。
F02 = os.environ.get("GENEBENCH_F02", "ljn@192.168.1.219")
PUSH_BUNDLE = _REPO / "ops" / "push_bundle_to_f02.sh"


def topology(topo: str | None = None) -> str:
    """**形态**（卡 A9，用户裁定 ①，2026-09-14）。`--topology` > `GENEBENCH_TOPOLOGY` > `dual`。

    `single` = 数据面 / 执行面 / 答案面同机，**整条路径不含任何 ssh、不含任何远端核查**；
    `dual` = 发布方这一套（f01 → f02）。**判据是显式的，不猜「这台机器像不像发布方」** ——
    那正是 N-838/840/841/842 那一族缺陷的病因：判据一旦依赖「这台机器能不能造出
    `/data/...`」，它在 Linux 上就永远是绿的，只有 macOS（根卷只读）才显形。
    """
    return PL.resolve_topology(topo)


def runner_root(topo: str | None = None) -> str:
    """执行面的根（N-841，用户裁定 ②）。**单机从 `cfg.GENEBENCH_ROOT` 现算**；
    双机是 `runner/placement_dual.RUNNER_ROOT_DEFAULT`，发布方那台逐字不变。
    两种形态都认显式覆盖 `GENEBENCH_RUNNER_ROOT`。"""
    return str(PL.runner_root(topo))

#: 两条通道各自的**题集根**与**网关 access_log**（卡 6.5）。
#: 值与 `ops/run_controls.py` 的四个同名常量逐字相同 —— 那边是三控侧的落点，
#: 这边是跑批侧的，两处都从**常量**渲染 `--help`（红队 2026-09-07 的 N-304：
#: 手写第二份的代价是 help 里少一层 `public/`，照抄命令直接失败）。
PRIVATE_ANSWER_ROOT = cfg.GENEBENCH_ROOT / "reference" / "tasks" / "v1.0-smoke"
PUBLIC_ANSWER_ROOT = cfg.GENEBENCH_ROOT / "reference" / "tasks" / "public" / "v1.0-smoke-public"
PRIVATE_GATEWAY_LOG = cfg.GENEBENCH_ROOT / "logs" / "gateway_access.jsonl"
PUBLIC_GATEWAY_LOG = cfg.GENEBENCH_ROOT / "logs" / "gateway_access_public.jsonl"

#: 本运行器认的通道。`results_db` 的通道轴同名同值。
CHANNELS: tuple[str, ...] = ("private", "public")

#: 机器标识（裁定 ⑮）。惰性取 —— `runner.inject` 顶层拉执行面的东西，
#: 而本模块的 `--dry` / `--check-plane` 在没有那些依赖时也该跑得起来。
MACHINE_ENV = "GENEBENCH_MACHINE_ID"


def machine_id() -> str:
    from runner.inject import machine_id as _mid
    return _mid()


def answer_root(channel: str) -> Path:
    return PUBLIC_ANSWER_ROOT if channel == "public" else PRIVATE_ANSWER_ROOT


def gateway_log(channel: str) -> Path:
    return PUBLIC_GATEWAY_LOG if channel == "public" else PRIVATE_GATEWAY_LOG


def gateway_addr(channel: str) -> str:
    """f02 上的容器要打哪个网关（`host:port`）。**端口按通道现算**，
    与 `genebench_config.gateway_port()` 同源；写死 18080 的后果是
    「报告头写着 public、数字来自 private」，没有一处会报错。"""
    port = cfg.GATEWAY_PUBLIC_PORT if channel == "public" else cfg.GATEWAY_PORT
    return f"{cfg.GATEWAY_HOST}:{port}"


def provider_dir(channel: str) -> Path:
    """该通道的**冻结 provider**（数据面这一份）。公开链把它建在 `snapshots/public_v1/` 下。"""
    return cfg.PUBLIC_PROVIDER_DIR if channel == "public" else cfg.SNAPSHOTS_V1 / "qlib_provider"


def probe_f02_gateway(channel: str, topo: str | None = None) -> tuple[bool, str]:
    """执行面打得到该通道的网关吗（**从执行面那一侧探**）。

    双机形态下从 f01 探是没有意义的：网关就绑在 f01 上，f01 永远打得到自己。
    要探的是「容器所在那台机器打不打得到」——18080 与 18081 在这一点上实测不同。
    **单机形态下执行面就是本机**，于是这条探针在本机直接跑 curl —— 不发 ssh。
    """
    addr = gateway_addr(channel)
    inner = f"curl -sS --max-time 10 http://{addr}/healthz"
    cmd = (["bash", "-c", inner] if topology(topo) == PL.SINGLE
           else ["ssh", "-o", "ConnectTimeout=120", F02, inner])
    p = _sh(cmd, timeout=180)
    body = (p.stdout or "").strip()
    ok = p.returncode == 0 and f'"channel":"{channel}"' in body.replace(" ", "")
    return ok, (body or (p.stderr or "").strip())[:240]


def probe_f02_provider(channel: str, topo: str | None = None) -> tuple[bool, str]:
    """执行面上有没有一份**根 sha 与该通道数据面一致**的 provider（注入器 P2 要比的就是这个数）。

    单机形态下执行面就是本机：同一条 shell，**不经 ssh**。
    """
    from genetask import pin
    want = pin.provider_root_sha256(provider_dir(channel))
    inner = (f"ls -d {runner_root(topo)}/provider/*/ 2>/dev/null | while read d; do "
             f'f="$d/files.sha256"; [ -f "$f" ] && sha256sum "$f"; done')
    cmd = (["bash", "-c", inner] if topology(topo) == PL.SINGLE
           else ["ssh", "-o", "ConnectTimeout=120", F02, inner])
    p = _sh(cmd, timeout=600)
    have = {}
    for line in (p.stdout or "").splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2:
            have[parts[0]] = parts[1].strip()
    hit = have.get(want)
    return bool(hit), (f"{want[:16]}… → {hit}" if hit else
                       f"要 {want[:16]}…；执行面上现有 " +
                       (", ".join(f"{k[:16]}…({v})" for k, v in have.items()) or "（一份都没有）"))


def assert_public_plane_ready(channel: str, topo: str | None = None) -> dict:
    """公开通道**真跑之前**的执行面前置。两件缺一即拒，且逐条说清怎么补。

    为什么拦在这里而不是让它在 f02 上红：两件的失败形态都会被读成别的东西 ——
    网关不通读成「模型不会做这道题」（空产物），provider 不在读成「注入器坏了」（18 次 P2 红）。
    """
    if channel != "public":
        return {"channel": channel, "checked": False}
    gw_ok, gw_info = probe_f02_gateway(channel, topo)
    pv_ok, pv_info = probe_f02_provider(channel, topo)
    out = {"channel": channel, "checked": True,
           "gateway": {"ok": gw_ok, "addr": gateway_addr(channel), "info": gw_info},
           "provider": {"ok": pv_ok, "expect_from": str(provider_dir(channel)), "info": pv_info}}
    bad = []
    # <!-- H10-2026-09-14 --> 拒绝文案**按形态渲染**：单机形态下这条路上没有 f01/f02，
    # 也不该让外部用户对着发布方的 LAN 地址开防火墙口（那是别人的机器）。
    single = topology(topo) == PL.SINGLE
    where = "本机（单机形态：执行面就是这台机器）" if single else "f02（执行面那台）"
    if not gw_ok and single:
        bad.append(
            f"① **{where}里的容器打不到公开网关 {gateway_addr(channel)}**（探得：{gw_info}）。\n"
            f"   网关起了吗：`ops/public_gateway.sh status`；起了还不通就是**本机的入站防火墙** ——\n"
            f"   容器发往宿主自身 IP 的包走 INPUT 链，docker 只在 FORWARD 链插规则，管不到这条。\n"
            f"   放行的端口要与你**实际起的那个实例**一致（公开通道默认 {cfg.GATEWAY_PUBLIC_PORT}、"
            f"私有 {cfg.GATEWAY_PORT}），网段取 `runner/c41/runner_core.EGRESS_SUBNET` 所在的那个 /22。\n"
            f"   开口要 root（本项目无 sudo），Linux 上请机器主人执行："
            f"`sudo ufw allow from 172.31.240.0/22 to any port "
            f"{gateway_addr(channel).rsplit(':', 1)[1]} proto tcp`\n"
            f"   macOS 没有 ufw、容器也不经宿主 INPUT 链 —— 见 docs/OPERATOR_MANUAL.md §1.3。")
    elif not gw_ok:
        bad.append(
            f"① **f02 打不到公开网关 {gateway_addr(channel)}**（探得：{gw_info}）。\n"
            f"   f01 起了吗：`ops/public_gateway.sh status`；起了还不通就是 f01 的入站防火墙 ——\n"
            f"   18080 放行、18081 没放（实测 f02 curl 18080 拿得到 healthz、18081 连接超时）。\n"
            f"   开口要 sudo（红线 B1 无 sudo），请用户执行："
            f"`sudo ufw allow from 192.168.1.219 to any port 18081 proto tcp`")
    if not pv_ok:
        how = "单机形态就在本机 `cp -a`" if single else "双机形态从数据面 rsync 到执行面"
        bad.append(
            f"② **{where}上没有公开通道的 provider**（{pv_info}）。\n"
            f"   两步：把 {provider_dir(channel)} 放到执行面的 "
            f"{runner_root(topo)}/provider/qlib_provider_<根前 8 位>/"
            f"（{how}）。**那 8 位现算，别手抄**：\n"
            f"   `$PY -c \"import runner.inject as I; print(I.provider_pin_expect('{channel}')[:8])\"`；\n"
            f"   再让注入器 P2 按通道取钉子 —— `genetask/pin.PROVIDER_SHA256_ROOT` 写死的是私有那份，\n"
            f"   而 `genetask/pin.py` 在冻结根 `CODE_FILES` 里，改它要推任务集版本（红线 B4）。\n"
            f"   取小改的路子：`check_provider_pin(..., expect=…)` 本来就收 `expect`，"
            f"由 `runner/inject.py` 按通道传，`pin.py` 一个字不动。")
    if bad:
        raise SystemExit(
            "[红] 公开通道的**执行面**还没准备好，拒绝启动真跑（干跑用 --dry，只探用 --check-plane）：\n"
            + "\n".join(bad))
    return out


def assert_channel(channel: str) -> str:
    """`--channel` 的值本身合法，且与进程的 `GENEBENCH_CHANNEL` **一致**。

    不一致 = 混通道跑批：题集根、网关日志、容器打的网关按 `--channel` 走，
    而 `cfg.snapshot_tables_dir()` / 结算侧读的表按环境变量走。三条判据照样全过、
    报告照样渲染，**数字看起来都对，只是来自另一份数据**（红队 2026-09-07 在三控上
    量到过同一形态，见 `ops/run_controls.py::assert_channel_matches`）。
    """
    ch = str(channel).strip()
    if ch not in CHANNELS:
        raise SystemExit(f"[红] --channel {ch!r} 不认识；可选 {list(CHANNELS)}")
    env = cfg.channel()
    if env != ch:
        raise SystemExit(
            f"[红] --channel {ch!r} 与环境变量 GENEBENCH_CHANNEL={env!r} 不一致 —— 拒绝启动。\n"
            f"    两者分管不同的东西：--channel 决定题集根/网关日志/容器打哪个网关，"
            f"GENEBENCH_CHANNEL 决定结算侧读哪一份快照表。\n"
            f"    对齐了再跑：GENEBENCH_CHANNEL={ch} $PY ops/run_joblist.py --channel {ch} …")
    return ch


def export_from_answer_plane(task_id: str, staging_root, digest: str, *,
                             answer_root: Path, image: str | None = None,
                             want_arms: tuple[str, ...] = ()) -> dict:
    """从**已经建好的答案面**导一个 X 面 bundle（公开通道走这条）。

    与 `ops.export_bundle.export_one` 的差别只有一个，但那一个是要命的：
    **不 `build_task` / 不 `write_task`**，因此不重建答案面。
    `export_one` 的落点是 `$GB/reference/tasks/<set_id>/`，而 `set_id` 在冻结根里
    （两条通道同为 `v1.0-smoke`）—— 在公开通道上调它，等于**拿公开 gold 覆盖私有答案面**
    （N-287 那次污染的同族形态，且当时也是「一次跑批顺手重写了另一条通道的东西」）。

    其余每一道门都保留、且调的是同一份实现：`check_private_files`（数据面自检）、
    `export_task`（剥 D 键）、`pin_image_digest`（钉 digest，必须在出通行证之前）、
    `check_export`（G2/G3/G4/C1）、`export_manifest`（两条版本轴进通行证）、
    `check_bundle_tree` + `assert_staging_has_no_answer_plane`（两道出口判据，红线 B2）。
    """
    import yaml

    from genetask import packager as P
    from ops import export_bundle as EB
    from ops.freeze_v10 import frozen_ref
    from ops.push_guard import check_bundle_tree

    task_dir = Path(answer_root) / task_id
    if not (task_dir / "task.yaml").is_file():
        raise RunJoblistError(
            f"{task_id}: 答案面里没有这道题（{task_dir}）。公开通道的题集由公开链建出来："
            f"`GENEBENCH_CHANNEL=public $PY ops/run_oracles.py --tier full --agent oracle "
            f"--answer-root $GB/reference --set-name public/v1.0-smoke-public`（HANDOFF §12.5 ④）")
    task = yaml.safe_load((task_dir / "task.yaml").read_text(encoding="utf-8"))
    have = set(task.get("instruction") or {})
    miss = [a for a in want_arms if a not in have]
    if miss:
        raise RunJoblistError(
            f"{task_id}: 答案面这一份只渲染了臂 {sorted(have)}，清单要的 {miss} 不在里面 —— "
            f"非默认臂要在**建题**那一步点名（`build_task(..., arms=[...])`），出集搬不出没有的东西")
    bad = P.check_private_files(task_dir)
    if bad:
        raise RunJoblistError(f"{task_id} 数据面自检不过（{len(bad)} 条）：\n  " + "\n  ".join(bad[:8]))

    staging = cfg.create_dir(staging_root)
    bundle = P.export_task(task_dir, staging)
    missing = [i["path"] for i in (task.get("inputs") or []) if not (Path(bundle) / i["path"]).is_file()]
    if missing:
        raise RunJoblistError(f"{task_id} 声明的输入不在 bundle 里（夹具没生成？）：{missing}")
    bad = P.pin_image_digest(bundle, digest, image=image)
    if bad:
        raise RunJoblistError("钉 digest 失败：\n  " + "\n  ".join(bad))
    ce = P.check_export(bundle, P.gold_sha_set(task_dir), task["canary"])
    manifest = P.export_manifest(task_dir, bundle, check_export_result=ce,
                                 frozen_ref=frozen_ref(), reference_ref=EB._reference_ref())
    manifest["arms"] = sorted(task["instruction"])
    manifest["arm_registry"] = EB.arm_registry_freshness()
    mp = Path(staging) / f"{task_id}.manifest.json"
    mp.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    mp.chmod(0o600)
    tree_bad = check_bundle_tree(bundle)
    if tree_bad:
        raise RunJoblistError("导出的 bundle 自己就不干净：\n  " + "\n  ".join(tree_bad))
    EB.assert_staging_has_no_answer_plane(staging)
    return {"task_dir": str(task_dir), "bundle": str(bundle), "manifest": str(mp),
            "frozen": manifest["frozen_manifest"], "arms": manifest["arms"],
            "arm_registry": manifest["arm_registry"]}


class RunJoblistError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ------------------------------------------------------------------ 命令拼装（干跑照着打印这几条）

def export_cmd(job: dict, staging: Path, arms: tuple[str, ...] | None) -> list[str]:
    c = [str(cfg.PYTHON), "ops/export_bundle.py", job["task_id"], "--staging", str(staging),
         "--digest", job["digest"] or "<digest 必填>"]
    if job.get("image"):
        c += ["--image", job["image"]]
    if arms:
        c += ["--arms", ",".join(arms)]
    return c


def bundle_dest(job: dict, topo: str | None = None) -> str:
    """这一批的 bundle 在执行面上的落点。两种形态**同一个形状**，只有根不同。"""
    return f"{runner_root(topo)}/{job['batch']}/runner/tasks"


def push_cmd(job: dict, staging: Path, topo: str | None = None) -> list[str]:
    """**双机形态**的推送命令 —— `ops/push_bundle_to_f02.sh` 是红线 B2 的唯一入口。

    **单机形态不走这条**（裁定 ①：单机没有「推」这件事），换成
    `runner/placement.place_bundle()` 本地落位；见 `export_and_push`。
    """
    t = job["task_id"]
    return [str(PUSH_BUNDLE), str(staging / "tasks" / t),
            bundle_dest(job, topo), str(staging / f"{t}.manifest.json")]


def f02_run_cmd(job: dict, channel: str = "private", topo: str | None = None) -> list[str]:
    """执行面上那一条。**预算参数默认整个不给** —— 给了就把 stage 档位关掉（卡 4.3）。

    **两种形态同一条 inner，只有外壳不同**（卡 A9）：双机包一层
    `ssh -o ConnectTimeout=120 <F02>`；单机直接 `bash -c`，**一次 ssh 都不发**。
    单机那条另有两处刻意的差别，各有理由：
    * `umask 077`（不是 022）—— 单机的执行面根落在 `$GENEBENCH_ROOT` 下，而红线 5 的
      递归审计要求那棵树下**每一个**目录都 go-rwx；077 比 022 更严，B7 要挡的
      「0775 的 `__pycache__`」被它一并挡住（何况 `PYTHONDONTWRITEBYTECODE=1`）。
      容器以 `run_uid:run_gid`（= 起它的那个用户）跑，0700 读得到。
    * 多送一个 `GENEBENCH_RUNNER_ROOT` —— 执行面那个进程要用同一个根，
      不送的话它会去取**双机默认**，于是「落位落在 A、真跑读 B」，而两边都不报错。

    只有清单里显式写了 `max_calls` / `max_tokens`（`budget_override` 非空）才传。

    `channel`：公开通道要多带一个 `GENEBENCH_GATEWAY_ADDR`（卡 6.5）——
    注入器把它渲染进 compose 的边车 `--gateway`（**上游**地址）。
    容器里那个 `http://gateway:18080` 是边车自己的监听端口，与通道无关，一个字不动。
    """
    b, t = job["batch"], job["task_id"]
    topo = topology(topo)
    rroot = runner_root(topo)
    gw = f"export GENEBENCH_GATEWAY_ADDR={gateway_addr(channel)}; " if channel == "public" else ""
    # **机器标识**（裁定 ⑮）：run_id 末尾那一段。注入器在 **f02** 上算 run_id，清单在 **f01**
    # 上算 job_id —— 不把 f01 的标识送过去的话，两边各自算出自己那台机器，`job_id != run_id`，
    # 「这个 job 跑出来的是哪个 run」又要靠一张会漂的映射表。
    # 送的是**结果库这一侧**的机器（f01）：一次跑批的读数归谁，看的是它落在谁的库里。
    mid = f"export {MACHINE_ENV}={machine_id()}; "
    # **通道要送过去**（N-611）。此前这条命令一个字都没提通道，f02 上的
    # `run_f02_a1.py` 于是按 private 取 provider 默认、注入器按 private 取 P2 期望 ——
    # **两头一致所以全绿**，而公开通道的 run 喂给容器的是私有 provider 树。
    # 送两份是故意的：`--channel` 管本进程，`GENEBENCH_CHANNEL` 管它 import 的一切。
    ch = f"export {cfg.CHANNEL_ENV}={channel}; "
    um = "umask 022" if topo == PL.DUAL else "umask 077"
    # **执行面根要送到对面**（N-855，2026-09-14）：`ops/run_f02_a1.py` 的 provider 根现在
    # 从执行面根现算（`runner_core.ROOT`），与 `probe_f02_provider` 查的那一个同源 ——
    # 前提是那个根**真的传过去了**。单机一直在送；双机此前一律不送，于是
    # 在 f01 上设了 `GENEBENCH_RUNNER_ROOT` 的那种用法里，探针查 A、对面读 B，
    # **而两边都不报错**。发布方那台不设这个变量 → `rr` 仍是空串，inner **逐字节不变**。
    rr = (f"export {PL.RUNNER_ROOT_ENV}={rroot}; "
          if topo != PL.DUAL or (os.environ.get(PL.RUNNER_ROOT_ENV) or "").strip() else "")
    inner = (f"{um}; export PYTHONDONTWRITEBYTECODE=1; {rr}{ch}{gw}{mid}cd {rroot} && "
             f"{PL.runner_py()} exec/ops/run_f02_a1.py --channel {channel} "
             f"--bundle {rroot}/{b}/runner/tasks/{t} "
             f"--manifest {rroot}/{b}/runner/tasks/{t}.manifest.json "
             f"--config-id {job['config_id']} --arms {job['arm']} --seq {job['seed']} "
             f"--timeout {job['timeout_s']} "
             f"--run-root {rroot}/{b}/runs --results-dir {rroot}/{b}/results")
    for k, flag in (("max_calls", "--max-calls"), ("max_tokens", "--max-tokens")):
        v = (job.get("budget_override") or {}).get(k)
        if v is not None:
            inner += f" {flag} {int(v)}"
    if topo == PL.SINGLE:
        return ["bash", "-c", inner]
    return ["ssh", "-o", "ConnectTimeout=120", F02, inner]


def live_budget(job: dict) -> dict[str, int]:
    """**现算**这一行今天会按哪档跑 —— 不读清单里物化的那个 `budget`。

    清单里的 `budget` 是**生成那一刻**的读数（`ops/joblist.py` 顶部有说明，写它是为了
    事后查得到「这一行当时按哪档跑的」）。`RUN_BUDGET` 后来改过（N-388：600k → 6M）之后，
    还没跑过的行里躺着的是**陈值** —— 而 `--dry` 打印的正是这个陈值，操作员干跑一遍
    看到的 `tok=3000000` 与手册写的 6M 直接矛盾（红队 W.rt finding 2）。
    真跑读的是 `budget_override`（见 `f02_run_cmd`），所以实跑档位一直是对的；
    错的只是**打印**。这里按 `registry.budget_for(stage)` + 逐键 override 现算一遍。
    """
    return JL.budget_of(job.get("stage"), job.get("budget_override"))[1]


def live_budget(job: dict) -> dict[str, int]:
    """**现算**这一行今天会按哪档跑 —— 不读清单里物化的那个 `budget`。

    清单里的 `budget` 是**生成那一刻**的读数（`ops/joblist.py` 顶部有说明，写它是为了
    事后查得到「这一行当时按哪档跑的」）。`RUN_BUDGET` 后来改过（N-388：600k → 6M）之后，
    还没跑过的行里躺着的是**陈值** —— 而 `--dry` 打印的正是这个陈值，操作员干跑一遍
    看到的 `tok=3000000` 与手册写的 6M 直接矛盾（红队 W.rt finding 2）。
    真跑读的是 `budget_override`（见 `f02_run_cmd`），所以实跑档位一直是对的；
    错的只是**打印**。这里按 `registry.budget_for(stage)` + 逐键 override 现算一遍。
    """
    return JL.budget_of(job.get("stage"), job.get("budget_override"))[1]


def score_cmd(batch: str, channel: str = "private", topo: str | None = None) -> list[str]:
    """结算那一条。**题集根与网关日志按通道给**（卡 6.5）：`score_runs.py` 两个参数的
    默认值都是私有那一套，不传的话公开通道的 run 会拿**私有 gold** 判分、
    在**私有 access_log** 里找不到自己的请求 —— 四个日志族于是静默塌成 unobservable，
    而 unobservable 与 clean 在表上分得开、与「查过了没问题」分不开。"""
    topo = topology(topo)
    c = [str(cfg.PYTHON), "ops/score_runs.py", "--batch", batch,
         "--remote", f"{runner_root(topo)}/{batch}/runs/runs",       # 两层 runs，见 HANDOFF 14.4 §1
         "--ref-tasks", str(answer_root(channel)),
         "--gateway-log", str(gateway_log(channel))]
    if topo == PL.SINGLE:
        # **同机结算**：`--remote-host local` = 不走 ssh，rsync 在本机两个路径之间拷
        # （`ops/score_runs.py::LOCAL_HOST`）。不给它的话 `pull()` 会去连**发布方的执行面**，
        # 而报错停在 ssh 那一层（卡 D2 实测：Host key verification failed），看不出原因。
        c += ["--remote-host", "local"]
    return c


def arms_for_export(arms) -> tuple[str, ...] | None:
    """出集要点名的臂。**与默认臂集合相同时返回 `None`** —— `export_bundle.export_one(arms=None)`
    的行为「与本参数不存在时逐字节相同」是那边写死的保证，点名一遍换不来更多东西，
    却把「默认两臂」这条路和「显式臂集」这条路混成一条。"""
    from genetask import bundle as GB
    ids = tuple(dict.fromkeys(str(a) for a in arms))
    return None if set(ids) == set(GB.ARMS) else JL.check_arms(ids)


def staging_of(job: dict) -> Path:
    return cfg.GENEBENCH_ROOT / "staging" / f"{job['batch']}_{job['task_id']}"


# ------------------------------------------------------------------ 各阶段

def _sh(cmd: list[str], *, cwd: Path | None = None, timeout: int | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd or _REPO), capture_output=True, text=True, timeout=timeout)


def export_and_push(task_id: str, jobs: list[dict], *, reuse: bool = True,
                    channel: str = "private", topo: str | None = None) -> dict:
    """一道题出一次集、推一次。`reuse=True` 时暂存里已有**与当前冻结根一致**的通行证就不重出。

    `channel="public"` 时**不重建答案面**，只从公开题集根导 X 面
    （见 `export_from_answer_plane` 的 docstring：`export_one` 会写私有答案面）。
    """
    from ops.export_bundle import export_one
    from ops.freeze_v10 import frozen_ref

    j0 = jobs[0]
    if not j0.get("digest"):
        raise RunJoblistError(f"{task_id}: 清单里没有 digest —— 出集必须钉执行面上真有的镜像 sha256")
    staging = staging_of(j0)
    man = staging / f"{task_id}.manifest.json"
    # 出集的臂顺序是**语义**（第一个必须是干预臂，N-364）。清单里的臂顺序已经过
    # `joblist.check_arms`，这里按清单里第一次出现的顺序传下去。
    arms_arg = arms_for_export(j["arm"] for j in jobs)

    if reuse and man.is_file():
        try:
            cur = json.loads(man.read_text(encoding="utf-8"))["frozen_manifest"]["root"]
        except (OSError, ValueError, KeyError):
            cur = None
        if cur and cur == frozen_ref()["root"]:
            log(f"  出集复用 {staging}（通行证 root 与当前冻结一致）")
            return {"task_id": task_id, "reused": True, "bundle": str(staging / "tasks" / task_id),
                    "manifest": str(man)}
        log(f"  暂存里的通行证 root={str(cur)[:12]}… 与当前冻结不一致 —— 重出集")

    if staging.exists():
        shutil.rmtree(staging)
    if channel == "public":
        r = export_from_answer_plane(task_id, staging, j0["digest"],
                                     answer_root=answer_root(channel), image=j0.get("image"),
                                     want_arms=tuple(dict.fromkeys(j["arm"] for j in jobs)))
    else:
        caps = json.loads((_REPO / "ops" / "capabilities.json").read_text(encoding="utf-8"))
        r = export_one(task_id, staging, j0["digest"], capabilities=caps,
                       image=j0.get("image"), arms=arms_arg)
    log(f"  出集 {task_id}（通道 {channel}）→ {r['bundle']}（臂 {r['arms']}）")
    if topology(topo) == PL.SINGLE:
        # **单机没有「推」这件事**（裁定 ①）：本地落位，不 ssh、不 rsync 到别的机器、
        # 不核远端 timer。门一道没少 —— push_guard + 容器边界 + 落地树扫，
        # 调的都是同一份实现（`runner/placement.place_bundle`）。
        got = PL.place_bundle(r["bundle"], bundle_dest(j0, topo), r["manifest"], topo)
        log(f"  落位 {task_id} → {got['landed']}（单机形态，0 次 ssh）")
    else:
        p = _sh(push_cmd(j0, staging, topo), timeout=1800)
        if p.returncode != 0:
            raise RunJoblistError(f"{task_id}: 推送失败（rc={p.returncode}）\n{p.stdout[-800:]}\n{p.stderr[-800:]}")
        log(f"  推送 {task_id} → f02 {(p.stdout or '').strip().splitlines()[-1:] or ['']}"[:200])
    return {"task_id": task_id, "reused": False, "bundle": r["bundle"], "manifest": r["manifest"]}


def run_one(job: dict, jobs_file: Path, channel: str = "private",
            topo: str | None = None) -> dict:
    """真跑一个 job。**串行由 `gateway_lock` 保证** —— 并发调用这个函数是安全的，
    它们会在网关锁上排队（红线 B6）。

    **公开通道不要再包一层 `ops/public_gateway.sh run`**：那个子命令自己就持有同一把
    `gateway_lock`，而这把锁不可重入（N-284）—— 表现是「网关起来了、一题都没跑、也不报错」。
    公开通道的正确跑法是 `public_gateway.sh start` → 跑本运行器 → `public_gateway.sh stop`。
    """
    jid = job["job_id"]
    JL.update(jobs_file, jid, status="running", started_at=_now(),
              attempts=int(job.get("attempts") or 0) + 1, error=None)
    cmd = f02_run_cmd(job, channel, topo)
    log(f"  真跑 {jid}（等网关锁…）")
    with gateway_lock(f"5.3:{job['batch']}:{jid}"):
        t0 = time.time()
        p = _sh(cmd, timeout=job["timeout_s"] + 900)
    dt = round(time.time() - t0, 1)
    rec = None
    for line in reversed((p.stdout or "").splitlines()):
        try:
            x = json.loads(line)
        except ValueError:
            continue
        if isinstance(x, dict) and "status" in x:
            rec = x
            break
    if p.returncode != 0 or rec is None or rec.get("status") != "RAN":
        why = (rec or {}).get("error") or (p.stderr or "")[-600:] or f"rc={p.returncode}"
        JL.update(jobs_file, jid, status="failed", ended_at=_now(),
                  error=f"真跑没起来/没跑完（rc={p.returncode}）：{str(why)[:600]}")
        log(f"  [红] {jid} rc={p.returncode} {str(why)[:200]}")
        return {"job_id": jid, "ok": False, "elapsed_s": dt}
    rid = rec.get("run_id")
    drift = ""
    if rid and rid != jid:
        # **不静默**（裁定 ⑮ 的立意就是这个）：两边同源的话这两个字符串逐字相同。
        # 最常见的原因是 exec 树没同步 —— f02 上那份 `runner/inject.py` 还不认机器标识。
        drift = (f"  ！run_id({rid}) ≠ job_id({jid})：两边不同源了。"
                 f"多半是 exec 树没同步（f02 上的 runner/inject.py 还是旧的）——"
                 f"`ops/push_exec_to_f02.sh --with-launch-data` 之后重跑。"
                 f"这一条仍按 run_id 结算，但「哪个 job 对哪个 run」从此要靠这行日志。")
        log(f"  [黄]{drift}")
    JL.update(jobs_file, jid, run_id=rid,
              note=f"跑完待结算：exit={rec.get('exit_code')} calls={rec.get('llm_calls')} {dt}s{drift}")
    log(f"  [绿] {jid} run_id={rec.get('run_id')} exit={rec.get('exit_code')} "
        f"calls={rec.get('llm_calls')} {dt}s")
    return {"job_id": jid, "ok": True, "elapsed_s": dt, "llm_calls": rec.get("llm_calls"),
            "run_id": rec.get("run_id")}


def score_and_ingest(batch: str, *, channel: str = "private",
                     topo: str | None = None) -> dict:
    p = _sh(score_cmd(batch, channel, topo), timeout=3600)
    print((p.stdout or "")[-3000:])
    if p.returncode not in (0, 1):                           # 1 = 有 run 没结算，但表已经出了
        raise RunJoblistError(f"结算失败（rc={p.returncode}）：{(p.stderr or '')[-800:]}")
    r = DB.backfill_batch(batch, channel=channel)
    log(f"  入库：+{r['added']} 条（重复 {r['duplicate']}，库里共 {r['n_total']}）")
    return r


def writeback(batch: str, jobs_file: Path, job_ids: list[str], *,
              records: list[dict] | None = None) -> dict[str, str]:
    """结算记录 → job 终态。`run_status == budget_exhausted` 单独一档（卡 5.3）。

    `records` 给了就用它，不给就读 `ops/reports/<batch>/records.json`（测试用第一条路）。"""
    recs = records if records is not None else json.loads(
        (_REPO / "ops" / "reports" / batch / "records.json").read_text(encoding="utf-8"))
    by_run = {r["run_id"]: r for r in recs}
    out: dict[str, str] = {}
    for j in JL.load(jobs_file):
        if j["job_id"] not in job_ids or j["status"] != "running":
            continue
        r = by_run.get(j["run_id"] or j["job_id"])
        if r is None:
            JL.update(jobs_file, j["job_id"], status="failed", ended_at=_now(),
                      error="结算里没有这条 run —— 跑起来了但没有可结算的 run 目录")
            out[j["job_id"]] = "failed"
            continue
        st = "budget_exhausted" if r.get("run_status") == "budget_exhausted" else "done"
        JL.update(jobs_file, j["job_id"], status=st, ended_at=_now(), run_id=r["run_id"],
                  note=f"run_status={r.get('run_status')} validity={r.get('validity')} "
                       f"l3={r.get('l3_kind')}:{r.get('l3_pass')} steps={r.get('steps')}")
        out[j["job_id"]] = st
    return out


def make_tables(batch: str, tables: list[str], out_dir: Path) -> list[str]:
    made = []
    for t in tables:
        for fmt in ("csv", "md", "latex"):
            p = _sh([str(cfg.PYTHON), "ops/mk_tables.py", "--table", t, "--format", fmt,
                     "--filter", f"batch={batch}", "--out", str(out_dir)], timeout=900)
            if p.returncode != 0:
                log(f"  [黄] table {t}/{fmt} 没出来：{(p.stderr or p.stdout or '')[-300:]}")
                continue
            made.append(f"{t}/{fmt}")
    return made


# ------------------------------------------------------------------ 主流程

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="按作业清单跑一批（卡 5.3）")
    ap.add_argument("--jobs", required=True, help="jobs.jsonl（ops/joblist.py gen 出的）")
    ap.add_argument("--resume", action="store_true",
                    help="续跑。终态一律跳过（不加这个开关也跳过；加了只是把「清单里已有终态」"
                         "从提醒变成预期）")
    ap.add_argument("--dry", action="store_true",
                    help="**不出集、不推、不跑、不改清单**：只把每个 job 会执行的命令打出来")
    ap.add_argument("--retry-status", default=None,
                    help="显式重跑这些状态（逗号分隔，例如 failed）。"
                         "**默认一个都不重跑** —— 撞闸与失败不自动重试")
    ap.add_argument("--retry-failed", action="store_true", help="= --retry-status failed")
    ap.add_argument("--only-task", default=None, help="只跑这些题（逗号分隔）")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--concurrency", type=int, default=None,
                    help="覆盖 registry.RUNNER_CONCURRENCY（不给就按 registry）")
    ap.add_argument("--no-export", action="store_true", help="跳过出集/推送（bundle 已在 f02 上）")
    ap.add_argument("--no-score", action="store_true", help="只跑，不结算/不入库/不回写终态")
    ap.add_argument("--channel", default="private", choices=list(CHANNELS),
                    help="private / public。**必须与环境变量 GENEBENCH_CHANNEL 一致**"
                         "（不一致 = 混通道跑批，见 assert_channel）。public 会：题集根用 "
                         f"{PUBLIC_ANSWER_ROOT}、网关日志用 {PUBLIC_GATEWAY_LOG.name}、"
                         "容器打 18081，且**不重建答案面**")
    ap.add_argument("--tables", default=None, help="出表，逗号分隔（a,b,adaptation）；不给就不出")
    ap.add_argument("--topology", default=None, choices=list(PL.TOPOLOGIES),
                    help="single / dual（不给就读环境变量 GENEBENCH_TOPOLOGY，再不给按 dual）。"
                         "**single = 数据面/执行面/答案面同机，整条路径不含任何 ssh**："
                         "bundle 与 exec 树都在本机落位（不调 ops/push_*_to_f02.sh），"
                         "结算走 --remote-host local。exec 树落位的入口是 "
                         "`python -m runner.placement --topology single --place-exec --with-launch-data`")
    ap.add_argument("--check-plane", action="store_true",
                    help="**只探不跑**：公开通道真跑要的两件执行面前置（执行面打不打得到该通道的网关、"
                         "执行面上有没有该通道的 provider）——单机形态下执行面就是本机，打印 JSON 后退出。"
                         "退出码 0 = 两件都齐")
    a = ap.parse_args(argv)
    a.channel = assert_channel(a.channel)
    a.topology = topology(a.topology)
    if a.topology == PL.SINGLE:
        # **单机形态：把执行面根钉进本进程环境**。不钉的话，惰性 import 进来的
        # `runner.c41.runner_core.ROOT` 会取双机默认 —— 于是「落位落在 A、
        # 某个默认值指着 B」，而两边都不报错（这正是 N-841 那一族的形状）。
        os.environ.setdefault(PL.RUNNER_ROOT_ENV, runner_root(a.topology))

    # ⑰ **版本锁**：任一轴与 RELEASE_MANIFEST 不一致 → 这个包拒绝运行。
    # **`--dry` 也拦**：干跑的用处是「把真跑会做的事原样打出来」，而真跑会被拦下 ——
    # 干跑照打一遍命令，等于教人去跑一个跑不起来的东西。
    try:
        CLI.assert_release_axes(where=f"ops/run_joblist.py --jobs {a.jobs}")
    except CLI.AxisError as e:
        print(str(e), file=sys.stderr)
        return 3

    if a.check_plane:
        try:
            print(json.dumps(assert_public_plane_ready(a.channel, a.topology),
                             ensure_ascii=False, indent=1))
        except SystemExit as e:
            print(str(e))
            return 2
        return 0

    jobs_file = Path(a.jobs)
    all_jobs = JL.load(jobs_file)
    if not all_jobs:
        raise SystemExit(f"{jobs_file} 是空的")
    batches = sorted({j["batch"] for j in all_jobs})
    if len(batches) != 1:
        raise SystemExit(f"一份清单只能是一个 batch（读到 {batches}）—— 结算与入库都按 batch 走")
    batch = batches[0]
    conc = int(a.concurrency) if a.concurrency else JL.concurrency()

    retry = JL._csv(a.retry_status) if a.retry_status else []
    if a.retry_failed and "failed" not in retry:
        retry.append("failed")
    only = JL._csv(a.only_task)
    todo, skipped = JL.select(all_jobs, resume=a.resume, retry_status=retry,
                              only_tasks=only, limit=a.limit)

    log(f"清单 {jobs_file}：{len(all_jobs)} 个 job；本轮要跑 {len(todo)}、跳过 {len(skipped)}；"
        f"batch={batch}；并发={conc}（registry.RUNNER_CONCURRENCY={JL.concurrency()}）")
    log(f"状态计数 {json.dumps(JL.stat(all_jobs), ensure_ascii=False)}")

    if a.dry:
        print("\n===== 干跑：以下命令一条都没有执行，清单一个字节都没改 =====")
        print(f"  # 通道 {a.channel}；题集根 {answer_root(a.channel)}；"
              f"网关日志 {gateway_log(a.channel)}；容器打 {gateway_addr(a.channel)}")
        print(f"  # 形态 {a.topology}；执行面根 {runner_root(a.topology)}"
              + ("（**单机：整条路径不发 ssh**，bundle 本地落位）"
                 if a.topology == PL.SINGLE else "（双机：推送走 ops/push_bundle_to_f02.sh）"))
        for t in dict.fromkeys(j["task_id"] for j in todo):
            tj = [j for j in todo if j["task_id"] == t]
            if a.channel == "public":
                # 公开通道**不重建答案面**：出集只从公开题集根导 X 面（没有等价的 CLI，
                # 打印的是本运行器内部那一步，见 export_from_answer_plane）。
                print(f"  # export_from_answer_plane({t!r}, {staging_of(tj[0])}, "
                      f"answer_root={answer_root(a.channel)})")
            else:
                print("  " + " ".join(export_cmd(tj[0], staging_of(tj[0]),
                                                  arms_for_export(j["arm"] for j in tj))))
            if a.topology == PL.SINGLE:
                print(f"  # runner.placement.place_bundle({staging_of(tj[0]) / 'tasks' / t}, "
                      f"{bundle_dest(tj[0], a.topology)}, "
                      f"{staging_of(tj[0]) / (t + '.manifest.json')})")
            else:
                print("  " + " ".join(push_cmd(tj[0], staging_of(tj[0]), a.topology)))
        for j in todo:
            live = live_budget(j)
            stale = "" if live == j.get("budget") else \
                    f"  ← 现算；清单里物化的是 {j.get('budget')}（生成那一刻的读数，已陈）"
            print(f"  # {j['job_id']}  档={j['budget_tier']} "
                  f"calls={live['max_calls']} tok={live['max_tokens']}{stale}")
            print("  " + str(cfg.PYTHON) + " ops/gateway_lock.py --what "
                  + json.dumps(f"5.3:{batch}:{j['job_id']}", ensure_ascii=False) + " -- "
                  + " ".join(f02_run_cmd(j, a.channel, a.topology)[:-1]) + " "
                  + json.dumps(f02_run_cmd(j, a.channel, a.topology)[-1], ensure_ascii=False))
        print("  " + " ".join(score_cmd(batch, a.channel, a.topology)))
        print(f"  {cfg.PYTHON} ops/results_db.py ingest --batch {batch} --channel {a.channel}")
        return 0

    if not todo:
        log("没有要跑的 job —— 全是终态。要重跑用 --retry-status <状态>")
        return 0

    # 认领上一轮的半途状态：running 且没有 run_id = 没真起来 → 退回 pending。
    ran_already: list[str] = []
    for j in todo:
        if j["status"] == "running" and j["run_id"]:
            ran_already.append(j["job_id"])
        elif j["status"] == "running":
            JL.update(jobs_file, j["job_id"], status="pending",
                      note="上一轮 running 但没有 run_id —— 判为没真起来，退回 pending")
        elif j["status"] in JL.TERMINAL:                      # --retry-status 选中的
            JL.update(jobs_file, j["job_id"], status="pending", error=None, ended_at=None,
                      note=f"显式重跑（原 {j['status']}）")
    if ran_already:
        log(f"{len(ran_already)} 个 job 上一轮跑完了没结算 —— 本轮只补结算，不重跑：{ran_already}")
    to_run = [j for j in todo if j["job_id"] not in ran_already]

    # ⓪ 公开通道：**推 bundle 之前**先探执行面（网关可达 + provider 在位）。
    #    放在出集之前 —— 缺了任何一件，推上去的 18 个 bundle 都只会在 f02 上一个个红。
    assert_public_plane_ready(a.channel, a.topology)

    # ① 出集 + 推送（同一 task 只一次；纯本机，可并行）
    by_task: dict[str, list[dict]] = {}
    for j in to_run:
        by_task.setdefault(j["task_id"], []).append(j)
    if not a.no_export and by_task:
        log(f"出集/推送 {len(by_task)} 道题：{list(by_task)}")
        with ThreadPoolExecutor(max_workers=max(1, conc)) as ex:
            futs = {t: ex.submit(export_and_push, t, js, channel=a.channel, topo=a.topology)
                    for t, js in by_task.items()}
            for t, f in futs.items():
                f.result()                                   # 出集失败就是整批停：bundle 是所有 job 的前提

    # ② 真跑（并发提交，`gateway_lock` 把它们排成串行）
    results = []
    if to_run:
        log(f"真跑 {len(to_run)} 个 job（网关锁串行）")
        with ThreadPoolExecutor(max_workers=max(1, conc)) as ex:
            for r in ex.map(lambda j: run_one(j, jobs_file, a.channel, a.topology), to_run):
                results.append(r)

    if a.no_score:
        log("--no-score：不结算、不入库、不回写终态（这些 job 停在 running）")
        return 0

    # ③ 结算 + 入库 + 回写
    log("结算 + 入库")
    score_and_ingest(batch, channel=a.channel, topo=a.topology)
    wb = writeback(batch, jobs_file, [j["job_id"] for j in to_run] + ran_already)
    log(f"回写 {len(wb)} 行：{json.dumps(wb, ensure_ascii=False)}")

    # ④ 出表
    if a.tables:
        out_dir = _REPO / "ops" / "reports" / batch
        made = make_tables(batch, JL._csv(a.tables), out_dir)
        log(f"出表 {made} → {out_dir}")

    final = JL.stat(JL.load(jobs_file))
    log(f"收工。状态计数 {json.dumps(final, ensure_ascii=False)}")
    return 0 if final["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
