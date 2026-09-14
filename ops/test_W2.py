# -*- coding: utf-8 -*-
"""卡 W2：发布阻塞的技术两项。

1. **冻结件**：`PUBLIC_FROZEN_ARTIFACTS` 六件到位，且**还是当初算出 gold 的那一份**
   —— 不看「文件在不在」（那太便宜了），看编译记录能不能把 gold 的标注面重放出来；
2. **instruments 重建**：只用 baostock 成分接口重建 csi300 / csi500 的 PIT 名单，
   与私有 `universe_pit` 对账。

第 2 组里**联网的部分不在测试里**（对方服务今天上午拒连过半小时，把它写进测试
等于给别人埋一颗恒红的雷）。测试只钉两件事：**不联网也能验的推断规则**
（`intervals` / 代码写法转换 / 非交易时段判据），以及**产物在的时候它自洽**。
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import genebench_config as cfg                              # noqa: E402
from snapshots.public import manifest as PM                 # noqa: E402


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ================================================================ 1. 冻结件

def test_every_declared_frozen_artifact_is_in_the_repo():
    """六件**全部**在仓库里。少一件 = 拿到包的人复现不了 τ。"""
    gone = [r for r in PM.PUBLIC_FROZEN_ARTIFACTS if not (REPO / r).is_file()]
    assert not gone, (
        f"冻结件缺 {gone} —— 三个 jsonl 在数据湖 {PM.FACTOR_LIB_UPSTREAM}，"
        f"跑 `python snapshots/public/recover_factor_library.py --write` 收回来")


def test_the_recorded_sha256_of_each_frozen_artifact_is_the_real_one():
    """登记的 sha 与文件实际的 sha 一致 —— 登记表不许和事实各说各话。"""
    bad = []
    for rel, want in PM.PUBLIC_FROZEN_ARTIFACT_SHA256.items():
        p = REPO / rel
        if not p.is_file():
            bad.append(f"{rel}：登记了 sha，文件不在")
        elif _sha(p) != want:
            bad.append(f"{rel}：登记 {want[:12]}… ≠ 实际 {_sha(p)[:12]}…")
    assert not bad, "冻结件的校验和对不上：\n  " + "\n  ".join(bad)


def test_the_sha_registry_covers_exactly_the_declared_artifacts():
    """登记表与声明清单**同集合** —— 只登记一半等于没登记。"""
    assert set(PM.PUBLIC_FROZEN_ARTIFACT_SHA256) == set(PM.PUBLIC_FROZEN_ARTIFACTS)


def test_the_repo_copies_are_byte_identical_to_the_lake():
    """仓库副本 == 湖里的上游。湖读不到就跳过（本测试也要能在没有湖的机器上跑）。"""
    up = cfg.LAKE / "reference" / "factor_library" / "compiled"
    if not up.is_dir():
        pytest.skip(f"读不到数据湖 {up}")
    for n in ("qlib_native.jsonl", "qlib_panel.jsonl", "blocked.jsonl"):
        a, b = up / n, REPO / "factor_library" / "compiled" / n
        assert _sha(a) == _sha(b), f"{n} 与湖里的不一致 —— 有人动过其中一边"


def test_the_backend_split_of_the_repo_copies_still_matches_gold():
    """从**仓库副本**读记录，后端分布必须逐个等于 `factor_exec` 的实测常量。

    644 / 66 / 82 + blocked 24。对不上说明因子池变了 —— 在旧池子上标定并签字的 τ
    就失去了锚点，`load_records()` 会直接抛，这条测试把那声抛捕成红。
    """
    from reference import factor_exec as fx
    fx.FACTOR_LIB = REPO / "factor_library" / "compiled"
    recs, prov = fx.load_records()
    assert prov["backend_counts"] == {**fx.EXPECTED_BACKENDS, "<blocked>": fx.EXPECTED_BLOCKED}
    assert len([r for r in recs if r.get("executable")]) == sum(fx.EXPECTED_BACKENDS.values())


def test_the_repo_copies_reproduce_the_operator_conflict_lists_written_beside_gold():
    """**最有力的一条**：gold 的标注面能被仓库副本一字不差地重放。

    `operator_convention_suspect.json` 是 2026-09-01 与 gold 一起落盘的。它的两个数组
    完全由编译记录决定。重放对得上 ⇒ 仓库里这三份与算 gold 用的那三份同源。
    """
    side = cfg.SNAPSHOTS_V1 / "gold_factors" / "operator_convention_suspect.json"
    if not side.is_file():
        pytest.skip(f"读不到 gold 旁的标注 {side}")
    want = json.loads(side.read_text(encoding="utf-8"))

    from reference import factor_exec as fx
    from reference import operator_flags as of
    fx.FACTOR_LIB = REPO / "factor_library" / "compiled"
    recs, _ = fx.load_records()
    comparable = [x["id"] for x in json.loads(
        (cfg.OPS / "acceptance" / "card_2.1b_crosscheck.json").read_text(encoding="utf-8"))["rows"]]

    assert of.gold_suspect(recs) == want["gold_suspect"], "gold 存疑名单重放不出来"
    assert of.tau_excluded(comparable, recs) == want["tau_excluded"], "τ 排除名单重放不出来"
    assert len(want["tau_excluded"]) == 13 and len(want["gold_suspect"]) == 23


def test_the_release_manifest_no_longer_blocks_on_missing_frozen_artifacts():
    """`frozen_artifacts_missing` 已闭合，且是**推导**出来的不是手写的。"""
    m = json.loads((REPO / "RELEASE_MANIFEST.json").read_text(encoding="utf-8"))
    bl = next(b for b in m["blockers"] if b["id"] == "frozen_artifacts_missing")
    assert bl["satisfied"] is True, f"仍未闭合：{bl['status_now']}"
    assert not (set(m["missing"]) & set(PM.PUBLIC_FROZEN_ARTIFACTS))


def test_the_remaining_blockers_are_the_users_decisions_not_ours():
    """那三条**不是技术项** —— 谁也不许替用户把它们标成满足。

    2026-09-10（卡 W.rt）改成**子集**判：清单里后来又加了技术项 blocker
    （`public_channel_zero_runs`：公开通道一个 run 都没有），那是我们自己的活，**可以**闭合，
    不该把这条断言拖红。这条钉的仍然是原来那件事 —— 三条用户决定项一条都不许被标成满足。
    """
    m = json.loads((REPO / "RELEASE_MANIFEST.json").read_text(encoding="utf-8"))
    open_ = sorted(b["id"] for b in m["blockers"] if not b["satisfied"])
    users = ["code_license_undecided", "data_license_text", "no_clone_url"]
    # 2026-09-11（卡 Z）：这张名单原本写死成「必须还开着」。用意没失效 ——
    # **不许施工方替用户把用户决定项标成满足**；失效的是那张名单：
    # 其中两条恰恰是**用户自己**决定的（⑳ 选了 Apache-2.0、㉑ 给了两个仓库地址）。
    # 于是分成两半：用户已裁的进 settled，剩下的仍然一条都不许被标成满足。
    # 2026-09-11 用户裁定 ⑨ 又裁了第三条：baostock 的再分发许可**已取得**
    # （研究用途、允许再分发派生日线数据、署名 baostock），`DATA_LICENSE` 状态 `granted`。
    # 于是三条用户决定项**全部**由用户自己裁完 —— 这条测试要拦的事没变：
    # 未裁定的一条都不许被施工方标成满足；裁定过的必须真的闭合、且记着谁裁的。
    users_settled = {"code_license_undecided", "no_clone_url", "data_license_text"}
    assert set(users) - users_settled <= set(open_), open_
    for bid in users_settled:
        b = next(x for x in m["blockers"] if x["id"] == bid)
        assert b["satisfied"] is True, f"{bid} 被记成已裁定却又没闭合：{b['status_now']}"
    # 技术项可以闭合，但不许**冒充**用户决定项混进来 —— 新增的每一条都要在这里被认一次。
    assert set(open_) - set(users) <= {"public_channel_zero_runs"}, open_
    # `releasable` 是**推导量**（没有缺件 ∧ 五条 blocker 全闭）。原来写死 `is False` ——
    # 裁定 ⑨ 闭掉最后一条之后那句话变成了假。这里改成「与清单自己的推导一致」：
    # 要拦的事没变（不许手改这个字段），且不再随用户裁定而红。
    derived = (not m["missing"]) and all(b["satisfied"] for b in m["blockers"])
    assert m["releasable"] is derived, \
        f"releasable 被手改了：缺件 {m['missing']}、未闭合 {open_}"


# ================================================================ 2. instruments 重建

@pytest.fixture(scope="module")
def IR():
    from snapshots.public import instruments_rebuild as ir
    return ir


def test_baostock_has_no_csi1000_constituent_api(IR):
    """**已知限制要写进代码，不只是写进报告。** baostock 只有 300 / 500 / 上证50。"""
    assert set(IR.INDICES) == {"csi300", "csi500"}
    assert "csi1000" not in IR.INDICES


def test_code_spellings_round_trip(IR):
    assert IR.to_qlib("sh.600000") == "SH600000"
    assert IR.to_qlib("sz.000001") == "SZ000001"
    assert IR.to_lake("sh.600000") == "600000.SH"
    assert IR.to_lake("sz.000001") == "000001.SZ"


def test_trading_hours_guard_matches_card_2_5(IR):
    """判据与 `ops/acceptance/card_2_5_fetch_union.py` 逐字同源：工作日 09:00–15:30 拒绝。"""
    import datetime as dt
    from ops.acceptance import card_2_5_fetch_union as C
    bj = dt.timezone(dt.timedelta(hours=8))
    for t, blocked in (((9, 0), True), ((12, 0), True), ((15, 30), True),
                       ((8, 59), False), ((15, 31), False)):
        now = dt.datetime(2026, 9, 10, *t, tzinfo=bj)          # 周四
        for fn, exc in ((IR.assert_not_trading_hours, IR.TradingHours),
                        (C.assert_not_trading_hours, C.TradingHours)):
            if blocked:
                with pytest.raises(exc):
                    fn(now)
            else:
                fn(now)
    IR.assert_not_trading_hours(dt.datetime(2026, 9, 12, 10, 0, tzinfo=bj))   # 周六：放行


def test_intervals_split_on_a_real_gap_and_only_on_a_real_gap(IR):
    """区间化的**判别力**：连着的合成一段，断开的必须裂成两段。"""
    days = ["2020-01-02", "2020-01-03", "2020-01-06", "2020-01-07", "2020-01-08"]
    mem = {days[0]: ["A", "B"], days[1]: ["A", "B"], days[2]: ["A"],
           days[3]: ["A", "B"], days[4]: ["A", "B"]}
    got = IR.intervals(mem, days)
    assert ("A", days[0], days[4]) in got, "全程在册却被切开了"
    assert ("B", days[0], days[1]) in got and ("B", days[3], days[4]) in got, "中间掉出去没被切开"
    assert len([x for x in got if x[0] == "B"]) == 2


def test_intervals_do_not_bridge_a_gap_at_the_edges(IR):
    days = ["2020-01-02", "2020-01-03", "2020-01-06"]
    got = IR.intervals({days[0]: ["A"], days[1]: [], days[2]: ["A"]}, days)
    assert sorted(got) == [("A", days[0], days[0]), ("A", days[2], days[2])]


def _rebuild_dir():
    return cfg.SNAPSHOTS_PUBLIC / "instruments_rebuild"


#: csi500 有 **22 个交易日只有 499 只** —— 这是 baostock 上游那 4 个名单版本自己就少一只
#: （2019-01-07 / 2019-01-14 / 2021-09-13 / 2021-09-27 各覆盖的那几天），
#: **不是我们跨步推断漏了一次调整**。判别方式见下面那条测试：短的天必须**整版整版**地短。
CSI500_SHORT_DAYS: int = 22
CSI500_SHORT_VERSIONS: tuple[str, ...] = ("2019-01-07", "2019-01-14", "2021-09-13", "2021-09-27")


@pytest.mark.parametrize("uni", ["csi300", "csi500"])
def test_the_rebuilt_membership_has_the_right_size_every_single_day(uni, IR):
    """产物在的时候：**每一个交易日**的成分数都要对得上，短的那些天要能逐条交代。

    这是最便宜也最狠的一条 —— 跨步推断只要漏掉一次调整，某些天就会多一只或少一只。
    csi300 全窗 4,269 天**天天 300**；csi500 有 22 天是 499，全部落在 4 个上游名单版本上。
    """
    p = _rebuild_dir() / f"{uni}_daily.jsonl"
    if not p.is_file():
        pytest.skip(f"还没重建：{p}（跑 instruments_rebuild.py fetch build）")
    want = {"csi300": 300, "csi500": 500}[uni]
    short, bad = [], []
    days = set(IR.calendar())
    seen = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        seen.add(rec["date"])
        n = len(rec["codes"])
        if len(set(rec["codes"])) != n:
            bad.append(f"{rec['date']}: 有重复代码")
        if n == want:
            continue
        if n == want - 1 and uni == "csi500":
            short.append(rec["date"])
        else:
            bad.append(f"{rec['date']}: {n}（既不是 {want} 也不是已知的 {want - 1}）")
    assert not bad, f"{uni} 成分数不对的日子（前 10）：{bad[:10]}（共 {len(bad)} 天）"
    assert seen == days, f"{uni} 覆盖的交易日与冻结日历不符（缺 {len(days - seen)} 天）"
    if uni == "csi500":
        assert len(short) == CSI500_SHORT_DAYS, (
            f"499 只的天数变了：{len(short)} ≠ {CSI500_SHORT_DAYS} —— "
            f"要么上游改了，要么我们的推断漏了一次调整，两种都要停下来看")


def test_the_short_csi500_days_come_from_upstream_versions_not_from_our_inference(IR):
    """**判别力**：短的天必须**整版整版**地短。

    这一条把两种成因分开：如果是我们跨步推断漏了调整，短的天会**横跨**某个名单版本的
    一部分（同一个 `updateDate` 下有的天 500、有的天 499）；如果是上游那一版自己就少一只，
    那一版覆盖的**每一天**都短。没有这条，上面那个 `== 22` 只是把现状抄下来当成了判据。
    """
    cache = _rebuild_dir() / "bs_cache" / "csi500"
    daily = _rebuild_dir() / "csi500_daily.jsonl"
    if not (cache.is_dir() and daily.is_file()):
        pytest.skip("还没重建")
    sizes = {}
    for line in daily.read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        sizes[rec["date"]] = len(rec["codes"])
    ver, cur = {}, None
    for d in IR.calendar():                      # 把逐日回填到它所属的上游名单版本
        f = cache / f"{d}.json"
        if f.is_file():
            cur = json.loads(f.read_text(encoding="utf-8"))["update"]
        ver.setdefault(cur, []).append(d)
    mixed = {u: sorted({sizes[d] for d in ds}) for u, ds in ver.items()
             if len({sizes[d] for d in ds}) > 1}
    assert not mixed, (
        f"有名单版本内部成分数不一致：{mixed} —— 那说明**同一版里混进了别的版**，"
        f"跨步推断漏了一次调整，必须重取")
    short_vers = sorted(u for u, ds in ver.items() if sizes[ds[0]] != 500)
    assert tuple(short_vers) == CSI500_SHORT_VERSIONS, short_vers


@pytest.mark.parametrize("uni", ["csi300", "csi500"])
def test_the_rebuilt_intervals_and_the_daily_sets_say_the_same_thing(uni, IR):
    """两份产物**必须互相解释**：区间展开 == 逐日集合。"""
    d1, d2 = _rebuild_dir() / f"{uni}.txt", _rebuild_dir() / f"{uni}_daily.jsonl"
    if not (d1.is_file() and d2.is_file()):
        pytest.skip("还没重建")
    days = IR.calendar()
    idx = {d: i for i, d in enumerate(days)}
    from collections import defaultdict
    expanded = defaultdict(set)
    for line in d1.read_text(encoding="utf-8").splitlines():
        c, a, b = line.split("\t")
        for k in range(idx[a], idx[b] + 1):
            expanded[days[k]].add(c)
    for line in d2.read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        assert expanded[rec["date"]] == set(rec["codes"]), f"{uni} {rec['date']} 两份产物不一致"
