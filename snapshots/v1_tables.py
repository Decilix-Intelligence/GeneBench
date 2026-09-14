"""v1 依赖表清单 —— 主实验一充分集,全日频,冻结线 `cfg.FREEZE_DATE`。

这是"v1 到底吃湖里哪几张表"的**唯一登记处**。卡 1.4(快照版本化)按这张清单
做 parquet 快照,卡 1.3(as-of 网关)按这张清单决定端点能答什么,
卡 0.2 的 `ops/lake_baseline.json` 按这张清单逐表体检。
往里加表 = 往 v1 数据面加表,必须同时写清"**哪张卡要用它**"。

清单之外的表默认**不进 v1**。有几张容易被误加的,连同不进的理由,
一并登记在 `EXCLUDED` 里 —— 不写下来的话,下一个人只会再问一遍。

这里也是 **`date_column` 与 `update_cadence` 的唯一登记处**
--------------------------------------------------------
两件事刻意**不**交给 `coverage-audit`:

1. **哪一列是时间轴**(`date_column`)。审计把 `st_history` 记成 `date_column=null`,
   而它表内 `pub_date` / `imp_date` 两列全表非空 —— 于是同一张表既被判成
   "data_time 分区(有时间语义)"又被判成"没有日期列",自相矛盾。
   而且"有几个日期列"和"哪个日期列是 PIT 可见时间轴"是两个问题:
   `dividend` 有 5 个日期列,其中 `ex_date` 是**除权日**(未来信息),
   选错就前视。这种判断必须写下来并说明理由,不能让审计替我们做。
2. **这张表多久该有一次新数据**(`update_cadence`)。冻结线只回答"历史够不够",
   不回答"这张表还活着吗"。实测有 6 张表 max_date 已经越过冻结线(于是一片绿)
   却早已停更 —— 详见各表 notes 里的 ⛔ 标记与 `ops/lake_baseline.json`
   的 `summary.stalled_tables`。
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "TableSpec",
    "V1_TABLES",
    "V1_TABLE_NAMES",
    "EXCLUDED",
    "DERIVED_VIEWS",
    "UPDATE_CADENCES",
    "CADENCE_TOLERANCE_DAYS",
    "stale_after_days",
    "by_card",
    "spec",
]


#: 合法的更新节奏取值(`TableSpec.update_cadence`)。
UPDATE_CADENCES: tuple[str, ...] = (
    "trading_day",  # 每个交易日都该有新数据(或新快照)
    "event",        # 有事件才有新行(公告流/分红/改名),但 ETL 本身天天在跑
    "month_end",    # 月末快照,一个月一期
    "irregular",    # 区间表,没有单一"新鲜度日期",判不了
)

#: **"多久没有新数据就算这张表停更了"**(日历天)。
#:
#: 为什么用日历天而不是交易日:交易日口径要反查 `trade_cal`,而 `ann_date`
#: 这类公告日期本来就可能落在周末(实测 `income_vip` 的 max ann_date = 20260829
#: 是周六),换算成交易日反而没有定义。日历天简单、无歧义,代价是容忍度要放宽到
#: 能吃下最长的假期。
#:
#: 容忍度怎么定的:
#:
#: * `trading_day` = **12 天**。A 股最长连休(春节/国庆)约 9-10 个日历天,
#:   12 天保证"放假"不会被误判成"停更";而实测真停更的表都落在 25 天以上,
#:   中间有十几天的安全间隔,不会来回翻。
#: * `event` = **14 天**。事件流本身可能几天没有新行,但 ETL 天天在跑,
#:   两周一条没有已经不正常了。
#: * `month_end` = **45 天**。一个月末周期最长 31 天,再给 14 天宽限
#:   (月末快照落地会晚几天)。
#: * `irregular` = `None`,**明确判不了**,不许粉饰成"没停更"。
CADENCE_TOLERANCE_DAYS: dict[str, int | None] = {
    "trading_day": 12,
    "event": 14,
    "month_end": 45,
    "irregular": None,
}


def stale_after_days(cadence: str) -> int | None:
    """这个节奏下,滞后多少个日历天就算停更;`irregular` 返回 `None`(判不了)。"""
    if cadence not in CADENCE_TOLERANCE_DAYS:
        raise KeyError(f"未知的更新节奏 {cadence!r},合法取值:{UPDATE_CADENCES}")
    return CADENCE_TOLERANCE_DAYS[cadence]


@dataclass(frozen=True)
class TableSpec:
    """一张 v1 依赖表的登记项。

    Attributes:
        dataset: 湖里的数据集名 = catalog 视图名 = `$GOLD/<dataset>/`。
        role: 它在 v1 里扮演什么(一句话)。
        used_by_cards: **哪张卡要用它**。实施稿的卡编号,如 ``"1.2"``。
        why: 为什么这张卡非它不可(具体到字段/口径,不要写"需要数据")。
        notes: 已知陷阱与口径提醒,会原样进 `ops/lake_baseline.json` 的 notes。
        date_column: **这张表的时间轴是哪一列**,无则 `None`。
            这里是唯一登记处 —— 刻意**不**信 `coverage-audit` 的 `date_column`
            字段(卡 0.2 补救 D5:审计说 `st_history` 没有日期列,而它表内
            实实在在有 `pub_date` / `imp_date`,于是同一张表被判成
            "有时间语义的 data_time 分区"却又"没有日期列",自相矛盾)。
            审计值降级成 `audit_date_column`,只用来对账、不再当判据。
        date_column_why: 为什么选这一列(多个候选时必须说清),或为什么判定无日期列。
        update_cadence: **期望**的更新节奏,见 `UPDATE_CADENCES`。
            这是"这张表还活着吗"的判据基准(卡 0.2 补救 D3)。
            注意它是**据同类表实测节奏推断的期望**,不是 ETL 侧的声明 ——
            湖不是我们的资产,拿不到它的排班表。
    """

    dataset: str
    role: str
    used_by_cards: tuple[str, ...]
    why: str
    notes: str = ""
    aliases: tuple[str, ...] = field(default_factory=tuple)
    date_column: str | None = None
    date_column_why: str = ""
    update_cadence: str = "trading_day"


# --------------------------------------------------------------------------
# 清单本体
# --------------------------------------------------------------------------

V1_TABLES: tuple[TableSpec, ...] = (
    # ---------------- 行情量价 ----------------
    TableSpec(
        dataset="daily",
        role="日线量价(未复权)——v1 一切价格的底座",
        used_by_cards=("1.2", "1.3", "1.4", "2.1", "3.2", "5.2"),
        why=(
            "卡 1.2 用它的**缺行**识别停牌;卡 1.3 的 /bars 端点直接答它;"
            "卡 1.4 快照它;卡 2.1 全部量价因子的输入;卡 5.2 回测取价。"
        ),
        notes=(
            "停牌票在这里是**缺行**不是显式标记,必须 join suspend_d + trade_cal 才能区分"
            "'停牌'与'尚未上市/已退市';触板判定也只能用它的 close/high/low 去比 stk_limit。"
        ),
        date_column="trade_date",
        date_column_why="日分区键与表内时间轴同名同义,唯一候选。",
        update_cadence="trading_day",
    ),
    TableSpec(
        dataset="adj_factor",
        role="复权因子 —— v1 **唯一**复权口径",
        used_by_cards=("1.3", "1.4", "2.1", "5.1", "5.2"),
        why=(
            "卡 1.3 的 /adj 端点;卡 2.1 因子计算前的价格复权;"
            "卡 5.1 复权指纹探针拿它当基准答案;卡 5.2 回测净值。"
        ),
        notes=(
            "实施稿定死:v1 数据面统一走 adj_factor,stk_factor_pro 的 bfq/hfq/qfq "
            "三价口径**不进网关**(2026-08 起两套口径不同步)。"
        ),
        date_column="trade_date",
        date_column_why="同 daily。",
        update_cadence="trading_day",
    ),
    TableSpec(
        dataset="daily_basic",
        role="日频估值/换手/市值衍生量",
        used_by_cards=("1.3", "1.4", "2.1", "5.2"),
        why=(
            "卡 1.3 的 /bars 扩展字段;卡 2.1 的 pe/pb/ps/turnover_rate/"
            "total_mv/circ_mv 类因子;卡 5.2 市值中性化与分组。"
        ),
        notes="与 daily 同为 trade_date 日分区,行数略少于 daily(部分票缺估值)。",
        date_column="trade_date",
        date_column_why="同 daily。",
        update_cadence="trading_day",
    ),
    TableSpec(
        dataset="stk_limit",
        role="涨跌停价",
        used_by_cards=("1.2", "1.3", "1.4", "3.2", "5.2"),
        why=(
            "卡 1.2 的触板判定;卡 1.3 的 /limits 端点;卡 3.2 的 S6/S8 "
            "约束与撮合;卡 5.2 可交易性过滤。"
        ),
        notes=(
            "**pre_close 全为 NULL**(实测),触板只能用 daily.close/high/low 对 "
            "up_limit/down_limit 比价,不要指望这张表自带前收。"
        ),
        date_column="trade_date",
        date_column_why="同 daily。",
        update_cadence="trading_day",
    ),
    TableSpec(
        dataset="suspend_d",
        role="停复牌事件(S=停牌 / R=复牌)",
        used_by_cards=("1.2", "1.3", "1.4", "3.2", "5.1"),
        why=(
            "卡 1.2 三方 join 的第二源;卡 1.3 的 /tradability;"
            "卡 3.2 的 S2 清洗陷阱题材料;卡 5.1 欠定语义探针。"
        ),
        notes="suspend_type 是 S/R 事件流,不是逐日状态,要自己前向填充成区间。",
        date_column="trade_date",
        date_column_why="同 daily(事件发生日 = 交易日)。",
        update_cadence="trading_day",
    ),
    # ---------------- 日历 ----------------
    TableSpec(
        dataset="trade_cal",
        role="交易日历",
        used_by_cards=("1.2", "1.3", "1.4", "2.2", "3.2", "5.1"),
        why=(
            "卡 1.2 区分'非交易日'与'停牌';卡 1.3 的 /calendar;"
            "卡 2.2 回测对齐;卡 5.1 日历探针的判据。"
        ),
        notes=(
            "湖里**只有 SSE 一个交易所**(6574 行,20090101→20261231,"
            "**含未来日历**——越过冻结线的日期天然存在,网关必须自己截断);"
            "gold 只有 1 个 snapshot_date 分区,不是日分区。"
            "⛔ **停更**:那唯一一个快照是 snapshot_date=2026-08-05,**此后从未刷新**。"
            "它照样'过冻结线'(cal_date 一路到 20261231),但那是**快照里预写的未来日历**,"
            "不是这张表还活着的证据 —— 判它新鲜度只能看**快照日**,不能看 cal_date。"
        ),
        date_column="cal_date",
        date_column_why=(
            "cal_date 是日历本身的时间轴;pretrade_date 是派生的前一交易日,不独立。"
            "⚠️ 但 cal_date **不能当新鲜度**:它是预写到 20261231 的未来日历,"
            "这张表的新鲜度是 snapshot_date(capture_time 语义,见 H4)。"
        ),
        update_cadence="trading_day",
    ),
    # ---------------- 宇宙 ----------------
    TableSpec(
        dataset="index_weight",
        role="指数成分权重月末快照 —— PIT 宇宙的**主源**",
        used_by_cards=("1.1", "1.3", "1.4", "3.2"),
        why="卡 1.1 用相邻月末 diff 推 csi300/500/1000 的成分区间(方案甲)。",
        notes=(
            "只有 000300.SH / 000905.SH / 000852.SH 三个指数,**月末快照**"
            "(2026 年为 0130/0227/0331/0430/0529/0630/0731,每期恰好 300/500/1000 条),"
            "**天然冻在 20260731**;月内调整会被抹平,这条局限要写进数据卡。"
            "注意它**不是停更** —— 月末节奏下 20260731 就是当期最新,"
            "所以 update_cadence 登记为 month_end(容忍 45 天),别拿日频尺子量它。"
        ),
        date_column="trade_date",
        date_column_why="月末快照的生效日,唯一时间轴。",
        update_cadence="month_end",
    ),
    TableSpec(
        dataset="stock_basic",
        role="上市状态多快照表(list_date / delist_date / list_status)",
        used_by_cards=("1.1", "1.3", "1.4", "5.1"),
        why=(
            "卡 1.1 的兜底源(退市/未上市回溯);卡 1.3 封装 snapshot 语义;"
            "卡 5.1 PIT 宇宙探针的对照。"
        ),
        notes=(
            "**多快照表**,分区 snapshot_date=YYYY-MM-DD,**只有 2026-08-05 起的十几个快照**"
            "(全部晚于冻结线)。2026-08-05 之前的状态**只能靠 list_date/delist_date 字段回溯,"
            "不能靠快照** —— 网关必须把这条规则写死,否则会漏未来信息。"
            "✅ 快照**每个交易日都在刷新**(与 trade_cal / index_basic 相反),是三张 "
            "capture_time 表里唯一还活着的。"
        ),
        date_column=None,
        date_column_why=(
            "表内 list_date / delist_date 是**上市/退市事件日**,不是这张表的时间轴 —— "
            "拿 max(list_date) 当新鲜度会把'最近有新股上市'误读成'快照是新的'。"
            "这张表的时间轴在**分区**上(snapshot_date),按 capture_time 处理。"
        ),
        update_cadence="trading_day",
    ),
    TableSpec(
        dataset="namechange",
        role="曾用名变更(ST 改名的原始事件)",
        used_by_cards=("1.1", "1.3", "5.1"),
        why="卡 1.1 用它还原任一时点的证券简称,判 ST/*ST 前缀;卡 5.1 PIT 探针交叉核对。",
        notes=(
            "ts_code 分区(5875 个),**不是时间分区** —— 它的'最新分区'是字典序最大的代码,"
            "与新鲜度无关,判新鲜度看视图的 ann_date。catalog 里另有派生视图 "
            "stock_name_pit 已把它与 stock_basic 拼成区间,卡 1.1 可直接对账。"
            "⛔ **停更**:max(ann_date) 停在 2026-08-06,此后再无新行。"
        ),
        date_column="ann_date",
        date_column_why=(
            "改名公告日 = 这条记录**何时可见**,是 PIT 正确的那一列;"
            "start_date/end_date 是改名生效区间,end_date 还有 4 成为空,不能当时间轴。"
        ),
        update_cadence="event",
    ),
    TableSpec(
        dataset="stock_st",
        role="日频 ST / *ST 标记",
        used_by_cards=("1.1", "1.2", "1.3", "3.2"),
        why="卡 1.1 的 ST 过滤;卡 1.2 状态字段;卡 3.2 的 S6 约束集(通常剔除 ST)。",
        notes=(
            "gold 是 trade_month=YYYYMM 月分区(不是日分区),起点 201608,早于此无覆盖。"
            "**月分区但日频内容** —— 分区粒度别当成更新粒度。"
        ),
        date_column="trade_date",
        date_column_why="逐日 ST 标记的所属交易日,唯一时间轴(月分区只是存储粒度)。",
        update_cadence="trading_day",
    ),
    TableSpec(
        dataset="st_history",
        role="ST 事件历史(戴帽/摘帽的公告级记录)",
        used_by_cards=("1.1",),
        why="卡 1.1 与 stock_st / namechange 三方交叉核对 ST 区间,给分歧清单当第三票。",
        notes=(
            "published_month 月分区(起点 202204),量很小(千级),只当交叉核对源,不当主源。"
            "⚠️ `coverage-audit` 把它记成 **date_column=null**,但表内 pub_date / imp_date "
            "两列**全表非空**(实测 1227/1227)。审计那个 null 与它 data_time 的分区语义"
            "直接矛盾(卡 0.2 补救 D5),此处以**表内实测**为准。"
        ),
        date_column="pub_date",
        date_column_why=(
            "两个候选:pub_date(公告发布日)与 imp_date(实施日)。取 **pub_date** —— "
            "实测 max(imp_date)=20260831 晚于 max(pub_date)=20260828,"
            "即实施日会**晚于**公告日,拿它当可见时间轴会漏未来信息。PIT 一律取可见日。"
        ),
        update_cadence="event",
    ),
    TableSpec(
        dataset="index_member_all",
        role="申万行业成分区间(l1/l2/l3 + in_date/out_date)",
        used_by_cards=("1.1", "2.1", "3.2"),
        why=(
            "卡 1.1 给每只票打 PIT 行业标签;卡 2.1 行业中性化因子必须的分组;"
            "卡 3.2 的 S5/S6 行业约束题面。"
        ),
        notes=(
            "l3_code=8xxxxx.SI 分区(338 个),**不是时间分区**;本身是区间表"
            "(in_date/out_date),没有单一日期列,新鲜度看不出来,要看字段。"
            "登记为 update_cadence=irregular:停没停更**判不了**,基线里 stalled=null,"
            "**不许**因为判不了就默认它是活的。"
        ),
        date_column=None,
        date_column_why=(
            "区间表:in_date/out_date 是成分**进出**行业的两端,不是记录的可见时间轴。"
            "拿 max(in_date) 当新鲜度会把'最近有票换行业'误读成'表在更新'。"
        ),
        update_cadence="irregular",
    ),
    # ---------------- 基本面三大报表 ----------------
    TableSpec(
        dataset="income",
        role="利润表(全量)",
        used_by_cards=("1.3", "1.4", "2.1", "3.2", "5.1"),
        why=(
            "卡 1.3 的 /fundamentals(严格 PIT);卡 2.1 的盈利类因子;"
            "卡 3.2 的 S3/S4 题面;卡 5.1 前视探针的正例来源。"
        ),
        notes=(
            "有 ann_date + f_ann_date + end_date + end_type + update_flag,"
            "**可严格 PIT**(用 f_ann_date 而不是 ann_date);ts_code 分区,非时间分区。"
            "⛔ **停更**:max(ann_date) 停在 2026-08-04,而孪生表 income_vip 已到 08-29,"
            "**两者差 20 天以上**。取并集补历史时别把 income 当最新口径。"
        ),
        date_column="ann_date",
        date_column_why=(
            "与 audit / 其余报表口径一致,便于跨表对账。"
            "⚠️ 取数做严格 PIT 时用 **f_ann_date**(实际公告日,实测最早到 20070112,"
            "早于 ann_date 的 20080102);此处 date_column 只用于体检新鲜度,不是取数口径。"
        ),
        update_cadence="event",
    ),
    TableSpec(
        dataset="income_vip",
        role="利润表(vip 接口口径,end_date 分区)",
        used_by_cards=("1.3", "1.4", "2.1"),
        why="与 income 同源不同抓取口径,卡 1.3/1.4 需要二者取并集补全历史,卡 2.1 交叉校验。",
        notes=(
            "end_date=YYYY-MM-DD 季度分区(70 个),覆盖 2009Q1→2026Q2;"
            "与 income 行数不同,不要假设互相包含。"
            "✅ 仍在更新(与已停更的 income 相反),是三大报表里的活口径。"
        ),
        date_column="ann_date",
        date_column_why="与 income 同口径,便于孪生表逐日对账。",
        update_cadence="event",
    ),
    TableSpec(
        dataset="balancesheet",
        role="资产负债表(全量)",
        used_by_cards=("1.3", "1.4", "2.1", "3.2", "5.1"),
        why="同 income:估值/杠杆/资产类因子与 PIT 探针的输入。",
        notes=(
            "156 列;ts_code 分区,非时间分区。"
            "⛔ **停更**:max(ann_date) 停在 2026-08-04,孪生表 balancesheet_vip 已到 08-28。"
        ),
        date_column="ann_date",
        date_column_why="同 income。",
        update_cadence="event",
    ),
    TableSpec(
        dataset="balancesheet_vip",
        role="资产负债表(vip 口径)",
        used_by_cards=("1.3", "1.4", "2.1"),
        why="与 balancesheet 取并集补历史 + 交叉校验。",
        notes="157 列(比 balancesheet 多一列),end_date 季度分区。✅ 仍在更新。",
        date_column="ann_date",
        date_column_why="同 income。",
        update_cadence="event",
    ),
    TableSpec(
        dataset="cashflow",
        role="现金流量表(全量)",
        used_by_cards=("1.3", "1.4", "2.1", "3.2", "5.1"),
        why="同 income:现金流类因子与 PIT 探针的输入。",
        notes=(
            "101 列;ts_code 分区,非时间分区。"
            "⛔ **停更**:max(ann_date) 停在 2026-08-04,孪生表 cashflow_vip 已到 08-28。"
        ),
        date_column="ann_date",
        date_column_why="同 income。",
        update_cadence="event",
    ),
    TableSpec(
        dataset="cashflow_vip",
        role="现金流量表(vip 口径)",
        used_by_cards=("1.3", "1.4", "2.1"),
        why="与 cashflow 取并集补历史 + 交叉校验。",
        notes="102 列;end_date 季度分区。✅ 仍在更新。",
        date_column="ann_date",
        date_column_why="同 income。",
        update_cadence="event",
    ),
    # ---------------- 指数 ----------------
    TableSpec(
        dataset="index_daily",
        role="指数日线(基准收益)",
        used_by_cards=("2.2", "3.2", "5.2"),
        why=(
            "卡 2.2 的 ε 标定需要基准;卡 3.2 的 S7 回测题面声明基准;"
            "卡 5.2 结算超额收益/IR 必须的对照。"
        ),
        notes="与 daily 同为 trade_date 日分区;只覆盖少数几个指数,取用前先确认基准代码在表里。",
        date_column="trade_date",
        date_column_why="同 daily。",
        update_cadence="trading_day",
    ),
    TableSpec(
        dataset="index_basic",
        role="指数元数据(名称/基日/基点)",
        used_by_cards=("1.1", "1.3"),
        why="卡 1.1/1.3 把 index_weight 与 index_daily 的指数代码解释成人读得懂的名字,并校验基准。",
        notes=(
            "**只有 8 行**,snapshot_date 分区且只有 2 个快照;无日期列。当元数据用,不当行情用。"
            "⛔ **停更**:两个快照是 2026-08-05 / 2026-08-06,此后再没抄过。"
            "同为 capture_time 的 stock_basic 每个交易日都在刷新 —— 这张没有,是真停了。"
        ),
        date_column=None,
        date_column_why=(
            "base_date(指数基日,max 20100531)/ list_date(发布日)是**指数自身的属性**,"
            "与'这张表抄到哪天'无关;exp_date 8 行全空。新鲜度只能看 snapshot_date。"
        ),
        update_cadence="trading_day",
    ),
    # ---------------- 事件 / 交叉核对 ----------------
    TableSpec(
        dataset="dividend",
        role="分红送转事件(拆分/送股的原始记录)",
        used_by_cards=("5.1", "2.1"),
        why=(
            "卡 5.1 明确要求'用湖内**已知拆分事件**构造复权指纹样本' —— 样本就来自这张表;"
            "卡 2.1 校验 adj_factor 的跳变点。"
        ),
        notes=(
            "ts_code 分区,非时间分区;ann_date 最早到 1991,注意早期数据质量。"
            "⛔ **停更**:max(ann_date) 停在 2026-08-01,是 v1 清单里滞后最久的一张。"
            "⚠️ ann_date 还有约 6000 行为空(171879/177858 非空),"
            "卡 5.1 用它构造拆分事件样本时要先过滤。"
        ),
        date_column="ann_date",
        date_column_why=(
            "预案公告日 = 事件**何时可见**。record_date/ex_date/pay_date/imp_ann_date "
            "都只有三成填充率(57k/177k),且 ex_date 是**除权日**属于未来信息,"
            "拿它当时间轴会前视。"
        ),
        update_cadence="event",
    ),
    TableSpec(
        dataset="limit_list_d",
        role="涨跌停/炸板榜(触板结果的第三方口径)",
        used_by_cards=("1.2",),
        why="卡 1.2 验收要求人工核对触板判定 —— 这张表是湖内可用的独立对照口径,省掉一半人工。",
        notes=(
            "**只覆盖 20200102 起**,冻结线内可用但历史不全;只当交叉核对源,"
            "触板主判据仍是 daily 比价 stk_limit。"
            "⛔ **停更**:gold 分区**硬停在 trade_date=2026-08-05**,而 daily 在其后"
            "还有 17 个交易日分区(→2026-08-28)。它照样'过冻结线'(20260805 > 20260731),"
            "所以在只看冻结线的基线里是一片绿 —— 卡 1.3 的网关**不能**拿它判新鲜度。"
            "对 v1 的 ≤2026-07-31 窗口不构成数据缺口。"
        ),
        date_column="trade_date",
        date_column_why="同 daily。",
        update_cadence="trading_day",
    ),
)

#: 清单里的数据集名(保持登记顺序)。
V1_TABLE_NAMES: tuple[str, ...] = tuple(t.dataset for t in V1_TABLES)


# --------------------------------------------------------------------------
# 明确**不进** v1 的表(写下来,免得下一个人再问一遍)
# --------------------------------------------------------------------------

EXCLUDED: tuple[dict[str, str], ...] = (
    {
        "dataset": "stk_factor_pro",
        "reason": (
            "带 bfq/hfq/qfq 三价口径。实施稿卡 1.3 定死:v1 数据面统一走 adj_factor,"
            "三价口径不进网关 —— 2026-08 起两套口径不同步,放进来等于给被测 agent "
            "两个互相矛盾的复权答案。"
        ),
        "revisit": "v1.1 若要做口径一致性题材,再单独评估。",
    },
    {
        "dataset": "fina_indicator",
        "reason": "**只有 ann_date,无 f_ann_date**,做不了严格 PIT;放进网关会直接漏未来信息。",
        "revisit": "v1.1 定降级规则(如统一延后 N 日可见)后再进。",
    },
    {
        "dataset": "fina_indicator_vip",
        "reason": "同 fina_indicator,缺 f_ann_date。",
        "revisit": "同上。",
    },
    {
        "dataset": "minute_1m / index_minute_1m / cn_minute_bar",
        "reason": "v1 **全日频**(实施稿 D3)。分钟线还卡在 NFS 桥(W1),v1 不需要。",
        "revisit": "Live 赛道。",
    },
    {
        "dataset": "moneyflow / margin / hk_hold 等另类数据",
        "reason": "v1 主实验一充分集只覆盖量价+基本面+宇宙+日历,不扩面。",
        "revisit": "v1.1 扩量(卡 3.3)时按题材需要逐张登记。",
    },
)

#: catalog 里的**派生视图**(没有独立 gold 目录,是别的表拼出来的)。
#: 不当数据源登记,但卡 1.1 拿它对账很省事,所以记一笔。
DERIVED_VIEWS: tuple[dict[str, str], ...] = (
    {
        "view": "stock_name_pit",
        "built_from": "namechange UNION ALL stock_basic",
        "use": (
            "已经把证券简称拼成 (ts_code, name, start_date, end_date) 区间,"
            "end_date 缺失填 99991231。卡 1.1 判 ST 前缀可直接对账,不必自己拼。"
        ),
    },
    {
        "view": "limit_list_ths_enriched",
        "built_from": "limit_list_ths + 衍生字段",
        "use": "卡 1.2 触板核对的又一路第三方口径(同花顺),优先级低于 limit_list_d。",
    },
)


# --------------------------------------------------------------------------
# 查询辅助
# --------------------------------------------------------------------------


def spec(dataset: str) -> TableSpec:
    """按数据集名取登记项。

    Raises:
        KeyError: 不在 v1 清单里。
    """
    for table in V1_TABLES:
        if table.dataset == dataset:
            return table
    raise KeyError(f"{dataset!r} 不在 v1 依赖表清单里(见 snapshots/v1_tables.py)")


def by_card(card: str) -> tuple[TableSpec, ...]:
    """某张卡要用到的全部表。"""
    return tuple(t for t in V1_TABLES if card in t.used_by_cards)


if __name__ == "__main__":  # pragma: no cover - 手工自检
    print(f"v1 依赖表 {len(V1_TABLES)} 张:")
    for _t in V1_TABLES:
        print(
            f"  {_t.dataset:20s} date={str(_t.date_column or '-'):12s} "
            f"cadence={_t.update_cadence:12s}"
            f"(停更阈值 {stale_after_days(_t.update_cadence)} 天) "
            f"cards={','.join(_t.used_by_cards)}"
        )
    print(f"\n明确排除 {len(EXCLUDED)} 项,派生视图 {len(DERIVED_VIEWS)} 个。")
