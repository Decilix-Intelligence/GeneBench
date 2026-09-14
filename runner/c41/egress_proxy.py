# -*- coding: utf-8 -*-
"""卡 4.1：任务容器的**唯一**出口。

    python3 egress_proxy.py --gateway 192.168.1.48:18080 --log /var/log/egress.jsonl

任务容器接在 ``internal: true`` 的网络上 —— **物理上没有默认路由**，
连不到任何东西。本进程同时接内网与外网，是它唯一的出口。

**为什么不用 `DOCKER-USER` / iptables 白名单**（这是对签字建议的一处改进，已批准）：

* iptables 方案需要 root，且在**宿主机**上留持久状态；
  一次 ``iptables -F``、一次 docker 重启、另一个管理员的一条规则，白名单就没了。
* ``internal: true`` 的默认拒绝是**网络拓扑保证**的 —— 容器根本没有出口，
  不是「有出口但被规则挡住」。**没有可被清空的状态。**
* 白名单因此是**代码**（本文件的 :data:`MODEL_API_ALLOW`），进版本库、可审查、可测试。

两个端口，两种用途，**都记日志**：

* ``:18080`` —— **纯 TCP 转发**到数据网关。任务容器用 ``http://gateway:18080`` 直接访问，
  不需要配代理。
* ``:3128``  —— **HTTP CONNECT 代理**，按**主机名 + TLS SNI** 双重白名单。给模型 API 用。
  按主机名而不是 IP：模型 API 在 CDN 后面 IP 会轮转，IP 白名单要么今天能跑明天挂，
  要么放宽到整个网段等于放开半个互联网。

**出向策略的理由不是「防数据外传」，是「防经互联网前视」**（设计笔记 D-08）：
冻结线是 ``2026-07-31``；一个能上公网的 agent 可以直接查 2026 年 8 月发生了什么，
我们整套 as-of 强制**当场失效且静默** —— 网关 ``access_log`` 干干净净，
前视探针全绿，因为它根本没走我们的数据面。

日志是**证据**：它是网关 ``access_log.jsonl`` 的**网络侧**对应物。
卡 5.1 的前视探针以**两者合起来**结算：数据面侧看网关日志，网络侧看本文件的日志。
少任何一侧，「这次运行有没有绕过数据面去外面取数」都答不了。
"""
from __future__ import annotations

import argparse
import json
import os
import select
import socket
import ssl
import sys
import threading
import time
from datetime import datetime, timezone

# --------------------------------------------------------------- 白名单（是代码，不是防火墙状态）

#: 运行期白名单：**主机名 -> 「哪个被测配置需要它」**。
#: 每一条都必须写明引用者 —— **没有引用者的条目就是死白名单面**，
#: 与「路由白名单假绿」（D-06 实例 3）是同一形状：条目在，保护不在。
#: **由 `runner/registry.py::collect_egress_hosts()` 生成**（§15，裁定 2026-09-04）。
#: 这里保留字面量是因为本文件要**单文件**挂进边车容器（`/opt/egress_proxy.py`），
#: 不能在容器里 import 注册表；同源由 `ops/test_c41.py::test_allowlist_matches_registry`
#: 保证 —— **键集相等**（不是包含），改注册表不改这里当场红。
#:
#: 先前两条（anthropic / openai）的引用者写的是「待 M6 复核」，也就是
#: **没有任何真实配置需要它们**（N-32）；而 2026-09-04 实测：openai 从两台机 TCP 层不通、
#: anthropic 403 地区封锁 —— 白名单上挂着两条既没人要、又不可达的条目。
MODEL_API_ALLOW: dict[str, str] = {
    "api.deepseek.com": "cfg-codex-deepseek、cfg-openhands-deepseek、cfg-rdagent-deepseek",
}

#: **反向代理的上游允许集**（裁定 2026-09-04）。`MODEL_API_ALLOW` 的语义随之改变：
#: 它不再是「允许 CONNECT 到哪」，而是「反向代理允许连到哪个上游」。
MODEL_UPSTREAMS: frozenset[str] = frozenset(MODEL_API_ALLOW)

#: **允许 CONNECT 到的主机名 —— 现在是空集。**
#:
#: 为什么清空：模型只能经**反向代理**到达（边车在明文侧附鉴权头，
#: 再对上游起 TLS）。留一条 CONNECT 到 `api.deepseek.com` 的路，等于给
#: 「agent 自带一把 key 直连」留了门 —— 而那条路上边车看不见任何东西：
#: 没有 usage、没有 Steps、预算闸也管不着。
#: 空集不是「暂时没有条目」，是**判据**：任何 CONNECT 一律拒并留痕。
ALLOW: frozenset[str] = frozenset()

#: 容器内给 SDK 的**占位** key。边车在转发时把它替换成真 key。
#: agent 拿到的就是这一串 —— 它是公开的，写在这里没有任何问题。
PLACEHOLDER_KEY: str = "sk-genebench-placeholder"

#: 允许 CONNECT 的端口。即使主机在白名单里，端口也必须在这里。
#: 只放 443 是为了让 SNI 校验成立 —— 明文端口上没有 SNI 可校。
ALLOW_PORTS: frozenset[int] = frozenset({443})

#: **依赖装在镜像构建期，不进运行期白名单**（卡 4.1 §3.4，签字裁定）。
#: 构建时联网、运行时断网。这里列的是**常见**包/镜像仓库，作为**绊线**。
#:
#: ⚠ 这份清单**永远不可能完整**（镜像站无穷多）。它拦的是「顺手加一条」的情况，
#: 真正的保证是上面那条评审规则：**每个条目必须指名一个需要它的被测配置**。
#: 不要把这份清单当成完备的防线 —— 那正是 D-06 要防的「以为在保护，其实是空的」。
BUILD_TIME_ONLY: tuple[str, ...] = (
    "pypi.org", "pythonhosted.org", "pypi.tuna.tsinghua.edu.cn", "pypi.douban.com",
    "registry.npmjs.org", "npmmirror.com", "yarnpkg.com",
    "github.com", "githubusercontent.com", "gitlab.com", "codeload.github.com",
    "anaconda.org", "anaconda.com", "conda.io",
    "debian.org", "ubuntu.com", "alpinelinux.org", "centos.org", "epel.cloud",
    "mirrors.aliyun.com", "mirrors.tuna.tsinghua.edu.cn", "mirrors.ustc.edu.cn",
    "crates.io", "rubygems.org", "maven.org", "docker.io", "quay.io", "ghcr.io",
)

#: SNI 必须与 CONNECT 的目标主机名**逐字相等**。
#: 关掉它等于允许 domain fronting：CONNECT 到白名单域名、TLS 里握另一个域名。
REQUIRE_SNI_MATCH: bool = True


def is_build_time_only(host: str) -> bool:
    """主机名是否落在「只允许构建期」的包/镜像仓库上。"""
    h = host.lower().rstrip(".")
    return any(h == d or h.endswith("." + d) for d in BUILD_TIME_ONLY)


# ---- import 期守门：白名单本身要能被检查，不能只靠人看 ----------------------

#: **行情 / 新闻源一律不得入表**（§15 的第三类绊线）。
#: 放进去等于让被测系统**绕过数据面取数** —— 网关 `access_log` 会干干净净、
#: 卡 5.1 的前视探针全绿，而 as-of 强制已经失效（卡 4.1 §3.1 的形态）。
#: 与 `BUILD_TIME_ONLY` 并列：两张表都是**绊线**，不是完备防线。
#: 这份与 `runner/registry.py::MARKET_DATA_HOSTS` 同源（测试盯着）。
MARKET_DATA_DENY: tuple[str, ...] = (
    "query1.finance.yahoo.com", "query2.finance.yahoo.com", "fc.yahoo.com",
    "finnhub.io", "www.alphavantage.co", "api.polygon.io", "news.google.com",
    "api.tiingo.com", "api.twelvedata.com", "www.reddit.com", "api.stocktwits.com",
    "api.polymarket.com", "api.stlouisfed.org",
)


def is_market_data(host: str) -> bool:
    h = host.lower().rstrip(".")
    return any(h == d or h.endswith("." + d) for d in MARKET_DATA_DENY)


def assert_allowlist_sane(mapping: dict[str, str]) -> None:
    """白名单的**三条**硬规则。**import 期就跑**，并且可以被测试拿坏输入喂。

    做成函数而不是模块级裸语句，是为了让「这条守门真的会红」可被证明 ——
    裸语句只能证明好输入不红，证不了坏输入会红（D-06）。
    """
    unjustified = sorted(h for h, why in mapping.items() if not str(why).strip())
    if unjustified:
        raise RuntimeError(
            f"白名单条目没写引用者：{unjustified} —— "
            f"没有被测配置需要的条目就是死白名单面，删掉或写明谁需要它。")
    leak = sorted(h for h in mapping if is_build_time_only(h))
    if leak:
        raise RuntimeError(
            f"运行期白名单里出现了包/镜像仓库 {leak} —— "
            f"依赖一律在镜像构建期解决（构建时联网、运行时断网），卡 4.1 §3.4 签字裁定。")
    feed = sorted(h for h in mapping if is_market_data(h))
    if feed:
        raise RuntimeError(
            f"运行期白名单里出现了行情/新闻源 {feed} —— 那等于让被测系统绕过数据面取数："
            f"网关 access_log 会干干净净、前视探针全绿，而 as-of 强制已经失效。")


def assert_allowlist_reachable(mapping: dict[str, str] | None = None, *,
                               timeout: float = 8.0) -> None:
    """**第四类绊线：条目必须实测可达**（裁定 2026-09-04）。

    **不在 import 期跑**：边车在容器里 import 本文件，那时做网络探测会让
    边车的启动依赖外网 —— 一次抖动就变成「边车起不来」，而真正的问题只是探测超时。
    由 harness 在**起容器之前**调，或由 `ops/test_c41.py` 的联网测试调。

    为什么需要它：一个只在 403 层失败的域名会一直挂在表上**装作有效**，
    而「有效」正是白名单存在的全部意义。2026-09-04 实测：
    `api.openai.com` TCP 层不通、`api.anthropic.com` 403 地区封锁 ——
    两条都在表上挂了很久，没有任何东西说它们其实用不了。
    """
    import socket
    import ssl
    bad = []
    for host in sorted(mapping if mapping is not None else MODEL_API_ALLOW):
        try:
            with socket.create_connection((host, 443), timeout=timeout) as raw:
                ctx = ssl.create_default_context()
                with ctx.wrap_socket(raw, server_hostname=host):
                    pass
        except Exception as e:                              # noqa: BLE001
            bad.append(f"{host}: {type(e).__name__}: {str(e)[:80]}")
    if bad:
        raise RuntimeError(
            "白名单条目实测不可达：\n  " + "\n  ".join(bad)
            + "\n只在 403 层失败的域名会一直挂在表上装作有效，而「有效」正是白名单的全部意义。")


assert_allowlist_sane(MODEL_API_ALLOW)

# --------------------------------------------------------------- 日志

_LOCK = threading.Lock()
_LOG_PATH = "/tmp/egress.jsonl"
_TASK_ID = "unknown"


def log(**kw) -> None:
    rec = {"ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
           "task_id": _TASK_ID, **kw}
    line = json.dumps(rec, ensure_ascii=False)
    with _LOCK:
        with open(_LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    print(line, flush=True)


# --------------------------------------------------------------- TLS SNI

def parse_sni(data: bytes) -> str | None:
    """从 TLS ClientHello 里取 SNI。取不到返回 ``None``（**调用方必须 fail closed**）。

    只解析到需要的深度，不做完整 TLS 解析：
    record(5) → handshake 头(4) → version(2) + random(32) + session_id
    → cipher_suites → compression → extensions → ext type 0x0000 → host_name。
    """
    try:
        if len(data) < 5 or data[0] != 0x16:          # 不是 handshake record
            return None
        rec_len = int.from_bytes(data[3:5], "big")
        body = data[5:5 + rec_len]
        if len(body) < 4 or body[0] != 0x01:          # 不是 ClientHello
            return None
        hs_len = int.from_bytes(body[1:4], "big")
        hs = body[4:4 + hs_len]
        if len(hs) < hs_len:                          # ClientHello 跨了多个 record
            return None
        i = 2 + 32                                    # client_version + random
        i += 1 + hs[i]                                # session_id
        i += 2 + int.from_bytes(hs[i:i + 2], "big")   # cipher_suites
        i += 1 + hs[i]                                # compression_methods
        if i + 2 > len(hs):
            return None
        ext_total = int.from_bytes(hs[i:i + 2], "big")
        i += 2
        end = min(i + ext_total, len(hs))
        while i + 4 <= end:
            etype = int.from_bytes(hs[i:i + 2], "big")
            elen = int.from_bytes(hs[i + 2:i + 4], "big")
            edata = hs[i + 4:i + 4 + elen]
            i += 4 + elen
            if etype != 0x0000:                       # server_name
                continue
            j = 2                                     # server_name_list 长度
            while j + 3 <= len(edata):
                ntype = edata[j]
                nlen = int.from_bytes(edata[j + 1:j + 3], "big")
                name = edata[j + 3:j + 3 + nlen]
                j += 3 + nlen
                if ntype == 0x00:                     # host_name
                    # SNI 按 RFC 6066 是 ASCII（国际化域名走 punycode）。
                    # 非 ASCII 一律判解析失败 → 调用方 fail closed。
                    return name.decode("ascii", errors="strict").lower().rstrip(".")
            return None
        return None
    except (IndexError, ValueError, UnicodeDecodeError):
        return None


def hello_complete(data: bytes) -> bool:
    """第一条 TLS record 是否已经收全 —— 收全了还解不出 SNI 就不必再等。"""
    if len(data) < 5 or data[0] != 0x16:
        return False
    return len(data) >= 5 + int.from_bytes(data[3:5], "big")


def read_client_hello(sock: socket.socket, cap: int = 16384,
                      deadline_s: float = 10.0) -> tuple[bytes, str | None]:
    """读到能解出 SNI 为止。返回 ``(已读字节, sni)``；读不出就是 ``(已读字节, None)``。

    必须把读到的字节**原样交给上游**（调用方负责），否则 TLS 握手会因为丢了
    ClientHello 而失败 —— 这类 bug 只有真跑才会露（D-10）。
    """
    buf = b""
    t_end = time.time() + deadline_s
    while len(buf) < cap and time.time() < t_end:
        sock.settimeout(max(0.1, t_end - time.time()))
        try:
            chunk = sock.recv(4096)
        except (OSError, socket.timeout):
            break
        if not chunk:
            break
        buf += chunk
        sni = parse_sni(buf)
        if sni is not None:
            return buf, sni
        if hello_complete(buf):
            # 收全了仍解不出 —— 不是分片问题，别干等到超时
            return buf, None
    return buf, parse_sni(buf)


# --------------------------------------------------------------- 转发

def pipe(a: socket.socket, b: socket.socket) -> int:
    """双向转发，返回搬运的字节数（进日志，用于外传体量的事后结算）。"""
    total = 0
    socks = [a, b]
    try:
        for s in socks:
            s.settimeout(None)
        while True:
            r, _, x = select.select(socks, [], socks, 60)
            if x or not r:
                break
            for s in r:
                data = s.recv(65536)
                if not data:
                    return total
                (b if s is a else a).sendall(data)
                total += len(data)
    except OSError:
        pass
    finally:
        for s in (a, b):
            try:
                s.close()
            except OSError:
                pass
    return total


#: ID-1/ID-2（卡 4.3 §6.5）：身份由**边车**在入口注入，不由客户端自报。
#: 边车在可信侧、其 env 由 compose 从 run dir 渲染，任务容器改不到 —— 它是唯一可信注入点。
IDENTITY_HEADERS = {
    "x-genebench-task-id": "GENEBENCH_TASK_ID",
    "x-genebench-config-id": "GENEBENCH_CONFIG_ID",
    "x-gb-run-id": "GENEBENCH_RUN_ID",
    "x-gb-arm": "GENEBENCH_ARM",
}
#: **要剥掉的全类前缀**（大小写不敏感）。先剥后注，禁止「只追加不删除」——
#: starlette 的 `Headers.get()` 取**第一个**同名头，客户端抢先写一份就赢了（ID-1 实测）。
STRIP_PREFIXES = ("x-genebench-", "x-gb-")


#: 边车**用与网关同一个库**解析请求头（裁定 2026-09-05）。
#:
#: 为什么不是"再补几条规则"：裸 LF 只是「边车与上游解析差异」这一类的**一个实例**。
#: 同类还有 obs-fold、TE 与 CL 并存、chunked 扩展、头名大小写重复……逐种补是跑步机；
#: 照着 h11 重写一遍行界规则则会漂（漂的表现就是下一个走私洞）。
#: 让边车**跑 h11 本尊**，"两个解析器看法不同"在构造上不存在。
#:
#: **容器里怎么有 h11**：它是纯 Python（23 个文件、151 KB、无扩展），
#: `runner/inject.py` 的 P7d 把**网关自己那份** h11 复制进 run dir 挂给边车，
#: 与边车源码同样进 P8 文件集封闭、sha 记进 `inject.json`。
#: 所以两边不是"版本号相同"，是**同一份字节**。
# f02 的 python3 **没有 h11 也没有 pip**（2026-09-05 实测）。容器里 h11 经 P7d 挂在 /opt（PYTHONPATH），
# 但 **runner 进程自己**也会 import 本模块（`runner_core` 取 PLACEHOLDER_KEY）——
# 所以先把 exec 树里随树船运的 `vendor/` 放进 sys.path（有就加，没有就走正常 import）。
import sys as _sys                                                  # noqa: E402
from pathlib import Path as _Path                                   # noqa: E402
# 容器里本文件挂在 /opt/egress_proxy.py（parents 只有两层），那里 h11 走 PYTHONPATH=/opt —— 不能硬取 parents[2]。
_PARENTS = _Path(__file__).resolve().parents
_VENDOR = _PARENTS[2] / "vendor" if len(_PARENTS) > 2 else None
if _VENDOR is not None and (_VENDOR / "h11" / "__init__.py").is_file() and str(_VENDOR) not in _sys.path:
    _sys.path.insert(0, str(_VENDOR))
try:
    import h11                                                      # noqa: E402
except ModuleNotFoundError as _h11_err:                             # N-856，2026-09-14
    raise ModuleNotFoundError(
        "找不到 h11。执行面上它应该**随 exec 树船运**在 `<exec 树>/vendor/h11/`"
        f"（本进程找的是 {_VENDOR}）。2026-09-14 之前仓库里没有它、也没有任何文档化步骤会铺它 ——"
        "f02 上那一份是 2026-09-05 手工跑 `ops/run_f02_container_tests.sh` 留下的**遗留物**，"
        "于是一棵从零铺的执行面 import 不了整棵 runner（`runner_core` 在 import 期取本模块的"
        " PLACEHOLDER_KEY）。现在由 `runner/placement.stage_vendor` 从**发布方网关环境自己那份**"
        " h11 铺过去（裁定 2026-09-05：边车与网关不是「版本号相同」而是**同一份字节**）：\n"
        "  双机：ops/push_exec_to_f02.sh --with-launch-data\n"
        "  单机：GENEBENCH_TOPOLOGY=single python -m runner.placement --place-exec --with-launch-data"
    ) from _h11_err

#: 网关环境里 h11 的版本。**不一致就在 import 期红** —— 边车与网关解析不同版本的 h11，
#: 差异类就又回来了，而它不会以任何别的方式表现出来。
H11_VERSION = "0.16.0"


def _assert_h11_pinned(mod=None) -> None:
    m = mod if mod is not None else h11
    got = getattr(m, "__version__", None)
    if got != H11_VERSION:
        raise RuntimeError(
            f"边车装的 h11 是 {got}，钉的是 {H11_VERSION} —— "
            f"边车与网关必须跑同一份解析器，否则「两个解析器看法不同」这一类洞就回来了")


_assert_h11_pinned()

#: 剥除前缀的 bytes 形态（h11 给出的头名是小写 bytes）。
_STRIP_B: tuple[bytes, ...] = tuple(p.encode("ascii") for p in STRIP_PREFIXES)


_HTTP_METHODS = (b"GET", b"POST", b"PUT", b"DELETE", b"HEAD", b"OPTIONS", b"PATCH")


class ProtocolViolation(ValueError):
    """头部不是规范的 CRLF 形式。**拒绝，不是尽力解析。**"""


#: 头部结束标记。**必须与上游解析器认得一样多** —— 上游是 h11，它把裸 LF 也当行分隔
#: （`h11.ReceiveBuffer` 的 `blank_line_regex`）。边车只认 `\r\n\r\n` 的话，
#: 攻击方用 `\n\n` 结尾就能让边车读不到边界（一路读到 1MB 抛错），而网关照常受理。
_HEAD_ENDS = (b"\r\n\r\n", b"\n\r\n", b"\r\n\n", b"\n\n")


def _find_head_end(buf: bytes) -> tuple[int, int]:
    """返回 (头部字节数, 分隔符长度)；找不到返回 (-1, 0)。取**最早**的那个。"""
    best, blen = -1, 0
    for marker in _HEAD_ENDS:
        i = buf.find(marker)
        if i >= 0 and (best < 0 or i < best or (i == best and len(marker) > blen)):
            best, blen = i, len(marker)
    return best, blen


def assert_canonical_head(head: bytes) -> None:
    """头部里出现**裸 LF 或裸 CR** 一律拒（RFC 7230 §3.5 允许接收方拒）。

    **这条不是洁癖，是 ID-1/ID-2 的前提**（2026-09-05 实测，见 N-91）：
    边车按 CRLF 切行来剥身份头，而上游 h11 把裸 LF 也当行分隔 —— 两个解析器对
    「哪些是头」看法不同。于是

        X-Whatever: a\nx-genebench-config-id: cfg-forged\r\n

    在边车看来是**一行**（名字 `x-whatever`，不在剥除前缀里，原样放行），
    到 h11 那里是**两行**；伪造的 `config_id` 还排在边车注入的真值**前面**，
    而 starlette 的 `.get()` 取第一个。结果：任务容器可以伪造**任意身份头**到
    **任意端点**，`access_log` 会如实记下那个伪造身份 —— lookahead 归因、越权率、
    模拟盘会话，全部按身份切片，全部作废。

    解析器不一致这类洞，靠「把边车也写成 h11 那样」是修不完的（下一个差异会再来一次）。
    **收窄输入**才是能封住整类的做法：只接受规范 CRLF。
    """
    n = len(head)
    for i in range(n):
        b = head[i]
        if b == 0x0A and (i == 0 or head[i - 1] != 0x0D):
            raise ProtocolViolation(f"头部第 {i} 字节是裸 LF")
        if b == 0x0D and (i + 1 >= n or head[i + 1] != 0x0A):
            raise ProtocolViolation(f"头部第 {i} 字节是裸 CR")


def _read_until_headers(sock, buf: bytes) -> tuple[bytes, bytes]:
    """读到 header 结束。返回 (头部含空行, 余下已读字节)。连接关闭返回 (b"", 剩余)。"""
    while True:
        i, blen = _find_head_end(buf)
        if i >= 0:
            return buf[:i + blen], buf[i + blen:]
        chunk = sock.recv(65536)
        if not chunk:
            return b"", buf
        buf += chunk
        if len(buf) > 1 << 20:
            raise ValueError("HTTP 头超过 1MB")


def _header_value(head: bytes, name: str) -> str | None:
    want = name.lower().encode()
    for line in head.split(b"\r\n")[1:]:
        if not line:
            continue
        k, _, v = line.partition(b":")
        if k.strip().lower() == want:
            return v.strip().decode("latin-1", "replace")
    return None


def _framing(head: bytes, headers) -> tuple[str, int]:
    """`(transfer-encoding, content-length)`。给了 h11 头就用它，**不再按字节重切**。"""
    if headers is not None:
        te = cl = b""
        for n, v in headers:
            if n == b"transfer-encoding":
                te = v
            elif n == b"content-length":
                cl = v
        return te.decode("latin-1").lower(), int(cl or b"0")
    return ((_header_value(head, "transfer-encoding") or "").lower(),
            int(_header_value(head, "content-length") or 0))


def _relay_body(src, dst, head: bytes, pre: bytes, headers=None) -> None:
    """按 Content-Length / chunked **精确**转发消息体，一个字节不多不少。

    多搬一个字节 = 把下一个请求的头当成了体（于是它逃掉剥注）；
    少搬一个 = 上游一直等而客户端以为发完了。T15 正是盯着前一种。
    """
    te, n = _framing(head, headers)
    if "chunked" in te:
        buf = pre
        while True:
            while b"\r\n" not in buf:
                c = src.recv(65536)
                if not c:
                    dst.sendall(buf)
                    return
                buf += c
            line, _, rest = buf.partition(b"\r\n")
            size = int(line.split(b";")[0].strip() or b"0", 16)
            need = size + 2                       # 数据 + 结尾 CRLF
            chunk = rest
            while len(chunk) < need:
                c = src.recv(65536)
                if not c:
                    break
                chunk += c
            dst.sendall(line + b"\r\n" + chunk[:need])
            buf = chunk[need:]
            if size == 0:
                return
        return
    # n 由 _framing 给出（见上）。
    sent = min(len(pre), n)
    if sent:
        dst.sendall(pre[:sent])
    left = n - sent
    while left > 0:
        c = src.recv(min(65536, left))
        if not c:
            return
        dst.sendall(c)
        left -= len(c)


def parse_request(head: bytes) -> "h11.Request":
    """**用 h11 解析**（与网关同一份字节的同一个库）。解析不了就拒。

    这是根治「边车与上游解析差异」那一类的做法：边车看到的头 = 网关会看到的头，
    因为它们是同一个解析器给出的。裸 LF 走私之所以成立，正是因为原来这里是
    `head.split(b"\r\n")` —— 一份手写的、与 h11 不同的行界规则。
    """
    conn = h11.Connection(h11.SERVER)
    try:
        conn.receive_data(head)
        ev = conn.next_event()
    except Exception as e:                                          # noqa: BLE001
        raise ProtocolViolation(f"h11 解析失败：{type(e).__name__}: {e}") from None
    if not isinstance(ev, h11.Request):
        raise ProtocolViolation(f"h11 给出的不是 Request，而是 {type(ev).__name__}")
    return ev


def assert_unambiguous_framing(head: bytes, req: "h11.Request") -> None:
    """两条 h11 **不管**、但必须拒的（2026-09-05 实测确认 h11 对这两种一律放行）：

    * **`Transfer-Encoding` 与 `Content-Length` 并存** —— 经典的请求走私原语：
      两端谁优先谁就决定消息边界，边界不一致就能把下一个请求的头塞进上一个的体里，
      而那个头**逃掉剥注**。RFC 7230 §3.3.3 允许拒；这里必须拒。
    * **obs-fold（续行以 SP/HTAB 开头）** —— h11 会把它折进上一行的值（实测
      `X-A: 1` + `  continued` → `x-a: 1 continued`）。折法一致时没有歧义，
      但 RFC 7230 §3.2.4 要求拒绝或替换，而**没有任何正经客户端发它**。
      收窄输入的代价是零，留着的代价是下一次要重新论证一遍"折法一致"。
    """
    for line in head.split(b"\r\n")[1:]:
        if line[:1] in (b" ", b"\t"):
            raise ProtocolViolation("头部含 obs-fold 续行（RFC 7230 §3.2.4 已废弃）")
    names = {n for n, _ in req.headers}
    if b"content-length" in names and b"transfer-encoding" in names:
        raise ProtocolViolation(
            "Transfer-Encoding 与 Content-Length 并存 —— 消息边界取决于哪一端优先，"
            "是请求走私的经典原语")


def serialize_identity(req: "h11.Request", identity: dict[str, str]) -> bytes:
    """**从 h11 的解析结果重新序列化**：边车批准的那份视图，就是发给网关的那些字节。

    保留原始字节的话，"边车批准了什么"与"网关会读到什么"之间又留了一道缝。
    代价是头名统一成小写（h11 的归一）—— HTTP 头名本就大小写不敏感，
    网关那侧也是小写比对，语义一个字没变。
    """
    out = [b"%s %s HTTP/%s" % (req.method, req.target, req.http_version)]
    for name, value in req.headers:
        if any(name.startswith(pfx) for pfx in _STRIP_B):
            continue                       # 剥：含重复出现的同名头、任意大小写
        out.append(name + b": " + value)
    for h, env in IDENTITY_HEADERS.items():
        v = identity.get(env)
        if v:
            out.append(h.encode("latin-1") + b": " + v.encode("latin-1", "replace"))
    return b"\r\n".join(out) + b"\r\n\r\n"


def rewrite_identity(head: bytes, identity: dict[str, str]) -> bytes:
    """**先剥后注**（h11 解析 → 剥身份头 → 注 runner 真值 → 规范重序列化）。"""
    return serialize_identity(parse_request(head), identity)


def http_identity_proxy(listen_port: int, target: tuple[str, int], label: str,
                        identity: dict[str, str]) -> None:
    """网关端口上的 **HTTP 层反向代理**（ID-1/ID-2）。

    **每个请求都重新剥注** —— T15 实测过：只剥第一个、之后交给双向 splice 的实现，
    同一 keep-alive 连接上的**第二个**请求会带着伪造头原样到达网关，
    而网关日志会如实记下那个伪造身份。所以这里必须逐消息解析、逐消息重写。
    """
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", listen_port))
    srv.listen(64)
    log(event="listen", kind="http_identity", port=listen_port,
        target=f"{target[0]}:{target[1]}", identity=sorted(identity))
    while True:
        cli, addr = srv.accept()

        def handle(cli=cli, addr=addr):
            up = None
            n_req = 0
            try:
                up = socket.create_connection(target, timeout=15)
                cli.settimeout(30)
                up.settimeout(30)
                cbuf = b""
                ubuf = b""
                while True:
                    head, cbuf = _read_until_headers(cli, cbuf)
                    if not head:
                        break
                    n_req += 1
                    try:
                        assert_canonical_head(head)          # 纵深：裸 LF/CR
                        req = parse_request(head)            # 主控：与网关同一个解析器
                        assert_unambiguous_framing(head, req)
                    except ProtocolViolation as pv:
                        # 留痕：这不是"格式不规范"，这是身份伪造/请求走私的**攻击特征**（N-91）。
                        log(event="head_not_canonical", label=label, client=addr[0],
                            requests=n_req, detail=str(pv))
                        cli.sendall(b"HTTP/1.1 400 Bad Request\r\n"
                                    b"Content-Length: 0\r\nConnection: close\r\n\r\n")
                        break
                    up.sendall(serialize_identity(req, identity))
                    # 体的边界**取 h11 已经解析好的那份**，不再按字节重切一遍 ——
                    # 重切就是第二个解析器，而第二个解析器就是下一个走私洞。
                    _relay_body(cli, up, head, cbuf, headers=req.headers)
                    cbuf = b""
                    rhead, ubuf = _read_until_headers(up, ubuf)
                    if not rhead:
                        break
                    cli.sendall(rhead)
                    _relay_body(up, cli, rhead, ubuf)
                    ubuf = b""
                log(event="http_identity", label=label, client=addr[0], requests=n_req)
            except Exception as e:      # noqa: BLE001
                log(event="http_identity_fail", label=label, client=addr[0],
                    requests=n_req, error=str(e))
            finally:
                for s in (cli, up):
                    try:
                        s and s.close()
                    except OSError:
                        pass
        threading.Thread(target=handle, daemon=True).start()


# --------------------------------------------------------------- 模型反向代理（裁定 (a)）

#: 每 run 的预算上限。由 registry 按配置定，compose 注入。
#: 0 / None = 不限（**只在自测里用**：生产必须有闸，否则一次跑飞就烧掉整轮预算）。
_BUDGET = {"max_calls": 0, "max_tokens": 0, "calls": 0, "tokens": 0}
_BUDGET_LOCK = threading.Lock()
_LLM_LOG_PATH = "/var/log/gb/llm_log.jsonl"


def llm_log(**kw) -> None:
    """逐请求记 request/response/usage。**Authorization 剥掉再落盘。**

    这份日志是 **harness 无关的轨迹源**（裁定 2026-09-04）：
    Steps 从这里取（模型调用序列），不再逐 harness 写轨迹提取器 ——
    逐 harness 的提取器有几个 harness 就有几种漂法，而两臂经的是同一个边车。
    """
    rec = {"ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
           "task_id": _TASK_ID, **kw}
    try:
        with _LOCK:
            with open(_LLM_LOG_PATH, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:      # noqa: BLE001
        # **写失败必须响**。先前这里是 `except OSError: pass`，而 `_now()` 根本不存在
        # （`log()` 是内联时间戳）—— 于是每次调用都 NameError，被 `handle` 的外层
        # except 吞掉：**响应正常返回、模型正常答、而证据源一条都没写**。
        # 实测抓到（2026-09-04 端到端第一次跑）。
        # 证据源静默写不出来，与「这次运行没调过模型」在数值上不可区分（D-06 的形态）。
        log(event="llm_log_write_failed", error=f"{type(e).__name__}: {e}",
            path=_LLM_LOG_PATH)


def _strip_auth(head: bytes) -> bytes:
    out = []
    for line in head.split(b"\r\n"):
        if line.lower().startswith(b"authorization:"):
            out.append(b"authorization: <stripped>")
        else:
            out.append(line)
    return b"\r\n".join(out)


def _replace_auth(head: bytes, real_key: str, upstream: str) -> bytes:
    """把占位 key 换成真 key，并把 Host 改成上游。**真 key 只在这一行出现。**"""
    lines = head.split(b"\r\n")
    out = []
    seen_auth = False
    for line in lines:
        low = line.lower()
        if low.startswith(b"authorization:"):
            seen_auth = True
            out.append(f"authorization: Bearer {real_key}".encode())
        elif low.startswith(b"host:"):
            out.append(f"host: {upstream}".encode())
        elif low.startswith(b"accept-encoding:"):
            out.append(b"accept-encoding: identity")   # 便于抽 usage，不必解压
        else:
            out.append(line)
    if not seen_auth and out:
        out.insert(1, f"authorization: Bearer {real_key}".encode())
    return b"\r\n".join(out)


def _client_key(head: bytes) -> str | None:
    v = _header_value(head, "authorization")
    if not v:
        return None
    return v.split(None, 1)[-1].strip() if " " in v else v.strip()


def _budget_check() -> str | None:
    with _BUDGET_LOCK:
        if _BUDGET["max_calls"] and _BUDGET["calls"] >= _BUDGET["max_calls"]:
            return f"calls={_BUDGET['calls']} 已达上限 {_BUDGET['max_calls']}"
        if _BUDGET["max_tokens"] and _BUDGET["tokens"] >= _BUDGET["max_tokens"]:
            return f"tokens={_BUDGET['tokens']} 已达上限 {_BUDGET['max_tokens']}"
        return None


def _budget_add(calls: int = 0, tokens: int = 0) -> dict:
    with _BUDGET_LOCK:
        _BUDGET["calls"] += calls
        _BUDGET["tokens"] += tokens
        return {"calls": _BUDGET["calls"], "tokens": _BUDGET["tokens"]}


def _read_body_capture(src, dst, head: bytes, pre: bytes, cap: int = 2_000_000) -> bytes:
    """边转发边**有界**留一份副本 —— 留副本是为了抽 usage，
    有界是因为一次流式响应可以很大，而我们只需要它的尾巴。"""
    import io as _io
    buf = _io.BytesIO()

    class _Tee:
        def sendall(self, b):
            if buf.tell() < cap:
                buf.write(b[: cap - buf.tell()])
            dst.sendall(b)

    _relay_body(src, _Tee(), head, pre)
    return buf.getvalue()


def _dechunk(raw: bytes) -> bytes:
    """把 `Transfer-Encoding: chunked` 的分块框架去掉。

    **为什么需要它**：`_read_body_capture` 留的是**线路上的原始字节**，
    chunked 响应里夹着分块长度行 —— `json.loads` 当然解析不了，
    于是 `usage` 抽出来是 `{}`。而 `usage` 正是 §13.4「自报 tokens 要有网络侧佐证」
    的那一侧证据：抽不到就等于那条交叉核**没有数据源**，
    而它表现为「这次运行的 usage 是空的」，与「上游没返回 usage」不可分。
    实测抓到（2026-09-04 端到端第二次跑：DeepSeek 的响应是 chunked）。
    """
    out = bytearray()
    i = 0
    while i < len(raw):
        j = raw.find(b"\r\n", i)
        if j < 0:
            break
        try:
            n = int(raw[i:j].split(b";", 1)[0].strip() or b"0", 16)
        except ValueError:
            return raw            # 不是 chunked，原样返回
        if n == 0:
            break
        out += raw[j + 2: j + 2 + n]
        i = j + 2 + n + 2
    return bytes(out) if out else raw


class _ChunkedDecoder:
    """**边收边**去掉 chunked 框架的状态机（任意切分边界都对）。

    `_dechunk` 只能整段做，而整段做要求整段都在手里 —— 那正是留不下尾巴的原因。
    """

    def __init__(self) -> None:
        self._buf = b""
        self._need = 0        # 当前块还差几个数据字节
        self._skip = 0        # 还要吞掉几个字节的块尾 CRLF
        self.done = False
        self.broken = False

    def feed(self, data: bytes) -> bytes:
        if self.done or self.broken:
            return b""
        self._buf += data
        out = bytearray()
        while self._buf:
            if self._skip:
                k = min(self._skip, len(self._buf))
                self._buf = self._buf[k:]
                self._skip -= k
                continue
            if self._need:
                k = min(self._need, len(self._buf))
                out += self._buf[:k]
                self._buf = self._buf[k:]
                self._need -= k
                if self._need == 0:
                    self._skip = 2
                continue
            j = self._buf.find(b"\r\n")
            if j < 0:
                if len(self._buf) > 64:        # 块长行不可能这么长 —— 框架坏了
                    self.broken = True
                break
            try:
                n = int(self._buf[:j].split(b";", 1)[0].strip() or b"0", 16)
            except ValueError:
                self.broken = True
                break
            self._buf = self._buf[j + 2:]
            if n == 0:
                self.done = True               # 末块；trailer 不要
                break
            self._need = n
        return bytes(out)


def _capture_head_tail(src, dst, head: bytes, pre: bytes, *,
                       cap: int = 2_000_000, tail_cap: int = 262_144):
    """边转发边留**头**与**尾**两份有界副本（chunked 边收边去框架）。

    返回 `(head_bytes, tail_bytes, total)`：`total` 是解框后的真实体长度 ——
    `total > len(head_bytes)` 就是「这次被截过」，日志里据此说得清
    「usage 抽不到」是上游没给还是我们没留住。
    """
    import io as _io
    te = (_header_value(head, "transfer-encoding") or "").lower()
    dec = _ChunkedDecoder() if "chunked" in te else None
    buf = _io.BytesIO()
    tail = bytearray()
    st = {"n": 0}

    class _Tee:
        def sendall(self, b):
            dst.sendall(b)                      # 先转发：留副本失败也不该拖累被测方
            body = dec.feed(b) if dec is not None else b
            if not body:
                return
            st["n"] += len(body)
            room = cap - buf.tell()
            if room > 0:
                buf.write(body[:room])
            tail.extend(body)
            if len(tail) > tail_cap:
                del tail[:len(tail) - tail_cap]

    _relay_body(src, _Tee(), head, pre)
    return buf.getvalue(), bytes(tail), st["n"]


#: usage 的键名在两套 API 下不同：Chat Completions 是
#: `prompt_tokens` / `completion_tokens`，Responses API 是 `input_tokens` / `output_tokens`。
#: 归一到前者 —— 下游（`llm_trace.usage_totals`）只认一套。
_USAGE_ALIASES = {"input_tokens": "prompt_tokens", "output_tokens": "completion_tokens"}

#: 「命中缓存的输入 token」在三种形状下的名字。OpenAI 两套 API 把它嵌在 `*_tokens_details`
#: 里（`cached_tokens`），Anthropic Messages 平铺成 `cache_read_input_tokens`，
#: DeepSeek 的 Chat Completions 平铺成 `prompt_cache_hit_tokens`。
#: 归一到 `cached_prompt_tokens`。**与 `runner/c42/llm_trace.CACHED_KEYS` 逐字同源**
#: （`ops/test_llm_usage_shapes.py` 盯着相等）—— 本文件要单文件挂进边车容器，不能 import 它。
_CACHED_KEYS: tuple[str, ...] = ("cached_tokens", "cache_read_input_tokens",
                                 "prompt_cache_hit_tokens")

#: 嵌套 details 的容器名（OpenAI Chat Completions / Responses 各一个）。
_DETAIL_KEYS: tuple[str, ...] = ("prompt_tokens_details", "input_tokens_details")

#: `wire_shape` 的取值域。**它是记录里的一个字段，不是判据** —— 用途是让
#: 「这条为什么没有 usage」可答：形状认不出来与上游没给，是两个结论。
WIRE_SHAPES: tuple[str, ...] = ("chat_completions", "responses",
                                "anthropic_messages", "unknown")


def _norm_usage(u: dict) -> dict:
    """把任一形状的 `usage` 归一到 `prompt_tokens / completion_tokens /
    cached_prompt_tokens / total_tokens`。**原始键一律保留** ——
    `runner/pricing.py::CACHE_HIT_KEYS` 认的是原始名，改成只留归一键会让 `$` 列变。
    """
    out = {}
    for k, v in u.items():
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            out[_USAGE_ALIASES.get(k, k)] = int(v)
    cached = None
    for dk in _DETAIL_KEYS:                       # 嵌套那一份（OpenAI 两套 API）
        d = u.get(dk)
        if not isinstance(d, dict):
            continue
        for ck in _CACHED_KEYS:
            v = d.get(ck)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                cached = int(v)
                break
        if cached is not None:
            break
    if cached is None:                            # 平铺那一份（Anthropic / DeepSeek）
        for ck in _CACHED_KEYS:
            v = out.get(ck)
            if isinstance(v, int):
                cached = v
                break
    if cached is not None:
        out["cached_prompt_tokens"] = cached
    if "total_tokens" not in out and ("prompt_tokens" in out or "completion_tokens" in out):
        out["total_tokens"] = out.get("prompt_tokens", 0) + out.get("completion_tokens", 0)
    return out


def _find_usage(obj) -> dict:
    """在任意深度找 `usage` 对象。

    **为什么要递归**：Responses API 的 usage 嵌在 `response.usage` 里
    （SSE 的 `response.completed` 事件），而 Chat Completions 是顶层 `usage`。
    只认顶层的第一版在 Codex CLI 上抽出来是 `None` —— 而那让交叉核报了一条
    **假的 `telemetry_unbacked`**（实测：真调了 3 次、codex 自报 8743 tokens）。
    假 finding 比抽不到更坏：它指着被测方说谎，而说谎的是我们的抽取器。
    """
    if isinstance(obj, dict):
        u = obj.get("usage")
        if isinstance(u, dict):
            n = _norm_usage(u)
            if n:
                return n
        for v in obj.values():
            got = _find_usage(v)
            if got:
                return got
    elif isinstance(obj, list):
        for v in obj:
            got = _find_usage(v)
            if got:
                return got
    return {}


def _find_usage_raw(obj) -> dict:
    """`_find_usage` 的**不归一**版本 —— 返回上游原样的 `usage` 对象。

    要原样是因为流式要**跨事件合并**：合并必须在归一之前做，
    否则每个事件各自补出来的 `total_tokens` 会互相覆盖成假数
    （Anthropic 的 `message_start` 只有 input、`message_delta` 只有 output，
    各自补的 total 都是半个）。
    """
    if isinstance(obj, dict):
        u = obj.get("usage")
        if isinstance(u, dict) and any(
                isinstance(v, (int, float)) and not isinstance(v, bool) for v in u.values()):
            return u
        for v in obj.values():
            got = _find_usage_raw(v)
            if got:
                return got
    elif isinstance(obj, list):
        for v in obj:
            got = _find_usage_raw(v)
            if got:
                return got
    return {}


def _merge_raw(a: dict, b: dict) -> dict:
    """把后一个事件的 usage 并进前一个。**后来的非零值赢；零不覆盖已有的非零。**

    为什么不是「后来的一律赢」：Anthropic 的 `message_start` 给 `input_tokens`
    与 `cache_read_input_tokens`，`message_delta` 只给最终的 `output_tokens`
    （有的版本还带一个 `input_tokens: 0`）。一律后来者赢会把 prompt 抹成 0，
    而 0 与「上游没给」在下游不可分 —— 那正是这张卡要消掉的那种假数。
    """
    out = dict(a)
    for k, v in b.items():
        if k not in out:
            out[k] = v
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            if v:
                out[k] = v
        elif isinstance(v, dict) and v:
            out[k] = _merge_raw(out[k] if isinstance(out.get(k), dict) else {}, v)
    return out


def _raw_usage_of(body: bytes) -> dict:
    """一段响应体里的原始 usage：先当整份 JSON 试，再按 SSE **从前往后**逐事件合并。"""
    txt = body.decode("utf-8", "replace")
    try:
        got = _find_usage_raw(json.loads(txt))
        if got:
            return got
    except Exception:      # noqa: BLE001
        pass
    raw: dict = {}
    for line in txt.splitlines():
        if not line.startswith("data:"):
            continue
        chunk = line[5:].strip()
        if chunk in ("", "[DONE]"):
            continue
        try:
            obj = json.loads(chunk)
        except Exception:      # noqa: BLE001
            continue           # 被截断的最后半行：跳过，不是错误
        got = _find_usage_raw(obj)
        if got:
            raw = _merge_raw(raw, got)
    return raw


def _wire_shape(path: str, raw: dict) -> str:
    """这条走的是哪种 wire 形状。**先看 path**（确定的），认不出再看键名（推的）。"""
    p = (path or "").split("?", 1)[0].rstrip("/").lower()
    if p.endswith("/chat/completions"):
        return "chat_completions"
    if p.endswith("/responses"):
        return "responses"
    if p.endswith("/messages") or p.endswith("/messages/count_tokens"):
        return "anthropic_messages"
    if "cache_read_input_tokens" in raw or "cache_creation_input_tokens" in raw:
        return "anthropic_messages"
    if "prompt_tokens" in raw:
        return "chat_completions"
    if "input_tokens" in raw:
        return "responses"
    return "unknown"


def usage_from_parts(parts, path: str = "") -> dict:
    """从若干段响应体（头 + 尾）里抽出**归一后**的 usage，并标 `wire_shape`。

    分成「头 + 尾」两段是因为**流式响应的 usage 在最后一个事件里**，而我们只留有界副本：
    留头不留尾时，一次超过副本上限的流式响应抽出来是 `{}` ——
    而 `{}` 与「上游没给 usage」在下游不可分（`llm_trace` 的三态就白设了）。
    """
    raw: dict = {}
    for p in parts:
        if not p:
            continue
        raw = _merge_raw(raw, _raw_usage_of(p))
    if not raw:
        return {}
    out = _norm_usage(raw)
    out["wire_shape"] = _wire_shape(path, raw)
    return out


def _extract_usage(body: bytes, path: str = "") -> dict:
    """从响应里抽 `usage`。三种 wire 形状 + 流式，归一到同一组键。

    * **Chat Completions**：`usage.prompt_tokens / completion_tokens`，
      缓存命中是 `prompt_cache_hit_tokens`（DeepSeek）或
      `prompt_tokens_details.cached_tokens`（OpenAI）；
    * **Responses API**：`usage.input_tokens / output_tokens`
      （+ `input_tokens_details.cached_tokens`），SSE 里在 `response.completed` 上；
    * **Anthropic Messages**：`usage.input_tokens / output_tokens`
      （+ `cache_read_input_tokens`），SSE 里**跨两个事件**
      （`message_start` 给 input、`message_delta` 给 output）—— 所以要合并不是取最后一个。
    """
    return usage_from_parts([body], path)


def _deny_http(cli, status: int, reason: str, detail: str, **extra) -> None:
    """拒绝，并**以 access_log 同格式**留一条记录（裁定 2026-09-04）。"""
    payload = json.dumps({"error": "denied", "reason": reason, "detail": detail},
                         ensure_ascii=False).encode()
    cli.sendall(b"HTTP/1.1 %d Denied\r\ncontent-type: application/json\r\n"
                b"content-length: %d\r\nconnection: close\r\n\r\n%s"
                % (status, len(payload), payload))
    llm_log(decision="deny", reason=reason, status=status, detail=detail, **extra)


def model_reverse_proxy(listen_port: int, upstream: str, real_key: str, *,
                        path_prefix: str = "/v1") -> None:
    """**OpenAI 兼容反向代理**（裁定 (a)，2026-09-04）。

    agent 的 `base_url` 指到这里（任务网内**明文**），边车附 `Authorization`
    后对上游起 TLS。**真 key 不进任务容器** —— 容器里只有占位串。

    为什么不是 CONNECT + 加头：CONNECT 隧道里是 TLS，边车没法往里加头
    （要么做中间人、要么分发 CA）。反向代理还顺带解决三件事：
    usage 可见（§13.4 的网络侧佐证）、Steps 有 harness 无关的来源、预算闸有落点。

    **上游主机名校验落在这里的出站 TLS 客户端** —— 不再靠 CONNECT 时的 SNI 比对。
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", listen_port))
    srv.listen(64)
    log(event="listen", kind="model_reverse_proxy", port=listen_port,
        upstream=upstream, path_prefix=path_prefix,
        max_calls=_BUDGET["max_calls"], max_tokens=_BUDGET["max_tokens"])

    def handle(cli, addr):
        up = None
        try:
            cli.settimeout(300)
            head, pre = _read_until_headers(cli, b"")
            if not head:
                return
            first = head.split(b"\r\n", 1)[0].decode("latin-1", "replace")
            method, _, rest = first.partition(" ")
            path = rest.rsplit(" ", 1)[0]

            key = _client_key(head)
            if key and key != PLACEHOLDER_KEY:
                # agent 自带了一把 key —— 那是一条**未声明的资源**：
                # 它可以绕开预算闸，也让 usage 归属对不上。
                _deny_http(cli, 403, "foreign_credential",
                           "容器里只该有占位 key；自带凭据是未声明的资源",
                           path=path, method=method)
                return
            over = _budget_check()
            if over:
                _deny_http(cli, 429, "budget_exceeded", over, path=path, method=method,
                           budget=dict(_BUDGET))
                return

            up_raw = socket.create_connection((upstream, 443), timeout=30)
            up = ctx.wrap_socket(up_raw, server_hostname=upstream)
            up.settimeout(300)
            up.sendall(_replace_auth(head, real_key, upstream))
            req_body = _read_body_capture(cli, up, head, pre)

            rhead, upre = _read_until_headers(up, b"")
            if not rhead:
                _deny_http(cli, 502, "upstream_no_response", "上游没有响应头",
                           path=path)
                return
            cli.sendall(rhead)
            resp_body, resp_tail, resp_len = _capture_head_tail(up, cli, rhead, upre)
            truncated = resp_len > len(resp_body)
            # 截过就把**尾巴也喂进去** —— 流式的 usage 在最后一个事件里。
            usage = usage_from_parts([resp_body] + ([resp_tail] if truncated else []), path)
            tot = int(usage.get("total_tokens") or 0)
            budget = _budget_add(calls=1, tokens=tot)
            status = int(rhead.split(b" ", 2)[1]) if b" " in rhead else 0
            extra = {}
            if not usage:
                # **「没有 usage」要说得出是哪一种**：上游拒绝（gemini-cli 的 404）、
                # 体是空的、还是体里就没有。三者都不是 0，而它们的结论各不相同。
                extra["usage_absent"] = ("upstream_error" if status >= 400 else
                                         "empty_body" if not resp_len else
                                         "truncated_no_usage" if truncated else "no_usage_in_body")
                extra["wire_shape"] = _wire_shape(path, {})
            llm_log(decision="allow", status=status, method=method, path=path,
                    upstream=upstream, usage=usage, budget=budget,
                    response_bytes=resp_len, response_truncated=truncated, **extra,
                    request_head=_strip_auth(head).decode("latin-1", "replace")[:2000],
                    request_body=req_body.decode("utf-8", "replace")[:20000],
                    response_body=resp_body.decode("utf-8", "replace")[:20000])
        except Exception as e:      # noqa: BLE001
            # 二次失败陷阱：`llm_log` 自己若抛，这里再调它一次就把异常又扔一遍，
            # 线程静默死掉而**第一现场的错误信息丢了**。所以兜到 `log()`。
            try:
                llm_log(decision="deny", reason="proxy_error", detail=str(e)[:300])
            except Exception:      # noqa: BLE001
                log(event="model_proxy_error", error=str(e)[:300])
        finally:
            for sk in (cli, up):
                try:
                    sk and sk.close()
                except OSError:
                    pass

    while True:
        c, a2 = srv.accept()
        threading.Thread(target=handle, args=(c, a2), daemon=True).start()


def forward_server(listen_port: int, target: tuple[str, int], label: str) -> None:
    """纯 TCP 转发 —— 给数据网关用。任务容器无需配代理。

    绑 ``0.0.0.0`` 是**容器内**的 0.0.0.0：本服务**不发布任何端口**，
    compose lint 的 L-6 会拦住任何给代理服务加 ``ports:`` 的改动（D-07）。
    """
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", listen_port))
    srv.listen(64)
    log(event="listen", kind="forward", port=listen_port, target=f"{target[0]}:{target[1]}")
    while True:
        cli, addr = srv.accept()

        def handle(cli=cli, addr=addr):
            t0 = time.time()
            try:
                up = socket.create_connection(target, timeout=15)
            except OSError as e:
                log(event="forward_fail", label=label, client=addr[0], error=str(e))
                cli.close()
                return
            n = pipe(cli, up)
            log(event="forward", label=label, client=addr[0],
                target=f"{target[0]}:{target[1]}", bytes=n,
                elapsed_ms=round((time.time() - t0) * 1000))
        threading.Thread(target=handle, daemon=True).start()


def connect_proxy(listen_port: int, *, bind_host: str = "0.0.0.0",
                  on_ready=None) -> None:
    """HTTP CONNECT 代理，按**主机名 + SNI** 白名单。默认拒绝。

    ``bind_host`` 默认 ``0.0.0.0`` 是**容器内**的 0.0.0.0（本服务不发布端口，见 L-6）；
    集成测试传 ``127.0.0.1`` 并用 ``on_ready(port)`` 取实际端口。
    """
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((bind_host, listen_port))
    srv.listen(64)
    listen_port = srv.getsockname()[1]
    log(event="listen", kind="connect_proxy", port=listen_port,
        allow=sorted(ALLOW), allow_ports=sorted(ALLOW_PORTS),
        require_sni_match=REQUIRE_SNI_MATCH)
    if on_ready is not None:
        on_ready(listen_port)
    while True:
        cli, addr = srv.accept()
        threading.Thread(target=_handle_connect, args=(cli, addr), daemon=True).start()


def _deny(cli: socket.socket, code: bytes, **kw) -> None:
    log(event="deny", **kw)
    try:
        cli.sendall(b"HTTP/1.1 " + code + b"\r\n\r\n")
    except OSError:
        pass
    try:
        cli.close()
    except OSError:
        pass


def _handle_connect(cli: socket.socket, addr) -> None:
    try:
        cli.settimeout(15)
        head = b""
        while b"\r\n\r\n" not in head and len(head) < 8192:
            chunk = cli.recv(4096)
            if not chunk:
                cli.close()
                return
            head += chunk
        first = head.split(b"\r\n", 1)[0].decode("latin1")
        parts = first.split()
        if len(parts) < 2 or parts[0].upper() != "CONNECT":
            _deny(cli, b"405 Method Not Allowed",
                  reason="not_connect", request=first[:200], client=addr[0])
            return
        hostport = parts[1]
        host, _, port_s = hostport.rpartition(":")
        host = host.lower().rstrip(".")
        port = int(port_s) if port_s.isdigit() else 443
        if host not in ALLOW or port not in ALLOW_PORTS:
            _deny(cli, b"403 Forbidden", reason="not_in_allowlist",
                  host=host, port=port, client=addr[0], allow=sorted(ALLOW))
            return

        try:
            up = socket.create_connection((host, port), timeout=15)
        except OSError as e:
            log(event="connect_fail", host=host, port=port, error=str(e), client=addr[0])
            try:
                cli.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            finally:
                cli.close()
            return
        cli.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")

        # ---- SNI 校验：CONNECT 说的和 TLS 里握的必须是同一个域名 ----
        # 客户端要等到收到 200 才会发 ClientHello，所以只能在这里校。
        pre = b""
        if REQUIRE_SNI_MATCH:
            pre, sni = read_client_hello(cli)
            if sni != host:                       # 含 sni is None：**fail closed**
                up.close()
                _deny(cli, b"403 Forbidden", reason="sni_mismatch",
                      host=host, sni=sni, port=port, client=addr[0])
                return
            up.sendall(pre)                       # 原样补发，否则握手丢了开头

        t0 = time.time()
        n = pipe(cli, up)
        log(event="connect", host=host, port=port, bytes=n + len(pre), client=addr[0],
            sni_checked=REQUIRE_SNI_MATCH,
            elapsed_ms=round((time.time() - t0) * 1000))
    except Exception as e:      # noqa: BLE001  代理不能因为一个坏请求就死
        log(event="error", error=f"{type(e).__name__}: {e}", client=addr[0])
        try:
            cli.close()
        except OSError:
            pass


def main() -> int:
    global _LOG_PATH, _TASK_ID
    p = argparse.ArgumentParser(description="卡 4.1 出向代理")
    p.add_argument("--gateway", default="192.168.1.48:18080")
    p.add_argument("--gateway-port", type=int, default=18080)
    p.add_argument("--proxy-port", type=int, default=3128)
    p.add_argument("--log", default="/var/log/egress.jsonl")
    p.add_argument("--model-port", type=int, default=8081,
                   help="模型反向代理的监听端口。agent 的 base_url 指到它。")
    p.add_argument("--model-upstream", default="",
                   help="上游主机名。必须在 MODEL_UPSTREAMS 里（由 registry 生成）。")
    p.add_argument("--llm-log", default="/var/log/gb/llm_log.jsonl")
    p.add_argument("--max-calls", type=int, default=0)
    p.add_argument("--max-tokens", type=int, default=0)
    p.add_argument("--key-env", default="GENEBENCH_MODEL_API_KEY",
                   help="真 key 的环境变量名。**只注给边车服务**，任务容器看不到。")
    # `--inject-identity` **已删除**（裁定 2026-09-05，N-92）：它曾是可选的，
    # 不给就退回纯 TCP 转发 —— 那条路没有身份保证，而**没有一条 lint 断言 compose 里有它**。
    # 整条 ID-1/ID-2 于是依赖「模板恰好写着这个标志」，改掉它会静默退回原样透传。
    # 去掉可选性：身份注入永远开。要一条不能被静默摘掉的保证，就不能让它是个开关。
    a = p.parse_args()
    _LOG_PATH = a.log
    _TASK_ID = os.environ.get("GENEBENCH_TASK_ID", "unknown")
    host, _, port = a.gateway.partition(":")
    identity = {env: os.environ.get(env, "") for env in IDENTITY_HEADERS.values()}
    missing = [k for k, v in identity.items() if not v]
    if missing:
        # **宁可不起，不可注错**：身份缺一个，网关日志就会缺一列，
        # 而缺列在结算侧看起来与「这次运行没发过请求」不可区分（D-06）。
        print(f"边车拒绝启动：身份环境变量缺 {missing} —— "
              f"它们由 compose 从 run dir 渲染，缺了说明注入器没写对", file=sys.stderr)
        return 2
    threading.Thread(target=http_identity_proxy,
                     args=(a.gateway_port, (host, int(port)), "gateway", identity),
                     daemon=True).start()
    threading.Thread(target=connect_proxy, args=(a.proxy_port,), daemon=True).start()

    # ---- 模型反向代理（裁定 (a)）----
    global _LLM_LOG_PATH
    _LLM_LOG_PATH = a.llm_log
    _BUDGET["max_calls"] = a.max_calls
    _BUDGET["max_tokens"] = a.max_tokens
    if a.model_upstream:
        if a.model_upstream not in MODEL_UPSTREAMS:
            print(f"边车拒绝启动：上游 {a.model_upstream} 不在允许集 "
                  f"{sorted(MODEL_UPSTREAMS)} —— 允许集由 registry 生成，"
                  f"手改这里等于绕过 §15 的同源约束", file=sys.stderr)
            return 2
        real = os.environ.get(a.key_env, "")
        if not real:
            # **宁可不起，不可让占位串到上游**：占位串会被上游当成一把坏 key，
            # 于是每次调用都 401，而 401 看起来像「模型不配合」而不是「我们没配 key」。
            print(f"边车拒绝启动：{a.key_env} 为空 —— 真 key 由 runner 从 "
                  f"~/.config/genebench/secrets.env 读入并**只注给边车**", file=sys.stderr)
            return 2
        threading.Thread(target=model_reverse_proxy,
                         args=(a.model_port, a.model_upstream, real),
                         daemon=True).start()

    log(event="ready", gateway=a.gateway, allow=sorted(ALLOW),
        model_upstream=a.model_upstream or None, model_port=a.model_port,
        max_calls=a.max_calls, max_tokens=a.max_tokens,
        require_sni_match=REQUIRE_SNI_MATCH)
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    raise SystemExit(main())
