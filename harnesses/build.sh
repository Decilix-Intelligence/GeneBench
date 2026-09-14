#!/usr/bin/env sh
# harnesses/build.sh <id> [--tag NAME] [--dry-run] [--force] [--no-base-build]
#
# 把 `harnesses/<id>/Dockerfile` 构建成镜像并打印 digest。
# 阶段三 3.1，2026-09-06；2026-09-13 卡 A2 补「缺基座就自己构」与多架构。
#
# 为什么要有这个脚本：在它之前，镜像的来历是一份**不在仓库里**的构建脚本 ——
# 三个 harness 的 Dockerfile 由它用 heredoc 现写现构建。于是「仓库里的
# `harnesses/<id>/Dockerfile`」与「真正构建出镜像的那份」之间没有任何机器判据，
# 只有「我抄回来时是一样的」这句话。本脚本把构建源换成**仓库里的那份**：
# 构建读的和复核读的是同一个文件。
#
# 为什么 tag 从 `launch.json` 的 `image` 取，而不是拼 `gb-<id>-u:r1`：
# 真正决定容器起哪个镜像的是 `launch.json` 的 `image` 字段（注入器从那里读）。
# 拼名字会在 codex（`gb-cx-u:r1`，历史短名）这种地方对不上 —— 而对不上的表现是
# 「构建成功了，跑的还是旧镜像」。让构建与启动读同一个字段，这个坑就不存在。
#
# 在哪跑：**任何有 docker 的机器**。发布方内网是在执行面 f02 上跑（数据面 f01
# 没有容器运行时）；外部用户在自己的机器上跑。两边读的是同一棵树里的同一份文件。
#
# 没有执行位：同步到执行面的 rsync 用 `--chmod=D700,F600`（红线 5 的权限口径），
# 落地一律 0600。所以一律用 `sh harnesses/build.sh …` 调，不要指望 `./`。
#
# 基座：`FROM` 只能是统一基座 `gb-base:bookworm-r1`，本脚本在构建前显式核这一条。
# **基座不在本机时，本脚本会用仓库里的 `build/base/` 先把它构出来**（2026-09-13 之前
# 这里只会打印一句「去发布方某台机器上构」，而那是外部用户没有的路径 —— Mac 外部验收
# 就卡在这一条）。不想让它自动构 → `--no-base-build`。
#
# shell 兼容：本脚本在 Linux 的 dash、macOS 的 /bin/sh（bash 3.2 sh 模式）与 zsh
# 下都要能跑。所以：不用 `sed -i` / `readlink -f` / `mapfile` 这些 GNU 或 bash 专有的东西；
# **所有变量插值一律写成 `${VAR}` 带花括号** —— 不带花括号时，
# 「变量名后面紧跟中文标点（句号、全角括号之类）」这种写法会被 macOS 的 bash 3.2
# 在 UTF-8 locale 下把标点的头一个字节吃进变量名，于是 `set -u` 报
# `BASE_IMAGE?: unbound variable` —— 用户看到的是这句，而不是「你缺基座」。
# 实测（2026-09-13，darwin 24.6.0）：同一行 `LC_ALL=C` 下正常、
# `LC_ALL=en_US.UTF-8` 下必炸；zsh 两种 locale 都正常。也就是说这是个
# **只在某些 locale 下发作**的 bug，最难被发布方自己踩到。见 N-750。
# 回归锁在 `ops/test_A2.py::test_build_sh_has_no_bare_var_before_nonascii`。
set -eu

umask 022                       # 红线 B7：别在共享树上留 0775
export PYTHONDONTWRITEBYTECODE=1

BASE_IMAGE="gb-base:bookworm-r1"
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${HERE}/.." && pwd)"
#: 基座的构建上下文。默认是仓库里的 `build/base/`；只同步了执行树、手里没有
#: `build/` 的机器可以用 `GB_BASE_CONTEXT` 指过去。
BASE_CONTEXT="${GB_BASE_CONTEXT:-${REPO_ROOT}/build/base}"
#: 构基座时要不要显式指定平台（例：`linux/arm64`）。留空 = 跟随本机架构。
BASE_PLATFORM="${GB_BASE_PLATFORM:-}"

usage() {
  cat >&2 <<'U'
用法：sh harnesses/build.sh <id> [--tag NAME] [--dry-run] [--force] [--no-base-build]

  <id>             harnesses/<id>/ 的目录名（= harness id）
  --tag NAME       覆盖镜像 tag（默认取 harnesses/<id>/launch.json 的 image 字段）
  --dry-run        只做前置核查并打印将要执行的 docker 命令，不构建（基座也不构）
  --force          目标 tag 已存在时也构建（默认拒绝：重打一个被 --digest 钉住的 tag
                   会让所有已出集 bundle 的通行证对不上，而表现是「跑起来 ok」）
  --no-base-build  缺统一基座时不自动构建，直接报错退出

环境变量：
  GB_BASE_CONTEXT   基座的构建上下文目录（默认 <仓库>/build/base）
  GB_BASE_PLATFORM  构基座时传给 docker build 的 --platform（默认跟随本机架构）

示例：
  sh harnesses/build.sh codex --dry-run
  sh harnesses/build.sh codex
U
  exit 2
}

ID=""; TAG=""; DRY=0; FORCE=0; NO_BASE_BUILD=0
while [ $# -gt 0 ]; do
  case "$1" in
    --tag) shift; [ $# -gt 0 ] || usage; TAG="$1" ;;
    --dry-run) DRY=1 ;;
    --force) FORCE=1 ;;
    --no-base-build) NO_BASE_BUILD=1 ;;
    -h|--help) usage ;;
    -*) echo "未知参数 $1" >&2; usage ;;
    *) [ -z "${ID}" ] || { echo "只接受一个 <id>（多给了 $1）" >&2; usage; }; ID="$1" ;;
  esac
  shift
done
[ -n "${ID}" ] || usage

DIR="${HERE}/${ID}"
[ -d "${DIR}" ] || { echo "!! 没有 ${DIR} —— <id> 就是 harnesses/ 下的目录名" >&2; exit 1; }
for f in Dockerfile launch.json config.yaml README.md; do
  [ -f "${DIR}/${f}" ] || { echo "!! 缺 ${DIR}/${f} —— 一个 harness 要四件文件，见 harnesses/README.md" >&2; exit 1; }
done

# ── ⓪ docker 在不在（这一句要在任何 docker 调用之前，否则用户看到的是一串
#      `command not found` 而不是「你还没装/没起 docker」） ───────────────────
command -v docker >/dev/null 2>&1 || {
  echo "!! 这台机器上没有 docker —— 本脚本只做构建，构建必须有容器运行时。" >&2
  echo "   装好 Docker（Linux: docker engine；macOS/Windows: Docker Desktop）并确认" >&2
  echo "   \`docker info\` 能出结果之后再跑。" >&2
  exit 1
}
docker info >/dev/null 2>&1 || {
  echo "!! docker 命令在，但连不上 daemon（\`docker info\` 失败）。" >&2
  echo "   Docker Desktop 没启动、或当前用户不在 docker 组时就是这个样子。" >&2
  exit 1
}

# ── ① 基座在不在：**先判、先记住**，再做别的 ───────────────────────────────
# 这一步刻意排在所有 `${BASE_IMAGE}` 插值与所有耗时动作之前：缺基座是最常见的
# 第一次失败，而它此前的表现是一句 `unbound variable`（见文件头的 shell 兼容说明）。
if docker image inspect "${BASE_IMAGE}" >/dev/null 2>&1; then
  BASE_PRESENT=1
else
  BASE_PRESENT=0
fi

# ── ② Dockerfile 的第一条**有效**指令必须是 FROM 统一基座（N-62） ──────────
# 顶部允许有注释（W-0 要求 Dockerfile 顶部注明镜像名与 digest 的来历），
# 所以这里看的是第一条非空非注释行，不是字面第一行。
FIRST="$(grep -v '^[[:space:]]*#' "${DIR}/Dockerfile" | grep -v '^[[:space:]]*$' | head -1)"
case "${FIRST}" in
  "FROM ${BASE_IMAGE}") : ;;
  *) echo "!! ${DIR}/Dockerfile 的第一条指令是 [${FIRST}]，必须是 [FROM ${BASE_IMAGE}]" >&2
     echo "   统一基座是 N-62 的裁定：三个 harness 各用各的官方基座时，pandas/pyarrow 版本差异" >&2
     echo "   会混进主表的「harness 差异」那一列，而 S2/S3/S7 的产出恰恰是数值。" >&2
     exit 1 ;;
esac

# 多条 FROM 会让注入器的 P4c 当场红（「Dockerfile 有 N 条 FROM」），在这里先说。
NFROM="$(grep -c '^[[:space:]]*FROM[[:space:]]' "${DIR}/Dockerfile" || true)"
[ "${NFROM}" = "1" ] || { echo "!! ${DIR}/Dockerfile 有 ${NFROM} 条 FROM —— 注入器 P4c 只允许 1 条" >&2; exit 1; }

# ── ③ tag：默认从 launch.json 的 image 取（构建与启动读同一个字段） ─────────
if [ -z "${TAG}" ]; then
  TAG="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["image"])' "${DIR}/launch.json")" \
    || { echo "!! 读不出 ${DIR}/launch.json 的 image 字段" >&2; exit 1; }
fi
[ -n "${TAG}" ] || { echo "!! launch.json 的 image 是空的" >&2; exit 1; }

# ── ④ 缺基座 → 用仓库里的 build/base/ 先把它构出来 ─────────────────────────
if [ "${BASE_PRESENT}" = 0 ]; then
  echo "== 基座       : 本机没有 ${BASE_IMAGE}"
  if [ ! -f "${BASE_CONTEXT}/Dockerfile" ]; then
    echo "!! 缺基座镜像 ${BASE_IMAGE}，而基座的构建上下文也不在：${BASE_CONTEXT}/Dockerfile 不存在。" >&2
    echo "   完整仓库里它在 build/base/。只同步了执行树（harnesses/ 等几个目录）的机器上没有这一份 ——" >&2
    echo "   用 GB_BASE_CONTEXT=<build/base 的路径> 指过去，或者换到完整仓库里跑本脚本。" >&2
    echo "   第三条路：在别的机器上构好基座，docker save / docker load 搬过来。" >&2
    exit 1
  fi
  if [ "${NO_BASE_BUILD}" = 1 ]; then
    echo "!! 缺基座镜像 ${BASE_IMAGE}，而 --no-base-build 让本脚本不要自己构。" >&2
    echo "   自己构一次：sh -c 'docker build -t ${BASE_IMAGE} \"${BASE_CONTEXT}\"'" >&2
    exit 1
  fi
  if [ "${DRY}" = 1 ]; then
    echo "== 会先构基座 : docker build -t ${BASE_IMAGE} ${BASE_CONTEXT}"
    echo "              （dry-run 不真构；基座要几分钟，见 build/base/README.md）"
  else
    echo "== 先构基座   : docker build -t ${BASE_IMAGE} ${BASE_CONTEXT}"
    echo "              这一步要能访问 docker.io（FROM 的 python 基础镜像）、nodejs.org、"
    echo "              deb.debian.org 与 pypi.org；几分钟，见 build/base/README.md。"
    if [ -n "${BASE_PLATFORM}" ]; then
      docker build --platform "${BASE_PLATFORM}" -t "${BASE_IMAGE}" "${BASE_CONTEXT}" 2>&1 | tail -8
    else
      docker build -t "${BASE_IMAGE}" "${BASE_CONTEXT}" 2>&1 | tail -8
    fi
    docker image inspect "${BASE_IMAGE}" >/dev/null 2>&1 || {
      echo "!! 基座构建跑完了，但 ${BASE_IMAGE} 还是不在 —— 上面几行就是 docker 的原话。" >&2
      exit 1
    }
    echo "== 基座构建完成：${BASE_IMAGE}（$(docker image inspect --format '{{.Id}}' "${BASE_IMAGE}")）"
    BASE_PRESENT=1
  fi
fi

# ── ⑤ 目标 tag 已存在 = 默认拒绝 ────────────────────────────────────────────
# `--dry-run` 只**说**这件事、不拦：dry-run 的用途正是「我还没构建，先看看会发生什么」，
# 在那一步就退 1 会让人以为前置核查没过。
if docker image inspect "${TAG}" >/dev/null 2>&1 && [ "${FORCE}" = 0 ] && [ "${DRY}" = 1 ]; then
  echo "== 注意     ：tag ${TAG} 已存在（$(docker image inspect --format '{{.Id}}' "${TAG}")）"
  echo "              真构建时会被拒绝 —— 换 tag，或确认后加 --force。"
elif docker image inspect "${TAG}" >/dev/null 2>&1 && [ "${FORCE}" = 0 ]; then
  OLD="$(docker image inspect --format '{{.Id}}' "${TAG}")"
  echo "!! tag ${TAG} 已存在（${OLD}）。重打它会让**已出集 bundle 的 --digest 全部对不上**，" >&2
  echo "   而对不上的表现是通行证核对红、或者更糟：核对绿而跑的是另一个镜像。" >&2
  echo "   要新建一个版本 → 换 tag（改 launch.json 的 image，或 --tag）；" >&2
  echo "   确认要覆盖 → 加 --force，并把新 digest 同步到所有引用它的 --digest。" >&2
  exit 1
fi

echo "== harness   : ${ID}"
echo "== 上下文     : ${DIR}"
if [ "${BASE_PRESENT}" = 1 ]; then
  echo "== 基座       : ${BASE_IMAGE}（$(docker image inspect --format '{{.Id}}' "${BASE_IMAGE}")）"
else
  echo "== 基座       : ${BASE_IMAGE}（还不在本机 —— dry-run 没有替你构）"
fi
echo "== 目标 tag   : ${TAG}"
echo "== docker build -t ${TAG} ${DIR}"

if [ "${DRY}" = 1 ]; then
  echo "== dry-run 到此为止（前置核查全绿，没有构建）"
  exit 0
fi

docker build -t "${TAG}" "${DIR}" 2>&1 | tail -8

DIGEST="$(docker image inspect --format '{{.Id}}' "${TAG}")"
echo
echo "== 构建完成"
echo "   镜像 ${TAG}"
echo "   digest ${DIGEST}"
echo
echo "接下来两件事（漏掉哪件都表现为「跑起来 ok」）："
echo "  1) 把 digest 写进 harnesses/${ID}/Dockerfile 顶部的来历注释；"
echo "  2) 出集时用它：ops/export_bundle.py <task> --digest ${DIGEST} --image ${TAG%%:*}"
