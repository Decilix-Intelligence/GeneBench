"""卡 1.1 源B 验收测试。

跑法::

    cd $REPO && $GENEBENCH_ROOT/env/bin/python -m pytest ops/test_universe_source_b.py -q

断言分四组:
1. **产物存在且权限对**(红线 5:目录 0700、文件 0600)。
2. **解析忠实**:行数与源文件逐一对齐,没有静默丢弃。
3. **区间约定**:闭区间结论的结构证据与外部证据都必须成立。
4. **冻结线**(红线 7):没有任何一行越过 `cfg.FREEZE_DATE`。
"""

from __future__ import annotations

import datetime as dt
import json
import os
import stat
from pathlib import Path

import pyarrow.parquet as pq
import pytest

import genebench_config as cfg
from snapshots import universe_qlib as uq

# 源文件的真实行数(直接 wc -l 得到,写死是故意的:
# 解析器少读一行就得炸,不能让它跟着源文件一起"自洽")
EXPECTED_RAW_LINES = {
    "all": 6142,
    "csi300": 16198,
    "csi500": 22503,
    "csi800": 59207,
    "csi1000": 33008,
    "csiall": 119178,
}


@pytest.fixture(scope="module")
def summary() -> dict:
    path = uq.summary_path()
    assert path.exists(), f"摘要不在:{path};先跑 python -m snapshots.universe_qlib"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def table():
    path = uq.parquet_path()
    assert path.exists(), f"parquet 不在:{path};先跑 python -m snapshots.universe_qlib"
    return pq.read_table(path)


# ----------------------------------------------------------------- 1. 产物与权限


def test_parquet_schema_exact(table):
    """字段名与顺序必须与约定完全一致 —— 下游对账按名取列。"""
    assert table.schema.names == [
        "code",
        "universe",
        "in_date",
        "out_date",
        "raw_code",
        "source_file",
    ]
    assert str(table.schema.field("in_date").type) == "date32[day]"
    assert str(table.schema.field("out_date").type) == "date32[day]"


def test_output_permissions():
    """红线 5:umask 是 002,不显式收紧就会落成组可读。"""
    for path in (uq.parquet_path(), uq.summary_path()):
        mode = stat.S_IMODE(os.stat(path).st_mode)
        assert mode & cfg.FORBIDDEN_MODE_BITS == 0, f"{path} mode={oct(mode)} 对组/其它开放"
    directory = uq.parquet_path().parent
    while directory != cfg.GENEBENCH_ROOT and directory != Path(directory.root):
        mode = stat.S_IMODE(os.stat(directory).st_mode)
        assert mode & cfg.FORBIDDEN_MODE_BITS == 0, f"{directory} mode={oct(mode)} 对组/其它开放"
        directory = directory.parent


def test_output_path_comes_from_shared_config():
    """产物目录走 `cfg.UNIVERSE_DIR`(卡 1.1 源A 引入的共享常量),不许各拼各的。"""
    assert uq.parquet_path().parent == cfg.UNIVERSE_DIR
    assert cfg.UNIVERSE_DIR == cfg.SNAPSHOTS / "v1" / "universe", (
        "共享常量 cfg.UNIVERSE_DIR 的布局变了,产物落点会跟着变 —— 这是跨卡契约,"
        "改之前要同步卡 1.1 源A / 源B 两边"
    )
    assert uq.summary_path().parent == cfg.OPS


def test_universe_qlib_covers_cfg_universes():
    """源B 解出的宇宙必须是 `cfg.UNIVERSES`(源A 的三个基准池)的超集。

    源B 多解 `all`/`csi800`/`csiall`,但**不能少解**源A 要对账的任何一个。
    """
    assert set(cfg.UNIVERSES) <= set(uq.UNIVERSE_ORDER), (
        f"源B 缺了源A 要用的宇宙:{set(cfg.UNIVERSES) - set(uq.UNIVERSE_ORDER)}"
    )
    assert set(uq.UNIVERSE_FILES) == set(uq.UNIVERSE_ORDER)


def test_no_absolute_path_literals_in_module():
    """唯一配置入口是 `genebench_config`,模块里不许有绝对路径字面量。"""
    text = Path(uq.__file__).read_text(encoding="utf-8")
    for needle in ("/data/", "/home/ljn"):
        assert needle not in text, f"模块里出现了绝对路径字面量 {needle!r}"


# ----------------------------------------------------------------- 2. 解析忠实


def test_every_source_line_accounted_for(summary):
    """每个源文件的每一行都必须有去处:成行 / unmapped / bad / reversed。"""
    for universe, expected in EXPECTED_RAW_LINES.items():
        diag = summary["parse_diagnostics"][universe]
        assert diag["n_lines_parsed"] == expected, (
            f"{universe}:解析了 {diag['n_lines_parsed']} 行,源文件有 {expected} 行"
        )


def test_no_silent_drops(summary):
    """坏行 / 倒挂区间必须是 0;真出现了要报出来而不是被吞掉。"""
    for universe, diag in summary["parse_diagnostics"].items():
        assert diag["n_bad_lines"] == 0, f"{universe} 有坏行:{diag['bad_lines'][:3]}"
        assert diag["n_reversed_intervals"] == 0, f"{universe} 有倒挂区间"


def test_prefix_enumeration_is_complete(summary):
    """前缀是扫出来的,不是假设的;出现新前缀必须进 unmapped。"""
    found = set(summary["code_normalization"]["prefixes_found_by_scanning"])
    assert found == {"SH", "SZ", "BJ"}, f"出现了预期外的交易所前缀:{found}"
    assert summary["code_normalization"]["n_unmapped"] == 0
    assert summary["code_normalization"]["unmapped"] == []


def test_symbol_anomaly_is_reported_not_dropped(summary, table):
    """SHT00018 形态异常,但必须**映射后留在产物里**并被上报。"""
    anomalies = summary["code_normalization"]["symbol_anomalies"]
    assert {a["code"] for a in anomalies} == {"T00018.SH"}
    assert len(anomalies) == 7
    codes = set(table.column("code").to_pylist())
    assert "T00018.SH" in codes, "异常码被静默丢弃了"


def test_normalize_code_rules():
    assert uq.normalize_code("SH600000").code == "600000.SH"
    assert uq.normalize_code("SZ000001").code == "000001.SZ"
    assert uq.normalize_code("BJ430017").code == "430017.BJ"
    bad = uq.normalize_code("XX123456")
    assert not bad.ok and bad.code is None and "未知交易所前缀" in bad.reason
    odd = uq.normalize_code("SHT00018")
    assert odd.ok and odd.code == "T00018.SH" and odd.anomaly


def test_row_counts_match_summary(summary, table):
    assert table.num_rows == summary["totals"]["n_intervals"]
    per = summary["per_universe"]
    counts: dict[str, int] = {}
    for value in table.column("universe").to_pylist():
        counts[value] = counts.get(value, 0) + 1
    for universe, stat_ in per.items():
        assert counts[universe] == stat_["n_intervals"]


# ------------------------------------------------------------- 3. 区间约定证据


def test_in_date_is_always_a_trading_day(summary):
    """闭区间结论的第一根支柱:in_date 是生效日,必然是交易日。"""
    for universe, ev in summary["evidence_structural"]["per_universe"].items():
        assert ev["in_date_trading_day_ratio"] == 1.0, f"{universe} 的 in_date 有非交易日"


def test_out_date_is_calendar_not_trading_for_index_files(summary):
    """第二根支柱:csi* 的 out_date 大量落在非交易日 → 它是日历减法的结果。"""
    per = summary["evidence_structural"]["per_universe"]
    for universe in ("csi300", "csi500", "csi800", "csi1000", "csiall"):
        ratio = per[universe]["out_date_trading_day_ratio"]
        assert ratio < 1.0, f"{universe} 的 out_date 全是交易日,与日历减法假设矛盾"
        assert per[universe]["out_weekday_hist"].get("6", 0) > 0, (
            f"{universe} 的 out_date 没有落在周日的 —— 与 `next_in - 1 天` 矛盾"
        )
    # all.txt 相反:两端都是交易日
    assert per["all"]["out_date_trading_day_ratio"] == 1.0


def test_segments_never_overlap(summary):
    """同一 code 的多段之间不许重叠,否则'区间'本身就没有意义。"""
    for universe, ev in summary["evidence_structural"]["per_universe"].items():
        assert ev["n_overlapping_pairs"] == 0, f"{universe} 有重叠区间:{ev['overlap_examples']}"


def test_closed_interval_beats_half_open_on_lake(summary):
    """外部证据:快照日落在 out_date 上时,闭区间给全名单、半开给空集。"""
    cross = summary["evidence_lake_crosscheck"]["per_universe"]
    for universe in ("csi300", "csi500"):
        block = cross[universe]
        assert block["closed_total_symmetric_diff"] < block["halfopen_total_symmetric_diff"]
        assert block["n_discriminating_dates"] > 0
        for day in block["discriminating_dates"]:
            assert day["halfopen_members"] == 0, (
                f"{universe} {day['snapshot_date']}:半开区间本该在边界日塌成空集"
            )
            assert day["closed_members"] == day["lake_members"], (
                f"{universe} {day['snapshot_date']}:闭区间成分数与湖对不上"
            )


def test_named_case_boundary(summary):
    """具名个案:2026-06-30 生效的 csi300 调整,边界必须一刀切干净。"""
    case = summary["evidence_named_case"]
    assert case["n_leavers"] > 0 and case["n_joiners"] > 0
    assert len(case["leavers_present_in_snapshot_before"]) == case["n_leavers"]
    assert case["leavers_present_in_snapshot_after"] == []
    assert case["joiners_present_in_snapshot_before"] == []
    assert len(case["joiners_present_in_snapshot_after"]) == case["n_joiners"]


# --------------------------------------------------------------- 4. 冻结线红线


def test_freeze_line_respected(table):
    """红线 7:产物里没有任何一天越过 `cfg.FREEZE_DATE`。"""
    freeze = dt.date.fromisoformat(cfg.FREEZE_DATE)
    assert max(table.column("out_date").to_pylist()) <= freeze
    assert max(table.column("in_date").to_pylist()) <= freeze


def test_intervals_are_well_formed(table):
    ins = table.column("in_date").to_pylist()
    outs = table.column("out_date").to_pylist()
    assert all(a <= b for a, b in zip(ins, outs)), "存在 in_date > out_date 的行"


def test_censoring_sentinel_is_unambiguous(summary):
    """截断前没有天然的 out_date == FREEZE,所以截断后它就是右删失标记。"""
    assert summary["freeze"]["censoring_sentinel_is_unambiguous"] is True
    assert summary["freeze"]["n_natural_out_eq_freeze_before_clip"] == {}


def test_all_vs_csi_semantics_are_flagged(summary):
    """all.txt 与 csi*.txt 语义不同这件事必须写在摘要里,并点名指数条目。"""
    warn = summary["semantics_warning"]
    assert "上市区间" in warn["all_txt"]
    assert set(warn["non_stock_entries"]) == {"all"}
    assert len(warn["non_stock_entries"]["all"]) == 6


def test_hazards_are_recorded(summary):
    ids = {h["id"] for h in summary["known_data_hazards"]}
    assert {"B-01", "B-02", "B-03", "B-04", "B-05", "B-06", "B-07"} <= ids
