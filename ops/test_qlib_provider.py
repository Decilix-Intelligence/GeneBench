# -*- coding: utf-8 -*-
"""卡 2.1a 验收：自建冻结 qlib provider 的五条完成定义 + 我们自己加的三条不变式。

签字人给的五条（编号沿用原话）：

    ① provider 的 factor 列与网关 /adj 端点对任意 (code,date) 逐值相等
    ② 由 provider 价除以 factor 反算的原始价与网关 /bars 相等（容差内）
    ③ provider 日历与截断后的 trade_cal 逐日相等
    ④ provider instruments 与 universe_pit 逐区段相等
    ⑤ 与社区 release 的收益率级比对作为诊断项报出一致率，**不作判据**

本文件跑**抽样**规模（进套件，秒级）；**全量**规模在
``ops/acceptance/card_2.1a_full_verify.py``，结果归档进报告。
两者的判据完全相同 —— 抽样不是放宽，是同一条断言的快版本。

立场沿用卡 1.3：不写自证式断言。日历、区段、样本码全部**从产物与快照现读**，
不抄实现里的常量。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import duckdb
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import genebench_config as cfg  # noqa: E402
from snapshots import qlib_provider as qp  # noqa: E402

FREEZE = cfg.FREEZE_DATE.replace("-", "")
TABLES = cfg.SNAPSHOTS_V1 / "tables"

pytestmark = pytest.mark.skipif(
    not qp.MANIFEST.exists(), reason="provider 尚未构建"
)


# ------------------------------------------------------------------ 夹具

@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(":memory:")
    yield c
    c.close()


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(qp.MANIFEST.read_text())


@pytest.fixture(scope="module")
def sample_codes(con) -> list[str]:
    """抽样码：**从数据里选出来的极端 + 确定性随机**，不是手挑的。

    极端 = 归一化跨度最大的（复权最容易出错的地方）与最小的；
    再按固定种子补随机码，保证三个交易所都有。
    """
    extreme = con.execute(f"""
        WITH lastf AS (
          SELECT ts_code, argMax(adj_factor, trade_date) f_last, min(adj_factor) f_min
          FROM read_parquet('{TABLES / 'adj_factor.parquet'}')
          WHERE trade_date <= '{FREEZE}' GROUP BY 1)
        (SELECT ts_code FROM lastf ORDER BY f_min/f_last ASC LIMIT 6)
        UNION ALL
        (SELECT ts_code FROM lastf ORDER BY f_min/f_last DESC LIMIT 6)
    """).fetchall()
    per_ex = con.execute(f"""
        SELECT ts_code FROM (
          SELECT ts_code, right(ts_code,2) ex,
                 row_number() OVER (PARTITION BY right(ts_code,2)
                                    ORDER BY hash(ts_code || '{cfg.TRADABILITY_SAMPLE_SEED}'), ts_code) rn
          FROM (SELECT DISTINCT ts_code FROM read_parquet('{TABLES / 'adj_factor.parquet'}'))
        ) WHERE rn <= 8 ORDER BY ts_code
    """).fetchall()
    codes = sorted({r[0] for r in extreme} | {r[0] for r in per_ex})
    assert len({c[-2:] for c in codes}) == 3, f"样本没覆盖三个交易所：{codes}"
    return codes


def _provider_frame(code: str) -> "dict[str, np.ndarray] | None":
    """读回一只票的全部字段 + 对应的日历日期。"""
    d = qp.FEATURES_DIR / qp.qlib_code(code).lower()
    if not d.exists():
        return None
    cal = qp.calendar()
    out: dict[str, np.ndarray] = {}
    start = None
    for f in qp.FIELDS:
        s, arr = qp.read_bin(d / f"{f}.day.bin")
        if start is None:
            start, n = s, len(arr)
        assert s == start, f"{code}/{f} 的 start_index {s} 与其它字段 {start} 不一致"
        assert len(arr) == n, f"{code}/{f} 长度不一致"
        out[f] = arr.astype("float64")
    out["date"] = np.array(cal[start:start + n], dtype=object)
    return out


# ------------------------------------------------------------------ ③ 日历

def test_03_calendar_equals_truncated_trade_cal(con):
    """③ provider 日历与截断后的 trade_cal 逐日相等。"""
    want = [r[0] for r in con.execute(
        f"SELECT cal_date FROM read_parquet('{TABLES / 'trade_cal.parquet'}') "
        f"WHERE exchange='SSE' AND is_open=1 AND cal_date <= '{FREEZE}' ORDER BY cal_date"
    ).fetchall()]
    got = [l.strip().replace("-", "") for l in
           qp.CALENDAR_FILE.read_text().splitlines() if l.strip()]
    assert got == want, f"日历不等：{len(got)} vs {len(want)}"
    assert got[-1] == FREEZE


def test_03b_no_future_calendar_and_snapshot_still_has_one():
    """provider 不出 day_future.txt，**而快照表里的未来日历必须还在**。

    这条把两处规则的差别钉住：卡 1.4 保留 153 行未来日历（T+N 对齐要用），
    卡 2.1 的求值日历停在冻结线。谁把其中一处"统一"掉，这条就红。
    """
    assert not (qp.CALENDAR_DIR / "day_future.txt").exists()
    con = duckdb.connect(":memory:")
    n = con.execute(
        f"SELECT count(*) FROM read_parquet('{TABLES / 'trade_cal.parquet'}') "
        f"WHERE cal_date > '{FREEZE}'").fetchone()[0]
    con.close()
    assert n > 0, "快照表里的未来日历没了 —— 卡 1.4 的 capture_time 规则被破坏"


def test_right_edges_are_counted_from_trade_cal_not_hardcoded():
    """求值右端从日历现数；并且必须真的比冻结线早 h 天。"""
    cal = qp.calendar()
    edges = qp.evaluation_right_edges()
    assert set(edges) == set(qp.HOLDING_PERIODS)
    for h, e in edges.items():
        assert cal.index(e) == len(cal) - 1 - h
        assert e < FREEZE if h >= 1 else True
    assert edges[1] > edges[5] > edges[20], "右端必须随持有期单调左移"
    with pytest.raises(ValueError):
        qp.evaluation_right_edge(0)
    with pytest.raises(ValueError):
        qp.evaluation_right_edge(len(cal))


# ------------------------------------------------------------------ ④ instruments

@pytest.mark.parametrize("uni", cfg.UNIVERSES_PIT)
def test_04_instruments_equal_universe_pit(con, uni):
    """④ provider instruments 与 universe_pit canonical 逐区段相等。"""
    want = [f"{qp.qlib_code(c)}\t{lo[:4]}-{lo[4:6]}-{lo[6:]}\t{hi[:4]}-{hi[4:6]}-{hi[6:]}"
            for c, lo, hi in con.execute(
                f"SELECT code, in_date_compact, out_date_compact "
                f"FROM read_parquet('{cfg.UNIVERSE_PIT_PARQUET}') "
                f"WHERE universe = ? AND canonical ORDER BY code, in_date_compact", [uni]
            ).fetchall()]
    got = [l for l in (qp.INSTRUMENTS_DIR / f"{uni}.txt").read_text().splitlines() if l.strip()]
    assert got == want, f"{uni} 区段不等：{len(got)} vs {len(want)}"


def test_04b_ambiguous_segments_are_kept_not_filtered(con):
    """④补：``ambiguous`` 区段必须**在场**。

    判别力：先断言 universe_pit 里真的有 ambiguous 行（否则这条是空的），
    再逐条断言它们出现在 instruments 文件里。provider 是数据层不做筛选 ——
    静默丢弃会让我们有两个不同的宇宙，且日后无法测"在模糊区段上会发生什么"。
    """
    rows = con.execute(
        f"SELECT universe, code, in_date_compact, out_date_compact "
        f"FROM read_parquet('{cfg.UNIVERSE_PIT_PARQUET}') WHERE canonical AND ambiguous"
    ).fetchall()
    assert rows, "universe_pit 里一条 ambiguous 都没有 —— 这条断言当前是空的，去查数据"
    for uni, code, lo, hi in rows:
        line = f"{qp.qlib_code(code)}\t{lo[:4]}-{lo[4:6]}-{lo[6:]}\t{hi[:4]}-{hi[4:6]}-{hi[6:]}"
        text = (qp.INSTRUMENTS_DIR / f"{uni}.txt").read_text()
        assert line in text, f"{uni} 少了 ambiguous 区段 {line!r}"


# ------------------------------------------------------------------ ① factor

def test_01_factor_matches_adj_factor_exactly(con, sample_codes):
    """① provider factor × 归一化基准 == 湖/网关的 adj_factor，逐值。

    provider 的 factor 是**归一化过的**（冻结线 = 1），所以逐值相等要带上基准；
    基准本身落在 ``norm_base.parquet`` 里，是产物的一部分，不是测试里的魔数。
    """
    base = {r[0]: (r[1], r[2]) for r in con.execute(
        f"SELECT ts_code, base_date, base_adj_factor FROM read_parquet('{qp.NORM_BASE_PARQUET}')"
    ).fetchall()}
    checked = 0
    worst = 0.0
    for code in sample_codes:
        pf = _provider_frame(code)
        assert pf is not None, f"{code} 没有 features"
        want = dict(con.execute(
            f"SELECT trade_date, adj_factor FROM read_parquet('{TABLES / 'adj_factor.parquet'}') "
            f"WHERE ts_code = ? AND trade_date <= '{FREEZE}'", [code]).fetchall())
        base_date, base_adj = base[code]
        assert base_date in want and want[base_date] == base_adj
        for i, d in enumerate(pf["date"]):
            f = pf["factor"][i]
            if d not in want:
                assert not np.isfinite(f), f"{code} {d} 没有 adj_factor 却写了 factor={f}"
                continue
            rel = abs(f * base_adj - want[d]) / want[d]
            worst = max(worst, rel)
            assert rel < 1e-6, f"{code} {d}: factor×base={f * base_adj} vs adj={want[d]}"
            checked += 1
    # 覆盖率不用魔数：样本码在冻结线内的 adj_factor 行**一条不能漏**。
    expected = con.execute(
        f"SELECT count(*) FROM read_parquet('{TABLES / 'adj_factor.parquet'}') "
        f"WHERE trade_date <= '{FREEZE}' AND ts_code IN "
        f"({','.join(['?'] * len(sample_codes))})", sample_codes).fetchone()[0]
    assert checked == expected, f"比了 {checked} 点，样本码应有 {expected} 点 —— 有行没被覆盖"
    print(f"\n① factor 逐值：{checked} 个点（= 样本全量），最大相对偏差 {worst:.3e}")


def test_01b_factor_is_one_at_freeze_for_listed_codes(con, sample_codes):
    """归一化基准定死为冻结线：冻结线当天在市的票 factor(冻结线) == 1。"""
    seen_freeze = seen_earlier = 0
    for code in sample_codes:
        pf = _provider_frame(code)
        idx = {d: i for i, d in enumerate(pf["date"])}
        if FREEZE in idx and np.isfinite(pf["factor"][idx[FREEZE]]):
            assert abs(pf["factor"][idx[FREEZE]] - 1.0) < 1e-6, code
            seen_freeze += 1
        else:
            # 冻结线前已退市/停更 → 基准是自身最后一日，那天 factor == 1
            fin = np.isfinite(pf["factor"])
            assert abs(pf["factor"][fin][-1] - 1.0) < 1e-6, code
            seen_earlier += 1
    assert seen_freeze, "样本里没有一只票活到冻结线？"


# ------------------------------------------------------------------ ② 反算原始价

def test_02_price_over_factor_recovers_raw(con, sample_codes):
    """② provider 价 / factor == 原始价（快照口径，即网关 /bars 的口径）。"""
    checked = 0
    worst = {f: 0.0 for f in ("open", "high", "low", "close")}
    for code in sample_codes:
        pf = _provider_frame(code)
        raw = {r[0]: r[1:] for r in con.execute(
            f"SELECT trade_date, open, high, low, close, amount, volume "
            f"FROM read_parquet('{TABLES / 'daily.parquet'}') "
            f"WHERE ts_code = ? AND trade_date <= '{FREEZE}'", [code]).fetchall()}
        for i, d in enumerate(pf["date"]):
            if d not in raw:
                assert not np.isfinite(pf["close"][i]), f"{code} {d} daily 无行却有价"
                continue
            o, h, l, c, amt, vol = raw[d]
            fac = pf["factor"][i]
            for name, want in (("open", o), ("high", h), ("low", l), ("close", c)):
                got = pf[name][i] / fac
                rel = abs(got - want) / max(abs(want), 1e-12)
                worst[name] = max(worst[name], rel)
                assert rel < 1e-5, f"{code} {d} {name}: {got} vs {want}"
            assert abs(pf["amount"][i] - amt) / max(amt, 1e-12) < 1e-6
            assert abs(pf["volume"][i] * fac - vol) / max(vol, 1e-12) < 1e-5
            checked += 1
    expected = con.execute(
        f"SELECT count(*) FROM read_parquet('{TABLES / 'daily.parquet'}') "
        f"WHERE trade_date <= '{FREEZE}' AND ts_code IN "
        f"({','.join(['?'] * len(sample_codes))})", sample_codes).fetchone()[0]
    assert checked == expected, f"比了 {checked} 行，样本码 daily 应有 {expected} 行"
    print(f"\n② 反算原始价：{checked} 行（= 样本全量），最大相对偏差 {worst}")


def test_02b_gateway_bars_and_adj_agree_with_provider(sample_codes):
    """②补：**走真网关端点**再验一遍（上一条走的是同一份快照 parquet）。

    端点带 as_of 判定与行域重建（/bars 的行域来自 tradability），
    parquet 直读绕过了这两层 —— 两条都过才说明 provider 与执行面同源。
    """
    from fastapi.testclient import TestClient
    from gateway.app import app

    client = TestClient(app)
    hdr = {"x-genebench-config-id": "c21a", "x-genebench-task-id": "verify"}
    code = sample_codes[len(sample_codes) // 2]
    lo, hi = "2026-06-01", "2026-07-31"
    r = client.get("/adj", params={"as_of": cfg.FREEZE_DATE, "code": code,
                                   "start_date": lo, "end_date": hi}, headers=hdr)
    assert r.status_code == 200, r.text
    gw_adj = {row["trade_date"]: row["adj_factor"] for row in r.json()["data"]}
    r = client.get("/bars", params={"as_of": cfg.FREEZE_DATE, "code": code,
                                    "start_date": lo, "end_date": hi}, headers=hdr)
    assert r.status_code == 200, r.text
    gw_bars = {str(row["date"]).replace("-", ""): row for row in r.json()["data"]}
    assert gw_adj and gw_bars, f"{code} 在窗口内没有网关数据"

    pf = _provider_frame(code)
    idx = {d: i for i, d in enumerate(pf["date"])}
    import duckdb as _d
    c2 = _d.connect(":memory:")
    base_adj = c2.execute(
        f"SELECT base_adj_factor FROM read_parquet('{qp.NORM_BASE_PARQUET}') WHERE ts_code=?",
        [code]).fetchone()[0]
    c2.close()
    n_adj = n_bar = 0
    for d, a in gw_adj.items():
        if d in idx and np.isfinite(pf["factor"][idx[d]]):
            assert abs(pf["factor"][idx[d]] * base_adj - a) / a < 1e-6, (code, d)
            n_adj += 1
    for d, row in gw_bars.items():
        if d not in idx or row.get("close") is None or not np.isfinite(pf["close"][idx[d]]):
            continue
        got = pf["close"][idx[d]] / pf["factor"][idx[d]]
        assert abs(got - row["close"]) / max(abs(row["close"]), 1e-12) < 1e-5, (code, d)
        n_bar += 1
    assert n_adj > 10 and n_bar > 10, f"网关比对样本太少 adj={n_adj} bars={n_bar}"
    print(f"\n②补 网关端点：{code} adj {n_adj} 点 / bars {n_bar} 点")


# ------------------------------------------------------------------ 我们加的不变式

def test_inv_vwap_times_volume_equals_amount(sample_codes):  # noqa: D401
    """``vwap × volume == amount``，**与复权无关**的逐行恒等式。

    它是"价格乘 factor、股数除 factor、金额不动"这套口径的直接推论，
    白得的内部一致性检查：任何一处分派写反，这条立刻红。
    """
    worst = 0.0
    n = 0
    for code in sample_codes:
        pf = _provider_frame(code)
        ok = np.isfinite(pf["vwap"]) & np.isfinite(pf["volume"]) & np.isfinite(pf["amount"])
        if not ok.any():
            continue
        lhs = pf["vwap"][ok] * pf["volume"][ok]
        rhs = pf["amount"][ok]
        rel = np.abs(lhs - rhs) / np.maximum(np.abs(rhs), 1e-12)
        worst = max(worst, float(rel.max()))
        n += int(ok.sum())
    assert n > 50_000, f"只验了 {n} 行，样本太小"
    assert worst < 1e-5, f"vwap×volume 与 amount 最大相对偏差 {worst}"
    print(f"\n恒等式 vwap×volume==amount：{n} 行，最大相对偏差 {worst:.3e}")


def test_inv_vwap_unit_band(sample_codes):
    """vwap 单位判据（签字人给的硬判据）：``low <= vwap <= high`` 的行占比 >= 99%。

    从 **provider 产物**现算，不是从湖 —— 单位若在写盘环节被改坏，这条要能看见。
    """
    inb = tot = 0
    for code in sample_codes:
        pf = _provider_frame(code)
        ok = (np.isfinite(pf["vwap"]) & np.isfinite(pf["low"]) & np.isfinite(pf["high"]))
        v, lo, hi = pf["vwap"][ok], pf["low"][ok], pf["high"][ok]
        tol = qp.VWAP_BAND_REL_TOL
        inb += int(np.sum((v >= lo * (1 - tol)) & (v <= hi * (1 + tol))))
        tot += int(ok.sum())
    rate = inb / tot
    print(f"\nvwap 落带率 {rate:.6%}（{inb}/{tot}，相对容差 {qp.VWAP_BAND_REL_TOL}）")
    assert rate >= qp.VWAP_BAND_MIN_RATE, f"落带率 {rate:.4%} < {qp.VWAP_BAND_MIN_RATE:.0%}：单位错了"


def test_inv_vwap_is_null_never_inf_when_volume_nonpositive(manifest):
    """volume<=0 的行 vwap 必须是 NULL，不得 inf/0。

    **判别力披露**：实测全表 ``volume<=0`` 的行 **0 条**，所以这条守门当前**空转**。
    这里不假装它被测过 —— 断言分两半：(a) 全 provider 无 inf；
    (b) 用**构造数据**直接打 ``_adjust()``，证明守门代码本身有效。
    """
    assert manifest["features"]["volume_nonpositive_rows"] == 0
    assert manifest["features"]["vwap_null_rows"] == 0
    raw = {"open": np.array([1.0, 1.0]), "high": np.array([1.0, 1.0]),
           "low": np.array([1.0, 1.0]), "close": np.array([1.0, 1.0]),
           "amount": np.array([100.0, 100.0]), "volume": np.array([0.0, 10.0])}
    out = qp._adjust(raw, np.array([1.0, 1.0]))
    assert not np.isfinite(out["vwap"][0]), f"volume=0 得到 {out['vwap'][0]}，应为 NaN"
    assert np.isnan(out["vwap"][0]), "必须是 NaN，不能是 inf"
    assert out["vwap"][1] == 10.0


def test_no_infinities_anywhere(sample_codes):
    for code in sample_codes:
        pf = _provider_frame(code)
        for f in qp.FIELDS:
            assert not np.isinf(pf[f]).any(), f"{code}/{f} 有 inf"


def test_adjustment_partition_guard_has_teeth():
    """D-03 纪律：分派表护栏必须是 **import 期**的，且删一个字段真的会炸。

    在**子进程**里注入，主进程零污染。
    """
    src = qp.__file__
    inject = (
        "import re,sys,importlib\n"
        f"p={src!r}\n"
        "s=open(p,encoding='utf-8').read()\n"
        "s=s.replace('frozenset({\"amount\", \"factor\"})','frozenset({\"amount\"})')\n"
        "import types\n"
        "m=types.ModuleType('x'); m.__file__=p\n"
        "sys.path.insert(0,'/data/shared/genebench/repo')\n"
        "try:\n"
        "    exec(compile(s,p,'exec'), m.__dict__)\n"
        "except RuntimeError as e:\n"
        "    print('GUARD_FIRED'); sys.exit(0)\n"
        "print('NO_GUARD'); sys.exit(1)\n"
    )
    r = subprocess.run([sys.executable, "-c", inject], capture_output=True, text=True,
                       cwd=str(cfg.REPO))
    assert "GUARD_FIRED" in r.stdout, f"护栏没响：{r.stdout}{r.stderr}"


# ------------------------------------------------------------------ qlib 真读得动

def test_qlib_can_read_the_provider(sample_codes):
    """**格式的唯一硬证据**：用 qlib 自己的读取器把 provider 读出来。

    bin 是我们直写的（没走 dump_bin 的 CSV 往返），所以格式对不对不能自证 ——
    必须由 qlib 的 ``D.features`` 判。顺带验 ``$close/$factor == 原始价``。
    在子进程里 ``qlib.init``，避免污染同套件里别的测试。
    """
    # 必须挑一只**在冻结线当天还在市**的票：否则窗口里零行，
    # `rows > 20` 会因为选码而不是因为格式变红。这一版之前就栽在这里 ——
    # 抽样顺序在全套件里与单跑不同，`sample_codes[0]` 换成了一只已退市的。
    alive = [c for c in sample_codes
             if (pf := _provider_frame(c)) is not None and FREEZE in set(pf["date"])]
    assert alive, f"样本里没有一只票活到冻结线：{sample_codes}"
    code = alive[0]
    script = f"""
import json, sys
import qlib
from qlib.data import D
qlib.init(provider_uri={str(qp.PROVIDER_DIR)!r}, region="cn",
          expression_cache=None, dataset_cache=None, redis_port=-1)
df = D.features([{qp.qlib_code(code)!r}], ["$close", "$factor", "$vwap", "$volume", "$amount"],
                start_time="2026-06-01", end_time="2026-07-31", freq="day")
ins = D.instruments("csi300")
names = D.list_instruments(ins, start_time="2026-07-31", end_time="2026-07-31", as_list=True)
cal = D.calendar(start_time="2026-01-01", end_time="2026-12-31", freq="day")
print(json.dumps({{"rows": len(df), "cols": list(df.columns),
                  "last": None if df.empty else float(df["$close"].iloc[-1]),
                  "last_factor": None if df.empty else float(df["$factor"].iloc[-1]),
                  "csi300_n": len(names),
                  "cal_max": str(max(cal))[:10], "cal_n": len(cal)}}))
"""
    r = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                       cwd=str(cfg.REPO))
    assert r.returncode == 0, f"qlib 读 provider 失败：\n{r.stdout}\n{r.stderr[-3000:]}"
    out = json.loads(r.stdout.strip().splitlines()[-1])
    print(f"\nqlib 读回：{out}")
    assert out["rows"] > 20, out
    assert set(out["cols"]) == {"$close", "$factor", "$vwap", "$volume", "$amount"}
    assert 250 <= out["csi300_n"] <= 320, f"csi300 在冻结线当天 {out['csi300_n']} 只"
    assert out["cal_max"] <= cfg.FREEZE_DATE, (
        f"qlib 眼里的日历越过冻结线：{out['cal_max']} —— 红线 7 的结构保证破了")


def test_manifest_records_digest_and_matches_files(manifest):
    """产物随 manifest 记 sha256；重算 files.sha256 的根必须对得上。"""
    d = manifest["digest"]
    assert d["files"] > 46_000 and d["bytes"] > 400_000_000
    assert qp._sha256(qp.FILES_DIGEST) == d["files_sha256_digest"]
    lines = qp.FILES_DIGEST.read_text().splitlines()
    assert len(lines) == d["files"]
    # 抽一个 bin 复核明细里的哈希不是空转的
    for ln in lines:
        h, size, rel = ln.split("  ", 2)
        if rel.endswith("close.day.bin"):
            p = qp.PROVIDER_DIR / rel
            assert qp._sha256(p) == h and p.stat().st_size == int(size)
            break
    else:
        pytest.fail("files.sha256 里一个 close.day.bin 都没有")


def test_sample_codes_are_deterministic(con, sample_codes):
    """抽样必须可复现：同一条查询连跑两次必须给同一批码。

    上一版 `ORDER BY hash(...)` 没有平局兜底，实测**单跑与全套件跑得到的样本不同**
    （`000502.SZ` 与 `001239.SZ` 互换），导致下游用 `sample_codes[0]` 的测试
    在全套件里选到一只已退市的票而变红。加了 `, ts_code` 兜底之后钉住这条。
    """
    a = con.execute(f"""
        SELECT ts_code FROM (
          SELECT ts_code,
                 row_number() OVER (PARTITION BY right(ts_code,2)
                                    ORDER BY hash(ts_code || '{cfg.TRADABILITY_SAMPLE_SEED}'),
                                             ts_code) rn
          FROM (SELECT DISTINCT ts_code FROM read_parquet('{TABLES / 'adj_factor.parquet'}'))
        ) WHERE rn <= 8 ORDER BY ts_code""").fetchall()
    b = con.execute(f"""
        SELECT ts_code FROM (
          SELECT ts_code,
                 row_number() OVER (PARTITION BY right(ts_code,2)
                                    ORDER BY hash(ts_code || '{cfg.TRADABILITY_SAMPLE_SEED}'),
                                             ts_code) rn
          FROM (SELECT DISTINCT ts_code FROM read_parquet('{TABLES / 'adj_factor.parquet'}'))
        ) WHERE rn <= 8 ORDER BY ts_code""").fetchall()
    assert a == b, "同一条抽样查询两次结果不同"
    assert set(r[0] for r in a) <= set(sample_codes)
