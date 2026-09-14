# -*- coding: utf-8 -*-
"""公开包的**物料清单**（卡 2.5，裁定 2026-09-04 N-58④/⑤/⑥）。

卡 2.5 的交付物是「可下载的 benchmark」——**物料清单就是交付清单**。
私有通道保留全表；公开包只带 v1 真正用得到的东西。
"""
from __future__ import annotations

#: **零读取表**：登记了、拷进 v1 快照了、但**没有任何生产代码路径读它们**。
#: 全树扫描 417 个文件（`*.py` + `*.yaml` + `*.json`，**未采样**）确认：
#: 全部命中都是 `v1_tables.py` 的登记、`lake_baseline.json` 的基线记录、
#: `ops/recon/probes/` 的一次性侦查脚本，以及注释里作分区语义的举例。
#: 因子 gold（792×3 已建）与 22 道非骨架题**一处都没读**。
#:
#: 约 705MB，占 `tables/` 近一半 —— **不进公开包**；私有通道原样保留。
#: **卡 2.6 补全逐题 oracle 之后要复核一遍**（骨架题补全可能引入新读取）。
PUBLIC_EXCLUDED_TABLES: tuple[str, ...] = (
    "daily_basic",          # 695MB，最大的一张
    "stock_st", "st_history",
    "index_member_all",     # 申万行业 PIT —— 24 条 blocked 因子解封才需要
    "index_daily", "index_basic",
    "dividend",
)

#: 私有通道保留、公开包**不带**的答案面/授权数据。
#: 6 张财务报表：`/fundamentals` 已不发放给 v1 任何一道题（N-58①），
#: 而 baostock 的季频财务**无 `f_ann_date`** —— 我们的 PIT 判据正是
#: `f_ann_date IS NOT NULL AND <= as_of` 且明令禁止 `coalesce(f_ann_date, ann_date)`
#: （那是全市场级前视泄漏），所以「用公开源补一份」这条路不成立。
PRIVATE_ONLY_TABLES: tuple[str, ...] = (
    "income", "income_vip", "balancesheet", "balancesheet_vip",
    "cashflow", "cashflow_vip",
    "limit_list_d",         # 涨跌停验证器：私有通道当 oracle 核推导，不发
    "namechange",           # universe_build 的诊断输入，公开通道用 baostock 的替代路径
)

#: 公开包**必须带**的冻结件（N-58⑥）：gold 的**定义面**。
#: 少了它们，拿到包的人复现不了 —— 而 τ 恰恰标定在
#: 「两个实现有多一致」上，换实现 = 重算 gold + 重标 τ + 重新签字。
#: 每一项**带 sha256**，文档写明「τ 标定于此实现对」。
PUBLIC_FROZEN_ARTIFACTS: tuple[str, ...] = (
    "factor_library/compiled/qlib_native.jsonl",
    "factor_library/compiled/qlib_panel.jsonl",
    "factor_library/compiled/blocked.jsonl",
    "reference/factorlib_pinned/formula.py",
    "reference/factorlib_pinned/qlib_loader.py",
    "reference/factorlib_pinned/qlib_ops.py",
)

#: **不进快照、不进公开包**：记忆探针的答案钥匙要从**活源现取**（N-58⑤，归卡 2.6）。
#: 冻进快照就等于把答案放进了交付物 —— 而探针问的正是「模型记没记住冻结线之后的事」。
NEVER_SNAPSHOT: tuple[str, ...] = ("cn_cpi", "repurchase", "block_trade")


#: 六件冻结件的 **sha256**（W2，2026-09-10）。`ops/mk_release_manifest.py` 自己也算一遍，
#: 两边对不上 = 有人动过冻结件 —— `ops/test_release_manifest.py` 会当场抓到。
#:
#: **`factor_library/compiled/` 三件不是「丢了又找回来」，是从来没进过仓库**：
#: 它们一直住在数据湖 `$LAKE/reference/factor_library/compiled/`
#: （`reference.factor_exec.FACTOR_LIB` 就是从那里读的，gold 也是在那三份上算的），
#: 而本清单写的是**仓库相对路径** —— 于是 `mk_release_manifest` 一直把它们记成缺件。
#: 公开包必须自足（拿到包的人没有我们的湖），所以 W2 把湖里那三份**逐字节钉进仓库**。
#: 与 gold 的对账见 `ops/reports/public/factor_library_recovery.md`：
#: 后端分布 644/66/82 + blocked 24、`operator_convention_suspect.json` 的
#: 23 条 gold 存疑与 13 条 τ 排除、报告 §10 的 141 因子 / 379,950 格 —— 三项逐条复现。
PUBLIC_FROZEN_ARTIFACT_SHA256: dict[str, str] = {
    "factor_library/compiled/qlib_native.jsonl":
        "f0ea97c6bd5b1a8c41736b31a68756d1543d9e11c26ee3d1f8cf42727b2a4698",
    "factor_library/compiled/qlib_panel.jsonl":
        "cbf4ba183edfaabb30211decb57297c391b888ff1e6fc5fd77cc62720f882384",
    "factor_library/compiled/blocked.jsonl":
        "955f7a66c4e7a63d727fce9cb3b6fa6f22ca1b725d7db4e864bbbe76cb2bb5cc",
    "reference/factorlib_pinned/formula.py":
        "3eaf99b7dc829e824cc37cea4a414858ffc34dec9b317ab807df960bf9cb17a4",
    "reference/factorlib_pinned/qlib_loader.py":
        "bbad13f3b7152df1566b5719290baa6426f717e79227c7009a51c9208224cf96",
    "reference/factorlib_pinned/qlib_ops.py":
        "f3d16a7925c5778cf3760516ac62671958fdef675e26fb90983077aca8c7ced2",
}


#: 三件 jsonl 在湖里的上游路径（**只读**，重建脚本从不往那里写）。
#: 重放：`$PY snapshots/public/recover_factor_library.py --write`。
FACTOR_LIB_UPSTREAM: str = "$LAKE/reference/factor_library/compiled"


class ManifestError(RuntimeError):
    pass


def assert_manifest_disjoint() -> None:
    """import 期跑。三张表两两不交 —— 一张表同时「排除」又「必带」是自相矛盾。"""
    sets = {"excluded": set(PUBLIC_EXCLUDED_TABLES),
            "private_only": set(PRIVATE_ONLY_TABLES),
            "never_snapshot": set(NEVER_SNAPSHOT)}
    keys = sorted(sets)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            both = sets[a] & sets[b]
            if both:
                raise ManifestError(f"{a} 与 {b} 同时含 {sorted(both)}")


def public_tables(all_registered: tuple[str, ...]) -> list[str]:
    """公开包实际要带的表 = 登记表 − 零读取 − 私有专属。"""
    drop = set(PUBLIC_EXCLUDED_TABLES) | set(PRIVATE_ONLY_TABLES) | set(NEVER_SNAPSHOT)
    return sorted(t for t in all_registered if t not in drop)


assert_manifest_disjoint()
