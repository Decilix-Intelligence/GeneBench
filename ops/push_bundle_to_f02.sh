#!/usr/bin/env bash
# 把一个 X 面 bundle 推到执行面 f02。**唯一允许的推送入口。**
#
# 为什么不许再手写 rsync：2026-09-04 我用
#   rsync -a .../scratch/a1/ f02:/data/genebench_runner/a1/
# 推了**父目录**，把同级的 reference/（canary.json / scorer.yaml / solve.py）
# 一起送上了执行面。那是红线。判据不在人的注意力里，判据在这个脚本里。
#
# 用法：ops/push_bundle_to_f02.sh <本地 bundle 目录> <f02 目标目录> <通行证 manifest.json>
# 语义：只推**这一个 bundle 目录本身**，先过门（形状 + 通行证逐文件核对），
#       再推，推完在对面独立复核一次。通行证是必填的 —— 没有它就无法判断推的是不是
#       我们冻结的那棵树，而「没核对」不等于「核对过了没问题」。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${GENEBENCH_PY:-/data/shared/genebench/env/bin/python}"
# f01 上没有 `finance02-ts` 这个别名（那是 Mac 的 ssh config）。本脚本跑在数据面，
# 所以默认写数据面能解析的目标。数据面→执行面是架构里唯一允许的 ssh 方向。
F02="${GENEBENCH_F02:-ljn@192.168.1.219}"

[ $# -eq 3 ] || { echo "用法：$0 <本地 bundle 目录> <f02 目标目录> <通行证 manifest.json>" >&2; exit 2; }
SRC="$(cd "$1" && pwd)"          # 解成绝对路径：相对路径 + 尾斜杠是那次事故的一半原因
DST="$2"
MANIFEST="$(cd "$(dirname "$3")" && pwd)/$(basename "$3")"

# ① 门。红就停 —— set -e 之外再显式一次，让意图不依赖 shell 选项。
if ! "$PY" "$REPO_ROOT/ops/push_guard.py" "$SRC" "$MANIFEST"; then
  echo "推送中止：bundle 没过守门。**不要在这里加例外。**" >&2
  exit 1
fi

# ①b **兜底扫描的 timer 必须是活的**（N-61）。
#    2026-09-05 实测：改了 .service 之后 timer 悄悄变成 disabled，
#    `list-timers` 里一个都不剩 —— 门还在，但**每小时没人来按它**。
#    我们在依赖它的这一刻检查它，而不是相信它一直活着。
TIMER=genebench-answer-plane-scan.timer
if ! ssh "$F02" "systemctl --user is-enabled $TIMER >/dev/null 2>&1 && \
                 systemctl --user is-active $TIMER >/dev/null 2>&1"; then
  echo "推送中止：对面的每小时兜底扫描 $TIMER 不在 enabled+active —— **门有了门后没人**" >&2
  echo "  修：ssh $F02 'systemctl --user daemon-reload && systemctl --user enable --now $TIMER'" >&2
  exit 1
fi

# ①c **容器边界口径**（v1.0.16，卡 G2，用户裁定 N-627 走 B）。
#    红线 2 从「答案面不上执行面」（判机器）改成「**答案面永不挂进 agent 容器**」（判挂载面）。
#    对这个脚本意味着什么：**bundle 就是挂载面本身** —— 它的 `work/` 会被复制进 run dir，
#    再由 compose 以 `- <run_dir>/work:/task` 挂进任务容器。所以这里把它**声明**成
#    「将挂到 /task 的那个面」，用容器模式判一次；这是**主口径**。
#
#    为什么下面 ④ 的树扫描**保留**而不是换掉（这是本脚本要交代清楚的取舍）：
#      * 主口径管的是「会不会被 agent 看到」；树口径管的是「这台机器上有没有」。
#      * 公开通道下答案面本来就公开，树口径对它已经没有判别力；
#        但**私有通道的 gold 全量仍然不公开**，它出现在 f02 上仍然是事故 ——
#        那种事故只有树口径看得见（它可能根本没被任何 compose 挂过）。
#      * 两道门的处置相反：容器模式**拒绝启动、不删**（命中的往往是答案面本体），
#        树模式**命中即删**（命中的是一份不该在那儿的副本）。合成一道就必须二选一，
#        而两种情形我们都要管。
GUARD_LOCAL="$REPO_ROOT/runner/f02/answer_plane_guard.py"
if ! PYTHONDONTWRITEBYTECODE=1 "$PY" "$GUARD_LOCAL" --mode container \
        --mount "$SRC/work:/task" --mount "$SRC:/task" \
        --log "${GENEBENCH_APG_LOG:-/data/shared/genebench/logs/answer_plane_local.jsonl}"; then
  echo "推送中止：**容器边界命中** —— 这个 bundle 挂进 /task 会让 agent 看到答案面。" >&2
  echo "  （容器模式不删任何东西：命中的往往是答案面本体。请改 bundle，不要改这道门。）" >&2
  exit 1
fi

# ② 目标目录必须落在执行面根下 —— 防手滑推到 f02 的别处。
case "$DST" in
  /data/genebench_runner/*) : ;;
  *) echo "推送中止：目标 $DST 不在 /data/genebench_runner/ 下" >&2; exit 1 ;;
esac

# ③ 推。**不带尾斜杠**：推目录本身，不推「目录的内容到父级」。
ssh "$F02" "mkdir -m 700 -p $(printf %q "$DST")"
rsync -a --no-perms --chmod=D700,F600 "$SRC" "$F02:$DST/"
# 通行证随行：注入器在对面还要拿它核冻结（N-44）。
BASENAME_EARLY="$(basename "$SRC")"
rsync -a --no-perms --chmod=F600 "$MANIFEST" "$F02:$DST/${BASENAME_EARLY}.manifest.json"

# ④ **落地即扫**（N-61 补强，2026-09-05 裁定）：调对面**自己的**门。
#    ① 查的是本地树、这条查的是**真的落到对面的东西**，而且用的是
#    执行面上那份实现 —— 不是这里再写一遍 grep。发送侧的判据可以被
#    手写命令绕过（2026-09-05 就是），接收侧的不能。
#    命中时它会**删除 + 落闩 + 记日志**，并以退出码 1 告诉我们发生过。
BASENAME="$(basename "$SRC")"
GUARD=/data/genebench_runner/exec/runner/f02/answer_plane_guard.py
if ! ssh "$F02" "test -f $GUARD"; then
  echo "推送后复核中止：对面没有 $GUARD —— **缺门不等于没问题**" >&2
  exit 1
fi
if ! ssh "$F02" "python3 $GUARD --root $(printf %q "$DST/$BASENAME") \
                   --log /data/genebench_runner/logs/answer_plane.jsonl"; then
  echo "**推送后落地扫描命中：对面出现答案面，已按 N-61 处置。立即复核闩与日志。**" >&2
  exit 1
fi
echo "[绿] 已推 $SRC → $F02:$DST/$BASENAME（发送侧门 + 接收侧落地扫描都过）"
