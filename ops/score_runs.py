#!/usr/bin/env python3
"""数据面结算入口（线 C，2026-09-05）：把 f02 上的 run 目录拉回来 → 逐个 `scorer.score_run` → Table A / B → CSV + LaTeX。

方向纪律：**只有 f01 → f02 这一个 ssh 方向**；拉取是 f01 主动 rsync，f02 上不放任何回连。
拉回来的 run 目录落 `/data/shared/genebench/runs_in/<batch>/`（0700），不进仓库。

用法：
    python ops/score_runs.py --batch a1 --remote /data/genebench_runner/a1/runs/runs [--no-pull]
产出：ops/reports/<batch>/scores/<run_id>.score.json、table_a.csv、table_b.csv、table_a.tex、table_b.tex、summary.md
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from ops import report_io as RIO                    # noqa: E402
import genebench_config as cfg                     # noqa: E402
from scorer import l3 as L3                        # noqa: E402
from scorer import report as R                      # noqa: E402
from scorer import score_run as SR                  # noqa: E402

#: 表头必须写清这批数是**构造验收**（M6 的定义：1 个配置 × 双臂 × 每阶段 1–2 题 × 1 种子）。
#: 不写的话，一张长得像主表的表会被当成实验结果读 —— 而它证明的是链路，不是模型能力。
CAPTION = {"m6": "Table A — GeneBench v1.0 构造验收（M6-lite：1 配置 × 双臂 × 8 题 × 1 种子；**不是实验数据**）",
           "a1": "Table A — A1 链路冒烟（s1-cor-01；**不是实验数据**）"}


def caption_for(batch: str) -> str:
    """任意 batch 名都有一句合规的表头。

    `CAPTION` 里写死的那两条是有具体口径的（M6-lite 的题量与种子数、A1 的题号），
    换不来通用文案。但**没被写死的 batch 也必须带上「不是实验数据」** ——
    接入验证会不断造出新 batch 名（`w31`、`ho1`、……），而回退文案里少了这句，
    一张长得像主表的表就会被当成实验结果读。它证明的是链路，不是模型能力。
    """
    return CAPTION.get(batch, f"Table A — {batch}（接入/harness 验证，不是实验数据）")

#: 拉取的**默认**远端主机（发布方的执行面）。只有 `--remote` 自己不带主机段、
#: 且没传 `--remote-host` 时才用它，而且**每次都打印出来** —— 静默用它的代价
#: 卡 D2 在一台干净机器上实测过：外部用户敲 `--remote <自己机器上的路径>`，
#: rsync 去连的是**发布方的执行面**（`Host key verification failed`），
#: 而那句报错里看不出「它连的是别人的机器」。同机结算传 `--remote-host local`。
F02 = os.environ.get("GENEBENCH_F02", "ljn@192.168.1.219")
#: `--remote-host` 的这个取值 = 不走 ssh，rsync 在**本机**两个路径之间拷。
LOCAL_HOST = "local"
#: 结算落点与私有题集根，**从 `cfg` 现算**（N-770）。
#: 写死发布方绝对路径的代价卡 D2 实测过：`--no-pull` 这条路直接拿 `RUNS_IN / batch`
#: 当 run 根，那个目录在外部机器上不存在 → 结算链当场断；而另一头
#: `ops/results_db.py::protocol_by_run()` 用的是 `cfg.GENEBENCH_ROOT / "runs_in"` ——
#: **在发布方那台机器上这两条是同一个路径，所以这处分叉在内网永远看不见**。
#: 现在两处同源：换根只要换 `GENEBENCH_ROOT`，结算与入库一起跟着走。
#: （与 `ops/run_joblist.py` 的 `PRIVATE_ANSWER_ROOT` 等四个常量同源。）
RUNS_IN = cfg.GENEBENCH_ROOT / "runs_in"
REF_TASKS = cfg.GENEBENCH_ROOT / "reference" / "tasks" / "v1.0-smoke"
#: 公开通道那一套题集根。**与私有并列不覆盖**（卡 1.1-c），常量与 `ops/run_controls.py`
#: 的 `PUBLIC_ANSWER_ROOT` 同一个值 —— 从那里 import，免得第二次分叉。
from ops.run_controls import PUBLIC_ANSWER_ROOT as PUBLIC_REF_TASKS   # noqa: E402
from ops.run_controls import assert_channel_matches                   # noqa: E402


def ref_tasks_for_channel() -> Path:
    """本通道的题集根（= gold 所在处）。

    写死私有那一份的后果实测过：公开通道的 run 拿**私有 gold** 比对，
    CellAgree / max_band_ratio 整片改变而 SR、pass@1 恰好没翻 —— 聚合数看不出来。
    """
    return PUBLIC_REF_TASKS if cfg.channel() == "public" else REF_TASKS


def split_remote(remote: str) -> tuple[str | None, str]:
    """`[user@]host:/path` → `(host, path)`；没有主机段 → `(None, path)`。

    只认**冒号出现在第一个斜杠之前**的那种写法 —— `/data/a:b` 是一个本机路径，
    不是主机段。判错的方向很贵：把本机路径当成主机名，rsync 会去连一台不存在的机器，
    而报错停在 ssh 那一层，看不出是路径被当成了主机。
    """
    head, sep, tail = remote.partition(":")
    if not sep or not head or "/" in head:
        return None, remote
    return head, tail


def pull(batch: str, remote: str, *, host: str = F02,
         runs_root: Path | None = None) -> Path:
    base = runs_root or RUNS_IN
    dst = base / batch
    dst.mkdir(parents=True, exist_ok=True, mode=0o700)
    base.chmod(0o700)
    dst.chmod(0o700)
    h, path = split_remote(remote)
    h = h or host
    src = f"{path.rstrip('/')}/" if h == LOCAL_HOST else f"{h}:{path.rstrip('/')}/"
    # **每次都说清从哪台机器拉**：不打印的话，「它连的是发布方的机器」这件事
    # 只能从 ssh 的报错里猜（卡 D2 实测：Host key verification failed）。
    print(f"[pull ] {'本机' if h == LOCAL_HOST else h}:{path} → {dst}")
    # 排除 agent 的 scratch：Codex 在 `.codex/tmp/arg0/` 下留**断链的符号链接**，
    # rsync 照搬过来之后网关的红线 5 守门 `stat` 不到它们 → **拒绝启动网关**
    # （2026-09-05 实测：OOM 重启 + 这些断链 = 10 分钟数据面停摆）。产物与日志都不在 `.codex/` 里。
    cmd = ["rsync", "-a", "--no-perms", "--chmod=D700,F600",
           "--exclude=.codex/", "--exclude=**/tmp/arg0/",
           src, f"{dst}/"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise SystemExit(f"拉取失败：{r.stderr[-500:]}")
    return dst


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", required=True)
    ap.add_argument("--remote", default=None,
                    help="执行面上的 runs 根（含各 run 目录）。可以写成 `[user@]host:/path` "
                         "自带主机段；不带主机段时用 --remote-host 那台")
    ap.add_argument("--remote-host", default=F02,
                    help=f"--remote 不带主机段时的远端主机（默认 {F02} = 发布方的执行面）。"
                         f"**在自己的机器上结算传 `{LOCAL_HOST}`** —— 不传的话 rsync 去连的是"
                         "发布方那台，报错停在 ssh 层，看不出连错了机器")
    ap.add_argument("--runs-root", default=None,
                    help=f"run 目录的根（默认 {RUNS_IN} = $GENEBENCH_ROOT/runs_in）。"
                         "**换根优先改 GENEBENCH_ROOT**：入库那一步"
                         "（ops/results_db.py::protocol_by_run）只认 $GENEBENCH_ROOT/runs_in，"
                         "只改本参数的话结算出得了表、入库反算不出协议轴")
    ap.add_argument("--no-pull", action="store_true")
    ap.add_argument("--ref-tasks", default=None,
                    help="题集根（gold 所在处）。**默认按通道取**："
                         f"private→{REF_TASKS}，public→{PUBLIC_REF_TASKS}")
    ap.add_argument("--gateway-log", default=None,
                    help="本机网关 access_log（数据面结算的日志侧证据；四个依赖日志的探针族靠它从 "
                         "unobservable 变成真判）。**默认按通道取**：private→gateway_access.jsonl，"
                         "public→gateway_access_public.jsonl（两条通道不混写一份，见 gateway/access_log.py）")
    ap.add_argument("--no-gateway-log", action="store_true", help="不读日志（模拟 f02 侧的不可得，四族标 unobservable）")
    ap.add_argument("--calibration", default=None,
                    help="标定文件；默认取**本通道**的（GENEBENCH_CHANNEL：private→snapshots/v1，public→snapshots/public_v1）")
    a = ap.parse_args(argv)
    # **读哪条通道的标定，是一次显式参数**（红队最终轮 block 1）。
    # 从前这里什么都不传，由 `l3.load_calibration()` 的默认值回落到私有快照 ——
    # 于是公开通道的分数是拿私有 τ 算的，而外部单机上根本没有那个文件。
    calib_path = Path(a.calibration) if a.calibration else cfg.calibration_path()
    if not calib_path.is_file():
        raise SystemExit(f"标定文件不在：{calib_path}（通道 {cfg.channel()}）——"
                         "公开树请先按 README 把 Release 附件解到 snapshots/public_v1/")
    calib = L3.load_calibration(calib_path)
    # 日志侧同理（与 calibration 同一个病）：`cfg.gateway_access_log()` 按通道取，
    # 从前这里写死私有那一份，于是公开通道结算时四个依赖日志的探针族在私有日志里
    # 找不到切片 —— overreach 整片 None、gate 判定整片改变，而且**一声不吭**。
    ref_tasks = Path(a.ref_tasks) if a.ref_tasks else ref_tasks_for_channel()
    # 与 `ops/run_controls` 同一道拦：公开题集 + 非公开通道 = 混通道结算，拒绝启动。
    assert_channel_matches(ref_tasks)
    gw_path = Path(a.gateway_log) if a.gateway_log else cfg.gateway_access_log()
    print(f"[calib] 通道={cfg.channel()} 取自 {calib_path} τ={calib['tau']['value']}")
    print(f"[tasks] 通道={cfg.channel()} 题集根 {ref_tasks}")
    print(f"[gwlog] 通道={cfg.channel()} 取自 {gw_path}"
          + ("" if a.no_gateway_log else ("" if gw_path.is_file() else "  ← 不在！四族将标 unobservable")))
    runs_base = Path(a.runs_root) if a.runs_root else RUNS_IN
    runs_root = runs_base / a.batch
    if not a.no_pull:
        if not a.remote:
            raise SystemExit("--remote 必填（或 --no-pull）")
        runs_root = pull(a.batch, a.remote, host=a.remote_host, runs_root=runs_base)
    # **run 根不在就当场说清楚**（N-770）：从前这里径直 `iterdir()`，
    # 外部机器上那个目录不存在 —— 报出来的是一个 FileNotFoundError（更早的形态是
    # 退 0 并打印「runs: 0；问题: 0」）。两种都答不出「那我该把 run 放哪儿」。
    if not runs_root.is_dir():
        raise SystemExit(
            f"没有 run 目录：{runs_root}\n"
            f"  要么把这一批的 run 目录放成 {runs_base}/{a.batch}/<run_id>/，\n"
            f"  要么传 --runs-root <根>（根下仍按 <batch>/<run_id>/ 分），\n"
            f"  要么用 --remote [user@]host:/path 拉过来"
            f"（在自己这一台上结算就传 --remote-host {LOCAL_HOST}）")
    out = _REPO / "ops" / "reports" / a.batch
    scores = out / "scores"
    scores.mkdir(parents=True, exist_ok=True)
    records, problems = [], []
    for rd in sorted(p for p in runs_root.iterdir() if p.is_dir() and (p / "run.json").is_file()):
        inj = json.loads((rd / "inject.json").read_text(encoding="utf-8"))
        task_dir = ref_tasks / inj["task_id"]
        if not (task_dir / "task.yaml").is_file():
            problems.append(f"{rd.name}: 没有题目录 {task_dir}")
            continue
        try:
            r = SR.score_run(rd, task_dir, out_dir=scores, calib=calib,
                             gateway_log_path=(None if a.no_gateway_log else gw_path))
        except Exception as e:                       # noqa: BLE001  一个 run 坏了不该拖垮整批；但要记下来
            problems.append(f"{rd.name}: {type(e).__name__}: {e}")
            continue
        records.append(r["record"])
        rec = r["record"]
        print(f"{rec['run_id']}: {rec['run_status']} validity={rec['validity']} gate={rec['gate_failed']} "
              f"l3={rec['l3_kind']}:{rec['l3_pass']} steps={rec['steps']}")
    ta, tb = R.table_a(records), R.table_b(records)
    RIO.secure_dir(out)
    R.write_csv(ta, out / "table_a.csv", R.TABLE_A_COLUMNS)
    R.write_csv(tb, out / "table_b.csv")
    (out / "table_a.tex").write_text(R.to_latex(
        ta, ("config_id", "arm", "SR", "pass@1", "pass^3", "ProgressRate", "Steps", "$", "Latency", "Recov", "越权率"),
        caption=caption_for(a.batch), label=f"tab:a-{a.batch}"), encoding="utf-8")
    cols_b = tuple(dict.fromkeys(k for r in tb for k in r))
    (out / "table_b.tex").write_text(R.to_latex(
        tb, cols_b, caption=caption_for(a.batch).replace("Table A", "Table B"),
        label=f"tab:b-{a.batch}"), encoding="utf-8")
    (out / "records.json").write_text(json.dumps(records, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    lines = [f"# {a.batch} 结算摘要", "",
             f"通道: {cfg.channel()}；标定: {calib_path}（τ={calib['tau']['value']}）",
             f"网关日志: {'（未读）' if a.no_gateway_log else gw_path}",
             f"题集根: {ref_tasks}",
             f"runs: {len(records)}；问题: {len(problems)}", ""]
    for r in ta:
        lines.append(f"- {r['config_id']} / {r['arm']}: SR={r['SR']} pass@1={r['pass@1']} pass^3={r['pass^3']} "
                     f"Steps={r['Steps']} Latency={r['Latency']} 越权率={r['越权率']}")
    if problems:
        lines += ["", "## 没结算的 run", ""] + [f"- {p}" for p in problems]
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    RIO.secure_tree(out)                # 报告也是答案面的东西：0600 / 0700（见 ops/report_io.py）
    RIO.secure_tree(runs_root)
    print("\n".join(lines))
    print(f"→ {out}")
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
