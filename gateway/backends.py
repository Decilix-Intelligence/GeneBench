# -*- coding: utf-8 -*-
"""live 湖 / snapshot 双后端。

v1 评测**一律走 snapshot**（卡 1.4 落地后把默认改成 snapshot）。
现在 snapshot 后端还没有物料，所以：

- 默认后端由环境变量 ``GENEBENCH_GATEWAY_BACKEND`` 控制，**配置驱动不是改代码**；
- 缺省值是 ``live``，但只要 `cfg.SNAPSHOT_TABLES_DIR` 出现 manifest，
  `default_backend()` 就自动切 ``snapshot`` —— 卡 1.4 落地即生效，不用再改这里。

**白名单是承重的**：`EXPOSED_DATASETS` 之外的表一律不给查。
`reference/` 与 `scorer/` 不在任何清单里，也不允许通过参数拼出来（红线 5）。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pandas as pd

import genebench_config as cfg
from snapshots import lake

from .errors import GatewayDenied, Reason

#: 卡 1.4 的快照落点。**另起子目录**，不要和卡 1.1/1.2 的产物混在一起
#: （否则 manifest 会把它们一起算进去 —— 见 tickets N-14）。
#: **这两个常量恒指私有通道**（既有语义不动）；公开通道走下面的 `tables_dir()`。
SNAPSHOT_TABLES_DIR: Path = cfg.SNAPSHOTS / cfg.SNAPSHOT_VERSION / "tables"
SNAPSHOT_MANIFEST: Path = SNAPSHOT_TABLES_DIR / "manifest.json"


def tables_dir() -> Path:
    """**当前通道**的快照表目录（卡 1.1-a）。private 时就是 `SNAPSHOT_TABLES_DIR`。"""
    return cfg.snapshot_tables_dir()


def manifest_path() -> Path:
    return tables_dir() / "manifest.json"

BACKENDS: tuple[str, ...] = ("live", "snapshot")

#: **网关能查的表，就这些。**任何不在这里的名字直接 403。
#: 刻意不写成"排除 reference/scorer"——白名单比黑名单安全：
#: 将来新增一张表若忘了登记，失败形态是"查不到"（响的），不是"被查到"（哑的）。
EXPOSED_DATASETS: frozenset[str] = frozenset(
    {
        "daily",
        "adj_factor",
        "stk_limit",
        "suspend_d",
        "trade_cal",
        "income",
        "income_vip",
        "balancesheet",
        "balancesheet_vip",
        "cashflow",
        "cashflow_vip",
    }
)

#: 明确**不进 v1** 的表，单独列出来是为了给出有信息量的拒绝理由。
BLOCKED_DATASETS: dict[str, str] = {
    "fina_indicator": "缺 f_ann_date，无法严格 PIT（实施稿卡 1.3 明确不进 v1）",
    "fina_indicator_vip": "同 fina_indicator",
    "stk_factor_pro": "bfq/hfq/qfq 三价口径不进 v1 数据面（与 adj_factor 不同步）",
}


#: 公开通道**不服务**的数据集（卡 2.5 §1 的确认项 + N-58①）。
#: 六张财务报表：baostock 的季频财务**无 `f_ann_date`**，而我们的 PIT 判据正是
#: `f_ann_date IS NOT NULL AND <= as_of` 且明令禁止 `coalesce(f_ann_date, ann_date)`
#: （那是全市场级前视泄漏）—— 所以「用公开源补一份」这条路**不成立**，
#: 不是「暂时没建」。拒绝时给的理由必须是这一条，不能是「查不到」。
PUBLIC_WITHHELD_DATASETS: dict[str, str] = {
    "income": "公开通道不服务财务（baostock 季频财务无 f_ann_date，做不到严格 PIT）",
    "income_vip": "同 income",
    "balancesheet": "同 income",
    "balancesheet_vip": "同 income",
    "cashflow": "同 income",
    "cashflow_vip": "同 income",
}


def exposed_datasets(channel: str | None = None) -> frozenset[str]:
    """**当前通道**能查的表。公开通道 = 私有清单 − `PUBLIC_WITHHELD_DATASETS`。"""
    if cfg.assert_channel(channel) == "public":
        return frozenset(EXPOSED_DATASETS) - frozenset(PUBLIC_WITHHELD_DATASETS)
    return EXPOSED_DATASETS


def default_backend() -> str:
    """当前生效的后端。配置驱动。

    **公开通道只有 snapshot 一种后端**：`live` 指的是私有审计湖，
    在公开通道上放行 live 等于把私有数据从公开端点发出去。这里当场抛，
    而不是静默降级 —— 静默降级的表现是「公开网关照常答，答的是私有数」。
    """
    forced = os.environ.get("GENEBENCH_GATEWAY_BACKEND", "").strip().lower()
    public = cfg.channel() == "public"
    if forced:
        if forced not in BACKENDS:
            raise ValueError(
                f"GENEBENCH_GATEWAY_BACKEND={forced!r} 不认识；只接受 {BACKENDS}"
            )
        if public and forced == "live":
            raise ValueError(
                "公开通道（GENEBENCH_CHANNEL=public）不许用 live 后端："
                "live 读的是私有审计湖，那等于把私有数据从公开端点发出去。"
            )
        return forced
    if public:
        return "snapshot"
    return "snapshot" if SNAPSHOT_MANIFEST.exists() else "live"


def assert_exposed(dataset: str) -> str:
    """白名单闸门。"""
    name = str(dataset).strip().lower()
    if cfg.channel() == "public" and name in PUBLIC_WITHHELD_DATASETS:
        raise GatewayDenied(
            Reason.DATASET_NOT_EXPOSED,
            f"{name} 在公开通道不服务：{PUBLIC_WITHHELD_DATASETS[name]}",
            context={"dataset": name, "channel": "public"},
        )
    if name in BLOCKED_DATASETS:
        raise GatewayDenied(
            Reason.DATASET_NOT_EXPOSED,
            f"{name} 不在 v1 数据面：{BLOCKED_DATASETS[name]}",
            context={"dataset": name},
        )
    if name not in exposed_datasets():
        raise GatewayDenied(
            Reason.DATASET_NOT_EXPOSED,
            f"{name} 不在 v1 暴露清单里",
            context={"dataset": name, "exposed": sorted(exposed_datasets())},
        )
    return name


def snapshot_path(dataset: str) -> Path:
    return tables_dir() / f"{dataset}.parquet"


def read_table(
    dataset: str,
    *,
    where: str = "",
    params: list[Any] | None = None,
    columns: str = "*",
    backend: str | None = None,
    conn: Any = None,
) -> pd.DataFrame:
    """按当前后端读一张（已白名单校验过的）表。

    **不做任何 as_of 判定** —— 那是 `asof.py` 的事，而且必须发生在
    调用本函数**之前**（403 要先于取数，见 asof 模块的不变量 2）。
    """
    name = assert_exposed(dataset)
    be = backend or default_backend()
    clause = f" WHERE {where}" if where else ""
    if be == "snapshot":
        target = snapshot_path(name)
        if not target.exists():
            raise GatewayDenied(
                Reason.DATASET_NOT_EXPOSED,
                f"snapshot 后端里没有 {name}（卡 1.4 尚未落地该表）",
                status=503,
                context={"dataset": name, "backend": be},
            )
        sql = f"SELECT {columns} FROM read_parquet(?){clause}"  # noqa: S608
        # **N-42**：snapshot 读 parquet，不该碰 market.duckdb —— 由 lake 内部择路。
        return lake.query(sql, [str(target), *(params or [])], conn=conn)
    sql = f'SELECT {columns} FROM "{name}"{clause}'  # noqa: S608
    return lake.query(sql, params or [], conn=conn)
