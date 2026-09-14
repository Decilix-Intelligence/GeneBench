# -*- coding: utf-8 -*-
"""卡 2.1b：792 条因子的参考执行器（oracle），三路后端分发。

    cd $REPO && ulimit -n 8192 && $GENEBENCH_ROOT/env/bin/python -m reference.factor_exec --help

**后端分布是要记录的事实，不是可以调整的实现细节。** 三路各自的记录数按
``execution_backend`` 字段（不是按文件）：``qlib_expression`` 644 /
``qlib_panel_loader`` 66 / ``qlib_kunquant_loader`` 82，另有 24 条 blocked。
任何一路大面积失败都**停下汇报**，不自行降级到别的后端 —— 降级等于改口径。

三路各是什么（实测，不是照文档）：

* ``qlib_expression``（644）—— ``compiled_expression`` 是**可直接求值的 qlib 表达式**，
  但用到 6 个 qlib 内置没有的算子（``CnSma`` 80 次 / ``PairMax`` 71 / ``PairMin`` 8 /
  ``DecayLinear`` 3 / ``DaysSinceMax`` 2 / ``DaysSinceMin`` 2）。
  这些算子的实现取自**钉版本**的 ``reference/factorlib_pinned/qlib_ops.py``。
* ``qlib_panel_loader``（66）—— ``compiled_expression`` 是**源方言原文**（大写），
  不是 qlib 表达式：``(-1 * CORR(RANK(DELTA(LOG(VOLUME),1)), RANK((CLOSE-OPEN)/OPEN), 6))``。
  要截面语义（``RANK`` 139 次）才能求值，走钉版本的 ``PanelFormulaEvaluator``。
* ``qlib_kunquant_loader``（82）—— ``compiled_expression`` 是**模块路径**
  ``KunQuant.predefined.Alpha101.alphaNNN``，由 KunQuant JIT 编译成 C++ 后一次算完 101 条。
  ``alpha001`` 的输出**减 0.5**（因子库自己的口径，82 条的 ``translation_notes`` 都写了）。

**为什么用钉版本的平台实现，而不是自己重写**：那 66 条方言公式的语义
（``MAX(x, 3)`` 是逐元素还是滚动？）与 ``alpha001 -0.5`` 都是**因子库自己的口径**。
重写等于凭空造出第二套语义，而 τ 恰恰是在"两个实现有多一致"上标定的 ——
用自造的第二套去标 τ，标出来的是我们自己的实现分歧，不是被测系统的。

**数据只从冻结 provider 来。** ``qlib.init(provider_uri=$SNAPSHOTS/v1/qlib_provider)``，
所以日历物理上止于冻结线，红线 7 是结构保证。

**gold 因子值算到冻结线当天**（2026-07-31）——右端约束是给**前向收益**的，不是给因子值的。
三个持有期的可用右端记在 manifest 里，由评分器硬拦，见
``snapshots.qlib_provider.evaluation_right_edges()``。
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

import genebench_config as cfg
from snapshots import qlib_provider as qp

# ---------------------------------------------------------------- 落点与常量

#: **``GOLD_DIR`` 是一个通道相关的模块属性**（卡 1.1-b），由下面的 ``__getattr__`` 给出：
#: 不设 ``GENEBENCH_CHANNEL`` 时它逐字等于既有的 ``cfg.SNAPSHOTS_V1 / "gold_factors"``，
#: 设成 ``public`` 时指向 ``snapshots/public_v1/gold_factors``。
#:
#: 用 PEP 562 的模块级 ``__getattr__`` 而不是改成函数，是为了让**下游一个字都不用改**：
#: ``reference/factor_crosscheck.py`` / ``reference/backtest.py`` / ``ops/ic_epsilon.py``
#: 都写着 ``fx.GOLD_DIR``。逐个去改的话，漏掉一处的表现是
#: 「公开通道的互检读了私有 gold」—— 秩相关照样算得出来，只是算的是另一条通道的数。
#: ``monkeypatch.setattr(fx, "GOLD_DIR", ...)`` 仍然有效（真全局会遮蔽 ``__getattr__``）。
FACTOR_LIB: Path = cfg.LAKE / "reference" / "factor_library" / "compiled"
LIB_FILES: tuple[str, ...] = ("qlib_native.jsonl", "qlib_panel.jsonl", "blocked.jsonl")

#: 与钉版本 loader 的默认一致。改它会改变所有滚动算子的暖机长度 = 改口径。
WARMUP_DAYS: int = 600

#: 三路后端的**实测**记录数。不是配置项 —— 对不上就说明因子库变了，必须停下。
EXPECTED_BACKENDS: dict[str, int] = {
    "qlib_expression": 644,
    "qlib_panel_loader": 66,
    "qlib_kunquant_loader": 82,
}
EXPECTED_BLOCKED: int = 24

#: 一次喂给 ``D.features`` 的表达式条数。纯性能参数，不影响数值。
EXPRESSION_BATCH: int = 40

__all__ = ["load_records", "init_qlib", "run", "GOLD_DIR", "EXPECTED_BACKENDS",
           "gold_dir", "provider_paths", "PanelStore", "SpillPanelStore"]


# ---------------------------------------------------------------- 面板暂存面


class PanelStore:
    """求值产出的因子面板的暂存面，``write_gold`` 从这里逐个取走。

    这一版把面板留在内存里 —— 与本类引入之前那个 ``dict[str, DataFrame]``
    **逐字等价**：``ids()`` 就是原来的 ``sorted(panels)``，``columns_union()``
    就是原来那句 ``sorted({c for f in panels.values() for c in f.columns})``。
    唯一多出来的是 :meth:`release`：``write_gold`` 写完一个因子就把它放掉，
    于是落盘阶段内存是**往下走**的，不再是「全程压着峰值」。
    """

    def __init__(self) -> None:
        self._panels: dict[str, pd.DataFrame] = {}

    def put(self, fid: str, frame: pd.DataFrame) -> None:
        self._panels[fid] = frame

    def ids(self) -> list[str]:
        """排序后的因子 id。``write_gold`` 原来就是按 ``sorted(...)`` 走的，顺序不变。"""
        return sorted(self._panels)

    def columns_union(self) -> list[str]:
        """全部面板的列并集 —— 成分掩膜的列轴。"""
        return sorted({c for f in self._panels.values() for c in f.columns})

    def get(self, fid: str) -> pd.DataFrame:
        return self._panels[fid]

    def release(self, fid: str) -> None:
        """写完就放。内存版是丢引用，落盘版是删临时文件。"""
        self._panels.pop(fid, None)

    def cleanup(self) -> None:
        self._panels.clear()

    def __len__(self) -> int:
        return len(self._panels)

    def __contains__(self, fid: object) -> bool:
        return fid in self._panels


class SpillPanelStore(PanelStore):
    """把每个面板**即时落到临时盘**，内存里只留列名。

    **为什么要有它。** ``run()`` 原来把 792 个面板同时压在内存里：csi1000 实测
    常驻约 22 GiB，而 f01 只有 30 GiB 且是共用机。2026-09-07 05:20Z 内核就是这么
    把公开通道那一次 gold 收走的（anon-rss 22 GB，``exit=137``）；被杀之前它已经
    退化到「写一个 parquet 要一小时」（私有那次是 7.8 秒），也就是说换页早就把它
    拖垮了 —— **不是慢，是在换页里空转**。开了本类之后峰值只剩「原始面板 + 手里
    这一批」。

    **为什么用 pickle 而不是 parquet / npy。** 这是**中间暂存**，不是产物，判据是
    「放进去什么、取出来就是什么」：dtype、index、columns、NaN 一个不差。
    parquet 要在 index / columns / dtype 上来回转换，``np.save`` 会把多 dtype 的帧
    压成一个公共 dtype —— 两条路都可能**悄悄改掉**最后落盘的数，而 gold 出来照样
    是一堆看着正常的 parquet。``ops/test_public_chain.py`` 里有一条拿真形状的帧走
    两条路比 ``to_parquet`` 字节的测试钉住这件事。

    落点由调用方给（``run(spill_dir=...)`` / ``--spill-dir``），用完 :meth:`cleanup`
    自己删干净；文件一律 0600（红线 5）。
    """

    def __init__(self, spill_dir: "str | Path") -> None:
        super().__init__()
        self._dir = Path(spill_dir)
        cfg.create_dir(self._dir)
        self._cols: dict[str, tuple] = {}

    def _path(self, fid: str) -> Path:
        return self._dir / f"{fid}.pkl"

    def put(self, fid: str, frame: pd.DataFrame) -> None:
        dst = self._path(fid)
        frame.to_pickle(dst, compression=None, protocol=5)
        dst.chmod(0o600)
        self._cols[fid] = tuple(frame.columns)

    def ids(self) -> list[str]:
        return sorted(self._cols)

    def columns_union(self) -> list[str]:
        return sorted({c for cs in self._cols.values() for c in cs})

    def get(self, fid: str) -> pd.DataFrame:
        return pd.read_pickle(self._path(fid), compression=None)

    def release(self, fid: str) -> None:
        self._path(fid).unlink(missing_ok=True)
        self._cols.pop(fid, None)

    def cleanup(self) -> None:
        for fid in list(self._cols):
            self.release(fid)
        self._cols.clear()
        try:
            self._dir.rmdir()
        except OSError:                     # 目录里还有别人的东西就留着，不越权删
            pass

    def __len__(self) -> int:
        return len(self._cols)

    def __contains__(self, fid: object) -> bool:
        return fid in self._cols


def gold_dir(ch: "str | None" = None) -> Path:
    """该通道的 gold 因子根。private 返回的就是既有那个路径。"""
    return cfg.gold_dir(ch)


def provider_paths(ch: "str | None" = None) -> "qp.ProviderPaths":
    """该通道的 provider 上下文。private 返回的就是 :data:`snapshots.qlib_provider.PRIVATE_PATHS`。

    **不走 ``qp.paths()``**：那个是 ``qp.using()`` 的进程内上下文（卡 1.1-a 建 provider 时用），
    而这条链要由 ``GENEBENCH_CHANNEL`` 直接驱动 —— 两者在
    ``ops/test_public_chain.py::test_env_channel_and_qp_context_agree`` 里对齐。
    """
    return qp.PATHS_BY_CHANNEL[cfg.assert_channel(ch)]


def __getattr__(name: str):
    """PEP 562：``GOLD_DIR`` 按通道现算。其余属性照常报 AttributeError。"""
    if name == "GOLD_DIR":
        return gold_dir()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ---------------------------------------------------------------- 因子库

def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_records() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """读 792 条可执行 + 24 条 blocked，并**当场核对后端分布**。

    分布对不上就抛 —— 因子库是外部产物，它变了我们必须知道，
    而不是让 gold 悄悄地建在另一个池子上（τ 的锚点就是这个池子）。
    """
    recs: list[dict[str, Any]] = []
    prov: dict[str, Any] = {"files": {}}
    for name in LIB_FILES:
        p = FACTOR_LIB / name
        n = 0
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                r["_source_file"] = name
                recs.append(r)
                n += 1
        prov["files"][name] = {"rows": n, "sha256": _sha256(p)}
    counts: dict[str, int] = {}
    for r in recs:
        counts[r.get("execution_backend") or "<blocked>"] = (
            counts.get(r.get("execution_backend") or "<blocked>", 0) + 1
        )
    got = {k: v for k, v in counts.items() if k in EXPECTED_BACKENDS}
    if got != EXPECTED_BACKENDS or counts.get("<blocked>") != EXPECTED_BLOCKED:
        raise RuntimeError(
            f"因子库的后端分布变了：实测 {counts}，期望 {EXPECTED_BACKENDS} + "
            f"blocked {EXPECTED_BLOCKED}。**停下汇报**，不要自行调整常量 —— "
            f"池子变动会让在旧池子上标定并签字的 τ 失去锚点。"
        )
    prov["backend_counts"] = counts
    return recs, prov


def executable(recs: Iterable[dict[str, Any]], backend: str) -> list[dict[str, Any]]:
    return [r for r in recs if r.get("executable") and r.get("execution_backend") == backend]


# ---------------------------------------------------------------- qlib

#: 已经 init 过的 provider 目录（空串 = 还没 init）。
#:
#: **刻意不是布尔**（卡 1.1-b）：一个进程里先跑私有再跑公开时，只记布尔会让第二次
#: ``init_qlib()`` 直接返回，于是公开链**静默地**读私有 provider —— 那种错不报错，
#: 表现只是「公开 gold 的数和私有一模一样」。
_INITED: str = ""


def init_qlib(ch: "str | None" = None) -> None:
    """把 qlib 指向**该通道的冻结 provider**，并注册钉版本的 6+2 个自定义算子。

    通道由 ``GENEBENCH_CHANNEL`` 决定；不设时与本参数引入之前逐字相同。
    """
    global _INITED
    pp = provider_paths(ch)
    if _INITED == str(pp.provider_dir):
        return
    import qlib

    from reference.factorlib_pinned import qlib_ops

    if not pp.manifest.exists():
        raise RuntimeError(f"provider 不存在：{pp.provider_dir}。"
                           f"先跑卡 2.1a（公开通道跑 ops/build_public_channel.py）。")
    qlib.init(
        provider_uri=str(pp.provider_dir), region="cn",
        expression_cache=None, dataset_cache=None, redis_port=-1,
        custom_ops=list(qlib_ops.CUSTOM_QLIB_OPS),
    )
    _INITED = str(pp.provider_dir)


def membership_mask(universe: str, start: str, end: str, index, columns) -> pd.DataFrame:
    """逐日成分掩膜（PIT）。``D.list_instruments`` 给的是区段，这里折成 日×票 的布尔面板。"""
    from qlib.data import D

    spans = D.list_instruments(D.instruments(universe), start_time=start, end_time=end,
                               as_list=False)
    mask = pd.DataFrame(False, index=index, columns=columns)
    for code, segs in spans.items():
        if code not in mask.columns:
            continue
        col = np.zeros(len(index), dtype=bool)
        for lo, hi in segs:
            col |= (index >= pd.Timestamp(lo)) & (index <= pd.Timestamp(hi))
        mask[code] = col
    return mask


# ---------------------------------------------------------------- 三路求值

def eval_expression(recs: list[dict[str, Any]], universe: str, start: str, end: str,
                    *, verbose: bool = True, sink: "Any | None" = None
                    ) -> tuple[dict[str, pd.DataFrame], list[tuple[str, str]]]:
    """`qlib_expression`：直接喂 qlib 表达式引擎，分批以控内存。

    Args:
        sink: ``sink(fid, frame)``。给了就**边算边交出去**（``run()`` 交给
            :class:`PanelStore`），返回的 dict 是空的；不给就照旧攒在 dict 里返回。
    """
    from qlib.data import D

    out: dict[str, pd.DataFrame] = {}
    emit = sink if sink is not None else out.__setitem__
    failures: list[tuple[str, str]] = []
    inst = D.instruments(universe)
    for i in range(0, len(recs), EXPRESSION_BATCH):
        batch = recs[i:i + EXPRESSION_BATCH]
        exprs = [r["compiled_expression"] for r in batch]
        try:
            df = D.features(inst, exprs, start_time=start, end_time=end, freq="day")
        except Exception as exc:            # 整批失败 → 退化成逐条，定位到具体因子
            for r in batch:
                try:
                    d1 = D.features(inst, [r["compiled_expression"]],
                                    start_time=start, end_time=end, freq="day")
                    emit(r["id"], _to_panel(d1.iloc[:, 0]))
                except Exception as e2:
                    failures.append((r["id"], f"{type(e2).__name__}: {e2}"))
            if verbose:
                print(f"    批 {i} 整批失败（{type(exc).__name__}），已逐条重试", flush=True)
            continue
        for r, col in zip(batch, df.columns):
            emit(r["id"], _to_panel(df[col]))
        del df
        if verbose:
            print(f"    表达式 {min(i + EXPRESSION_BATCH, len(recs))}/{len(recs)}", flush=True)
    return out, failures


def _to_panel(series: pd.Series) -> pd.DataFrame:
    """qlib 出的 (instrument, datetime) 长表 → 日 × 票 面板。"""
    s = series
    if s.index.names == ["instrument", "datetime"]:
        s = s.swaplevel().sort_index()
    s.index = s.index.set_names(["datetime", "instrument"])
    return s.unstack("instrument").sort_index()


def eval_panel_and_kunquant(recs_panel: list[dict[str, Any]], recs_kq: list[dict[str, Any]],
                            universe: str, start: str, end: str, *, verbose: bool = True,
                            sink: "Any | None" = None
                            ) -> tuple[dict[str, pd.DataFrame], list[tuple[str, str]]]:
    """`qlib_panel_loader` + `qlib_kunquant_loader`：共用一份原始面板。

    Args:
        sink: 同 :func:`eval_expression` —— 给了就边算边交出去。
    """
    from qlib.data import D

    from reference.factorlib_pinned import qlib_loader
    from reference.factorlib_pinned.formula import parse_formula

    out: dict[str, pd.DataFrame] = {}
    emit = sink if sink is not None else out.__setitem__
    failures: list[tuple[str, str]] = []
    panels = qlib_loader._raw_panels(D.instruments(universe), start, end, WARMUP_DAYS)
    if verbose:
        print(f"    原始面板 {panels['CLOSE'].shape}（含 {WARMUP_DAYS} 天暖机）", flush=True)

    if recs_kq:
        names = {str(r["name"]) for r in recs_kq}
        try:
            wq = qlib_loader._worldquant_panels(panels, names)
            by_name = {str(r["name"]): r["id"] for r in recs_kq}
            produced = sorted(wq)
            missing = sorted(names - set(wq))
            # pop 而不是遍历：KunQuant 一次吐 82 张面板，交出去一张就放一张，
            # 否则 sink 落盘的意义被这一坨抵消掉。
            for nm in produced:
                frame = wq.pop(nm)
                if nm in by_name:
                    emit(by_name[nm], frame)
                del frame
            for nm in missing:
                failures.append((by_name.get(nm, nm), "KunQuant 未产出该 alpha"))
            if verbose:
                print(f"    KunQuant {len(produced)}/{len(recs_kq)}", flush=True)
        except Exception as exc:
            for r in recs_kq:
                failures.append((r["id"], f"KunQuant 整体失败 {type(exc).__name__}: {exc}"))

    if recs_panel:
        ev = qlib_loader.PanelFormulaEvaluator(panels)
        for n, r in enumerate(recs_panel, 1):
            try:
                emit(r["id"], ev.evaluate(parse_formula(r["compiled_expression"])))
            except Exception as exc:
                failures.append((r["id"], f"{type(exc).__name__}: {exc}"))
            if verbose and n % 20 == 0:
                print(f"    panel {n}/{len(recs_panel)}", flush=True)
    return out, failures


# ---------------------------------------------------------------- 落盘

def write_gold(universe: str, panels: "dict[str, pd.DataFrame] | PanelStore",
               mask: pd.DataFrame,
               start: str, end: str, *, verbose: bool = True,
               root: "Path | None" = None) -> dict[str, Any]:
    """每因子一个 parquet，长表 ``(date, code, value)``，**只留当日在成分内的格**。

    Args:
        panels: 普通 dict（照旧）或 :class:`PanelStore`。给 store 时**写完一个就放掉
            一个**，落盘阶段的内存是往下走的。
        root: 落点根。``None`` = 该通道的 gold 根。给一个别的路径可以在**不碰既有产物**
            的前提下重跑一遍做逐字节比对（卡 1.1-b 的私有通道不变性证据就是这么取的）。
    """
    d = (root or gold_dir()) / universe
    cfg.create_dir(d)
    lo, hi = pd.Timestamp(start), pd.Timestamp(end)
    stats = {"factors": 0, "rows": 0, "bytes": 0, "all_nan": [],
             "nonfinite_cells": 0, "factors_with_nonfinite": {},
             "would_overflow_float32": 0, "factors_overflowing_float32": {}}
    store = panels if isinstance(panels, PanelStore) else None
    ids = store.ids() if store is not None else sorted(panels)
    total = len(ids)
    for n, fid in enumerate(ids, 1):
        frame = store.get(fid) if store is not None else panels[fid]
        f = frame.reindex(index=mask.index, columns=mask.columns)
        f = f.where(mask)
        f = f.loc[(f.index >= lo) & (f.index <= hi)]
        # 先扔掉整列全空的票再 stack：reindex 会造出一批全 NaN 列，
        # pandas 对它们发 FutureWarning 且未来会改 dtype 推断 —— 扔掉既静音又更快。
        f = f.dropna(axis=1, how="all")
        if f.empty:
            stacked = pd.Series(dtype="float64")
        else:
            # dropna 只丢 NaN（= 当日无法计算）；inf 会**留下**，见下面的记账。
            stacked = f.stack(future_stack=True).dropna()
        if stacked.empty:
            stats["all_nan"].append(fid)
        vals = stacked.to_numpy(dtype="float64")
        # **不静默截断也不静默丢弃。** 参考实现真的会吐 inf（除零、幂爆炸），
        # 那是它的诚实输出；gold 是数据层，筛选留给评分层（同 ambiguous 区段的处理）。
        bad = int((~np.isfinite(vals)).sum())
        if bad:
            stats["nonfinite_cells"] += bad
            stats["factors_with_nonfinite"][fid] = bad
        # float32 会把这些值饱和成 inf —— 首版就是这么写的，pandas 只发一句
        # "overflow encountered in cast" 的 RuntimeWarning，产物里看不出来。
        # 秩相关对饱和**不是**不变的：一批不同的大数会被压成同一个 inf 而并列，
        # Fid% 会因此虚高。所以 gold 存 float64，并把"若用 float32 会溢出多少格"记账。
        ovf = int(np.sum(np.isfinite(vals) & (np.abs(vals) > np.finfo("float32").max)))
        if ovf:
            stats["would_overflow_float32"] += ovf
            stats["factors_overflowing_float32"][fid] = ovf
        tbl = pd.DataFrame({
            "date": (stacked.index.get_level_values(0).strftime("%Y%m%d")
                     if len(stacked) else pd.Index([], dtype="object")),
            "code": (stacked.index.get_level_values(1).astype(str)
                     if len(stacked) else pd.Index([], dtype="object")),
            "value": vals,
        })
        p = d / f"{fid}.parquet"
        tbl.to_parquet(p, index=False, compression="zstd")
        p.chmod(0o600)
        stats["factors"] += 1
        stats["rows"] += len(tbl)
        stats["bytes"] += p.stat().st_size
        del frame, f, stacked, vals, tbl
        if store is not None:
            store.release(fid)
        if verbose and n % 100 == 0:
            print(f"    落盘 {n}/{total}", flush=True)
    return stats


# ---------------------------------------------------------------- 编排

def run(universe: str, start: str, end: str, *, verbose: bool = True,
        backends: "tuple[str, ...] | None" = None,
        gold_root: "Path | None" = None,
        spill_dir: "Path | None" = None) -> dict[str, Any]:
    """一个宇宙的 gold。

    Args:
        spill_dir: 给了就把求值出来的面板**即时落到这个临时目录**
            （:class:`SpillPanelStore`），峰值内存从「全部面板」降到「手里这一批」。
            产物逐字节不变 —— 暂存面只决定面板在被 ``write_gold`` 消费之前放在哪。
    """
    cfg.harden_umask()
    t0 = time.time()
    ch = cfg.channel()
    root = gold_root or gold_dir(ch)
    recs, prov = load_records()
    init_qlib(ch)
    from qlib.data import D

    want = backends or tuple(EXPECTED_BACKENDS)
    ex = executable(recs, "qlib_expression") if "qlib_expression" in want else []
    pl = executable(recs, "qlib_panel_loader") if "qlib_panel_loader" in want else []
    kq = executable(recs, "qlib_kunquant_loader") if "qlib_kunquant_loader" in want else []
    if verbose:
        print(f"[{universe}] {start} … {end}；"
              f"expression {len(ex)} / panel {len(pl)} / kunquant {len(kq)}", flush=True)

    panels: PanelStore = SpillPanelStore(spill_dir) if spill_dir else PanelStore()
    failures: list[tuple[str, str]] = []
    t_ex = t_pk = 0.0
    if ex:
        t = time.time()
        _, f1 = eval_expression(ex, universe, start, end, verbose=verbose, sink=panels.put)
        failures += f1; t_ex = time.time() - t
    if pl or kq:
        t = time.time()
        _, f2 = eval_panel_and_kunquant(pl, kq, universe, start, end, verbose=verbose,
                                        sink=panels.put)
        failures += f2; t_pk = time.time() - t

    # 后端级失败率：任何一路大面积失败都要显式地红，不能被总数稀释。
    per_backend: dict[str, dict[str, int]] = {}
    fid2backend = {r["id"]: r["execution_backend"] for r in recs if r.get("executable")}
    for b, want_n in EXPECTED_BACKENDS.items():
        if b not in want:
            continue
        got = sum(1 for fid in panels.ids() if fid2backend.get(fid) == b)
        per_backend[b] = {"expected": want_n, "produced": got, "failed": want_n - got}

    cal = D.calendar(start_time=start, end_time=end, freq="day")
    index = pd.DatetimeIndex(cal)
    cols = panels.columns_union()
    mask = membership_mask(universe, start, end, index, cols)
    if verbose:
        print(f"    成分掩膜 {mask.shape}，日均成分 {mask.sum(axis=1).mean():.1f}", flush=True)
    try:
        wstats = write_gold(universe, panels, mask, start, end, verbose=verbose, root=root)
    finally:
        panels.cleanup()

    pp = provider_paths(ch)
    manifest = {
        "card": "2.1b",
        "channel": ch,
        "universe": universe, "start": start, "end": end,
        "built_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "provider": {"dir": str(pp.provider_dir),
                     "digest": json.loads(pp.manifest.read_text())["digest"]["files_sha256_digest"]},
        "factor_library": prov,
        "vendored_factorlib": json.loads(
            (cfg.REPO / "reference" / "factorlib_pinned" / "PROVENANCE.json").read_text()),
        "warmup_days": WARMUP_DAYS,
        "per_backend": per_backend,
        "failures": failures,
        "write": wstats,
        "trading_days": len(cal),
        "elapsed_s": {"expression": round(t_ex, 1), "panel_kunquant": round(t_pk, 1),
                      "total": round(time.time() - t0, 1)},
        "evaluation_right_edges": {str(h): v for h, v in qp.evaluation_right_edges().items()},
        "note": ("gold 因子值算到冻结线当天；求值右端是给**前向收益**的约束，"
                 "由评分器硬拦，不在这里截。"),
    }
    mp = root / universe / "manifest.json"
    mp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    mp.chmod(0o600)
    if verbose:
        print(f"[{universe}] 完成 {wstats['factors']} 因子 / {wstats['rows']:,} 行 / "
              f"{wstats['bytes'] / 2**20:.0f} MiB / {manifest['elapsed_s']}", flush=True)
        if failures:
            print(f"  ⚠ 失败 {len(failures)} 条：{failures[:5]}", flush=True)
    return manifest


def main(argv: "list[str] | None" = None) -> int:
    p = argparse.ArgumentParser(description="卡 2.1b 因子参考执行器")
    p.add_argument("--universe", default="csi300", choices=list(cfg.UNIVERSES_PIT))
    p.add_argument("--start", default="2019-01-01")
    p.add_argument("--end", default=cfg.FREEZE_DATE)
    p.add_argument("--backends", default=None,
                   help="逗号分隔，只跑其中几路（调试用；正式跑不要限制）")
    p.add_argument("--gold-root", default=None,
                   help="落点根（默认该通道的 gold 根）。比对用，不覆盖既有产物。")
    p.add_argument("--spill-dir", default=None,
                   help="求值出来的面板即时落到这个临时目录，峰值内存从 ~22 GiB 降到几 GiB。"
                        "产物逐字节不变；跑完自动删。共用机上跑大宇宙请务必给。")
    a = p.parse_args(argv)
    b = tuple(a.backends.split(",")) if a.backends else None
    m = run(a.universe, a.start, a.end, backends=b,
            gold_root=Path(a.gold_root) if a.gold_root else None,
            spill_dir=Path(a.spill_dir) if a.spill_dir else None)
    bad = [k for k, v in m["per_backend"].items() if v["failed"] > 0]
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
