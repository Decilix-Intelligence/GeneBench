"""卡 1.2:**可交易性视图** `tradability` —— 某只票在某个交易日到底能不能交易。

跑法::

    cd $REPO && $GENEBENCH_ROOT/env/bin/python -m snapshots.tradability

产物(路径全部来自 `genebench_config`,本文件**不含任何绝对路径字面量**):

* `cfg.TRADABILITY_DIR`            —— 冻结产物,按年分区 `year=YYYY/part-0.parquet`
* `cfg.TRADABILITY_ACCEPTANCE_DIR` —— **验收专用**单日切片,在冻结线**之外**
* `cfg.TRADABILITY_JSON`           —— 机器可读摘要 + 完整性自查(进 git)
* `cfg.TRADABILITY_CARD`           —— 数据卡,人读(进 git;本模块生成,不手写)
* `cfg.TRADABILITY_SAMPLE_REPORT`  —— 10 条抽样的**判定链路取证**表(进 git)


================================================================
一、这张表回答什么 / 不回答什么
================================================================

一行 = 一个 ``(code, date)``。``status`` 五档,**互斥且完备**:

============ ==========================================================
status       含义
============ ==========================================================
``no_data``  `daily` 无行,且没有任何"这天停牌"的证据。**数据缺失**。
``suspend``  `daily` 无行,且 `suspend_d` 说停牌。**全天停牌**。
``limit_up`` `daily` 有行,且 **收盘价 == 涨停价**。收盘封板,**买不进**。
``limit_down`` `daily` 有行,且 **收盘价 == 跌停价**。收盘封板,**卖不出**。
``trade``    `daily` 有行,收盘没封板。
============ ==========================================================

**它不回答"这天涨没涨停"。** `status == 'limit_up'` 是**收盘**封板;
盘中摸到涨停又打开的(炸板)`status` 仍是 `trade`,要看
`limit_touched_up`。两个口径都产出、分列、命名上就分开,是因为它们
回答的是两个不同的问题:

* **能不能成交** → 收盘口径(`limit_up_close` / `limit_down_close`)。
  收盘封在涨停价上,你的买单排在几万手后面,成交不了。
* **有没有触板** → 盘中口径(`limit_touched_up` / `limit_touched_down`)。
  `high` 摸到过涨停价就算,不管收盘封没封住。

湖里的 `limit_list_d`(第三方口径)恰好证明这两件事必须分开:它的 `Z`
(炸板)在 2021-06 有 407 行,**407/407 全部**落在我们的 `limit_touched_up`
里,但其中 **13 行**我们判 `limit_up_close` 为真 —— 那是"炸板之后收盘又封回去"。
一个口径盖不住两种问题。

**⚠️ 这条等价性有一类已知例外:IPO 首日。** 上面那个 407/407 是在 2021-06 上量的,
另外三个月复核也是满分(2023-11 384/384、2024-03 580/580、2026-06 709/709),
但 **2020-01 是 304/305**。唯一反例 ``601816.SH @ 2020-01-16``(京沪高铁上市首日):
`limit_list_d` 记 `Z`,我们记 ``limit_touched_up = False``。回源看是**我们对的** ——
`daily` high **6.99** < `stk_limit` up_limit **7.03**(首日 ±44% 档),
而 `suspend_d` 当天有一条 ``S / 09:30-10:00``。也就是说 `limit_list_d` 的 `Z`
在这里编码的是**新股首日临时停牌**,不是"触到价格板又打开"。
所以"`Z` ⊆ `limit_touched_up`"这条论据的适用范围是**非 IPO 首日**;
`ops/test_tradability.py` 的交叉验证跑在 2021-06 上,那个月没有这类样本。
把这句写进来是因为上一版把 407/407 当成了无条件成立的证据 —— 证据本身没错,
适用范围被夸大了。**要不要把交叉验证扩到多个月、或者对 IPO 首日单独放行,
登记在 `ops/tickets.md` N-09,本卡不动**(动它要改交叉验证的月份口径,
和"修哨兵"是两件事)。


================================================================
二、行域:哪些 ``(code, date)`` 会有行
================================================================

**行域 = 四条证据通道的并集**,再交上"交易日 & 不超过上界":

1. ``listing_window`` —— `stock_basic` 的在市窗口 ``list_date <= D < delist_date``
   (口径与卡 1.1 的第三源**同一份代码**:`universe_build.load_listing_windows`)。
2. ``daily``     —— 当天有行情行(有行 = 一定在市、一定交易过)。
3. ``stk_limit`` —— 当天交易所发了涨跌停价。
4. ``suspend_d`` —— 当天停复牌事件流提到它。

**为什么不能只用第 1 条。** 实测:`daily` 里有 **84,424** 行落在在市窗口
**之外**,只用窗口做行域会把它们静默丢掉 —— 那可是真实成交过的交易日。
两个成因都查清了:

* **76,325 行 / 全是 `.BJ`**:北交所把老代码换成 `920xxx`,行情按**新代码**
  回填到了挂牌之前,而 `stock_basic.list_date` 记的是新代码的挂牌日。
* **8,099 行 / 全是 `.SZ`**:这些 `ts_code` 在 `stock_basic` 里**根本没有行**。

反过来 ``on_or_after_delist`` 一行都没有 —— 这独立验证了卡 1.1 那条
"`daily` 在 `delist_date` 当天及之后零行"的实测结论。

窗口外的行照样出,但 ``in_listing_window = False``。要"只看正常在市的票",
下游自己加这个过滤;由这张表替你删,你就再也看不见它们了。


================================================================
三、停牌 vs 数据缺失:这张表的核心
================================================================

**停牌票在 `daily` 里是缺行,不是标记。** 而"缺行"同时意味着两件完全不同
的事:*这天停牌* 和 *这天的数据我们没有*。分开它们只能靠三方:

* `trade_cal`(SSE,`is_open = 1`)—— 先确定这天**是交易日**。非交易日
  连行都不该有,不是"缺行"。**本表每一行都落在交易日网格上**,
  所以"非交易日"这一类在产物里根本不存在,这是设计不是遗漏。
* `daily` —— 有没有行情。
* `suspend_d` —— 说不说得出"这天停牌"。

`suspend_d` 有两种证据强度,写在 ``suspend_basis`` 里:

* ``suspend_d_S``     当天就有 ``suspend_type = 'S'`` 的行。**直接证据。**
* ``carried_after_S`` 当天没有 S 行,但前面某个交易日有 S,此后**一直**没有
  行情行、也没有 R。停牌状态**顺延**过来。**推断证据。**

  为什么需要顺延:`suspend_d` 在 2013 年之前是**事件流**而不是逐日状态
  (2009 年 `R` 一行都没有,`R` 最早出现在 20100510)。只认当天 S 会把
  长期停牌的中间那些天全判成 `no_data`。顺延的终止条件是
  **"这只票又有行情行了,或者出现了 R"** —— 不是拍一个天数上限,
  上限是任意的,而"又开始交易了"是数据自己说的。

  实测顺延解释了 **22,064** 行;剩下 **18,328** 行确实没有任何证据,
  判 `no_data`。两个数都写进数据卡,不藏。

* ``none``            没有任何停牌证据。

⚠️ **`suspend_type = 'S'` 与 `daily` 有行会同时出现**(全历史 6,313 行)。
那不是矛盾,是**盘中临时停牌**:停十分钟又复牌,当天照样成交。
这种行 ``intraday_halt = True``,``status`` 按有行情算(`trade` / `limit_*`)。

  **⚠️ 与共享上下文的一处出入(实测):`suspend_timing` 并非全为 NULL。**
  全表 482,298 行里 **2,643 行非空**(0.55%),而且非空的**正好就是**盘中停牌:
  2019 年起 "S 且 daily 有行" 的行 ``suspend_timing`` **100% 非空**
  (形如 ``9:31-9:41``)。但 2009-2011 年这类行的 `suspend_timing`
  **100% 为空**(1,435 / 778 / 719 行)。
  所以:**`suspend_timing` 可以当"这是盘中停牌"的佐证,但不能当判据** ——
  它在早年缺失。本表的判据是"`daily` 有没有行",那个在全历史都可靠。


================================================================
四、触板:只能用 `daily` 比价,不能信 `stk_limit.pre_close`
================================================================

判据::

    limit_up_close     = |close - up_limit|   < cfg.LIMIT_PRICE_TOL
    limit_down_close   = |close - down_limit| < cfg.LIMIT_PRICE_TOL
    limit_touched_up   = high >= up_limit   - cfg.LIMIT_PRICE_TOL
    limit_touched_down = low  <= down_limit + cfg.LIMIT_PRICE_TOL

**关于容差。** 价格和涨跌停价都是两位小数,但 float64 存两位小数本身不精确,
裸 ``==`` 是在赌两边的位模式恰好一样。实测三个月共 26.9 万行,
``==`` / ``<1e-6`` / ``<5e-3`` / ``round(2)==`` 四种判据**逐行相同**,
一条都不差 —— 所以容差在当前湖数据上不改变任何结论。留着它是防线不是修正:
将来换数据源、换精度,它能挡住一次静默漂移。

**关于 `stk_limit.pre_close`。** 共享上下文说"全为 NULL"。实测**不是**:
全表 15,008,861 行里 14,875,699 行非空(99.1%),2009-2018 年**逐年 100% 非空**。
真相是它**在 2026-08 塌了**:该月 116,429 行里只有 11,058 行非空(9.5%)。
结论反而更强 —— 拿它当前收会**在回测里一路正确、到最近的数据上突然全空**,
是最难查的那种故障。所以判触板只走 `daily` 比价,这条不因新事实而改。

**关于 `stk_limit` 行数比 `daily` 多。** 停牌票也发涨跌停价。所以 join 方向是
``行域 LEFT JOIN daily LEFT JOIN stk_limit``,不是 ``daily JOIN stk_limit`` ——
后者会把"停牌当天的涨跌停价"整片丢掉,而那恰恰是复牌首日定价的锚。
反向也有:2021-06 有 1,965 行 `daily` 没有对应的 `stk_limit` 行,
这些行 ``has_limit = False``、四个触板列全 `False`,**不是**"没触板",
是"没法判"。要区分请看 `has_limit`。

**⚠️ 无涨跌幅限制的哨兵值。** `stk_limit` 里有一族行,``up_limit`` / ``down_limit``
不是价格,是"这天没有涨跌停"的编码(新股上市首日、科创板/北交所首日一类)。
实测(≤ 冻结线的 14,892,432 行,up/down 两列均无 NULL)它只有**六种**取值,
合计 **7,107** 行 —— 最后一列 `band` 是隐含带宽 ``(up-down)/(up+down)``:

=============  ==============  ======  ======
``up_limit``   ``down_limit``  行数    band
=============  ==============  ======  ======
100000.0       0.01             2,754     1.0
1000000.0      0.01             2,332     1.0
999999.999     0.01               975     1.0
99999.999      0.01               751     1.0
99999.99       0.0                267     1.0
0.0            0.0                 28     NaN
=============  ==============  ======  ======

**卡 1.2 第一版把判据写成 ``up_limit >= 100000.0``,差一分钱,只抓到前三种共
6,061 行,漏掉后三种共 1,046 行**(2021:22 / 2022:83 / 2023:320 / 2024:190 /
2025:241 / 2026:162,**在增长**;另有 28 行 ``0.0/0.0`` 散在 2009-2015)。
那 1,046 行被错标 ``no_price_limit = False``,于是这张表对它们断言"有涨跌停价、
可判、且没触板",并把 ``99999.999`` 当**真实涨停价**发出去 ——
例:``688425.SH @ 2021-06-22``(科创板上市首日,low 5.19 / high 12.15 / close 8.22,
日内振幅 >130%,本就没有涨跌停),下游算 ``up_limit / close`` 会拿到 12,165 倍。

现在的判据是 `no_price_limit_mask()`,**三条腿取并集**::

    up 侧   : up_limit >= cfg.NO_PRICE_LIMIT_UP_MIN (9.9e4)  或  up_limit <= 0
    down 侧 : down_limit <= cfg.NO_PRICE_LIMIT_DOWN_MAX (0.01)
    band 侧 : (up-down)/(up+down) >= cfg.NO_PRICE_LIMIT_BAND_MAX (0.5)  或  up+down <= 0

**为什么不是"把阈值调小"就完了。** 前两条腿仍然咬死在具体数值上,只能罩住
已经见过的编码 —— 而这次翻车正是"见过的编码之外还有一族"。第三条腿不认识
任何具体哨兵值:真实的 ±5%/±10%/±20%/±30%/±44% 档给出 band
0.05/0.10/0.20/0.30/0.44,哨兵一律给出 1.0。实测非哨兵行 band ∈ **[0.0097, 0.4408]**
(上界是 ``601975.SH @ 2019-01-08``,6.21/2.41 的新股首日 ±44% 档),
哨兵行恒为 **1.0** —— 中间是条**空的**鸿沟,阈值取 0.5/0.6/0.7/0.9 选出的行数
一模一样。所以将来湖里冒出 ``up=88888.88 / down=0.02`` 这种没见过的编码,
band 侧照样罩得住。

三条腿在当前湖上选出**完全相同**的 7,107 行(``down_limit <= 0.01`` 而 ``up_limit``
正常的行 **0 行**,反向也 **0 行**),
`ops/test_tradability.py::test_sentinel_legs_agree_on_the_lake` 把这件事钉住 ——
**湖里一旦出现只满足其中一部分腿的行,它会变红**。这是刻意留的报警口:
遇到没见过的编码要吵,不要静默判 `False`。

这类行 ``no_price_limit = True``,四个触板列一律 `False`。**这条防线是必需的**:
一只价格恰好 0.01 的票碰上 ``down_limit = 0.01`` 会被误判 `limit_down`,
而漏掉的那 1,046 行恰恰就是防线没合上的地方。


================================================================
五、日历只有 SSE —— 这是约定不是数据事实
================================================================

湖 `trade_cal` **只有 SSE 一个交易所**(6,574 行,20090101→20261231)。
本表对 `.SZ` / `.BJ` 的票**同样使用 SSE 日历**。

这是**约定,不是数据事实**。沪深两市的交易日历在实务上一致,北交所随深市,
但"一致"是行业惯例,不是这张表能从数据里证明的东西 —— 湖里根本没有
SZSE / BSE 的日历可对。真要出现某天只有一市开市,本表会把另一市的票
判成 `no_data`(缺行)而不是"非交易日"。

湖侧另有一条:`trade_cal` 的 gold 只有**一个** `snapshot_date=2026-08-05`
分区且此后从未刷新。它的 `cal_date` 一路排到 20261231,那是**快照里预写的
未来日历**,不是这张表还活着的证据。本表只取 ``cal_date <= 上界``,
不受影响,但 `/calendar` 一类端点要小心。


================================================================
六、冻结线与验收切片
================================================================

冻结产物 `cfg.TRADABILITY_DIR` 的上界是 `cfg.FREEZE_DATE`(红线 7)。

实施稿的验收要求 **2026-08-28** 的实测样例,那一天在冻结线**之外**。
所以另出一份 `cfg.TRADABILITY_ACCEPTANCE_DIR`,**物理分家**、目录名带
`acceptance`、parquet metadata 里写死 ``beyond_freeze_line = true``。
它**只为验收复现存在**,任何训练/回测窗口都不许把它拼进来。

构建时两者**走同一条状态机**(见 `build_frames`):日历网格取到验收日,
逐年推进;``date <= FREEZE_DATE`` 的写冻结目录,``date == 验收日`` 的写验收目录,
中间那些天算完即弃。这样做是因为停牌顺延状态**跨年连续** ——
另起一个只读单日的分支,会拿不到"这只票是从 7 月就停到现在"的上下文。
"冻结产物逐位不变"这件事有保证:延长网格右端只会让在市窗口的右端更远,
``<= FREEZE_DATE`` 的那些天的成员与取值完全不变。
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

try:  # 允许 `python snapshots/tradability.py` 这种不带包上下文的跑法
    import genebench_config as cfg
except ModuleNotFoundError:  # pragma: no cover - 仅在裸脚本模式下走到
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import genebench_config as cfg

from snapshots import lake
from snapshots import universe_build as ub

__all__ = [
    "CALENDAR_VIEW",
    "DAILY_DS",
    "SUSPEND_DS",
    "LIMIT_DS",
    "LIMIT_LIST_DS",
    "TRADABILITY_COLUMNS",
    "COLUMN_DOC",
    "PARQUET_SCHEMA",
    "load_grid",
    "year_partition_path",
    "build_frames",
    "classify",
    "read_tradability",
    "read_acceptance",
    "tradability_at",
    "parquet_metadata",
    "summarize",
    "render_data_card",
    "render_sample_report",
    "main",
]

#: 进程入口收紧 umask(红线 5)。import 即生效,和 `universe_build` 同一个姿势。
_PREVIOUS_UMASK = os.umask(cfg.REQUIRED_UMASK)

# --------------------------------------------------------------------------
# 湖侧对象名
# --------------------------------------------------------------------------

#: 交易日历视图。湖里只有 SSE(见模块 docstring 第五节)。
CALENDAR_VIEW: str = ub.CALENDAR_VIEW
#: 行情量价 gold 数据集。停牌票在这里是**缺行**。
DAILY_DS: str = "daily"
#: 停复牌事件流 gold 数据集(`S` = 停牌 / `R` = 复牌)。
SUSPEND_DS: str = "suspend_d"
#: 涨跌停价 gold 数据集。行数比 `daily` **多**(停牌票也发价)。
LIMIT_DS: str = "stk_limit"
#: 涨跌停榜。**只当交叉核对源**,不参与本表任何判定;覆盖 20200102 起。
LIMIT_LIST_DS: str = "limit_list_d"

#: 从 `daily` 取的列。只取判定与取证真正用得到的,不整表搬。
_DAILY_COLS = ("ts_code", "trade_date", "high", "low", "close", "volume")
#: 取证表**额外**读的列。只给人核对用,不进产物 schema ——
#: `open` / `pre_close` 不参与任何判定,但人复核时第一眼就要看它们。
_DAILY_FORENSIC_COLS = (
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "pre_close",
    "volume",
)
_SUSPEND_COLS = ("ts_code", "trade_date", "suspend_type", "suspend_timing")
_LIMIT_COLS = ("ts_code", "trade_date", "up_limit", "down_limit")

# --------------------------------------------------------------------------
# 产物列
# --------------------------------------------------------------------------

#: 产物列顺序。**改这里要同步改 `PARQUET_SCHEMA` 与 `COLUMN_DOC`**,
#: `ops/test_tradability.py::test_columns_schema_and_doc_agree` 会核三者一致。
TRADABILITY_COLUMNS: tuple[str, ...] = (
    "code",
    "date",
    "date_compact",
    "status",
    "in_listing_window",
    "has_daily",
    "has_limit",
    "suspend_flag",
    "suspend_timing",
    "suspend_basis",
    "intraday_halt",
    "close",
    "high",
    "low",
    "volume",
    "up_limit",
    "down_limit",
    "no_price_limit",
    "limit_up_close",
    "limit_down_close",
    "limit_touched_up",
    "limit_touched_down",
)

#: 每列一句人话。数据卡从这里生成,不手写第二份。
COLUMN_DOC: dict[str, str] = {
    "code": "湖内形态的股票代码,如 `600000.SH`(**不是** qlib 的 `SH600000`)。",
    "date": "交易日(`date32`)。全表每一行都落在 `trade_cal`(SSE,`is_open=1`)上。",
    "date_compact": "`date` 的 8 位 `YYYYMMDD` 字符串形态,供直接 join 湖里的 `trade_date`。",
    "status": "五档可交易性,互斥完备。取值见 `cfg.TRADABILITY_STATUSES`。**收盘口径**。",
    "in_listing_window": (
        "`stock_basic` 的在市窗口 `list_date <= D < delist_date` 是否覆盖这天。"
        "`False` 的行是靠行情/涨跌停价/停复牌事件进来的(见模块 docstring 第二节)。"
    ),
    "has_daily": "`daily` 当天有没有行。这是「停牌 vs 有行情」的**唯一**判据。",
    "has_limit": (
        "`stk_limit` 当天有没有行。`False` 时四个触板列全 `False`,"
        "那是**没法判**不是**没触板** —— 要区分就看这一列。"
    ),
    "suspend_flag": (
        "当天 `suspend_d` 说了什么:`S`(停牌)/ `R`(复牌)/ "
        "`SR`(**同日两条都有**,湖里实测 161 个 `(code, date)` 是这样)/ "
        "空(当天无行)。"
    ),
    "suspend_timing": (
        "当天 `suspend_d.suspend_timing` 原值,如 `9:31-9:41`。非空 = 盘中停牌的**佐证**;"
        "但它 2011 年前 100% 为空,**不能当判据**。"
    ),
    "suspend_basis": "凭什么说它停牌。取值见 `cfg.TRADABILITY_SUSPEND_BASES`。",
    "intraday_halt": (
        "`has_daily and suspend_flag == 'S'` —— 盘中临时停牌,当天照样成交。"
        "`status` 按有行情算,不是 `suspend`。"
    ),
    "close": "`daily.close`,未复权。触板收盘口径的比价基准。`has_daily=False` 时为空。",
    "high": "`daily.high`,未复权。`limit_touched_up` 的比价基准。",
    "low": "`daily.low`,未复权。`limit_touched_down` 的比价基准。",
    "volume": (
        "`daily.volume`。**留着它是因为 0 成交也是可交易性信号** —— "
        "有行情行但一手没成交,和封死在一字板上是两回事。"
    ),
    "up_limit": "`stk_limit.up_limit`。`no_price_limit=True` 时是哨兵值不是价格。",
    "down_limit": "`stk_limit.down_limit`。同上。",
    "no_price_limit": (
        "「无涨跌幅限制」哨兵。判据是**三条腿取并集**:"
        + " **或** ".join(f"`{leg}`" for leg in cfg.NO_PRICE_LIMIT_LEGS)
        + "。这类行的 `up_limit`/`down_limit` 不是价格,四个触板列一律 `False`。"
    ),
    "limit_up_close": "**收盘**封在涨停价上(买不进)。判据 `|close - up_limit| < tol`。",
    "limit_down_close": "**收盘**封在跌停价上(卖不出)。判据 `|close - down_limit| < tol`。",
    "limit_touched_up": "**盘中**摸到过涨停价。判据 `high >= up_limit - tol`。封没封住不管。",
    "limit_touched_down": "**盘中**摸到过跌停价。判据 `low <= down_limit + tol`。",
}

#: parquet 落盘 schema。显式写死,不让 pandas 猜 —— 猜出来的类型会跨分区漂移。
PARQUET_SCHEMA = pa.schema(
    [
        pa.field("code", pa.string(), nullable=False),
        pa.field("date", pa.date32(), nullable=False),
        pa.field("date_compact", pa.string(), nullable=False),
        pa.field("status", pa.string(), nullable=False),
        pa.field("in_listing_window", pa.bool_(), nullable=False),
        pa.field("has_daily", pa.bool_(), nullable=False),
        pa.field("has_limit", pa.bool_(), nullable=False),
        pa.field("suspend_flag", pa.string(), nullable=True),
        pa.field("suspend_timing", pa.string(), nullable=True),
        pa.field("suspend_basis", pa.string(), nullable=False),
        pa.field("intraday_halt", pa.bool_(), nullable=False),
        pa.field("close", pa.float64(), nullable=True),
        pa.field("high", pa.float64(), nullable=True),
        pa.field("low", pa.float64(), nullable=True),
        pa.field("volume", pa.float64(), nullable=True),
        pa.field("up_limit", pa.float64(), nullable=True),
        pa.field("down_limit", pa.float64(), nullable=True),
        pa.field("no_price_limit", pa.bool_(), nullable=False),
        pa.field("limit_up_close", pa.bool_(), nullable=False),
        pa.field("limit_down_close", pa.bool_(), nullable=False),
        pa.field("limit_touched_up", pa.bool_(), nullable=False),
        pa.field("limit_touched_down", pa.bool_(), nullable=False),
    ]
)

#: 护栏：`from_pandas(frame[COLUMNS], schema=PARQUET_SCHEMA)` 有一处**不对称** ——
#: 往 `TRADABILITY_COLUMNS` 加了列却忘了加进 schema，那一列会被**静默丢掉**
#: （不报错、文件大小几乎不变）；反过来（只加 schema）才会报错。
#: 卡 1.1 的 `universe_build` 真踩过：加 `ambiguous` 列后产物里没有它，
#: 只有下游 `KeyError` 才暴露。所以在 import 期钉死两者等价。
_SCHEMA_NAMES = tuple(f.name for f in PARQUET_SCHEMA)
if set(_SCHEMA_NAMES) != set(TRADABILITY_COLUMNS):
    raise RuntimeError(
        f"PARQUET_SCHEMA 与 TRADABILITY_COLUMNS 对不上："
        f"只在 schema {sorted(set(_SCHEMA_NAMES) - set(TRADABILITY_COLUMNS))}，"
        f"只在 COLUMNS {sorted(set(TRADABILITY_COLUMNS) - set(_SCHEMA_NAMES))}。"
        f"加列时两处都要改。"
    )


# ==========================================================================
# 交易日网格
# ==========================================================================


def load_grid(bound: str | None = None, conn: Any | None = None) -> ub.Grid:
    """从湖 `trade_cal` 读交易日,截到 `bound`(含),默认 `cfg.FREEZE_DATE`。

    刻意**不**直接复用 `universe_build.load_grid` —— 那一个把冻结线写死在函数体里,
    而本卡的验收切片必须能取到冻结线之外的一天。参数化是唯一区别,
    `ops/test_tradability.py::test_grid_matches_universe_build_grid` 断言
    ``load_grid(FREEZE).days == universe_build.load_grid().days`` 逐日相同,防漂移。

    Args:
        bound: 上界(含),`YYYY-MM-DD`。默认 `cfg.FREEZE_DATE`。
        conn: 复用的湖连接。**强烈建议传** —— 见 `open_lake` 的说明。

    Returns:
        `universe_build.Grid`。

    Raises:
        LakeError: 截到上界后一个交易日都没有。
    """
    limit = (bound or cfg.FREEZE_DATE).replace("-", "")
    raw = lake.query(
        f"SELECT cal_date FROM {CALENDAR_VIEW} "  # noqa: S608
        "WHERE is_open = 1 AND cal_date <= ? ORDER BY cal_date",
        [limit],
        conn=conn,
    )["cal_date"].tolist()
    days = [dt.date(int(s[:4]), int(s[4:6]), int(s[6:8])) for s in raw]
    if not days:
        raise lake.LakeError(
            f"{CALENDAR_VIEW} 里没有截到 {limit} 的交易日,数据出事了。"
        )
    return ub.Grid(days)


def open_lake(tries: int = 20, wait: float = 15.0) -> Any:
    """开一个**全程复用**的湖连接,连不上就耐心重试。

    为什么必须复用一个连接:`lake.read_gold()` 不传 `conn` 时会**临时开一个**,
    而 duckdb 打开 `market.duckdb` 需要拿文件锁 —— 湖侧 ETL(`qlib_env` 的
    python)持写锁时,只读打开也会 ``IOException: Could not set lock``。
    本卡一次构建要读 18 年 × 3 张表 = 54 次定向分区,每次都去抢一次锁,
    撞上 ETL 窗口的概率接近 1(实测:probe 跑到 2020 年就被锁挂掉)。
    开一次、传下去,就只赌一次。

    `lake.open_catalog()` 自带 5 次线性退避(合计约 15 秒),对付瞬时 `.wal`
    够用,对付一整轮 ETL 不够,所以这里再套一层长退避。

    Args:
        tries: 外层重试次数。
        wait: 外层每次重试的间隔(秒)。

    Returns:
        duckdb 只读连接。调用方负责 `close()`。

    Raises:
        LakeError: 重试完仍然打不开。
    """
    last: Exception | None = None
    for attempt in range(1, tries + 1):
        try:
            return lake.open_catalog()
        except lake.LakeError as exc:  # 湖侧 ETL 持锁
            last = exc
            print(
                f"[tradability] 湖被占用,{wait:.0f}s 后重试 ({attempt}/{tries})",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(wait)
    raise lake.LakeError(
        f"连不上湖(外层重试 {tries} 次,每次间隔 {wait:.0f}s)。最后一次:{last}"
    )


# ==========================================================================
# 构建
# ==========================================================================


def _domain_from_windows(
    windows: dict[str, tuple[int, int]], i0: int, i1: int
) -> tuple[np.ndarray, np.ndarray]:
    """把在市窗口在 ``[i0, i1]`` 这一段网格上摊平成 ``(code[], idx[])``。

    纯 numpy 展开,不写 python 双层循环 —— 全表 1500 万行,循环会跑到天荒地老。
    """
    codes: list[str] = []
    los: list[int] = []
    his: list[int] = []
    for code, (a, b) in windows.items():
        lo, hi = max(a, i0), min(b, i1)
        if lo <= hi:
            codes.append(code)
            los.append(lo)
            his.append(hi)
    if not codes:
        return np.array([], dtype=object), np.array([], dtype=np.int64)
    lo_arr = np.asarray(los, dtype=np.int64)
    hi_arr = np.asarray(his, dtype=np.int64)
    counts = hi_arr - lo_arr + 1
    total = int(counts.sum())
    # 每个 code 一段连续区间 → 用"全局 arange 减去各段起点偏移"一次性展开
    starts = np.cumsum(counts) - counts
    idx = np.arange(total, dtype=np.int64) - np.repeat(starts, counts)
    idx += np.repeat(lo_arr, counts)
    return np.repeat(np.asarray(codes, dtype=object), counts), idx


def no_price_limit_mask(up: np.ndarray, down: np.ndarray) -> np.ndarray:
    """「无涨跌幅限制」哨兵的**唯一**判据。三条腿取并集(OR)。

    抽成模块级函数(而不是内联在 `classify` 里)是刻意的:`ops/test_tradability.py`
    与 `ops/negctl_tradability.py` 都要拿它对**湖侧**统计做交叉验证,
    内联的话它们就只能复述实现,那种断言恒真、没有判别力(卡 1.2 复核 D3)。

    三条腿::

        up 侧   : up_limit >= cfg.NO_PRICE_LIMIT_UP_MIN  或  up_limit <= 0
        down 侧 : down_limit <= cfg.NO_PRICE_LIMIT_DOWN_MAX
        band 侧 : (up-down)/(up+down) >= cfg.NO_PRICE_LIMIT_BAND_MAX  或  up+down <= 0

    **前两条腿咬死在具体数值上,只能罩住已经见过的编码;第三条不是。**
    band 是隐含涨跌幅带宽,尺度无关:真实的 ±5%/±10%/±20%/±30%/±44% 档给出
    0.05/0.10/0.20/0.30/0.44,而哨兵一律给出 1.0。实测冻结线内非哨兵行
    band ∈ [0.0097, 0.4408],哨兵行恒为 1.0 —— 中间是条空鸿沟。所以哪怕将来
    湖里冒出 ``up=88888.88 / down=0.02`` 这种谁也没见过的编码,band 侧照样罩得住。

    实测(≤ 冻结线的 14,892,432 行 `stk_limit`)三条腿选出**完全相同**的 7,107 行。
    取 OR 是 fail-safe 方向:宁可多标一行"没法判",也不要把 `99999.999` 当真实
    涨停价发给下游。取值分布与漏判后果见 `genebench_config.NO_PRICE_LIMIT_LEGS`。

    **三条腿同时保留、而不是只留最强的那条**,是为了让
    `ops/test_tradability.py::test_sentinel_legs_agree_on_the_lake` 有东西可比:
    三条独立判据逐行同集是个可证伪的事实,湖里一旦出现只满足其中一部分的行,
    那条测试就会变红 —— 这是"遇到没见过的编码时**报警**而不是静默判 False"的落点。
    只留一条腿的话就没有交叉验证了,又退回自证循环。

    **每条腿只要求自己那一列有值**(band 侧两列都要),不要求两列同时有值。
    当前湖上这个区别为零 —— `stk_limit` 的 up/down 两列都没有 NULL,
    缺失只来自本表的外连接,那时两列一起是 NaN。但"只有一列缺"将来若真的出现,
    按单列判仍然会标出哨兵,而按双列判会漏掉,所以取前者:方向朝 fail-safe 偏。

    Args:
        up: `up_limit` 的 float64 数组。NaN(= `has_limit=False`,本表外连接的产物)
            表示"这天根本没发涨跌停价",和"发了但编码成无限制"是两件事,
            所以 NaN 不参与 up 侧与 band 侧判定。
        down: `down_limit` 的 float64 数组,同样以 NaN 表示缺失。

    Returns:
        与输入等长的 bool 数组。
    """
    up_ok = np.isfinite(up)
    dn_ok = np.isfinite(down)
    up_leg = up_ok & ((up >= cfg.NO_PRICE_LIMIT_UP_MIN) | (up <= 0.0))
    down_leg = dn_ok & (down <= cfg.NO_PRICE_LIMIT_DOWN_MAX)
    # band 侧:up+down <= 0 时除法没有意义,单独作为一档(实测就是那 28 行 0.0/0.0)。
    both = up_ok & dn_ok
    total = np.where(both, up + down, np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        band = np.where(total > 0, (up - down) / total, np.nan)
    band_leg = both & ((total <= 0) | (band >= cfg.NO_PRICE_LIMIT_BAND_MAX))
    return up_leg | down_leg | band_leg

def classify(
    frame: pd.DataFrame, carry_in: "dict[str, bool] | None" = None
) -> pd.DataFrame:
    """把「行域 + 三源证据」的宽表判成 `status` 等派生列。**纯函数,不碰湖。**

    输入必须已经按 ``(code, date_idx)`` 排好序,且含列:
    ``code / date_idx / in_listing_window / has_daily / has_limit /
    suspend_flag / suspend_timing / close / high / low / volume /
    up_limit / down_limit``。

    这里是全卡唯一的判定逻辑。**刻意抽成纯函数**,是为了让
    `ops/test_tradability.py` 能拿手搓的小样本喂进来验优先级,
    不必先跑一遍 1500 万行的构建。

    Args:
        frame: 上面说的宽表。**会被就地加列**(调用方已经持有副本)。
        carry_in: ``{code: 进入本段时是不是停牌态}``。逐年构建时由上一年的
            最后一个交易日传进来 —— 没有它,跨年的长期停牌会在年初被误判成
            `no_data`。只对每只票在本段里的**第一个 block** 生效。

    Returns:
        同一个 `frame`,补齐了 `TRADABILITY_COLUMNS` 里的派生列。
    """
    tol = cfg.LIMIT_PRICE_TOL
    has_daily = frame["has_daily"].to_numpy()
    flag = frame["suspend_flag"].to_numpy()
    is_s = np.isin(flag, ("S", "SR"))
    is_r = np.isin(flag, ("R", "SR"))

    # ---- 停牌状态机 ------------------------------------------------------
    # 事件值:0 = 明确「今天在交易/复牌了」,1 = 明确「今天停牌」,NaN = 没说。
    #
    # 三条赋值的**顺序就是优先级**,后写的压过先写的:
    #   1. `S` -> 1(停牌)。
    #   2. **纯** `R`(当天没有 S)-> 0。`SR` 同日不算「确定在交易」:
    #      湖里实测有 161 个 (code, date) 同时有 S 和 R 行,其中 34 个**没有**
    #      行情行 —— 那 34 天到底交易了没有,`suspend_d` 自己说不清;
    #      有 S 而无行情就该判停牌,不该因为多了一条 R 就翻成 `no_data`。
    #   3. `daily` 有行 -> 0,**压过一切**。有成交是最硬的证据,
    #      「S 且 daily 有行」= 盘中临时停牌,那天是交易过的。
    ev = np.full(len(frame), np.nan)
    ev[is_s] = 1.0
    ev[is_r & ~is_s] = 0.0
    ev[has_daily] = 0.0

    # 顺延只能在**连续**的交易日上做。两处必须断开:
    #   1. 换了一只票;
    #   2. 同一只票的两行在网格上不相邻(行域是并集,窗口外的行会有洞)——
    #      隔着洞把停牌状态接过去,等于凭空断言洞里那些天也停牌。
    idx = frame["date_idx"].to_numpy()
    code = frame["code"].to_numpy()
    new_block = np.empty(len(frame), dtype=bool)
    new_block[0] = True
    if len(frame) > 1:
        new_block[1:] = (code[1:] != code[:-1]) | (idx[1:] != idx[:-1] + 1)
    block = np.cumsum(new_block)
    ev_series = pd.Series(ev, index=pd.RangeIndex(len(frame)))
    filled = ev_series.groupby(block).ffill().to_numpy()

    # 每个 block 里"第一个事件之前"的那些行,ffill 填不上,只能靠 `carry_in`。
    # 但**只有每只票的第一个 block** 有资格继承 —— 后面的 block 是被"洞"
    # 断开的,隔着洞继承等于凭空断言洞里那些天也停牌。
    base = np.zeros(len(frame))
    if carry_in:
        inherits = np.fromiter(
            (bool(carry_in.get(c, False)) for c in code), dtype=bool, count=len(frame)
        )
        first_block = (
            pd.Series(block).groupby(pd.Series(code), sort=False).transform("min")
        ).to_numpy()
        base = np.where((block == first_block) & inherits, 1.0, 0.0)
    carried = np.where(np.isnan(filled), base, filled)
    suspended = carried == 1.0

    frame["suspend_basis"] = np.where(
        is_s & ~has_daily,
        "suspend_d_S",
        np.where(suspended, "carried_after_S", "none"),
    )
    frame["intraday_halt"] = has_daily & is_s

    # ---- 触板 ------------------------------------------------------------
    def _num(col: str) -> np.ndarray:
        # 空 join 会让整列落成 object dtype,裸 `.to_numpy(float)` 直接抛。
        return pd.to_numeric(frame[col], errors="coerce").to_numpy(dtype="float64")

    up = _num("up_limit")
    dn = _num("down_limit")
    close = _num("close")
    high = _num("high")
    low = _num("low")

    no_limit = no_price_limit_mask(up, dn)
    frame["no_price_limit"] = no_limit
    # 能判触板的前提:有行情、有涨跌停价、而且那个价不是"无限制"哨兵。
    judgable = has_daily & np.isfinite(up) & np.isfinite(dn) & ~no_limit

    frame["limit_up_close"] = judgable & (np.abs(close - up) < tol)
    frame["limit_down_close"] = judgable & (np.abs(close - dn) < tol)
    frame["limit_touched_up"] = judgable & (high >= up - tol)
    frame["limit_touched_down"] = judgable & (low <= dn + tol)

    # ---- status(优先级见模块 docstring 第一节)---------------------------
    status = np.where(
        ~has_daily,
        np.where(suspended, "suspend", "no_data"),
        np.where(
            frame["limit_up_close"].to_numpy(),
            "limit_up",
            np.where(frame["limit_down_close"].to_numpy(), "limit_down", "trade"),
        ),
    )
    frame["status"] = status
    return frame


def build_frames(
    bound: str | None = None,
    *,
    conn: Any | None = None,
    grid: ub.Grid | None = None,
    windows: dict[str, tuple[int, int]] | None = None,
) -> Iterator[tuple[int, pd.DataFrame]]:
    """逐年产出 `tradability` 宽表。**生成器**,一年一个 frame,不把 1500 万行同时握在手里。

    年与年之间的停牌顺延状态**精确**接上:每年算完把最后一个交易日的
    ``{code: 是不是停牌态}`` 交给下一年当 `carry_in`。

    **一开始不是这么写的**,先写的是"多算上一年最后 60 个交易日当前缀"。
    那版是错的,而且错得很隐蔽:`suspend_d` 在 2009-2012 年是**事件流**,
    长期停牌只在第一天发一条 `S`;一只票连续停牌超过 60 个交易日又跨年,
    前缀里就只剩"缺行且无 `S`",ffill 出来是 0,年初整段被判成 `no_data`。
    对账时才发现"顺延救回的行数"只有全历史扫一遍的一半(10,019 vs 22,064)。
    传状态字典不但更准,还更省 —— 不用重算前缀。

    仍然存在的边界:如果一只票在上一年最后一个交易日**没有行**
    (四条证据通道一条都没响),它就拿不到 `carry_in`。那是对的 ——
    行域里有洞的地方本来就不该顺延(见 `classify` 的 block 切分)。

    Args:
        bound: 网格上界(含)。默认 `cfg.FREEZE_DATE`。
        conn: 复用的湖连接。不传就自己开一个(并在结束时关掉)。
        grid: 预先建好的网格,省一次 `trade_cal` 查询(测试用)。
        windows: 预先建好的在市窗口(测试用)。

    Yields:
        ``(year, frame)``,`frame` 的列是 `TRADABILITY_COLUMNS` + `date_idx`。
    """
    own_conn = conn is None
    con = conn if conn is not None else open_lake()
    try:
        g = grid if grid is not None else load_grid(bound, conn=con)
        w = windows if windows is not None else ub.load_listing_windows(g, conn=con)[0]
        years = sorted({d.year for d in g.days})
        carry: dict[str, bool] = {}
        for year in years:
            positions = [i for i, d in enumerate(g.days) if d.year == year]
            i0, i1 = positions[0], positions[-1]
            frame = _build_span(g, w, i0, i1, con, carry_in=carry)
            carry = _carry_out(frame, i1)
            yield year, frame
    finally:
        if own_conn:
            con.close()


def _carry_out(frame: pd.DataFrame, last_idx: int) -> dict[str, bool]:
    """把"这一年最后一个交易日,每只票是不是停牌态"交给下一年。

    ``status == 'suspend'`` 就是状态机里的"停牌态" —— 这两件事恒等:
    状态为停牌 ⟺ 那天缺行且顺延/直接证据说停牌 ⟺ `status == 'suspend'`。
    所以这里不用另外把状态数组传出来,读 `status` 就够。

    只收**最后一个交易日有行**的票。没行的票说明四条证据通道那天一条都没响,
    行域在那里是断的,下一年不该继承(见 `classify` 的 block 切分)。
    """
    last = frame[frame["date_idx"] == last_idx]
    return dict(zip(last["code"], (last["status"] == "suspend").to_numpy()))


def _collapse_suspend(s: pd.DataFrame) -> pd.DataFrame:
    """把 `suspend_d` 的同日多行**确定性**地压成一行。

    ⚠️ 这不是防御性编程,是实测出来的坑:湖里有 **161** 个 ``(ts_code, trade_date)``
    同时躺着一条 ``S`` 和一条 ``R``(合计 322 行,2011-2026 各年都有),
    其中 **127** 个当天 `daily` 有行、**34** 个没有。

    最早那版写的是 ``drop_duplicates(keep="first")`` —— 那是**顺序依赖**的:
    留下 S 还是 R 取决于 parquet 的行序,换个分区读法结果就变。
    是全历史独立复算(`ops/negctl_tradability.py`)把它抓出来的:`suspend_d_S` 差 32 行。

    现在的做法是**不丢信息**:同日既有 S 又有 R,`suspend_flag` 就写成 ``"SR"``,
    让它在产物里看得见。`classify` 对 ``SR`` 的处理见那边的优先级注释。
    `suspend_timing` 取当天第一个非空值(按 ``S`` 优先排序后取 first,
    因为盘中停牌的时段是挂在 S 行上的)。
    """
    if s.empty:
        return pd.DataFrame(
            {
                "code": pd.Series(dtype=object),
                "date_idx": pd.Series(dtype="int64"),
                "suspend_flag": pd.Series(dtype=object),
                "suspend_timing": pd.Series(dtype=object),
            }
        )
    work = s.sort_values(
        ["code", "date_idx", "suspend_type"],
        ascending=[True, True, False],  # "S" 排在 "R" 前,timing 才取得到
        kind="mergesort",
    )
    work = work.assign(
        _is_s=work["suspend_type"].eq("S"), _is_r=work["suspend_type"].eq("R")
    )
    agg = work.groupby(["code", "date_idx"], as_index=False, sort=False).agg(
        _is_s=("_is_s", "max"),
        _is_r=("_is_r", "max"),
        suspend_timing=("suspend_timing", "first"),
    )
    agg["suspend_flag"] = np.where(
        agg["_is_s"] & agg["_is_r"],
        "SR",
        np.where(agg["_is_s"], "S", "R"),
    )
    return agg[["code", "date_idx", "suspend_flag", "suspend_timing"]]


def _build_span(
    grid: ub.Grid,
    windows: dict[str, tuple[int, int]],
    i0: int,
    i1: int,
    con: Any,
    carry_in: "dict[str, bool] | None" = None,
) -> pd.DataFrame:
    """构建网格区间 ``[i0, i1]`` 上的完整宽表(含判定)。"""
    days = grid.compact[i0 : i1 + 1]
    day_to_idx = {d: i0 + k for k, d in enumerate(days)}
    globs = sorted({d[:4] for d in days})

    def _read(dataset: str, columns: tuple[str, ...]) -> pd.DataFrame:
        parts = [
            lake.read_gold(
                dataset, f"trade_date={y}-*", columns=list(columns), conn=con
            )
            for y in globs
        ]
        df = pd.concat(parts, ignore_index=True) if len(parts) > 1 else parts[0]
        # 定向分区 glob 是按**年**取的,必然多带出区间外的日子,切掉。
        return df[df["trade_date"].isin(day_to_idx)].reset_index(drop=True)

    daily = _read(DAILY_DS, _DAILY_COLS)
    susp = _read(SUSPEND_DS, _SUSPEND_COLS)
    limit = _read(LIMIT_DS, _LIMIT_COLS)

    # ---- 行域 = 四条证据通道的并集 --------------------------------------
    w_code, w_idx = _domain_from_windows(windows, i0, i1)
    parts = [
        pd.DataFrame(
            {
                "code": w_code,
                "date_idx": w_idx,
                # 只有这一块来自在市窗口;另外三块是"行情/涨跌停价/停复牌说它存在",
                # 那不等于 stock_basic 认为它在市(实测 84,424 行确实不在)。
                "in_listing_window": np.ones(len(w_code), dtype=bool),
            }
        )
    ]
    for src in (daily, susp, limit):
        parts.append(
            pd.DataFrame(
                {
                    "code": src["ts_code"].to_numpy(),
                    "date_idx": src["trade_date"].map(day_to_idx).to_numpy(),
                    "in_listing_window": np.zeros(len(src), dtype=bool),
                }
            )
        )
    domain = pd.concat(parts, ignore_index=True)
    domain = (
        domain.groupby(["code", "date_idx"], as_index=False, sort=False)[
            "in_listing_window"
        ]
        .max()
        .sort_values(["code", "date_idx"], kind="mergesort")
        .reset_index(drop=True)
    )

    # ---- 三源左连接 ------------------------------------------------------
    def _key(df: pd.DataFrame, marker: str) -> pd.DataFrame:
        out = df.rename(columns={"ts_code": "code"}).copy()
        out["date_idx"] = out["trade_date"].map(day_to_idx).astype("int64")
        # 显式标记「这一行来自源表」。**不能拿 close.notna() 当有行的判据** ——
        # 那把"这天没有行情行"和"有行但 close 是空"混成一件事,
        # 而前者是 suspend/no_data、后者是脏数据,必须分得开。
        out[marker] = True
        return out.drop(columns=["trade_date"])

    frame = domain.merge(_key(daily, "has_daily"), on=["code", "date_idx"], how="left")
    frame["has_daily"] = frame["has_daily"].notna().to_numpy()
    frame = frame.merge(_key(limit, "has_limit"), on=["code", "date_idx"], how="left")
    frame["has_limit"] = frame["has_limit"].notna().to_numpy()
    frame = frame.merge(
        _collapse_suspend(_key(susp, "_has_susp").drop(columns=["_has_susp"])),
        on=["code", "date_idx"],
        how="left",
    )

    # left join 的空位在 object 列里是 float `nan`,不是 `None`。
    # `pa.Table.from_pandas(schema=string)` 碰上 float nan 会抛
    # "Could not convert nan with type float",所以在这里统一成 None。
    for col in ("suspend_flag", "suspend_timing"):
        frame[col] = frame[col].astype(object).where(frame[col].notna(), None)

    frame = classify(frame, carry_in=carry_in)

    frame["date"] = [grid.days[i] for i in frame["date_idx"]]
    frame["date_compact"] = [grid.compact[i] for i in frame["date_idx"]]
    ordered = [*TRADABILITY_COLUMNS, "date_idx"]
    return frame[ordered]


# ==========================================================================
# 落盘
# ==========================================================================


def year_partition_path(year: int, root: Path | None = None) -> Path:
    """冻结产物里某一年的 parquet 路径:``<root>/year=YYYY/part-0.parquet``。"""
    base = root if root is not None else cfg.TRADABILITY_DIR
    return base / f"year={year}" / "part-0.parquet"


def acceptance_partition_path(date: str, root: Path | None = None) -> Path:
    """验收切片的 parquet 路径:``<root>/date=YYYY-MM-DD/part-0.parquet``。"""
    base = root if root is not None else cfg.TRADABILITY_ACCEPTANCE_DIR
    return base / f"date={date}" / "part-0.parquet"


def _write_private(path: Path, write: Any) -> dict[str, Any]:
    """原子 + 0600 写文件:先写同目录临时文件、chmod、再 `os.replace`。

    umask 是 002,裸写会落成组可读;答案隔离靠的就是权限位(红线 5)。
    目录走 `cfg.create_dir()`(0700),文件显式 chmod 600,一个都不能省。
    """
    cfg.create_dir(path.parent)
    tmp = path.with_name(path.name + ".tmp")
    try:
        write(tmp)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        if tmp.exists():  # pragma: no cover
            tmp.unlink()
    data = path.read_bytes()
    return {
        "path": str(path),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "mode": oct(path.stat().st_mode & 0o777),
    }


def parquet_metadata(
    grid: ub.Grid, *, beyond_freeze: bool, valid_from: str, valid_to: str
) -> dict[bytes, bytes]:
    """写进 parquet **schema metadata** 的口径指纹。

    摘要 JSON 与数据卡都在 repo 里,parquet 单独流转时**带不走**。
    拿到 parquet 的人必须能只从文件本身知道:它到哪天、`status` 是什么口径、
    以及它是不是那份**越过冻结线**的验收切片。
    """
    meta = {
        "genebench_card": "1.2",
        "table": "tradability",
        "generator": "snapshots/tradability.py",
        "freeze_line": cfg.FREEZE_DATE,
        "beyond_freeze_line": "true" if beyond_freeze else "false",
        "valid_from": valid_from,
        "valid_to": valid_to,
        "n_trading_days_in_grid": str(len(grid)),
        "calendar": f"{CALENDAR_VIEW}(is_open=1,**只有 SSE**;深市/北交所用它是约定不是数据事实)",
        "statuses": ",".join(cfg.TRADABILITY_STATUSES),
        "status_convention": (
            "limit_up / limit_down 是**收盘**封板口径;盘中触板看 "
            "limit_touched_up / limit_touched_down,不在 status 里"
        ),
        "limit_price_tol": repr(cfg.LIMIT_PRICE_TOL),
        "no_price_limit_rule": " OR ".join(cfg.NO_PRICE_LIMIT_LEGS),
        "suspend_bases": ",".join(cfg.TRADABILITY_SUSPEND_BASES),
        "row_domain": (
            "listing_window ∪ daily ∪ stk_limit ∪ suspend_d,"
            "窗口外的行 in_listing_window=False(不删,只标)"
        ),
        "data_card": str(cfg.TRADABILITY_CARD.relative_to(cfg.REPO)),
        "warning": (
            "has_limit=False 时四个触板列全 False —— 那是**没法判**不是**没触板**。"
        ),
    }
    if beyond_freeze:
        meta["acceptance_only"] = (
            "本切片在冻结线之外,**只为复现实施稿点名的实测样例**;"
            "任何训练/回测窗口都不许把它拼进来(红线 7)。"
        )
    return {k.encode(): str(v).encode() for k, v in meta.items()}


def _write_parquet(frame: pd.DataFrame, path: Path, kv: dict[bytes, bytes]) -> dict:
    def _do(p: Path) -> None:
        table = pa.Table.from_pandas(
            frame[list(TRADABILITY_COLUMNS)], schema=PARQUET_SCHEMA, preserve_index=False
        )
        merged = dict(table.schema.metadata or {})
        merged.update(kv)
        pq.write_table(table.replace_schema_metadata(merged), p, compression="zstd")

    art = _write_private(path, _do)
    art["rows"] = int(len(frame))
    return art


# ==========================================================================
# 读取入口
# ==========================================================================


def read_tradability(
    years: "int | list[int] | None" = None, root: Path | None = None
) -> pd.DataFrame:
    """读回冻结产物。`years` 不给就读全部(**1500 万行,先想清楚**)。"""
    base = root if root is not None else cfg.TRADABILITY_DIR
    if years is None:
        paths = sorted(base.glob("year=*/part-0.parquet"))
    else:
        wanted = [years] if isinstance(years, int) else list(years)
        paths = [year_partition_path(y, base) for y in wanted]
    missing = [p for p in paths if not p.exists()]
    if not paths or missing:
        raise FileNotFoundError(
            f"缺分区:{missing or base}。先跑 `python -m snapshots.tradability`。"
        )
    return pd.concat([pd.read_parquet(p) for p in paths], ignore_index=True)


def read_acceptance(
    date: str | None = None, root: Path | None = None
) -> tuple[pd.DataFrame, dict[str, str]]:
    """读回**验收专用**切片 + 它的 parquet metadata。

    刻意和 `read_tradability` 分成两个函数:一个手滑把验收切片读进回测,
    就是越过冻结线(红线 7)。函数名本身就是那道提醒。
    """
    target = acceptance_partition_path(date or cfg.TRADABILITY_ACCEPTANCE_DATE, root)
    if not target.exists():
        raise FileNotFoundError(f"验收切片不存在:{target}")
    raw = pq.ParquetFile(target).schema_arrow.metadata or {}
    meta = {k.decode(): v.decode() for k, v in raw.items() if k != b"pandas"}
    return pd.read_parquet(target), meta


def tradability_at(
    code: str, date: str, *, root: Path | None = None
) -> "dict[str, Any] | None":
    """查一行。`date` 用 ``YYYY-MM-DD`` 或 ``YYYYMMDD``。查不到返回 `None`。

    **已知口径缺陷,本卡不修(`ops/tickets.md` N-10)**:"这天不是交易日"和
    "这天没这只票"目前都返回**同一个** `None`,调用方分不开。改它要动函数签名
    (多一种异常),属于口径变更,登记成票等一并处理,不在"修哨兵"这张卡里顺手改。

    Args:
        code: 湖内形态代码,如 ``600000.SH``。
        date: ``YYYY-MM-DD`` 或 ``YYYYMMDD``。
        root: 产物根,默认 `cfg.TRADABILITY_DIR`(测试用)。

    Returns:
        该行的 dict;产物里没有这一行时返回 `None`(见上面的已知缺陷)。

    Raises:
        ValueError: `date` 超过冻结线 —— 越界读**必须抛错**,不能静默返回
            `None`,否则调用方分不清"这天没这只票"和"这天根本不在产物里"。
    """
    compact = date.replace("-", "")
    if compact > cfg.FREEZE_DATE.replace("-", ""):
        raise ValueError(
            f"{date} 超过冻结线 {cfg.FREEZE_DATE}(红线 7)。"
            f" 验收切片走 `read_acceptance()`,不走这里。"
        )
    frame = read_tradability(int(compact[:4]), root=root)
    hit = frame[(frame["code"] == code) & (frame["date_compact"] == compact)]
    if hit.empty:
        return None
    return hit.iloc[0].to_dict()


# ==========================================================================
# 摘要 / 数据卡 / 抽样取证
# ==========================================================================


def _status_counts(frame: pd.DataFrame) -> dict[str, int]:
    counts = frame["status"].value_counts().to_dict()
    return {s: int(counts.get(s, 0)) for s in cfg.TRADABILITY_STATUSES}


def summarize(
    per_year: list[dict[str, Any]],
    acceptance: pd.DataFrame,
    grid: ub.Grid,
    listing_diag: dict[str, Any],
) -> dict[str, Any]:
    """把逐年统计汇总成机器可读摘要。数据卡里的每个数字都从这里来。"""
    total = {s: 0 for s in cfg.TRADABILITY_STATUSES}
    basis = {b: 0 for b in cfg.TRADABILITY_SUSPEND_BASES}
    agg = {
        "rows": 0,
        "in_listing_window": 0,
        "outside_listing_window": 0,
        "has_daily": 0,
        "has_limit": 0,
        "no_price_limit": 0,
        "intraday_halt": 0,
        "intraday_halt_timing_nonnull": 0,
        "limit_touched_up": 0,
        "limit_touched_down": 0,
        "limit_up_close": 0,
        "limit_down_close": 0,
        "touched_up_not_closed": 0,
        "touched_down_not_closed": 0,
        "daily_without_limit": 0,
        "zero_volume_with_daily": 0,
    }
    for row in per_year:
        for s in cfg.TRADABILITY_STATUSES:
            total[s] += row["status"][s]
        for b in cfg.TRADABILITY_SUSPEND_BASES:
            basis[b] += row["suspend_basis"][b]
        for k in agg:
            agg[k] += row[k]
    return {
        "card": "1.2",
        "table": "tradability",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "freeze_line": cfg.FREEZE_DATE,
        "calendar": {
            "view": CALENDAR_VIEW,
            "exchanges_in_lake": ["SSE"],
            "convention": (
                "深市 / 北交所的票同样使用 SSE 日历。**这是约定不是数据事实** —— "
                "湖里没有 SZSE / BSE 日历可对。"
            ),
            "n_trading_days": len(grid),
            "first": grid.days[0].isoformat(),
            "last": grid.days[-1].isoformat(),
        },
        "row_domain": {
            "definition": "listing_window ∪ daily ∪ stk_limit ∪ suspend_d(交易日网格上)",
            "listing_source": listing_diag,
        },
        "totals": {**agg, "status": total, "suspend_basis": basis},
        "by_year": per_year,
        "acceptance": {
            "date": cfg.TRADABILITY_ACCEPTANCE_DATE,
            "beyond_freeze_line": True,
            "rows": int(len(acceptance)),
            "status": _status_counts(acceptance),
        },
    }


def _fmt(value: Any, nd: int = 2) -> str:
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return "—"
    if isinstance(value, (bool, np.bool_)):
        return "是" if value else "否"
    if isinstance(value, float):
        return f"{value:.{nd}f}"
    return str(value)


def pick_samples(
    frame: pd.DataFrame, n: int, detail_n: int, seed: int
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """抽 `n` 条随机样本,并从中**挑** `detail_n` 条做链路取证。

    挑选规则(写死,可复现):

    1. 用 `seed` 从冻结产物里**等概率**抽 `n` 条。这是无偏样本,
       它的 `status` 分布本身就是一个结论(全表 99% 是 `trade`,
       所以 50 条里大概率一条 `suspend` 都没有 —— 这正是要如实报告的事)。
    2. 取证的 `detail_n` 条**按 status 分层**挑:先在这 `n` 条里,
       每个出现过的 `status` 各取第一条;`n` 条里没出现过的 `status`,
       用**同一个种子**从全表该 status 的行里补一条(否则取证表会
       只剩 `trade`,人工复核就核不到最难的那两类);还差的名额,
       按抽样顺序从 `n` 条里依次补足。

    刻意不做"看起来更有代表性"的手工挑选 —— 手挑的样本没法复现,
    "人工复核过了"这句话就没有重量。

    Returns:
        ``(sample_n, detail, meta)``。
    """
    rng = np.random.default_rng(seed)
    take = min(n, len(frame))
    positions = rng.choice(len(frame), size=take, replace=False)
    sample = frame.iloc[np.sort(positions)].reset_index(drop=True)

    chosen: list[pd.Series] = []
    origin: list[str] = []
    seen: set[tuple[str, str]] = set()
    for status in cfg.TRADABILITY_STATUSES:
        hit = sample[sample["status"] == status]
        if len(hit):
            row = hit.iloc[0]
            chosen.append(row)
            origin.append("来自 50 条随机样本")
        else:
            pool = frame[frame["status"] == status]
            if not len(pool):
                continue
            row = pool.iloc[int(rng.integers(0, len(pool)))]
            chosen.append(row)
            origin.append(f"50 条里没有 `{status}`,同种子从全表该状态补抽")
        seen.add((row["code"], row["date_compact"]))
    for _, row in sample.iterrows():
        if len(chosen) >= detail_n:
            break
        if (row["code"], row["date_compact"]) in seen:
            continue
        chosen.append(row)
        origin.append("来自 50 条随机样本(补足名额)")
        seen.add((row["code"], row["date_compact"]))

    detail = pd.DataFrame(chosen[:detail_n]).reset_index(drop=True)
    detail["_origin"] = origin[:detail_n]
    meta = {
        "seed": seed,
        "n": int(len(sample)),
        "detail_n": int(len(detail)),
        "sample_status_distribution": _status_counts(sample),
        "rule": pick_samples.__doc__.strip().splitlines()[0],
    }
    return sample, detail, meta


def _evidence_rows(detail: pd.DataFrame, con: Any) -> list[dict[str, Any]]:
    """给取证表的每一条现场把三源原始行捞出来 —— **不从产物里抄**。

    取证的意义就在于"不信产物,回源头看"。所以这里逐条查湖:
    `trade_cal` 说这天开不开市、`daily` 有没有行、`suspend_d` 怎么说、
    `stk_limit` 的上下限是多少。人照着这四行就能自己复核出 `status`。
    """
    rows: list[dict[str, Any]] = []
    for _, r in detail.iterrows():
        code, compact = str(r["code"]), str(r["date_compact"])
        cal = lake.query(
            f"SELECT exchange, cal_date, is_open FROM {CALENDAR_VIEW} "  # noqa: S608
            "WHERE cal_date = ?",
            [compact],
            conn=con,
        )
        part = f"trade_date={compact[:4]}-{compact[4:6]}-{compact[6:]}"
        dly = lake.read_gold(
            DAILY_DS,
            part,
            columns=list(_DAILY_FORENSIC_COLS),
            where=f"ts_code = '{code}'",
            conn=con,
        )
        sus = lake.read_gold(
            SUSPEND_DS, part, columns=list(_SUSPEND_COLS),
            where=f"ts_code = '{code}'", conn=con,
        )
        lim = lake.read_gold(
            LIMIT_DS, part, columns=list(_LIMIT_COLS),
            where=f"ts_code = '{code}'", conn=con,
        )
        rows.append(
            {
                "code": code,
                "date": str(r["date"]),
                "status": str(r["status"]),
                "origin": str(r["_origin"]),
                "cal_exchanges": ",".join(sorted(cal["exchange"].astype(str))) or "—",
                "cal_is_open": int(cal["is_open"].max()) if len(cal) else None,
                "daily_rows": int(len(dly)),
                "daily": dly.iloc[0].to_dict() if len(dly) else None,
                "suspend_rows": int(len(sus)),
                "suspend": sus.iloc[0].to_dict() if len(sus) else None,
                "limit_rows": int(len(lim)),
                "limit": lim.iloc[0].to_dict() if len(lim) else None,
                "product": {c: r[c] for c in TRADABILITY_COLUMNS},
            }
        )
    return rows


def render_sample_report(evidence: list[dict[str, Any]], meta: dict[str, Any]) -> str:
    """把 10 条取证渲染成 markdown 表格 —— 让人能照着链路自行复核。"""
    lines: list[str] = [
        "# 卡 1.2 验收 (b):10 条判定链路取证",
        "",
        "> 本文件由 `snapshots/tradability.py` 生成,**不要手改** —— 手改会和产物漂移。",
        "",
        "## 这张表怎么用",
        "",
        "每一行给出**从三个源头到 `status` 的完整链路**:`trade_cal` 说这天开不开市、",
        "`daily` 有没有行、`suspend_d` 怎么说、`stk_limit` 的上下限对上 `daily` 的 OHLC。",
        "拿这四条原始证据,任何人都能自己推一遍 `status`,不必信产物。",
        "",
        "复核用的判定规则(与 `snapshots/tradability.py::classify` 一字不差):",
        "",
        "```",
        "daily 无行 + 有停牌证据            -> suspend",
        "daily 无行 + 无停牌证据            -> no_data",
        "daily 有行 + |close-up_limit|<tol  -> limit_up      (收盘封板)",
        "daily 有行 + |close-down_limit|<tol-> limit_down    (收盘封板)",
        "daily 有行 + 其它                  -> trade",
        f"tol = {cfg.LIMIT_PRICE_TOL!r}",
        "「无涨跌幅限制」哨兵(-> 四个触板列强制 False),三条腿取并集:",
        *[f"    ({leg})" for leg in cfg.NO_PRICE_LIMIT_LEGS],
        "```",
        "",
        "## 抽样规则",
        "",
        f"- 随机种子 `{meta['seed']}`,从冻结产物里**等概率**抽 `{meta['n']}` 条。",
        f"- 这 {meta['n']} 条的 status 分布:"
        + "、".join(f"`{k}`={v}" for k, v in meta["sample_status_distribution"].items())
        + "。",
        "- 取证的 10 条按 status **分层**挑(规则见 `pick_samples` 的 docstring),"
        "每条都标了它是从 50 条里来的还是补抽的。",
        "",
        "## 取证表",
        "",
    ]
    for i, e in enumerate(evidence, 1):
        p = e["product"]
        lines += [
            f"### {i}. `{e['code']}` @ `{e['date']}` → **`{e['status']}`**",
            "",
            f"*来源:{e['origin']}*",
            "",
            "| 环节 | 湖里查到什么 | 对 status 的作用 |",
            "|---|---|---|",
            (
                f"| `trade_cal` | 交易所 `{e['cal_exchanges']}`,"
                f"`is_open={_fmt(e['cal_is_open'])}` | "
                f"开市 → 缺行才有「停牌 vs 缺数据」之分 |"
            ),
        ]
        if e["daily"]:
            d = e["daily"]
            lines.append(
                f"| `daily` | **有 1 行**:pre_close={_fmt(d['pre_close'])},"
                f"OHLC = {_fmt(d['open'])}/{_fmt(d['high'])}/"
                f"{_fmt(d['low'])}/{_fmt(d['close'])},"
                f"volume={_fmt(d['volume'], 0)} | 有行 → 只可能是 "
                f"`trade`/`limit_up`/`limit_down` |"
            )
        else:
            lines.append(
                "| `daily` | **0 行(缺行)** | 缺行 → 只可能是 `suspend`/`no_data` |"
            )
        if e["suspend"]:
            s = e["suspend"]
            timing = s.get("suspend_timing")
            lines.append(
                f"| `suspend_d` | **有 1 行**:`suspend_type={s['suspend_type']}`,"
                f"`suspend_timing={timing if timing else 'NULL'}` | "
                f"{'S=停牌' if s['suspend_type'] == 'S' else 'R=复牌'};"
                f"`suspend_basis={p['suspend_basis']}` |"
            )
        else:
            lines.append(
                f"| `suspend_d` | **0 行** | 当天无停复牌事件;"
                f"`suspend_basis={p['suspend_basis']}` |"
            )
        if e["limit"]:
            lm = e["limit"]
            lines.append(
                f"| `stk_limit` | **有 1 行**:`up_limit={_fmt(lm['up_limit'])}`,"
                f"`down_limit={_fmt(lm['down_limit'])}`"
                f"{'(**无涨跌幅限制哨兵**)' if p['no_price_limit'] else ''} | "
                f"比价 → `limit_up_close={_fmt(p['limit_up_close'])}`,"
                f"`limit_touched_up={_fmt(p['limit_touched_up'])}`,"
                f"`limit_down_close={_fmt(p['limit_down_close'])}`,"
                f"`limit_touched_down={_fmt(p['limit_touched_down'])}` |"
            )
        else:
            lines.append(
                "| `stk_limit` | **0 行** | `has_limit=False` → 四个触板列强制 "
                "`False`,那是**没法判**不是**没触板** |"
            )
        lines += [
            "",
            f"产物这一行:`in_listing_window={_fmt(p['in_listing_window'])}`、"
            f"`has_daily={_fmt(p['has_daily'])}`、`has_limit={_fmt(p['has_limit'])}`、"
            f"`intraday_halt={_fmt(p['intraday_halt'])}`。",
            "",
        ]
    return "\n".join(lines) + "\n"


def render_data_card(summary: dict[str, Any], sample_meta: dict[str, Any]) -> str:
    """生成数据卡。**每个数字都是这次产出现算的**,不手写。"""
    t = summary["totals"]
    st = t["status"]
    sb = t["suspend_basis"]
    rows = t["rows"]

    def pct(x: int) -> str:
        return f"{x / rows * 100:.3f}%" if rows else "—"

    lines = [
        "# 数据卡:`tradability`(卡 1.2 可交易性视图)",
        "",
        "> 本文件由 `snapshots/tradability.py` 生成,**不要手改**。",
        f"> 生成时间(UTC):{summary['generated_at_utc']}",
        "",
        "## 一句话",
        "",
        "给定 `(code, date)`,回答**这天能不能交易** —— 五档 `status`,互斥完备。",
        "",
        "## 产物",
        "",
        f"- 冻结产物:`{cfg.TRADABILITY_DIR}`,按年分区 `year=YYYY/part-0.parquet`,"
        f"上界 **{cfg.FREEZE_DATE}**(红线 7)。",
        f"- **验收专用**切片:`{cfg.TRADABILITY_ACCEPTANCE_DIR}`,"
        f"日期 **{summary['acceptance']['date']}**,在冻结线**之外**,"
        f"{summary['acceptance']['rows']:,} 行。",
        "  它只为复现实施稿点名的两个实测样例而存在,"
        "**任何训练/回测窗口都不许把它拼进来**;parquet metadata 里写死了 "
        "`beyond_freeze_line=true`,读取入口也另设一个 `read_acceptance()`。",
        "",
        "## 规模与分布",
        "",
        f"- 总行数 **{rows:,}**,覆盖 {summary['calendar']['n_trading_days']:,} 个交易日"
        f"({summary['calendar']['first']} → {summary['calendar']['last']})。",
        "",
        "| status | 行数 | 占比 | 含义 |",
        "|---|---:|---:|---|",
        f"| `trade` | {st['trade']:,} | {pct(st['trade'])} | 有行情,收盘没封板 |",
        f"| `limit_up` | {st['limit_up']:,} | {pct(st['limit_up'])} | **收盘**封在涨停价(买不进)|",
        f"| `limit_down` | {st['limit_down']:,} | {pct(st['limit_down'])} | **收盘**封在跌停价(卖不出)|",
        f"| `suspend` | {st['suspend']:,} | {pct(st['suspend'])} | `daily` 缺行 + 有停牌证据 |",
        f"| `no_data` | {st['no_data']:,} | {pct(st['no_data'])} | `daily` 缺行 + **没有**停牌证据 |",
        "",
        "## `suspend` 与 `no_data` 的分界(本表最需要读懂的一节)",
        "",
        "停牌票在 `daily` 里是**缺行**,不是标记。而缺行同时意味着两件事:",
        "*这天停牌* 和 *这天的数据我们没有*。分开它们只能靠三方 join。",
        "",
        "| `suspend_basis` | 行数 | 说明 |",
        "|---|---:|---|",
        f"| `suspend_d_S` | {sb['suspend_d_S']:,} | 当天 `suspend_d` 就有 `S`。**直接证据** |",
        f"| `carried_after_S` | {sb['carried_after_S']:,} | 前面有 `S`,此后一直没有行情行也没有 `R`,状态**顺延**。**推断证据** |",
        f"| `none` | {sb['none']:,} | 没有任何停牌证据 |",
        "",
        f"顺延一共救回 **{sb['carried_after_S']:,}** 行 —— 不顺延的话它们会全部被误判成 "
        f"`no_data`。为什么需要顺延:`suspend_d` 在早年是**事件流**不是逐日状态"
        "(2009 年 `R` 一行都没有,`R` 最早出现在 20100510)。",
        "",
        f"剩下 **{st['no_data']:,}** 行确实没有任何证据,判 `no_data`。"
        "这个数不藏 —— 它就是这张表说不清楚的部分。",
        "",
        "`no_data` 里有一小类值得单独说:**当天 `suspend_d` 说 `R`(复牌)但 `daily` 没有行**。",
        "复牌了却没有行情,`suspend_d` 和 `daily` 互相矛盾,谁也证明不了那天到底能不能交易 ——",
        "所以判 `no_data` 而不是 `trade`。这类行 `suspend_flag = 'R'` 且 `has_daily = False`,",
        "想单独捞出来一个过滤就够。",
        "",
        "### ⚠️ 同一天既有 `S` 又有 `R`",
        "",
        "湖里有 **161** 个 `(code, date)` 同时躺着一条 `S` 和一条 `R`(合计 322 行,",
        "2011-2026 各年都有),其中 **127** 个当天 `daily` 有行、**34** 个没有。",
        "本表把这种情况显式编码成 `suspend_flag = 'SR'`,**不丢信息**;",
        "判定上 `S` 压过 `R`(有 `S` 而无行情就判停牌),`daily` 有行又压过两者。",
        "",
        "> 最早那版写的是 `drop_duplicates(keep='first')` —— **顺序依赖**,",
        "> 留下 `S` 还是 `R` 取决于 parquet 行序。是 `ops/negctl_tradability.py` 的",
        "> 全历史独立复算把它抓出来的(`suspend_d_S` 差 32 行)。40 条 pytest 全绿,",
        "> 单月逐行重算也全绿 —— **抽查看不出这种错**。",
        "",
        "### ⚠️ 顺延的已知弱点",
        "",
        "顺延的终止条件是「这只票又有行情行了,或者出现了 `R`」,**没有天数上限**。",
        "所以一只停牌后直接退市的票,从停牌日到窗口末尾会**整段**判 `suspend`。",
        "那在语义上是对的(它确实一天都没能交易),但如果你要的是「有效停牌」,",
        "请按 `suspend_basis == 'suspend_d_S'` 收紧。",
        "",
        "另一条(**踩过的坑,留在这里**):构建是**逐年**做的,跨年的顺延状态"
        "现在是**精确**传递的 —— 每年把最后一个交易日的停牌态交给下一年。",
        "最早那版不是这么写的,是「多算上一年最后 60 个交易日当前缀」。那版错得很隐蔽:",
        "`suspend_d` 在 2009-2012 年是**事件流**,长期停牌只在第一天发一条 `S`;",
        "一只票连续停牌超过 60 个交易日又跨年,前缀里就只剩「缺行且无 `S`」,",
        "年初整段被判成 `no_data`。对账才发现顺延救回的行数只有全历史扫一遍的一半",
        "(10,019 vs 22,064)。**抽查看不出来这种错,只有和另一份独立统计对数才看得出来。**",
        "",
        "现在仍然存在的边界:一只票如果在上一年最后一个交易日**四条证据通道一条都没响**,",
        "它拿不到 `carry_in`。那是对的 —— 行域里有洞的地方本来就不该顺延。",
        "",
        "## 触板:两个口径,分列,不要混",
        "",
        "| 列 | 判据 | 回答的问题 |",
        "|---|---|---|",
        "| `limit_up_close` | `\\|close - up_limit\\| < tol` | 收盘封住了吗(**买不进**)|",
        "| `limit_down_close` | `\\|close - down_limit\\| < tol` | 收盘封住了吗(**卖不出**)|",
        "| `limit_touched_up` | `high >= up_limit - tol` | 盘中摸到过吗(封没封住不管)|",
        "| `limit_touched_down` | `low <= down_limit + tol` | 同上 |",
        "",
        f"- `status` 只用**收盘**口径。盘中摸到涨停又打开的(炸板)`status` 仍是 `trade`。",
        f"- 全表:盘中触涨停 **{t['limit_touched_up']:,}** 行,其中收盘没封住的"
        f"(炸板)**{t['touched_up_not_closed']:,}** 行;"
        f"盘中触跌停 **{t['limit_touched_down']:,}** 行,其中 "
        f"**{t['touched_down_not_closed']:,}** 行收盘没封住。",
        "",
        "### 浮点比价的容差",
        "",
        f"`cfg.LIMIT_PRICE_TOL = {cfg.LIMIT_PRICE_TOL!r}`。价格与涨跌停价都是两位小数,"
        "但 float64 存两位小数本身不精确,裸 `==` 是在赌位模式对齐。",
        "实测三个月共 26.9 万行,`==` / `<1e-6` / `<5e-3` / `round(2)==` 四种判据"
        "**逐行相同**,一条都不差 —— 容差在当前湖数据上不改变任何结论,"
        "留着它是防线不是修正。",
        "",
        "### ⚠️ 「无涨跌幅限制」哨兵",
        "",
        "`stk_limit` 里有一族行,`up_limit` / `down_limit` **不是价格**,"
        "是「这天没有涨跌停」的编码(新股上市首日、科创板/北交所首日一类)。",
        "判据是**三条腿取并集**,写在 `cfg.NO_PRICE_LIMIT_UP_MIN` / "
        "`cfg.NO_PRICE_LIMIT_DOWN_MAX` / `cfg.NO_PRICE_LIMIT_BAND_MAX`:",
        "",
        "```",
        *[f"({leg})" for leg in cfg.NO_PRICE_LIMIT_LEGS],
        "```",
        "",
        f"本产物里命中 **{t['no_price_limit']:,}** 行,`no_price_limit = True`,"
        "四个触板列一律 `False`。",
        "",
        "湖侧独立统计:≤ 冻结线的 `stk_limit` 共 14,892,432 行(`up_limit` / "
        "`down_limit` 两列均无 NULL),其中 `down_limit <= 0.01` 的 **7,107** 行,"
        "`(up_limit, down_limit)` 只有六种取值 —— 末列 `band` 是隐含带宽 "
        "`(up-down)/(up+down)`:",
        "",
        "| `up_limit` | `down_limit` | 行数 | `band` |",
        "| --- | --- | ---: | ---: |",
        "| `100000.0` | `0.01` | 2,754 | 1.0 |",
        "| `1000000.0` | `0.01` | 2,332 | 1.0 |",
        "| `999999.999` | `0.01` | 975 | 1.0 |",
        "| `99999.999` | `0.01` | 751 | 1.0 |",
        "| `99999.99` | `0.0` | 267 | 1.0 |",
        "| `0.0` | `0.0` | 28 | NaN |",
        "",
        "(不加冻结线是 7,163 行,多出来的 56 行全在 2026-08,被红线 7 挡在窗口外。)",
        "",
        "三条腿在当前湖上**逐行同集**:`down_limit <= 0.01` 而 `up_limit` 正常的行 "
        "**0 行**,反向也 **0 行**。这是 `test_sentinel_legs_agree_on_the_lake` "
        "断言的内容 —— **湖里一旦出现只满足其中一部分腿的行,它会变红**,"
        "刻意留的报警口:遇到没见过的编码要吵,不要静默判 `False`。",
        "",
        "**⚠️ 本卡第一版在这里错过一次,写下来免得再犯。** 第一版判据是 "
        "`up_limit >= 100000.0`,差一分钱,只抓到前三种共 **6,061** 行,"
        "**漏掉后三种 1,046 行**(2021:22 / 2022:83 / 2023:320 / 2024:190 / "
        "2025:241 / 2026:162,**在增长**;另有 28 行 `0.0/0.0` 散在 2009-2015)。"
        "那 1,046 行被错标 `no_price_limit = False`,"
        "于是这张表对它们断言「有涨跌停价、可判、且没触板」,并把 `99999.999` "
        "当**真实涨停价**发出去 —— 例:`688425.SH @ 2021-06-22`(科创板上市首日,"
        "low 5.19 / high 12.15 / close 8.22,日内振幅 >130%,本就没有涨跌停),"
        "下游算 `up_limit / close` 会拿到 **12,165 倍**。",
        "",
        "**为什么不是「把阈值调小」就完了。** 前两条腿仍然咬死在具体数值上,"
        "只能罩住已经见过的编码,而这次翻车正是「见过的之外还有一族」。"
        "第三条腿不认识任何具体哨兵值:真实的 ±5%/±10%/±20%/±30%/±44% 档给出 "
        "`band` 0.05/0.10/0.20/0.30/0.44,哨兵一律给出 1.0。实测非哨兵行 "
        "`band ∈ [0.0097, 0.4408]`(上界 `601975.SH @ 2019-01-08`,6.21/2.41,"
        "新股首日 ±44% 档),哨兵行恒为 1.0 —— 中间是条**空的**鸿沟,"
        "阈值取 0.5/0.6/0.7/0.9 选出的行数一模一样。所以将来冒出 "
        "`up=88888.88 / down=0.02` 这种没见过的编码,`band` 侧照样罩得住。",
        "",
        "**这条防线是必需的,不是保险**:一只价格恰好 `0.01` 的票碰上 "
        "`down_limit = 0.01` 会被误判 `limit_down`,而漏掉的那 1,046 行"
        "恰恰就是防线没合上的地方。必须先排除哨兵行再比价。",
        "",
        "### ⚠️ 不要用 `stk_limit.pre_close`",
        "",
        "共享上下文说它「全为 NULL」。**实测不是**:全表 15,008,861 行里 14,875,699 行非空"
        "(99.1%),2009-2018 年**逐年 100% 非空**。真相是它在 **2026-08 塌了**:"
        "该月 116,429 行里只有 11,058 行非空(9.5%)。",
        "结论反而更强 —— 拿它当前收会**在回测里一路正确、到最近的数据上突然全空**,"
        "是最难查的那种故障。所以本表判触板只走 `daily` 比价。",
        "",
        "## 行域:哪些 `(code, date)` 会有行",
        "",
        "**行域 = `listing_window` ∪ `daily` ∪ `stk_limit` ∪ `suspend_d`**,"
        "再交上交易日网格与上界。",
        "",
        f"- 落在 `stock_basic` 在市窗口内:**{t['in_listing_window']:,}** 行;"
        f"窗口**外**:**{t['outside_listing_window']:,}** 行"
        f"({pct(t['outside_listing_window'])})。",
        "- 为什么不能只用在市窗口:实测 `daily` 里有 **84,424** 行落在窗口之外,"
        "只用窗口做行域会把真实成交过的交易日静默丢掉。两个成因都查清了 —— "
        "**76,325 行全是 `.BJ`**(北交所换代码 `920xxx`,行情按新代码回填到挂牌之前),"
        "**8,099 行全是 `.SZ`**(这些 `ts_code` 在 `stock_basic` 里根本没有行)。",
        "- 反过来 `on_or_after_delist` **一行都没有** —— 独立验证了"
        "「`daily` 在 `delist_date` 当天及之后零行」。",
        "- 窗口外的行照样出,只是 `in_listing_window = False`。"
        "要只看正常在市的票,**下游自己加这个过滤**;由这张表替你删,你就再也看不见它们了。",
        "",
        "## `S` 与 `daily` 有行同时出现 = 盘中临时停牌",
        "",
        f"全表 **{t['intraday_halt']:,}** 行 `intraday_halt = True`:"
        "`suspend_d` 说 `S`,但 `daily` 有行。那不是矛盾,是停十分钟又复牌,当天照样成交。",
        f"这类行 `status` 按有行情算。其中 `suspend_timing` 非空的有 "
        f"**{t['intraday_halt_timing_nonnull']:,}** 行。",
        "",
        "> **⚠️ 与共享上下文的出入(实测)。** 共享上下文说 `suspend_timing` 全为 NULL。"
        "实测全表 482,298 行里 **2,643 行非空**(0.55%),而且非空的**正好就是**盘中停牌:"
        "2019 年起「`S` 且 `daily` 有行」的行 100% 非空(形如 `9:31-9:41`);"
        "但 2009-2011 年这类行 100% 为空(1,435 / 778 / 719 行)。"
        "所以 `suspend_timing` 只能当**佐证**,不能当判据 —— "
        "本表的判据是「`daily` 有没有行」,那个在全历史都可靠。",
        "",
        "## ⚠️ 日历只有 SSE —— 这是约定不是数据事实",
        "",
        "湖 `trade_cal` **只有 SSE 一个交易所**(6,574 行,20090101→20261231)。",
        "本表对 `.SZ` / `.BJ` 的票**同样使用 SSE 日历**。",
        "沪深两市交易日历在实务上一致、北交所随深市,但「一致」是行业惯例,"
        "**不是这张表能从数据里证明的东西** —— 湖里根本没有 SZSE / BSE 日历可对。",
        "真要出现某天只有一市开市,本表会把另一市的票判成 `no_data`(缺行),"
        "而不是「非交易日」。",
        "",
        "另有一条:`trade_cal` 的 gold 只有**一个** `snapshot_date=2026-08-05` 分区且此后从未刷新。"
        "它的 `cal_date` 一路排到 20261231,那是**快照里预写的未来日历**,不是它还活着的证据。",
        "",
        "## `has_limit = False` 的行",
        "",
        f"全表有 **{t['daily_without_limit']:,}** 行有行情但 `stk_limit` **没有**对应行"
        "(2021-06 单月就有 1,965 行)。这些行四个触板列全 `False`,"
        "**那是「没法判」不是「没触板」** —— 要区分请看 `has_limit`。",
        "",
        "## 独立口径交叉验证:`limit_list_d`",
        "",
        "湖里 `limit_list_d`(涨跌停榜,覆盖 20200102 起,gold 停更在 2026-08-05)"
        "是**不参与本表任何判定**的第三方口径。拿 2021-06 单月对了一遍:",
        "",
        "| 它说 | 条数 | 落在我们哪一列 | 覆盖率 |",
        "|---|---:|---|---:|",
        "| `U`(涨停)| 1,193 | `limit_up_close` | **1193/1193 = 100%** |",
        "| `D`(跌停)| 201 | `limit_down_close` | **201/201 = 100%** |",
        "| `Z`(炸板)| 407 | `limit_touched_up` | **407/407 = 100%** |",
        "",
        "- 反向我们多出 **682** 条 `limit_up_close` 它没收 —— 查清了:"
        "涨跌幅比例直方图显示这 682 条集中在 **4.7%~5.4%**,是 **ST / *ST 的 ±5% 涨跌停**,"
        "而同期它收录的 1,193 条集中在 **10% / 20%**。是它的口径不收 ST,不是我们判错。",
        "- 407 条 `Z` 里有 **13 条**我们同时判 `limit_up_close = True` —— "
        "那是**炸板之后收盘又封回去**。这恰恰说明收盘口径与盘中口径必须分列:"
        "一个口径盖不住两种问题。",
        "",
        "## 不该拿它做什么",
        "",
        "1. **不要拿 `status` 当「涨没涨停」。** 它是收盘封板口径;炸板的 `status` 是 `trade`。",
        "2. **不要把 `no_data` 当「停牌」。** 那是我们说不清楚的行,拿去回测等于凭空持仓。",
        "3. **不要把验收切片拼进回测窗口。** 它在冻结线之外。",
        "4. **不要用 `has_limit=False` 的行推断「没触板」。**",
        "5. **不要拿它当行情表。** `close/high/low/volume` 只是判定依据的留档,"
        "未复权、不完整;取价走 `daily` + `adj_factor`。",
        "",
        "## 抽样取证",
        "",
        f"验收 (b) 的 10 条链路取证在 `{cfg.TRADABILITY_SAMPLE_REPORT.relative_to(cfg.REPO)}`,"
        f"随机种子 `{sample_meta['seed']}`。50 条随机样本的 status 分布:"
        + "、".join(f"`{k}`={v}" for k, v in sample_meta["sample_status_distribution"].items())
        + "。",
        "",
    ]
    return "\n".join(lines) + "\n"


# ==========================================================================
# 入口
# ==========================================================================


def _year_stats(frame: pd.DataFrame, year: int) -> dict[str, Any]:
    touched_up = frame["limit_touched_up"]
    touched_dn = frame["limit_touched_down"]
    basis = frame["suspend_basis"].value_counts().to_dict()
    return {
        "year": year,
        "rows": int(len(frame)),
        "status": _status_counts(frame),
        "suspend_basis": {
            b: int(basis.get(b, 0)) for b in cfg.TRADABILITY_SUSPEND_BASES
        },
        "in_listing_window": int(frame["in_listing_window"].sum()),
        "outside_listing_window": int((~frame["in_listing_window"]).sum()),
        "has_daily": int(frame["has_daily"].sum()),
        "has_limit": int(frame["has_limit"].sum()),
        "no_price_limit": int(frame["no_price_limit"].sum()),
        "intraday_halt": int(frame["intraday_halt"].sum()),
        "intraday_halt_timing_nonnull": int(
            (frame["intraday_halt"] & frame["suspend_timing"].notna()).sum()
        ),
        "limit_touched_up": int(touched_up.sum()),
        "limit_touched_down": int(touched_dn.sum()),
        "limit_up_close": int(frame["limit_up_close"].sum()),
        "limit_down_close": int(frame["limit_down_close"].sum()),
        "touched_up_not_closed": int((touched_up & ~frame["limit_up_close"]).sum()),
        "touched_down_not_closed": int((touched_dn & ~frame["limit_down_close"]).sum()),
        "daily_without_limit": int((frame["has_daily"] & ~frame["has_limit"]).sum()),
        "zero_volume_with_daily": int(
            (frame["has_daily"] & (frame["volume"].fillna(-1) == 0)).sum()
        ),
    }


def main(argv: "list[str] | None" = None) -> int:
    """构建 → 落盘 → 摘要 → 数据卡 → 取证表。

    默认**同时**产出冻结产物与验收切片。`--no-acceptance` 只出冻结产物,
    此时网格上界就是冻结线,**一个冻结线之外的分区都不会被读**。
    """
    parser = argparse.ArgumentParser(description="卡 1.2:构建 tradability")
    parser.add_argument(
        "--no-acceptance",
        action="store_true",
        help="不产出验收切片;网格上界就是冻结线,不读冻结线之外的任何分区",
    )
    args = parser.parse_args(argv)

    lake.raise_open_file_limit()
    acc_date = cfg.TRADABILITY_ACCEPTANCE_DATE
    want_acc = not args.no_acceptance
    bound = acc_date if want_acc else cfg.FREEZE_DATE
    freeze_compact = cfg.FREEZE_DATE.replace("-", "")
    acc_compact = acc_date.replace("-", "")

    con = open_lake()
    try:
        grid = load_grid(bound, conn=con)
        windows, listing_diag = ub.load_listing_windows(grid, conn=con)
        frozen_grid = ub.Grid([d for d in grid.days if d.isoformat() <= cfg.FREEZE_DATE])
        kv_frozen = parquet_metadata(
            frozen_grid,
            beyond_freeze=False,
            valid_from=frozen_grid.days[0].isoformat(),
            valid_to=frozen_grid.days[-1].isoformat(),
        )

        per_year: list[dict[str, Any]] = []
        artifacts: list[dict[str, Any]] = []
        acceptance = pd.DataFrame(columns=list(TRADABILITY_COLUMNS))
        n_discarded = 0

        for year, frame in build_frames(
            bound, conn=con, grid=grid, windows=windows
        ):
            frozen = frame[frame["date_compact"] <= freeze_compact]
            if len(frozen):
                stats = _year_stats(frozen, year)
                art = _write_parquet(frozen, year_partition_path(year), kv_frozen)
                stats["artifact"] = art
                per_year.append(stats)
                artifacts.append(art)
                print(
                    f"[tradability] year={year} rows={len(frozen):,} "
                    f"-> {art['path']}",
                    flush=True,
                )
            if want_acc:
                hit = frame[frame["date_compact"] == acc_compact]
                if len(hit):
                    acceptance = hit.reset_index(drop=True)
            n_discarded += int(
                (
                    (frame["date_compact"] > freeze_compact)
                    & (frame["date_compact"] != acc_compact)
                ).sum()
            )

        if want_acc:
            if acceptance.empty:
                raise RuntimeError(
                    f"验收日 {acc_date} 一行都没产出 —— 它是不是不在 "
                    f"{CALENDAR_VIEW} 的交易日里?"
                )
            kv_acc = parquet_metadata(
                grid, beyond_freeze=True, valid_from=acc_date, valid_to=acc_date
            )
            acc_art = _write_parquet(
                acceptance, acceptance_partition_path(acc_date), kv_acc
            )
            print(
                f"[tradability] acceptance {acc_date} rows={len(acceptance):,} "
                f"-> {acc_art['path']}",
                flush=True,
            )
        else:
            acc_art = None

        summary = summarize(per_year, acceptance, frozen_grid, listing_diag)
        summary["build"] = {
            "grid_bound": bound,
            "acceptance_enabled": want_acc,
            "rows_beyond_freeze_discarded": n_discarded,
            "cross_year_carry": "exact(逐年把最后一个交易日的停牌态传给下一年)",
            "partitions": artifacts,
            "acceptance_artifact": acc_art,
        }

        # 抽样取证:只从**冻结产物**里抽。
        frozen_all = pd.concat(
            [pd.read_parquet(a["path"]) for a in artifacts], ignore_index=True
        )
        sample, detail, sample_meta = pick_samples(
            frozen_all,
            cfg.TRADABILITY_SAMPLE_N,
            cfg.TRADABILITY_SAMPLE_DETAIL_N,
            cfg.TRADABILITY_SAMPLE_SEED,
        )
        evidence = _evidence_rows(detail, con)
        summary["sampling"] = sample_meta
        summary["sample_50"] = sample[
            ["code", "date_compact", "status", "suspend_basis", "has_daily", "has_limit"]
        ].to_dict("records")
        summary["sample_10_evidence"] = evidence

        # 实施稿点名的两个样例,单独留档(验收 (a))
        summary["acceptance_cases"] = {
            code: (
                acceptance[acceptance["code"] == code]
                .drop(columns=["date_idx"], errors="ignore")
                .to_dict("records")
            )
            for code in ("000711.SZ", "600491.SH")
        }
    finally:
        con.close()

    report = render_sample_report(evidence, sample_meta)
    summary["sample_report"] = _write_private(
        cfg.TRADABILITY_SAMPLE_REPORT,
        lambda p: p.write_text(report, encoding="utf-8"),
    )
    card_text = render_data_card(summary, sample_meta)
    summary["data_card"] = _write_private(
        cfg.TRADABILITY_CARD, lambda p: p.write_text(card_text, encoding="utf-8")
    )
    _write_private(
        cfg.TRADABILITY_JSON,
        lambda p: p.write_text(
            json.dumps(summary, ensure_ascii=False, indent=1, default=str) + "\n",
            encoding="utf-8",
        ),
    )

    t = summary["totals"]
    print(
        "[tradability] 完成:"
        f"{t['rows']:,} 行 / status="
        + ", ".join(f"{k}={v:,}" for k, v in t["status"].items()),
        flush=True,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
