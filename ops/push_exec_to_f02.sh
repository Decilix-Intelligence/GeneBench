#!/usr/bin/env bash
# 把仓库里**执行面要用的那几个模块**同步到 f02 的 `exec/` 树。W-0，2026-09-06。
#
# 在此之前这件事没有脚本：`exec/` 怎么来的，仓库里一个字都没写
# （`ops/tickets.md:1947` 只留下一句「同步 `exec/` 后 P2 对全量真 provider 判绿」）。
# 于是 2026-09-04 发生过一次「按规格调用却拿到错函数」—— **对面是改名前的旧版**。
#
# ── 为什么是**白名单**而不是「四个目录减去几个排除项」 ──────────────────
# 任务书原话是「只同步 genetask ops runner vendor 四个目录（排除 __pycache__
# .pytest_cache ops/reports ops/acceptance ops/recon）」。**照做会踩红线 2**：
#   * `genetask/templates/**/solve.py`（170 份）与 `**/scorer.yaml` —— 参考解与评分器；
#   * `ops/data_cards/gold_factors.md`、`ops/data_cards/s7_backtest_gold.md` —— gold 口径；
#   * `ops/test_*.py` 里有合成 gold 串字面量。
# 那份排除清单里一条都没挡住。所以这里按**保守方向**做（CONFLICT，已登记）：
# 列出执行面真正 import 得到的东西，**其余一律不推**；并且不靠这份清单本身判绿 ——
# 推之前先在 f01 的 staging 上跑一遍**执行面自己那道门**（`answer_plane_guard.scan`），
# 有一条命中就停。判据不在写清单的人的注意力里，判据在扫描里。
#
# 用法：
#   ops/push_exec_to_f02.sh [--dry-run] [--with-launch-data] [--no-verify]
#
#   --dry-run           只建 staging + 扫描 + 打印 rsync 会做什么，不推
#   --with-launch-data  额外同步 harnesses/ 与 integrations/（阶段二/三需要 f02 也读
#                       launch.json / config.yaml 时才打开；**默认关**，见 tickets_inbox/W-0.md）
#   --no-verify         跳过推送后的 command_for 逐字节复核（不建议）
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# ── 落点：**可配 + 缺了大声说**（N-851 = N-840，用户裁定 ①，2026-09-14）────────────
# 原来这两行是 `PY="${GENEBENCH_PY:-/data/shared/genebench/env/bin/python}"` 与
# `STAGE="${GENEBENCH_EXEC_STAGE:-/data/shared/genebench/scratch/exec_push}"` ——
# **另一台机器的绝对路径 + 静默使用**。外部双机用户照 README §2.4 ③ 敲裸命令，一路走到
# 「== 3/6 …扫 staging」那句 `"$PY" - "$STAGE"` 才炸：`No such file or directory`，**rc=127**；
# 而 `GENEBENCH_PY` / `GENEBENCH_EXEC_STAGE` / `GENEBENCH_EXEC_DEST` 在 README、
# docs/OPERATOR_MANUAL.md、ops/HANDOFF.md 里 **grep 命中 0 次** —— 报错里没有一句话
# 告诉他该设什么。与 N-770 / N-826 / N-831 同形：**分叉在「跑它的是不是发布方那台机器」上**。
#
# **只改默认值的来源与缺失时的表现，不改这个脚本的任何判据与步骤**（用户口径：
# 「双机路径不动」= 单机改造不许改双机语义）：六步、顺序、落地即扫、逐字节复核一条没动。
#   ① 默认从 `GENEBENCH_ROOT` 现算 —— 那是两处文档反复写过的**唯一**落点变量；
#      `GB_ROOT` 自己的兜底值与 `genebench_config._DEFAULT_ROOT` 逐字相同
#      （`ops/test_F10.py` 把这两个字面量钉在一起，漂了就红）；
#   ② 解释器不存在 → **第 0 步当场停**，并把该设的变量名打出来，不再走到第 133 行才 rc=127。
# **发布方那台不设任何变量时，四个取值与本次改动之前逐字节相同**（同一份测试钉住）。
GB_ROOT="${GENEBENCH_ROOT:-/data/shared/genebench}"
PY="${GENEBENCH_PY:-$GB_ROOT/env/bin/python}"
F02="${GENEBENCH_F02:-ljn@192.168.1.219}"
DEST="${GENEBENCH_EXEC_DEST:-/data/genebench_runner/exec}"
STAGE="${GENEBENCH_EXEC_STAGE:-$GB_ROOT/scratch/exec_push}"
SSH_OPTS=(-o ConnectTimeout=120)

DRY=0; LAUNCH_DATA=0; VERIFY=1; PRINT_PATHS=0
for a in "$@"; do
  case "$a" in
    --dry-run) DRY=1 ;;
    --with-launch-data) LAUNCH_DATA=1 ;;
    --no-verify) VERIFY=0 ;;
    --print-paths) PRINT_PATHS=1 ;;
    *) echo "未知参数 $a" >&2; exit 2 ;;
  esac
done

# `--print-paths`：只把解析出来的四个落点打成 JSON 然后退出，**什么都不做**。
# 它是给 `ops/test_F10.py` 用的 —— 「不设任何变量时发布方那台逐字节不变」这条断言
# 必须量**这个脚本自己解析出来的值**，而不是在测试里再抄一遍那四个字面量（抄的那份会漂）。
if [ "$PRINT_PATHS" = 1 ]; then
  printf '{"GB_ROOT":"%s","PY":"%s","F02":"%s","DEST":"%s","STAGE":"%s"}\n' \
    "$GB_ROOT" "$PY" "$F02" "$DEST" "$STAGE"
  exit 0
fi

# ── 第 0 步：解释器在不在。**不在就现在停**（N-851）───────────────────────
if [ ! -x "$PY" ]; then
  cat >&2 <<EOF
[红] 找不到可执行的 Python：$PY
     这个脚本要用**发布方环境那个解释器**跑三件事：staging 的答案面扫描（第 3 步）、
     逐字节复核（第 6 步）、以及把 h11 铺进 vendor/（第 1 步，N-856）。
     它默认取 \$GENEBENCH_ROOT/env/bin/python（现在 GENEBENCH_ROOT=$GB_ROOT）。
     三个可设的变量（都可以单独设）：
       GENEBENCH_ROOT        数据面根，默认 /data/shared/genebench
       GENEBENCH_PY          直接指定解释器，赢过上面那个
       GENEBENCH_EXEC_STAGE  staging 目录，默认 \$GENEBENCH_ROOT/scratch/exec_push
     另有 GENEBENCH_F02（默认 $F02）与 GENEBENCH_EXEC_DEST（默认 $DEST）。
     看这一次会解析成什么：ops/push_exec_to_f02.sh --print-paths
EOF
  exit 2
fi

# ── 白名单。加一个执行面要用的新模块 = 在这里加一行，别放宽规则。 ──────────
#: `arms.yaml` 是**臂注册表**（卡 4.1）：`bundle.py` 在 import 期读它，缺文件即 PackError。
#: 漏了它的表现不是「少个功能」，是**整棵 runner 在 f02 上 import 不了**，而 f01 侧一切正常。
GENETASK_FILES=(__init__.py bundle.py pin.py arms.yaml)
#: `genetask/arms/`：指令变体臂追加的固定题面文本（`arms.yaml` 的 `variant_text_file`）。
#: 目录整棵推 —— 加一个变体臂不该再来改这个脚本一次。
GENETASK_DIRS=(arms)
OPS_FILES=(guard_modes.py run_f02_a1.py api_usage.py)
#: 仓库里 `ops/` 是**命名空间包**（没有 `__init__.py`），f02 的 `exec/ops/` 里却有一个空的。
#: 它是当初铺 exec/ 时留下的，对面没有任何东西 `import ops`。这里**照原样补一个空文件**，
#: 只为让 `--delete` 不去动它 —— 同步的职责是让两边一致，不是顺手改对面的现状。
OPS_EMPTY_INIT=1
OPS_DIRS=(protocol)
#: runner/ 整棵推（它是执行面的本体，里面没有答案面）。
RUNNER_WHOLE=1
#: vendor/：**h11 现在随 exec 树船运**（N-856，2026-09-14）。在此之前它不在仓库里、
#: 也没有任何文档化步骤会铺它 —— f02 上那份是 2026-09-05 手工跑
#: `ops/run_f02_container_tests.sh` 留下的**遗留物**，于是一棵从零铺的执行面
#: **import 不了整棵 runner**（`runner_core` 在 import 期取 `egress_proxy.PLACEHOLDER_KEY`，
#: 而那个模块是模块级 `import h11`）。第 1 步用
#: `"$PY" -m runner.placement --stage-vendor` 从**发布方网关环境自己那份** h11 铺进 staging
#: （唯一实现在 `runner/placement.stage_vendor`，两条路径共用）。
#: 源目录仍然可能不在（别的 vendor 包）——那时仍**跳过、不 --delete**。
SYNC_DIRS=(genetask ops runner vendor)

#: 绝不许出现在 staging 里的路径段（红线 2）。
FORBIDDEN_SEGMENTS=(reference scorer runs_in gold memory_probe_answers solution)
#: 答案面文件名（与 runner/f02/answer_plane_guard.py::ANSWER_PLANE_NAMES 同一批）。
FORBIDDEN_NAMES=(canary.json scorer.yaml solve.py equivalence.md slots.json _ledger.jsonl)

cd "$REPO_ROOT"

echo "== 1/6 建 staging：$STAGE"
rm -rf "$STAGE"
mkdir -m 700 -p "$STAGE"

mkdir -m 700 -p "$STAGE/genetask"
for f in "${GENETASK_FILES[@]}"; do cp -p "genetask/$f" "$STAGE/genetask/"; done
for d in "${GENETASK_DIRS[@]:-}"; do
  [ -d "genetask/$d" ] || continue
  rsync -a --exclude='__pycache__/' --exclude='.pytest_cache/' "genetask/$d/" "$STAGE/genetask/$d/"
done

mkdir -m 700 -p "$STAGE/ops"
for f in "${OPS_FILES[@]}"; do cp -p "ops/$f" "$STAGE/ops/"; done
[ "$OPS_EMPTY_INIT" = 1 ] && : > "$STAGE/ops/__init__.py"
for d in "${OPS_DIRS[@]}"; do
  rsync -a --exclude='__pycache__/' --exclude='.pytest_cache/' "ops/$d/" "$STAGE/ops/$d/"
done

if [ "$RUNNER_WHOLE" = 1 ]; then
  rsync -a --exclude='__pycache__/' --exclude='.pytest_cache/' runner/ "$STAGE/runner/"
fi

# h11 → staging 的 vendor/（N-856）。**唯一实现**在 `runner/placement.stage_vendor`：
# 两条路径（这个脚本与单机落位）共用一份，而不是在这里再抄一张清单出来 ——
# 两份清单 = 两个真相，`OPS_FILES` 那一对已经为此付过一次代价。
"$PY" -m runner.placement --stage-vendor "$STAGE" | sed 's/^/   /'

if [ "$LAUNCH_DATA" = 1 ]; then
  for d in harnesses integrations; do
    [ -d "$d" ] || continue
    rsync -a --exclude='__pycache__/' --exclude='.pytest_cache/' "$d/" "$STAGE/$d/"
  done
  SYNC_DIRS+=(harnesses integrations)
  echo "   （--with-launch-data：harnesses/ 与 integrations/ 一并入列）"
fi

echo "== 2/6 断言：staging 里不含答案面的名字"
bad=0
for seg in "${FORBIDDEN_SEGMENTS[@]}"; do
  if find "$STAGE" -name "$seg" -print -quit | grep -q .; then
    echo "  !! staging 里出现禁段 '$seg'：" >&2
    find "$STAGE" -name "$seg" >&2
    bad=1
  fi
done
for n in "${FORBIDDEN_NAMES[@]}"; do
  if find "$STAGE" -name "$n" -print -quit | grep -q .; then
    echo "  !! staging 里出现答案面文件名 '$n'：" >&2
    find "$STAGE" -name "$n" >&2
    bad=1
  fi
done
[ "$bad" = 0 ] || { echo "同步中止：白名单漏了东西。**不要在这里加例外。**" >&2; exit 1; }
echo "   [绿] 禁段/禁名 各 0 命中"

# ── 口径说明（v1.0.16，卡 G2，用户裁定 N-627 走 B）────────────────────────
# 红线 2 改成了「**答案面永不挂进 agent 容器**」（判挂载面），不再是「不上执行面」（判机器）。
# **exec/ 树不挂进任务容器**：compose 只把 `<run_dir>/work` 挂到 `/task`，
# exec/ 是 runner 自己在宿主上跑的代码。所以对这个脚本而言，
# 容器边界口径**天然满足**，下面这道树扫描是**纯第二道** —— 保留它的理由有两条：
#   ① 私有通道的 gold 全量仍然不公开，它出现在 f02 上仍然是事故，
#      而那种事故不经过任何 compose，只有树口径看得见；
#   ② exec/ 里一旦混进 `solve.py`，下一个人很可能顺手把它挂进容器 ——
#      在东西落地那一刻拦住，比在它被挂载那一刻拦住早一步。
# **它没有被降级为可选**：命中仍然中止同步。
echo "== 3/6 用执行面自己那道门扫 staging（树口径，第二道；命中即停，不推）"
"$PY" - "$STAGE" <<'PYGUARD'
import importlib.util, pathlib, sys
repo = pathlib.Path.cwd()          # 脚本已 cd 到 REPO_ROOT
gp = repo / "runner" / "f02" / "answer_plane_guard.py"
spec = importlib.util.spec_from_file_location("_apg", gp)
m = importlib.util.module_from_spec(spec)
sys.modules["_apg"] = m          # dataclass 要在 sys.modules 里找得到自己的模块
spec.loader.exec_module(m)
hits = m.scan(sys.argv[1])
if hits:
    for h in hits:
        print(f"  [{h.kind}] {h.path}  {h.detail}", file=sys.stderr)
    print(f"\n**staging 里有 {len(hits)} 项答案面命中 —— 同步中止。**", file=sys.stderr)
    raise SystemExit(1)
print(f"   [绿] {sys.argv[1]}：answer_plane_guard.scan 0 命中（{sum(1 for _ in pathlib.Path(sys.argv[1]).rglob('*') if _.is_file())} 个文件）")
PYGUARD

# `$DEST` **根自己**要 0700（2026-09-14，卡 F10 在一棵全新执行面目录上量到）：
# 下面那句 `mkdir -m 700 -p "$DEST/$d"` 的 `-m` 只作用在**最后一段**，中间的 `$DEST`
# 吃 f02 的 umask（022）落成 0775 —— 而注入器 P0 的红线 5 守门审计的就是这棵树，
# 于是新铺的执行面**第一次真跑就红在自己的根上**。既有那棵 `exec/` 是 2026-09 手工
# `mkdir` 出来的 0700，所以这条在它上面永远不显形。`chmod go-rwx` 与
# `ops/guard_modes.harden()` 同语义（只去组/其它位，不动属主位）。
ssh "${SSH_OPTS[@]}" "$F02" "mkdir -m 700 -p $(printf %q "$DEST") && \
    chmod go-rwx $(printf %q "$DEST")"

echo "== 4/6 同步（每个目录各自 --delete，删除只发生在该目录内部）"
for d in "${SYNC_DIRS[@]}"; do
  if [ ! -d "$STAGE/$d" ]; then
    echo "   -- $d/：staging 里没有这个源 → **跳过，且不 --delete**"
    continue
  fi
  if [ "$DRY" = 1 ]; then
    echo "   -- $d/ （dry-run）"
    rsync -a -n -i --delete --no-perms --chmod=D700,F600 \
      -e "ssh ${SSH_OPTS[*]}" "$STAGE/$d/" "$F02:$DEST/$d/" | sed 's/^/      /'
  else
    ssh "${SSH_OPTS[@]}" "$F02" "mkdir -m 700 -p $(printf %q "$DEST/$d")"
    rsync -a --delete --no-perms --chmod=D700,F600 \
      -e "ssh ${SSH_OPTS[*]}" "$STAGE/$d/" "$F02:$DEST/$d/"
    echo "   -- $d/ 已同步"
  fi
done

if [ "$DRY" = 1 ]; then
  echo "== dry-run 到此为止（没有推任何东西）"
  exit 0
fi

echo "== 5/6 对面落地即扫（用 f02 上那份实现，不是这里再写一遍 grep）"
GUARD="$DEST/runner/f02/answer_plane_guard.py"
if ! ssh "${SSH_OPTS[@]}" "$F02" "test -f $GUARD"; then
  echo "推送后复核中止：对面没有 $GUARD —— **缺门不等于没问题**" >&2; exit 1
fi
if ! ssh "${SSH_OPTS[@]}" "$F02" "python3 $GUARD --root $(printf %q "$DEST") \
        --log /data/genebench_runner/logs/answer_plane.jsonl"; then
  echo "**落地扫描命中：对面出现答案面，已按 N-61 处置。立即复核闩与日志。**" >&2; exit 1
fi

if [ "$VERIFY" = 0 ]; then echo "== 6/6 跳过复核（--no-verify）"; exit 0; fi

echo "== 6/6 逐字节复核：两侧 command_for(\"Codex CLI\") 必须相同"
HERE="$("$PY" -c 'import sys; sys.path.insert(0,"."); from runner.c42 import harness_commands as H; print(H.command_for("Codex CLI"))')"
THERE="$(ssh "${SSH_OPTS[@]}" "$F02" "cd $(printf %q "$DEST") && PYTHONDONTWRITEBYTECODE=1 python3 -c \"from runner.c42 import harness_commands as H; print(H.command_for('Codex CLI'))\"")"
if [ "$HERE" != "$THERE" ]; then
  echo "!! 两侧不一致 —— 同步没落干净或对面有本地改动" >&2
  echo "   f01: ${HERE:0:160}…" >&2
  echo "   f02: ${THERE:0:160}…" >&2
  exit 1
fi
echo "   [绿] 两侧一致（${#HERE} 字节）"
echo "[绿] exec 树已同步到 $F02:$DEST"
