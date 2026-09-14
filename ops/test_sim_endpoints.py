# -*- coding: utf-8 -*-
"""卡 4.4 的**端点**侧验收：SIM-A/B/D/G/H/J/L + N-45。

纯引擎的语义在 `ops/test_sim_engine.py`（那一轮不需要起服务）。
这一轮测的是「挂上网关之后」才成立的那些：路由白名单、身份头、
**拒绝以与网关 deny 同格式同切片键落 access_log**、以及 POST body 的重复键。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

import genebench_config as cfg                          # noqa: E402
from gateway import access_log                          # noqa: E402
from gateway.app import ALLOWED_ROUTES, create_app, registered_paths  # noqa: E402
from gateway.errors import Reason                       # noqa: E402
from gateway.routers import sim as SIM                  # noqa: E402
from gateway.sim_engine import SimEngine                # noqa: E402

CAL = ["2026-07-01", "2026-07-02", "2026-07-03", "2026-07-06"]
SYM = "600000.SH"
CID, TID = "cfg-sim", "s8-cor-01"
#: **会话键的一半**（裁定 N-88，2026-09-05）：`(run_id, task_id)`，不是 `(config_id, task_id)`。
#: 三个头都必需 —— `/sim/*` 对缺 `x-gb-run-id` 是 fail-closed 的。
RID = "s8-cor-01.strict.cfg-sim.r01"
H = {"x-genebench-config-id": CID, "x-genebench-task-id": TID, "x-gb-run-id": RID}


def _engine(**kw) -> SimEngine:
    return SimEngine(calendar=list(CAL), window_end=CAL[-1],
                     closes={(d, SYM): 10.0 + i for i, d in enumerate(CAL)}, **kw)


@pytest.fixture
def client(tmp_path, monkeypatch):
    """每个用例一份**自己的** access_log —— 共用一份的话，
    「这次请求有没有落 deny」会被上一个用例的行污染。"""
    monkeypatch.setattr(access_log, "ACCESS_LOG", tmp_path / "gateway_access.jsonl")
    monkeypatch.setattr(cfg, "LOGS", tmp_path, raising=False)
    SIM.reset_sessions()
    yield TestClient(create_app(), raise_server_exceptions=False)
    SIM.reset_sessions()
    # 有用例会把工厂摘掉来测「没有会话」那一支。**在这里装回去** ——
    # 摘了不装回，后面每一条用例都在一个没有工厂的网关上跑，
    # 而它们大多自己 register_session，所以照样绿：又一个恒绿。
    from gateway import sim_factory
    sim_factory.register()


def _log_lines(tmp_path) -> list[dict]:
    p = tmp_path / "gateway_access.jsonl"
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


# --------------------------------------------------------------- SIM-A

def test_sim_a_routes_are_exactly_the_whitelist():
    """逐条登记，**多一条也红**。写 `/sim/{op}` 一条通配会让
    「实现里多写了一个没在契约里的操作」变成静默可达。"""
    app = create_app()
    assert registered_paths(app) == set(ALLOWED_ROUTES)
    for p in ("/sim/state", "/sim/order", "/sim/cancel", "/sim/advance", "/sim/log"):
        assert p in ALLOWED_ROUTES


def test_sim_m_no_answer_surface_in_sim_paths():
    """SIM-M：`/sim/*` 的任何路径都不含答案面字样。"""
    from gateway.app import FORBIDDEN_PATH_TOKENS
    for p in ALLOWED_ROUTES:
        low = p.lower()
        assert not any(tok in low for tok in FORBIDDEN_PATH_TOKENS), p


# --------------------------------------------------------------- SIM-B

@pytest.mark.parametrize("drop", ["x-genebench-config-id", "x-genebench-task-id"])
def test_sim_b_missing_identity_header_is_denied_and_logged(client, tmp_path, drop):
    SIM.register_session(RID, TID, _engine())
    h = {k: v for k, v in H.items() if k != drop}
    r = client.get("/sim/state", headers=h)
    assert r.status_code // 100 != 2, r.text
    rows = [x for x in _log_lines(tmp_path) if x["path"] == "/sim/state"]
    assert rows and rows[-1]["decision"] == "deny", rows


# --------------------------------------------------------------- SIM-H / N-45

def test_sim_h_overreach_403_lands_in_access_log(client, tmp_path):
    """**N-45 的修法在这里被验**：先前 sim 的拒单抛的是引擎自己的 `SimError`，
    永远进不了 access_log —— 于是「越权率 = 403 次数 / 请求总数，来源网关日志」
    这条契约**根本没有数据源**。"""
    SIM.register_session(RID, TID, _engine(permitted_operations=("order", "advance",
                                                                "state", "log")))
    r = client.post("/sim/cancel", headers=H, json={"order_id": "x"})
    assert r.status_code == 403, r.text
    rows = [x for x in _log_lines(tmp_path) if x["path"] == "/sim/cancel"]
    assert len(rows) == 1, rows
    row = rows[0]
    assert row["decision"] == "deny"
    assert row["reason"] == Reason.OPERATION_NOT_PERMITTED.value
    assert row["task_id"] == TID and row["config_id"] == CID


def test_sim_h_slice_key_is_not_a_free_lunch(client, tmp_path):
    """N-36 的环境侧对应物：**不在环境侧把它还原**。
    自报一个不存在的 config_id 不会凭空造出一个会话，也不会让这次请求消失 ——
    它照样落一行 deny（切片变空 ≠ 零请求）。"""
    SIM.register_session_factory(None)      # 本条测的是「没有工厂时不会凭空有会话」
    SIM.register_session(RID, TID, _engine())
    # **伪造的是 `run_id`** —— 裁定 N-88 之后它才是会话键；伪造 `config_id` 现在
    # 落到的是同一个会话（那条判据在 `ops/test_sim_factory.py`）。
    r = client.get("/sim/state", headers={**H, "x-gb-run-id": "run-forged"})
    assert r.status_code == 404
    rows = [x for x in _log_lines(tmp_path) if x["path"] == "/sim/state"]
    assert rows and rows[-1]["decision"] == "deny", rows
    assert rows[-1]["run_id"] == "run-forged", "网关照记不核 —— 核在边车与三核那一侧"


# --------------------------------------------------------------- SIM-C / D

def test_sim_c_advance_takes_no_date_parameter(client, tmp_path):
    """**靠接口形状，不靠文档禁止** —— 端点收不到日期参数，就没有可以违反的规则。"""
    SIM.register_session(RID, TID, _engine())
    r = client.post("/sim/advance", headers=H, json={"to": "2026-07-06"})
    assert r.status_code == 422, r.text
    assert "不接受任何参数" in r.text
    ok = client.post("/sim/advance", headers=H)
    assert ok.status_code == 200 and ok.json()["sim_date"] == CAL[1]


def test_sim_d_advance_emits_exactly_one_audit_event(client):
    """`advance` 不落事件，重放就少了时间轴 —— 同一串 order/cancel 在不同的
    推进次数下终态不同，而重放器会算出「一致」，因为它根本不知道中间推进过。"""
    SIM.register_session(RID, TID, _engine())
    before = client.get("/sim/log", headers=H).json()["events"]
    client.post("/sim/advance", headers=H)
    after = client.get("/sim/log", headers=H).json()["events"]
    added = after[len(before):]
    assert len(added) == 1 and added[0]["type"] == "advance", added
    assert added[0]["payload"]["from"] == CAL[0] and added[0]["payload"]["to"] == CAL[1]


# --------------------------------------------------------------- SIM-G / J / L

def test_sim_g_state_is_read_only_projection(client):
    """只有 GET —— 「可写的投影」这个形状在接口上不存在。"""
    SIM.register_session(RID, TID, _engine())
    for verb in ("post", "put", "patch", "delete"):
        r = getattr(client, verb)("/sim/state", headers=H)
        assert r.status_code == 405, (verb, r.status_code)


def test_sim_j_order_is_idempotent_but_advance_is_not(client):
    SIM.register_session(RID, TID, _engine())
    body = {"symbol": SYM, "side": "buy", "qty": 100,
            "client_order_id": "c-1", "reference_close": 10.0}
    a = client.post("/sim/order", headers=H, json=body).json()
    b = client.post("/sim/order", headers=H, json=body).json()
    assert a["order_id"] == b["order_id"]
    orders = [e for e in client.get("/sim/log", headers=H).json()["events"]
              if e["type"] == "order"]
    assert len(orders) == 1, orders
    client.post("/sim/advance", headers=H)
    client.post("/sim/advance", headers=H)
    assert client.get("/sim/state", headers=H).json()["sim_date"] == CAL[2], \
        "advance **不幂等**是它的正确行为"


def test_sim_l_window_exhausted_is_409_and_logged(client, tmp_path):
    SIM.register_session(RID, TID, _engine())
    for _ in range(len(CAL) - 1):
        assert client.post("/sim/advance", headers=H).status_code == 200
    r = client.post("/sim/advance", headers=H)
    assert r.status_code == 409, r.text
    rows = [x for x in _log_lines(tmp_path) if x["path"] == "/sim/advance"]
    assert rows[-1]["decision"] == "deny"
    assert rows[-1]["reason"] == Reason.WINDOW_EXHAUSTED.value


# --------------------------------------------------------------- §1.3 已知洞

def test_post_body_duplicate_key_is_refused(client):
    """`SCALAR_PARAMS` 中间件只查 query string，**管不到 POST 的 JSON body**。
    `json.loads` 默认「后者胜」—— 那正是「静默择一」。"""
    SIM.register_session(RID, TID, _engine())
    raw = ('{"symbol":"600000.SH","side":"buy","qty":100,"qty":200,'
           '"client_order_id":"c-2","reference_close":10.0}')
    r = client.post("/sim/order", headers={**H, "content-type": "application/json"},
                    content=raw)
    assert r.status_code == 422, r.text
    assert "重复键" in r.text and "qty" in r.text


def test_order_requires_reference_close(client):
    """委托体的 `reference_close` 是**提交时价的记录**，无论 Slip 基准取哪一个都要带 ——
    与「拿哪个价当零点」的口径选择是两回事，两个名字相近的东西不要合并。"""
    SIM.register_session(RID, TID, _engine())
    r = client.post("/sim/order", headers=H,
                    json={"symbol": SYM, "side": "buy", "qty": 100,
                          "client_order_id": "c-3"})
    assert r.status_code == 422 and "reference_close" in r.text


def test_every_sim_request_lands_exactly_one_access_log_row(client, tmp_path):
    """越权率的分母是「数据与操作请求总数」—— 少记一行，分母就小一点，
    而越权率**看起来更低**。方向对我们有利的那种静默错误。"""
    SIM.register_session(RID, TID, _engine())
    client.get("/sim/state", headers=H)
    client.get("/sim/log", headers=H)
    client.post("/sim/advance", headers=H)
    rows = [x for x in _log_lines(tmp_path) if x["path"].startswith("/sim/")]
    assert len(rows) == 3, [r["path"] for r in rows]
    assert all(r["decision"] == "allow" for r in rows), rows
    assert all(r["task_id"] == TID for r in rows)


# --------------------------------------------------------------- SIM-E

def test_sim_e_asof_is_capped_by_sim_date(client, tmp_path):
    """没有这条，S8 的前视是**免费**的：agent 在 sim_date 时直接请求
    `as_of=冻结线`，拿到未来的价格再决定今天下什么单 ——
    数据面全程合法、网关日志全绿，而交易决策是拿未来做出来的。"""
    SIM.register_session(RID, TID, _engine())
    late = client.get("/bars", headers=H,
                      params={"code": SYM, "as_of": CAL[-1],
                              "start_date": CAL[0], "end_date": CAL[0]})
    assert late.status_code == 403, late.text
    rows = [x for x in _log_lines(tmp_path) if x["path"] == "/bars"]
    assert rows and rows[-1]["decision"] == "deny"
    assert rows[-1]["reason"] in {Reason.ASOF_BEYOND_FREEZE.value,
                                  Reason.TARGET_AFTER_ASOF.value,
                                  Reason.RANGE_END_AFTER_ASOF.value}, rows[-1]
    assert rows[-1]["extra"]["run_ceiling"] == CAL[0].replace("-", "")


def test_sim_e_ceiling_moves_only_after_advance(client):
    """**推进后才前移**，不是推进时一起判 —— 判定必须先于取数。"""
    SIM.register_session(RID, TID, _engine())
    p = {"code": SYM, "as_of": CAL[1], "start_date": CAL[0], "end_date": CAL[0]}
    assert client.get("/bars", headers=H, params=p).status_code == 403
    client.post("/sim/advance", headers=H)
    r = client.get("/bars", headers=H, params=p)
    assert r.status_code != 403, r.text


def test_sim_e_does_not_touch_runs_without_a_sim_session(client):
    """S1..S7 没有模拟盘会话 —— 不该凭空多出一个上界。

    **这条原来用的是 `s8-cor-01` 的头**（模块级 `H`）—— 说的是 S1..S7，测的是 S8。
    红队 2026-09-05 补 S8 无会话判据时才暴露：判据一改它就红，
    而它红的理由与它的 docstring 无关。**说一件事、测另一件事的测试，
    在被别的改动碰到之前一直是绿的。**
    """
    h = {**H, "x-genebench-task-id": "s3-cor-01"}
    r = client.get("/bars", headers=h,
                   params={"code": SYM, "as_of": "2026-07-31",
                           "start_date": "2026-07-01", "end_date": "2026-07-01"})
    assert r.status_code != 403, r.text


def test_s8_without_a_session_is_denied_not_unbounded(client):
    """**S8 没有会话 ⇒ 拒绝**，不是「无上界」（红队 2026-09-05，A 类）。

    原来 `current_sim_date` 没会话就返回 None，`guard_run_ceiling` 里
    `if ceiling and ...` 于是整条静默。S8 的 agent 只要**先取数、后交易**，
    前视就是免费的 —— 数据面全程合法、网关日志全绿。
    """
    SIM.register_session_factory(None)      # 显式：本条测的是**没有会话**那一支
    r = client.get("/bars", headers=H,          # H 的 task_id 是 s8-cor-01
                   params={"code": SYM, "as_of": "2026-07-31",
                           "start_date": "2026-07-01", "end_date": "2026-07-01"})
    assert r.status_code == 403, r.text
    body = r.json()
    assert body["reason"] == Reason.ASOF_BEYOND_FREEZE.value, body
    assert body["context"]["run_ceiling"] is None


def test_s8_with_a_session_uses_the_sim_date_as_ceiling(client):
    """有会话之后上界就是 `sim_date` —— 反面：这条防「一律拒绝」的恒红实现。"""
    SIM.register_session(RID, TID, _engine())
    ok = client.get("/bars", headers=H,
                    params={"code": SYM, "as_of": CAL[0],
                            "start_date": CAL[0], "end_date": CAL[0]})
    assert ok.status_code != 403, ok.text
    late = client.get("/bars", headers=H,
                      params={"code": SYM, "as_of": CAL[-1],
                              "start_date": CAL[0], "end_date": CAL[0]})
    assert late.status_code == 403, late.text
    # 上界在 context 里是紧凑形（网关内部统一口径）——
    # 写死一个带横杠的字面量会让这条测试测的是格式而不是语义。
    assert late.json()["context"]["run_ceiling"] == CAL[0].replace("-", "")


def test_sim_e_decision_is_made_before_any_read(client, tmp_path):
    """先取后判会在日志里留下一次实际读取，卡 5.1 结算前视时分不清
    「读了但没给」与「根本没读」。判据：被拒的那行 `rows` 必须是 None。"""
    SIM.register_session(RID, TID, _engine())
    client.get("/bars", headers=H,
               params={"code": SYM, "as_of": CAL[-1],
                       "start_date": CAL[0], "end_date": CAL[0]})
    row = [x for x in _log_lines(tmp_path) if x["path"] == "/bars"][-1]
    assert row["rows"] is None, f"被拒的请求却记了行数 —— 说明先取了再判：{row}"


def test_ceiling_logic_lives_in_asof_not_in_each_endpoint():
    """`asof.py` 的模块纪律：所有端点都必须过这里，不许各写各的。
    判定在 asof.py，**调用点**在中间件（唯一看得见每个请求的地方）——
    逐端点调用漏一个就是一条免费的前视通道，而漏了没有任何东西会说。"""
    from gateway import asof
    from pathlib import Path
    src = Path(asof.__file__).read_text(encoding="utf-8")
    assert "def guard_run_ceiling" in src
    # 查**调用**（`名字(`），不查名字出现 —— 查名字会把文档字符串里的提及
    # 也算成调用（sim.py 的 docstring 里就写着这个名字）。同样的坑：
    # 那条「只有一个 compose 渲染出口」的测试曾经命中自己。
    import ast

    def _calls(path) -> int:
        tree = ast.parse(Path(path).read_text(encoding="utf-8"))
        n = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                name = getattr(f, "attr", None) or getattr(f, "id", None)
                n += name == "guard_run_ceiling"
        return n

    gw = Path(asof.__file__).parent
    assert _calls(gw / "app.py") == 1, "中间件之外还有别处在判"
    for r in ("market.py", "reference.py", "sim.py"):
        assert _calls(gw / "routers" / r) == 0, f"{r} 自己又判了一遍"


# =============================================================== 红队一轮（2026-09-05）
# 攻击者的 case **原样入库**（协议：不重写攻击者的 case —— 重写会把作者的理解再带进去一次）。
# 修前实测输出写在各条 docstring 里。

@pytest.mark.parametrize("qty,before", [
    (300.0, "200 accepted"),        # JSON 浮点
    (300.7, "200 accepted，引擎里记成 300（静默截断）"),
    ("300", "200 accepted"),        # 字符串
])
def test_rt1_router_coercion_no_longer_kills_the_engine_type_check(client, qty, before):
    """**A 类**：路由层 `int(body["qty"])` 让引擎的类型判据成为死代码（D-06）。

    修前实测：`qty=300.0` / `qty="300"` → 200 accepted；`qty=300.7` → 200 且**记成 300**。
    同样的值**直接喂引擎**三个都被拒 —— 判据写在那儿，没有任何请求能送到它面前。
    """
    SIM.register_session(RID, TID, _engine())
    r = client.post("/sim/order", headers=H, json={
        "symbol": SYM, "side": "buy", "qty": qty,
        "client_order_id": "c1", "reference_close": 10.0})
    assert r.status_code == 422, f"修前是 {before}，现在应当 422：{r.text}"
    assert r.json()["context"]["field"] == "qty"


def test_rt2_reference_close_true_no_longer_buys_ten_times_leverage(client):
    """**A 类 high**：`reference_close` 是冻结额基准，`true` 被强转成 1.0。

    修前实测：现金 1,000,000 时提交 `qty=100000, reference_close=true` → 200 accepted，
    **冻结 100,000**（真价 10.0 应冻结 1,000,000）—— 凭空十倍杠杆，
    `insufficient_cash` 全程不响。
    """
    eng = _engine()
    SIM.register_session(RID, TID, eng)
    cash0 = eng.cash
    r = client.post("/sim/order", headers=H, json={
        "symbol": SYM, "side": "buy", "qty": 100000,
        "client_order_id": "x1", "reference_close": True})
    assert r.status_code == 422, r.text
    assert r.json()["context"]["field"] == "reference_close"
    assert eng.cash == cash0, "被拒的委托不该动现金"


def test_rt2b_string_reference_close_is_refused(client):
    SIM.register_session(RID, TID, _engine())
    r = client.post("/sim/order", headers=H, json={
        "symbol": SYM, "side": "buy", "qty": 300,
        "client_order_id": "x2", "reference_close": "10.0"})
    assert r.status_code == 422 and r.json()["context"]["field"] == "reference_close"


@pytest.mark.parametrize("oid", [{"a": 1}, None, 7, ["o000001"]])
def test_rt3_cancel_with_a_non_string_order_id_is_a_format_error(client, oid):
    """**B 类**：`str(body["order_id"])` 把格式错误报成业务结果。

    修前实测：`{"order_id": {"a": 1}}` → **200 `{"status": "not_found"}`**。
    「请求写错了」与「这单不存在」是两回事，混成一个会让 Audit 重放对不上。
    """
    SIM.register_session(RID, TID, _engine())
    r = client.post("/sim/cancel", headers=H, json={"order_id": oid})
    assert r.status_code == 422, r.text
    assert r.json()["context"]["field"] == "order_id"


def test_rt_legit_order_still_passes(client):
    """**误拒视角**：合法委托必须照常通过 —— 恒红的类型门与恒绿的一样会被绕过。"""
    SIM.register_session(RID, TID, _engine())
    r = client.post("/sim/order", headers=H, json={
        "symbol": SYM, "side": "buy", "qty": 300,
        "client_order_id": "ok-1", "reference_close": 10.0})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "accepted"


def test_rt_integer_valued_float_is_still_refused(client):
    """`300.0` 与 `300` 在 JSON 里是**两个类型**。「反正值一样」正是强转的辩护词，
    而它同时让 `300.7` 通过 —— 判据必须落在类型上，不落在值上。"""
    SIM.register_session(RID, TID, _engine())
    r = client.post("/sim/order", headers=H, json={
        "symbol": SYM, "side": "buy", "qty": 300.0,
        "client_order_id": "f1", "reference_close": 10.0})
    assert r.status_code == 422


def test_rt1b_bool_qty_is_refused_by_the_router_not_by_the_engine(client):
    """`true` 必须在**路由层**被判掉。

    留给引擎接也会 422（`bad_qty`：`int(True)` = 1，不是 100 的倍数）——
    但那是**碰巧**：判据是「1 不是 100 的倍数」，不是「true 不是整数」。
    换个 `qty=true` 的场景（比如将来允许 1 股）就会静默通过。
    判据落在哪一层，决定了它换个场景还成不成立。
    """
    SIM.register_session(RID, TID, _engine())
    r = client.post("/sim/order", headers=H, json={
        "symbol": SYM, "side": "buy", "qty": True,
        "client_order_id": "b1", "reference_close": 10.0})
    assert r.status_code == 422, r.text
    ctx = r.json()["context"]
    assert ctx.get("field") == "qty", f"被引擎接住了而不是路由层：{ctx}"
    assert ctx.get("got") == "bool"


def test_rt4_ceiling_exists_on_the_very_first_data_request(client):
    """**A 类**：会话必须在**取数时**就物化，否则「还没碰过 /sim」= 没有上界。

    修前实测：`current_sim_date` 只 `.get()`，没会话返回 None，
    `guard_run_ceiling` 里 `if ceiling and ...` 整条静默 ——
    S8 的 agent 先取完未来数据再开始交易，前视**免费**。

    这里注册一个工厂，然后**一次 `/sim/*` 都不调**，直接取数：
    上界必须已经生效（拒绝 as_of 越过 sim_date 的请求）。
    """
    made = {"n": 0}

    def factory(cid, tid, *, set_id):
        # `set_id` 必填（N-578）：工厂签名跟着生产路径走，这里也要收得下它
        assert set_id, "工厂没拿到 set_id —— 会话键就少了一半"
        if not tid.startswith("s8-"):
            return None                      # S1..S7 不该凭空多出上界
        made["n"] += 1
        return _engine()

    SIM.reset_sessions()
    SIM.register_session_factory(factory)
    try:
        r = client.get("/bars", headers=H,
                       params={"code": SYM, "as_of": CAL[-1],
                               "start_date": CAL[0], "end_date": CAL[0]})
        assert made["n"] == 1, "取数没有物化会话 —— 上界不会存在"
        assert r.status_code == 403, r.text
        assert r.json()["context"]["run_ceiling"] == CAL[0].replace("-", "")
        # 反面：S1..S7 的工厂返回 None，不该多出上界
        h7 = {**H, "x-genebench-task-id": "s3-cor-01"}
        ok = client.get("/bars", headers=h7,
                        params={"code": SYM, "as_of": "2026-07-31",
                                "start_date": CAL[0], "end_date": CAL[0]})
        assert ok.status_code != 403, ok.text
    finally:
        SIM.register_session_factory(None)
        SIM.reset_sessions()
