# -*- coding: utf-8 -*-
"""`reference/gateway_client.py` 的判据测试。

这个文件存在的理由很具体：2026-09-05 那次 40 题跑批，S1/S2/S3/S5 的取数代码
在**同一批端点形状**上各错各的（`rows` 当成数据、`start` 当成 `start_date`、
`name=` 当成 `universe=`、`/adj` 的列名当成 `/bars` 的列名、请求不带身份头），
每一处都只有真跑才暴露。客户端把这些形状收成一处之后，
**它们必须被测住** —— 否则下次改客户端时会一处一处漂回去。

不打网络：`urlopen` 被替换成按 URL 返回固定回包的桩。
"""
from __future__ import annotations

import io
import json
import sys
import urllib.error
import urllib.parse
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reference import gateway_client as gc                                  # noqa: E402


class _Resp(io.BytesIO):
    def __init__(self, body: dict, ts: str | None = "2026-09-05T00:00:00Z", status: int = 200):
        super().__init__(json.dumps(body).encode())
        self.status = status
        self.headers = {gc.TS_HEADER: ts} if ts else {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def _stub(monkeypatch, handler):
    """`handler(path, params) -> dict | (dict, status)`。记录每次被调用的 URL 与请求头。"""
    calls: list[dict] = []

    def fake(req, timeout=None):
        u = urllib.parse.urlparse(req.full_url)
        params = urllib.parse.parse_qs(u.query, keep_blank_values=True)
        calls.append({"path": u.path, "params": params, "headers": dict(req.headers)})
        r = handler(u.path, params)
        body, status = r if isinstance(r, tuple) else (r, 200)
        if status != 200:
            raise urllib.error.HTTPError(req.full_url, status, "boom",
                                         {gc.TS_HEADER: "ts-err"}, io.BytesIO(json.dumps(body).encode()))
        return _Resp(body)

    monkeypatch.setattr(gc.urllib.request, "urlopen", fake)
    return calls


def _client() -> gc.Client:
    return gc.Client("http://gw.invalid", task_id="t-1", as_of="2026-07-31")


# ------------------------------------------------------------------ 身份与 as_of
def test_every_request_carries_identity_headers(monkeypatch):
    """身份头缺失 = 网关日志按 (task_id, config_id) 切出 0 条 —— 表现成「一次都没请求过」。"""
    calls = _stub(monkeypatch, lambda p, q: {"rows": 0, "data": []})
    _client().get_json("/bars", code=["600000.SH"])
    h = {k.lower(): v for k, v in calls[0]["headers"].items()}
    assert h["x-genebench-task-id"] == "t-1"
    assert h["x-genebench-config-id"] == "oracle"


def test_every_request_carries_as_of(monkeypatch):
    calls = _stub(monkeypatch, lambda p, q: {"rows": 0, "data": []})
    _client().get_json("/calendar", start_date="2026-01-01")
    assert calls[0]["params"]["as_of"] == ["2026-07-31"]


def test_for_context_takes_gateway_from_context_only():
    """D-32：网关地址来自环境（Context），task_id/as_of 来自 task.yaml —— 不许反过来。"""
    class Ctx:
        gateway, task_id, as_of, config_id = "http://x", "s7-cor-01", "2026-07-31", "oracle"
    c = gc.Client.for_context(Ctx())
    assert (c.base_url, c.task_id, c.as_of) == ("http://x", "s7-cor-01", "2026-07-31")


# ------------------------------------------------------------------ 逐个端点形状
def test_rows_is_a_count_not_the_data(monkeypatch):
    """`pd.DataFrame(r.json()["rows"])` 在 2026-09-05 真跑时炸了三处。"""
    _stub(monkeypatch, lambda p, q: {"rows": 2, "data": [{"code": "600000.SH", "date": "2026-07-31",
                                                          "status": "trade", "close": 1.0},
                                                         {"code": "600004.SH", "date": "2026-07-31",
                                                          "status": "trade", "close": 2.0}]})
    df = _client().frame("/bars", code=["600000.SH"])
    assert len(df) == 2 and "close" in df.columns


def test_universe_members_are_flattened_to_code_column(monkeypatch):
    """`/universe` 不给 `data`，给 `{size, members}` —— 按通用路径读会得到空表。"""
    _stub(monkeypatch, lambda p, q: {"size": 2, "rows": 2, "members": ["600000.SH", "000001.SZ"]})
    assert sorted(_client().members("csi300", "2026-07-31")) == ["000001.SZ", "600000.SH"]


def test_calendar_column_is_cal_date_and_is_renamed(monkeypatch):
    _stub(monkeypatch, lambda p, q: {"rows": 2, "data": [
        {"cal_date": "20260730", "is_open": True}, {"cal_date": "20260731", "is_open": False}]})
    assert _client().trading_days("2026-07-01", "2026-07-31") == ["2026-07-30"]


def test_adj_columns_ts_code_trade_date_are_renamed(monkeypatch):
    """`/adj` 的列名与 `/bars` 不同（`ts_code`/`trade_date`）。不归一就 merge 出全 NaN。"""
    _stub(monkeypatch, lambda p, q: {"rows": 1, "data": [
        {"ts_code": "600000.SH", "trade_date": "20260731", "adj_factor": 17.3774}]})
    df = _client().adj(["600000.SH"], "2026-07-31", "2026-07-31")
    assert list(df.columns) == ["code", "date", "adj_factor"]


def test_bars_and_adj_date_formats_are_normalised_to_the_same_shape(monkeypatch):
    """`/bars` 给 `YYYY-MM-DD`、`/adj` 给 `YYYYMMDD` —— 这是本仓最容易静默出错的一处。"""
    def h(path, q):
        if path == "/bars":
            return {"rows": 1, "data": [{"code": "600000.SH", "date": "2026-07-31",
                                         "status": "trade", "close": 1.0}]}
        return {"rows": 1, "data": [{"ts_code": "600000.SH", "trade_date": "20260731",
                                     "adj_factor": 2.0}]}
    _stub(monkeypatch, h)
    c = _client()
    b = c.bars(["600000.SH"], "2026-07-31", "2026-07-31", ["close"])
    a = c.adj(["600000.SH"], "2026-07-31", "2026-07-31")
    assert b.date.tolist() == a.date.tolist() == ["2026-07-31"]
    assert len(b.merge(a, on=["code", "date"])) == 1          # merge 得出行 = 归一成功


def test_tradability_sends_repeated_code_params_and_a_single_date(monkeypatch):
    """实测签名：`code` 重复参数（不是逗号串），`date` 单日（不接区间）。"""
    calls = _stub(monkeypatch, lambda p, q: {"rows": 1, "data": [
        {"code": "600000.SH", "date": "2026-07-31", "status": "trade"}]})
    _client().tradability(["600000.SH", "000001.SZ"], ["2026-07-30", "2026-07-31"])
    assert len(calls) == 2                                    # 逐日
    assert calls[0]["params"]["code"] == ["600000.SH", "000001.SZ"]
    assert calls[0]["params"]["date"] == ["2026-07-30"]
    assert "start_date" not in calls[0]["params"]


def test_bars_requires_explicit_fields(monkeypatch):
    """缺省 `fields` = 读全表，会被 `actual_reads` 反推成超读。"""
    calls = _stub(monkeypatch, lambda p, q: {"rows": 1, "data": [
        {"code": "600000.SH", "date": "2026-07-31", "status": "trade", "close": 1.0}]})
    _client().bars(["600000.SH"], "2026-07-31", "2026-07-31", ["close", "volume"])
    assert calls[0]["params"]["fields"] == ["close,volume"]


# ------------------------------------------------------------------ 分批
def test_chunking_keeps_each_request_under_max_rows(monkeypatch):
    """一次超过 `MAX_ROWS` 行 → 网关 422，而 422 会被记成 denied，排查方向完全错。"""
    calls = _stub(monkeypatch, lambda p, q: {"rows": 1, "data": [
        {"code": q["code"][0], "date": "2019-01-02", "status": "trade", "close": 1.0}]})
    codes = [f"{i:06d}.SZ" for i in range(600)]
    _client().bars(codes, "2019-01-02", "2026-07-03", ["close"])
    span = gc.Client._session_span("2019-01-02", "2026-07-03")
    assert all(len(c["params"]["code"]) * span <= gc.MAX_ROWS for c in calls)
    assert sum(len(c["params"]["code"]) for c in calls) == 600      # 一票不漏


def test_chunk_size_follows_the_window_not_a_hardcoded_number(monkeypatch):
    """窗口短 → 每批可以放更多票。写死批大小的话这条会红。"""
    calls = _stub(monkeypatch, lambda p, q: {"rows": 1, "data": [
        {"code": q["code"][0], "date": "2026-07-31", "status": "trade", "close": 1.0}]})
    codes = [f"{i:06d}.SZ" for i in range(600)]
    _client().bars(codes, "2026-07-30", "2026-07-31", ["close"])
    assert len(calls) == 1


# ------------------------------------------------------------------ 台账
def test_ledger_records_denied_requests_too(monkeypatch):
    """被拒的请求不记台账，`payload.fetches` 与网关日志就对不上 —— 而对不上没人报。"""
    _stub(monkeypatch, lambda p, q: ({"detail": "beyond freeze line"}, 403))
    c = _client()
    body, ts, code = c.get_json("/bars", code=["600000.SH"])
    assert code == 403 and len(c.ledger) == 1
    assert c.ledger[0]["status"] == "denied" and c.ledger[0]["rows"] is None


def test_ledger_distinguishes_empty_from_ok(monkeypatch):
    _stub(monkeypatch, lambda p, q: {"rows": 0, "data": []})
    c = _client()
    c.get_json("/bars", code=["600000.SH"])
    assert c.ledger[0]["status"] == "empty"


def test_fetched_at_comes_from_the_gateway_echo_header(monkeypatch):
    """不用本地时钟，也不去读 access_log —— 后者会让被核值与核它的基准同源。"""
    _stub(monkeypatch, lambda p, q: {"rows": 0, "data": []})
    c = _client()
    c.get_json("/bars", code=["600000.SH"])
    assert c.ledger[0]["fetched_at"] == "2026-09-05T00:00:00Z"


def test_rate_limited_is_its_own_status(monkeypatch):
    _stub(monkeypatch, lambda p, q: ({"detail": "slow down"}, 429))
    c = _client()
    c.get_json("/bars", code=["600000.SH"])
    assert c.ledger[0]["status"] == "rate_limited"


# ------------------------------------------------------------------ 空回包不许静默通过
@pytest.mark.parametrize("call", [
    lambda c: c.members("csi300", "2026-07-31"),
    lambda c: c.bars(["600000.SH"], "2026-07-01", "2026-07-31", ["close"]),
    lambda c: c.adj(["600000.SH"], "2026-07-01", "2026-07-31"),
])
def test_empty_response_raises_instead_of_returning_an_empty_frame(monkeypatch, call):
    """取不到数就往下算 = 面板空、指标算出来是 NaN 或 0，而没有一处报错。"""
    _stub(monkeypatch, lambda p, q: {"rows": 0, "data": [], "members": []})
    with pytest.raises(gc.GatewayError):
        call(_client())


def test_calendar_without_is_open_raises(monkeypatch):
    _stub(monkeypatch, lambda p, q: {"rows": 1, "data": [{"cal_date": "20260731"}]})
    with pytest.raises(gc.GatewayError):
        _client().trading_days("2026-07-01", "2026-07-31")


# ------------------------------------------------------------------ 代码格式
def test_code_format_roundtrip():
    assert gc.to_panel_code("600000.SH") == "SH600000"
    assert gc.to_gateway_code("SH600000") == "600000.SH"
    assert gc.to_gateway_code(gc.to_panel_code("000001.SZ")) == "000001.SZ"
