# oracle 参考解（数据面私有；在 f01 直跑，经网关 snapshot 后端产 artifact）。gold_token: <<gold_token>>
# S4-ECO-01（自由发挥，anchor pending，oracle.expected=validate_only）：
#   oracle 不进排名，只作 Selection Regret 上界（实施稿 §S4：t-stat + FDR selector）。
# gold 切片 = 池内每个因子在 [window.start, holdout.start) 与 holdout 两段上的 ic_by_horizon（f01 预算好，按 gold_args.pool_id）。
# 结算（卡 5.x，尚未落盘——D-11：这里只写 oracle 会交什么，不写怎么判）：
#   效果分候选 = 选中因子留出段 IC 经 search_count 紧缩后的 IC_deflated（对接决定 §1.3）；
#   Selection Regret = max_pool(holdout IC) − selected holdout IC。
# 材料（f01 物化）：pool_id → 20 条 gtja_191 可执行因子的 gold 面板拼成长表；池成员表存 reference/pools/<pool_id>.json。
import json, sys

import yaml
from pathlib import Path

import numpy as np
import pandas as pd

# 统一 I/O 契约（裁定 2026-09-05）：读标准位置的任务规格、经网关取数、写标准 artifact 路径。
# **不接受任何 stage 特定的 env/argv** —— 从任务目录读得出来的东西，一律不从环境拿。
from reference.oracle_io import context as _oracle_context
from reference.oracle_io import write as _oracle_write
CTX = _oracle_context(__file__)

TASK = yaml.safe_load(Path("task.yaml").read_text(encoding="utf-8"))   # 数据面全量 task.yaml
D = TASK["declared"]
#: oracle 的**默认留出段**。这不是题面规定的口径 —— 题面允许自划留出段并写进 `payload.holdout`，
#: oracle 只是也做了一次划分。这两个日期是按出集那一行（`s4-eco-01`，窗口 2026-01-05..2026-06-30）
#: 的**后半段**填的。
DEFAULT_HOLDOUT = {"start": "2026-04-01", "end": "2026-06-30"}

#: 训练段 / 留出段各自的最低交易日数。低于它，那一段算不出 `ic_stats`，也选不出因子。
MIN_SEGMENT_DAYS = 10


def split_window(days: list[str]) -> tuple[dict, str]:
    """把窗口切成「训练段 | 留出段」，返回 `(holdout, rule)`。

    **病灶（N-518，用户裁定 ③ 走 A，2026-09-10）**：这两个日期原来是写死的常量，
    而窗口是实例层会换的取值。于是窗口一挪，这个划分就**不再落在窗口里**，而**没有一处会报**：

    * 窗口挪到留出段**之前**（`s4-eco-02` / `s4-eco-04`，2026-01-05..2026-03-31）：
      `hold_dates` 是空的 → `ic_by_horizon` 逐日算不出 IC → `ic_stats` 七个字段全 NaN →
      artifact 照样写盘、照样过 envelope 校验，直到结算时 7 条 `malformed:s4_ic_stat_not_number`。
    * 窗口挪到留出段**之内**（`s4-eco-03`，2026-04-01..2026-06-30）：训练段是空的 →
      所有候选的 mean/std 都是 NaN → 挑因子返回 NaN → `"nan"` 被当成 factor_id 查因子池 →
      崩在「池里没有 'nan' 的行」。**报错指着因子池，问题在这一行常量。**

    修法不是「把窗口从候选里去掉」（那等于宣布这道题只在一个窗口上成立），
    是让划分**跟着窗口走**：默认划分在窗口里切得出两段就用它（出集那一行因此**逐字节不变**），
    切不出来就按窗口自身的交易日位置对半分，并在 `payload.note` 里**如实记下用的是哪条规则** ——
    不许让「回退的划分」看起来像「默认划分」（与 `gateway/sim_engine.py` 对 Slip 默认基准价
    那一条是同一个纪律）。

    连对半分都切不出两段 `MIN_SEGMENT_DAYS` → 抛 `S4SampleTooThin`：
    窗口本身太短，这道题在这个取值上**没有答案**，说清楚比编一个出来强。
    """
    train = [d for d in days if d < DEFAULT_HOLDOUT["start"]]
    hold = [d for d in days if DEFAULT_HOLDOUT["start"] <= d <= DEFAULT_HOLDOUT["end"]]
    if len(train) >= MIN_SEGMENT_DAYS and len(hold) >= MIN_SEGMENT_DAYS:
        return dict(DEFAULT_HOLDOUT), "default"
    from reference import s4_oracle_common as _s4
    k = len(days) // 2
    if k < MIN_SEGMENT_DAYS or len(days) - k < MIN_SEGMENT_DAYS:
        raise _s4.S4SampleTooThin(
            f"窗口里只有 {len(days)} 个交易日，切不出两段各 {MIN_SEGMENT_DAYS} 天的"
            f"「训练 | 留出」—— 这道题在这个窗口取值上没有答案。"
            f"默认划分 {DEFAULT_HOLDOUT['start']}..{DEFAULT_HOLDOUT['end']} 在本窗口里是 "
            f"训练 {len(train)} 天 / 留出 {len(hold)} 天")
    return {"start": days[k], "end": days[-1]}, "window_half"


def train_stats(pool: pd.DataFrame, X: dict, start: str, end: str, h: int) -> pd.DataFrame:
    """每个 factor_id 在 [start, end) 上、持有期 h 的逐日截面 Spearman：mean / std / n。"""
    from reference import s4_oracle_common as s4
    dates = [d for d in X["window"] if start <= d < end]
    rows = {}
    for fid, sub in pool.groupby("factor_id"):
        f = (sub.assign(date=sub["date"].map(s4._iso),
                        code=sub["code"].astype(str).str.strip().map(s4.gwc.to_gateway_code))
                .pivot(index="date", columns="code", values="value")
                .reindex(index=dates, columns=X["codes"]))
        fwd = s4.forward_returns(f.index, X["adj_close"], h)
        Xd = {k: (v.loc[dates] if isinstance(v, pd.DataFrame) else v) for k, v in X.items()}
        valid = s4.valid_mask(f, Xd, fwd)
        ic, _n = s4.ic_series(f, fwd, valid, D["tie_handling"])
        x = ic.dropna()
        rows[fid] = {"mean": float(x.mean()), "std": float(x.std(ddof=1)), "n": int(len(x))}
    return pd.DataFrame(rows).T


def main() -> None:
    from reference import s4_oracle_common as s4
    from reference.gateway_client import Client
    pool = pd.read_parquet("work/factor_pool.parquet")             # date, code, factor_id, value
    h0 = min(D["holding_periods"])
    X = s4.build_inputs(Client.for_context(CTX), TASK, max(D["holding_periods"]))
    holdout, rule = split_window(X["window"])           # 划分跟着窗口走（③）
    stats = train_stats(pool, X, TASK["window"]["start"], holdout["start"], h0)   # 只看留出段之前
    chosen, survivors, note = s4.bh_fdr_select(stats, q=0.10)
    train = stats["mean"]
    hold_dates = [d for d in X["window"] if holdout["start"] <= d <= holdout["end"]]
    factor = s4.load_factor_panel("work/factor_pool.parquet", chosen)
    ic_stats = s4.ic_by_horizon(factor, X, D, 0, dates=hold_dates)[str(h0)]
    # 用的不是默认划分就**如实写进 note**。只在回退时追加，默认那条一个字节不加 ——
    # 出集那一行（s4-eco-01）的 gold 因此与 v1.0.14 逐字节相同。
    if rule != "default":
        note = f"{note};holdout_rule={rule}"
    art = {
        "schema_version": "1.0", "artifact_id": f"{TASK['task_id']}-oracle", "stage": "S4",
        "task_id": TASK["task_id"], "config_id": "oracle", "arm": "strict", "seed": 0,
        "as_of": TASK["as_of"], "produced_at": pd.Timestamp.utcnow().isoformat(), "provenance": [],
        "declarations": dict(D),
        "payload": {"selected_factor_id": chosen, "ic_stats": ic_stats, "holdout": holdout,
                    "search_count": int(train.notna().sum()), "fdr_survivors": survivors, "note": note,
                    "candidates_evaluated": [{"factor_id": k, "train_ic_mean": float(v)} for k, v in train.items()]},
    }
    _oracle_write(CTX, art)               # 标准路径 + 0600（红线 5）
if __name__ == "__main__":
    main()
