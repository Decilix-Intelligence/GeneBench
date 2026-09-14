# -*- coding: utf-8 -*-
"""卡 1.1-b：公开通道重建链的测试。

两类：

* **私有通道逐字不变** —— 不设 ``GENEBENCH_CHANNEL`` 时，每一个被改过的落点
  都必须等于改动之前那个常量本身。这是本卡的硬判据，所以它是一条一条写死的，
  不是「遍历一下看看形状」。
* **公开分支真的切过去了** —— 而且切换是**由环境变量驱动**的，不是靠调用方记得传参。

外加一条**长牙的**结构测试：``ops/run_public_chain.py`` 用 ops 侧覆盖表接管了
``reference/factor_crosscheck.py`` 与 ``reference/backtest.py``（那两个文件不在
卡 1.1-b 的授权路径里）。覆盖表漏一项的表现是「公开链把互检格写进了私有目录」，
两边都不报错 —— 所以由 :func:`test_channel_overrides_cover_every_private_rooted_path`
反过来从模块里**扫**出所有指向 ``snapshots/v1/`` 的模块级路径来对账。
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import genebench_config as cfg                                    # noqa: E402


@pytest.fixture(autouse=True)
def _clean_channel(monkeypatch):
    """每条测试都从「没设环境变量」开始 —— 否则前一条泄漏的通道会让后一条恒绿。"""
    monkeypatch.delenv(cfg.CHANNEL_ENV, raising=False)


def _mods():
    from reference import calibration as cal
    from reference import epsilon as ep
    from reference import epsilon_dual as ed
    from reference import factor_exec as fx
    return fx, ed, ep, cal


# ------------------------------------------------------------- 私有通道逐字不变

def test_private_paths_are_the_existing_constants():
    """卡 1.1-b 之前这几个落点是写死的常量；现在必须逐字等于当初那个值。"""
    assert cfg.snapshot_root() == cfg.SNAPSHOTS_V1
    assert cfg.gold_dir() == cfg.SNAPSHOTS_V1 / "gold_factors"
    assert cfg.crosscheck_dir() == cfg.SNAPSHOTS_V1 / "crosscheck"
    assert cfg.epsilon_dir() == cfg.SNAPSHOTS_V1 / "epsilon"
    assert cfg.calibration_path() == cfg.SNAPSHOTS_V1 / "calibration.json"
    assert cfg.universe_dir() == cfg.UNIVERSE_DIR
    assert cfg.universe_pit_parquet() == cfg.UNIVERSE_PIT_PARQUET
    assert cfg.crosscheck_report() == cfg.OPS / "acceptance" / "card_2.1b_crosscheck.json"


def test_private_module_attributes_are_the_existing_constants():
    fx, ed, ep, cal = _mods()
    assert fx.GOLD_DIR == cfg.SNAPSHOTS_V1 / "gold_factors"
    assert ed.EPS_DIR == cfg.SNAPSHOTS_V1 / "epsilon"
    assert ed.OUT == cfg.SNAPSHOTS_V1 / "epsilon" / "epsilon_dual.json"
    assert ep.OUT == cfg.SNAPSHOTS_V1 / "epsilon" / "epsilon.json"
    assert cal.OUT == cfg.SNAPSHOTS_V1 / "calibration.json"
    assert fx.provider_paths().provider_dir == cfg.SNAPSHOTS_V1 / "qlib_provider"


# ------------------------------------------------------------------ 公开分支

def test_public_paths_land_under_public_v1(monkeypatch):
    monkeypatch.setenv(cfg.CHANNEL_ENV, "public")
    fx, ed, ep, cal = _mods()
    root = cfg.SNAPSHOTS_PUBLIC
    assert cfg.snapshot_root() == root
    assert fx.GOLD_DIR == root / "gold_factors"
    assert ed.OUT == root / "epsilon" / "epsilon_dual.json"
    assert ep.OUT == root / "epsilon" / "epsilon.json"
    assert cal.OUT == root / "calibration.json"
    assert cfg.crosscheck_report() == root / "crosscheck" / "card_2.1b_crosscheck.json"
    assert fx.provider_paths().provider_dir == cfg.PUBLIC_PROVIDER_DIR


def test_downstream_modules_follow_the_channel_without_being_edited(monkeypatch):
    """``factor_crosscheck`` / ``backtest`` 都写着 ``fx.GOLD_DIR``，一个字没改过。

    ``GOLD_DIR`` 若退回成普通常量，这条会红 —— 那正是「公开互检读了私有 gold」
    这类静默错误的入口。
    """
    from reference import backtest as bt
    from reference import factor_crosscheck as fc
    monkeypatch.setenv(cfg.CHANNEL_ENV, "public")
    assert fc.fx.GOLD_DIR == cfg.SNAPSHOTS_PUBLIC / "gold_factors"
    assert bt.fx.GOLD_DIR == cfg.SNAPSHOTS_PUBLIC / "gold_factors"


def test_unknown_channel_is_refused(monkeypatch):
    """不认识的通道名当场抛，**不静默退回 private**。"""
    monkeypatch.setenv(cfg.CHANNEL_ENV, "publik")
    for fn in (cfg.snapshot_root, cfg.gold_dir, cfg.crosscheck_dir, cfg.epsilon_dir,
               cfg.calibration_path, cfg.universe_dir, cfg.crosscheck_report):
        with pytest.raises(ValueError):
            fn()
    fx, _, _, _ = _mods()
    with pytest.raises(ValueError):
        fx.gold_dir()


def test_module_getattr_still_raises_for_unknown_names():
    fx, ed, ep, cal = _mods()
    for mod in (fx, ed, ep, cal):
        with pytest.raises(AttributeError):
            getattr(mod, "NO_SUCH_ATTRIBUTE_HERE")


def test_env_channel_and_qp_context_agree(monkeypatch):
    """两套通道机制（环境变量 / ``qp.using()`` 上下文）必须指向同一份 provider。"""
    import snapshots.qlib_provider as qp
    fx, _, _, _ = _mods()
    monkeypatch.setenv(cfg.CHANNEL_ENV, "public")
    with qp.using("public"):
        assert fx.provider_paths().provider_dir == qp.paths().provider_dir
        assert fx.provider_paths().tables_dir == qp.paths().tables_dir


# --------------------------------------------------------------- init_qlib 记账

def test_init_qlib_remembers_which_provider_not_just_that_it_ran(monkeypatch):
    """``_INITED`` 必须记「哪一个 provider」。

    只记布尔的话：同一个进程里先跑私有再跑公开，第二次 ``init_qlib()`` 直接返回，
    公开链**静默地**读私有 provider。这里把公开 provider 的 manifest 指到一个
    不存在的路径 —— 记路径的实现会抛「provider 不存在」，记布尔的会一声不吭返回。
    """
    fx, _, _, _ = _mods()
    monkeypatch.setattr(fx, "_INITED", str(cfg.SNAPSHOTS_V1 / "qlib_provider"))

    class _Fake:
        provider_dir = Path("/nonexistent/public/provider")
        manifest = Path("/nonexistent/public/provider/manifest.json")

    monkeypatch.setattr(fx, "provider_paths", lambda ch=None: _Fake())
    with pytest.raises(RuntimeError, match="provider 不存在"):
        fx.init_qlib()


# ------------------------------------------------------------------- 覆盖表

def test_channel_overrides_cover_every_private_rooted_path():
    """**长牙的那条**：从模块里扫出所有指向 `snapshots/v1/` 的模块级路径，逐个对账。

    ``reference/factor_crosscheck.py`` 与 ``reference/backtest.py`` 不在卡 1.1-b
    的授权路径里，公开链靠 ops 侧覆盖表接管它们的落点。这两个模块**将来任何时候**
    新长出一个写死在私有根上的模块级路径，这条测试就红 —— 覆盖表得跟着补，
    而不是等到某次公开跑完才发现产物落在了私有目录里。
    """
    from ops import run_public_chain as rpc

    covered = {(m, a) for (m, a) in rpc._override_map()}
    found: set[tuple[str, str]] = set()
    for modname in ("reference.factor_crosscheck", "reference.backtest"):
        mod = importlib.import_module(modname)
        for name, val in vars(mod).items():
            if name.startswith("__") or not isinstance(val, Path):
                continue
            try:
                val.relative_to(cfg.SNAPSHOTS_V1)
            except ValueError:
                continue
            found.add((modname, name))
    # `REPORT_JSON` 落在 ops/acceptance 下（不在 SNAPSHOTS_V1 里），单独点名。
    found.add(("reference.factor_crosscheck", "REPORT_JSON"))
    assert found <= covered, f"覆盖表漏了：{sorted(found - covered)}"


def test_channel_overrides_restore_even_when_the_body_raises():
    """还原是硬要求：留一个指向公开根的模块常量下去，私有产物会被写进公开目录。"""
    from ops import run_public_chain as rpc
    from reference import factor_crosscheck as fc

    before = fc.CELLS_DIR
    with pytest.raises(ZeroDivisionError):
        with rpc.channel_overrides():
            assert fc.CELLS_DIR == cfg.crosscheck_dir("public")
            1 / 0
    assert fc.CELLS_DIR == before


def test_override_targets_are_public_rooted():
    from ops import run_public_chain as rpc
    for (_m, _a), v in rpc._override_map().items():
        assert str(v).startswith(str(cfg.SNAPSHOTS_PUBLIC)) or v == cfg.crosscheck_report("public")


# ------------------------------------------------------- ic_family 收进 build()

def test_native_ic_family_equals_the_merged_one():
    """``calibration.build()`` 原生写的 ``ic_family`` 与 ``merge_ic_epsilon`` 的产出逐值相同。

    拿**私有通道现成的那份**比 —— 它是卡 1.2 用 `merge_ic_epsilon.py` 合进去的。
    两条路一旦分叉，`calibration.json` 里的带就会与 `ic_epsilon_dual.json` 里的对不上，
    而 S4 的判分照常出数。
    """
    import hashlib

    from ops import merge_ic_epsilon as mie
    calib = cfg.calibration_path("private")
    src = cfg.epsilon_dir("private") / "ic_epsilon_dual.json"
    if not (calib.is_file() and src.is_file()):
        pytest.skip("私有 calibration.json / ic_epsilon_dual.json 不在（本机没跑过 1.2）")
    live = json.loads(calib.read_text(encoding="utf-8"))["epsilon"].get("ic_family")
    assert live is not None, "私有 calibration.json 里没有 ic_family —— 卡 1.2 的产物丢了"
    raw = src.read_bytes()
    built = mie.build_block(json.loads(raw), src_path=src,
                            src_sha256=hashlib.sha256(raw).hexdigest())
    assert built == live


def test_calibration_omits_ic_family_when_the_source_is_absent(monkeypatch, tmp_path):
    """产物不在 → 不写这个键（而不是写一个空块）。空块会让 L3 以为有带。"""
    from reference import calibration as cal
    monkeypatch.setattr(cfg, "epsilon_dir", lambda ch=None: tmp_path)
    assert cal._ic_family() is None


# ------------------------------------------------------ ε 落盘跟着通道走

def test_compare_pairwise_writes_into_the_channel_epsilon_dir(monkeypatch, tmp_path):
    from reference import epsilon_dual as ed
    monkeypatch.setattr(cfg, "epsilon_dir", lambda ch=None: tmp_path)
    for i, bump in ((1, 0.0), (2, 0.01), (3, 0.02)):
        (tmp_path / f"out_b{i}.json").write_text(json.dumps({
            "sharpe_net": 1.0 + bump, "max_drawdown_net": -0.2 - bump,
            "ann_return_net": 0.05 + bump, "turnover_one_way_mean": 0.1 + bump,
            "turnover_two_way_mean": 0.2 + bump, "win_rate_net": 0.5,
        }), encoding="utf-8")
    rep = ed.compare_pairwise({f"B{i}": tmp_path / f"out_b{i}.json" for i in (1, 2, 3)},
                              label="daily", verbose=False)
    assert (tmp_path / "epsilon_dual_daily.json").is_file()
    assert rep["n_implementations"] == 3
    # win_rate_net 三份完全相同 → 无自由度，**不得用别的指标的 ε 代填**
    assert "win_rate_net" in rep["no_freedom"]


def test_write_gold_can_land_somewhere_else(tmp_path):
    """``write_gold(root=…)`` 是私有不变性证据的取法：重跑一遍但不碰既有产物。"""
    import numpy as np
    import pandas as pd
    from reference import factor_exec as fx

    idx = pd.to_datetime(["2026-07-29", "2026-07-30"])
    cols = ["SH600000", "SZ000001"]
    panels = {"f1": pd.DataFrame([[1.0, 2.0], [3.0, 4.0]], index=idx, columns=cols)}
    mask = pd.DataFrame(True, index=idx, columns=cols)
    st = fx.write_gold("csi300", panels, mask, "2026-07-29", "2026-07-30",
                       verbose=False, root=tmp_path)
    assert st["factors"] == 1 and st["rows"] == 4
    assert (tmp_path / "csi300" / "f1.parquet").is_file()
    assert not (fx.gold_dir() / "csi300" / "f1.parquet").is_file(), "写到既有 gold 里去了"
    assert np.isclose(pd.read_parquet(tmp_path / "csi300" / "f1.parquet")["value"].sum(), 10.0)


# ------------------------------------------------------------------ 链条形状

def test_every_step_has_a_handler_and_a_marker():
    from ops import run_public_chain as rpc
    assert set(rpc.STEPS) == set(rpc.HANDLERS)
    for s in rpc.STEPS:
        assert rpc.state_marker(s).parent == cfg.PUBLIC_STATE_DIR


def test_chain_refuses_to_run_on_the_private_channel(monkeypatch):
    """搞错通道时**必须报错**，不能悄悄把公开链跑到私有根上去。"""
    from ops import run_public_chain as rpc
    monkeypatch.setenv(cfg.CHANNEL_ENV, "private")
    with pytest.raises(SystemExit, match="只跑公开通道"):
        rpc.main(["--dry-run"])


# --------------------------------------------------------- 公开产物（跑完才有）

def _public_calibration():
    p = cfg.calibration_path("public")
    if not p.is_file():
        pytest.skip(f"公开通道还没跑到 calibration（{p} 不存在）")
    return json.loads(p.read_text(encoding="utf-8"))


def test_public_calibration_has_tau_epsilon_and_ic_family():
    d = _public_calibration()
    assert 0.0 < d["tau"]["value"] <= 1.0
    assert set(d["epsilon"]["by_frequency"]) == {"daily", "weekly", "monthly"}
    assert d["epsilon"]["ic_family"]["by_holding_period"].keys() >= {"1", "5", "20"}
    assert str(cfg.SNAPSHOTS_PUBLIC) in d["provider"]["dir"]


def test_public_calibration_keeps_the_same_structural_verdicts():
    """卡 2.5 §10：**结构性结论**不许因为换了数据源就改。

    daily 可标定、weekly/monthly 不可用 —— 与私有通道同一条分档结论。
    数字可以动（那是数据差异），结论动了就是要单独上报的事。
    """
    d = _public_calibration()
    bf = d["epsilon"]["by_frequency"]
    assert bf["daily"]["usable"] is True
    assert bf["weekly"]["usable"] is False
    assert bf["monthly"]["usable"] is False


# ------------------------------------------------------- 面板暂存面（内存压不住时）

def test_importing_the_chain_module_does_not_flip_the_process_channel(monkeypatch):
    """**import 期不许改进程环境。**

    `ops/run_public_chain.py` 最初把 ``os.environ.setdefault("GENEBENCH_CHANNEL",
    "public")`` 写在模块顶上。表现：任何 import 了它的进程整个翻到公开通道 ——
    同一次 pytest 里跑在它后面的 `ops/test_calibration.py` 于是去读
    `snapshots/public_v1/calibration.json`，17 条 ERROR，而两个模块各自单跑都绿。
    这条测试把「通道只能由调用方设」钉住。
    """
    monkeypatch.delenv(cfg.CHANNEL_ENV, raising=False)
    import ops.run_public_chain as rpc                                # noqa: F401
    importlib.reload(rpc)
    import os
    assert cfg.CHANNEL_ENV not in os.environ, (
        "import ops.run_public_chain 之后进程环境里多了 GENEBENCH_CHANNEL —— "
        "这会把同进程里别的模块一起拖到公开通道上去")
    assert cfg.channel() == "private"


def _fake_panel(n_days: int = 40, n_codes: int = 7):
    import numpy as np
    import pandas as pd
    idx = pd.bdate_range("2020-01-01", periods=n_days, name="datetime")
    cols = pd.Index([f"SH60{i:04d}" for i in range(n_codes)], name="instrument")
    rng = np.random.default_rng(20260907)
    v = rng.standard_normal((n_days, n_codes))
    v[3, 2] = np.nan
    v[10, :] = np.nan
    v[20, 1] = np.inf                      # gold 真的会存 inf，暂存面不许把它吃掉
    v[21, 1] = 1e300                       # float32 会饱和的量级
    return pd.DataFrame(v, index=idx, columns=cols)


def test_spill_store_round_trips_the_frame_exactly(tmp_path):
    """暂存面的判据是「放进去什么、取出来就是什么」—— dtype / index / columns / NaN / inf。"""
    from reference import factor_exec as fx
    import pandas as pd

    f = _fake_panel()
    s = fx.SpillPanelStore(tmp_path / "spill")
    s.put("x.001", f)
    back = s.get("x.001")
    pd.testing.assert_frame_equal(back, f, check_exact=True, check_dtype=True,
                                  check_names=True, check_freq=True)
    assert back.to_numpy().tobytes() == f.to_numpy().tobytes()   # 连 NaN 的位型都一样
    s.cleanup()
    assert not (tmp_path / "spill" / "x.001.pkl").exists()


def test_two_stores_write_byte_identical_gold(tmp_path):
    """**硬判据**：走内存和走暂存盘，`write_gold` 落出来的 parquet 逐字节相同。

    暂存面只决定面板在被 `write_gold` 消费之前放在哪；它一旦改动了数，
    表现是「gold 照样是一堆看着正常的 parquet，只是数变了」—— 没有任何一处会报错。
    """
    import hashlib
    import pandas as pd
    from reference import factor_exec as fx

    panels = {f"x.{i:03d}": _fake_panel() for i in (1, 2, 3)}
    cols = sorted({c for f in panels.values() for c in f.columns})
    idx = panels["x.001"].index
    mask = pd.DataFrame(True, index=idx, columns=cols)
    mask.iloc[5, 0] = False                # 掩膜真的要挖掉一些格

    mem = fx.PanelStore()
    spl = fx.SpillPanelStore(tmp_path / "spill")
    for k, v in panels.items():
        mem.put(k, v)
        spl.put(k, v)
    assert mem.ids() == spl.ids()
    assert mem.columns_union() == spl.columns_union()

    outs = {}
    for name, store in (("mem", mem), ("spill", spl)):
        root = tmp_path / name
        st = fx.write_gold("csi300", store, mask, str(idx[0].date()), str(idx[-1].date()),
                           verbose=False, root=root)
        outs[name] = (st, {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in sorted((root / "csi300").glob("*.parquet"))})
        assert len(store) == 0, "write_gold 应该写完一个放一个"
    assert outs["mem"][1] == outs["spill"][1] and len(outs["mem"][1]) == 3
    assert outs["mem"][0] == outs["spill"][0]


def test_write_gold_still_takes_a_plain_dict(tmp_path):
    """向后兼容：既有调用方传的是 dict，不能因为引入 store 就要求他们改。"""
    import pandas as pd
    from reference import factor_exec as fx

    panels = {"x.001": _fake_panel()}
    idx = panels["x.001"].index
    mask = pd.DataFrame(True, index=idx, columns=sorted(panels["x.001"].columns))
    st = fx.write_gold("csi300", panels, mask, str(idx[0].date()), str(idx[-1].date()),
                       verbose=False, root=tmp_path)
    assert st["factors"] == 1
    assert panels, "传 dict 时不许把调用方的 dict 掏空"


def test_eval_sink_replaces_the_returned_dict(monkeypatch):
    """给了 sink 就**边算边交出去**：返回的 dict 必须是空的，否则等于攒了两份。"""
    from reference import factor_exec as fx
    import inspect
    for fn in (fx.eval_expression, fx.eval_panel_and_kunquant):
        assert "sink" in inspect.signature(fn).parameters
    src = inspect.getsource(fx.run)
    assert "sink=panels.put" in src, "run() 必须把 store 接到求值出口上"
    assert "panels.update(" not in src, "run() 不该再往 dict 里 update 面板"
