"""卡 1.2 验收:`tradability` 的产物自洽 + 与三源的可还原性 + 第三方口径交叉验证。

跑法::

    cd $REPO && $GENEBENCH_ROOT/env/bin/python -m pytest ops/test_tradability.py -q

**这套测试的立场是证伪,不是背书。** 凡是"把摘要里的数字再算一遍然后和摘要比"
的自证式断言一律不写 —— 那只能证明代码没变,证明不了产物是对的。

分五层:

1. **结构自洽**:枚举值、键唯一、冻结线、`status` 能从同一行的其它列**重新推出来**、
   触板列与 `has_limit` / 哨兵的关系。完全不碰湖。
2. **与湖的可还原性**:拿 2021-06 单月,用一个**逐行 python 循环**(和产物那套
   向量化实现是两份独立代码)从 `daily` / `suspend_d` / `stk_limit` 现场重算,
   逐行比。
3. **第三方口径交叉验证**:`limit_list_d`(不参与本表任何判定)的 `U` / `D` / `Z`
   必须**全部**落进我们对应的列里。这是唯一一条"外部真相"。
4. **验收 (a) 的两个实测样例**:不信产物,回湖里把三源原始行捞出来对。
5. **负控**:故意破坏产物 / 故意退化判定,断言测试真的会红。测试自己也要被测。
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

import numpy as np
import pandas as pd
import pytest

import genebench_config as cfg
from snapshots import lake
from snapshots import tradability as tr
from snapshots import universe_build as ub

#: 交叉验证与逐行重算用的月份。选 2021-06 的理由:
#: `limit_list_d` 覆盖它(该表只有 20200102 起),而且它同时含有
#: 主板 10% / 创业板 20% / ST 5% 三种涨跌幅,不是一个退化样本。
RECOMPUTE_MONTH = "2021-06"
RECOMPUTE_YEAR = 2021


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def summary() -> dict[str, Any]:
    if not cfg.TRADABILITY_JSON.exists():
        pytest.fail(
            f"摘要不存在:{cfg.TRADABILITY_JSON}。"
            f" 先跑 `python -m snapshots.tradability`。"
        )
    return json.loads(cfg.TRADABILITY_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def years(summary) -> list[int]:
    return [row["year"] for row in summary["by_year"]]


@pytest.fixture(scope="module")
def slim(years) -> pd.DataFrame:
    """全表,但**只取判定相关的列** —— 22 列 × 1500 万行会把内存吃光。"""
    cols = [
        "code",
        "date_compact",
        "status",
        "has_daily",
        "has_limit",
        "suspend_flag",
        "suspend_basis",
        "intraday_halt",
        "no_price_limit",
        "limit_up_close",
        "limit_down_close",
        "limit_touched_up",
        "limit_touched_down",
        "in_listing_window",
    ]
    return pd.concat(
        [
            pd.read_parquet(tr.year_partition_path(y), columns=cols)
            for y in years
        ],
        ignore_index=True,
    )


@pytest.fixture(scope="module")
def one_year() -> pd.DataFrame:
    """一年的**全列**产物,用来验价格列与触板列的关系。"""
    return tr.read_tradability(RECOMPUTE_YEAR)


@pytest.fixture(scope="module")
def acceptance() -> tuple[pd.DataFrame, dict[str, str]]:
    return tr.read_acceptance()


@pytest.fixture(scope="module")
def con():
    lake.raise_open_file_limit()
    c = tr.open_lake()
    yield c
    c.close()


# ===========================================================================
# 第 1 层:结构自洽(不碰湖)
# ===========================================================================


def test_columns_schema_and_doc_agree() -> None:
    """列清单、parquet schema、列文档三者必须逐字一致。

    三处各写一份是最容易漂的地方:加了列忘了写文档,数据卡就会漏掉它;
    改了顺序忘了改 schema,`pa.Table.from_pandas` 会静默按名字对上而顺序错乱。
    """
    assert tuple(f.name for f in tr.PARQUET_SCHEMA) == tr.TRADABILITY_COLUMNS
    assert tuple(tr.COLUMN_DOC) == tr.TRADABILITY_COLUMNS


def test_partitions_exist_for_every_year_in_grid(summary, years) -> None:
    for y in years:
        assert tr.year_partition_path(y).exists(), f"缺 year={y} 分区"
    first = dt.date.fromisoformat(summary["calendar"]["first"]).year
    last = dt.date.fromisoformat(summary["calendar"]["last"]).year
    assert years == list(range(first, last + 1))


def test_enums_are_closed(slim) -> None:
    """`status` / `suspend_basis` / `suspend_flag` 不许出现枚举外的值。"""
    assert set(slim["status"].unique()) <= set(cfg.TRADABILITY_STATUSES)
    assert set(slim["suspend_basis"].unique()) <= set(cfg.TRADABILITY_SUSPEND_BASES)
    flags = set(slim["suspend_flag"].dropna().unique())
    # `SR` 不是 tushare 的取值,是我们对"同日既有 S 又有 R"的显式编码 ——
    # 实测 161 个 (code, date) 是这样,详见 `_collapse_suspend`。
    assert flags <= {"S", "R", "SR"}, f"suspend_type 出现了意料之外的值:{flags}"
    assert "SR" in flags, "一个 SR 都没有?那 161 个同日冲突的 key 去哪了"


def test_every_status_actually_occurs(slim) -> None:
    """五档必须**都**出现过。

    只出现四档意味着有一条分支从没被走到 —— 那条分支就是没被验证过的死代码。
    """
    counts = slim["status"].value_counts()
    missing = [s for s in cfg.TRADABILITY_STATUSES if counts.get(s, 0) == 0]
    assert not missing, f"这些 status 一行都没有:{missing}"


def test_no_row_beyond_freeze_line(slim) -> None:
    """红线 7:冻结产物里不许有超过冻结线的行。"""
    assert slim["date_compact"].max() <= cfg.FREEZE_DATE.replace("-", "")


def test_key_is_unique(slim) -> None:
    """``(code, date)`` 是主键。重复行会让下游 join 悄悄放大行数。"""
    dupes = slim.duplicated(subset=["code", "date_compact"]).sum()
    assert dupes == 0, f"{dupes} 行 (code, date) 重复"


def test_date_and_compact_agree(one_year) -> None:
    derived = pd.to_datetime(one_year["date_compact"], format="%Y%m%d").dt.date
    assert (derived.to_numpy() == one_year["date"].to_numpy()).all()


def _recompute_status(df: pd.DataFrame) -> np.ndarray:
    """只用**同一行的其它列**把 `status` 重新推一遍(优先级见 cfg 的 docstring)。"""
    suspended = df["suspend_basis"].to_numpy() != "none"
    has_daily = df["has_daily"].to_numpy()
    return np.where(
        ~has_daily,
        np.where(suspended, "suspend", "no_data"),
        np.where(
            df["limit_up_close"].to_numpy(),
            "limit_up",
            np.where(df["limit_down_close"].to_numpy(), "limit_down", "trade"),
        ),
    )


def test_status_is_reproducible_from_its_own_row(slim) -> None:
    """`status` 必须能从同一行的证据列**重新推出来**,一行都不能差。

    这一条挡的是"status 和证据列各写各的"——那种错在抽查里几乎看不见,
    但会让下游按 `has_daily` 过滤和按 `status` 过滤得到不同的结果集。
    """
    got = _recompute_status(slim)
    bad = np.flatnonzero(got != slim["status"].to_numpy())
    assert len(bad) == 0, (
        f"{len(bad)} 行的 status 和它自己的证据列对不上,例如:\n"
        f"{slim.iloc[bad[:5]]}"
    )


def test_suspend_basis_matches_flag(slim) -> None:
    """`suspend_d_S` 必须真的当天有 `S`;有 `S` 且缺行必须判 `suspend_d_S`。"""
    is_direct = slim["suspend_basis"] == "suspend_d_S"
    has_s = slim["suspend_flag"].isin(["S", "SR"])
    assert has_s[is_direct].all()
    assert (~slim.loc[is_direct, "has_daily"]).all()
    assert ((has_s & ~slim["has_daily"]) == is_direct).all()


def test_intraday_halt_is_S_with_a_daily_row(slim) -> None:
    """`intraday_halt` 的定义:`S` 且 `daily` 有行。这类行不许判 `suspend`。"""
    expect = slim["suspend_flag"].isin(["S", "SR"]) & slim["has_daily"]
    assert (slim["intraday_halt"] == expect).all()
    assert (slim.loc[slim["intraday_halt"], "status"] != "suspend").all()
    assert slim["intraday_halt"].sum() > 0, "一行盘中停牌都没有?这不可能,先查数据"


def test_limit_flags_are_false_without_a_judgable_limit(slim) -> None:
    """没有 `stk_limit` 行、或撞上"无涨跌幅限制"哨兵 → 四个触板列必须全 `False`。

    这是那条"`has_limit=False` 是**没法判**不是**没触板**"的代码级保证。
    """
    unjudgable = (~slim["has_limit"]) | slim["no_price_limit"] | (~slim["has_daily"])
    cols = [
        "limit_up_close",
        "limit_down_close",
        "limit_touched_up",
        "limit_touched_down",
    ]
    for c in cols:
        assert not slim.loc[unjudgable, c].any(), f"{c} 在不可判的行上为真"


def test_close_sealed_implies_touched(slim) -> None:
    """收盘封板必然盘中触板(`close <= high`)。反过来不成立(炸板)。"""
    assert (~slim["limit_up_close"] | slim["limit_touched_up"]).all()
    assert (~slim["limit_down_close"] | slim["limit_touched_down"]).all()
    # 反向必须**真的**不成立,否则两列就是同一列,分开写没有意义
    assert (slim["limit_touched_up"] & ~slim["limit_up_close"]).sum() > 0
    assert (slim["limit_touched_down"] & ~slim["limit_down_close"]).sum() > 0


def test_limit_up_and_down_are_mutually_exclusive(slim) -> None:
    assert not (slim["limit_up_close"] & slim["limit_down_close"]).any()


def test_price_columns_are_present_exactly_when_has_daily(one_year) -> None:
    """`has_daily` 与价格列的空值必须完全对齐 —— 否则"缺行"的定义就漂了。"""
    assert (one_year.loc[one_year["has_daily"], "close"].notna()).all()
    assert (one_year.loc[~one_year["has_daily"], "close"].isna()).all()
    assert (one_year.loc[one_year["has_limit"], "up_limit"].notna()).all()
    assert (one_year.loc[~one_year["has_limit"], "up_limit"].isna()).all()


def test_limit_judgement_recomputes_from_prices(one_year) -> None:
    """四个触板列必须能从同一行的 `close/high/low/up_limit/down_limit` 重算出来。"""
    tol = cfg.LIMIT_PRICE_TOL
    d = one_year
    judgable = (
        d["has_daily"] & d["has_limit"] & ~d["no_price_limit"]
    ).to_numpy()
    close = d["close"].to_numpy(dtype="float64")
    high = d["high"].to_numpy(dtype="float64")
    low = d["low"].to_numpy(dtype="float64")
    up = d["up_limit"].to_numpy(dtype="float64")
    dn = d["down_limit"].to_numpy(dtype="float64")
    assert (
        (judgable & (np.abs(close - up) < tol)) == d["limit_up_close"].to_numpy()
    ).all()
    assert (
        (judgable & (np.abs(close - dn) < tol)) == d["limit_down_close"].to_numpy()
    ).all()
    assert ((judgable & (high >= up - tol)) == d["limit_touched_up"].to_numpy()).all()
    assert ((judgable & (low <= dn + tol)) == d["limit_touched_down"].to_numpy()).all()


def test_float_tolerance_changes_nothing_on_current_data(one_year) -> None:
    """数据卡声称"四种判据逐行相同"。**这条声明必须可被证伪。**

    如果哪天湖里的价格精度变了,这条会红 —— 那正是我们要被提醒的时刻。
    """
    d = one_year[one_year["has_daily"] & one_year["has_limit"] & ~one_year["no_price_limit"]]
    close = d["close"].to_numpy(dtype="float64")
    up = d["up_limit"].to_numpy(dtype="float64")
    exact = close == up
    tol = np.abs(close - up) < cfg.LIMIT_PRICE_TOL
    loose = np.abs(close - up) < 5e-3
    rounded = np.round(close, 2) == np.round(up, 2)
    assert (exact == tol).all()
    assert (exact == loose).all()
    assert (exact == rounded).all()


# --------------------------------------------------------------------------
# 「无涨跌幅限制」哨兵 —— 卡 1.2 复核 D1/D3 的修法
#
# **这一组刻意不用 `cfg.NO_PRICE_LIMIT_*` 当真相。** 上一版是这么写的::
#
#     expect = d["up_limit"] >= cfg.NO_PRICE_LIMIT_MIN
#     assert (d["no_price_limit"] == expect).all()
#
# 用**同一个常量**复述**同一个实现**,阈值取多少它都绿 —— 结构上不可能发现
# "阈值差一分钱、漏掉 1,046 行"这件事(而那件事真的发生了)。
# 所以下面的判据一律来自**这两条与实现无关的领域事实**,直接写成字面量:
#
#   * A 股个股价格从来没接近过 1 万元。实测冻结线内非哨兵行 `up_limit` 最大
#     **3,240.0**(`688808.SH @ 2026-06-26`),所以 `up_limit > PLAUSIBLE_MAX_PRICE`
#     必然不是价格。
#   * 最小报价单位 0.01 元,`down_limit` 真要落到 0.05 以下,前收得在 5 分钱附近。
#     实测非哨兵行 `down_limit` 最小 **0.07**,所以 `down_limit < PLAUSIBLE_MIN_PRICE`
#     必然不是价格。
#   * 监管给过的最宽涨跌幅档是新股首日 ±44%,隐含带宽 0.44。实测非哨兵行
#     band 上界 **0.4408**,所以 band > `PLAUSIBLE_MAX_BAND` 必然不是真实价格带。
#
# 这三个数**不是** cfg 里的阈值,它们之间隔着一道很宽的空隙(3,240 → 10,000 →
# 99,000;0.07 → 0.05 → 0.01;0.4408 → 0.45 → 0.5)。谁把 cfg 改歪了,
# 这几条会红;cfg 和实现一起改歪,这几条**照样**红。
# --------------------------------------------------------------------------

#: 与实现无关的"这不可能是股价"上界(A 股个股从没到过 1 万元)。
PLAUSIBLE_MAX_PRICE = 10_000.0
#: 与实现无关的"这不可能是股价"下界。
PLAUSIBLE_MIN_PRICE = 0.05
#: 与实现无关的"这不可能是真实涨跌幅带"上界(最宽的监管档是新股首日 ±44%)。
PLAUSIBLE_MAX_BAND = 0.45

_FZ = cfg.FREEZE_DATE.replace("-", "")
#: 湖侧 SQL 里的 band 表达式(`up + down = 0` 时为 NULL,单独判)。
_BAND_SQL = "(up_limit - down_limit) / nullif(up_limit + down_limit, 0)"


def test_sentinel_legs_agree_on_the_lake(con) -> None:
    """**湖侧**统计:哨兵的三条腿必须逐行选出同一批行。

    这是"遇到没见过的编码时**报警**而不是静默判 `False`"的落点。三条腿彼此
    独立(一条看 `up_limit` 的量级、一条看 `down_limit` 的量级、一条看两者的
    比例关系),它们在当前湖上逐行同集是个**可证伪的事实**。将来湖里若冒出
    只满足其中一部分的行,这条会红,人就得回去重读数据 —— 而不是让判据
    悄悄漏掉一族编码(那正是 D1 的翻车方式)。
    """
    up_sql = (
        f"up_limit >= {cfg.NO_PRICE_LIMIT_UP_MIN!r} OR up_limit <= 0"
    )
    dn_sql = f"down_limit <= {cfg.NO_PRICE_LIMIT_DOWN_MAX!r}"
    band_sql = (
        f"up_limit + down_limit <= 0"
        f" OR {_BAND_SQL} >= {cfg.NO_PRICE_LIMIT_BAND_MAX!r}"
    )
    row = lake.query(
        "SELECT"
        f"  sum(CASE WHEN {up_sql} THEN 1 ELSE 0 END) AS n_up,"
        f"  sum(CASE WHEN {dn_sql} THEN 1 ELSE 0 END) AS n_down,"
        f"  sum(CASE WHEN {band_sql} THEN 1 ELSE 0 END) AS n_band,"
        f"  sum(CASE WHEN ({up_sql}) OR ({dn_sql}) OR ({band_sql})"
        "       THEN 1 ELSE 0 END) AS n_any,"
        f"  sum(CASE WHEN ({up_sql}) AND ({dn_sql}) AND ({band_sql})"
        "       THEN 1 ELSE 0 END) AS n_all,"
        "   count(*) AS n_rows"
        f" FROM stk_limit WHERE trade_date <= '{_FZ}'",
        conn=con,
    ).iloc[0]
    n_any, n_all = int(row["n_any"]), int(row["n_all"])
    assert n_any > 0, "湖里一行哨兵都没有?先查数据再改这条测试"
    assert n_any == n_all, (
        f"三条腿不再同集:并集 {n_any} 行,交集 {n_all} 行 —— "
        f"up 侧 {int(row['n_up'])} / down 侧 {int(row['n_down'])} /"
        f" band 侧 {int(row['n_band'])}。"
        "湖里出现了只满足一部分腿的编码,哨兵判据必须回去重读数据"
    )


def test_sentinel_population_is_exactly_what_domain_bounds_say(con) -> None:
    """哨兵总体必须与**领域常识**圈出的集合逐行一致 —— 判据完全不来自 cfg。

    这条是三条腿之外的第四份独立判据:只用"股价不可能 > 1 万 / < 0.05 元"
    这种和实现无关的字面量。cfg 里的阈值若被改歪(包括改回 100000.0),
    实现选出的集合会和这里对不上,这条就红。
    """
    hist = lake.query(
        f"SELECT up_limit, down_limit, count(*) AS n FROM stk_limit"
        f" WHERE trade_date <= '{_FZ}'"
        f"   AND (up_limit > {PLAUSIBLE_MAX_PRICE} OR up_limit <= 0"
        f"        OR down_limit < {PLAUSIBLE_MIN_PRICE})"
        " GROUP BY 1, 2 ORDER BY n DESC",
        conn=con,
    )
    assert not hist.empty
    up = hist["up_limit"].to_numpy(dtype="float64")
    dn = hist["down_limit"].to_numpy(dtype="float64")
    got = tr.no_price_limit_mask(up, dn)
    assert got.all(), (
        "领域常识判定「这不是价格」的编码,实现却没标成哨兵:\n"
        f"{hist[~got]}"
    )
    # 反向:实现标出来的行数不能多于领域常识圈出的总体。
    n_domain = int(hist["n"].sum())
    n_impl = int(
        lake.query(
            "SELECT count(*) AS n FROM stk_limit"
            f" WHERE trade_date <= '{_FZ}'"
            f"   AND (up_limit >= {cfg.NO_PRICE_LIMIT_UP_MIN!r} OR up_limit <= 0"
            f"        OR down_limit <= {cfg.NO_PRICE_LIMIT_DOWN_MAX!r}"
            f"        OR up_limit + down_limit <= 0"
            f"        OR {_BAND_SQL} >= {cfg.NO_PRICE_LIMIT_BAND_MAX!r})",
            conn=con,
        )["n"].iloc[0]
    )
    assert n_impl == n_domain, (
        f"实现圈出 {n_impl} 行,领域常识圈出 {n_domain} 行 —— 两者必须一致"
    )


def test_no_price_limit_matches_the_lake_row_for_row(one_year, con) -> None:
    """产物的 `no_price_limit` 必须与**湖里现查**的哨兵集合逐行相同。

    仍然不复述实现:湖侧用领域常识的字面量圈行,和产物标出来的集合做对称差。
    """
    keys = lake.query(
        "SELECT ts_code, trade_date FROM stk_limit"
        f" WHERE trade_date LIKE '{RECOMPUTE_YEAR}%' AND trade_date <= '{_FZ}'"
        f"   AND (up_limit > {PLAUSIBLE_MAX_PRICE} OR up_limit <= 0"
        f"        OR down_limit < {PLAUSIBLE_MIN_PRICE})",
        conn=con,
    )
    from_lake = set(zip(keys["ts_code"], keys["trade_date"]))
    marked = one_year[one_year["no_price_limit"]]
    from_product = set(zip(marked["code"], marked["date_compact"]))
    assert from_lake, f"{RECOMPUTE_YEAR} 年湖里一行哨兵都没有?先查数据"
    assert from_product - from_lake == set(), (
        f"产物多标了湖里没有的哨兵行:{sorted(from_product - from_lake)[:5]}"
    )
    assert from_lake - from_product == set(), (
        f"产物漏标了湖里的哨兵行:{sorted(from_lake - from_product)[:5]}"
    )


def test_sentinel_rows_never_leak_a_price(one_year) -> None:
    """哨兵值绝不许被当成真实价格流出去 —— D1 的**后果**侧断言。

    判据全是领域常识字面量,不引用 cfg。即使将来判据又写歪了,只要有一行
    荒谬价格被判成"可判",这条就红。
    """
    judgable = (
        one_year["has_daily"] & one_year["has_limit"] & ~one_year["no_price_limit"]
    )
    up = one_year.loc[judgable, "up_limit"].to_numpy(dtype="float64")
    dn = one_year.loc[judgable, "down_limit"].to_numpy(dtype="float64")
    assert up.size > 0
    assert up.max() < PLAUSIBLE_MAX_PRICE, (
        f"可判的行里出现了 up_limit={up.max()},那不是价格是哨兵"
    )
    assert dn.min() > PLAUSIBLE_MIN_PRICE, (
        f"可判的行里出现了 down_limit={dn.min()},那不是价格是哨兵"
    )
    band = (up - dn) / (up + dn)
    assert band.max() < PLAUSIBLE_MAX_BAND, (
        f"可判的行里出现了隐含带宽 {band.max():.4f} > ±44% 的监管上限,"
        "那不是真实的涨跌停区间"
    )


def test_the_old_threshold_would_be_caught_by_these_tests(con) -> None:
    """**自证**:把阈值改回 100000.0,上面那几条必须真的红。

    这条把"旧判据确实漏行"钉成一个断言。它一绿,就说明上面几条不是恒真式。
    如果哪天湖里那族 `99999.99x` 编码消失了,这条会红 —— 那时才该重新讨论
    阈值,而不是让测试悄悄退化成没有判别力。
    """
    total = int(
        lake.query(
            "SELECT count(*) AS n FROM stk_limit"
            f" WHERE trade_date <= '{_FZ}' AND down_limit <= 0.01",
            conn=con,
        )["n"].iloc[0]
    )
    legacy = int(
        lake.query(
            "SELECT count(*) AS n FROM stk_limit"
            f" WHERE trade_date <= '{_FZ}' AND up_limit >= 100000.0",
            conn=con,
        )["n"].iloc[0]
    )
    assert legacy < total, (
        f"旧阈值 up_limit>=100000.0 罩住 {legacy} 行,哨兵总体 {total} 行 —— "
        "两者相等就说明这组测试失去判别力了,回去重读数据"
    )
    # 漏掉的那一族必须真的会被现在的实现罩住。
    missed = lake.query(
        "SELECT up_limit, down_limit, count(*) AS n FROM stk_limit"
        f" WHERE trade_date <= '{_FZ}' AND down_limit <= 0.01"
        "   AND NOT (up_limit >= 100000.0) GROUP BY 1, 2",
        conn=con,
    )
    assert not missed.empty, "旧阈值一行都没漏?那 D1 就不成立了,回去重读数据"
    got = tr.no_price_limit_mask(
        missed["up_limit"].to_numpy(dtype="float64"),
        missed["down_limit"].to_numpy(dtype="float64"),
    )
    assert got.all(), f"新判据仍然漏掉:\n{missed[~got]}"


def test_an_unseen_sentinel_encoding_is_still_caught() -> None:
    """湖里**没出现过**的编码也要被罩住 —— band 侧存在的全部理由。

    D1 的教训不是"阈值取错了",是"把判据绑死在见过的取值上"。所以这里喂一个
    湖里根本不存在的编码,断言它照样被识别,并且**旧的一刀切阈值罩不住它**。
    """
    up = np.array([88_888.88, 4_321.0, 12.5], dtype="float64")
    dn = np.array([0.02, 0.03, 10.5], dtype="float64")
    got = tr.no_price_limit_mask(up, dn)
    assert got[0], "88888.88/0.02 这种没见过的编码必须被 band 侧罩住"
    assert got[1], "4321.0/0.03 也是荒谬带宽,必须被罩住"
    assert not got[2], "12.5/10.5 是正常的 ±8.7% 带,不许误判成哨兵"
    # 旧的一刀切阈值对第一条无能为力 —— 这才是 band 侧的价值。
    assert not (up[0] >= 100_000.0)
    # NaN(= has_limit False)不算哨兵。
    nan_row = tr.no_price_limit_mask(
        np.array([np.nan]), np.array([np.nan])
    )
    assert not nan_row[0]


def test_artifact_permissions_block_group_and_world(summary) -> None:
    """红线 5:产物文件 0600、目录 0700。umask 是 002,裸写会落成组可读。"""
    for art in summary["build"]["partitions"]:
        assert art["mode"] == "0o600", f"{art['path']} 权限是 {art['mode']}"
    assert summary["build"]["acceptance_artifact"]["mode"] == "0o600"
    for path in (cfg.TRADABILITY_DIR, cfg.TRADABILITY_ACCEPTANCE_DIR):
        for d in [path, *path.rglob("*")]:
            if d.is_dir():
                assert not (d.stat().st_mode & cfg.FORBIDDEN_MODE_BITS), d


def test_parquet_metadata_carries_the_convention() -> None:
    """parquet 单独流转时带不走数据卡,口径指纹必须写在 schema metadata 里。"""
    import pyarrow.parquet as pq

    meta = {
        k.decode(): v.decode()
        for k, v in (
            pq.ParquetFile(tr.year_partition_path(RECOMPUTE_YEAR))
            .schema_arrow.metadata
            or {}
        ).items()
        if k != b"pandas"
    }
    assert meta["genebench_card"] == "1.2"
    assert meta["beyond_freeze_line"] == "false"
    assert meta["valid_to"] == cfg.FREEZE_DATE
    assert "收盘" in meta["status_convention"]
    assert "SSE" in meta["calendar"]


# ===========================================================================
# 第 2 层:与湖的可还原性 —— 逐行独立重算
# ===========================================================================


def _independent_month(con: Any, month: str) -> pd.DataFrame:
    """**另一份实现**:逐行 python 循环,从三源现场推 `status`。

    刻意不复用 `tradability.classify` —— 复用了就只是把同一段代码跑两遍。
    这里的循环慢得多,但它和产物那套向量化实现是两份独立代码,
    对不上说明至少有一份错了。
    """
    part = f"trade_date={month}-*"
    dly = lake.read_gold(
        tr.DAILY_DS, part, columns=["ts_code", "trade_date", "high", "low", "close"],
        conn=con,
    )
    sus = lake.read_gold(
        tr.SUSPEND_DS, part, columns=["ts_code", "trade_date", "suspend_type"], conn=con
    )
    lim = lake.read_gold(
        tr.LIMIT_DS, part, columns=["ts_code", "trade_date", "up_limit", "down_limit"],
        conn=con,
    )
    d_idx = {(r.ts_code, r.trade_date): r for r in dly.itertuples(index=False)}
    s_idx = {(r.ts_code, r.trade_date): r.suspend_type for r in sus.itertuples(index=False)}
    l_idx = {(r.ts_code, r.trade_date): r for r in lim.itertuples(index=False)}

    tol = cfg.LIMIT_PRICE_TOL
    rows = []
    for key in sorted(set(d_idx) | set(s_idx) | set(l_idx)):
        code, td = key
        d = d_idx.get(key)
        s = s_idx.get(key)
        lm = l_idx.get(key)
        if d is None:
            status = "suspend" if s == "S" else ("no_data" if s != "S" else "suspend")
            up_c = dn_c = up_t = dn_t = False
        else:
            judgable = lm is not None and lm.up_limit is not None
            if judgable:
                # 与 `no_price_limit_mask` 不同源的等价写法:纯 python、逐行、
                # 三条腿分开写一遍,不调用被测函数。
                u = float(lm.up_limit)
                dl = None if lm.down_limit is None else float(lm.down_limit)
                sentinel = u >= cfg.NO_PRICE_LIMIT_UP_MIN or u <= 0.0
                if dl is not None:
                    sentinel = sentinel or dl <= cfg.NO_PRICE_LIMIT_DOWN_MAX
                    sentinel = sentinel or u + dl <= 0.0 or (
                        (u - dl) / (u + dl) >= cfg.NO_PRICE_LIMIT_BAND_MAX
                    )
                if sentinel:
                    judgable = False
            if judgable:
                up_c = abs(float(d.close) - float(lm.up_limit)) < tol
                dn_c = abs(float(d.close) - float(lm.down_limit)) < tol
                up_t = float(d.high) >= float(lm.up_limit) - tol
                dn_t = float(d.low) <= float(lm.down_limit) + tol
            else:
                up_c = dn_c = up_t = dn_t = False
            status = "limit_up" if up_c else ("limit_down" if dn_c else "trade")
        rows.append(
            {
                "code": code,
                "date_compact": td,
                "status": status,
                "has_daily": d is not None,
                "limit_up_close": up_c,
                "limit_down_close": dn_c,
                "limit_touched_up": up_t,
                "limit_touched_down": dn_t,
            }
        )
    return pd.DataFrame(rows)


def test_month_recomputes_row_for_row_from_the_lake(con, one_year) -> None:
    """2021-06 单月:独立实现逐行重算,与产物比。

    **只比 `suspend_basis != 'carried_after_S'` 的行** —— 顺延态需要看月初之前的
    历史,单月重算拿不到那个上下文。被排除的行另有一条断言(见下一个测试)。
    """
    ours = one_year[one_year["date_compact"].str.startswith(RECOMPUTE_MONTH.replace("-", ""))]
    ours = ours[ours["suspend_basis"] != "carried_after_S"]
    theirs = _independent_month(con, RECOMPUTE_MONTH)
    merged = ours.merge(
        theirs, on=["code", "date_compact"], how="inner", suffixes=("_ours", "_ref")
    )
    assert len(merged) > 50_000, f"重算样本太小({len(merged)}),这条测试没有意义"
    for col in (
        "status",
        "has_daily",
        "limit_up_close",
        "limit_down_close",
        "limit_touched_up",
        "limit_touched_down",
    ):
        bad = merged[merged[f"{col}_ours"] != merged[f"{col}_ref"]]
        assert len(bad) == 0, (
            f"{col} 有 {len(bad)} 行对不上,例如:\n"
            f"{bad[['code', 'date_compact', f'{col}_ours', f'{col}_ref']].head()}"
        )


def test_carried_rows_have_no_daily_row_and_no_S_that_day(slim) -> None:
    """被上一条排除掉的顺延行,必须满足顺延的**前提**:缺行、当天无 `S`、无 `R`。"""
    carried = slim[slim["suspend_basis"] == "carried_after_S"]
    assert len(carried) > 0
    assert not carried["has_daily"].any()
    assert carried["suspend_flag"].isna().all()


def test_grid_matches_universe_build_grid(con) -> None:
    """本模块的 `load_grid(FREEZE)` 必须和卡 1.1 的网格**逐日相同**。

    两处各建一份网格是刻意的(本卡要能取到冻结线之外),
    但它们在冻结线以内必须一模一样,否则两张表的日期轴会悄悄错开。
    """
    assert tr.load_grid(cfg.FREEZE_DATE, conn=con).days == ub.load_grid(conn=con).days


def test_calendar_really_only_has_sse(con) -> None:
    """数据卡声称"日历只有 SSE,深市用它是约定不是数据事实"。核这句话。"""
    got = lake.query(
        f"SELECT DISTINCT exchange FROM {tr.CALENDAR_VIEW}", conn=con  # noqa: S608
    )["exchange"].tolist()
    assert got == ["SSE"], f"湖里出现了新交易所 {got} —— 数据卡那句约定要重写了"


def test_suspend_timing_cannot_be_used_as_the_criterion(slim) -> None:
    """`suspend_timing` 非空**不能**当"盘中停牌"的判据 —— 它在早年缺失。

    共享上下文说它"全为 NULL";实测是 0.55% 非空,而且非空的正好是盘中停牌。
    但 2009-2011 年这类行 100% 为空。这条断言把"早年为空"钉死,
    防止有人看到近年 100% 命中就把判据换成它。
    """
    halts = slim[slim["intraday_halt"]]
    assert len(halts) > 0
    early = halts[halts["date_compact"] < "20120101"]
    assert len(early) > 0, "早年一行盘中停牌都没有?先查数据"
    # 早年这些行如果全都有 timing,那"不能当判据"这句话就不成立了
    one_year_full = tr.read_tradability(2009)
    early_full = one_year_full[one_year_full["intraday_halt"]]
    assert len(early_full) > 0
    assert early_full["suspend_timing"].isna().all(), (
        "2009 年的盘中停牌行出现了非空 suspend_timing —— "
        "湖侧回填了?那 tradability 的数据卡要重写"
    )


# ===========================================================================
# 第 3 层:第三方口径交叉验证(limit_list_d)
# ===========================================================================


def test_limit_list_d_is_fully_covered(con, one_year) -> None:
    """`limit_list_d` 不参与本表任何判定,是唯一的**外部真相**。

    * 它的 `U`(涨停)必须**全部**落进我们的 `limit_up_close`;
    * `D`(跌停)全部落进 `limit_down_close`;
    * `Z`(炸板)全部落进 `limit_touched_up` —— 这一条直接证明
      "盘中触板"必须和"收盘封板"分成两列。
    """
    ll = lake.read_gold(
        tr.LIMIT_LIST_DS,
        f"trade_date={RECOMPUTE_MONTH}-*",
        columns=["ts_code", "trade_date", "limit"],
        conn=con,
    )
    assert len(ll) > 1000, f"limit_list_d 在 {RECOMPUTE_MONTH} 只有 {len(ll)} 行"
    ours = one_year.set_index(["code", "date_compact"])

    def _keys(flag: str) -> set:
        sub = ll[ll["limit"] == flag]
        return set(zip(sub["ts_code"], sub["trade_date"]))

    for flag, col in (
        ("U", "limit_up_close"),
        ("D", "limit_down_close"),
        ("Z", "limit_touched_up"),
    ):
        keys = _keys(flag)
        assert keys, f"limit_list_d 里没有 {flag}"
        hit = ours.reindex(sorted(keys))[col]
        missed = hit[~hit.fillna(False).astype(bool)]
        assert len(missed) == 0, (
            f"limit_list_d 说 {flag} 的 {len(missed)} 行,我们的 {col} 是 False:\n"
            f"{list(missed.index[:5])}"
        )


def test_we_are_a_strict_superset_of_limit_list_d_because_of_ST(con, one_year) -> None:
    """我们比 `limit_list_d` 多出来的涨停,必须能被"ST 的 ±5% 涨跌停"解释。

    多出来 682 条不是缺陷,是它的口径不收 ST。判据:这些行的
    ``up_limit / close_{前收近似}`` 集中在 5% 附近,而它收录的集中在 10% / 20%。
    这里不重算前收,直接用一个更硬的量:多出来的这批里,
    **绝大多数**的涨跌幅比例明显低于它收录的那批。
    """
    ll = lake.read_gold(
        tr.LIMIT_LIST_DS,
        f"trade_date={RECOMPUTE_MONTH}-*",
        columns=["ts_code", "trade_date", "limit"],
        conn=con,
    )
    pre = lake.read_gold(
        tr.DAILY_DS,
        f"trade_date={RECOMPUTE_MONTH}-*",
        columns=["ts_code", "trade_date", "pre_close"],
        conn=con,
    )
    u_keys = set(
        zip(ll.loc[ll["limit"] == "U", "ts_code"], ll.loc[ll["limit"] == "U", "trade_date"])
    )
    mine = one_year[
        one_year["limit_up_close"]
        & one_year["date_compact"].str.startswith(RECOMPUTE_MONTH.replace("-", ""))
    ].merge(
        pre.rename(columns={"ts_code": "code", "trade_date": "date_compact"}),
        on=["code", "date_compact"],
        how="left",
    )
    mine = mine[mine["pre_close"] > 0]
    mine["ratio"] = (mine["up_limit"] / mine["pre_close"] - 1) * 100
    in_ll = pd.Series(
        [(c, d) in u_keys for c, d in zip(mine["code"], mine["date_compact"])]
    )
    extra = mine[~in_ll.to_numpy()]
    inside = mine[in_ll.to_numpy()]
    assert len(extra) > 100, f"只多出 {len(extra)} 条?对账结论要重写"
    assert extra["ratio"].median() < 7.0, (
        f"多出来那批的涨跌幅中位数是 {extra['ratio'].median():.2f}%,"
        f"不像 ST 的 ±5% —— 那「它的口径不收 ST」这个解释就站不住了"
    )
    assert inside["ratio"].median() >= 9.0


# ===========================================================================
# 第 4 层:验收 (a) 的两个实测样例
# ===========================================================================


def test_acceptance_slice_is_marked_beyond_freeze(acceptance) -> None:
    frame, meta = acceptance
    assert meta["beyond_freeze_line"] == "true"
    assert meta["valid_to"] == cfg.TRADABILITY_ACCEPTANCE_DATE
    assert "acceptance_only" in meta
    assert set(frame["date_compact"].unique()) == {
        cfg.TRADABILITY_ACCEPTANCE_DATE.replace("-", "")
    }


def _lake_evidence(con: Any, code: str, date: str) -> dict[str, Any]:
    part = f"trade_date={date}"
    return {
        "daily": lake.read_gold(
            tr.DAILY_DS, part, columns=list(tr._DAILY_COLS),
            where=f"ts_code = '{code}'", conn=con,
        ),
        "suspend": lake.read_gold(
            tr.SUSPEND_DS, part, columns=list(tr._SUSPEND_COLS),
            where=f"ts_code = '{code}'", conn=con,
        ),
    }


def test_acceptance_000711_is_suspend_with_no_daily_row(acceptance, con) -> None:
    """验收 (a) 上半:`000711.SZ` = `suspend` 且 `daily` 无行。

    **不信产物**:同时回湖里把原始行捞出来,两边都必须对。
    """
    frame, _ = acceptance
    row = frame[frame["code"] == "000711.SZ"]
    assert len(row) == 1, "验收切片里应该恰好一行 000711.SZ"
    row = row.iloc[0]
    assert row["status"] == "suspend"
    assert not row["has_daily"]
    assert row["suspend_flag"] == "S"
    assert row["suspend_basis"] == "suspend_d_S"

    ev = _lake_evidence(con, "000711.SZ", cfg.TRADABILITY_ACCEPTANCE_DATE)
    assert len(ev["daily"]) == 0, "湖里 daily 竟然有行,产物和源头对不上"
    assert list(ev["suspend"]["suspend_type"]) == ["S"]


def test_acceptance_600491_trades_on_its_resume_day(acceptance, con) -> None:
    """验收 (a) 下半:`600491.SH` = `trade`(当日复牌 `R`)。"""
    frame, _ = acceptance
    row = frame[frame["code"] == "600491.SH"]
    assert len(row) == 1
    row = row.iloc[0]
    assert row["status"] == "trade"
    assert row["has_daily"]
    assert row["suspend_flag"] == "R"
    assert row["suspend_basis"] == "none"
    assert not row["intraday_halt"]

    ev = _lake_evidence(con, "600491.SH", cfg.TRADABILITY_ACCEPTANCE_DATE)
    assert len(ev["daily"]) == 1
    assert list(ev["suspend"]["suspend_type"]) == ["R"]


def test_sample_report_has_ten_rows_with_full_evidence(summary) -> None:
    """验收 (b):取证表必须有 10 条,且每条四个环节的证据都写全了。"""
    assert cfg.TRADABILITY_SAMPLE_REPORT.exists()
    text = cfg.TRADABILITY_SAMPLE_REPORT.read_text(encoding="utf-8")
    ev = summary["sample_10_evidence"]
    assert len(ev) == cfg.TRADABILITY_SAMPLE_DETAIL_N
    assert len(summary["sample_50"]) == cfg.TRADABILITY_SAMPLE_N
    assert summary["sampling"]["seed"] == cfg.TRADABILITY_SAMPLE_SEED
    for e in ev:
        assert e["cal_is_open"] == 1, f"{e['code']} @ {e['date']} 不是交易日?"
        assert f"`{e['code']}`" in text
        assert "`trade_cal`" in text and "`suspend_d`" in text and "`stk_limit`" in text
    # 五档都要被取证覆盖到,否则最难的两类根本没人核过
    assert {e["status"] for e in ev} == set(cfg.TRADABILITY_STATUSES)


def test_sampling_is_reproducible(one_year, summary) -> None:
    """同一个种子必须抽出同一批样本。抽不重复,"人工复核过了"就没有重量。"""
    frame = tr.read_tradability(summary["by_year"][0]["year"])
    a, _, _ = tr.pick_samples(frame, 50, 10, cfg.TRADABILITY_SAMPLE_SEED)
    b, _, _ = tr.pick_samples(frame, 50, 10, cfg.TRADABILITY_SAMPLE_SEED)
    assert a.equals(b)
    c, _, _ = tr.pick_samples(frame, 50, 10, cfg.TRADABILITY_SAMPLE_SEED + 1)
    assert not a.equals(c), "换了种子还抽出同一批?随机数根本没生效"


def test_data_card_numbers_come_from_the_summary(summary) -> None:
    """数据卡里的关键数字必须和摘要逐字一致(数据卡是生成的,不是手写的)。"""
    assert cfg.TRADABILITY_CARD.exists()
    card = cfg.TRADABILITY_CARD.read_text(encoding="utf-8")
    t = summary["totals"]
    for value in (
        t["rows"],
        t["status"]["suspend"],
        t["status"]["no_data"],
        t["suspend_basis"]["carried_after_S"],
        t["no_price_limit"],
    ):
        assert f"{value:,}" in card, f"数据卡里找不到 {value:,}"


# ===========================================================================
# 第 5 层:`classify` 的分支表 + 负控
# ===========================================================================


def _mini(rows: list[dict[str, Any]]) -> pd.DataFrame:
    base = {
        "code": "000001.SZ",
        "date_idx": 0,
        "in_listing_window": True,
        "has_daily": False,
        "has_limit": False,
        "suspend_flag": None,
        "suspend_timing": None,
        "close": np.nan,
        "high": np.nan,
        "low": np.nan,
        "volume": np.nan,
        "up_limit": np.nan,
        "down_limit": np.nan,
    }
    return pd.DataFrame([{**base, **r} for r in rows])


def test_classify_priority_table() -> None:
    """把优先级表逐行喂进 `classify`,一档一档核。"""
    frame = _mini(
        [
            # 0 缺行 + 当天 S          -> suspend / 直接证据
            {"date_idx": 0, "suspend_flag": "S"},
            # 1 缺行 + 什么都没有      -> 顺延自 0            -> suspend / 推断
            {"date_idx": 1},
            # 2 有行(复牌)           -> 顺延中断            -> trade
            {"date_idx": 2, "has_daily": True, "close": 10.0, "high": 10.0, "low": 9.0},
            # 3 缺行 + 无证据          -> no_data
            {"date_idx": 3},
            # 4 有行 + 收盘封涨停      -> limit_up
            {
                "date_idx": 4, "has_daily": True, "has_limit": True,
                "close": 11.0, "high": 11.0, "low": 10.0,
                "up_limit": 11.0, "down_limit": 9.0,
            },
            # 5 有行 + 盘中触板但收盘打开 -> trade + touched
            {
                "date_idx": 5, "has_daily": True, "has_limit": True,
                "close": 10.5, "high": 11.0, "low": 10.0,
                "up_limit": 11.0, "down_limit": 9.0,
            },
            # 6 有行 + 收盘封跌停      -> limit_down
            {
                "date_idx": 6, "has_daily": True, "has_limit": True,
                "close": 9.0, "high": 10.0, "low": 9.0,
                "up_limit": 11.0, "down_limit": 9.0,
            },
            # 7 有行 + S(盘中临时停牌) -> trade,不是 suspend
            {
                "date_idx": 7, "has_daily": True, "suspend_flag": "S",
                "close": 10.0, "high": 10.0, "low": 10.0,
            },
            # 8 哨兵:价格恰好等于 down_limit=0.01 也不许判 limit_down
            {
                "date_idx": 8, "has_daily": True, "has_limit": True,
                "close": 0.01, "high": 0.01, "low": 0.01,
                "up_limit": 999999.999, "down_limit": 0.01,
            },
        ]
    )
    out = tr.classify(frame.copy())
    assert list(out["status"]) == [
        "suspend", "suspend", "trade", "no_data",
        "limit_up", "trade", "limit_down", "trade", "trade",
    ]
    assert list(out["suspend_basis"])[:4] == [
        "suspend_d_S", "carried_after_S", "none", "none",
    ]
    assert bool(out.loc[5, "limit_touched_up"]) and not bool(out.loc[5, "limit_up_close"])
    assert bool(out.loc[7, "intraday_halt"])
    assert bool(out.loc[8, "no_price_limit"])
    assert not bool(out.loc[8, "limit_down_close"])
    assert not bool(out.loc[8, "limit_touched_down"])


def test_classify_carry_stops_at_R() -> None:
    frame = _mini(
        [
            {"date_idx": 0, "suspend_flag": "S"},
            {"date_idx": 1},
            {"date_idx": 2, "suspend_flag": "R"},
            {"date_idx": 3},
        ]
    )
    out = tr.classify(frame.copy())
    assert list(out["status"]) == ["suspend", "suspend", "no_data", "no_data"]


def test_classify_carry_does_not_cross_a_gap() -> None:
    """行域是并集,窗口外的行会有洞。**隔着洞顺延等于凭空断言洞里也停牌。**"""
    frame = _mini(
        [
            {"date_idx": 0, "suspend_flag": "S"},
            {"date_idx": 1},
            {"date_idx": 9},  # 中间 2..8 没有行 —— 断开
        ]
    )
    out = tr.classify(frame.copy())
    assert list(out["status"]) == ["suspend", "suspend", "no_data"]


def test_classify_carry_does_not_cross_codes() -> None:
    frame = _mini(
        [
            {"code": "000001.SZ", "date_idx": 0, "suspend_flag": "S"},
            {"code": "000002.SZ", "date_idx": 1},
        ]
    )
    out = tr.classify(frame.copy())
    assert list(out["status"]) == ["suspend", "no_data"]


def test_negative_control_tampered_status_is_caught(slim) -> None:
    """负控:把一行的 `status` 改掉,自洽检查必须红。"""
    tampered = slim.head(20_000).copy()
    idx = int(np.flatnonzero((tampered["status"] == "trade").to_numpy())[0])
    tampered.loc[idx, "status"] = "suspend"
    got = _recompute_status(tampered)
    assert (got != tampered["status"].to_numpy()).sum() == 1


def test_negative_control_dropping_the_sentinel_guard_would_misjudge() -> None:
    """负控:不排除哨兵,价格 0.01 的票会被误判 `limit_down`。

    这条测试的存在意义是把那个"看起来无害"的哨兵变成一个**被证明过的坑**。

    **上一版只喂 `999999.999` —— 那个值在旧阈值 100000.0 之上,所以旧实现也绿,
    这条负控当时测不到边界(复核 D3)。** 现在把湖里真实出现过的**六种**编码
    逐个喂进去,其中后三种正是旧阈值漏掉的那 1,046 行。
    """
    # (up_limit, down_limit, 旧阈值 up>=100000.0 罩不罩得住)
    encodings = [
        (100_000.0, 0.01, True),
        (1_000_000.0, 0.01, True),
        (999_999.999, 0.01, True),
        (99_999.999, 0.01, False),   # 旧阈值漏掉,751 行
        (99_999.99, 0.0, False),     # 旧阈值漏掉,267 行
        (0.0, 0.0, False),           # 旧阈值漏掉,28 行;连"大于阈值"都不是
    ]
    missed_by_legacy = 0
    for up, dn, legacy_ok in encodings:
        px = max(dn, 0.01)
        frame = _mini(
            [
                {
                    "date_idx": 0, "has_daily": True, "has_limit": True,
                    "close": px, "high": px, "low": px,
                    "up_limit": up, "down_limit": dn,
                }
            ]
        )
        out = tr.classify(frame.copy())
        assert bool(out.loc[0, "no_price_limit"]), f"{up}/{dn} 没被识别成哨兵"
        assert out.loc[0, "status"] == "trade", f"{up}/{dn} 判成了 {out.loc[0,'status']}"
        assert not bool(out.loc[0, "limit_down_close"])
        assert not bool(out.loc[0, "limit_touched_down"])
        if not legacy_ok:
            missed_by_legacy += 1
            assert not (up >= 100_000.0), f"{up} 标注成旧阈值漏掉,但它其实 >= 100000"
    assert missed_by_legacy == 3, (
        "旧阈值必须真的漏掉三种编码 —— 否则这条负控没有判别力"
    )
    # 退化实现(不看哨兵)会怎么判:
    naive = abs(0.01 - 0.01) < cfg.LIMIT_PRICE_TOL
    assert naive, "退化实现确实会判成封跌停 —— 所以哨兵这道闸不能省"
    # 反向:正常价格不许被新判据吞掉。
    frame = _mini(
        [
            {
                "date_idx": 0, "has_daily": True, "has_limit": True,
                "close": 11.0, "high": 11.0, "low": 10.0,
                "up_limit": 11.0, "down_limit": 9.0,
            }
        ]
    )
    out = tr.classify(frame.copy())
    assert not bool(out.loc[0, "no_price_limit"]), "正常 ±10% 带被误判成哨兵"
    assert out.loc[0, "status"] == "limit_up"


def test_tradability_at_refuses_to_read_beyond_the_freeze_line() -> None:
    """越界读**必须抛错**,不能静默返回 None。

    静默返回会让调用方分不清"这天没这只票"和"这天根本不在产物里" ——
    后者是越过红线 7,必须响。
    """
    with pytest.raises(ValueError, match="冻结线"):
        tr.tradability_at("600000.SH", cfg.TRADABILITY_ACCEPTANCE_DATE)


def test_tradability_at_reads_a_real_row(summary) -> None:
    row = tr.tradability_at("600000.SH", f"{RECOMPUTE_YEAR}-06-30")
    assert row is not None
    assert row["code"] == "600000.SH"
    assert row["status"] in cfg.TRADABILITY_STATUSES
    assert tr.tradability_at("NOPE.SH", f"{RECOMPUTE_YEAR}-06-30") is None
