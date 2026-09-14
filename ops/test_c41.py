# -*- coding: utf-8 -*-
"""卡 4.1 的可测部分：compose lint、出向白名单、SNI 校验。

**为什么这些要进主测试套**：卡 4.1 的隔离由「compose 长成那个样子 + 白名单是那几条」
保证。这两件事都在代码里，就都应当被 CI 盯着，而不是只靠 f02 上手跑一次 `negctl_lint.py`。
docker 相关的六条验收仍在 f02 上做（本文件不碰 docker）。
"""
from __future__ import annotations

import socket
import ssl
import sys
import threading
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runner" / "c41"))

import egress_proxy as ep                                  # noqa: E402
from negctl_lint import BASE, CASES, REVERSE               # noqa: E402
from runner_core import lint_compose, render_compose       # noqa: E402
import runner_core as RC                                  # noqa: E402


# ------------------------------------------------------------------ lint

def test_baseline_compose_is_clean():
    assert lint_compose(BASE) == [], "基线 compose 就不干净，后面的负例都不作数"


def test_render_compose_is_pure():
    """render 不许有副作用 —— 否则 lint 没法在数据面机器上被测。"""
    d = Path("/data/genebench_runner/tasks/pure-check")
    render_compose("pure-check", "strict")
    assert not d.exists(), f"render_compose 建了目录 {d}，它应当是纯函数"


@pytest.mark.parametrize("name", list(CASES))
def test_each_negative_control_is_caught_by_its_own_rule(name):
    """全红不够：必须是**被它自己那条规则**拦下的。

    一个负例若因别的规则红，被测的那条规则其实是空的 —— 机制在，保护不在（D-06）。
    """
    text, want = CASES[name]
    found = lint_compose(text)
    hit = [v for v in found if v.startswith(want)]
    assert hit, f"{name}：期望命中 {want}，实得 {found or '（全绿）'}"


def test_reverse_control_stays_green():
    """只改注释必须仍然通过 —— 否则 lint 是在乱红，红色也不构成证据。"""
    assert lint_compose(REVERSE) == []


def test_lint_rule_ids_are_unique_and_documented():
    """每条负例的规则号互不重叠，且都真的出现在 lint 的实现里。"""
    ids = {want for _, want in CASES.values()}
    assert ids == {"L-1", "L-2", "L-3", "L-4", "L-5", "L-6", "L-7", "L-8", "L-9"}, ids


def test_L6_is_not_a_duplicate_of_L1_L2():
    """L-6 的判别力：一个**格式完全合规**的端口发布，L-1/L-2 都不响，只有 L-6 响。"""
    text, _ = CASES["L-6 代理服务发布端口（格式合规）"]
    found = lint_compose(text)
    assert not [v for v in found if v.startswith(("L-1", "L-2"))], \
        "格式合规却被 L-1/L-2 拦了，说明这个负例证不出 L-6 的独立价值"
    assert [v for v in found if v.startswith("L-6")]


# ------------------------------------------------------------------ 白名单

def test_every_allowlist_entry_names_who_needs_it():
    """**白名单的语义在 2026-09-04 改了，这条测试随之改写，留记录**（同 N-33 做法）。

    改前：`MODEL_API_ALLOW` 是「允许 **CONNECT** 到哪」，`ALLOW == frozenset(它)`。
    改后（裁定 (a)）：它是「**反向代理**允许连到哪个上游」（`MODEL_UPSTREAMS`），
    而 `ALLOW`（CONNECT）**清空** —— 模型只能经反向代理到达。
    """
    assert ep.MODEL_API_ALLOW, "白名单为空 —— 反向代理就没有上游可连"
    for host, why in ep.MODEL_API_ALLOW.items():
        assert str(why).strip(), f"{host} 没写引用者"
    assert ep.MODEL_UPSTREAMS == frozenset(ep.MODEL_API_ALLOW)
    assert ep.ALLOW == frozenset(), "CONNECT 白名单必须是空的（见下一条测试的理由）"


def test_allowlist_has_no_package_registry():
    assert not [h for h in ep.MODEL_UPSTREAMS if ep.is_build_time_only(h)], \
        "运行期白名单里混进了包仓库 —— 依赖必须在镜像构建期解决"


def test_allowlist_guard_actually_fires():
    """守门的判别力：坏输入必须抛。只证明好输入不抛，等于没证。"""
    with pytest.raises(RuntimeError, match="包/镜像仓库"):
        ep.assert_allowlist_sane({"pypi.org": "某个配置说它要装包"})
    with pytest.raises(RuntimeError, match="没写引用者"):
        ep.assert_allowlist_sane({"api.example.com": "  "})
    ep.assert_allowlist_sane({"api.example.com": "某被测配置"})   # 好输入不抛


@pytest.mark.parametrize("host,expect", [
    ("pypi.org", True), ("files.pythonhosted.org", True),
    ("mirrors.aliyun.com", True), ("raw.githubusercontent.com", True),
    ("api.anthropic.com", False), ("api.openai.com", False),
    ("notpypi.org", False),                     # 后缀匹配不能误伤
])
def test_build_time_only_classifier(host, expect):
    assert ep.is_build_time_only(host) is expect


def test_only_443_allowed():
    """只放 443 是 SNI 校验成立的前提 —— 明文端口上没有 SNI 可校。"""
    assert ep.ALLOW_PORTS == frozenset({443})


def test_sni_match_is_required():
    """状态锁：关掉 SNI 校验等于允许 domain fronting，改动必须过测试这一关。"""
    assert ep.REQUIRE_SNI_MATCH is True


# ------------------------------------------------------------------ SNI

def _capture_real_client_hello(server_hostname: str, timeout: float = 5.0) -> bytes:
    """用 OpenSSL 真发一次 ClientHello，把字节抓下来。

    **不是我自己拼的字节** —— 自造样本会把解析器的误解原样复制进测试，
    两边一起错还一起绿（D-06 第 4 个实例就是这么来的：扫描器与判据同源）。
    """
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    got: list[bytes] = []

    def serve():
        conn, _ = srv.accept()
        conn.settimeout(timeout)
        try:
            got.append(conn.recv(16384))
        except OSError:
            pass
        conn.close()

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with socket.create_connection(srv.getsockname(), timeout=timeout) as raw:
            with ctx.wrap_socket(raw, server_hostname=server_hostname) as s:
                s.recv(1)           # 握手必然失败（对面不是 TLS 服务端），不关心
    except (ssl.SSLError, OSError):
        pass
    t.join(timeout)
    srv.close()
    return got[0] if got else b""


def test_parse_sni_on_a_real_openssl_client_hello():
    raw = _capture_real_client_hello("api.anthropic.com")
    assert raw, "没抓到 ClientHello"
    assert ep.parse_sni(raw) == "api.anthropic.com"


def test_parse_sni_distinguishes_two_different_names():
    """判别力：换个域名，解出来必须跟着变 —— 否则解析器可能只是在返回常量。"""
    a = ep.parse_sni(_capture_real_client_hello("api.anthropic.com"))
    b = ep.parse_sni(_capture_real_client_hello("evil.example.net"))
    assert a == "api.anthropic.com" and b == "evil.example.net" and a != b


@pytest.mark.parametrize("blob", [
    b"", b"GET / HTTP/1.1\r\n\r\n",                 # 不是 TLS
    b"\x16\x03\x01\x00\x05\x01\x00\x00\x01\x00",    # 是 TLS 但没有 SNI
])
def test_parse_sni_fails_closed(blob):
    assert ep.parse_sni(blob) is None


def test_parse_sni_on_truncated_hello_returns_none():
    """截断必须返回 None（调用方 fail closed），不能返回半个域名。"""
    raw = _capture_real_client_hello("api.anthropic.com")
    assert ep.parse_sni(raw[:len(raw) // 2]) is None


def test_hello_complete_discriminates():
    raw = _capture_real_client_hello("api.anthropic.com")
    assert ep.hello_complete(raw) is True
    assert ep.hello_complete(raw[:20]) is False
    assert ep.hello_complete(b"GET / HTTP/1.1\r\n") is False


# ------------------------------------------------- SNI 的**执行**（不只是解析）

class _Upstream:
    """假上游：只记收到的字节。用来回答「代理到底转没转」。"""

    def __init__(self):
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(4)
        self.port = self.sock.getsockname()[1]
        self.got = b""
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            conn.settimeout(3)
            try:
                while True:
                    b = conn.recv(4096)
                    if not b:
                        break
                    self.got += b
            except OSError:
                pass
            finally:
                conn.close()


def _proxy_roundtrip(monkeypatch, tmp_path, sni_name: str):
    """把代理真起起来，走一次 CONNECT，返回 (代理应答, 上游收到的字节, 日志文本)。"""
    up = _Upstream()
    monkeypatch.setattr(ep, "ALLOW", frozenset({"localhost"}))
    monkeypatch.setattr(ep, "ALLOW_PORTS", frozenset({up.port}))
    monkeypatch.setattr(ep, "_LOG_PATH", str(tmp_path / "egress.jsonl"))

    ready: list[int] = []
    threading.Thread(
        target=ep.connect_proxy, args=(0,),
        kwargs={"bind_host": "127.0.0.1", "on_ready": ready.append},
        daemon=True).start()
    for _ in range(200):
        if ready:
            break
        threading.Event().wait(0.01)
    assert ready, "代理没起来"

    cli = socket.create_connection(("127.0.0.1", ready[0]), timeout=5)
    cli.settimeout(5)
    cli.sendall(f"CONNECT localhost:{up.port} HTTP/1.1\r\n"
                f"Host: localhost\r\n\r\n".encode())
    resp = cli.recv(1024)
    if b"200" in resp:
        cli.sendall(_capture_real_client_hello(sni_name))
        threading.Event().wait(0.6)
        try:
            resp += cli.recv(1024)
        except OSError:
            pass
    cli.close()
    threading.Event().wait(0.2)
    log = (tmp_path / "egress.jsonl").read_text(encoding="utf-8")
    return resp, up.got, log


def test_matching_sni_is_forwarded(monkeypatch, tmp_path):
    resp, got, _ = _proxy_roundtrip(monkeypatch, tmp_path, "localhost")
    assert b"200 Connection Established" in resp
    assert got.startswith(b"\x16\x03"), "SNI 相符却没把 ClientHello 转给上游"


def test_mismatched_sni_is_denied_and_nothing_reaches_upstream(monkeypatch, tmp_path):
    """判别力：CONNECT 到白名单域名、TLS 里握另一个域名（domain fronting）必须被拦。

    这条证明的是**执行**，不是解析 —— 解析对了但没接进拒绝路径，
    等于「机制在、保护不在」（D-06）。
    """
    resp, got, log = _proxy_roundtrip(monkeypatch, tmp_path, "evil.example.net")
    assert b"403" in resp, f"域名前置没被拦：{resp[:120]!r}"
    assert got == b"", "被拒了却仍有字节到达上游"
    assert "sni_mismatch" in log and "evil.example.net" in log, \
        "拒绝没进代理日志 —— 卡 5.1 的网络侧结算源就是这份日志，不记等于没拦"


# --------------------------------------------------------------- L-10（N-48）

def _compose():
    return RC.render_compose("hello-0001", "open")


def test_l10_every_service_is_deprivileged():
    """N-48（2026-09-04 裁定「现在修」）。判据**封闭**：遍历每一个服务，不列白名单 ——
    白名单版会在加第三个服务时静默漏掉它（guard_modes 那次：白名单 4 项 vs 封闭 40307 项）。"""
    text = _compose()
    assert RC.lint_compose(text) == []
    doc = yaml.safe_load(text)
    for name, svc in doc["services"].items():
        assert svc.get("user"), name
        assert str(svc["user"]).split(":")[0] not in ("0", "root"), name
        assert [c.upper() for c in svc["cap_drop"]] == ["ALL"], name
        assert any(str(o).startswith("no-new-privileges")
                   for o in svc["security_opt"]), name


@pytest.mark.parametrize("drop", ["user", "cap_drop", "security_opt"])
def test_l10_is_discriminating(drop):
    """突变落在**门保护的对象**（compose 文本）上，不落在门的参数上。"""
    doc = yaml.safe_load(_compose())
    for svc in doc["services"].values():
        svc.pop(drop, None)
    bad = RC.lint_compose(yaml.safe_dump(doc, allow_unicode=True))
    hit = [b for b in bad if b.startswith("L-10")]
    assert len(hit) >= 2, f"两个服务都缺 {drop} 却只报了 {len(hit)} 条：{bad}"


def test_l10_explicit_root_is_as_bad_as_missing():
    doc = yaml.safe_load(_compose())
    doc["services"]["task"]["user"] = "0:0"
    bad = RC.lint_compose(yaml.safe_dump(doc, allow_unicode=True))
    assert any("显式写 root" in b for b in bad), bad
    doc["services"]["task"]["user"] = "root"
    assert any("显式写 root" in b
               for b in RC.lint_compose(yaml.safe_dump(doc, allow_unicode=True)))


def test_l10_uid_is_the_running_user_not_a_hardcoded_1000():
    """写死 1000 的那份在换机器/换账号时会静默错位，
    而错位的表现是「产物属主不对」—— 与「容器没降权」看起来一样。"""
    import os
    assert RC.runner_ids() == (os.getuid(), os.getgid())
    assert f'user: "{os.getuid()}:{os.getgid()}"' in _compose()


def test_compose_has_exactly_one_render_entry_point():
    """三处各自 format 同一个模板正是漏字段的来源（加 N-48 的占位符时当场 KeyError）。"""
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    # 针脚在运行时拼出来 —— 写成字面量的话本文件会命中自己，
    # 那条「只有一个出口」的断言就永远差一条，看起来像真红。
    needle = "COMPOSE_TMPL" + ".format"
    hits = []
    for py in sorted(root.rglob("*.py")):
        if needle in py.read_text(encoding="utf-8", errors="replace"):
            hits.append(str(py.relative_to(root)))
    assert hits == ["runner/c41/runner_core.py"], \
        f"这些地方绕过了 format_compose：{hits}"


# --------------------------------------------------------------- §15 白名单同源（裁定 2026-09-04）

def test_allowlist_matches_registry():
    """§15 的三条断言。第一条（**键集相等**，不是包含）是本卡加的 ——
    手抄的白名单必然漂：先前两条的引用者写的是「待 M6 复核」，
    也就是没有任何真实配置需要它们（N-32）。"""
    from runner import registry as REG
    want = REG.collect_egress_hosts()
    assert set(ep.MODEL_API_ALLOW) == set(want), \
        f"白名单 {sorted(ep.MODEL_API_ALLOW)} ≠ 注册表 {sorted(want)}"
    for h, who in ep.MODEL_API_ALLOW.items():
        assert who.strip(), h
        assert not ep.is_build_time_only(h), h


def test_v10_is_one_model_many_harnesses():
    """裁定：同一模型 × 多种 harness —— 把模型效应固定，只暴露 harness 与协议臂差异。

    **这里原来写的是 `len(REG.CONFIGS) == 3`。** 那条在 W-0 把被测配置改成数据驱动
    之前是对的（主表就是 `BUILTIN_CONFIGS` 那三条），之后就成了一条**会被正常施工跑红**
    的断言：主表现在是「内置三条 + `harnesses/`、`integrations/` 两棵树里 `enabled: true` 的」，
    于是阶段二/三每接一个系统它就红一次，而那不是回归。
    改成三条真判据：内置三条**仍在**（数据不许悄悄换掉它们）、`config_id` 互异、
    `harness` 名互异 —— 后两条才是主表切片键必须成立的性质。
    """
    from runner import registry as REG
    assert len({c.model for c in REG.CONFIGS}) == 1
    builtin_ids = {c.config_id for c in REG.BUILTIN_CONFIGS}
    ids = [c.config_id for c in REG.CONFIGS]
    assert builtin_ids <= set(ids), f"内置三条不在主表里：{sorted(builtin_ids - set(ids))}"
    assert len(set(ids)) == len(ids), f"config_id 重复：{ids}"
    harnesses = [c.harness for c in REG.CONFIGS]
    assert len(set(harnesses)) == len(harnesses), f"harness 名重复：{harnesses}"
    assert len(REG.CONFIGS) >= 3
    assert all(c.host == "api.deepseek.com" for c in REG.CONFIGS)
    import dataclasses
    mixed = list(REG.CONFIGS[:-1]) + [dataclasses.replace(REG.CONFIGS[-1], model="other")]
    import unittest.mock as M
    with M.patch.object(REG, "CONFIGS", tuple(mixed)):
        with pytest.raises(REG.RegistryError, match="同一模型"):
            REG.assert_registry_sane()


def test_market_data_hosts_are_the_third_tripwire():
    """行情/新闻源入表 = 让被测系统绕过数据面取数：
    access_log 干干净净、前视探针全绿，而 as-of 强制已经失效。"""
    from runner import registry as REG
    assert set(ep.MARKET_DATA_DENY) == set(REG.MARKET_DATA_HOSTS), "两份绊线表漂了"
    for host in ("finnhub.io", "query1.finance.yahoo.com", "news.google.com"):
        with pytest.raises(RuntimeError, match="行情/新闻源"):
            ep.assert_allowlist_sane({host: "某个真实配置"})
        assert ep.is_market_data(host) and ep.is_market_data("sub." + host)
    assert not ep.is_market_data("api.deepseek.com")


def test_registry_refuses_a_feed_host_as_base_url():
    from runner import registry as REG
    import dataclasses
    import unittest.mock as M
    bad = dataclasses.replace(REG.CONFIGS[0], base_url="https://finnhub.io")
    with M.patch.object(REG, "CONFIGS", (bad,) + REG.CONFIGS[1:]):
        with pytest.raises(REG.RegistryError, match="绕过数据面"):
            REG.assert_registry_sane()


def test_reachability_tripwire_exists_and_is_not_run_at_import():
    """第四类绊线：条目必须**实测可达**。

    不在 import 期跑 —— 边车在容器里 import 本文件，那时做网络探测会让
    边车的启动依赖外网，一次抖动就变成「边车起不来」。
    """
    assert hasattr(ep, "assert_allowlist_reachable")
    src = Path(ep.__file__).read_text(encoding="utf-8")
    tail = src[src.index("def assert_allowlist_reachable"):]
    assert "\nassert_allowlist_reachable(" not in tail, "它被放到 import 期跑了"
    with pytest.raises(RuntimeError, match="实测不可达"):
        ep.assert_allowlist_reachable({"no-such-host.invalid": "x"}, timeout=3)


@pytest.mark.network
def test_allowlist_entries_are_actually_reachable():
    """联网测试。2026-09-04 实测：api.openai.com TCP 层不通、api.anthropic.com 403 ——
    两条在表上挂了很久，没有任何东西说它们其实用不了。"""
    ep.assert_allowlist_reachable(timeout=10)


def test_unparsable_volume_entry_is_flagged_not_skipped():
    """D-23：**看不懂 ≠ 没有挂载。** 先前解析不出 source 的条目被静默跳过，
    于是一条我们看不懂的 volumes 项可以绕过 L-5 全家。"""
    doc = yaml.safe_load(render_compose("hello-0001", "open"))
    doc["services"]["task"]["volumes"].append({"type": "bind", "target": "/x"})
    bad = lint_compose(yaml.safe_dump(doc, allow_unicode=True))
    assert any("解析不出挂载源" in b for b in bad), bad


def test_malformed_egress_log_line_is_not_counted_as_no_request(tmp_path):
    """出向日志是卡 5.1 网络侧的结算源。写坏的行先前被静默吞掉，
    表现为「这次少了一个请求」，与「真的没请求」不可分（D-06 的形态）。"""
    import json as _json
    d = tmp_path / "tasks" / "t1"
    (d / "log").mkdir(parents=True)
    (d / "work").mkdir()
    lines = [_json.dumps({"event": "ready"}), _json.dumps({"event": "forward"}),
             "{ this is not json"]
    (d / "log" / "egress.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    src = Path(RC.__file__).read_text(encoding="utf-8")
    assert "malformed += 1" in src and "解析不了" in src, \
        "解析失败又被静默吞掉了"
    i = src.index("malformed += 1")
    j = src.index("if starts != 1:")
    assert "raise RuntimeError" in src[i:j], "计了数却没有人因此中止"


def test_registry_is_labelled_an_acceptance_config_in_both_places():
    """范围修正 2026-09-04：三条 DeepSeek 是 **M6 的验收配置**，不是实验设计。

    验收配置与实验设计在代码里长得一模一样（都是 `Config` 实例），
    **只能靠那句话分开** —— 所以它必须同时在两处，少一处这条测试就红。
    一份验收配置被当成实验设计读，就等于宣称了一个我们没有做过的比较。
    """
    from pathlib import Path
    from runner import registry as REG
    assert REG.PURPOSE == "acceptance"
    doc = REG.__doc__ or ""
    assert "验收配置" in doc and "不是实验设计" in doc and "M7" in doc, \
        "registry 的模块 docstring 没写这条定性"
    fp = (Path(REG.__file__).resolve().parents[1] / "ops" / "specs"
          / "fairness_protocol.md").read_text(encoding="utf-8")
    assert "验收配置 ≠ 实验设计" in fp and "M7" in fp, \
        "公平性协议里没写这条 —— 读者在第 1 节看到三条配置会当成配置矩阵"


def test_switching_purpose_to_experiment_is_refused():
    """判别力：改一个字符串就想把验收配置变成实验设计，必须红。"""
    import unittest.mock as M
    from runner import registry as REG
    with M.patch.object(REG, "PURPOSE", "experiment"):
        with pytest.raises(REG.RegistryError, match="M7"):
            REG.assert_registry_sane()


def test_m6_scope_is_recorded_with_the_original_kept():
    """改定要留原文对照 —— 只改不留，半年后没人分得清「当初就是这么定的」
    与「后来改小了」。"""
    from pathlib import Path
    from runner import registry as REG
    plan = (Path(REG.__file__).resolve().parents[1] / "ops"
            / "GeneBench工程实施稿_v1.md").read_text(encoding="utf-8")
    assert "M6 **构造验收**" in plan and "原文（2026-08-30）已作废，留档对照" in plan
    assert "本阶段任何数字不进论文，不称主表" in plan
    assert "### M7 实验规划" in plan and "审定前不启动网格" in plan
    assert "预注册的 confirmatory 判据与 exploratory 边界" in plan


# --------------------------------------------------------------- 凭据路径（裁定 (a)，2026-09-04）

def test_connect_allowlist_is_empty_by_design():
    """模型只能经**反向代理**到达。留一条 CONNECT 到上游的路，等于给
    「agent 自带一把 key 直连」留了门 —— 而那条路上边车看不见任何东西：
    没有 usage、没有 Steps、预算闸也管不着。

    **空集不是「暂时没有条目」，是判据** —— 所以这条测试断言它就是空的。
    """
    assert ep.ALLOW == frozenset(), f"CONNECT 白名单不是空的：{sorted(ep.ALLOW)}"
    assert ep.MODEL_UPSTREAMS, "上游允许集空了 —— 那反向代理连不上任何模型"
    from runner import registry as REG
    assert set(ep.MODEL_UPSTREAMS) == set(REG.collect_egress_hosts()), \
        "上游允许集与注册表漂了（§15 的同源约束现在管的是反向代理）"


def test_placeholder_key_never_reaches_upstream():
    """**占位串永不到达上游**：转发时 `_replace_auth` 把它换成真 key。"""
    head = (b"POST /v1/chat/completions HTTP/1.1\r\nhost: gateway:8081\r\n"
            b"authorization: Bearer " + ep.PLACEHOLDER_KEY.encode() + b"\r\n\r\n")
    # 运行时拼 —— 写成字面量的话这个文件会被凭据 lint 判成泄漏（实测抓到过一次）
    fake = "sk" + "-REAL-" + "abcdefghijklmnop"
    out = ep._replace_auth(head, fake, "api.deepseek.com")
    assert ep.PLACEHOLDER_KEY.encode() not in out, "占位串原样发到上游了"
    assert f"authorization: Bearer {fake}".encode() in out
    assert b"host: api.deepseek.com" in out, "Host 没改成上游"
    # 没带 authorization 时也要补上 —— 否则上游 401，而 401 看起来像模型不配合
    bare = b"POST /v1/x HTTP/1.1\r\nhost: gateway:8081\r\n\r\n"
    assert fake.encode() in ep._replace_auth(bare, fake, "api.deepseek.com")


def test_foreign_credential_is_refused():
    """agent 自带一把 key = **未声明的资源**：绕开预算闸，usage 归属也对不上。"""
    own = "sk" + "-agents-own-key"
    head = f"POST /v1/x HTTP/1.1\r\nauthorization: Bearer {own}\r\n\r\n".encode()
    assert ep._client_key(head) == own
    assert ep._client_key(b"POST /v1/x HTTP/1.1\r\n\r\n") is None
    src = Path(ep.__file__).read_text(encoding="utf-8")
    assert "foreign_credential" in src


def test_authorization_is_stripped_before_it_lands_in_llm_log():
    """llm_log 落 run dir，run dir 会被归档、会进结果库 —— 真 key 不能在里面。"""
    secret = "sk" + "-REAL-secret"
    head = f"POST /v1/x HTTP/1.1\r\nauthorization: Bearer {secret}\r\nx: y\r\n".encode()
    out = ep._strip_auth(head)
    assert secret.encode() not in out and b"<stripped>" in out
    assert b"x: y" in out, "把别的头也剥掉了"


def test_budget_gate_refuses_and_records():
    """超限拒绝并**以 access_log 同格式**留记录（reason=budget_exceeded）。"""
    saved = dict(ep._BUDGET)
    try:
        ep._BUDGET.update({"max_calls": 2, "max_tokens": 0, "calls": 0, "tokens": 0})
        assert ep._budget_check() is None
        ep._budget_add(calls=2, tokens=100)
        over = ep._budget_check()
        assert over and "上限" in over, over
        ep._BUDGET.update({"max_calls": 0, "max_tokens": 50, "calls": 0, "tokens": 60})
        assert ep._budget_check(), "token 上限没生效"
        ep._BUDGET.update({"max_calls": 0, "max_tokens": 0, "calls": 999, "tokens": 999})
        assert ep._budget_check() is None, "0 表示不限"
    finally:
        ep._BUDGET.clear()
        ep._BUDGET.update(saved)


def test_usage_is_extracted_from_both_shapes():
    """usage 是 §13.4「自报 tokens 要有网络侧佐证」的那一侧证据。"""
    plain = b'{"choices":[],"usage":{"total_tokens":123,"prompt_tokens":100}}'
    assert ep._extract_usage(plain)["total_tokens"] == 123
    stream = (b'data: {"choices":[{"delta":{}}]}\n\n'
              b'data: {"usage":{"total_tokens":77}}\n\ndata: [DONE]\n')
    assert ep._extract_usage(stream)["total_tokens"] == 77
    assert ep._extract_usage(b"not json at all") == {}, "抽不到就该是空，不是编一个 0"


def test_real_key_is_not_in_the_repo_and_the_scanner_now_has_a_real_input(tmp_path):
    """**凭据 lint 的判别力用例现在有真输入了**（裁定 2026-09-04）。

    此前它只喂合成串，属于「今天一把密钥都没有，不喂坏输入就是恒绿」。
    真 key 已落在 f02 的 `~/.config/genebench/secrets.env`（0600）——
    这条测试用**它的形状**（`sk-` 前缀 + 32 位）造一个等价输入，
    并断言仓库里搜不到那个形状。
    """
    import re
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent))
    from test_env import _key_offenders                       # noqa: E402
    # 运行时拼 —— 写成字面量的话，**这个文件自己**会被凭据 lint 判成泄漏
    # （实测：全量跑时 test_no_api_key_material_in_the_repo 当场红）。
    # 同「只有一个 compose 出口」那条曾经命中自己的坑。
    shaped = "sk" + "-" + ("a1b2c3d4e5f6" * 2) + "90abcdef"   # 与真 key 同形状
    (tmp_path / "leak.env").write_text(f"DEEPSEEK_API_KEY={shaped}\n", encoding="utf-8")
    (tmp_path / "leak.py").write_text(f'KEY = "{shaped}"\n', encoding="utf-8")
    hits = _key_offenders(tmp_path)
    assert len(hits) >= 2, f"真 key 的形状没被抓到：{hits}"
    repo = Path(__file__).resolve().parents[1]
    assert not re.search(r"sk-[A-Za-z0-9]{30,}",
                         (repo / "runner" / "c41" / "egress_proxy.py")
                         .read_text(encoding="utf-8")), "边车里有像真 key 的串"
