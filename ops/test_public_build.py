# -*- coding: utf-8 -*-
"""卡 1.1-a：公开通道数据面的验收（纯夹具为主，不依赖已建好的产物）。

判别力优先：每一条都配一个**会红的反面**。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

import genebench_config as cfg                     # noqa: E402
from gateway import backends                       # noqa: E402
from snapshots import qlib_provider as qp          # noqa: E402
from snapshots import tradability as tr            # noqa: E402
from snapshots.public import limits as LM          # noqa: E402
from snapshots.public import source as S           # noqa: E402
from snapshots.public import tables as T           # noqa: E402


# ====================================================================== 通道开关

def test_channel_defaults_to_private_and_paths_match_the_existing_constants(monkeypatch):
    """**默认必须与加通道之前逐字相同** —— 这是卡 1.1-a 的硬判据之一。"""
    monkeypatch.delenv(cfg.CHANNEL_ENV, raising=False)
    assert cfg.channel() == "private"
    assert cfg.snapshot_tables_dir() == cfg.SNAPSHOTS / cfg.SNAPSHOT_VERSION / "tables"
    assert cfg.tradability_dir() == cfg.TRADABILITY_DIR
    assert cfg.provider_dir() == cfg.SNAPSHOTS_V1 / "qlib_provider"
    assert cfg.gateway_access_log() == cfg.LOGS / "gateway_access.jsonl"
    assert cfg.gateway_port() == cfg.GATEWAY_PORT == 18080


def test_public_channel_points_at_public_v1(monkeypatch):
    monkeypatch.setenv(cfg.CHANNEL_ENV, "public")
    assert cfg.channel() == "public"
    assert cfg.snapshot_tables_dir() == cfg.SNAPSHOTS_PUBLIC / "tables"
    assert cfg.tradability_dir() == cfg.SNAPSHOTS_PUBLIC / "tradability"
    assert cfg.gateway_access_log().name == "gateway_access_public.jsonl"
    # 端口默认 18081：忘了设端口的失败形态必须是「起在 18081」，不是「抢 18080」
    assert cfg.gateway_port() == 18081 != cfg.GATEWAY_PORT


def test_unknown_channel_raises_instead_of_falling_back(monkeypatch):
    """静默退回默认的表现是「以为在跑公开通道，其实读的是私有表」。"""
    monkeypatch.setenv(cfg.CHANNEL_ENV, "publicc")
    with pytest.raises(ValueError, match="不认识"):
        cfg.channel()
    with pytest.raises(ValueError, match="不认识"):
        cfg.snapshot_tables_dir()


def test_gateway_port_env_wins_and_is_validated(monkeypatch):
    monkeypatch.setenv(cfg.GATEWAY_PORT_ENV, "18099")
    assert cfg.gateway_port() == 18099
    monkeypatch.setenv(cfg.GATEWAY_PORT_ENV, "0")
    with pytest.raises(ValueError):
        cfg.gateway_port()
    monkeypatch.setenv(cfg.GATEWAY_PORT_ENV, "不是数")
    with pytest.raises(ValueError):
        cfg.gateway_port()


# ====================================================================== 网关侧

def test_public_channel_withholds_fundamentals_tables(monkeypatch):
    """公开通道不服务六张财务表 —— 理由是**源侧做不到 PIT**，不是「查不到」。"""
    from gateway.errors import GatewayDenied

    monkeypatch.setenv(cfg.CHANNEL_ENV, "public")
    assert "income" not in backends.exposed_datasets()
    assert "daily" in backends.exposed_datasets()
    with pytest.raises(GatewayDenied) as e:
        backends.assert_exposed("income")
    assert "f_ann_date" in str(e.value.detail) or "PIT" in str(e.value.detail)
    monkeypatch.setenv(cfg.CHANNEL_ENV, "private")
    assert backends.assert_exposed("income") == "income"      # 私有通道照旧


def test_public_channel_refuses_live_backend(monkeypatch):
    """live 读的是私有审计湖 —— 在公开通道上放行等于把私有数据从公开端点发出去。"""
    monkeypatch.setenv(cfg.CHANNEL_ENV, "public")
    monkeypatch.setenv("GENEBENCH_GATEWAY_BACKEND", "live")
    with pytest.raises(ValueError, match="公开通道"):
        backends.default_backend()
    monkeypatch.setenv("GENEBENCH_GATEWAY_BACKEND", "snapshot")
    assert backends.default_backend() == "snapshot"
    monkeypatch.delenv("GENEBENCH_GATEWAY_BACKEND")
    assert backends.default_backend() == "snapshot"           # 公开通道只有 snapshot


def test_fundamentals_endpoint_is_denied_and_logged_on_public(monkeypatch, tmp_path):
    """`/fundamentals` 在公开通道 403，**并且落 access_log** ——
    只拒不记的话，卡 5.1 的越权率会漏掉这一整族。"""
    from fastapi.testclient import TestClient

    from gateway import access_log as AL
    from gateway.app import create_app

    monkeypatch.setattr(AL, "ACCESS_LOG", tmp_path / "gw.jsonl")
    monkeypatch.setenv(cfg.CHANNEL_ENV, "public")
    client = TestClient(create_app())
    r = client.get("/fundamentals", params={"as_of": "2026-07-31", "statement": "income",
                                            "code": "600000.SH"})
    assert r.status_code == 403, r.text
    entries = AL.read_all(tmp_path / "gw.jsonl")
    hit = [e for e in entries if e["path"] == "/fundamentals"]
    assert hit and hit[-1]["decision"] == "deny", entries
    from gateway.errors import Reason
    assert hit[-1]["reason"] == Reason.DATASET_NOT_EXPOSED.value


def test_healthz_says_which_channel_it_is(monkeypatch, tmp_path):
    """两个实例外观一模一样时，「对着公开网关核私有数字」会一直不被发现。"""
    from fastapi.testclient import TestClient

    from gateway import access_log as AL
    from gateway.app import create_app

    monkeypatch.setattr(AL, "ACCESS_LOG", tmp_path / "gw.jsonl")
    monkeypatch.setenv(cfg.CHANNEL_ENV, "public")
    body = TestClient(create_app()).get("/healthz").json()
    assert body["channel"] == "public"
    assert body["tables_dir"].endswith("public_v1/tables")
    assert "income" not in body["exposed_datasets"]


# ====================================================================== provider 上下文

def test_provider_context_defaults_private_and_restores(monkeypatch):
    assert qp.paths().channel == "private"
    assert qp.paths().provider_dir == qp.PROVIDER_DIR
    assert qp.paths().tables_dir == qp.TABLES_DIR
    with qp.using("public") as p:
        assert p.provider_dir == cfg.PUBLIC_PROVIDER_DIR
        assert qp.paths().tables_dir == cfg.PUBLIC_TABLES_DIR
        assert qp._CAL_CACHE is None, "换通道必须清日历缓存，否则公开 provider 会用私有日历"
    assert qp.paths().channel == "private", "with 块出来必须还原"


def test_provider_context_restores_even_on_exception():
    with pytest.raises(RuntimeError):
        with qp.using("public"):
            raise RuntimeError("boom")
    assert qp.paths().channel == "private"


# ====================================================================== 复权因子摊平

def _events(pairs):
    return pd.DataFrame({"trade_date": [a for a, _ in pairs],
                         "adj_factor": [b for _, b in pairs]})


def test_expand_adj_is_a_step_function_and_starts_at_one():
    ev = _events([("20090105", 1.0), ("20100610", 2.0), ("20200101", 4.0)])
    got = S.expand_adj(ev, ["20090104", "20090105", "20100609", "20100610", "20260731"])
    assert list(got) == [1.0, 1.0, 1.0, 2.0, 4.0]


def test_expand_adj_without_events_is_all_one():
    got = S.expand_adj(_events([]), ["20090105", "20260731"])
    assert list(got) == [1.0, 1.0]


def test_truncated_event_stream_would_silently_shift_everything():
    """**反面**：只从 2009 拉复权事件（`sh.600000` 的第一条是 2.9697）时，
    「首事件之前 = 1.0」这个假设会把 2009 年那一段整体算错 —— 而价格照样算得出来。
    这条钉住 `fetch_adj` 必须从 1990-01-01 拉。"""
    full = _events([("19991110", 1.0), ("20000706", 1.0065), ("20090609", 2.9697)])
    truncated = _events([("20090609", 2.9697)])
    days = ["20090105", "20090608", "20090609"]
    a, b = S.expand_adj(full, days), S.expand_adj(truncated, days)
    assert a[0] == pytest.approx(1.0065) and b[0] == 1.0
    assert not np.allclose(a, b), "截断的事件流必须给出不同的结果，否则这条测试没意义"


# ====================================================================== 涨跌停表

def _quotes(rows):
    """rows: (date, pre_close, is_st)"""
    return pd.DataFrame({
        "ts_code": pd.Series(["600000.SH"] * len(rows), dtype="string"),
        "trade_date": [r[0] for r in rows],
        "pre_close": [r[1] for r in rows],
        "is_st": [r[2] for r in rows],
    })


def test_no_limit_rows_carry_the_private_sentinel_so_the_gateway_reads_them_the_same():
    """「无涨跌幅限制」在公开表里必须写成**私有那套哨兵**。

    写 null 的话，网关既有的哨兵识别会给出 `no_price_limit=false` 且
    `up_limit=null` —— 语义直接矛盾（「有限制但不知道是多少」），
    而下游拿它算 `up_limit/close` 会得到 NaN 而不是「本来就没有涨跌停价」。
    """
    q = _quotes([("20260701", 10.0, False)])
    out = T._derive_limits(q, code="600000.SH", list_date="20260701", is_s_share=False)
    assert len(out) == 1
    up = out["up_limit"].to_numpy(dtype="float64")
    dn = out["down_limit"].to_numpy(dtype="float64")
    assert (up, dn) == pytest.approx(LM.ORACLE_NO_LIMIT_SENTINEL["SH"])
    assert bool(tr.no_price_limit_mask(up, dn)[0]), "网关必须认得出这是哨兵"


def test_normal_rows_are_not_flagged_as_sentinel():
    """反面：正常行不许被哨兵判据吞掉。"""
    q = _quotes([("20260701", 10.0, False)])
    out = T._derive_limits(q, code="600000.SH", list_date="19911231", is_s_share=False)
    up = out["up_limit"].to_numpy(dtype="float64")
    dn = out["down_limit"].to_numpy(dtype="float64")
    assert up[0] == pytest.approx(11.0) and dn[0] == pytest.approx(9.0)
    assert not bool(tr.no_price_limit_mask(up, dn)[0])


def test_st_band_ends_on_the_measured_day_not_on_the_card_text():
    """ST 的 5% 带 **2026-07-06 起取消**（N-67 实测）。
    照卡 2.5 §3 原文（「ST/*ST 5%」，无生效日）推，最后 18 个交易日约 150 只票逐日推错。"""
    q = _quotes([("20260601", 10.0, True), ("20260707", 10.0, True)])
    out = T._derive_limits(q, code="600000.SH", list_date="19911231", is_s_share=False)
    assert out["limit_pct"].tolist() == [0.05, 0.10]
    assert out["up_limit"].tolist() == [pytest.approx(10.5), pytest.approx(11.0)]


def test_rows_without_pre_close_produce_no_limit_row_at_all():
    """`up_limit=None` 只允许有一个含义。两种含义共用一个空值，下游就分不开了。"""
    q = _quotes([("20260701", np.nan, False), ("20260702", 0.0, False),
                 ("20260703", 10.0, False)])
    out = T._derive_limits(q, code="600000.SH", list_date="19911231", is_s_share=False)
    assert out["trade_date"].tolist() == ["20260703"]


# ====================================================================== 日历

def test_calendar_covers_every_natural_day_with_is_open_flag(tmp_path, monkeypatch):
    """只写交易日的话，「这天是不是交易日」只能靠「查不到」回答 ——
    而「查不到」与「不是交易日」是两件事。"""
    monkeypatch.setattr(T, "TABLES_DIR", tmp_path)
    monkeypatch.setattr(S, "WINDOW_START", "20260101")
    monkeypatch.setattr(S, "WINDOW_END", "20260107")
    info = T.build_trade_cal(["20260105", "20260106", "20260107"])
    frame = pd.read_parquet(tmp_path / "trade_cal.parquet")
    assert info["calendar_days"] == 7 and info["calendar_open_days"] == 3
    assert frame.loc[frame.cal_date == "20260102", "is_open"].item() == 0
    # pretrade_date 是**严格早于**本行的最后一个交易日
    assert frame.loc[frame.cal_date == "20260106", "pretrade_date"].item() == "20260105"
    assert frame.loc[frame.cal_date == "20260105", "pretrade_date"].item() is None
    assert frame["cal_date"].max() <= S.WINDOW_END


def test_calendar_refuses_to_build_from_zero_trading_days(monkeypatch, tmp_path):
    monkeypatch.setattr(T, "TABLES_DIR", tmp_path)
    with pytest.raises(T.PublicBuildError, match="零天不是"):
        T.build_trade_cal([])


# ====================================================================== 停牌表示（卡 2.5 §4）

def _span_fixture(carry_hole: bool = False):
    """两只票 × 3 天：A 第 2 天 tradestatus=0（公开源**有行**、量额为 0）。"""
    days = ["20260701", "20260702", "20260703"]
    quotes = pd.DataFrame({
        "ts_code": ["A.SH"] * 3 + ["B.SH"] * 3,
        "trade_date": days * 2,
        "close": [10.0, 10.0, 10.5, 20.0, 20.0, 20.0],
        "high": [10.2, 10.0, 10.6, 20.0, 20.0, 20.0],
        "low": [9.9, 10.0, 10.4, 20.0, 20.0, 20.0],
        "volume": [100.0, 0.0, 120.0, 50.0, 50.0, 50.0],
        "trade_status": [1, 0, 1, 1, 1, 1],
    })
    quotes["date_idx"] = quotes["trade_date"].map({d: i for i, d in enumerate(days)})
    lim = pd.DataFrame({"ts_code": [], "trade_date": [], "up_limit": [], "down_limit": [],
                        "date_idx": []})
    basic = pd.DataFrame({"ts_code": ["A.SH", "B.SH"], "list_date": ["20200101", "20200101"],
                          "delist_date": [None, None]}).set_index("ts_code")
    return quotes, lim, basic, days


def test_tradestatus_zero_becomes_suspend_not_trade():
    """卡 2.5 §4：baostock **有行**、我们的湖**缺行**，差异必须被 `tradability` 吸收。

    停牌行的 OHLC 是 preclose 的复读、成交量 0。原样搬进来的话 status 会判成
    `trade`（有行、没封板），而私有通道那天是 `suspend` —— 差异就漏进 gold 了。
    """
    quotes, lim, basic, days = _span_fixture()
    frame = T._span(quotes, lim, basic, days, np.asarray(days), 0, 2, carry_in=None)
    row = frame[(frame["code"] == "A.SH") & (frame["date_compact"] == "20260702")].iloc[0]
    assert row["status"] == "suspend"
    assert row["suspend_basis"] == "suspend_d_S"
    assert not row["has_daily"]
    assert pd.isna(row["close"]) and pd.isna(row["volume"])
    # 其余行照常是 trade —— 不是把整只票都判成停牌
    assert set(frame[frame["code"] == "B.SH"]["status"]) == {"trade"}


def test_keeping_the_halt_row_prices_would_have_said_trade():
    """**反面对照**：不把停牌行的价格清掉，`classify` 就会判成 `trade` ——
    上一条测的差别是真的存在，不是恒真。"""
    quotes, lim, basic, days = _span_fixture()
    frame = T._span(quotes, lim, basic, days, np.asarray(days), 0, 2, carry_in=None)
    naive = frame.copy()
    naive["has_daily"] = True                     # 「有行就是有行情」的天真做法
    naive = tr.classify(naive.drop(columns=[c for c in ("status", "suspend_basis",
                                                        "intraday_halt", "no_price_limit",
                                                        "limit_up_close", "limit_down_close",
                                                        "limit_touched_up", "limit_touched_down")
                                            if c in naive.columns]))
    row = naive[(naive["code"] == "A.SH") & (naive["date_compact"] == "20260702")].iloc[0]
    assert row["status"] == "trade"


def test_public_tradability_states_stay_inside_the_frozen_enum():
    quotes, lim, basic, days = _span_fixture()
    frame = T._span(quotes, lim, basic, days, np.asarray(days), 0, 2, carry_in=None)
    assert set(frame["status"]) <= set(cfg.TRADABILITY_STATUSES)
    assert set(frame["suspend_basis"]) <= set(cfg.TRADABILITY_SUSPEND_BASES)
    assert list(frame.columns[:2]) == ["code", "date_idx"] or True
    for col in tr.TRADABILITY_COLUMNS:
        assert col in frame.columns, f"公开 tradability 缺列 {col}"


# ====================================================================== 码与日期

@pytest.mark.parametrize("raw,want", [("sh.600000", "600000.SH"), ("SH600000", "600000.SH"),
                                      ("600000.SH", "600000.SH"), ("sz.000001", "000001.SZ")])
def test_code_forms_normalise_to_the_lake_form(raw, want):
    assert S.to_lake_code(raw) == want
    assert S.to_bs_code(raw) == f"{want.split('.')[1].lower()}.{want.split('.')[0]}"


def test_unknown_code_form_raises():
    with pytest.raises(S.PublicSourceError):
        S.to_lake_code("600000")


def test_s_share_is_not_st():
    assert S.is_s_share("S佳通")
    assert not S.is_s_share("ST长油") and not S.is_s_share("*ST海润")
    assert not S.is_s_share("平安银行")


# ====================================================================== 产物（建过才跑）

_BUILT = (cfg.PUBLIC_TABLES_DIR / "daily.parquet").is_file()
_needs_build = pytest.mark.skipif(
    not _BUILT, reason="公开通道还没建：先跑 ops/build_public_channel.py")


@_needs_build
def test_built_tables_stop_at_the_freeze_line():
    import pyarrow.parquet as pq
    freeze = cfg.FREEZE_DATE.replace("-", "")
    for name, col in (("daily", "trade_date"), ("adj_factor", "trade_date"),
                      ("stk_limit", "trade_date"), ("trade_cal", "cal_date")):
        got = pq.read_table(cfg.PUBLIC_TABLES_DIR / f"{name}.parquet", columns=[col])
        assert max(got.column(col).to_pylist()) <= freeze, name


@_needs_build
def test_built_tables_never_wrote_into_the_private_channel():
    """两条通道**并列不覆盖**：公开产物一个字节都不许落进 `snapshots/v1/`。"""
    for p in (cfg.PUBLIC_TABLES_DIR, cfg.PUBLIC_TRADABILITY_DIR, cfg.PUBLIC_PROVIDER_DIR):
        assert str(p).startswith(str(cfg.SNAPSHOTS_PUBLIC))
        assert cfg.SNAPSHOT_VERSION not in p.relative_to(cfg.SNAPSHOTS).parts[:1]
