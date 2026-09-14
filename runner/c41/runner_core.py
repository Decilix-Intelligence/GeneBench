# -*- coding: utf-8 -*-
"""卡 4.1：任务容器编排、compose lint、遥测入库。

    python3 runner_core.py hello --arm strict --task-id T-0001

**隔离由拓扑保证，不由规则保证**（见 `ops/specs/card_4.1_container_isolation.md`）：

* 任务容器只接 ``gb_task``（``internal: true``）—— **物理上没有默认路由**；
* 代理边车同时接 ``gb_task`` 与 ``gb_egress``，是**唯一**出口；
* 因此「默认拒绝」不是一条可被 ``iptables -F`` 掉的规则，而是网络拓扑本身。

:func:`lint_compose` 是这套拓扑的**守门**：拓扑保证只在 compose 长成那个样子时成立，
所以「compose 长成那个样子」必须是可测的，不能只是写在笔记里的提醒。
"""
from __future__ import annotations

import argparse
import json
import os
import ipaddress
import re
import sqlite3
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

# 这个模块有**两种**被 import 的方式，都得活：
# ① 测试与 f02 把 `runner/c41` 直接放进 sys.path（`import runner_core`）；
# ② 仓库里按包 import（`runner.c41.runner_core`）。
# 第二次 import 失败会照常抛 —— 不吞「文件真的没了」这种错。
try:
    from subnets import RESERVED as RESERVED_SUBNETS, overlaps_any        # IN-2
except ModuleNotFoundError:
    from runner.c41.subnets import RESERVED as RESERVED_SUBNETS, overlaps_any

#: 占位 key 的**单一定义**在边车里 —— compose 里再写一遍字面量，
#: 两处就会漂，而漂的表现是「agent 拿到的占位串与边车认的那个不同」→
#: 每次调用都被判 `foreign_credential`，看起来像 agent 自带了凭据。
try:
    from .egress_proxy import PLACEHOLDER_KEY as EP_PLACEHOLDER_KEY
except ImportError:      # 边车作为单文件挂进容器时的导入形态
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).parent))
    from egress_proxy import PLACEHOLDER_KEY as EP_PLACEHOLDER_KEY

PLACEHOLDER_KEY_LITERAL = EP_PLACEHOLDER_KEY

def _dual_runner_root() -> str:
    """双机形态（发布方执行面）的根。**函数内 import** —— 单机形态设了
    `GENEBENCH_RUNNER_ROOT` 之后根本走不到这里（卡 A9：单机路径上 `/data` 字面量零次）。"""
    from runner.placement_dual import RUNNER_ROOT_DEFAULT
    return RUNNER_ROOT_DEFAULT


#: 执行面的根。**`GENEBENCH_RUNNER_ROOT` 赢过默认**（卡 A9，N-841）：单机形态下
#: `ops/run_joblist.py` 会把它钉进环境，于是 `task_dir()` / `db()` / `format_compose`
#: 的三处默认与落位用的是**同一个根**。不设它时取值与本改动之前**逐字相同**。
ROOT = Path((os.environ.get("GENEBENCH_RUNNER_ROOT") or "").strip() or _dual_runner_root())
#: 数据网关的**默认**地址（私有通道的生产实例）。这一行的值逐字未变 ——
#: 不设 `GENEBENCH_GATEWAY_ADDR` 时，渲染出来的 compose 与本改动之前逐字节相同。
GATEWAY_DEFAULT = "192.168.1.48:18080"

#: 覆盖它的环境变量（卡 6.5）。**只认这一个**，且只在**注入那一刻**读。
#: 为什么需要它：边车的 `--gateway` 是**上游**地址，而公开通道的网关实例起在 18081
#: （`genebench_config.GATEWAY_PUBLIC_PORT`）。写死 18080 的话，`GENEBENCH_CHANNEL=public`
#: 只改了数据面这一侧 —— f02 上的容器照样打私有网关，**报告头写着 public、数字来自 private**，
#: 而没有任何一条判据会拦它（同族的错见 N-304 / `ops/run_controls.py::assert_channel_matches`）。
GATEWAY_ADDR_ENV = "GENEBENCH_GATEWAY_ADDR"

#: 只收 `IPv4:端口`。**不收主机名**：容器网里 DNS 由 compose 提供，`gateway` 这个名字
#: 已经是边车自己；写个别的名字进来会得到「边车把请求转给它自己」的死循环。
_GATEWAY_ADDR_RE = re.compile(r"^(\d{1,3}(?:\.\d{1,3}){3}):(\d{1,5})$")

#: 明确拒掉的上游地址。`127.0.0.1` / `localhost` 在**边车容器里**指向边车自己，
#: `0.0.0.0` 不是一个可连的目标 —— 三者的失败形态都是「连上了自己 / 连不上」而不是
#: 「地址写错了」，所以拦在注入之前。
_GATEWAY_ADDR_DENY = ("0.0.0.0", "127.0.0.1", "localhost", "::1")


def gateway_addr() -> str:
    """本次注入要写进 compose 的**数据网关上游**地址（`host:port`）。

    不设环境变量 → `GATEWAY_DEFAULT`，与本函数引入之前逐字相同。
    设了就校验形状再用；形状不对**当场抛**，不静默回落到默认值 ——
    回落的表现是「以为在跑公开通道，其实打的是私有网关」，那正是要拦的那件事。
    """
    raw = os.environ.get(GATEWAY_ADDR_ENV, "").strip()
    if not raw:
        return GATEWAY_DEFAULT
    m = _GATEWAY_ADDR_RE.match(raw)
    if not m:
        raise ValueError(
            f"{GATEWAY_ADDR_ENV}={raw!r} 形状不对 —— 要 `IPv4:端口`（例 192.168.1.48:18081）。"
            f"不收主机名：容器网里 `gateway` 这个名字是边车自己。")
    host, port = m.group(1), int(m.group(2))
    if any(int(o) > 255 for o in host.split(".")):
        raise ValueError(f"{GATEWAY_ADDR_ENV}={raw!r} 不是合法 IPv4")
    if not 1 <= port <= 65535:
        raise ValueError(f"{GATEWAY_ADDR_ENV}={raw!r} 的端口不在 1..65535")
    if host in _GATEWAY_ADDR_DENY:
        raise ValueError(
            f"{GATEWAY_ADDR_ENV}={raw!r}：{host} 在**边车容器里**指向边车自己，"
            f"不是数据面那台机器。写数据面的 LAN 地址。")
    return f"{host}:{port}"


def __getattr__(name: str):
    """`GATEWAY` 保留成模块属性（PEP 562）——既有调用方
    （`runner/inject.py`、`ops/test_inject.py`）一个字都不用改，
    但它现在**按环境现算**而不是 import 期定死。"""
    if name == "GATEWAY":
        return gateway_addr()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
LAN = "192.168.1.219"                       # f02 的 LAN 地址，端口映射必须显式绑它
#: **仅作缺省**（单跑、冒烟）。真运行由 `subnets.allocate()` 按运行分配（IN-1）——
#: 常量网段两臂并发必然抢同一个网。
TASK_SUBNET = "172.31.240.0/24"
EGRESS_SUBNET = "172.31.241.0/24"

TASK_SERVICE = "task"                       # 被测 agent 跑在这里，**不可信方**
PROXY_SERVICE = "gateway"                   # 代理边车，唯一出口
TASK_NETWORK = "gb_task"                    # internal: true
EGRESS_NETWORK = "gb_egress"                # 只有代理边车可以接

# --------------------------------------------------------------- 双臂题面

HELLO_TASK = {
    "id": "hello-task",
    "stage": "S1",
    "goal": "经数据网关取 600519.SH 在 2026-07-01 至 2026-07-10 的日线，把返回的行数写进 /task/result.json",
    "arms": {
        # 两臂**语义等价**，差别只在「说得多细」——卡 4.3 的等价性由签字人抽查
        "strict": (
            "任务：经数据网关取一段日线并报告行数。\n"
            "网关地址：http://gateway:18080\n"
            "端点：GET /bars\n"
            "参数：as_of=2026-07-31、code=600519.SH、start_date=2026-07-01、end_date=2026-07-10\n"
            "请求头：x-genebench-config-id 与 x-genebench-task-id 取环境变量 "
            "GENEBENCH_CONFIG_ID / GENEBENCH_TASK_ID\n"
            "产出：把返回 JSON 里 rows 字段的值写成 {\"rows\": <整数>} 存到 /task/result.json\n"
        ),
        "open": (
            "任务：查出贵州茅台（600519.SH）在 2026 年 7 月 1 日到 7 月 10 日之间有多少个交易日的日线数据，"
            "把这个条数写进 /task/result.json，格式 {\"rows\": <整数>}。\n"
            "数据只能经本环境提供的数据网关获取，网关在 http://gateway:18080。\n"
            "本次评测的 as_of 是 2026-07-31。\n"
        ),
    },
    "check": {"rows": 8},   # 2026-07-01..07-10 之间的 SSE 交易日数，由验收现算核对
}

# --------------------------------------------------------------- compose

#: `{task_id}` 必须是**真 task_id**，不是 run_id —— 它进 `x-genebench-task-id` 头，
#: 而网关 access_log 的切片键、scorer 的切片、N-36 的 config_id 核对全挂在这个值上。
#: 项目名与 run 目录用 `{project}` / `{run_id}` 这两个独立占位符（卡 4.3 §6.5）。
COMPOSE_TMPL = """name: {project}
networks:
  gb_task:
    internal: true
    ipam:
      config:
        - subnet: {task_subnet}
  gb_egress:
    ipam:
      config:
        - subnet: {egress_subnet}
services:
  gateway:
    image: python:3.11-alpine
    user: "{run_uid}:{run_gid}"
    cap_drop: [ALL]
    security_opt: ["no-new-privileges:true"]
    networks: [gb_task, gb_egress]
    volumes:
      - {proxy_py}:/opt/egress_proxy.py:ro
      # 边车用**网关那一份 h11** 解析请求头（裁定 2026-09-05）。挂进来而不是
      # 运行期 `pip install` —— 后者被卡 4.1 §3.4 明令禁止（要把包仓库放进出向白名单，
      # 而那正是白名单膨胀的唯一真实来源）。h11 是纯 Python，挂载即可用。
      - {h11_dir}:/opt/h11:ro
      - {logdir}:/var/log/gb
    environment:
      GENEBENCH_TASK_ID: "{task_id}"
      GENEBENCH_RUN_ID: "{run_id}"
      GENEBENCH_CONFIG_ID: "{config_id}"
      GENEBENCH_ARM: "{arm}"
      # **真 key 只出现在这里**（边车服务），任务容器的 environment 里没有它。
      # 值由 runner 从 ~/.config/genebench/secrets.env 读入后经进程环境传给 compose，
      # **不落 compose.yml、不落 run dir**（compose 里写的是 ${{...}} 引用）。
      GENEBENCH_MODEL_API_KEY: "${{GENEBENCH_MODEL_API_KEY}}"
      # 让 `import h11` 找到挂进来的那份（/opt/h11）。
      PYTHONPATH: "/opt"
    command: >
      python3 /opt/egress_proxy.py --gateway {gateway}
      --log /var/log/gb/egress.jsonl
      --llm-log /var/log/gb/llm_log.jsonl
      --model-port {model_port} --model-upstream {model_upstream}
      --max-calls {max_calls} --max-tokens {max_tokens}
  task:
    image: {image}
    # N-48（2026-09-04 裁定「现在修」）：不加这三行的后果实测过 ——
    # 上一轮真跑的 work/artifact.json 与 log/egress.jsonl 都是 `root:root`，
    # harness（非 root）连删都删不掉；而被测 agent 是**不可信方**，它以 root
    # 往宿主 bind mount 里写，可以造出 harness 删不掉、甚至读不到的目录
    # （chmod 000 的 root 目录会让 verify_run_dir_unchanged 表现为「文件消失」
    # 而不是「越权」）。同族实证：root 容器写一次共享挂载，搞坏了 19 个爬虫。
    user: "{run_uid}:{run_gid}"
    cap_drop: [ALL]
    security_opt: ["no-new-privileges:true"]
    networks: [gb_task]
    depends_on: [gateway]
    working_dir: /task
    volumes:
      - {workdir}:/task
    environment:
      GENEBENCH_TASK_ID: "{task_id}"
      GENEBENCH_RUN_ID: "{run_id}"
      GENEBENCH_CONFIG_ID: "{config_id}"
      GENEBENCH_ARM: "{arm}"
      GENEBENCH_GATEWAY: "http://gateway:18080"
      # 模型走**边车的反向代理**（裁定 (a)）。任务容器里只有占位 key ——
      # 边车在转发时把它换成真 key，于是 agent 拿不到真 key，
      # 而 usage / Steps / 预算闸全部有落点。
      OPENAI_BASE_URL: "http://gateway:{model_port}/v1"
      OPENAI_API_BASE: "http://gateway:{model_port}/v1"
      LLM_BASE_URL: "http://gateway:{model_port}/v1"
      OPENAI_API_KEY: "{placeholder_key}"
      LLM_API_KEY: "{placeholder_key}"
      HTTP_PROXY: "http://gateway:3128"
      HTTPS_PROXY: "http://gateway:3128"
      NO_PROXY: "gateway,localhost,127.0.0.1"
      no_proxy: "gateway,localhost,127.0.0.1"
    command: {command}
"""


def task_dir(task_id: str) -> Path:
    return ROOT / "tasks" / task_id


#: 模型反向代理在容器网里的端口。与网关端口分开 —— 一个端口两种语义
#: （数据网关 vs 模型代理）会让日志与白名单都对不上号。
MODEL_PORT: int = 8081


def format_compose(**kw) -> str:
    """**唯一的 compose 渲染出口。**

    先前三处各自 `COMPOSE_TMPL.format(...)`（`render_compose`、`inject.py`、
    以及测试夹具）—— 加 N-48 的 `{run_uid}` 两个占位符时，三处里只有一处跟着改，
    另外两处当场 `KeyError`。这次 KeyError 是**响的**（好事），
    但下一个新占位符未必这么幸运：漏一个默认值就是静默漂开。
    所以收敛成一个函数，uid/gid 在这里补默认。
    """
    kw.setdefault("run_uid", runner_ids()[0])
    kw.setdefault("run_gid", runner_ids()[1])
    kw.setdefault("model_port", MODEL_PORT)
    kw.setdefault("placeholder_key", EP_PLACEHOLDER_KEY)
    # 上游与预算**默认取第一条验收配置** —— 生产由调用方按 config_id 传。
    kw.setdefault("model_upstream", "")
    kw.setdefault("max_calls", 0)
    kw.setdefault("max_tokens", 0)
    return COMPOSE_TMPL.format(**kw)


def runner_ids() -> tuple[int, int]:
    """跑 runner 的那个用户。容器降到它 —— 产物属主因此与 harness 一致。

    取**当前进程**的 uid/gid，不写死 1000：写死的那份在换机器/换账号时会静默错位，
    而错位的表现是「产物属主不对」，与「容器没降权」看起来一样。
    """
    return os.getuid(), os.getgid()


def render_compose(task_id: str, arm: str, *, image: str = "python:3.11-alpine",
                   command: str = 'sh -c "sleep 3600"', config_id: str = "cfg-hello",
                   run_uid: int | None = None, run_gid: int | None = None) -> str:
    """**纯函数**：只拼字符串，不建目录、不落盘 —— 这样 lint 可以在数据面机器上被测。"""
    d = task_dir(task_id)
    ids = {}
    if run_uid is not None:
        ids["run_uid"] = run_uid
    if run_gid is not None:
        ids["run_gid"] = run_gid
    return format_compose(
        task_id=task_id, run_id=f"{task_id}-{arm}", project=f"gb-{task_id}",
        arm=arm, image=image, command=command, config_id=config_id, **ids,
        # **现算**，不引模块级的 `GATEWAY`：模块内的名字查找不过 `__getattr__`。
        task_subnet=TASK_SUBNET, egress_subnet=EGRESS_SUBNET, gateway=gateway_addr(),
        proxy_py=str(ROOT / "egress_proxy.py"), h11_dir=str(ROOT / "h11"),
        workdir=str(d / "work"), logdir=str(d / "log"))


# --------------------------------------------------------------- lint

#: 运行期装依赖的痕迹。**依赖一律在镜像构建期解决**（构建时联网、运行时断网），
#: 卡 4.1 §3.4 签字裁定。运行期装依赖必然要求把包仓库放进出向白名单，
#: 而那正是「白名单膨胀」的唯一真实来源。
RUNTIME_INSTALL_PATTERNS = (
    r"\bpip3?\s+install\b", r"\bpython3?\s+-m\s+pip\s+install\b",
    r"\bapt(-get)?\s+install\b", r"\bapk\s+add\b", r"\bdnf\s+install\b",
    r"\byum\s+install\b", r"\bnpm\s+(install|i|ci)\b", r"\byarn\s+add\b",
    r"\bconda\s+install\b", r"\buv\s+(pip\s+)?(install|add)\b",
    r"\bcargo\s+install\b", r"\bgem\s+install\b", r"\bgo\s+(get|install)\b",
)

#: 出现在 compose 里就说明打算在运行期联网取包（环境变量、command 里都算）。
PACKAGE_HOST_HINTS = (
    "pypi.org", "pythonhosted.org", "pypi.tuna", "pypi.douban",
    "registry.npmjs.org", "npmmirror.com", "anaconda.org", "anaconda.com",
    "mirrors.aliyun.com", "mirrors.tuna", "mirrors.ustc",
    "deb.debian.org", "archive.ubuntu.com", "dl-cdn.alpinelinux.org",
    "PIP_INDEX_URL", "PIP_EXTRA_INDEX_URL", "NPM_CONFIG_REGISTRY",
)


def _as_list(v) -> list:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def _service_networks(svc: dict) -> list[str]:
    n = svc.get("networks")
    if isinstance(n, dict):
        return list(n)
    return [str(x) for x in _as_list(n)]


def _flatten(obj) -> str:
    """把一个服务块整体拍平成文本，用于「痕迹扫描」类规则。"""
    return yaml.safe_dump(obj, allow_unicode=True, default_flow_style=False)


#: **数据根**：任务容器绝不该挂到的宿主目录（TK-1 判据 2 的**纵深**，不是主判据）。
#:
#: **主次写明（裁定 2026-09-04）**：
#: * **主判据** = `realpath(挂载源)` 在 `runs_root` 之下。它是**封闭**的 ——
#:   凡不在 runs 根下的挂载一律拒，不需要枚举「不该挂哪里」。
#: * **纵深** = 这张 `DATA_ROOTS` 表。它是**开放**列举，注定会烂（新增一个数据目录
#:   而忘了往这里加，它就漏了）。所以它只在主判据之外多兜一层，
#:   **不能**把它当成「挂载安全」的判据本身。
#: 有一条 sanity 测试断言 `runs_root` 自身不落在任何 `DATA_ROOTS` 内 ——
#: 否则主判据与纵深互相打架，每个 run 都会被自己的纵深判红。
#:
#: **不要**把 `/data` 本身写进来 —— 那会让规则恒红（run dir 也在 /data 下），
#: 而恒红的规则下一个人会把它注释掉。列的是具体的数据目录。
DATA_ROOTS: tuple[str, ...] = ("/data/shared", "/data/market_lake_f02",
                               "/data/genebench_runner/manifests",
                               "/data/genebench_runner/provider")


def lint_compose(text: str, *, expect_workdir: str | Path | None = None,
                 runs_root: str | Path | None = None) -> list[str]:
    """compose 的**硬规则**。每一条都必须真的能拦住（负例见 ``negctl_lint.py``）。

    编号与 `ops/specs/card_4.1_container_isolation.md` 第 5 节一一对应。
    """
    bad: list[str] = []

    # ---- L-1 / L-2：端口映射的格式（D-07）。文本级，先于结构解析 ----
    for m in re.finditer(r'^\s*-\s*"?(\d+):(\d+)"?\s*$', text, re.M):
        bad.append(f"L-1 裸端口映射 `{m.group(0).strip()}` —— docker 的 -p 默认绑 0.0.0.0 "
                   f"且会自插 DOCKER 链绕过 ufw；必须写成 {LAN}:PORT:PORT（D-07）")
    for m in re.finditer(r'^\s*-\s*"?([\d.]+):(\d+):(\d+)"?\s*$', text, re.M):
        if m.group(1) != LAN:
            bad.append(f"L-2 端口映射绑了 {m.group(1)} 而不是 {LAN}（D-07）")

    try:
        doc = yaml.safe_load(text) or {}
    except yaml.YAMLError as e:
        return bad + [f"L-0 compose 不是合法 YAML：{e}"]
    nets = doc.get("networks") or {}
    svcs = doc.get("services") or {}

    # ---- L-3 任务网络必须 internal ----
    tnet = nets.get(TASK_NETWORK)
    if not isinstance(tnet, dict) or tnet.get("internal") is not True:
        bad.append(f"L-3 网络 `{TASK_NETWORK}` 必须 `internal: true` —— "
                   f"默认拒绝要由**拓扑**保证，不是由规则保证")

    # ---- L-4 网段冲突（IN-2：真的 overlaps()，不是子串）----
    # 原来写的是 `"10.42." in text`。**`10.40.0.0/13` 覆盖 10.42/16 与 10.43/16，
    # 却一个禁用子串都不含** —— 当场假绿（卡 4.3 §IN-2 逐字记着这个反例）。
    declared = 0
    for nname, ncfg in (nets or {}).items():
        for cfgitem in (((ncfg or {}).get("ipam") or {}).get("config") or []):
            raw = (cfgitem or {}).get("subnet")
            if raw is None:
                continue
            declared += 1
            try:
                net = ipaddress.ip_network(str(raw), strict=False)
            except ValueError as e:
                bad.append(f"L-4 网络 `{nname}` 的 subnet `{raw}` 解析不出来（{e}）—— "
                           f"解析不了就判不了重叠，不许当成通过")
                continue
            for hit in overlaps_any(net, RESERVED_SUBNETS):
                bad.append(f"L-4 网络 `{nname}`：{hit}")
    if not declared:
        bad.append("L-4 compose 里一个 subnet 都没声明 —— "
                   "docker 会从自己的默认池里挑，而那个池就在 172.16/12 里；"
                   "**没声明**与**声明了个好的**在日志里长得一样")

    task = svcs.get(TASK_SERVICE) or {}
    proxy = svcs.get(PROXY_SERVICE) or {}

    # ---- L-5 任务容器不得 bind-mount 宿主机路径 ----
    # `expect_workdir` 给了就走 TK-1(a) 的**三条判据**（卡 4.3 §8.1，收紧为「精确相等」）；
    # 没给则退回旧的路径片段判据（老调用点还在用 tasks/<id> 布局）。
    # **观测面**：任务服务的每一个 volume 条目都要看，不只是以 `/` 开头的。
    # 原先只收绝对路径 —— 相对路径（`./sneak`、`../../data/shared`）与 `${VAR}` 插值
    # 对「恰为 1」和落点判据**完全隐形**（红队 2026-09-04，high）。
    task_binds, non_abs = [], []
    for vol in _as_list(task.get("volumes")):
        src = vol.get("source") if isinstance(vol, dict) else str(vol).split(":", 1)[0]
        if not src:
            # 先前这里静默跳过。**解析不了的挂载条目不是「没有挂载」** ——
            # 跳过它等于让一条我们看不懂的 volumes 项绕过 L-5 全家（D-23）。
            bad.append(f"L-5 解析不出挂载源的条目 `{vol!r}` —— "
                       f"看不懂的挂载不许放行：看不懂 ≠ 没有挂载")
            continue
        s = str(src)
        if s.startswith("/"):
            task_binds.append(s)
        elif s.startswith((".", "~", "$")) or "/" in s or "${" in s:
            # 相对路径 / 家目录 / 环境变量插值：都能落到宿主任意位置，且 compose 会在
            # **运行时**才解析 —— lint 期看不出它指向哪，所以一律红。
            non_abs.append(s)
            task_binds.append(s)          # 也计入「恰为 1」的计数
    for s in non_abs:
        bad.append(f"L-5c 任务服务的挂载源 `{s}` 不是绝对路径 —— "
                   f"相对路径与 ${{VAR}} 插值在 compose 运行时才解析，lint 期看不出它指向哪")
    if expect_workdir is None:
        for src in task_binds:
            if "/tasks/" not in src and "/runs/" not in src:
                bad.append(f"L-5 任务容器 bind-mount 了宿主机路径 `{src}` —— "
                           f"N-29：f02 本地就有 40GB 世界可读的湖副本，只允许挂任务工作目录")
    else:
        want = Path(expect_workdir).resolve()
        # 判据 1：**恰为 1** 个 bind，且 realpath 精确相等。
        # 用 realpath 而不是字面量比：指向 work/ 的符号链接、`work/../work` 绕路写法
        # 在字面量比下长得完全正确（§8.1 的负例 ③④）。
        if len(task_binds) != 1:
            bad.append(f"L-5a 任务服务的 bind 挂载数是 {len(task_binds)}，必须**恰为 1**："
                       f"{task_binds} —— 只查「有没有一个对的」会放行「一个对的 + 一个别的」")
        for src in task_binds:
            got = Path(src).resolve()
            # 判据 1a：写进 compose 的必须是**规范路径** —— 不许符号链接、不许 `..` 绕路。
            # 为什么不满足于「realpath 之后相等」：那个相等只在**检查时刻**成立。
            # 符号链接可以在 lint 之后、容器启动之前被改指向 /data/shared（TOCTOU），
            # 而 `..` 的语义本身又依赖路径中间有没有符号链接。规范路径没有这个时间窗。
            if str(Path(src)) != str(got):
                bad.append(f"L-5a 挂载源 `{src}` 不是规范路径（realpath = {got}）—— "
                           f"符号链接与 `..` 绕路都要在使用时刻再解析一次，"
                           f"而 lint 只能在检查时刻看；两者之间可以被改指向别处")
            if got != want:
                bad.append(f"L-5a 任务服务挂的是 `{src}`（realpath {got}），"
                           f"必须精确等于本 run 的 work/：{want}")
            # 判据 2：必须在 runs_root 之下，且不是任何一个数据根、也不在数据根之下
            if runs_root is not None and Path(runs_root).resolve() not in got.parents:
                bad.append(f"L-5a 挂载点 {got} 不在 runs 根 {Path(runs_root).resolve()} 之下")
            for d in DATA_ROOTS:
                dr = Path(d)
                if got == dr or dr in got.parents:
                    bad.append(f"L-5a 挂载点 {got} 落在数据根 {d} 之内 —— "
                               f"判据 1 对它是绿的（路径可以既精确相等又落在湖里）。"
                               f"**本地自查请把 run 根放到数据根之外**"
                               f"（`ops/run_f02_a1.py --dry --run-root $TMPDIR/genebench_dry`）")

    # ---- L-5b 顶层 named volume 用 driver_opts 做 bind（卡 4.3 T18 实测发现，2026-09-04）----
    # `volumes: {sneak: {driver_opts: {type: none, device: /data/shared, o: bind}}}` 是一个
    # **真实可用**的 bind 写法：它能挂任何宿主路径，而在 service 段里长得和普通 named volume
    # 一模一样 —— 肉眼与 grep 都过。上面的 L-5 只扫 service 的 volumes，对它**完全沉默**
    # （实测：短语法 1 条、长语法 1 条、这一种 0 条）。
    for vname, vdef in (doc.get("volumes") or {}).items():
        opts = ((vdef or {}).get("driver_opts") or {}) if isinstance(vdef, dict) else {}
        dev, o = str(opts.get("device") or ""), str(opts.get("o") or "")
        if not dev:
            continue
        used_by_task = vname in {(v.get("source") if isinstance(v, dict) else str(v).split(":", 1)[0])
                                 for v in _as_list(task.get("volumes"))}
        if "bind" in o or dev.startswith("/"):
            who = "任务容器" if used_by_task else "本 compose"
            bad.append(f"L-5b {who}用顶层 named volume `{vname}` 的 driver_opts 做 bind："
                       f"device=`{dev}` o=`{o}` —— 这是 bind-mount 的第三种写法，"
                       f"能挂任何宿主路径（含 N-29 那份世界可读的湖副本）")

    # ---- L-6 v1 不得发布任何端口 ----
    # L-1/L-2 管的是「万一将来批准发布端口，格式得对」；L-6 是 v1 的实际策略：
    # 一个发布到 LAN 的代理端口 = 一台对 tailnet 敞开的开放代理（D-07 + D-09）。
    for name, svc in svcs.items():
        if _as_list((svc or {}).get("ports")):
            bad.append(f"L-6 服务 `{name}` 发布了端口 —— v1 任何服务都不得发布端口；"
                       f"代理一旦发布就是一台对 LAN/tailnet 敞开的开放代理")

    # ---- L-7 任务服务只能接任务网络 ----
    tn = _service_networks(task)
    if tn != [TASK_NETWORK]:
        bad.append(f"L-7 任务服务接的网络是 {tn}，必须**只有** [{TASK_NETWORK}] —— "
                   f"接上 `{EGRESS_NETWORK}` 等于绕开代理直接出网，拓扑保证当场失效")
    if EGRESS_NETWORK not in _service_networks(proxy) or TASK_NETWORK not in _service_networks(proxy):
        bad.append(f"L-7 代理服务必须同时接 [{TASK_NETWORK}, {EGRESS_NETWORK}]，否则它不是出口")

    # ---- L-8 运行期不得装依赖 ----
    blob = _flatten(task)
    for pat in RUNTIME_INSTALL_PATTERNS:
        m = re.search(pat, blob)
        if m:
            bad.append(f"L-8 任务服务在**运行期**装依赖（`{m.group(0)}`）—— "
                       f"依赖一律在镜像构建期解决（构建时联网、运行时断网），"
                       f"卡 4.1 §3.4 签字裁定；运行期装依赖必然要把包仓库放进出向白名单")
    for hint in PACKAGE_HOST_HINTS:
        if hint in blob:
            bad.append(f"L-8 任务服务里出现包仓库痕迹 `{hint}` —— 同上，构建期解决")

    # ---- L-10 每个服务都必须降权（N-48）----
    # 判据是**封闭**的：遍历 svcs 里每一个服务，不列白名单。
    # 白名单版会在加第三个服务时静默漏掉它 —— guard_modes 那次的教训
    # （白名单收紧 4 项 vs 封闭判据 40307 项）。
    for name, svc in svcs.items():
        svc = svc or {}
        u = str(svc.get("user", "")).strip()
        if not u:
            bad.append(f"L-10 服务 `{name}` 没有 `user:` —— 容器默认以 root 跑，"
                       f"产物是 root 属主、harness 删不掉；被测 agent 是不可信方（N-48）")
        elif u.split(":")[0] in ("0", "root"):
            bad.append(f"L-10 服务 `{name}` 的 user 是 `{u}` —— 显式写 root 与不写一样坏")
        caps = [str(c).upper() for c in _as_list(svc.get("cap_drop"))]
        if "ALL" not in caps:
            bad.append(f"L-10 服务 `{name}` 缺 `cap_drop: [ALL]` —— "
                       f"降 uid 不等于降能力，CAP_* 仍可能留着")
        opts = [str(o) for o in _as_list(svc.get("security_opt"))]
        if not any(o.startswith("no-new-privileges") for o in opts):
            bad.append(f"L-10 服务 `{name}` 缺 `security_opt: no-new-privileges` —— "
                       f"缺了它，镜像里任何 setuid 二进制都能把权限提回去")

    # ---- L-11 真 key 不进任务容器（裁定 (a)，2026-09-04）----
    # 任务容器里只该有**占位串**；真 key 只注给边车服务，且在 compose 里
    # 只能是 `${...}` 引用 —— 写成字面量就等于把它落进了 run dir，
    # 而 run dir 会被归档、会进结果库。
    KEY_ENV = "GENEBENCH_MODEL_API_KEY"
    tenv = task.get("environment") or {}
    if isinstance(tenv, list):
        tenv = dict(e.split("=", 1) for e in tenv if "=" in str(e))
    if KEY_ENV in tenv:
        bad.append(f"L-11 任务服务的 environment 里有 `{KEY_ENV}` —— "
                   f"被测 agent 是不可信方，真 key 一旦进容器，"
                   f"它就能绕开预算闸直连上游，而边车看不见任何东西")
    for k, v in tenv.items():
        sv = str(v)
        if "API_KEY" in k.upper() and sv and sv != PLACEHOLDER_KEY_LITERAL:
            bad.append(f"L-11 任务服务的 `{k}` 不是占位串 —— 容器里只该有 "
                       f"`{PLACEHOLDER_KEY_LITERAL}`，边车在转发时替换")
    penv = proxy.get("environment") or {}
    if isinstance(penv, list):
        penv = dict(e.split("=", 1) for e in penv if "=" in str(e))
    kv = str(penv.get(KEY_ENV, ""))
    if not kv:
        bad.append(f"L-11 边车服务没有 `{KEY_ENV}` —— 没有真 key，"
                   f"占位串会原样到上游，每次调用 401，"
                   f"而 401 看起来像「模型不配合」不像「我们没配 key」")
    elif not (kv.startswith("${") and kv.endswith("}")):
        bad.append(f"L-11 边车服务的 `{KEY_ENV}` 是**字面量**而不是 `${{...}}` 引用 —— "
                   f"字面量会随 compose.yml 落进 run dir，而 run dir 会被归档、进结果库")

    # ---- L-9 网关调用不得被代理劫走（D-10：只有真跑才会露的坑）----
    env = task.get("environment") or {}
    if isinstance(env, list):
        env = dict(e.split("=", 1) for e in env if "=" in str(e))
    proxy_url = f"http://{PROXY_SERVICE}:3128"
    for k in ("HTTP_PROXY", "HTTPS_PROXY"):
        if env.get(k) != proxy_url:
            bad.append(f"L-9 任务服务的 {k} 应为 `{proxy_url}`，实为 `{env.get(k)}`")
    for k in ("NO_PROXY", "no_proxy"):
        if PROXY_SERVICE not in str(env.get(k, "")):
            bad.append(f"L-9 任务服务的 {k} 必须含 `{PROXY_SERVICE}` —— "
                       f"否则到网关的**明文 HTTP** 请求会被 HTTP_PROXY 劫给 CONNECT 代理，"
                       f"代理回 405，症状看起来像网关坏了（D-10）")
    return bad


# --------------------------------------------------------------- 遥测

DDL = """
CREATE TABLE IF NOT EXISTS agent_result (
  run_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, arm TEXT NOT NULL,
  config_id TEXT, started_at TEXT, finished_at TEXT, elapsed_s REAL,
  exit_code INTEGER, failure_mode TEXT, markers TEXT,
  tokens_in INTEGER, tokens_out INTEGER, cost_usd REAL, steps INTEGER,
  search_count INTEGER, trial_family TEXT,          -- 卡 2.3 冻结项，先留位
  cash_ratio_median REAL,                            -- N-26 探针前置，先留位
  result_json TEXT, gateway_hits INTEGER, egress_denied INTEGER
);
"""


def db(path: Path | None = None) -> sqlite3.Connection:
    p = path or (ROOT / "results" / "results.sqlite3")
    p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(p)
    c.executescript(DDL)
    return c


def record(conn: sqlite3.Connection, **kw) -> None:
    cols = [r[1] for r in conn.execute("PRAGMA table_info(agent_result)")]
    row = {k: v for k, v in kw.items() if k in cols}
    q = (f"INSERT OR REPLACE INTO agent_result ({','.join(row)}) "
         f"VALUES ({','.join('?' * len(row))})")
    conn.execute(q, list(row.values()))
    conn.commit()


# --------------------------------------------------------------- 运行

def rotate_egress_log(logdir: Path) -> Path | None:
    """把上一轮的出向日志挪开，**每次运行一份自己的**。

    不挪的后果是静默的：日志跨运行追加，``egress_denied`` 会把**上一轮**的拒绝
    算进这一轮。数值仍然合理、没有任何东西报错 —— D-06 那个形状。
    """
    cur = logdir / "egress.jsonl"
    if not cur.exists():
        return None
    n = 1
    while (logdir / f"egress.{n}.jsonl").exists():
        n += 1
    dest = logdir / f"egress.{n}.jsonl"
    cur.rename(dest)                     # 留着，它是卡 5.1 网络侧的结算证据
    return dest


def run_task(task_id: str, arm: str, *, verbose: bool = True) -> dict:
    d = task_dir(task_id)
    body = HELLO_TASK["arms"][arm]
    (d / "work").mkdir(parents=True, exist_ok=True)
    (d / "log").mkdir(parents=True, exist_ok=True)
    rotate_egress_log(d / "log")
    (d / "work" / "INSTRUCTION.md").write_text(body, encoding="utf-8")
    script = r'''
import json, os, urllib.request
gw = os.environ["GENEBENCH_GATEWAY"]
q = ("as_of=2026-07-31&code=600519.SH&start_date=2026-07-01&end_date=2026-07-10")
req = urllib.request.Request(f"{gw}/bars?{q}", headers={
    "x-genebench-config-id": os.environ.get("GENEBENCH_CONFIG_ID", ""),
    "x-genebench-task-id": os.environ.get("GENEBENCH_TASK_ID", "")})
with urllib.request.urlopen(req, timeout=30) as r:
    d = json.load(r)
json.dump({"rows": d["rows"]}, open("/task/result.json", "w"))
print("rows =", d["rows"])
'''
    (d / "work" / "agent.py").write_text(script, encoding="utf-8")
    compose = render_compose(task_id, arm, command='sh -c "python3 /task/agent.py"')
    bad = lint_compose(compose)
    if bad:
        raise RuntimeError("compose lint 未过：\n  " + "\n  ".join(bad))
    cf = d / "compose.yml"
    cf.write_text(compose, encoding="utf-8")

    t0 = time.time()
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    subprocess.run(["docker", "compose", "-f", str(cf), "up", "-d", "gateway"],
                   capture_output=True, text=True)
    time.sleep(2)
    r = subprocess.run(["docker", "compose", "-f", str(cf), "run", "--rm", "task"],
                       capture_output=True, text=True, timeout=300)
    el = time.time() - t0
    subprocess.run(["docker", "compose", "-f", str(cf), "down", "-v"],
                   capture_output=True, text=True)

    res = None
    rp = d / "work" / "result.json"
    if rp.exists():
        try:
            res = json.loads(rp.read_text())
        except Exception:
            res = None
    elog = d / "log" / "egress.jsonl"
    hits = denied = starts = malformed = 0
    if elog.exists():
        for line in elog.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                e = json.loads(line)
            except Exception:
                # 出向日志是**卡 5.1 网络侧的结算源**。解析不了的行先前被静默吞掉，
                # 而 hits/denied 照样往下加 —— 一条写坏的行于是表现为
                # 「这次少了一个请求」，与「真的没请求」不可分（D-06 的形态）。
                malformed += 1
                continue
            hits += e.get("event") == "forward"
            denied += e.get("event") == "deny"
            starts += e.get("event") == "ready"
    # 判别力断言：这份日志必须**恰好**是一次运行的。两次以上说明轮转没生效，
    # 计数就跨了运行 —— 那 hits/denied 两个数都不作数。
    if malformed:
        raise RuntimeError(
            f"出向日志里有 {malformed} 行解析不了 —— 它是卡 5.1 网络侧的结算源，"
            f"写坏的行不能当成「这段时间没请求」（D-06 的形态）。"
            f"先查是不是写盘被截断，再决定这次运行是否作废。")
    if starts != 1:
        raise RuntimeError(
            f"出向日志里有 {starts} 次启动记录（应为 1）—— 日志跨运行了，"
            f"gateway_hits/egress_denied 都不可信")

    out = {"run_id": f"{task_id}-{arm}", "task_id": task_id, "arm": arm,
           "config_id": "cfg-hello", "started_at": started,
           "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "elapsed_s": round(el, 2), "exit_code": r.returncode,
           "failure_mode": None if r.returncode == 0 else "nonzero_exit",
           "markers": json.dumps({"stdout_tail": r.stdout[-300:]}, ensure_ascii=False),
           "result_json": json.dumps(res, ensure_ascii=False) if res else None,
           "gateway_hits": hits, "egress_denied": denied,
           "search_count": None, "trial_family": None, "cash_ratio_median": None}
    conn = db()
    record(conn, **out)
    conn.close()
    if verbose:
        print(json.dumps({k: out[k] for k in
                          ("run_id", "arm", "exit_code", "elapsed_s",
                           "result_json", "gateway_hits", "egress_denied")},
                         ensure_ascii=False, indent=1))
        if r.returncode != 0:
            print("--- stderr ---\n" + r.stderr[-1200:])
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["hello", "lint"])
    p.add_argument("--arm", default="strict", choices=["strict", "open"])
    p.add_argument("--task-id", default="hello-0001")
    a = p.parse_args()
    if a.cmd == "lint":
        print(lint_compose(render_compose(a.task_id, a.arm)) or "lint 通过")
        return 0
    run_task(a.task_id, a.arm)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
