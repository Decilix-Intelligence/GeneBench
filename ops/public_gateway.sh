#!/bin/bash
# 公开通道网关实例的起停（卡 1.1-a）。
#
#   ops/public_gateway.sh start|stop|status
#   ops/public_gateway.sh run -- <命令>     # 拿网关锁 → 起 → 跑 → 停（跑批用这个）
#
# 生产网关（systemd 用户单元 genebench-gateway.service，private，18080）**不动**：
# 本脚本只管公开实例，端口默认 18081，绑定地址与生产同一条规则（显式地址，绝不 0.0.0.0）。
#
# 三条守门，都不是只写在注释里：
#   1. **端口不许等于生产端口** —— 手滑把 GENEBENCH_GATEWAY_PORT 设成 18080
#      的失败形态必须是「拒绝启动」，不能是「把生产网关挤掉」。
#   2. 起来之后**核 /healthz 的 channel 必须是 public** —— 起了个私有实例却以为
#      在跑公开通道，是这张卡最贵的一种错：数字看起来都对，只是来自另一份数据。
#   3. stop 之后**核端口真的释放了**，否则下一次 start 会得到一个假的「已在跑」。
#
# **macOS 上没有 `ss`，也没有 `setsid`**（卡 C2，2026-09-13）。三处用到它们的地方
# 都分了岔，选哪一支由 `command -v` 当场判 —— **不看操作系统名**，
# 因为装了 `ss` 的 Mac 与精简到没有 `ss` 的 Linux 两种都存在：
#   查端口在不在监听  ss -ltn  → lsof -nP -iTCP:PORT -sTCP:LISTEN → nc -z
#   查占端口的 pid    ss -ltnp → lsof … -t
#   脱离终端起进程    setsid nohup → nohup（脚本里 job control 本来就是关的，nohup 足够）
# 另：绑定地址取自 `genebench_config.py::GATEWAY_HOST`，那是个**常量，没有环境变量可以覆盖**
# （端口有 GENEBENCH_GATEWAY_PORT，地址没有）。换机器要先改它，见手册 §1.3。
set -u

GB="${GENEBENCH_ROOT:-/data/shared/genebench}"
REPO="$GB/repo"
PY="$GB/env/bin/python"
HOST="$(cd "$REPO" && "$PY" -c 'import genebench_config as c; print(c.GATEWAY_HOST)')"
PROD_PORT="$(cd "$REPO" && "$PY" -c 'import genebench_config as c; print(c.GATEWAY_PORT)')"
PORT="${GENEBENCH_GATEWAY_PORT:-$(cd "$REPO" && "$PY" -c 'import genebench_config as c; print(c.GATEWAY_PUBLIC_PORT)')}"
PIDFILE="$GB/logs/public_gateway.pid"
LOGFILE="$GB/logs/public_gateway_stdout.log"
BASE="http://$HOST:$PORT"

die() { echo "[红] $*" >&2; exit 2; }

# ---- Linux / macOS 分岔（卡 C2，2026-09-13） ----------------------------
have() { command -v "$1" > /dev/null 2>&1; }

port_busy() {
  if have ss; then
    ss -ltn "sport = :$PORT" 2>/dev/null | grep -q LISTEN
  elif have lsof; then
    lsof -nP -iTCP:"$PORT" -sTCP:LISTEN > /dev/null 2>&1
  elif have nc; then
    nc -z "$HOST" "$PORT" > /dev/null 2>&1
  else
    die "既没有 ss，也没有 lsof / nc —— 查不了端口占用。这个脚本的三条守门有两条要靠它，不敢往下走。"
  fi
}

#: 占着 $PORT 的那个进程的 pid（查不到就回空串）。
listener_pid() {
  if have ss; then
    ss -ltnp "sport = :$PORT" 2>/dev/null | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2
  elif have lsof; then
    lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null | head -1
  fi
}

#: `status` 打给人看的那一行。
listener_line() {
  if have ss; then
    ss -ltnp "sport = :$PORT" 2>/dev/null | tail -1
  elif have lsof; then
    lsof -nP -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | tail -1
  else
    echo "（这台机器上没有 ss / lsof，只知道端口被占着）"
  fi
}

assert_not_prod_port() {
  if [ "$PORT" = "$PROD_PORT" ]; then
    die "GENEBENCH_GATEWAY_PORT=$PORT 就是生产网关的端口。公开实例不许起在这个端口上。"
  fi
}

do_start() {
  assert_not_prod_port
  if port_busy; then
    echo "[黄] $HOST:$PORT 已经在监听 —— 当作已启动。要重起先 stop"
    do_status; return 0
  fi
  mkdir -p "$GB/logs"; chmod 700 "$GB/logs" 2>/dev/null
  cd "$REPO" || die "进不去 $REPO"
  # macOS 的默认硬上限常常比 8192 低，调不上去就算了 —— 这一条是给 gold 全表扫准备的，
  # 起网关本身用不到那么多 fd，不该因为它起不来。
  ulimit -n 8192 2>/dev/null || echo "[黄] ulimit -n 8192 没调上去（当前 $(ulimit -n)）——起网关够用，跑 gold 之前要自己抬"
  umask 0077
  # setsid 是 Linux 的；macOS 没有。脚本里 job control 本来就是关的，nohup 足以脱离终端。
  if have setsid; then
    GENEBENCH_CHANNEL=public GENEBENCH_GATEWAY_PORT="$PORT" \
    GENEBENCH_GATEWAY_BACKEND=snapshot PYTHONUNBUFFERED=1 \
      setsid nohup "$PY" -m gateway.run --workers 1 > "$LOGFILE" 2>&1 &
  else
    GENEBENCH_CHANNEL=public GENEBENCH_GATEWAY_PORT="$PORT" \
    GENEBENCH_GATEWAY_BACKEND=snapshot PYTHONUNBUFFERED=1 \
      nohup "$PY" -m gateway.run --workers 1 > "$LOGFILE" 2>&1 &
  fi
  echo $! > "$PIDFILE"
  # **等 180 秒不是保守，是实测**：网关 import 链（fastapi + pandas + pyarrow +
  # duckdb + snapshots.*）在 f01 上要 41 秒才开始监听。等 40 秒的第一版
  # 每次都在「起来之前」就去 curl，然后把「没起来」记成「起失败了」。
  local t0; t0=$(date +%s)
  for _ in $(seq 1 180); do
    if curl -sS --max-time 3 "$BASE/healthz" > /dev/null 2>&1; then break; fi
    kill -0 "$(cat "$PIDFILE")" 2>/dev/null || { tail -20 "$LOGFILE"; die "进程起来就退了"; }
    sleep 1
  done
  echo "（起来用了 $(( $(date +%s) - t0 )) 秒）"
  local health
  health="$(curl -sS --max-time 5 "$BASE/healthz" 2>/dev/null)" || {
    echo "--- $LOGFILE 末尾 ---"; tail -20 "$LOGFILE"; die "起来了但 /healthz 打不通"; }
  case "$health" in
    *'"channel":"public"'*|*'"channel": "public"'*) : ;;
    *) echo "$health"; do_stop; die "起的不是公开通道实例（/healthz 的 channel 不是 public）" ;;
  esac
  echo "[绿] 公开网关已起：$BASE （pid $(cat "$PIDFILE")）"
  echo "$health"
}

do_stop() {
  local pid=""
  [ -f "$PIDFILE" ] && pid="$(cat "$PIDFILE")"
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null
  else
    pid="$(listener_pid)"
    [ -n "$pid" ] && kill "$pid" 2>/dev/null
  fi
  for _ in $(seq 1 20); do port_busy || break; sleep 1; done
  if port_busy; then
    [ -n "$pid" ] && kill -9 "$pid" 2>/dev/null
    for _ in $(seq 1 10); do port_busy || break; sleep 1; done
  fi
  rm -f "$PIDFILE"
  if port_busy; then die "$HOST:$PORT 仍在监听 —— 没停干净"; fi
  echo "[绿] 公开网关已停，$PORT 已释放"
}

do_status() {
  echo "channel=public host=$HOST port=$PORT pidfile=$PIDFILE"
  if port_busy; then
    echo "监听中：$(listener_line)"
    curl -sS --max-time 5 "$BASE/healthz" || echo "（/healthz 打不通）"
    echo
  else
    echo "未在监听"
  fi
}

do_run() {
  # 跑批：拿网关锁 → 起 → 跑命令 → 停（不管命令成败都停）。
  # 锁是 N-125 的那把：跑批与真跑不许同时打网关。
  [ "$#" -gt 0 ] || die "run 后面要跟命令：ops/public_gateway.sh run -- <cmd>"
  cd "$REPO" || die "进不去 $REPO"
  # **不要在这里再塞一个 `--`**：`ops/gateway_lock.py` 走 argparse，
  # 命令里的第二个 `--` 会被它一并吃掉，于是内层的 `shift` 把真正的命令
  # 移没了 —— 表现是「网关起了又停了，命令一声不响地没跑」（实测踩过一次）。
  exec "$PY" ops/gateway_lock.py --what "public_gateway.sh run: $*" -- \
    bash -c 'set -e; "$0" start >&2; trap "\"$0\" stop >&2" EXIT; "$@"' \
    "$0" "$@"
}

case "${1:-}" in
  start) do_start ;;
  stop) do_stop ;;
  status) do_status ;;
  run) shift; [ "${1:-}" = "--" ] && shift; do_run "$@" ;;
  *) echo "用法：$0 start|stop|status|run -- <命令>" >&2; exit 2 ;;
esac
