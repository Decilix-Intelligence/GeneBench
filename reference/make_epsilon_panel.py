# -*- coding: utf-8 -*-
"""构建 ε 面板 `bt_input_csi300_v2.parquet` —— **S7 gold 的全部输入**（收编自 N-82）。

**为什么要收编**：这份代码原来住在 `/data/shared/genebench/scratch/export_input2.py` ——
不在仓库、不在冻结清单、没有测试。也就是「定义 S7 gold 输入的那份代码不受任何门保护」。
2026-09-05 裁定：收进仓库、加测试，**并以走网关的第二实现对拍作为它的验收**。

**两条链路，两个实现**（这是 N-82 缓解的核心）：

| | 本文件 | `reference/s7_oracle_common.fetch_panel` |
| --- | --- | --- |
| `close` / `factor` | qlib `D.features($close, $factor)` | 网关 `/bars` 原始 close × `/adj` |
| `in_universe` | qlib instruments 的 `in_date/out_date` 区间 | `/universe` **逐日 PIT** 名单 |
| `has_price` / `is_delisted` | 本文件的 `derive_flags` | 同一条规则的第二次实现 |

`ops/acceptance/s7_panel_vs_frozen.py` 逐格比 984,960 格，`close`/`factor` **逐位相等**、
三个布尔列各 0 格不一致。**不同数据源 + 不同算法给出同一张表**，
排掉的是「取数口径与 ε 那次不同」这一整类错误 —— 那类错误的表现是
11 项指标一起偏，没有任何一项报错。

**这个文件不该被重跑**：冻结面板已经是 ε 的标定基准，重跑会（见 N-89）
在归约类指标上产生 1e-15 量级的环境漂移。它在这里是**记录与判据**，
不是日常工具。真要重建，重建之后必须重标 ε。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import genebench_config as cfg                                        # noqa: E402

#: 契约 §1：窗口左端之前留 6 个交易日暖机（只用于 ffill / pre_close）。
WARMUP_DAYS = 6

PANEL_COLUMNS = ("date", "code", "close", "factor",
                 "in_universe", "has_price", "is_delisted", "signal")


def warmup_start(full_calendar: list, window_days: list) -> str:
    """暖机起点：整段日历里，回测窗口首日**往前数 6 个交易日**。

    v1 直接用窗口首日取数，于是 `ffill` 与 `pre_close` 在首日无历史可用，
    首日一律不判涨跌停 —— 而首日正是建仓日。
    """
    i = max(0, len(full_calendar) - len(window_days) - WARMUP_DAYS)
    return str(full_calendar[i])[:10]


def membership_frame(spans: dict) -> pd.DataFrame:
    """qlib 的 `{code: [(in_date, out_date), ...]}` 摊成长表。

    **一只票可以有多段成分区间**（调出又调入）。摊成多行、后面按
    `(date, code)` 聚合取 `max`，等价于「任一段覆盖当日即在成分内」。
    只取第一段的话，调出又调入的票在第二段里会被记成不在成分内 ——
    而那正是契约 §1 第二形态（掉出指数但仍在交易）要区分的东西。
    """
    rows = [(c, pd.Timestamp(a), pd.Timestamp(b))
            for c, segs in spans.items() for a, b in segs]
    return pd.DataFrame(rows, columns=["code", "in_date", "out_date"])


def derive_flags(grid: pd.DataFrame, px: pd.DataFrame, memdf: pd.DataFrame) -> pd.DataFrame:
    """在 `日 × 码` 全格上派生四种形态（契约 §1）。**纯函数，可测。**

    * `in_universe` —— 当日落在该票任一成分区间内；
    * `has_price` —— `close` 非空；
    * `is_delisted` —— **无价** 且 **晚于该票最后一个有价日**。

    `is_delisted` 这条是纯操作性的：它把「永久停牌但仍上市」也算成退市（N-81）。
    契约 §1 的措辞是「真退市」，两句话现在不是一回事 —— 登记在案，本轮按原样复现，
    因为 ε 就是在这条规则下标定的。
    """
    out = grid.merge(px, on=["date", "code"], how="left")
    out = out.merge(memdf, on="code", how="left")
    out["in_universe"] = (out["date"] >= out["in_date"]) & (out["date"] <= out["out_date"])
    out = (out.groupby(["date", "code"], as_index=False)
              .agg(close=("close", "first"), factor=("factor", "first"),
                   in_universe=("in_universe", "max")))
    out["in_universe"] = out["in_universe"].fillna(False).astype(bool)
    out["has_price"] = out["close"].notna()
    last_px = (out.loc[out["has_price"]].groupby("code")["date"].max()
                 .rename("last_price_date").reset_index())
    out = out.merge(last_px, on="code", how="left")
    out["is_delisted"] = (~out["has_price"]) & (out["date"] > out["last_price_date"])
    return out


def attach_signal(out: pd.DataFrame, sig: pd.DataFrame) -> pd.DataFrame:
    """左连接信号，日期落成 `YYYY-MM-DD` 字符串，列序按契约 §1。"""
    out = out.merge(sig, on=["date", "code"], how="left").sort_values(["date", "code"])
    out = out.assign(date=out["date"].dt.strftime("%Y-%m-%d"))
    return out[list(PANEL_COLUMNS)].reset_index(drop=True)


def build(*, out_path: Path | None = None) -> pd.DataFrame:
    """取数（qlib）+ 派生 + 落盘。**需要 qlib 环境**，单测不跑这一支。"""
    from reference import backtest as bt
    from reference import factor_exec as fx
    fx.init_qlib()
    from qlib.data import D

    conf = bt.CONFIG
    start, end, uni = conf["start"], conf["end"], conf["universe"]
    bt_days = D.calendar(start_time=start, end_time=end, freq="day")
    full = D.calendar(start_time="2018-12-01", end_time=end, freq="day")
    lo = warmup_start(full, bt_days)

    # ① 窗口内**曾经**进过成分的全部代码
    spans = D.list_instruments(D.instruments(uni), start_time=lo, end_time=end, as_list=False)
    codes = sorted(spans)

    # ② **不带成分过滤**地取价格 —— 与 v1 的唯一实质区别。
    #    v1 用 `D.instruments(uni)` 取数会按成分区间过滤，于是「不在成分内」表现为
    #    **整行缺失、连价格都没有**，与契约「掉出指数的持仓可以按市价卖」直接冲突。
    #    三份独立实现因此各自发明了规则，B 侧共 292 次「消失即清仓」。
    px = D.features(codes, ["$close", "$factor"], start_time=lo, end_time=end, freq="day")
    px.columns = ["close", "factor"]
    if px.index.names == ["instrument", "datetime"]:
        px = px.swaplevel().sort_index()
    px.index = px.index.set_names(["date", "code"])
    px = px.reset_index()

    # ③ 补全 日 × 码 全格 —— 让「无价」这件事**显式存在**，而不是靠行缺失暗示
    days = pd.DatetimeIndex([d for d in full if str(d)[:10] >= lo])
    grid = pd.MultiIndex.from_product([days, codes], names=["date", "code"]).to_frame(index=False)

    out = derive_flags(grid, px, membership_frame(spans))

    sig = pd.read_parquet(fx.GOLD_DIR / uni / "qlib_alpha158.ROC20.parquet")
    sig = sig.assign(date=pd.to_datetime(sig["date"], format="%Y%m%d")).rename(
        columns={"value": "signal"})
    out = attach_signal(out, sig)

    # 卡 1.1-b：落点按通道走（private 逐字等于既有的 `snapshots/v1/epsilon/`）。
    dst = Path(out_path) if out_path else cfg.epsilon_dir() / "bt_input_csi300_v2.parquet"
    cfg.create_dir(dst.parent)
    out.to_parquet(dst, index=False, compression="zstd")
    dst.chmod(0o600)
    return out


if __name__ == "__main__":
    raise SystemExit(print(build().shape) or 0)
