"""卡 1.2 负控 + 全历史独立复算。**不是 pytest**,是给人跑给人看的。

跑法::

    cd $REPO && $GENEBENCH_ROOT/env/bin/python ops/negctl_tradability.py

两件事:

**A. 全历史独立复算(不是抽查)。**
`ops/test_tradability.py` 的逐行重算只覆盖 2021-06 一个月 —— 那个粒度**看不见
跨年的错**。本脚本用一份完全不同的实现:**不分年**,按 code 在整条交易日网格上
顺序走一遍状态机,把 `suspend` / `no_data` / `carried_after_S` 的**全历史总数**
和产物对。

这条不是多余的。卡 1.2 第一版把跨年顺延写成"多算上一年最后 60 个交易日当前缀",
`ops/test_tradability.py` **40 条全绿**,单月逐行重算也全绿 —— 因为错只发生在
年初、且只影响连续停牌超过 60 个交易日的票。是这个全历史对数把它抓出来的
(`carried_after_S` 只有正确值的一半)。**抽查看不出结构性的错。**

**B. 负控:把判定逐条退化,断言验收测试真的会红。**
测试自己也要被测 —— 一条断言如果在错误的实现下也绿,它就没在守任何东西。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import genebench_config as cfg  # noqa: E402
from snapshots import lake  # noqa: E402
from snapshots import tradability as tr  # noqa: E402
from snapshots import universe_build as ub  # noqa: E402

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}{(' — ' + detail) if detail else ''}")
    if not ok:
        FAILURES.append(name)


# ---------------------------------------------------------------------------
# A. 全历史独立复算
# ---------------------------------------------------------------------------


def independent_full_history(con) -> dict[str, int]:
    """按 code 在**整条**网格上顺序走状态机,不分年。与产物是两份独立实现。"""
    grid = tr.load_grid(cfg.FREEZE_DATE, conn=con)
    windows, _ = ub.load_listing_windows(grid, conn=con)
    idx_of = {d: i for i, d in enumerate(grid.compact)}

    # 三源:只要 (code, day_idx) 的存在性 + suspend_type
    have_daily: dict[str, set[int]] = {}
    have_limit: dict[str, set[int]] = {}
    have_susp: dict[str, set[int]] = {}
    flag: dict[tuple[str, int], set[str]] = {}
    for year in sorted({d.year for d in grid.days}):
        g = f"trade_date={year}-*"
        for ds, sink in ((tr.DAILY_DS, have_daily), (tr.LIMIT_DS, have_limit)):
            df = lake.read_gold(ds, g, columns=["ts_code", "trade_date"], conn=con)
            for c, td in zip(df["ts_code"], df["trade_date"]):
                i = idx_of.get(td)
                if i is not None:
                    sink.setdefault(c, set()).add(i)
        sus = lake.read_gold(
            tr.SUSPEND_DS, g, columns=["ts_code", "trade_date", "suspend_type"], conn=con
        )
        for c, td, t in zip(sus["ts_code"], sus["trade_date"], sus["suspend_type"]):
            i = idx_of.get(td)
            if i is not None:
                # 同日可能既有 S 又有 R(实测 161 个 key)—— 收成集合,
                # 不做任何"留第一条"的顺序依赖选择。
                flag.setdefault((c, i), set()).add(t)
                have_susp.setdefault(c, set()).add(i)

    codes = set(windows) | set(have_daily) | set(have_limit) | set(have_susp)
    tally = {
        "rows": 0, "suspend": 0, "no_data": 0,
        "carried_after_S": 0, "suspend_d_S": 0,
    }
    for code in codes:
        days: set[int] = set()
        if code in windows:
            lo, hi = windows[code]
            days |= set(range(lo, hi + 1))
        days |= have_daily.get(code, set())
        days |= have_limit.get(code, set())
        days |= have_susp.get(code, set())
        d_set = have_daily.get(code, frozenset())
        prev = None
        state = False
        for i in sorted(days):
            if prev is not None and i != prev + 1:
                state = False  # 洞:不许顺延
            prev = i
            tally["rows"] += 1
            d = i in d_set
            f = flag.get((code, i), frozenset())
            if d:
                # 有成交是最硬的证据,压过一切
                state = False
                continue
            if "S" in f:
                state = True
                tally["suspend"] += 1
                tally["suspend_d_S"] += 1
                continue
            if "R" in f:
                # 复牌了却没有行情行 —— 说不清,算数据缺失
                state = False
                tally["no_data"] += 1
                continue
            if state:
                tally["suspend"] += 1
                tally["carried_after_S"] += 1
            else:
                tally["no_data"] += 1
    return tally


def run_full_history_check(con) -> None:
    print("\n=== A. 全历史独立复算(不分年,按 code 顺序走)===")
    ref = independent_full_history(con)
    summary_path = cfg.TRADABILITY_JSON
    import json

    got = json.loads(summary_path.read_text(encoding="utf-8"))["totals"]
    pairs = [
        ("rows", got["rows"], ref["rows"]),
        ("suspend", got["status"]["suspend"], ref["suspend"]),
        ("no_data", got["status"]["no_data"], ref["no_data"]),
        ("suspend_d_S", got["suspend_basis"]["suspend_d_S"], ref["suspend_d_S"]),
        ("carried_after_S", got["suspend_basis"]["carried_after_S"], ref["carried_after_S"]),
    ]
    for name, a, b in pairs:
        check(f"全历史 {name}", a == b, f"产物 {a:,} vs 独立复算 {b:,}")


# ---------------------------------------------------------------------------
# B. 负控
# ---------------------------------------------------------------------------


def _mini(rows: list[dict]) -> pd.DataFrame:
    base = {
        "code": "000001.SZ", "date_idx": 0, "in_listing_window": True,
        "has_daily": False, "has_limit": False, "suspend_flag": None,
        "suspend_timing": None, "close": np.nan, "high": np.nan, "low": np.nan,
        "volume": np.nan, "up_limit": np.nan, "down_limit": np.nan,
    }
    return pd.DataFrame([{**base, **r} for r in rows])


def run_negative_controls() -> None:
    print("\n=== B. 负控:把判定逐条退化,看断言会不会红 ===")

    # B1 去掉顺延 -> 长期停牌被判 no_data
    f = _mini([{"date_idx": 0, "suspend_flag": "S"}, {"date_idx": 1}, {"date_idx": 2}])
    good = list(tr.classify(f.copy())["status"])
    naive = ["suspend" if r.get("suspend_flag") == "S" else "no_data"
             for r in f.to_dict("records")]
    check(
        "B1 去掉顺延会改变结论",
        good != naive,
        f"正确 {good} vs 退化 {naive}",
    )

    # B2 不排除"无涨跌幅限制"哨兵 -> 0.01 的票被误判封跌停。
    #
    # **上一版只用 999999.999 造样本 —— 那个值在旧阈值 100000.0 之上,所以
    # 旧实现也能通过,这条负控当时测不到边界。** 现在把湖里真实出现过的六种
    # 哨兵取值逐个喂进去,其中后三种正是旧阈值漏掉的那 1,046 行的编码。
    sentinels = [
        (100000.0, 0.01, "旧阈值也能罩住"),
        (1000000.0, 0.01, "旧阈值也能罩住"),
        (999999.999, 0.01, "旧阈值也能罩住"),
        (99999.999, 0.01, "**旧阈值漏掉**(751 行)"),
        (99999.99, 0.0, "**旧阈值漏掉**(267 行)"),
        (0.0, 0.0, "**旧阈值漏掉**(28 行);up_limit=0 连「大于阈值」都不是"),
    ]
    for up, dn, why in sentinels:
        f = _mini([{
            "date_idx": 0, "has_daily": True, "has_limit": True,
            "close": max(dn, 0.01), "high": max(dn, 0.01), "low": max(dn, 0.01),
            "up_limit": up, "down_limit": dn,
        }])
        out = tr.classify(f.copy())
        legacy_would_catch = up >= 100000.0
        check(
            f"B2 哨兵 up={up:.10g}/down={dn:.10g} 被识别({why})",
            bool(out.loc[0, "no_price_limit"])
            and out.loc[0, "status"] == "trade"
            and not bool(out.loc[0, "limit_down_close"])
            and not bool(out.loc[0, "limit_touched_down"]),
            f"旧阈值 up>=100000.0 {'能' if legacy_would_catch else '**不能**'}罩住它",
        )

    # B2b 旧阈值必须**真的**罩不住后三种 —— 否则上面那六条没有判别力。
    missed_by_legacy = [(u, d) for u, d, _ in sentinels if u < 100000.0]
    check(
        "B2b 旧阈值确实漏掉一族哨兵",
        len(missed_by_legacy) == 3,
        f"旧阈值漏掉 {missed_by_legacy}",
    )

    # B2c 真实价格不许被误判成哨兵(新判据不能宽到把正常行也罩进去)。
    f = _mini([{
        "date_idx": 0, "has_daily": True, "has_limit": True,
        "close": 11.0, "high": 11.0, "low": 10.0, "up_limit": 11.0, "down_limit": 9.0,
    }])
    out = tr.classify(f.copy())
    check(
        "B2c 正常价格不被误判成哨兵",
        not bool(out.loc[0, "no_price_limit"]) and out.loc[0, "status"] == "limit_up",
    )

    # B2d 湖里**没出现过**的编码也要罩住 —— band 侧存在的全部理由。
    # D1 的教训不是"阈值取错了",是"把判据绑死在见过的取值上"。
    for up, dn, want, why in [
        (88888.88, 0.02, True, "没见过的编码,band≈1.0,旧阈值罩不住"),
        (4321.0, 0.03, True, "量级像价格但带宽荒谬,两个旧阈值都罩不住"),
        (12.5, 10.5, False, "正常 ±8.7% 带,不许误判"),
        (6.21, 2.41, False, "真实上界:新股首日 ±44% 档(601975.SH@2019-01-08)"),
    ]:
        f = _mini([{
            "date_idx": 0, "has_daily": True, "has_limit": True,
            "close": dn, "high": dn, "low": dn, "up_limit": up, "down_limit": dn,
        }])
        got = bool(tr.classify(f.copy()).loc[0, "no_price_limit"])
        check(f"B2d {up:g}/{dn:g} -> no_price_limit={want}({why})", got == want)

    # B3 触板用 close 而不是 high -> 炸板整片丢失
    f = _mini([{
        "date_idx": 0, "has_daily": True, "has_limit": True,
        "close": 10.5, "high": 11.0, "low": 10.0, "up_limit": 11.0, "down_limit": 9.0,
    }])
    out = tr.classify(f.copy())
    check(
        "B3 用 high 才看得见炸板",
        bool(out.loc[0, "limit_touched_up"]) and not bool(out.loc[0, "limit_up_close"]),
    )

    # B4 "S 且有行情"判成 suspend -> 盘中停牌被当成全天停牌
    f = _mini([{
        "date_idx": 0, "has_daily": True, "suspend_flag": "S",
        "close": 10.0, "high": 10.0, "low": 10.0,
    }])
    out = tr.classify(f.copy())
    check(
        "B4 盘中停牌不许判 suspend",
        out.loc[0, "status"] == "trade" and bool(out.loc[0, "intraday_halt"]),
    )

    # B5 隔着洞顺延 -> 凭空断言洞里也停牌
    f = _mini([{"date_idx": 0, "suspend_flag": "S"}, {"date_idx": 9}])
    check("B5 洞会切断顺延", list(tr.classify(f.copy())["status"]) == ["suspend", "no_data"])

    # B6 跨年 carry_in 真的生效
    f = _mini([{"date_idx": 100}])
    check(
        "B6 carry_in 生效",
        tr.classify(f.copy(), carry_in={"000001.SZ": True}).loc[0, "status"] == "suspend"
        and tr.classify(f.copy()).loc[0, "status"] == "no_data",
    )


# ---------------------------------------------------------------------------
# C. 篡改产物,断言验收测试会红
# ---------------------------------------------------------------------------


def run_tamper_check() -> None:
    print("\n=== C. 篡改产物 -> 验收测试必须红 ===")
    year = 2021
    target = tr.year_partition_path(year)
    backup = target.with_suffix(".parquet.bak")
    df = pd.read_parquet(target)
    import os
    import shutil

    shutil.copy2(target, backup)
    os.chmod(backup, 0o600)
    try:
        hit = int(np.flatnonzero((df["status"] == "trade").to_numpy())[0])
        df.loc[hit, "status"] = "suspend"
        import pyarrow as pa
        import pyarrow.parquet as pq

        meta = pq.ParquetFile(backup).schema_arrow.metadata or {}
        table = pa.Table.from_pandas(
            df[list(tr.TRADABILITY_COLUMNS)], schema=tr.PARQUET_SCHEMA, preserve_index=False
        )
        pq.write_table(table.replace_schema_metadata(dict(meta)), target, compression="zstd")
        os.chmod(target, 0o600)
        rc = subprocess.run(
            [
                str(cfg.PYTHON), "-m", "pytest",
                "ops/test_tradability.py::test_status_is_reproducible_from_its_own_row",
                "-q",
            ],
            cwd=str(cfg.REPO), capture_output=True, text=True,
        )
        check("C1 篡改 status 后自洽检查变红", rc.returncode != 0, rc.stdout.strip()[-160:])
    finally:
        shutil.move(str(backup), str(target))
        os.chmod(target, 0o600)
    rc = subprocess.run(
        [
            str(cfg.PYTHON), "-m", "pytest",
            "ops/test_tradability.py::test_status_is_reproducible_from_its_own_row",
            "-q",
        ],
        cwd=str(cfg.REPO), capture_output=True, text=True,
    )
    check("C2 还原后恢复绿", rc.returncode == 0, rc.stdout.strip()[-80:])


def main() -> int:
    lake.raise_open_file_limit()
    con = tr.open_lake()
    try:
        run_full_history_check(con)
    finally:
        con.close()
    run_negative_controls()
    run_tamper_check()
    print("\n" + ("=" * 60))
    if FAILURES:
        print(f"负控 FAIL:{FAILURES}")
        return 1
    print("负控 PASS(全部)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
