"""卡 1.1 **源A**:从 `index_weight` 月末快照 diff 推 PIT 成分区间。

产出 `(code, universe, in_date, out_date)` 三宇宙区间表 ——
csi300 / csi500 / csi1000,加上截断标记与不确定性窗口。

跑法::

    cd $REPO && $GENEBENCH_ROOT/env/bin/python -m snapshots.universe_index_weight

产物两个(路径全部来自 `genebench_config`,本文件**不含任何绝对路径字面量**):

* `cfg.UNIVERSE_INTERVALS_PARQUET` —— 区间表(落 `$GENEBENCH_ROOT`,**不进 repo**)
* `cfg.UNIVERSE_SOURCE_A_JSON`     —— 统计摘要 + 数据卡(小文本,进 git)


================================================================
一、语义:快照 diff 到底推得出什么(全卡最容易错的地方)
================================================================

原始事实只有一种形状:**"某月末最后一个交易日 T,这只票在成分里"**。
211 期(csi300/csi500,20090123→20260731)/ 142 期(csi1000,20141031→20260731),
每期一张全量名单。相邻两期做 diff 得到的是

    "在 T_{k-1} 之后、T_k 之前的**某个时点**发生了变动"

**不是**精确生效日。中证的调仓生效日是 6 月/12 月第二个星期五的下一交易日
(还有临时调整),落在月中;月末快照只能告诉你"到月末为止,这只票在/不在"。
所以 in_date / out_date 的**分辨率上限就是快照粒度(约一个月)**,
这一条无论怎么选约定都改不掉。

------------------------------------------------
1.1 约定:入场取"首次出现的那期",出场取"消失那期的前一个交易日"
------------------------------------------------

设某段连续在成分内的快照是 T_i .. T_j(T_{i-1} 不在、T_{j+1} 不在),本模块取::

    in_date  = T_i                                  # 首次观测到在成分内的那期
    out_date = prev_trading_day(T_{j+1})            # 消失那期的前一个交易日

**这是刻意选的不对称约定,理由是 PIT(信息可得性),不是美观。**

判据只有一条:**区间里的每一天,都只能用那天(含)之前已经存在的信息推出来。**
把两个自由度分开看:

*入场侧*。真实入场日 ∈ (T_{i-1}, T_i]。备选是 `T_{i-1} 的次日`(区间左端外推)。
但"这只票进来了"这件事,**最早只能在 T_i 那期名单公布时知道**。
把 in_date 提前到 T_{i-1}+1,等于让整整一个月的持仓建立在一份当时还不存在的名单上
—— 教科书级的前视偏差。所以入场取 **T_i**:观测点本身,不外推。

*出场侧*。真实出场日 ∈ (T_j, T_{j+1}]。备选是 `T_j`(最后一次观测到在成分内的那期)。
`T_j` 看着更"保守"(只声明观测到的东西),但它**同样是前视**,只是方向反了:
在 T_j+1 那天,你手上最新的名单还是 T_j 那份,上面白纸黑字写着这只票在成分里;
你之所以敢在 T_j+1 就把它剔掉,唯一的依据是 T_{j+1} 那份**还没出生**的名单。
把票提前一个月剔掉,同样是用未来信息。所以出场取
**"下一期快照的前一个交易日"** —— 持有到名单告诉你它不在为止。

两条合起来的等价说法:**任意交易日 D 的宇宙 = 不晚于 D 的最后一期快照的名单**
(last-observation-carried-forward)。这正是 PIT 的定义:宇宙规模在两期快照之间
**不会缩水**,它只在快照日跳变。

**但"恒等于名义值 300/500/1000"是错的,不要当不变量依赖**(对抗审查 D4):
在每个交易日上展开区间后实测

    csi300  {298: 20, 300: 4235}   # 20091231 ~ 20100128 这 20 个交易日是 298
    csi500  {500: 4255}
    csi1000 {1000: 2857}

那 20 天是 20091229 两只票同日吸收合并退市(600001.SH 邯郸钢铁 / 600357.SH 承德钒钛)
在指数里留下的 2 席空缺,权重和仍是 99.993(正常带 [99.90, 100.11])—— 真空缺,
不是漏行。下游写 ``assert len(univ) == 300`` 会在这 20 天上炸。
摘要 JSON 的 ``integrity.size_histogram_by_period`` 给出现算的分布,
`ops/test_universe_source_a.py` 把这个白名单钉成断言。

代价写明白:区间**外**近似真实区间(出场侧最多晚一个月),
不是内近似。想要内近似的下游可以用 `last_seen_snapshot` 自己收窄 ——
观测量与约定量在产物里是**分开两列**的,谁都不用反推。

`out_date` 取的是"前一个**交易日**"而不是"前一个自然日":本基准的时间轴是交易日,
两者在 `in_date <= D <= out_date` 这类过滤上**结果完全相同**(中间隔的都是非交易日),
但交易日版本保证产物里每一个日期都能直接和 `daily` / `trade_cal` 对上,
不需要下游再做一次日历取整。(qlib 用的是自然日,见第三节。)

------------------------------------------------
1.2 截断:第一期与最后一期不是普通的进出
------------------------------------------------

*左截断*。在**首期**(csi300/500 = 20090123,csi1000 = 20141031)就出现的票,
它是那天进来的、还是 2005 年就在里面了,**源A 根本看不见** —— 首期之前没有快照。
产物里 ``left_censored=True``,`in_date` 仍填首期日期。

为什么 `in_date` 不像 `out_date` 那样填 NULL:两种截断的**可用性**不一样。
右截断是"区间还没结束",NULL 才是正确的"无上界";左截断是"更早的事不可知",
但源A 的数据本身也从首期才开始,任何落在数据区间内的查询日 D 都 ``>= 首期``,
首期是一个既安全又可用的下界。填 NULL 只会逼下游写一堆 ``fillna``。
**真正的下界要靠源B(qlib instruments,csi500 回溯到 2007-01-31、
csi300 回溯到 2005-04-08)补** —— 这正是卡 1.2 交叉核对的价值所在。

*右截断*。在**末期**(20260731,恰好是冻结线)仍在成分里的票,没有观测到出场。
``right_censored=True``,``out_date = NULL``。NULL 表示"区间开口",
**不是** 20260731 —— 写成 20260731 会被下游读成"7 月 31 日被调出",凭空造一次调仓。

------------------------------------------------
1.3 一只票可以多次进出 → 多段区间
------------------------------------------------

按"快照期序号连续"切段:同一 (code, universe) 下,期序号不连续的地方断开,
每段一行,`segment_idx` 从 0 起。**不合并**跨越缺口的段 —— 那个缺口是真的
(在中间那些期它确实不在名单上)。实测确有大量多段票(见摘要 JSON)。


================================================================
二、已知局限(数据卡)
================================================================

1. **月内调整被完全抹平。** 月中调进、同月内又调出的票,两期快照都看不到它,
   源A 里根本不存在。反过来,月中的调整会被记到月末那一期上,
   于是所有 in/out 日期都有**最多约一个月的系统性滞后**。
2. **分辨率 = 快照粒度。** 见 1.1。要精确到日必须换源(源B qlib instruments,
   或未来接指数公司的调整公告)。
3. **首期左截断 / 末期右截断。** 见 1.2。
4. **成分数缺额期。** 若某期成分数不等于名义值,该期的"消失/出现"里**可能**混进
   数据缺行造成的假调仓。本模块**不修补**,只判成因并点名:
   `diagnose_off_size()` 用"权重和是否仍≈100"+"缺的席位有没有同窗口内的
   `delist_date` 取证"两条判据把缺额期分成 ``index_vacancy``(指数真空缺,正常)
   与 ``unexplained``(必须逐条查);只有 ``unexplained`` 且形状真是"在–缺–在"的
   段边界才打 ``entry_gap_suspect`` / ``exit_gap_suspect``。
   **本数据上这两列全为 False** —— 唯一的缺额期 20091231 已被退市取证解释。
5. **冻结线 2026-07-31**(红线 7)。查询显式加了上界,湖继续前进也不会污染 v1。
6. **`weight` 字段未进产物。** 源A 只回答"在不在",不回答"占多少"。
   权重是另一件事(卡 3.2),混进区间表只会让语义含糊。


================================================================
三、与 qlib instruments(源B)的区间约定对齐
================================================================

源B 的格式是 ``SH600000\\t2005-04-08\\t2005-06-30``,同一 code 多行 = 多段。
实测(`cfg.QLIB_RELEASE/instruments`)它的约定是:

* **贴片式,不合并相邻段。** 每次调仓都切一刀,``end_k + 1 自然日 == start_{k+1}``。
  csi300 16198 行里 14973 对相邻段是首尾相接的,只有 276 对是真缺口;
  "每个 start 都紧跟着某个 end"这条在三个宇宙上**无一例外**。
  所以 **qlib 的行数不是段数** —— 直接拿 16198 去比我们的段数是错的,
  必须先把相邻段合并成极大段(合并后:csi300 1225 / csi500 2466 / csi1000 3349)。
* **右端夹到发布日,不是 NULL。** 三个文件的 ``max_end`` 都是 2026-08-26
  (= release 目录名),且恰好 300 / 500 / 1000 行落在这一天 —— 就是"当前仍在成分内"。
  我们用 NULL,对齐时要把 NULL 映射成各自的数据末端。
* **左端能回溯到源A 之前。** csi300 最早 2005-04-08、csi500 最早 2007-01-31,
  都早于源A 的 20090123 —— 源A 的左截断正是靠这里补。
  csi1000 最早 2014-10-31,与源A 首期**同一天**。
* **代码形态与日期格式都不同。** ``SH600000`` 前缀式 vs 湖里的 ``600000.SH``;
  ISO ``2005-04-08`` vs ``20050408``。对齐前必须两次转换。
* **切点粒度不同,但重合度很高。** qlib csi1000 的 34 个 start **全部**落在
  月末最后一个交易日、且**全部**是 `index_weight` 的快照日;csi500 45 个里 35 个、
  csi300 54 个里 29 个也是。也就是说源B 在 csi1000 上几乎就是月末粒度,
  在 csi300/csi500 上则含更细的日内切点(csi300 有 14 个 start 连交易日都不是,
  疑似用了公告日)。

**由此可以预判源A→源B 的差异方向,卡 1.2 应当按这个去卡:**

* **先把两源都投影到交易日网格再比。** 源B 的端点是**自然日**
  (``end_k = start_{k+1} - 1 天``),大量落在周末/节假日;源A 的 out_date 取的是
  前一个**交易日**。不取整直接比,会先收到一批 −2 自然日的假警报 ——
  实测 245 条(csi300 35 + csi500 101 + csi1000 109),**全部恰好 −2**,
  且 qlib 的 ``end`` **无一是交易日**(实测
  ``n_negative_where_qlib_end_is_a_trading_day = 0/0/0``)。这一步不做,后面四条全是噪声。
* 入场侧 ``in_date_A >= start_B``(源A 最晚要等到月末才看见入场);
  实测入场滞后最小 21 天、无负值,这一侧没有取整问题。
* 出场侧 ``out_date_A >= prev_trading_day(end_B + 1 天)``
  (等价说法:先把 B 的自然日端点取整到交易日网格,再比)。
  ⚠️ **不是** ``out_date_A >= end_B`` —— 那个写法正是上面 245 条假矛盾的来源。
* 两侧偏差都应 ``<=`` 一个快照间隔(约一个月;交易日口径见 ``cfg.BOUNDARY_TOL_TD``)。
* **取整之后**方向仍然反了的,才是真矛盾,值得逐条查。

这五条与摘要 JSON 的 ``qlib_alignment.expected_direction_for_card_1_2`` 是同一份内容,
改一处必须同时改另一处(对抗审查 D5:本 docstring 曾与 JSON 互相打架)。

注:本文件只做**约定层**对齐,不做逐 code 对账 —— 那是卡 1.2(源B)的活。
摘要 JSON 的 ``qlib_alignment`` 块记录的是现场实测的结构事实,供卡 1.2 复用。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# ⚠️ 收紧 umask 必须发生在**任何仓库内 import 之前**,不能等到 main()。
#
# 本机默认 umask 是 002。CPython 在 import 一个模块时就会现建 `__pycache__/`
# 写字节码 —— 那一刻 main() 还没跑,`cfg.harden_umask()` 也还没被调到,
# 于是 `snapshots/__pycache__` 会落成 **0775**,踩掉卡 0.1 的红线 5 递归审计。
# 卡 0.2 的 builder 已经真的踩过一次,这里照抄它定下的三行。
#
# 字面量 0o077 是刻意重复 `cfg.REQUIRED_UMASK` 的 —— 它必须早于
# `import genebench_config` 生效,那时还拿不到常量。下面紧跟一条断言防漂移。
# ---------------------------------------------------------------------------
_PREVIOUS_UMASK = os.umask(0o077)

import pandas as pd  # noqa: E402

try:  # 允许 `python snapshots/universe_index_weight.py` 这种不带包上下文的跑法
    import genebench_config as cfg  # noqa: E402
except ModuleNotFoundError:  # pragma: no cover - 仅在裸脚本模式下走到
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import genebench_config as cfg  # noqa: E402

try:
    from snapshots import lake  # noqa: E402
except ModuleNotFoundError:  # pragma: no cover
    import lake  # type: ignore[no-redef] # noqa: E402

assert 0o077 == cfg.REQUIRED_UMASK, (
    f"上面硬写的 umask 0o077 与 cfg.REQUIRED_UMASK={oct(cfg.REQUIRED_UMASK)} 漂移了"
)

# ---------------------------------------------------------------------------
# 上面那行 umask 挡不住的那一个目录:**本模块所在包自己的字节码缓存**。
#
# 推荐跑法是 `python -m snapshots.universe_index_weight`,而 `-m` 会先 import
# 包 `snapshots`(执行 `snapshots/__init__.py`)。CPython 是在**编译那一刻**
# 就写 `snapshots/__pycache__/__init__.*.pyc` 的 —— 比本文件的第一行还早,
# 所以 `snapshots/__pycache__` 必带本机的 002 umask 落成 **0775**。
# 实测:只加上面的 umask 收紧,冷启动跑一次 builder 就能造出 0o775 的
# `snapshots/__pycache__`,踩红卡 0.1 的递归权限审计。
#
# 先有鸡先有蛋,没法靠"更早调用"解决,只能事后**幂等收敛** ——
# 和 `conftest.py` 对付它自己缓存目录的是同一套办法。
# `cfg.create_dir()` 对已存在的目录就是纯 chmod,正好干这个。
# ---------------------------------------------------------------------------
_REPO_ROOT_FOR_CACHE = Path(__file__).resolve().parents[1]

#: 本次收敛(chmod)了哪些缓存目录,便于排查。
CONVERGED_CACHE_DIRS: list[str] = []
for _cache in _REPO_ROOT_FOR_CACHE.rglob("__pycache__"):
    if not _cache.is_dir():
        continue
    if _cache.stat().st_mode & cfg.FORBIDDEN_MODE_BITS:
        CONVERGED_CACHE_DIRS.append(str(_cache))
    cfg.create_dir(_cache)

__all__ = [
    "SOURCE_VIEW",
    "CALENDAR_VIEW",
    "INTERVAL_COLUMNS",
    "WEIGHT_SUM_TOL",
    "assert_compact_date_convention",
    "load_snapshots",
    "snapshot_dates_by_universe",
    "off_size_periods",
    "diagnose_off_size",
    "previous_trading_day_map",
    "build_intervals",
    "turnover_by_universe",
    "universe_size_by_trading_day",
    "summarize",
    "parquet_metadata",
    "read_intervals",
    "universe_at",
    "write_outputs",
    "build",
    "main",
]

#: 源A 的唯一数据来源(catalog 只读 view)。
SOURCE_VIEW: str = "index_weight"

#: 交易日历。湖里只有 SSE 一个交易所 —— A 股两所日历一致,够用;
#: 这里只拿它做"前一个交易日"的推导,不做任何跨所判断。
CALENDAR_VIEW: str = "trade_cal"

#: 产物列顺序。**动这个顺序等于改产物 schema**,下游要跟着改。
INTERVAL_COLUMNS: tuple[str, ...] = (
    "code",
    "universe",
    "index_code",
    "segment_idx",
    "in_date",
    "out_date",
    "last_seen_snapshot",
    "prev_snapshot",
    "next_snapshot",
    "n_snapshots",
    "left_censored",
    "right_censored",
    "entry_gap_suspect",
    "exit_gap_suspect",
)

#: 每列一句话,直接写进摘要 JSON,免得下游还要回来读源码。
COLUMN_DOC: dict[str, str] = {
    "code": "成分股代码,湖内形态 `600000.SH`(不是 qlib 的 `SH600000`)。",
    "universe": "csi300 / csi500 / csi1000。",
    "index_code": "湖内 index_code,与 universe 一一对应。",
    "segment_idx": "同一 (code, universe) 内的第几段,按时间 0 起。",
    "in_date": "区间起(含),YYYYMMDD。= 首次观测到在成分内的那期快照日 T_i。",
    "out_date": (
        "区间止(含),YYYYMMDD。= 消失那期快照 T_{j+1} 的**前一个交易日**。"
        "右截断时为 NULL —— 表示区间开口,**不是** 20260731。"
    ),
    "last_seen_snapshot": (
        "最后一次**观测到**在成分内的那期快照日 T_j,永不为空。"
        "这是观测量;out_date 是约定量。想要内近似区间的下游用这一列。"
    ),
    "prev_snapshot": (
        "上一期快照日 T_{i-1}(该期观测到**不在**成分内);左截断时为 NULL。"
        "真实入场日 ∈ (prev_snapshot, in_date]。"
    ),
    "next_snapshot": (
        "消失那期快照日 T_{j+1};右截断时为 NULL。"
        "真实出场日 ∈ (last_seen_snapshot, next_snapshot]。"
    ),
    "n_snapshots": "本段覆盖的快照期数 j-i+1。",
    "left_censored": (
        "本段起于该宇宙**首期**快照,真实入场日不可知(≤ in_date)。"
        "**能不能靠源B 回溯,三个宇宙各不相同,不是通用承诺**:csi300 300/300 可回溯但"
        "统统撞到 qlib 自己的左边界 2005-04-08(可回溯天数 p50 == max == 1386,只是下界);"
        "csi500 466/500(93.2%);**csi1000 0/1000 —— 一只都补不了**(源B 首日与源A 首期同一天)。"
        "逐宇宙实测见 conventions.left_censored。"
    ),
    "right_censored": (
        "本段延续到**末期**(冻结线 20260731),未观测到出场 → out_date = NULL。"
    ),
    "entry_gap_suspect": (
        "形状是'在–缺–在':prev_snapshot 是一个**无法解释**的成分数缺额期"
        "(`classification == 'unexplained'`),**且**该 code 在**再上一期**也在成分内 —— "
        "本段起点可能是数据漏行造成的假调入。不修补,只标记。"
        "已被退市取证解释的缺额期(`index_vacancy`)**不**触发本标记。"
    ),
    "exit_gap_suspect": (
        "'在–缺–在'的出场侧:next_snapshot 是**无法解释**的缺额期,**且**该 code "
        "在**再下一期**又回到成分内 —— 本段终点可能是数据漏行造成的假调出。"
    ),
}


# --------------------------------------------------------------------------
# 读湖(只读)
# --------------------------------------------------------------------------


def assert_compact_date_convention(conn: Any | None = None) -> dict[str, str]:
    """守住本模块最底层的前提:``index_weight.trade_date`` 是 8 位 ``YYYYMMDD`` **字符串**。

    为什么值这两行(对抗审查 D7):同一份 gold 数据有**两条访问路径、两种类型** ——

    * catalog 的 ``index_weight`` view(本模块走的):``VARCHAR`` / ``'20090123'``
    * ``read_parquet('<GOLD>/index_weight/…')``:``DATE`` / ``2009-01-23``

    而 `AGENT_CONTEXT` 恰恰把裸 `read_parquet` 推荐为 "Too many open files" 的绕法。
    本模块**通篇**把 `trade_date` 当 8 位字符串做字典键和大小比较
    (``dates[i] < dates[j]``、``prev_of[d]``、``WHERE trade_date <= '20260731'``)。
    一旦有人把 `SOURCE_VIEW` 改指到裸 parquet,这些比较会**换一套语义**。

    好消息是混比会大声报错而不是静默出错;坏消息是没有任何一条断言写明这个前提。
    这里把它写下来:失败即 `LakeError`,并直说"视图口径变了"。

    Returns:
        实测到的类型样本,进摘要 JSON 留档。
    """
    probe = lake.query(
        f"SELECT any_value(typeof(trade_date)) AS t_date, "  # noqa: S608
        f"any_value(typeof(con_code)) AS t_code, "
        f"min(trade_date) AS min_date, max(trade_date) AS max_date FROM {SOURCE_VIEW}",
        conn=conn,
    ).iloc[0]
    observed = {
        "trade_date_typeof": str(probe["t_date"]),
        "con_code_typeof": str(probe["t_code"]),
        "min_trade_date": str(probe["min_date"]),
        "max_trade_date": str(probe["max_date"]),
    }
    if observed["trade_date_typeof"] != "VARCHAR" or len(observed["min_trade_date"]) != 8:
        raise lake.LakeError(
            f"{SOURCE_VIEW}.trade_date 的口径变了:实测 {observed} —— "
            f"本模块的 YYYYMMDD 8 位字符串约定失效(字典序比较、prev_trading_day 查表、"
            f"冻结线过滤全都建立在它上面)。先确认 catalog view 的定义,不要绕过去。"
        )
    return observed


def load_snapshots(
    conn: Any | None = None, freeze: str | None = None
) -> pd.DataFrame:
    """读 `index_weight` 的 (index_code, con_code, trade_date),**截到冻结线**。

    显式带 ``trade_date <= FREEZE`` 上界(红线 7):湖是活的,冻结线是 v1 的契约,
    不能靠"反正现在 max 就是 20260731"这种巧合来保证。

    Args:
        conn: 复用的只读连接。
        freeze: 冻结线(``YYYYMMDD``),默认 `lake.FREEZE_DATE_COMPACT`。
            **这个参数存在的唯一理由是让红线 7 可被证伪**(对抗审查 D8):
            湖里的 `index_weight` 本身就冻在 20260731,所以真实冻结线下
            ``WHERE trade_date <= ?`` 是个恒真条件,过滤逻辑被误删也不会有测试变红。
            负控测试传一个更早的日期进来,断言产物真的被截短了。

    Returns:
        列 ``index_code / con_code / trade_date``,已按 (index_code, con_code,
        trade_date) 排好序;`trade_date` / `con_code` 都是 ``YYYYMMDD`` / 湖内形态字符串。

    Raises:
        LakeError: 湖里出现了 `cfg.UNIVERSE_INDEX_CODE` 之外的 index_code
            —— 那说明宇宙映射表过期了,必须先修映射再跑,不能默默丢数据;
            或 `SOURCE_VIEW` 的日期口径不再是 8 位字符串(见
            `assert_compact_date_convention`)。
    """
    assert_compact_date_convention(conn=conn)
    df = lake.query(
        f"SELECT index_code, con_code, trade_date FROM {SOURCE_VIEW} "  # noqa: S608
        "WHERE trade_date <= ? "
        "ORDER BY index_code, con_code, trade_date",
        [freeze or lake.FREEZE_DATE_COMPACT],
        conn=conn,
    )
    unknown = sorted(set(df["index_code"]) - set(cfg.INDEX_CODE_UNIVERSE))
    if unknown:
        raise lake.LakeError(
            f"{SOURCE_VIEW} 里出现了未登记的 index_code:{unknown};"
            f" 已登记的是 {sorted(cfg.INDEX_CODE_UNIVERSE)}。"
            f" 先更新 cfg.UNIVERSE_INDEX_CODE,不要默默丢数据。"
        )
    return df


def snapshot_dates_by_universe(df: pd.DataFrame) -> dict[str, list[str]]:
    """每个宇宙的快照期次(升序、去重)。

    三个宇宙**各自**取自己的期次:csi1000 从 20141031 起,比 csi300/500 晚 142 期,
    共用一套日期会给 csi1000 凭空造出 69 期"全员缺席"。
    """
    out: dict[str, list[str]] = {}
    for uni in cfg.UNIVERSES:
        code = cfg.UNIVERSE_INDEX_CODE[uni]
        dates = sorted(set(df.loc[df["index_code"] == code, "trade_date"]))
        out[uni] = dates
    return out


def off_size_periods(df: pd.DataFrame) -> dict[str, list[dict[str, Any]]]:
    """点名成分数**不等于名义值**的期次(数据质量信号)。

    不修补。修补需要知道"少的是哪两只",而那正是本源看不见的东西;
    悄悄补上会把一个已知缺陷变成一个看不见的缺陷。
    """
    out: dict[str, list[dict[str, Any]]] = {}
    for uni in cfg.UNIVERSES:
        code = cfg.UNIVERSE_INDEX_CODE[uni]
        want = cfg.UNIVERSE_NOMINAL_SIZE[uni]
        sub = df[df["index_code"] == code]
        counts = sub.groupby("trade_date")["con_code"].agg(["count", "nunique"])
        bad = []
        for date, row in counts.iterrows():
            n = int(row["count"])
            if n != want or int(row["nunique"]) != want:
                bad.append(
                    {
                        "trade_date": str(date),
                        "n_rows": n,
                        "n_distinct_codes": int(row["nunique"]),
                        "nominal": want,
                        "delta": n - want,
                    }
                )
        out[uni] = sorted(bad, key=lambda r: r["trade_date"])
    return out


#: 判"指数真空缺"时,权重和允许偏离 100 的绝对量。
#:
#: 实测三宇宙全部 564 期的权重和落在 ``[99.90, 100.11]``;若真漏了行,
#: 权重和应当少掉漏掉那几只的权重量级(实测 ``min(weight)=0.007``,
#: 大盘股是 0.1~0.6)。0.5 既装得下正常抖动,又接不住"漏了一只大票"。
WEIGHT_SUM_TOL: float = 0.5


def diagnose_off_size(
    df: pd.DataFrame,
    dates_by_universe: dict[str, list[str]],
    off_size: dict[str, list[dict[str, Any]]],
    conn: Any | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """给每个**成分数缺额期**判成因:是"指数真空缺",还是"数据漏行"。

    对抗审查 D1/D2 的修法。原实现只会说"这期不满额"就一律当数据缺陷,
    于是把一次**正常的公司行为**(两只票同日吸收合并退市,指数短暂空 2 席)
    判成 ``FAIL``,还把缺额期之后**整份调入名单**染成 ``entry_gap_suspect``。

    判据两条,都要满足才归 ``index_vacancy``:

    1. **权重和仍≈100**(``|sum(weight) - 100| <= WEIGHT_SUM_TOL``)。
       漏行会连带漏掉权重;真空缺不会 —— 指数编制方把剩下的成分重新归一。
    2. **缺的席位有退市取证**:这期相对上一期掉出去的票里,至少有 ``-delta`` 只
       的 ``stock_basic.delist_date`` 落在 ``(prev_snapshot, trade_date]`` 内。

    两条有一条不成立就归 ``unexplained`` —— 那才是真该查的。

    这是本模块唯一一处读 `weight` 的地方,**只用于判成因,不进产物、不进任何
    成员判定**(对抗审查 V5:``load_snapshots()`` 压根没 select 它)。

    Args:
        df: `load_snapshots()` 的结果。
        dates_by_universe: 每宇宙的期次。
        off_size: `off_size_periods()` 的结果。
        conn: 复用的只读连接。

    Returns:
        ``{universe: [ {trade_date, delta, classification, sum_weight,
        delisted_explaining_vacancy, dropped_codes, ...}, ... ]}``。
    """
    out: dict[str, list[dict[str, Any]]] = {u: [] for u in cfg.UNIVERSES}
    if not any(off_size.values()):
        return out

    weight_sums = lake.query(
        f"SELECT index_code, trade_date, sum(weight) AS sum_weight "  # noqa: S608
        f"FROM {SOURCE_VIEW} WHERE trade_date <= ? GROUP BY 1, 2",
        [lake.FREEZE_DATE_COMPACT],
        conn=conn,
    )
    wmap = {
        (r.index_code, r.trade_date): float(r.sum_weight)
        for r in weight_sums.itertuples(index=False)
    }
    # `stock_basic` 是**多快照**表(19 个快照 × 同一 ts_code),直接 join 会把行数
    # 乘 19。实测 list_date / delist_date / list_status 在 19 个快照间**零漂移**,
    # 所以 DISTINCT 之后恰好一码一行(5890/5890)。
    basic = lake.query(
        "SELECT DISTINCT ts_code, delist_date FROM stock_basic "
        "WHERE delist_date IS NOT NULL",
        conn=conn,
    )
    delist_of = {r.ts_code: r.delist_date for r in basic.itertuples(index=False)}

    for uni in cfg.UNIVERSES:
        rows = off_size[uni]
        if not rows:
            continue
        index_code = cfg.UNIVERSE_INDEX_CODE[uni]
        dates = dates_by_universe[uni]
        pos = {d: i for i, d in enumerate(dates)}
        sub = df[df["index_code"] == index_code]
        members: dict[str, set[str]] = defaultdict(set)
        for code, td in zip(sub["con_code"], sub["trade_date"]):
            members[td].add(code)
        for r in rows:
            d = r["trade_date"]
            i = pos[d]
            prev = dates[i - 1] if i > 0 else None
            dropped = sorted(members[prev] - members[d]) if prev else []
            added = sorted(members[d] - members[prev]) if prev else []
            explaining = [
                {"code": c, "delist_date": delist_of[c]}
                for c in dropped
                if c in delist_of and prev is not None and prev < delist_of[c] <= d
            ]
            sw = wmap.get((index_code, d))
            weight_ok = sw is not None and abs(sw - 100.0) <= WEIGHT_SUM_TOL
            seats_short = -r["delta"] if r["delta"] < 0 else 0
            delist_ok = seats_short > 0 and len(explaining) >= seats_short
            classification = (
                "index_vacancy" if (weight_ok and delist_ok) else "unexplained"
            )
            out[uni].append(
                {
                    "trade_date": d,
                    "prev_snapshot": prev,
                    "delta": r["delta"],
                    "n_rows": r["n_rows"],
                    "nominal": r["nominal"],
                    "sum_weight": round(sw, 4) if sw is not None else None,
                    "weight_sum_within_tolerance": weight_ok,
                    "weight_sum_tolerance": WEIGHT_SUM_TOL,
                    "n_dropped_vs_prev": len(dropped),
                    "n_added_vs_prev": len(added),
                    "delisted_explaining_vacancy": explaining,
                    "n_seats_short": seats_short,
                    "classification": classification,
                    "why": (
                        "权重和仍≈100 且缺的席位有同窗口内的 delist_date 取证 —— "
                        "指数在合并退市后短暂空缺,属正常公司行为,不是数据缺陷。"
                        if classification == "index_vacancy"
                        else "权重和异常或缺的席位没有退市取证 —— 无法解释,必须逐条查。"
                    ),
                }
            )
    return out


def previous_trading_day_map(
    dates: Iterable[str], conn: Any | None = None
) -> dict[str, str]:
    """给每个 `dates` 里的日期算出它的**前一个交易日**。

    只用 `trade_cal` 里 ``is_open = 1`` 的日期,并且**截到冻结线**。

    Args:
        dates: 待求前一交易日的日期(``YYYYMMDD``),必须都是交易日本身。
        conn: 复用的只读连接。

    Returns:
        ``{date: previous_trading_day}``。

    Raises:
        LakeError: 某个输入日期不在交易日历里(说明快照日不是交易日 —— 数据出事了),
            或它是日历上的第一个交易日(没有前一天)。
    """
    cal = lake.query(
        f"SELECT cal_date FROM {CALENDAR_VIEW} "  # noqa: S608
        "WHERE is_open = 1 AND cal_date <= ? ORDER BY cal_date",
        [lake.FREEZE_DATE_COMPACT],
        conn=conn,
    )["cal_date"].tolist()
    prev_of = {cur: prv for prv, cur in zip(cal, cal[1:])}
    known = set(cal)
    out: dict[str, str] = {}
    for d in dates:
        if d not in known:
            raise lake.LakeError(
                f"快照日 {d} 不在 {CALENDAR_VIEW}(is_open=1)里 —— "
                f"月末快照日理应是交易日,这是数据质量事故,不要绕过去。"
            )
        if d not in prev_of:
            raise lake.LakeError(f"{d} 是交易日历上的第一天,没有前一个交易日。")
        out[d] = prev_of[d]
    return out


# --------------------------------------------------------------------------
# 核心:相邻期 diff → 区间
# --------------------------------------------------------------------------


def build_intervals(
    df: pd.DataFrame,
    dates_by_universe: dict[str, list[str]],
    prev_trading_day: dict[str, str],
    off_size: dict[str, list[dict[str, Any]]],
    off_size_diag: dict[str, list[dict[str, Any]]] | None = None,
) -> pd.DataFrame:
    """把逐期名单折成区间表。

    算法:按 (universe, code) 收集"在第几期出现",期序号连续的并成一段。
    每段按第 1.1 节的约定落 `in_date` / `out_date`,并把观测量
    (`last_seen_snapshot`)与不确定性窗口(`prev_snapshot` / `next_snapshot`)
    一起带出来 —— 下游不用回头再查湖就能自己收窄或放宽。

    Args:
        df: `load_snapshots()` 的结果。
        dates_by_universe: 每宇宙的期次。
        prev_trading_day: `previous_trading_day_map()` 的结果。
        off_size: `off_size_periods()` 的结果。
        off_size_diag: `diagnose_off_size()` 的结果。**缺省 = 全部当
            ``unexplained``**(保守)。只有被判成 ``index_vacancy`` 的缺额期
            才不会触发 suspect 标记 —— 见下面 D1 那段。

    Returns:
        列见 `INTERVAL_COLUMNS`,按 (universe 按 `cfg.UNIVERSES` 顺序, code,
        segment_idx) 排序,确定性可复现。
    """
    # ------------------------------------------------------------------
    # `entry_gap_suspect` / `exit_gap_suspect` 的判据(对抗审查 D1 后收窄)
    #
    # 旧判据是"prev_snapshot 是个缺额期"。它把缺额期**之后整份调入名单**无差别
    # 染红:实测 20 行 True 里 **0 行**站得住 —— 18 个 entry 标记全部挂在
    # 20100129 那次正常调入上,其中 17 只在 20091231 之前**从未**进过 csi300,
    # 还有两只(中国建筑 / 中国中冶)是 2009 年才上市的新股。要检验的假设
    # ("它其实在缺额期名单里、只是行丢了")的必要条件是**它在缺额期的上一期在成分内**,
    # 而这 18 只没有一只满足。
    #
    # 收窄成两条**同时**成立:
    #   1. 相邻的那个缺额期被判成 `unexplained`(不是已被退市解释的 index_vacancy);
    #   2. 形状真的是"在–缺–在":该 code 在缺额期的**再上一期**也在成分内
    #      (出场侧对称:缺额期的**再下一期**又回来了)。
    #
    # 在本数据上两条合起来的结果是 0 行 —— 这是**正确的零**,不是失效的检查:
    # 负控测试 `ops/test_universe_source_a.py::test_gap_suspect_fires_on_synthetic_hole`
    # 造一个人工"在–缺–在"的洞,断言标记会亮。
    # ------------------------------------------------------------------
    diag = off_size_diag or {}
    unexplained_dates = {
        uni: {
            r["trade_date"]
            for r in diag.get(uni, [])
            if r.get("classification") != "index_vacancy"
        }
        if uni in diag
        else {r["trade_date"] for r in off_size.get(uni, [])}
        for uni in cfg.UNIVERSES
    }

    rows: list[dict[str, Any]] = []
    for uni in cfg.UNIVERSES:
        index_code = cfg.UNIVERSE_INDEX_CODE[uni]
        dates = dates_by_universe[uni]
        if not dates:
            continue
        pos = {d: i for i, d in enumerate(dates)}
        last_pos = len(dates) - 1
        bad_pos = {pos[d] for d in unexplained_dates.get(uni, set()) if d in pos}

        sub = df[df["index_code"] == index_code]
        seen: dict[str, list[int]] = defaultdict(list)
        for code, td in zip(sub["con_code"], sub["trade_date"]):
            seen[code].append(pos[td])

        for code in sorted(seen):
            idxs = sorted(set(seen[code]))
            # 切成"期序号连续"的极大段
            runs: list[tuple[int, int]] = []
            start = prev = idxs[0]
            for i in idxs[1:]:
                if i == prev + 1:
                    prev = i
                    continue
                runs.append((start, prev))
                start = prev = i
            runs.append((start, prev))

            present = set(idxs)
            for seg_idx, (i, j) in enumerate(runs):
                left_censored = i == 0
                right_censored = j == last_pos
                prev_snap = None if left_censored else dates[i - 1]
                next_snap = None if right_censored else dates[j + 1]
                in_date = dates[i]
                last_seen = dates[j]
                out_date = None if next_snap is None else prev_trading_day[next_snap]
                if out_date is not None and out_date < in_date:
                    # 只有当两期快照是相邻交易日时才可能发生;月末节奏下不该出现。
                    raise lake.LakeError(
                        f"{uni}/{code} 第 {seg_idx} 段算出 out_date={out_date} "
                        f"< in_date={in_date}(next_snapshot={next_snap}) —— "
                        f"两期快照相隔不到一个交易日,约定失效,先查数据。"
                    )
                rows.append(
                    {
                        "code": code,
                        "universe": uni,
                        "index_code": index_code,
                        "segment_idx": seg_idx,
                        "in_date": in_date,
                        "out_date": out_date,
                        "last_seen_snapshot": last_seen,
                        "prev_snapshot": prev_snap,
                        "next_snapshot": next_snap,
                        "n_snapshots": j - i + 1,
                        "left_censored": left_censored,
                        "right_censored": right_censored,
                        # "在–缺–在" 才算可疑:缺额期(未被解释)紧邻本段边界,
                        # **且**该 code 在缺额期的另一侧也在成分内。
                        "entry_gap_suspect": (
                            i - 1 in bad_pos and (i - 2) in present
                        ),
                        "exit_gap_suspect": (
                            j + 1 in bad_pos and (j + 2) in present
                        ),
                    }
                )

    frame = pd.DataFrame(rows, columns=list(INTERVAL_COLUMNS))
    if frame.empty:  # pragma: no cover - 湖空了才会走到
        return frame
    order = {u: i for i, u in enumerate(cfg.UNIVERSES)}
    frame = (
        frame.assign(_u=frame["universe"].map(order))
        .sort_values(["_u", "code", "segment_idx"], kind="mergesort")
        .drop(columns="_u")
        .reset_index(drop=True)
    )
    for col in (
        "code",
        "universe",
        "index_code",
        "in_date",
        "out_date",
        "last_seen_snapshot",
        "prev_snapshot",
        "next_snapshot",
    ):
        frame[col] = frame[col].astype("string")
    for col in ("segment_idx", "n_snapshots"):
        frame[col] = frame[col].astype("int32")
    for col in (
        "left_censored",
        "right_censored",
        "entry_gap_suspect",
        "exit_gap_suspect",
    ):
        frame[col] = frame[col].astype("bool")
    return frame


# --------------------------------------------------------------------------
# 统计
# --------------------------------------------------------------------------


def _dist(values: list[int]) -> dict[str, Any]:
    """min / p25 / median / p75 / **p95** / max / mean / n + **仅非零期的条件分布**。

    对抗审查 D9:csi300 的 `adds` 有 210 个转移里 168 个是零变动,于是
    ``p25 == median == p75 == 0``,读起来像"这个指数不换手",而实际
    ``mean = 3.448``、``max = 30``(= 10% 的调仓上限)。四分位没算错,是**误导**。
    补 `p95` 和 `nonzero`(只在真的发生了调仓的那些期上算)才看得见量级。
    """
    if not values:
        return {"n": 0}
    ordered = sorted(values)

    def _q(xs: list[int], frac: float) -> float:
        """线性插值分位数。手写而不用 `statistics.quantiles`:后者在 n<2 时抛异常,
        而这里 `nonzero` 子集完全可能只有 0~1 个元素。"""
        if not xs:
            return 0.0
        if len(xs) == 1:
            return float(xs[0])
        p = frac * (len(xs) - 1)
        lo = int(p)
        hi = min(lo + 1, len(xs) - 1)
        return float(xs[lo] + (xs[hi] - xs[lo]) * (p - lo))

    nonzero = [v for v in ordered if v != 0]
    return {
        "n": len(ordered),
        "min": ordered[0],
        "p25": int(round(_q(ordered, 0.25))),
        "median": float(statistics.median(ordered)),
        "p75": int(round(_q(ordered, 0.75))),
        "p95": int(round(_q(ordered, 0.95))),
        "max": ordered[-1],
        "mean": round(statistics.fmean(ordered), 3),
        "zero_change_periods": len(ordered) - len(nonzero),
        "nonzero": {
            "n": len(nonzero),
            "min": nonzero[0] if nonzero else None,
            "median": float(statistics.median(nonzero)) if nonzero else None,
            "p95": int(round(_q(nonzero, 0.95))) if nonzero else None,
            "max": nonzero[-1] if nonzero else None,
            "mean": round(statistics.fmean(nonzero), 3) if nonzero else None,
        },
        "note": (
            "零变动期占多数时,p25/median/p75 会全是 0 —— 那不是'不换手',"
            "看 `nonzero` 与 `p95`。"
        ),
    }


def turnover_by_universe(
    df: pd.DataFrame, dates_by_universe: dict[str, list[str]]
) -> dict[str, Any]:
    """相邻两期之间的换手只数:调入 |S_k \\ S_{k-1}| 与调出 |S_{k-1} \\ S_k|。

    成分数恒定时 adds == drops;两者不等的那几期,差额恰好等于成分数的变化 ——
    这是缺额期的另一种表现,所以顺手把不等的期次点出来。
    """
    out: dict[str, Any] = {}
    for uni in cfg.UNIVERSES:
        index_code = cfg.UNIVERSE_INDEX_CODE[uni]
        dates = dates_by_universe[uni]
        sub = df[df["index_code"] == index_code]
        members: dict[str, set[str]] = defaultdict(set)
        for code, td in zip(sub["con_code"], sub["trade_date"]):
            members[td].add(code)
        adds: list[int] = []
        drops: list[int] = []
        detail: list[dict[str, Any]] = []
        asym: list[dict[str, Any]] = []
        for prv, cur in zip(dates, dates[1:]):
            a = len(members[cur] - members[prv])
            d = len(members[prv] - members[cur])
            adds.append(a)
            drops.append(d)
            detail.append({"from": prv, "to": cur, "adds": a, "drops": d})
            if a != d:
                asym.append(
                    {
                        "from": prv,
                        "to": cur,
                        "adds": a,
                        "drops": d,
                        "size_change": len(members[cur]) - len(members[prv]),
                    }
                )
        out[uni] = {
            "n_transitions": len(adds),
            "adds": _dist(adds),
            "drops": _dist(drops),
            "asymmetric_transitions": asym,
            "top5_by_adds": sorted(detail, key=lambda r: -r["adds"])[:5],
        }
    return out


def _missing_row_suspects(
    df: pd.DataFrame,
    dates_by_universe: dict[str, list[str]],
    off_size: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    """缺额期里,"前一期在、后一期也在、偏偏这期不在"的代码 —— 高度疑似漏行。

    点名到具体代码,是为了让人能拿去跟 tushare 原始数据核对;
    本模块自己**不**据此改任何区间。
    """
    out: dict[str, list[dict[str, Any]]] = {}
    for uni in cfg.UNIVERSES:
        rows = off_size[uni]
        if not rows:
            out[uni] = []
            continue
        index_code = cfg.UNIVERSE_INDEX_CODE[uni]
        dates = dates_by_universe[uni]
        pos = {d: i for i, d in enumerate(dates)}
        sub = df[df["index_code"] == index_code]
        members: dict[str, set[str]] = defaultdict(set)
        for code, td in zip(sub["con_code"], sub["trade_date"]):
            members[td].add(code)
        found: list[dict[str, Any]] = []
        for r in rows:
            d = r["trade_date"]
            i = pos[d]
            if i == 0 or i == len(dates) - 1:
                continue
            before, after = dates[i - 1], dates[i + 1]
            both = (members[before] & members[after]) - members[d]
            for code in sorted(both):
                found.append(
                    {
                        "trade_date": d,
                        "code": code,
                        "present_at_prev": before,
                        "present_at_next": after,
                    }
                )
        out[uni] = found
    return out


def _off_size_detail(
    df: pd.DataFrame,
    dates_by_universe: dict[str, list[str]],
    off_size: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    """缺额期前后到底进出了哪些代码 —— 让人能拿去跟原始数据源核对。

    `_missing_row_suspects()` 只回答"是不是漏行"这一种假设;它为空**不等于**
    这期没问题,只说明缺的那几只不是"前后都在、中间掉了"的形状。
    所以这里把缺额期两侧的实际进出名单原样列出来,不做任何解释。
    """
    out: dict[str, list[dict[str, Any]]] = {}
    for uni in cfg.UNIVERSES:
        rows = off_size[uni]
        if not rows:
            out[uni] = []
            continue
        index_code = cfg.UNIVERSE_INDEX_CODE[uni]
        dates = dates_by_universe[uni]
        pos = {d: i for i, d in enumerate(dates)}
        sub = df[df["index_code"] == index_code]
        members: dict[str, set[str]] = defaultdict(set)
        for code, td in zip(sub["con_code"], sub["trade_date"]):
            members[td].add(code)
        detail = []
        for r in rows:
            d = r["trade_date"]
            i = pos[d]
            before = dates[i - 1] if i > 0 else None
            after = dates[i + 1] if i < len(dates) - 1 else None
            detail.append(
                {
                    "trade_date": d,
                    "delta": r["delta"],
                    "prev_snapshot": before,
                    "next_snapshot": after,
                    "dropped_entering_this_period": sorted(
                        members[before] - members[d]
                    )
                    if before
                    else None,
                    "added_entering_this_period": sorted(members[d] - members[before])
                    if before
                    else None,
                    "dropped_leaving_this_period": sorted(members[d] - members[after])
                    if after
                    else None,
                    "added_leaving_this_period": sorted(members[after] - members[d])
                    if after
                    else None,
                    "came_back_next_period": sorted(
                        (members[before] - members[d]) & members[after]
                    )
                    if before and after
                    else None,
                }
            )
        out[uni] = detail
    return out


def _qlib_alignment() -> dict[str, Any]:
    """现场实测源B(qlib instruments)的**结构事实**,供卡 1.2 复用。

    只看约定层(行数 / 段数 / 是否贴片 / 右端怎么截 / 切点粒度),
    **不做逐 code 对账** —— 那是卡 1.2。qlib release 目录不在就返回 unavailable,
    源A 不该因为源B 缺席而失败。
    """
    root = cfg.QLIB_RELEASE / "instruments"
    if not root.is_dir():
        return {"status": "unavailable", "dir": str(root)}
    out: dict[str, Any] = {"status": "ok", "dir": str(root), "universes": {}}
    for uni in cfg.UNIVERSES:
        path = root / f"{uni}.txt"
        if not path.is_file():
            out["universes"][uni] = {"status": "missing", "path": str(path)}
            continue
        rows = [ln.split("\t") for ln in path.read_text().splitlines() if ln.strip()]
        per_code: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for r in rows:
            per_code[r[0]].append((r[1], r[2]))
        touching = gapped = merged = 0
        for segs in per_code.values():
            segs.sort()
            merged += 1
            for (_s1, e1), (s2, _e2) in zip(segs, segs[1:]):
                nxt = _dt.date.fromisoformat(e1) + _dt.timedelta(days=1)
                if _dt.date.fromisoformat(s2) == nxt:
                    touching += 1
                else:
                    gapped += 1
                    merged += 1
        starts = sorted({r[1] for r in rows})
        ends = sorted({r[2] for r in rows})
        out["universes"][uni] = {
            "status": "ok",
            "n_lines": len(rows),
            "n_codes": len(per_code),
            "n_segments_after_merging_adjacent": merged,
            "adjacent_pairs_touching": touching,
            "adjacent_pairs_with_gap": gapped,
            "n_distinct_starts": len(starts),
            "min_start": starts[0],
            "max_end": ends[-1],
            "n_lines_at_max_end": sum(1 for r in rows if r[2] == ends[-1]),
            "code_form_example": rows[0][0],
            "date_form_example": rows[0][1],
        }
    return out


def universe_size_by_trading_day(
    df: pd.DataFrame, dates_by_universe: dict[str, list[str]]
) -> dict[str, dict[int, int]]:
    """在**每个快照期**上数宇宙规模,给出 ``{universe: {size: 期数}}`` 直方图。

    对抗审查 D4:docstring 曾写"每个交易日的宇宙规模恒等于名义值 300/500/1000",
    被自家数据证伪(csi300 有 20 个交易日是 298)。绝对句式会被下游当不变量依赖
    (``assert len(univ) == 300``)。这里把真实分布算出来写进摘要,
    并由 `ops/test_universe_source_a.py` 把"允许的例外"钉成白名单。

    注:LOCF 展开到逐**交易日**与按**期**统计给出的是同一张直方图的两种权重,
    这里按期算(便宜、可复现);逐交易日版本见对抗审查 adv_a1。
    """
    out: dict[str, dict[int, int]] = {}
    for uni in cfg.UNIVERSES:
        index_code = cfg.UNIVERSE_INDEX_CODE[uni]
        sub = df[df["index_code"] == index_code]
        counts = sub.groupby("trade_date")["con_code"].nunique()
        hist: dict[int, int] = defaultdict(int)
        for n in counts:
            hist[int(n)] += 1
        out[uni] = dict(sorted(hist.items()))
    return out


def summarize(
    df: pd.DataFrame,
    intervals: pd.DataFrame,
    dates_by_universe: dict[str, list[str]],
    off_size: dict[str, list[dict[str, Any]]],
    off_size_diag: dict[str, list[dict[str, Any]]] | None = None,
    date_types: dict[str, str] | None = None,
) -> dict[str, Any]:
    """摘要 JSON 的全部内容:约定 + 数据卡 + 逐宇宙统计 + 完整性自查。"""
    diag = off_size_diag or {u: [] for u in cfg.UNIVERSES}
    per_universe: dict[str, Any] = {}
    for uni in cfg.UNIVERSES:
        dates = dates_by_universe[uni]
        sel = intervals[intervals["universe"] == uni]
        nominal = cfg.UNIVERSE_NOMINAL_SIZE[uni]
        bad = off_size[uni]
        n_seg_per_code = sel.groupby("code").size()
        per_universe[uni] = {
            "index_code": cfg.UNIVERSE_INDEX_CODE[uni],
            "nominal_size": nominal,
            "n_intervals": int(len(sel)),
            "n_distinct_codes": int(sel["code"].nunique()),
            "n_left_censored": int(sel["left_censored"].sum()),
            "n_right_censored": int(sel["right_censored"].sum()),
            "n_entry_gap_suspect": int(sel["entry_gap_suspect"].sum()),
            "n_exit_gap_suspect": int(sel["exit_gap_suspect"].sum()),
            "n_codes_with_multiple_segments": int((n_seg_per_code > 1).sum()),
            "max_segments_per_code": int(n_seg_per_code.max()) if len(sel) else 0,
            "size_is_constant": not bad,
            "n_periods": len(dates),
            "n_periods_at_nominal_size": len(dates) - len(bad),
            "off_size_periods": bad,
            "date_coverage": {
                "first_snapshot": dates[0] if dates else None,
                "last_snapshot": dates[-1] if dates else None,
                "n_snapshots": len(dates),
                "snapshots": dates,
            },
        }

    return {
        "card": "1.1-sourceA",
        "title": "PIT 宇宙源A:index_weight 月末快照 diff → 成分区间",
        "generated_at_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(
            timespec="seconds"
        ),
        "generator": "snapshots/universe_index_weight.py",
        "source_view": SOURCE_VIEW,
        "calendar_view": CALENDAR_VIEW,
        "freeze_line": lake.FREEZE_DATE_COMPACT,
        "source_rows_upto_freeze": int(len(df)),
        "conventions": {
            "in_date": "T_i —— 首次观测到在成分内的那期快照日(不外推到上一期次日)。",
            "out_date": (
                "prev_trading_day(T_{j+1}) —— 消失那期快照的前一个交易日;"
                "右截断为 NULL。"
            ),
            "why": (
                "唯一判据是 PIT:区间里每一天只能用那天(含)之前已有的信息推出来。"
                "入场提前到 T_{i-1}+1 = 用一份还没公布的名单建仓(前视);"
                "出场收缩到 T_j = 靠一份还没出生的名单提前减仓(同样是前视)。"
                "两条合起来等价于:任意交易日 D 的宇宙 = 不晚于 D 的最后一期快照,"
                "即 last-observation-carried-forward。"
            ),
            "resolution": (
                "分辨率上限 = 快照粒度(约一个月)。真实入场 ∈ (prev_snapshot, in_date],"
                "真实出场 ∈ (last_seen_snapshot, next_snapshot];两个窗口都在产物里。"
            ),
            "interval_closure": "闭区间 [in_date, out_date],两端都含。",
            "out_date_day_type": (
                "取前一个**交易日**而非前一个自然日。在交易日网格上两者过滤结果相同,"
                "但交易日版本能直接与 daily / trade_cal 对齐,省下游一次日历取整。"
                "qlib 用自然日,对齐时注意。"
            ),
            "left_censored": (
                "首期出现的票,真实入场日不可知(≤ in_date)。in_date 仍填首期,"
                "另有布尔字段标记 —— 填 NULL 会逼下游写 fillna,而首期是安全可用的下界。"
                "**能不能靠源B 回溯,三个宇宙各不相同(实测):** "
                "csi300 首期 300 只**全部**能回溯,但可回溯天数 p50 == max == 1386 天,"
                "说明这 300 只**统统撞到了 qlib 自己的左边界 2005-04-08** —— "
                "1386 天只是**下界**,真实在册时长被低估得更多;"
                "csi500 466/500(93.2%)可回溯,最多 723 天;"
                "**csi1000 0/1000 —— 一只都补不了**(源B 首日 20141031 与源A 首期同一天)。"
                "把'真正的下界靠源B 回溯'当成三个宇宙通用的承诺是错的。"
            ),
            "right_censored": (
                "末期(= 冻结线 20260731)仍在成分内的票:out_date = NULL,不是 20260731。"
                "写成 20260731 会被读成'当天被调出',凭空造一次调仓。"
            ),
            "multi_segment": "按期序号连续切段,一只票多次进出 → 多行,segment_idx 从 0 起。",
        },
        "columns": COLUMN_DOC,
        "limitations": [
            "月内调整被完全抹平:月中调进、同月又调出的票在源A 里根本不存在;"
            "月中的调整会被记到月末那一期,所有日期有最多约一个月的系统性滞后。",
            "分辨率 = 快照粒度,要精确到日必须换源(源B qlib instruments / 指数调整公告)。",
            "首期左截断、末期右截断,见 conventions。",
            "成分数缺额期里的'消失/出现'可能混有数据漏行造成的假调仓;本模块不修补,"
            "只判成因(index_vacancy / unexplained)并对'在–缺–在'形状的段边界打 "
            "entry_gap_suspect / exit_gap_suspect。本数据上这两列全为 False。",
            "宇宙规模**不**恒等于名义值:csi300 在 20091231→20100128 的 20 个交易日是 298"
            "(合并退市留下的 2 席真空缺)。下游不要写 assert len(univ) == nominal。",
            "**产物本身不带时间上下界**:parquet 的 schema metadata 里写了 "
            "valid_from / valid_to,但按 in_date <= D <= out_date 过滤的下游若不读它,"
            "把 D 取到冻结线之外会安静地拿到末期名单,取到首期之前会安静地拿到空集。"
            "**唯一安全的读法是 `universe_at()`**,它会对越界的 D 抛错。",
            "冻结线 2026-07-31(红线 7):查询显式带上界,湖继续前进不污染 v1。",
            "weight 字段未进产物:源A 只回答'在不在',不回答'占多少'(权重是卡 3.2)。",
            "trade_cal 只有 SSE 一个交易所;A 股两所日历一致,"
            "本模块也只用它推'前一个交易日',不做跨所判断。",
        ],
        "integrity": {
            "source_view_date_types": date_types or {},
            "size_histogram_by_period": {
                uni: {str(k): v for k, v in hist.items()}
                for uni, hist in universe_size_by_trading_day(
                    df, dates_by_universe
                ).items()
            },
            "nominal_size_verdict_legend": {
                "PASS": "每期都恰好等于名义值。",
                "VACANCY_EXPLAINED": (
                    "有缺额期,但**每一个**都被判成 `index_vacancy` —— 权重和仍≈100 "
                    "且缺的席位有同窗口内的 delist_date 取证(合并退市留下的空席)。"
                    "属正常公司行为,不是数据缺陷。"
                ),
                "FAIL": "有缺额期无法解释(权重和异常 或 缺席位没有退市取证),必须逐条查。",
            },
            "nominal_size_check": {
                uni: {
                    "nominal": cfg.UNIVERSE_NOMINAL_SIZE[uni],
                    "n_periods": len(dates_by_universe[uni]),
                    "n_off_size": len(off_size[uni]),
                    "off_size_periods": off_size[uni],
                    "off_size_diagnosis": diag.get(uni, []),
                    # 对抗审查 D2:三态。旧实现只要有一期不满额就报 FAIL,
                    # 于是把"两只票同日吸收合并退市、指数短暂空 2 席"这件正常事
                    # 判成整份摘要里唯一的 FAIL,任何自动门禁都会被它绊住。
                    "verdict": (
                        "PASS"
                        if not off_size[uni]
                        else (
                            "VACANCY_EXPLAINED"
                            if diag.get(uni)
                            and all(
                                r["classification"] == "index_vacancy"
                                for r in diag[uni]
                            )
                            else "FAIL"
                        )
                    ),
                }
                for uni in cfg.UNIVERSES
            },
            "missing_row_suspects_note": (
                "只检验'前一期在、后一期也在、偏偏这期不在'这一种假设(简单漏行)。"
                "**为空不等于这期没问题** —— 只说明缺的那几只不是这个形状。"
                "缺额期两侧的实际进出名单见 off_size_detail,自己看。"
            ),
            "missing_row_suspects": _missing_row_suspects(
                df, dates_by_universe, off_size
            ),
            "off_size_detail": _off_size_detail(df, dates_by_universe, off_size),
            "duplicate_rows_in_source": int(
                len(df) - len(df.drop_duplicates(["index_code", "con_code", "trade_date"]))
            ),
            "intervals_with_out_before_in": int(
                (
                    intervals["out_date"].notna()
                    & (intervals["out_date"] < intervals["in_date"])
                ).sum()
            ),
        },
        "turnover": turnover_by_universe(df, dates_by_universe),
        "universes": per_universe,
        "totals": {
            "n_intervals": int(len(intervals)),
            "n_rows_in_source": int(len(df)),
            "n_distinct_code_universe_pairs": int(
                intervals.groupby(["universe", "code"]).ngroups
            ),
        },
        "qlib_alignment": {
            "note": (
                "只做**约定层**对齐,不做逐 code 对账(那是卡 1.2)。"
                "qlib 是**贴片式**:end_k + 1 自然日 == start_{k+1},相邻段不合并 ——"
                "所以 qlib 的行数不是段数,比对前必须先合并相邻段。"
                "右端夹到 release 日期(2026-08-26)而不是 NULL;"
                "代码是 SH600000 前缀式、日期是 ISO,两处都要转换。"
            ),
            "expected_direction_for_card_1_2": [
                "**先把两源都投影到交易日网格再比**:源B 的端点是**自然日**"
                "(``end_k = start_{k+1} - 1 天``),大量落在周末/节假日;"
                "源A 的 out_date 取的是前一个**交易日**。不取整直接比,"
                "会先收到一批 −2 自然日的假警报(实测 245 条,全部恰好 −2,"
                "且 qlib 的 end **无一是交易日**)。",
                "in_date_A >= start_B(源A 最晚要等到月末才看见入场);"
                "实测入场滞后最小 21 天、无负值,这一侧没有取整问题。",
                "out_date_A >= prev_trading_day(end_B + 1 天)"
                "(等价说法:先把 B 的自然日端点取整到交易日网格,再比)。",
                "两侧偏差都应 <= 一个快照间隔(约一个月;交易日口径见 cfg.BOUNDARY_TOL_TD)。",
                "**取整之后**方向仍然反了的,才是真矛盾,值得逐条查。",
            ],
            "measured_out_date_lag_natural_days": {
                "note": (
                    "``out_date_A − end_B``,自然日,只算非右截断段。−2 的那些"
                    "**不是矛盾**,是自然日/交易日取整伪影(周末)。"
                ),
                "csi300": {"-2": 35, "0": 505, "2": 2, "25": 43, "27": 39, "28": 23, "29": 36, "30": 40},
                "csi500": {"-2": 101, "0": 1411, "21": 1, "25": 101, "28": 51, "29": 51, "30": 50},
                "csi1000": {"-2": 109, "0": 2240},
                "n_negative_where_qlib_end_is_a_trading_day": {
                    "csi300": 0,
                    "csi500": 0,
                    "csi1000": 0,
                },
            },
            "measured": _qlib_alignment(),
        },
    }


# --------------------------------------------------------------------------
# 落盘
# --------------------------------------------------------------------------


def _write_private(path: Path, write: Any) -> dict[str, Any]:
    """原子 + 0600 写文件:先写同目录临时文件、chmod、再 `os.replace`。

    umask 是 002,裸写会落成组可读 —— 答案隔离靠的就是权限位(红线 5),
    所以每个产物文件都必须显式 chmod 600,不能指望 umask。
    """
    cfg.create_dir(path.parent)
    tmp = path.with_name(path.name + ".tmp")
    try:
        write(tmp)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        if tmp.exists():  # pragma: no cover - 只有写失败才走到
            tmp.unlink()
    data = path.read_bytes()
    return {
        "path": str(path),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "mode": oct(path.stat().st_mode & 0o777),
    }


def parquet_metadata(dates_by_universe: dict[str, list[str]]) -> dict[bytes, bytes]:
    """写进 parquet **schema metadata** 的口径指纹(对抗审查 D3)。

    为什么非写不可:摘要 JSON 里的 ``date_coverage`` 只在 JSON 里,
    parquet 单独流转(拷给别人、进另一个仓库)时**带不走**。
    于是拿到 parquet 的人不知道它的有效区间是 ``[首期, 20260731]``,
    按 ``in_date <= D <= out_date`` 查 2027 年会安静地拿到 2026-07-31 那份名单。

    键都是 ``bytes``,pyarrow 的 kv metadata 只收 bytes。
    """
    firsts = {u: (ds[0] if ds else None) for u, ds in dates_by_universe.items()}
    meta = {
        "genebench_card": "1.1-sourceA",
        "generator": "snapshots/universe_index_weight.py",
        "source_view": SOURCE_VIEW,
        "freeze_line": lake.FREEZE_DATE_COMPACT,
        "valid_from": min(d for d in firsts.values() if d),
        "valid_to": lake.FREEZE_DATE_COMPACT,
        "valid_from_by_universe": json.dumps(firsts, ensure_ascii=False),
        "date_format": "YYYYMMDD 字符串",
        "interval_closure": "闭区间 [in_date, out_date];out_date IS NULL = 右截断(区间开口)",
        "safe_reader": "snapshots.universe_index_weight.universe_at(universe, date)",
        "warning": (
            "直接按 in_date <= D <= out_date 过滤**不会**对越界的 D 报错:"
            "D > valid_to 返回末期名单,D < valid_from 返回空集。用 safe_reader。"
        ),
    }
    return {k.encode(): str(v).encode() for k, v in meta.items()}


def read_intervals(path: Path | None = None) -> tuple[pd.DataFrame, dict[str, str]]:
    """读回产物 + 它的 metadata。``(frame, meta)``,meta 已解成 ``str -> str``。"""
    import pyarrow.parquet as _pq

    target = path or cfg.UNIVERSE_INTERVALS_PARQUET
    raw = _pq.ParquetFile(target).schema_arrow.metadata or {}
    meta = {
        k.decode(): v.decode()
        for k, v in raw.items()
        if k != b"pandas"  # pandas 自己塞的那一大坨不是我们的口径
    }
    return pd.read_parquet(target), meta


def universe_at(
    universe: str,
    date: str,
    *,
    frame: pd.DataFrame | None = None,
    meta: dict[str, str] | None = None,
) -> list[str]:
    """**唯一安全的读法**:取 `universe` 在交易日 `date`(``YYYYMMDD``)的成员。

    对抗审查 D3 的修法。裸写 ``in_date <= D & (out_date.isna() | D <= out_date)``
    在两个方向上都**静默**:

        20090105 → 0 只(首期之前,空集,不报错)
        20260731 → 300 只
        20270101 → 300 只(冻结线之外!安静地给你末期名单)
        29991231 → 300 只

    本函数对越界的 `date` 抛 `ValueError`,而不是返回空集或满额。

    Args:
        universe: `cfg.UNIVERSES` 之一。
        date: ``YYYYMMDD``。
        frame: 已读好的区间表;不给就现读产物。
        meta: 已读好的 metadata;不给就现读。

    Returns:
        升序去重的成员代码列表。

    Raises:
        ValueError: `universe` 不认识,或 `date` 落在该宇宙的有效区间之外。
    """
    if universe not in cfg.UNIVERSES:
        raise ValueError(f"不认识的宇宙 {universe!r};有的是 {list(cfg.UNIVERSES)}")
    if not (isinstance(date, str) and len(date) == 8 and date.isdigit()):
        raise ValueError(f"date 必须是 8 位 YYYYMMDD 字符串,拿到 {date!r}")
    if frame is None or meta is None:
        frame, meta = read_intervals()
    valid_from = json.loads(meta["valid_from_by_universe"])[universe]
    valid_to = meta["valid_to"]
    if not (valid_from <= date <= valid_to):
        raise ValueError(
            f"{universe} 的有效区间是 [{valid_from}, {valid_to}],查询日 {date} 在区间外。"
            f" 越界查询在本表上**不会**自然报错(D > valid_to 返回末期名单、"
            f"D < valid_from 返回空集),所以这里显式拦下。"
        )
    sel = frame[frame["universe"] == universe]
    hit = sel[
        (sel["in_date"] <= date)
        & (sel["out_date"].isna() | (sel["out_date"] >= date))
    ]
    return sorted(set(hit["code"]))


def write_outputs(
    intervals: pd.DataFrame,
    summary: dict[str, Any],
    dates_by_universe: dict[str, list[str]] | None = None,
) -> dict[str, dict[str, Any]]:
    """写 parquet(落 `$GENEBENCH_ROOT`)+ 摘要 JSON(落 `ops/`)。

    parquet 先写、把它的 sha256/大小塞回 summary,再写 JSON ——
    这样 JSON 里记的指纹永远指向同一次产出。
    """
    coverage = dates_by_universe or {
        uni: summary["universes"][uni]["date_coverage"]["snapshots"]
        for uni in cfg.UNIVERSES
    }
    kv = parquet_metadata(coverage)

    def _write_parquet(p: Path) -> None:
        import pyarrow as _pa
        import pyarrow.parquet as _pq

        table = _pa.Table.from_pandas(intervals, preserve_index=False)
        merged = dict(table.schema.metadata or {})
        merged.update(kv)
        _pq.write_table(table.replace_schema_metadata(merged), p)

    art = _write_private(cfg.UNIVERSE_INTERVALS_PARQUET, _write_parquet)
    art["schema_metadata"] = {k.decode(): v.decode() for k, v in kv.items()}
    art["rows"] = int(len(intervals))
    art["columns"] = list(INTERVAL_COLUMNS)
    summary["artifact"] = art
    js = _write_private(
        cfg.UNIVERSE_SOURCE_A_JSON,
        lambda p: p.write_text(
            json.dumps(summary, ensure_ascii=False, indent=1, default=str) + "\n",
            encoding="utf-8",
        ),
    )
    return {"parquet": art, "summary_json": js}


def build() -> tuple[pd.DataFrame, dict[str, Any]]:
    """跑完整条链路:读湖 → 建区间 → 出摘要。**不落盘**,便于测试直接调。"""
    lake.raise_open_file_limit()
    with lake.catalog() as con:
        date_types = assert_compact_date_convention(conn=con)
        df = load_snapshots(conn=con)
        dates_by_universe = snapshot_dates_by_universe(df)
        off_size = off_size_periods(df)
        off_size_diag = diagnose_off_size(df, dates_by_universe, off_size, conn=con)
        all_dates = sorted({d for ds in dates_by_universe.values() for d in ds})
        prev_td = previous_trading_day_map(all_dates, conn=con)
    intervals = build_intervals(df, dates_by_universe, prev_td, off_size, off_size_diag)
    summary = summarize(
        df, intervals, dates_by_universe, off_size, off_size_diag, date_types
    )
    return intervals, summary


def main(argv: list[str] | None = None) -> int:
    """CLI 入口。``--dry-run`` 只算不写,用来在改约定后先看数再决定要不要落盘。

    注意 umask **不在这里**收紧 —— 那太晚了,见文件顶部 `_PREVIOUS_UMASK` 那段。
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dry-run", action="store_true", help="只计算并打印摘要,不写任何文件"
    )
    args = parser.parse_args(argv)

    intervals, summary = build()

    for uni in cfg.UNIVERSES:
        u = summary["universes"][uni]
        print(
            f"{uni:8s} 区间 {u['n_intervals']:6d} | 去重 code {u['n_distinct_codes']:5d} "
            f"| 左截断 {u['n_left_censored']:4d} | 右截断 {u['n_right_censored']:5d} "
            f"| 每期恒 {u['nominal_size']}: "
            f"{'是' if u['size_is_constant'] else '否(' + str(len(u['off_size_periods'])) + ' 期不足额)'}"
        )
    for uni in cfg.UNIVERSES:
        t = summary["turnover"][uni]
        print(
            f"{uni:8s} 换手(调入) min={t['adds']['min']} "
            f"median={t['adds']['median']} max={t['adds']['max']} "
            f"| 调出 min={t['drops']['min']} median={t['drops']['median']} "
            f"max={t['drops']['max']}"
        )

    if args.dry_run:
        print("--dry-run:未写任何文件")
        return 0

    written = write_outputs(intervals, summary)
    for kind, info in written.items():
        print(f"{kind:13s} -> {info['path']} ({info['bytes']} B, mode {info['mode']})")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
