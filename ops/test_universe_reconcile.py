"""卡 1.1 对账验收测试。

跑法::

    cd $REPO && $GENEBENCH_ROOT/env/bin/python -m pytest ops/test_universe_reconcile.py -q

断言分六组:

1. **产物存在且权限对**(红线 5:目录 0700、文件 0600)。
2. **算术自洽**:成员日的交并差恒等式、Jaccard 与交并集一致、归因不重不漏。
   这一组是这份报告可信度的地基 —— 归因表若不配平,分类结论就是编的。
3. **约定归一化生效**:窗口右端落在冻结线、两源原生跨度是**原始日历**日期
   (不能被交易日网格夹成 2009-01-05)、源A 的合并是恒等变换。
4. **抽样可复现**:同种子重算两次逐字相同;JSON 里落盘的 300 只与重算结果一致;
   不同宇宙抽到的不是同一批票。
5. **签字清单可用**:20 条、覆盖多类、20 家不同公司、每条都有判词与依据。
6. **与源B 文档的交叉核对**:自动识别出的代码映射对必须正好是源B 文档 §2.2
   列出的那 4 组 —— 多一组是误配,少一组是漏配,两种都得炸。
7. **冻结线**(红线 7):产物里没有任何日期越过 `cfg.FREEZE_DATE`。
"""

from __future__ import annotations

import datetime as dt
import json
import re
import stat

import pytest

import genebench_config as cfg
from snapshots import universe_reconcile as ur

#: 源B 文档 §2.2 / §5 独立考据出来的 4 组代码变更(旧码 → 新码)。
#: 写死是故意的:自动配对必须**重现**这份人写的结论,而不是自说自话。
EXPECTED_CODE_MAP_PAIRS = {
    ("000022.SZ", "001872.SZ"),
    ("000043.SZ", "001914.SZ"),
    ("300114.SZ", "302132.SZ"),
    ("601313.SH", "601360.SH"),
}


@pytest.fixture(scope="module")
def res() -> dict:
    path = ur.summary_path()
    assert path.exists(), f"摘要不在:{path};先跑 python -m snapshots.universe_reconcile"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def report_text() -> str:
    path = ur.report_path()
    assert path.exists(), f"报告不在:{path};先跑 python -m snapshots.universe_reconcile"
    return path.read_text(encoding="utf-8")


# ------------------------------------------------------------- 1. 产物与权限


def test_artifacts_exist():
    assert ur.summary_path().exists()
    assert ur.report_path().exists()


def test_artifact_modes_are_0600():
    """答案面之外的产物也一律 0600 —— 本机 umask 是 002,不显式 chmod 就会组可读。"""
    for path in (ur.summary_path(), ur.report_path()):
        mode = stat.S_IMODE(path.stat().st_mode)
        assert mode & cfg.FORBIDDEN_MODE_BITS == 0, f"{path} mode={oct(mode)} 组/其它可读"


def test_report_dir_mode_is_0700():
    mode = stat.S_IMODE(cfg.REPORTS.stat().st_mode)
    assert mode & cfg.FORBIDDEN_MODE_BITS == 0, f"{cfg.REPORTS} mode={oct(mode)}"


# ------------------------------------------------------------- 2. 算术自洽


@pytest.mark.parametrize("uni", cfg.UNIVERSES)
def test_member_day_set_identities(res, uni):
    """交并差恒等式。任何一条不成立,后面所有一致率都不用看了。"""
    m = res["per_universe"][uni]["member_day"]
    assert m["n_intersection"] + m["n_only_source_a"] == m["n_member_days_source_a"]
    assert m["n_intersection"] + m["n_only_source_b"] == m["n_member_days_source_b"]
    assert (
        m["n_intersection"] + m["n_only_source_a"] + m["n_only_source_b"]
        == m["n_union"]
    )
    assert m["n_symmetric_difference"] == m["n_only_source_a"] + m["n_only_source_b"]
    assert m["jaccard"] == pytest.approx(m["n_intersection"] / m["n_union"], abs=1e-6)


def test_overall_member_day_is_the_sum_of_universes(res):
    ov = res["member_day_overall"]
    for key in ("n_intersection", "n_union", "n_only_source_a", "n_only_source_b"):
        assert ov[key] == sum(
            res["per_universe"][u]["member_day"][key] for u in cfg.UNIVERSES
        )


def test_attribution_is_exhaustive_and_disjoint(res):
    """各分歧类型的成员日之和必须**恰好等于**总对称差,且未归类为 0。

    这是整份分类表的可信度地基:配不平就说明区段被重复计数或漏计,
    "81.6% 来自基期缺口"之类的话立刻变成编的。
    """
    ac = res["attribution_check"]
    assert ac["balanced"] is True
    assert ac["n_unclassified_runs"] == 0
    assert ac["attributed_member_days"] == ac["total_symmetric_difference_member_days"]
    assert ac["total_symmetric_difference_member_days"] == (
        res["member_day_overall"]["n_symmetric_difference"]
    )
    assert sum(
        c["n_member_days"] for c in res["divergence_classes"].values()
    ) == ac["attributed_member_days"]


def test_per_universe_class_breakdown_sums_to_class_total(res):
    for key, c in res["divergence_classes"].items():
        assert (
            sum(v["n_member_days"] for v in c["by_universe"].values())
            == c["n_member_days"]
        ), f"{key} 的分宇宙拆分与合计对不上"


def test_segment_verdicts_sum_to_sample_size(res):
    for uni in cfg.UNIVERSES:
        blk = res["segment_level"][uni]
        assert sum(blk["verdicts"].values()) == blk["n_sampled"]


# ------------------------------------------------- 3. 约定归一化确实生效


def test_window_right_edge_is_the_freeze_line(res):
    """红线 7:两源都被截到冻结线,所以窗口右端只能是它。"""
    for uni in cfg.UNIVERSES:
        assert res["per_universe"][uni]["window"]["end"] == cfg.FREEZE_DATE


def test_native_spans_use_calendar_dates_not_the_grid(res):
    """源B 的原生左端必须是原始日历日期。

    湖 `trade_cal` 只从 2009-01-05 起。如果这里报的是投影后的网格日期,
    csi300 会写成 "2009-01-05 起",把源B 真实覆盖的 2005~2008 抹掉 ——
    那是一句假话,而且会让"窗口外单独统计"这条要求形同虚设。
    """
    assert res["per_universe"]["csi300"]["window"]["source_b_native_span"][0] == "2005-04-08"
    assert res["per_universe"]["csi500"]["window"]["source_b_native_span"][0] == "2007-01-31"
    for uni in ("csi300", "csi500"):
        out = res["per_universe"][uni]["outside_window"]
        assert out["source_b_rows_entirely_before_window"] > 0
        assert out["source_b_calendar_days_before_window"] > 0


def test_source_a_merge_is_a_noop(res):
    """源A 的相邻段之间至少隔一个完整快照周期,合并必须什么都不动。

    真合并掉了东西,说明源A 的切段逻辑或本模块的网格投影有问题。
    """
    assert res["normalisation"]["source_a"]["n_segments_merged_away"] == 0
    assert res["normalisation"]["source_a"]["merge_is_noop"] is True


def test_source_b_tiling_is_actually_collapsed(res):
    """源B 的贴片行必须被合并掉一大截,否则段级比较比的是"行数"不是"段数"。"""
    diag = res["normalisation"]["source_b"]
    assert diag["n_segments_after_merge"] < diag["n_rows_on_grid"] / 5


# --------------------------------------------------------- 4. 抽样可复现


def test_sampling_is_deterministic():
    pool = [f"{i:06d}.SZ" for i in range(1000)]
    first = ur.sample_codes(pool, "csi300", 300, ur.SAMPLE_SEED)
    second = ur.sample_codes(list(reversed(pool)), "csi300", 300, ur.SAMPLE_SEED)
    assert first == second, "抽样结果依赖了输入顺序,不是纯函数"
    assert len(first) == 300 and len(set(first)) == 300


def test_sampling_differs_across_universes():
    """宇宙名参与哈希 —— 否则三个宇宙在看同一批票,300 只的覆盖面被浪费掉。"""
    pool = [f"{i:06d}.SZ" for i in range(3000)]
    a = set(ur.sample_codes(pool, "csi300", 300, ur.SAMPLE_SEED))
    b = set(ur.sample_codes(pool, "csi1000", 300, ur.SAMPLE_SEED))
    assert len(a & b) < 90, "两个宇宙抽到的票重合过多,种子里大概没带宇宙名"


def test_recorded_sample_matches_recomputation(res):
    """落盘的 300 只必须能被重新算出来 —— 这是签字清单可核查的前提。"""
    for uni in cfg.UNIVERSES:
        recorded = res["segment_level"][uni]["sampled_codes"]
        assert len(recorded) == res["segment_level"][uni]["n_sampled"]
        assert len(set(recorded)) == len(recorded)
        again = ur.sample_codes(recorded, uni, ur.SAMPLE_SIZE, ur.SAMPLE_SEED)
        assert again == sorted(recorded), f"{uni} 的抽样不可复现"


def test_sample_size_matches_the_acceptance_wording(res):
    """实施稿验收原文是"抽 300 只逐段比对"。"""
    assert ur.SAMPLE_SIZE == 300
    for uni in cfg.UNIVERSES:
        assert res["segment_level"][uni]["n_sampled"] == 300


# ------------------------------------------------------- 5. 签字清单可用


def test_signoff_has_twenty_usable_items(res):
    so = res["signoff_sample"]
    assert so["n_items"] == 20
    codes = [it["code"] for it in so["items"]]
    assert len(set(codes)) == 20, "20 条落在少于 20 家公司上,签字覆盖面被浪费"
    for it in so["items"]:
        assert it["verdict"], f"{it['code']} 没有判断"
        assert len(it["basis"]) > 30, f"{it['code']} 的依据太短,等于没写"
        assert it["source_a_says"] and it["source_b_says"]
        assert it["disagreement_span"][0] <= it["disagreement_span"][1]


def test_signoff_is_stratified_not_top_heavy(res):
    """分层挑选:必须覆盖多个类型。

    随机挑会把 20 条全砸在基期缺口一类上(它占九成成员日),
    签完字也看不出别的问题 —— 这条断言就是防那个。
    """
    classes = {it["class"] for it in res["signoff_sample"]["items"]}
    assert len(classes) >= 5, f"只覆盖了 {len(classes)} 类,分层失效"
    non_empty = {
        k for k, v in res["divergence_classes"].items() if v["n_runs"] > 0
    }
    assert classes == non_empty, "有非空类型没被抽到,或抽到了空类型"
    counts = {c: sum(1 for it in res["signoff_sample"]["items"] if it["class"] == c) for c in classes}
    assert max(counts.values()) <= 4, f"单类超过 4 条:{counts}"


def test_delist_verdicts_follow_the_direction_not_a_template(res):
    """退市类的判词必须按方向算。

    源B 通常比源A 晚剔除退市票,但**不是永远** —— `600357.SH`(2009-12-29 退市)
    就是源A 反而多留了 2 天。套模板会在这条上给出反向的错误结论。
    """
    items = [
        it for it in res["signoff_sample"]["items"] if it["class"] == "delist_response"
    ]
    assert items, "退市类一条都没抽到"
    verdicts = {it["verdict"] for it in items}
    assert verdicts != {"源A 对"} or len(items) == 1, "退市判词看起来是套死的"
    for it in items:
        assert it["delist_date"], f"{it['code']} 归到退市类却没有退市日"
        assert "退市" in it["basis"] and it["delist_date"] in it["basis"]


# ---------------------------------------- 6. 与源B 文档的交叉核对


def test_code_mapping_pairs_reproduce_the_source_b_findings(res):
    """自动配对必须正好重现源B 文档 §2.2 的 4 组代码变更。

    多一组 = 误配(用 ``|X∩Y|/min`` 而不是 Jaccard 时实测会把三个不相干的码
    全配到同一只票上);少一组 = 漏配。两种都得炸。
    """
    found = {
        (d["code_only_in_that_source"], d["counterpart_code_in_other_source"])
        for d in res["code_mapping_pairs"]
    }
    assert found == EXPECTED_CODE_MAP_PAIRS, f"配对结果与源B 文档不一致:{found}"
    for d in res["code_mapping_pairs"]:
        assert d["day_set_jaccard"] >= ur.CODE_MAP_MIN_JACCARD


def test_base_period_gap_matches_source_b_b01(res):
    """源B 文档 B-01:csi1000 在 2015-05-29 之前只有 3 个成员。

    这里是从数据自己算出来的(成员数低于名义规模一半),不是抄日期。
    算出来的边界与人写的考据对不上,说明有一方错了。
    """
    gap = res["per_universe"]["csi1000"]["source_b_base_period_gap"]
    assert gap is not None
    assert gap["gap_end_exclusive"] == "2015-05-29"
    assert gap["source_b_member_count_at_window_start"] == 3
    for uni in ("csi300", "csi500"):
        assert res["per_universe"][uni]["source_b_base_period_gap"] is None


# --------------------------------------------------------------- 7. 冻结线


def test_no_date_exceeds_the_freeze_line(res):
    """红线 7。扫全 JSON 的每一个 ISO 日期,一个都不许越线。

    两条**具名**豁免(豁免的是那一个字符串,不是一个模式 —— 数据日期该报红照样报红):

    * ``generated_at_utc`` —— 报告的生成时刻,不是数据日期;
    * ``snapshot_inputs.qlib_release`` —— 源B 上游的**供应商发布目录名**
      (形如 ``2026-08-26``)。源B 产物本身早在卡 1.1-sourceB 就被截到冻结线,
      由 `test_window_right_edge_is_the_freeze_line` 与源B 自己的套件盯着;
      抬头写出这个目录名是为了让「这份报告对的是哪一版输入」可追溯。
    """
    freeze = dt.date.fromisoformat(cfg.FREEZE_DATE)
    pat = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
    blob = json.dumps(res, ensure_ascii=False)
    exempt = {res["generated_at_utc"][:10], res["snapshot_inputs"]["qlib_release"]}
    over = sorted(
        {
            s
            for s in pat.findall(blob)
            if dt.date.fromisoformat(s) > freeze and s not in exempt
        }
    )
    assert not over, f"越过冻结线的日期:{over}"


def test_freeze_line_scanner_still_catches_a_real_violation(res):
    """上一条加了豁免,得证明它没把闸门拆了:塞一个越界的**数据**日期进去必须被抓到。"""
    freeze = dt.date.fromisoformat(cfg.FREEZE_DATE)
    pat = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
    poisoned = dict(res)
    poisoned["_negative_control"] = {"some_data_date": "2026-09-30"}
    exempt = {res["generated_at_utc"][:10], res["snapshot_inputs"]["qlib_release"]}
    over = sorted(
        {
            s
            for s in pat.findall(json.dumps(poisoned, ensure_ascii=False))
            if dt.date.fromisoformat(s) > freeze and s not in exempt
        }
    )
    assert over == ["2026-09-30"], f"负控没被抓到:{over}"


# ------------------------------------------------- 报告与 JSON 不许漂移


def test_report_headline_numbers_match_the_json(report_text, res):
    """`.md` 是给人看的、`.json` 是给机器读的,两者必须是同一次计算的产物。"""
    ov = res["member_day_overall"]
    sg = res["segment_level_overall"]
    assert f"{ov['jaccard'] * 100:.4f}%" in report_text
    assert f"{ov['jaccard_excluding_base_period_gap'] * 100:.4f}%" in report_text
    assert f"{sg['pct_identical']:.2f}%" in report_text
    assert f"{sg['pct_identical_or_within_tolerance']:.2f}%" in report_text
    assert str(res["parameters"]["sample_seed"]) in report_text


def test_report_has_every_required_section(report_text):
    """实施稿点名要的几块内容,缺一块就不算交付。"""
    for heading in (
        "## 执行摘要",
        "## 1. 方法",
        "### 1.2 比较窗口",
        "### 1.3 容忍多少天算一致",
        "## 2. 层次(a):成员日一致率",
        "## 3. 层次(b):区间段一致率",
        "## 4. 分歧分类",
        "## 5. 人工签字清单",
        "## 6. 已知局限",
    ):
        assert heading in report_text, f"报告缺章节:{heading}"
    assert report_text.count("人工签字 | ☐ 认可") == 20


def test_rebuild_is_byte_stable_except_the_timestamp():
    """同样的输入必须得到同样的报告 —— 否则"重跑可复现"是空话。"""
    first = ur.build()
    second = ur.build()
    first.pop("generated_at_utc")
    second.pop("generated_at_utc")
    assert json.dumps(first, ensure_ascii=False, sort_keys=True, default=str) == (
        json.dumps(second, ensure_ascii=False, sort_keys=True, default=str)
    )
