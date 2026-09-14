# -*- coding: utf-8 -*-
"""`integrations/genebench_client/` 的判据测试（阶段二 2.2）。

**为什么这些测试打生产网关而不是打桩**：垫片存在的全部理由是「取数经过网关并在
`access_log` 上留痕」。桩能证明代码路径对，证明不了那条痕迹真的落下来了 ——
而 2026-09-05 那次 40 题跑批里，S2 的取数代码"看起来在请求"、日志里切出来是 0 条
（缺身份头），桩测试全绿。所以核心三条判据（切片条数、403 落痕、NO_DATA 留痕）
一律真打。

请求很轻（几十次 GET，全部命中已缓存的年表），**不需要 `gateway_lock`** ——
锁是给跑批与真跑用的。每条测试用**自己的 `run_id`**，与别的代理的流量互不干扰。
"""
from __future__ import annotations

import ast
import contextlib
import json
import os
import socket
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
#: 垫片是**独立可 pip 装的包**，不在仓库根的 import 路径上。测试按源码树装配，
#: 与容器里 `pip install /opt/genebench_client` 拿到的是同一份代码。
PKG_SRC = REPO / "integrations" / "genebench_client" / "src"
sys.path.insert(0, str(PKG_SRC))

import genebench_config as cfg                                            # noqa: E402
import genebench_client as gb                                             # noqa: E402
from genebench_client import codes as gc                                  # noqa: E402
from genebench_client import nodata as nd                                 # noqa: E402
from genebench_client import qlib_provider as qp                          # noqa: E402
from genebench_client.compat import akshare as ak                         # noqa: E402
from genebench_client.compat import tushare as ts                         # noqa: E402
from genebench_client.compat import yfinance as yf                        # noqa: E402

GATEWAY = f"http://{cfg.GATEWAY_HOST}:{cfg.GATEWAY_PORT}"
#: 冻结线之前一个有充足行情的 as_of。
AS_OF = "2026-06-30"
#: 窗口固定，便于逐值比对。
WIN = ("2026-06-01", "2026-06-10")
CODE, CODE2 = "600000.SH", "000001.SZ"
ACCESS_LOG = cfg.gateway_access_log()


#: **在 import 期**抓下 socket 的原件。
#:
#: `ops/test_env.py::_no_outbound_network` 是一个 `scope="session"` 的 autouse
#: fixture，它把 `socket.*` 换成「非回环一律 AssertionError」的门，
#: 而**它的 teardown 在整场测试结束时才跑** —— 也就是说：全量按字母序跑到
#: `test_env.py` 之后，这道门就一直开着。本文件的真打测试要连的是**局域网里的
#: 数据面网关** `192.168.1.48:18080`（红线 4 要求网关绑显式 LAN 地址，
#: 所以它**不可能**在回环上），于是 2026-09-06 全量实测：14 条真打测试同时红，
#: 报的是「card 0.1 验收必须完全离线,却检测到出网调用」，而单跑本文件全绿。
#:
#: 那道门要挡的是「某个 import 顺手去 pypi / 下载 qlib 数据」，**局域网数据面不是外网**
#: —— 它自己已经为同一类误伤开过一次口子（回环，见那里的 docstring）。
#: 正确的修法是在 `ops/test_env.py` 里把网关地址一并放行，但那不是本卡的路径，
#: 已登记 `ops/tickets_inbox/2.2.md`（N-?）。
#:
#: 在那之前，本文件的做法是：真打测试期间换上**更窄的一道门** ——
#: 只放行回环与网关那一个地址，别的一律炸。既不是"把门关掉"，也不是"绕过"：
#: 在这些测试里，出网限制比 session 那道门**更严**。
#: 原件必须在 import 期抓：pytest 先收集全部模块、再跑第一个测试，
#: 所以这一行执行时 `test_env` 的 fixture 还没装。
_REAL_SOCKET: dict = {
    "connect": socket.socket.connect,
    "connect_ex": socket.socket.connect_ex,
    "getaddrinfo": socket.getaddrinfo,
    "create_connection": socket.create_connection,
}

#: 本文件允许连的非回环地址。**恰好一个。**
ALLOWED_HOSTS: frozenset = frozenset({cfg.GATEWAY_HOST})


def _host_of(target) -> str:
    host = target[0] if isinstance(target, (tuple, list)) and target else target
    return str(host).strip("[]").lower() if isinstance(host, (str, bytes)) else ""


@contextlib.contextmanager
def _only_gateway_egress():
    """真打期间：只放行回环与 `ALLOWED_HOSTS`，别的一律 `AssertionError`。

    退出时**把进来时看到的那套装回去** —— 不是装回原件。装回原件就等于
    把 `test_env` 的门永久拆了，而它对**别的**测试是有效的判据。
    """
    installed = {"connect": socket.socket.connect, "connect_ex": socket.socket.connect_ex,
                 "getaddrinfo": socket.getaddrinfo,
                 "create_connection": socket.create_connection}

    def _mk(name, fn, idx):
        def wrapper(*args, **kw):
            h = _host_of(args[idx]) if len(args) > idx else ""
            if h.startswith("127.") or h in ("localhost", "::1", "", "0.0.0.0") \
                    or h in ALLOWED_HOSTS:
                return fn(*args, **kw)
            raise AssertionError(
                f"本文件只许连网关 {sorted(ALLOWED_HOSTS)} 与回环，"
                f"却出现了 {name} → {h!r}。垫片的全部取数都该经网关，"
                f"多出来的这条连接就是一条**未声明的数据源**")
        return wrapper

    socket.socket.connect = _mk("connect", _REAL_SOCKET["connect"], 1)
    socket.socket.connect_ex = _mk("connect_ex", _REAL_SOCKET["connect_ex"], 1)
    socket.getaddrinfo = _mk("getaddrinfo", _REAL_SOCKET["getaddrinfo"], 0)
    socket.create_connection = _mk("create_connection", _REAL_SOCKET["create_connection"], 0)
    try:
        yield
    finally:
        socket.socket.connect = installed["connect"]
        socket.socket.connect_ex = installed["connect_ex"]
        socket.getaddrinfo = installed["getaddrinfo"]
        socket.create_connection = installed["create_connection"]


def _gateway_up() -> bool:
    """探活。**同样走窄门** —— 它也是一次真实的 LAN 连接。"""
    try:
        with _only_gateway_egress():
            with urllib.request.urlopen(f"{GATEWAY}/healthz", timeout=5) as r:
                return r.status == 200
    except (urllib.error.URLError, OSError):
        return False


def live(fn):
    """真打网关的那些测试的装饰器。**只把"部署事实"翻成 skip，绝不翻"垫片缺陷"。**

    判据就是本包自己的异常分层：`GatewayUnreachable` = 连不上（部署），
    其它一切（`LookaheadDenied` / `MalformedRequest` / `AssertionError` / …）
    = 垫片或判据的问题，**照红不误**。

    为什么需要它（2026-09-06 实测）：全量跑到一半时别的代理重启了
    `genebench-gateway.service`（阶段一在做通道切换），我这 14 条真打测试
    同时变红 —— 而它们单跑全绿。一条**因为别人重启了服务**而红的测试，
    训练的是"看到红先忽略"，那正是 N-42 要挡的东西。
    所以这里在抛之前**再探一次活**：网关还活着却连不上 → 那是垫片的问题，红；
    网关确实没了 → skip，理由里写清是谁的事。
    """
    import functools

    @functools.wraps(fn)
    def wrapper(*a, **kw):
        if not _gateway_up():
            pytest.skip(f"网关 {GATEWAY} 没起来；起法见 ops/HANDOFF.md"
                        f"（genebench-gateway.service）")
        try:
            with _only_gateway_egress():
                return fn(*a, **kw)
        except gb.GatewayUnreachable as exc:
            if _gateway_up():
                raise                  # 网关活着却连不上 = 垫片的问题，不许 skip 掉
            pytest.skip(f"网关跑到一半没了（{exc}）—— 多半是别的代理在重启 "
                        f"genebench-gateway.service；这不是垫片的判据")
    return wrapper


# --------------------------------------------------------------------------- 工具


def _client(tag: str) -> gb.Client:
    """一条测试一个 `run_id` —— 切片键是 run_id，共用一个就互相污染条数。"""
    return gb.Client(base_url=GATEWAY, as_of=AS_OF, task_id=f"t22-{tag}",
                     config_id="gb-client-test", run_id=f"gbc.{tag}.{uuid.uuid4().hex[:8]}",
                     arm="strict")


def _use(cli: gb.Client) -> gb.Client:
    """把兼容层挂到这个客户端上（兼容层没有 as_of / 身份参数可传）。"""
    gb.reset()
    gb.configure(base_url=cli.base_url, as_of=cli.as_of, task_id=cli.task_id,
                 config_id=cli.config_id, run_id=cli.run_id, arm=cli.arm)
    return gb.client()


def _slice(run_id: str) -> list[dict]:
    """`access_log` 里属于这次运行的那些行。**按身份头过滤**，不按时间窗。"""
    if not ACCESS_LOG.exists():
        return []
    out = []
    for raw in ACCESS_LOG.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw or run_id not in raw:
            continue
        try:
            row = json.loads(raw)
        except ValueError:
            continue
        if row.get("run_id") == run_id:
            out.append(row)
    return out


def _direct(path: str, run_id: str, **params) -> dict:
    """绕开垫片、直接问网关 —— **交叉核的另一条腿**。

    用垫片自己的 `Client` 去核垫片，就是被核值与核它的基准同源（恒真）。
    """
    import urllib.parse
    q = urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(f"{GATEWAY}{path}?{q}", headers={
        "x-genebench-task-id": "t22-direct", "x-genebench-config-id": "gb-client-test",
        "x-gb-run-id": run_id})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


@pytest.fixture(autouse=True)
def _clean():
    yield
    gb.reset()


# --------------------------------------------------------------------------- 纯单元


def test_no_reference_dependency():
    """红线 2 的结构保证：垫片跑在**执行面容器**里，不许有一行 `reference/` 依赖。

    用 AST 查 import，不用 grep —— grep 会被注释里的字样骗到，也漏掉
    `__import__("reference")` 之外的写法。
    """
    banned = {"reference", "scorer", "gold", "snapshots", "genetask", "runner",
              "gateway", "genebench_config", "ops"}
    bad: list[str] = []
    for path in sorted(PKG_SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module or ""]
            for n in names:
                if n.split(".")[0] in banned:
                    bad.append(f"{path.relative_to(PKG_SRC)}:{node.lineno} import {n}")
    assert not bad, ("垫片 import 了答案面/数据面模块：\n  " + "\n  ".join(bad) +
                     "\n这些东西不在容器里，也不许进容器（红线 2）")


def test_third_party_deps_are_only_pandas_numpy():
    """依赖表是**可测的**：多一个三方依赖就多一次「容器里 pip install」的理由，
    而运行期装包被卡 4.1 §3.4 明令禁止。"""
    allowed = {"pandas", "numpy", "genebench_client"}
    stdlib = set(getattr(sys, "stdlib_module_names", ())) | {"__future__"}
    bad: list[str] = []
    for path in sorted(PKG_SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""] if node.level == 0 else []
            else:
                continue
            for n in names:
                top = n.split(".")[0]
                if top and top not in allowed and top not in stdlib:
                    bad.append(f"{path.relative_to(PKG_SRC)}:{node.lineno} {n}")
    assert not bad, "垫片只许依赖 pandas / numpy：\n  " + "\n  ".join(bad)


@pytest.mark.parametrize("raw,lake", [
    ("600000.SH", "600000.SH"), ("600000.SS", "600000.SH"), ("SH600000", "600000.SH"),
    ("600000", "600000.SH"), ("000001.SZ", "000001.SZ"), ("000001", "000001.SZ"),
    ("300750", "300750.SZ"), ("430047", "430047.BJ"), ("830799", "830799.BJ"),
    ("920819", "920819.BJ"), ("900901", "900901.SH"), ("200011", "200011.SZ"),
])
def test_code_writings_round_trip(raw, lake):
    assert gc.to_lake(raw) == lake


def test_920_is_beijing_not_shanghai():
    """**先判 920 再判首位 9**：北交所 920xxx 与沪市 B 股 900xxx 都以 9 开头。
    判反了就是把北交所的票发去了上交所 —— 取到的是另一只票，而不是报错。"""
    assert gc.infer_market("920819") == "BJ"
    assert gc.infer_market("900901") == "SH"


def test_yfinance_suffix_is_ss_not_sh():
    """yfinance 的沪市后缀是 `.SS`。写成 `.SH` 的话 yfinance 那边查不到，
    而我们这边照收 —— 于是"换个垫片就跑通了"变成了"换个垫片就静默换了票"。"""
    assert gc.to_yfinance("600000.SH") == "600000.SS"
    assert gc.to_yfinance("000001.SZ") == "000001.SZ"
    assert gc.to_akshare("600000.SH") == "600000"
    assert gc.to_panel("600000.SH") == "SH600000"


def test_unknown_code_raises_not_guesses():
    with pytest.raises(gc.CodeError):
        gc.to_lake("AAPL")
    with pytest.raises(gc.CodeError):
        gc.to_lake("700000")           # 首位 7 不在已知号段：抛，不猜一个默认市场


def test_as_of_required_is_fail_closed():
    """缺 as_of **不猜** —— 猜出来的值会让越界变成合法请求。"""
    gb.reset()
    os.environ.pop(gb.AS_OF_ENV, None)
    gb.configure(base_url=GATEWAY, task_id="t", config_id="c", run_id="r")
    with pytest.raises(gb.AsOfRequired):
        yf.download("600000.SS", start=WIN[0], end=WIN[1])


def test_yfinance_end_is_exclusive():
    """`end` 右开是 yfinance 的语义，网关的 `end_date` 是**闭**的。
    漏了这一天不会报错，只会多/少一根 K 线。"""
    lo, hi = yf._window("2026-06-01", "2026-06-11", None, AS_OF)
    assert (lo, hi) == ("2026-06-01", "2026-06-10")


def test_yfinance_does_not_clamp_explicit_lookahead():
    """**垫片不许自己把越界窗口截回 as_of。**

    截回去 = 那次前视尝试根本没到网关 = `access_log` 里什么都没有，
    而卡 5.1 的前视结算只认 access_log。于是「它试图看未来」与「它没试过」
    不可区分。第一版就是这么写的，这条测试是那个洞的记录。
    """
    lo, hi = yf._window("2026-07-01", "2026-07-11", None, AS_OF)
    assert hi == "2026-07-10" > AS_OF
    lo2, hi2 = ak._clamp("20260701", "20260710", AS_OF)
    assert hi2 == "2026-07-10" > AS_OF


def test_akshare_sentinel_defaults_are_not_lookahead():
    """akshare 签名里写死的 `20500101` 是**库的默认参数**，不是越界意图。"""
    lo, hi = ak._clamp(ak.SENTINEL_START, ak.SENTINEL_END, AS_OF)
    assert (lo, hi) == (ak.LAKE_START, AS_OF)


def test_only_daily_is_served():
    """接受一个被忽略的 `interval` 等于让调用方以为分钟线生效了。"""
    gb.reset()
    gb.configure(base_url=GATEWAY, as_of=AS_OF, task_id="t", config_id="c", run_id="r")
    with pytest.raises(gb.MalformedRequest):
        yf.download("600000.SS", start=WIN[0], end=WIN[1], interval="1m")
    with pytest.raises(gb.MalformedRequest):
        ak.stock_zh_a_hist("600000", period="weekly")


def test_unknown_bars_field_is_rejected_not_ignored():
    """拼错的字段名被静默跳过时，调用方拿到的仍是一份「看起来成功」的结果。"""
    cli = gb.Client(base_url=GATEWAY, as_of=AS_OF, task_id="t", config_id="c", run_id="r")
    with pytest.raises(gb.MalformedRequest):
        cli.bars([CODE], *WIN, fields=["clsoe"])


def test_tushare_unknown_field_is_rejected():
    with pytest.raises(gb.MalformedRequest):
        ts._wanted("ts_code,pct_chg", ts.DAILY_COLUMNS)


def test_compat_install_and_uninstall():
    assert set(gb.compat.install()) == {"yfinance", "tushare", "akshare"}
    assert sys.modules["yfinance"] is yf
    assert set(gb.compat.uninstall()) == {"yfinance", "tushare", "akshare"}
    assert "yfinance" not in sys.modules


def test_qlib_provider_missing_is_loud(tmp_path, monkeypatch):
    """provider 不在时**抛**，不回落到 qlib 社区 channel ——
    社区那份 `amount` 是千元、`volume` 是手，与本环境差 1000×/100×。"""
    monkeypatch.setenv(qp.PROVIDER_ENV, str(tmp_path / "nope"))
    with pytest.raises(qp.ProviderMissing):
        qp.provider_uri()
    root = tmp_path / "prov"
    (root / "calendars").mkdir(parents=True)
    (root / "calendars" / "day.txt").write_text("2026-06-30\n", encoding="utf-8")
    monkeypatch.setenv(qp.PROVIDER_ENV, str(root))
    assert qp.qlib_init_kwargs() == {"provider_uri": str(root), "region": "cn"}
    # PA-3：默认**原地返回**，不复制 —— 复制一份到别处只是多一个可写入口
    assert qp.ensure() == str(root)
    dest = tmp_path / "copy"
    assert qp.ensure(dest) == str(dest)
    with pytest.raises(qp.ProviderMissing):
        qp.ensure(dest)                       # 已存在不覆盖（PA-3）


# --------------------------------------------------------------------------- 真打网关


@live
def test_log_slice_equals_request_count():
    """**这条是本卡的核心判据**：经垫片取数后，`access_log` 里本 run 的切片
    条数 == 垫片自己数的请求次数，且路径逐条对上。

    对不上有两种形态，都致命：切片是 0（身份头没带上，日志按 run_id 切不出来），
    或条数少于请求数（有一条路径绕过了 `Client.request`，比如谁又直接 `urlopen` 了）。
    """
    cli = _client("slice")
    cli.healthz()
    cli.bars([CODE, CODE2], *WIN, fields=["close", "volume"])
    cli.adj([CODE], *WIN)
    cli.calendar(*WIN)
    cli.limits([CODE], *WIN)
    cli.universe("csi300", "2026-06-10")
    cli.tradability([CODE], "2026-06-10")
    rows = _slice(cli.run_id)
    assert len(rows) == len(cli.ledger), (
        f"日志切片 {len(rows)} 条 ≠ 垫片记的 {len(cli.ledger)} 次请求。"
        f"日志路径 {[r['path'] for r in rows]}；台账 {[e['path'] for e in cli.ledger]}")
    assert [r["path"] for r in rows] == [e["path"] for e in cli.ledger]
    assert {r["config_id"] for r in rows} == {"gb-client-test"}
    assert {r["arm"] for r in rows} == {"strict"}
    # `as_of` 每一条都带上了 —— 少一条就是一次没有 as_of 约束的取数
    assert all(r["as_of"] == AS_OF for r in rows if r["path"] != "/healthz")


@live
def test_compat_layers_also_land_in_the_slice():
    """三个兼容层各走一遍，条数照样对得上 —— 兼容层没有第二条取数路径。"""
    cli = _use(_client("compat"))
    yf.download([gc.to_yfinance(CODE), gc.to_yfinance(CODE2)], start=WIN[0], end="2026-06-11")
    ts.pro_api().daily(ts_code=CODE, start_date="20260601", end_date="20260610")
    ak.stock_zh_a_hist("600000", start_date="20260601", end_date="20260610", adjust="qfq")
    rows = _slice(cli.run_id)
    assert len(rows) == len(cli.ledger) > 0
    assert {r["path"] for r in rows} <= {"/bars", "/adj"}
    # `fields` 显式传了 —— 不传的话 S3 的读取集探针把它反推成「读了全表」
    assert all("fields" in r["params"] for r in rows if r["path"] == "/bars")


@live
def test_lookahead_is_denied_by_the_gateway_and_logged():
    """越界要由**网关**判成 403 并落日志，不是垫片自己拦下来。"""
    cli = _use(_client("ahead"))
    with pytest.raises(gb.LookaheadDenied) as exc:
        yf.download(gc.to_yfinance(CODE), start="2026-07-01", end="2026-07-11")
    assert exc.value.reason == "range_end_after_asof"
    assert exc.value.status == 403
    denied = [r for r in _slice(cli.run_id) if r["status"] == 403]
    assert denied, "403 没落进 access_log —— 越权率就没有数据源"
    assert denied[0]["reason"] == "range_end_after_asof"


@live
@pytest.mark.parametrize("call,kind,api", [
    (lambda: yf.Ticker("600000.SS").news, "news", "yfinance.Ticker.news"),
    (lambda: yf.Ticker("600000.SS").financials, "fundamentals", "yfinance.Ticker.financials"),
    (lambda: ts.pro_api().fina_indicator(ts_code=CODE), "fundamentals",
     "tushare.pro.fina_indicator"),
    (lambda: ts.pro_api().moneyflow(ts_code=CODE), "moneyflow", "tushare.pro.moneyflow"),
    (lambda: ak.stock_news_em(symbol="600000"), "news", "akshare.stock_news_em"),
    (lambda: ak.stock_individual_fund_flow(stock="600000"), "moneyflow",
     "akshare.stock_individual_fund_flow"),
])
def test_no_data_leaves_a_trace_in_the_gateway_log(call, kind, api):
    """新闻 / 财务 / 资金流：抛 `NoData` **并且**在 access_log 上留一行。

    只抛不留痕的话，「被测系统尝试去拿新闻」这件事在数据面上什么都没有 ——
    与「它根本没想过要新闻」不可区分。
    """
    cli = _use(_client("nodata"))
    with pytest.raises(gb.NoData) as exc:
        call()
    assert exc.value.kind == kind and exc.value.api == api
    assert exc.value.traced is True
    rows = _slice(cli.run_id)
    hit = [r for r in rows if r["path"] == f"{nd.NODATA_PREFIX}/{kind}"]
    assert hit, f"没有 {nd.NODATA_PREFIX}/{kind} 的日志行；切到的是 {[r['path'] for r in rows]}"
    assert hit[-1]["status"] == 404 and hit[-1]["params"]["api"] == api
    assert hit[-1]["params"]["as_of"] == AS_OF


@live
def test_no_data_never_touches_fundamentals_endpoint():
    """留痕**不能以泄题为代价**：`/fundamentals` 是白名单里真实存在的端点，
    打它会 200 —— 那等于把「题面没告诉 agent 它有」的数据递到手里（N-58①）。"""
    cli = _use(_client("nofund"))
    with pytest.raises(gb.NoData):
        ts.pro_api().income(ts_code=CODE)
    assert all(r["path"] != "/fundamentals" for r in _slice(cli.run_id))


@live
def test_yfinance_values_match_a_direct_gateway_fetch():
    """逐值交叉核：垫片的 OHLCV 必须等于**绕开垫片**直接问网关拿到的那一份。"""
    cli = _use(_client("yfval"))
    got = yf.download(gc.to_yfinance(CODE), start=WIN[0], end="2026-06-11", auto_adjust=False)
    raw = _direct("/bars", "gbc.direct.yfval", as_of=AS_OF, code=CODE,
                  start_date="20260601", end_date="20260610",
                  fields="open,high,low,close,volume")["data"]
    raw = [r for r in raw if r.get("close") is not None]
    assert list(got.columns) == list(yf._ORDER_RAW)
    assert len(got) == len(raw)
    assert got["Close"].tolist() == [r["close"] for r in raw]
    assert got["Volume"].tolist() == [float(r["volume"]) for r in raw]
    assert got.index[0].strftime("%Y-%m-%d") == raw[0]["date"]
    # Adj Close 的基准是**窗口内最后一天**（as-of 世界里没有"今天"）
    assert got["Adj Close"].iloc[-1] == pytest.approx(got["Close"].iloc[-1])


@live
def test_tushare_units_are_lots_and_kiloyuan():
    """湖是 **股/元**，tushare 原生是 **手/千元**。不换算的话任何成交额口径
    静默差 100× / 1000×，而没有任何东西会报错。"""
    cli = _use(_client("tsunit"))
    got = ts.pro_api().daily(ts_code=CODE, start_date="20260601", end_date="20260603")
    raw = _direct("/bars", "gbc.direct.tsunit", as_of=AS_OF, code=CODE,
                  start_date="20260601", end_date="20260603",
                  fields="open,high,low,close,volume,amount")["data"]
    raw = [r for r in raw if r.get("close") is not None]
    assert list(got.columns) == list(ts.DAILY_COLUMNS)
    assert got["trade_date"].tolist() == [r["date"].replace("-", "") for r in raw]
    assert got["vol"].tolist() == [r["volume"] / 100 for r in raw]
    assert got["amount"].tolist() == [r["amount"] / 1000 for r in raw]
    # 单位自洽：千元 × 1000 / (手 × 100) 应该落在当天的 [low, high] 里
    px = got["amount"] * 1000 / (got["vol"] * 100)
    assert ((px >= got["low"] * 0.99) & (px <= got["high"] * 1.01)).all()


@live
def test_tushare_index_weight_has_no_fabricated_weight_column():
    """`/universe` 只发 PIT 成分，不发权重。给一列 NaN 会让 `weight.sum()` 静默变 0 ——
    所以这里让它 `KeyError`：响的错，不是哑的错。"""
    _use(_client("iw"))
    iw = ts.pro_api().index_weight(index_code="000300.SH", trade_date="20260610")
    assert list(iw.columns) == list(ts.INDEX_WEIGHT_COLUMNS)
    assert "weight" not in iw.columns
    assert len(iw) == 300


@live
def test_akshare_hist_columns_and_qfq_base():
    """akshare 列名与单位（成交量**手**、成交额**元**），前复权基准是窗口内最后一天。"""
    _use(_client("akhist"))
    raw_df = ak.stock_zh_a_hist("600000", start_date="20260601", end_date="20260610")
    qfq = ak.stock_zh_a_hist("600000", start_date="20260601", end_date="20260610", adjust="qfq")
    hfq = ak.stock_zh_a_hist("600000", start_date="20260601", end_date="20260610", adjust="hfq")
    assert list(raw_df.columns) == list(ak.HIST_COLUMNS)
    assert raw_df["股票代码"].iloc[0] == "600000"
    assert raw_df["日期"].iloc[0] == "2026-06-01"
    # 前复权：窗口最后一天 == 不复权最后一天（基准就是它）
    assert qfq["收盘"].iloc[-1] == pytest.approx(raw_df["收盘"].iloc[-1], abs=1e-4)
    # 后复权 = 原价 × adj_factor，一定不小于原价（本窗口 factor > 1）
    assert hfq["收盘"].iloc[-1] > raw_df["收盘"].iloc[-1]
    assert (raw_df["成交额"] / (raw_df["成交量"] * 100) >= raw_df["最低"] * 0.99).all()


@live
def test_akshare_calendar_stops_at_as_of():
    """"实时"日历也受 as_of 约束 —— 未来交易日是**真的查得到**的那条越界路径。"""
    _use(_client("akcal"))
    cal = ak.tool_trade_date_hist_sina()
    assert len(cal) > 4000
    assert cal["trade_date"].iloc[-1].isoformat() <= AS_OF


@live
def test_universe_all_is_the_market_not_an_index():
    _use(_client("uni"))
    cli = gb.client()
    members = cli.members("all", "2026-06-10")
    assert len(members) > 5000
    assert all(m.endswith((".SH", ".SZ", ".BJ")) for m in members)


# ══════════════════════════════════════════ 阶段二红队修复（2.rt）：垫片 README 的三条 major
#
# 垫片 README 是 `integrations/README.md` §1③/§4 明确指过去的那一份 —— 按顺序读的作者
# 会**先**看到它。所以它与主手册、与契约冲突的说法必须当判据看，不是文档口味问题。

CLIENT_README = REPO / "integrations" / "genebench_client" / "README.md"


def _shim_readme() -> str:
    return CLIENT_README.read_text(encoding="utf-8")


def test_the_shim_readme_does_not_send_authors_to_task_yaml():
    """finding 5①：`task.yaml` 不在容器里（主手册 §1④ 与契约 §1.1 都这么说）。

    垫片 README 开头第一屏原来写「从 task.yaml 的 as_of 读来」，
    照它走会先做一次找不到文件的调查。
    """
    text = _shim_readme()
    assert "从 task.yaml 的 as_of 读来" not in text, "垫片 §1 还在让作者读 task.yaml"
    head = text[:text.find("## 2.")]
    assert "INSTRUCTION.md" in head, "垫片 §1 没告诉作者 as_of 真正从哪来"
    assert 'spec["as_of"]' not in text, "`spec` 从哪来没有定义过，不能出现在可抄的行里"


def test_the_shim_readme_marks_402_as_unreachable():
    """finding 5②：预算闸是 429 `budget_exceeded`，全树没有 402 的落点。

    代码侧的事实取自边车：超预算返回 429。
    """
    proxy = (REPO / "runner" / "c41" / "egress_proxy.py").read_text(encoding="utf-8")
    assert "budget_exceeded" in proxy and "429" in proxy, (
        "边车不再用 429 报预算耗尽 —— 垫片 README 的异常表要跟着改")
    text = _shim_readme()
    i = text.find("| 402 |")
    assert i > 0, "异常表里的 402 行不见了"
    row = text[i:text.find("\n", i)]
    assert "429" in row and ("没有" in row or "不存在" in row), (
        "402 那一行没说明「本项目里没有东西返回 402」")


def test_the_shim_readme_documents_the_adjust_basis_of_every_layer():
    """finding 4：三个 compat 层的复权口径没有任何文档，而 `adjust` 声明写错是违例。

    代码侧的事实：akshare 层认 `qfq`/`hfq`，且在本地按 `/adj` 的因子算。
    """
    src = (REPO / "integrations" / "genebench_client" / "src" / "genebench_client"
           / "compat" / "akshare.py").read_text(encoding="utf-8")
    assert "qfq" in src and "hfq" in src, "akshare 层不再认 qfq/hfq 了 —— 偏离表要跟着改"
    text = _shim_readme()
    i = text.find("| 复权口径 |")
    assert i > 0, "§4 的偏离表没有「复权口径」这一行"
    row = text[i:text.find("\n", i)]
    for token in ("none", "pre", "post", "adj_factor"):
        assert token in row, f"复权口径那一行没写 {token}"


def test_the_shim_readme_documents_panel_ref_and_field_map():
    """finding 6：`panel_ref.sha256` 对什么算、`field_map` 的方向、面板写在哪，无处可查。

    三样都有唯一答案：摘要是**文件字节**的（`genetask/file_contract.py::sha256_of`），
    序列化与落点由题面固定槽逐字给出（`FILE_SPECS`），方向是「源字段 → 目标字段」。
    """
    import sys as _sys
    _sys.path.insert(0, str(REPO))
    from genetask.file_contract import spec_for

    sp = spec_for("S2")
    text = _shim_readme()
    seg = text[text.find("### 7.3"):text.find("### 7.4")]
    assert seg, "找不到 §7.3"
    assert sp["path"] in seg, f"§7.3 没说面板写在 {sp['path']}"
    assert "字节摘要" in seg, "§7.3 没说 sha256 是文件字节的摘要"
    assert "源字段 → 目标字段" in seg, "§7.3 没说 field_map 的方向"
    for col in sp["columns"]:
        assert col in seg, f"§7.3 的规范序列化漏了列 {col}"
    assert sp["float_format"] in seg, "§7.3 没写浮点格式"


def test_the_shim_readme_warns_that_compat_fields_do_not_reach_the_gateway():
    """finding 1：compat 的 `fields` 只裁剪返回值，网关上的读取集仍是完整列集。"""
    full = '"open", "high", "low", "close", "volume", "amount"'
    hard = [p.name for p in sorted((REPO / "integrations" / "genebench_client" / "src"
                                    / "genebench_client" / "compat").glob("*.py"))
            if full in p.read_text(encoding="utf-8")]
    assert hard, "compat 层不再按完整列集请求了 —— 偏离表那一行要跟着改"
    text = _shim_readme()
    i = text.find("| compat 的 `fields` |")
    assert i > 0, "§4 的偏离表没有「compat 的 `fields`」这一行"
    row = text[i:text.find("\n", i)]
    assert "只裁剪返回值" in row and "declared_reads" in row, "那一行没说清后果"
    assert "bars(" in row, "那一行没给替代写法"
