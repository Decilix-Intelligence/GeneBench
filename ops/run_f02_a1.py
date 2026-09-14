#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A1 驱动（在 **f02** 上跑，用 exec 树；2026-09-05 通宵）：一道题 × 一个配置 × 若干臂，经注入器真跑。

    cd /data/genebench_runner/exec && python3 ops/run_f02_a1.py \\
        --bundle /data/genebench_runner/a1/runner/tasks/s1-cor-01 \\
        --manifest /data/genebench_runner/a1/runner/tasks/s1-cor-01.manifest.json \\
        --config-id cfg-codex-deepseek --arms strict,open --seq 1

**凭据**：从 `~/.config/genebench/secrets.env` 读 `DEEPSEEK_API_KEY`，只放进本进程环境的
`GENEBENCH_MODEL_API_KEY`（compose 里 `${GENEBENCH_MODEL_API_KEY}` 引用它，只给边车）。
**绝不打印、绝不写盘。**

**命令**：`runner.c42.harness_commands.command_for(harness)`；返回 `None` 的 harness
（RD-Agent(Q) 只有降级路径）记 BLOCKED 而不是硬跑。

**预算**：注入器按 bundle `task.yaml` 里的 `stage` 从 registry 取**档**写进边车
（`registry.budget_for`：默认 100 次 / 600,000 tokens，**S4 150 / 9M**，**S7 300 / 18M**）。
下面的 `--max-calls` / `--max-tokens` 显式给了就**逐键覆盖档位**（给哪个覆盖哪个）。

**自查（`--dry`）**：只注入不跑 —— P0–P9 与 `work/` 装配全走一遍，**不起容器、不调模型、
不读凭据**，跑完按公平性协议 §6.2/§6.6.4 逐条比各臂的 `work/` 文件集与 sha。
加了一个新臂之后就用它在 f01 上核（红队 2026-09-07 finding 2：在此之前这条路只存在于
读代码的人脑子里）。**run 根必须在数据根之外**（`/data/shared` 之内会被 L-5a 当场拒），
默认 `$TMPDIR/genebench_dry`；f01 上的 provider 用 `--provider-root
/data/shared/genebench/snapshots/v1/qlib_provider`：

    $PY ops/run_f02_a1.py --dry --bundle <B> --manifest <M> --config-id cfg-codex-deepseek \
        --arms <干预臂>,open --provider-root /data/shared/genebench/snapshots/v1/qlib_provider
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# **顶层 import 注入器**：`provider_default()` 与 `main()` 的通道解析都要用它的钉子表。
# （`dry_check()` 里那一句同名的局部 import 是历史遗留，留着无害。）
from runner import inject as INJ                                      # noqa: E402
from runner import registry as REG                                    # noqa: E402
from runner import run_loop as RL                                     # noqa: E402
from runner.c41 import runner_core as RC                              # noqa: E402
from runner.c42 import harness_commands as HC                         # noqa: E402

def runner_root() -> Path:
    """执行面的根。**与 `ops/run_joblist.py::probe_f02_provider` 同源**（N-855，2026-09-14）。

    `runner.c41.runner_core.ROOT` 与 `runner/placement.runner_root()` 认的是**同一个**
    显式覆盖 `GENEBENCH_RUNNER_ROOT`，回落到**同一个**常量
    `runner.placement_dual.RUNNER_ROOT_DEFAULT` —— 所以数据面那侧的探针查哪棵树、
    这里就读哪棵树。
    """
    return Path(RC.ROOT)


#: 执行面上冻结 provider 的**父目录**。每条通道一份，目录名约定
#: `qlib_provider_<根 sha 前 8 位>`：private → `…_54fdda39`、public → `…_56134866`。
#:
#: **原先这里写死 `/data/genebench_runner/provider`**（N-855）。同一条路径上，
#: `ops/run_joblist.probe_f02_provider` 查的却是 `runner_root()/provider` —— **两处不同源**。
#: 双机形态下两者恰好相等，所以在 Linux 上一直不显形；单机形态下执行面根是
#: `$GENEBENCH_ROOT/genebench_runner`，而 f02 上 `/data/genebench_runner/provider`
#: **恰好存在**（双机遗留），于是表现为「**跑起来 ok，只是读了另一棵树**」——
#: 这一条的危险不是它报错，是它**不报错**。修完还加了 `assert_provider_same_source`。
RUNNER_PROVIDER_ROOT = runner_root() / "provider"


def provider_default(channel: str | None = None) -> Path:
    """该通道**默认**的 provider 根 —— 从注入器的钉子表**现算**，不写死绝对路径。

    此前这里是一个模块常量（写死私有那一份），而 `main()` 的 `global` 又漏了它 ——
    真跑路径上 `--provider-root` 于是被静默忽略（N-611）。**公开通道的 18 个 run
    喂给容器的全是私有 provider，P2 还全绿**（期望值也回落到私有，两头一致）。
    改成按通道现算之后，「默认值」与「P2/P7e 的期望值」同源：
    两条通道各自的默认再也不可能指到对方那棵树上。
    """
    return RUNNER_PROVIDER_ROOT / f"qlib_provider_{INJ.provider_pin_expect(channel)[:8]}"


#: 向后兼容的名字 —— **只是 private 那条通道的默认值**，不再是真跑读的那个量。
#: 真跑读 `a.provider_root`（见 `main()`）。
PROVIDER = RUNNER_PROVIDER_ROOT / "qlib_provider_54fdda39"
#: 这两个**总是被 `ops/run_joblist.py` 的 `--run-root` / `--results-dir` 盖掉**，
#: 所以它们此前写死绝对路径没有显形过（`ops/test_single_machine.py` 的 `KNOWN_DEFECT`
#: 把它们记成 latent）。与 `RUNNER_PROVIDER_ROOT` 同源、同一次改掉（卡 F10）：
#: 发布方那台不设 `GENEBENCH_RUNNER_ROOT` 时取值与改动前逐字相同。
RUN_ROOT = runner_root() / "a1" / "runs"
RESULTS = runner_root() / "a1" / "results"
SECRETS = Path.home() / ".config" / "genebench" / "secrets.env"


def assert_provider_same_source(provider_root, *, dry: bool) -> None:
    """**inner 真用的 provider 根，必须就是探针查的那一个**（N-855，2026-09-14）。

    `ops/run_joblist.probe_f02_provider` 扫的是 `<执行面根>/provider/*/`；真跑要是读了
    别处那一棵，探针就在替**另一棵树**担保 —— 而两边都不会报错（f02 上两棵都在）。
    所以这里**当场拒绝并把两个值都打出来**，不许继续。

    `--dry` 不判：自查那条路径明确要求把 provider 指到数据面那一份
    （本模块 docstring 的照抄命令：`--provider-root $GB/snapshots/v1/qlib_provider`），
    它本来就不在执行面根下，判它会把一道自查变成死锁。
    """
    want = RUNNER_PROVIDER_ROOT
    got = Path(provider_root)
    if dry:
        print(f"[dry] provider 根 {got}（--dry 不判同源；真跑要求它落在 {want} 下）")
        return
    if got.parent != want:
        raise SystemExit(
            "[红] provider 根与探针查的那一棵不是同一个 —— 拒绝继续（N-855）。\n"
            f"    本进程要用的  ：{got}\n"
            f"    探针查的父目录：{want}（= <执行面根>/provider，执行面根 {runner_root()}）\n"
            "    两者不一致时真跑会静默读另一棵树，而 P2 两头一致所以照样全绿。\n"
            "    对齐办法：要么不传 --provider-root（按通道取默认），"
            "要么把 GENEBENCH_RUNNER_ROOT 设成那棵树的根。")


def load_key() -> None:
    """把 DEEPSEEK_API_KEY 读进 GENEBENCH_MODEL_API_KEY。**不回显**。"""
    if not SECRETS.is_file():
        raise SystemExit(f"缺 {SECRETS}")
    mode = SECRETS.stat().st_mode & 0o777
    if mode != 0o600:
        raise SystemExit(f"{SECRETS} 权限是 {oct(mode)}，要求 0600")
    for line in SECRETS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("DEEPSEEK_API_KEY="):
            os.environ["GENEBENCH_MODEL_API_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'")
            return
    raise SystemExit("secrets.env 里没有 DEEPSEEK_API_KEY=")


#: `--dry` 的 run 根默认落点。**数据根之外** —— 见 `dry_run_root`。
DRY_ROOT_DEFAULT = Path(os.environ.get("TMPDIR") or "/tmp") / "genebench_dry"


def dry_run_root(path=None) -> Path:
    """`--dry` 的 run 根。落在数据根（`/data/shared` 这些）之内会被 L-5a 当场拒 ——
    那条门查的是 compose 里任务容器的挂载点，而挂载点就是 `<run_root>/runs/<rid>/work`。
    在这里先判一次，是为了让人看到的是「换个 run 根」而不是注入到一半的 L-5a 报错。
    """
    from runner.c41.runner_core import DATA_ROOTS
    root = Path(path or DRY_ROOT_DEFAULT).resolve()
    for d in DATA_ROOTS:
        dr = Path(d)
        if root == dr or dr in root.parents:
            raise SystemExit(
                f"--dry 的 run 根 {root} 落在数据根 {d} 之内 —— L-5a 判据 2 会当场拒。"
                f"本地自查把 run 根放到数据根之外，例如 --run-root {DRY_ROOT_DEFAULT}")
    return root


def dry_check(a, command: str | None) -> int:
    """**只注入不跑**：P0–P9 + `work/` 装配，然后按 §6.2/§6.6.4 逐条比臂。

    与真跑的全部差别就是三个开关：没有 docker（`require_docker=False`）、
    不查仓库权限（`check_modes=False`）、不搬 602 M 的 provider（`place_provider=False`），
    外加一个数据根之外的 run 根。这四件事此前**文档里一个字都没有**（红队 finding 2）。

    退出码：0 = 每一条子句都对上；1 = 任一臂注入失败，或臂差异不等于该臂的工件集。
    """
    from genetask.bundle import ARM_BY_ID, BASELINE_ARM
    from runner import inject as INJ

    manifest = json.loads(Path(a.manifest).read_text(encoding="utf-8"))
    expect_root = manifest["frozen_manifest"]["root"]
    run_root = dry_run_root(a.run_root) / f"{manifest['task_id']}.{time.strftime('%Y%m%dT%H%M%S')}"
    run_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    arms = [x.strip() for x in a.arms.split(",") if x.strip()]
    print(f"[dry] run 根 {run_root}；臂 {arms}；bundle {a.bundle}")

    work: dict[str, Path] = {}
    for arm in arms:
        try:
            inj = INJ.inject(a.bundle, arm, run_root=run_root, provider_root=a.provider_root,
                             config_id=a.config_id, manifest=manifest,
                             expect_frozen_root=expect_root,
                             command=command or 'sh -c "true"', seq=a.seq,
                             require_docker=False, check_modes=False, place_provider=False,
                             model_upstream="")
        except Exception as e:                                        # noqa: BLE001
            print(f"[红] {arm} 注入失败：{type(e).__name__}: {e}")
            return 1
        work[arm] = Path(inj.run_dir) / "work"
        print(f"[dry] {arm:<10} run_dir={inj.run_dir}  work/ "
              f"{sum(1 for p in work[arm].rglob('*') if p.is_file())} 个文件")

    base = BASELINE_ARM
    if base not in work:
        print(f"[黄] 参照臂 {base!r} 不在 --arms 里 —— 注入过了，但 §6.2 的等号没有可比的一侧。"
              f"自查请带上它：--arms <干预臂>,{base}")
        return 0
    rc = 0
    for arm in arms:
        if arm == base:
            continue
        proto = dict(INJ.arm_files(arm))
        for spec in ARM_BY_ID[arm].artifacts:
            # 逐题规则随 bundle 走（按题不同，因此不在封闭清单里）——
            # §6.6.4 的右侧是「该臂工件集 ∪ 该臂的逐题规则」，少算它这条判据会误红。
            if spec.per_task_rules:
                src = Path(a.bundle) / "work" / spec.mount
                if src.is_dir():
                    proto.update({f"{spec.mount}/{f.name}": ""
                                  for f in sorted(src.iterdir()) if f.is_file()})
        d = INJ.arm_diff(work[arm], work[base])
        bad = INJ.check_arm_diff(work[arm], work[base], protocol=proto, arm=arm, base=base)
        print(f"[dry] {arm} vs {base}：{arm} 独有 {d['strict_only']}；"
              f"{base} 独有 {d['open_only']}；同名 sha 不同 {d['sha_differs']}")
        if bad:
            rc = 1
            print("[红] " + "\n[红] ".join(bad))
        else:
            print(f"[绿] {arm} vs {base} 三条子句逐条对上（独有集 == 该臂工件集 ∪ 逐题规则；"
                  f"{base} 独有 == ∅；同名文件里 sha 不同的只有 INSTRUCTION.md）")
    return rc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--config-id", required=True)
    ap.add_argument("--arms", default="strict,open",
                    help="逗号分隔的臂名。**任何登记在 genetask/arms.yaml 里的臂**都行"
                         "（内置 strict,open；非默认臂要先用 build_task(..., arms=[...]) 出集，"
                         "否则 bundle 的 task.yaml 里没有它的 instruction 条目，P6 会红）。"
                         "拼错的臂名由注入器 P1 当场拒绝")
    ap.add_argument("--seq", type=int, default=1)
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--max-calls", type=int, default=None,
                    help="本批每 run 的模型调用上限（覆盖 registry.RUN_BUDGET，只在本进程生效）。"
                         "**不给就按 stage 取档**：registry.budget_for —— 默认 100，S4 150，S7 300。"
                         "跑 S4/S7 的题时别显式写 100，那等于把档位关掉。"
                         "A1 总上限 200 次：Codex 两臂已用 45，其余各 run ≤ 50。")
    ap.add_argument("--run-root", default=None, help="run 目录根（默认 a1/runs；M6-lite 用 m6/runs）")
    ap.add_argument("--provider-root", default=None,
                    help="冻结 provider 的根。**不给就按 --channel 取该通道的默认**"
                         "（<执行面根>/provider/qlib_provider_<根前 8 位>；执行面根认 "
                         "GENEBENCH_RUNNER_ROOT，双机默认见 "
                         "runner/placement_dual.RUNNER_ROOT_DEFAULT）。"
                         "真跑时它必须落在那个父目录下，否则当场拒（N-855）。"
                         "在 f01 上 --dry 时指到 "
                         "/data/shared/genebench/snapshots/v1/qlib_provider。"
                         "给了就**真跑也生效** —— 2026-09-11 之前只有 --dry 用它（N-611）")
    ap.add_argument("--channel", default=None,
                    help="通道（private|public）。决定 provider 的默认根与 P2/P7e 的期望值。"
                         "不给就取环境变量 GENEBENCH_CHANNEL，再不给按 private。"
                         "**认错的通道当场抛**，不回落 —— 回落会把一次拼写错误"
                         "伪装成一次 provider 事故")
    ap.add_argument("--dry", action="store_true",
                    help="**只注入不跑**：P0–P9 + work/ 装配，不起容器、不调模型、不读凭据；"
                         "跑完按公平性协议 §6.2/§6.6.4 比各臂的 work/ 文件集与 sha。"
                         "run 根必须在数据根之外（L-5a），默认 $TMPDIR/genebench_dry")
    ap.add_argument("--results-dir", default=None, help="结果 json 目录（默认 a1/results；M6-lite 用 m6/results）")
    ap.add_argument("--max-tokens", type=int, default=None,
                    help="本批每 run 的 token 上限。**不给就按 stage 取档**（默认 600,000，S4 9M，S7 18M）。"
                         "Codex 裸臂在第 22 次调用就撞了 600k（每次 45k prompt），"
                         "A1 是基建冒烟，按用户裁定只卡调用次数，这里放到 3M。")
    a = ap.parse_args()
    # **通道先定，别的都跟着它**（N-611）。`provider_pin_expect` 对不认识的通道当场抛，
    # 不回落 —— 回落会把一次拼写错误伪装成一次 provider 事故。
    channel = (a.channel or os.environ.get(INJ.CHANNEL_ENV) or INJ.DEFAULT_CHANNEL).strip()
    INJ.provider_pin_expect(channel)
    # 注入器的 `channel` 形参默认从环境取（`run_loop.run_once` 不转发它），
    # 所以在这里落进本进程环境 —— P2 / P7e / `PA.materialize` 三处拿到的于是是同一条通道。
    os.environ[INJ.CHANNEL_ENV] = channel
    if a.provider_root is None:
        a.provider_root = str(provider_default(channel))
    # **同源判据**（N-855）：不一致当场拒，两个值都打出来。
    assert_provider_same_source(a.provider_root, dry=bool(a.dry))
    global RUN_ROOT, RESULTS
    if a.run_root:
        RUN_ROOT = Path(a.run_root)
    if a.results_dir:
        RESULTS = Path(a.results_dir)
    if a.max_calls is not None or a.max_tokens is not None:
        # **不要在这里再 import 一次 REG**：那会让 REG 在整个 main() 里变成局部名，
        # 而它只在本分支被赋值 —— 两个参数都不给时下面的 REG.by_id 直接 UnboundLocalError。
        # 顶层第 32 行已经 import 过了；就地改 RUN_BUDGET 用的就是那同一个模块对象。
        if a.max_calls is not None:
            REG.RUN_BUDGET["max_calls"] = int(a.max_calls)       # inject 从这里取预算闸写进边车
        if a.max_tokens is not None:
            REG.RUN_BUDGET["max_tokens"] = int(a.max_tokens)

    cfg = REG.by_id(a.config_id)
    command = HC.command_for(cfg.harness)
    if a.dry:
        # **不读凭据、不建 results 目录**：自查不产生任何结算面的东西。
        return dry_check(a, command)
    RESULTS.mkdir(mode=0o700, parents=True, exist_ok=True)
    if command is None:
        out = {"config_id": cfg.config_id, "harness": cfg.harness, "status": "BLOCKED",
               "why": "没有 LLM 驱动的调用命令（适配器只有降级路径）"}
        (RESULTS / f"{cfg.config_id}.BLOCKED.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
        print(json.dumps(out, ensure_ascii=False))
        return 3

    manifest = json.loads(Path(a.manifest).read_text(encoding="utf-8"))
    root = manifest["frozen_manifest"]["root"]
    load_key()
    RUN_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)

    rc_all = 0
    for arm in [x.strip() for x in a.arms.split(",") if x.strip()]:
        t0 = time.time()
        rec: dict = {"config_id": cfg.config_id, "harness": cfg.harness, "arm": arm, "seq": a.seq,
                     "channel": channel, "provider_root": str(a.provider_root)}
        try:
            # **`a.provider_root`，不是模块常量 `PROVIDER`**（N-611）——
            # 读常量的那一版让 `--provider-root` 在真跑路径上成了摆设。
            res = RL.run_once(Path(a.bundle), arm, run_root=RUN_ROOT,
                              provider_root=Path(a.provider_root),
                              config_id=cfg.config_id, manifest=manifest, expect_frozen_root=root,
                              command=command, seq=a.seq, timeout_s=a.timeout)
            rec.update({"status": "RAN", "run_id": res.run_id, "run_dir": str(res.run_dir),
                        "exit_code": res.exit_code, "elapsed_s": res.elapsed_s})
            art = Path(res.run_dir) / "work" / "artifact.json"
            rec["artifact"] = str(art) if art.is_file() else None
            rec["artifact_bytes"] = art.stat().st_size if art.is_file() else 0
            llm = Path(res.run_dir) / "log" / "llm_log.jsonl"
            rec["llm_calls"] = sum(1 for _ in llm.open()) if llm.is_file() else 0
            # **这个 run 跑在哪条通道的哪份 provider 上** —— 从 inject.json 抄一份进结果记录，
            # 免得事后要 ssh 进 f02 翻 run 目录才答得上来（N-611）。
            ij = Path(res.run_dir) / "inject.json"
            if ij.is_file():
                rec["provider"] = (json.loads(ij.read_text(encoding="utf-8")) or {}).get("provider")
        except Exception as e:                                        # noqa: BLE001
            rec.update({"status": "ERROR", "error": f"{type(e).__name__}: {str(e)[-800:]}"})
            rc_all = 1
        rec["wall_s"] = round(time.time() - t0, 1)
        # 文件名带 task_id：M6-lite 多题共用一个 results 目录，不带会互相覆盖
        (RESULTS / f"{manifest['task_id']}.{cfg.config_id}.{arm}.r{a.seq:02d}.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps({k: v for k, v in rec.items() if k != "error"} | {"error": rec.get("error", "")[:300]},
                         ensure_ascii=False))
    return rc_all


if __name__ == "__main__":
    raise SystemExit(main())
