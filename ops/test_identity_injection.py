"""卡 4.3 §6.5：身份在源头注入（ID-1..ID-5）。

**为什么这件事非做不可**：两个身份头是**任务容器自己填的**（样例 agent 直接
`os.environ.get("GENEBENCH_CONFIG_ID")` 塞进请求头）。容器内环境变量可写、请求头可改，
所以切片键的源头是**被测方的自报值**。校验层（N-36）能抓「自报值 ≠ 本次运行的真值」，
抓不到「自报值被改成**另一次运行的**合法真值」—— 两臂并发跑同一个 config 时，
strict 臂可以把自己的请求记到 open 臂名下，两边的日志都还「合法」。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from gateway import access_log                                   # noqa: E402
from runner.c41.egress_proxy import (IDENTITY_HEADERS, STRIP_PREFIXES,  # noqa: E402
                                     rewrite_identity)

TRUTH = {"GENEBENCH_TASK_ID": "s1-cor-01", "GENEBENCH_CONFIG_ID": "cfg-a",
         "GENEBENCH_RUN_ID": "s1-cor-01.open.cfg-a.r01", "GENEBENCH_ARM": "open"}


def _head(*extra: bytes) -> bytes:
    lines = [b"GET /calendar?start_date=2026-07-01 HTTP/1.1", b"Host: gateway"] + list(extra)
    return b"\r\n".join(lines) + b"\r\n\r\n"


def _headers_of(raw: bytes) -> list[tuple[str, str]]:
    out = []
    for line in raw.split(b"\r\n")[1:]:
        if not line:
            continue
        k, _, v = line.partition(b":")
        out.append((k.strip().lower().decode(), v.strip().decode()))
    return out


# --------------------------------------------------------------- ID-1 先剥后注

def test_id1_forged_identity_headers_are_stripped_not_appended():
    """**先剥后注**。只追加不删除时，starlette 的 `.get()` 取**第一个**同名头 ——
    客户端抢先写一份就赢了，注入等于没做。"""
    got = _headers_of(rewrite_identity(
        _head(b"x-genebench-task-id: FORGED", b"x-genebench-config-id: FORGED-CFG"), TRUTH))
    tid = [v for k, v in got if k == "x-genebench-task-id"]
    assert tid == ["s1-cor-01"], f"应恰好一个且是真值，实际 {tid}"
    assert "FORGED" not in str(got)


def test_id1_duplicate_and_mixed_case_forgeries_are_all_stripped():
    """含**重复出现的同名头**、大小写变体 —— 全类剥掉。"""
    got = _headers_of(rewrite_identity(
        _head(b"x-genebench-task-id: A", b"X-GENEBENCH-TASK-ID: B",
              b"X-Genebench-Task-Id: C", b"x-gb-run-id: forged",
              b"X-GB-ARM: strict"), TRUTH))
    assert [v for k, v in got if k == "x-genebench-task-id"] == ["s1-cor-01"]
    assert [v for k, v in got if k == "x-gb-arm"] == ["open"]
    for bad in ("A", "B", "C", "forged", "strict"):
        assert bad not in [v for _, v in got], f"伪造值 {bad} 没被剥掉"


def test_id1_first_header_wins_semantics_is_the_reason():
    """把「为什么必须剥」钉成一条测试：`.get()` 语义下第一个同名头赢。
    这不是推断 —— starlette 的 Headers 就是这么取的（规格 §6.5 ID-1 实测）。"""
    raw = [("x-genebench-task-id", "FAKE"), ("x-genebench-task-id", "REAL")]
    first = next(v for k, v in raw if k == "x-genebench-task-id")
    assert first == "FAKE", "只追加不剥时，客户端抢先写的那份会赢"


@pytest.mark.parametrize("framing,expect", [
    (b"Content-Length: 42", ("content-length", "42")),
    (b"Transfer-Encoding: chunked", ("transfer-encoding", "chunked")),
])
def test_body_framing_headers_are_untouched(framing, expect):
    """Transfer-Encoding / Content-Length **照搬不改** —— 注入器不许改数据面语义。

    2026-09-05 起两者**分开测**：并存已被 `assert_unambiguous_framing` 拒
    （见 `test_te_and_cl_together_are_refused`），原来那条一次喂两个的用例
    现在会被正确地拒掉，留着它就变成了"测拒绝"而不是"测照搬"。
    """
    got = _headers_of(rewrite_identity(
        _head(framing, b"Content-Type: application/json"), TRUTH))
    assert expect in got
    assert ("content-type", "application/json") in got


def test_request_line_is_untouched():
    out = rewrite_identity(_head(b"x-gb-arm: forged"), TRUTH)
    assert out.split(b"\r\n")[0] == b"GET /calendar?start_date=2026-07-01 HTTP/1.1"


def test_non_identity_headers_survive():
    got = _headers_of(rewrite_identity(_head(b"Accept: */*", b"User-Agent: probe"), TRUTH))
    assert ("accept", "*/*") in got and ("user-agent", "probe") in got


# --------------------------------------------------------------- ID-2 值来自边车 env

def test_id2_values_come_from_the_sidecar_env_not_the_request():
    """边车 env 由 compose 从 run dir 渲染，任务容器与它**不共享文件系统也不共享 env**。"""
    assert set(IDENTITY_HEADERS.values()) == {
        "GENEBENCH_TASK_ID", "GENEBENCH_CONFIG_ID", "GENEBENCH_RUN_ID", "GENEBENCH_ARM"}
    partial = {"GENEBENCH_TASK_ID": "s1-cor-01"}
    got = _headers_of(rewrite_identity(_head(b"x-gb-arm: forged"), partial))
    assert ("x-genebench-task-id", "s1-cor-01") in got
    # env 里没有的字段**不注**，也不保留伪造值 —— 宁可缺，不可错
    assert not [v for k, v in got if k == "x-gb-arm"]


def test_strip_prefixes_cover_both_families():
    assert set(STRIP_PREFIXES) == {"x-genebench-", "x-gb-"}
    for h in IDENTITY_HEADERS:
        assert any(h.startswith(p) for p in STRIP_PREFIXES), f"{h} 不在剥离前缀内"


# --------------------------------------------------------------- ID-4 日志增列

def test_id4_access_log_has_run_id_and_arm_columns():
    """不加列，注进来的真值没有地方落。**加法**：默认 None，不动既有列。"""
    import inspect
    sig = inspect.signature(access_log.record).parameters
    assert "run_id" in sig and "arm" in sig
    assert sig["run_id"].default is None and sig["arm"].default is None
    # 只测**返回的那个 dict**（record 的文档字符串明说它是为此返回的）；
    # 落盘目录在 f01 上，开发机没有 —— 把 ensure_log_dir 指到 tmp，别让环境依赖混进判据。
    import tempfile, unittest.mock as _mock
    with tempfile.TemporaryDirectory() as d:
        with _mock.patch.object(access_log, "ensure_log_dir",
                                lambda: Path(d) / "access.jsonl"):
            entry = access_log.record(method="GET", path="/calendar", params={},
                                      as_of="2026-07-31", decision="allow", status=200,
                                      task_id="s1-cor-01", config_id="cfg-a",
                                      run_id="s1-cor-01.open.cfg-a.r01", arm="open")
    assert entry["run_id"] == "s1-cor-01.open.cfg-a.r01" and entry["arm"] == "open"
    for legacy in ("ts", "config_id", "task_id", "method", "path", "decision", "status"):
        assert legacy in entry, f"既有列 {legacy} 丢了"


def test_id3_run_id_is_the_slice_key_and_separates_arms():
    """ID-3：切片键退化为 run_id —— 它蕴含臂、配置与第几次重跑。
    **两臂并发同 config 也不串**：arm 不同则 run_id 不同。"""
    a = "s1-cor-01.strict.cfg-a.r01"
    b = "s1-cor-01.open.cfg-a.r01"
    assert a != b, "同 task 同 config 的两臂必须落在不同的切片键上"
    assert a.split(".")[0] == b.split(".")[0], "同一道题"
    assert a.split(".")[2] == b.split(".")[2], "同一个 config"


# --------------------------------------------------------------- ID-1 的端到端（T15 的本地形态）

@pytest.mark.skipif(True, reason="本机沙箱不许监听端口；这条的真形态是 f02 的 T15 "
                                  "（runner/f02/verify_container.py --only T15），"
                                  "它已经在真容器 + 真网关上跑过并抓到过反例")
def test_every_request_on_a_keepalive_connection_is_rewritten():
    """**同一 keep-alive 连接上的每一个请求**都要重新剥注。

    T15 在 f02 实测抓到过反例：只剥第一个、之后交给双向 splice 的实现，
    第二个请求带着伪造头原样到达网关，**网关日志如实记下了那个伪造身份**
    （`s9-forged-99` / `cfg-forged` / `strict`）。规格 §6.5 ID-1 预言的正是这个形态。
    """
    import socket
    import threading
    from runner.c41.egress_proxy import http_identity_proxy

    seen: list[bytes] = []
    up_srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    up_srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    up_srv.bind(("127.0.0.1", 0))
    up_srv.listen(4)
    up_port = up_srv.getsockname()[1]

    def upstream():
        conn, _ = up_srv.accept()
        conn.settimeout(10)
        buf = b""
        for _ in range(2):                       # 收两个请求，各回一个短响应
            while b"\r\n\r\n" not in buf:
                c = conn.recv(65536)
                if not c:
                    return
                buf += c
            head, _, buf = buf.partition(b"\r\n\r\n")
            seen.append(head)
            conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
        conn.close()

    threading.Thread(target=upstream, daemon=True).start()
    proxy_port = 0
    ps = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    ps.bind(("127.0.0.1", 0))
    proxy_port = ps.getsockname()[1]
    ps.close()
    threading.Thread(target=http_identity_proxy,
                     args=(proxy_port, ("127.0.0.1", up_port), "test", TRUTH),
                     daemon=True).start()
    import time
    time.sleep(0.4)

    cli = socket.create_connection(("127.0.0.1", proxy_port), timeout=10)
    forged = (b"GET /a HTTP/1.1\r\nHost: gw\r\nx-genebench-task-id: FORGED\r\n"
              b"x-gb-arm: strict\r\nContent-Length: 0\r\nConnection: keep-alive\r\n\r\n")
    cli.sendall(forged + forged)                 # **同一连接连发两个**
    cli.settimeout(10)
    got = b""
    try:
        while got.count(b"HTTP/1.1 200") < 2 and len(got) < 65536:
            c = cli.recv(65536)
            if not c:
                break
            got += c
    except socket.timeout:
        pass
    cli.close()
    time.sleep(0.3)

    assert len(seen) == 2, f"上游只收到 {len(seen)} 个请求 —— 第二个没被转发"
    for i, head in enumerate(seen, 1):
        text = head.decode("latin-1")
        assert "FORGED" not in text, f"第 {i} 个请求带着伪造 task_id 到了上游"
        assert "x-gb-arm: strict" not in text, f"第 {i} 个请求带着伪造 arm"
        assert "x-genebench-task-id: s1-cor-01" in text, f"第 {i} 个请求没注入真值"
        assert "x-gb-arm: open" in text, f"第 {i} 个请求没注入真 arm"


# ===================================================================== N-91
# **行界不一致 = 身份伪造**（2026-09-05 实测）
#
# 上面那 12 条全部用规范 CRLF 造请求，所以全部绿 —— 而边车在裸 LF 面前是敞开的。
# 判据要落在**不变式**上，不是落在「我想到的那个攻击串」上：
#
#     边车剥注之后，**上游解析器**看到的身份头，必须恰好等于边车注入的真值。
#
# 「上游解析器」在这里就用 h11 本尊（网关跑在 uvicorn/h11 上），
# 不用我自己再写一个 —— 自己写的那个会和边车犯同一个错，测出来永远是绿的。

import h11                                                          # noqa: E402

from runner.c41.egress_proxy import (ProtocolViolation,             # noqa: E402
                                     assert_canonical_head, _find_head_end)

IDENT = {"GENEBENCH_TASK_ID": "s8-cor-01", "GENEBENCH_CONFIG_ID": "oracle-real",
         "GENEBENCH_RUN_ID": "rid-real", "GENEBENCH_ARM": "strict"}

#: 一组**行界畸形**的请求。每一条都：边车若按 `\r\n` 切行就看不见伪造头，
#: 而 h11 看得见。第一条是 2026-09-05 实测打穿的那一条。
SMUGGLED = {
    "bare_lf_after_benign": (b"GET /sim/state HTTP/1.1\r\n"
                             b"X-Whatever: a\nx-genebench-config-id: cfg-FORGED\r\n"
                             b"Host: gateway\r\n\r\n"),
    "bare_lf_chain": (b"GET /bars HTTP/1.1\r\n"
                      b"Accept: */*\nx-genebench-task-id: s1-cor-01\n"
                      b"x-gb-run-id: rid-FORGED\r\nHost: gateway\r\n\r\n"),
    "lf_terminated_block": (b"GET /sim/log HTTP/1.1\n"
                            b"Host: gateway\nx-genebench-config-id: cfg-FORGED\n\n"),
}


def _as_h11_sees(wire: bytes) -> list[tuple[str, str]]:
    conn = h11.Connection(h11.SERVER)
    conn.receive_data(wire)
    ev = conn.next_event()
    assert isinstance(ev, h11.Request), ev
    return [(k.decode().lower(), v.decode()) for k, v in ev.headers]


def test_h11_really_does_accept_bare_lf():
    """先证**前提**成立 —— 否则下面几条测的是一个不存在的威胁（恒绿）。"""
    seen = _as_h11_sees(b"GET / HTTP/1.1\r\nA: 1\nB: 2\r\nHost: g\r\n\r\n")
    assert ("a", "1") in seen and ("b", "2") in seen, seen


@pytest.mark.parametrize("name", sorted(SMUGGLED))
def test_n91_upstream_sees_exactly_the_injected_identity(name):
    """**不变式**：剥注之后，h11 解析出来的每一个身份头都只能是边车注入的真值。

    这条红过：`X-Whatever: a\\nx-genebench-config-id: cfg-forged` 在边车看来是一行
    （名字 `x-whatever`，不剥），到 h11 那里是两行，伪造值还排在真值**前面**，
    而 starlette 的 `.get()` 取第一个。
    """
    out = rewrite_identity(SMUGGLED[name], IDENT)
    seen = _as_h11_sees(out)
    for k, v in seen:
        if any(k.startswith(p) for p in STRIP_PREFIXES):
            assert v in IDENT.values(), f"{name}: 上游看到了非注入值 {k}={v}"
    got = {k: v for k, v in seen if k == "x-genebench-config-id"}
    assert got == {"x-genebench-config-id": "oracle-real"}, seen


@pytest.mark.parametrize("name", sorted(SMUGGLED))
def test_n91_non_canonical_heads_are_rejected(name):
    """纵深的第二层：非规范头**直接拒**，不是尽力解析。

    收窄输入封的是**整类**（下一个解析器差异也被封住），
    而「把边车写成和 h11 一样」只封住这一个。
    """
    with pytest.raises(ProtocolViolation):
        assert_canonical_head(SMUGGLED[name])


def test_n91_canonical_head_still_passes():
    """恒红的门与恒绿的一样没用 —— 先证它放得过正常请求。"""
    assert_canonical_head(b"GET /bars HTTP/1.1\r\nHost: g\r\nAccept: */*\r\n\r\n") is None


def test_n91_bare_cr_is_rejected_too():
    with pytest.raises(ProtocolViolation, match="裸 CR"):
        assert_canonical_head(b"GET / HTTP/1.1\r\nA: 1\rB: 2\r\n\r\n")


@pytest.mark.parametrize("wire,head_len", [
    (b"GET / HTTP/1.1\r\nHost: g\r\n\r\n", 23),
    (b"GET / HTTP/1.1\nHost: g\n\n", 22),
    (b"GET / HTTP/1.1\r\nHost: g\n\r\n", 23),
])
def test_n91_head_boundary_matches_what_h11_accepts(wire, head_len):
    """边界检测必须与上游认得一样多。只认 `\\r\\n\\r\\n` 的话，
    攻击方用 `\\n\\n` 结尾就能让边车一路读到 1MB 抛错，而网关照常受理。"""
    i, blen = _find_head_end(wire)
    assert i >= 0, wire
    assert i + blen == len(wire), (i, blen, len(wire))
    assert i == head_len, (i, head_len)



# ===================================================================== 根治：边车跑 h11
#
# 裸 LF 只是「边车与上游解析差异」这一类的**一个实例**。逐种补规则是跑步机，
# 照着 h11 重写行界规则会漂。边车改用 **h11 本尊**之后这一类在构造上不存在 ——
# 下面这组测的就是"构造上不存在"这件事本身，而不是某一个攻击串。

from runner.c41.egress_proxy import (H11_VERSION, _assert_h11_pinned,  # noqa: E402
                                     assert_unambiguous_framing, parse_request,
                                     serialize_identity)


def test_h11_pin_matches_the_gateway_environment():
    """边车与网关必须跑**同一份** h11。这条在网关环境里跑，
    所以网关升级了 h11 而没改钉子 → 当场红。"""
    assert H11_VERSION == h11.__version__


def test_a_different_h11_is_refused_at_import_time():
    import types
    with pytest.raises(RuntimeError, match="同一份解析器"):
        _assert_h11_pinned(types.SimpleNamespace(__version__="0.15.0"))


def test_sidecar_and_gateway_agree_on_the_header_set():
    """**不变式**：边车剥注前看到的头集合 = h11（网关那一侧）解析出来的头集合。

    这是"构造上消失"的直接判据 —— 边车不再有自己的一套行界规则，
    所以两边不可能看法不同。旧实现在裸 LF 上就是看法不同。
    """
    for name, wire in SMUGGLED.items():
        seen_by_sidecar = {(k, v) for k, v in parse_request(wire).headers}
        seen_by_gateway = {(k.lower(), v) for k, v in
                           [(a, b) for a, b in _as_h11_sees(wire)]}
        got = {(k.decode(), v.decode()) for k, v in seen_by_sidecar}
        assert got == seen_by_gateway, name


@pytest.mark.parametrize("wire", [
    b"POST /x HTTP/1.1\r\nHost: g\r\nContent-Length: 5\r\nTransfer-Encoding: chunked\r\n\r\n",
    b"POST /x HTTP/1.1\r\nHost: g\r\nTransfer-Encoding: chunked\r\nContent-Length: 5\r\n\r\n",
])
def test_te_and_cl_together_are_refused(wire):
    """**h11 自己不拒**（2026-09-05 实测：两个头都原样给出来）—— 所以这条必须我们拒。

    并存是请求走私的经典原语：谁优先谁定消息边界，边界不一致就能把下一个请求的头
    塞进上一个的体里，而那个头**逃掉剥注**。
    """
    req = parse_request(wire)
    assert {b"content-length", b"transfer-encoding"} <= {n for n, _ in req.headers}, \
        "前提变了：h11 现在自己拒了，这条测试要重写"
    with pytest.raises(ProtocolViolation, match="并存"):
        assert_unambiguous_framing(wire, req)


def test_obs_fold_is_refused():
    """h11 会把续行折进上一行的值（实测 `x-a: 1 cont`），不报错。
    折法一致时没有歧义，但 RFC 7230 §3.2.4 要求拒，而没有正经客户端发它。"""
    wire = b"GET /x HTTP/1.1\r\nHost: g\r\nX-A: 1\r\n  cont\r\n\r\n"
    req = parse_request(wire)
    assert (b"x-a", b"1 cont") in list(req.headers), "前提变了：h11 不再折 obs-fold"
    with pytest.raises(ProtocolViolation, match="obs-fold"):
        assert_unambiguous_framing(wire, req)


def test_well_formed_requests_still_pass_both_framing_checks():
    """恒红的门与恒绿的一样没用。"""
    for wire in (b"GET /x HTTP/1.1\r\nHost: g\r\n\r\n",
                 b"POST /x HTTP/1.1\r\nHost: g\r\nContent-Length: 3\r\n\r\n",
                 b"POST /x HTTP/1.1\r\nHost: g\r\nTransfer-Encoding: chunked\r\n\r\n"):
        assert_unambiguous_framing(wire, parse_request(wire)) is None


def test_h11_rejects_are_translated_to_protocol_violation():
    """h11 自己拒的（重复且冲突的 Content-Length、缺 Host）要变成同一种拒绝，
    不能漏成 500 或者被 `except Exception` 吞掉。"""
    for wire in (b"POST /x HTTP/1.1\r\nHost: g\r\nContent-Length: 5\r\nContent-Length: 6\r\n\r\n",
                 b"GET /x HTTP/1.1\r\nX-A: 1\r\n\r\n"):
        with pytest.raises(ProtocolViolation, match="h11 解析失败"):
            parse_request(wire)


def test_serialization_round_trips_a_normal_request():
    wire = b"GET /calendar?a=1 HTTP/1.1\r\nHost: g\r\nAccept: */*\r\n\r\n"
    out = serialize_identity(parse_request(wire), IDENT)
    assert out.split(b"\r\n")[0] == b"GET /calendar?a=1 HTTP/1.1"
    got = dict(_as_h11_sees(out))
    assert got["accept"] == "*/*" and got["host"] == "g"
    assert got["x-genebench-config-id"] == "oracle-real"
