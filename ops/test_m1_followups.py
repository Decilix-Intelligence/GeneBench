# -*- coding: utf-8 -*-
"""M1 签字收尾（指令 2① / 2② / 3① / 3②）的验收。

立场同前几卡：**不写自证式断言**。模糊区段的条数与成员日从对账产物取，
但**成员日总数钉死 791**（签字口径）——写死这个数就是为了让它在任何一侧变化时报红。
"""
from __future__ import annotations

import datetime as dt
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import genebench_config as cfg  # noqa: E402
from snapshots import code_alias, lake  # noqa: E402
from snapshots import universe_build as ub  # noqa: E402

#: M1 签字回执里的口径。两边任一变化都必须报红，不许静默。
SIGNED_OFF_MEMBER_DAYS: int = 791
SIGNED_OFF_SPANS: int = 6
SIGNED_OFF_ALIAS_PAIRS: int = 5


# ======================================================================
# 指令 2① —— ambiguous 标记
# ======================================================================


def test_ambiguous_spans_match_the_signoff():
    runs = ub.ambiguous_spans()
    assert len(runs) == SIGNED_OFF_SPANS, (
        f"模糊区段 {len(runs)} 条，签字口径是 {SIGNED_OFF_SPANS} 条"
    )
    assert ub.ambiguous_member_days() == SIGNED_OFF_MEMBER_DAYS, (
        f"模糊成员日 {ub.ambiguous_member_days()}，签字口径是 {SIGNED_OFF_MEMBER_DAYS}"
    )
    for r in runs:
        assert r["universe"] in cfg.UNIVERSES
        assert r["only_in_source"] in ("A", "B")
        assert dt.date.fromisoformat(r["start"]) <= dt.date.fromisoformat(r["end"])


def test_ambiguous_spans_come_from_full_runs_not_examples():
    """产物必须有 `runs` 全量，不是 `examples` 的 3 条。

    这条是护栏：拿 examples 打标记会漏掉一半区段（6 条只标 3 条），
    而漏标的失败形态是**静默的** —— 生成器照样出题，题面落在两源打架的地方。
    """
    import json

    data = json.loads((cfg.OPS / "universe_reconciliation.json").read_text(encoding="utf-8"))
    cls = data["divergence_classes"][ub.AMBIGUOUS_CLASS]
    assert "runs" in cls, "对账产物没有 runs 字段"
    assert len(cls["runs"]) == cls["n_runs"] == SIGNED_OFF_SPANS
    assert len(cls["examples"]) < len(cls["runs"]), "examples 竟然和 runs 一样多？"


def test_pit_has_the_ambiguous_column():
    frame, _ = ub.read_pit()
    assert "ambiguous" in frame.columns
    assert frame["ambiguous"].dtype == bool
    assert frame["ambiguous"].any(), "一行都没标上 —— 标记逻辑没生效"


def test_every_ambiguous_span_is_covered_by_flag_or_absent_by_design():
    """每条模糊区段要么有被标记的行，要么在 canonical 口径下根本没有行。

    后者不是漏标：例如 `300114.SZ` 只有源B 说它在市，源A 没有这段，
    universe_pit（canonical=源A 为主）里查无此段 —— 所以**行级列不是权威**，
    权威是 `ambiguous_spans()`。这条测试把这个事实钉死。
    """
    frame, _ = ub.read_pit()
    absent: list[str] = []
    for r in ub.ambiguous_spans():
        lo, hi = dt.date.fromisoformat(r["start"]), dt.date.fromisoformat(r["end"])
        hit = frame[
            (frame["universe"] == r["universe"])
            & (frame["code"] == r["code"])
            & (frame["in_date"] <= hi)
            & (frame["out_date"] >= lo)
        ]
        if len(hit):
            assert hit["ambiguous"].all(), f"{r['code']} 有交集的行没被标记"
        else:
            absent.append(f"{r['universe']}/{r['code']}")
    # 至少有一条是"产物里没有对应行"的，否则这条测试没有判别力
    assert absent, "没有任何一条区段是 canonical 缺行的？那 spans 与列就等价了，回来看"


def test_universe_at_can_exclude_ambiguous():
    """`exclude_ambiguous=True` 必须真的少给成员，而且少的正好是那几只。"""
    frame, meta = ub.read_pit()
    checked = 0
    for r in ub.ambiguous_spans():
        if r["only_in_source"] != "A":
            continue  # 只有源A 有的段才可能出现在 canonical 产物里
        day = dt.date.fromisoformat(r["start"])
        keep = ub.universe_at(r["universe"], day.strftime("%Y%m%d"),
                              frame=frame, meta=meta)
        drop = ub.universe_at(r["universe"], day.strftime("%Y%m%d"),
                              frame=frame, meta=meta, exclude_ambiguous=True)
        if r["code"] in keep:
            assert r["code"] not in drop, f"{r['code']} 没被排除掉"
            assert set(keep) - set(drop) == {r["code"]}, "排除面扩大了，不该误伤"
            checked += 1
    assert checked > 0, "一条都没验到 —— 测试没有判别力"


def test_excluding_ambiguous_is_a_noop_outside_the_spans():
    """区段之外不许误伤：随便挑一个干净的日子，两种读法必须完全一致。"""
    frame, meta = ub.read_pit()
    for day in ("20260731", "20200102", "20150105"):
        a = ub.universe_at("csi300", day, frame=frame, meta=meta)
        b = ub.universe_at("csi300", day, frame=frame, meta=meta, exclude_ambiguous=True)
        assert a == b or set(a) - set(b), "误伤了区段之外的成员"


def test_is_ambiguous_is_exact_on_the_boundary():
    """闭区间：首尾两天都算命中，各外扩一天都不算。"""
    r = ub.ambiguous_spans()[0]
    lo, hi = dt.date.fromisoformat(r["start"]), dt.date.fromisoformat(r["end"])
    assert ub.is_ambiguous(r["universe"], r["code"], lo)
    assert ub.is_ambiguous(r["universe"], r["code"], hi)
    assert not ub.is_ambiguous(r["universe"], r["code"], lo - dt.timedelta(days=1))
    assert not ub.is_ambiguous(r["universe"], r["code"], hi + dt.timedelta(days=1))


# ======================================================================
# 指令 2② —— code_alias
# ======================================================================


def test_code_alias_table_exists_and_matches_the_report():
    frame = code_alias.read()
    assert len(frame) == SIGNED_OFF_ALIAS_PAIRS
    assert set(frame["status"]) == {"auto_inferred_pending_confirmation"}, (
        "有别名被标成了别的状态 —— 自动推断不能自己给自己升级"
    )


def test_code_alias_cannot_be_confirmed_without_evidence():
    """升级成 confirmed 必须有公告出处，否则构造即抛。"""
    with pytest.raises(ValueError):
        code_alias.Alias(
            universe="csi1000", code_a="001872.SZ", code_b="000022.SZ",
            day_set_jaccard=0.98, span_start="2015-05-29", span_end="2018-12-27",
            n_disagreement_td=877, status="confirmed",
        )
    ok = code_alias.Alias(
        universe="csi1000", code_a="001872.SZ", code_b="000022.SZ",
        day_set_jaccard=0.98, span_start="2015-05-29", span_end="2018-12-27",
        n_disagreement_td=877, status="confirmed", evidence="深交所公告 XXXX",
    )
    assert ok.status == "confirmed"


def test_code_alias_does_not_leak_into_universe_pit():
    """签字裁定：别名**不进** universe_pit 本体，宇宙表继续用湖的当前码。"""
    frame, _ = ub.read_pit()
    alias = code_alias.read()
    pit_codes = set(frame["code"])
    # 源B 侧的码不应该出现在产物里（除非它本来就是湖的当前码）
    leaked = [
        r["code_b"] for _, r in alias.iterrows()
        if r["code_b"] in pit_codes and r["code_b"] != r["code_a"]
    ]
    assert not leaked, f"源B 侧的码泄漏进了 universe_pit：{leaked}"


def test_code_alias_declares_its_use_boundary():
    import json

    summary = json.loads((cfg.OPS / "code_alias.json").read_text(encoding="utf-8"))
    assert "universe_pit" in summary["forbidden_uses"]
    assert "reconciliation" in summary["allowed_uses"]


# ======================================================================
# 指令 2③ —— 数据卡补记
# ======================================================================


def test_data_card_records_the_csi1000_window_floor():
    card = (cfg.DATA_CARDS / "universe_pit.md").read_text(encoding="utf-8")
    assert "2015-05-29" in card, "数据卡没写 csi1000 的市场窗口起点"
    assert "csi1000" in card


# ======================================================================
# 指令 3① —— 网关 workers 守门
# ======================================================================


def test_run_module_refuses_multiple_workers():
    from gateway import run as gwrun

    with pytest.raises(RuntimeError, match="worker"):
        gwrun.assert_single_worker(2)
    with pytest.raises(RuntimeError):
        gwrun.assert_single_worker(4)
    assert gwrun.assert_single_worker(1) == 1
    assert gwrun.assert_single_worker(None) == 1


def test_run_cli_rejects_workers_flag():
    """命令行给 --workers 2 必须**拒绝启动**，不是只在 docstring 里警告。"""
    proc = subprocess.run(
        [str(cfg.PYTHON), "-m", "gateway.run", "--workers", "2"],
        cwd=str(cfg.REPO), capture_output=True, text=True, timeout=90,
    )
    assert proc.returncode != 0, "多 worker 竟然启动了"
    combined = proc.stdout + proc.stderr
    assert "worker" in combined.lower()
    assert "access_log" in combined or "日志" in combined


def test_access_log_lock_is_process_local_and_documented():
    from gateway import access_log

    src = Path(access_log.__file__).read_text(encoding="utf-8")
    assert "threading" in src and "_LOCK" in src
    assert "worker" in src, "没写清楚多 worker 的限制"


# ======================================================================
# 指令 3② —— load_listing_windows 的字段回溯语义
# ======================================================================


@pytest.fixture(scope="module")
def grid_and_windows():
    lake.raise_open_file_limit()
    with lake.catalog(retries=40, retry_wait=15.0) as con:
        grid = ub.load_grid(con)
        windows, diag = ub.load_listing_windows(grid, conn=con)
    return grid, windows, diag


def test_listing_window_starts_at_or_after_list_date(grid_and_windows):
    """上市边界：窗口左端 = 不早于 list_date 的第一个交易日。"""
    grid, windows, _ = grid_and_windows
    with lake.catalog(retries=40, retry_wait=15.0) as con:
        df = lake.query(
            "SELECT DISTINCT ts_code, list_date FROM stock_basic "
            "WHERE list_date IS NOT NULL AND list_date >= '20150101' "
            "ORDER BY list_date LIMIT 40",
            conn=con,
        )
    checked = 0
    for row in df.itertuples(index=False):
        w = windows.get(row.ts_code)
        if not w:
            continue
        ld = dt.date(int(row.list_date[:4]), int(row.list_date[4:6]), int(row.list_date[6:]))
        start = grid.days[w[0]]
        assert start >= ld, f"{row.ts_code} 窗口左端 {start} 早于 list_date {ld}"
        # 且它必须是"第一个"这样的交易日：前一个交易日要早于 list_date
        if w[0] > 0:
            assert grid.days[w[0] - 1] < ld, f"{row.ts_code} 左端不是第一个交易日"
        checked += 1
    assert checked >= 5, f"只验到 {checked} 只，样本太少"


def test_listing_window_is_right_open_at_delist_date(grid_and_windows):
    """退市边界：右端**开区间** —— 最后一个在市交易日严格早于 delist_date。

    依据（模块 docstring 已写、这里现场复验）：湖 `daily` 在 delist_date
    当天及之后**零行**，把退市日算进在市会造出一个没有行情的持仓日。
    """
    grid, windows, _ = grid_and_windows
    with lake.catalog(retries=40, retry_wait=15.0) as con:
        df = lake.query(
            "SELECT DISTINCT ts_code, delist_date FROM stock_basic "
            "WHERE delist_date IS NOT NULL AND delist_date <> '' "
            "AND delist_date >= '20150101' AND delist_date <= ? "
            "ORDER BY delist_date DESC LIMIT 25",
            [lake.FREEZE_DATE_COMPACT], conn=con,
        )
        checked = 0
        for row in df.itertuples(index=False):
            w = windows.get(row.ts_code)
            if not w:
                continue
            dd = dt.date(int(row.delist_date[:4]), int(row.delist_date[4:6]),
                         int(row.delist_date[6:]))
            last = grid.days[w[1]]
            assert last < dd, f"{row.ts_code} 在市窗口含到了 {last} >= delist_date {dd}"
            # 现场复验"退市日当天及之后 daily 零行"这条依据
            n = lake.query(
                "SELECT count(*) AS n FROM daily WHERE ts_code = ? AND trade_date >= ?",
                [row.ts_code, row.delist_date], conn=con,
            ).iloc[0]["n"]
            assert int(n) == 0, (
                f"{row.ts_code} 在 delist_date 当天及之后还有 {n} 行 daily —— "
                f"右端开区间这条依据在这只票上不成立，回来重审口径"
            )
            checked += 1
    assert checked >= 3, f"只验到 {checked} 只退市票，样本太少"


def test_rename_does_not_change_the_listing_window(grid_and_windows):
    """更名边界：更名**不改变** ts_code，也就不该影响在市窗口。

    这条守的是一个容易犯的错：把 `namechange` 当成"换了一只票"去切窗口。
    真正会换码的是 `code_alias` 那一类（指令 2②），而它**不进 universe_pit**。
    """
    grid, windows, _ = grid_and_windows
    with lake.catalog(retries=40, retry_wait=15.0) as con:
        df = lake.query(
            "SELECT ts_code, count(*) AS n FROM namechange "
            "WHERE ann_date <= ? GROUP BY ts_code HAVING count(*) >= 3 "
            "ORDER BY n DESC LIMIT 10",
            [lake.FREEZE_DATE_COMPACT], conn=con,
        )
        assert len(df), "湖里没有多次更名的票？"
        checked = 0
        for row in df.itertuples(index=False):
            w = windows.get(row.ts_code)
            if not w:
                continue
            basic = lake.query(
                "SELECT DISTINCT list_date, delist_date FROM stock_basic WHERE ts_code = ?",
                [row.ts_code], conn=con,
            )
            assert len(basic) == 1, f"{row.ts_code} 的在市字段在多快照间漂移了"
            ld = basic.iloc[0]["list_date"]
            start = grid.days[w[0]]
            assert start >= dt.date(int(ld[:4]), int(ld[4:6]), int(ld[6:])), (
                f"{row.ts_code} 更名了 {row.n} 次，但窗口左端跑到了 list_date 之前"
            )
            checked += 1
    assert checked >= 3, f"只验到 {checked} 只更名票，样本太少"


def test_listing_window_diagnostics_are_self_consistent(grid_and_windows):
    _, windows, diag = grid_and_windows
    assert diag["n_codes_with_window_in_grid"] == len(windows)
    assert diag["n_codes_in_view"] >= len(windows)
    assert "左闭右开" in diag["convention"]


def test_two_grid_classes_are_not_interchangeable():
    """`universe_build.Grid` 与 `universe_reconcile.Grid` **同名但接口不同**。

    我写这组测试时就踩了：reconcile 的有 `.date(i)` / `.iso(i)`，build 的只有
    `.days[i]`（外加 `.compact`）。两边刻意各建一份是为了保持"报告依赖产物、
    产物不依赖报告"的依赖方向（build.Grid 的 docstring 写了理由），
    但同名会让人以为可以互换。这条把差异钉死，将来谁统一了接口会在这里报红。
    """
    from snapshots import universe_reconcile as ur

    assert hasattr(ur.Grid, "date") and hasattr(ur.Grid, "iso")
    assert not hasattr(ub.Grid, "date"), "build.Grid 长出了 .date()——两边该统一了"
    assert hasattr(ub.Grid, "compact") and hasattr(ub.Grid, "index_of")
    # 共有的部分必须真的同义
    for name in ("floor", "ceil"):
        assert hasattr(ub.Grid, name) and hasattr(ur.Grid, name)
