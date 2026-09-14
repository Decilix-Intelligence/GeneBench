# -*- coding: utf-8 -*-
"""卡 1.3 网关探针套件（G-01 … G-10）。

编号沿用 `ops/reports/gateway_probe_report.md` 表 A —— 那张表是在网关还不存在时
写下的"本应怎么断言"，这里是它的兑现。

**立场是证伪，不是背书。** 凡是"把实现里的常量再抄一遍然后和实现比"的自证式断言
一律不写（那正是卡 0.2 D1 与卡 1.2 D3 栽过的跟头）：
PIT 边界日、停牌样例、哨兵行都**从湖里现查**，不写死。
"""
from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import genebench_config as cfg  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from snapshots import lake  # noqa: E402

from gateway import access_log  # noqa: E402
from gateway.app import ALLOWED_ROUTES, app, registered_paths  # noqa: E402

FREEZE = cfg.FREEZE_DATE.replace("-", "")

#: 需要 as_of 的端点及其最小可用参数（不含 as_of）。
DATA_ENDPOINTS: dict[str, dict[str, str]] = {
    "/bars": {"code": "600519.SH", "start_date": "2026-07-01", "end_date": "2026-07-10"},
    "/adj": {"code": "600519.SH", "start_date": "2026-07-01", "end_date": "2026-07-10"},
    "/calendar": {"start_date": "2026-07-01", "end_date": "2026-07-10"},
    "/limits": {"code": "600519.SH", "start_date": "2026-07-01", "end_date": "2026-07-10"},
    "/universe": {"universe": "csi300", "date": "2026-07-31"},
    "/tradability": {"code": "600519.SH", "date": "2026-07-31"},
    "/fundamentals": {"statement": "income", "code": "600519.SH"},
}

HEADERS = {"x-genebench-config-id": "cfg-probe", "x-genebench-task-id": "task-probe"}


@pytest.fixture(scope="module")
def client() -> TestClient:
    cfg.harden_umask()
    return TestClient(app)


@pytest.fixture(scope="module")
def logfile(tmp_path_factory) -> Path:
    """把 access_log 重定向到临时文件，避免污染真日志、也便于精确断言。"""
    target = tmp_path_factory.mktemp("gwlog") / "access.jsonl"
    original = access_log.ACCESS_LOG
    access_log.ACCESS_LOG = target
    yield target
    access_log.ACCESS_LOG = original


def _log_since(logfile: Path, n: int) -> list[dict]:
    return access_log.read_all(logfile)[n:]


def _log_len(logfile: Path) -> int:
    return len(access_log.read_all(logfile))


# ======================================================================
# G-09 绑定地址（红线 4）—— 源码级 + 行为级双重
# ======================================================================


def test_g09_wildcard_bind_is_refused_at_source():
    for bad in ("0.0.0.0", "", "::", "*", "[::]", "0", "::0", "  0.0.0.0  "):
        with pytest.raises(Exception):
            cfg.assert_no_wildcard_bind(bad)
    assert cfg.assert_no_wildcard_bind(cfg.GATEWAY_HOST) == cfg.GATEWAY_HOST


def test_g09_run_module_binds_through_the_guard():
    """run.py 必须**经守门函数**取 host，不能直接把常量塞进 uvicorn。"""
    src = (cfg.REPO / "gateway" / "run.py").read_text(encoding="utf-8")
    assert "assert_no_wildcard_bind(cfg.GATEWAY_HOST)" in src
    assert "0.0.0.0" not in src


def test_g09_no_wildcard_bind_in_code():
    """`0.0.0.0` 不许出现在**代码**里（docstring/注释里讨论它是应该的）。

    第一版我用"这一行有没有 # 或引号"当启发式，结果被 app.py 模块 docstring
    里那句解释 tailscale 的话绊倒 —— 那是测试写糙了，不是代码有问题。
    改成 AST：只看真正的字符串**常量节点**，docstring 由 ast 天然区分不出来，
    所以再排除掉每个模块/函数的首个字符串表达式（那就是 docstring）。
    """
    import ast

    offenders: list[str] = []
    for py in sorted((cfg.REPO / "gateway").rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
                body = getattr(node, "body", [])
                if body and isinstance(body[0], ast.Expr) and isinstance(
                    body[0].value, ast.Constant
                ) and isinstance(body[0].value.value, str):
                    docstrings.add(id(body[0].value))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and "0.0.0.0" in node.value
                and id(node) not in docstrings
            ):
                offenders.append(f"{py.name}:{node.lineno}")
    # asof/errors 里没有；若将来有人在守门函数的黑名单里列它，也应显式豁免
    assert not offenders, f"代码里出现 0.0.0.0 字面量：{offenders}"


def test_g09_test_suite_leaves_no_listener():
    """**探针套件**跑完不许留监听 —— 常驻进程是运维事故的第一名。

    测的是**测试用端口**（18099），不是 18080：网关按 M6 形态常驻在 18080
    （裁定 2026-09-04，systemd --user 单元）。原先这条绑 `cfg.GATEWAY_PORT`，
    网关一起来它就永远红 —— 而一条恒红的测试下一个人会把它注释掉，
    连带把「套件不许留监听」这个真判据一起丢了。两件事要分开测：
    这条管套件自己，下一条管常驻网关是不是**按单元**起的。
    """
    from ops.test_env import GATEWAY_TEST_PORT
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind((cfg.GATEWAY_HOST, GATEWAY_TEST_PORT))
    finally:
        s.close()


def test_g09_production_listener_is_the_systemd_unit_not_a_stray_process():
    """18080 上**如果**有监听，它必须是 systemd 单元起的那个，不是谁手跑的残留。

    「端口上有东西」既可能是按裁定常驻的网关，也可能是某次调试忘了关的进程 ——
    两者在 `ss` 里长得一样。判据落在**是谁起的**上。
    """
    import shutil
    import subprocess
    if shutil.which("systemctl") is None:
        pytest.skip("没有 systemctl")
    probe = socket.socket()
    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        probe.bind((cfg.GATEWAY_HOST, cfg.GATEWAY_PORT))
        probe.close()
        return                                  # 端口空闲：没有常驻网关，无可检查
    except OSError:
        probe.close()
    r = subprocess.run(["systemctl", "--user", "is-active", "genebench-gateway.service"],
                       capture_output=True, text=True)
    assert r.stdout.strip() == "active", (
        f"{cfg.GATEWAY_HOST}:{cfg.GATEWAY_PORT} 上有监听，但 genebench-gateway.service "
        f"不是 active（{r.stdout.strip()!r}）—— 那是个来路不明的常驻进程")


# ======================================================================
# G-10 答案隔离 + 路由白名单（红线 5）
# ======================================================================


def test_g10_route_whitelist_is_not_vacuous():
    """护栏自检：必须真的收集到全部路由。

    踩过的坑：FastAPI 把 include_router 的路由包进 ``_IncludedRouter``
    （``path=None``），只看顶层就**只能看到 /healthz**，白名单校验空跑通过。
    """
    paths = registered_paths(app)
    assert paths == ALLOWED_ROUTES, f"路由与白名单不符：{sorted(paths ^ ALLOWED_ROUTES)}"
    assert len(paths) >= 8


@pytest.mark.parametrize(
    "path",
    [
        "/reference", "/scorer", "/gold", "/answers",
        "/reference/gold.parquet", "/scorer/config.json",
        "/../reference", "/%2e%2e/scorer", "/bars/../../reference",
    ],
)
def test_g10_answer_surface_is_unreachable(client, path):
    r = client.get(path, params={"as_of": "2026-07-31"})
    assert r.status_code in (403, 404, 405), f"{path} 返回了 {r.status_code}"


def test_g10_no_forbidden_token_in_any_route():
    for p in registered_paths(app):
        low = p.lower()
        for token in ("reference", "scorer", "gold", "answer"):
            assert token not in low, f"路由 {p} 含禁用字样 {token}"


# ======================================================================
# G-01 as_of 强制
# ======================================================================


@pytest.mark.parametrize("path", sorted(DATA_ENDPOINTS))
def test_g01_asof_is_required(client, path):
    r = client.get(path, params=DATA_ENDPOINTS[path])
    assert r.status_code == 422, r.text
    assert r.json()["reason"] == "asof_missing"


@pytest.mark.parametrize(
    "bad", ["2026/07/31", "31-07-2026", "2026-7-31", "20260731T00:00:00",
            "2026-07-31 00:00", "2026-02-30", "", "   ", "yesterday"],
)
def test_g01_malformed_asof_is_refused(client, bad):
    r = client.get("/calendar", params={"as_of": bad, "start_date": "2026-07-01",
                                        "end_date": "2026-07-10"})
    assert r.status_code == 422, f"as_of={bad!r} 竟然被接受：{r.text[:200]}"
    assert r.json()["reason"] in ("asof_malformed", "asof_missing")


def test_g01_asof_itself_is_clamped_to_freeze_line(client):
    """as_of 越过冻结线也是越界（红线 7），不是"看未来"那一档。"""
    r = client.get("/calendar", params={"as_of": "2026-09-01",
                                        "start_date": "2026-07-01",
                                        "end_date": "2026-07-10"})
    assert r.status_code == 403
    assert r.json()["reason"] == "asof_beyond_freeze_line"


# ======================================================================
# G-02 越界必 403 —— 逐条路径
# ======================================================================


@pytest.mark.parametrize(
    "path,params,reason",
    [
        ("/bars", {"code": "600519.SH", "start_date": "2026-07-01",
                   "end_date": "2026-08-15"}, "range_end_after_asof"),
        ("/adj", {"code": "600519.SH", "start_date": "2026-07-01",
                  "end_date": "2026-08-15"}, "range_end_after_asof"),
        ("/limits", {"code": "600519.SH", "start_date": "2026-07-01",
                     "end_date": "2026-08-15"}, "range_end_after_asof"),
        ("/calendar", {"start_date": "2026-07-01",
                       "end_date": "2026-12-31"}, "range_end_after_asof"),
        ("/bars", {"code": "600519.SH", "start_date": "2026-07-01"},
         "open_range_would_cross_asof"),
        ("/adj", {"code": "600519.SH", "start_date": "2026-07-01"},
         "open_range_would_cross_asof"),
        ("/universe", {"universe": "csi300", "date": "2026-07-31"},
         "universe_asof_after_asof"),
        ("/tradability", {"code": "600519.SH", "date": "2026-07-31"},
         "target_date_after_asof"),
    ],
)
def test_g02_out_of_bound_is_403(client, path, params, reason):
    """as_of 取 2026-06-30，各条越界路径都必须被拦。"""
    r = client.get(path, params={**params, "as_of": "2026-06-30"})
    assert r.status_code == 403, f"{path} {params} → {r.status_code}\n{r.text[:300]}"
    assert r.json()["reason"] == reason, r.json()


def test_g02_denied_body_carries_no_data(client):
    """403 的响应体里不许夹带任何越界数据。"""
    r = client.get("/adj", params={"as_of": "2026-06-30", "code": "600519.SH",
                                   "start_date": "2026-07-01", "end_date": "2026-07-31"})
    assert r.status_code == 403
    body = r.json()
    assert "data" not in body and "members" not in body


@pytest.mark.parametrize("variant", ["AS_OF", "As_Of"])
def test_g02_param_name_is_case_sensitive_not_a_bypass(client, variant):
    """大小写变体不能绕过 —— 它应该表现为"没给 as_of"，而不是被接受。"""
    r = client.get("/calendar", params={variant: "2026-07-31",
                                        "start_date": "2026-07-01",
                                        "end_date": "2026-07-10"})
    assert r.status_code == 422
    assert r.json()["reason"] == "asof_missing"


def test_g02_duplicate_asof_is_refused(client):
    """重复的 as_of 必须被拒，不能静默择一。

    **这条是探针实测抓出来的真漏洞**：修之前 FastAPI 取**最后一个**（宽的那个）
    并放行了 2026-06-30 之后的日历行 —— 调用方却完全可以声称自己给的是第一个。
    授权参数的歧义被静默解析，就是一次可否认的越权。
    """
    r = client.get("/calendar?as_of=2026-06-30&as_of=2026-07-31"
                   "&start_date=2026-07-01&end_date=2026-07-20")
    assert r.status_code == 422, f"重复 as_of 竟被接受：{r.status_code} {r.text[:200]}"
    assert r.json()["reason"] == "param_malformed"
    assert "data" not in r.json()


@pytest.mark.parametrize("key", ["start_date", "end_date", "universe", "statement", "mode"])
def test_g02_duplicate_scalar_params_are_refused(client, key):
    """同理，别的标量参数重复也不许择一。"""
    base = {"as_of": "2026-07-31", "start_date": "2026-07-01", "end_date": "2026-07-10"}
    qs = "&".join(f"{k}={v}" for k, v in base.items()) + f"&{key}=x&{key}=y"
    r = client.get(f"/calendar?{qs}")
    assert r.status_code == 422, f"{key} 重复被接受了"
    assert r.json()["reason"] == "param_malformed"


# ======================================================================
# G-03 越界必记录
# ======================================================================


def test_g03_denial_is_logged_with_full_request(client, logfile):
    before = _log_len(logfile)
    r = client.get("/adj", params={"as_of": "2026-06-30", "code": "600519.SH",
                                   "start_date": "2026-07-01", "end_date": "2026-07-31"},
                   headers=HEADERS)
    assert r.status_code == 403
    new = _log_since(logfile, before)
    assert new, "越界请求没有落日志 —— 卡 5.1 的前视结算会瞎掉"
    entry = new[-1]
    assert entry["decision"] == "deny"
    assert entry["reason"] == "range_end_after_asof"
    assert entry["status"] == 403
    assert entry["config_id"] == "cfg-probe"
    assert entry["task_id"] == "task-probe"
    assert entry["path"] == "/adj"
    # 请求全文可回放
    assert entry["params"]["end_date"] == "2026-07-31"
    assert entry["params"]["code"] == "600519.SH"
    assert entry["as_of"] == "2026-06-30"
    assert entry["freeze_line"] == cfg.FREEZE_DATE


def test_g03_allow_is_logged_too(client, logfile):
    before = _log_len(logfile)
    r = client.get("/calendar", params={"as_of": "2026-07-31",
                                        "start_date": "2026-07-01",
                                        "end_date": "2026-07-10"}, headers=HEADERS)
    assert r.status_code == 200
    entry = _log_since(logfile, before)[-1]
    assert entry["decision"] == "allow"
    assert entry["status"] == 200
    assert entry["backend"] in ("live", "snapshot")


def test_g03_log_lands_outside_the_repo():
    """日志必须落 $GENEBENCH_ROOT/logs，不能落 repo（红线 6）。"""
    original = cfg.LOGS / "gateway_access.jsonl"
    assert cfg.LOGS.is_relative_to(cfg.GENEBENCH_ROOT)
    assert not str(original).startswith(str(cfg.REPO))


# ======================================================================
# G-04 PIT 可见性翻转（边界日**从湖里现查**，不写死）
# ======================================================================


@pytest.fixture(scope="module")
def maotai_q1_boundary() -> tuple[str, str]:
    """现查 600519.SH 2026Q1 的 f_ann_date，返回 (前一日, 边界日)。"""
    lake.raise_open_file_limit()
    df = lake.query(
        "SELECT f_ann_date FROM income "
        "WHERE ts_code = ? AND end_date = ? AND f_ann_date IS NOT NULL "
        "ORDER BY f_ann_date LIMIT 1",
        ["600519.SH", "20260331"],
    )
    if not len(df):
        pytest.skip("湖里没有 600519.SH 2026Q1 的 income 行")
    d = str(df.iloc[0]["f_ann_date"])
    import datetime as dt

    prev = (dt.date(int(d[:4]), int(d[4:6]), int(d[6:])) - dt.timedelta(days=1))
    return prev.strftime("%Y%m%d"), d


def test_g04_pit_visibility_flips_on_f_ann_date(client, maotai_q1_boundary):
    before_day, on_day = maotai_q1_boundary
    r0 = client.get("/fundamentals", params={"as_of": before_day, "statement": "income",
                                             "code": "600519.SH", "end_date": "20260331"})
    r1 = client.get("/fundamentals", params={"as_of": on_day, "statement": "income",
                                             "code": "600519.SH", "end_date": "20260331"})
    assert r0.status_code == 200 and r1.status_code == 200
    assert r0.json()["rows"] == 0, f"{before_day} 就看见了 2026Q1 —— 前视泄漏"
    assert r1.json()["rows"] >= 1, f"{on_day} 反而看不见"


def test_g04_null_f_ann_date_is_dropped_not_coalesced(client):
    """N-15：f_ann_date 有大量 NULL，放行它们 = 全市场级前视泄漏。

    判别力来自**湖侧现算**：先数出 NULL 行有多少，再确认网关一行都没返回。
    """
    lake.raise_open_file_limit()
    nulls = lake.query(
        "SELECT count(*) AS n FROM income_vip WHERE f_ann_date IS NULL"
    ).iloc[0]["n"]
    assert int(nulls) > 0, "湖侧没有 NULL 了？那 N-15 的前提变了，回来改结论"
    src = (cfg.REPO / "gateway" / "routers" / "reference.py").read_text(encoding="utf-8")
    assert "IS NOT NULL" in src, "PIT 过滤必须显式排除 NULL"
    assert "coalesce" not in src.lower().replace("coalesce(f_ann_date, ann_date)", ""), (
        "出现 coalesce 兜底 —— 那是全市场级前视泄漏"
    )
    r = client.get("/fundamentals", params={"as_of": FREEZE, "statement": "income_vip"})
    assert r.status_code == 200
    assert all(row.get("f_ann_date") for row in r.json()["data"])


def test_g04_uses_f_ann_date_not_ann_date():
    src = (cfg.REPO / "gateway" / "routers" / "reference.py").read_text(encoding="utf-8")
    assert 'VISIBILITY_COL: str = "f_ann_date"' in src


# ======================================================================
# G-05 停牌日 /bars 带 status（样例从湖里现挖，且在冻结线内）
# ======================================================================


@pytest.fixture(scope="module")
def suspended_sample() -> tuple[str, str]:
    """冻结线内的一个停牌 (code, date)。"""
    lake.raise_open_file_limit()
    df = lake.query(
        "SELECT ts_code, trade_date FROM suspend_d "
        "WHERE suspend_type = 'S' AND trade_date <= ? "
        "ORDER BY trade_date DESC LIMIT 1",
        [FREEZE],
    )
    if not len(df):
        pytest.skip("冻结线内没挖到停牌样例")
    row = df.iloc[0]
    return str(row["ts_code"]), str(row["trade_date"])


def test_g05_suspended_day_has_a_row_with_status(client, suspended_sample):
    code, day = suspended_sample
    iso = f"{day[:4]}-{day[4:6]}-{day[6:]}"
    r = client.get("/bars", params={"as_of": FREEZE, "code": code,
                                    "start_date": iso, "end_date": iso})
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body["rows"] >= 1, "停牌日返回了空 —— 静默空正是卡 1.2 要消灭的坑"
    row = body["data"][0]
    assert row["status"] is not None
    assert row["status"] in cfg.TRADABILITY_STATUSES


# ======================================================================
# G-06 复权口径唯一
# ======================================================================


@pytest.mark.parametrize("mode", ["hfq", "qfq", "bfq", "HFQ", "qfq_close"])
def test_g06_three_price_modes_are_refused(client, mode):
    r = client.get("/adj", params={"as_of": FREEZE, "code": "600519.SH",
                                   "start_date": "2026-07-01",
                                   "end_date": "2026-07-10", "mode": mode})
    assert r.status_code == 403
    assert r.json()["reason"] == "adjustment_mode_not_in_v1"


def test_g06_no_three_price_columns_leak(client):
    r = client.get("/adj", params={"as_of": FREEZE, "code": "600519.SH",
                                   "start_date": "2026-07-01", "end_date": "2026-07-10"})
    assert r.status_code == 200
    for row in r.json()["data"]:
        for k in row:
            assert not k.endswith(("_hfq", "_qfq", "_bfq"))


# ======================================================================
# G-08 fina_indicator 不可达
# ======================================================================


@pytest.mark.parametrize("name", ["fina_indicator", "fina_indicator_vip", "stk_factor_pro"])
def test_g08_excluded_datasets_are_unreachable(client, name):
    r = client.get("/fundamentals", params={"as_of": FREEZE, "statement": name})
    assert r.status_code == 403
    assert r.json()["reason"] == "dataset_not_exposed_in_v1"


def test_g08_backend_whitelist_is_a_whitelist_not_a_blacklist():
    from gateway import backends

    with pytest.raises(Exception):
        backends.assert_exposed("some_table_nobody_registered")


# ======================================================================
# /limits 不得泄露哨兵价（卡 1.2 D1 的下游版本）
# ======================================================================


@pytest.fixture(scope="module")
def sentinel_sample() -> tuple[str, str]:
    lake.raise_open_file_limit()
    df = lake.query(
        "SELECT ts_code, trade_date FROM stk_limit "
        "WHERE down_limit <= 0.01 AND trade_date <= ? "
        "ORDER BY trade_date DESC LIMIT 1",
        [FREEZE],
    )
    if not len(df):
        pytest.skip("冻结线内没挖到哨兵行")
    row = df.iloc[0]
    return str(row["ts_code"]), str(row["trade_date"])


def test_limits_never_leaks_a_sentinel_price(client, sentinel_sample):
    code, day = sentinel_sample
    iso = f"{day[:4]}-{day[4:6]}-{day[6:]}"
    r = client.get("/limits", params={"as_of": FREEZE, "code": code,
                                      "start_date": iso, "end_date": iso})
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body["rows"] >= 1
    row = body["data"][0]
    assert row["no_price_limit"] is True
    assert row["up_limit"] is None and row["down_limit"] is None, (
        "把哨兵值当真实涨停价发出去了 —— 下游算 up_limit/close 会拿到几千倍"
    )


def test_limits_does_not_expose_all_null_pre_close(client):
    r = client.get("/limits", params={"as_of": FREEZE, "code": "600519.SH",
                                      "start_date": "2026-07-01",
                                      "end_date": "2026-07-10"})
    assert r.status_code == 200
    for row in r.json()["data"]:
        assert "pre_close" not in row, "stk_limit.pre_close 全为 NULL，不该透出"


# ======================================================================
# /healthz 与后端开关
# ======================================================================


def test_healthz_needs_no_asof_but_is_still_logged(client, logfile):
    before = _log_len(logfile)
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["bind"] == f"{cfg.GATEWAY_HOST}:{cfg.GATEWAY_PORT}"
    assert _log_len(logfile) > before, "探活也是一次访问，必须记账"


def test_backend_switch_is_config_driven(monkeypatch):
    from gateway import backends

    monkeypatch.setenv("GENEBENCH_GATEWAY_BACKEND", "snapshot")
    assert backends.default_backend() == "snapshot"
    monkeypatch.setenv("GENEBENCH_GATEWAY_BACKEND", "live")
    assert backends.default_backend() == "live"
    monkeypatch.setenv("GENEBENCH_GATEWAY_BACKEND", "nonsense")
    with pytest.raises(ValueError):
        backends.default_backend()
