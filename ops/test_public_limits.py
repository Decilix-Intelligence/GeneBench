# -*- coding: utf-8 -*-
"""`snapshots/public/limits.py` 的判据（卡 2.5 §3 / B3）。

每条常量都对得上**私有 `stk_limit` 上实测到的**行为，
样例值直接取自 2026-07 的 oracle 行 —— 不是编出来的。
"""
from __future__ import annotations

import pytest

from snapshots.public import limits as L


# ---------------------------------------------------------------- 板块判定
@pytest.mark.parametrize("code,board", [
    ("600000.SH", "main"), ("000001.SZ", "main"), ("001248.SZ", "main"),
    ("300750.SZ", "chinext"), ("301583.SZ", "chinext"), ("302132.SZ", "chinext"),
    ("688806.SH", "star"), ("689009.SH", "star"),
    ("830799.BJ", "bse"), ("430047.BJ", "bse"), ("920006.BJ", "bse"),
    ("sh.600000", "main"), ("sz.300750", "chinext"),
])
def test_board_classification(code, board):
    assert L.board_of(code) == board


def test_new_code_ranges_are_covered():
    """`302xxx`（创业板）与 `920xxx`（北交所）是 2026-07 在册的**真代码**。

    只写 `300` / `8`+`4` 会把它们判成 unknown —— 而 unknown 在这里是**抛异常**。
    实测：2026-07 的 5,542 个代码里有 333 个曾落进 unknown（332 个 920、1 个 302）。
    """
    for c in ("920006.BJ", "302132.SZ"):
        assert L.board_of(c) != "unknown"


def test_unknown_board_raises_instead_of_defaulting():
    """认不出不等于用默认值 —— 默认成 10% 会让北交所的推导系统性偏窄。"""
    with pytest.raises(L.LimitRuleError):
        L.limit_pct("999999.XX", "20260731", is_st=False)


# ---------------------------------------------------------------- 取整口径
@pytest.mark.parametrize("code,pre,up,down", [
    ("000001.SZ", 11.61, 12.77, 10.45),      # 11.61×1.1 = 12.771 → 12.77（不是 12.78）
    ("000002.SZ", 3.33, 3.66, 3.00),
    ("000007.SZ", 8.71, 9.58, 7.84),
])
def test_main_board_matches_the_oracle_rows(code, pre, up, down):
    """三行**取自私有 `stk_limit` 的 20260731**，不是构造的。"""
    r = L.derive(code, "20260731", pre, is_st=False, days_listed=999)
    assert (r.up, r.down) == (up, down)


def test_rounding_is_half_up_not_bankers():
    """Python 内置 `round()` 是银行家舍入，第三位恰为 5 时会差一分。

    `1.15 × 1.1 = 1.265` → 四舍五入 **1.27**；`round(1.265, 2)` 给 1.26。
    """
    r = L.derive("600000.SH", "20260731", 1.15, is_st=False, days_listed=999)
    assert r.up == 1.27, f"取整口径不对：{r.up}"
    assert round(1.265, 2) == 1.26, "前提变了：这条测试靠的是内置 round 的行为"


def test_bse_truncates_instead_of_rounding():
    """**北交所是「不超过幅度」的截断**，不是四舍五入（实测差别巨大）。

    2026-07 全市场 7,518 行北交所：用四舍五入核一致率 **52.4%**，
    换成涨停向下取整 / 跌停向上取整是 **99.87%**。
    """
    r = L.derive("920006.BJ", "20260731", 10.01, is_st=False, days_listed=999)
    # 10.01×1.3 = 13.013 → 截断 13.01（四舍五入也会给 13.01）
    # 10.01×0.7 = 7.007 → 向上 7.01（四舍五入会给 7.01）——换个数才分得开：
    r2 = L.derive("920006.BJ", "20260731", 10.05, is_st=False, days_listed=999)
    # 10.05×1.3 = 13.065 → **截断 13.06**（四舍五入会给 13.07）
    assert r2.up == 13.06, f"北交所涨停没有向下截断：{r2.up}"
    # 10.05×0.7 = 7.035 → **向上 7.04**（四舍五入也给 7.04，方向一致）
    assert r2.down == 7.04
    assert r.up == 13.01


def test_bse_rounding_differs_from_main_on_the_same_number():
    """判别力：同一个前收，北交所与主板的取整方向必须真的不同。"""
    pre = 10.05
    bse = L.derive("920006.BJ", "20260731", pre, is_st=False, days_listed=999)
    main = L.derive("600000.SH", "20260731", pre, is_st=False, days_listed=999)
    assert bse.up != main.up and bse.pct != main.pct


# ---------------------------------------------------------------- ST
def test_main_board_st_is_five_percent():
    """`000010.SZ` 20260701 前收 1.70 → oracle up 1.79 / down 1.62（实测行）。"""
    r = L.derive("000010.SZ", "20260701", 1.70, is_st=True, days_listed=999)
    assert (r.up, r.down, r.pct) == (1.79, 1.62, 0.05)


@pytest.mark.parametrize("code", ["301583.SZ", "688806.SH"])
def test_registration_boards_do_not_narrow_for_st(code):
    """**最容易写错的一条**：创业板 / 科创板的 ST **仍是 20%**。

    写成「ST 一律 5%」会在这两个板块上系统性偏窄，而偏窄的表现是
    gold 里涨停判定偏多 —— 数照样算得出来。
    """
    # **日期必须早于 ST 带取消日**，否则 is_st 早就被重置了，
    # 这条测试会测不到「注册制板块不因 ST 收窄」这件事本身。
    day = "20260601"
    assert day <= L.ST_5PCT_LAST_DAY
    st = L.derive(code, day, 10.0, is_st=True, days_listed=999)
    non = L.derive(code, day, 10.0, is_st=False, days_listed=999)
    assert st.pct == non.pct == 0.20
    assert st.up == non.up == 12.0


# ---------------------------------------------------------------- 新股
@pytest.mark.parametrize("day", [1, 2, 3, 4, 5])
def test_first_five_trading_days_have_no_limit(day):
    """实测四只 2026-07 新股（301583 / 688806 / 001248 / 688825）**全部**前 5 日无限制。"""
    r = L.derive("301583.SZ", "20260710", 22.6, is_st=False, days_listed=day)
    assert r.up is None and r.down is None
    assert "无涨跌幅限制" in r.reason


def test_sixth_trading_day_is_limited_again():
    r = L.derive("301583.SZ", "20260717", 140.0, is_st=False, days_listed=6)
    assert r.up == 168.0 and r.down == 112.0      # oracle 行：140.0 → 168.0 / 112.0


def test_unknown_listing_date_is_said_out_loud():
    """「不知道上市日」不能被读成「已确认不是新股」——理由里必须写着。"""
    r = L.derive("600000.SH", "20260731", 10.0, is_st=False, days_listed=None)
    assert r.up is not None and "上市日未知" in r.reason


def test_missing_pre_close_is_not_guessed():
    r = L.derive("600000.SH", "20260731", None, is_st=False, days_listed=999)
    assert r.up is None and "不猜" in r.reason


def test_no_limit_and_missing_pre_close_are_distinguishable():
    """两种 `up is None` 含义相反，**只能靠 reason 分**（值分不出来）。"""
    a = L.derive("600000.SH", "20260731", None, is_st=False, days_listed=999)
    b = L.derive("301583.SZ", "20260710", 22.6, is_st=False, days_listed=1)
    assert a.up is b.up is None
    assert a.reason != b.reason


def test_module_does_not_emit_the_oracle_sentinel():
    """「无限制」是**语义**（`None`），不是一个大数。

    私有 oracle 用 `999999.999`/`99999.999` 编码它，而且**沪深还不一样** ——
    把编码搬进推导，公开通道就会带着一个私有实现细节走。
    """
    import inspect
    src = inspect.getsource(L.derive) + inspect.getsource(L.limit_pct)
    assert "999999.999" not in src and "99999.999" not in src




# ---------------------------------------------------------------- 生效日
def test_chinext_was_ten_percent_before_2020_08_24():
    old = L.limit_pct("300750.SZ", "20200821", is_st=False)
    new = L.limit_pct("300750.SZ", "20200824", is_st=False)
    assert old[0] == 0.10 and new[0] == 0.20


# ---------------------------------------------------------------- 实测出来的三条规则修正
def test_st_five_percent_band_ends_within_the_window():
    """**ST 的 5% 带在冻结线之前就结束了**（私有 oracle 逐日数出来的）。

    「隐含幅度落在 4%~6%」的票数：20260615..20260703 每天 149–162 只，
    **20260706 起只剩 1 只**（`600182.SH` S佳通，是 S 股不是 ST），此后到 20260731 不变。

    卡 2.5 §3 的规则表写「ST / *ST 5%」且**没有生效日** —— 照它推，
    冻结线前最后 18 个交易日约 150 只票逐日推错，而**私有通道读 `stk_limit` 不受影响**：
    只有要自己推的公开通道会错。
    """
    before = L.derive("000010.SZ", "20260701", 1.70, is_st=True, days_listed=999)
    after = L.derive("000010.SZ", "20260710", 1.70, is_st=True, days_listed=999)
    assert before.pct == 0.05 and (before.up, before.down) == (1.79, 1.62)   # oracle 行
    assert after.pct == 0.10 and (after.up, after.down) == (1.87, 1.53)      # oracle 行
    assert L.ST_5PCT_LAST_DAY == "20260703"


def test_s_share_keeps_the_five_percent_band():
    """`600182.SH`「S佳通」是全市场**唯一**仍在 5% 带上的票（20260710 实测）。

    它是 **S 股（未完成股改）**，不是 ST —— 两者的判据必须分开，
    否则 ST 带取消时会把它一起带走。
    """
    r = L.derive("600182.SH", "20260710", 13.65, is_st=False, days_listed=999, is_s_share=True)
    assert r.pct == L.S_SHARE_PCT == 0.05
    assert abs(r.up - 14.33) < 1e-9      # oracle 隐含 0.0498


def test_new_listing_free_window_is_board_specific():
    """北交所新股只有 **1 天**无限制，沪深是 **5 天**（`920222.BJ` 20260629 上市实测）。

    写成一个全局的 5，北交所新股的第 2–5 天会被系统性判成「无限制」。
    """
    assert L.NO_LIMIT_TRADING_DAYS["bse"] == 1
    assert L.NO_LIMIT_TRADING_DAYS["main"] == L.NO_LIMIT_TRADING_DAYS["star"] == 5
    d2 = L.derive("920222.BJ", "20260701", 36.17, is_st=False, days_listed=2)
    assert d2.up is not None and d2.pct == 0.30      # oracle：47.02 / 25.32
    assert abs(d2.up - 47.02) < 1e-9 and abs(d2.down - 25.32) < 1e-9


def test_sentinel_table_has_three_encodings():
    """「无限制」在私有 oracle 里有**三种**编码，三个交易所各一种。"""
    assert set(L.ORACLE_NO_LIMIT_SENTINEL) == {"SH", "SZ", "BJ"}
    assert len({v for v in L.ORACLE_NO_LIMIT_SENTINEL.values()}) == 3


def test_delisting_first_day_has_no_limit():
    """**退市整理期第 1 个交易日无涨跌幅限制**（卡 §3 的规则表里没有这一条）。

    2026-01..07 内名字以「退」结尾的票共 7 只，每只**恰好 1 天**出现无限制哨兵，
    且那一天**正好等于**它在 `namechange` 里改名为「*退」的 `start_date`（7/7）。
    判据取自改名日 —— 那张表与 `stk_limit` 相互独立，不是拿 oracle 反推 oracle。
    """
    r = L.derive("920305.BJ", "20260709", 3.57, is_st=False, days_listed=999,
                 delisting_first_day=True)
    assert r.up is None and r.down is None and "退市整理期" in r.reason
    nxt = L.derive("920305.BJ", "20260710", 0.69, is_st=False, days_listed=999)
    assert nxt.up is not None, "只有第 1 天无限制，第 2 天要回到正常幅度"
    assert abs(nxt.up - 0.89) < 1e-9 and abs(nxt.down - 0.49) < 1e-9   # oracle 行


def test_delisting_beats_the_normal_branch_but_not_missing_pre_close():
    """优先级：前收缺失 > 退市整理期 > 新股 > 正常。

    「前收缺失」必须排最前 —— 没有前收时**任何**推导都是猜。
    """
    a = L.derive("920305.BJ", "20260709", None, is_st=False, delisting_first_day=True)
    assert "不猜" in a.reason
    b = L.derive("301583.SZ", "20260710", 22.6, is_st=False, days_listed=1,
                 delisting_first_day=True)
    assert "退市整理期" in b.reason      # 同时命中时以退市整理期为准（实测里两者不共存）


# ---------------------------------------------------------------- 数据卡与实现对齐
def test_data_card_numbers_match_the_module():
    """**D-21 对齐断言**：数据卡里的口径必须与 `limits.py` 的常量一致。

    数据卡是**手写**的（不像 `qlib_provider.md` 由代码生成），
    所以它与实现之间没有天然的绑定 —— 改了常量而忘了改卡，
    两处会各说各话，而读卡的人不会去读代码。
    """
    from pathlib import Path
    card = (Path(__file__).resolve().parents[1] / "ops" / "data_cards"
            / "public_channel.md").read_text(encoding="utf-8")
    # ST 带的结束日
    y, m, d = L.ST_5PCT_LAST_DAY[:4], L.ST_5PCT_LAST_DAY[4:6], L.ST_5PCT_LAST_DAY[6:]
    nxt = "2026-07-06"                       # 结束日之后的第一个交易日（实测那一天起取消）
    assert nxt in card, f"卡里没写 ST 带取消日 {nxt}（模块里最后一天是 {y}-{m}-{d}）"
    # 新股窗口：沪深 5 / 北交所 1
    assert f"沪深 {L.NO_LIMIT_TRADING_DAYS['main']} 天" in card
    assert f"北交所 {L.NO_LIMIT_TRADING_DAYS['bse']} 天" in card
    # 三种哨兵编码都要写进卡 —— 它们是与私有 oracle 对账时唯一会用到的实现细节
    for ex, (up, dn) in L.ORACLE_NO_LIMIT_SENTINEL.items():
        assert str(up) in card, f"卡里没写 {ex} 的无限制哨兵 {up}"
    # 判据取 change_reason 而不是名字
    assert "change_reason" in card and "退市整理期" in card
