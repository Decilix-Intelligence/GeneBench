# -*- coding: utf-8 -*-
"""`/bars` 的 `fields` 参数（卡 2.3-c 的前置）：日志要有字段粒度，未知字段不得静默忽略。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import genebench_config as cfg                      # noqa: E402
from fastapi.testclient import TestClient           # noqa: E402
from gateway import access_log                      # noqa: E402
from gateway.app import app                         # noqa: E402
from reference.artifact_schema import actual_reads  # noqa: E402

Q = {"as_of": "2026-07-31", "code": "600519.SH", "start_date": "2026-07-01", "end_date": "2026-07-10"}
H = {"x-genebench-config-id": "cfg-t", "x-genebench-task-id": "task-fields"}


@pytest.fixture(scope="module")
def client() -> TestClient:
    cfg.harden_umask()
    return TestClient(app)


@pytest.fixture(scope="module")
def logfile(tmp_path_factory) -> Path:
    target = tmp_path_factory.mktemp("gwlog") / "access.jsonl"
    original = access_log.ACCESS_LOG
    access_log.ACCESS_LOG = target
    yield target
    access_log.ACCESS_LOG = original


def test_fields_subset_returns_only_requested_plus_keys(client, logfile):
    r = client.get("/bars", params={**Q, "fields": "close"}, headers=H)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["rows"] > 0
    assert d["fields"] == ["close"]
    cols = set(d["data"][0])
    assert cols == {"code", "date", "status", "close"}, cols


def test_star_and_omitted_return_everything(client, logfile):
    a = client.get("/bars", params=Q, headers=H).json()
    b = client.get("/bars", params={**Q, "fields": "*"}, headers=H).json()
    assert set(a["data"][0]) == set(b["data"][0])
    assert "close" in a["data"][0]


def test_validator_bars_fields_equals_what_gateway_actually_serves(client, logfile):
    """漂移断言：校验器的 BARS_FIELDS 必须与 `/bars` **实际返回**的列逐字相等。

    这张表若多写了 `open`（它不在 tradability 视图里），`actual_reads("*")` 会反推出
    从未发生的读取 —— 校验器自己就成了 D-06 的一个实例。
    """
    from reference.artifact_schema import BARS_FIELDS, BARS_KEY_COLUMNS
    served = set(client.get("/bars", params=Q, headers=H).json()["data"][0])
    assert served - BARS_KEY_COLUMNS == BARS_FIELDS, {
        "网关多出": sorted(served - BARS_KEY_COLUMNS - BARS_FIELDS),
        "表里多写": sorted(BARS_FIELDS - served)}


def test_bars_serves_open_amount_vwap_since_n33():
    """N-33 状态锁的**翻转记录**（证明锁不是摆设）：

    * 2026-09-01：`/bars` 不服务 open/amount/vwap，本测试的前身
      `test_bars_does_not_serve_open_amount_vwap_yet` 断言它们**不在** BARS_FIELDS —— 当时绿；
    * 2026-09-02 裁定网关加列；加列后前身测试**红**（锁起作用），随即改成本条：三列**必须在**。
    两次状态都在 git 历史里（提交 54aa96a 前后）。
    """
    from reference.artifact_schema import BARS_FIELDS
    assert {"open", "amount", "vwap"} <= BARS_FIELDS
    assert "pre_close" not in BARS_FIELDS, "pre_close 不在冻结 provider 的字段集里，不该加"


def test_bars_vwap_matches_card_21a_convention(client, logfile):
    """vwap = amount / volume（卡 2.1a 实证口径），volume=0 → null；且 low ≤ vwap ≤ high 占比 ≥ 99%。"""
    r = client.get("/bars", params={**Q, "fields": "open,high,low,close,volume,amount,vwap"}, headers=H)
    assert r.status_code == 200, r.text
    rows = r.json()["data"]
    assert rows
    in_band = total = 0
    for x in rows:
        if x["volume"] in (None, 0):
            assert x["vwap"] is None, x
            continue
        assert x["vwap"] is not None and x["amount"] is not None, x
        assert abs(x["vwap"] - x["amount"] / x["volume"]) < 1e-9 * max(1.0, abs(x["vwap"])), x
        total += 1
        in_band += (x["low"] <= x["vwap"] <= x["high"])
    assert total > 0
    assert in_band / total >= 0.99, f"in-band {in_band}/{total}"


def test_bars_served_set_is_explicit_no_silent_gap(client, logfile):
    """D-06 第 10 例：候选列写着、实际不服务的静默差不许再出现 —— 响应列必须**恰好**等于声明的服务集。"""
    from gateway.routers.market import BARS_SERVED_COLUMNS, KEY_COLUMNS
    served = set(client.get("/bars", params=Q, headers=H).json()["data"][0])
    assert served == set(BARS_SERVED_COLUMNS) | set(KEY_COLUMNS), {
        "响应多出": sorted(served - set(BARS_SERVED_COLUMNS) - set(KEY_COLUMNS)),
        "声明了没服务": sorted(set(BARS_SERVED_COLUMNS) - served)}


def test_unknown_field_is_422_not_silently_ignored(client, logfile):
    """拼错的字段名若被悄悄跳过，调用方拿到的仍是「看起来成功」的结果（D-06）。"""
    r = client.get("/bars", params={**Q, "fields": "close,cloes"}, headers=H)
    assert r.status_code == 422, r.text
    assert "cloes" in r.text


def test_repeated_fields_param_is_ambiguous_and_refused(client, logfile):
    r = client.get("/bars?as_of=2026-07-31&code=600519.SH&start_date=2026-07-01"
                   "&end_date=2026-07-10&fields=open&fields=close", headers=H)
    assert r.status_code == 422


def test_fields_lands_in_access_log_and_reconstructs(client, logfile):
    """探针的地基：日志里的 `fields` 能被 actual_reads() 反推出字段集。"""
    client.get("/bars", params={**Q, "fields": "close"}, headers={**H, "x-genebench-task-id": "task-rr"})
    entries = [e for e in access_log.read_all(logfile) if e.get("task_id") == "task-rr"]
    assert entries and entries[-1]["params"].get("fields") == "close"
    assert actual_reads(entries) == {"close"}


def test_capabilities_file_matches_gateway():
    """卡 3.1 状态锁的输入 `ops/capabilities.json` 不许与网关实际行为脱节（D-06：配置态与运行态要对得上）。"""
    import json
    from reference.artifact_schema import BARS_FIELDS
    caps = json.loads((_REPO / "ops" / "capabilities.json").read_text(encoding="utf-8"))
    served = {"open", "amount", "vwap"} <= BARS_FIELDS
    assert caps["n33_bars_open_amount_vwap"] is served, "能力位与 BARS_FIELDS 不一致：改一边必须改另一边"
    # N-96 翻转记录（2026-09-05）：卡 4.4 §6 五步的 1–3 核过 —— ① 五端点 + as_of/sim_date 耦合 +
    # OPERATION_NOT_PERMITTED + 会话工厂（N-87）+ 会话键 (run_id, task_id)（N-88）；
    # ② SIM-A..M 在 ops/test_sim_engine.py / test_sim_endpoints.py 各有具名用例，SIM-N 由
    # ops/run_f02_sim_n.sh 从 f02 任务容器真打一次（/sim/state 200，f01 access_log 六条全是 runner 真值）；
    # ③ 越界（as_of 晚于 sim_date → 403）与越权（OPERATION_NOT_PERMITTED → 403）用例在 test_sim_endpoints。
    # 第 4 步就是这条断言翻转 + ops/capabilities.json 同步；第 5 步（S8 五行 draft → packed）改出集清单，
    # 按 freeze_v10 的判据是致命漂移，须人工签字，不在这里做。
    assert caps["s8_state_endpoint"] is True, "S8 状态端点已就位（N-96 第 4 步）；要撤回先改这条测试并留记录"


# =============================================================== B8：ts 回显（卡 2.6）
def test_every_response_echoes_the_access_log_ts(tmp_path, monkeypatch):
    """**响应头里的 ts 必须与 `access_log` 里那条逐字相等**（D-21 对齐断言）。

    为什么要回显：oracle 的 `payload.fetches[i].fetched_at` 要与日志里那条的 ts 比对。
    如果让 oracle 自己去读日志填这个值，**被核的值与核它的基准就同源了** ——
    交叉核成了恒真。回显之后，值由网关在**响应时**给出，
    核对在**结算时**从日志另取一次，两条路径才真正独立。
    """
    import json as _json

    from fastapi.testclient import TestClient

    from gateway import access_log as AL
    from gateway.app import TS_HEADER, create_app

    log = tmp_path / "gw.jsonl"
    monkeypatch.setattr(AL, "ACCESS_LOG", log)
    monkeypatch.setattr(cfg, "LOGS", tmp_path, raising=False)
    c = TestClient(create_app(), raise_server_exceptions=False)
    h = {"x-genebench-config-id": "oracle", "x-genebench-task-id": "s1-cor-01"}

    r = c.get("/universe", headers=h,
              params={"as_of": "2026-07-31", "universe": "csi300", "date": "2026-07-31"})
    assert TS_HEADER in r.headers, "allow 路径没有回显 ts"
    rows = [_json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["ts"] == r.headers[TS_HEADER], \
        f"回显的 ts 与日志里那条不一致：{r.headers[TS_HEADER]} vs {rows[-1]['ts']}"


def test_denied_responses_echo_the_ts_too(tmp_path, monkeypatch):
    """**被拒的那次取数照样要入台账**（S1 契约），所以它也需要一个可核的 fetched_at。"""
    import json as _json

    from fastapi.testclient import TestClient

    from gateway import access_log as AL
    from gateway.app import TS_HEADER, create_app

    log = tmp_path / "gw.jsonl"
    monkeypatch.setattr(AL, "ACCESS_LOG", log)
    monkeypatch.setattr(cfg, "LOGS", tmp_path, raising=False)
    c = TestClient(create_app(), raise_server_exceptions=False)
    h = {"x-genebench-config-id": "oracle", "x-genebench-task-id": "s1-cor-01"}
    r = c.get("/bars", headers=h,
              params={"as_of": "2027-01-01", "code": "600000.SH",
                      "start_date": "2026-07-01", "end_date": "2026-07-02", "fields": "close"})
    assert r.status_code >= 400, r.text
    assert TS_HEADER in r.headers, "deny 路径没有回显 ts"
    rows = [_json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["ts"] == r.headers[TS_HEADER]


def test_duplicate_param_denial_echoes_the_ts(tmp_path, monkeypatch):
    import json as _json

    from fastapi.testclient import TestClient

    from gateway import access_log as AL
    from gateway.app import TS_HEADER, create_app

    log = tmp_path / "gw.jsonl"
    monkeypatch.setattr(AL, "ACCESS_LOG", log)
    monkeypatch.setattr(cfg, "LOGS", tmp_path, raising=False)
    c = TestClient(create_app(), raise_server_exceptions=False)
    r = c.get("/bars?as_of=2026-07-31&as_of=2026-07-30&code=600000.SH"
              "&start_date=2026-07-01&end_date=2026-07-02&fields=close",
              headers={"x-genebench-config-id": "oracle", "x-genebench-task-id": "t"})
    assert r.status_code == 422
    assert TS_HEADER in r.headers
    rows = [_json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["ts"] == r.headers[TS_HEADER]


@pytest.mark.parametrize("path,params", [
    ("/bars", {"as_of": "2026-07-31", "code": "600000.SH", "start_date": "2026-07-27",
               "end_date": "2026-07-31", "fields": "close"}),
    ("/adj", {"as_of": "2026-07-31", "code": "600000.SH", "start_date": "2026-07-27",
              "end_date": "2026-07-31"}),
    ("/universe", {"as_of": "2026-07-31", "universe": "csi300", "date": "2026-07-31"}),
])
def test_access_log_rows_equals_the_body_rows(tmp_path, monkeypatch, path, params):
    """**日志里的 `rows` 必须等于回包里的 `rows`**（卡 2.6 / B8 实测逼出来的）。

    修前：成功路径**根本不传 `rows`**，日志那一列恒为 `None`。
    而 `source_status` 探针判的是「artifact 自报的 status 与**日志推出来的 status** 一致」，
    `rows=None` 被推成 `empty`，于是

    * 老老实实报 `ok` 的 artifact **每一条 fetch 都被判违例**（S1 五题实测 601 条）；
    * 而一个把所有 fetch 都报成 `empty` 的 artifact **反而全过**。

    **这条探针是反的** —— 而且它有发出点、测试里也提到过族名。
    「有发出点」「测试里提到过」两样都不能说明一族探针是**朝着对的方向**在判。
    """
    import json as _json

    from fastapi.testclient import TestClient

    from gateway import access_log as AL
    from gateway.app import create_app

    log = tmp_path / "gw.jsonl"
    monkeypatch.setattr(AL, "ACCESS_LOG", log)
    monkeypatch.setattr(cfg, "LOGS", tmp_path, raising=False)
    c = TestClient(create_app(), raise_server_exceptions=False)
    r = c.get(path, headers={"x-genebench-config-id": "oracle",
                             "x-genebench-task-id": "s1-cor-01"}, params=params)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "rows" in body, f"{path} 的回包没有 rows —— 中间件就记不到行数"
    rows = [_json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["rows"] == body["rows"], \
        f"{path}：日志 rows={rows[-1]['rows']} ≠ 回包 rows={body['rows']}"
    assert rows[-1]["rows"] is not None


def test_source_status_now_agrees_for_an_honest_fetch(tmp_path, monkeypatch):
    """**判别力**：诚实上报 `ok` 的一条 fetch，交叉核必须判**一致**。

    这条是上一条的语义面 —— 只断言「日志有行数」还不够，
    要断言那个行数**推出来的 status** 与诚实自报的一致。
    """
    import json as _json

    from fastapi.testclient import TestClient

    from gateway import access_log as AL
    from gateway.app import TS_HEADER, create_app
    from reference.artifact_schema import _status_from_log

    log = tmp_path / "gw.jsonl"
    monkeypatch.setattr(AL, "ACCESS_LOG", log)
    monkeypatch.setattr(cfg, "LOGS", tmp_path, raising=False)
    c = TestClient(create_app(), raise_server_exceptions=False)
    r = c.get("/bars", headers={"x-genebench-config-id": "oracle",
                                "x-genebench-task-id": "s1-cor-01"},
              params={"as_of": "2026-07-31", "code": "600000.SH",
                      "start_date": "2026-07-27", "end_date": "2026-07-31", "fields": "close"})
    assert r.json()["rows"] > 0
    entry = [_json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()][-1]
    assert _status_from_log(entry) == "ok", \
        f"诚实的 ok 被日志推成 {_status_from_log(entry)!r} —— 探针方向是反的"
    assert entry["ts"] == r.headers[TS_HEADER]


def test_buffering_never_truncates_the_body(tmp_path, monkeypatch):
    """**中间件缓冲回包时，body 必须原样送达。**

    第一版在超过缓冲上限时 `break` 掉循环、又把**原**响应放行 ——
    那个响应的 `body_iterator` 已经被消费了一半，客户端收到空 body
    （实测 `/fundamentals` 返回 200 但 `r.json()` 直接 JSONDecodeError）。
    **读一半就放行**是这里唯一不能做的事。
    """
    from fastapi.testclient import TestClient

    from gateway import access_log as AL
    from gateway.app import create_app

    monkeypatch.setattr(AL, "ACCESS_LOG", tmp_path / "gw.jsonl")
    monkeypatch.setattr(cfg, "LOGS", tmp_path, raising=False)
    c = TestClient(create_app(), raise_server_exceptions=False)
    for path, params in (
        ("/fundamentals", {"as_of": "2026-07-31", "statement": "income_vip"}),
        ("/bars", {"as_of": "2026-07-31", "code": "600000.SH", "start_date": "2026-07-27",
                   "end_date": "2026-07-31", "fields": "close"}),
    ):
        r = c.get(path, headers={"x-genebench-config-id": "oracle",
                                 "x-genebench-task-id": "t"}, params=params)
        assert r.status_code == 200, (path, r.status_code)
        body = r.json()                     # 解析不了 = body 被截断
        assert isinstance(body, dict) and body
        assert int(r.headers["content-length"]) == len(r.content), \
            f"{path}：content-length 与实际字节数不一致"
