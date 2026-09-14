# -*- coding: utf-8 -*-
"""`gateway/sim_factory.py` 的判据测试。

第一条是这个文件存在的理由：**生产路径上没有人注册过会话工厂**（N-87），
于是真网关上 S8 四道题一律 404，而 `ops/test_sim_endpoints.py` 全绿 ——
因为它自己注册工厂。机制齐备、接线缺一根、所有测试都在接线的另一侧（F7）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import genebench_config as cfg                                        # noqa: E402
from gateway import sim_factory as sf                                 # noqa: E402
from gateway.routers import sim as SIM                                # noqa: E402
from gateway.sim_engine import SimEngine                              # noqa: E402

#: 本文件测的是冒烟集那一份（`set_id` 2026-09-11 起必填，N-578）。
SET = "v1.0-smoke"

RELEASED = ("s8-cor-01", "s8-eco-01", "s8-ops-01", "s8-rob-01")


@pytest.fixture(autouse=True)
def _clean():
    SIM.reset_sessions()
    sf.reset_ledger()
    yield
    SIM.reset_sessions()
    sf.reset_ledger()


# ------------------------------------------------------------------ 接线
def test_production_app_registers_a_factory():
    """N-87。没有这条，`create_app()` 少一行谁都发现不了。"""
    SIM.register_session_factory(None)
    from gateway.app import create_app
    create_app()
    assert SIM._FACTORY is not None, "create_app() 没有注册会话工厂 —— S8 在真网关上全 404"


def test_factory_returns_none_for_non_s8():
    """返回空引擎会给 S1..S7 凭空造出一个 `as_of` 上界。"""
    assert sf.build_engine("oracle", "s3-cor-01", set_id=SET) is None


# ------------------------------------------------------------------ 只读 X 面
@pytest.mark.parametrize("task_id", RELEASED)
def test_face_carries_only_the_four_x_side_keys(task_id):
    face = sf.read_task_face(task_id, SET)
    assert sorted(face) == ["declared", "stage", "universe", "window"]


@pytest.mark.parametrize("task_id", RELEASED)
def test_face_never_carries_the_canary(task_id):
    """`task.yaml` 里有 gold token 与 canary 段。工厂返回整份就等于把答案面递给了调用方。"""
    assert "GBC-" not in yaml.safe_dump(sf.read_task_face(task_id, SET), allow_unicode=True)


def test_unknown_declared_field_raises(tmp_path, monkeypatch):
    """契约加了字段而工厂没跟上 → 静默忽略的表现是「声明了但环境没照做」，没有一处会报。"""
    d = tmp_path / "s8-x-01"
    d.mkdir()
    doc = yaml.safe_load((sf.task_dir("s8-cor-01", SET) / "task.yaml").read_text(encoding="utf-8"))
    doc["declared"]["brand_new_knob"] = 1
    (d / "task.yaml").write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(sf, "task_dir", lambda tid, sid: d)
    with pytest.raises(ValueError, match="brand_new_knob"):
        sf.read_task_face("s8-x-01", SET)


def test_unsupported_matching_frequency_raises(tmp_path, monkeypatch):
    d = tmp_path / "s8-y-01"
    d.mkdir()
    doc = yaml.safe_load((sf.task_dir("s8-cor-01", SET) / "task.yaml").read_text(encoding="utf-8"))
    doc["declared"]["matching_frequency"] = "weekly"
    (d / "task.yaml").write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(sf, "task_dir", lambda tid, sid: d)
    with pytest.raises(ValueError, match="matching_frequency"):
        sf.build_engine("oracle", "s8-y-01", set_id=SET)


# ------------------------------------------------------------------ 可交易性映射
def _frame(rows):
    return pd.DataFrame(rows, columns=["date", "code", "status", "close"])


def _patch_lake(monkeypatch, rows, opens=True):
    monkeypatch.setattr(sf, "_tradability_year", lambda y: _frame(rows))
    monkeypatch.setattr(sf.backends, "read_table",
                        lambda *a, **k: pd.DataFrame(
                            [{"ts_code": r[1], "trade_date": r[0].replace("-", ""), "open": 9.0}
                             for r in rows] if opens else []))


DAYS = ["2026-07-01"]
SYMS = ["600000.SH"]


def test_limit_up_is_not_an_untradable_status(monkeypatch):
    """湖里 status 有 `limit_up`，引擎只认 `{trade,suspend,no_data}` ——
    原样传进去走 fail-closed，**买卖两边一起拒**，而契约是涨停只挡买。"""
    _patch_lake(monkeypatch, [("2026-07-01", "600000.SH", "limit_up", 10.0)])
    m = sf.market_frames(SYMS, DAYS)
    assert m["tradable"][("2026-07-01", "600000.SH")] == "trade"
    assert ("2026-07-01", "600000.SH") in m["limit_up"]
    assert ("2026-07-01", "600000.SH") not in m["limit_down"]


def test_limit_down_only_marks_the_down_set(monkeypatch):
    _patch_lake(monkeypatch, [("2026-07-01", "600000.SH", "limit_down", 10.0)])
    m = sf.market_frames(SYMS, DAYS)
    assert m["tradable"][("2026-07-01", "600000.SH")] == "trade"
    assert ("2026-07-01", "600000.SH") in m["limit_down"]


def test_suspend_stays_untradable(monkeypatch):
    _patch_lake(monkeypatch, [("2026-07-01", "600000.SH", "suspend", None)])
    m = sf.market_frames(SYMS, DAYS)
    assert m["tradable"][("2026-07-01", "600000.SH")] == "suspend"
    assert ("2026-07-01", "600000.SH") not in m["closes"]


def test_unregistered_status_raises_instead_of_failing_closed_silently(monkeypatch):
    """漏登记一个取值 → 引擎把它当成两边都拒，而 gold 照样出数、指标全错、没有一处报错。"""
    _patch_lake(monkeypatch, [("2026-07-01", "600000.SH", "halted_forever", 10.0)])
    with pytest.raises(RuntimeError, match="没登记的 status"):
        sf.market_frames(SYMS, DAYS)


def test_empty_market_frame_raises(monkeypatch):
    _patch_lake(monkeypatch, [("2026-07-01", "000002.SZ", "trade", 10.0)])
    with pytest.raises(RuntimeError, match="一行都没有"):
        sf.market_frames(SYMS, DAYS)


def test_missing_opens_raises(monkeypatch):
    """`slippage_reference_price=open` 的题会静默拿不到基准价。"""
    _patch_lake(monkeypatch, [("2026-07-01", "600000.SH", "trade", 10.0)], opens=False)
    with pytest.raises(RuntimeError, match="open"):
        sf.market_frames(SYMS, DAYS)


# ------------------------------------------------------------------ 真数据装配
@pytest.mark.parametrize("task_id", RELEASED)
def test_released_task_builds_an_engine(task_id):
    e = sf.build_engine("oracle", task_id, set_id=SET)
    assert isinstance(e, SimEngine) and e.calendar
    assert e.calendar[0] == sf.read_task_face(task_id, SET)["window"]["start"]
    assert e.closes, "没有收盘价的模拟盘撮合不出任何东西"


@pytest.mark.parametrize("task_id", RELEASED)
def test_declared_permissions_reach_the_engine(task_id):
    d = sf.read_task_face(task_id, SET)["declared"]
    e = sf.build_engine("oracle", task_id, set_id=SET)
    assert e.permitted_operations == tuple(d["permitted_operations"])
    assert e.visible_state_fields == tuple(d["visible_state_fields"])
    assert e.slippage_base == d["slippage_reference_price"]


@pytest.mark.parametrize("task_id", RELEASED)
def test_visible_state_fields_exist_in_the_engine(task_id):
    """题面声明的可见字段必须是环境真有的。**`s8-rob-01` 今天不满足**（N-86）：
    题面写 `open_orders`，契约与引擎叫 `pending_orders`，
    于是那道题的每一次 `/sim/state` 都是 422 —— agent 照题面做也一样。"""
    if task_id == "s8-rob-01":
        pytest.xfail("N-86：题面 open_orders vs 引擎 pending_orders，待裁定后改题面")
    e = sf.build_engine("oracle", task_id, set_id=SET)
    keys = set(e.state(_skip_gate=True))
    assert set(e.visible_state_fields) <= keys, sorted(set(e.visible_state_fields) - keys)


# ------------------------------------------------------------------ 会话键 = (run_id, task_id)（N-88）
def test_a_forged_config_id_lands_on_the_same_session():
    """裁定 N-88：会话键是 `(run_id, task_id)` —— **换 config_id 换不出新账户**。

    这是裁定要求的那条判据（「伪造 config_id 打 /sim/state 落到的仍是本 run 会话」）。
    走的是真 `create_app()`，不是直接调工厂 —— 要测的正是**路由那一层**用什么当键。
    """
    from fastapi.testclient import TestClient
    from gateway.app import create_app
    c = TestClient(create_app(), raise_server_exceptions=False)
    base = {"x-genebench-task-id": "s8-cor-01", "x-gb-run-id": "s8-cor-01.strict.cfg-a.r01"}
    real = {**base, "x-genebench-config-id": "cfg-a"}
    forged = {**base, "x-genebench-config-id": "cfg-FORGED"}

    assert c.post("/sim/order", headers=real, json={
        "symbol": "600000.SH", "side": "buy", "qty": 100,
        "client_order_id": "n88-1", "reference_close": 10.0}).status_code == 200
    st = c.get("/sim/state", headers=forged)
    assert st.status_code == 200, st.text
    # 同一个 run 的会话：现金已经被那笔买单冻掉，**不是**复位后的 1,000,000。
    assert st.json()["cash"] < 1_000_000.0, st.json()
    assert len(sf.creation_ledger("s8-cor-01")) == 1, sf.creation_ledger("s8-cor-01")


def test_a_different_run_id_does_get_its_own_session():
    """反面：换 `run_id` 确实是另一次运行，就该是另一个会话 —— 否则这条键是恒等的。"""
    from fastapi.testclient import TestClient
    from gateway.app import create_app
    c = TestClient(create_app(), raise_server_exceptions=False)
    h = {"x-genebench-task-id": "s8-cor-01", "x-genebench-config-id": "cfg-a"}
    c.get("/sim/state", headers={**h, "x-gb-run-id": "run-1"})
    c.get("/sim/state", headers={**h, "x-gb-run-id": "run-2"})
    assert [r["run_id"] for r in sf.creation_ledger("s8-cor-01")] == ["run-1", "run-2"]


def test_missing_run_id_is_refused_not_defaulted():
    """fail-closed：缺 `x-gb-run-id` 就退回按 config_id 建会话的话，
    这条裁定等于没落地，而且**没有一处会报**。"""
    from fastapi.testclient import TestClient
    from gateway.app import create_app
    c = TestClient(create_app(), raise_server_exceptions=False)
    r = c.get("/sim/state", headers={"x-genebench-task-id": "s8-cor-01",
                                     "x-genebench-config-id": "cfg-a"})
    assert r.status_code == 422, r.text
    assert "x-gb-run-id" in r.text


def test_the_oracle_client_sends_a_run_id():
    """数据面的 oracle 不经边车、自己填头。`/sim/*` 对缺头是 fail-closed 的，
    客户端不填就是整阶段 422。"""
    from reference.gateway_client import Client
    h = Client("http://x", task_id="s8-cor-01", as_of="2026-07-31")._headers()
    assert h["x-gb-run-id"]
