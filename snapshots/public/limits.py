# -*- coding: utf-8 -*-
"""涨跌停价的推导（卡 2.5 §3 —— 本卡唯一的工程量）。

公开源只给 `preclose` 与 `isST`；涨跌停价要**自己推**。
推导规则按板块与生效日走，**四舍五入到分**。

**为什么单独成模块**：这段代码是公开通道与私有通道之间唯一一处
「我们自己算」的地方 —— 其余字段都是搬运。算错的表现是
**gold 照常算得出数**，只有拿私有 `stk_limit` 逐行核才看得见。

**取整口径实测（2026-09-05，私有湖 tushare 行）**：
`000001.SZ` pre_close 11.61 → up 12.77（11.61×1.1 = 12.771，**不是** 12.78），
down 10.45（10.449）。`000002.SZ` 3.33 → 3.66 / 3.00。
即**普通四舍五入到两位小数**，不是只入不舍。
Python 内置 `round()` 是**银行家舍入**（`round(2.675, 2) == 2.67`），
这里必须用 `Decimal` 的 `ROUND_HALF_UP`，否则每逢第三位恰为 5 就差一分。
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal

#: 创业板 / 科创板放宽到 20% 的生效日。**在这之前是 10%。**
#: 冻结线 2026-07-31 远在其后，但规则要写对 —— 重建历史时会用到。
CHINEXT_20PCT_FROM = "20200824"
STAR_20PCT_FROM = "20190722"        # 科创板开市即 20%

#: 新股上市后**无涨跌幅限制**的交易日数，**按板块不同**（2026-07 私有 oracle 逐日核）。
#: 沪深：`301583.SZ`(20260710 上市)、`688806.SH`(20260721)、`001248.SZ`(20260702)、
#: `688825.SH`(20260727) **全部前 5 个交易日无限制，第 6 日起正常**。
#: 北交所：`920222.BJ`(20260629 上市) 只有 **1 天**无限制，次日起就是 30%。
#: 写成一个全局的 5 会让北交所新股的头几天系统性判成「无限制」。
NO_LIMIT_TRADING_DAYS: dict[str, int] = {"main": 5, "chinext": 5, "star": 5, "bse": 1}

#: 私有 `stk_limit` 用**哨兵值**表示「无限制」，而且**三个交易所各不相同**（实测）：
#: 深 `(999999.999, 0.01)`、沪 `(99999.999, 0.01)`、北 `(99999.99, 0.0)`。
#: 本模块**不产出哨兵** —— `Limits.up is None` 就是「无限制」这个**语义**。
#: 哨兵只在与私有 oracle 对账时用得着，所以记在这里当**数据**，不当判据。
ORACLE_NO_LIMIT_SENTINEL = {"SH": (99999.999, 0.01), "SZ": (999999.999, 0.01),
                            "BJ": (99999.99, 0.0)}

#: **ST 的 5% 带在窗口内结束了。** 私有 `stk_limit` 上逐日数「隐含幅度落在 4%~6%」的票：
#: 20260615..20260703 每天 149–162 只，**20260706 起只剩 1 只**，此后到冻结线不变。
#: 那 1 只是 `600182.SH`「S佳通」—— **S 股（未完成股改）**，不是 ST。
#: 也就是说：**2026-07-06 起 ST/*ST 不再收窄到 5%**，回到所在板块的正常幅度。
#:
#: 卡 2.5 §3 的规则表原文写的是「ST / *ST 5%」且**没有生效日** ——
#: 照它推，冻结线前最后 18 个交易日会有约 150 只票逐日推错。
#: 私有通道读 `stk_limit` 不受影响，**只有公开通道（要自己推）会错**，
#: 而错的表现是涨跌停判定偏紧、gold 照常算得出数。这正是「拿 oracle 逐行核」要抓的东西。
ST_5PCT_LAST_DAY: str = "20260703"

#: **退市整理期的第一天无涨跌幅限制。**
#: 判据取 `namechange.change_reason == '退市整理期'` 那条记录的 `start_date`，
#: 与 `stk_limit` 相互独立 —— 不是拿 oracle 反推 oracle。
#:
#: **不能按名字判**：命名规则**两个交易所不一样** —— 深/北是后缀「退」
#: （`国华退`、`云创退`），**沪是前缀「退市」**（`退市华嵘`、`退市观典`）。
#: 第一版按后缀判，整个沪市漏掉；表现是半年 763,301 行里 8 行分歧散落各处、
#: 看起来像随机噪声，而不是「少了一条规则」。
#: 卡 2.5 §3 的规则表里**没有这一条**规则。
DELISTING_FIRST_DAY_FREE: bool = True

#: S 股（股权分置改革未完成，名字以 `S` 开头且不是 `ST`）的 5% 带**没有随之取消**。
#: 全市场当前只有 `600182.SH`。样本只有一只，**结论按「观测到的」写，不按「规则应该是」写**。
S_SHARE_PCT: float = 0.05


class LimitRuleError(ValueError):
    pass


@dataclass(frozen=True)
class Limits:
    up: float | None
    down: float | None
    pct: float | None
    board: str
    reason: str


def board_of(code: str) -> str:
    """从代码判板块。接受 `600000.SH` 与 `sh.600000` 两种写法。"""
    c = code.strip().lower()
    if "." in c:
        a, b = c.split(".", 1)
        num = a if a[:1].isdigit() else b
    else:
        num = c
    num = num.strip()
    if num.startswith(("688", "689")):
        return "star"
    # 创业板号段实际已扩到 301/302（`302132.SZ` 是 2026-07 在册的真代码）——
    # 只写 300 会把它判成 unknown，而 unknown 在这里是**抛异常**，不是默认值。
    if num.startswith(("300", "301", "302")):
        return "chinext"
    # 北交所：老号段 8xxxxx / 4xxxxx，2024 年起新增 **920xxx**
    # （2026-07 在册 332 个，占「认不出」的 99.7%）。
    if num.startswith(("8", "4", "920")):
        return "bse"
    if num.startswith(("60", "00")):
        return "main"
    return "unknown"


def limit_pct(code: str, trade_date: str, *, is_st: bool,
              is_s_share: bool = False) -> tuple[float | None, str, str]:
    """返回 `(幅度, 板块, 理由)`。幅度 `None` = 无涨跌幅限制。

    **ST 与板块的关系是这条规则里最容易写错的一处**：主板 ST 是 5%，
    而创业板 / 科创板的 ST **仍是 20%**（注册制板块不因 ST 收窄）。
    写成「ST 一律 5%」会在这两个板块上系统性偏低，
    而偏低的表现是 gold 里涨停判定偏多 —— 数照样算得出来。
    """
    b = board_of(code)
    if b == "unknown":
        raise LimitRuleError(f"认不出板块：{code} —— 认不出不等于用默认值")
    if is_s_share:
        return S_SHARE_PCT, b, "S 股（未完成股改）5%"
    if is_st and trade_date > ST_5PCT_LAST_DAY:
        is_st = False          # 5% 带已于 2026-07-06 起取消，回到板块正常幅度
    if b == "bse":
        return 0.30, b, "北交所 30%"
    if b == "star":
        pct = 0.20 if trade_date >= STAR_20PCT_FROM else 0.10
        return pct, b, f"科创板（{'20%' if pct == 0.2 else '开市前 10%'}）；ST 不收窄"
    if b == "chinext":
        if trade_date >= CHINEXT_20PCT_FROM:
            return 0.20, b, "创业板注册制 20%；ST 不收窄"
        return (0.05, b, "创业板注册制前，ST 5%") if is_st else (0.10, b, "创业板注册制前 10%")
    return (0.05, b, "主板 ST 5%") if is_st else (0.10, b, "主板 10%")


def _round2(x: Decimal, rounding=ROUND_HALF_UP) -> float:
    return float(x.quantize(Decimal("0.01"), rounding=rounding))


#: 取整口径**按板块不同**（实测，2026-07 全市场 23 个交易日）：
#: 沪深各板块是普通四舍五入；**北交所是「不超过幅度」的截断** ——
#: 涨停向下取整、跌停向上取整。用四舍五入去核北交所，一致率只有 **52.4%**；
#: 换成截断是 **99.87%**。这条差别**任何文档核对都查不出来**，
#: 只有拿私有 `stk_limit` 逐行核才看得见。
_ROUNDING = {"bse": (ROUND_FLOOR, ROUND_CEILING)}


def derive(code: str, trade_date: str, pre_close, *, is_st: bool,
           days_listed: int | None = None, is_s_share: bool = False,
           delisting_first_day: bool = False) -> Limits:
    """从前收推涨跌停价。

    `up`/`down` 为 `None` 有**两种**含义，靠 `reason` 区分，不靠值：
    ① 前收缺失 —— **不猜**；② 新股前 5 个交易日**无涨跌幅限制**。
    调用方要区分时读 `reason`；把「无限制」写成一个大数是**私有 oracle 的编码**，
    不是这里的语义（见 `ORACLE_NO_LIMIT_SENTINEL`）。

    `days_listed`：含当日在内、上市以来的交易日序号（第 1 日 = 上市当日）。
    传 `None` 表示调用方**不知道** —— 那就按有限制推，
    并在 `reason` 里说明这一点，免得「不知道」被读成「已确认不是新股」。
    """
    b = board_of(code)
    if pre_close is None:
        return Limits(None, None, None, b, "前收缺失 —— 不猜")
    if delisting_first_day and DELISTING_FIRST_DAY_FREE:
        return Limits(None, None, None, b, "退市整理期第 1 个交易日 —— 无涨跌幅限制")
    n_free = NO_LIMIT_TRADING_DAYS.get(b, 0)
    if days_listed is not None and days_listed <= n_free:
        return Limits(None, None, None, b,
                      f"新股上市第 {days_listed} 个交易日 —— 前 {n_free} 日无涨跌幅限制")
    pct, b, why = limit_pct(code, trade_date, is_st=is_st, is_s_share=is_s_share)
    if days_listed is None:
        why += "；**上市日未知**，按有限制推"
    p = Decimal(str(pre_close))
    ru, rd = _ROUNDING.get(b, (ROUND_HALF_UP, ROUND_HALF_UP))
    return Limits(_round2(p * (Decimal(1) + Decimal(str(pct))), ru),
                  _round2(p * (Decimal(1) - Decimal(str(pct))), rd), pct, b, why)
