# -*- coding: utf-8 -*-
"""卡 2.1b 验收：三路后端分发 + gold 面板 + 双实现互检。

立场沿用前几卡：**不写自证式断言**。后端条数、成分名单、自定义算子清单
一律从因子库 / provider / qlib 现读，不抄实现里的常量再和实现比。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import genebench_config as cfg  # noqa: E402
from reference import factor_exec as fx  # noqa: E402
from snapshots import qlib_provider as qp  # noqa: E402

FREEZE = cfg.FREEZE_DATE.replace("-", "")
VENDOR = cfg.REPO / "reference" / "factorlib_pinned"
UNIVERSE = "csi300"


def _gold_manifest_path() -> Path:
    return fx.GOLD_DIR / UNIVERSE / "manifest.json"


needs_gold = pytest.mark.skipif(
    not _gold_manifest_path().exists(), reason="gold 面板尚未生成"
)


# ------------------------------------------------------------ 后端分布是事实

def test_backend_counts_match_the_recorded_fact():
    """三路后端的条数按 `execution_backend` **字段**，不是按文件。

    644 / 66 / 82 + blocked 24。这不是配置，是我们要记录的事实 ——
    对不上就说明因子库变了，`load_records()` 必须当场抛而不是继续建 gold。
    """
    recs, prov = fx.load_records()
    assert prov["backend_counts"] == {**fx.EXPECTED_BACKENDS,
                                      "<blocked>": fx.EXPECTED_BLOCKED}
    assert sum(fx.EXPECTED_BACKENDS.values()) == 792
    # 判别力：文件口径会给出 644/148/24，与字段口径**必须不同**，
    # 否则这条断言分不出两种口径，等于没测。
    by_file: dict[str, int] = {}
    for r in recs:
        by_file[r["_source_file"]] = by_file.get(r["_source_file"], 0) + 1
    assert by_file["qlib_panel.jsonl"] == 66 + 82, by_file
    assert by_file["qlib_panel.jsonl"] != fx.EXPECTED_BACKENDS["qlib_panel_loader"], (
        "文件口径与字段口径给出了同一个数 —— 那本卡更正的那处口径差异就不存在了")


def test_backend_drift_guard_actually_fires():
    """因子库漂移守门的负例对照：把期望值改一个，`load_records()` 必须抛。

    在子进程里改，主仓零改动。
    """
    code = (
        "import sys; sys.path.insert(0, %r)\n"
        "from reference import factor_exec as fx\n"
        "fx.EXPECTED_BACKENDS['qlib_panel_loader'] = 67\n"
        "try:\n"
        "    fx.load_records()\n"
        "except RuntimeError as e:\n"
        "    print('GUARD_FIRED'); raise SystemExit(0)\n"
        "print('NO_GUARD'); raise SystemExit(1)\n" % str(cfg.REPO)
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       cwd=str(cfg.REPO))
    assert "GUARD_FIRED" in r.stdout, f"{r.stdout}{r.stderr[-800:]}"


# ------------------------------------------------------------ 钉版本参考实现

def test_vendored_factorlib_matches_its_own_pin():
    """仓库里的钉版本副本没有被就地改过。"""
    prov = json.loads((VENDOR / "PROVENANCE.json").read_text(encoding="utf-8"))
    import hashlib
    for name, meta in prov["files"].items():
        got = hashlib.sha256((VENDOR / name).read_bytes()).hexdigest()
        assert got == meta["sha256"], f"{name} 与 PROVENANCE 对不上（被就地改过？）"
    assert prov["platform_git_rev"], "没记上游 git rev —— 钉版本就没钉住"


def test_vendored_factorlib_still_matches_upstream():
    """上游平台代码若漂移，这条**红给你看**。

    红了不是让你去改代码 —— 是让你**有意识地**重新钉版本，并且知道
    重新钉意味着 gold 因子值可能变、τ 要重标。
    """
    src = Path(json.loads((VENDOR / "PROVENANCE.json").read_text())["source_dir"])
    if not src.is_dir():
        pytest.skip(f"上游 {src} 不可读")
    import hashlib
    drift = []
    prov = json.loads((VENDOR / "PROVENANCE.json").read_text())
    for name, meta in prov["files"].items():
        up = src / name
        if not up.exists():
            drift.append(f"{name} 上游已删除")
            continue
        if hashlib.sha256(up.read_bytes()).hexdigest() != meta["sha256"]:
            drift.append(f"{name} 上游已变")
    assert not drift, (
        f"上游 factorlib 漂移：{drift}。重新钉版本前先想清楚 gold 与 τ 要不要重算。")


def test_custom_ops_are_both_needed_and_absent_from_qlib():
    """6 个自定义算子**确实被用到**，且 qlib 内置里**确实没有**。

    两半都要断言：只断"注册了"证明不了什么（注册一个没人用的算子也会绿）；
    只断"被用到"也证明不了什么（如果 qlib 本来就有，就不需要钉版本实现）。
    """
    from qlib.data.ops import OpsList

    from reference.factorlib_pinned import qlib_ops

    recs, _ = fx.load_records()
    used: set[str] = set()
    for r in recs:
        if r.get("executable") and r["execution_backend"] == "qlib_expression":
            used |= set(r.get("custom_ops") or [])
    assert used, "一条 custom_ops 都没用到 —— 这条断言是空的"
    builtin = {o.__name__ for o in OpsList}
    vendored = {o.__name__ for o in qlib_ops.CUSTOM_QLIB_OPS}
    assert used <= vendored, f"用到但钉版本没提供：{sorted(used - vendored)}"
    assert not (used & builtin), (
        f"这些算子 qlib 内置就有，不需要钉版本实现：{sorted(used & builtin)}")


# ------------------------------------------------------------ 数据面来源

def test_qlib_is_pointed_at_the_frozen_provider():
    """执行器看到的日历必须止于冻结线 —— 红线 7 的结构保证在这一层也要成立。"""
    code = (
        "import sys, json; sys.path.insert(0, %r)\n"
        "from reference import factor_exec as fx\n"
        "fx.init_qlib()\n"
        "from qlib.data import D\n"
        "from qlib.config import C\n"
        "cal = D.calendar(start_time='2026-01-01', end_time='2026-12-31', freq='day')\n"
        "print(json.dumps({'max': str(max(cal))[:10], 'n': len(cal),\n"
        "                  'uri': str(C.provider_uri)}))\n" % str(cfg.REPO)
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       cwd=str(cfg.REPO))
    assert r.returncode == 0, r.stderr[-2000:]
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["max"] <= cfg.FREEZE_DATE, out
    assert str(qp.PROVIDER_DIR) in out["uri"], out


# ------------------------------------------------------------ gold 面板

@pytest.fixture(scope="module")
def gold_manifest() -> dict:
    return json.loads(_gold_manifest_path().read_text(encoding="utf-8"))


@needs_gold
def test_gold_covers_all_792_with_zero_backend_failures(gold_manifest):
    """三路各自的产出数必须等于期望数。**任何一路缺一条都要红。**

    实施稿要求"某一路大面积失败先停下汇报"，所以失败必须按后端分开看，
    不能被 792 这个总数稀释。
    """
    for b, exp in fx.EXPECTED_BACKENDS.items():
        got = gold_manifest["per_backend"][b]
        assert got["produced"] == exp, f"{b}: 产出 {got['produced']}/{exp}"
        assert got["failed"] == 0, f"{b} 有 {got['failed']} 条失败"
    assert gold_manifest["write"]["factors"] == 792
    assert not gold_manifest["failures"], gold_manifest["failures"][:5]
    assert not gold_manifest["write"]["all_nan"], (
        f"这些因子在整个窗口上全空：{gold_manifest['write']['all_nan'][:10]}")


@needs_gold
def test_gold_is_float64_not_saturated(gold_manifest):
    """gold 存 float64，并且"若用 float32 会溢出多少格"是**量出来的**。

    首版用 float32，pandas 只发一句 RuntimeWarning，产物里看不出来 ——
    而秩相关对饱和**不是**不变的：一批不同的大数被压成同一个 inf 会并列，Fid% 虚高。
    """
    d = fx.GOLD_DIR / UNIVERSE
    files = sorted(p for p in d.glob("*.parquet"))
    assert len(files) == 792, len(files)
    import pyarrow.parquet as pq
    for p in files[:20] + files[-20:]:
        sch = pq.read_schema(p)
        assert str(sch.field("value").type) == "double", (p.name, sch)
    w = gold_manifest["write"]
    assert "would_overflow_float32" in w, "没有溢出记账 —— 这个坑没有被记住"
    # 判别力：这个坑必须真的存在过，否则这条记账是装饰
    assert w["would_overflow_float32"] > 0 or w["nonfinite_cells"] > 0, (
        "既没有 float32 溢出也没有非有限值 —— 去核实，首版是真的报过 overflow 的")


@needs_gold
def test_gold_dates_never_exceed_the_freeze_line():
    d = fx.GOLD_DIR / UNIVERSE
    for p in sorted(d.glob("*.parquet"))[:40]:
        t = pd.read_parquet(p, columns=["date"])
        if t.empty:
            continue
        assert t["date"].max() <= FREEZE, (p.name, t["date"].max())


@needs_gold
def test_gold_membership_is_point_in_time():
    """抽若干日：gold 当日出现的票必须**正好**是当日成分，不多不少。

    名单从 qlib 现查（`D.list_instruments`），不从 gold 自己推 —— 否则是自证。
    """
    code = (
        "import sys, json; sys.path.insert(0, %r)\n"
        "from reference import factor_exec as fx\n"
        "fx.init_qlib()\n"
        "from qlib.data import D\n"
        "out = {}\n"
        "for day in ('2016-06-30', '2020-03-16', '2024-09-30', '2026-07-31'):\n"
        "    names = D.list_instruments(D.instruments(%r), start_time=day,\n"
        "                               end_time=day, as_list=True)\n"
        "    out[day] = sorted(names)\n"
        "print(json.dumps(out))\n" % (str(cfg.REPO), UNIVERSE)
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       cwd=str(cfg.REPO))
    assert r.returncode == 0, r.stderr[-2000:]
    want = json.loads(r.stdout.strip().splitlines()[-1])
    # 挑一条覆盖率高的因子（$close 的简单变换），它应该在每个成分日都有值
    p = fx.GOLD_DIR / UNIVERSE / "qlib_alpha158.001.parquet"
    if not p.exists():
        p = sorted((fx.GOLD_DIR / UNIVERSE).glob("qlib_alpha158.*.parquet"))[0]
    t = pd.read_parquet(p)
    checked = 0
    for day, names in want.items():
        if not names:
            continue
        got = set(t.loc[t["date"] == day.replace("-", ""), "code"])
        extra = got - set(names)
        assert not extra, f"{day} gold 里有非成分票：{sorted(extra)[:5]}"
        assert len(got) >= 0.9 * len(names), (
            f"{day} gold 只覆盖 {len(got)}/{len(names)} 只成分")
        checked += 1
    assert checked >= 3, f"只核了 {checked} 天"


# ------------------------------------------------------------ 双实现互检

@pytest.fixture(scope="module")
def xcheck() -> dict:
    from reference import factor_crosscheck as fc
    if not fc.REPORT_JSON.exists():
        pytest.skip("互检报告尚未生成")
    return json.loads(fc.REPORT_JSON.read_text(encoding="utf-8"))


def test_crosscheck_has_at_least_30_comparable_factors(xcheck):
    """实施稿要求抽 30 条跨后端可比因子。这是**下界**：能比的全比。"""
    from reference import factor_crosscheck as fc
    assert xcheck["comparable_factors"] >= fc.MIN_COMPARABLE, xcheck["comparable_factors"]
    assert xcheck["meets_requirement"]


def test_crosscheck_pairs_are_genuinely_two_engines(xcheck):
    """互检的两侧必须**不是同一个引擎**，否则秩相关恒等于 1，是自证式比较。

    判别力两半：
    (a) 参与互检的后端里**不能**出现 `qlib_panel_loader`；
    (b) 被排除的那批里**必须真的存在**"两侧字符串完全相同"的实例 ——
        没有实例就说明这条排除规则在当前数据上是空的，那要么数据变了，要么判据写错了。
    """
    assert "qlib_panel_loader" not in xcheck["per_backend"], xcheck["per_backend"]
    assert set(xcheck["per_backend"]) == {"qlib_expression", "qlib_kunquant_loader"}
    same = xcheck["skipped"]["same_engine"]
    assert same, "一条都没排除 —— 这条规则当前是空的"
    assert [x for x in same if x["identical_strings"]], (
        "被排除的 66 条里没有一条 expression == compiled_expression —— "
        "自证式比较的风险不存在了？去核实数据")


# ------------------------------------------------------------ 冻结口径 F-1…F-5

def test_vectorized_spearman_matches_scipy_on_real_data():
    """**F-1 的唯一硬证据**：向量化实现必须逐日等于 `scipy.stats.spearmanr`。

    τ 完全建立在这个函数上，而它为了避开 43 万次 Python 调用重写了 Spearman ——
    重写就必须对照。用**真实 gold 面板**（自带真实的结结构），不用构造数据：
    构造数据里没有结，正好测不到平均法这一半。
    """
    from scipy import stats as st

    from reference import factor_crosscheck as fc

    d = fx.GOLD_DIR / UNIVERSE
    files = sorted(d.glob("*.parquet"))
    if len(files) < 2:
        pytest.skip("gold 不足两条")

    def panel(p):
        t = pd.read_parquet(p)
        t["date"] = pd.to_datetime(t["date"], format="%Y%m%d")
        return t.pivot(index="date", columns="code", values="value")

    a, b = panel(files[0]), panel(files[len(files) // 2])
    idx = a.index.intersection(b.index)[-120:]
    cols = a.columns.intersection(b.columns)
    a, b = a.loc[idx, cols], b.loc[idx, cols]
    rho, n = fc._row_spearman(a, b)

    ties_seen = 0
    compared = 0
    for k, day in enumerate(idx):
        x, y = a.loc[day].to_numpy("float64"), b.loc[day].to_numpy("float64")
        ok = np.isfinite(x) & np.isfinite(y)
        if ok.sum() < fc.MIN_CROSS_SECTION:
            assert not np.isfinite(rho[k])
            continue
        xv, yv = x[ok], y[ok]
        if len(np.unique(xv)) < len(xv) or len(np.unique(yv)) < len(yv):
            ties_seen += 1
        want = st.spearmanr(xv, yv).statistic
        if not np.isfinite(want):
            continue
        assert abs(rho[k] - want) < 1e-9, (str(day), rho[k], want)
        compared += 1
    assert compared >= 50, f"只对照了 {compared} 天"
    assert ties_seen > 0, (
        "这 120 天里一个结都没有 —— 那平均法这一半没被测到，去换一对因子")


def test_tau_is_pooled_not_time_averaged(xcheck):
    """**F-2/F-3**：τ 必须是"全因子 × 全交易日"二维分布的 P10。

    三个数都要在报告里，且差值要显式记账 —— 差很大是"失配集中在少数日子"的信号，
    是另一个故事，不能被一个数盖掉。
    """
    t = xcheck["tau_candidates"]
    for k in ("pooled_factor_x_day_p10", "factor_level_mean_p10",
              "delta_pooled_minus_factor_mean"):
        assert k in t, t
    assert abs((t["pooled_factor_x_day_p10"] - t["factor_level_mean_p10"])
               - t["delta_pooled_minus_factor_mean"]) < 1e-12
    # 判别力：两种取法**必须**给出不同的数，否则这条冻结项区分不出任何东西
    assert t["pooled_factor_x_day_p10"] != t["factor_level_mean_p10"], (
        "两种取法给出同一个数 —— 那 F-2 就分不出'先平均'与'不先平均'，去核实实现")
    assert xcheck["cells_kept"] > 10_000, xcheck["cells_kept"]


def test_degenerate_rule_has_teeth_and_is_documented(xcheck):
    """**F-4**：degenerate 判据必须真的剔掉东西，阈值来源必须记录。"""
    from reference import factor_crosscheck as fc
    m = xcheck["methodology"]
    assert m["degenerate_threshold_source"], "阈值来源没记录"
    assert "N-17" in m["degenerate_threshold_source"], "没写清与 N-17 同源"
    assert xcheck["cells_degenerate"] > 0, (
        "一格都没剔掉 —— 这条判据在当前数据上是空的，去核实")
    c = xcheck["contamination"]
    assert set(c) >= {"tau_before_degenerate_removal", "tau_after_degenerate_removal",
                      "shift", "cells_removed_frac"}
    # 实测的唯一值比例分布要报出来，好让签字人看见 5% 落在哪
    u = xcheck["unique_value_ratio_observed"]
    assert "frac_below_threshold" in u and "p50" in u, u
    assert fc.DEGENERATE_UNIQUE_RATIO == 0.05


def test_degenerate_detector_flags_a_constant_cross_section():
    """判据本身的正例：一个逐日常数的截面必须被标 degenerate。

    真数据里 degenerate 是不是**这个**原因，报告说了算；
    这条只证明检测器不是摆设。
    """
    from reference import factor_crosscheck as fc
    const = np.full((3, 100), 7.0)
    assert (fc._row_nunique(const) == 1).all()
    varied = np.tile(np.arange(100.0), (3, 1))
    assert (fc._row_nunique(varied) == 100).all()
    thr = np.floor(fc.DEGENERATE_UNIQUE_RATIO * 100)
    assert 1 < thr, "阈值太低，常数截面反而过关"


def test_degenerate_rates_reported_on_both_axes(xcheck):
    """**F-5**：剔除率按因子与按日各报一次；全窗 degenerate 的因子要列名。"""
    assert "degenerate_by_factor" in xcheck and "degenerate_by_day" in xcheck
    assert "all_window_degenerate" in xcheck["degenerate_by_factor"]
    assert xcheck["degenerate_by_day"]["worst_10_days"]
    assert set(xcheck["degenerate_by_backend"]) == set(xcheck["per_backend"])


def test_backend_strata_are_reported_without_a_verdict(xcheck):
    """按后端对分层的分布要落盘 —— τ 分不分后端由数据说话，报告不预设结论。"""
    for b, v in xcheck["per_backend"].items():
        assert v["pooled"], b
        assert v["pooled_hist"], b
        assert "tau_pooled_p10" in v, b
        assert v["factors"] > 0
    assert xcheck["per_backend"]["qlib_expression"]["factors"] >= 30
    assert xcheck["per_backend"]["qlib_kunquant_loader"]["factors"] >= 30
